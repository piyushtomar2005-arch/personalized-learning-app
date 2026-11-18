import os
BASE = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.environ.get("DATABASE_PATH", os.path.join(BASE, "database.db"))
SQLALCHEMY_TRACK_MODIFICATIONS = False
