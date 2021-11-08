#!/usr/bin/env python3

import os
import sys
import platform
import shutil
from setuptools import setup
from setuptools.command.install_scripts import install_scripts as install_scripts_orig
from subprocess import check_call

sys.path.append(os.getcwd())
from debspawn import __appname__, __version__  # noqa: E402


thisfile = __file__
if not os.path.isabs(thisfile):
    thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))
source_root = os.path.dirname(thisfile)


class install_scripts(install_scripts_orig):

    def _check_command(self, command):
        if not shutil.which(command):
            print('The "{}" binary was not found. Please install it to continue!'.format(command),
                  file=sys.stderr)
            sys.exit(1)

    def _check_commands_available(self):
        ''' Check if certain commands are available that debspawn needs to work. '''
        self._check_command('systemd-nspawn')
        self._check_command('findmnt')
        self._check_command('zstd')
        self._check_command('debootstrap')
        self._check_command('dpkg')

    def run(self):
        if platform.system() == 'Windows':
            super().run()
            return

        if not self.skip_build:
            self.run_command('build_scripts')
        self.outfiles = []

        if self.dry_run:
            return

        # We want the files to be installed without a suffix on Unix
        self.mkpath(self.install_dir)
        for infile in self.get_inputs():
            infile = os.path.basename(infile)
            in_built = os.path.join(self.build_dir, infile)
            in_stripped = infile[:-3] if infile.endswith('.py') else infile
            outfile = os.path.join(self.install_dir, in_stripped)
            # NOTE: Mode is preserved by default
            self.copy_file(in_built, outfile)
            self.outfiles.append(outfile)

        # try to install configuration snippets, manual pages and other external data
        bin_install_dir = str(self.install_dir)
        if '/usr/' in bin_install_dir:
            install_root = bin_install_dir.split('/usr/', 1)[0]
            prefix = '/usr/local' if '/usr/local/' in bin_install_dir else '/usr'
            sysdata_install_script = os.path.join(source_root, 'install-sysdata.py')
            if os.path.isfile(sysdata_install_script) and os.path.isdir(install_root):
                check_call([sys.executable,
                            sysdata_install_script,
                            '--root', install_root,
                            '--prefix', prefix])
            else:
                print('Unable to install externally managed data!', file=sys.stderr)
        else:
            print(('\n\n ------------------------\n'
                   'Unable to install external configuration and manual pages!\n'
                   'While these files are not essential to work with debspawn, they will improve how it runs '
                   'or are useful as documentation. Please install these files manually by running the '
                   '`install-sysdata.py` script from debspawn\'s source directory manually as root.\n'
                   'Installing these external files is not possible when installing e.g. with pip. If `setup.py` is '
                   'used directly we make an attempt to install the files, but this attempt has failed.'
                   '\n ------------------------\n\n'),
                  file=sys.stderr)


cmdclass = {
    'install_scripts': install_scripts,
}

packages = [
    'debspawn',
    'debspawn.utils',
]

package_data = {'': ['debspawn/dsrun']}

scripts = ['debspawn.py']

install_requires = ['toml>=0.10']

setup(
    name=__appname__,
    version=__version__,
    author="Matthias Klumpp",
    author_email="matthias@tenstral.net",
    description='Easily build Debian packages in systemd-nspawn containers',
    license="LGPL-3.0+",
    url="https://github.com/lkhq/debspawn",
    long_description=open(os.path.join(source_root, 'README.md')).read(),
    long_description_content_type='text/markdown',

    python_requires='>=3.9',
    platforms=['any'],
    zip_safe=False,
    include_package_data=True,

    packages=packages,
    cmdclass=cmdclass,
    package_data=package_data,
    scripts=scripts,
    install_requires=install_requires
)
