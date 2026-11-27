# Auditing Orphan Rows and the Risks of Disabling foreign_key_checks

In a sales system, every row in `order_items` must reference a real order in `orders`. If an import process writes order details before creating orders, or a script disables foreign key checks and loads bad data, the child table can contain `order_id` values that do not exist in the parent table. Such rows are called **orphan rows**.

MySQL can protect parent-child relationships with foreign keys, yet the `foreign_key_checks` variable allows temporarily disabling these checks within a session or changing the default for new connections. Re-enabling the variable does not automatically scan and verify rows written while checks were off. Therefore, you must know how to detect orphans, remediate bad data, and tightly govern any workflow that sets `foreign_key_checks=0`.

## 1. What Are Orphan Rows?

A foreign key requires values in a child table to reference a valid key in a parent table, unless the foreign key is allowed to be `NULL` under MySQL's rules.

Example:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE=InnoDB;
```

Every `orders.customer_id` must match a `customers.id`. If the `orders` table contains a row with `customer_id = 900` while no customer `id = 900` exists, that order row is an orphan with respect to `fk_orders_customer`.

Distinguish two cases:

- **Orphan child:** a child row has a non-`NULL` foreign key without a matching parent row. This is a referential integrity violation.
- **Parent without children:** a parent row is not yet referenced by any child row—for example, a customer who has not placed any orders yet. This is normally a valid business state, not an orphan.

Never delete a parent row just because it has no child rows, and never delete a child row simply because a query flagged it as an orphan. First determine the relationship and business meaning of the data.

## 2. How Do Foreign Keys Protect Data?

In InnoDB, foreign keys are checked on operations that could break referential relationships:

- On `INSERT` or `UPDATE` of a child row, the foreign key value must reference a valid parent row, unless exempted by `NULL`.
- On `DELETE` or `UPDATE` of a referenced key in the parent table, behavior follows `ON DELETE` and `ON UPDATE` rules such as `RESTRICT`, `CASCADE`, or `SET NULL`.
- Constraints are stored in schema metadata and enforced while `foreign_key_checks` is enabled.

The data types of the foreign key column and referenced column must be compatible. For numeric types, pay attention to width and `UNSIGNED`; for string types, pay attention to character set and collation. Related tables must use a storage engine supporting foreign keys, most commonly InnoDB.

InnoDB needs indexes to verify relationships. The referenced column must have a suitable index, usually `PRIMARY KEY` or `UNIQUE`; the child table also needs an index on the foreign key columns. If no child-side index exists, InnoDB can automatically create one when declaring the foreign key. Proactively design and name indexes so the schema remains readable and maintainable.

## 3. What Is foreign_key_checks?

`foreign_key_checks` is the system variable controlling whether MySQL enforces foreign key checks. Common values:

| Value | Meaning |
|---|---|
| `1` or `ON` | Enable foreign key checks |
| `0` or `OFF` | Disable foreign key checks within the configured scope |

Check current values:

```sql
SELECT
    @@SESSION.foreign_key_checks AS session_fk_checks,
    @@GLOBAL.foreign_key_checks AS global_fk_checks;
```

### 3.1. SESSION and GLOBAL Scopes

`foreign_key_checks` has both session and global scopes:

- `SET SESSION foreign_key_checks = 0` disables checks only in the current connection.
- `SET GLOBAL foreign_key_checks = 0` changes the default for connections opened afterward; already open sessions retain their own session state.
- When a session closes, its session state ends. A connection held in a connection pool can keep the altered value if the application fails to reset it.

Example disabling only for one session:

```sql
SET SESSION foreign_key_checks = 0;

-- Controlled import operation here.

SET SESSION foreign_key_checks = 1;
```

Never use `SET GLOBAL` for a routine import. Changing the global setting can cause new connections across the entire system to skip checks, allowing independent write streams to insert invalid data.

### 3.2. Re-Enabling Does Not Mean Existing Data Was Checked

This is the single most important operational fact in MySQL: **setting `foreign_key_checks = 1` does not cause MySQL to rescan rows written while checks were disabled**.

Example:

1. Session A disables `foreign_key_checks`.
2. Session A inserts a child row with a non-existent `customer_id`.
3. Session A re-enables `foreign_key_checks`.
4. The invalid child row remains in the table; MySQL does not retroactively delete, fix, or reject that row.

After step 3, new statements in the session are checked again, yet previously created orphans stay behind. Therefore, after every import or migration that disables checks, run audit queries to verify the data.

## 4. Detecting Orphans with Single-Column Foreign Keys

Suppose `orders.customer_id` references `customers.id`. Two query patterns are commonly used.

### 4.1. LEFT JOIN and IS NULL

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

`LEFT JOIN` retains every row from the child table. When no matching customer exists, columns on the `customers` side become `NULL`; the condition `c.id IS NULL` selects rows without a parent.

The `o.customer_id IS NOT NULL` filter clarifies that an optional relationship can omit a reference value. If the column is `NOT NULL`, this condition is redundant yet still clarifies intent for readers.

### 4.2. NOT EXISTS

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

`NOT EXISTS` directly expresses the intent: no parent row exists whose key equals the child row's foreign key. This pattern scales cleanly when relationships span multiple columns or include additional predicates.

### 4.3. Count First, Sample Later

On large tables, count orphans first before fetching detailed rows:

```sql
SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Fetch a sample of rows for investigation:

```sql
SELECT o.id, o.customer_id, o.created_at
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  )
ORDER BY o.id
LIMIT 100;
```

Do not dump all orphan rows to terminals or logs if the table holds personal data. Select minimal identifying columns, mask sensitive fields, and limit row counts.

## 5. Detecting Orphans with Composite Foreign Keys

A foreign key can consist of multiple columns. For example, `order_lines` uses the composite key `(order_id, line_no)` to identify a line item; `shipment_items` references that key pair.

```sql
CREATE TABLE order_lines (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE shipment_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NULL,
    line_no INT UNSIGNED NULL,
    shipped_qty INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_shipment_order_line (order_id, line_no),
    CONSTRAINT fk_shipment_order_line
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines (order_id, line_no)
) ENGINE=InnoDB;
```

Orphan audit query:

```sql
SELECT
    s.id,
    s.order_id,
    s.line_no
FROM shipment_items AS s
WHERE s.order_id IS NOT NULL
  AND s.line_no IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS ol
      WHERE ol.order_id = s.order_id
        AND ol.line_no = s.line_no
  );
```

With composite foreign keys in MySQL, if **any component of the foreign key is `NULL`**, the row is not required to reference a parent row and is exempt from relationship checking. Therefore, when auditing orphans under this rule, check only rows where every component is non-`NULL`.

If business rules require the key pair to always provide both values, declare both columns `NOT NULL`. If an optional relationship is allowed, clearly define what a partial `NULL` means; avoid leaving half-populated data such as a present `order_id` with a `NULL` `line_no` if the business rejects it.

## 6. Discovering Existing Foreign Keys

Before writing audit queries, identify which constraints are declared, which columns participate, and which tables are referenced.

### 6.1. List Foreign Keys in the Current Schema

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

The `REFERENTIAL_CONSTRAINTS` view provides constraint names and `ON UPDATE`/`ON DELETE` behaviors.

### 6.2. Inspect Columns of Each Foreign Key

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

`ORDINAL_POSITION` shows column order within composite keys. Group columns sharing the same `CONSTRAINT_SCHEMA`, `TABLE_NAME`, and `CONSTRAINT_NAME` to reconstruct exact child-parent column pairs. Do not check individual columns separately when a constraint is composite; compare the full tuple.

### 6.3. Verify Actual DDL

```sql
SHOW CREATE TABLE orders\G
SHOW CREATE TABLE order_lines\G
SHOW CREATE TABLE shipment_items\G
```

`SHOW CREATE TABLE` displays the constraints actually defined on the server, index names, column types, and storage engines. Compare live DDL against source-controlled migrations if schema drift is suspected.

Metadata views only display objects the current account has privileges to see. If a constraint appears missing, check the selected schema and privileges before concluding the constraint does not exist.

## 7. Orphans Differ from Unused Parents

A query finding parents without children serves a different purpose from an orphan audit query.

Example finding customers without orders:

```sql
SELECT c.id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

This is likely a report of customers who have not purchased yet, not an integrity error. An orphan is a child row missing its parent; a childless parent is simply an unreferenced parent row. The two concepts check in opposite directions.

Never use a childless-parent query to decide on bulk deletions without checking all other relationships, retention periods, and business rules.

## 8. Why Can Orphan Rows Appear?

In a properly designed and operated system, foreign keys prevent new orphans. However, orphan rows can still appear in scenarios such as:

- A process disabled `foreign_key_checks` and imported child rows referencing non-existent parents.
- Data was loaded from legacy files, external systems, or inconsistent dumps.
- An application wrote data into tables lacking foreign keys or using a storage engine that does not enforce constraints.
- A migration dropped constraints, changed data types, or altered relationship structures incompletely.
- Data was modified directly by admin scripts, ETL jobs, or sync tools.
- The system previously used MyISAM or another non-FK engine, then migrated to InnoDB without cleaning existing data.
- Partial data was restored from backups taken at different points in time, leaving parent-child relationships out of sync.

If orphans are discovered even though `foreign_key_checks` is currently on, do not assume MySQL skipped enforcing a constraint. Investigate when the data was written, the table's storage engine, actual constraints, which session ran the import, and migration history.

## 9. Risks of Disabling foreign_key_checks

Disabling checks can be convenient in certain controlled import workflows, yet it removes referential protection across the affected session.

### 9.1. Writing Data Without a Parent Becomes Possible

While checks are off, `INSERT` or `UPDATE` statements can write foreign key values that do not exist in the parent table. Those rows stay behind after checks are turned back on.

Example in a test session:

```sql
SET SESSION foreign_key_checks = 0;

INSERT INTO orders (id, customer_id)
VALUES (7001, 999999);

SET SESSION foreign_key_checks = 1;
```

If customer `999999` does not exist, the order row is still saved. Re-enabling checks does not roll back or delete this row.

### 9.2. Referential Integrity Gaps Can Form

While checks are off, the system might:

- Write child rows before parent rows are loaded.
- Modify referenced keys without matching parent rows.
- Apply schema changes or imports that leave relationships inconsistent.
- Expose incomplete data to concurrent application reads.

If multiple processes or sessions operate concurrently, pinpoint exactly which connection disabled checks. `SET SESSION` affects only that session; disabling globally can affect new connections and widen the blast radius.

### 9.3. Re-Enabling Does Not Certify Existing Data

There is no automatic re-validation of existing data when resetting the variable to `1`. Therefore, running:

```sql
SET SESSION foreign_key_checks = 1;
```

only restores checking for subsequent operations in that session. It does not prove existing rows satisfy the foreign keys.

### 9.4. Disabling Checks Is Not a Fix for Foreign Key Errors

If an `INSERT` fails with error `1452`, the usual cause is a missing parent row or a wrong foreign key value. Disabling checks to force the statement through only hides the error and creates orphans. Inspect the parent record, input data, and import ordering first.

If `DELETE` or `UPDATE` on a parent fails with error `1451`, inspect child relationships and `ON DELETE`/`ON UPDATE` rules. Never disable checks to delete a parent before deciding whether child data must be preserved, reassigned, or deleted per business rules.

## 10. When Can foreign_key_checks Be Temporarily Disabled?

A few situations may justify disabling checks inside an isolated session:

- Importing a large, pre-verified dataset from a trusted source accompanied by a post-import audit procedure.
- Loading multiple tables in an inconvenient order when the dataset's relationships have already been validated upfront.
- Rebuilding or restoring schemas in a controlled maintenance window.

Even in these cases, the preferred option remains loading parent tables before child tables so checks stay enabled. Only disable checks when there is a clear technical justification and measured benefit.

Do not disable checks in these situations:

- Normal application business requests.
- Payment, order, inventory, or balance transactions.
- Scheduled scripts lacking audit steps and error reporting.
- Live production receiving concurrent writes without a maintenance window or control plan.
- Whenever affected foreign keys are unknown and no orphan remediation procedure exists.

## 11. Safe Import Workflow When Disabling Checks Is Unavoidable

Suppose you must load data from a dump file into an already-created schema. Execute inside a dedicated connection with logging and full process control.

### Step 1: Verify Source and Structure

- Inspect the source file, export timestamp, and target schema.
- Confirm table engines and DDL.
- List foreign keys via `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` and `KEY_COLUMN_USAGE`.
- Ensure backups and a recovery plan are ready.
- If possible, order the import with parents before children so disabling checks is unnecessary.

### Step 2: Save the Initial Session State

```sql
SET @old_foreign_key_checks = @@SESSION.foreign_key_checks;
SELECT @old_foreign_key_checks;
```

Record the value so you restore the exact initial state. Never assume the initial state is always `1` if connection initialization might alter the session.

### Step 3: Disable Checks in the Target Session

```sql
SET SESSION foreign_key_checks = 0;
SELECT @@SESSION.foreign_key_checks;
```

Verify the output is `0` on the exact connection running the import. Never open another tab or connection and assume it shares the same state.

### Step 4: Load Data and Verify Import Output

Run the import inside the same connection or a tool with explicitly configured session scope. Check exit codes, error logs, source/target row counts, and loaded tables. If the tool opens a fresh connection per chunk, verify the mode on every connection; session settings do not carry over across connections.

### Step 5: Re-Enable Even If the Import Fails

```sql
SET SESSION foreign_key_checks = @old_foreign_key_checks;
SELECT @@SESSION.foreign_key_checks;
```

In applications, place restoration inside cleanup logic equivalent to `finally`. Never return a connection to a pool without restoring/resetting session state. If the connection drops, the old session ends; on a fresh connection, verify the default value before proceeding.

### Step 6: Audit Orphans Before Opening Traffic

Run orphan queries for every relevant foreign key, including single-column and composite keys. Confirm the count is `0`, or produce an explicitly approved exception list with remediation. Only reopen application traffic once data passes integrity checks.

### Step 7: Log and Reconcile

Record the import source, timestamp, connection, pre/post check status, loaded row counts, detected orphans, and remediation actions. For large datasets, run additional checksum verification or business reconciliation.

## 12. Remediating Orphan Rows

There is no one-size-fits-all fix for every orphan. Choose the action based on what the data means.

### 12.1. Restore Missing Parent Rows

If child rows are valid and parent rows were omitted due to an incomplete import, restore the parent rows from an authoritative source. Before inserting, verify keys, mandatory attributes, and the parent's other relationships.

```sql
-- Example only after verifying customer 999999 genuinely exists
-- in the authoritative source and can be restored.
INSERT INTO customers (id, full_name)
VALUES (999999, 'Restored Customer');
```

Never invent a fake parent named `Unknown` just to make the orphan query return zero rows. That makes keys look superficially valid while corrupting business data.

### 12.2. Reassign the Foreign Key to the Correct Parent

If `customer_id` was misassigned, look up the true customer from an authoritative source or mapping table and update it:

```sql
UPDATE orders
SET customer_id = 120
WHERE id = 7001
  AND customer_id = 999999;
```

Including the old value in `WHERE` prevents overwriting if another process already corrected the row. In real systems, verify the mapping and inspect affected row counts.

### 12.3. Set NULL If the Relationship Is Optional

If business rules permit an order without an attached customer, the column must allow `NULL` and business rules must accept that state:

```sql
UPDATE orders
SET customer_id = NULL
WHERE id = 7001
  AND customer_id = 999999;
```

Do not use `NULL` to evade constraints when the relationship is actually mandatory. Before updating, check whether applications, reports, and queries assume `customer_id` is always non-null.

### 12.4. Archive or Delete Child Rows

If child rows are test artifacts, import junk, or hold no business value, archive or delete them after approval. Before deleting, take needed backups, inspect downstream child tables, and assess reporting/audit impacts.

Never run a mass `DELETE` based solely on an unreviewed orphan query. Build an explicit list of IDs to remediate, verify with the data owner, and check affected row counts.

## 13. Transactions and Consistency During Audits

Audit queries on InnoDB tables can observe data changing concurrently. When a point-in-time consistent report is needed, use a consistent snapshot:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );

COMMIT;
```

In InnoDB, consistent reads within the transaction share the same read view according to the isolation level and snapshot start time. Results reflect state at that snapshot; data can still change after the transaction ends.

If you need to both audit and remediate, control concurrent writers. You can pause writers, use a maintenance window, or run remediation with explicit locking and update predicates. A plain `SELECT` audit query does not stop another application from introducing changes immediately afterward.

Do not hold snapshot transactions open unnecessarily long on large tables. Long-lived read views retain old row versions in undo logs and increase purge pressure. Batch the work or use an appropriate maintenance window.

## 14. Re-Adding or Verifying Foreign Keys After Cleanup

If a table lacks a foreign key yet, audit and clean data before adding the constraint:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

When checks are enabled, MySQL/InnoDB validates existing data while adding a foreign key; if orphans exist, the DDL fails. This DDL may acquire metadata locks and perform validation across a large table, so evaluate duration, resources, and application impact.

If the constraint already existed while data may have been written with checks disabled, re-enabling the variable does not verify legacy data. Run the audit query. One way to force the server to re-validate data against the constraint definition is dropping and re-adding the foreign key while checks are enabled, after cleanup and inside a controlled maintenance window. This is DDL with an implicit commit, may acquire locks, and creates a brief window where the constraint does not exist; never treat it as rollbackable inside a normal transaction.

Once complete, verify:

```sql
SHOW CREATE TABLE orders\G

SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Output should confirm the expected constraint exists and zero orphans remain in that relationship.

## 15. Performance When Auditing Orphans on Large Tables

Scanning an entire table can consume substantial I/O and CPU. Optimize for data scale:

- Ensure the child-side foreign key column is indexed and the parent-side referenced column has a suitable index.
- Use `NOT EXISTS` or an anti-join with clear predicates; read `EXPLAIN` to inspect MySQL's chosen plan.
- Count orphans first; fetch detail rows only when investigating.
- For very large tables, partition the audit by primary key ranges or time ranges to limit work per batch.
- Run audits during low-traffic hours if queries compete with OLTP workloads.
- Do not add redundant indexes solely for a one-off audit; weigh long-term write and storage costs.
- Record execution time, rows scanned, and orphan counts to compare across audits.

Example auditing by ID range:

```sql
SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.id >= 100000
  AND o.id < 200000
  AND o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Batching merely structures the work; for a globally consistent result, use a single snapshot or prevent writes throughout the entire audit window. Otherwise, batches executed at different times may reflect different data states.

## 16. Common Foreign Key Error Codes

| Error Code | Scenario | Investigation Path |
|---:|---|---|
| `1452` | Cannot add/update a child row because no matching parent row exists | Check FK value, parent row, import order, and session `foreign_key_checks` |
| `1451` | Cannot delete/update a parent row because referencing child rows exist | Inspect child table, referencing row count, and `ON DELETE`/`ON UPDATE` rules |
| `1215` or version-specific FK creation error | Cannot add foreign key | Check engine, data types, signedness, charset/collation, indexes, and constraint names |
| `1005` with errno 150 in some cases | Invalid or incompatible foreign key definition | Inspect `SHOW ENGINE INNODB STATUS` and compare DDL of both tables |

After a foreign key creation failure, inspect:

```sql
SHOW ENGINE INNODB STATUS\G
```

The `LATEST FOREIGN KEY ERROR` section typically provides extra details on the most recent foreign key creation or operation failure. This section can be overwritten by newer errors, so capture it promptly near the time of failure.

## 17. Checklist Before and After Disabling foreign_key_checks

Before disabling:

- Do I have a concrete technical reason, and have I tried loading parents before children first?
- Have all affected foreign keys and tables been identified accurately?
- Are backups, an authoritative data source, and a recovery plan in place?
- Can this run inside a dedicated connection using `SESSION` scope only?
- Was the initial `@@SESSION.foreign_key_checks` value saved?
- Could other writers or a connection pool mutate the session state?

After importing:

- Was `foreign_key_checks` restored to its initial value?
- Did the connection pool reset session state before returning the connection?
- Was an orphan audit run for every single-column and composite foreign key?
- Did composite key audits handle rows with one or more `NULL` components properly?
- Is the orphan count 0 or covered by an approved remediation plan?
- Have DDL, row counts, error logs, and reconciliation checks been verified?
- Were timestamp, import source, and audit results logged?

## Conclusion

Orphan rows are child rows whose foreign keys lack matching parent rows. Use `LEFT JOIN ... IS NULL` or `NOT EXISTS` to detect them, while properly handling composite keys and `NULL` values. Setting `foreign_key_checks=0` can assist controlled imports, yet it allows relationship-violating data to enter tables; re-enabling checks does not verify previously written rows. Prefer keeping checks enabled, loading parents before children, disabling checks only in an isolated session when truly necessary, and always auditing, remediating data, and verifying constraints before reopening application traffic.
