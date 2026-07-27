"""
Fallback logic for months with "No Orders Found" message.
Moves the selector back one month and reloads the results.
"""
from datetime import datetime
from typing import Optional, Callable, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def _log(log_func: Optional[Callable[[str], None]], message: str) -> None:
    if log_func:
        try:
            log_func(message)
        except Exception:
            pass


def _expected_orders_marker(month: Optional[int], year: Optional[int]) -> str:
    """Build the visible heading marker for a target month/year."""
    if not month or not year:
        return ''
    return f'WV PSC Orders Issued - {datetime(year, month, 1):%B, %Y}'.lower()


def _page_matches_target_month_year(driver, month: Optional[int], year: Optional[int]) -> bool:
    """Check whether the page content has updated to the target month/year."""
    marker = _expected_orders_marker(month, year)
    if not marker:
        return True
    try:
        return marker in (driver.page_source or '').lower()
    except Exception:
        return False


def apply_new_month_fallback(
    driver,
    log_func: Optional[Callable[[str], None]] = None,
    target_month: Optional[int] = None,
    target_year: Optional[int] = None,
) -> bool:
    """If 'No Orders Found' is present, select a target month/year or previous month and reload.

    Returns True if a fallback attempt was made, False otherwise.
    """
    try:
        info_nodes = driver.find_elements(By.CSS_SELECTOR, "h2.info")
        if not info_nodes:
            return False
        info_text = " ".join([n.text for n in info_nodes]).lower()
        if "no orders found" not in info_text:
            return False

        _log(log_func, f"No Orders Found detected: {info_text.strip()}")
        if target_month and target_year:
            _log(log_func, f"Applying new-month fallback: selecting {target_month}/{target_year}.")
        else:
            _log(log_func, "Applying new-month fallback: selecting previous month.")

        month_select = Select(driver.find_element(By.ID, "OrderMonth"))
        year_select = Select(driver.find_element(By.ID, "OrderYear"))

        current_month = int(month_select.first_selected_option.get_attribute("value"))
        current_year = int(year_select.first_selected_option.get_attribute("value"))
        _log(log_func, f"Current selection: month={current_month}, year={current_year}")

        if not target_month or not target_year:
            if current_month == 1:
                target_month = 12
                target_year = current_year - 1
            else:
                target_month = current_month - 1
                target_year = current_year

        month_select.select_by_value(str(target_month))
        year_select.select_by_value(str(target_year))
        _log(log_func, f"Fallback selection: month={target_month}, year={target_year}")

        display_btn = driver.find_element(By.ID, "Display")
        display_btn.click()
        _log(log_func, "Clicked Display to reload results.")

        if not wait_for_results_or_no_orders(driver, timeout=10, month=target_month, year=target_year):
            return False
        _log(log_func, f"Fallback loaded: {target_month}/{target_year}")
        return True
    except Exception as exc:
        _log(log_func, f"Fallback failed: {str(exc)}")
        return False


def get_selected_month_year(driver) -> Tuple[Optional[int], Optional[int]]:
    """Return the currently selected month/year values, if available."""
    try:
        month_select = Select(driver.find_element(By.ID, "OrderMonth"))
        year_select = Select(driver.find_element(By.ID, "OrderYear"))
        current_month = int(month_select.first_selected_option.get_attribute("value"))
        current_year = int(year_select.first_selected_option.get_attribute("value"))
        return current_month, current_year
    except Exception:
        return None, None


def apply_month_year_selection(
    driver,
    month: int,
    year: int,
    log_func: Optional[Callable[[str], None]] = None,
    wait_for_rows: bool = True,
) -> bool:
    """Select a month/year and click Display to load results."""
    try:
        month_select = Select(driver.find_element(By.ID, "OrderMonth"))
        year_select = Select(driver.find_element(By.ID, "OrderYear"))
        month_select.select_by_value(str(month))
        year_select.select_by_value(str(year))
        _log(log_func, f"Restoring month/year selection: {month}/{year}")
        display_btn = driver.find_element(By.ID, "Display")
        display_btn.click()
        if wait_for_rows:
            if not wait_for_results_or_no_orders(driver, timeout=10, month=month, year=year):
                return False
        return True
    except Exception as exc:
        _log(log_func, f"Failed to restore month/year selection: {str(exc)}")
        return False


def has_no_orders_message(driver) -> bool:
    """Return True if the page shows a 'No Orders Found' message."""
    try:
        info_nodes = driver.find_elements(By.CSS_SELECTOR, "h2.info")
        if not info_nodes:
            return False
        info_text = " ".join([n.text for n in info_nodes]).lower()
        return "no orders found" in info_text
    except Exception:
        return False


def wait_for_results_or_no_orders(
    driver,
    timeout: int = 10,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> bool:
    """Wait until rows are present or a 'No Orders Found' message appears."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: has_no_orders_message(d) or (
                d.find_elements(By.XPATH, "//table//tbody//tr")
                and _page_matches_target_month_year(d, month, year)
            )
        )
        return True
    except TimeoutException:
        return False

