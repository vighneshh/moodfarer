import os
import re
import csv
import io
from datetime import date, timedelta, datetime

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask,
    app,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    Response,
    send_from_directory,
    current_app,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from extensions import db, csrf
from oauth import oauth, init_oauth, google_configured
from models import User, Assessment, PushSubscription, RewirementCheckin
from email_utils import (
    send_verification_email,
    send_password_reset_email,
    send_email,
    confirm_token,
    smtp_configured,
    VERIFY_SALT,
    RESET_SALT,
    VERIFY_MAX_AGE,
    RESET_MAX_AGE,
)
from push_utils import push_configured, vapid_public_key, send_push

from rewirements import REWIREMENTS, WEEKDAY_KEYS, WEEKDAY_LABELS, rewirement_for

from questions import (
    QUESTIONS,
    CATEGORIES,
    ANSWER_SCALE,
    category_for,
    category_name,
    severity_for,
    severity_tone,
    has_urgent_flags,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

    if os.environ.get("APP_ENV") == "development":
        db_path = os.environ.get("DATABASE_PATH", os.path.join("/tmp", "checkin.db"))
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_SORT_KEYS"] = False

    # Cookies: secure defaults. SESSION_COOKIE_SECURE is left off for local http
    # dev and should be forced on in production (e.g. behind HTTPS on Vercel).
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FORCE_HTTPS", "false").lower() == "true"

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    init_oauth(app)

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_globals():
        return {
            "google_configured": google_configured(),
            "push_configured": push_configured(),
        }

    register_routes(app)
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_streak(all_dates_set):
    if not all_dates_set:
        return 0
    today = date.today()
    cursor = today if today in all_dates_set else today - timedelta(days=1)
    streak = 0
    while cursor in all_dates_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_dashboard_stats(user_id):
    assessments = (
        Assessment.query.filter_by(user_id=user_id)
        .order_by(Assessment.assessment_date.asc())
        .all()
    )
    by_date = {a.assessment_date: a for a in assessments}

    today = date.today()
    today_assessment = by_date.get(today)

    sorted_desc = sorted(assessments, key=lambda a: a.assessment_date, reverse=True)
    previous_assessment = None
    for a in sorted_desc:
        if a.assessment_date != today:
            previous_assessment = a
            break

    last_7_cutoff = today - timedelta(days=6)
    last_30_cutoff = today - timedelta(days=29)

    last_7 = [a for a in assessments if a.assessment_date >= last_7_cutoff]
    last_30 = [a for a in assessments if a.assessment_date >= last_30_cutoff]

    avg_7 = round(sum(a.total_score for a in last_7) / len(last_7)) if last_7 else None
    avg_30 = round(sum(a.total_score for a in last_30) / len(last_30)) if last_30 else None

    scores = [a.total_score for a in assessments]

    return {
        "today": today_assessment,
        "previous": previous_assessment,
        "avg_7": avg_7,
        "avg_30": avg_30,
        "completed_7": len(last_7),
        "total_count": len(assessments),
        "streak": compute_streak(set(by_date.keys())),
        "highest": max(scores) if scores else None,
        "lowest": min(scores) if scores else None,
    }


def trend_series(user_id, days: int):
    cutoff = date.today() - timedelta(days=days - 1)
    assessments = (
        Assessment.query.filter(
            Assessment.user_id == user_id, Assessment.assessment_date >= cutoff
        )
        .order_by(Assessment.assessment_date.asc())
        .all()
    )
    return {
        "labels": [a.assessment_date.strftime("%b %-d") for a in assessments],
        "scores": [a.total_score for a in assessments],
        "dates": [a.assessment_date.isoformat() for a in assessments],
    }


def category_breakdown(assessment: Assessment):
    answers = assessment.answers
    breakdown = []
    for cat in CATEGORIES:
        lo, hi = cat["range"]
        vals = [answers.get(i) for i in range(lo, hi + 1) if answers.get(i) is not None]
        avg = round(sum(vals) / len(vals), 1) if vals else 0
        breakdown.append({"name": cat["name"], "key": cat["key"], "average": avg, "max": 4})
    return breakdown


def insights_data(user_id):
    assessments = (
        Assessment.query.filter_by(user_id=user_id)
        .order_by(Assessment.assessment_date.asc())
        .all()
    )
    if not assessments:
        return None

    n_cats = {c["key"]: {"name": c["name"], "total": 0, "count": 0} for c in CATEGORIES}
    for a in assessments:
        answers = a.answers
        for cat in CATEGORIES:
            lo, hi = cat["range"]
            vals = [answers.get(i) for i in range(lo, hi + 1) if answers.get(i) is not None]
            if vals:
                n_cats[cat["key"]]["total"] += sum(vals)
                n_cats[cat["key"]]["count"] += len(vals)

    category_averages = []
    for key, d in n_cats.items():
        avg = round(d["total"] / d["count"], 1) if d["count"] else 0
        category_averages.append({"key": key, "name": d["name"], "average": avg})

    q_totals = {q["id"]: [] for q in QUESTIONS}
    for a in assessments:
        for qid, val in a.answers.items():
            if qid in q_totals:
                q_totals[qid].append(val)

    question_averages = []
    for q in QUESTIONS:
        vals = q_totals[q["id"]]
        if vals:
            question_averages.append(
                {
                    "id": q["id"],
                    "text": q["text"],
                    "category": category_name(q["category"]),
                    "average": round(sum(vals) / len(vals), 2),
                }
            )
    top_challenges = sorted(question_averages, key=lambda x: x["average"], reverse=True)[:5]

    scores = [a.total_score for a in assessments]
    best = min(assessments, key=lambda a: a.total_score)
    hardest = max(assessments, key=lambda a: a.total_score)

    today = date.today()
    window = [today - timedelta(days=i) for i in range(29, -1, -1)]
    done_dates = {a.assessment_date for a in assessments}
    consistency = [1 if d in done_dates else 0 for d in window]

    return {
        "category_averages": category_averages,
        "top_challenges": top_challenges,
        "overall_average": round(sum(scores) / len(scores), 1),
        "best": best,
        "hardest": hardest,
        "consistency": consistency,
        "consistency_labels": [d.strftime("%b %-d") for d in window],
        "total_count": len(assessments),
    }


def rewirement_insights(user_id):
    rows = RewirementCheckin.query.filter_by(user_id=user_id).all()
    if not rows:
        return None

    weeks_logged = len({r.week_start for r in rows})
    by_practice = {}
    for rw in REWIREMENTS:
        practice_rows = [r for r in rows if r.rewirement_key == rw["key"]]
        done = sum(1 for r in practice_rows if r.completed)
        possible = weeks_logged * len(day_keys_for(rw))
        by_practice[rw["key"]] = {
            "title": rw["title"],
            "done": done,
            "rate": round(done / possible * 100) if possible else 0,
        }

    total_done = sum(1 for r in rows if r.completed)
    total_possible = weeks_logged * sum(len(day_keys_for(rw)) for rw in REWIREMENTS)

    return {
        "weeks_logged": weeks_logged,
        "total_done": total_done,
        "overall_rate": round(total_done / total_possible * 100) if total_possible else 0,
        "by_practice": sorted(by_practice.values(), key=lambda x: x["rate"], reverse=True),
    }


def flash_dev_link(prefix: str, sent: bool, link: str):
    """When SMTP isn't configured, surface the link directly so the flow is
    fully testable without a real mail server."""
    if not sent:
        flash(f"{prefix} (dev mode — no SMTP configured, so here's the link): {link}", "info")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def users_due_for_reminder(now: datetime = None, window_minutes: int = 30):
    """Users who: opted into email and/or push reminders, whose reminder_time
    has just passed (within `window_minutes`), haven't completed today's
    check-in yet, and haven't already been reminded today."""
    now = now or datetime.now()
    today = now.date()
    now_minutes = now.hour * 60 + now.minute

    due = []
    candidates = User.query.filter(
        db.or_(User.reminder_email_enabled.is_(True), User.reminder_push_enabled.is_(True))
    ).all()

    for user in candidates:
        if user.reminder_last_sent == today:
            continue
        if not TIME_RE.match(user.reminder_time or ""):
            continue

        target_minutes = _minutes(user.reminder_time)
        elapsed = now_minutes - target_minutes
        if elapsed < 0 or elapsed > window_minutes:
            continue

        already_done = Assessment.query.filter_by(
            user_id=user.id, assessment_date=today
        ).first()
        if already_done:
            continue

        due.append(user)

    return due


def build_export_rows(user_id):
    assessments = (
        Assessment.query.filter_by(user_id=user_id)
        .order_by(Assessment.assessment_date.asc())
        .all()
    )
    header = ["date", "total_score", "severity"] + [f"q{q['id']}" for q in QUESTIONS] + ["notes"]
    rows = [header]
    for a in assessments:
        answers = a.answers
        row = [a.assessment_date.isoformat(), a.total_score, a.severity]
        row += [answers.get(q["id"], "") for q in QUESTIONS]
        row += [a.notes or ""]
        rows.append(row)
    return rows


def week_start_for(d: date) -> date:
    """The Sunday that starts the week containing d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def day_keys_for(rewirement: dict):
    if rewirement["type"] == "binary":
        return [o["key"] for o in rewirement["options"]]
    return WEEKDAY_KEYS


def get_rewirement_week_cards(user_id, week_start: date):
    rows = RewirementCheckin.query.filter_by(user_id=user_id, week_start=week_start).all()
    by_key = {(r.rewirement_key, r.day_key): r for r in rows}

    cards = []
    for rw in REWIREMENTS:
        days = []
        done_count = 0
        for dk in day_keys_for(rw):
            row = by_key.get((rw["key"], dk))
            completed = bool(row and row.completed)
            if completed:
                done_count += 1
            label = WEEKDAY_LABELS.get(dk, dk.title()) if rw["type"] == "week" else next(
                o["label"] for o in rw["options"] if o["key"] == dk
            )
            days.append({
                "key": dk,
                "label": label,
                "completed": completed,
                "note": row.note if row else "",
            })
        cards.append({
            **rw,
            "days": days,
            "done_count": done_count,
            "total_count": len(days),
        })
    return cards


def get_rewirement_week_summary(user_id, week_start: date):
    rows = RewirementCheckin.query.filter_by(user_id=user_id, week_start=week_start, completed=True).all()
    done = len(rows)
    total = sum(len(day_keys_for(rw)) for rw in REWIREMENTS)
    return {"done": done, "total": total}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app):

    # -------------------------------------------------------------
    # Signup / login / logout
    # -------------------------------------------------------------

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("home"))

        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm_password") or ""

            error = None
            if not name:
                error = "Please tell us what to call you."
            elif not EMAIL_RE.match(email):
                error = "That doesn't look like a valid email address."
            elif len(password) < 8:
                error = "Your password needs to be at least 8 characters."
            elif password != confirm:
                error = "Those passwords don't match."
            elif User.query.filter_by(email=email).first():
                error = "An account with that email already exists."

            if error:
                flash(error, "error")
                return render_template("signup.html", name=name, email=email), 400

            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            sent, link = send_verification_email(user)
            flash("Account created. We've sent a verification link to your email.", "success")
            flash_dev_link("Verify your email", sent, link)

            login_user(user)
            return redirect(url_for("home"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("home"))

        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            remember = bool(request.form.get("remember"))

            user = User.query.filter_by(email=email).first()
            if user is None or not user.check_password(password):
                flash("Incorrect email or password.", "error")
                return render_template("login.html", email=email), 401

            login_user(user, remember=remember)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("home"))

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # -------------------------------------------------------------
    # Email verification
    # -------------------------------------------------------------

    @app.route("/verify-email/<token>")
    def verify_email(token):
        email = confirm_token(token, VERIFY_SALT, VERIFY_MAX_AGE)
        if email is None:
            flash("That verification link is invalid or has expired.", "error")
            return redirect(url_for("login"))

        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("We couldn't find that account.", "error")
            return redirect(url_for("login"))

        user.email_verified = True
        db.session.commit()
        flash("Your email is verified. Thanks!", "success")
        return redirect(url_for("home") if current_user.is_authenticated else url_for("login"))

    @app.route("/resend-verification", methods=["POST"])
    @login_required
    def resend_verification():
        if current_user.email_verified:
            flash("Your email is already verified.", "info")
        else:
            sent, link = send_verification_email(current_user)
            flash("Verification email sent.", "success")
            flash_dev_link("Verify your email", sent, link)
        return redirect(request.referrer or url_for("home"))

    # -------------------------------------------------------------
    # Forgot / reset password
    # -------------------------------------------------------------

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            user = User.query.filter_by(email=email).first()

            # Always show the same message, whether or not the account exists,
            # so this endpoint can't be used to enumerate registered emails.
            if user and user.has_password:
                sent, link = send_password_reset_email(user)
                flash_dev_link("Reset your password", sent, link)
            elif user and not user.has_password:
                flash(
                    "That account signs in with Google. Use \u201cSign in with Google\u201d instead.",
                    "info",
                )
                return render_template("forgot_password.html", email=email)

            flash("If an account exists for that email, we've sent a reset link.", "success")
            return redirect(url_for("login"))

        return render_template("forgot_password.html")

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        email = confirm_token(token, RESET_SALT, RESET_MAX_AGE)
        if email is None:
            flash("That reset link is invalid or has expired.", "error")
            return redirect(url_for("forgot_password"))

        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("We couldn't find that account.", "error")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm_password") or ""

            if len(password) < 8:
                flash("Your password needs to be at least 8 characters.", "error")
                return render_template("reset_password.html", token=token)
            if password != confirm:
                flash("Those passwords don't match.", "error")
                return render_template("reset_password.html", token=token)

            user.set_password(password)
            db.session.commit()
            flash("Your password has been reset. Please sign in.", "success")
            return redirect(url_for("login"))

        return render_template("reset_password.html", token=token)

    # -------------------------------------------------------------
    # Google OAuth
    # -------------------------------------------------------------

    @app.route("/auth/google")
    def auth_google():
        if not google_configured():
            flash("Google sign-in isn't configured yet.", "error")
            return redirect(url_for("login"))
        redirect_uri = url_for("auth_google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/google/callback")
    def auth_google_callback():
        if not google_configured():
            return redirect(url_for("login"))

        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo") or oauth.google.userinfo()
        google_id = userinfo["sub"]
        email = userinfo["email"].lower()
        name = userinfo.get("name") or email.split("@")[0]

        user = User.query.filter_by(google_id=google_id).first()
        if user is None:
            user = User.query.filter_by(email=email).first()
            if user is not None:
                # An account with this email already exists (password-based).
                # Link the Google identity to it rather than creating a duplicate.
                user.google_id = google_id
            else:
                user = User(name=name, email=email, google_id=google_id)
                db.session.add(user)

        if userinfo.get("email_verified"):
            user.email_verified = True

        db.session.commit()
        login_user(user)
        return redirect(url_for("home"))

    # -------------------------------------------------------------
    # Account settings
    # -------------------------------------------------------------

    @app.route("/account", methods=["GET", "POST"])
    @login_required
    def account():
        if request.method == "POST":
            action = request.form.get("action")

            if action == "update_profile":
                name = (request.form.get("name") or "").strip()
                email = (request.form.get("email") or "").strip().lower()

                if not name:
                    flash("Please enter a name.", "error")
                elif not EMAIL_RE.match(email):
                    flash("That doesn't look like a valid email address.", "error")
                elif email != current_user.email and User.query.filter_by(email=email).first():
                    flash("That email is already in use.", "error")
                else:
                    email_changed = email != current_user.email
                    current_user.name = name
                    current_user.email = email
                    if email_changed:
                        current_user.email_verified = False
                    db.session.commit()
                    flash("Profile updated.", "success")
                    if email_changed:
                        sent, link = send_verification_email(current_user)
                        flash("We've sent a verification link to your new email.", "info")
                        flash_dev_link("Verify your email", sent, link)

            elif action == "change_password":
                current_password = request.form.get("current_password") or ""
                new_password = request.form.get("new_password") or ""
                confirm = request.form.get("confirm_new_password") or ""

                if current_user.has_password and not current_user.check_password(current_password):
                    flash("Your current password is incorrect.", "error")
                elif len(new_password) < 8:
                    flash("Your new password needs to be at least 8 characters.", "error")
                elif new_password != confirm:
                    flash("Those passwords don't match.", "error")
                else:
                    current_user.set_password(new_password)
                    db.session.commit()
                    flash("Password updated.", "success")

            elif action == "delete_account":
                confirm_email = (request.form.get("confirm_email") or "").strip().lower()
                if confirm_email != current_user.email.lower():
                    flash("Type your email exactly to confirm account deletion.", "error")
                else:
                    user = current_user._get_current_object()
                    logout_user()
                    db.session.delete(user)
                    db.session.commit()
                    flash("Your account and all your data have been deleted.", "success")
                    return redirect(url_for("signup"))

            elif action == "update_reminders":
                reminder_time = (request.form.get("reminder_time") or "19:00").strip()
                if not TIME_RE.match(reminder_time):
                    flash("Please choose a valid time.", "error")
                else:
                    current_user.reminder_email_enabled = bool(request.form.get("reminder_email_enabled"))
                    current_user.reminder_time = reminder_time
                    db.session.commit()
                    flash("Reminder settings saved.", "success")

            return redirect(url_for("account"))

        return render_template("account.html", smtp_configured=smtp_configured())

    # -------------------------------------------------------------
    # Theme preference
    # -------------------------------------------------------------

    @app.route("/api/theme", methods=["POST"])
    @login_required
    def set_theme():
        payload = request.get_json(force=True, silent=True) or {}
        theme = payload.get("theme")
        if theme not in ("light", "dark", "system"):
            return jsonify({"error": "Invalid theme."}), 400
        current_user.theme = theme
        db.session.commit()
        return jsonify({"theme": theme})

    # -------------------------------------------------------------
    # Web push
    # -------------------------------------------------------------

    @app.route("/sw.js")
    def service_worker():
        # Served at the root (not /static/sw.js) so its default scope covers
        # the whole app, not just /static/.
        return send_from_directory(
            os.path.join(BASE_DIR, "static"), "sw.js", mimetype="application/javascript"
        )

    @app.route("/api/push/public-key")
    @login_required
    def push_public_key():
        return jsonify({"publicKey": vapid_public_key() if push_configured() else None})

    @app.route("/api/push/subscribe", methods=["POST"])
    @login_required
    def push_subscribe():
        payload = request.get_json(force=True, silent=True) or {}
        endpoint = payload.get("endpoint")
        p256dh = payload.get("p256dh")
        auth = payload.get("auth")
        if not (endpoint and p256dh and auth):
            return jsonify({"error": "Invalid subscription."}), 400

        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existing is None:
            existing = PushSubscription(user_id=current_user.id, endpoint=endpoint)
            db.session.add(existing)
        existing.user_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth

        current_user.reminder_push_enabled = True
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/push/unsubscribe", methods=["POST"])
    @login_required
    def push_unsubscribe():
        payload = request.get_json(force=True, silent=True) or {}
        endpoint = payload.get("endpoint")
        if endpoint:
            PushSubscription.query.filter_by(
                endpoint=endpoint, user_id=current_user.id
            ).delete()
        remaining = PushSubscription.query.filter_by(user_id=current_user.id).count()
        if remaining == 0:
            current_user.reminder_push_enabled = False
        db.session.commit()
        return jsonify({"ok": True})

    # -------------------------------------------------------------
    # Reminder cron endpoint (called by an external scheduler)
    # -------------------------------------------------------------

    @app.route("/api/cron/send-reminders", methods=["GET", "POST"])
    def send_reminders():
        secret = os.environ.get("CRON_SECRET")
        if not secret:
            return jsonify({"error": "Reminders are not configured on this server."}), 503

        provided = request.args.get("key") or (
            request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        if provided != secret:
            return jsonify({"error": "Unauthorized."}), 403

        due = users_due_for_reminder()
        reminded = 0
        for user in due:
            sent_any = False

            if user.reminder_email_enabled:
                try:
                    send_email(
                        "A gentle nudge — Daily Check-in",
                        user.email,
                        f"Hi {user.name},\n\nJust a reminder to complete today's check-in "
                        f"whenever you have a few minutes.\n\n{url_for('home', _external=True)}",
                    )
                    sent_any = True
                except Exception:  # noqa: BLE001 - one bad send shouldn't stop the batch
                    current_app.logger.exception("Reminder email failed for user %s", user.id)

            if user.reminder_push_enabled:
                for sub in user.push_subscriptions:
                    ok = send_push(
                        sub.to_subscription_info(),
                        "Daily Check-in",
                        "Don't forget today's check-in.",
                        url_for("home"),
                    )
                    sent_any = sent_any or ok

            if sent_any:
                user.reminder_last_sent = date.today()
                reminded += 1

        db.session.commit()
        return jsonify({"checked": len(due), "reminded": reminded})

    # -------------------------------------------------------------
    # Export
    # -------------------------------------------------------------

    @app.route("/export/csv")
    @login_required
    def export_csv():
        rows = build_export_rows(current_user.id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerows(rows)
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=checkin-history-{date.today().isoformat()}.csv"
            },
        )

    @app.route("/export/xlsx")
    @login_required
    def export_xlsx():
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter

        rows = build_export_rows(current_user.id)
        wb = Workbook()
        ws = wb.active
        ws.title = "Check-ins"
        for row in rows:
            ws.append(row)
        for col_idx in range(1, len(rows[0]) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 12

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            buf.read(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=checkin-history-{date.today().isoformat()}.xlsx"
            },
        )

    @app.route("/rewire")
    @login_required
    def rewire():
        week_param = request.args.get("week")
        current_week = week_start_for(date.today())
        try:
            week_start = (
                datetime.strptime(week_param, "%Y-%m-%d").date() if week_param else current_week
            )
        except ValueError:
            week_start = current_week
        week_start = week_start_for(week_start)
        if week_start > current_week:
            week_start = current_week

        cards = get_rewirement_week_cards(current_user.id, week_start)
        return render_template(
            "rewire.html",
            cards=cards,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            prev_week=(week_start - timedelta(days=7)).isoformat(),
            next_week=(week_start + timedelta(days=7)).isoformat(),
            is_current_week=week_start == current_week,
            is_future_next=week_start + timedelta(days=7) > current_week,
            strengths=current_user.signature_strengths,
        )

    @app.route("/rewire/history")
    @login_required
    def rewire_history():
        week_rows = (
            db.session.query(RewirementCheckin.week_start)
            .filter_by(user_id=current_user.id, completed=True)
            .distinct()
            .order_by(RewirementCheckin.week_start.desc())
            .all()
        )
        weeks = []
        for (ws,) in week_rows:
            summary = get_rewirement_week_summary(current_user.id, ws)
            weeks.append({"week_start": ws, "week_end": ws + timedelta(days=6), **summary})
        return render_template("rewire_history.html", weeks=weeks)

    @app.route("/api/rewire/toggle", methods=["POST"])
    @login_required
    def rewire_toggle():
        payload = request.get_json(force=True, silent=True) or {}
        key = payload.get("rewirement_key")
        day_key = payload.get("day_key")
        week_param = payload.get("week_start")

        rw = rewirement_for(key)
        if rw is None or day_key not in day_keys_for(rw):
            return jsonify({"error": "Invalid practice or day."}), 400

        try:
            week_start = datetime.strptime(week_param, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid week."}), 400
        week_start = week_start_for(week_start)
        if week_start > week_start_for(date.today()):
            return jsonify({"error": "Can't log a future week."}), 400

        row = RewirementCheckin.query.filter_by(
            user_id=current_user.id, rewirement_key=key, week_start=week_start, day_key=day_key
        ).first()
        if row is None:
            row = RewirementCheckin(
                user_id=current_user.id, rewirement_key=key, week_start=week_start, day_key=day_key,
                completed=True,
            )
            db.session.add(row)
        else:
            row.completed = not row.completed
        db.session.commit()
        return jsonify({"completed": row.completed})

    @app.route("/api/rewire/note", methods=["POST"])
    @login_required
    def rewire_note():
        payload = request.get_json(force=True, silent=True) or {}
        key = payload.get("rewirement_key")
        day_key = payload.get("day_key")
        week_param = payload.get("week_start")
        note = (payload.get("note") or "").strip()[:1000]

        rw = rewirement_for(key)
        if rw is None or day_key not in day_keys_for(rw):
            return jsonify({"error": "Invalid practice or day."}), 400

        try:
            week_start = datetime.strptime(week_param, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid week."}), 400
        week_start = week_start_for(week_start)

        row = RewirementCheckin.query.filter_by(
            user_id=current_user.id, rewirement_key=key, week_start=week_start, day_key=day_key
        ).first()
        if row is None:
            row = RewirementCheckin(
                user_id=current_user.id, rewirement_key=key, week_start=week_start, day_key=day_key,
                completed=False,
            )
            db.session.add(row)
        row.note = note
        db.session.commit()
        return jsonify({"note": row.note})

    @app.route("/rewire/strengths", methods=["POST"])
    @login_required
    def rewire_strengths():
        strengths = [
            (request.form.get(f"strength_{i}") or "").strip()[:120] for i in range(1, 5)
        ]
        current_user.signature_strengths = strengths
        db.session.commit()
        flash("Signature strengths saved.", "success")
        return redirect(url_for("rewire"))

    # -------------------------------------------------------------
    # App routes (all require a signed-in user, all scoped to that user)
    # -------------------------------------------------------------

    @app.route("/")
    @login_required
    def home():
        stats = get_dashboard_stats(current_user.id)
        trend = trend_series(current_user.id, 7)
        rewire_summary = get_rewirement_week_summary(current_user.id, week_start_for(date.today()))
        return render_template(
            "home.html",
            stats=stats,
            trend=trend,
            today=date.today(),
            rewire_summary=rewire_summary,
        )

    @app.route("/assessment")
    @login_required
    def assessment():
        target_date_str = request.args.get("date")
        target_date = (
            datetime.strptime(target_date_str, "%Y-%m-%d").date()
            if target_date_str
            else date.today()
        )
        if target_date > date.today():
            flash("You can't log a check-in for a future date.", "error")
            return redirect(url_for("home"))

        existing = Assessment.query.filter_by(
            user_id=current_user.id, assessment_date=target_date
        ).first()
        existing_answers = existing.answers if existing else {}

        return render_template(
            "assessment.html",
            questions=QUESTIONS,
            answer_scale=ANSWER_SCALE,
            categories={c["key"]: c["name"] for c in CATEGORIES},
            existing_answers=existing_answers,
            target_date=target_date.isoformat(),
            target_date_display=target_date.strftime("%A, %B %-d"),
            is_today=target_date == date.today(),
            is_update=existing is not None,
        )

    @app.route("/api/assessments", methods=["POST"])
    @login_required
    def save_assessment():
        payload = request.get_json(force=True, silent=True) or {}
        answers = payload.get("answers", {})
        target_date_str = payload.get("date")

        if len(answers) != len(QUESTIONS):
            return jsonify({"error": "All 25 questions must be answered."}), 400

        try:
            answers_int = {int(k): int(v) for k, v in answers.items()}
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid answer format."}), 400

        for v in answers_int.values():
            if v < 0 or v > 4:
                return jsonify({"error": "Answer values must be between 0 and 4."}), 400

        target_date = (
            datetime.strptime(target_date_str, "%Y-%m-%d").date()
            if target_date_str
            else date.today()
        )
        if target_date > date.today():
            return jsonify({"error": "You can't log a check-in for a future date."}), 400

        total_score = sum(answers_int.values())
        severity = severity_for(total_score)

        record = Assessment.query.filter_by(
            user_id=current_user.id, assessment_date=target_date
        ).first()
        if record is None:
            record = Assessment(user_id=current_user.id, assessment_date=target_date)
            db.session.add(record)

        record.answers = answers_int
        record.total_score = total_score
        record.severity = severity
        db.session.commit()

        previous = (
            Assessment.query.filter(
                Assessment.user_id == current_user.id,
                Assessment.assessment_date < target_date,
            )
            .order_by(Assessment.assessment_date.desc())
            .first()
        )

        return jsonify(
            {
                "id": record.id,
                "total_score": total_score,
                "severity": severity,
                "date": target_date.isoformat(),
                "previous_score": previous.total_score if previous else None,
            }
        )

    @app.route("/result/<int:assessment_id>")
    @login_required
    def result(assessment_id):
        record = Assessment.query.filter_by(
            id=assessment_id, user_id=current_user.id
        ).first_or_404()
        previous = (
            Assessment.query.filter(
                Assessment.user_id == current_user.id,
                Assessment.assessment_date < record.assessment_date,
            )
            .order_by(Assessment.assessment_date.desc())
            .first()
        )
        return render_template(
            "result.html",
            record=record,
            previous=previous,
            breakdown=category_breakdown(record),
            tone=severity_tone(record.severity),
            show_care_note=has_urgent_flags(record.answers),
        )

    @app.route("/history")
    @login_required
    def history():
        assessments = (
            Assessment.query.filter_by(user_id=current_user.id)
            .order_by(Assessment.assessment_date.desc())
            .all()
        )
        tones = {a.id: severity_tone(a.severity) for a in assessments}
        return render_template(
            "history.html", assessments=assessments, tones=tones, today=date.today()
        )

    @app.route("/history/<int:assessment_id>")
    @login_required
    def history_detail(assessment_id):
        record = Assessment.query.filter_by(
            id=assessment_id, user_id=current_user.id
        ).first_or_404()
        previous = (
            Assessment.query.filter(
                Assessment.user_id == current_user.id,
                Assessment.assessment_date < record.assessment_date,
            )
            .order_by(Assessment.assessment_date.desc())
            .first()
        )
        return render_template(
            "assessment_detail.html",
            record=record,
            previous=previous,
            breakdown=category_breakdown(record),
            questions=QUESTIONS,
            tone=severity_tone(record.severity),
            show_care_note=has_urgent_flags(record.answers),
        )

    @app.route("/history/<int:assessment_id>/delete", methods=["POST"])
    @login_required
    def delete_assessment(assessment_id):
        record = Assessment.query.filter_by(
            id=assessment_id, user_id=current_user.id
        ).first_or_404()
        db.session.delete(record)
        db.session.commit()
        flash("Check-in deleted.", "success")
        return redirect(url_for("history"))

    @app.route("/insights")
    @login_required
    def insights():
        data = insights_data(current_user.id)
        rewire_data = rewirement_insights(current_user.id)
        return render_template("insights.html", data=data, rewire_data=rewire_data)

    @app.route("/api/trend")
    @login_required
    def api_trend():
        try:
            days = int(request.args.get("days", 7))
        except ValueError:
            days = 7
        days = days if days in (7, 30, 90) else 7
        return jsonify(trend_series(current_user.id, days))

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
