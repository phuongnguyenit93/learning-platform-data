# Business Keys, Idempotency, and Duplicate Event Protection

In systems with concurrent requests, workers, and services writing to MySQL, a business operation can be delivered multiple times. A user clicks the pay button twice, a client retries after a timeout, a message broker redelivers an event after a consumer disconnects, or two workers process the same order simultaneously. If every delivery produces a new side effect, the system can create duplicate orders, double-charge accounts, or send duplicate notifications.

Handling this safely requires combining three layers: unique business keys in the database, request/consumer idempotency, and transactions ensuring processing markers are persisted atomically with data mutations. Row locks serialize competing updates; unique constraints act as the final arbiter for operations that must occur once. For message-broker integrations, inbox/outbox patterns handle duplicate deliveries without assuming the network can guarantee end-to-end exactly-once delivery.

This lesson uses MySQL 8.4, InnoDB, and Java/Spring at an illustrative level. The patterns also apply to other services connecting to MySQL via JDBC.

## Objectives

After this lesson, you will be able to:

- Distinguish business keys, surrogate/primary keys, row locks, and idempotency keys.
- Use unique constraints to block two requests from creating the same business effect.
- Design tables storing idempotency keys and request fingerprints.
- Handle repeated requests by replaying stored results.
- Use the inbox pattern to prevent duplicate event processing within the same transaction as business updates.
- Use a transactional outbox to persist business changes and events atomically.
- Choose pessimistic locking, optimistic locking, or compare-and-set based on contention patterns.
- Handle deadlocks, lock timeouts, retries, and idempotency record retention.
- Understand the limits of exactly-once claims in distributed systems.

## 1. Types of Keys and Problems to Solve

The following concepts are related yet do not replace one another:

| Concept | Purpose | Example |
|---|---|---|
| Business key | Identifies an entity or operation per business rules | Partner order code, payment transaction ID |
| Primary key | Uniquely identifies a row in the database | `orders.id` |
| Unique constraint | Ensures a value or combination of values never appears twice | `UNIQUE(provider, provider_transaction_id)` |
| Row lock | Serializes concurrent operations on existing rows | `SELECT ... FOR UPDATE` |
| Optimistic version | Detects a transaction updating data modified concurrently | `version` column or JPA `@Version` |
| Idempotency key | Identifies retries of the same logical request | `Idempotency-Key` header |
| Event ID / inbox key | Identifies an event already processed by a consumer | `(consumer_name, event_id)` |

Row locks do not replace unique constraints. Two transactions can both check for a non-existent key and then both attempt to insert; only a unique constraint atomically decides one winner. Conversely, a unique constraint alone does not ensure a multi-step flow executes in valid business order; transactions and row locks still have their own roles.

## 2. Starting from Unique Business Keys

Suppose a partner submits orders with its own reference number. An order from the same partner must never be created twice:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    merchant_id BIGINT UNSIGNED NOT NULL,
    external_order_no VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_orders_merchant_external (
        merchant_id, external_order_no
    )
) ENGINE = InnoDB;
```

The unique key `(merchant_id, external_order_no)` encodes the business rule: the same merchant cannot have two orders with the same external reference number. If the same code is valid across two different merchants, `merchant_id` must be part of the unique key.

Do not rely solely on a `SELECT` check before `INSERT`:

```sql
SELECT id
FROM orders
WHERE merchant_id = 42
  AND external_order_no = 'EXT-2026-001';

-- Only INSERT afterward if no row was found.
```

Two concurrent requests can both see no row and then both insert. This is a check-then-act race condition. The fix is defining a unique constraint and letting InnoDB arbitrate atomically:

```sql
INSERT INTO orders (
    merchant_id, external_order_no, status,
    total_amount, created_at
)
VALUES (42, 'EXT-2026-001', 'PENDING', 125000.00, NOW(6));
```

One request succeeds; the other receives a duplicate-key error. The application should read the existing row, compare business data, and return the appropriate response. If the same business key arrives with a different payload, never silently overwrite the existing order.

### 2.1. Choosing the Scope of a Business Key

Before creating a unique key, answer:

- Which scope owns uniqueness: system-wide, tenant, merchant, or operation type?
- Is the key case-sensitive?
- Is whitespace or Unicode normalization needed?
- Can the key be reused after cancellation or deletion?
- Must historical data be retained permanently?

For codes issued by external systems, define explicit comparison rules. A case-insensitive collation can treat `abc-01` and `ABC-01` as identical keys. If a partner defines codes as byte-sensitive, use binary types/collations or normalize prior to storage.

### 2.2. Duplicate Keys as a Business Outcome to Handle

Not every duplicate-key error is a system bug. It may indicate the request was already processed. Distinguish which constraint was violated:

- Duplicate order business key: look up the existing order and verify payload equivalence.
- Duplicate payment gateway transaction ID: do not record the payment a second time.
- Duplicate event inbox key: the consumer already processed that event.
- Duplicate unrelated unique key: likely a genuine data bug that should raise an error.

Never catch every `DuplicateKeyException` and blindly return HTTP 200. Treat it as an already-processed duplicate only after locating the exact operation's unique key and verifying matching content.

## 3. Idempotency for HTTP/API Requests

### 3.1. What Does Idempotency Mean?

An operation is idempotent if re-executing the same logical request causes no additional business side effects. For example, resending a payment creation request with the same idempotency key must return the previously created payment result rather than creating a second charge.

Idempotency keys are typically sent by clients in headers:

```http
POST /payments
Idempotency-Key: 2d1f8d9e-8c6a-4b8d-a6f7-4c1a1a2b3c4d
Content-Type: application/json

{
  "orderId": 8123,
  "amount": 125000
}
```

The server must scope keys by tenant, endpoint/operation, and retention window. A random key does not make a request idempotent on its own; the server must persist the key and outcome in the database.

### 3.2. Idempotency Key Storage Table

Example schema:

```sql
CREATE TABLE api_idempotency (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    operation VARCHAR(80)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARBINARY(128) NOT NULL,
    owner_token BINARY(16) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    state ENUM('PROCESSING', 'SUCCEEDED') NOT NULL,
    response_code SMALLINT UNSIGNED NULL,
    response_body JSON NULL,
    resource_id BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_idempotency_scope (
        tenant_id, operation, idempotency_key
    ),
    KEY idx_idempotency_created (created_at)
) ENGINE = InnoDB;
```

Column roles:

- `tenant_id` and `operation` scope the key. Two different APIs can use the same key string without colliding.
- `idempotency_key` uses `VARBINARY` for exact byte comparison, avoiding collations that might conflate distinct keys.
- `request_hash` is a SHA-256 digest of the canonicalized request, detecting the same key reused with a different payload.
- `owner_token` is 16 random bytes generated by the current request. It distinguishes the transaction that just created the record from requests encountering a pre-existing record.
- `state` and response fields store the result to replay to the client.

Never store passwords, secret tokens, or payment card details inside idempotency records. Store only necessary response fields and apply appropriate data protection policies.

### 3.3. Same Key with Different Payload Must Be Rejected

A buggy client might reuse an old key while changing `amount` or `orderId`. If the server checks only the key, it could wrongly return an earlier request's result for a different request.

Build a stable fingerprint from business-significant fields:

```text
request_hash = SHA-256(
    canonical(operation, tenant_id, order_id, amount, currency)
)
```

Canonicalization must be deterministic: identical logical data yields the same hash regardless of JSON field order or whitespace. Never hash raw arbitrary JSON strings if serializers can vary ordering or formatting. Include fields affecting the business outcome; exclude irrelevant metadata such as request timestamps.

If the key already exists:

- Same hash and already succeeded: replay the stored response.
- Different hash: return a conflict error, such as HTTP 409.
- Still processing in a multi-phase workflow: return a processing status or ask the client to retry later; never start a second side effect.

### 3.4. Performing Claim and Business Update in One Transaction

For operations contained entirely within one MySQL database, you can insert the idempotency record, update business state, and persist the response in a single transaction.

Claim portion example:

```sql
INSERT INTO api_idempotency (
    tenant_id, operation, idempotency_key,
    owner_token, request_hash, state, created_at
)
VALUES (
    ?, ?, ?, ?, ?, 'PROCESSING', NOW(6)
)
ON DUPLICATE KEY UPDATE id = id;

SELECT id, owner_token, request_hash, state,
       response_code, response_body, resource_id
FROM api_idempotency
WHERE tenant_id = ?
  AND operation = ?
  AND idempotency_key = ?
FOR UPDATE;
```

The application generates a fresh `owner_token` per attempt. After the upsert, read the row with `FOR UPDATE`:

1. If the row's `owner_token` matches the current request's token, this transaction just created the key and may execute the business logic.
2. If the token differs, another request created the key earlier. Compare `request_hash`.
3. If the hashes differ, return a conflict error.
4. If `state` is `SUCCEEDED`, return the stored response.
5. If `state` is `PROCESSING` committed by a multi-phase workflow, return an in-progress response per API contract.

In the single-transaction model, a newly inserted `PROCESSING` row is uncommitted, so concurrent requests do not observe partial state. A colliding upsert waits until the first transaction releases its unique-key lock. If the first commits, the second reads `SUCCEEDED`; if the first rolls back, the second inserts the key and executes the business logic.

Continuing in the same transaction:

```sql
-- Execute only when owner_token matches the current request.
INSERT INTO payments (
    tenant_id, order_id, amount, status, created_at
)
VALUES (?, ?, ?, 'SUCCEEDED', NOW(6));

SET @payment_id = LAST_INSERT_ID();

UPDATE api_idempotency
SET state = 'SUCCEEDED',
    response_code = 201,
    response_body = ?,
    resource_id = @payment_id,
    completed_at = NOW(6)
WHERE id = ?;

COMMIT;
```

This example assumes the payment insert and idempotency update run on the same connection. In real applications, explicitly capture the generated ID from JDBC/JPA and bind it to `resource_id`; do not implicitly rely on `LAST_INSERT_ID()` if another `INSERT` could occur in between.

Crucially, the business row and idempotency outcome commit together. If any step fails, rolling back removes both the idempotency claim and the business change. Subsequent retries can safely try again.

`ON DUPLICATE KEY UPDATE id = id` is a no-op used to wait on/lock the row sharing the unique key; this table should carry only the intended idempotency unique key (besides the primary key). Avoid triggers with side effects on the idempotency table. Inspect the exact conflicting constraint and test concurrency behavior on your running MySQL version.

### 3.5. Transaction Boundaries When Calling External Services

Never hold a MySQL transaction open while calling a payment gateway, email provider, or external API. The database cannot roll back money already debited by an external system, and a network timeout does not prove whether the external call succeeded or failed.

For external side effects:

1. Persist the business request and an outbox event in one MySQL transaction.
2. Commit.
3. A worker sends the command to the external service using a stable idempotency key.
4. Record the callback/response outcome in a separate transaction.
5. Retry with the same key; handle timeouts by querying status from the provider if its API supports it.

This is a multi-phase workflow. A `PROCESSING` record can be committed to represent pending work, but it must include a lease, timeout, retry policy, and terminal state. Never allow a processing record to linger indefinitely without recovery.

## 4. Business Keys for Payments and State Transitions

API idempotency keys prevent the same request from being applied multiple times. Unique business keys on payment tables add protection when different clients, different workers, or separate integration paths do not share an idempotency key.

Example ensuring each provider transaction is recorded at most once:

```sql
CREATE TABLE payment_transactions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider VARCHAR(40)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    provider_transaction_id VARCHAR(150)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_transaction (
        provider, provider_transaction_id
    ),
    KEY idx_payment_order (order_id)
) ENGINE = InnoDB;
```

When a provider webhook redelivers the same `provider_transaction_id`, the unique key blocks a second payment row. The consumer reads the existing record and verifies order, amount, currency, and status. If the same provider transaction ID arrives with a different amount, that is a discrepancy requiring investigation or quarantine, not a valid duplicate.

### 4.1. Conditional State Transitions

Some workflows can use compare-and-set:

```sql
UPDATE orders
SET status = 'CONFIRMED',
    updated_at = NOW(6)
WHERE id = ?
  AND status = 'PENDING';
```

If affected rows equal 1, this request performed the transition. If 0, the order is no longer `PENDING`, does not exist, or failed the condition. Read current state to distinguish. This prevents two requests from driving the same order through the same transition twice.

For balance deductions or inventory updates, enforce conditions directly in the `UPDATE` statement:

```sql
UPDATE inventory
SET available_quantity = available_quantity - ?,
    updated_at = NOW(6)
WHERE product_id = ?
  AND available_quantity >= ?;
```

If `ROW_COUNT()` is 0, stock is insufficient or the product does not exist. Avoid reading the quantity first and updating later without locking or re-checking inside the write statement.

### 4.2. Do Not Replace Business Checks with Idempotency

Two requests with different idempotency keys can still attempt to buy the last item or pay the same invoice. Therefore:

- Idempotency keys identify retries of a single logical request.
- Unique business keys prevent duplicate creation of business entities/transactions.
- State conditions and transactions guard valid transitions.
- Row locks or optimistic versions handle contention when multiple requests mutate the same resource.

These layers complement one another.

## 5. Row Locking in InnoDB

### 5.1. Pessimistic Locking with `SELECT ... FOR UPDATE`

When you must read a row, compute, and update based on its current value, lock the row inside a transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 100
FOR UPDATE;

-- Application checks balance and computes a valid amount.
UPDATE accounts
SET balance = balance - 50000
WHERE account_id = 100;

COMMIT;
```

`FOR UPDATE` is a locking read. In InnoDB, the transaction holds the lock until commit or rollback. Other transactions attempting to update or lock the same row wait or error according to timeout/locking options.

Search predicates should use appropriate indexes. Locking via an unindexed column or broad range can cause InnoDB to lock more records/ranges than expected, reducing concurrency. Use primary or unique keys when protecting a single row.

### 5.2. `NOWAIT` and `SKIP LOCKED`

MySQL 8.0 supports locking reads with `NOWAIT` and `SKIP LOCKED`:

- `NOWAIT`: if a target row is locked by another transaction, the statement errors immediately.
- `SKIP LOCKED`: skips locked rows and returns rows available immediately.

Example worker claiming jobs from a queue:

```sql
START TRANSACTION;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority DESC, id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Update selected IDs to RUNNING and assign worker.
COMMIT;
```

`SKIP LOCKED` fits queue workers because multiple workers claim distinct rows without blocking each other. The result is an inconsistent view of the queue; never use it for business queries needing a complete view of data. After claiming, record an owner/lease and reclaim jobs if a worker dies.

### 5.3. Do Not Hold Locks During Slow Work

Transactions holding locks should contain only necessary database operations. Never make HTTP calls, send emails, write files, or wait on user input while holding row locks. Long transactions increase wait times, deadlock risk, undo history, and reduce throughput.

### 5.4. Named Locks Are Not Data Transaction Locks

MySQL offers `GET_LOCK()` for session-scoped named locks. Named locks can assist certain coordination tasks, but:

- They do not replace unique constraints or row locks.
- They do not automatically roll back with a transaction.
- They are bound to a session/connection; pools may reuse connections.
- They require proper release and disconnect handling.
- They do not provide reliable distributed locking across independent database systems without accounting for failover.

Never use named locks as the sole safeguard for payments, inventory, or duplicate event protection. Data still requires unique constraints and transactions.

## 6. Optimistic Locking with Versioning

When conflicts are infrequent and you want to avoid locking rows during reads/computation, use optimistic locking. Each row carries a `version` column:

```sql
ALTER TABLE inventory
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

On read, the application fetches both `available_quantity` and `version`. On update:

```sql
UPDATE inventory
SET available_quantity = ?,
    version = version + 1,
    updated_at = NOW(6)
WHERE product_id = ?
  AND version = ?;
```

If affected rows equal 1, the update succeeded. If 0, another transaction modified the row or the row no longer exists; the application re-reads and decides whether to retry or return a conflict.

In JPA:

```java
@Entity
public class Inventory {
    @Id
    private Long productId;

    private Integer availableQuantity;

    @Version
    private Long version;
}
```

Hibernate adds the version predicate to the `UPDATE` and increments `version` on flush. If the version no longer matches, the application receives an optimistic locking exception. Catch it at the transaction boundary, roll back the old transaction, and only then re-read/retry in a fresh transaction.

Choosing a locking strategy:

| Scenario | Recommendation |
|---|---|
| Account/order rarely updated concurrently, wanting conflict detection | Optimistic version |
| Must read state and update in a short transaction under high contention | `SELECT ... FOR UPDATE` |
| Only need to transition state if currently in an expected state | Conditional `UPDATE ... WHERE status = ...` |
| Ensure a business key exists only once | Unique constraint |
| Multiple workers sharing queue rows | `FOR UPDATE SKIP LOCKED` combined with leases |

## 7. Inbox Pattern: Preventing Duplicate Event Processing

Message brokers typically provide at-least-once delivery. A consumer may finish processing an event and crash before ACKing; the broker will redeliver it. This is normal behavior, because the broker cannot know for certain whether the consumer's database transaction committed.

The inbox pattern persists processed event IDs in the same database and transaction as the business update.

### 7.1. Inbox Table

```sql
CREATE TABLE event_inbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    consumer_name VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    producer_name VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_id VARBINARY(128) NOT NULL,
    payload_hash BINARY(32) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    processed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inbox_consumer_event (
        consumer_name, producer_name, event_id
    )
) ENGINE = InnoDB;
```

Keying by consumer and producer lets multiple distinct logical consumers process the same event while ensuring each consumer applies it once. If an event ID is unique only within a topic or partition, include the stream/topic identifier in the key.

### 7.2. Correct Processing Order

Inside one transaction, the consumer executes:

1. Insert the event ID into the inbox.
2. If the insert succeeds as a new row, apply business changes.
3. Update `processed_at`.
4. Commit the transaction.
5. After commit succeeds, ACK the message to the broker.

If the business update fails, rollback removes the uncommitted inbox row; when the broker redelivers, the consumer can retry. If commit succeeds but the ACK is lost, redelivery hits the existing unique key, so the consumer skips the business side effect and ACKs.

Never ACK before the transaction commits. If you ACK early and the transaction rolls back or the database fails, the event can be lost from processing.

### 7.3. Java Pattern with Explicit Transaction Boundaries

Example using `TransactionTemplate` so duplicate inspection runs after the failed transaction has rolled back:

```java
public void onMessage(OrderPaidEvent event) {
    byte[] payloadHash = hashCanonicalPayload(event);

    try {
        transactionTemplate.executeWithoutResult(tx -> {
            inboxRepository.insert(
                "order-projection",
                event.producer(),
                event.eventId(),
                payloadHash
            );

            orderProjection.apply(event);

            inboxRepository.markProcessed(
                "order-projection",
                event.producer(),
                event.eventId()
            );
        });

        broker.ack(event);
    } catch (DuplicateKeyException ex) {
        // TransactionTemplate already rolled back before throwing.
        var existing = inboxRepository.find(
            "order-projection",
            event.producer(),
            event.eventId()
        );

        if (existing.isPresent()
                && MessageDigest.isEqual(
                    existing.get().payloadHash(),
                    payloadHash)) {
            broker.ack(event);
            return;
        }

        if (existing.isPresent()) {
            quarantine(event, "Same event ID with different payload");
            broker.ack(event);
            return;
        }

        // Duplicate key originated from another constraint in the business update.
        throw ex;
    }
}
```

This is an illustrative template. `inboxRepository.insert`, `orderProjection.apply`, and `markProcessed` must share the same DataSource/transaction manager to run in one transaction. The post-rollback `find` must run in a new transaction or independent read operation. If a duplicate key arises from another business constraint, never mistake it for an already-processed event; because the inbox insert rolled back, the inbox query will not find the event.

If the same event ID has a different payload hash, the producer may have improperly reused an ID or data was altered. Route it to quarantine/dead-letter and alert operations; do not silently ACK it as a valid duplicate if system contracts require investigation.

### 7.4. Inbox Cannot Enclose External Side Effects

If a consumer updates MySQL and then calls an email API in the same method, the database transaction cannot roll back a sent email. If it sends the email first and the transaction rolls back, event redelivery may send the email again.

For external side effects, write an outbox command in the same transaction as the inbox/business update. A separate worker sends the email or calls the API; the receiving service should also support idempotency keys. If unsupported, design retries/reconciliation and account for possible duplicates per the external system's characteristics.

## 8. Transactional Outbox: Never Losing Events After Commit

A common bug pattern is:

1. Commit order changes to MySQL.
2. Publish an event to the broker.

If the application crashes between the two steps, the database changed but the event is never sent. Reversing the order is also risky: publishing succeeds yet the database transaction rolls back, leaving consumers with an event lacking corresponding state.

A transactional outbox solves this by writing business data and the event inside the same MySQL transaction.

### 8.1. Outbox Table

```sql
CREATE TABLE event_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BINARY(16) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    claimed_by VARCHAR(100) NULL,
    lease_until DATETIME(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_outbox_event (event_id),
    KEY idx_outbox_pending (published_at, lease_until, id)
) ENGINE = InnoDB;
```

### 8.2. Writing Business State and Event in the Same Transaction

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED',
    updated_at = NOW(6)
WHERE id = 8123
  AND status = 'PENDING';

-- Write event only if the state transition actually succeeded.
INSERT INTO event_outbox (
    event_id, aggregate_type, aggregate_id,
    event_type, payload, created_at
)
VALUES (
    UUID_TO_BIN(UUID()), 'ORDER', 8123,
    'OrderConfirmed',
    JSON_OBJECT('orderId', 8123, 'status', 'CONFIRMED'),
    NOW(6)
);

COMMIT;
```

In application code, check the `UPDATE` affected rows before creating the event. If no transition happened, do not emit a new confirmation event. If per-aggregate event ordering is required, include an aggregate version/sequence and have the publisher emit in designed order.

### 8.3. Lease-Based Publisher Claiming

Never hold a transaction and row locks while waiting on the broker over the network. A worker can claim a batch of events in a short transaction:

```sql
START TRANSACTION;

SELECT id
FROM event_outbox
WHERE published_at IS NULL
  AND (lease_until IS NULL OR lease_until < NOW(6))
ORDER BY id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- For the selected IDs, update:
-- claimed_by = worker ID
-- lease_until = NOW(6) + INTERVAL 30 SECOND
-- attempts = attempts + 1

COMMIT;
```

After committing, the worker reads payloads and publishes. Once the broker acknowledges receipt, the worker updates `published_at` and clears the lease. If the worker dies before publishing, the lease expires and another worker reclaims the rows.

One window cannot be eliminated completely: the broker receives the event, but the worker dies before updating `published_at`. The event will be published again after the lease expires. Therefore, an outbox guarantees no lost events while still permitting duplicate publication; consumer inboxes must be idempotent.

`SKIP LOCKED` allows multiple publishers to claim distinct rows. Leases must outlast normal publish latency and support renewal if processing runs long. Never let one worker hold a claim indefinitely.

## 9. Exactly-Once and the Limits of Distributed Systems

Never promise that an entire chain `HTTP → MySQL → broker → consumer → external API` runs strictly once. Timeouts, process crashes, network partitions, and lost ACKs prevent senders from always knowing whether receivers completed work.

Practical designs typically combine:

- At-least-once delivery: messages may be redelivered.
- API and consumer idempotency: identical keys/events do not repeat business effects.
- Unique business constraints: block duplicate entities or transactions.
- Transactional inbox/outbox: bind processing records to database mutations.
- Reconciliation: verify state with providers or external systems when outcomes are uncertain.

You can achieve "effectively one business outcome" within a single database transaction when idempotency markers and business updates commit/roll back together. Across multiple independent systems, you need sagas, outboxes/inboxes, and per-step idempotency; no single MySQL transaction spans them all.

## 10. Deadlocks, Lock Timeouts, and Safe Retries

When multiple transactions lock rows in different orders, InnoDB can detect a deadlock and roll back one transaction as the victim. Common errors:

- `1213` / SQLSTATE `40001`: deadlock found.
- `1205`: lock wait timeout exceeded.

Example with two transactions:

```text
Transaction A             Transaction B
-------------             -------------
lock account 1            lock account 2
wait account 2            wait account 1
```

Reduce deadlocks by:

1. Locking rows in a consistent system-wide order, such as ascending primary key.
2. Keeping transactions short and locking only necessary rows.
3. Using indexes so locking queries stay narrow.
4. Never calling external services while holding locks.
5. Keeping batches small and avoiding unnecessarily wide range updates.

When a deadlock or lock timeout occurs, retry the entire transaction from the beginning with a retry limit, backoff, and jitter. Never retry only the final `UPDATE` statement, because earlier reads/decisions may no longer be valid. Any external side effects must use idempotency keys or outboxes so retries do not duplicate effects.

Timeouts during `COMMIT` or disconnections right after commit create an indeterminate state: the transaction may have committed even though the client received no response. Before re-running the operation, look up the idempotency/business key to determine the persisted outcome.

## 11. Retention and Idempotency Operations

### 11.1. Retain Keys Long Enough

Idempotency key retention must exceed the maximum window in which clients, gateways, brokers, or partners may retry. Deleting keys too early allows a retried old request to execute its side effect again.

For financial operations, provider transaction keys or business references may need to be retained far longer than HTTP idempotency keys. Keep unique business constraints on transactional tables as a permanent safeguard.

### 11.2. Batch Data Cleanup

If idempotency tables have expiration windows, delete in small batches using an index on expiration/creation time:

```sql
DELETE FROM api_idempotency
WHERE created_at < NOW(6) - INTERVAL 30 DAY
ORDER BY created_at
LIMIT 1000;
```

Delete only after the retry window closes and no active workflows remain. For event inboxes, retain records longer than broker retention and possible replay windows. When intentional replays are needed, use a new consumer/version namespace or a controlled reset procedure; never purge inbox rows arbitrarily.

### 11.3. Monitoring Metrics

Monitor at least:

- Duplicate requests by operation/tenant.
- Occurrences of the same idempotency key with a different payload hash.
- Events deduplicated by inbox and events sent to quarantine.
- Pending outbox count, age of oldest event, and publish retry counts.
- Deadlocks, lock wait timeouts, and transaction retries.
- Expired `PROCESSING` records and expired leases.
- Duplicate business key rates per integration.

Logs should carry operation, tenant/business reference, event ID, and trace ID as appropriate. Never log full sensitive payloads or credentials.

## 12. Workflow for Handling a Payment Event

Suppose a provider delivers a `PaymentSucceeded` event multiple times:

1. Verify webhook signature and provider identity before processing.
2. Extract event ID and provider transaction ID; verify whether event IDs stay stable across retries.
3. Start a MySQL transaction.
4. Insert the event ID into the inbox with a unique key on consumer/provider/event.
5. If the event already exists and payload hashes match, end the transaction without re-applying business effects; ACK after verification completes.
6. If the event is new, check the unique provider transaction ID and verify order/amount/currency.
7. Update payment/order through a valid transition; use state conditions or row locks as needed.
8. Write an outbox event such as `OrderPaid` in the same transaction.
9. Commit the transaction and then ACK the webhook/message.
10. Publisher emits the outbox event; downstream consumers use their own inboxes to deduplicate.

If the provider transaction ID already exists yet order reference or amount mismatches, route the event into an investigation workflow. Never ignore mismatches simply because the event ID or provider transaction ID was seen before.

## 13. Testing Concurrency and Failures

A sequential test does not prove idempotency works under concurrency. Test with multiple concurrent connections/workers:

1. Send 20 parallel requests with identical tenant, operation, key, and payload. Expect exactly one business row; all responses match.
2. Send the same key with a different amount. Expect one request to succeed and the other to receive a conflict error.
3. Send two different keys sharing the same business key. Expect the unique business constraint to allow only one resource creation.
4. Deliver the same event multiple times in parallel. Expect one inbox row and one business effect.
5. Kill the consumer after commit but before ACK. On broker redelivery, the consumer must skip the side effect and ACK.
6. Kill the consumer before commit. The transaction rolls back both inbox and business update; redelivery is allowed to process.
7. Kill the publisher after the broker accepts the event but before marking published. The event may be re-sent; consumers must deduplicate.
8. Induce controlled deadlocks and verify full-transaction retries do not duplicate effects.
9. Simulate post-commit timeouts and verify retries return the stored outcome.

Verify row counts, final states, balances/inventory totals, and emitted event counts—not just HTTP status codes.

## 14. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| User retry creates two orders | Missing idempotency key or unique business key | Add scoped idempotency key and business unique constraint |
| Same key with different payload accepted | Request hash not stored/compared | Compute deterministic fingerprint and return conflict |
| Two workers process the same event | `SELECT` check before `INSERT` only | Use unique inbox key and transaction |
| Inbox recorded then business update fails, event dropped | Inbox committed separately before business update | Commit inbox and business effect in one transaction |
| Business update succeeds but event never published | Publishing outside transaction without an outbox | Write outbox in the same transaction as business state |
| Duplicate events published after worker crash | Broker received event before publisher marked published | Use idempotent inbox on consumers |
| `DuplicateKeyException` treated as valid duplicate | Failed to inspect constraint and business reference | Verify exact inbox/business key and payload |
| `PROCESSING` record stuck indefinitely | Multi-phase workflow lacks leases/recovery | Add leases, timeouts, retries, and terminal states |
| Deadlocks spike under high load | Inconsistent lock order or long transactions | Standardize lock order, shorten transactions, bound retries |
| Request times out with unknown commit state | Response lost after commit | Look up idempotency/business key before re-running |

## 15. Design Checklist

- [ ] Every operation has a clearly defined business key and uniqueness scope.
- [ ] Unique constraints exist in MySQL; never rely solely on `SELECT` existence checks.
- [ ] API records idempotency keys scoped by tenant/operation.
- [ ] Request hashes detect same key with differing payloads.
- [ ] Business updates and idempotency results commit in the same transaction when sharing a database.
- [ ] Event inbox has a unique key by consumer and event identity.
- [ ] Inbox insert, business effect, and processed marker share one transaction.
- [ ] Broker ACK occurs only after commit.
- [ ] Outbox events are written in the same transaction as business state.
- [ ] Publishers use leases/recovery; consumers tolerate duplicate publication.
- [ ] External APIs use dedicated idempotency keys or reconciliation workflows.
- [ ] Row locks/optimistic versions are chosen according to contention level.
- [ ] Transactions are short, properly indexed, with consistent lock ordering.
- [ ] Deadlocks/timeouts retry the entire transaction with caps and backoff.
- [ ] Retention is no shorter than retry/replay windows.
- [ ] Metrics track duplicates, conflicts, inbox/outbox lag, and retries.
- [ ] Concurrency, pre/post-commit crashes, and lost ACKs have been tested.

## 16. Self-Check Exercises

1. Why does a `SELECT` checking a business key before `INSERT` fail to stop two concurrent requests from creating duplicate records?
2. How does an idempotency key differ from a business key?
3. Why must request hashes be compared when a client resends the same idempotency key?
4. In a single-transaction idempotency model, what happens if the process crashes before commit?
5. Why must the inbox record and business update reside in the same transaction?
6. Why must the broker ACK occur after the transaction commits?
7. Under what circumstances can an outbox publish duplicates, and how do consumers handle them?
8. When should `SELECT ... FOR UPDATE` be used instead of optimistic versioning?
9. Why does a named lock `GET_LOCK()` not replace a unique constraint?
10. Upon receiving deadlock error 1213, should you retry only the last statement or the entire transaction?
11. Why does a timeout immediately after commit require checking the idempotency key before re-running?
12. If the same event ID arrives with a different payload hash, what should the consumer do?

**Answer hints:** (1) Two transactions can both read the non-existent state; only a unique constraint arbitrates atomically. (2) A business key identifies a domain entity/operation; an idempotency key identifies retries of a logical request. (3) To avoid returning the wrong result or ignoring a request with a different payload. (4) The transaction rolls back both the claim and the business effect, allowing retries to reprocess cleanly. (5) If split across transactions, the marker may persist while the business effect fails or vice versa. (6) If ACKing before commit, events can be lost when transactions roll back. (7) Publisher crashes after broker receipt but before marking published; consumers deduplicate via inbox. (8) When reading current state and updating in a short transaction under high contention. (9) Named locks are session-bound and do not enforce durable data uniqueness. (10) Retry the entire transaction with backoff and retry limits. (11) Because commit may have succeeded even though the client never received the response. (12) Quarantine/alert and investigate the producer or data; do not treat it as a valid duplicate.

## References

- [MySQL 8.4 Reference Manual: InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual: InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual: INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual: Locking Functions](https://dev.mysql.com/doc/refman/8.4/en/locking-functions.html)
- [Spring Framework Reference: Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Data JPA Reference: Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
