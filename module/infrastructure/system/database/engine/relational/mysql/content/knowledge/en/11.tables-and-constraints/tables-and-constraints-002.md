# CREATE TABLE, DEFAULT, NOT NULL, and Default Value Expressions

## Objectives

After this lesson, you will be able to:

- Create tables with `CREATE TABLE` using appropriate data types, column attributes, and table options.
- Distinguish between `NULL`, `NOT NULL`, `DEFAULT`, and values passed by the application.
- Predict how MySQL handles omitted columns, columns assigned `DEFAULT`, and columns passed `NULL`.
- Declare literal default values, `CURRENT_TIMESTAMP`, and default expressions.
- Understand the impact of strict SQL mode when values are missing or `NULL` is passed into a `NOT NULL` column.
- Inspect DDL, metadata, and warnings to verify that the table structure matches the design.

## 1. The Role of CREATE TABLE in Data Design

`CREATE TABLE` defines the storage structure for a dataset: each column's name and type, nullability, default values, keys, indexes, constraints, storage engine, character set, and collation. These decisions affect data integrity, how applications write records, query performance, and the ability to evolve the schema later.

For example, an orders table might need:

- An auto-incrementing order ID that always has a value.
- A mandatory customer ID.
- An initial status of `PENDING` if the application does not supply a status.
- A monetary amount defaulting to 0 that must not be `NULL`.
- Creation and update timestamps.
- An optional notes column that can be `NULL`.

A good design expresses data rules directly in the schema. The application must still validate business logic, but the database should guard fundamental invariants so every client writing data complies with them.

## 2. Basic Structure of CREATE TABLE

General syntax:

```sql
CREATE TABLE [IF NOT EXISTS] table_name (
    column_name data_type [column_attributes],
    ...,
    [table_constraints]
)
[ENGINE = storage_engine]
[DEFAULT CHARACTER SET = charset_name]
[COLLATE = collation_name];
```

An example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_status (status)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

In this example:

- `customer_id` is an auto-incrementing primary key and does not accept `NULL`.
- `full_name` and `email` are mandatory data.
- `phone` is optional data.
- `status` receives `ACTIVE` if an `INSERT` statement does not supply a value for this column.
- `created_at` receives the current timestamp upon row creation if not specified.
- `UNIQUE KEY` ensures emails do not duplicate according to the column's collation rules.
- `InnoDB` provides transactions and standard data integrity capabilities.
- `utf8mb4` supports Unicode data; the collation determines how strings are compared.

The `utf8mb4_0900_ai_ci` collation is available in MySQL 8.0. If you use a different version or distribution, check `SHOW COLLATION` and choose a supported collation.

### 2.1. IF NOT EXISTS Does Not Verify the Schema

`CREATE TABLE IF NOT EXISTS` suppresses the error simply because the table already exists:

```sql
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT NOT NULL PRIMARY KEY
);
```

If the `customers` table already exists with different data types, indexes, or defaults, the statement neither modifies the structure nor verifies that the two definitions match. Therefore, migrations should not treat successful execution of this statement as proof that the schema is correct. Verify using `SHOW CREATE TABLE` or a schema management tool.

## 3. NULL and NOT NULL

### 3.1. What Does NULL Represent?

`NULL` represents an unknown, absent, or unprovided value according to application semantics. It differs from:

- An empty string `''`.
- The number zero `0`.
- The string `'0'`.
- Boolean `FALSE`.
- A placeholder date such as `'0000-00-00'`.

For example:

```sql
CREATE TABLE customer_profiles (
    profile_id BIGINT NOT NULL PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(100) NULL,
    login_count INT NOT NULL DEFAULT 0
);
```

`middle_name` may be unknown or absent, so it can be `NULL`. `login_count` always holds an integer; when creating a record without supplying a login count, the database uses 0.

### 3.2. NOT NULL Establishes a Mandatory Condition

Declaring `NOT NULL` requires the column to have a non-`NULL` value after MySQL processes the write statement. For example:

```sql
CREATE TABLE products (
    product_id BIGINT NOT NULL PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    description TEXT NULL
);
```

`product_name` must have a value; `description` may have no content.

`NOT NULL` does not automatically guarantee the string has meaningful content. `product_name = ''` is still a non-NULL string in SQL terms and can be stored. If you need to forbid whitespace-only strings, the application or an appropriate constraint must check it separately.

### 3.3. Comparing NULL Must Use IS NULL

Do not use `= NULL` or `<> NULL` to test for NULL values:

```sql
-- Correct
SELECT * FROM customer_profiles
WHERE middle_name IS NULL;

SELECT * FROM customer_profiles
WHERE middle_name IS NOT NULL;
```

SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. Standard comparisons with `NULL` evaluate to UNKNOWN, so `WHERE middle_name = NULL` does not match rows whose value is NULL.

## 4. What Does DEFAULT Mean?

`DEFAULT` declares the value MySQL uses when an `INSERT` statement omits that column, or when the statement explicitly specifies the `DEFAULT` keyword for the column.

For example:

```sql
CREATE TABLE tasks (
    task_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id)
);
```

The following writes behave differently:

```sql
-- Omit status and retry_count: MySQL uses DEFAULT
INSERT INTO tasks (title)
VALUES ('Send welcome email');

-- Explicitly specify DEFAULT for status and retry_count
INSERT INTO tasks (title, status, retry_count)
VALUES ('Generate report', DEFAULT, DEFAULT);

-- Specify explicit values: DEFAULT is not used
INSERT INTO tasks (title, status, retry_count)
VALUES ('Import customers', 'RUNNING', 2);
```

In the first case, `status` is `PENDING` and `retry_count` is 0. In the second case, MySQL uses the declared defaults. The third case stores the passed-in values.

### 4.1. DEFAULT Does Not Automatically Replace NULL

This is a critical point:

```sql
INSERT INTO tasks (title, status)
VALUES ('Task A', DEFAULT);

INSERT INTO tasks (title, status)
VALUES ('Task B', NULL);
```

The first statement asks to use the default value. The second statement explicitly passes `NULL`. For the `status NOT NULL` column, the second statement is rejected under strict SQL mode; under non-strict mode, MySQL may substitute the data type's implicit default and emit a warning. Do not rely on this implicit conversion behavior.

For a nullable column, passing `NULL` stores `NULL` rather than triggering `DEFAULT`. To use the default, omit the column from the insert column list or use the `DEFAULT` keyword.

### 4.2. DEFAULT vs. Application Initial Values

If Java always sends `status = 'PENDING'`, the database does not use the default because the application already supplied a value. If a batch import, admin script, or another service omits the column, then the database applies the default. Declaring defaults in the database establishes a common rule for all clients, though the application still needs to decide when to pass explicit values.

## 5. Literal Default Values

### 5.1. Strings and Numbers

Simple default values can be declared directly:

```sql
CREATE TABLE inventory (
    item_id BIGINT NOT NULL AUTO_INCREMENT,
    item_name VARCHAR(150) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    item_status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    unit_price DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (item_id)
);
```

- Strings are enclosed in single quotes.
- Numbers are written as numeric literals without quotes.
- Boolean values in MySQL can be written as `TRUE`/`FALSE`; they correspond to 1/0.
- The default must be compatible with the column's data type and value domain.

### 5.2. DEFAULT NULL

For nullable columns, you can declare it explicitly:

```sql
CREATE TABLE profiles (
    profile_id BIGINT NOT NULL PRIMARY KEY,
    nickname VARCHAR(80) NULL DEFAULT NULL
);
```

In many cases, a nullable column without a declared default also has an implicit default of `NULL`. Explicitly declaring `DEFAULT NULL` can make the intent clearer to readers of the DDL. Do not declare `DEFAULT NULL` on a `NOT NULL` column.

### 5.3. Be Careful with Implicit Defaults

Omitting `DEFAULT` does not mean every column has a useful default value. For a `NOT NULL` column without a default, if an `INSERT` omits that column, the outcome depends on the SQL mode:

- Under strict mode, the statement is typically rejected because the column has no default value.
- Under non-strict mode, MySQL may insert the data type's implicit default and emit a warning.

Type-based implicit defaults can be 0 for numeric types, an empty string for string types, or a zero-date in certain configurations/contexts. Those values rarely represent valid business data. Declare intentional defaults or require the application to supply the data.

## 6. DEFAULT for Date and Time

MySQL supports `CURRENT_TIMESTAMP` as a default for `TIMESTAMP` and `DATETIME` columns:

```sql
CREATE TABLE audit_events (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
);
```

- `DEFAULT CURRENT_TIMESTAMP` assigns the current timestamp on insert when the column is omitted.
- `ON UPDATE CURRENT_TIMESTAMP` automatically updates the timestamp when the row is modified according to MySQL's rules.
- Both attributes can specify fractional seconds precision, such as `CURRENT_TIMESTAMP(6)` for `TIMESTAMP(6)` or `DATETIME(6)` columns.

Example with microseconds:

```sql
CREATE TABLE api_requests (
    request_id BIGINT NOT NULL AUTO_INCREMENT,
    request_path VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_id)
);
```

`TIMESTAMP` is converted by MySQL between the session timezone and UTC on write/read. `DATETIME` stores calendar date and time components without automatic timezone conversion. Therefore, `DEFAULT CURRENT_TIMESTAMP` on a `DATETIME` column stores the time value according to the session timezone at the moment of insert; a clear timezone policy is required to avoid mixed-timezone data.

`ON UPDATE CURRENT_TIMESTAMP` is not a general-purpose trigger. It attaches automatic update behavior to a timestamp column when the row changes. If you need updates based on complex business conditions, use application logic or a carefully designed trigger.

## 7. Default Value Expressions

### 7.1. Expression Defaults Since MySQL 8.0.13

Starting in MySQL 8.0.13, expressions can be used as column default values. The expression must be enclosed in parentheses, except for the special `CURRENT_TIMESTAMP` syntax for `TIMESTAMP`/`DATETIME`.

For example:

```sql
CREATE TABLE calculation_settings (
    setting_id BIGINT NOT NULL AUTO_INCREMENT,
    retry_limit INT NOT NULL DEFAULT (2 + 3),
    label VARCHAR(80) NOT NULL DEFAULT (LOWER('UNSET')),
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    PRIMARY KEY (setting_id)
);
```

When inserting while omitting these columns, MySQL evaluates the default expression according to expression and column type rules. `retry_limit` receives the result of `2 + 3`; `label` receives the lowercase string; `metadata` receives an empty JSON object.

Default expressions help the database generate values according to a consistent rule. However, avoid using complex expressions to hide business logic that the application should control.

### 7.2. Limitations of Default Expressions

A default expression is not an arbitrary query. It cannot reference other columns in the same row, and cannot contain subqueries, variables, parameters, or stored/loadable functions. Only use expressions and built-in functions supported by your MySQL version in the default context.

The following example is invalid because `total`'s default references other columns:

```sql
-- Invalid: DEFAULT cannot reference unit_price or quantity
CREATE TABLE order_lines_invalid (
    unit_price DECIMAL(12,2) NOT NULL,
    quantity INT NOT NULL,
    total DECIMAL(14,2) NOT NULL DEFAULT (unit_price * quantity)
);
```

If a column must be computed from other columns, consider a generated column:

```sql
CREATE TABLE order_lines (
    line_id BIGINT NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12,2) NOT NULL,
    quantity INT NOT NULL,
    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (unit_price * quantity) STORED,
    PRIMARY KEY (line_id)
);
```

A generated column is a value computed from other columns per the schema definition; it is not a default. Applications do not write values directly to a generated column the way they write to normal columns.

### 7.3. Defaults for JSON, TEXT, and BLOB

In MySQL 8.0.13 and later, types such as `JSON`, `TEXT`, and `BLOB` can have defaults when declared as parenthesized expressions. For example:

```sql
CREATE TABLE documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    attributes JSON NOT NULL DEFAULT (JSON_OBJECT()),
    content TEXT NOT NULL DEFAULT ('') ,
    PRIMARY KEY (document_id)
);
```

Older MySQL versions do not support expression defaults in this way. If backward compatibility with older versions is needed, omit defaults on columns of those types and have the application supply an explicit value on insert, or use an alternative design suited to the requirements.

### 7.4. Checking Version Compatibility

Before deploying expression defaults, verify the version:

```sql
SELECT VERSION();
```

Then test creating the table in an equivalent environment and inspect the DDL:

```sql
SHOW CREATE TABLE calculation_settings\G
```

MariaDB and other MySQL-compatible distributions may have different support timelines and limitations. Do not assume support simply because syntax runs on a development machine.

## 8. NOT NULL, DEFAULT, and SQL Mode

SQL mode affects how MySQL handles missing or invalid data. In particular, strict mode helps catch inserts missing mandatory values early.

Check the mode:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

### 8.1. Omitting a NOT NULL Column Without a DEFAULT

Suppose:

```sql
CREATE TABLE employees (
    employee_id BIGINT NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(150) NOT NULL,
    department_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (employee_id)
);
```

The following statement omits `department_code`:

```sql
INSERT INTO employees (employee_name)
VALUES ('Nguyen An');
```

In strict SQL mode, MySQL rejects it because `department_code` has no default value. In non-strict mode, the server may use the type's implicit default and emit a warning. Do not rely on non-strict behavior to populate business data.

### 8.2. Passing NULL into a NOT NULL Column

```sql
INSERT INTO employees (employee_name, department_code)
VALUES ('Tran Binh', NULL);
```

In strict mode, MySQL raises an error because the column does not accept `NULL`. In non-strict mode, MySQL may substitute the implicit default and emit a warning. Even if a column has an explicit default, `NULL` does not automatically trigger the default.

### 8.3. Checking Warnings Immediately After a Statement

Immediately after an insert/update statement that might raise warnings, run:

```sql
SHOW WARNINGS;
```

Also inspect the written data:

```sql
SELECT employee_id, employee_name, department_code
FROM employees
ORDER BY employee_id DESC
LIMIT 5;
```

`INSERT IGNORE` can downgrade certain errors to warnings and coerce data so the insert continues. Do not use `IGNORE` as a workaround for `NOT NULL` errors or invalid data; understand the warnings and verify the rows afterward.

## 9. Practical Table Design Example

Example of an orders table with clear defaults:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    subtotal DECIMAL(19,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(19,2) NOT NULL DEFAULT 0.00,
    note VARCHAR(500) NULL DEFAULT NULL,
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (order_status, created_at)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

The design above assumes MySQL 8.0.13 or higher because it uses an expression default for JSON. On older versions, remove the JSON default and require the application to pass `JSON_OBJECT()` or valid JSON on insert. Verify that the target collation is supported on the server.

Illustrative inserts:

```sql
-- Database provides status, currency, default amounts, metadata, and timestamps
INSERT INTO orders (customer_id)
VALUES (1001);

-- Application overrides defaults with explicit values
INSERT INTO orders (
    customer_id,
    order_status,
    currency_code,
    subtotal,
    metadata
)
VALUES (
    1002,
    'CONFIRMED',
    'USD',
    125.50,
    JSON_OBJECT('source', 'web')
);

-- Use explicit DEFAULT for specific columns
INSERT INTO orders (customer_id, order_status, subtotal)
VALUES (1003, DEFAULT, DEFAULT);
```

Verification query:

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    currency_code,
    subtotal,
    discount_amount,
    note,
    metadata,
    created_at,
    updated_at
FROM orders
ORDER BY order_id;
```

Note: defaulting to `VND` is only appropriate if the business truly treats VND as the default currency. If users or orders can use multiple currencies, the application should pass the currency explicitly instead of relying on a default that could cause business errors.

## 10. Inspecting Definitions and Metadata After Creating a Table

### 10.1. SHOW CREATE TABLE

The most important command to inspect the actual MySQL DDL:

```sql
SHOW CREATE TABLE orders\G
```

Check:

- Data types, lengths, unsigned, and precision/scale.
- `NULL`/`NOT NULL`.
- `DEFAULT` values and expression defaults.
- `AUTO_INCREMENT`.
- `ON UPDATE` for timestamp columns.
- Primary key, unique keys, and indexes.
- Engine, character set, and collation.

### 10.2. INFORMATION_SCHEMA.COLUMNS

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    GENERATION_EXPRESSION,
    ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

`IS_NULLABLE` indicates whether the column accepts NULL. `COLUMN_DEFAULT` shows the default exposed in metadata; how expression defaults are represented may vary by version. `EXTRA` can indicate `auto_increment`, `DEFAULT_GENERATED`, or additional attributes. `GENERATION_EXPRESSION` is used for generated columns.

### 10.3. Checking Engine and Charset/Collation

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

Metadata helps verify the live schema after migrations. Do not rely solely on migration files or executed scripts; inspect the actual server serving the application.

## 11. Modifying DEFAULT and NOT NULL on Tables with Existing Data

### 11.1. Adding or Changing DEFAULT

Change a column's default:

```sql
ALTER TABLE orders
    ALTER COLUMN order_status SET DEFAULT 'PENDING';
```

Or drop a default:

```sql
ALTER TABLE orders
    ALTER COLUMN order_status DROP DEFAULT;
```

Changing a default does not update values in existing rows. It affects subsequent inserts when the column is omitted or given `DEFAULT`.

### 11.2. Changing a Column from Nullable to NOT NULL

Before making the change, find rows currently containing `NULL`:

```sql
SELECT COUNT(*) AS null_status_count
FROM orders
WHERE order_status IS NULL;
```

If NULL data exists, decide the replacement value based on business rules and update in a controlled manner. For example, only if business rules confirm legacy statuses should be treated as `PENDING`:

```sql
UPDATE orders
SET order_status = 'PENDING'
WHERE order_status IS NULL;
```

Then alter the column definition preserving all required attributes:

```sql
ALTER TABLE orders
    MODIFY order_status VARCHAR(20)
        NOT NULL DEFAULT 'PENDING';
```

`MODIFY` requires re-declaring the type and important attributes. Before running it, pull `SHOW CREATE TABLE` so you do not accidentally lose comments, custom charset/collation, defaults, or other attributes.

For large tables, `ALTER TABLE` may rebuild the table or hold metadata locks for a period of time. Check DDL algorithms, online capabilities, disk space, and lock durations on the exact MySQL version before deploying.

## 12. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Setting `NOT NULL` for genuinely optional data | Applications must send dummy values or inserts fail | Clarify whether the business allows missing data |
| Using `DEFAULT 0` for every number | 0 can be confused with unknown/uncalculated | Use 0 only when it is a valid business value; if unknown, consider NULL |
| Assuming `DEFAULT` replaces `NULL` | Inserts passing NULL do not use the default | Omit the column or use the `DEFAULT` keyword when you want the default |
| Relying on implicit defaults in non-strict mode | Data may unexpectedly receive 0/empty string/zero-date | Use strict mode, declare explicit defaults, and check warnings |
| Using double quotes for string defaults | Can fail when `ANSI_QUOTES` is enabled | Use single quotes for string literals |
| Using expression defaults without checking version | DDL may fail on older servers | Verify MySQL 8.0.13+ and test on the deployment version |
| Using DEFAULT to compute from other columns | Invalid DDL or wrong mechanism for the intent | Use a generated column or application logic |
| Using `IF NOT EXISTS` and assuming the schema matches | Existing table may retain a different definition | Verify with `SHOW CREATE TABLE` and schema migrations |
| Changing to NOT NULL without auditing existing data | DDL fails or data is silently coerced | Count NULLs, clean up data, and verify SQL mode first |

## 13. Checklist Before Creating or Altering a Table

- [ ] Table/column names are meaningful, consistent, and avoid unnecessary reserved words.
- [ ] Data types cover the value domain, precision, and scale.
- [ ] Mandatory columns use `NOT NULL`; genuinely optional columns use `NULL`.
- [ ] `DEFAULT` reflects a valid business value, not a placeholder to avoid errors.
- [ ] Cases of omitting a column, using `DEFAULT`, and passing `NULL` are clearly distinguished.
- [ ] Date/time defaults align with the timezone policy.
- [ ] Expression defaults are supported by the target MySQL version.
- [ ] Defaults do not reference other columns; generated columns are considered when needed.
- [ ] Primary key, indexes, and constraints match query and integrity needs.
- [ ] Engine, character set, and collation are explicitly specified or verified.
- [ ] `SHOW CREATE TABLE`, `INFORMATION_SCHEMA`, and warnings are checked after migration.
- [ ] Locking, disk space, and online DDL capability are evaluated when altering large tables.

## 14. Conclusion

`CREATE TABLE` is where a system's structure and part of its data rules are defined. `NOT NULL` requires a column to have a value, while `DEFAULT` supplies a value when an insert omits the column or requests the `DEFAULT` keyword. Passing `NULL` is a distinct action and does not automatically trigger the default.

Declare data types, nullability, and defaults according to business semantics. Use `CURRENT_TIMESTAMP` for creation/update timestamps where appropriate; only use expression defaults on supported versions; verify SQL mode to prevent unintended implicit defaults. After creating or modifying a schema, verify it using `SHOW CREATE TABLE` and MySQL Server's own metadata.
