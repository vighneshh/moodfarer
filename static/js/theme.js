window.CheckinTheme = (function () {
  function isDarkFor(pref) {
    if (pref === 'dark') return true;
    if (pref === 'light') return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function apply(pref) {
    document.documentElement.classList.toggle('dark', isDarkFor(pref));
  }

  async function set(pref, opts) {
    opts = opts || {};
    localStorage.setItem('theme', pref);
    apply(pref);

    if (opts.persist) {
      try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
        await fetch('/api/theme', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
          body: JSON.stringify({ theme: pref }),
        });
      } catch (e) {
        // Non-fatal — the preference still applies locally via localStorage.
      }
    }
  }

  return { apply, set };
})();
