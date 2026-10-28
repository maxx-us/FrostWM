import GLib from 'gi://GLib';
import St from 'gi://St';
import Cairo from 'cairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

class FrostOverlay {
    constructor() {
        this._flakes = [];
        this._last = GLib.get_monotonic_time() / 1000000;
        this._area = new St.DrawingArea({ reactive: false, can_focus: false });
        this._area.connect('repaint', area => this._paint(area));
        Main.layoutManager.addTopChrome(this._area, { affectsStruts: false, trackFullscreen: true });
        this._syncSize();
        this._sizeSignal = global.stage.connect('notify::width', () => this._syncSize());
        this._heightSignal = global.stage.connect('notify::height', () => this._syncSize());
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            const now = GLib.get_monotonic_time() / 1000000;
            const dt = Math.min(0.08, now - this._last);
            this._last = now;
            const [w, h] = global.stage.get_size();
            const count = Math.max(25, Math.min(260, Math.round(w * h / 18000)));
            while (this._flakes.length < count) this._flakes.push(this._newFlake(w, h, true));
            while (this._flakes.length > count) this._flakes.pop();
            for (const f of this._flakes) {
                f.phase += dt * 1.5;
                f.x += (f.vx + Math.sin(f.phase) * 7) * dt;
                f.y += f.vy * dt;
                if (f.y > h + 4) Object.assign(f, this._newFlake(w, h, false));
                if (f.x < -4) f.x = w + 3;
                if (f.x > w + 4) f.x = -3;
            }
            this._area.queue_repaint();
            return GLib.SOURCE_CONTINUE;
        });
    }
    _newFlake(w, h, anywhere) {
        return { x: Math.random() * Math.max(1, w), y: anywhere ? Math.random() * Math.max(1, h) : -Math.random() * 30, r: 0.7 + Math.random() * 1.8, vy: 18 + Math.random() * 54, vx: -8 + Math.random() * 16, a: 0.35 + Math.random() * 0.65, phase: Math.random() * Math.PI * 2 };
    }
    _syncSize() {
        const [w, h] = global.stage.get_size();
        this._area.set_position(0, 0);
        this._area.set_size(w, h);
    }
    _paint(area) {
        const cr = area.get_context();
        if (!cr) return;
        cr.setOperator(Cairo.Operator.CLEAR); cr.paint();
        cr.setOperator(Cairo.Operator.OVER);
        for (const f of this._flakes) {
            cr.setSourceRGBA(0.98, 0.98, 0.94, f.a);
            cr.arc(f.x, f.y, f.r, 0, Math.PI * 2); cr.fill();
        }
        cr.$dispose();
    }
    destroy() {
        if (this._timer) GLib.source_remove(this._timer);
        if (this._sizeSignal) global.stage.disconnect(this._sizeSignal);
        if (this._heightSignal) global.stage.disconnect(this._heightSignal);
        Main.layoutManager.removeChrome(this._area); this._area.destroy();
    }
}
export default class FrostWMExtension {
    enable() { this._overlay = new FrostOverlay(); }
    disable() { if (this._overlay) this._overlay.destroy(); this._overlay = null; }
}