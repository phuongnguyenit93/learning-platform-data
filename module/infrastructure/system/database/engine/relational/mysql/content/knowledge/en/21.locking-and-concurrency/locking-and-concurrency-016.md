# Designing concurrency-safe and retry-safe operations

A business operation may be submitted multiple times, executed concurrently by multiple workers, or interrupted right after the database has committed. Relying solely on statement ordering in application code makes it easy to deduct inventory twice, overwrite newer updates, or create duplicate transactions. Proper design requires enforcing data invariants inside the database, defining clear transaction boundaries, and making retries predictable.

With MySQL/InnoDB, you can combine atomic updates, pessimistic locking, optimistic version control, unique constraints, and idempotency keys. When a deadlock or timeout occurs, the application must re-run the entire business unit in a new transaction. When a connection drops during `COMMIT`, the outcome may be unknown; an idempotency key lets you determine whether the operation was already processed.

## Objectives

After this lesson, you will be able to:

- Identify data invariants and enforce them directly in SQL statements or schema constraints.
- Use atomic updates to avoid read-then-write bugs under concurrent transactions.
- Choose pessimistic locking or optimistic locking according to contention levels.
- Design short transactions, consistent lock acquisition ordering, and clear processing boundaries.
- Use idempotency keys to prevent duplicate execution on client retries.
- Distinguish retryable errors from business errors and indeterminate `COMMIT` outcomes.
- Use a transactional outbox when a transaction must emit events or call external services.

Examples assume MySQL 8.0 or later, InnoDB tables, and input validation in the application before sending SQL.

## 1. Start from data invariants

An invariant is a condition that must always hold true after every committed operation. For example:

- Inventory must never go negative.
- Account balance must never go negative if business rules forbid overdrafts.
- A payment request code must be recorded at most once.
- An order must belong to a valid customer.
- An order's total amount and status must stay consistent with its line items.

Identify invariants before choosing a locking approach. Then place protection as close to the data as possible: `NOT NULL`, `UNIQUE`, foreign keys, appropriate `CHECK` constraints, and predicates inside `UPDATE`. Application-layer checks remain necessary for returning clear user messages, but cannot replace database enforcement because two requests can read the same value before either writes.

For example, a flow that reads inventory first and then decides to deduct stock has a race condition:

```sql
SELECT available
FROM inventory
WHERE product_id = 10;
```

If two workers both read `available = 5`, both can conclude enough stock exists to fulfill an order for 4 units. When both subsequently write results calculated from the stale value, data becomes corrupt. The bug lies in the gap between the read step and the write step.

## 2. Prefer atomic updates when business rules allow

If the rule can be expressed in a single statement, move the check condition directly into the `UPDATE` statement itself:

```sql
UPDATE inventory
SET available = available - 4,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 10
  AND available >= 4;
```

InnoDB evaluates the check and modifies the row under the statement's locking. Two transactions cannot both use a stale value to push inventory negative. The application checks affected rows immediately after the statement:

```sql
SELECT ROW_COUNT();
```

If the result is `1`, inventory was deducted. If `0`, either the product does not exist or stock is insufficient. If you must distinguish the two cases, run an additional query inside the same transaction per business requirements. This example assumes the deducted quantity is positive; the application must reject zero or negative quantities before issuing SQL.

When inventory deduction must accompany order recording, put both changes inside one transaction:

```sql
START TRANSACTION;

UPDATE inventory
SET available = available - 4,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 10
  AND available >= 4;

-- Application checks ROW_COUNT() must equal 1.
-- If 0, ROLLBACK and return out-of-stock result.

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (7001, 10, 4);

COMMIT;
```

If the `INSERT` fails, the transaction must `ROLLBACK` to restore the deducted quantity. In application code, checking affected rows and ending the transaction must execute on the exact same connection.

## 3. Pessimistic locking when you must read before deciding

Some business flows must read multiple columns or rows, compute values, and then update. When the decision must rely on current state, use `SELECT ... FOR UPDATE` inside a transaction:

```sql
START TRANSACTION;

SELECT available, reorder_level
FROM inventory
WHERE product_id = 10
FOR UPDATE;

-- Application checks conditions and computes order quantity.
UPDATE inventory
SET available = available - 4
WHERE product_id = 10
  AND available >= 4;

COMMIT;
```

`FOR UPDATE` requests a current read and holds the appropriate write lock until the transaction ends. Other transactions attempting to modify that row must wait. Use pessimistic locking when conflicts are frequent or logic genuinely requires holding the read state steady for the remainder of the transaction.

Principles for using it:

1. Use proper indexes to locate exact rows to lock. Broad range scans can hold more locks than expected.
2. Open the transaction right before acquiring locks and end it immediately after finishing changes.
3. Never wait on users, make HTTP calls, send emails, or run slow work while holding locks.
4. If multiple rows must be locked, acquire locks in a stable order, such as ascending primary key.
5. Check affected row counts and roll back if any business step fails its condition.

### Example: transferring funds between two accounts

Suppose we need to transfer 100 units from account 100 to account 200. Every transfer flow must lock accounts in ascending `account_id` order, regardless of transfer direction, to reduce deadlock risk:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 100
FOR UPDATE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 200
FOR UPDATE;

-- Application confirms both accounts exist and source balance is sufficient.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 100
  AND balance >= 100;

-- If ROW_COUNT() is not 1: ROLLBACK.
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 200;

-- Confirm ROW_COUNT() equals 1 for both UPDATEs.
-- If not met, ROLLBACK instead of writing ledger.
-- Write the ledger/transfer record in the same transaction.
COMMIT;
```

For a transfer in the opposite direction, the application still locks account 100 first and then account 200, and only afterward applies source and destination roles. Consistent lock ordering prevents one transaction from locking A and waiting for B while another locks B and waits for A. Proper ordering reduces deadlocks, though it does not eliminate deadlocks caused by other tables, indexes, or flows.

In a real system, record a transfer entry with a unique business code, verify positive amounts, verify source and destination accounts differ if required, and confirm both updates succeeded before `COMMIT`.

## 4. Optimistic locking with a version column

When conflicts are rare and you do not want to hold locks while users edit data, use optimistic locking. Each row has a version column:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

When reading a document, the application retrieves `version` as well. When saving, it requires `version` to still match the value read earlier:

```sql
UPDATE documents
SET title = 'Updated plan',
    body = 'New content',
    version = version + 1
WHERE document_id = 501
  AND version = 7;
```

If `ROW_COUNT()` equals `1`, the update succeeded and the new version is `8`. If it equals `0`, the row was deleted or another transaction updated it first; the application must reload the data and ask the user to resolve the conflict or apply merge rules. Never silently overwrite with stale data, as that loses someone else's edits.

Incrementing `version` in the same statement ensures every successful update changes the row, so affected row count detects conflicts reliably. Do not merely inspect the value from an earlier `SELECT`; the `WHERE version = ?` condition is the atomic compare-and-set step.

## 5. Using constraints to prevent race conditions

The `SELECT`-to-check then `INSERT` pattern is normally unsafe:

```sql
SELECT COUNT(*)
FROM users
WHERE email = 'lan@example.com';

-- If not yet present, INSERT.
```

Two transactions can both observe `0` and both attempt to insert. The proper protection is placing a unique constraint:

```sql
ALTER TABLE users
ADD CONSTRAINT uq_users_email UNIQUE (email);
```

Then execute `INSERT` and handle the duplicate-key error (`1062`) as a business outcome arbitrated by the database. If duplicate emails are forbidden, the unique constraint is the final guarantee even when multiple applications or workers write concurrently.

Commonly used constraints:

- `PRIMARY KEY` and `UNIQUE` to enforce identity and uniqueness.
- `NOT NULL` to prevent missing required values.
- `FOREIGN KEY` to enforce referential relationships.
- `CHECK` to express single-row invariants; MySQL enforces `CHECK` starting in version 8.0.16.

Never use `INSERT IGNORE` casually to mask errors. It can skip offending rows and emit warnings, fooling the application into believing the whole operation succeeded. Distinguish expected duplicate keys from other data errors.

## 6. Idempotency keys to prevent duplicate execution

A request may be resent due to client timeouts, repeated button clicks, proxy retries, or worker message redelivery. If each submission creates a new transaction, operations like payments, orders, or point deductions can execute multiple times.

**Idempotency** means receiving the same logical request multiple times produces the exact same business outcome as processing it once. A common implementation has the client send a unique key per logical operation; the server stores that key alongside the outcome in the database.

Example request-tracking table:

```sql
CREATE TABLE idempotency_requests (
    request_key VARBINARY(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    request_status ENUM('PROCESSING', 'COMPLETED') NOT NULL,
    response_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (request_key)
) ENGINE = InnoDB;
```

Upon receiving a transfer request, the server starts a transaction and attempts to record `request_key` before applying changes:

```sql
START TRANSACTION;

INSERT INTO idempotency_requests
    (request_key, request_hash, request_status)
VALUES
    ('transfer-req-9f82', UNHEX(SHA2('{"from":100,"to":200,"amount":100}', 256)), 'PROCESSING');

-- Execute business logic only when INSERT succeeds.
-- Lock accounts in a consistent order, check balance,
-- update both accounts, and write the transfer ledger.

UPDATE idempotency_requests
SET request_status = 'COMPLETED',
    response_payload = JSON_OBJECT(
        'transfer_id', 88001,
        'status', 'COMPLETED'
    )
WHERE request_key = 'transfer-req-9f82';

COMMIT;
```

This is a single transaction: the idempotency record, balance updates, ledger, and stored response commit or roll back together. A concurrent request reusing the same `request_key` hits the unique key; its insert may wait for the first transaction to finish. If the first transaction commits, the second request gets a duplicate-key error and must not execute the business logic again. If the first transaction rolls back, the second request can insert the key and become the executing request.

When hitting a duplicate key:

1. Roll back the current transaction.
2. Read the `idempotency_requests` record in a fresh transaction or autocommit.
3. Compare `request_hash` against the current request's content. Reusing a key with a different payload must be rejected; never return the result of a different operation.
4. If the status is `COMPLETED`, return the stored `response_payload`.

In the design above, the `PROCESSING` state is not committed separately, so other clients do not observe it while the logic is running. This is intentional so database changes remain atomic. If a workflow must maintain processing status across multiple transactions or long external calls, design explicit leases, timeouts, processing ownership, and recovery rules; never hold a database transaction open while waiting on an external service.

Idempotency keys must be retained long enough to cover the window during which clients may retry. Cleanup policies must account for maximum retry windows and audit requirements. Never reuse a key for a different logical operation.

`request_hash` should be computed from a canonical representation of the payload, containing business-significant fields in a stable order and format. Do not hash raw client-sent JSON text directly if the same logical payload can serialize into different strings. The SQL example above illustrates storing SHA-256 in binary form; in real applications, compute the hash in the service layer and pass the 32-byte value into the `INSERT`.

## 7. Retrying properly when a transaction fails

Not every error should be retried. First, classify errors by cause:

| Error | Common meaning | Handling |
|---|---|---|
| Deadlock, MySQL error `1213`, SQLSTATE `40001` | InnoDB selected this transaction as victim and rolled it back | Re-run the entire business unit in a fresh transaction if safe to retry |
| Lock wait timeout, error `1205` | Transaction waited for a lock beyond configured duration | By default InnoDB rolls back only the timed-out statement; application should roll back the entire business transaction before considering retry |
| Duplicate key, error `1062` | Unique constraint violation or idempotency request already exists | Handle per business rules; do not retry blindly |
| Validation, syntax, privilege, or invalid foreign key | Request or statement has a deterministic error | Fix data/statement/privileges; retrying will not solve it |
| Connection lost during `COMMIT` | Client does not know whether server committed | Look up by idempotency key or business code before deciding to resend |

### Retry the entire transaction

A deadlock causes InnoDB to roll back the entire chosen victim transaction. For a lock wait timeout, by default only the timed-out statement is rolled back unless `innodb_rollback_on_timeout` alters that behavior. Therefore, the safe application-layer approach is rolling back the entire logical transaction after a retryable error, then starting a new transaction and re-reading state.

Never re-run only the last SQL statement. Earlier decisions may have relied on stale data or earlier steps may have been rolled back. Restart from the beginning of the business unit with clear transaction boundaries.

Conceptual handling flow:

```text
Start new transaction
        |
Execute full business logic
        |
      COMMIT
        |
   Succeeded? ---- Yes ----> Return result
        |
       No
        |
ROLLBACK (if connection still usable)
        |
Retryable error and attempts left?
        | Yes                | No
        v                    v
Wait backoff + jitter    Return error/escalate
        |
Loop back to new transaction
```

Exponential backoff with jitter prevents workers from retrying simultaneously in lockstep:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
sleep(random(0, delay))
```

Cap both retry attempts and total elapsed time. Sleep after the old transaction has ended so you do not hold locks while sleeping. If the request deadline expires, return a retryable status or hand off work to an appropriate queue.

### Connection lost right at COMMIT

This is a special case. The server may have committed successfully before the response reached the client, or the server may not have committed. The client knows only that the connection dropped, not the final outcome. Resending a non-idempotent `UPDATE balance = balance - 100` can deduct funds a second time.

With an idempotency key, the client resends the same key and payload. The server checks the idempotency table: if the prior operation committed, return the stored result; if not committed, the request can be processed. Without an idempotency key or unique business identifier, query state using a business identifier before deciding to retry.

## 8. Transactions do not span external services

An InnoDB transaction governs only changes inside databases participating in that transaction. It cannot roll back a sent email, an API call accepted by another service, or a payment completed at a payment gateway.

Never hold a transaction and row locks open while calling an external service. A common pattern is the **transactional outbox**:

1. Within the same transaction, update business data and insert an event into an `outbox` table.
2. Commit the transaction. If the transaction rolls back, neither the business changes nor the event exist.
3. A separate worker reads unsent events, publishes them to a broker or target service, and marks them sent.
4. Consumers process events keyed by unique `event_id` to prevent duplicate effects if the worker resends after a timeout.

An outbox normally provides at-least-once delivery, because a worker can publish successfully and lose connectivity before marking the row sent. Consumers must be idempotent or maintain a deduplication table. Never promise "exactly once" across multiple systems using only a MySQL transaction.

When calling a payment gateway, generate a business idempotency key and send it with every retry to the payment gateway if the service supports it. Both the database and payment gateway need the same reference code to reconcile status when network outcomes are uncertain.

## 9. Checklist for designing concurrent operations

Before deploying an important write operation, answer:

- Which invariant must always remain true after commit?
- Can the condition and change be expressed in a single atomic `UPDATE`?
- If multiple steps are required, does the transaction cover all related database changes?
- Is `FOR UPDATE` needed, or is optimistic locking via a version column sufficient?
- Do transactions acquire locks in the same consistent order?
- Is there a unique constraint to block duplicate records at the database layer?
- Does the request carry an idempotency key or unique business identifier?
- Are deadlock, timeout, duplicate-key, and connection-lost-at-commit errors classified separately?
- Does retry re-run the entire transaction with an attempt cap and backoff?
- Are emails, HTTP calls, brokers, or payments decoupled from transactions via an outbox or idempotent mechanism?

## 10. Practice exercises

Assume tables `inventory(product_id, available)`, `accounts(account_id, balance)`, and `documents(document_id, title, body, version)`.

1. Write an `UPDATE` statement that deducts 3 items from inventory only when `available >= 3`. Explain how the application distinguishes success from out-of-stock.
2. Open two sessions both ordering quantity 4 when inventory is 5. Execute the atomic update in both sessions and observe the results.
3. Write a transfer of 100 units between two accounts, locking both rows in ascending `account_id` order and writing a ledger entry in the same transaction.
4. Write an optimistic locking `UPDATE` for a document with `version = 12`. Describe how to handle affected rows equal to 0.
5. Design a unique key on `request_key`. Simulate two concurrent requests using the same key and determine which request is allowed to run the business logic.
6. Classify deadlock, lock wait timeout, duplicate key, and connection drop right after `COMMIT`. For each case, state whether to retry and where execution must restart.
7. Sketch an outbox table and rules allowing a consumer to process the same `event_id` multiple times without repeating business side effects.

## Key takeaways

- Protect invariants with atomic statements and database constraints; never rely on separate read-then-write patterns.
- Use pessimistic locking when you must hold current state steady inside a transaction; use a version column when detecting concurrent overwrites.
- Keep transactions short, use appropriate indexes, and acquire multiple locks in a stable order.
- Idempotency keys prevent retried requests from running the same business logic twice; the same key must bind to the same payload.
- After a deadlock or timeout, roll back the business unit and retry the entire transaction in a new session when the error is retryable.
- Losing connection at `COMMIT` yields an indeterminate outcome; look up status via the idempotency key before re-executing.
- Decouple external side effects from transactions using an outbox and make consumers idempotent.
