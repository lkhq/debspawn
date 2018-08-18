#!/usr/bin/env python3

import os
import sys
from debspawn import cli

thisfile = __file__
if not os.path.isabs(thisfile):
    thisfile = os.path.normpath(os.path.join(os.getcwd(), thisfile))

sys.exit(cli.run(thisfile, sys.argv[1:]))
