const $ = s => document.querySelector(s);
let qs = [], t0 = 0, meta = {}, timer = null;
async function start(p) {
  try {
    const r = await fetch('/api/quiz/start?' + new URLSearchParams(p)); const d = await r.json();
    if (!r.ok) { $('#msg').innerHTML = '<div class="alert alert-warning">' + (d.error || 'Error') + '</div>'; return; }
    qs = d.questions; meta = p; t0 = Date.now();
    $('#setup').classList.add('d-none'); $('#test').classList.remove('d-none'); $('#msg').innerHTML = '';
    $('#info').textContent = qs.length + ' questions · difficulty: ' + d.difficulty; meta.used = d.difficulty;
    $('#qs').innerHTML = qs.map((q, i) => `<div class="card p-3 mb-3"><div class="small text-muted">${q.subject} · ${q.topic} · ${q.difficulty}</div>
      <div class="fw-semibold my-2">${i + 1}. ${q.question}</div>` + ['A', 'B', 'C', 'D'].map(k =>
      `<label class="opt"><input type="radio" name="q${q.id}" value="${k}"> ${k}. ${q.options[k]}</label>`).join('') + '</div>').join('');
    timer = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); $('#timer').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }, 1000);
  } catch (e) { $('#msg').innerHTML = '<div class="alert alert-danger">Could not reach the server.</div>'; }
}
$('#sf').addEventListener('submit', e => { e.preventDefault(); start(Object.fromEntries(new FormData(e.target))); });
$('#submit').addEventListener('click', async () => {
  const answers = {}; qs.forEach(q => { const c = document.querySelector(`input[name=q${q.id}]:checked`); if (c) answers[q.id] = c.value; });
  const left = qs.length - Object.keys(answers).length;
  if (left && !confirm(left + ' question(s) unanswered. Submit anyway?')) return;
  clearInterval(timer);
  const r = await fetch('/api/quiz/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_ids: qs.map(q => q.id), answers, subject: meta.subject, difficulty: meta.used, seconds: Math.floor((Date.now() - t0) / 1000) }) });
  const d = await r.json();
  if (r.ok) location.href = d.redirect; else $('#msg').innerHTML = '<div class="alert alert-danger">' + d.error + '</div>';
});
const url = new URLSearchParams(location.search);
if (url.get('auto')) { const p = { subject: url.get('subject') || 'mixed', n: url.get('n') || 10, difficulty: url.get('difficulty') || 'adaptive' }; if (url.get('topic')) p.topic = url.get('topic'); start(p); }
