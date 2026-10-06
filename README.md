# caelestia-spotifast

Makes [Spotifast](https://spotifast.rocks) follow your [Caelestia](https://github.com/caelestia-dots/caelestia)
colour scheme automatically, the way Caelestia already themes Spotify through Spicetify.

Every time Caelestia's colours change (new wallpaper, `caelestia scheme set`, light/dark toggle),
a `caelestia.json` palette is written to Spotifast's themes folder. Spotifast on Linux picks it up
on its own and recolours without interrupting playback.

## How it works

| Spicetify (built into Caelestia) | Spotifast (this repo) |
| --- | --- |
| `caelestia` CLI fills `spicetify-{dark,light}.ini` | `caelestia-spotifast` builds a palette from the same colours |
| Written to `~/.config/spicetify/Themes/caelestia/color.ini` | Written to `~/.config/spotifast/themes/caelestia.json` |
| Runs inside `apply_colours()` | Runs from `theme.postHook`, right after `apply_colours()` |
| `spicetify watch -s` reloads Spotify | Spotifast watches its themes folder; `spotifast reload-themes` is also sent |
| `spicetify config current_theme caelestia` once | Choose **caelestia** in Spotifast once |

## Requirements

- The Caelestia CLI (`caelestia`) with `theme.postHook` support (current versions).
- Python 3.10+ (already needed by the Caelestia CLI). No extra packages.
- Spotifast with custom themes (Settings → Appearance has an "Open themes folder" button).
  0.10.2 or newer is recommended: from then on Linux Spotifast notices palette changes by itself.
- Only for `--systemd`: a systemd user session.

## Install

```sh
git clone https://github.com/mikkisnuyh/spotifast-caelestia-theme.git
cd spotifast-caelestia-theme
./install.sh
```

Then, once, in Spotifast: **Settings → Appearance → Theme → caelestia**.
Optionally turn off **Tint pages with album art** to keep the Caelestia colours on every page.

Options:

| Option | Effect |
| --- | --- |
| `--systemd` | Use a systemd user path unit that watches `~/.local/state/caelestia/scheme.json` instead of `theme.postHook`. Leaves `cli.json` untouched. |
| `--select` | Also select `caelestia` in Spotifast's `settings.json`. Skipped while Spotifast is running, because it would overwrite the change on exit. |
| `--bin-dir DIR` | Install the script somewhere other than `~/.local/bin`. The hook uses the full path, so it need not be on `PATH`. |

Running `install.sh` again is safe; it never adds the hook twice. Switching between the
postHook and `--systemd` removes the other trigger.

### What the installer changes

Added:

- `~/.local/bin/caelestia-spotifast`
- `~/.config/spotifast/themes/caelestia.json` (and the Flatpak equivalent under
  `~/.var/app/rocks.spotifast.Spotifast/config/spotifast/themes/` when the Flatpak is installed)
- With `--systemd`: `~/.config/systemd/user/caelestia-spotifast.{path,service}`

Edited:

- `~/.config/caelestia/cli.json`: the script is added to `theme.postHook`. An existing hook is kept
  and runs first (`<yours>; caelestia-spotifast`). All other settings are preserved; the file is
  re-indented. The previous version is saved as `cli.json.caelestia-spotifast.bak`. A symlinked
  `cli.json` (e.g. kept in a dotfiles repo) stays a symlink. Invalid JSON is never touched.
- With `--select` only: `custom_theme` in Spotifast's `settings.json` (backup saved the same way).

Nothing in Caelestia, its Spicetify theme, or Spotifast's built-in palettes is changed.

## Uninstall

```sh
./uninstall.sh            # add --bin-dir DIR if you installed with one
./uninstall.sh --keep-theme   # keep the last caelestia.json palette
```

This removes only the hook command, the units, the script and (unless `--keep-theme`) the palette.
Choose another theme in Spotifast afterwards; until then it keeps the last Caelestia colours.

## Colour mapping

Caelestia schemes are Material You palettes. They map to Spotifast's colours like this:

| Spotifast | Caelestia |
| --- | --- |
| `base` | scheme mode (`dark` / `light`) |
| `window` | `surface` |
| `panel` | `surfaceContainerLow` |
| `surface` | `surfaceContainer` |
| `surface_hover`, `overlay` | `surfaceContainerHigh` |
| `surface_active` | `surfaceContainerHighest` |
| `outline` | `outlineVariant` |
| `text` | `onSurface` |
| `secondary` | `onSurfaceVariant` |
| `dim` | `outline` |
| `accent` | `primary` |
| `accent_hover` | `primary` mixed 15% towards `onSurface` |
| `on_accent` | `onPrimary` |
| `danger` | `error` |
| `shadow` | `shadow` at Spotifast's own strength (`8c` dark, `32` light) |
| `warning` | not set: Spotifast's amber is kept, since Caelestia's named colours are shifted towards the scheme's primary |

Any colour missing from a scheme is left out, so Spotifast's base palette fills it in.

## Manual use

```sh
caelestia-spotifast            # write the palette from the current scheme
caelestia-spotifast --stdout   # print it instead
SPOTIFAST_THEMES_DIR=/some/dir caelestia-spotifast   # write somewhere else
```

Without `SCHEME_COLOURS`/`SCHEME_MODE` in the environment (which Caelestia's postHook provides),
the scheme is read from `${XDG_STATE_HOME:-~/.local/state}/caelestia/scheme.json`.

## Development

```sh
python3 -m unittest discover -s tests
```

The tests run every script against a temporary `HOME`. The fixtures in `tests/fixtures/` are the
colour values of Caelestia's Catppuccin schemes, taken from [caelestia-dots/cli](https://github.com/caelestia-dots/cli)
(`src/caelestia/data/schemes/`, GPL-3.0). The expected palettes in `tests/expected/`
come from Caelestia's Catppuccin Mocha (dark) and Latte (light) schemes and have also been
checked against Spotifast's own palette parser (`fastframe-theme`).
