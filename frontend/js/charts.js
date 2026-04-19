/**
 * Charts.js — Gráfico P&L con Chart.js
 */

let pnlChart = null;

function initPnlChart() {
  const ctx = document.getElementById('pnl-chart');
  if (!ctx) return;

  pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'P&L Realizado ($)',
        data: [],
        borderColor: '#4299e1',
        backgroundColor: 'rgba(66,153,225,0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: '#4299e1',
        pointBorderColor: '#080c14',
        pointBorderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#8b9bb4', font: { family: 'Inter', size: 12 } }
        },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: 'rgba(255,255,255,0.08)',
          borderWidth: 1,
          titleColor: '#f0f6ff',
          bodyColor: '#8b9bb4',
          padding: 12,
          callbacks: {
            label: (ctx) => {
              const val = ctx.raw;
              const color = val >= 0 ? '🟢' : '🔴';
              return `${color} P&L: $${val.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#4a5568', font: { size: 11 } }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#4a5568',
            font: { size: 11 },
            callback: (v) => `$${v.toFixed(0)}`
          }
        }
      }
    }
  });
}

async function loadPnl(days = 30) {
  // Actualizar botones activos
  document.querySelectorAll('.btn-tab').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.includes(days));
  });

  try {
    const res = await fetch(`/pnl?days=${days}`);
    const data = await res.json();

    if (!pnlChart || !data.length) return;

    const labels = data.map(d => {
      const dt = new Date(d.date);
      return dt.toLocaleDateString('es-ES', { month: 'short', day: 'numeric' });
    });
    const values = data.map(d => d.realized_pnl || 0);

    // Color dinámico según tendencia
    const lastVal = values[values.length - 1] || 0;
    const color = lastVal >= 0 ? '#48bb78' : '#fc8181';
    pnlChart.data.datasets[0].borderColor = color;
    pnlChart.data.datasets[0].backgroundColor = lastVal >= 0
      ? 'rgba(72,187,120,0.1)'
      : 'rgba(252,129,129,0.1)';
    pnlChart.data.datasets[0].pointBackgroundColor = color;

    pnlChart.data.labels = labels;
    pnlChart.data.datasets[0].data = values;
    pnlChart.update('active');
  } catch (e) {
    console.error('Error cargando P&L:', e);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  initPnlChart();
  loadPnl(30);
});
