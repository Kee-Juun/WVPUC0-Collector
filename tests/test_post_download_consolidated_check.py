"""
Post-download consolidated case checker
Checks downloaded PDFs for consolidated cases and verifies if they should be kept or deleted
"""
import PyPDF2
import re
import json
from pathlib import Path
from typing import List, Tuple, Optional
import sys


class ConsolidatedCaseChecker:
    """Checks for consolidated cases and determines if files should be deleted"""
    
    def __init__(self, config_path: Optional[Path] = None, dry_run: bool = True):
        """
        Initialize checker
        
        Args:
            config_path: Path to config.json (defaults to config.json in script directory)
            dry_run: If True, only report what would be done without deleting files
        """
        if config_path is None:
            config_path = Path(__file__).parent / 'config.json'
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.dry_run = dry_run
        self.sf_view_path = self._get_sf_view_path()
    
    def _get_sf_view_path(self) -> Optional[Path]:
        """Get SF-View path from config"""
        sf_view_url = self.config.get('sf_view_url', '')
        if not sf_view_url:
            return None
        
        # Handle file:// URLs - convert to UNC format for Windows network paths
        if sf_view_url.startswith('file://'):
            # Remove file:// prefix
            path_str = sf_view_url.replace('file://', '')
            # Convert forward slashes to backslashes for Windows
            path_str = path_str.replace('/', '\\')
            # If it's a network path (no drive letter), ensure it starts with \\
            if not path_str.startswith('\\\\') and '\\' in path_str and not path_str[1:2] == ':':
                # Network path without \\ prefix - add it
                path_str = '\\\\' + path_str.lstrip('\\')
            path = Path(path_str)
        else:
            path = Path(sf_view_url)
        
        # Try to access the path
        try:
            if path.exists():
                return path
            else:
                print(f"[WARNING] SF-View path does not exist: {path}")
                print(f"          Attempted path: {path}")
                return None
        except Exception as e:
            print(f"[WARNING] Cannot access SF-View path: {path}")
            print(f"          Error: {str(e)}")
            return None
    
    def extract_case_from_filename(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract case number and date from filename
        
        Returns:
            (case_number, date) or (None, None) if parsing fails
        """
        # Format: LDC_SMD_{case_number}_{date}_E2E.pdf
        pattern = r'LDC_SMD_(\d{2}-\d{4}-[A-Z0-9-]+)_(\d{8})_E2E\.pdf'
        match = re.match(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    def extract_top_case_numbers(self, pdf_path: Path, top_chars: int = 2000) -> List[str]:
        """
        Extract case numbers from the top section of a PDF
        
        Args:
            pdf_path: Path to PDF file
            top_chars: Number of characters from start to analyze (default: 2000)
        
        Returns:
            List of case numbers found in top section
        """
        try:
            # Add timeout protection - limit to first page only
            reader = PyPDF2.PdfReader(str(pdf_path))
            if len(reader.pages) == 0:
                return []
            
            # Extract text from first page only (to avoid hanging on large PDFs)
            try:
                first_page_text = reader.pages[0].extract_text()
            except Exception as e:
                # If extraction fails, return empty
                return []
            
            top_section = first_page_text[:top_chars]
            
            # Find all case numbers in format: XX-XXXX-XXX
            case_pattern = r'\b\d{2}-\d{4}-[A-Z0-9-]+\b'
            cases = re.findall(case_pattern, top_section, re.IGNORECASE)
            
            # Return unique cases (preserving case)
            seen = set()
            unique_cases = []
            for case in cases:
                case_upper = case.upper()
                if case_upper not in seen:
                    seen.add(case_upper)
                    unique_cases.append(case)
            
            return unique_cases
        except Exception as e:
            # Silently return empty list on error (error will be logged in check_pdf)
            return []
    
    def check_case_in_sfview(self, case_number: str, date_str: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a case exists in SF-View
        
        Args:
            case_number: Case number to check (e.g., "25-0429-PWD-C")
            date_str: Date string in format MMDDYYYY (e.g., "02112026")
        
        Returns:
            (exists, filename_if_found) tuple
        """
        if not self.sf_view_path:
            return False, None
        
        try:
            # Construct expected filename
            expected_filename = f"LDC_SMD_{case_number}_{date_str}_E2E.pdf"
            
            # Check various patterns (try exact match first for speed)
            patterns = [
                expected_filename,  # Exact match
                f'LDC_SMD_{case_number}_*.pdf',  # Same case, any date
                f'*{case_number}*.pdf',  # Any file with case number
            ]
            
            for pattern in patterns:
                try:
                    matching_files = list(self.sf_view_path.glob(pattern))
                    if matching_files:
                        return True, matching_files[0].name
                except Exception:
                    # If glob fails (network issue), continue to next pattern
                    continue
            
            return False, None
        except Exception as e:
            # If SF-View check fails, assume not found
            return False, None
    
    def check_pdf(self, pdf_path: Path) -> dict:
        """
        Check a single PDF file for consolidated cases
        
        Returns:
            Dictionary with check results
        """
        result = {
            'file': pdf_path.name,
            'file_path': str(pdf_path),
            'filename_case': None,
            'filename_date': None,
            'top_cases': [],
            'other_cases': [],
            'is_consolidated': False,
            'sf_view_checks': {},
            'should_delete': False,
            'delete_reason': None,
            'error': None
        }
        
        try:
            # Extract case number and date from filename
            filename_case, filename_date = self.extract_case_from_filename(pdf_path.name)
            if not filename_case or not filename_date:
                result['error'] = f"Could not parse filename: {pdf_path.name}"
                return result
            
            result['filename_case'] = filename_case
            result['filename_date'] = filename_date
            
            # Extract case numbers from top of document
            top_cases = self.extract_top_case_numbers(pdf_path)
            result['top_cases'] = top_cases
            
            # Find other cases (excluding filename case)
            other_cases = [
                case for case in top_cases 
                if case.upper() != filename_case.upper()
            ]
            result['other_cases'] = other_cases
            result['is_consolidated'] = len(other_cases) > 0
            
            # If consolidated, check SF-View for other cases
            if result['is_consolidated']:
                for other_case in other_cases:
                    exists, found_filename = self.check_case_in_sfview(other_case, filename_date)
                    result['sf_view_checks'][other_case] = {
                        'exists': exists,
                        'filename': found_filename
                    }
                    
                    # If any other case exists in SF-View, we should delete this file
                    if exists:
                        result['should_delete'] = True
                        result['delete_reason'] = (
                            f"Case {other_case} already exists in SF-View as {found_filename}"
                        )
                        break  # Only need one match to delete
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def process_directory(self, directory: Path) -> List[dict]:
        """
        Process all PDF files in a directory
        
        Args:
            directory: Directory containing PDF files
        
        Returns:
            List of check results
        """
        pdf_files = list(directory.glob('*.pdf'))
        results = []
        
        print(f"Processing {len(pdf_files)} PDF file(s) in {directory}...\n")
        
        for idx, pdf_file in enumerate(sorted(pdf_files), 1):
            print(f"[{idx}/{len(pdf_files)}] Processing: {pdf_file.name}...", end=' ', flush=True)
            try:
                result = self.check_pdf(pdf_file)
                results.append(result)
                print("Done")
                
                # Print summary (only for consolidated cases or errors)
                if result['is_consolidated'] or result['error']:
                    self._print_result(result)
            except Exception as e:
                print(f"ERROR: {str(e)}")
                result = {
                    'file': pdf_file.name,
                    'error': str(e),
                    'is_consolidated': False,
                    'should_delete': False
                }
                results.append(result)
        
        return results
    
    def _print_result(self, result: dict):
        """Print formatted result"""
        print("="*80)
        print(f"File: {result['file']}")
        print(f"Filename case: {result['filename_case']}")
        
        if result['error']:
            print(f"ERROR: {result['error']}")
            return
        
        if result['is_consolidated']:
            print(f"[!] CONSOLIDATED CASE DETECTED")
            print(f"    Top cases found: {', '.join(result['top_cases'])}")
            print(f"    Other cases: {', '.join(result['other_cases'])}")
            
            print(f"\n    SF-View checks:")
            for case, check in result['sf_view_checks'].items():
                status = f"FOUND: {check['filename']}" if check['exists'] else "NOT FOUND"
                print(f"      - {case}: {status}")
            
            if result['should_delete']:
                print(f"\n    [DELETE] {result['delete_reason']}")
                if self.dry_run:
                    print(f"    (DRY RUN - file would be deleted)")
                else:
                    try:
                        Path(result['file_path']).unlink()
                        print(f"    [DELETED] File removed successfully")
                    except Exception as e:
                        print(f"    [ERROR] Failed to delete: {str(e)}")
            else:
                print(f"\n    [KEEP] No other cases found in SF-View")
        else:
            print(f"[OK] Single case document (not consolidated)")
        
        print()
    
    def print_summary(self, results: List[dict]):
        """Print summary of all results"""
        total = len(results)
        consolidated = sum(1 for r in results if r['is_consolidated'])
        to_delete = sum(1 for r in results if r['should_delete'])
        errors = sum(1 for r in results if r['error'])
        
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total files processed: {total}")
        print(f"Consolidated cases found: {consolidated}")
        print(f"Files to delete: {to_delete}")
        print(f"Errors: {errors}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE (files will be deleted)'}")
        print("="*80)


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check downloaded PDFs for consolidated cases and verify SF-View duplicates'
    )
    parser.add_argument(
        'path',
        type=str,
        help='Path to PDF file or directory containing PDFs'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config.json (defaults to config.json in script directory)'
    )
    parser.add_argument(
        '--live',
        action='store_true',
        help='Actually delete files (default is dry-run mode)'
    )
    
    args = parser.parse_args()
    
    # Initialize checker
    config_path = Path(args.config) if args.config else None
    checker = ConsolidatedCaseChecker(config_path=config_path, dry_run=not args.live)
    
    # Process path
    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: Path does not exist: {path}")
        sys.exit(1)
    
    if path.is_file():
        # Single file
        result = checker.check_pdf(path)
        checker._print_result(result)
        checker.print_summary([result])
    elif path.is_dir():
        # Directory
        results = checker.process_directory(path)
        checker.print_summary(results)
    else:
        print(f"ERROR: Path is not a file or directory: {path}")
        sys.exit(1)


if __name__ == '__main__':
    main()

