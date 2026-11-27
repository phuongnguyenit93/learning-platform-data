# Distinguishing DELETE, TRUNCATE, DROP, and PURGE in Oracle Database

When cleaning up Oracle data, the four keywords **`DELETE`, `TRUNCATE`, `DROP`, and `PURGE`** are often mentioned together because all four make data disappear from everyday queries. Yet they operate at **completely different levels**: individual rows, entire table contents, table object definitions, and the database recycle bin. Choosing the wrong command can cause unrecoverable data loss (`ROLLBACK` impossible), implicitly commit another transaction, break dependent objects, or wipe out recycle-bin recovery.

In Oracle's **Tables and Constraints** chapter, you must understand not just syntax, but also **transactions**, **constraints**, **triggers**, **redo/undo**, **tablespace and storage**, and post-operation recoverability. This lesson covers each command, compares them across real scenarios, and provides safe hands-on exercises on `LAB_`-prefixed tables.

> **Scope Warning:** `TRUNCATE`, `DROP`, and `PURGE` examples here should only be tested on **lab tables you control**. They can have effects that cannot be undone with `ROLLBACK`. Never run them on critical tables or production environments just to observe behavior.

## 1. At a Glance: What Do the Four Commands Do?

| Command | Impact Level | Category | Supports `WHERE`? | Standard `ROLLBACK`? | Does Table Still Exist? |
|---|---|---|---|---|---|
| **`DELETE`** | Matching **rows**, or all rows if omitted | **DML** | **Yes** | **Yes, if transaction not committed** | **Yes** |
| **`TRUNCATE TABLE`** | **All rows** of a table (or a partition via partition syntax) | **DDL** | **No** | **No** | **Yes**, structure remains |
| **`DROP TABLE`** | The **table object** and components in drop scope | **DDL** | **No** | **No** | **No** in the normal active namespace |
| **`PURGE`** | **Dropped objects in the recycle bin**, or skips the recycle bin via `DROP ... PURGE` | Recycle bin / DDL management command | **No** | **No** | Dropped object loses `FLASHBACK ... TO BEFORE DROP` via recycle bin |

Short examples:

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED';

TRUNCATE TABLE lab_orders;

DROP TABLE lab_orders;

DROP TABLE lab_orders PURGE;
~~~

These are **independent options**, not four commands meant to run sequentially on the same table. After `DROP TABLE`, the table name is no longer queryable; after `DROP ... PURGE`, the object bypasses the recycle bin and cannot be recovered via `FLASHBACK TABLE ... TO BEFORE DROP`.

A mental model:

~~~text
DELETE   ── remove selected ROWS (or all rows)
                │   keeps table/schema object
                │   transactional, supports ROLLBACK before COMMIT
                ▼
TRUNCATE ── EMPTY entire table
                │   keeps table definition
                │   DDL, implicit COMMIT, no ROLLBACK
                ▼
DROP     ── remove table OBJECT from active schema
                │   may place object into recycle bin
                ▼
PURGE    ── remove object recoverability from RECYCLE BIN
                    not a command for deleting live rows
~~~

## 2. Distinguish DML and DDL Before Acting

**DML (Data Manipulation Language)** manipulates data inside tables: `INSERT`, `UPDATE`, `DELETE`, `MERGE`. DML runs inside a **transaction**; you can `COMMIT` to persist or `ROLLBACK` to undo uncommitted changes.

**DDL (Data Definition Language)** alters object definitions/structures and database management metadata: `CREATE`, `ALTER`, `TRUNCATE`, `DROP`, etc. In Oracle, DDL normally performs an **implicit commit** before executing, and commits the DDL result upon success. Thus `TRUNCATE` and `DROP` can never be treated as rollbackable steps inside a DML transaction.

A classic accidental data-loss trap:

~~~sql
UPDATE lab_customer
SET display_name = 'New name'
WHERE customer_id = 10;

-- Not manually COMMITted yet.
TRUNCATE TABLE lab_temp_data;

ROLLBACK;
~~~

A beginner may think `ROLLBACK` reverts `LAB_CUSTOMER` to the old name and restores `LAB_TEMP_DATA`. **Wrong:** `TRUNCATE` is DDL, so Oracle implicitly commits the pending transaction **before** running the DDL. Thus the `LAB_CUSTOMER` update is committed, and the truncated data never comes back on rollback. Even if the DDL itself fails afterward, the earlier DML may already have been committed by the pre-DDL implicit commit.

**Safe habit:** Explicitly commit or roll back important DML transactions **before** running any DDL. Use a dedicated administrative connection for schema work where appropriate; never slip "cleanup" DDL into a Java business transaction expecting rollback to protect everything.

## 3. DELETE: Conditional Row Deletion Within a Transaction

`DELETE` is the right choice when removing **a subset of data** or when deletion must obey normal constraints and transaction boundaries.

### 3.1. Conditional Deletion

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED'
  AND created_at < DATE '2025-01-01';
~~~

Oracle deletes rows matching the predicate. Without `WHERE`:

~~~sql
DELETE FROM lab_orders;
~~~

This deletes **all rows**, yet remains DML: Oracle still performs row-level deletion, generates undo and redo, and checks constraints and triggers. It is **not the same** as `TRUNCATE TABLE` even though `COUNT(*)` afterward returns 0 in both cases.

### 3.2. DELETE Can Be Rolled Back

~~~sql
DELETE FROM lab_orders
WHERE order_id = 101;

-- Inspect row count before deciding.
SELECT COUNT(*)
FROM lab_orders
WHERE order_id = 101;

ROLLBACK;
~~~

As long as `DELETE` and `ROLLBACK` occur in the same uncommitted transaction, the deleted row is restored. Keep in mind:

- If `COMMIT` already ran or the client uses **auto-commit**, `ROLLBACK` cannot undo committed deletes.
- If a DDL statement ran in between, its implicit commit ended the transaction before `ROLLBACK`.
- If multiple DML statements ran in the same transaction, a full `ROLLBACK` undoes **all uncommitted changes** since the transaction began (unless using savepoints), not only the last delete.

For multi-step safety, use a savepoint:

~~~sql
SAVEPOINT before_cleanup;

DELETE FROM lab_orders
WHERE order_status = 'CANCELLED';

-- If inspection shows something is off:
ROLLBACK TO before_cleanup;
~~~

Savepoints apply to DML transactions; **you cannot set a savepoint and use it to undo TRUNCATE or DROP**.

### 3.3. DELETE Fires Triggers and Enforces Constraints

Oracle supports DML triggers on `DELETE`:

- **Statement-level triggers** firing once per DELETE statement.
- **Row-level triggers** (`FOR EACH ROW`) firing per affected row.

Conceptual example:

~~~sql
CREATE TABLE lab_delete_audit (
  audit_id    NUMBER GENERATED ALWAYS AS IDENTITY,
  deleted_id  NUMBER NOT NULL,
  deleted_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_lab_delete_audit PRIMARY KEY (audit_id)
);

CREATE OR REPLACE TRIGGER trg_lab_orders_delete
AFTER DELETE ON lab_orders
FOR EACH ROW
BEGIN
  INSERT INTO lab_delete_audit(deleted_id)
  VALUES (:OLD.order_id);
END;
/
~~~

This is an illustrative trigger; `LAB_ORDERS` and `ORDER_ID` must exist, and trigger creation privileges are required. If the transaction executes `ROLLBACK`, standard DML audit rows written by the trigger **in the same transaction** also roll back (unless using an autonomous transaction, which has different semantics). This trigger **is not fired by `TRUNCATE TABLE`** because truncate is not row-by-row DML deletion.

A statement-level `DELETE` trigger fires even if the DELETE affects zero rows, whereas a row-level trigger fires only for actually affected rows. Never build business logic assuming every table-emptying command fires DELETE triggers.

### 3.4. DELETE and Foreign Keys

Suppose:

~~~text
LAB_PARENT
   ID (PK)
      |
      | 1
      | N
      v
LAB_CHILD
   PARENT_ID (FK)
~~~

Deleting a parent still referenced by children is blocked when an active FK lacks a cascading/nullifying clause:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
-- Typically raises ORA-02292 when child rows still reference the parent.
~~~

Depending on DDL, a foreign key may use `ON DELETE CASCADE` to delete children with the parent, or `ON DELETE SET NULL` when the child column is nullable and business rules permit. Never enable cascade merely for cleanup convenience if child rows hold audit history that must survive.

## 4. TRUNCATE: Emptying a Table, Keeping Its Definition, No Rollback

`TRUNCATE TABLE` removes all rows from a table **without taking the row-by-row DELETE path**. In Oracle, this is **DDL**.

~~~sql
TRUNCATE TABLE lab_orders;
~~~

What remains after truncate (on standard tables):

- **The table object and column definitions** remain.
- **Constraints, triggers, privileges, and indexes** remain attached to the table per Oracle rules; index contents are reset to match an empty table.
- New rows can be `INSERT`ed into the table afterward.

What is gone is **all table row data as of truncate time**. There is no `WHERE` clause to truncate only cancelled orders or rows before a cutoff date; selective deletion requires `DELETE` or partition maintenance.

### 4.1. Why Is TRUNCATE Usually Faster Than Deleting All Rows?

`DELETE FROM table` processes individual rows, generating undo for rollback, redo, and firing constraints/triggers per DML rules. On very large tables, that work is expensive.

`TRUNCATE` mainly updates metadata/segment structures to discard data structurally; it generates **far less undo for row removal** and can be dramatically faster for emptying a whole table. However:

- It does not mean "zero redo/undo"; metadata and segment updates still carry cost.
- Truncate may still wait on active locks/transactions and must obey constraint checks.
- Truncate does not fire row-level DELETE triggers.
- Truncate cannot be rolled back like DELETE.

Never pick TRUNCATE for speed alone when business rules require history retention, audit triggers, or rollback capability.

### 4.2. High Water Mark (HWM) and Storage

The **High Water Mark** tracks the boundary of segment blocks used/allocated under Oracle storage management. `DELETE` removes rows yet usually **does not lower the table's HWM**; allocated blocks remain part of the segment and can be reused by future inserts.

`TRUNCATE` generally **resets the HWM** and can release extents depending on storage options:

~~~sql
TRUNCATE TABLE lab_orders DROP STORAGE;

TRUNCATE TABLE lab_orders REUSE STORAGE;
~~~

| Option | Practical Meaning |
|---|---|
| **`DROP STORAGE`** | Oracle releases extents that can be reclaimed per segment rules; the standard default for table truncate |
| **`REUSE STORAGE`** | Retains allocated extents so subsequent loads can reuse them, useful for frequently reloaded staging tables |

"Releasing extents" **does not mean** the tablespace's OS datafile shrinks automatically; datafile sizing and physical disk reclamation are separate administrative tasks. Also, do not judge `SELECT` performance solely by seeing `COUNT(*) = 0` after truncate; execution plans and storage state still matter.

### 4.3. TRUNCATE and Foreign Keys: Do Not Confuse with DELETE CASCADE

When a parent table is referenced by an **enabled foreign key** on another table, Oracle generally **forbids truncating the parent** when referential preconditions are unmet—even if you believe the child table is currently empty. Exact rules depend on objects and version, yet the rule to remember is that **TRUNCATE does not replace DELETE and does not perform row-by-row checks**.

In many lab setups, you must truncate **children before parents**:

~~~sql
TRUNCATE TABLE lab_child;
TRUNCATE TABLE lab_parent;
~~~

Even so, emptying the child table **does not disable the enabled foreign key** pointing to the parent, so the second statement can still be rejected by Oracle. When FKs exist, choose an appropriate strategy:

- Use `DELETE` in child → parent order when transactions or auditing are needed.
- Consider `TRUNCATE ... CASCADE` **where Oracle version and foreign key definitions permit it**; never assume every FK supports cascading truncate.
- In DBA-approved workflows, handle constraints or partitions explicitly with verification and recovery plans—never automatically disable all FKs in production.

In order/product schemas, truncating a parent often fails even when merely trying to "reset test data." Use isolated staging/lab tables when frequent truncation is needed.

### 4.4. TRUNCATE CASCADE Is Not DROP CASCADE CONSTRAINTS

On Oracle versions supporting `TRUNCATE TABLE ... CASCADE` under qualifying conditions (specifically relationships configured with `ON DELETE CASCADE`), it truncates data across related tables. Never apply it blindly: its blast radius spans multiple tables and must be verified on your exact release and configuration.

~~~sql
-- Syntax example only for supporting FK designs and versions;
-- never run on data you need to keep.
TRUNCATE TABLE lab_parent CASCADE;
~~~

By contrast, `DROP TABLE ... CASCADE CONSTRAINTS` **drops the referential constraints** needed to drop the parent table—it **does not drop the child tables**. These two cascades are fundamentally different and are covered separately under DROP.

## 5. DROP: Removing a Table Definition from the Schema

Running:

~~~sql
DROP TABLE lab_orders;
~~~

removes the table from the active schema namespace. This differs from `TRUNCATE`:

- `TRUNCATE` keeps the table object and column schema.
- `DROP` makes the table name unavailable to normal queries; `SELECT * FROM lab_orders` raises `ORA-00942`.
- Dependent objects (views, procedures, materialized views, triggers, constraints, indexes, etc.) may be dropped, invalidated, or impacted per Oracle object rules.
- `DROP` is **DDL**: it cannot be undone with `ROLLBACK` like `DELETE`.

### 5.1. DROP and the Recycle Bin

When the **recycle bin** is enabled and the object qualifies, `DROP TABLE` moves the table and dependent structures into the recycle bin rather than freeing storage immediately. Recycle-bin names look like system-generated `BIN$...` identifiers so Oracle can distinguish multiple drops of the same table name.

~~~text
Before DROP
  LAB_ORDERS  ── normal usable table
       |
       | DROP TABLE LAB_ORDERS
       v
After DROP (when recycle bin applies)
  LAB_ORDERS name is no longer normally queryable
       |
       v
  Recycle bin: BIN$...   ── eligible for flashback before drop
       |
       | PURGE / DROP ... PURGE
       v
  No recycle-bin flashback recovery path remains
~~~

Whether an object enters the recycle bin depends on `RECYCLEBIN` configuration, object type, tablespace, privileges, and exceptions. Not every `DROP` is recoverable from the recycle bin. In particular, `DROP TABLE ... PURGE` **bypasses the recycle bin** from the start.

### 5.2. DROP TABLE ... PURGE

~~~sql
DROP TABLE lab_orders PURGE;
~~~

This **drops the table and purges it immediately**, skipping the recycle bin. It is stronger than a plain `DROP TABLE` when the recycle bin is active. Afterward, `FLASHBACK TABLE lab_orders TO BEFORE DROP` cannot recover that drop from the recycle bin.

Do not equate "not in recycle bin" with "impossible to recover by any means": DBAs may still have RMAN backups, storage snapshots, or other recovery options. Those require formal DBA recovery procedures, privileges, and prerequisites—not a quick `ROLLBACK` or `FLASHBACK ... TO BEFORE DROP`.

### 5.3. DROP with Foreign Keys from Other Tables

If a child table has an FK pointing to a parent table:

~~~sql
DROP TABLE lab_parent;
~~~

is rejected by Oracle because an active referential constraint references the parent's key. When deliberately **removing the parent table**, Oracle offers:

~~~sql
DROP TABLE lab_parent CASCADE CONSTRAINTS;
~~~

`CASCADE CONSTRAINTS` lets Oracle **drop the dependent foreign key constraints** on other tables. It **does not mean `DROP TABLE lab_child`**, nor does it delete child rows. Afterward, the child table remains, yet its foreign key protection to the parent is gone—understand the integrity impact clearly.

If you do not intend to sever relationships, **never** add cascade out of habit. Re-check your goal: are you trying to delete test rows, empty a table, or truly remove an entity from the schema?

### 5.4. DROP and Other Dependent Objects

A table feeds many components:

~~~text
TABLE
 ├── PRIMARY KEY / UNIQUE / CHECK / FOREIGN KEY on the table
 ├── INDEXES / TRIGGERS
 ├── Referencing VIEWS and PL/SQL units
 ├── SYNONYMS
 └── JDBC / JPA apps / reports / ETL
~~~

Dropping a table drops or moves directly attached structures to the recycle bin depending on type; referencing views, PL/SQL units, and external consumers **are not deleted automatically**, yet become invalid and fail at runtime. A synonym pointing to a table name does not guarantee the table still exists. Recreating the schema after `DROP` requires restoring DDL, constraints, grants, indexes, comments, data, and dependencies—not just a bare `CREATE TABLE`.

## 6. PURGE: Emptying the Recycle Bin, Not Deleting Rows

**PURGE** operates on **already-dropped objects** sitting in the recycle bin, or as a drop modifier bypassing the bin. It is not a command to "purge rows with status CANCELLED" from a live table.

Common forms:

~~~sql
-- Drop and bypass the recycle bin at once:
DROP TABLE lab_old_data PURGE;

-- View objects in the current user's recycle bin:
SELECT object_name, original_name, type, droptime
FROM user_recyclebin
ORDER BY droptime DESC;

-- Purge one dropped table using its exact BIN$ name from the dictionary:
PURGE TABLE "BIN$...$...";

-- Purge all objects in the current user's recycle bin:
PURGE RECYCLEBIN;
~~~

The string `"BIN$...$..."` above is an **illustrative placeholder**, not literal SQL to run. Recycle-bin names often contain special characters, so double quotes are normally needed in `PURGE TABLE` with `BIN$...` names. Query `USER_RECYCLEBIN`, copy the **exact `OBJECT_NAME`**, and purge only objects confirmed unneeded.

### 6.1. Difference Between PURGE TABLE and PURGE RECYCLEBIN

| Statement | Scope |
|---|---|
| `PURGE TABLE "BIN$..."` | Targets a single dropped table in the recycle bin by exact name |
| `PURGE RECYCLEBIN` | Purges objects in the **current user's** recycle bin per Oracle rules |
| `PURGE DBA_RECYCLEBIN` | Broader administrative scope, requires corresponding privileges |
| `DROP TABLE x PURGE` | Drops table `x` without placing it in the recycle bin |

**Risk:** `PURGE RECYCLEBIN` can wipe **many other dropped tables**, not just the one from your current test. Never use it as a "quick cleanup" in shared schemas. In labs, practice purging **one specific `BIN$` table** after inspecting the list.

### 6.2. Does PURGE Shrink Datafiles?

Purging frees segment space formerly held in the recycle bin so Oracle can reuse it within the tablespace. However, **this does not automatically shrink OS datafiles on disk**. Datafile growth, HWM, space reclamation, and backup retention are separate management layers.

### 6.3. PURGE and Recoverability

Once an object is purged from the recycle bin, `FLASHBACK TABLE ... TO BEFORE DROP` can no longer restore it. Recovery then depends on backups and full DBA recovery workflows—not an instant undo button.

## 7. Data Recovery: How DELETE Differs from DROP

Different recovery tools match **different incidents**:

| Scenario | Possible Recovery | Key Conditions |
|---|---|---|
| `DELETE` just ran, uncommitted | `ROLLBACK` or `ROLLBACK TO SAVEPOINT` | Must still be in the uncommitted transaction |
| `DELETE` already committed | Flashback Query/Table or backup restore, sometimes `INSERT ... SELECT AS OF` | Depends on undo retention, privileges, row movement/workflow, target timestamp |
| `TRUNCATE` already ran | Backup/restore per Oracle procedures | Standard `ROLLBACK` impossible; recycle bin does not hold truncated rows |
| `DROP TABLE` with recycle bin active | `FLASHBACK TABLE ... TO BEFORE DROP` | Object still in recycle bin and recovery conditions satisfied |
| `DROP TABLE ... PURGE` or already `PURGE`d | Backup/RMAN/other recovery if available | No `TO BEFORE DROP` path via recycle bin |

### 7.1. FLASHBACK TABLE ... TO BEFORE DROP

If the table entered the recycle bin and has not been purged, you can try:

~~~sql
FLASHBACK TABLE lab_orders TO BEFORE DROP;
~~~

If `LAB_ORDERS` was already reused by a new table, recovery must resolve the name collision; Oracle supports `RENAME TO` during flashback before drop when appropriate:

~~~sql
FLASHBACK TABLE lab_orders
  TO BEFORE DROP RENAME TO lab_orders_restored;
~~~

**Flashback before drop does not restore the entire surrounding environment.** Related objects such as incoming foreign keys from other tables, certain grants, dependencies, or constraint/index names may not revert identically and must be inspected afterward against DDL/migrations.

### 7.2. Flashback Query After DELETE

After a `DELETE` has been committed, Oracle may allow querying prior table state via **Flashback Query** if sufficient undo remains and privileges permit:

~~~sql
-- Illustration: query an earlier table version,
-- provided the timestamp falls within Flashback Query retention.
SELECT *
FROM lab_orders AS OF TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '10' MINUTE);
~~~

Its primary purpose is **investigating** prior state before deciding how to recover. Oracle does not guarantee 10 minutes or more of undo retention under every workload. To restore rows, design controlled insert/merge scripts checking primary keys, FKs, transactions, and subsequent writes. **Never** treat Flashback Query as a replacement for long-term backups.

### 7.3. TRUNCATE Does Not Send Data to the Recycle Bin

A frequent misconception: **the recycle bin holds dropped objects**, not row versions removed by truncate. Therefore, after `TRUNCATE TABLE`, `FLASHBACK TABLE ... TO BEFORE DROP` does not apply because the table **was never dropped**. Recovering pre-truncate data requires prepared backup/restore procedures.

## 8. Detailed Behavior Comparison in Oracle

| Question | DELETE | TRUNCATE | DROP | PURGE |
|---|---|---|---|---|
| Target | Data rows | All table contents | Table object | Dropped object in recycle bin |
| DML or DDL? | DML | DDL | DDL | Recycle bin / DDL management |
| Supports `WHERE`? | Yes | No | No | No |
| Can remove a few rows? | Yes | No | No | No |
| Standard rollback possible? | Yes, before commit | No | No | No |
| Implicit commit? | Not from DELETE itself | Yes | Yes | Yes, per DDL operation semantics |
| Fires DELETE row triggers? | Yes, for affected rows | No | No | No |
| Row-delete FK checks? | Yes | Blocked by enabled FKs; not row deletion | Blocked/affects dependent constraints | Object already dropped |
| Index/table structure retained? | Yes | Yes | Unavailable normally after drop | Cannot flashback from recycle bin after purge |
| Table HWM reset? | Usually no | Usually yes | Object dropped | Reclaims dropped object space |
| Shrinks OS files immediately? | Not automatically | May release extents, does not shrink datafiles | Depends on recycle bin/storage | Frees extents; does not shrink datafiles |
| Involves recycle bin? | No | No | Possibly | Directly operates on it |
| Best suited for | Selective/audited/transactional deletion | Emptying permitted temp/staging tables | Retiring a table from the schema | Cleaning dropped objects when flashback is definitely unneeded |

Entries in this table reflect **general behavior for standard Oracle heap tables**. Temporary tables, partitioned tables, domain indexes, clusters, materialized views, and specialized features carry their own rules and syntax. Never extrapolate every variant blindly from this summary alone.

## 9. Controlled Hands-On Lab on an Independent Table

The steps below use a **new table `LAB_CLEANUP_DEMO`** with no FKs so business tables remain untouched. Use a dedicated schema in a practice PDB with `CREATE TABLE` privilege and quota. If a table with this name already exists, **do not overwrite or drop it**; pick a unique lab table name.

### Step 1 — Create Table and Seed Rows

~~~sql
CREATE TABLE lab_cleanup_demo (
  record_id NUMBER NOT NULL,
  description VARCHAR2(100 CHAR) NOT NULL,
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_lab_cleanup_demo PRIMARY KEY (record_id)
);

INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (1, 'Data row A');
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (2, 'Data row B');
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (3, 'Data row C');

COMMIT;

SELECT record_id, description
FROM lab_cleanup_demo
ORDER BY record_id;
~~~

Initially, three rows exist with `RECORD_ID` values `1, 2, 3`.

### Step 2 — DELETE Then ROLLBACK

~~~sql
DELETE FROM lab_cleanup_demo
WHERE record_id = 2;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- In this session: 2 rows.

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- After rollback: 3 rows.
~~~

In another session, visibility of uncommitted changes depends on isolation and snapshots. Under standard `READ COMMITTED`, another session does not see your **uncommitted** DELETE until you commit.

### Step 3 — DELETE Then COMMIT

~~~sql
DELETE FROM lab_cleanup_demo
WHERE record_id = 2;

COMMIT;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- 2 rows.

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- Still 2 rows: commit ended the transaction.
~~~

In real operations, this is why you verify `WHERE` predicates and affected row counts before committing. Never assume an undo is possible when using a framework with auto-commit enabled.

### Step 4 — Repopulate Data to Test TRUNCATE

~~~sql
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (2, 'Recreated data row B');

COMMIT;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- Back to 3 rows.
~~~

### Step 5 — TRUNCATE Then Attempt ROLLBACK

~~~sql
TRUNCATE TABLE lab_cleanup_demo REUSE STORAGE;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- 0 rows.

ROLLBACK;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- Still 0 rows.
~~~

`REUSE STORAGE` retains allocated extents for subsequent inserts; it does not make truncate rollbackable.

### Step 6 — Reinsert Data, DROP, and Observe the Recycle Bin

~~~sql
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (10, 'Data before DROP');
COMMIT;

-- Check session recycle bin setting:
SHOW PARAMETER recyclebin

-- When permitted and appropriate in lab:
-- ALTER SESSION SET recyclebin = ON;

DROP TABLE lab_cleanup_demo;

SELECT object_name, original_name, type, droptime
FROM user_recyclebin
WHERE original_name = 'LAB_CLEANUP_DEMO'
ORDER BY droptime DESC;
~~~

`SHOW PARAMETER` is a SQL*Plus/SQLcl command, not standard SQL. If the recycle bin is enabled and the table qualifies, an object named `BIN$...` appears; if absent, check configuration/exceptions rather than assuming the query dropped your data.

If flashback is available in your lab, after `DROP` try:

~~~sql
FLASHBACK TABLE lab_cleanup_demo TO BEFORE DROP;

SELECT COUNT(*)
FROM lab_cleanup_demo;
-- The row inserted before DROP should reappear.
~~~

Whether recovery succeeds depends on recycle bin state, privileges, and object eligibility. When successful, the table returns from the recycle bin—**this demonstrates recycle-bin flashback, not `ROLLBACK`**.

### Step 7 — Test DROP ... PURGE on a Disposable Lab Table

If flashback succeeded and you are sure the data is no longer needed:

~~~sql
DROP TABLE lab_cleanup_demo PURGE;
~~~

Afterward, `FLASHBACK ... TO BEFORE DROP` can no longer recover that drop. If flashback did not succeed in Step 6, **do not** blindly add drop commands on existing names without checking object/owner; skip this step.

### Step 8 — PURGE a Specific Dropped Object

To practice `PURGE TABLE`, create a **distinct** lab table and drop it normally with recycle bin enabled:

~~~sql
CREATE TABLE lab_purge_demo (id NUMBER);
INSERT INTO lab_purge_demo VALUES (1);
COMMIT;

DROP TABLE lab_purge_demo;

SELECT object_name, original_name, type
FROM user_recyclebin
WHERE original_name = 'LAB_PURGE_DEMO';
~~~

When the query returns a row with `OBJECT_NAME` like `BIN$...`, copy that **exact name** and run:

~~~sql
-- Replace the placeholder with the exact OBJECT_NAME from the query result:
PURGE TABLE "BIN$...actual_name...";
~~~

Re-query `USER_RECYCLEBIN` to verify the purged object is no longer available for flashback before drop. Never run `PURGE RECYCLEBIN` in a shared schema just to clean up this single lab exercise.

## 10. Practicing with FKs: Why Do DELETE and TRUNCATE Follow Different Rules?

Create two independent lab tables with an FK **without ON DELETE CASCADE**:

~~~sql
CREATE TABLE lab_parent (
  parent_id NUMBER PRIMARY KEY,
  title VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_child (
  child_id NUMBER PRIMARY KEY,
  parent_id NUMBER NOT NULL,
  note_text VARCHAR2(60 CHAR),
  CONSTRAINT fk_lab_child_parent
    FOREIGN KEY (parent_id)
    REFERENCES lab_parent (parent_id)
);

INSERT INTO lab_parent VALUES (1, 'Parent A');
INSERT INTO lab_child VALUES (101, 1, 'Child A');
COMMIT;
~~~

### 10.1. DELETE Parent While Child Exists

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
-- Typically raises ORA-02292: child record found.
~~~

Oracle blocks deleting the parent while referencing children exist. If the business allows deleting both, a transaction can do:

~~~sql
DELETE FROM lab_child
WHERE parent_id = 1;

DELETE FROM lab_parent
WHERE parent_id = 1;

ROLLBACK;
-- Both tables return to their pre-transaction state.
~~~

If you ran `COMMIT` instead of `ROLLBACK`, the deletes would persist. Writing child-then-parent deletes reflects understanding referential integrity.

### 10.2. TRUNCATE Parent Table

~~~sql
-- Lab test: generally disallowed while an enabled FK from another table references it.
TRUNCATE TABLE lab_parent;
~~~

Oracle raises **`ORA-02266`** (unique/primary keys in table referenced by enabled foreign keys). Even after truncating the child first, **the FK remains enabled**, so an empty child table does not automatically allow truncating the parent.

~~~sql
TRUNCATE TABLE lab_child;
-- Succeeds on the child table.

TRUNCATE TABLE lab_parent;
-- Still rejected while FK metadata remains enabled.
~~~

If a system is designed for `TRUNCATE CASCADE`, verify Oracle release and FK definitions carefully. On operational tables with complex FKs, transactional `DELETE` or DBA-designed maintenance workflows are usually safer than disabling constraints.

### 10.3. DROP Parent with CASCADE CONSTRAINTS

~~~sql
-- Only when you genuinely intend to drop lab_parent and dependent FKs.
DROP TABLE lab_parent CASCADE CONSTRAINTS;
~~~

Afterward, `LAB_CHILD` still exists, while `FK_LAB_CHILD_PARENT` is gone because its parent table was dropped. Never confuse `CASCADE CONSTRAINTS` with "drop child tables." Inspect `USER_CONSTRAINTS` and remaining objects rather than assuming child writes are still FK-protected.

## 11. Oracle Data Dictionary: Verify After Every Operation

To verify whether a table still exists, whether constraints remain, or what sits in the recycle bin, query metadata instead of guessing.

### 11.1. Which PDB and Schema Are You In?

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

In a CDB with multiple PDBs, identically named tables in different PDBs **are completely different objects**. Before any `TRUNCATE`, `DROP`, or `PURGE`, verify **PDB/service, user/schema, and exact table name**.

### 11.2. Check Tables Remaining in the Schema

~~~sql
SELECT table_name, tablespace_name, status
FROM user_tables
WHERE table_name IN (
  'LAB_CLEANUP_DEMO', 'LAB_PARENT', 'LAB_CHILD'
)
ORDER BY table_name;
~~~

After `DELETE` or `TRUNCATE`, the table name still appears. After `DROP TABLE`, the original name disappears from active tables. If logged in as another user with privileges, query `ALL_*` views filtered by `OWNER`.

### 11.3. Inspect the Recycle Bin

~~~sql
SELECT
  object_name,
  original_name,
  type,
  droptime,
  can_undrop,
  can_purge
FROM user_recyclebin
WHERE original_name LIKE 'LAB_%'
ORDER BY droptime DESC;
~~~

`ORIGINAL_NAME` shows the pre-drop name; `OBJECT_NAME` is the system recycle-bin name. `CAN_UNDROP` and `CAN_PURGE` report eligibility recorded by Oracle. The recycle bin can hold multiple versions with the same `ORIGINAL_NAME` if a table was dropped multiple times.

### 11.4. Check Foreign Keys Before Deleting or Dropping

~~~sql
SELECT
  child.table_name AS child_table,
  child.constraint_name AS fk_name,
  parent.table_name AS parent_table,
  child.status,
  child.delete_rule
FROM user_constraints child
JOIN user_constraints parent
  ON parent.constraint_name = child.r_constraint_name
 AND parent.owner = child.r_owner
WHERE child.constraint_type = 'R'
  AND parent.table_name = 'LAB_PARENT'
ORDER BY child.table_name, child.constraint_name;
~~~

`DELETE_RULE` shows FK delete behavior (`NO ACTION`, `CASCADE`, `SET NULL`), and `STATUS` shows whether the FK is enabled. Across schemas, check catalog privileges and `OWNER`; never conclude "no FKs exist" simply because your user lacks visibility into another schema's table.

## 12. Scenarios for Choosing the Right Command

### Scenario A — Deleting Cancelled Orders Past Retention Period

Requirement: "Delete only cancelled orders past retention, write audit logs, and allow rollback if row counts look wrong."

**Choose `DELETE ... WHERE`** inside a tightly controlled transaction with FK checks, auditing, and retention predicates. `TRUNCATE` is unsuitable because it wipes the whole table. For critical business data, take backups and follow change approval.

### Scenario B — Nightly Reload of an Expendable Staging Table

Requirement: "Standalone staging table; yesterday's rows are unneeded; prepare an empty table for loading millions of new rows."

**Consider `TRUNCATE TABLE ... REUSE STORAGE`** when no blocking FKs/objects exist, applications have quiesced the table, and DDL implicit commit is acceptable. If staging participates in a larger workflow requiring whole-job rollback, use another approach or partition/batch staging.

### Scenario C — Permanently Retiring an Unused Intermediate Table

Requirement: "Table is no longer part of the new schema version; all dependent applications have been updated."

**Choose `DROP TABLE`** in a reviewed migration. Audit constraints, views, synonyms, Java code, grants, and backups before dropping. If policy allows the recycle bin, omit `PURGE` initially to retain a short recovery window; if policy demands immediate destruction, use `PURGE` deliberately.

### Scenario D — Clearing Dropped Lab Tables to Free Tablespace Space

Requirement: "Schema recycle bin contains many dropped test tables."

**Choose `PURGE TABLE "BIN$..."`** for verified targets, or `PURGE RECYCLEBIN` only when authorized and safe to clear the user's entire bin. `DELETE FROM` and `TRUNCATE` cannot operate on tables no longer in the active namespace.

### Scenario E — Emptying a Parent Table with Many Foreign Keys

Requirement: "Clean up a set of related tables in an integration environment."

Do not pick `TRUNCATE` merely for speed. Map **all dependencies**, understand enabled/disabled FKs, `ON DELETE` rules, auditing, partitions, and rollback needs. For conditional or row-verified cleanup, use `DELETE` in dependency order or a designed workflow. If intentionally resetting an entire test schema, follow dedicated maintenance and backup scripts.

### Scenario F — Removing Personal Data for Privacy Compliance

Requirement: "Erase an individual and related data without destroying required accounting records."

No single SQL command solves this. Classify data, foreign keys, retention laws, transaction histories, replicas, backups, and legal rules. `PURGE` on the recycle bin does not erase live rows in active tables; `TRUNCATE` wipes all unrelated rows. Implement a verified deletion/anonymization workflow.

## 13. Common Errors and Diagnostics

| Error / Symptom | Typical Situation | Explanation / Resolution |
|---|---|---|
| `ORA-02292` | `DELETE` parent with children | Inspect FKs; handle children per business rules or adjust deletion design |
| `ORA-02266` | `TRUNCATE` parent referenced by enabled FK | Structural FK restriction, not merely whether child has rows |
| `ORA-00942` after `DROP` | Querying dropped table or wrong schema/privileges | Check `USER_TABLES`, `USER_RECYCLEBIN`, schema/PDB |
| `ORA-00054` | DDL cannot acquire required lock | Find blocking sessions/transactions and follow operational procedures |
| `ROLLBACK` does not restore after TRUNCATE | `TRUNCATE` is DDL | Needs backup/restore to recover pre-truncate rows |
| Table missing from recycle bin | `DROP ... PURGE`, recycle bin OFF, ineligible object, or already purged | Check configuration and action history; never assume flashback works |
| `FLASHBACK TABLE ... TO BEFORE DROP` fails | Object absent, name collision, or unmet conditions | Query `USER_RECYCLEBIN`; consider `RENAME TO` or DBA restore |
| Datafile does not shrink after PURGE | Reclaiming recycle-bin segments does not shrink OS datafiles | Distinguish free tablespace extents from OS datafile size |
| Full-table DELETE is slow | High row count, undo/redo, triggers, FKs, locks | Evaluate workload; consider batching, partitions, or `TRUNCATE` if acceptable |
| DROP fails due to FK | Parent referenced by another table's FK | Audit dependencies; never add `CASCADE CONSTRAINTS` casually |
| JDBC DELETE cannot roll back | Connection uses auto-commit or already committed | Fix transaction management and boundaries before deleting |

Never memorize error codes in isolation while ignoring **schema, PDB, constraint, and transaction context**. The same error can stem from multiple causes; querying the data dictionary beats guessing.

## 14. DELETE in Java JDBC and Transactions

Java applications frequently delete rows conditionally and verify affected counts. JDBC executes DELETE via `executeUpdate()`, which returns the **affected row count** per statement semantics.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.LocalDate;

// Assumes connection is managed within an application transaction.
connection.setAutoCommit(false);

String sql = """
    DELETE FROM lab_orders
    WHERE order_status = ?
      AND created_at < ?
    """;

try {
    int deleted;
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, "CANCELLED");
        ps.setDate(2, java.sql.Date.valueOf(LocalDate.of(2025, 1, 1)));
        deleted = ps.executeUpdate();
    }

    // Lab safety policy example: abort if more than 1000 rows matched.
    if (deleted > 1000) {
        throw new IllegalStateException(
            "Unexpected delete count: " + deleted);
    }

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
~~~

This assumes `CREATED_AT` has a compatible date type and timezone semantics are well-defined. In real applications, if `CREATED_AT` is `TIMESTAMP WITH TIME ZONE` or stored in UTC, bind the exact timestamp/instant type per contract rather than using `java.sql.Date` and risking date-boundary bugs.

Also note: **a matching affected-row count does not prove all delete logic is safe**. It is merely one sanity check. Critical operations still require auditing, permission checks, FK analysis, staging tests, impact sizing, and recovery readiness.

**Never** mix `TRUNCATE TABLE` or `DROP TABLE` into a JDBC transaction expecting `connection.rollback()` to revert the workflow. Those are DDL statements with Oracle's implicit commit behavior.

## 15. Handling Large Volumes While Preserving Availability

On tables with tens or hundreds of millions of rows, command choice directly affects availability:

### 15.1. Batched DELETE

When cleaning up expired rows:

- Define clear predicates and delete in **controlled batches** to cap lock hold times and undo consumption.
- Log row counts and progress after each batch in a job-tracking table.
- Avoid massive single-transaction deletes that overwhelm undo, redo, locks, and standby apply.
- **Never** rely on `ROWNUM <= n` as a stable business ordering guarantee without a proper batch/key selection strategy.

Example syntax for a small bounded batch:

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED'
  AND created_at < DATE '2025-01-01'
  AND ROWNUM <= 500;

COMMIT;
~~~

This merely **caps row count per DELETE execution**. It does not delete in `ORDER BY` order, and re-evaluates predicates each iteration. For deterministic order or resumability, drive batches by key ranges; note that separate batches under concurrent writes observe different read snapshots.

### 15.2. Partition Maintenance

When data is partitioned by period (e.g., monthly), partition operations can drop old data at the **partition** level instead of row-by-row DELETEs:

~~~sql
-- Syntax illustration; requires a properly partitioned table.
ALTER TABLE lab_orders
  TRUNCATE PARTITION p_2024_01;
~~~

This is DDL, not a rollbackable DELETE. Depending on partition type, global indexes, referential constraints, and configuration, index maintenance options or restrictions apply. Never run on unpartitioned tables, and never run in production without index and backup planning.

### 15.3. Maintenance Windows and Connection Pools

`TRUNCATE` and `DROP` modify structures or data broadly, acquire DDL locks, and affect active sessions. Application connection pools cache prepared statements and hold active transactions; after DDL, cursors/plans invalidate and requests may fail until statements/connections refresh.

During maintenance, verify:

1. Can application write paths be paused and open transactions drained?
2. Which objects, FKs, indexes, views, stored procedures, and jobs does the DDL affect?
3. Must commands execute in a specific order, maintenance window, or migration?
4. Do backups exist and have **restores been tested** in a comparable environment?
5. How will you verify counts, schema, grants, queries, and app connectivity afterward?

## 16. Review Questions and Practice Exercises

### Exercise 1 — Uncommitted DELETE

You run:

~~~sql
DELETE FROM lab_cleanup_demo WHERE record_id = 1;
ROLLBACK;
~~~

**Question:** Assuming no commit or DDL intervened, does row 1 still exist?

**Guidance:** Yes. `DELETE` is DML, and rollback undoes uncommitted changes in the transaction.

### Exercise 2 — DDL Committing Another Transaction

You run:

~~~sql
UPDATE lab_customer SET display_name = 'X' WHERE customer_id = 10;
TRUNCATE TABLE lab_staging;
ROLLBACK;
~~~

**Question:** Does `ROLLBACK` restore both the customer's name and the staging rows?

**Guidance:** No. `TRUNCATE` is DDL and executes an implicit commit beforehand; never treat it as a rollbackable step in a DML transaction.

### Exercise 3 — Two Empty Tables That Are Not Alike

Both `DELETE FROM lab_cleanup_demo; COMMIT;` and `TRUNCATE TABLE lab_cleanup_demo;` leave `COUNT(*) = 0`. Name **at least four differences** that `COUNT(*)` does not reveal.

**Guidance:** DML vs. DDL, pre-commit rollback capability, DELETE triggers, undo/redo volume and segment/HWM handling, implicit commit.

### Exercise 4 — Foreign Key Still Enabled

You truncated `LAB_CHILD`. `LAB_PARENT` still has an enabled FK from `LAB_CHILD` pointing to it. Why does `TRUNCATE LAB_PARENT` still fail?

**Guidance:** Truncate restrictions inspect **enabled FK metadata**, not just how many rows remain in the child table.

### Exercise 5 — DROP and PURGE

You run:

~~~sql
DROP TABLE lab_cleanup_demo;
~~~

**Question:** Can the table be restored via `FLASHBACK TABLE ... TO BEFORE DROP`? Does the answer change for `DROP TABLE lab_cleanup_demo PURGE`?

**Guidance:** A normal drop **can** be recovered when the recycle bin is active and the object remains; `DROP ... PURGE` bypasses the recycle bin, removing that before-drop path.

### Exercise 6 — Difference Between the Two CASCADEs

Why does `DROP TABLE lab_parent CASCADE CONSTRAINTS` differ from `TRUNCATE TABLE lab_parent CASCADE`?

**Guidance:** `DROP ... CASCADE CONSTRAINTS` drops **referential constraints** blocking parent removal without dropping child tables; `TRUNCATE ... CASCADE` empties data across related tables where supported.

### Exercise 7 — Choosing Commands for Three Requests

Propose solutions for:

1. Deleting 200 verified cancelled orders with auditing and rollback on mismatch.
2. Emptying a standalone staging table before loading fresh data.
3. Clearing a dropped object from the recycle bin after an approved retention period.

**Guidance:** (1) `DELETE ... WHERE` in a transaction; (2) `TRUNCATE TABLE` if eligible; (3) `PURGE TABLE` targeting the specific object or an approved scoped purge.

### Exercise 8 — Table Dropped, Yet Disk Still Full

After `DROP TABLE`, `USER_RECYCLEBIN` shows a `BIN$...` entry and the tablespace remains nearly full. Does that make sense?

**Guidance:** Yes. The object remains in the recycle bin for flashback before drop; purging frees segment space inside Oracle's tablespace without automatically shrinking OS datafiles.

## 17. Conclusion: Choose by Goal and Recoverability

~~~text
What do you want to do?
   |
   +── Delete a filtered set of rows?
   |       └── DELETE ... WHERE
   |           DML; manage COMMIT/ROLLBACK; check FKs and triggers
   |
   +── Empty an entire table while keeping its schema?
   |       └── TRUNCATE TABLE
   |           DDL; implicit commit; no ROLLBACK
   |           check FKs, storage, maintenance
   |
   +── Remove a table completely from the database model?
   |       └── DROP TABLE
   |           DDL; may enter recycle bin
   |           check FKs, dependent objects, and migration
   |
   └── Remove dropped objects from the recycle bin?
           └── PURGE TABLE / PURGE RECYCLEBIN
               not for deleting rows in live tables
               removes FLASHBACK TO BEFORE DROP path via recycle bin
~~~

**Key takeaway:** `DELETE` is a **transactional data operation**; `TRUNCATE` is a **DDL table-emptying operation**; `DROP` removes **the table as a schema object**; and `PURGE` clears **dropped objects from the recycle bin or bypasses it on drop**. Whenever asked to "delete," clarify whether you are removing **rows or a table**, whether **`WHERE`, auditing, and rollback** are required, which **foreign keys** exist, whether recovery from **backup/recycle bin** is needed, and whether any active system still depends on the object. The right choice starts from those questions—not from whichever command finishes fastest.
