# Designing Short Transactions, Error Control, and Retry Rules in Oracle Database

A database transaction must keep related changes in a single consistent unit, yet also finish quickly so it does not hold locks too long, consume resources, and block other sessions. When errors occur, the application must know which errors can be retried, which must be returned to the user, and how to avoid executing a business operation twice if the outcome of a prior attempt is unknown.

Good transaction design balances four goals:

1. **Atomicity:** changes belonging to the same business operation must succeed together or be discarded together.
2. **Short duration:** hold transactions and locks only as long as strictly necessary.
3. **Clear error handling:** roll back the proper scope, preserve the root error cause, and never swallow errors.
4. **Safe retries:** retry only when justified, bounded, and repeatable without creating duplicate side effects.

In Oracle, these concerns tie directly to transaction isolation, row locks, `SAVEPOINT`, `SQL%ROWCOUNT`, PL/SQL exception handling, unique constraints, idempotency keys, and errors such as `ORA-00060` or `ORA-08177`. This lesson covers design from a simple DML operation up to application transaction flows and queue workers.

## 1. A Transaction Is the Boundary of a Business Operation

A transaction groups business-related data changes into one unit. For example, transferring money between two accounts requires:

- Debiting the source account.
- Crediting the destination account.
- Potentially inserting a transaction history record.

If only the debit succeeds and the credit fails, the data is no longer valid. All three operations must belong to the same transaction:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

INSERT INTO transfer_log (
    from_account_id,
    to_account_id,
    amount,
    created_at
)
VALUES (
    10,
    20,
    100,
    SYSTIMESTAMP
);

COMMIT;
~~~

If a step fails before COMMIT, the application can ROLLBACK to discard the transaction's changes. COMMIT confirms all changes; ROLLBACK discards uncommitted changes.

### 1.1 A Transaction Is Not Synonymous with One SQL Statement

A transaction can consist of one or many SQL statements. Even a single UPDATE statement executes inside a transaction. A multi-step business workflow can require multiple DML statements before committing.

Oracle provides statement-level atomicity: if one SQL statement errors during execution, the changes of that statement itself are rolled back. This **does not mean the entire preceding transaction automatically rolls back**.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- This statement errors because account_id does not exist or a condition/constraint fails:
UPDATE accounts
SET balance = balance + 100
WHERE account_id = -999;
~~~

The failure of the second UPDATE does not automatically undo the first UPDATE. If business rules require both operations to succeed together, the caller must ROLLBACK the transaction upon detecting the error.

### 1.2 Oracle Defaults to READ COMMITTED

Oracle's default isolation level is READ COMMITTED. Each query sees data committed before that query started, along with changes made by the current transaction itself. A subsequent SELECT can see new data committed by another session after the previous SELECT.

This means two SELECTs in the same READ COMMITTED transaction do not necessarily see the same snapshot. If business logic needs to protect a row about to be updated, use `SELECT FOR UPDATE` or optimistic concurrency via a version column/update predicate.

Do not confuse READ COMMITTED with transactions auto-committing after every statement. DML remains uncommitted until the application or session issues COMMIT, unless the client/driver has autocommit enabled.

## 2. Why Must Transactions Be Kept Short?

Long transactions increase row lock hold times, increase the amount of undo that must be retained, prolong waits for other sessions, and make recovery on failure harder. A long transaction is also more prone to interruption by timeouts, disconnects, or user actions.

### 2.1 Things Never to Do While Holding a Transaction

Avoid holding a transaction open while:

- Waiting for user confirmation on screen.
- Calling HTTP APIs, payment providers, email services, or message brokers.
- Uploading/downloading files or processing large files.
- Running a long CPU computation that needs no database reads/writes.
- Waiting on an external task or sleeping for a retry.
- Waiting for an operator to inspect results.

Bad flow example:

~~~text
BEGIN TRANSACTION
    UPDATE data and hold row lock
    Call external API, wait 15 seconds
    Wait for user confirmation
    Write log
COMMIT
~~~

Throughout the wait, locks remain held. Sessions needing to update the same rows can get blocked.

### 2.2 Structuring a Better Flow

~~~text
Validate inputs and prepare data
              |
              v
Begin short transaction
              |
              v
Read/lock required data
              |
              v
Check invariants and execute DML
              |
              v
Write related records
              |
              v
COMMIT
              |
              v
Execute external side effects via a suitable mechanism
~~~

Put only operations that must be atomic together inside the transaction. Independent and slow tasks should be prepared beforehand or executed post-commit via a retryable mechanism.

### 2.3 Short Does Not Mean Splitting Arbitrarily

Never split one business operation into multiple transactions just to make each transaction shorter if doing so breaks atomicity. For instance, a money transfer cannot commit the debit step and then start a separate transaction for the credit step, unless a compensating business model and intermediate states are explicitly designed.

For importing millions of rows, committing in batches is acceptable if each batch is an independent unit with checkpoints. In that case, the system accepts partially completed states and must resume safely. This is a business/architectural decision, not a harmless technical micro-optimization.

## 3. Minimizing Lock Hold Duration

### 3.1 Lock Only When Truly Necessary

A standard SELECT does not lock rows the way `SELECT FOR UPDATE` locks them. If you need to read and then update a row while preventing another session from modifying it in between, you can lock it:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE;
~~~

After acquiring the lock, the session can check the balance and update within the same transaction. The lock is held until COMMIT or ROLLBACK.

### 3.2 NOWAIT and WAIT

If you do not want to wait on locks indefinitely, pick a wait policy:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE NOWAIT;
~~~

`NOWAIT` requests an immediate error if the row is locked by another session. The application can return a busy status or apply bounded retries per business rules.

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE WAIT 5;
~~~

`WAIT 5` allows waiting up to the specified number of seconds before raising a lock error. The wait limit should align with SLAs and overall request timeouts.

### 3.3 SKIP LOCKED for Queues

~~~sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` skips rows currently locked by another session, useful when multiple workers dequeue tasks from a queue. It is unsuitable for user queries needing to view complete data because locked rows are silently omitted.

For queues, lock and claim ownership in a short transaction, update the status/lease, and commit. Perform heavy processing after releasing the lock.

### 3.4 Conditional Updates Instead of Read-Then-Check

When decrementing inventory without allowing negative counts, a conditional UPDATE is generally safer than SELECT followed by UPDATE:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :p_quantity
WHERE product_id = :p_product_id
  AND available_qty >= :p_quantity;
~~~

Then check:

~~~sql
IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(
        -20001,
        'Insufficient inventory or product does not exist'
    );
END IF;
~~~

The predicate is evaluated alongside the update under Oracle's locking mechanics. Two sessions placing orders simultaneously cannot both deduct more than available stock just because both read a stale value earlier.

If you need to distinguish "product missing" from "insufficient stock," run a follow-up keyed query or return distinct business outcome codes. Never skip checking `SQL%ROWCOUNT`.

## 4. Optimistic Concurrency with a Version Column

Not every workflow needs `SELECT FOR UPDATE`. When conflicts are infrequent and stale data modifications can be detected, optimistic concurrency is an option.

### 4.1 Add a Version Column

~~~sql
ALTER TABLE account_profile
ADD (version_no NUMBER DEFAULT 0 NOT NULL);
~~~

The application reads `VERSION_NO` along with the data. When updating, pass back the version it read:

~~~sql
UPDATE account_profile
SET display_name = :p_display_name,
    version_no = version_no + 1
WHERE account_id = :p_account_id
  AND version_no = :p_expected_version;
~~~

Check `SQL%ROWCOUNT`:

- `1`: update succeeded; the current version matched what the application read.
- `0`: the row does not exist or was updated earlier by another session; this is a conflict to resolve.

### 4.2 Never Blindly Overwrite Conflicts

If the UPDATE returns 0 rows, the application should re-read the latest data and decide:

- Notify the user that the data changed.
- Merge changes if business rules permit.
- Recompute the operation on fresh data and perform a bounded retry.

Never blindly loop the UPDATE with the same `VERSION_NO`, as it will keep failing to match. Nor should you drop the version predicate to force an overwrite without an explicit policy.

### 4.3 Distinguish Business Conflicts from Transient Errors

An optimistic conflict is not necessarily a transient database error. It may reflect a legitimate edit by another user. UIs often need to reload fresh data and ask the user to confirm/merge rather than retrying blindly.

## 5. Maintain Consistent Lock Order to Reduce Deadlocks

A deadlock occurs when two transactions wait on resources held by each other in a cycle.

Example:

~~~text
Session A                       Session B
---------                       ---------
Locks account 10                Locks account 20
Waits for account 20            Waits for account 10
        \                       /
         \------ deadlock -----/
~~~

Oracle detects the deadlock and raises `ORA-00060` on one statement. To reduce the likelihood:

- Whenever locking multiple rows, acquire locks in the same deterministic order across all code paths—such as ascending `ACCOUNT_ID`.
- Keep transactions short and avoid waiting on external services while holding locks.
- Do not lock more rows than necessary.
- Design proper indexes to minimize row lookup time.
- Review workflows to see if any two paths update the same set of rows in opposite orders.

Consistent lock ordering reduces deadlocks, though it does not eliminate every deadlock cause. Triggers, foreign keys, indexes, and related tables can also introduce additional lock paths.

## 6. Error Control in PL/SQL

### 6.1 An Exception Does Not Automatically Roll Back the Entire Transaction

If a DML statement errors, Oracle rolls back the effects of that statement. Earlier DML statements in the transaction remain active until the caller COMMITs or ROLLBACKs.

Example:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -999;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

`RAISE` propagates the error to the caller. It does not automatically roll back the first UPDATE. The caller must decide to roll back the transaction if business logic requires both operations to succeed together.

### 6.2 When to Use RAISE_APPLICATION_ERROR?

To return a business error with a custom code in the range `-20000` to `-20999`:

~~~sql
IF p_amount <= 0 THEN
    RAISE_APPLICATION_ERROR(
        -20010,
        'Transfer amount must be greater than 0'
    );
END IF;
~~~

Custom error codes help applications distinguish business validation failures from Oracle system errors. Do not reuse arbitrary codes colliding with system errors or collapse every error into one generic code that hides the root cause.

### 6.3 WHEN OTHERS Must Not Swallow Errors

Never write:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

This misleads the application into thinking the operation succeeded while data may be partially updated or incorrect.

Minimum pattern if simply propagating the error:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
~~~

If logging is needed, record useful context such as `SQLCODE`, `SQLERRM`, request ID, and business step; then re-raise with `RAISE`. Note that logs written inside the same transaction will roll back with the transaction. Independent logging mechanisms must be designed separately without unilaterally committing business changes.

### 6.4 Shared Procedures Should Not Unilaterally COMMIT

A stored procedure can be invoked from many different flows. If a procedure COMMITs on its own, it can commit other changes the caller already made in the same session transaction.

An easily controllable convention:

- The procedure executes the necessary DML.
- The procedure returns a result or raises an error.
- The caller owns the transaction boundary and decides COMMIT/ROLLBACK.

If a database API is explicitly designed to own its transaction, document that contract clearly. Never mix the two models unpredictably in the same system.

## 7. SAVEPOINT and Partial Rollback

`SAVEPOINT` marks a position inside the current transaction:

~~~sql
SAVEPOINT before_optional_step;

UPDATE customer_profile
SET note = 'processed'
WHERE customer_id = 10;

-- If the optional step fails:
ROLLBACK TO before_optional_step;
~~~

`ROLLBACK TO SAVEPOINT` undoes changes since the savepoint without ending the transaction. Changes before the savepoint remain.

### 7.1 SAVEPOINT Is Not a Nested Transaction

`SAVEPOINT` does not create an independent child transaction and has no separate COMMIT. Committing the transaction commits all remaining changes, both before and after the savepoint that were not rolled back.

### 7.2 Using Savepoints for Skippable Work

Example: a transaction updates an order and then tries writing optional data:

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :p_order_id;

SAVEPOINT before_optional_audit;

BEGIN
    INSERT INTO optional_order_note (order_id, note_text)
    VALUES (:p_order_id, :p_note);
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_audit;
        -- Only ignore if policy explicitly permits this step to be optional.
END;

-- The caller must still decide whether to COMMIT or ROLLBACK the transaction.
~~~

Only use this pattern when writing the note is genuinely non-mandatory for confirming the order. If auditing is a legal or mandatory business requirement, never swallow the error and continue.

### 7.3 Savepoints in Shared Procedures

Savepoint names belong to the current transaction, not a lexical scope local to each procedure. A procedure creating a savepoint with the same name as a caller's savepoint replaces that marker. If using internal savepoints, apply a dedicated naming convention and document behavior; many systems stay simpler by letting the caller manage rollback.

### 7.4 DDL Erases Savepoints

Oracle DDL triggers an implicit commit. Any savepoint created before DDL ceases to exist after the commit boundary. Never use `SAVEPOINT` expecting partial rollback across `CREATE`, `ALTER`, `DROP`, or `TRUNCATE`.

## 8. Classifying Errors: Retryable or Not?

Not every error should be retried. Retrying only helps when the cause is likely transient and the operation can safely repeat.

| Scenario | Oracle Example | Typically Appropriate Handling |
|---|---|---|
| Deadlock | ORA-00060 | Roll back unit of work, review lock order; bounded retry possible |
| Cannot serialize transaction | ORA-08177 | Roll back and retry entire transaction if business rules allow |
| Row locked with NOWAIT | ORA-00054 | Return busy status or bounded retry per SLA |
| Duplicate key/unique violation | ORA-00001 | Check if duplicate request or data conflict; never retry blindly |
| Parent not found for FK | ORA-02291 | Fix order/input or return business error; usually do not retry |
| FK violation due to child rows | ORA-02292 | Handle data relationships; never retry blindly |
| NULL not allowed | ORA-01400 | Fix input data or rules; do not retry |
| Value too large | ORA-12899 | Fix data or schema; do not retry |
| Invalid type conversion | ORA-01722 | Fix data/SQL; do not retry |
| User cancelled statement | ORA-01013 | Respect cancellation; do not auto-rerun |
| Snapshot too old | ORA-01555 | Review query duration, undo, and workload; do not treat as blindly retryable |
| Connection lost during COMMIT | Network/connection error | Commit outcome may be ambiguous; check via idempotency key before deciding |

The error code is only part of the picture. Consider where it occurred, transaction isolation, connection state, idempotency, and business rules.

### 8.1 ORA-00060: deadlock detected

Oracle detects a wait cycle and aborts one statement to break the deadlock. Earlier DML in the transaction may still remain. If the business operation involves multiple interdependent steps, the application should ROLLBACK the entire transaction before deciding to retry from the start.

Retrying only the failed statement while earlier changes remain in the transaction can produce confusing business states. Find the root cause of the deadlock and standardize lock ordering rather than merely bumping retry counts.

### 8.2 ORA-08177: can't serialize access

This error can occur when a transaction uses SERIALIZABLE and cannot maintain serializability against its chosen snapshot. Normally you must roll back the transaction and rerun the entire unit of work to obtain a fresh snapshot.

Never retry only the failed UPDATE statement if earlier logic read data and made decisions from a stale snapshot.

### 8.3 ORA-00054: resource busy

This error typically relates to a lock-requesting operation configured with `NOWAIT` or a timeout. If the resource is only briefly busy, you can return a busy status or perform a bounded retry after rolling back and releasing the current transaction's locks.

Never wait indefinitely. A request with a deadline must enforce a finite total wait budget.

### 8.4 ORA-00001: unique constraint violated

This is usually a data error or a sign the request was already processed, not a transient deadlock. If a table has a `UNIQUE` constraint on an idempotency key, a duplicate indicates a prior call already produced a result.

The application must query the record by key, verify payload/hash, and return the stored result if it is the exact same request. If the same key arrives with different content, return a conflict error instead of treating it as success.

## 9. Safe Retry Rules

### 9.1 Retry the Entire Business Unit

For concurrency errors like `ORA-08177` or deadlocks, you normally must:

1. Halt processing of the current unit of work.
2. ROLLBACK the transaction to discard remaining changes.
3. Release connections/locks appropriately.
4. Wait a short bounded interval.
5. Start a new transaction and re-read fresh data.
6. Re-execute all logic without reusing decisions computed from a stale snapshot.

Retrying a single isolated statement can be wrong if earlier steps affected business predicates.

### 9.2 Bounded Retries

Always cap:

- Attempt count, e.g., at most 3 retries after the initial attempt.
- Total retry duration against the request deadline.
- Maximum wait interval between attempts.
- Specific error types eligible for retry.

Never loop indefinitely. If a conflict repeats continuously, return an error or enqueue for deferred processing rather than holding requests and resources forever.

### 9.3 Exponential Backoff and Jitter

Exponential backoff increases the wait interval with each retry. Jitter adds randomness so multiple clients do not wake up and collide on the exact same lock simultaneously.

Illustrative formula:

\[
\text{delay}_k =
\min(\text{cap}, \text{base}\times 2^{k-1})
\times U(0.5, 1.5)
\]

Where `U` is a uniform random factor between `0.5` and `1.5`. For example, base 100 ms, cap 2 seconds, and max 4 attempts. Actual values must reflect target latency, load levels, and SLAs.

Crucial: roll back and release locks before sleeping. Never hold a transaction open during backoff.

### 9.4 Do Not Retry Permanent Data Errors

Errors such as value too long, wrong data type, missing foreign key, missing required value, or syntax errors will not vanish after a few hundred milliseconds. Retrying only increases load and latency.

Classify by error code and context; unclassified errors should default safely to non-retryable until an explicit policy is defined.

## 10. Idempotency: The Foundation of Safe Retries

An idempotent operation can be executed repeatedly without duplicating the final business outcome. This is essential whenever a client may resend a request after a timeout or disconnect.

### 10.1 Why Might a Request Be Resent?

Example:

1. Client sends an order creation request.
2. Database INSERTs and COMMITs successfully.
3. Response is lost on the network before reaching the client.
4. Client assumes the request failed and resends it.

If every submission INSERTs a new order, one user action creates two orders.

### 10.2 Idempotency Key

The client generates a stable request key for one business intent, such as a UUID. The database stores the key with a unique constraint:

~~~sql
CREATE TABLE api_request (
    request_key   VARCHAR2(64) PRIMARY KEY,
    payload_hash  VARCHAR2(128) NOT NULL,
    result_id     NUMBER,
    request_state VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Inside the order-creation transaction:

1. Attempt to INSERT the request key.
2. Create the order and related records.
3. Save `result_id` and completed status in `API_REQUEST`.
4. COMMIT in the same transaction.

If the request arrives again with the same key:

- If the record is already completed and the payload hash matches, return the stored result.
- If the key exists with a different payload hash, return a conflict error.
- If the prior request is still in-progress in a multi-step model, follow designed state/lease and recovery rules; never assume key existence automatically equals completed business work.

### 10.3 Unique Constraints Guard Against Races

Simply SELECTing to check that a key does not exist and then INSERTing is insufficient under concurrent sessions. Two sessions can both see no row yet. A `PRIMARY KEY`/`UNIQUE` constraint forces the database to accept only one key.

The losing session receives `ORA-00001` once the winning session commits. The application reads the request by key and determines whether the previous result can be returned.

### 10.4 Same Key Must Have Same Payload

Do not check `request_key` alone. Store a payload hash or sufficient business fields to confirm the repeated request carries identical content. If a client reuses a key for a different amount or account, never mistakenly return the old result.

The hash must be computed from a canonical payload representation with strict rules for field order, decimal formatting, encoding, and NULL values.

## 11. Ambiguous COMMIT Outcomes on Disconnect

This is a special scenario where blind retries must be avoided.

### 11.1 The Commit Request May Have Reached the Server

The client sends COMMIT, yet the connection drops before receiving the response. Two possibilities exist:

- Oracle committed, and the response was lost.
- Oracle did not commit, or the transaction rolled back when the session ended.

The client cannot infer from a network error alone that the transaction failed.

### 11.2 Never Resend Non-Idempotent Operations

If the operation creates an order, debits funds, or captures payment, resending immediately can double the effect if the first attempt committed.

Appropriate workflow:

1. Reuse the exact same idempotency key from the initial request.
2. Reconnect to the database.
3. Look up the request/operation status by key.
4. If already completed, return the stored result.
5. If nonexistent or confirmed incomplete, rerun per business rules.
6. If status remains indeterminable, keep it pending and reconcile; never invent a new request with a fresh key.

### 11.3 Distinguish Pre-COMMIT Errors from In-COMMIT Errors

If an error occurs before sending COMMIT and the connection/session closes, the uncommitted transaction is rolled back by Oracle when the session ends. However, if the error occurs during COMMIT and the response never reaches the client, the outcome may be ambiguous.

Retry code should therefore recognize which phase was executing. A connection drop during a SELECT differs fundamentally from a connection drop right at COMMIT.

## 12. Integrating with External Services: Transactional Outbox

Never keep a database transaction open while calling external services:

~~~text
BEGIN DB TRANSACTION
    UPDATE order
    Call payment provider
    Wait response
    UPDATE payment status
COMMIT
~~~

This flow holds locks across unreliable network calls. If the payment provider charges funds yet the response is lost, the database and provider fall out of sync.

### 12.1 Transactional Outbox Pattern

Within the same database transaction:

1. Update the order to a payment-pending status.
2. Write an event to an `OUTBOX` table.
3. COMMIT.

Example:

~~~sql
UPDATE orders
SET status = 'PAYMENT_PENDING'
WHERE order_id = :p_order_id;

INSERT INTO outbox_event (
    event_id,
    aggregate_id,
    event_type,
    payload,
    event_status,
    created_at
)
VALUES (
    :p_event_id,
    :p_order_id,
    'REQUEST_PAYMENT',
    :p_payload,
    'READY',
    SYSTIMESTAMP
);

COMMIT;
~~~

A worker reads `OUTBOX`, calls the payment provider with a stable idempotency key, and updates delivery status. The database transaction stays short, and the order/outbox changes commit together.

### 12.2 Why Does Outbox Still Need Idempotency?

A worker might:

1. Send the request successfully to the provider.
2. Have the provider process it successfully.
3. Crash before marking the event sent.
4. Restart and send the event a second time.

Thus the provider or consumer must deduplicate by event/request ID. An outbox typically delivers at-least-once semantics; it does not automatically guarantee exactly-once side effects on external systems.

### 12.3 Consumers Must Also Handle Duplicates

A consumer can store processed `EVENT_ID` values with a unique constraint. Upon receiving the same event again, it checks status and avoids applying the business effect twice.

## 13. Retries in Java/JDBC Applications

Java applications typically manage transactions via `Connection`:

~~~java
connection.setAutoCommit(false);
~~~

After executing DML statements:

~~~java
connection.commit();
~~~

On errors before commit:

~~~java
connection.rollback();
~~~

### 13.1 Retry Pseudocode Distinguishing Commit

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            Result result = executeBusinessUnit(connection, requestKey);

            // From here on, a COMMIT response failure can make the outcome ambiguous.
            try {
                connection.commit();
            } catch (SQLException commitError) {
                throw new CommitOutcomeUnknownException(
                    requestKey,
                    commitError
                );
            }

            return result;
        } catch (CommitOutcomeUnknownException e) {
            // Do not retry blindly. Look up requestKey using a fresh connection.
            throw e;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            if (!isRetryable(e) || attempt == maxAttempts) {
                throw e;
            }
        }
    }

    sleepWithBackoffAndJitter(attempt);
}
~~~

This pseudocode illustrates the structure, not a complete retry class for every driver. Add SQL error-code classification, deadlines, broken-connection handling, logging, and a commit-outcome reconciliation step via request key.

### 13.2 Returning Connections to the Pool in a Clean State

Before returning a connection to the pool:

- COMMIT or ROLLBACK the transaction per the actual outcome.
- Leave no unfinished transactions.
- Keep no unnecessary statements/result sets open.
- If the connection is broken or transaction state is indeterminable, evict the connection from the pool per driver/pool mechanics.

Never reuse a connection with an unknown state for the next request.

### 13.3 Do Not Stack Retries Across Multiple Layers Simultaneously

If the JDBC layer retries 3 times, the service layer retries 3 times, and the API gateway retries 3 times, one operation can run up to 27 times. Choose one primary retry-owning layer, or enforce a global retry budget across layers.

## 14. PL/SQL Example: Transfer with Scoped Rollback

The example below illustrates a transaction owned by the invoking block. Inside shared procedures, let the caller decide commit/rollback per the system's transaction contract.

### 14.1 Validate Parameters and Execute DML

~~~sql
DECLARE
    l_amount NUMBER := 100;
    l_from_id NUMBER := 10;
    l_to_id NUMBER := 20;
    l_rows PLS_INTEGER;
BEGIN
    IF l_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Amount must be positive');
    END IF;

    IF l_from_id = l_to_id THEN
        RAISE_APPLICATION_ERROR(-20011, 'Accounts must be different');
    END IF;

    UPDATE accounts
    SET balance = balance - l_amount
    WHERE account_id = l_from_id
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20012,
            'Source account missing or insufficient balance'
        );
    END IF;

    UPDATE accounts
    SET balance = balance + l_amount
    WHERE account_id = l_to_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20013, 'Destination account not found');
    END IF;

    INSERT INTO transfer_log (
        from_account_id,
        to_account_id,
        amount,
        created_at
    )
    VALUES (
        l_from_id,
        l_to_id,
        l_amount,
        SYSTIMESTAMP
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

This block owns its own transaction for illustration, so it ROLLBACKs everything on error and COMMITs when all steps succeed. Do not copy COMMIT/ROLLBACK verbatim from this block into a procedure invoked inside a larger application transaction.

### 14.2 Conditional Update Protecting Balance

The condition `BALANCE >= AMOUNT` sits directly inside the UPDATE. This avoids the race where two sessions both read a stale balance and both decide funds are sufficient.

Still, money transfers also require locking both accounts, deterministic lock ordering, destination account existence, balance limits, and a request idempotency key. The example above illustrates atomicity and `SQL%ROWCOUNT`, not a full production banking system.

### 14.3 Deadlock During Opposing Transfers

If one session transfers from account 10 to 20 and another transfers from 20 to 10, each session may lock its source first and wait on its destination, creating a deadlock. Production systems should lock accounts in the same deterministic order—such as ascending account ID—before executing debits/credits by source/destination role.

## 15. Queue Workers and Short Transactions

A worker pattern for processing queues:

### 15.1 Claim Work in a Short Transaction

~~~sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
~~~

After selecting a row, the worker updates:

~~~sql
UPDATE job_queue
SET status = 'PROCESSING',
    claimed_at = SYSTIMESTAMP,
    lease_until = SYSTIMESTAMP + INTERVAL '2' MINUTE,
    worker_id = :p_worker_id
WHERE job_id = :p_job_id;

COMMIT;
~~~

The claim transaction ends quickly and releases the lock. The worker performs the actual work outside any database transaction.

### 15.2 Complete in Another Transaction

After processing, the worker opens a short transaction:

~~~sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = SYSTIMESTAMP
WHERE job_id = :p_job_id
  AND worker_id = :p_worker_id
  AND status = 'PROCESSING';

COMMIT;
~~~

The `worker_id` and `status` predicates prevent a stale worker from mistakenly overwriting after its lease was reassigned to another worker. Systems must define lease expiry, heartbeats, and retry limits.

### 15.3 Worker Crashes Mid-Execution

If a worker crashes after performing an external side effect yet before marking `DONE`, the job may be reclaimed once its lease expires. Thus processing logic must be idempotent or use a deduplication key. Queue status alone does not guarantee side effects happen only once.

## 16. Batching and Chunked Commits

For jobs processing millions of rows, a single transaction may run too long and generate massive undo. You can split into batches if each batch is independent and safely resumable.

### 16.1 Key-Range Batch Pattern

A workflow can:

1. Select an unprocessed key range.
2. Update data within that range.
3. Write a checkpoint or batch ID in the same transaction.
4. COMMIT.
5. Advance to the next batch.

~~~sql
UPDATE large_table
SET processed_flag = 'Y'
WHERE id > :p_last_id
  AND id <= :p_next_id
  AND processed_flag = 'N';

UPDATE batch_checkpoint
SET last_id = :p_next_id,
    updated_at = SYSTIMESTAMP
WHERE job_name = 'PROCESS_LARGE_TABLE';

COMMIT;
~~~

Checkpoints and batch data should commit together so the checkpoint never advances ahead of unfinished data, or vice versa.

### 16.2 Do Not Commit Row-by-Row in a Loop Unnecessarily

Committing every row creates heavy round-trips/log syncs, lowers throughput, and leaves partial progress hard to manage. Use bulk DML or an appropriate batch size when business logic allows.

### 16.3 Choose Batch Size Based on Real Data

Batch size depends on:

- Row size and undo/redo volume.
- Lock hold duration.
- Log writer speed and I/O.
- Latency impact on online transactions.
- Retry capability and recovery time.

No single fixed batch size fits every system. Measure on a representative environment and tune against SLAs.

### 16.4 When Business Logic Requires All or Nothing

If all rows must change as one indivisible unit, maintain one atomic transaction even if it runs longer. Optimize queries, use set-based processing, avoid external operations, and size resources accordingly instead of committing mid-way and breaking business rules.

## 17. Logging and Error Observability

When retrying or rolling back, logs need enough context for analysis without exposing sensitive data.

Useful fields to log:

- Request ID or idempotency key.
- Business/object identifiers in a safe form.
- Processing step and operation name.
- Oracle error code, `SQLCODE`, `SQLERRM`.
- Retry attempt count and wait duration.
- Start/end timestamps and total latency.
- Whether commit outcome is confirmed or ambiguous.

In PL/SQL, `DBMS_APPLICATION_INFO` can tag module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CONFIRM_ORDER'
    );
END;
/
~~~

Applications can set `CLIENT_IDENTIFIER` to assist tracing sessions by controlled request/user. Never write passwords, tokens, card numbers, or sensitive payloads to logs.

### 17.1 Error Logging Must Not Lose the Original Error

If logging inside an exception handler also fails, ensure the original error is still preserved or reported. Never let a secondary error mask the primary error.

### 17.2 Transaction Logs and Independent Auditing

Logs written inside the same transaction will roll back with it. When failures must be persisted even if the business transaction rolls back, deliberately design independent logging—such as an autonomous-transaction logger or an external logging system. Autonomous transactions cannot see the main transaction's uncommitted changes and must avoid depending on uncommitted data.

## 18. End-to-End Retry Workflow

You can follow this workflow for a data-modifying request:

~~~text
Receive request + idempotency key
              |
              v
Check if request already completed?
       | Yes            | No
       v                v
Return stored       Start transaction
   result                |
                         v
                  Read/validate data
                         |
                         v
                  Execute atomic DML
                         |
                         v
                  Write result + outbox
                         |
                         v
                       COMMIT
                    /          \
              Success        Lost response
                  |               |
                  v               v
            Return result    Look up key
                                  |
                        +---------+---------+
                        |                   |
                    Committed          Incomplete
                        |                   |
                        v                   v
                  Return result       Retry per policy
~~~

If DML hits a retryable error before commit:

1. Roll back the transaction.
2. Log the error and attempt.
3. Release locks/connection.
4. Back off with jitter.
5. Start a new transaction and re-read fresh data.
6. Stop on success, permanent error, or exhausted retry budget.

## 19. Common Design Mistakes

| Design Mistake | Consequence | Improvement |
|---|---|---|
| Holding transaction during HTTP calls | Long locks, increased blocking | Commit data and outbox first; call external systems afterward |
| Unbounded retries | Uncontrolled load and waits | Enforce retry budget, deadlines, and attempt caps |
| Retrying only the failed SQL inside the old transaction | Retains prior changes and stale snapshot | Roll back and rerun the entire business unit where suitable |
| Retrying every ORA error | Pointlessly repeats data errors | Classify retryable vs. permanent errors |
| Omitting an idempotency key | Repeated requests duplicate orders/charges | Unique request key and persist outcome |
| Relying on SELECT before INSERT to prevent duplicates | Race conditions across sessions | `UNIQUE` constraint |
| Resending a fresh request after lost COMMIT response | Can execute business operation twice | Look up by the exact same idempotency key |
| Procedure self-COMMITting | Can commit caller's work | Define transaction ownership clearly |
| `WHEN OTHERS THEN NULL` | Masks errors and partial states | `RAISE` or return controlled errors |
| Sleeping while holding a transaction | Keeps holding locks while waiting | Roll back/commit before backing off |
| Locking multiple rows in inconsistent orders | Deadlocks | Standardize lock acquisition order |
| Splitting transactions when business requires atomicity | Invalid intermediate states | Keep one transaction or design a state machine/compensation |
| Committing row-by-row without checkpoints | Hard to resume and reconcile | Independent batches + checkpoint in same transaction |
| Calling external service before DB commit | External side effect succeeds while DB rolls back | Outbox, idempotency, and reconciliation workflows |
| Using `SKIP LOCKED` for user queries | Locked rows vanish from results | Use only for worker/queue semantics |

## 20. Transaction and Retry Design Checklist

Before shipping a business workflow to production, verify:

1. Which changes must succeed or fail together?
2. Where does the transaction start and who owns COMMIT/ROLLBACK?
3. Are any user waits, network calls, file I/O, or sleeps inside the active transaction?
4. Can a conditional DML statement replace SELECT-then-UPDATE?
5. Is `SELECT FOR UPDATE` or an optimistic version check needed?
6. When locking multiple rows, do all paths acquire locks in the exact same order?
7. Are appropriate `WAIT`/`NOWAIT` bounds configured?
8. Do exception handlers roll back the proper scope and preserve the root error?
9. Are savepoints used, and could they collide with the caller's savepoints?
10. Which Oracle error codes are permitted to retry?
11. Does retry roll back and start a fresh transaction?
12. Are retries bounded by attempt count, deadline, and backoff/jitter?
13. Does the request carry an idempotency key backed by a unique constraint?
14. If a COMMIT response is lost, can the outcome be resolved by key?
15. Do external side effects use an outbox or reliable synchronization mechanism?
16. Can workers/consumers receive the same event twice, and do they deduplicate?
17. Are batch checkpoints committed in the same transaction as batch data?
18. Do logs capture request ID, error code, and attempt without leaking sensitive data?

## 21. Practice Exercises

**Q1 — Atomicity.** A transaction debits account A and then credits account B. The second UPDATE fails. What happens if PL/SQL only executes `RAISE` and the caller does not roll back?

Hint: The failed statement rolls back, yet the first UPDATE remains in the transaction; the caller must roll back if the entire operation must be cancelled.

**Q2 — Short Transactions.** Why should you avoid calling a payment provider while holding `SELECT FOR UPDATE`?

Hint: The network can stall or time out, holding row locks long and blocking other sessions.

**Q3 — Optimistic Concurrency.** An UPDATE checking `VERSION_NO` returns `SQL%ROWCOUNT = 0`. What should you do?

Hint: Re-read fresh data, report conflict, or merge per rules; never loop endlessly on the same version.

**Q4 — Deadlock.** Two sessions lock accounts 10 and 20 in opposite orders. How do you reduce deadlocks?

Hint: Standardize lock ordering by ascending account ID.

**Q5 — Error Classification.** Should `ORA-12899` be retried after 500 ms?

Hint: No. Data exceeding column length is an input/schema error that will not resolve itself.

**Q6 — ORA-08177.** When a SERIALIZABLE transaction hits this error, should you retry the statement or the transaction?

Hint: Roll back and rerun the entire business unit against a fresh snapshot if retryable.

**Q7 — Unique Conflict.** What might `ORA-00001` on an idempotency key indicate?

Hint: A request with the same key was already recorded. Look up the outcome and compare payloads rather than retrying blindly.

**Q8 — Commit Outcome.** A client disconnects right while calling COMMIT. Why should it not create a brand-new request?

Hint: The commit may have succeeded while the response was lost. Use the same key to look up status.

**Q9 — Outbox.** Why does an outbox still require an idempotent consumer?

Hint: The worker may deliver successfully and crash before marking the event complete; the event can be redelivered.

**Q10 — Batching.** When committing in batches, when should the checkpoint be written?

Hint: Inside the exact same transaction as the batch data so progress state and data never drift apart.

## 22. Summary

Good transaction design in Oracle respects business boundaries and ends transactions promptly once atomic DML completes. Never hold locks while waiting on users or external services; choose conditional UPDATEs, `SELECT FOR UPDATE`, or optimistic version checks based on contention levels. On errors, remember a single SQL failure does not automatically roll back the entire transaction; the caller must own and execute COMMIT/ROLLBACK explicitly.

Retries require classification, bounds, backoff, and idempotency:

- `ORA-00060` and `ORA-08177` normally require rolling back and retrying the entire unit of work if permissible.
- `ORA-00054` may be a transient lock conflict, yet wait times must remain bounded.
- `ORA-00001` requires checking for duplicate requests/unique conflicts rather than blind retries.
- Data errors like `ORA-01400`, `ORA-02291`, or `ORA-12899` usually require fixing inputs or rules, not retrying.
- Disconnects during COMMIT can leave outcomes ambiguous; look up status via idempotency key before re-executing.
- Outboxes and idempotent consumers handle external side effects without prolonging database transactions.

When transactions stay short, errors are accurately classified, and requests can safely repeat, systems minimize blocking, avoid partial data, recover cleanly from contention, and maintain consistent behavior through network or worker failures.
