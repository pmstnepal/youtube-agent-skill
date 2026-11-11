#!/usr/bin/env python3
"""logo.py - the channel logo, animated, added to any video: before it, after it, or in a corner.

    python3 logo.py in.mp4 out.mp4 --intro                    # logo sting, then the video
    python3 logo.py in.mp4 out.mp4 --outro                    # the video, then the logo sting
    python3 logo.py in.mp4 out.mp4 --badge tl                 # animated corner badge, whole video
    python3 logo.py in.mp4 out.mp4 --badge br --from 40 --to 46 --size 0.3
    python3 logo.py in.mp4 out.mp4 --badge at --at 760,1560 --size 0.22   # exact spot (badge's top-left, px)
    python3 logo.py in.mp4 out.mp4 --intro --outro --badge tr # any combination
    python3 logo.py --preview out.mp4                         # the sting alone, on a dark frame

The logo comes from the brand kit: ~/.claude/youtube/host/brand/logo-source.png (RGBA). It sits on a
white card so its red and navy read on any background. Each part animates on its own: the letters pop
up one after another, "SINCE" and "2013" wipe in, "US-Nepal" slides in, then a shine crosses the card.

Intro and outro are full frames: the card over a blurred, darkened still of the video's first (or last)
frame, with a soft two-note chime. The badge has no sound and leaves the video's audio alone.
Corners: tl tr bl br, or `at` with --at x,y for an exact spot. On Shorts, the right edge and the bottom
carry YouTube's buttons and title - tl is the safe corner; tr and br sit under the like/comment
buttons. Check the episode's own layout too: a corner can land on its title text.

Needs numpy, Pillow and ffmpeg.
"""
import json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

KIT = os.path.join(os.path.expanduser("~"), ".claude", "youtube", "host", "brand")
SRC = os.path.join(KIT, "logo-source.png")
FPS, SR = 30, 48000
STING = 2.4                       # intro/outro length, seconds
BADGE_IN, BADGE_OUT = 1.4, 0.35   # the badge's entrance and exit

# parts of the 1024x1024 source logo, by region (found from its alpha and colours)
CROP = (20, 310, 1020, 720)       # logo + breathing room; the card is drawn around this
LETTERS = [(0, 260), (260, 545), (545, 701), (701, 830)]          # p m s t, x ranges
SINCE = (600, 415, 830, 485)      # white text across s and t
YEAR = (835, 415, 1000, 485)      # "2013"
PLACE = (600, 600, 1000, 705)     # "US-Nepal"

def ease_back(x):                 # overshoots a little, then settles: a "pop"
    x = np.clip(x, 0, 1); c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2

def ease_out(x):
    x = np.clip(x, 0, 1); return 1 - (1 - x) ** 3

def load_parts():
    logo = np.asarray(Image.open(SRC).convert("RGBA")).astype(np.float32)
    rgb, a = logo[..., :3], logo[..., 3]
    white = (rgb.min(-1) > 200) & (a > 0)
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W]
    def region(m):
        out = logo.copy(); out[..., 3] = np.where(m, a, 0); return out
    def box(b): return (xx >= b[0]) & (xx < b[2]) & (yy >= b[1]) & (yy < b[3])
    since, year, place = box(SINCE) & white, box(YEAR), box(PLACE)
    letters = [region((xx >= x0) & (xx < x1) & ~since & ~year & ~place) for x0, x1 in LETTERS]
    parts = {"letters": letters, "since": region(since), "year": region(year), "place": region(place)}
    c = CROP
    crop = lambda p: Image.fromarray(p[c[1]:c[3], c[0]:c[2]].astype(np.uint8), "RGBA")
    return {k: [crop(p) for p in v] if k == "letters" else crop(v) for k, v in parts.items()}

def card_frame(parts, t, width, out_at=None):
    """The card with the logo at time t (seconds since the entrance began), `width` px wide, RGBA."""
    cw, ch = CROP[2] - CROP[0], CROP[3] - CROP[1]
    k = width / cw
    w, h = width, round(ch * k)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # the card: scales up and fades in first
    cs = 0.86 + 0.14 * ease_back(t / 0.3); ca = ease_out(t / 0.2)
    cardw, cardh = round(w * cs), round(h * cs)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    x0, y0 = (w - cardw) // 2, (h - cardh) // 2
    d.rounded_rectangle((x0, y0, x0 + cardw, y0 + cardh), radius=round(h * 0.16), fill=(255, 255, 255, round(255 * ca)))
    canvas.alpha_composite(card)

    def place(img, dx=0.0, dy=0.0, scale=1.0, alpha=1.0, wipe=1.0):
        if alpha <= 0 or wipe <= 0:
            return
        im = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        if wipe < 1:                                      # reveal left to right
            arr = np.asarray(im).copy(); arr[:, round(arr.shape[1] * wipe):, 3] = 0; im = Image.fromarray(arr)
        if alpha < 1:
            arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3] * alpha).astype(np.uint8); im = Image.fromarray(arr)
        canvas.alpha_composite(im, (round((w - im.width) / 2 + dx * w), round((h - im.height) / 2 + dy * h)))

    for i, L in enumerate(parts["letters"]):              # letters pop up one after another
        p = (t - 0.18 - i * 0.09) / 0.38
        if p > 0:
            place(L, dy=0.10 * (1 - ease_out(p)), scale=0.75 + 0.25 * ease_back(p), alpha=ease_out(p * 1.6))
    place(parts["since"], wipe=ease_out((t - 0.62) / 0.35))
    place(parts["year"], wipe=ease_out((t - 0.72) / 0.35))
    p = (t - 0.85) / 0.4
    place(parts["place"], dx=0.06 * (1 - ease_out(p)), alpha=ease_out(p))

    arr = np.asarray(canvas).astype(np.float32)
    # shine: a soft diagonal band of light crossing the card once
    s = (t - 1.25) / 0.55
    if 0 < s < 1:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        band = np.exp(-(((xx + yy * 0.6) - (-0.3 + 1.6 * s) * w) / (w * 0.06)) ** 2)
        logo_ink = (arr[..., :3].min(-1) < 230) & (arr[..., 3] > 0)
        arr[..., :3] += (band * logo_ink * 120)[..., None]
    if out_at is not None and t > out_at:                 # exit: shrink a little and fade
        q = ease_out((t - out_at) / BADGE_OUT)
        arr[..., 3] *= 1 - q
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        sc = 1 - 0.08 * q
        small = im.resize((round(w * sc), round(h * sc)), Image.LANCZOS)
        im = Image.new("RGBA", (w, h)); im.alpha_composite(small, ((w - small.width) // 2, (h - small.height) // 2))
        arr = np.asarray(im).astype(np.float32)
    # a soft shadow under the card, so it lifts off busy backgrounds
    sh = Image.fromarray((arr[..., 3] * 0.45).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(2, w // 60)))
    out = Image.new("RGBA", (w, h + w // 40)); out.paste((0, 0, 0, 255), (0, w // 80), sh)
    out.alpha_composite(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    return out

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", path], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])

def chime(dur):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for start, f in ((0.15, 784.0), (0.42, 1046.5)):     # G5 then C6, soft bell tones
        u = np.clip(t - start, 0, None)
        out += (np.sin(2 * np.pi * f * u) + 0.3 * np.sin(4 * np.pi * f * u)) * np.exp(-u * 4.5) * (t >= start)
    return (out * 0.12 * 32767).astype(np.int16)

def sting(parts, W, H, still, path, outro=False):
    """A full-frame sting: card centred over a blurred, darkened still."""
    bg = Image.open(still).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.fromarray((np.asarray(bg) * 0.45).astype(np.uint8))
    n = int(STING * FPS)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", path + ".pcm",
                           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-shortest", path],
                          stdin=subprocess.PIPE)
    open(path + ".pcm", "wb").write(chime(STING).tobytes())
    for f in range(n):
        t = f / FPS
        card = card_frame(parts, t, round(W * 0.82), out_at=STING - BADGE_OUT if outro else None)
        frame = bg.copy(); frame.paste(card, ((W - card.width) // 2, (H - card.height) // 2), card)
        ff.stdin.write(np.asarray(frame).tobytes())
    ff.stdin.close(); ff.wait(); os.remove(path + ".pcm")

def badge_clip(parts, width, dur, path):
    """The badge as a transparent clip (qtrle in .mov keeps the alpha)."""
    n = int(dur * FPS)
    first = card_frame(parts, 0, width)
    w, h = first.size
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(FPS),
                           "-i", "-", "-c:v", "qtrle", path], stdin=subprocess.PIPE)
    still = None
    for f in range(n):
        t = f / FPS
        if BADGE_IN < t < dur - BADGE_OUT and still is not None:
            frame = still                                 # settled: reuse the same frame
        else:
            frame = card_frame(parts, t, width, out_at=dur - BADGE_OUT)
            if t >= BADGE_IN and still is None:
                still = frame
        ff.stdin.write(frame.tobytes())
    ff.stdin.close(); ff.wait()
    return w, h

def main():
    a = sys.argv[1:]
    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default
    parts = load_parts()
    if "--preview" in a:
        out = opt("--preview"); tmp = tempfile.mkdtemp()
        Image.new("RGB", (1080, 1920), (40, 30, 26)).save(os.path.join(tmp, "s.png"))
        sting(parts, 1080, 1920, os.path.join(tmp, "s.png"), out); print("preview:", out); return
    src, out = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))][:2]
    W, H, D = probe(src)
    tmp = tempfile.mkdtemp()
    inputs, filt, vlabel = ["-i", src], [], "[0:v]"
    badge = opt("--badge")
    if badge:
        t0 = float(opt("--from", 0)); t1 = float(opt("--to", D)); size = float(opt("--size", 0.26))
        bw, bh = badge_clip(parts, round(W * size), t1 - t0, os.path.join(tmp, "badge.mov"))
        m = round(W * 0.04)
        if badge == "at":
            x, y = (int(v) for v in opt("--at").split(","))
        else:
            x = m if badge[1] == "l" else W - bw - m
            y = round(H * 0.06) if badge[0] == "t" else H - bh - round(H * 0.16)
        inputs += ["-itsoffset", str(t0), "-i", os.path.join(tmp, "badge.mov")]
        filt.append(f"{vlabel}[1:v]overlay={x}:{y}:eof_action=pass[vb]"); vlabel = "[vb]"
    body = os.path.join(tmp, "body.mp4")
    if filt:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", vlabel,
                        "-map", "0:a?", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", body], check=True)
    else:
        body = src
    pieces = []
    if "--intro" in a:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-frames:v", "1", os.path.join(tmp, "first.png")], check=True)
        sting(parts, W, H, os.path.join(tmp, "first.png"), os.path.join(tmp, "intro.mp4")); pieces.append(os.path.join(tmp, "intro.mp4"))
    pieces.append(body)
    if "--outro" in a:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", src, "-frames:v", "1", os.path.join(tmp, "last.png")], check=True)
        sting(parts, W, H, os.path.join(tmp, "last.png"), os.path.join(tmp, "outro.mp4"), outro=True); pieces.append(os.path.join(tmp, "outro.mp4"))
    if len(pieces) == 1:
        os.replace(body, out) if body != src else subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy", out], check=True)
    else:
        ins = sum((["-i", p] for p in pieces), [])
        chain = "".join(f"[{i}:v]fps={FPS},setsar=1[v{i}];[{i}:a]aresample={SR},aformat=channel_layouts=stereo[a{i}];" for i in range(len(pieces)))
        chain += "".join(f"[v{i}][a{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=1[v][a]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", chain, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", out], check=True)
    print("done:", out)

if __name__ == "__main__":
    main()
