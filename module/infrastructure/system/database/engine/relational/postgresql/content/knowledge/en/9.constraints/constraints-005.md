# FOREIGN KEY and Referential Integrity in PostgreSQL

In a sales system, every order must belong to a real customer, and every order line must reference an existing order and an existing product. If a developer inserts an order with `customer_id = 999` when no such customer exists, the data becomes an **orphan record**. If someone deletes a product that has already been sold, do historical order lines remain valid? These are problems of **referential integrity**.

PostgreSQL solves this class of problems with **`FOREIGN KEY`**: one or more columns in a **child** table must reference a valid key in a **parent** table, except where `NULL` values are permitted by the constraint's rules. A foreign key is not just for drawing ER diagrams—PostgreSQL enforces it during data writes and coordinates it with transactions, locks, and `ON DELETE`/`ON UPDATE` actions.

This lesson covers how to declare foreign keys, sample data for verification, what happens when parent records are deleted or updated, multi-column foreign keys, `MATCH SIMPLE`/`MATCH FULL`, `DEFERRABLE`, adding foreign keys to large tables via `NOT VALID`, indexing concerns, and error handling. Examples target modern PostgreSQL and run in a **dedicated practice schema**. Statements designed to fail intentionally are clearly marked; do not run them in production.

## 1. Objectives and Relational Model

After this lesson, you should be able to:

1. Identify the **referencing/child table** and the **referenced/parent table**.
2. Create column-level and table-level `FOREIGN KEY` constraints and explain how they differ from `PRIMARY KEY`, `UNIQUE`, and `CHECK`.
3. Know when PostgreSQL rejects `INSERT`, `UPDATE`, and `DELETE` with SQLSTATE `23503`.
4. Choose the right `ON DELETE`/`ON UPDATE` action rather than defaulting to `CASCADE` everywhere.
5. Understand how `NULL` and multi-column foreign keys affect integrity.
6. Use `DEFERRABLE` when temporarily reordering operations within the **same transaction**, while still validating before commit.
7. Inspect constraint metadata, find orphan references in legacy data, and manage the performance impact of related operations.

### 1.1. Example Schema Diagram

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : ordered_product

    CUSTOMERS {
        bigint customer_id PK
        text customer_code UK
        text full_name
    }
    PRODUCTS {
        bigint product_id PK
        text sku UK
        numeric list_price
    }
    ORDERS {
        bigint order_id PK
        text order_no UK
        bigint customer_id FK
        text order_status
    }
    ORDER_ITEMS {
        bigint order_id PK,FK
        bigint product_id PK,FK
        integer quantity
        numeric unit_price
    }
~~~

Each customer can place many orders. Each order can contain many order lines. A product can appear in many orders; the `order_items` table turns the **many-to-many** relationship between orders and products into two one-to-many relationships.

**The foreign key lives on the child table.** For example:

~~~text
customers.customer_id  <---- orders.customer_id
  parent primary key             child foreign key

orders.order_id         <---- order_items.order_id
products.product_id     <---- order_items.product_id
~~~

The primary key of `order_items` is the **pair `(order_id, product_id)`**. That prevents the same product from appearing twice in the same order, while allowing it to appear across many different orders.

## 2. What Does a FOREIGN KEY Actually Guarantee?

A basic declaration:

~~~sql
CREATE TABLE child (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL
        REFERENCES parent(parent_id)
);
~~~

Suppose `parent.parent_id` is the primary key. When inserting a child row with `parent_id = 15`, PostgreSQL requires **a parent row with key 15 to exist**. If none exists, the write fails.

Integrity is checked on both directions of change:

- **Inserting/updating the child table:** does the row reference an existing parent key?
- **Deleting/updating a key in the parent table:** what happens to child rows that still point to that key?

Because the constraint lives inside the database, it protects data even when multiple applications, batch jobs, or `psql` sessions write concurrently. Checking via a `SELECT` in application code before `INSERT` is vulnerable: between the two queries, another transaction can modify the parent row; application-side checks **do not replace** database foreign keys.

### 2.1. How FOREIGN KEY Differs from Other Constraints

| Constraint | What It Checks | Example |
| --- | --- | --- |
| `PRIMARY KEY` | Unique, non-`NULL` row identifier for a table | `customers.customer_id` |
| `UNIQUE` | Non-duplicate value or combination per unique semantics | `products.sku` |
| `NOT NULL` | Column must hold a non-`NULL` value | `orders.customer_id` |
| `CHECK` | Conditional expression over row values | `quantity > 0` |
| **`FOREIGN KEY`** | Child column(s) point to a valid key in the parent table | `orders.customer_id → customers.customer_id` |

A `FOREIGN KEY` **does not guarantee** that every customer has an order, or that every order has at least one line item. It enforces **child pointing to parent**, not that a parent must have children.

### 2.2. Rules Outside the Scope of FOREIGN KEY

A foreign key does not automatically verify:

- Payment total equals the sum of order lines.
- A `PAID` order must have line items and full payment collected.
- Product inventory is sufficient.
- A customer places at most three orders per day.
- A product category hierarchy has no parent-child cycles.

Those rules require other constraints, transactions, triggers, exclusion constraints, or properly designed business logic.

## 3. Creating a Practice Schema with Foreign Keys

Run the commands below **once in a lab database with a fresh schema**. Do not use a production schema. If `fk_lab_119` already exists and holds data, pick a different practice schema name instead of dropping it carelessly.

### 3.1. Creating Parent Tables: customers and products

~~~sql
CREATE SCHEMA fk_lab_119;

CREATE TABLE fk_lab_119.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL
        CHECK (list_price > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

Here explicit `BIGINT` IDs are inserted so the sample data is easy to trace. In real applications, IDs are typically generated via `GENERATED ... AS IDENTITY` or an equivalent stable mechanism; foreign key semantics remain identical.

### 3.2. Creating orders with a FOREIGN KEY

~~~sql
CREATE TABLE fk_lab_119.orders (
    order_id BIGINT PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'NEW',
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT orders_status_check
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);
~~~

`CONSTRAINT fk_orders_customer` is our chosen **constraint name**. Clear names help when reading error messages, writing migrations, and querying system catalogs.

`ON DELETE RESTRICT` means a customer cannot be deleted while orders still reference them. `ON UPDATE RESTRICT` prevents modifying the customer key in a way that breaks those links. In transactional systems, **key IDs usually never need to change**; if a customer changes their name or email, update those attributes rather than changing `customer_id`.

### 3.3. Creating order_items with Two Foreign Keys

~~~sql
CREATE TABLE fk_lab_119.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price > 0),

    CONSTRAINT order_items_pk
        PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES fk_lab_119.orders (order_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES fk_lab_119.products (product_id)
        ON DELETE RESTRICT
);
~~~

This table intentionally uses **two different deletion policies**:

- `fk_items_order ON DELETE CASCADE`: if an **order** is explicitly deleted, its child order items are deleted along with it.
- `fk_items_product ON DELETE RESTRICT`: if a **product** appears in order items, that product cannot be deleted.

This is a **teaching model** to observe each action. In production, physical deletion of orders and sales history is usually tightly restricted for accounting, auditing, and recovery reasons. `CASCADE` should not be applied blindly to transactional history.

### 3.4. Loading Sample Data

~~~sql
INSERT INTO fk_lab_119.customers
    (customer_id, customer_code, full_name)
VALUES
    (1, 'C001', 'Nguyen An'),
    (2, 'C002', 'Tran Binh'),
    (3, 'C003', 'Le Chi');

INSERT INTO fk_lab_119.products
    (product_id, sku, product_name, list_price)
VALUES
    (10, 'BOOK-01', 'PostgreSQL Book', 150000.00),
    (20, 'PEN-01', 'Blue Ballpoint Pen', 20000.00),
    (30, 'MOUSE-01', 'Wireless Mouse', 280000.00);

INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id, order_status)
VALUES
    (100, 'SO-100', 1, 'PAID'),
    (200, 'SO-200', 2, 'NEW');

INSERT INTO fk_lab_119.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (100, 10, 2, 150000.00),
    (100, 20, 3,  20000.00),
    (200, 30, 1, 280000.00);
~~~

Every foreign key is valid: customers `1` and `2` exist; orders `100` and `200` exist; products `10`, `20`, and `30` exist.

### 3.5. Verifying Seed Results

~~~sql
SELECT
    (SELECT COUNT(*) FROM fk_lab_119.customers) AS customers,
    (SELECT COUNT(*) FROM fk_lab_119.products) AS products,
    (SELECT COUNT(*) FROM fk_lab_119.orders) AS orders,
    (SELECT COUNT(*) FROM fk_lab_119.order_items) AS order_items;
~~~

Expected counts: **3 customers, 3 products, 2 orders, 3 order items**.

~~~sql
SELECT
    o.order_no,
    c.customer_code,
    c.full_name,
    COUNT(oi.product_id) AS line_count,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS order_total
FROM fk_lab_119.orders AS o
JOIN fk_lab_119.customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN fk_lab_119.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id, o.order_no, c.customer_code, c.full_name
ORDER BY o.order_id;
~~~

| Order | Customer | Line Items | Total Amount |
| --- | --- | ---: | ---: |
| `SO-100` | `C001` | 2 | 360.000 |
| `SO-200` | `C002` | 1 | 280.000 |

Historical unit price is stored in `order_items.unit_price` rather than recomputed from `products.list_price` after catalog price changes. `LEFT JOIN` ensures orders with zero lines still appear; a foreign key does not force an order to have line items.

## 4. Three Ways to Write a FOREIGN KEY

### 4.1. Column-Level Syntax

When the foreign key consists of a single column:

~~~sql
CREATE TABLE fk_lab_119.simple_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES fk_lab_119.customers (customer_id)
);
~~~

The `REFERENCES` clause immediately follows the column definition. Omitting `ON DELETE` defaults to `NO ACTION`.

### 4.2. Table-Level Syntax

~~~sql
CREATE TABLE fk_lab_119.simple_orders_2 (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_simple_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers (customer_id)
);
~~~

Table-level syntax is convenient for multi-column keys, explicit constraint naming, or adding `MATCH`/`ON DELETE`/`DEFERRABLE` clauses.

**Create only one of these two example tables if you want to test**; `simple_orders` and `simple_orders_2` are extra tables not used in the main dataset.

### 4.3. Adding a Foreign Key with ALTER TABLE

When the child table already exists:

~~~sql
ALTER TABLE fk_lab_119.simple_orders
ADD CONSTRAINT fk_simple_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers (customer_id);
~~~

This assumes `simple_orders` from Section 4.1 was created **without the inline constraint**. If you ran the exact DDL in Section 4.1, the table already has an equivalent FK; adding another creates a redundant duplicate constraint with unnecessary overhead. To demonstrate `ALTER TABLE` cleanly on an existing table, use a new table **without an FK yet**:

~~~sql
CREATE TABLE fk_lab_119.import_orders (
    import_order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

ALTER TABLE fk_lab_119.import_orders
ADD CONSTRAINT fk_import_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers (customer_id);
~~~

When adding an FK normally, PostgreSQL verifies all existing child rows. If orphan rows exist, adding the constraint fails. The `NOT VALID` workflow for large historical tables is covered in Section 13.

## 5. The Referenced Key Must Have Appropriate Uniqueness

An FK cannot reference **just any column that may contain duplicates**. PostgreSQL requires a parent key guaranteeing each referenced key tuple maps cleanly to a valid parent record as required.

Typically the target is:

- The parent table's `PRIMARY KEY`; or
- Columns with a **non-deferrable `UNIQUE` constraint**; or
- Columns covered by a qualifying **non-partial unique index**.

Example of an FK pointing to a **unique business code**:

~~~sql
CREATE TABLE fk_lab_119.customer_notes (
    note_id BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL,
    content TEXT NOT NULL,

    CONSTRAINT fk_notes_customer_code
        FOREIGN KEY (customer_code)
        REFERENCES fk_lab_119.customers (customer_code)
);
~~~

Because `customers.customer_code` has `UNIQUE`, it can be referenced. Even so, business codes change more often than surrogate IDs; evaluate `ON UPDATE` and data lifecycle before using one as an FK target.

### 5.1. Why Not Reference a Name Column?

If a customer's name is `Nguyen An`, multiple people can share that name. An FK to `full_name` lacks uniqueness and cannot reliably identify the intended customer. **Do not force a unique constraint onto a display name just to satisfy a foreign key** if the domain allows duplicate names.

### 5.2. A Partial Unique Index Cannot Serve as a General FK Target

A conditional unique index:

~~~sql
-- Conceptual example:
-- CREATE UNIQUE INDEX uq_active_sku
-- ON products(sku) WHERE is_active;
~~~

only guarantees uniqueness for rows matching `WHERE`. It is **not sufficient** for a general FK referencing `sku` across all states because rows outside the predicate are not constrained as required by an FK. An FK target needs a full, non-partial unique key or index.

### 5.3. Column Types and Order Must Be Compatible

PostgreSQL must have a compatible equality operator between the FK value and the parent key. Do not arbitrarily mismatch data types or collations expecting the FK to cast everything safely. For new schemas, keep child columns on the same logical type as the parent key—for example, both `BIGINT`.

In multi-column keys, **column pairing is determined by declaration order**. Mixing up the order makes the constraint invalid or checks the wrong columns.

## 6. Testing Foreign Key Violations on Child Writes

In the tests below, **the goal is to observe intentional errors**, not to insert new sample data. Run each test in your lab database. In PostgreSQL, a failing statement inside a transaction puts the transaction into an aborted state; use `ROLLBACK` or `ROLLBACK TO SAVEPOINT` before continuing.

### 6.1. INSERT with Nonexistent customer_id

~~~sql
BEGIN;
SAVEPOINT before_invalid_insert;

INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id)
VALUES
    (900, 'SO-INVALID-900', 999);
-- Expected: ERROR, SQLSTATE 23503 (foreign_key_violation).

ROLLBACK TO SAVEPOINT before_invalid_insert;
ROLLBACK;
~~~

Customer `999` does not exist. PostgreSQL rejects the order row before the transaction can commit a broken reference.

A typical error message looks like:

~~~text
ERROR:  insert or update on table "orders"
        violates foreign key constraint "fk_orders_customer"
DETAIL: Key (customer_id)=(999) is not present in table "customers".
SQLSTATE: 23503
~~~

Exact wording or schema qualification can vary by client, version, and context. `23503` is the SQLSTATE code applications use to classify referential errors.

### 6.2. UPDATE an FK Column to a Nonexistent Key

~~~sql
BEGIN;
SAVEPOINT before_invalid_update;

UPDATE fk_lab_119.orders
SET customer_id = 999
WHERE order_id = 100;
-- Expected: SQLSTATE 23503.

ROLLBACK TO SAVEPOINT before_invalid_update;
ROLLBACK;
~~~

Not only `INSERT`, but `UPDATE` changing an FK must also maintain valid references. After rollback, order `100` still belongs to customer `1`.

### 6.3. INSERT an Order Item with a Nonexistent Product

~~~sql
BEGIN;
SAVEPOINT before_invalid_item;

INSERT INTO fk_lab_119.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (100, 999, 1, 100000.00);
-- Expected: SQLSTATE 23503 from fk_items_product.

ROLLBACK TO SAVEPOINT before_invalid_item;
ROLLBACK;
~~~

Order `100` exists, but product `999` does not. **A row with multiple FKs must satisfy all of them.** If both order and product are missing, do not rely on PostgreSQL “always reporting one FK before the other” in business logic.

### 6.4. Distinguishing FK Errors from Other Errors

| SQLSTATE | Typical Error | Example |
| --- | --- | --- |
| `23503` | `foreign_key_violation` | Referenced customer does not exist |
| `23505` | `unique_violation` | Duplicate `order_no` or duplicate PK |
| `23502` | `not_null_violation` | `orders.customer_id = NULL` |
| `23514` | `check_violation` | `quantity = 0` |

Java applications using PostgreSQL JDBC can read SQLSTATE via `SQLException.getSQLState()` and map it to an appropriate business error. Never return raw SQL error messages containing internal database details on public APIs.

**Practice note:** some clients or `psql` scripts configured to stop on first error will not execute the subsequent `ROLLBACK TO SAVEPOINT` lines automatically. In that case, roll back manually or let your test framework catch the exception and manage the transaction.

## 7. Deleting Parent Rows: NO ACTION, RESTRICT, CASCADE, SET NULL, SET DEFAULT

An FK relationship must specify behavior when a parent key is **deleted or modified**. PostgreSQL provides five main actions:

| Action | When Parent Key Is Deleted / Updated | Typical Use Case |
| --- | --- | --- |
| `NO ACTION` | Rejects if invalid references remain at check time; the default action | Preserving references; can combine with deferrability where allowed |
| `RESTRICT` | Rejects changes affecting a referenced parent row under immediate check rules | Protecting history against parent deletion or key changes |
| `CASCADE` | Deletes child rows on parent delete, or updates child FK when parent key changes | Child data strictly depends on the parent's lifecycle |
| `SET NULL` | Sets child FK column(s) to `NULL` | Optional relationship; child record may remain unlinked |
| `SET DEFAULT` | Sets child FK to its declared default value | Reassigns to a valid business default record |

Actions can be declared independently:

~~~sql
FOREIGN KEY (parent_id)
REFERENCES some_schema.parent_table(id)
ON DELETE CASCADE
ON UPDATE RESTRICT
~~~

Never assume `ON DELETE` defaults to `CASCADE`. In PostgreSQL, the default is **`NO ACTION`**.

### 7.1. RESTRICT: Protecting Customers with Existing Orders

In our schema:

~~~sql
CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
ON DELETE RESTRICT
~~~

Test:

~~~sql
BEGIN;
SAVEPOINT before_delete_customer;

DELETE FROM fk_lab_119.customers
WHERE customer_id = 1;
-- Expected: SQLSTATE 23503, because order 100 references customer 1.

ROLLBACK TO SAVEPOINT before_delete_customer;
ROLLBACK;
~~~

Because order `SO-100` still exists, PostgreSQL refuses to delete customer `C001`. This is the right choice when transaction history must be preserved and physical deletion of active customers is forbidden.

### 7.2. CASCADE: Deleting Line Items When an Order Is Deleted

`order_items.order_id` is declared `ON DELETE CASCADE`. Test inside a transaction and roll back:

~~~sql
BEGIN;

SELECT COUNT(*) AS before_delete
FROM fk_lab_119.order_items
WHERE order_id = 100;
-- 2

DELETE FROM fk_lab_119.orders
WHERE order_id = 100;
-- Deletes order 100 and automatically deletes its two line items.

SELECT COUNT(*) AS after_delete
FROM fk_lab_119.order_items
WHERE order_id = 100;
-- 0 inside the current transaction.

ROLLBACK;
~~~

After rollback, both order `100` and its two line items are restored. `DELETE FROM orders` is not blocked by `customers` here because we are **deleting from the child table `orders`** in the customer–order relation, while `CASCADE` triggers down the order–items relation.

**Caution:** `CASCADE` can propagate across multiple levels of relationships. A `DELETE` with a bad `WHERE` clause can wipe large volumes of dependent data, causing heavy load and long locks. On important tables, consider soft deletes, archival policies, and whether historical records should ever be physically deleted.

### 7.3. RESTRICT Protecting Products Referenced in Orders

~~~sql
BEGIN;
SAVEPOINT before_delete_product;

DELETE FROM fk_lab_119.products
WHERE product_id = 10;
-- Expected: SQLSTATE 23503 from fk_items_product.

ROLLBACK TO SAVEPOINT before_delete_product;
ROLLBACK;
~~~

Product `10` appears in order `100`. When a business discontinues a product, updating `is_active = FALSE` while keeping the record so historical sales remain intact is usually much better:

~~~sql
BEGIN;

UPDATE fk_lab_119.products
SET is_active = FALSE
WHERE product_id = 10;

ROLLBACK;
~~~

An FK does not prevent referencing an `is_active = FALSE` product. If only active products may be sold, the application must enforce that business check inside the transaction or via an appropriate control mechanism.

### 7.4. SET NULL: Optional Relationships

Suppose an article has an assigned editor, yet if that editor leaves the system the article should remain:

~~~sql
CREATE TABLE fk_lab_119.editors (
    editor_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    editor_id BIGINT NULL,
    CONSTRAINT fk_articles_editor
        FOREIGN KEY (editor_id)
        REFERENCES fk_lab_119.editors(editor_id)
        ON DELETE SET NULL
);
~~~

When the editor is deleted, `articles.editor_id` becomes `NULL`. **The column must allow `NULL`** for this action to succeed. If the column is `NOT NULL`, setting `NULL` fails; PostgreSQL does not override `NOT NULL`.

For composite foreign keys, modern PostgreSQL versions provide syntax to set only selected columns to `NULL` on `ON DELETE` when needed; use that specialized feature carefully to preserve other required columns.

### 7.5. SET DEFAULT: The Default Value Must Still Be a Valid Reference

Suppose deleting an owning group reassigns documents to an “Uncategorized” group with ID 0:

~~~sql
CREATE TABLE fk_lab_119.groups (
    group_id BIGINT PRIMARY KEY,
    group_name TEXT NOT NULL
);

INSERT INTO fk_lab_119.groups(group_id, group_name)
VALUES (0, 'Uncategorized');

CREATE TABLE fk_lab_119.group_documents (
    document_id BIGINT PRIMARY KEY,
    group_id BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_documents_group
        FOREIGN KEY (group_id)
        REFERENCES fk_lab_119.groups(group_id)
        ON DELETE SET DEFAULT
);
~~~

`SET DEFAULT` **does not bypass the FK**. If the default is 0 and group `0` does not exist, deleting a parent produces an invalid reference and fails. If the column has no `DEFAULT`, its implicit default is `NULL`, which must also satisfy `NOT NULL` and other constraints.

### 7.6. Choosing Deletion Policies by Data Semantics

| Business Relationship | Likely Policy | What to Evaluate |
| --- | --- | --- |
| Customer → placed orders | `RESTRICT`/`NO ACTION` | Never accidentally erase history or accounting data |
| Draft order → temporary cart lines | `CASCADE` | Child lines have no independent meaning |
| Assignee → article | `SET NULL` | Can an article exist unassigned? |
| Category → document | `SET DEFAULT` | Does a valid default record exist? |
| Product → sales history | `RESTRICT` or soft-discontinue | Historical SKU and prices must remain intact |

Do not make every relationship `CASCADE` just for “convenient cleanup”. Base the choice on **entity lifecycle and history retention requirements**.

## 8. ON UPDATE: When a Parent Key Changes

`ON UPDATE` triggers when **the referenced key value in the parent table changes**. Updating an ordinary non-key column (such as `full_name`) does not trigger FK updates.

Example:

~~~sql
CREATE TABLE fk_lab_119.regions (
    region_code TEXT PRIMARY KEY,
    region_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.stores (
    store_id BIGINT PRIMARY KEY,
    region_code TEXT NOT NULL,
    CONSTRAINT fk_stores_region
        FOREIGN KEY (region_code)
        REFERENCES fk_lab_119.regions(region_code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

INSERT INTO fk_lab_119.regions
    (region_code, region_name)
VALUES ('NORTH', 'North Region');

INSERT INTO fk_lab_119.stores
    (store_id, region_code)
VALUES (1, 'NORTH');
~~~

Changing the region code inside a transaction:

~~~sql
BEGIN;

UPDATE fk_lab_119.regions
SET region_code = 'NORTH-V2'
WHERE region_code = 'NORTH';

SELECT store_id, region_code
FROM fk_lab_119.stores
WHERE store_id = 1;
-- Store 1's region_code has become NORTH-V2.

ROLLBACK;
~~~

`ON UPDATE CASCADE` automatically propagates the new parent key to child rows. However, mutating primary keys or widely referenced business codes can be expensive, lock many rows, and affect external systems; with immutable surrogate keys, frequent update cascades are rarely needed.

## 9. NO ACTION Differs from RESTRICT in Check Timing

In most ordinary situations, both `NO ACTION` and `RESTRICT` reject a `DELETE` when child rows remain. The key difference is **deferrability**.

- **`NO ACTION`** is the default. When non-deferrable or currently immediate, it checks at statement check time. If the FK is `DEFERRABLE` and currently deferred, validating the reference can be postponed until transaction end.
- **`RESTRICT`** does not allow deferring **that restriction check** in the same way; PostgreSQL blocks deleting or updating a referenced parent row immediately in the action's context.
- **`CASCADE`/`SET NULL`/`SET DEFAULT`** are referential actions that modify child data. Do not assume those actions are postponed until `COMMIT` merely because the constraint is declared `DEFERRABLE`.

### 9.1. When Deferred Checking Is Needed

Suppose you want to move relationships from an old parent key to a new parent key within the **same transaction**. At an intermediate point, references may be temporarily invalid, yet by transaction end every reference is resolved.

With `NO ACTION DEFERRABLE`, the application can run `SET CONSTRAINTS ... DEFERRED` to postpone eligible checks. `RESTRICT` is not suitable if the intent is to allow a temporarily invalid referential state inside the transaction.

**This is not a way to commit orphan data.** Deferring only changes **when the check happens**, never removing the integrity rule.

## 10. DEFERRABLE and SET CONSTRAINTS Inside a Transaction

PostgreSQL allows certain constraints, including foreign keys, to be declared:

~~~sql
DEFERRABLE INITIALLY IMMEDIATE
~~~

or:

~~~sql
DEFERRABLE INITIALLY DEFERRED
~~~

| Declaration | Default Check Timing | Can Change via SET CONSTRAINTS? |
| --- | --- | --- |
| `NOT DEFERRABLE` | Immediate | No |
| `DEFERRABLE INITIALLY IMMEDIATE` | Immediate | Yes, to deferred within a transaction |
| `DEFERRABLE INITIALLY DEFERRED` | Deferred | Yes, to immediate within a transaction |

### 10.1. Dedicated Example for Testing a Deferred FK

~~~sql
CREATE TABLE fk_lab_119.deferred_parents (
    parent_id BIGINT PRIMARY KEY
);

CREATE TABLE fk_lab_119.deferred_children (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT fk_deferred_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES fk_lab_119.deferred_parents(parent_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Inside a transaction:

~~~sql
BEGIN;

SET CONSTRAINTS fk_deferred_child_parent DEFERRED;

-- parent_id = 700 does not exist yet:
INSERT INTO fk_lab_119.deferred_children
    (child_id, parent_id)
VALUES (1, 700);

-- Insert parent before commit:
INSERT INTO fk_lab_119.deferred_parents(parent_id)
VALUES (700);

COMMIT;
~~~

Because the constraint was switched to deferred for this transaction and the parent row was inserted before `COMMIT`, the final state is valid.

If you omit inserting the parent, `COMMIT` is **rejected** with `23503`, so orphan data is never committed. This validates integrity **at transaction completion** rather than disabling the FK.

### 10.2. Switching from DEFERRED Back to IMMEDIATE

~~~sql
BEGIN;
SET CONSTRAINTS fk_deferred_child_parent DEFERRED;

-- Operations requiring deferred checking go here.

SET CONSTRAINTS fk_deferred_child_parent IMMEDIATE;
-- PostgreSQL immediately validates all pending deferred checks here.

ROLLBACK;
~~~

`SET CONSTRAINTS ... IMMEDIATE` retroactively checks all postponed violations. If validation fails, the mode switch fails and the application must handle the error and roll back per transaction rules.

### 10.3. When Should You Use DEFERRABLE?

Appropriate when:

- Loading data with cyclic references inside one transaction with a clear validation path.
- Swapping or restructuring relationships whose intermediate steps are temporarily inconsistent.
- Running multi-step batches where ordering varies while commit-time validity is guaranteed.

Do not mark every FK deferred just to avoid import ordering mistakes. Errors pile up at `COMMIT`, causing late rollbacks on large transactions and making the offending row harder to pinpoint. Whenever possible, loading **parents before children** is simpler.

## 11. NULL in Foreign Keys: MATCH SIMPLE and MATCH FULL

A foreign key **does not automatically forbid NULL**. When child columns allow `NULL`, referential rules depend on `MATCH`.

### 11.1. Nullable Single-Column FK

~~~sql
CREATE TABLE fk_lab_119.optional_orders (
    optional_order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL,
    CONSTRAINT fk_optional_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers(customer_id)
);

INSERT INTO fk_lab_119.optional_orders
    (optional_order_id, customer_id)
VALUES
    (1, NULL),
    (2, 1);
~~~

`customer_id = NULL` is allowed because the relationship is optional. `customer_id = 1` is allowed because customer 1 exists. `customer_id = 999` is rejected.

If business rules require **every order to have a customer**, declare `customer_id BIGINT NOT NULL` as in `orders`. `NOT NULL` blocks missing values; `FOREIGN KEY` blocks **nonexistent parent** values.

### 11.2. MATCH SIMPLE: Default for Multi-Column Foreign Keys

Suppose a foreign key references a composite key `(tenant_id, product_code)`. Under `MATCH SIMPLE`, if **at least one FK component is NULL**, the row normally does not have to satisfy existence of the pair.

This can be intentional for optional relations, but can accidentally permit “half-populated” rows (tenant present, product missing) when business rules forbid partial references.

### 11.3. MATCH FULL: Either All NULL or Entire Pair Valid

Create a parent table with a composite key:

~~~sql
CREATE TABLE fk_lab_119.tenant_products (
    tenant_id BIGINT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    CONSTRAINT tenant_products_pk
        PRIMARY KEY (tenant_id, product_code)
);

INSERT INTO fk_lab_119.tenant_products
    (tenant_id, product_code, product_name)
VALUES
    (1, 'A', 'Product A of tenant 1'),
    (2, 'A', 'Product A of tenant 2');
~~~

Child table with two nullable columns:

~~~sql
CREATE TABLE fk_lab_119.optional_tenant_items (
    item_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NULL,
    product_code TEXT NULL,
    CONSTRAINT fk_optional_tenant_product
        FOREIGN KEY (tenant_id, product_code)
        REFERENCES fk_lab_119.tenant_products
            (tenant_id, product_code)
        MATCH FULL
);
~~~

Scenarios:

| `tenant_id` | `product_code` | With MATCH FULL | Reason |
| ---: | --- | --- | --- |
| 1 | `A` | Valid | Pair (1, A) exists |
| 2 | `A` | Valid | Pair (2, A) exists |
| `NULL` | `NULL` | Valid | Entire foreign key is omitted |
| 1 | `NULL` | **Invalid** | Only part of the pair is NULL |
| `NULL` | `A` | **Invalid** | Only part of the pair is NULL |
| 1 | `X` | **Invalid** | Pair (1, X) does not exist |

Test:

~~~sql
INSERT INTO fk_lab_119.optional_tenant_items
    (item_id, tenant_id, product_code)
VALUES
    (1, 1, 'A'),
    (2, NULL, NULL);

-- In the lab, run separately to observe the error:
-- INSERT INTO fk_lab_119.optional_tenant_items
--     (item_id, tenant_id, product_code)
-- VALUES (3, 1, NULL);
~~~

`MATCH PARTIAL` appears in standard SQL syntax but **is not implemented by PostgreSQL** as a standard FK mode. In PostgreSQL, the practical options are the default **MATCH SIMPLE** and **MATCH FULL**.

### 11.4. If All Components Are Required, Use NOT NULL

When an item always belongs to a specific tenant:

~~~sql
CREATE TABLE fk_lab_119.tenant_order_items (
    tenant_id BIGINT NOT NULL,
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    CONSTRAINT fk_tenant_item_product
        FOREIGN KEY (tenant_id, product_code)
        REFERENCES fk_lab_119.tenant_products
            (tenant_id, product_code)
);
~~~

Because both columns are `NOT NULL`, the “half-NULL pair” issue disappears. The composite foreign key guarantees **product A is verified within the matching tenant**, rather than merely checking whether `product_code` exists under some other tenant.

## 12. Multi-Column Foreign Keys Protect Paired Relationships

Consider `tenant_products`:

~~~text
tenant_products
-----------------------------------------
tenant_id    product_code    product_name
1            A               Product A / tenant 1
2            A               Product A / tenant 2
~~~

If you create **two separate FKs**:

~~~text
FOREIGN KEY (tenant_id)    -> a tenant key in another table
FOREIGN KEY (product_code) -> a shared product code
~~~

both individual values might exist while the **tenant–product combination is invalid**. A composite FK:

~~~sql
FOREIGN KEY (tenant_id, product_code)
REFERENCES fk_lab_119.tenant_products(tenant_id, product_code)
~~~

validates the pair as **a single relationship**.

### 12.1. Watch Column Order Carefully

Suppose the parent key is `PRIMARY KEY (tenant_id, product_code)`. The child columns must align position by position:

~~~sql
FOREIGN KEY (tenant_id, product_code)
REFERENCES fk_lab_119.tenant_products(tenant_id, product_code)
~~~

Do not reorder child or parent columns in the FK clause just because two columns happen to share the same type in another schema. Migration tools and reviewers must match both column names and **ordinal positions**.

### 12.2. Do Not Rely on a Single ID Instead of Composite Integrity

In multi-tenant systems, `product_id` might collide across tenants if IDs are only unique per tenant. In that case, `FOREIGN KEY (product_id)` alone is insufficient. Either include `tenant_id` in the referenced key if it is part of the business identity, or use a genuinely globally unique surrogate ID for safe linking.

An FK is an important boundary, but **it does not replace tenant authorization checks**. Applications must still verify which tenant a user is allowed to access.

## 13. Adding a FOREIGN KEY to Populated Tables: NOT VALID and VALIDATE

In production, tables are often created before full constraints are applied, or hold legacy data imported from older systems. Adding an FK the standard way requires **scanning and validating all existing child rows**, incurring I/O and locking impact.

PostgreSQL supports a two-step workflow:

1. `ADD CONSTRAINT ... NOT VALID`: registers the constraint **without scanning all existing rows to verify them immediately**.
2. `VALIDATE CONSTRAINT`: after legacy data is cleaned up, PostgreSQL scans and verifies rows to mark the constraint validated.

Key point: **`NOT VALID` does not allow new writes to violate the constraint**. Once created, new writes and relevant updates are enforced by the constraint.

### 13.1. Example of Historical Data with Orphan References

Create a temporary import table without an initial FK:

~~~sql
CREATE TABLE fk_lab_119.import_lines (
    import_line_id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO fk_lab_119.import_lines
    (import_line_id, product_id, quantity)
VALUES
    (1, 10, 2),
    (2, 999, 1);  -- Bad legacy row: product 999 does not exist.
~~~

Attempting to add a fully validated FK immediately:

~~~sql
-- Illustrates a statement that fails on current data:
-- ALTER TABLE fk_lab_119.import_lines
-- ADD CONSTRAINT fk_import_lines_product
-- FOREIGN KEY (product_id)
-- REFERENCES fk_lab_119.products(product_id);
~~~

fails because the `product_id = 999` row has no parent.

### 13.2. Registering an Unvalidated Foreign Key

~~~sql
ALTER TABLE fk_lab_119.import_lines
ADD CONSTRAINT fk_import_lines_product
FOREIGN KEY (product_id)
REFERENCES fk_lab_119.products(product_id)
NOT VALID;
~~~

In PostgreSQL, the constraint now exists with **`convalidated = false`** in the catalog. Existing rows have not been scanned for verification.

Never conclude that because `ALTER TABLE ... NOT VALID` succeeded, all existing data is clean.

### 13.3. Finding Orphan Rows in Legacy Data

~~~sql
SELECT
    il.import_line_id,
    il.product_id
FROM fk_lab_119.import_lines AS il
LEFT JOIN fk_lab_119.products AS p
    ON p.product_id = il.product_id
WHERE p.product_id IS NULL
ORDER BY il.import_line_id;
~~~

This finds row `import_line_id = 2`, `product_id = 999`.

When FK columns allow `NULL`, reconciliation queries must account for `MATCH SIMPLE`/`MATCH FULL` semantics before flagging missing parents. Since `product_id` is `NOT NULL` here, a straightforward anti-join suffices.

### 13.4. Repairing Data, Then Running VALIDATE

In our lab we know row 2 should map to product 10:

~~~sql
UPDATE fk_lab_119.import_lines
SET product_id = 10
WHERE import_line_id = 2;

ALTER TABLE fk_lab_119.import_lines
VALIDATE CONSTRAINT fk_import_lines_product;
~~~

Once validation succeeds, PostgreSQL marks existing data as verified against the constraint.

In production, **do not arbitrarily replace `999` with any valid ID** just to pass the FK. Trace the source system, repair the mapping, or quarantine bad rows for business remediation. A technically valid FK pointing to the **wrong product** is still corrupted business data.

### 13.5. Why Is NOT VALID Helpful for Large Migrations?

Adding an FK with `NOT VALID` avoids scanning the entire child table while registering the constraint; `VALIDATE CONSTRAINT` can run afterward using a less disruptive lock strategy that generally interferes less with concurrent updates than adding and validating everything in one step.

However:

- `ADD CONSTRAINT` still acquires appropriate locks on both participating tables.
- `VALIDATE CONSTRAINT` still consumes I/O, CPU, locks, and time.
- On large tables, test on staging, monitor lock waits, and pick an appropriate deployment window.
- If validation fails, the constraint remains **not validated**; clean up remaining violations and retry.

**`NOT VALID` is not a way to permanently disable an FK.** It is a migration tool for transitioning cleanly from unverified legacy data to verified referential integrity.

## 14. Indexes and FOREIGN KEY Performance

An FK must look up parent keys and sometimes find **all referencing child rows** when a parent key is updated or deleted. Indexes heavily affect the cost of these operations.

### 14.1. Parent-Side Index

The parent's `PRIMARY KEY` or `UNIQUE` key already has a supporting unique index—for instance, `customers(customer_id)` has its PK index.

PostgreSQL uses that uniqueness structure to verify valid parent targets. There is no need to create a second duplicate B-tree index on `customers(customer_id)` just for the FK to work.

### 14.2. Child-Side Indexes Are Not Created Automatically for FKs

Declaring:

~~~sql
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
~~~

**does not automatically create an index on `orders(customer_id)`**. This is a critical distinction in performance design.

Why is a child-side index often helpful?

1. Application queries frequently fetch orders by customer.
2. When deleting or updating a customer key, PostgreSQL must check whether any orders still reference it.
3. If the child table has millions of rows and lacks a suitable index, those checks can incur heavy I/O.

Example:

~~~sql
CREATE INDEX idx_orders_customer_id
ON fk_lab_119.orders(customer_id);
~~~

Create this once in the lab. If the table already has an index with `customer_id` as a useful leading prefix—such as `(customer_id, ordered_at)`—a separate single-column index may be unnecessary; inspect execution plans and other queries first.

### 14.3. Checking Indexes for Both FKs on order_items

`order_items` has `PRIMARY KEY(order_id, product_id)`. Its PK B-tree index leads with `order_id`, which efficiently supports lookups by `order_id`. However, queries filtering only by `product_id` or parent-side checks looking for child rows referencing **a product** may benefit from a dedicated index:

~~~sql
CREATE INDEX idx_order_items_product_id
ON fk_lab_119.order_items(product_id);
~~~

Not every FK demands a separate index **at all costs**: indexes consume disk space, write overhead, and cache memory. Evaluate data volume, parent `DELETE`/`UPDATE` frequency, `JOIN` patterns, and actual execution plans.

### 14.4. FKs and Lock Waits

PostgreSQL must ensure a transaction cannot commit a child row pointing to a parent deleted or re-keyed by a concurrent transaction. To enforce this, it coordinates row locks and internal referential checks.

This can cause:

- Child `INSERT`s waiting on an in-flight parent key change.
- Parent `DELETE`s waiting on or scanning child rows.
- Complex multi-row updates/deletes experiencing lock contention.
- Inconsistent locking order across multiple FK tables contributing to **deadlocks**.

Never “fix” lock waits by turning off constraints. Inspect workloads, long-running transactions, missing child indexes, and application update ordering.

## 15. FOREIGN KEY in Transactions and Concurrency

A manual check:

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM fk_lab_119.customers
    WHERE customer_id = 1
);
~~~

cannot replace an FK, because after that `SELECT` finishes, another transaction could delete or alter the parent row before your code inserts the order.

### 15.1. Two Sessions Operating on the Same Parent Row

Suppose:

~~~text
Session A                         Session B
------------------------------------------------------
BEGIN
INSERT orders(customer_id=3)
                                  BEGIN
                                  DELETE customers WHERE id=3
                                  (may wait / hit FK)
COMMIT or ROLLBACK
                                  proceeds per committed outcome
~~~

PostgreSQL uses locking and referential checks so a state violating the FK can never commit. Who waits or succeeds depends on timing and transaction outcomes—never assume “my `SELECT` saw the parent, so `INSERT` is guaranteed safe”.

### 15.2. Constraints Do Not Replace Business Transactions

Suppose placing an order involves three steps:

1. Create `orders`.
2. Create `order_items`.
3. Deduct inventory.

The FK ensures line items reference valid orders and products, but **it will not automatically roll back inventory deduction if the application splits those three steps into separate transactions**. Multi-step business operations belong inside one transaction:

~~~sql
BEGIN;

-- Insert order.
-- Insert line items with valid FKs.
-- Conditionally update inventory and verify affected row count.

COMMIT;
~~~

If any required step fails, the application must roll back the entire transaction instead of committing partial state. With `DEFERRABLE` constraints, the application must also handle errors raised at `COMMIT`.

### 15.3. Deadlocks and Retries

FKs do not eliminate deadlocks. If concurrent transactions lock overlapping tables/rows in opposite orders, PostgreSQL can raise `SQLSTATE 40P01` (*deadlock_detected*). When that happens, roll back and—if the operation is safe to repeat—**retry the entire transaction** with bounded attempts and backoff.

Never blindly retry every PostgreSQL error: `23503` indicates invalid data or broken relationships, not a transient deadlock.

## 16. Scope Limits: Same Database, Cross-Schema, and Cyclic Relationships

### 16.1. Referencing Another Schema in the Same Database

~~~sql
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
~~~

When the child table lives in `app` and the parent lives in `reference` within the **same database**, cross-schema FKs are supported by PostgreSQL with appropriate privileges. Using explicit schema prefixes avoids `search_path` ambiguity.

However, PostgreSQL **does not allow standard SQL foreign keys directly across different databases** in the same instance. When data lives in separate databases or services, integrity must be managed at the integration/application layer; Foreign Data Wrappers (FDWs) do not turn cross-database links into native locally enforced FKs.

### 16.2. Self-Referencing Foreign Keys

Example category tree:

~~~sql
CREATE TABLE fk_lab_119.categories (
    category_id BIGINT PRIMARY KEY,
    parent_category_id BIGINT NULL,
    category_name TEXT NOT NULL,

    CONSTRAINT fk_category_parent
        FOREIGN KEY (parent_category_id)
        REFERENCES fk_lab_119.categories(category_id)
        ON DELETE RESTRICT
);
~~~

A root category has `parent_category_id = NULL`; child categories point to an existing category's ID.

**A self-referencing FK does not automatically prevent cycles**: for instance, A pointing to B and B pointing to A can satisfy “parent exists” if inserted/updated in a valid order. If the domain requires an acyclic tree, add ancestor/cycle detection via transactions, recursive queries, or another suitable mechanism.

### 16.3. Mutual / Cyclic References Between Two Tables

Two tables can reference each other—for example, `department` pointing to its lead `employee` and `employee` pointing to its `department`. To seed or insert data, you can:

- Create tables first and add one FK afterward via `ALTER TABLE`.
- Allow one side to be temporarily `NULL` if the model permits.
- Use a `DEFERRABLE` constraint to insert both rows in one transaction and commit once both links exist.

Do not use deferrability to commit rows missing a parent; it only lets you reorder creation/edits within the transaction.

## 17. DELETE vs. TRUNCATE: Do Not Expect ON DELETE CASCADE to Act the Same

In PostgreSQL, `DELETE FROM parent WHERE ...` removes rows individually and fires foreign key actions such as `ON DELETE CASCADE`.

By contrast, `TRUNCATE` is a table-level truncation mechanism, not a row-by-row `DELETE`. When a table is referenced by FKs from other tables, PostgreSQL normally forbids `TRUNCATE` on the parent alone unless all referencing tables are included in the truncate command or `CASCADE` is specified on `TRUNCATE` itself.

~~~sql
-- DO NOT RUN: dangerous example that can wipe all lab data.
-- TRUNCATE TABLE fk_lab_119.orders CASCADE;
~~~

`TRUNCATE ... CASCADE` **empties all dependent referencing tables completely**, rather than applying `ON DELETE` rules selectively per row like `DELETE`. Never run it in production as a “time-saver” without verifying every affected table.

### 17.1. DROP TABLE ... CASCADE Is Not ON DELETE CASCADE Either

`DROP TABLE ... CASCADE` resolves **schema-level object dependencies**. When dropping a parent table, PostgreSQL can drop the dependent FK constraint from the child table without necessarily dropping the child table itself. That is completely different from deleting child rows via `ON DELETE CASCADE`.

**Three uses of CASCADE to keep distinct:**

| Syntax | Primary Scope |
| --- | --- |
| `ON DELETE CASCADE` | Child data rows of an FK when a parent row is deleted |
| `TRUNCATE ... CASCADE` | Referencing tables truncated together with the target table |
| `DROP ... CASCADE` | Dependent catalog objects in the schema |

Never add `CASCADE` out of habit without confirming which operation and scope it triggers.

## 18. Partitioning, Inheritance, and Advanced Cases

Modern PostgreSQL supports foreign keys involving **partitioned tables**, subject to version-specific capabilities and restrictions. When adopting them, check carefully:

- Whether the FK points *to* a partitioned table or *from* a partitioned table.
- Whether unique/primary keys on the partitioned table satisfy partition-key rules.
- How attaching/detaching partitions interacts with constraint validation.
- The cost of checks, deletes, and cascades across many partitions.

Meanwhile, **traditional table inheritance** does not automatically propagate parent FK behavior identically across child tables in all directions. Do not confuse declarative partitioning with legacy inheritance when designing referential integrity.

If your project uses partitioning, test DDL on your **exact major PostgreSQL version** and partition layout; do not treat an unpartitioned FK example as proof that every partitioned topology behaves identically.

## 19. Inspecting Existing FOREIGN KEYs in a Schema

### 19.1. Using psql

In `psql`:

~~~text
\d fk_lab_119.orders
\d fk_lab_119.order_items
\d+ fk_lab_119.import_lines
~~~

`\d` is a **`psql` meta-command**, not SQL you can send verbatim over JDBC. It displays constraints, indexes, and incoming/outgoing references recorded by PostgreSQL.

### 19.2. Using information_schema

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    rc.update_rule,
    rc.delete_rule,
    rc.match_option
FROM information_schema.table_constraints AS tc
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_catalog = tc.constraint_catalog
   AND rc.constraint_schema = tc.constraint_schema
   AND rc.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'fk_lab_119'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name;
~~~

`information_schema` offers portable SQL-standard metadata, though output can be filtered by privileges and omits some PostgreSQL-specific details.

### 19.3. Using pg_catalog for Full Definitions

~~~sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    con.conname AS constraint_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    con.convalidated AS is_validated,
    pg_catalog.pg_get_constraintdef(con.oid, TRUE)
        AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE con.contype = 'f'
  AND child_ns.nspname = 'fk_lab_119'
ORDER BY child.relname, con.conname;
~~~

Key fields:

- `conrelid`: child table.
- `confrelid`: parent table.
- `contype = 'f'`: foreign key.
- `condeferrable`: whether the constraint can be deferred.
- `condeferred`: whether it starts deferred.
- `convalidated`: whether existing data has been validated against the constraint.
- `pg_get_constraintdef`: reconstructs the readable constraint definition.

### 19.4. Checking for NOT VALID Foreign Keys

~~~sql
SELECT
    child.relname AS table_name,
    con.conname,
    con.convalidated,
    pg_get_constraintdef(con.oid, TRUE) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
WHERE con.contype = 'f'
  AND ns.nspname = 'fk_lab_119'
  AND NOT con.convalidated
ORDER BY table_name, con.conname;
~~~

If `VALIDATE CONSTRAINT` succeeded in Section 13, this query will **no longer return `fk_import_lines_product`**. On large systems, tracking unvalidated FKs should be part of migration monitoring.

### 19.5. Resolving Columns on Both Sides of Composite FOREIGN KEYs

PostgreSQL records participating column numbers in `pg_constraint.conkey` and `confkey`. The query below pairs each position so column order is preserved:

~~~sql
SELECT
    child.relname AS child_table,
    con.conname AS constraint_name,
    pos.n AS pair_position,
    child_col.attname AS child_column,
    parent.relname AS parent_table,
    parent_col.attname AS parent_column
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
CROSS JOIN LATERAL
    generate_subscripts(con.conkey, 1) AS pos(n)
JOIN pg_catalog.pg_attribute AS child_col
    ON child_col.attrelid = con.conrelid
   AND child_col.attnum = con.conkey[pos.n]
JOIN pg_catalog.pg_attribute AS parent_col
    ON parent_col.attrelid = con.confrelid
   AND parent_col.attnum = con.confkey[pos.n]
WHERE con.contype = 'f'
  AND ns.nspname = 'fk_lab_119'
ORDER BY child.relname, con.conname, pos.n;
~~~

This is a reliable way to reconstruct relationship diagrams with composite foreign keys. Note that `OID` is an internal catalog identifier in the current database, not a stable business key across dev, staging, and production.

## 20. Detecting and Handling Orphan References

Once an FK is validated and not bypassed by special mechanisms, the database prevents new writes from introducing invalid references. However, legacy data or data loaded via special paths may still require auditing.

### 20.1. Anti-Join

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM fk_lab_119.orders AS o
LEFT JOIN fk_lab_119.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
~~~

On our sample data, this must return **0 rows**.

### 20.2. NOT EXISTS

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM fk_lab_119.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM fk_lab_119.customers AS c
    WHERE c.customer_id = o.customer_id
);
~~~

For `NOT NULL` FK columns, this finds orphan rows cleanly. If the FK is nullable and `NULL` means “no relationship”, exclude `NULL` rows when looking solely for **broken** references rather than **unassigned** ones.

Example:

~~~sql
-- For a nullable foreign key:
-- WHERE child.parent_id IS NOT NULL
--   AND NOT EXISTS (
--       SELECT 1 FROM parent
--       WHERE parent.id = child.parent_id
--   )
~~~

### 20.3. Do Not Patch Bad Data with Arbitrary IDs

When `customer_id = 999` is missing, possible causes include:

- Parent data has not been imported yet.
- ID mapping between old and new systems was wrong.
- The parent record was deleted before the FK existed.
- Data was loaded using a tool/process that bypassed checks.

Fix the root cause by checking source records and identifying the real parent. Reassigning broken rows to a “default customer” merely to satisfy the constraint destroys business accuracy and hides integration bugs.

## 21. Never Disable FOREIGN KEYs Casually for “Fast Imports”

In PostgreSQL, FK constraints are enforced using internal trigger mechanisms. Certain administrative settings can alter trigger or replication behavior. **Never use them as a shortcut to bypass integrity checks** in normal application workflows.

For large imports, prefer:

1. Creating target tables with proper PK/FK definitions when feasible.
2. Loading parent tables before child tables.
3. Using staging tables to cleanse data and resolve key mappings.
4. Using `NOT VALID`/`VALIDATE CONSTRAINT` in a controlled migration workflow where appropriate.
5. Batching writes, measuring locks and I/O, and logging rejected rows.
6. Reconciling counts and completing validation before trusting production data.

Mechanisms such as changing `session_replication_role` or disabling triggers can prevent normal FK checks, require elevated privileges, and risk leaving orphan data behind. Never apply them just to “get a script through” or suppress `23503` errors.

## 22. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Child `INSERT` fails with `23503` | FK value has no matching parent | Verify parent key/ID and seed order |
| Parent `DELETE` fails with `23503` | Child rows still exist under RESTRICT/NO ACTION | Find referencing child tables and count links |
| Parent key `UPDATE` fails with `23503` | Child rows point to the old key | Keep surrogate IDs immutable; avoid casual key edits |
| Adding FK fails: “no unique constraint matching” | Target lacks an eligible unique key | Check parent PK, UNIQUE, or non-partial unique index |
| Adding FK to legacy table fails | Orphan rows exist | Run anti-join, fix mappings, consider NOT VALID + VALIDATE |
| `VALIDATE CONSTRAINT` fails | Legacy violations remain | Reconcile and repair rows per business rules |
| Multi-column FK behaves unexpectedly | Wrong column order or partial NULLs | Check `MATCH`, `NOT NULL`, and child–parent pairs |
| `SET NULL` on parent delete fails | Child column is `NOT NULL` or violates another rule | Inspect child DDL and constraints |
| `SET DEFAULT` on parent delete fails | Default does not point to an existing parent | Verify default parent record and value domain |
| `CASCADE` deletes surprisingly many rows | Deep chain of dependent tables | Inspect DDL and child counts before `DELETE` |
| Parent delete is slow | Missing child index or lock contention | Check `pg_stat_activity`, indexes, child row counts |
| `ALTER TABLE ADD FK` hangs | Lock waits or scanning a huge table | Check long transactions; consider NOT VALID migration |
| `TRUNCATE` parent blocked | Dependent FKs exist even if ON DELETE is CASCADE | Distinguish `TRUNCATE` from `DELETE` |
| FK error raised only at `COMMIT` | Constraint is `DEFERRABLE DEFERRED` | Check end-of-transaction state, roll back, fix ordering |
| FK exists yet data is business-invalid | FK only checks key existence | Add business rules, transactions, and reconciliation |

### 22.1. Inspecting Constraints Stored in PostgreSQL

When an error occurs, extract the **constraint name** from the error details/SQLSTATE and query `pg_constraint` instead of guessing from table names:

~~~sql
SELECT
    con.conname,
    pg_get_constraintdef(con.oid, TRUE) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS rel
    ON rel.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'fk_lab_119'
  AND con.contype = 'f'
  AND con.conname = 'fk_orders_customer';
~~~

Clear constraint names let developers and DBAs immediately identify the active `ON DELETE` / `ON UPDATE` policy.

### 22.2. Investigating Locks During Deletes/Updates

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY pid;
~~~

A lock wait does not mean the FK itself is “broken”. Check which transaction holds the lock, how long it has been open, and which business flow caused it; never terminate production sessions without verifying impact first.

## 23. Guided Practice Exercises

### Exercise 1 — Inserting an Order with a Nonexistent Customer

Using the lab schema, try inserting `orders(customer_id=999)` and observe the SQLSTATE.

~~~sql
BEGIN;
SAVEPOINT s1;
INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id)
VALUES (901, 'SO-BAD-901', 999);
ROLLBACK TO SAVEPOINT s1;
ROLLBACK;
~~~

**Expected:** `23503` from `fk_orders_customer`. Explain why database-level FK enforcement is stronger than an application-level `SELECT`.

### Exercise 2 — Deleting a Customer Who Has Orders

Try deleting `customer_id=1` inside a transaction and explain why `RESTRICT` rejects it. Then test `customer_id=3`, who has no orders:

~~~sql
BEGIN;

DELETE FROM fk_lab_119.customers
WHERE customer_id = 3;
-- Succeeds inside the transaction because no orders reference customer 3.

ROLLBACK;
~~~

**Question:** Does an FK require every customer to have an order? Why was customer 3 allowed to exist before deletion?

### Exercise 3 — Observing CASCADE and ROLLBACK

Inside a transaction, count `order_items` for order `100`, delete order `100`, count again, and then roll back. After rollback, verify both the order and its items still exist. Explain why `CASCADE` still participates in the transaction.

### Exercise 4 — Choosing the Right Delete Action

Design policies for these relationships:

1. User → temporary login sessions.
2. Customer → issued invoices.
3. Manager → document that does not require a manager.
4. Category → records reassigned to a default category.

Choose `CASCADE`, `RESTRICT`/`NO ACTION`, `SET NULL`, or `SET DEFAULT`, and state the required column nullability or default record.

### Exercise 5 — Multi-Column Tenant Relationship

Given `tenant_products`:

~~~text
(1, A) exists
(2, A) exists
(1, X) does not exist
~~~

Try inserting `(1, X)` into `tenant_order_items`. Explain why checking `tenant_id` and `product_code` separately is insufficient and why a composite FK pair is needed.

### Exercise 6 — Comparing MATCH SIMPLE and MATCH FULL

Create a child table with nullable `tenant_id` and `product_code` using `MATCH SIMPLE`, then compare its behavior against `optional_tenant_items MATCH FULL`. Test two pairs:

~~~text
(NULL, NULL)
(1, NULL)
~~~

**Hint:** `MATCH SIMPLE` skips checking the pair if any part is NULL; `MATCH FULL` requires all components NULL or all components matching a parent row.

### Exercise 7 — Deferring an FK Until COMMIT

Using `deferred_parents` and `deferred_children`:

1. Run `SET CONSTRAINTS ... DEFERRED`.
2. Insert the child before the parent.
3. Insert the parent afterward.
4. Commit and verify the result.
5. Repeat with different IDs **without inserting the parent**, and observe the error at commit.

**Hint:** the constraint does not vanish; validity must hold by commit time.

### Exercise 8 — Adding an FK to an Existing Table

Create `import_lines` with one valid product ID and one nonexistent ID. Add the constraint `NOT VALID`, find the orphan via `LEFT JOIN` or `NOT EXISTS`, fix the data after confirming the right mapping, and run `VALIDATE CONSTRAINT`. Check `pg_constraint.convalidated` before and after.

### Exercise 9 — Deciding Indexes for FK Columns

List the indexes of `fk_lab_119.orders` and `fk_lab_119.order_items`:

~~~sql
SELECT
    schemaname, tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'fk_lab_119'
  AND tablename IN ('orders', 'order_items')
ORDER BY tablename, indexname;
~~~

Explain:

- Why doesn't `orders(customer_id)` automatically get an index just from the FK?
- Why does `PRIMARY KEY(order_id, product_id)` usually support lookups by `order_id` better than lookups by `product_id` alone?
- When should you add an extra child-side index, and what are its costs?

### Exercise 10 — Distinguishing DELETE, TRUNCATE, and DROP

Using the orders and items model, describe:

1. `DELETE FROM orders WHERE order_id=100` with `ON DELETE CASCADE`.
2. `TRUNCATE orders CASCADE`.
3. `DROP TABLE orders CASCADE`.

**Do not run the last two statements casually on valuable data.** Explain the scope of deleting **rows**, truncating **tables**, and dropping **schema objects**.

### Exercise 11 — Auditing All FOREIGN KEYs in a Schema

Query `pg_catalog.pg_constraint` filtering `contype='f'` to display child table, parent table, definition, and `convalidated`. Identify which constraint is declared `DEFERRABLE`.

**Expected:** `fk_deferred_child_parent` has `condeferrable = true`; the import constraint after successful validation has `convalidated = true`.

### Exercise 12 — Designing a Safe Data Integration Pipeline

A job receives 100,000 order lines, of which 200 reference products that do not exist yet. Propose a workflow:

1. Load raw data into staging.
2. Reconcile product codes against the parent table.
3. Separate valid rows from rows needing remediation.
4. Load missing parents if valid records are provided by a trusted source.
5. Insert valid child rows in bounded transactions/batches.
6. Reconcile row counts and constraint state.

Explain why you should neither disable the FK nor reassign all failing IDs to an arbitrary product.

## 24. Foreign Key Design Checklist

| Question Before Creating an FK | Decision to Clarify |
| --- | --- |
| Is this truly a “child must point to existing parent” relation? | An FK fits if the database can enforce that relationship |
| Does the parent key have an eligible PK/unique key? | The target must have qualifying uniqueness |
| May the child exist without a parent? | `NOT NULL` vs. nullable per business rules |
| Does the FK have multiple columns? | `MATCH SIMPLE`/`MATCH FULL` and column ordering |
| Can parent records be physically deleted? | Choose `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, or `SET DEFAULT` |
| Do parent key values ever change? | Decide `ON UPDATE`; prefer immutable IDs whenever possible |
| Are temporarily invalid states needed inside a transaction? | Consider `DEFERRABLE` deliberately |
| Does the table already contain large data? | Check for orphans, `NOT VALID`/`VALIDATE`, and lock plans |
| Is there an index supporting the FK on the child side? | Review `JOIN`s, parent deletes/updates, and existing PK/indexes |
| Do external systems depend on the data? | FKs do not replace integration contracts, events, or authorization |
| Must history be retained? | Avoid casual `CASCADE` on accounting/transactional data |
| Is there proof the constraint is validated? | Check `pg_constraint.convalidated` and migration history |

## 25. Official PostgreSQL Documentation

When working across PostgreSQL versions, verify syntax and limits against your **exact major version**:

- [PostgreSQL — Constraints / Foreign Keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK): FK declaration, referential actions, null semantics, and composite keys.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): adding, dropping, and validating constraints and locking considerations.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): deferring checks for eligible constraints.
- [PostgreSQL — pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html): FK metadata, `conkey`, `confkey`, `convalidated`, and `condeferrable`.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): interaction between transactions, locks, and data operations.

URLs with `/docs/current/` point to the current stable release documentation. If targeting a specific major version, replace `current` with the major version number to check exact behavior, especially for partitioning and extended FK features.

## 26. Summary

**`FOREIGN KEY` is the constraint that keeps child-to-parent table relationships meaningful:** a value or tuple in the child must point to a valid key in the parent according to the chosen `NULL` rules. PostgreSQL enforces it not only on child inserts, but also on child key updates, parent deletes, and parent key updates. Actions `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, and `SET DEFAULT` must be selected based on entity lifecycle and history-retention needs.

For more complex models, understand **composite foreign keys**, `MATCH SIMPLE` vs. `MATCH FULL`, and **`DEFERRABLE`** to control check timing within a transaction without sacrificing integrity at commit. For legacy systems with large tables, the **`NOT VALID` → cleanse data → `VALIDATE CONSTRAINT`** workflow enables controlled rollout. Evaluate child-side indexes carefully because PostgreSQL **does not automatically create an index solely because a column is an FK**.

Foreign keys are a vital database-layer safeguard, though they do not replace business transactions, authorization, reconciliation, or safe deletion policies. Combined properly, they let PostgreSQL keep referential integrity consistent even when many applications and transactions write concurrently.
