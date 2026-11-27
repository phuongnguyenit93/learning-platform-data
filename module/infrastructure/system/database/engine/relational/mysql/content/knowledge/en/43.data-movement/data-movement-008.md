# Unique Keys, Foreign Keys, and Post-Load Integrity Checks

When loading data into MySQL, a load statement finishing without errors does not prove the data is valid. Unique keys protect identifiers from duplication; foreign keys protect parent-child table relationships; post-load verification queries catch duplicate records, orphan rows, missing values, and row-count discrepancies. A reliable data movement workflow must validate data before loading, enforce appropriate constraints, and reconcile afterward.

This lesson belongs to the **Data Movement and Migration** chapter of the `DATABASE_MYSQL` module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backups, and operational troubleshooting—integrity constraints safeguard data quality across imports, migrations, and cross-system synchronization.

## 1. Why Verify Integrity After Loading?

Suppose an e-commerce system has two tables:

- `customers`: stores customers, each having an internal ID and an email.
- `orders`: stores orders, each belonging to a customer.

Data imported from CSV or legacy systems can suffer from issues such as:

- Two customers sharing the same email because the source file contained duplicate records.
- An order referencing a nonexistent `customer_id`.
- Order numbers colliding across two import runs.
- Key values missing or misconverted during load.
- Records skipped due to conversion errors, `INSERT IGNORE`, or `LOAD DATA ... IGNORE`.
- Re-running an import job creating duplicate rows or accidentally overwriting existing data.

These defects can corrupt reports, drop rows from joins, violate business rules, or cause future updates/deletes to fail. Database constraints are the final line of defense; source-file checks and application checks do not replace them.

## 2. Primary Keys, Unique Keys, and Foreign Keys

These three key types serve distinct purposes:

| Key Type | Role | Characteristics |
|---|---|---|
| PRIMARY KEY | Uniquely identifies each row | At most one primary key per table; primary key columns cannot be `NULL` |
| UNIQUE KEY | Prevents two rows from sharing the same key value | A table can have multiple unique keys; MySQL allows multiple `NULL` values in a unique index |
| FOREIGN KEY | Preserves child-to-parent table relationships | Non-`NULL` values in the referencing column must match a referenced key |

For example, `customers.id` is the internal primary key; `customers.email` is a business unique key; `orders.customer_id` is a foreign key pointing to customers.

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_customers_email UNIQUE (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(40) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  total_amount DECIMAL(12, 2) NOT NULL,
  import_batch_id VARCHAR(64) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_orders_order_no UNIQUE (order_no),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers (id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

Both `customers.id` and `orders.customer_id` are `BIGINT UNSIGNED`. The data types of the referencing column and referenced column must be compatible; for integers, width and signed/unsigned attributes must match. For string columns, charset and collation must match. Both parent and child tables must use a storage engine that supports foreign keys, typically InnoDB.

The referenced column should be a PRIMARY KEY or UNIQUE KEY. InnoDB requires suitable indexes on both the referenced column and the foreign key column; if the child side lacks an index, MySQL may create one automatically. Declaring indexes explicitly makes index names and purposes easier to manage.

## 3. Choosing Unique Keys According to Business Rules

A unique key must reflect what genuinely cannot be duplicated. For example:

- Login email unique across the entire system.
- Invoice number unique within a company.
- Product SKU unique within a store.
- The pair `tenant_id, external_code` unique within each tenant.

If a code is unique only per tenant, do not create a standalone unique index on `external_code`. Use a composite key instead:

~~~sql
CREATE TABLE external_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tenant_id BIGINT UNSIGNED NOT NULL,
  external_code VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_external_records_tenant_code
    UNIQUE (tenant_id, external_code)
) ENGINE=InnoDB;
~~~

The composite key ensures the same `external_code` can appear across different tenants without repeating within the same tenant. Column order in the index also affects query index usability; order columns according to real query patterns and constraints.

### NULL in UNIQUE

MySQL permits multiple rows with `NULL` in a unique index because `NULL` is not considered equal to another `NULL` in uniqueness comparisons. In a multi-column unique index, rows containing `NULL` in one component can also coexist even when the remaining components match.

If business logic requires every record to have a code, email, or external key, declare that column `NOT NULL`. Do not rely on `UNIQUE` to automatically block missing values.

~~~sql
-- If email is mandatory, declare NOT NULL
ALTER TABLE customers
  MODIFY email VARCHAR(254) NOT NULL;
~~~

When using `MODIFY`, re-specify all column attributes to preserve, such as charset, collation, `DEFAULT`, and `COMMENT`. The example above assumes the column has no extra attributes to retain; inspect `SHOW CREATE TABLE customers` before running on a real schema.

Before changing from nullable to `NOT NULL`, find and resolve any rows currently holding `NULL`:

~~~sql
SELECT id
FROM customers
WHERE email IS NULL;
~~~

### How Collation Affects Uniqueness

A unique index on strings follows the column's collation. Under case-insensitive or accent-insensitive collations, values such as `Alice@example.com` and `alice@example.com` may be treated as equal. Some collations also have specific rules for trailing whitespace.

Before creating a unique index, inspect column charset/collation:

~~~sql
SHOW FULL COLUMNS FROM customers;
~~~

If business rules require case sensitivity or accent sensitivity, choose an appropriate collation after checking MySQL version support. Never change a collation just to make an import succeed; changing it alters comparison, sorting, and uniqueness semantics for existing data.

## 4. Choosing Foreign Key Actions

Foreign keys define how MySQL behaves when a parent row is updated or deleted:

| Action | Outcome | Use Case |
|---|---|---|
| RESTRICT | Rejects deleting/updating the parent row if child rows still reference it | Safe default when history must be preserved |
| NO ACTION | In InnoDB, behaves identically to RESTRICT | When explicitly stating the action is disallowed |
| CASCADE | Propagates parent updates/deletes down to child rows | Tight lifecycle-dependent relationships |
| SET NULL | Sets the foreign key column on child rows to `NULL` | Optional relationship; child column must allow `NULL` |

For instance, orders need historical retention and should generally not be deleted when a customer is removed. Using `RESTRICT` causes customer deletion to fail if referencing orders still exist. If business rules allow deleting line items when deleting an order, `ON DELETE CASCADE` may be considered between `order_items` and `orders`.

~~~sql
CREATE TABLE products (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  product_id BIGINT UNSIGNED NOT NULL,
  quantity INT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  KEY idx_order_items_order_id (order_id),
  KEY idx_order_items_product_id (product_id),
  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES orders (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id)
    REFERENCES products (id)
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

Use `CASCADE` deliberately because a single delete on a parent table can wipe out many child rows. For financial, order, or audit-history data, it is usually better to retain records and use a cancelled/archived status rather than cascading deletes.

InnoDB checks foreign keys immediately during write operations; MySQL does not support `DEFERRABLE` foreign keys to postpone checks until transaction commit. When importing multi-table relational data, load order and constraint state are therefore critical.

## 5. Designing a Load Flow via Staging Tables

For large datasets or data from partially trusted sources, load into staging tables first. Staging tables keep data close to source form so normalization, validation, and promotion to core tables happen under control.

Model:

~~~text
CSV / legacy system
       |
       v
Staging tables
       |
       +--> Check types and required values
       |
       +--> Find duplicate keys
       |
       +--> Find orphan foreign keys
       |
       v
Core tables with PRIMARY / UNIQUE / FOREIGN KEY
       |
       v
Post-load reconciliation of counts, totals, and relationships
~~~

Example creating staging tables for customers and orders:

~~~sql
CREATE TABLE stg_customers (
  source_id VARCHAR(40),
  email VARCHAR(254),
  display_name VARCHAR(120)
) ENGINE=InnoDB;

CREATE TABLE stg_orders (
  source_order_no VARCHAR(40),
  source_customer_id VARCHAR(40),
  total_amount_text VARCHAR(40),
  import_batch_id VARCHAR(64) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE stg_customer_id_map (
  source_id VARCHAR(40) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (source_id),
  KEY idx_stg_customer_id_map_customer (customer_id)
) ENGINE=InnoDB;

CREATE TABLE stg_external_records (
  tenant_id BIGINT UNSIGNED,
  external_code VARCHAR(80)
) ENGINE=InnoDB;
~~~

Staging columns can use string types to retain raw input values, followed by controlled conversion. However, staging should not turn into unmanaged long-term storage. Tagging batch ID, load timestamp, and data source provides traceability per migration run.

## 6. Pre-Promotion Checks Before Moving Data to Core Tables

### Finding Missing Required Values

~~~sql
SELECT *
FROM stg_customers
WHERE email IS NULL
   OR TRIM(email) = ''
   OR display_name IS NULL
   OR TRIM(display_name) = '';
~~~

For order numbers:

~~~sql
SELECT *
FROM stg_orders
WHERE source_order_no IS NULL
   OR TRIM(source_order_no) = '';
~~~

Define clear handling for missing data: reject the batch, route bad rows to a quarantine table for correction, or apply defaults if business rules permit. Never auto-fill empty strings into a mandatory identifier.

### Finding Duplicate Single Keys

~~~sql
SELECT
  email,
  COUNT(*) AS duplicate_count
FROM stg_customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

The query groups according to the column's collation. For results to match the target unique index, staging should use the exact same charset and collation as the target column; otherwise, `GROUP BY` in staging may treat two strings as distinct while the target table's unique index considers them equal.

Check order numbers:

~~~sql
SELECT
  source_order_no,
  COUNT(*) AS duplicate_count
FROM stg_orders
WHERE source_order_no IS NOT NULL
GROUP BY source_order_no
HAVING COUNT(*) > 1;
~~~

### Finding Duplicate Composite Keys

~~~sql
SELECT
  tenant_id,
  external_code,
  COUNT(*) AS duplicate_count
FROM stg_external_records
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~

If a component of a unique key can be `NULL`, check `NULL` rows separately according to business rules; a unique index may permit multiple rows containing `NULL`.

### Checking Orphan Foreign Keys

An order is valid only if the referenced customer exists. When staging holds source customer IDs, map them to target IDs and verify the relationship:

~~~sql
SELECT
  o.source_order_no,
  o.source_customer_id
FROM stg_orders AS o
LEFT JOIN stg_customer_id_map AS m
  ON m.source_id = o.source_customer_id
LEFT JOIN customers AS c
  ON c.id = m.customer_id
WHERE o.source_customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

The result lists orders lacking a matching customer. Fix the mapping, load the missing customers, or quarantine those orders. Never fabricate a dummy customer just to make a foreign key pass.

### Checking Values and Data Types

Before casting strings to numbers or dates, locate unparseable or out-of-range values. Example:

~~~sql
SELECT *
FROM stg_orders
WHERE total_amount_text IS NULL
   OR TRIM(total_amount_text) = ''
   OR total_amount_text NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$';
~~~

The regex illustrates a non-negative decimal format with up to two fractional digits. Adapt it to source file format, decimal separator, and currency rules. After casting, verify target column bounds and business constraints.

## 7. Loading in Parent-First, Child-Second Order

When foreign keys are enabled, parent rows must be loaded before child rows. In this example:

1. Load `customers`.
2. Build or verify the mapping from source customer IDs to `customers.id`.
3. Load `orders` with valid `customer_id` values.
4. Load `order_items` once orders exist.

Example promoting validated customers into the core table:

~~~sql
INSERT INTO customers (email, display_name)
SELECT email, display_name
FROM stg_customers;
~~~

Then map IDs via a stable business key. If email is unique and normalized, staging can join against the core table:

~~~sql
INSERT INTO orders (order_no, customer_id, total_amount, import_batch_id)
SELECT
  s.source_order_no,
  c.id,
  CAST(s.total_amount_text AS DECIMAL(12, 2)),
  s.import_batch_id
FROM stg_orders AS s
JOIN stg_customer_id_map AS m
  ON m.source_id = s.source_customer_id
JOIN customers AS c
  ON c.id = m.customer_id;
~~~

This example assumes the mapping has been verified unique and the data passed validation. If the mapping could return multiple rows for one source ID, the join will multiply records; check cardinality before inserting.

For large migrations, split into batches by key or data range. Record completed batches so you can resume after failure without double-loading. Use per-batch transactions when batch size and lock duration allow. Avoid one giant transaction that inflates undo logs, holds locks for a long time, and lengthens crash recovery.

## 8. Should You Disable FOREIGN_KEY_CHECKS During Import?

MySQL allows temporarily disabling foreign key checks within a session:

~~~sql
SET SESSION FOREIGN_KEY_CHECKS = 0;

-- Run prepared import operations.

SET SESSION FOREIGN_KEY_CHECKS = 1;
~~~

This is sometimes helpful when importing a dump with complex table order or when a tool loads data first and creates relationships afterward. However, understand the critical limitation:

**Re-enabling FOREIGN_KEY_CHECKS does not rescan loaded data for orphan rows.** If child rows without parents were loaded while checks were off, setting the variable back to 1 will not automatically detect or remove those invalid rows.

Therefore:

- Prefer keeping foreign key checks enabled and loading parent tables before child tables.
- If disabling is unavoidable, disable it only in the dedicated batch import session.
- Before re-enabling, run anti-join queries for every parent-child relationship.
- After re-enabling, confirm the variable is back to 1.
- Never allow applications to access data that remains in an unverified state.

~~~sql
SELECT @@SESSION.foreign_key_checks;
~~~

`FOREIGN_KEY_CHECKS` has both session and global scopes. A session change affects only the current connection; a global change affects new connections and requires appropriate administrative privileges. In import workflows, using session scope confines the blast radius.

Similarly, `unique_checks=0` is sometimes used to optimize InnoDB bulk loads when data is guaranteed duplicate-free. Use it only after verifying the data and understanding its effects; never use it to bypass unique key errors. For uncertain data, keep unique checks enabled so the database rejects duplicate records.

## 9. Adding Constraints After Loading Data

Some migrations create target tables first, load data, validate, and only then add unique keys and foreign keys. This can reduce the overhead of maintaining multiple indexes during bulk loads, but it is safe only if the data is thoroughly verified and the tables are not yet exposed to applications as valid data.

Before adding a unique key, search for duplicates:

~~~sql
SELECT email, COUNT(*) AS n
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;
~~~

If zero rows are returned and the column satisfies `NULL` rules, add the constraint:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Before adding a foreign key, search for orphan rows:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

If zero rows are returned, add the constraint:

~~~sql
ALTER TABLE orders
  ADD CONSTRAINT fk_orders_customer
  FOREIGN KEY (customer_id)
  REFERENCES customers (id)
  ON UPDATE RESTRICT
  ON DELETE RESTRICT;
~~~

If `customer_id` allows `NULL`, rows with `customer_id IS NULL` do not violate the foreign key. If business rules require every order to have a customer, the column must be declared `NOT NULL` and existing `NULL` rows resolved first.

`ALTER TABLE` may need to build indexes, scan all rows, or acquire a metadata lock. Estimate disk space, duration, write impact, and online DDL requirements for your MySQL version before running on large tables. Adding a constraint fails if existing data violates it; never ignore errors and treat the migration as complete.

## 10. Post-Load Integrity Checks

After loading, run verification queries again on the **target tables**, not only on staging.

### Checking Duplicates on Unique Keys

~~~sql
SELECT email, COUNT(*) AS n
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;

SELECT order_no, COUNT(*) AS n
FROM orders
GROUP BY order_no
HAVING COUNT(*) > 1;
~~~

If unique indexes already exist, these queries also verify data under the target column's comparison semantics. For composite keys, `GROUP BY` must include all components in the logical order of the business rule.

### Checking Orphan Rows

~~~sql
SELECT
  o.id,
  o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

The result must be empty. Repeat for every foreign key relationship, including multi-hop chains such as `order_items -> orders -> customers`.

### Checking Required Values and Value Domains

~~~sql
SELECT COUNT(*) AS missing_email
FROM customers
WHERE email IS NULL OR TRIM(email) = '';

SELECT COUNT(*) AS invalid_total
FROM orders
WHERE total_amount < 0;
~~~

Validate against real business rules. Some systems allow refund or negative-adjustment orders; in those cases, do not blindly enforce `total_amount >= 0`.

### Reconciling Counts

Compare row counts by batch, key range, or date between source and target. Do not compare full-table totals alone because two datasets can have identical row counts while containing different records.

Example:

~~~sql
SELECT COUNT(*) AS source_rows
FROM stg_orders;

SELECT COUNT(*) AS target_rows
FROM orders
WHERE import_batch_id = 'batch_2026_11_19';
~~~

For deeper checks, compare business aggregates such as total monetary amounts, order counts by status, and customer counts by segment. Aggregates must apply identical filter rules and batch scope.

### Checking Constraint Metadata

Inspect table definitions:

~~~sql
SHOW CREATE TABLE customers;
SHOW CREATE TABLE orders;
~~~

Verify registered constraints:

~~~sql
SELECT
  tc.TABLE_NAME,
  tc.CONSTRAINT_NAME,
  tc.CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS AS tc
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.TABLE_NAME IN ('customers', 'orders')
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME;
~~~

Inspect foreign key columns:

~~~sql
SELECT
  kcu.TABLE_NAME,
  kcu.CONSTRAINT_NAME,
  kcu.COLUMN_NAME,
  kcu.REFERENCED_TABLE_NAME,
  kcu.REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE AS kcu
WHERE kcu.CONSTRAINT_SCHEMA = DATABASE()
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
~~~

Verify constraint names, child columns, parent columns, and column order in composite keys. Seeing a constraint name exist is not enough to prove it references the intended table and columns.

## 11. Handling Bad Data and Safely Re-Running Migrations

Do not fix bad data by arbitrarily deleting rows just to make an import succeed. Each error type needs a policy:

| Error | Controlled Handling |
|---|---|
| Duplicate email | Identify the canonical record, merge, or fix source data per business rules |
| Source ID missing mapping | Supply the mapping or quarantine the record |
| Child row without parent | Load missing parents or exclude from batch after business sign-off |
| Uncastable value | Retain source value, log conversion error, and fix mapping |
| Duplicate against existing data | Explicitly decide insert, update, or skip per clear policy |
| Re-run batch | Use batch IDs, idempotent keys, and progress tracking to prevent double loads |

`INSERT IGNORE` and `REPLACE` are not generic error-handling tools. `INSERT IGNORE` can convert certain errors into warnings and skip rows; `REPLACE` can delete conflicting rows and insert new ones, triggering delete/cascade behavior depending on schema. If using `ON DUPLICATE KEY UPDATE`, explicitly identify which unique keys may collide and which fields may be updated.

After every import statement, immediately check inserted/updated counts, warnings, and errors. Example:

~~~sql
SHOW WARNINGS;
~~~

Run this immediately after the target statement because any subsequent SQL statement can overwrite the warning list. Archive batch logs, rows read, rows loaded, rejected rows, and reasons for auditing.

## 12. Sample Migration Workflow

A practical workflow for customers and orders:

1. **Capture source state:** record timestamp, data scope, row counts, and business aggregates to reconcile.
2. **Create staging:** hold source data and batch metadata.
3. **Normalize:** standardize date formats, numbers, character encoding, and business keys per agreed rules.
4. **Check uniqueness:** detect duplicate emails, order numbers, and composite keys.
5. **Check relationships:** validate customer mappings and orphan child rows.
6. **Load parent tables:** load `customers` and verify identifying keys.
7. **Load child tables:** load `orders`, then `order_items` in dependency order.
8. **Apply constraints:** create or verify PRIMARY KEY, UNIQUE KEY, and FOREIGN KEY constraints.
9. **Post-load reconciliation:** verify duplicates, orphans, `NULL`s, row counts, and business totals.
10. **Open application access:** shift traffic only after the batch is validated and a rollback/recovery plan is ready.

For migrations that must stay synchronized while applications continue writing, establish a snapshot strategy or dual-write/change-capture mechanism, define the cutover point, and reconcile post-snapshot deltas. Running a single export/import while the source keeps taking writes will not yield a point-in-time consistent copy.

## 13. Verification Checklist

**Before Loading**

- [ ] Defined PRIMARY KEY, UNIQUE KEY, and FOREIGN KEY according to business rules.
- [ ] Checked data types, signed/unsigned, charset, and collation across related columns.
- [ ] Found `NULL`, empty, duplicate, and malformed values in staging.
- [ ] Checked parent-child key mappings and orphan record counts.
- [ ] Selected load order, batch size, and re-run strategy.
- [ ] Decided whether constraints stay active during import.

**After Loading**

- [ ] Reconciled row counts by batch and business totals.
- [ ] Re-ran duplicate checks on target tables.
- [ ] Ran anti-join checks for each foreign key.
- [ ] Verified `NOT NULL` and value domains.
- [ ] Verified constraints via `SHOW CREATE TABLE` and `information_schema`.
- [ ] Read warnings/errors from the import statements.
- [ ] Saved verification results and opened traffic only after data confirmation.

## 14. Key Takeaways

- PRIMARY KEY identifies rows; UNIQUE KEY enforces non-duplication; FOREIGN KEY protects parent-child relationships.
- UNIQUE in MySQL allows multiple `NULL`s; use `NOT NULL` when business rules require a value.
- Collation determines string comparison and can make two strings differing only in case collide as duplicates.
- Data types and attributes on both sides of a foreign key must be compatible; appropriate indexes should exist on both sides.
- Load parent tables before child tables when foreign keys are enabled.
- Disabling `FOREIGN_KEY_CHECKS` does not cause MySQL to rescan existing data when re-enabled.
- Staging tables catch errors before bad data enters core tables.
- Post-load verification must cover duplicates, orphans, `NULL`s, row counts, business totals, and constraint metadata.
- Never use `IGNORE` or `REPLACE` to hide errors without understanding data policy.
- A migration is complete only when data is reconciled and traceable by batch.

Keys and constraints only protect data when designed around business rules and verified against real datasets. Treat staging, pre-load checks, constraint enforcement, and post-load reconciliation as mandatory steps in a repeatable, auditable data movement workflow.

## References

- [MySQL 8.0 Reference Manual: InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.0/en/innodb-foreign-key-constraints.html)
- [MySQL 8.0 Reference Manual: CREATE TABLE and UNIQUE Constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table.html)
- [MySQL 8.0 Reference Manual: Server SQL Modes and Data Conversion](https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html)
- [MySQL 8.0 Reference Manual: FOREIGN_KEY_CHECKS](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html#sysvar_foreign_key_checks)
