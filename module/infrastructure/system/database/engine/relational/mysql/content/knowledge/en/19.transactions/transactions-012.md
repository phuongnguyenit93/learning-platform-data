# Designing Short Transactions, Error Handling, and Controlled Retries

A MySQL transaction should wrap the exact portion of data work that must succeed or fail together. An overly long transaction holds locks for a long time, increasing lock waits, deadlocks, undo history, and response times. Conversely, a transaction that is too short or split along the wrong boundary can leave data in a half-finished state. Good design requires balancing atomicity, lock hold time, and recoverability from transient errors.

With InnoDB, applications should prepare data before opening a transaction, quickly execute database operations requiring atomicity, verify the result of each step, and commit or roll back immediately. When encountering a deadlock or lock wait timeout, perform a clean rollback and retry **the entire business unit** with a bounded retry limit. When the commit outcome is indeterminate due to connection loss, idempotency is required to avoid applying the business operation twice.

## 1. Transaction Boundaries Should Follow Business Units

A transaction should group changes that must be observed as a single business outcome. For example, order creation may include:

1. Recording the order.
2. Reserving or deducting inventory.
3. Recording order items.
4. Recording an event to be published after the order is confirmed.

If one step fails, related database changes must roll back together. However, sending emails, calling payment gateways, or waiting for user confirmation cannot be undone by MySQL's `ROLLBACK`. External actions outside the database need separate coordination mechanisms such as an outbox, idempotent consumers, or a saga.

Before designing a transaction, determine:

- Which business invariants must always hold true?
- Which rows/tables must change together?
- Which conditions must be checked under a lock or inside an atomic DML statement?
- When one step fails, must the entire unit of work be canceled?
- Are there external actions to dispatch after commit?

These boundaries prevent both extremes: committing too early and exposing a partial state, or extending a transaction across work that does not need database locks.

## 2. Why Must Transactions Be Short?

In InnoDB, a transaction can hold record locks, gap locks, or next-key locks until it ends. Long transactions increase the probability that other transactions must wait and create deadlock cycles.

Long-open transactions also retain older row versions needed for consistent reads. This can make undo history difficult to purge, increase undo storage size, and strain the system. Even a transaction reading a snapshot and leaving the connection idle for several minutes can cause operational issues without continuously running SQL statements.

Practical principles:

- Validate input and perform calculations not requiring locked data before opening a transaction.
- Open the transaction right before data operations requiring atomicity.
- Use indexes to locate exact rows and limit scan/lock scope.
- Lock multiple rows in a consistent order.
- Never make HTTP calls, send emails, upload files, wait for users, or sleep while a transaction is open.
- Commit or roll back immediately upon completing database work.
- Never return a connection with an unclosed transaction back to the connection pool.

## 3. Prepare Before the Transaction, Perform the Minimum Inside

For example, when creating an order, the application can do the following before the transaction:

- Validate request syntax and structure.
- Calculate totals from validated data, if the calculation does not depend on concurrent database state.
- Normalize product IDs and sort the ID list in a fixed order.
- Generate a request ID / idempotency key.
- Prepare the event payload to write to the outbox.

Then the transaction only executes steps needing synchronization with current data: confirming inventory, inserting the order, inserting order items, writing the outbox, and saving the idempotency result. Do not move a critical validation outside the transaction if the value can change concurrently before writing. For example, checking stock outside the transaction and deducting stock later creates a race condition.

## 4. Use Conditional UPDATE Instead of Read-Modify-Write When Possible

If you only need to reduce inventory when sufficient stock remains, a single conditional statement is usually shorter and safer than reading the quantity into the application and calculating there:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 501
  AND available_quantity >= 2;
```

The application checks affected rows:

- `1`: the condition was met and inventory was reduced.
- `0`: the product does not exist or inventory was insufficient per the condition.

If you need to distinguish between the two causes, you can run an additional read inside the same transaction under appropriate logic. Do not omit the `available_quantity >= 2` condition assuming an earlier application check still holds.

With InnoDB tables, the `UPDATE` statement is an atomic operation. Two transactions competing on the same product are coordinated via locks; the second statement evaluates the condition against the current row when executing the update. This is a useful pattern to shorten transaction duration and avoid lost updates.

## 5. Short Transaction Example for Placing Orders and Reserving Stock

Suppose there are tables for orders, inventory, order items, and outbox:

```sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
) ENGINE=InnoDB;

CREATE TABLE outbox_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_key VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_outbox_event_key (event_key)
) ENGINE=InnoDB;
```

The application prepares the request, validates format, and sorts `product_id` values before starting the transaction. Inside the transaction:

```sql
START TRANSACTION;

-- Iterate over product_id in ascending order.
-- Each UPDATE must affect exactly one row; otherwise, ROLLBACK.
UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 501
  AND available_quantity >= 2;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 502
  AND available_quantity >= 1;

-- After the application confirms both UPDATEs succeeded:
INSERT INTO orders (customer_id, total_amount, status)
VALUES (42, 250000.00, 'pending');

-- Application retrieves the newly created order_id on the same connection.
SET @order_id = LAST_INSERT_ID();
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (@order_id, 501, 2, 75000.00),
    (@order_id, 502, 1, 100000.00);

INSERT INTO outbox_events (event_key, event_type, payload)
VALUES (
    'order-created:request-abc',
    'OrderCreated',
    JSON_OBJECT('customer_id', 42, 'request_id', 'request-abc')
);

COMMIT;
```

This is an illustrative skeleton. In real code, obtain `order_id` immediately after the insert via your driver's generated-keys API or store it in a session variable on the same connection; do not invoke another operation that could overwrite `LAST_INSERT_ID()` between fetching the ID and inserting order items. If any inventory UPDATE affects 0 rows, the application must roll back and return an out-of-stock or invalid-product error. Never proceed to insert the order and commit.

After commit, a separate worker reads the outbox and dispatches the event. Sending notifications does not keep the order-creation transaction open during network waits.

## 6. Locking Multiple Rows in the Same Order

Deadlocks frequently occur when transactions lock the same set of rows in different orders:

- Transaction A locks product 501 and waits for 502.
- Transaction B locks product 502 and waits for 501.

To reduce risk, every workflow updating multiple products should lock or update them in the same order, such as ascending `product_id`. Sort the ID list in the application before executing statements inside the transaction.

If locks must be acquired before computing:

```sql
START TRANSACTION;

SELECT product_id, available_quantity
FROM inventory
WHERE product_id IN (501, 502)
ORDER BY product_id
FOR UPDATE;

-- Validate and update within the same transaction.

COMMIT;
```

The result ordering of `SELECT` is not an absolute guarantee of the internal order every locking plan will use in every situation. For complex workflows, inspect the actual access path and lock acquisition; a consistent access-ordering rule remains an important deadlock-reduction measure.

## 7. Good Indexes Keep Transactions Short and Locks Narrow

An `UPDATE` missing an index on its lookup condition may scan many more records than necessary. With locking reads or DML, the number of index records scanned affects lock scope and contention likelihood.

Example:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501
  AND available_quantity >= 1;
```

`product_id` is the primary key, so MySQL can locate the row directly. If a query filters on an unindexed column, evaluate appropriate indexes and inspect the execution plan with `EXPLAIN`.

Do not create indexes indiscriminately. Every index increases insert/update/delete overhead and storage size. Choose indexes based on workload, selectivity, and column ordering; check both query performance and write cost.

## 8. Distinguishing Retryable Errors from Business Errors

Not every SQL error should be retried. Some errors are transient due to contention, whereas others are data or business rule violations that will continue failing if resent with the same input.

| Error / Scenario | Common MySQL Code | How to Handle |
| --- | ---: | --- |
| Deadlock detected by InnoDB | `1213` (`ER_LOCK_DEADLOCK`) | Victim transaction is rolled back; entire transaction can be retried with a limit |
| Lock wait timeout | `1205` (`ER_LOCK_WAIT_TIMEOUT`) | Statement is rolled back by default; application should explicitly roll back the transaction before considering retry |
| NOWAIT failed to acquire lock | `3572` (`ER_LOCK_NOWAIT`) | Treat as resource busy; return error or follow a short, bounded retry policy |
| Duplicate key | `1062` (`ER_DUP_ENTRY`) | Usually a business/idempotency conflict; check existing record, do not retry blindly |
| Foreign key / check / data validation | E.g. `1452`, `3819`, `1406` | Fix data or return business error; do not retry with same input |
| Connection lost during commit | Possible connection error such as `2013` | Commit outcome may be indeterminate to client; look up via idempotency key before resending |

Deadlocks typically accompany SQLSTATE `40001`. Classify errors using SQLSTATE and the driver's vendor error code rather than matching text messages alone, because messages can change across versions or locales.

Error codes are only part of the picture. Applications should inspect SQLSTATE, vendor code, connection state, and the phase where the error occurred. Never retry all `HY000` errors or every network error as though they share identical semantics.

## 9. Deadlock: Roll Back the Entire Transaction and Retry Everything

When InnoDB detects a deadlock, it selects one transaction as the victim and rolls back that transaction. Statements executed earlier in the victim transaction are no longer effective.

The application must not merely re-run the last SQL statement. It must start a new transaction and re-run the entire business unit from the beginning, including necessary reads/checks. Values read in the previous attempt may now be stale; the new attempt must re-read current state.

Example handling logic:

```text
for attempt from 1 to MAX_ATTEMPTS:
    acquire connection
    begin transaction
    try:
        read current state
        validate conditions
        perform all database writes
        commit
        return success
    catch error:
        rollback if transaction is still active
        if error is retryable and attempt < MAX_ATTEMPTS:
            release connection
            wait with exponential backoff and jitter
            continue with a new transaction
        raise error
    finally:
        return only a clean connection to the pool
```

This is pseudocode, not SQL syntax. When retrying, use a new transaction; do not continue executing statements inside a transaction already rolled back by InnoDB.

## 10. Lock Wait Timeout Differs from Deadlock

When waiting for a lock exceeds `innodb_lock_wait_timeout`, InnoDB by default rolls back only the waiting statement, not necessarily the entire transaction. If `innodb_rollback_on_timeout` is enabled, full-transaction rollback behavior is applied.

Check configuration:

```sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
```

To keep application state simple and avoid holding locks from earlier parts of the transaction, the safe handling approach is usually to roll back the entire transaction after a timeout and then evaluate whether to retry the full business unit. Never assume a timeout always terminates the transaction automatically.

Before retrying, investigate the root cause of lock waits: another long-open transaction, missing indexes, inconsistent row access ordering, or overly wide range scans. Retrying repeatedly without reducing contention only adds load to the system.

## 11. Bounded Retries, Exponential Backoff, and Jitter

If multiple requests retry immediately after a deadlock, they may clash on the exact same rows again and trigger further deadlocks. Backoff spaces attempts apart; random jitter helps prevent multiple clients from waking up at the exact same instant.

A starting policy could be:

- At most 3 to 5 attempts per business unit.
- Exponentially increasing wait times, e.g., `base_delay * 2^(attempt - 1)`.
- Add random jitter within an appropriate range.
- Cap the wait time, e.g., a few hundred milliseconds up to roughly one second depending on SLA.
- Total retry time must stay within the request deadline.

Illustrative formula example:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
sleep_for(random(0, delay))
```

Numbers must be tuned according to system latency, throughput, and lock wait durations. Never sleep while holding a transaction or locks. Always roll back and release the connection/locks first before waiting.

## 12. Do Not Blindly Retry Business or Data Errors

The following cases usually cannot be resolved by retrying with the same data:

- Insufficient inventory.
- Locked account or insufficient balance.
- Data violating `NOT NULL`, `CHECK`, or `FOREIGN KEY`.
- Business key already exists and must be handled per duplicate rules.
- Input values exceeding column limits or having invalid format.
- User lacks permissions to perform the operation.

Retries are only suitable when the error is likely to clear after a short interval, such as a deadlock or transient lock contention. For data errors, return a meaningful result or ask the client to adjust the input.

## 13. Idempotency: Protecting Against Client Retries

A request may be resent due to client timeouts, repeated button clicks, proxy retries, or lost commit responses. If every resend creates a new order, a single business request could be executed multiple times.

An idempotency key is a unique identifier representing a single business request. The database uses a unique constraint to ensure a key is processed only once. Example result-storage table:

```sql
CREATE TABLE idempotency_requests (
    request_key VARCHAR(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_payload JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    PRIMARY KEY (request_key)
) ENGINE=InnoDB;
```

Within the same transaction as the business logic:

```sql
START TRANSACTION;

INSERT INTO idempotency_requests
    (request_key, request_hash, status)
VALUES
    ('request-abc', UNHEX(SHA2('{"customer_id":42}', 256)), 'processing');

-- Reserve inventory, create order, order_items, and outbox event.

UPDATE idempotency_requests
SET status = 'completed',
    response_payload = JSON_OBJECT('order_id', @order_id),
    completed_at = CURRENT_TIMESTAMP
WHERE request_key = 'request-abc';

COMMIT;
```

In production, use a request hash computed from a canonicalized payload rather than an arbitrary JSON string whose key order or formatting might vary. In the application, compute a deterministic hash and bind it via a prepared statement.

Within the same transaction, the application must assign `@order_id` to the ID just generated on the current connection (or pass the ID obtained from the driver's generated-keys API) before updating `response_payload`. The session variable only illustrates the SQL flow; the application can bind the ID directly into the `UPDATE` statement.

If another request uses the same `request_key`, the `INSERT` hits a duplicate key error once the first transaction commits. The application rolls back the duplicate attempt, reads the existing idempotency record, and returns the saved result if `request_hash` matches. If the same key has a different payload, return a conflict error; do not treat it as the same request.

If the first transaction rolls back before committing, the idempotency row is also rolled back; a retried request can create a new reservation and execute the business logic. Because the idempotency record and business changes live in the same transaction, their states cannot diverge.

## 14. Indeterminate Commit Outcome on Connection Loss

A tricky scenario occurs when the application sends `COMMIT`, MySQL processes and commits it successfully, but the connection drops before the client receives the response. The client cannot tell for certain whether the transaction committed from the network error alone.

Never assume every connection error during commit means rollback. Also never resend a non-idempotent operation with a new request ID, because the first transaction may already have succeeded.

Safe procedure:

1. Keep the original request's idempotency key unchanged.
2. Use a new connection to look up the outcome by key.
3. If status is `completed` and the hash matches, return the saved result.
4. If no record is found, you may retry with the same key per policy; the unique constraint protects you if the prior transaction actually committed.
5. If the same key has a different payload hash, return a conflict error and investigate.

Without idempotency or a unique business key, it is hard to distinguish "commit succeeded but response was lost" from "transaction did not commit." This is why idempotency is part of retry design, not just an API convenience.

## 15. Outbox: Moving Side Effects Outside the Transaction

If an event must be published after creating an order, write an outbox row inside the same transaction as the order. A worker reads unsent events and dispatches them to the message broker after commit.

Flow:

1. Transaction writes the order and the outbox event.
2. Commit confirms both.
3. Worker fetches unpublished events and sends them to the broker.
4. Worker marks events as published after receiving appropriate acknowledgment.
5. Consumer processes idempotently because the worker may resend if it crashes after sending but before marking.

Outbox ensures the event to be published is not lost from the database when the order-creation transaction commits. It does not automatically provide exactly-once delivery to the broker; typically the system achieves at-least-once delivery combined with consumer idempotency.

Do not call the broker or external APIs while the order-creation transaction is open. A slow network call can hold locks for a long time and cause a chain of lock waits for other requests.

## 16. Optimistic Locking for Low-Contention Updates

Not every business operation needs `SELECT ... FOR UPDATE`. For low-contention data, optimistic locking uses a version column to detect whether a row changed since the application read it:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    body TEXT NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id)
) ENGINE=InnoDB;
```

The application reads `version = 7`, edits the content, and writes:

```sql
UPDATE documents
SET body = 'New content',
    version = version + 1
WHERE document_id = 10
  AND version = 7;
```

If affected rows equals 1, the update succeeded. If it equals 0, the version changed or the row no longer exists; the application must re-read and handle the conflict rather than overwriting blindly. This approach fits when conflicts are rare and locks should not be held while a user is editing.

Optimistic locking does not replace transactions when a business operation updates multiple tables requiring atomicity. It is a row-level conflict detection technique.

## 17. Batch Processing and Long Jobs

Do not keep a single transaction open while processing hundreds of thousands or millions of records if business rules allow splitting. Dividing into reasonably sized batches helps:

- Reduce lock hold duration per batch.
- Reduce undo log size and the volume of data needing rollback.
- Reduce the impact of deadlocks and lock waits.
- Allow progress tracking and resuming from checkpoints.

Example workflow:

1. Determine a stable set of IDs to process.
2. Split into batches, such as a few hundred or a few thousand rows depending on row size and load.
3. Run each batch in its own transaction.
4. Save a checkpoint or processing status alongside the batch.
5. Retry only failed batches using an idempotent key.

Batching changes the atomicity boundary: the entire job is no longer atomic as a single transaction. Use it only when business logic accepts partial progress states and supports resuming/reconciliation. If all rows must succeed or fail together, you cannot arbitrarily split the transaction.

## 18. Managing Connections and Transaction State in Applications

A transaction belongs to a single connection. Every statement requiring atomicity must execute on the same connection and inside the same transaction.

An application-layer management pattern:

```text
connection = pool.acquire()
try:
    begin transaction on connection
    try:
        execute all database steps on this connection
        verify affected-row counts
        commit on this connection
    catch error:
        rollback if the connection is usable
        throw error
finally:
    ensure no transaction remains open
    return a clean connection to the pool
```

If rollback fails because the connection died, do not return that connection to the pool as if it were clean; discard it or let the driver handle it per pool policy. When a connection is reused, ensure autocommit, isolation level, session variables, and transaction state match the expected configuration.

Never open a transaction on connection A, execute a statement on connection B, and expect committing A to confirm both. Doing so breaks transaction boundaries.

## 19. Observing Long Transactions and Lock Wait Causes

When transactions are slow, find the root cause rather than immediately raising timeouts or adding more retries.

Inspect open transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Inspect InnoDB status:

```sql
SHOW ENGINE INNODB STATUS\G
```

On MySQL 8.0, `performance_schema.data_locks` and `performance_schema.data_lock_waits` help inspect locks and lock wait relationships. Read privileges and Performance Schema settings must be appropriate for the environment.

Signs to watch out for:

- A transaction open for a long time with no currently running query.
- A connection holding locks while the application waits on an external service.
- Lock waits concentrated on the same table or hot row.
- Query plans scanning too many rows due to missing indexes or non-sargable conditions.
- Repeated deadlocks between the same update flows acquiring locks in different orders.
- Growing undo history due to prolonged transaction snapshots.

Log transaction duration, retry counts, error codes, lock wait time, and request IDs. Do not log sensitive data unnecessarily.

## 20. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | How to Handle |
| --- | --- | --- |
| Longer transactions are safer | Long transactions hold locks and undo history longer | Wrap only operations requiring atomicity |
| Can call external APIs inside a transaction and roll back on failure | MySQL rollback cannot undo external services | Use outbox/saga or compensating actions |
| Deadlock only needs retrying the last SQL statement | InnoDB rolls back the entire victim transaction | Retry the entire business unit in a new transaction |
| Lock wait timeout always rolls back the entire transaction | By default only the statement rolls back; configuration can change this | Roll back explicitly before retrying |
| Retry every database error | Data/business errors do not fix themselves when resent | Retry only classified transient errors |
| Immediate retry is enough | Multiple clients may contend again simultaneously | Use backoff, jitter, and retry limits |
| Losing connection on COMMIT means rollback | Commit may have succeeded while response was lost | Look up by idempotency key |
| Idempotency key is only needed at the API | Uniqueness must be protected by a unique constraint in the database | Save key and result inside the business transaction |
| Outbox guarantees exactly-once delivery | Workers may resend if crashing after dispatch | Consumers must be idempotent |
| Batching still keeps full-job atomicity | Each batch commits independently | Split only when business logic allows partial progress |
| Can return a connection with an open transaction to the pool | Next request may inherit old state and locks | Commit/roll back, reset, or evict the connection |

## 21. Transaction Design and Retry Process

When building a critical write operation, follow this sequence:

1. **Define invariants:** what data must always remain valid after the operation?
2. **Finalize boundaries:** which changes must commit/roll back together?
3. **Prepare upfront:** validate the request, normalize data, and generate an idempotency key outside the transaction.
4. **Optimize access paths:** are there indexes for row lookup and locking conditions?
5. **Standardize lock ordering:** all flows touching multiple rows access them in the same order.
6. **Open transactions late:** only right before the reads/writes needing consistency.
7. **Minimize statements:** use conditional DML where suitable; check affected rows.
8. **Write outbox and idempotency:** in the same transaction as business changes.
9. **Commit early:** never hold a transaction while calling external services.
10. **Classify errors:** deadlock, timeout, duplicate, validation, or connection failure.
11. **Roll back cleanly:** never retry inside a failed transaction.
12. **Retry with bounds:** new transaction, re-read state, exponential backoff, and jitter.
13. **Handle uncertain commits:** look up with the same idempotency key before re-executing.
14. **Observe and improve:** monitor transaction duration, lock waits, deadlocks, and retry rates.

## 22. Practice Exercises

1. Write an order-placement transaction deducting stock, creating an order, and inserting order items; roll back if any product lacks sufficient quantity.
2. Revise the flow using `UPDATE ... WHERE available_quantity >= ?` and checking affected rows.
3. Create two sessions updating two products in opposite orders to observe a deadlock; then standardize access order.
4. Trigger a lock wait timeout and compare behavior with `innodb_rollback_on_timeout` on/off in a lab environment.
5. Write full-transaction retry pseudocode with at most 3 attempts and exponential backoff with jitter.
6. Create an idempotency table with primary key `request_key`; send the same request twice and verify only one order is created.
7. Try sending the same idempotency key with a different payload hash; design the conflict response.
8. Simulate losing response after commit by disconnecting the client at the right moment in a test environment; verify the outcome using the idempotency key.
9. Write an outbox event in the same transaction as creating an order; build a worker to send events and an idempotent consumer.
10. Add a `version` column to a documents table and test optimistic locking with two clients updating concurrently.
11. Split a large update job into batches; design checkpoints, retries, and reconciliation to resume after failures.
12. Use `information_schema.innodb_trx`, `SHOW ENGINE INNODB STATUS`, and Performance Schema to locate long transactions or lock waits.

## 23. Key Takeaways

A transaction should enclose the exact business unit of work needing atomicity and end as soon as possible. Prepare data beforehand, use appropriate indexes, perform conditional updates, lock multiple rows in a consistent order, and never call external services while holding a transaction.

Deadlock (`1213`) causes InnoDB to roll back the entire victim transaction; lock wait timeout (`1205`) rolls back only the statement by default, so applications usually need to roll back everything before retrying. Retries must re-run the entire business logic in a new transaction with limits, exponential backoff, and jitter; never blindly retry validation or duplicate errors. When losing connection during commit, the outcome may be unclear to the client: use an idempotency key protected by a unique constraint to look up or safely resend. Outbox moves side effects after commit, while consumers must be idempotent. Monitor transaction duration, lock waits, deadlocks, retries, and connection pools to catch issues before they become data incidents.
