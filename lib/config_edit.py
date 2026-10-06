#!/usr/bin/env python3
"""JSON edits for install.sh and uninstall.sh.

    config_edit.py add-hook    CLI_JSON COMMAND
    config_edit.py remove-hook CLI_JSON COMMAND
    config_edit.py select      SETTINGS_JSON FILENAME

Edits keep every other setting, write through symlinks (so a cli.json kept in
a dotfiles repository stays a link), and replace the file atomically after copying it to
<name>.caelestia-spotifast.bak. A file
that is not valid JSON is never touched.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SEPARATOR = "; "
BACKUP_SUFFIX = ".caelestia-spotifast.bak"


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
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup and target.exists():
        shutil.copy2(target, target.with_name(target.name + BACKUP_SUFFIX))
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def hook_with(existing: str, command: str) -> str:
    """`existing` with `command` run after it."""
    existing = existing.rstrip()
    while existing.endswith(";") and not existing.endswith(";;"):
        existing = existing[:-1].rstrip()
    if not existing:
        return command
    # `a &; b` is a syntax error; a background job is already terminated.
    if existing.endswith("&") and not existing.endswith("&&"):
        return f"{existing} {command}"
    return f"{existing}{SEPARATOR}{command}"


def hook_without(existing: str, command: str) -> str:
    """`existing` with the `command` that hook_with added taken out again."""
    for before in (SEPARATOR + command, " " + command):
        if existing.endswith(before):
            return existing[: -len(before)]
    if existing.strip() == command:
        return ""
    if existing.startswith(command + SEPARATOR):
        return existing[len(command + SEPARATOR) :]
    return existing.replace(SEPARATOR + command, "")


def add_hook(path: Path, command: str) -> str:
    config = read(path)
    theme = config.setdefault("theme", {})
    if not isinstance(theme, dict):
        raise EditError(f'"theme" in {path} is not an object; leaving it unchanged')
    existing = theme.get("postHook") or ""
    if not isinstance(existing, str):
        raise EditError(f'"theme.postHook" in {path} is not a string; leaving it unchanged')
    if command in existing:
        return "already present"
    theme["postHook"] = hook_with(existing, command)
    write(path, config, backup=True)
    return "added after the existing postHook" if existing.strip() else "added"


def remove_hook(path: Path, command: str) -> str:
    if not path.exists():
        return "no config"
    config = read(path)
    theme = config.get("theme")
    existing = theme.get("postHook") if isinstance(theme, dict) else None
    if not isinstance(existing, str) or command not in existing:
        return "not present"
    remaining = hook_without(existing, command).rstrip()
    if remaining:
        theme["postHook"] = remaining
    else:
        del theme["postHook"]
        if not theme:
            del config["theme"]
    write(path, config, backup=True)
    return "removed"


def select(path: Path, filename: str) -> str:
    settings = read(path)
    if settings.get("custom_theme") == filename:
        return "already selected"
    settings["custom_theme"] = filename
    # The cache belongs to the previous selection; Spotifast refills it.
    settings.pop("custom_theme_cache", None)
    write(path, settings, backup=True)
    return "selected"


def main(argv: list[str]) -> int:
    actions = {"add-hook": add_hook, "remove-hook": remove_hook, "select": select}
    if len(argv) != 4 or argv[1] not in actions:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        print(actions[argv[1]](Path(argv[2]), argv[3]))
    except (EditError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
