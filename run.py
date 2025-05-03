#!/usr/bin/env python3
# Simple script to run the Akita WAIS CLI

import sys
# Ensure the akita_wais package is importable (adjust if needed based on installation)
# If installed via setup.py, this might not be necessary.
# If running directly from the source directory, it should work.
from akita_wais import cli

if __name__ == "__main__":
    cli.main()
