# reCAPTCHA v3

Adds invisible, score-based bot detection to the contact form — no challenge UI for real users, just a background score (0.0 = likely bot, 1.0 = likely human) the backend checks before sending mail.

## Creating the key

Use the classic reCAPTCHA admin console: https://www.google.com/recaptcha/admin/create

- Type: **Score based (v3)** — not Challenge (v2), and specifically not the Enterprise product. Google Cloud sometimes surfaces reCAPTCHA Enterprise as the default path for accounts that have used Google Cloud before; this classic console page reliably creates a standard v3 key, which is what the code in this skill verifies against. See "Enterprise vs. standard" below.
- **Domains**: register every domain that will ever serve the form during this migration, in one pass — `<project>.web.app`, `<project>.firebaseapp.com`, and both `<domain>` and `www.<domain>`. Adding a domain later is easy, but forgetting one now is the #1 cause of the failure below.

You get a **site key** (public, goes in frontend JS) and a **secret key** (goes in Secret Manager, never in code).

## Frontend

```html
<script src="https://www.google.com/recaptcha/api.js?render=SITE_KEY" async defer></script>
```

On form submit, get a token before posting:

```js
grecaptcha.ready(function() {
  grecaptcha.execute('SITE_KEY', {action: 'contact'}).then(function(token) {
    payload.recaptchaToken = token;
    // ...then POST payload
  });
});
```

## Backend

Verify server-side against Google's endpoint (full implementation in `assets/functions-template/index.js`):

```js
const resp = await fetch("https://www.google.com/recaptcha/api/siteverify", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ secret, response: token }).toString(),
});
const data = await resp.json();
// data.success, data.score (0.0–1.0)
```

Reject below a score threshold (0.5 is a reasonable default) and reject a missing token outright.

## The two failure modes that aren't your code

Both look like application bugs and cost real debugging time before the actual cause is found — check these first.

**"ERROR for site owner: Invalid domain for site key"** shown directly to a real visitor. The domain they're on isn't in the key's registered domain list. Fix in the reCAPTCHA admin console (Settings → Domains), not in code. This recurs every time a new domain starts serving the form — the temporary `*.web.app` domain, then later the real domain — so re-check the domain list at each stage rather than assuming it's still complete.

**Server logs show `browser-error` from `siteverify`, with no other detail**, while the domain list is confirmed correct. This is very likely an **Enterprise-type key being checked against the classic `siteverify` endpoint**, which only understands standard v3/v2 keys. Enterprise keys need a different verification API (`createAssessment`) entirely. The fix is not code — delete the key and create a fresh one through the classic admin console URL above, explicitly as Score based (v3). Confirm by checking the key's row in the reCAPTCHA console; it will say "reCAPTCHA v3" plainly if correct, or show Enterprise-specific fields if not.

If you inherit an existing key and can't tell which type it is, the fastest resolution is often to just create a new standard v3 key from scratch and swap both the site key (frontend) and secret (backend secret value) — faster than diagnosing an ambiguous existing key.

## Re-registering domains after the custom domain goes live

Once Phase 7's cutover completes, the real domain serves the site. If reCAPTCHA was set up in Phase 5 with only the temporary `*.web.app` domains registered, add the real domain (and `www`) to the same key now — don't wait for a user report of the "Invalid domain" error in production.

## Hiding the floating badge

Users regularly ask to remove the "protected by reCAPTCHA" badge that floats over the page — it's Google's default UI and clashes with a custom design. This is allowed, but only if you replace it with a visible text disclosure; Google's terms require one or the other, not neither.

```css
.grecaptcha-badge { visibility: hidden; }
```

Use `visibility: hidden`, not `display: none` — Google's own guidance calls out `visibility` specifically, and it's a one-line, low-risk change.

Then add the required text near every form the badge was protecting, in the user's site language, linking Google's real policy pages:

```html
<p class="recaptcha-note">
  This site is protected by reCAPTCHA, and the
  <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google Privacy Policy</a>
  and
  <a href="https://policies.google.com/terms" target="_blank" rel="noopener">Terms of Service</a> apply.
</p>
```

If the site has more than one form using reCAPTCHA (e.g. an inline contact section plus a floating "contact us" modal — see `references/contact-form.md`), add this note next to each instance, not just the first one.
