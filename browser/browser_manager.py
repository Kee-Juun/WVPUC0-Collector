"""
Browser management module for WVPUC0 Document Collector
Handles Chrome driver setup, window management, and page detection
"""
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


class BrowserManager:
    """Manages browser/driver operations including launch, window management, and page detection"""
    
    def __init__(self, log_signal: Callable[[str], None], config: dict, headless: bool = False):
        """
        Initialize browser manager
        
        Args:
            log_signal: Signal/function to emit log messages
            config: Configuration dictionary
            headless: Whether to run browser in headless mode
        """
        self.log_signal = log_signal
        self.config = config
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
    
    def launch_chrome_driver(self, download_dir: Optional[Path] = None) -> Optional[webdriver.Chrome]:
        """Launch Chrome driver with appropriate options"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            if self.headless:
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
            
            if download_dir is None:
                base_download_dir = Path.home() / self.config.get('download_path')
                base_download_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime('%m-%d-%Y_%I-%M-%S-%p')
                run_folder_name = f'WVPUC0_{timestamp}'
                download_dir = base_download_dir / run_folder_name
                download_dir.mkdir(parents=True, exist_ok=True)
            
            prefs = {
                'download.default_directory': str(download_dir),
                'download.prompt_for_download': False,
                'download.directory_upgrade': True,
                'plugins.always_open_pdf_externally': True
            }
            chrome_options.add_experimental_option('prefs', prefs)
            
            # Let Selenium Manager detect the installed Chrome version and
            # provision a compatible ChromeDriver. It also reuses its local
            # cache when the matching driver has already been downloaded.
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script('Object.defineProperty(navigator, \'webdriver\', {get: () => undefined})')
            self.driver = driver
            self.log_signal('Chrome browser launched successfully')
            return driver
        except Exception as e:
            self.log_signal(f'Failed to launch Chrome: {str(e)}')
            return None
    
    def setup_download_preferences(self, download_dir: Path):
        """Setup download preferences for the browser"""
        if self.driver:
            prefs = {
                'download.default_directory': str(download_dir),
                'download.prompt_for_download': False,
                'download.directory_upgrade': True,
                'plugins.always_open_pdf_externally': True
            }
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                'behavior': 'allow',
                'downloadPath': str(download_dir)
            })
    
    def is_orders_by_month_page(self) -> bool:
        """Check if the current page is the OrdersByMonth listing page."""
        if not self.driver:
            return False
        try:
            url = self.driver.current_url.lower()
            title = (self.driver.title or '').lower()
            return 'ordersbymonth.cfm' in url or 'psc orders by month' in title
        except Exception:
            return False
    
    def did_download_start(self, download_dir: Path, initial_pdf_count: int) -> bool:
        """Check if a download likely started (crdownload or new PDF)."""
        try:
            if list(download_dir.glob('*.crdownload')):
                return True
            current_pdf_files = list(download_dir.glob('*.pdf'))
            return len(current_pdf_files) > initial_pdf_count
        except Exception:
            return False
    
    def is_chrome_error_page(self) -> bool:
        """Detect Chrome's built-in error pages (timeouts, DNS, etc.)."""
        if not self.driver:
            return False
        try:
            title = (self.driver.title or '').lower()
            if 'this site can\'t be reached' in title or "this site can't be reached" in title:
                return True
            page = (self.driver.page_source or '').lower()
            return 'err_connection_timed_out' in page or 'err_name_not_resolved' in page
        except Exception:
            return False
    
    def close_extra_window(self, original_handle: str):
        """Close any non-original window and switch back."""
        if not self.driver:
            return
        try:
            # Validate windows exist
            if not self.driver.window_handles:
                return
            
            current_handle = self.driver.current_window_handle
            if current_handle != original_handle and current_handle in self.driver.window_handles:
                # Close current window if it's not the original
                self.driver.close()
            
            # Switch back to original window if it still exists
            if original_handle in self.driver.window_handles:
                self.driver.switch_to.window(original_handle)
            elif self.driver.window_handles:
                # Original window closed, use first available
                self.driver.switch_to.window(self.driver.window_handles[0])
        except Exception as e:
            # Try to recover by switching to any available window
            try:
                if self.driver.window_handles:
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass
    
    def validate_and_recover_window(self, expected_handle: Optional[str] = None) -> str:
        """Validate that a window exists and recover if needed.
        Returns the current valid window handle.
        """
        if not self.driver or not self.driver.window_handles:
            raise Exception("No browser windows available")
        
        if expected_handle and expected_handle in self.driver.window_handles:
            try:
                self.driver.switch_to.window(expected_handle)
                return expected_handle
            except Exception:
                pass
        
        # Fall back to first available window
        if self.driver.window_handles:
            handle = self.driver.window_handles[0]
            self.driver.switch_to.window(handle)
            return handle
        
        raise Exception("Cannot recover: no browser windows available")
    
    def capture_debug_artifacts(self, label: str, download_dir: Path):
        """Save screenshot and HTML for debugging page-specific failures."""
        if not self.driver:
            return
        try:
            debug_dir = download_dir / 'Debug'
            debug_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_label = re.sub(r'[^a-zA-Z0-9_-]', '_', label)[:60]
            screenshot_path = debug_dir / f'{timestamp}_{safe_label}.png'
            html_path = debug_dir / f'{timestamp}_{safe_label}.html'
            self.driver.save_screenshot(str(screenshot_path))
            with html_path.open('w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            self.log_signal(f'Debug saved: {screenshot_path.name}, {html_path.name}')
        except Exception as e:
            self.log_signal(f'Failed to save debug artifacts: {str(e)}')
    
    def quit(self):
        """Quit the browser driver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

