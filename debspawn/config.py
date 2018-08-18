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

import json
import os
import platform
from typing import List
from pathlib import Path
import logging as log


class GlobalConfig:
    """
    Global configuration affecting all of DebSpawn.
    """

    def load(self, fname=None):
        if not fname:
            fname = '/etc/debspawn/global.json'

        jdata = {}
        if os.path.isfile(fname):
            with open(fname) as json_file:
                jdata = json.load(json_file)

        self._osroots_dir = jdata.get('OSRootsDir', '/var/lib/debspawn/containers/')
        self._results_dir = jdata.get('ResultsDir', '/var/lib/debspawn/results/')
        self._aptcache_dir = jdata.get('APTCacheDir', '/var/lib/debspawn/aptcache/')
        self._dsrun_path  = '/usr/lib/debspawn/dsrun.py'

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
