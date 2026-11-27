# Designing Idempotent Operations and Locks to Prevent Duplicate Processing

In a Spring Boot system, a request can be sent again because a user clicks a button twice, a browser retries after losing connectivity, an API gateway times out, or a worker receives a message again. If each receipt creates a new order, charges money, or sends a notification, the system produces duplicate side effects even though each individual call is valid.

**Idempotency** ensures that repeating the same logical request does not create additional unintended business outcomes. **Deduplication** identifies and skips duplicate deliveries or submissions. **Locks** coordinate processes competing to handle a resource at a given time. These three techniques are related but solve different problems: a lock does not automatically guarantee idempotency, and deduplication is effective only within its designed scope and retention window.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain **idempotent operations**, **idempotency keys**, **deduplication**, and **at-least-once delivery**.
2. Design APIs that accept idempotency keys, bind key scope, and store processing results.
3. Use unique constraints/transactions to prevent two concurrent requests from creating the same business result.
4. Distinguish database locks, distributed locks, leases, fencing tokens, and optimistic concurrency.
5. Use conditional writes such as ETag, generation/version, or create-if-absent for storage operations.
6. Combine idempotency with transactional outbox/inbox when the database and messaging do not share a transaction.
7. Understand the scope of duplicate detection/locks in Azure Service Bus, AWS SQS, and Google Cloud Pub/Sub.
8. Test retries, duplicate delivery, race conditions, lock expiry, and unknown outcomes.
9. Observe duplicates, conflicts, lock contention, and processing states without storing or logging sensitive data.

## 2. What Is Idempotency?

An operation \(f\) is idempotent if applying it multiple times with the same inputs and context produces an observable outcome equivalent to applying it once:

\[
f(f(x)) = f(x)
\]

This is a conceptual model; for APIs with side effects, you must clearly define what **observable outcome** includes—which data states, transactions, messages, emails, or payments are affected.

| Operation | Potentially Idempotent? | Conditions |
| --- | --- | --- |
| Read order details | Usually yes | Creates no side effects |
| Set order status to CANCELLED | Possibly | Updates state per rules without creating extra side effects |
| Increment inventory count by 1 | No | Each call increments again |
| Set inventory to an absolute value of 20 | Possibly | Same value and same condition/version |
| Create a new order | Not by default | Needs an idempotency key or unique business key |
| Send confirmation email | Not by default | Needs deduplication/outbox and duplicate-send control |
| Send message to broker | Not by default | Needs message identity/deduplication/consumer idempotency |

**HTTP methods do not automatically guarantee business idempotency.** PUT is usually designed to be idempotent under HTTP semantics; POST usually is not. However, if a PUT endpoint sends another email or charges money on every request, side effects can still repeat.

### Idempotency vs. Deduplication and Locks

| Concept | Question Addressed | Typical Mechanisms |
| --- | --- | --- |
| **Idempotency** | Does re-calling the same request create extra side effects? | Storing result by key, unique constraint, conditional update |
| **Deduplication** | Are two deliveries/sends with the same identifier the same message? | Message ID, inbox table, broker duplicate detection |
| **Lock** | Who is allowed to process a resource during this period? | DB row lock, lease, distributed lock |
| **Optimistic concurrency** | Did the data change between read and write? | Version, ETag, compare-and-set |
| **Fencing token** | How to prevent a stale lock holder from writing after lease expiry? | Monotonically increasing token verified at the write target |

A resilient system often combines several mechanisms: idempotency keys for APIs, unique constraints for atomicity, outbox/inbox for messaging, and locks only when coordinating work.

## 3. Why Can a Request or Message Be Processed Twice?

Common scenarios:

- The user clicks the pay button twice.
- The client sends a request and loses the response; not knowing whether the server committed, it retries.
- An API gateway retries a request after a timeout.
- A worker crashes after committing to the database but before acknowledging the message.
- The broker redelivers a message because the lock/visibility/ack deadline expired.
- A publisher sends a message successfully, loses the acknowledgment, and resends.
- Two replicas receive identical requests nearly simultaneously.
- A job scheduler reruns a job after missing a heartbeat.
- An upload operation is retried after the server already saved the blob but the client never received the response.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant DB as Database
    C->>A: POST /payments
    A->>DB: Commit payment
    DB-->>A: Commit succeeded
    A--xC: Response lost
    C->>A: Retry same request
    Note over C,A: Server cannot tell this is a retry without an idempotency key
    A->>DB: May create a second payment
~~~

**A timeout does not prove the operation never happened.** The request may have been processed and committed by the service while the response was lost on the way back. That is why you must design state tracking and post-timeout result lookup.

## 4. Idempotency Keys for APIs

An **idempotency key** is a stable identifier generated by the client or issued by the server representing a single business intent. The client must resend the same key when retrying the same intent.

Example:

~~~http
POST /api/payments
Idempotency-Key: 9a8b6f70-0a31-4f9c-8e0a-8e4f6dbcb120
Content-Type: application/json
~~~

Body:

~~~json
{
  "orderId": "ORD-2026-00125",
  "amount": 1250000,
  "currency": "VND"
}
~~~

If the client resends the same key and the same payload, the server returns the stored result or the in-progress status. If the same key arrives with a different payload, the server should reject it because one key must not represent two different intents.

### Key Design Rules

1. The key must remain stable across retries of the same operation.
2. The key must be sufficiently unpredictable if it can be used to retrieve results; do not treat the key as an authentication mechanism.
3. Key scope must be clearly defined: tenant, principal, operation, or endpoint.
4. Do not reuse a single shared key across all requests of a user.
5. Do not generate a new key on every client retry.
6. Store a payload fingerprint/hash to detect key reuse with different content.
7. Set retention aligned with how long clients can retry and business rules.
8. Do not embed personal information, secrets, or sensitive data in the key.

### Scope of an Idempotency Key

A key table should enforce uniqueness by scope:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

If uniqueness is enforced only by idempotency_key globally, collisions can occur across tenants or operations. If scoped by user when one user has multiple apps/operations, consider including client/application scope as well.

**A key does not replace authorization.** When returning a stored result, the server must still verify the current caller is authorized to view that result. Never let an idempotency key act as a bearer token to access a payment/order.

## 5. Payload Fingerprinting and Handling Key Reuse

Alongside the key, the server typically stores a **request fingerprint** to validate the payload.

Example:

~~~text
fingerprint = SHA-256(
    canonicalize(
        tenantId,
        operationName,
        normalizedRequestBody,
        relevantBusinessHeaders
    )
)
~~~

Canonicalization must be deterministic: logically identical data must produce the same fingerprint regardless of JSON field ordering or whitespace. Include only fields that truly define business semantics in the fingerprint; exclude trace IDs, transport timestamps, or headers that change on every retry.

| Request | Key | Fingerprint | Outcome |
| --- | --- | --- | --- |
| First call | K1 | H1 | Start processing |
| Retry of same request | K1 | H1 | Return stored result / in-progress status |
| Same key, different payload | K1 | H2 | Reject as conflict |
| New business intent | K2 | H3 | Process as a new request |

If the payload contains sensitive data, do not store the raw body just for comparison. Store a canonicalized hash; choose algorithms and protections matching security requirements. Hashing does not encrypt data and does not replace encryption/access control.

## 6. Storing Idempotency Records in a Database

A common design stores the record in the same database used by business logic.

PostgreSQL example:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       VARCHAR(64) NOT NULL,
    status             VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(100),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Common statuses:

| Status | Meaning |
| --- | --- |
| IN_PROGRESS | Key accepted and operation is currently processing |
| SUCCEEDED | Business operation finished; stored result can be returned |
| FAILED_FINAL | Failure that cannot be retried with the same intent/key per policy |
| RETRYABLE | Transient failure; allowed to continue per policy |
| UNKNOWN | Cannot determine whether side effects occurred; needs reconciliation |

Not every system needs all statuses. If the entire business operation and the idempotency record fit in one database transaction, it can be simpler. If a workflow spans multiple services, durable states and clear recovery rules are required.

### Why Is a Unique Constraint Needed?

Two requests with the same key can hit two replicas at the same time. Both may read that no record exists and both start processing. A SELECT before INSERT is not enough to prevent race conditions.

A **unique constraint/primary key** is the atomic guard in the database: only one transaction can insert the record for that key. The other request must read the existing record and decide to return the result, wait, or report in-progress.

~~~mermaid
sequenceDiagram
    participant A as Replica A
    participant B as Replica B
    participant DB as Database
    par Same idempotency key
        A->>DB: INSERT key K
        B->>DB: INSERT key K
    end
    DB-->>A: Insert succeeded
    DB-->>B: Unique constraint conflict
    A->>DB: Process and update record
    B->>DB: Read record K
    DB-->>B: IN_PROGRESS or stored result
~~~

**Do not use a distributed lock as a substitute for a unique constraint.** The database must enforce uniqueness right where business state is persisted.

## 7. Idempotent API Processing Flow

A general flow:

1. Authenticate the caller and check business permissions.
2. Read the idempotency key and determine tenant/operation scope.
3. Canonicalize the request and compute its fingerprint.
4. Attempt to create an idempotency record in IN_PROGRESS status atomically.
5. If the key already exists:
   - Different fingerprint: return conflict.
   - SUCCEEDED: return the stored result after verifying authorization.
   - IN_PROGRESS: return in-progress status or wait within bounds.
   - FAILED_FINAL: return the recorded terminal failure.
   - RETRYABLE/UNKNOWN: follow the recovery policy; do not blindly rerun.
6. The record owner executes the business logic within the appropriate transaction/boundary.
7. Persist the result, resource ID, and completion status.
8. Return the response.

### Responses for Duplicate Requests

| Record State | Possible Response | Meaning |
| --- | --- | --- |
| Succeeded | Same stored response/result, usually same success code | Retry receives the original outcome |
| In progress | 202 Accepted with operation URL or 409 Conflict per API contract | Client knows the operation is not finished yet |
| Same key, different payload | 409 Conflict | Key is already bound to a different request |
| Terminal failure | Return stored failure or matching error code | Do not rerun the same key |
| Unknown | 202/409 or status code per contract | Requires lookup/reconciliation |

No single status code is mandatory for all APIs. What matters is a clear contract, stable responses, and a way for callers to check status.

## 8. Spring Boot Example: Idempotency with a Unique Constraint

The example below illustrates structure; adapt data types and SQL to your actual database.

### 8.1. Entity/Record

~~~java
public record IdempotencyKey(
        String tenantId,
        String operation,
        String key) {
}

public record IdempotencyResult(
        String status,
        String requestHash,
        String resourceId,
        String responseJson) {
}
~~~

### 8.2. Repository Contract

~~~java
public interface IdempotencyRepository {

    boolean tryInsertInProgress(
            IdempotencyKey key,
            String requestHash);

    IdempotencyResult find(IdempotencyKey key);

    void markSucceeded(
            IdempotencyKey key,
            String resourceId,
            String responseJson);

    void markFailedFinal(
            IdempotencyKey key,
            String errorCode);
}
~~~

tryInsertInProgress must rely on an **INSERT with a unique constraint** and handle duplicate-key errors per database semantics. Never implement it as SELECT followed by INSERT without a unique constraint.

### 8.3. Application Service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApplicationService {

    private final IdempotencyRepository idempotency;
    private final PaymentRepository payments;
    private final RequestFingerprint fingerprint;

    public PaymentApplicationService(
            IdempotencyRepository idempotency,
            PaymentRepository payments,
            RequestFingerprint fingerprint) {
        this.idempotency = idempotency;
        this.payments = payments;
        this.fingerprint = fingerprint;
    }

    public PaymentResponse create(
            String tenantId,
            String key,
            CreatePaymentCommand command) {

        String operation = "CREATE_PAYMENT";
        String hash = fingerprint.of(command);
        IdempotencyKey id = new IdempotencyKey(
                tenantId, operation, key);

        boolean owner = idempotency.tryInsertInProgress(id, hash);

        if (!owner) {
            IdempotencyResult existing = idempotency.find(id);

            if (!existing.requestHash().equals(hash)) {
                throw new IdempotencyConflictException();
            }

            if ("SUCCEEDED".equals(existing.status())) {
                return PaymentResponse.fromJson(existing.responseJson());
            }

            if ("IN_PROGRESS".equals(existing.status())) {
                throw new OperationInProgressException();
            }

            throw new OperationNeedsReconciliationException();
        }

        return createPaymentAndComplete(id, command);
    }

    @Transactional
    protected PaymentResponse createPaymentAndComplete(
            IdempotencyKey id,
            CreatePaymentCommand command) {

        Payment payment = payments.create(command);
        PaymentResponse response =
                new PaymentResponse(payment.id(), "ACCEPTED");

        idempotency.markSucceeded(
                id, payment.id(), response.toJson());

        return response;
    }
}
~~~

This is **architectural pseudocode**, not a complete implementation. Several points must be addressed in real implementations:

- In Spring proxy mode, self-invocation of a @Transactional method may bypass the proxy. Extract transaction logic into a separate bean or place the transaction boundary properly.
- tryInsertInProgress and createPaymentAndComplete in this example need a consistent transaction strategy. If the IN_PROGRESS insert commits separately and the business transaction rolls back, orphan-record recovery is required.
- If the record and payment are written in the same transaction, the unique insert, payment insert, and mark-succeeded commit/roll back together. This suits short operations wholly inside one database.
- Avoid calling payment providers, Blob, or Service Bus inside a long database transaction whenever possible.
- If side effects happen outside the database, you need outbox/state machine/reconciliation; a database transaction cannot roll back an action already accepted by an external system.
- On a duplicate-insert conflict, the repository should re-read the record in a fresh transaction or after the conflicting transaction finishes, per database isolation semantics.

### 8.4. Right Transaction Boundaries

For business logic writing only within a single database:

~~~text
BEGIN
  INSERT idempotency record (unique key)
  INSERT payment/order
  UPDATE idempotency record = SUCCEEDED
COMMIT
~~~

If any step fails before commit, both the idempotency record and the payment/order roll back together. A later retry can re-attempt using the same key.

For business logic calling an external payment provider:

~~~text
BEGIN
  INSERT idempotency record
  INSERT payment intent / outbox command
COMMIT

Worker:
  Call payment provider with stable provider idempotency key
  Reconcile provider result
  Update payment and idempotency state
~~~

Do not hold a database transaction open while waiting on a remote payment API. Pass an idempotency key to the provider if supported and persist reconciliation state.

## 9. Choosing Where to Store Idempotency State

| Storage Option | Pros | Risks / Limitations |
| --- | --- | --- |
| **Same business database** | Unique constraints and transactions protect atomically | Adds DB load; needs retention/cleanup |
| Redis | Low latency, atomic operations/TTL | Not automatically synchronized with business transactions; eviction/failover can lose records |
| Cosmos DB | Conditional create/ETag, scale, and partitioning | Requires partition key/transaction scope design; consistency/unique key constraints scoped per container/partition |
| DynamoDB | Conditional writes and TTL | Partition key design, hot partitions, and TTL deletion is not instantaneous |
| Firestore | Transactions/create preconditions | Transaction limits and per-document/key contention |
| Broker deduplication | Reduces duplicate messages within a broker scope | Bounded window/semantics; consumers still must be idempotent |

If the idempotency record lives in Redis while the order/payment lives in a database, the two stores share no transaction. Redis may record the key and the database fail, or vice versa. Design explicit states, recovery, and a clear source of truth.

**For financial operations or critical side effects, database transactions/unique constraints paired with durable business state are generally a stronger foundation than a simple TTL cache.**

## 10. Message Deduplication: The Inbox Pattern

Brokers typically provide **at-least-once** delivery semantics. A message can be redelivered if a consumer fails to acknowledge/complete it, a lock expires, or the connection drops after processing.

Consumers should maintain an **inbox/processed-message table**:

~~~sql
CREATE TABLE processed_messages (
    consumer_name  VARCHAR(100) NOT NULL,
    message_id     VARCHAR(200) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref     VARCHAR(200),
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Flow:

1. Receive message with a stable MessageId.
2. Start a database transaction.
3. Insert (consumer_name, message_id) into the inbox.
4. On unique conflict, the message was already processed; skip business execution.
5. If insert succeeds, update business state.
6. Commit the inbox record and business state in the same transaction.
7. After commit, complete/ack the message.
8. If the process crashes after commit but before ack, the broker redelivers; the inbox detects the duplicate and the consumer simply completes/acks without repeating side effects.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Message M1
    C->>DB: BEGIN + INSERT inbox(M1)
    C->>DB: Update business state
    C->>DB: COMMIT
    C--xB: ACK lost / process crash
    B->>C: Redeliver M1
    C->>DB: INSERT inbox(M1)
    DB-->>C: Duplicate key
    C->>B: Complete/ACK, do not repeat business update
~~~

Crucial condition: **the inbox record and business state must be in the same transaction** for atomic protection. Writing the inbox to Redis and updating the database separately leaves a crash gap between the two steps that can still lose or duplicate work.

### Consumer Deduplication by Message ID

The Message ID must remain stable across publisher retries. If the publisher generates a new MessageId on every retry, the inbox cannot recognize duplicates. Use an operation/event ID derived from business state, not a random trace ID.

If the same message ID arrives with a different payload, the consumer should detect the conflict via fingerprint rather than silently ignoring it.

## 11. Transactional Outbox: Protecting the Publisher

Inbox protects the consumer; **outbox** protects publishing events from the database to the broker.

Suppose an API updates an order and emits OrderUpdated:

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders
  INSERT outbox_events
COMMIT

Publisher:
  Read pending outbox event
  Send to broker using stable event ID
  Mark sent after suitable acknowledgement
~~~

If the database commits successfully while the broker temporarily fails, the outbox record remains for the publisher to retry. If the broker accepted the message but the ACK was lost, the publisher can resend with the same event ID; the consumer inbox/deduplication handles the duplicate.

**Outbox does not create end-to-end exactly-once processing.** It ensures business state and publishing intent are saved atomically in the database; publishing can still repeat and consumers must be idempotent.

### Common Outbox States

| State | Meaning |
| --- | --- |
| PENDING | Not yet sent by a publisher |
| CLAIMED | A worker is processing / holding a lease |
| SENT | Publish confirmation received per contract |
| RETRY | Rescheduled for sending after a scheduled time |
| DEAD | Exceeded retry budget or terminal error; needs investigation |

Multi-replica publishers can use SELECT ... FOR UPDATE SKIP LOCKED, leases, or atomic claims to distribute work. Even though claiming prevents two workers from picking the same record normally, **stable message IDs and consumer idempotency remain essential** because a worker can crash after the broker accepts the message.

## 12. Locks: When Needed and When Not

A **lock** ensures only one process at a time may perform a piece of work within a given scope. However, locks can expire, lose connectivity, or continue to be used by an old process after a new process acquires the lock.

| Mechanism | Scope | Characteristics |
| --- | --- | --- |
| **In-process mutex** | Single JVM | Cannot coordinate across replicas |
| **Database row lock** | Transaction/database | Has transaction semantics, but long locks cause contention |
| **Unique constraint** | Database key | Prevents duplicate records; usually better than locks for uniqueness |
| **Optimistic locking** | Row/document/version | Detects concurrent updates without holding long locks |
| **Distributed lease** | Multiple processes | Has owner and expiration; must handle expiry/renewal |
| **Broker message lock** | Single message delivery | Bounds how long a consumer holds a message; does not guarantee side effects happen once |

### Do Not Lock Everything

If the goal is simply preventing two payments for the same idempotency key, a **unique constraint** is usually simpler and safer than a distributed lock.

Locks are useful for excluding expensive work over a period—for example, ensuring only one worker reconciles an account or one job handles a partition. Even with a lock, final writes should still enforce idempotency/version/fencing to guard against stale owners.

## 13. Distributed Locks, Leases, and Fencing Tokens

A distributed lock typically carries an expiration (**lease/TTL**) so that if a process crashes, the lock can be released after a bounded time.

Common Redis example:

~~~text
SET lock:account:123 <unique-owner-token> NX PX 10000
~~~

- NX: create the key only if it does not exist.
- PX 10000: 10-second TTL.
- unique-owner-token: distinct value identifying the lock owner.

On release, check the owner token before deleting the key atomically (e.g., via Lua script). If process A's lease expires and process B acquires a new lock, A must not delete B's lock.

### The Stale Owner Problem

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant L as Lock store
    participant B as Worker B
    participant R as Resource
    A->>L: Acquire lease
    L-->>A: Granted
    Note over A,L: A pauses longer than TTL
    L-->>B: A's lease expired
    B->>L: Acquire new lease
    L-->>B: Granted
    A->>R: Continues writing despite expired lease
    B->>R: Writes under new lease
~~~

If A can still write after its lease expires, two workers can mutate the resource concurrently. The lock key's TTL expiring does not stop the old process from continuing execution.

### Fencing Tokens

A **fencing token** is a monotonically increasing number issued each time a new lease is granted. The target resource accepts operations only from tokens greater than or equal to the latest recorded token, per the specific contract.

| Worker | Fencing Token | Outcome |
| --- | ---: | --- |
| Worker A | 41 | Accepted |
| Worker B after A's lease expires | 42 | Accepted, newer token |
| Worker A resumes | 41 | Rejected because token is stale |

Fencing works only if **the resource write target checks the token**. If the lock store issues tokens but the destination database/Blob/API does not validate them, the token cannot protect side effects.

### Lease Renewal

If work takes longer than the TTL, a worker can renew the lease. Ensure:

- Renew before expiry with an adequate safety margin.
- Only the current owner may renew.
- If renewal fails, the worker must stop initiating new side effects.
- Handle lost responses on successful renewals by verifying owner/token.
- Never treat renewal as proof that an older worker was not paused or that the network is healthy.

## 14. Optimistic Concurrency: ETags and Versions

Not every concurrent operation needs a lock. **Optimistic concurrency** lets multiple clients read data, but accepts an update only if the version has not changed.

Example:

1. Client reads order at version 7.
2. Another client updates it to version 8.
3. First client sends an update conditioned on version still being 7.
4. Database/service rejects it because current version is 8.
5. Client re-reads and decides to merge or return conflict.

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

If 0 rows are updated, the version changed or the resource does not exist. This is **compare-and-set**, not blind retry.

### ETags in Azure Storage

Azure Blob Storage supports conditions such as **If-Match**/**If-None-Match** based on ETags on appropriate operations:

- **If-None-Match: \*** can be used to create a blob only if it does not yet exist.
- **If-Match: <etag>** permits an update only if the current ETag matches the value previously read.
- If the condition fails, the service returns the corresponding precondition/conflict error.

These conditions prevent race-condition overwrites and support resource-level idempotency. Check the exact Blob SDK API and error codes for the version you use.

### An ETag Is Not an Idempotency Key

An ETag validates resource version/state. An idempotency key identifies a business intent. An operation may need both: the key to recognize retries of the same request, and the ETag to prevent another request from overwriting newer data.

## 15. Locks and Conditional Writes in Azure Services

### Azure Blob Storage

You can combine:

- Deterministic blob names derived from resource/operation ID.
- Create-if-absent using **If-None-Match: \***.
- Conditional updates using ETag/If-Match.
- Blob leases when exclusive access to a blob is needed for a period.
- Metadata storing operation ID or version to aid reconciliation.

**A Blob lease alone does not make an entire business operation idempotent.** Leases can expire or be lost, and side effects in a database or Service Bus lie outside the Blob lease's scope. When using leases, handle lease IDs, renewals, releases, and lease-conflict errors per the SDK/service contract.

### Azure Cosmos DB

For Cosmos DB, idempotency design must consider:

- Partition keys and transaction scope.
- **Transactional batch** applies only within a single logical partition per API support.
- Conditional create/upsert and ETag/If-Match per operation.
- Unique key policies configured on the container; unique keys are evaluated within a logical partition and have design constraints.
- Request charges/429s and SDK retries.
- Consistency level and how state is re-read after unknown outcomes.

Do not assume a single Cosmos DB transaction can update multiple logical partitions or stay atomic with Service Bus. When workflows cross transaction boundaries, use an appropriate outbox/saga/reconciliation pattern.

### Azure Service Bus

Service Bus provides several mechanisms for duplicate handling:

- **Duplicate detection** uses MessageId to recognize duplicate messages within a configured time window.
- **Peek-lock** holds a message during its lock duration; consumers complete/abandon/dead-letter per settlement rules.
- **Sessions** support ordered/grouped processing per session with session locks.
- Locks can be renewed per configuration/client behavior.

Duplicate detection has a **bounded time window and per-entity/configuration scope**; it is not an infinite idempotency store. If the same event is sent again after the window closes or with a different MessageId, the broker treats it as a new message. Consumers should still use a durable inbox/deduplication for critical side effects.

## 16. Comparing Idempotency and Deduplication on AWS, Azure, and Google Cloud

| Need | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Conditional object write | Blob ETag/If-Match/If-None-Match | S3 conditional requests/preconditions per API | Cloud Storage generation preconditions |
| Conditional DB write | Cosmos DB ETag/transactional batch/native unique key policy | DynamoDB condition expressions/transactions | Firestore transactions/create preconditions; Spanner transactions |
| Broker duplicate handling | Service Bus duplicate detection by MessageId/window | SQS FIFO deduplication by deduplication ID/window; content-based option | Pub/Sub message IDs/delivery semantics; exactly-once delivery scoped per subscription/region feature |
| Durable consumer deduplication | Inbox table/database | DynamoDB/relational inbox | Firestore/Spanner/relational inbox |
| Lock/lease | Blob lease, Service Bus message lock, database/Redis lease | SQS visibility timeout, DynamoDB conditional lease/lock | Pub/Sub ack deadline, database/lease store |
| Retries and unknown outcomes | SDK/service retry + idempotency state | SDK retry + conditional write | RPC retry + transaction/precondition |

Do not mechanically equate **Service Bus duplicate detection** with **SQS FIFO deduplication** or Pub/Sub exactly-once delivery. Scopes, retention windows, message ordering, redelivery, and ack semantics all differ.

### Key Limitations to Remember

- **Amazon SQS FIFO** has a finite deduplication window; producer retries outside the window or with a different deduplication ID can still create a new message.
- **Google Cloud Pub/Sub exactly-once delivery** is a scoped feature with specific conditions; it does not turn a consumer's downstream side effects into exactly-once.
- **Cloud Storage generation preconditions** protect object versions/write conditions, not databases and messaging at the same time.
- **DynamoDB conditional writes** can protect uniqueness/claims by key; TTL cleanup does not necessarily happen at the exact expiration second.
- **Cosmos DB unique keys** are scoped to a logical partition; partition keys must align with business invariants.

## 17. Retention, Cleanup, and Key Reuse

Idempotency records cannot be kept forever in every system. Determine retention based on:

- How long clients/proxies may retry a request.
- How long brokers may redeliver a message.
- Batch/job or workflow lifecycles.
- Audit and business dispute requirements.
- Risk of a client resending an old key after the record was deleted.

If records are purged too early, a late retry may be treated as a brand-new request and cause duplicate side effects.

### Retention Policy

| Operation Type | Retention Considerations |
| --- | --- |
| Side-effect-free API read | May not need an idempotency record |
| Order creation | Covers client retry window and duplicate-order prevention rules |
| Payment/financial operation | Follows business, reconciliation, and audit policies; usually longer than standard HTTP retries |
| Message inbox | At least covers redelivery/replay windows and duplicate-processing prevention |
| Outbox event | Until published/reconciled; history can be archived |
| Job scheduler | Covers job rerun/recovery windows |

### Key Expiry Does Not Mean Immediate Reuse Is Safe

If a payment completed, deleting its idempotency record after 24 hours does not mean the same key or business operation can safely be created again. You may need to retain a **unique business reference** longer than the technical record. Separate:

- Idempotency cache/record for technical retries.
- Unique business constraint protecting long-term invariants.
- Audit/history for investigation and reconciliation.

Cleanup should run in bounded batches, avoiding deletion of records that are IN_PROGRESS, UNKNOWN, or pending reconciliation. Partition by date/tenant or archive to manage storage size.

## 18. Handling IN_PROGRESS State and Dead Workers

A request may insert an IN_PROGRESS idempotency record and then crash. Without recovery, the key can remain stuck forever.

A long-running workflow design should also store:

- owner_id or worker ID.
- lease_until or next_heartbeat_at.
- attempt_count.
- last_error_code.
- updated_at.
- operation_deadline or expires_at.
- fencing_token if leases are used and the resource supports checking it.

A recovery worker can find records past their lease, check whether side effects occurred, and transition them to RETRYABLE, UNKNOWN, SUCCEEDED, or FAILED_FINAL.

**Never rely on TTL alone to conclude an old worker has stopped.** A process may pause for a long time and resume. When reclaiming work, fencing/version checks must stop the old owner from writing results after the new owner takes over.

### Unknown Status

If a request to a payment provider times out after sending, do not immediately mark it FAILED_FINAL. Call a lookup API by provider idempotency key/transaction reference if supported, or wait for webhooks/settlement to reconcile. While uncertain, keep the status UNKNOWN and block creating a new payment for the same business operation.

## 19. Locks Do Not Replace Idempotency: Message Processing Example

Suppose a Service Bus consumer processes an OrderPaid message:

~~~text
Worker A receives message, 30-second lock
Worker A calls payment/accounting service
Worker A pauses for 40 seconds
Lock expires
Worker B receives message again and processes it
Worker A resumes execution
~~~

Both A and B can execute the side effect if the target service does not check operation ID/version. A lock only lowers the probability of concurrent execution during the lease; it does not prove the old worker stopped.

Protections:

1. Use a stable MessageId/event ID.
2. Have the consumer insert an inbox record with a unique constraint in the same transaction as the business update.
3. If using a distributed lock for long work, use a lease + fencing token validated by the target resource.
4. Ensure external APIs receive an idempotency key if supported.
5. Complete the message after the business/inbox transaction commits.
6. If a crash happens before complete, redelivery is caught by the inbox.

### Message IDs Must Be Stable

Publishers should derive the event ID from the operation/event saved in the outbox. Generating a fresh UUID on every send attempt prevents broker duplicate detection and consumer inboxes from recognizing the same event.

## 20. Security of Idempotency Keys and Locks

- Do not treat an idempotency key as a credential or proof of authorization.
- Bind keys to tenant/principal and operation; verify authorization before returning cached responses.
- Avoid storing raw secrets or sensitive payloads in records when unnecessary.
- Do not log full request bodies, keys, or lock owner tokens if policy requires masking.
- Never allow callers to supply arbitrary resource IDs to retrieve another tenant's results.
- Lock keys must use clear namespaces and sensible TTLs; avoid key collisions across environments/tenants.
- Redis lock release must check the owner token atomically; never use unconditional DEL.
- Restrict access to idempotency/inbox/outbox tables and protect audit data.
- Cleanup must avoid deleting records currently in progress or needed for reconciliation.

## 21. Observability and Testing

### Metrics to Track

| Metric | Meaning |
| --- | --- |
| idempotency_first_seen_total | Requests seen for the first time |
| idempotency_replay_total | Duplicate requests served a stored response |
| idempotency_conflict_total | Same key with different fingerprint |
| idempotency_in_progress_total | Requests hitting an active in-progress operation |
| idempotency_unknown_outcome_total | Outcomes requiring reconciliation |
| deduplication_hit_total | Duplicate messages/resources detected |
| lock_acquire_total / lock_contended_total | Lock acquisition and contention counts |
| lease_expired_total | Leases expired before completion |
| fencing_rejected_total | Stale owners/tokens rejected |
| outbox_pending_count | Number of unpublished events |
| inbox_duplicate_total | Already-processed messages redelivered |

Do not put idempotency keys, user IDs, payment IDs, or message IDs into high-cardinality metric labels. Record those in controlled logs/traces with appropriate masking and retention.

### Mandatory Test Cases

| Scenario | Expected Outcome |
| --- | --- |
| Same key, same payload, sequential requests | Only one business effect; replay returns stored result |
| Same key, different payload | Conflict; business logic does not run a second time |
| Two concurrent requests with same key | Unique constraint grants ownership to only one |
| Process crashes after commit, before response | Retry receives the stored result |
| Process crashes before commit | Transaction rolls back; recovery allows retry |
| Message redelivery after commit, before ACK | Inbox detects duplicate |
| Lock expires, old worker continues | Fencing/version prevents stale write |
| Retry after retention expires | Unique business constraint still protects invariants |
| Publisher loses ACK after broker acceptance | Same event ID; consumer prevents duplicate processing |
| Redis lock store failover | Do not assume lock survived; verify fencing/idempotency |

### Testing Race Conditions

To test two concurrent requests:

1. Launch multiple threads or processes sending the same idempotency key.
2. Synchronize their start with a barrier/latch.
3. Record how many times the business operation actually executed.
4. Verify only one record/key was created.
5. Verify the remaining requests receive responses per contract.
6. Repeat across multiple replicas to verify database uniqueness, not just an in-JVM lock.

Never use synchronized in a single instance to conclude a multi-replica system is protected against duplicates.

## 22. Lab Exercise: Building an Idempotent Payment Creation API

**Context:** The Spring Boot Payment API receives POST /payments, creates a payment record, and publishes PaymentRequested to Service Bus. Clients may retry on lost responses; workers may crash after publishing.

### Part A — API Idempotency

1. Require the Idempotency-Key header.
2. Define scope (tenant_id, operation, key).
3. Canonicalize the request and compute its fingerprint.
4. Create an idempotency table with a unique constraint.
5. Within a database transaction, create the payment and update the idempotency result if all side effects remain inside the database.
6. If the same key/payload already succeeded, return the old result.
7. If the same key has a different payload, return conflict.
8. If in progress, return operation status or response per API contract.

### Part B — Outbox and Consumer Inbox

1. Inside the payment-creation transaction, insert an outbox event with a stable event ID.
2. The publisher fetches pending events using a bounded claim/lease.
3. Send the event to Service Bus with MessageId equal to the event ID.
4. Mark sent after acknowledgment per contract.
5. The consumer inserts an inbox record and updates business state in the same transaction.
6. On duplicate receipt, skip the business update and complete the message.

### Part C — Locks and Concurrency

1. Fire two concurrent requests with the same key.
2. Verify the unique constraint ensures only one payment.
3. If worker leases exist, use owner tokens/lease expiry and fencing/versioning.
4. Simulate an old worker continuing after lease expiration.
5. Verify stale writes are rejected at the state store.

### Part D — Fault Injection

1. Drop the response after the payment transaction commits.
2. Cause the publisher to lose the ACK after the broker may have accepted the message.
3. Kill the consumer after database commit but before message completion.
4. Trigger message redelivery and verify the inbox prevents duplicate side effects.
5. Submit the same key with a different payload and verify conflict.
6. Verify cleanup/retention does not delete records still needed for reconciliation.

### Deliverables

- Schemas for idempotency, outbox, and inbox.
- API contract for the key header and replay/in-progress/conflict responses.
- Transaction boundary and message flow diagrams.
- Evidence from concurrency, crash/retry, and redelivery tests.
- Retention, reconciliation, lock/lease, and fencing policies if used.
- Metrics for duplicates, lock contention, outbox backlog, and unknown outcomes.

### Self-Check Questions

1. Why does a client timeout not prove the server has not committed?
2. How must the same idempotency key with a different payload be handled?
3. Why is SELECT followed by INSERT insufficient against two concurrent requests?
4. How do a unique constraint and a distributed lock solve different problems?
5. Why does lock TTL expiration not guarantee an old worker stopped?
6. When checked by which component does a fencing token actually take effect?
7. Which transaction must the inbox record belong to in order to prevent duplicate message processing?
8. What gap between database and broker does the outbox protect?
9. Why does broker duplicate detection not replace consumer idempotency?
10. How does ETag/If-Match differ from an idempotency key?
11. Why must idempotency record retention account for business unique constraints as well?
12. When a payment provider times out with an unknown outcome, why should you not immediately create a new payment?

## 23. Takeaways

- **Idempotency** protects business outcomes when the same intent is resent; **deduplication** identifies duplicate sends/deliveries; **locks** coordinate processing rights within a scope and timeframe.
- Idempotency keys must be stable, scoped, payload-fingerprinted, and retained appropriately. Same key with a different payload must be rejected per API contract.
- **Unique constraints/conditional writes** are atomic guards at the state store. SELECT before INSERT and synchronized within a single JVM cannot stop multi-replica race conditions.
- **Distributed leases** can expire while an old worker is still running. Use fencing/versions validated at the target resource to block stale owners.
- **Inbox/outbox** protect the database-to-messaging boundary; they do not provide end-to-end exactly-once semantics, so consumers must remain idempotent.
- Blob ETag/lease, Cosmos DB partitions/transactions, Service Bus duplicate detection/locks, SQS FIFO/visibility, and Pub/Sub ack/exactly-once all have different scopes.
- Timeouts create unknown outcomes; state lookup, reconciliation, idempotency keys, and unique business constraints matter more than blind retries.
- Test concurrent requests, crashes between commit and ACK, lease expiry, duplicate delivery, payload conflicts, and retention; track duplicate hits, contention, and backlogs.

## References

- [Azure Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Blob Storage concurrency management](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Azure Cosmos DB transactional batch](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Azure Cosmos DB unique keys](https://learn.microsoft.com/azure/cosmos-db/unique-keys)
- [AWS SQS FIFO deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon DynamoDB condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html)
- [Google Cloud Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Cloud Storage request preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
