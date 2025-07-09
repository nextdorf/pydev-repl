# test_parse.py
'''
Exhaustive tests for parse.affected_snippet.

* Two-space indent
* Single quotes only
* All code snippets are multiline literals
'''

from __future__ import annotations

import types

import numpy as np
import pytest

from pydev_repl.parse import affected_snippet


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _run(src: str) -> dict[str, object]:
  '''Execute *src* in a fresh module and return its globals dict.'''
  mod = types.ModuleType('sandbox')
  exec(src, mod.__dict__)
  return mod.__dict__


def _nl(s: str, and_strip: bool = True) -> str:
  '''Return *s* with exactly one trailing newline (matches helper output).'''
  s = s.strip() if and_strip else s.rstrip('\n')
  s = '\n'.join(si for si in s.splitlines() if si)
  return s + '\n'


# ─────────────────────────────────────────────────────────────────────────────
# Basic unit tests
# ─────────────────────────────────────────────────────────────────────────────
def test_assignment_change_propagates():
  '''Changing the value of x should force dependent y to rerun.'''
  old = '''
x = 1
y = x + 1
'''.strip()

  new = '''
x = 2
y = x + 1
'''.strip()

  expected = _nl('''
x = 2
y = x + 1
''')
  assert affected_snippet(old, new) == expected


def test_self_referential_assignment():
  '''Self-referential assignment must rerun when the initial value changes.'''
  old = '''
x = 1
x = x + 1
y = x * 2
'''.strip()

  new = '''
x = 5
x = x + 1
y = x * 2
'''.strip()

  expected = _nl('''
x = 5
x = x + 1
y = x * 2
''')
  assert affected_snippet(old, new) == expected


def test_function_body_change_triggers_call_rerun():
  '''Changing the function body should also rerun its call sites.'''
  old = '''
def foo():
  return 1
z = foo()
'''.strip()

  new = '''
def foo():
  return 2
z = foo()
'''.strip()

  expected = _nl('''
def foo():
  return 2
z = foo()
''')
  assert affected_snippet(old, new) == expected


def test_function_added_and_used():
  '''New function plus its first use; unchanged x line must not appear.'''
  old = '''
x = 1
'''.strip()

  new = '''
def inc(a):
  return a + 1
x = 1
y = inc(x)
'''.strip()

  expected = _nl('''
def inc(a):
  return a + 1
y = inc(x)
''')
  assert affected_snippet(old, new) == expected


def test_import_alias_change():
  '''Changing an import alias should rerun the alias and lines using it.'''
  old = '''
import math as m
r = m.sqrt(4)
'''.strip()

  new = '''
import cmath as m
r = m.sqrt(4)
'''.strip()

  expected = _nl('''
import cmath as m
r = m.sqrt(4)
''')
  assert affected_snippet(old, new) == expected


# ─────────────────────────────────────────────────────────────────────────────
# Edge-case unit tests
# ─────────────────────────────────────────────────────────────────────────────
def test_param_shadowing_not_dirty():
  '''Variable sharing name with function param must not dirty the definition.'''
  old = '''
x = 1
def foo(x):
  return x + 1
y = foo(x)
'''.strip()

  new = '''
x = 2
def foo(x):
  return x + 1
y = foo(x)
'''.strip()

  expected = _nl('''
x = 2
y = foo(x)
''')
  assert affected_snippet(old, new) == expected


def test_line_deletion_only():
  '''Deleting an assignment removes its symbol; dependent line reruns.'''
  old = '''
a = 1
b = 2
c = a + b
'''.strip()

  new = '''
a = 1
c = a + 1
'''.strip()

  expected = _nl('''
c = a + 1
''')
  assert affected_snippet(old, new) == expected


def test_augmented_assignment_dependency():
  '''x += 1 both reads and writes x; it must rerun when x changes.'''
  old = '''
x = 1
x += 1
y = x
'''.strip()

  new = '''
x = 10
x += 1
y = x
'''.strip()

  expected = _nl('''
x = 10
x += 1
y = x
''')
  assert affected_snippet(old, new) == expected


def test_tuple_assignment_propagates():
  '''Tuple assignment provides both a and b; dependents rerun.'''
  old = '''
a, b = 1, 2
c = a + b
'''.strip()

  new = '''
a, b = 3, 4
c = a + b
'''.strip()

  expected = _nl('''
a, b = 3, 4
c = a + b
''')
  assert affected_snippet(old, new) == expected


def test_trailing_newline_insensitivity():
  '''Helper normalises trailing newline differences automatically.'''
  src1 = _nl('''
x = 1
y = 2
''', and_strip=False)
  src2 = '''
x = 3
y = 2
'''.strip()  # no final newline

  expected = _nl('''
x = 3
y = 2
''')
  assert affected_snippet(src1, src2) == expected


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────
def test_numpy_self_weighted_avg_patch():
  '''Patch execution must reproduce result of full rerun (NumPy example).'''
  template = '''
import numpy as np

def self_weighted_avg(xs):
  xs = np.asarray(xs)
  abs_xs = abs(xs)
  return abs_xs / np.sum(abs_xs, axis=-1, keepdims=True)

xs = {xs_val}
xs = np.asarray(xs) + 1
wxs = self_weighted_avg(xs)
wxs2 = self_weighted_avg(xs)**2
w2xs = self_weighted_avg(xs**2)
dwxs2 = w2xs - wxs2
'''.strip()

  old_src = template.format(xs_val='[-4, -3, -2, -1, 1, 2, 3, 4]')
  new_src = template.format(xs_val='np.arange(-4, 5)')

  full_ns = _run(new_src)
  patch = affected_snippet(old_src, new_src)

  patched_ns = _run(old_src)
  exec(patch, patched_ns)

  assert np.allclose(full_ns['dwxs2'], patched_ns['dwxs2'])


def test_long_dependency_chain():
  '''Five-step dependency chain must rerun completely when root changes.'''
  old = '''
a = 1
b = a + 1
c = b + 1
d = c + 1
e = d + 1
'''.strip()

  new = '''
a = 42
b = a + 1
c = b + 1
d = c + 1
e = d + 1
'''.strip()

  expected = _nl('''
a = 42
b = a + 1
c = b + 1
d = c + 1
e = d + 1
''')
  assert affected_snippet(old, new) == expected

  ns_full = _run(new)
  ns_patch = _run(old)
  exec(expected, ns_patch)
  assert ns_full['e'] == ns_patch['e']

# ─────────────────────────────────────────────────────────────────────────────
# Additional unit tests (ADVANCED CASES)
# ─────────────────────────────────────────────────────────────────────────────
def test_augassign_chained_dependency():
  '''
  Two += statements chained together: both must re-run when the seed changes.
  '''
  old = '''
x = 1
x += 1
x += 2
y = x
'''.strip()

  new = '''
x = 5
x += 1
x += 2
y = x
'''.strip()

  expected = _nl('''
x = 5
x += 1
x += 2
y = x
''')
  assert affected_snippet(old, new) == expected


def test_walrus_operator_dependency():
  '''
  Walrus operator reads *and* writes the target; depends on previous value.
  '''
  old = '''
count = 3
if (count := count + 1) > 0:
  msg = 'ok'
'''.strip()

  new = '''
count = 10
if (count := count + 1) > 0:
  msg = 'ok'
'''.strip()

  expected = _nl('''
count = 10
if (count := count + 1) > 0:
  msg = 'ok'
''')
  assert affected_snippet(old, new) == expected


def test_import_from_alias_change():
  '''Alias in 'from … import … as …' propagates to its uses.'''
  old = '''
from math import sqrt as root
val = root(4)
'''.strip()

  new = '''
from cmath import sqrt as root
val = root(4)
'''.strip()

  expected = _nl('''
from cmath import sqrt as root
val = root(4)
''')
  assert affected_snippet(old, new) == expected


def test_list_comprehension_dependency():
  '''Changing the iterable forces comprehension rerun.'''
  old = '''
nums = [1, 2, 3]
squares = [n*n for n in nums]
'''.strip()

  new = '''
nums = [10, 11, 12]
squares = [n*n for n in nums]
'''.strip()

  expected = _nl('''
nums = [10, 11, 12]
squares = [n*n for n in nums]
''')
  assert affected_snippet(old, new) == expected


def test_lambda_dependency():
  '''Lambda uses outer variable; redefinition should rerun call.'''
  old = '''
k = 2
f = lambda x: x * k
r = f(3)
'''.strip()

  new = '''
k = 5
f = lambda x: x * k
r = f(3)
'''.strip()

  expected = _nl('''
k = 5
f = lambda x: x * k
r = f(3)
''')
  assert affected_snippet(old, new) == expected


def test_multiple_targets_same_name():
  '''`x = y = 1` provides both; change must rerun chain.'''
  old = '''
x = y = 1
z = x + y
'''.strip()

  new = '''
x = y = 5
z = x + y
'''.strip()

  expected = _nl('''
x = y = 5
z = x + y
''')
  assert affected_snippet(old, new) == expected


def test_nested_function_body_no_prop():
  '''
  Changing body *inside* nested fn should NOT pull top-level call to outer fn.
  '''
  old = '''
def outer():
  def inner():
    return 1
  return inner()

res = outer()
'''.strip()

  new = '''
def outer():
  def inner():
    return 2
  return inner()

res = outer()
'''.strip()

  expected = _nl('''
def outer():
  def inner():
    return 2
  return inner()

res = outer()
''')
  assert affected_snippet(old, new) == expected


def test_blank_line_breaks_contiguity():
  '''
  A blank line between dirty and clean stmts should stop automatic inclusion.
  '''
  old = '''
x = 1

y = x + 1
'''.strip()

  new = '''
x = 2

y = x + 1
'''.strip()

  expected = _nl('''
x = 2
y = x + 1
''')
  assert affected_snippet(old, new) == expected


def test_class_definition_and_use():
  '''Class def change must rerun instantiation but not unrelated lines.'''
  old = '''
class Foo:
  value = 1

obj = Foo()
other = 42
'''.strip()

  new = '''
class Foo:
  value = 2

obj = Foo()
other = 42
'''.strip()

  expected = _nl('''
class Foo:
  value = 2

obj = Foo()
''')
  assert affected_snippet(old, new) == expected


def test_tuple_unpack_target_partial_change():
  '''
  Only one target (a) changes; dependent on a must rerun, b-only user stays.
  '''
  old = '''
a, b = 1, 2
use_a = a * 2
use_b = b * 3
'''.strip()

  new = '''
a, b = 10, 2
use_a = a * 2
use_b = b * 3
'''.strip()

  # TODO: Shouldn't rerun use_b
  expected = _nl('''
a, b = 10, 2
use_a = a * 2
use_b = b * 3
''')
  assert affected_snippet(old, new) == expected


def test_walrus_inside_comprehension():
  '''
  Walrus in comprehension creates/reads same var; change seed reruns comp.
  '''
  old = '''
seed = 1
vals = [(seed := seed + 1) for _ in range(3)]
'''.strip()

  new = '''
seed = 5
vals = [(seed := seed + 1) for _ in range(3)]
'''.strip()

  expected = _nl('''
seed = 5
vals = [(seed := seed + 1) for _ in range(3)]
''')
  assert affected_snippet(old, new) == expected



# ─────────────────────────────────────────────────────────────────────────────
# Grand-all-features integration test
# ─────────────────────────────────────────────────────────────────────────────
def test_kitchen_sink_patch():
  '''
  Single patch touches:
    1. import alias (math → cmath)
    2. function body change (square)
    3. new helper function + first use (avg / avg_squares)
    4. data list mutation (nums)
    5. multiline-string extension (poem)
  … while leaving greet() and unrelated constant untouched.
  '''

  old_src = '''
import math as m

def greet(name):
  return f'Hello, {name}!'

def square(x):
  # old body
  return x * x

nums = [
  1,
  2,
  3,
  4,
  5
]
squares = [square(n) for n in nums]

poem = """Roses are red,
Violets are blue.
"""

r = m.sqrt(16)
unchanged_constant = 99
'''.strip()

  new_src = '''
import cmath as m

def greet(name):
  return f'Hello, {name}!'

def square(x):
  # Same body but with new comment
  return x * x

# new helper function + first call
def avg(xs):
  return sum(xs) / len(xs)

nums = [
  1,
  2,
  3,
  5,
  4
]
squares = [square(n) for n in nums]
avg_squares = avg(squares)

poem = """Roses are red,
Violets are blue,
Sugar is sweet.
"""

r = m.sqrt(16)
unchanged_constant = 99
'''.strip()

  expected = _nl('''
import cmath as m

def avg(xs):
  return sum(xs) / len(xs)

nums = [
  1,
  2,
  3,
  5,
  4
]
squares = [square(n) for n in nums]
avg_squares = avg(squares)

poem = """Roses are red,
Violets are blue,
Sugar is sweet.
"""

r = m.sqrt(16)
''')

  # full execution for ground-truth
  full_ns = _run(new_src)

  # apply diff patch to old namespace
  patch = affected_snippet(old_src, new_src)
  assert patch == expected

  patched_ns = _run(old_src)
  exec(patch, patched_ns)

  # assertions – everything observable must match
  assert full_ns['squares'] == patched_ns['squares']
  assert full_ns['avg_squares'] == patched_ns['avg_squares']
  assert full_ns['r'] == patched_ns['r']
  assert full_ns['poem'] == patched_ns['poem']
  assert full_ns['unchanged_constant'] == patched_ns['unchanged_constant']
  # unchanged function greet should remain identical object
  assert full_ns['greet'].__code__.co_code == patched_ns['greet'].__code__.co_code
