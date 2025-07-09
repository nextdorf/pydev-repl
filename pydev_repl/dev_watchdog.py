# dev_watchdog.py
'''
Event-driven file-watching based on the `watchdog` library.

Install watchdog first:
    pip install watchdog

API
---
watch_files(paths, on_change, recursive=False)  ->  stop_fn
    • paths      : iterable of file or directory paths
    • on_change  : callback(Set[Path]) called with the set of modified *files*
    • recursive  : watch sub-directories when a *directory* path is given
Returns:
    stop_fn()    : call to stop the observer thread cleanly
'''

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Set

from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from watchdog.observers import Observer


class _ChangeHandler(FileSystemEventHandler):
  def __init__(self, watched: Set[Path], callback: Callable[[Set[Path]], None]) -> None:
    super().__init__()
    self._files = watched
    self._cb = callback

  # “modified” also fires on create/overwrite for most editors
  def on_modified(self, event: FileModifiedEvent):  # type: ignore[override]
    p = Path(event.src_path).resolve()
    if p in self._files:          # ignore temp files etc.
      self._cb({p})


def watch_files(
  paths: Iterable[str | Path],
  on_change: Callable[[Set[Path]], None],
  *,
  recursive: bool = False,
  debounce_sec: float = 0.05,   # collapse rapid bursts
) -> Callable[[], None]:
  paths = {Path(p).resolve() for p in paths}
  handler = _ChangeHandler(paths, _debounced(on_change, debounce_sec))

  observer = Observer()
  for p in paths:
    observer.schedule(handler, str(p.parent), recursive=recursive)
  observer.start()

  def stop() -> None:
    observer.stop()
    observer.join()

  return stop


# ---------- utility: simple debounce ----------------------------------------
def _debounced(fn: Callable[[Set[Path]], None], wait: float):
  last_call: list[float] = [0.0]
  pending: Set[Path] = set()

  def _wrapped(files: Set[Path]) -> None:
    nonlocal pending
    pending |= files
    now = time.time()
    if now - last_call[0] > wait:
      last_call[0] = now
      to_send, pending = pending, set()
      fn(to_send)

  return _wrapped
