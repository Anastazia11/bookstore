"""
Settings you may need to change.

Running on your own computer: only change DB_PASSWORD (the MySQL root
password you chose when installing MySQL).

When you deploy online later, the host gives you these values and you put them
in "environment variables" instead of editing this file.
"""
import os

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")   # <-- change this
DB_NAME = os.environ.get("DB_NAME", "bookstore")
DB_SSL_CA = os.environ.get("DB_SSL_CA")  # only needed for some cloud databases

# Any long random text. It protects the login cookies.
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-to-any-long-random-text")
