# Building an Order Management Schema with Constraints, Sequences, and Sample Data

An order management schema needs to model customers, products, orders, and order line items. A sound design must preserve data integrity when an application creates orders, adds products, changes order status, or updates product prices. Oracle Database provides primary keys, foreign keys, unique constraints, check constraints, not null constraints, sequences, triggers, and views to build a controllable data foundation.

This hands-on lab builds a small schema structured closely to a real-world application. We will create the `CUSTOMERS`, `CURRENCIES`, `PRODUCTS`, `ORDERS`, and `ORDER_ITEMS` tables; define keys and constraints; use sequences combined with triggers to generate IDs; load sample data; and run verification and order aggregation queries.

The statements are written for Oracle SQL. Run them in an application schema where the DBA has granted privileges to create tables, sequences, triggers, and views, along with sufficient tablespace quota. You do not need to grant the `DBA` role to the application user.

## 1. Defining Requirements and the Data Model

### 1.1. Core Entities

| Table | Role | Primary Key |
|---|---|---|
| `CUSTOMERS` | Stores customer information. | `CUSTOMER_ID` |
| `CURRENCIES` | Catalog of valid currencies. | `CURRENCY_CODE` |
| `PRODUCTS` | Product catalog and current prices. | `PRODUCT_ID` |
| `ORDERS` | Order header information. | `ORDER_ID` |
| `ORDER_ITEMS` | Product line items belonging to an order. | (`ORDER_ID`, `LINE_NO`) |

Data relationships:

```text
CUSTOMERS (1) -------- (N) ORDERS
                           |
                           | (1)
                           |
                           (N)
                       ORDER_ITEMS
                           |
                           | (N)
                           |
                           (1)
                        PRODUCTS

CURRENCIES (1) -------- (N) PRODUCTS
CURRENCIES (1) -------- (N) ORDERS
```

A customer can have multiple orders. An order has one or more line items. Each line item references a product. Both products and orders reference a currency code to prevent storing arbitrary currency strings.

### 1.2. Why Is ORDER_ITEMS a Separate Table?

An order can contain multiple products; if `PRODUCT_ID`, `QUANTITY`, and `UNIT_PRICE` were placed directly in `ORDERS`, each order could store only one product or would require repeating columns such as `PRODUCT_1`, `PRODUCT_2`. That approach is difficult to scale and causes anomalies during inserts and updates.

Separating `ORDER_ITEMS` establishes a clear one-to-many relationship. The composite primary key (`ORDER_ID`, `LINE_NO`) identifies each line within an order. `LINE_NO` is a sequence number assigned by the application within the scope of a single order, so it does not require a separate database sequence.

### 1.3. Storing the Sale Price at Order Time

`PRODUCTS.UNIT_PRICE` is the current catalog price. `ORDER_ITEMS.UNIT_PRICE` is the price locked in at the time the order is placed. You should not recalculate historical orders using the product's current price because catalog prices can change later.

Similarly, an order stores the transaction's `CURRENCY_CODE`. If a product later changes its price or listing currency, historical order data still retains the amounts and currency applied at purchase time.

### 1.4. Business Rules and Database Constraints

The schema will enforce rules that can be expressed at the row or relationship level:

- IDs must not be null and must not be duplicated.
- Customer emails and product SKUs are unique.
- An order must reference an existing customer.
- A line item must reference an existing order and an existing product.
- Quantity must be greater than 0.
- Unit price and discount must be non-negative.
- A line item's discount must not exceed its pre-discount line total.
- Order status may only accept one of the predefined values.
- Currency code must exist in the currencies catalog.

Rules spanning multiple tables, such as requiring the product's currency to match the order's currency, should be validated in the application service or stored procedure within the same transaction. A standard `CHECK` constraint cannot query another table.

## 2. Choosing Oracle Data Types

| Data | Recommended Type | Reason |
|---|---|---|
| ID | `NUMBER(19,0)` | Used for large integer keys. |
| Name/email/SKU | `VARCHAR2(... CHAR)` | Bounded strings; uses explicit character semantics. |
| Quantity | `NUMBER(12,3)` | Allows goods measured in fractional units. |
| Unit price/discount | `NUMBER(19,4)` | Preserves decimal precision, avoiding floating-point types. |
| Status | `VARCHAR2(20 CHAR)` | Readable status code with a check constraint. |
| Timestamp | `TIMESTAMP(6) WITH TIME ZONE` | Stores point-in-time values with timezone/offset. |
| Long notes | `CLOB` if needed | Intended for large text content. |

Do not use `FLOAT` or `BINARY_DOUBLE` for monetary values if the business requires exact decimal arithmetic. In Java, `BigDecimal` typically maps well to Oracle `NUMBER` for currency amounts and fractional quantities.

Oracle `DATE` stores both date and time down to the second. If only a calendar date is needed, `DATE` can be used with a convention for the time component; if fractional seconds or time zones are needed, use the appropriate `TIMESTAMP` type. The examples below use `TIMESTAMP WITH TIME ZONE` for key event timestamps.

## 3. Creating Tables in Dependency Order

Create parent tables before child tables so foreign keys can reference them. Execute in the application schema; object names without a schema prefix belong to the current user.

### 3.1. CURRENCIES Table

```sql
CREATE TABLE currencies (
    currency_code  VARCHAR2(3 CHAR)  NOT NULL,
    currency_name  VARCHAR2(60 CHAR) NOT NULL,
    minor_units    NUMBER(1,0)       DEFAULT 2 NOT NULL,
    CONSTRAINT pk_currencies PRIMARY KEY (currency_code),
    CONSTRAINT ck_currencies_code_len
        CHECK (LENGTH(currency_code) = 3),
    CONSTRAINT ck_currencies_minor_units
        CHECK (minor_units BETWEEN 0 AND 4)
);
```

`CURRENCY_CODE` is a three-character code primary key. `MINOR_UNITS` describes the standard number of decimal places for the currency, though rounding and calculation rules must still be handled consistently in the business layer.

### 3.2. CUSTOMERS Table

```sql
CREATE TABLE customers (
    customer_id  NUMBER(19,0)       NOT NULL,
    full_name    VARCHAR2(150 CHAR) NOT NULL,
    email        VARCHAR2(320 CHAR) NOT NULL,
    phone        VARCHAR2(30 CHAR),
    created_at   TIMESTAMP(6) WITH TIME ZONE
                 DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);
```

`EMAIL` is marked unique to prevent two customers from sharing the same email address per the example's rules. If the business allows duplicate emails or email is not a unique identifier, adjust the constraint accordingly. Oracle currently treats an empty `VARCHAR2` string as `NULL`; therefore, `NOT NULL` also prevents empty emails under Oracle semantics.

### 3.3. PRODUCTS Table

```sql
CREATE TABLE products (
    product_id    NUMBER(19,0)        NOT NULL,
    sku           VARCHAR2(40 CHAR)   NOT NULL,
    product_name  VARCHAR2(200 CHAR) NOT NULL,
    unit_price    NUMBER(19,4)        NOT NULL,
    currency_code VARCHAR2(3 CHAR)   NOT NULL,
    is_active     CHAR(1 CHAR)        DEFAULT 'Y' NOT NULL,
    created_at    TIMESTAMP(6) WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT fk_products_currency
        FOREIGN KEY (currency_code)
        REFERENCES currencies (currency_code),
    CONSTRAINT ck_products_price CHECK (unit_price >= 0),
    CONSTRAINT ck_products_active CHECK (is_active IN ('Y', 'N'))
);
```

SKU is a unique product code. The current price must not be negative. `IS_ACTIVE` allows discontinuing a product while keeping references from historical orders intact. Do not delete products that have already been used in order history.

### 3.4. ORDERS Table

```sql
CREATE TABLE orders (
    order_id         NUMBER(19,0)        NOT NULL,
    order_number     VARCHAR2(30 CHAR)  NOT NULL,
    customer_id      NUMBER(19,0)        NOT NULL,
    ordered_at       TIMESTAMP(6) WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,
    order_status     VARCHAR2(20 CHAR)  DEFAULT 'PENDING' NOT NULL,
    currency_code    VARCHAR2(3 CHAR)  NOT NULL,
    shipping_address VARCHAR2(500 CHAR),
    note             VARCHAR2(1000 CHAR),
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT fk_orders_currency
        FOREIGN KEY (currency_code)
        REFERENCES currencies (currency_code),
    CONSTRAINT ck_orders_status
        CHECK (order_status IN (
            'PENDING', 'CONFIRMED', 'SHIPPED',
            'COMPLETED', 'CANCELLED'
        ))
);
```

`ORDER_NUMBER` is the user-facing code and has a unique constraint. `ORDER_ID` is the technical surrogate key used for joins. The two identifiers serve different purposes.

The shipping address is stored as a snapshot on the order so history does not change when a customer updates their profile address. In a more complex system, a separate address table can exist while still copying the required fields onto the order at checkout time.

### 3.5. ORDER_ITEMS Table

```sql
CREATE TABLE order_items (
    order_id         NUMBER(19,0) NOT NULL,
    line_no          NUMBER(5,0)  NOT NULL,
    product_id       NUMBER(19,0) NOT NULL,
    quantity         NUMBER(12,3) NOT NULL,
    unit_price       NUMBER(19,4) NOT NULL,
    discount_amount  NUMBER(19,4) DEFAULT 0 NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT ck_order_items_line_no CHECK (line_no > 0),
    CONSTRAINT ck_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_items_price CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_discount
        CHECK (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        )
);
```

The composite primary key guarantees line numbers do not duplicate within the same order. Foreign keys prevent a line item from referencing a nonexistent order or product. `UNIT_PRICE` stores the price locked at sale time; `DISCOUNT_AMOUNT` stores the monetary discount for that line.

The example uses default foreign key behavior, disallowing deletion of a referenced parent record. This is intentional to protect order history. Do not use `ON DELETE CASCADE` for `ORDERS`/`ORDER_ITEMS` if the system must retain transaction trails or meet audit requirements.

## 4. Creating Indexes for Queries and Foreign Keys

Primary keys and unique constraints typically create corresponding unique indexes. For foreign keys that are not the leading column of an existing index, consider adding dedicated indexes to support joins and reduce locking issues when updating or deleting parent rows.

```sql
CREATE INDEX ix_orders_customer_date
    ON orders (customer_id, ordered_at);

CREATE INDEX ix_orders_status_date
    ON orders (order_status, ordered_at);

CREATE INDEX ix_order_items_product
    ON order_items (product_id);
```

The primary key of `ORDER_ITEMS` is `(ORDER_ID, LINE_NO)`, so the PK index already supports queries filtering on `ORDER_ID` as the leading column. The `PRODUCT_ID` index supports querying line items by product as well as foreign key operations.

Do not create an index on every column. Every index increases storage usage and the cost of `INSERT`, `UPDATE`, and `DELETE`; choose indexes based on actual workload and verify execution plans.

## 5. Creating Sequences for Primary Key Generation

### 5.1. What Is a Sequence?

A sequence is an Oracle object that generates a series of numbers on demand. Multiple sessions can fetch values from the same sequence without manually locking a counter table. Sequences are well suited for issuing technical IDs for customers, products, and orders.

Create the sequences:

```sql
CREATE SEQUENCE customers_seq
    START WITH 1001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;

CREATE SEQUENCE products_seq
    START WITH 5001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;

CREATE SEQUENCE orders_seq
    START WITH 9001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;
```

Explanation:

- `START WITH`: starting value.
- `INCREMENT BY`: step increment on each fetch.
- `MINVALUE`/`NOMAXVALUE`: range bounds.
- `CACHE 50`: caches a batch of values in the instance to reduce sequence acquisition overhead.
- `NOCYCLE`: does not wrap around when reaching the limit.

The starting values above are for illustration only. In a system with pre-loaded data, choose sequence starting values higher than existing keys or synchronize the sequence according to your deployment procedure.

### 5.2. NEXTVAL and CURRVAL

Fetch a new value:

```sql
SELECT customers_seq.NEXTVAL
FROM dual;
```

After calling `NEXTVAL` in the current session, you can read the value just obtained with:

```sql
SELECT customers_seq.CURRVAL
FROM dual;
```

`CURRVAL` can only be used in a session after that session has called `NEXTVAL` at least once for the corresponding sequence. Values fetched by other sessions do not affect the current session's `CURRVAL`.

It can also be used directly in an `INSERT`:

```sql
INSERT INTO customers (
    customer_id, full_name, email
)
VALUES (
    customers_seq.NEXTVAL,
    'Nguyen An',
    'an@example.com'
);
```

### 5.3. Sequences Do Not Guarantee Gapless IDs

Sequences can produce gaps because:

- A transaction calls `NEXTVAL` and then rolls back.
- An instance restarts or the sequence cache is aged out/lost.
- Multiple sessions fetch numbers concurrently.
- A statement fetches a sequence value but fails to insert.
- RAC/cache configurations and sequence activity leave gaps.

This is normal behavior. Do not use sequences for invoice numbers that must be strictly contiguous if business or legal regulations prohibit gaps. A sequence guarantees unique values within its configured range, not a gapless transaction counter.

### 5.4. CACHE, ORDER, and RAC

`CACHE` improves performance when many sessions fetch sequence values concurrently. If the instance stops abnormally, cached but unused values may be skipped; gaps are not an error.

In RAC, a `NOORDER` sequence is typically suitable when you only need unique values and high throughput. `ORDER` enforces cluster-wide allocation order matching request order, which can increase coordination overhead. Do not enable `ORDER` merely because you want IDs ordered by commit time; sequences do not guarantee transaction commit order.

### 5.5. Inspecting Sequences

```sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM user_sequences
ORDER BY sequence_name;
```

For cached sequences, `LAST_NUMBER` may reflect the next value recorded/cache boundary rather than the exact last value handed out to the application. Do not rely on it as exact proof of the highest ID currently stored in a table.

## 6. Using Triggers to Auto-Assign IDs

### 6.1. Why Use Triggers?

A `BEFORE INSERT` trigger can fetch `NEXTVAL` when the application omits the ID. This lets `INSERT` statements supply only business columns while the database assigns the key automatically.

Trigger for customers:

```sql
CREATE OR REPLACE TRIGGER customers_bir
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    IF :NEW.customer_id IS NULL THEN
        :NEW.customer_id := customers_seq.NEXTVAL;
    END IF;
END;
/
```

Trigger for products:

```sql
CREATE OR REPLACE TRIGGER products_bir
BEFORE INSERT ON products
FOR EACH ROW
BEGIN
    IF :NEW.product_id IS NULL THEN
        :NEW.product_id := products_seq.NEXTVAL;
    END IF;
END;
/
```

Trigger for orders:

```sql
CREATE OR REPLACE TRIGGER orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.order_id IS NULL THEN
        :NEW.order_id := orders_seq.NEXTVAL;
    END IF;
END;
/
```

`FOR EACH ROW` creates a row-level trigger. `:NEW` represents the row values being inserted; the trigger only assigns an ID when the provided value is `NULL`, allowing authorized migration or import tasks to supply explicit IDs provided there is a plan to synchronize the sequence afterward.

### 6.2. Checking Triggers and Compilation Errors

```sql
SELECT trigger_name,
       table_name,
       status,
       triggering_event
FROM user_triggers
WHERE table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS')
ORDER BY table_name, trigger_name;
```

If a trigger is invalid:

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
```

Do not proceed with loading data while an ID-generating trigger is `INVALID` or `DISABLED`. An insert omitting the ID will fail due to the `NOT NULL` primary key constraint if the trigger does not fire.

### 6.3. Modern Alternative: Identity Columns

Oracle 12c and later support identity columns. If a project does not need to manage separate sequences and triggers, you can declare:

```sql
CREATE TABLE customers_identity_demo (
    customer_id NUMBER(19,0)
        GENERATED BY DEFAULT ON NULL AS IDENTITY
        (START WITH 1 INCREMENT BY 1 CACHE 50),
    full_name VARCHAR2(150 CHAR) NOT NULL,
    CONSTRAINT pk_customers_identity_demo PRIMARY KEY (customer_id)
);
```

Identity columns make DDL cleaner, with Oracle managing the internal sequence. `GENERATED ALWAYS` prevents the application from passing an explicit value; `BY DEFAULT` allows explicit values; `BY DEFAULT ON NULL` also auto-generates a value when `NULL` is supplied.

Choose one ID generation mechanism per column: either identity or sequence/trigger. Do not both declare an identity column and attach a sequence-fetching trigger for the same ID. The main example in this lab uses sequence/trigger to clearly demonstrate the mechanism and remain compatible with older Oracle systems.

## 7. Loading Sample Reference Data

Run these statements in an empty schema or a fresh test schema. The unique values in the examples are designed for a single run; re-running them will trigger unique constraint errors. For seed scripts that must be idempotent across multiple runs, switch to `MERGE` or check for existing rows before inserting.

### 7.1. Loading Currencies

```sql
INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('VND', 'Vietnamese Dong', 0);

INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('USD', 'US Dollar', 2);

INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('EUR', 'Euro', 2);
```

### 7.2. Loading Customers

Omit `CUSTOMER_ID`; the trigger will fetch a value from `CUSTOMERS_SEQ`:

```sql
INSERT INTO customers (full_name, email, phone)
VALUES ('Nguyen An', 'an@example.com', '+84901234567');

INSERT INTO customers (full_name, email, phone)
VALUES ('Tran Binh', 'binh@example.com', '+84907654321');

INSERT INTO customers (full_name, email, phone)
VALUES ('Le Chi', 'chi@example.com', NULL);
```

### 7.3. Loading Products

```sql
INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'KB-001', 'Mechanical Keyboard', 125.5000, 'USD', 'Y'
);

INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'MS-002', 'Wireless Mouse', 45.0000, 'USD', 'Y'
);

INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'BAG-003', 'Laptop Bag', 750000.0000, 'VND', 'Y'
);
```

### 7.4. Creating Sample Orders

Use `INSERT ... SELECT` to look up `CUSTOMER_ID` by the unique email:

```sql
INSERT INTO orders (
    order_number,
    customer_id,
    currency_code,
    order_status,
    shipping_address,
    note
)
SELECT
    'ORD-2026-0001',
    customer_id,
    'USD',
    'CONFIRMED',
    '12 Nguyen Hue, District 1, Ho Chi Minh City',
    'Sample order one'
FROM customers
WHERE email = 'an@example.com';
```

```sql
INSERT INTO orders (
    order_number,
    customer_id,
    currency_code,
    order_status,
    shipping_address,
    note
)
SELECT
    'ORD-2026-0002',
    customer_id,
    'VND',
    'PENDING',
    '25 Le Loi, District 1, Ho Chi Minh City',
    'Sample order two'
FROM customers
WHERE email = 'binh@example.com';
```

Each query must return exactly one customer. The unique constraint on email supports that assumption; if no row matches, `INSERT ... SELECT` inserts 0 rows without necessarily raising an error. In production scripts, check the row count or use PL/SQL to raise an explicit error when the customer is not found.

### 7.5. Adding Order Line Items

Prices are copied from the catalog into `ORDER_ITEMS.UNIT_PRICE` when the order is created:

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    1,
    p.product_id,
    1,
    p.unit_price,
    0
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0001'
  AND p.sku = 'KB-001';
```

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    2,
    p.product_id,
    2,
    p.unit_price,
    5.0000
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0001'
  AND p.sku = 'MS-002';
```

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    1,
    p.product_id,
    1,
    p.unit_price,
    0
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0002'
  AND p.sku = 'BAG-003';
```

In a real application, the service must verify that the product is active and that the price and currency are valid, then create the order header and lines within the same transaction. The SQL examples above assume the orders and products already exist.

### 7.6. Committing Sample Data

```sql
COMMIT;
```

DML statements can be rolled back before commit. However, DDL in Oracle issues implicit commits before and after many DDL statements; do not expect to roll back an entire script that creates tables and sequences as a single DML transaction.

## 8. Creating a View for Order Totals

Avoid storing duplicate order totals in both the header and line items unless you have a consistent synchronization strategy. Totals can be computed from line items using a view:

```sql
CREATE OR REPLACE VIEW v_order_totals AS
SELECT
    o.order_id,
    o.order_number,
    o.customer_id,
    o.ordered_at,
    o.order_status,
    o.currency_code,
    NVL(
        SUM(oi.quantity * oi.unit_price - oi.discount_amount),
        0
    ) AS total_amount
FROM orders o
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.customer_id,
    o.ordered_at,
    o.order_status,
    o.currency_code;
```

The `LEFT JOIN` ensures that orders without line items still appear with a total of 0. `NVL` replaces a `NULL` result from `SUM` with 0. If taxes, shipping fees, order-level coupons, or order-level rounding exist, extend the model and calculation rules accordingly; do not assume the total is always just the sum of line amounts across all systems.

## 9. Verification Queries

### 9.1. Viewing Customers

```sql
SELECT customer_id, full_name, email, phone, created_at
FROM customers
ORDER BY customer_id;
```

### 9.2. Viewing the Product Catalog

```sql
SELECT p.product_id,
       p.sku,
       p.product_name,
       p.unit_price,
       p.currency_code,
       p.is_active,
       c.currency_name
FROM products p
JOIN currencies c
  ON c.currency_code = p.currency_code
ORDER BY p.sku;
```

### 9.3. Viewing Orders and Totals

```sql
SELECT order_number,
       customer_id,
       ordered_at,
       order_status,
       currency_code,
       total_amount
FROM v_order_totals
ORDER BY ordered_at DESC;
```

### 9.4. Viewing Details of a Single Order

```sql
SELECT o.order_number,
       c.full_name,
       o.order_status,
       o.currency_code,
       oi.line_no,
       p.sku,
       p.product_name,
       oi.quantity,
       oi.unit_price,
       oi.discount_amount,
       oi.quantity * oi.unit_price - oi.discount_amount AS line_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
JOIN products p
  ON p.product_id = oi.product_id
WHERE o.order_number = 'ORD-2026-0001'
ORDER BY oi.line_no;
```

### 9.5. Top Products by Revenue

```sql
SELECT p.sku,
       p.product_name,
       SUM(oi.quantity) AS units_sold,
       SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS sales_amount
FROM order_items oi
JOIN products p
  ON p.product_id = oi.product_id
JOIN orders o
  ON o.order_id = oi.order_id
WHERE o.order_status IN ('CONFIRMED', 'SHIPPED', 'COMPLETED')
GROUP BY p.sku, p.product_name
ORDER BY sales_amount DESC;
```

This aggregation query groups orders by product without separating currencies. In the sample schema, both USD and VND can exist; directly summing monetary amounts across different currencies is a business logic error. In real reports, also group by `o.currency_code`, or convert amounts using a defined exchange rate and conversion timestamp.

Version grouped by currency:

```sql
SELECT p.sku,
       p.product_name,
       o.currency_code,
       SUM(oi.quantity) AS units_sold,
       SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS sales_amount
FROM order_items oi
JOIN products p
  ON p.product_id = oi.product_id
JOIN orders o
  ON o.order_id = oi.order_id
WHERE o.order_status IN ('CONFIRMED', 'SHIPPED', 'COMPLETED')
GROUP BY p.sku, p.product_name, o.currency_code
ORDER BY o.currency_code, sales_amount DESC;
```

## 10. Verifying Constraints and Metadata

### 10.1. Viewing Constraints

```sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred
FROM user_constraints
WHERE table_name IN (
    'CURRENCIES', 'CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS'
)
ORDER BY table_name, constraint_type, constraint_name;
```

Common constraint types:

| Code | Meaning |
|---|---|
| `P` | Primary key. |
| `R` | Referential integrity / foreign key. |
| `U` | Unique. |
| `C` | Check constraint or not null constraint represented in the data dictionary. |

### 10.2. Viewing Columns Participating in Constraints

```sql
SELECT uc.table_name,
       uc.constraint_name,
       ucc.column_name,
       ucc.position
FROM user_constraints uc
JOIN user_cons_columns ucc
  ON ucc.constraint_name = uc.constraint_name
 AND ucc.table_name = uc.table_name
WHERE uc.table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS')
ORDER BY uc.table_name, uc.constraint_name, ucc.position;
```

### 10.3. Viewing Indexes

```sql
SELECT index_name,
       table_name,
       uniqueness,
       status,
       visibility
FROM user_indexes
WHERE table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS')
ORDER BY table_name, index_name;
```

### 10.4. Checking for Orphan Data

Enabled and validated foreign keys prevent most orphan scenarios. Even so, reconciliation queries are useful after imports or migrations:

```sql
SELECT COUNT(*) AS orphan_order_items
FROM order_items oi
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.order_id = oi.order_id
);
```

And check currency references:

```sql
SELECT COUNT(*) AS invalid_product_currency
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM currencies c
    WHERE c.currency_code = p.currency_code
);
```

The expected result for both queries is 0.

## 11. Understanding Constraints and Delete/Update Behavior

### 11.1. PRIMARY KEY

A primary key is both unique and not null. Every table should have a stable primary key. For `ORDER_ITEMS`, the composite key (`ORDER_ID`, `LINE_NO`) represents the line sequence within an order.

### 11.2. FOREIGN KEY

A foreign key guarantees that the referenced value exists in the parent table. By default, Oracle prevents deleting a parent row that is currently referenced. This fits order data well because order history must remain intact even when a customer or product becomes inactive.

If the business requires removing personal data, design an appropriate anonymization/retention workflow rather than cascading deletes across orders and transaction details.

### 11.3. UNIQUE

A unique constraint guarantees no two rows share duplicate values across the constraint columns. Oracle allows multiple `NULL` values in a unique constraint under Oracle semantics; if a column must have a value, combine it with `NOT NULL` as shown in the email and SKU examples.

### 11.4. CHECK

Check constraints are appropriate for row-level rules such as `quantity > 0`, `unit_price >= 0`, or status membership in an allowed list. In Oracle, a check expression evaluating to UNKNOWN due to `NULL` does not cause the constraint to fail; therefore, add a separate `NOT NULL` constraint when a value is required.

Do not put cross-table rules or queries against other data inside a check constraint. Use FKs, unique constraints, controlled triggers, or transaction/service logic depending on the rule type.

### 11.5. Order Status

`CHECK` only restricts the set of allowed values; it does not enforce state transition order. For example, a `CANCELLED` order should not transition back to `SHIPPED` if business rules forbid it. State transition rules should be enforced in the service layer or stored procedure with proper concurrency and transaction control.

## 12. Creating an Order in a Single Transaction

Creating an order typically requires:

1. Verifying that the customer exists and is active.
2. Verifying that the product exists, is active for sale, and has a matching price/currency.
3. Creating the `ORDERS` header.
4. Creating each `ORDER_ITEMS` row with the snapshot price.
5. Updating inventory or recording a stock reservation, if applicable.
6. Committing everything or rolling back if any mandatory step fails.

In a Java/JDBC application, the transaction boundary should encompass both the header and all line items. Do not commit the header first and then insert the lines if the business requires an order to have complete line details.

Example PL/SQL block illustrating creating a header and a line item in a single transaction block (ID assigned via sequence):

```sql
DECLARE
    l_order_id    orders.order_id%TYPE;
    l_customer_id customers.customer_id%TYPE;
    l_product_id  products.product_id%TYPE;
    l_price       products.unit_price%TYPE;
BEGIN
    SELECT customer_id
    INTO l_customer_id
    FROM customers
    WHERE email = 'an@example.com';

    INSERT INTO orders (
        order_number, customer_id, currency_code,
        order_status, shipping_address
    )
    VALUES (
        'ORD-2026-0003', l_customer_id, 'USD',
        'PENDING', '12 Nguyen Hue, Ho Chi Minh City'
    )
    RETURNING order_id INTO l_order_id;

    SELECT product_id, unit_price
    INTO l_product_id, l_price
    FROM products
    WHERE sku = 'KB-001'
      AND is_active = 'Y';

    INSERT INTO order_items (
        order_id, line_no, product_id,
        quantity, unit_price, discount_amount
    )
    VALUES (
        l_order_id, 1, l_product_id,
        1, l_price, 0
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

The `ORDERS_BIR` trigger assigns `ORDER_ID` before the insert, so `RETURNING` receives the generated ID. The example block creates only one line item for illustration. In an application handling concurrent requests, use bind parameters and a transaction manager/JDBC rather than concatenating values into SQL strings.

If a procedure is called inside an application-managed transaction, agree clearly on who owns commit/rollback. A stored procedure should not issue its own commit if the caller needs to combine it with other operations in a larger transaction.

## 13. Synchronizing Sequences After Importing Data with Explicit IDs

When importing or loading data from a source that already contains IDs, the sequence may lag behind `MAX(ID)` in the table. If the trigger continues fetching `NEXTVAL`, new inserts can collide with existing primary keys.

Check the current maximums:

```sql
SELECT MAX(customer_id) AS max_customer_id FROM customers;
SELECT MAX(product_id)  AS max_product_id  FROM products;
SELECT MAX(order_id)    AS max_order_id    FROM orders;
```

Then synchronize the sequences using a controlled DBA procedure. Do not modify data dictionary tables directly. For an existing sequence, you can temporarily adjust its increment to reach the target value and then reset `INCREMENT BY` back to 1, or recreate the sequence according to an appropriate procedure. Stop writers during synchronization to avoid race conditions.

For Oracle versions supporting identity columns, managing the internal sequence differs; follow the corresponding Oracle documentation rather than applying external sequence/trigger tricks.

## 14. Deploying the Schema via Migration Scripts

### 14.1. Separating DDL and Seed Data

A migration directory structure might look like this:

```text
db/migration/
  V001__create_currencies.sql
  V002__create_customers.sql
  V003__create_products.sql
  V004__create_orders.sql
  V005__create_order_items.sql
  V006__create_sequences_and_triggers.sql
  V007__create_indexes_and_views.sql
  R__reference_data.sql
```

File names and syntax depend on whether the project chooses Flyway or Liquibase. Splitting migrations in dependency order makes changes easier to review, test, and track.

### 14.2. DDL in Oracle Performs Implicit Commits

Oracle executes an implicit commit before and after many DDL statements. Therefore, do not assume `ROLLBACK` can undo `CREATE TABLE`, `CREATE SEQUENCE`, `CREATE TRIGGER`, or `ALTER TABLE` the way it undoes DML. Migration tools need separate state tracking and recovery procedures for DDL.

### 14.3. Creating Users and Privileges

The DBA can create the schema owner, allocate tablespace quota, and grant the required object-creation privileges. Illustrative example (tablespace and password must follow organizational standards):

```sql
CREATE USER order_app IDENTIFIED BY "use-secret-manager-instead";
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE,
      CREATE TRIGGER, CREATE VIEW TO order_app;
ALTER USER order_app QUOTA 500M ON app_data;
```

The password in the example is only a placeholder and must never be used in production. Do not grant overly broad privileges such as `DBA` or `UNLIMITED TABLESPACE` just to run migrations. Separate the deployment schema owner from the runtime account if your security architecture requires it.

## 15. Common Errors

| Error | Possible Cause | Resolution |
|---|---|---|
| `ORA-00955: name is already used` | A table, sequence, index, or trigger with the same name already exists. | Check existing objects; use versioned migrations instead of re-running ad-hoc scripts. |
| `ORA-00942: table or view does not exist` | Created in the wrong order, wrong schema, or missing privileges. | Verify owner, current schema, and created objects. |
| `ORA-02270` | Referenced column in FK lacks a matching unique/primary key. | Create PK/UNIQUE on the parent table before creating the FK. |
| `ORA-02291` | Inserting a child row referencing a nonexistent parent key. | Insert parent data first or fix the referenced ID. |
| `ORA-02292` | Deleting a parent row that still has referencing child rows. | Preserve history, delete via business workflow, or handle child rows safely. |
| `ORA-00001` | Primary key/unique violation. | Check for duplicate email, SKU, order number, or an out-of-sync sequence. |
| `ORA-01400` | Insert missing a `NOT NULL` column. | Provide a value or an appropriate default. |
| `ORA-02290` | Check constraint violation. | Check status, quantity, price, discount, and NULL values. |
| `ORA-04098` | Trigger is INVALID or revalidation failed. | Query `USER_ERRORS`, fix the trigger, and recompile. |
| `ORA-04091` | Mutating table error in a row-level trigger. | Do not query the table currently being modified from a row trigger; move logic to an appropriate design. |
| `ORA-01031` | Insufficient privileges to create objects or execute packages. | Have the DBA grant least-privilege permissions as required. |

When a trigger only fetches `NEXTVAL`, it does not query the table being inserted into, thereby avoiding mutating table errors. Do not turn triggers into a container for complex business logic.

## 16. Practice Exercises

After running the schema and sample data scripts, complete the following exercises:

1. Insert a new customer and verify that the trigger auto-generates `CUSTOMER_ID`.
2. Insert one VND product and one USD product; verify that the currency must exist.
3. Create an order with two line items; store snapshot unit prices.
4. Attempt to insert a line item with `QUANTITY = 0`; verify that the check constraint rejects it.
5. Attempt to insert `ORDER_STATUS = 'UNKNOWN'`; verify that the check constraint rejects it.
6. Attempt to create two customers with the same email; verify that the unique constraint rejects it.
7. Attempt to delete a product already referenced in `ORDER_ITEMS`; verify that the foreign key protects order history.
8. Update a catalog price and verify that existing orders retain their original `ORDER_ITEMS.UNIT_PRICE`.
9. Write a revenue query grouped by product and currency; do not sum USD and VND together.
10. Test calling `orders_seq.NEXTVAL` directly and check `CURRVAL` within the same session.
11. Create an additional view showing each customer, order count, and total order value per currency.
12. Write a new migration adding a `CANCEL_REASON` column and an appropriate constraint for cancelled orders.

## 17. Post-Creation Schema Verification Checklist

The queries below verify object status and data after executing the scripts:

```sql
SELECT table_name
FROM user_tables
WHERE table_name IN (
    'CURRENCIES', 'CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS'
)
ORDER BY table_name;
```

```sql
SELECT sequence_name, increment_by, cache_size, cycle_flag
FROM user_sequences
WHERE sequence_name IN ('CUSTOMERS_SEQ', 'PRODUCTS_SEQ', 'ORDERS_SEQ')
ORDER BY sequence_name;
```

```sql
SELECT trigger_name, table_name, status
FROM user_triggers
WHERE trigger_name IN ('CUSTOMERS_BIR', 'PRODUCTS_BIR', 'ORDERS_BIR')
ORDER BY trigger_name;
```

```sql
SELECT 'CUSTOMERS' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'PRODUCTS', COUNT(*) FROM products
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM order_items;
```

The schema is complete when all tables, constraints, sequences, triggers, indexes, and views exist in a valid state; sample data links properly; aggregation queries return sensible results; and rule-violating operations are rejected by the database.

## Conclusion

An order management schema should clearly separate customers, products, order headers, and order line items. Primary keys, foreign keys, unique constraints, check constraints, and not null constraints protect data integrity, while sequences combined with triggers safely generate IDs under concurrent inserts. Sample data demonstrates creating parent records first, followed by orders and line items with snapshot pricing. In production deployments, manage DDL with versioned migrations, enforce least-privilege access, preserve order history, and calculate totals separately per currency. A schema is only truly reliable once its constraints are verified and business queries and transactions execute correctly on Oracle.
