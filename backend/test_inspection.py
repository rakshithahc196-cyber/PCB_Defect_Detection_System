"""Regression checks for checkpoint-only inspection."""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image, ImageDraw
from backend import app as api


class TensorList:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class InspectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        model = root / 'best.pt'
        model.touch()
        state = {'classes': [], 'samples': [], 'history': [], 'scan_count': 0, 'defect_count': 0}
        for name, value in [('MODEL', model), ('DETECTIONS', root)]:
            patcher = patch.object(api, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, kwargs in [('read_state', {'return_value': state}), ('write_state', {})]:
            patcher = patch.object(api, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        data = io.BytesIO()
        image = Image.new('RGB', (200, 200), 'white')
        image.paste((30, 140, 60), (10, 10, 190, 190))  # whole board in view
        image.save(data, format='PNG')
        self.data = data.getvalue()

    @staticmethod
    def encode(image):
        data = io.BytesIO()
        image.save(data, format='PNG')
        return data.getvalue()

    def test_all_classes_use_real_predictions_without_board_gate(self):
        names = {i: f'class_{i}' for i in range(11)}
        result = SimpleNamespace(names=names, boxes=SimpleNamespace(
            xyxy=TensorList([[20, 40, 100, 120]] * 11),
            conf=TensorList([0.71] * 11), cls=TensorList(list(names))))
        with patch.object(api, 'predict_yolo', return_value=result) as predict:
            scan = asyncio.run(api.run_inspection(self.data))
        self.assertEqual([f['name'] for f in scan['findings']], list(names.values()))
        self.assertEqual(scan['findings'][0]['confidence'], 0.71)
        box = scan['findings'][0]['box']
        crop = predict.call_args.args[0]
        self.assertEqual([round(box['x'] * crop.width), round(box['y'] * crop.height), round(box['w'] * crop.width), round(box['h'] * crop.height)], [20, 40, 80, 80])  # relative to the board crop
        self.assertEqual(scan['model_file'], 'best.pt')
        self.assertFalse(scan['model_stale'])
        self.assertEqual(scan['region_source'], 'green')
        self.assertEqual(predict.call_count, 1)

    def test_no_detection_is_unknown(self):
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            scan = asyncio.run(api.run_inspection(self.data))
        self.assertFalse(scan['pcb_detected'])
        self.assertEqual(scan['findings'], [])
        predict.assert_called_once()

    def test_frame_without_green_board_skips_model(self):
        with patch.object(api, 'predict_yolo') as predict:
            scan = asyncio.run(api.run_inspection(self.encode(Image.new('RGB', (200, 200), 'white'))))
        predict.assert_not_called()
        self.assertFalse(scan['pcb_detected'])
        self.assertEqual(scan['region_source'], 'none')
        self.assertTrue(scan['localization_warning'])

    def test_crops_to_green_board(self):
        image = Image.new('RGB', (400, 300), 'white')
        image.paste((30, 140, 60), (100, 50, 300, 250))
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            scan = asyncio.run(api.run_inspection(self.encode(image)))
        width, height = predict.call_args.args[0].size
        self.assertTrue(200 <= width <= 212 and 200 <= height <= 212, (width, height))
        self.assertEqual(scan['region_source'], 'green')
        self.assertAlmostEqual(scan['pcb_region']['x'], .25, places=2)

    def test_dark_blue_green_board_clipped_top_and_bottom_is_inspected(self):
        image = Image.new('RGB', (400, 300), (225, 230, 228))
        image.paste((20, 70, 60), (150, 0, 370, 300))  # dark teal solder mask, like older boards
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            scan = asyncio.run(api.run_inspection(self.encode(image), full_view=True))
        predict.assert_called_once()
        self.assertEqual(scan['region_source'], 'green')

    def test_large_board_clipped_at_one_edge_is_inspected(self):
        image = Image.new('RGB', (400, 300), 'white')
        image.paste((30, 140, 60), (80, 100, 320, 300))  # runs off the bottom only
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            scan = asyncio.run(api.run_inspection(self.encode(image), full_view=True))
        predict.assert_called_once()
        self.assertEqual(scan['region_source'], 'green')

    def test_sliver_at_one_edge_is_not_inspected(self):
        image = Image.new('RGB', (400, 300), 'white')
        image.paste((30, 140, 60), (0, 60, 50, 240))
        with patch.object(api, 'predict_yolo') as predict:
            scan = asyncio.run(api.run_inspection(self.encode(image), full_view=True))
        predict.assert_not_called()
        self.assertTrue(scan['localization_warning'].startswith('PCB only partly in view'))

    def test_upload_cropped_to_board_edges_is_still_inspected(self):
        image = Image.new('RGB', (300, 200), (30, 140, 60))
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            asyncio.run(api.run_inspection(self.encode(image)))
        predict.assert_called_once()

    def test_defects_off_board_or_whole_crop_are_dropped(self):
        image = Image.new('RGB', (400, 300), (128, 128, 128))
        ImageDraw.Draw(image).ellipse((100, 50, 300, 250), fill=(30, 140, 60))  # round board leaves background in the crop corners
        names = {0: 'burnt_pcb', 1: 'goodpcb'}
        result = SimpleNamespace(names=names, boxes=SimpleNamespace(
            xyxy=TensorList([[50, 50, 100, 100], [0, 0, 208, 208], [0, 0, 208, 208], [0, 0, 10, 10], [140, 0, 160, 208], [90, 12, 120, 195]]),
            conf=TensorList([0.9] * 6), cls=TensorList([0, 0, 1, 0, 0, 0])))
        with patch.object(api, 'predict_yolo', return_value=result) as predict:
            scan = asyncio.run(api.run_inspection(self.encode(image)))
        crop = predict.call_args.args[0]
        self.assertEqual(crop.getpixel((1, 1)), (255, 255, 255))  # background painted out
        # kept: a small burn, the whole-board goodpcb box and a long crack (90..120) running most of the board;
        # dropped: whole-crop defect, off-board corner box and an edge-to-edge strip
        self.assertEqual([(f['name'], round(f['box']['x'] * crop.width)) for f in scan['findings']], [('burnt_pcb', 50), ('goodpcb', 0), ('burnt_pcb', 90)])

    def test_orientation_merge(self):
        upright = [([10, 10, 50, 50], 0.35, 2), ([100, 100, 140, 140], 0.4, 4), ([200, 10, 240, 60], 0.9, 6)]
        flipped = [([12, 11, 49, 52], 0.3, 2), ([300, 300, 340, 340], 0.95, 7), ([60, 60, 90, 90], 0.3, 5)]
        kept = api.merge_orientations(upright, flipped, 0.25)
        # kept: agreed weak defect, confident upright-only and confident flipped-only; dropped: weak single-view hits
        self.assertEqual(sorted((cls, round(score, 2)) for _, score, cls in kept), [(2, 0.35), (6, 0.9), (7, 0.95)])

    def test_manual_crop(self):
        with patch.object(api, 'predict_yolo', return_value=SimpleNamespace(boxes=None)) as predict:
            scan = asyncio.run(api.run_inspection(self.data, '{"x":0.1,"y":0.1,"w":0.8,"h":0.8}'))
        self.assertEqual(predict.call_args.args[0].size, (160, 160))
        self.assertEqual(scan['region_source'], 'manual')

    def test_missing_checkpoint_has_no_fallback(self):
        api.MODEL.unlink()
        with self.assertRaises(HTTPException) as error:
            asyncio.run(api.run_inspection(self.data))
        self.assertEqual(error.exception.status_code, 409)

    def test_invalid_crop_is_rejected(self):
        with self.assertRaises(HTTPException):
            asyncio.run(api.run_inspection(self.data, '{"x":2,"y":0,"w":1,"h":1}'))


if __name__ == '__main__':
    unittest.main()
