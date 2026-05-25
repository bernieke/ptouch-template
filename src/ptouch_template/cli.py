#!/usr/bin/env python

import argparse
import sys

import ptouch.__main__
import xdg_base_dirs

from ptouch_template.ptouch_template import (
    Config,
    PrintError,
    create_template,
    delete_template,
    describe,
    list_templates,
    print_labels,
)
from ptouch_template.template import TemplateError

CONFIG_FILE = xdg_base_dirs.xdg_config_home() / 'ptouch-template.ini'

PRINT_HELP = 'Print one or more labels from a template'
CREATE_HELP = 'Create a template'
LIST_HELP = 'List available templates'
DESCRIBE_HELP = 'List the print options and placeholders in a template'
DELETE_HELP = 'Delete a template'
SHOW_CONFIG_HELP = 'Show the current configuration'
SAVE_CONFIG_HELP = ("Save the current arguments to the config file, "
                    "so you won't have to specify them next time")

PRINT_DESCRIPTION = f"""{PRINT_HELP}.

Pass the name of the template or a path to a DXF file saved from a template,
and, if the template has placeholders, one of:
* --csv: a path to a CSV file with a row per label and the columns named after
  the placeholders
* one or more contents:
    - for templates with a single placeholder each string prints a label
    - for templates with multiple placeholders a series of <placeholder>=<text>
      strings (you can only print a single label with multiple placeholders)
"""

CREATE_DESCRIPTION = f"""{CREATE_HELP}.

The tape or tube width must be provided.
The configured printer will then determine the height of the printable area.

Also the desired length of the label must be provided.

This area will be marked in the template with a (not printed) yellow rectangle.

There will be a blank margin to either side of this rectangle.
When printing with cutting it can be no less than, and defaults to, 2mm.
When printing with --no-cut or --mark it can be less, or even zero.

Default cutting behavior:
* A half cut will be made between labels.
  The --full-cut, --no-cut, and --mark flags can be used to change this.
* A final full cut will be made.
  Add the --no-feed flag to replace the cut with a vertical 1px line.
  This flag requires either --no-cut or --mark to be provided as well.
  You will then need to physically remove the tape and cut it manually.

Tape notes:
* Non-laminated tapes cannot be half cut, so always use one of the cut options
  --full-cut, --no-cut, or --mark
* It is recommended to use --no-cut with heatshrink tapes to save the cutter
* And to not half cut extra strong adhesive tapes to avoid adhesive buildup

When editing the template:
* Do not remove the yellow rectangle, and do not put anything outside of it
* Add "{{<placeholder>}}" texts to be replaced during printing
  (fi. "{{first_name}} {{last_name}}", without the surrounding double quotes)
* If you want to be able to replace placeholers with multi-line texts,
  make sure to use a multi-line DXF text (MTEXT instead of TEXT)
"""

PRINTERS = list(ptouch.__main__.PRINTER_TYPES.keys())
TAPE_WIDTHS = list(ptouch.__main__.TAPE_WIDTHS.keys())
TUBE_WIDTHS = list(ptouch.__main__.TUBE_WIDTHS.keys())

# Labels with a width smaller than this cannot be printed with a full cut
MIN_FULL_CUT_WIDTH = {
    'P900W': 18.06,
}


def error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def main():
    config = Config(CONFIG_FILE)

    # Create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--debug', '-d', action='store_true',
        help='Create images instead of printing them')

    def add_argument(*args, value, **kwargs):
        required = kwargs.pop('required', not value)
        parser.add_argument(*args, required=required, default=value, **kwargs)

    add_argument(
        '--templates', '-t', value=config.templates, help='Template folder')

    # Add connection arguments
    conn_group = parser.add_mutually_exclusive_group(
        required=not config.host and not config.usb)
    conn_group.add_argument(
        '--host', '-H', metavar='IP', default=config.host,
        help='Printer IP address for network connection')
    conn_group.add_argument(
        '--usb', nargs='?', const=True, default=config.usb, metavar='URI',
        help=('Use USB connection. Optional URI: '
              'usb://[vendor:]product[/serial] '
              '(e.g., usb://:0x2086/A1B2C3D4E5)'))

    # Add printer arguments
    add_argument(
        '--printer', '-p', value=config.printer, help='Printer model',
        choices=PRINTERS)

    # Add printer option arguments
    add_argument(
        '--no-compression', value=config.no_compression, action='store_true',
        required=False, help='Disable TIFF compression')

    # Add command subparsers
    subparsers = parser.add_subparsers(
        dest='command', required=True, title='Command')

    print_parser = subparsers.add_parser(
        'print', help=PRINT_HELP, description=PRINT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    print_parser.set_defaults(func=print_labels)
    print_parser.add_argument(
        'template',
        help=('Name of a template '
              'or a path to a DXF file saved from a template'))
    print_parser.add_argument(
        'contents', nargs='*',
        help=('Mutually exclusive with --csv. '
              'When the template has no placeholders: do not pass contents. '
              'When the template has just one placeholder: '
              'pass one string per label. '
              'When the template has multiple placeholders: '
              'pass one "<placeholder>=<text>" string per placeholder '
              '(you can only print one label with multiple placeholders, '
              'use --csv instead of contents to print multiple labels).'))
    print_parser.add_argument(
        '--csv', type=argparse.FileType('r'),
        help=('Path to a CSV file with a row per label '
              'and columns named after placeholders'))
    print_parser.add_argument(
        '--copies', '-c', type=int, default=1, metavar='N',
        help='Number of copies to print (default: 1)')
    print_parser.add_argument(
        '--no-snmp-check', '-n', action='store_true',
        help='Do not check installed media width with SNMP')
    print_parser.add_argument(
        '--ignore-extra-columns', action='store_true',
        help='Ignore extra columns in CSV files')

    create_parser = subparsers.add_parser(
        'create', help=CREATE_HELP, description=CREATE_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    create_parser.set_defaults(func=create_template)
    create_parser.add_argument('name', help='Name of the template')
    create_parser.add_argument(
        '--overwrite', action='store_true',
        help='Overwrite the template if it already exists')
    # Tape or tube (mutually exclusive)
    media_group = create_parser.add_mutually_exclusive_group(required=True)
    media_group.add_argument(
        '--tape-width', '-t', type=float, choices=TAPE_WIDTHS,
        help='Laminated tape width in mm',
    )
    media_group.add_argument(
        '--tube-width', '-T', type=float, choices=TUBE_WIDTHS,
        help=('Heat shrink tube diameter in mm '
              '(2:1:\xa05.8/8.8/11.7/17.7/23.6, '
              '3:1:\xa05.2/9.0/11.2/21.0/31.0)'))
    create_parser.add_argument(
        '--length', '-l', type=float, required=True, help='Label length in mm')
    # Print options
    create_parser.add_argument(
        '--high-resolution', action='store_true',
        help='Enable high resolution mode')
    create_parser.add_argument(
        '--margin', '-m', type=float, metavar='MM', default=2,
        help='Margin in mm (default, and minimum when cutting: 2mm)')
    create_parser.add_argument(
        '--no-feed', action='store_true',
        help=('Do not feed and cut after the last label '
              '(requires either --no-cut or --mark)'))
    # Cut options (mutually exclusive)
    cut_group = create_parser.add_mutually_exclusive_group()
    cut_group.add_argument(
        '--full-cut', action='store_true',
        help=('Use full cuts between labels instead of half cuts '
              '(recommended for strong adhesive tapes)'))
    cut_group.add_argument(
        '--no-cut', action='store_true',
        help='Do not cut at all between labels (e.g. for patch panels)')
    cut_group.add_argument(
        '--mark', action='store_true',
        help='Add a vertical line between labels instead of cutting')

    list_parser = subparsers.add_parser(
        'list', help=LIST_HELP, description=LIST_HELP)
    list_parser.set_defaults(func=list_templates)
    list_parser.add_argument(
        '--only-names', action='store_true',
        help='Only print the names of the templates')

    describe_parser = subparsers.add_parser(
        'describe', help=DESCRIBE_HELP, description=DESCRIBE_HELP)
    describe_parser.set_defaults(func=describe)
    describe_parser.add_argument('template', help='Name of the template')

    show_config_parser = subparsers.add_parser(
        'show-config', help=SHOW_CONFIG_HELP, description=SHOW_CONFIG_HELP)
    show_config_parser.set_defaults(func=config.print)

    save_config_parser = subparsers.add_parser(
        'save-config', help=SAVE_CONFIG_HELP, description=SAVE_CONFIG_HELP)
    save_config_parser.set_defaults(func=config.save)

    delete_parser = subparsers.add_parser(
        'delete', help=DELETE_HELP, description=DELETE_HELP)
    delete_parser.set_defaults(func=delete_template)
    delete_parser.add_argument('name', help='Name of the template to delete')

    # Extra argument validation
    args = parser.parse_args()
    if args.command == 'print':
        if args.copies < 1:
            error('--copies must be at least 1')
        if args.csv and args.contents:
            error('--csv and contents are mutually exclusive')
    elif args.command == 'create':
        if args.no_feed and not (args.no_cut or args.mark):
            error('--no-feed requires either --no-cut or --mark')
        if not args.no_cut and not args.mark and args.margin < 2:
            error('--margin must be at least 2mm when cutting')
        if (
            args.full_cut
            and args.length < MIN_FULL_CUT_WIDTH.get(args.printer, 0)
        ):
            error(f'--full-cut requires a label length of at least '
                  f'{MIN_FULL_CUT_WIDTH[args.printer]}mm for {args.printer}')

    # Execute command
    try:
        args.func(args)
    except (TemplateError, PrintError) as e:
        error(e.args[0])


if __name__ == '__main__':
    main()
