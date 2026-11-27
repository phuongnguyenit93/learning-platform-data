# Transaction ID, xmin, xmax, and Row Version States in PostgreSQL

## 1. From One Data Row to Multiple MVCC Versions

Suppose a document management application has a row:

~~~text
doc_id = 1
title  = "Draft"
status = "draft"
~~~

Employee A starts editing it to `title = 'Approved'` but **has not COMMITted yet**. At the same time, employee B opens the document viewing screen. Should B see A's uncommitted content? If B is running a long report, should B suddenly see part of A's new results halfway through the calculations?

PostgreSQL uses **MVCC — Multi-Version Concurrency Control**, a mechanism for managing **multiple versions of a row**. Rather than modifying a single value in place and forcing everyone to view the same copy, PostgreSQL can retain different tuple versions so each transaction sees the version matching its **snapshot**.

When learning MVCC, you will commonly encounter:

- **Transaction ID (XID):** an identifier for a transaction that can be used in the versioning mechanism.
- **`xmin`:** a system field associated with the transaction that **created the tuple version**.
- **`xmax`:** a system field that can record the transaction that **marked the version as ended** or participated in **row locking**; it cannot be interpreted simply as "non-zero means deleted".
- **`ctid`:** the physical location of the tuple version, which changes on updates or table rewrites.
- **Snapshot:** a statement's or transaction's view of which transactions have completed, are in progress, or are not yet visible.
- **VACUUM/FREEZE:** mechanisms for managing old versions and XID age to prevent dead-data accumulation and wraparound.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the role of XID, 32-bit XID, and Full Transaction ID (`xid8`).
2. Query the system columns `xmin`, `xmax`, and `ctid` in a controlled manner.
3. Describe a tuple's lifecycle across `INSERT`, `UPDATE`, `DELETE`, `COMMIT`, and `ROLLBACK`.
4. Distinguish **transaction state** from **tuple visibility under a snapshot**.
5. Understand why `xmax != 0` is **not sufficient** to conclude a row has been deleted.
6. Observe two concurrent read/write sessions under `READ COMMITTED` and `REPEATABLE READ`.
7. Understand the roles of `pg_xact`, tuple header flags, HOT, VACUUM, freezing, and wraparound.
8. Avoid using `xmin`, `xmax`, or `ctid` as business keys or an audit log.
9. Design optimistic locking with a dedicated version column and diagnose long-running transactions.

> **Scope:** this lesson covers PostgreSQL's MVCC mechanism, not directly reading or editing raw data pages. Practice only on a lab database with appropriate permissions; never hold long transactions open or run `VACUUM FULL` in production for experimentation.

---

## 2. Distinguishing Three Important Concepts

In PostgreSQL there are at least three distinct layers of information:

| Layer | Subject | Question Answered |
|---|---|---|
| **Transaction** | XID, in-progress/committed/aborted state | "Has the transaction that created/modified the data finished?" |
| **Tuple version** | `xmin`, `xmax`, flags, `ctid` | "Which transaction created this version, and how has it been marked modified/deleted or locked?" |
| **Snapshot** | XID horizon, active transaction list, isolation | "From the reader's point of view, which version is allowed to appear?" |

A tuple containing `xmin` and `xmax` **does not carry the entire answer to "visible or invisible" on its own**. The same version can be:

- Visible to transaction B yet invisible to transaction C because of **different snapshots**.
- Visible after the creating transaction COMMITs, yet absent from an older snapshot.
- Still physically on disk after being DELETEd, even though normal `SELECT` queries no longer return it.

### 2.1. A Timeline Illustration

~~~text
Time ───────────────────────────────────────────────────────────>

Transaction A: BEGIN ── UPDATE row ───────────── COMMIT
                    |       |                    |
Old version:        |       | still visible        | no longer visible
                    |       | from old snapshot    | in new snapshot
New version:        |  created but not yet       | visible from
                    |  committed, B doesn't see  | eligible snapshot

Transaction B:  SELECT before COMMIT      SELECT after COMMIT
~~~

This is a conceptual model. Exactly which rows are visible depends on isolation level, snapshot timing, and transaction status—not merely whether a COMMIT occurred.

---

## 3. What Is a Transaction ID (XID)?

### 3.1. XID Is Not a PRIMARY KEY

An XID is a **transaction** identifier used in concurrency coordination. It is not:

- A row ID (`doc_id`).
- A user ID.
- A row creation timestamp.
- A commit sequence number usable as business history.
- A stable key for APIs.

A single transaction containing multiple write operations can create/modify **many tuples that all share the same XID** in their `xmin` or `xmax` fields. Conversely, one business row across multiple `UPDATE`s has multiple tuple versions tagged with different XIDs.

### 3.2. Not Every Transaction Immediately Gets a Regular XID

PostgreSQL uses a **virtual transaction ID** mechanism for sessions/transactions and typically does not allocate a permanent XID immediately when performing only simple read operations. An XID is normally assigned when a transaction performs an operation that requires one, such as writing data. Do not assume `BEGIN` always allocates a new XID number right away.

In PostgreSQL versions with modern transaction-ID functions:

~~~sql
BEGIN;

SELECT pg_current_xact_id_if_assigned() AS xid_if_allocated;

-- The next function requests an XID for the transaction if not yet assigned:
SELECT pg_current_xact_id() AS current_xid8;

ROLLBACK;
~~~

On a new transaction that has not needed an XID yet, the first call **can return NULL**. `pg_current_xact_id()` guarantees returning a Full Transaction ID for the transaction and can cause an XID to be allocated when called. Do not call it indiscriminately just to "print a number" in read-only reports.

### 3.3. 32-bit XID and Full Transaction ID

PostgreSQL uses traditional XIDs with a **32-bit** range, so XID numbers theoretically wrap around after many transactions. To determine age ordering safely across wraparound, PostgreSQL uses an **epoch / full transaction ID** mechanism alongside freezing/wraparound handling.

Some types and representations:

| Concept | Type/Representation | Note |
|---|---|---|
| Tuple `xmin`/`xmax` | `xid` (32-bit) | System value in the tuple header |
| `pg_current_xact_id()` | `xid8` | Full Transaction ID with epoch information |
| `backend_xid` in stats | Backend's XID, if assigned | Can be NULL |
| `backend_xmin` | Snapshot horizon held by the backend | Not a row's `xmin` |

**Do not compare strings** `xmin::text` and `pg_current_xact_id()::text` to determine "equality" in all circumstances. They use different representations/types, and there are also wraparound, transaction states, and PostgreSQL version differences.

### 3.4. XID Is Not a Clock

Having two transactions with different XIDs is not enough to deduce:

- Which transaction **COMMITted first**.
- Which transaction had an earlier business timestamp.
- Which transaction belonged to the same request.

XIDs are generally assigned sequentially as needed, but assignment order **does not equal COMMIT order**. Transaction A may be assigned an XID first, run longer, and commit **after** transaction B.

If you want to store audit timestamps, use an explicit column like `created_at TIMESTAMPTZ` plus business context—do not infer it from XIDs.

### 3.5. pg_current_snapshot

~~~sql
SELECT
    pg_current_snapshot() AS snapshot_value,
    pg_snapshot_xmin(pg_current_snapshot()) AS low_boundary,
    pg_snapshot_xmax(pg_current_snapshot()) AS high_boundary;
~~~

These functions give a view of **snapshot boundaries** and related transaction IDs, not a table listing all row versions. Because the snapshot can change between statements under `READ COMMITTED`, if you want to inspect a specific snapshot, capture it **once** and inspect that exact value within the same query/CTE.

~~~sql
WITH s AS (
    SELECT pg_current_snapshot() AS snapshot_value
)
SELECT
    snapshot_value,
    pg_snapshot_xmin(snapshot_value) AS snapshot_xmin,
    pg_snapshot_xmax(snapshot_value) AS snapshot_xmax
FROM s;
~~~

In the text representation of a snapshot, you can see a format with a low bound, high bound, and list of active XIDs. **Exact values vary with workload**; there is no fixed XID number you are expected to memorize.

### 3.6. A Conceptual Snapshot Example

Suppose a snapshot has:

~~~text
xmin = 730
xmax = 736
in-progress XIDs = {732, 734}
~~~

When evaluating the transaction that created a tuple:

- XIDs **736 and above** are not yet considered to have occurred in this snapshot.
- XIDs **732 and 734** were still active at snapshot time, so their writes are not seen as committed data from other transactions.
- Other XIDs **lower than xmax** still require checking committed/aborted status and applicable rules.

Snapshot bounds are not the `xmin`/`xmax` of a specific row. They are **two sets of similar names belonging to two different structures**.

---

## 4. Tuple System Columns

PostgreSQL provides several system columns that can be `SELECT`ed directly even though they are not in the user's `CREATE TABLE` column list:

| System column | Primary Meaning | What Not to Infer |
|---|---|---|
| `xmin` | XID that created the current tuple version | Not the business INSERT timestamp |
| `xmax` | Field associated with version ending **or lock state**, depending on flags | Non-zero does not guarantee a committed DELETE/UPDATE |
| `cmin` | Command ID of the statement creating the tuple within the transaction | Not creation time |
| `cmax` | Command ID of the statement marking the tuple ended, when applicable | Not a timestamp or commit state |
| `ctid` | Physical address of the tuple version in the table | Not a stable primary key |
| `tableoid` | OID of the table holding the version (useful with inheritance/partitioning) | Not a business ID |

### 4.1. Why Doesn't SELECT * Show xmin?

~~~sql
SELECT *
FROM mvcc_lab.documents;
~~~

It only shows the table's normal declared columns. To see system columns, you must **name them explicitly**:

~~~sql
SELECT
    doc_id,
    title,
    xmin,
    xmax,
    ctid
FROM mvcc_lab.documents;
~~~

Run the queries above after creating the lab table in the next section.

### 4.2. cmin/cmax Do Not Replace xmin/xmax

A transaction can run multiple statements in sequence; command IDs help PostgreSQL distinguish changes within the same transaction under internal visibility rules. However, `cmin`/`cmax` are not designed as a "what time was it" audit log. Learners usually only need to understand their role, not manually modify or decode them.

---

## 5. Creating the Table and Data to Observe MVCC

Work in a dedicated lab database:

~~~sql
CREATE SCHEMA IF NOT EXISTS mvcc_lab;

CREATE TABLE mvcc_lab.documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'review', 'published')),
    version_no INTEGER NOT NULL DEFAULT 1
        CHECK (version_no >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Load data **once** into the empty table:

~~~sql
INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (1, 'Doc A', 'draft'),
    (2, 'Doc B', 'draft'),
    (3, 'Doc C', 'draft');
~~~

Inspect:

~~~sql
SELECT
    doc_id,
    title,
    status,
    version_no,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS physical_table
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

An **illustrative** output, not XID/ctid values guaranteed by PostgreSQL:

~~~text
doc_id  title   status  xmin_text  xmax_text  ctid
1       Doc A   draft   741        0          (0,1)
2       Doc B   draft   741        0          (0,2)
3       Doc C   draft   741        0          (0,3)
~~~

Notes:

- XID `741` is just an **example number**; actual values depend on the database and concurrent activity.
- If all three rows were `INSERT`ed in **one statement/transaction**, they typically share the same `xmin`.
- `xmax=0` commonly appears when the version has not been marked deleted/updated/locked in a way requiring an XID, but do not turn this into a rule defining the entire row state.
- `ctid=(0,1)` is a **physical block/offset** pair, not a stable ID.
- Other transactions running before or after will make the XIDs in your environment differ from this illustration.

### 5.1. Do Not Rely on Display Order

Do not depend on natural heap scan order. Write `ORDER BY doc_id` for consistent output; `xmin` and `ctid` do not replace `ORDER BY`.

### 5.2. An Example That Is Not Retained

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (99, 'Temp doc', 'draft');

SELECT doc_id, title, xmin::text AS xmin, xmax::text AS xmax, ctid
FROM mvcc_lab.documents
WHERE doc_id = 99;

ROLLBACK;

SELECT doc_id
FROM mvcc_lab.documents
WHERE doc_id = 99;
~~~

Inside the transaction, the inserting session can see the newly added row with the writing transaction's `xmin`. After `ROLLBACK`, a normal `SELECT` no longer sees `doc_id=99`.

However, that **does not prove** the temporary version's bytes were physically erased from the page at rollback time. Uncleaned physical records can remain in storage until `VACUUM` or maintenance operations handle them.

---

## 6. xmin: The Transaction That Created the Version

### 6.1. INSERT Assigns xmin to the New Version

When a transaction successfully `INSERT`s a tuple, the tuple header stores `xmin` associated with the creating transaction.

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (100, 'Under test', 'review')
RETURNING
    doc_id,
    xmin::text AS creating_xid,
    xmax::text AS xmax_text,
    ctid;

ROLLBACK;
~~~

This example does not persist changes. Inside the writing transaction, `RETURNING xmin` lets you observe the XID attached to the newly created version.

### 6.2. UPDATE Also Creates a Version With a New xmin

A common misconception: `xmin` is not necessarily the XID of the **original INSERT of the business row**.

When updating:

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'Doc A edited',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1
RETURNING
    doc_id, title, version_no,
    xmin::text AS version_creator_xid,
    xmax::text AS xmax_text,
    ctid;

ROLLBACK;
~~~

`UPDATE` normally creates a **new tuple version** with the updating transaction's `xmin`. The old version is marked so it stops being visible to eligible snapshots once the update commits.

After rollback, the new version does not take effect; a normal `SELECT` still returns the row as it was before the update.

### 6.3. xmin Is Not "Creation Date"

Suppose document 1 was created last year, and today its title is `UPDATE`d. After the update commits, the current version has **today's** transaction `xmin`, not the original `INSERT` transaction.

To know when a business entity was created, store a dedicated column:

~~~sql
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

and ensure the application does not overwrite `created_at` on `UPDATE`; if you need detailed change history, use an appropriate audit log/history design.

### 6.4. Multiple Rows in One Transaction Can Share xmin

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET status = 'review',
    version_no = version_no + 1
WHERE doc_id IN (1, 2)
RETURNING doc_id, xmin::text AS xmin_text;

ROLLBACK;
~~~

Two versions created in the same transaction can share an XID. Therefore, **`xmin` is not a unique key per row**.

---

## 7. xmax: Written on UPDATE/DELETE or Locking, Not Simply "Deleted"

### 7.1. Basic Idea

In an initial easy-to-grasp model:

~~~text
Old version:
    xmin = transaction that created it
    xmax = transaction that marked it invalidated

New version after UPDATE:
    xmin = UPDATE transaction
    xmax = not yet marked ended/locked accordingly
~~~

But this is a **pedagogical model**—it is not enough to determine visibility from the integer in `xmax` alone.

### 7.2. DELETE Marks the Old Version

~~~sql
BEGIN;

DELETE FROM mvcc_lab.documents
WHERE doc_id = 3
RETURNING doc_id, title;

ROLLBACK;
~~~

A normal `DELETE` does not create a "new row version with deleted status" in the table. It marks the existing version as deleted by the relevant transaction. After `ROLLBACK`, document 3 remains visible.

If the `DELETE` is COMMITted, normal `SELECT`s on new snapshots will no longer see that row, though the old heap record can still exist physically until `VACUUM`.

### 7.3. Non-Zero xmax Can Be an Uncommitted UPDATE/DELETE

Session A is running an `UPDATE` and has not COMMITted yet. Session B under `READ COMMITTED` can still see the **old version**. The old version's header may already record A's transaction in `xmax`, even though B cannot yet see the new version.

Therefore:

~~~sql
-- NOTE: the following reasoning is WRONG.
SELECT doc_id
FROM mvcc_lab.documents
WHERE xmax::text <> '0';
~~~

The result of the query above is **not a reliable list of "deleted rows"**. It merely applies an expression to a system field of versions that are **already visible to the current SELECT**.

### 7.4. Non-Zero xmax Can Be a Row Lock

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

-- In another session, you might observe system columns of
-- a version that is still visible, but you must not conclude
-- from xmax alone that the row was deleted.

ROLLBACK;
~~~

Certain row locks are reflected in the `xmax` field and tuple header flags. When there are multiple lockers, PostgreSQL may use a **MultiXactId**.

### 7.5. Non-Zero xmax Can Point to an Aborted Transaction

A transaction attempts an `UPDATE`/`DELETE` and then `ROLLBACK`s. Transaction traces may remain in the tuple header for a while; the transaction that attempted the change was **aborted**, so it does not validly delete the version.

Concluding "non-zero xmax => deleted" ignores **COMMIT/ABORT status and flags**, and is therefore wrong.

### 7.6. What Must Be Checked to Determine Tuple Visibility?

Not just `xmax`:

- Is the tuple's `xmin` from a creating transaction that committed and is visible to this snapshot?
- If `xmax` has a value, is it a deleting/updating XID, a single locker, or a MultiXact?
- Is the transaction associated with `xmax` **committed**, **aborted**, or still **in progress**?
- Does the reader's snapshot see the version expiration?
- Do tuple header flags say `xmax` is invalid or lock-only?
- Is the reader **the creating/modifying transaction itself**, and at which command ID?

PostgreSQL handles these details inside the engine; applications typically **do not reimplement visibility algorithms in SQL**.

---

## 8. From INSERT to UPDATE to DELETE: Version Lifecycle

### 8.1. INSERT

~~~text
Transaction T10: INSERT document 1
Tuple V1:
    xmin = T10
    xmax = no effective ending marker

T10 COMMIT
=> Eligible later snapshots can see V1
~~~

### 8.2. UPDATE

~~~text
Transaction T20: UPDATE document 1

Tuple V1 (old):
    xmin = T10
    xmax = T20  [model showing marked replaced]

Tuple V2 (new):
    xmin = T20
    xmax = no effective ending marker

Before T20 COMMIT:
    Other transactions with eligible snapshots still see V1
    Transaction T20 usually sees its own change V2

After T20 COMMIT:
    Eligible new snapshots see V2
    Old snapshots may still see V1
~~~

### 8.3. DELETE

~~~text
Transaction T30: DELETE document 1

Tuple V2:
    xmin = T20
    xmax = T30  [model showing marked deleted]

Before T30 COMMIT:
    Other readers can still see V2

After T30 COMMIT:
    New snapshots do not see document 1
    Sufficiently old snapshots can still see V2
~~~

### 8.4. ROLLBACK

If T20 or T30 **ROLLBACK**s, their changes are not treated as committed. The valid old version can remain visible. Do not confuse "a transaction modified a page before rollback" with "the database must revert every byte immediately".

### 8.5. State Diagram by Snapshot

~~~mermaid
flowchart TD
    A["INSERT creates V1, xmin = T10"] --> B{"How does T10 end?"}
    B -- "ROLLBACK" --> C["V1 is not visible to other snapshots"]
    B -- "COMMIT" --> D["V1 can be visible"]
    D --> E["UPDATE creates V2; V1 marked xmax=T20"]
    E --> F{"T20?"}
    F -- "ROLLBACK" --> D
    F -- "In progress" --> G["Old readers can see V1; T20 sees V2"]
    F -- "COMMIT" --> H["New snapshot sees V2; old snapshot can see V1"]
    H --> I["DELETE marks V2 with T30"]
    I --> J{"T30?"}
    J -- "ROLLBACK" --> H
    J -- "COMMIT" --> K["New snapshot does not see row; physical version awaits cleanup"]
~~~

**T10, T20, and T30 are purely illustrative labels.** They are not actual XIDs in the lab database.

---

## 9. On UPDATE, Does PostgreSQL Create a New Version?

### 9.1. UPDATE Normally Does Not Overwrite the Old Tuple In Place

Under MVCC, `UPDATE` creates a new tuple version and marks the old version with the updating transaction's info. This allows older snapshots to keep reading their appropriate data.

~~~sql
BEGIN;

SELECT doc_id, title, xmin::text AS xmin, ctid
FROM mvcc_lab.documents
WHERE doc_id = 1;

UPDATE mvcc_lab.documents
SET title = 'Updated title',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING
    doc_id,
    title,
    xmin::text AS xmin,
    ctid;

ROLLBACK;
~~~

Within the transaction, the new tuple version may have a different `xmin` from the old one and a different `ctid` because it resides at a different physical location. The actual location depends on heap layout, data, and optimizations; never hardcode `(block,offset)` in applications.

### 9.2. HOT Update

PostgreSQL has the **HOT — Heap-Only Tuple** optimization when conditions permit—such as when updated columns do not change values tracked by any index and sufficient free space remains on the page. Tuple versions can then be linked in a **HOT chain**, reducing the need to create certain new index entries.

This **does not negate MVCC**: a new tuple version still exists; HOT is only an access/write optimization on heap and indexes.

Not every `UPDATE` of a non-indexed column is guaranteed to be HOT: page free space, expression/partial indexes, PostgreSQL version, and table state can all affect it.

### 9.3. "Live" Status Is Not Just Checking xmax

PostgreSQL may consider a version:

- Visible to one reader.
- Invisible to another reader.
- Superseded yet still needed by an old snapshot.
- Dead to all potentially reading snapshots and eligible for cleanup.

Thus, "a version is still on a page" **does not mean** it will appear in any current reader's `SELECT`.

---

## 10. ctid: Version Location Is Not a Business ID

`ctid` represents a tuple's location, typically formatted as:

~~~text
(block_number, item_offset)
~~~

For example:

~~~sql
SELECT doc_id, ctid
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

The `ctid` value can change when:

- The row is `UPDATE`d (creating a new tuple version).
- The table is rewritten by `VACUUM FULL`, `CLUSTER`, or other rewrite operations.
- Storage is reorganized during administrative operations.

### 10.1. Do Not Use ctid as a Primary Key

Wrong:

~~~text
API returns "documentId" = "(0,7)" and stores it permanently.
~~~

That TID **is not guaranteed to point to the same entity after an UPDATE/rewrite**. Use `doc_id` or a stable business key.

### 10.2. ctid Is Occasionally Useful for Diagnostics

If you want to show that two `UPDATE`s can produce different versions, `ctid` is useful as technical output in a **lab**. However, a normal `SELECT` only shows the version visible at that time—it does not grant arbitrary access to full `ctid` history.

Do not rely on `ctid` to look up a "previous version" of a document that has been updated and vacuumed many times.

---

## 11. Two psql Windows: Seeing the Old Version During an Uncommitted UPDATE

Open **two independent connections** (A and B) to the same lab database. This scenario ends with `ROLLBACK` so it makes no lasting data changes.

### 11.1. Session A: BEGIN and UPDATE

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'A editing but not committed',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING
    doc_id,
    title,
    version_no,
    xmin::text AS xmin,
    xmax::text AS xmax,
    ctid;

-- Pause here, do not COMMIT/ROLLBACK yet.
~~~

Inside session A, A's own `SELECT` sees the uncommitted change made by **A itself**.

### 11.2. Session B: Normal Read

~~~sql
SELECT
    doc_id,
    title,
    version_no,
    xmin::text AS xmin,
    xmax::text AS xmax,
    ctid
FROM mvcc_lab.documents
WHERE doc_id = 1;
~~~

Under standard `READ COMMITTED`, B **does not see A's uncommitted title**. B sees the old version of document 1 matching its snapshot. If you check the old version's `xmax`, you may sometimes see a value related to the in-progress update transaction, yet the version remains **visible to B**. Do not turn one specific observation into a universal rule for all cases.

### 11.3. Session A: ROLLBACK

~~~sql
ROLLBACK;
~~~

### 11.4. Session B: Read Again

~~~sql
SELECT doc_id, title, version_no, xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 1;
~~~

The row remains in its pre-experiment committed state; A's title change was discarded. Traces in the heap header may remain until the engine processes them, but they **never make an aborted change visible**.

### 11.5. What If A COMMITted Instead of ROLLBACK?

A **new** `SELECT` from B under `READ COMMITTED` normally sees the new version after commit. However, a transaction B under `REPEATABLE READ` that already captured an older snapshot can continue seeing the old version until B's transaction ends. That scenario is shown next.

---

## 12. Snapshot and Isolation: READ COMMITTED vs. REPEATABLE READ

### 12.1. READ COMMITTED: Per-Statement Snapshot

This is PostgreSQL's default isolation level in many installations. Each statement sees a fresh snapshot taken when that statement starts.

~~~text
Session B (READ COMMITTED)               Session A
----------------------------------      ------------------------
SELECT doc 2  → sees "Doc B"            BEGIN
                                        UPDATE doc 2
                                        COMMIT
SELECT doc 2  → sees "New Doc B"
~~~

B's two `SELECT`s can see two different versions because they are **two separate statements**. This is **not a dirty read**: B only sees the change after A has committed.

### 12.2. REPEATABLE READ: Stable Transaction Snapshot

In PostgreSQL, `REPEATABLE READ` uses a stable snapshot once the transaction's snapshot is established. Subsequent normal `SELECT`s continue using that snapshot.

**Session B — start first:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

-- The first SELECT establishes the snapshot view for transaction B:
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;

-- Keep transaction B open, switch to session A.
~~~

**Session A — update and commit:**

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'New Doc B',
    version_no = version_no + 1
WHERE doc_id = 2;

COMMIT;
~~~

**Session B — still inside the REPEATABLE READ transaction:**

~~~sql
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;

COMMIT;

-- A new statement after ending the transaction:
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;
~~~

Expected semantics:

- B's first `SELECT`: sees the version committed before B's snapshot was established.
- Second `SELECT` **in the same transaction B**: still sees the old version even though A committed.
- `SELECT` after B COMMITs, in a new transaction/statement: can see title `New Doc B`.

> This example performs an **actual COMMIT** in session A, modifying lab document 2. If you want to preserve initial data, practice in a dedicated lab database/schema or have an intentional reset procedure; never revert rows by modifying production data.

### 12.3. A Snapshot Is Not Copying the Entire Table

PostgreSQL does not create a new copy of the table for every transaction. A snapshot is **logical metadata** helping the engine determine which tuple versions are visible. Keeping multiple versions in the heap and reading via MVCC delivers a consistent view without copying all data for every reader.

### 12.4. REPEATABLE READ Does Not Guarantee Every UPDATE Succeeds

If a `REPEATABLE READ` transaction tries to modify a row already changed by another transaction since its snapshot, PostgreSQL can raise a **serialization failure** (e.g., `"could not serialize access due to concurrent update"`). A transaction reading an old snapshot cannot arbitrarily overwrite newer data without concurrency control.

### 12.5. SERIALIZABLE

PostgreSQL's `SERIALIZABLE` level additionally detects interactions that cannot correspond to any serial transaction schedule, including **SSI — Serializable Snapshot Isolation**. A transaction may be aborted with `SQLSTATE 40001` even when inspecting `xmin`/`xmax` pairs reveals nothing obvious.

The application must **retry the entire transaction** when that error is safely retriable, not just repeat the final `UPDATE`. That is one more reason not to build custom concurrency control algorithms on a few system columns.

---

## 13. Visibility Rules: Why Are XID, Status, and Snapshot All Needed?

To know whether a tuple version appears in a `SELECT`, PostgreSQL must evaluate multiple pieces of information together. In a simplified model:

### 13.1. Tuple Creating XID (`xmin`)

| Creating Transaction State | For Another Reader |
|---|---|
| **Aborted** | The tuple created by that transaction does not become visible committed data |
| **In progress** | Uncommitted changes are not visible as committed data |
| **Committed earlier and visible in snapshot** | The tuple may be considered visible, then `xmax` is checked |
| **Committed but outside current snapshot** | The tuple is still not visible in the older snapshot |

When the reader is **the writing transaction itself**, it follows rules to see its own changes via command IDs; the table above describes **other transactions** in general.

### 13.2. Ending or Locking XID (`xmax`)

If `xmin` indicates the version was validly created and is visible to the snapshot, check `xmax`:

| `xmax` Situation | General Meaning |
|---|---|
| No effective ending marker | The tuple can remain visible |
| `UPDATE`/`DELETE` transaction **aborted** | The change did not make the old tuple disappear |
| `UPDATE`/`DELETE` transaction still **in progress** | Other readers can normally still see the old tuple |
| `UPDATE`/`DELETE` transaction **committed and visible to snapshot** | The old tuple is no longer visible to that snapshot |
| `xmax` used for **row locking** | Not treated as deleting the tuple |
| Field contains a **MultiXactId** | Must inspect the group of lockers/updaters along with flags, not read as a single normal XID |

Actual engine rules include many more details about command IDs, infomask bits, subtransactions, speculative insertions, and snapshot types. This table simply illustrates **why `xmax = 0` cannot define "live row"**.

### 13.3. A Tuple Can Be Visible to A Yet Invisible to B

Suppose V1 was created and committed by T10. T20 updates it to V2, then T20 commits.

~~~text
Snapshot S_old taken before T20 commit:
  V1 → visible
  V2 → invisible

Snapshot S_new taken after T20 commit:
  V1 → invisible
  V2 → visible
~~~

The same page can hold **both versions**; the snapshot determines which version belongs in the `SELECT` output.

### 13.4. Normal SELECT Does Not Return All Physical Versions

~~~sql
SELECT doc_id, title, xmin::text, xmax::text, ctid
FROM mvcc_lab.documents
WHERE doc_id = 2;
~~~

This query only returns the version visible to the `SELECT`'s snapshot. It is **not** a command to "list all update history of document 2" even though `xmin`/`xmax` are selected.

### 13.5. PostgreSQL Must Coordinate Transaction Status

Knowing only `xmin=741` and `xmax=780` without knowing whether 780 is **committed, aborted, in progress, lock-only, or MultiXact** is not enough to determine version state accurately. The system maintains commit-status storage/lookup mechanisms and header flags to reach a conclusion.

---

## 14. pg_xact, Tuple Headers, and Hint Bits

### 14.1. pg_xact Stores Transaction Status

PostgreSQL uses a commit/abort transaction status facility commonly referred to as **pg_xact** (in older documentation you may see `pg_clog`).

When checking tuple visibility, the engine may need to know whether the relevant transaction XID has:

- Committed.
- Aborted.
- Or is still in progress.

Never directly read or modify internal files under the data directory in an application to "check" transaction status. That is internal storage/engine state managed by PostgreSQL.

### 14.2. Hint Bits Avoid Repeated Lookups

Once a transaction's status is determined, PostgreSQL can set **hint bits** in the tuple header so subsequent checks know faster whether the transaction committed or aborted.

Conceptual example:

~~~text
Tuple header:
  xmin   = T10
  xmax   = T20
  flags  = "xmin committed", "xmax lock-only/invalid/..."

Snapshot:
  set of transactions visible from reader's view

pg_xact / state metadata:
  transaction status when lookup is needed
~~~

Hint bits are an **internal optimization**, not a business API.

### 14.3. Why Is SELECT xmin/xmax Alone Not Enough?

The statement:

~~~sql
SELECT doc_id, xmin::text, xmax::text
FROM mvcc_lab.documents;
~~~

does not expose all flags in the tuple header. You can observe `xmax`'s number without knowing from it alone whether it represents **lock-only** or a **committed delete**. In fact, a truly deleted version may **not appear in the result set at all** for you to `SELECT`.

### 14.4. Is Inspecting Internal Pages Necessary?

Extensions such as `pageinspect` can help analyze tuple headers at a low level in appropriate investigation environments, usually requiring elevated privileges and deep knowledge of page formats. This lesson **does not require** installing extensions or reading raw pages; use SQL and existing system columns to understand the mechanism.

Do not run page-level queries on production just to "read xmax"; such analysis easily misreads tuple offsets, HOT chains, vacuum state, and access permissions.

---

## 15. Row Locks and MultiXactId

### 15.1. Locking a Row Differs From Deleting a Row

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SELECT FOR UPDATE` locks a row to coordinate with concurrent write transactions. By itself, it **does not change the title**, does not perform a business `DELETE`, and does not make a normal `SELECT` reader see the row as "deleted".

A row lock can leave metadata in the tuple header involving `xmax` and flags. Seeing a non-zero `xmax` on a visible tuple can therefore reflect a **lock**, not a commit that removed the row.

### 15.2. Multiple Transactions Locking Together

Some row lock modes are compatible with each other (for example, readers requesting compatible shared locks). PostgreSQL may need to track **multiple transactions locking the same tuple**.

**MultiXactId** is the mechanism representing a group of transactions participating in such lock/update states. In those circumstances, `xmax` cannot be interpreted simply as "the ID of one deleting transaction".

### 15.3. A Wrong Assumption

~~~text
If xmax = 881:
    "Transaction 881 DELETED the row"
~~~

This inference can be wrong because:

- 881 could be an uncommitted `UPDATE` transaction.
- 881 could have rolled back.
- The `xmax` value could be for a row lock.
- The field could hold a `MultiXactId` interpreted via tuple flags.
- An older snapshot could still see the old version even after a delete/update commit.

### 15.4. Row Locks Affect Concurrency

Two sessions wanting to `UPDATE` the same row may have to wait for each other. PostgreSQL coordinates row locks and MVCC:

- **MVCC** determines which versions are visible.
- **Locking** determines when a write/lock operation must wait or conflicts.

Do not equate "PostgreSQL has MVCC" with "there are never lock waits, deadlocks, or serialization failures".

### 15.5. Lock-Waiting Queries With Timeout

In the lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT doc_id
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

This sets a local lock wait limit for a transaction. If a query hits a lock timeout error inside a transaction, roll back or handle via a savepoint; do not leave the connection running in an aborted state.

---

## 16. UPDATE Does Not Create "History Records" Queryable Forever

A very common misconception:

> PostgreSQL keeps multiple versions due to MVCC, so can we SELECT old versions to build a history viewer?

**You cannot rely on that.** Old versions exist for **snapshot consistency** and can be cleaned up once no longer needed; they are **not business history with guaranteed retention**.

### 16.1. Business Example

~~~text
09:00  document 1: status=draft
09:10  UPDATE status=review, COMMIT
09:30  UPDATE status=published, COMMIT
~~~

A new `SELECT` at 09:31 typically sees `status=published`. PostgreSQL might still have old tuple versions on disk temporarily, but:

- Normal `SELECT`s do not return them.
- `VACUUM` can clean them when eligible.
- You have no query API to "fetch the 09:00 version" using only `xmin` and `xmax`.
- XIDs do not encode timestamps sufficient to reconstruct history.

### 16.2. To Audit, Design Auditing

An illustrative history table:

~~~sql
CREATE TABLE mvcc_lab.document_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id BIGINT NOT NULL,
    old_title TEXT,
    old_status TEXT,
    new_title TEXT,
    new_status TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    reason TEXT
);
~~~

This is only the **schema**. Complete history also requires triggers or application logic writing accurately on every update, actor tracking, security, retention, replay, and transaction handling. Never assume a history table populates automatically just because `CREATE TABLE` exists.

### 16.3. Backup/PITR Is Not Directly SELECTing Versions

PostgreSQL can recover to a point in time when configured with proper backups, WAL archiving, and PITR. That is a **recovery** mechanism, not `SELECT`ing old MVCC versions directly from a live table.

---

## 17. VACUUM: When Are Dead Versions Reclaimed?

### 17.1. Why Is VACUUM Needed?

`UPDATE` creates new versions and `DELETE` marks old versions. Over time:

- Many tuple versions are no longer visible to any transaction.
- Dead versions occupy space in the heap and indexes.
- Without cleanup, reads/writes can slow down, causing **table/index bloat**.

**`VACUUM`** reclaims and marks space as reusable based on the state and horizon of live transactions.

### 17.2. "COMMITted DELETE" Does Not Mean "Bytes Immediately Erased From File"

~~~text
T10 INSERT V1, COMMIT
T20 UPDATE V1→V2, COMMIT
T30 DELETE V2, COMMIT

SELECT on new snapshot: row not visible
Heap file: may still contain old physical versions
VACUUM: checks whether any snapshot still needs the versions
If eligible: can reclaim/mark for reuse
~~~

Once all snapshots that might need a dead tuple have finished, the engine can process dead versions. This is not an instant wipe of every byte across all files at `COMMIT`.

### 17.3. Dead to One Snapshot Is Not Necessarily Removable for All Snapshots

A new snapshot after an `UPDATE` `COMMIT` may no longer see V1, but a `REPEATABLE READ` transaction started earlier can still see V1. Therefore, `VACUUM` **must not reclaim V1 too early**.

Distinguish between:

1. **Invisible to a given reader.**
2. **Dead to every snapshot that could still need the version.**
3. **Processed by `VACUUM` for space reuse.**

These are three distinct states/concepts.

### 17.4. Regular VACUUM and VACUUM FULL

| Command | Primary Purpose | Operational Note |
|---|---|---|
| `VACUUM` | Clean dead tuples, maintain visibility/free space and frozen XIDs | Normally runs concurrently with regular workloads, though still consumes resources |
| Autovacuum | Background workers processing eligible tables | Needs monitoring; never disable arbitrarily |
| `VACUUM FULL` | Rewrite the table to reclaim more physical disk space | Requires a strong lock, can cause downtime, changes `ctid` locations |

Do not run `VACUUM FULL` in production just to "reset xmin/xmax" or inspect `ctid`. Its purpose is not to serve as an interactive MVCC history inspection tool.

### 17.5. Rolled-Back Records Also Need Physical Cleanup

An `INSERT` followed by `ROLLBACK` can leave a tuple in the heap that the engine knows is not visible. A rolled-back `UPDATE` can leave an invalid new version. Those versions/spaces can be cleaned up later by `VACUUM` or cleanup mechanisms.

**Semantic rollback** does not necessarily delete all physical changes immediately.

---

## 18. Freezing and XID Wraparound

### 18.1. Why Do 32-bit XIDs Need Anti-Wraparound Mechanisms?

Traditional transaction IDs in tuple headers have a finite 32-bit domain. After very many transactions, the number space wraps around. Without a way to distinguish "old" from "new", comparing XID age could mistake a very old transaction for a brand-new one.

PostgreSQL uses **XID age, freezing, and maintenance** to ensure sufficiently old tuples are safely treated as belonging to committed past transactions while preventing dangerous wraparound situations.

### 18.2. A Frozen Tuple Does Not Mean Raw xmin Is Always 2

In older descriptions/implementations, you may see a special symbol **`FrozenTransactionId`**. However, in many modern PostgreSQL versions, freezing can be represented by **flags** in the tuple header, while the observed raw `xmin` value is not necessarily rewritten to one specific magic number.

Therefore, do not conclude:

~~~text
xmin::text <> '2'  → tuple is definitely not frozen
~~~

That is a misconception. Frozen state is determined by storage/visibility mechanisms, not an application convention based solely on `xmin`'s text value.

### 18.3. A Very Old Transaction Does Not Mean a Very Old Business Row

XID ordering and age calculations use internal wraparound semantics. Do not compute:

~~~text
business age of row = current_xid - xmin
~~~

and treat it as "seconds" or "days". XIDs are not timestamps and can be frozen, modulo-wrapped, in another epoch, or not allocated at `BEGIN`.

### 18.4. Observing XID Age at the Database Level

In an environment with privileges to read statistics:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
~~~

This is an indicator of XID age distance for database maintenance, **not** a table of when data was created.

### 18.5. Observing XID Age of Relations

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    age(c.relfrozenxid) AS rel_xid_age
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname = 'mvcc_lab'
ORDER BY rel_xid_age DESC;
~~~

`relfrozenxid` shows the freezing horizon for a relation. Never edit catalog values directly to "reduce XID age"; use autovacuum/`VACUUM` and PostgreSQL-supported administrative procedures.

### 18.6. MultiXact Also Has Its Own Lifecycle and Freezing

When multiple transactions lock the same tuple, `MultiXactId`s also require age and wraparound management. PostgreSQL has autovacuum/freeze mechanisms for MultiXacts as well. Do not try to interpret every `xmax` value as a single XID and ignore MultiXact age.

### 18.7. Consequences of Ignoring Autovacuum

If XID age grows toward dangerous thresholds without timely freezing, PostgreSQL triggers protective mechanisms and warnings, and can even refuse write transactions to prevent losing version distinction. Therefore, **never disable autovacuum arbitrarily** in write-active databases.

---

## 19. Long Transactions and the Global xmin Horizon

### 19.1. Why Can Long Read Transactions Cause Bloat?

A `REPEATABLE READ` transaction holds an old snapshot. Meanwhile:

~~~text
Reader R: BEGIN REPEATABLE READ ──────────(long read)─────────── COMMIT
Writer W: UPDATE many rows → COMMIT
Writer X: UPDATE more     → COMMIT
VACUUM:   cannot clean versions R might still read
~~~

Old versions that R is still entitled to see must be retained long enough. If R stays open too long, dead tuples accumulate and cause bloat. Other horizon-holding sources include replication slots, prepared transactions, or sync/backup mechanisms depending on configuration.

### 19.2. backend_xmin Differs From Tuple xmin

In `pg_stat_activity`:

- `backend_xid` is the XID currently assigned to the backend (if any).
- `backend_xmin` represents the XID horizon the backend is holding for its snapshot/transaction visibility.

This **does not mean** `backend_xmin` is "the smallest `xmin` among rows read by the backend's query".

### 19.3. Observing Open Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Some columns/details for other sessions require appropriate privileges. Do not conclude a slow backend must be terminated based solely on transaction age; verify its owner and impact first.

### 19.4. Idle in Transaction

A session running:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT * FROM mvcc_lab.documents;
-- Application forgets to COMMIT/ROLLBACK for many minutes.
~~~

can enter `idle in transaction`. With a snapshot still held, it can restrict cleanup of old versions. End transactions when done:

~~~sql
ROLLBACK;
~~~

Under `READ COMMITTED`, a normal `SELECT`'s snapshot is not necessarily retained across statements; do not apply the exact same horizon conclusion to **every** `idle in transaction` session. Even so, long-open transactions still hold locks/resources and remain an operational concern.

### 19.5. Horizon Holders Are Not Only App Backends

When investigating bloat and high XID age, DBAs also check:

- Replication slots with relevant `xmin` or `catalog_xmin`.
- Prepared transactions not yet committed or rolled back.
- Standby feedback and replicas holding snapshots.
- Autovacuum, freeze progress, and retention.

Never drop replication slots or prepared transactions casually, as that can break replication or corrupt business transactions.

---

## 20. SQL Diagnostics Without Touching Storage Internals

### 20.1. Viewing Visible Versions and System Info

~~~sql
SELECT
    doc_id,
    title,
    status,
    version_no,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS source_relation
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

How to read it:

- `doc_id`: business key defined by the schema.
- `xmin`: hints at the XID that created the **visible version**.
- `xmax`: may relate to update/delete/lock; do not classify directly from it alone.
- `ctid`: physical address of the **visible version**.

### 20.2. Checking Whether the Current Transaction Has an XID Yet

~~~sql
BEGIN;

SELECT
    pg_current_xact_id_if_assigned() AS xid_before_write;

UPDATE mvcc_lab.documents
SET title = title
WHERE doc_id = 1;

SELECT
    pg_current_xact_id_if_assigned() AS xid_after_write;

ROLLBACK;
~~~

`UPDATE ... SET title = title` can still create a new version under `UPDATE` semantics even when the `title` value does not change. It is **not** a "read-only check without writing". Because of `ROLLBACK`, no change is persisted in the lab.

If you only want to observe without allocating a new XID, do not call `pg_current_xact_id()` in a pure read transaction because that function can assign an XID.

### 20.3. Inspecting Snapshots

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH s AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    snap,
    pg_snapshot_xmin(snap) AS snapshot_xmin,
    pg_snapshot_xmax(snap) AS snapshot_xmax
FROM s;

ROLLBACK;
~~~

This is the **transaction's snapshot horizon**, not tuple `xmin`/`xmax`. These functions aid in observing the mechanism; they do not replace an engine that explains all MVCC internals.

### 20.4. Checking Other Backends' State

~~~sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
~~~

With proper privileges, you can detect sessions with long transactions or waiting on locks. Do not treat these values as per-document change history.

### 20.5. Numbers Are Not Stable Across Runs

XIDs, snapshot bounds, `ctid`, and lock info depend on database activity, other transactions, and vacuuming. In exercises, **explain the relationships** rather than hardcoding tests expecting `xmin=741` or `ctid=(0,1)`.

---

## 21. Optimistic Locking: Prefer version_no Over xmin

### 21.1. Application-Layer Lost Update

Suppose:

~~~text
Client A reads current title, version_no=1.
Client B also reads current title, version_no=1.
Client A saves "Content A", version_no increments to 2.
Client B saves "Content B" over stale data without checking version.
~~~

If the application overwrites unchecked, A's change can be lost from a business standpoint.

### 21.2. Conditional Update Using version_no

~~~sql
UPDATE mvcc_lab.documents
SET
    title = 'Content from client',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1
  AND version_no = 1
RETURNING doc_id, title, version_no;
~~~

**Run on the lab only** when you actually intend to update. Meaning:

- If the current version has `version_no=1`, the update succeeds and increments it to 2.
- If the client is stale, `UPDATE 0` shows the version token **no longer matches**, so the application returns a conflict and asks to reload.
- In PostgreSQL, the version-conditioned `UPDATE` executes atomically alongside acquiring the appropriate row lock, avoiding the anti-pattern of checking the version in the client and then writing independently.

### 21.3. Explicit Versions Have Many Benefits

- Fits API/ETag designs and can live cleanly in UI payloads.
- Stable in **application semantics**, without needing to understand modulo XIDs.
- Not confused by developers with MVCC headers or row locks.
- Can be recorded alongside audit/event history per business policy.

Applications still need transactions, `UNIQUE`/constraint enforcement, and retries on contention; `version_no` does not replace all guarantees of `SERIALIZABLE` or history design.

### 21.4. Can xmin Be Used as a Version Token?

In some tools and ORMs, `xmin` is used as a **short-term conflict detection signal** for a specific row version. However, it should not be treated as a long-term stable API or business-level "version number" because:

- `xid` values have wraparound/epoch semantics.
- Table rewrites, freezing, and storage changes can affect context.
- `xmin` is not a timestamp or a per-entity counter.
- Using it outside PostgreSQL or across replication/copying may not preserve expected semantics.

If you adopt that strategy, rely strictly on verified driver/ORM contracts, scope, and PostgreSQL version. For new designs needing clear long-term semantics, **a dedicated `version_no` column is usually easier to manage**.

---

## 22. Misconceptions About xmin/xmax to Avoid

### 22.1. "xmin is row creation time"

False. XIDs are not timestamps; after an `UPDATE`, the current version carries the updating transaction's `xmin`, not the original `INSERT` transaction.

### 22.2. "xmax = 0 means live row, non-zero means deleted"

False. `xmax` can also store locks, MultiXacts, in-progress XIDs, or aborted XIDs. Visibility depends on commit status, flags, and snapshots.

### 22.3. "Every old version can be SELECTed"

False. Normal `SELECT`s only see versions valid for the snapshot. Old versions may already be cleaned up by `VACUUM`.

### 22.4. "ctid is a better ID than primary key"

False. `ctid` is the physical address of a tuple version and can change after `UPDATE`/rewrites.

### 22.5. "A larger XID definitely committed later"

False. XID allocation order is not `COMMIT` order, and XIDs are subject to wraparound/epoch.

### 22.6. "A transaction gets a permanent XID immediately on BEGIN"

Not necessarily. Read transactions may not be assigned a regular XID; functions like `pg_current_xact_id()` can actively trigger allocation.

### 22.7. "VACUUM only cleans DELETEd rows"

False. Old versions from `UPDATE`s, records from aborted transactions, and XID age freezing all involve maintenance.

### 22.8. "VACUUM FULL is safe to try anytime"

False. `VACUUM FULL` takes a strong lock, rewrites the table, and disrupts operations. Never run it casually in production.

### 22.9. "PostgreSQL has MVCC so there are no lock waits"

False. `UPDATE`/`DELETE`/`SELECT FOR UPDATE` and DDL can still wait on locks or deadlock. MVCC and locking complement each other.

### 22.10. "READ COMMITTED holds one snapshot from BEGIN to COMMIT"

False in PostgreSQL. `READ COMMITTED` usually takes a snapshot per statement; `REPEATABLE READ` holds a stable snapshot once established.

### 22.11. "An aborted transaction can still be committed with COMMIT"

No. After an SQL error puts a transaction into an aborted state, you must roll back or roll back to a valid savepoint. `COMMIT` on an aborted transaction does not force failed changes into committed data.

### 22.12. "xmin/xmax can replace an audit trail"

False. They serve MVCC and do not record business history, actor, reason, timestamp, vacuumed old versions, or external changes.

---

## 23. Quick Reference Table

| Want to Know | Appropriate Tool / SQL | Note |
|---|---|---|
| Which transaction created the visible version? | `SELECT xmin FROM table` | XID of the **version**, not entity creation history |
| What ending/lock field does the version have? | `SELECT xmax FROM table` | Do not infer deleted automatically |
| Where is the version in the heap? | `SELECT ctid FROM table` | Can change |
| Has the current transaction been assigned an XID? | `pg_current_xact_id_if_assigned()` | Can be NULL |
| Full XID of the current transaction? | `pg_current_xact_id()` | Can cause an XID to be allocated |
| Current snapshot? | `pg_current_snapshot()` | Not a list of row history |
| Snapshot boundaries? | `pg_snapshot_xmin(snap)`, `pg_snapshot_xmax(snap)` | Names overlap tuple fields but have different meanings |
| What horizon is a backend holding? | `pg_stat_activity.backend_xmin` | Not a row's `xmin` |
| How long has a transaction been open? | `pg_stat_activity.xact_start` | Requires privilege to view sessions |
| When are old versions cleaned? | VACUUM and visibility horizons | Not cleaned if still needed by an old snapshot |
| Database XID age | `age(datfrozenxid)` | Maintenance metric, not document age |
| Document creation time | Application-managed `created_at` | Do not infer from `xmin` |
| Update history | Audit/history table or event log | Do not infer from dead tuples |
| Detecting client edits based on stale version | `WHERE version_no = :expected` | Prefer a dedicated version token |

### 23.1. Diagram of Layers Involved in Visibility Decisions

~~~mermaid
flowchart TD
    A["Reader sends SELECT"] --> B["Reader's snapshot"]
    A --> C["Tuple version in heap"]
    C --> D["xmin: creating transaction"]
    C --> E["xmax: ending/lock/MultiXact"]
    C --> F["Tuple header flags, command metadata"]
    D --> G["XID status / pg_xact when needed"]
    E --> G
    B --> H["PostgreSQL MVCC ruleset"]
    F --> H
    G --> H
    H --> I{"Tuple visible to this snapshot?"}
    I -- "Yes" --> J["Can appear in SELECT result"]
    I -- "No" --> K["Does not appear in normal SELECT"]
~~~

**Do not replace this diagram with `WHERE xmax = 0`**. PostgreSQL already has an engine handling visibility; application tasks simply read the rows returned by valid SQL statements under their snapshot.

---

## 24. Practice Exercises

Exercises use `mvcc_lab.documents` from section 5, unless two sessions or a hypothetical scenario are specified. **To keep experiments repeatable**, prefer operations ending in `ROLLBACK`. Any exercise that `COMMIT`s modifies lab data and may make `version_no` differ from 1 later.

### Exercise 1 — Identifying System Fields

Write SQL to display `doc_id`, `title`, `xmin`, `xmax`, `ctid`, and `tableoid` of the three documents. Why doesn't `SELECT *` automatically show `xmin`?

### Exercise 2 — One INSERT, Multiple Rows

If all three documents are `INSERT`ed in one transaction, why can they carry the **same xmin** despite having three different `doc_id`s?

### Exercise 3 — Checking When an XID Is Assigned

Write a transaction starting with `pg_current_xact_id_if_assigned()`, perform a temporary `UPDATE`, call the function again, and `ROLLBACK`. Why shouldn't you always use `pg_current_xact_id()` in the first step when you only want to observe?

### Exercise 4 — INSERT Then ROLLBACK

`INSERT` document 99 inside a transaction, `SELECT xmin/ctid`, `ROLLBACK`, and then `SELECT` again. Is row 99 still visible? Is the physical data necessarily erased from the heap immediately?

### Exercise 5 — UPDATE Creates a New Version

Write a transaction updating the title of document 1, returning `xmin` and `ctid` via `RETURNING`, then roll back. Why does `xmin` after update no longer represent the original `INSERT` transaction?

### Exercise 6 — DELETE and xmax

`DELETE` document 3 without committing. Can session B under `READ COMMITTED` read document 3? What happens if A `ROLLBACK`s?

### Exercise 7 — Two Concurrent Sessions

Session A `BEGIN`s and `UPDATE`s document 1 without committing. Session B runs a normal `SELECT`. Which title version will B see? After A `COMMIT`s, what will a new statement in B under `READ COMMITTED` typically see?

### Exercise 8 — REPEATABLE READ

Session B establishes a `REPEATABLE READ` snapshot, then A `UPDATE`s document 2 and `COMMIT`s. Which version will B's second `SELECT` in the transaction see? Why?

### Exercise 9 — Snapshot xmin vs. Tuple xmin

Distinguish `pg_snapshot_xmin(pg_current_snapshot())` from `SELECT xmin FROM mvcc_lab.documents`. They share the word "xmin", but are they the same piece of information?

### Exercise 10 — Non-Zero xmax

Given a visible tuple with `xmin=100` and `xmax=101`, is there enough evidence to state "the row was DELETEd"? Name at least four possibilities to consider.

### Exercise 11 — SELECT FOR UPDATE

Write a transaction locking document 1 with `SELECT FOR UPDATE`, then roll back. Does locking delete the title? Why can it involve `xmax`?

### Exercise 12 — MultiXact

A tuple has multiple transactions holding compatible row locks simultaneously. Why can't `xmax` always be read as "one transaction deleting the row"?

### Exercise 13 — ctid

Why shouldn't `ctid` be used as a document ID in URLs or APIs? Name at least two operations that can cause this location to change.

### Exercise 14 — HOT

If an `UPDATE` modifies a column that does not affect indexes, PostgreSQL **may** perform a HOT update. Does that mean it creates no new tuple version?

### Exercise 15 — Tuple State by Snapshot

V1 was created and committed by T10. T20 creates V2 replacing V1, then commits. Snapshot `S_old` precedes T20's commit; `S_new` follows it. Which version can each snapshot see?

### Exercise 16 — Order After COMMIT?

Two transactions are assigned XIDs in order T30 then T31, but T31 `COMMIT`s before T30. Can you determine `COMMIT` order solely by comparing XID numbers?

### Exercise 17 — pg_xact and Hint Bits

Why does PostgreSQL need transaction status information beyond `xmin`/`xmax` numbers, and how do hint bits help?

### Exercise 18 — Aborted Transaction

A transaction `INSERT`s a tuple and then `ROLLBACK`s. Why is that tuple invisible to new snapshots even though it may have been physically written to the heap?

### Exercise 19 — VACUUM

A `REPEATABLE READ` session holds an old snapshot for 30 minutes while another session continuously `UPDATE`s rows and `COMMIT`s. Why might `VACUUM` be unable to reclaim certain old versions yet?

### Exercise 20 — XID Wraparound

Why can't `xmin` be used as a forever-increasing number? Is "raw xmin does not equal `FrozenTransactionId`" enough to conclude a row is not frozen?

### Exercise 21 — XID Age

Write SQL to find `age(datfrozenxid)` across databases. Why is that value not the data's "age in days"?

### Exercise 22 — Idle in Transaction

Write SQL checking PID, state, `xact_start`, and `backend_xmin`. Explain the difference between `backend_xmin` and a tuple's `xmin`.

### Exercise 23 — History Diagnostics

A team asks to view every title edit over the past 90 days using only `SELECT xmin, xmax, ctid`. Why can't that requirement be guaranteed via normal MVCC? Propose a history storage solution.

### Exercise 24 — Optimistic Locking

Clients A and B both read `version_no=1`. A updates and increments version to 2. Write B's `UPDATE` statement so it applies only when version is still 1. If `UPDATE 0`, how should it be handled?

### Exercise 25 — No-Op UPDATE

Is `UPDATE ... SET title=title` a read-only statement that allocates no XID and creates no new version? Explain.

### Exercise 26 — Snapshot and New SQL

A table has tuple V1 replaced by V2 after `COMMIT`. Why does a normal `SELECT` on the table in a new transaction return only V2 while V1 can still sit in the heap until `VACUUM`?

### Exercise 27 — SERIALIZABLE

Why does using `SERIALIZABLE` not mean every transaction will `COMMIT` successfully? What should an application do when receiving `SQLSTATE 40001`?

### Exercise 28 — Design Synthesis

A document-editing application wants: no dirty reads, no lost updates from stale clients, edit auditing, visibility into long transactions, and not treating non-zero `xmax` as `DELETE`. Propose an appropriate data architecture and workflow.

---

## 25. Suggested Solutions

### Exercise 1

~~~sql
SELECT
    doc_id, title,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS relation_name
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

System columns are not automatically expanded by `SELECT *`; they must be requested explicitly. They are tuple-version metadata, not application-defined columns.

### Exercise 2

`xmin` marks the **transaction that created the tuple version**, not a row ID. One transaction inserting multiple rows can create multiple tuples with the same XID; `doc_id` is the distinct identifier per entity.

### Exercise 3

~~~sql
BEGIN;

SELECT pg_current_xact_id_if_assigned() AS before_write;

UPDATE mvcc_lab.documents
SET title = title
WHERE doc_id = 1;

SELECT pg_current_xact_id_if_assigned() AS after_write;

ROLLBACK;
~~~

Before writing, the transaction may not have been assigned a regular XID, so the first result can be NULL. After `UPDATE`, an XID is normally assigned. `pg_current_xact_id()` can **actively assign an XID**, making the "has one been assigned yet?" experiment non-neutral.

### Exercise 4

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents (doc_id, title, status)
VALUES (99, 'Test draft', 'draft')
RETURNING doc_id, xmin::text, xmax::text, ctid;

ROLLBACK;

SELECT * FROM mvcc_lab.documents WHERE doc_id = 99;
~~~

`SELECT` after rollback does not see row 99. The tuple created earlier may not be physically erased immediately; PostgreSQL handles invalid versions during appropriate cleanup/`VACUUM`.

### Exercise 5

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'Temp title',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING doc_id, title, xmin::text AS xmin, ctid;

ROLLBACK;
~~~

`UPDATE` creates a new tuple version with the `UPDATE` transaction's `xmin`. Therefore, **the current version's `xmin`** must not be interpreted as the transaction that originally created the entity.

### Exercise 6

**Session A:**

~~~sql
BEGIN;
DELETE FROM mvcc_lab.documents WHERE doc_id = 3;
-- Not committed yet.
~~~

**Session B:**

~~~sql
SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 3;
~~~

Under `READ COMMITTED`, B continues seeing the old committed version with no dirty read. When A `ROLLBACK`s, the `DELETE` has no effect; B continues seeing document 3.

**Back to Session A:**

~~~sql
ROLLBACK;
~~~

### Exercise 7

Before `COMMIT`, B sees the **old committed** title. After `COMMIT`, a new `SELECT` by B under `READ COMMITTED` typically sees the **new title**. There is no dirty read; the snapshot advances between statements.

### Exercise 8

B keeps the `REPEATABLE READ` snapshot established before A's commit. B's normal `SELECT`s continue seeing the **old version** within that transaction. Once B ends its transaction and takes a new snapshot, it can see A's committed version.

### Exercise 9

`pg_snapshot_xmin` is a **transaction ID boundary within a snapshot**, used to determine transaction visibility. `documents.xmin` is the XID that **created a tuple version**. Their names look similar, but they are not the same object.

### Exercise 10

Not enough evidence. `xmax=101` could belong to a transaction that is:

1. An `UPDATE`/`DELETE` still in progress.
2. An `UPDATE`/`DELETE` that aborted.
3. A row lock with no delete behavior.
4. A `MultiXactId` representing a group of lockers.
5. A committed `UPDATE`/`DELETE` where the old version is still visible to an older snapshot.

You must consider snapshot, commit status, flags, and semantics of the involved transaction.

### Exercise 11

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

Locking coordinates concurrent operations; it does not delete the title. Row-lock metadata can be reflected in `xmax`/tuple flags, which is why non-zero `xmax` does not equal `DELETE`.

### Exercise 12

PostgreSQL uses **`MultiXactId`** to represent a group of transactions participating in row locking in appropriate scenarios. The `xmax` field must be interpreted alongside flags, not always as a single XID.

### Exercise 13

`ctid` is the **physical address of a tuple version**, which can change after `UPDATE`, `VACUUM FULL`, `CLUSTER`, or rewrites. APIs need stable application IDs like `doc_id`.

### Exercise 14

No. HOT is an `UPDATE` optimization in heap/indexes; a new tuple version still exists under MVCC. HOT can skip updating some index entries when conditions allow, without removing versioning.

### Exercise 15

Snapshot `S_old` taken before T20's commit typically sees **V1** and not V2. Snapshot `S_new` taken after T20's commit typically sees **V2** and not V1. Version V1 may still exist physically in the heap to serve `S_old`.

### Exercise 16

No. XIDs generally relate to allocation/activity timing, **not commit sequence**; T31 can commit before T30 even if assigned an XID later.

### Exercise 17

PostgreSQL needs to know whether the creating/ending transaction committed, aborted, or is still running, while also evaluating flags and the snapshot. `pg_xact` stores transaction status; **hint bits** in the tuple header cache conclusions to avoid repeated lookups.

### Exercise 18

`INSERT` may write physical bytes and an `xmin` for the tuple, but an **aborted** transaction produces no committed visible data. MVCC checks transaction status, not merely whether bytes exist.

### Exercise 19

The reader's old snapshot may still need tuple versions from before the `UPDATE`s. `VACUUM` must not reclaim versions still potentially visible to that reader; long read transactions increase retention time and bloat.

### Exercise 20

Traditional XIDs have **32-bit wraparound**. Freezing and XID age mechanisms prevent confusing very old transactions with new ones. In modern PostgreSQL, freezing can be represented via tuple header flags; `raw xmin != FrozenTransactionId` does not prove a tuple is unfrozen.

### Exercise 21

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

`age(datfrozenxid)` measures **transaction ID age for maintenance/freezing**, not wall-clock days or document creation timestamps.

### Exercise 22

~~~sql
SELECT
    pid, state, xact_start,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

`backend_xmin` is the XID horizon held by the backend for snapshot/visibility; `tuple.xmin` is the transaction that created a **specific row version**.

### Exercise 23

MVCC is not a 90-day retention history store. Old tuple versions can be cleaned once no snapshot needs them; system columns do not provide actor, reason, or exact edit timestamps. Design an **audit table**, triggers/application events, clear write permissions, retention, and history queries.

### Exercise 24

Suppose B holds token `expected_version=1`:

~~~sql
UPDATE mvcc_lab.documents
SET title = 'Update from B',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1 AND version_no = 1
RETURNING doc_id, version_no;
~~~

If A already updated `version_no` to 2, B's `UPDATE` matches no rows and returns **0 rows**. B should report a conflict, reload the new version, ask the user to resolve differences, or apply an intentional merge; never overwrite blindly.

### Exercise 25

No. `UPDATE SET title=title` is still a write statement; PostgreSQL normally creates a new tuple version even when the `title` value does not change, can allocate an XID, and participates in locking/WAL. Do not treat it as a side-effect-free `SELECT`.

### Exercise 26

Normal `SELECT` applies an MVCC snapshot and returns only visible tuple versions. V1 may be marked old and invisible to new snapshots while still needed by old snapshots or awaiting `VACUUM` reclamation; thus **not visible** does not mean **no physical bytes remain**.

### Exercise 27

PostgreSQL's `SERIALIZABLE` can detect conflicts causing a transaction to abort with `SQLSTATE 40001`. You must roll back and retry the **entire transaction** on a fresh snapshot with a bounded retry limit, not just retry the last `UPDATE` using stale facts.

### Exercise 28

One design:

1. Use `doc_id` as primary key alongside appropriate data constraints.
2. Read via normal SQL; PostgreSQL's MVCC prevents dirty reads from other transactions.
3. Send `version_no` to the client; on updates use `UPDATE ... WHERE doc_id=? AND version_no=? RETURNING ...`.
4. If `UPDATE 0`, return a conflict instead of overwriting.
5. Use a transaction to commit the document change **together with the audit event**.
6. Record who edited, what changed, when, and request ID if needed; do not rely on `xmin`/`xmax`.
7. Keep transactions short and roll back on errors.
8. Monitor `pg_stat_activity`, `backend_xmin`, long-running transactions, autovacuum, and XID age.
9. Never treat non-zero `xmax` as deleted, and never use `ctid` as an ID.
10. When complex concurrent interactions exist, verify isolation level, row locking, and retry policies as needed.

---

## 26. Summary

**Transaction ID (XID), `xmin`, `xmax`, and snapshots are cooperating parts of PostgreSQL's MVCC mechanism, not four simple audit columns.**

- **XID:** transaction identifier tied to versions; not a timestamp, commit order, or primary key. Traditional XIDs are 32-bit, while newer APIs offer `xid8`/Full Transaction ID.
- **Tuple `xmin`:** tied to the transaction that created the **current tuple version**. After `UPDATE`, the new version has a new `xmin`; never infer entity creation time from it.
- **Tuple `xmax`:** can relate to `UPDATE`/`DELETE`, uncommitted/aborted transactions, row locking, or MultiXacts. **`xmax != 0` is not a test for "row was deleted".**
- **`ctid`:** physical address of a version, not a stable ID.
- **Snapshot:** determines which version a reader sees, alongside transaction commit status and tuple header flags. `READ COMMITTED` takes a snapshot per statement; `REPEATABLE READ` holds a transaction snapshot per PostgreSQL rules.
- **VACUUM and freeze:** clean old versions when safe and prevent XID wraparound; dead to a new snapshot is not necessarily eligible for reclamation if an old snapshot still needs it.
- **Long transactions and replication/prepared transactions:** can hold back the horizon and delay cleanup; monitor them.
- **Application design:** use PKs, a `version_no` column, business timestamps, and audit tables when needed; never turn system columns into long-term data contracts.

The right mental model: **identify creating/ending transactions on the tuple → check committed/in-progress/aborted status and lock flags → apply the reader's snapshot → let PostgreSQL decide visibility → rely on VACUUM/freeze for physical lifecycle → store audit trails and business locks in dedicated structures**.
