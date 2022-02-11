# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2022 Matthias Klumpp <matthias@tenstral.net>
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
import tempfile
from debspawn.utils.misc import bindmount, umount, is_mountpoint, rmtree_mntsafe


def test_bindmount_umount(gconfig):
    with tempfile.TemporaryDirectory() as src_tmpdir1:
        with tempfile.TemporaryDirectory() as src_tmpdir2:
            with tempfile.TemporaryDirectory() as dest_tmpdir:
                bindmount(src_tmpdir1, dest_tmpdir)
                assert is_mountpoint(dest_tmpdir)

                bindmount(src_tmpdir2, dest_tmpdir)
                assert is_mountpoint(dest_tmpdir)

                # sanity check
                open(os.path.join(src_tmpdir2, 'test'), 'a').close()
                assert os.path.isfile(os.path.join(dest_tmpdir, 'test'))

                # umount is supposed to unmount everything, even overmounted directories
                umount(dest_tmpdir)
                assert not is_mountpoint(dest_tmpdir)


def test_rmtree_mntsafe(gconfig):
    mnt_tmpdir = tempfile.TemporaryDirectory().name
    dest_tmpdir = tempfile.TemporaryDirectory().name

    # create directory structure and files to delete
    mp_dir = os.path.join(dest_tmpdir, 'subdir', 'mountpoint')
    mount_subdir = os.path.join(mnt_tmpdir, 'subdir_in_mount')
    os.makedirs(mp_dir)
    os.makedirs(mount_subdir)
    open(os.path.join(dest_tmpdir, 'file1.txt'), 'a').close()
    open(os.path.join(mp_dir, 'file_below_mountpoint.txt'), 'a').close()
    open(os.path.join(mnt_tmpdir, 'file_in_mount.txt'), 'a').close()
    open(os.path.join(mount_subdir, 'file_in_mount_subdir.txt'), 'a').close()

    # create bindmount
    bindmount(mnt_tmpdir, mp_dir)
    assert is_mountpoint(mp_dir)

    # try to delete the directory structure containing bindmounts
    rmtree_mntsafe(dest_tmpdir)

    # verify
    assert not os.path.exists(dest_tmpdir)
    assert os.path.isfile(os.path.join(mnt_tmpdir, 'file_in_mount.txt'))
    assert os.path.isfile(os.path.join(mount_subdir, 'file_in_mount_subdir.txt'))

    # cleanup mounted dir
    rmtree_mntsafe(mnt_tmpdir)
    assert not os.path.exists(mnt_tmpdir)
