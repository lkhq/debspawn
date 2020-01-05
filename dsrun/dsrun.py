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
import shlex
import subprocess
from contextlib import contextmanager
from argparse import ArgumentParser
from glob import glob


BUILD_USER = 'builder'


#
# Globals
#

unicode_enabled = True
color_enabled = True


def run_command(cmd, env=None):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    proc_env = env
    if proc_env:
        proc_env = os.environ.copy()
        proc_env.update(env)

    p = subprocess.run(cmd, env=proc_env)
    if p.returncode != 0:
        print('Command `{}` failed.'.format(' '.join(cmd)))
        sys.exit(p.returncode)


def run_apt_command(cmd):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    env = {'DEBIAN_FRONTEND': 'noninteractive'}
    apt_cmd = ['apt-get',
               '-uyq',
               '-o Dpkg::Options::="--force-confnew"']
    apt_cmd.extend(cmd)

    run_command(apt_cmd, env)


def print_textbox(title, tl, hline, tr, vline, bl, br):
    def write_utf8(s):
        sys.stdout.buffer.write(s.encode('utf-8'))

    tlen = len(title)
    write_utf8('\n{}'.format(tl))
    write_utf8(hline * (10 + tlen))
    write_utf8('{}\n'.format(tr))

    write_utf8('{}  {}'.format(vline, title))
    write_utf8(' ' * 8)
    write_utf8('{}\n'.format(vline))

    write_utf8(bl)
    write_utf8(hline * (10 + tlen))
    write_utf8('{}\n'.format(br))

    sys.stdout.flush()


def print_header(title):
    global unicode_enabled

    if unicode_enabled:
        print_textbox(title, '╔', '═', '╗', '║', '╚', '╝')
    else:
        print_textbox(title, '+', '═', '+', '|', '+', '+')


def print_section(title):
    global unicode_enabled

    if unicode_enabled:
        print_textbox(title, '┌', '─', '┐', '│', '└', '┘')
    else:
        print_textbox(title, '+', '-', '+', '|', '+', '+')


@contextmanager
def eatmydata():
    try:
        # FIXME: We just override the env vars here, appending to them would
        # be much cleaner.
        os.environ['LD_LIBRARY_PATH'] = '/usr/lib/libeatmydata'
        os.environ['LD_PRELOAD'] = 'libeatmydata.so'
        yield
    finally:
        del os.environ['LD_LIBRARY_PATH']
        del os.environ['LD_PRELOAD']


def update_container():
    with eatmydata():
        run_apt_command('update')
        run_apt_command('full-upgrade')

        run_apt_command(['install', '--no-install-recommends',
                         'build-essential', 'dpkg-dev', 'fakeroot', 'eatmydata'])

        run_apt_command(['--purge', 'autoremove'])
        run_apt_command('clean')

    try:
        pwd.getpwnam(BUILD_USER)
    except KeyError:
        print('No "{}" user, creating it.'.format(BUILD_USER))
        run_command('adduser --system --no-create-home --disabled-password {}'.format(BUILD_USER))

    run_command('mkdir -p /srv/build')
    run_command('chown {} /srv/build'.format(BUILD_USER))

    return True


def prepare_run():
    print_section('Preparing container')

    with eatmydata():
        run_apt_command('update')
        run_apt_command('full-upgrade')

    return True


def prepare_package_build(arch_only=False, qa_lintian=False):
    print_section('Preparing container for build')

    with eatmydata():
        run_apt_command('update')
        run_apt_command('full-upgrade')
        run_apt_command(['install', '--no-install-recommends',
                         'build-essential', 'dpkg-dev', 'fakeroot'])

        # if we want to run Lintian later, we need to make sure it is installed
        if qa_lintian:
            run_apt_command(['install', 'lintian'])

    os.chdir('/srv/build')

    run_command('chown -R {} /srv/build'.format(BUILD_USER))
    for f in glob('./*'):
        if os.path.isdir(f):
            os.chdir(f)
            break

    print_section('Installing package build-dependencies')
    with eatmydata():
        cmd = ['build-dep']
        if arch_only:
            cmd.append('--arch-only')
        cmd.append('./')
        run_apt_command(cmd)

    return True


def build_package(buildflags=None):
    print_section('Build')

    os.chdir('/srv/build')
    for f in glob('./*'):
        if os.path.isdir(f):
            os.chdir(f)
            break

    cmd = ['dpkg-buildpackage']
    if buildflags:
        cmd.extend(buildflags)
    run_command(cmd)

    # run_command will exit the whole program if the command failed,
    # so we can return True here (everything went fine if we are here)
    return True


def run_qatasks(qa_lintian=True):
    ''' Run QA tasks on a built package immediately after build (currently Lintian) '''
    os.chdir('/srv/build')
    for f in glob('./*'):
        if os.path.isdir(f):
            os.chdir(f)
            break

    if qa_lintian:
        print_section('QA: Lintian')

        # ensure Lintian is really installed
        run_apt_command(['install', 'lintian'])

        # drop privileges
        pw = pwd.getpwnam(BUILD_USER)
        os.seteuid(pw.pw_uid)

        cmd = ['lintian',
               '-I',  # infos by default
               '--pedantic',  # pedantic hints by default,
               '--no-tag-display-limit'  # display all tags found (even if that may be a lot occasionally)
               ]
        run_command(cmd)

    # run_command will exit the whole program if the command failed,
    # so we can return True here (everything went fine if we are here)
    return True


def setup_environment(use_color=True, use_unicode=True):
    os.environ['LANG'] = 'C.UTF-8' if use_unicode else 'C'
    os.environ['HOME'] = '/nonexistent'

    os.environ['TERM'] = 'xterm-256color' if use_color else 'xterm-mono'
    os.environ['SHELL'] = '/bin/sh'

    del os.environ['LOGNAME']


def main():
    if not os.environ.get('container'):
        print('This helper script must be run in a systemd-nspawn container.')
        return 1

    parser = ArgumentParser(description='DebSpawn helper script')
    parser.add_argument('--update', action='store_true', dest='update',
                        help='Initialize the container.')
    parser.add_argument('--no-color', action='store_true', dest='no_color',
                        help='Disable terminal colors.')
    parser.add_argument('--no-unicode', action='store_true', dest='no_unicode',
                        help='Disable unicode support.')
    parser.add_argument('--arch-only', action='store_true', dest='arch_only', default=None,
                        help='Only get arch-dependent packages (used when satisfying build dependencies).')
    parser.add_argument('--build-prepare', action='store_true', dest='build_prepare',
                        help='Prepare building a Debian package.')
    parser.add_argument('--build-run', action='store_true', dest='build_run',
                        help='Build a Debian package.')
    parser.add_argument('--lintian', action='store_true', dest='qa_lintian',
                        help='Run Lintian on the generated package.')
    parser.add_argument('--buildflags', action='store', dest='buildflags', default=None,
                        help='Flags passed to dpkg-buildpackage.')
    parser.add_argument('--prepare-run', action='store_true', dest='prepare_run',
                        help='Prepare container image for generic script run.')
    parser.add_argument('--run-qa', action='store_true', dest='run_qatasks',
                        help='Run QA tasks (only Lintian currently) against a package.')

    options = parser.parse_args(sys.argv[1:])

    # initialize environment defaults
    global unicode_enabled, color_enabled
    unicode_enabled = not options.no_unicode
    color_enabled = not options.no_color
    setup_environment(color_enabled, unicode_enabled)

    if options.update:
        r = update_container()
        if not r:
            return 2
    elif options.build_prepare:
        r = prepare_package_build(options.arch_only, options.qa_lintian)
        if not r:
            return 2
    elif options.build_run:
        buildflags = []
        if options.buildflags:
            buildflags = shlex.split(options.buildflags)
        r = build_package(buildflags)
        if not r:
            return 2
    elif options.prepare_run:
        r = prepare_run()
        if not r:
            return 2
    elif options.run_qatasks:
        r = run_qatasks(qa_lintian=options.qa_lintian)
        if not r:
            return 2
    else:
        print('ERROR: No action specified.')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
