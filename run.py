#!/usr/bin/env python3
# Akita WAIS Launcher
# Organization: Akita Engineering
# License: GPLv3

import sys
import os

# Ensure the package is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from akita_wais import cli

if __name__ == "__main__":
    cli.main()
