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

import subprocess
import platform
from .utils.env import colored_output_allowed, unicode_allowed
from .utils.misc import temp_dir


def get_nspawn_personality(osbase):
    '''
    Return the syszemd-nspawn container personality for the given combination
    of host architecture and base OS.
    This allows running x86 builds on amd64 machines.
    '''
    import fnmatch

    if platform.machine() == 'x86_64' and fnmatch.filter([osbase.arch], 'i?86'):
        return 'x86'
    return None


def nspawn_run_persist(osbase, base_dir, machine_name, chdir, command=[], flags=[], tmp_apt_cache_dir=None, verbose=False):
    if isinstance(command, str):
        command = command.split(' ')
    if isinstance(flags, str):
        flags = flags.split(' ')

    personality = get_nspawn_personality(osbase)

    def run_nspawn_with_aptcache(aptcache_tmp_dir):
        cmd = ['systemd-nspawn',
               '--chdir={}'.format(chdir),
               '-M', machine_name,
               '--bind={}:/var/cache/apt/archives/'.format(aptcache_tmp_dir)]
        if personality:
            cmd.append('--personality={}'.format(personality))
        cmd.extend(flags)
        cmd.extend(['-a{}D'.format('' if verbose else 'q'), base_dir])
        cmd.extend(command)

        # ensure the temporary apt cache is up-to-date
        osbase.aptcache.create_instance_cache(aptcache_tmp_dir)

        # run command in container
        proc = subprocess.run(cmd)

        # archive APT cache, so future runs of this command are faster
        osbase.aptcache.merge_from_dir(aptcache_tmp_dir)

        return proc

    if tmp_apt_cache_dir:
        proc = run_nspawn_with_aptcache(tmp_apt_cache_dir)
    else:
        with temp_dir('aptcache-' + machine_name) as aptcache_tmp:
            proc = run_nspawn_with_aptcache(aptcache_tmp)

    return proc.returncode


def nspawn_run_ephemeral(osbase, base_dir, machine_name, chdir, command=[], flags=[]):
    if isinstance(command, str):
        command = command.split(' ')
    if isinstance(flags, str):
        flags = flags.split(' ')

    personality = get_nspawn_personality(osbase)

    cmd = ['systemd-nspawn',
           '--chdir={}'.format(chdir),
           '-M', machine_name]
    if personality:
        cmd.append('--personality={}'.format(personality))
    cmd.extend(flags)
    cmd.extend(['-aqxD', base_dir])
    cmd.extend(command)

    proc = subprocess.run(cmd)
    return proc.returncode


def nspawn_make_helper_cmd(flags):
    if isinstance(flags, str):
        flags = flags.split(' ')

    cmd = ['/usr/lib/debspawn/dsrun.py']
    if not colored_output_allowed():
        cmd.append('--no-color')
    if not unicode_allowed():
        cmd.append('--no-unicode')

    cmd.extend(flags)
    return cmd


def nspawn_run_helper_ephemeral(osbase, base_dir, machine_name, helper_flags, chdir='/tmp', nspawn_flags=[]):
    cmd = nspawn_make_helper_cmd(helper_flags)
    return nspawn_run_ephemeral(base_dir, machine_name, chdir, cmd, nspawn_flags)


def nspawn_run_helper_persist(osbase, base_dir, machine_name, helper_flags, chdir='/tmp', nspawn_flags=[], tmp_apt_cache_dir=None):
    cmd = nspawn_make_helper_cmd(helper_flags)
    return nspawn_run_persist(osbase, base_dir, machine_name, chdir, cmd, nspawn_flags, tmp_apt_cache_dir)
