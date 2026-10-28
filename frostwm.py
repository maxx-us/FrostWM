#!/usr/bin/env python3
"""FrostWM 0.9 — cozy winter snow overlay for GTK3 + gtk-layer-shell Wayland compositors."""
import json
import math
import os
import random
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
import cairo

CFG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "frostwm/config.json"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
DEFAULTS = {
    "enabled": True,
    "style": "Cozy Winter",
    "preset": "custom",
    "intensity": 50,
    "wind_strength": 25,
    "fps": 60,
    "max_particles": 260,
    "min_speed": 18.0,
    "max_speed": 72.0,
    "flake_min_radius": 0.7,
    "flake_max_radius": 2.5,
    "opacity": 0.82,
    "close_burst": True,
    "window_ledges": True,
    "ledge_target_depth": 4,
    "ledge_max_depth": 8,
    "mouse_effects": True,
    "socket": str(RUNTIME_DIR / "frostwm.sock"),
}

# Presets are starting points: all existing individual controls remain available.
PRESETS = {
    "gentle": {
        "style": "Gentle Snow", "intensity": 22, "wind_strength": 8,
        "fps": 45, "max_particles": 220, "min_speed": 10.0,
        "max_speed": 34.0, "flake_min_radius": 0.6,
        "flake_max_radius": 1.8, "opacity": 0.62,
        "close_burst": False, "window_ledges": False, "mouse_effects": False,
    },
    "cozy": {
        "style": "Cozy Winter", "intensity": 35, "wind_strength": 25,
        "fps": 60, "max_particles": 260, "min_speed": 18.0,
        "max_speed": 72.0, "flake_min_radius": 0.7,
        "flake_max_radius": 2.5, "opacity": 0.82,
        "close_burst": True, "window_ledges": True, "mouse_effects": True,
    },
    "blizzard": {
        "style": "Blizzard", "intensity": 90, "wind_strength": 78,
        "fps": 60, "max_particles": 420, "min_speed": 38.0,
        "max_speed": 125.0, "flake_min_radius": 0.9,
        "flake_max_radius": 3.0, "opacity": 0.94,
        "close_burst": True, "window_ledges": True, "mouse_effects": True,
    },
}

def load_config():
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULTS.copy()
    try:
        user_cfg = json.loads(CFG_PATH.read_text())
        if isinstance(user_cfg, dict):
            cfg.update(user_cfg)
    except FileNotFoundError:
        CFG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    except Exception as exc:
        print(f"FrostWM: config read error: {exc}", flush=True)
    cfg["intensity"] = max(0, min(100, int(cfg.get("intensity", 50))))
    cfg["wind_strength"] = max(0, min(100, int(cfg.get("wind_strength", 25))))
    cfg["max_particles"] = max(1, min(1000, int(cfg.get("max_particles", 260))))
    cfg["particles"] = round(cfg["max_particles"] * cfg["intensity"] / 100)
    cfg["fps"] = max(10, min(120, int(cfg.get("fps", 60))))
    cfg["ledge_target_depth"] = max(1, min(8, int(cfg.get("ledge_target_depth", 4))))
    cfg["ledge_max_depth"] = max(cfg["ledge_target_depth"], min(8, int(cfg.get("ledge_max_depth", 8))))
    cfg["socket"] = str(RUNTIME_DIR / "frostwm.sock")
    return cfg

class Flake:
    __slots__ = ("x", "y", "r", "vy", "vx", "phase", "alpha", "warm")
    def __init__(self, w, h, cfg, anywhere=False):
        self.x = random.uniform(0, max(1, w))
        self.y = random.uniform(0, max(1, h)) if anywhere else random.uniform(-h * .15, 0)
        self.r = random.uniform(cfg["flake_min_radius"], cfg["flake_max_radius"])
        self.vy = random.uniform(cfg["min_speed"], cfg["max_speed"])
        self.vx = random.uniform(-8, 8)
        self.phase = random.random() * math.tau
        self.alpha = random.uniform(.35, 1.0)
        self.warm = random.random() < .10

class FrostWM(Gtk.Window):
    def __init__(self):
        super().__init__(title="FrostWM")
        self.cfg = load_config()
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_app_paintable(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_namespace(self, "frostwm")
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(self, -1)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)

        self.flakes = []
        self.width, self.height = 1, 1
        self.last = time.monotonic()
        self.wind = self.cfg["wind_strength"] * .40  # up to 40 logical px/s
        self.gust = 0.0
        self.enabled = bool(self.cfg["enabled"])
        self.windows = {}
        self.bursts = []
        self._cmd_server = None
        self._socket_path = Path(self.cfg["socket"])
        self._stopping = False
        # Ambient snow wakes mimic pointer disturbance without global cursor access.
        self.ambient_wakes = []
        self.ambient_next = random.uniform(1.2, 2.8)

        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("map-event", self.on_map)
        self._fill_particles()
        self._start_ipc()
        self.tick_source = GLib.timeout_add(max(1, int(1000 / self.cfg["fps"])), self.tick)
        GLib.timeout_add(180, self.poll_commands)
        signal.signal(signal.SIGTERM, self._signal_stop)
        signal.signal(signal.SIGINT, self._signal_stop)

    def _signal_stop(self, *_):
        GLib.idle_add(self.stop_cleanly)

    def stop_cleanly(self):
        if self._stopping:
            return GLib.SOURCE_REMOVE
        self._stopping = True
        try:
            if self._cmd_server:
                self._cmd_server.close()
                self._cmd_server = None
        except Exception:
            pass
        try:
            self._socket_path.unlink(missing_ok=True)
        except Exception:
            pass
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    def _set_passthrough(self, *_):
        # Verified by the user on their GTK3/GdkWayland/Niri setup.
        gw = self.get_window()
        if not gw:
            return
        try:
            gw.set_pass_through(True)
        except Exception as exc:
            print(f"FrostWM: set_pass_through failed: {exc}", flush=True)
        try:
            gw.input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception as exc:
            print(f"FrostWM: empty input region failed: {exc}", flush=True)

    def on_realize(self, *_):
        self._set_passthrough()
        GLib.idle_add(self._set_passthrough)

    def on_map(self, *_):
        self._set_passthrough()
        GLib.idle_add(self._set_passthrough)
        return False

    def _fill_particles(self, reseed=False):
        count = self.cfg["particles"] if self.enabled else 0
        if reseed:
            # GTK can briefly report a 1x1 allocation on startup. Rebuild all
            # particles after the real overlay dimensions are known.
            self.flakes = [
                Flake(self.width, self.height, self.cfg, anywhere=True)
                for _ in range(count)
            ]
            return
        while len(self.flakes) < count:
            self.flakes.append(Flake(self.width, self.height, self.cfg, anywhere=True))
        self.flakes = self.flakes[:count]

    def _start_ipc(self):
        threading.Thread(target=self._ipc_worker, daemon=True, name="frostwm-niri-ipc").start()

    def _ipc_worker(self):
        while not self._stopping:
            if not os.environ.get("NIRI_SOCKET"):
                time.sleep(2)
                continue
            proc = None
            try:
                proc = subprocess.Popen(
                    ["niri", "msg", "--json", "event-stream"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    if self._stopping:
                        break
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    GLib.idle_add(self.handle_niri_event, event)
            except Exception as exc:
                print(f"FrostWM: Niri IPC reconnect: {exc}", flush=True)
            finally:
                if proc and proc.poll() is None:
                    proc.terminate()
            time.sleep(2)

    @staticmethod
    def _window_rect(win):
        """Return visible tile geometry from Niri's Window or WindowLayout JSON."""
        if not isinstance(win, dict):
            return {}
        for source in (win, win.get("layout"), win.get("window_layout")):
            if not isinstance(source, dict):
                continue
            if all(k in source for k in ("x", "y", "width", "height")):
                try:
                    return {k: float(source[k]) for k in ("x", "y", "width", "height")}
                except (TypeError, ValueError):
                    pass

        layout = win.get("layout", win)
        if not isinstance(layout, dict):
            return {}
        pos = layout.get("tile_pos_in_workspace_view")
        size = layout.get("tile_size")
        # Niri's visual coordinates are these pairs. pos_in_scrolling_layout is
        # only a column/row index and must never be treated as screen coordinates.
        if (isinstance(pos, (list, tuple)) and len(pos) == 2
                and isinstance(size, (list, tuple)) and len(size) == 2
                and pos[0] is not None and pos[1] is not None):
            try:
                return {
                    "x": float(pos[0]), "y": float(pos[1]),
                    "width": float(size[0]), "height": float(size[1]),
                }
            except (TypeError, ValueError):
                return {}
        return {}

    def _remember_window(self, wid, win, layout_override=None):
        if not wid or not isinstance(win, dict):
            return
        wid = str(wid)
        old = self.windows.get(wid, {})
        candidate = dict(win)
        if layout_override is not None:
            candidate["layout"] = layout_override
        rect = self._window_rect(candidate)
        if not rect:
            return
        self.windows[wid] = {
            **rect,
            "depth": old.get("depth", 1.5),
            "title": win.get("title", old.get("title", "")),
            "workspace_id": win.get("workspace_id", old.get("workspace_id")),
        }

    def _close_burst(self, rect):
        if not self.cfg.get("close_burst", True):
            return
        # Start at the TOP edge of the closing window, not its centre.
        try:
            x = float(rect["x"]) + float(rect["width"]) / 2
            y = float(rect["y"])
        except (KeyError, TypeError, ValueError):
            # No valid position: skip the burst instead of spawning at desktop centre.
            return
        self.bursts.append({"x": x, "y": y, "n": 22, "age": 0.0})

    def handle_niri_event(self, event):
        if not isinstance(event, dict):
            return GLib.SOURCE_REMOVE
        name, payload = next(iter(event.items()), ("", {}))
        key = str(name).lower().replace("_", "")
        data = payload if isinstance(payload, dict) else {}

        # The event stream starts with WindowsChanged containing a full snapshot.
        # Later snapshots also let us reliably detect which windows have closed.
        if key == "windowschanged":
            incoming = data.get("windows", [])
            fresh = {}
            if isinstance(incoming, list):
                for win in incoming:
                    if not isinstance(win, dict):
                        continue
                    wid = str(win.get("id", ""))
                    if not wid:
                        continue
                    previous = self.windows.get(wid, {})
                    rect = self._window_rect(win)
                    if rect:
                        fresh[wid] = {
                            **rect,
                            "depth": previous.get("depth", 1.0),
                            "title": win.get("title", previous.get("title", "")),
                            "workspace_id": win.get("workspace_id", previous.get("workspace_id")),
                        }
                    elif previous:
                        fresh[wid] = previous
            for wid, old_window in list(self.windows.items()):
                if wid not in fresh:
                    self._close_burst(old_window)
            self.windows = fresh
            return GLib.SOURCE_REMOVE

        # Niri calls this WindowLayoutsChanged (plural), with [id, layout] pairs.
        if key == "windowlayoutschanged":
            for item in data.get("changes", []):
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                wid, layout = str(item[0]), item[1]
                old_window = self.windows.get(wid, {})
                if isinstance(layout, dict):
                    self._remember_window(wid, {
                        "id": wid, "title": old_window.get("title", ""),
                        "workspace_id": old_window.get("workspace_id"),
                    }, layout_override=layout)
            return GLib.SOURCE_REMOVE

        # Metadata updates may carry a full window object with geometry nested in layout.
        if "windowopenedorchanged" in key or "windowopened" in key or "windowchanged" in key:
            win = data.get("window", data)
            if isinstance(win, dict):
                self._remember_window(str(win.get("id", data.get("id", ""))), win)
            return GLib.SOURCE_REMOVE

        # Compatibility with variants that explicitly emit a close event.
        if "windowclosed" in key or "windowremoved" in key:
            win = data.get("window", data)
            wid = str(win.get("id", data.get("id", ""))) if isinstance(win, dict) else ""
            old_window = self.windows.pop(wid, None)
            self._close_burst(self._window_rect(win) or old_window or {})
        return GLib.SOURCE_REMOVE

    def poll_commands(self):
        if self._stopping:
            return GLib.SOURCE_REMOVE
        try:
            if self._cmd_server is None:
                self._socket_path.parent.mkdir(parents=True, exist_ok=True)
                self._socket_path.unlink(missing_ok=True)
                self._cmd_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._cmd_server.bind(str(self._socket_path))
                os.chmod(self._socket_path, 0o600)
                self._cmd_server.listen(8)
                self._cmd_server.setblocking(False)
            try:
                conn, _ = self._cmd_server.accept()
            except BlockingIOError:
                conn = None
            if conn is not None:
                with conn:
                    conn.settimeout(.2)
                    cmd = conn.recv(1024).decode(errors="ignore").strip()
                    reply = self.handle_command(cmd)
                    if reply:
                        conn.sendall(reply.encode())
        except Exception as exc:
            print(f"FrostWM: control socket: {exc}", flush=True)
        return GLib.SOURCE_CONTINUE

    def _set_fps(self, fps):
        """Apply a new GTK animation tick interval immediately."""
        fps = max(10, min(120, int(fps)))
        old_source = getattr(self, "tick_source", None)
        if old_source:
            try:
                GLib.source_remove(old_source)
            except GLib.Error:
                pass
        self.cfg["fps"] = fps
        self.last = time.monotonic()
        self.tick_source = GLib.timeout_add(max(1, round(1000 / fps)), self.tick)
        self.queue_draw()
        return fps

    def handle_command(self, cmd):
        if cmd == "toggle":
            self.enabled = not self.enabled
            self.cfg["enabled"] = self.enabled
            self._fill_particles()
            self.save_config()
            return "on" if self.enabled else "off"
        if cmd in ("on", "enable", "start-effect"):
            self.enabled = True
            self.cfg["enabled"] = True
            self._fill_particles()
            self.save_config()
            return "on"
        if cmd in ("off", "disable", "stop-effect"):
            self.enabled = False
            self.cfg["enabled"] = False
            self._fill_particles()
            self.save_config()
            return "off"
        if cmd == "gust":
            self.gust = random.choice([-1, 1]) * random.uniform(35, 90)
            return "ok"
        if cmd.startswith("preset "):
            parts = cmd.split()
            if len(parts) != 2 or parts[1].lower() not in PRESETS:
                return "error: choose gentle, cozy, or blizzard"
            name = parts[1].lower()
            self.cfg.update(PRESETS[name])
            self.cfg["preset"] = name
            self.cfg["particles"] = round(
                self.cfg["max_particles"] * self.cfg["intensity"] / 100
            )
            self.enabled = bool(self.cfg.get("enabled", True))
            self.wind = self.cfg["wind_strength"] * .40
            self.gust = 0.0
            self._fill_particles(reseed=True)
            self._set_fps(self.cfg["fps"])
            self.save_config()
            return f"{name}: intensity={self.cfg['intensity']} wind={self.cfg['wind_strength']} fps={self.cfg['fps']} (target FPS)";
        if cmd.startswith("density "):
            try:
                self.cfg["intensity"] = max(0, min(100, int(cmd.split()[1])))
                self.cfg["preset"] = "custom"
                self.cfg["particles"] = round(self.cfg["max_particles"] * self.cfg["intensity"] / 100)
                self._fill_particles()
                self.save_config()
                return str(self.cfg["intensity"])
            except (ValueError, IndexError):
                return "error"
        if cmd.startswith("wind "):
            try:
                self.cfg["wind_strength"] = max(0, min(100, int(cmd.split()[1])))
                self.cfg["preset"] = "custom"
                self.wind = self.cfg["wind_strength"] * .40
                self.save_config()
                return str(self.cfg["wind_strength"])
            except (ValueError, IndexError):
                return "error"
        if cmd.startswith("fps "):
            parts = cmd.split()
            try:
                if len(parts) != 2:
                    return "error: usage is fps 10..120"
                requested = int(parts[1])
                if not 10 <= requested <= 120:
                    return "error: FPS must be between 10 and 120"
                fps = self._set_fps(requested)
                self.cfg["preset"] = "custom"
                self.save_config()
                return f"target FPS set to {fps}"
            except ValueError:
                return "error: FPS must be an integer between 10 and 120"
        if cmd == "status":
            return json.dumps({
                "enabled": self.enabled, "style": self.cfg["style"],
                "preset": self.cfg.get("preset", "custom"),
                "fps": self.cfg["fps"],
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "unknown",
                "window_tracking": bool(os.environ.get("NIRI_SOCKET")),
                "intensity": self.cfg["intensity"], "wind": self.cfg["wind_strength"],
                "mouse_effects": self.cfg["mouse_effects"],
                "mouse_tracking": False,
                "ambient_effects": bool(self.cfg.get("mouse_effects", True)),
                "ambient_wakes": len(self.ambient_wakes),
                "surface_size": [self.width, self.height],
                "particles": len(self.flakes),
                "window_ledges": bool(self.cfg["window_ledges"] and os.environ.get("NIRI_SOCKET")),
            })
        if cmd == "clear":
            self.windows.clear()
            self.bursts.clear()
            return "ok"
        if cmd == "quit":
            GLib.idle_add(self.stop_cleanly)
            return "stopping"
        return "unknown command"

    def save_config(self):
        try:
            CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CFG_PATH.write_text(json.dumps(self.cfg, indent=2) + "\n")
        except Exception as exc:
            print(f"FrostWM: couldn't save config: {exc}", flush=True)

    def _update_ambient_effects(self, dt):
        """Create brief, localized snow swirls without reading pointer/input devices."""
        if not self.cfg.get("mouse_effects", True):
            self.ambient_wakes.clear()
            return

        self.ambient_next -= dt
        if self.ambient_next <= 0:
            if random.random() < 0.72:
                x = random.uniform(self.width * 0.18, self.width * 0.82)
                y = random.uniform(self.height * 0.18, self.height * 0.82)
            else:
                x = random.uniform(0, self.width)
                y = random.uniform(0, self.height)
            self.ambient_wakes.append({
                "x": x, "y": y,
                "radius": random.uniform(75, 145),
                "age": 0.0,
                "duration": random.uniform(1.8, 3.0),
                "strength": random.uniform(22, 48),
                "spin": random.choice((-1, 1)),
            })
            self.ambient_next = random.uniform(2.8, 5.8) * (1.15 - self.cfg["wind_strength"] / 250)
            if random.random() < 0.22 + self.cfg["wind_strength"] / 250:
                self.gust += random.choice((-1, 1)) * random.uniform(12, 38)

        for wake in self.ambient_wakes:
            wake["age"] += dt
        self.ambient_wakes = [w for w in self.ambient_wakes if w["age"] < w["duration"]]

    def _apply_ambient_wakes(self, flake, dt):
        for wake in self.ambient_wakes:
            dx, dy = flake.x - wake["x"], flake.y - wake["y"]
            distance = math.hypot(dx, dy)
            radius = wake["radius"]
            if distance < 1 or distance >= radius:
                continue
            life = max(0.0, 1.0 - wake["age"] / wake["duration"])
            proximity = 1.0 - distance / radius
            force = wake["strength"] * proximity * life * dt
            # A soft outward nudge plus a tangential swirl, like a pointer wake.
            flake.x += (dx / distance) * force + (-dy / distance) * force * 0.72 * wake["spin"]
            flake.y += (dy / distance) * force + (dx / distance) * force * 0.48 * wake["spin"]

    def tick(self):
        if self._stopping:
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        dt = min(.08, now - self.last)
        self.last = now
        alloc = self.get_allocation()
        w, h = max(1, alloc.width), max(1, alloc.height)
        if w > 1 and h > 1 and (w, h) != (self.width, self.height):
            oldw, oldh = self.width, self.height
            self.width, self.height = w, h
            if oldw > 1 and oldh > 1:
                sx, sy = w / oldw, h / oldh
                for f in self.flakes:
                    f.x *= sx
                    f.y *= sy
            else:
                # Previously flakes were initialized against a 1x1 surface,
                # which piled them all into the upper-left corner.
                self._fill_particles(reseed=True)
        elif w <= 1 or h <= 1:
            # Wait for gtk-layer-shell to allocate the fullscreen surface.
            self.queue_draw()
            return GLib.SOURCE_CONTINUE
        if self.enabled:
            self._update_ambient_effects(dt)
            self._fill_particles()
            self.gust *= max(0, 1 - dt * .55)
            for f in self.flakes:
                f.phase += dt * 1.7
                wind_noise = math.sin(f.phase) * 5
                f.x += (f.vx + self.wind + self.gust + wind_noise) * dt
                f.y += f.vy * dt
                # Ambient swirls create mouse-like snow motion without pointer access.
                if self.cfg.get("mouse_effects", True):
                    self._apply_ambient_wakes(f, dt)
                if f.y > self.height + 5:
                    f.y = random.uniform(-30, -2)
                    f.x = random.uniform(0, self.width)
                if f.x < -5:
                    f.x = self.width + 4
                elif f.x > self.width + 5:
                    f.x = -4
            for b in self.bursts:
                b["age"] += dt
                b["n"] = max(0, b["n"] - dt * 12)
            self.bursts = [b for b in self.bursts if b["age"] < 1.8 and b["n"] > 0]
            if self.cfg.get("window_ledges", True):
                for win in self.windows.values():
                    win["depth"] = min(float(self.cfg["ledge_target_depth"]), float(win.get("depth", 1.5)) + dt * .35)
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if not self.enabled:
            return False

        cozy = str(self.cfg.get("style", "Cozy Winter")).lower() == "cozy winter"
        # Subtle, warm bokeh at the very edges; transparent elsewhere.
        if cozy:
            for i, (x, y, radius, alpha) in enumerate((
                (self.width * .06, self.height * .08, 90, .025),
                (self.width * .93, self.height * .13, 115, .022),
                (self.width * .12, self.height * .92, 100, .018),
            )):
                pat = cairo.RadialGradient(x, y, 0, x, y, radius)
                pat.add_color_stop_rgba(0, .98, .69, .38, alpha)
                pat.add_color_stop_rgba(1, .98, .69, .38, 0)
                cr.set_source(pat)
                cr.paint()

        for f in self.flakes:
            if cozy and f.warm:
                cr.set_source_rgba(1.0, .88, .70, self.cfg["opacity"] * f.alpha)
            else:
                cr.set_source_rgba(.98, .98, .94 if cozy else 1.0, self.cfg["opacity"] * f.alpha)
            cr.arc(f.x, f.y, f.r, 0, math.tau)
            cr.fill()
            if f.r > 1.8:
                cr.set_source_rgba(1, 1, 1, .28)
                cr.set_line_width(.6)
                cr.move_to(f.x - f.r * 2, f.y)
                cr.line_to(f.x + f.r * 2, f.y)
                cr.stroke()

        # Very soft ambient glows accompany temporary snow swirls.
        if self.cfg.get("mouse_effects", True):
            for wake in self.ambient_wakes:
                life = max(0.0, 1.0 - wake["age"] / wake["duration"])
                radius = wake["radius"] * (0.55 + 0.45 * (1.0 - life))
                halo = cairo.RadialGradient(wake["x"], wake["y"], 2, wake["x"], wake["y"], radius)
                halo.add_color_stop_rgba(0, 1.0, .86, .66, (.055 if cozy else .025) * life)
                halo.add_color_stop_rgba(1, 1.0, .86, .66, 0)
                cr.set_source(halo)
                cr.paint()

        for b in self.bursts:
            t = b["age"]
            for i in range(min(int(b["n"]), 30)):
                x = b["x"] + math.sin(i * 12.989) * i * 1.1
                y = b["y"] + t * 65 + (i % 7) * t * 15
                cr.set_source_rgba(1.0, .92, .78, max(0, 1 - t / 1.8))
                cr.arc(x, y, .7 + (i % 3) * .4, 0, math.tau)
                cr.fill()

        # Accumulation along reported top edges; depth grows gently to the configured target.
        if self.cfg.get("window_ledges", True):
            for win in self.windows.values():
                try:
                    x, y, width = float(win["x"]), float(win["y"]), float(win["width"])
                    depth = max(1.0, min(float(self.cfg["ledge_max_depth"]), float(win.get("depth", 1))))
                    if width > 20 and -8 < y < self.height:
                        cr.set_source_rgba(1.0, .96, .87, .88)
                        cr.set_line_width(depth)
                        cr.move_to(x, y + depth / 2)
                        cr.line_to(x + width, y + depth / 2)
                        cr.stroke()
                        # tiny rounded snow mounds
                        cr.set_source_rgba(1, .99, .94, .92)
                        for j in range(max(1, int(width // 70))):
                            mx = x + (j + .5) * width / max(1, int(width // 70))
                            cr.arc(mx, y, depth * .6, math.pi, math.tau)
                            cr.fill()
                except (KeyError, TypeError, ValueError):
                    continue
        return False

def main():
    app = FrostWM()
    app.show_all()
    app._set_passthrough()
    Gtk.main()
    app.stop_cleanly()

if __name__ == "__main__":
    main()
