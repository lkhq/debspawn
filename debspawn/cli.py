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

__mainfile = None


def init_config(options):
    global __mainfile

    gconf = GlobalConfig()
    gconf.load(options.config)

    if not __mainfile.startswith('/usr'):
        gconf.dsrun_path = os.path.normpath(os.path.join(__mainfile, '..', 'dsrun', 'dsrun.py'))

    # check if we are forbidden from using unicode - otherwise we build
    # with unicode enabled by default
    if options.no_unicode:
        set_unicode_allowed(False)
    else:
        if not 'utf-8' in os.environ.get('LANG', 'utf-8').lower():
            log.warning('Building with unicode support, but your environment does not seem to support unicode.')
        set_unicode_allowed(True)

    return gconf


def command_create(options):
    ''' Create new container image '''

    if not options.suite:
        print('Need at least a suite name to bootstrap!')
        sys.exit(1)
    gconf = init_config(options)
    osbase = OSBase(gconf, options.suite, options.arch, options.variant)
    r = osbase.create(options.mirror)
    if not r:
        sys.exit(2)


def command_update(options):
    ''' Update container image '''

    if not options.suite:
        print('Need at least a suite name for update!')
        sys.exit(1)
    gconf = init_config(options)
    osbase = OSBase(gconf, options.suite, options.arch, options.variant)
    r = osbase.update()
    if not r:
        sys.exit(2)


def command_build(options):
    ''' Build a package in a new volatile container '''

    from .build import build_from_directory, build_from_dsc

    if not options.suite:
        print('Need at least a suite name for building!')
        sys.exit(1)
    gconf = init_config(options)
    osbase = OSBase(gconf, options.suite, options.arch, options.variant)

    if not options.target or os.path.isdir(options.target):
        r = build_from_directory(osbase, options.target, options.sign)
    else:
        r = build_from_dsc(osbase, options.target, options.sign)
    if not r:
        sys.exit(2)


def command_login(options):
    ''' Open interactive session in a container '''

    if not options.suite:
        print('Need at least a suite name!')
        sys.exit(1)
    gconf = init_config(options)
    osbase = OSBase(gconf, options.suite, options.arch, options.variant)
    r = osbase.login(options.persistent)
    if not r:
        sys.exit(2)


def command_run(options, custom_command):
    ''' Run arbitrary command in container session '''

    if not options.suite:
        print('Need at least a suite name!')
        sys.exit(1)
    gconf = init_config(options)
    osbase = OSBase(gconf, options.suite, options.arch, options.variant)
    r = osbase.run(custom_command, options.build_dir, options.artifacts_dir, options.external_commad, options.header)
    if not r:
        sys.exit(2)


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

    global __mainfile
    __mainfile = mainfile

    parser = ArgumentParser(description='Build in nspawn containers')
    subparsers = parser.add_subparsers(dest='sp_name', title='subcommands')

    # generic arguments
    parser.add_argument('--config', action='store', dest='config', default=None,
                        help='Path to the global config file.')
    parser.add_argument('--verbose', action='store_true', dest='verbose',
                        help='Enable debug messages.')
    parser.add_argument('--no-unicode', action='store_true', dest='no_unicode',
                        help='Disable unicode support.')

    # 'create' command
    sp = subparsers.add_parser('create', help="Create new container image")
    add_container_select_arguments(sp)
    sp.add_argument('--mirror', action='store', dest='mirror', default=None,
                    help='Set a specific mirror to bootstrap from.')
    sp.set_defaults(func=command_create)

    # 'update' command
    sp = subparsers.add_parser('update', help="Update a container image")
    add_container_select_arguments(sp)
    sp.set_defaults(func=command_update)

    # 'build' command
    sp = subparsers.add_parser('build', help="Build a package in an isolated environment")
    add_container_select_arguments(sp)
    sp.add_argument('--sign', action='store_true', dest='sign',
                        help='Sign the resulting package.')
    sp.add_argument('target', action='store', nargs='?', default=None,
                    help='The source package file or source directory to build.')
    sp.set_defaults(func=command_build)

    # 'login' command
    sp = subparsers.add_parser('login', help="Open interactive session in a container")
    add_container_select_arguments(sp)
    sp.add_argument('--persistent', action='store_true', dest='persistent',
                    help='Make changes done in the session persistent.')
    sp.set_defaults(func=command_login)

    # 'run' command
    sp = subparsers.add_parser('run', help="Run arbitrary command in an ephemeral container")
    add_container_select_arguments(sp)
    sp.add_argument('--artifacts-out', action='store', dest='artifacts_dir', default=None,
                    help='Directory on the host where artifacts can be stored. Mounted to /srv/artifacts in the guest.')
    sp.add_argument('--build-dir', action='store', dest='build_dir', default=None,
                    help='Select a host directory that gets bind mounted to /srv/build.')
    sp.add_argument('--external-command', action='store_true', dest='external_commad',
                    help='If set, the command script will be copied from the host to the container and then executed.')
    sp.add_argument('--header', action='store', dest='header', default=None,
                    help='Name of the task that is run, will be printed as header.')
    sp.add_argument('command', action='store', nargs='*', default=None,
                    help='The command to run.')

    # special case, so 'run' can understand which arguments are for debspawn and which are
    # for the command to be executed
    if args[0] == 'run':
        custom_command = None
        for i, arg in enumerate(args):
            if arg == '---':
                if i+1 == len(args):
                    print('No command was given after "---", can not continue.')
                    sys.exit(1)
                custom_command = args[i+1:]
                args = args[:i]
                break

    args = parser.parse_args(args)
    if args.sp_name == 'run':
        if not custom_command:
            custom_command = args.command
        command_run(args, custom_command)
    else:
        args.func(args)
