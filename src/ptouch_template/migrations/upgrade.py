#!/usr/bin/env python

import argparse
import importlib
import pathlib
import sys

import ezdxf
import ezdxf.entities.xdata

from ptouch_template.template import SCHEMA_VERSION


def read_version(path):
    doc = ezdxf.readfile(path)
    for entity in doc.modelspace():
        if not entity.has_xdata('ptouch-template'):
            continue
        with ezdxf.entities.xdata.XDataUserDict.entity(
            entity, name='template', appid='ptouch-template'
        ) as xdata:
            return xdata.get('version', 1)
    return None


def main():
    parser = argparse.ArgumentParser(
        description=f'Upgrade templates to schema version {SCHEMA_VERSION}')
    parser.add_argument('paths', nargs='+', type=pathlib.Path,
                        help='Templates to upgrade')
    args = parser.parse_args()
    for path in args.paths:
        try:
            version = read_version(path)
        except (IOError, ezdxf.DXFError) as e:
            print(e, file=sys.stderr)
            continue
        if version is None:
            print(f'{path} is not a ptouch template', file=sys.stderr)
            continue
        if version > SCHEMA_VERSION:
            print(f'{path} is schema version {version}, '
                  f'but {SCHEMA_VERSION} is required', file=sys.stderr)
            continue
        if version == SCHEMA_VERSION:
            continue
        while version < SCHEMA_VERSION:
            modpath = f'ptouch_template.migrations.v{version}_to_{version + 1}'
            module = importlib.import_module(modpath)
            module.upgrade(path)
            version += 1
        print(f'{path} upgraded to schema version {SCHEMA_VERSION}')


if __name__ == '__main__':
    main()
