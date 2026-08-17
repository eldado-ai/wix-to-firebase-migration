# Firebase project setup

## Account and project creation

The user creates the Firebase project themselves — it's tied to their Google account and, if a contact form is in scope, their billing. Point them to https://console.firebase.google.com, have them click "Add project," and get the project ID back from them (or drive it yourself if they've handed you an authenticated session/CLI).

Install and authenticate the CLI if not already done:

```bash
npm install -g firebase-tools
firebase login
```

## Blaze plan — when it's needed and why

The free **Spark** plan cannot run Cloud Functions or use Secret Manager. If Phase 4 (contact form) is in scope, the project needs **Blaze (pay-as-you-go)**. Say this plainly rather than letting the word "pay-as-you-go" cause alarm: Blaze includes a substantial free tier (2M function invocations/month as of writing), and a brochure-site contact form will not come close to it in practice. A pure static site with no form can stay on Spark.

The user upgrades via the console (Project Settings → Usage and billing). **Plan changes take a minute or two to propagate** — if a `firebase functions:secrets:set` command reports "must be on Blaze plan" immediately after they upgrade, don't start debugging. Wait briefly and retry; it resolves itself. This has caused real confusion because the console shows the new plan as active before the backend fully catches up.

## `firebase.json`

Minimal shape for a static site with no function yet:

```json
{
  "hosting": {
    "public": ".",
    "ignore": ["firebase.json", "**/.*", "functions/**", "**/node_modules/**"]
  }
}
```

`public` points at the directory containing the built site (adjust if your generated output lives in a subfolder). Once Phase 4 adds a function, `hosting.rewrites` and a top-level `functions` block get added — see `references/contact-form.md`.

## First deploy

```bash
firebase deploy --only hosting
```

Watch for two distinct completion states in the output — this distinction matters enough to repeat here even though `references/troubleshooting.md` covers it in depth:

```
✔  hosting[project-id]: file upload complete
i  hosting[project-id]: finalizing version...
✔  hosting[project-id]: version finalized
i  hosting[project-id]: releasing new version...
✔  hosting[project-id]: release complete
```

"file upload complete" is not "release complete." If the CLI process exits (errors, gets killed, or is run with `--only hosting,functions` and the functions half fails afterward) before reaching "release complete," the hosting change silently never goes live even though nothing in the earlier output looked like a hosting failure. Always confirm the final line appeared; if it didn't, rerun `firebase deploy --only hosting` alone.

The site is now live at `https://<project-id>.web.app` (and the equivalent `.firebaseapp.com`). This is the safe URL for every phase up through Phase 6 — the custom domain and its DNS aren't touched until Phase 7.

## Multiple deploy targets during development

If you're iterating quickly (many small CSS/content fixes in a row), it's fine to deploy after each change rather than batching — `firebase deploy --only hosting` for a small static site typically takes under 30 seconds. Batching many changes into one deploy makes it harder to isolate which change caused a problem if something breaks.

## Cache headers for static assets that don't change once published

Firebase Hosting's default caching is conservative. For content you generate once and never edit in place — images, and especially any generated audio (see the optional audio-narration enhancement) — set an explicit long-lived, immutable cache so repeat visits (and repeat plays of the same audio file) are served from the visitor's browser cache instead of re-downloaded from your hosting:

```json
{
  "hosting": {
    "headers": [
      {
        "source": "/blog/audio/**",
        "headers": [
          { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
        ]
      }
    ]
  }
}
```

If a file at that path ever needs to change, ship it under a new filename rather than overwriting — `immutable` tells browsers not to revalidate it at all for the `max-age` period, so an in-place edit may not reach visitors with a cached copy for up to a year.

## A deploy fails partway through uploading many new files

```
Error: Task <hash> failed: retries exhausted after 6 attempts, with error: Failed to make request to https://upload-firebasehosting.googleapis.com/...
```

This shows up when a deploy uploads a large batch of new binary files at once (e.g. dozens of newly generated images or audio files added in the same deploy) — one file's upload hits a transient network failure and the whole command exits non-zero, even though most files uploaded fine. It is not a sign of a broken file or a config problem.

**Fix:** just rerun `firebase deploy --only hosting`. The deploy is content-addressed — it re-checks which files are already present on the current hosting version and only uploads what's still missing, so the retry is fast and safe to repeat.
