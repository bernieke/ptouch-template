#!/usr/bin/env python

import ezdxf
import ezdxf.entities.xdata

OPTIONS = ['printer', 'media_type', 'media_width', 'high_resolution',
           'margin', 'cut', 'feed']


def upgrade(path):
    doc = ezdxf.readfile(path)
    for entity in doc.modelspace():
        if entity.has_xdata('ptouch-template'):
            break
    else:
        raise ValueError(f'{path} is not a ptouch template')
    with ezdxf.entities.xdata.XDataUserDict.entity(
        entity, name='options', appid='ptouch-template'
    ) as options:
        full_cut = options.pop('full_cut', 0)
        no_cut = options.pop('no_cut', 0)
        mark = options.pop('mark', 0)
        no_feed = options.pop('no_feed', 0)
        if full_cut:
            cut = 'full'
        elif no_cut:
            cut = 'none'
        elif mark:
            cut = 'mark'
        else:
            cut = 'half'
        values = dict(options, cut=cut, feed=int(not no_feed))
        options.clear()
        for option in OPTIONS:
            options[option] = values[option]
    with ezdxf.entities.xdata.XDataUserDict.entity(
        entity, name='template', appid='ptouch-template'
    ) as template:
        template['version'] = 2
    doc.saveas(path)
