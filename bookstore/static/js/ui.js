/*
  Small helpers for the Bookstore pages (no libraries needed):
    1. select.fancy      -> a dropdown that matches the site's look
    2. input[data-suggest] -> a text box that suggests names as you type
    3. form[data-busy]   -> disables the submit button and shows a message while sending
*/
(function () {
  "use strict";

  var uid = 0;
  var openMenu = null;                       // the dropdown that is open right now (only one at a time)

  function closeOpen() { if (openMenu) openMenu.close(); }

  document.addEventListener("click", function (e) {
    if (openMenu && !openMenu.owns(e.target)) openMenu.close();
  });
  // When the page scrolls or the window is resized, keep the menu attached to its
  // button (close it only if the button has scrolled out of sight).
  function follow(e) {
    if (!openMenu || (e && e.target instanceof Node && openMenu.menu.contains(e.target))) return;
    var r = openMenu.anchor.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) { openMenu.close(); return; }
    place(openMenu.menu, openMenu.anchor);
  }
  window.addEventListener("resize", follow);
  window.addEventListener("scroll", follow, true);

  // Put the floating menu under its button (or above it if there is no room below).
  function place(menu, anchor) {
    var r = anchor.getBoundingClientRect();
    menu.style.minWidth = r.width + "px";
    menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - menu.offsetWidth - 8)) + "px";
    var below = window.innerHeight - r.bottom;
    var h = Math.min(menu.scrollHeight, 280);
    if (below < h + 12 && r.top > below) {
      menu.style.top = Math.max(8, r.top - h - 6) + "px";
    } else {
      menu.style.top = (r.bottom + 6) + "px";
    }
  }

  function makeMenu() {
    var ul = document.createElement("ul");
    ul.className = "dd-menu";
    ul.setAttribute("role", "listbox");
    ul.id = "dd-menu-" + (++uid);
    ul.hidden = true;
    document.body.appendChild(ul);
    return ul;
  }

  function setActive(menu, items, index, control) {
    items.forEach(function (li, i) { li.classList.toggle("active", i === index); });
    if (index >= 0 && items[index]) {
      control.setAttribute("aria-activedescendant", items[index].id);
      items[index].scrollIntoView({ block: "nearest" });
    } else {
      control.removeAttribute("aria-activedescendant");
    }
  }

  /* ---------------------------------------------------------------- 1. select */
  function enhanceSelect(select) {
    var wrap = document.createElement("div");
    wrap.className = "dd";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dd-btn";
    btn.setAttribute("role", "combobox");
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    if (select.getAttribute("aria-label")) btn.setAttribute("aria-label", select.getAttribute("aria-label"));
    btn.innerHTML = '<span class="dd-label"></span>' +
      '<svg class="dd-chev" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">' +
      '<path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var label = btn.firstChild;

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(btn);
    wrap.appendChild(select);                // stays in the form, so it still submits its value
    select.style.display = "none";
    select.tabIndex = -1;

    var menu = makeMenu();
    btn.setAttribute("aria-controls", menu.id);
    var items = [], active = -1, typed = "", typedTimer = null;

    function build() {
      menu.innerHTML = "";
      items = [];
      Array.prototype.forEach.call(select.options, function (opt, i) {
        var li = document.createElement("li");
        li.className = "dd-opt";
        li.id = menu.id + "-o" + i;
        li.setAttribute("role", "option");
        li.textContent = opt.text;
        li.dataset.index = i;
        li.setAttribute("aria-selected", opt.selected ? "true" : "false");
        if (opt.disabled) li.setAttribute("aria-disabled", "true");
        li.addEventListener("click", function () { choose(i); });
        li.addEventListener("mousemove", function () { setActive(menu, items, items.indexOf(li), btn); active = items.indexOf(li); });
        menu.appendChild(li);
        items.push(li);
      });
    }

    function refreshLabel() {
      var opt = select.options[select.selectedIndex];
      label.textContent = opt ? opt.text : "";
    }

    function choose(i) {
      if (select.options[i] && !select.options[i].disabled) {
        select.selectedIndex = i;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        refreshLabel();
      }
      close();
      btn.focus();
    }

    function open() {
      if (menu.hidden === false) return;
      closeOpen();
      build();
      menu.hidden = false;
      wrap.classList.add("open");
      btn.setAttribute("aria-expanded", "true");
      active = select.selectedIndex;
      place(menu, btn);
      setActive(menu, items, active, btn);
      openMenu = { menu: menu, anchor: btn, close: close, owns: function (t) { return wrap.contains(t) || menu.contains(t); } };
    }

    function close() {
      menu.hidden = true;
      wrap.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
      btn.removeAttribute("aria-activedescendant");
      if (openMenu && openMenu.menu === menu) openMenu = null;
    }

    function move(step) {
      var n = items.length, i = active;
      for (var k = 0; k < n; k++) {
        i = (i + step + n) % n;
        if (!select.options[i].disabled) break;
      }
      active = i;
      setActive(menu, items, active, btn);
    }

    btn.addEventListener("click", function () { menu.hidden ? open() : close(); });
    btn.addEventListener("keydown", function (e) {
      var isOpen = !menu.hidden;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!isOpen) open(); else move(e.key === "ArrowDown" ? 1 : -1);
      } else if (e.key === "Home" && isOpen) { e.preventDefault(); active = -1; move(1); }
      else if (e.key === "End" && isOpen) { e.preventDefault(); active = 0; move(-1); }
      else if ((e.key === "Enter" || e.key === " ") && isOpen) { e.preventDefault(); choose(active); }
      else if (e.key === "Escape" && isOpen) { e.preventDefault(); close(); }
      else if (e.key === "Tab" && isOpen) { close(); }
      else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && e.key !== " ") {
        // type a few letters to jump to an option
        typed += e.key.toLowerCase();
        clearTimeout(typedTimer);
        typedTimer = setTimeout(function () { typed = ""; }, 700);
        for (var i = 0; i < select.options.length; i++) {
          if (select.options[i].text.toLowerCase().indexOf(typed) === 0) {
            if (menu.hidden) { select.selectedIndex = i; select.dispatchEvent(new Event("change", { bubbles: true })); refreshLabel(); }
            else { active = i; setActive(menu, items, i, btn); }
            break;
          }
        }
      }
    });

    refreshLabel();
  }

  /* -------------------------------------------------------------- 2. suggest */
  function enhanceSuggest(input) {
    var names;
    try { names = JSON.parse(input.getAttribute("data-suggest") || "[]"); } catch (err) { names = []; }
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    var menu = makeMenu();
    input.setAttribute("aria-controls", menu.id);
    var items = [], active = -1;

    function matches() {
      var q = input.value.trim().toLowerCase();
      return names.filter(function (n) { return !q || n.toLowerCase().indexOf(q) !== -1; }).slice(0, 40);
    }

    function show() {
      var list = matches();
      if (!list.length || (list.length === 1 && list[0] === input.value)) { hide(); return; }
      closeOpen();
      menu.innerHTML = "";
      items = list.map(function (n, i) {
        var li = document.createElement("li");
        li.className = "dd-opt";
        li.id = menu.id + "-o" + i;
        li.setAttribute("role", "option");
        li.textContent = n;
        li.addEventListener("mousedown", function (e) { e.preventDefault(); pick(n); });
        menu.appendChild(li);
        return li;
      });
      active = -1;
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      place(menu, input);
      openMenu = { menu: menu, anchor: input, close: hide, owns: function (t) { return t === input || menu.contains(t); } };
    }

    function hide() {
      menu.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      if (openMenu && openMenu.menu === menu) openMenu = null;
    }

    function pick(name) { input.value = name; hide(); }

    input.addEventListener("focus", show);
    input.addEventListener("input", show);
    input.addEventListener("blur", hide);
    input.addEventListener("keydown", function (e) {
      if (menu.hidden) { if (e.key === "ArrowDown") { show(); e.preventDefault(); } return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        setActive(menu, items, active, input);
      } else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(items[active].textContent); }
      else if (e.key === "Escape") { e.preventDefault(); hide(); }
    });
  }

  /* ----------------------------------------------------------------- 3. busy */
  function enhanceBusy(form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector('button[type="submit"]');
      if (!btn || form.dataset.sent) return;
      form.dataset.sent = "1";
      var text = form.getAttribute("data-busy");
      setTimeout(function () { btn.disabled = true; btn.textContent = text; }, 0);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("select.fancy"), enhanceSelect);
    Array.prototype.forEach.call(document.querySelectorAll("input[data-suggest]"), enhanceSuggest);
    Array.prototype.forEach.call(document.querySelectorAll("form[data-busy]"), enhanceBusy);
  });
  // Coming back with the browser's Back button: let the pay/save buttons work again.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) window.location.reload();
  });
})();
