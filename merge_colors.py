"""
merge_colors.py — collapse per-color product pages into ONE product with a
"Color" option (same pattern as the Signature Sunglasses).

Usage (from the project folder, next to diamond.db):

    python3 merge_colors.py                  # DRY RUN: shows the plan, changes nothing
    python3 merge_colors.py --apply          # actually performs the merge

By default it targets products whose name starts with:
    "Diamond Dripp Signature Sliding Mitt"
Change NAME_PREFIX below if your naming differs.

What it does:
  1. Finds every active product whose name starts with NAME_PREFIX.
  2. Uses the leftover text after the prefix as that variant's Color label
     (e.g. "Diamond Dripp Signature Sliding Mitt - Red/White" -> "Red/White").
  3. Keeps ONE product (the lowest sort/id) as the master:
       - renames it to exactly NAME_PREFIX
       - adds a "Color: ..." option listing every variant color
       - keeps any other option groups the master already had (e.g. Size)
       - sums stock from all variants into it
  4. Moves every variant's images onto the master (appended after its own,
     in color order) so all colors show in the master's gallery.
  5. DEACTIVATES the variant products (not deleted — flip them back on in
     the admin if anything looks wrong, or delete them there later).

BACK UP FIRST:  cp diamond.db diamond.db.bak
"""
import json, re, sqlite3, sys, os

NAME_PREFIX = "Diamond Dripp Signature Sliding Mitt"
OPTION_NAME = "Color"
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diamond.db")

APPLY = "--apply" in sys.argv

def color_label(full_name: str) -> str:
    """'<prefix> - Red/White (Youth)' -> 'Red/White (Youth)'"""
    rest = full_name[len(NAME_PREFIX):]
    rest = re.sub(r"^[\s\-–—:,|]+", "", rest).strip()
    return rest or full_name.strip()

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM products WHERE active=1 AND name LIKE ? ORDER BY sort, id",
        (NAME_PREFIX + "%",)).fetchall()

    if len(rows) < 2:
        print(f"Found {len(rows)} active product(s) starting with '{NAME_PREFIX}'.")
        print("Nothing to merge. Check NAME_PREFIX matches your product names exactly.")
        return

    master, variants = rows[0], rows[1:]
    print(f"MASTER  -> #{master['id']} '{master['name']}'  ${master['price']}  stock={master['stock']}")

    colors, total_stock, price_mismatch = [], master["stock"], []
    lbl = color_label(master["name"])
    colors.append(lbl if lbl != master["name"].strip() else "Original")

    for v in variants:
        c = color_label(v["name"])
        colors.append(c)
        total_stock += v["stock"]
        if v["price"] != master["price"]:
            price_mismatch.append((v["name"], v["price"]))
        n_imgs = conn.execute("SELECT COUNT(*) c FROM product_images WHERE product_id=?",
                              (v["id"],)).fetchone()["c"]
        print(f"VARIANT -> #{v['id']} '{v['name']}'  color='{c}'  "
              f"${v['price']}  stock={v['stock']}  images={n_imgs}")

    # de-dupe colors, preserve order
    seen, ordered = set(), []
    for c in colors:
        if c.lower() not in seen:
            seen.add(c.lower()); ordered.append(c)

    # merge option groups: keep master's non-Color groups, add/replace Color
    try:
        groups = json.loads(master["options"] or "[]")
    except Exception:
        groups = []
    groups = [g for g in groups if g.get("name", "").lower() != OPTION_NAME.lower()]
    groups.insert(0, {"name": OPTION_NAME, "choices": ordered})

    print(f"\nPLAN: master keeps name '{NAME_PREFIX}', gains option "
          f"'{OPTION_NAME}: {', '.join(ordered)}'")
    print(f"      stock {master['stock']} -> {total_stock} (summed)")
    print(f"      {len(variants)} variant page(s) will be deactivated; "
          f"their images move to the master's gallery")
    if price_mismatch:
        print("\n  !! PRICE WARNING — these variants have a different price; "
              "the master's price wins (one price per product):")
        for n, p in price_mismatch:
            print(f"     '{n}' was ${p}")

    if not APPLY:
        print("\nDRY RUN ONLY — nothing changed. Re-run with --apply to do it.")
        return

    # ---- apply ----
    next_sort = (conn.execute(
        "SELECT COALESCE(MAX(sort),0) m FROM product_images WHERE product_id=?",
        (master["id"],)).fetchone()["m"]) + 1
    for v in variants:
        for img in conn.execute(
                "SELECT id FROM product_images WHERE product_id=? ORDER BY sort, id",
                (v["id"],)).fetchall():
            conn.execute("UPDATE product_images SET product_id=?, sort=? WHERE id=?",
                         (master["id"], next_sort, img["id"]))
            next_sort += 1
        conn.execute("UPDATE products SET active=0 WHERE id=?", (v["id"],))

    conn.execute("UPDATE products SET name=?, options=?, stock=? WHERE id=?",
                 (NAME_PREFIX, json.dumps(groups), total_stock, master["id"]))
    conn.commit()
    print(f"\nDONE. Merged into product #{master['id']} "
          f"(slug '{master['slug']}'). Variants deactivated, not deleted.")
    print("Reload the web app, check the product page, then delete the "
          "deactivated variants in the admin whenever you're confident.")

if __name__ == "__main__":
    main()