import io
import logging
import shutil
import unittest
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.case_collector import CaseCollector
from utils.logger import Logger


class _NoSfViewMatches:
    def check_case_exists_in_sfview(self, _case_number):
        return False


class ConsolidationLoggingTests(unittest.TestCase):
    GROUP = [
        '26-0597-PSD-C',
        '26-0676-PSD-C',
        '26-0698-PSD-C',
        '26-0699-PSD-C',
        '26-0707-PSD-C',
        '26-0714-PSD-C',
    ]

    @contextmanager
    def temp_directory(self):
        directory = Path(__file__).parent / f'.logging_test_{uuid.uuid4().hex}'
        directory.mkdir()
        try:
            yield directory
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _case(case_number):
        return {'case_number': case_number, 'link': f'https://example.test/{case_number}'}

    def test_tracker_log_separates_matches_from_remaining_group_cases(self):
        logs = []
        skipped = []
        all_cases = [self._case(case_number) for case_number in self.GROUP]
        remaining = all_cases[1:5]
        collector = CaseCollector(
            driver=None,
            log_signal=logs.append,
            config={},
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            db_path=None,
            collector_name='WVPUC0',
            pdf_processor=None,
            sfview_checker=_NoSfViewMatches(),
            skipped_files=skipped,
        )
        collector._consolidation_groups = {'test-group': all_cases}

        result = collector.apply_consolidation_rules(
            remaining,
            {'26-0597-PSD-C', '26-0714-PSD-C'},
        )

        self.assertEqual(result, [])
        self.assertEqual(len(skipped), 4)
        self.assertIn(
            '  -> Tracker matches: 26-0597-PSD-C, 26-0714-PSD-C',
            logs,
        )
        self.assertIn(
            '  -> Skipped 4 remaining consolidated case(s): '
            '26-0676-PSD-C, 26-0698-PSD-C, 26-0699-PSD-C, 26-0707-PSD-C',
            logs,
        )
        self.assertFalse(any('6 duplicates' in message for message in logs))

    def test_logger_is_safe_for_cp1252_console_and_utf8_log_file(self):
        with self.temp_directory() as directory:
            raw_console = io.BytesIO()
            console = io.TextIOWrapper(raw_console, encoding='cp1252', errors='strict')
            with patch('sys.stderr', console):
                logger = Logger(log_dir=str(directory))
                logger.info('Unicode marker: →')
                for handler in logger.logger.handlers:
                    handler.flush()
                console.flush()

            console_text = raw_console.getvalue().decode('cp1252')
            file_text = logger.log_file.read_text(encoding='utf-8')
            self.assertIn('Unicode marker: ?', console_text)
            self.assertIn('Unicode marker: →', file_text)
            for handler in list(logger.logger.handlers):
                handler.close()
                logger.logger.removeHandler(handler)


if __name__ == '__main__':
    unittest.main()
