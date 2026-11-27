# Persisting Idempotent Processing State and Deduplication Retention Windows

In serverless architectures, a request or message can be resent when a client times out, a function terminates mid-flight, a queue redelivers a message, or the system retries after a transient error. If every delivery creates a new order, charges a payment, or sends a notification, a single business action can produce multiple side effects.

**Idempotency** ensures that an operation submitted multiple times still yields a single business outcome within a defined scope. Achieving this requires storing processing state durably under a stable key, coordinating concurrent requests with atomic operations, and retaining records long enough to cover the entire window of possible retries, redeliveries, and replays.

This lesson focuses on persisting idempotency state in a database or shared data store, choosing keys and fingerprints, handling `PROCESSING`/`SUCCEEDED` states, recovering crashed workers with leases, calculating retention windows, and protecting external side effects. Examples use Java and SQL for HTTP functions, queue consumers, and event-driven workflows.

## Learning Objectives

After completing this lesson, you will be able to:

- Explain why retries and at-least-once delivery require durable idempotency state.
- Distinguish between idempotency, duplicate detection, and exactly-once processing.
- Design idempotency keys scoped by tenant, operation, and business action.
- Use request fingerprints to detect key reuse with a different payload.
- Store processing state using unique constraints and atomic claims.
- Choose short transactions for synchronous operations or leases for long-running work.
- Handle duplicate requests while a record is `PROCESSING` or already `SUCCEEDED`.
- Calculate retention windows from client retries, queue retention, redelivery, DLQs, and replays.
- Distinguish logical expiry from physical record deletion by storage TTL.
- Protect external side effects with downstream idempotency, outboxes, and sagas.
- Test race conditions, crash windows, retries, and deduplication expiry.

## 1. Why Must Idempotent State Be Persisted?

A function can complete its business work while the response never reaches the caller. The caller only sees a timeout and resends the same request. A queue consumer can finish processing a message but crash before its acknowledgment is recorded; the broker redelivers the message. A workflow can retry a task because it did not receive a result even though the side effect already happened in the target system.

Example:

1. A client sends `POST /orders` to create an order.
2. The function writes the order and returns an HTTP response.
3. The network drops before the client receives the response.
4. The client retries because it does not know whether the first attempt succeeded.
5. If the function creates a new order, a single user intent creates two orders.

Another example with payments:

1. The function calls a payment provider.
2. The provider charges the card successfully.
3. The function times out before saving the result or returning a response.
4. The queue redelivers the message.
5. The function calls charge again.

In both cases, checking state only in RAM or a static variable is insufficient. Instances can be reclaimed, subsequent invocations can run on different JVMs, and multiple requests can arrive concurrently.

### Idempotency Does Not Equal Exactly-Once

- **Idempotency:** repeating the same operation with the same key and same semantics creates no additional business outcome.
- **Duplicate detection:** identifying an event or request that has been seen previously.
- **At-least-once delivery:** the system may redeliver a message until it is acknowledged or exhausts its retry policy.
- **Exactly-once effect:** the business effect occurs only once within a guaranteed scope. This is usually a property built from transactions, idempotency, and cross-system protocols; it cannot be inferred solely from a broker having deduplication.

Idempotency must be enforced at the boundary where side effects can occur. FIFO queues, broker deduplication, or retry policies can reduce duplicates, but they do not replace idempotency state at the consumer and target service.

## 2. Define the Scope of an Idempotent Operation

Before creating a key, define precisely what "the same operation" means.

A key should be scoped by the dimensions that must be kept distinct, typically including:

- The tenant or account owning the request.
- The operation or endpoint, such as `orders.create` or `payments.capture`.
- The idempotency key supplied by the client/producer or generated and stored with the event by the system.
- The business entity/action if derived from domain identity, such as order ID + capture attempt.

Do not use a global unscoped key if two tenants or two operation types might accidentally collide on the same key string.

For example, the same string `req-123` can be valid for two different tenants, but must be stored under two independent scopes:

~~~text
tenant-A | orders.create   | req-123
tenant-B | orders.create   | req-123
tenant-A | payments.capture| req-123
~~~

A schema commonly uses a composite unique key:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

If the key is derived from a business ID, verify that it represents one specific action. An order may have multiple valid payment attempts, so a bare `orderId` may be too broad; you need to distinguish `payment.capture`, `payment.refund`, or the corresponding attempt.

### Keys Must Remain Stable Across Retries

For HTTP, the client generates a key once per operation and resends the exact same key on retry. Do not generate a new UUID on each client retry.

For events, the producer generates an event ID when the event is recorded and preserves that ID across publish retries or replays. If an outbox worker generates a new event ID on each send attempt, consumers cannot detect duplicates.

For workflows, the idempotency key should reflect the business action, not just the execution attempt. A retry of the same task must reuse the key; a new business action needs a new key.

### Keys Should Be Unpredictable and Free of Sensitive Data

Clients can use random UUIDs with sufficient entropy. Do not place email addresses, card numbers, access tokens, or personal information directly inside a key. If a key is derived from business data, consider an HMAC with a securely managed secret and ensure the key cannot be reversed to recover the original data.

A key is not an authentication mechanism. The caller must still be authenticated and authorized before reading or replaying stored results.

## 3. Request Fingerprinting: Detecting Key Misuse

The same idempotency key must represent the same business request. If a client sends an existing key with a different payload, the system should neither silently return the old result nor execute the new request.

Store a **request fingerprint** (a hash of canonicalized data) alongside the key:

| Field | Role |
|---|---|
| `idempotency_key` | Identifies the logical operation |
| `request_hash` | Detects payload differences when a key is reused |
| `operation` | Distinguishes the action type |
| `tenant_id` | Isolates scope |
| `status` | Processing status |
| `response/result` | Result replayed for duplicate requests |

The fingerprint should be computed from fields that affect the business outcome after normalization. Do not hash raw JSON if property order, whitespace, number formatting, or date representations can differ while carrying the same meaning.

For example, the following two payloads carry the same meaning:

~~~json
{"orderId":"ord-7","quantity":2}
~~~

~~~json
{
  "quantity": 2,
  "orderId": "ord-7"
}
~~~

The byte hashes of these two JSON strings differ. You can canonicalize JSON, or better yet, construct a canonical representation from the validated command:

~~~java
public record CreateOrderFingerprintInput(
        String tenantId,
        String customerId,
        String currency,
        java.util.List<LineFingerprint> lines) {
}

public record LineFingerprint(
        String sku,
        int quantity,
        long unitPriceMinor) {
}
~~~

Whether line-item order is significant depends on the contract. If order is insignificant, sort deterministically before hashing; if significant, preserve the order. Do not apply normalization that alters semantics.

### Java: Generating a SHA-256 Fingerprint

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class RequestFingerprint {
    private RequestFingerprint() {
    }

    public static String sha256(String canonicalPayload) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonicalPayload.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }
}
~~~

This function assumes `canonicalPayload` was constructed deterministically from the validated command. Do not include secrets or raw payment credentials in the fingerprint input unnecessarily. A SHA-256 fingerprint is for comparing payloads; it is not a request authentication signature.

When a key already exists:
- Matching hash: this is a retry/duplicate of the same operation.
- Different hash: return a conflict error per API contract, typically HTTP 409, and do not execute the business logic.

Do not overwrite the old fingerprint with the new fingerprint when a key is reused.

## 4. Persisting Idempotency State Durably

Idempotency records must live in a shared data store accessible by every instance handling the same scope. For financial operations or critical writes, a database with transactions and unique constraints is typically the right choice.

PostgreSQL example:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation          VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    status             VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    result_reference   VARCHAR(300),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    lease_owner        UUID,
    lease_until        TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation, idempotency_key),
    CHECK (status IN ('PROCESSING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_FINAL'))
);

CREATE INDEX idx_idempotency_expiry
    ON idempotency_record (expires_at);
~~~

Explanation:

- The primary key prevents two instances from creating two records for the same key/scope.
- `request_hash` detects key reuse with a different payload.
- `status` captures processing progress.
- `response_status` and `response_body` allow returning the prior result if the API must replay responses.
- `result_reference` can point to the order/payment record instead of storing a large response.
- `expires_at` is the logical expiry timestamp under the retention policy.
- `lease_owner` and `lease_until` support long-running work that may require takeover.

Not every system needs every column. For a short synchronous operation in the same database, leases may not be needed. For an event consumer, you might only need event ID, consumer name, status, and processed time. Design to match the actual contract rather than copying a larger schema than necessary.

### How Much Result State Should Be Stored?

There are three common approaches:

1. Store the canonicalized response if it is small, stable, and permissible to store.
2. Store a resource ID/result reference and reconstruct the response from current business data.
3. Store an outcome code and status if the caller only needs to know whether the operation completed.

If storing the response body, consider PII, secrets, retention, encryption, and read permissions. Never store access tokens, credentials, or card data. When replaying sensitive responses, authenticate and authorize the current caller before returning stored results.

## 5. Processing States and State Transitions

A straightforward model:

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key
    PROCESSING --> SUCCEEDED: Commit result
    PROCESSING --> FAILED_RETRYABLE: Transient failure
    PROCESSING --> FAILED_FINAL: Permanent failure
    FAILED_RETRYABLE --> PROCESSING: Retry / lease takeover
    SUCCEEDED --> [*]
    FAILED_FINAL --> [*]
~~~

| State | Meaning | Duplicate Request |
|---|---|---|
| `PROCESSING` | A worker has claimed the key and is processing | Wait, return in-progress, or retry later; do not execute the side effect in parallel |
| `SUCCEEDED` | Business outcome has committed | Return the stored result |
| `FAILED_RETRYABLE` | Transient error, safe to retry | Allow retry per policy and lease |
| `FAILED_FINAL` | Business or permanent error | Return the stored error or require a new key per contract |

Not every error should be persisted as `FAILED_FINAL`. For instance, invalid input can be rejected before claiming the key; transient timeouts can be retried. Classify failures explicitly.

### Duplicate Requests While `PROCESSING`

If a key is claimed but has no final outcome yet, the API must define the behavior:

- Wait briefly and re-read the result.
- Return HTTP 202 with an operation/status URL for caller polling.
- Return HTTP 409 or 425/429 per contract, with `Retry-After` if appropriate.
- For queue consumers, do not acknowledge the message if work is unfinished; let the trigger retry per policy.

Never let a second request execute the same side effect merely because the first request has not yet recorded `SUCCEEDED`. Exact behavior depends on the trigger type and SLA.

## 6. Atomic Claim via Unique Constraint

Do not use a "SELECT first, then INSERT if missing" flow without atomic protection. Two invocations can both observe no existing record and both execute the business action.

Dangerous pattern:

~~~sql
SELECT *
FROM idempotency_record
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key;

-- If no row exists, both invocations can proceed and INSERT.
~~~

Use a unique constraint with an atomic insert:

~~~sql
INSERT INTO idempotency_record (
    tenant_id,
    operation,
    idempotency_key,
    request_hash,
    status,
    expires_at
)
VALUES (
    :tenant,
    :operation,
    :key,
    :request_hash,
    'PROCESSING',
    :expires_at
)
ON CONFLICT (tenant_id, operation, idempotency_key) DO NOTHING
RETURNING tenant_id;
~~~

- A row returned: the current invocation claimed the key.
- No row returned: the key already exists; read the existing record and compare fingerprint/status.
- If two transactions insert the same key concurrently, the unique index arbitrates contention. The second transaction waits for the first transaction's outcome under database isolation/locking semantics before learning whether its insert succeeded.

This provides database-level concurrency protection. A `synchronized` block or `ConcurrentHashMap` in Java cannot replace it because invocations can run across multiple JVMs.

## 7. Pattern A: Short Synchronous Operations in the Same Database Transaction

If the business state and idempotency record live in the same database, the simplest approach is placing claim, business writes, result storage, and outbox insertion inside **the same transaction**:

1. Begin transaction.
2. Insert the idempotency key protected by a unique constraint.
3. If the insert fails because the key exists, read the committed record and handle the duplicate.
4. If the claim succeeds, perform the business writes.
5. Write the outbox event if an event needs to be published.
6. Update the idempotency record to `SUCCEEDED` and store the result.
7. Commit the transaction.
8. Only after committing, return the response or acknowledge the message.

When the transaction rolls back, both the claim and the business writes roll back. A later retry can claim the key again. When the transaction commits, duplicate requests see `SUCCEEDED` and return the stored result.

### SQL Example Inside a Transaction

~~~sql
BEGIN;

INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, status, expires_at
)
VALUES (
    :tenant, 'orders.create', :key,
    :request_hash, 'PROCESSING', :expires_at
)
ON CONFLICT DO NOTHING
RETURNING tenant_id;

-- Proceed only if INSERT returned a row:
INSERT INTO orders (order_id, tenant_id, customer_id, status)
VALUES (:order_id, :tenant, :customer_id, 'CREATED');

INSERT INTO outbox_event (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :event_id, :order_id, 'OrderCreated', :payload, now()
);

UPDATE idempotency_record
SET status = 'SUCCEEDED',
    response_status = 201,
    response_body = :response_json,
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = 'orders.create'
  AND idempotency_key = :key;

COMMIT;
~~~

Business writes execute only if the claim succeeded. If the claim failed, roll back/close the current transaction and read the existing record in a new transaction or handle it via equivalent logic. Do not proceed with inserting the order.

In this model, `PROCESSING` may not be visible to other transactions because the record commits alongside the final result. That is intentional: short operations execute atomically, while duplicates wait for the first transaction and then read the final outcome. If a transaction would run for minutes, holding locks that long is inappropriate; use a separate lease model instead.

### Java: Transaction Boundaries

Illustrative example with Spring:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateOrderTransactionalService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CreateOrderTransactionalService(
            IdempotencyRepository idempotency,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.idempotency = idempotency;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public StoredResult create(
            CreateOrderCommand command,
            String requestHash) {

        boolean claimed = idempotency.tryInsertProcessing(
                command.tenantId(),
                "orders.create",
                command.idempotencyKey(),
                requestHash);

        if (!claimed) {
            throw new DuplicateKeyException(
                    "Idempotency key already exists");
        }

        Order order = orders.insert(command);
        outbox.insert(OrderCreatedEvent.from(order));

        StoredResult result = StoredResult.created(order);
        idempotency.markSucceeded(
                command.tenantId(),
                "orders.create",
                command.idempotencyKey(),
                result);

        return result;
    }
}
~~~

This is an application service outline. The adapter/controller must catch `DuplicateKeyException` or `claimed = false`, read the committed record, and:
- compare the request hash;
- return the stored result if `SUCCEEDED`;
- return conflict if the hash differs;
- handle in-progress if the architecture commits `PROCESSING` separately.

Do not call payment providers or external APIs inside a long database transaction. This transaction pattern is only appropriate when side effects commit in the same database or are written to an outbox.

## 8. Pattern B: Long-Running Work with Leases and Recovery

A workflow can run for minutes or wait for callbacks. Do not hold a database transaction open throughout that time. Instead:

1. Atomically claim the key and commit the `PROCESSING` state.
2. Record `lease_owner` and `lease_until`.
3. Have the worker perform the work outside the transaction.
4. Renew the lease while work remains active.
5. Upon completion, update to `SUCCEEDED` conditioned on the owner token still matching.
6. If the worker dies, another worker can take over after the lease expires.
7. If the old worker recovers, it must not be allowed to overwrite the new worker's result.

Example initial claim:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, status, lease_owner,
    lease_until, expires_at
)
VALUES (
    :tenant, :operation, :key,
    :request_hash, 'PROCESSING', :owner_token,
    now() + interval '60 seconds',
    :expires_at
)
ON CONFLICT DO NOTHING
RETURNING *;
~~~

Renew the lease only while the current worker still owns the record:

~~~sql
UPDATE idempotency_record
SET lease_until = now() + interval '60 seconds',
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key
  AND status = 'PROCESSING'
  AND lease_owner = :owner_token
  AND lease_until > now();
~~~

If the update count is 0, the worker no longer holds the lease or the lease has expired. It must stop initiating new side effects and inspect the current state.

### Takeover After Lease Expiry

A new worker can reclaim an expired `PROCESSING` record via a conditional update:

~~~sql
UPDATE idempotency_record
SET lease_owner = :new_owner_token,
    lease_until = now() + interval '60 seconds',
    updated_at = now()
WHERE tenant_id = :tenant
  AND operation = :operation
  AND idempotency_key = :key
  AND status = 'PROCESSING'
  AND lease_until < now()
RETURNING *;
~~~

Only one worker can succeed in updating the same record under proper transaction/locking semantics. Use database time (`now()`) for lease comparisons to avoid relying on instance clocks.

### Owner Tokens and Fencing

An owner token prevents the old worker from updating the record after a new worker takes over. However, checking the token in the database alone is insufficient if the old worker already sent a request to a payment provider or external system.

For resources that support fencing, use a monotonically increasing token (fencing number/version) and require the target resource to reject operations bearing stale tokens. If the target system does not support fencing, you need a stable idempotency key on the target system or a reconciliation mechanism.

A lease is not proof that the old worker has stopped. It only indicates logical ownership has expired. The old worker may have paused and resumed; every write must be guarded by owner/fencing checks and side effects must be idempotent.

## 9. `FAILED` States and Retry Policies

Not all failures are handled the same way.

| Error Category | Examples | State / Policy |
|---|---|---|
| Validation / permanent business error | Invalid quantity, locked account | Can save `FAILED_FINAL` or reject before claiming |
| Business conflict | Out of stock, disallowed state transition | Save error outcome if the contract requires retries with the same key to return the same result |
| Transient infrastructure | Database temporarily unavailable | Roll back short transaction or mark `FAILED_RETRYABLE` |
| Ambiguous timeout | Downstream request timed out after sending | Query downstream or retry with the same idempotency key |
| Worker crash | Instance reclaimed while `PROCESSING` | Lease expiry and recovery |
| Permission / configuration error | IAM `AccessDenied`, wrong secret | Do not retry indefinitely; alert and fix configuration |

If the same key has already received a final business error, should a retry return the same error or be allowed to try again when conditions change? This must be decided in the API contract.

Examples:
- For `orders.create`, if out-of-stock is the final outcome of that request, retrying with the same key should return the stored conflict; to try again after stock is replenished, the client creates a new key.
- For a transient database error before commit, the transaction rolls back and the key is not recorded; retrying with the same key can run again.
- For a payment timeout where it is unknown whether the charge occurred, do not create a new key. Query the provider or retry with the same downstream idempotency key.

## 10. Determining the Retention Window and TTL

The retention window is how long the system keeps idempotency records to recognize retries/duplicates of the same operation. If records are deleted too early, a late retry may be treated as a new request and trigger side effects again.

Determine **the latest point in time when the same operation can still be resubmitted**, measured from initial acceptance. Retention must cover that entire span plus a safety margin.

Time horizons to account for:

- Client retry window: how long can a client or mobile app retry?
- API gateway / load balancer retries: do intermediate layers retry automatically?
- Queue retention and redelivery: how long can a message remain and be redelivered?
- Visibility/ack deadlines and retry backoff: can a message be redelivered after multiple backoff delays?
- DLQ retention and replay: how long afterward can an operator replay a message?
- Workflow timeout: how long can an execution continue or resume?
- Scheduled retries or delayed delivery: until when can work be rescheduled?
- Disaster recovery / restore: how far back can backups or event archives be replayed?
- Clock skew and operational time: margin needed to avoid expiring right at the boundary.

A guiding formula:

~~~text
retention window
  >= latest permitted retry/redelivery/replay horizon
     + operational safety margin
~~~

If windows occur sequentially, sum the durations from first receipt to the latest possible replay. If they are independent limits measured from the same origin, take the maximum. Do not set TTL based solely on the HTTP client's retry window while ignoring DLQs or manual replays.

### Example Retention Calculation

Suppose:
- Clients can retry for 24 hours.
- The queue retains messages for up to 4 days.
- The DLQ can be replayed within 14 days from initial receipt.
- Operations need an extra 2 days to handle incidents.

Retention must cover at least 14 days + 2 days margin = 16 days, assuming the DLQ horizon is measured from initial receipt. If DLQ retention starts only after a message moves to the DLQ and adds onto queue retention, calculate the actual sequential horizon rather than taking a simple maximum.

### TTL Is Not an Exact Deletion Timestamp

Many data stores support TTL via asynchronous physical deletion. For example, DynamoDB TTL, Firestore TTL, or cache expiration mechanisms may not remove a record at the exact second of `expires_at`. PostgreSQL typically requires a scheduled cleanup job or partition retention to delete records.

Therefore, separate two concepts:

- **Logical expiry:** the application considers a key expired according to `expires_at`.
- **Physical deletion:** storage actually deletes the record later to reclaim space.

Storage TTL is a cleanup mechanism and should not be the sole logic deciding whether a duplicate is allowed to run again. The application must explicitly check `expires_at` and enforce its expired-record policy.

### Do Not Let `PROCESSING` Records Expire Arbitrarily

If a record is `PROCESSING` and `expires_at` arrives before work finishes, TTL could delete the record and another invocation could create a new claim while the old worker is still running.

For long-running work:
- Lease deadline and retention expiry are two separate timestamps.
- A lease can expire so another worker can take over.
- Retention must not end while the operation is still `PROCESSING`.
- Start the retention countdown only after a terminal state is recorded, or set `expires_at` far enough out and extend it while processing continues.
- Cleanup jobs must not delete `PROCESSING` records with an active lease.

## 11. TTL Behavior by Storage Type

TTL mechanics vary by platform:

| Storage | Common Mechanism | Design Notes |
|---|---|---|
| PostgreSQL/MySQL | `expires_at` column + scheduled cleanup/partitioning | Application enforces logical expiry itself; cleanup can run in batches |
| DynamoDB | TTL attribute in epoch time | Asynchronous physical deletion; do not rely on items disappearing on time |
| Redis | Key expiry / `EXPIRE` | Suitable for cache/coordination when durability and failover are configured appropriately; consider eviction/persistence |
| Firestore | TTL policy on a timestamp field | Background deletion, not guaranteed immediately at expiry time |
| Object/event archive | Lifecycle/retention policy | May need to retain events/schemas longer than idempotency records |

Not every store offers the same semantics for atomic conditional writes, durability, replication, and TTL. Before choosing an idempotency store, verify:
- Does it support atomic insert-if-absent or conditional updates?
- Do unique constraints work across the required multi-region scope?
- Is read-after-write consistency sufficient for duplicate detection?
- Can TTL delete a `PROCESSING` record?
- Could failover or restore lose recently written keys?
- Do throughput and cost fit the request volume?

For financial workloads, do not rely on an evicting cache as the sole source of truth for idempotency if losing a key could cause duplicate charges. Redis can serve as a coordination or optimization layer, but the authoritative record should live where durability and consistency meet business requirements.

## 12. Expired Records and Behavior When Keys Reappear

When a key passes logical retention, there are several options:

1. **Allow a new operation:** appropriate when the contract defines keys as unique only within a time window.
2. **Reject old keys:** appropriate when keys are treated as never-reusable identifiers.
3. **Allow reuse only with matching payload or a new business version:** requires explicit rules and atomic enforcement.

For payments or order creation with lasting consequences, it is usually best to have durable business unique constraints alongside TTL-based idempotency. For instance, an order ID or payment operation ID must not be recreated merely because an idempotency record expired.

If an expired record still exists due to asynchronous cleanup, do not blindly delete and re-insert in two separate operations. Use a transaction and conditional update against `expires_at`, status, and lease so only one invocation can reuse the record. If an old key can still arrive from a DLQ replay, the chosen retention was too short.

## 13. Side Effects Outside the Database

A SQL transaction cannot atomically span a payment provider, email API, object storage, and another database. Side effects require dedicated design.

### Use Downstream Idempotency Keys

If a payment provider supports idempotency, pass the same key on every retry of the same payment operation. Store the provider reference and result so you can query status on an ambiguous timeout.

Do not generate a new key merely because the previous call timed out. A timeout does not prove the provider did not execute the charge.

### Transactional Outbox

When updating a database and publishing an event:

1. Within one transaction, write the business record, idempotency result, and outbox event.
2. A worker reads the outbox and publishes the event.
3. Once publishing succeeds, mark the event as sent.
4. If the worker crashes before marking sent, the event may be republished.
5. Consumers deduplicate using the stable event ID.

The outbox bridges the gap between a database commit and message publishing. It does not guarantee the broker delivers only once.

### Sagas and Compensation

For multi-system workflows such as reserving inventory then charging payment:
- Persist the state of each step.
- Use a dedicated idempotency key per business action.
- Retry retryable steps.
- If a later step fails permanently, execute compensation such as releasing inventory or issuing a refund.
- Persist compensation outcomes so retrying compensation is also idempotent.

Do not treat code rollback or deleting an idempotency record as compensation. Side effects that already occurred in external systems require compensating business actions.

## 14. Java: Modeling Idempotency State

States and processing decisions can be represented with explicit Java types:

~~~java
public enum IdempotencyStatus {
    PROCESSING,
    SUCCEEDED,
    FAILED_RETRYABLE,
    FAILED_FINAL
}

public sealed interface IdempotencyDecision {
    record Execute(String ownerToken) implements IdempotencyDecision {}
    record Replay(StoredResult result) implements IdempotencyDecision {}
    record InProgress(java.time.Instant retryAfter)
            implements IdempotencyDecision {}
    record KeyConflict() implements IdempotencyDecision {}
    record RejectFinal(StoredResult result)
            implements IdempotencyDecision {}
}

public record StoredResult(
        int statusCode,
        String responseBody,
        String resourceId) {
}
~~~

The store interface can be kept framework-independent:

~~~java
public interface IdempotencyStore {
    IdempotencyDecision claim(
            IdempotencyScope scope,
            String key,
            String requestHash);

    void complete(
            IdempotencyScope scope,
            String key,
            String ownerToken,
            StoredResult result);

    void markRetryableFailure(
            IdempotencyScope scope,
            String key,
            String ownerToken);

    void extendLease(
            IdempotencyScope scope,
            String key,
            String ownerToken);
}

public record IdempotencyScope(
        String tenantId,
        String operation) {
}
~~~

The real implementation must guarantee atomicity via database unique constraints or conditional writes. An interface does not create concurrency safety on its own; an in-memory fake is only suitable for sequential unit tests.

### Handling Claim Results in a Handler

~~~java
public final class IdempotentOrderHandler {
    private final IdempotencyStore store;
    private final PlaceOrderUseCase useCase;

    public IdempotentOrderHandler(
            IdempotencyStore store,
            PlaceOrderUseCase useCase) {
        this.store = store;
        this.useCase = useCase;
    }

    public StoredResult handle(
            IdempotencyScope scope,
            String key,
            String requestHash,
            PlaceOrderCommand command) {

        IdempotencyDecision decision =
                store.claim(scope, key, requestHash);

        if (decision instanceof IdempotencyDecision.Replay replay) {
            return replay.result();
        }
        if (decision instanceof IdempotencyDecision.KeyConflict) {
            throw new IdempotencyKeyConflictException();
        }
        if (decision instanceof IdempotencyDecision.InProgress) {
            throw new OperationInProgressException();
        }
        if (decision instanceof IdempotencyDecision.RejectFinal rejected) {
            return rejected.result();
        }

        IdempotencyDecision.Execute execute =
                (IdempotencyDecision.Execute) decision;

        try {
            PlaceOrderResult result = useCase.execute(command);
            StoredResult stored = new StoredResult(
                    201,
                    "{\"orderId\":\"" + result.orderId() + "\"}",
                    result.orderId());

            store.complete(
                    scope, key, execute.ownerToken(), stored);
            return stored;
        } catch (RuntimeException error) {
            store.markRetryableFailure(
                    scope, key, execute.ownerToken());
            throw error;
        }
    }
}

class IdempotencyKeyConflictException extends RuntimeException {
}

class OperationInProgressException extends RuntimeException {
}
~~~

This is a skeleton for work with separate claim/lease steps; do not use this exact pattern in place of the short transaction in Section 7. The JSON response here is string-concatenated for illustration; in production, use a serializer and store a normalized response. Also classify exceptions so only genuinely retryable failures are marked retryable.

With short transactions, claim, business writes, and completion must share the same transaction. If `store.complete` fails after the use case has executed an external side effect, downstream idempotency or reconciliation is required; you must not assume a retry is automatically safe.

## 15. Duplicate Handling Rules by Trigger

| Trigger | On Duplicate Receipt | While Processing | Once Succeeded |
|---|---|---|---|
| HTTP API | Compare key + fingerprint | 202/409/Retry-After per contract | Replay response/result |
| SQS/queue | Use message/event ID or business key | Do not ack until complete; lease/retry | Ack duplicate after confirming completion |
| Pub/Sub/event bus | Use stable event ID | Nack/retry or track in-progress state | Ack/return success per semantics |
| Workflow task | Key by execution + task/business action | Resume/checkpoint or lease | Return stored result |
| Scheduled invocation | Key by schedule occurrence/window | Only one worker claims | Skip or return prior run result |

Platforms differ in acknowledgment, retry, and ordering semantics. Adapters must map idempotency states to the right trigger behavior. Never return HTTP 200 or acknowledge a message just because the key is `PROCESSING` if doing so could lose unfinished work.

## 16. Security and Access Control for the Idempotency Store

Idempotency records can contain tenant IDs, operation names, resource references, and response data. Protect them as business data.

- Scope keys by tenant/account and operation.
- Authenticate and authorize callers before replaying responses.
- Never store tokens, passwords, payment credentials, or full card data.
- Restrict read/write permissions to the store per function.
- Encrypt data at rest and in transit.
- Apply retention and cleanup aligned with data policies.
- Do not put raw idempotency keys in metric labels.
- Log masked/hashed keys or correlation IDs when investigation is needed.
- Audit manual replay, reset, or record deletion actions.
- Do not allow clients to request deleting records to bypass the deduplication window.

If keys are guessable and responses contain sensitive data, an attacker could probe for old results. Therefore, idempotency keys do not replace authorization; response replay must respect the caller's current permissions.

## 17. Observing Idempotency and Retention

Track the following metrics:

| Metric/log | Meaning |
|---|---|
| `idempotency_claim_total` | Count of new claims |
| `idempotency_replay_total` | Requests returning a previously stored result |
| `idempotency_conflict_total` | Same key with a mismatched fingerprint |
| `idempotency_in_progress_total` | Duplicates hitting an in-flight operation |
| `idempotency_lease_takeover_total` | Count of lease takeovers by another worker |
| `idempotency_expired_key_total` | Keys arriving after logical retention expired |
| `idempotency_store_error_total` | Store read/write errors |
| `idempotency_record_age` | Age of records and their statuses |
| `outbox_oldest_unpublished_age` | Oldest event awaiting publication |

Keep metric labels bounded to operation, consumer, outcome, and environment. Do not use idempotency keys, tenant IDs, or order IDs as high-cardinality labels.

Alerts should focus on:
- Unusual spikes in conflict rates.
- `PROCESSING` records persisting longer than lease/processing SLAs.
- Sudden increases in lease takeovers.
- Store timeouts or conditional write failures.
- Record cleanup falling behind storage volume.
- Duplicates arriving after retention expiration.
- Growing outbox backlogs or DLQs.

Logs should include operation, masked key/hash prefix, event ID, masked owner token, status, and correlation ID. Never log sensitive response bodies.

## 18. Testing Idempotency and Crash Windows

Sequential unit tests are not enough to verify idempotency in distributed systems. Test in layers.

### Unit Tests

- Same key + same fingerprint + `SUCCEEDED` returns the stored result.
- Same key + different fingerprint returns conflict.
- New key claims successfully.
- `PROCESSING` returns in-progress state.
- `FAILED_RETRYABLE` can be reclaimed according to policy.
- `FAILED_FINAL` returns the stored error outcome.
- Keys past logical retention follow the contract.
- Stale workers cannot complete after the lease owner changes.

### Database / Concurrency Integration Tests

- Two transactions claiming the same key: only one succeeds.
- Two different keys for the same operation proceed independently.
- Duplicate requests wait for the first transaction to commit, then read the result.
- Transaction rollback leaves no partial record or business write.
- Unique constraints hold under many concurrent connections.
- Conditional takeover grants the lease to only one worker.
- Cleanup does not delete `PROCESSING` records with valid leases.

### Failure / Recovery Tests

| Crash Point | What to Verify |
|---|---|
| Before claim | Retry claims normally |
| After claim but before business write in the same transaction | Rollback removes the claim too |
| After business write but before commit | Entire transaction rolls back |
| After commit but before HTTP response | Retry replays the same result |
| After outbox publish but before marking sent | Event may republish, but consumer deduplicates |
| After external payment success but before local update | Retry uses same downstream key or reconciles |
| Worker dies while `PROCESSING` | Lease expires and a new worker takes over |
| Old worker recovers after takeover | Owner/fencing check prevents stale completion |
| DLQ replay days later | Record is still within retention and duplicates produce no new side effects |

### TTL Tests

- Keys within retention must replay the old result.
- Keys just past logical retention must follow the reuse/rejection policy.
- Uncompleted physical deletion in storage must not alter logical expiry.
- Cleanup jobs must not delete `PROCESSING` records.
- Replays within the DLQ window must not exceed retention.
- Backup restores or disaster recovery must not lose active keys.

Test time progression with a mock `Clock` or controlled timestamps in the test database. Do not use `Thread.sleep()` to wait for real TTLs in unit tests.

## 19. Idempotency State Design Checklist

- [ ] Identify which business operations require idempotency and which side effects are protected.
- [ ] Keep keys stable across client retries, broker redeliveries, and replays.
- [ ] Scope keys by tenant/account and operation.
- [ ] Detect same-key, different-payload reuse via fingerprints.
- [ ] Derive fingerprints from normalized commands, independent of JSON formatting.
- [ ] Store records in a shared durable store.
- [ ] Protect atomic claims with unique constraints or conditional writes.
- [ ] Define clear semantics for `PROCESSING`, `SUCCEEDED`, and failure states.
- [ ] Define appropriate HTTP/queue behavior for duplicates arriving while `PROCESSING`.
- [ ] Combine claim, business writes, outbox, and result in a short transaction when using one database.
- [ ] Use leases, owner tokens, recovery, and fencing for long-running work.
- [ ] Keep lease timeouts separate from retention TTLs.
- [ ] Size retention to cover client retries, queue retention, redelivery, DLQs, and replays.
- [ ] Enforce logical expiry independently of physical TTL deletion.
- [ ] Prevent cleanup from deleting active `PROCESSING` records.
- [ ] Protect external side effects with downstream idempotency or reconciliation.
- [ ] Enforce long-term business uniqueness separately from TTL-based idempotency.
- [ ] Check authorization before replaying responses and avoid exposing sensitive data.
- [ ] Emit metrics for replays, conflicts, in-progress hits, takeovers, and store errors.
- [ ] Implement unit, concurrency, integration, and crash-recovery tests.

## Self-Check

1. Why does a client timeout not prove that the first processing attempt failed?
2. How does idempotency differ from exactly-once processing?
3. Why must idempotency keys be scoped by tenant and operation?
4. What problem does a request fingerprint solve when a client reuses a key?
5. How does a unique constraint prevent the "SELECT then INSERT" race condition?
6. When should claim and business writes be combined in a single transaction?
7. Why does long-running work require leases and owner/fencing checks?
8. Which retry/redelivery/replay intervals must the retention window account for?
9. How does logical expiry differ from physical TTL deletion?
10. Why should TTL not delete a record that is `PROCESSING`?
11. If a payment provider already charged the card but the function timed out, how should retries behave?
12. What problem does the transactional outbox solve, and what does it not guarantee?
13. Why is an in-memory `Map` insufficient to protect idempotency across multiple function instances?
14. Which crash windows must be tested before deploying a consumer to production?

Persisting idempotent state is a core part of data design, not an afterthought cache bolted on after encountering duplicates. Keys must be stable and scoped, the database must claim atomically, state must support replay or recovery, and retention must span the entire period over which messages or requests can reappear. When combined with transactions, leases, downstream idempotency, outboxes, and crash-window testing, Java functions can retry safely without creating duplicate side effects.
