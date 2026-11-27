# Idempotency and unique constraints for duplicate write requests

In **Spring Data Relational JDBC**, a write request can be sent multiple times even though the user performed a single action. For example, a client sends an order creation request, but the network drops before receiving the response. Not knowing whether the server committed, the client retries the request. If every incoming request creates a new order, one user action produces multiple business side effects.

**Idempotency** is a design approach where repeating an operation with the same request identifier produces only one business effect. A database **unique constraint** is a critical safeguard for handling concurrent requests too. Checking in Java before inserting is unsafe because two transactions can both observe "does not exist yet" and both insert.

In Spring Data JDBC, you can store an idempotency key alongside the processing outcome in the database, place that operation and the aggregate mutation inside a single transaction, and rely on a unique constraint so the database arbitrates duplicate requests. This lesson explains how to design keys, request fingerprints, transactions, retries, result replay, conflicts, and coordination with an outbox for external side effects.

## 1. Why can write requests be sent multiple times?

A request can be resent because:

- The client timed out while the server was still processing.
- The server committed, but the response was lost in transit.
- A gateway or load balancer retried the request.
- The user clicked a button multiple times.
- A message broker redelivered a message before the consumer acknowledged it.
- A worker restarted without knowing whether its previous run finished.

Example:

~~~text
Client                  Server                  Database
  |                        |                        |
  | POST /orders           |                        |
  |----------------------->| INSERT order           |
  |                        |----------------------->|
  |                        | COMMIT                 |
  |                        |<-----------------------|
  |       response lost    |                        |
  |        X               |                        |
  | timeout                |                        |
  |                        |                        |
  | retry POST /orders     |                        |
  |----------------------->| INSERT order again     |
~~~

The server cannot treat a retried request as a new action just because it received another HTTP request. The client must send a stable identifier for the same operation, such as an `Idempotency-Key` header.

## 2. What does idempotency mean?

An idempotent operation has this property: executing it once or multiple times with the same inputs and the same operation identifier leads to the same final business effect.

Examples:

- Creating an order with the same idempotency key creates only one order.
- Resending a payment request with the same key does not record a second payment.
- A consumer receiving the same event ID again does not apply the business effect a second time.
- Setting a property to a specific value, such as changing status to `CANCELLED`, can be idempotent when state transition rules are designed appropriately.

Idempotency does not mean all requests with identical payloads must be deduplicated. Two requests to create two separate orders can have identical bodies yet represent two valid actions. Therefore, operations must be identified by a client-generated key or a business identifier with clear semantics.

### 2.1. Idempotency differs from HTTP methods

HTTP defines PUT and DELETE as having idempotent protocol semantics, while POST is generally not treated as idempotent by default. Still, applications must design exact behavior:

- PUT setting a resource to a specified state can usually be repeated.
- DELETE on the same resource may return a different status on a repeat call, yet the final effect remains that the resource is gone.
- POST creating an order or recording a payment usually needs an idempotency key if clients can retry.

Simply using an HTTP method does not automatically create database deduplication.

### 2.2. Idempotency is not system-wide exactly-once

Networks, message brokers, and services can deliver requests/messages multiple times. Idempotency handles duplicate deliveries while preserving a single business effect within the protected scope. Do not promise end-to-end exactly-once delivery based solely on a single unique key in one database.

Practical systems typically combine at-least-once delivery with idempotent processing and persistent result records.

## 3. Idempotency keys

An idempotency key uniquely identifies one business execution attempt. The client generates the key before sending the request and reuses the exact same key when retrying the same operation.

Header example:

~~~http
POST /api/orders
Idempotency-Key: 8c2e6e6a-8f7d-4e7c-a8ef-8f5f14d2f9f1
Content-Type: application/json
~~~

If the client times out and resends the exact same request, it sends the same key. When the user starts a brand-new order action, the client generates a new key.

### 3.1. Key scope

Do not assume keys are globally unique across the entire system. Define a unique scope combining:

- Tenant or account.
- Operation/endpoint name.
- Idempotency key.

Example:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

This way, two tenants can use the same key string without colliding, and the same key across two different operation types can be distinguished if the contract allows it.

Keys should have length limits, an accepted format, and an appropriate retention period. Never use sensitive data such as access tokens or passwords as keys.

### 3.2. Who generates the key?

For HTTP APIs, the client usually generates a random UUID or a token with sufficient entropy. The server validates the key, checks its length, and combines it with tenant/operation to establish scope.

For message consumers, a stable message ID or event ID can serve as the idempotency key. The producer must preserve the same event ID when redelivering the same message.

## 4. Unique constraints are the arbiter under concurrency

A common flawed approach:

~~~java
if (!receiptRepository.existsByKey(key)) {
    receiptRepository.save(new Receipt(key));
    orderRepository.save(order);
}
~~~

Two requests can run concurrently:

~~~text
Transaction A                  Transaction B
-------------                  -------------
SELECT key -> absent
                               SELECT key -> absent
INSERT receipt
                               INSERT receipt
INSERT order
                               INSERT order
COMMIT
                               COMMIT
~~~

Without a unique constraint, both transactions can create duplicate receipts and orders. This is a check-then-act race condition: the check result becomes stale the moment another transaction modifies the database.

Create a unique constraint:

~~~sql
CREATE TABLE idempotency_record (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    operation VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    resource_id BIGINT,
    response_status INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uk_idempotency_scope
        UNIQUE (tenant_id, operation, idempotency_key)
);
~~~

The database allows at most one row per scope. If two transactions concurrently insert the same key, the unique index arbitrates: one insert succeeds; the other waits or receives a conflict depending on database behavior. Thus, the unique constraint is the final line of defense; `exists` checks can only be a secondary optimization, never the uniqueness guarantee.

## 5. Idempotency keys and business unique keys are different

These two types of unique constraints enforce different rules:

| Type | Example | What does it protect? |
| --- | --- | --- |
| Idempotency key | (tenant_id, operation, idempotency_key) | Re-submitting the same request does not create duplicate effects |
| Business unique key | order_number, provider_payment_id, external_reference | Prevents creating two records representing the same business entity/event |

For example, two requests with different idempotency keys could still carry the same external_reference from a partner system. A business unique constraint prevents creating two orders for that reference.

Conversely, two requests with the same idempotency key but different bodies must be caught via a request fingerprint. A unique key only tells you the key was used; it does not prove the new request carries the same intent as the original request.

Critical systems often need both idempotency keys and business unique constraints.

## 6. Request fingerprints: detecting key misuse

When storing an idempotency record, also store a hash of the canonicalized business payload:

~~~text
request_hash = SHA-256(canonical request representation)
~~~

A fingerprint distinguishes:

- Same key, same payload: valid retry, replay the saved result.
- Same key, different payload: client reused a key for a different action; return a conflict.

Example:

~~~text
First attempt:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 2}]}
  hash = H1

Retry:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 2}]}
  hash = H1  -> replay

Misuse:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 5}]}
  hash = H2  -> conflict
~~~

Do not hash raw JSON if key ordering, number formatting, whitespace, or equivalent representations can vary across submissions. Canonicalize the request per the API schema, such as sorting keys, normalizing values, and hashing only business-meaningful fields.

Do not include server-generated random data in the fingerprint before processing. Clearly define which fields change the meaning of a command.

## 7. Saving the receipt with the business operation in one transaction

For a fast database-only command, the simplest approach saves the idempotency record, mutates the aggregate, and stores the result in the **same transaction**:

~~~text
BEGIN
  INSERT idempotency_record (scope, key, hash, state)
  INSERT purchase_order
  INSERT order_line ...
  UPDATE idempotency_record
      SET state = COMPLETED,
          resource_id = ...,
          response_body = ...
COMMIT
~~~

If any step fails, the entire transaction rolls back. There is no completed receipt without an order, nor a committed order without a receipt when both share the same transaction.

### 7.1. Receipt entity

Spring Data JDBC entity example:

~~~java
@Table("idempotency_record")
public class IdempotencyRecord {

    @Id
    private Long id;

    private String tenantId;
    private String operation;
    private String idempotencyKey;
    private String requestHash;
    private String state;
    private Long resourceId;
    private Integer responseStatus;
    private String responseBody;
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
}
~~~

Repository:

~~~java
public interface IdempotencyRecordRepository
        extends CrudRepository<IdempotencyRecord, Long> {

    Optional<IdempotencyRecord>
    findByTenantIdAndOperationAndIdempotencyKey(
            String tenantId,
            String operation,
            String idempotencyKey
    );
}
~~~

Java property names must map to snake_case columns via the naming strategy or `@Column` annotations if the schema uses different names. The unique constraint must still be declared in the database; repository method names alone cannot enforce uniqueness.

### 7.2. Write the receipt first, then write the aggregate

Inside the transaction:

1. Insert the receipt with the key and request hash.
2. Create and save the aggregate root.
3. Write child rows through the aggregate repository.
4. Store the resource ID and response snapshot on the receipt.
5. Commit.

This order ensures the unique constraint is checked before creating business effects. If inserting the receipt hits a duplicate, the current transaction does not proceed to create the order.

### 7.3. Storing the result for replay

Storing only the key is insufficient if the API must return the same response as the initial call. You can store:

- HTTP status.
- Resource ID.
- Serialized response body.
- Required headers, if dictated by the contract.
- Completion timestamp.

If you store only the resource ID and query the resource's current state on retry, the response may differ from the original because the resource has since changed. Decide whether the API must replay a response snapshot or only return the resource identifier.

Do not store secrets or unnecessary sensitive data in receipts. If storing response bodies, apply appropriate protection policies and retention limits.

## 8. Handling duplicate requests and replaying results

When inserting the receipt fails due to the unique key:

1. The retry's write transaction must roll back or terminate properly.
2. Read the committed receipt in a fresh transaction/read operation.
3. Compare the request hash.
4. If the hash matches and the receipt is completed, return the stored result.
5. If the hash differs, return a conflict error because the key was already used for different content.

Pseudo-flow:

~~~text
Receive request(key, command)
        |
        v
Compute canonical request hash
        |
        v
Try transaction:
  insert receipt with unique key
  write aggregate
  store completed response
  commit
        |
        +-- success --> return new response
        |
        +-- duplicate key
                |
                v
          transaction has ended/rolled back
                |
                v
          load existing receipt
                |
          +-----+------+
          |            |
       same hash    different hash
          |            |
       replay       conflict
       response
~~~

### 8.1. Do not catch duplicates and continue inside the failed transaction

A unique violation can mark the transaction rollback-only or put the database transaction into an error state. For example, PostgreSQL requires rolling back the transaction after a normal SQL error before executing further statements.

Therefore, do not catch a duplicate exception inside the same transaction and immediately query the receipt and continue as though the transaction were healthy. Let the transaction fail and finish; then read the receipt in a separate transaction.

A clean structure uses a non-transactional facade calling a `@Transactional` bean to execute the command, then catching the duplicate exception after the proxy has rolled back the transaction:

~~~java
@Service
public class CreateOrderAttempt {

    @Transactional
    public CreateOrderResult execute(
            String tenantId,
            String key,
            String requestHash,
            CreateOrderCommand command
    ) {
        // Insert receipt, save aggregate, mark receipt complete.
        // A unique violation must escape this method.
        return ...;
    }
}
~~~

Facade:

~~~java
@Service
public class IdempotentOrderService {

    private final CreateOrderAttempt attempt;
    private final IdempotencyReplayService replay;

    public IdempotentOrderService(
            CreateOrderAttempt attempt,
            IdempotencyReplayService replay
    ) {
        this.attempt = attempt;
        this.replay = replay;
    }

    public CreateOrderResult create(
            String tenantId,
            String key,
            CreateOrderCommand command
    ) {
        String hash = requestHasher.hash(command);
        try {
            return attempt.execute(tenantId, key, hash, command);
        } catch (DuplicateKeyException ex) {
            return replay.resolve(tenantId, "CREATE_ORDER", key, hash);
        }
    }
}
~~~

This is an illustrative skeleton; inject `requestHasher`, declare exceptions/domain results, and handle exact constraints properly. `DuplicateKeyException` is a subclass of `DataIntegrityViolationException` in Spring. Depending on write mechanics and driver/framework exception translation, unique violations may surface as another specific exception. Treat it as an idempotency duplicate only when you identify the right unique constraint or when the replay step locates the corresponding receipt; never turn arbitrary integrity errors into successful replays.

### 8.2. What if no receipt is found after a duplicate exception?

The duplicate exception may have come from another business unique constraint, such as SKU or external reference. If no receipt is found for the scope/key, re-throw the error or handle the corresponding business conflict. Never assume every duplicate key error is an idempotency replay.

### 8.3. Duplicate request arriving while the first request is still running

With a unique insert inside a transaction, the second request may have to wait for the first transaction to resolve the unique index conflict:

- If the first transaction commits, the second receives a unique conflict and reads the completed receipt to replay.
- If the first transaction rolls back, the second can insert successfully and execute the command.

Waiting details, timeouts, and receipt visibility depend on the database and isolation level. Configure suitable timeouts and test on your target database.

## 9. Using INSERT ... ON CONFLICT or equivalents

Some databases support insert syntax that does not fail the transaction when a key already exists. PostgreSQL:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, state, created_at
)
VALUES (
    :tenantId, :operation, :key,
    :requestHash, 'PROCESSING', :createdAt
)
ON CONFLICT (tenant_id, operation, idempotency_key)
DO NOTHING;
~~~

Then inspect the affected row count:

- `1`: the request claimed the key and can execute the command.
- `0`: the key already existed; read the existing receipt and compare hashes.

This is PostgreSQL syntax and is not portable verbatim to all databases. SQL Server, MySQL, Oracle, and others have different ways of expressing upsert/ignore-conflict. When supporting multiple databases, separate implementations by dialect or use the insert + exception translation strategy.

Even when using `ON CONFLICT DO NOTHING`, you must still account for transactions and visibility under your isolation level. Do not assume every database shares identical semantics for concurrent inserts and read-after-conflict.

## 10. PROCESSING state and long-running commands

For short database-only commands, the receipt can be created and completed in the same transaction; intermediate states are never committed externally. If the transaction rolls back, the receipt disappears too.

For long-running or asynchronous work, the application may need to commit the receipt in a `PROCESSING` state before processing:

~~~text
NEW -> PROCESSING -> COMPLETED
                  -> FAILED/RETRYABLE
~~~

In that case, additional operational mechanisms are needed:

- A lease/lock owner identifying the active worker.
- A lease expiration to reclaim abandoned work.
- Attempt counts and retry timestamps.
- Distinguishing recoverable failures from permanent failures.
- Rules for duplicate requests arriving while PROCESSING (return 202, wait, or report in-progress).
- Worker recovery after a process crash.

Never store `PROCESSING` and assume it will always reach `COMPLETED`. Processes can crash mid-way; you need mechanisms to detect and resume them.

### 10.1. Do not leave PROCESSING receipts stuck indefinitely

If a receipt is committed before running the business command, a worker may crash after claiming it. Use `lease_until`, `attempt_count`, and `updated_at` to determine when work can be reclaimed. Reclaiming must use atomic conditions or proper locking so two workers do not claim the same job.

This model is more complex than single-transaction idempotency. Use it only when processing duration or asynchronous architecture truly requires it.

## 11. Idempotency with external side effects outside the database

A JDBC transaction protects only changes participating in that database transaction. It cannot roll back sent emails, HTTP requests to a payment provider, or messages published to a broker.

Unsafe example:

~~~text
BEGIN
  save order
  call payment provider
  insert idempotency receipt
COMMIT
~~~

If the payment provider charged the customer but the database rolled back, the system ends up with a real payment without a corresponding order/receipt. If the database commits while the external call fails, outcomes also drift out of sync.

### 11.1. Transactional outbox

A common pattern:

~~~text
BEGIN
  save order aggregate
  save idempotency receipt
  insert outbox event
COMMIT

Outbox publisher:
  read unpublished event
  send to broker/provider
  mark published
~~~

The order, receipt, and outbox event commit in the same transaction. The publisher can resend an event if uncertain whether a prior send succeeded; the consumer must deduplicate using the event ID or process idempotently.

An outbox guarantees the event is persisted atomically with the business change in the database. It does not by itself make broker delivery exactly-once; publishers and consumers must still handle duplicate deliveries.

### 11.2. Using the provider's idempotency key

When calling a payment provider, pass a stable key scoped to the payment operation if the provider supports it. On retries, send the same provider idempotency key so the provider does not create two transactions.

Application keys and provider keys may have different scopes. Store the mapping between them for reconciliation, retries, and investigation.

## 12. Idempotency and optimistic locking solve different problems

These two mechanisms are frequently confused:

| Mechanism | Question answered |
| --- | --- |
| Idempotency key + unique constraint | Is this the exact same command that was already processed before? |
| Optimistic locking (`@Version`) | Is the aggregate still at the version this command was based on? |
| Business unique constraint | Do these two records violate a domain uniqueness rule? |

Examples:

- Client retries the same order-creation request: idempotency key prevents creating a second order.
- Two users edit the same order starting from version 5: optimistic locking detects that one update used a stale version.
- Two requests with different keys both create an order with an existing external reference: business unique constraint blocks duplicate references.

A single system may need all three mechanisms.

## 13. Retention period for idempotency records

Not all records need to be kept forever, yet deleting them too early allows late retries to execute the effect again.

Retention policies should consider:

- How long can clients retry?
- What is the gateway/message broker redelivery window?
- Are there business or audit rules requiring receipt retention?
- Can results be reconstructed from the resource ID?
- Can sensitive response bodies be purged while keeping key/hash/resource ID?

If records are purged after 24 hours while clients may retry after 48 hours, the same key can be processed twice. Choose a retention period longer than the maximum retry window and consider keeping long-lived business unique references as an extra safeguard.

Records can be partitioned or cleaned up by age, provided cleanup never deletes active PROCESSING receipts or records still within the retry window.

## 14. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking `exists` before inserting | Race condition under concurrent requests | Add a unique constraint and handle duplicates |
| Generating a new key on each retry | Server treats each retry as a new command | Client reuses the same key for the same operation |
| Not storing a request hash | Same key can be reused with a different body | Store a fingerprint and return conflict on mismatch |
| Keys without tenant/operation scope | Callers/endpoints can collide unexpectedly | Use a composite unique constraint per scope |
| Storing key without storing outcome | Cannot replay consistent responses | Store response snapshot or resource reference per contract |
| Catching duplicate inside the failed transaction | Transaction may be rollback-only/aborted | Let the transaction end, then read the receipt in a fresh transaction |
| Treating every DataIntegrityViolation as an idempotency duplicate | Masks foreign key, CHECK, or business unique errors | Identify the exact constraint and verify the receipt |
| Saving receipt and aggregate in two separate transactions | Can leave a receipt without a resource or vice versa | Write in the same transaction when using the same database |
| Calling external API inside transaction expecting rollback | Side effects outside DB do not roll back | Use outbox and provider idempotency |
| Leaving PROCESSING without lease/recovery | Requests get stuck indefinitely | Add leases, timeouts, retries, and worker recovery |
| Purging receipts too early | Late retries can re-trigger effects | Align retention with the retry window |
| Confusing idempotency with optimistic locking | Fails to handle retries or lost updates properly | Use the right mechanism for each problem |

## 15. Workflow for designing idempotent writes

When implementing an endpoint or consumer that may receive duplicate deliveries:

1. **Define the command:** which business action must take effect at most once within what scope?
2. **Choose a stable key:** client-generated key or event ID; preserve it across retries.
3. **Define scope:** tenant, operation, and key.
4. **Canonicalize the request:** build a fingerprint from business-meaningful fields.
5. **Add a unique constraint:** let the database arbitrate concurrent requests.
6. **Choose a transaction strategy:** short commands write receipt, aggregate, and response in one transaction; long commands need a state machine/lease.
7. **Store replay results:** response snapshot or resource ID per API contract.
8. **Handle duplicates after rollback:** read the committed receipt, compare hashes, replay or return conflict.
9. **Protect domain invariants:** add business unique constraints and optimistic locking as needed.
10. **Handle side effects:** write outbox in the transaction and deduplicate at consumers/providers.
11. **Set retention:** keep records long enough for retry windows and audit needs.
12. **Test concurrency:** fire concurrent requests with the same key and verify only one business effect occurs.

## 16. Testing idempotency and unique constraints

Key test scenarios:

| Scenario | Expected outcome |
| --- | --- |
| Send a key once | Creates resource and completed receipt |
| Resend same key, same body | Creates no new resource; returns saved result |
| Send same key, different body | Returns conflict; creates no new effect |
| Two requests with same key run concurrently | Only one transaction produces the effect |
| First request rolls back before commit | Retried request can execute the command |
| Two different keys with same business reference | Business unique constraint prevents duplicate records |
| Aggregate write succeeds but receipt write fails | Shared transaction rolls back both |
| Duplicate outbox event delivery | Consumer deduplicates by event ID |
| Receipt expires past retention and old request returns | Behavior matches documented retention policy |

### 16.1. Concurrency tests require a real database

Mocking repositories cannot prove the unique index actually serializes/rejects two concurrent inserts. Run integration tests against a production-like database or Testcontainers:

1. Pick a fixed idempotency key and command.
2. Launch multiple threads/requests simultaneously with that key.
3. Synchronize their start to maximize contention.
4. Wait for all outcomes.
5. Verify exactly one receipt exists in that scope.
6. Verify exactly one order/resource exists.
7. Verify the remaining requests replay the same result or receive an in-progress status per contract.

Do not only assert that one request succeeded; inspect database state after concurrency completes.

### 16.2. Testing rollback on mid-flight errors

Force a step after inserting the receipt or saving the aggregate to fail, then confirm the transaction leaves behind no partial receipt or resource. The test must read back after the command's transaction finishes, avoiding a wrapping test transaction that obscures actual commit/rollback behavior.

## Key takeaways

Idempotency protects a command from creating duplicate effects when clients, gateways, or message brokers resend the same request. An idempotency key identifies the operation instance; a request hash catches keys reused with different payloads; a unique constraint acts as the database arbiter when requests run concurrently.

For short database write commands, store the receipt, aggregate mutation, and replay result in the same transaction. On a duplicate key, let the write attempt's transaction finish, then read the committed receipt in a new transaction; compare fingerprints to replay or return a conflict. Business unique constraints and `@Version` protect orthogonal rules. For external side effects outside the database, write to an outbox in the same transaction and handle duplicate delivery in publishers and consumers. This yields reliable write behavior under retries and concurrency without relying on race-prone existence checks.
