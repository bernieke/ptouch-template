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
    edit_template,
    list_templates,
    print_labels,
)
from ptouch_template.template import CUT_OPTIONS, TemplateError

CONFIG_FILE = xdg_base_dirs.xdg_config_home() / 'ptouch-template.ini'

PRINT_HELP = 'Print one or more labels from a template'
CREATE_HELP = 'Create a template'
EDIT_HELP = 'Edit template options'
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

The options the template was created with can be overridden for this print,
without changing the template.
"""

CREATE_DESCRIPTION = f"""{CREATE_HELP}.

The tape or tube width must be provided.
The configured printer will then determine the height of the printable area.

Also the desired length of the label must be provided, in mm or "auto".

For a fixed length the printable area is marked in the template
with a (not printed) yellow rectangle.
For "auto" only the left edge is marked with a yellow vertical line.

There will be a blank margin to either side of the printable area.
When printing with cutting it can be no less than, and defaults to, 2mm.
With --cut none or --cut mark it can be less, or even zero.

Cutting behavior:
* --cut half makes a half cut between labels, --cut full a full cut,
  --cut none does not cut at all, and --cut mark prints a vertical line
  between the labels instead of cutting.
* --feed true feeds and cuts the tape after the last label.
  With --feed false the tape is left in the printer, is not cut,
  and a vertical 1px line marks where to cut.
  You will then need to remove the tape and cut it manually.

Tape notes:
* Non-laminated tapes cannot be half cut, so always use --cut full, none, or
  mark
* It is recommended to use --cut none with heatshrink tapes to save the cutter
* And to not half cut extra strong adhesive tapes to avoid adhesive buildup

Defaults: --cut half, --feed true, --margin 2mm, --high-resolution false.

When editing the template:
* Do not remove the yellow rectangle or guide line
* For a fixed length do not put anything outside of the rectangle
* For "auto" length keep everything to the right of the guide line
* Add "{{<placeholder>}}" texts to be replaced during printing
  (fi. "{{first_name}} {{last_name}}", without the surrounding double quotes)
* If you want to be able to replace placeholers with multi-line texts,
  make sure to use a multi-line DXF text (MTEXT instead of TEXT)
"""

EDIT_DESCRIPTION = f"""{EDIT_HELP}.

Change the options of an existing template while keeping its tape/tube width
and its content (texts and placeholders).

Options are applied exactly as for "create": any option not given reverts to
its default (e.g. omitting --cut restores half cuts).
"""

PRINTERS = list(ptouch.__main__.PRINTER_TYPES.keys())
TAPE_WIDTHS = list(ptouch.__main__.TAPE_WIDTHS.keys())
TUBE_WIDTHS = list(ptouch.__main__.TUBE_WIDTHS.keys())


def error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = str(val).lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError('invalid truth value {!r}'.format(val))


def length(value):
    if value == 'auto':
        return 'auto'
    try:
        value = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('Length must be a number or "auto"')
    if value <= 0:
        raise argparse.ArgumentTypeError('Length must be greater than 0')
    return value


def main():
    config = Config(CONFIG_FILE)

    # Create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--debug', '-d', action='store_true',
        help='Create images instead of printing them')

    def add_options(subparser, override=False):
        # The options stored in the template, print takes them as overrides
        if override:
            subparser = subparser.add_argument_group(
                'Template options',
                'Override the options the template was created with')
        subparser.add_argument(
            '--length', '-l', type=length, metavar='{MM|auto}',
            required=not override, default=None,
            help='Label length in mm or "auto"')
        subparser.add_argument(
            '--cut', choices=CUT_OPTIONS, default=None if override else 'half',
            help=('Separate the labels with half cuts, full cuts, nothing, '
                  'or a printed line'))
        subparser.add_argument(
            '--feed', type=strtobool, metavar='{true,false}',
            default=None if override else True,
            help='Feed and cut the tape after the last label')
        subparser.add_argument(
            '--margin', '-m', type=float, metavar='MM',
            default=None if override else 2,
            help='Margin in mm (minimum 2mm when cutting)')
        subparser.add_argument(
            '--high-resolution', type=strtobool, metavar='{true,false}',
            default=None if override else bool(config.high_resolution),
            help='Enable high resolution mode')

    parser.add_argument(
        '--templates', '-t', default=config.templates,
        required=not config.templates, help='Template folder')

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
    parser.add_argument(
        '--printer', '-p', default=config.printer,
        required=not config.printer, help='Printer model', choices=PRINTERS)

    # Add printer option arguments
    parser.add_argument(
        '--no-compression', default=config.no_compression,
        action='store_true', help='Disable TIFF compression')

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
    add_options(print_parser, override=True)

    create_parser = subparsers.add_parser(
        'create', help=CREATE_HELP, description=CREATE_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    create_parser.set_defaults(func=create_template)
    create_parser.add_argument('name', help='Name of the template')
    create_parser.add_argument(
        '--overwrite', action='store_true',
        help='Overwrite the template if it already exists')
    edit_parser = subparsers.add_parser(
        'edit', help=EDIT_HELP, description=EDIT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    edit_parser.set_defaults(func=edit_template)
    edit_parser.add_argument('name', help='Name of the template to edit')
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
    for subparser in [create_parser, edit_parser]:
        add_options(subparser)

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

    # Execute command
    try:
        args.func(args)
    except (TemplateError, PrintError) as e:
        error(e.args[0])


if __name__ == '__main__':
    main()
