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
import sys
import toml


thisfile = __file__
if not os.path.isabs(thisfile):
    thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))


__all__ = ['GlobalConfig']


class GlobalConfig:
    '''
    Global configuration singleton affecting all of Debspawn.
    '''

    _instance = None

    class __GlobalConfig:
        def load(self, fname=None):
            if not fname:
                fname = '/etc/debspawn/global.toml'

            cdata = {}
            if os.path.isfile(fname):
                with open(fname) as f:
                    try:
                        cdata = toml.load(f)
                    except toml.TomlDecodeError as e:
                        print('Unable to parse global configuration (global.toml): {}'.format(str(e)), file=sys.stderr)
                        sys.exit(8)

            self._dsrun_path = os.path.normpath(os.path.join(thisfile, '..', 'dsrun'))
            if not os.path.isfile(self._dsrun_path):
                print('Debspawn is not set up properly: Unable to find file "{}". Can not continue.'.format(self._dsrun_path), file=sys.stderr)
                sys.exit(4)

            self._osroots_dir = cdata.get('OSImagesDir', '/var/lib/debspawn/containers/')
            self._results_dir = cdata.get('ResultsDir', '/var/lib/debspawn/results/')
            self._aptcache_dir = cdata.get('APTCacheDir', '/var/lib/debspawn/aptcache/')
            self._injected_pkgs_dir = cdata.get('InjectedPkgsDir', '/var/lib/debspawn/injected-pkgs/')
            self._temp_dir = cdata.get('TempDir', '/var/tmp/debspawn/')
            self._allow_unsafe_perms = cdata.get('AllowUnsafePermissions', False)

            self._syscall_filter = cdata.get('SyscallFilter', 'compat')
            if self._syscall_filter == 'compat':
                # permit some system calls known to be needed by packages that sbuild & Co.
                # build without problems.
                self._syscall_filter = ['@memlock',
                                        '@pkey',
                                        '@clock',
                                        '@cpu-emulation']
            elif self._syscall_filter == 'nspawn-default':
                # make no additional changes, so nspawn's built-in defaults are used
                self._syscall_filter = []
            else:
                if type(self._syscall_filter) is not list:
                    print('Configuration error (global.toml): Entry "SyscallFilter" needs to be either a string value ("compat" or "nspawn-default"), ' +
                          'or a list of permissible system call names as listed by the syscall-filter command of systemd-analyze(1)', file=sys.stderr)
                    sys.exit(8)

        @property
        def dsrun_path(self) -> str:
            return self._dsrun_path

        @dsrun_path.setter
        def dsrun_path(self, v) -> str:
            self._dsrun_path = v

        @property
        def osroots_dir(self) -> str:
            return self._osroots_dir

        @property
        def results_dir(self) -> str:
            return self._results_dir

        @property
        def aptcache_dir(self) -> str:
            return self._aptcache_dir

        @property
        def injected_pkgs_dir(self) -> str:
            return self._injected_pkgs_dir

        @property
        def temp_dir(self) -> str:
            return self._temp_dir

        @property
        def syscall_filter(self) -> list:
            return self._syscall_filter

        @property
        def allow_unsafe_perms(self) -> bool:
            return self._allow_unsafe_perms

    def __init__(self, fname=None):
        if not GlobalConfig._instance:
            GlobalConfig._instance = GlobalConfig.__GlobalConfig()
            GlobalConfig._instance.load(fname)

    def __getattr__(self, name):
        return getattr(self._instance, name)
