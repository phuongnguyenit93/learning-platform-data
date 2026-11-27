# Undo, MVCC, and Read Consistency in Oracle Database

Oracle Database allows multiple sessions to read and modify data concurrently. One session may be updating a row while another session runs a query on that same table. So readers never see uncommitted data or a result stitched together from inconsistent states, Oracle uses **undo**, **MVCC (Multi-Version Concurrency Control)**, and **read consistency**.

These three concepts are closely related yet not synonymous:

- **Undo** stores the information needed to roll back changes and reconstruct older data versions.
- **MVCC** is how Oracle serves multiple logical versions of data to concurrent readers and writers.
- **Read consistency** ensures a query sees data as of a consistent point in time, rather than seeing ongoing changes happening mid-query.

In Oracle, a standard query does not have to wait for every other transaction to finish before reading data. When a row is being modified by another session without committing yet, a reader can use undo to reconstruct the previously committed version. Consequently, readers and writers generally do not block each other in traditional read-waits-for-write or write-waits-for-read fashion.

This lesson explains undo records and undo segments, SCN, consistent read, statement-level vs. transaction-level snapshots, two-session interactions, undo vs. redo differences, undo retention management, and `ORA-01555` errors.

## 1. Why Is Read Consistency Needed?

### 1.1. The Problem When Multiple Sessions Access Data Concurrently

Suppose an accounts table has balances:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5,000 |
| 202 | 8,000 |

Session A transfers 1,000 from account 101 to account 202. Inside its transaction, A performs two operations:

1. Debit 1,000 from account 101.
2. Credit 1,000 to account 202.
3. COMMIT.

While A has only completed step 1, Session B runs a query summing all balances. If B could read the incomplete state, it might see a total of 12,000 instead of 13,000. That is an uncommitted intermediate state and must not be treated as confirmed data.

Oracle uses read consistency so B sees a committed state valid as of when the query began. B never reads half of A's transaction.

### 1.2. Core Goals

Read consistency in Oracle helps guarantee:

- **No reading uncommitted data from another transaction** (dirty read).
- A standard SELECT sees data from the same logical snapshot throughout the statement.
- Readers can read previously committed versions while a writer is updating rows.
- A multi-table query does not arbitrarily mix versions committed at different times within a single statement snapshot.

This does not mean all queries within a READ COMMITTED transaction see the exact same snapshot. By default, Oracle assigns a fresh snapshot to each statement; this is explained in Section 7.

### 1.3. Dirty Read, Non-Repeatable Read, and Phantom

| Phenomenon | Meaning |
| --- | --- |
| Dirty read | Reading uncommitted changes from another transaction |
| Non-repeatable read | Reading the same row across two statements and receiving different values because another transaction committed changes |
| Phantom | Re-running a query condition and seeing added or missing matching rows because another transaction committed an insert/delete/update |
| Read skew | Reading related pieces of data from mutually inconsistent points in time |

Oracle disallows dirty reads in standard transaction isolation levels. Under default READ COMMITTED, different statements can see different snapshots, so non-repeatable reads and phantoms can occur between two statements. SERIALIZABLE and READ ONLY provide a consistent transaction-level snapshot per Oracle rules.

## 2. What Is Undo?

### 2.1. Undo Stores Information to Revert to Prior States

When a transaction modifies data, Oracle generates undo information describing how to restore the prior version of the data. Depending on the operation:

- **UPDATE:** undo contains the old values needed to revert the update.
- **DELETE:** undo contains the information needed to restore the deleted row.
- **INSERT:** undo enables removing the effect of the newly inserted row upon rollback.

Example:

```sql
UPDATE employees
SET salary = 25000
WHERE employee_id = 100;
```

If the old value was 22000, undo retains enough information for Oracle to restore salary back to 22000 on transaction rollback or to reconstruct the previously committed version for a consistent read.

Undo is not simply a full copy of the entire table. It consists of change records managed by Oracle inside undo segments.

### 2.2. Undo Segments and Undo Tablespace

Undo records are stored in **undo segments**, which reside in a database-managed **undo tablespace**. When a transaction executes DML, Oracle uses an undo segment to record the necessary information.

One way to visualize this:

```text
Transaction
    |
    | UPDATE / INSERT / DELETE
    v
Undo segment
    |
    | undo records (before-image / rollback information)
    v
Undo tablespace

Data blocks  <---- modified ---->  Database buffer cache
    ^
    |
    +---- undo is used to reconstruct older versions
```

Under Automatic Undo Management, Oracle automatically manages allocating and reusing undo space according to the undo tablespace configuration and retention policies.

### 2.3. What Is Undo Used For?

Undo serves multiple roles:

1. **ROLLBACK:** undoing changes of uncommitted transactions.
2. **Read consistency:** reconstructing data versions matching a SELECT statement's snapshot.
3. **Flashback Query and certain Flashback features:** retrieving data versions within available undo and feature limits.
4. **Transaction recovery:** supporting recovery of incomplete transactions per Oracle mechanisms.

A committed transaction does not mean its undo is erased immediately. Old undo may still be required for running queries or flashback purposes during the retention window.

### 2.4. Undo Is Not Redo

Both undo and redo are essential, yet serve different purposes:

| Feature | Undo | Redo |
| --- | --- | --- |
| Primary goal | Undo changes, reconstruct old data versions | Replay changes for recovery |
| Information | Data/metadata needed for rollback and consistent read | Description of changes to reapply |
| Where managed | Undo segments in undo tablespace | Redo log buffer and online/archived redo logs |
| Used during ROLLBACK | Yes | Not the rollback mechanism |
| Used during media recovery | Does not replace redo | Essential component for rolling forward |

When DML modifies data blocks, Oracle also generates redo to protect recoverability. Changes to undo blocks are also logged to redo. Do not think of undo and redo as symmetric copies or assume either can replace the other.

## 3. How Does MVCC Work in Oracle?

### 3.1. Multiple Logical Versions of a Row

MVCC stands for *Multi-Version Concurrency Control*. Instead of forcing readers to always wait for writers to release locks, Oracle can use undo to reconstruct the row version matching the point in time the query needs to read.

For example, an account row initially has balance 5,000. Session A updates it to 4,000 without committing yet:

```text
Previously committed version: BALANCE = 5,000
Version being updated by A:   BALANCE = 4,000 (uncommitted)

Reader B needing a snapshot before A commits:
    -> uses undo to reconstruct BALANCE = 5,000
```

Oracle does not necessarily keep a separate full copy for every version in a dedicated version store like some other DBMSs. A consistent version is reconstructed on demand from the current data block and undo records.

### 3.2. Consistent Read

A *consistent read* returns data as it existed at a snapshot SCN. If the current block was modified by another transaction after that snapshot, Oracle can apply the necessary undo chain to reconstruct the block to a state matching that SCN.

As a result, the SELECT sees a consistent committed state, even though the current physical block may hold uncommitted changes or changes committed after the snapshot.

### 3.3. Readers and Writers Rarely Block Each Other

For standard SELECT statements:

- Readers do not need to wait for writers to commit in order to read prior versions.
- Writers do not need to wait for standard SELECTs to finish just because they are reading rows.
- Writers still need locks to protect changes and handle conflicts with other writers.
- Statements like `SELECT ... FOR UPDATE` have locking semantics different from a standard SELECT.

This is one of MVCC's major benefits: increasing concurrency while preserving read consistency.

### 3.4. MVCC Does Not Mean Nothing Ever Waits

An `UPDATE` statement may have to wait if the row is currently locked by another transaction. `SELECT ... FOR UPDATE` can wait on row locks. DDL, table locks, shared resources, or other contention can also cause waits.

Therefore, the accurate statement is **standard SELECTs normally read a consistent version without waiting on DML row locks**, not that Oracle never experiences blocking.

## 4. SCN and Snapshots

### 4.1. What Is an SCN?

SCN (*System Change Number*) is a logical sequence number Oracle uses to order change events in the database. An SCN is not simply a wall-clock timestamp in seconds. Oracle uses SCNs in recovery, read consistency, and many other features.

When a query needs a snapshot, Oracle determines an SCN corresponding to the start time of the statement or transaction depending on the isolation level.

### 4.2. Query Snapshot

You can visualize this as:

```text
Time --------------------------------------------------------->

SCN 100       SCN 110       SCN 120       SCN 130
   |             |             |             |
   |             |             |             +-- Transaction B COMMIT
   |             |             +---------------- Transaction A COMMIT
   |             +------------------------------ Query Q begins
   +-------------------------------------------- Old state

Query Q reads snapshot at SCN 110:
- Sees changes committed before the snapshot.
- Does not see changes committed after SCN 110.
```

Oracle uses undo to reconstruct necessary versions when current blocks changed after the snapshot SCN.

### 4.3. One Statement Sees One Snapshot

Under READ COMMITTED, a long-running SELECT starts at a logical snapshot. If another transaction commits while the SELECT is running, the running SELECT continues reading its own snapshot; the next statement can see the newly committed changes.

This matters for multi-row joins or aggregations. Oracle does not allow the start of a single statement to read old state and the end to read new state just because another transaction committed mid-flight.

## 5. Two-Session Practice: Reader and Writer

This example uses a small demo table to observe behavior. Open two SQL windows or two independent sessions in SQL Developer/SQLcl.

### 5.1. Create Table and Data

Run once in a study schema:

```sql
CREATE TABLE demo_mvcc_accounts (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO demo_mvcc_accounts VALUES (101, 5000);
INSERT INTO demo_mvcc_accounts VALUES (202, 8000);
COMMIT;
```

The initial balance of account 101 is 5000.

### 5.2. Session A: Update Without Committing

In Session A:

```sql
UPDATE demo_mvcc_accounts
SET balance = 4000
WHERE account_id = 101;

-- Not committed yet.
```

Session A has generated undo for the old value 5000 and holds the new change inside an uncommitted transaction.

### 5.3. Session B: Standard SELECT

In Session B:

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Result:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5000 |

Session B does not read A's uncommitted value 4000. Oracle uses undo to return the previously committed version.

### 5.4. Session B: Attempt to Update the Same Row

While A still has not committed, try in B:

```sql
UPDATE demo_mvcc_accounts
SET balance = 4500
WHERE account_id = 101;
```

This command will wait because A holds a row lock. This is a write operation competing with another write transaction, unlike a standard SELECT.

You do not need to leave the command waiting indefinitely in this exercise. Cancel the statement in the client or roll back Session B if it opened a transaction and is waiting.

### 5.5. Session A: COMMIT

Return to Session A:

```sql
COMMIT;
```

The change to 4000 is committed and transaction A's lock is released.

### 5.6. Session B: Run a New SELECT

Re-run in Session B:

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

New result:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 4000 |

Session B started a new statement under READ COMMITTED, so the new snapshot sees A's commit.

### 5.7. Takeaways

- Standard SELECT does not see A's uncommitted data.
- SELECT can read old versions via undo while A is modifying the row.
- B's UPDATE on the same row waits for the lock held by A.
- Once A commits, B's new statement sees the new value.
- Reader/writer and writer/writer have different concurrency behaviors.

## 6. Statement-Level Read Consistency

### 6.1. READ COMMITTED Is the Default

Oracle defaults to the **READ COMMITTED** isolation level. Each SQL statement gets its own consistent snapshot as of the time the statement starts.

Session A example:

```sql
SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Session B updates balance and COMMITs. When A runs the SELECT again, A can see the new value because that is a new statement with a new snapshot.

One transaction can contain multiple SELECT statements, and each statement can see newly committed data from other sessions.

### 6.2. Two SELECTs in the Same Transaction Can Return Different Results

Session A:

```sql
SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;

-- Wait for Session B to update and COMMIT.

SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

If B committed a change between the two statements, A can see a different value on the second SELECT. This is a transaction-level non-repeatable read under READ COMMITTED, and it is the designed behavior of this isolation level.

### 6.3. A Long SELECT Does Not Switch Snapshots Mid-Flight

Suppose Session A opens a multi-row SELECT cursor and is fetching results. Session B updates and commits several rows in the table while A is still reading.

A's running cursor continues returning results from the snapshot taken when the statement opened. Once A finishes and runs a new SELECT, the new statement can see B's committed changes.

This distinguishes between:
- Multiple separate SELECT statements: each statement can have a different snapshot.
- One running statement: data is read consistently according to that statement's snapshot.

### 6.4. Join Queries Also Have a Statement Snapshot

Example:

```sql
SELECT o.order_id,
       o.customer_id,
       c.customer_name,
       o.total_amount
FROM   orders o
JOIN   customers c
       ON c.customer_id = o.customer_id
WHERE  o.order_date >= DATE '2026-01-01';
```

Oracle ensures the tables read in the statement share the same read-consistent snapshot. A join query will not see `orders` rows from a newer time and `customers` rows from an older time simply because another transaction committed between scanning the two tables.

## 7. Transaction-Level Read Consistency

### 7.1. SERIALIZABLE

When multiple statements in the same transaction must see one stable snapshot, you can use the SERIALIZABLE isolation level:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;

-- Subsequent statements in the transaction use the transaction snapshot.
```

`SET TRANSACTION` must be placed at the beginning of the transaction, before other statements in that transaction.

In SERIALIZABLE, the transaction sees data committed before the transaction started (along with the transaction's own changes), per the transaction snapshot. If another transaction changes data that the SERIALIZABLE transaction attempts to update in a way causing a serialization conflict, Oracle may return `ORA-08177: can't serialize access for this transaction`.

SERIALIZABLE does not mean Oracle locks the entire table for the transaction. It provides snapshot semantics and required conflict detection; the application must implement an appropriate retry strategy when receiving serialization errors.

### 7.2. READ ONLY Transactions

If a transaction only needs to read a stable snapshot, you can use:

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT SUM(total_amount) FROM orders;
SELECT AVG(total_amount) FROM orders;

COMMIT;
```

`SET TRANSACTION READ ONLY` must also be placed at the start of the transaction. Read queries in the transaction use a transaction-level snapshot; standard DML is disallowed in this mode.

### 7.3. Comparing Isolation Levels

| Feature | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Snapshot | Per statement | Transaction-level | Transaction-level |
| Sees new commits between two SELECTs in the same transaction | Possible | No, uses transaction snapshot | No, uses transaction snapshot |
| DML by this transaction | Yes | Yes | No |
| Serialization conflict | Not under this serializable snapshot model | Possible ORA-08177 | No DML by this transaction |
| Typical use case | General application transactions | Multiple statements needing a consistent snapshot | Consistent read-only reporting |

Choose an isolation level based on business requirements. READ COMMITTED typically fits most OLTP transactions; use SERIALIZABLE or READ ONLY when a stable snapshot across multiple statements is required and the corresponding overhead/limits are acceptable.

### 7.4. A Transaction Still Sees Its Own Changes

Even with read consistency, a transaction still sees changes that it performed itself. A snapshot does not freeze the session from its own operations. Oracle merges the committed version at the snapshot with the current transaction's own changes according to SQL semantics.

## 8. Standard SELECT and SELECT FOR UPDATE

### 8.1. Standard SELECT

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

A standard SELECT reads a consistent version and does not lock rows merely for reading. It can read older versions via undo while another transaction modifies the row.

### 8.2. SELECT FOR UPDATE

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101
FOR UPDATE;
```

`FOR UPDATE` requests locks on the selected rows so the current session can update them safely. It may wait for another transaction currently holding locks on those rows. After acquiring the locks, the transaction can update the selected rows.

Several variants control waiting:
- `NOWAIT`: do not wait if a row is locked; return an error immediately.
- `WAIT n`: wait up to `n` seconds per Oracle syntax.
- `SKIP LOCKED`: skip rows currently locked, often used for controlled queue/work distribution.

These options alter lock acquisition behavior; they do not replace the consistent read mechanism of standard SELECTs.

### 8.3. When Is FOR UPDATE Needed?

Use it when application logic needs to:
1. Read a row to decide on an update.
2. Hold a lock on that row within the transaction.
3. Execute the update based on the read value.
4. COMMIT or ROLLBACK to release the lock.

Do not use `FOR UPDATE` on every SELECT. Unnecessary locking increases blocking and reduces concurrency.

## 9. Undo Retention and Undo Lifecycle

### 9.1. Undo Is Not Erased Immediately After COMMIT

After COMMIT, undo records are no longer needed to roll back that transaction, yet may still be needed for:
- Running queries with older snapshots.
- READ COMMITTED/Serializable transactions needing consistent reads.
- Flashback Query within the range of still-available undo data.

Oracle can reuse undo space when necessary according to retention policies and space pressure.

### 9.2. UNDO_RETENTION

The `UNDO_RETENTION` parameter sets a target duration for retaining undo (in seconds) under Automatic Undo Management. This value is a target, not an absolute promise in every configuration.

When the undo tablespace experiences space pressure, Oracle may reuse expired undo—or in certain necessary cases reuse unexpired undo—if retention guarantee is not enabled and free space is insufficient.

You can check settings with:

```sql
SHOW PARAMETER undo;
```

Or query parameters:

```sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN ('undo_management', 'undo_tablespace', 'undo_retention');
```

Appropriate privileges are required to read dynamic performance views.

### 9.3. RETENTION GUARANTEE

An undo tablespace can be configured with retention guarantee so Oracle will not overwrite unexpired undo merely due to space shortage. This is useful when flashback/long queries strictly require retention.

However, if the tablespace runs out of space and cannot allocate more extents, DML may fail due to lack of undo space. Therefore, `RETENTION GUARANTEE` must be accompanied by proper sizing, monitoring, and capacity expansion planning; do not enable it indiscriminately.

### 9.4. Automatic Undo Management

In standard configurations, Oracle manages undo automatically. DBAs must monitor:
- Undo tablespace size and autoextend settings.
- Undo generation rate of the workload.
- Duration of long-running queries.
- Actual achieved retention time.
- Snapshot too old errors and undo allocation failures.

Do not increase `UNDO_RETENTION` in isolation without evaluating storage capacity and undo generation rate.

## 10. ORA-01555: snapshot too old

### 10.1. Cause

Common error:

```text
ORA-01555: snapshot too old
```

This error occurs when Oracle needs undo to reconstruct the data version at a query's snapshot, yet the required undo has been overwritten or is no longer available.

Example:
1. Query A starts and needs to read an older snapshot.
2. Query A runs for a long time.
3. Other sessions continuously UPDATE/DELETE and generate heavy undo.
4. Old undo needed by Query A gets reused before Query A reads the corresponding blocks.
5. Query A cannot reconstruct the required version and raises `ORA-01555`.

### 10.2. Common Contributing Factors

- Long-running read queries.
- High-rate undo generation from DML.
- Small undo tablespace relative to the workload.
- Insufficient `UNDO_RETENTION` relative to query duration.
- Undo reused before the query needs to read it.
- Certain patterns processing cursors and committing inside loops can raise error likelihood in specific workloads.

Do not conclude `ORA-01555` is solely caused by "long query" or solely by "low `UNDO_RETENTION`." Correlate query duration, undo generation rate, tablespace capacity, actual tuned retention, and failure timing.

### 10.3. Troubleshooting Approach

1. Identify the failing SQL and timestamp of the error.
2. Measure query duration, data volume, and concurrent DML frequency.
3. Inspect undo tablespace sizing, `UNDO_RETENTION`, and autoextend capability.
4. Review undo history via monitoring views if privileged.
5. Reduce query duration or split work into pieces with suitable snapshots/logic.
6. Increase space or retention when resources and operational requirements permit.
7. Re-evaluate transaction patterns, especially committing inside cursor loops.

Not every long query causes `ORA-01555`. With sufficient undo space and proper retention, long queries can complete normally.

### 10.4. Do Not Fix by Committing Arbitrarily

Frequent commits inside a cursor-fetch loop are not a general solution for undo issues. Under certain processing patterns, continuous commits allow undo needed by a long-running cursor to be reused, increasing the risk of `ORA-01555`. Design transactions around business units of work—never commit merely to "free undo" without understanding the side effects.

### 10.5. Monitoring Undo

DBAs can inspect undo statistics:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

These columns help observe undo blocks generated, transaction counts, maximum query duration, tuned retention, and snapshot-too-old / space error counts. Column names and accessibility depend on version/privileges; check documentation for your running release.

## 11. Undo and Flashback Query

### 11.1. Reading Data at an Earlier SCN

Oracle can use undo for Flashback Query to query data as of a point in the past, within the bounds of retained undo data and feature prerequisites.

Syntax example:

```sql
SELECT account_id,
       balance
FROM   demo_mvcc_accounts
AS OF SCN :snapshot_scn
WHERE  account_id = 101;
```

`AS OF SCN` instructs Oracle to reconstruct the row version at the specified SCN. If required undo is no longer available, the flashback query may fail.

### 11.2. Flashback by Timestamp

```sql
SELECT account_id,
       balance
FROM   demo_mvcc_accounts
AS OF TIMESTAMP
       (SYSTIMESTAMP - INTERVAL '5' MINUTE)
WHERE  account_id = 101;
```

This example reads the version from roughly five minutes ago. Actual lookback range is subject to undo retention, timestamp-to-SCN mapping granularity, and configuration limits.

### 11.3. Flashback Does Not Replace Backups

Flashback Query is a way to read historical versions based on usable undo data. It does not replace backups, archived redo, Data Guard, or a disaster recovery strategy. When recovery over long intervals or after physical data loss is needed, use appropriate recovery solutions.

## 12. Real-World Scenarios and Choosing Isolation

### 12.1. OLTP Applications

A sales application typically uses READ COMMITTED:
- Each statement sees data committed as of statement start.
- Readers do not read uncommitted data.
- Short transactions minimize lock hold times.
- Competing DML on the same row may wait or fail depending on the scenario.

This is Oracle's default level and generally fits most transactional applications.

### 12.2. Reports Requiring Multiple SELECTs on the Same Snapshot

If a report runs multiple SELECTs and needs all of them to observe the exact same data state, READ COMMITTED may be insufficient because each statement gets its own snapshot.

Options to consider:
- A `READ ONLY` transaction.
- A `SERIALIZABLE` transaction if matching transaction semantics are also needed.
- Flashback Query with the same SCN across queries if the architecture fits.

Choose the approach based on report duration, undo retention, DML workload, and business requirements.

### 12.3. Checking Balances and Updating

If an application reads a balance and decides to debit funds, a standard SELECT holds no row locks. Another transaction could change the balance before the update. Use an appropriate transaction pattern, such as:
- Using an atomic conditional UPDATE like `WHERE balance >= :amount`.
- Or reading the row with `SELECT FOR UPDATE` and updating within the same transaction.
- Checking affected row counts and handling concurrency errors.

MVCC guarantees consistent reads, yet does not automatically turn an application's read-decide-write sequence into an atomic operation.

### 12.4. A Query Can Read While Data Is Being Updated

This is normal behavior in Oracle. The reader sees the committed version at its snapshot; the writer continues updating and committing. If the query needs an older version whose undo was reused before the query finishes, the query may hit `ORA-01555`.

Thus, read consistency depends on both the MVCC mechanism and maintaining undo for the necessary duration.

## 13. Common Errors and Misconceptions

| Misconception or Symptom | Explanation |
| --- | --- |
| SELECT sees the old value while another session is UPDATEing | Expected behavior: consistent read uses undo |
| SELECT does not wait for UPDATE | Readers generally do not need the writer's row lock |
| UPDATE waits for another UPDATE | Writers need locks on the same row |
| Second SELECT sees a new value in the same transaction | Can occur under READ COMMITTED because each statement gets a fresh snapshot |
| Long query raises ORA-01555 | Undo needed for the snapshot is no longer available |
| Undo disappears immediately after COMMIT | False; undo may still be needed for consistent read/flashback |
| UNDO_RETENTION is an absolute guarantee | False without retention guarantee and sufficient space |
| MVCC means blocking never occurs | False; FOR UPDATE, DML, DDL, and other resources can still wait |
| Undo and redo are the same | Undo serves rollback/consistent read; redo serves recovery |
| READ COMMITTED keeps the same snapshot for the whole transaction | False; snapshots are allocated per statement |

### 13.1. Distinguishing ORA-01555 and Lock Errors

- **ORA-01555:** required undo is no longer available to reconstruct the snapshot version.
- **Lock wait:** a session needs a lock currently held by another session.
- **ORA-08177:** a SERIALIZABLE transaction hit a conflict preventing continuation under serializable semantics.

These are three distinct problems. Expanding the undo tablespace will not resolve a held row lock; increasing lock timeouts will not restore overwritten undo; retrying a SERIALIZABLE transaction must be properly designed in the application layer.

### 13.2. COMMIT and ROLLBACK

- `COMMIT` confirms the transaction's changes, releases associated locks, and makes changes visible to statement snapshots starting after the commit.
- `ROLLBACK` undoes uncommitted changes using undo and releases locks.
- Another transaction does not see the current session's uncommitted changes.
- Undo for committed work may still be retained for consistent reads and flashback.

## 14. Checklist for Designing Transactions and Reports

Before deploying a multi-session workflow, determine:

1. **Business requirement:** is a consistent snapshot needed for one statement or an entire transaction?
2. **Isolation level:** READ COMMITTED, SERIALIZABLE, or READ ONLY?
3. **Duration:** how long can queries/transactions run?
4. **Undo workload:** how fast does DML generate undo?
5. **Retention:** is undo retained long enough for queries and flashback?
6. **Locking:** which operations need `SELECT FOR UPDATE` or conditional UPDATE?
7. **Conflicts:** how does the application handle row lock waits and `ORA-08177`?
8. **Commit boundaries:** are transactions scoped to sensible business units?
9. **Monitoring:** monitor undo tablespace, `V$UNDOSTAT`, and snapshot-too-old errors.
10. **Recovery:** do backups and redo logs meet recovery objectives?

Key guidelines:
- Keep transactions short when business rules permit.
- Avoid committing row-by-row inside cursor loops without clear justification.
- Do not use `FOR UPDATE` when only reading is needed.
- Never assume multiple READ COMMITTED statements share one snapshot.
- Never raise retention without evaluating undo space capacity.
- Never treat Flashback as a long-term backup.

## 15. Practice Exercises

### Exercise 1 — Observe Consistent Read

Create the `DEMO_MVCC_ACCOUNTS` table and data per Section 5. In Session A, UPDATE balance from 5000 to 4000 without committing. Run SELECT in Session B.

**Expected:** Session B sees 5000, not the uncommitted 4000.

### Exercise 2 — Observe Writer Blocking

While Session A has not committed, have Session B UPDATE the same `account_id`.

**Expected:** B waits on the lock held by A. Once A commits or rolls back, B proceeds depending on the state.

### Exercise 3 — Compare Statement Snapshots

Session B runs SELECT, then Session A UPDATEs and COMMITs, and then B runs SELECT again under READ COMMITTED.

**Expected:** the two SELECTs can return different values because each statement gets a new snapshot.

### Exercise 4 — Snapshot in a Long Cursor

Open a multi-row query in Session A and start fetching. While the cursor is still open, have Session B update and commit related rows.

**Expected:** A's cursor continues using the snapshot from when the statement opened; a new SELECT afterward can see B's committed changes.

### Exercise 5 — SERIALIZABLE

Start a transaction:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT balance
FROM demo_mvcc_accounts
WHERE account_id = 101;
```

Then have another session update and commit. Re-run SELECT in the serializable transaction.

**Expected:** the transaction continues seeing the transaction snapshot instead of a new per-statement snapshot. Try a conflicting update to observe `ORA-08177` in a test environment.

### Exercise 6 — READ ONLY

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM demo_mvcc_accounts;
SELECT SUM(balance) FROM demo_mvcc_accounts;
SELECT AVG(balance) FROM demo_mvcc_accounts;

COMMIT;
```

**Goal:** observe multiple statements reading from one transaction snapshot. Attempt DML inside the READ ONLY transaction to see the mode's restriction.

### Exercise 7 — Compare SELECT and SELECT FOR UPDATE

Run a standard SELECT and then `SELECT FOR UPDATE` on a row. Use another session to UPDATE the same row.

**Expected:** standard SELECT does not lock rows for reading; `SELECT FOR UPDATE` acquires locks and can block or wait.

### Exercise 8 — Inspect Undo Configuration

```sql
SELECT name, value
FROM v$parameter
WHERE name IN ('undo_management',
               'undo_tablespace',
               'undo_retention');
```

**Goal:** read undo parameters if the account is privileged. If not privileged, ask a DBA to provide the settings; never grant broad privileges just for an exercise.

### Exercise 9 — Inspect Undo Statistics

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

**Goal:** recognize undo usage, long queries, and snapshot-too-old errors. Output reflects instance monitoring metrics, not business table data.

### Exercise 10 — Flashback Query

Obtain an appropriate SCN from your test environment and run:

```sql
SELECT account_id, balance
FROM demo_mvcc_accounts AS OF SCN :snapshot_scn
WHERE account_id = 101;
```

**Goal:** read an older version if undo is still available and the account has required privileges.

### Exercise 11 — Distinguish Undo and Redo

Explain the role of undo during ROLLBACK and consistent read, then explain how redo is used during recovery.

### Exercise 12 — Diagnose ORA-01555

A report runs for 40 minutes on a large table while the system experiences heavy UPDATE transactions. List the data to collect before changing `UNDO_RETENTION` or undo tablespace size.

**Hint:** failing SQL, query duration, `V$UNDOSTAT`, undo tablespace, DML rate, tuned retention, guarantee setting, and expansion capacity.

## 16. Oracle Reference Documentation

- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): concurrency mechanisms, read consistency, and transactions.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo.html): undo records, undo segments, and how undo is used.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, undo retention, and undo tablespace configuration.
- [Oracle Database SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): READ ONLY and SERIALIZABLE isolation levels.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT, FOR UPDATE, and Flashback Query.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): performance monitoring and diagnosing database issues.

During concurrent reads and writes in Oracle, undo supplies the information to restore prior versions, MVCC enables readers to observe consistent data without waiting for every writer, and read consistency defines the snapshot visible to a statement or transaction. Distinguish statement-level snapshots in READ COMMITTED from transaction-level snapshots in SERIALIZABLE/READ ONLY, understand the role of write locks, and monitor undo retention to prevent snapshot-too-old errors.
