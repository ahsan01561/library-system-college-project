"""Library Management System - Flask + SQLite (MCA final year project)."""
import os
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

_generate = generate_password_hash


def generate_password_hash(password):
    return _generate(password, method="pbkdf2:sha256")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "library.db")

# Business rules (from the PRD)
LOAN_DAYS = 14
MAX_BOOKS = 3
FINE_PER_DAY = 2

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")


# ---------- Database helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Create tables and add demo data on the first run."""
    conn = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE_DIR, "schema.sql")) as f:
        conn.executescript(f.read())
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
                     ("Head Librarian", "admin@library.com", generate_password_hash("admin123"), "librarian"))
        cur = conn.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
                           ("Rahul Sharma", "student@library.com", generate_password_hash("student123"), "student"))
        conn.execute("INSERT INTO members (user_id, member_code, phone) VALUES (?,?,?)",
                     (cur.lastrowid, "M1001", "9876543210"))
        books = [
            ("Clean Code", "Robert C. Martin", "9780132350884", "Programming", 5),
            ("Database System Concepts", "Silberschatz, Korth", "9780073523323", "Databases", 2),
            ("Operating System Concepts", "Silberschatz", "9781119800361", "Systems", 3),
            ("Learning Python", "Mark Lutz", "9781449355739", "Programming", 4),
        ]
        conn.executemany("INSERT INTO books (title, author, isbn, category, total_copies, available_copies) "
                         "VALUES (?,?,?,?,?,?)", [b + (b[4],) for b in books])
    conn.commit()
    conn.close()


def calc_fine(due_date_str, returned_on=None):
    """fine = late days x FINE_PER_DAY (never negative)."""
    returned_on = returned_on or date.today()
    late_days = (returned_on - date.fromisoformat(due_date_str)).days
    return max(0, late_days) * FINE_PER_DAY


def add_fines(rows):
    """Turn loan rows into dicts and add a live fine for books still issued."""
    result = []
    for r in rows:
        d = dict(r)
        if d["status"] == "issued":
            d["fine"] = calc_fine(d["due_date"])
        result.append(d)
    return result


# ---------- Login / roles ----------
def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have permission to open that page.", "error")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard" if session["role"] == "librarian" else "my_books"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("home"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------
@app.route("/dashboard")
@login_required("librarian")
def dashboard():
    c = db()
    stats = {
        "books": c.execute("SELECT COALESCE(SUM(total_copies),0) FROM books").fetchone()[0],
        "members": c.execute("SELECT COUNT(*) FROM members").fetchone()[0],
        "issued": c.execute("SELECT COUNT(*) FROM loans WHERE status='issued'").fetchone()[0],
        "overdue": c.execute("SELECT COUNT(*) FROM loans WHERE status='issued' AND due_date < ?",
                             (date.today().isoformat(),)).fetchone()[0],
    }
    recent = c.execute(
        """SELECT l.*, b.title, u.name AS member_name FROM loans l
           JOIN books b ON b.id = l.book_id
           JOIN members m ON m.id = l.member_id
           JOIN users u ON u.id = m.user_id
           ORDER BY l.id DESC LIMIT 8""").fetchall()
    return render_template("dashboard.html", stats=stats, recent=add_fines(recent),
                           today=date.today().isoformat())


# ---------- Books ----------
@app.route("/books")
@login_required()
def books():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = db().execute(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? ORDER BY title",
        (like, like, like)).fetchall()
    return render_template("books.html", books=rows, q=q)


@app.route("/books/add", methods=["GET", "POST"])
@login_required("librarian")
def add_book():
    if request.method == "POST":
        f = request.form
        try:
            copies = int(f["total_copies"])
            if copies < 1:
                raise ValueError
            db().execute(
                "INSERT INTO books (title, author, isbn, category, total_copies, available_copies) VALUES (?,?,?,?,?,?)",
                (f["title"].strip(), f["author"].strip(), f["isbn"].strip(), f["category"].strip(), copies, copies))
            db().commit()
            flash("Book added.", "success")
            return redirect(url_for("books"))
        except ValueError:
            flash("Total copies must be a number of 1 or more.", "error")
        except sqlite3.IntegrityError:
            flash("A book with this ISBN already exists.", "error")
    return render_template("book_form.html", book=None)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required("librarian")
def edit_book(book_id):
    book = db().execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if book is None:
        flash("Book not found.", "error")
        return redirect(url_for("books"))
    if request.method == "POST":
        f = request.form
        try:
            new_total = int(f["total_copies"])
            on_loan = book["total_copies"] - book["available_copies"]
            if new_total < max(on_loan, 1):
                flash(f"Total copies cannot be less than {max(on_loan, 1)} (copies currently on loan).", "error")
                return render_template("book_form.html", book=book)
            db().execute(
                "UPDATE books SET title=?, author=?, isbn=?, category=?, total_copies=?, available_copies=? WHERE id=?",
                (f["title"].strip(), f["author"].strip(), f["isbn"].strip(), f["category"].strip(),
                 new_total, new_total - on_loan, book_id))
            db().commit()
            flash("Book updated.", "success")
            return redirect(url_for("books"))
        except ValueError:
            flash("Total copies must be a number.", "error")
        except sqlite3.IntegrityError:
            flash("A book with this ISBN already exists.", "error")
    return render_template("book_form.html", book=book)


@app.route("/books/<int:book_id>/delete", methods=["POST"])
@login_required("librarian")
def delete_book(book_id):
    active = db().execute("SELECT COUNT(*) FROM loans WHERE book_id=? AND status='issued'", (book_id,)).fetchone()[0]
    if active:
        flash("Cannot delete: this book is currently issued.", "error")
    else:
        db().execute("DELETE FROM loans WHERE book_id=?", (book_id,))
        db().execute("DELETE FROM books WHERE id=?", (book_id,))
        db().commit()
        flash("Book deleted.", "success")
    return redirect(url_for("books"))


# ---------- Members ----------
@app.route("/members", methods=["GET", "POST"])
@login_required("librarian")
def members():
    if request.method == "POST":
        f = request.form
        try:
            cur = db().execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,'student')",
                               (f["name"].strip(), f["email"].strip().lower(),
                                generate_password_hash(f["password"] or "student123")))
            code = f"M{1000 + cur.lastrowid}"
            db().execute("INSERT INTO members (user_id, member_code, phone) VALUES (?,?,?)",
                         (cur.lastrowid, code, f["phone"].strip()))
            db().commit()
            flash(f"Member added with ID {code}.", "success")
        except sqlite3.IntegrityError:
            db().rollback()
            flash("A user with this email already exists.", "error")
        return redirect(url_for("members"))
    rows = db().execute(
        """SELECT m.member_code, m.phone, u.name, u.email,
           (SELECT COUNT(*) FROM loans l WHERE l.member_id = m.id AND l.status='issued') AS active_loans
           FROM members m JOIN users u ON u.id = m.user_id ORDER BY m.id""").fetchall()
    return render_template("members.html", members=rows, max_books=MAX_BOOKS)


# ---------- Issue / Return ----------
def active_loans():
    return add_fines(db().execute(
        """SELECT l.*, b.title, b.isbn, m.member_code, u.name AS member_name FROM loans l
           JOIN books b ON b.id = l.book_id
           JOIN members m ON m.id = l.member_id
           JOIN users u ON u.id = m.user_id
           WHERE l.status = 'issued' ORDER BY l.due_date""").fetchall())


@app.route("/transactions")
@login_required("librarian")
def transactions():
    return render_template("transactions.html", loans=active_loans(), today=date.today().isoformat(),
                           loan_days=LOAN_DAYS, fine_per_day=FINE_PER_DAY)


@app.route("/issue", methods=["POST"])
@login_required("librarian")
def issue():
    code = request.form["member_code"].strip().upper()
    isbn = request.form["isbn"].strip()
    c = db()
    member = c.execute("SELECT * FROM members WHERE member_code = ?", (code,)).fetchone()
    book = c.execute("SELECT * FROM books WHERE isbn = ?", (isbn,)).fetchone()
    if member is None:
        flash("Member ID not found.", "error")
    elif book is None:
        flash("Book with this ISBN not found.", "error")
    elif book["available_copies"] < 1:
        flash("No copies of this book are available.", "error")
    elif c.execute("SELECT COUNT(*) FROM loans WHERE member_id=? AND status='issued'",
                   (member["id"],)).fetchone()[0] >= MAX_BOOKS:
        flash(f"This member already has {MAX_BOOKS} books issued.", "error")
    elif c.execute("SELECT 1 FROM loans WHERE member_id=? AND book_id=? AND status='issued'",
                   (member["id"], book["id"])).fetchone():
        flash("This member already has this book.", "error")
    else:
        today = date.today()
        due = today + timedelta(days=LOAN_DAYS)
        c.execute("INSERT INTO loans (book_id, member_id, issue_date, due_date) VALUES (?,?,?,?)",
                  (book["id"], member["id"], today.isoformat(), due.isoformat()))
        c.execute("UPDATE books SET available_copies = available_copies - 1 WHERE id = ?", (book["id"],))
        c.commit()
        flash(f"Issued '{book['title']}'. Due on {due.strftime('%d %b %Y')}.", "success")
    return redirect(url_for("transactions"))


@app.route("/return/<int:loan_id>", methods=["POST"])
@login_required("librarian")
def return_book(loan_id):
    c = db()
    loan = c.execute("SELECT * FROM loans WHERE id = ? AND status = 'issued'", (loan_id,)).fetchone()
    if loan is None:
        flash("Loan not found or already returned.", "error")
    else:
        fine = calc_fine(loan["due_date"])
        c.execute("UPDATE loans SET return_date=?, fine=?, status='returned' WHERE id=?",
                  (date.today().isoformat(), fine, loan_id))
        c.execute("UPDATE books SET available_copies = available_copies + 1 WHERE id = ?", (loan["book_id"],))
        c.commit()
        flash(f"Book returned. Fine: Rs {fine}.", "success" if fine == 0 else "warning")
    return redirect(url_for("transactions"))


# ---------- Student view ----------
@app.route("/my-books")
@login_required("student")
def my_books():
    rows = db().execute(
        """SELECT l.*, b.title, b.author FROM loans l
           JOIN books b ON b.id = l.book_id
           JOIN members m ON m.id = l.member_id
           WHERE m.user_id = ? ORDER BY l.status, l.due_date""", (session["user_id"],)).fetchall()
    loans = add_fines(rows)
    return render_template("my_books.html", loans=loans, today=date.today().isoformat(),
                           total_fine=sum(l["fine"] for l in loans))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
