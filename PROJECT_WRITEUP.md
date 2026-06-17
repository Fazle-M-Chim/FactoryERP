# HIC Industries — Production Management System
## Complete Technical Reference & Code Writeup

**Version:** 1.0 (Local Production Build)  
**Last Updated:** June 2026  
**Status:** Active — running locally, not yet deployed  
**Default Login:** username `admin` / password `hic2024` — change immediately on first run

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [How to Run It](#2-how-to-run-it)
3. [Architecture Overview](#3-architecture-overview)
4. [Technology Stack](#4-technology-stack)
5. [File Structure](#5-file-structure)
6. [Database Schema — All Tables Explained](#6-database-schema)
7. [Authentication & Role System](#7-authentication--role-system)
8. [The Five-Stage Workflow](#8-the-five-stage-workflow)
9. [Every Route Explained (app.py)](#9-every-route-explained)
10. [Every Model Explained (models.py)](#10-every-model-explained)
11. [Inventory System](#11-inventory-system)
12. [Recipe System](#12-recipe-system)
13. [Print Documents](#13-print-documents)
14. [Frontend — Templates & CSS](#14-frontend)
15. [Responsive Design](#15-responsive-design)
16. [Known Limitations & Planned Work](#16-known-limitations--planned-work)

---

## 1. What This System Does

HIC Industries is a plastic film manufacturing factory. This system replaces paper-based tracking of the entire production lifecycle — from receiving a customer order to dispatching and billing the product.

The core business process this software models:

1. A customer orders a specific plastic film product. The order specifies: product type (e.g. Lamination Film Natural Metallocene), width in mm, thickness in microns, and total weight in kg.
2. The factory produces individual **rolls** of film on one of four machine sides (Raju Side A/B, Shubham Side A/B). Each roll weighs roughly 25–30 kg. A 1000 kg order produces ~35–40 rolls.
3. Each roll is weighed. Three weights are recorded: Production Weight (core + film), Gross Weight (production + packaging wrap), Core Weight (the paper tube the film wraps around). Net Weight = Gross − Core, and is calculated automatically.
4. When all rolls are done, the work order is marked **Ready**.
5. Multiple Ready work orders can be grouped into a **Packing List** document.
6. A **Dispatch Memo (DM)** is generated for the packing list — this is the physical delivery document that goes with the truck.
7. The factory also tracks raw material **inventory** — which grades of plastic resin are in stock, how much, and deducts the correct amounts automatically when a work order is created (based on the product **Recipe**).

---

## 2. How to Run It

```bash
# Navigate to project folder
cd hic_project

# Install dependencies (first time only)
pip install flask flask-sqlalchemy flask-login werkzeug

# Start the server
python app.py

# Open in browser
# http://127.0.0.1:5000

# Login with:
# Username: admin
# Password: hic2024
```

The SQLite database (`instance/hic.db`) is **created automatically** on first run. All tables are created, default product types are seeded, and the admin user is created — all without any manual setup.

### ⚠️ When to delete the database

If you change the database schema (add columns, add tables), the old `hic.db` must be deleted and the app restarted. SQLAlchemy does not automatically migrate existing databases. All data will be lost, so back up the file first.

---

## 3. Architecture Overview

```
Browser (any device)
       │
       │  HTTP requests
       ▼
Flask Application (app.py)
  ├── @login_required + role decorators guard every route
  ├── Routes read/write data via SQLAlchemy ORM
  ├── Render Jinja2 HTML templates
  └── Return JSON for API endpoints
       │
       ▼
SQLAlchemy ORM (models.py)
  └── Translates Python objects ↔ SQL queries
       │
       ▼
SQLite database (instance/hic.db)
  └── Single file, no server required
```

The application is **server-rendered**. Every page is a full HTML response from Flask. There is no separate frontend framework (no React, no Vue). JavaScript is used only for:
- Auto-calculating net weight from gross − core
- Fetching next roll/WO numbers from the API
- The hamburger sidebar toggle on mobile
- The material deduction preview when creating a work order
- Opening the inline roll edit form

---

## 4. Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Web framework | Flask 3.x (Python) | Lightweight, minimal setup, easy to run locally |
| ORM / Database layer | Flask-SQLAlchemy | Clean Python object mapping, no raw SQL |
| Database | SQLite | Zero-configuration, single file, no server |
| Authentication | Flask-Login | Session management, login_required decorator |
| Password hashing | Werkzeug (bundled with Flask) | Industry-standard bcrypt hashing |
| Templates | Jinja2 (bundled with Flask) | Server-side HTML rendering, inheritance |
| Styling | Custom CSS (~2300 lines) | Full design control, no framework dependency |
| JavaScript | Vanilla JS | No build step, no npm, no bundler |
| Fonts | Inter (Google Fonts) | Clean, readable, professional |

---

## 5. File Structure

```
hic_project/
├── app.py                        # All Flask routes and application logic (~1000 lines)
├── models.py                     # All SQLAlchemy database models (~495 lines)
├── PROJECT_WRITEUP.md            # This document
│
├── instance/
│   └── hic.db                    # SQLite database (auto-created, not in git)
│
├── static/
│   ├── css/
│   │   └── style.css             # Complete stylesheet (~2300 lines)
│   └── js/
│       └── main.js               # Auto-dismiss flash messages, net weight calc
│
└── templates/                    # Jinja2 HTML templates (22 files)
    ├── base.html                 # Master layout — sidebar, topbar, flash messages, JS
    ├── login.html                # Standalone login page (no sidebar)
    │
    ├── dashboard.html            # Work orders list with status counts
    ├── work_order_new.html       # Create / edit work order
    ├── work_order_detail.html    # Work order detail view
    ├── production.html           # Log production rolls for one WO
    │
    ├── packing_list_index.html   # List all packing lists
    ├── packing_list_new.html     # Create packing list — select multiple WOs
    ├── packing_list_detail.html  # View packing list + printable document
    │
    ├── dm_index.html             # List all dispatch memos
    ├── dm_new.html               # Create dispatch memo
    ├── dm_detail.html            # View DM + printable delivery memo
    ├── dm_edit.html              # Edit DM details
    │
    ├── recipe_index.html         # List all recipes
    ├── recipe_form.html          # Create / edit recipe (layers + grades)
    ├── recipe_detail.html        # View recipe in handwritten-style format + print
    │
    ├── inventory_index.html      # Current stock levels for all grades
    ├── inventory_add_stock.html  # Add incoming stock / new grade
    ├── inventory_ledger.html     # Transaction history for one grade
    │
    ├── customers.html            # Manage customers
    ├── product_types.html        # Manage product type dropdown
    └── users.html                # Manage user accounts (admin only)
```

---

## 6. Database Schema

The database has **12 tables**. Here is every table, every column, what it stores, and how tables relate to each other.

### Relationships diagram (simplified)

```
User
ProductType
Customer ──────────────────────┐
                               │ customer_id FK
WorkOrder ─────────────────────┘
  │ recipe_id FK ──────────────────── Recipe
  │                                     │
  ├─── ProductionRoll                   ├─── RecipeLayer
  │                                     │       └─── RecipeGrade
  └─── PackingListItem ──────────────── PackingList
                                          └─── DispatchMemo

RawMaterial
  └─── InventoryLedger (reference: WO number)
```

---

### Table: `product_types`

Stores the dropdown list of film product types shown in the Work Order form.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | VARCHAR(100) | Unique. e.g. "Lamination Film Natural Metallocene" |
| `is_active` | BOOLEAN | False = hidden from dropdowns, preserved in existing WOs |
| `sort_order` | INTEGER | Controls display order in dropdown |
| `created_at` | DATETIME | Auto-set |

**Seeded automatically** on first run with 19 types (all Lamination Film variants, LD products, VCI, LL Sheet). Only seeded when the table is empty.

**`active_names()`** — class method returning just the names of active types, used to populate dropdowns.

---

### Table: `customers`

Stores customer company records.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | VARCHAR(200) | Unique company name |
| `address` | TEXT | Delivery address, used on Dispatch Memos |
| `is_active` | BOOLEAN | False = hidden from WO dropdown |
| `created_at` | DATETIME | Auto-set |

**Relationship:** One customer → many work orders (via `customer_id` FK on `work_orders`).

**Name sync:** When a customer is renamed, `app.py` updates the denormalised `customer_name` field on all their existing work orders automatically, so historical records stay readable even if the customer name changes.

---

### Table: `work_orders`

The central table. One row per customer order.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `wo_number` | VARCHAR(50) | Unique. Sequential: WO8000, WO8001, ... Auto-suggested but editable |
| `product_type` | VARCHAR(100) | Copied from ProductType name at creation time |
| `customer_id` | INTEGER FK | References `customers.id`. Nullable (legacy safety) |
| `customer_name` | VARCHAR(200) | Denormalised copy of customer name. Stays correct even if customer is later renamed |
| `size_mm` | FLOAT | Film width in millimetres |
| `thickness_microns` | FLOAT | Film thickness in microns |
| `total_weight_kg` | FLOAT | Target order weight in kg |
| `status` | VARCHAR(50) | See status flow below |
| `notes` | TEXT | Free-text notes |
| `created_at` | DATETIME | Auto-set |
| `recipe_id` | INTEGER FK | References `recipes.id`. Optional — links the WO to a formula |
| `inventory_deducted` | BOOLEAN | True once inventory has been deducted for this WO |

**Status flow:**
```
open → in_production → ready → dispatched
```
- `open`: just created, no rolls added yet
- `in_production`: first roll has been logged
- `ready`: production complete, awaiting packing (set by operator/admin)
- `dispatched`: included in a Dispatch Memo

**WO number generation:** `next_wo_number()` finds the most recently created WO with a "WO" prefix, strips the prefix, increments the number by 1. Starts at WO8000. The result is pre-filled in the form but the user can edit it. A database UNIQUE constraint catches accidental duplicates.

**Computed properties** (Python `@property` — not stored in DB, calculated on the fly):
- `total_produced_kg` — sum of `net_weight_kg` across all production rolls
- `total_gross_kg` — sum of gross weights
- `total_core_kg` — sum of core weights
- `roll_count` — number of rolls linked to this WO
- `progress_pct` — `(total_produced_kg / total_weight_kg) * 100`, capped at 100

---

### Table: `production_rolls`

One row per physical roll of film produced for a work order.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `work_order_id` | INTEGER FK | References `work_orders.id`. Cascade delete |
| `machine` | VARCHAR(4) | One of: RA, RB, SA, SB |
| `roll_no` | VARCHAR(50) | e.g. "RA2000". Auto-suggested per machine, editable |
| `size_mm` | FLOAT | Inherited from WO by default, editable per roll |
| `thickness_microns` | FLOAT | Inherited from WO by default, editable |
| `production_weight_kg` | FLOAT | Core + film weight on the machine |
| `gross_weight_kg` | FLOAT | Production weight + outer packaging wrap |
| `core_weight_kg` | FLOAT | Weight of the paper tube the film winds onto |
| `net_weight_kg` | FLOAT | = gross − core. Calculated by server and stored |
| `created_at` | DATETIME | Auto-set |

**Machine codes:**
- `RA` = Raju, Side A
- `RB` = Raju, Side B
- `SA` = Shubham, Side A
- `SB` = Shubham, Side B

**Roll number sequences:** Each machine has its own global sequence starting at 2000. RA2000, RA2001 ... independent of other machines and spanning all work orders. `next_roll_number(machine)` queries the last roll for that machine and increments by 1.

**Cascade delete:** When a work order is deleted, all its production rolls are automatically deleted too.

---

### Table: `packing_lists`

An independent grouping document covering one or more work orders ready for dispatch.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `pl_number` | VARCHAR(50) | Unique. Auto-generated: PL-2026-0001, PL-2026-0002, ... |
| `created_at` | DATETIME | Auto-set |
| `notes` | TEXT | Optional |

**PL number generation:** `next_pl_number()` counts existing PLs for the current year and formats as `PL-YYYY-NNNN`.

**Computed properties:**
- `work_orders` — list of WorkOrder objects via the join table
- `total_rolls`, `total_net_kg`, `total_gross_kg`, `total_core_kg` — summed across all linked WOs

---

### Table: `packing_list_items`

Join table linking packing lists to work orders. Many-to-many in principle, but in practice one WO appears in at most one active PL at a time.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `packing_list_id` | INTEGER FK | References `packing_lists.id`. Cascade delete |
| `work_order_id` | INTEGER FK | References `work_orders.id`. Cascade delete |
| `added_at` | DATETIME | When the WO was added to this PL |

---

### Table: `dispatch_memos`

One delivery memo per packing list. The physical transport document.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `packing_list_id` | INTEGER FK | References `packing_lists.id`. One-to-one |
| `dm_number` | VARCHAR(50) | Unique. **Manually entered** by user (matches physical booklet) |
| `dispatch_date` | DATE | Date of dispatch |
| `vehicle_number` | VARCHAR(50) | Truck/vehicle registration |
| `customer_name` | VARCHAR(200) | Copied from WO at dispatch time |
| `customer_address` | TEXT | Copied from customer record at dispatch time |
| `created_at` | DATETIME | Auto-set |

**DM number:** Unlike other numbers in the system, the DM number is entered manually by the admin/supervisor. This matches the physical pre-printed delivery memo booklet used in the factory. Duplicate DM numbers are rejected at the database level (UNIQUE constraint) and also checked in the route before saving.

**Deleting a DM:** When a DM is deleted, all work orders in its packing list are reverted from `dispatched` back to `ready` status so they can be re-dispatched with a corrected memo.

---

### Table: `users`

User accounts for authentication.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(80) | Unique |
| `password_hash` | VARCHAR(200) | Bcrypt hash via Werkzeug. Plain password never stored |
| `role` | VARCHAR(20) | One of: admin, operator, supervisor |
| `is_active` | BOOLEAN | False = login rejected even with correct password |
| `created_at` | DATETIME | Auto-set |

**Seeded automatically:** If the `users` table is empty on first run, an admin account is created with username `admin` and password `hic2024`.

---

### Table: `recipes`

A formula for making a specific film product. Defines the composition of each layer.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | VARCHAR(200) | e.g. "Lamination Chutney Grade" |
| `recipe_no` | VARCHAR(50) | Reference number from physical binder, e.g. "Nov 22" |
| `product_type` | VARCHAR(100) | Which product type this recipe is for |
| `date` | DATE | Date the recipe was written |
| `treatment_min` | FLOAT | Minimum corona treatment in Dynes |
| `treatment_max` | FLOAT | Maximum corona treatment in Dynes |
| `layer_ratio` | VARCHAR(50) | e.g. "1:1:1" — thickness ratio between layers |
| `notes` | TEXT | Free text |
| `created_at` | DATETIME | Auto-set |
| `updated_at` | DATETIME | Auto-updated on edit |

**`material_tally`** — computed property that aggregates kg amounts across all layers. If GradeA appears in Inner (20 kg) and Middle (80 kg), the tally returns `{"GradeA": 100}`. This is used for the inventory deduction calculation.

**`total_kg_net`** — sum of all grade kg amounts across all layers. Represents one batch of production.

**`total_kg_gross`** — `total_kg_net × 1.03`. The 3% factor accounts for material wastage and is the quantity you need to order from suppliers.

---

### Table: `recipe_layers`

One row per layer (Inner, Middle, Outer) for each recipe.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `recipe_id` | INTEGER FK | References `recipes.id`. Cascade delete |
| `layer_order` | INTEGER | 0 = Inner, 1 = Middle, 2 = Outer |
| `layer_name` | VARCHAR(50) | "Inner", "Middle", "Outer" |
| `target_kg` | FLOAT | Target production weight for this layer (default 100 kg) |

**Computed properties:**
- `total_pct` — sum of percentages across all grades in this layer (should = 100)
- `total_kg` — sum of kg amounts across all grades

---

### Table: `recipe_grades`

One row per raw material grade within a layer. Up to 6 grades per layer.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `layer_id` | INTEGER FK | References `recipe_layers.id`. Cascade delete |
| `grade_order` | INTEGER | 0–5, controls display order |
| `grade_name` | VARCHAR(100) | e.g. "F19010", "1005FY20", "1018RK" |
| `percentage` | FLOAT | Percentage of this grade in the layer (0–100) |
| `kg_amount` | FLOAT | Actual kg of this grade (for the target_kg batch) |

---

### Table: `raw_materials`

Master list of raw material grade names tracked in inventory.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | VARCHAR(100) | Unique. Matches grade names used in recipes |
| `description` | VARCHAR(200) | Optional description |
| `unit` | VARCHAR(10) | Always "kg" |
| `is_active` | BOOLEAN | False = hidden from inventory views |
| `created_at` | DATETIME | Auto-set |

**Auto-sync:** On every request, the `before_request` function scans all `recipe_grades` and calls `get_or_create()` for each grade name, ensuring every grade mentioned in any recipe automatically appears in the inventory master list.

**`current_stock_kg`** — computed from summing all ledger entries. No stock column is stored — the ledger IS the stock. This means stock is always provably correct by examining the audit trail.

---

### Table: `inventory_ledger`

Every single stock movement, ever. The ledger is append-only — nothing is ever deleted or modified.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `material_id` | INTEGER FK | References `raw_materials.id`. Cascade delete |
| `qty_kg` | FLOAT | **Positive = stock in, Negative = stock out** |
| `txn_type` | VARCHAR(30) | "incoming", "work_order", or "adjustment" |
| `reference` | VARCHAR(100) | e.g. "WO8000", "INV-001", "Manual adjustment" |
| `notes` | TEXT | Optional description |
| `created_by` | VARCHAR(80) | Username of person who created this entry |
| `created_at` | DATETIME | Auto-set |

**Transaction types:**
- `incoming` — stock received from supplier. qty_kg is positive.
- `work_order` — materials consumed by a work order. qty_kg is negative.
- `adjustment` — manual correction. qty_kg can be positive or negative.

**Current stock formula:** `SELECT SUM(qty_kg) FROM inventory_ledger WHERE material_id = X`

This ledger-based approach means you can always trace exactly where stock went, which work orders used it, and who recorded each movement.

---

## 7. Authentication & Role System

### Login flow

1. User visits any page → Flask-Login checks if session has a valid user ID
2. If not authenticated → redirect to `/login`
3. User submits username + password → Flask looks up user by username → calls `check_password()` which uses Werkzeug's `check_password_hash()` → if valid, calls `login_user()` which stores user ID in the Flask session cookie
4. All subsequent requests → Flask-Login calls `load_user(user_id)` to load the user from DB into `current_user`
5. Logout → `logout_user()` clears the session

Passwords are never stored in plain text. Werkzeug uses PBKDF2-HMAC-SHA256 by default.

### Role definitions

```python
ROLE_PERMISSIONS = {
    "admin":      {"all"},         # unrestricted — passes every permission check
    "operator":   {
        "production_add_roll",     # add rolls to a WO
        "production_edit_roll",    # edit existing rolls
        "production_delete_roll",  # remove rolls
        "production_mark_ready",   # mark WO as ready / back to in_production
    },
    "supervisor": {
        "packing_list",            # create/edit/delete packing lists
        "dispatch_memo",           # create/edit/delete dispatch memos
        "inventory",               # view/edit inventory stock
    },
}
```

### Route protection — two decorators

**`@admin_required`** — checks `current_user.role == "admin"`. Used on: WO creation/edit/delete, customer management, product type management, user management, recipes.

**`@require_permission(permission)`** — calls `current_user.can(permission)`. The `can()` method returns True if the user's role has `"all"` in its permission set OR if the specific permission string is in the set. Used on: roll edit/delete, packing list operations, dispatch memo operations.

**Operator production access** — the production route handles all production actions in one route. The route checks `action` and whether the user is an operator:
```python
operator_allowed = {"add_roll", "mark_ready", "mark_in_production"}
if action not in operator_allowed and current_user.role == "operator":
    flash("You don't have permission for that action.", "error")
```
This means operators see the full production page but can only trigger the permitted actions.

### What each role can see in the sidebar

- **Admin:** everything — Dashboard, New Work Order, Production, Packing Lists, Dispatch Memos, Inventory, Recipes, Customers, Product Types, Users
- **Supervisor:** Dashboard, Production (read-only), Packing Lists, Dispatch Memos, Inventory
- **Operator:** Dashboard, Production (full for their WOs)

Sidebar links are wrapped in `{% if current_user.role == 'admin' %}` guards in `base.html`.

---

## 8. The Five-Stage Workflow

### Overview

The workflow is **non-linear**. Work orders are created by admin, production is logged by operators, and packing/dispatch is done by supervisors — all independently, not as a locked sequential pipeline.

```
[Admin creates WO] → dashboard
[Operator logs rolls] → production page → mark ready → dashboard
[Supervisor creates Packing List from ready WOs]
[Supervisor creates Dispatch Memo from packing list]
```

### Stage 1 — Work Order (Admin only)

Route: `GET/POST /work-order/new`

Admin fills in: WO number (auto-suggested as WO8000, WO8001...), customer (dropdown), product type (dropdown), film width, thickness, total order weight, and optionally a recipe.

If a recipe is selected:
- The route calculates `scale = target_kg / recipe.total_kg_net`
- For each grade in the recipe's material tally, it creates a negative `InventoryLedger` entry: `qty_kg = -(grade_kg × scale)`
- Sets `wo.inventory_deducted = True`

Before submission, JavaScript fetches `/api/recipe-material-preview/<recipe_id>?target_kg=<n>` and shows a live table of what will be deducted and whether each grade has sufficient stock.

### Stage 2 — Production (Operator + Admin)

Route: `GET/POST /work-order/<id>/production`

The operator selects a machine (RA/RB/SA/SB), gets a pre-filled roll number (e.g. RA2000 — fetched from `/api/next-roll-number?machine=RA`), and enters weights. Net weight is auto-calculated in JavaScript (gross − core) and the server recalculates it again on save.

The production history table has a machine filter toggle (Both / Raju / Shubham) that filters rows client-side. Each row has inline Edit (expands the row into a form) and Remove buttons.

When production is complete, the operator clicks "Mark as Ready" → WO status becomes `ready` → redirect to dashboard.

### Stage 3 — Packing List (Supervisor + Admin)

Route: `GET/POST /packing-lists/new`

A table of all `ready` work orders with checkboxes. Supervisor selects any combination and creates one Packing List covering all of them. The PL gets an auto-number (PL-2026-0001).

The detail page shows one sub-table per WO, with all rolls and weights. The print preview generates one packing document per WO using the popup print method (no browser title/URL).

The packing list document format matches the physical format used in the factory:
- Row 1: PACKING LIST — [CUSTOMER NAME] (centred, bold)
- Row 2: Product spec (e.g. LAMINATION FILM NAT. MET. 1135 MM × 20 MIC.)
- Columns: SR NO. / ROLL NO. / GROSS WT. / CORE WT. / NET WT.
- TOTAL row
- Right sidebar: DATE / WO. NO. / DM NO. (DM NO. is editable before printing)

### Stage 4 — Dispatch Memo (Supervisor + Admin)

Route: `GET/POST /dispatch-memos/new`

Select a packing list (that doesn't already have a DM), enter the DM number (from the physical pre-printed booklet), dispatch date, vehicle number, customer name and address.

On submit: all WOs in the PL are set to `dispatched`. The DM number is validated as unique.

The printed DM matches the physical HIC Industries delivery memo format:
- Top-left: "No." label with DM number in large red text
- Top-right: **H I C INDUSTRIES** in large bold, full address (B-69&70 MIDC Industrial Area, Butibori, Nagpur - 441122), phone, email, GSTIN
- One horizontal line: Vehicle No. | [DELIVERY MEMO box] | Date
- To: customer name and address
- Table: S.No. / W.O. No. / Product Description (with G.wt / C.wt / N.wt) / Qty
- TOTAL row
- Legal text
- Receiver's Signature / For HIC INDUSTRIES

### Stage 5 — Billing

Not yet implemented. The system currently only tracks up to dispatch.

---

## 9. Every Route Explained

### Auth

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/login` | GET/POST | None | Renders login form; on POST validates credentials, creates session |
| `/logout` | GET | login_required | Destroys session, redirects to login |

### Dashboard

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/` | GET | login_required | Queries all WOs (optionally filtered by `?status=`), counts per status, stores counts in `g.dash_counts` and `g.dash_filter` for the sidebar stage filter |

### User Management

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/settings/users` | GET/POST | admin_required | List users; POST handles: add (create new user), reset_password, toggle (enable/disable), delete |

### Product Types & Customers

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/settings/product-types` | GET/POST | admin_required | Manage product type dropdown. Actions: add, toggle, delete (blocked if in use) |
| `/settings/customers` | GET/POST | admin_required | Manage customers. Actions: add, edit (syncs name to WOs), toggle, delete (blocked if linked to WOs) |

### Work Orders

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/work-order/new` | GET/POST | admin_required | GET: renders form with next WO number, customer list, recipe list. POST: creates WO, deducts inventory if recipe selected, redirects to dashboard |
| `/work-order/<id>` | GET | login_required | Detail view showing all WO data and roll summary |
| `/work-order/<id>/edit` | GET/POST | admin_required | Edit WO fields (not WO number). Does not re-run inventory deduction |
| `/work-order/<id>/delete` | POST | admin_required | Deletes WO and all cascade-linked rolls and packing items |

### Production

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/work-order/<id>/production` | GET/POST | login_required + action check | GET: renders production page. POST actions: add_roll (creates ProductionRoll, auto-sets status to in_production if first roll), mark_ready (sets status=ready, redirects to dashboard), mark_in_production (reverts status) |
| `/roll/<id>/delete` | POST | require_permission("production_delete_roll") | Deletes one roll, redirects back to production page |
| `/roll/<id>/edit` | POST | require_permission("production_edit_roll") | Updates all roll fields, recalculates net weight, redirects back |

### Packing Lists

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/packing-lists` | GET | login_required (not operator) | Lists all PLs and ready WOs awaiting packing |
| `/packing-lists/new` | GET/POST | require_permission("packing_list") | GET: shows ready WOs with checkboxes. POST: creates PL and PackingListItem join records |
| `/packing-lists/<id>` | GET | login_required (not operator) | Shows PL with per-WO tables and print preview |
| `/packing-lists/<id>/remove-wo` | POST | require_permission("packing_list") | Removes one WO from the PL |
| `/packing-lists/<id>/delete` | POST | require_permission("packing_list") | Deletes PL (blocked if DM exists), reverts WO statuses to ready |

### Dispatch Memos

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/dispatch-memos` | GET | login_required (not operator) | Lists all DMs and PLs awaiting dispatch |
| `/dispatch-memos/new` | GET/POST | require_permission("dispatch_memo") | GET: shows PL dropdown. POST: creates DM, sets all WOs to dispatched |
| `/dispatch-memos/<id>` | GET | login_required (not operator) | DM detail page with print document |
| `/dispatch-memos/<id>/edit` | GET/POST | require_permission("dispatch_memo") | Edit date, vehicle, customer info |
| `/dispatch-memos/<id>/delete` | POST | require_permission("dispatch_memo") | Deletes DM, reverts WOs from dispatched to ready |

### Recipes

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/recipes` | GET | admin_required | Lists all recipes with total net kg |
| `/recipes/new` | GET/POST | admin_required | Creates Recipe + 3 RecipeLayers + up to 18 RecipeGrades (6 per layer) |
| `/recipes/<id>` | GET | admin_required | Shows recipe in handwritten-style format, printable |
| `/recipes/<id>/edit` | GET/POST | admin_required | Updates all recipe fields and grades in-place |
| `/recipes/<id>/delete` | POST | admin_required | Deletes recipe and all cascade layers/grades |

### Inventory

| Route | Method | Guard | What it does |
|-------|--------|-------|--------------|
| `/inventory` | GET | inventory_allowed (admin + supervisor) | Stock levels for all active materials, colour-coded, with totals |
| `/inventory/add-stock` | GET/POST | inventory_allowed | GET: table of all grades with quantity fields. POST actions: add_material (new grade to master list), add_stock (incoming stock entries) |
| `/inventory/adjust` | POST | inventory_allowed | Creates a manual adjustment ledger entry (positive or negative) |
| `/inventory/ledger/<id>` | GET | inventory_allowed | Full transaction history for one material |

### API Endpoints (JSON, authenticated)

| Route | What it returns |
|-------|----------------|
| `/api/next-wo-number` | `{"wo_number": "WO8001"}` — next suggested WO number |
| `/api/next-roll-number?machine=RA` | `{"roll_number": "RA2001"}` — next roll number for that machine |
| `/api/customer-address?id=3` | `{"address": "..."}` — customer address for the WO form hint |
| `/api/packing-list-info/<id>` | PL summary (WO numbers, customer, totals) for the DM creation form |
| `/api/recipe-material-preview/<id>?target_kg=500` | List of grade deductions with current/after stock levels |

---

## 10. Every Model Explained

### `before_request` — runs on every single HTTP request

```python
@app.before_request
def initialise_db():
    db.create_all()           # Creates any tables that don't exist yet (safe to run every time)
    ProductType.seed_defaults() # Seeds 19 product types if table is empty
    User.seed_admin()           # Creates admin user if no users exist
    # Sync grade names from recipes into RawMaterial master list
    for rg in RecipeGrade.query.filter(grade_name != ""):
        RawMaterial.get_or_create(rg.grade_name)
    db.session.commit()
    # Store in-production WOs for sidebar display
    g.in_production_wos = WorkOrder.query.filter_by(status="in_production").all()
```

This pattern means the app is truly zero-setup — first request creates everything.

### `WorkOrder.next_wo_number()`

```python
@classmethod
def next_wo_number(cls):
    last = cls.query.filter(cls.wo_number.like("WO%")).order_by(cls.id.desc()).first()
    if last is None:
        return f"WO{cls.WO_START}"  # "WO8000"
    suffix = last.wo_number[2:]     # Strip "WO" prefix → "8000"
    try:
        return f"WO{int(suffix) + 1}"   # → "WO8001"
    except ValueError:
        # Fallback if WO number was manually set to non-numeric
        count = cls.query.filter(cls.wo_number.like("WO%")).count()
        return f"WO{cls.WO_START + count}"
```

### `ProductionRoll.next_roll_number(machine)`

Same pattern — finds the last roll for that specific machine code, strips the prefix, increments. Each machine (RA, RB, SA, SB) has its own independent sequence starting at 2000.

### `Recipe.material_tally`

```python
@property
def material_tally(self):
    tally = {}
    for grade in self.all_grades:   # all RecipeGrade rows across all 3 layers
        if grade.grade_name and grade.kg_amount:
            tally[grade.grade_name] = tally.get(grade.grade_name, 0) + grade.kg_amount
    return tally
    # Returns: {"F19010": 100, "1005FY20": 18, "1018RK": 75, ...}
```

This is the core of the inventory system. If GradeA is 20 kg in Inner and 80 kg in Middle, `material_tally` returns `{"GradeA": 100}`.

### `RawMaterial.current_stock_kg`

```python
@property
def current_stock_kg(self):
    return round(sum(e.qty_kg for e in self.ledger_entries), 3)
```

No stock column is ever stored. Current stock is always computed live from the ledger. This guarantees the audit trail and the balance are always consistent.

### Inventory deduction logic (in `work_order_new` route)

```python
scale = target_kg / recipe_batch_kg   # e.g. 500 / 300 = 1.667
for grade_name, batch_kg in tally.items():
    deduct_kg = round(batch_kg * scale, 3)
    mat = RawMaterial.get_or_create(grade_name)
    entry = InventoryLedger(
        qty_kg=-deduct_kg,           # NEGATIVE = out of stock
        txn_type="work_order",
        reference=wo_number,         # "WO8001"
    )
```

If the recipe defines 100 kg of GradeA per 300 kg batch, and the WO is for 500 kg, then: `100 × (500/300) = 166.667 kg` of GradeA is deducted.

---

## 11. Inventory System

### Data flow

```
Supplier delivers stock
    ↓
Add Stock page → InventoryLedger entry (qty_kg = +N, txn_type = "incoming")
    ↓
current_stock_kg = sum of all entries = positive number

Admin creates Work Order with recipe
    ↓
For each grade: InventoryLedger entry (qty_kg = -N, txn_type = "work_order")
    ↓
current_stock_kg reduces

Stock count correction needed
    ↓
Adjust → InventoryLedger entry (qty_kg = ±N, txn_type = "adjustment")
```

### Grade auto-discovery

When recipes are created or edited, every grade name is automatically added to the `raw_materials` table via `get_or_create()`. This means the inventory is always aware of every grade used in production, even before any stock is entered. New grades start at 0 kg and turn negative when a WO is created — flagging the shortfall immediately.

### The deduction preview (live JavaScript)

When creating a new WO, selecting a recipe and entering a weight triggers an API call to `/api/recipe-material-preview/<recipe_id>?target_kg=<n>`. The response includes, for each grade:
- How much will be deducted
- Current stock level
- Stock after deduction
- Whether stock is sufficient (true/false)

This displays as a colour-coded table before the WO is saved — green rows are fine, red rows indicate insufficient stock. The WO can still be created even with negative stock (the system records the over-commitment), but the warning is visible.

---

## 12. Recipe System

### Structure

Each recipe has exactly 3 layers: **Inner**, **Middle**, **Outer**. Each layer has up to **6 grade slots**. Unused slots are stored as empty strings and are filtered out on display.

The recipe form uses field naming convention: `layer_0_grade_0_name`, `layer_0_grade_0_pct`, `layer_0_grade_0_kg` — where the first index is the layer (0=Inner, 1=Middle, 2=Outer) and the second is the grade slot (0–5).

### The printed format

The recipe detail page replicates the handwritten format from the physical binder exactly:

```
28/11/24.      Lamination Chutney Grade.      Nov 22
──────────────────────────────────────────────────────
Treatment = 44 to 46 Dynes
Layer Ratio = 1:1:1

Inner.  F19010 + 1005FY20 + 1018RK
         20%   +  10%     +  70%.
         20kg  +  10kg    +  70kg  ──────────  100 kg

Middle. F19010 + HD46003
         80%   +  20%.
         80kg  +  20kg  ──────────────────────  100 kg

Outer.  F18010 + 1005FY20 + 1018RK
         87%   +  8%      +  5%.
         87kg  +  8kg     +  5kg  ──────────   100 kg
                                               ──────
                                               300 kg

Material Required
─────────────────────────────────────────────────────
1) F19010    = 20+80  = 100  × 1.03  = 103  → 213
2) 1005FY20  = 10+8   = 18   × 1.03  = 19   → 39
3) 1018RK    = 70+5   = 75   × 1.03  = 77   → 159
4) HD46003   = 20     = 20   × 1.03  = 21   → 44
5) F18010    = 87     = 87   × 1.03  = 90   → 186
                      ────         ─────
                       300          641
```

The dashes between grades and the total line are CSS border-bottom on flex spacers, not actual characters. The monospace font (Courier New) ensures columns align correctly.

---

## 13. Print Documents

Two documents are printable: the **Packing List** and the **Delivery Memo**.

### The popup print method

Both documents use the same technique to avoid the browser printing its own header (page title, URL):

```javascript
function printDocument() {
    const docEl = document.getElementById('printDoc');
    const styleBlocks = Array.from(document.querySelectorAll('style')).map(s => s.outerHTML).join('\n');
    const linkHref = document.querySelector('link[rel="stylesheet"]')?.href || '';
    const linkTag = linkHref ? `<link rel="stylesheet" href="${linkHref}">` : '';

    const html = `<!DOCTYPE html><html><head><title></title>${linkTag}${styleBlocks}
        <style>@page { margin: 0; }</style>
        </head><body>${docEl.outerHTML}</body></html>`;

    const popup = window.open('', '_blank', 'width=794,height=1123');
    popup.document.write(html);
    popup.document.close();
    popup.onload = () => setTimeout(() => {
        popup.focus();
        popup.print();
        setTimeout(() => popup.close(), 1000);
    }, 300);
}
```

Key details:
- `<title></title>` — empty title = no title in printed header
- `@page { margin: 0; }` — removes browser's default page margins; the document wrapper provides its own padding
- The popup has no URL bar content, so no URL is printed
- The CSS and font references are copied from the parent page so the popup renders correctly
- `setTimeout(..., 300)` — waits for stylesheet to load before printing

### Packing list print

One document is generated per work order in the packing list. If the PL has 3 WOs, the print popup shows 3 separate tables. The DM number field in the preview header is editable before printing — it updates the sidebar in real time via JavaScript and is included in the popup HTML.

### Delivery memo print

The DM exactly matches the physical format used by HIC Industries. The "No." in the top-left corner uses `position: absolute` so the company name block can be truly centred over the full page width despite the number being present. The machine type is `courier new` (monospace) for precise column alignment.

---

## 14. Frontend

### Base layout (`base.html`)

Every page (except login) extends `base.html`. The base template provides:
- The dark blue sidebar (240px wide) with the HIC Industries logo, navigation links, and sidebar stage filter on the dashboard
- The white topbar (60px tall) with page title, breadcrumb, contextual actions, and the user/sign-out bar
- Flash message container (auto-dismisses after 4 seconds via `main.js`)
- The sidebar overlay div and hamburger button (shown/hidden by CSS and JS based on screen width)

### Sidebar navigation logic

The sidebar nav links use `{% if request.endpoint == 'dashboard' and g.dash_counts %}` to conditionally show the stage filter sub-links, and `{% if current_user.role == 'admin' %}` to show admin-only links. When inside a WO's production page, a "WO: WO8001" section appears with links to that WO's pages.

The `g.in_production_wos` list (populated in `before_request`) is used to show which WOs are currently in production under the Production nav link.

### CSS architecture

The stylesheet is organised into sections:
1. CSS variables (colours, spacing, shadows, border-radius)
2. Global reset
3. Sidebar and topbar layout
4. Step progress bar
5. Cards, tables, forms
6. Status badges
7. Buttons
8. Dashboard stats row
9. Machine grid (radio buttons for production)
10. Packing list and DM print document styles
11. Recipe print styles
12. Inventory-specific styles
13. Responsive breakpoints

---

## 15. Responsive Design

Four breakpoints handle screens from phones to ultra-wide monitors:

| Breakpoint | Width | Key changes |
|---|---|---|
| XL | > 1400px | Sidebar widens to 260px, more content padding, 5-column stat row |
| MD | 900–1200px | Sidebar narrows to 220px, form grids collapse, detail layouts stack — covers square monitors |
| SM | 600–900px | Sidebar becomes a slide-in drawer with hamburger button, steps bar hidden, all grids go single-column, tables scroll horizontally |
| XS | < 600px | Font size 13px, tighter padding, "Sign Out" text hidden (icon only), phone-optimised layout |

### Hamburger sidebar (≤ 900px)

```javascript
function toggleSidebar() {
    sidebar.classList.toggle('open');    // CSS: .sidebar.open { transform: translateX(0); }
    overlay.classList.toggle('open');    // CSS: .sidebar-overlay.open { display: block; }
}
```

The sidebar is always rendered in the HTML — it's never conditionally hidden in Jinja. On small screens, CSS transforms it off-screen to the left. The `.open` class slides it back into view. Clicking the overlay (the dark background) closes it.

---

## 16. Known Limitations & Planned Work

### Current limitations

1. **SQLite only** — Fine for 1–2 simultaneous users on one machine. For more users or web deployment, switch to PostgreSQL (one config line change in `app.py`).

2. **No data backup** — The `instance/hic.db` file should be manually copied to a safe location regularly. A backup script is planned.

3. **Inventory deduction is one-way** — When a WO is deleted, inventory is NOT restored. This is intentional (deleting a WO doesn't mean the materials are back in stock — they may have been wasted in production). If you need to restore stock after a mistake, use the manual Adjustment feature.

4. **No billing module** — The system tracks through dispatch. Invoicing is not implemented.

5. **No search** — No full-text search on the dashboard. Filter by status only. As the order count grows, this will need addressing.

6. **Recipes don't version** — Editing a recipe changes it globally. There is no version history. If you change a recipe after using it, old WOs linked to it will show the updated recipe, not the recipe as it was when the WO was created.

7. **Single DM per packing list** — One packing list can only have one dispatch memo. Split shipments are not supported.

### Planned work

- **Billing module** — rate per kg, GST line items, invoice generation and PDF export
- **Automated backups** — hourly/daily/weekly/monthly copies of `hic.db` via a cron job
- **PostgreSQL + deployment** — VPS or local server deployment with proper multi-user support
- **PDF export** — native PDF generation for packing lists and DMs using WeasyPrint (currently browser-based popup print only)
- **Analytics dashboard** — monthly production volume, customer-wise output, WO completion times
- **Inventory reorder alerts** — flag grades below a minimum threshold
- **Recipe versioning** — snapshot the recipe at WO creation time so historical records are accurate

---

*Document version 2.0 — reflects full build state as of June 2026*  
*Written for HIC Industries production team and future developers*
