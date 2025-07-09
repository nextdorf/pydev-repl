import argparse
from pathlib import Path
from typing import List, Optional


def parse_argv(argv: Optional[List[str]] = None) -> argparse.Namespace:
  '''
  Parse command-line arguments for *pydev-repl*.

  Parameters
  ----------
  argv
    A custom argument list (mainly for testing).  When None the
    function uses ``sys.argv[1:]`` automatically.

  Returns
  -------
  argparse.Namespace
    • source   : Path to initial script (or '-' for stdin)  
    • patch    : Optional patch string / file path  
    • reload   : Bool flag - reload imported modules before each patch  
    • watch    : Bool flag - enable file-watch mode  
    • interval : Polling interval in seconds (when --watch)  
    • verbose  : Verbosity count (-v, -vv, …)
  '''
  parser = argparse.ArgumentParser(
      prog='pydev-repl',
      description='Incremental Python runner / REPL with hot-patching support.',
  )

  # positional: initial script
  parser.add_argument(
      'source',
      help='Path to the Python script to run, or "-" to read from stdin.',
      type=Path,
  )

  # optional patch
  parser.add_argument(
      '--patch',
      '-p',
      help='Patch code or file to execute after the initial run.',
      default=None,
  )

  # reload flag
  parser.add_argument(
      '--reload',
      action='store_true',
      help='Reload imported modules before executing each patch.',
  )

  # watch mode
  parser.add_argument(
      '--watch',
      '-w',
      action='store_true',
      help='Continuously watch the source & patch file(s) and rerun on change.',
  )
  parser.add_argument(
      '--interval',
      '-i',
      type=float,
      default=0.5,
      metavar='SEC',
      help='Polling interval for --watch (default: 0.5 s).',
  )

  # verbosity
  parser.add_argument(
      '--verbose',
      '-v',
      action='count',
      default=0,
      help='Increase logging verbosity; repeat for more detail.',
  )

  try:
    import argcomplete
    argcomplete.autocomplete(parser)
  except ImportError:
    pass
  return parser.parse_args(argv)
