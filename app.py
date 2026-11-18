import random
from datetime import datetime
from functools import wraps
import numpy as np
import pandas as pd
from flask import (Flask, request, session, redirect, url_for, render_template, jsonify, flash)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config.from_object("config")
db = SQLAlchemy(app)

# ----------------------------------------------------------------- MODELS
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    college = db.Column(db.String(150)); course = db.Column(db.String(100)); year = db.Column(db.Integer)

class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False); icon = db.Column(db.String(10))

class Topic(db.Model):
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    subject = db.relationship("Subject", backref="topics")

class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    difficulty = db.Column(db.String(10), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200)); option_b = db.Column(db.String(200))
    option_c = db.Column(db.String(200)); option_d = db.Column(db.String(200))
    correct = db.Column(db.String(1), nullable=False); explanation = db.Column(db.Text)
    subject = db.relationship("Subject"); topic = db.relationship("Topic")

class Attempt(db.Model):  # quiz_attempts
    __tablename__ = "quiz_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    mode = db.Column(db.String(20)); difficulty = db.Column(db.String(30))
    total = db.Column(db.Integer, default=0); correct = db.Column(db.Integer, default=0)
    percent = db.Column(db.Float, default=0); seconds = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Answer(db.Model):  # quiz_answers
    __tablename__ = "quiz_answers"
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    chosen = db.Column(db.String(1)); is_correct = db.Column(db.Boolean, default=False)
    question = db.relationship("Question")

class StudentSubject(db.Model):
    __tablename__ = "student_subjects"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)

class Resource(db.Model):
    __tablename__ = "resources"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    title = db.Column(db.String(200)); rtype = db.Column(db.String(20))
    description = db.Column(db.Text); url = db.Column(db.String(500))
    topic = db.relationship("Topic")

# ------------------------------------------------------------ AUTH HELPERS
def uid(): return session.get("uid")

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not uid():
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first."), 401
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def do_register(d):
    name = (d.get("name") or "").strip(); email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if not name or "@" not in email or len(pw) < 6:
        return None, "Enter a name, a valid email and a password of at least 6 characters."
    if User.query.filter_by(email=email).first():
        return None, "This email is already registered."
    try: year = int(d.get("year") or 1)
    except ValueError: return None, "Year must be a number."
    u = User(name=name, email=email, password_hash=generate_password_hash(pw),
             college=(d.get("college") or "").strip(), course=(d.get("course") or "").strip(), year=year)
    db.session.add(u); db.session.flush()
    for s in Subject.query.all(): db.session.add(StudentSubject(user_id=u.id, subject_id=s.id))
    db.session.commit()
    return u, None

def do_login(d):
    u = User.query.filter_by(email=(d.get("email") or "").strip().lower()).first()
    if not u: return None, "No account found for this email."
    if not check_password_hash(u.password_hash, d.get("password") or ""): return None, "Wrong password."
    return u, None

# --------------------------------------------------- SERVICES (analysis etc.)
def selected_ids(u):
    return [s.subject_id for s in StudentSubject.query.filter_by(user_id=u).all()]

def answers_df(u):
    rows = (db.session.query(Answer.attempt_id, Answer.is_correct, Question.subject_id, Question.topic_id)
            .join(Question, Answer.question_id == Question.id)
            .join(Attempt, Answer.attempt_id == Attempt.id).filter(Attempt.user_id == u).all())
    df = pd.DataFrame(rows, columns=["attempt", "correct", "sid", "tid"])
    df["correct"] = df["correct"].astype(float)
    return df

def status(score):
    if score < 50: return "Weak"
    if score < 75: return "Needs Improvement"
    return "Strong"

POOLS = [(40, ["Easy"], "Easy"), (60, ["Easy", "Medium"], "Easy/Medium"), (75, ["Medium"], "Medium"),
         (90, ["Medium", "Hard"], "Medium/Hard"), (101, ["Hard"], "Hard")]

def adaptive(u, sid=None, tid=None):
    """Weighted recent score (+/-5 for improving/declining trend) -> difficulty pool."""
    df = answers_df(u)
    if len(df) and sid: df = df[df.sid == sid]
    if len(df) and tid: df = df[df.tid == tid]
    if not len(df): return dict(score=0, pool=["Easy"], label="Easy", trend="new", recent=[])
    s = (df.groupby("attempt").correct.mean() * 100).tolist()[-3:]
    w = np.array([0.2, 0.3, 0.5][-len(s):]); w = w / w.sum()
    base = float(np.dot(s, w)); slope = s[-1] - s[0] if len(s) > 1 else 0
    trend = "improving" if slope >= 10 else "declining" if slope <= -10 else "steady"
    score = min(100, max(0, base + (5 if trend == "improving" else -5 if trend == "declining" else 0)))
    for lim, pool, label in POOLS:
        if score < lim:
            return dict(score=round(score, 1), pool=pool, label=label, trend=trend, recent=[round(x, 1) for x in s])

def topic_stats(u):
    df = answers_df(u); res = []
    for t in Topic.query.filter(Topic.subject_id.in_(selected_ids(u))).all():
        d = df[df.tid == t.id] if len(df) else df
        n = len(d); sc = round(float(d.correct.mean() * 100), 1) if n else None
        res.append(dict(topic_id=t.id, topic=t.name, subject_id=t.subject_id, subject=t.subject.name, score=sc,
                        attempted=n, status=status(sc) if n else "Not started",
                        priority=round(100 - (sc if n else 50), 1)))
    return sorted(res, key=lambda r: -r["priority"])

def subject_stats(u):
    df = answers_df(u); out = []
    for s in Subject.query.filter(Subject.id.in_(selected_ids(u))).all():
        d = df[df.sid == s.id] if len(df) else df
        sc = round(float(d.correct.mean() * 100), 1) if len(d) else None
        out.append(dict(id=s.id, name=s.name, icon=s.icon, score=sc, attempted=len(d), level=adaptive(u, s.id)["label"]))
    return out

def overall(u):
    atts = Attempt.query.filter_by(user_id=u).order_by(Attempt.id).all()
    p = [a.percent for a in atts]; corr = sum(a.correct for a in atts); tot = sum(a.total for a in atts)
    slope = float(np.polyfit(range(len(p[-5:])), p[-5:], 1)[0]) if len(p) > 1 else 0
    return dict(quizzes=len(atts), questions=tot, correct=corr, incorrect=tot - corr,
                accuracy=round(corr / tot * 100, 1) if tot else 0,
                average=round(float(np.mean(p)), 1) if p else 0,
                improvement=round(p[-1] - p[-2], 1) if len(p) > 1 else 0, slope=round(slope, 2),
                timeline=[dict(label=f"Quiz {i+1}", percent=x) for i, x in enumerate(p)],
                progress=[round(x - p[0], 1) for x in p], level=adaptive(u)["label"])

def recs_for(score):
    if score is None or score < 40: return ["Study basic learning material", "Practice easy questions", "Watch a video explanation"]
    if score <= 70: return ["Revise core concepts", "Attempt medium questions"]
    return ["Read advanced resources", "Attempt hard questions", "Take mixed quizzes"]

def res_dict(r):
    thumb = None
    if "youtube.com/watch?v=" in (r.url or ""): thumb = f"https://img.youtube.com/vi/{r.url.split('v=')[1][:11]}/hqdefault.jpg"
    return dict(id=r.id, topic=r.topic.name, subject=r.topic.subject.name, title=r.title, type=r.rtype,
                description=r.description, url=r.url, thumb=thumb)

def resources_for(tid): return [res_dict(r) for r in Resource.query.filter_by(topic_id=tid).all()]

def recommendations(u, k=5):
    out = []
    for t in topic_stats(u)[:k]:
        ad = adaptive(u, t["subject_id"], t["topic_id"])
        out.append(dict(t, actions=recs_for(t["score"]), difficulty=ad["label"], trend=ad["trend"],
                        resources=resources_for(t["topic_id"])))
    return out

def learning_path(u):
    path = []
    for i, t in enumerate(topic_stats(u)[:12], 1):
        sc = t["score"]
        act = ("Start learning: watch intro video, then take an easy quiz" if sc is None else
               "Study fundamentals, watch a video, do 10 easy questions" if sc < 50 else
               "Revise concepts and practise medium questions" if sc < 75 else
               "Go advanced: hard questions and mixed tests")
        path.append(dict(priority=i, subject=t["subject"], topic=t["topic"], topic_id=t["topic_id"],
                         subject_id=t["subject_id"], score=sc, status=t["status"], action=act,
                         difficulty=adaptive(u, t["subject_id"], t["topic_id"])["label"]))
    return path

def pick_questions(u, sub, n, diff, tid=None):
    n = max(1, min(int(n), 50)); sel = selected_ids(u)
    if diff in ("Easy", "Medium", "Hard"): pool = [diff]; used = diff
    else:
        ad = adaptive(u, int(sub) if str(sub).isdigit() else None, tid); pool = ad["pool"]; used = ad["label"]
    q = Question.query
    if tid: q = q.filter_by(topic_id=tid)
    if str(sub).isdigit(): q = q.filter_by(subject_id=int(sub))
    else: q = q.filter(Question.subject_id.in_(sel))
    allq = q.all()
    pref = [x for x in allq if x.difficulty in pool]; rest = [x for x in allq if x.difficulty not in pool]
    random.shuffle(pref); random.shuffle(rest)
    if str(sub).isdigit() or tid: chosen = (pref + rest)[:n]
    else:  # mixed: round-robin across subjects
        by = {}
        for x in pref + rest: by.setdefault(x.subject_id, []).append(x)
        chosen = []
        while len(chosen) < n and any(by.values()):
            for k in list(by):
                if by[k] and len(chosen) < n: chosen.append(by[k].pop(0))
    random.shuffle(chosen)
    return chosen, used

def feedback(att):
    by = {}
    for a in Answer.query.filter_by(attempt_id=att.id).all():
        by.setdefault((a.question.subject.name, a.question.topic.name), []).append(a.is_correct)
    ts = {f"{s} - {t}": sum(v) / len(v) * 100 for (s, t), v in by.items()}
    strong = [k for k, v in ts.items() if v >= 75]; weak = sorted([k for k, v in ts.items() if v < 50], key=ts.get)
    p = att.percent
    msgs = ["Excellent work!" if p >= 85 else "Good attempt!" if p >= 60 else "Keep going - this is a starting point." ]
    if strong: msgs.append("You performed well in " + ", ".join(strong[:3]) + ".")
    if weak: msgs.append("Your main weakness is " + weak[0] + ".")
    prev = Attempt.query.filter(Attempt.user_id == att.user_id, Attempt.id < att.id).order_by(Attempt.id.desc()).first()
    if prev:
        d = round(p - prev.percent, 1)
        msgs.append(f"Your score {'improved' if d > 0 else 'dropped' if d < 0 else 'stayed the same'}"
                    + (f" by {abs(d)}%" if d else "") + " compared with your previous attempt.")
    msgs.append(f"Recommended action: study {weak[0].split(' - ')[1]} and attempt 10 practice questions." if weak
                else "Recommended action: try a harder difficulty or a mixed test.")
    return dict(messages=msgs, strong=strong, weak=weak, weakest=weak[0] if weak else None)

def dashboard_data(u):
    ts = topic_stats(u); weak = [t for t in ts if t["attempted"] and t["status"] != "Strong"][:3]
    rec = recommendations(u, 1)
    return dict(overall=overall(u), subjects=subject_stats(u), weak_topics=weak, recommended=rec[0] if rec else None)

def performance_data(u):
    o = overall(u)
    return dict(subjects=[dict(name=s["name"], score=s["score"] or 0) for s in subject_stats(u)],
                topics=[t for t in topic_stats(u) if t["attempted"]], timeline=o["timeline"],
                correct=o["correct"], incorrect=o["incorrect"], progress=o["progress"], overall=o)

# ------------------------------------------------------------- PAGE ROUTES
@app.route("/")
def index(): return redirect(url_for("dashboard" if uid() else "login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try: u, err = do_register(request.form)
        except SQLAlchemyError: db.session.rollback(); u, err = None, "Database error, please try again."
        if err: flash(err, "danger"); return render_template("register.html")
        session["uid"] = u.id; return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, err = do_login(request.form)
        if err: flash(err, "danger"); return render_template("login.html")
        session["uid"] = u.id; return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); flash("Logged out.", "info"); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard(): return render_template("dashboard.html", d=dashboard_data(uid()), user=db.session.get(User, uid()))

@app.route("/subjects", methods=["GET", "POST"])
@login_required
def subjects():
    if request.method == "POST":
        ids = [int(x) for x in request.form.getlist("subjects") if x.isdigit()]
        if not ids: flash("Select at least one subject.", "danger")
        else: set_subjects(uid(), ids); flash("Subjects updated.", "success")
    return render_template("subjects.html", subjects=Subject.query.all(), sel=selected_ids(uid()))

def set_subjects(u, ids):
    StudentSubject.query.filter_by(user_id=u).delete()
    for i in ids:
        if db.session.get(Subject, i): db.session.add(StudentSubject(user_id=u, subject_id=i))
    db.session.commit()

@app.route("/quiz")
@login_required
def quiz():
    return render_template("quiz.html", subjects=Subject.query.filter(Subject.id.in_(selected_ids(uid()))).all())

@app.route("/quiz/result/<int:aid>")
@login_required
def quiz_result(aid):
    a = Attempt.query.filter_by(id=aid, user_id=uid()).first()
    if not a: flash("Result not found.", "danger"); return redirect(url_for("quiz"))
    fb = feedback(a); answers = Answer.query.filter_by(attempt_id=a.id).all()
    wt = None
    if fb["weakest"]:
        sname, tname = fb["weakest"].split(" - ", 1)
        wt = Topic.query.join(Subject).filter(Subject.name == sname, Topic.name == tname).first()
    return render_template("quiz_result.html", a=a, fb=fb, answers=answers, wt=wt)

@app.route("/performance")
@login_required
def performance(): return render_template("performance.html", o=overall(uid()))

@app.route("/learning-path")
@login_required
def learning_path_page(): return render_template("learning_path.html", path=learning_path(uid()))

@app.route("/resources")
@login_required
def resources():
    tid = request.args.get("topic", type=int)
    if tid: ts = [t for t in topic_stats(uid()) if t["topic_id"] == tid] or topic_stats(uid())[:1]
    else: ts = topic_stats(uid())[:6]
    return render_template("resources.html", groups=[dict(t=t, res=resources_for(t["topic_id"])) for t in ts])

@app.route("/practice")
@login_required
def practice():
    return render_template("practice.html", recs=[dict(r, n=10) for r in recommendations(uid(), 6)])

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    u = db.session.get(User, uid())
    if request.method == "POST":
        u.name = (request.form.get("name") or u.name).strip(); u.college = request.form.get("college", "").strip()
        u.course = request.form.get("course", "").strip(); u.year = request.form.get("year", type=int) or u.year
        db.session.commit(); flash("Profile updated.", "success")
    return render_template("profile.html", u=u, o=overall(uid()))

# --------------------------------------------------------------- API ROUTES
def body(): return request.get_json(silent=True) or {}

@app.post("/api/register")
def api_register():
    u, err = do_register(body())
    if err: return jsonify(error=err), 400
    session["uid"] = u.id; return jsonify(message="Registered", name=u.name), 201

@app.post("/api/login")
def api_login():
    u, err = do_login(body())
    if err: return jsonify(error=err), 401
    session["uid"] = u.id; return jsonify(message="Logged in", name=u.name)

@app.post("/api/logout")
def api_logout(): session.clear(); return jsonify(message="Logged out")

@app.get("/api/dashboard")
@login_required
def api_dashboard(): return jsonify(dashboard_data(uid()))

@app.get("/api/subjects")
@login_required
def api_subjects():
    sel = selected_ids(uid())
    return jsonify([dict(id=s.id, name=s.name, selected=s.id in sel, topics=[t.name for t in s.topics]) for s in Subject.query.all()])

@app.post("/api/subjects/select")
@login_required
def api_select():
    ids = [i for i in body().get("subject_ids", []) if isinstance(i, int)]
    if not ids: return jsonify(error="Select at least one subject."), 400
    set_subjects(uid(), ids); return jsonify(message="Subjects updated", subject_ids=ids)

@app.get("/api/quiz/start")
@login_required
def api_start():
    sub = request.args.get("subject", "mixed"); n = request.args.get("n", 10)
    diff = request.args.get("difficulty", "adaptive").capitalize(); tid = request.args.get("topic", type=int)
    if not str(n).isdigit() or int(n) < 1: return jsonify(error="Invalid number of questions."), 400
    if sub != "mixed" and not sub.isdigit(): return jsonify(error="Invalid subject."), 400
    qs, used = pick_questions(uid(), sub, n, diff, tid)
    if not qs: return jsonify(error="No questions are available for this selection."), 404
    return jsonify(difficulty=used, questions=[dict(id=q.id, subject=q.subject.name, topic=q.topic.name,
        difficulty=q.difficulty, question=q.text, options=dict(A=q.option_a, B=q.option_b, C=q.option_c, D=q.option_d)) for q in qs])

@app.post("/api/quiz/submit")
@login_required
def api_submit():
    d = body(); ids = d.get("question_ids"); ans = d.get("answers") or {}
    if not ids or not isinstance(ids, list): return jsonify(error="Quiz is empty."), 400
    qs = Question.query.filter(Question.id.in_(ids)).all()
    if not qs: return jsonify(error="Questions not found."), 404
    sub = d.get("subject"); sid = int(sub) if str(sub).isdigit() else None
    try:
        a = Attempt(user_id=uid(), subject_id=sid, mode="subject" if sid else "mixed", difficulty=str(d.get("difficulty", "")),
                    total=len(qs), seconds=int(d.get("seconds") or 0)); db.session.add(a); db.session.flush()
        c = 0
        for q in qs:
            ch = str(ans.get(str(q.id), "")).upper()[:1]; ok = ch == q.correct; c += ok
            db.session.add(Answer(attempt_id=a.id, question_id=q.id, chosen=ch, is_correct=ok))
        a.correct = c; a.percent = round(c / len(qs) * 100, 1); db.session.commit()
    except SQLAlchemyError:
        db.session.rollback(); return jsonify(error="Could not save the quiz. Please try again."), 500
    return jsonify(attempt_id=a.id, percent=a.percent, redirect=url_for("quiz_result", aid=a.id))

@app.get("/api/performance")
@login_required
def api_perf(): return jsonify(performance_data(uid()))

@app.get("/api/performance/subjects")
@login_required
def api_perf_sub(): return jsonify(subject_stats(uid()))

@app.get("/api/performance/topics")
@login_required
def api_perf_top(): return jsonify(topic_stats(uid()))

@app.get("/api/learning-path")
@login_required
def api_path(): return jsonify(learning_path(uid()))

@app.get("/api/resources")
@login_required
def api_res():
    tid = request.args.get("topic", type=int)
    if tid:
        r = resources_for(tid)
        if not r: return jsonify(error="No resources found for this topic."), 404
        return jsonify(r)
    return jsonify([dict(topic=t["topic"], resources=resources_for(t["topic_id"])) for t in topic_stats(uid())[:6]])

@app.get("/api/practice")
@login_required
def api_practice():
    return jsonify([dict(topic=r["topic"], subject=r["subject"], topic_id=r["topic_id"], subject_id=r["subject_id"],
                         score=r["score"], questions=10, difficulty=r["difficulty"]) for r in recommendations(uid(), 6)])

@app.get("/api/recommendations")
@login_required
def api_recs(): return jsonify(recommendations(uid(), 8))

@app.errorhandler(404)
def nf(e):
    if request.path.startswith("/api/"): return jsonify(error="Not found"), 404
    return '<h3>Page not found</h3><a href="/">Go home</a>', 404

@app.errorhandler(500)
def err(e):
    db.session.rollback()
    if request.path.startswith("/api/"): return jsonify(error="Server error"), 500
    return '<h3>Something went wrong.</h3><a href="/">Go home</a>', 500

def init_db():
    with app.app_context():
        db.create_all()
        if not Subject.query.first():
            from seed_data import seed
            seed(globals())

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
