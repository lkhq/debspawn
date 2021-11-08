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
import sys
import shutil
import json
from glob import glob
from .config import GlobalConfig
from .utils.env import ensure_root
from .utils.log import print_info, print_warn, print_error, print_bullet, print_section, \
    print_bool_item
from .osbase import OSBase


def ensure_rmtree_symattack_protection():
    ''' Exit the program with an error if rmtree does not protect against symlink attacks '''
    if not shutil.rmtree.avoids_symlink_attacks:
        print_error('Will not continue: rmtree does not run in symlink-attack protected mode.')
        sys.exit(1)


def maintain_migrate(gconf: GlobalConfig):
    ''' Migrate configuration from older versions of debspawn to the latest version '''

    ensure_root()

    # migrate old container images directory, if needed
    images_dir = gconf.osroots_dir
    if not os.path.isdir(images_dir):
        old_images_dir = '/var/lib/debspawn/containers'
        if os.path.isdir(old_images_dir):
            print_info('Migrating images directory...')
            shutil.move(old_images_dir, images_dir)


def maintain_clear_caches(gconf: GlobalConfig):
    ''' Delete all cache data for all images '''

    ensure_root()
    ensure_rmtree_symattack_protection()

    aptcache_dir = gconf.aptcache_dir
    if os.path.isdir(aptcache_dir):
        for cdir in glob(os.path.join(aptcache_dir, '*')):
            print_info('Removing APT cache for: {}'.format(os.path.basename(cdir)))
            if os.path.isdir(cdir):
                shutil.rmtree(cdir)
            else:
                os.remove(cdir)

    dcache_dir = os.path.join(gconf.osroots_dir, 'dcache')
    if os.path.isdir(dcache_dir):
        print_info('Removing image derivatives cache.')
        shutil.rmtree(dcache_dir)


def maintain_purge(gconf: GlobalConfig, force: bool = False):
    ''' Remove all images as well as any data associated with them '''

    ensure_root()
    ensure_rmtree_symattack_protection()

    if not force:
        print_warn(('This action will delete ALL your images as well as their configuration, build results and other '
                    'associated data and will clear all data from the directories you may have configured as default.'))
        delete_all = False
        while True:
            try:
                in_res = input('Do you really want to continue? [y/N]: ')
            except EOFError:
                in_res = 'n'
                print()
            if not in_res:
                delete_all = False
                break
            elif in_res.lower() == 'y':
                delete_all = True
                break
            elif in_res.lower() == 'n':
                delete_all = False
                break

        if not delete_all:
            print_info('Purge action aborted.')
            return

    print_warn('Deleting all images, image configuration, build results and state data.')
    for sdir in [gconf.osroots_dir, gconf.results_dir, gconf.aptcache_dir, gconf.injected_pkgs_dir]:
        if not os.path.isdir(sdir):
            continue
        if sdir.startswith('/home/') or sdir.startswith('/usr/'):
            continue
        print_info('Purging: {}'.format(sdir))
        for d in glob(os.path.join(sdir, '*')):
            if os.path.isdir(d):
                shutil.rmtree(d)
            else:
                os.remove(d)

    default_state_dir = '/var/lib/debspawn/'
    if os.path.isdir(default_state_dir):
        print_info('Removing: {}'.format(default_state_dir))
        shutil.rmtree(default_state_dir)


def maintain_update_all(gconf: GlobalConfig):
    ''' Update all container images that we know. '''

    ensure_root()

    osroots_dir = gconf.osroots_dir
    tar_files = []
    if os.path.isdir(osroots_dir):
        tar_files = list(glob(os.path.join(osroots_dir, '*.tar.zst')))
    if not tar_files:
        print_info('No container base images have been found!')
        return

    failed_images = []
    nodata_images = []
    first_entry = True
    for tar_fname in tar_files:
        img_basepath = os.path.splitext(os.path.splitext(tar_fname)[0])[0]
        config_fname = img_basepath + '.json'
        imgid = os.path.basename(img_basepath)

        # read configuration data
        if not os.path.isfile(config_fname):
            nodata_images.append(imgid)
            continue

        with open(config_fname, 'rt') as f:
            cdata = json.loads(f.read())

        if not first_entry:
            print()
        first_entry = False
        print_bullet('Update: {}'.format(imgid), indent=1, large=True)

        osbase = OSBase(gconf,
                        cdata['Suite'],
                        cdata['Architecture'],
                        cdata.get('Variant'),
                        custom_name=os.path.basename(img_basepath))
        r = osbase.update()
        if not r:
            print_error('Failed to update {}'.format(imgid))
            failed_images.append(imgid)

    if nodata_images or failed_images:
        print()
    for imgid in nodata_images:
        print_warn('Could not auto-update image {}: Configuration data is missing.'.format(imgid))
    if failed_images:
        print_error('Failed to update image(s): {}'.format(', '.join(failed_images)))
        sys.exit(1)


def maintain_print_status(gconf: GlobalConfig):
    '''
    Print status information about this Debspawn installation
    that may be useful for debugging issues.
    '''
    import platform
    from . import __version__
    from .osbase import print_container_base_image_info, debootstrap_version
    from .nspawn import systemd_version, systemd_detect_virt

    print('Debspawn Status Report', end='')
    sys.stdout.flush()

    # read distribution information
    os_release = {}
    if os.path.exists('/etc/os-release'):
        with open('/etc/os-release') as f:
            for line in f:
                k, v = line.rstrip().split("=")
                os_release[k] = v.strip('"')

    print_section('Host System')
    print('OS:', os_release.get('NAME', 'Unknown'), os_release.get('VERSION', '<?>'))
    print('Platform:', platform.platform(aliased=True))
    print('Virtualization:', systemd_detect_virt())
    print('Systemd-nspawn version:', systemd_version())
    print('Debootstrap version:', debootstrap_version())

    print_section('Container image list')
    print_container_base_image_info(gconf)

    print_section('Debspawn')
    print('Version:', __version__)
    print_bool_item('Tmpfiles.d configuration:', os.path.isfile('/usr/lib/tmpfiles.d/debspawn.conf'),
                    text_true='installed', text_false='missing')
    print_bool_item('Monthly cache cleanup timer:', os.path.isfile('/lib/systemd/system/debspawn-clear-caches.timer'),
                    text_true='available', text_false='missing')
    print_bool_item('Manual pages:', len(glob('/usr/share/man/man1/debspawn*.1.*')) >= 8,
                    text_true='installed', text_false='missing')
    if not os.path.isfile('/etc/debspawn/global.toml'):
        print('Global configuration: default')
    else:
        print('Global configuration:')
        with open('/etc/debspawn/global.toml', 'r') as f:
            for line in f:
                print('    ', line)
