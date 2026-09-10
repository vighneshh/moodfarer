self.addEventListener('push', function (event) {
  let data = { title: 'Daily Check-in', body: "Don't forget today's check-in." , url: '/' };
  try {
    if (event.data) data = Object.assign(data, event.data.json());
  } catch (e) {
    // Fall back to defaults if the payload wasn't JSON.
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      data: { url: data.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((all) => {
      for (const client of all) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
