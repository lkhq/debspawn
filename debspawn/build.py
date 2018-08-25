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
import shutil
import platform
from glob import glob
from .utils.env import ensure_root, switch_unprivileged, get_owner_uid_gid, get_free_space, get_tree_size
from .utils.misc import print_header, print_section, temp_dir, cd, print_info, print_error, format_filesize
from .utils.command import safe_run
from .nspawn import nspawn_run_helper_persist


def internal_execute_build(osbase, pkg_dir, buildflags=[]):
    if not pkg_dir:
        raise Exception('Package directory is missing!')

    with osbase.new_instance() as (instance_dir, machine_name):
        # first, check basic requirements

        # instance dir and pkg dir are both temporary directories, so they
        # will be on the same filesystem configured as workspace for debspawn.
        # therefore we only check on directory.
        free_space = get_free_space(instance_dir)
        print_info('Free space in workspace: {}'.format(format_filesize(free_space)))

        # check for at least 512MiB - this is a ridiculously small amount, so the build will likely fail.
        # but with even less, even attempting a build is pointless.
        if (free_space / 2048) < 512:
            print_error('Not enough free space available in workspace.')
            return 8

        # prepare the build. At this point, we only run trusted code and the container
        # has network access
        with temp_dir('aptcache-' + machine_name) as aptcache_tmp:
            nspawn_flags = ['--bind={}:/srv/build/'.format(os.path.normpath(pkg_dir))]
            r = nspawn_run_helper_persist(osbase,
                                          instance_dir,
                                          machine_name,
                                          '--build-prepare',
                                          '/srv',
                                          nspawn_flags,
                                          aptcache_tmp)
            if r != 0:
                print_error('Build environment setup failed.')
                return False

            # run the actual build. At this point, code is less trusted, and we disable network access.
            nspawn_flags = ['--bind={}:/srv/build/'.format(os.path.normpath(pkg_dir)),
                            '-u', 'builder',
                            '--private-network']
            helper_flags = ['--build-run']
            if buildflags:
                helper_flags.append('--buildflags={}'.format(' '.join(buildflags)))
            r = nspawn_run_helper_persist(osbase,
                                          instance_dir,
                                          machine_name,
                                          helper_flags,
                                          '/srv',
                                          nspawn_flags,
                                          aptcache_tmp)
            if r != 0:
                return False

            build_dir_size = get_tree_size(pkg_dir)
            print_info('This build required {} of dedicated disk space.'.format(format_filesize(build_dir_size)))

    return True


def print_build_detail(osbase, pkgname, version):
    print_info('Package: {}'.format(pkgname))
    print_info('Version: {}'.format(version))
    print_info('Distribution: {}'.format(osbase.suite))
    print_info('Architecture: {}'.format(osbase.arch))
    print_info()


def _read_source_package_details():
    out, err, ret = safe_run(['dpkg-parsechangelog'])
    if ret != 0:
        raise Exception('Running dpkg-parsechangelog failed: {}{}'.format(out, err))

    pkg_sourcename = None
    pkg_version = None
    for line in out.split('\n'):
        if line.startswith('Source: '):
            pkg_sourcename = line[8:].strip()
        elif line.startswith('Version: '):
            pkg_version = line[9:].strip()

    if not pkg_sourcename or not pkg_version:
        print_error('Unable to determine source package name or source package version. Can not continue.')
        return None, None, None

    dsc_fname = '{}_{}.dsc'.format(pkg_sourcename, pkg_version)

    return pkg_sourcename, pkg_version, dsc_fname


def _get_build_flags(build_only=None, include_orig=False, maintainer=None, extra_flags=[]):
    buildflags = []

    if build_only:
        if build_only == 'binary':
            buildflags.append('-b')
        elif build_only == 'arch':
            buildflags.append('-B')
        elif build_only == 'indep':
            buildflags.append('-A')
        elif build_only == 'source':
            buildflags.append('-S')
        else:
            print_error('Invalid build-only flag "{}". Can not continue.'.format(build_only))
            return False, []

    if include_orig:
        buildflags.append('-sa')
    if maintainer:
        buildflags.append('-m\'{}\''.format(maintainer))
        buildflags.append('-e\'{}\''.format(maintainer))
    buildflags.extend(extra_flags)

    return True, buildflags


def _retrieve_artifacts(osbase, tmp_dir):
    print_section('Retrieving build artifacts')

    o_uid, o_gid = get_owner_uid_gid()
    acount = 0
    for f in glob(os.path.join(tmp_dir, '*.*')):
        if os.path.isfile(f):
            target_fname = os.path.join(osbase.results_dir, os.path.basename(f))
            shutil.copy2(f, target_fname)
            os.chown(target_fname, o_uid, o_gid)
            acount += 1
    print_info('Copied {} files.'.format(acount))


def _sign_result(results_dir, spkg_name, spkg_version, build_arch):
    print_section('Signing Package')
    changes_basename = '{}_{}_{}.changes'.format(spkg_name, spkg_version, build_arch)

    with switch_unprivileged():
        proc = subprocess.run(['debsign', os.path.join(results_dir, changes_basename)])
        if proc.returncode != 0:
            print_error('Signing failed.')
            return False
    return True


def _print_system_info():
    from . import __version__
    from .utils.misc import current_time_string
    print_info('debspawn {version} on {host} at {time}'.format(version=__version__, host=platform.node(), time=current_time_string()))
    print_info()


def build_from_directory(osbase, pkg_dir, sign=False, build_only=None, include_orig=False, maintainer=None, extra_dpkg_flags=[]):
    ensure_root()
    osbase.ensure_exists()

    if not pkg_dir:
        pkg_dir = os.getcwd()
    pkg_dir = os.path.abspath(pkg_dir)

    r, buildflags = _get_build_flags(build_only, include_orig, maintainer, extra_dpkg_flags)
    if not r:
        return False

    _print_system_info()
    print_header('Package build (from directory)')

    print_section('Creating source package')
    with cd(pkg_dir):
        with switch_unprivileged():
            pkg_sourcename, pkg_version, dsc_fname = _read_source_package_details()
            if not pkg_sourcename:
                return False

            cmd = ['dpkg-buildpackage', '-S', '-d', '--no-sign']
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                return False

    print_header('Package build')
    print_build_detail(osbase, pkg_sourcename, pkg_version)

    with temp_dir(pkg_sourcename) as pkg_tmp_dir:
        with cd(pkg_tmp_dir):
            cmd = ['dpkg-source',
                   '-x', os.path.join(pkg_dir, '..', dsc_fname)]
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                return False

        ret = internal_execute_build(osbase, pkg_tmp_dir, buildflags)
        if not ret:
            return False

        # copy build results
        _retrieve_artifacts(osbase, pkg_tmp_dir)

    # sign the resulting package
    if sign:
        r = _sign_result(osbase.results_dir, pkg_sourcename, pkg_version, osbase.arch)
        if not r:
            return False

    print_info('Done.')

    return True


def build_from_dsc(osbase, dsc_fname, sign=False, build_only=None, include_orig=False, maintainer=None, extra_dpkg_flags=[]):
    ensure_root()
    osbase.ensure_exists()

    r, buildflags = _get_build_flags(build_only, include_orig, maintainer, extra_dpkg_flags)
    if not r:
        return False

    _print_system_info()

    dsc_fname = os.path.abspath(os.path.normpath(dsc_fname))
    tmp_prefix = os.path.basename(dsc_fname).replace('.dsc', '').replace(' ', '-')
    with temp_dir(tmp_prefix) as pkg_tmp_dir:
        with cd(pkg_tmp_dir):
            cmd = ['dpkg-source',
                   '-x', dsc_fname]
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                return False

            pkg_srcdir = None
            for f in glob('./*'):
                if os.path.isdir(f):
                    pkg_srcdir = f
                    break
            if not pkg_srcdir:
                print_error('Unable to find source directory of extracted package.')
                return False

            with cd(pkg_srcdir):
                pkg_sourcename, pkg_version, dsc_fname = _read_source_package_details()
                if not pkg_sourcename:
                    return False

            print_header('Package build')
            print_build_detail(osbase, pkg_sourcename, pkg_version)

        ret = internal_execute_build(osbase, pkg_tmp_dir, buildflags)
        if not ret:
            return False

        # copy build results
        _retrieve_artifacts(osbase, pkg_tmp_dir)

    # sign the resulting package
    if sign:
        r = _sign_result(osbase.results_dir, pkg_sourcename, pkg_version, osbase.arch)
        if not r:
            return False

    print_info('Done.')

    return True
