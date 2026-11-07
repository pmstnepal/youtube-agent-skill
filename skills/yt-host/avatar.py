#!/usr/bin/env python3
"""avatar.py - one voiced line into a talking-host clip, from the approved portrait in the host kit.

    python3 avatar.py line.mp3 out.mp4             # prints the cost, does nothing else
    python3 avatar.py line.mp3 out.mp4 --go        # submits, waits, downloads

Everything that makes the host look the same in every video lives in ~/.claude/youtube/host/host.json:
the approved portrait (already cropped), the model, the expressiveness and the prompt. This tool reads
those and nothing else, so two episodes made months apart come out with the same face and teeth.

Needs SYNC_API_KEY in the environment. Lines over the per-job limit are refused - split the audio at a
pause instead. The job id is written next to the output before polling, so a re-run after a crash or a
closed laptop resumes the paid job instead of paying for a second one.
"""
import json, os, subprocess, sys, time, urllib.request, uuid

KIT = os.path.join(os.path.expanduser("~"), ".claude", "youtube", "host")
API = "https://api.sync.so/v2"
UA = "yt-host/1.0 (+https://github.com/Jakeschincariol/youtube-agent-skill)"

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())

def call(method, url, key, body=None, ctype=None):
    # the API sits behind a firewall that refuses urllib's default User-Agent (error 1010)
    req = urllib.request.Request(url, data=body, method=method, headers={"x-api-key": key, "User-Agent": UA})
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"sync.so {method} failed: HTTP {e.code} {e.read()[:400].decode(errors='replace')}")

def multipart(fields, files):
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    for name, (fname, data, mime) in files.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                     f'Content-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n")
    return b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    audio, out = args
    host = json.load(open(os.path.join(KIT, "host.json")))
    av, portrait = host["avatar"], host.get("approved_portrait")
    if not portrait:
        sys.exit("no approved portrait in host.json yet - run a test and approve one first")
    image = os.path.join(KIT, portrait["image"])

    secs = duration(audio)
    lo, hi = (secs * c for c in av["cost_per_second_usd"])
    print(f"{os.path.basename(audio)}: {secs:.1f}s  ->  ${lo:.2f}-${hi:.2f}  ({av['model']}, temperature {av['temperature']})")
    if secs > av["max_seconds_per_job"]:
        sys.exit(f"over {av['max_seconds_per_job']}s - split the line at a pause and run each half")
    if "--go" not in sys.argv:
        print("dry run - add --go to submit"); return

    key = os.environ.get("SYNC_API_KEY") or sys.exit("SYNC_API_KEY is not set")
    idfile = out + ".job"
    if os.path.exists(idfile):
        gid = open(idfile).read().strip(); print("resuming", gid)
    else:
        opts = {"i2v_prompt": av["i2v_prompt"], "temperature": av["temperature"]}
        body, ctype = multipart({"model": av["model"], "options": json.dumps(opts)},
                                {"image": ("portrait.jpg", open(image, "rb").read(), "image/jpeg"),
                                 "audio": (os.path.basename(audio), open(audio, "rb").read(),
                                           "audio/mpeg" if audio.endswith(".mp3") else "audio/wav")})
        gid = call("POST", f"{API}/generate", key, body, ctype)["id"]
        open(idfile, "w").write(gid); print("submitted", gid)

    while True:
        time.sleep(10)
        g = call("GET", f"{API}/generate/{gid}", key)
        if g["status"] == "COMPLETED":
            with urllib.request.urlopen(urllib.request.Request(g["outputUrl"], headers={"User-Agent": UA}), timeout=600) as r:
                open(out, "wb").write(r.read())
            os.remove(idfile)
            print("done:", out); return
        if g["status"] in ("FAILED", "REJECTED"):
            os.remove(idfile)
            sys.exit(f"{g['status']}: {g.get('errorCode')} {g.get('error')}")
        print(" ", g["status"], flush=True)

if __name__ == "__main__":
    main()
