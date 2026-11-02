# Library Management System

Flask + SQLite web app (MCA final year project).

## Run

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

The database (`library.db`) and demo data are created automatically on the first run.

| Role | Email | Password |
|---|---|---|
| Librarian | admin@library.com | admin123 |
| Student | student@library.com | student123 |

## Features
Login with two roles, add/edit/delete/search books, add/view members, issue books (14-day due date, max 3 per member), return books with automatic fine (Rs 2 per late day), dashboard, and a student "My Books" page.

## Structure
```
app.py          routes and business logic
schema.sql      4 tables: users, books, members, loans
templates/      HTML pages (Jinja)
static/         style.css
```

Set a real `SECRET_KEY` environment variable before deploying.
