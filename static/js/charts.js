const COL = { Weak: '#ef4444', 'Needs Improvement': '#f59e0b', Strong: '#10b981' };
async function loadCharts(ids) {
  const r = await fetch('/api/performance'); if (!r.ok) return; const d = await r.json();
  const mk = (id, cfg) => { const el = document.getElementById(id); if (el && ids.includes(id)) new Chart(el, cfg); };
  const pct = { y: { min: 0, max: 100 } };
  mk('cSubjects', { type: 'bar', data: { labels: d.subjects.map(s => s.name), datasets: [{ label: '%', data: d.subjects.map(s => s.score), backgroundColor: '#2563eb' }] }, options: { scales: pct } });
  mk('cTimeline', { type: 'line', data: { labels: d.timeline.map(t => t.label), datasets: [{ label: 'Score %', data: d.timeline.map(t => t.percent), borderColor: '#2563eb', tension: .3 }] }, options: { scales: pct } });
  mk('progress', { type: 'line', data: { labels: d.timeline.map(t => t.label), datasets: [{ label: 'Score %', data: d.timeline.map(t => t.percent), borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,.15)', fill: true, tension: .3 }] }, options: { scales: pct } });
  mk('cTopics', { type: 'bar', data: { labels: d.topics.map(t => t.topic), datasets: [{ label: '%', data: d.topics.map(t => t.score), backgroundColor: d.topics.map(t => COL[t.status]) }] }, options: { indexAxis: 'y', scales: { x: { min: 0, max: 100 } } } });
  mk('cAccuracy', { type: 'doughnut', data: { labels: ['Correct', 'Incorrect'], datasets: [{ data: [d.correct, d.incorrect], backgroundColor: ['#10b981', '#ef4444'] }] } });
  mk('cProgress', { type: 'line', data: { labels: d.timeline.map(t => t.label), datasets: [{ label: 'Improvement vs first quiz (%)', data: d.progress, borderColor: '#10b981', tension: .3 }] } });
}
