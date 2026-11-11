#!/usr/bin/env python3
"""ai_particles.py - the AI's on-screen presence: a 3D sphere of gold light points that turns slowly and
swells with the AI's voice, with dust drifting around it. The approved AI look (ep03, 2026-11-11).

    python3 ai_particles.py ai_voice.wav out.mp4               # the whole file, AI talking throughout
    python3 ai_particles.py ai_voice.wav out.mp4 --motion 0.75 # calmer; 1.5 livelier

From a build:  ai_particles.render(ai_only_wav, segments, total_seconds, out_mp4)
  segments = [(start, end), ...] in seconds - frames outside them are black, because the build only
  shows this layer while the AI talks. Output is 1000x1360 at 30 fps, the stage size of the Shorts layout.

The motion is set once, here: MOTION = 1.0 is the approved level. It sits at about 40% of the first
version, which jumped on every syllable and was too aggressive; 0.5 was too still. What keeps it a
sphere: the voice levels are smoothed over ~0.2 s, neighbouring bands move together, and the push is a
few percent of the radius. What makes it 3D: perspective (camera at 3 radii), and depth picks each
point's size and brightness - near points large and bright, far ones small and dim.

Rendered at half size and upscaled; the glow is a blurred copy of the points added back on top.
Needs numpy, Pillow and ffmpeg.
"""
import subprocess, sys, wave
import numpy as np
from PIL import Image, ImageFilter

W, H, FPS = 500, 680, 30
NBANDS = 64
def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return sr, a

def band_levels(a, sr, frames):
    """Per-frame log-spaced band levels (0..1) and loudness, with fast attack / slow release."""
    hop, win = sr / FPS, 2048
    edges = np.geomspace(90, 7000, NBANDS + 1)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    idx = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges, edges[1:])]
    hann = np.hanning(win).astype(np.float32)
    tilt = np.linspace(0, 16, NBANDS, dtype=np.float32)   # lift the quieter highs so the whole ring moves
    bands, rms = np.zeros((frames, NBANDS), np.float32), np.zeros(frames, np.float32)
    prev_b, prev_r = np.zeros(NBANDS, np.float32), 0.0
    for f in range(frames):
        c = int(f * hop)
        seg = a[max(0, c - win // 2): c + win // 2]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        mag = np.abs(np.fft.rfft(seg * hann))
        b = np.array([mag[i].mean() if len(i) else 0 for i in idx], np.float32)
        b = np.clip((20 * np.log10(b + 1e-6) + 10 + tilt) / 45, 0, 1)
        r = float(np.clip((20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-6) + 45) / 35, 0, 1))
        prev_b = np.maximum(b, prev_b * 0.82)
        prev_r = max(r, prev_r * 0.88)
        bands[f], rms[f] = prev_b, prev_r
    return bands, rms

CX, CY, R0 = W / 2, H * 0.44, 118
GOLD, WHITE, CYAN = np.array([255, 196, 92.]), np.array([255, 246, 228.]), np.array([120, 220, 255.])
rng = np.random.default_rng(3)
CAM = 3.0                                     # camera distance in sphere radii: closer = stronger perspective
MOTION = 1.0                                  # how much the sphere moves with the voice (0 = still)
# soft round dots in three sizes, picked by depth: far points small, near points large
def _dot(r):
    n = int(np.ceil(r)) + 1
    return [(dx, dy, float(np.exp(-(dx * dx + dy * dy) / (r * r * 0.6)))) for dx in range(-n, n + 1)
            for dy in range(-n, n + 1) if dx * dx + dy * dy <= (r + 0.5) ** 2]
DOTS = [_dot(1.2), _dot(2.0), _dot(2.9)]

def dots(buf, x, y, w, kernel):
    for dx, dy, k in kernel:
        np.add.at(buf, (y + dy, x + dx), w * k)

def smooth(v, a):
    """Exponential smoothing along time (axis 0): a small a is slow and calm."""
    out = np.empty_like(v); acc = v[0]
    for i in range(len(v)):
        acc = acc + a * (v[i] - acc); out[i] = acc
    return out

# sphere: Fibonacci points, so they are spread evenly
NS = 900                                      # fewer, brighter points read as a shape, not a haze
k = np.arange(NS) + 0.5
phi = np.arccos(1 - 2 * k / NS)                               # 0 at the top, pi at the bottom
theta = np.pi * (1 + 5 ** 0.5) * k
SPH = np.stack([np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)], 1)
# each point listens to one band: lows at the equator, highs at the poles, so speech ripples outward
BAND = np.clip((np.abs(np.cos(phi)) * (NBANDS - 1)).astype(int), 0, NBANDS - 1)
JIT = rng.uniform(0, 2 * np.pi, NS)
# dust: points on random shells further out, drifting outward and wrapping
ND = 300
DUST_DIR = rng.standard_normal((ND, 3)); DUST_DIR /= np.linalg.norm(DUST_DIR, axis=1, keepdims=True)
DUST_R0 = rng.uniform(1.3, 3.2, ND)
DUST_SPD = rng.uniform(0.04, 0.12, ND)

def rot(t):
    a, b = t * 0.26, 0.42 + 0.06 * np.sin(t * 0.25)         # a steady spin, tilted towards the camera
    ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    return rx @ ry

def render(ai_wav, segments, total, out):
    sr, a = read_wav(ai_wav)
    frames = int(round(total * FPS))
    bands, rms = band_levels(a, sr, frames)
    bands, rms = smooth(bands, 0.20), smooth(rms, 0.16)      # ~0.2 s to follow the voice: lively, no jitter
    bands = (bands + np.roll(bands, 1, 1) + np.roll(bands, -1, 1)) / 3   # neighbours move together
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rho = np.hypot(xx - CX, yy - CY)
    bg = np.array([12, 10, 14], np.float32) + np.exp(-(rho / 300) ** 2)[..., None] * np.array([46, 30, 12], np.float32)
    black = np.zeros((H, W, 3), np.uint8).tobytes()
    def active(t): return any(s <= t <= e for s, e in segments)

    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-vf", "scale=1000:1360:flags=bicubic",
                           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for f in range(frames):
        t = f / FPS
        if not active(t):
            ff.stdin.write(black); continue
        lev, b = float(rms[f]), bands[f]
        R = rot(t)
        # sphere: stays a sphere - a gentle breath with the voice, a slow shimmer, a soft ripple
        # MOTION scales all of it (see the top of the file)
        push = 1 + MOTION * (0.08 * lev + 0.024 * np.sin(t * 1.4 + JIT) + 0.13 * b[BAND] * (0.4 + lev)
                             + 0.02 * np.sin(phi * 4 - t * 1.6))
        P = (SPH * push[:, None]) @ R.T
        hot = np.clip(b[BAND] * 1.2 - 0.2, 0, 1)[:, None]      # loud bands warm towards white
        col = GOLD * (1 - hot) + WHITE * hot
        buf = np.zeros((H, W, 3), np.float32)
        z = P[:, 2]; s = CAM / (CAM - z)
        x = (CX + P[:, 0] * R0 * s).astype(int); y = (CY - P[:, 1] * R0 * s).astype(int)
        depth = np.clip((z + 1.1) / 2.2, 0, 1)                 # 0 at the back, 1 at the front
        ok = (x >= 5) & (x < W - 5) & (y >= 5) & (y < H - 5)
        w = ((0.55 + 0.5 * lev) * (0.18 + 0.82 * depth ** 1.5))[:, None] * col * 1.2
        for i, kern in enumerate(DOTS):                        # back third small, front third large
            m = ok & (np.minimum((depth * 3).astype(int), 2) == i)
            dots(buf, x[m], y[m], w[m] * (0.9, 0.6, 0.45)[i], kern)
        # dust: drifts outward faster while the AI is loud, fades out at the edge, starts again inside
        rr = 1.3 + (DUST_R0 - 1.3 + t * DUST_SPD * (0.9 + 0.6 * lev)) % 1.9   # drifts, a little faster on loud words
        D = (DUST_DIR * rr[:, None]) @ R.T
        fade = np.clip(1 - (rr - 1.3) / 1.9, 0, 1) ** 1.5
        dcol = np.where((np.arange(ND) % 7 == 0)[:, None], CYAN, GOLD)
        z = D[:, 2]; s = CAM / (CAM + 2.2 - z)                  # dust is further out: keep it in front of the camera
        x = (CX + D[:, 0] * R0 * s * 1.6).astype(int); y = (CY - D[:, 1] * R0 * s * 1.6).astype(int)
        ok = (x >= 5) & (x < W - 5) & (y >= 5) & (y < H - 5)
        dots(buf, x[ok], y[ok], (fade * (0.5 + 0.3 * lev))[ok, None] * dcol[ok] * 0.35, DOTS[0])
        # glow: a wide and a tight blur of the points, added back
        pts = Image.fromarray(np.clip(buf, 0, 255).astype(np.uint8))
        glow = (np.asarray(pts.filter(ImageFilter.GaussianBlur(14)), np.float32) * 1.6
                + np.asarray(pts.filter(ImageFilter.GaussianBlur(3)), np.float32) * 1.3)
        core = np.exp(-(rho / (R0 * 0.5)) ** 2)[..., None] * GOLD * (0.07 + 0.10 * lev)
        img = bg + core + glow + buf
        ff.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    ff.stdin.close()
    if ff.wait():
        raise SystemExit("ai_particles: ffmpeg failed")

if __name__ == "__main__":
    args = [x for i, x in enumerate(sys.argv[1:]) if not x.startswith("--") and not sys.argv[i].startswith("--motion")]
    if "--motion" in sys.argv:
        MOTION = float(sys.argv[sys.argv.index("--motion") + 1])
    if len(args) != 2:
        sys.exit(__doc__)
    with wave.open(args[0]) as w:
        dur = w.getnframes() / w.getframerate()
    render(args[0], [(0, dur)], dur, args[1])
    print("done:", args[1])
