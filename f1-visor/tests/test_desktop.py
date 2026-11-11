import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np
import detect_video


class DesktopTests(unittest.TestCase):
    def test_snapshot_is_raw_and_camera_closes_on_save_failure(self):
        for write_ok in (True, False):
            with self.subTest(write_ok=write_ok), tempfile.TemporaryDirectory() as directory:
                cv2 = MagicMock()
                capture = cv2.VideoCapture.return_value
                capture.isOpened.return_value = True
                capture.read.side_effect = lambda: (True, np.zeros((40, 40, 3), dtype=np.uint8))
                cv2.cvtColor.side_effect = lambda frame, _: frame
                cv2.putText.side_effect = lambda frame, *_args: frame.fill(255)
                cv2.waitKey.side_effect = [ord('s'), ord('q')]
                cv2.imwrite.return_value = write_ok
                predictor = MagicMock()
                predictor.meta = {'threshold': .4}
                predictor.predict.return_value = .8
                with patch.dict('sys.modules', {'cv2': cv2}), \
                     patch('f1visor.vision.Predictor', return_value=predictor), \
                     patch('sys.argv', ['detect_video.py', '--snapshots', directory]), patch('builtins.print'):
                    if write_ok:
                        detect_video.main()
                    else:
                        with self.assertRaises(OSError):
                            detect_video.main()
                saved_path, saved_frame = cv2.imwrite.call_args.args
                self.assertEqual(Path(saved_path).parent, Path(directory))
                self.assertEqual(int(saved_frame.sum()), 0)
                capture.release.assert_called_once()
                cv2.destroyAllWindows.assert_called_once()
