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
from ptouch_template.migrations import v1_to_2
from ptouch_template.template import (
    Template,
    TapeType,
    TemplateError,
    mm_to_px,
)


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
            cut='half',
            feed=True,
            csv=None,
        )

    def create(self, **options):
        args = self.args()
        args.name = 'test'
        args.tape_width = 18
        args.length = 20
        args.overwrite = True
        for option, value in options.items():
            setattr(args, option, value)
        pt.create_template(args)
        return pathlib.Path(args.templates) / 'test.dxf'

    def marker(self, doc):
        for entity in doc.modelspace():
            if entity.has_xdata('ptouch-template'):
                return entity

    def print_args(self, **overrides):
        args = argparse.Namespace(
            templates=self.templates_dir.name, template='test')
        for option, value in overrides.items():
            setattr(args, option, value)
        return args

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
        args.feed = False
        args.cut = 'full'
        pt.create_template(args)
        self.validate_options(args)

    def test_arguments(self):
        base_args = ['--usb', '--printer', 'P900W']
        base_create_args = base_args + ['create', 'x', '-t', '18', '-l', '10']
        for good_args in [
            base_args + ['list'],
            base_create_args,
            base_create_args + ['--cut', 'mark'],
            base_create_args + ['--cut', 'none'],
            base_args + ['create', 'x', '-t', '18', '-l', '20',
                         '--cut', 'full'],
            base_create_args + ['--cut', 'mark', '--feed', 'false'],
            base_create_args + ['--feed', 'false'],
            base_args + ['create', 'x', '-t', '18', '-l', '20',
                         '--cut', 'full', '--feed', 'false'],
            base_create_args + ['--high-resolution', 'true'],
            base_create_args + ['--high-resolution', 'yes'],
            base_args + ['create', 'x', '-t', '18', '-l', 'auto'],
            base_args + ['create', 'x', '-t', '18', '-l', 'auto',
                         '--cut', 'full'],
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
            base_args + ['create', 'x', '-t', '18', '-l', '18',
                         '--cut', 'full'],
            base_create_args + ['--cut', 'both'],
            base_create_args + ['--feed', 'maybe'],
            base_create_args + ['--high-resolution', 'sometimes'],
            base_create_args + ['--margin', '1'],
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
            cut='half',
            feed=True,
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
            'test', length='auto', margin=3, cut='none'))
        template = Template(argparse.Namespace(
            templates=args.templates, template='test'))
        # Options changed
        self.assertEqual(template.width, 0)
        self.assertEqual(template.options.margin, 3)
        self.assertEqual(template.options.cut, 'none')
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
                for cut in ['half', 'full', 'none', 'mark']:
                    for feed in [True, False]:
                        for margin in [0, 1, 2, 3]:
                            if margin < 2 and cut not in ['none', 'mark']:
                                continue
                            self.check_printing(printed_labels, length, cut,
                                                feed, margin)

    def check_printing(self, printed_labels, length, cut, feed, margin):
        with tempfile.TemporaryDirectory() as templates_dir:
            args = self.args()
            args.templates = templates_dir
            args.name = 'test'
            args.tape_width = 18
            args.length = length
            args.margin = margin
            args.feed = feed
            args.cut = cut
            pt.create_template(args)
            if length == 'auto':
                path = pathlib.Path(templates_dir) / 'test.dxf'
                doc = ezdxf.readfile(path)
                (doc.modelspace()
                 .add_text('{{text}}', height=4)
                 .set_placement((0, 2)))
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

    def append_cut_line(self, template, image):
        # Mirror the trailing margin and cut line printed when not feeding
        margin_px = mm_to_px(template.options.margin, template.dpi)
        padded = PIL.Image.new(
            'RGB', size=(image.width + margin_px, template.height),
            color=(255, 255, 255))
        padded.paste(image, (0, 0))
        PIL.ImageDraw.Draw(padded).line(
            [(padded.width - 1, 0), (padded.width - 1, padded.height)],
            fill=0, width=1)
        return padded

    def verify_print_results(self, args, printed_labels, contents, copies):
        def debug(args):
            parts = [
                f'{attr}: {getattr(args, attr)}'
                for attr in ['cut', 'feed', 'margin']
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

        if args.cut in ['none', 'mark']:
            # Concatenate with filler or mark, using actual per-label widths
            if args.margin:
                if args.cut == 'none':
                    filler = pt.create_blank(template)
                else:
                    filler = pt.create_mark(template)
                images = []
                for i, label in enumerate(labels):
                    if i:
                        images.append(filler)
                    images.append(label)
                if not args.feed:
                    margin_px = mm_to_px(template.options.margin, template.dpi)
                    images.append(PIL.Image.new(
                        'RGB', size=(margin_px, template.height),
                        color=(255, 255, 255)))
                image = concatenate(images)
            else:
                image = concatenate(labels)
                if args.cut == 'mark':
                    start = 0
                    for label in labels[:-1]:
                        start += label.width
                        PIL.ImageDraw.Draw(image).line(
                            [(start - 1, 0), (start - 1, image.height)],
                            fill=0, width=2)
            if not args.feed:
                PIL.ImageDraw.Draw(image).line(
                    [(image.width - 1, 0), (image.width - 1, image.height)],
                    fill=0, width=1)
            expected = [(image, args.feed, False, False)]
        else:
            expected = []
            for i, label in enumerate(labels):
                is_last = (i == last)
                if args.cut == 'full':
                    label = self.pad_full_cut(template, label)
                if is_last and not args.feed:
                    label = self.append_cut_line(template, label)
                expected.append((label, is_last and args.feed,
                                 args.cut == 'full', not args.cut == 'full'))

        self.assertEqual(len(printed_labels), len(expected), debug(args))
        for _expected, printed in zip(expected, printed_labels):
            for i in range(1, len(_expected)):
                self.assertEqual(_expected[i], printed[i], debug(args))
            # _expected[0].save('1.png')
            # printed[0].image.save('2.png')
            self.assertEqual(_expected[0], printed[0].image, debug(args))

    def test_version(self):
        path = self.create()
        doc = ezdxf.readfile(path)
        with ezdxf.entities.xdata.XDataUserDict.entity(
            self.marker(doc), name='template', appid='ptouch-template'
        ) as xdata:
            del xdata['version']
        doc.saveas(path)
        # A template without a matching version is refused
        with self.assertRaises(TemplateError) as context:
            Template(self.print_args(template=str(path)))
        self.assertIn('version', context.exception.args[0])
        # And skipped when listing the templates
        self.assertEqual(Template.list_templates(self.templates_dir.name), [])

    def test_upgrade(self):
        path = self.create(cut='full', feed=False)
        doc = ezdxf.readfile(path)
        # Turn the template back into a version 1 template
        with ezdxf.entities.xdata.XDataUserDict.entity(
            self.marker(doc), name='options', appid='ptouch-template'
        ) as options:
            del options['cut']
            del options['feed']
            options['full_cut'] = 1
            options['no_cut'] = 0
            options['mark'] = 0
            options['no_feed'] = 1
        with ezdxf.entities.xdata.XDataUserDict.entity(
            self.marker(doc), name='template', appid='ptouch-template'
        ) as xdata:
            del xdata['version']
        doc.saveas(path)

        v1_to_2.upgrade(path)
        template = Template(self.print_args())
        self.assertEqual(template.options.cut, 'full')
        self.assertFalse(template.options.feed)

    def test_overrides(self):
        self.create(cut='none', margin=0)
        template = Template(self.print_args(
            cut='half', margin=2, feed=False, high_resolution=True,
            length='auto'))
        self.assertEqual(template.options.cut, 'half')
        self.assertEqual(template.options.margin, 2)
        self.assertFalse(template.options.feed)
        self.assertTrue(template.options.high_resolution)
        self.assertEqual(template.width, 0)
        # Without overrides the stored options are used
        template = Template(self.print_args())
        self.assertEqual(template.options.cut, 'none')
        self.assertEqual(template.options.margin, 0)
        self.assertTrue(template.options.feed)
        self.assertEqual(template.width, mm_to_px(20, template.dpi))

    def test_clipping(self):
        path = self.create()
        doc = ezdxf.readfile(path)
        (doc.modelspace()
         .add_text('{{text}}', height=4)
         .set_placement((0, 2)))
        doc.saveas(path)
        template = Template(self.print_args())
        self.assertIsNotNone(pt.create_label(template, 'fits'))
        with self.assertRaises(pt.ClipError):
            pt.create_label(template, 'this text is far too long to fit')

        path = self.create(length=40)
        doc = ezdxf.readfile(path)
        (doc.modelspace()
         .add_text('{{text}}', height=20)
         .set_placement((0, 2)))
        doc.saveas(path)
        template = Template(self.print_args())
        with self.assertRaises(pt.ClipError):
            pt.create_label(template, 'high')


if __name__ == '__main__':
    unittest.main(buffer=True)
