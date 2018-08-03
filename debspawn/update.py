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
from .nspawn import nspawn_run_persist, nspawn_run_helper_persist


def update_osroot(gconf, osroot):
    if os.getuid() != 0:
        print('This command needs to be run as root.')
        return False

    # ensure image location exists
    Path(gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

    # create helper script runner
    copy_helper_script(gconf, osroot.get_name())

    if not nspawn_run_helper_persist(gconf, osroot, ['--update']):
        return False

    return True
