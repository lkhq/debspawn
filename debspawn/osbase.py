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
from contextlib import contextmanager
from .utils.misc import ensure_root, temp_dir, print_header, print_section
from .utils.command import safe_run
from .utils.zstd_tar import compress_directory, decompress_tarball, ensure_tar_zstd
from .nspawn import nspawn_run_helper_persist


class OSBase:
    ''' Describes an OS base registered with debspawn '''

    def __init__(self, gconf, suite, arch, variant=None):
        self._gconf = gconf
        self._suite = suite
        self._arch = arch
        self._variant = variant
        self._name = self._make_name()


        # ensure we can (de)compress zstd tarballs
        ensure_tar_zstd()


    def _make_name(self):
        if not self._arch:
            out, _, ret = safe_run(['dpkg-architecture', '-qDEB_HOST_ARCH'])
            if ret != 0:
                raise Exception('Running dpkg-architecture failed: {}'.format(out))

            self._arch = out.strip()
        if self._variant:
            return '{}-{}-{}'.format(self._suite, self._arch, self._variant)
        else:
            return '{}-{}'.format(self._suite, self._arch)


    @property
    def name(self) -> str:
        return self._name

    @property
    def suite(self) -> str:
        return self._suite

    @property
    def arch(self) -> str:
        return self._arch

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def global_config(self):
        return self._gconf

    @property
    def results_dir(self):
        resdir = self._gconf.results_dir
        Path(resdir).mkdir(parents=True, exist_ok=True)
        return resdir


    def _copy_helper_script(self, osroot_path):
        script_location = os.path.join(osroot_path, 'usr', 'lib', 'debspawn')
        Path(script_location).mkdir(parents=True, exist_ok=True)
        script_fname = os.path.join(script_location, 'dsrun.py')

        if os.path.isfile(script_fname):
            os.remove(script_fname)
        shutil.copy2(self._gconf.dsrun_path, script_fname)

        os.chmod(script_fname, 0o0755)


    def get_tarball_location(self):
        return os.path.join(self._gconf.osroots_dir, '{}.tar.zst'.format(self.name))


    def exists(self):
        return os.path.isfile(self.get_tarball_location())


    def new_nspawn_machine_name(self):
        import platform
        from random import choices
        from string import ascii_lowercase, digits

        nid = ''.join(choices(ascii_lowercase + digits, k=4))
        return '{}-{}-{}'.format(platform.node(), self.name, nid)


    def create(self, mirror=None):
        ensure_root()

        if self.exists():
            print('This configuration has already been created. You can only delete or update it.')
            return False

        # ensure image location exists
        Path(self._gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

        print_header('Creating new base: {} [{}]'.format(self.suite, self.arch))
        print('Using mirror: {}'.format(mirror if mirror else 'default'))
        if self.variant:
            print('variant: {}'.format(variant))
        cmd = ['debootstrap',
               '--arch={}'.format(self.arch),
               '--include=python3-minimal']
        if self.variant:
            cmd.append('--variant={}'.format(self.variant))

        with temp_dir() as tdir:
            cmd.extend([self.suite, tdir])
            if mirror:
                cmd.append(mirror)

            print_section('Bootstrap')
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                return False

            # create helper script runner
            self._copy_helper_script(tdir)

            print_section('Configure')
            if nspawn_run_helper_persist(tdir, self.new_nspawn_machine_name(), '--update') != 0:
                return False

            print_section('Creating Tarball')
            compress_directory(tdir, self.get_tarball_location())

        print('Done.')
        return True


    @contextmanager
    def new_instance(self, basename=None):
        with temp_dir() as tdir:
            decompress_tarball(self.get_tarball_location(), tdir)
            yield tdir, self.new_nspawn_machine_name()


    def make_instance_permanent(self, instance_dir):
        ''' Add changes done in the current instance to the main tarball of this OS tree, replacing it. '''

        tarball_name = self.get_tarball_location()
        tarball_name_old = '{}.old'.format(tarball_name)

        os.replace(tarball_name, tarball_name_old)
        compress_directory(instance_dir, tarball_name)
        os.remove(tarball_name_old)


    def update(self):
        ensure_root()

        if not self.exists():
            print('Can not update "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Updating container')
        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            print_section('Update')
            if nspawn_run_helper_persist(instance_dir, self.new_nspawn_machine_name(), '--update') != 0:
                return False

            print_section('Recreating tarball')
            self.make_instance_permanent(instance_dir)

        print('Done.')
        return True
