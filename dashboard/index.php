<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WiFi-CSI 낙상 감지 대시보드</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body          { background: #1a1a2e; color: #e0e0e0; }
    .card         { background: #16213e; border: 1px solid #0f3460; }
    .card-header  { background: #0f3460; border-bottom: 1px solid #1a4a8a; }
    .table-dark   { --bs-table-bg: #0d1b2a; --bs-table-hover-bg: #112240; }
    .status-dot   {
      width: 12px; height: 12px; border-radius: 50%;
      display: inline-block; vertical-align: middle;
    }
    .dot-running  { background: #00d26a; animation: blink 1.5s infinite; }
    .dot-stopped  { background: #dc3545; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
  </style>
</head>
<body>

<!-- 네비게이션 바 -->
<nav class="navbar navbar-dark py-2" style="background: #0f3460;">
  <div class="container-fluid">
    <span class="navbar-brand fw-bold fs-5">WiFi-CSI 낙상 감지 시스템</span>
    <span id="clock" class="text-light small font-monospace"></span>
  </div>
</nav>

<div class="container-fluid mt-3 pb-4">

  <!-- 상태 요약 카드 3개 -->
  <div class="row g-3 mb-3">
    <div class="col-md-4">
      <div class="card h-100">
        <div class="card-header">시스템 상태</div>
        <div class="card-body">
          <span class="status-dot dot-running me-2"></span>
          <span id="sys-label" class="fw-semibold">운영 중</span>
          <div class="mt-2 small text-muted">
            마지막 갱신: <span id="last-update">-</span>
          </div>
        </div>
      </div>
    </div>

    <div class="col-md-4">
      <div class="card h-100">
        <div class="card-header">마지막 낙상 이벤트</div>
        <div class="card-body" id="last-event-card">
          <span class="text-muted">이벤트 없음</span>
        </div>
      </div>
    </div>

    <div class="col-md-4">
      <div class="card h-100">
        <div class="card-header">누적 낙상 확정</div>
        <div class="card-body">
          <h2 class="text-danger mb-0" id="confirmed-total">-</h2>
          <div class="small text-muted mt-1">confirmed = 1 이벤트 합계</div>
        </div>
      </div>
    </div>
  </div>

  <!-- CSI 파형 차트 -->
  <?php include __DIR__ . '/components/csi_chart.php'; ?>

  <!-- 이벤트 타임라인 + 통계 -->
  <div class="row g-3 mt-0">
    <div class="col-lg-6">
      <?php include __DIR__ . '/components/event_timeline.php'; ?>
    </div>
    <div class="col-lg-6">
      <?php include __DIR__ . '/components/stats.php'; ?>
    </div>
  </div>

</div><!-- /container-fluid -->

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

<script>
// 실시간 시계
(function () {
  function tick() {
    document.getElementById('clock').textContent =
      new Date().toLocaleString('ko-KR', { hour12: false });
  }
  tick();
  setInterval(tick, 1000);
})();

// 상태 카드 갱신 (5초마다)
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    document.getElementById('confirmed-total').textContent =
      data.confirmed_total ?? '-';

    if (data.last_event) {
      const e = data.last_event;
      const badge = e.confirmed
        ? '<span class="badge bg-danger me-1">낙상 확정</span>'
        : '<span class="badge bg-warning text-dark me-1">미확정</span>';
      const impact = e.impact_detected
        ? '<span class="badge bg-warning text-dark">충격음 감지</span>'
        : '';
      document.getElementById('last-event-card').innerHTML =
        `${badge}${impact}
         <div class="mt-1 small">${e.detected_at ?? ''}</div>
         <div class="small text-muted">신뢰도 ${(e.csi_confidence * 100).toFixed(1)}%</div>`;
    }

    document.getElementById('last-update').textContent =
      new Date().toLocaleTimeString('ko-KR');
  } catch (e) {
    console.error('Status fetch error:', e);
  }
}

fetchStatus();
setInterval(fetchStatus, 5000);
</script>

</body>
</html>
