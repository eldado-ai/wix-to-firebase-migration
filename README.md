# Wix → Firebase migration

A [Claude Code](https://claude.com/claude-code) skill that walks an agent (and the site owner) through moving an existing Wix website to self-hosted Firebase Hosting — content and images extracted and rebuilt as plain files you own, a contact-form backend replacing Wix's built-in form, spam protection, SEO-preserving redirects, and the domain cutover itself, in an order specifically chosen so nothing goes live before it's been verified.

This isn't a script you run once and walk away from — it's a structured process an agent follows over several sessions, asking the site owner for decisions and account access at each step rather than assuming them.

## Why leave Wix

Wix is a closed platform: the HTML it serves is generated, content lives behind its CMS, and a domain registered through Wix is locked in ways that block common infrastructure choices. This skill exists because getting off it safely — without losing content, breaking email, or tanking search rankings — takes a specific, non-obvious sequence of steps, and getting that sequence wrong is expensive to undo.

## What it covers

| Phase | What happens |
|---|---|
| Discovery | Inventory the Wix site — pages, DNS, email records, features in use |
| Content extraction | Pull every page's real content (not just what the nav shows) and every referenced image, structured — not flattened to plain text |
| Site rebuild | Generate static HTML/CSS from one template, no build step |
| Firebase setup | Project, `firebase.json`, first deploy to a free `*.web.app` domain |
| Contact form | A Cloud Function replacing Wix's form, with the tradeoffs explained |
| Spam protection | Honeypot + rate limit + reCAPTCHA v3 |
| SEO preparation | Canonical URLs, sitemap, 301 redirects from every old Wix URL |
| **Domain cutover** | The one irreversible step — done last, in an order that avoids downtime |
| Post-cutover verification | Confirm on the real domain, not the temporary one |
| Cloudflare (optional) | Only if the tradeoff (a registrar transfer) is worth it to the user |

Two optional add-ons are documented too, since they come up often after a migration: a floating "contact us" button reusing the same form, and blog post audio narration via text-to-speech.

## Using this

This repo is meant to be used as a Claude Code skill, not run as a standalone CLI tool. Point Claude Code at it (or drop it in a skills directory it scans) and start a conversation about moving a Wix site — `SKILL.md` is the entry point the agent follows.

The scripts under `scripts/` are also usable by hand if you'd rather drive the process yourself — each one takes `--help` for usage, and `references/` has the full detail behind every phase (the non-obvious traps, not just the happy path).

## Structure

```
SKILL.md                     — the process itself, phase by phase
references/                  — one file per phase/topic, full detail + traps
scripts/                     — extraction, image download, site generation, verification
assets/                      — a Cloud Function template and a privacy-policy starting point
```

## Note

This is a personal skill built from real migrations, not an official Anthropic or Firebase product. `assets/privacy-policy-template.html` is a starting point, not legal advice — say so to whoever uses it.
