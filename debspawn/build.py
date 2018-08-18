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
from pathlib import Path
from glob import glob
from .utils.misc import ensure_root, print_header, print_section, temp_dir, cd, colored_output_allowed
from .utils.command import safe_run
from .nspawn import nspawn_run_helper, nspawn_make_helper_cmd


def internal_execute_build(osbase, pkg_dir):
    if not pkg_dir:
        raise Exception('Package directory is missing!')

    with osbase.new_instance() as (instance_dir, machine_name):
        # prepare the build. At this point, we only run trusted code and the container
        # has network access
        cmd = ['systemd-nspawn',
               '--chdir=/srv',
               '-M', machine_name,
               '--bind={}:/srv/build/'.format(os.path.normpath(pkg_dir)),
               '-aqD', instance_dir]
        cmd.extend(nspawn_make_helper_cmd('--build-prepare'))

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return False

        # run the actual build. At this point, code is less trusted, and we disable network access.
        cmd = ['systemd-nspawn',
               '--chdir=/srv',
               '-M', machine_name,
               '-u', 'builder',
               '--private-network',
               '--bind={}:/srv/build/'.format(os.path.normpath(pkg_dir)),
               '-aqD', instance_dir]
        cmd.extend(nspawn_make_helper_cmd('--build-run'))

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return False
    return True


def print_build_detail(osbase, pkgname, version):
    print('Package: {}'.format(pkgname))
    print('Version: {}'.format(version))
    print('Distribution: {}'.format(osbase.suite))
    print('Architecture: {}'.format(osbase.arch))
    print()


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
        print('Unable to determine source package name or source package version. Can not continue.')
        return None, None, None

    dsc_fname = '{}_{}.dsc'.format(pkg_sourcename, pkg_version)

    return pkg_sourcename, pkg_version, dsc_fname


def build_from_directory(osbase, pkg_dir):
    ensure_root()
    if not pkg_dir:
        pkg_dir = os.getcwd()

    print_header('Package build (from directory)')

    print_section('Creating source package')
    with cd(pkg_dir):
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

        ret = internal_execute_build(osbase, pkg_tmp_dir)
        if not ret:
            return False

        print_section('Retrieving build artifacts')
        for f in glob(os.path.join(pkg_tmp_dir, '*.*')):
            if os.path.isfile(f):
                shutil.copy2(f, osbase.results_dir)
    print('Done.')

    return True


def build_from_dsc(osbase, dsc_fname):
    ensure_root()

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
                print('Unable to find source directory of extracted package.')
                return False

            with cd(pkg_srcdir):
                pkg_sourcename, pkg_version, dsc_fname = _read_source_package_details()
                if not pkg_sourcename:
                    return False

            print_header('Package build')
            print_build_detail(osbase, pkg_sourcename, pkg_version)

        ret = internal_execute_build(osbase, pkg_tmp_dir)
        if not ret:
            return False

        print_section('Retrieving build artifacts')
        for f in glob(os.path.join(pkg_tmp_dir, '*.*')):
            if os.path.isfile(f):
                shutil.copy2(f, osbase.results_dir)
    print('Done.')

    return True
