# Building Idempotency Keys Around Business Intent

In serverless architectures, the same request can arrive multiple times: an HTTP client retries after a timeout, a queue redelivers a message, Lambda retries an invocation, a workflow re-executes a state, or a user clicks a button twice. If every delivery triggers a new side effect, the system may create duplicate orders, charge a customer twice, or deduct inventory multiple times.

Idempotency ensures that a single business intent produces only one effective outcome, even when the request is sent or processed multiple times. The critical building block is the idempotency key: a stable identifier for one specific business execution.

A good key must answer the question: **Is this the same business intent being retried, or a new intent that happens to have an identical payload?**

You should not arbitrarily generate a key from the entire payload and treat two identical payloads as the same transaction. A customer can intentionally purchase the same product twice with the same quantity and price. Those are two valid, distinct intents. The key must be tied to the identity of the business operation, while a payload fingerprint is used to detect whether a key is being reused with different data.

This lesson covers how to identify business intent, design key scope and lifecycle, store idempotency state safely under concurrency, handle external side effects, and apply these patterns in Java serverless workloads.

## 1. What Problem Does Idempotency Solve?

An idempotent operation can be executed repeatedly without changing the final business outcome after the first execution.

Examples:

- Creating an order with the same key creates only one order.
- Capturing a payment with the same key creates only one payment capture.
- Recording a processed event with the same event identity does not run side effects again.
- Releasing an already-released reservation does not increment inventory twice.

Conversely, if the same request is processed twice and creates two orders or two charges, that operation is not idempotent.

### 1.1. Why Are Serverless Systems Prone to Duplicates?

Serverless systems commonly favor retry-based delivery to improve work completion guarantees. As a result, a handler can be invoked again in scenarios such as:

- An HTTP client misses the response due to a network timeout even though the server already committed.
- Lambda processes a message but fails before the event source receives a success acknowledgment.
- SQS or Pub/Sub redelivers a message.
- A worker completes a side effect but loses connectivity before acknowledging.
- Step Functions retries a Task after a transient error.
- A user resubmits a request because they do not know whether the previous attempt succeeded.
- A DLQ message is replayed hours or days later.

You cannot rely on the assumption that a message will only be delivered once. Design consumers so that duplicate delivery does not repeat business impact.

### 1.2. Idempotency Is Not Exactly-Once Delivery

It is important to distinguish:

| Concept | Meaning |
|---|---|
| At-most-once | Operations may be lost, but are never processed repeatedly |
| At-least-once | Operations may be delivered/processed repeatedly to reduce the risk of losing work |
| Deduplication | Identifying and ignoring duplicates based on an identity |
| Idempotent effect | Repeating an operation creates no additional business impact |
| Exactly-once effect | A business effect is committed exactly once within a defined boundary |

A single queue or function cannot by itself guarantee exactly-once execution across an entire chain consisting of a broker, Java process, database, and payment provider. In practice, systems achieve an **effectively-once business outcome** by combining retry-based delivery, idempotency keys, unique constraints, transactions, outbox/inbox patterns, and reconciliation.

Do not label a system as exactly-once if it only performs in-memory deduplication or relies solely on a queue's FIFO feature.

## 2. Identify Business Intent Before Creating a Key

An idempotency key represents a single business execution, not necessarily a payload or a message.

For example, the same customer might place two separate orders with identical contents. Each click to confirm a purchase is a separate intent. The system needs a distinct order request ID or operation ID for each confirmation.

Common business intents and suitable keys:

| Business Operation | Suitable Intent Identifier |
|---|---|
| Create order | Order request ID generated when the user confirms |
| Capture payment | Payment attempt ID |
| Refund | Refund request ID |
| Reserve inventory | Reservation request ID |
| Send invoice | Invoice delivery operation ID |
| Process an event | Event source + event ID, combined with business operation ID if needed |
| Run a batch item | Batch run ID + item operation ID |

Example with payments:

- Order 1042 has payment attempt A.
- The provider times out and the worker retries attempt A.
- All retries of attempt A must use the same key.
- If the payment is declined and the user explicitly retries with a new payment attempt, attempt B must have a different key.

Do not use the order ID as the key for every payment attempt if business rules allow multiple valid payment attempts.

### 2.1. Do Not Derive the Key Solely from a Payload Hash

Suppose two requests both have the following body:

~~~json
{
  "sku": "BOOK-01",
  "quantity": 1,
  "unitPrice": 250000
}
~~~

If you use the SHA-256 hash of the payload as the key, two independent purchases will be treated as the same operation. The second request may return the result of the first purchase, preventing the customer from creating a new order.

A payload hash serves a different purpose: it acts as a **request fingerprint** to verify whether the same key is being used with the same content.

Rules:

- The business intent ID generates or identifies the key.
- The fingerprint validates the request content.
- The key remains unchanged across retries of the same intent.
- A new intent must have a new key, even when the payload is identical.

## 3. Design the Scope of an Idempotency Key

A key must be placed within a clear scope. The same key string can be valid for two different tenants or two different operations.

A scope typically consists of:

- Authenticated tenant or account.
- Operation/API name.
- Idempotency key.
- Optionally a contract version if semantics change.

Example composite unique key:

~~~text
tenant_id + operation_name + idempotency_key
~~~

Example:

~~~text
tenant=tenant-17
operation=capture-payment
key=pay-attempt-8d71...
~~~

Do not place a unique constraint on the key globally if the system allows multiple tenants to generate their own keys. Conversely, do not omit the tenant from the scope and assume clients will always generate globally unique keys.

Scope should also prevent a key from colliding across endpoints. A key for `create-order` should not conflict with a key for `refund-payment` just because the client sent the same string.

### 3.1. Keys Need Sufficient Entropy and Must Not Contain Sensitive Data

If the client generates the key, use a random UUID or a value with sufficient entropy. If the server generates the operation ID, create and persist that ID before the first attempt so retries can reuse it.

Do not include email addresses, phone numbers, card numbers, customer names, or sensitive data in the key. Keys may appear in databases, logs, traces, or support tools.

Do not treat an idempotency key as an authorization credential. Possessing a key does not automatically grant permission to view or modify the result; every request must still authenticate and enforce authorization by tenant/resource.

You may log a truncated fingerprint or masked reference for investigation, but avoid logging the full key unnecessarily.

## 4. Generate and Propagate Keys Across Retries

A key must be created at the boundary where the system knows a new business intent begins.

HTTP API example:

1. The client generates an `Idempotency-Key` for the submit-order action.
2. The client sends the key with the request.
3. On timeout, the client resends the exact same key and the same payload.
4. The server returns the saved result if the prior operation completed.
5. When the user starts a new order placement, the client generates a new key.

Message consumer example:

1. The producer generates an operation ID when the business action begins.
2. The event carries the operation ID in its payload or trusted metadata.
3. The broker redelivers the event, and the consumer reads the same operation ID.
4. All retries and redeliveries reuse that key.
5. Replaying from a DLQ also preserves the operation ID if it is still the same business intent.

Do not generate a new UUID at the start of every Lambda invocation. If every retry generates a new key, the system treats each attempt as a new operation and idempotency breaks down.

### 4.1. Do Not Use Execution ID or Attempt Number as a Business Key

Step Functions execution ARNs and retry attempt numbers are useful for tracing and operations, but they do not necessarily represent business intent.

If an operator starts a new execution to recover a failed order, the execution ARN will be different. The business operation ID must be preserved in the input or retrieved from the business record.

Similarly, do not append the attempt number to the key of a capture operation if retries are supposed to represent the same capture. An attempt number is only appropriate when the business domain genuinely creates a new intent, such as a customer confirming a new payment attempt.

## 5. HTTP APIs with Idempotency-Key

An API can accept the key via a header:

~~~http
POST /v1/orders
Idempotency-Key: 3d9b3c5e-2e7f-4a4d-9f9e-7c...
Content-Type: application/json
~~~

The server needs to:

1. Authenticate the caller and determine the tenant.
2. Verify that the key is present, properly formatted, and within length limits.
3. Determine the operation scope.
4. Canonicalize the request and compute its fingerprint.
5. Claim the key atomically in the database.
6. If already completed with the same fingerprint, return the stored result.
7. If the key is in progress, return a response according to the published contract.
8. If the same key has a different fingerprint, reject the request.

### 5.1. Responses When a Request Is Resubmitted

The API should clearly define responses for each state:

| Key State | Possible Behavior |
|---|---|
| Does not exist | Claim and execute the operation |
| In progress | Return 202 with an operation status URL, or 409/Retry-After per contract |
| Completed | Return the saved status/body/resource reference |
| Same key, different payload | Return 409 Conflict |
| Transient failure | Allow retry per policy with the same key |
| Permanently rejected | Return the saved error or require a new intent per contract |
| Needs reconciliation | Return pending/unknown status and continue reconciliation |

There is no single status code suitable for every API. What matters is that the contract is consistent and clients know whether to retry, poll operation status, or create a new intent.

### 5.2. Returning the Original Result

If the first request created order 1042 and the response was lost, a retried request with the same key should receive a result representing order 1042.

You can store:

- HTTP status.
- Response body or resource ID.
- Content type and select required business headers.
- Completion timestamp.
- API/contract version.

You do not need to store every header. Never store `Authorization`, cookies, access tokens, or secret data in the idempotency response.

If the response contains data whose visibility can change based on access permissions, re-check authorization before returning stored data. Idempotency must never bypass security boundaries.

## 6. Request Fingerprinting: Detecting Key Misuse

A fingerprint represents the business-meaningful content of a request. When the same key is resubmitted, the fingerprint must match the first submission.

Do not hash raw JSON arbitrarily, because two JSON payloads can carry the exact same meaning while differing in field order or formatting. Canonicalize the data first:

- Normalize field ordering.
- Normalize numbers and decimal scale per business rules.
- Normalize default values.
- Normalize enums and unit codes.
- Strip trace IDs, request timestamps, and transport metadata that do not affect business semantics.
- Keep fields that affect the outcome, such as amount, currency, account, and target resource.

For example, if `amount` represents money, use `BigDecimal` with a defined scale/currency; do not convert to `double` before hashing.

### 6.1. Java Fingerprint Example

The example below illustrates computing a fingerprint from normalized fields:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.UUID;

public final class PaymentFingerprint {

    public String calculate(
            String tenantId,
            UUID paymentAttemptId,
            BigDecimal amount,
            String currency) {

        String canonical = String.join("|",
                tenantId,
                paymentAttemptId.toString(),
                amount.stripTrailingZeros().toPlainString(),
                currency.toUpperCase(Locale.ROOT));

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

This is a minimal example. In production, the canonical format should include a version, unambiguous delimiters/encoding, and explicit normalization rules. Use a canonical serializer or a length-prefixed structure if fields can contain delimiters.

Do not include per-submission fields such as trace IDs or request-received timestamps in the fingerprint. Otherwise, a valid retry could be misinterpreted as a different payload.

## 7. Persisting Idempotency Records Durably

Do not use a static map or in-memory cache as the source of truth. Serverless instances can scale to zero, restart, or run concurrently across many instances. A key must be recognized consistently across all workers.

A table can store:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id            VARCHAR(100) NOT NULL,
    operation_name       VARCHAR(100) NOT NULL,
    idempotency_key      VARCHAR(200) NOT NULL,
    request_fingerprint  VARCHAR(128) NOT NULL,
    status               VARCHAR(32) NOT NULL,
    resource_id          VARCHAR(200),
    response_status      INTEGER,
    response_body        JSONB,
    provider_key         VARCHAR(200),
    owner_token          UUID,
    generation           BIGINT NOT NULL DEFAULT 1,
    lease_until          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

This is an illustrative PostgreSQL schema. You can use another database or durable key-value store as long as it supports equivalent conditional writes or transactions.

Key fields:

- Scope and key form the unique identity.
- Fingerprint detects reuse with mismatched payloads.
- Status indicates which step the operation is in.
- Resource/response stores the result for replay.
- Owner token and generation support leasing/fencing.
- Provider key (if the operation calls an external service) remains stable across retries.
- `expires_at` supports retention and cleanup.

Do not store raw requests containing sensitive data if unnecessary. If you must store responses for replay, apply access controls, encryption, retention policies, and data minimization.

## 8. Idempotency Record States

A straightforward state model:

~~~text
NEW
  -> IN_PROGRESS
       -> COMPLETED
       -> RETRYABLE_FAILURE
       -> RECONCILIATION_REQUIRED
       -> REJECTED
~~~

| State | Meaning | Behavior When Same Key Arrives Again |
|---|---|---|
| IN_PROGRESS | A worker owns the operation | Do not execute side effects concurrently; wait or return in-progress status |
| COMPLETED | Operation reached a final outcome | Return the stored result |
| RETRYABLE_FAILURE | Transient error, safe to retry | Reclaim according to policy with the same key |
| RECONCILIATION_REQUIRED | Unclear whether side effect occurred | Reconcile before retrying |
| REJECTED | Request permanently rejected per contract | Return the stored error or require a new intent |

Do not mark `COMPLETED` merely because the handler started running or called a provider. Only mark `COMPLETED` once the business outcome is confirmed and durably persisted.

A deterministic validation error before any side effect can be recorded as `REJECTED`. A timeout after calling a provider should not automatically be marked `RETRYABLE_FAILURE`, because the provider may have already executed the operation.

## 9. Claim Keys Atomically to Prevent Race Conditions

Two Lambda invocations can receive the same message, or two HTTP requests with the same key can arrive nearly simultaneously. If both check "no record exists" and both proceed to create an order, idempotency is broken.

You need an atomic operation:

- A unique constraint on scope + key.
- Conditional insert/update.
- A transaction or compare-and-set.
- A single worker holding a valid lease at any given time.

Claim flow:

~~~mermaid
flowchart TD
    A["Receive request + key"] --> B["Canonicalize and fingerprint"]
    B --> C["Atomic insert / claim"]
    C --> D{"Claimed?"}
    D -->|Yes| E["Execute operation"]
    D -->|No| F["Read existing record"]
    F --> G{"Fingerprint matches?"}
    G -->|No| H["409 Conflict"]
    G -->|Yes| I{"Status"}
    I -->|COMPLETED| J["Replay result"]
    I -->|IN_PROGRESS| K["Wait / 202 / Retry-After"]
    I -->|RETRYABLE| L["Reclaim under lease"]
    I -->|RECONCILIATION| M["Reconcile first"]
~~~

Do not use a "SELECT then INSERT" pattern without a unique constraint or transaction. Two requests can both SELECT and find no record before both perform an INSERT.

### 9.1. Claim Pseudocode

One way to implement this with a database:

1. Start a transaction.
2. Attempt to INSERT a record with status `IN_PROGRESS` and a new owner token.
3. If the insert succeeds, commit the claim.
4. On unique conflict, read the existing record.
5. Compare the fingerprint; if different, return conflict.
6. If `COMPLETED`, return the stored result.
7. If the lease is still valid, report that the operation is in progress.
8. If the lease has expired and the state allows reclaiming, conditionally update the owner/generation.
9. Commit before making a long network call.

The unique constraint is the final line of defense against concurrent requests. Do not rely on a check inside the Java process alone.

## 10. Leasing and Fencing When Workers Terminate

A worker can be terminated after claiming a key. If the record stays `IN_PROGRESS` forever, the operation gets stuck. A lease allows another worker to reclaim it after a timeout.

However, leasing introduces a risk: the old worker might still be running after its lease expires while a new worker has already reclaimed the key.

Use an owner token and generation:

- Each claim generates a new owner token.
- Each reclaim increments the generation.
- When writing the outcome, the worker must update conditionally against the current owner token/generation.
- A stale worker must not overwrite a newer worker's result.

Example conditional update:

~~~sql
UPDATE idempotency_record
SET status = 'COMPLETED',
    response_status = :response_status,
    response_body = CAST(:response_body AS JSONB),
    updated_at = NOW()
WHERE tenant_id = :tenant_id
  AND operation_name = :operation_name
  AND idempotency_key = :key
  AND status = 'IN_PROGRESS'
  AND owner_token = :owner_token
  AND generation = :generation;
~~~

If the updated row count is zero, the worker no longer owns the operation. It should read the current state and must not overwrite it.

Fencing only protects updates to the store that checks the generation. For external providers, you still need a provider idempotency key or reconciliation so the old and new workers do not trigger two side effects.

## 11. Do Not Hold Database Transactions While Calling External APIs

An anti-pattern is opening a transaction, holding a row lock, and then calling a payment provider over the network. If the provider is slow, the transaction holds locks for a long time, connections are exhausted, and the database can bottleneck.

Instead:

1. Use a short transaction to claim the key and create the operation state.
2. Commit.
3. Call the provider outside the transaction using a stable provider key.
4. Use another transaction to persist the provider result and update business/idempotency state.
5. If the process crashes between steps, retries or a reconciler resume from durable state.

If the business row and idempotency record live in the same database, you can commit them in the same transaction to prevent one from completing without the other.

With an external provider, you cannot atomically commit across your database and the provider's system without a distributed transaction protocol supported by both. Design a state machine and reconciliation flow to cover that gap.

## 12. External Side Effects Require Provider Idempotency

Suppose a Java Lambda calls a payment provider:

1. The provider captures the payment.
2. The response is lost due to a network timeout.
3. Lambda throws an exception.
4. The queue redelivers the message.
5. The worker calls capture again.

If the provider supports idempotency keys, send the same provider key on every attempt of the same payment intent. The provider can return the already-created transaction result instead of capturing again.

The provider key should be saved in the idempotency record before the first call. Do not generate a new key on retry.

### 12.1. When the Provider Does Not Support Idempotency

If the provider lacks idempotency keys, use a business reference and a status lookup API if available:

- Send a unique merchant reference for the operation.
- On timeout, query the transaction by reference.
- If it already succeeded, record the outcome and do not call the create operation again.
- If no transaction exists, retry according to policy.
- If the outcome cannot be determined, keep the state `RECONCILIATION_REQUIRED` and route to manual review or a reconciliation job.

You cannot guarantee zero duplicates if the provider neither supports idempotency, nor accepts a unique merchant reference, nor provides a way to look up outcomes.

### 12.2. Provider Idempotency Retention Windows

A provider may retain idempotency keys only for a limited window. If your system replays a DLQ after the provider has forgotten the key, sending the same key again may create a new side effect depending on the provider's contract.

Therefore:

- Check the retention window in the provider's documentation.
- Store the provider transaction/reference ID once the outcome is known.
- Do not blindly replay old operations after the provider key expires.
- Run reconciliation before replaying outside the retention window.
- Retain local idempotency records long enough for retries and recovery.

## 13. Transactional Outbox and Inbox

An operation may need to both update a database and publish an event. If the database commits but publishing fails, the system loses the event. If publishing succeeds but the transaction rolls back, consumers receive an event for data that does not exist.

The transactional outbox solves this by writing business state and the outbox row in the same transaction:

~~~mermaid
flowchart TD
    A["Java command handler"] --> T["Database transaction"]
    T --> B["Update business row"]
    T --> O["Insert outbox event"]
    B --> C["Commit"]
    O --> C
    C --> P["Outbox publisher"]
    P --> Q["Broker"]
    Q --> I["Consumer inbox / idempotency"]
    I --> D["Business effect"]
~~~

The publisher may resend the same outbox event if it is unsure whether a previous send succeeded. Therefore, the event ID must remain stable and consumers need an inbox/deduplication mechanism.

An inbox records the identity of processed events, such as `source + event ID`, alongside the business state or transaction. A unique constraint prevents two consumers from processing the same event identity concurrently.

The outbox guarantees atomicity between updating business database state and recording the intent to publish. It does not by itself guarantee single delivery from the broker; both publisher and consumer still require retry handling and idempotency.

## 14. Event ID Differs from Business Idempotency Key

An event ID identifies a specific event. A business key identifies a specific business intent.

For example:

- A producer creates a CloudEvent with `source` `/orders` and `id` `evt-91`.
- The broker redelivers that exact event multiple times; `source + id` remains the same.
- The consumer uses `source + id` to deduplicate event deliveries.
- The event requests capturing payment for payment attempt `P-17`; the consumer uses operation `capture-payment:P-17` as the business key.
- If the same payment intent is re-emitted under a new event ID, the business key still prevents a second capture.

With CloudEvents, `source + id` is the proper identifier pair for recognizing duplicate deliveries of the same event. However, a new event ID does not by itself prove a new business action; a producer might re-emit the same command under a different ID. Conversely, a single business object can emit multiple distinct valid events.

It is usually best to have both layers:

1. Transport/event deduplication by `source + event ID`.
2. Business idempotency by `operation + business intent ID`.

Do not use timestamps or message receive counts as event identity.

## 15. Designing Keys by Trigger Type

| Trigger | Identity to Keep Stable | Notes |
|---|---|---|
| HTTP API | `Idempotency-Key` of a client intent | Scope by tenant and operation |
| SQS | Message/business operation ID in payload; event ID if present | Standard queues can redeliver |
| SQS FIFO | Message deduplication ID for publishing and business key at consumer | Broker deduplication window does not replace a durable store |
| Pub/Sub | Message/event identity and business operation ID | Redelivery can happen before ack |
| Kafka | Event identity or topic/partition/offset for delivery tracking; business key for effect | Offsets do not represent a business intent across republishes |
| Step Functions | Business operation ID in execution input | Retries/redrives must preserve the ID |
| Scheduled job | Job run ID + item ID | A new scheduled run is a new intent if defined by business rules |

Do not use queue receipt handles, delivery attempt counts, or visibility tokens as business keys. Those values can change across redeliveries.

## 16. Java Service Handling Idempotency

A service can separate responsibilities as follows:

- `IdempotencyStore`: claims, reads state, and updates results.
- `RequestFingerprinter`: canonicalizes and computes fingerprints.
- `BusinessService`: executes business logic.
- `ExternalClient`: calls the provider with a stable provider key.
- `Reconciler`: resolves unknown outcomes.
- Transaction boundary: commits business state and idempotency result together when possible.

Example interfaces:

~~~java
public interface IdempotencyStore {
    ClaimResult claim(
            String tenantId,
            String operation,
            String key,
            String fingerprint);

    void complete(
            Claim claim,
            String resourceId,
            PaymentResult result);

    void markRetryable(Claim claim, String reason);

    void markReconciliationRequired(Claim claim, String reason);

    void markRejected(Claim claim, String reason);
}

public interface PaymentGateway {
    PaymentResult capture(
            PaymentCommand command,
            String providerIdempotencyKey);
}
~~~

`ClaimResult` can represent one of these outcomes:

~~~text
ACQUIRED
ALREADY_COMPLETED
IN_PROGRESS
FINGERPRINT_MISMATCH
RECONCILIATION_REQUIRED
REJECTED
~~~

Orchestration example:

~~~java
public final class IdempotentCaptureService {

    private final IdempotencyStore store;
    private final PaymentGateway gateway;

    public IdempotentCaptureService(
            IdempotencyStore store,
            PaymentGateway gateway) {
        this.store = store;
        this.gateway = gateway;
    }

    public PaymentResult capture(PaymentCommand command) {
        String fingerprint = command.fingerprint();

        ClaimResult result = store.claim(
                command.tenantId(),
                "capture-payment",
                command.idempotencyKey(),
                fingerprint);

        if (result.isFingerprintMismatch()) {
            throw new IdempotencyConflictException(
                    "Key was already used with different request data");
        }

        if (result.isCompleted()) {
            return result.savedPaymentResult();
        }

        if (result.isInProgress()) {
            throw new OperationInProgressException(
                    result.operationReference());
        }

        if (result.requiresReconciliation()) {
            throw new ReconciliationRequiredException(
                    result.operationReference());
        }

        if (result.isRejected()) {
            throw new PreviouslyRejectedOperationException(
                    result.savedError());
        }

        Claim claim = result.claim();

        try {
            PaymentResult payment = gateway.capture(
                    command,
                    claim.providerIdempotencyKey());

            store.complete(
                    claim,
                    payment.paymentId(),
                    payment);

            return payment;
        } catch (OutcomeUnknownException error) {
            store.markReconciliationRequired(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        } catch (RetryablePaymentException error) {
            store.markRetryable(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        } catch (PermanentPaymentException error) {
            store.markRejected(
                    claim,
                    error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

This is an illustrative skeleton; the methods must be backed by transactions/conditional updates and fencing as described earlier. Exception classification must follow the provider's contract. If the provider could have executed the side effect before a timeout, use `OutcomeUnknownException` and reconcile rather than marking a failure that gets retried blindly.

When the store returns `ALREADY_COMPLETED`, return the stored result. When it returns `IN_PROGRESS`, the API can poll or return 202/409 per contract. Do not call the gateway in those branches.

## 17. Transactions for Local Database Effects

If the side effect only updates the same database, you can commit the business update and the idempotency completion in a single transaction.

Example logic:

~~~text
BEGIN

Lock/verify idempotency claim by owner_token + generation
Insert or update order row
Insert outbox event if needed
Update idempotency record to COMPLETED
Save response/resource reference

COMMIT
~~~

If the transaction rolls back, both the business state and idempotency completion roll back. Retries can reclaim according to policy.

If the business update commits but the idempotency record is updated in a separate transaction, the process might crash in between and a retry would not know the side effect already occurred. Put both changes into the same transaction whenever they reside in the same database.

Do not make network calls to a payment provider inside this transaction. External side effects need their own state machine and reconciliation.

## 18. Idempotency in Workflows and Sagas

A Step Functions workflow can retry individual Tasks. The business operation ID should be passed all the way through:

~~~json
{
  "orderId": "order-1042",
  "paymentAttemptId": "payment-attempt-17",
  "operations": {
    "capturePaymentKey": "capture-payment-attempt-17",
    "reserveInventoryKey": "reserve-order-1042"
  }
}
~~~

When a Task retries, Lambda receives the same key. If an execution is relaunched for recovery, the workflow must retrieve the operation ID from the order record or saved input.

Compensation is a distinct business operation and needs its own key. For example:

~~~text
capture-payment:payment-attempt-17
refund-payment:payment-attempt-17
release-inventory:reservation-771
~~~

Do not use the same key for a forward action and its compensation because they have different semantics. Refunds need their own idempotency so retries do not refund twice.

If a Saga triggers compensation after a timeout where the forward action might have succeeded, reconcile the forward action before deciding whether compensation is needed.

## 19. Retention and Key Lifecycle

If you delete idempotency records too early, an old replayed message may be treated as a new intent. If you keep them indefinitely, storage grows and stale data can complicate governance.

Retention should exceed the longest period over which the same intent might be resubmitted:

- Client retry horizon.
- Broker retention and redelivery horizon.
- DLQ retention and expected replay window.
- Workflow duration, retry, and redrive window.
- Reconciliation and manual recovery time.
- Provider idempotency retention.
- Business archival/audit requirements.

Do not set a TTL based solely on normal processing time. An event can be replayed days later once an incident is resolved.

You can purge the response body earlier while retaining a tombstone/key fingerprint/resource reference longer if needed to prevent duplicate side effects. Cleanup rules must avoid deleting `IN_PROGRESS` or `RECONCILIATION_REQUIRED` records.

If keys expire under the API contract, the documentation must state clearly that clients must not retry an old intent past that window without checking status first.

## 20. Security and Privacy

An idempotency key is not an authentication secret, yet it is still metadata that can be linked to an operation. Protect it as a controlled identifier:

- Scope by the authenticated tenant, not a client-declared tenant ID.
- Avoid logging the full key unless needed.
- Do not include PII or payment data in the key.
- Do not return a stored response before checking current authorization.
- Encrypt stored data according to policy.
- Restrict read access to the idempotency table.
- Guard against clients generating unbounded keys to bloat storage.
- Apply rate limits and quotas per principal/tenant.
- Do not let keys become a way to guess resource IDs or bypass access control.

Fingerprints can also leak information if computed from low-entropy data and exposed. Use a hash/HMAC appropriate to your threat model, and never store raw secrets in fingerprint input logs.

## 21. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Generating a new UUID on every retry | Every attempt becomes a new operation | Generate the key once at the business intent boundary |
| Using a payload hash as the key | Two valid intents with identical payloads get merged | Use an operation ID; use fingerprint only to compare payloads |
| No unique constraint | Two workers simultaneously create side effects | Atomic claim and database uniqueness |
| Using a static map | State is lost on scaling/restarts | Shared durable store |
| Deduplicating only by event ID | A new event can repeat the same business command | Add a business idempotency key |
| Using an execution ARN | A new execution does not recognize the old intent | Preserve the business operation ID |
| Marking complete before provider result | Retries are skipped even though the side effect never occurred | Mark complete only after durable confirmation |
| Retrying immediately after an ambiguous timeout | May create duplicate side effects | Reconcile or use a provider key |
| Leasing without fencing | A stale worker overwrites a newer worker | Owner token and generation |
| TTL too short | Old replays create new transactions | Base retention on retry/replay horizons |
| Sharing a key between capture and refund | Two distinct operations collide | Namespace keys by operation |
| Returning stored results without re-authorizing | May leak another tenant's/resource's data | Enforce authorization before replaying responses |

## 22. Test Plan for Idempotency

Test sequential cases, concurrent cases, and crashes at side-effect boundaries.

| Test | Scenario | Expected Outcome |
|---|---|---|
| ID-01 | Same key, same payload sent twice | One business effect; second call replays the result |
| ID-02 | Same key, different payload | Conflict; second side effect does not run |
| ID-03 | Two concurrent requests with the same key | Only one worker acquires the claim |
| ID-04 | Two tenants using the same key string | No conflict when scopes differ |
| ID-05 | Two new intents with identical payloads | Two different keys, two valid operations |
| ID-06 | Worker dies after claim before side effect | Lease/recovery allows continuation |
| ID-07 | Provider succeeds but response times out | Retry/reconcile does not capture a second time |
| ID-08 | Worker dies after provider success before DB update | Stable provider key or reconciliation recovers |
| ID-09 | Lease expires while old worker is still running | Fencing prevents the old worker from overwriting |
| ID-10 | Event redelivery with same source + id | Inbox ignores duplicate |
| ID-11 | New event ID but old business intent | Business key prevents duplicate side effect |
| ID-12 | DLQ replay after a long delay | Check retention and reconcile before replay |
| ID-13 | Expired key | Behavior matches contract; never silently duplicates |
| ID-14 | Callback/compensation invoked twice | Only one compensating business effect |
| ID-15 | Unauthorized caller uses a known key | Cannot view or alter the result |

### 22.1. Testing Real Concurrency

Do not merely mock the store and assert a method was called once. Write integration tests against a real database or test database with equivalent unique constraints and transactions:

1. Launch multiple concurrent requests with the same scope/key.
2. Use a barrier so requests start nearly simultaneously.
3. Verify only one request obtains the claim.
4. Verify only one provider call or business insert is committed.
5. Verify the remaining requests receive `IN_PROGRESS` or the completed result.
6. Re-run after terminating a process mid-flight between steps.

Test across multiple instances/processes to prove the mechanism does not depend on `synchronized` or static locks inside the JVM.

## 23. Process for Designing Idempotency Keys

1. **Identify the business intent.** Is an order placement, a payment attempt, or a refund request one intent?
2. **Choose a stable operation ID.** Generate and persist it before the first attempt.
3. **Define the scope.** Tenant + operation + key.
4. **Separate key and fingerprint.** The key identifies intent; the fingerprint validates request data.
5. **Enforce a unique constraint.** Protect claims against concurrency across instances.
6. **Design the state machine.** `IN_PROGRESS`, `COMPLETED`, `RETRYABLE_FAILURE`, `RECONCILIATION_REQUIRED`, and `REJECTED`.
7. **Use leasing/fencing.** Enable recovery without letting stale workers overwrite newer ones.
8. **Protect external side effects.** Pass a stable provider key or reconciliation reference.
9. **Use transactions/outbox.** Commit business state and idempotency records atomically when possible.
10. **Set retention.** Cover client retries, broker redeliveries, DLQ replays, and workflow recovery.
11. **Check authorization.** Idempotency does not replace access control.
12. **Test crashes and races.** Simulate timeouts before/after side effects and concurrent requests.

Good idempotency keys start with a clear business model. When a key represents a stable intent, a fingerprint catches mismatched reuse, the database claims atomically, and external side effects use provider keys or reconciliation, Java serverless workers can retry safely without creating unintended orders, payments, or reservations.

## 24. Self-Check Questions

- How does idempotency differ from exactly-once delivery?
- Why must the key represent business intent?
- Why should a payload hash not be used as the sole key?
- In what scenario does a new payment attempt need a different key?
- How does the `tenant + operation + key` scope prevent collisions?
- Which fields should a fingerprint canonicalize?
- Why is `SELECT` followed by `INSERT` without a unique constraint unsafe?
- What two problems do leasing and fencing solve?
- Why should you not hold a database transaction while calling a provider?
- What should you do when a provider executed a side effect but the response timed out?
- How do transactional outbox and inbox complement idempotency?
- How does an event ID differ from a business idempotency key?
- Why must Step Functions retries preserve the operation ID?
- Which time horizons should retention of idempotency records be based on?
- How can you test two Lambda instances receiving the same key concurrently?
