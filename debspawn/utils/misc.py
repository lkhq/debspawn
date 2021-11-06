# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2021 Matthias Klumpp <matthias@tenstral.net>
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
import stat
import shutil
import fcntl
import subprocess
from typing import Any, Optional
from pathlib import Path
from contextlib import contextmanager
from ..config import GlobalConfig


def listify(item: Any):
    '''
    Return a list of :item, unless :item already is a lit.
    '''
    if not item:
        return []
    return item if type(item) == list else [item]


@contextmanager
def cd(where):
    ncwd = os.getcwd()
    try:
        yield os.chdir(where)
    finally:
        os.chdir(ncwd)


def random_string(prefix: Optional[str] = None, count: int = 8):
    '''
    Create a string of random alphanumeric characters of a given length,
    separated with a hyphen from an optional prefix.
    '''

    from random import choice
    from string import ascii_lowercase, digits

    if count <= 0:
        count = 1
    rdm_id = ''.join(choice(ascii_lowercase + digits) for _ in range(count))
    if prefix:
        return '{}-{}'.format(prefix, rdm_id)
    return rdm_id


@contextmanager
def temp_dir(basename=None):
    ''' Context manager for a temporary directory in debspawn's temp-dir location.

    This function will also ensure that we will not jump into possibly still
    bind-mounted directories upon deletion, and will unmount those directories
    instead.
    '''

    dir_name = random_string(basename)
    temp_basedir = GlobalConfig().temp_dir
    if not temp_basedir:
        temp_basedir = '/var/tmp/debspawn/'

    tmp_path = os.path.join(temp_basedir, dir_name)
    Path(tmp_path).mkdir(parents=True, exist_ok=True)

    fd = os.open(tmp_path, os.O_RDONLY)
    # we hold a shared lock on the directory to prevent systemd-tmpfiles
    # from deleting it, just in case we are building something for days
    try:
        if fd > 0:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except (IOError, OSError):
        print('WARNING: Unable to lock temporary directory {}'.format(tmp_path),
              file=sys.stderr)
        sys.stderr.flush()

    try:
        yield tmp_path
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            rmtree_mntsafe(tmp_path)
        finally:
            if fd > 0:
                os.close(fd)


def safe_copy(src, dst, *, preserve_mtime: bool = True):
    '''
    Attempt to safely copy a file, by atomically replacing the destination and
    protecting against symlink attacks.
    '''
    dst_tmp = random_string(dst + '.tmp')
    try:
        if preserve_mtime:
            shutil.copy2(src, dst_tmp)
        else:
            shutil.copy(src, dst_tmp)
        if os.path.islink(dst):
            os.remove(dst)
        os.replace(dst_tmp, dst)
    finally:
        try:
            os.remove(dst_tmp)
        except OSError:
            pass


def maybe_remove(f):
    ''' Delete a file if it exists, but do nothing if it doesn't. '''
    try:
        os.remove(f)
    except OSError:
        pass


def format_filesize(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def current_time_string():
    ''' Get the current time as human-readable string. '''

    from datetime import datetime, timezone
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone().strftime('%Y-%m-%d %H:%M:%S UTC%z')


def version_noepoch(version):
    ''' Return version from :version without epoch. '''

    version_noe = version
    if ':' in version_noe:
        version_noe = version_noe.split(':', 1)[1]
    return version_noe


def hardlink_or_copy(src, dst):
    ''' Hardlink a file :src to :dst or copy the file in case linking is not possible '''

    try:
        os.link(src, dst)
    except (PermissionError, OSError):
        shutil.copy2(src, dst)


def is_mountpoint(path) -> bool:
    '''Check if :path is a mountpoint.

    Unlike os.path.ismount, this function will also consider
    bindmountpoints.
    This function may be slow
    '''

    if not os.path.exists(path):
        return False
    if os.path.ismount(path):
        return True

    ret = subprocess.run(['findmnt', '-M', str(path)],
                         capture_output=True,
                         check=False)
    if ret.returncode == 0:
        return True
    return False


def bindmount(from_path, to_path):
    ''' Create a bindmount point.'''

    cmd = ['mount', '--bind', from_path, to_path]
    ret = subprocess.run(cmd, capture_output=True, check=False)
    if ret.returncode != 0:
        raise Exception('Unable to create bindmount {} -> {}'.format(
            from_path, to_path))


def umount(path, lazy: bool = True):
    '''Try to unmount a path.'''

    cmd = ['umount']
    if lazy:
        cmd.append('-l')
    cmd.append(path)
    ret = subprocess.run(cmd, capture_output=True, check=False)
    if ret.returncode != 0:
        raise Exception('Unable to umount path {}'.format(path))

    # try again if the mountpoint is still there, as
    # overmounting may have happened
    if is_mountpoint(path):
        umount(path, lazy=lazy)


def _rmtree_mntsafe_fd(topfd, path, onerror):
    try:
        with os.scandir(topfd) as scandir_it:
            entries = list(scandir_it)
    except OSError as err:
        err.filename = path
        onerror(os.scandir, path, sys.exc_info())
        return
    for entry in entries:
        fullname = os.path.join(path, entry.name)
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            is_dir = False
        else:
            if is_dir:
                try:
                    orig_st = entry.stat(follow_symlinks=False)
                    is_dir = stat.S_ISDIR(orig_st.st_mode)
                except OSError:
                    onerror(os.lstat, fullname, sys.exc_info())
                    continue
        if is_dir:
            if is_mountpoint(fullname):
                try:
                    umount(fullname)
                    orig_st = os.stat(fullname, follow_symlinks=False)
                except Exception:
                    onerror(umount, fullname, sys.exc_info())
                    continue

            try:
                dirfd = os.open(entry.name, os.O_RDONLY, dir_fd=topfd)
            except OSError:
                onerror(os.open, fullname, sys.exc_info())
            else:
                try:
                    if os.path.samestat(orig_st, os.fstat(dirfd)):
                        _rmtree_mntsafe_fd(dirfd, fullname, onerror)
                        try:
                            os.rmdir(entry.name, dir_fd=topfd)
                        except OSError:
                            onerror(os.rmdir, fullname, sys.exc_info())
                    else:
                        try:
                            # This can only happen if someone replaces
                            # a directory with a symlink after the call to
                            # os.scandir or stat.S_ISDIR above.
                            raise OSError("Cannot call rmtree on a symbolic "
                                          "link")
                        except OSError:
                            onerror(os.path.islink, fullname, sys.exc_info())
                finally:
                    os.close(dirfd)
        else:
            try:
                os.unlink(entry.name, dir_fd=topfd)
            except OSError:
                onerror(os.unlink, fullname, sys.exc_info())


def rmtree_mntsafe(path, ignore_errors=False, onerror=None):
    '''Recursively delete a directory tree, unmounting mount points if possible.
    This function is based on shutil.rmtree, but will not jump into mount points,
    but instead try to unmount them and if that fails leave them alone.
    This prevents data loss in case bindmounts were set carelessly.

    If ignore_errors is set, errors are ignored; otherwise, if onerror
    is set, it is called to handle the error with arguments (func,
    path, exc_info) where func is platform and implementation dependent;
    path is the argument to that function that caused it to fail; and
    exc_info is a tuple returned by sys.exc_info().  If ignore_errors
    is false and onerror is None, an exception is raised.
    '''
    if ignore_errors:
        # pylint: disable=function-redefined
        def onerror(*args):
            pass
    elif onerror is None:
        # pylint: disable=misplaced-bare-raise
        def onerror(*args):
            raise

    # While the unsafe rmtree works fine on bytes, the fd based does not.
    if isinstance(path, bytes):
        path = os.fsdecode(path)

    if os.path.ismount(path):
        try:
            umount(path)
        except Exception:
            onerror(umount, path, sys.exc_info())
            return

    # Note: To guard against symlink races, we use the standard
    # lstat()/open()/fstat() trick.
    try:
        orig_st = os.lstat(path)
    except Exception:
        onerror(os.lstat, path, sys.exc_info())
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except Exception:
        onerror(os.open, path, sys.exc_info())
        return
    try:
        if os.path.samestat(orig_st, os.fstat(fd)):
            _rmtree_mntsafe_fd(fd, path, onerror)
            try:
                os.rmdir(path)
            except OSError:
                onerror(os.rmdir, path, sys.exc_info())
        else:
            try:
                # symlinks to directories are forbidden, see bug #1669
                raise OSError("Cannot call rmtree on a symbolic link")
            except OSError:
                onerror(os.path.islink, path, sys.exc_info())
    finally:
        os.close(fd)
