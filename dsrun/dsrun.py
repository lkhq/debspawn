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
from argparse import ArgumentParser
from glob import glob


BUILD_USER = 'builder'


def call(cmd):
    print(' ! {}'.format(cmd))
    r = os.system(cmd)
    if r != 0:
        sys.exit(r)


def drop_privileges():
    pwn = pwd.getpwnam(BUILD_USER)
    uid = pwn.pw_uid
    os.setuid(uid)

    os.system('whoami')


def update_container():
    call('apt-get update -q')
    call('apt-get full-upgrade -q --yes')
    call('apt-get install build-essential --no-install-recommends -q --yes')

    try:
        pwd.getpwnam(BUILD_USER)
    except KeyError:
        print('No "{}" user, creating it.'.format(BUILD_USER))
        call('adduser --system --no-create-home --disabled-password {}'.format(BUILD_USER))

    call('mkdir -p /srv/build')
    call('chown {} /srv/build'.format(BUILD_USER))

    return True


def main():
    if not os.environ.get('container'):
        print('This helper script must be run in a systemd-nspawn container.')
        return 1

    parser = ArgumentParser(description='DebSpawn helper script')
    parser.add_argument('--update', action='store_true', dest='update',
                        help='Initialize the container.')
    parser.add_argument('--build', dest='build', default=None,
                        help='Build a Debian package.')

    options = parser.parse_args(sys.argv[1:])
    if options.update:
        r = update_container()
        if not r:
            return 2
    elif options.build:
        call('apt update')
        call('apt full-upgrade -q --yes')

        call('apt install --no-install-recommends dpkg-dev fakeroot -q --yes')
        os.chdir('/srv/build')

        #for f in glob('/srv/build/*'):
        #    os.system('rm -r {}'.format(f))

        call('chown -R {} /srv/build'.format(BUILD_USER))
        #call('sudo -u {} apt-get source {}'.format(BUILD_USER, sys.argv[1]))
        for f in glob('./*'):
            if os.path.isdir(f):
                os.chdir(f)
                break

        call('apt-get build-dep -q --yes ./')

        #drop_privileges()
        call('sudo -u {} dpkg-buildpackage'.format(BUILD_USER))

    return 0


if __name__ == '__main__':
    sys.exit(main())
