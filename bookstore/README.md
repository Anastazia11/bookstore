# Online Bookstore (Flask + MySQL)

## 1. Create the database (MySQL Workbench)
Fresh start (wipes everything):
1. Open `database/schema.sql` and click the lightning bolt  (builds the empty tables).
2. Open `database/seed.sql` and click the lightning bolt    (adds the 10 books).

Already have the database from before and only want the new payment tables (keeps your users and books):
- Open `database/upgrade_orders.sql` and click the lightning bolt. Run it once.

## 2. Run the website
1. Open `config.py` and put your MySQL root password in `DB_PASSWORD`.
2. In a terminal inside this folder:

        venv\Scripts\activate
        pip install -r requirements.txt
        python app.py

   (first time only: create the venv with `python -m venv venv` before activating it)
3. Open http://127.0.0.1:5000 in your browser.

## 3. Accounts
- Anyone can sign up (username, email, password).
- Admins see the "Manage" link. Admin = the very first account created, plus anyone who signs up with an
  email listed in `ADMIN_EMAILS` in `config.py` (the teacher, yzhang@njust.edu.cn, is already listed).

## 4. Adding books (Manage page, no files to copy by hand)
Manage -> "Add a new book": fill in the details and choose the cover image and the PDF with the file buttons.
Manage -> Edit on any book: change details or upload a new cover / PDF.
- Covers are saved in `static/covers/` (public).
- PDFs are saved in `pdfs/` (NOT public): the site only hands a PDF to someone who bought or is renting the book.

## 5. Mock payment
Cart -> Checkout -> Pay. It is a demo: nothing is charged and no card details are collected or stored.
After paying, the books appear in "My library" (profile menu) with a Download PDF button.
Buying = access forever. Renting = access for 30 days (per month) or 120 days (per semester).

## Folder guide
- `app.py`        all the Python logic (routes + SQL)
- `config.py`     database password and settings
- `templates/`    the HTML pages
- `static/css/style.css`  colours and layout (change the colours at the top)
- `static/js/ui.js`       the styled dropdowns
- `static/favicon.*`      the browser-tab icon
- `pdfs/`         uploaded PDFs (private)
- `database/`     schema.sql, seed.sql, upgrade_orders.sql

## Common errors
- "Access denied for user 'root'"  -> wrong password in config.py
- "Unknown database 'bookstore'"   -> run database/schema.sql first
- "Table 'bookstore.orders' doesn't exist" -> run database/upgrade_orders.sql
