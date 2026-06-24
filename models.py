from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))  # Indian Standard Time
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ─── PRODUCT TYPES ────────────────────────────────────────────────────────────

class ProductType(db.Model):
    __tablename__ = "product_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    DEFAULT_TYPES = [
        # Lamination Film — Natural
        "Lamination Film Natural GP",
        "Lamination Film Natural Metallocene",
        "Lamination Film Natural Metallocene - EV Grade",
        "Lamination Film Natural Metallocene - Camphor",
        "Lamination Film Natural GP - Agarbatti",
        "Lamination Film Natural Metallocene - Chutney Grade",
        "Lamination Film Natural Metallocene - Easy Peel",
        # Lamination Film — Milky
        "Lamination Film Milky GP",
        "Lamination Film Milky Metallocene",
        "Lamination Film Milky Metallocene - EV Grade",
        # Lamination Film — Other
        "Lamination Film Orange Metallocene",
        # LD
        "LD Shrink",
        "LD Liners",
        "LD Tubing",
        "LD Sheet - OSC - One Side Cut",
        "LD Stretch",
        # VCI / LL
        "VCI Film",
        "VCI Stretch Film",
        "LL Sheet",
    ]

    @classmethod
    def seed_defaults(cls):
        if cls.query.count() == 0:
            for i, name in enumerate(cls.DEFAULT_TYPES):
                db.session.add(cls(name=name, sort_order=i))
            db.session.commit()

    @classmethod
    def active_list(cls):
        return cls.query.filter_by(is_active=True).order_by(cls.sort_order, cls.name).all()

    @classmethod
    def active_names(cls):
        return [pt.name for pt in cls.active_list()]


# ─── CUSTOMERS ────────────────────────────────────────────────────────────────

class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    address = db.Column(db.Text, default="")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    work_orders = db.relationship("WorkOrder", backref="customer", lazy=True)

    @classmethod
    def active_list(cls):
        return cls.query.filter_by(is_active=True).order_by(cls.name).all()


# ─── WORK ORDERS ──────────────────────────────────────────────────────────────

class WorkOrder(db.Model):
    __tablename__ = "work_orders"

    id = db.Column(db.Integer, primary_key=True)
    wo_number = db.Column(db.String(50), unique=True, nullable=False)
    product_type = db.Column(db.String(100), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    customer_name = db.Column(db.String(200), nullable=False)
    size_mm = db.Column(db.Float, nullable=False)
    thickness_microns = db.Column(db.Float, nullable=False)
    total_weight_kg = db.Column(db.Float, nullable=False)
    # Statuses: open | in_production | ready | dispatched
    status = db.Column(db.String(50), default="open", nullable=False)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Recipe link — set at WO creation, drives inventory deduction
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=True)
    inventory_deducted = db.Column(db.Boolean, default=False, nullable=False)

    recipe = db.relationship("Recipe", foreign_keys=[recipe_id], lazy=True)

    rolls = db.relationship("ProductionRoll", backref="work_order", lazy=True,
                            cascade="all, delete-orphan")
    # WO can appear in multiple packing list items
    packing_items = db.relationship("PackingListItem", backref="work_order", lazy=True,
                                    cascade="all, delete-orphan")

    @property
    def total_produced_kg(self):
        return sum(r.net_weight_kg or 0 for r in self.rolls)

    @property
    def total_gross_kg(self):
        return sum(r.gross_weight_kg or 0 for r in self.rolls)

    @property
    def total_core_kg(self):
        return sum(r.core_weight_kg or 0 for r in self.rolls)

    @property
    def roll_count(self):
        return len(self.rolls)

    @property
    def progress_pct(self):
        if self.total_weight_kg == 0:
            return 0
        return min(100, round((self.total_produced_kg / self.total_weight_kg) * 100, 1))

    WO_START = 8000

    @classmethod
    def next_wo_number(cls):
        last = cls.query.filter(cls.wo_number.like("WO%")).order_by(cls.id.desc()).first()
        if last is None:
            return f"WO{cls.WO_START}"
        suffix = last.wo_number[2:]
        try:
            return f"WO{int(suffix) + 1}"
        except ValueError:
            count = cls.query.filter(cls.wo_number.like("WO%")).count()
            return f"WO{cls.WO_START + count}"

    STATUS_LABELS = {
        "open": "Open",
        "in_production": "In Production",
        "ready": "Ready",
        "dispatched": "Dispatched",
    }
    STATUS_COLORS = {
        "open": "status-open",
        "in_production": "status-production",
        "ready": "status-packed",       # reuse green badge
        "dispatched": "status-dispatched",
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_css(self):
        return self.STATUS_COLORS.get(self.status, "")


# ─── PRODUCTION ROLLS ─────────────────────────────────────────────────────────

MACHINES = {
    "RA": {"label": "Raju — Side A", "short": "Raju A", "start": 2000},
    "RB": {"label": "Raju — Side B", "short": "Raju B", "start": 2000},
    "SA": {"label": "Shubham — Side A", "short": "Shubham A", "start": 2000},
    "SB": {"label": "Shubham — Side B", "short": "Shubham B", "start": 2000},
}

MACHINE_CHOICES = [
    ("RA", "Raju — Side A"),
    ("RB", "Raju — Side B"),
    ("SA", "Shubham — Side A"),
    ("SB", "Shubham — Side B"),
]


class ProductionRoll(db.Model):
    __tablename__ = "production_rolls"

    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey("work_orders.id"), nullable=False)
    machine = db.Column(db.String(4), nullable=False, default="RA")
    roll_no = db.Column(db.String(50), nullable=False)
    size_mm = db.Column(db.Float, nullable=False)
    thickness_microns = db.Column(db.Float, nullable=False)
    production_weight_kg = db.Column(db.Float, nullable=False)
    gross_weight_kg = db.Column(db.Float, nullable=False)
    core_weight_kg = db.Column(db.Float, nullable=False)
    net_weight_kg = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def next_roll_number(cls, machine: str) -> str:
        machine = machine.upper()
        start = MACHINES.get(machine, {}).get("start", 2000)
        last = cls.query.filter(cls.machine == machine).order_by(cls.id.desc()).first()
        if last is None:
            return f"{machine}{start}"
        suffix = last.roll_no.upper().replace(machine, "", 1)
        try:
            return f"{machine}{int(suffix) + 1}"
        except ValueError:
            count = cls.query.filter(cls.machine == machine).count()
            return f"{machine}{start + count}"

    def recalculate_net(self):
        self.net_weight_kg = round(self.gross_weight_kg - self.core_weight_kg, 3)


# ─── PACKING LISTS ────────────────────────────────────────────────────────────

class PackingList(db.Model):
    """An independent packing document grouping one or more work orders."""
    __tablename__ = "packing_lists"

    id = db.Column(db.Integer, primary_key=True)
    pl_number = db.Column(db.String(50), unique=True, nullable=False)  # e.g. PL-2026-0001
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, default="")

    items = db.relationship("PackingListItem", backref="packing_list", lazy=True,
                            cascade="all, delete-orphan")
    # A packing list can have one dispatch memo
    dispatch_memo = db.relationship("DispatchMemo", backref="packing_list",
                                    uselist=False, lazy=True, cascade="all, delete-orphan")

    @classmethod
    def next_pl_number(cls):
        year = datetime.utcnow().year
        count = cls.query.filter(cls.pl_number.like(f"PL-{year}-%")).count() + 1
        return f"PL-{year}-{count:04d}"

    @property
    def work_orders(self):
        return [item.work_order for item in self.items]

    @property
    def total_rolls(self):
        return sum(wo.roll_count for wo in self.work_orders)

    @property
    def total_net_kg(self):
        return sum(wo.total_produced_kg for wo in self.work_orders)

    @property
    def total_gross_kg(self):
        return sum(wo.total_gross_kg for wo in self.work_orders)

    @property
    def total_core_kg(self):
        return sum(wo.total_core_kg for wo in self.work_orders)


class PackingListItem(db.Model):
    """Join table: one row per WO included in a packing list."""
    __tablename__ = "packing_list_items"

    id = db.Column(db.Integer, primary_key=True)
    packing_list_id = db.Column(db.Integer, db.ForeignKey("packing_lists.id"), nullable=False)
    work_order_id = db.Column(db.Integer, db.ForeignKey("work_orders.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─── DISPATCH MEMOS ───────────────────────────────────────────────────────────

class DispatchMemo(db.Model):
    """Delivery memo for a packing list — covers all WOs in the list."""
    __tablename__ = "dispatch_memos"

    id = db.Column(db.Integer, primary_key=True)
    packing_list_id = db.Column(db.Integer, db.ForeignKey("packing_lists.id"), nullable=False)
    dm_number = db.Column(db.String(50), unique=True, nullable=False)  # numeric, e.g. "5410"
    dispatch_date = db.Column(db.Date, nullable=False)
    vehicle_number = db.Column(db.String(50), default="")
    # Customer info copied at dispatch time (DMs can span multiple customers)
    customer_name = db.Column(db.String(200), default="")
    customer_address = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def next_dm_number(cls):
        """Simple sequential integer DM number starting at 5000."""
        last = cls.query.order_by(cls.id.desc()).first()
        if last is None:
            return "5000"
        try:
            return str(int(last.dm_number) + 1)
        except ValueError:
            return str(cls.query.count() + 5000)


# ─── USERS (authentication) ───────────────────────────────────────────────────

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

ROLES = {
    "admin":      "Admin",
    "operator":   "Operator",
    "supervisor": "Supervisor",
}

# Role permissions map — what each role can do
ROLE_PERMISSIONS = {
    "admin":      {"all"},                                     # unrestricted
    "operator":   {"production_add_roll", "production_edit_roll",
                "production_delete_roll", "production_mark_ready"},
    "supervisor": {"packing_list", "dispatch_memo", "inventory"},  # pack + dispatch + inventory
}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operator")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def role_label(self):
        return ROLES.get(self.role, self.role)

    def can(self, permission):
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return "all" in perms or permission in perms

    @classmethod
    def seed_admin(cls):
        """Create default admin account if no users exist."""
        if cls.query.count() == 0:
            admin = cls(username="admin", role="admin")
            admin.set_password("hic2024")
            db.session.add(admin)
            db.session.commit()


# ─── RECIPES ──────────────────────────────────────────────────────────────────

class Recipe(db.Model):
    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)           # e.g. "Lamination Chutney Grade"
    recipe_no = db.Column(db.String(50), default="")           # e.g. "Nov 22"
    product_type = db.Column(db.String(100), default="")       # link to product type name
    date = db.Column(db.Date, nullable=True)
    treatment_min = db.Column(db.Float, nullable=True)         # e.g. 44 Dynes
    treatment_max = db.Column(db.Float, nullable=True)         # e.g. 46 Dynes
    treatment_na  = db.Column(db.Boolean, default=False, nullable=False)  # True = N/A
    layer_ratio = db.Column(db.String(50), default="1:1:1")    # e.g. "1:1:1"
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    layers = db.relationship("RecipeLayer", backref="recipe", lazy=True,
                             cascade="all, delete-orphan",
                             order_by="RecipeLayer.layer_order")

    @property
    def all_grades(self):
        """Flat list of all grades across all layers for the material tally."""
        grades = []
        for layer in self.layers:
            grades.extend(layer.grades)
        return grades

    @property
    def material_tally(self):
        """Aggregate kg per grade name across all layers."""
        tally = {}
        for grade in self.all_grades:
            if grade.grade_name and grade.kg_amount:
                tally[grade.grade_name] = tally.get(grade.grade_name, 0) + grade.kg_amount
        return tally

    @property
    def total_kg_net(self):
        return sum(self.material_tally.values())

    @property
    def total_kg_gross(self):
        return round(self.total_kg_net * 1.03, 3)


class RecipeLayer(db.Model):
    __tablename__ = "recipe_layers"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    layer_order = db.Column(db.Integer, nullable=False)        # 0=Inner, 1=Middle, 2=Outer
    layer_name = db.Column(db.String(50), nullable=False)      # "Inner", "Middle", "Outer"
    target_kg = db.Column(db.Float, default=100.0)             # total kg for this layer

    grades = db.relationship("RecipeGrade", backref="layer", lazy=True,
                             cascade="all, delete-orphan",
                             order_by="RecipeGrade.grade_order")

    @property
    def total_pct(self):
        return sum(g.percentage or 0 for g in self.grades)

    @property
    def total_kg(self):
        return sum(g.kg_amount or 0 for g in self.grades)


class RecipeGrade(db.Model):
    __tablename__ = "recipe_grades"

    id = db.Column(db.Integer, primary_key=True)
    layer_id = db.Column(db.Integer, db.ForeignKey("recipe_layers.id"), nullable=False)
    grade_order = db.Column(db.Integer, nullable=False)        # 0–5 (up to 6 grades per layer)
    grade_name = db.Column(db.String(100), default="")         # e.g. "F19010", "1005FY20"
    percentage = db.Column(db.Float, nullable=True)            # e.g. 20.0
    kg_amount = db.Column(db.Float, nullable=True)             # e.g. 20.0


# ─── INVENTORY ────────────────────────────────────────────────────────────────

class RawMaterial(db.Model):
    """Master list of raw material grades used in recipes and tracked in inventory."""
    __tablename__ = "raw_materials"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)   # e.g. "F19010"
    description = db.Column(db.String(200), default="")
    unit = db.Column(db.String(10), default="kg")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ledger_entries = db.relationship("InventoryLedger", backref="material",
                                     lazy=True, cascade="all, delete-orphan")

    @property
    def current_stock_kg(self):
        """Live stock = sum of all ledger qty entries for this material."""
        return round(sum(e.qty_kg for e in self.ledger_entries), 3)

    @property
    def total_in_kg(self):
        return round(sum(e.qty_kg for e in self.ledger_entries if e.qty_kg > 0), 3)

    @property
    def total_out_kg(self):
        return round(abs(sum(e.qty_kg for e in self.ledger_entries if e.qty_kg < 0)), 3)

    @classmethod
    def get_or_create(cls, name):
        """Find or create a RawMaterial by name (used when syncing from recipes)."""
        name = name.strip()
        m = cls.query.filter_by(name=name).first()
        if not m:
            m = cls(name=name)
            db.session.add(m)
            db.session.flush()
        return m


class InventoryLedger(db.Model):
    """Every stock movement — positive = in, negative = out."""
    __tablename__ = "inventory_ledger"

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("raw_materials.id"), nullable=False)
    qty_kg = db.Column(db.Float, nullable=False)              # + incoming, - outgoing
    txn_type = db.Column(db.String(30), nullable=False)       # incoming | work_order | adjustment
    reference = db.Column(db.String(100), default="")         # e.g. "WO8000", "Manual adj."
    notes = db.Column(db.Text, default="")
    created_by = db.Column(db.String(80), default="")         # username
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    TXN_LABELS = {
        "incoming":   "Stock In",
        "work_order": "WO Deduction",
        "adjustment": "Adjustment",
    }

    @property
    def txn_label(self):
        return self.TXN_LABELS.get(self.txn_type, self.txn_type)

    @property
    def customer_name(self):
        """Look up customer name when this entry was caused by a work order."""
        if self.txn_type == "work_order" and self.reference:
            wo = WorkOrder.query.filter_by(wo_number=self.reference).first()
            if wo:
                return wo.customer_name
        return ""


# ─── WORKERS (name list for attendance) ───────────────────────────────────────

class Worker(db.Model):
    """Named floor worker — used as a consistent picker in attendance logging."""
    __tablename__ = "workers"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False, unique=True)
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Worker {self.name}>"


# ─── ATTENDANCE PHOTOS ────────────────────────────────────────────────────────

class AttendancePhoto(db.Model):
    """Daily shift attendance photo — one record per photo taken at shift start."""
    __tablename__ = "attendance_photos"

    id          = db.Column(db.Integer, primary_key=True)
    worker_name = db.Column(db.String(100), nullable=False)
    shift       = db.Column(db.String(20),  nullable=False)   # Morning / Evening / Night
    shift_date  = db.Column(db.Date,        nullable=False)
    photo_filename = db.Column(db.String(200), nullable=False)
    notes       = db.Column(db.Text, default="")
    taken_by    = db.Column(db.String(80),  nullable=False)   # username
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    SHIFTS = ["Morning", "Evening"]


# ─── ROLL PHOTOS ──────────────────────────────────────────────────────────────

class RollPhoto(db.Model):
    """Photo of a production roll, typically taken before dispatch."""
    __tablename__ = "roll_photos"

    id             = db.Column(db.Integer, primary_key=True)
    roll_id        = db.Column(db.Integer, db.ForeignKey("production_rolls.id"),
                               nullable=False)
    photo_filename = db.Column(db.String(200), nullable=False)
    notes          = db.Column(db.Text, default="")
    taken_by       = db.Column(db.String(80), nullable=False)  # username
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    roll = db.relationship("ProductionRoll", backref="photos", lazy=True)
