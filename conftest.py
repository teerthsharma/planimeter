"""Puts the repository root on sys.path so `import corpus` works from tests/.

pytest inserts the directory of the topmost conftest.py, so this file existing
is the whole mechanism. corpus.py is deliberately not inside the package - it
is the source of every truth value and users never install it.
"""
