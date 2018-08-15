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
from .utils.misc import print_header, print_section
from .utils.command import safe_run
from .nspawn import nspawn_run_helper


def build_dir(osbase, pkg_dir):
    if os.getuid() != 0:
        print('This command needs to be run as root.')
        return False

    if not pkg_dir:
        pkg_dir = os.getcwd()

    print_header('Package build')
    print('Package: {}'.format('?'))
    print('Version: {}'.format('?'))
    print('Distribution: {}'.format(osbase.suite))
    print('Architecture: {}'.format(osbase.arch))

    with osbase.new_instance() as (instance_dir, machine_name):
        # prepare the build. At this point, we only run trusted code and the container
        # has network access
        cmd = ['systemd-nspawn',
               '--chdir=/srv',
               '-M', machine_name,
               '--bind={}:/srv/build/'.format(os.path.normpath(os.path.join(pkg_dir, '..'))),
               '-aqD', instance_dir,
               '/usr/lib/debspawn/dsrun.py', '--build-prepare=auto']

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return False

        # run the actual build. At this point, code is less trusted, and we disable network access.
        cmd = ['systemd-nspawn',
               '--chdir=/srv',
               '-M', machine_name,
               '-u', 'builder',
               '--private-network',
               '--bind={}:/srv/build/'.format(os.path.normpath(os.path.join(pkg_dir, '..'))),
               '-aqD', instance_dir,
               '/usr/lib/debspawn/dsrun.py', '--build-run=auto']

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return False
    return True
