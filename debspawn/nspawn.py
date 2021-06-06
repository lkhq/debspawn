# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2021 Matthias Klumpp <matthias@tenstral.net>
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
import platform
from typing import Union
from .utils import temp_dir, print_error, print_warn, print_info, safe_run, run_forwarded
from .utils.env import colored_output_allowed, unicode_allowed
from .utils.command import run_command
from .injectpkg import PackageInjector


__systemd_version = None


def systemd_version():
    global __systemd_version
    if __systemd_version:
        return __systemd_version

    __systemd_version = -1
    try:
        out, _, _ = safe_run(['systemd-nspawn', '--version'])
        parts = out.split(' ', 2)
        if len(parts) >= 2:
            __systemd_version = int(parts[1])
    except Exception as e:
        print_warn('Unable to determine systemd version: {}'.format(e))

    return __systemd_version


def systemd_detect_virt():
    vm_name = 'unknown'
    try:
        out, _, _ = run_command(['systemd-detect-virt'])
        vm_name = out.strip()
    except Exception as e:
        print_warn('Unable to determine current virtualization: {}'.format(e))

    return vm_name


def systemd_version_atleast(expected_version: int):
    v = systemd_version()
    # we always assume we are running the highest version,
    # if we failed to determine the right systemd version
    if v < 0:
        return True
    if v >= expected_version:
        return True
    return False


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


def _execute_sdnspawn(osbase, parameters, machine_name, *,
                      allow_permissions: list[str] = None, syscall_filter: list[str] = None,
                      env_vars: dict[str, str] = None, private_users: bool = False):
    '''
    Execute systemd-nspawn with the given parameters.
    Mess around with cgroups if necessary.
    '''
    import sys

    if not allow_permissions:
        allow_permissions = []
    if not syscall_filter:
        syscall_filter = []
    if not env_vars:
        env_vars = {}

    capabilities = []
    full_dev_access = False
    full_proc_access = False
    ro_kmods_access = False
    kvm_access = False
    all_privileges = False
    for perm in allow_permissions:
        perm = perm.lower()
        if perm.startswith('cap_') or perm == 'all':
            if perm == 'all':
                capabilities.append(perm)
                print_warn('Container retains all privileges.')
                all_privileges = True
            else:
                capabilities.append(perm.upper())
        elif perm == 'full-dev':
            full_dev_access = True
        elif perm == 'full-proc':
            full_proc_access = True
        elif perm == 'read-kmods':
            ro_kmods_access = True
        elif perm == 'kvm':
            kvm_access = True
        else:
            print_info('Unknown allowed permission: {}'.format(perm))

    if (capabilities or full_dev_access or full_proc_access or kvm_access) \
            and not osbase.global_config.allow_unsafe_perms:
        print_error('Configuration does not permit usage of additional and potentially dangerous permissions. Exiting.')
        sys.exit(9)

    cmd = ['systemd-nspawn']
    cmd.extend(['-M', machine_name])
    cmd.append('--register=no')
    if private_users:
        cmd.append('-U')  # User namespaces with --private-users=pick --private-users-chown, if possible
    if full_dev_access:
        cmd.extend(['--bind', '/dev'])
        if systemd_version_atleast(244):
            cmd.append('--console=pipe')
        cmd.extend(['--property=DeviceAllow=block-* rw',
                    '--property=DeviceAllow=char-* rw'])
    if kvm_access and not full_dev_access:
        if os.path.exists('/dev/kvm'):
            cmd.extend(['--bind', '/dev/kvm'])
            cmd.extend(['--property=DeviceAllow=/dev/kvm rw'])
        else:
            print_warn('Access to KVM requested, but /dev/kvm does not exist on the host. Is virtualization supported?')
    if full_proc_access:
        cmd.extend(['--bind', '/proc'])
        if not all_privileges:
            print_warn('Container has access to host /proc')
    if ro_kmods_access:
        cmd.extend(['--bind-ro', '/lib/modules/'])
        cmd.extend(['--bind-ro', '/boot/'])
    if capabilities:
        cmd.extend(['--capability', ','.join(capabilities)])
    if syscall_filter:
        cmd.extend(['--system-call-filter', ' '.join(syscall_filter)])

    for v_name, v_value in env_vars.items():
        cmd.extend(['-E', '{}={}'.format(v_name, v_value)])

    cmd.extend(parameters)

    proc = run_forwarded(cmd)
    return proc.returncode


def nspawn_run_persist(osbase, base_dir, machine_name, chdir,
                       command: Union[list[str], str] = None, flags: Union[list[str], str] = None, *,
                       tmp_apt_cache_dir: str = None, pkginjector: PackageInjector = None,
                       allowed: list[str] = None, syscall_filter: list[str] = None,
                       env_vars: dict[str, str] = None, private_users: bool = False,
                       verbose: bool = False):
    if isinstance(command, str):
        command = command.split(' ')
    elif not command:
        command = []
    if isinstance(flags, str):
        flags = flags.split(' ')
    elif not flags:
        flags = []

    personality = get_nspawn_personality(osbase)

    def run_nspawn_with_aptcache(aptcache_tmp_dir):
        params = ['--chdir={}'.format(chdir),
                  '--link-journal=no',
                  '--bind={}:/var/cache/apt/archives/'.format(aptcache_tmp_dir)]
        if pkginjector and pkginjector.instance_repo_dir:
            params.append('--bind={}:/srv/extra-packages/'.format(pkginjector.instance_repo_dir))

        if personality:
            params.append('--personality={}'.format(personality))
        params.extend(flags)
        params.extend(['-a{}D'.format('' if verbose else 'q'), base_dir])
        params.extend(command)

        # ensure the temporary apt cache is up-to-date
        osbase.aptcache.create_instance_cache(aptcache_tmp_dir)

        # run command in container
        ret = _execute_sdnspawn(osbase,
                                params,
                                machine_name,
                                allow_permissions=allowed,
                                syscall_filter=syscall_filter,
                                env_vars=env_vars,
                                private_users=private_users)

        # archive APT cache, so future runs of this command are faster
        osbase.aptcache.merge_from_dir(aptcache_tmp_dir)

        return ret

    if tmp_apt_cache_dir:
        ret = run_nspawn_with_aptcache(tmp_apt_cache_dir)
    else:
        with temp_dir('aptcache-' + machine_name) as aptcache_tmp:
            ret = run_nspawn_with_aptcache(aptcache_tmp)

    return ret


def nspawn_run_ephemeral(osbase, base_dir, machine_name, chdir,
                         command: Union[list[str], str] = None, flags: Union[list[str], str] = None,
                         allowed: list[str] = None, syscall_filter: list[str] = None,
                         env_vars: dict[str, str] = None, private_users: bool = False):
    if isinstance(command, str):
        command = command.split(' ')
    elif not command:
        command = []
    if isinstance(flags, str):
        flags = flags.split(' ')
    elif not flags:
        flags = []

    personality = get_nspawn_personality(osbase)

    params = ['--chdir={}'.format(chdir),
              '--link-journal=no']
    if personality:
        params.append('--personality={}'.format(personality))
    params.extend(flags)
    params.extend(['-aqxD', base_dir])
    params.extend(command)

    return _execute_sdnspawn(osbase,
                             params,
                             machine_name,
                             allow_permissions=allowed,
                             syscall_filter=syscall_filter,
                             env_vars=env_vars,
                             private_users=private_users)


def nspawn_make_helper_cmd(flags, build_uid: int):
    if isinstance(flags, str):
        flags = flags.split(' ')

    cmd = ['/usr/lib/debspawn/dsrun']
    if not colored_output_allowed():
        cmd.append('--no-color')
    if not unicode_allowed():
        cmd.append('--no-unicode')
    if build_uid > 0:
        cmd.append('--buid={}'.format(build_uid))

    cmd.extend(flags)
    return cmd


def nspawn_run_helper_ephemeral(osbase, base_dir, machine_name, helper_flags, chdir='/tmp', *,
                                build_uid: int, nspawn_flags: Union[list[str], str] = None,
                                allowed: list[str] = None, env_vars: dict[str, str] = None,
                                private_users: bool = False):
    cmd = nspawn_make_helper_cmd(helper_flags, build_uid)
    return nspawn_run_ephemeral(base_dir,
                                machine_name,
                                chdir,
                                cmd,
                                flags=nspawn_flags,
                                allowed=allowed,
                                env_vars=env_vars,
                                private_users=private_users)


def nspawn_run_helper_persist(osbase, base_dir, machine_name, helper_flags, chdir='/tmp', *,
                              build_uid: int, nspawn_flags=[], tmp_apt_cache_dir=None,
                              pkginjector=None, allowed: list[str] = None, syscall_filter: list[str] = None,
                              env_vars: dict[str, str] = None, private_users: bool = False):
    cmd = nspawn_make_helper_cmd(helper_flags, build_uid)
    return nspawn_run_persist(osbase,
                              base_dir,
                              machine_name,
                              chdir,
                              cmd,
                              nspawn_flags,
                              tmp_apt_cache_dir=tmp_apt_cache_dir,
                              pkginjector=pkginjector,
                              allowed=allowed,
                              syscall_filter=syscall_filter,
                              env_vars=env_vars,
                              private_users=private_users)
