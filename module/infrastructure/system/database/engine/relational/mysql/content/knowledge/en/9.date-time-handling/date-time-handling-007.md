# DEFAULT CURRENT_TIMESTAMP and ON UPDATE CURRENT_TIMESTAMP

MySQL can automatically assign creation timestamps and update modification timestamps via two column attributes: `DEFAULT CURRENT_TIMESTAMP` and `ON UPDATE CURRENT_TIMESTAMP`. They are commonly used for `created_at` and `updated_at` columns in business tables.

`DEFAULT CURRENT_TIMESTAMP` provides a timestamp when an `INSERT` omits a value for the column. `ON UPDATE CURRENT_TIMESTAMP` tells MySQL to update the column whenever a row changes. Each attribute can be used independently or combined. For clear behavior, schemas typically declare both for `updated_at`, while `created_at` only needs the default value.

This lesson explains how they work, syntax, fractional seconds precision, time zone differences between `TIMESTAMP` and `DATETIME`, special update cases, and how to test behavior on MySQL 8.x.

## 1. What Is DEFAULT CURRENT_TIMESTAMP Used For?

`DEFAULT` specifies the value MySQL uses when an `INSERT` statement omits a value for the column or explicitly specifies `DEFAULT`.

Example:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

When inserting a row without `created_at`:

```sql
INSERT INTO articles (title)
VALUES ('Introduction to MySQL');

SELECT id, title, created_at
FROM articles;
```

MySQL automatically uses the current timestamp as `created_at`. The application does not need to generate a timestamp manually for routine inserts.

You can also instruct MySQL to use the default explicitly:

```sql
INSERT INTO articles (title, created_at)
VALUES ('Schema Design', DEFAULT);
```

Both approaches apply the default value:

- Omitting the column from the `INSERT` column list.
- Passing the `DEFAULT` keyword in the column's value slot.

`DEFAULT CURRENT_TIMESTAMP` does not mean MySQL overwrites a value supplied by the application. If an `INSERT` provides a specific valid value, MySQL uses that value.

## 2. What Is ON UPDATE CURRENT_TIMESTAMP Used For?

`ON UPDATE CURRENT_TIMESTAMP` automatically updates the timestamp when a row is modified. Example:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

The two columns have distinct responsibilities:

- `created_at` records the creation instant. Because it has no `ON UPDATE`, its value does not change automatically when the row is updated.
- `updated_at` receives the current timestamp on insert and updates automatically whenever the row changes.

Example:

```sql
INSERT INTO articles (title)
VALUES ('Table Design');

SELECT id, title, created_at, updated_at
FROM articles;

UPDATE articles
SET title = 'MySQL Table Design'
WHERE id = 1;

SELECT id, title, created_at, updated_at
FROM articles
WHERE id = 1;
```

After the `UPDATE` changes `title`, MySQL automatically updates `updated_at`. `created_at` stays unchanged.

## 3. Combining DEFAULT and ON UPDATE

For a column that should receive the current timestamp on creation and update automatically on modification, declare both attributes:

```sql
updated_at DATETIME NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP
```

This is the standard pattern for modification timestamp columns. If you only declare `ON UPDATE CURRENT_TIMESTAMP` without `DEFAULT`, the insert default depends on NULL/NOT NULL settings and data-type default rules. Therefore, always declare `DEFAULT` explicitly when you want a deterministic initial timestamp.

You can write `CURRENT_TIMESTAMP()` with parentheses or `CURRENT_TIMESTAMP` without them. `NOW()` is a synonym for `CURRENT_TIMESTAMP` in SQL expressions, though in DDL `CURRENT_TIMESTAMP` is preferred to express the automatic column attribute clearly.

## 4. Practical Example with created_at and updated_at

An accounts table can be designed as follows:

```sql
CREATE TABLE customer_accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_accounts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Insert an account:

```sql
INSERT INTO customer_accounts (email, display_name)
VALUES ('linh@example.test', 'Nguyen Linh');
```

There is no need to pass `created_at` or `updated_at`; MySQL assigns defaults to both.

Update the display name:

```sql
UPDATE customer_accounts
SET display_name = 'Linh Nguyen'
WHERE email = 'linh@example.test';
```

`updated_at` updates automatically; `created_at` does not change. This gives applications a simple way to display when a record was created and last modified.

## 5. Conditions That Trigger ON UPDATE

MySQL automatically updates a column with `ON UPDATE CURRENT_TIMESTAMP` only when a row's values actually change. Simply executing an `UPDATE` statement does not always change the timestamp.

For example, if `display_name` is already `'Linh Nguyen'`:

```sql
UPDATE customer_accounts
SET display_name = 'Linh Nguyen'
WHERE email = 'linh@example.test';
```

If no column actually changes value, `updated_at` does not update just because the statement ran.

Conversely, changing any other column in the same row can trigger the timestamp update:

```sql
UPDATE customer_accounts
SET is_active = FALSE
WHERE email = 'linh@example.test';
```

If `is_active` transitions from `TRUE` to `FALSE`, `updated_at` is updated. This mechanism does not watch a single specific column like `display_name`; it watches for any change to the row.

## 6. Explicitly Overriding or Suppressing Timestamp Updates

The application can still pass an explicit value to a column with `ON UPDATE`.

### 6.1. Writing a Specific Timestamp

```sql
UPDATE customer_accounts
SET display_name = 'Linh N.',
    updated_at = '2026-11-19 09:30:00'
WHERE id = 1;
```

When an explicit value is provided for `updated_at`, MySQL uses the supplied value instead of auto-generating the current time. This can be useful during historical imports or data synchronization, provided time zones and clock sources are properly controlled.

### 6.2. Keeping the Timestamp Unchanged During an Update

If you need to update another column while keeping `updated_at` untouched, explicitly assign the column to its current value:

```sql
UPDATE customer_accounts
SET display_name = 'Linh N.',
    updated_at = updated_at
WHERE id = 1;
```

When the timestamp column is explicitly assigned its own current value, the auto-update rule does not replace it. Use this only when business logic genuinely requires skipping the update timestamp; if done frequently, consider designing a separate column or data flow to represent non-business changes.

## 7. INSERT, NULL, and DEFAULT

Distinguish three cases:

| Insert Form | Behavior |
| --- | --- |
| Column omitted | MySQL uses the column's default if defined |
| `DEFAULT` specified | MySQL uses the column's default |
| `NULL` passed | Nullable column receives `NULL`; `NOT NULL` column typically errors in strict mode |

Example with a nullable column:

```sql
CREATE TABLE optional_dates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(80) NOT NULL,
    happened_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO optional_dates (label)
VALUES ('Use default');

INSERT INTO optional_dates (label, happened_at)
VALUES ('Explicitly NULL', NULL);

INSERT INTO optional_dates (label, happened_at)
VALUES ('Request default', DEFAULT);
```

The first and third rows receive the default value; the second row receives `NULL`. Do not pass `NULL` expecting MySQL to always substitute the current timestamp. Certain legacy `TIMESTAMP` behaviors depended on `explicit_defaults_for_timestamp` in older versions; do not rely on that legacy compatibility behavior in new schemas.

If a timestamp column is mandatory, declare it `NOT NULL` with an explicit default. If `NULL` carries business meaning such as “time not yet determined”, declare it nullable and handle that case in application code.

## 8. Fractional Seconds Precision

MySQL supports fractional seconds precision from 0 to 6 for `TIMESTAMP` and `DATETIME`:

- `DATETIME` or `TIMESTAMP` without precision: defaults to 0, storing whole seconds only.
- `(3)`: stores down to milliseconds.
- `(6)`: stores down to microseconds.

Column definitions and temporal functions should use the same precision:

```sql
CREATE TABLE api_requests (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_path VARCHAR(255) NOT NULL,
    created_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`CURRENT_TIMESTAMP(3)` generates values with millisecond precision; `CURRENT_TIMESTAMP(6)` uses microseconds. If a column has precision 0 while the application supplies fractional seconds, MySQL adjusts according to the column's precision. Check the rounding/truncation mode and driver behavior if high temporal precision is required.

Do not adopt `(6)` precision everywhere out of habit. It adds granularity and can affect index size or serialization formats; choose it only when the business needs to distinguish events occurring very close together.

## 9. CURRENT_TIMESTAMP and Connection Session Time Zone

`CURRENT_TIMESTAMP` returns the current instant in the MySQL session's time zone. Therefore, `time_zone` configuration affects the generated value.

Check time zones:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

Key difference between the two types:

- `TIMESTAMP` converts between the session time zone and UTC on write/read. MySQL stores the value in UTC and displays it in the session time zone.
- `DATETIME` stores the date and time components as supplied; MySQL does not automatically convert time zones for `DATETIME`.

For example, if the session uses `'+07:00'`, `CURRENT_TIMESTAMP` returns the time in the session's clock. When assigned to a `TIMESTAMP` column, MySQL converts it to UTC for storage and converts it back when read in that session. When assigned to a `DATETIME` column, the session clock time is stored directly as a timezone-naive datetime.

To ensure connections generate consistent timestamps, systems typically configure session time zones to UTC:

```sql
SET SESSION time_zone = '+00:00';
```

In applications using a connection pool, configure the timezone for every connection at initialization or via driver configuration. Do not run `SET time_zone` once on a single connection and assume all other connections change as well.

If the business needs an absolute instant, `TIMESTAMP` with a UTC session is typically a good fit within the type's value range. If storing local wall-clock time such as “09:00 at the store” without representing a single global instant, `DATETIME` can be appropriate; store the timezone separately if accurate conversion across DST or other zones is needed.

## 10. Which Instant Does CURRENT_TIMESTAMP Capture?

In MySQL, `CURRENT_TIMESTAMP`, `NOW()`, and `LOCALTIME` are synonymous expressions for the current time in normal contexts. The value of `NOW()` is fixed when execution of the current statement begins; multiple calls within the same statement return the exact same instant.

This means `updated_at` is neither the transaction commit time nor necessarily the end of a long-running transaction. It reflects when the row-modifying statement executed. If the business requires commit time, external event receipt time, or full history, design a dedicated audit/event model.

`SYSDATE()` has different semantics: it returns the time at which the function itself executes and can vary across calls within the same statement. Do not replace `CURRENT_TIMESTAMP` with `SYSDATE()` in defaults or on-update definitions without understanding this difference and its replication implications.

## 11. Multiple Temporal Columns in the Same Table

Modern MySQL allows multiple `TIMESTAMP` or `DATETIME` columns with automatic initialization/updating. Example:

```sql
CREATE TABLE documents (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    published_at DATETIME NULL DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`published_at` does not auto-populate with the current time because the business records it only when the document is published; `created_at` receives the creation timestamp; `updated_at` auto-updates whenever the row changes.

Older MySQL versions had historical restrictions on automatic initialization/updating across multiple `TIMESTAMP` columns. If you must support legacy versions, check documentation for that exact version and the `explicit_defaults_for_timestamp` variable; do not assume identical behavior across all servers.

## 12. INSERT ... ON DUPLICATE KEY UPDATE and REPLACE

When using upsert, the automatic update rule still applies if the existing row actually changes:

```sql
INSERT INTO customer_accounts (email, display_name)
VALUES ('linh@example.test', 'Linh Nguyen') AS new
ON DUPLICATE KEY UPDATE
    display_name = new.display_name;
```

If the email already exists and `display_name` changes, `updated_at` updates automatically. If the value matches the existing one, the row does not change and the timestamp does not necessarily update. The new-row alias syntax in this example requires MySQL 8.0.19 or later; `VALUES(column)` inside `ON DUPLICATE KEY UPDATE` was deprecated in MySQL 8.0.20.

`REPLACE` has delete-then-insert semantics for conflicting rows. As a result, temporal columns with defaults may receive fresh timestamps as in an insert, meaning `created_at` can change. Do not use `REPLACE` as a drop-in substitute for `UPDATE` when creation timestamps and related relationships must remain intact.

## 13. Bulk Updates and Migrations

A bulk update can modify `updated_at` across many rows:

```sql
UPDATE customer_accounts
SET is_active = FALSE
WHERE last_login_at < '2025-01-01';
```

If the condition matches many rows and `is_active` actually changes, each matching row's `updated_at` will update. This can impact reports, data sync pipelines, and jobs polling by `updated_at`.

Before running migrations or backfills on large tables, decide whether timestamp updates should trigger. If re-importing historical data, you can supply `updated_at` explicitly according to target data rules; otherwise, let the automatic mechanism record the current processing time. Do not silently alter timestamp semantics merely to make a migration pass.

## 14. Triggers and Applications Updating Timestamps Together

`updated_at` can be updated by the application, a trigger, or `ON UPDATE CURRENT_TIMESTAMP`. Avoid having multiple mechanisms write to the same column without explicit precedence rules.

If the application sends an explicit `updated_at`, it can override MySQL's auto-generated value. If a `BEFORE UPDATE` trigger modifies the column, check how it interacts with the `ON UPDATE` attribute. Mixing mechanisms easily leads to confusing behavior when different layers use different time zones or clocks.

Pick one authoritative source for modification timestamps. If the database is the source of truth, rely on column attributes and avoid application overrides. If business service time is required, pass an explicit value and design clock, timezone, retry, and synchronization handling clearly.

## 15. Inspecting Definitions and Behavior

Inspect the table DDL:

```sql
SHOW CREATE TABLE customer_accounts\G
```

Inspect column metadata:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    DATETIME_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_accounts'
ORDER BY ORDINAL_POSITION;
```

`COLUMN_DEFAULT` shows the declared default value; `EXTRA` can show `on update CURRENT_TIMESTAMP`; `DATETIME_PRECISION` shows fractional seconds precision.

You can test behavior by capturing timestamps before and after an update:

```sql
SELECT id, created_at, updated_at
FROM customer_accounts
WHERE id = 1;

UPDATE customer_accounts
SET display_name = CONCAT(display_name, ' ')
WHERE id = 1;

SELECT id, created_at, updated_at
FROM customer_accounts
WHERE id = 1;
```

In a lab environment, compare `created_at` and `updated_at` after insert, after an update that changes data, and after a no-op update. With precision 0, two rapid operations within the same second can be hard to distinguish; use `(3)` or `(6)` when finer observation is needed.

## 16. Common Mistakes and Misconceptions

| Misconception / Error | Reality | How to Handle |
| --- | --- | --- |
| `DEFAULT CURRENT_TIMESTAMP` auto-updates on update | This attribute only provides a default on insert or when `DEFAULT` is requested | Add `ON UPDATE CURRENT_TIMESTAMP` if auto-update is needed |
| `ON UPDATE` always changes on any UPDATE | Updates automatically only when the row actually changes and no other explicit value is assigned | Verify before/after values and the update statement |
| Passing `NULL` is equivalent to using default | Nullable columns store `NULL`; `NOT NULL` columns may error | Omit the column from INSERT or use the `DEFAULT` keyword |
| `TIMESTAMP` and `DATETIME` handle timezones the same way | `TIMESTAMP` converts by session timezone; `DATETIME` does not auto-convert | Choose type by semantics and configure session timezone |
| `updated_at` is the commit time | `CURRENT_TIMESTAMP` reflects statement execution start time | Use an audit/event table if commit history or exact commit time is required |
| `REPLACE` works like UPDATE | `REPLACE` deletes and re-inserts | Use `UPDATE` or upsert when creation history must be preserved |
| App and trigger both write timestamps without rules | Can overwrite values or introduce clock skew | Choose one authoritative source and test interactions |

## 17. Practice Exercises

1. Create a `tasks` table with `created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` and `updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`.
2. Insert a task without passing the two timestamp columns; inspect the generated values.
3. Update `title` to a different value; verify `updated_at` changes while `created_at` stays the same.
4. Run an update setting `title` to its exact current value; observe `updated_at`.
5. Update another column such as `is_done`; verify `updated_at` auto-updates.
6. Test inserting with the timestamp column omitted, using `DEFAULT`, and passing `NULL`; explain the outcomes based on nullability and SQL mode.
7. Create `DATETIME(3)` and `TIMESTAMP(6)` columns with matching `CURRENT_TIMESTAMP` precision; inspect fractional seconds.
8. Switch session `time_zone` between `'+00:00'` and `'+07:00'`; compare `NOW()`, `UTC_TIMESTAMP()`, `TIMESTAMP`, and `DATETIME`.
9. Query `INFORMATION_SCHEMA.COLUMNS` to inspect `COLUMN_DEFAULT`, `EXTRA`, and `DATETIME_PRECISION`.
10. Design a backfill migration and explain whether historical timestamps should be preserved or overwritten with the current processing time.

## 18. Key Takeaways

`DEFAULT CURRENT_TIMESTAMP` assigns the current timestamp when an insert omits the column or specifies `DEFAULT`. `ON UPDATE CURRENT_TIMESTAMP` updates the timestamp automatically when a row genuinely changes. Use both on `updated_at` for automatic initialization and updates; use `DEFAULT` alone on `created_at` to preserve creation time.

Fractional seconds precision can be chosen from 0 to 6 and should align between column types and `CURRENT_TIMESTAMP(fsp)`. `CURRENT_TIMESTAMP` depends on the session timezone; `TIMESTAMP` converts via UTC while `DATETIME` stores date/time values verbatim. Distinguish `NULL` from `DEFAULT`, understand upsert/`REPLACE` effects, and avoid conflicting timestamp writes across application code, triggers, and the database. Always inspect actual DDL and metadata before deploying temporal behavior to production.
