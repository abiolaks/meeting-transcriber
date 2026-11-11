# Deployment options

A decision record for **where the compute runs**. This sits beside `SPEC.md` and
does not override its locked decisions until one option is chosen.

## The question

> Can this be hosted for free, for two people, usable from Mac and Windows
> without installing anything on the laptop?

Short answer: **yes — but hosting moves the *models*, not the *microphone*.**
Something on the laptop must still hear the meeting. That turns out to be a small
thing (a ~10 MB capture agent), which is a much better trade than it first sounds.

---

## The capture problem, stated precisely

A web page **cannot** hear the Zoom or Teams desktop app. Browser audio capture
(`getDisplayMedia({ audio: true })`) can only take the audio of a *tab* in the
same browser, and only if the user ticks "share tab audio".

| Meeting platform | Browser-only? | Why |
|---|---|---|
| Google Meet (in Chrome/Edge) | **Yes** | Tab audio capture works |
| Zoom (desktop app) | **No** | Page cannot reach another process's audio |
| Teams (desktop app) | **No** | Same, plus protected audio path |
| Any of them, recording uploaded | **Yes** | Platform does the capture, you upload the file |

So "zero install" is achievable only for Google Meet, or for an upload-after-the-
fact workflow. For Zoom and Teams desktop, some client-side component is required
unless you accept a much worse experience (joining the meeting *inside* a browser
tab you control, which Zoom and Teams do not really support).

---

## Three modes

### Mode A — Local all-in-one (current spec)

Everything on the laptop. `SPEC.md` v0.3 as written.

- **Pros:** no network, no data leaving the machine, zero marginal cost, works on
  a plane. Nothing to host.
- **Cons:** the i7-8650U is Tier C — ~25–35 min per hour of meeting. Install is a
  desktop app with ~3 GB of models and IT may object.

### Mode B — Thin capture agent + hosted processing ★

A ~10–20 MB agent records mic + system loopback, encrypts, and streams or uploads
to a backend that does ASR, synthesis and storage. The UI is a browser tab.

```
laptop: capture agent (10-20 MB, no models)
   │  HTTPS, chunked, resumable
   ▼
server: queue → ASR → LLM → SQLite → web UI
```

- **Pros:** models never touch the laptop; the agent is small enough to be
  tolerable to IT; Mac and Windows both just need the agent + a browser; compute
  is decoupled and upgradeable; one server serves both people.
- **Cons:** audio leaves the laptop (policy question); needs connectivity during
  the meeting; you now run a server.

> **Note:** the agent still needs the same permissions as Mode A — loopback access
> on Windows (none), screen-recording on macOS. Hosting does not remove that.

### Mode C — Browser-only, no install at all

Either Google Meet tab capture, or upload a platform recording (Zoom local
recording, Teams/Meet cloud recording downloaded).

- **Pros:** genuinely zero install; works on any machine including a locked-down
  work laptop; excellent for a two-person trial.
- **Cons:** Zoom/Teams real-time is out; you depend on the meeting host permitting
  recording; cloud recordings can take minutes to appear after the call.

---

## What "free hosting" actually means

Ranked by viability for CPU inference, honestly.

| Option | Spec | Real catch |
|---|---|---|
| **Oracle Cloud Always Free** | 4× Ampere A1 (ARM) + 24 GB RAM, indefinitely | Capacity is frequently unavailable in popular regions; Oracle reclaims instances that look idle; account approval can be slow. **But it is the only free tier that can actually run this.** |
| **Own machine + Tailscale / Cloudflare Tunnel** | The M2 at home, reached from anywhere | Free and private; needs the Mac awake; you are the ops team. Tailscale free covers 3 users / 100 devices. |
| **Hetzner CX22 / CAX11** | 2 vCPU, 4 GB, ~€4/month | Not free, but reliable and boring. The escape hatch when free hosting disappoints. |
| Hugging Face Spaces (free CPU) | 2 vCPU, 16 GB | Sleeps, public-by-default, ToS not meant for this. Demo only. |
| Render / Railway / Fly free tiers | 512 MB – $5 credit | Too small or too temporary for 20-minute inference jobs. |
| Cloudflare Workers / Containers | CPU-time limits | Cannot host whisper.cpp for a 60-minute job. |

**Speed reality check:** a 4-OCPU Ampere A1 is roughly comparable to, or faster
than, the i7-8650U for sustained batch inference — no 15 W thermal ceiling, no
competing Teams process. So Mode B is **not** a speed downgrade. It is often an
upgrade, at the cost of privacy and connectivity.

### Two users is easy

One VM, one SQLite file, a job queue with a concurrency limit of 1–2 so two
60-minute jobs do not thrash 4 cores, two accounts, TLS via Caddy. No tenancy
model needed. Roughly 30–115 MB of audio per meeting stored.

---

## The uncomfortable part

In Mode B, **work-meeting audio leaves the laptop and lands on a third-party
host.** For a corporate machine that is often a policy violation regardless of
how well the app is built, and it is a materially different consent story from
"nothing ever leaves your device." Recording consent gets harder too: you are now
disclosing to a service, not just to a file on your disk.

If the meetings are internal and the laptop is company property, this is worth
one conversation with whoever owns security policy before any code is written.

---

## Recommendation

**Build Mode B, with Mode C as the zero-install on-ramp, and keep Mode A as the
fallback for anyone who cannot send audio anywhere.**

The reason is that Mode B does not throw away the local work:

- the pipeline is identical — the same whisper.cpp, the same llama.cpp, the same
  note renderer, just running on a different box;
- the capture agent is a thin shell over the same audio code Mode A needs;
- the browser UI is the same UI Mode C needs.

Only the transport and the packaging differ. That is a genuinely small delta, and
it means the choice can be deferred — or rather, **made per user** rather than
baked in.

For hosting, start with the **M2 at home + Tailscale** (free, private, and you
already own it), and move to Oracle Always Free only if the Mac cannot stay awake.
If both become annoying, €4/month at Hetzner ends the argument.

---

## What this does to the spec

If Mode B is chosen, three things in `SPEC.md` change and nothing else does:

1. **D2 (offline runtime)** becomes mode-dependent: "no network" applies to
   Mode A only. Mode B requires a documented, explicit upload consent screen.
2. **§4 CPU tiering** splits into *client* (capture only — a 2010 laptop can do
   this) and *server* (inference tier).
3. **§17 Phase 0 gate** is measured on the server, not the i7-8650U. The
   benchmark kit still matters, but it now sizes the server instead of deciding
   whether the product exists.

## Open decision

> Does privacy/offline outweigh speed and convenience for these two users?

- If **privacy wins** → Mode A, and the i7-8650U limitation is accepted or the
  hardware changes.
- If **convenience wins** → Mode B, and the work happens on a server you control.
- If **you are unsure** → build the pipeline headless first (Phase 1). It is
  identical in all three modes, and it is the cheapest way to find out whether
  the notes are good enough to be worth any of this.
