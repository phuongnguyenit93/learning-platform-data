# ORA-08177 and Retrying SERIALIZABLE Transactions

Oracle Database supports the **SERIALIZABLE** transaction isolation level. At this level, queries within the same transaction read from a transaction-level consistent snapshot. Changes committed by other transactions after the snapshot was established do not appear in subsequent reads of the current transaction.

In exchange, if a SERIALIZABLE transaction tries to update a row that was modified and committed by another transaction after its snapshot began, Oracle may reject the operation with the error:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

This is a retryable concurrency conflict error. The standard correct handling is to **roll back the entire transaction, start a new transaction, re-read the data, and re-execute the entire business operation**. Simply rerunning the failed SQL statement is not enough, because earlier decisions may have relied on the stale snapshot.

This lesson explains how SERIALIZABLE works in Oracle, conditions that commonly lead to ORA-08177, statement vs. transaction rollback scope, bounded retry strategies in applications, and cases where READ COMMITTED, explicit locking, or constraints are preferable to raising the isolation level.

## 1. Review of transaction isolation levels in Oracle

Oracle typically uses **READ COMMITTED** as its default isolation level. At this level, each query sees a consistent snapshot as of the moment that statement begins. A subsequent SELECT in the same transaction can see newer data if another transaction committed between the two SELECTs.

With **SERIALIZABLE**, statements in the same transaction read from a transaction-level snapshot. Changes committed by other transactions after the snapshot was created do not appear in the current transaction's snapshot.

| Characteristic | READ COMMITTED | SERIALIZABLE |
|---|---|---|
| Read snapshot | Per statement | Per transaction |
| Two SELECTs in one transaction | Can see different committed states | Both see the transaction's snapshot, plus the transaction's own changes |
| Changes committed after transaction starts | Visible to subsequent SELECTs | Not visible in the current snapshot |
| Conflict when writing a row modified after snapshot | Usually waits for lock and proceeds per READ COMMITTED rules | May receive ORA-08177 |
| Application cost | Typically fewer serialization conflict retries needed | Requires a strategy for handling serialization failures |

Do not choose SERIALIZABLE just because its name sounds safer. Choose an isolation level based on consistency requirements, data update patterns, and the application's ability to handle retries.

## 2. SERIALIZABLE establishes a transaction-level snapshot

To select SERIALIZABLE for the current transaction, use:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

This statement must be executed at the start of the transaction, before other SQL statements in the transaction. Once a statement has already started a transaction, you cannot arbitrarily change the isolation level mid-transaction.

Example:

~~~sql
COMMIT;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Subsequent SELECTs in the transaction continue reading the same snapshot.
~~~

After the transaction ends with COMMIT or ROLLBACK, the next transaction can start with its configured isolation level.

### 2.1 Changes made by the transaction itself remain visible

The SERIALIZABLE snapshot does not blind a transaction to its own changes. A transaction sees:

- Data committed before its snapshot was established.
- Changes performed by the current transaction itself.

The transaction does not see new changes committed by other transactions after the snapshot point.

Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 101;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

SELECT balance
FROM accounts
WHERE account_id = 101;
~~~

The second SELECT sees the balance after the current transaction's own UPDATE, even though the initial read snapshot stays stable.

### 2.2 SERIALIZABLE does not lock every row it reads

A common misconception is that SERIALIZABLE locks every row a transaction SELECTs. In Oracle, regular read queries use read consistency and do not automatically place row locks merely because the isolation level is SERIALIZABLE.

Other transactions can still update and commit a row that the current transaction read. A conflict is detected when the current transaction tries to modify data that was changed after its snapshot; at that point Oracle may return ORA-08177.

This differs from assuming "once SELECTed, the row is locked." If business logic needs row locks to serialize operations, use an explicit locking mechanism like SELECT ... FOR UPDATE or a suitable shared lock design.

## 3. When does ORA-08177 occur?

Message:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Typical scenario:

1. Transaction A starts at SERIALIZABLE and reads a row.
2. Transaction B modifies that same row and COMMITs.
3. Transaction A attempts to UPDATE or DELETE the row under its old snapshot.
4. Oracle detects the row was changed by another transaction after A's snapshot began and rejects A's statement with ORA-08177.

Oracle cannot allow A to overwrite a version of data that A has not seen under its transaction snapshot. Rejecting the statement prevents A from proceeding on stale state and producing results inconsistent with the chosen isolation level.

### 3.1 The error typically involves write conflicts on the same row

For example, two transactions both updating account 101's balance:

- A reads balance 1,000 in A's snapshot.
- B updates balance to 1,200 and COMMITs.
- A tries to update based on balance 1,000.

Under SERIALIZABLE, A is not allowed to silently overwrite the new version B committed. A may receive ORA-08177.

### 3.2 Not every conflict is ORA-08177

| Error | Common Meaning |
|---|---|
| ORA-08177 | SERIALIZABLE transaction cannot proceed with write under its snapshot |
| ORA-00060 | Deadlock: sessions waiting on locks in a cycle |
| ORA-00054 | Could not acquire resource lock with NOWAIT or timeout |
| ORA-00001 | Unique constraint or unique index violation |
| ORA-30006 | Timeout expired waiting for lock in certain operations |

Do not handle all SQL errors with the same retry policy. ORA-08177 is a serialization conflict; a unique violation may be genuinely duplicate data; a deadlock requires investigating lock ordering and may have its own retry policy.

### 3.3 ORA-08177 does not necessarily mean the whole transaction rolled back automatically

Oracle applies statement-level atomicity to the failed DML statement: changes made by the failing statement itself are undone. Earlier successful DML statements in the transaction may still be pending.

Technically, the transaction has not necessarily been rolled back completely the instant ORA-08177 arrives. However, for a sound retry strategy, the application should roll back the entire transaction and restart the business operation from the beginning. Continuing the old transaction risks keeping logic derived from the stale snapshot.

## 4. Two-session experiment reproducing ORA-08177

Run in a test schema. Create a table and an initial row:

~~~sql
CREATE TABLE lab_serializable_account (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(14,2) NOT NULL
);

INSERT INTO lab_serializable_account VALUES (101, 1000);
COMMIT;
~~~

Open two separate SQL sessions, called Session A and Session B.

### 4.1 Session A: start SERIALIZABLE and read the row

Run in Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A reads balance 1,000. Transaction A's snapshot is now established.

### 4.2 Session B: update and COMMIT

In Session B, at the default READ COMMITTED isolation level:

~~~sql
UPDATE lab_serializable_account
SET balance = balance + 200
WHERE account_id = 101;

COMMIT;
~~~

The balance is committed as 1,200.

### 4.3 Back to Session A: read and then try to update

Run SELECT again in Session A:

~~~sql
SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A still sees balance 1,000 because it reads from transaction A's snapshot.

Next:

~~~sql
UPDATE lab_serializable_account
SET balance = balance - 100
WHERE account_id = 101;
~~~

Oracle may return:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Session A attempted to write to a row that Session B modified and committed after A's snapshot.

### 4.4 Roll back and verify the committed state

In Session A:

~~~sql
ROLLBACK;
~~~

Then start a new transaction and read again:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A sees balance 1,200. The new transaction gets a new snapshot, including B's committed change.

## 5. Why must the entire transaction be retried?

Suppose an order-placement workflow consists of:

1. Read product price and inventory quantity.
2. Calculate total amount.
3. Check customer credit limit.
4. Deduct inventory.
5. Insert order header and order lines.
6. Record payment.

If step 5 hits ORA-08177, rerunning only the order INSERT is dangerous. Decisions in steps 1–3 may have relied on a stale snapshot; inventory, price, or credit limit may have changed in another transaction.

Proper retry flow:

~~~text
BEGIN TRANSACTION SERIALIZABLE
    Read input data
    Validate business rules
    Recompute calculations
    Execute all DML
    COMMIT

If ORA-08177 occurs:
    ROLLBACK entire transaction
    Wait briefly
    Start new SERIALIZABLE transaction
    Re-read data
    Re-validate rules
    Re-execute full business operation
~~~

A new transaction gets a fresh snapshot. Rolling back only to a savepoint and retrying the last statement does not solve the stale snapshot problem.

### 5.1 Retrying does not mean replaying already-read data

Each retry must re-read required data and recompute business decisions:

- Prices may have changed.
- Inventory may have dropped.
- Credit limit may have been consumed.
- Order status may have changed.
- A row may have been deleted or replaced.

If the application simply replays DML using values computed on the first attempt, it can repeat a decision that is no longer valid.

### 5.2 When retrying is no longer valid by business rules

A transaction may fail because new data makes a business condition false. For instance, after retrying, inventory is no longer sufficient. That is no longer a serialization error to keep retrying; the application must return a business outcome such as "insufficient stock."

Distinguish:

- ORA-08177: snapshot conflict; transaction can be retried.
- Business check fails after reading the new snapshot: stop retrying and return the corresponding outcome.
- Connection error or uncertain COMMIT outcome: requires separate handling because the application may not know whether the server committed.

## 6. Bounded retries and backoff

If multiple sessions continuously update the same data, immediate retries can trigger a new cycle of collisions. Common strategy:

1. Retry only errors classified as transient, such as Oracle error code 8177.
2. Roll back the full transaction before retrying.
3. Cap the maximum number of attempts.
4. Increase wait intervals between attempts (*exponential backoff*).
5. Add randomness (*jitter*) so clients do not retry in lockstep.
6. Log retry counts and wait durations.
7. Once retries are exhausted, return a handleable error or enqueue for deferred retry per business policy.

Illustrative wait schedule:

| Retry Attempt | Base Wait Interval |
|---:|---:|
| 1 | 50 ms |
| 2 | 100 ms |
| 3 | 200 ms |
| 4 | 400 ms |
| 5 | 800 ms |

Actual wait times may include jitter and be bounded by the overall request timeout. No single fixed number fits every workload.

### 6.1 Why not retry infinitely?

Infinite retries can:

- Hold requests and connections for too long.
- Amplify load while the database is already under contention.
- Lengthen request queues.
- Mask design flaws causing transactions to collide constantly.
- Trigger a retry storm when many clients fail together.

After a reasonable number of attempts, log the failure, return a retryable-later status, or move to asynchronous processing.

### 6.2 Retry only recoverable errors

Do not write:

~~~java
catch (SQLException ex) {
    retryEverything();
}
~~~

ORA-00001 may be a duplicate request; ORA-02291 may be missing referenced parent data; ORA-00942 is a schema/privilege error; these errors do not vanish after waiting briefly.

## 7. Retry pattern in JDBC

In JDBC, configure isolation before executing SQL statements in the transaction. Disable autocommit so multiple statements run in the same transaction.

Example processing skeleton:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE
        );
        connection.setAutoCommit(false);

        try {
            // Re-read data inside the new transaction.
            Account source = loadAccount(connection, sourceAccountId);
            Account target = loadAccount(connection, targetAccountId);

            // Re-validate and recalculate from freshly read data.
            validateTransfer(source, target, amount);

            // Execute all changes belonging to the business operation.
            debit(connection, sourceAccountId, amount);
            credit(connection, targetAccountId, amount);
            insertTransferLog(connection, requestId,
                              sourceAccountId, targetAccountId, amount);

            connection.commit();
            return;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    } catch (SQLException ex) {
        if (!isOra08177(ex) || attempt == maxAttempts) {
            throw ex;
        }

        sleepWithBackoffAndJitter(attempt);
    }
}
~~~

An error-checking helper can walk the SQLException chain:

~~~java
static boolean isOra08177(SQLException exception) {
    for (SQLException current = exception;
         current != null;
         current = current.getNextException()) {
        if (current.getErrorCode() == 8177) {
            return true;
        }
    }
    return false;
}
~~~

loadAccount, validateTransfer, debit, credit, insertTransferLog, and sleepWithBackoffAndJitter are structural placeholders to implement for your application. If exceptions are wrapped by another exception type, traverse the cause chain appropriate to your framework.

### 7.1 Key points in the JDBC pattern

- Each attempt obtains a fresh transaction and re-reads data.
- Isolation is set before business SQL statements.
- All DML statements share one connection.
- On error, roll back before closing the connection.
- Only error 8177 enters the retry branch in this example.
- On commit success, return immediately.

With connection pools, follow the pool's connection-reset rules. Never return a connection with an open transaction to the pool. If rollback fails, discard or mark the connection per pool mechanics to avoid reusing unknown state.

### 7.2 Handling uncertain COMMIT outcomes

A network failure right when sending COMMIT can leave the client unsure whether the server committed. This differs from the server explicitly returning ORA-08177.

If a client blindly reruns the business operation after a connection failure, it could create a duplicate transaction if the prior attempt actually committed. Use a request ID/idempotency key with a unique constraint or a business state table to recognize completed work.

## 8. Idempotency and side effects in retried transactions

A transaction may execute multiple times due to retries. Therefore, operations must be designed not to produce duplicate results when the same request is retried.

Example transfer table with a unique request ID:

~~~sql
CREATE TABLE lab_transfer_request (
    request_id     VARCHAR2(64) PRIMARY KEY,
    from_account   NUMBER NOT NULL,
    to_account     NUMBER NOT NULL,
    amount         NUMBER(14,2) NOT NULL,
    status         VARCHAR2(20) NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

The application uses a stable REQUEST_ID for the same business request. If the request was committed earlier, the unique constraint identifies the duplicate submission. Define how to return the stored outcome of the completed request instead of debiting money a second time.

### 8.1 Never send emails or call external APIs inside a retry loop

If an application sends an email before COMMIT and then hits ORA-08177, the email cannot roll back automatically. A retry could send the email a second time.

A common pattern is the transactional outbox:

1. Write business changes and an outbox row inside the same transaction.
2. COMMIT.
3. A separate worker reads the outbox and sends messages/emails.
4. The worker marks sent or retries delivery using an idempotency key.

Thus retrying the database transaction does not automatically duplicate external side effects.

### 8.2 Do not use sequences to guarantee non-duplicate requests

Sequences can produce gaps when transactions roll back or retry. A new sequence ID on each attempt does not prove it is a new business request. Use a stable request ID or unique business key to prevent duplicates.

## 9. SERIALIZABLE and write skew

SERIALIZABLE in Oracle provides transaction-level read consistency and detects conflicts when a transaction attempts to write data modified by another transaction after its snapshot. However, do not assume merely setting this isolation level automatically protects every multi-row business invariant.

A noteworthy scenario is **write skew**: two transactions read the same valid state and then update two different rows. Because they do not overwrite the same row, a row-level write conflict may not occur, even though the combined post-commit state violates a business rule.

Example rule: at least one doctor must always be on call. The table has two doctors, both currently on call:

| DOCTOR_ID | ON_CALL |
|---:|---|
| 1 | Y |
| 2 | Y |

Both transactions read that two doctors are on call:

- Transaction A sets doctor 1 to N.
- Transaction B sets doctor 2 to N.
- Each transaction updates only a different row.

Without a shared lock or constraint protecting the aggregate invariant, both can commit and leave zero doctors on call. That is why multi-row business invariants must be analyzed explicitly, rather than relying solely on an isolation label.

### 9.1 Locking a shared coordination row

One approach is creating a lock/guard row representing the on-call roster. Every transaction must lock that row before reading and updating doctors:

~~~sql
SELECT roster_id
FROM on_call_roster
WHERE roster_id = 1
FOR UPDATE;

SELECT COUNT(*)
FROM doctors
WHERE on_call = 'Y';

-- Validate rule and then update doctor.
~~~

In a READ COMMITTED design, transactions locking the same guard row serialize at that point. After waiting for the lock, the next transaction reads the latest committed state in the next statement and re-validates the invariant.

All related write paths must follow the same locking rule. If any update flow bypasses the guard row, the protection is incomplete.

### 9.2 Prefer constraints when expressible

If a rule can be expressed via:

- PRIMARY KEY or UNIQUE.
- FOREIGN KEY.
- Single-row CHECK constraints.
- A controlled aggregate/guard column.

let the database enforce the invariant where appropriate. Aggregate rules across multiple rows usually require locking or a different data model; standard CHECK constraints cannot contain queries counting rows in another table.

## 10. When to use SERIALIZABLE vs. READ COMMITTED?

No isolation level is optimal for every workload.

### 10.1 SERIALIZABLE can fit when

- A transaction needs to read one consistent snapshot across multiple SELECT statements.
- Business rules depend on data at the same logical point in time.
- The application can roll back and retry the entire transaction.
- Write conflict frequency is low enough for retries to be effective.
- Multi-row invariants already have suitable locks/constraints.

### 10.2 READ COMMITTED typically fits when

- The application accepts each SELECT seeing the latest committed state when that statement begins.
- Specific rows need updating and can be locked with SELECT FOR UPDATE.
- Validation and update can be folded into a single conditional DML statement.
- You want to avoid transaction-level serialization conflict retries for write-heavy workloads.

### 10.3 Conditional updates instead of read-then-write

Instead of:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :account_id;

-- Application checks balance on the client side.

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id;
~~~

place the condition directly inside DML:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Then check the number of updated rows:

- 1 row: operation satisfied the condition.
- 0 rows: account does not exist or balance is insufficient; determine the reason per business requirements.

This narrows the window between read and write and leverages UPDATE's row lock. It is usually simpler than elevating the entire transaction to SERIALIZABLE when only protecting a single-row condition.

### 10.4 SELECT FOR UPDATE

If business logic needs to read multiple columns before deciding, lock the row:

~~~sql
SELECT balance, status
FROM accounts
WHERE account_id = :account_id
FOR UPDATE;
~~~

The row stays locked until the transaction commits or rolls back. Other sessions wanting to modify that row must wait or handle timeout/NOWAIT/SKIP LOCKED appropriately.

Explicit locking helps serialize operations on the selected rows. It does not automatically protect a rule spanning other unlocked rows; you must identify the full row set or lock a guard row.

## 11. Errors commonly confused with ORA-08177

| Error Code | Cause | Should It Use the Same ORA-08177 Retry Policy? |
|---|---|---|
| ORA-08177 | Serialization conflict in a SERIALIZABLE transaction | Yes, retry full transaction after rollback |
| ORA-00060 | Deadlock | Can retry transaction under its own policy, but investigate lock ordering |
| ORA-00001 | Unique violation | Normally do not blindly retry; check duplicate data/request |
| ORA-02291 | Missing parent reference key | Fix order or data; not a serialization conflict |
| ORA-02292 | Cannot delete parent row because child rows exist | Handle data relationship |
| ORA-00054 | Resource busy/NOWAIT or timeout | May retry with timeout handling, but understand what holds the resource |
| ORA-30006 | Lock wait timeout expired | Retry may fit if business rules and deadlines allow |

Do not classify errors solely as "looks concurrency-related." Check the exact Oracle code, SQL operation, transaction state, and logs of involved sessions.

## 12. Diagnosing ORA-08177 in real environments

When the error occurs, capture at minimum:

- The SQL statement and bind values involved.
- Oracle error code 8177 and full exception stack.
- Session isolation level.
- Transaction start time and error timestamp.
- SQL_ID if available.
- Application-level request ID/correlation ID.
- Retry count and wait durations.
- How many DML statements preceded the failing statement in the transaction.

### 12.1 Inspecting the session

In environments with privileges for the views:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       module,
       action
FROM v$session
WHERE audsid = SYS_CONTEXT('USERENV', 'SESSIONID');
~~~

V$SESSION does not necessarily display the current isolation level directly in every release. Applications should log transaction configuration at transaction start; DBAs can use appropriate views/session instrumentation to investigate.

### 12.2 Viewing active sessions and SQL

DBAs can inspect:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       blocking_session
FROM v$session
WHERE username IS NOT NULL
ORDER BY sid;
~~~

ORA-08177 is a serialization conflict rather than necessarily a session waiting on a lock. There will not always be a BLOCKING_SESSION explaining the error; inspect operation history and transaction timing.

### 12.3 Measuring retry frequency

Applications should record metrics:

- Number of SERIALIZABLE transactions started.
- Number of ORA-08177 occurrences.
- Number of transactions succeeding on retry.
- Number of transactions exhausting retries.
- Average and percentile retry counts.
- End-to-end completion latency including retries.
- Tables/business keys experiencing frequent conflicts.

If a business flow frequently retries many times, the isolation level or locking model may be mismatched to the contention level. Raising retry limits indefinitely only hides the problem.

## 13. Retries in PL/SQL and transaction ownership

PL/SQL procedures typically execute within the caller session's transaction. A procedure should not arbitrarily COMMIT/ROLLBACK the caller's entire transaction unless its contract specifies so.

For ORA-08177, retries should usually be coordinated at the layer owning the entire business unit:

1. Catch the serialization error.
2. ROLLBACK the current transaction.
3. Start a new transaction at the appropriate isolation level.
4. Re-read data.
5. Re-run the entire business operation.

Do not catch ORA-08177 inside a sub-procedure and rerun a single UPDATE, because the sub-procedure cannot know what earlier decisions the caller made.

### 13.1 Savepoints do not refresh the snapshot

Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM lab_serializable_account
WHERE account_id = 101;

SAVEPOINT before_change;

-- Another session updates and COMMITs this row.

UPDATE lab_serializable_account
SET balance = balance + 10
WHERE account_id = 101;
~~~

If the UPDATE receives ORA-08177, running:

~~~sql
ROLLBACK TO before_change;
~~~

does not create a new snapshot. The transaction remains the original SERIALIZABLE transaction. To get a fresh snapshot, end the transaction with ROLLBACK and start a new one.

## 14. Design optimizations to reduce serialization conflicts

If ORA-08177 happens frequently, investigate design-level causes:

### 14.1 Shorten open transaction duration

- Read and validate required data close to update time.
- Do not call external services while a transaction is open.
- Do not perform long CPU work between DML statements.
- Do not span a transaction across user interactions.
- Commit or roll back promptly once the business unit finishes.

The longer a transaction stays open, the wider the window for other sessions to modify rows it intends to update.

### 14.2 Shrink shared write footprints

- Identify which rows genuinely need updating.
- Avoid updating a single global summary row on every request if work can be partitioned by business key.
- Update with precise predicates.
- Avoid reading a large set and writing back everything when only a few rows changed.

Do not split partitions/keys arbitrarily if doing so breaks invariants. The goal is reducing contention while still enforcing the rules.

### 14.3 Choose isolation and locking per requirements

- Use READ COMMITTED when statement-level snapshots suffice.
- Use SELECT FOR UPDATE when operations on specific rows must serialize.
- Use a guard row when invariants span multiple rows.
- Use unique/foreign key/check constraints when rules can be expressed in the schema.
- Use SERIALIZABLE when a consistent transaction snapshot is required and retry handling is in place.

## 15. Decision flowchart for handling ORA-08177

~~~mermaid
flowchart TD
    A["Application receives ORA-08177"] --> B["Identify error 8177 from Oracle"]
    B --> C["Roll back entire transaction"]
    C --> D{"Retries left and within request deadline?"}
    D -->|No| E["Return handleable error / enqueue"]
    D -->|Yes| F["Backoff + jitter"]
    F --> G["Start new transaction"]
    G --> H["Re-read data and validate business rules"]
    H --> I{"Data still satisfies conditions?"}
    I -->|No| J["Return business outcome"]
    I -->|Yes| K["Re-run full DML"]
    K --> L{"COMMIT succeeds?"}
    L -->|Yes| M["Done"]
    L -->|ORA-08177| B
    L -->|Other error| N["Handle by error code"]
~~~

## 16. Self-check practice labs

These labs use table LAB_SERIALIZABLE_ACCOUNT from section 4. Run in a test schema with two independent sessions.

### Lab 1 — Reproduce ORA-08177

Execute in exact order:

1. Session A runs SET TRANSACTION SERIALIZABLE and SELECTs the balance.
2. Session B UPDATEs the same row and COMMITs.
3. Session A runs SELECT again.
4. Session A runs UPDATE on the same row.

Record the value A sees and the error received. Explain why the second SELECT still saw the old snapshot.

### Lab 2 — Retry the transaction

After the error in Lab 1, Session A runs ROLLBACK. Start a new SERIALIZABLE transaction, re-read the balance, re-run the UPDATE, and COMMIT. Compare snapshots before and after retry.

### Lab 3 — Statement rollback vs. transaction rollback

In Session A, perform a valid UPDATE on another row before triggering the conflict. When the conflicting UPDATE receives ORA-08177, inspect the state of the earlier change. Then ROLLBACK the entire transaction and verify from another session.

### Lab 4 — Savepoint does not refresh snapshot

Inside a SERIALIZABLE transaction, create a SAVEPOINT and let Session B modify and commit the row. When Session A hits ORA-08177, try ROLLBACK TO SAVEPOINT and rerun the UPDATE. Observe why the snapshot was not refreshed. Finally run a full ROLLBACK.

### Lab 5 — READ COMMITTED

Run the same scenario under READ COMMITTED. Compare Session A re-reading data after B commits and A's ability to UPDATE. Explain the difference between statement-level and transaction-level snapshots.

### Lab 6 — Bounded retry

Write pseudo-code or a Java loop with at most 4 attempts, backoff, and jitter. Retry only when the Oracle error code is 8177. Unique constraint errors and invalid business data must exit the retry loop.

### Lab 7 — Idempotency

Create a unique request ID for a funds transfer. Simulate the same request being resent after a timeout. Design so the resubmission does not debit twice.

### Lab 8 — Write skew

Use two on-call doctor rows. Two sessions both read both rows and then update different rows in SERIALIZABLE transactions. Observe the invariant "at least one doctor is always on call." Propose a guard row or shared locking mechanism.

### Lab 9 — Conditional DML

Write an UPDATE deducting balance with predicate balance >= :amount, then check rowcount. Compare with SELECT first followed by an unconditional UPDATE.

### Lab 10 — Measure contention

Run multiple sessions concurrently updating a set of rows. Record ORA-08177 counts, successful retries, failed retries, and total completion time. Vary transaction duration and compare.

## 17. Common misconceptions

| Misconception | Accurate Understanding |
|---|---|
| SERIALIZABLE locks every row it SELECTs | Regular SELECTs do not automatically lock rows |
| ORA-08177 automatically rolls back the entire transaction | Only the failed statement is rolled back; earlier DML may remain pending |
| Rerunning just the failed SQL statement is enough | You must roll back and rerun the full business operation from a new snapshot |
| ROLLBACK TO SAVEPOINT creates a new snapshot | Savepoints do not end the transaction or refresh its snapshot |
| SERIALIZABLE always prevents every invariant violation | Multi-row rules still need constraints or suitable shared locks |
| Every SQL error can be retried | Retry only classified transient errors |
| Infinite immediate retries are safe | Use caps, backoff, jitter, and metrics |
| JDBC rollback can always undo a prior commit | Autocommit or an already succeeded commit cannot be rolled back |
| ORA-08177 is the same as a deadlock | It is a serialization conflict, distinct from ORA-00060 |
| Sequences leave no gaps if a transaction rolls back | NEXTVAL is not returned on rollback |
| Emails/APIs roll back together with the database | External side effects require an outbox or compensation |

## 18. SERIALIZABLE retry deployment checklist

Before enabling retries in production, verify:

- Is the isolation level set before the first statement of the transaction?
- Does the transaction genuinely require a transaction-level consistent snapshot?
- Is error code 8177 accurately detected via the Oracle error code?
- On error, does the application roll back the entire transaction?
- Does each retry re-read data and recompute decisions?
- Are retries bounded by attempt count and total deadline?
- Are backoff and jitter in place to prevent retry storms?
- Is there a request ID/idempotency key to handle duplicate submissions?
- Are emails/APIs or external side effects kept outside the retry loop?
- Are ambiguous network errors around COMMIT handled separately?
- Are multi-row invariants protected by shared locks or constraints?
- Are metrics tracked for retry rate, successes, failures, and contention?
- Has it been tested with multiple concurrent sessions using representative data?

## 19. Takeaways

| Topic | Rule |
|---|---|
| READ COMMITTED | Statement-level consistent snapshot |
| SERIALIZABLE | Transaction-level consistent snapshot |
| SET TRANSACTION | Set isolation level at the beginning of the transaction |
| ORA-08177 | Write conflict with data committed by another transaction after snapshot |
| Statement atomicity | Failed DML statement is rolled back individually |
| Transaction retry | Roll back everything and start a new transaction |
| Savepoints | Do not refresh the transaction's snapshot |
| Retry policy | Bounded, with backoff, jitter, and only for eligible errors |
| Idempotency | Same request never causes duplicate business effects |
| Side effects | Use outbox/compensation for systems outside the database |
| Write skew | Shared locks/constraints may be required for multi-row invariants |
| READ COMMITTED + locking | Usually preferable when only specific rows or scopes need protection |

ORA-08177 signals that Oracle cannot let a SERIALIZABLE transaction proceed with writes under its stale snapshot. Roll back the entire transaction, start a new transaction, re-read the data, and rerun the business logic with bounded retries. At the same time, review isolation levels, transaction durations, contended rows, and multi-row invariants. A solid retry strategy must protect both data correctness and request idempotency, especially when the application triggers side effects outside the database.
