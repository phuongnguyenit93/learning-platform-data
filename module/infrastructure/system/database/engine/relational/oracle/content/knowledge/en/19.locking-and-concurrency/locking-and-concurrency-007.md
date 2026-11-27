# Deadlocks, Lock-Ordering Causes, and Rollback Scope in Oracle

Two transactions may both need to modify multiple rows. If they acquire locks in opposite orders, each transaction can hold one lock while waiting for the other. Neither transaction can proceed: that is a **deadlock**. Oracle automatically detects this wait cycle and raises error ORA-00060 for one of the participating statements.

An easy mistake in applications involves the rollback scope. When Oracle detects a deadlock, it rolls back the selected statement to break the cycle; that **does not mean the entire transaction of the session receiving the error has been automatically rolled back**. Earlier successful DML statements in that transaction may still be pending commit, and their corresponding locks remain held. If the statements belong to the same atomic business unit of work, the application usually must roll back the entire transaction before retrying.

This lesson belongs to the **Locking and Concurrency** group of Database Engine Relational Oracle. It explains how lock cycles form, common root causes, consistent lock-ordering rules, how to read a deadlock graph, statement rollback vs. transaction rollback scope, and includes a two-session lab to reproduce ORA-00060.

After this lesson, you can:

- Distinguish normal blocking from a deadlock.
- Describe a lock-wait cycle and recognize causes rooted in row access ordering.
- Understand why two individually valid SQL statements can still deadlock when executed concurrently.
- Organize consistent locking order across transactions and application call paths.
- Recognize deadlocks involving multiple tables, triggers, foreign keys, and indexes.
- Understand precisely which statement Oracle rolls back and what part of the transaction remains intact.
- Use deadlock traces/graphs and session information to locate root causes.
- Design bounded retries, full unit-of-work rollback, and duplicate-request protection.
- Reproduce, handle, and verify deadlocks using two Oracle sessions.

> **Example scope:** Syntax follows Oracle Database 19c. All tables with the _LAB suffix are solely for use in a dedicated practice schema. Never intentionally induce deadlocks on a production system. Experiments require two independent sessions, not two tabs sharing a single connection.

## 1. How do blocking and deadlock differ?

### 1.1. Blocking: one session waiting on another

Suppose Session A updates account 10 without running COMMIT. Session B wants to update the same account:

~~~sql
-- Session A
UPDATE account_lab
SET balance = balance - 10
WHERE account_id = 10;
-- Not yet COMMITted.
~~~

~~~sql
-- Session B
UPDATE account_lab
SET balance = balance + 20
WHERE account_id = 10;
-- B waits for A to release the lock.
~~~

This is blocking. A holds the row lock; B waits for A to COMMIT or ROLLBACK. Once A finishes its transaction, B can continue. There is no wait cycle, so it is not yet a deadlock.

### 1.2. Deadlock: sessions waiting on each other in a cycle

A deadlock occurs when A waits for a resource held by B while B simultaneously waits for a resource held by A:

~~~text
Session A                         Session B
---------                         ---------
Locks row 1                       Locks row 2
       |                                  |
       v                                  v
Needs row 2                       Needs row 1
       |                                  |
       +--------- wait cycle -------------+
                         |
                         v
                      DEADLOCK
                         |
                         v
            Oracle detects ORA-00060
~~~

Neither session can make progress on its own unless part of the locks is released. Oracle detects the cycle and rolls back one statement to break the deadlock. Consequently, deadlocks are normally detected and surfaced as errors rather than leaving sessions waiting forever.

### 1.3. Quick comparison

| Scenario | Blocking | Deadlock |
| --- | --- | --- |
| Session waiting on lock | Yes | Yes |
| Wait cycle exists | No | Yes |
| Resolves when blocker commits/rolls back | Yes | Cycle must be broken |
| Characteristic error | Possibly none; waits until timeout if configured | ORA-00060 |
| Resolution approach | Identify blocker, shorten transaction, wait or reasonable timeout | Identify cycle, fix lock ordering, rollback/retry at proper scope |

A long-running transaction can cause blocking without any deadlock. Conversely, a deadlock can happen very quickly when two sessions acquire locks in opposite orders.

## 2. Classic example: updating two rows in opposite orders

Suppose an accounts table has two rows:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 1 | 1,000 |
| 2 | 1,000 |

Session A transfers or updates in order 1 then 2. Session B updates in order 2 then 1.

### 2.1. Steps creating a deadlock

| Step | Session A | Session B |
| ---: | --- | --- |
| 1 | UPDATE row 1, holds lock 1 | |
| 2 | | UPDATE row 2, holds lock 2 |
| 3 | UPDATE row 2, waits for B | |
| 4 | | UPDATE row 1, waits for A |
| 5 | Oracle detects cycle and raises ORA-00060 on one statement | |

Each UPDATE statement is valid when run in isolation. The problem lies in the lock-acquisition order when two transactions run concurrently.

### 2.2. Conditions for forming a deadlock

A deadlock requires a cycle of resource dependencies. In the example:

- A holds the lock on row 1.
- B holds the lock on row 2.
- A requests row 2, which B holds.
- B requests row 1, which A holds.

If A only requests row 2 and B never requests row 1, that is blocking, not a deadlock. A cycle only arises when a wait path loops back to the originating transaction.

## 3. Which resources does Oracle lock?

### 3.1. Row locks and transaction locks

When updating or deleting a row, Oracle locks the modified row. Row locks are held until the transaction ends with COMMIT or ROLLBACK.

Oracle manages row locks through transaction metadata and internal locking structures. In diagnostic tools, you commonly encounter:

- TX enqueue: transaction-related lock, typically appearing in row contention or transaction-resource waits.
- TM enqueue: table-level DML lock, used to coordinate table access and protect DML/DDL operations.

Do not assume every TX wait is a deadlock. A TX wait may simply be normal blocking; examine the cycle and deadlock graph before concluding.

### 3.2. Locks are held across multiple statements

~~~sql
UPDATE account_lab
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_lab
SET balance = balance + 100
WHERE account_id = 2;

-- Both locks remain held until COMMIT or ROLLBACK.
~~~

Oracle does not automatically release row locks when an UPDATE statement finishes. If the transaction continues executing more SQL statements, earlier locks remain held.

This is why long transactions increase blocking risk and create conditions for deadlocks. The more resources a transaction holds, the higher its chance of colliding with other transactions.

### 3.3. Regular SELECT vs. SELECT FOR UPDATE

Regular SELECT uses read consistency and does not acquire row locks like UPDATE. SELECT FOR UPDATE actively locks selected rows to protect a read-then-update workflow:

~~~sql
SELECT account_id, balance
FROM account_lab
WHERE account_id = 1
FOR UPDATE;
~~~

If multiple transactions use SELECT FOR UPDATE on multiple rows, locking order remains critical. Adding SELECT FOR UPDATE does not eliminate deadlocks on its own; if two sessions lock the same set of rows in opposite orders, deadlocks can still happen.

## 4. Common deadlock causes

### 4.1. Two transactions accessing rows in opposite orders

This is the easiest cause to spot:

~~~text
Flow A: row 10 -> row 20
Flow B: row 20 -> row 10
~~~

Examples:

- Two funds transfers A→B and B→A.
- Two orders deducting inventory for the same two products while iterating products in different orders.
- Two batch jobs updating the same group of records sorted by different keys.

**Fix:** standardize locking order using a stable key, such as ascending account_id, ascending product_id, or a unified resource hierarchy.

### 4.2. Accessing multiple tables in different orders

Suppose a business workflow updates CUSTOMER, ORDER, and INVENTORY. One flow executes:

~~~text
CUSTOMER -> ORDER -> INVENTORY
~~~

Another flow executes:

~~~text
INVENTORY -> ORDER -> CUSTOMER
~~~

If two flows hold locks on different tables and then request each other's locks, a wait cycle can form.

**Fix:** define a shared lock hierarchy across the entire application. Every flow must follow the same table/resource order, even when some steps live inside other stored procedures.

### 4.3. Triggers or procedures acquiring unexpected locks

An UPDATE statement can fire a trigger. The trigger in turn updates an audit table, summary table, or related table. The caller only sees one UPDATE statement, yet the transaction has actually acquired locks across multiple tables.

Example:

~~~text
UPDATE ORDER
   |
   +--> trigger updates CUSTOMER_STAT
   |
   +--> trigger writes AUDIT_LOG
~~~

If another flow updates CUSTOMER_STAT first and then updates ORDER, the locking order between the two flows is no longer consistent.

**Fix:** map out all tables touched by triggers, cascades, procedures, and packages. The lock hierarchy must cover indirectly accessed resources as well.

### 4.4. Batch jobs processing overlapping row sets

Two workers may start with disjoint groups of records and later update shared secondary resources. If each worker processes IDs in different orders, deadlocks can occur.

Example:

- Worker A processes order 100 then 200.
- Worker B processes order 200 then 100.
- Both update inventory or reconciliation status.

**Fix:** partition work by key, sort IDs consistently, avoid having two workers own overlapping business groups, and keep transactions short.

### 4.5. Foreign keys lacking an appropriate index

Oracle does not automatically create an index on foreign key columns. When deleting or modifying a parent key, if the child foreign key column lacks a suitable index, Oracle may need to lock the child table more broadly to protect referential checks. This increases blocking and can contribute to deadlocks with concurrent DML on the child table.

Example:

~~~sql
CREATE TABLE order_header_lab (
    order_id NUMBER PRIMARY KEY
);

CREATE TABLE order_line_lab (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    CONSTRAINT fk_order_line_lab
        FOREIGN KEY (order_id)
        REFERENCES order_header_lab(order_id)
);
~~~

If the workload frequently deletes/updates parent keys or has concurrent DML on the child table, evaluate an index:

~~~sql
CREATE INDEX ix_order_line_order_id_lab
ON order_line_lab(order_id);
~~~

A foreign key index generally reduces locking scope and relationship-check cost. However, it does not guarantee eliminating all deadlocks; lock ordering and other resources must still be controlled.

### 4.6. Unique constraints and index entries

Two transactions manipulating values tied to a unique index may have to wait on each other's commit/rollback outcome. If each transaction modifies multiple unique keys or multiple tables in different orders, those waits can combine into a deadlock.

Do not conclude every ORA-00060 is two UPDATEs on the same row. The deadlock graph may point to TX/TM enqueues or index resources. Read the trace to identify the true object.

### 4.7. DDL and DML contention

DDL operations require metadata/table locks of certain scopes. If one session holds a DML lock and another runs DDL or an operation dependent on metadata locks, complex lock waits can arise.

Do not run DDL in the middle of business transaction steps. Oracle DDL also performs implicit commits, making it both a locking issue and a transaction-boundary issue.

## 5. Core rule: consistent locking order

### 5.1. Choose a global order

For multiple resources, define a fixed order, such as:

~~~text
1. CUSTOMER
2. ACCOUNT
3. ORDER
4. INVENTORY
5. LEDGER
6. OUTBOX
~~~

Every transaction needing multiple resource types must acquire locks in that same order. If a flow does not need CUSTOMER, it can start at ACCOUNT; however, it must never lock ORDER and then go back to CUSTOMER if another flow goes CUSTOMER → ORDER.

This order is an application architectural convention, not an Oracle-enforced order. It must be applied across all layers: direct SQL, PL/SQL, triggers, batches, and background jobs.

### 5.2. Sort row locks by ID

If a transaction needs to lock multiple accounts, use ascending account_id in every flow. With two IDs:

~~~text
min(account_id) -> max(account_id)
~~~

Thus, transferring A→B and transferring B→A both lock the same two rows in the same physical order.

### 5.3. Funds transfer example locking in ascending order

Lab table:

~~~sql
CREATE TABLE deadlock_account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(50 CHAR) NOT NULL,
    balance NUMBER(18,2) NOT NULL,
    CONSTRAINT ck_deadlock_balance_lab CHECK (balance >= 0)
);

INSERT INTO deadlock_account_lab VALUES (10, 'Account A', 1000);
INSERT INTO deadlock_account_lab VALUES (20, 'Account B', 1000);
COMMIT;
~~~

The following procedure locks both rows in ascending account_id order, regardless of transfer direction:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_ordered_lab (
    p_from_id IN NUMBER,
    p_to_id   IN NUMBER,
    p_amount  IN NUMBER
) AS
    v_first_balance  NUMBER(18,2);
    v_second_balance NUMBER(18,2);
    v_from_balance   NUMBER(18,2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Amount must be positive');
    END IF;

    IF p_from_id = p_to_id THEN
        RAISE_APPLICATION_ERROR(-20002, 'Accounts must be different');
    END IF;

    -- Always lock the smaller account_id first.
    IF p_from_id < p_to_id THEN
        SELECT balance
        INTO v_first_balance
        FROM deadlock_account_lab
        WHERE account_id = p_from_id
        FOR UPDATE;

        SELECT balance
        INTO v_second_balance
        FROM deadlock_account_lab
        WHERE account_id = p_to_id
        FOR UPDATE;

        v_from_balance := v_first_balance;
    ELSE
        SELECT balance
        INTO v_first_balance
        FROM deadlock_account_lab
        WHERE account_id = p_to_id
        FOR UPDATE;

        SELECT balance
        INTO v_second_balance
        FROM deadlock_account_lab
        WHERE account_id = p_from_id
        FOR UPDATE;

        v_from_balance := v_second_balance;
    END IF;

    IF v_from_balance < p_amount THEN
        RAISE_APPLICATION_ERROR(-20003, 'Insufficient funds');
    END IF;

    UPDATE deadlock_account_lab
    SET balance = balance - p_amount
    WHERE account_id = p_from_id;

    UPDATE deadlock_account_lab
    SET balance = balance + p_amount
    WHERE account_id = p_to_id;
END;
/
~~~

Call the procedure:

~~~sql
BEGIN
    transfer_ordered_lab(10, 20, 100);
END;
/

COMMIT;
~~~

The procedure does not COMMIT. The transaction owner decides to COMMIT once the entire unit of work finishes or ROLLBACK if an error occurs.

Key point: both 10→20 and 20→10 transfers lock account 10 first and then 20. If all paths updating those two accounts follow this rule, they will not create a cycle by reversing those two locks.

### 5.4. With many rows, do not rely on incidental ordering

A multi-row UPDATE statement may be executed by the optimizer with different access paths and plans as indexes, statistics, or data change. Do not rely on the incidental physical order of a single run as your lock order.

When tight control is needed, you can:

- Select the keys to process in a deterministic order.
- Lock each row in that order, or use a FOR UPDATE cursor read by a stable key.
- Once the required set is locked, apply the modifications.
- Ensure all other flows use the same order.

Locking row-by-row has its own overhead; weigh row count, indexes, and transaction length. For very large sets, partitioning work or redesigning to reduce overlap is usually better than one transaction holding thousands of locks.

## 6. Rollback scope when Oracle detects a deadlock

This part must be remembered precisely when writing applications.

### 6.1. Oracle rolls back the deadlocking statement, not the whole transaction automatically

When Oracle detects a deadlock, it chooses one statement participating in the cycle and rolls back that statement to break the deadlock. That session receives error ORA-00060.

DML statements that succeeded before the rolled-back statement may still remain in the transaction. Locks acquired by those earlier statements may also remain held.

Example:

~~~sql
UPDATE deadlock_account_lab
SET balance = balance - 10
WHERE account_id = 10;

-- The second statement hits a deadlock and receives ORA-00060.
UPDATE deadlock_account_lab
SET balance = balance + 10
WHERE account_id = 20;
~~~

If the second statement is rolled back, the first statement is not automatically rolled back with it. The transaction may still be open.

### 6.2. Why shouldn't you just catch ORA-00060 and COMMIT?

Suppose a business operation must:

1. Debit account A.
2. Credit account B.
3. Write a transfer history record.

If step 2 hits a deadlock and is rolled back, step 1 may still be pending. If the application catches the error and COMMITs, account A may be debited without B being credited or history recorded. That is an incomplete business state.

For a unit of work requiring atomicity, the right handling is usually:

1. Catch ORA-00060.
2. ROLLBACK the entire transaction.
3. Log the error and correlation info outside the rolled-back transaction if needed.
4. Wait a bounded backoff interval.
5. Start a new transaction and rerun the entire business operation if safely retryable.

### 6.3. Comparing rollback scopes

| Action | Scope of Undone Changes | Does the Transaction End? |
| --- | --- | --- |
| Statement-level rollback when a statement fails | Changes made by the failed statement | No |
| ROLLBACK TO SAVEPOINT | Changes after the specified savepoint | No |
| ROLLBACK | All uncommitted changes in the current transaction | Yes |
| COMMIT | None undone; confirms transaction changes | Yes |

A deadlock statement rollback is not the same as a full-transaction ROLLBACK. Nor should it be confused with an application-issued ROLLBACK TO SAVEPOINT.

### 6.4. Savepoints do not solve every deadlock automatically

Example:

~~~sql
UPDATE deadlock_account_lab
SET balance = balance - 10
WHERE account_id = 10;

SAVEPOINT before_second_step;

UPDATE deadlock_account_lab
SET balance = balance + 10
WHERE account_id = 20;
~~~

If the second statement hits a deadlock, Oracle rolls back that statement. The application still must decide the fate of the first statement. ROLLBACK TO SAVEPOINT can be helpful for an optional work branch, but if the second step is mandatory for a transfer, rolling back the whole transaction is the right choice to preserve atomicity.

### 6.5. COMMIT and ROLLBACK release locks

- COMMIT confirms all pending changes and releases transaction locks.
- ROLLBACK undoes all uncommitted changes and releases transaction locks.
- ROLLBACK TO SAVEPOINT undoes work after the marker and releases locks associated with the rolled-back changes per Oracle rules.

Do not let a session that received ORA-00060 keep its transaction open while the application waits for a user or calls another service.

## 7. Two-session lab: reproducing ORA-00060

### 7.1. Prepare the table

Run once in a lab schema:

~~~sql
CREATE TABLE deadlock_lab (
    id NUMBER PRIMARY KEY,
    value_no NUMBER NOT NULL
);

INSERT INTO deadlock_lab VALUES (1, 100);
INSERT INTO deadlock_lab VALUES (2, 200);
COMMIT;
~~~

Open two independent Oracle sessions. Do not COMMIT between steps marked uncommitted.

### 7.2. Session A locks row 1

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 1;
~~~

Do not COMMIT. Session A holds the lock on row 1.

### 7.3. Session B locks row 2

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 2;
~~~

Do not COMMIT. Session B holds the lock on row 2.

### 7.4. Session A requests row 2

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 10
WHERE id = 2;
~~~

A must wait because B holds the lock on row 2. Leave this statement waiting.

### 7.5. Session B requests row 1

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 10
WHERE id = 1;
~~~

B must wait for A. Now a cycle exists: A waits for B and B waits for A. Oracle detects the deadlock; one statement receives ORA-00060.

### 7.6. End both sessions' transactions

In the session that received ORA-00060, run:

~~~sql
ROLLBACK;
~~~

If the other statement was waiting, it can proceed once the lock is released. In that remaining session, run ROLLBACK to undo all lab changes:

~~~sql
ROLLBACK;
~~~

Verify:

~~~sql
SELECT id, value_no
FROM deadlock_lab
ORDER BY id;
~~~

The result should be back to 100 and 200. Note that which session receives ORA-00060 is not a rule an application can rely on; Oracle picks a statement to break the cycle.

### 7.7. Retry using the same locking order

In both flows, update row 1 first, then row 2. If A and B still collide, one session may wait for the other, but no cycle forms from these two rows alone because both acquire row 1 before row 2.

Session A:

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 1;

UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 2;
~~~

Session B also executes in that exact order. One session may wait on row 1; once the other runs COMMIT/ROLLBACK, it proceeds. That is resolvable blocking, not an order-inversion deadlock.

End each session with COMMIT or ROLLBACK.

### 7.8. Clean up the lab table

~~~sql
-- Only run after both sessions have ended their transactions.
DROP TABLE deadlock_lab PURGE;
~~~

DROP TABLE is DDL and has an implicit commit per Oracle rules. Run only when sure this is your lab table and its data is no longer needed.

## 8. Diagnosing deadlocks in Oracle

### 8.1. ORA-00060 and the deadlock graph

Common message:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

Oracle writes diagnostic details to a trace file via the diagnostic infrastructure. The deadlock graph typically shows:

- Participating sessions.
- Enqueue/resource types.
- Which session holds and which requests each resource.
- Resource IDs and lock modes.
- Related SQL statements when available.

Traces help pinpoint the actual cycle, but must be combined with code paths and transaction timelines to find the business root cause.

### 8.2. Locating the trace directory

With appropriate privileges:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

Default Trace File is typically the current session's trace file; deadlocks may be written to the involved sessions' traces and alert/diagnostic locations depending on configuration. DBAs can use ADRCI or management tools to find traces by timestamp and process.

### 8.3. Observing sessions waiting on locks

While blocking is still active, you can inspect:

~~~sql
SELECT
    sid,
    serial#,
    username,
    event,
    blocking_session,
    seconds_in_wait,
    wait_class
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

This view reflects sessions waiting at query time. Deadlocks are usually broken immediately by Oracle upon detection, so after ORA-00060 there may no longer be a wait chain visible in V$SESSION. In that case, trace files are the primary source.

In RAC, inspect GV$SESSION and the corresponding instance columns so sessions on other instances are not missed.

### 8.4. Observing TX/TM locks

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
  AND (l.request > 0 OR l.block = 1)
ORDER BY s.sid, l.type;
~~~

Columns LMODE and REQUEST represent held and requested modes. To interpret the resource accurately, cross-reference V$LOCK_TYPE, V$SESSION, and the deadlock graph; do not infer root cause from a single TX wait row alone.

### 8.5. Trace reading workflow

When ORA-00060 occurs:

1. Record the timestamp, service/module/action, request ID, and SQL ID if available.
2. Retrieve the deadlock graph from the trace.
3. Identify the sessions and resources in the cycle.
4. Correlate object IDs, rows/resources, and involved SQL.
5. Trace the application call paths, triggers, and procedures creating the lock order.
6. Compare lock acquisition orders across transactions.
7. Fix the lock order or reduce overlap, then reproduce in a test environment.

Do not simply increase timeouts. Timeouts lengthen how long something waits without breaking a deadlock cycle.

## 9. Preventing deadlocks in design and code

### 9.1. Define a lock hierarchy

Document the locking order for tables/resources updated together. For example:

~~~text
CUSTOMER -> ACCOUNT -> ORDER -> ORDER_LINE -> INVENTORY -> LEDGER
~~~

If a new code path needs to lock in reverse order, redesign it or prove it cannot overlap with the other flow.

### 9.2. Standardize row-locking order

For multiple IDs, use the same sort rule, such as ascending primary key. Do not depend on the incidental order of a full scan, index scan, or execution plan.

### 9.3. Minimize lock count and hold duration

- Lock only the rows truly needed.
- Perform checks that do not require locks before entering the transaction when safe.
- Never wait on users, call REST services, send emails, or transfer files while holding locks.
- Commit/roll back as soon as the unit of work finishes.
- Avoid processing a huge batch in a single transaction if it can be split into independent business units.

Splitting transactions is only valid when business rules allow parts to be committed separately. Never commit between two steps that must succeed together just to shorten lock time.

### 9.4. Audit triggers and indirect procedures

Whenever adding a trigger or calling a new procedure, check which additional tables it updates and how lock ordering changes. Avoid triggers with broad side effects that are hidden from the caller's SQL.

### 9.5. Appropriate indexes for predicates and foreign keys

Indexes can reduce the number of rows read and resource hold time, especially for conditional UPDATE/DELETE. Evaluate foreign key indexes on child tables when workloads delete/update parent keys. Indexes do not replace lock ordering; they only reduce certain types of contention.

### 9.6. Partition work

For worker queues or batches, partition by tenant, account range, or business key to reduce the chance of two workers touching the same rows. SELECT FOR UPDATE SKIP LOCKED can help queues, but only when skipping locked rows matches job semantics. It is not a general solution for all deadlocks.

### 9.7. Avoid keeping transactions open while calling external services

If you need to call a payment service or send messages, design an outbox/saga or an appropriate state workflow. Holding a database transaction open across network calls increases lock duration and does not provide atomicity with the external system anyway.

## 10. Handling ORA-00060 and retries

### 10.1. Roll back the entire unit of work when atomicity is required

Handling pattern in an application service:

~~~text
BEGIN TRANSACTION
    execute step A
    execute step B
    execute step C
    COMMIT

ON ORA-00060
    ROLLBACK WHOLE TRANSACTION
    wait with bounded backoff
    retry whole business operation if safe
~~~

The decisive point is rolling back the entire transaction before retrying. Rerunning only the failed statement leaves earlier changes pending and can base business logic on stale data.

### 10.2. Bounded retries and backoff

Never retry immediately in a tight loop. A policy can include:

- A maximum attempt limit.
- Exponential backoff with jitter.
- Logging retry count, SQL ID, request ID, and wait duration.
- Retrying only errors classified as transient conflicts.
- Returning a handleable/reconcilable error once retries are exhausted.

Backoff reduces the likelihood that transactions collide repeatedly at the same instant. It does not replace fixing reversed lock ordering.

### 10.3. Retries must be idempotent

A client may lose connectivity after the database COMMITs but before receiving the response. When resending the request, the application must recognize it is the same business request.

Example request table:

~~~sql
CREATE TABLE transfer_request_lab (
    request_id VARCHAR2(64 CHAR) PRIMARY KEY,
    transfer_id NUMBER NOT NULL UNIQUE,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL
);
~~~

The unique request ID is written inside the same transaction as balance updates and history. If the same request arrives again, the application returns the stored outcome instead of executing the transfer a second time.

### 10.4. Distinguishing retryable errors

| Error | Common Handling Approach |
| --- | --- |
| ORA-00060 | Roll back full transaction; fix lock order; bounded retry if business-safe |
| ORA-08177 | Roll back and rerun entire SERIALIZABLE transaction if appropriate |
| ORA-00054 or lock timeout | Wait/backoff or report busy per policy |
| ORA-00001 unique violation | Check whether request already exists or data is invalid; do not blindly retry |
| ORA-02290 check violation | Fix data/logic; normally do not retry same input |
| Connection error around COMMIT | Commit outcome may be unknown to client; verify using request/idempotency key |

Not all database errors are transient. Retrying constraint or logic errors does not substitute for fixing data or conditions.

## 11. Deadlocks in JDBC

### 11.1. Catching the error and rolling back the connection

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateFirstResource(connection);
        updateSecondResource(connection);
        writeBusinessHistory(connection);
        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

On ORA-00060, roll back the full transaction before returning the connection to the pool. Never catch the exception, keep reusing the connection, and commit earlier DML statements.

### 11.2. Detecting Oracle error codes

The Oracle JDBC driver typically provides the vendor error code in SQLException:

~~~java
catch (SQLException ex) {
    if (ex.getErrorCode() == 60) {
        // ORA-00060: deadlock detected
    }
    throw ex;
}
~~~

You can check SQLState and chained exceptions depending on the driver, but the Oracle vendor error code specifically identifies ORA-00060. Do not rely solely on matching localized message strings.

### 11.3. Retrying at the transaction-owning layer

Pseudocode:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            executeWholeBusinessUnit(connection, request);
            connection.commit();
            return;
        } catch (SQLException ex) {
            connection.rollback();
            if (ex.getErrorCode() != 60 || attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    sleepWithBackoffAndJitter(attempt);
}
~~~

This is pseudocode: production implementations must handle rollback failures, connection-pool close errors, interruption, ambiguous transaction outcomes around COMMIT, and idempotency. Each retry must acquire a clean transaction/connection and execute the entire business operation again.

### 11.4. Do not commit inside child DAOs

A child DAO or repository should never COMMIT on its own if it participates in a larger unit of work. The service layer owns the transaction, coordinates all DAOs on the same connection, and decides commit/rollback. If each DAO obtains its own connection, they are no longer in the same transaction and atomicity breaks.

## 12. Anti-patterns to avoid

| Practice | Why It Is Dangerous | Better Approach |
| --- | --- | --- |
| Only increasing timeout | The deadlock cycle still exists | Fix locking order |
| Catching ORA-00060 and COMMITting | DML prior to the failed statement may still be pending | Roll back entire unit of work if failed step leaves business state incomplete |
| Retrying only the failed statement | Prior steps may have used stale snapshots/state | Retry the full transaction after rollback |
| Adding COMMITs between UPDATEs to release locks | Breaks business atomicity | Shorten transaction while keeping mandatory steps together |
| Sorting in only one flow | Other flows can still lock in reverse order | Enforce lock hierarchy across all code paths |
| Relying on incidental scan order | Execution plans can change | Lock according to a deliberately designed lock order |
| Skipping all locked rows with SKIP LOCKED | Can violate job semantics | Use only for queues/workers where skipping is valid |
| Dropping triggers to stop deadlocks without analysis | Can lose invariants/auditing | Analyze side effects and redesign order |
| Creating indexes blindly | Increases DML/storage costs without fixing cycles | Read deadlock graph and evaluate indexes per workload |

## 13. Advanced lab: two-way funds transfer

After running the lab in Section 7, you can compare two approaches.

### 13.1. Deadlock-prone approach

Two flows update two accounts but lock in transfer direction:

~~~text
Transfer 10 -> 20: lock 10, then 20
Transfer 20 -> 10: lock 20, then 10
~~~

When run concurrently, they can form a cycle.

### 13.2. Standardized-order approach

~~~text
Transfer 10 -> 20: lock 10, then 20
Transfer 20 -> 10: lock 10, then 20
~~~

Both lock the smaller ID first. One transaction may wait, but no cycle forms from that pair of rows alone.

### 13.3. Observation questions

- Which session received ORA-00060?
- Which statement was rolled back?
- Was DML before that statement still pending?
- How long were the earlier locks held?
- How did the remaining session proceed after the victim rolled back?
- After both rolled back, did balances return to their initial values?
- When both used ascending lock order, how did the outcome change?

Record a millisecond-level timeline if helpful. Accurately identifying the rolled-back statement and open transaction avoids the misconception that Oracle automatically rolls back every change.

## 14. Design and operations checklist

Before deploying a multi-table DML workflow to production, check:

1. Are all tables/rows requiring locks listed?
2. Is there a system-wide lock hierarchy?
3. Are rows within the same table locked in a stable ID order?
4. Do triggers, cascades, and procedures acquire extra locks?
5. Do foreign keys have suitable indexes when required by the workload?
6. Do transactions hold locks while making network calls or waiting for users?
7. Do batch jobs have overlapping data sets?
8. Does the application roll back the entire transaction after ORA-00060?
9. Are retries bounded and idempotent?
10. Are traces/SQL IDs/request IDs sufficient for investigation?
11. Are there concurrency tests using two sessions or multiple workers?
12. After changing execution plans/indexes/triggers, was deadlock behavior re-tested?

## 15. Self-check questions

1. How does a deadlock differ from normal blocking?
2. Why can two individually valid UPDATE statements still deadlock?
3. Which edges make up the wait cycle in the two-row example?
4. Which error does Oracle report when detecting a deadlock?
5. When ORA-00060 occurs, does Oracle roll back a statement or the whole transaction?
6. Can successful DML statements before the rolled-back statement still remain pending?
7. Why does an application usually need to roll back the whole transaction after a deadlock?
8. What effect does COMMIT have on held row locks?
9. Why does locking in ascending account_id order reduce deadlocks?
10. Why must a lock hierarchy include triggers and indirectly called procedures?
11. How can an unindexed foreign key widen locking scope?
12. Does ORA-00060 always indicate two UPDATEs on the same table?
13. What information can a deadlock graph provide?
14. Why does increasing timeouts not solve a deadlock?
15. When is SKIP LOCKED appropriate?
16. Why can retrying only the failed statement produce incorrect business results?
17. How do bounded retries and backoff help?
18. How does an idempotency key handle a client losing the COMMIT response?
19. Why shouldn't you COMMIT between mandatory transfer steps?
20. What must be verified after fixing lock ordering?

**Answer hints:**

1. Blocking is a linear wait path that can clear; a deadlock is a wait cycle.
2. Because each transaction can hold one lock and then request a lock held by the other.
3. A waits for row 2 held by B; B waits for row 1 held by A.
4. ORA-00060.
5. The selected statement to break the cycle; the whole transaction is not automatically rolled back.
6. Yes, they can remain pending until COMMIT/ROLLBACK.
7. To avoid committing an incomplete business state and to release remaining locks.
8. Confirms changes and releases transaction locks.
9. Both transactions acquire locks in the same order, eliminating cycles from inverting that pair of rows.
10. Because indirect side effects also acquire locks and can reverse locking order.
11. Parent deletes/updates may require broader locks on the child table, increasing blocking.
12. No; resources may involve TX/TM enqueues, indexes, or multiple tables.
13. Sessions, resources, lock modes, holder/waiter relationships, and related SQL when available.
14. Timeouts only change wait duration; the cycle does not disappear on its own.
15. For worker queues where skipping rows locked by another worker matches job semantics.
16. Because prior steps may still be pending and business decisions may rely on stale data.
17. Reduces repeated collisions and avoids infinite retry storms that amplify load.
18. Recognizes already-processed requests and returns the stored outcome instead of executing the side effect twice.
19. Committing early makes partial changes permanent so they cannot be rolled back together.
20. Reproduce concurrently, inspect traces, verify lock order, transaction rollback, and final data state.

## Oracle Reference Documentation

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): locks, concurrency handling, and read consistency.
- [Oracle Database 19c Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transactions, commits, rollbacks, and statement-level failures.
- [Oracle Database 19c Administrator's Guide — Managing Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-data-concurrency-and-consistency.html): managing locks and concurrency.
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): lock/enqueue information.
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state and blocking sessions.
- [Oracle Database 19c Administrator's Guide — Automatic Diagnostic Repository](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/monitoring-the-database.html): diagnostic information and traces.
- [Oracle Database Error Messages — ORA-00060](https://docs.oracle.com/en/error-help/db/ora-00060/): deadlock detected while waiting for resource.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE and locking clauses.

**Key rule to remember:** deadlocks usually stem from a lock cycle, especially when transactions acquire multiple rows or multiple tables in different orders. Oracle detects the cycle and rolls back a chosen statement, yet earlier changes in that transaction may remain pending. For an atomic unit of work, roll back the entire transaction, fix the locking order across all call paths, and only retry the full business operation with bounds and duplicate-processing protection.
