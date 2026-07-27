"""
Excel reporting module for WVPUC0 Document Collector
Handles saving results to Excel files with styling
"""
import pandas as pd
import openpyxl
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Callable, Optional


class ExcelReporter:
    """Handles Excel file generation and styling for WVPUC0 results"""
    
    def __init__(self, log_signal: Callable[[str], None], generate_filename_fn: Callable[[Dict], str]):
        """
        Initialize Excel reporter
        
        Args:
            log_signal: Signal/function to emit log messages
            generate_filename_fn: Function to generate filename from case dict
        """
        self.log_signal = log_signal
        self.generate_filename = generate_filename_fn
    
    def save_results(self, download_dir: Path, downloaded_files: List[Dict], skipped_files: List[Dict], consolidated_cases: Optional[List[Dict]] = None):
        """Save all results to a single Excel file with multiple sheets"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = download_dir / f'WVPUC0_Run_Report_{timestamp}.xlsx'
            
            with pd.ExcelWriter(report_file, engine='openpyxl') as writer:
                # Sheet 1: Downloaded Cases
                if downloaded_files:
                    df_downloaded = self.prepare_dataframe_for_excel(downloaded_files)
                    df_downloaded.to_excel(writer, sheet_name='Downloaded Cases', index=False)
                    self._apply_sheet_styling(writer, 'Downloaded Cases', len(df_downloaded.columns))
                    self.log_signal(f'Downloaded cases sheet added to report')
                
                # Sheet 2: Skipped Cases
                if skipped_files:
                    df_skipped = self.prepare_dataframe_for_excel(skipped_files)
                    df_skipped.to_excel(writer, sheet_name='Skipped Cases', index=False)
                    self._apply_sheet_styling(writer, 'Skipped Cases', len(df_skipped.columns))
                    self.log_signal(f'Skipped cases sheet added to report')
                
                # Sheet 3: Consolidated Cases
                if consolidated_cases:
                    df_consolidated = self.prepare_consolidated_dataframe(consolidated_cases)
                    if not df_consolidated.empty:
                        df_consolidated.to_excel(writer, sheet_name='Consolidated Cases', index=False)
                        self._apply_sheet_styling(writer, 'Consolidated Cases', len(df_consolidated.columns))
                        self.log_signal(f'Consolidated cases sheet added to report')
            
            self.log_signal(f'WVPUC0 Run Report saved to: {report_file}')
        except Exception as e:
            self.log_signal(f'Error saving results: {str(e)}')
    
    def prepare_dataframe_for_excel(self, cases: List[Dict]) -> pd.DataFrame:
        """Prepare dataframe with proper headers and filename column"""
        df = pd.DataFrame(cases)
        # Prefer the actual saved filename when present; otherwise generate the expected one.
        def build_filename(row):
            saved_filename = row.get('saved_filename')
            if isinstance(saved_filename, str) and saved_filename:
                return saved_filename
            return self.generate_filename({
                'date': row['date'] if isinstance(row['date'], date) else row['date'],
                'case_number': row['case_number']
            })
        df['filename'] = df.apply(build_filename, axis=1)
        df = df.rename(columns={
            'date_text': 'Date',
            'case_number': 'Case Number',
            'link': 'Link',
            'description': 'Description',
            'filename': 'Filename',
            'consolidation_reason': 'Consolidation Reason'
        })
        base_columns = ['Date', 'Case Number', 'Link', 'Description', 'Filename']
        if 'Consolidation Reason' in df.columns:
            base_columns.append('Consolidation Reason')
        df = df[base_columns]
        return df
    
    def _apply_sheet_styling(self, writer: pd.ExcelWriter, sheet_name: str, num_columns: int):
        """Apply styling to a sheet in the Excel writer"""
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        header_colors = ['90EE90'] * num_columns
        for col_idx, color in enumerate(header_colors, start=1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.fill = openpyxl.styles.PatternFill(start_color=color, end_color=color, fill_type='solid')
            cell.font = openpyxl.styles.Font(bold=True)
    
    def prepare_consolidated_dataframe(self, consolidated_cases: List[Dict]) -> pd.DataFrame:
        """Prepare consolidated cases data for Excel"""
        try:
            report_data = []
            for case_info in consolidated_cases:
                # Create a row for each member case
                for member in case_info.get('members', []):
                    report_data.append({
                        'Filename': case_info.get('filename', ''),
                        'Primary Case': case_info.get('filename_case', ''),
                        'Date': case_info.get('filename_date', ''),
                        'All Cases in Document': ', '.join(case_info.get('all_cases', [])),
                        'Member Case': member.get('case_number', ''),
                        'Member Exists in SF-View': 'Yes' if member.get('exists_in_sfview') else 'No',
                        'Member Filename in SF-View': member.get('filename', '') or 'N/A',
                        'Status': 'DELETED' if case_info.get('deleted') else 'KEPT',
                        'Delete Reason': case_info.get('delete_reason', '') or 'N/A'
                    })
            
            if report_data:
                return pd.DataFrame(report_data)
            return pd.DataFrame()
        except Exception as e:
            self.log_signal(f'Error preparing consolidated cases dataframe: {str(e)}')
            return pd.DataFrame()

