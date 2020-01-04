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

from debspawn.osbase import OSBase


def test_container_create(gconfig):
    components = ['main', 'contrib', 'non-free']
    extra_suites = []

    osbase = OSBase(gconfig,
                    'testing',
                    'amd64',
                    variant='minbase',
                    base_suite=None)
    r = osbase.create(None,
                      components,
                      extra_suites,
                      None)
    assert r