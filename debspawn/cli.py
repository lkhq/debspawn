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
from argparse import ArgumentParser
from .config import GlobalConfig
from .osbase import OSBase


def _get_config(mainfile, conf_file=None):
    gconf = GlobalConfig()
    gconf.load(conf_file)

    if not mainfile.startswith('/usr'):
        gconf.dsrun_path = os.path.normpath(os.path.join(mainfile, '..', 'dsrun', 'dsrun.py'))
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
        gconf = _get_config(mainfile, options.config)
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
        gconf = _get_config(mainfile, options.config)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = osbase.update()
        if not r:
            sys.exit(2)
    elif cmdname == 'build':
        from .build import build_dir

        parser.add_argument('--variant', action='store', dest='variant', default=None,
                        help='Set the bootstrap script variant to use for generating the root fs.')
        parser.add_argument('--arch', action='store', dest='arch', default=None,
                        help='The architecture to bootstrap for.')
        parser.add_argument('suite', action='store', nargs='?', default=None,
                        help='The suite to bootstrap.')
        parser.add_argument('directory', action='store', nargs='?', default=None,
                        help='The directory.')

        options = parser.parse_args(cmdargs)
        if not options.suite:
            print('Need at least a suite name for building!')
            sys.exit(1)
        gconf = _get_config(mainfile, options.config)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = build_dir(osbase, options.directory)
        if not r:
            sys.exit(2)
    elif cmdname == 'run':
        pass
    else:
        print('Command "{}" is unknown.'.format(cmdname))
        sys.exit(1)
