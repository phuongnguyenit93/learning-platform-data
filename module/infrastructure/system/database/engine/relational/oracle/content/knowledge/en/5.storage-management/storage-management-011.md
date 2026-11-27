# Undo Segments, Undo Retention, and Read Consistency Needs

## 1. The Problem: Why Can Others Still Read Data While It Is Being Modified?

Suppose a banking system has account `A001` with a confirmed balance of **1,000,000 VND**. One transaction begins updating the balance to 800,000 VND but **has not `COMMIT`ted yet**. At the same time, another transaction needs to display the balance to the customer.

Oracle Database must satisfy multiple simultaneous requirements:

- Prevent readers from seeing an **uncommitted** balance.
- Allow standard read queries to proceed without waiting every time another session is updating a row.
- When an update transaction fails or the user runs `ROLLBACK`, **restore the pre-change state**.
- When a `SELECT` query scans many rows over a long duration, returned rows must reflect **a single consistent view of the data**, even while other sessions continue updating.

That is why Oracle uses **undo**. Undo is not simply "a copy of the entire table before edits"; it is information about the changes needed to **reverse operations** or **reconstruct older versions of data** when needed.

In Oracle's **Storage** chapter, three concepts must be understood together:

1. **Undo segment**: storage structure containing undo records, organized inside an undo tablespace.
2. **Undo retention**: target duration Oracle tries to retain undo no longer needed for rollback so it can serve old-version reads and certain other features.
3. **Read consistency**: how Oracle uses transaction info and undo so a query sees data as of the appropriate point in time, avoiding uncommitted changes.

After this lesson, you should be able to explain what happens when `UPDATE`, `SELECT`, `COMMIT`, and `ROLLBACK` run concurrently; recognize why long queries can hit `ORA-01555`; and inspect undo-related parameters/objects.

## 2. What Is Undo and When Is It Generated?

**Undo data** is data used to reverse changes made by a transaction. When updating or deleting rows, Oracle saves the info needed to restore the pre-operation state. For inserts, undo info lets Oracle remove the newly inserted row if the transaction rolls back.

Example:

```sql
UPDATE accounts
SET balance = 800000
WHERE account_id = 'A001';
```

Suppose the row had `balance = 1000000` before this statement. Oracle generates undo info for the change so that if needed, the logical state can be returned to the previous value. This is a simplified explanation for learners: the actual format of an undo record depends on the operation and block structure, and is **not necessarily an intact copy of the entire row or table**.

### 2.1. Which Operations Involve Undo?

| Operation | Relationship to Undo |
|---|---|
| `INSERT` | Needs info to undo the inserted row if the transaction rolls back |
| `UPDATE` | Needs enough info to reverse the change performed |
| `DELETE` | Needs enough info to restore deleted data if rolled back |
| `ROLLBACK` | Uses undo info to reverse uncommitted changes |
| `SELECT` (standard) | **Uses undo when needed to reconstruct older versions**; read queries do not generate undo for read rows the way DML generates undo |
| `COMMIT` | Confirms the transaction; generated undo **does not necessarily vanish immediately** |
| Flashback Query | Can access older data versions based on still-available undo |

Example within a transaction:

```sql
SAVEPOINT before_change;

UPDATE accounts
SET balance = balance - 200000
WHERE account_id = 'A001';

ROLLBACK TO SAVEPOINT before_change;
```

`ROLLBACK TO SAVEPOINT` can undo changes made after the savepoint within the active transaction. A full `ROLLBACK` undoes all uncommitted changes in the transaction. **Once `COMMIT` succeeds, `ROLLBACK` cannot reverse that commit**; a compensating transaction or appropriate recovery procedure is required.

### 2.2. Undo Is Not Redo

Oracle uses both **undo** and **redo**, yet the two mechanisms serve different purposes:

| Component | Typical Role | When Needed |
|---|---|---|
| **Undo** | Reverse transaction changes; reconstruct older versions for consistent reads | `ROLLBACK`, reading data while another session modifies it |
| **Redo** | Record change info needed to recover the database after a failure | Recovering committed changes per recovery mechanics |
| **Backup** | Copies serving restore/recovery procedures | Recovering from lost files or damaged environments |

Never deduce that "having undo removes the need for redo/backups," or that "redo is a history table allowing applications to query old values directly." These are distinct components working together in Oracle's transaction and recovery architecture.

## 3. Where Is Undo Stored? Undo Tablespaces and Undo Segments

In typical environments using **Automatic Undo Management (AUM)**, Oracle automatically manages **undo segments** inside an **undo tablespace** configured for the corresponding instance/container.

Basic storage relationship:

```text
                  ORACLE DATABASE
                         |
                  UNDO TABLESPACE
                    UNDOTBS1
                         |
           +-------------+--------------+
           |                            |
       DATAFILE 1                   DATAFILE 2
           |                            |
       [data blocks]                [data blocks]
           ^                            ^
           |                            |
       Extent A                     Extent B
           \                            /
            \                          /
              UNDO SEGMENT (example)
                   |
                Undo records
                   |
          Change info serving
          rollback and consistent read
```

Just like other segments, an **undo segment** consists of **extents**, and each extent consists of Oracle data blocks residing in **one datafile**. One undo segment can have multiple extents, with actual organization/allocation managed by Oracle. Transactions use undo segments assigned by the database engine; never imagine each `UPDATE` creates its own datafile or dedicated undo segment.

### 3.1. Storage Layers to Distinguish

| Layer | Meaning for Undo |
|---|---|
| Undo tablespace | Logical space dedicated to holding undo segments |
| Undo tablespace datafile | Actual storage file holding blocks belonging to undo segments |
| Undo segment | Structure through which Oracle manages transactions' undo records |
| Undo extent | Group of blocks allocated to an undo segment |
| Undo block | Block inside an extent holding undo data/structures |
| Undo record | Info supporting rollback or reconstructing older data versions |

For example, a datafile of an undo tablespace on a filesystem might be configured as:

```text
/u02/oradata/LABDB/undotbs01.dbf
```

In **ASM** environments, paths may take forms like `+DATA/...` instead of Linux paths. An undo tablespace can use multiple datafiles depending on tablespace type and configuration. **Never read or edit undo blocks directly with a file editor**: all of this data is managed by Oracle.

### 3.2. AUM and Parameters to Recognize

| Parameter | Meaning |
|---|---|
| `UNDO_MANAGEMENT` | Undo management mode; `AUTO` means Automatic Undo Management |
| `UNDO_TABLESPACE` | Selected undo tablespace in the appropriate instance/container context |
| `UNDO_RETENTION` | Target duration (seconds) to retain committed undo subject to space and retention rules |

**Illustrative** configuration example:

```text
undo_management = AUTO
undo_tablespace = UNDOTBS1
undo_retention  = 900
```

`900` corresponds to **900 seconds = 15 minutes**. That **does not mean Oracle guarantees returning every data version for exactly 15 minutes**; you must account for **actual undo retention capacity**, retention policy, and query conditions.

In a multitenant architecture (CDB/PDB), using **local undo** or **shared undo** depending on version/configuration can make undo tablespace placement and scope differ. When querying admin views, always confirm whether you are connected to the **CDB root or a specific PDB** and which objects you are authorized to view.

## 4. How Does Undo Support Transaction Atomicity?

Consider a two-step money transfer transaction:

```text
BEGIN transaction (conceptually)
    |
    +--> UPDATE sender account: subtract 200,000
    |
    +--> UPDATE receiver account: add 200,000
    |
    +-- If either step fails: ROLLBACK
    |
    +-- If both succeed: COMMIT
```

Oracle records changes and sufficient undo info so that on rollback, affected rows return to their appropriate pre-transaction state. Upon `COMMIT`, transaction results are confirmed; Oracle **does not immediately erase the associated undo**, because queries that began before the commit time may still need to read older versions.

An **uncommitted** transaction holds undo needed for rollback capability. That undo is treated as **active undo** and cannot be arbitrarily overwritten to make room for another transaction. This differs from undo belonging to finished transactions.

**Atomicity** of updates within **a single Oracle transaction** does not automatically span systems outside the database, such as an HTTP request to a payment gateway. If an application combines Oracle updates with external service calls, design appropriate coordination such as idempotency/outbox/saga patterns.

## 5. Read Consistency: Which Version Is Read and as of When?

### 5.1. The Dirty Read Problem

Suppose two sessions connect:

```text
                  Session A                       Session B
-----------------------------------------------------------------
t0          balance = 1,000,000
t1          UPDATE balance = 800,000
            (NOT YET COMMITTED)
t2                                          SELECT balance?
t3          COMMIT or ROLLBACK
```

If Session B read `800,000` while A had not yet committed, B would see a value that **might never persist**: A could still roll back to `1,000,000`. That is a dirty read.

Oracle uses **multiversion read consistency** so a standard `SELECT` receives **the committed version matching its read point in time**. Here, B normally sees `1,000,000` at t2 without waiting for A to commit.

### 5.2. SCN and Consistent Read

Oracle uses the **System Change Number (SCN)** as a logical marker to manage change ordering and consistency. Under the `READ COMMITTED` isolation level, each SQL query is evaluated against a **statement-level consistent view of data**.

Simplified model:

1. A `SELECT` starts and receives an appropriate **snapshot SCN**.
2. Oracle needs to read a block that has changes newer than that snapshot, or contains data currently being modified by another transaction.
3. When needed, Oracle uses undo info to reconstruct a **consistent read (CR) version** of the block matching the view the query is allowed to see.
4. The query returns data from that consistent version instead of blindly reading the latest value sitting in the block.

```text
Current block
  ROW A balance=800,000 (uncommitted in A)
           |
           | needs version matching B's snapshot
           v
     Undo information
           |
           v
CR copy of block: ROW A balance=1,000,000
           |
           v
Session B receives value 1,000,000
```

Oracle reconstructs a **consistent block/row version for the read request** from change records and transaction states; the diagram illustrates only the concept, not every internal buffer-cache implementation detail.

### 5.3. A Long `SELECT` Still Sees Consistent Data

Suppose a report query starts at 10:00 and reads millions of records over 8 minutes. During those 8 minutes, many other transactions may update and commit data.

Under `READ COMMITTED`, rows within **the same `SELECT`** must reflect the state consistent with **that statement's snapshot**, rather than each row arbitrarily shifting as of when it happens to be read. If a block was updated after the snapshot, Oracle uses available undo to build the corresponding version.

This is vital for reports: if an order-table sum read pre-commit data while another part of the **same statement** read post-commit details, results would contradict themselves. Statement-level consistency prevents that within Oracle's guarantees.

### 5.4. Statement-Level vs. Transaction-Level Consistency

Oracle supports several transaction isolation levels:

| Level / Mode | Common Read View | What to Remember |
|---|---|---|
| `READ COMMITTED` | Each statement gets its own snapshot (Oracle's common default) | Two consecutive `SELECT`s in one transaction can return different results if another session commits in between |
| `SERIALIZABLE` | Queries inside the transaction aim for a transaction-level consistent snapshot | When update conflicts cannot be serialized per Oracle's mechanism, `ORA-08177` may occur |
| `READ ONLY` transaction | Queries see a transaction-level consistent snapshot | This transaction cannot be used for standard data modifications |

Example starting a read-only transaction in SQL*Plus:

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM user_tables;
SELECT COUNT(*) FROM user_objects;

COMMIT;
```

`SET TRANSACTION` must be issued right at the start of the transaction per Oracle rules. `READ ONLY` is helpful when multiple queries need a unified snapshot, though for long transactions it can increase undo retention demand.

**Do not confuse snapshot consistency with locks:** a normal Oracle `SELECT` does not place row locks like `SELECT ... FOR UPDATE`. `SELECT ... FOR UPDATE` actively requests locks and can block if rows are locked by another transaction. Those two SQL statements serve different goals.

## 6. Hands-On Example with Two SQL*Plus/SQLcl Sessions

This example uses **two sessions logged into the same practice schema**. You need permission to create tables and manipulate data in that schema. Never use real business tables. In SQL*Plus, set `SET AUTOCOMMIT OFF` to ensure update steps do not auto-commit; some GUI tools/drivers manage autocommit differently.

### Step 1. Create Sample Data in Session A

```sql
SET AUTOCOMMIT OFF

CREATE TABLE undo_lab_accounts (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL
);

INSERT INTO undo_lab_accounts (account_id, balance)
VALUES (1, 1000);

COMMIT;
```

`CREATE TABLE` is DDL and performs an implicit commit per Oracle rules. After `COMMIT`, row `account_id = 1` with `balance = 1000` is confirmed.

### Step 2. Session A Updates Without Committing

```sql
UPDATE undo_lab_accounts
SET balance = 800
WHERE account_id = 1;

-- Neither COMMIT nor ROLLBACK yet.
```

Within Session A, querying this row again shows **the change made by Session A itself**:

```sql
SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Expected result in Session A is `800`.

### Step 3. Session B Reads While A Has Not Committed

Open a second terminal/worksheet connected to the same database and schema:

```sql
SET AUTOCOMMIT OFF

SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Expected result in **Session B** is `1000`. B does not see `800` because it is an uncommitted change in A. Normal reads use an undo-based consistent version instead of waiting on A.

### Step 4. Session A Rolls Back

Back in A:

```sql
ROLLBACK;

SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Expected result is `1000`. Running `SELECT` again in B also shows `1000`.

### Step 5. Test Committing Then Reading Again in B

In A:

```sql
UPDATE undo_lab_accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
```

In B, when executing **a new `SELECT` statement** under `READ COMMITTED`:

```sql
SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Expected result is `900`. This time B sees the committed value because the new query's snapshot is taken after the commit.

### Step 6. Clean Up Practice Data

Perform this only after confirming the table name you created in the practice schema and that no session still uses it:

```sql
DROP TABLE undo_lab_accounts PURGE;
```

`DROP TABLE ... PURGE` drops the object without placing it in the recycle bin per corresponding rules; this is destructive DDL with an implicit commit. Never run it if the table contains data that must be kept.

### What the Practice Exercise Demonstrates

```text
TIME    SESSION A                         SESSION B
----    ------------------------------    -----------------------
t0      COMMIT balance=1000
t1      UPDATE balance=800
        (uncommitted)
t2                                        SELECT -> 1000
t3      ROLLBACK
t4                                        SELECT -> 1000
t5      UPDATE balance=900; COMMIT
t6                                        SELECT -> 900
```

In practice, you do not necessarily observe Oracle reading undo directly on every `SELECT`; the observable behavior is **isolation of uncommitted data** and **updated statement snapshots after commit**.

## 7. Undo After Commit: ACTIVE, UNEXPIRED, EXPIRED

Undo for a running transaction must persist for rollback and consistency. Once a transaction commits, its undo may still be needed for queries that started before the commit or for historical-data features.

Undo extent statuses can typically be observed via `DBA_UNDO_EXTENTS`:

| Status | General Meaning | Reusability |
|---|---|---|
| **`ACTIVE`** | Holds undo needed for an active transaction | Must not be overwritten arbitrarily, as it is needed for rollback |
| **`UNEXPIRED`** | Holds committed undo still within the managed retention window | Oracle tries to keep it; can be reused under space pressure unless retention guarantee is enabled |
| **`EXPIRED`** | Undo past the retention window under current policy | Can be reused to record new undo |

Simplified lifecycle diagram:

```text
Transaction executing UPDATE/DELETE
              |
              v
       ACTIVE undo extent
              |
          COMMIT / finish
              |
              v
      UNEXPIRED undo extent
         (still retained)
              |
       retention period elapses
              |
              v
       EXPIRED undo extent
              |
              v
  Reusable for new undo writes
```

These statuses are an **extent-level** view in the dictionary; the actual lifecycle also depends on undo records, transactions, usage patterns, and allocation/reuse mechanics. Never think a single commit immediately turns the entire undo tablespace into `EXPIRED`.

## 8. `UNDO_RETENTION`: A Retention Goal, Not a Deletion Timer

The `UNDO_RETENTION` parameter is specified in **seconds**. For example:

```text
UNDO_RETENTION = 900  --> 15 minutes
```

Meaning: this is a **target duration** to retain committed undo to support long queries and features requiring older data versions. However, actual achievable retention depends on undo tablespace size, `AUTOEXTEND` settings, DML volume, Oracle's retention tuning, and **retention guarantee** mode.

### 8.1. Why `UNDO_RETENTION = 900` Does Not Guarantee 15 Minutes

Suppose:

1. A report query runs for 12 minutes.
2. Other transactions are writing heavily, generating massive undo.
3. The undo tablespace is small and can no longer expand.
4. Extents holding committed undo needed by the query become eligible for reuse under a non-guaranteed policy.

If older undo needed for a consistent read gets overwritten before the query reaches it, the report can fail with **`ORA-01555: snapshot too old`**, even though `UNDO_RETENTION` is set to 900 seconds.

**A configured retention value does not substitute for provisioning sufficient undo space.** Open transactions, long queries, and heavy concurrent DML all contribute to actual capacity demand.

### 8.2. Undo Retention Tuning

In Automatic Undo Management mode, Oracle can **adjust undo retention duration based on usage and available space**. `V$UNDOSTAT` provides interval statistics, including `TUNED_UNDORETENTION` on versions supporting that column.

Distinguish between:

- **`UNDO_RETENTION`**: administrator-configured parameter, usually acting as a target/minimum goal under the active mechanism.
- **`TUNED_UNDORETENTION`**: retention duration Oracle tuned/recorded during the stats interval, not a promise that every Flashback Query will find data across that whole span.
- **Actual historical query success**: depends on whether needed undo records still exist, whether schema changes occurred, privileges, and other conditions.

Seeing a high `TUNED_UNDORETENTION` number at one point does not mean you can assume full history remains queryable at arbitrary future times.

### 8.3. Retention Guarantee and Trade-offs

An undo tablespace can be configured with **`RETENTION GUARANTEE`**:

- When **guarantee** is enabled, Oracle protects **unexpired undo** from being overwritten merely to make room for new DML.
- If space runs short, **new DML transactions can fail** because additional undo cannot be allocated.
- Without guarantee, Oracle can reuse **unexpired undo** under space pressure, exposing older-version queries to `ORA-01555`.

Administrative syntax example—**never run arbitrarily in a live environment**:

```sql
-- Illustrative DBA command only; must weigh risk of running out of undo space.
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;

-- Return to standard mode when appropriate:
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
```

This configuration change affects the database's ability to accept writes. `RETENTION GUARANTEE` helps preserve older data per policy, yet **does not create extra storage space** and does not guarantee data access beyond the retention window or across incompatible structural changes.

### 8.4. How Should Undo Size Be Balanced?

There is no single size fitting every application. Key factors are:

- DML rate and pattern: wide-row updates, deletes, bulk loads, batch jobs.
- Number of concurrent transactions and how long transactions stay open.
- Duration `SELECT` queries or reports must hold snapshots.
- How long Flashback features need older versions retained.
- Autoextend capability, datafile limits, and filesystem/ASM resources.
- `V$UNDOSTAT` metrics, `ORA-01555` alerts, and undo allocation failures.

Rough throughput-based estimate:

```text
Required undo capacity (estimate)
  ≈ undo generation rate during peak load
    × duration old versions must be retained
    + buffer for spikes and active transactions
```

For example, if the workload generates an average of roughly **1 MB of undo per second** during a peak window and needs roughly **15 minutes** of retention, that portion alone is about **900 MB** before adding buffer and checking real limits. This is only **a way of thinking about sizing**; real capacity planning requires measuring actual workloads and using Oracle advisor/monitoring tools.

## 9. `ORA-01555: snapshot too old` and Read Consistency Needs

**`ORA-01555`** typically occurs when Oracle needs to reconstruct an older version for a query, yet the relevant undo info **is no longer available**. The classic scenario is a long-running `SELECT` while the system processes heavy DML and undo has to be reused.

### 9.1. Illustrative Timeline

```text
Time
 |
 t0  Query Q starts -> snapshot SCN = S
 |
 t1  Transaction T updates many blocks
 |
 t2  T COMMITs; T's undo could help Q read data as of S
 |
 t3  Other DML generates heavy undo; tablespace runs short on space
 |
 t4  Old undo needed by Q gets reused per retention policy
 |
 t5  Q reaches a modified block and needs undo from t2
 |
 t6  Cannot reconstruct block as of SCN S -> ORA-01555
```

An important point: **the failure does not necessarily trigger at the moment undo is overwritten**—the error surfaces only when the query actually reaches that block and needs the missing undo to complete its consistent read.

### 9.2. Causes to Examine

| Situation | Why It Relates to `ORA-01555` |
|---|---|
| Very long-running read query | The older the snapshot, the more committed undo versions it may require |
| Heavy concurrent DML with small undo space | New undo forces old undo to be reused before the query finishes |
| Aggressive batch update/delete jobs | Undo generation spikes sharply beyond normal sizing |
| Long-lived transactions/cursors with poor fetch/commit patterns | Can strain old-version retention and break long-running cursors |
| Insufficient peak-load visibility | Sizing works during normal hours yet fails during peak intervals |

Oracle also has other technical scenarios involving consistent reads and transaction handling; therefore, **never conclude every `ORA-01555` is simply a shortage of megabytes in the undo tablespace**. Inspect the SQL, runtime, DML volume, undo settings, and specific logs.

### 9.3. Appropriate Remediation Steps

1. **Identify the failing SQL** and its execution duration, especially reports reading huge datasets or holding cursors open long.
2. **Inspect actual undo metrics** at the time of the error: `V$UNDOSTAT`, undo datafile sizes, extent statuses, `MAXQUERYLEN`, `SSOLDERRCNT`, `NOSPACEERRCNT`.
3. **Shorten queries where possible** via index design, tighter filtering, better execution plans, or splitting work without breaking snapshot requirements.
4. **Provision adequate undo space and autoextend policy** when evidence shows space shortage; mind real physical storage limits.
5. **Review transaction duration and commit patterns**. Committing overly frequently inside loops/cursors is not a universal fix for undo issues and can make consistent views harder to maintain.
6. **Enable retention guarantee only after evaluating trade-offs** against the risk of DML failing due to inability to allocate undo.

If a report requires a single snapshot across multiple SQL statements, consider a `READ ONLY` transaction or an appropriate data-snapshotting approach. Keeping snapshots longer generally **increases undo demand**, so coordinate it with capacity planning.

### 9.4. Distinguishing from Undo Out-of-Space Error `ORA-30036`

An error such as:

```text
ORA-30036: unable to extend segment ... in undo tablespace ...
```

indicates Oracle cannot allocate additional space needed for an undo segment under the current configuration. Causes include: undo tablespace out of allocatable space, datafile unable to extend, active undo cannot be overwritten, or retention guarantee protecting unexpired undo.

Two distinct symptoms:

- **`ORA-01555`**: a query **lacks older undo needed for a consistent read**.
- **`ORA-30036`**: an operation **cannot allocate new undo** under current storage/policy constraints.

Raising retention or enabling guarantee can help one side while worsening **write space exhaustion for DML** if capacity is insufficient. Watch both error types and peak system loads together.

## 10. Undo and Flashback Query

Oracle lets certain queries read data as of an earlier point in time via **Flashback Query** (`AS OF TIMESTAMP` or `AS OF SCN`), provided the mechanism and required data remain available.

**Illustrative** example on table `ACCOUNTS` that has existed steadily since before the queried timestamp (requires appropriate privileges):

```sql
SELECT account_id, balance
FROM accounts AS OF TIMESTAMP
     (SYSTIMESTAMP - INTERVAL '5' MINUTE)
WHERE account_id = 'A001';
```

Meaning: asks Oracle to construct the table's view roughly 5 minutes before the current time. This SQL statement is **not guaranteed to always succeed**:

- Needed undo may already have been reused.
- The table might not have existed then or may have undergone DDL limiting flashback.
- Appropriate environment privileges and features are required.

Flashback Query is not a permanent full-history storage system. It also differs from database backup/recovery and from Flashback Database / Flashback Data Archive, which have their own purposes, storage mechanisms, and prerequisites.

## 11. Observing Undo in a Practice Environment

The following are **read-only** commands. `V$...` views are dynamic performance views and `DBA_...` views are dictionary views; application accounts normally lack privileges to query them. If you hit privilege errors, use an authorized monitoring/DBA account—**never expand production application account privileges**.

### 11.1. Viewing Active Undo Parameters

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
)
ORDER BY name;
```

In SQL*Plus, you can use client commands:

```sql
SHOW PARAMETER undo_management
SHOW PARAMETER undo_tablespace
SHOW PARAMETER undo_retention
```

Interpret results in the context of your connected instance/PDB. `SHOW PARAMETER` is a SQL*Plus/SQLcl client command, not pure SQL to embed directly in JDBC.

### 11.2. Viewing Undo Tablespaces and Retention Mode

```sql
SELECT tablespace_name,
       contents,
       status,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO'
ORDER BY tablespace_name;
```

`RETENTION` shows modes like `GUARANTEE` or `NOGUARANTEE`; do not confuse it with the `UNDO_RETENTION` time parameter (in seconds).

Inspect datafiles of undo tablespaces:

```sql
SELECT f.tablespace_name,
       f.file_name,
       ROUND(f.bytes / 1024 / 1024, 2) AS size_mb,
       f.autoextensible,
       ROUND(f.maxbytes / 1024 / 1024, 2) AS max_mb
FROM dba_data_files f
JOIN dba_tablespaces t
  ON t.tablespace_name = f.tablespace_name
WHERE t.contents = 'UNDO'
ORDER BY f.tablespace_name, f.file_name;
```

`MAXBYTES` is the value recorded by Oracle in the view, not an indicator of total remaining real storage. On ASM/OMF systems, `FILE_NAME` may be an Oracle-managed name.

### 11.3. Viewing ACTIVE, UNEXPIRED, and EXPIRED Extents

```sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
```

The output is a snapshot of extent statuses at query time. A light-DML environment may show many `EXPIRED` extents; a high-load environment may show larger `ACTIVE`/`UNEXPIRED` totals. **Never use these numbers to justify deleting undo files**: extents are managed automatically by Oracle.

### 11.4. Viewing Undo Usage History and Retention Pressure Signs

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt,
       tuned_undoretention
FROM v$undostat
WHERE begin_time >= SYSDATE - 1
ORDER BY begin_time DESC;
```

Meaning of key columns:

| `V$UNDOSTAT` Column | Common Meaning |
|---|---|
| `BEGIN_TIME`, `END_TIME` | Statistical time interval |
| `UNDOBLKS` | Number of undo blocks consumed during the interval |
| `TXNCOUNT` | Number of transactions recorded during the interval |
| `MAXQUERYLEN` | Longest duration of a tracked query in the interval, in seconds |
| `SSOLDERRCNT` | Count of snapshot too old (`ORA-01555`) errors recorded in the interval |
| `NOSPACEERRCNT` | Count of insufficient undo space occurrences per statistics |
| `TUNED_UNDORETENTION` | Oracle-tuned retention window, in seconds |

`V$UNDOSTAT` intervals are usually roughly **10 minutes**; history depth and aggregation depend on version. `MAXQUERYLEN` reflects statistics of queries tracked by Oracle, **not an absolute guarantee that every application query was measured identically**.

If `SSOLDERRCNT` rises during an error window, that is a key clue for investigating `ORA-01555`. If `NOSPACEERRCNT` rises, check ability to allocate new undo. Read metrics alongside workload and configuration to pinpoint root causes accurately.

### 11.5. Viewing Transactions Using Heavy Undo

With appropriate query privileges:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
```

`USED_UBLK` and `USED_UREC` relate to undo blocks/records used by active transactions; they do not mean "a session using lots of undo is automatically an error." A large data-loading batch can be completely legitimate. Check transaction runtime, business task, and resource status before intervening.

## 12. Scenarios Easily Misunderstood in Application Systems

### Scenario A: "Once `COMMIT` finishes, is undo deleted?"

**No.** Committing removes rollback need for the committed transaction, yet pre-commit versions may still be needed by an earlier-started `SELECT` or Flashback Query. Undo can stay retained and later be reused per retention policy.

### Scenario B: "Does raising `UNDO_RETENTION` fix every `ORA-01555`?"

**No.** If the undo tablespace lacks space or cannot expand, setting a higher retention target does not create new files/space. Inspect DML load, query duration, datafile settings, dynamic views, and actual errors.

### Scenario C: "Is `SELECT` always blocked if an `UPDATE` holds a row lock?"

A normal `SELECT` in Oracle can use a consistent version and does not have to wait for `UPDATE` to commit in standard cases. However, `SELECT ... FOR UPDATE` seeks to lock rows and thus may wait; DDL and specialized locking scenarios also follow their own rules. Do not treat all read forms as identical.

### Scenario D: "I am in `READ COMMITTED`—why did two `SELECT`s in the same transaction return different results?"

Because `READ COMMITTED` provides **statement-level read consistency**. Each new `SELECT` can obtain a new snapshot. If multiple queries must share one snapshot within an appropriate scope, explore `READ ONLY` or `SERIALIZABLE` transactions and evaluate business requirements.

### Scenario E: "Does enabling retention guarantee make the database more stable?"

Not always. Guarantee prioritizes **preserving unexpired undo**, which can leave new transactions with nowhere to write and cause failures when space is tight. Deciding to use guarantee must weigh the importance of old-version reads against DML availability.

### Scenario F: "The undo tablespace is full—should I delete the `.dbf` file to free space?"

**Never.** Undo datafiles are Oracle-managed database components; manually deleting/editing files risks corrupting the database or preventing startup. DBAs use supported Oracle mechanisms for space management and recovery.

### Scenario G: "My Java app already uses `@Transactional`—do I no longer need to know about undo?"

`@Transactional` helps the application define transaction boundaries when configured properly, while Oracle still uses undo for rollback and consistent reads. Long-running transactions, large batch DML, or heavy concurrency still consume undo; frameworks do not automatically solve retention or sizing issues.

## 13. Designing Applications with Undo and Read Consistency in Mind

### 13.1. Keep Transactions Concise

In a Java backend, keep database reads/writes requiring atomicity inside short, clear transactions. Avoid opening a transaction and then waiting on user input, calling slow HTTP services, or running long CPU tasks if those steps do not belong inside the same transaction boundary.

Long-open transactions hold locks and active undo longer, increasing resource pressure. However, **never split a business transaction that must remain atomic into arbitrary smaller commits** just to reduce undo: that can break business consistency.

### 13.2. Understand Snapshots When Reading Reports

A single aggregate SQL query reads data under one statement-level snapshot. If a report requires multiple tightly coupled queries, decide whether a transaction-level snapshot is needed. When holding longer snapshots, budget undo space for the corresponding read window.

Splitting one large query into many smaller queries can shorten each statement, yet can also cause statements to see **different snapshots**. Evaluate that trade-off against reporting requirements.

### 13.3. Monitor Real Workloads Before Changing Parameters

As system load increases, monitor simultaneously:

- `V$UNDOSTAT` during peak windows.
- Query durations and how long transactions stay open.
- `ORA-01555` and `ORA-30036` errors.
- Undo tablespace size/autoextend and real underlying storage capacity.
- Batch update/delete jobs, report schedules, and peak-load windows.

Raising `UNDO_RETENTION` alone or resizing files alone while queries/reports stay overly slow may miss the root cause. Combining query tuning, transaction design, and undo sizing is the sustainable approach.

## 14. Self-Check Questions

**Question 1.** Session A updates a row without `COMMIT`ting. Session B runs a standard `SELECT` under `READ COMMITTED`. Does B see the uncommitted new value?

**Answer:** No. B reads a consistent data version matching the statement's snapshot, reconstructed using undo if needed.

**Question 2.** Session A commits. Is A's undo immediately deleted?

**Answer:** Not necessarily. Committed undo can be retained for older-snapshot queries and Flashback Query, then reused per retention rules.

**Question 3.** Does `UNDO_RETENTION = 1800` mean all historical data is guaranteed queryable for 30 minutes?

**Answer:** No. It is a target duration (seconds), while actual retention depends on undo capacity, guarantee policy, workload, operation type, and Flashback Query conditions.

**Question 4.** How do `ORA-01555` and `ORA-30036` differ?

**Answer:** `ORA-01555` involves missing older undo needed to reconstruct a consistent-read version; `ORA-30036` involves being unable to allocate new space for an undo segment.

**Question 5.** If a `SELECT` runs for 20 minutes while many other transactions commit, can rows near the end of the query reflect a different snapshot from rows at the start?

**Answer:** Oracle enforces statement-level read consistency as of the query's snapshot; if older versions cannot be rebuilt because undo is gone, the query fails with an error rather than silently mixing data from different times.

**Question 6.** Can `UNEXPIRED` undo be overwritten in `NOGUARANTEE` mode?

**Answer:** Yes, when Oracle needs space for new undo under space-management policies. Enabling `GUARANTEE` shifts the trade-off: preserving unexpired undo at the risk of new DML running out of space.

**Question 7.** Is a `SERIALIZABLE` transaction a free solution to keep reports always consistent?

**Answer:** No. It changes snapshot/conflict handling and can prolong old-version read requirements; you must weigh write activity, transaction duration, undo resources, and potential serialization conflict errors.

## 15. Conclusion

**Undo segments** are where Oracle organizes information required for **rollback** and **reconstructing older data versions**. Undo records reside in segments within the undo tablespace, structured into extents and data blocks managed automatically by Oracle.

**Read consistency** allows standard `SELECT` queries to see data states matching their snapshots, even while other transactions modify the same tables. Under `READ COMMITTED`, snapshots are typically bound to **each statement**; a long-running query may rely heavily on undo to preserve that view.

**Undo retention** sets a target duration for retaining committed undo, yet actual effectiveness depends on DML volume, query runtime, undo tablespace size/expansion capability, and retention guarantee mode. Consequently, resolving `ORA-01555` or `ORA-30036` requires examining **both consistent-read demand and space allocation capacity**, rather than tweaking a single parameter.
