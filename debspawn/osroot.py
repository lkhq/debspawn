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
from .utils.command import safe_run


class OSRoot:
    ''' Describes an OS root directory '''

    def __init__(self, suite, arch, variant=None):
        self._suite = suite
        self._arch = arch
        self._variant = variant


    def get_name(self):
        if not self._arch:
            out, _, ret = safe_run(['dpkg-architecture', '-qDEB_HOST_ARCH'])
            self._arch = out.strip()
        if self._variant:
            return '{}-{}-{}'.format(self._suite, self._arch, self._variant)
        else:
            return '{}-{}'.format(self._suite, self._arch)


    @property
    def suite(self) -> str:
        return self._suite

    @property
    def arch(self) -> str:
        return self._arch

    @property
    def variant(self) -> str:
        return self._variant
