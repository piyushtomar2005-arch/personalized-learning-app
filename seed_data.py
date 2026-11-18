"""Run `python seed_data.py` to create tables and load sample data."""
import csv, os, random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def rows(f):
    with open(os.path.join(D, f), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def seed(g):
    db = g["db"]; Subject = g["Subject"]; Topic = g["Topic"]; Question = g["Question"]
    Resource = g["Resource"]; User = g["User"]; StudentSubject = g["StudentSubject"]
    Attempt = g["Attempt"]; Answer = g["Answer"]
    tmap = {}
    for r in rows("subjects.csv"):
        s = Subject(name=r["name"], icon=r["icon"]); db.session.add(s); db.session.flush()
        for t in r["topics"].split("|"):
            tp = Topic(name=t, subject_id=s.id); db.session.add(tp); db.session.flush()
            tmap[(s.name, t)] = tp
            q = (s.name + " " + t).replace(" ", "+")
            db.session.add(Resource(topic_id=tp.id, title=f"{s.name} {t} - Video Lessons", rtype="Video",
                description=f"Curated YouTube video explanations of {t} in {s.name}.",
                url="https://www.youtube.com/results?search_query=" + q + "+tutorial"))
            db.session.add(Resource(topic_id=tp.id, title=f"{t} - Study Notes", rtype="Article",
                description=f"Read an overview article about {t}.",
                url="https://en.wikipedia.org/wiki/Special:Search?search=" + q))
    for r in rows("questions.csv"):
        tp = tmap[(r["subject"], r["topic"])]
        db.session.add(Question(subject_id=tp.subject_id, topic_id=tp.id, difficulty=r["difficulty"],
            text=r["question"], option_a=r["a"], option_b=r["b"], option_c=r["c"], option_d=r["d"],
            correct=r["answer"], explanation=r["explanation"]))
    for r in rows("resources.csv"):
        tp = tmap.get((r["subject"], r["topic"]))
        if tp:
            db.session.add(Resource(topic_id=tp.id, title=r["title"], rtype=r["type"],
                description=r["description"], url=r["url"]))
    demo = User(name="Demo Student", email="demo@student.com", password_hash=generate_password_hash("demo123"),
                college="Demo College", course="B.Tech CSE", year=2)
    db.session.add(demo); db.session.flush()
    for s in Subject.query.all():
        db.session.add(StudentSubject(user_id=demo.id, subject_id=s.id))
    db.session.commit()
    # demo history: improving student, weak in a few topics
    random.seed(7)
    qs = Question.query.all(); weak = {"Normalization", "Deadlock", "Routing", "Transactions"}
    for i, p in enumerate([0.35, 0.45, 0.55, 0.65, 0.75]):
        pick = random.sample(qs, 15)
        a = Attempt(user_id=demo.id, mode="mixed", difficulty="Adaptive", total=15, correct=0, percent=0,
                    seconds=600, created_at=datetime.utcnow() - timedelta(days=(5 - i) * 2))
        db.session.add(a); db.session.flush()
        c = 0
        for q in pick:
            ok = random.random() < (p - 0.3 if q.topic.name in weak else p + 0.1)
            ch = q.correct if ok else random.choice([x for x in "ABCD" if x != q.correct])
            c += ok
            db.session.add(Answer(attempt_id=a.id, question_id=q.id, chosen=ch, is_correct=ok))
        a.correct = c; a.percent = round(c / 15 * 100, 1)
    db.session.commit()
    print("Sample data loaded. Login: demo@student.com / demo123")

if __name__ == "__main__":
    from app import init_db
    init_db()
    print("Database ready.")
