# Shared by install.sh and uninstall.sh. Expects $units_dir to be set.

say() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

# Stops and removes the systemd user units, if they are installed.
remove_units() {
    local unit_path=$units_dir/caelestia-spotifast.path
    [[ -e $unit_path ]] || return 0
    if command -v systemctl >/dev/null; then
        systemctl --user disable --now caelestia-spotifast.path >/dev/null 2>&1 || true
    fi
    rm -f -- "$unit_path" "$units_dir/caelestia-spotifast.service"
    if command -v systemctl >/dev/null; then
        systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi
    say "Removed the systemd path unit"
}

# $1 as the executable of a systemd Exec*= line: double-quoted so spaces stay
# in the path, with `%` (specifiers) escaped. systemd expands `$` variables
# only in arguments, and rejects quotes, backslashes and control characters
# in an executable however they are escaped; systemd_path_ok checks for those.
systemd_quote() {
    printf '"%s"' "${1//%/%%}"
}

systemd_path_ok() {
    [[ $1 != *[\\\"\']* && $1 != *[[:cntrl:]]* ]]
}
