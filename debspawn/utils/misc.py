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


unicode_allowed = True


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


def colored_output_allowed():
    return (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()) or \
            ('TERM' in os.environ and os.environ['TERM']=='ANSI')


def unicode_allowed():
    global unicode_allowed
    return unicode_allowed


def set_unicode_allowed(val):
    global unicode_allowed
    unicode_allowed = val


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
    global unicode_allowed

    if unicode_allowed:
        print_textbox(title, '╔', '═', '╗', '║', '╚', '╝')
    else:
        print_textbox(title, '+', '═', '+', '|', '+', '+')


def print_section(title):
    global unicode_allowed

    if unicode_allowed:
        print_textbox(title, '┌', '─', '┐', '│', '└', '┘')
    else:
        print_textbox(title, '+', '-', '+', '|', '+', '+')


def format_filesize(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)
