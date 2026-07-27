"""
SF-View checker module for WVPUC0 Document Collector
Checks if cases already exist in SF-View directory
"""
from pathlib import Path
from typing import Dict, Callable


class SFViewChecker:
    """Checks if case numbers exist in SF-View directory"""
    
    def __init__(self, log_signal: Callable[[str], None], config: Dict):
        """
        Initialize SF-View checker
        
        Args:
            log_signal: Signal/function to emit log messages
            config: Configuration dictionary
        """
        self.log_signal = log_signal
        self.config = config
    
    def check_case_exists_in_sfview(self, case_number: str) -> bool:
        """Check if case number exists in SF-View directory by looking for existing files"""
        try:
            sf_view_url = self.config.get('sf_view_url')
            if sf_view_url.startswith('file://'):
                sf_view_path = Path(sf_view_url.replace('file://', ''))
            else:
                sf_view_path = Path(sf_view_url)
            
            if not sf_view_path.exists():
                return False
            
            clean_case_number = case_number.replace(' ', '')
            possible_patterns = [
                f'*{clean_case_number}*.pdf',
                f'*{case_number}*.pdf',
                f'LDC_SMD_{clean_case_number}_*.pdf',
                f'LDC_SMD_{case_number}_*.pdf'
            ]
            
            for pattern in possible_patterns:
                matching_files = list(sf_view_path.glob(pattern))
                if matching_files:
                    self.log_signal(f'Found existing file for case {case_number} in SF-View: {matching_files[0].name}')
                    return True
            
            # Fallback: check all PDF files
            try:
                all_pdf_files = list(sf_view_path.glob('*.pdf'))
                for pdf_file in all_pdf_files:
                    if clean_case_number in pdf_file.name or case_number in pdf_file.name:
                        self.log_signal(f'Found existing file for case {case_number} in SF-View: {pdf_file.name}')
                        return True
            except Exception as e:
                self.log_signal(f'Error checking existing files: {str(e)}')
            
            self.log_signal(f'Case {case_number} not found in SF-View - proceeding with download')
            return False
        except Exception as e:
            self.log_signal(f'SF-View check failed: {str(e)} - proceeding with download')
            return False

