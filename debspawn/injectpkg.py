# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2020 Matthias Klumpp <matthias@tenstral.net>
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
from pathlib import Path
from glob import glob
from contextlib import contextmanager
from .utils import hardlink_or_copy, temp_dir, print_info


class PackageInjector:
    '''
    Inject packages from external sources into the container APT environment.
    '''

    def __init__(self, osbase):
        self._pkgs_basedir = osbase.global_config.injected_pkgs_dir
        self._pkgs_specific_dir = os.path.join(self._pkgs_basedir, osbase.name)
        self._has_injectables = None
        self._instance_repo_dir = None

    def has_injectables(self):
        ''' Return True if we actually have any packages ready to inject '''

        if type(self._has_injectables) is bool:
            return self._has_injectables

        if os.path.exists(self._pkgs_basedir) and os.path.isdir(self._pkgs_basedir):
            for f in os.listdir(self._pkgs_basedir):
                if os.path.isfile(os.path.join(self._pkgs_basedir, f)):
                    self._has_injectables = True
                    return True

            if os.path.exists(self._pkgs_specific_dir) and os.path.isdir(self._pkgs_specific_dir):
                for f in os.listdir(self._pkgs_specific_dir):
                    if os.path.isfile(os.path.join(self._pkgs_specific_dir, f)):
                        self._has_injectables = True
                        return True

        self._has_injectables = False
        return False

    def create_instance_repo(self, tmp_repo_dir):
        '''
        Create a temporary location where all injected packages for this container
        are copied to.
        '''

        Path(self._pkgs_basedir).mkdir(parents=True, exist_ok=True)
        Path(tmp_repo_dir).mkdir(parents=True, exist_ok=True)

        print_info('Copying injected packages to instance location')
        self._instance_repo_dir = tmp_repo_dir

        # copy/link injected packages specific to this environment
        if os.path.isdir(self._pkgs_specific_dir):
            for pkg_fname in glob(os.path.join(self._pkgs_specific_dir, '*.deb')):
                pkg_path = os.path.join(tmp_repo_dir, os.path.basename(pkg_fname))

                if not os.path.isfile(pkg_path):
                    hardlink_or_copy(pkg_fname, pkg_path)

        # copy/link injected packages used by all environments
        for pkg_fname in glob(os.path.join(self._pkgs_basedir, '*.deb')):
            pkg_path = os.path.join(tmp_repo_dir, os.path.basename(pkg_fname))

            if not os.path.isfile(pkg_path):
                hardlink_or_copy(pkg_fname, pkg_path)

    @property
    def instance_repo_dir(self) -> str:
        return self._instance_repo_dir


@contextmanager
def package_injector(osbase, machine_name=None):
    '''
    Create a package injector as context manager and make
    it create a new temporary instance repo.
    '''

    if not machine_name:
        from random import choice
        from string import ascii_lowercase, digits

        nid = ''.join(choice(ascii_lowercase + digits) for _ in range(4))
        machine_name = '{}-{}'.format(osbase.name, nid)

    pi = PackageInjector(osbase)
    if not pi.has_injectables():
        yield pi
    else:
        with temp_dir('pkginject-' + machine_name) as injectrepo_tmp:
            pi.create_instance_repo(injectrepo_tmp)
            yield pi
