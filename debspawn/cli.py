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


def add_container_select_arguments(parser):
    parser.add_argument('--variant', action='store', dest='variant', default=None,
                        help='Set the bootstrap script variant.')
    parser.add_argument('--arch', action='store', dest='arch', default=None,
                        help='The architecture of the container.')
    parser.add_argument('suite', action='store', nargs='?', default=None,
                        help='The suite name of the container.')


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

    # handle subcommands
    if cmdname == 'new':
        add_container_select_arguments(parser)
        parser.add_argument('--mirror', action='store', dest='mirror', default=None,
                        help='Set a specific mirror to bootstrap from.')

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
        add_container_select_arguments(parser)

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

        add_container_select_arguments(parser)
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

    elif cmdname == 'login':
        add_container_select_arguments(parser)
        parser.add_argument('--persistent', action='store_true', dest='persistent',
                        help='Make changes done in the session persistent.')

        options = parser.parse_args(cmdargs)
        if not options.suite:
            print('Need at least a suite name!')
            sys.exit(1)
        gconf = init_config(mainfile, options)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = osbase.login(options.persistent)
        if not r:
            sys.exit(2)

    elif cmdname == 'run':
        add_container_select_arguments(parser)
        parser.add_argument('--artifacts-out', action='store', dest='artifacts_dir', default=None,
                        help='Directory on the host where artifacts can be stored. Mounted to /srv/artifacts in the guest.')
        parser.add_argument('--build-dir', action='store', dest='build_dir', default=None,
                        help='Select a host directory that gets bind mounted to /srv/build.')
        parser.add_argument('--external-command', action='store_true', dest='external_commad',
                        help='If set, the command script will be copied from the host to the container and then executed.')
        parser.add_argument('--header', action='store', dest='header', default=None,
                        help='Name of the task that is run, will be printed as header.')
        parser.add_argument('command', action='store', nargs='*', default=None,
                        help='The command to run.')

        custom_command = None
        for i, arg in enumerate(cmdargs):
            if arg == '---':
                if i == len(cmdargs):
                    print('No command was given after "---", can not continue.')
                    sys.exit(1)
                custom_command = cmdargs[i+1:]
                cmdargs = cmdargs[:i]
                break

        options = parser.parse_args(cmdargs)
        if not custom_command:
            custom_command = options.command
        if not options.suite:
            print('Need at least a suite name!')
            sys.exit(1)
        gconf = init_config(mainfile, options)
        osbase = OSBase(gconf, options.suite, options.arch, options.variant)
        r = osbase.run(custom_command, options.build_dir, options.artifacts_dir, options.external_commad, options.header)
        if not r:
            sys.exit(2)

    else:
        print('Command "{}" is unknown.'.format(cmdname))
        sys.exit(1)
