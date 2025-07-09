# parse.py
'''
Diff-analysis helper: affected_snippet(old_src, new_src) → snippet
Two-space indent, single quotes everywhere.
'''

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import List, Set


# ─────────────────────────────────────────────────────────────────────────────
# 0.  Normalise input
# ─────────────────────────────────────────────────────────────────────────────
def _sanitise(src: str) -> str:
  '''Ensure exactly one trailing newline.'''
  return src.rstrip('\n') + '\n'

def _is_comment_or_blank(line: str) -> bool:
  stripped = line.lstrip()
  return stripped == '' or stripped.startswith('#')

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Static-analysis helpers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _Stmt:
  idx: int
  start: int
  end: int
  src: str
  provides: Set[str]
  depends: Set[str]
  is_def: bool


class _LoadNameFinder(ast.NodeVisitor):
  '''Collect *load-context* names at top level (skip nested defs).'''

  def __init__(self) -> None:
    self.names: Set[str] = set()

  def visit_FunctionDef(self, node: ast.FunctionDef) -> None:     # noqa
    pass  # skip inner scope

  visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

  def visit_Name(self, node: ast.Name) -> None:                   # type: ignore[override]
    if isinstance(node.ctx, ast.Load):
      self.names.add(node.id)


def _collect_target_names(target) -> Set[str]:
  '''Recursively gather names assigned in targets (incl. unpacking).'''
  names: Set[str] = set()
  if isinstance(target, ast.Name):
    names.add(target.id)
  elif isinstance(target, (ast.Tuple, ast.List)):
    for elt in target.elts:
      names |= _collect_target_names(elt)
  return names


def _scan(lines: List[str]) -> List[_Stmt]:
  mod = ast.parse(''.join(lines))
  stmts: List[_Stmt] = []

  for i, node in enumerate(mod.body):
    s, e = node.lineno - 1, getattr(node, 'end_lineno', node.lineno) - 1
    is_def = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))

    # —— symbols provided ——————————————————————————————————————— #
    provides: Set[str] = set()
    if is_def:
      provides.add(node.name)
    elif isinstance(node, ast.Assign):
      for t in node.targets:
        provides |= _collect_target_names(t)
    elif isinstance(node, ast.AugAssign):
      provides |= _collect_target_names(node.target)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
      for n in node.names:
        provides.add(n.asname or n.name.split('.')[0])

    # —— dependencies (load context + aug-assign targets) ———————— #
    depends: Set[str] = set()
    if not (is_def or isinstance(node, (ast.Import, ast.ImportFrom))):
      finder = _LoadNameFinder()
      finder.visit(node)
      depends |= finder.names
      if isinstance(node, ast.AugAssign):
        # target is read as well as written
        depends |= _collect_target_names(node.target)

    stmts.append(
      _Stmt(
        idx=i,
        start=s,
        end=e,
        src=''.join(lines[s : e + 1]),
        provides=provides,
        depends=depends,
        is_def=is_def,
      )
    )
  return stmts


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Public API
# ─────────────────────────────────────────────────────────────────────────────
def affected_snippet(old_src: str, new_src: str) -> str:
  '''
  Return a snippet (from *new_src*) with every top-level statement that is
  directly changed, indirectly affected (through symbol dependencies), **or**
  immediately contiguous (no blank line) to a dirty statement.
  '''
  old_src = _sanitise(old_src)
  new_src = _sanitise(new_src)

  old_lines = old_src.splitlines(keepends=True)
  new_lines = new_src.splitlines(keepends=True)

  # —— 1. diff → line numbers changed in *new* ——————————————— #
  changed_lines: Set[int] = set()
  lo = ln = 0
  for d in difflib.ndiff(old_lines, new_lines):
    tag = d[:2]
    if tag == '  ':
      lo += 1
      ln += 1
    elif tag == '- ':
      lo += 1
    elif tag == '+ ':
      # Only count as change if the *added* line isn't comment/blank
      if not _is_comment_or_blank(new_lines[ln]):
        changed_lines.add(ln)
      ln += 1

  stmts = _scan(new_lines)

  # —— 2. seed dirty sets ———————————————————————————————— #
  direct_dirty_ids = {
    s.idx for s in stmts if any(s.start <= ln <= s.end for ln in changed_lines)
  }
  dirty_ids = set(direct_dirty_ids)
  dirty_syms = {sym for s in stmts if s.idx in dirty_ids for sym in s.provides}

  # —— 3. dependency propagation ——————————————————————————— #
  changed = True
  while changed:
    changed = False
    for s in stmts:
      if s.idx in dirty_ids:
        continue
      if s.depends & dirty_syms:
        dirty_ids.add(s.idx)
        dirty_syms |= s.provides
        changed = True

  # —— 4. include contiguous statements *after non-def dirty stmts* —— #
  for i, s in enumerate(stmts):
    if s.idx not in direct_dirty_ids or s.is_def:
      continue                       # skip if not direct-dirty or is a def
    j = i + 1
    while j < len(stmts) and stmts[j].start == stmts[j - 1].end + 1:
      if stmts[j].is_def:
        break                        # stop before a definition
      dirty_ids.add(stmts[j].idx)
      j += 1

  # —— 5. build snippet ———————————————————————————————— #
  return ''.join(s.src for s in stmts if s.idx in dirty_ids)
