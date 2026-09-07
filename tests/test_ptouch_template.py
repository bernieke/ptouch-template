#!/usr/bin/env python

import argparse
import pathlib
import tempfile
import unittest
import unittest.mock

import ezdxf
import PIL

from ptouch_template.cli import main
from ptouch_template import ptouch_template as pt
from ptouch_template.template import Template, TapeType, mm_to_px


PRINTERS = {
    'P900W': {
        'height': {
            1: {9: 106, 18: 234},
            2: {9: 88},
        },
        'dpi': 360,
    },
}


class PtouchTemplateTestCase(unittest.TestCase):

    def setUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        self.templates_dir = tempfile.TemporaryDirectory()
        unittest.mock.patch('xdg_base_dirs.xdg_config_Home', lambda: '/tmp')

    def tearDown(self):
        self.config_dir.cleanup()
        self.templates_dir.cleanup()

    def args(self):
        return argparse.Namespace(
            debug=False,
            templates=self.templates_dir.name,
            host=None,
            usb=True,
            printer='P900W',
            no_compression=False,
            tape_width=None,
            tube_width=None,
            length=None,
            high_resolution=False,
            margin=2,
            no_feed=False,
            full_cut=False,
            no_cut=False,
            mark=False,
            csv=None,
        )

    def height(self, args):
        media_width = args.tape_width or args.tube_width
        media_type = 1 if args.tape_width else 2
        return PRINTERS[args.printer]['height'][media_type][media_width]

    def validate_options(self, args):
        name = args.__dict__.pop('name')
        args.template = name
        template = Template(args)
        self.assertEqual(template.name, name)
        expected_width_px = mm_to_px(args.length, template.dpi)
        self.assertEqual(template.width, expected_width_px)
        self.assertEqual(template.height, self.height(args))
        self.assertEqual(template.dpi, PRINTERS[args.printer]['dpi'])
        if args.tape_width:
            self.assertEqual(template.options.media_type, TapeType.TAPE)
            self.assertEqual(template.options.media_width, args.tape_width)
        else:
            self.assertEqual(template.options.media_type, TapeType.TUBE)
            self.assertEqual(template.options.media_width, args.tube_width)
        for option in template.options.__annotations__:
            if option in ['media_type', 'media_width']:
                continue
            self.assertEqual(getattr(template.options, option),
                             getattr(args, option))

    def test_save_load_options(self):
        args = self.args()
        args.name = 'test'
        args.tape_width = 18
        args.length = 20
        args.no_feed = True
        args.full_cut = True
        pt.create_template(args)
        self.validate_options(args)

    def test_arguments(self):
        base_args = ['--usb', '--printer', 'P900W']
        base_create_args = base_args + ['create', 'x', '-t', '18', '-l', '10']
        for good_args in [
            base_args + ['list'],
            base_create_args,
            base_create_args + ['--mark'],
            base_create_args + ['--no-cut'],
            base_args + ['create', 'x', '-t', '18', '-l', '20', '--full-cut'],
            base_create_args + ['--mark', '--no-feed'],
            base_args + ['create', 'x', '-t', '18', '-l', 'auto'],
            base_args + ['create', 'x', '-t', '18', '-l', 'auto',
                         '--full-cut'],
        ]:
            with tempfile.TemporaryDirectory() as templates_dir:
                args = ['ptouch-template', '-t', templates_dir] + good_args
                with unittest.mock.patch('sys.argv', args):
                    try:
                        main()
                    except (Exception, SystemExit):
                        print(args)
                        raise
        for bad_args in [
            [],
            base_args,
            base_args + ['create'],
            base_args + ['create', 'x'],
            base_args + ['create', 'x', '-t', '18', '-l', '18', '--full-cut'],
            base_create_args + ['--no-feed'],
            base_create_args + ['--no-feed', '--full-cut'],
            base_create_args + ['--mark', '--full-cut'],
            base_create_args + ['--mark', '--no-cut'],
            base_create_args + ['--no-cut', '--full-cut'],
            base_args + ['create', 'x', '-t', '18', '-l', '0'],
            base_args + ['create', 'x', '-t', '18', '-l', '-5'],
            base_args + ['edit'],
            base_args + ['edit', 'x'],
            base_args + ['edit', 'x', '-l', 'auto', '-T', '18'],
        ]:
            with tempfile.TemporaryDirectory() as templates_dir:
                args = ['ptouch-template', '-t', templates_dir] + bad_args
                with unittest.mock.patch('sys.argv', ['pt'] + bad_args):
                    with self.assertRaises(SystemExit, msg=args):
                        main()

    def test_media_type(self):
        args = self.args()
        args.name = 'tape'
        args.tape_width = 9
        args.length = 20
        pt.create_template(args)
        self.validate_options(args)

        args = self.args()
        args.name = 'tube'
        args.tube_width = 9
        args.length = 20
        pt.create_template(args)
        self.validate_options(args)

    def edit_args(self, name, **options):
        args = argparse.Namespace(
            command='edit',
            templates=self.templates_dir.name,
            name=name,
            printer='P900W',
            length='auto',
            high_resolution=False,
            margin=2,
            no_feed=False,
            full_cut=False,
            no_cut=False,
            mark=False,
        )
        for option, value in options.items():
            setattr(args, option, value)
        return args

    def test_edit(self):
        args = self.args()
        args.name = 'test'
        args.tape_width = 18
        args.length = 20
        pt.create_template(args)
        # Add user content to the template
        path = pathlib.Path(args.templates) / 'test.dxf'
        doc = ezdxf.readfile(path)
        (doc.modelspace()
         .add_text('{{name}}', height=6)
         .set_placement((0, 0)))
        doc.saveas(path)

        # Edit options, keeping the tape width and the content
        pt.edit_template(self.edit_args(
            'test', length='auto', margin=3, no_cut=True))
        template = Template(argparse.Namespace(
            templates=args.templates, template='test'))
        # Options changed
        self.assertEqual(template.width, 0)
        self.assertEqual(template.options.margin, 3)
        self.assertTrue(template.options.no_cut)
        # Tape width cannot be changed
        self.assertEqual(template.options.media_type, TapeType.TAPE)
        self.assertEqual(template.options.media_width, 18)
        # Content preserved
        self.assertIn('name', template.placeholders)

    def test_edit_nonexistent(self):
        with self.assertRaises(pt.PrintError):
            pt.edit_template(self.edit_args('nope', length=20))

    def test_printing(self):
        printed_labels = []

        def mock_print(self, label, margin_mm=None, high_resolution=None,
                      feed=True, auto_cut=None, half_cut=None):
            printed_labels.append((label, feed, auto_cut, half_cut))

        mock_conn = unittest.mock.MagicMock()
        with (
            unittest.mock.patch('ptouch.ConnectionUSB',
                                return_value=mock_conn),
            unittest.mock.patch('ptouch.PTP900W.print', mock_print),
        ):
            for length in [20, 'auto']:
                for cut in [None, 'half-cut', 'full-cut', 'mark', 'no-cut']:
                    for no_feed in [True, False]:
                        for margin in [0, 1, 2, 3]:
                            if margin < 2 and cut in ['half-cut', 'full-cut']:
                                continue
                            if no_feed and cut not in ['no-cut', 'mark']:
                                continue
                            self.check_printing(printed_labels, length, cut,
                                                no_feed, margin)

    def check_printing(self, printed_labels, length, cut, no_feed, margin):
        with tempfile.TemporaryDirectory() as templates_dir:
            args = self.args()
            args.templates = templates_dir
            args.name = 'test'
            args.tape_width = 18
            args.length = length
            args.margin = margin
            args.no_feed = no_feed
            args.full_cut = (cut == 'full-cut')
            args.mark = (cut == 'mark')
            args.no_cut = (cut == 'no-cut')
            pt.create_template(args)
            if length == 'auto':
                path = pathlib.Path(templates_dir) / 'test.dxf'
                doc = ezdxf.readfile(path)
                (doc.modelspace()
                 .add_text('{{text}}', height=4)
                 .set_placement((0, 0)))
                doc.saveas(path)
                contents = ['long enough', '', 'short']
                copies = 1
            else:
                contents = []
                copies = 3
            print_args = argparse.Namespace(
                debug=False,
                usb=True,
                host=None,
                no_compression=False,
                templates=templates_dir,
                template=args.name,
                copies=copies,
                contents=contents,
                csv=None,
            )
            pt.print_labels(print_args)
            self.verify_print_results(args, printed_labels, contents, copies)
            printed_labels.clear()

    def pad_full_cut(self, template, image):
        # Mirror the full-cut minimum-length padding applied when printing
        min_px = mm_to_px(
            pt.MIN_FULL_CUT_WIDTH.get(template.options.printer, 0),
            template.dpi)
        if image.width >= min_px:
            return image
        padded = PIL.Image.new('RGB', size=(min_px, template.height),
                               color=(255, 255, 255))
        padded.paste(image, (0, 0))
        return padded

    def verify_print_results(self, args, printed_labels, contents, copies):
        def debug(args):
            parts = [
                f'{attr}: {getattr(args, attr)}'
                for attr in ['no_feed', 'full_cut', 'mark', 'no_cut', 'margin']
            ]
            return ', '.join(parts)

        def concatenate(images):
            total_width = sum(image.width for image in images)
            _image = PIL.Image.new('RGB', size=(total_width, images[0].height))
            start = 0
            for image in images:
                _image.paste(image, (start, 0))
                start += image.width
            return _image

        template = Template(argparse.Namespace(
            templates=args.templates, template=args.name))

        # Reconstruct the labels the same way print_labels expands contents,
        # dropping blank labels that render no content (auto templates)
        rows = (list(contents) if template.placeholders else [None]) * copies
        labels = [
            label
            for label in (pt.create_label(template, row) for row in rows)
            if label is not None
        ]
        last = len(labels) - 1

        if args.no_cut or args.mark:
            # Concatenate with filler or mark, using actual per-label widths
            if args.margin:
                if args.no_cut:
                    filler = pt.create_blank(template)
                else:
                    filler = pt.create_mark(template)
                images = []
                for i, label in enumerate(labels):
                    if i:
                        images.append(filler)
                    images.append(label)
                if args.no_feed:
                    margin_px = mm_to_px(template.options.margin, template.dpi)
                    images.append(PIL.Image.new(
                        'RGB', size=(margin_px, template.height),
                        color=(255, 255, 255)))
                image = concatenate(images)
            else:
                image = concatenate(labels)
                if args.mark:
                    start = 0
                    for label in labels[:-1]:
                        start += label.width
                        PIL.ImageDraw.Draw(image).line(
                            [(start - 1, 0), (start - 1, image.height)],
                            fill=0, width=2)
            if args.no_feed:
                PIL.ImageDraw.Draw(image).line(
                    [(image.width - 1, 0), (image.width - 1, image.height)],
                    fill=0, width=1)
            expected = [(image, not args.no_feed, False, False)]
        elif args.full_cut:
            expected = [
                (self.pad_full_cut(template, label), i == last, True, False)
                for i, label in enumerate(labels)
            ]
        else:
            expected = [
                (label, i == last, False, True)
                for i, label in enumerate(labels)
            ]

        self.assertEqual(len(printed_labels), len(expected), debug(args))
        for _expected, printed in zip(expected, printed_labels):
            for i in range(1, len(_expected)):
                self.assertEqual(_expected[i], printed[i], debug(args))
            # _expected[0].save('1.png')
            # printed[0].image.save('2.png')
            self.assertEqual(_expected[0], printed[0].image, debug(args))


if __name__ == '__main__':
    unittest.main(buffer=True)
