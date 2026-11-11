import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from evaluation_plots import load_test_predictions, render_report


class EvaluationTests(unittest.TestCase):
    def make_run(self, root):
        (root/'best.json').write_text(json.dumps({'classes': ['clean','stain'], 'threshold': .8}))
        (root/'history.csv').write_text('epoch,train_loss,val_loss,train_accuracy,val_accuracy\n1,1,.8,.5,.5\n2,.6,.7,.75,.75\n')
        (root/'predictions.csv').write_text('split,path,label,stain_probability\n'
            'val,val/ignored.png,1,.99\ntest,clean/a.png,0,.1\ntest,clean/b.png,0,.9\n'
            'test,stain/a.png,1,.6\ntest,stain/b.png,1,.95\n')

    def test_prediction_contract_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.make_run(root)
            records, threshold = load_test_predictions(root)
            self.assertEqual(len(records), 4)
            self.assertEqual(threshold, .8)
            with (root/'predictions.csv').open('a') as handle:
                handle.write('test,bad.png,1,nan\n')
            with self.assertRaises(ValueError):
                load_test_predictions(root)

    @unittest.skipUnless(importlib.util.find_spec('sklearn') and importlib.util.find_spec('matplotlib'),
                         'Install requirements-analysis.txt for report tests')
    def test_report_metrics_images_and_no_overwrite(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.make_run(root)
            for folder in ('clean','stain'):
                (root/folder).mkdir()
                for name in ('a','b'):
                    Image.new('RGB',(20,20),'red').save(root/folder/(name+'.png'))
            report = render_report(root, root/'figures', root)
            self.assertEqual(report['accuracy'], .5)
            self.assertEqual(report['stain']['recall'], .5)
            for name in ('learning_curves.png','evaluation.png','hard_examples.png'):
                with Image.open(root/'figures'/name) as image:
                    image.verify()
            with (root/'figures/hard_examples.csv').open() as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual(len({r['path'] for r in rows}),len(rows))
            with self.assertRaises(FileExistsError):
                render_report(root, root/'figures')
            text=(root/'predictions.csv').read_text().replace('clean/a.png','../outside.png')
            (root/'predictions.csv').write_text(text)
            with self.assertRaisesRegex(ValueError,'outside'):
                render_report(root,root/'unsafe',root)
            self.assertFalse((root/'unsafe').exists())
