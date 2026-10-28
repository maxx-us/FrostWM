# FrostWM 0.5 — Cozy Winter

FrostWM is a transparent, click-through snowfall overlay for GTK3, gtk-layer-shell, and Niri. Bring a cozy winter atmosphere to your desktop with animated snow, interactive mouse effects, and snow accumulation along window edges.

## ✨ Features and defaults

- Snowfall enabled
- Style: **Cozy Winter** — cream-white flakes, a few warm flakes, and subtle amber edge glow
- Intensity: **50%** (130 particles when the maximum is 260)
- Wind: **25%**
- Window-edge accumulation enabled, with a 4 px target and 8 px hard maximum
- Interactive mouse effects: flakes gently bend around the pointer, with a subtle warm halo
- Window-close snow bursts enabled
- Click-through input handling using `Gdk.Window.set_pass_through(True)` and an empty Cairo input region, applied after realize/map
- User systemd service for background operation, safe shutdown, and journal logs

## 🚀 Quick install — one command

On CachyOS or another compatible Linux system, open a terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/maxx-us/FrostWM/main/install-remote.sh -o /tmp/frostwm-install.sh && bash /tmp/frostwm-install.sh; result=$?; rm -f /tmp/frostwm-install.sh; exit "$result"
```

This downloads and runs the remote installer, which fetches the latest source from the repository and runs `install.sh`.

**Requirements:** `curl` or `wget`, `tar`, Python 3, GTK3, PyGObject, PyCairo, and gtk-layer-shell. The remote installer does not use `sudo`; install missing system dependencies separately.

> **Security note:** This downloads and executes the installer from the repository's `main` branch. Review [`install-remote.sh`](https://github.com/maxx-us/FrostWM/blob/main/install-remote.sh) and [`install.sh`](https://github.com/maxx-us/FrostWM/blob/main/install.sh) before running it if you want to inspect what will be executed.

## Fixes in 0.5

- Read Niri’s actual visual tile coordinates and sizes instead of assuming x/y/width/height fields.
- Track the initial `WindowsChanged` snapshot and plural `WindowLayoutsChanged` updates so visible window ledges can be drawn.
- Detect closed windows from Niri’s replacement window snapshots.
- Spawn the falling-snow burst from the closing window’s top edge; if no valid position is known, skip the burst instead of incorrectly using the desktop centre.

After updating, rerun the one-command installer above, then run `frostwm restart` to restart the running overlay.

## Dependencies

On CachyOS, install any missing dependencies with:

```bash
sudo pacman -S python python-gobject gtk3 python-cairo gtk-layer-shell
```

## Manual installation

If you downloaded the source archive manually, extract it, open a terminal in the extracted `FrostWM-main` directory, and run:

```bash
./install.sh
```

No terminal needs to stay open. FrostWM runs as a user systemd service.

If `~/.local/bin` is not already in your Zsh PATH, add this line to `~/.zshrc`:

```zsh
export PATH="$HOME/.local/bin:$PATH"
```

Then reload Zsh:

```zsh
source ~/.zshrc
```

## Commands

```bash
frostwm start           # Start overlay
frostwm stop            # Safely stop and remove overlay
frostwm toggle          # Toggle snow while leaving service running
frostwm on              # Enable snowfall
frostwm off             # Disable snowfall
frostwm status          # Print JSON status
frostwm gust            # Trigger a gust
frostwm intensity 0     # Turn snowfall density to zero
frostwm intensity 50    # 50% density
frostwm intensity 100   # Full density
frostwm wind 25         # Wind strength, 0..100
frostwm enable          # Start service automatically at login
frostwm disable-startup # Disable automatic login start
frostwm restart         # Restart service
frostwm logs            # Show recent service logs
```

`frostwm stop` stops the service; `frostwm off` only hides snowfall, leaving the service running for quick toggles.

To start FrostWM automatically in future sessions, run:

```bash
frostwm enable
```

The CLI imports the current Niri/Wayland session variables into the systemd user manager before starting or restarting the service.

## Waybar

The installer copies the Waybar helper to `~/.config/waybar/scripts/frostwm`.

To enable it:

1. Merge `
