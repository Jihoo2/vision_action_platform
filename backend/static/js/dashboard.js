// Django가 ORM으로 집계해 json_script 로 넘긴 값으로 Chart.js 차트를 그림 (API 호출 없음)
(() => {
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  if (typeof Chart === "undefined") {
    document.querySelectorAll("canvas").forEach((c) => c.replaceWith(Object.assign(
      document.createElement("p"), { className: "msg error", textContent: "Chart.js를 불러오지 못했습니다 (인터넷 연결 확인)." })));
    return;
  }
  const intAxis = { beginAtZero: true, ticks: { precision: 0 } };

  new Chart(document.getElementById("chart-actions"), {
    type: "bar",
    data: { labels: data.actions.labels, datasets: [{ label: "예측 건수", data: data.actions.values, backgroundColor: "#2f5bea" }] },
    options: { plugins: { legend: { display: false } }, scales: { y: intAxis } },
  });

  new Chart(document.getElementById("chart-status"), {
    type: "doughnut",
    data: { labels: data.status.labels,
            datasets: [{ data: data.status.values, backgroundColor: ["#9ca3af", "#3b82f6", "#16a34a", "#dc2626"] }] },
    options: { plugins: { legend: { position: "right" } } },
  });

  const formColors = { OK: "#16a34a", NG: "#dc2626", CHECK: "#f59e0b" };
  new Chart(document.getElementById("chart-form"), {
    type: "bar",
    data: { labels: data.form.labels,
            datasets: data.form.datasets.map((d) => ({ label: d.label, data: d.values, backgroundColor: formColors[d.label] })) },
    options: { plugins: { legend: { position: "right" } }, scales: { x: { stacked: true }, y: { ...intAxis, stacked: true } } },
  });

  new Chart(document.getElementById("chart-input"), {
    type: "bar",
    data: { labels: data.input.labels, datasets: [{ label: "작업 수", data: data.input.values, backgroundColor: ["#2f5bea", "#f59e0b"] }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: intAxis } },
  });
})();
