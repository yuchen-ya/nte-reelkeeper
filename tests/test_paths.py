from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nte_ocr.paths import application_directory
from nte_ocr.vision import Reader, RecognitionError


class PortablePathTests(unittest.TestCase):
    def test_missing_portable_model_is_rejected_before_ocr_initializes(self):
        with tempfile.TemporaryDirectory() as folder, patch('sys.frozen', True, create=True), \
                patch('nte_ocr.vision.ROOT', Path(folder)), patch('nte_ocr.vision.RapidOCR') as engine:
            with self.assertRaisesRegex(RecognitionError, '模型缺失'):
                Reader()
            engine.assert_not_called()

    def test_frozen_paths_follow_executable_not_temporary_bundle(self):
        with tempfile.TemporaryDirectory(prefix='便携 中文 ') as folder:
            with patch('sys.frozen', True, create=True), patch('sys.executable', str(Path(folder) / 'ReelKeeper.exe')):
                root = application_directory()
                settings = root / 'settings.json'
                settings.write_text('{"rounds": 5}', encoding='utf-8')
                self.assertEqual(application_directory(), Path(folder).resolve())
                self.assertEqual((application_directory() / 'settings.json').read_text(encoding='utf-8'), '{"rounds": 5}')

    def test_source_paths_keep_existing_project_location(self):
        with patch('sys.frozen', False, create=True):
            self.assertEqual(application_directory(), Path(__file__).resolve().parents[1])
