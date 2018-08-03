#!/usr/bin/env python3

from debspawn import cli
import sys, os

thisfile = __file__
if not os.path.isabs(thisfile):
    thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))

sys.exit(cli.run(thisfile, sys.argv[1:]))
