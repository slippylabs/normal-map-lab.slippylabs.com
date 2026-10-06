#!/usr/bin/env python
"""The light orbit must turn at the same speed on any display.

    <a venv with playwright>/bin/python orbit_pacing_test.py

Before 2026-10-06 orbitTick did `orbitAngle += 0.012` PER FRAME, so a
revolution took 8.7 s on a 60 Hz panel and 3.6 s on a 144 Hz one -- and the
orbit checkbox is checked by default, so every visitor saw it.

The real index.html is driven in Chromium with rAF under this script's control,
and the light's position is read off `state` -- which is what drawLit() paints
from. The control reverts the pacing in flight, derived from the shipped file
so it cannot drift away from it.
"""
import http.server, functools, os, socketserver, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
PACED = "const frames = lastOrbit === null ? 1 : Math.min(8, (now - lastOrbit) / (1000 / 60));"

INIT = """
window.__q = []; window.__t = null;
window.requestAnimationFrame = (cb) => window.__q.push(cb);
window.cancelAnimationFrame = () => {};
window.__drive = (hz, frames) => {
  if (window.__t === null) window.__t = performance.now();
  for (let i = 0; i < frames; i++) {
    const due = window.__q; window.__q = [];
    for (const cb of due) cb(window.__t);
    window.__t += 1000 / hz;
  }
};
"""

def serve(body=None):
    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if body is not None and self.path.split("?")[0] in ("/", "/index.html"):
                b = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            super().do_GET()
        def log_message(self, *a): pass
    h = functools.partial(H, directory=ROOT)
    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        def handle_error(self, *a): pass
    httpd = S(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def angle_after(pg, url, hz, seconds):
    """How far round the light travelled in `seconds` of wall clock."""
    n = hz * seconds
    assert abs(n - round(n)) < 1e-9, f"{seconds}s is {n} frames at {hz} Hz -- pick a duration that divides"
    pg.goto(url, wait_until="load", timeout=60000)
    pg.wait_for_function("window.__q.length > 0", timeout=30000)
    # the orbit only moves the light once an image is loaded, which the demo does
    pg.wait_for_function("window.__nml ? true : true")
    pg.evaluate(f"window.__drive({hz}, 1)")
    a = pg.evaluate("({ x: state.lightX, y: state.lightY, on: state.orbit })")
    pg.evaluate(f"window.__drive({hz}, {round(n) - 1})")
    b = pg.evaluate("({ x: state.lightX, y: state.lightY, on: state.orbit })")
    if not a["on"]:
        return None
    import math
    # the angle swept about the image centre, which is what 'speed' means here
    c = pg.evaluate("({ w: image.width, h: image.height })")
    cx, cy = c["w"] / 2, c["h"] / 2
    a0 = math.atan2(a["y"] - cy, a["x"] - cx)
    a1 = math.atan2(b["y"] - cy, b["x"] - cx)
    d = (a1 - a0) % (2 * math.pi)
    return d


def main():
    src = open(os.path.join(ROOT, "index.html")).read()
    fails = []
    print("normal-map-lab orbit pacing")
    if PACED not in src:
        print("  FAIL the shipped index.html does not contain the paced line")
        return 1
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for label, body, want_even in (("shipped", None, True),
                                       ("control (pacing reverted)",
                                        src.replace(PACED, "const frames = 1;"), False)):
            httpd, port = serve(body)
            url = f"http://127.0.0.1:{port}/index.html"
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.add_init_script(INIT)
            got = {hz: angle_after(pg, url, hz, 0.5) for hz in (30, 60, 144)}
            pg.close()
            httpd.shutdown()
            if any(v is None for v in got.values()):
                fails.append(f"{label}: the orbit was off, so nothing was measured")
                continue
            spread = max(got.values()) / min(got.values())
            print(f"  {label:26s} " + ", ".join(f"{got[hz]:.4f} rad at {hz} Hz" for hz in (30, 60, 144))
                  + f"  (spread x{spread:.2f})")
            if want_even:
                # Asserted against the closed form, not a tolerance. The page's
                # first frame has no previous timestamp so it can only assume a
                # single 60 Hz frame, whatever the rate -- which costs the 30 Hz
                # arm one sixtieth of simulated time and gains the 144 Hz arm a
                # fraction. That is the whole of the 1.06 spread (0.336/0.348 is
                # exactly 28/29), so predict it rather than tolerate it.
                for hz in (30, 60, 144):
                    sixtieths = (round(hz * 0.5) - 1) * (60 / hz)     # after the primed frame
                    want = 0.012 * sixtieths
                    if abs(got[hz] - want) > 1e-4:
                        fails.append(f"at {hz} Hz the orbit swept {got[hz]:.5f} rad where "
                                     f"0.012 rad per 60 Hz frame predicts {want:.5f}")
                print("     each matches 0.012 rad per 60 Hz frame: "
                      + ", ".join(f"{0.012 * ((round(hz * 0.5) - 1) * (60 / hz)):.4f}"
                                  for hz in (30, 60, 144)))
            if not want_even and spread < 1.5:
                fails.append(f"the CONTROL only spread x{spread:.2f} -- this test would not have caught "
                             f"the bug, so its pass means nothing")
            for e in errs:
                fails.append(f"{label}: page error {e[:80]}")
        b.close()
    print()
    for f in fails:
        print("FAIL " + f)
    print("orbit pacing: the light turns at the same speed on any display" if not fails
          else f"orbit pacing: {len(fails)} problems")
    return 1 if fails else 0

sys.exit(main())
