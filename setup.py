#!/usr/bin/env python3

from spark import __appname__, __version__
from setuptools import setup

packages = [
    'debspawn',
    'debspawn.utils',
]

scripts = ['debspawn.py']

data_files = [('lib/debspawn', ['dsrun/dsrun.py'])]

long_description = ""

setup(
    name=__appname__,
    version=__version__,
    scripts=[],
    packages=packages,
    data_files=data_files,
    author="Matthias Klumpp",
    author_email="matthias@tenstral.net",
    long_description=long_description,
    description='Debian packager builder based on systemd-nspawn',
    license="LGPL-3.0+",
    url="https://lkorigin.github.io/",
    platforms=['any'],
    entry_points=scripts,
)
