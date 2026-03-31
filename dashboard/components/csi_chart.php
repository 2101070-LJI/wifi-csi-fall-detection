<div class="card mb-3">
  <div class="card-header d-flex justify-content-between align-items-center">
    <span>실시간 CSI 진폭</span>
    <span class="badge bg-secondary" id="csi-sample-count">0 samples</span>
  </div>
  <div class="card-body">
    <canvas id="csiChart" height="80"></canvas>
    <div id="csi-no-data" class="text-center text-muted py-3 d-none">
      수집된 CSI 데이터가 없습니다
    </div>
  </div>
</div>

<script>
(function () {
  const ctx = document.getElementById('csiChart').getContext('2d');
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: '평균 진폭',
        data: [],
        borderColor: '#00d26a',
        backgroundColor: 'rgba(0, 210, 106, 0.08)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      animation: false,
      scales: {
        x: { display: false },
        y: {
          min: 0,
          ticks: { color: '#aaa', maxTicksLimit: 5 },
          grid: { color: 'rgba(255,255,255,0.05)' }
        }
      },
      plugins: { legend: { display: false } }
    }
  });

  async function fetchCSI() {
    try {
      const res = await fetch('/api/csi/stream?n=100');
      const data = await res.json();
      const samples = data.samples ?? [];

      const noData = document.getElementById('csi-no-data');
      const canvas = document.getElementById('csiChart');

      if (samples.length === 0) {
        canvas.classList.add('d-none');
        noData.classList.remove('d-none');
        document.getElementById('csi-sample-count').textContent = '0 samples';
        return;
      }

      canvas.classList.remove('d-none');
      noData.classList.add('d-none');
      document.getElementById('csi-sample-count').textContent = samples.length + ' samples';

      chart.data.labels = samples.map(s => {
        return new Date(s.timestamp * 1000).toLocaleTimeString('ko-KR');
      });
      chart.data.datasets[0].data = samples.map(s => s.mean_amplitude);
      chart.update('none');
    } catch (e) {
      console.error('CSI fetch error:', e);
    }
  }

  fetchCSI();
  setInterval(fetchCSI, 2000);
})();
</script>
