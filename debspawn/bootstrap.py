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
from .osroot import OSRoot


def bootstrap_new(gconf, oroot, mirror=None):
    if os.getuid() != 0:
        print('This command needs to be run as root.')
        return False

    # ensure image location exists
    Path(gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

    osroot_name = oroot.get_name()

    cmd = ['debootstrap',
           '--arch={}'.format(oroot.arch),
           '--include=python3']
    if oroot.variant:
        cmd.append('--variant={}'.format(oroot.variant))
    cmd.extend([suite, os.path.join(gconf.osroots_dir, osroot_name)])
    if mirror:
        cmd.append(mirror)

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return False

    # create helper script runner
    copy_helper_script(gconf, osroot_name)

    return True
