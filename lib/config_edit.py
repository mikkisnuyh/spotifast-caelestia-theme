#!/usr/bin/env python3
"""JSON edits for install.sh and uninstall.sh.

    config_edit.py add-hook    CLI_JSON SCRIPT
    config_edit.py remove-hook CLI_JSON
    config_edit.py select      SETTINGS_JSON FILENAME

Edits keep every other setting, write through symlinks (so a cli.json kept in
a dotfiles repository stays a link), and replace the file atomically after copying it to
<name>.caelestia-spotifast.bak. A file
that is not valid JSON is never touched.
"""

import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

NAME = "caelestia-spotifast"
# What versions before the hook went on its own line put before it.
LEGACY_SEPARATOR = "; "
BACKUP_SUFFIX = f".{NAME}.bak"

# The generator is one self-contained file; its atomic_write is shared from it.
_loader = importlib.machinery.SourceFileLoader(
    "caelestia_spotifast", str(Path(__file__).resolve().parent.parent / NAME)
)
generator = importlib.util.module_from_spec(importlib.util.spec_from_loader(_loader.name, _loader))
_loader.exec_module(generator)


class EditError(Exception):
    pass


def read(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text.removeprefix("﻿")) if text.strip() else {}
    except json.JSONDecodeError as error:
        raise EditError(f"{path} is not valid JSON ({error}); leaving it unchanged") from error
    if not isinstance(data, dict):
        raise EditError(f"{path} does not hold a JSON object; leaving it unchanged")
    return data


def write(path: Path, data: dict, backup: bool) -> None:
    target = Path(os.path.realpath(path))
    if backup and target.exists():
        shutil.copy2(target, target.with_name(target.name + BACKUP_SUFFIX))
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    generator.atomic_write(target, json.dumps(data, indent=4, ensure_ascii=False) + "\n", mode)


def is_ours(command: str) -> bool:
    """Whether `command` runs caelestia-spotifast and nothing else, from any
    directory (so an install with another --bin-dir is recognised too)."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    return len(words) == 1 and os.path.basename(words[0]) == NAME


def hook_with(existing: str, command: str) -> str:
    """`existing` with `command` run after it, on a line of its own: unlike
    `; command`, that also runs when the hook ends in a `# comment`."""
    existing = existing.rstrip()
    return f"{existing}\n{command}" if existing else command


def line_without_ours(line: str) -> str:
    kept = []
    for part in line.split(LEGACY_SEPARATOR):
        if is_ours(part):
            continue
        # Older versions appended to a background job as `job & command`.
        before, amp, after = part.rpartition("& ")
        if amp and not before.endswith("&") and is_ours(after):
            part = before + "&"
        kept.append(part)
    return LEGACY_SEPARATOR.join(kept)


def hook_without(existing: str) -> str:
    """`existing` with every caelestia-spotifast command taken out, whether it
    was added on its own line or, by older versions, after `; `."""
    lines = []
    for line in existing.split("\n"):
        remaining = line_without_ours(line)
        if remaining != line and not remaining.strip():
            continue
        lines.append(remaining)
    return "\n".join(lines).rstrip()


def add_hook(path: Path, script: str) -> str:
    config = read(path)
    theme = config.setdefault("theme", {})
    if not isinstance(theme, dict):
        raise EditError(f'"theme" in {path} is not an object; leaving it unchanged')
    existing = theme.get("postHook") or ""
    if not isinstance(existing, str):
        raise EditError(f'"theme.postHook" in {path} is not a string; leaving it unchanged')
    # Also takes out a hook from an install with another --bin-dir.
    others = hook_without(existing)
    hook = hook_with(others, shlex.quote(script))
    if hook == existing:
        return "already present"
    theme["postHook"] = hook
    write(path, config, backup=True)
    if others != existing.rstrip():
        return "updated"
    return "added after the existing postHook" if existing.strip() else "added"


def remove_hook(path: Path) -> str:
    if not path.exists():
        return "no config"
    config = read(path)
    theme = config.get("theme")
    existing = theme.get("postHook") if isinstance(theme, dict) else None
    if not isinstance(existing, str):
        return "not present"
    remaining = hook_without(existing)
    if remaining == existing.rstrip():
        return "not present"
    if remaining:
        theme["postHook"] = remaining
    else:
        del theme["postHook"]
        if not theme:
            del config["theme"]
    write(path, config, backup=True)
    return "removed"


def select(path: Path, filename: str) -> str:
    # Spotifast writes a complete settings.json on its first run; a file
    # holding only the theme is never created here.
    if not path.exists():
        return "skipped (no settings.json yet; start Spotifast once)"
    settings = read(path)
    if settings.get("custom_theme") == filename:
        return "already selected"
    settings["custom_theme"] = filename
    # The cache belongs to the previous selection; Spotifast refills it.
    settings.pop("custom_theme_cache", None)
    write(path, settings, backup=True)
    return "selected"


def main(argv: list[str]) -> int:
    actions = {"add-hook": (add_hook, 4), "remove-hook": (remove_hook, 3), "select": (select, 4)}
    if len(argv) < 2 or argv[1] not in actions or len(argv) != actions[argv[1]][1]:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        print(actions[argv[1]][0](Path(argv[2]), *argv[3:]))
    except (EditError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
