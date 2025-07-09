# context.py
'''
Run or patch Python source in cached execution contexts.

Public call
-----------
    run(ctx_or_src, patch: str | None = None, cfg: Config | None = None) -> str
        • ctx_or_src : context key | file path | raw source string
        • patch      : optional snippet to execute in that context
        • cfg        : optional Config only when *creating* a context
Returns the context-key.
'''

from __future__ import annotations

import importlib
# import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Dict, List
import ast

from .parse import affected_snippet


# ─────────────────────────────────────────────────────────────────────────────
# Config — only controls which kinds of statements run
# ─────────────────────────────────────────────────────────────────────────────
class Config:
  def __init__(
    self,
    execute_imports: bool = True,
    define_functions: bool = True,
    run_code: bool = True,
    reload_modules: bool = False,
  ) -> None:
    self.execute_imports = execute_imports
    self.define_functions = define_functions
    self.run_code = run_code
    self.reload_modules = reload_modules


# ─────────────────────────────────────────────────────────────────────────────
# Internal cache: key → {'globals', 'src', 'cfg'}
# ─────────────────────────────────────────────────────────────────────────────
_CTX: Dict[str, Dict[str, object]] = {}


def _new_key() -> str:
  return uuid.uuid4().hex


# ─────────────────────────────────────────────────────────────────────────────
# Execution helpers
# ─────────────────────────────────────────────────────────────────────────────
def _should_run_line(line: str, cfg: Config) -> bool:
  '''Decide if a single top-level line should execute under *cfg*.'''
  import ast
  stripped = line.strip()
  if not stripped:
    return False
  node = ast.parse(line).body[0]
  if isinstance(node, (ast.Import, ast.ImportFrom)):
    return cfg.execute_imports
  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
    return cfg.define_functions
  return cfg.run_code


def _exec(src: str, g: Dict[str, object], cfg: Config) -> None:
  '''Plain exec with caller-supplied globals; no I/O redirection.'''
  if not src.strip():
    return 

  # pre_mods = {name: mod for name, mod in g.items() if isinstance(mod, ModuleType)}
  # if pre_mods:
  #   src_prefix = 'import importlib\n'
  #   for mod_name in pre_mods.keys():
  #     src_prefix += f'importlib.reload({mod_name})\n'
  #   src = f'{src_prefix}\n{src}'
  if cfg.reload_modules:
    for name, obj in g.items():
      if isinstance(obj, ModuleType):
        g[name] = importlib.reload(obj)

  code = compile(src, g.get('__file__', '<string>'), 'exec')
  exec(code, g, g)

# def _exec(src: str, g: Dict[str, object], cfg: Config) -> None:
#   '''Plain exec with caller-supplied globals; no I/O redirection.'''
#   if not src.strip():
#     return 

#   # pre_mods = {name: mod for name, mod in g.items() if isinstance(mod, ModuleType)}

#   code = compile(src, g.get('__file__', '<string>'), 'exec')
#   exec(code, g, g)

#   if cfg.reload_modules:
#     for name, obj in g.items():
#       if isinstance(obj, ModuleType):
#         # reload existing or newly imported module
#         importlib.reload(obj)
#         g[name] = obj

#     # # Clean up modules removed in the executed snippet when reload flag is on
#     # for name in list(pre_mods):
#     #   if name not in g or not isinstance(g[name], ModuleType):
#     #     continue
#     #   # Still the same module object?  Re-load it as well
#     #   importlib.reload(g[name])

def _execute_fresh(src: str, cfg: Config) -> Dict[str, object]:
  '''
  Execute *src* in a brand-new globals dict, respecting the Config flags
  **statement-wise** (never chopping multi-line blocks).
  '''
  g: Dict[str, object] = {'__name__': '__main__'}

  # Fast-path: all switches ON  → execute whole script
  if cfg.execute_imports and cfg.define_functions and cfg.run_code:
    _exec(src, g, cfg)
    return g

  # Build snippet containing only allowed statements
  lines = src.splitlines(keepends=True)
  module = ast.parse(src)
  selected_chunks: list[str] = []

  for node in module.body:
    keep = False
    if isinstance(node, (ast.Import, ast.ImportFrom)):
      keep = cfg.execute_imports
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
      keep = cfg.define_functions
    else:
      keep = cfg.run_code

    if keep:
      start = node.lineno - 1
      end = getattr(node, 'end_lineno', node.lineno) - 1
      selected_chunks.append(''.join(lines[start : end + 1]))

  _exec(''.join(selected_chunks), g, cfg)
  return g


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def run(ctx_or_src: str, patch: str | None = None, cfg: Config | None = None) -> str:
  '''
  • If *ctx_or_src* is an existing context key, reuse it (and apply patch).
  • Otherwise treat it as file path (if exists) or raw source, create context.
  • Always return the context key.
  '''
  # --- existing context -----------------------------------------------------
  if ctx_or_src in _CTX:
    key = ctx_or_src
    ctx = _CTX[key]
    if patch:
      _exec(patch, ctx['globals'], ctx['cfg'])
      ctx['src'] += '\n' + patch
    return key

  # --- new context ----------------------------------------------------------
  src_path = Path(ctx_or_src)
  try:
    is_path = (
          len(ctx_or_src) < 4096
      and not any(c in ctx_or_src for c in ':*\n\t')
      and src_path.exists()
      and src_path.is_file()
    )
  except:
    is_path = False
  src_text = src_path.read_text(encoding='utf-8') if is_path else ctx_or_src

  cfg = cfg or Config()
  g = _execute_fresh(src_text, cfg)

  key = _new_key()
  _CTX[key] = {'globals': g, 'src': src_text, 'cfg': cfg}

  if patch:
    _exec(patch, g, cfg)
    _CTX[key]['src'] += '\n' + patch

  return key


# ─────────────────────────────────────────────────────────────────────────────
# Convenience accessor
# ─────────────────────────────────────────────────────────────────────────────
def globals_of(key: str) -> Dict[str, object]:
  return _CTX[key]['globals'].copy()
