# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2018 Matthias Klumpp <matthias@tenstral.net>
#
# Licensed under the GNU Lesser General Public License Version 3
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the license, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import shutil
from pathlib import Path
from contextlib import contextmanager
from ..utils.command import safe_run


def sign(changes, gpg):
    if changes.endswith(".dud"):
        safe_run(['gpg', '-u', gpg, '--clearsign', changes])
        os.rename("%s.asc" % (changes), changes)
    else:
        safe_run(['debsign', '-k', gpg, changes])


def upload(changes, gpg, host):
    sign(changes, gpg)
    return safe_run(['dput', host, changes])


@contextmanager
def cd(where):
    ncwd = os.getcwd()
    try:
        yield os.chdir(where)
    finally:
        os.chdir(ncwd)


@contextmanager
def temp_dir(basename=None):
    from random import choices
    from string import ascii_lowercase, digits

    rdm_id = ''.join(choices(ascii_lowercase + digits, k=8))
    if basename:
        dir_name = '{}-{}'.format(basename, rdm_id)
    else:
        dir_name = rdm_id

    tmp_path = os.path.join('/var/tmp/debspawn/', dir_name)
    Path(tmp_path).mkdir(parents=True, exist_ok=True)

    try:
        yield tmp_path
    finally:
        shutil.rmtree(tmp_path)


def ensure_root():
    if os.geteuid() == 0:
        return

    if shutil.which('sudo'):
        os.execvp("sudo", ["sudo"] + sys.argv)
    else:
        print('This command needs to be run as root.')
        sys.exit(1)


def print_textbox(title, tl, hline, tr, vline, bl, br):
    def write_utf8(s):
        sys.stdout.buffer.write(s.encode('utf-8'))

    l = len(title)
    write_utf8('\n{}'.format(tl))
    write_utf8(hline * (10 + l))
    write_utf8('{}\n'.format(tr))

    write_utf8('{}  {}'.format(vline, title))
    write_utf8(' ' * 8)
    write_utf8('{}\n'.format(vline))

    write_utf8(bl)
    write_utf8(hline * (10 + l))
    write_utf8('{}\n'.format(br))

    sys.stdout.flush()


def print_header(title):
    print_textbox(title, '╔', '═', '╗', '║', '╚', '╝')


def print_section(title):
    print_textbox(title, '┌', '─', '┐', '│', '└', '┘')
