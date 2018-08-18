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
from glob import glob
from .utils.misc import ensure_root, print_header, print_section, temp_dir, cd
from .utils.command import safe_run
from .nspawn import nspawn_run_helper_persist


def internal_execute_build(osbase, pkg_dir, buildflags):
    if not pkg_dir:
        raise Exception('Package directory is missing!')

    with osbase.new_instance() as (instance_dir, machine_name):
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


def _get_build_flags(build_arch_only=False, build_indep_only=False, include_orig=False, extra_flags=[]):
    if build_arch_only and build_indep_only:
        print('Can not build only arch-indep and only arch-specific packages at the same time. Nothing would get built. Please check your flags.')
        return False, []

    buildflags = []
    if build_arch_only:
        buildflags.append('-B')
    if build_indep_only:
        buildflags.append('-A')
    if include_orig:
        buildflags.append('-sa')
    buildflags.extend(extra_flags)

    return True, buildflags


def _retrieve_artifacts(osbase, tmp_dir):
    print_section('Retrieving build artifacts')

    acount = 0
    for f in glob(os.path.join(tmp_dir, '*.*')):
        if os.path.isfile(f):
            shutil.copy2(f, osbase.results_dir)
            acount += 1
    print('Copied {} files.'.format(acount))


def _sign_result(results_dir, spkg_name, spkg_version, build_arch):
    print_section('Signing Package')
    changes_basename = '{}_{}_{}.changes'.format(spkg_name, spkg_version, build_arch)

    proc = subprocess.run(['debsign', os.path.join(results_dir, changes_basename)])
    if proc.returncode != 0:
        print('Signing failed.')
        return False
    return True


def build_from_directory(osbase, pkg_dir, sign=False, build_arch_only=False, build_indep_only=False, include_orig=False, extra_dpkg_flags=[]):
    ensure_root()
    if not pkg_dir:
        pkg_dir = os.getcwd()

    r, buildflags = _get_build_flags(build_arch_only, build_indep_only, include_orig, extra_dpkg_flags)
    if not r:
        return False

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

    print('Done.')

    return True


def build_from_dsc(osbase, dsc_fname, sign=False, build_arch_only=False, build_indep_only=False, include_orig=False, extra_dpkg_flags=[]):
    ensure_root()

    r, buildflags = _get_build_flags(build_arch_only, build_indep_only, include_orig, extra_dpkg_flags)
    if not r:
        return False

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

    print('Done.')

    return True
