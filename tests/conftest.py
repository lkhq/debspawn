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
import sys
import pytest


@pytest.fixture(scope='session', autouse=True)
def gconfig():
    '''
    Ensure the global config object is set up properly for unit-testing.
    '''
    import shutil
    import debspawn.cli
    from . import source_root

    debspawn.cli.__mainfile = os.path.join(source_root, 'debspawn.py')

    class MockOptions:
        config = None
        no_unicode = False
        owner = None

    gconf = debspawn.cli.init_config(MockOptions())

    test_tmp_dir = '/tmp/debspawn-test/'
    shutil.rmtree(test_tmp_dir, ignore_errors=True)
    os.makedirs(test_tmp_dir)

    gconf._osroots_dir = os.path.join(test_tmp_dir, 'containers/')
    gconf._results_dir = os.path.join(test_tmp_dir, 'results/')
    gconf._aptcache_dir = os.path.join(test_tmp_dir, 'aptcache/')

    return gconf


@pytest.fixture(scope='session', autouse=True)
def ensure_root():
    '''
    Ensure we run with superuser permissions.
    '''

    if os.geteuid() != 0:
        print('The testsuite has to be run with superuser permissions in order to create nspawn instances.')
        sys.exit(1)
