# test_dev_watchdog.py
'''
Tests for dev_watchdog.watch_files

Requirements
------------
* Two-space indent, single quotes
* Uses pytest and watchdog's real backend
'''

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from pydev_repl import dev_watchdog as dw


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────
def _touch(path: Path, text: str = 'x') -> None:
  path.write_text(text, encoding='utf-8')
  # Ensure mtime bumps even on very fast writes
  os.utime(path, None)


# ─────────────────────────────────────────────────────────────────────────────
# Test: single change triggers callback exactly once
# ─────────────────────────────────────────────────────────────────────────────
def test_single_write(tmp_path: Path):
  f = tmp_path / 'a.txt'
  _touch(f, 'first')

  event = threading.Event()

  def on_change(paths):
    assert paths == {f.resolve()}
    event.set()

  stop = dw.watch_files([f], on_change, debounce_sec=0.05)
  try:
    _touch(f, 'second')
    assert event.wait(2.0), 'callback did not fire'
  finally:
    stop()


# ─────────────────────────────────────────────────────────────────────────────
# Test: burst of writes debounced into one callback
# ─────────────────────────────────────────────────────────────────────────────
def test_debounce(tmp_path: Path):
  f = tmp_path / 'b.txt'
  _touch(f, '0')

  hits: list[set[Path]] = []

  def on_change(paths):
    hits.append(paths)

  stop = dw.watch_files([f], on_change, debounce_sec=0.2)
  try:
    # three rapid modifications within < debounce period
    for i in range(3):
      _touch(f, str(i + 1))
      time.sleep(0.05)
    time.sleep(0.5)        # wait long enough for debounce window to close
    assert len(hits) == 1, f'expected 1 callback, got {len(hits)}'
    assert hits[0] == {f.resolve()}
  finally:
    stop()


# ─────────────────────────────────────────────────────────────────────────────
# Test: stop() halts further notifications
# ─────────────────────────────────────────────────────────────────────────────
def test_stop_prevents_future_events(tmp_path: Path):
  f = tmp_path / 'c.txt'
  _touch(f, 'init')

  hit = threading.Event()

  def on_change(_):
    hit.set()

  stop = dw.watch_files([f], on_change, debounce_sec=0.05)
  # first change should fire
  _touch(f, '1')
  assert hit.wait(2.0)
  hit.clear()

  # stop the watcher
  stop()

  # modify again; should NOT set the event
  _touch(f, '2')
  time.sleep(0.3)
  assert not hit.is_set(), 'callback fired after stop()'
