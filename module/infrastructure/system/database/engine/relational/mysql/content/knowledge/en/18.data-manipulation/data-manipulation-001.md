# Single-Row INSERT, Multi-Row INSERT, and INSERT from SELECT

When an application onboards a new customer, imports a product catalog, or aggregates order data into a reporting table, it needs to write data into MySQL in a well-structured way with proper error handling. MySQL provides several forms of `INSERT`: inserting a single row with `VALUES`, inserting multiple rows in a single statement, and inserting query results directly with `INSERT ... SELECT`.

Choosing the right form of `INSERT` helps reduce round-trips to the server, maintain consistency across tables, and prevent missing or corrupted data. You must clearly define the column list, default values, constraints, unique keys, transactions, and how to handle duplicate source data.

## 1. How Does INSERT Write Data into a Table?

`INSERT` adds one or more rows to a table. Common syntax:

```sql
INSERT INTO table_name (column_1, column_2, ...)
VALUES (value_1, value_2, ...);
```

The column list defines the position and meaning of each value. The number of values in each tuple must match the number of listed columns; the order of values must correspond to the column order.

Example customers table:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
```

Insert one customer:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.com', 'Nguyen Van An');
```

MySQL automatically generates `id`, uses the default `ACTIVE` for `status`, assigns `NULL` to `note`, and uses the current timestamp for `created_at`.

### 1.1. Always List Column Names

Prefer writing:

```sql
INSERT INTO customers (email, full_name, status)
VALUES ('binh@example.com', 'Tran Minh Binh', 'ACTIVE');
```

Avoid writing:

```sql
INSERT INTO customers
VALUES (NULL, 'binh@example.com', 'Tran Minh Binh', 'ACTIVE', NULL, DEFAULT);
```

A statement without a column list depends on the order of all columns in the table. When the schema adds or reorders columns, the old statement may fail or write data into the wrong columns. Listing columns makes the SQL explicit and less coupled to the physical table structure.

### 1.2. Omitting Columns to Use DEFAULT

If a column is omitted from the column list, MySQL uses that column's default value if one exists. The example above omits `status`, `note`, and `created_at`.

You can explicitly specify `DEFAULT`:

```sql
INSERT INTO customers (email, full_name, status, note)
VALUES ('chi@example.com', 'Le Thu Chi', DEFAULT, NULL);
```

`DEFAULT` instructs MySQL to use the default defined for the column. `NULL` is an actual NULL value; it does not mean using the default.

Comparison:

| Syntax | Meaning |
|---|---|
| Omit column from INSERT list | Uses the column's default if defined; otherwise behavior depends on nullability and SQL mode |
| Specify `DEFAULT` | Requests using the column's default |
| Specify `NULL` | Writes SQL NULL if the column allows it |
| Specify `''` | Writes an empty string, which is different from NULL |

In strict mode, omitting a `NOT NULL` column without a default usually causes the statement to fail. In non-strict mode, MySQL may use an implicit default and emit a warning; do not rely on this behavior for business data.

### 1.3. Inserting a Row with Only Default Values

If every column can receive a default or be auto-generated, you can write:

```sql
INSERT INTO customers () VALUES ();
```

This statement creates a row using default values. With the example schema, `id` auto-increments, `status` receives `ACTIVE`, `note` receives NULL, and `created_at` receives the current timestamp; however, `email` and `full_name` are `NOT NULL` without a default, so this statement will fail under a typical strict configuration. This example illustrates the syntax, not valid data for the `customers` table.

### 1.4. MySQL's INSERT ... SET Syntax

MySQL also supports an extended form:

```sql
INSERT INTO customers
SET email = 'dung@example.com',
    full_name = 'Pham Quoc Dung',
    status = DEFAULT;
```

The `INSERT ... SET` form assigns each column by name, which is convenient when the statement has few columns or is built from name/value pairs. This is a MySQL-specific syntax; `INSERT ... (columns) VALUES (...)` is more standard and portable across database management systems.

## 2. AUTO_INCREMENT Values and the Newly Generated ID

For an `AUTO_INCREMENT` column, you can omit the ID column from the INSERT list so MySQL assigns it automatically:

```sql
INSERT INTO customers (email, full_name)
VALUES ('hoa@example.com', 'Nguyen Thu Hoa');

SELECT LAST_INSERT_ID() AS customer_id;
```

`LAST_INSERT_ID()` returns the most recently generated auto-increment ID on the current connection. The SELECT statement must run on the same physical connection as the INSERT statement. Do not use `SELECT MAX(id)` to retrieve the newly created ID because another connection may insert concurrently in between.

For a multi-row INSERT statement, `LAST_INSERT_ID()` returns the first auto-increment ID generated by that statement, not the entire list of IDs. Do not assume subsequent IDs are contiguous; rollbacks, failed inserts, concurrency, and auto-increment settings can create gaps.

In Java JDBC, prefer the statement's generated keys API:

```java
String sql = "INSERT INTO customers (email, full_name) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    statement.setString(1, email);
    statement.setString(2, fullName);
    statement.executeUpdate();

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (keys.next()) {
            long customerId = keys.getLong(1);
        }
    }
}
```

Check the statement result and handle cases where the driver does not return a generated key. If the transaction rolls back, the received ID does not guarantee the row still exists.

### 2.1. Inserting an Explicit AUTO_INCREMENT Value

MySQL allows providing an explicit value for an `AUTO_INCREMENT` column:

```sql
INSERT INTO customers (id, email, full_name)
VALUES (5000, 'imported@example.com', 'Imported customer');
```

Only do this when you have a clear reason such as recovery or syncing IDs from an authoritative source. An explicit value can affect the next auto-generated value. A value of `0` is usually treated as a request to assign a new ID; if the `NO_AUTO_VALUE_ON_ZERO` SQL mode is enabled, `0` is stored as an explicit value. A `NULL` value in an AUTO_INCREMENT column normally instructs MySQL to generate a new value.

## 3. Multi-Row INSERT in a Single Statement

When you have multiple rows with the same structure, use a single statement with multiple tuples:

```sql
INSERT INTO customers (email, full_name, status)
VALUES
    ('lan@example.com', 'Vu Ngoc Lan', 'ACTIVE'),
    ('minh@example.com', 'Do Quang Minh', 'ACTIVE'),
    ('nam@example.com', 'Phan Hoang Nam', 'PENDING');
```

Each tuple must have the exact same number of values and the same column order. This statement typically reduces the number of client requests sent to the server compared to running three separate INSERT statements.

### 3.1. Benefits of Multi-Row INSERT

- Reduces round-trips between the application and MySQL.
- Reduces repeated statement parsing and execution overhead.
- Makes it easier to group a batch of data into a single write unit.
- Can improve throughput when loading moderate amounts of data.

However, an overly large batch can make the SQL statement very long, consume memory, create a large transaction, and increase lock hold duration. Choose the batch size based on row size, packet limits, latency, resources, and rollback considerations.

### 3.2. Every Tuple Must Match the Column List

Incorrect example:

```sql
-- WRONG: the second tuple is missing a value.
INSERT INTO customers (email, full_name, status)
VALUES
    ('one@example.com', 'First person', 'ACTIVE'),
    ('two@example.com', 'Second person');
```

MySQL raises an error because the tuples do not have the same number of values. You must also ensure consistent column order; swapping `email` and `full_name` can cause data type errors or store values in the wrong columns.

### 3.3. Using DEFAULT Per Row

```sql
INSERT INTO customers (email, full_name, status, note)
VALUES
    ('one@example.com', 'First person', DEFAULT, NULL),
    ('two@example.com', 'Second person', 'PENDING', 'Pending verification'),
    ('three@example.com', 'Third person', DEFAULT, 'Registered in store');
```

Each tuple can provide different values or use `DEFAULT` for a column. The column list must still remain the same across all tuples.

## 4. INSERT from SELECT

`INSERT ... SELECT` inserts the result of a query into a target table without requiring the application to read the data and send each row back.

Syntax:

```sql
INSERT INTO target_table (target_col_1, target_col_2, ...)
SELECT source_expr_1, source_expr_2, ...
FROM source_table
WHERE condition;
```

The number of columns and expressions in the SELECT must match the target column list. Order matters: the first expression goes into the first target column, the second expression goes into the second column, and so on.

### 4.1. Selective Data Copying

Suppose you have a table storing inactive customers:

```sql
CREATE TABLE inactive_customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    archived_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Insert inactive customers from the main table:

```sql
INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    c.id,
    c.email,
    c.full_name,
    CURRENT_TIMESTAMP
FROM customers AS c
WHERE c.status = 'INACTIVE';
```

MySQL reads the matching rows and inserts them into the target table. If the target table has a duplicate primary key or unique key, the statement may fail unless an appropriate duplicate-handling strategy is used.

### 4.2. Aggregating Data Before Inserting

You can use JOIN, GROUP BY, and expressions in SELECT to generate reporting data:

```sql
CREATE TABLE customer_order_summary (
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    calculated_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Insert the aggregated results:

```sql
INSERT INTO customer_order_summary (
    customer_id,
    order_count,
    total_amount,
    calculated_at
)
SELECT
    o.customer_id,
    COUNT(DISTINCT o.id),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP
FROM orders AS o
INNER JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
```

This query computes the total amount per customer from paid orders. Because each order has multiple line items, `COUNT(DISTINCT o.id)` counts unique orders while `SUM` totals amounts at the line-item level. If you join another one-to-many table, you must account for fan-out to avoid multiplying totals.

### 4.3. Inserting Only Rows That Do Not Yet Exist

You can filter the source using `NOT EXISTS`:

```sql
INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    c.id,
    c.email,
    c.full_name,
    CURRENT_TIMESTAMP
FROM customers AS c
WHERE c.status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM inactive_customers AS a
      WHERE a.customer_id = c.id
  );
```

`NOT EXISTS` avoids selecting customers already present in the target table at the time the query reads. However, two concurrent jobs can still both see an ID as missing and both attempt to insert it. The primary key/unique key on the target table remains the final safeguard; if concurrent execution must be safe, design an appropriate duplicate/idempotency strategy.

### 4.4. INSERT ... SELECT from the Same Table

MySQL can read data from a table and insert it back into the same table if the statement and structure allow it. Be careful to avoid re-selecting newly inserted rows or creating unbounded duplicates. Always define clear source filtering conditions, appropriate unique constraints, and test on small datasets before running large batches.

## 5. Choosing a Strategy for Duplicate Data

When inserting a row whose primary key or unique key already exists, MySQL normally returns a duplicate key error. There are three common options, each with different semantics.

### 5.1. Letting the Duplicate Error Occur

This is usually the best choice when duplication is a business error:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.com', 'Another name');
```

If the email already exists in the unique index, MySQL rejects the insert. The application can return a message such as "email is already in use" or trigger a specific business workflow.

### 5.2. INSERT IGNORE

`INSERT IGNORE` instructs MySQL to ignore certain errors that can be downgraded to warnings, including duplicate key errors:

```sql
INSERT IGNORE INTO customers (email, full_name)
VALUES
    ('existing@example.com', 'Do not overwrite old name'),
    ('new@example.com', 'New customer');
```

Duplicate rows can be skipped while other valid rows are still inserted. However, `IGNORE` has a broader scope than duplicate keys: certain data errors such as type conversions or out-of-range values may be downgraded to warnings, with data adjusted according to MySQL rules. Therefore, do not use `IGNORE` just to "make the statement succeed" without inspecting warnings.

Immediately after the statement, check:

```sql
SHOW WARNINGS;
```

`SHOW WARNINGS` reflects the warnings from the most recent statement in the same session; run it right after the INSERT before another statement replaces the warning list. In the application, inspect affected rows, warning count, and log skipped data.

### 5.3. INSERT ... ON DUPLICATE KEY UPDATE

If a key conflict means the existing row should be updated, use an upsert:

```sql
CREATE TABLE product_inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (product_id, warehouse_id)
) ENGINE=InnoDB;
```

Insert a new row or update the quantity:

```sql
INSERT INTO product_inventory (
    product_id,
    warehouse_id,
    available_quantity,
    updated_at
)
VALUES (42, 3, 100, CURRENT_TIMESTAMP) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = incoming.available_quantity,
    updated_at = incoming.updated_at;
```

The row alias syntax after `VALUES` is supported starting in MySQL 8.0.19. The alias `incoming` represents the row proposed for insertion; in the duplicate branch, you can use it to reference the new values.

Before MySQL 8.0.19, many examples used `VALUES(column_name)` in the update clause. That `VALUES()` function usage was deprecated in MySQL 8.0.20; on newer versions, prefer a row alias.

`ON DUPLICATE KEY UPDATE` is triggered when the insert conflicts with any PRIMARY KEY or UNIQUE index. If a table has multiple unique keys, you must understand which key a conflict can occur on; do not assume there is only one business key.

### 5.4. Comparing IGNORE, UPSERT, and REPLACE

| Approach | On duplicate | Behavior |
|---|---|---|
| `INSERT` | Raises an error | Does not silently skip duplicate data |
| `INSERT IGNORE` | Skips rows/errors convertible to warnings | Does not update the existing row; must check warnings |
| `INSERT ... ON DUPLICATE KEY UPDATE` | Executes the UPDATE branch | Keeps the existing row and updates specified columns |
| `REPLACE INTO` | Deletes the conflicting row and inserts a new row | Can trigger FKs, triggers, auto-increment, and omit-column defaults |

`REPLACE` is not simply a form of UPSERT. For a conflicting row, MySQL performs a delete followed by an insert; `ON DELETE` foreign keys, triggers, and columns omitted from the INSERT can produce completely different side effects than UPDATE. Do not use `REPLACE` in place of `ON DUPLICATE KEY UPDATE` when you want to preserve the existing row's identity and relationships.

## 6. Affected Rows and Warnings on INSERT

After an INSERT, applications often need to know how many rows the statement affected. With `INSERT ... ON DUPLICATE KEY UPDATE`, the affected-row count follows MySQL's standard rules:

- `1` if a new row is inserted.
- `2` if an existing row is updated.
- `0` if an existing row is assigned its current values.

If the client uses the `CLIENT_FOUND_ROWS` flag, an unchanged row may be reported as `1`. Therefore, do not interpret affected rows as an independent business state indicator without accounting for the connector and flags.

With a multi-row INSERT, affected rows is the total processed according to the statement's rules; `INSERT IGNORE` and upserts can yield numbers different from the number of input tuples. If you need to know specifically which rows were inserted, skipped, or updated, rely on business keys, driver results, and reconciliation workflows rather than looking at a single number.

## 7. INSERT and Transactions

With InnoDB, INSERT is a transactional operation. You can group multiple write operations into a single transaction to guarantee they all commit or roll back together:

```sql
START TRANSACTION;

INSERT INTO orders (customer_id, status, created_at)
VALUES (120, 'NEW', CURRENT_TIMESTAMP);

SET @order_id = LAST_INSERT_ID();

INSERT INTO order_items (
    order_id,
    line_no,
    product_id,
    warehouse_id,
    quantity,
    unit_price,
    created_at
)
VALUES
    (@order_id, 1, 42, 3, 2, 150000.00, CURRENT_TIMESTAMP),
    (@order_id, 2, 57, 3, 1,  80000.00, CURRENT_TIMESTAMP);

COMMIT;
```

If one statement fails, the application can roll back the entire transaction:

```sql
ROLLBACK;
```

In production code, use prepared statements and application local variables; `@order_id` here only illustrates a session variable retained across statements on the same connection. Always check for errors on every operation and commit only when all required steps succeed.

### 7.1. INSERT ... SELECT in a Transaction

You can run INSERT SELECT alongside other operations inside an InnoDB transaction:

```sql
START TRANSACTION;

INSERT INTO inactive_customers (
    customer_id,
    email,
    full_name,
    archived_at
)
SELECT
    id,
    email,
    full_name,
    CURRENT_TIMESTAMP
FROM customers
WHERE status = 'INACTIVE';

-- Verify row count and business conditions here.

COMMIT;
```

If the statement or subsequent check fails, roll back to discard the transactional changes. DDL and certain administrative statements cause an implicit commit; do not place them in between while expecting the entire transaction to roll back.

### 7.2. Atomicity and Storage Engines

The rollback behavior in the example depends on a transactional storage engine such as InnoDB. With a non-transactional engine, `ROLLBACK` cannot undo written changes. For business systems requiring integrity, use InnoDB for related tables and keep operations within the same transaction and connection.

## 8. Checking Data Before INSERT ... SELECT

Before loading a large amount of data, run the corresponding SELECT to inspect the source:

```sql
SELECT
    c.id,
    c.email,
    c.full_name
FROM customers AS c
WHERE c.status = 'INACTIVE'
ORDER BY c.id
LIMIT 100;
```

Check the row count:

```sql
SELECT COUNT(*) AS source_rows
FROM customers
WHERE status = 'INACTIVE';
```

Check for duplicates against the target key:

```sql
SELECT c.id, COUNT(*) AS occurrences
FROM customers AS c
WHERE c.status = 'INACTIVE'
GROUP BY c.id
HAVING COUNT(*) > 1;
```

If the target table has other unique keys, check for conflicts on each of those unique keys as well. Running `SELECT` beforehand only shows the data at the time of inspection; another transaction can still modify the source or insert the same key before the INSERT runs. Constraints on the target table remain the final safeguard.

## 9. INSERT from SELECT and Data Types

SELECT expressions are converted to the target column types. Ensure that types and value ranges are compatible:

- Integers do not exceed the target column's range.
- Decimal values retain sufficient precision and scale.
- Strings are not truncated or converted across charsets unexpectedly.
- Date/time values match the target type and timezone.
- SQL NULL is written only to nullable columns or handled with explicit fallback logic.

Example of intentional conversion:

```sql
INSERT INTO monthly_revenue (month_start, total_amount)
SELECT
    CAST(DATE_FORMAT(o.created_at, '%Y-%m-01') AS DATE),
    CAST(SUM(oi.quantity * oi.unit_price) AS DECIMAL(18,2))
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.status = 'PAID'
GROUP BY DATE_FORMAT(o.created_at, '%Y-%m-01');
```

Using CAST makes the intended type explicit. However, you must verify how date/time expressions are converted and that precision matches the target schema. Do not use CAST to mask invalid source data.

## 10. INSERT Performance

### 10.1. Reducing Round-Trips with Multi-Row INSERT

If an application has 500 rows, sending 500 separate INSERT statements usually incurs far more round-trips than splitting them into multi-row batches. Choose the batch size based on benchmarks and packet limits; there is no single optimal number for every workload.

### 10.2. Indexes and Constraints Increase Write Cost

Every INSERT must update relevant indexes and validate constraints. Tables with many indexes, foreign keys, or triggers have higher write overhead. Create only indexes that serve actual queries; do not drop constraints for speed without an alternative validation mechanism.

### 10.3. Packet Size

Large multi-row INSERT statements can exceed `max_allowed_packet` on the client or server. When encountering packet-too-large errors, reduce the batch size and inspect client/server settings. Do not raise the limit arbitrarily; batches must fit available resources and processing windows.

### 10.4. Overly Large Transactions

A transaction writing hundreds of thousands or millions of rows can hold undo logs, locks, and resources for a long time, increasing replication lag or putting pressure on purge. You can split the work into batches and commit incrementally if the business accepts partial completion. If all-or-nothing atomicity is required, keep the corresponding transaction boundary or design a staging/reconciliation workflow.

## 11. Prepared Statements for Application INSERTs

Do not concatenate user input directly into SQL strings. Use parameter binding:

```java
String sql = "INSERT INTO customers (email, full_name, status) VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, fullName);
    statement.setString(3, status);
    int affectedRows = statement.executeUpdate();
}
```

For multiple rows, you can use JDBC batching:

```java
String sql = "INSERT INTO customers (email, full_name) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (Customer customer : customers) {
        statement.setString(1, customer.email());
        statement.setString(2, customer.fullName());
        statement.addBatch();
    }
    int[] results = statement.executeBatch();
}
```

The Batch API may be optimized by the driver or sent as multiple statements depending on configuration; do not assume `executeBatch()` is always equivalent to a single multi-row INSERT statement. If atomicity is required, manage transactions explicitly and handle `BatchUpdateException`.

## 12. Common INSERT Errors

| Error / Symptom | Possible Cause | Resolution |
|---|---|---|
| Column count doesn't match value count | Number of values does not match the column list | Check each tuple and column order |
| Duplicate entry | PRIMARY KEY or UNIQUE violation | Decide between error, ignore, or upsert policy |
| Cannot be null | Inserting NULL or omitting a NOT NULL column with no default | Provide a valid value or design an appropriate business default |
| Data too long / out of range | Value exceeds column length or data type range | Check schema and source data; avoid relying on implicit truncation |
| Cannot add or update a child row | FK value has no matching parent | Load parent rows first; verify foreign keys and source data |
| INSERT IGNORE did not write all rows | Duplicate rows or errors downgraded to warnings | Run SHOW WARNINGS, check affected rows, and reconcile source/target |
| LAST_INSERT_ID returns unexpected value | Executed on a different connection or previous insert failed | Retrieve ID on the same connection immediately after a successful insert |
| Oversized batch causes packet error | Statement exceeds packet limit | Reduce batch size and check max_allowed_packet |
| INSERT SELECT creates duplicate data | Source has multiple rows or concurrent jobs ran | Verify grain, unique keys, and idempotency strategy |
| Rollback does not undo data | Table uses a non-transactional engine or transaction already committed | Use InnoDB and verify transaction boundaries |

## 13. Choosing the Right Form of INSERT

| Need | SQL Form to Consider |
|---|---|
| Create one record from a form | `INSERT ... (columns) VALUES (...)` |
| Create a record using defaults | `INSERT ... () VALUES ()` if schema allows |
| Write a batch of structurally identical rows | Multi-row `INSERT ... VALUES (...), (...)` |
| Copy/filter/aggregate data inside the server | `INSERT ... SELECT` |
| Intentionally skip duplicate rows | `INSERT IGNORE`, along with checking warnings |
| Update when a key already exists | `INSERT ... ON DUPLICATE KEY UPDATE` |
| Ensure multiple tables write or cancel together | InnoDB transaction |
| Write dynamic data from an application | Prepared statement / parameter binding |

Before running in production, verify unique keys, expected row counts, duplicate behavior, trigger/FK impact, batch size, and rollback capability.

## 14. Safety Checklist Before and After INSERT

**Before writing:**

- Is the column list explicit and in the right order?
- Does each tuple have the exact number of values?
- Are defaults, NULLs, and empty strings properly distinguished?
- Do values match the target types, precision, charset, and value ranges?
- Could PRIMARY KEY, UNIQUE, or FOREIGN KEY violations occur?
- If using INSERT SELECT, have you run SELECT to verify the source and grain?
- Is there any fan-out risk that could inflate row counts or totals?
- Is the duplicate policy to fail, ignore, or update?
- Are batch size and transaction scope suitable for system load?

**After writing:**

- Check affected rows and warnings.
- Retrieve the generated key on the same connection if needed.
- Reconcile source and target row counts during imports.
- Commit only when all operations in the transaction succeed.
- Log enough details to retry safely without creating duplicate data.
- Monitor execution time, lock waits, replication lag, and resources for large batches.

## Conclusion

`INSERT ... VALUES` is suited for creating a single row; multi-row `INSERT` reduces round-trips when writing multiple rows with the same structure; `INSERT ... SELECT` helps filter, transform, and aggregate data directly inside MySQL. Always list columns, understand DEFAULT vs. NULL, verify unique and foreign keys, choose duplicate policies intentionally, and manage InnoDB transactions. For dynamic data, use prepared statements; for batches and imports, check warnings, affected rows, batch sizes, and reconciliation results. These practices keep write operations accurate, recoverable, and operationally stable.
