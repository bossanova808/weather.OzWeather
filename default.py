# -*- coding: utf-8 -*-

import sys
from resources.lib import ozweather

# This is kept as minimal as possible per @enen92's advice that:
#  Reason for this is that entry point files are the only python files that are not compiled to bytecode (pyc).
#  Hence, you'll see a performance gain if you store your codebase in a "module"

if __name__ == "__main__":
    ozweather.run(sys.argv)

