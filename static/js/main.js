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
