// Gráficos del dashboard (Chart.js). Colores siempre acompañados de leyenda con texto.
(function () {
  const D = window.PERMANECE_DATOS;
  if (!D || typeof Chart === "undefined") return;

  const COLORES = { alto: "#c0392b", medio: "#e0a800", bajo: "#2e8b57", sin: "#8a94a6" };
  const NOMBRES = { alto: "Alto", medio: "Medio", bajo: "Bajo", sin: "Sin clasificar" };
  const niveles = ["alto", "medio", "bajo", "sin"];

  // La matriz llega con claves numéricas convertidas a texto por JSON
  new Chart(document.getElementById("grafGrados"), {
    type: "bar",
    data: {
      labels: D.etiquetasGrados,
      datasets: niveles.map(n => ({
        label: NOMBRES[n],
        backgroundColor: COLORES[n],
        data: D.grados.map(g => D.matriz[g][n]),
        borderRadius: 3,
      })),
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { position: "bottom" } },
    },
  });

  new Chart(document.getElementById("grafNiveles"), {
    type: "doughnut",
    data: {
      labels: niveles.map(n => NOMBRES[n]),
      datasets: [{ data: niveles.map(n => D.porNivel[n]), backgroundColor: niveles.map(n => COLORES[n]) }],
    },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" } }, cutout: "60%" },
  });
})();
