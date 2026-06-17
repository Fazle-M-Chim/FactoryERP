# HIC Industries — Factory Production Management System

A web-based production management system for HIC Industries, a plastic film manufacturing factory in Nagpur, India. Replaces paper-based tracking of the full production lifecycle from customer order through to dispatch.

**Built with:** Python · Flask · SQLAlchemy · SQLite · Flask-Login · Jinja2 · Vanilla JS · Custom CSS

---

## Quick Start

```bash
# 1. Install dependencies
pip install flask flask-sqlalchemy flask-login werkzeug

# 2. Start the server
cd FactoryProduction
python app.py

# 3. Open in browser
# From same machine:   http://127.0.0.1:8080
# From other devices:  http://192.168.31.89:8080

# Default login
# Username: admin
# Password: hic2024   ← change this immediately in Settings → Users
```

The database (`instance/hic.db`) is created automatically on first run. All tables, default product types, and the admin user are seeded without any setup.

---

## Accessing from Other Devices (Same WiFi)

The server listens on `0.0.0.0:8080`, meaning any device on the same network can connect.

- **iPhone / Android:** Open `http://192.168.31.89:8080` in Safari or Chrome
- **Add to home screen:** Share → "Add to Home Screen" for an app-like shortcut
- **Other computers:** Same URL in any browser

> If port 8080 conflicts, change the `port=` value at the bottom of `app.py`.  
> On macOS, port 5000 is occupied by AirPlay Receiver — use 8080 or disable AirPlay Receiver in System Settings.

---

## File Structure

```
FactoryProduction/
├── app.py              # All Flask routes and application logic (~1380 lines)
├── models.py           # All SQLAlchemy database models (~510 lines)
├── README.md           # This file
│
├── instance/
│   └── hic.db          # SQLite database (auto-created, never commit this)
│
├── static/
│   ├── css/
│   │   └── style.css   # Complete stylesheet (~2650 lines)
│   └── js/
│       └── main.js     # Flash dismiss, net weight calculation
│
└── templates/          # 23 Jinja2 HTML templates
    ├── base.html               # Master layout: sidebar, topbar, CSRF, hamburger JS
    ├── login.html              # Standalone login page
    ├── dashboard.html          # Work orders list with status filters and stat cards
    ├── work_order_new.html     # Create / edit work order (with recipe + inventory preview)
    ├── work_order_detail.html  # Work order detail and progress
    ├── production.html         # Split Raju / Shubham production panels
    ├── packing_list_index.html
    ├── packing_list_new.html
    ├── packing_list_detail.html  # Printable packing list document
    ├── dm_index.html
    ├── dm_new.html
    ├── dm_detail.html            # Printable delivery memo
    ├── dm_edit.html
    ├── recipe_index.html
    ├── recipe_form.html          # 3-layer × 6-grade recipe entry with auto-calc
    ├── recipe_detail.html        # Handwritten-style recipe view + print
    ├── inventory_index.html      # Stock levels, adjust modal, professional print
    ├── inventory_add_stock.html
    ├── inventory_ledger.html     # Per-grade transaction history + print
    ├── customers.html
    ├── product_types.html
    ├── users.html
    └── error.html
```

---

## Database Schema

13 tables. Delete `instance/hic.db` and restart whenever you change column definitions.

| Table | Purpose |
|-------|---------|
| `product_types` | Dropdown of 19 film types (Lamination Film variants, LD, VCI, LL Sheet) |
| `customers` | Customer company records with name and delivery address |
| `work_orders` | One row per customer order. Status: open → in_production → ready → dispatched |
| `production_rolls` | Individual rolls produced. Each links to a WO and a machine (RA/RB/SA/SB) |
| `packing_lists` | Groups multiple ready WOs into one dispatch document |
| `packing_list_items` | Join table: WO ↔ packing list |
| `dispatch_memos` | Delivery memo for a packing list. DM number entered manually from physical booklet |
| `users` | Login accounts with role: admin / supervisor / operator |
| `recipes` | Film formula: treatment, layer ratio, notes |
| `recipe_layers` | 3 per recipe (Inner / Middle / Outer), each with target kg |
| `recipe_grades` | Up to 6 grades per layer: name, percentage, kg amount |
| `raw_materials` | Master list of all material grade names used across recipes and inventory |
| `inventory_ledger` | Append-only stock ledger. Every movement recorded. Current stock = SUM(qty_kg) |

---

## User Roles

Three roles. Set when creating users in Settings → Users.

| Role | Can do |
|------|--------|
| **Admin** | Everything: create WOs, manage recipes, all production actions, all settings, user management |
| **Supervisor** | Packing lists, dispatch memos, inventory (view + edit stock). Cannot create WOs or recipes |
| **Operator** | Production only: add rolls, edit rolls, delete rolls, mark ready / back to in-production |

The sidebar navigation adapts per role — links for restricted areas are hidden.

---

## The Production Workflow

```
[Admin] Create Work Order
        ↓  (optionally select a Recipe → inventory auto-deducted)
[Operator] Log production rolls on Raju or Shubham panels
        ↓  (Mark as Ready when done)
[Supervisor] Create Packing List (group multiple ready WOs)
        ↓
[Supervisor] Create Dispatch Memo (enter DM number from physical booklet)
        ↓
WOs marked Dispatched ✓
```

### Work Order numbers
Sequential from WO8000. Auto-suggested but editable. Enforced unique at DB level.

### Roll numbers
Per-machine sequences starting at 2000: RA2000, RB2000, SA2000, SB2000. Auto-suggested on the production page, editable.

### Production page
Split into two independent panels — **Raju** (blue, RA/RB) and **Shubham** (purple, SA/SB). Each panel has its own Side A/B selector, roll number, weight fields, and history table. An overall progress bar spans the top.

### Net weight
Calculated automatically: **Net = Gross − Core**. Computed client-side as you type and confirmed server-side on save.

---

## Inventory System

### How stock is tracked
The `inventory_ledger` table is append-only. Every movement is a row:
- **Stock In** (`incoming`): positive qty_kg — when material arrives from supplier
- **WO Deduction** (`work_order`): negative qty_kg — auto-deducted when WO is created with a recipe
- **Adjustment** (`adjustment`): positive or negative — manual corrections

Current stock = `SUM(qty_kg)` for that material. This means the balance is always provable by examining the full audit trail.

### Inventory deduction on WO creation
When creating a WO, select a Recipe. A live preview table shows exactly how much of each grade will be deducted and whether stock is sufficient. On save, ledger entries are created automatically, scaled to the WO target weight:

```
deduct_kg = (grade_kg_in_recipe / recipe_total_kg) × wo_target_kg
```

### Grade auto-sync
Every grade name in every recipe is automatically added to `raw_materials` on each request. You never need to manually add grades that exist in recipes — they appear in inventory at 0 kg and go negative if a WO deducts before stock is entered.

---

## Recipe System

Each recipe has:
- **Header:** name, recipe number, product type, date, layer ratio
- **Treatment:** min–max Dynes, or tick "N/A — No treatment required"
- **3 layers** (Inner / Middle / Outer), each with a target kg and up to **6 grades**
- Per grade: name, percentage (%), kg amount

### Auto-calculation
When you enter a percentage and the layer target kg is set, the kg field fills automatically: `kg = (% / 100) × target_kg`. Changing the target kg recalculates all grades in that layer.

### Material Required tally
Shown at the bottom of the recipe detail view. Aggregates each grade across all layers, shows net kg total, applies × 1.03 wastage factor, gives gross kg total. Formula applied once on the total, not per-grade, to avoid rounding errors.

### Print format
Replicates the physical handwritten binder format exactly — monospace font, `+` signs between grades, dashed underline before layer total, double-underline grand total.

---

## Print Documents

Three documents use a popup print method (no browser URL/title bar in output):

### Packing List
One sub-table per WO. Columns: SR NO. / ROLL NO. / GROSS WT. / CORE WT. / NET WT. Sidebar shows DATE / WO NO. / DM NO. (editable before printing). Product type shown in all caps.

### Delivery Memo (DM)
Matches the physical HIC Industries delivery memo format:
- `H I C INDUSTRIES` heading centred over full page width (No. is `position:absolute` top-left so it doesn't affect centring)
- Address: B-69&70 MIDC Industrial Area, Butibori, Nagpur - 441122
- GSTIN: 27AAHFH2211B1Z3
- One line: Vehicle No. | DELIVERY MEMO box | Date
- Per-WO rows with product name, spec, G.wt / C.wt / N.wt, and qty
- Signature space: 40px padding above each signature line

### Inventory Reports
Both the inventory index and the grade ledger have a Print button that generates a professional A4 document:
- HIC Industries header with dark blue company name
- Dark blue column headers, alternating row shading
- Colour-coded stock values (green / amber / red)
- Footer with who printed it and timestamp

---

## Dates and Times

All dates displayed as **dd/mm/yyyy** (e.g. 17/06/2026).  
All datetimes displayed in **IST (Indian Standard Time, UTC+5:30)** (e.g. 17/06/2026 13:00).

Timestamps are stored in UTC in the database and converted via the `| ist` Jinja filter on display. Date-only fields use the `| fmt_date` filter.

---

## Security

- **Passwords:** bcrypt-hashed via Werkzeug. Plain passwords never stored.
- **Sessions:** Flask-Login session cookies, `SECRET_KEY` from environment variable `HIC_SECRET_KEY` or a generated key.
- **CSRF protection:** Per-session token injected automatically into every POST form and fetch() call by a script in `base.html`. All state-changing routes check the token before processing.
- **Role guards:** `@admin_required` and `@require_permission(perm)` decorators on every route. 403 on violation.
- **No public access:** The app runs on the local network only (no HTTPS, no domain, not exposed to the internet).

---

## Responsive Design

Four CSS breakpoints:

| Breakpoint | Width | Behaviour |
|---|---|---|
| XL | >1400px | Wider sidebar (260px), more padding |
| MD | 900–1200px | Narrower sidebar (220px), layouts stack — **square monitors** |
| SM | ≤900px | Hamburger drawer sidebar, all grids single-column, tables scroll |
| XS | ≤600px | 13px base font, tighter padding, icon-only sign out |

The production split panel stacks to single column at ≤1100px. All tables have `overflow-x: auto` for horizontal scrolling on narrow screens. Tested on Mac (wide + square), iPhone Safari.

---

## API Endpoints

All require authentication. Return JSON.

| Endpoint | Returns |
|----------|---------|
| `GET /api/next-wo-number` | Next suggested WO number |
| `GET /api/next-roll-number?machine=RA` | Next roll number for that machine |
| `GET /api/customer-address?id=3` | Customer delivery address |
| `GET /api/packing-list-info/<id>` | PL summary for DM creation form |
| `GET /api/recipe-material-preview/<id>?target_kg=500` | Per-grade deduction preview with current/after stock |

---

## Known Limitations

1. **No billing module.** System tracks through dispatch. Invoicing not implemented.
2. **SQLite only.** Fine for 1–5 concurrent users on a local network. For cloud deployment, switch to PostgreSQL (one config line).
3. **No automatic backup.** Copy `instance/hic.db` manually to a safe location regularly.
4. **Recipe versioning.** Editing a recipe changes it globally — historical WOs linked to it reflect the current recipe, not what it was at creation time.
5. **Inventory deduction is one-way.** Deleting a WO does not restore its deducted inventory. Use a manual Adjustment to add stock back if needed.
6. **Single DM per packing list.** Split shipments are not supported.
7. **No search.** Dashboard filters by status only. With many WOs, a search bar would help.

---

## Planned / Future Work

- Billing module (rate per kg, GST line items, PDF invoice)
- Automated hourly/daily/weekly backups of `hic.db`
- Cloud deployment (Hetzner VPS + Nginx + Gunicorn + HTTPS)
- PostgreSQL migration for multi-user cloud use
- PDF export using WeasyPrint (currently browser popup print)
- Analytics: monthly volume, customer-wise output, WO completion times
- Inventory reorder alerts when grade falls below threshold
- Recipe version history — snapshot at WO creation time

---

## Company Details (baked into print documents)

```
HIC Industries
B-69&70 MIDC Industrial Area, Butibori, Nagpur - 441122
Ph: 9595290872
Email: hic.industries@gmail.com
GSTIN: 27AAHFH2211B1Z3
```

---

## Changelog

| Version | Changes |
|---------|---------|
| v1 | Initial proof of concept |
| v2–v10 | Work orders, production rolls, packing lists, DM |
| v11 | Edit/delete rolls and packing lists; delete DM with WO revert |
| v12–v13 | DM print format (centred header, no empty rows, single-line meta, signature space) |
| v14 | Full product type list (19 types); address corrected to B-69&70 |
| v15 | Login system (3 roles); Recipe module (3 layers × 6 grades, material tally, print) |
| v16 | Recipe print matches handwritten format; operator can edit/delete rolls |
| v17 | Sign Out button in topbar |
| v18 | Full responsive design (4 breakpoints, hamburger sidebar) |
| v19 | Inventory module: stock ledger, WO deduction, material preview, grade auto-sync |
| v20 | Complete technical README (v1.0) |
| v21 | Production page split into Raju / Shubham panels |
| v22 | Sidebar scrollable — all nav links always accessible |
| v23 | Recipe maths fixed (300 × 1.03 = 309, not 312); clear grade button; treatment N/A checkbox |
| v24 | Print buttons on inventory pages; all dates IST dd/mm/yyyy; recipe % → kg auto-calc |
| v25 | Button icon alignment fixed across all 23 templates |
| v26 | Inventory adjust modal working; professional print documents for inventory and ledger |
| v27 | Customer edit fixed (data attributes, no quote collision); customer name in ledger; notes optional |
| v28 | Server listens on 0.0.0.0:8080 — accessible from all devices on local network |

---

*Last updated: June 2026 — v28*  
*HIC Industries Production Management System*
