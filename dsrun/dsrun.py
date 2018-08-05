#!/usr/bin/env python3
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
import sys
import pwd
import subprocess
from contextlib import contextmanager
from argparse import ArgumentParser
from glob import glob


BUILD_USER = 'builder'


def run_command_capture(command, input=None):
    if not isinstance(command, list):
        command = shlex.split(command)

    if not input:
        input = None
    elif isinstance(input, str):
        input = input.encode('utf-8')
    elif not isinstance(input, bytes):
        input = input.read()

    try:
        pipe = subprocess.Popen(command,
                                shell=False,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                )
    except OSError:
        return (None, None, -1)

    (output, stderr) = pipe.communicate(input=input)
    (output, stderr) = (c.decode('utf-8', errors='ignore') for c in (output, stderr))
    return (output, stderr, pipe.returncode)


def safe_run_capture(cmd, input=None, expected=0):
    if not isinstance(expected, tuple):
        expected = (expected, )

    out, err, ret = run_command_capture(cmd, input=input)

    if ret not in expected:
        raise SubprocessError(out, err, ret, cmd)

    return out, err, ret


def run_command(cmd):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    #print(' ! {}'.format(cmd))
    p = subprocess.run(cmd)
    if p.returncode != 0:
        print('Command `{}` failed.'.format(' '.join(cmd)))
        sys.exit(r)


def detect_dpkg_architecture():
    out, _, ret = safe_run_capture(['dpkg-architecture', '-qDEB_HOST_ARCH'])
    return out.strip()


def print_textbox(title, tl, hline, tr, vline, bl, br):
    def write_utf8(s):
        sys.stdout.buffer.write(s.encode('utf-8'))

    l = len(title)
    write_utf8('\n{}'.format(tl))
    write_utf8(hline * (10 + l))
    write_utf8('{}\n'.format(tr))

    write_utf8('{}  {}'.format(vline, title))
    write_utf8(' ' * 8)
    write_utf8('{}\n'.format(vline))

    write_utf8(bl)
    write_utf8(hline * (10 + l))
    write_utf8('{}\n'.format(br))

    sys.stdout.flush()


def print_header(title):
    print_textbox(title, '╔', '═', '╗', '║', '╚', '╝')


def print_section(title):
    print_textbox(title, '┌', '─', '┐', '│', '└', '┘')


@contextmanager
def eatmydata():
    try:
        # FIXME: We just oferride the env vars here, maybe just appending
        # to them is much better
        os.environ['LD_LIBRARY_PATH'] = '/usr/lib/libeatmydata'
        os.environ['LD_PRELOAD'] = 'libeatmydata.so'
        yield
    finally:
        del os.environ['LD_LIBRARY_PATH']
        del os.environ['LD_PRELOAD']


def drop_privileges():
    pwn = pwd.getpwnam(BUILD_USER)
    uid = pwn.pw_uid
    os.setuid(uid)

    os.environ['USER'] = BUILD_USER
    os.environ['HOME'] = '/nonexistent'  # ensure HOME is invalid


def update_container():
    print_header('Updating container contents')

    run_command('apt-get update -q')
    run_command('apt-get full-upgrade -q --yes')
    run_command(['apt-get', 'install', '--no-install-recommends', '-q', '--yes',
                     'build-essential', 'dpkg-dev', 'fakeroot', 'eatmydata'])

    try:
        pwd.getpwnam(BUILD_USER)
    except KeyError:
        print('No "{}" user, creating it.'.format(BUILD_USER))
        run_command('adduser --system --no-create-home --disabled-password {}'.format(BUILD_USER))

    run_command('mkdir -p /srv/build')
    run_command('chown {} /srv/build'.format(BUILD_USER))

    return True


def build_package():
    print_header('Package build')
    print('Package: {}'.format('?'))
    print('Version: {}'.format('?'))
    print('Distribution: {}'.format('?'))
    print('Architecture: {}'.format(detect_dpkg_architecture()))

    print_section('Preparing container for build')

    with eatmydata():
        run_command('apt-get update -q')
        run_command('apt-get full-upgrade -q --yes')
        run_command(['apt-get', 'install', '--no-install-recommends', '-q', '--yes',
                     'build-essential', 'dpkg-dev', 'fakeroot', 'eatmydata'])

    os.chdir('/srv/build')

    run_command('chown -R {} /srv/build'.format(BUILD_USER))
    #run_command('sudo -u {} apt-get source {}'.format(BUILD_USER, sys.argv[1]))
    for f in glob('./*'):
        if os.path.isdir(f):
            os.chdir(f)
            break

    print_section('Installing package build-dependencies')
    with eatmydata():
        run_command('apt-get build-dep -q --yes ./')

    print_section('Build')

    drop_privileges()
    run_command('dpkg-buildpackage')

    return True


def setup_environment():
    os.environ['LANG'] = 'C.UTF-8'
    os.environ['HOME'] = '/nonexistent'

    del os.environ['LOGNAME']


def main():
    if not os.environ.get('container'):
        print('This helper script must be run in a systemd-nspawn container.')
        return 1

    parser = ArgumentParser(description='DebSpawn helper script')
    parser.add_argument('--update', action='store_true', dest='update',
                        help='Initialize the container.')
    parser.add_argument('--build', dest='build', default=None,
                        help='Build a Debian package.')

    setup_environment()

    options = parser.parse_args(sys.argv[1:])
    if options.update:
        r = update_container()
        if not r:
            return 2
    elif options.build:
        r = build_package()
        if not r:
            return 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
