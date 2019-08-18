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
from .env import unicode_allowed
from ..config import GlobalConfig


@contextmanager
def cd(where):
    ncwd = os.getcwd()
    try:
        yield os.chdir(where)
    finally:
        os.chdir(ncwd)


@contextmanager
def temp_dir(basename=None):
    from random import choice
    from string import ascii_lowercase, digits

    rdm_id = ''.join(choice(ascii_lowercase + digits) for _ in range(8))
    if basename:
        dir_name = '{}-{}'.format(basename, rdm_id)
    else:
        dir_name = rdm_id

    temp_basedir = GlobalConfig().temp_dir
    if not temp_basedir:
        temp_basedir = '/var/tmp/debspawn/'

    tmp_path = os.path.join(temp_basedir, dir_name)
    Path(tmp_path).mkdir(parents=True, exist_ok=True)

    try:
        yield tmp_path
    finally:
        shutil.rmtree(tmp_path)


def print_textbox(title, tl, hline, tr, vline, bl, br):
    def write_utf8(s):
        sys.stdout.buffer.write(s.encode('utf-8'))

    tlen = len(title)
    write_utf8('\n{}'.format(tl))
    write_utf8(hline * (10 + tlen))
    write_utf8('{}\n'.format(tr))

    write_utf8('{}  {}'.format(vline, title))
    write_utf8(' ' * 8)
    write_utf8('{}\n'.format(vline))

    write_utf8(bl)
    write_utf8(hline * (10 + tlen))
    write_utf8('{}\n'.format(br))

    sys.stdout.flush()


def print_header(title):
    if unicode_allowed():
        print_textbox(title, '╔', '═', '╗', '║', '╚', '╝')
    else:
        print_textbox(title, '+', '═', '+', '|', '+', '+')


def print_section(title):
    if unicode_allowed():
        print_textbox(title, '┌', '─', '┐', '│', '└', '┘')
    else:
        print_textbox(title, '+', '-', '+', '|', '+', '+')


def print_info(*arg):
    '''
    Prints an information message and ensures that it shows up on
    stdout immediately.
    '''
    print(*arg)
    sys.stdout.flush()


def print_error(*arg):
    '''
    Prints an information message and ensures that it shows up on
    stdout immediately.
    '''
    print('ERROR:', *arg, file=sys.stderr)
    sys.stderr.flush()


def format_filesize(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def current_time_string():
    ''' Get the current time as human-readable string. '''

    from datetime import datetime, timezone
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone().strftime('%Y-%m-%d %H:%M:%S UTC%z')


def version_noepoch(version):
    ''' Return version from :version without epoch. '''

    version_noe = version
    if ':' in version_noe:
        version_noe = version_noe.split(':', 1)[1]
    return version_noe
