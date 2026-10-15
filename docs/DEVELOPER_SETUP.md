# Moodfarer — Developer Setup Guide

A calm, mobile-first self-assessment tracker built with Flask, Jinja2, Tailwind CSS,
vanilla JavaScript, Chart.js, and SQLAlchemy (SQLite locally).

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000. The SQLite database is created automatically at
`/tmp/checkin.db` (override with the `DATABASE_PATH` environment variable).

## Accounts

Sign-up and sign-in are built in with Flask-Login and hashed passwords
(werkzeug's `generate_password_hash`/`check_password_hash` — no plaintext ever
stored). Every route except `/login` and `/signup` requires a signed-in session,
and every query is scoped to `current_user.id`, so one person can never see another
person's check-ins (a mismatched `assessment_id` returns a 404, not someone else's
data). Sessions are cookie-based; set a real `SECRET_KEY` environment variable
before deploying — the fallback in `app.py` is for local dev only.

The `Assessment` table's uniqueness constraint is now `(user_id, assessment_date)`
instead of `assessment_date` alone, so each user gets their own one-entry-per-day.

## Email, verification, and password reset

Email verification and password-reset links are generated with `itsdangerous`
signed, expiring tokens (verification links last 24 hours, reset links 1 hour) —
no separate token table needed.

Sending real email requires SMTP credentials via environment variables:

```
MAIL_SERVER=smtp.yourprovider.com
MAIL_PORT=587
MAIL_USERNAME=you@yourdomain.com
MAIL_PASSWORD=your-smtp-password
MAIL_DEFAULT_SENDER=you@yourdomain.com
MAIL_USE_TLS=true
```

**Without SMTP configured** (the default for local dev), emails aren't sent —
instead, the verification/reset link is written to the server log *and* flashed
directly on the page after signup / "forgot password", so the whole flow is
testable without setting up a mail server. Configure SMTP before deploying
somewhere real people will use.

Email verification is "soft": unverified users can still use the app, but see a
dismissible-per-visit banner with a resend link until they verify.

## Google sign-in

Optional — the "Sign in with Google" button only appears when both of these are
set:

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

Create these in the Google Cloud Console (OAuth consent screen + OAuth client ID,
type "Web application"), and add `http(s)://your-domain/auth/google/callback` as
an authorized redirect URI (for local dev: `http://localhost:5000/auth/google/callback`).
Signing in with Google auto-verifies the email and links to an existing
password-based account if the email already matches one.

## Account settings & deletion

`/account` lets a signed-in user update their name/email (changing email requires
re-verification), change or set a password, and permanently delete their account
(they must type their email to confirm — this cascades and deletes every
check-in they've logged).

## CSRF protection

All state-changing requests (forms and the `POST /api/assessments` the daily
check-in JS uses) are protected by Flask-WTF's `CSRFProtect`. Forms carry a
hidden `csrf_token` field; the JS fetch call reads the token from a `<meta
name="csrf-token">` tag and sends it as an `X-CSRFToken` header.

## Everyday features

- **Backfill a past day**: a date picker at the top of History (`GET /assessment?date=YYYY-MM-DD`)
  opens the normal one-question-at-a-time flow for that date. Future dates are rejected both
  client-side (`max` on the date input) and server-side (in the page route and the save API).
- **Edit / delete a past entry**: the detail page for any check-in has an "Edit" link (reopens
  the assessment for that date, pre-filled) and a "Delete" button (`POST
  /history/<id>/delete`, confirms before deleting, scoped to the signed-in user).
- **Export**: `/export/csv` and `/export/xlsx` (buttons on the History page) download every
  check-in — date, total score, severity, all 25 individual answers, and notes.

## Dark mode

Implemented with CSS custom properties rather than per-element `dark:` classes: `paper`,
`card`, `ink`, `ink-soft`, `ink-faint`, and `line` in the Tailwind config all resolve to
`var(--color-*)`, and `static/css/style.css` defines light values on `:root` and dark values
on `.dark`. That means every existing template that already used those color names picked up
dark mode automatically, with no per-file edits needed.

- A blocking inline script in `<head>` applies the right class before first paint (no flash of
  the wrong theme), using, in priority order: the signed-in user's saved `theme` preference,
  then `localStorage`, then the OS-level `prefers-color-scheme`.
- Preference is three-way (Light / Dark / System), set from Account → Appearance, and syncs
  across devices via `User.theme` (`POST /api/theme`) for signed-in users; `localStorage` covers
  the logged-out login/signup pages.
- A quick-toggle button (sun/moon icon) sits in the header on desktop and top-right on mobile
  for a one-tap flip between light and dark.

## Reminders (email + browser push)

Account → Reminders lets someone turn on an email nudge, a rough time of day, and — if the
server has Web Push configured — a browser push notification, all only firing on days they
haven't checked in yet.

**How sending works**: nothing runs on a timer inside the app itself (important for a
serverless deployment). Instead, `GET/POST /api/cron/send-reminders` is meant to be hit
periodically by an external scheduler. Each run finds users whose reminder time just passed
(within a 30-minute catch window, so a 15-minute cron cadence won't miss anyone), who haven't
completed today's check-in, and who haven't already been reminded today, then sends email
and/or push to each.

Protect it with a shared secret:

```
CRON_SECRET=some-long-random-string
```

The endpoint accepts the secret as `?key=...` or an `Authorization: Bearer ...` header, and
returns `503` if `CRON_SECRET` isn't set at all (reminders are fully off by default). The
included `vercel.json` already defines a cron hitting this endpoint every 15 minutes — Vercel
automatically sends the `Authorization: Bearer $CRON_SECRET` header for cron-triggered
requests when `CRON_SECRET` is set as an environment variable, so no secret needs to be
hardcoded in `vercel.json`.

**Browser push setup** (optional — the whole section stays hidden until this is configured):

```bash
python generate_vapid_keys.py
```

Set the three printed values as environment variables (`VAPID_PUBLIC_KEY`,
`VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_EMAIL`). Once set, "Enable" in Account → Reminders
registers `/sw.js` as a service worker, requests notification permission, and stores the
subscription (`PushSubscription` model) via `/api/push/subscribe`.

I was able to fully test the subscribe/unsubscribe endpoints, the cron auth, and the
"who's due for a reminder" selection logic (including the do-not-double-send and
already-checked-in-today cases) — all with fabricated data in this environment. I could
**not** test an actual push notification arriving in a real browser, since that needs a live
VAPID setup and an actual subscribed device; the `pywebpush` call is wrapped so a failed or
expired subscription just gets logged and skipped rather than breaking the batch, but you'll
want to confirm delivery yourself once it's deployed.

## Project structure

```
app.py                     Flask app, routes, dashboard/insight calculations
models.py                  SQLAlchemy User, Assessment, and PushSubscription models
questions.py                25-item question bank, categories, scoring, tone helpers
extensions.py               db + CSRFProtect instances (avoids circular imports)
email_utils.py              Token generation + email sending (SMTP or dev-mode log/flash)
oauth.py                    Google OAuth client setup, disabled gracefully if unconfigured
push_utils.py                Web Push (VAPID) sending, disabled gracefully if unconfigured
generate_vapid_keys.py      One-off script to generate a VAPID keypair
templates/                 Jinja2 templates (base.html for the app, auth_base.html for login/signup)
static/css/style.css       Small hand-written refinements on top of Tailwind
static/js/assessment.js    One-question-at-a-time flow, client-held answers
vercel.json                Deployment config for a single Vercel project
```

## Design notes

- **Palette**: warm sage-tinted paper background, moss green accent, a restrained
  warm-to-brick gradient for severity levels (amber → clay → brick → maroon) instead
  of a harsh red/green traffic-light scheme.
- **Type**: Inter throughout the UI; Fraunces reserved for the large score numerals
  on the result, home, and detail screens — one deliberate accent rather than a
  second typeface everywhere.
- **Assessment flow**: the 25 questions are rendered client-side from a JSON payload
  embedded in the page. Answers are held in memory in the browser and only sent to
  the server (`POST /api/assessments`) once all 25 are answered, so navigating back
  and forth never loses progress and there's a single round trip to save.
- **One question per screen**, a segmented (not solid) progress bar tied to the
  4 real categories, and a single subtle slide transition between questions —
  intentionally not animated further than that.

## Data model

`Assessment`: `id`, `assessment_date` (unique per day), `answers` (JSON, keys `"1"`–`"25"`),
`total_score`, `severity`, `notes`, `created_at`, `updated_at`.

## A note on sensitive content

Questions 23–25 (suicidal urges) show a brief supportive note while answering, and
the result/detail screens surface a calm message with the 988 Suicide & Crisis
Lifeline if any of those three items are answered above 0. This is a personal
tracking tool, not a diagnostic or clinical instrument — it's not a substitute for
professional care.

## Deploying

`vercel.json` is set up to run this as a single Python project. Note that SQLite on
Vercel's serverless filesystem is ephemeral — for a real deployment, swap the
`SQLALCHEMY_DATABASE_URI` for a hosted Postgres/MySQL instance (e.g. Vercel Postgres,
Neon, Supabase) via an environment variable; the SQLAlchemy models don't need to change.
