(() => {
  const form = document.querySelector('#bookingForm');
  if (!form) return;
  const statusEl = document.querySelector('#formStatus');
  const submit = document.querySelector('#submitBtn');
  const carSelect = document.querySelector('#carSelect');
  const passengerCount = document.querySelector('#passengerCount');
  const tripType = document.querySelector('#tripType');
  const returnRow = document.querySelector('#returnDateRow');
  const returnDate = document.querySelector('#returnDate');
  const departure = document.querySelector('#travelDate');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  departure.min = today;
  returnDate.min = today;

  function syncTrip() {
    const isRoundTrip = tripType.value === 'round_trip';
    returnRow.hidden = !isRoundTrip;
    returnDate.required = isRoundTrip;
    if (!isRoundTrip) returnDate.value = '';
  }
  tripType.addEventListener('change', syncTrip);
  departure.addEventListener('change', () => {
    returnDate.min = departure.value || today;
    if (returnDate.value && returnDate.value < returnDate.min) returnDate.value = '';
  });
  syncTrip();

  carSelect.addEventListener('change', () => {
    const maxSeats = Number(carSelect.selectedOptions[0]?.dataset.seats);
    if (maxSeats) {
      passengerCount.max = maxSeats;
      if (Number(passengerCount.value) > maxSeats) passengerCount.value = maxSeats;
    } else passengerCount.max = 50;
  });
  document.querySelectorAll('[data-car]').forEach(link => {
    link.addEventListener('click', () => {
      carSelect.value = link.dataset.car;
      carSelect.dispatchEvent(new Event('change'));
    });
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    statusEl.textContent = '';
    statusEl.className = 'form-status';
    submit.disabled = true;
    const oldLabel = submit.innerHTML;
    submit.textContent = 'Đang lưu yêu cầu...';
    try {
      const data = Object.fromEntries(new FormData(form).entries());
      const response = await fetch('/api/bookings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
        body: JSON.stringify(data)
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || 'Có lỗi khi gửi yêu cầu.');
      statusEl.textContent = result.message;
      statusEl.classList.add('success');
      form.reset();
      passengerCount.value = '1';
      syncTrip();
    } catch (error) {
      statusEl.textContent = error.message || 'Không kết nối được đến máy chủ.';
      statusEl.classList.add('error');
    } finally {
      submit.disabled = false;
      submit.innerHTML = oldLabel;
    }
  });
})();
