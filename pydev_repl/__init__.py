# pydev_repl/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
  __version__ = version(__name__)
except PackageNotFoundError:
  __version__ = '0.0.0.dev0'

from .context import run, globals_of, Config
from .parse import affected_snippet
from .dev_watchdog import watch_files
from .dev_argparse import parse_argv

__all__ = ['run', 'globals_of', 'Config', 'affected_snippet', 'watch_files', 'parse_argv']
