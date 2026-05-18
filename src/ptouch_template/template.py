#!/usr/bin/env python

import argparse
import enum
import math
import os
import pathlib
import re

import ezdxf
import ezdxf.addons.drawing.layout
import ptouch.__main__

PRINTERS = list(ptouch.__main__.PRINTER_TYPES.keys())
TAPE_WIDTHS = list(ptouch.__main__.TAPE_WIDTHS.keys())
TUBE_WIDTHS = list(ptouch.__main__.TUBE_WIDTHS.keys())

MM = ezdxf.addons.drawing.layout.Units.mm

TEXT_ENTITIES = 'TEXT MTEXT ATTRIB ATTDEF'


def px_to_mm(px, dpi):
    return px * 25.4 / dpi


def px_to_in(px, dpi):
    return px / dpi


def mm_to_px(mm, dpi):
    return math.ceil(mm * dpi / 25.4)


class TemplateError(Exception):
    pass


class TapeType(enum.Enum):
    TAPE = 1
    TUBE = 2


class Options:
    printer: str
    media_type: TapeType
    media_width: float
    high_resolution: bool = False
    margin: float = 2
    full_cut: bool = False
    no_cut: bool = False
    no_feed: bool = False
    mark: bool = False

    def __init__(self, path, args=None):
        if args:
            # Create template
            for arg in self.__annotations__:
                if arg not in ['media_type', 'media_width']:
                    setattr(self, arg, getattr(args, arg))
            if args.tape_width:
                self.media_type = TapeType.TAPE
                self.media_width = args.tape_width
            else:
                self.media_type = TapeType.TUBE
                self.media_width = args.tube_width
            Printer = ptouch.__main__.PRINTER_TYPES[self.printer]
            dpi = Printer.RESOLUTION_DPI
            height = Template.get_printable_height(
                Printer, self.media_type, self.media_width)
            height_mm = px_to_mm(height, dpi)
            width_mm = args.length
            width = mm_to_px(width_mm, dpi)
            doc = ezdxf.new('R2000', units=MM)
            doc.appids.new('ptouch-template')
            msp = doc.modelspace()
            rectangle = msp.add_polyline2d([
                (0, 0),
                (0, height_mm),
                (width_mm, height_mm),
                (width_mm, 0),
                (0, 0),
            ], dxfattribs={'color': 2})
            with ezdxf.entities.xdata.XDataUserDict.entity(
                rectangle, name='options', appid='ptouch-template') as xdata:
                for arg, value in vars(self).items():
                    if value is None:
                        value = ''
                    elif isinstance(value, bool):
                        value = int(value)
                    elif isinstance(value, TapeType):
                        value = value.value
                    xdata[arg] = value
            with ezdxf.entities.xdata.XDataUserDict.entity(
                rectangle, name='template', appid='ptouch-template') as xdata:
                xdata['width'] = width
                xdata['height'] = height
                xdata['dpi'] = dpi
            doc.saveas(path)
        else:
            # Read template
            for arg, value in Template.read_xdata(path, 'options').items():
                if arg in self.__annotations__:
                    if value == '':
                        value = None
                    elif arg == 'media_type':
                        value = TapeType(value)
                    setattr(self, arg, value)


class Template:
    name: str | None
    path: pathlib.Path
    options: Options
    placeholders: dict[str, list[str]]

    width: int
    height: int
    dpi: int

    @staticmethod
    def list_templates(location):
        templates = []
        for filename in sorted(os.listdir(location)):
            if not filename.endswith('.dxf'):
                continue
            name = filename[:-4]
            opt = Options(pathlib.Path(location) / filename)
            templates.append((name, opt))
        return templates

    @staticmethod
    def get_media_class(media_type, media_width):
        if media_type == TapeType.TAPE:
            return ptouch.__main__.TAPE_WIDTHS[media_width]
        else:
            return ptouch.__main__.TUBE_WIDTHS[media_width]

    @staticmethod
    def get_printable_height(Printer, media_type, media_width):
        media_class = Template.get_media_class(media_type, media_width)
        try:
            return Printer.PIN_CONFIGS[media_class].print_pins
        except KeyError:
            raise TemplateError(f'Media width {media_width} is not supported '
                                f'by printer {Printer.__name__}')

    @staticmethod
    def get_all_text_entities(doc):
        for entity in doc.modelspace().query(TEXT_ENTITIES):
            yield entity
        for layout in doc.layouts:
            for entity in layout.query(TEXT_ENTITIES):
                yield entity
        for block_layout in doc.blocks:
            if (
                not block_layout.block.is_anonymous
                and not block_layout.block.is_xref
            ):
                for entity in block_layout.query(TEXT_ENTITIES):
                    yield entity

    @staticmethod
    def get_placeholders(path):
        doc = ezdxf.readfile(path)
        placeholders = {}
        for entity in Template.get_all_text_entities(doc):
            for raw_placeholder in re.findall(r'{{.+?}}', entity.dxf.text):
                placeholder = raw_placeholder[2:-2].strip()
                if placeholder not in placeholders:
                    placeholders[placeholder] = []
                placeholders[placeholder].append(raw_placeholder)
        return placeholders

    @staticmethod
    def read_xdata(path, name):
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        for entity in msp:
            if not entity.has_xdata('ptouch-template'):
                continue
            with ezdxf.entities.xdata.XDataUserDict.entity(
                entity, name=name, appid='ptouch-template'
            ) as xdata:
                return dict(xdata)
        raise TemplateError(
            f'{path} does not contain the expected ptouch-template attributes')

    def __init__(self, args: argparse.Namespace):
        if 'name' in args:
            # Create template
            templates = [
                name for name, _ in Template.list_templates(args.templates)]
            if args.name in templates:
                raise TemplateError(f'Template {args.name} already exists')
            self.name = args.name
            self.path = pathlib.Path(args.templates) / self.filename
            self.options = Options(self.path, args)
            self.placeholders = []
            self.dpi = self.Printer.RESOLUTION_DPI
            self.width = mm_to_px(args.length, self.dpi)
            self.height = Template.get_printable_height(
                self.Printer, self.options.media_type,
                self.options.media_width)
        else:
            # Print labels
            for name, opt in Template.list_templates(args.templates):
                if args.template == name:
                    self.name = args.template
                    self.path = pathlib.Path(args.templates) / self.filename
                    self.options = opt
                    break
            else:
                if not os.path.exists(args.template):
                    raise TemplateError(f'File {args.template} does not exist')
                self.name = None
                self.path = pathlib.Path(args.template)
                self.options = Options(self.path)
            self.placeholders = Template.get_placeholders(self.path)
            xdata = Template.read_xdata(self.path, 'template')
            self.width = xdata['width']
            self.height = xdata['height']
            self.dpi = xdata['dpi']

    def __str__(self):
        return self.name if self.name else str(self.path)

    @property
    def Printer(self):
        return ptouch.__main__.PRINTER_TYPES[self.options.printer]

    @property
    def filename(self):
        return f'{self.name}.dxf'

    @property
    def media_class(self):
        return Template.get_media_class(
            self.options.media_type, self.options.media_width)
