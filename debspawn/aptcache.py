# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2020 Matthias Klumpp <matthias@tenstral.net>
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
import shutil
from pathlib import Path
from glob import glob
from .utils.misc import hardlink_or_copy


class APTCache:
    '''
    Manage cache of APT packages
    '''

    def __init__(self, osbase):
        self._cache_dir = os.path.join(osbase.global_config.aptcache_dir, osbase.name)

    def merge_from_dir(self, tmp_cache_dir):
        '''
        Merge in packages from a temporary cache
        '''

        from random import choice
        from string import ascii_lowercase, digits

        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
        for pkg_fname in glob(os.path.join(tmp_cache_dir, '*.deb')):
            pkg_basename = os.path.basename(pkg_fname)
            pkg_cachepath = os.path.join(self._cache_dir, pkg_basename)

            if not os.path.isfile(pkg_cachepath):
                pkg_tmp_name = pkg_cachepath + '.tmp-' + ''.join(choice(ascii_lowercase + digits) for _ in range(8))
                shutil.copy2(pkg_fname, pkg_tmp_name)
                try:
                    os.rename(pkg_tmp_name, pkg_cachepath)
                except OSError:
                    # maybe some other debspawn instance tried to add the package just now,
                    # in that case we give up
                    os.remove(pkg_tmp_name)

    def create_instance_cache(self, tmp_cache_dir):
        '''
        Copy the cache to a temporary location for use in a new container instance.
        '''

        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
        Path(tmp_cache_dir).mkdir(parents=True, exist_ok=True)

        for pkg_fname in glob(os.path.join(self._cache_dir, '*.deb')):
            pkg_cachepath = os.path.join(tmp_cache_dir, os.path.basename(pkg_fname))

            if not os.path.isfile(pkg_cachepath):
                hardlink_or_copy(pkg_fname, pkg_cachepath)

    def clear(self):
        '''
        Remove all cache contents.
        '''

        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
        cache_size = len(glob(os.path.join(self._cache_dir, '*.deb')))

        old_cache_dir = self._cache_dir.rstrip(os.sep) + '.old'
        os.rename(self._cache_dir, old_cache_dir)
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        shutil.rmtree(old_cache_dir)

        return cache_size

    def delete(self):
        '''
        Remove cache completely - only useful when removing a base image completely.
        '''
        shutil.rmtree(self._cache_dir)
