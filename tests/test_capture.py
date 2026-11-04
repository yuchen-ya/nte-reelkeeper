import unittest

import numpy as np

from nte_ocr.capture import crop_client


class ClientCropTests(unittest.TestCase):
    def test_high_dpi_title_bar_and_borders_are_removed(self):
        image = np.zeros((1487, 2564, 3), dtype=np.uint8)
        image[45:1485, 2:2562] = (10, 20, 30)
        client = dict(left=1278, top=361, width=2560, height=1440)
        cropped = crop_client(image, client, (1276, 316, 3840, 1803))
        self.assertEqual(cropped.shape, (1440, 2560, 3))
        self.assertTrue(np.all(cropped == (10, 20, 30)))

    def test_unexpected_capture_size_stops(self):
        with self.assertRaisesRegex(OSError, '尺寸与窗口不一致'):
            crop_client(np.zeros((50, 50, 3)), dict(left=0, top=0, width=100, height=80),
                        (0, 0, 100, 90))
