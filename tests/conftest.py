import os
import sys

# ensure project root is on Python path for imports
test_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, test_root)
