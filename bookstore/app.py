"""
Online Bookstore - Flask backend.

Sections of this file:
  1. Settings + database helpers
  2. Login helpers + template helpers
  3. Pages: sign up / login / logout
  4. Pages: books (list + search, split-panel book view, rate, like/dislike)
  5. Pages: cart, mock checkout, receipt, library, PDF download
  6. Pages: about / contact
  7. Pages: admin (add a book, edit a book, update price, delete a book, upload files)
"""
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # biggest upload accepted: 200 MB

COVER_DIR = os.path.join(app.static_folder, "covers")  # cover images are public
PDF_DIR = os.path.join(app.root_path, "pdfs")          # PDFs live OUTSIDE static/: only paying users get them
os.makedirs(COVER_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

# Anyone who signs up with one of these emails becomes an admin automatically
# (the very first account ever created is also an admin).
ADMIN_EMAILS = {e.strip().lower()
                for e in getattr(config, "ADMIN_EMAILS", ["yzhang@njust.edu.cn"])}

RENT_DAYS = {"month": 30, "semester": 120}   # how long a rental lasts


# =============================================================================
# 1. DATABASE HELPERS
# =============================================================================
def get_db():
    """Open one MySQL connection per request and reuse it."""
    if "db" not in g:
        import pymysql  # imported here so the file loads even before you install it

        options = dict(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,  # rows come back as dictionaries
            autocommit=True,                         # save changes immediately
        )
        if config.DB_SSL_CA:
            options["ssl_ca"] = config.DB_SSL_CA
        g.db = pymysql.connect(**options)
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """Run a SELECT. Returns a list of rows (or one row / None if one=True)."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        rows = cur.fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """Run an INSERT / UPDATE / DELETE. Returns the new row id (for INSERT)."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def now():
    return datetime.now().replace(microsecond=0)


# One SELECT that gathers everything a book card or book page needs.
BOOK_SQL = """
SELECT b.*,
       a.name AS author, g.name AS genre, p.name AS publisher,
       (SELECT ROUND(AVG(stars), 1) FROM ratings  WHERE book_id = b.id)                AS avg_rating,
       (SELECT COUNT(*)             FROM ratings  WHERE book_id = b.id)                AS rating_count,
       (SELECT COUNT(*)             FROM feedback WHERE book_id = b.id AND is_like = 1) AS likes,
       (SELECT COUNT(*)             FROM feedback WHERE book_id = b.id AND is_like = 0) AS dislikes
FROM books b
JOIN authors    a ON b.author_id    = a.id
JOIN genres     g ON b.genre_id     = g.id
JOIN publishers p ON b.publisher_id = p.id
"""


# =============================================================================
# 2. LOGIN HELPERS + TEMPLATE HELPERS
# =============================================================================
def current_user():
    """The logged-in user (a dict) or None."""
    if "user" not in g:
        g.user = None
        if session.get("user_id"):
            g.user = query(
                "SELECT id, username, email, is_admin FROM users WHERE id = %s",
                (session["user_id"],), one=True)
    return g.user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user()["is_admin"]:
            flash("Only the store admin can open that page.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_globals():
    """Variables every template can use: the user and the cart count."""
    user = current_user()
    cart_count = 0
    if user:
        row = query("SELECT COUNT(*) AS n FROM cart_items WHERE user_id = %s",
                    (user["id"],), one=True)
        cart_count = row["n"]
    return dict(user=user, cart_count=cart_count)


def asset_exists(relative_path):
    """True if static/<relative_path> exists (so we only show real cover files)."""
    if not relative_path:
        return False
    return os.path.isfile(os.path.join(app.static_folder, relative_path))


def pdf_file_for(pdf_path):
    """Full path of a book's PDF if the file really exists, else None."""
    if not pdf_path:
        return None
    full = os.path.join(PDF_DIR, os.path.basename(pdf_path))
    return full if os.path.isfile(full) else None


@app.template_filter("money")
def money(value):
    return "" if value is None else "${:,.2f}".format(value)


@app.template_filter("rent_label")
def rent_label(book):
    return "${:,.2f}/{}".format(book["rent_price"], book["rent_period"] or "month")


@app.template_filter("nice_date")
def nice_date(value):
    return value.strftime("%b %d, %Y") if value else ""


app.jinja_env.globals["asset_exists"] = asset_exists
app.jinja_env.globals["pdf_exists"] = lambda path: pdf_file_for(path) is not None


def slugify(text):
    """'My Book: Part 2' -> 'my-book-part-2' (safe to use in a file name)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "book"


# =============================================================================
# 3. SIGN UP / LOGIN / LOGOUT
# =============================================================================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not 3 <= len(username) <= 50:
            error = "Username must be 3 to 50 characters."
        elif "@" not in email or "." not in email or len(email) > 100:
            error = "Please enter a valid email address."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "The two passwords do not match."
        elif query("SELECT id FROM users WHERE username = %s OR email = %s",
                   (username, email), one=True):
            error = "That username or email is already registered."

        if error:
            flash(error, "error")
            return render_template("auth.html", tab="signup",
                                   form=dict(username=username, email=email))

        # Admin = the very first account, or an email listed in ADMIN_EMAILS.
        is_first = query("SELECT COUNT(*) AS n FROM users", one=True)["n"] == 0
        make_admin = is_first or email in ADMIN_EMAILS
        user_id = execute(
            "INSERT INTO users (username, email, password_hash, is_admin) VALUES (%s, %s, %s, %s)",
            (username, email, generate_password_hash(password), 1 if make_admin else 0))
        session.clear()
        session["user_id"] = user_id
        flash("Welcome, %s! Your account is ready." % username, "ok")
        return redirect(url_for("home"))

    return render_template("auth.html", tab="signup", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        who = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = query("SELECT * FROM users WHERE username = %s OR email = %s",
                    (who, who.lower()), one=True)
        if row and check_password_hash(row["password_hash"], password):
            if row["email"].lower() in ADMIN_EMAILS and not row["is_admin"]:
                execute("UPDATE users SET is_admin = 1 WHERE id = %s", (row["id"],))
            session.clear()
            session["user_id"] = row["id"]
            return redirect(url_for("home"))
        flash("Wrong username or password.", "error")
        return render_template("auth.html", tab="login", form=dict(username=who))

    if current_user():
        return redirect(url_for("home"))
    return render_template("auth.html", tab="login", form={})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =============================================================================
# 4. BOOKS
# =============================================================================
@app.route("/")
@login_required
def home():
    """LOOKUP 1: all books.  LOOKUP 2: by title/author text.
    LOOKUP 3: by genre / author / publisher (dropdowns)."""
    text = request.args.get("q", "").strip()
    genre_id = request.args.get("genre", "")
    author_id = request.args.get("author", "")
    publisher_id = request.args.get("publisher", "")

    where, args = [], []
    if text:
        where.append("(b.title LIKE %s OR a.name LIKE %s)")
        args += ["%" + text + "%", "%" + text + "%"]
    if genre_id.isdigit():
        where.append("b.genre_id = %s")
        args.append(int(genre_id))
    if author_id.isdigit():
        where.append("b.author_id = %s")
        args.append(int(author_id))
    if publisher_id.isdigit():
        where.append("b.publisher_id = %s")
        args.append(int(publisher_id))

    sql = BOOK_SQL
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY b.title"

    return render_template(
        "home.html", active="books",
        books=query(sql, args),
        genres=query("SELECT * FROM genres ORDER BY name"),
        authors=query("SELECT * FROM authors ORDER BY name"),
        publishers=query("SELECT * FROM publishers ORDER BY name"),
        filters=dict(q=text, genre=genre_id, author=author_id, publisher=publisher_id),
        filtered=bool(where))


def get_access(user_id, book_id):
    """Has this user paid for the book? Returns the best order line (or None).
    A purchase lasts forever; a rental only until its expiry date."""
    return query(
        """SELECT oi.mode, oi.expires_at
           FROM order_items oi JOIN orders o ON oi.order_id = o.id
           WHERE o.user_id = %s AND oi.book_id = %s
             AND (oi.mode = 'buy' OR oi.expires_at > %s)
           ORDER BY CASE WHEN oi.mode = 'buy' THEN 0 ELSE 1 END, oi.expires_at DESC""",
        (user_id, book_id, now()), one=True)


@app.route("/book/<int:book_id>")
@login_required
def book_detail(book_id):
    """The split view: left = this book, right = other books."""
    user = current_user()
    book = query(BOOK_SQL + " WHERE b.id = %s", (book_id,), one=True)
    if book is None:
        abort(404)

    same_genre = query(BOOK_SQL + " WHERE b.genre_id = %s AND b.id <> %s ORDER BY b.title",
                       (book["genre_id"], book_id))
    others = query(BOOK_SQL + " WHERE b.id <> %s ORDER BY b.title", (book_id,))

    mine = query("SELECT stars FROM ratings WHERE user_id = %s AND book_id = %s",
                 (user["id"], book_id), one=True)
    vote = query("SELECT is_like FROM feedback WHERE user_id = %s AND book_id = %s",
                 (user["id"], book_id), one=True)
    in_cart = query("SELECT mode FROM cart_items WHERE user_id = %s AND book_id = %s",
                    (user["id"], book_id), one=True)

    return render_template(
        "book.html", active="books", book=book, same_genre=same_genre, others=others,
        my_stars=mine["stars"] if mine else 0,
        my_vote=None if vote is None else ("like" if vote["is_like"] else "dislike"),
        in_cart=in_cart, access=get_access(user["id"], book_id),
        has_pdf=pdf_file_for(book["pdf_path"]) is not None)


@app.route("/book/<int:book_id>/rate", methods=["POST"])
@login_required
def rate_book(book_id):
    stars = request.form.get("stars", "")
    if stars not in ("1", "2", "3", "4", "5"):
        abort(400)
    uid = current_user()["id"]
    if query("SELECT id FROM ratings WHERE user_id = %s AND book_id = %s", (uid, book_id), one=True):
        execute("UPDATE ratings SET stars = %s WHERE user_id = %s AND book_id = %s",
                (int(stars), uid, book_id))
    else:
        execute("INSERT INTO ratings (user_id, book_id, stars) VALUES (%s, %s, %s)",
                (uid, book_id, int(stars)))
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/book/<int:book_id>/feedback", methods=["POST"])
@login_required
def feedback(book_id):
    """Like / dislike. Clicking the same button again removes your vote."""
    vote = request.form.get("vote")
    if vote not in ("like", "dislike"):
        abort(400)
    is_like = 1 if vote == "like" else 0
    uid = current_user()["id"]
    row = query("SELECT id, is_like FROM feedback WHERE user_id = %s AND book_id = %s",
                (uid, book_id), one=True)
    if row is None:
        execute("INSERT INTO feedback (user_id, book_id, is_like) VALUES (%s, %s, %s)",
                (uid, book_id, is_like))
    elif int(row["is_like"]) == is_like:
        execute("DELETE FROM feedback WHERE id = %s", (row["id"],))
    else:
        execute("UPDATE feedback SET is_like = %s WHERE id = %s", (is_like, row["id"]))
    return redirect(url_for("book_detail", book_id=book_id))


# =============================================================================
# 5. CART, MOCK CHECKOUT, RECEIPT, LIBRARY, DOWNLOAD
# =============================================================================
def cart_items(user_id):
    return query(
        """SELECT c.id AS item_id, c.mode, b.id AS book_id, b.title, b.image_url,
                  b.price, b.rent_price, b.rent_period, a.name AS author
           FROM cart_items c
           JOIN books b   ON c.book_id = b.id
           JOIN authors a ON b.author_id = a.id
           WHERE c.user_id = %s ORDER BY c.id""", (user_id,))


def line_price(item):
    """Price of one cart line: the buy price or the rent price."""
    return item["price"] if item["mode"] == "buy" else item["rent_price"]


@app.route("/cart")
@login_required
def cart():
    items = cart_items(current_user()["id"])
    total = sum((line_price(i) or Decimal("0") for i in items), Decimal("0"))
    return render_template("cart.html", active="cart", items=items, total=total)


@app.route("/cart/add", methods=["POST"])
@login_required
def cart_add():
    try:
        book_id = int(request.form.get("book_id", ""))
    except ValueError:
        abort(400)
    mode = request.form.get("mode")
    book = query("SELECT id, price, rent_price FROM books WHERE id = %s", (book_id,), one=True)
    if book is None or mode not in ("buy", "rent"):
        abort(400)
    if (mode == "buy" and book["price"] is None) or (mode == "rent" and book["rent_price"] is None):
        flash("That option is not available for this book.", "error")
        return redirect(url_for("book_detail", book_id=book_id))

    uid = current_user()["id"]
    owned = get_access(uid, book_id)
    if owned and owned["mode"] == "buy":
        flash("You already own this book. Find it in My library.", "ok")
        return redirect(url_for("book_detail", book_id=book_id))

    if query("SELECT id FROM cart_items WHERE user_id = %s AND book_id = %s", (uid, book_id), one=True):
        execute("UPDATE cart_items SET mode = %s WHERE user_id = %s AND book_id = %s",
                (mode, uid, book_id))
    else:
        execute("INSERT INTO cart_items (user_id, book_id, mode) VALUES (%s, %s, %s)",
                (uid, book_id, mode))
    flash("Added to your cart (%s)." % ("buy" if mode == "buy" else "rent"), "ok")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def cart_remove(item_id):
    execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s",
            (item_id, current_user()["id"]))
    return redirect(url_for("cart"))


@app.route("/checkout")
@login_required
def checkout():
    """Step 1: order summary + the (fake) payment form."""
    items = cart_items(current_user()["id"])
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))
    total = sum((line_price(i) or Decimal("0") for i in items), Decimal("0"))
    return render_template("checkout.html", active="cart", items=items, total=total)


@app.route("/checkout/pay", methods=["POST"])
@login_required
def pay():
    """Step 2: MOCK payment. No card data is read, sent or stored anywhere.
    It records an order, empties the cart and unlocks the downloads."""
    uid = current_user()["id"]
    items = [i for i in cart_items(uid) if line_price(i) is not None]
    if not items:
        flash("Nothing to pay for.", "error")
        return redirect(url_for("cart"))
    total = sum((line_price(i) for i in items), Decimal("0"))
    paid_at = now()

    db = get_db()
    db.begin()                       # all-or-nothing: either the whole order is saved or none of it
    try:
        order_id = execute(
            "INSERT INTO orders (user_id, total, status, created_at) VALUES (%s, %s, 'paid', %s)",
            (uid, total, paid_at))
        for i in items:
            is_rent = i["mode"] == "rent"
            period = (i["rent_period"] or "month") if is_rent else None
            expires = paid_at + timedelta(days=RENT_DAYS[period]) if is_rent else None
            execute(
                """INSERT INTO order_items (order_id, book_id, title, mode, price, rent_period, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (order_id, i["book_id"], i["title"], i["mode"], line_price(i), period, expires))
        execute("DELETE FROM cart_items WHERE user_id = %s", (uid,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("receipt", order_id=order_id))


def mark_access(rows):
    """Add 'active' (still usable?) and 'can_download' to order lines."""
    moment = now()
    for r in rows:
        r["active"] = r["mode"] == "buy" or (r["expires_at"] is not None and r["expires_at"] > moment)
        r["can_download"] = bool(r["active"] and r["book_id"] and pdf_file_for(r["pdf_path"]))
    return rows


ORDER_LINES_SQL = """
SELECT oi.*, o.created_at AS ordered_at, b.image_url, b.pdf_path, a.name AS author
FROM order_items oi
JOIN orders o        ON oi.order_id = o.id
LEFT JOIN books b    ON oi.book_id = b.id
LEFT JOIN authors a  ON b.author_id = a.id
"""


@app.route("/order/<int:order_id>")
@login_required
def receipt(order_id):
    order = query("SELECT * FROM orders WHERE id = %s AND user_id = %s",
                  (order_id, current_user()["id"]), one=True)
    if order is None:
        abort(404)
    lines = mark_access(query(ORDER_LINES_SQL + " WHERE oi.order_id = %s ORDER BY oi.id", (order_id,)))
    return render_template("receipt.html", active="library", order=order, lines=lines)


@app.route("/library")
@login_required
def library():
    uid = current_user()["id"]
    lines = mark_access(query(ORDER_LINES_SQL + " WHERE o.user_id = %s ORDER BY oi.id DESC", (uid,)))
    orders = query(
        """SELECT o.*, (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) AS n
           FROM orders o WHERE o.user_id = %s ORDER BY o.id DESC""", (uid,))
    return render_template("library.html", active="library", lines=lines, orders=orders)


@app.route("/book/<int:book_id>/download")
@login_required
def download(book_id):
    """Send the PDF, but only to someone who bought it or is renting it right now."""
    book = query("SELECT id, title, pdf_path FROM books WHERE id = %s", (book_id,), one=True)
    if book is None:
        abort(404)
    if get_access(current_user()["id"], book_id) is None:
        flash("Buy or rent this book to download it.", "error")
        return redirect(url_for("book_detail", book_id=book_id))
    if pdf_file_for(book["pdf_path"]) is None:
        flash("The PDF for this book has not been uploaded yet.", "error")
        return redirect(url_for("book_detail", book_id=book_id))
    return send_from_directory(PDF_DIR, os.path.basename(book["pdf_path"]),
                               as_attachment=True, download_name=slugify(book["title"]) + ".pdf")


# =============================================================================
# 6. ABOUT / CONTACT
# =============================================================================
@app.route("/about")
@login_required
def about():
    return render_template("about.html", active="about")


@app.route("/contact")
@login_required
def contact():
    return render_template("contact.html", active="contact")


# =============================================================================
# 7. ADMIN: UPDATE FUNCTIONS (add a book, edit a book, update a price, delete a book)
# =============================================================================
def to_money(text, required=False):
    """'12.5' -> Decimal('12.50'); '' -> None. Raises ValueError for bad input."""
    text = (text or "").strip().replace("$", "")
    if not text:
        if required:
            raise ValueError("A buy price is required.")
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("'%s' is not a valid price." % text)
    if value < 0 or value > 99999:
        raise ValueError("A price must be between 0 and 99999.")
    return value.quantize(Decimal("0.01"))


def get_or_create(table, name):
    """Find a genre/author/publisher by name, or create it. Returns its id."""
    row = query("SELECT id FROM %s WHERE name = %%s" % table, (name,), one=True)
    if row:
        return row["id"]
    return execute("INSERT INTO %s (name) VALUES (%%s)" % table, (name,))


def read_book_form(f):
    """Read and check the add/edit form. Raises ValueError with a friendly message."""
    title = f.get("title", "").strip()[:200]
    author = f.get("author", "").strip()[:100]
    genre = f.get("genre", "").strip()[:50]
    publisher = f.get("publisher", "").strip()[:100]
    if not (title and author and genre and publisher):
        raise ValueError("Title, author, genre and publisher are required.")

    isbn = re.sub(r"[\s-]", "", f.get("isbn", ""))
    if len(isbn) > 20:
        raise ValueError("That ISBN is too long.")

    year_text = f.get("year", "").strip()
    try:
        year = int(year_text) if year_text else None
    except ValueError:
        raise ValueError("Year must be a number.")
    if year is not None and not 1000 <= year <= 2100:
        raise ValueError("Year must be between 1000 and 2100.")

    price = to_money(f.get("price"), required=True)
    rent_price = to_money(f.get("rent_price"))
    period = f.get("rent_period") if f.get("rent_period") in RENT_DAYS else "month"

    return dict(title=title, author=author, genre=genre, publisher=publisher,
                isbn=isbn or None, year=year, price=price, rent_price=rent_price,
                rent_period=period if rent_price is not None else None,
                description=f.get("description", "").strip() or None)


def check_upload(file, kind):
    """Check an uploaded cover ('cover') or PDF ('pdf').
    Returns its extension, or '' if nothing was chosen. Raises ValueError if it is not acceptable."""
    if file is None or not file.filename:
        return ""
    ext = os.path.splitext(file.filename)[1].lower()
    head = file.stream.read(12)
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)

    if kind == "pdf":
        if ext != ".pdf" or not head.startswith(b"%PDF-"):
            raise ValueError("The book file must be a PDF.")
        if size > 150 * 1024 * 1024:
            raise ValueError("The PDF is larger than 150 MB.")
    else:
        looks_ok = ((ext in (".jpg", ".jpeg") and head.startswith(b"\xff\xd8\xff")) or
                    (ext == ".png" and head.startswith(b"\x89PNG")) or
                    (ext == ".webp" and head[:4] == b"RIFF" and head[8:12] == b"WEBP"))
        if not looks_ok:
            raise ValueError("The cover must be a JPG, PNG or WEBP image.")
        if size > 8 * 1024 * 1024:
            raise ValueError("The cover image is larger than 8 MB.")
    return ext


def store_upload(file, folder, title, ext):
    """Save the upload with a safe, unique name. Returns just the file name."""
    name = "%s-%s%s" % (slugify(title), uuid.uuid4().hex[:6], ext)
    file.save(os.path.join(folder, name))
    return name


@app.route("/admin")
@admin_required
def admin():
    return render_template(
        "admin.html", active="admin",
        books=query(BOOK_SQL + " ORDER BY b.title"),
        genres=query("SELECT * FROM genres ORDER BY name"),
        authors=query("SELECT * FROM authors ORDER BY name"),
        publishers=query("SELECT * FROM publishers ORDER BY name"))


@app.route("/admin/add", methods=["POST"])
@admin_required
def admin_add():
    """UPDATE 1: add a new book (with its cover image and PDF, if you choose them)."""
    try:
        data = read_book_form(request.form)
        if data["isbn"] and query("SELECT id FROM books WHERE isbn = %s", (data["isbn"],), one=True):
            raise ValueError("A book with that ISBN already exists.")
        cover_ext = check_upload(request.files.get("cover_file"), "cover")
        pdf_ext = check_upload(request.files.get("pdf_file"), "pdf")
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin"))

    cover = "covers/" + store_upload(request.files["cover_file"], COVER_DIR, data["title"], cover_ext) if cover_ext else None
    pdf = "pdfs/" + store_upload(request.files["pdf_file"], PDF_DIR, data["title"], pdf_ext) if pdf_ext else None

    execute(
        """INSERT INTO books (title, image_url, pdf_path, isbn, publication_year, price,
                              rent_price, rent_period, description, genre_id, author_id, publisher_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (data["title"], cover, pdf, data["isbn"], data["year"], data["price"],
         data["rent_price"], data["rent_period"], data["description"],
         get_or_create("genres", data["genre"]),
         get_or_create("authors", data["author"]),
         get_or_create("publishers", data["publisher"])))
    flash("Added \"%s\"." % data["title"], "ok")
    return redirect(url_for("admin"))


@app.route("/admin/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit(book_id):
    """Change any detail of a book, or upload a new cover / PDF for it."""
    book = query(BOOK_SQL + " WHERE b.id = %s", (book_id,), one=True)
    if book is None:
        abort(404)

    if request.method == "POST":
        try:
            data = read_book_form(request.form)
            if data["isbn"] and query("SELECT id FROM books WHERE isbn = %s AND id <> %s",
                                      (data["isbn"], book_id), one=True):
                raise ValueError("Another book already has that ISBN.")
            cover_ext = check_upload(request.files.get("cover_file"), "cover")
            pdf_ext = check_upload(request.files.get("pdf_file"), "pdf")
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_edit", book_id=book_id))

        cover, pdf = book["image_url"], book["pdf_path"]     # keep the old files unless a new one is chosen
        if cover_ext:
            cover = "covers/" + store_upload(request.files["cover_file"], COVER_DIR, data["title"], cover_ext)
        if pdf_ext:
            pdf = "pdfs/" + store_upload(request.files["pdf_file"], PDF_DIR, data["title"], pdf_ext)

        execute(
            """UPDATE books SET title = %s, image_url = %s, pdf_path = %s, isbn = %s,
                      publication_year = %s, price = %s, rent_price = %s, rent_period = %s,
                      description = %s, genre_id = %s, author_id = %s, publisher_id = %s
               WHERE id = %s""",
            (data["title"], cover, pdf, data["isbn"], data["year"], data["price"],
             data["rent_price"], data["rent_period"], data["description"],
             get_or_create("genres", data["genre"]),
             get_or_create("authors", data["author"]),
             get_or_create("publishers", data["publisher"]), book_id))
        flash("Saved \"%s\"." % data["title"], "ok")
        return redirect(url_for("admin"))

    return render_template(
        "admin_edit.html", active="admin", book=book,
        genres=query("SELECT * FROM genres ORDER BY name"),
        authors=query("SELECT * FROM authors ORDER BY name"),
        publishers=query("SELECT * FROM publishers ORDER BY name"))


@app.route("/admin/<int:book_id>/price", methods=["POST"])
@admin_required
def admin_price(book_id):
    """UPDATE 2: change the buy / rent price of a book."""
    try:
        price = to_money(request.form.get("price"), required=True)
        rent_price = to_money(request.form.get("rent_price"))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin"))
    period = request.form.get("rent_period") if rent_price is not None else None
    execute("UPDATE books SET price = %s, rent_price = %s, rent_period = %s WHERE id = %s",
            (price, rent_price, period if period in RENT_DAYS else None, book_id))
    flash("Price updated.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/<int:book_id>/delete", methods=["POST"])
@admin_required
def admin_delete(book_id):
    """UPDATE 3: delete a book (its ratings, likes and cart entries go with it;
    past orders keep the title). The files stay on disk."""
    execute("DELETE FROM books WHERE id = %s", (book_id,))
    flash("Book deleted.", "ok")
    return redirect(url_for("admin"))


# =============================================================================
# EXTRAS
# =============================================================================
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico")


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def too_large(_e):
    flash("That upload is too large (limit 200 MB).", "error")
    return redirect(request.referrer or url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
