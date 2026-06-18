import os
import secrets
from datetime import datetime, date, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, g, abort, session)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from models import (db, WorkOrder, ProductionRoll, ProductType, Customer,
                    PackingList, PackingListItem, DispatchMemo,
                    User, Recipe, RecipeLayer, RecipeGrade,
                    RawMaterial, InventoryLedger,
                    MACHINE_CHOICES, MACHINES, ROLES)

app = Flask(__name__)

# ─── JINJA2 FILTERS ───────────────────────────────────────────────────────────

def to_ist(dt):
    """Convert a naive UTC datetime to IST and format as dd/mm/yyyy HH:MM."""
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        utc_dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = utc_dt.astimezone(IST)
        return ist_dt.strftime("%d/%m/%Y %H:%M")
    return dt.strftime("%d/%m/%Y")


def fmt_date(d):
    """Format a date or datetime as dd/mm/yyyy."""
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y")


app.jinja_env.filters["ist"]      = to_ist
app.jinja_env.filters["fmt_date"] = fmt_date


# SECRET_KEY MUST be set as an environment variable in production.
# If missing, we generate a temporary one and print a loud warning —
# this means sessions will not survive restarts or multi-worker deployments.
_secret = os.environ.get("HIC_SECRET_KEY")
if not _secret:
    _secret = os.urandom(32).hex()
    import sys
    print("WARNING: HIC_SECRET_KEY environment variable is not set.", file=sys.stderr)
    print("WARNING: Sessions will be lost on every restart. Set HIC_SECRET_KEY in your environment.", file=sys.stderr)
app.config["SECRET_KEY"] = _secret

# On Railway, use /data (persistent volume). Locally, use instance/hic.db
_db_dir = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", 
           os.path.join(os.path.abspath(os.path.dirname(__file__)), "instance"))
os.makedirs(_db_dir, exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(_db_dir, "hic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Session settings — ensure sessions persist across requests on Railway
app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 30    # 30 days
app.config["SESSION_COOKIE_HTTPONLY"]     = True
app.config["SESSION_COOKIE_SAMESITE"]     = "Lax"
# Use Secure cookies on HTTPS (Railway), plain HTTP locally
app.config["SESSION_COOKIE_SECURE"]       = os.environ.get("RAILWAY_ENVIRONMENT") is not None

db.init_app(app)


# ─── INPUT PARSING HELPERS ────────────────────────────────────────────────────
# These let routes accept user input without crashing on bad values. Each parse
# appends a friendly message to `errors` instead of raising, so the route can
# flash the problem and re-render the form with the data the user already typed.

def parse_float(value, field_label, errors, default=0.0,
                allow_negative=False, allow_blank=True):
    """Parse a form value as a float. On bad input, record a message and return
    `default`. Blank is treated as `default` when allow_blank is True."""
    if value is None or str(value).strip() == "":
        if allow_blank:
            return default
        errors.append(f"{field_label} is required.")
        return default
    try:
        num = float(str(value).strip())
    except (ValueError, TypeError):
        errors.append(f"{field_label} must be a number (you entered \"{value}\").")
        return default
    if not allow_negative and num < 0:
        errors.append(f"{field_label} cannot be negative.")
        return default
    return num


def parse_date(value, field_label, errors):
    """Parse a YYYY-MM-DD form value as a date. Returns None on bad/missing input
    and records a friendly message."""
    if value is None or str(value).strip() == "":
        errors.append(f"{field_label} is required.")
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        errors.append(f"{field_label} must be a valid date.")
        return None


def parse_int_id(value):
    """Best-effort parse of an id-like form/query value. Returns None if not a
    valid integer (so callers can 404 or skip rather than crash)."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "error"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── CSRF PROTECTION ──────────────────────────────────────────────────────────
# Lightweight, dependency-free CSRF guard. A per-session random token is required
# on every state-changing (POST) request. The token is exposed to templates as
# csrf_token() and injected automatically into every form by a small script in
# base.html, so individual forms don't each need a hidden field added by hand.

def _get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _get_csrf_token}


@app.before_request
def csrf_protect():
    if request.method == "POST":
        # The login form is exempt: there is no session/token yet at that point,
        # and credentials themselves authenticate the request.
        if request.endpoint == "login":
            return
        sent = (request.form.get("_csrf_token")
                or request.headers.get("X-CSRFToken"))
        if not sent or sent != session.get("_csrf_token"):
            abort(400, description="Invalid or missing CSRF token. Please reload the page and try again.")


# ─── ROLE GUARDS ──────────────────────────────────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

def require_permission(permission):
    """Decorator: allow admins + anyone with the specific permission."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if not current_user.can(permission):
                flash("You don't have permission to do that.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ─── INITIALISE ───────────────────────────────────────────────────────────────

_DB_READY = {"done": False}


def _ensure_db_setup():
    """One-time: create tables, seed defaults, sync recipe grades into inventory.
    Runs on the first request only, not on every request."""
    if _DB_READY["done"]:
        return
    db.create_all()
    ProductType.seed_defaults()
    User.seed_admin()
    try:
        for rg in RecipeGrade.query.filter(RecipeGrade.grade_name != "").all():
            RawMaterial.get_or_create(rg.grade_name)
        db.session.commit()
    except Exception:
        db.session.rollback()
    _DB_READY["done"] = True


@app.before_request
def initialise_db():
    _ensure_db_setup()
    try:
        g.in_production_wos = (WorkOrder.query
                               .filter_by(status="in_production")
                               .order_by(WorkOrder.wo_number)
                               .all())
    except Exception:
        g.in_production_wos = []


# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            session.permanent = True   # use PERMANENT_SESSION_LIFETIME
            login_user(user, remember=True)
            flash(f"Welcome, {user.username}.", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    status_filter = request.args.get("status", "all")
    query = WorkOrder.query.order_by(WorkOrder.created_at.desc())
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    work_orders = query.all()
    counts = {
        "all":           WorkOrder.query.count(),
        "open":          WorkOrder.query.filter_by(status="open").count(),
        "in_production": WorkOrder.query.filter_by(status="in_production").count(),
        "ready":         WorkOrder.query.filter_by(status="ready").count(),
        "dispatched":    WorkOrder.query.filter_by(status="dispatched").count(),
    }
    g.dash_counts = counts
    g.dash_filter = status_filter
    return render_template("dashboard.html", work_orders=work_orders,
                           counts=counts, active_filter=status_filter)


# ─── USER MANAGEMENT (admin only) ─────────────────────────────────────────────

@app.route("/settings/users", methods=["GET", "POST"])
@login_required
@admin_required
def users_manage():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "operator")
            if not username or not password:
                flash("Username and password are required.", "error")
            elif User.query.filter_by(username=username).first():
                flash(f"Username '{username}' already exists.", "error")
            elif role not in ROLES:
                flash("Invalid role.", "error")
            else:
                u = User(username=username, role=role)
                u.set_password(password)
                db.session.add(u)
                db.session.commit()
                flash(f"User '{username}' ({ROLES[role]}) created.", "success")

        elif action == "reset_password":
            u = User.query.get_or_404(int(request.form.get("user_id", 0)))
            new_pw = request.form.get("new_password", "").strip()
            if not new_pw:
                flash("Password cannot be empty.", "error")
            else:
                u.set_password(new_pw)
                db.session.commit()
                flash(f"Password reset for '{u.username}'.", "success")

        elif action == "toggle":
            u = User.query.get_or_404(int(request.form.get("user_id", 0)))
            if u.id == current_user.id:
                flash("Cannot disable your own account.", "error")
            else:
                u.is_active = not u.is_active
                db.session.commit()
                flash(f"'{u.username}' {'enabled' if u.is_active else 'disabled'}.", "info")

        elif action == "delete":
            u = User.query.get_or_404(int(request.form.get("user_id", 0)))
            if u.id == current_user.id:
                flash("Cannot delete your own account.", "error")
            else:
                db.session.delete(u)
                db.session.commit()
                flash(f"'{u.username}' deleted.", "info")

        return redirect(url_for("users_manage"))

    users = User.query.order_by(User.username).all()
    return render_template("users.html", users=users, roles=ROLES)


# ─── PRODUCT TYPES ────────────────────────────────────────────────────────────

@app.route("/settings/product-types", methods=["GET", "POST"])
@login_required
@admin_required
def product_types_manage():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Product type name cannot be empty.", "error")
            elif ProductType.query.filter_by(name=name).first():
                flash(f"'{name}' already exists.", "error")
            else:
                max_order = db.session.query(db.func.max(ProductType.sort_order)).scalar() or 0
                db.session.add(ProductType(name=name, sort_order=max_order + 1))
                db.session.commit()
                flash(f"'{name}' added.", "success")
        elif action == "toggle":
            pt = ProductType.query.get_or_404(int(request.form.get("pt_id", 0)))
            pt.is_active = not pt.is_active
            db.session.commit()
            flash(f"'{pt.name}' {'enabled' if pt.is_active else 'disabled'}.", "info")
        elif action == "delete":
            pt = ProductType.query.get_or_404(int(request.form.get("pt_id", 0)))
            in_use = WorkOrder.query.filter_by(product_type=pt.name).count()
            if in_use:
                flash(f"Cannot delete '{pt.name}' — used by {in_use} WO(s).", "error")
            else:
                db.session.delete(pt)
                db.session.commit()
                flash(f"'{pt.name}' deleted.", "info")
        return redirect(url_for("product_types_manage"))

    product_types = ProductType.query.order_by(ProductType.sort_order, ProductType.name).all()
    return render_template("product_types.html", product_types=product_types)


# ─── CUSTOMERS ────────────────────────────────────────────────────────────────

@app.route("/settings/customers", methods=["GET", "POST"])
@login_required
@admin_required
def customers_manage():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip()
            if not name:
                flash("Customer name cannot be empty.", "error")
            elif Customer.query.filter_by(name=name).first():
                flash(f"'{name}' already exists.", "error")
            else:
                db.session.add(Customer(name=name, address=address))
                db.session.commit()
                flash(f"Customer '{name}' added.", "success")
        elif action == "edit":
            c = Customer.query.get_or_404(int(request.form.get("customer_id", 0)))
            new_name = request.form.get("name", "").strip()
            new_address = request.form.get("address", "").strip()
            if not new_name:
                flash("Customer name cannot be empty.", "error")
            elif new_name != c.name and Customer.query.filter_by(name=new_name).first():
                flash(f"'{new_name}' already exists.", "error")
            else:
                old_name = c.name
                c.name = new_name
                c.address = new_address
                if old_name != new_name:
                    WorkOrder.query.filter_by(customer_name=old_name).update({"customer_name": new_name})
                db.session.commit()
                flash("Customer updated.", "success")
        elif action == "toggle":
            c = Customer.query.get_or_404(int(request.form.get("customer_id", 0)))
            c.is_active = not c.is_active
            db.session.commit()
            flash(f"'{c.name}' {'enabled' if c.is_active else 'disabled'}.", "info")
        elif action == "delete":
            c = Customer.query.get_or_404(int(request.form.get("customer_id", 0)))
            in_use = WorkOrder.query.filter_by(customer_id=c.id).count()
            if in_use:
                flash(f"Cannot delete '{c.name}' — linked to {in_use} WO(s).", "error")
            else:
                db.session.delete(c)
                db.session.commit()
                flash(f"'{c.name}' deleted.", "info")
        return redirect(url_for("customers_manage"))

    customers = Customer.query.order_by(Customer.name).all()
    for c in customers:
        c.wo_count = WorkOrder.query.filter_by(customer_id=c.id).count()
    return render_template("customers.html", customers=customers)


# ─── WORK ORDER (admin only) ──────────────────────────────────────────────────

@app.route("/work-order/new", methods=["GET", "POST"])
@login_required
@admin_required
def work_order_new():
    next_wo = WorkOrder.next_wo_number()
    product_types = ProductType.active_names()
    customers = Customer.active_list()
    recipes = Recipe.query.order_by(Recipe.name).all()

    if request.method == "POST":
        wo_number = request.form.get("wo_number", "").strip()
        customer_id = request.form.get("customer_id", "").strip()
        recipe_id_str = request.form.get("recipe_id", "").strip()

        if not wo_number:
            flash("Work Order number is required.", "error")
            return render_template("work_order_new.html", product_types=product_types,
                                   customers=customers, recipes=recipes,
                                   next_wo=next_wo, form=request.form)
        if WorkOrder.query.filter_by(wo_number=wo_number).first():
            flash(f"Work Order '{wo_number}' already exists.", "error")
            return render_template("work_order_new.html", product_types=product_types,
                                   customers=customers, recipes=recipes,
                                   next_wo=next_wo, form=request.form)

        errors = []
        product_type = request.form.get("product_type", "").strip()
        if not product_type:
            errors.append("Product type is required.")
        size_mm = parse_float(request.form.get("size_mm"), "Film width", errors)
        thickness = parse_float(request.form.get("thickness_microns"), "Thickness", errors)
        target_kg = parse_float(request.form.get("total_weight_kg"), "Total order weight", errors)

        cust = Customer.query.get(parse_int_id(customer_id)) if customer_id else None
        recipe = Recipe.query.get(parse_int_id(recipe_id_str)) if recipe_id_str else None

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("work_order_new.html", product_types=product_types,
                                   customers=customers, recipes=recipes,
                                   next_wo=next_wo, form=request.form)

        wo = WorkOrder(
            wo_number=wo_number,
            product_type=product_type,
            customer_id=cust.id if cust else None,
            customer_name=cust.name if cust else "",
            size_mm=size_mm,
            thickness_microns=thickness,
            total_weight_kg=target_kg,
            notes=request.form.get("notes", "").strip(),
            status="open",
            recipe_id=recipe.id if recipe else None,
            inventory_deducted=False,
        )
        db.session.add(wo)
        db.session.flush()

        # ── Inventory deduction ──────────────────────────────────────────────
        if recipe and target_kg > 0:
            recipe_batch_kg = recipe.total_kg_net  # what the recipe defines as 1 batch
            if recipe_batch_kg > 0:
                scale = target_kg / recipe_batch_kg
                tally = recipe.material_tally      # {grade_name: kg per batch}
                for grade_name, batch_kg in tally.items():
                    if not grade_name:
                        continue
                    deduct_kg = round(batch_kg * scale, 3)
                    mat = RawMaterial.get_or_create(grade_name)
                    entry = InventoryLedger(
                        material_id=mat.id,
                        qty_kg=-deduct_kg,
                        txn_type="work_order",
                        reference=wo_number,
                        notes=f"Deducted for {wo_number} ({target_kg} kg order)",
                        created_by=current_user.username,
                    )
                    db.session.add(entry)
                wo.inventory_deducted = True

        db.session.commit()
        flash(f"Work Order {wo.wo_number} created.", "success")
        if recipe and wo.inventory_deducted:
            flash(f"Inventory deducted based on recipe '{recipe.name}'.", "info")
        return redirect(url_for("dashboard"))

    return render_template("work_order_new.html", product_types=product_types,
                           customers=customers, recipes=recipes,
                           next_wo=next_wo, form={})


@app.route("/work-order/<int:wo_id>")
@login_required
def work_order_detail(wo_id):
    wo = WorkOrder.query.get_or_404(wo_id)
    return render_template("work_order_detail.html", wo=wo)


@app.route("/work-order/<int:wo_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def work_order_edit(wo_id):
    wo = WorkOrder.query.get_or_404(wo_id)
    product_types = ProductType.active_names()
    if wo.product_type not in product_types:
        product_types = [wo.product_type] + product_types
    customers = Customer.active_list()
    if wo.customer_id:
        cust_ids = [c.id for c in customers]
        if wo.customer_id not in cust_ids:
            current_cust = Customer.query.get(wo.customer_id)
            if current_cust:
                customers = [current_cust] + customers
    if request.method == "POST":
        customer_id = request.form.get("customer_id", "").strip()
        cust = Customer.query.get(parse_int_id(customer_id)) if customer_id else None

        errors = []
        product_type = request.form.get("product_type", "").strip()
        if not product_type:
            errors.append("Product type is required.")
        size_mm = parse_float(request.form.get("size_mm"), "Film width", errors)
        thickness = parse_float(request.form.get("thickness_microns"), "Thickness", errors)
        total_weight = parse_float(request.form.get("total_weight_kg"), "Total order weight", errors)

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("work_order_new.html", product_types=product_types,
                                   customers=customers, next_wo=wo.wo_number,
                                   form=request.form, edit=True, wo=wo)

        wo.product_type = product_type
        wo.customer_id = cust.id if cust else None
        wo.customer_name = cust.name if cust else ""
        wo.size_mm = size_mm
        wo.thickness_microns = thickness
        wo.total_weight_kg = total_weight
        wo.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash("Work Order updated.", "success")
        return redirect(url_for("work_order_detail", wo_id=wo.id))
    return render_template("work_order_new.html", product_types=product_types,
                           customers=customers, next_wo=wo.wo_number,
                           form=wo, edit=True, wo=wo)


@app.route("/work-order/<int:wo_id>/delete", methods=["POST"])
@login_required
@admin_required
def work_order_delete(wo_id):
    wo = WorkOrder.query.get_or_404(wo_id)
    db.session.delete(wo)
    db.session.commit()
    flash(f"Work Order {wo.wo_number} deleted.", "info")
    return redirect(url_for("dashboard"))


# ─── PRODUCTION (operator + admin) ───────────────────────────────────────────

@app.route("/work-order/<int:wo_id>/production", methods=["GET", "POST"])
@login_required
def production(wo_id):
    wo = WorkOrder.query.get_or_404(wo_id)
    if request.method == "POST":
        action = request.form.get("action", "add_roll")

        # Permission model:
        #   admin     → all actions
        #   operator  → full control of production history (add rolls, mark
        #               ready / back to in-production); roll edit & delete are
        #               handled by the roll_edit / roll_delete routes, which
        #               operators are also permitted to use.
        #   supervisor→ read-only on production (no modifying actions)
        role = current_user.role
        if role == "admin" or role == "operator":
            pass  # full access to production actions
        else:
            # supervisor and any other non-production role: read-only
            flash("You don't have permission to modify production.", "error")
            return redirect(url_for("production", wo_id=wo_id))

        if action == "add_roll":
            errors = []
            machine = request.form.get("machine", "RA").upper()
            if machine not in MACHINES:
                errors.append("Please select a valid machine.")
            roll_no = request.form.get("roll_no", "").strip()
            if not roll_no:
                errors.append("Roll number is required.")
            gross = parse_float(request.form.get("gross_weight_kg"), "Gross weight", errors)
            core = parse_float(request.form.get("core_weight_kg"), "Core weight", errors)
            size_mm = parse_float(request.form.get("size_mm"), "Size", errors, default=wo.size_mm)
            thickness = parse_float(request.form.get("thickness_microns"), "Thickness",
                                    errors, default=wo.thickness_microns)
            prod_wt = parse_float(request.form.get("production_weight_kg"), "Production weight", errors)
            net = round(gross - core, 3)
            if not errors and net <= 0:
                errors.append("Net weight must be positive — check that gross is greater than core.")
            # Guard against duplicate roll numbers (DB has no unique constraint on roll_no)
            if roll_no and ProductionRoll.query.filter_by(roll_no=roll_no).first():
                errors.append(f"Roll number '{roll_no}' already exists.")

            if errors:
                for e in errors:
                    flash(e, "error")
                return redirect(url_for("production", wo_id=wo.id))

            roll = ProductionRoll(
                work_order_id=wo.id, machine=machine,
                roll_no=roll_no,
                size_mm=size_mm,
                thickness_microns=thickness,
                production_weight_kg=prod_wt,
                gross_weight_kg=gross, core_weight_kg=core, net_weight_kg=net,
            )
            db.session.add(roll)
            if wo.status == "open":
                wo.status = "in_production"
            db.session.commit()
            flash(f"Roll {roll.roll_no} added. Net: {net} kg", "success")

        elif action == "mark_ready":
            if wo.roll_count == 0:
                flash("Cannot mark Ready — no rolls have been added yet.", "error")
                return redirect(url_for("production", wo_id=wo.id))
            wo.status = "ready"
            db.session.commit()
            flash(f"{wo.wo_number} marked as Ready.", "success")
            return redirect(url_for("dashboard"))

        elif action == "mark_in_production":
            wo.status = "in_production"
            db.session.commit()
            flash(f"{wo.wo_number} moved back to In Production.", "info")

        return redirect(url_for("production", wo_id=wo.id))

    rolls = (ProductionRoll.query.filter_by(work_order_id=wo.id)
             .order_by(ProductionRoll.created_at).all())
    return render_template("production.html", wo=wo, rolls=rolls,
                           machine_choices=MACHINE_CHOICES, machines=MACHINES)


@app.route("/roll/<int:roll_id>/delete", methods=["POST"])
@login_required
@require_permission("production_delete_roll")
def roll_delete(roll_id):
    roll = ProductionRoll.query.get_or_404(roll_id)
    wo_id = roll.work_order_id
    db.session.delete(roll)
    db.session.commit()
    flash(f"Roll {roll.roll_no} removed.", "info")
    return redirect(url_for("production", wo_id=wo_id))


@app.route("/roll/<int:roll_id>/edit", methods=["POST"])
@login_required
@require_permission("production_edit_roll")
def roll_edit(roll_id):
    roll = ProductionRoll.query.get_or_404(roll_id)
    errors = []
    roll_no = request.form.get("roll_no", roll.roll_no).strip()
    if not roll_no:
        errors.append("Roll number is required.")
    machine = request.form.get("machine", roll.machine).upper()
    if machine not in MACHINES:
        errors.append("Invalid machine.")
    size_mm = parse_float(request.form.get("size_mm"), "Size", errors, default=roll.size_mm)
    thickness = parse_float(request.form.get("thickness_microns"), "Thickness", errors, default=roll.thickness_microns)
    prod_wt = parse_float(request.form.get("production_weight_kg"), "Production weight", errors, default=roll.production_weight_kg)
    gross = parse_float(request.form.get("gross_weight_kg"), "Gross weight", errors, default=roll.gross_weight_kg)
    core = parse_float(request.form.get("core_weight_kg"), "Core weight", errors, default=roll.core_weight_kg)
    net = round(gross - core, 3)
    if not errors and net <= 0:
        errors.append("Net weight must be positive — check that gross is greater than core.")
    # Block renaming onto another roll's number
    if roll_no != roll.roll_no:
        dup = ProductionRoll.query.filter_by(roll_no=roll_no).first()
        if dup and dup.id != roll.id:
            errors.append(f"Roll number '{roll_no}' already exists.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("production", wo_id=roll.work_order_id))

    roll.roll_no = roll_no
    roll.machine = machine
    roll.size_mm = size_mm
    roll.thickness_microns = thickness
    roll.production_weight_kg = prod_wt
    roll.gross_weight_kg = gross
    roll.core_weight_kg = core
    roll.net_weight_kg = net
    db.session.commit()
    flash(f"Roll {roll.roll_no} updated.", "success")
    return redirect(url_for("production", wo_id=roll.work_order_id))


# ─── PACKING LISTS (supervisor + admin) ──────────────────────────────────────

@app.route("/packing-lists")
@login_required
def packing_list_index():
    if current_user.role == "operator":
        flash("Operators cannot access packing lists.", "error")
        return redirect(url_for("dashboard"))
    pls = PackingList.query.order_by(PackingList.created_at.desc()).all()
    ready_wos = WorkOrder.query.filter_by(status="ready").all()
    return render_template("packing_list_index.html", packing_lists=pls, ready_wos=ready_wos)


@app.route("/packing-lists/new", methods=["GET", "POST"])
@login_required
@require_permission("packing_list")
def packing_list_new():
    if request.method == "POST":
        wo_ids = request.form.getlist("wo_ids")
        if not wo_ids:
            flash("Select at least one Work Order.", "error")
            return redirect(url_for("packing_list_new"))

        # Re-validate server-side: only Ready WOs not already in a packing list
        # may be included. This guards against stale forms and crafted POSTs.
        already_packed = {item.work_order_id for item in PackingListItem.query.all()}
        valid_wos = []
        skipped = []
        for raw in wo_ids:
            wid = parse_int_id(raw)
            wo = WorkOrder.query.get(wid) if wid is not None else None
            if not wo:
                continue
            if wo.status != "ready" or wo.id in already_packed:
                skipped.append(wo.wo_number)
                continue
            valid_wos.append(wo)

        if not valid_wos:
            flash("None of the selected work orders are eligible "
                  "(they must be Ready and not already packed).", "error")
            return redirect(url_for("packing_list_new"))

        pl = PackingList(pl_number=PackingList.next_pl_number(),
                         notes=request.form.get("notes", "").strip())
        db.session.add(pl)
        db.session.flush()
        for wo in valid_wos:
            db.session.add(PackingListItem(packing_list_id=pl.id, work_order_id=wo.id))
        db.session.commit()
        flash(f"Packing List {pl.pl_number} created.", "success")
        if skipped:
            flash(f"Skipped {', '.join(skipped)} — already packed or not Ready.", "info")
        return redirect(url_for("packing_list_detail", pl_id=pl.id))

    already_packed = {item.work_order_id for item in PackingListItem.query.all()}
    ready_wos = [wo for wo in WorkOrder.query.filter_by(status="ready").all()
                 if wo.id not in already_packed]
    return render_template("packing_list_new.html", ready_wos=ready_wos)


@app.route("/packing-lists/<int:pl_id>")
@login_required
def packing_list_detail(pl_id):
    if current_user.role == "operator":
        flash("Operators cannot access packing lists.", "error")
        return redirect(url_for("dashboard"))
    pl = PackingList.query.get_or_404(pl_id)
    return render_template("packing_list_detail.html", pl=pl,
                           today=date.today().strftime("%d.%m.%y"))


@app.route("/packing-lists/<int:pl_id>/remove-wo", methods=["POST"])
@login_required
@require_permission("packing_list")
def packing_list_remove_wo(pl_id):
    pl = PackingList.query.get_or_404(pl_id)
    wo_id = parse_int_id(request.form.get("wo_id"))
    item = (PackingListItem.query.filter_by(packing_list_id=pl.id, work_order_id=wo_id).first()
            if wo_id is not None else None)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Work Order removed from packing list.", "info")
    return redirect(url_for("packing_list_detail", pl_id=pl.id))


@app.route("/packing-lists/<int:pl_id>/delete", methods=["POST"])
@login_required
@require_permission("packing_list")
def packing_list_delete(pl_id):
    pl = PackingList.query.get_or_404(pl_id)
    if pl.dispatch_memo:
        flash("Cannot delete — delete the Dispatch Memo first.", "error")
        return redirect(url_for("packing_list_detail", pl_id=pl.id))
    for wo in pl.work_orders:
        if wo.status in ("ready", "dispatched"):
            wo.status = "ready"
    db.session.delete(pl)
    db.session.commit()
    flash("Packing List deleted.", "info")
    return redirect(url_for("packing_list_index"))


# ─── DISPATCH MEMOS (supervisor + admin) ─────────────────────────────────────

@app.route("/dispatch-memos")
@login_required
def dm_index():
    if current_user.role == "operator":
        flash("Operators cannot access dispatch memos.", "error")
        return redirect(url_for("dashboard"))
    dms = DispatchMemo.query.order_by(DispatchMemo.created_at.desc()).all()
    undispatched = (PackingList.query
                    .filter(~PackingList.id.in_(
                        db.session.query(DispatchMemo.packing_list_id)))
                    .order_by(PackingList.created_at.desc()).all())
    return render_template("dm_index.html", dms=dms, undispatched=undispatched)


@app.route("/dispatch-memos/new", methods=["GET", "POST"])
@login_required
@require_permission("dispatch_memo")
def dm_new():
    undispatched_pls = (PackingList.query
                        .filter(~PackingList.id.in_(
                            db.session.query(DispatchMemo.packing_list_id)))
                        .order_by(PackingList.created_at.desc()).all())
    if request.method == "POST":
        pl_id = parse_int_id(request.form.get("packing_list_id"))
        pl = PackingList.query.get_or_404(pl_id) if pl_id is not None else None
        if pl is None:
            flash("Please select a valid packing list.", "error")
            return redirect(url_for("dm_new"))
        if pl.dispatch_memo:
            flash("This packing list already has a Dispatch Memo.", "error")
            return redirect(url_for("dm_new"))
        dm_number = request.form.get("dm_number", "").strip()
        if not dm_number:
            flash("DM Number is required.", "error")
            return redirect(url_for("dm_new", pl_id=pl_id))
        if DispatchMemo.query.filter_by(dm_number=dm_number).first():
            flash(f"DM Number '{dm_number}' already exists.", "error")
            return redirect(url_for("dm_new", pl_id=pl_id))
        errors = []
        dispatch_date = parse_date(request.form.get("dispatch_date"), "Dispatch date", errors)
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("dm_new", pl_id=pl_id))
        dm = DispatchMemo(
            packing_list_id=pl.id, dm_number=dm_number,
            dispatch_date=dispatch_date,
            vehicle_number=request.form.get("vehicle_number", "").strip(),
            customer_name=request.form.get("customer_name", "").strip(),
            customer_address=request.form.get("customer_address", "").strip(),
        )
        db.session.add(dm)
        for wo in pl.work_orders:
            wo.status = "dispatched"
        db.session.commit()
        flash(f"Dispatch Memo {dm.dm_number} created.", "success")
        return redirect(url_for("dm_detail", dm_id=dm.id))

    preselect_pl_id = request.args.get("pl_id", type=int)
    preselect_pl = PackingList.query.get(preselect_pl_id) if preselect_pl_id else None
    return render_template("dm_new.html", undispatched_pls=undispatched_pls,
                           preselect_pl=preselect_pl, today=date.today().isoformat())


@app.route("/dispatch-memos/<int:dm_id>")
@login_required
def dm_detail(dm_id):
    if current_user.role == "operator":
        abort(403)
    dm = DispatchMemo.query.get_or_404(dm_id)
    return render_template("dm_detail.html", dm=dm,
                           today=date.today().strftime("%d.%m.%y"))


@app.route("/dispatch-memos/<int:dm_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("dispatch_memo")
def dm_edit(dm_id):
    dm = DispatchMemo.query.get_or_404(dm_id)
    if request.method == "POST":
        errors = []
        dispatch_date = parse_date(request.form.get("dispatch_date"), "Dispatch date", errors)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("dm_edit.html", dm=dm)
        dm.dispatch_date = dispatch_date
        dm.vehicle_number = request.form.get("vehicle_number", "").strip()
        dm.customer_name = request.form.get("customer_name", "").strip()
        dm.customer_address = request.form.get("customer_address", "").strip()
        db.session.commit()
        flash("Dispatch Memo updated.", "success")
        return redirect(url_for("dm_detail", dm_id=dm.id))
    return render_template("dm_edit.html", dm=dm)


@app.route("/dispatch-memos/<int:dm_id>/delete", methods=["POST"])
@login_required
@require_permission("dispatch_memo")
def dm_delete(dm_id):
    dm = DispatchMemo.query.get_or_404(dm_id)
    pl = dm.packing_list
    for wo in pl.work_orders:
        if wo.status == "dispatched":
            wo.status = "ready"
    db.session.delete(dm)
    db.session.commit()
    flash(f"Dispatch Memo {dm.dm_number} deleted. WOs reverted to Ready.", "info")
    return redirect(url_for("packing_list_detail", pl_id=pl.id))


# ─── RECIPES (admin only) ─────────────────────────────────────────────────────

LAYER_NAMES = ["Inner", "Middle", "Outer"]
MAX_GRADES = 6


@app.route("/recipes")
@login_required
@admin_required
def recipe_index():
    recipes = Recipe.query.order_by(Recipe.created_at.desc()).all()
    return render_template("recipe_index.html", recipes=recipes)


@app.route("/recipes/new", methods=["GET", "POST"])
@login_required
@admin_required
def recipe_new():
    product_types = ProductType.active_names()
    if request.method == "POST":
        errors = []
        name = request.form.get("name", "").strip()
        if not name:
            errors.append("Recipe name is required.")

        date_str = request.form.get("recipe_date", "").strip()
        recipe_date = None
        if date_str:
            recipe_date = parse_date(date_str, "Date", errors)

        treatment_na  = request.form.get("treatment_na") == "1"
        t_min_raw = request.form.get("treatment_min", "").strip()
        t_max_raw = request.form.get("treatment_max", "").strip()
        treatment_min = None if treatment_na else (parse_float(t_min_raw, "Treatment (min)", errors, default=None) if t_min_raw else None)
        treatment_max = None if treatment_na else (parse_float(t_max_raw, "Treatment (max)", errors, default=None) if t_max_raw else None)

        # Validate all layer/grade numbers before writing anything
        parsed_layers = []
        for li, layer_name in enumerate(LAYER_NAMES):
            target_kg = parse_float(request.form.get(f"layer_{li}_target_kg"),
                                    f"{layer_name} target kg", errors, default=100)
            grades = []
            for gi in range(MAX_GRADES):
                grade_name = request.form.get(f"layer_{li}_grade_{gi}_name", "").strip()
                pct_str = request.form.get(f"layer_{li}_grade_{gi}_pct", "").strip()
                kg_str = request.form.get(f"layer_{li}_grade_{gi}_kg", "").strip()
                pct = parse_float(pct_str, f"{layer_name} grade {gi+1} %", errors, default=None) if pct_str else None
                kg = parse_float(kg_str, f"{layer_name} grade {gi+1} kg", errors, default=None) if kg_str else None
                grades.append((grade_name, pct, kg))
            parsed_layers.append((layer_name, target_kg, grades))

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("recipe_form.html", recipe=None, product_types=product_types,
                                   layer_names=LAYER_NAMES, max_grades=MAX_GRADES, edit=False,
                                   form=request.form)

        recipe = Recipe(
            name=name,
            recipe_no=request.form.get("recipe_no", "").strip(),
            product_type=request.form.get("product_type", "").strip(),
            layer_ratio=request.form.get("layer_ratio", "1:1:1").strip(),
            notes=request.form.get("notes", "").strip(),
            date=recipe_date,
            treatment_min=treatment_min,
            treatment_max=treatment_max,
            treatment_na=treatment_na,
        )
        db.session.add(recipe)
        db.session.flush()

        for li, (layer_name, target_kg, grades) in enumerate(parsed_layers):
            layer = RecipeLayer(recipe_id=recipe.id, layer_order=li,
                                layer_name=layer_name, target_kg=target_kg)
            db.session.add(layer)
            db.session.flush()
            for gi, (grade_name, pct, kg) in enumerate(grades):
                db.session.add(RecipeGrade(
                    layer_id=layer.id, grade_order=gi,
                    grade_name=grade_name, percentage=pct, kg_amount=kg,
                ))

        db.session.flush()
        # Ensure every named grade exists in the inventory master list
        for _, _, glist in parsed_layers:
            for gname, _, _ in glist:
                if gname:
                    RawMaterial.get_or_create(gname)
        db.session.commit()
        flash(f"Recipe '{recipe.name}' created.", "success")
        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    return render_template("recipe_form.html", recipe=None, product_types=product_types,
                           layer_names=LAYER_NAMES, max_grades=MAX_GRADES, edit=False)


@app.route("/recipes/<int:recipe_id>")
@login_required
@admin_required
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    return render_template("recipe_detail.html", recipe=recipe,
                           layer_names=LAYER_NAMES, max_grades=MAX_GRADES)


@app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def recipe_edit(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    product_types = ProductType.active_names()
    if recipe.product_type and recipe.product_type not in product_types:
        product_types = [recipe.product_type] + product_types

    if request.method == "POST":
        errors = []
        name = request.form.get("name", "").strip()
        if not name:
            errors.append("Recipe name is required.")

        date_str = request.form.get("recipe_date", "").strip()
        new_date = recipe.date
        if date_str:
            new_date = parse_date(date_str, "Date", errors)

        treatment_na  = request.form.get("treatment_na") == "1"
        t_min_raw = request.form.get("treatment_min", "").strip()
        t_max_raw = request.form.get("treatment_max", "").strip()
        treatment_min = None if treatment_na else (parse_float(t_min_raw, "Treatment (min)", errors, default=None) if t_min_raw else None)
        treatment_max = None if treatment_na else (parse_float(t_max_raw, "Treatment (max)", errors, default=None) if t_max_raw else None)

        # Parse all layer/grade numbers first
        layers_sorted = sorted(recipe.layers, key=lambda l: l.layer_order)
        parsed = []
        for li, layer in enumerate(layers_sorted):
            target_kg = parse_float(request.form.get(f"layer_{li}_target_kg"),
                                    f"{layer.layer_name} target kg", errors, default=100)
            grade_vals = []
            for gi, grade in enumerate(sorted(layer.grades, key=lambda g: g.grade_order)):
                gname = request.form.get(f"layer_{li}_grade_{gi}_name", "").strip()
                pct_str = request.form.get(f"layer_{li}_grade_{gi}_pct", "").strip()
                kg_str = request.form.get(f"layer_{li}_grade_{gi}_kg", "").strip()
                pct = parse_float(pct_str, f"{layer.layer_name} grade {gi+1} %", errors, default=None) if pct_str else None
                kg = parse_float(kg_str, f"{layer.layer_name} grade {gi+1} kg", errors, default=None) if kg_str else None
                grade_vals.append((grade, gname, pct, kg))
            parsed.append((layer, target_kg, grade_vals))

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("recipe_form.html", recipe=recipe, product_types=product_types,
                                   layer_names=LAYER_NAMES, max_grades=MAX_GRADES, edit=True)

        recipe.name = name
        recipe.recipe_no = request.form.get("recipe_no", "").strip()
        recipe.product_type = request.form.get("product_type", "").strip()
        recipe.layer_ratio = request.form.get("layer_ratio", "1:1:1").strip()
        recipe.notes = request.form.get("notes", "").strip()
        recipe.date = new_date
        recipe.treatment_na  = treatment_na
        recipe.treatment_min = treatment_min
        recipe.treatment_max = treatment_max
        recipe.updated_at = datetime.utcnow()

        for layer, target_kg, grade_vals in parsed:
            layer.target_kg = target_kg
            for grade, gname, pct, kg in grade_vals:
                grade.grade_name = gname
                grade.percentage = pct
                grade.kg_amount = kg

        db.session.flush()
        for layer, _, grade_vals in parsed:
            for grade, gname, pct, kg in grade_vals:
                if gname:
                    RawMaterial.get_or_create(gname)
        db.session.commit()
        flash(f"Recipe '{recipe.name}' updated.", "success")
        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    return render_template("recipe_form.html", recipe=recipe, product_types=product_types,
                           layer_names=LAYER_NAMES, max_grades=MAX_GRADES, edit=True)


@app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
@login_required
@admin_required
def recipe_delete(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    name = recipe.name
    db.session.delete(recipe)
    db.session.commit()
    flash(f"Recipe '{name}' deleted.", "info")
    return redirect(url_for("recipe_index"))


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/next-wo-number")
@login_required
def api_next_wo_number():
    return jsonify({"wo_number": WorkOrder.next_wo_number()})


@app.route("/api/next-roll-number")
@login_required
def api_next_roll_number():
    machine = request.args.get("machine", "RA").upper()
    if machine not in MACHINES:
        return jsonify({"error": "Invalid machine"}), 400
    return jsonify({"roll_number": ProductionRoll.next_roll_number(machine), "machine": machine})


@app.route("/api/customer-address")
@login_required
def api_customer_address():
    cid = parse_int_id(request.args.get("id"))
    if cid is None:
        return jsonify({"address": ""})
    cust = Customer.query.get(cid)
    return jsonify({"address": cust.address if cust else ""})


@app.route("/api/packing-list-info/<int:pl_id>")
@login_required
def api_pl_info(pl_id):
    pl = PackingList.query.get_or_404(pl_id)
    wos = pl.work_orders
    customer_name = wos[0].customer_name if wos else ""
    customer_address = ""
    if wos and wos[0].customer_id:
        cust = Customer.query.get(wos[0].customer_id)
        if cust:
            customer_address = cust.address
    return jsonify({
        "pl_number": pl.pl_number,
        "wo_numbers": [wo.wo_number for wo in wos],
        "customer_name": customer_name,
        "customer_address": customer_address,
        "total_rolls": pl.total_rolls,
        "total_net_kg": round(pl.total_net_kg, 3),
    })


# ─── ERROR HANDLERS ────────────────────────────────────────────────────────────
# Friendly pages instead of raw tracebacks / terse text. JSON for API paths.

def _wants_json():
    return request.path.startswith("/api/")


@app.errorhandler(400)
def err_400(e):
    msg = getattr(e, "description", "Bad request.")
    if _wants_json():
        return jsonify({"error": msg}), 400
    return render_template("error.html", code=400, title="Bad Request", message=msg), 400


@app.errorhandler(403)
def err_403(e):
    if _wants_json():
        return jsonify({"error": "Forbidden"}), 403
    return render_template("error.html", code=403, title="Access Denied",
                           message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def err_404(e):
    if _wants_json():
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", code=404, title="Not Found",
                           message="That page or record doesn't exist."), 404


@app.errorhandler(500)
def err_500(e):
    db.session.rollback()
    if _wants_json():
        return jsonify({"error": "Server error"}), 500
    return render_template("error.html", code=500, title="Something Went Wrong",
                           message="An unexpected error occurred. Please try again."), 500


# ─── INVENTORY ─────────────────────────────────────────────────────────────────

def _inventory_allowed():
    """Admin or supervisor can manage inventory."""
    return current_user.is_authenticated and current_user.can("inventory")


@app.route("/inventory")
@login_required
def inventory_index():
    if not _inventory_allowed():
        flash("You don't have permission to view inventory.", "error")
        return redirect(url_for("dashboard"))
    materials = (RawMaterial.query
                 .filter_by(is_active=True)
                 .order_by(RawMaterial.name)
                 .all())
    # Flag low stock (below zero = over-committed)
    return render_template("inventory_index.html", materials=materials)


@app.route("/inventory/add-stock", methods=["GET", "POST"])
@login_required
def inventory_add_stock():
    if not _inventory_allowed():
        flash("You don't have permission to manage inventory.", "error")
        return redirect(url_for("dashboard"))

    materials = (RawMaterial.query
                 .filter_by(is_active=True)
                 .order_by(RawMaterial.name)
                 .all())

    if request.method == "POST":
        action = request.form.get("action", "add_stock")

        if action == "add_material":
            # Add a new raw material grade to the master list
            name = request.form.get("mat_name", "").strip()
            desc = request.form.get("mat_desc", "").strip()
            if not name:
                flash("Grade name is required.", "error")
            elif RawMaterial.query.filter_by(name=name).first():
                flash(f"Grade '{name}' already exists.", "error")
            else:
                db.session.add(RawMaterial(name=name, description=desc))
                db.session.commit()
                flash(f"Grade '{name}' added to master list.", "success")
            return redirect(url_for("inventory_add_stock"))

        elif action == "add_stock":
            # Add incoming stock for one or more materials
            entries_added = 0
            for mat in materials:
                qty_str = request.form.get(f"qty_{mat.id}", "").strip()
                if not qty_str:
                    continue
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue
                if qty == 0:
                    continue
                notes = request.form.get(f"notes_{mat.id}", "").strip()
                db.session.add(InventoryLedger(
                    material_id=mat.id,
                    qty_kg=qty,
                    txn_type="incoming",
                    reference=request.form.get("reference", "").strip(),
                    notes=notes,
                    created_by=current_user.username,
                ))
                entries_added += 1
            db.session.commit()
            if entries_added:
                flash(f"Stock updated for {entries_added} grade(s).", "success")
            else:
                flash("No quantities entered.", "info")
            return redirect(url_for("inventory_index"))

    return render_template("inventory_add_stock.html", materials=materials)


@app.route("/inventory/adjust", methods=["POST"])
@login_required
def inventory_adjust():
    """Manual stock adjustment (correction)."""
    if not _inventory_allowed():
        abort(403)
    mat_id = parse_int_id(request.form.get("material_id"))
    if mat_id is None:
        abort(404)
    mat = RawMaterial.query.get_or_404(mat_id)
    qty_str = request.form.get("qty_kg", "").strip()
    try:
        qty = float(qty_str)
    except ValueError:
        flash("Invalid quantity.", "error")
        return redirect(url_for("inventory_index"))

    db.session.add(InventoryLedger(
        material_id=mat.id,
        qty_kg=qty,
        txn_type="adjustment",
        reference="Manual adjustment",
        notes=request.form.get("notes", "").strip(),
        created_by=current_user.username,
    ))
    db.session.commit()
    flash(f"Adjustment of {qty:+.3f} kg applied to {mat.name}.", "success")
    return redirect(url_for("inventory_index"))


@app.route("/inventory/ledger/<int:material_id>")
@login_required
def inventory_ledger(material_id):
    """Full transaction history for one material."""
    if not _inventory_allowed():
        abort(403)
    mat = RawMaterial.query.get_or_404(material_id)
    entries = (InventoryLedger.query
               .filter_by(material_id=material_id)
               .order_by(InventoryLedger.created_at.desc())
               .all())
    return render_template("inventory_ledger.html", mat=mat, entries=entries)


@app.route("/api/recipe-material-preview/<int:recipe_id>")
@login_required
def api_recipe_material_preview(recipe_id):
    """Return material deduction preview for a given recipe + target kg."""
    recipe = Recipe.query.get_or_404(recipe_id)
    try:
        target_kg = float(request.args.get("target_kg", 0) or 0)
    except (ValueError, TypeError):
        target_kg = 0
    batch_kg = recipe.total_kg_net
    if batch_kg <= 0 or target_kg <= 0:
        return jsonify({"items": [], "total_net": 0})

    scale = target_kg / batch_kg
    items = []
    for grade_name, batch_qty in recipe.material_tally.items():
        if not grade_name:
            continue
        deduct = round(batch_qty * scale, 3)
        mat = RawMaterial.query.filter_by(name=grade_name).first()
        current = mat.current_stock_kg if mat else 0.0
        items.append({
            "grade": grade_name,
            "deduct_kg": deduct,
            "current_stock": current,
            "after_stock": round(current - deduct, 3),
            "ok": (current - deduct) >= 0,
        })
    return jsonify({
        "items": items,
        "recipe_name": recipe.name,
        "recipe_batch_kg": batch_kg,
        "target_kg": target_kg,
    })


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "instance"), exist_ok=True)
    # Debug mode is OFF by default so the interactive debugger (which allows
    # arbitrary code execution) is never exposed accidentally. To develop
    # locally with auto-reload, run:  HIC_DEBUG=1 python app.py
    debug_mode = os.environ.get("HIC_DEBUG", "").lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=debug_mode, host="0.0.0.0", port=port)