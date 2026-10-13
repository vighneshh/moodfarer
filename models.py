import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    google_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    theme = db.Column(db.String(16), nullable=False, default="system")
    reminder_email_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_push_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_time = db.Column(db.String(5), nullable=False, default="19:00")
    reminder_last_sent = db.Column(db.Date, nullable=True)
    signature_strengths_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assessments = db.relationship(
        "Assessment", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    push_subscriptions = db.relationship(
        "PushSubscription", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    rewirement_checkins = db.relationship(
        "RewirementCheckin", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def signature_strengths(self):
        try:
            return json.loads(self.signature_strengths_json) if self.signature_strengths_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    @signature_strengths.setter
    def signature_strengths(self, value: list):
        self.signature_strengths_json = json.dumps(value)


class Assessment(db.Model):
    __tablename__ = "assessments"
    __table_args__ = (
        db.UniqueConstraint("user_id", "assessment_date", name="uq_user_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assessment_date = db.Column(db.Date, nullable=False, index=True)
    answers_json = db.Column(db.Text, nullable=False, default="{}")
    total_score = db.Column(db.Integer, nullable=False, default=0)
    severity = db.Column(db.String(64), nullable=False, default="")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def answers(self):
        try:
            return {int(k): v for k, v in json.loads(self.answers_json).items()}
        except (json.JSONDecodeError, TypeError):
            return {}

    @answers.setter
    def answers(self, value: dict):
        self.answers_json = json.dumps({str(k): v for k, v in value.items()})

    def to_dict(self):
        return {
            "id": self.id,
            "assessment_date": self.assessment_date.isoformat(),
            "answers": self.answers,
            "total_score": self.total_score,
            "severity": self.severity,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_subscription_info(self):
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }


class RewirementCheckin(db.Model):
    __tablename__ = "rewirement_checkins"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "rewirement_key", "week_start", "day_key",
            name="uq_user_rewirement_week_day",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rewirement_key = db.Column(db.String(64), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False, index=True)
    day_key = db.Column(db.String(16), nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)