import os, secrets, hashlib, time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-deploying")
database_url = os.environ.get("DATABASE_URL", "sqlite:///rabalata.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "/tmp/rabalata_uploads")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config.update(
    MAIL_SERVER=os.environ.get("MAIL_SERVER", ""),
    MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
    MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "true").lower() == "true",
    MAIL_USERNAME=os.environ.get("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", ""),
    MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", "")),
)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)
mail = Mail(app)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False, default="Rabalata customer")
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(40), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="customer", nullable=False)
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmailCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

class DriverProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    car_brand = db.Column(db.String(80), nullable=False)
    car_model = db.Column(db.String(100), nullable=False)
    car_color = db.Column(db.String(60), nullable=False)
    number_plate = db.Column(db.String(30), nullable=False, index=True)
    selfie_filename = db.Column(db.String(255), nullable=False)
    car_photo_filename = db.Column(db.String(255), nullable=False)
    approved = db.Column(db.Boolean, default=False)
    available = db.Column(db.Boolean, default=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    balance_cents = db.Column(db.Integer, default=0)
    user = db.relationship("User", backref=db.backref("driver_profile", uselist=False))

class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    pickup = db.Column(db.String(255), nullable=False)
    destination = db.Column(db.String(255), nullable=False)
    pickup_lat = db.Column(db.Float)
    pickup_lng = db.Column(db.Float)
    dest_lat = db.Column(db.Float)
    dest_lng = db.Column(db.Float)
    proposed_fare_cents = db.Column(db.Integer, nullable=False)
    agreed_fare_cents = db.Column(db.Integer)
    payment_method = db.Column(db.String(20), nullable=False, default="cash")
    payment_status = db.Column(db.String(30), default="unpaid")
    status = db.Column(db.String(30), default="requested")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("User", foreign_keys=[customer_id])
    driver = db.relationship("User", foreign_keys=[driver_id])

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey("ride.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), default="pending")
    ride = db.relationship("Ride", backref="offers")
    driver = db.relationship("User")

class PayoutRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_holder = db.Column(db.String(120), nullable=False)
    account_number_encrypted = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def driver_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u or u.role != "driver":
            flash("Driver account required.", "warning")
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def send_code(email, code):
    if not app.config["MAIL_SERVER"] or not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        raise RuntimeError("Email delivery is not configured. Set MAIL_* environment variables in Render.")
    msg = Message("Your Rabalata Shuttle verification code", recipients=[email])
    msg.body = f"Your Rabalata Shuttle verification code is {code}. It expires in 10 minutes. If you did not request it, ignore this email."
    mail.send(msg)

@app.context_processor
def inject_user():
    return {"logged_user": current_user(), "year": datetime.utcnow().year}

@app.route("/")
def home():
    drivers = DriverProfile.query.filter_by(approved=True, available=True).all()
    return render_template("home.html", drivers=drivers)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "customer")
        if role not in ("customer", "driver") or not name or not email or not phone or len(password) < 10:
            flash("Complete all fields. Password must be at least 10 characters.", "danger")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("That email is already registered. Log in instead.", "danger")
            return render_template("register.html")
        user = User(full_name=name, email=email, phone=phone, role=role, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        session["pending_email"] = email
        code = f"{secrets.randbelow(1000000):06d}"
        db.session.add(EmailCode(email=email, code_hash=hashlib.sha256(code.encode()).hexdigest(), expires_at=datetime.utcnow()+timedelta(minutes=10)))
        db.session.commit()
        try:
            send_code(email, code)
        except Exception as e:
            app.logger.exception("Verification email failed")
            flash("Account saved, but email could not be sent. Configure email delivery in Render, then request a new code.", "danger")
            return redirect(url_for("verify"))
        flash("A 6-digit verification code was sent to your email.", "success")
        return redirect(url_for("verify"))
    return render_template("register.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("pending_email")
    if not email:
        flash("Register first to request a verification code.", "warning")
        return redirect(url_for("register"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        item = EmailCode.query.filter_by(email=email, used=False).order_by(EmailCode.id.desc()).first()
        if not item or item.expires_at < datetime.utcnow() or not secrets.compare_digest(item.code_hash, hashlib.sha256(code.encode()).hexdigest()):
            flash("Code is invalid or expired. Request a new one by registering again or contact support.", "danger")
            return render_template("verify.html")
        item.used = True
        user = User.query.filter_by(email=email).first()
        user.verified = True
        db.session.commit()
        session.pop("pending_email", None)
        session["user_id"] = user.id
        flash("Email verified. Welcome to Rabalata Shuttle.", "success")
        return redirect(url_for("driver_register" if user.role == "driver" else "home"))
    return render_template("verify.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Incorrect email or password.", "danger")
        elif not user.verified:
            session["pending_email"] = user.email
            flash("Verify your email before logging in.", "warning")
            return redirect(url_for("verify"))
        else:
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("driver_dashboard" if user.role == "driver" else "home"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))

@app.route("/driver/register", methods=["GET", "POST"])
@login_required
def driver_register():
    u = current_user()
    if u.role != "driver":
        flash("Choose the driver account type when registering.", "warning")
        return redirect(url_for("home"))
    if request.method == "POST":
        brand=request.form.get("car_brand","").strip(); model=request.form.get("car_model","").strip()
        color=request.form.get("car_color","").strip(); plate=request.form.get("number_plate","").strip().upper()
        selfie=request.files.get("selfie"); carphoto=request.files.get("car_photo")
        if not all([brand,model,color,plate,selfie,carphoto]) or not selfie.filename or not carphoto.filename:
            flash("Complete all vehicle details and upload a selfie plus car photo.", "danger")
            return render_template("driver_register.html")
        if not allowed_file(selfie.filename) or not allowed_file(carphoto.filename):
            flash("Use JPG, PNG or WEBP images only.", "danger")
            return render_template("driver_register.html")
        if DriverProfile.query.filter_by(number_plate=plate).first():
            flash("That number plate is already registered.", "danger")
            return render_template("driver_register.html")
        sf=f"{u.id}_selfie_{secure_filename(selfie.filename)}"; cf=f"{u.id}_car_{secure_filename(carphoto.filename)}"
        selfie.save(os.path.join(app.config["UPLOAD_FOLDER"],sf)); carphoto.save(os.path.join(app.config["UPLOAD_FOLDER"],cf))
        profile=DriverProfile(user_id=u.id,car_brand=brand,car_model=model,car_color=color,number_plate=plate,selfie_filename=sf,car_photo_filename=cf)
        db.session.add(profile); db.session.commit()
        flash("Driver profile submitted for admin review. You cannot accept rides until approved.", "success")
        return redirect(url_for("driver_dashboard"))
    return render_template("driver_register.html")

@app.route("/driver/dashboard")
@login_required
@driver_required
def driver_dashboard():
    profile=DriverProfile.query.filter_by(user_id=current_user().id).first()
    rides=Ride.query.filter_by(status="requested").order_by(Ride.created_at.desc()).all()
    myrides=Ride.query.filter_by(driver_id=current_user().id).order_by(Ride.created_at.desc()).limit(20).all()
    return render_template("driver_dashboard.html", profile=profile, rides=rides, myrides=myrides)

@app.post("/driver/availability")
@login_required
@driver_required
def driver_availability():
    p=DriverProfile.query.filter_by(user_id=current_user().id).first()
    if not p or not p.approved:
        flash("Your driver profile must be approved first.", "warning")
    else:
        p.available = request.form.get("available") == "yes"
        db.session.commit()
        flash("Availability updated.", "success")
    return redirect(url_for("driver_dashboard"))

@app.post("/driver/location")
@login_required
@driver_required
def driver_location():
    p=DriverProfile.query.filter_by(user_id=current_user().id).first()
    if not p or not p.approved:
        return jsonify({"error":"Driver not approved"}), 403
    data=request.get_json(silent=True) or {}
    try:
        p.latitude=float(data["latitude"]); p.longitude=float(data["longitude"])
        db.session.commit()
        return jsonify({"ok":True})
    except (KeyError,TypeError,ValueError):
        return jsonify({"error":"Valid latitude and longitude required"}),400

@app.route("/book", methods=["GET","POST"])
@login_required
def book():
    if current_user().role != "customer":
        flash("Customer accounts book rides.", "warning")
        return redirect(url_for("home"))
    if request.method == "POST":
        try: fare=int(round(float(request.form.get("fare","0"))*100))
        except ValueError: fare=0
        pickup=request.form.get("pickup","").strip(); dest=request.form.get("destination","").strip()
        if not pickup or not dest or fare < 1000:
            flash("Enter pickup, destination and a fare of at least R10.", "danger")
            return render_template("book.html")
        method=request.form.get("payment_method","cash")
        if method not in ("cash","card"): method="cash"
        ride=Ride(customer_id=current_user().id,pickup=pickup,destination=dest,
          pickup_lat=parse_float(request.form.get("pickup_lat")),pickup_lng=parse_float(request.form.get("pickup_lng")),
          dest_lat=parse_float(request.form.get("dest_lat")),dest_lng=parse_float(request.form.get("dest_lng")),
          proposed_fare_cents=fare,payment_method=method,
          payment_status="pending_gateway" if method=="card" else "cash_due")
        db.session.add(ride); db.session.commit()
        flash("Ride request created. Drivers can make counter-offers. Card payment stays pending until a real payment gateway confirms it.", "success")
        return redirect(url_for("ride_detail", ride_id=ride.id))
    return render_template("book.html")

def parse_float(v):
    try: return float(v) if v else None
    except ValueError: return None

@app.route("/ride/<int:ride_id>")
@login_required
def ride_detail(ride_id):
    ride=db.session.get(Ride,ride_id)
    u=current_user()
    if not ride or (ride.customer_id != u.id and ride.driver_id != u.id and u.role != "admin"):
        flash("Ride not found.", "danger"); return redirect(url_for("home"))
    return render_template("ride.html", ride=ride)

@app.post("/ride/<int:ride_id>/offer")
@login_required
@driver_required
def offer(ride_id):
    ride=db.session.get(Ride,ride_id); p=DriverProfile.query.filter_by(user_id=current_user().id).first()
    if not ride or ride.status != "requested" or not p or not p.approved or not p.available:
        flash("This ride is not available or your driver profile is not approved/available.", "danger")
        return redirect(url_for("driver_dashboard"))
    try: amount=int(round(float(request.form.get("amount","0"))*100))
    except ValueError: amount=0
    if amount < 1000:
        flash("Offer must be at least R10.", "danger"); return redirect(url_for("driver_dashboard"))
    db.session.add(Offer(ride_id=ride.id,driver_id=current_user().id,amount_cents=amount,message=request.form.get("message","")[:300]))
    db.session.commit()
    flash("Your price offer was sent to the customer.", "success")
    return redirect(url_for("driver_dashboard"))

@app.post("/offer/<int:offer_id>/accept")
@login_required
def accept_offer(offer_id):
    o=db.session.get(Offer,offer_id)
    if not o or o.ride.customer_id != current_user().id or o.status != "pending" or o.ride.status != "requested":
        flash("Offer cannot be accepted.", "danger"); return redirect(url_for("home"))
    o.status="accepted"; o.ride.driver_id=o.driver_id; o.ride.agreed_fare_cents=o.amount_cents; o.ride.status="accepted"
    for other in o.ride.offers:
        if other.id != o.id and other.status == "pending": other.status="declined"
    db.session.commit()
    flash("Driver accepted. Use the map to follow the driver when live location sharing is enabled.", "success")
    return redirect(url_for("ride_detail",ride_id=o.ride_id))

@app.post("/ride/<int:ride_id>/complete")
@login_required
@driver_required
def complete_ride(ride_id):
    ride=db.session.get(Ride,ride_id)
    if not ride or ride.driver_id != current_user().id or ride.status not in ("accepted","in_progress"):
        flash("Ride cannot be completed.", "danger")
    elif ride.payment_method == "card" and ride.payment_status != "paid":
        flash("Card payment has not been confirmed by the payment provider. Do not mark it paid manually.", "danger")
    else:
        ride.status="completed"
        if ride.payment_method == "card":
            p=DriverProfile.query.filter_by(user_id=current_user().id).first()
            # Actual card settlement and available balance must be reconciled with a verified gateway webhook.
            if p and ride.payment_status == "paid":
                p.balance_cents += max(0, ride.agreed_fare_cents or ride.proposed_fare_cents)
        db.session.commit(); flash("Ride marked completed.", "success")
    return redirect(url_for("driver_dashboard"))

@app.route("/driver/payout", methods=["GET","POST"])
@login_required
@driver_required
def driver_payout():
    p=DriverProfile.query.filter_by(user_id=current_user().id).first()
    if not p or not p.approved:
        flash("Approved driver profile required.", "warning"); return redirect(url_for("driver_dashboard"))
    if request.method=="POST":
        flash("Payouts are not enabled until a compliant payment provider and verified payout API are configured. Do not submit bank details on this placeholder form.", "warning")
        return redirect(url_for("driver_dashboard"))
    return render_template("payout.html", profile=p)

@app.route("/health")
def health(): return jsonify({"status":"ok","service":"Rabalata Shuttle"})

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
