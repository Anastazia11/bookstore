USE bookstore;

CREATE TABLE IF NOT EXISTS orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'paid',
  created_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS order_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  book_id INT NULL,                  -- becomes NULL if the book is deleted later
  title VARCHAR(200) NOT NULL,       -- copy of the title at purchase time
  mode ENUM('buy','rent') NOT NULL,
  price DECIMAL(8,2) NOT NULL,
  rent_period ENUM('month','semester') NULL,
  expires_at DATETIME NULL,          -- only for rentals
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (book_id)  REFERENCES books(id)  ON DELETE SET NULL
);
