# Blog audio narration (optional enhancement)

A "listen to this post" feature: a play button on each blog post (and each blog listing card) that reads the post aloud, using Google Cloud Text-to-Speech to pre-generate one MP3 per post rather than synthesizing on the fly. Pre-generating is the right call for a brochure/blog site — the content doesn't change often, generation is a one-time batch job, and the result is a static file Firebase Hosting already knows how to serve.

This is unrelated to the migration itself; treat it as an optional add-on requested after the site is live, the way Cloudflare (Phase 9) is.

## Voice cloning ("can I use my real voice?") — set expectations first

Users sometimes ask for their own voice rather than a generic TTS voice. Two real paths exist, neither of which is "flip a switch":

- **Google Cloud Instant Custom Voice** exists but is gated behind an allowlist/approval process for enterprise-style accounts — it is not available through a normal API key, and there's no way to know in advance whether a given project would be approved or how long that takes. Confirm this rather than assuming: `voices.list` will not show custom voices, and the REST discovery document (`$discovery/rest?version=v1` and `v1beta1`) has no `customVoices`-style resource — if it's not there, self-serve access isn't available on that project.
- **ElevenLabs** (a different vendor entirely) does offer accessible instant voice cloning, but it means the user records themselves, signs up for a paid plan, and hands you an API key. This skill doesn't cover ElevenLabs integration — if the user wants to go this route, it's a separate build.

For most requests, a high-quality stock voice is the right default — offer it first.

## Picking a voice: generate samples, don't guess

Google's Hebrew (and most other language) voice catalog spans old and new generations — plain `Standard`, `Wavenet`, and the newer `Chirp3-HD` voices, which sound noticeably more natural. List what's actually available before choosing:

```bash
curl -s -G "https://texttospeech.googleapis.com/v1/voices" \
  --data-urlencode "key=$API_KEY" \
  --data-urlencode "languageCode=he-IL"
```

Generate a short sample (one or two sentences of real site content) in 3–4 candidate voices, send them to the user as files, and let them pick — don't commit the whole batch to one voice on a guess. This costs a handful of API calls and avoids redoing 40+ files because the chosen voice didn't land.

## API key setup — the referrer-restriction trap

The Text-to-Speech REST API is simpler to script against than the client libraries, using a plain API key:

1. Enable the API: `console.cloud.google.com/apis/library/texttospeech.googleapis.com?project=<project>`
2. Create an API key: `console.cloud.google.com/apis/credentials?project=<project>` → Create Credentials → API key
3. Restrict it to **Cloud Text-to-Speech API only** under API restrictions (safe even if the key leaks)

**The key will fail with `403 API_KEY_HTTP_REFERRER_BLOCKED` on the first server-side call**, even though it works fine in a browser. Newly created keys sometimes default to (or get left with) an HTTP-referrer application restriction, which blocks any request without a browser `Referer` header — exactly what a server-side script sends. Fix: in the key's settings, set **Application restrictions → None** (leave the API restriction to Text-to-Speech alone in place — that's the restriction that actually matters for safety). This is a one-field change in the console; there is no code-side workaround.

## Generating the files

Extract plain text per post (strip tags, turn paragraph/heading boundaries into `.\n` so the synthesized speech pauses between them), then call `text:synthesize` per post:

```python
payload = {
    "input": {"text": text},
    "voice": {"languageCode": "he-IL", "name": "he-IL-Chirp3-HD-Kore"},
    "audioConfig": {"audioEncoding": "MP3"}
}
resp = requests.post(
    f"https://texttospeech.googleapis.com/v1/text:synthesize?key={API_KEY}",
    json=payload
)
audio_bytes = base64.b64decode(resp.json()["audioContent"])
```

Save each result as `blog/audio/<slug>.mp3`, matching the post's own filename slug so the frontend can compute the audio path from the page it's on without a lookup table.

**Set a request timeout** (`timeout=30` or similar) and use unbuffered/flushed output if running as a long batch — a hung request with no timeout and buffered `print()` output looks identical to "nothing is happening," and is easy to mistake for a stuck script when it's actually one bad connection. If a batch job seems to produce zero output after several minutes, check process CPU time (`ps aux`) — near-zero CPU with high wall-clock time confirms it's blocked on network I/O, not computing.

**5000-byte-per-request limit.** Google's `text:synthesize` caps input at 5000 bytes — Hebrew and other non-Latin scripts run 2 bytes/char in UTF-8, so this can bite well before 5000 *characters*. Check the longest post's byte length before assuming single-request synthesis is safe for the whole batch; if any post exceeds it, split on paragraph boundaries, synthesize each chunk separately, and concatenate the resulting MP3s with `ffmpeg` (concat demuxer) rather than raw byte concatenation, which corrupts MP3 frame boundaries.

## Frontend: play buttons without duplicating logic per post

One generic click handler, bound to every `[data-audio]` element on the page, covers both the full-post play button and every card's play button in a listing grid:

```js
let nowAudio = null, nowBtn = null;
function stopAudio() {
  if (nowAudio) nowAudio.pause();
  if (nowBtn) nowBtn.classList.remove('playing');
  nowAudio = null; nowBtn = null;
}
document.querySelectorAll('[data-audio]').forEach((btn) => {
  btn.addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (nowBtn === btn && nowAudio) {
      nowAudio.paused ? nowAudio.play() : nowAudio.pause();
      btn.classList.toggle('playing');
      return;
    }
    stopAudio();
    const audio = new Audio(btn.dataset.audio);
    audio.addEventListener('ended', stopAudio);
    audio.addEventListener('error', stopAudio);
    audio.play().catch(stopAudio);
    btn.classList.add('playing');
    nowAudio = audio; nowBtn = btn;
  });
});
```

Two details that matter:

- **`ev.preventDefault(); ev.stopPropagation();` is required** when the play button sits inside a card that's itself a link (`<a class="blog-card">...</a>` wrapping the whole card). Without it, clicking play also navigates to the post — the click event bubbles from the button up to the anchor and triggers its default action.
- **`.catch(stopAudio)` on `audio.play()`** — `play()` returns a promise that rejects if the source 404s or the format isn't supported. Without a catch, this surfaces as an unhandled promise rejection in the console on every failed play, which is noisy and easy to mistake for a real bug during testing (it'll happen legitimately if you test play buttons before the audio files finish generating).
- Track only one "now playing" audio globally — clicking a second play button should stop the first, not layer audio on top of audio.

## Bandwidth: caching, not access control

Someone will ask "how do I stop users replaying the audio over and over" expecting a rate-limit. The right answer is caching, not blocking legitimate use — see the `Cache-Control: immutable` entry in `references/firebase-setup.md`. Once set, repeat plays (even across page reloads) are served from the visitor's browser cache, not re-downloaded, so there's nothing left to protect against.

## Cost, in practice

Google Cloud TTS has a generous monthly free tier per voice tier (WaveNet/Chirp3-HD included). A typical blog — even 40–50 posts at ~1,000 characters each — totals well under 100K characters, a small fraction of the free allowance. Say the actual total character count when scoping this, so "is this going to cost money" gets a concrete answer instead of a vague reassurance.
