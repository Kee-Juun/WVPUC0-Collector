import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import fitz

from utils.consolidated_case_checker import ConsolidatedCaseChecker
from utils.pdf_text_extractor import extract_pdf_text


class PdfOcrFallbackTests(unittest.TestCase):
    @contextmanager
    def temp_directory(self):
        directory = Path(__file__).parent / f'.ocr_test_{uuid.uuid4().hex}'
        directory.mkdir()
        try:
            yield directory
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def make_pdf(path: Path, native_text: str = '') -> None:
        document = fitz.open()
        page = document.new_page()
        if native_text:
            page.insert_text((72, 72), native_text)
        document.save(str(path))
        document.close()

    def test_native_text_avoids_ocr(self):
        with self.temp_directory() as directory:
            pdf_path = directory / 'native.pdf'
            self.make_pdf(pdf_path, 'COMMISSION FINAL ORDER with enough searchable text')

            with patch('utils.pdf_text_extractor._ocr_page') as ocr_page:
                text = extract_pdf_text(pdf_path, 1, min_native_chars=10)

            self.assertIn('COMMISSION FINAL ORDER', text)
            ocr_page.assert_not_called()

    def test_thin_page_uses_ocr_fallback(self):
        with self.temp_directory() as directory:
            pdf_path = directory / 'scan.pdf'
            self.make_pdf(pdf_path)

            with patch(
                'utils.pdf_text_extractor._ocr_page',
                return_value='ADMINISTRATIVE LAW JUDGE FINAL ORDER',
            ) as ocr_page:
                text = extract_pdf_text(pdf_path, 1, min_native_chars=10)

            self.assertEqual(text, 'ADMINISTRATIVE LAW JUDGE FINAL ORDER')
            ocr_page.assert_called_once()

    def test_forced_ocr_retries_garbled_native_text(self):
        with self.temp_directory() as directory:
            pdf_path = directory / 'garbled.pdf'
            self.make_pdf(pdf_path, 'native text exists but does not reveal the visible heading')

            with patch(
                'utils.pdf_text_extractor._ocr_page',
                return_value='COMMISSION FINAL ORDER',
            ) as ocr_page:
                text = extract_pdf_text(pdf_path, 1, force_ocr=True)

            self.assertEqual(text, 'COMMISSION FINAL ORDER')
            ocr_page.assert_called_once()

    def test_consolidated_caption_can_come_from_ocr(self):
        with self.temp_directory() as directory:
            pdf_path = directory / 'scan.pdf'
            self.make_pdf(pdf_path)
            checker = ConsolidatedCaseChecker({'sf_view_url': ''}, lambda _message: None)

            with patch(
                'utils.consolidated_case_checker.extract_pdf_text',
                return_value='25-0123-G-PC\n26-0456-G-PC\nCOMMISSION FINAL ORDER',
            ):
                cases = checker.extract_top_case_numbers(pdf_path)

            self.assertEqual(cases, ['25-0123-G-PC', '26-0456-G-PC'])


if __name__ == '__main__':
    unittest.main()
