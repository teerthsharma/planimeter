"""`python -m planimeter` - the Windows escape hatch when Scripts/ is off PATH."""

import sys

from .cli import main

sys.exit(main())
