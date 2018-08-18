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
import logging as log
from argparse import ArgumentParser
from .config import GlobalConfig
from .utils.misc import set_unicode_allowed
from .osbase import OSBase


def init_config(mainfile, options):
    gconf = GlobalConfig()
    gconf.load(options.config)

    if not mainfile.startswith('/usr'):
        gconf.dsrun_path = os.path.normpath(os.path.join(mainfile, '..', 'dsrun', 'dsrun.py'))

    # check if we are forbidden from using unicode - otherwise we build
    # with unicode enabled by default
    if options.no_unicode:
        set_unicode_allowed(False)
    else:
        if not 'utf-8' in os.environ.get('LANG', 'utf-8').lower():
            log.warning('Building with unicode support, but your environment does not seem to support unicode.')
        set_unicode_allowed(True)

    return gconf


def run(mainfile, args):
    if len(args) == 0:
        print('Need a subcommand to proceed!')
        sys.exit(1)
    cmdname = args[0]
    cmdargs = args[1:]

    parser = ArgumentParser(description='Build in nspawn containers')
    parser.add_argument('--config', action='store', dest='config', default=None,
                        help='Path to the global config file.')
    parser.add_argument('--verbose', action='store_true', dest='verbose',
                        help='Enable debug messages.')
    parser.add_argument('--no-unicode', action='store_true', dest='no_unicode',
                        help='Enable debug messages.')


    if cmdname == 'new':
        parser.add_argument('--variant', action='store', dest='variant', default=None,
                        help='Set the bootstrap script variant to use for generating the root fs.')
        parser.add_argument('--mirror', action='store', dest='mirror', default=None,
                        help='Set a specific mirror to bootstrap from.')
        parser.add_argument('suite', action='store', nargs='?', default=None,
                        help='The suite to bootstrap.')
        parser.add_argument('arch', action='store', nargs='?', default=None,
                        help='The architecture to bootstrap for.')

        options = parser.parse_args(cmdargs)
        if not options.suite:
            print('Need at least a suite name to bootstrap!')
            sys.exit(1)
        gconf = init_config(mainfile, options)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = osbase.create(options.mirror)
        if not r:
            sys.exit(2)
    elif cmdname == 'update':
        parser.add_argument('--variant', action='store', dest='variant', default=None,
                        help='Set the bootstrap script variant to use for generating the root fs.')
        parser.add_argument('suite', action='store', nargs='?', default=None,
                        help='The suite to bootstrap.')
        parser.add_argument('arch', action='store', nargs='?', default=None,
                        help='The architecture to bootstrap for.')

        options = parser.parse_args(cmdargs)
        if not options.suite:
            print('Need at least a suite name for update!')
            sys.exit(1)
        gconf = init_config(mainfile, options)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = osbase.update()
        if not r:
            sys.exit(2)
    elif cmdname == 'build':
        from .build import build_from_directory, build_from_dsc

        parser.add_argument('--variant', action='store', dest='variant', default=None,
                        help='Set the bootstrap script variant to use for generating the root fs.')
        parser.add_argument('--arch', action='store', dest='arch', default=None,
                        help='The architecture to bootstrap for.')
        parser.add_argument('suite', action='store', nargs='?', default=None,
                        help='The suite to bootstrap.')
        parser.add_argument('target', action='store', nargs='?', default=None,
                        help='The source package file or source directory to build.')

        options = parser.parse_args(cmdargs)
        if not options.suite:
            print('Need at least a suite name for building!')
            sys.exit(1)
        gconf = init_config(mainfile, options)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)

        if not options.target or os.path.isdir(options.target):
            r = build_from_directory(osbase, options.target)
        else:
            r = build_from_dsc(osbase, options.target)
        if not r:
            sys.exit(2)
    elif cmdname == 'run':
        pass
    elif cmdname == 'login':
        pass
    else:
        print('Command "{}" is unknown.'.format(cmdname))
        sys.exit(1)
