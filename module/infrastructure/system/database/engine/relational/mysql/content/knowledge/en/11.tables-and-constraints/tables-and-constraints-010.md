# DEFAULT Expressions, Invisible Columns, and Version Requirements

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, execution plan reading, query optimization, privileges, backups, and operations. When designing or extending tables, two useful yet version-dependent features are DEFAULT expressions and invisible columns. DEFAULT expressions let you compute default values on row insertion; invisible columns let you store a column hidden from statements using implicit column lists.

These two features help reduce initialization boilerplate in applications and support more backward-compatible schema changes. However, they have specific rules regarding version support, syntax, INSERT/SELECT behavior, and cross-environment compatibility. Always verify the actual MySQL version before using them in migrations.

## 1. DEFAULT in Table Design

DEFAULT specifies the value used when an INSERT statement omits a column or explicitly requests the DEFAULT keyword. It expresses meaningful initial values directly in the schema.

Example:

~~~sql
CREATE TABLE tasks (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id)
) ENGINE=InnoDB;
~~~

When inserting a row while omitting `status`, `retry_count`, and `created_at`, MySQL applies the respective default values. This gives all clients consistent data initialization rules, including admin scripts or background jobs that bypass the main application layer.

DEFAULT does not replace business validation. For example, defaulting `status` to `PENDING` does not mean every subsequent state transition is valid; the application must still enforce workflow rules.

## 2. Literal Defaults and Expression Defaults

### 2.1. Literal Default

A literal default is a fixed constant declared directly:

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(200) NOT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    description VARCHAR(500) NULL DEFAULT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
~~~

The examples `1`, `'VND'`, and `NULL` are fixed literals. Every row omitting the corresponding column receives the exact declared value.

### 2.2. Expression Default

An expression default is an expression evaluated whenever a default value is needed. MySQL has supported DEFAULT expressions since **MySQL 8.0.13**. The expression must be enclosed in parentheses:

~~~sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(36) NOT NULL DEFAULT (UUID()),
    title VARCHAR(200) NOT NULL,
    review_due DATE NOT NULL DEFAULT (CURRENT_DATE + INTERVAL 30 DAY),
    PRIMARY KEY (document_id),
    UNIQUE KEY uq_documents_public_id (public_id)
) ENGINE=InnoDB;
~~~

In this example, `UUID()` generates an identifier when a default is needed; the date expression computes a due date from the current date. Whenever a row is inserted omitting the respective column, MySQL evaluates the expression to produce the value.

A DEFAULT expression must be enclosed in parentheses, even when it consists of a single function call or calculation. This syntax distinguishes expression defaults from literal defaults and avoids confusion when reading DDL.

### 2.3. Allowed Expressions and Limitations

An expression default can use literals, operators, parentheses, and built-in functions permitted by MySQL. The expression cannot reference values of other columns and cannot contain components such as:

- Subqueries.
- Stored functions or loadable functions.
- System variables, user variables, or routine parameters.
- References to columns of the row being inserted.

The following example is invalid because `end_date`'s default references `start_date`:

~~~sql
-- Invalid
CREATE TABLE subscriptions (
    start_date DATE NOT NULL,
    end_date DATE DEFAULT (start_date + INTERVAL 1 YEAR)
);
~~~

If a value must be computed from other columns in the same row, consider a generated column or compute it in the INSERT/UPDATE statement. DEFAULT only generates a fallback value when a column is not supplied; it is not a mechanism for recomputing columns whenever related data changes.

You cannot use a subquery to fetch a default value from another table. If you need to allocate codes or values depending on external data, perform it inside an application-layer transaction or properly designed stored logic.

### 2.4. Default Expressions for BLOB, TEXT, GEOMETRY, and JSON

Since MySQL 8.0.13, `BLOB`, `TEXT`, `GEOMETRY`, and `JSON` types can use default expressions; for these types, the default value must be written as a parenthesized expression, even when the value is a literal:

~~~sql
CREATE TABLE article_content (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    body TEXT NOT NULL DEFAULT (''),
    metadata JSON NOT NULL DEFAULT (JSON_OBJECT()),
    PRIMARY KEY (article_id)
) ENGINE=InnoDB;
~~~

In MySQL prior to 8.0.13, do not rely on this default expression syntax. If you need to support MySQL 5.7 or older environments, initialize the value in INSERT statements or the application layer using a uniform rule.

### 2.5. CURRENT_TIMESTAMP and Timestamp Columns

MySQL supported declaring `CURRENT_TIMESTAMP` on `TIMESTAMP` and `DATETIME` columns even before general expression defaults existed:

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

`CURRENT_TIMESTAMP` in DEFAULT sets the creation timestamp on row insert. `ON UPDATE CURRENT_TIMESTAMP` updates the timestamp when the row changes per column rules. These two capabilities are distinct: DEFAULT does not automatically update on every UPDATE; `ON UPDATE` defines the automatic update behavior.

You can specify fractional seconds precision, such as `CURRENT_TIMESTAMP(3)`. Choose precision consistently across the schema, driver, and business requirements.

## 3. When Is DEFAULT Applied?

### 3.1. Omitting the Column in INSERT

When a column does not appear in the INSERT column list, MySQL uses the column's default if one exists:

~~~sql
INSERT INTO tasks (title)
VALUES ('Import customers');
~~~

The new row receives status `PENDING`, `retry_count` `0`, and `created_at` from `CURRENT_TIMESTAMP`. This is the most common and readable usage.

### 3.2. Using the Explicit DEFAULT Keyword

You can ask MySQL to use the default for a specific column:

~~~sql
INSERT INTO tasks (title, status, retry_count)
VALUES ('Rebuild search index', DEFAULT, DEFAULT);
~~~

`DEFAULT` in a value position instructs MySQL to apply that column's default. This is helpful when an INSERT lists all columns explicitly while wanting a few columns to receive schema-defined values.

### 3.3. Explicitly Passing NULL Is Not the Same as Omitting a Column

If a column allows NULL, passing NULL stores NULL rather than automatically triggering the default:

~~~sql
CREATE TABLE profiles (
    profile_id BIGINT NOT NULL,
    nickname VARCHAR(100) NULL DEFAULT 'Guest',
    PRIMARY KEY (profile_id)
);

INSERT INTO profiles (profile_id)
VALUES (1);

INSERT INTO profiles (profile_id, nickname)
VALUES (2, NULL);
~~~

The first row receives `nickname` `Guest` because the column was omitted. The second row receives `NULL` because the client explicitly passed `NULL`. If you want the second row to use the default, pass `DEFAULT` instead of `NULL`.

On a NOT NULL column, passing NULL normally fails in strict SQL mode. Never rely on MySQL coercing NULL to an implicit default in non-strict mode; that behavior produces warnings and unexpected data.

### 3.4. DEFAULT in UPDATE

You can reset a column back to its default:

~~~sql
UPDATE tasks
SET retry_count = DEFAULT
WHERE task_id = 10;
~~~

`DEFAULT` in UPDATE applies the column's default value at statement execution time. If the default is an expression, MySQL evaluates the expression to obtain the applied value. This resets the targeted column; it does not reset all columns in the row.

### 3.5. Columns Without a Declared DEFAULT

If a column is omitted and has no explicit default, MySQL applies implicit default rules based on data type and nullability. On a NOT NULL column under strict mode, missing values cause INSERT to fail. Schema design should declare explicit DEFAULTs for columns with genuine initial values and NOT NULL for mandatory data.

## 4. DEFAULT Expressions vs. Generated Columns

The two features serve different purposes:

| Characteristic | DEFAULT Expression | Generated Column |
|---|---|---|
| When evaluated | When INSERT omits the column or specifies DEFAULT; when UPDATE sets DEFAULT | When read or stored per column definition |
| Depends on other columns | No | Can reference same-row columns per generated column rules |
| Allows arbitrary input values | Explicit values can be supplied in INSERT/UPDATE | Cannot assign values directly to generated columns |
| Purpose | Initial or fallback value | Value derived from other data in the same row |

Generated column example:

~~~sql
CREATE TABLE order_lines (
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

`line_total` is computed from `quantity` and `unit_price`. If you want a default value for an independent column like `retry_count`, use DEFAULT. If you need a calculation from other columns, consider a generated column or expressions in DML.

## 5. What Is an Invisible Column?

An invisible column is a column that still exists in the table and stores data normally, but does not appear in statements relying on implicit column lists. This feature has been supported since **MySQL 8.0.23**.

Example:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    internal_note VARCHAR(500) NULL INVISIBLE,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
~~~

`internal_note` is an invisible column. It can still be read and written when referenced explicitly by name, and it can participate in indexes per MySQL rules. The `INVISIBLE` keyword does not drop the column or erase its data.

### 5.1. SELECT * Skips Invisible Columns

~~~sql
SELECT *
FROM customers;
~~~

The result omits `internal_note`. To read this column, name it explicitly:

~~~sql
SELECT customer_id, full_name, internal_note
FROM customers;
~~~

This is useful when adding an internal or migration-support column while keeping the output shape of existing `SELECT *` queries intact.

An invisible column is not a security mechanism. Anyone with `SELECT` privilege on the table can still access the column if they know its name; data access permissions are still governed by MySQL privileges. To restrict data visibility, use column-level privileges, views, or appropriate security controls.

### 5.2. INSERT Without a Column List

Invisible columns are excluded from the implicit column list of INSERT statements that omit column names. For instance, on the `customers` table above:

~~~sql
INSERT INTO customers
VALUES (1001, 'Nguyen An');
~~~

The two values correspond to the two visible columns `customer_id` and `full_name`; `internal_note` is skipped and receives `NULL` because it is nullable. If an invisible column is NOT NULL, provide an appropriate DEFAULT so implicit INSERT statements continue to work.

You can write to an invisible column explicitly when needed:

~~~sql
INSERT INTO customers
    (customer_id, full_name, internal_note)
VALUES
    (1002, 'Tran Binh', 'Imported from legacy system');
~~~

In new applications, still prefer explicit column lists in INSERT statements. This is easier to read, does not depend on physical column order, and reduces breakage when schemas evolve.

### 5.3. UPDATE and Other Statements

Invisible columns can still be referenced explicitly in `SELECT`, `WHERE`, `ORDER BY`, `JOIN`, `UPDATE`, and standard SQL expressions:

~~~sql
UPDATE customers
SET internal_note = 'Verified'
WHERE customer_id = 1002;

SELECT customer_id, full_name
FROM customers
WHERE internal_note = 'Verified';
~~~

Invisible columns can still be indexed and participate in constraints according to the rules of that column and index type. Invisibility only affects whether the column is included in implicit column lists; it does not turn the column into a separate object or prevent explicit querying.

## 6. Creating and Modifying Invisible Columns

### 6.1. Creating New Tables

Declare `INVISIBLE` in `CREATE TABLE`:

~~~sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NULL,
    source_system VARCHAR(50) NOT NULL DEFAULT 'web' INVISIBLE,
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

`source_system` does not appear in `SELECT *` or column-list-less `INSERT` statements. To record the source, the application specifies `source_system` explicitly; otherwise, the default `web` is used.

### 6.2. Adding an Invisible Column to an Existing Table

~~~sql
ALTER TABLE event_log
  ADD COLUMN migration_tag VARCHAR(40) NULL INVISIBLE;
~~~

The new column can be added without increasing the visible column count in `SELECT *` results. This is useful when rolling out schema changes first and updating applications afterward to read/write the new column.

### 6.3. Toggling Visible and Invisible

Since MySQL 8.0.23, you can alter visibility:

~~~sql
ALTER TABLE event_log
  ALTER COLUMN migration_tag SET VISIBLE;

ALTER TABLE event_log
  ALTER COLUMN migration_tag SET INVISIBLE;
~~~

When switched to `VISIBLE`, the column appears in `SELECT *` and implicit column lists. The result shape for applications using `SELECT *` may change. When switched to `INVISIBLE`, the column is excluded from implicit lists while its data is preserved.

You can use `MODIFY COLUMN` with `INVISIBLE`/`VISIBLE` when changing other parts of the column definition at the same time, but you must re-declare the full data type, `NULL`/`NOT NULL`, `DEFAULT`, comment, and other attributes.

### 6.4. Limitations to Know

- A table must have at least one visible column.
- An invisible column still requires a unique name within the table.
- An invisible column is not a secret column; metadata and explicit queries can still reveal it.
- Some ORM, schema diff, or ETL tools may not handle visibility as expected if older versions do not recognize this attribute.
- Verify the behavior of import/export commands and admin tools you use, not just `SELECT *`.

## 7. Inspecting DEFAULT and Visibility Metadata

### 7.1. SHOW CREATE TABLE

This is the comprehensive way to view column definitions:

~~~sql
SHOW CREATE TABLE customers;
~~~

The output shows DEFAULT expressions, `INVISIBLE` attributes, indexes, constraints, and other properties. Save the output before and after migrations for comparison.

### 7.2. INFORMATION_SCHEMA.COLUMNS

You can query column metadata:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

`EXTRA` may contain attributes such as `auto_increment`, `DEFAULT_GENERATED`, `INVISIBLE`, or generated column info depending on column type and version. Check `EXTRA` to detect invisible columns:

~~~sql
SELECT COLUMN_NAME, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND EXTRA LIKE '%INVISIBLE%';
~~~

`COLUMN_DEFAULT` shows the default value in metadata; for expression defaults, representation varies by version. Use `SHOW CREATE TABLE` to verify the exact syntax rather than relying on a single metadata field.

### 7.3. Checking Server Version

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution;
~~~

Do not rely only on the client version or Connector/J version. DDL features must be supported by the server executing them. If your environment has multiple nodes or replicas, verify version and compatibility across all involved nodes.

## 8. Version Conditions and Compatibility

Key milestones to remember:

| Feature | MySQL Version | Notes |
|---|---|---|
| Literal DEFAULT | Present since legacy MySQL versions | Fixed constant default value |
| CURRENT_TIMESTAMP for TIMESTAMP/DATETIME | Present since legacy versions | Special timestamp default mechanism |
| General expression default | MySQL 8.0.13+ | Expression must be in parentheses; component restrictions apply |
| Default expression for BLOB/TEXT/GEOMETRY/JSON | MySQL 8.0.13+ | Must write default as an expression, even for literals |
| Invisible column | MySQL 8.0.23+ | Hidden from implicit column lists like `SELECT *` |

MySQL 5.7 does not support general expression defaults or invisible columns. If an application must run simultaneously on MySQL 5.7 and 8.0, migrations using these newer features will fail on 5.7 nodes.

Before deploying, check:

1. Exact server version and supported features.
2. MySQL versions on replicas, restore environments, and CI environments.
3. Whether ORMs, migration tools, schema introspection, and code generators understand invisible columns.
4. Whether drivers and applications rely on `SELECT *` or column-list-less `INSERT`s.
5. Whether logical dump/restore preserves DEFAULT expressions and `INVISIBLE` attributes when importing into target servers.

Never assume a migration that runs on development 8.0.36 will automatically run on production 8.0.22 or an older replica.

## 9. Combining DEFAULT Expressions with Invisible Columns

Both features can work together to add an internal attribute without changing the output of `SELECT *` and implicit-list `INSERT`s:

~~~sql
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(40)
    NOT NULL
    DEFAULT ('legacy')
    INVISIBLE;
~~~

On a server supporting expression defaults and invisible columns, the new column:

- Does not appear in `SELECT *`.
- Is excluded from implicit column lists of column-list-less `INSERT`s.
- Receives `'legacy'` when `INSERT` omits the column.
- Can be accessed by naming `source_system` in explicit SQL statements.

Example:

~~~sql
INSERT INTO customers (customer_id, full_name)
VALUES (2001, 'Le Chi');

SELECT customer_id, full_name, source_system
FROM customers
WHERE customer_id = 2001;
~~~

The new row receives `source_system = 'legacy'`. Applications can be rolled out gradually to write the actual source, and the column can later be switched to visible if needed. Do not use invisible columns to postpone updating long-term data contracts indefinitely; document when and under what conditions the column will become visible.

## 10. Applications, ORMs, and Data Contracts

### 10.1. Avoid SELECT *

Applications should list the columns they need to read:

~~~sql
SELECT customer_id, full_name, created_at
FROM customers;
~~~

`SELECT *` ties the data contract to every visible column at runtime. Adding a visible column alters the order and count of returned fields; invisible columns avoid breaking implicit lists, yet they do not turn `SELECT *` into a durable design.

### 10.2. Avoid INSERT Without a Column List

Do not rely on:

~~~sql
INSERT INTO customers
VALUES (2002, 'Pham Dung');
~~~

Write instead:

~~~sql
INSERT INTO customers (customer_id, full_name)
VALUES (2002, 'Pham Dung');
~~~

Explicit column lists make migrations that add, reorder, or change column visibility much safer to manage. They also make clear which columns are supplied and which receive DEFAULTs.

### 10.3. ORMs and Entity Mapping

ORMs often read schema metadata to generate entities or mappings. If an ORM does not understand invisible columns, it might:

- Generate `SELECT *` and fail to map the invisible column.
- Generate positional or column-listed INSERTs unexpectedly.
- Report schema drift because metadata shows an extra column.
- Drop the `INVISIBLE` attribute when generating reverse migrations.

Check your ORM version and how it introspects `INFORMATION_SCHEMA`. For critical entities, declare column lists explicitly and run integration tests against the exact target MySQL version.

DEFAULT expressions may also not be fully modeled by an ORM. Some ORMs read `COLUMN_DEFAULT` as plain text or do not know how to emit expression DDL. Inspect generated migrations rather than assuming ORM annotations translate identically to MySQL DDL.

### 10.4. Invisible Does Not Replace Access Control

Invisible columns do not hide data from authorized users. If a column holds sensitive data, grant column-level `SELECT` privileges, use views exposing only permitted columns, or apply proper security controls. Do not use `INVISIBLE` as an information security measure.

## 11. Safe Migration Rollout

### 11.1. Before Making Changes

- Confirm the MySQL version supports expression defaults or invisible columns.
- Capture `SHOW CREATE TABLE` and relevant metadata.
- Audit application statements using `SELECT *`, column-list-less `INSERT`s, and ETL tools.
- Determine whether the default expression uses nondeterministic functions or has replication compatibility constraints.
- Check whether the new column needs `NOT NULL`, `DEFAULT`, indexes, or constraints.
- Test the DDL on a data copy running a version matching production.

### 11.2. Adding an Invisible Column in Phases

A phased application rollout workflow might look like:

1. Add the invisible column with the appropriate type, `NULL`/`NOT NULL`, and `DEFAULT`.
2. Verify `SELECT *` and existing `INSERT`s still work as expected.
3. Deploy updated application code to read/write the column by explicit name.
4. Reconcile data in the new column and monitor application errors.
5. Once all clients are ready, decide whether to keep it invisible or switch it to visible.

Do not assume adding an invisible column is always instant or lock-free. DDL algorithms depend on version, storage engine, change type, and table structure. Review `ALTER TABLE` plans, version docs, and test on staging.

### 11.3. Changing DEFAULT

To update a column's default, you can run:

~~~sql
ALTER TABLE tasks
  ALTER COLUMN retry_count SET DEFAULT (1 + 1);
~~~

This command updates the default value used for subsequent `INSERT`/`UPDATE` statements requesting `DEFAULT`; it does not automatically update `retry_count` on existing rows. To backfill existing rows, run a separate `UPDATE` with an explicit condition and verify the affected row count.

To drop a default:

~~~sql
ALTER TABLE tasks
  ALTER COLUMN retry_count DROP DEFAULT;
~~~

Before dropping a default, check whether any clients omit the column on `INSERT`. If the column is `NOT NULL` and lacks a default, inserts omitting it will start failing under strict mode.

### 11.4. Rollback

MySQL DDL typically triggers an implicit commit; do not expect a transaction `ROLLBACK` to undo `CREATE`/`ALTER TABLE`. Prepare intentional reverse migrations:

- If a new column was added, you can `DROP COLUMN` after confirming applications no longer depend on it.
- If visibility was toggled, toggle back between `VISIBLE`/`INVISIBLE` per the data contract.
- If a default changed, restore the previous default from the saved DDL.
- If data has already been written into the new column, do not drop the column before deciding what data must be preserved or migrated.

Backups and restore testing remain essential for changes that can affect data. Schema rollback does not automatically undo data written after a migration.

## 12. Hands-on Lab: DEFAULT Expressions and Invisible Columns

Perform in a MySQL lab with **MySQL 8.0.23 or later** to use both features. Do not run on a production database.

**Step 1 — Verify version.**

~~~sql
SELECT VERSION() AS mysql_version;
~~~

If the server is below 8.0.23, skip the invisible column steps; you can practice DEFAULT expressions alone on 8.0.13+.

**Step 2 — Create the lab table.**

~~~sql
CREATE TABLE lab_feature_flags (
    flag_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    flag_name VARCHAR(100) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    audit_token CHAR(36) NOT NULL DEFAULT (UUID()) INVISIBLE,
    PRIMARY KEY (flag_id),
    UNIQUE KEY uq_lab_audit_token (audit_token)
) ENGINE=InnoDB;
~~~

**Step 3 — Test SELECT \*.**

~~~sql
INSERT INTO lab_feature_flags (flag_name)
VALUES ('new-checkout');

SELECT * FROM lab_feature_flags;

SELECT flag_id, flag_name, enabled, created_at, audit_token
FROM lab_feature_flags;
~~~

The first query omits `audit_token`. The second query reads the invisible column by explicit name.

**Step 4 — Test default expressions.**

~~~sql
INSERT INTO lab_feature_flags (flag_name, enabled)
VALUES ('new-search', DEFAULT);

SELECT flag_name, enabled, audit_token
FROM lab_feature_flags;
~~~

Observe that `enabled` receives `0` and `audit_token` is auto-generated when omitted.

**Step 5 — Test INSERT without a column list.**

~~~sql
INSERT INTO lab_feature_flags
VALUES (DEFAULT, 'legacy-import', DEFAULT, DEFAULT);
~~~

Values correspond only to the visible columns in order. The invisible `audit_token` is omitted and receives its default expression. Afterward, explicitly query `audit_token` to verify.

**Step 6 — Toggle visibility.**

~~~sql
ALTER TABLE lab_feature_flags
  ALTER COLUMN audit_token SET VISIBLE;

SELECT * FROM lab_feature_flags;
~~~

Observe `audit_token` appearing in `SELECT *`. Switch it back to invisible:

~~~sql
ALTER TABLE lab_feature_flags
  ALTER COLUMN audit_token SET INVISIBLE;
~~~

**Step 7 — Inspect metadata.**

~~~sql
SHOW CREATE TABLE lab_feature_flags;

SELECT COLUMN_NAME, COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lab_feature_flags'
ORDER BY ORDINAL_POSITION;
~~~

Locate the default expressions and the `INVISIBLE` attribute in the output.

**Step 8 — Clean up the lab.**

~~~sql
DROP TABLE lab_feature_flags;
~~~

Drop the lab table only after inspecting all results.

**Expected outcome:** successfully create expression defaults, understand when MySQL applies defaults, distinguish NULL from omitting a column, verify that invisible columns are excluded from `SELECT *` and implicit `INSERT`s, and inspect metadata alongside version requirements.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Server reports syntax error at `DEFAULT (expression)` | MySQL is below 8.0.13 or expression is invalid | Check `VERSION()`, parenthesized syntax, and expression default limits |
| DEFAULT expression references another column and is rejected | Default expressions cannot read same-row column values | Use a generated column or compute the value in DML |
| DEFAULT does not fire when client passes NULL | Explicit NULL is a supplied value, not an omitted column | Omit the column from INSERT or pass `DEFAULT` |
| BLOB/TEXT/JSON rejects literal default | These types require expression syntax for defaults on supported versions | Use `DEFAULT ('literal')` on MySQL 8.0.13+ or initialize in application code |
| Invisible column missing from `SELECT *` | Expected behavior | Specify the column name explicitly when reading it |
| Column-list-less INSERT does not populate invisible column | Invisible columns are omitted from implicit column lists | Use appropriate DEFAULT/NULL or specify column list explicitly |
| `ALTER COLUMN SET INVISIBLE` fails | Server below 8.0.23 or table would have zero visible columns | Verify version and ensure at least one visible column remains |
| ORM fails to read or write invisible column | ORM/schema introspection does not support visibility | Check ORM version, mappings, and generated SQL |
| Application receives extra field after switching VISIBLE | `SELECT *` begins returning the newly visible column | Review data contracts and deploy compatible clients before changing visibility |

## 14. Principles to Remember

- A literal DEFAULT is a fixed constant; an expression default is evaluated whenever the column needs a default value.
- Expression defaults are supported from MySQL 8.0.13 and must be enclosed in parentheses.
- Expression defaults cannot reference other columns, subqueries, variables, or stored functions.
- `BLOB`, `TEXT`, `GEOMETRY`, and `JSON` require parenthesized default expressions on supported versions.
- DEFAULT only applies when a column is omitted or `DEFAULT` is requested; explicit NULL never triggers the default automatically.
- Generated columns fit values derived from other columns; DEFAULT fits initial values.
- Invisible columns are supported from MySQL 8.0.23, still store data, and remain accessible by explicit name.
- `SELECT *` and implicit column lists skip invisible columns; explicit INSERTs can still write them.
- Invisibility is not security; use privileges or views to control data access.
- Audit servers, replicas, ORMs, migration tools, and applications before adopting version-dependent features.
- DDL issues implicit commits; prepare reverse migrations and backups rather than relying on `ROLLBACK`.

DEFAULT expressions and invisible columns are useful tools for evolving schemas, but they are only safe when every client agrees on the same data contract. Verify the MySQL version, declare meaningful defaults, use explicit column lists, and test migrations in a production-equivalent environment before deploying.
