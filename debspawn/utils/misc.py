# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2020 Matthias Klumpp <matthias@tenstral.net>
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
import shutil
from pathlib import Path
from contextlib import contextmanager
from ..config import GlobalConfig


def listify(item):
    '''
    Return a list of :item, unless :item already is a lit.
    '''
    if not item:
        return []
    return item if type(item) == list else [item]


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


def hardlink_or_copy(src, dst):
    ''' Hardlink a file :src to :dst or copy the file in case linking is not possible '''

    try:
        os.link(src, dst)
    except (PermissionError, OSError):
        shutil.copy2(src, dst)
