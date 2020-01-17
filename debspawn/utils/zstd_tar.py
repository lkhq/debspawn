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

import shutil
from .command import run_command


def ensure_tar_zstd():
    ''' Check if the required binaries for compression are available '''

    if not shutil.which('zstd'):
        raise Exception('The "zsdt" binary was not found, we can not compress tarballs. Please install zstd to continue!')
    if not shutil.which('tar'):
        raise Exception('The "tar" binary was not found, we can not create tarballs. Please install tar to continue!')


def compress_directory(dirname, tarname):
    ''' Compress a directory to a given tarball '''

    cmd = ['tar',
           '-C', dirname,
           '-I', 'zstd',
           '-cf', tarname,
           '.']

    out, err, ret = run_command(cmd)

    if ret != 0:
        raise Exception('Unable to create tarball "{}":\n{}{}'.format(tarname, out, err))


def decompress_tarball(tarname, dirname):
    ''' Compress a directory to a given tarball '''

    cmd = ['tar',
           '-C', dirname,
           '-I', 'zstd',
           '-xf', tarname]

    out, err, ret = run_command(cmd)

    if ret != 0:
        raise Exception('Unable to decompress tarball "{}":\n{}{}'.format(tarname, out, err))
