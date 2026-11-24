# SELECT, INSERT, UPDATE, DELETE, and Data Definition Statements

This lesson belongs to **Data Foundations** in the **Spring Framework - data-access** module. Its goal is to understand direct SQL operations before using JDBC, JdbcTemplate, Spring Data JDBC, or JPA: **SELECT** reads data, **INSERT** adds rows, **UPDATE** modifies rows, **DELETE** removes rows, and **DDL** defines and alters the structures holding data.

## 1. Recognizing Statement Groups and Scope of Impact

| Group | Representative Statements | Effect |
| --- | --- | --- |
| DQL (query; sometimes grouped with DML) | SELECT | Returns result sets from tables, joins tables, filters, groups, and sorts |
| DML (data manipulation) | INSERT, UPDATE, DELETE | Adds, modifies, and deletes rows in existing tables |
| DDL (data definition) | CREATE, ALTER, DROP; TRUNCATE is usually classified as DDL | Creates, alters, and drops tables, indexes, constraints, or schema objects |
| TCL (transaction control) | BEGIN/START TRANSACTION, COMMIT, ROLLBACK | Defines transaction boundaries and commits/aborts transactions |
| DCL (data control) | GRANT, REVOKE | Grants and revokes privileges |

Do not merely memorize group names: the key distinction is **changing individual data rows** versus **changing the schema and storage rules**. SQL is a declarative language; you describe the desired result, and the DBMS chooses the access plan. Syntax and classification nuances may differ across PostgreSQL, MySQL, SQL Server, and Oracle.

### Unified Practice Dataset

The runnable statements below use **PostgreSQL** as the reference DBMS. Practice in a dedicated database without conflicting `categories`/`products` tables. Statements to create the structure:

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id BIGINT NOT NULL
        REFERENCES categories(id) ON DELETE RESTRICT,
    sku VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_category_id ON products (category_id);
~~~

The **PRIMARY KEY** constraint identifies each row; **FOREIGN KEY** ensures references point to an existing category; **UNIQUE** prevents duplicate SKU values; **NOT NULL** requires a value; **CHECK** enforces value domains; and **DEFAULT** supplies a value when INSERT omits a column. CHECK alone does not replace NOT NULL: under SQL semantics, a CHECK condition evaluating to UNKNOWN from NULL may still be accepted.

Load sample data into the newly created schema:

~~~sql
INSERT INTO categories (name)
VALUES ('Books'), ('Equipment');

INSERT INTO products (category_id, sku, name, price, stock)
VALUES
    (
        (SELECT id FROM categories WHERE name = 'Books'),
        'BOOK-001', 'Java Fundamentals', 350000.00, 8
    ),
    (
        (SELECT id FROM categories WHERE name = 'Books'),
        'BOOK-002', 'Practical SQL', 280000.00, 0
    ),
    (
        (SELECT id FROM categories WHERE name = 'Equipment'),
        'DEV-001', 'Mechanical Keyboard', 1200000.00, 5
    );
~~~

Do not hard-code that generated IDs will always be 1, 2, 3. The subquery looks up a category by `name`, which has `UNIQUE`, yielding at most one result. If the category name does not exist, the subquery returns NULL and the INSERT is rejected by NOT NULL. When working through each following exercise, reset the sample data or account for the initial state; the UPDATE/DELETE examples may change row counts.

## 2. SELECT — Querying Data

Common clauses (the lines below are a **syntax diagram, not an executable statement**):

~~~sql
SELECT [DISTINCT] column_1, expression_2, ...
FROM source_table
[JOIN other_table ON join_condition]
[WHERE row_condition]
[GROUP BY group_column]
[HAVING group_condition]
[ORDER BY sort_column ASC | DESC]
[LIMIT row_count OFFSET offset_rows];
~~~

In **logical** processing order, SQL builds the row set in FROM/JOIN, filters rows in WHERE, groups in GROUP BY, filters groups in HAVING, evaluates expressions in SELECT, applies DISTINCT, and then sorts/limits. **Physical execution** order may differ because the optimizer is free to choose an equivalent plan.

### 2.1. SELECT, WHERE, ORDER BY, LIMIT

~~~sql
SELECT sku, name, price, stock
FROM products
WHERE price >= 300000 AND stock > 0
ORDER BY price DESC, sku ASC
LIMIT 10;
~~~

On the initial data, the result contains **DEV-001** (1,200,000) before **BOOK-001** (350,000). SELECT lists the columns to retrieve, WHERE combines conditions with AND, ORDER BY sorts descending by price then ascending by SKU, and LIMIT returns at most 10 rows. **Without ORDER BY, there is no guarantee on result order**, even if several consecutive runs look identical.

Common filtering forms:

~~~sql
-- BETWEEN includes both endpoints.
SELECT sku FROM products WHERE price BETWEEN 200000 AND 500000;

-- Match an element in a set.
SELECT sku FROM products WHERE sku IN ('BOOK-001', 'DEV-001');

-- % matches 0 or more characters; _ matches exactly one character.
SELECT sku FROM products WHERE name LIKE 'Java%';

-- NULL comparisons must use IS NULL / IS NOT NULL.
SELECT sku FROM products WHERE created_at IS NOT NULL;
~~~

**NULL means "unknown/missing value", not 0 or an empty string**. Ordinary comparisons with NULL evaluate to UNKNOWN; WHERE only keeps rows when the condition is TRUE. Therefore, do not write `WHERE col = NULL` or `WHERE col <> NULL`. `NOT IN` also requires care if the right-hand set contains NULL.

DISTINCT removes rows having the same values across **all selected expressions**. Specifying columns explicitly is usually more stable than `SELECT *` in APIs with data contracts; adding a column to a table should not unintentionally alter the column list consumed by the application.

### 2.2. JOIN — Combining Multiple Tables

~~~sql
SELECT
    p.sku,
    p.name AS product_name,
    c.name AS category_name
FROM products AS p
INNER JOIN categories AS c ON c.id = p.category_id
ORDER BY p.sku;
~~~

INNER JOIN keeps only row pairs satisfying the ON condition. LEFT JOIN keeps all rows from the left side; if there is no matching right-hand row, the right-side columns receive NULL. Filter placement matters greatly:

~~~sql
-- Categories still appear even when they have no in-stock products.
SELECT c.name AS category_name, p.sku
FROM categories AS c
LEFT JOIN products AS p
    ON p.category_id = c.id AND p.stock > 0
ORDER BY c.name, p.sku;
~~~

Moving `p.stock > 0` down to WHERE would eliminate categories with no matching products. You must also watch out for JOINs missing a condition that cause Cartesian products, inflating row counts and duplicating data in reports.

### 2.3. GROUP BY, HAVING, and Aggregate Functions

~~~sql
SELECT
    c.name AS category_name,
    COUNT(p.id) AS product_count,
    COALESCE(SUM(p.stock), 0) AS total_stock
FROM categories AS c
LEFT JOIN products AS p ON p.category_id = c.id
GROUP BY c.id, c.name
HAVING COUNT(p.id) >= 1
ORDER BY c.name;
~~~

Result from the initial data: category **Books** has 2 products / total stock 8; **Equipment** has 1 product / total stock 5. WHERE filters **before** grouping, while HAVING filters **after** aggregation. Common functions: COUNT, SUM, AVG, MIN, MAX. `COUNT(*)` counts every result row, whereas `COUNT(p.id)` ignores NULL; in a LEFT JOIN, `COUNT(*)` may also count unmatched rows from the right side. COALESCE substitutes NULL with a fallback value. Columns in SELECT outside aggregate functions must follow the DBMS's GROUP BY / functional-dependency rules.

### 2.4. Pagination and Performance

~~~sql
SELECT id, sku, name
FROM products
ORDER BY id
LIMIT 20 OFFSET 40;
~~~

This is page three when each page has 20 rows and the first page is page 1. ORDER BY needs to be deterministic, usually including a unique key. Large OFFSET values can force the DBMS to read and discard many rows; when paging forward by ID, keyset pagination can be more efficient:

~~~sql
SELECT id, sku, name
FROM products
WHERE id > 100
ORDER BY id
LIMIT 20;
~~~

Here 100 is the last ID of the previous page. When the table changes concurrently, the two pagination styles may observe different result sets. LIMIT is PostgreSQL/MySQL syntax; some DBMSs use `FETCH FIRST`, `OFFSET FETCH`, or `TOP`. For large datasets, run EXPLAIN and check appropriate indexes instead of assuming every WHERE query uses an index.

## 3. INSERT — Adding Rows

Always specify the column list explicitly so the statement does not depend on schema column order:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
VALUES (
    (SELECT id FROM categories WHERE name = 'Books'),
    'BOOK-003', 'Advanced SQL', 420000.00, 4
);
~~~

Omitting `id` lets IDENTITY generate an ID; omitting `stock` uses `DEFAULT 0`. NOT NULL, UNIQUE, FOREIGN KEY, and CHECK are enforced on write. INSERT can insert multiple rows with multi-tuple VALUES, as in the sample dataset, or insert from a query result:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT c.id, 'BOOK-004', 'Database Design', 390000.00, 3
FROM categories AS c
WHERE c.name = 'Books';
~~~

If the Books category does not exist, this `INSERT ... SELECT` inserts **0 rows**; to guarantee exactly one row, the application must check the update count.

### Retrieving Auto-Generated IDs and Handling Conflicts

PostgreSQL supports RETURNING:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT id, 'BOOK-005', 'Introduction to JDBC', 250000.00, 7
FROM categories
WHERE name = 'Books'
RETURNING id, sku;
~~~

If a SKU violates UNIQUE, INSERT fails by default. PostgreSQL supports intentional conflict handling:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT id, 'BOOK-001', 'Java Fundamentals', 350000.00, 8
FROM categories
WHERE name = 'Books'
ON CONFLICT (sku) DO NOTHING;
~~~

`DO NOTHING` skips conflicting rows and **does not update** existing data. For an UPSERT, you must define `ON CONFLICT DO UPDATE` rules; equivalent syntax varies across DBMSs. Do not use conflict-ignoring clauses to mask unexpected data errors.

## 4. UPDATE — Modifying Existing Rows

~~~sql
UPDATE products
SET price = 360000.00
WHERE sku = 'BOOK-001';
~~~

Every row matching WHERE is updated. Without WHERE, the statement can modify the entire table:

~~~sql
-- DANGEROUS: sets the same price for all products.
UPDATE products SET price = 360000.00;
~~~

A reliable manual data-fix workflow is to SELECT to inspect the target rows, open a transaction, run UPDATE, verify the affected row count or RETURNING output, and only then COMMIT; if something looks wrong, ROLLBACK before committing.

### Relative Updates and Business-Guard Conditions

~~~sql
UPDATE products
SET stock = stock - 2
WHERE sku = 'BOOK-001' AND stock >= 2
RETURNING sku, stock;
~~~

Starting from the initial state, one row is updated and the stock of BOOK-001 becomes **6**. If the SKU does not exist or stock is below 2, the result is 0 rows. The application must handle this case and not treat every UPDATE that throws no exception as a business success.

Updating relative to column values in a single conditional statement avoids the uncontrolled pattern of reading stock into the application, computing the new value, and overwriting. For multi-table or contended operations, you still need to understand transactions and isolation levels to guarantee all business invariants.

Example updating multiple columns at once:

~~~sql
UPDATE products
SET name = 'Foundational Java',
    price = ROUND(price * 1.05, 2)
WHERE sku = 'BOOK-001';
~~~

`RETURNING` and `UPDATE ... FROM/JOIN` syntax varies across DBMSs. Do not think of UPDATE as sequential Java variable assignments; expressions are evaluated by the DBMS under SQL statement semantics.

## 5. DELETE — Removing Rows

~~~sql
DELETE FROM products
WHERE sku = 'BOOK-002' AND stock = 0
RETURNING sku;
~~~

On the initial sample state, this deletes one product, BOOK-002. Without WHERE, DELETE targets every row:

~~~sql
-- DANGEROUS: deletes all rows in the products table.
DELETE FROM products;
~~~

**Foreign key constraints** can block DELETE on a parent table that still has referencing child rows. In the sample schema, `categories` is referenced by `products` and `ON DELETE RESTRICT` prevents deleting a category that still has products. `ON DELETE CASCADE` deletes children along with the parent when designed that way, which can cause unintended data loss. `SET NULL` is only valid when the child column allows NULL. Never blindly change an FK to CASCADE just to make a DELETE statement succeed.

If the system requires recovery or auditing, "soft delete" via a `deleted_at` column may fit, though it is a distinct domain model: queries must filter active rows, and uniqueness, access control, and retention must match the design. A committed DELETE may be unrecoverable without recovery/backup mechanisms.

### DELETE vs. TRUNCATE

| Criterion | DELETE | TRUNCATE |
| --- | --- | --- |
| Scope | Can filter with WHERE; without WHERE, targets whole table | Empties table; does not support WHERE |
| Statement group | DML | Usually treated as DDL |
| Triggers, identity, locks, FKs | Follows DBMS DELETE rules | Has its own mechanisms, differing from DELETE and across DBMSs |
| Recovery in transaction | Depends on transaction support | **Do not assume** every DBMS rolls it back the same way |

PostgreSQL supports rolling back TRUNCATE inside a suitable transaction, whereas MySQL implicitly commits around many DDL statements. For tables referenced by FKs, TRUNCATE has special restrictions and locking rules. Use it only after deciding to clear the entire table and understanding its impact in your DBMS.

## 6. DDL — Defining and Changing Structure

- **CREATE TABLE** defines the table name, columns, data types, DEFAULTs, and constraints; **CREATE INDEX** adds an access structure.
- **ALTER TABLE** adds, modifies, or drops columns or constraints, depending on DBMS capabilities.
- **DROP TABLE/INDEX** removes an object; DROP TABLE also destroys the table's data.
- **TRUNCATE** empties a table according to DBMS DDL rules, with no WHERE clause.

An example of phased schema evolution:

~~~sql
ALTER TABLE products
ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX idx_products_active_price
ON products (active, price);

SELECT sku, name
FROM products
WHERE active = TRUE AND price >= 300000
ORDER BY price DESC;
~~~

Queries referencing `active` can run only after ALTER completes. Indexes can speed up certain queries yet consume storage, add overhead to INSERT/UPDATE/DELETE, and are not guaranteed to be chosen by the optimizer; inspect query plans and real workloads.

The following teardown commands are for learning syntax only—**do not run them on data you want to keep**:

~~~sql
DROP INDEX idx_products_active_price;
ALTER TABLE products DROP COLUMN active;
-- DROP TABLE products; -- will remove the table and its data if executed
~~~

In a Spring application, schema changes in shared environments should go through versioned migrations such as Flyway or Liquibase. Before applying them, evaluate compatibility between old and new app versions, data backfills, table-locking impact, roll-forward/rollback options, and backups. Never assume all CREATE/ALTER/DROP statements roll back: PostgreSQL supports many DDL statements inside transactions, whereas MySQL typically performs implicit commits around many DDL statements.

## 7. Transactions, Concurrent Updates, and Affected Row Counts

A single business action may involve multiple DML statements, requiring a transaction. For example, transferring one unit of inventory between two SKUs:

~~~sql
BEGIN;

UPDATE products
SET stock = stock - 1
WHERE sku = 'BOOK-001' AND stock >= 1;

UPDATE products
SET stock = stock + 1
WHERE sku = 'BOOK-002';

-- The application must verify that EACH UPDATE affects exactly one row.
-- If both succeed, COMMIT; if wrong or an error occurs, ROLLBACK.
~~~

The example intentionally **does not auto-COMMIT**: a transaction does not automatically enforce the requirement that "each UPDATE must affect exactly one row." If one UPDATE touches 0 rows and the application still commits, the business outcome can be wrong. Transaction atomicity and isolation levels are separate concerns; isolation levels affect how concurrent transactions see data and can lead to race conditions or deadlocks. Define a sensible retry strategy for contention errors.

In JDBC, SELECT returns a ResultSet, whereas INSERT/UPDATE/DELETE typically yield an update count. "Throws no error" does not necessarily mean "modified the intended rows." In Spring, `@Transactional` is usually placed at the service layer to wrap a unit of work; understand the actual transaction manager and rollback rules before relying on the annotation.

## 8. Connecting SQL Knowledge to Spring JdbcTemplate

JdbcTemplate supports manual SQL in Spring: managing JDBC resource lifecycles, binding parameters, mapping ResultSets, and translating SQLExceptions into Spring's DataAccessException hierarchy. The snippet below is **a class inside a Spring application with `spring-jdbc`, a configured `JdbcTemplate`/`DataSource`, and an existing `products` table**. It is not a standalone Java program runnable with `javac` alone.

File `ProductDao.java`, Java 17+ syntax:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductDao {
    private final JdbcTemplate jdbc;

    public ProductDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<ProductView> findAvailable(BigDecimal minPrice) {
        return jdbc.query(
            """
            SELECT sku, name, price, stock
            FROM products
            WHERE price >= ? AND stock > 0
            ORDER BY price DESC, sku
            """,
            (rs, rowNum) -> new ProductView(
                rs.getString("sku"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getInt("stock")
            ),
            minPrice
        );
    }

    public boolean reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int updated = jdbc.update(
            """
            UPDATE products
            SET stock = stock - ?
            WHERE sku = ? AND stock >= ?
            """,
            quantity, sku, quantity
        );
        return updated == 1;
    }

    public record ProductView(
        String sku, String name, BigDecimal price, int stock
    ) {}
}
~~~

The **`?`** symbol marks a value-binding placeholder via PreparedStatement. `minPrice`, `quantity`, and `sku` are passed as parameters instead of concatenating input values into SQL strings. This prevents SQL injection and keeps type handling explicit. Parameters cannot represent table names, column names, or SQL keywords; if users may choose an ORDER BY column, map against an allowlisted set of column names.

`reserve` returns `true` if exactly one row had its stock decremented and `false` if the SKU does not exist or stock is insufficient. The `stock >= ?` condition guards against negative stock. For multi-step workflows, the service layer must define transactions and behavior when an update count is unexpected. Even when using JPA instead of JdbcTemplate, understanding basic SQL remains essential to read ORM-generated queries and diagnose constraint, relationship, and performance issues.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| UPDATE/DELETE missing WHERE | Modifies or deletes the entire table | SELECT target rows first, use transactions, verify affected rows |
| WHERE col = NULL | Fails to match NULL rows | Use IS NULL / IS NOT NULL |
| Relying on SELECT order without ORDER BY | Pagination or display breaks expectations | Specify ORDER BY clearly, with a unique key when needed |
| COUNT(*) after LEFT JOIN to count right-side table | Counts unmatched rows as well | Use COUNT(p.id) or conditional aggregation |
| Concatenating user input into SQL | SQL injection, escaping/type bugs | Bind parameters with PreparedStatement |
| INSERT without listing columns | Fragile to column order / schema changes | Always list target columns |
| Ignoring update count | Assumes success even when 0 rows changed | Check the exact business invariant |
| Using ON DELETE CASCADE carelessly | Can delete related rows unintentionally | Design explicit FK policies |
| Assuming DDL always rolls back | Failed migrations become hard to recover | Check DBMS behavior and plan migrations |
| Indexing every column | Slow writes, wasted storage | Measure workload, inspect EXPLAIN |

## 10. Self-Check Exercises with Sample Data

The answers below apply to the **initial three-product state** from section 1. If you ran experimental INSERT/UPDATE/DELETE statements, restore the sample data in your practice environment before checking.

**Exercise 1. Find in-stock products priced at least 300,000, most expensive first.**

~~~sql
SELECT sku, price
FROM products
WHERE stock > 0 AND price >= 300000
ORDER BY price DESC, sku;
~~~

Answer: DEV-001 (1,200,000), then BOOK-001 (350,000).

**Exercise 2. Find out-of-stock products.**

~~~sql
SELECT sku, name
FROM products
WHERE stock = 0
ORDER BY sku;
~~~

Answer: BOOK-002.

**Exercise 3. Find categories with at least two products, including out-of-stock ones.**

~~~sql
SELECT c.name, COUNT(p.id) AS product_count
FROM categories AS c
LEFT JOIN products AS p ON p.category_id = c.id
GROUP BY c.id, c.name
HAVING COUNT(p.id) >= 2;
~~~

Answer: Books, `product_count = 2`. If the requirement changes to "two **in-stock** products," adjust the join condition or counting expression accordingly.

**Exercise 4. Decrease BOOK-001 stock by two units without allowing negative values.**

~~~sql
UPDATE products
SET stock = stock - 2
WHERE sku = 'BOOK-001' AND stock >= 2
RETURNING sku, stock;
~~~

Answer on the first run: one row updated, stock drops from 8 to 6. Running it again keeps subtracting until `stock < 2`, at which point affected rows becomes 0. This statement is not idempotent; when retrying after a timeout, guard against subtracting twice if the previous attempt committed.

**Exercise 5. Distinguish two types of changes.** `UPDATE products SET price = ...` is DML because it modifies row values; `ALTER TABLE products ADD COLUMN active BOOLEAN ...` is DDL because it alters the schema. The new schema must remain compatible with running application code.

### Checklist When Writing SQL in a Spring Application

1. Identify tables, keys, columns to read/write, and how NULLs are handled.
2. Verify PK, FK, UNIQUE, NOT NULL, CHECK, and domain rules.
3. Use bound parameters for input data; avoid string-concatenated SQL.
4. For UPDATE/DELETE, verify WHERE, affected rows, transactions, and concurrency handling.
5. For SELECT, check JOIN, ORDER BY, pagination, data volume, and execution plans.
6. For DDL, verify DBMS-specific syntax and deploy via controlled migrations.

Mastering core SQL enables accurate reasoning about Spring's data-access layer—from query results and update-count handling to database constraints and transactions.