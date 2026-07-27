"""
Consolidated case checker module
Checks downloaded PDFs for consolidated cases and deletes files if other members exist in SF-View
"""
import PyPDF2
import hashlib
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
from datetime import date, datetime, timedelta
import time
import threading

from utils.pdf_text_extractor import extract_pdf_text


class ConsolidatedCaseChecker:
    """Checks for consolidated cases and determines if files should be deleted"""
    
    def __init__(self, config: Dict, log_signal: Callable[[str], None]):
        """
        Initialize checker
        
        Args:
            config: Configuration dictionary
            log_signal: Function to emit log messages
        """
        self.config = config
        self.log_signal = log_signal
        self.sf_view_path = self._get_sf_view_path()
        # Per-run caches to avoid repeated SF-View checks and group decisions
        # Maps CASE_NUMBER (uppercased) -> (exists_in_sfview: Optional[bool], filename: Optional[str])
        # exists_in_sfview values:
        #   True  -> found in SF-View
        #   False -> confirmed not found
        # Uncertain results (None) are not cached, so a later lookup can retry.
        self._sfview_case_cache: Dict[str, Tuple[Optional[bool], Optional[str]]] = {}
        self._pdf_hash_cache: Dict[str, Optional[str]] = {}
        # Maps group key (tuple of uppercased case numbers in group) -> decision dict
        # Decision dict example:
        #   {'mode': 'sfview_covered', 'delete_reason': str, 'sf_member_case': str, 'sf_member_filename': str}
        #   {'mode': 'local_keep_lowest', 'keep_case': str}
        #   {'mode': 'sfview_unknown_local_dedupe', 'keep_case': str, 'identical_cases': tuple}
        self._group_decisions: Dict[Tuple[str, ...], Dict] = {}
        self.consolidated_cases_log = []  # Track all consolidated cases for reporting
    
    def _get_sf_view_path(self) -> Optional[Path]:
        """Get SF-View path from config"""
        sf_view_url = self.config.get('sf_view_url', '')
        if not sf_view_url:
            return None
        
        # Handle file:// URLs - convert to UNC format for Windows network paths
        if sf_view_url.startswith('file://'):
            path_str = sf_view_url.replace('file://', '')
            path_str = path_str.replace('/', '\\')
            # If it's a network path, ensure it starts with \\
            if not path_str.startswith('\\\\') and '\\' in path_str and not path_str[1:2] == ':':
                path_str = '\\\\' + path_str.lstrip('\\')
            path = Path(path_str)
        else:
            path = Path(sf_view_url)
        
        try:
            if path.exists():
                return path
            else:
                self.log_signal(f'[WARNING] SF-View path does not exist: {path}')
                return None
        except Exception as e:
            self.log_signal(f'[WARNING] Cannot access SF-View path: {str(e)}')
            return None
    
    def extract_case_from_filename(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract case number and date from filename"""
        pattern = r'LDC_SMD_([A-Z0-9-]+?)([a-z]+)?_(\d{8})_E2E\.pdf'
        match = re.match(pattern, filename)
        if match:
            return match.group(1), match.group(3)
        return None, None

    def _format_case_date(self, case_date) -> Optional[str]:
        """Format a case date as MMDDYYYY when available."""
        if isinstance(case_date, date):
            return case_date.strftime('%m%d%Y')
        if hasattr(case_date, 'strftime'):
            return case_date.strftime('%m%d%Y')
        if isinstance(case_date, str):
            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m%d%Y']:
                try:
                    return datetime.strptime(case_date, fmt).strftime('%m%d%Y')
                except Exception:
                    continue
        return None

    def _normalize_case_number(self, case_number: str) -> str:
        """
        Normalize a case number by removing spaces and converting to uppercase.
        
        This handles cases where PDF text has spaces like "26-0310-C  -C"
        which should match "26-0310-C-C" in filenames.
        """
        if not case_number:
            return ""
        # Remove all spaces and convert to uppercase
        return case_number.replace(" ", "").upper()

    @staticmethod
    def _normalize_pdf_line(line: str) -> str:
        """Collapse PDF-extracted spacing for stable delimiter detection."""
        return re.sub(r'\s+', ' ', (line or '')).strip()

    def _is_caption_delimiter(self, line: str) -> bool:
        """Return True when a line looks like the start of the order body/title."""
        normalized = self._normalize_pdf_line(line)
        if not normalized:
            return False

        delimiter_patterns = [
            re.compile(r'\bCORRECTIVE\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bCOMMISSION\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bRECOMMENDED\s+DECISION\b', re.IGNORECASE),
            re.compile(r'\bRECOMMENDED\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bCOMMISSION\s+PROCEDURAL\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bCOMMISSION\s+PROCEDURE\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bCOMMISSION\s+FINAL\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bMEDIATION\s+FINAL\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bMEDIATION\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bADMINISTRATIVE\s+LAW\s+JUDGE\s+FINAL\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bINTERIM\s+RECOMMENDED\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bINTERIM\s+RECOMMENDED\s+DECISION\b', re.IGNORECASE),
            re.compile(r'\bINTERIM\s+DECISION\b', re.IGNORECASE),
            re.compile(r'\bPROCEEDING\s+UPON\s+MOTION\b', re.IGNORECASE),
            re.compile(r'\bPROCEEDING\s+ORDER\b', re.IGNORECASE),
            re.compile(r'\bINVESTIGATION\s+OF\b', re.IGNORECASE),
            re.compile(r'\bORDER\b', re.IGNORECASE),
        ]
        if any(pattern.search(normalized) for pattern in delimiter_patterns):
            return True

        letters = [ch for ch in normalized if ch.isalpha()]
        if not letters:
            return False
        uppercase_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
        return uppercase_ratio >= 0.6 and len(normalized) <= 80 and bool(
            re.search(r'\b(ORDER|DECISION)\b', normalized, re.IGNORECASE)
        )

    def _extract_caption_text(self, page_text: str) -> str:
        """Return only the caption block from page 1, stopping at the title/header."""
        if not page_text:
            return ''

        raw_lines = [line for line in page_text.splitlines() if line and line.strip()]
        if not raw_lines:
            return ''

        caption_lines: List[str] = []
        for line in raw_lines[:80]:
            if self._is_caption_delimiter(line):
                break
            caption_lines.append(line)

        caption_text = '\n'.join(caption_lines)
        # Rejoin case numbers split across line breaks, e.g. "25-0366-LRR-W-\nC".
        while True:
            collapsed = re.sub(r'([A-Z0-9])-\s*\n\s*([A-Z0-9])', r'\1-\2', caption_text, flags=re.IGNORECASE)
            if collapsed == caption_text:
                break
            caption_text = collapsed
        caption_text = re.sub(r'(?<=\w)\s*-\s*(?=\w)', '-', caption_text)
        return caption_text
    
    def _make_group_key(self, cases: List[str]) -> Tuple[str, ...]:
        """Create a normalized key for a consolidated group from a list of case numbers."""
        return tuple(sorted({self._normalize_case_number(c) for c in cases if c}))

    def _get_lowest_case(self, cases: List[str]) -> Optional[str]:
        """Return the lexicographically lowest docket number from the list (case-insensitive)."""
        normalized = [c for c in cases if c]
        if not normalized:
            return None
        # Docket numbers are zero-padded (e.g. 26-0138-...), so string sort is fine
        return sorted(normalized, key=lambda x: x.upper())[0]

    def _get_pdf_sha256(self, pdf_path: Path) -> Optional[str]:
        """Return a cached SHA-256 digest for a local PDF."""
        cache_key = str(pdf_path.resolve())
        if cache_key in self._pdf_hash_cache:
            return self._pdf_hash_cache[cache_key]

        try:
            digest = hashlib.sha256()
            with pdf_path.open('rb') as pdf_file:
                for chunk in iter(lambda: pdf_file.read(1024 * 1024), b''):
                    digest.update(chunk)
            result = digest.hexdigest()
        except Exception as e:
            self.log_signal(f'[WARNING] Could not fingerprint {pdf_path.name}: {str(e)}')
            result = None

        self._pdf_hash_cache[cache_key] = result
        return result

    def _find_identical_local_cases(
        self,
        reference_path: Path,
        group_key: Tuple[str, ...],
        download_dir: Path,
        downloaded_files: List[Dict],
    ) -> List[str]:
        """Find members of a consolidated group with byte-identical local PDFs."""
        reference_hash = self._get_pdf_sha256(reference_path)
        if not reference_hash:
            return []

        identical_cases = set()
        for candidate in downloaded_files:
            candidate_filename = candidate.get('saved_filename') or self._generate_filename(candidate)
            candidate_path = Path(candidate.get('saved_path')) if candidate.get('saved_path') else download_dir / candidate_filename
            parsed_case, _ = self.extract_case_from_filename(candidate_filename)
            candidate_case = self._normalize_case_number(candidate.get('case_number') or parsed_case)
            if candidate_case not in group_key or not candidate_path.exists():
                continue
            if self._get_pdf_sha256(candidate_path) == reference_hash:
                identical_cases.add(candidate_case)

        return sorted(identical_cases)
    
    def extract_top_case_numbers(self, pdf_path: Path, max_pages: int = 10) -> List[str]:
        """
        Extract case numbers from the caption / consolidated list at the start of a PDF.

        Safe strategy:
        - Read only the first page
        - Scan only the caption block before the title/order heading
        - Ignore all case-number mentions in the order body
        """
        try:
            reader = PyPDF2.PdfReader(str(pdf_path))
            if len(reader.pages) == 0:
                return []

            # Require at least two trailing docket segments after the year to avoid
            # partial matches like "25-0366-LRR-W" from wrapped body text.
            case_pattern = re.compile(r'\b\d{2}-\d{4}(?:-[A-Z0-9]+){2,}\b', re.IGNORECASE)

            seen: set[str] = set()
            unique_cases: List[str] = []
            page_text = extract_pdf_text(
                pdf_path,
                1,
                use_ocr=bool(self.config.get('ocr_enabled', True)),
                min_native_chars=int(self.config.get('ocr_min_native_chars', 50)),
                language=str(self.config.get('ocr_language', 'eng')),
                dpi=int(self.config.get('ocr_dpi', 250)),
                timeout_seconds=int(self.config.get('ocr_page_timeout_seconds', 30)),
                log=self.log_signal,
            )

            caption_text = self._extract_caption_text(page_text)
            for case in case_pattern.findall(caption_text):
                case_upper = case.upper()
                if case_upper not in seen:
                    seen.add(case_upper)
                    unique_cases.append(case)

            return unique_cases
        except Exception:
            return []
    
    def check_case_in_sfview(self, case_number: str, date_str: str) -> Tuple[Optional[bool], Optional[str]]:
        """
        Check if a case exists in SF-View using targeted glob patterns, with caching.

        This uses targeted glob searches for specific case numbers instead of
        scanning all files. Much faster for large directories (e.g., 21k+ files).
        Results are cached per run so each case number is only checked once.
        """
        if not self.sf_view_path:
            return False, None

        key = (case_number or "").upper()
        if key in self._sfview_case_cache:
            return self._sfview_case_cache[key]

        retry_attempts = max(1, int(self.config.get('consolidated_sfview_retry_attempts', 2)))
        result: Tuple[Optional[bool], Optional[str]] = (None, None)
        for attempt in range(1, retry_attempts + 1):
            result = self._check_case_in_sfview_with_glob(case_number, date_str)
            if result[0] is not None:
                self._sfview_case_cache[key] = result
                return result
            if attempt < retry_attempts:
                self.log_signal(
                    f'Retrying SF-View check for {case_number} '
                    f'(attempt {attempt + 1}/{retry_attempts})...'
                )

        # An uncertain result is deliberately not cached. A later lookup may
        # succeed after a transient network-share delay.
        return result
    
    def _check_case_in_sfview_with_glob(self, case_number: str, date_str: str) -> Tuple[Optional[bool], Optional[str]]:
        """
        Check if a case exists in SF-View using targeted glob patterns with timeout protection.
        
        This method uses glob patterns to search for specific case numbers, which is
        much faster than scanning all files. For a directory with 21k+ files, this
        typically takes seconds instead of minutes.
        """
        if not self.sf_view_path:
            return None, None
            
        try:
            # Build expected filename and patterns (most specific first for speed)
            expected_filename = f"LDC_SMD_{case_number}_{date_str}_E2E.pdf"
            patterns = [
                expected_filename,  # Exact match - fastest if it exists
                f'LDC_SMD_{case_number}_*.pdf',  # Same case, any date
                f'*{case_number}*.pdf',  # Any file with case number (broadest)
            ]
            
            result = [None]  # Use list to allow modification from nested function
            check_complete = threading.Event()
            check_error = [None]
            
            def _check_thread():
                """Perform glob check in a separate thread with timeout protection"""
                try:
                    for pattern in patterns:
                        try:
                            # Glob pattern search - only matches files matching the pattern
                            # This is much faster than scanning all files
                            matching_files = list(self.sf_view_path.glob(pattern))
                            if matching_files:
                                # Found a match - return the first one
                                result[0] = (True, matching_files[0].name)
                                check_complete.set()
                                return
                        except Exception as e:
                            # If one pattern fails, try the next
                            check_error[0] = e
                            continue
                    
                    # No matches found
                    result[0] = (False, None)
                    check_complete.set()
                except Exception as e:
                    check_error[0] = e
                    result[0] = (False, None)
                    check_complete.set()
            
            # Start check in a thread
            thread = threading.Thread(target=_check_thread, daemon=True)
            thread.start()
            
            # Wait up to 10 seconds for the check (glob should be fast, but network can be slow)
            timeout_seconds = max(1, int(self.config.get('consolidated_sfview_timeout_seconds', 15)))
            if check_complete.wait(timeout=timeout_seconds):
                if check_error[0]:
                    self.log_signal(f'[WARNING] Error checking SF-View for {case_number}: {str(check_error[0])}')
                return result[0]
            else:
                # Timeout - network path is too slow or unavailable
                self.log_signal(f'[WARNING] SF-View check for {case_number} timed out after {timeout_seconds} seconds')
                return None, None
                
        except Exception as e:
            self.log_signal(f'[WARNING] Error in SF-View glob check for {case_number}: {str(e)}')
            return None, None
    
    def check_and_delete_consolidated_cases(self, download_dir: Path, downloaded_files: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Check all downloaded files for consolidated cases and delete if needed
        
        Args:
            download_dir: Directory containing downloaded PDFs
            downloaded_files: List of downloaded case dictionaries
        
        Returns:
            (remaining_downloaded_files, deleted_cases_info) tuple
        """
        total_files = len(downloaded_files)
        if total_files == 0:
            self.log_signal('Consolidated case check skipped (no downloaded files)')
            return [], []

        self.log_signal(f'Starting consolidated case check for {total_files} downloaded file(s)...')
        remaining_files = []
        deleted_cases = []
        
        for idx, case in enumerate(downloaded_files, start=1):
            case_number = case.get('case_number', '')
            # Progress/status message so the UI clearly shows activity
            # Example: "Checking consolidated case 3/10: 25-0429-PWD-C"
            self.log_signal(f'Checking consolidated case {idx}/{total_files}: {case_number or "UNKNOWN"}')

            filename = case.get('saved_filename') or self._generate_filename(case)
            saved_path = case.get('saved_path')
            pdf_path = Path(saved_path) if saved_path else download_dir / filename
            
            if not pdf_path.exists():
                # File doesn't exist, skip it
                remaining_files.append(case)
                continue
            
            parsed_case, parsed_date = self.extract_case_from_filename(filename)
            filename_case = case_number or parsed_case
            filename_date = self._format_case_date(case.get('date')) or parsed_date
            if not filename_case or not filename_date:
                # Can't parse filename, keep it
                remaining_files.append(case)
                continue
            
            # Extract case numbers from top of PDF
            top_cases = self.extract_top_case_numbers(pdf_path)
            
            # Normalize case numbers (remove spaces) before comparison
            # This handles cases like "26-0310-C  -C" in PDF matching "26-0310-C-C" in filename
            filename_case_normalized = self._normalize_case_number(filename_case)
            normalized_top_cases = {
                self._normalize_case_number(c)
                for c in top_cases
                if self._normalize_case_number(c)
            }

            # A single caption case that differs from the filename is usually a
            # miscaptioned/reissued order, not a true consolidated document.
            if len(normalized_top_cases) < 2:
                if normalized_top_cases and filename_case_normalized not in normalized_top_cases:
                    self.log_signal(
                        f'Caption case mismatch for {filename}: caption shows {", ".join(top_cases)}; '
                        f'skipping consolidated deletion'
                    )
                remaining_files.append(case)
                continue
            other_cases = []
            for c in top_cases:
                c_normalized = self._normalize_case_number(c)
                # Skip if normalized versions are exactly the same
                if c_normalized == filename_case_normalized:
                    continue
                # Skip if one is a prefix/substring of the other (e.g., "26-0310-C" is prefix of "26-0310-C-C")
                # This handles cases where the regex extracts partial case numbers
                if filename_case_normalized.startswith(c_normalized) or c_normalized.startswith(filename_case_normalized):
                    # These are the same case number, just formatted differently - not consolidated
                    continue
                # This is a genuinely different case number
                other_cases.append(c)
            
            if not other_cases:
                # Not a consolidated case, keep it
                remaining_files.append(case)
                continue

            # Consolidated case detected
            self.log_signal(f'Consolidated case detected: {filename_case} (contains: {", ".join(other_cases)})')

            # Build a normalized group key for this consolidated group
            group_key = self._make_group_key(top_cases)

            # Default decision flags for this specific file
            should_delete = False
            delete_reason = None
            found_members = []

            # If we've already made a decision for this consolidated group, reuse it
            group_decision = self._group_decisions.get(group_key)
            if group_decision is None:
                # First time we've seen this group: check SF-View for all other members
                uncertain_sfview = False
                for other_case in other_cases:
                    self.log_signal(f'Checking SF-View for consolidated member: {other_case}...')
                    exists, found_filename = self.check_case_in_sfview(other_case, filename_date)
                    if exists is None:
                        uncertain_sfview = True
                        found_members.append({
                            'case_number': other_case,
                            'filename': None,
                            'exists_in_sfview': None
                        })
                        continue
                    if exists:
                        should_delete = True
                        found_members.append({
                            'case_number': other_case,
                            'filename': found_filename,
                            'exists_in_sfview': True
                        })
                        delete_reason = f"Case {other_case} already exists in SF-View as {found_filename}"
                        # Record group-level decision: any member found in SF-View means group is covered
                        self._group_decisions[group_key] = {
                            'mode': 'sfview_covered',
                            'delete_reason': delete_reason,
                            'sf_member_case': other_case,
                            'sf_member_filename': found_filename,
                        }
                        break
                    else:
                        found_members.append({
                            'case_number': other_case,
                            'filename': None,
                            'exists_in_sfview': False
                        })

                if not should_delete and uncertain_sfview:
                    identical_local_cases = self._find_identical_local_cases(
                        pdf_path, group_key, download_dir, downloaded_files
                    )
                    if len(identical_local_cases) > 1:
                        keep_case = self._get_lowest_case(identical_local_cases)
                        self._group_decisions[group_key] = {
                            'mode': 'sfview_unknown_local_dedupe',
                            'reason': 'SF-View check did not complete; byte-identical local copies were found',
                            'keep_case': keep_case,
                            'identical_cases': tuple(identical_local_cases),
                        }
                    else:
                        self._group_decisions[group_key] = {
                            'mode': 'sfview_unknown',
                            'reason': 'SF-View check did not complete for one or more consolidated members',
                        }
                    group_decision = self._group_decisions[group_key]
                elif not should_delete:
                    # No members found in SF-View: keep exactly one member (lowest docket) for this group
                    keep_case = self._get_lowest_case(list(group_key))
                    self._group_decisions[group_key] = {
                        'mode': 'local_keep_lowest',
                        'keep_case': keep_case,
                    }
                    group_decision = self._group_decisions[group_key]
            else:
                # We already have a group-level decision; reconstruct member info from cache if available
                for other_case in other_cases:
                    key = (other_case or "").upper()
                    cache_val = self._sfview_case_cache.get(key, (None, None))
                    exists, found_filename = cache_val
                    found_members.append({
                        'case_number': other_case,
                        'filename': found_filename,
                        'exists_in_sfview': exists,
                    })

            # Apply group-level decision to this specific file
            if group_decision is None:
                # Should not happen, but keep safe default: keep file
                self.log_signal(f'[WARNING] No group decision recorded for consolidated group {group_key}; keeping file {filename}')
                remaining_files.append(case)
                continue

            mode = group_decision.get('mode')
            if mode == 'sfview_covered':
                # Any member is in SF-View: delete this consolidated file
                should_delete = True
                delete_reason = group_decision.get('delete_reason')
            elif mode == 'sfview_unknown':
                should_delete = False
                delete_reason = None
                self.log_signal(
                    f'Keeping consolidated candidate {filename} because SF-View status is uncertain '
                    f'({group_decision.get("reason")})'
                )
            elif mode == 'sfview_unknown_local_dedupe':
                keep_case = group_decision.get('keep_case')
                identical_cases = set(group_decision.get('identical_cases', ()))
                if filename_case_normalized in identical_cases and filename_case_normalized != keep_case:
                    should_delete = True
                    delete_reason = (
                        f'Byte-identical consolidated duplicate; kept {keep_case} while SF-View was unavailable'
                    )
                else:
                    should_delete = False
                    delete_reason = None
                    self.log_signal(
                        f'Keeping one byte-identical consolidated group representative: {filename} '
                        f'({keep_case}; SF-View status uncertain)'
                    )
            elif mode == 'local_keep_lowest':
                keep_case = group_decision.get('keep_case')
                if keep_case and filename_case.upper() != keep_case.upper():
                    # This file is NOT the lowest docket in the group -> delete
                    should_delete = True
                    delete_reason = (
                        f"Consolidated group; kept lowest docket {keep_case}, deleting {filename_case}"
                    )
                else:
                    # This file is the chosen representative for the group -> keep
                    should_delete = False
                    delete_reason = None
                    self.log_signal(
                        f'Keeping consolidated group representative: {filename} '
                        f'(lowest docket {keep_case}; no members in SF-View)'
                    )

            # Log consolidated case info
            consolidated_info = {
                'filename': filename,
                'filename_case': filename_case,
                'filename_date': filename_date,
                'all_cases': top_cases,
                'other_cases': other_cases,
                'members': found_members,
                'deleted': should_delete,
                'delete_reason': delete_reason
            }
            self.consolidated_cases_log.append(consolidated_info)
            
            if should_delete:
                # Delete the file
                try:
                    pdf_path.unlink()
                    self.log_signal(f'Deleted consolidated case: {filename} - {delete_reason}')
                    case['consolidated_deleted'] = True
                    case['consolidated_delete_reason'] = delete_reason
                    case['consolidated_members'] = [m['case_number'] for m in found_members if m['exists_in_sfview']]
                    deleted_cases.append(case)
                except Exception as e:
                    self.log_signal(f'Error deleting {filename}: {str(e)}')
                    # If deletion fails, keep the file
                    remaining_files.append(case)
            else:
                if mode == 'sfview_unknown':
                    keep_reason = 'SF-View status uncertain; no byte-identical local copy found'
                elif mode == 'sfview_unknown_local_dedupe':
                    keep_reason = 'kept as the byte-identical group representative while SF-View was unavailable'
                else:
                    keep_reason = 'no other members in SF-View'
                self.log_signal(f'Keeping consolidated case: {filename} ({keep_reason})')
                remaining_files.append(case)
        
        self.log_signal(f'Consolidated case check complete. Deleted: {len(deleted_cases)}, Kept: {len(remaining_files)}')
        return remaining_files, deleted_cases
    
    def _generate_filename(self, case: Dict) -> str:
        """Generate filename from case dict"""
        format_template = self.config.get('file_naming_format', 'LDC_SMD_{case_number}_{date}_E2E')
        case_date = case.get('date')
        if isinstance(case_date, date):
            date_str = case_date.strftime('%m%d%Y')
        elif hasattr(case_date, 'strftime'):
            date_str = case_date.strftime('%m%d%Y')
        else:
            # Try to parse if it's a string
            try:
                from datetime import datetime
                if isinstance(case_date, str):
                    # Try common date formats
                    for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m%d%Y']:
                        try:
                            dt = datetime.strptime(case_date, fmt)
                            date_str = dt.strftime('%m%d%Y')
                            break
                        except:
                            continue
                    else:
                        date_str = str(case_date)
                else:
                    date_str = str(case_date)
            except:
                date_str = str(case_date)
        clean_case_number = (case.get('filename_case_number') or case.get('case_number', '')).replace(' ', '')
        filename = format_template.format(case_number=clean_case_number, date=date_str)
        return f'{filename}.pdf'
    
    def get_consolidated_cases_report(self) -> List[Dict]:
        """Get consolidated cases data for Excel report"""
        return self.consolidated_cases_log

