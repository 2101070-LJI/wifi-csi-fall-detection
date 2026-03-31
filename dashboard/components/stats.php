<div class="card h-100">
  <div class="card-header">일별 낙상 통계 (최근 30일)</div>
  <div class="card-body pb-1">
    <canvas id="dailyChart" height="130"></canvas>
  </div>
  <div class="card-header border-top">시간대별 분포 (최근 7일)</div>
  <div class="card-body">
    <canvas id="hourlyChart" height="130"></canvas>
  </div>
</div>

<script>
(function () {
  const CHART_OPTS = {
    responsive: true,
    scales: {
      x: { ticks: { color: '#aaa', maxRotation: 45 }, grid: { color: 'rgba(255,255,255,0.05)' } },
      y: { beginAtZero: true, ticks: { color: '#aaa', precision: 0 }, grid: { color: 'rgba(255,255,255,0.05)' } }
    },
    plugins: { legend: { labels: { color: '#ccc', boxWidth: 12 } } }
  };

  const dailyChart = new Chart(
    document.getElementById('dailyChart').getContext('2d'),
    {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          { label: '전체 감지', data: [], backgroundColor: 'rgba(13,110,253,0.6)' },
          { label: '낙상 확정', data: [], backgroundColor: 'rgba(220,53,69,0.8)' },
        ]
      },
      options: CHART_OPTS
    }
  );

  const hourlyData = Array(24).fill(0);
  const hourlyChart = new Chart(
    document.getElementById('hourlyChart').getContext('2d'),
    {
      type: 'bar',
      data: {
        labels: Array.from({ length: 24 }, (_, i) => i + '시'),
        datasets: [{ label: '감지 수', data: [...hourlyData], backgroundColor: 'rgba(255,193,7,0.7)' }]
      },
      options: CHART_OPTS
    }
  );

  async function fetchStats() {
    try {
      const res = await fetch('/api/stats');
      const data = await res.json();

      // 일별
      const daily = data.daily ?? [];
      dailyChart.data.labels = daily.map(d => d.date);
      dailyChart.data.datasets[0].data = daily.map(d => d.total);
      dailyChart.data.datasets[1].data = daily.map(d => d.confirmed ?? 0);
      dailyChart.update();

      // 시간대별
      const hData = Array(24).fill(0);
      (data.hourly ?? []).forEach(h => { hData[h.hour] = h.total; });
      hourlyChart.data.datasets[0].data = hData;
      hourlyChart.update();
    } catch (e) {
      console.error('Stats fetch error:', e);
    }
  }

  fetchStats();
  setInterval(fetchStats, 30000);
})();
</script>
