"""
Reporting module for WVPUC0 Document Collector
Handles summary logging and reporting
"""
from typing import Callable, Optional


class Reporter:
    """Handles summary reporting and logging"""
    
    def __init__(self, log_signal: Callable[[str], None]):
        """
        Initialize reporter
        
        Args:
            log_signal: Signal/function to emit log messages
        """
        self.log_signal = log_signal
    
    def log_summary(
        self, 
        includes_count: int, 
        duplicates_count: int, 
        errors_count: int,
        last_duplicate_filename: Optional[str] = None,
        last_duplicate_sid: Optional[str] = None,
        last_duplicate_date: Optional[str] = None
    ) -> None:
        """Log a summary report for the run."""
        try:
            self.log_signal('--------------DONE--------------')
            self.log_signal(f'Includes: {includes_count}')
            self.log_signal(f'Duplicates: {duplicates_count}')
            self.log_signal(f'Errors: {errors_count}')
            if last_duplicate_filename or last_duplicate_sid or last_duplicate_date:
                filename_display = last_duplicate_filename or 'N/A'
                if last_duplicate_sid and last_duplicate_sid in filename_display:
                    filename_display = filename_display.replace(f'.{last_duplicate_sid}.pdf', '.pdf')
                    filename_display = filename_display.replace(f'.{last_duplicate_sid}', '')
                if filename_display.lower().endswith('.pdf.pdf'):
                    filename_display = filename_display[:-4]
                self.log_signal(f'Last Collected Filename: {filename_display}')
                self.log_signal(f'Last Collected SID: {last_duplicate_sid or "N/A"}')
                self.log_signal(f'Last Collected Date: {last_duplicate_date or "N/A"}')
            self.log_signal('--------------DONE--------------')
        except Exception:
            pass

