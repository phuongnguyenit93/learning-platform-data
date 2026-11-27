# Building an Order Schema with Foreign Keys, CHECK Constraints, and Sample Data

This lab belongs to the **DATABASE_MYSQL** module. The goal is to build a small order schema that still covers the relationships and data rules commonly found in e-commerce applications: customers, products, orders, and order items. We will use primary keys, unique keys, foreign keys, CHECK constraints, appropriate data types, and sample data to validate the design.

A good schema needs to enforce critical rules directly at the database layer. The application can validate data before writing, yet multiple services, background jobs, or import tasks may still write directly. PRIMARY KEY, UNIQUE, FOREIGN KEY, and CHECK allow MySQL to reject invalid data states even when an application flow misses validation.

This lab uses InnoDB and MySQL 8.0.16 or later so that CHECK constraints are enforced. If you use an older version, note that MySQL prior to 8.0.16 parses CHECK clauses without enforcing the condition. Verify the server version before relying on CHECK to protect production data.

## 1. Business Model and Scope

We will build four entities:

- **customers:** customer information.
- **products:** product catalog and current selling price.
- **orders:** order header, including customer, status, timestamp, and total amounts.
- **order_items:** individual products, quantities, unit prices at the time of ordering, and line-item discounts.

Relationships:

~~~text
customers 1 -------- N orders
                       |
                       |
                       1
                       |
                       N
                  order_items
                       N
                       |
                       1
                    products
~~~

One customer can have many orders. One order can have many order items. Each order item references one product. One product can appear in many orders.

In this model, the unit price in order_items is a **snapshot price at the time of purchase**. Do not pull the current price from products to recalculate old orders, because product prices may change after a customer has placed an order. Similarly, customer information can also be stored as a snapshot on the order if the business requires preserving the shipping address or recipient name at the time of purchase.

Lab scope:

1. Create the database and tables in the proper foreign key dependency order.
2. Choose data types, primary keys, unique keys, and indexes.
3. Declare foreign keys with intentional delete/update actions.
4. Add CHECK constraints for prices, quantities, statuses, and total amounts.
5. Insert sample data inside a transaction.
6. Query orders using JOINs and aggregations.
7. Test valid and invalid cases.
8. Inspect metadata and verify consistency.

We are not yet building full inventory, payments, shipping, taxes, refunds, or status history. Those parts can be added after the core schema is clear and solid.

## 2. Choosing Data Types and Key Rules

Before writing DDL, we need to agree on the design choices.

| Attribute | Choice | Rationale |
|---|---|---|
| Internal ID | BIGINT UNSIGNED AUTO_INCREMENT | Large range, non-negative, easy to reference |
| Email | VARCHAR(254) | Appropriate length limit for email addresses |
| SKU | VARCHAR(64) | Product codes may contain letters and separators |
| Prices and money | DECIMAL(p,2) | Avoids binary floating-point rounding errors of FLOAT/DOUBLE |
| Quantity | INT UNSIGNED | Item quantities are non-negative |
| Status | VARCHAR with CHECK | Human-readable and allows restricting allowed values |
| Timestamp | DATETIME(6) | Preserves timestamps with microsecond precision per application convention |
| Engine | InnoDB | Supports transactions, foreign keys, and row-level locking |
| Charset | utf8mb4 | Full Unicode support |

### 2.1. PRIMARY KEY

Each table has a stable primary key. Internal IDs should not depend on email, SKU, or order number because business values can change according to policy.

Columns referenced by a foreign key must have a suitable index; in this lab, the primary key of the parent table satisfies that requirement.

### 2.2. UNIQUE

We use unique keys for:

- Customer email.
- Product SKU.
- Order number.
- The pair `(order_id, product_id)` in order_items.

A unique key on the order_id/product_id pair means a product can only appear on a single line in a given order. If the business needs multiple separate lines for the same product, such as different batches or pricing tiers, drop this unique key or add a distinguishing attribute to the key.

Email in this example uses a case-insensitive collation at the database level. This can cause two emails that differ only in letter case to be treated as duplicates. Define your product's email normalization rules before applying this in a production system.

### 2.3. FOREIGN KEY

Foreign keys ensure child rows reference an existing parent row. The data types on both sides must be compatible, including size and the UNSIGNED attribute.

We choose the following behaviors:

- Do not delete a customer if they still have orders: ON DELETE RESTRICT.
- Do not delete a product already referenced by an order item: ON DELETE RESTRICT.
- When deleting an order in a demo environment, its order items are deleted along with it: ON DELETE CASCADE.

In real e-commerce systems, orders that have already triggered business workflows are usually not deleted; a cancelled status or archival is used instead. CASCADE here illustrates the ownership relationship between order and order_items. Only use it when deleting the parent genuinely means deleting the children according to business rules.

### 2.4. CHECK

CHECK validates conditions on the row being written:

- Product price is non-negative.
- Active flag accepts only 0 or 1.
- Order status belongs to the allowed set.
- Order item quantity is greater than 0.
- Discount is non-negative and does not exceed the line total before discount.
- Order total amount equals subtotal minus discount plus shipping fee.

CHECK does not replace foreign keys and cannot verify the SUM of order items in another table. Cross-table rules must be enforced within application transactions, triggers, or appropriate data workflows.

## 3. Creating the Database

Run in the lab environment:

~~~sql
CREATE DATABASE mysql_order_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE mysql_order_lab;
~~~

If the database already exists, do not re-run CREATE DATABASE as a reset step. Use a dedicated test database or explicitly inspect existing data before recreating the schema.

Check the server version:

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@default_storage_engine AS default_engine,
       @@sql_mode AS sql_mode;
~~~

This lab requires InnoDB. The DDL will explicitly declare ENGINE=InnoDB so it does not rely on default server settings.

## 4. Creating the `customers` Table

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Explanation:

- customer_id is an auto-incrementing primary key.
- email is required and unique.
- full_name is required.
- phone can be NULL because a customer may not have provided a phone number yet.
- created_at stores the record creation timestamp with microsecond precision.

Do not use email as the primary key. Emails can change; an internal ID keeps references from related tables stable.

If the business allows multiple customers to use the same email across different tenants, the unique key must include tenant_id. This schema models a single storefront where email is table-wide unique.

## 5. Creating the `products` Table

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(13,2) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT chk_products_unit_price CHECK (unit_price >= 0.00),
    CONSTRAINT chk_products_is_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Explanation:

- SKU is a unique business code.
- unit_price uses DECIMAL(13,2) because money should not be stored as FLOAT/DOUBLE.
- is_active allows discontinuing a product while preserving order history.
- CHECK guards against negative prices and invalid status flags.
- updated_at is updated automatically when the row changes.

Do not delete a product simply because it is discontinued. Historical order items still need to reference the product for reporting and auditing. We use is_active = 0 to discontinue sales.

### 5.1. Why must the price in `order_items` still be stored separately?

products.unit_price is the current price. When a product's price increases from 100,000 to 120,000, orders created before the change must still keep the unit price of 100,000. Therefore, order_items has its own unit_price column as a snapshot.

Do not write historical queries by joining order_items with products and using products.unit_price to calculate old order totals. The price column in order_items is the actual transaction price.

## 6. Creating the `orders` Table

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_number VARCHAR(32) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    currency CHAR(3) NOT NULL DEFAULT 'VND',
    ordered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    subtotal DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    shipping_fee DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),

    KEY idx_orders_customer_ordered_at (customer_id, ordered_at),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT chk_orders_status
        CHECK (status IN (
            'PENDING',
            'CONFIRMED',
            'PAID',
            'CANCELLED',
            'FULFILLED'
        )),

    CONSTRAINT chk_orders_amounts
        CHECK (
            subtotal >= 0.00
            AND discount_amount >= 0.00
            AND shipping_fee >= 0.00
            AND total_amount >= 0.00
            AND discount_amount <= subtotal
            AND total_amount = subtotal - discount_amount + shipping_fee
        )
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Explanation:

- order_number is the user-facing order code, backed by a unique key.
- customer_id references customers.
- status is constrained by CHECK to prevent arbitrary values.
- currency stores a three-letter currency code; the example uses VND.
- subtotal is the total item amount before discounts.
- discount_amount is the total discount.
- shipping_fee is the shipping fee.
- total_amount must equal subtotal - discount_amount + shipping_fee.

Index idx_orders_customer_ordered_at serves queries fetching orders by customer sorted by timestamp. Having customer_id as the leading column also supports the foreign key lookup.

The total columns on the header hold aggregated data. CHECK only verifies the formula across columns within the same row; it does not automatically compute SUM from order_items. The application must update these columns in the same transaction as the order items.

### 6.1. Why not delete customers who have orders?

ON DELETE RESTRICT prevents deleting a customer while referencing rows exist in orders. This is the right choice when order history must be retained. If you need to hide or deactivate a customer, add a status column instead of deleting the row.

## 7. Creating the `order_items` Table

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13,2) NOT NULL,
    discount_amount DECIMAL(13,2) NOT NULL DEFAULT 0.00,

    line_total DECIMAL(15,2)
        GENERATED ALWAYS AS (
            quantity * unit_price - discount_amount
        ) STORED,

    PRIMARY KEY (order_item_id),

    CONSTRAINT uq_order_items_order_product
        UNIQUE (order_id, product_id),

    KEY idx_order_items_product_id (product_id),

    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_order_items_amounts
        CHECK (
            unit_price >= 0.00
            AND discount_amount >= 0.00
            AND discount_amount <= quantity * unit_price
        )
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Explanation:

- order_id references the order.
- product_id references the product.
- quantity must be greater than 0.
- unit_price is the snapshot price at the time of purchase.
- discount_amount is the discount for the order line.
- line_total is a generated column calculated from quantity, unit price, and discount.

Unique key (order_id, product_id) prevents the same product from appearing on multiple lines within the same order. If multiple lines are needed for one product, such as splitting by batch or different promotions, adjust the unique key according to that model.

Index idx_order_items_product_id supports looking up all orders containing a product and helps MySQL enforce the foreign key from products. The unique index starting with order_id already supports the reference to orders.

A generated column prevents the application from writing a line_total that mismatches quantity, unit_price, and discount_amount. If compatibility with a version or model that does not support generated columns this way is required, line_total can be stored as an application-computed column, but it must be validated inside the transaction.

### 7.1. Why is ON DELETE CASCADE only placed on `order_items.order_id`?

An order item belongs to an order. When deleting an order in the lab database, deleting its items along with it expresses a clear ownership relationship.

A product does not own historical order lines; orders need to preserve references to purchased products. Therefore, product_id uses ON DELETE RESTRICT. In practice, products are usually marked inactive rather than deleted.

## 8. Inspecting the Schema After Creation

Read the actual DDL:

~~~sql
SHOW CREATE TABLE customers\G
SHOW CREATE TABLE products\G
SHOW CREATE TABLE orders\G
SHOW CREATE TABLE order_items\G
~~~

Inspect indexes:

~~~sql
SHOW INDEX FROM customers;
SHOW INDEX FROM products;
SHOW INDEX FROM orders;
SHOW INDEX FROM order_items;
~~~

Check foreign keys and CHECK constraints in metadata:

~~~sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;
~~~

You can also view detailed columns and data types:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Do not rely solely on migration files to conclude that a schema is correct. SHOW CREATE TABLE and metadata reflect the actual structure the server is actively using.

## 9. Inserting Sample Data

We use explicit IDs to keep the examples readable. In typical applications, AUTO_INCREMENT generates IDs and the code retrieves the generated value via JDBC or an ORM.

Insert customers and products:

~~~sql
INSERT INTO customers
    (customer_id, email, full_name, phone)
VALUES
    (1, 'lan@example.com', 'Nguyen Mai Lan', '0901000001'),
    (2, 'minh@example.com', 'Tran Quoc Minh', '0901000002');

INSERT INTO products
    (product_id, sku, product_name, unit_price, is_active)
VALUES
    (101, 'COFFEE-01', 'Coffee beans 500g', 100000.00, 1),
    (102, 'MUG-01', 'Ceramic mug 350ml', 150000.00, 1),
    (103, 'TEA-01', 'Green tea 200g', 75000.00, 1);
~~~

Verify the data:

~~~sql
SELECT * FROM customers ORDER BY customer_id;
SELECT * FROM products ORDER BY product_id;
~~~

### 9.1. Creating an order and its items in a single transaction

Suppose customer 1 buys:

- Two bags of coffee at 100,000 per bag.
- One ceramic mug at 150,000.
- A 10,000 discount on the ceramic mug line.
- A 20,000 shipping fee.

Subtotal before discount is 350,000. Total discount is 10,000. Total payment is 350,000 - 10,000 + 20,000 = 360,000.

We create the header first, insert the order items, compute the totals from the items, and update the header before committing:

~~~sql
START TRANSACTION;

INSERT INTO orders (
    order_number,
    customer_id,
    status,
    currency,
    subtotal,
    discount_amount,
    shipping_fee,
    total_amount
)
VALUES (
    'ORD-2026-0001',
    1,
    'PENDING',
    'VND',
    0.00,
    0.00,
    20000.00,
    20000.00
);

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price,
    discount_amount
)
VALUES
    (@new_order_id, 101, 2, 100000.00, 0.00),
    (@new_order_id, 102, 1, 150000.00, 10000.00);

SELECT
    COALESCE(SUM(quantity * unit_price), 0.00),
    COALESCE(SUM(discount_amount), 0.00)
INTO @subtotal, @discount
FROM order_items
WHERE order_id = @new_order_id;

UPDATE orders
SET subtotal = @subtotal,
    discount_amount = @discount,
    total_amount = @subtotal - @discount + shipping_fee
WHERE order_id = @new_order_id;

COMMIT;
~~~

In this example, the header is created with subtotal and discount set to 0 so it satisfies the CHECK constraint during insertion. All operations reside inside one transaction; other connections cannot see the uncommitted state under InnoDB's default isolation level.

If any step fails, the application must ROLLBACK instead of committing an incomplete order. In Java/Spring code, use a clear transaction boundary, such as a service method annotated with @Transactional, and let exceptions trigger a rollback according to your configured policy.

Note: SQL clients may continue executing subsequent statements after an error depending on their mode. When running manually, if a statement inside the transaction fails, check the transaction state and explicitly run ROLLBACK before re-running the entire example.

### 9.2. Do not use current product prices to recalculate old orders

The price in order_items was captured at the time of purchase. Even if products.unit_price changes, order_items.unit_price stays unchanged. This is why order data must store a snapshot of the transaction price.

## 10. Querying Orders with JOINs

Retrieve full details of an order:

~~~sql
SELECT
    o.order_number,
    o.status,
    o.ordered_at,
    c.full_name,
    c.email,
    p.sku,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    oi.discount_amount,
    oi.line_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
WHERE o.order_number = 'ORD-2026-0001'
ORDER BY oi.order_item_id;
~~~

This is a relational read query:

- orders provides the header.
- customers provides customer details.
- order_items provides the line items.
- products provides the SKU and product name.

For an order that does not yet have any items, INNER JOIN will not return the header. If a report needs to display orders without items as well, use LEFT JOIN from orders to order_items.

### 10.1. Order total summary report

~~~sql
SELECT
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount,
    COALESCE(SUM(oi.line_total), 0.00) AS item_net_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
ORDER BY o.ordered_at DESC;
~~~

In this model, item_net_total is the sum of lines after line discounts. For the sample order, the result is 340,000; adding the 20,000 shipping fee yields total_amount of 360,000.

### 10.2. Finding orders whose header totals mismatch their items

We can use a reconciliation query:

~~~sql
SELECT
    o.order_id,
    o.order_number,
    o.subtotal,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
        AS calculated_subtotal,
    o.discount_amount,
    COALESCE(SUM(oi.discount_amount), 0.00)
        AS calculated_discount,
    o.total_amount,
    COALESCE(SUM(oi.line_total), 0.00) + o.shipping_fee
        AS calculated_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
HAVING
    o.subtotal <> calculated_subtotal
    OR o.discount_amount <> calculated_discount
    OR o.total_amount <> calculated_total;
~~~

If zero rows are returned, header totals match the line items under this lab's model. This query is useful for periodic reconciliation jobs.

Production systems may involve order-level discounts, taxes, vouchers, packaging fees, or rounding. In those cases, extend the formula and snapshot model accordingly; do not force every business rule into one simple calculation.

## 11. Testing FOREIGN KEY Constraints

Foreign keys must prevent referencing a non-existent parent row.

Try inserting an order with a non-existent customer_id:

~~~sql
INSERT INTO orders (
    order_number,
    customer_id,
    status,
    currency
)
VALUES (
    'ORD-INVALID-CUSTOMER',
    999999,
    'PENDING',
    'VND'
);
~~~

Expected result: MySQL rejects the insert due to violating fk_orders_customer.

Try inserting an order item with a non-existent product_id:

~~~sql
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES (
    (SELECT order_id FROM orders
     WHERE order_number = 'ORD-2026-0001'),
    999999,
    1,
    10000.00
);
~~~

Expected result: MySQL rejects the insert due to violating fk_order_items_product. The subquery looks up order_id from the sample order number so the example does not depend on a specific AUTO_INCREMENT value.

### 11.1. Testing UNIQUE Constraints

Try inserting an already existing email:

~~~sql
INSERT INTO customers (email, full_name)
VALUES ('lan@example.com', 'Lan Duplicate');
~~~

Expected result: MySQL returns a duplicate key error for uq_customers_email. Likewise, SKU and order_number must remain unique according to their declared unique keys.

Try deleting a customer who already has orders:

~~~sql
DELETE FROM customers
WHERE customer_id = 1;
~~~

Expected result: rejected due to ON DELETE RESTRICT.

Try deleting a product that already has order items:

~~~sql
DELETE FROM products
WHERE product_id = 101;
~~~

Expected result: rejected due to ON DELETE RESTRICT.

Error test statements should be executed separately rather than placed inside an automated seed script if the runner aborts the whole script on error.

## 12. Testing CHECK Constraints

On MySQL 8.0.16 or later, try inserting a negative price:

~~~sql
INSERT INTO products (
    sku,
    product_name,
    unit_price,
    is_active
)
VALUES (
    'BAD-PRICE',
    'Negative price product',
    -1000.00,
    1
);
~~~

Expected result: rejected by chk_products_unit_price.

Try a quantity of 0:

~~~sql
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES (
    (SELECT order_id FROM orders
     WHERE order_number = 'ORD-2026-0001'),
    103,
    0,
    75000.00
);
~~~

Expected result: rejected by chk_order_items_quantity. The subquery retrieves order_id from the sample order created earlier.

Try an invalid status:

~~~sql
UPDATE orders
SET status = 'UNKNOWN'
WHERE order_number = 'ORD-2026-0001';
~~~

Expected result: rejected by chk_orders_status.

Try a total amount that violates the formula:

~~~sql
UPDATE orders
SET total_amount = 1.00
WHERE order_number = 'ORD-2026-0001';
~~~

Expected result: rejected by chk_orders_amounts.

If any of the statements above succeed, check your MySQL version. MySQL versions before 8.0.16 do not enforce CHECK constraints; some MySQL-compatible engines also have their own rules. Do not assume CHECK is active just because SHOW CREATE TABLE displays the expression.

## 13. Verifying Integrity with Queries

### 13.1. Finding order items without a parent order

Foreign keys should prevent this situation, yet verification queries are helpful after migrations or during data audits:

~~~sql
SELECT oi.*
FROM order_items AS oi
LEFT JOIN orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

### 13.2. Finding order items without a product

~~~sql
SELECT oi.*
FROM order_items AS oi
LEFT JOIN products AS p
    ON p.product_id = oi.product_id
WHERE p.product_id IS NULL;
~~~

### 13.3. Checking for abnormal statuses and values

~~~sql
SELECT order_id, order_number, status, total_amount
FROM orders
WHERE status NOT IN (
    'PENDING',
    'CONFIRMED',
    'PAID',
    'CANCELLED',
    'FULFILLED'
)
OR total_amount < 0.00;
~~~

These queries act as supplementary checks. When constraints are enforced and not disabled, they typically return empty result sets. However, bulk imports, older server versions, or schema changes can still make independent verification necessary.

## 14. Indexes and How to Inspect Queries

The indexes in this schema are chosen based on relationships and expected queries:

| Index | Purpose |
|---|---|
| PRIMARY KEY on each table | Row identification and lookup |
| UNIQUE customers.email | Prevents duplicate emails and looks up customers by email |
| UNIQUE products.sku | Prevents duplicate SKUs and looks up products |
| UNIQUE orders.order_number | Prevents duplicate order numbers and looks up orders |
| idx_orders_customer_ordered_at | Fetches orders by customer and timestamp |
| UNIQUE order_items(order_id, product_id) | Prevents duplicate products within an order, supports finding items by order |
| idx_order_items_product_id | Finds orders containing a product and supports FK checks |

Use EXPLAIN to inspect the query execution plan:

~~~sql
EXPLAIN
SELECT order_id, order_number, ordered_at
FROM orders
WHERE customer_id = 1
ORDER BY ordered_at DESC;
~~~

Inspect:

- key: the index MySQL plans to use.
- type: the access method.
- rows: estimated number of rows examined.
- Extra: additional details such as Using filesort or Using index.

Indexes are not free. Every index increases storage usage and INSERT/UPDATE/DELETE overhead. Do not add an index on every column merely because it appears in a WHERE clause. Base decisions on actual queries, cardinality, selectivity, and EXPLAIN ANALYZE on supported versions.

## 15. Transactions and Write Ordering

Order creation operations must be atomic:

1. Create the order header.
2. Create the order_items rows.
3. Compute subtotal and discount from the items.
4. Update total_amount.
5. Commit.

If any step fails, roll back everything so no half-created order remains.

Conceptual Java/Spring example:

~~~java
@Service
public class OrderService {

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(
            Order.pendingFor(command.customerId(), command.shippingFee())
        );

        for (CreateOrderLine line : command.lines()) {
            Product product = productRepository.findById(line.productId())
                .orElseThrow(ProductNotFoundException::new);

            if (!product.isActive()) {
                throw new ProductNotAvailableException();
            }

            orderItemRepository.save(
                OrderItem.snapshot(
                    order,
                    product,
                    line.quantity(),
                    product.getUnitPrice(),
                    line.discountAmount()
                )
            );
        }

        orderTotalsService.recalculate(order.getId());
        return order.getId();
    }
}
~~~

This is an outline illustrating transaction boundaries and snapshot pricing. Production code must explicitly define monetary calculations, rounding, concurrency during price updates, inventory checks, and flush timing. Do not call non-idempotent external services inside a long-running database transaction.

### 15.1. Why is checking whether a product is active not enough?

An application may read `is_active = 1` right before another transaction discontinues the product prior to commit. If business rules prohibit selling a product after it has been discontinued, a concurrency strategy is needed: lock the product row with `SELECT ... FOR UPDATE`, verify its status inside the transaction, and write the order in a consistent order.

Similarly, if inventory exists, quantities must be checked and updated atomically or with proper locking to prevent overselling. The current schema does not include an inventory table, so it cannot enforce stock rules.

## 16. ON DELETE and ON UPDATE Rules

Referential action choices should reflect the data lifecycle.

| Relationship | ON DELETE | Rationale |
|---|---|---|
| customers → orders | RESTRICT | Never delete customers with order history |
| orders → order_items | CASCADE | Order items belong to the order in the demo model |
| products → order_items | RESTRICT | Preserve historical product references |

ON UPDATE RESTRICT is used across all keys. Internal IDs should remain stable and rarely change. If a parent key must change, perform a controlled migration rather than relying on cascading updates on an identity key.

Do not use ON DELETE CASCADE by default for every relationship. Deleting a customer could wipe out millions of orders and payment records if cascades propagate broadly; this behavior can cause long locks, huge transaction logs, and loss of business history.

## 17. Extending the Schema for Real-World Requirements

Once the core schema works properly, you can add:

- **order_addresses:** snapshot of the shipping address at order placement time.
- **payments:** payment transactions, provider references, statuses, and idempotency keys.
- **order_status_history:** audit trail of status transitions.
- **inventory:** stock levels per product/warehouse and reservations.
- **shipments:** delivery records, tracking numbers, and statuses.
- **taxes/promotions:** tax and promotion rules.
- **audit log:** actor, timestamp, and source of changes.

Every new table needs defined primary keys, foreign keys, unique constraints, CHECK constraints, indexes, and retention/deletion policies. Do not add relationships simply because you can; add them when concrete business rules and queries require them.

### 17.1. Price history and order snapshots

If you need to track how product prices changed over time, create a `product_price_history` table with `effective_from`/`effective_to` or store price-change events. However, `order_items` must still store the exact price applied to each specific transaction. Price history and snapshot prices serve two different purposes.

### 17.2. Currencies and rounding

DECIMAL(13,2) fits a VND example using a two-decimal-place model, though VND in practice is typically handled in whole-dong units. Decide precision and scale based on the supported currencies. If supporting multiple currencies, do not assume every currency shares the same number of decimal places. Rounding rules must be consistent across the application and tested with boundary values.

## 18. Schema Completion Checklist

- [ ] Database created with utf8mb4 charset.
- [ ] All tables use InnoDB.
- [ ] customers and products created before referencing tables.
- [ ] Each table has a stable PRIMARY KEY.
- [ ] Email, SKU, and order number have appropriate UNIQUE constraints.
- [ ] Foreign key data types match the referenced key types.
- [ ] Foreign keys declared with intentional ON DELETE/ON UPDATE actions.
- [ ] Indexes added to support queries and foreign keys.
- [ ] Prices and totals use DECIMAL.
- [ ] Quantity has a CHECK greater than 0.
- [ ] Status has a CHECK restricting allowed values.
- [ ] Header totals satisfy the same-row formula.
- [ ] Verified that the MySQL version enforces CHECK constraints.
- [ ] Sample data written inside a transaction.
- [ ] Line-item unit prices are snapshots captured at purchase time.
- [ ] Tested foreign key, unique, and CHECK constraint errors.
- [ ] Inspected SHOW CREATE TABLE, SHOW INDEX, and metadata.
- [ ] Ran JOIN, aggregation, and reconciliation queries.
- [ ] Checked EXPLAIN for key queries.
- [ ] Defined rollback handling when an order creation step fails.

## 19. Extended Practice Exercises

1. Add an `order_addresses` table to store snapshot shipping addresses. Choose an appropriate ON DELETE action and explain why referencing only the customer's current address is insufficient.
2. Add a `payments` table with a unique `provider_reference` and a CHECK constraint requiring `amount` to be greater than 0.
3. Add `order_status_history` to record every status transition; determine the index needed to query history by `order_id` and timestamp.
4. Add a `tenant_id` column to `customers` and `orders`, then replace the unique email constraint with `UNIQUE (tenant_id, email)`.
5. Modify the model so a single product can appear on multiple lines within one order. Choose a new unique key.
6. Write a query to find the top 10 products by total quantity sold.
7. Write a query to calculate daily revenue for a given month.
8. Use EXPLAIN to compare querying orders by `customer_id` before and after adding a suitable index.
9. Insert a record with a non-existent `product_id` and capture the foreign key error.
10. Attempt to insert a negative price on MySQL 8.0.16+ and compare with an older MySQL environment that does not enforce CHECK.
11. Simulate two concurrent transactions creating the same `order_number` to observe the unique constraint behavior.
12. Design an order-creation transaction that checks inventory and updates stock without overselling remaining quantities.

## 20. Self-Check

1. Why does `order_items` need to store `unit_price` instead of always reading the price from `products`?
2. Why should the `customer_id` foreign key reference the PRIMARY KEY of `customers`?
3. What does the unique key `(order_id, product_id)` enforce, and which business scenarios does it restrict?
4. Why does `products` use ON DELETE RESTRICT while `order_items` uses ON DELETE CASCADE toward `orders`?
5. Can CHECK inspect the SUM of `order_items` to validate `orders.total_amount`?
6. Why must total amounts be updated in the same transaction as the order items?
7. Why is DECIMAL more suitable than FLOAT for monetary values?
8. Why can't MySQL versions prior to 8.0.16 rely on CHECK to protect data?
9. Which index supports querying orders by customer and timestamp?
10. When adding inventory, how must concurrency be handled to prevent overselling?

After completing this lab, the schema enforces core business rules directly in MySQL: unique identifiers, valid parent-child relationships, non-negative prices, positive quantities, and order statuses within an allowed set. Transactions bind header creation, item insertion, and total calculation into a single unit of work. As you expand into payments, inventory, and shipping, continue designing constraints around business rules and validating them with both sample data and intentional constraint violations.
