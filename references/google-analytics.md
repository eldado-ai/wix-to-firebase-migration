# Google Analytics (GA4) — optional, consent required

Users regularly ask "where are my visitor stats?" after a migration, expecting Firebase Hosting to report them. It doesn't — Firebase Hosting's own console only reports bandwidth/request volume (Usage and billing), not who visited or what they looked at. Actual traffic analytics means adding Google Analytics (GA4), which is a real scope change, not a small tweak: it introduces a new data processor and, for a site with EU visitors, a consent requirement before it can load at all. Say this plainly and get explicit agreement before building it — don't add analytics as a drive-by addition to some other change.

## Getting a Measurement ID

Since the site already runs on Firebase, linking Analytics through the Firebase project is the natural path — the user does this themselves (it's their Google Analytics account/org to create or choose):

1. Firebase Console → Project Settings → **Integrations** tab → Google Analytics → **Link** (or **Manage** if already linked)
2. Once linked, the Measurement ID (`G-XXXXXXXXXX`) is on Project Settings → General, or in Analytics itself under Admin → Data Streams → the web stream

Everything below assumes you have this ID.

## Why "Consent Mode defaults" isn't enough here

Google's own recommended pattern (Consent Mode v2) loads `gtag.js` unconditionally and adjusts its behavior based on a `consent` state — even in "denied" mode it still pings Google with reduced data. That's a defensible approach for a lot of sites, but for anything in a sensitive category (health, legal, financial — the kind of site this skill's users often run) the safer, simpler, and more clearly defensible rule is: **don't load the GA script at all until the visitor actively accepts.** No script tag exists in the DOM, no request to Google happens, nothing is ambiguous. This trades a small amount of Google's fanciness for a much easier "yes, nothing loads without consent" answer if anyone ever asks.

## The pattern: consent banner gates script injection

One consent banner, shown once per visitor (remembered via `localStorage`), on every page:

```html
<div class="cookie-consent" id="cookieConsent" role="dialog" aria-label="cookie consent">
  <p>This site uses Google Analytics cookies to understand how visitors use the site. See the <a href="privacy.html">privacy policy</a> for details.</p>
  <div class="cookie-consent-actions">
    <button type="button" id="cookieDecline">No thanks</button>
    <button type="button" id="cookieAccept">Accept</button>
  </div>
</div>
```

```js
var GA_ID = 'G-XXXXXXXXXX';

function loadAnalytics() {
  if (window.__gaLoaded) return;
  window.__gaLoaded = true;
  window.dataLayer = window.dataLayer || [];
  function gtag(){ dataLayer.push(arguments); }
  window.gtag = gtag;
  gtag('js', new Date());
  gtag('config', GA_ID);
  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
  document.head.appendChild(s);
}

var stored = null;
try { stored = localStorage.getItem('cookie-consent'); } catch (e) {}

if (stored === 'granted') {
  loadAnalytics();
} else if (stored !== 'denied') {
  document.getElementById('cookieConsent').classList.add('open');
}

document.getElementById('cookieAccept').addEventListener('click', function () {
  try { localStorage.setItem('cookie-consent', 'granted'); } catch (e) {}
  document.getElementById('cookieConsent').classList.remove('open');
  loadAnalytics();
});
document.getElementById('cookieDecline').addEventListener('click', function () {
  try { localStorage.setItem('cookie-consent', 'denied'); } catch (e) {}
  document.getElementById('cookieConsent').classList.remove('open');
});
```

The `try/catch` around `localStorage` isn't decorative — it's not available in every browsing context (private/incognito mode in some browsers, or if the user has storage disabled), and an uncaught exception there would break the whole page's script, not just consent tracking.

## Give visitors a way to change their mind

Add a small "Cookie settings" link in the footer (next to the privacy policy link, present on every page) that just re-opens the banner:

```js
document.getElementById('cookieSettingsLink').addEventListener('click', function (ev) {
  ev.preventDefault();
  document.getElementById('cookieConsent').classList.add('open');
});
```

This is expected by most consent frameworks and by GDPR-conscious users specifically — a banner that only ever appears once, with no way to revisit the choice, isn't real consent management.

## Rolling this out across every page

Same discipline as any other shared-template change (see Phase 2): the banner markup, its CSS, and this JS belong in the one shared template/partial the site already regenerates from — not hand-copied into each generated page. If the migration used `generate_site.py`, add the banner to the template file once; if pages were generated individually without a shared source, that's the moment to introduce one rather than patch 40 files by hand.

Watch for one layout collision specifically: if the site also has a floating action button (see `references/contact-form.md`) fixed to a bottom corner, a bottom consent banner can visually overlap it while the banner is open. Shift the FAB up (a CSS class toggled alongside `.cookie-consent.open`) rather than leaving the two stacked on top of each other.

## Update the privacy policy — don't skip this

`assets/privacy-policy-template.html` includes a line under "What this site does not do" stating no analytics are installed. If GA4 gets added, that line is now false and needs to change: delete it, and add a dedicated section — mirroring the reCAPTCHA section already in the template — naming Google Analytics specifically, saying what it's used for, and stating that it only loads after consent. Do this update in the same change that adds GA4, not as a follow-up someone might forget.
