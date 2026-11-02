CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('librarian', 'student'))
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    isbn TEXT NOT NULL UNIQUE,
    category TEXT,
    total_copies INTEGER NOT NULL CHECK (total_copies >= 0),
    available_copies INTEGER NOT NULL CHECK (available_copies >= 0)
);
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    member_code TEXT NOT NULL UNIQUE,
    phone TEXT
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    return_date TEXT,
    fine INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'returned'))
);
