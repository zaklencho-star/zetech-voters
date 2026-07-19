# Zetech University — Student Elections Portal

A real Flask + SQLite web app (not a mockup). Server-rendered pages, a proper
relational schema, hashed admin credentials, and transactional vote-casting
so a student can't double-vote even under a race condition.

## Stack
- **Backend:** Flask 3, plain `sqlite3` (stdlib) — no ORM
- **Images:** Pillow — every candidate photo is server-side resized/cropped
  to a 480×480 JPEG on upload, regardless of what the admin uploads
- **Auth:** Werkzeug password hashing for the admin account; server-side
  session for both the voter's in-progress ballot and the admin login
- **Frontend:** Jinja2 templates, no JS framework, one shared stylesheet

## Setup

```bash
cd zetech_voting
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Visit `http://localhost:5000`. The SQLite database and admin account are
created automatically on first run at `instance/zetech_voting.sqlite3`.

**Default admin login:** username `returning_officer`, passcode
`ZetechVotes2026`. Change it immediately from Admin → Settings.

## How voting is locked down

- **Admission number format** — validated against a regex built from every
  course code in `constants.py`: `CODE/NNNN/YY` (e.g. `BIRD/0124/25`). Add or
  remove programmes there and the whole system (validation, dropdowns,
  settings page) updates automatically.
- **One vote per admission number** — enforced twice: once as an application
  check, and again as a `PRIMARY KEY` on `voted_admissions`, so even two
  simultaneous submissions from the same admission number can't both
  succeed (the second hits an `IntegrityError` and is rejected).
- **Ballot state lives server-side in the session**, not in the page, so it
  can't be tampered with by editing form fields in the browser.
- **Admin routes** are all gated behind `@admin_required`; passwords are
  hashed with `werkzeug.security`, never stored in plaintext.

## Project layout

```
app.py                  routes & request handling
constants.py             course codes, dockets, admission regex — edit here
database.py               schema + connection helper (plain sqlite3)
templates/                Jinja2 pages
static/css/style.css     shared stylesheet
static/uploads/           candidate photos (created automatically)
instance/                 SQLite database file (created automatically)
```

## Production notes (read before a real election)

This is built to run correctly, but a couple of things are left as
deliberate configuration steps rather than baked in, since they depend on
your deployment:

1. **Set a real `SECRET_KEY`** via the `ZETECH_SECRET_KEY` environment
   variable — don't rely on the fallback dev key in `app.py`.
2. **Run behind a real WSGI server** (gunicorn/uwsgi) and HTTPS, not
   `python app.py`'s dev server.
3. **Add CSRF protection** (e.g. Flask-WTF) if this will be exposed beyond a
   trusted campus network — the forms here don't currently carry CSRF
   tokens.
4. **Back up `instance/zetech_voting.sqlite3`** before using the Settings →
   Reset Election button — it is irreversible by design.
