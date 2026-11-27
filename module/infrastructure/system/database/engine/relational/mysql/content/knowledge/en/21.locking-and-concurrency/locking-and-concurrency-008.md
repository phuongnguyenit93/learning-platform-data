# Foreign key checks, unique key checks, and contention hotspots

Foreign keys (FK) and unique keys both protect data integrity and participate in InnoDB's locking mechanism. When a transaction inserts a child row, MySQL must verify that the referenced parent row exists. When adding a value to a unique index, InnoDB must ensure no other transaction commits the same unique key. These checks can cause transactions to wait, receive duplicate-key errors, fail foreign key checks, or enter deadlocks.

Therefore, investigating contention is not merely finding which `UPDATE` statement is waiting. You need to know which constraint is being checked, which index is used, which transaction holds record/gap locks, and whether many requests are converging on the same key. The exact same constraint design can protect data accurately yet create a hotspot when a high volume of transactions hit the same parent row or unique value simultaneously.

This lesson belongs to the `DATABASE_MYSQL` module, covering table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and handling relational database operational issues. The goal is to inspect constraints using metadata and real data, understand concurrent execution schedules around FK/UNIQUE, and choose ways to reduce contention while preserving business invariants.

After this lesson, you will be able to:

- Inspect FK and UNIQUE definitions using `SHOW CREATE TABLE` and `INFORMATION_SCHEMA`.
- Detect orphan references and duplicate values before adding constraints.
- Understand data type, index, and column order requirements for foreign keys.
- Explain how InnoDB locks during FK and unique index checks.
- Reproduce contention between a child insert and a parent delete/update.
- Reproduce two transactions concurrently inserting the same unique key and predict commit/rollback outcomes.
- Identify hotspots caused by parent rows, unique keys, cascades, and lock ordering.
- Observe lock waits, deadlocks, and access paths using Performance Schema, `sys`, and `EXPLAIN`.
- Reduce contention via appropriate indexes, short transactions, consistent operation ordering, and suitable write designs.

## 1. How do constraints protect data?

The two constraint types serve different purposes:

| Constraint | Protected rule | Example |
| --- | --- | --- |
| `FOREIGN KEY` | The referenced key value in the child table must point to a valid row in the parent table, or be `NULL` if the column allows it | `employees.department_id` must reference an existing `departments.department_id` |
| `UNIQUE` | Disallows two rows having the same unique key value combination under the index's comparison rules | Login email must not be duplicated |

An FK does not by itself enforce a one-to-one relationship. Multiple child rows can reference the same parent row. If you want a parent row to be referenced at most once, add a unique constraint on the FK column in the child table.

UNIQUE does not replace FK. A `department_id` can be unique in the child table and still point to a nonexistent department if there is no FK.

In InnoDB, constraints are checked during statement execution, not solely when the client calls `COMMIT`. MySQL does not support deferred foreign key constraints of the "wait until end of transaction to validate" style.

## 2. Creating a lab schema with FK and UNIQUE

Run the setup once in a test schema. Tables use InnoDB and names have the `cc_` prefix for easy identification.

```sql
DROP TABLE IF EXISTS cc_employees;
DROP TABLE IF EXISTS cc_departments;

CREATE TABLE cc_departments (
    department_id INT UNSIGNED NOT NULL,
    department_code VARCHAR(20) NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id),
    CONSTRAINT uq_cc_departments_code UNIQUE (department_code)
) ENGINE = InnoDB;

CREATE TABLE cc_employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT UNSIGNED NULL,
    email VARCHAR(190) NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (employee_id),
    CONSTRAINT uq_cc_employees_email UNIQUE (email),
    KEY idx_cc_employees_department (department_id),
    CONSTRAINT fk_cc_employees_department
        FOREIGN KEY (department_id)
        REFERENCES cc_departments (department_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;

INSERT INTO cc_departments (department_id, department_code, department_name) VALUES
(10, 'ENG', 'Engineering'),
(20, 'SAL', 'Sales');

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(1, 10, 'an@example.com', 'An'),
(2, 10, 'binh@example.com', 'Binh'),
(3, 20, 'chi@example.com', 'Chi'),
(4, NULL, 'dung@example.com', 'Dung');
```

In this fixture:

- `cc_departments.department_id` is the parent key.
- `cc_departments.department_code` is a unique key.
- `cc_employees.department_id` is a nullable FK; multiple employees can belong to the same department.
- `cc_employees.email` is a unique key and `NOT NULL`.
- Index `idx_cc_employees_department` supports looking up child rows by FK.

If you need to re-run the script, drop the child table before the parent table because the FK references the parent table.

## 3. Inspecting constraint definitions

### 3.1. SHOW CREATE TABLE

This is the fastest way to see the actual definitions stored by MySQL:

```sql
SHOW CREATE TABLE cc_departments;
SHOW CREATE TABLE cc_employees;
```

Check:

- Is the storage engine InnoDB?
- Does the FK reference the right table and right columns?
- Do `ON DELETE` and `ON UPDATE` match the business policy?
- Is the FK column nullable or not?
- Do unique keys have the right columns and column order?
- Does an index supporting the FK column exist?

Do not read only migration source files. The actual schema can differ due to legacy migrations, manual edits, or incomplete deployments.

### 3.2. Inspecting constraints via INFORMATION_SCHEMA

List table constraints:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    tc.TABLE_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.TABLE_NAME IN ('cc_departments', 'cc_employees')
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME;
```

View FK columns and referenced columns:

```sql
SELECT
    kcu.CONSTRAINT_NAME,
    kcu.TABLE_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME,
    kcu.POSITION_IN_UNIQUE_CONSTRAINT
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
WHERE kcu.CONSTRAINT_SCHEMA = DATABASE()
  AND kcu.TABLE_NAME = 'cc_employees'
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

View referential actions:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND TABLE_NAME = 'cc_employees';
```

### 3.3. Inspecting indexes and unique indexes

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('cc_departments', 'cc_employees')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`NON_UNIQUE = 0` indicates a unique index. `SEQ_IN_INDEX` shows column order in a composite index; `SUB_PART` shows whether the index uses a prefix length. For a composite unique index, the entire combination of columns forms the protected key.

## 4. Checking data before adding an FK

Before adding an FK to a table that already contains data, find child values lacking a corresponding parent row:

```sql
SELECT
    e.employee_id,
    e.department_id
FROM cc_employees AS e
LEFT JOIN cc_departments AS d
    ON d.department_id = e.department_id
WHERE e.department_id IS NOT NULL
  AND d.department_id IS NULL;
```

The expected result is empty. The condition `e.department_id IS NOT NULL` excludes rows without an assigned relationship; a nullable FK permits those rows.

If rows are returned, classify them before adding the constraint:

- Missing parent ID due to imported data: locate and restore the proper parent row.
- Wrong child ID: fix it to a valid ID using a verified mapping.
- Truly optional relationship: allow `NULL` if business rules permit.
- Data that cannot be fixed automatically: route to a separate cleanup workflow rather than arbitrarily assigning a parent ID.

When running `ALTER TABLE ... ADD CONSTRAINT FOREIGN KEY`, InnoDB validates existing data. If any orphan reference exists, adding the FK fails.

### 4.1. Checking data type compatibility

FK columns and referenced columns must be compatible. For integer types, width and signedness must match; for example, `INT UNSIGNED` should reference `INT UNSIGNED`, not arbitrarily pair with signed `INT`. For string types, charset and collation must be compatible.

For composite FKs, the column count and order on both sides must match:

```sql
FOREIGN KEY (tenant_id, department_code)
REFERENCES departments (tenant_id, department_code)
```

The parent-side index must support the exact referenced column order. In new designs, prefer referencing an explicit primary key or unique key. InnoDB historically permitted certain references to non-unique or partial indexes outside the standard, but that nonstandard behavior is deprecated and configuration/version-dependent; do not build new schemas on it.

InnoDB requires an index on the child side to check and locate referencing rows. If no suitable index exists yet, MySQL can automatically create the needed index. Even so, declare and name indexes explicitly to manage the schema cleanly, avoid redundant indexes, and control access paths.

## 5. Checking data before adding UNIQUE

Before adding a unique key, find duplicate groups under the exact comparison rules the index will use:

```sql
SELECT
    email,
    COUNT(*) AS duplicate_count
FROM cc_employees
GROUP BY email
HAVING COUNT(*) > 1;
```

If a string column uses a case-insensitive collation, `GROUP BY` normally applies that same collation's comparison rules. Thus, two strings differing only in letter case can be considered duplicates by the unique index.

For a composite unique key:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS duplicate_count
FROM imported_records
WHERE tenant_id IS NOT NULL
  AND external_code IS NOT NULL
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

The filter condition here assumes both columns allow NULL. A MySQL unique index allows multiple rows containing `NULL` in one or more key components; those rows are not considered duplicates under standard unique comparison rules. If the columns are `NOT NULL`, the `WHERE` clause can be omitted.

### 5.1. NULL in UNIQUE

MySQL permits multiple `NULL` values in a unique index:

```sql
CREATE TABLE cc_optional_codes (
    row_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    external_code VARCHAR(50) NULL,
    UNIQUE KEY uq_cc_optional_codes_external_code (external_code)
) ENGINE = InnoDB;

INSERT INTO cc_optional_codes VALUES
(1, NULL),
(2, NULL),
(3, 'A-100');
```

The first two rows do not violate the unique key. If business rules require every row to have a code and for it to be unique, declare `NOT NULL` alongside `UNIQUE`.

### 5.2. Collation and the meaning of "duplicate"

For strings, a unique index applies the column's collation rules. For example, a case-insensitive `_ci` collation can treat `User@example.com` and `user@example.com` as the same key. Some collations also treat accented or equivalent characters identically.

Before adding a unique index on email, username, or external codes:

- Check the column's charset/collation.
- Determine whether business rules are case-sensitive or case-insensitive.
- Normalize data according to the agreed rules.
- Run duplicate-detection queries using the same collation.
- Check the index length and chosen data type.

Do not switch to another collation just to make a migration pass without assessing impacts on login, search, and existing data.

## 6. Safely adding and modifying constraints

Example adding an FK after verifying data:

```sql
ALTER TABLE cc_employees
ADD CONSTRAINT fk_cc_employees_department
FOREIGN KEY (department_id)
REFERENCES cc_departments (department_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

In the section 2 fixture, the FK was already declared at table creation; do not re-run this `ALTER` on that same table. The snippet above illustrates a migration for a table lacking the constraint.

Adding a unique index:

```sql
ALTER TABLE cc_employees
ADD CONSTRAINT uq_cc_employees_email UNIQUE (email);
```

If the unique key already exists in the lab schema, do not run it again. For production migrations, check metadata beforehand and plan for metadata lock duration, index build time, temporary disk space, and DML impact.

DDL can wait for a metadata lock if another transaction holds a metadata lock on the table. "Online DDL" does not mean zero metadata locks across all phases. Verify supported `ALGORITHM`/`LOCK` options for your exact operation and MySQL version; do not force options unsupported by the engine.

## 7. How InnoDB locks during foreign key checks

An FK is not merely a logical metadata check. InnoDB must protect the relationship from concurrent changes.

### 7.1. Child INSERT checking parent

When a transaction inserts a child row with a non-`NULL` FK, InnoDB must verify that the corresponding parent row exists. The FK check can place a shared record lock on the checked parent record. The lock is held for the transaction duration, so conflicting deletes or key updates on the parent may have to wait.

Shared locks on the same parent row can usually coexist with other shared locks; this does not mean all child inserts referencing the same parent are serialized. Prominent contention occurs when another transaction tries to delete/modify the parent or when concurrent child inserts conflict on another unique key/index.

### 7.2. Parent DELETE/UPDATE checking child

When deleting a parent row or changing a referenced key, InnoDB must check the child table to ensure the FK action is valid. With `RESTRICT`/`NO ACTION`, if referencing child rows exist, the parent operation is rejected. This check can lock relevant records/index entries in the child table.

An index on the child-side FK column is vital for locating referencing rows. InnoDB requires an index supporting the FK; a suitable index also prevents the check from scanning a wide region of data.

### 7.3. Execution schedule: child INSERT competing with parent DELETE

Use the `cc_departments` and `cc_employees` schema from section 2. Pick department 10, which has not been deleted.

**Session A:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(1001, 10, 'new.employee@example.com', 'New Employee');

-- Not yet committed: FK check has verified parent 10.
```

**Session B:**

```sql
START TRANSACTION;

DELETE FROM cc_departments
WHERE department_id = 10;
```

The DELETE in B can wait for the lock related to the parent row held by A during its FK check. When A finishes:

**Session A:**

```sql
COMMIT;
```

Then B resumes its FK check and is rejected because department 10 now has a referencing child row, per `ON DELETE RESTRICT`.

If B locks/deletes the parent before A performs its FK check, A's child insert may have to wait. If B commits deleting the parent, A resumes and receives a foreign key error because the parent no longer exists. Transaction ordering determines who waits and which statement fails; the constraint ensures no orphaned child reference is ever committed.

To re-run the example, roll back/commit sessions cleanly and delete employee 1001 if it was previously committed.

## 8. ON DELETE and ON UPDATE change the scope of work

Common referential actions:

| Action | Meaning | Concurrency impact |
| --- | --- | --- |
| `RESTRICT` | Rejects deleting/modifying parent key if referencing child rows exist | Checks and locks related records; statement may wait or fail |
| `NO ACTION` | In InnoDB equivalent to `RESTRICT`, checked immediately | Not a deferred constraint |
| `CASCADE` | Deletes/updates child rows following changes on the parent row | Can update/delete many child rows and hold many locks |
| `SET NULL` | Sets the FK column in child rows to NULL | FK column must allow NULL; many child rows may be updated |

### 8.1. CASCADE can amplify a single operation

A single `DELETE` targeting one parent row can trigger deleting thousands of child rows if `ON DELETE CASCADE` is used. It is a single statement, yet lock scope, undo logs, redo logs, and transaction duration can be huge.

Before using cascade on a high fan-out relationship:

- Estimate the maximum number of child rows.
- Ensure proper FK indexes exist.
- Evaluate deadlocks against concurrent workflows updating the child table.
- Consider batched deletes at the application layer if business rules permit and load control is needed.
- Do not split a cascade operation into multiple transactions if doing so exposes invalid intermediate states.

### 8.2. SET NULL

If using `ON DELETE SET NULL`, the FK column must be nullable. If the column is `NOT NULL`, the design is incompatible. Also review application logic because `NULL` may mean "unassigned" rather than "parent was deleted."

## 9. How InnoDB locks during UNIQUE checks

A unique index is the final mechanism protecting uniqueness in a multi-transaction environment. Application-level checks such as "SELECT first, if missing then INSERT" are insufficient because two requests can simultaneously see no existing row.

Example:

```sql
SELECT employee_id
FROM cc_employees
WHERE email = 'same@example.com';

-- Only if no row exists does the application INSERT.
```

Two transactions can both run the SELECT and both get empty results. The unique index must still be declared so that one INSERT wins and the other cannot create a duplicate.

### 9.1. Execution schedule: two transactions concurrently INSERTing the same unique key

Before running, confirm the email `race@example.com` does not yet exist.

**Session A:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(2001, 10, 'race@example.com', 'Race A');

-- Not yet committed.
```

**Session B:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(2002, 10, 'race@example.com', 'Race B');
```

B's INSERT typically must wait for the outcome of transaction A because the unique index cannot decide whether there is a duplicate until A commits or rolls back.

If A runs:

```sql
COMMIT;
```

then B resumes and receives a duplicate-key error. If A runs `ROLLBACK`, B can proceed and succeed because the unique value is no longer held by A.

The constraint guarantees two rows with the same email can never be committed. This outcome does not depend on whether the application ran a prior check query.

### 9.2. Composite unique keys

With:

```sql
UNIQUE KEY uq_tenant_external_code (tenant_id, external_code)
```

MySQL guarantees that the combination `(tenant_id, external_code)` is unique, not each individual column. Two different tenants can use the same external code. Column order in the index affects both unique key definition and index usability for queries.

If `NULL` exists in any component, the unique index allows multiple combinations containing NULL under MySQL's NULL rules. If business logic requires strict uniqueness for every row, key components should be `NOT NULL` or use a suitable normalized design.

### 9.3. Collation, prefix indexes, and functional uniqueness

A unique index on strings uses the column/index collation. A case-insensitive column can treat two strings differing only in case as duplicates.

A unique prefix index enforces uniqueness only on the indexed prefix. For example, `UNIQUE KEY (code(8))` can reject two codes sharing the same first eight characters even if their suffixes differ. Do not use a prefix unique index if business rules require uniqueness across the full string.

With a functional index or a unique index on a generated column, the normalized expression value is what gets protected. Test with the exact same expression/collation during pre-migration duplicate detection.

## 10. Duplicate-handling statements and consequences

### 10.1. Standard INSERT

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'Another An');
```

Because the email already exists, the statement fails with a duplicate-key error. Inside an explicit transaction, a statement error does not necessarily roll back the entire transaction automatically; the application must decide to roll back when business logic cannot continue.

### 10.2. INSERT ... ON DUPLICATE KEY UPDATE

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'An Updated')
ON DUPLICATE KEY UPDATE
    employee_name = VALUES(employee_name);
```

The `VALUES(col)` syntax in the update clause is deprecated in newer MySQL versions; for new code, use a row alias per your deployment version's syntax. MySQL 8.4 example:

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'An Updated') AS incoming
ON DUPLICATE KEY UPDATE
    employee_name = incoming.employee_name;
```

This statement can trigger the update branch upon conflicting with any PRIMARY KEY or UNIQUE index. If the table has multiple unique keys, do not assume only `email` determines which row gets updated. Review the design and clearly verify the business conflict target; MySQL lacks syntax to target a single specific constraint like some other database systems.

### 10.3. INSERT IGNORE

`INSERT IGNORE` can downgrade certain errors into warnings and skip offending rows. This can be useful for intentional imports, but it can also mask bad data or other conversion issues. Afterward, always inspect warnings and actual inserted row counts.

### 10.4. REPLACE

`REPLACE` has delete-then-insert semantics for conflicting rows in applicable cases; it is not simply an UPDATE. This behavior can affect foreign keys, cascades, triggers, auto-increment values, and omitted columns. Do not use `REPLACE` as a substitute for update without evaluating all side effects.

## 11. Identifying hotspots and contention patterns

Not every delay stems from the same lock type. Distinguish row/index locks, gap/next-key locks, metadata locks, and internal latches.

| Hotspot | Possible symptoms | Common cause |
| --- | --- | --- |
| One parent row referenced by many child inserts | Parent delete/update waits; child inserts wait when parent is locked | Many transactions checking the same parent key or one flow deleting/updating the parent |
| One unique value written by many requests | Duplicate-key errors or lock waits on the same unique entry | Requests competing on the same username, email, external reference, or idempotency key |
| One unique counter/sequence row | Many transactions waiting on the same row | Using a single row as a global counter |
| High fan-out cascade | Long transactions, many row locks, deadlocks | Deleting/updating a parent affects a huge number of child rows |
| Child FK index poorly matched to business queries | Wide scans, many records checked/locked | Index missing leading columns, wrong column order, or non-sargable predicates |
| Monotonic inserts into the same index region | Page/latch contention even without long row-lock waits | Many inserts concentrated on the rightmost page of a B-tree or a hot index |
| DDL on an actively used table | Metadata lock waits | Long transactions holding metadata locks or migrations running concurrently with workload |

### 11.1. Many child inserts referencing the same parent

Shared record locks for FK checks can coexist. Therefore, do not conclude that sharing a parent ID automatically serializes all child inserts. Contention usually becomes pronounced when a transaction tries to delete/update the parent, or when concurrent inserts collide on another unique index, auto-increment/index page, or other resource.

If a parent row contains frequently updated shared status, consider separating rarely changed parent info from hot counters/states, or updating state via an explicit protocol. Do not drop an FK just to reduce waits if the relationship still needs protection.

### 11.2. Hot unique keys and idempotency keys

An endpoint may receive the same idempotency key from multiple concurrent retry requests. A unique index is the right mechanism to allow only one request to create the canonical record. Other requests may wait and then receive a duplicate error; the application should read back the saved result and return the same business response rather than treating every duplicate as an unrecoverable failure.

If a system uses a single row as a counter for every request, that row can become a hotspot. Consider allocating ID ranges, using appropriate sequences, sharding counters by bucket, or delegating to a dedicated ID generator. Never replace a unique constraint with an application `SELECT` check.

### 11.3. Insert-intention locks and gap locks

When inserting into an index position, InnoDB uses an insert-intention lock to signal intent to insert into the corresponding gap. Transactions inserting at different positions within the same gap can usually proceed concurrently; insert-intention locks are not a mechanism to serialize all inserts inside a gap. However, a gap lock or next-key lock held by another transaction can cause an INSERT to wait.

For example, Session A runs a locking range read under `REPEATABLE READ` on an index interval; Session B inserts a value falling inside the locked gap. B may wait even though the new value does not collide with any existing record. This is contention from range protection, distinct from duplicate-key waits when two transactions insert the same unique value.

## 12. Checking lock waits and deadlocks

### 12.1. Performance Schema

MySQL 8.x provides Performance Schema tables to observe data locks and lock waits:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, INDEX_NAME, THREAD_ID;
```

Inspect relationships between waiting transactions and blocking transactions:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    req.LOCK_DATA AS waiting_lock_data,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

These tables reflect currently held locks; once a wait ends, rows can disappear. Privileges and instrumentation level depend on server configuration.

### 12.2. sys schema and InnoDB status

If the `sys` schema is available, the following view offers a more readable view of lock waits:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

Details of the latest deadlock:

```sql
SHOW ENGINE INNODB STATUS;
```

Read the `LATEST DETECTED DEADLOCK` section to find:

- Which transaction was the victim.
- Which statements were running.
- Involved indexes/tables and lock modes.
- Lock acquisition order of each transaction.
- Which transaction held locks and which was waiting.

The deadlock log only describes the most recent deadlock stored at query time. For systems experiencing frequent deadlocks, enable/collect appropriate logs and analyze frequency rather than relying on a single snapshot.

### 12.3. Distinguishing row locks from metadata locks and latches

- `performance_schema.data_locks` and `data_lock_waits` observe InnoDB data locks.
- `performance_schema.metadata_locks` helps investigate metadata locks, usually tied to DDL and active table-using transactions.
- Latch/page contention is internal InnoDB synchronization; it does not necessarily appear as a waiting row lock. Inspect wait instrumentation, mutexes/rwlocks, and appropriate performance metrics.

You can inspect metadata locks on the lab tables with:

```sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME IN ('cc_departments', 'cc_employees')
ORDER BY OBJECT_NAME, LOCK_STATUS, OWNER_THREAD_ID;
```

Do not conclude "FK is causing locks" from a single slow request. Cross-reference threads, transactions, indexes, SQL, and wait timestamps to pinpoint the exact cause.

## 13. EXPLAIN and indexes for FK/UNIQUE

Inspect the query finding child rows before deleting a parent:

```sql
EXPLAIN
SELECT employee_id
FROM cc_employees
WHERE department_id = 10;
```

The query should use an index starting with `department_id`. If you also filter on `status`, a composite index may need a column order matching the workload, such as `(department_id, status)`.

Inspect a query by unique key:

```sql
EXPLAIN
SELECT employee_id
FROM cc_employees
WHERE email = 'an@example.com';
```

A unique index finds at most one row by the full key. With a composite unique index, queries on the leading column can use the leftmost prefix; queries on trailing columns alone do not automatically get the same benefit.

`EXPLAIN` reveals the access path and row estimates, not complete runtime locks. Combine it with `performance_schema.data_locks`, `data_lock_waits`, transaction metadata, and deadlock reports to investigate concurrency.

## 14. Reducing contention while preserving data integrity

### 14.1. Keep transactions short

Never open a transaction and then call HTTP APIs, wait for users, process large files, or perform unrelated tasks. Long transactions hold locks longer and raise conflict probability.

### 14.2. Acquire locks in a consistent order

If a business flow updates parent then child, all code paths should follow that same order. If one flow locks child first then parent while another locks parent first then child, deadlocks can occur.

With multiple parent/child rows, sorting IDs and processing in a consistent order helps reduce wait cycles. This lowers deadlock probability, though it does not guarantee total elimination.

### 14.3. Use appropriate indexes

- Keep indexes on child-side FK columns.
- Use composite indexes whose leftmost prefix matches common predicates.
- Avoid data-type conversions or wrapping columns in functions inside join/filter predicates if they disable index usage.
- Watch for redundant indexes; too many indexes increase the cost of every INSERT/UPDATE/DELETE.

### 14.4. Treat duplicates as valid concurrency outcomes

For username/email registration or idempotency keys, design the application to handle duplicate-key errors intentionally. Never run `SELECT` and assume the value will still be unclaimed at `INSERT` time. The unique index is the atomic arbiter.

### 14.5. Do not remove constraints to treat symptoms

Disabling `foreign_key_checks` or dropping unique indexes can let bad data slip in and make recovery much harder. Only use `SET FOREIGN_KEY_CHECKS = 0` in controlled import/migration workflows with subsequent data validation. Re-enabling `FOREIGN_KEY_CHECKS` does not automatically scan and re-validate data loaded while checks were disabled.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking FKs only in application code | Two concurrent requests can create orphan references | Enforce FKs in the database and handle constraint errors |
| Using SELECT before INSERT to guarantee uniqueness | Race condition between two requests | Create a UNIQUE index and handle duplicate-key errors |
| Not checking for orphans before adding an FK | Migration fails when validating existing data | Run an anti-join and fix data in a controlled manner |
| Not checking for duplicates before adding UNIQUE | Migration fails or requires urgent data cleanup | Run GROUP BY/HAVING using the exact collation and composite key |
| Thinking UNIQUE allows only one NULL | Second NULL insert fails contrary to assumptions | Remember MySQL allows multiple NULLs in a unique index |
| Using nonstandard parent keys or mismatched index order | FK fails to create or depends on nonstandard behavior | Prefer PK/UNIQUE and exact column ordering |
| Dropping child-side indexes | Increases cost of checking/finding child rows and impacts locking | Create an appropriate index on the FK |
| Assuming child inserts on the same parent are always serialized | Misdiagnosing hotspots | Distinguish shared FK-check locks from parent delete/update or unique-key conflicts |
| Using CASCADE on high fan-out relationships without measuring | Single operation creates massive locks and long transactions | Estimate fan-out, verify indexes, and measure load |
| Using INSERT IGNORE to swallow all errors | Masks invalid data and warnings | Inspect warnings/affected rows; use only when semantics are clear |
| Using REPLACE as an UPDATE | Can delete+insert, firing cascades/triggers | Use UPDATE or an upsert with proper semantics |
| Looking only at EXPLAIN to infer locks | Misses full runtime lock behavior | Combine Performance Schema and InnoDB status |

## 16. Practice exercises

1. Create the lab schema from section 2. Run `SHOW CREATE TABLE` and query `INFORMATION_SCHEMA` to list FKs, UNIQUEs, and indexes.
2. Try inserting an employee with `department_id = 999`. Record the FK error; try `department_id = NULL` and explain why it is valid.
3. Create a temporary child table without an FK, insert an orphan reference, and run an anti-join to detect the bad data before adding the constraint.
4. Create email data that collides under the current collation. Run `GROUP BY/HAVING`, then try adding a unique index in a separate lab table.
5. Test a nullable unique index with multiple NULL rows. Alter the column to NOT NULL and observe the difference.
6. Open two sessions; have A insert an employee referencing department 10 without committing, and have B delete department 10. Observe the lock wait and the error after A commits.
7. Open two sessions and both insert the same unique email. Test A committing so B rolls back/gets a duplicate error; then repeat with A rolling back so B succeeds.
8. Test `ON DELETE CASCADE` on a lab table with many child rows. Measure duration, observe locks, and check affected row counts.
9. Query `performance_schema.data_locks` and `data_lock_waits` while one session is waiting. Cross-reference with `SHOW ENGINE INNODB STATUS`.
10. Run `EXPLAIN` on queries finding child rows by FK and queries by email. Compare with and without indexes in a test schema.
11. Redesign a parent/child update flow so all code paths acquire locks in the same order; explain how deadlock risk is reduced.

## 17. Pre-production checklist for FK/UNIQUE

- [ ] Confirmed participating tables use the InnoDB engine.
- [ ] Verified actual constraint definitions via `SHOW CREATE TABLE`/`INFORMATION_SCHEMA`.
- [ ] FK columns match data type, signedness, charset/collation, and column order.
- [ ] Parent key is a standard PK/UNIQUE; no reliance on nonstandard referenced keys.
- [ ] Child FK has an index aligned with the relationship and workload.
- [ ] Zero orphan references exist prior to adding FKs.
- [ ] Zero duplicates exist under the unique index's exact collation and semantics.
- [ ] Explicitly decided whether NULL is permitted in FK/UNIQUE columns.
- [ ] `ON DELETE`/`ON UPDATE` match business rules and fan-out has been estimated.
- [ ] Application handles duplicate-key and foreign key violations as expected concurrency outcomes.
- [ ] Transactions are short, lock ordering is consistent, and deadlock retries are bounded.
- [ ] Inspected access paths with `EXPLAIN` and runtime locks with Performance Schema as needed.
- [ ] Migration plans account for metadata locks, index build time, and rollback/recovery.
- [ ] Constraint checks are never disabled without a post-import data verification procedure.

## 18. Completion criteria

You have completed this lesson when you can read FK/UNIQUE definitions from a live schema, detect orphans and duplicates prior to migration, explain index/data-type requirements, reproduce contention between a child insert and a parent delete as well as two inserts on the same unique key, distinguish shared FK-check locks from unique/record/gap lock conflicts, and locate waiting transactions and hotspots using Performance Schema or InnoDB status. You should also be able to propose ways to reduce contention without sacrificing data invariants.

## References

- [MySQL 8.4 Reference Manual — InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html)
- [MySQL 8.4 Reference Manual — InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual — InnoDB Lock and Lock-Wait Information](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-understanding-innodb-locking.html)
- [MySQL 8.4 Reference Manual — The INFORMATION_SCHEMA STATISTICS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-statistics-table.html)
- [MySQL 8.4 Reference Manual — Performance Schema data_locks Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-locks-table.html)
