"""
WVPUC0 Collector - simplified version based on NonCCSAutoCollectors architecture
Uses Selenium to navigate and extract PDF URLs, then requests to download
"""
from __future__ import annotations
import logging
import re
import html as ihtml
from datetime import datetime, timezone, date
from typing import Iterable, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from .base_collector import BaseCollector, DocumentCandidate
from utils.new_month_fallback import (
    apply_month_year_selection,
    get_selected_month_year,
    has_no_orders_message,
    wait_for_results_or_no_orders,
)

logger = logging.getLogger(__name__)


def _parse_mdy(date_text: str) -> Optional[datetime]:
    """Parse MM/DD/YYYY or MM/DD/YY date"""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(date_text.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _month_year_range(start_date: date, end_date: date):
    """Generate month/year pairs for date range"""
    cur = datetime(start_date.year, start_date.month, 1, tzinfo=timezone.utc)
    end = datetime(end_date.year, end_date.month, 1, tzinfo=timezone.utc)
    while cur <= end:
        yield cur.month, cur.year
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)


class WVPUC0Collector(BaseCollector):
    """WVPUC0 collector - extracts case URLs from list, gets PDF URLs, downloads with requests"""
    
    name = "WVPUC0"
    base_url = "https://www.psc.state.wv.us/scripts/orders/OrdersByMonth.cfm"
    
    # Document type patterns
    TYPE_RE = re.compile(
        r"^(?:Recommended Decision|Mediation Final Order|Commission Final Order|"
        r"Interim Recommended Decision|Administrative Law Judge Final Order|"
        r"Commission Order|Commission Corrective Order|Commission Procedural Order|"
        r"Commission Procedure Order)",
        re.IGNORECASE
    )
    
    # Exclusion phrases
    EXCLUDE_PHRASES = [
        "Commission Order Denying Request to Extend Administrative Law Judge Decision Due",
        "Commission Order Extending Administrative Law Judge Decision Due Date",
        "Commission Order extending the ALJ Decision Due Date",
        "Procedural Order",
        "Scheduling Order",
        "Notice of Filing",
        "Commission Order Extending Answer Due Date",
    ]
    
    def __init__(self, config: dict, log_signal=None, start_date: Optional[date] = None, end_date: Optional[date] = None):
        super().__init__(config, log_signal)
        self.start_date = start_date
        self.end_date = end_date
        self.selected_month = None
        self.selected_year = None
    
    def _extract_pdf_url_from_case_page(self, driver: webdriver.Chrome, case_page_url: str) -> Optional[str]:
        """Navigate to case page and extract PDF URL"""
        try:
            driver.get(case_page_url)
            time.sleep(2)  # Wait for page to load
            
            # Look for PDF link
            try:
                pdf_link = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//a[contains(@href, ".pdf")]'))
                )
                pdf_url = pdf_link.get_attribute('href')
                if pdf_url:
                    if pdf_url.startswith('/'):
                        base_url = '/'.join(case_page_url.split('/')[:3])
                        pdf_url = base_url + pdf_url
                    return pdf_url
            except TimeoutException:
                # Try alternative selectors
                try:
                    download_btn = driver.find_element(By.XPATH, '//a[contains(text(), "Download") or contains(text(), "PDF")]')
                    pdf_url = download_btn.get_attribute('href')
                    if pdf_url:
                        if pdf_url.startswith('/'):
                            base_url = '/'.join(case_page_url.split('/')[:3])
                            pdf_url = base_url + pdf_url
                        return pdf_url
                except NoSuchElementException:
                    pass
            
            return None
        except Exception as e:
            self.log_signal(f'Error extracting PDF URL from {case_page_url}: {str(e)}')
            return None

    def _extract_month_result_rows(self, driver: webdriver.Chrome) -> list[dict[str, str]]:
        """
        Snapshot the current WVPSC month-results table into plain data.

        This uses one JavaScript DOM pass for speed and to avoid stale Selenium
        row elements once we start navigating into individual case pages.
        """
        try:
            row_payloads = driver.execute_script(
                """
                const rows = Array.from(document.querySelectorAll('table tbody tr'));
                return rows
                    .map((row) => {
                        if (row.querySelectorAll('th').length) {
                            return null;
                        }

                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length < 4) {
                            return null;
                        }

                        const textOf = (index) => ((cells[index]?.textContent) || '').trim();
                        const link = cells[1].querySelector('a[href]');

                        return {
                            date_text: textOf(0),
                            docket_text: textOf(1),
                            case_name: textOf(2),
                            raw_meta: textOf(3),
                            case_page_url: link ? (link.href || '') : '',
                        };
                    })
                    .filter(Boolean);
                """
            )

            if isinstance(row_payloads, list):
                return row_payloads

        except Exception as e:
            self.log_signal(
                f'JavaScript month-row extraction failed; falling back to Selenium reads: {str(e)}'
            )

        row_payloads: list[dict[str, str]] = []
        rows = driver.find_elements(By.XPATH, '//table//tbody//tr')
        for row in rows:
            try:
                if row.find_elements(By.TAG_NAME, 'th'):
                    continue

                cols = row.find_elements(By.XPATH, './td')
                if len(cols) < 4:
                    continue

                link_elems = cols[1].find_elements(By.XPATH, './/a[@href]')
                case_page_url = link_elems[0].get_attribute("href") if link_elems else ""

                row_payloads.append({
                    "date_text": (cols[0].text or "").strip(),
                    "docket_text": (cols[1].text or "").strip(),
                    "case_name": (cols[2].text or "").strip(),
                    "raw_meta": (cols[3].text or "").strip(),
                    "case_page_url": case_page_url or "",
                })
            except StaleElementReferenceException:
                continue

        return row_payloads
    
    def search(self, driver: webdriver.Chrome, start_date: Optional[datetime], end_date: Optional[datetime]) -> Iterable[DocumentCandidate]:
        """Search for cases and yield DocumentCandidate objects"""
        # Convert dates
        if isinstance(start_date, datetime):
            start_date_obj = start_date.date()
        elif isinstance(start_date, date):
            start_date_obj = start_date
        else:
            start_date_obj = self.start_date
        
        if isinstance(end_date, datetime):
            end_date_obj = end_date.date()
        elif isinstance(end_date, date):
            end_date_obj = end_date
        else:
            end_date_obj = self.end_date
        
        if not start_date_obj or not end_date_obj:
            return
        
        try:
            driver.get(self.base_url)
            time.sleep(2)
            
            total_rows = kept = skipped_type = skipped_date = 0
            
            for target_month, target_year in _month_year_range(start_date_obj, end_date_obj):
                tries = 0
                while True:
                    tries += 1
                    try:
                        # Select month/year
                        apply_month_year_selection(driver, target_month, target_year, self.log_signal)
                        self.log_signal(f'Selected month={target_month} year={target_year}')
                        
                        # Wait for results
                        wait_for_results_or_no_orders(
                            driver,
                            timeout=10,
                            month=target_month,
                            year=target_year,
                        )
                        
                        if has_no_orders_message(driver):
                            self.log_signal(f'No results for {target_month}/{target_year}')
                            break
                        
                        # Snapshot table rows before we navigate into case pages.
                        row_payloads = self._extract_month_result_rows(driver)
                        if not row_payloads:
                            self.log_signal(f'No rows found for {target_month}/{target_year}')
                            break

                        self.log_signal(f'Found {len(row_payloads)} rows for {target_month}/{target_year}')
                        total_rows += len(row_payloads)
                        
                        # Process each row
                        for row_data in row_payloads:
                            try:
                                # Extract data
                                date_text = (row_data.get("date_text") or "").strip()
                                docket_text = ihtml.unescape((row_data.get("docket_text") or "").strip())
                                case_name = ihtml.unescape((row_data.get("case_name") or "").strip())
                                raw_meta = ihtml.unescape((row_data.get("raw_meta") or "").strip())
                                
                                # Parse date
                                decided_dt = _parse_mdy(date_text)
                                if not decided_dt:
                                    continue
                                
                                # Date filter
                                if start_date_obj and decided_dt.date() < start_date_obj:
                                    skipped_date += 1
                                    continue
                                if end_date_obj and decided_dt.date() > end_date_obj:
                                    skipped_date += 1
                                    continue
                                
                                # Type filter
                                if not self.TYPE_RE.match(raw_meta or ""):
                                    skipped_type += 1
                                    continue
                                
                                # Exclude phrases
                                if any(phrase.lower() in (raw_meta or "").lower() for phrase in self.EXCLUDE_PHRASES):
                                    skipped_type += 1
                                    continue
                                
                                # Get case page URL
                                case_page_url = ihtml.unescape((row_data.get("case_page_url") or "").strip())
                                if not case_page_url:
                                    continue
                                
                                # Make absolute
                                if case_page_url.startswith('/'):
                                    base_url = '/'.join(self.base_url.split('/')[:3])
                                    case_page_url = base_url + case_page_url
                                
                                # Extract PDF URL from case page
                                pdf_url = self._extract_pdf_url_from_case_page(driver, case_page_url)
                                if not pdf_url:
                                    self.log_signal(f'Could not find PDF URL for {docket_text}')
                                    continue
                                
                                # Generate filename
                                mmddyyyy = decided_dt.strftime("%m%d%Y")
                                title = f"LDC_SMD_{docket_text}_{mmddyyyy}_E2E"
                                
                                self.log_signal(f'KEEP date={decided_dt.date().isoformat()} docket={docket_text} url={pdf_url}')
                                kept += 1
                                
                                yield DocumentCandidate(
                                    url=pdf_url,
                                    title=title,
                                    published_at=decided_dt,
                                    referrer=case_page_url,
                                    ext=".pdf",
                                    case_number=docket_text
                                )
                                
                            except StaleElementReferenceException:
                                continue
                            except Exception as e:
                                self.log_signal(f'Error processing row: {str(e)}')
                                continue
                        
                        break
                    except StaleElementReferenceException:
                        if tries <= 2:
                            self.log_signal(f'Stale element; retrying {target_month}/{target_year} (attempt {tries})')
                            continue
                        else:
                            self.log_signal(f'Giving up on {target_month}/{target_year} due to staleness')
                            break
                    except Exception as e:
                        self.log_signal(f'Error processing {target_month}/{target_year}: {str(e)}')
                        break
            
            self.log_signal(f'Summary: kept={kept} skipped_by_type={skipped_type} skipped_by_date={skipped_date} total_rows={total_rows}')
        
        except Exception as e:
            self.log_signal(f'Search failed: {str(e)}')
            logger.exception(f'Search failed: {str(e)}')

