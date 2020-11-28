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
    print_info, print_error, print_warn, listify
from .utils.env import ensure_root
from .utils.command import safe_run
from .utils.zstd_tar import compress_directory, decompress_tarball, ensure_tar_zstd
from .nspawn import nspawn_run_helper_persist, nspawn_run_persist
from .aptcache import APTCache


class OSBase:
    '''
    Describes an OS base registered with debspawn
    '''

    def __init__(self, gconf, suite, arch, variant=None, base_suite=None, cachekey=None):
        self._gconf = gconf
        self._suite = suite
        self._base_suite = base_suite
        self._arch = arch
        self._variant = variant
        self._name = self._make_name()
        self._results_dir = self._gconf.results_dir
        self._cachekey = cachekey
        if self._cachekey:
            self._cachekey = self._cachekey.replace(' ', '')

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

    def get_image_location(self):
        return os.path.join(self._gconf.osroots_dir, '{}.tar.zst'.format(self.name))

    def get_image_cache_dir(self):
        cache_img_dir = os.path.join(self._gconf.osroots_dir, 'dcache', self.name)
        Path(cache_img_dir).mkdir(parents=True, exist_ok=True)
        return cache_img_dir

    def get_cache_image_location(self):
        if not self._cachekey:
            return None
        return os.path.join(self.get_image_cache_dir(), '{}.tar.zst'.format(self._cachekey))

    def get_config_location(self):
        return os.path.join(self._gconf.osroots_dir, '{}.json'.format(self.name))

    def exists(self):
        return os.path.isfile(self.get_image_location())

    def cacheimg_exists(self):
        location = self.get_cache_image_location()
        if not location:
            return False
        return os.path.isfile(location)

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
            f.write('\n')

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

    def _create_internal(self, mirror=None, components=None, extra_suites=[], extra_source_lines=None, show_header=True):
        ''' Create new container base image (internal method) '''

        if self.exists():
            print_error('An image already exists for this configuration. Can not create a new one.')
            return False

        # ensure image location exists
        Path(self._gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

        if show_header:
            print_header('Creating new base: {} [{}]'.format(self.suite, self.arch))
        else:
            print_section('Creating new base: {} [{}]'.format(self.suite, self.arch))

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
            # sources.list. We also add any explicit extra suites and source lines
            if self.has_base_suite or extra_suites or extra_source_lines:
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
                    if self.has_base_suite:
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

            # drop machine-id file, if one exists
            try:
                os.remove(os.path.join(tdir, 'etc', 'machine-id'))
            except OSError:
                pass

            print_section('Creating Tarball')
            self._clear_image_tree(tdir)
            compress_directory(tdir, self.get_image_location())

        # store configuration settings, so we can later recreate this tarball
        # or just display information about it
        self._write_config_json(mirror, components, extra_suites, extra_source_lines)

        return True

    def create(self, mirror=None, components=None, extra_suites=[], extra_source_lines=None):
        ''' Create new container base image (internal method) '''
        ensure_root()

        if self.exists():
            print_error('This configuration has already been created. You can only delete or update it.')
            return False

        ret = self._create_internal(mirror=mirror,
                                    components=components,
                                    extra_suites=extra_suites,
                                    extra_source_lines=extra_source_lines,
                                    show_header=True)
        if ret:
            print_info('Done.')

        return ret

    def delete(self):
        ''' Remove container base image '''
        ensure_root()

        if not self.exists():
            print_error('Can not delete "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Removing base image {}'.format(self.name))

        print_section('Deleting cache')
        # remove packages cache
        cache_size = self._aptcache.clear()
        print_info('Removed {} cached packages.'.format(cache_size))
        self._aptcache.delete()
        # remove cached images
        shutil.rmtree(self.get_image_cache_dir())
        print_info('Cache directory removed.')

        print_section('Deleting base tarball')
        os.remove(self.get_image_location())

        config_fname = self.get_config_location()
        if os.path.isfile(config_fname):
            print_section('Deleting configuration manifest')
            os.remove(config_fname)

        print_info('Done.')
        return True

    @contextmanager
    def new_instance(self, basename=None):
        with temp_dir() as tdir:
            if self.cacheimg_exists():
                image_fname = self.get_cache_image_location()
            else:
                image_fname = self.get_image_location()
            decompress_tarball(image_fname, tdir)
            yield tdir, self.new_nspawn_machine_name()

    def make_instance_permanent(self, instance_dir):
        ''' Add changes done in the current instance to the main tarball of this OS tree, replacing it. '''

        # remove unwanted files from the tarball
        self._clear_image_tree(instance_dir)

        if self._cachekey:
            tarball_name = self.get_cache_image_location()
        else:
            tarball_name = self.get_image_location()
        tarball_name_old = '{}.old'.format(tarball_name)

        if os.path.isfile(tarball_name):
            os.replace(tarball_name, tarball_name_old)
        compress_directory(instance_dir, tarball_name)
        if os.path.isfile(tarball_name_old):
            os.remove(tarball_name_old)

        tar_size = os.path.getsize(tarball_name)
        if self._cachekey:
            print_info('New compressed tarball size (for {}) is {}'.format(self._cachekey, format_filesize(tar_size)))
        else:
            print_info('New compressed tarball size is {}'.format(format_filesize(tar_size)))

    def update(self):
        ''' Update container base image '''
        ensure_root()

        if not self.exists():
            print_error('Can not update "{}": The configuration does not exist.'.format(self.name))
            return False

        print_header('Updating container image')

        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            print_section('Update')
            if nspawn_run_helper_persist(self, instance_dir, self.new_nspawn_machine_name(), '--update') != 0:
                return False

            # drop machine-id file, if one exists
            try:
                os.remove(os.path.join(instance_dir, 'etc', 'machine-id'))
            except OSError:
                pass

            print_section('Recreating tarball')
            self.make_instance_permanent(instance_dir)

        print_section('Cleaning up cache')
        cache_size = self._aptcache.clear()
        print_info('Removed {} cached packages.'.format(cache_size))
        # remove now-outdated cached images
        shutil.rmtree(self.get_image_cache_dir())

        print_info('Done.')
        return True

    def recreate(self):
        ''' Recreate a container base image '''
        ensure_root()

        if not self.exists():
            print_error('Can not recreate "{}": The image does not exist.'.format(self.name))
            return False

        config_fname = self.get_config_location()
        if not os.path.isfile(config_fname):
            print_error('Can not recreate "{}": Unable to find configuration data for this image.'.format(self.name))
            return False

        print_header('Recreating container image')

        # read configuration data
        with open(config_fname, 'rt') as f:
            cdata = json.loads(f.read())
            self._suite = cdata.get('Suite', self.suite)
            self._arch = cdata.get('Architecture', self.arch)
            self._variant = cdata.get('Variant', self.variant)
            mirror = cdata.get('Mirror')
            components = cdata.get('Components')
            extra_suites = cdata.get('ExtraSuites', [])
            extra_source_lines = cdata.get('ExtraSourceLines')

        print_section('Deleting cache')
        cache_size = self._aptcache.clear()
        print_info('Removed {} cached packages.'.format(cache_size))
        self._aptcache.delete()
        print_info('Cache directory removed.')

        # move old image tarball out of the way
        image_name = self.get_image_location()
        image_name_old = self.get_image_location() + '.old'
        if os.path.isfile(image_name_old):
            print_info('Removing cruft image')
            os.remove(image_name_old)
        os.rename(image_name, image_name_old)
        print_info('Old tarball moved.')

        # ty to create the tarball again
        try:
            ret = self._create_internal(mirror=mirror,
                                        components=components,
                                        extra_suites=extra_suites,
                                        extra_source_lines=extra_source_lines,
                                        show_header=False)
        except Exception as e:
            print_error('Error while trying to create image: {}'.format(str(e)))
            ret = False

        if ret:
            if os.path.isfile(image_name_old):
                print_info('Removing old image')
                os.remove(image_name_old)

            print_info('Removing outdated cached images')
            shutil.rmtree(self.get_image_cache_dir())

            print_info('Done.')
            return True
        else:
            print_info('Restoring old tarball')
            if os.path.isfile(image_name):
                print_info('Removing failed new image')
                os.remove(image_name)
            os.rename(image_name_old, image_name)
            print_info('Recreation failed.')
            return False

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

    def _copy_command_script_to_instance_dir(self, instance_dir: str, command_script: str) -> str:
        '''
        Copy a script from the host to the current instance directory and make it
        executable.
        Contains the path to the executable script as seen from inside the container.
        '''
        host_script = os.path.abspath(command_script)
        if not os.path.isfile(host_script):
            return None

        script_location = os.path.join(instance_dir, 'srv', 'tmp')
        Path(script_location).mkdir(parents=True, exist_ok=True)
        script_fname = os.path.join(script_location, os.path.basename(host_script))

        if os.path.isfile(script_fname):
            os.remove(script_fname)
        shutil.copy2(host_script, script_fname)
        os.chmod(script_fname, 0o0755)

        return os.path.join('/srv', 'tmp', os.path.basename(host_script))

    def run(self, command, build_dir, artifacts_dir, init_command=None, copy_command=False, header_msg=None, allowed=[]):
        ''' Run an arbitrary command or script in the container '''
        ensure_root()

        if not self.exists():
            print_error('Can not run command in "{}": The base image does not exist.'.format(self.name))
            return False

        if len(command) <= 0:
            print_error('No command was given. Can not continue.')
            return False

        if isinstance(init_command, str):
            if init_command:
                import shlex
                init_command = shlex.split(init_command)
        init_command = listify(init_command)

        # ensure we have absolute paths
        if build_dir:
            build_dir = os.path.abspath(build_dir)
        if artifacts_dir:
            artifacts_dir = os.path.abspath(artifacts_dir)

        if self._cachekey and init_command and not self.cacheimg_exists():
            print_header('Preparing template for `{}`'.format(self._cachekey))

            # we do not have a cached image prepared, let's do that now!
            with self.new_instance() as (instance_dir, machine_name):
                # ensure helper script runner exists and is up to date
                self._copy_helper_script(instance_dir)

                if copy_command:
                    # copy initialization script from host to container
                    host_script = init_command[0]
                    init_command[0] = self._copy_command_script_to_instance_dir(instance_dir, host_script)
                    if not init_command[0]:
                        print_error('Unable to find initialization script "{}", can not copy it to the container. Exiting.'.format(host_script))
                        return False

                r = nspawn_run_helper_persist(self,
                                              instance_dir,
                                              machine_name,
                                              '--prepare-run',
                                              '/srv')
                if r != 0:
                    print_error('Container setup failed.')
                    return False
                # we do not want some permissions to be in effect here,
                # as they may have unwanted effects on the final cached image
                banned_permissions = ['full-dev', 'full-proc', 'read-kmods']
                filtered_allowed = []
                for perm in allowed:
                    if perm not in banned_permissions:
                        filtered_allowed.append(perm)
                r = nspawn_run_persist(self,
                                       instance_dir,
                                       machine_name,
                                       '/srv',
                                       init_command,
                                       allowed=filtered_allowed)
                if r != 0:
                    return False

                print_info('Storing prepared image in cache')
                self.make_instance_permanent(instance_dir)

        if header_msg:
            print_header(header_msg)
        if self._cachekey and init_command and self.cacheimg_exists():
            print_info('Using cached container image `{}`'.format(self._cachekey))

        with self.new_instance() as (instance_dir, machine_name):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            if copy_command:
                # copy the script from the host into our container and execute it there
                host_script = command[0]
                command[0] = self._copy_command_script_to_instance_dir(instance_dir, host_script)
                if not command[0]:
                    print_error('Unable to find script "{}", can not copy it to the container. Exiting.'.format(host_script))
                    return False

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

        cache_files = list(glob(os.path.join(osroots_dir, 'dcache', imgid, '*.tar.zst')))
        cached_names = []
        for cfile in cache_files:
            cname = os.path.basename(os.path.splitext(os.path.splitext(cfile)[0])[0])
            cached_names.append(cname)

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

        if cached_names:
            print('CachedImages = {}'.format('; '.join(cached_names)))
        if i != tar_files_len - 1:
            print()
