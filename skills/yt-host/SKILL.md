---
name: yt-host
description: >-
  Keep the on-camera host identical across every video: same face, same teeth,
  same voice, same look. Turns voiced lines into talking-host clips from one
  approved portrait. Use for "make me talk", "animate my photo", "host clip",
  "avatar", "new episode without filming", or any video where the host appears
  but was not filmed.
---

# yt-host

Consistency does not come from describing the host well. It comes from **never re-deciding**. One
approved portrait, one model, one setting, one voice - chosen once, written down, reused. Every
run reads the host kit; nothing about the host's appearance is chosen per episode.

## The host kit

Lives outside the repo, because it holds the host's face:

```
~/.claude/youtube/host/
  host.json            the decisions: approved portrait, model, temperature, prompt, voices, look
  approved/portrait.jpg  the exact image sent to the model, already cropped
  approved/reference-take.mp4  the approved test clip - what "looks right" means
  portraits/           the source photos
  teeth/               mouth close-ups - the reference for the teeth check
  voice/pmst-nepal.wav   the approved brand name, out loud - the reference for the brand check
```

Read `host.json` first, every time. If `approved_portrait` is null, there is no kit yet - go to
**Approving a portrait**, not to generation.

## Making clips

1. Voice the line with `host.json → voice` (ElevenLabs, that voice id and speed). Keep the notes:
   the brand is written `P M S T, <break time="0.3s" /> Nepal` or it is mispronounced.
2. **Check the brand before any clip is made** - see **The brand, out loud** below. A wrong brand
   found after generation costs a clip; found here it costs nothing.
3. One clip per line. Lines over `avatar.max_seconds_per_job` get split at a pause, not mid-word.
4. Dry run first and show the user the cost line. Generation costs money; the user says go.

```bash
python3 skills/yt-host/avatar.py voice/you1.mp3 out/you1.mp4          # cost only
python3 skills/yt-host/avatar.py voice/you1.mp3 out/you1.mp4 --go     # generate
```

5. The output is 25 fps on the portrait's own background. The episode build retimes it to the
   edit's frame rate and replaces the background with the kit's `look`.

## The brand, out loud

The channel name is said the same way in every video, and the reference for "the same way" is a
recording, not a spelling: `host.json → voice.brand_clip` (`voice/pmst-nepal.wav`, the approved
"PMST, Nepal" from ep02). The spelling trick gets most lines right; delivery settings still break it.
Known failures with the host voice:

- `PMS Tina Paul` / `PM Stinney Paul` - the letters run together. Fixed by the spaced spelling.
- `PMST and Nepal`, or a drawn-out `Neh-pal` - higher style or lower stability (an energetic
  delivery) adds a sound before "Nepal" or stretches it. The spelling does not prevent this.

Every line that says the brand gets transcribed (faster-whisper, word timestamps) before it is used.
If the brand is wrong:

1. Re-voice once with the calm settings (stability 0.5, style at most 0.15). Sign-off lines do not
   need the energy of the argument lines.
2. Still wrong, or the line is already animated: splice the reference in. Find the bad word's span on
   the loudness envelope (from the dip after "PMST" to the dip before the next word), replace it with
   the clip's "Nepal" matched to the line's loudness, starting where the old word started, with
   silence after it. The line keeps its length, so a clip animated from it stays in sync and is not
   paid for twice. Keep the original as `<stem>-orig.mp3`.
3. Transcribe again. The check passes when it reads "PMST Nepal" with nothing between the two.

## The check - every clip, before it goes in an edit

Pull 8-12 frames across the clip plus a mouth crop of each, and put the approved portrait as the
first tile. Reject the clip if any of these fail:

- **Teeth.** Compare with `teeth/`. The real teeth are uneven; a take where they come out even and
  neat has been invented by the model. This is the most common failure and the easiest to miss.
- **Face.** Same face as tile one in every frame - eyes, beard line, hairline. No frame where it is
  "someone similar".
- **Calm.** No exaggerated pout or gape, head stays near the portrait's pose.

A rejected clip is regenerated once. If it fails twice, tell the user which check failed - do not
loosen the settings on your own.

## Approving a portrait

The model copies the photo's angle, sharpness and teeth. It cannot add what the photo does not show.

- Camera at eye level, head straight, looking into the lens. Low angles stay low in every video.
- **Lips parted, teeth showing** ("ehh"). Closed lips make the model invent teeth.
- Focus on the face. A soft photo gives a soft video; sharpening does not fix it.
- Tall crop, head and shoulders, nothing over the mouth.

Run one short test line, do the check above, and only when the user approves it, write the crop,
image and settings into `host.json` with the date. Changing the portrait later is a new approval, not
a tweak - and every episode after it will look different from every episode before it.

## The AI on screen

The AI is never a face. It is a sphere of gold light points that turns slowly in 3D and swells with
the AI's voice - `ai_particles.py`, approved on ep03 and recorded in `host.json → ai_visual`. Every
episode uses it as is; the build shows it on the stage only while the AI talks.

```bash
python3 skills/yt-host/ai_particles.py ai_voice.wav out.mp4          # preview on a voice file
# from a build:  ai_particles.render(ai_only_wav, [(start, end), ...], total_seconds, out_mp4)
```

- **The motion is decided: `MOTION = 1.0`.** It is about 40% of the first version, which jumped on
  every syllable and read as aggressive; half of the current level read as too still. If the user
  asks for calmer or livelier, change only `MOTION` (0.75 calmer, 1.5 livelier), show a test, and
  record the new value in `host.json` once they approve it.
- **It stays a sphere.** The voice is smoothed over ~0.2 s and the push is a few percent of the
  radius. A change that lets the shape break up is a different look, not a tweak.
- **The 3D comes from depth, not movement:** perspective, and near points larger and brighter than
  far ones. Keep both if anything about the look changes.

## The logo

The channel logo lives in the kit (`brand/logo-source.png`, transparent) and goes on with `logo.py`,
as the last step on a finished episode - never baked into a template, so any video can take it:

```bash
python3 skills/yt-host/logo.py ep.mp4 out.mp4 --intro            # 2.4 s sting before the video
python3 skills/yt-host/logo.py ep.mp4 out.mp4 --outro            # 2.4 s sting after it
python3 skills/yt-host/logo.py ep.mp4 out.mp4 --badge tl --from 1 --to 12
python3 skills/yt-host/logo.py ep.mp4 out.mp4 --badge at --at 760,1560 --size 0.22
python3 skills/yt-host/logo.py --preview sting.mp4               # see the animation alone
```

The logo sits on a white card so its red and navy read on any background, and every part animates on
its own (letters pop in turn, "SINCE"/"2013" wipe, "US-Nepal" slides, a shine crosses it).

- **Intro on a Short costs the hook.** The first second decides the swipe; a 2.4 s logo before the
  first line spends it. Prefer the badge or the outro on Shorts, the intro on long videos.
- **Corners collide.** On Shorts the right edge and the bottom carry YouTube's buttons and title, and
  the episode's own layout has a title at the top. Pull one frame with the badge on and look before
  rendering the rest.

## The gate

Nothing here publishes. The video says the host's words in the host's voice, so every upload made
with it carries YouTube's altered-or-synthetic-content disclosure. The last line of every run is the
question: **use this clip, or regenerate it?**
