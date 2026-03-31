<div class="card h-100">
  <div class="card-header d-flex justify-content-between align-items-center">
    <span>낙상 이벤트 이력</span>
    <button class="btn btn-sm btn-outline-light" onclick="fetchEvents()">새로고침</button>
  </div>
  <div class="card-body p-0">
    <div class="table-responsive" style="max-height: 420px; overflow-y: auto;">
      <table class="table table-dark table-sm table-hover mb-0">
        <thead class="sticky-top" style="background: #0f3460;">
          <tr>
            <th class="ps-3">감지 시각</th>
            <th>신뢰도</th>
            <th>충격음</th>
            <th>판정</th>
          </tr>
        </thead>
        <tbody id="event-tbody">
          <tr>
            <td colspan="4" class="text-center text-muted py-3">로딩 중...</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="px-3 py-2 small text-muted" id="event-total"></div>
  </div>
</div>

<script>
async function fetchEvents() {
  try {
    const res = await fetch('/api/events?limit=50');
    const data = await res.json();
    const tbody = document.getElementById('event-tbody');
    const totalEl = document.getElementById('event-total');

    totalEl.textContent = '전체 ' + (data.total ?? 0) + '건';

    if (!data.events || data.events.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">이벤트 없음</td></tr>';
      return;
    }

    tbody.innerHTML = data.events.map(e => {
      const confirmedBadge = e.confirmed
        ? '<span class="badge bg-danger">낙상 확정</span>'
        : '<span class="badge bg-secondary">미확정</span>';
      const impactBadge = e.impact_detected
        ? '<span class="badge bg-warning text-dark">감지</span>'
        : '<span class="text-muted">-</span>';
      const confPct = (e.csi_confidence * 100).toFixed(1) + '%';
      return `
        <tr>
          <td class="ps-3 small">${e.detected_at ?? '-'}</td>
          <td>${confPct}</td>
          <td>${impactBadge}</td>
          <td>${confirmedBadge}</td>
        </tr>`;
    }).join('');
  } catch (e) {
    console.error('Events fetch error:', e);
  }
}

fetchEvents();
setInterval(fetchEvents, 10000);
</script>
