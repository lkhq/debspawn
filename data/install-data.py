#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2021 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: LGPL-3.0-or-later

import os
import sys
import shutil
from pathlib import Path
try:
    import pkgconfig
except ImportError:
    print(('Unable to import pkgconfig. Please install the module '
           '(apt install python3-pkgconfig or pip install pkgconfig) '
           'to continue.'))
    sys.exit(4)


class Installer:
    def __init__(self, prefix: str = None):
        if not prefix:
            prefix = os.environ.get('DESTDIR')
        if not prefix:
            prefix = os.environ.get('PREFIX')
        if not prefix:
            prefix = '/'
        self._prefix = prefix

    def install(self, src, dst):
        if dst.startswith('/'):
            dst = dst[1:]
        dst_full = os.path.join(self._prefix, dst, os.path.basename(src))
        Path(os.path.dirname(dst_full)).mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copy(src, dst_full)
        os.chmod(dst_full, 0o755)
        print('{}\t{}'.format(src, dst_full))


print('Installing debspawn system configuration.')
thisfile = __file__
if not os.path.isabs(thisfile):
    thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))
os.chdir(os.path.dirname(thisfile))

if not pkgconfig.installed('systemd', '>= 240'):
    print('Systemd is not installed on this system. Please make systemd available to continue.')
    sys.exit(4)

inst = Installer()
tmpfiles_dir = pkgconfig.variables('systemd')['tmpfiles_dir']
inst.install('tmpfiles.d/debspawn.conf', tmpfiles_dir)
