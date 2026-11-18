# Personalized Learning and Adaptive Quiz Platform

Flask + SQLite + SQLAlchemy + Pandas/NumPy + Chart.js.

## Run in VS Code (Windows)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python seed_data.py
python app.py
```
Open http://127.0.0.1:5000 — demo login: **demo@student.com / demo123** (5 sample quizzes included).
The database also initialises automatically on first `python app.py`.

## How it works
- **Adaptive difficulty** (`adaptive()` in app.py): last 3 quiz scores (for that subject/topic) are weighted 20/30/50%; ±5 points if the trend is improving/declining (≥10 pt change). Score → <40 Easy, 40–60 Easy/Medium, 60–75 Medium, 75–90 Medium/Hard, >90 Hard.
- **Weak-topic detection** (`status()`): topic score <50 Weak, <75 Needs Improvement, else Strong.
- **Recommendations / learning path**: priority = 100 − topic score (unattempted topics = 50); sorted highest first; actions and resources depend on the score band.
- **Questions**: add more rows to `data/questions.csv` (and delete `database.db`, rerun `python seed_data.py`). Resources live in `data/resources.csv` and the `resources` table.
