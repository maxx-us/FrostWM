# FrostWM 0.4 — Cozy Winter

FrostWM is a transparent, click-through snow overlay for GTK3 + gtk-layer-shell + Niri.

## Defaults in 0.4

- Snowfall enabled
- Style: **Cozy Winter** (cream-white flakes, a few warm flakes, subtle amber edge glow)
- Intensity: **50%** (130 particles when max is 260)
- Wind: **25%**
- Window-edge accumulation enabled, target 4 px, hard maximum 8 px
- Interactive mouse effects enabled: flakes gently bend around the pointer and a very subtle warm halo follows it
- Window-close snow bursts enabled
- Verified input-passthrough combination retained: `Gdk.Window.set_pass_through(True)` plus an empty Cairo input region, applied after realize/map
- User service for background operation, safe stop, and journal logs

## Dependencies

On CachyOS, install if missing:

```bash
sudo pacman -S python python-gobject gtk3 python-cairo gtk-layer-shell
```

## Install

Extract the archive, open a terminal in the extracted `frostwm-0.4` directory, then:

```bash
./install.sh
```

No terminal needs to stay open. FrostWM runs as a user systemd service.

If `~/.local/bin` is not already in your zsh PATH, add this line to `~/.zshrc`:

```zsh
export PATH="$HOME/.local/bin:$PATH"
```

Then reload zsh:

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

`frostwm stop` stops the service; `frostwm off` only hides snowfall, leaving the service running for quick toggles. `frostwm enable` enables service startup but doesn't start it immediately unless `frostwm start` is run too.

To start automatically in future sessions, run:

```bash
frostwm enable
```

The CLI imports the current Niri/Wayland session variables into the systemd user manager before starting/restarting the service.

## Waybar

The installer copies the Waybar helper to `~/.config/waybar/scripts/frostwm`. Merge `waybar/config-snippet.jsonc` into your Waybar config and add `"custom/frostwm"` to the appropriate module list. Left click toggles; right click triggers a gust. If the service is stopped, clicking starts it.

## Logs and safe shutdown

```bash
frostwm logs
systemctl --user stop frostwm.service
```

The service receives SIGTERM; FrostWM handles it, closes its control socket, unmaps the overlay, and exits. systemd restarts it on unexpected crashes and records output in the journal. If anything goes wrong:

```bash
frostwm stop
```

Emergency fallback:

```bash
systemctl --user kill --signal=SIGKILL frostwm.service
```

Use SIGKILL only if normal stop fails; it skips the program's cleanup handler.

## Known limitations

- This is a prototype. The input passthrough mechanism was verified on the user's GTK3/Wayland/Niri system in a separate diagnostic program; the full v0.4 overlay still needs testing on that system.
- Niri event payload geometry can vary by version. Window-edge snow and close bursts are best-effort and need confirmation on the target session.
- The current overlay is a single-output prototype; multi-monitor-specific surfaces and per-monitor settings are not implemented.
- Interactive mouse effects read the current pointer position without receiving pointer events, preserving click-through. Pointer coordinates may not map correctly on multi-monitor layouts.
