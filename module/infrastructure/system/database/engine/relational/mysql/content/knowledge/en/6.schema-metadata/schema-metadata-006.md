# SHOW CREATE TABLE, SHOW INDEX, and SHOW TABLE STATUS

When working with MySQL, knowing a table's name and columns is not enough to understand its true structure. A table also has data types, default values, primary keys, foreign keys, constraints, indexes, storage engine, collation, and many other storage options. This information directly affects data integrity, how queries are executed, and how the database is operated.

MySQL provides three commonly used commands for quickly inspecting table metadata:

- **SHOW CREATE TABLE** displays the DDL statement describing how the table is defined.
- **SHOW INDEX** displays the table's indexes and the properties of each key part.
- **SHOW TABLE STATUS** displays general overview information about the table and storage engine.

These three commands complement one another. When investigating a slow query, you can use `SHOW CREATE TABLE` to understand structure and constraints, `SHOW INDEX` to inspect existing indexes, and `SHOW TABLE STATUS` to view the engine, size estimates, and storage statistics. Results must be read within their limits: metadata describes observable structure and state, and does not by itself prove a query plan is optimal.

This lesson focuses on MySQL 8.x with InnoDB as the common storage engine.

## 1. Preparing a Table for Practice

Suppose a sales system has a customers table and an orders table:

~~~sql
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email       VARCHAR(255) NOT NULL,
    full_name   VARCHAR(150) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
~~~

This example includes several components to inspect:

- An auto-increment primary key for each table.
- A `UNIQUE` constraint ensuring emails do not duplicate.
- A foreign key linking orders to customers.
- Two composite indexes serving different query patterns.
- `DECIMAL` storing monetary values with exact decimal precision.
- `utf8mb4` and collation defining how strings are stored, compared, and sorted.

After creating the tables, we can use the three `SHOW` commands to see how MySQL records their structure and storage information.

## 2. SHOW CREATE TABLE: Viewing a Table's DDL Definition

### 2.1. Syntax and usage

`SHOW CREATE TABLE` returns the `CREATE TABLE` statement MySQL uses to describe the current table.

~~~sql
SHOW CREATE TABLE orders;
~~~

If no default database is selected, specify the schema explicitly:

~~~sql
SHOW CREATE TABLE shop.orders;
~~~

In the MySQL client, you can use `\G` to format output vertically, making long DDL easier to read:

~~~sql
SHOW CREATE TABLE shop.orders\G
~~~

The output normally has two columns:

| Column | Meaning |
|---|---|
| Table | Table name |
| Create Table | DDL statement describing the table structure |

The `Create Table` value can include column names, data types, `NULL`/`NOT NULL`, `DEFAULT`, `AUTO_INCREMENT`, primary key, indexes, constraints, engine, charset, collation, comments, partitions, and related options if present.

### 2.2. Reading components in the output

A shortened example of the output format:

~~~sql
CREATE TABLE orders (
  order_id bigint unsigned NOT NULL AUTO_INCREMENT,
  customer_id bigint unsigned NOT NULL,
  status varchar(30) NOT NULL,
  total decimal(13,2) NOT NULL,
  created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_created (customer_id,created_at),
  KEY idx_orders_status_created (status,created_at),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

This is an illustrative example of the main contents; actual formatting may vary by version, configuration, and table properties.

When reading DDL, inspect sequentially:

1. **Columns and data types:** are the types, lengths, precision, and scale accurate as required?
2. **NULL and DEFAULT:** which columns are required, which have defaults, and are default expressions used?
3. **Primary key:** does the table have a suitable and stable primary key?
4. **UNIQUE and foreign keys:** are business rules and relationships represented in the schema?
5. **Indexes:** do the names, column order, and index types fit the queries?
6. **Engine:** is the table using InnoDB as expected?
7. **Charset and collation:** do strings use the appropriate character set and comparison rules?
8. **Other options:** are comments, row format, partitions, generated columns, or special attributes declared properly?

### 2.3. SHOW CREATE TABLE is not a verbatim copy of the original script

MySQL may normalize how DDL is represented when returning results. Therefore, `SHOW CREATE TABLE` is useful for knowing the definition the server currently applies, but it does not necessarily reproduce the original migration file or script character for character.

Several points to keep in mind:

- Whitespace, letter case, and identifier quoting styles may differ.
- Default values or attributes may be formatted in the server's normalized style.
- Certain implicit options may be rendered explicitly in the output.
- DDL depends on the server version; re-running the statement on another version may require adjustments.

Therefore, use the output to inspect the current structure and assist with controlled migrations. If you need to track schema change history, manage migrations in version control rather than treating `SHOW` output as change history.

### 2.4. Access privileges and metadata scope

Users need appropriate privileges to view an object's metadata. In multi-schema environments, observable results may be restricted by the current account's privileges. If an object does not appear or its definition cannot be retrieved, check the default database, schema name, table name, and access privileges.

Do not use the `root` account merely to read table structures in applications or internal tools. Grant schema management or metadata read privileges appropriate to the operational role.

## 3. SHOW INDEX: Inspecting Indexes

### 3.1. Syntax

To view all indexes of a table:

~~~sql
SHOW INDEX FROM orders;
~~~

Specify the database explicitly:

~~~sql
SHOW INDEX FROM orders FROM shop;
~~~

`SHOW KEYS` is a common synonym:

~~~sql
SHOW KEYS FROM shop.orders;
~~~

You can filter results by index name or other attributes using a `WHERE` clause:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'idx_orders_customer_created';
~~~

### 3.2. Important columns in the output

`SHOW INDEX` returns one row per key part of an index. For a composite index consisting of multiple columns, a single index appears across multiple rows.

| Column | Meaning |
|---|---|
| Table | Table name |
| Non_unique | 0 if the index is declared unique; 1 if the index allows duplicate values |
| Key_name | Index name; PRIMARY is the primary key |
| Seq_in_index | Position of the key part in the index, starting at 1 |
| Column_name | Column name of the key part; may be NULL for expression-based key parts |
| Collation | Key part sort direction, typically A or D; may be NULL if not applicable |
| Cardinality | Estimated number of distinct values in the index or key prefix |
| Sub_part | Indexed prefix length, if any |
| Null | Indicates whether the key part can contain NULL |
| Index_type | Index type, such as BTREE |
| Comment | Additional index information |
| Index_comment | Comment declared by the index creator |
| Visible | Indicates whether the index is visible to the optimizer in versions supporting invisible indexes |
| Expression | Expression used as the key part for functional indexes in supported versions |

Not every version returns the exact same column set. Consult the documentation for your running MySQL version when writing automated scripts to parse the output.

With a unique index on a nullable column, MySQL can still accept multiple rows with `NULL` values. Thus, `Non_unique = 0` describes the index's uniqueness attribute, yet when verifying data rules you must also check column nullability.

### 3.3. Reading a single index

For the primary key:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'PRIMARY';
~~~

For a composite index:

~~~sql
SHOW INDEX FROM shop.orders
WHERE Key_name = 'idx_orders_customer_created';
~~~

If the index consists of `(customer_id, created_at)`, the output will have two key parts:

| Seq_in_index | Column_name |
|---:|---|
| 1 | customer_id |
| 2 | created_at |

This order matters. Composite B-tree indexes typically support conditions starting from the leftmost column effectively, known as the leftmost prefix rule. The index `(customer_id, created_at)` can support filtering by `customer_id`, or filtering by `customer_id` combined with a time condition. It usually does not replace an index on `created_at` alone for queries filtering only by `created_at`.

Examples:

~~~sql
-- Can leverage the leftmost prefix of the index
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42;

-- Can use both key parts
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01';

-- Cannot rely solely on leftmost prefix to conclude this index fits
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01';
~~~

The optimizer still decides the plan based on statistics and cost. The leftmost prefix rule helps understand an index's structural capability, not guarantee the index will always be chosen.

### 3.4. Cardinality is an estimated value

`Cardinality` is typically an estimate of the number of distinct values in the index or key prefix. InnoDB uses index statistics so the optimizer can estimate selectivity and plan cost.

Do not treat cardinality as an exact count at query time. Values can change after data changes or after statistics are updated. If stale statistics are suspected, consider:

~~~sql
ANALYZE TABLE shop.orders;
~~~

`ANALYZE TABLE` updates table and index statistics according to the storage engine's mechanism. This is an administrative operation that impacts server activity, so consider load and environment before running it on production systems.

### 3.5. Prefix indexes, functional indexes, and invisible indexes

`Sub_part` indicates the indexed prefix length when a prefix index is used. For example, on a long string column, an index might only index a leading portion of the value:

~~~sql
CREATE INDEX idx_customer_email_prefix
ON customers (email(32));
~~~

Prefix indexes can reduce index size, but they do not store the entire column value in the key part. They are not suitable for every query. If you create a unique prefix index, uniqueness is checked on the indexed prefix; this does not replace a `UNIQUE` constraint on the full value in all cases.

MySQL 8.0.13 and later support functional key parts. Example:

~~~sql
CREATE INDEX idx_customer_email_lower
ON customers ((LOWER(email)));
~~~

In `SHOW INDEX` output, the `Expression` column can show the indexed expression. Syntax and support depend on the version.

MySQL 8.0 also supports invisible indexes. An invisible index is still maintained as data changes, but the optimizer ignores it by default. The `Visible` attribute in `SHOW INDEX` output helps verify this status. Invisible indexes can assist in testing the impact of dropping an index before permanently deleting it, though every workload must be checked before deciding.

### 3.6. SHOW INDEX does not show whether an index is actually used

This command describes existing indexes and their properties. It does not indicate whether a specific query chooses that index, nor does it measure how many rows are actually read.

To inspect a query plan:

~~~sql
EXPLAIN
SELECT order_id, status, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the `SELECT` statement and adds actual iterator metrics. Use it only when running the real query against current data and incurring the corresponding load is acceptable.

## 4. SHOW TABLE STATUS: Viewing General Table Status

### 4.1. Syntax

View tables in the current database:

~~~sql
SHOW TABLE STATUS;
~~~

Specify a database and filter by name:

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders';
~~~

Or use a `WHERE` clause:

~~~sql
SHOW TABLE STATUS FROM shop
WHERE Name IN ('customers', 'orders');
~~~

The `LIKE` clause supports `%` and `_` wildcards. For example, `LIKE 'order%'` finds names starting with `order`.

### 4.2. Common columns

`SHOW TABLE STATUS` returns one row per listed table. Common columns include:

| Column | Meaning |
|---|---|
| Name | Table name |
| Engine | Table storage engine, e.g., InnoDB |
| Version | Internal format version field for compatibility; usually not needed by applications |
| Row_format | Row format reported by the engine, e.g., Dynamic or Compact |
| Rows | Row count; for InnoDB, usually an estimate |
| Avg_row_length | Estimated average row length in bytes |
| Data_length | Data size as reported by the engine in bytes |
| Max_data_length | Maximum data size as reported by the engine |
| Index_length | Index size as reported by the engine in bytes |
| Data_free | Free space reported by the engine; interpretation depends on engine and tablespace |
| Auto_increment | Reported next `AUTO_INCREMENT` value if the table has this attribute |
| Create_time | Table creation timestamp if provided by the engine |
| Update_time | Most recent data update timestamp if provided by the engine; may be NULL or unreliable with InnoDB |
| Check_time | Table check timestamp if supported by the engine |
| Collation | Default collation of the table |
| Checksum | Checksum if supported by the engine |
| Create_options | Additional table creation options |
| Comment | Table comment |

Exact column sets and values can vary across storage engines and MySQL versions. `SHOW TABLE STATUS` is primarily useful for overview checks; do not treat every field as an exact figure or as having identical meaning across all engines.

### 4.3. Interpreting size and row-count fields

For InnoDB, `Rows` is typically a statistical estimate rather than an exact count. If you need an exact row count, run:

~~~sql
SELECT COUNT(*) FROM shop.orders;
~~~

On large tables, `COUNT(*)` still has to perform data-reading work according to the execution plan and transaction state. Do not repeatedly run count queries on large tables just to replace statistical monitoring.

`Data_length` and `Index_length` help observe data and index scale, though how engines calculate and report them can differ. With InnoDB, table data is organized inside the clustered index; therefore `Data_length` relates to the clustered index size, while `Index_length` primarily reflects secondary indexes as reported by the engine.

`Data_free` does not equate to disk space that can be immediately reclaimed. It may represent free space inside a tablespace or extents managed by the engine. For shared tablespaces, the value can reflect a scope wider than a single table. Do not treat `Data_free` as guaranteed space that can be returned to the operating system.

`Update_time` also requires caution. With InnoDB, this field may not be updated or may return `NULL` depending on version and storage layout. Do not rely on it as the sole source for determining when a table's data last changed.

### 4.4. Checking engine and collation

A quick query:

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

Check at minimum:

- Whether `Engine` is indeed `InnoDB`.
- Whether `Collation` matches the application's string comparison rules.
- Whether `Rows` is reasonable at an estimate level compared to expected scale.
- Whether `Data_length` and `Index_length` show unusual changes across monitoring intervals.
- Whether `Create_options` and `Comment` contain details needing review.

If inspecting a table using another engine, factor in that engine's characteristics before interpreting size, row count, or `data_free`.

## 5. Using All Three Commands Together in One Inspection

Suppose a query listing orders by customer is slow:

~~~sql
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

An inspection workflow can follow these steps:

**Step 1: Verify the table definition**

~~~sql
SHOW CREATE TABLE shop.orders\G
~~~

Check the `customer_id` data type, primary key, engine, and constraints. Confirm whether the table declares a composite index matching the filter condition and time ordering.

**Step 2: Verify indexes**

~~~sql
SHOW INDEX FROM shop.orders;
~~~

Check whether an index contains `customer_id` in the first position and `created_at` in the next position. Check whether the index is visible, whether key parts are in the right order, and whether cardinality looks reasonable.

**Step 3: Check table overview information**

~~~sql
SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

Check the engine, estimated rows, data size, and index size. If the table is much larger than expected or statistics appear stale, investigate further.

**Step 4: Inspect the query plan**

~~~sql
EXPLAIN
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Read `key`, `type`, `rows`, `filtered`, and `Extra` in tabular `EXPLAIN` output. With JSON format, inspect `used_key_parts`, row estimates, and cost. No single `type` or `key` value is enough to conclude performance; consider actual rows, selectivity, and returned data.

**Step 5: Measure actual execution if needed**

~~~sql
EXPLAIN ANALYZE
SELECT order_id, status, total, created_at
FROM shop.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

`EXPLAIN ANALYZE` executes the `SELECT`, so use it in an appropriate environment and timing window. Compare estimated rows with actual rows, per-iterator timing, and loop counts to pinpoint where work occurs.

## 6. Comparing with INFORMATION_SCHEMA

`SHOW` commands are convenient for operators doing quick manual checks. When you need structured metadata queries, multi-table aggregations, or report exports, `INFORMATION_SCHEMA` is usually a better fit.

Useful metadata tables include:

| Table | Information |
|---|---|
| `INFORMATION_SCHEMA.TABLES` | One row per table or view, including engine, row estimate, sizes, and timestamps |
| `INFORMATION_SCHEMA.COLUMNS` | Columns, data types, NULL, default, collation, and column order |
| `INFORMATION_SCHEMA.STATISTICS` | Index key parts, order, cardinality, and index attributes |
| `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` | Constraint types such as PRIMARY KEY, UNIQUE, FOREIGN KEY, and CHECK |
| `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` | Columns participating in keys and referenced relationships |
| `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` | Foreign key referential rules |

Example retrieving index info via `INFORMATION_SCHEMA`:

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Example retrieving table info:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_TYPE = 'BASE TABLE';
~~~

`INFORMATION_SCHEMA` allows combining metadata across many tables in one query. However, statistical columns such as `TABLE_ROWS`, `DATA_LENGTH`, and `INDEX_LENGTH` can still be estimates or engine-dependent; switching to `INFORMATION_SCHEMA` does not turn statistics into exact counts.

### 6.1. SHOW or INFORMATION_SCHEMA?

| Need | Suitable approach |
|---|---|
| Quickly read a table's DDL | `SHOW CREATE TABLE` |
| Check index order and attributes | `SHOW INDEX` |
| View engine and table size overview | `SHOW TABLE STATUS` |
| Aggregate metadata across multiple tables | `INFORMATION_SCHEMA` |
| Build filtered and joined schema reports | `INFORMATION_SCHEMA` |
| Inspect a query's execution plan | `EXPLAIN` or `EXPLAIN ANALYZE` |
| Determine which index a query is using | `EXPLAIN`, Performance Schema, or appropriate monitoring tools |

No single command replaces all of the checks above. Choose the tool based on the question you need to answer.

## 7. Limitations and Operational Notes

### 7.1. Metadata reflects the current state

`SHOW CREATE TABLE` describes the current structure. If a schema is altered via migrations, `ALTER TABLE`, or an admin tool, the output reflects the post-change structure. It does not tell you who made the change or when.

To trace schema history, rely on migration files, version control, audit logs, or proper change management processes.

### 7.2. Cardinality and row counts may be estimates

InnoDB uses statistics to estimate cardinality and row counts. The numbers may not match current data precisely. When needed, update statistics with `ANALYZE TABLE`, then re-check the execution plan and measure performance.

### 7.3. Size does not equate to reclaimable space

`Data_length`, `Index_length`, and `Data_free` are engine-reported metrics. They do not always map directly to file sizes that can be deleted or returned to the operating system. With InnoDB, consider tablespaces, file-per-table, shared tablespaces, undo tablespaces, and extent allocation.

### 7.4. Results depend on privileges and database scope

If a table is missing from output, check:

- Is the right database selected?
- Is the schema specified in the command?
- Is the table name spelled accurately?
- Does the account have privileges to view the object and its metadata?
- Is the object actually a base table or a view?

`SHOW TABLE STATUS` primarily lists table status; to inspect views and combined table/view metadata, use `INFORMATION_SCHEMA.TABLES` and related metadata views.

### 7.5. Do not use SHOW INDEX as a substitute for performance testing

Having an index present does not guarantee the optimizer uses it. Conversely, a table scan is not always wrong: if a table is small or a condition selects most rows, a table scan can be cheaper. Always cross-check metadata with execution plans and runtime metrics.

## 8. Example Pre-Release Schema Check

Before releasing an application version with new migrations, developers can follow this process in a test environment:

1. Run the migration that creates or alters tables.
2. Use `SHOW CREATE TABLE` to verify data types, defaults, constraints, engine, and collation match the design.
3. Use `SHOW INDEX` to verify new indexes have the right names, key-part order, uniqueness, and visibility.
4. Use `SHOW TABLE STATUS` to confirm the table exists and uses the required engine.
5. Run representative queries with `EXPLAIN` to see whether the optimizer can use indexes as intended.
6. Run data and transaction tests to verify constraints work properly.
7. Archive the check results or migration report alongside the application version.

Example quick post-migration check queries:

~~~sql
SHOW CREATE TABLE shop.orders\G

SHOW INDEX FROM shop.orders;

SHOW TABLE STATUS FROM shop LIKE 'orders'\G
~~~

The commands above only read metadata; they do not replace data-write tests, rollback tests, or application compatibility checks.

## 9. Common Misconceptions

**"SHOW CREATE TABLE returns the exact original SQL file that created the table."** Not necessarily. MySQL can normalize and supplement how attributes are represented.

**"SHOW INDEX shows which index a query is using."** No. It lists existing indexes; you need `EXPLAIN` to inspect a specific query's plan.

**"Cardinality is the exact number of distinct values."** No. It is usually a statistical estimate, especially with InnoDB.

**"Rows in SHOW TABLE STATUS is an exact row count."** No. With InnoDB, it is usually an estimate. Use `COUNT(*)` if an exact count is truly needed and the query cost is acceptable.

**"Data_free is guaranteed disk space you can reclaim."** No. It depends on the engine and how tablespaces are managed.

**"If an index appears in SHOW INDEX, the optimizer will definitely use it."** No. The optimizer picks plans based on statistics and cost.

**"SHOW TABLE STATUS replaces INFORMATION_SCHEMA."** No. `SHOW` suits quick checks; `INFORMATION_SCHEMA` is suited for querying, aggregating, and reporting metadata.

## Conclusion

`SHOW CREATE TABLE`, `SHOW INDEX`, and `SHOW TABLE STATUS` are three foundational tools for inspecting schemas and metadata in MySQL. The first reveals the current DDL definition; the second reveals index structure and properties; the third provides an overview of the engine, estimated row count, and table sizes.

When reviewing designs or investigating queries, combine all three commands with `EXPLAIN`, `EXPLAIN ANALYZE`, and `INFORMATION_SCHEMA` as needed. Always distinguish declared structure from estimated statistics, and distinguish an existing index from an index actually chosen by the optimizer. Reading metadata accurately keeps schema management, keys, indexes, queries, and MySQL operations grounded in evidence.
