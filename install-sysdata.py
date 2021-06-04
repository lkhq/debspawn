#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2021 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: LGPL-3.0-or-later

#
# This is a helper script to install additional configuration and documentation into
# system locations, which Python's setuptools and pip will not usually let us install.
#

import os
import sys
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
try:
    import pkgconfig
except ImportError:
    print()
    print(('Unable to import pkgconfig. Please install the module '
           '(apt install python3-pkgconfig or pip install pkgconfig) '
           'to continue.'))
    print()
    sys.exit(4)
from docs.assemble_man import generate_docbook_pages, create_manpage


class Installer:
    def __init__(self, root: str = None, prefix: str = None):
        if not root:
            root = os.environ.get('DESTDIR')
        if not root:
            root = '/'
        self.root = root

        if not prefix:
            prefix = '/usr/local' if self.root == '/' else '/usr'
        if prefix.startswith('/'):
            prefix = prefix[1:]
        self.prefix = prefix

    def install(self, src, dst, replace_vars=False):
        if dst.startswith('/'):
            dst = dst[1:]
            dst_full = os.path.join(self.root, dst, os.path.basename(src))
        else:
            dst_full = os.path.join(self.root, self.prefix, dst, os.path.basename(src))

        Path(os.path.dirname(dst_full)).mkdir(mode=0o755, parents=True, exist_ok=True)
        if replace_vars:
            with open(src, 'r') as f_src:
                with open(dst_full, 'w') as f_dst:
                    for line in f_src:
                        f_dst.write(line.replace('@PREFIX@', '/' + self.prefix))
        else:
            shutil.copy(src, dst_full)
        os.chmod(dst_full, 0o644)
        print('{}\t\t{}'.format(os.path.basename(src), dst_full))


def chdir_to_source_root():
    thisfile = __file__
    if not os.path.isabs(thisfile):
        thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))
    os.chdir(os.path.dirname(thisfile))


def make_manpages(temp_dir):
    ''' Build manual pages '''

    # check for xsltproc, we need it to build manual pages
    if not shutil.which('xsltproc'):
        print('The "xsltproc" binary was not found. Please install it to continue!')
        sys.exit(1)

    build_dir = os.path.join(temp_dir, 'docbook')
    Path(build_dir).mkdir(parents=True, exist_ok=True)
    pages = generate_docbook_pages(build_dir)
    man_files = []
    for page in pages:
        man_files.append(create_manpage(page, temp_dir))
    return man_files


def install_data(temp_dir: str, root_dir: str, prefix_dir: str):
    chdir_to_source_root()

    print('Checking dependencies')
    if not pkgconfig.installed('systemd', '>= 240'):
        print('Systemd is not installed on this system. Please make systemd available to continue.')
        sys.exit(4)

    print('Generating manual pages')
    manpage_files = make_manpages(temp_dir)

    print('Installing data')
    inst = Installer(root_dir, prefix_dir)
    sd_tmpfiles_dir = pkgconfig.variables('systemd')['tmpfilesdir']
    sd_system_unit_dir = pkgconfig.variables('systemd')['systemdsystemunitdir']
    man_dir = os.path.join('share', 'man', 'man1')

    inst.install('data/tmpfiles.d/debspawn.conf', sd_tmpfiles_dir)
    inst.install('data/services/debspawn-clear-caches.timer', sd_system_unit_dir)
    inst.install('data/services/debspawn-clear-caches.service', sd_system_unit_dir, replace_vars=True)
    for mf in manpage_files:
        inst.install(mf, man_dir)


def main():
    parser = ArgumentParser(description='Debspawn system data installer')

    parser.add_argument('--root', action='store', dest='root', default=None,
                        help='Root directory to install into.')
    parser.add_argument('--prefix', action='store', dest='prefix', default=None,
                        help='Directory prefix (usually `/usr` or `/usr/local`).')

    options = parser.parse_args(sys.argv[1:])
    with TemporaryDirectory(prefix='dsinstall-') as temp_dir:
        install_data(temp_dir, options.root, options.prefix)
    return 0


if __name__ == '__main__':
    sys.exit(main())
