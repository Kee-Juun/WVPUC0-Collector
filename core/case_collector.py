"""
Case collection module for WVPUC0 Document Collector
Handles collecting case data from the website and consolidation logic
"""
import re
from datetime import datetime, date
from typing import List, Dict, Set, Callable, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from utils.new_month_fallback import (
    apply_month_year_selection,
    get_selected_month_year,
    has_no_orders_message,
    wait_for_results_or_no_orders,
)
from database.db_utils import db_url_exists


class CaseCollector:
    """Handles case data collection and consolidation logic"""
    
    def __init__(
        self,
        driver: webdriver.Chrome,
        log_signal: Callable[[str], None],
        config: dict,
        start_date: date,
        end_date: date,
        db_path: Optional[str],
        collector_name: str,
        pdf_processor,
        sfview_checker,
        skipped_files: list,
        selected_month: Optional[int] = None,
        selected_year: Optional[int] = None
    ):
        """
        Initialize case collector
        
        Args:
            driver: Selenium Chrome driver
            log_signal: Signal/function to emit log messages
            config: Configuration dictionary
            start_date: Start date for collection
            end_date: End date for collection
            db_path: Path to database file
            collector_name: Collector name for database
            pdf_processor: PDFProcessor instance
            sfview_checker: SFViewChecker instance
            skipped_files: List to append skipped cases to
            selected_month: Currently selected month
            selected_year: Currently selected year
        """
        self.driver = driver
        self.log_signal = log_signal
        self.config = config
        self.start_date = start_date
        self.end_date = end_date
        self.db_path = db_path
        self.collector_name = collector_name
        self.pdf_processor = pdf_processor
        self.sfview_checker = sfview_checker
        self.skipped_files = skipped_files
        self.selected_month = selected_month
        self.selected_year = selected_year
        self._consolidation_groups = {}

    @staticmethod
    def _extract_document_id(case_link: str) -> str:
        """Use CaseActivityID as the stable document identity when available."""
        match = re.search(r'CaseActivityID=([^&]+)', case_link or '', re.IGNORECASE)
        return match.group(1) if match else ''

    def _normalize_case_link(self, case_link: str) -> str:
        """Normalize relative case links to absolute document URLs."""
        if not case_link:
            return ''
        if case_link.startswith('/'):
            main_url = self.config.get('main_url', '')
            base_url = '/'.join(main_url.split('/')[:3])
            return base_url + case_link
        return case_link

    def _get_case_identity(self, case: Dict) -> str:
        """Return the per-document identity used across filtering stages."""
        return (
            case.get('document_id')
            or case.get('link')
            or f'{case.get("case_number", "")}|{case.get("date_text", "")}|{case.get("description", "")}'
        )

    def _get_listing_exclude_keywords(self) -> List[str]:
        """Return exclusion phrases for list-page descriptions.

        "Notice of Filing" is intentionally omitted by default at this stage
        because the phrase can appear in descriptive text for Commission Orders.
        We reserve that decision for the post-download PDF heading filter.
        """
        listing_exclude_keywords = self.config.get('listing_exclude_keywords')
        if listing_exclude_keywords is not None:
            return listing_exclude_keywords
        return [
            kw
            for kw in self.config.get('exclude_keywords', [])
            if kw.strip().lower() != 'notice of filing'
        ]
    
    def collect_case_data(self) -> List[Dict]:
        """Collect case data from the main table"""
        cases = []
        try:
            main_url = self.config.get('main_url')
            url_candidates = [main_url]
            if isinstance(main_url, str) and main_url.startswith('http://'):
                url_candidates.append('https://' + main_url[len('http://'):])

            loaded = False
            last_error = None
            for url in url_candidates:
                try:
                    self.log_signal(f'Loading main URL: {url}')
                    self.driver.set_page_load_timeout(30)
                    self.driver.get(url)
                    loaded = True
                    break
                except Exception as e:
                    last_error = e
                    self.log_signal(f'Error loading URL {url}: {str(e)}')

            if not loaded:
                raise last_error or Exception('Failed to load main URL')
            # Iterate through all months in the selected date range
            seen_documents = set()
            year = self.start_date.year
            month = self.start_date.month
            while (year, month) <= (self.end_date.year, self.end_date.month):
                self.log_signal(f'Loading main URL: {main_url} (month={month}, year={year})')
                self.driver.set_page_load_timeout(30)
                self.driver.get(main_url)
                apply_month_year_selection(
                    self.driver,
                    month,
                    year,
                    self.log_signal,
                    wait_for_rows=False,
                )
                wait_for_results_or_no_orders(self.driver, timeout=10, month=month, year=year)
                if has_no_orders_message(self.driver):
                    self.log_signal(f'No Orders Found - {month:02d}/{year}')
                    # advance to next month
                    if month == 12:
                        year += 1
                        month = 1
                    else:
                        month += 1
                    continue

                self.selected_month, self.selected_year = get_selected_month_year(self.driver)
                rows = self.driver.find_elements(By.XPATH, '//table//tbody//tr[td]')
                for row in rows:
                    try:
                        cells = row.find_elements(By.XPATH, './/td')
                        if len(cells) < 4:
                            continue
                        date_cell = cells[0]
                        date_text = date_cell.text.strip()
                        if not date_text:
                            continue
                        try:
                            case_date = datetime.strptime(date_text, '%m/%d/%Y').date()
                        except ValueError:
                            continue
                        if self.start_date <= case_date <= self.end_date:
                            try:
                                case_links = cells[1].find_elements(By.XPATH, './/a[@href]')
                                if not case_links:
                                    continue
                                case_cell = case_links[0]
                                case_number = case_cell.text.strip()
                                if not case_number:
                                    continue
                                case_link = self._normalize_case_link(case_cell.get_attribute('href'))
                                document_id = self._extract_document_id(case_link)
                                case_identity = document_id or case_link
                                if not case_identity or case_identity in seen_documents:
                                    continue
                                
                                # Row-level URL duplicate check (before processing)
                                if case_link and self.db_path:
                                    if db_url_exists(self.db_path, self.collector_name, case_link):
                                        self.log_signal(f'Row-level skip (already-saved URL): {case_number} - {case_link}')
                                        seen_documents.add(case_identity)
                                        continue
                                
                                description = cells[3].text.strip()
                                resolution_text = cells[4].text.strip() if len(cells) > 4 else ''
                                if self.should_include_case(description):
                                    cases.append({
                                        'date': case_date,
                                        'date_text': date_text,
                                        'case_number': case_number,
                                        'document_id': document_id,
                                        'case_activity_id': document_id,
                                        'link': case_link,
                                        'description': description,
                                        'resolution_text': resolution_text,
                                        'list_month': month,
                                        'list_year': year,
                                    })
                                    seen_documents.add(case_identity)
                            except Exception as e:
                                self.log_signal(f'Error parsing row: {str(e)}')
                                continue
                    except Exception as e:
                        self.log_signal(f'Error processing row: {str(e)}')
                        continue

                # advance to next month
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1

            self.log_signal(f'Collected {len(cases)} valid cases')
            self._prepare_consolidation_groups(cases)
            return cases
        except Exception as e:
            self.log_signal(f'Error collecting case data: {str(e)}')
            return []
    
    def should_include_case(self, description: str) -> bool:
        """Check if case should be included based on description.
        Rules:
        - "Procedural Order" only excludes when it starts the description (ignoring leading whitespace)
        - Otherwise, if both include and exclude match, the longer phrase wins
        - Else if any include phrase matches, include
        - Else if any exclude phrase matches, exclude
        - Else exclude by default
        """
        include_keywords = self.config.get('include_keywords', [])
        exclude_keywords = self._get_listing_exclude_keywords()
        desc_lower = description.lower()
        include_matches = [kw for kw in include_keywords if kw.lower() in desc_lower]
        exclude_matches = []
        for kw in exclude_keywords:
            kw_lower = kw.lower()
            if kw_lower == 'procedural order':
                # Only exclude if it starts with "Procedural Order"
                if re.search(r'^\s*procedural order\b', desc_lower):
                    exclude_matches.append(kw)
            else:
                if kw_lower in desc_lower:
                    exclude_matches.append(kw)
        longest_include_len = max((len(kw) for kw in include_matches), default=0)
        longest_exclude_len = max((len(kw) for kw in exclude_matches), default=0)
        if longest_include_len > 0 and longest_exclude_len > 0:
            return longest_include_len >= longest_exclude_len
        elif longest_include_len > 0:
            return True
        elif longest_exclude_len > 0:
            return False
        else:
            return False
    
    def _prepare_consolidation_groups(self, cases: List[Dict]) -> None:
        """Build consolidation groups without filtering cases yet."""
        self._consolidation_groups = {}
        if len(cases) <= 1:
            return

        def normalize_consolidation_text(text: str) -> str:
            cleaned = re.sub(r'\d{2}-\d{4}-[A-Z0-9-]+', '', (text or '').lower())
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return cleaned.strip()

        resolution_groups = {}
        consolidation_groups = {}
        consolidation_case_ids = set()
        for case in cases:
            resolution_text = case.get('resolution_text', '').strip()
            description = case.get('description', '').strip()
            consolidation_source = ''
            if 'consolidat' in resolution_text.lower():
                consolidation_source = resolution_text
            elif 'consolidat' in description.lower():
                consolidation_source = description
            if consolidation_source:
                key = normalize_consolidation_text(consolidation_source)
                if key:
                    consolidation_groups.setdefault(key, []).append(case)
                    consolidation_case_ids.add(self._get_case_identity(case))
                    continue
            if resolution_text:
                resolution_groups.setdefault(resolution_text, []).append(case)

        for key, group_cases in consolidation_groups.items():
            if len(group_cases) > 1:
                self._consolidation_groups[f'consolidation:{key}'] = group_cases

        for resolution_text, group_cases in resolution_groups.items():
            remaining_cases = [case for case in group_cases if self._get_case_identity(case) not in consolidation_case_ids]
            if len(remaining_cases) > 1:
                self._consolidation_groups[f'resolution:{resolution_text}'] = remaining_cases
    
    def apply_consolidation_rules(self, cases: List[Dict], tracker_duplicates: Set[str]) -> List[Dict]:
        """Apply consolidation logic after duplicate filtering."""
        if not self._consolidation_groups:
            return cases

        current_case_ids = {self._get_case_identity(case) for case in cases}
        skipped_case_ids = {self._get_case_identity(case) for case in self.skipped_files if self._get_case_identity(case)}
        processed_case_ids = set()
        final_cases = []
        consolidated_count = 0

        for group_cases in self._consolidation_groups.values():
            if len(group_cases) <= 1:
                continue

            # All case numbers in this consolidated group (including ones already
            # removed by tracker or previous filters).
            group_all_numbers = list(dict.fromkeys(case['case_number'] for case in group_cases))

            # Only cases still under consideration in this run.
            group_current = [case for case in group_cases if self._get_case_identity(case) in current_case_ids]
            if len(group_current) <= 0:
                # Nothing left from this group to process in this run.
                continue

            consolidated_count += 1
            group_current.sort(key=lambda x: x['case_number'])
            self.log_signal(f'Consolidated group detected: {", ".join(group_all_numbers)}')

            # 1) Check database first - if any member exists in database, skip entire group
            db_canonical = None
            if self.db_path:
                try:
                    for case in group_cases:
                        case_link = self._normalize_case_link(case.get('link', ''))
                        if case_link and db_url_exists(self.db_path, self.collector_name, case_link):
                            db_canonical = case['case_number']
                            break
                except Exception as e:
                    self.log_signal(f'Error checking database in consolidation: {str(e)}')
                    db_canonical = None
            
            if db_canonical:
                self.log_signal(
                    f'  → Consolidated order already exists in database via {db_canonical}; '
                    f'skipping group: {", ".join(group_all_numbers)}'
                )
                for case in group_current:
                    case_id = self._get_case_identity(case)
                    if case_id not in skipped_case_ids:
                        case['consolidation_reason'] = (
                            f'Consolidated order already exists in database via {db_canonical}'
                        )
                        self.skipped_files.append(case)
                        skipped_case_ids.add(case_id)
                    processed_case_ids.add(case_id)
                continue

            # 2) If any member of this consolidated group is already in SF-View,
            # treat the entire group as already represented across runs.
            sfview_canonical = None
            try:
                for num in group_all_numbers:
                    if self.sfview_checker.check_case_exists_in_sfview(num):
                        sfview_canonical = num
                        break
            except Exception:
                sfview_canonical = None

            if sfview_canonical:
                self.log_signal(
                    f'  → Consolidated order already exists in SF-View via {sfview_canonical}; '
                    f'skipping group: {", ".join(group_all_numbers)}'
                )
                for case in group_current:
                    case_id = self._get_case_identity(case)
                    if case_id not in skipped_case_ids:
                        case['consolidation_reason'] = (
                            f'Consolidated order already exists in SF-View via {sfview_canonical}'
                        )
                        self.skipped_files.append(case)
                        skipped_case_ids.add(case_id)
                    processed_case_ids.add(case_id)
                continue

            # 3) If any member is already in Tracker duplicates, skip whole group.
            if any(case_num in tracker_duplicates for case_num in group_all_numbers):
                matched = [case_num for case_num in group_all_numbers if case_num in tracker_duplicates]
                self.log_signal(f'  → Already collected in tracker: {", ".join(matched)}')
                self.log_signal(f'  → Skipped: {", ".join(group_all_numbers)} ({len(group_all_numbers)} duplicates)')
                for case in group_current:
                    case_id = self._get_case_identity(case)
                    if case_id not in skipped_case_ids:
                        case['consolidation_reason'] = 'Consolidated with already collected case'
                        self.skipped_files.append(case)
                        skipped_case_ids.add(case_id)
                    processed_case_ids.add(case_id)
                continue

            selected_case = group_current[0]
            skipped_cases = group_current[1:]
            skipped_numbers = [case['case_number'] for case in skipped_cases]
            self.log_signal(f'  → Selected: {selected_case["case_number"]}')
            self.log_signal(f'  → Skipped: {", ".join(skipped_numbers)} ({len(skipped_cases)} duplicates)')
            final_cases.append(selected_case)
            processed_case_ids.add(self._get_case_identity(selected_case))
            for skipped_case in skipped_cases:
                case_id = self._get_case_identity(skipped_case)
                if case_id not in skipped_case_ids:
                    skipped_case['consolidation_reason'] = f'Consolidated with {selected_case["case_number"]}'
                    self.skipped_files.append(skipped_case)
                    skipped_case_ids.add(case_id)
                processed_case_ids.add(case_id)

        for case in cases:
            case_id = self._get_case_identity(case)
            if case_id not in processed_case_ids:
                final_cases.append(case)

        if consolidated_count > 0:
            self.log_signal(f'Consolidation complete: {consolidated_count} groups detected, {len(final_cases)} cases to process')
        return final_cases
    
    def detect_consolidated_cases(self, cases: List[Dict]) -> List[Dict]:
        """Detect and handle consolidated cases with identical resolution text"""
        self._prepare_consolidation_groups(cases)
        return self.apply_consolidation_rules(cases, set())

