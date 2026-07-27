import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from utils.consolidated_case_checker import ConsolidatedCaseChecker


class ConsolidatedTimeoutDedupTests(unittest.TestCase):
    GROUP = ['24-0789-G-PC', '26-0448-G-PC']

    def make_checker(self):
        return ConsolidatedCaseChecker(
            {
                'sf_view_url': '',
                'consolidated_sfview_retry_attempts': 2,
                'consolidated_sfview_timeout_seconds': 1,
            },
            lambda _message: None,
        )

    @contextmanager
    def temp_directory(self):
        directory = Path(__file__).parent / f'.consolidated_test_{uuid.uuid4().hex}'
        directory.mkdir()
        try:
            yield directory
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def make_case(self, directory: Path, case_number: str, content: bytes):
        filename = f'LDC_SMD_{case_number}_07222026_E2E.pdf'
        path = directory / filename
        path.write_bytes(content)
        return {
            'case_number': case_number,
            'date': '07/22/2026',
            'saved_filename': filename,
            'saved_path': str(path),
        }

    def test_timeout_keeps_only_lowest_case_when_local_pdfs_are_identical(self):
        with self.temp_directory() as directory:
            cases = [self.make_case(directory, case, b'identical consolidated PDF') for case in self.GROUP]
            checker = self.make_checker()

            with patch.object(checker, 'extract_top_case_numbers', return_value=self.GROUP), \
                    patch.object(checker, 'check_case_in_sfview', return_value=(None, None)):
                remaining, deleted = checker.check_and_delete_consolidated_cases(directory, cases)

            self.assertEqual([case['case_number'] for case in remaining], ['24-0789-G-PC'])
            self.assertEqual([case['case_number'] for case in deleted], ['26-0448-G-PC'])
            self.assertTrue((directory / cases[0]['saved_filename']).exists())
            self.assertFalse((directory / cases[1]['saved_filename']).exists())

    def test_timeout_keeps_nonidentical_local_pdfs(self):
        with self.temp_directory() as directory:
            cases = [
                self.make_case(directory, self.GROUP[0], b'first PDF'),
                self.make_case(directory, self.GROUP[1], b'different PDF'),
            ]
            checker = self.make_checker()

            with patch.object(checker, 'extract_top_case_numbers', return_value=self.GROUP), \
                    patch.object(checker, 'check_case_in_sfview', return_value=(None, None)):
                remaining, deleted = checker.check_and_delete_consolidated_cases(directory, cases)

            self.assertEqual(len(remaining), 2)
            self.assertEqual(deleted, [])

    def test_uncertain_sfview_results_are_retried_and_not_cached(self):
        checker = self.make_checker()
        checker.sf_view_path = Path('available-for-test')

        with patch.object(
            checker,
            '_check_case_in_sfview_with_glob',
            return_value=(None, None),
        ) as lookup:
            self.assertEqual(checker.check_case_in_sfview('26-0448-G-PC', '07222026'), (None, None))
            self.assertEqual(checker.check_case_in_sfview('26-0448-G-PC', '07222026'), (None, None))

        self.assertEqual(lookup.call_count, 4)
        self.assertNotIn('26-0448-G-PC', checker._sfview_case_cache)


if __name__ == '__main__':
    unittest.main()
