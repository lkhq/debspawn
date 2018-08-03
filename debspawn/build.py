# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Matthias Klumpp <matthias@tenstral.net>
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
import subprocess
from pathlib import Path
from .utils.command import safe_run
from .utils.misc import copy_helper_script
from .nspawn import nspawn_run_helper


def build_dir(gconf, osroot, pkg_dir):
    if os.getuid() != 0:
        print('This command needs to be run as root.')
        return False

    if not pkg_dir:
        pkg_dir = os.getcwd()


    osroot_name = osroot.get_name()
    cmd = ['systemd-nspawn',
           '--chdir=/srv',
           '--bind={}:/srv/build/'.format(os.path.normpath(os.path.join(pkg_dir, '..'))),
           '-axD', os.path.join(gconf.osroots_dir, osroot_name),
           '/usr/lib/debspawn/dsrun.py', '--build=auto']

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return False
    return True
