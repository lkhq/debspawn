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


def test_container_create_delete(gconfig, testing_container):
    # the "default" container is created by a fixture.
    # what we actually want to do here in future is create and
    # delete containers with special settings
    pass


def test_container_update(gconfig, testing_container):
    ''' Update a container '''

    suite, arch, variant = testing_container
    osbase = OSBase(gconfig, suite, arch, variant)
    assert osbase.update()


def test_container_recreate(gconfig, testing_container):
    ''' Test recreating a container '''

    suite, arch, variant = testing_container
    osbase = OSBase(gconfig, suite, arch, variant)
    assert osbase.recreate()
