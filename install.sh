#!/usr/bin/env bash
# Installs caelestia-spotifast: Spotifast follows the Caelestia colour scheme.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./install.sh [--systemd] [--select] [--bin-dir DIR]

Installs caelestia-spotifast and runs it after every Caelestia colour change,
so Spotifast's "caelestia" theme always matches your desktop.

  --systemd       Trigger through a systemd user path unit that watches
                  Caelestia's scheme.json, instead of adding a command to
                  theme.postHook in ~/.config/caelestia/cli.json.
  --select        Also select "caelestia" as Spotifast's theme (edits
                  Spotifast's settings.json; skipped while Spotifast runs
                  or before it has saved its settings once).
  --bin-dir DIR   Where to install the script (default: ~/.local/bin).
  -h, --help      Show this help.
EOF
}

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_home=${XDG_CONFIG_HOME:-$HOME/.config}
bin_dir=$HOME/.local/bin
use_systemd=false
select_theme=false
select_failed=false

while (($#)); do
    case $1 in
        --systemd) use_systemd=true ;;
        --select) select_theme=true ;;
        --bin-dir)
            [[ $# -ge 2 ]] || { echo "--bin-dir needs a directory" >&2; exit 2; }
            bin_dir=$2
            shift
            ;;
        -h | --help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    echo "Python 3.10 or newer is required (it also runs the Caelestia CLI)." >&2
    exit 1
fi

bin_dir=$(realpath -m -- "$bin_dir")
script=$bin_dir/caelestia-spotifast
cli_json=$config_home/caelestia/cli.json
units_dir=$config_home/systemd/user
edit=("python3" "$repo/lib/config_edit.py")
# shellcheck source=lib/common.sh
source "$repo/lib/common.sh"

if $use_systemd; then
    command -v systemctl >/dev/null || { echo "systemctl not found; install without --systemd." >&2; exit 1; }
    if ! systemd_path_ok "$script"; then
        echo "systemd cannot run a script whose path contains quotes, backslashes or control characters;" >&2
        echo "choose another --bin-dir or install without --systemd." >&2
        exit 1
    fi
fi

say "Installing $script"
install -Dm755 -- "$repo/caelestia-spotifast" "$script"

if $use_systemd; then
    # Only one trigger, so the palette is not written twice per change. A
    # cli.json that cannot be edited stops the install here.
    result=$("${edit[@]}" remove-hook "$cli_json")
    [[ $result == removed ]] && say "Removed the theme.postHook command from $cli_json"
    say "Installing systemd user units in $units_dir"
    mkdir -p -- "$units_dir"
    install -m644 -- "$repo/systemd/caelestia-spotifast.path" "$units_dir/"
    exec_start=$(systemd_quote "$script")
    while IFS= read -r line; do
        [[ $line == "ExecStart=@EXEC@" ]] && line="ExecStart=$exec_start"
        printf '%s\n' "$line"
    done <"$repo/systemd/caelestia-spotifast.service" >"$units_dir/caelestia-spotifast.service"
    chmod 644 -- "$units_dir/caelestia-spotifast.service"
    systemctl --user daemon-reload
    systemctl --user enable --now caelestia-spotifast.path
else
    command -v caelestia >/dev/null || warn "the caelestia command was not found; the hook runs once it is installed."
    remove_units
    result=$("${edit[@]}" add-hook "$cli_json" "$script")
    case $result in
        "already present") say "theme.postHook in $cli_json already runs caelestia-spotifast" ;;
        *) say "theme.postHook in $cli_json: $result (backup: cli.json.caelestia-spotifast.bak)" ;;
    esac
fi

say "Writing the current scheme"
if ! "$script"; then
    warn "no palette yet; it is written on the next Caelestia scheme or wallpaper change."
fi

if $select_theme; then
    if pgrep -x spotifast >/dev/null 2>&1; then
        warn "Spotifast is running, so it was not changed (it would overwrite the edit on exit)."
        warn "Choose caelestia under Settings -> Appearance -> Theme, or quit Spotifast and rerun with --select."
    else
        targets=("$config_home/spotifast/settings.json")
        flatpak=$HOME/.var/app/rocks.spotifast.Spotifast
        [[ -d $flatpak ]] && targets+=("$flatpak/config/spotifast/settings.json")
        for settings in "${targets[@]}"; do
            if result=$("${edit[@]}" select "$settings" caelestia.json); then
                say "Spotifast theme in $settings: $result"
            else
                select_failed=true
            fi
        done
    fi
fi

cat <<EOF

Done. Spotifast now gets a "caelestia" palette whenever Caelestia's colours change.
EOF
$select_theme || echo 'Select it once in Spotifast under Settings -> Appearance -> Theme -> caelestia.'
echo 'Tip: turn off "Tint pages with album art" there to keep the Caelestia colours on every page.'
if $select_failed; then
    warn "the theme could not be selected in every settings.json (see above); choose caelestia in Spotifast instead."
    exit 1
fi
