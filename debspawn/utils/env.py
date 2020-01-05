# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2020 Matthias Klumpp <matthias@tenstral.net>
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
import shutil
from contextlib import contextmanager


_unicode_allowed = True  # store whether we are allowed to use unicode
_owner_uid = 0  # uid of the user on whose behalf we are running
_owner_gid = 0  # gid of the user on whose behalf we are running


def set_owning_user(user, group=None):
    '''
    Set the user on whose behalf we are running.
    This is useful so we can drop privileges to
    the perticular user in many cases.
    '''
    from pwd import getpwnam, getpwuid
    from grp import getgrnam

    if user.isdecimal():
        uid = int(user)
    else:
        uid = getpwnam(user).pw_uid

    if not group:
        gid = getpwuid(uid).pw_gid
    elif group.isdecimal():
        gid = int(group)
    else:
        gid = getgrnam(group).gr_gid

    global _owner_uid
    global _owner_gid
    _owner_uid = uid
    _owner_gid = gid


def ensure_root():
    '''
    Ensure we are running as root and all code following
    this function is privileged.
    '''
    if os.geteuid() == 0:
        return

    args = sys.argv.copy()

    owner_set = any(a.startswith('--owner=') for a in sys.argv)
    if owner_set:
        # we don't override an owner explicitly set by the user
        args = sys.argv.copy()
    else:
        args = [sys.argv[0]]

        # set flag to tell the new process who it can impersonate
        # for unprivileged actions. It it is root, just omit the flag.
        uid = os.getuid()
        gid = os.getgid()
        if uid != 0 or gid != 0:
            args.append('--owner={}:{}'.format(uid, gid))
        args.extend(sys.argv[1:])

    def filter_env_far(result, name):
        value = os.environ.get(name)
        if not value:
            return
        result.append('{}={}'.format(name, shlex.quote(value)))

    if shutil.which('sudo'):
        # Filter "good" environment variables that we want to have after running sudo.
        # Most of those are standard variables affecting debsign bahevior later, in case
        # the user has requested signing
        import shlex
        env = []
        filter_env_far(env, 'DEBEMAIL')
        filter_env_far(env, 'DEBFULLNAME')
        filter_env_far(env, 'GPGKEY')
        filter_env_far(env, 'GPG_AGENT_INFO')

        os.execvp("sudo", ["sudo"] + env + args)
    else:
        print('This command needs to be run as root.')
        sys.exit(1)


@contextmanager
def switch_unprivileged():
    '''
    Run actions using the unprivileged user ID
    on the behalf of which we are running.
    This is NOT a security feature!
    '''
    import pwd

    global _owner_uid
    global _owner_gid

    if _owner_uid == 0 and _owner_gid == 0:
        # we can't really do much here, we have to run
        # as root, as we don't know an unprivileged user
        # to switch to

        yield
    else:
        orig_egid = os.getegid()
        orig_euid = os.geteuid()
        orig_home = os.environ.get('HOME')
        if not orig_home:
            orig_home = pwd.getpwuid(os.getuid()).pw_dir

        try:
            os.setegid(_owner_gid)
            os.seteuid(_owner_uid)
            os.environ['HOME'] = pwd.getpwuid(_owner_uid).pw_dir

            yield
        finally:
            os.setegid(orig_egid)
            os.seteuid(orig_euid)
            os.environ['HOME'] = orig_home


def get_owner_uid_gid():
    global _owner_uid
    global _owner_gid

    return _owner_uid, _owner_gid


def colored_output_allowed():
    return (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()) or \
           ('TERM' in os.environ and os.environ['TERM'] == 'ANSI')


def unicode_allowed():
    global _unicode_allowed
    return _unicode_allowed


def set_unicode_allowed(val):
    global _unicode_allowed
    _unicode_allowed = val


def get_free_space(path):
    '''
    Return free space of :path
    '''
    real_path = os.path.realpath(path)
    stat = os.statvfs(real_path)
    # get free space in MiB.
    free_space = float(stat.f_bsize * stat.f_bavail)
    return free_space


def get_tree_size(path):
    '''
    Return total size of files in path and subdirs. If
    is_dir() or stat() fails, print an error message to stderr
    and assume zero size (for example, file has been deleted).
    '''
    total = 0
    for entry in os.scandir(path):
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError as error:
            print('Error calling is_dir():', error, file=sys.stderr)
            continue
        if is_dir:
            total += get_tree_size(entry.path)
        else:
            try:
                total += entry.stat(follow_symlinks=False).st_size
            except OSError as error:
                print('Error calling stat():', error, file=sys.stderr)
    return total
