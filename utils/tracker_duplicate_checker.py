"""
Online duplicate checking against LN Doc Tracker.
Modeled after ALLCUS BOT duplicate checker, but configurable.
"""
import re
import time
from datetime import date, timedelta
from typing import List, Dict, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class TrackerCheckFailed(RuntimeError):
    """Raised when tracker duplicate checking cannot complete safely."""


class TrackerDuplicateChecker:
    """Duplicate checker using LN Doc Tracker (configurable)."""

    def __init__(self, driver, logger, log_func, config):
        self.driver = driver
        self.logger = logger
        self.log_func = log_func
        self.config = config

    def _log(self, message: str) -> None:
        if self.log_func:
            try:
                self.log_func(message)
                return
            except Exception:
                pass
        if self.logger:
            try:
                self.logger.info(message)
            except Exception:
                pass

    def _normalize_case_number(self, value: str) -> str:
        return re.sub(r'[^A-Z0-9]', '', (value or '').upper())

    def _strip_filename_variant_suffix(self, value: str) -> str:
        """Remove local a/b/c... filename suffixes before date matching."""
        match = re.match(r'^([A-Z0-9-]+?)([a-z]+)?$', value or '')
        if match:
            return match.group(1)
        return value or ''

    def _normalize_date(self, value: str) -> str:
        return re.sub(r'[^0-9]', '', (value or ''))

    def _get(self, key: str, default=None):
        if self.config:
            return self.config.get(key, default)
        return default

    def _handle_tracker_failure(self, cases: List[Dict], message: str) -> Tuple[List[Dict], List[Dict]]:
        """Either fail open by config or stop the run with a clear error."""
        if self._get('tracker_fail_open', False):
            self._log(f'{message} Continuing without tracker filtering because tracker_fail_open=true.')
            return cases, []
        raise TrackerCheckFailed(message)

    def _get_tracker_retry_delay(self, attempt: int) -> int:
        """Return the backoff delay before the given retry attempt."""
        base_delay = int(self._get('tracker_retry_backoff_seconds', 5))
        max_delay = int(self._get('tracker_retry_max_backoff_seconds', 30))
        if attempt <= 1:
            return 0
        delay = base_delay * (2 ** (attempt - 2))
        return min(max(0, delay), max_delay)

    def _reset_tracker_state(self) -> None:
        """Best-effort cleanup before retrying the tracker flow."""
        if not self.driver:
            return
        try:
            self.driver.execute_script('window.stop();')
        except Exception:
            pass
        try:
            self.driver.get('about:blank')
        except Exception:
            pass

    def navigate_to_tracker(self) -> bool:
        url = self._get('tracker_url')
        if not url:
            self._log('Tracker URL not configured; skipping online duplicate check')
            return False
        try:
            self._log(f'Navigating to tracker: {url}')
            self.driver.get(url)
            return True
        except Exception as e:
            self._log(f'Error navigating to tracker: {str(e)}')
            return False

    def setup_query(self) -> bool:
        """Run the tracker query wizard (ALLCUS-style XPaths by default)."""
        try:
            if not self._get('tracker_use_query_wizard', True):
                return True

            first_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_first_query_xpath', '/html/body/table/tbody/tr/td[2]/table[3]/tbody/tr[1]/td/a/img')))
            )
            first_button.click()

            second_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_second_query_xpath', '/html/body/table/tbody/tr/td[2]/center/a/img')))
            )
            second_button.click()

            radio_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_open_existing_xpath', '//*[@id="startQuery"]/table/tbody/tr/td[2]/table[2]/tbody/tr[3]/td/input')))
            )
            radio_button.click()

            next_button1 = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_next1_xpath', '//*[@id="startQuery"]/table/tbody/tr/td[2]/table[2]/tbody/tr[4]/td/input')))
            )
            next_button1.click()

            option_xpath = self._get('tracker_query_option_xpath', '//*[@id="select1"]/option[19]')
            option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, option_xpath))
            )
            option.click()

            next_button2 = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_next2_xpath', '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[3]/td/input')))
            )
            next_button2.click()

            next_button3 = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_next3_xpath', '//input[@type="submit" and @value="  Next  "]')))
            )
            next_button3.click()

            search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self._get('tracker_search_xpath', '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[9]/td/input[3]')))
            )
            search_button.click()

            return True
        except Exception as e:
            self._log(f'Error setting up tracker query: {str(e)}')
            return False

    def enter_search_criteria(self, start_date: date, end_date: date) -> bool:
        court_code = self._get('tracker_court_code', '')
        try:
            court_xpath = self._get('tracker_court_xpath', '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[27]/td[4]/input')
            date_xpath = self._get('tracker_date_xpath', '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[33]/td[4]/input')
            finish_xpath = self._get('tracker_finish_xpath', '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[72]/td/input[5]')

            if court_code:
                court_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, court_xpath))
                )
                court_input.clear()
                court_input.send_keys(court_code)

            window_days_before = int(self._get('tracker_date_window_days_before', 30))
            window_days_after = int(self._get('tracker_date_window_days_after', 30))
            if window_days_before > 0 or window_days_after > 0:
                tracker_start = end_date - timedelta(days=max(0, window_days_before))
                tracker_end = end_date + timedelta(days=max(0, window_days_after))
                self._log(
                    f'Using tracker date window: '
                    f'-{window_days_before}d/+{window_days_after}d '
                    f'({tracker_start:%m/%d/%Y}-{tracker_end:%m/%d/%Y})'
                )
            else:
                tracker_start = start_date
                tracker_end = end_date
            date_range = f"{tracker_start.strftime('%m/%d/%Y')}-{tracker_end.strftime('%m/%d/%Y')}"
            date_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, date_xpath))
            )
            date_input.clear()
            date_input.send_keys(date_range)

            finish_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, finish_xpath))
            )
            finish_button.click()
            return True
        except Exception as e:
            self._log(f'Error entering tracker search criteria: {str(e)}')
            return False

    def wait_for_report(self, timeout: int = 60) -> bool:
        """Wait until the tracker report is actually loaded.

        We treat the appearance of the literal text 'END OF REPORT' anywhere on
        the page as the primary readiness signal, since that indicates the
        report has finished rendering. We still fall back to the old
        report-cell check so existing configs keep working.
        """
        try:
            report_cell_xpath = self._get(
                'tracker_report_ready_xpath',
                '/html/body/form/table[2]/tbody/tr[1]/td[1]',
            )

            def _report_ready(driver):
                # Prefer the semantic "END OF REPORT" marker if present.
                try:
                    if 'END OF REPORT' in (driver.page_source or ''):
                        return True
                except Exception:
                    # Ignore transient issues reading page_source
                    pass

                # Fallback: original behavior – wait for the first report cell.
                try:
                    elem = driver.find_element(By.XPATH, report_cell_xpath)
                    return elem is not None
                except Exception:
                    return False

            WebDriverWait(self.driver, timeout).until(_report_ready)
            return True
        except TimeoutException:
            self._log(f'Tracker report failed to load within {timeout} seconds')
            return False

    def _extract_tracker_rows_snapshot(self) -> List[List[str]]:
        """
        Snapshot tracker report rows into plain cell-text lists.

        This uses one JavaScript DOM/XPath pass so we avoid repeated Selenium
        row/cell reads across the large tracker result table.
        """
        rows_xpath = self._get('tracker_rows_xpath', '//table[2]//tr')

        try:
            row_snapshots = self.driver.execute_script(
                """
                const xpath = arguments[0];

                function rowsFromXPath(path) {
                    const result = document.evaluate(
                        path,
                        document,
                        null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                        null
                    );
                    const rows = [];
                    for (let i = 0; i < result.snapshotLength; i += 1) {
                        rows.push(result.snapshotItem(i));
                    }
                    return rows;
                }

                let rows = rowsFromXPath(xpath);
                if (!rows.length && xpath !== '//tr') {
                    rows = rowsFromXPath('//tr');
                }

                return rows.map((row) =>
                    Array.from(row.querySelectorAll('td')).map(
                        (cell) => (cell.textContent || '').trim()
                    )
                );
                """,
                rows_xpath,
            )

            if isinstance(row_snapshots, list):
                return row_snapshots

        except Exception as e:
            self._log(
                f'JavaScript tracker table extraction failed; falling back to Selenium reads: {str(e)}'
            )

        rows = self.driver.find_elements(By.XPATH, rows_xpath)
        if not rows:
            rows = self.driver.find_elements(By.XPATH, '//tr')

        row_snapshots: List[List[str]] = []
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, 'td')
                row_snapshots.append([cell.text.strip() for cell in cells])
            except Exception:
                row_snapshots.append([])
        return row_snapshots

    def extract_tracker_case_keys(self, row_snapshots: List[List[str]] | None = None) -> List[Tuple[str, str]]:
        """Extract (case_number, date) keys from tracker rows."""
        keys: List[Tuple[str, str]] = []
        case_regex = self._get('tracker_case_regex', r'\d{2}-\d{4}-[A-Z0-9-]+')
        date_regex = self._get('tracker_date_regex', r'\d{8}')
        case_re = re.compile(case_regex, re.IGNORECASE)
        date_re = re.compile(date_regex)
        case_col_index = int(self._get('tracker_case_column_index', 3))  # 1-based
        date_col_index = int(self._get('tracker_date_column_index', 0))  # 1-based, 0 disables

        try:
            row_snapshots = row_snapshots or self._extract_tracker_rows_snapshot()

            for cells in row_snapshots[1:]:
                if not cells:
                    continue
                text_parts: List[str] = []
                if len(cells) >= case_col_index:
                    text_parts.append((cells[case_col_index - 1] or '').strip())
                # Fallback: scan all cells in the row
                if not text_parts[0:1]:
                    text_parts = [(cell or '').strip() for cell in cells]

                for text in text_parts:
                    if not text:
                        continue
                    case_matches = case_re.findall(text)
                    date_matches = date_re.findall(text)
                    if not date_matches and date_col_index and len(cells) >= date_col_index:
                        date_cell_text = (cells[date_col_index - 1] or '').strip()
                        if date_cell_text:
                            date_matches = date_re.findall(date_cell_text)
                    for case_match in case_matches:
                        if date_matches:
                            for date_match in date_matches:
                                keys.append((case_match, date_match))
                        else:
                            keys.append((case_match, ''))

            return keys
        except Exception as e:
            self._log(f'Error extracting tracker case numbers: {str(e)}')
            return []

    def extract_tracker_text_date_keys(self, row_snapshots: List[List[str]] | None = None) -> List[Tuple[str, str, str, str]]:
        """Extract normalized text+date keys from tracker rows (for unconventional names)."""
        keys: List[Tuple[str, str, str, str]] = []
        case_col_index = int(self._get('tracker_case_column_index', 3))  # 1-based
        date_col_index = int(self._get('tracker_date_column_index', 0))  # 1-based, 0 disables
        date_regex = self._get('tracker_date_regex', r'\d{8}')
        date_re = re.compile(date_regex)
        filename_re = re.compile(r'LDC_SMD_([A-Z0-9-]+?)([a-z]+)?_(\d{8})_E2E')
        sid_re = re.compile(r'\.([A-Z0-9]{6,})\.pdf', re.IGNORECASE)
        try:
            row_snapshots = row_snapshots or self._extract_tracker_rows_snapshot()

            for cells in row_snapshots[1:]:
                if not cells:
                    continue
                row_texts = [(cell or '').strip() for cell in cells if (cell or '').strip()]
                row_filename = ''
                row_sid = ''
                for text in row_texts:
                    if not row_filename and filename_re.search(text):
                        row_filename = text
                    if not row_sid:
                        sid_match = sid_re.search(text)
                        if sid_match:
                            row_sid = sid_match.group(1)
                    if row_filename and row_sid:
                        break
                text_parts: List[str] = []
                if len(cells) >= case_col_index:
                    text_parts.append((cells[case_col_index - 1] or '').strip())
                if not text_parts[0:1]:
                    text_parts = [(cell or '').strip() for cell in cells]

                for text in text_parts:
                    if not text:
                        continue
                    file_match = filename_re.search(text)
                    if file_match:
                        case_text = self._strip_filename_variant_suffix(file_match.group(1))
                        date_text = file_match.group(3)
                        case_norm = self._normalize_case_number(case_text)
                        date_norm = self._normalize_date(date_text)
                        if case_norm and date_norm:
                            keys.append((case_norm, date_norm, row_sid, row_filename or text))
                            continue
                    norm = self._normalize_case_number(text)
                    if not norm:
                        continue
                    date_matches = date_re.findall(text)
                    if not date_matches and date_col_index and len(cells) >= date_col_index:
                        date_cell_text = (cells[date_col_index - 1] or '').strip()
                        if date_cell_text:
                            date_matches = date_re.findall(date_cell_text)
                    if date_matches:
                        for date_match in date_matches:
                            keys.append((norm, self._normalize_date(date_match), row_sid, row_filename))
                    else:
                        keys.append((norm, '', row_sid, row_filename))

            return keys
        except Exception as e:
            self._log(f'Error extracting tracker case texts: {str(e)}')
            return []

    def filter_cases(self, cases: List[Dict], start_date: date, end_date: date) -> Tuple[List[Dict], List[Dict]]:
        """Return (filtered_cases, skipped_cases) based on online tracker duplicates."""
        if not cases:
            return [], []

        if not self._get('tracker_enabled', False):
            return cases, []

        max_attempts = max(1, int(self._get('tracker_retry_attempts', 3)))
        failure_message = 'Tracker duplicate check failed'

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                delay = self._get_tracker_retry_delay(attempt)
                self._log(
                    f'Tracker retry {attempt}/{max_attempts}: waiting {delay}s, '
                    f'then refreshing the tracker and trying again'
                )
                if delay > 0:
                    time.sleep(delay)
                self._reset_tracker_state()

            self._log(f'Tracker duplicate check attempt {attempt}/{max_attempts}')

            if not self.navigate_to_tracker():
                failure_message = 'Tracker duplicate check failed: unable to open tracker'
                continue

            if not self.setup_query():
                failure_message = 'Tracker duplicate check failed: unable to set up tracker query'
                continue

            if not self.enter_search_criteria(start_date, end_date):
                failure_message = 'Tracker duplicate check failed: unable to enter tracker search criteria'
                continue

            if not self.wait_for_report():
                failure_message = 'Tracker duplicate check failed: tracker report did not load'
                continue

            break
        else:
            return self._handle_tracker_failure(cases, failure_message)

        row_snapshots = self._extract_tracker_rows_snapshot()
        tracker_keys_raw = self.extract_tracker_case_keys(row_snapshots)
        tracker_text_keys_raw = self.extract_tracker_text_date_keys(row_snapshots)
        tracker_match_with_date = self._get('tracker_match_with_date', True)
        case_regex = self._get('tracker_case_regex', r'\d{2}-\d{4}-[A-Z0-9-]+')
        case_re = re.compile(case_regex, re.IGNORECASE)
        tracker_set = set()
        for case_num, date_text in tracker_keys_raw:
            case_norm = self._normalize_case_number(case_num)
            date_norm = self._normalize_date(date_text)
            if tracker_match_with_date and date_norm:
                tracker_set.add((case_norm, date_norm))
            else:
                tracker_set.add((case_norm, ''))
        tracker_text_map = {}
        for case_norm, date_norm, sid, filename in tracker_text_keys_raw:
            tracker_text_map[(case_norm, date_norm)] = {
                'sid': sid,
                'filename': filename,
            }
        self._log(f'Online tracker cases found: {len(tracker_set)}')

        filtered_cases: List[Dict] = []
        skipped_cases: List[Dict] = []
        for case in cases:
            case_num = case.get('case_number', '')
            case_norm = self._normalize_case_number(case_num)
            case_is_conventional = bool(case_re.search(case_num or ''))
            case_date = case.get('date')
            case_date_str = ''
            try:
                if isinstance(case_date, date):
                    case_date_str = case_date.strftime('%m%d%Y')
            except Exception:
                case_date_str = ''

            key_with_date = (case_norm, case_date_str) if case_norm and case_date_str else None
            key_without_date = (case_norm, '')
            is_duplicate = False
            if key_with_date and key_with_date in tracker_set:
                is_duplicate = True
            elif key_without_date in tracker_set:
                is_duplicate = True
            elif case_norm and case_date_str:
                if (case_norm, case_date_str) in tracker_text_map:
                    is_duplicate = True
                    # This path uses the filename-based tracker map (CSO_SF_FILE),
                    # which strips trailing a/b/c suffixes to catch variant filenames.
                    case['duplicate_reason'] = 'Found in tracker (text+date match via filename)'

            if is_duplicate:
                meta_key = key_with_date or key_without_date
                if meta_key in tracker_text_map:
                    meta = tracker_text_map.get(meta_key, {})
                    if meta.get('sid'):
                        case['tracker_sid'] = meta.get('sid')
                    if meta.get('filename'):
                        case['tracker_filename'] = meta.get('filename')
                    if meta_key:
                        case['tracker_date'] = meta_key[1]
                case['tracker_duplicate'] = True
                if 'duplicate_reason' not in case:
                    case['duplicate_reason'] = 'Found in tracker'
                skipped_cases.append(case)
                reason = case.get('duplicate_reason', 'Found in tracker')
                self._log(f'Skipping {case_num} - {reason.lower()}')
            else:
                filtered_cases.append(case)

        return filtered_cases, skipped_cases

