# ptouch-template

ptouch-template is a CLI application which facilitates creation of DXF ptouch templates, and the printing from them.

It is built on top of the [ezdxf](https://github.com/mozman/ezdxf) and [ptouch](https://github.com/nbuchwitz/ptouch) libraries.

And also requires the optional ezdxf dependencies [Pillow](https://github.com/python-pillow/Pillow) and [matplotlib](https://github.com/matplotlib/matplotlib).


# Installation

```Bash
uv tool install 'ptouch-template[usb,snmp]'
```

The usb dependency is required to print over usb.

The snmp dependency allows the script to read the installed tape width to prevent you from printing with a template for a different size tape. Requires the printer to have networking.

You can print over usb, and still use the SNMP link to verify the tape width.

I've noticed that the heathshrink tube 3:1 21mm tape mistakenly reports 24mm tape width over SNMP. If that happens you can pass `--no-snmp-check` to disable the check during printing.


# Usage

```Bash
> ptouch-template --help
usage: ptouch-template [-h] [--debug] [--templates TEMPLATES] [--host IP |
                       --usb [URI]]
                       [--printer {E550W,P750W,P900,P900W,P910BT,P950NW}]
                       [--no-compression]
                       {print,create,edit,list,describe,show-config,save-config,delete} ...

options:
  -h, --help            show this help message and exit
  --debug, -d           Create images instead of printing them
  --templates, -t TEMPLATES
                        Template folder
  --host, -H IP         Printer IP address for network connection
  --usb [URI]           Use USB connection. Optional URI:
                        usb://[vendor:]product[/serial] (e.g.,
                        usb://:0x2086/A1B2C3D4E5)
  --printer, -p {E550W,P750W,P900,P900W,P910BT,P950NW}
                        Printer model
  --no-compression      Disable TIFF compression

Command:
  {print,create,edit,list,describe,show-config,save-config,delete}
    print               Print one or more labels from a template
    create              Create a template
    edit                Edit template options
    list                List available templates
    describe            List the print options and placeholders in a template
    show-config         Show the current configuration
    save-config         Save the current arguments to the config file, so you
                        won't have to specify them next time
    delete              Delete a template
```

```Bash
> ptouch-template create --help
usage: ptouch-template create [-h] (--tape-width {3.5,6,9,12,18,24,36} |
                              --tube-width {5.8,8.8,11.7,17.7,23.6,5.2,9.0,11.2,21.0,31.0})
                              --length LENGTH [--high-resolution]
                              [--margin MM] [--no-feed] [--full-cut |
                              --no-cut | --mark]
                              name

Create a template.

The tape or tube width must be provided.
The configured printer will then determine the height of the printable area.

Also the desired length of the label must be provided, in mm or "auto".

For a fixed length the printable area is marked in the template
with a (not printed) yellow rectangle.
For "auto" only the left edge is marked with a yellow vertical line.

There will be a blank margin to either side of the printable area.
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
* Do not remove the yellow rectangle or guide line
* For a fixed length do not put anything outside of the rectangle
* For "auto" length keep everything to the right of the guide line
* Add "{<placeholder>}" texts to be replaced during printing
  (fi. "{first_name} {last_name}", without the surrounding double quotes)
* If you want to be able to replace placeholers with multi-line texts,
  make sure to use a multi-line DXF text (MTEXT instead of TEXT)

positional arguments:
  name                  Name of the template

options:
  -h, --help            show this help message and exit
  --tape-width, -t {3.5,6,9,12,18,24,36}
                        Laminated tape width in mm
  --tube-width, -T {5.8,8.8,11.7,17.7,23.6,5.2,9.0,11.2,21.0,31.0}
                        Heat shrink tube diameter in mm
                        (2:1: 5.8/8.8/11.7/17.7/23.6,
                        3:1: 5.2/9.0/11.2/21.0/31.0)
  --length, -l LENGTH   Label length in mm or "auto"
  --high-resolution     Enable high resolution mode
  --margin, -m MM       Margin in mm (default, and minimum when cutting: 2mm)
  --no-feed             Do not feed and cut after the last label (requires
                        either --no-cut or --mark)
  --full-cut            Use full cuts between labels instead of half cuts
                        (recommended for strong adhesive tapes)
  --no-cut              Do not cut at all between labels (e.g. for patch
                        panels)
  --mark                Add a vertical line between labels instead of cutting
```

```Bash
> ptouch-template edit --help
usage: ptouch-template edit [-h] --length LENGTH [--high-resolution]
                            [--margin MM] [--no-feed] [--full-cut | --no-cut |
                            --mark]
                            name

Edit template options.

Change the options of an existing template while keeping its tape/tube width
and its content (texts and placeholders).

Options are applied exactly as for "create": any option not given reverts to
its default (e.g. omitting a cut option restores half cuts).

positional arguments:
  name                 Name of the template to edit

options:
  -h, --help           show this help message and exit
  --length, -l LENGTH  Label length in mm or "auto"
  --high-resolution    Enable high resolution mode
  --margin, -m MM      Margin in mm (default, and minimum when cutting: 2mm)
  --no-feed            Do not feed and cut after the last label (requires
                       either --no-cut or --mark)
  --full-cut           Use full cuts between labels instead of half cuts
                       (recommended for strong adhesive tapes)
  --no-cut             Do not cut at all between labels (e.g. for patch
                       panels)
  --mark               Add a vertical line between labels instead of cutting
```

```Bash
> ptouch-template print --help
usage: ptouch-template print [-h] [--csv CSV] [--copies N] [--no-snmp-check]
                             template [contents ...]

Print one or more labels from a template.

Pass the name of the template or a path to a DXF file saved from a template,
and, if the template has placeholders, one of:
* --csv: a path to a CSV file with a row per label and the columns named after
  the placeholders
* one or more contents:
    - for templates with a single placeholder each string prints a label
    - for templates with multiple placeholders a series of <placeholder>=<text>
      strings (you can only print a single label with multiple placeholders)

positional arguments:
  template             Name of a template or a path to a DXF file saved from a
                       template
  contents             Mutually exclusive with --csv. When the template has no
                       placeholders: do not pass contents. When the template
                       has just one placeholder: pass one string per label.
                       When the template has multiple placeholders: pass one
                       "<placeholder>=<text>" string per placeholder (you can
                       only print one label with multiple placeholders, use
                       --csv instead of contents to print multiple labels).

options:
  -h, --help           show this help message and exit
  --csv CSV            Path to a CSV file with a row per label and columns
                       named after placeholders
  --copies, -c N       Number of copies to print (default: 1)
  --no-snmp-check, -n  Do not check installed media width with SNMP
```


# Development

Setup the virtualenv:
```Bash
uv sync --all-extras --all-groups
```

Install the project:
```Bash
uv tool install --editable '.[usb,snmp]'
```

Build and publish:
```Bash
uv version <version>
git commit
git tag v<version>
git push
git push --tags
rm -rf dist
uv build
uv publish --token <token>
```
