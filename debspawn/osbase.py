# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2020 Matthias Klumpp <matthias@tenstral.net>
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
import json
import subprocess
import shutil
from pathlib import Path
from contextlib import contextmanager
from .utils import temp_dir, print_header, print_section, format_filesize, \
    print_info, print_error, print_warn
from .utils.env import ensure_root
from .utils.command import safe_run
from .utils.zstd_tar import compress_directory, decompress_tarball, ensure_tar_zstd
from .nspawn import nspawn_run_helper_persist, nspawn_run_persist
from .aptcache import APTCache


class OSBase:
    '''
    Describes an OS base registered with debspawn
    '''

    def __init__(self, gconf, suite, arch, variant=None, base_suite=None):
        self._gconf = gconf
        self._suite = suite
        self._base_suite = base_suite
        self._arch = arch
        self._variant = variant
        self._name = self._make_name()
        self._results_dir = self._gconf.results_dir

        self._aptcache = APTCache(self)

        # ensure we can (de)compress zstd tarballs
        ensure_tar_zstd()

    def _make_name(self):
        if not self._arch:
            out, _, ret = safe_run(['dpkg-architecture', '-qDEB_HOST_ARCH'])
            if ret != 0:
                raise Exception('Running dpkg-architecture failed: {}'.format(out))

            self._arch = out.strip()
        if self._variant:
            return '{}-{}-{}'.format(self._suite, self._arch, self._variant)
        else:
            return '{}-{}'.format(self._suite, self._arch)

    @property
    def name(self) -> str:
        return self._name

    @property
    def suite(self) -> str:
        return self._suite

    @property
    def base_suite(self) -> str:
        return self._base_suite

    @property
    def arch(self) -> str:
        return self._arch

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def global_config(self):
        return self._gconf

    @property
    def aptcache(self):
        return self._aptcache

    @property
    def has_base_suite(self) -> bool:
        return True if self.base_suite and self.base_suite != self.suite else False

    @property
    def results_dir(self):
        Path(self._results_dir).mkdir(parents=True, exist_ok=True)
        return self._results_dir

    @results_dir.setter
    def results_dir(self, path):
        self._results_dir = path
        Path(self._results_dir).mkdir(exist_ok=True)

    def _copy_helper_script(self, osroot_path):
        script_location = os.path.join(osroot_path, 'usr', 'lib', 'debspawn')
        Path(script_location).mkdir(parents=True, exist_ok=True)
        script_fname = os.path.join(script_location, 'dsrun')

        if os.path.isfile(script_fname):
            os.remove(script_fname)
        shutil.copy2(self._gconf.dsrun_path, script_fname)

        os.chmod(script_fname, 0o0755)

    def get_tarball_location(self):
        return os.path.join(self._gconf.osroots_dir, '{}.tar.zst'.format(self.name))

    def get_config_location(self):
        return os.path.join(self._gconf.osroots_dir, '{}.json'.format(self.name))

    def exists(self):
        return os.path.isfile(self.get_tarball_location())

    def ensure_exists(self):
        '''
        Ensure the container image exists, and terminate the
        program with an error code in case it does not.
        '''
        import sys
        if not self.exists():
            print_error('The container image for "{}" does not exist. Please create it first.'.format(self.name))
            sys.exit(3)

    def new_nspawn_machine_name(self):
        import platform
        from random import choice
        from string import ascii_lowercase, digits

        nid = ''.join(choice(ascii_lowercase + digits) for _ in range(4))

        # on Linux, the maximum hostname length is 64, so we simple set this as general default for
        # debspawn here.
        # shorten the hostname part or replace the suffix, depending on what is longer.
        # This should only ever matter if the hostname of the system already is incredibly long
        uniq_suffix = '{}-{}'.format(self.name, nid)
        if len(uniq_suffix) > 48:
            uniq_suffix = ''.join(choice(ascii_lowercase + digits) for _ in range(12))
        node_name_prefix = platform.node()[:63 - len(uniq_suffix)]

        return '{}-{}'.format(node_name_prefix, uniq_suffix)

    def _write_config_json(self, mirror, components, extra_suites, extra_source_lines):
        '''
        Create configuration file for this container base image
        '''

        print_info('Saving configuration settings.')
        data = {'Suite': self.suite,
                'Architecture': self.arch}
        if self.variant:
            data['Variant'] = self.variant
        if mirror:
            data['Mirror'] = mirror
        if components:
            data['Components'] = components
        if extra_suites:
            data['ExtraSuites'] = extra_suites
        if extra_source_lines:
            data['ExtraSourceLines'] = extra_source_lines

        with open(self.get_config_location(), 'wt') as f:
            f.write(json.dumps(data, sort_keys=True, indent=4))

    def _clear_image_tree(self, image_dir):
        ''' Clear files from a directory tree that we don't want in the tarball. '''

        if os.path.ismount(image_dir):
            print_warn('Preparing OS tree for compression, but /dev is still mounted.')
            return

        for sdir, _, files in os.walk(os.path.join(image_dir, 'dev')):
            for f in files:
                fname = os.path.join(sdir, f)
                if os.path.lexists(fname) and not os.path.isdir(fname) and not os.path.ismount(fname):
                    os.remove(fname)

    def create(self, mirror=None, components=None, extra_suites=[], extra_source_lines=None):
        ''' Create new container base image '''
        ensure_root()

        if self.exists():
            print_error('This configuration has already been created. You can only delete or update it.')
            return False

        # ensure image location exists
        Path(self._gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

        print_header('Creating new base: {} [{}]'.format(self.suite, self.arch))
        print('Using mirror: {}'.format(mirror if mirror else 'default'))
        if self.variant:
            print('variant: {}'.format(self.variant))
        cmd = ['debootstrap',
               '--arch={}'.format(self.arch),
               '--include=python3-minimal,eatmydata']
        if components:
            cmd.append('--components={}'.format(','.join(components)))
        if self.variant:
            cmd.append('--variant={}'.format(self.variant))

        with temp_dir() as tdir:
            bootstrap_suite = self.suite
            if self.has_base_suite:
                bootstrap_suite = self.base_suite
            cmd.extend([bootstrap_suite, tdir])
            print('Bootstrap suite: {}'.format(bootstrap_suite))
            if extra_suites:
                print('Additional suites: {}'.format(', '.join(extra_suites)))
            if extra_source_lines:
                print('Custom sources.list lines will be added:')
                for line in extra_source_lines.split('\\n'):
                    print('    {}'.format(line))
            if mirror:
                cmd.append(mirror)

            print_section('Bootstrap')
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                return False

            # create helper script runner
            self._copy_helper_script(tdir)

            # if we bootstrapped the base suite, add the primary suite to
            # sources.list now
            if self.has_base_suite:
                import re

                sourceslist_fname = os.path.join(tdir, 'etc', 'apt', 'sources.list')
                if not mirror:
                    with open(sourceslist_fname, 'r') as f:
                        contents = f.read()
                        matches = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', contents)
                        if not matches:
                            print_error('Unable to detect default APT repository URL (no regex matches).')
                            return False
                        mirror = matches[0]
                    if not mirror:
                        print_error('Unable to detect default APT repository URL.')
                        return False

                if not components:
                    components = ['main']  # FIXME: We should really be more clever here, e.g. depend on python-apt and parse sources.list properly
                with open(sourceslist_fname, 'a') as f:
                    f.write('deb {mirror} {suite} {components}\n'.format(mirror=mirror, suite=self.suite, components=' '.join(components)))

                    if extra_suites:
                        f.write('\n')
                    for esuite in extra_suites:
                        if esuite == self.suite or esuite == bootstrap_suite:
                            # don't add existing suites multiple times
                            continue
                        f.write('deb {mirror} {esuite} {components}\n'.format(mirror=mirror, esuite=esuite, components=' '.join(components)))

                    if extra_source_lines:
                        f.write('\n')
                        for line in extra_source_lines.split('\\n'):
                            f.write('{}\n'.format(line.strip()))

            print_section('Configure')
            if nspawn_run_helper_persist(self, tdir, self.new_nspawn_machine_name(), '--update') != 0:
                return False

            print_section('Creating Tarball')
            self._clear_image_tree(tdir)
            compress_directory(tdir, self.get_tarball_location())

        # store configuration settings, so we can later recreate this tarball
        # or just display information about it
        self._write_config_json(mirror, components, extra_suites, extra_source_lines)

        print_info('Done.')
        return True

    def delete(self):
        ''' Remove container base image '''
        ensure_root()

        if not self.exists():
            print_error('Can not delete "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Removing base image {}'.format(self.name))

        print_section('Deleting cache')
        cache_size = self._aptcache.clear()
        print_info('Removed {} cached packages.'.format(cache_size))
        self._aptcache.delete()
        print_info('Cache directory removed.')

        print_section('Deleting base tarball')
        os.remove(self.get_tarball_location())

        config_fname = self.get_config_location()
        if os.path.isfile(config_fname):
            print_section('Deleting configuration manifest')
            os.remove(config_fname)

        print_info('Done.')
        return True

    @contextmanager
    def new_instance(self, basename=None):
        with temp_dir() as tdir:
            decompress_tarball(self.get_tarball_location(), tdir)
            yield tdir, self.new_nspawn_machine_name()

    def make_instance_permanent(self, instance_dir):
        ''' Add changes done in the current instance to the main tarball of this OS tree, replacing it. '''

        # remove unwanted files from the tarball
        self._clear_image_tree(instance_dir)

        tarball_name = self.get_tarball_location()
        tarball_name_old = '{}.old'.format(tarball_name)

        os.replace(tarball_name, tarball_name_old)
        compress_directory(instance_dir, tarball_name)
        os.remove(tarball_name_old)

        tar_size = os.path.getsize(self.get_tarball_location())
        print_info('New compressed tarball size is {}'.format(format_filesize(tar_size)))

    def update(self):
        ''' Update container base image '''
        ensure_root()

        if not self.exists():
            print_error('Can not update "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Updating container')

        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            print_section('Update')
            if nspawn_run_helper_persist(self, instance_dir, self.new_nspawn_machine_name(), '--update') != 0:
                return False

            print_section('Recreating tarball')
            self.make_instance_permanent(instance_dir)

        print_section('Cleaning up cache')
        cache_size = self._aptcache.clear()
        print_info('Removed {} cached packages.'.format(cache_size))

        print_info('Done.')
        return True

    def login(self, persistent=False, allowed=[]):
        ''' Interactive shell login into the container '''
        ensure_root()

        if not self.exists():
            print_info('Can not enter "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Login (persistent changes) for {}'.format(self.name) if persistent else 'Login for {}'.format(self.name))
        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            # run an interactive shell in the new container
            nspawn_run_persist(self,
                               instance_dir,
                               self.new_nspawn_machine_name(),
                               '/srv',
                               verbose=True,
                               allowed=allowed)

            if persistent:
                print_section('Recreating tarball')
                self.make_instance_permanent(instance_dir)
            else:
                print_info('Changes discarded.')

        print_info('Done.')
        return True

    def run(self, command, build_dir, artifacts_dir, copy_command=False, header_msg=None, allowed=[]):
        ''' Run an arbitrary command or script in the container '''
        ensure_root()

        if not self.exists():
            print_error('Can not run command in "{}": The base image does not exist.'.format(self.name))
            return False

        if len(command) <= 0:
            print_error('No command was given. Can not continue.')
            return False

        if header_msg:
            print_header(header_msg)

        # ensure we have absolute paths
        if build_dir:
            build_dir = os.path.abspath(build_dir)
        if artifacts_dir:
            artifacts_dir = os.path.abspath(artifacts_dir)

        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            if copy_command:
                # copy the script from the host into our container and execute it there
                host_script = os.path.abspath(command[0])
                if not os.path.isfile(host_script):
                    print_error('Unable to find script "{}", can not copy it to the container. Exiting.'.format(host_script))
                    return False

                script_location = os.path.join(instance_dir, 'srv', 'tmp')
                Path(script_location).mkdir(parents=True, exist_ok=True)
                script_fname = os.path.join(script_location, os.path.basename(host_script))

                if os.path.isfile(script_fname):
                    os.remove(script_fname)
                shutil.copy2(host_script, script_fname)
                os.chmod(script_fname, 0o0755)

                command[0] = os.path.join('/srv', 'tmp', os.path.basename(host_script))

            r = nspawn_run_helper_persist(self,
                                          instance_dir,
                                          machine_name,
                                          '--prepare-run',
                                          '/srv')
            if r != 0:
                print_error('Container setup failed.')
                return False

            print_section('Running Task')

            nspawn_flags = []
            chdir = '/srv'
            if artifacts_dir:
                nspawn_flags.extend(['--bind={}:/srv/artifacts/'.format(os.path.normpath(artifacts_dir))])
            if build_dir:
                nspawn_flags.extend(['--bind={}:/srv/build/'.format(os.path.normpath(build_dir))])
                chdir = '/srv/build'

            r = nspawn_run_persist(self,
                                   instance_dir,
                                   machine_name,
                                   chdir,
                                   command,
                                   nspawn_flags,
                                   allowed=allowed)
            if r != 0:
                return False

        print_info('Done.')
        return True


def print_container_base_image_info(gconf):
    '''
    Search for all available container base images and list information
    about them.
    '''
    from glob import glob

    osroots_dir = gconf.osroots_dir
    tar_files = []
    if os.path.isdir(osroots_dir):
        tar_files = list(glob(os.path.join(osroots_dir, '*.tar.zst')))
    if not tar_files:
        print_info('No container base images have been found!')
        return False
    tar_files_len = len(tar_files)

    for i, tar_fname in enumerate(tar_files):
        img_basepath = os.path.splitext(os.path.splitext(tar_fname)[0])[0]
        config_fname = img_basepath + '.json'
        imgid = os.path.basename(img_basepath)
        print('[{}]'.format(imgid))

        # read configuration data if it exists
        if os.path.isfile(config_fname):
            with open(config_fname, 'rt') as f:
                cdata = json.loads(f.read())
            for key, value in cdata.items():
                if type(value) is list:
                    value = '; '.join(value)
                print('{} = {}'.format(key, value))

        tar_size = os.path.getsize(tar_fname)
        print('Size = {}'.format(format_filesize(tar_size)))
        if i != tar_files_len - 1:
            print()
