#!/usr/bin/env bash
# Removes what install.sh added. Other settings and hooks are kept.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [--keep-theme] [--bin-dir DIR]

  --keep-theme    Keep the generated caelestia.json palette in Spotifast's
                  themes folder (it just stops updating).
  --bin-dir DIR   The directory given to install.sh (default: ~/.local/bin).
  -h, --help      Show this help.
EOF
}

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_home=${XDG_CONFIG_HOME:-$HOME/.config}
bin_dir=$HOME/.local/bin
keep_theme=false

while (($#)); do
    case $1 in
        --keep-theme) keep_theme=true ;;
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

bin_dir=$(realpath -m -- "$bin_dir")
script=$bin_dir/caelestia-spotifast
cli_json=$config_home/caelestia/cli.json
units_dir=$config_home/systemd/user
# shellcheck source=lib/common.sh
source "$repo/lib/common.sh"

# Removing the script while the hook still runs it would break every scheme
# change, so nothing is removed unless the hook is gone.
if ! result=$(python3 "$repo/lib/config_edit.py" remove-hook "$cli_json"); then
    echo "Nothing was removed: theme.postHook in $cli_json could not be edited (see above)." >&2
    echo "Fix the file and rerun." >&2
    exit 1
fi
[[ $result == removed ]] && say "Removed the command from theme.postHook in $cli_json"

remove_units

if [[ -e $script ]]; then
    rm -f -- "$script"
    say "Removed $script"
fi

if ! $keep_theme; then
    for themes in "$config_home/spotifast/themes" "$HOME/.var/app/rocks.spotifast.Spotifast/config/spotifast/themes"; do
        if [[ -f $themes/caelestia.json ]]; then
            rm -f -- "$themes/caelestia.json"
            say "Removed $themes/caelestia.json"
        fi
    done
    echo "If Spotifast still has caelestia selected, it keeps the last colours until you choose another theme."
fi
