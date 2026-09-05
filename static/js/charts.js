/**
 * RetailIQ Charting Utilities (Chart.js wrapper)
 * Dark SaaS theme optimized charts for Revenue, Trends, Store Comparison, and Categories.
 */

window.RetailCharts = {
  instances: {},

  destroyChart(id) {
    if (this.instances[id]) {
      this.instances[id].destroy();
      delete this.instances[id];
    }
  },

  renderRevenueTrendChart(canvasId, trendData) {
    this.destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || !window.Chart) return;

    const labels = trendData.map(d => {
      const parts = d.date.split("-");
      return `${parts[1]}/${parts[2]}`;
    });
    const revenues = trendData.map(d => d.revenue);
    const units = trendData.map(d => d.units);

    this.instances[canvasId] = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Daily Revenue (₹)",
            data: revenues,
            borderColor: "#6366f1",
            backgroundColor: "rgba(99, 102, 241, 0.15)",
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: 2,
            pointHoverRadius: 6,
            yAxisID: "y"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            backgroundColor: "#161c2e",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            titleColor: "#f8fafc",
            bodyColor: "#c7d2fe",
            callbacks: {
              label: (context) => ` Revenue: ₹${context.parsed.y.toLocaleString("en-IN")}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.04)" },
            ticks: { color: "#64748b", font: { size: 11 }, maxTicksLimit: 12 }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            ticks: {
              color: "#64748b",
              font: { size: 11 },
              callback: (val) => `₹${(val / 1000).toFixed(0)}k`
            }
          }
        }
      }
    });
  },

  renderStoreComparisonChart(canvasId, storeData) {
    this.destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || !window.Chart) return;

    const labels = storeData.map(s => s.store_name);
    const revenues = storeData.map(s => s.total_revenue);

    this.instances[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "30-Day Revenue (₹)",
            data: revenues,
            backgroundColor: [
              "rgba(99, 102, 241, 0.8)",
              "rgba(59, 130, 246, 0.8)",
              "rgba(16, 185, 129, 0.8)",
              "rgba(245, 158, 11, 0.8)"
            ],
            borderRadius: 6,
            borderWidth: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#161c2e",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            callbacks: {
              label: (c) => ` Revenue: ₹${c.parsed.y.toLocaleString("en-IN")}`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#94a3b8", font: { size: 11 } }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#64748b",
              font: { size: 11 },
              callback: (val) => `₹${(val / 100000).toFixed(1)}L`
            }
          }
        }
      }
    });
  },

  renderCategoryDonutChart(canvasId, categoryData) {
    this.destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx || !window.Chart) return;

    const labels = categoryData.map(c => c.category_name);
    const revenues = categoryData.map(c => c.total_revenue);

    this.instances[canvasId] = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: revenues,
            backgroundColor: [
              "#6366f1", "#3b82f6", "#10b981", "#f59e0b",
              "#ec4899", "#8b5cf6", "#14b8a6"
            ],
            borderWidth: 2,
            borderColor: "#101522"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: {
            position: "right",
            labels: { color: "#94a3b8", boxWidth: 12, font: { size: 11 } }
          },
          tooltip: {
            backgroundColor: "#161c2e",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            callbacks: {
              label: (c) => ` ₹${c.parsed.toLocaleString("en-IN")}`
            }
          }
        }
      }
    });
  }
};
