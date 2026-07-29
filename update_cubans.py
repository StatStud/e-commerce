"""
update_cubans.py — collapse every Cuban chain page into ONE product with a
"Color" option (Silver / Gold / Rose Gold) and install the new photo set.

Usage (from the project folder, next to diamond.db):

    python3 update_cubans.py            # DRY RUN: shows the plan, changes nothing
    python3 update_cubans.py --apply    # actually applies it

What it does:
  1. Finds every ACTIVE product with "cuban" in its name (case-insensitive).
  2. Picks the master: the product with slug 'cuban-link-chain' if present,
     otherwise the first by sort/id. All other matches are variants.
  3. Master gets option  Color: Silver, Gold, Rose Gold  (replacing any old
     Color/Finish group; any other option groups it had are kept).
  4. Stock from all variants is summed into the master; variants are
     DEACTIVATED (not deleted — restore or delete them in the admin later).
  5. The master's photo gallery is REPLACED with the 8 new images, in
     color order matching the dropdown:
        silver x2, gold x3, rose gold x3 (primary = silver full-chain shot)
     (Old gallery rows are removed from the DB; the old files stay on disk.)

BACK UP FIRST:  cp diamond.db diamond.db.bak
"""
import json, os, sqlite3, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "diamond.db")
APPLY = "--apply" in sys.argv

NEW_IMAGES = [
    "products/cuban_silver_1.jpg",    # silver — full chain  (primary)
    "products/cuban_silver_2.jpg",    # silver — clasp closeup
    "products/cuban_gold_1.jpg",      # gold — full chain spread
    "products/cuban_gold_2.jpg",      # gold — coiled
    "products/cuban_gold_3.jpg",      # gold — clasp closeup
    "products/cuban_rosegold_1.jpg",  # rose gold — full chain
    "products/cuban_rosegold_2.jpg",  # rose gold — angled clasp
    "products/cuban_rosegold_3.jpg",  # rose gold — clasp closeup
]
COLORS = ["Silver", "Gold", "Rose Gold"]

def main():
    # sanity: the new image files must exist before we touch the DB
    missing = [f for f in NEW_IMAGES
               if not os.path.exists(os.path.join(BASE, "static", "img", f))]
    if missing:
        print("ABORT — these image files are missing from static/img/:")
        for m in missing:
            print("  ", m)
        print("Unzip cuban_update.zip into the project folder first.")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM products WHERE active=1 AND name LIKE '%cuban%' COLLATE NOCASE "
        "ORDER BY sort, id").fetchall()
    if not rows:
        print("No active products with 'cuban' in the name were found. Nothing to do.")
        return

    master = next((r for r in rows if r["slug"] == "cuban-link-chain"), rows[0])
    variants = [r for r in rows if r["id"] != master["id"]]

    print(f"MASTER  -> #{master['id']} '{master['name']}' (slug {master['slug']}) "
          f"${master['price']} stock={master['stock']}")
    total_stock = master["stock"]
    for v in variants:
        total_stock += v["stock"]
        print(f"VARIANT -> #{v['id']} '{v['name']}' ${v['price']} stock={v['stock']} "
              f"(will be deactivated)")
        if v["price"] != master["price"]:
            print(f"   !! price differs from master; master's ${master['price']} wins")

    old_imgs = conn.execute("SELECT COUNT(*) c FROM product_images WHERE product_id=?",
                            (master["id"],)).fetchone()["c"]

    # options: keep non-color groups, set Color fresh
    try:
        groups = json.loads(master["options"] or "[]")
    except Exception:
        groups = []
    groups = [g for g in groups
              if g.get("name", "").lower() not in ("color", "colour", "finish")]
    groups.insert(0, {"name": "Color", "choices": COLORS})

    print(f"\nPLAN: option 'Color: {', '.join(COLORS)}'")
    print(f"      stock {master['stock']} -> {total_stock}")
    print(f"      gallery: {old_imgs} old image(s) replaced by {len(NEW_IMAGES)} new")
    if not variants:
        print("      (no variant pages found — just updating the one product)")

    if not APPLY:
        print("\nDRY RUN ONLY — nothing changed. Re-run with --apply to do it.")
        return

    for v in variants:
        conn.execute("UPDATE products SET active=0 WHERE id=?", (v["id"],))
    conn.execute("DELETE FROM product_images WHERE product_id=?", (master["id"],))
    for i, fn in enumerate(NEW_IMAGES):
        conn.execute("INSERT INTO product_images(product_id,filename,sort) VALUES(?,?,?)",
                     (master["id"], fn, i))
    conn.execute("UPDATE products SET options=?, stock=? WHERE id=?",
                 (json.dumps(groups), total_stock, master["id"]))
    conn.commit()
    print(f"\nDONE. Product #{master['id']} now has the Color option and the new "
          f"8-photo gallery. Reload the web app and check /product/{master['slug']}")

if __name__ == "__main__":
    main()
