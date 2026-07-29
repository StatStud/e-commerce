# Grand Slam Glasses — update notes

## What's new
A new product, **Grand Slam Glasses** (slug `grand-slam-glasses`, Accessories, $19.99,
27 colorways), with an Amazon-style gallery: picking a colorway shows exactly
5 images — front, angled, side for that color, plus the shared
"Product Dimensions & Fit" and "Adjustable Temple" info images.

## Files changed / added
- `app.py`
  - `SIZE_CHART_KINDS` now includes `glasses`; `size_chart_images()` returns the
    fit + temple pair for it (same mechanism the mitts use for youth/adult charts)
  - seed `add()` accepts a `size_chart` argument; new seed entry for the product
  - product route tags gallery images with a `variant` key when filenames follow
    `<group>/<NN_variant>/<file>.jpg`
- `templates/product.html` — thumbs carry `data-variant`
- `static/js/main.js` — gallery filters to the selected colorway (info images always shown)
- `templates/admin/product_edit.html` — new "Sunglasses info (fit + temple)" size-chart option
- `static/img/glasses/<NN_colorway>/{01_front,02_angled,03_side}.jpg` — 27 folders, 81 photos
- `static/img/size_charts/glasses_fit.jpg`, `glasses_temple.jpg` — shared info images
- `diamond.db` — product + 81 image rows inserted (fresh databases get it from the seed)

## How to deploy
Extract this zip **at the repo root** (`unzip -o` over the project). Paths inside the
zip are already repo-relative — `static/` and `templates/` sit at the top level,
nothing nested. Then reload the web app.

If your live server's `diamond.db` differs from the repo copy, don't overwrite it —
instead add the product once via admin, or run the insert snippet in this repo's
history, and set its Size chart to "Sunglasses info (fit + temple)".

## Adding future colorways
Drop a new folder `static/img/glasses/28_<color-slug>/` with the three photos, add the
matching colorway name to the product's options in admin (name must slugify to the
folder suffix, e.g. "Teal / White" → `teal-white`), and add the three images to the
product. The gallery filtering picks it up automatically.
