from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dateutil.relativedelta import relativedelta


# --- Datenbank-Objekt importieren (NICHT neu erstellen!) ---
from modelle import db, Eltern, Kind, Termin, User

app = Flask(__name__)
app.secret_key = "super_geheimer_schluessel_123"

app.jinja_env.globals['now'] = datetime.now

@app.context_processor
def inject_user_status():
    return {
        "is_logged_in": "user_id" in session
    }


# --- Datenbank-Konfiguration ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# --- DB mit App verbinden ---
db.init_app(app)

# ---------------------------------
# Login-Decorator
# ---------------------------------
from functools import wraps

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------
# Eltern-Datensatz des eingeloggten Users holen
# ---------------------------------
def get_current_parent():
    if "user_id" not in session:
        return None

    return Eltern.query.filter_by(user_id=session["user_id"]).first()

# ---------------------------------
# U-Untersuchungen (MVP: automatisch berechnet)
# ---------------------------------
U_TERMINE = [
    ("U1", relativedelta(days=+0)),   # Geburt
    ("U2", relativedelta(days=+3)),   # 3. Lebenstag
    ("U3", relativedelta(months=+1)),
    ("U4", relativedelta(months=+3)),
    ("U5", relativedelta(months=+6)),
    ("U6", relativedelta(months=+12)),
    ("U7", relativedelta(months=+24)),
    ("U7a", relativedelta(months=+36)),
    ("U8", relativedelta(months=+48)),
    ("U9", relativedelta(months=+60)),
]

# ---------------------------------
# Startseite / Dashboard
# ---------------------------------
@app.route("/")
@login_required
def home():
    from datetime import date

    eltern = get_current_parent()
    if not eltern:
        return redirect(url_for("login"))

    heute = date.today().strftime("%Y-%m-%d")

    # Alle Kinder der Eltern
    kinder = Kind.query.filter_by(eltern_id=eltern.id).all()

    # Alle Termine der Eltern
    termine = (
        Termin.query
        .join(Kind)
        .filter(Kind.eltern_id == eltern.id)
        .order_by(Termin.datum.asc())
        .all()
    )

    # Nächster offener/kommender Termin finden
    naechster = None
    for t in termine:
        if not t.erledigt and t.datum >= heute:
            naechster = t
            break

    return render_template(
        "home.html",
        eltern=eltern,
        kinder=kinder,
        naechster=naechster,
        current_date=heute
    )


# ---------------------------------
# Profilseite des eingeloggten Elternteils
# ---------------------------------
@app.route("/eltern")
@login_required
def eltern_profil():
    eltern = get_current_parent()

    if not eltern:
        return "Kein Eltern-Datensatz gefunden.", 404

    return render_template("profil.html", eltern=eltern)

@app.route("/profil/bearbeiten", methods=["GET", "POST"])
@login_required
def profil_bearbeiten():
    eltern = get_current_parent()

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")

        if not name or not email:
            return render_template("profil_bearbeiten.html",
                                   eltern=eltern,
                                   error="Bitte alle Felder ausfüllen.")

        # Eltern-Daten aktualisieren
        eltern.name = name
        eltern.email = email
        

        db.session.commit()

        return redirect(url_for("eltern_profil"))


    return render_template("profil_bearbeiten.html", eltern=eltern)

# ---------------------------------
# Eltern anlegen
# ---------------------------------
@app.route("/eltern/neu", methods=["GET", "POST"])
@login_required
def eltern_neu():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")

        if not name or not email:
            return render_template(
                "eltern_neu.html",
                error="Bitte alle Felder ausfüllen."
            )

        neuer_elternteil = Eltern(name=name, email=email)
        db.session.add(neuer_elternteil)
        db.session.commit()

        return redirect(url_for("eltern_profil"))

    return render_template("eltern_neu.html")


# ---------------------------------
# Eltern-Detailseite
# ---------------------------------
@app.route("/eltern/<int:eltern_id>")
@login_required
def eltern_detail(eltern_id):
    eltern = Eltern.query.get_or_404(eltern_id)

    # Sicherheitscheck: gehört dieser Eltern-Datensatz zum eingeloggten User?
    if eltern.user_id != session.get("user_id"):
        return "Nicht erlaubt.", 403

    return render_template("eltern_detail.html", eltern=eltern)

# ---------------------------------
# Kind anlegen
# ---------------------------------
@app.route("/kind/neu", methods=["GET", "POST"])
@login_required
def kind_neu():
    eltern = get_current_parent()
    if not eltern:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name")
        geburt = request.form.get("geburt")

        if not name or not geburt:
            # eltern_als_liste -> damit dein Template weiter mit for-Schleife klarkommt
            return render_template(
                "kind_neu.html",
                error="Bitte alle Felder ausfüllen.",
                eltern=[eltern]
            )

        # Kind wird automatisch dem eingeloggten Elternteil zugeordnet
        neues_kind = Kind(name=name, geburt=geburt, eltern_id=eltern.id)
        db.session.add(neues_kind)
        db.session.commit()

        # ---------------------------------
        # U-Termine automatisch anlegen
        # ---------------------------------
        geburtsdatum_dt = datetime.strptime(geburt, "%Y-%m-%d")

        # ---- U3–U9: automatisch wie bisher ----
        for art, offset in U_TERMINE:
            termin_datum = geburtsdatum_dt + offset
            termin = Termin(
                art=art,
                datum=termin_datum.strftime("%Y-%m-%d"),
                kind_id=neues_kind.id
            )
            db.session.add(termin)

        db.session.commit()

        return redirect(url_for("kinder_liste"))

    # GET: Formular anzeigen
    return render_template("kind_neu.html", eltern=[eltern])



# ---------------------------------
# Kinderliste
# ---------------------------------
@app.route("/kinder")
@login_required
def kinder_liste():
    eltern = get_current_parent()
    if not eltern:
        return redirect(url_for("home"))

    kinder = Kind.query.filter_by(eltern_id=eltern.id).all()
    return render_template("kinder_liste.html", kinder=kinder)

# ---------------------------------
# Kind-Detailseite
# ---------------------------------
@app.route("/kinder/<int:kind_id>")
@login_required
def kind_detail(kind_id):
    kind = Kind.query.get_or_404(kind_id)
    return render_template("kind_detail.html", kind=kind)

@app.route("/kind/bearbeiten/<int:kind_id>", methods=["GET", "POST"])
@login_required
def kind_bearbeiten(kind_id):
    kind = Kind.query.get_or_404(kind_id)
    eltern = get_current_parent()

    # Sicherheitsprüfung – darf nur eigene Kinder bearbeiten
    if kind.eltern_id != eltern.id:
        return "Nicht erlaubt.", 403

    if request.method == "POST":
        name = request.form.get("name")
        geburt = request.form.get("geburt")

        if not name or not geburt:
            return render_template(
                "kind_bearbeiten.html",
                kind=kind,
                error="Bitte alle Felder ausfüllen."
            )

        # Daten aktualisieren
        kind.name = name
        kind.geburt = geburt
        db.session.commit()

        return redirect(url_for("kinder_liste"))

    return render_template("kind_bearbeiten.html", kind=kind)


# ---------------------------------
# Kind löschen (FINAL)
# ---------------------------------
@app.route("/kind/loeschen/<int:kind_id>")
@login_required
def kind_loeschen(kind_id):
    parent = get_current_parent()
    if not parent:
        return redirect(url_for("login"))

    kind = Kind.query.get_or_404(kind_id)

    # Sicherheitscheck: Kind gehört NICHT diesem Elternteil?
    if kind.eltern_id != parent.id:
        return "Nicht erlaubt.", 403

    # Alle Termine für dieses Kind löschen
    Termin.query.filter_by(kind_id=kind_id).delete()

    # Kind löschen
    db.session.delete(kind)
    db.session.commit()

    return redirect(url_for("kinder_liste"))

# ---------------------------------
# Alle Termine (gruppiert nach Kind)
# ---------------------------------
@app.route("/termine")
@login_required
def termine():
    from datetime import date

    eltern = get_current_parent()
    if not eltern:
        return redirect(url_for("home"))

    # Alle Kinder der Eltern
    kinder = Kind.query.filter_by(eltern_id=eltern.id).all()

    # Dictionary: { "Saliha": [...], "Sascha": [...] }
    gruppen = {}

    for kind in kinder:
        termine_kind = (
            Termin.query
            .filter_by(kind_id=kind.id)
            .order_by(Termin.datum.asc())
            .all()
        )
        gruppen[kind.name] = termine_kind

    # Heutiges Datum im gleichen Format wie in DB
    heute = date.today().strftime("%Y-%m-%d")

    # Flache Liste ALLER Termine
    alle_termine = []
    for liste in gruppen.values():
        alle_termine.extend(liste)

    # Sortieren
    alle_termine.sort(key=lambda t: t.datum)

    # Nächster Termin: nicht erledigt + heute oder Zukunft
    naechster = None
    for t in alle_termine:
        if not t.erledigt and t.datum >= heute:
            naechster = t
            break

    return render_template(
        "termine.html",
        gruppen=gruppen,
        naechster=naechster,
        heute=heute
    )


# ---------------------------------
# Termin erledigt markieren
# ---------------------------------
@app.route("/termin/<int:id>/done")
@login_required
def termin_done(id):
    termin = Termin.query.get_or_404(id)

    eltern = get_current_parent()
    if not eltern or termin.kind.eltern_id != eltern.id:
        return "Nicht erlaubt.", 403

    termin.erledigt = True
    db.session.commit()
    return redirect(url_for("termine"))

# ---------------------------------
# Termin bearbeiten
# ---------------------------------
@app.route("/termin/<int:id>", methods=["GET", "POST"])
@login_required
def termin_detail(id):
    termin = Termin.query.get_or_404(id)

    eltern = get_current_parent()
    if not eltern or termin.kind.eltern_id != eltern.id:
        return "Nicht erlaubt.", 403

    if request.method == "POST":
        bestaetigt = request.form.get("bestaetigtes_datum")
        erledigt = request.form.get("erledigt")

        # Bestätigtes Datum speichern oder löschen
        termin.bestaetigtes_datum = bestaetigt if bestaetigt else None

        # Erledigt-Status speichern
        termin.erledigt = True if erledigt else False

        db.session.commit()
        return redirect(url_for("termine"))

    return render_template("termin_detail.html", termin=termin)

# ---------------------------------
# Registrierung
# ---------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # User anlegen
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Automatisch Eltern-Datensatz anlegen
        eltern = Eltern(
            name=email,     # Platzhalter, später änderbar
            email=email,
            user_id=user.id
        )
        db.session.add(eltern)
        db.session.commit()

        # Automatisch einloggen
        session["user_id"] = user.id

        return redirect(url_for("kinder_liste"))

    return render_template("register.html")


# ---------------------------------
# Login
# ---------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Login fehlgeschlagen")

    return render_template("login.html")


# ---------------------------------
# Logout
# ---------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --------------------------
# Fehlerseiten
# --------------------------
from flask import render_template

@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("errors/500.html"), 500



# ----- Test-Routen -----
@app.route("/test403")
def test403():
    abort(403)

@app.route("/test500")
def test500():
    1/0

@app.route("/routes")
def list_routes():
    output = []
    for rule in app.url_map.iter_rules():
        output.append(f"{rule.endpoint:30}  {rule}")
    return "<pre>" + "\n".join(sorted(output)) + "</pre>"

# ----- App Start -----
if __name__ == "__main__":
    app.config["ENV"] = "production"
    app.config["DEBUG"] = False
    app.config["TESTING"] = False
    app.run(debug=False)



