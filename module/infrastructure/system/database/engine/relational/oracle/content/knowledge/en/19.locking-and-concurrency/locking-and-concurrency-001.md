# Row Locks, Table Locks, Enqueues, and Latches/Mutexes in Oracle Database

When multiple sessions concurrently read and update data, Oracle Database must coordinate access to prevent unintended overwrites, preserve consistency, and protect internal structures. Oracle uses several different synchronization mechanisms. Among them, it is important to clearly distinguish:

- **Row lock:** protects a single row of data modified or explicitly locked by a transaction.
- **Table lock:** coordinates table-level operations; DML automatically acquires a table lock in a mode that allows multiple sessions to modify different rows concurrently.
- **Enqueue:** a queued locking mechanism used to coordinate access to resources such as a transaction (`TX`) or a table (`TM`).
- **Latch and mutex:** internal synchronization mechanisms that protect structures in Oracle's shared memory, such as the shared pool, library cache, or buffer cache.

These concepts are related, but they are not interchangeable. A session waiting on `enq: TX - row lock contention` is usually waiting for another transaction to release a lock on data; a session waiting on a latch or mutex is usually waiting for access to an internal structure in the SGA. `COMMIT` can release a row lock, but it is not a universal fix for every type of contention.

## 1. Why does a database need locks and synchronization mechanisms?

Suppose two sessions concurrently update an account balance:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
```

If both transactions read the same old value and overwrite each other without coordination, one update can lose the result of the other. This class of problem is commonly called a *lost update*.

Oracle uses locks to coordinate conflicting write operations. When a transaction modifies a row, that transaction holds a row lock until it commits or rolls back. Another transaction wanting to modify the same row must wait for the lock-holding transaction to finish, unless a different application strategy is used.

Beyond table data, Oracle also has internal structures in the SGA accessed concurrently by many processes. These structures require short-lived synchronization mechanisms such as latches and mutexes. Their purpose is to protect shared memory, not to lock a business row.

```text
                 Multiple sessions/processes
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Data access               SGA access
             |                       |
             v                       v
      Row lock / TM lock        Latch / Mutex
         via enqueue       internal synchronization
             |                       |
             v                       v
     Protect rows/tables   Protect memory structures
```

## 2. Row locks: locking at the data-row level

A **row lock** is the lock Oracle uses to protect rows that are modified or explicitly locked within a transaction. DML operations such as `UPDATE` and `DELETE` lock the affected rows; `SELECT ... FOR UPDATE` requests row locks so an application can read and then update in a controlled manner.

### 2.1. UPDATE locks the updated rows

```sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 101;
```

Oracle locks the employee row with `EMPLOYEE_ID = 101` in the current transaction. Another session attempting to update or lock the same row must wait if the lock is held. Other sessions can still update different rows in the same table.

### 2.2. DELETE locks the deleted row

```sql
DELETE FROM employees
WHERE employee_id = 101;
```

The deleted row is locked until the transaction ends. Before commit, other transactions cannot treat the uncommitted delete as a confirmed change; Oracle uses read consistency to serve queries.

### 2.3. INSERT and row locks

When inserting a new row, the transaction owns that uncommitted change. Other sessions do not see the new row through normal queries until the insert is committed. If another transaction attempts to insert the same unique key created by the first transaction while it is still uncommitted, it may have to wait for the first transaction to finish to determine whether a unique constraint violation occurs.

Therefore, waiting on a `TX` enqueue is not always just two sessions running `UPDATE` on the same existing row. The TX enqueue also participates in coordinating several other transaction contention scenarios, such as unique key conflicts.

### 2.4. Row locks are held until COMMIT or ROLLBACK

```sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 101;

-- The row lock is still held here.

COMMIT;
-- Or ROLLBACK;
```

Row locks are released when the transaction commits or rolls back. Simply finishing statement execution is not enough to release a row lock if the transaction remains open.

### 2.5. Regular SELECT does not lock rows

In Oracle, a regular `SELECT` query uses read consistency and does not automatically acquire row locks to block other sessions from updating data.

```sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 101;
```

This query does not lock the employee row. Another session can update the row while the current session is reading; Oracle provides a version of the data consistent as of the query's read point in time.

If the application needs to read a row and reserve priority to update that row, it can use `SELECT ... FOR UPDATE`.

## 3. SELECT FOR UPDATE: reading and explicitly locking rows

`SELECT ... FOR UPDATE` locks the selected rows so the current session can process them before the transaction ends.

```sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 101
FOR UPDATE;
```

The session holds locks on the selected rows until `COMMIT` or `ROLLBACK`. Another session wishing to update or acquire `FOR UPDATE` on the same row must wait or apply an appropriate wait option.

### 3.1. Reading and then updating within the same transaction

For example, an application wants to read an order's status, validate it, and then transition the status:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

COMMIT;
```

The lock is held between the `SELECT FOR UPDATE` statement and the `UPDATE` statement, so another transaction cannot concurrently modify the same row in a conflicting way. If business validation fails, roll back to release the lock.

### 3.2. OF specifies which table is locked in a join query

In a multi-table query, the `OF` clause can specify a column belonging to the table that should be locked:

```sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 9001
FOR UPDATE OF o.status;
```

`OF o.status` identifies the `ORDERS` table as the table to lock; it **does not mean only the STATUS column is locked**. A row lock protects rows of the specified table, not individual columns. If `OF` is omitted, Oracle may lock rows from the lockable tables in the query according to `FOR UPDATE` rules.

### 3.3. NOWAIT: do not wait for the lock

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE NOWAIT;
```

If the row is already locked by another session, the statement does not wait and immediately returns an error (typically `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`). The application can ask the user to retry or handle it according to business logic.

### 3.4. WAIT n: wait up to a specified duration

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE WAIT 5;
```

The session waits up to 5 seconds to acquire the lock. If the time expires and the resource is still busy, Oracle returns a timeout error. The number of seconds should be chosen based on SLA and application processing time; do not set it so long that requests hold connections without making progress.

### 3.5. SKIP LOCKED: skip rows that are already locked

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` skips rows currently locked by other transactions and continues looking for other rows it can lock. This is a useful pattern for multiple workers pulling tasks from a queue, because a worker can process another job instead of waiting on one held by another worker.

Applications typically perform the following within the same transaction:

1. Select one or a batch of `READY` jobs using `FOR UPDATE SKIP LOCKED`.
2. Update the job status to `RUNNING` or record which worker claimed the job.
3. Commit to confirm claiming the job.
4. Process the job using an appropriate mechanism; upon completion, update the status in a separate transaction.

`SKIP LOCKED` does not by itself guarantee exactly-once job processing in all situations. Status tracking, leases/timeouts, retries, and idempotency are needed to recover when a worker dies after claiming a job.

### 3.6. Limitations of FOR UPDATE

Not every `SELECT` statement can add `FOR UPDATE`. Oracle imposes restrictions on queries with `DISTINCT`, group functions, `GROUP BY`, set operators, and certain types of views/subqueries. When you need to lock input data for an aggregation, clearly identify the source table/rows and run an appropriate locking query instead of adding `FOR UPDATE` to an unsupported aggregate query.

## 4. Table locks: locking at the table level

Oracle uses a **table lock** to coordinate operations that require access at the table object level. A table lock does not mean that all rows in the table are locked against all access. Several modes allow multiple sessions to read and perform DML on different rows concurrently.

### 4.1. DML automatically acquires a Row Exclusive table lock

When a session performs DML such as `INSERT`, `UPDATE`, `DELETE`, or `MERGE`, Oracle typically automatically acquires a table lock in **Row Exclusive (RX)** mode on the modified table, along with the necessary row locks.

```sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 101;
```

While the transaction remains open:

- The session holds an RX table lock on `EMPLOYEES`.
- Employee row 101 is locked at the row level.
- Other sessions can still perform DML on other rows of the table.
- Another session may be blocked if it requests a table lock in a mode that conflicts with RX, such as `LOCK TABLE ... IN SHARE MODE`.

### 4.2. Oracle does not automatically escalate many row locks into an exclusive table lock

Oracle does not perform lock escalation in the sense of automatically converting thousands of row locks into a single exclusive table lock just because a transaction updates many rows. DML continues to use a table-level DML lock in the appropriate mode and row locks on the affected rows.

This allows other transactions to keep updating non-conflicting rows, even when one transaction modifies many rows in the same table. Even so, a transaction updating too many rows can still generate heavy undo/redo, hold many locks, and cause other sessions to wait on specific rows.

## 5. Five table lock modes in Oracle

Oracle provides five table lock modes commonly described as follows:

| Mode | Abbreviation | Mode in V$LOCK | General Meaning |
|---|---|---:|---|
| Row Share | RS | 2 | Allows concurrent access; typically acquired by `SELECT FOR UPDATE` |
| Row Exclusive | RX | 3 | Allows multiple concurrent DML transactions on different rows; DML acquires this mode automatically |
| Share | S | 4 | Allows concurrent queries but restricts DML from other transactions |
| Share Row Exclusive | SRX | 5 | Allows reads; restricts other transactions from acquiring conflicting DML/share modes |
| Exclusive | X | 6 | Strongest table lock; prevents other incompatible table locks |

`V$LOCK.LMODE` and `V$LOCK.REQUEST` use numeric mode values. A value of 0 indicates no mode held/requested; values 2–6 correspond to the modes above.

### 5.1. General compatibility

The table below shows the basic compatibility among Oracle's table lock modes. `Y` means they can coexist; `N` means they conflict. Mode 1 is Null lock, which is compatible with every mode.

| Held Mode \ Requested Mode | Null (1) | RS (2) | RX (3) | S (4) | SRX (5) | X (6) |
|---|---:|---:|---:|---:|---:|---:|
| Null (1) | Y | Y | Y | Y | Y | Y |
| RS (2) | Y | Y | Y | Y | Y | N |
| RX (3) | Y | Y | Y | N | N | N |
| S (4) | Y | Y | N | Y | N | N |
| SRX (5) | Y | Y | N | N | N | N |
| X (6) | Y | N | N | N | N | N |

Use this matrix as a tool to understand table lock conflicts, without assuming every row lock conflicts with every table lock. Row-level locks and table-level locks serve different roles.

### 5.2. Row Share (RS)

RS allows queries and high concurrency, while preventing another session from acquiring an incompatible exclusive table lock. `SELECT ... FOR UPDATE` typically acquires an RS table lock along with row locks on the selected rows.

### 5.3. Row Exclusive (RX)

RX is the mode automatically acquired by DML. Multiple transactions can hold RX on a table at the same time; actual conflicts on the same row are resolved by row locks / TX enqueues.

### 5.4. Share (S)

A Share lock allows other sessions to read the table but conflicts with Row Exclusive and stronger modes. It is typically acquired explicitly via `LOCK TABLE ... IN SHARE MODE` when a transaction needs to protect the table state from DML by other transactions for a period of time.

### 5.5. Share Row Exclusive (SRX)

SRX is stronger than S, allowing the lock-holding session to read and modify the table while restricting other transactions from acquiring incompatible DML/share modes. This mode can significantly reduce concurrency; use it only when business requirements truly demand it.

### 5.6. Exclusive (X)

Exclusive is the strongest table lock mode. It prevents other sessions from acquiring incompatible table locks; regular queries can still read data via read consistency, but DML from other sessions will be blocked until the lock is released.

## 6. LOCK TABLE: explicit table locking

General syntax:

```sql
LOCK TABLE table_name
IN [ROW SHARE | ROW EXCLUSIVE | SHARE | SHARE ROW EXCLUSIVE | EXCLUSIVE] MODE
    [NOWAIT | WAIT integer];
```

Example:

```sql
LOCK TABLE employees IN ROW EXCLUSIVE MODE;
```

or:

```sql
LOCK TABLE employees IN SHARE MODE NOWAIT;
```

The table lock is held until `COMMIT` or `ROLLBACK`. If `NOWAIT`/`WAIT` is not specified, the statement may wait according to Oracle's default behavior until the lock is granted.

### 6.1. Table locks are not a default substitute for row locks

For example:

```sql
LOCK TABLE employees IN EXCLUSIVE MODE;
```

locks at the table level, causing DML operations from other sessions on the table to block. If the goal is only to update a single employee, you should normally use `UPDATE ... WHERE employee_id = ...` or `SELECT ... FOR UPDATE`, so other transactions can continue working on non-conflicting rows.

### 6.2. WAIT and NOWAIT with LOCK TABLE

```sql
LOCK TABLE employees IN SHARE MODE WAIT 10;
```

The statement waits up to 10 seconds to acquire the table lock. If it cannot be acquired, Oracle returns a timeout error. With `NOWAIT`, an error is returned immediately when the lock cannot be obtained.

### 6.3. Locking multiple tables

Multiple tables can be locked in a single statement:

```sql
LOCK TABLE orders, order_items
IN SHARE ROW EXCLUSIVE MODE;
```

If multiple transactions lock the same set of tables in different orders, waiting or deadlocks can occur. Standardize the lock acquisition order in the application and only lock objects that are genuinely needed.

## 7. Enqueues: queued locking mechanisms

An **enqueue** is a synchronization mechanism that manages modes and queues, used by Oracle to control concurrent access to protected resources. An enqueue may be held for the duration of a transaction or as needed depending on the resource type.

The two most important enqueue types when analyzing DML are:

- **TX:** transaction enqueue, related to transactions and waiting for other transactions to finish.
- **TM:** DML enqueue, related to locking table objects.

Enqueues are managed by Oracle's lock manager. A session requesting a mode incompatible with a currently held mode may have to wait in a queue.

### 7.1. TX enqueue

TX represents a transaction-related lock. When a transaction modifies a row, Oracle records transaction information in the corresponding block/row structure. Another session needing to modify the same row may have to wait for the transaction that owns the change to finish.

In `V$LOCK`, a TX enqueue is identified by `TYPE = 'TX'`. `ID1` and `ID2` identify the transaction; they are **not the table's OBJECT_ID**. Do not join TX `ID1` directly to `DBA_OBJECTS.OBJECT_ID` to find the locked table.

One transaction can lock many rows, which does not mean `V$LOCK` displays a separate TX enqueue for each row. A TX enqueue is a transaction-scoped mechanism; specific row details must be investigated further via session wait information, currently executing SQL, row wait fields, and block data.

### 7.2. TM enqueue

TM is the DML enqueue protecting a table object. For example, DML on a table typically holds TM in Row Exclusive mode (mode 3). In `V$LOCK`, when `TYPE = 'TM'`, `ID1` usually corresponds to the `OBJECT_ID` of the locked object.

A TM lock does not mean every row in the table is locked. It is a table-level lock mode coordinated with row-level locks to allow transactions to update different rows concurrently.

### 7.3. Enqueue wait events

Some wait events you may encounter:

| Wait event | Common meaning |
|---|---|
| `enq: TX - row lock contention` | Session waiting for another transaction to release a lock related to a row/transaction conflict |
| `enq: TX - allocate ITL entry` | Session waiting for an available ITL slot in a data block |
| `enq: TM - contention` | Session waiting on an incompatible table DML lock |
| `enq: TX - index contention` | A form of contention related to transactions/indexes; check the specific cause and version |

The wait event name helps guide investigation, but it is not enough to conclude a single root cause. Examine the blocking session, SQL, object, transaction age, and the type of operation running.

## 8. How row locks are represented in blocks: ITL and TX

Oracle stores transaction information related to rows inside the data block. An important part is the **Interested Transaction List (ITL)**. ITL entries in the block record the transactions interested in or modifying rows in that block, along with information needed by Oracle to identify the transaction and serve read consistency.

The row header contains a reference to the corresponding ITL entry. Because of this, a row lock is not simply a separate object in `V$LOCK` for each row. When another session needs to modify a row currently owned by an uncommitted transaction, it may have to wait on that transaction's TX enqueue.

### 8.1. What is an ITL slot?

A data block has a limited number of ITL entries at a given time. If many concurrent transactions try to modify rows located in the same block and no usable ITL entry remains, a session may wait on:

```text
enq: TX - allocate ITL entry
```

This is not the same as two sessions updating the same row. The cause is that the block has no free ITL slot available for a new transaction, or existing entries are tied to unfinished transactions.

### 8.2. INITRANS and PCTFREE

`INITRANS` specifies the initial number of ITL entries reserved in a block for a segment/table or index. Oracle can dynamically expand the ITL in a block when sufficient space remains. `PCTFREE` reserves a portion of block space to support row updates and other space needs.

When investigating ITL contention, a DBA may review `INITRANS`, `PCTFREE`, concurrency levels, and data distribution. Do not blindly increase `INITRANS` or alter storage parameters by guesswork; measure waits, verify block contention, and test in an appropriate environment.

## 9. Latches: short-lived synchronization for SGA structures

A **latch** is a lightweight internal synchronization mechanism Oracle uses to protect data structures in shared memory (SGA). A latch is typically held for a very short duration so a process can read or modify an internal structure without another process concurrently accessing it in a way that could corrupt data.

Examples of areas/structures that may involve latches:

- Shared pool and structures managing SQL/cursors.
- Buffer cache and buffer chains.
- Certain internal memory and resource management structures.

A latch is not a row lock or a table lock:

| Characteristic | Row/table lock | Latch |
|---|---|---|
| Purpose | Coordinate access to data/database objects | Protect internal structures in the SGA |
| Hold duration | Can last until COMMIT/ROLLBACK for transaction locks | Usually very brief, within a critical section |
| Business relevance | Can be tied to rows/tables being processed | Typically tied to Oracle internal operations |
| Released by COMMIT | Transaction locks are released on commit/rollback | Not a mechanism for releasing latches |
| Wait example | `enq: TX - row lock contention` | `latch: shared pool`, `latch: cache buffers chains` |

### 9.1. Latch contention

If many processes compete for the same latch, some processes must wait or retry acquiring the latch. Wait events can start with `latch:`. For example:

- `latch: shared pool`: contention on latches related to the shared pool.
- `latch: cache buffers chains`: contention on buffer chains in the buffer cache.

Do not treat latch contention by looking for a row lock and committing, because the cause may lie in SQL patterns, hot blocks, parse workload, or other internal activity.

### 9.2. A latch does not protect a SQL statement for its entire runtime

A SQL statement may perform many steps and only acquire latches during brief intervals when accessing SGA structures. A latch is not held from the moment a SQL statement starts until the transaction commits like a row lock. Therefore, a long-running query does not mean it holds a latch continuously throughout that time.

## 10. Mutexes: lighter-weight internal synchronization for certain structures

A **mutex** (mutual exclusion) is an internal synchronization mechanism used by Oracle to protect certain shared structures, especially in cases involving the library cache and cursors. Mutexes enable finer-grained contention control for certain resources compared to traditional latch mechanisms.

A mutex is also not a business row lock. A session waiting on a mutex may be waiting to access or pin a cursor or object in the library cache, rather than waiting for another transaction to commit a row in a table.

Some wait events related to mutexes/library cache you may encounter depending on version and workload:

- `cursor: pin S wait on X`
- `library cache: mutex X`
- `library cache: mutex S`

Wait event names and display details can vary across Oracle versions. Consult version-specific documentation and actual diagnostic data.

### 10.1. Potential causes of mutex contention

Certain workloads can trigger mutex contention:

- Many sessions accessing the same cursor or library cache object at high frequency.
- Excessive hard parsing of SQL due to differing literal SQL or missing appropriate bind variables.
- Frequent cursor invalidation/reloads.
- Certain object/cursor access patterns that concentrate contention.

These are investigative directions, not automatic conclusions. When seeing mutex wait events, check `SQL_ID`, cursor, module/action, version, AWR/ASH (if licensed), and the corresponding Oracle documentation.

## 11. Comparing row locks, table locks, enqueues, latches, and mutexes

| Mechanism | What does it protect? | Duration / Boundary | Identification Example |
|---|---|---|---|
| Row lock | A row of data | Usually until COMMIT/ROLLBACK | Another transaction waiting to modify the same row |
| Table lock | Table object according to mode | Usually until COMMIT/ROLLBACK for DML/table locks | TM mode 3 (RX) |
| Enqueue | Resources coordinated via modes/queues; can be transactions or tables | Depends on enqueue type and transaction/resource | TX, TM; wait `enq: ...` |
| Latch | Internal structures in the SGA | Short critical section | `latch: shared pool` |
| Mutex | Certain internal structures such as library cache/cursors | Short critical section | `library cache: mutex X` |

An enqueue is a lock management mechanism; TX/TM are specific enqueue types. Row locks and table locks are concepts describing the scope of data/object protection. Latches and mutexes are distinct types of internal synchronization mechanisms.

## 12. Deadlock: two transactions waiting on each other

A deadlock occurs when two or more sessions hold resources that another session needs while waiting for resources held by the other session. Classic example:

**Session A:**

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

-- Then attempts to lock account 2.
UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;
```

**Session B:**

```sql
UPDATE lab_accounts
SET balance = balance - 20
WHERE account_id = 2;

-- Then attempts to lock account 1.
UPDATE lab_accounts
SET balance = balance + 20
WHERE account_id = 1;
```

If A holds the lock on row 1 and waits for row 2, while B holds the lock on row 2 and waits for row 1, the two transactions form a wait cycle. Oracle detects the deadlock and reports:

```text
ORA-00060: deadlock detected while waiting for resource
```

Oracle typically rolls back the statement involved in the deadlock in one session to break the wait cycle; **you should not assume that session's entire transaction has been automatically rolled back**. The application must handle the error, determine the transaction state, and roll back the entire business transaction if required.

### 12.1. Ways to reduce deadlock risk

- Flows that update multiple rows should acquire locks in the same consistent order, such as ascending account ID.
- Keep transactions short; do not wait for user input or make network service calls while holding row locks.
- Update only the exact set of rows needed, avoiding overly broad locking.
- Use clear update predicates and appropriate indexes to avoid unexpected scans/locks.
- When retrying a deadlock, retry the entire business unit in a controlled way and ensure idempotency.

### 12.2. Deadlock vs. lock wait

If A holds a lock and B is simply waiting on A, that is a lock wait, not necessarily a deadlock. A deadlock requires a circular wait dependency. Oracle can let B keep waiting until A commits/rolls back or times out according to the statement/application mechanism.

## 13. Common wait events and how to distinguish them

| Wait event | Problem group | Initial investigation direction |
|---|---|---|
| `enq: TX - row lock contention` | Transaction/row conflict | Find blocker, row-updating SQL, uncommitted transaction, unique key conflict |
| `enq: TM - contention` | Table DML lock conflict | Check TM mode, DDL, `LOCK TABLE`, transactions holding strong modes |
| `enq: TX - allocate ITL entry` | ITL in data block | Check hot block, INITRANS/PCTFREE, concurrent transactions |
| `latch: cache buffers chains` | Latch/buffer cache | Find hot block, concentrated access SQL, buffer contention |
| `latch: shared pool` | Latch/shared pool | Check parse workload, shared pool pressure, SQL/cursor patterns |
| `cursor: pin S wait on X` | Cursor/library cache mutex-related wait | Check cursor invalidation, parse/compile, and session holding the pin |
| `library cache: mutex X` | Library cache mutex | Inspect SQL/cursor/object, hard parsing, and DDL activity |
| `buffer busy waits` | Buffer/block concurrency | Identify segment/block and access type causing contention |

Do not lump every wait event together as "the database is locked." Identify the resource type and synchronization mechanism before choosing a remediation.

## 14. Diagnosing sessions waiting on locks

Querying dynamic performance views typically requires appropriate privileges such as `SELECT_CATALOG_ROLE` or direct privileges on the views. Regular application accounts should not be granted broad privileges just to run diagnostic queries.

### 14.1. Viewing waiting sessions and blockers

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_session,
       blocking_instance,
       final_blocking_session,
       sql_id,
       seconds_in_wait
FROM v$session
WHERE blocking_session IS NOT NULL
   OR event LIKE 'enq:%'
ORDER BY seconds_in_wait DESC;
```

The blocker columns help locate the blocking session. `BLOCKING_SESSION` may be null depending on wait state, configuration, or wait type; combine this with additional session and lock information.

### 14.2. Viewing held/requested enqueues

```sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       ctime,
       block
FROM v$lock
WHERE type IN ('TX', 'TM')
ORDER BY type, id1, id2, sid;
```

Important columns:

- `TYPE`: enqueue type, such as TX or TM.
- `ID1`, `ID2`: resource identifiers specific to the enqueue type.
- `LMODE`: mode currently held by the session.
- `REQUEST`: mode requested by the session; nonzero typically indicates waiting to acquire that mode.
- `CTIME`: duration the session has held the current mode or waited, depending on view context.
- `BLOCK`: indicator of whether the session is blocking other sessions as represented by the view.

Do not interpret `ID1` the same way for every `TYPE`. For TM, `ID1` is typically `OBJECT_ID`; for TX, `ID1`/`ID2` identify the transaction.

### 14.3. Correlating TM with objects

```sql
SELECT l.sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       l.lmode,
       l.request,
       l.ctime
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
LEFT JOIN dba_objects o
  ON o.object_id = l.id1
WHERE l.type = 'TM'
ORDER BY l.ctime DESC;
```

This query uses `ID1` to look up the object for a TM lock. Do not apply that join to TX. If you lack privileges on `DBA_OBJECTS`, a DBA can use `ALL_OBJECTS`/`USER_OBJECTS` within appropriate privilege scope.

### 14.4. Viewing objects with TM locks

```sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.os_user_name,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
```

`V$LOCKED_OBJECT` is useful for seeing objects that have DML locks. It does not provide a complete list of rowids for every row lock currently held.

### 14.5. Viewing session row wait information

When a session is waiting on a row lock, certain `V$SESSION` columns can provide row wait details such as `ROW_WAIT_OBJ#`, `ROW_WAIT_FILE#`, `ROW_WAIT_BLOCK#`, and `ROW_WAIT_ROW#` (values are only meaningful in the appropriate wait state).

```sql
SELECT sid,
       serial#,
       event,
       row_wait_obj#,
       row_wait_file#,
       row_wait_block#,
       row_wait_row#,
       blocking_session,
       sql_id
FROM v$session
WHERE event = 'enq: TX - row lock contention';
```

You can use the object/file/block/row information to investigate further. The row wait columns are not always populated; do not treat 0 or null values as definitive proof that no row conflict exists.

## 15. Two-session lab: observing row locks

These labs use a dummy table `LAB_LOCK_ACCOUNTS`. Practice only in an authorized **DEV/TEST** schema and verify the correct PDB/service. Do not use real accounts or attempt to induce deadlocks on production business tables.

### 15.1. Create the lab table

```sql
CREATE TABLE lab_lock_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_lock_accounts VALUES (1, 'Account A', 1000);
INSERT INTO lab_lock_accounts VALUES (2, 'Account B', 2000);
INSERT INTO lab_lock_accounts VALUES (3, 'Account C', 3000);
COMMIT;
```

### 15.2. Session A locks a row

```sql
UPDATE lab_lock_accounts
SET balance = balance - 100
WHERE account_id = 1;
```

Do not commit. Session A is now holding a row lock on account 1.

### 15.3. Session B updates the same row

```sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 1;
```

Session B must wait for Session A to finish its transaction. Meanwhile, try updating a different row:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 2;
```

Account row 2 is not locked by Session A, so it can be updated independently, depending on any other existing locks.

### 15.4. Finish transaction A

In Session A:

```sql
COMMIT;
```

Session B can proceed once the lock is released. Verify the balance and commit/roll back Session B as intended for the lab.

### 15.5. Try SELECT FOR UPDATE NOWAIT

Session A:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 3
FOR UPDATE;
```

Keep the transaction open. Session B:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 3
FOR UPDATE NOWAIT;
```

Observe the error returned immediately. Then run `ROLLBACK` in Session A to release the lock.

### 15.6. Try SKIP LOCKED

Session A locks account 1:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 1
FOR UPDATE;
```

Session B:

```sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id IN (1, 2, 3)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

Session B skips locked account 1 and can retrieve accounts 2 and 3. Afterward, roll back both sessions.

## 16. Lab: table locks and TM enqueues

### 16.1. Session A acquires a SHARE table lock

```sql
LOCK TABLE lab_lock_accounts IN SHARE MODE;
```

Keep the transaction open. Session A holds an S table lock on the table.

### 16.2. Session B attempts DML

```sql
UPDATE lab_lock_accounts
SET balance = balance + 1
WHERE account_id = 1;
```

DML requires TM Row Exclusive (RX), which conflicts with the Share lock S held by Session A. Session B will wait.

### 16.3. Release the lock

Session A:

```sql
COMMIT;
```

Session B can continue. Observe `V$LOCK`/`V$SESSION` if you have appropriate privileges to see the TM enqueue and wait state.

## 17. Lab: controlled deadlock

Perform this only in an isolated lab database, with two sessions controlled by the learner. Do not attempt to trigger deadlocks on shared tables.

Session A:

```sql
UPDATE lab_lock_accounts
SET balance = balance - 10
WHERE account_id = 1;
```

Session B:

```sql
UPDATE lab_lock_accounts
SET balance = balance - 20
WHERE account_id = 2;
```

After each session holds its own row lock, Session A:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 10
WHERE account_id = 2;
```

Session A waits for B. Next, Session B:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 20
WHERE account_id = 1;
```

Session B waits for A, creating a deadlock cycle. Oracle detects it and returns `ORA-00060` to one statement. Note which session/statement errored; then check whether transactions remain open and explicitly roll back in both sessions before continuing.

## 18. Distinguishing lock contention from latch/mutex contention

When a session waits for a long time, first read `EVENT` and `WAIT_CLASS` in `V$SESSION` or your monitoring tool.

| Symptom | Investigation direction |
|---|---|
| `enq: TX - row lock contention` | Another transaction is holding a row/transaction-related lock; find the blocker and uncommitted transaction |
| `enq: TM - contention` | Conflicting table DML lock mode; check `LOCK TABLE`, DDL, and transactions holding TM |
| `enq: TX - allocate ITL entry` | ITL slot contention in a block; check hot blocks and segment configuration |
| `latch: ...` | Latch contention on SGA structures; investigate SQL/workload and related internal structures |
| `... mutex ...` or `cursor: pin ...` | Mutex/library cache/cursor contention; check parsing, invalidation, and SQL/cursors |
| `buffer busy waits` | Buffer/block access contention; do not assume it is a row lock |

Killing a session based solely on a single wait event is not recommended. First identify the blocker, transaction age, running SQL, impacted business process, and rollback cost. Killing a session can trigger a long rollback, hold resources during rollback, and cause cascading impact.

## 19. Common mistakes and misconceptions

| Misconception / Symptom | Accurate Understanding |
|---|---|
| Regular SELECT locks rows | Regular SELECT uses read consistency and does not automatically lock rows |
| DML locks the entire table | DML acquires an RX mode table lock and row locks on affected rows; other rows can still be modified |
| Oracle escalates row locks into a table lock when modifying many rows | Oracle does not perform automatic lock escalation of that kind |
| A TX enqueue is always a specific row lock | TX is a transaction enqueue; there are multiple causes of TX waits, not just row conflicts |
| A TM lock means every row in the table is locked | TM is a table-level DML lock mode; row locks coordinate row-level conflicts |
| V$LOCK has one TX row per locked row | TX enqueues are tied to transactions; row lock information resides in the data block/ITL |
| COMMIT solves every type of contention | COMMIT releases transaction locks; latches/mutexes are short-lived internal synchronization |
| Latches and mutexes are like row locks | They protect SGA structures, not business rows |
| FOR UPDATE locks only the column named in OF | OF identifies the table whose rows should be locked; row locks lock rows, not individual columns |
| SKIP LOCKED guarantees a job runs exactly once | Application-level status tracking, retries, leases, and idempotency are required |
| ORA-00060 always rolls back the entire transaction | Oracle rolls back the statement involved in the deadlock; the application must handle the remaining transaction |
| ORA-00054 is a deadlock | It is typically resource busy/NOWAIT/timeout, not necessarily a wait cycle |
| Using LOCK TABLE is always safer than SELECT FOR UPDATE | Table locks have broader scope and can severely reduce concurrency |
| All TX waits are caused by two users modifying the same row | TX waits can also involve unique keys, ITL slots, or other transaction mechanisms |

## 20. Lock contention investigation checklist

When a request waits on a lock, follow this sequence:

1. Identify the waiting session: SID, SERIAL#, SQL_ID, module/action, event, wait duration.
2. Identify the blocker: `BLOCKING_SESSION`, corresponding session/instance, and open transaction.
3. Identify the resource type: TX, TM, ITL, latch, mutex, or buffer wait.
4. If TM, identify the object and lock mode; check DDL or `LOCK TABLE`.
5. If TX, identify the statement and involved row/unique key/ITL; check which transaction has not committed.
6. Check when the transaction started and why the application is holding the connection/lock for so long.
7. Determine whether the business operation can retry, roll back, or requires compensation.
8. Only change indexes, INITRANS, PCTFREE, SQL, or code after gathering evidence of the root cause and testing in an appropriate environment.

## 21. Review questions

**Question 1.** What resource does a row lock protect?

**Answer:** A row of data modified by a transaction or explicitly locked, for example with `SELECT FOR UPDATE`.

**Question 2.** Does a regular SELECT in Oracle automatically acquire row locks?

**Answer:** No. Regular SELECT uses read consistency; to lock rows, you must use an explicit mechanism such as `SELECT FOR UPDATE`.

**Question 3.** What table lock mode does DML automatically acquire?

**Answer:** Typically Row Exclusive (RX, mode 3), while simultaneously locking the affected rows.

**Question 4.** Can two sessions hold RX on the same table at the same time?

**Answer:** Yes. RX is compatible with RX; conflicts on the same row are handled at the row/transaction level.

**Question 5.** What does `SELECT ... FOR UPDATE NOWAIT` do when a row is already locked?

**Answer:** Returns an error immediately instead of waiting.

**Question 6.** What scenario is `SKIP LOCKED` suitable for?

**Answer:** Multiple workers pulling work items from a queue; each worker skips rows already locked by another worker and takes other rows.

**Question 7.** How do TX and TM enqueues differ?

**Answer:** TX relates to transactions and transaction-wait scenarios; TM is the DML enqueue protecting table objects.

**Question 8.** Why shouldn't you join `V$LOCK.ID1` for TX directly to `DBA_OBJECTS.OBJECT_ID`?

**Answer:** TX ID1/ID2 identify the transaction, not an object ID. For TM, ID1 typically corresponds to the object ID.

**Question 9.** How do latches/mutexes differ from row locks?

**Answer:** Latches/mutexes protect internal structures in the SGA during short critical sections; row locks protect data rows and are usually held until commit/rollback.

**Question 10.** Does `enq: TX - allocate ITL entry` necessarily mean two sessions are modifying the same row?

**Answer:** No. It typically indicates a block lacks an ITL entry available for a new transaction.

**Question 11.** Does Oracle automatically escalate thousands of row locks into an exclusive table lock?

**Answer:** No such automatic lock escalation mechanism exists; DML continues using table DML locks and row locks.

**Question 12.** What does ORA-00060 mean?

**Answer:** Deadlock detected while waiting for resource. Oracle breaks the wait cycle by rolling back the involved statement; the application must handle the rest of the transaction.

## Conclusion

**Row locks, table locks, enqueues, latches, and mutexes solve different synchronization scopes.** Row locks protect data rows; DML typically also acquires an RX table lock to coordinate table-level access; TX and TM are common enqueue types encountered when investigating lock waits. Oracle does not automatically escalate row locks into an exclusive table lock simply because a transaction updates many rows.

`SELECT FOR UPDATE` is used to explicitly lock rows, with `NOWAIT`, `WAIT`, or `SKIP LOCKED` depending on how the application wants to handle waiting. `LOCK TABLE` locks objects in a broader mode and should be used carefully. Latches and mutexes protect internal SGA structures for brief periods, are not business row locks, and are not released by committing a transaction. When diagnosing issues, read the wait event accurately, find the blocker, and distinguish TX/TM/ITL from latches/mutexes before modifying SQL, schema, or configuration.

## Oracle Reference Documentation

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, row locks, and table locks.
- [Oracle Database 19c Concepts — Automatic Locks in DML Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): automatic locking in DML and table lock modes.
- [Oracle Database 19c SQL Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `FOR UPDATE`, `NOWAIT`, `WAIT`, and `SKIP LOCKED`.
- [Oracle Database 19c SQL Reference — LOCK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOCK-TABLE.html): table lock syntax and modes.
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): enqueue lock information.
- [Oracle Database 19c Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): objects with DML locks.
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session, wait event, and blocking session.
- [Oracle Database 19c Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/index.html): diagnosing contention, latches, and instance performance.
