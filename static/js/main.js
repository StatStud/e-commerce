// Diamond Dripp storefront JS
document.addEventListener('DOMContentLoaded', function () {

  // product gallery thumbs
  document.querySelectorAll('.thumb').forEach(function (t) {
    t.addEventListener('click', function () {
      document.querySelectorAll('.thumb').forEach(x => x.classList.remove('on'));
      t.classList.add('on');
      var main = document.getElementById('mainImg');
      if (main) main.src = t.dataset.src;
    });
  });

  // variant-aware gallery: when a product's photos are grouped by colorway
  // (thumbs carry data-variant), show only the selected colorway's photos.
  // Thumbs with an empty data-variant (size charts / info images) always show.
  (function () {
    var thumbs = Array.prototype.slice.call(document.querySelectorAll('.thumb[data-variant]'));
    var keyed = thumbs.filter(function (t) { return t.dataset.variant; });
    if (!keyed.length) return;
    var slug = function (s) {
      return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    };
    var keys = {};
    keyed.forEach(function (t) { keys[t.dataset.variant] = true; });
    // find the option select whose choices map onto the variant keys
    var sel = Array.prototype.slice.call(document.querySelectorAll('#buyForm select'))
      .find(function (s) {
        return Array.prototype.some.call(s.options, function (o) { return keys[slug(o.value)]; });
      });
    if (!sel) return;
    var apply = function () {
      var k = slug(sel.value), first = null;
      thumbs.forEach(function (t) {
        var show = !t.dataset.variant || t.dataset.variant === k;
        t.style.display = show ? '' : 'none';
        if (show && !first) first = t;
      });
      if (first) {
        thumbs.forEach(function (t) { t.classList.remove('on'); });
        first.classList.add('on');
        var main = document.getElementById('mainImg');
        if (main) main.src = first.dataset.src;
      }
    };
    sel.addEventListener('change', apply);
    apply();
  })();

  // qty steppers
  document.querySelectorAll('.qty-stepper').forEach(function (s) {
    var input = s.querySelector('input');
    s.querySelectorAll('button[data-step]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = parseInt(input.value || '1', 10) + parseInt(b.dataset.step, 10);
        input.value = Math.max(1, Math.min(99, v));
      });
    });
  });

  // ajax add-to-cart with toast
  var buyForm = document.getElementById('buyForm');
  if (buyForm) {
    buyForm.addEventListener('submit', function (e) {
      e.preventDefault();
      fetch(buyForm.action, {
        method: 'POST',
        body: new FormData(buyForm),
        headers: { 'X-Requested-With': 'fetch' }
      }).then(r => r.json()).then(function (d) {
        if (d.ok) {
          var c = document.getElementById('cartCount');
          if (c) c.textContent = d.count;
          toast('Added to cart — ' + d.name);
        }
      }).catch(function () { buyForm.submit(); });
    });
  }

  function toast(msg) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(function () { t.classList.remove('show'); }, 2600);
  }
});
