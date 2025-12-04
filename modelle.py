from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Eltern(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String(120), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    kinder = db.relationship("Kind", backref="eltern", lazy=True)

class Kind(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    geburt = db.Column(db.String, nullable=False)

    eltern_id = db.Column(db.Integer, db.ForeignKey("eltern.id"), nullable=False)
    termine = db.relationship("Termin", backref="kind", lazy=True)


class Termin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    art = db.Column(db.String(10), nullable=False)
    datum = db.Column(db.String, nullable=False)

    bestaetigtes_datum = db.Column(db.String, nullable=True)

    erledigt = db.Column(db.Boolean, default=False)
    kind_id = db.Column(db.Integer, db.ForeignKey("kind.id"), nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
