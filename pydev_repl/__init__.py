# pydev_repl/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
  __version__ = version(__name__)
except PackageNotFoundError:      # development mode
  __version__ = '0.0.0.dev0'

from .context import run, globals_of, Config          # re-export
from .parse import affected_snippet                   # re-export
from .dev_watchdog import watch_files                 # re-export

__all__ = [
  'run', 'globals_of', 'Config',
  'affected_snippet',
  'watch_files',
]
