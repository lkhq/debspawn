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
import tempfile
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


def copy_helper_script(gconf, osroot_name):
    # ensure image location exists
    Path(gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

    osroot_path = os.path.join(gconf.osroots_dir, osroot_name)
    if not os.path.isdir(osroot_path):
        raise Exception('Tried to access os tree "{}", which does not exist.'.format(osroot_name))

    script_location = os.path.join(osroot_path, 'usr', 'lib', 'debspawn')
    Path(script_location).mkdir(parents=True, exist_ok=True)
    script_fname = os.path.join(script_location, 'dsrun.py')

    if os.path.isfile(script_fname):
        os.remove(script_fname)
    shutil.copy2(gconf.dsrun_path, script_fname)

    os.chmod(script_fname, 0o0755)


@contextmanager
def cd(where):
    ncwd = os.getcwd()
    try:
        yield os.chdir(where)
    finally:
        os.chdir(ncwd)


@contextmanager
def tdir():
    fp = tempfile.mkdtemp()
    try:
        yield fp
    finally:
        shutil.rmtree(fp)
