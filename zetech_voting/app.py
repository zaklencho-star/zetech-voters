import os
import sqlite3
import uuid
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, send_from_directory
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

from constants import COURSES, COURSE_BY_CODE, DOCKETS, is_valid_admission, normalize_admission
from database import get_db, init_db, now_iso, DEFAULT_ADMIN_USERNAME

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
PHOTO_SIZE = 480  # square thumbnail, px

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("ZETECH_SECRET_KEY", "dev-secret-change-me-before-deploying")
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # 6 MB upload ceiling
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------- helpers --

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_candidate_photo(file_storage):
    """Resize/crop the uploaded photo to a consistent square JPEG thumbnail
    and save it under static/uploads with a collision-proof filename."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        raise ValueError("Unsupported image type. Use PNG, JPG, GIF, or WEBP.")

    image = Image.open(file_storage.stream)
    image = ImageOps.exif_transpose(image)  # respect phone camera orientation
    image = image.convert("RGB")
    image = ImageOps.fit(image, (PHOTO_SIZE, PHOTO_SIZE), Image.LANCZOS)

    filename = f"{uuid.uuid4().hex}.jpg"
    dest = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image.save(dest, "JPEG", quality=87)
    return filename


def candidates_for_docket(conn, docket):
    return conn.execute(
        "SELECT * FROM candidates WHERE docket = ? ORDER BY name", (docket,)
    ).fetchall()


def active_dockets(conn):
    rows = conn.execute("SELECT DISTINCT docket FROM candidates").fetchall()
    present = {r["docket"] for r in rows}
    return [d for d in DOCKETS if d in present]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please sign in as the returning officer to continue.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def voter_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("voter_admission"):
            return redirect(url_for("voter_login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"dockets_all": DOCKETS, "courses_all": COURSES}


# ------------------------------------------------------------------ home --

@app.route("/")
def home():
    return render_template("home.html")


# ---------------------------------------------------------------- voting --

@app.route("/vote/login", methods=["GET", "POST"])
def voter_login():
    error = None
    admission_input = ""
    if request.method == "POST":
        admission_input = request.form.get("admission", "")
        admission = normalize_admission(admission_input)

        if not is_valid_admission(admission):
            error = "That doesn't look like a valid admission number. Use the format COURSECODE/NNNN/YY, e.g. BIRD/0124/25."
        else:
            conn = get_db()
            try:
                already = conn.execute(
                    "SELECT 1 FROM voted_admissions WHERE admission_number = ?", (admission,)
                ).fetchone()
                if already:
                    error = "This admission number has already cast a ballot in this election."
                else:
                    dockets = active_dockets(conn)
                    if not dockets:
                        error = "No candidates have been registered yet. Please check back later."
                    else:
                        session.clear()
                        session["voter_admission"] = admission
                        session["ballot_dockets"] = dockets
                        session["docket_index"] = 0
                        session["picks"] = {}
                        return redirect(url_for("ballot"))
            finally:
                conn.close()
    return render_template("voter_login.html", error=error, admission_input=admission_input)


@app.route("/vote/ballot")
@voter_required
def ballot():
    dockets = session.get("ballot_dockets", [])
    idx = session.get("docket_index", 0)
    if idx >= len(dockets):
        return redirect(url_for("review"))

    docket = dockets[idx]
    conn = get_db()
    try:
        candidates = candidates_for_docket(conn, docket)
    finally:
        conn.close()

    picks = session.get("picks", {})
    return render_template(
        "ballot.html",
        docket=docket,
        candidates=candidates,
        step_number=idx + 1,
        step_total=len(dockets),
        dockets=dockets,
        current_index=idx,
        selected_id=picks.get(docket),
        is_last=(idx == len(dockets) - 1),
    )


@app.route("/vote/select", methods=["POST"])
@voter_required
def select_candidate():
    dockets = session.get("ballot_dockets", [])
    idx = session.get("docket_index", 0)
    if idx >= len(dockets):
        return redirect(url_for("review"))
    docket = dockets[idx]

    candidate_id = request.form.get("candidate_id")
    direction = request.form.get("direction", "next")

    picks = session.get("picks", {})
    if candidate_id:
        picks[docket] = candidate_id
        session["picks"] = picks

    conn = get_db()
    try:
        has_candidates = len(candidates_for_docket(conn, docket)) > 0
    finally:
        conn.close()

    if direction == "back":
        session["docket_index"] = max(0, idx - 1)
        return redirect(url_for("ballot"))

    if has_candidates and docket not in picks:
        flash("Please select a candidate before continuing.", "error")
        return redirect(url_for("ballot"))

    session["docket_index"] = idx + 1
    if session["docket_index"] >= len(dockets):
        return redirect(url_for("review"))
    return redirect(url_for("ballot"))


@app.route("/vote/review")
@voter_required
def review():
    dockets = session.get("ballot_dockets", [])
    picks = session.get("picks", {})
    conn = get_db()
    try:
        rows = []
        for docket in dockets:
            cid = picks.get(docket)
            if not cid:
                continue
            cand = conn.execute("SELECT * FROM candidates WHERE id = ?", (cid,)).fetchone()
            if cand:
                rows.append({"docket": docket, "candidate": cand})
    finally:
        conn.close()
    return render_template("review.html", rows=rows)


@app.route("/vote/edit")
@voter_required
def edit_ballot():
    dockets = session.get("ballot_dockets", [])
    session["docket_index"] = max(0, len(dockets) - 1)
    return redirect(url_for("ballot"))


@app.route("/vote/cast", methods=["POST"])
@voter_required
def cast_vote():
    admission = session["voter_admission"]
    picks = session.get("picks", {})

    conn = get_db()
    try:
        already = conn.execute(
            "SELECT 1 FROM voted_admissions WHERE admission_number = ?", (admission,)
        ).fetchone()
        if already:
            flash("This admission number has already voted.", "error")
            session.clear()
            return redirect(url_for("voter_login"))

        try:
            conn.execute(
                "INSERT INTO voted_admissions (admission_number, voted_at) VALUES (?, ?)",
                (admission, now_iso()),
            )
            for candidate_id in picks.values():
                conn.execute(
                    "UPDATE candidates SET votes = votes + 1 WHERE id = ?", (candidate_id,)
                )
            conn.commit()
        except sqlite3.IntegrityError:
            # Someone raced us with the same admission number between the check and the insert.
            conn.rollback()
            flash("This admission number has already voted.", "error")
            session.clear()
            return redirect(url_for("voter_login"))
    finally:
        conn.close()

    dockets_voted = len(picks)
    session.clear()
    session["last_receipt"] = {"admission": admission, "dockets_voted": dockets_voted}
    return redirect(url_for("voter_done"))


@app.route("/vote/done")
def voter_done():
    receipt = session.pop("last_receipt", None)
    if not receipt:
        return redirect(url_for("home"))
    return render_template("done.html", receipt=receipt, now=now_iso())


# ------------------------------------------------------------------ admin --

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        try:
            user = conn.execute(
                "SELECT * FROM admin_users WHERE username = ?", (username,)
            ).fetchone()
        finally:
            conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["is_admin"] = True
            session["admin_username"] = username
            return redirect(url_for("admin_candidates"))
        error = "Incorrect username or passcode."
    return render_template("admin_login.html", error=error, default_username=DEFAULT_ADMIN_USERNAME)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_username", None)
    return redirect(url_for("home"))


@app.route("/admin/candidates", methods=["GET", "POST"])
@admin_required
def admin_candidates():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        docket = request.form.get("docket", "")
        course_code = request.form.get("course_code", "")

        if not name:
            flash("Please enter the candidate's full name.", "error")
        elif docket not in DOCKETS:
            flash("Please choose a valid docket.", "error")
        elif course_code not in COURSE_BY_CODE:
            flash("Please choose a valid course.", "error")
        else:
            try:
                photo_filename = save_candidate_photo(request.files.get("photo"))
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_candidates"))

            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO candidates (name, docket, course_code, photo_filename, votes, created_at) "
                    "VALUES (?, ?, ?, ?, 0, ?)",
                    (name, docket, course_code, photo_filename, now_iso()),
                )
                conn.commit()
            finally:
                conn.close()
            flash(f"{name} was added to the {docket} ballot.", "success")
        return redirect(url_for("admin_candidates"))

    conn = get_db()
    try:
        candidates = conn.execute(
            "SELECT * FROM candidates ORDER BY docket, name"
        ).fetchall()
    finally:
        conn.close()
    return render_template(
        "admin_candidates.html",
        candidates=candidates,
        dockets=DOCKETS,
        courses=COURSES,
        active_tab="candidates",
    )


@app.route("/admin/candidates/<int:candidate_id>/delete", methods=["POST"])
@admin_required
def admin_delete_candidate(candidate_id):
    conn = get_db()
    try:
        cand = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        if cand:
            conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
            conn.commit()
            if cand["photo_filename"]:
                path = os.path.join(app.config["UPLOAD_FOLDER"], cand["photo_filename"])
                if os.path.exists(path):
                    os.remove(path)
            flash(f"{cand['name']} was removed from the ballot.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_candidates"))


@app.route("/admin/results")
@admin_required
def admin_results():
    conn = get_db()
    try:
        candidates = conn.execute("SELECT * FROM candidates").fetchall()
        total_voters = conn.execute("SELECT COUNT(*) AS n FROM voted_admissions").fetchone()["n"]
    finally:
        conn.close()

    total_votes = sum(c["votes"] for c in candidates)
    results_by_docket = []
    for docket in DOCKETS:
        cands = sorted(
            [c for c in candidates if c["docket"] == docket],
            key=lambda c: c["votes"], reverse=True
        )
        if not cands:
            continue
        docket_total = sum(c["votes"] for c in cands) or 1
        top_votes = cands[0]["votes"]
        rows = [{
            "candidate": c,
            "pct": round((c["votes"] / docket_total) * 100),
            "is_leader": c["votes"] == top_votes and top_votes > 0,
        } for c in cands]
        results_by_docket.append({"docket": docket, "rows": rows})

    return render_template(
        "admin_results.html",
        total_candidates=len(candidates),
        total_votes=total_votes,
        total_voters=total_voters,
        results_by_docket=results_by_docket,
        active_tab="results",
    )


@app.route("/admin/settings")
@admin_required
def admin_settings():
    return render_template("admin_settings.html", courses=COURSES, active_tab="settings")


@app.route("/admin/reset", methods=["POST"])
@admin_required
def admin_reset():
    confirm_phrase = request.form.get("confirm_phrase", "")
    if confirm_phrase != "RESET ELECTION":
        flash('Type "RESET ELECTION" exactly to confirm this action.', "error")
        return redirect(url_for("admin_settings"))

    conn = get_db()
    try:
        photos = [r["photo_filename"] for r in conn.execute("SELECT photo_filename FROM candidates").fetchall()]
        conn.execute("DELETE FROM candidates")
        conn.execute("DELETE FROM voted_admissions")
        conn.commit()
    finally:
        conn.close()

    for filename in photos:
        if filename:
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if os.path.exists(path):
                os.remove(path)

    flash("The election has been fully reset.", "success")
    return redirect(url_for("admin_settings"))


@app.route("/admin/password", methods=["POST"])
@admin_required
def admin_change_password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM admin_users WHERE username = ?", (session["admin_username"],)
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            flash("Current passcode is incorrect.", "error")
        elif len(new) < 8:
            flash("New passcode must be at least 8 characters.", "error")
        elif new != confirm:
            flash("New passcode and confirmation do not match.", "error")
        else:
            conn.execute(
                "UPDATE admin_users SET password_hash = ? WHERE username = ?",
                (generate_password_hash(new), session["admin_username"]),
            )
            conn.commit()
            flash("Passcode updated successfully.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_settings"))


# ------------------------------------------------------------- entrypoint --

init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
