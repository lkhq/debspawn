#!/usr/bin/env python3

import os
import sys
import platform
import shutil

from debspawn import __appname__, __version__
from setuptools import setup
from setuptools.command.install_scripts import install_scripts as install_scripts_orig
from subprocess import check_call


class install_scripts(install_scripts_orig):
    def run(self):
        if platform.system() == 'Windows':
            super().run()
            return

        if not self.skip_build:
            self.run_command('build_scripts')
        self.outfiles = []
        if not self.dry_run:
            self.mkpath(self.install_dir)

        # We want the files to be installed without a suffix on Unix
        for infile in self.get_inputs():
            infile = os.path.basename(infile)
            in_built = os.path.join(self.build_dir, infile)
            in_stripped = infile[:-3] if infile.endswith('.py') else infile
            outfile = os.path.join(self.install_dir, in_stripped)
            # NOTE: Mode is preserved by default
            self.copy_file(in_built, outfile)
            self.outfiles.append(outfile)

        # handle generation of manual pages
        if not shutil.which('xsltproc'):
            print('The "xsltproc" binary was not found. Please install it to continue!')
            sys.exit(1)

        man_dir = os.path.normpath(os.path.join(self.install_dir, '..', 'share', 'man', 'man1'))
        if not self.dry_run:
            self.mkpath(man_dir)

            check_call(['xsltproc',
                        '--nonet',
                        '--stringparam', 'man.output.quietly', '1',
                        '--stringparam', 'funcsynopsis.style', 'ansi',
                        '--stringparam', 'man.th.extra1.suppress', '1',
                        '-o', os.path.join(man_dir, 'debspawn.1'),
                        'http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl',
                        'docs/debspawn.1.xml'])


cmdclass = {
    'install_scripts': install_scripts,
}

packages = [
    'debspawn',
    'debspawn.utils',
]

scripts = ['debspawn.py']

data_files = [('lib/debspawn', ['dsrun/dsrun.py'])]

setup(
    name=__appname__,
    version=__version__,
    author="Matthias Klumpp",
    author_email="matthias@tenstral.net",
    description='Debian package builder and build helper using systemd-nspawn',
    license="LGPL-3.0+",
    url="https://lkorigin.github.io/",

    python_requires='>=3.5',
    platforms=['any'],

    packages=packages,
    data_files=data_files,
    cmdclass=cmdclass,
    scripts=scripts,
)
