#!/usr/bin/env python

import argparse
import configparser
import csv
import io
import math
import pathlib
import socket
import sys
import time

import PIL
import ezdxf
import ezdxf.addons.drawing.config
import ezdxf.addons.drawing.layout
import ezdxf.addons.drawing.matplotlib
import ptouch
import matplotlib.pyplot

from ptouch_template.template import Template, px_to_in, px_to_mm, mm_to_px

try:
    from snmp import Engine, SNMPv2c
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False

TAPE_WIDTH_OID = '1.3.6.1.2.1.43.8.2.1.12.1.1'

MM = ezdxf.addons.drawing.layout.Units.mm

config = ezdxf.addons.drawing.config.Configuration(
    background_policy=ezdxf.addons.drawing.config.BackgroundPolicy.WHITE,
    color_policy=ezdxf.addons.drawing.config.ColorPolicy.BLACK,
    min_lineweight=300 / 360,
    lineweight_scaling=0.0,
)
settings = ezdxf.addons.drawing.layout.Settings(
    page_alignment=ezdxf.addons.drawing.layout.PageAlignment.BOTTOM_LEFT)

# ptouch TapeConfig fixes for PTP900W
PIN_CONFIGS = ptouch.printers.PTP900W.PIN_CONFIGS
PIN_CONFIGS[ptouch.tape.Tape6mm].left_pins = 256
PIN_CONFIGS[ptouch.tape.Tape6mm].right_pins = 240
PIN_CONFIGS[ptouch.tape.Tape12mm].left_pins = 213
PIN_CONFIGS[ptouch.tape.Tape12mm].right_pins = 197
PIN_CONFIGS[ptouch.tape.Tape18mm].left_pins = 168
PIN_CONFIGS[ptouch.tape.Tape18mm].right_pins = 158
PIN_CONFIGS[ptouch.tape.Tape24mm].left_pins = 128
PIN_CONFIGS[ptouch.tape.Tape24mm].right_pins = 112
PIN_CONFIGS[ptouch.tape.Tape36mm].left_pins = 58
PIN_CONFIGS[ptouch.tape.Tape36mm].right_pins = 48


class PrintError(Exception):
    pass


class Config:
    printer: str | None = None
    host: str | None = None
    usb: str | bool | None = None
    high_resolution: bool | None = None
    no_compression: bool | None = None
    templates: str | None = None

    def __init__(self, config_file: pathlib.Path):
        self._config = configparser.ConfigParser()
        if config_file.exists():
            self._config.read(config_file)
        # String arguments
        for arg in ['printer', 'host', 'templates']:
            setattr(self, arg, self._config.get('DEFAULT', arg, fallback=None))
        # Boolean arguments
        for arg in ['high_resolution', 'no_compression']:
            value = self._config.getboolean('DEFAULT', arg, fallback=None)
            setattr(self, arg, value)
        # Boolean or string arguments
        for arg in ['usb']:
            try:
                value = self._config.getboolean('DEFAULT', arg, fallback=None)
            except ValueError:
                value = self._config.get('DEFAULT', arg)
            setattr(self, arg, value)

    def save(self, args: argparse.Namespace):
        self._config['DEFAULT'] = {}
        for arg in ['printer', 'host', 'usb', 'templates']:
            value = getattr(args, arg)
            if value is not None:
                if isinstance(value, bool):
                    value = 'true' if value else 'false'
                self._config['DEFAULT'][arg] = value
        with self.config_file.open('w') as f:
            self._config.write(f)

    def print(self, args):
        print('Setting: value (commandline override)')
        print('─────────────────────────────────────')
        for arg, value in vars(self).items():
            args_value = getattr(args, arg, None)
            if arg in ['_config'] or (value is None and args_value is None):
                continue
            if value is None:
                value = '-'
            arg_str = f'{arg}: {value}'
            if not args_value == value:
                arg_str += f' ({args_value})'
            print(arg_str)


def get_installed_media_width(host):
    ip = socket.gethostbyname(host)
    engine = Engine()
    manager = engine.Manager(ip, version=SNMPv2c, community=b'public')
    response = manager.get(TAPE_WIDTH_OID)
    return float(response[0].value.data.decode().split('mm')[0])


def create_label(template, contents):
    # Contents may be:
    # * None for no placeholders
    # * str for single placeholder
    # * dict for multiple placeholders
    if (
        (not contents and template.placeholders)
        or (contents and not template.placeholders)
        or (isinstance(contents, dict)
            and not len(contents) == len(template.placeholders))
        or (isinstance(contents, str) and not len(template.placeholders) == 1)
    ):
        raise PrintError('Mismatch in number of placeholders and contents')

    def replace(entity, raw_placeholders, value):
        for raw_placeholder in raw_placeholders:
            if raw_placeholder in entity.dxf.text:
                entity.dxf.text = entity.dxf.text.replace(
                    raw_placeholder, value)

    doc = ezdxf.readfile(template.path)
    msp = doc.modelspace()
    # Validate contents keys
    if isinstance(contents, dict):
        if not contents.keys() == template.placeholders.keys():
            raise PrintError('Mismatch in placeholders and contents key names')
    # Replace placeholders
    for entity in Template.get_all_text_entities(doc):
        for placeholder, raw_placeholders in template.placeholders.items():
            if isinstance(contents, dict):
                value = contents[placeholder]
            else:
                value = contents
            replace(entity, raw_placeholders, value)
    # Remove the yellow rectangle before rendering the image
    for entity in msp:
        if entity.has_xdata('ptouch-template'):
            msp.delete_entity(entity)
            break
    # Render to image
    context = ezdxf.addons.drawing.RenderContext(doc)
    width_in = px_to_in(template.width, template.dpi)
    height_in = px_to_in(template.height, template.dpi)
    figure = matplotlib.pyplot.figure(figsize=(width_in, height_in))
    axis = figure.add_axes([0, 0, 1, 1])
    backend = ezdxf.addons.drawing.matplotlib.MatplotlibBackend(axis)
    frontend = ezdxf.addons.drawing.Frontend(context, backend, config=config)
    frontend.draw_layout(msp, finalize=False)
    axis.set_xlim(0, px_to_mm(template.width, template.dpi))
    axis.set_ylim(0, px_to_mm(template.height, template.dpi))
    axis.set_axis_off()
    with io.BytesIO() as f:
        figure.savefig(
            f, dpi=template.dpi, format='png', bbox_inches=None, pad_inches=0)
        f.seek(0)
        image = PIL.Image.open(f, formats=['png']).copy()
        matplotlib.pyplot.close(figure)
        return image


def create_blank(template):
    width = mm_to_px(template.options.margin * 2, template.dpi)
    return PIL.Image.new(
        mode='RGB', size=(width, template.height), color=(255, 255, 255))


def create_mark(template):
    image = create_blank(template)
    middle = mm_to_px(template.options.margin, template.dpi)
    PIL.ImageDraw.Draw(image).line(
        [(middle, 0), (middle, template.height)], fill=0, width=2)
    return image


def print_labels(args):
    template = Template(args)

    # Create connection
    if args.usb is True:
        connection = ptouch.ConnectionUSB()
    elif args.usb:
        try:
            vendor_id, product_id, serial = ptouch.parse_usb_uri(args.usb)
            connection = ptouch.ConnectionUSB(
                vendor_id=vendor_id, product_id=product_id, serial=serial)
        except ValueError as e:
            raise PrintError(f'Error: {e}')
    else:
        connection = ptouch.ConnectionNetwork(args.host)

    # Create printer
    if not args.debug:
        printer = template.Printer(
            connection=connection, use_compression=not args.no_compression,
            high_resolution=template.options.high_resolution)

    # Check media width if possible
    installed_media_width = None
    if args.host and not args.no_snmp_check and SNMP_AVAILABLE:
        installed_media_width = get_installed_media_width(args.host)
        if not installed_media_width == template.options.media_width:
            raise PrintError(
                f'Installed media width {installed_media_width} does not '
                f'match template media width {template.options.media_width}')

    # Build contents list
    if args.csv:
        contents = list(csv.DictReader(args.csv))
        args.csv.close()
    elif not template.placeholders:
        contents = [None]
    elif len(template.placeholders) == 1:
        contents = args.contents if args.contents else [None]
    else:
        try:
            contents = [{
                x.split('=')[0]: x.split('=', 1)[1]
                for x in args.contents
            }]
        except IndexError:
            raise PrintError(
                'Could not parse contents, when more than one argument '
                'it needs to be a list of <key>=<value> pairs')
    contents = contents * args.copies

    # Create print queue [(image, feed, auto_cut, half_cut), ...]
    # With:
    #   feed: feed and cut after printing
    #   auto_cut: make a full cut between labels
    #   half_cut: make a half cut between labels
    # Only one of auto_cut or half_cut may be True,
    # and neither affects the last label printed
    print_queue = []

    # Prepare the image and flags for the no cutting options
    if template.options.no_cut or template.options.mark:
        n = len(contents)
        if template.options.margin:
            if template.options.no_cut:
                filler = create_blank(template)
            else:
                filler = create_mark(template)
            total_width = template.width * n + filler.width * (n - 1)
            if template.options.no_feed:
                total_width += math.ceil(filler.width / 2)
            width_with_filler = template.width + filler.width
        else:
            total_width = template.width * n
            width_with_filler = template.width
        image = PIL.Image.new(
            'RGB', size=(total_width, template.height), color=(255, 255, 255))
        print_queue.append((image, not template.options.no_feed, False, False))

    for n, _contents in enumerate(contents, start=1):
        is_first = (n == 1)
        is_last = (n == len(contents))
        label = create_label(template, _contents)

        # When not cutting we concatenate the labels with fillers inbetween
        if template.options.no_cut or template.options.mark:
            # For --mark draw a 2px line between labels if no margin (filler)
            if not template.options.margin and template.options.mark:
                if not is_first:
                    PIL.ImageDraw.Draw(label).line(
                        [(0, 0), (0, label.height)], fill=0, width=1)
                if not is_last:
                    PIL.ImageDraw.Draw(label).line(
                        [(label.width - 1, 0),
                         (label.width - 1, label.height)],
                        fill=0, width=1)
            # And the label to the image
            start = width_with_filler * (n - 1)
            image.paste(label, (start, 0))
            if is_last:
                # If --no-feed draw a 1px cut line at the end
                if template.options.no_feed:
                    PIL.ImageDraw.Draw(image).line(
                        [(image.width - 1, 0),
                         (image.width - 1, image.height)],
                        fill=0, width=1)
            elif template.options.margin:
                # Add the filler
                image.paste(filler, (start + template.width, 0))
            continue

        # Otherwise we add the label to the print queue with the proper flags
        feed = is_last
        auto_cut = template.options.full_cut
        half_cut = not auto_cut
        print_queue.append((label, feed, auto_cut, half_cut))

    # When not cutting we pass the default margin (print won't accept less)
    if template.options.no_cut or template.options.mark:
        margin_mm = 2
    else:
        margin_mm = template.options.margin

    # Print the labels
    i = 0
    for image, feed, auto_cut, half_cut in print_queue:
        i += 1
        if args.debug:
            name = str(i)
            if feed:
                name += ' feed'
            if auto_cut:
                name += ' auto_cut'
            if half_cut:
                name += ' half_cut'
            image.save(f'{name}.png')
        else:
            printer.print(
                label=ptouch.Label(image, template.media_class),
                margin_mm=margin_mm,
                high_resolution=template.options.high_resolution,
                feed=feed,
                auto_cut=auto_cut,
                half_cut=half_cut,
            )
            time.sleep(2)  # Avoid libusb segmentation fault during large batch


def create_template(args):
    Template(args)


def list_templates(args):
    if not args.templates:
        print('No template location configured', file=sys.stderr)
        sys.exit(1)
    for name, opt in Template.list_templates(args.templates):
        line = name
        if not args.only_names:
            line += f' ({opt.printer} {opt.media_width}mm)'
        print(line)


def delete_template(args):
    if not args.templates:
        print('No template location configured', file=sys.stderr)
        sys.exit(1)
    templates = {
        name: pathlib.Path(args.templates) / f'{name}.dxf'
        for name, _ in Template.list_templates(args.templates)
    }
    if args.name not in templates:
        raise PrintError(f'Template {args.name} does not exist')
    templates[args.name].unlink()


def describe(args):
    template = Template(args)
    print('OPTIONS')
    print('───────')
    for option, value in vars(template.options).items():
        print(f'{option}: {value}')
    print()
    print('PLACEHOLDERS')
    print('────────────')
    for placeholder in template.placeholders:
        print(placeholder)
