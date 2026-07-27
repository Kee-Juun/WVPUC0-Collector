# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'scraper.py'
# Bytecode version: 3.13.0rc3 (3571)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nWeb scraping logic for WVPUC0 Document Collector\n"""
import time
import re
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font
from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from config.config import ConfigManager
from utils.logger import Logger
from utils.tracker_duplicate_checker import TrackerDuplicateChecker, TrackerCheckFailed
from database.db_utils import (
    init_db, get_db_path, canonicalize_url, sha1_of_bytes,
    db_url_exists, db_title_exists, db_sha1_saved_path, db_sha1_with_date,
    db_insert_or_update_document, db_set_last_run
)
from utils.new_month_fallback import (
    apply_new_month_fallback,
    get_selected_month_year,
    apply_month_year_selection,
    has_no_orders_message,
    wait_for_results_or_no_orders,
)
from reporting.excel_reporter import ExcelReporter
from download.pdf_processor import PDFProcessor
from reporting.reporting import Reporter
from utils.sfview_checker import SFViewChecker
from browser.browser_manager import BrowserManager
from browser.page_navigator import PageNavigator
from .case_collector import CaseCollector
from download.download_manager import DownloadManager
from utils.consolidated_case_checker import ConsolidatedCaseChecker
class WVPCU0Scraper(QThread):
    """Main scraping thread"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    def __init__(self, start_date: date, end_date: date, headless: bool=False):
        super().__init__()
        self.start_date = start_date
        self.end_date = end_date
        self.headless = headless
        self.config = ConfigManager()
        self.logger = Logger()
        self.browser_manager = BrowserManager(self.log_signal.emit, self.config, self.headless)
        self.driver = None  # Will be set from browser_manager after launch
        self.download_dir = None
        self.downloaded_files = []
        self.skipped_files = []
        self.selected_month = None
        self.selected_year = None
        self.last_duplicate_filename = None
        self.last_duplicate_date = None
        self.last_duplicate_sid = None
        self._consolidation_groups = {}
        # Fingerprints of downloaded PDFs for this run:
        # (size, sha256) -> {'filename': str, 'case_number': str}
        # Database for persistent duplicate tracking
        self.db_path = None
        self.collector_name = "WVPUC0"
        
        # Initialize helper modules
        self.reporter = Reporter(self.log_signal.emit)
        self.sfview_checker = SFViewChecker(self.log_signal.emit, self.config)
        # PDF processor and Excel reporter will be initialized after config is fully loaded
        self.pdf_processor = None
        self.excel_reporter = None
    def run(self):
        """Main execution method"""
        try:
            self.status_signal.emit('Loading WVPUC0 Court Site...')
            self.log_signal.emit('Starting WVPUC0 document collection...')
            config_path = getattr(self.config, 'config_path', None)
            if config_path:
                self.log_signal.emit(f'Config loaded from: {config_path}')
            self.log_signal.emit(
                'Config summary: '
                f'headless={self.config.get("headless", False)}, '
                f'tracker_enabled={self.config.get("tracker_enabled", False)}, '
                f'main_url={self.config.get("main_url", "")}'
            )
            
            # Initialize helper modules that need runtime data
            self.pdf_processor = PDFProcessor(self.log_signal.emit, self.config, self.skipped_files)
            self.excel_reporter = ExcelReporter(self.log_signal.emit, self.pdf_processor.generate_filename)
            # Page navigator will be initialized after driver is created
            self.page_navigator = None
            
            # Initialize database for persistent duplicate tracking
            self.db_path = get_db_path(self.config)
            init_db(self.db_path)
            self.log_signal.emit(f'Database initialized: {self.db_path}')
            
            base_download_dir = Path.home() / self.config.get('download_path')
            timestamp = datetime.now().strftime('%m-%d-%Y_%I-%M-%S-%p')
            run_folder_name = f'WVPUC0_{timestamp}'
            self.download_dir = base_download_dir / run_folder_name
            self.download_dir.mkdir(parents=True, exist_ok=True)
            self.logger = Logger(log_dir=str(self.download_dir))
            self.driver = self.browser_manager.launch_chrome_driver(self.download_dir)
            if not self.driver:
                raise Exception('Failed to launch Chrome driver')

            # Initialize page navigator after driver is ready
            self.page_navigator = PageNavigator(
                self.driver,
                self.log_signal.emit,
                self.config,
                self.browser_manager,
                self.selected_month,
                self.selected_year
            )
            
            # Initialize case collector
            self.case_collector = CaseCollector(
                self.driver,
                self.log_signal.emit,
                self.config,
                self.start_date,
                self.end_date,
                self.db_path,
                self.collector_name,
                self.pdf_processor,
                self.sfview_checker,
                self.skipped_files,
                self.selected_month,
                self.selected_year
            )
            
            # Initialize download manager
            self.download_manager = DownloadManager(
                self.driver,
                self.log_signal.emit,
                self.config,
                self.browser_manager,
                self.page_navigator,
                self.pdf_processor,
                self.sfview_checker,
                self.skipped_files,
                self.downloaded_files,
                self.db_path,
                self.collector_name,
                self.download_dir,
                self.status_signal.emit,
                self.progress_signal.emit
            )

            self.browser_manager.setup_download_preferences(self.download_dir)
            
            cases = self.case_collector.collect_case_data()
            # Update selected_month/year from collector
            self.selected_month = self.case_collector.selected_month
            self.selected_year = self.case_collector.selected_year
            if self.page_navigator:
                self.page_navigator.selected_month = self.selected_month
                self.page_navigator.selected_year = self.selected_year
            if not cases:
                self.log_signal.emit('No cases found in the specified date range.')
                self.finished_signal.emit(True, 'No cases found')
            else:
                tracker_duplicates = set()
                if self.config.get('tracker_enabled', False):
                    try:
                        self.log_signal.emit('Starting online duplicate check (tracker)...')
                        tracker_checker = TrackerDuplicateChecker(
                            self.driver,
                            self.logger,
                            self.log_signal.emit,
                            self.config
                        )
                        cases, tracker_skipped = tracker_checker.filter_cases(
                            cases,
                            self.start_date,
                            self.end_date
                        )
                        if tracker_skipped:
                            self.skipped_files.extend(tracker_skipped)
                            self.log_signal.emit(f'Tracker duplicates skipped: {len(tracker_skipped)}')
                            tracker_duplicates.update(
                                item.get('case_number') for item in tracker_skipped if item.get('case_number')
                            )
                            try:
                                most_recent = None
                                most_recent_date = None
                                for item in tracker_skipped:
                                    item_date = None
                                    tracker_date = item.get('tracker_date')
                                    if isinstance(tracker_date, str) and tracker_date.isdigit() and len(tracker_date) == 8:
                                        try:
                                            item_date = datetime.strptime(tracker_date, '%m%d%Y').date()
                                        except Exception:
                                            item_date = None
                                    if not item_date:
                                        raw_date = item.get('date')
                                        if isinstance(raw_date, date):
                                            item_date = raw_date
                                    if item_date and (most_recent_date is None or item_date > most_recent_date):
                                        most_recent = item
                                        most_recent_date = item_date
                                if most_recent and most_recent_date:
                                    self.last_duplicate_filename = most_recent.get('tracker_filename') or self.pdf_processor.generate_filename(most_recent)
                                    self.last_duplicate_date = most_recent_date.strftime('%m/%d/%Y')
                                    self.last_duplicate_sid = most_recent.get('tracker_sid')
                            except Exception:
                                pass
                        self.log_signal.emit('Online duplicate check (tracker) completed')
                        # Return to the main site after tracker navigation
                        main_url = self.config.get('main_url')
                        if main_url:
                            self.log_signal.emit(f'Returning to main URL after tracker check: {main_url}')
                            self.driver.get(main_url)
                    except TrackerCheckFailed as e:
                        self.log_signal.emit(str(e))
                        raise
                    except Exception as e:
                        message = f'Error during tracker duplicate check: {str(e)}'
                        self.log_signal.emit(message)
                        if not self.config.get('tracker_fail_open', False):
                            raise RuntimeError(message) from e
                # Update case collector with current state
                self.case_collector.selected_month = self.selected_month
                self.case_collector.selected_year = self.selected_year
                cases = self.case_collector.apply_consolidation_rules(cases, tracker_duplicates)
                self.pdf_processor.assign_filename_letters(cases)
                if self.config.get('prefetch_pdf_links', False):
                    self.page_navigator.prefetch_pdf_links(cases)
                if not cases and self.skipped_files:
                    self.excel_reporter.save_results(self.download_dir, self.downloaded_files, self.skipped_files)
                    no_new_msg = 'No new documents collected. All documents already exist in the database.'
                    self.finished_signal.emit(True, no_new_msg)
                    return
                self.log_signal.emit(f'Found {len(cases)} cases to process')
                processed = 0
                # duplicate_count = 0  # Removed unnecessary duplicate limit
                # Force single-file-at-a-time downloads for accuracy
                # Disable bulk tab downloads to ensure one file at a time
                if False and self.config.get('bulk_tab_downloads', False):
                    processed, duplicate_count = self.download_manager.download_cases_in_tabs(cases, self.download_dir)
                else:
                    for i, case in enumerate(cases):
                        self.progress_signal.emit(int(i / len(cases) * 100))
                        self.status_signal.emit(f'Downloading {i + 1}/{len(cases)}: {case["case_number"]}')
                        if self.download_manager.process_case(case, self.download_dir):
                            processed += 1
                        # Removed duplicate counting logic - unnecessary limit
                self.progress_signal.emit(100)
                self.status_signal.emit('Checking for consolidated cases...')
                
                # Check for consolidated cases and delete if other members exist in SF-View
                # ConfigManager has .config dict attribute
                config_dict = self.config.config
                consolidated_checker = ConsolidatedCaseChecker(config_dict, self.log_signal.emit)
                remaining_downloaded, deleted_consolidated = consolidated_checker.check_and_delete_consolidated_cases(
                    self.download_dir, self.downloaded_files
                )
                
                # Update downloaded_files to exclude deleted consolidated cases
                self.downloaded_files = remaining_downloaded
                
                # Get consolidated cases report data
                consolidated_report = consolidated_checker.get_consolidated_cases_report()
                
                self.status_signal.emit('Collection completed')
                self.excel_reporter.save_results(
                    self.download_dir, 
                    self.downloaded_files, 
                    self.skipped_files,
                    consolidated_cases=consolidated_report
                )
                
                # Record last successful run in database
                if self.db_path:
                    try:
                        db_set_last_run(self.db_path, self.collector_name)
                        self.log_signal.emit('Last successful run recorded in database')
                    except Exception as e:
                        self.log_signal.emit(f'Error recording last run: {str(e)}')
                
                self.reporter.log_summary(
                    includes_count=len(self.downloaded_files),
                    duplicates_count=len(self.skipped_files),
                    errors_count=max(0, len(cases) - len(self.downloaded_files) - len(self.skipped_files)),
                    last_duplicate_filename=self.last_duplicate_filename,
                    last_duplicate_sid=self.last_duplicate_sid,
                    last_duplicate_date=self.last_duplicate_date
                )
                success_msg = f'Collection completed. Downloaded: {len(self.downloaded_files)}, Skipped: {len(self.skipped_files)}'
                self.finished_signal.emit(True, success_msg)
        except Exception as e:
            self.log_signal.emit(f'Error during collection: {str(e)}')
            self.finished_signal.emit(False, f'Collection failed: {str(e)}')
        finally:
            self.browser_manager.quit()

    def detect_consolidated_cases(self, cases: List[Dict]) -> List[Dict]:
        """Detect and handle consolidated cases with identical resolution text"""
        return self.case_collector.detect_consolidated_cases(cases)
