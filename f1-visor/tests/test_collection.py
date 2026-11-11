from io import BytesIO
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from collect_images import (parse_bing_results, validate_url, read_candidates, fetch_image,
                            save_image, download_images)


class CollectionTests(unittest.TestCase):
    def test_metadata_is_json_not_executable_code(self):
        raw = json.dumps({"murl": "https://example.org/photo", "purl": "https://example.org/page"})
        result = parse_bing_results([raw, raw, "__import__('os').system('bad')", '[]', '{}',
                                    '{"murl":"file:///etc/passwd"}'], "helmet view")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_page"], "https://example.org/page")
        self.assertEqual(result[0]["license_status"], "unreviewed")

    def test_url_and_candidate_validation(self):
        for value in ("file:///tmp/x", "https://user:password@example.org/x", "data:image/png;base64,AAA"):
            with self.assertRaises(ValueError):
                validate_url(value)
        with patch("collect_images.socket.getaddrinfo", return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaisesRegex(ValueError, "private"):
                validate_url("https://example.org/x", resolve=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.jsonl"
            path.write_text('{"image_url":"https://example.org/x"}\n' * 2)
            self.assertEqual(len(read_candidates(path)), 1)
            path.write_text('{"image_url":"file:///tmp/x"}')
            with self.assertRaisesRegex(ValueError, "line 1"):
                read_candidates(path)

    def test_redirects_size_limit_and_content_type(self):
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/secret"}
        def addresses(host, *_args, **_kwargs):
            return [(2, 1, 6, '', ('127.0.0.1' if host == '127.0.0.1' else '93.184.216.34', 80))]
        with patch("collect_images.socket.getaddrinfo", side_effect=addresses):
            with self.assertRaisesRegex(ValueError, "private"):
                fetch_image(session, "https://example.org/x", 10)
        self.assertEqual(session.get.call_count, 1)
        response.status_code = 200
        response.headers = {"Content-Type": "image/png"}
        response.iter_content.return_value = [b"too many bytes"]
        with patch("collect_images.validate_url"):
            with self.assertRaisesRegex(ValueError, "size limit"):
                fetch_image(session, "https://example.org/x", 5)
            response.headers = {"Content-Type": "text/html"}
            with self.assertRaisesRegex(ValueError, "not an image"):
                fetch_image(session, "https://example.org/x", 100)

    @unittest.skipUnless(importlib.util.find_spec('requests'), 'Install requirements-collect.txt for download tests')
    def test_image_format_duplicate_resume_and_failures(self):
        buffer = BytesIO()
        Image.new("RGB", (16, 16), "red").save(buffer, format="PNG")
        content = buffer.getvalue()
        records = [{"image_url": "https://example.org/a", "source_page": "https://example.org/page"},
                   {"image_url": "https://example.org/b"}]
        with tempfile.TemporaryDirectory() as directory:
            saved = save_image(content, directory, 10, 10)
            self.assertTrue(saved["file"].endswith('.png'))
            self.assertEqual(save_image(content, directory, 10, 10)["status"], "duplicate")
            with self.assertRaises(ValueError):
                save_image(content, directory, 800, 600)
            with patch("collect_images.fetch_image", side_effect=[(content, records[0]["image_url"]), ValueError('bad')]):
                stats = download_images(records, directory, object(), 10, 10, delay=0)
            self.assertEqual(stats, {"downloaded": 0, "duplicate": 1, "skipped": 0, "failed": 1})
            with patch("collect_images.fetch_image", return_value=(content, records[1]["image_url"])) as fetch:
                stats = download_images(records, directory, object(), 10, 10, delay=0)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(stats['skipped'], 1)
            manifest = [json.loads(line) for line in (Path(directory)/'manifest.jsonl').read_text().splitlines()]
            self.assertEqual(manifest[0]['source_page'], records[0]['source_page'])
            self.assertIsNone(manifest[0]['label'])
            self.assertFalse(list(Path(directory).glob('*.part')))
