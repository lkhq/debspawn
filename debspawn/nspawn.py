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


def nspawn_run_persist(base_dir, machine_name, commands):
    cmd = ['systemd-nspawn',
           '--chdir=/tmp',
           '-M', machine_name,
           '-aqD', base_dir]
    cmd.extend(commands)

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return False
    return True


def nspawn_run(base_dir, machine_name, commands):
    cmd = ['systemd-nspawn',
           '--chdir=/srv',
           '-M', machine_name,
           '-aqxD', base_dir]
    cmd.extend(commands)

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return False
    return True


def nspawn_run_helper(base_dir, machine_name, commands):
    cmd = ['/usr/lib/debspawn/dsrun.py']
    cmd.extend(commands)
    return nspawn_run(base_dir, machine_name, cmd)


def nspawn_run_helper_persist(base_dir, machine_name, commands):
    cmd = ['/usr/lib/debspawn/dsrun.py']
    cmd.extend(commands)
    return nspawn_run_persist(base_dir, machine_name, cmd)
