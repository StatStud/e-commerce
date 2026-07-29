"""
Diamond Dripp — e-commerce storefront + admin panel
Built for PythonAnywhere (Flask + SQLite). Payment & email auth are mocked for now.
"""
import os, json, sqlite3, secrets, re, datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, jsonify, g, abort, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:                                   # image optimization (resize + compress)
    from PIL import Image, ImageOps
except ImportError:                    # if Pillow is missing, uploads still work un-optimized
    Image = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "diamond.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB per request (originals get compressed on arrival)

MAX_IMG_DIM = 1600      # uploaded photos are resized so their longest side is <= this
JPEG_QUALITY = 85       # and re-saved as JPEG at this quality

DEFAULT_ADMIN_PASSWORD = "dripp2026"   # change from /admin > Settings

# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Gear',
  price REAL NOT NULL DEFAULT 0,
  compare_price REAL,
  description TEXT DEFAULT '',
  options TEXT DEFAULT '[]',
  badge TEXT DEFAULT '',
  stock INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1,
  featured INTEGER DEFAULT 0,
  sort INTEGER DEFAULT 100,
  size_chart TEXT DEFAULT 'none',
  created TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS product_images(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  sort INTEGER DEFAULT 100
);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name TEXT DEFAULT '',
  verified INTEGER DEFAULT 1,
  created TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_no TEXT UNIQUE NOT NULL,
  user_id INTEGER,
  email TEXT, name TEXT, phone TEXT,
  address TEXT, city TEXT, state TEXT, zip TEXT,
  items TEXT DEFAULT '[]',
  subtotal REAL DEFAULT 0, shipping REAL DEFAULT 0, total REAL DEFAULT 0,
  status TEXT DEFAULT 'New',
  payment_status TEXT DEFAULT 'Test mode',
  created TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS wishlist(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  options TEXT DEFAULT '{}',
  created TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

DEFAULT_SETTINGS = {
    "store_name": "Diamond Dripp",
    "announcement": "Free U.S. shipping on orders over $75 · New sliding mitt styles in stock",
    "hero_eyebrow": "Baseball & softball accessories",
    "hero_title": "Ice out your game.",
    "hero_sub": "Beaded chains, sliding mitts, arm sleeves and dugout gear built for players who show up loud.",
    "hero_cta": "Shop the drip",
    "about_title": "Built for the diamond",
    "about_text": "Diamond Dripp makes the gear that gets noticed between the lines — team-color beaded chains, iced-out Cubans, ice cream sleeves and sliding mitts your whole squad will want. Youth and adult sizes, ready to ship.",
    "contact_email": "orders@diamonddripp.com",
    "instagram": "@diamonddripp",
    "shipping_flat": "6.99",
    "free_ship_threshold": "75",
    "show_story": "1",
}

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = db_conn()
    conn.executescript(SCHEMA)
    # migrations for databases created before these columns existed (no-op otherwise)
    try:
        conn.execute("ALTER TABLE products ADD COLUMN size_chart TEXT DEFAULT 'none'")
    except sqlite3.OperationalError:
        pass  # column already there
    # settings defaults
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    if not conn.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone():
        conn.execute("INSERT INTO settings(key,value) VALUES('admin_password_hash',?)",
                     (generate_password_hash(DEFAULT_ADMIN_PASSWORD),))
    # seed products once
    if conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"] == 0:
        seed_products(conn)
    conn.commit()
    conn.close()

def seed_products(conn):
    def add(slug, name, category, price, compare, desc, options, badge, stock,
            featured, sort, images, size_chart="none"):
        cur = conn.execute(
            """INSERT INTO products(slug,name,category,price,compare_price,description,
               options,badge,stock,active,featured,sort,size_chart)
               VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?)""",
            (slug, name, category, price, compare, desc, json.dumps(options),
             badge, stock, featured, sort, size_chart))
        pid = cur.lastrowid
        for i, fn in enumerate(images):
            conn.execute("INSERT INTO product_images(product_id,filename,sort) VALUES(?,?,?)",
                         (pid, fn, i))

    necklace_colorways = [
        "Red / Light Blue / White", "Navy / Gold / White", "All White Ice",
        "Navy / White", "Gold / White / Navy", "Blue Mix (Royal / Sky / White)",
        "Royal / White", "Navy / Crystal AB", "Cardinal Red / White",
        "Teal / Black / White", "Red / Crystal", "Red / Black",
        "Royal Blue / White", "Red / White / Royal", "Black / Navy / White",
        "Red / White / Blue", "Teal / White"]
    add("beaded-team-necklace", "Beaded Team Necklace", "Necklaces", 19.99, 24.99,
        "Rhinestone disco-bead chains in your team colors. Every bead is fully iced "
        "360°, strung on strong elastic so it slips on fast and stays put through nine "
        "innings. Pick the colorway that matches your squad — 17 combos in stock.\n\n"
        "• Sparkle beads, iced on every side\n• One size fits youth and adult\n"
        "• Stretch cord, no clasp to fumble with\n• Matches every jersey in the dugout",
        [{"name": "Colorway", "choices": necklace_colorways}],
        "Team favorite", 50, 1, 1,
        [f"products/necklace_{i}.jpg" for i in range(1, 18)])

    mitt_styles = [
        "Ice Cream — Red/White/Blue (Youth)", "Coconut Tree — Blue/Red (Youth)",
        "Clown — Green/Purple (Youth)", "Plush Jason — Green (Youth)",
        "Gingerbread Man — Brown (Youth)", "Donut (Youth)",
        "Little Monster — Blue/Pink (Youth)", "Ice Milkshake (Youth)",
        "Fun Cookie — Blue (Youth)", "Super Mario (Youth)", "Big Eye — Green (Youth)",
        "Day of the Dead — Floral (Adult)", "Cattleya Banana (Adult)",
        "Funabou — Red/Blue (Adult)", "Boom — Orange/Yellow (Adult)",
        "Spider — Green (Adult)", "Spray Paint Face — Blue/Pink (Adult)",
        "Ice Milkshake (Adult)"]
    add("sliding-mitts", "Sliding Mitts", "On-Field Gear", 21.99, None,
        "Padded sliding mitts that protect your hand on every steal — and look wild "
        "doing it. Printed and embroidered designs from ice cream cones to little "
        "monsters, in youth and adult sizes (size is noted on each style).\n\n"
        "• Dense padding over fingers and wrist\n• Secure wrist strap\n"
        "• Youth and adult styles in stock\n• The dugout will ask where you got it",
        [{"name": "Style", "choices": mitt_styles}],
        "New styles", 118, 1, 2,
        ["products/mitts_collage.jpg"] +
        [f"mitts/{n}.jpg" for n in
         ["mitt_icecream", "mitt_coconut", "mitt_clown", "mitt_jason",
          "mitt_gingerbread", "mitt_donut", "mitt_monster", "mitt_milkshake_y",
          "mitt_cookie", "mitt_mario", "mitt_bigeye", "mitt_dayofdead",
          "mitt_banana", "mitt_funabou", "mitt_boom", "mitt_spider",
          "mitt_spraypaint", "mitt_milkshake_a"]])

    add("cuban-link-chain", "Iced Cuban Link Chain", "Necklaces", 34.99, 44.99,
        "A full pavé Cuban link that hits like a walk-off. Chunky prong-set links, "
        "iced edge to edge, with a boxed safety clasp that locks down tight. Wear it "
        "to the park or after the game.\n\n"
        "• Fully iced prong-set links\n• Secure box clasp\n"
        "• Three finishes: rose gold, gold, silver",
        [{"name": "Finish", "choices": ["Rose Gold", "Gold", "Silver"]}],
        "", 30, 1, 3,
        ["products/cuban_gold.jpg", "products/cuban_silver.jpg", "products/cuban_rosegold.jpg"])

    numbers = [str(n) for n in list(range(1, 24)) + [67, 98, 99]]
    add("numbered-necklace", "Numbered Necklace", "Necklaces", 16.99, None,
        "Rep your jersey number around your neck. Stainless steel rope chain (55cm) "
        "with a bold number pendant — pick silver or gold, then pick your number.\n\n"
        "• Stainless steel — won't tarnish or turn\n• 55cm rope chain\n"
        "• Numbers 1–23, 67, 98 and 99 in stock",
        [{"name": "Metal", "choices": ["Silver", "Gold"]},
         {"name": "Number", "choices": numbers}],
        "", 208, 1, 4,
        ["products/numbered_silver_grid.jpg", "products/numbered_silver_chain.jpg",
         "products/numbered_gold_grid.jpg", "products/numbered_gold_chain.jpg"])

    camo_nums = [1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 17, 18, 20, 21, 22, 23, 24, 25, 26, 30]
    sleeve_designs = ["White Vanilla", "Cherry Red", "Orange Creamsicle", "Dark Blue",
                      "Light Blue (Cotton Candy)", "Black Licorice", "Strawberry",
                      "Lemon", "Mint Chocolate Chip"] + \
                     [f"Digital Camo #{n}" for n in camo_nums]
    add("arm-sleeves", "Ice Cream & Camo Arm Sleeves", "On-Field Gear", 17.99, None,
        "The dripping ice cream cone sleeve that started it all — a waffle-cone "
        "forearm with a melting scoop and sprinkles up top. Also available in digital "
        "camo colorways. Premium stretch polyester with compression fit, moisture "
        "wicking and UV protection.\n\n"
        "• 9 ice cream flavors + 20 digital camo colorways\n"
        "• Youth Small through Adult Medium (see size chart in photos)\n"
        "• Flatlock seams, no irritation\n• Size down if between measurements",
        [{"name": "Design", "choices": sleeve_designs},
         {"name": "Size", "choices": ["Youth Small", "Youth Medium", "Youth Large",
                                       "Adult Small", "Adult Medium"]}],
        "Best seller", 100, 1, 5,
        ["products/sleeves_collection.jpg", "products/sleeves_photo1.jpg",
         "products/sleeves_photo2.jpg", "products/sleeves_photo3.jpg",
         "products/sleeves_sizechart.jpg"])

    sg_colors = ["Black / Purple", "Blue / Pink", "Pink", "Pink / Gold", "Grey",
                 "Transparent Pink / Gold", "White / Pink", "Black / Green",
                 "Black / Grey", "White / Silver", "Black / Dark Purple",
                 "Blue / Purple", "Blue", "Dark Green", "White / Blue",
                 "Black / Pink", "Red / Gold"]
    add("signature-sunglasses", "Diamond Dripp Signature Sunglasses", "Accessories",
        14.99, None,
        "Oversized sport shields made for day games. Lightweight PC frame and lens, "
        "full coverage, and enough colorways to match any uniform. The first drop in "
        "our signature eyewear line.\n\n"
        "• Lightweight sport shield design\n• PC frame + PC lens\n"
        "• 17 colorways in stock",
        [{"name": "Colorway", "choices": sg_colors}],
        "Signature", 60, 1, 6,
        ["products/sunglasses_1.jpg", "products/sunglasses_2.jpg", "products/sunglasses_3.jpg"])

    # Grand Slam Glasses — one image folder per colorway (static/img/glasses/NN_slug/)
    # with front / angled / side shots. The product page shows only the selected
    # colorway's photos, plus the shared fit + adjustable-temple images that are
    # appended via size_chart='glasses' (same idea as the mitt size charts).
    gs_dirs = [
        "01_blue-orange", "02_gold-blue", "03_black", "04_pink-green-white",
        "05_light-blue-silver", "06_pink-yellow-black", "07_pink-yellow-white",
        "08_blue-red", "09_pink-orange-silver", "10_black-red",
        "11_yellow-blue-white", "12_gold-orange", "13_yellow-blue-yellow",
        "14_orange-red-black", "15_orange-green-black", "16_yellow-orange-red",
        "17_yellow-blue-green", "18_purple-green-black", "19_orange-green-lime",
        "20_silver-black", "21_gold-lime", "22_blue-purple-red", "23_silver-white",
        "24_yellow-orange-pink", "25_blue-purple-black", "26_blue-green-purple",
        "27_black-gold"]

    def gs_name(d):
        parts = d.split("_", 1)[1].replace("light-blue", "light blue").split("-")
        return " / ".join(p.title() for p in parts)

    add("grand-slam-glasses", "Grand Slam Glasses", "Accessories", 19.99, None,
        "Full-shield sport sunglasses built for the diamond. Pick your colorway and "
        "the photos update to show that exact pair from the front, angled and side "
        "— what you see is what ships.\n\n"
        "• 27 team colorways in stock\n• Adjustable temple arms for a custom fit\n"
        "• One size fits most — youth and adult (see fit chart in photos)\n"
        "• Lightweight frame with full-coverage shield lens",
        [{"name": "Colorway", "choices": [gs_name(d) for d in gs_dirs]}],
        "New drop", 108, 1, 6,
        [f"glasses/{d}/{f}" for d in gs_dirs
         for f in ("01_front.jpg", "02_angled.jpg", "03_side.jpg")],
        size_chart="glasses")

    add("rhinestone-tumbler", "Rhinestone 40oz Tumbler", "Dugout", 44.99, 54.99,
        "A 40oz stainless tumbler covered corner-to-corner in rhinestones, with "
        "baseball or softball stitching running up the side. Double-wall insulated "
        "with a handle and straw lid — the loudest cup in the dugout.\n\n"
        "• 40oz stainless steel, double-wall insulated\n"
        "• Full rhinestone wrap with stitch detail\n• Handle + straw lid",
        [{"name": "Sport", "choices": ["Baseball (White)", "Softball (Yellow)"]}],
        "Sparkly", 25, 1, 7,
        ["products/cup_sparkly.jpg"])

    add("classic-tumbler", "Classic 40oz Tumbler", "Dugout", 29.99, None,
        "Same 40oz insulated tumbler, printed edition — baseball or softball "
        "stitching without the rhinestones. Keeps drinks cold through a "
        "doubleheader.\n\n"
        "• 40oz stainless steel, double-wall insulated\n"
        "• Printed stitch design\n• Handle + straw lid",
        [{"name": "Sport", "choices": ["Baseball (White)", "Softball (Yellow)"]}],
        "", 25, 0, 8,
        ["products/cup_regular.jpg"])

    add("golf-umbrella", "Diamond Dripp 67\" Umbrella", "Dugout", 39.99, None,
        "Tournament-day coverage. A 67-inch double-canopy golf umbrella with the "
        "Diamond Dripp emblem on every panel. Windproof frame, water repellent, UV "
        "protection — shade for the whole bleacher row.\n\n"
        "• 67\" large canopy\n• Windproof double canopy\n"
        "• Water repellent + UV protection",
        [], "", 20, 0, 9,
        ["products/umbrella.jpg"])

# initialize on import (safe: CREATE IF NOT EXISTS + seed only when empty)
init_db()

# ---------------------------------------------------------------- helpers
def get_setting(key, default=""):
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(key, value):
    get_db().execute("INSERT INTO settings(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def money(x):
    return f"${x:,.2f}"

app.jinja_env.filters["money"] = money

def product_by_slug(slug):
    return get_db().execute("SELECT * FROM products WHERE slug=? AND active=1", (slug,)).fetchone()

def product_images(pid):
    return get_db().execute(
        "SELECT * FROM product_images WHERE product_id=? ORDER BY sort, id", (pid,)).fetchall()

def primary_image(pid):
    row = get_db().execute(
        "SELECT filename FROM product_images WHERE product_id=? ORDER BY sort, id LIMIT 1",
        (pid,)).fetchone()
    return row["filename"] if row else None

def parse_options(p):
    try:
        return json.loads(p["options"] or "[]")
    except Exception:
        return []

def save_optimized_image(file, base_name):
    """Save an admin-uploaded image into UPLOAD_DIR, resized to MAX_IMG_DIM on the
    longest side and re-compressed as JPEG. Returns the saved filename.
    Falls back to saving the original file untouched if anything goes wrong."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if Image is None or ext == "gif":          # keep GIFs (possibly animated) as-is
        fn = secure_filename(f"{base_name}-{file.filename}")
        file.save(os.path.join(UPLOAD_DIR, fn))
        return fn
    try:
        img = Image.open(file.stream)
        img = ImageOps.exif_transpose(img)     # respect phone-camera rotation
        if max(img.size) > MAX_IMG_DIM:
            img.thumbnail((MAX_IMG_DIM, MAX_IMG_DIM), Image.LANCZOS)
        if img.mode in ("RGBA", "LA", "P"):    # flatten transparency onto white
            img = img.convert("RGBA")
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
        elif img.mode != "RGB":
            img = img.convert("RGB")
        stem = file.filename.rsplit(".", 1)[0] or "photo"
        fn = secure_filename(f"{base_name}-{stem}") + ".jpg"
        img.save(os.path.join(UPLOAD_DIR, fn), "JPEG",
                 quality=JPEG_QUALITY, optimize=True, progressive=True)
        return fn
    except Exception:
        try:
            file.stream.seek(0)
        except Exception:
            pass
        fn = secure_filename(f"{base_name}-{file.filename}")
        file.save(os.path.join(UPLOAD_DIR, fn))
        return fn

SIZE_CHART_KINDS = ("none", "youth", "adult", "both", "glasses")

def _chart_file(name):
    for ext in ("jpg", "jpeg", "png", "webp"):
        rel = f"size_charts/{name}.{ext}"
        if os.path.exists(os.path.join(BASE_DIR, "static", "img", rel)):
            return rel
    return None

def size_chart_images(kind):
    """Relative /pimg/ paths for the size chart image(s) a product should show.
    Looks in static/img/size_charts/ for youth.*, adult.*, and both.* —
    'both' prefers a single combined chart (both.*) and falls back to showing
    youth + adult separately. 'glasses' shows the sunglasses info pair
    (glasses_fit.* + glasses_temple.*). Missing files are skipped, never
    breaking a page."""
    kind = kind or "none"
    if kind == "glasses":
        return [f for f in (_chart_file("glasses_fit"), _chart_file("glasses_temple")) if f]
    if kind == "both":
        combined = _chart_file("both")
        if combined:
            return [combined]
        return [f for f in (_chart_file("youth"), _chart_file("adult")) if f]
    if kind in ("youth", "adult"):
        f = _chart_file(kind)
        return [f] if f else []
    return []

def cart():
    return session.setdefault("cart", [])

def cart_detail():
    """Return (lines, subtotal). Each line: product row + qty + opts + line total."""
    db = get_db()
    lines, subtotal = [], 0.0
    changed = False
    for item in list(cart()):
        p = db.execute("SELECT * FROM products WHERE id=? AND active=1",
                       (item["pid"],)).fetchone()
        if not p:
            cart().remove(item); changed = True
            continue
        line_total = p["price"] * item["qty"]
        subtotal += line_total
        lines.append({"p": p, "qty": item["qty"], "opts": item.get("opts", {}),
                      "key": item["key"], "line_total": line_total,
                      "img": primary_image(p["id"])})
    if changed:
        session.modified = True
    return lines, round(subtotal, 2)

def shipping_for(subtotal):
    if subtotal <= 0:
        return 0.0
    try:
        threshold = float(get_setting("free_ship_threshold", "75"))
        flat = float(get_setting("shipping_flat", "6.99"))
    except ValueError:
        threshold, flat = 75.0, 6.99
    return 0.0 if subtotal >= threshold else flat

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get("uid"):
            flash("Sign in to view your account.", "info")
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*a, **kw)
    return wrapped

@app.context_processor
def inject_globals():
    count = sum(i["qty"] for i in session.get("cart", []))
    cats = get_db().execute(
        "SELECT DISTINCT category FROM products WHERE active=1 ORDER BY category").fetchall()
    return dict(setting=get_setting, cart_count=count, user=current_user(),
                categories=[c["category"] for c in cats])

# ---------------------------------------------------------------- storefront
@app.route("/")
def home():
    db = get_db()
    featured = db.execute(
        "SELECT * FROM products WHERE active=1 AND featured=1 ORDER BY sort LIMIT 6").fetchall()
    if len(featured) < 3:
        featured = db.execute(
            "SELECT * FROM products WHERE active=1 ORDER BY sort LIMIT 6").fetchall()
    featured = [dict(p, img=primary_image(p["id"])) for p in featured]
    return render_template("index.html", featured=featured)

@app.route("/shop")
def shop():
    db = get_db()
    cat = request.args.get("category", "").strip()
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM products WHERE active=1"
    args = []
    if cat:
        sql += " AND category=?"; args.append(cat)
    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY sort, name"
    products = [dict(p, img=primary_image(p["id"]))
                for p in db.execute(sql, args).fetchall()]
    return render_template("shop.html", products=products, cat=cat, q=q)

@app.route("/product/<slug>")
def product(slug):
    p = product_by_slug(slug)
    if not p:
        abort(404)
    imgs = [dict(r) for r in product_images(p["id"])]
    # Variant-aware gallery: images stored as <group>/<NN_variant>/<file>.jpg
    # (e.g. glasses/01_blue-orange/01_front.jpg) are tagged with their variant
    # key so the front-end can show only the selected colorway's photos.
    for img in imgs:
        parts = img["filename"].split("/")
        img["variant"] = re.sub(r"^\d+_", "", parts[1]) if len(parts) == 3 else ""
    # append the product's size chart(s) to the gallery automatically
    try:
        chart_kind = p["size_chart"]
    except (IndexError, KeyError):
        chart_kind = "none"
    for rel in size_chart_images(chart_kind):
        imgs.append({"id": None, "filename": rel, "sort": 9999, "variant": ""})
    opts = parse_options(p)
    related = get_db().execute(
        "SELECT * FROM products WHERE active=1 AND id!=? AND category=? ORDER BY sort LIMIT 4",
        (p["id"], p["category"])).fetchall()
    related = [dict(r, img=primary_image(r["id"])) for r in related]
    return render_template("product.html", p=p, images=imgs, options=opts, related=related)

# ---------------------------------------------------------------- cart
def _opts_from_form(p):
    opts = {}
    for grp in parse_options(p):
        val = request.form.get(f"opt_{grp['name']}", "")
        if val:
            opts[grp["name"]] = val
    return opts

@app.route("/cart")
def view_cart():
    lines, subtotal = cart_detail()
    ship = shipping_for(subtotal)
    return render_template("cart.html", lines=lines, subtotal=subtotal,
                           shipping=ship, total=round(subtotal + ship, 2))

@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = request.form.get("pid", type=int)
    qty = max(1, min(99, request.form.get("qty", 1, type=int)))
    p = get_db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p:
        abort(404)
    opts = _opts_from_form(p)
    key = f"{pid}:{json.dumps(opts, sort_keys=True)}"
    for item in cart():
        if item["key"] == key:
            item["qty"] = min(99, item["qty"] + qty)
            break
    else:
        cart().append({"key": key, "pid": pid, "qty": qty, "opts": opts})
    session.modified = True
    if request.headers.get("X-Requested-With") == "fetch":
        count = sum(i["qty"] for i in cart())
        return jsonify(ok=True, count=count, name=p["name"])
    flash(f"Added {p['name']} to your cart.", "success")
    return redirect(request.referrer or url_for("view_cart"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    key = request.form.get("key", "")
    qty = request.form.get("qty", 1, type=int)
    for item in cart():
        if item["key"] == key:
            if qty <= 0:
                cart().remove(item)
            else:
                item["qty"] = min(99, qty)
            break
    session.modified = True
    return redirect(url_for("view_cart"))

@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    key = request.form.get("key", "")
    session["cart"] = [i for i in cart() if i["key"] != key]
    session.modified = True
    return redirect(url_for("view_cart"))

# ---------------------------------------------------------------- wishlist
@app.route("/wishlist")
def wishlist_view():
    u = current_user()
    items = []
    db = get_db()
    if u:
        rows = db.execute("""SELECT w.id wid, w.options, p.* FROM wishlist w
                             JOIN products p ON p.id=w.product_id
                             WHERE w.user_id=? ORDER BY w.created DESC""", (u["id"],)).fetchall()
        for r in rows:
            items.append({"wid": r["wid"], "p": r, "opts": json.loads(r["options"] or "{}"),
                          "img": primary_image(r["id"])})
    else:
        for entry in session.get("wl", []):
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1",
                           (entry["pid"],)).fetchone()
            if p:
                items.append({"wid": entry["key"], "p": p, "opts": entry.get("opts", {}),
                              "img": primary_image(p["id"])})
    return render_template("wishlist.html", items=items)

@app.route("/wishlist/add", methods=["POST"])
def wishlist_add():
    pid = request.form.get("pid", type=int)
    p = get_db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p:
        abort(404)
    opts = _opts_from_form(p)
    u = current_user()
    if u:
        get_db().execute("INSERT INTO wishlist(user_id,product_id,options) VALUES(?,?,?)",
                         (u["id"], pid, json.dumps(opts)))
        get_db().commit()
    else:
        wl = session.setdefault("wl", [])
        key = f"{pid}:{json.dumps(opts, sort_keys=True)}"
        if not any(e["key"] == key for e in wl):
            wl.append({"key": key, "pid": pid, "opts": opts})
        session.modified = True
    flash(f"Saved {p['name']} for later.", "success")
    return redirect(request.referrer or url_for("wishlist_view"))

@app.route("/wishlist/remove", methods=["POST"])
def wishlist_remove():
    wid = request.form.get("wid", "")
    u = current_user()
    if u and wid.isdigit():
        get_db().execute("DELETE FROM wishlist WHERE id=? AND user_id=?", (wid, u["id"]))
        get_db().commit()
    else:
        session["wl"] = [e for e in session.get("wl", []) if e["key"] != wid]
        session.modified = True
    return redirect(url_for("wishlist_view"))

@app.route("/wishlist/to-cart", methods=["POST"])
def wishlist_to_cart():
    wid = request.form.get("wid", "")
    u = current_user()
    pid, opts = None, {}
    if u and wid.isdigit():
        row = get_db().execute("SELECT * FROM wishlist WHERE id=? AND user_id=?",
                               (wid, u["id"])).fetchone()
        if row:
            pid, opts = row["product_id"], json.loads(row["options"] or "{}")
            get_db().execute("DELETE FROM wishlist WHERE id=?", (wid,))
            get_db().commit()
    else:
        for e in session.get("wl", []):
            if e["key"] == wid:
                pid, opts = e["pid"], e.get("opts", {})
                session["wl"].remove(e); session.modified = True
                break
    if pid:
        key = f"{pid}:{json.dumps(opts, sort_keys=True)}"
        for item in cart():
            if item["key"] == key:
                item["qty"] += 1; break
        else:
            cart().append({"key": key, "pid": pid, "qty": 1, "opts": opts})
        session.modified = True
        flash("Moved to cart.", "success")
    return redirect(url_for("wishlist_view"))

# ---------------------------------------------------------------- checkout
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, subtotal = cart_detail()
    if not lines:
        flash("Your cart is empty.", "info")
        return redirect(url_for("shop"))
    ship = shipping_for(subtotal)
    total = round(subtotal + ship, 2)
    u = current_user()
    if request.method == "POST":
        required = ["email", "name", "address", "city", "state", "zip"]
        data = {k: request.form.get(k, "").strip() for k in
                required + ["phone", "card_name", "card_number", "card_exp", "card_cvc"]}
        missing = [k for k in required if not data[k]]
        if missing or "@" not in data["email"]:
            flash("Please fill in every required field (and a valid email).", "error")
            return render_template("checkout.html", lines=lines, subtotal=subtotal,
                                   shipping=ship, total=total, form=data)
        order_no = "DD-" + secrets.token_hex(3).upper()
        items_json = json.dumps([
            {"name": l["p"]["name"], "pid": l["p"]["id"], "qty": l["qty"],
             "price": l["p"]["price"], "opts": l["opts"]} for l in lines])
        db = get_db()
        db.execute("""INSERT INTO orders(order_no,user_id,email,name,phone,address,city,
                      state,zip,items,subtotal,shipping,total,status,payment_status)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (order_no, u["id"] if u else None, data["email"], data["name"],
                    data["phone"], data["address"], data["city"], data["state"],
                    data["zip"], items_json, subtotal, ship, total,
                    "New", "Paid (test mode)"))
        # decrement stock
        for l in lines:
            db.execute("UPDATE products SET stock=MAX(0, stock-?) WHERE id=?",
                       (l["qty"], l["p"]["id"]))
        db.commit()
        session["cart"] = []
        session.modified = True
        return redirect(url_for("order_confirmation", order_no=order_no))
    form = {}
    if u:
        form = {"email": u["email"], "name": u["name"]}
    return render_template("checkout.html", lines=lines, subtotal=subtotal,
                           shipping=ship, total=total, form=form)

@app.route("/order/<order_no>")
def order_confirmation(order_no):
    o = get_db().execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not o:
        abort(404)
    items = json.loads(o["items"])
    return render_template("order_confirm.html", o=o, items=items)

# ---------------------------------------------------------------- accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        pw = request.form.get("password", "")
        if "@" not in email or len(pw) < 6:
            flash("Enter a valid email and a password of at least 6 characters.", "error")
            return render_template("register.html", email=email, name=name)
        db = get_db()
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash("That email already has an account. Try signing in.", "error")
            return render_template("register.html", email=email, name=name)
        db.execute("INSERT INTO users(email,password_hash,name,verified) VALUES(?,?,?,1)",
                   (email, generate_password_hash(pw), name))
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
        session["uid"] = uid
        flash("Account created. (Email verification is in test mode — you're in.)", "success")
        return redirect(url_for("account"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        u = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and check_password_hash(u["password_hash"], pw):
            session["uid"] = u["id"]
            flash(f"Welcome back{', ' + u['name'] if u['name'] else ''}!", "success")
            return redirect(request.args.get("next") or url_for("account"))
        flash("Email or password didn't match.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("uid", None)
    flash("Signed out.", "info")
    return redirect(url_for("home"))

@app.route("/account")
@login_required
def account():
    u = current_user()
    orders = get_db().execute(
        "SELECT * FROM orders WHERE user_id=? OR email=? ORDER BY created DESC",
        (u["id"], u["email"])).fetchall()
    orders = [dict(o, parsed=json.loads(o["items"])) for o in orders]
    return render_template("account.html", orders=orders)

# ---------------------------------------------------------------- admin
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if check_password_hash(get_setting("admin_password_hash"), pw):
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Wrong password.", "error")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "products": db.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
        "active": db.execute("SELECT COUNT(*) c FROM products WHERE active=1").fetchone()["c"],
        "orders": db.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "revenue": db.execute("SELECT COALESCE(SUM(total),0) s FROM orders").fetchone()["s"],
        "users": db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "low_stock": db.execute(
            "SELECT COUNT(*) c FROM products WHERE active=1 AND stock<=5").fetchone()["c"],
    }
    recent = db.execute("SELECT * FROM orders ORDER BY created DESC LIMIT 8").fetchall()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)

@app.route("/admin/products")
@admin_required
def admin_products():
    rows = get_db().execute("SELECT * FROM products ORDER BY sort, name").fetchall()
    rows = [dict(r, img=primary_image(r["id"])) for r in rows]
    return render_template("admin/products.html", products=rows)

def options_to_text(options_json):
    try:
        groups = json.loads(options_json or "[]")
    except Exception:
        return ""
    return "\n".join(f"{g['name']}: {', '.join(g['choices'])}" for g in groups)

def text_to_options(text):
    groups = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        choices = [c.strip() for c in rest.split(",") if c.strip()]
        if name.strip() and choices:
            groups.append({"name": name.strip(), "choices": choices})
    return json.dumps(groups)

def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "product"

@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_edit(pid=None):
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone() if pid else None
    if pid and not p:
        abort(404)
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip() or "Untitled product"
        slug = f.get("slug", "").strip() or slugify(name)
        slug = slugify(slug)
        # keep slug unique
        clash = db.execute("SELECT id FROM products WHERE slug=? AND id!=?",
                           (slug, pid or 0)).fetchone()
        if clash:
            slug = f"{slug}-{secrets.token_hex(2)}"
        vals = dict(
            name=name, slug=slug,
            category=f.get("category", "Gear").strip() or "Gear",
            price=f.get("price", 0, type=float) or 0,
            compare_price=f.get("compare_price", type=float),
            description=f.get("description", ""),
            options=text_to_options(f.get("options_text", "")),
            badge=f.get("badge", "").strip(),
            stock=f.get("stock", 0, type=int) or 0,
            active=1 if f.get("active") else 0,
            featured=1 if f.get("featured") else 0,
            sort=f.get("sort", 100, type=int) or 100,
        )
        # size chart: keep the current value if the form didn't send one
        sc = f.get("size_chart")
        if sc not in SIZE_CHART_KINDS:
            sc = (p["size_chart"] if p else "none")
        vals["size_chart"] = sc or "none"
        if p:
            db.execute("""UPDATE products SET name=:name, slug=:slug, category=:category,
                          price=:price, compare_price=:compare_price, description=:description,
                          options=:options, badge=:badge, stock=:stock, active=:active,
                          featured=:featured, sort=:sort, size_chart=:size_chart
                          WHERE id=:id""",
                       {**vals, "id": pid})
        else:
            cur = db.execute("""INSERT INTO products(name,slug,category,price,compare_price,
                             description,options,badge,stock,active,featured,sort,size_chart)
                             VALUES(:name,:slug,:category,:price,:compare_price,:description,
                             :options,:badge,:stock,:active,:featured,:sort,:size_chart)""", vals)
            pid = cur.lastrowid
        # image uploads — resized + compressed on arrival (see save_optimized_image)
        for file in request.files.getlist("images"):
            if file and file.filename and \
               file.filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXT:
                fn = save_optimized_image(file, f"{slug}-{secrets.token_hex(3)}")
                db.execute("INSERT INTO product_images(product_id,filename,sort) "
                           "VALUES(?,?,999)", (pid, f"__uploads__/{fn}"))
        db.commit()
        flash("Product saved.", "success")
        return redirect(url_for("admin_product_edit", pid=pid))
    images = product_images(pid) if pid else []
    return render_template("admin/product_edit.html", p=p, images=images,
                           options_text=options_to_text(p["options"]) if p else "")

def _remove_uploaded_file(filename):
    """Delete a photo file from disk, but only if it was an admin upload.
    Bundled images under static/img/ are never removed."""
    if filename and filename.startswith("__uploads__/"):
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename.split("/", 1)[1]))
        except OSError:
            pass

@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_product_delete(pid):
    db = get_db()
    for row in db.execute("SELECT filename FROM product_images WHERE product_id=?", (pid,)):
        _remove_uploaded_file(row["filename"])
    db.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()
    flash("Product deleted.", "info")
    return redirect(url_for("admin_products"))

@app.route("/admin/images/<int:img_id>/delete", methods=["POST"])
@admin_required
def admin_image_delete(img_id):
    db = get_db()
    row = db.execute("SELECT * FROM product_images WHERE id=?", (img_id,)).fetchone()
    if row:
        db.execute("DELETE FROM product_images WHERE id=?", (img_id,))
        db.commit()
        _remove_uploaded_file(row["filename"])
        return redirect(url_for("admin_product_edit", pid=row["product_id"]))
    return redirect(url_for("admin_products"))

@app.route("/admin/images/<int:img_id>/primary", methods=["POST"])
@admin_required
def admin_image_primary(img_id):
    db = get_db()
    row = db.execute("SELECT * FROM product_images WHERE id=?", (img_id,)).fetchone()
    if row:
        db.execute("UPDATE product_images SET sort=sort+1 WHERE product_id=?",
                   (row["product_id"],))
        db.execute("UPDATE product_images SET sort=0 WHERE id=?", (img_id,))
        db.commit()
        return redirect(url_for("admin_product_edit", pid=row["product_id"]))
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    rows = get_db().execute("SELECT * FROM orders ORDER BY created DESC").fetchall()
    return render_template("admin/orders.html", orders=rows)

@app.route("/admin/orders/<int:oid>", methods=["GET", "POST"])
@admin_required
def admin_order_detail(oid):
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        abort(404)
    if request.method == "POST":
        db.execute("UPDATE orders SET status=? WHERE id=?",
                   (request.form.get("status", "New"), oid))
        db.commit()
        flash("Order updated.", "success")
        return redirect(url_for("admin_order_detail", oid=oid))
    return render_template("admin/order_detail.html", o=o, items=json.loads(o["items"]))

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    keys = ["store_name", "announcement", "hero_eyebrow", "hero_title", "hero_sub",
            "hero_cta", "about_title", "about_text", "contact_email", "instagram",
            "shipping_flat", "free_ship_threshold", "show_story"]
    if request.method == "POST":
        for k in keys:
            if k == "show_story":
                set_setting(k, "1" if request.form.get(k) else "0")
            else:
                set_setting(k, request.form.get(k, ""))
        get_db().commit()
        flash("Site settings saved. Refresh the storefront to see changes.", "success")
        return redirect(url_for("admin_settings"))
    values = {k: get_setting(k, DEFAULT_SETTINGS.get(k, "")) for k in keys}
    return render_template("admin/settings.html", v=values)

@app.route("/admin/password", methods=["POST"])
@admin_required
def admin_password():
    new = request.form.get("new_password", "")
    if len(new) < 6:
        flash("New password must be at least 6 characters.", "error")
    else:
        set_setting("admin_password_hash", generate_password_hash(new))
        get_db().commit()
        flash("Admin password changed.", "success")
    return redirect(url_for("admin_settings"))

# serve admin-uploaded images through the product image path convention
@app.route("/pimg/<path:filename>")
def pimg(filename):
    if filename.startswith("__uploads__/"):
        return send_from_directory(UPLOAD_DIR, filename.split("/", 1)[1])
    return send_from_directory(os.path.join(BASE_DIR, "static", "img"), filename)

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
