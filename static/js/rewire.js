(function () {
  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  document.querySelectorAll('.rewire-day').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const key = btn.dataset.key;
      const day = btn.dataset.day;
      const week = btn.dataset.week;

      const wasDone = btn.classList.contains('is-done');
      btn.classList.toggle('is-done', !wasDone);
      const card = btn.closest('[data-rewirement]');
      const badge = card?.querySelector('.rewire-badge');
      if (badge) {
        const [done, total] = badge.textContent.trim().split('/').map((n) => parseInt(n, 10));
        badge.textContent = `${done + (wasDone ? -1 : 1)}/${total}`;
      }

      try {
        const res = await fetch('/api/rewire/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
          body: JSON.stringify({ rewirement_key: key, day_key: day, week_start: week }),
        });
        if (!res.ok) throw new Error('failed');
        const data = await res.json();
        btn.classList.toggle('is-done', data.completed);
      } catch (e) {
        btn.classList.toggle('is-done', wasDone);
        if (badge) {
          const [done, total] = badge.textContent.trim().split('/').map((n) => parseInt(n, 10));
          badge.textContent = `${done + (wasDone ? 1 : -1)}/${total}`;
        }
      }
    });
  });

  document.querySelectorAll('.rewire-note').forEach((input) => {
    let saveTimer = null;
    const save = async () => {
      try {
        await fetch('/api/rewire/note', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
          body: JSON.stringify({
            rewirement_key: input.dataset.key,
            day_key: input.dataset.day,
            week_start: input.dataset.week,
            note: input.value,
          }),
        });
      } catch (e) {}
    };
    input.addEventListener('blur', save);
    input.addEventListener('input', () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(save, 800);
    });
  });
})();