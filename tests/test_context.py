# test_context_runner.py
'''
Comprehensive tests for context_runner.run / globals_of.

Two-space indent, single quotes everywhere.
'''

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path
from types import MappingProxyType

import pytest

from pydev_repl import context
from pydev_repl.parse import affected_snippet

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_cache():
  'Clear context cache before each test for isolation.'
  context._CTX.clear()
  yield
  context._CTX.clear()


@pytest.fixture
def sample_src():
  return textwrap.dedent('''
    import math
    x = 1
    def foo():
      return x + 1
  ''').strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Context creation
# ─────────────────────────────────────────────────────────────────────────────
def test_create_from_raw(sample_src):
  key = context.run(sample_src)
  ns = context.globals_of(key)
  assert ns['x'] == 1
  assert 'math' in ns


def test_create_from_file(tmp_path: Path, sample_src):
  f = tmp_path / 'code.py'
  f.write_text(sample_src, encoding='utf-8')
  key = context.run(str(f))
  ns = context.globals_of(key)
  assert ns['foo']() == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Context reuse & patch
# ─────────────────────────────────────────────────────────────────────────────
def test_key_reuse_and_patch(sample_src):
  key1 = context.run(sample_src)
  context.run(key1, 'x = x + 4')
  ns = context.globals_of(key1)
  assert ns['x'] == 5
  # same key returned
  key2 = context.run(key1)
  assert key1 == key2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Config enforcement
# ─────────────────────────────────────────────────────────────────────────────
def test_config_execute_imports_false(tmp_path: Path):
  src = 'import math\nx = 1'
  cfg = context.Config(execute_imports=False)
  key = context.run(src, cfg=cfg)
  ns = context.globals_of(key)
  assert 'math' not in ns and ns['x'] == 1


def test_config_define_functions_false():
  src = 'def f():\n  return 1'
  key = context.run(src, cfg=context.Config(define_functions=False))
  ns = context.globals_of(key)
  assert 'f' not in ns


def test_config_run_code_false():
  src = 'y = 7'
  key = context.run(src, cfg=context.Config(run_code=False))
  ns = context.globals_of(key)
  assert 'y' not in ns


def test_config_mixed_flags():
  src = 'import math\ndef f():\n  return 2\nz = 3'
  cfg = context.Config(execute_imports=True, define_functions=False, run_code=False)
  key = context.run(src, cfg=cfg)
  ns = context.globals_of(key)
  assert 'math' in ns and 'f' not in ns and 'z' not in ns


# ─────────────────────────────────────────────────────────────────────────────
# 4. Isolation of contexts
# ─────────────────────────────────────────────────────────────────────────────
def test_isolated_contexts():
  k1 = context.run('a = 1')
  k2 = context.run('a = 100')
  assert context.globals_of(k1)['a'] == 1
  assert context.globals_of(k2)['a'] == 100


# ─────────────────────────────────────────────────────────────────────────────
# 5. Edge / uncommon cases
# ─────────────────────────────────────────────────────────────────────────────
def test_empty_source():
  key = context.run('')
  ns = context.globals_of(key)
  assert ns == {'__name__': '__main__'}


def test_comment_only_source():
  key = context.run('# just a comment')
  ns = context.globals_of(key)
  # assert ns == {'__name__': '__main__'}
  assert ns['__name__'] == '__main__'
  assert len(ns) == 2 and '__builtins__' in ns


def test_patch_noop_when_none(sample_src):
  key = context.run(sample_src)
  ns_before = context.globals_of(key)
  context.run(key)  # no patch
  ns_after = context.globals_of(key)
  assert ns_before == ns_after


def test_syntax_error_patch_raises(sample_src):
  key = context.run(sample_src)
  with pytest.raises(SyntaxError):
    context.run(key, 'def broken(:\n  pass')


# ─────────────────────────────────────────────────────────────────────────────
# 6. affected_snippet integration sanity
# ─────────────────────────────────────────────────────────────────────────────
def test_patch_via_affected_snippet():
  old = 'x = 1\ny = x + 1'
  new = 'x = 5\ny = x + 1'
  patch = affected_snippet(old, new)
  key = context.run(old)
  context.run(key, patch)
  assert context.globals_of(key)['x'] == 5
  assert context.globals_of(key)['y'] == 6


# ─────────────────────────────────────────────────────────────────────────────
# 7. Contiguous-line heuristic (forward only, non-def)
# ─────────────────────────────────────────────────────────────────────────────
def test_contiguous_forward_statement_executes(tmp_path: Path):
  old = 'x = 1\n\ny = x + 1'
  new = 'x = 2\n\ny = x + 1'
  patch = affected_snippet(old, new)
  key = context.run(old)
  context.run(key, patch)
  assert context.globals_of(key)['y'] == 3


def test_contiguous_definition_not_pulled():
  old = 'x = 1\ndef foo():\n  return x'
  new = 'x = 2\ndef foo():\n  return x'
  patch = affected_snippet(old, new)
  assert 'def foo' not in patch  # contiguous def should be omitted


# ─────────────────────────────────────────────────────────────────────────────
# Reload-modules integration test
# ─────────────────────────────────────────────────────────────────────────────
def test_reload_modules_flag_switches_underlying_module():
  from pydev_repl import context as ctx
  import types

  # --- initial script uses built-in math -----------------------------------
  src = 'import math\nx = math.sqrt(4)'
  key = ctx.run(src, cfg=ctx.Config(reload_modules=False))
  ns = ctx.globals_of(key)

  # baseline: math from stdlib, value == 2.0
  assert isinstance(ns['math'], types.ModuleType)
  assert ns['math'].__name__ == 'math'
  assert ns['x'] == 2.0 and type(ns['x']) == type(2.0)

  # --- patch re-binds name "math" to cmath ---------------------------------
  patch = 'import cmath as math\nx = math.sqrt(4)'
  ctx.run(key, patch)                 # same context, reload flag still on
  ns = ctx.globals_of(key)

  # After patch: math now points to cmath (complex answers)
  assert ns['math'].__name__ == 'cmath'
  assert ns['x'] == 2 + 0j and type(ns['x']) == type(2 + 0j)


def test_module_reload_via_empty_patch(tmp_path):
  from pydev_repl import context as ctx
  from tempfile import NamedTemporaryFile
  import time

  def write_into(f, text):
    f.seek(0)
    f.truncate(0)
    f.write(text)
    f.flush()


  with NamedTemporaryFile(mode='w', encoding='utf-8', dir='.', suffix='.py') as mod_file:
    # ── 1. build initial files ──────────────────────────────────────────────
    mod_body = 'def foo():\n  return {}\n'
    mod_name = mod_file.name.split('/')[-1].split('.')[0]
    write_into(mod_file, mod_body.format(2))

    src = f'import {mod_name}\nx = {mod_name}.foo()'

    # ── 2. create context with reload_modules=True ──────────────────────────
    cfg = ctx.Config(reload_modules=True)
    key = ctx.run(src, cfg=cfg)

    ns = ctx.globals_of(key)
    assert ns['x'] == 2                               # baseline

    # ── 3. modify mod.py to change behaviour ────────────────────────────────
    time.sleep(1.001) # ensure mtime of mod_file is different
    write_into(mod_file, mod_body.format(4))

    # ── 4. reuse context with an *empty* patch (single newline) ─────────────
    ctx.run(key, src)

    ns = ctx.globals_of(key)
    assert ns['x'] == 4                               # reloaded; value updated
    # assert ns['y'] == ns['x']



# ─────────────────────────────────────────────────────────────────────────────
# Big integration test: multi-patch evolution
# ─────────────────────────────────────────────────────────────────────────────
def test_multi_patch_evolution():
  from pydev_repl import context as ctx

  # ---------- initial, deliberately multi-line & varied --------------------
  initial_src = '''
import math as m

def square(x):
  # classic square
  return x * x

nums = [1, 2, 3]
mult = 2
squares = [square(n) for n in nums]
scaled = [n * mult for n in squares]

def power_sum(xs, p=1):
  return sum(n ** p for n in xs)

result1 = power_sum(scaled)

poem = """Roses are red,
Violets are blue."""
'''.strip()

  # ---------- patch 1: change data only ------------------------------------
  patch1 = '''
nums = [10, 20, 30]
mult = 3
squares = [square(n) for n in nums]
scaled = [n * mult for n in squares]
result1 = power_sum(scaled)
'''.strip()

  # ---------- patch 2: add helper & derived value --------------------------
  patch2 = '''
def avg(xs):
  return sum(xs) / len(xs)

avg_scaled = avg(scaled)
'''.strip()

  # ---------- patch 3: change function logic & recompute -------------------
  patch3 = '''
def square(x):
  # square plus linear term
  return x * x + x

squares = [square(n) for n in nums]
scaled = [n * mult for n in squares]
result1 = power_sum(scaled)
avg_scaled = avg(scaled)
'''.strip()

  # ---------- 1) create context and assert initial state -------------------
  key = ctx.run(initial_src)
  ns = ctx.globals_of(key)
  assert ns['squares'] == [1, 4, 9]
  assert ns['scaled']  == [2, 8, 18]
  assert ns['result1'] == 28

  # ---------- 2) apply patch 1 and re-check --------------------------------
  ctx.run(key, patch1)
  ns = ctx.globals_of(key)
  assert ns['nums']    == [10, 20, 30]
  assert ns['mult']    == 3
  assert ns['squares'] == [100, 400, 900]
  assert ns['scaled']  == [300, 1200, 2700]
  assert ns['result1'] == 4200           # 300+1200+2700

  # ---------- 3) patch 2: new helper + avg ---------------------------------
  ctx.run(key, patch2)
  ns = ctx.globals_of(key)
  assert 'avg' in ns
  assert ns['avg_scaled'] == 1400.0      # 4200 / 3

  # ---------- 4) patch 3: change square logic ------------------------------
  ctx.run(key, patch3)
  ns = ctx.globals_of(key)
  # new squares: n^2 + n  for 10,20,30
  assert ns['squares'] == [110, 420, 930]
  assert ns['scaled']  == [330, 1260, 2790]
  assert ns['result1'] == 4380           # sum of scaled
  assert ns['avg_scaled'] == 1460        # 4380 / 3

  # unchanged pieces
  assert ns['poem'].startswith('Roses are red')
  assert ns['power_sum'].__name__ == 'power_sum'


