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
```

Read `host.json` first, every time. If `approved_portrait` is null, there is no kit yet - go to
**Approving a portrait**, not to generation.

## Making clips

1. Voice the line with `host.json → voice` (ElevenLabs, that voice id and speed). Keep the notes:
   the brand is written `P M S T, <break time="0.3s" /> Nepal` or it is mispronounced.
2. One clip per line. Lines over `avatar.max_seconds_per_job` get split at a pause, not mid-word.
3. Dry run first and show the user the cost line. Generation costs money; the user says go.

```bash
python3 skills/yt-host/avatar.py voice/you1.mp3 out/you1.mp4          # cost only
python3 skills/yt-host/avatar.py voice/you1.mp3 out/you1.mp4 --go     # generate
```

4. The output is 25 fps on the portrait's own background. The episode build retimes it to the
   edit's frame rate and replaces the background with the kit's `look`.

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

## The gate

Nothing here publishes. The video says the host's words in the host's voice, so every upload made
with it carries YouTube's altered-or-synthetic-content disclosure. The last line of every run is the
question: **use this clip, or regenerate it?**
