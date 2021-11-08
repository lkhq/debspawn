# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2021 Matthias Klumpp <matthias@tenstral.net>
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
from typing import Optional
from .utils import temp_dir, print_header, print_section, format_filesize, \
    print_info, print_error, print_warn, listify
from .utils.misc import maybe_remove, safe_copy
from .utils.env import ensure_root, get_random_free_uid_gid, get_owner_uid_gid
from .utils.command import safe_run
from .utils.zstd_tar import compress_directory, decompress_tarball, ensure_tar_zstd
from .nspawn import nspawn_run_helper_persist, nspawn_run_persist
from .aptcache import APTCache


def debootstrap_version():
    ds_version = 'unknown'
    try:
        out, _, _ = safe_run(['debootstrap', '--version'])
        parts = out.strip().split(' ', 2)
        ds_version = parts[0 if len(parts) < 2 else 1]
    except Exception as e:
        print_warn('Unable to determine debootstrap version: {}'.format(e))

    return ds_version


class OSBase:
    '''
    Describes an OS base registered with debspawn
    '''

    def __init__(self, gconf, suite, arch, variant=None, *,
                 base_suite=None, custom_name=None, cachekey=None):
        self._gconf = gconf
        self._suite = suite
        self._base_suite = base_suite
        self._arch = arch

        # if variant is not passed, we use the configured default
        self._variant = variant if variant else gconf.default_bootstrap_variant
        if self._variant == 'none':
            # "none" is an alias to "don't set a variant when invoking debootstrap"
            self._variant = None

        self._custom_name = custom_name
        self._name = self._make_name()
        self._results_dir = self._gconf.results_dir
        self._cachekey = cachekey
        if self._cachekey:
            self._cachekey = self._cachekey.replace(' ', '')

        self._parameters_checked = False
        self._aptcache = APTCache(self)

        # get a fresh UID to give to our build user within the container
        self._builder_uid = get_random_free_uid_gid()[0]

        # ensure we can (de)compress zstd tarballs
        ensure_tar_zstd()

    def _make_name(self):
        ''' Configure a unique-ish name based on user defined data,
        and tweak the custom name and suite values to match. '''

        if self._custom_name and not self._suite:
            # if we have a custom name but no suite name, the custom name is treated
            # as our suite name *if* no image exists with the custom name
            # (this is for backwards compatibility)
            self._name = self._custom_name
            if not self.exists():
                self._suite = self._custom_name
                self._custom_name = None
        if self._custom_name == self._suite:
            self._custom_name = None

        if not self._arch:
            out, _, ret = safe_run(['dpkg', '--print-architecture'])
            if ret != 0:
                raise Exception('Running dpkg --print-architecture failed: {}'.format(out))

            self._arch = out.strip()
        if self._custom_name:
            return self._custom_name
        elif self._variant:
            return '{}-{}-{}'.format(self._suite, self._variant, self._arch)
        else:
            return '{}-{}'.format(self._suite, self._arch)

    def _custom_name_parameter_check(self):
        ''' Read parameters in case a custom name was passed, and perform basic sanity checks. '''
        import sys

        if self._parameters_checked:
            return
        if not self._custom_name:
            return

        config_fname = self.get_config_location()
        if not os.path.isfile(config_fname):
            print_error('No configuration data found for image "{}"!'.format(self.name))
            sys.exit(3)

        with open(config_fname, 'rt') as f:
            cdata = json.loads(f.read())

            c_suite = cdata.get('Suite', self.suite)
            if not self._suite:
                # if no suite was set, but we have one in the manifest file,
                # we will always use it to fill in the gap
                self._suite = c_suite

            if self.suite != c_suite:
                print_error('Expected suite name "{}" for image "{}", but got "{}" instead.'.format(
                    cdata.get('Suite'), self.name, self.suite))
                sys.exit(1)
            c_arch = cdata.get('Architecture', self.arch)
            c_variant = cdata.get('Variant', self.variant)

            if self.arch and self.arch != c_arch:
                print_warn(('Expected architecture "{}" for image "{}", but got "{}" instead. '
                            'Using expected value.').format(
                                c_arch, self.name, self.arch))
            if self.variant and self.variant != c_variant:
                print_warn(('Expected variant "{}" for image "{}", but got "{}" instead. '
                            'Using expected value.').format(
                                c_variant, self.name, self.variant))
            self._arch = c_arch
            self._variant = c_variant
        self._parameters_checked = True

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
        if not self._load_existent():
            print_error('The container image for "{}" does not exist. Please create it first.'.format(self.name))
            sys.exit(3)

    def _load_existent(self) -> bool:
        ''' Check if image exists, and if so load some essential data and return True. '''
        # ensure the set config values are sane if the user is using a custom container name
        if self._custom_name:
            self._custom_name_parameter_check()
        return self.exists()

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

    def _remove_unwanted_files(self, instance_dir):
        ''' Delete unwanted files from a base image '''

        # drop resolv.conf: Some OSes set this to a symlink, which will lead to nowhere
        # in the container and may cause issues when bindmounting over it
        maybe_remove(os.path.join(instance_dir, 'etc', 'resolv.conf'))

        # our APT proxy connfiguration should also not be stored, we will reset it every time
        maybe_remove(os.path.join(instance_dir, 'etc', 'apt', 'apt.conf.d', '98debspawn_proxy'))

        # drop machine-id file, if one exists
        maybe_remove(os.path.join(instance_dir, 'etc', 'machine-id'))
        # drop logfiles which we want to reset
        maybe_remove(os.path.join(instance_dir, 'var', 'log', 'lastlog'))
        maybe_remove(os.path.join(instance_dir, 'var', 'log', 'faillog'))

    def _setup_apt_proxy(self, instance_dir):
        ''' Setup APT proxy configuration.
        APT needs special treatment even in the container to work with a company proxy (yuck!),
        so we do this here so the user does not need to care about it.
        '''

        http_proxy = os.getenv('HTTP_PROXY', os.getenv('http_proxy'))
        https_proxy = os.getenv('HTTPS_PROXY', os.getenv('https_proxy'))
        if not http_proxy and not https_proxy:
            return
        if http_proxy:
            http_proxy = http_proxy.replace('"', '')
        if https_proxy:
            https_proxy = https_proxy.replace('"', '')

        proxyconf_fname = os.path.join(instance_dir, 'etc', 'apt', 'apt.conf.d', '98debspawn_proxy')
        with open(proxyconf_fname, 'w') as f:
            if http_proxy:
                f.write('Acquire::http::Proxy "{}";\n'.format(http_proxy))
            if https_proxy:
                f.write('Acquire::https::Proxy "{}";\n'.format(https_proxy))

    def _create_internal(self, mirror=None, components=None,
                         extra_suites: list[str] = None, extra_source_lines: str = None,
                         allow_recommends: bool = False,
                         show_header: bool = True):
        ''' Create new container base image (internal method) '''

        if self.exists():
            print_error('An image already exists for this configuration. Can not create a new one.')
            return False
        if not extra_suites:
            extra_suites = []

        # ensure image location exists
        Path(self._gconf.osroots_dir).mkdir(parents=True, exist_ok=True)

        if show_header:
            print_header('Creating new base: {} [{}]'.format(self.suite, self.arch))
        else:
            print_section('Creating new base: {} [{}]'.format(self.suite, self.arch))

        if self._custom_name:
            print('Custom name: {}'.format(self.name))
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
            proc = subprocess.run(cmd, check=False)
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
                        matches = re.findall(
                            'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                            contents)
                        if not matches:
                            print_error('Unable to detect default APT repository URL (no regex matches).')
                            return False
                        mirror = matches[0]
                    if not mirror:
                        print_error('Unable to detect default APT repository URL.')
                        return False

                if not components:
                    # FIXME: We should really be more clever here, e.g. depend on python-apt
                    # and parse sources.list properly
                    components = ['main']
                with open(sourceslist_fname, 'a') as f:
                    if self.has_base_suite:
                        f.write('deb {mirror} {suite} {components}\n'.format(mirror=mirror,
                                                                             suite=self.suite,
                                                                             components=' '.join(components)))

                    if extra_suites:
                        f.write('\n')
                        for esuite in extra_suites:
                            if esuite == self.suite or esuite == bootstrap_suite:
                                # don't add existing suites multiple times
                                continue
                            f.write('deb {mirror} {esuite} {components}\n'.format(mirror=mirror,
                                                                                  esuite=esuite,
                                                                                  components=' '.join(components)))

                    if extra_source_lines:
                        f.write('\n')
                        for line in extra_source_lines.split('\\n'):
                            f.write('{}\n'.format(line.strip()))

            # write our default APT settings for this container
            aptconf_fname = os.path.join(tdir, 'etc', 'apt', 'apt.conf.d', '99debspawn')
            with open(aptconf_fname, 'w') as f:
                # fail immediately with a proper exit code when e.g. apt update fails,
                # so we can retry and don't silently use old packages
                # (only available with newer APT versions)
                f.write('APT::Update::Error-Mode "any";\n')
                if not allow_recommends:
                    f.write('APT::Install-Recommends "0";\n')
                    f.write('APT::Install-Suggests "0";\n')

            # delete unwanted files, especially resolv.conf as a broken one will
            # mess with the next step
            self._remove_unwanted_files(tdir)

            # configure APT proxy, so the configure operation will work behind proxys
            self._setup_apt_proxy(tdir)

            print_section('Configure')
            if nspawn_run_helper_persist(self, tdir,
                                         self.new_nspawn_machine_name(),
                                         '--update',
                                         build_uid=self._builder_uid) != 0:
                return False

            # drop any unwanted files (again) before building the tarball
            self._remove_unwanted_files(tdir)

            print_section('Creating Tarball')
            self._clear_image_tree(tdir)
            compress_directory(tdir, self.get_image_location())

        # store configuration settings, so we can later recreate this tarball
        # or just display information about it
        self._write_config_json(mirror, components, extra_suites, extra_source_lines)

        return True

    def create(self, mirror: str = None, components: list[str] = None, *,
               extra_suites: list[str] = None, extra_source_lines: str = None,
               allow_recommends: bool = False):
        ''' Create new container base image (internal method) '''
        ensure_root()

        if self.exists():
            print_error('This configuration has already been created. You can only delete or update it.')
            return False

        ret = self._create_internal(mirror=mirror,
                                    components=components,
                                    extra_suites=extra_suites,
                                    extra_source_lines=extra_source_lines,
                                    allow_recommends=allow_recommends,
                                    show_header=True)
        if ret:
            print_info('Done.')

        return ret

    def delete(self):
        ''' Remove container base image '''
        ensure_root()

        if not self._load_existent():
            print_error('Can not delete "{}": This configuration does not exist.'.format(self.name))
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
            self._setup_apt_proxy(tdir)

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

        if not self._load_existent():
            print_error('Can not update "{}": This configuration does not exist.'.format(self.name))
            return False

        print_header('Updating container image')

        with self.new_instance() as (instance_dir, _):
            # ensure helper script runner exists and is up to date
            self._copy_helper_script(instance_dir)

            print_section('Update')
            if nspawn_run_helper_persist(self, instance_dir,
                                         self.new_nspawn_machine_name(),
                                         '--update',
                                         build_uid=self._builder_uid) != 0:
                return False

            # drop unwanted files from the image
            self._remove_unwanted_files(instance_dir)

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

        if not self._load_existent():
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
            allow_recommends = cdata.get('AllowRecommends', False)

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
                                        allow_recommends=allow_recommends,
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

    def login(self, persistent=False, allowed: list[str] = None):
        ''' Interactive shell login into the container '''
        ensure_root()

        if not self._load_existent():
            print_info('Can not enter "{}": This configuration does not exist.'.format(self.name))
            return False

        print_header('Login (persistent changes) for {}'.format(self.name)
                     if persistent else 'Login for {}'.format(self.name))
        with self.new_instance() as (instance_dir, _):
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

    def retrieve_artifacts(self, src_dir: str, dest_dir: Optional[str] = None):
        from glob import glob

        print_section('Retrieving build artifacts')
        if not dest_dir:
            dest_dir = self.results_dir

        o_uid, o_gid = get_owner_uid_gid()
        acount = 0
        for f in glob(os.path.join(src_dir, '*.*')):
            if os.path.isfile(f):
                target_fname = os.path.join(dest_dir, os.path.basename(f))
                safe_copy(f, target_fname)
                os.chown(target_fname, o_uid, o_gid, follow_symlinks=False)
                acount += 1
        print_info('Copied {} files.'.format(acount))

    def _copy_command_script_to_instance_dir(self, instance_dir: str, command_script: str) -> Optional[str]:
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

    def run(self, command, build_dir, artifacts_dir, init_command=None, copy_command=False,
            header_msg=None, bind_build_dir: Optional[str] = None, allowed: list[str] = None):
        ''' Run an arbitrary command or script in the container '''
        ensure_root()

        if not self._load_existent():
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
        allowed = listify(allowed)
        if bind_build_dir == 'n':
            bind_build_dir = None

        # ensure we have absolute paths
        if build_dir:
            build_dir = os.path.normpath(os.path.abspath(build_dir))
        if artifacts_dir:
            artifacts_dir = os.path.normpath(os.path.abspath(artifacts_dir))

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
                        print_error(('Unable to find initialization script "{}", '
                                     'can not copy it to the container. Exiting.').format(host_script))
                        return False

                r = nspawn_run_helper_persist(self,
                                              instance_dir,
                                              machine_name,
                                              '--prepare-run',
                                              '/srv',
                                              build_uid=self._builder_uid)
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

                init_nspawn_flags = []
                if build_dir:
                    if not bind_build_dir:
                        shutil.copytree(build_dir, os.path.join(instance_dir, 'srv', 'build'), dirs_exist_ok=True)
                    else:
                        if bind_build_dir == 'rw':
                            init_nspawn_flags = ['--bind={}:/srv/build/'.format(build_dir)]
                        elif bind_build_dir == 'ro':
                            init_nspawn_flags = ['--bind-ro={}:/srv/build/'.format(build_dir)]
                r = nspawn_run_persist(self,
                                       instance_dir,
                                       machine_name,
                                       '/srv',
                                       init_command,
                                       init_nspawn_flags,
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
                    print_error(('Unable to find script "{}", can not copy it to the container. '
                                 'Exiting.').format(host_script))
                    return False

            r = nspawn_run_helper_persist(self,
                                          instance_dir,
                                          machine_name,
                                          '--prepare-run',
                                          '/srv',
                                          build_uid=self._builder_uid)
            if r != 0:
                print_error('Container setup failed.')
                return False

            # Create a few directories we may use for bindmounting if some allow-flags are set,
            # and which are not commonly present in the base image.
            # This is only needed for `run` actions, and regular package builds should not require
            # bindmounts to these directories.
            os.makedirs(os.path.join(instance_dir, 'lib', 'modules'), exist_ok=True)
            os.makedirs(os.path.join(instance_dir, 'boot'), exist_ok=True)
            os.makedirs(os.path.join(instance_dir, 'srv', 'artifacts'), exist_ok=True)

            print_section('Running Task')
            nspawn_flags = []
            chdir = '/srv'
            if build_dir:
                chdir = '/srv/build'
                if not bind_build_dir:
                    shutil.copytree(build_dir, os.path.join(instance_dir, 'srv', 'build'), dirs_exist_ok=True)
                else:
                    if bind_build_dir == 'rw':
                        nspawn_flags.extend(['--bind={}:/srv/build/'.format(build_dir)])
                    elif bind_build_dir == 'ro':
                        nspawn_flags.extend(['--bind-ro={}:/srv/build/'.format(build_dir)])

            r = nspawn_run_persist(self,
                                   instance_dir,
                                   machine_name,
                                   chdir,
                                   command,
                                   nspawn_flags,
                                   allowed=allowed)
            if r != 0:
                return False

            # copy results to target directory
            self.retrieve_artifacts(os.path.join(instance_dir, 'srv', 'artifacts'), artifacts_dir)

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
