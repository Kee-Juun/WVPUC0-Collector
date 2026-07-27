"""
Page navigation module for WVPUC0 Document Collector
Handles case page navigation, PDF URL extraction, and tab management
"""
import time
import re
from typing import Dict, List, Optional, Tuple, Callable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.new_month_fallback import (
    get_selected_month_year,
    apply_month_year_selection,
)


class PageNavigator:
    """Handles page navigation and case page opening"""
    
    def __init__(
        self, 
        driver: webdriver.Chrome,
        log_signal: Callable[[str], None],
        config: dict,
        browser_manager,
        selected_month: Optional[int] = None,
        selected_year: Optional[int] = None
    ):
        """
        Initialize page navigator
        
        Args:
            driver: Selenium Chrome driver
            log_signal: Signal/function to emit log messages
            config: Configuration dictionary
            browser_manager: BrowserManager instance
            selected_month: Currently selected month
            selected_year: Currently selected year
        """
        self.driver = driver
        self.log_signal = log_signal
        self.config = config
        self.browser_manager = browser_manager
        self.selected_month = selected_month
        self.selected_year = selected_year
    
    def open_case_page(self, case: Dict, case_link: str) -> str:
        """Open the case page by clicking from list (opens in new tab).
        Returns the original window handle so caller can switch back later.
        """
        original_handle = self.driver.current_window_handle
        
        # Ensure we're on the list page
        if not self.browser_manager.is_orders_by_month_page():
            main_url = self.config.get('main_url')
            if main_url:
                self.driver.get(main_url)
                time.sleep(2)
        
        # Wait for list page to be ready
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//table//tbody//tr'))
            )
        except Exception:
            main_url = self.config.get('main_url')
            if main_url:
                self.driver.get(main_url)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, '//table//tbody//tr'))
                )
        
        # Set correct month/year if needed
        target_month = case.get('list_month') or self.selected_month
        target_year = case.get('list_year') or self.selected_year
        if target_month and target_year:
            current_month, current_year = get_selected_month_year(self.driver)
            if current_month != target_month or current_year != target_year:
                apply_month_year_selection(
                    self.driver,
                    target_month,
                    target_year,
                    self.log_signal,
                )
        
        # Find the case link
        case_id_match = re.search(r'CaseActivityID=([^&]+)', case_link, re.IGNORECASE)
        if case_id_match:
            case_id = case_id_match.group(1)
            link_xpath = f'//a[contains(@href, "CaseActivityID={case_id}")]'
        else:
            link_xpath = f'//a[normalize-space(text())="{case["case_number"]}"]'
        
        # Wait for link and click it (will open in new tab)
        existing_handles = set(self.driver.window_handles)
        link = WebDriverWait(self.driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, link_xpath))
        )
        
        # Get the link href before clicking
        link_href = link.get_attribute('href')
        if not link_href:
            raise Exception("Case link has no href attribute")
        
        # Make sure href is absolute
        if link_href.startswith('/'):
            main_url = self.config.get('main_url', '')
            base_url = '/'.join(main_url.split('/')[:3])
            link_href = base_url + link_href
        
        # Open link in new tab using window.open (more reliable than clicking)
        self.log_signal(f'Opening case link in new tab for {case["case_number"]}: {link_href}')
        self.driver.execute_script(f'window.open("{link_href}", "_blank");')
        
        # Wait for new tab to open
        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.window_handles) > len(existing_handles)
            )
        except Exception as e:
            raise Exception(f"New tab did not open after window.open: {str(e)}")
        
        # Switch to the new tab
        new_handles = [h for h in self.driver.window_handles if h not in existing_handles]
        if new_handles:
            new_handle = new_handles[0]
            self.driver.switch_to.window(new_handle)
            self.log_signal(f'Switched to new tab, waiting for page to load...')
            
            # Wait for page to actually load with a valid URL
            max_wait = 15
            for wait_attempt in range(max_wait):
                try:
                    # Check if window still exists
                    if new_handle not in self.driver.window_handles:
                        raise Exception("New tab closed before page could load")
                    
                    # Check if we have a valid URL
                    current_url = self.driver.current_url
                    if current_url and current_url != 'about:blank' and 'data:' not in current_url:
                        # Wait for page to be ready
                        ready_state = self.driver.execute_script('return document.readyState')
                        if ready_state == 'complete':
                            self.log_signal(f'New tab loaded successfully: {current_url}')
                            time.sleep(1)  # Extra moment for page to stabilize
                            return original_handle
                    
                    time.sleep(1)
                except Exception as e:
                    if wait_attempt < max_wait - 1:
                        time.sleep(1)
                        continue
                    raise Exception(f"Page did not load in new tab: {str(e)}")
            
            # If we get here, page didn't load properly
            current_url = self.driver.current_url if new_handle in self.driver.window_handles else "TAB_CLOSED"
            raise Exception(f"Page did not load properly in new tab. URL: {current_url}")
        else:
            raise Exception("New tab did not open after clicking case link")

    def open_case_in_new_tab(self, case: Dict, case_link: str) -> Optional[Tuple[str, str]]:
        """Open case link in a new tab from the list page to preserve referrer.
        Returns (original_handle, new_handle) or None if failed.
        """
        try:
            original_handle = self.driver.current_window_handle
            main_url = self.config.get('main_url')
            if not self.browser_manager.is_orders_by_month_page():
                if main_url:
                    self.driver.get(main_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//table//tbody//tr'))
            )
            target_month = case.get('list_month') or self.selected_month
            target_year = case.get('list_year') or self.selected_year
            if target_month and target_year:
                current_month, current_year = get_selected_month_year(self.driver)
                if current_month != target_month or current_year != target_year:
                    apply_month_year_selection(
                        self.driver,
                        target_month,
                        target_year,
                        self.log_signal,
                    )
            case_id_match = re.search(r'CaseActivityID=([^&]+)', case_link, re.IGNORECASE)
            link_xpath = None
            if case_id_match:
                case_id = case_id_match.group(1)
                link_xpath = f'//a[contains(@href, "CaseActivityID={case_id}")]'
            if not link_xpath:
                link_xpath = f'//a[normalize-space(text())="{case["case_number"]}"]'

            link = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, link_xpath))
            )
            link_href = link.get_attribute('href')
            if link_href and link_href.startswith('/'):
                base_url = '/'.join(main_url.split('/')[:3])
                link_href = base_url + link_href
            if not link_href:
                return None

            existing_handles = set(self.driver.window_handles)
            self.driver.execute_script('window.open(arguments[0], "_blank");', link_href)
            try:
                WebDriverWait(self.driver, 8).until(
                    lambda d: len(d.window_handles) > len(existing_handles)
                )
            except Exception:
                return None
            new_handles = [h for h in self.driver.window_handles if h not in existing_handles]
            if not new_handles:
                return None
            new_handle = new_handles[-1]
            try:
                self.driver.switch_to.window(new_handle)
            except Exception:
                return None
            return original_handle, new_handle
        except Exception:
            return None
    
    def extract_pdf_url(self, base_url: str) -> str:
        """Extract a direct PDF URL from the current page, if present."""
        try:
            current_url = self.driver.current_url or ''
            if current_url.lower().endswith('.pdf'):
                return current_url
            pdf_links = self.driver.find_elements(By.XPATH, '//a[contains(@href, ".pdf")]')
            if not pdf_links:
                return ''
            href = pdf_links[0].get_attribute('href') or ''
            if href.startswith('/'):
                return base_url + href
            return href
        except Exception:
            return ''
    
    def prefetch_pdf_links(self, cases: List[Dict]) -> None:
        """Pre-collect PDF links to speed up downloads."""
        if not cases:
            return
        main_url = self.config.get('main_url') or ''
        base_url = '/'.join(main_url.split('/')[:3]) if main_url else ''
        self.log_signal('Prefetching PDF links...')
        for case in cases:
            if case.get('pdf_url'):
                continue
            try:
                case_link = case.get('link', '')
                if case_link.startswith('/'):
                    case_link = base_url + case_link
                original_handle = self.open_case_page(case, case_link)
                time.sleep(1)
                pdf_url = self.extract_pdf_url(base_url)
                if pdf_url:
                    case['pdf_url'] = pdf_url
                self.browser_manager.close_extra_window(original_handle)
            except Exception as e:
                self.log_signal(f'Prefetch PDF link failed for {case.get("case_number")}: {str(e)}')
                try:
                    self.browser_manager.close_extra_window(self.driver.current_window_handle)
                except Exception:
                    pass

