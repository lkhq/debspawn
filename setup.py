#!/usr/bin/env python3

import os
import sys
import platform
import shutil

from debspawn import __appname__, __version__
from setuptools import setup
from setuptools.command.install_scripts import install_scripts as install_scripts_orig
from subprocess import check_call
from docs.assemble_man import generate_docbook_pages


class install_scripts(install_scripts_orig):

    def _create_manpage(self, xml_src, out_dir):
        man_name = os.path.splitext(os.path.basename(xml_src))[0]
        out_fname = os.path.join(out_dir, man_name)

        print('Generating manual page {}'.format(man_name))
        check_call(['xsltproc',
                    '--nonet',
                    '--stringparam', 'man.output.quietly', '1',
                    '--stringparam', 'funcsynopsis.style', 'ansi',
                    '--stringparam', 'man.th.extra1.suppress', '1',
                    '-o', out_fname,
                    'http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl',
                    xml_src])
        return out_fname

    def run(self):
        if platform.system() == 'Windows':
            super().run()
            return

        if not self.skip_build:
            self.run_command('build_scripts')
        self.outfiles = []

        # check for xsltproc, we need it to build manual pages
        if not shutil.which('xsltproc'):
            print('The "xsltproc" binary was not found. Please install it to continue!')
            sys.exit(1)

        if self.dry_run:
            return

        if '--single-version-externally-managed' not in sys.argv:
            print()
            print('Attempting to install Debspawn as binary distribution may not yield a working installation.', file=sys.stderr)
            print('We require a file to be installed in a system location, and manual pages are in an external location as well.', file=sys.stderr)
            print(('Currently, no workarounds for this issue have been implemented in Debspawn itself, so please run setup.py with '
                   '`--single-version-externally-managed`.'), file=sys.stderr)
            print('If you are using pip, try `sudo pip3 install --no-binary debspawn .`', file=sys.stderr)
            sys.exit(1)

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
        man_dir = os.path.normpath(os.path.join(self.install_dir, '..', 'share', 'man', 'man1'))
        self.mkpath(man_dir)
        pages = generate_docbook_pages(self.build_dir)
        for page in pages:
            self.outfiles.append(self._create_manpage(page, man_dir))


cmdclass = {
    'install_scripts': install_scripts,
}

packages = [
    'debspawn',
    'debspawn.utils',
]

package_data = {'': ['debspawn/dsrun']}

scripts = ['debspawn.py']

install_requires = ['toml']

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
    zip_safe=False,
    include_package_data=True,

    packages=packages,
    cmdclass=cmdclass,
    package_data=package_data,
    scripts=scripts,
    install_requires=install_requires
)
