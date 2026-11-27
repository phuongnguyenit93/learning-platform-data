# Message ID and Idempotency Key

## 1. Why Can a Message Be Processed Multiple Times?

In an integration system, a broker or adapter may redeliver **the same business event** if an acknowledgment is lost, a consumer crashes, or a retry is triggered. This is common in flows with **at-least-once delivery** semantics.

Suppose a payment service receives a charge request for order `ORD-1001`:

~~~text
10:00:00  Consumer receives PAYMENT_REQUESTED.
10:00:01  Payment API successfully collects the payment.
10:00:02  Consumer crashes before acking the broker.
10:00:05  Broker redelivers the message.
10:00:06  Consumer calls the Payment API again?
~~~

If the consumer treats every delivery as a new command, the customer may be charged twice. The **Idempotent Receiver** pattern helps the consumer recognize that an operation **has already been executed or already has an authoritative outcome**, so redelivery does not duplicate the business impact.

The tricky part is: **a framework Message ID is not necessarily an idempotency key suitable for the business domain.** A message may be recreated as it passes through a Transformer, adapter, or during a retry, while the payment operation remains a single logical operation.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant R as Receiver
    participant L as Operation Ledger
    participant P as Payment Service
    B->>R: Delivery #1, operationId=PAY-1001
    R->>L: Find operation PAY-1001
    L-->>R: Not completed
    R->>P: Charge, idempotency-key=PAY-1001
    P-->>R: SUCCESS
    R->>L: Record COMPLETED + receipt
    Note over R,B: Ack lost / consumer crash
    B->>R: Delivery #2, operationId=PAY-1001
    R->>L: Find operation PAY-1001
    L-->>R: COMPLETED + receipt
    Note over R: Do not charge a second time
~~~

The diagram illustrates the **desired outcome**, and does not assert that a database ledger and a Payment API always update atomically. Handling crashes and **UNKNOWN** outcomes will be explained separately.

This lesson belongs to the **Idempotent receiver** chapter of the `SPRING_INTEGRATION_PATTERN` module: learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, testing, and observing processing branches.

### Lesson Objectives

After completing this lesson, you will be able to:

1. Distinguish **Spring Message ID**, **event ID**, **delivery ID**, **correlation ID**, **trace ID**, and **business idempotency key**.
2. Choose the right idempotency scope by **tenant, consumer/operation, business intent, and version**.
3. Understand why a message with a new ID can still be a duplicate and two messages referencing the same business entity may not be duplicates.
4. Design an idempotent handler with a **durable inbox/operation ledger**, states, fingerprints, and receipts.
5. Know the limitations of `IdempotentReceiverInterceptor`, `MetadataStoreSelector`, and `ConcurrentMetadataStore` when handling side effects.
6. Identify how retries, crashes, duplicates, concurrent consumers, timeouts, and late replies need to be tested.
7. Combine Idempotent Receiver with other EIPs without losing metadata or masking business errors.

## 2. Message ID Is Not Always an Idempotency Key

### 2.1. Types of IDs in an Integration Flow

| Identifier | What Does It Identify? | What Is It Used For? |
|---|---|---|
| **Spring `MessageHeaders.ID`** | A specific Spring `Message<?>` instance during processing. | Trace/debug identity of a message within the framework. |
| **Business `eventId`** | A single emission of a business event at the source. | Deduplicating an event delivered multiple times. |
| **Business `operationId`** | A requested business action, e.g., charging an order. | Idempotency of a side effect or API command. |
| **Broker record coordinate** | Record position in a topic/partition/offset or equivalent envelope. | Investigating transport, consumer offsets, and redelivery. |
| **Delivery/attempt ID** | A single delivery or attempt. | Debugging retries, latency, failure attempts. |
| **`correlationId`** | A group of related messages or a request–reply conversation. | Splitter/Aggregator/Gateway correlation. |
| **`traceId`/`spanId`** | Distributed observability flow. | Tracing across services and threads. |
| **`claimId`** | Reference to a payload in a Claim Check store. | Restoring data; does not necessarily protect side effects. |
| **`sequenceNumber`** | Position in a message sequence. | Resequencer/Aggregator sequence semantics. |

**No single ID automatically replaces all other IDs.** You must determine “**which operation must take effect only once**” before choosing a key.

### 2.2. Message ID Can Change Even When Business Content Does Not

A new message built by `MessageBuilder` typically gets a framework-assigned ID:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> first =
        MessageBuilder.withPayload("PAY-ORD-1001").build();

Message<String> rebuilt =
        MessageBuilder.withPayload(first.getPayload()).build();

// A new message normally gets a new MessageHeaders.ID.
// Yet the business operation is still PAY-ORD-1001.
~~~

Even when payloads are identical, you should not expect `first.getHeaders().getId()` and `rebuilt.getHeaders().getId()` to always match. The framework, adapters, and how messages are constructed determine which metadata is preserved or regenerated. If you deduplicate solely by this ID, a **business duplicate** can slip through.

### 2.3. A Message ID Is Also Not Proof That Payment Has Not Run

For example, a broker redelivery might keep the envelope ID or reconstruct a Spring message with a new ID. Either way, a handler must check the status of **operationId=PAY-ORD-1001** at the component responsible for the side effect. Comparing Message IDs **cannot confirm whether an external payment has committed**.

### 2.4. Same orderId Does Not Mean Same Operation

~~~text
Order ORD-1001:
  CHARGE initial amount=100000
  REFUND partial amount=20000
  CHARGE adjustment amount=5000
~~~

If the dedup key is only `orderId`, the valid REFUND operation could be mistaken for a duplicate of the initial CHARGE. The key should reflect the **operation type and execution instance**:

~~~text
TENANT-A / PAYMENTS / CHARGE-ORD-1001-V1
TENANT-A / PAYMENTS / REFUND-ORD-1001-R1
TENANT-A / PAYMENTS / CHARGE-ORD-1001-ADJUST-1
~~~

These are **example values**, not a mandatory format. In a real system, the operation ID must come from an authoritative source with a unique issuance rule, rather than arbitrary string concatenation from user-spoofable fields.

## 3. The Most Important Question: “Same” at What Level?

### 3.1. Event Deduplication

An `OrderPaid(eventId=EVT-23)` event is delivered three times due to broker retries. A consumer updating a projection may need to apply **EVT-23 only once**.

~~~text
eventId=EVT-23, delivery#1
eventId=EVT-23, delivery#2
eventId=EVT-23, delivery#3

idempotency identity = (consumerName, tenantId, eventId)
~~~

If two different consumers must both process `EVT-23` — for example, BillingProjection and NotificationService — Projection having processed it must not prevent Notification from receiving the valid event. Therefore, the key needs to be **scoped by consumer** when side effects differ.

### 3.2. Command/Operation Idempotency

A `ChargePayment` API may be retried with a fixed operation ID when an HTTP timeout occurs:

~~~text
operationId=CHARGE-456, attempt=1 -> timeout
operationId=CHARGE-456, attempt=2 -> same business action
~~~

Here the business operation key matters more than the transport message's event ID. If the caller sends the same operationId with a **different amount**, that may be a **key conflict**, not a safe duplicate.

### 3.3. State-Based Idempotency

Some handlers can be naturally idempotent via state:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = ? AND status = 'PENDING';
~~~

The statement above may not apply a second time once the condition has changed. However, it **does not automatically protect** other side effects such as sending emails, calling payment APIs, or writing audit logs. And if the `PAID` status can transition away and return to `PENDING`, a business version/transition ID is needed to avoid replaying old commands.

### 3.4. Must the Result Stay Identical?

**An idempotent side effect** means calling the same operation again produces no new business impact. An API may also choose to **return the old receipt** so the caller does not see conflicting results.

Distinguish between:

- **At-most-one side effect:** do not charge twice.
- **Stable response:** retries receive the same receipt/operation state.
- **Deterministic payload:** the entire response is byte-for-byte identical.

These three requirements are not always equivalent. Observed timestamps may differ across retries, while the **idempotency key and final business outcome** must remain consistent per the contract.

## 4. Criteria for Choosing a Good Idempotency Key

### 4.1. Desired Properties

A good key should:

1. **Be stable across deliveries/retries of the same operation.**
2. **Distinguish different valid operations** on the same business entity.
3. **Have a clear scope** by tenant and consumer/operation.
4. **Be issued by an authoritative source** or verifiable at ingress.
5. **Not depend on receive timestamps or newly generated Spring Message IDs.**
6. **Be retainable longer than the retry/redelivery horizon** per retention policy.
7. **Provide a way to detect the same key with a different payload** via fingerprinting or contract validation.
8. **Not expose unnecessary sensitive data** when appearing in logs/headers.

### 4.2. Good Keys vs. Risky Keys

| Key | Assessment | Reason |
|---|---|---|
| `tenantId + service + operationId` | Good if components come from trusted sources. | Separates tenant, operation, and consumer. |
| `tenantId + eventId + consumerId` | Good for event receivers. | One event processed once per consumer. |
| `orderId` | Usually insufficient. | One order has multiple operations/versions. |
| `payload.toString()` | Unsafe. | Unstable formatting, no canonicalization guarantee. |
| `MessageHeaders.ID` | Insufficient for business effects. | May change when a message is reconstructed. |
| `traceId` | Unsuitable. | A single trace may contain multiple operations. |
| `correlationId` | Not by default. | May group multiple Splitter child messages. |
| `sequenceNumber` | Wrong on its own. | Same sequence numbers across many groups. |
| `System.currentTimeMillis()` on receipt | Wrong. | Every retry creates a new key. |
| `broker offset` | Only useful in specific contexts. | Unstable if an event is republished as a new record. |

### 4.3. Composite Keys Should Be Structured, Not Arbitrarily Concatenated

In a database, prefer a composite unique key:

~~~sql
UNIQUE (tenant_id, consumer_name, operation_id)
~~~

A string like `tenant + ":" + operation` can collide if components contain the delimiter. If you must store in a `ConcurrentMetadataStore` taking a String key, use an **unambiguous encoding** or encode validated components:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

final class IdempotencyKeys {
    private static String segment(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("EMPTY_ID_COMPONENT");
        }
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                        value.getBytes(StandardCharsets.UTF_8));
    }

    static String forOperation(
            String tenantId,
            String consumerName,
            String operationId) {
        return segment(tenantId) + "."
                + segment(consumerName) + "."
                + segment(operationId);
    }
}
~~~

This is **canonical encoding for combining already-trusted strings**, not a digital signature or secret encryption. URL-safe Base64 only separates components unambiguously; it **does not hide PII and does not prevent spoofing**. If tokens/keys cross a trust boundary, appropriate authentication, authorization, and integrity protection are required.

### 4.4. Versioned Keys and Consumer Scope

A system may change handler logic:

~~~text
Projection v1 consumes EVT-23
Projection v2 replays EVT-23 to rebuild state
~~~

If using the same inbox key as v1, v2 might block the entire replay. Conversely, if a version is accidentally added to the key of a **payment charge**, deploying v2 could issue a new charge for an old operation. Therefore:

- **Projection rebuild:** may use an approved `consumerName/version` or a new namespace.
- **Business side effects:** keep the same operation key across deployments, unless it is genuinely a new operation.
- **Key migration:** have a plan to read old state, rather than changing the namespace and treating every message as new.

### 4.5. Payload Fingerprint to Detect Misuse of Keys

For example, with the same `CHARGE-456`:

~~~text
Attempt 1: amountVnd=100000, currency=VND
Attempt 2: amountVnd=900000, currency=VND
~~~

The second attempt must not blindly receive the “old SUCCESS”. Store a fingerprint of the **business fields defining the operation**, then reject or investigate when the key matches but the fingerprint differs.

Do not compute the fingerprint using Java's `Object.hashCode()`, as it is not guaranteed to be stable across processes/versions. You need canonical serialization with schema version, currency, amount representation, normalization, and security policies; `SHA-256` of canonicalized data can be a technical option, though hashing **does not replace authorization**.

## 5. Java Model: Binding the Idempotency Key to a Business Operation

Examples target **Java 17+, Spring Boot 3.x, and Spring Integration 6.x**. Types are assumed to reside in the same package; in a real project, place `public` types into appropriate separate files. The payment business rules here are **purely simulated**, not a real payment gateway integration.

### 5.1. Payment Command with Explicit ID

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record ChargeCommand(
        String tenantId,
        String operationId,
        String orderId,
        BigDecimal amountVnd) {

    ChargeCommand {
        if (tenantId == null || tenantId.isBlank()
                || operationId == null || operationId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException(
                    "INVALID_CHARGE_COMMAND");
        }
    }
}

record OperationKey(
        String tenantId,
        String consumerName,
        String operationId) {
    OperationKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(consumerName);
        Objects.requireNonNull(operationId);
    }
}

record ChargeReceipt(
        String operationId,
        String paymentReference,
        String status) {}
~~~

Each field plays a distinct role:

- `tenantId` prevents mixing data across tenants.
- `operationId` stays fixed across retries of **the same charge operation**.
- `orderId` identifies the order, though one order may have multiple valid charges/refunds.
- `amountVnd` is business data that must be checked to detect **same key, different payload**.
- `consumerName` is the receiver's scope, which in this example can be fixed to `PAYMENT_CHARGE`.

### 5.2. Purposeful Fingerprint

For the illustrative VND currency model, we use a canonical tuple of `orderId` and `amountVnd`. A production system needs canonical schema versioning and proper currency/scale validation per business rules; the demo below **does not use cryptographic hashing**.

~~~java
final class ChargeFingerprint {
    static String of(ChargeCommand command) {
        return IdempotencyKeys.forOperation(
                command.tenantId(),
                command.orderId(),
                command.amountVnd()
                        .stripTrailingZeros()
                        .toPlainString());
    }
}
~~~

Deriving a fingerprint from business data enables:

~~~text
same operationId + same fingerprint
  -> valid duplicate / retry

same operationId + different fingerprint
  -> OPERATION_CONFLICT
~~~

**Do not assume every field belongs in the fingerprint.** For instance, request timestamps, tracing metadata, or `deliveryAttempt` may legitimately vary across retries. Conversely, amount/currency/customer/merchant scope are critical fields for payments. Field-selection policies must be explicit and versioned.

### 5.3. A Fake Receiver Retaining Receipts for Duplicates

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

record StoredChargeOutcome(
        String fingerprint,
        ChargeReceipt receipt) {}

final class InMemoryIdempotentChargeReceiver {
    private static final String CONSUMER = "PAYMENT_CHARGE";

    private final ConcurrentMap<OperationKey, StoredChargeOutcome> done =
            new ConcurrentHashMap<>();

    private final AtomicInteger appliedCharges =
            new AtomicInteger();

    ChargeReceipt handle(ChargeCommand command) {
        OperationKey key = new OperationKey(
                command.tenantId(), CONSUMER, command.operationId());
        String fingerprint = ChargeFingerprint.of(command);

        StoredChargeOutcome result = done.compute(key, (ignored, old) -> {
            if (old != null) {
                if (!old.fingerprint().equals(fingerprint)) {
                    throw new IllegalStateException(
                            "OPERATION_CONFLICT");
                }
                return old;
            }

            // Fake in-memory effect: no external HTTP/DB calls.
            int number = appliedCharges.incrementAndGet();
            ChargeReceipt receipt = new ChargeReceipt(
                    command.operationId(),
                    "SIMULATED-PAYMENT-" + number,
                    "SUCCESS");
            return new StoredChargeOutcome(fingerprint, receipt);
        });

        return result.receipt();
    }

    int appliedCount() {
        return appliedCharges.get();
    }
}
~~~

**Why use `ConcurrentHashMap.compute`?** In the fake, looking up the key, comparing the fingerprint, and generating the receipt are serialized per key within the same JVM; concurrent threads with the same key will not create two separate successful entries.

**Why must you never copy this verbatim for a real Payment API?**

- The `compute` mapping function is not a transaction with an external payment gateway.
- If the JVM crashes, both the map and receipts are lost.
- A remote call may commit and then time out; the map would not know the outcome.
- Multiple JVMs do not share a single map.
- A slow `compute` call can lock/block other operations in the same bucket of the data structure.

For real side effects, use a **durable operation ledger**, locking/unique constraints, and **idempotency at the system producing the side effect**, or proper reconciliation. `compute` here is strictly a learning fixture to illustrate key structure and duplicate behavior.

### 5.4. Comparing with Deduplication by Spring Message ID

Suppose a consumer uses:

~~~java
String seenKey = message.getHeaders().getId().toString();
~~~

If a Transformer constructs another message that still carries `operationId=PAY-1001`, `seenKey` may differ so the receiver fails to recognize the duplicate. Instead:

~~~java
ChargeCommand payload = (ChargeCommand) message.getPayload();
OperationKey key = new OperationKey(
        payload.tenantId(),
        "PAYMENT_CHARGE",
        payload.operationId());
~~~

That is a **business operation identity**, independent of the Spring message's instance ID.

## 6. JUnit 5 Tests for Idempotency Keys

### 6.1. Same Operation, Multiple Deliveries: Only One Fake Charge

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IdempotentChargeSuccessTest {

    @Test
    void sameOperationReturnsOriginalReceipt() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        ChargeCommand command = new ChargeCommand(
                "TENANT-A",
                "CHARGE-1001",
                "ORD-1001",
                new BigDecimal("100000"));

        ChargeReceipt first = receiver.handle(command);
        ChargeReceipt second = receiver.handle(command);
        ChargeReceipt third = receiver.handle(command);

        assertEquals(first, second);
        assertEquals(first, third);
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

The test verifies that the fake returns the old receipt when the same operation is delivered three times; it **does not** prove that an external payment provider provides exactly-once execution.

### 6.2. Same Order with Two Different Operations

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class DifferentOperationTest {
    @Test
    void separateOperationsOnSameOrderAreNotDeduplicated() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        ChargeCommand initial = new ChargeCommand(
                "TENANT-A", "CHARGE-INIT", "ORD-1",
                new BigDecimal("100000"));
        ChargeCommand adjustment = new ChargeCommand(
                "TENANT-A", "CHARGE-ADJUST", "ORD-1",
                new BigDecimal("5000"));

        ChargeReceipt a = receiver.handle(initial);
        ChargeReceipt b = receiver.handle(adjustment);

        assertNotEquals(a.paymentReference(), b.paymentReference());
        assertEquals(2, receiver.appliedCount());
    }
}
~~~

If deduplicating solely by `orderId`, this test would fail because the adjustment operation would be wrongly skipped.

### 6.3. Same Operation ID with Different Amount Must Conflict

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OperationConflictTest {
    @Test
    void sameKeyWithDifferentPayloadIsNotSafeDuplicate() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        receiver.handle(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));

        IllegalStateException error = assertThrows(
                IllegalStateException.class, () ->
                        receiver.handle(new ChargeCommand(
                                "TENANT-A", "CHARGE-1", "ORD-1",
                                new BigDecimal("900000"))));

        assertEquals("OPERATION_CONFLICT", error.getMessage());
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

This error differs from a valid duplicate. It must not be handled by returning the old receipt regardless of the new amount, nor by automatically generating a new operation ID if the caller is not authorized to create a new charge.

### 6.4. Two Tenants Using the Same Local Operation ID

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TenantIsolationTest {
    @Test
    void sameOperationLabelAcrossTenantsHasIndependentScope() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        receiver.handle(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));
        receiver.handle(new ChargeCommand(
                "TENANT-B", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));

        assertEquals(2, receiver.appliedCount());
    }
}
~~~

A key missing the tenant could allow tenant B's valid request to be blocked by tenant A's state. Conversely, adding the tenant to the key does not replace **actual tenant authorization**; a client must not be able to arbitrarily pick a tenant ID to access another's records.

### 6.5. Two Threads Receiving the Same Operation Concurrently

~~~java
import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ConcurrentDuplicateTest {
    @Test
    void twoThreadsSeeSameFakeReceipt() throws Exception {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<ChargeReceipt> a = pool.submit(() -> {
                start.await();
                return receiver.handle(command);
            });
            Future<ChargeReceipt> b = pool.submit(() -> {
                start.await();
                return receiver.handle(command);
            });
            start.countDown();

            assertEquals(a.get(), b.get());
            assertEquals(1, receiver.appliedCount());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

A single-JVM concurrency test helps uncover races in the fake. Across multiple pods/instances, you need **integration tests** sharing a persistent ledger/remote idempotency boundary, rather than trusting `ConcurrentHashMap` alone.

## 7. Why Is a “Message Seen” Table Not Enough for Safe Processing?

### 7.1. Recording “SEEN” Before Doing Business Work

A naive receiver might do:

~~~text
if seenStore.putIfAbsent(key, "SEEN") == null:
    chargePayment()
else:
    skip()
~~~

Suppose:

~~~text
T1  SEEN record is written successfully.
T2  Worker crashes before calling Payment.
T3  Broker redelivers the same operation.
T4  Receiver sees SEEN and skips.
~~~

Result: **no charge occurs**, yet the duplicate is skipped. This is an **at-most-once attempt** failure mode, insufficient when processing requires a clear final outcome.

### 7.2. Recording “SEEN” After Doing Business Work

Reverse the order:

~~~text
T1  Payment charge SUCCEEDS.
T2  Worker crashes before recording SEEN.
T3  Broker redelivers.
T4  Receiver does not find key, calls Payment a second time.
~~~

Result: **risk of double charging**. Simply putting the check **before** or **after** does not by itself solve crashes occurring between two independent operations.

### 7.3. Three State Groups That Must Not Be Confused

| State | Meaning | Action When a Duplicate Arrives |
|---|---|---|
| **COMPLETED** | Business outcome has been confirmed and authoritatively stored. | Return the old receipt or acknowledge/skip per contract. |
| **IN_PROGRESS** | An attempt is currently executing or holding a lease. | Wait, return PENDING, or coordinate retry; do not blindly start a new side effect. |
| **UNKNOWN** | Side effect may have committed, but the receipt was lost. | Reconcile with the authoritative source before retrying. |

Other states may exist:

- `RECEIVED`: message entered the inbox but has not started.
- `FAILED_RETRYABLE`: incomplete, can be retried per policy.
- `FAILED_FINAL`: terminal error outcome, do not automatically retry.
- `REJECTED_CONFLICT`: same key, different fingerprint.
- `CANCELLED`: cancelled by authority/policy; do not automatically reopen on redelivery.

**A single `SEEN` string lacks the semantics** needed to handle all of these cases.

### 7.4. Reference State Machine

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> IN_PROGRESS: acquire operation
    IN_PROGRESS --> COMPLETED: commit confirmed
    IN_PROGRESS --> FAILED_RETRYABLE: known transient failure
    FAILED_RETRYABLE --> IN_PROGRESS: authorized retry
    IN_PROGRESS --> UNKNOWN: outcome uncertain
    UNKNOWN --> COMPLETED: reconciled committed
    UNKNOWN --> FAILED_RETRYABLE: reconciled not committed
    RECEIVED --> REJECTED_CONFLICT: fingerprint mismatch
    COMPLETED --> [*]
    REJECTED_CONFLICT --> [*]
~~~

This is a **business/orchestration model**, not a state machine automatically generated by Spring Integration from a single annotation.

## 8. Durable Inbox/Operation Ledger

### 8.1. Minimal Schema with a Unique Key

PostgreSQL-style SQL example expressing the contract:

~~~sql
CREATE TABLE processed_operations (
    tenant_id          VARCHAR(120) NOT NULL,
    consumer_name      VARCHAR(120) NOT NULL,
    operation_id       VARCHAR(200) NOT NULL,
    payload_fingerprint VARCHAR(200) NOT NULL,
    status             VARCHAR(40) NOT NULL,
    receipt_json       TEXT,
    created_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, consumer_name, operation_id)
);
~~~

**The primary key** enforces uniqueness of the business operation within the chosen scope. However, it **does not automatically protect** remote HTTP side effects when the ledger and the payment system are two separate systems.

For auditing and recovery, you may also need:

- `attempt_count`, `last_error_code`, `next_retry_at`.
- `lease_owner`, `lease_until`, `fencing_version`.
- `external_payment_reference`.
- `result_version`, `schema_version`.
- `expires_at`/retention metadata.
- Store only approved fingerprints/receipts; do not arbitrarily store personal data.

### 8.2. Same DB Transaction: Apply Business Update + Persist Receipt

If the business side effect **also resides in the same database transaction**, you can perform:

~~~text
BEGIN TRANSACTION

1. INSERT inbox key (tenant, consumer, operation)
   ON CONFLICT DO NOTHING
2. SELECT operation row FOR UPDATE
3. If COMPLETED:
     - matching fingerprint -> return stored receipt
     - different fingerprint -> OPERATION_CONFLICT
4. If eligible to process:
     - perform business mutation in the same DB
     - store receipt and status=COMPLETED
5. COMMIT
~~~

PostgreSQL syntax example:

~~~sql
INSERT INTO processed_operations (
    tenant_id, consumer_name, operation_id,
    payload_fingerprint, status, created_at, updated_at
)
VALUES (
    :tenant, :consumer, :operation,
    :fingerprint, 'RECEIVED', CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, consumer_name, operation_id)
DO NOTHING;

SELECT status, payload_fingerprint, receipt_json
FROM processed_operations
WHERE tenant_id = :tenant
  AND consumer_name = :consumer
  AND operation_id = :operation
FOR UPDATE;
~~~

**This is an SQL skeleton**, not a complete ready-to-run transaction. You must handle row locking, isolation levels, unique constraint errors, deadlocks, response serialization, and access permissions. Never call a remote Payment API inside the same DB transaction and assume the payment rolled back if the DB rolls back.

### 8.3. When the Side Effect Is Outside the Database

~~~mermaid
flowchart TD
    M[Command message] --> L[(Durable Operation Ledger)]
    L -->|COMPLETED| R[Return stored receipt]
    L -->|RECEIVED / safe to start| P[External Payment API]
    P -->|Success receipt| C[Persist COMPLETED]
    P -->|Timeout / unknown| U[Mark UNKNOWN]
    U --> Q[Query/reconcile external status]
    Q -->|Already committed| C
    Q -->|Definitely not committed| RET[Retry with same idempotency key]
    RET --> P
~~~

Three points to protect:

1. **Same operation key sent to the external API** if the provider supports idempotency.
2. **Never blindly retry on an UNKNOWN outcome**; query status/reconcile before calling again.
3. **Use a durable ledger and concurrency control** so multiple consumers cannot launch two independent requests for the same key.

If the external service supports neither idempotency nor status queries, the system cannot promise exactly-once execution with a few lines of Spring Integration config. You must design business compensation/manual reconciliation or change the contract.

### 8.4. What Scope Does “Exactly-Once” Cover?

A broker may provide certain transactional mechanisms for **broker records**; a database has unique keys; a payment service has an idempotency header. But “exactly-once” must specify **across which boundary**:

| Scope | What Can Be Guaranteed? |
|---|---|
| Inbox insert in a single DB | Unique operation record by primary key. |
| Same DB transaction | Business mutation + receipt can be atomic if both are in the same transaction. |
| Broker consume → broker publish | May have transaction/offset semantics depending on broker/config. |
| Broker → remote HTTP payment | Not automatically atomic; requires remote idempotency/reconciliation. |
| Payment → email notification | May need outbox, duplicate-safe notifications, workflow state. |

**Idempotent Receiver does not turn an entire network of services into one distributed transaction.** It is one of the mechanisms that enables controlled handling of redeliveries.

## 9. Failure Scenarios Requiring Separate Explanation

### 9.1. Ack Lost After Commit

~~~text
Consume event E1
  -> commit business change + receipt
  -> ack broker (ack lost)

Broker redelivers E1
  -> receiver reads COMPLETED
  -> return previous receipt or skip expected side effect
  -> acknowledge duplicate
~~~

This is a scenario Idempotent Receiver handles well **if a durable record** is persisted prior to acking per the contract.

### 9.2. Crash While IN_PROGRESS

~~~text
Receiver A:
  -> claim operation key
  -> status IN_PROGRESS
  -> crash

Receiver B:
  -> sees IN_PROGRESS
~~~

Receiver B must not wait forever, nor automatically assume the operation failed. Lease deadlines, heartbeats, and fencing can be used; when a lease expires, **the possibility that worker A is still alive or the side effect already committed** must be resolved against the target system.

### 9.3. Two Concurrent Workers

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant L as Ledger
    participant X as External API
    A->>L: Claim operation OP-1
    B->>L: Claim operation OP-1
    L-->>A: Lease/fence=10
    L-->>B: Already IN_PROGRESS
    A->>X: Request idempotencyKey=OP-1
    X-->>A: SUCCESS
    A->>L: Commit COMPLETED with fence=10
    Note over B: Do not create a new business operation
~~~

This diagram shows the **desired contract**. Returning a lease/fence from the ledger must be implemented using properly consistent transactions/CAS, not an uncontrolled `SELECT` followed by `UPDATE`.

### 9.4. Duplicate Key with Conflicting Payload

If an existing receipt has:

~~~text
operationId=OP-1
fingerprint=F1
status=COMPLETED
~~~

and a new message has `operationId=OP-1` but fingerprint `F2`, do not return receipt F1 as a valid duplicate or silently create a new operation. The outcome should be **OPERATION_CONFLICT**, with auditing and investigation if payments/tenants are involved.

### 9.5. Late Reply from an Old Attempt

For instance, attempt 1 times out, attempt 2 starts, and then attempt 1's response arrives late. If the ledger receives both:

- Do not let an old `FAILED_RETRYABLE` status overwrite `COMPLETED`.
- Use version/fencing or state transition guards.
- Distinguish **attempt ID** (changes per attempt) from **operation ID** (stays fixed).
- If two external references appear for the same key, reconcile rather than arbitrarily picking the latest result.

### 9.6. Deleting the Dedupe Record Too Early

~~~text
Idempotency record TTL = 5 minutes
Broker redelivery / DLQ replay horizon = 24 hours
~~~

A duplicate arriving after 2 hours may not find the key and be treated as new. Retention must match the **horizon over which the same operation can be replayed**, along with security/data requirements. If tombstones must outlive the original payload, separate minimal metadata from sensitive data.

## 10. Idempotent Receiver in Spring Integration

### 10.1. Two Common Integration Approaches

With Spring Integration, the pattern can be implemented at two levels:

1. **At the message handler/service:** the handler queries the durable ledger, classifies duplicates/conflicts, and either returns the old receipt or executes the operation.
2. **At the endpoint advice:** use `IdempotentReceiverInterceptor` combined with `MessageSelector`/`MetadataStoreSelector` to detect messages with previously seen keys, then mark, discard, or handle according to configuration.

Approach 2 is very useful for **filtering/flagging duplicates at the endpoint**, but **does not automatically replace** a business ledger and external idempotency when handling payments, writing orders, or triggering high-risk side effects.

### 10.2. Java DSL Flow with Business-Key Receiver

Here is a self-contained example using the fake receiver in `Spring Integration Java DSL`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface ChargeGateway {
    @Gateway(
            requestChannel = "payment.command.input",
            replyTimeout = 5000)
    ChargeReceipt charge(ChargeCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class IdempotentReceiverFlowConfiguration {

    @Bean(name = "payment.command.input")
    MessageChannel paymentCommandInput() {
        return new DirectChannel();
    }

    @Bean
    InMemoryIdempotentChargeReceiver chargeReceiver() {
        return new InMemoryIdempotentChargeReceiver();
    }

    @Bean
    IntegrationFlow chargeFlow(
            InMemoryIdempotentChargeReceiver receiver) {
        return IntegrationFlow.from("payment.command.input")
                .handle(ChargeCommand.class,
                        (command, headers) -> receiver.handle(command))
                .get();
    }
}
~~~

This flow creates a request–reply handler that accepts `ChargeCommand` and returns `ChargeReceipt`. Duplicate handling resides **inside the service**, based on `tenantId + consumerName + operationId`, rather than `MessageHeaders.ID`.

**Demo limitation:** `InMemoryIdempotentChargeReceiver` is a fake; restarting the Spring context loses the map, and there are no real external side effects. For production, replace the handler with a service backed by a **durable ledger**, operation idempotency, and appropriate transactions/reconciliation.

### 10.3. `IdempotentReceiverInterceptor` and `MetadataStoreSelector`

Spring Integration provides an **Idempotent Receiver advice**. A common setup uses a selector reading the **business key** to check against a metadata store. Diagram:

~~~mermaid
flowchart LR
    I[Message<ChargeCommand>] --> A[Idempotent Receiver Advice]
    A --> K["Key = tenant/consumer/operation"]
    K --> S[(Metadata Store)]
    S -->|New key| H[Target Handler]
    S -->|Key already exists| D["Duplicate handling per configuration"]
~~~

Minimal concept:

~~~java
// Illustrative code showing how to wire a selector into the advice.
// Verify constructor/DSL options against your Spring Integration version
// and test actual duplicate behavior.

import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;

ConcurrentMetadataStore seenStore =
        new SimpleMetadataStore();

MessageSelector selector = message -> {
    ChargeCommand command =
            (ChargeCommand) message.getPayload();

    String key = IdempotencyKeys.forOperation(
            command.tenantId(),
            "PAYMENT_CHARGE",
            command.operationId());

    // null means putIfAbsent succeeded in the fake store.
    return seenStore.putIfAbsent(key, "SEEN") == null;
};

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
~~~

With current dependencies, you can also look at **`MetadataStoreSelector`**, which coordinates message selection with a metadata store. `ConcurrentMetadataStore` can perform atomic key check-and-set operations **within the guarantees of the store's implementation**.

**Three important warnings:**

- **The advice may mark duplicates with a header** such as `duplicateMessage` or route to a discard/error path depending on version and configuration. Do not assume all duplicates are blocked before the handler by default: verify both default behavior and actual configuration.
- `putIfAbsent(key, "SEEN")` marks **before** business work. If the handler fails, a retry with the same key may be treated as a duplicate even though the side effect **did not succeed**. You need a state/recovery policy or should restrict this advice to use cases genuinely accepting at-most-once admission.
- `SimpleMetadataStore` is in-memory and does not replace a durable ledger. A single `SEEN` metadata key is insufficient to return receipts, verify fingerprints, or reconcile remote payments.

**Do not attach the advice above alongside a durable business ledger and assume both share the same transaction.** If you need the advice to observe duplicates, explicitly define whether duplicate messages are marked, skipped, or routed to a branch, and how that affects Gateway replies.

### 10.4. Difference Between a Duplicate Header and a Business Outcome

A message may be **marked**:

~~~text
headers.duplicateMessage = true
payload.operationId = CHARGE-1001
~~~

Yet the receiver still needs to know:

- Is `CHARGE-1001` already **COMPLETED** with a receipt?
- Is the operation still **IN_PROGRESS** or has its lease expired?
- Does the payload match the prior request or is there a conflict?
- Is the sender authorized to view the stored receipt?
- Does the client expect **a reply** or can the message simply be dropped?

If the request arrives via `MessagingGateway`, discarding the duplicate **without returning a receipt** can cause the caller to time out, even though the prior operation succeeded. When the API contract requires a stable result, handling business idempotency **inside the handler** is usually clearer than silent dropping.

### 10.5. Header-Based Key or Payload-Based Key?

Two ways to extract the key:

~~~java
// Header supplied by a trusted ingress adapter:
String fromHeader = (String)
        message.getHeaders().get("idempotencyKey");

// Business payload:
ChargeCommand command =
        (ChargeCommand) message.getPayload();
String fromPayload = IdempotencyKeys.forOperation(
        command.tenantId(),
        "PAYMENT_CHARGE",
        command.operationId());
~~~

**Which header can be trusted?** If external callers can set the `idempotencyKey` header themselves, the adapter must check permissions and bind it to the tenant/operation; never use a raw header to bypass validation or retrieve another operation's receipt. If the payload comes from a sufficiently trusted source, building the key server-side can be clearer.

### 10.6. Misplaced Endpoint Advice Can Wrongly Block Retries

~~~text
Source -> Filter -> Transformer -> Payment Handler

Idempotent advice before Filter:
  SEEN is recorded even if Filter rejects the message.

Idempotent advice on Payment Handler:
  Only records that the message reached the target handler.
  Still requires recovery if the handler fails after marking.
~~~

Do not just ask “where is it quickest to place the interceptor?”. Define **what milestone counts as processed**, and **whether that record lives in the same transaction as the side effect being protected**.

## 11. Spring Integration Integration Tests

### 11.1. Retrying the Same Operation Yields One Stable Receipt

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(IdempotentReceiverFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class IdempotentReceiverIntegrationTest {

    @Autowired
    ChargeGateway gateway;

    @Autowired
    InMemoryIdempotentChargeReceiver receiver;

    @Test
    void duplicateRequestReturnsExistingResult() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A",
                "CHARGE-1001",
                "ORD-1001",
                new BigDecimal("100000"));

        ChargeReceipt first = gateway.charge(command);
        ChargeReceipt again = gateway.charge(command);

        assertEquals(first, again);
        assertEquals(1, receiver.appliedCount());
    }

    @Test
    void independentOperationCreatesAnotherReceipt() {
        gateway.charge(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));
        gateway.charge(new ChargeCommand(
                "TENANT-A", "CHARGE-2", "ORD-1",
                new BigDecimal("5000")));

        assertEquals(2, receiver.appliedCount());
    }
}
~~~

These tests verify **Gateway → channel → handler → return value** within a single Spring context. They do not exercise a broker, remote payment service, DB durability, or interceptor selector, so separate tests are needed for each of those boundaries.

### 11.2. Spring Message IDs May Differ While the Operation Remains the Same

A separate test demonstrates that two messages constructed from the same command can carry different IDs:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class SpringMessageIdVsOperationIdTest {

    @Test
    void distinctMessageIdsCanCarrySameOperation() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-77", "ORD-77",
                new BigDecimal("100000"));

        Message<ChargeCommand> first =
                MessageBuilder.withPayload(command).build();
        Message<ChargeCommand> second =
                MessageBuilder.withPayload(command).build();

        assertNotEquals(
                first.getHeaders().getId(),
                second.getHeaders().getId());
        assertEquals(
                first.getPayload().operationId(),
                second.getPayload().operationId());
    }
}
~~~

This result illustrates that **framework message identity** and **business operation identity** are two distinct layers. Do not infer from a unit test building new messages that a broker always changes IDs on redelivery: transports and converters have their own semantics.

### 11.3. Testing Duplicate Advice Must Also Verify the Handler

If using `IdempotentReceiverInterceptor`, a proper test should check:

1. On the first new key, the selector marks it accepted.
2. On the second old key, the metadata store indicates a duplicate.
3. The message is **marked/discarded/errored** as configured, rather than assuming false always drops.
4. If discarded, the caller/Gateway receives a result or times out per contract.
5. If the handler throws on the first attempt, retries are not wrongly blocked by a `SEEN` marker — or it is explicitly documented as intentional at-most-once admission.
6. Restarts/multi-instance runs with a production metadata store preserve the expected retention behavior.

You cannot rely solely on testing `selector.accept(...)` to prove a business operation is processed exactly once.

## 12. Interaction with Brokers, Gateways, Retries, and Error Channels

### 12.1. Transport Retries Do Not Necessarily Preserve the Spring Message ID

When messages travel through Kafka/JMS/AMQP/HTTP, separate the layers:

~~~text
Business event:
  eventId=EVT-77
  operationId=CHARGE-77

Transport record:
  topic=payments.requests
  partition=2
  offset=581

Spring Integration message in JVM:
  headers.id=UUID-1

Retry / republish:
  same eventId=EVT-77
  maybe new transport record offset=622
  maybe new headers.id=UUID-2
~~~

If a consumer only deduplicates by `topic/partition/offset`, an event **republished as a new record** can slip through. If it only uses `headers.id`, rebuilding the message can also generate a new ID. **Business eventId/operationId** is generally a more stable key for preventing repeated effects of the same logical event.

### 12.2. Delivery Semantics Do Not Equal Business Idempotency

| Delivery Situation | Risk | What Is Needed? |
|---|---|---|
| **At-most-once delivery** | Message may be lost before business commit. | Accept risk of loss or use a different protocol. |
| **At-least-once delivery** | Same message redelivered. | Idempotent Receiver/ledger and retry policy. |
| **Broker transaction** | Broker records/offsets have specific broker guarantees. | Still need to protect side effects outside the broker. |
| **HTTP caller retry** | Command may be resent with a different message ID. | Stable caller-supplied/server-issued operation ID and validation. |
| **DLQ replay** | Old event returns hours/days later. | Appropriate retention, dedupe state, and reauthorization. |
| **Outbox relay retry** | An event may be published repeatedly. | Preserve event ID across publish attempts. |

**Do not claim end-to-end exactly-once merely because broker transaction mode or consumer idempotency advice is enabled.** You must specify where and how side effects are protected.

### 12.3. Ack Before or After Business Commit?

~~~text
Receive
  -> validate
  -> look up / acquire operation key
  -> execute business work
  -> persist authoritative outcome
  -> broker acknowledgment
~~~

This is the **desired logical order** for an at-least-once flow. If acking before the result is durably stored, a crash can lose the operation. If acking after commit, a crash can cause the broker to redeliver, so the receiver must deduplicate. Specific transactional adapters, broker offset semantics, and store commits must be verified against the infrastructure.

### 12.4. Gateway Reply Timeout Does Not Prove Business Failure

A request–reply Gateway can experience:

~~~text
T0 Caller sends CHARGE-77.
T1 Receiver calls external payment.
T2 Payment commits.
T3 Reply network packet is lost.
T4 Gateway times out.
T5 Caller retries CHARGE-77.
~~~

The retry should keep the **same operationId**, check the stored receipt status, or use a remote idempotency key. Do not issue a new operation ID every time a caller hits a timeout, unless the business genuinely intends to create a distinct authorized operation.

### 12.5. Error Channel Is an Error Path, Not an Inbox Ledger

Spring Integration may wrap exceptions into an `ErrorMessage` and send them to `errorChannel` depending on execution model/configuration. However:

- A retried message might not produce an `ErrorMessage` in every configuration.
- An error on another thread may occur **after the producer already received an ack**.
- A handler exception does not mean an external side effect did not commit.
- A recovery handler receiving a `Throwable` does not automatically know if the operation is COMPLETED/UNKNOWN.
- A duplicate discarded by an interceptor might produce no technical error at all.

Store **business operation state and receipts** in an appropriate ledger, and use the error channel to **classify, observe, schedule retries, and quarantine** per contract.

### 12.6. Where Should Retry Advice Be Placed?

Consider an example with two endpoints:

~~~text
Token / Message
  -> Idempotency check / acquire
  -> External payment call
  -> Persist completion
~~~

If you wrap `RequestHandlerRetryAdvice` around the **entire endpoint** after the selector has already recorded `SEEN`, the second attempt could be treated as a duplicate even though the first did not finish. If the advice wraps only the external payment call, keep the **same operationId/idempotency key** and do not blindly retry UNKNOWN outcomes.

| Retry Scope | Key That Must Be Stable | Primary Risk |
|---|---|---|
| Retry local handler | Operation key. | `SEEN` marker recorded too early. |
| Retry broker record | Event/operation ID. | Redelivery after commit; ack lost. |
| Retry HTTP payment | External idempotency key. | Timeout after remote commit. |
| Replay from DLQ | Original event identity + consumer scope. | Dedupe record expired, schema changed. |
| Rebuild projection | Event ID + versioned consumer namespace. | Old dedupe blocks necessary replay. |

Do not retry by **manually deleting the idempotency key** to “let the message run again” without knowing whether the side effect already committed.

## 13. Combining with Router, Filter, Splitter, and Aggregator

### 13.1. Router: One Event Can Trigger Multiple Operations

An `OrderPaid(eventId=EVT-77)` event is routed by a Router to:

~~~mermaid
flowchart TD
    E["OrderPaid EVT-77"] --> R{Router / Recipient List}
    R --> B[BillingProjection]
    R --> N[Notification]
    R --> A[Audit]
    B --> K1["Key BILLING/EVT-77"]
    N --> K2["Key NOTIFY/EVT-77"]
    A --> K3["Key AUDIT/EVT-77"]
~~~

If all share a global dedupe key of just `EVT-77`, Billing may mark SEEN first, causing Notification and Audit to treat the message as a duplicate. Better: use a **consumer-specific scope** or a distinct operation ID per side effect.

Even if the Router only picks **one** route at a time, you must define what happens when routing policies change and an event is replayed: should an already completed old route run again? Changing namespaces/routes can create new effects and requires approval.

### 13.2. Filter May Record SEEN Too Early

~~~text
Idempotency filter marks EVT-77 as SEEN
  -> Business Filter rejects EVT-77
  -> Retry with corrected data still treated as duplicate
~~~

Distinguish between:

- **Malformed/permanently rejected event:** may record a final rejection outcome so it is not reprocessed endlessly.
- **Temporarily ineligible event:** may need retry/re-evaluation per business policy; should not be marked COMPLETED.
- **Accepted/processed event:** record completion only after the business work finishes properly.

A `MessageSelector` running before a business Filter can be valid for **admission dedupe**, but never treat it implicitly as **business completion dedupe**.

### 13.3. Splitter: Parent Correlation Is Not a Child Idempotency Key

~~~text
Batch B-1, correlationId=B-1
  -> Item #1 (itemId=I-1)
  -> Item #2 (itemId=I-2)
  -> Item #3 (itemId=I-3)
~~~

If each child uses `correlationId=B-1` as its idempotency key, items #2 and #3 could be mistaken for duplicates of item #1.

A better key:

~~~text
(tenantId, PROCESS_ITEM, batchProcessingId, itemId)
~~~

or a stable `itemOperationId` issued by the producer. `sequenceNumber` can help when per-item IDs are deterministically derived from an input snapshot, but do not use sequence numbers alone since many batches share 1, 2, 3.

### 13.4. Aggregator: Duplicates Can Cause Premature Release

An Aggregator waits for three messages:

~~~text
Expected: I-1, I-2, I-3
Received: I-1, I-1, I-2
~~~

If only counting `group.size()==3`, a duplicate can mask the missing `I-3`. Deduplication should happen by **business item identity**, and the Aggregator should check the set of expected IDs with an appropriate release strategy rather than trusting raw message counts.

If an Idempotent Receiver **skips duplicates** before the Aggregator, make sure it does not drop a **required outcome** and leave the group waiting forever. You may need to return the stored result for duplicates instead of silently discarding them.

### 13.5. Resequencer: Ordering Does Not Guarantee Non-Duplication

A Resequencer can emit messages in order by `sequenceNumber`, yet broker redelivery can still produce duplicates of the same logical event. **Ordering** and **idempotency** are two separate invariants.

~~~text
Received: seq=2, seq=1, seq=2 (redelivery)
Desired business effects:
  effect(seq=1) exactly once
  effect(seq=2) exactly once
~~~

Both a sequence/correlation contract, duplicate handling, and downstream idempotency are needed. If a duplicate is dropped, the Resequencer must still have all required positions to release properly.

### 13.6. Claim Check: A New Claim ID Does Not Create a New Operation

An original order may get a reissued claim because the old token expired:

~~~text
Claim C-100 -> operation PAY-ORD-1
Claim C-200 -> operation PAY-ORD-1 (authorized replay)
~~~

If `claimId` is used as the idempotency key, `C-200` could invoke payment again even though the business operation already ran via `C-100`. Separate **payload retrieval reference** from **business operation ID**.

### 13.7. Scatter–Gather: One Request, Multiple Branch Outcomes

~~~text
requestId=REQ-1
  -> inventory branch: op=REQ-1/inventory
  -> fraud branch:     op=REQ-1/fraud
~~~

Both branches can receive the same request ID yet perform different effects, so scope idempotency by recipient. The Gatherer must:

- Deduplicate replies sharing `requestId + recipientId` per the attempt/version contract.
- Not count two Inventory replies as two required recipients.
- Not treat one COMPLETED branch as confirming the entire request.
- Guard against late replies from an old attempt after group timeout.

**A global key using only `requestId` will mistakenly block valid branches.**

## 14. When a Transformer Alters Message Identity

### 14.1. A New Message Does Not Automatically Create a New Business Event

~~~java
// Input is an event needing normalization.
record PaidEvent(String eventId, String orderId) {}
record NormalizedPaidEvent(String eventId, String orderId) {}

NormalizedPaidEvent normalize(PaidEvent event) {
    return new NormalizedPaidEvent(
            event.eventId(),
            event.orderId().trim().toUpperCase());
}
~~~

A Transformer can create a new payload and a new message; yet if `eventId` is still `EVT-77`, it can still be **the same business event**. Deduplicating by the new Spring Message ID will fail to reflect this.

### 14.2. Do Not Let a Transformer Generate an operationId on Retry

Wrong:

~~~java
String operationId =
        java.util.UUID.randomUUID().toString();
~~~

if this code runs **every time** the same command is received. Each retry gets a different key and idempotency is defeated.

Better: `operationId` is assigned by a **trusted source when the business operation is created**, and propagated intact across retries/replays. For events lacking an upstream ID, there must be a numbering strategy at the ingress point backed by durable state; never generate random IDs on each consumer attempt.

### 14.3. Header Mapping and Trust Boundaries

If `eventId` or `idempotencyKey` lives in Kafka/HTTP headers:

- Is it propagated through outbound/inbound adapters?
- Does deserialization change the header's type or format?
- Is the adapter allowed to trust headers set directly by an external client?
- Can the payload's `operationId` conflict with the `idempotencyKey` header?
- Are headers stripped when passing through a Transform/Bridge/Router?

A safe approach is to designate **a single source of truth** for operation identity, validate and canonicalize it at trusted ingress, and propagate it consistently. Never copy all untrusted headers blindly and treat them as authorization to read stored receipts.

## 15. TTL, Memory, Persistence, and Duplicate-Detection Data

### 15.1. Dedupe State Must Live Long Enough

A key table purged after 10 minutes may be insufficient when:

~~~text
Broker retry window:      30 minutes
DLQ replay window:        7 days
Payment dispute window:   longer
Retention policy:         per business and legal rules
~~~

You do not always need to keep **full payloads or receipts** for that entire duration. You can separate:

- **Active operation record:** key, state, receipt, lease — sufficient for in-flight retries.
- **Completed tombstone:** minimal key, final status, fingerprint, external reference for the replay horizon.
- **Audit archive:** per separate retention and access policies, if actually required.

However, if a tombstone disappears while an old event can still be replayed, the consumer may process it as new. Setting TTL is a **business/architectural decision**, not merely cache tuning.

### 15.2. SimpleMetadataStore Does Not Guarantee Persistence Across Restarts

`SimpleMetadataStore` is suitable for learning/testing or use cases that accept in-memory state. For durable idempotency, consider a `ConcurrentMetadataStore` with proper persistence/transactions or a dedicated inbox/ledger table.

Questions to answer:

- Is the dedupe store shared across multiple JVMs?
- Is `putIfAbsent` atomic when two nodes run concurrently?
- Does the store retain keys across restarts?
- Is there a transaction covering the business mutation?
- Once cleanup deletes a key, how is a late duplicate handled?
- Are there limits on key count, TTL, and capacity alerts?

Do not equate the `ConcurrentMetadataStore` interface with **distributed exactly-once**. Actual guarantees depend on the backend implementation and side-effect boundaries.

### 15.3. Store Unavailable Is Different from Duplicate

~~~text
metadata store read timeout
~~~

This condition does not prove the operation was seen before. When the store is unavailable, the safe strategy for payments is usually **not to invoke new external side effects without an alternative idempotency safeguard**.

Some systems may allow a degraded mode using a remote idempotency key if the external API is strong enough, but that must be an explicitly approved policy; never default to “can't read the ledger, so just process it”.

### 15.4. Cleanup Is a Separate Workflow

If an operation is COMPLETED but deleting sensitive data from the ledger fails, **never retry the payment simply because cleanup failed**.

~~~text
Operation status = COMPLETED
Cleanup status   = PENDING_DELETE

Cleanup worker:
  retry deleting old payload/temporary data
  retain minimal dedupe tombstone if policy requires
  alert if deletion exceeds deadline
~~~

Ensure backups, replicas, caches, and DLQs do not retain expired data beyond retention policies. A “delete succeeded” on the primary database does not automatically prove all copies have been purged.

## 16. Security When Using Idempotency Keys

### 16.1. Do Not Trust Client-Supplied Keys Without Binding

Suppose an HTTP caller sends:

~~~text
Idempotency-Key: CHARGE-1001
Tenant: TENANT-A
~~~

The system must not treat these two headers as authorization. You must:

1. Authenticate the caller (mTLS/token/session per environment).
2. Derive tenant/merchant scope from the **principal or server-side authorization context**.
3. Verify the `operationId` belongs to the caller and the authorized business resource.
4. Validate key format, length, entropy/reuse policy, and rate limits.
5. If the key already exists, check the **payload fingerprint** before returning a receipt.
6. Never leak the receipt of an operation the caller is not authorized to access.

An easily guessable key is merely an **identifier**, not proof of ownership.

### 16.2. Deduplication Must Not Mask Security Incidents

If tenant B's token spoofs tenant A's operation ID, the system must not return `DUPLICATE_SUCCESS` prior to authorization. The order should be:

~~~text
Authenticate
  -> Authorize tenant/resource/operation
  -> Validate idempotency key + fingerprint
  -> Read/claim operation state
  -> Return previous result / execute operation
~~~

Even responding “operation key already exists” can leak information if access control is missing. The API may need to return a generic error for keys outside the caller's permitted scope.

### 16.3. Payload Fingerprints Do Not Replace Trusted Source Data

If you hash data modified by an attacker without authenticating the input source, the fingerprint only proves “two byte sequences match”, not that **the business action is authorized**. For broker events, verify the producer source, schema version, signatures/authentication where required, and tenant isolation.

### 16.4. Do Not Log Full Idempotency Keys Containing PII

An operation ID like `PAY:customer-email@example.com` can expose personal information in metrics/logs. Use opaque IDs or appropriately masked/hashed references, with restricted retention and access control.

For metric labels, **do not** use high-cardinality fields like `operationId`, `eventId`, tenant user IDs, or Spring Message IDs. Use bounded labels such as component, outcome, reason class, and route.

## 17. Flow Observability: What Is “Seen” vs. What Is “Completed”?

### 17.1. Suggested Events

~~~text
event=MESSAGE_RECEIVED
  operationRef=CHARGE-1001
  deliveryAttempt=1

event=IDEMPOTENCY_KEY_VALIDATED
  operationRef=CHARGE-1001
  keyScope=PAYMENT_CHARGE

event=OPERATION_ACQUIRED
  operationRef=CHARGE-1001
  state=IN_PROGRESS

event=SIDE_EFFECT_REQUESTED
  operationRef=CHARGE-1001
  remoteIdempotencyKey=CHARGE-1001

event=OPERATION_COMPLETED
  operationRef=CHARGE-1001
  receiptRef=PAY-XYZ

event=DUPLICATE_RECEIVED
  operationRef=CHARGE-1001
  deliveryAttempt=2

event=DUPLICATE_RESULT_RETURNED
  operationRef=CHARGE-1001
  result=EXISTING_RECEIPT
~~~

This is an **application-proposed structured log schema**, not default Spring Integration events. An `IDEMPOTENCY_KEY_VALIDATED` log must not be mistaken for `OPERATION_COMPLETED`.

### 17.2. Suggested Metrics

| Metric | Meaning |
|---|---|
| `receiver_messages_total` | Messages arriving at the receiver (including redeliveries). |
| `receiver_unique_operations_total` | New accepted business operations. |
| `receiver_duplicates_total{reason}` | Valid duplicates, whether completed or still in-progress. |
| `receiver_conflicts_total` | Same key, different fingerprint. |
| `receiver_completed_total{status}` | Operations reaching completion with final status. |
| `receiver_outcome_unknown_total` | Operations requiring reconciliation. |
| `receiver_lease_expired_total` | Expired operation leases. |
| `receiver_retry_total{reason}` | Retries by classified error reason. |
| `receiver_dlq_replay_total` | Operations replayed via DLQ. |
| `receiver_metadata_store_errors_total` | Errors reading/writing idempotency state. |
| `receiver_operation_latency_seconds` | Latency from start to outcome. |
| `receiver_pending_operations` | Operations without a final outcome yet. |
| `receiver_cleanup_failed_total` | Failed cleanups of expired data. |

These are illustrative metric names, not guaranteed to be auto-generated by the framework in every setup. Never conflate **received message count** with **new operation count**: if an event is delivered three times, the receive metric increases by three while the new-operation metric increases by one per contract.

### 17.3. Operational Signals and Valid Conclusions

| Signal | What Can Be Asserted | What Cannot Be Asserted |
|---|---|---|
| Message received | Consumer received a delivery. | Operation was never processed before. |
| Key found | Store has a matching record. | Business logic already COMPLETED. |
| `SEEN` marker written | Selector recorded appearance. | Side effect committed. |
| IN_PROGRESS lease acquired | One worker holds processing rights per lease contract. | Remote effect has not already happened on an old worker. |
| Receipt persisted COMPLETED | Ledger confirms outcome. | External systems are atomically synchronized without reconciliation. |
| Broker acked | Broker recorded ack per its semantics. | No redelivery/replay exists elsewhere. |
| Duplicate discarded | This message did not proceed past discard. | Caller received a valid receipt. |

### 17.4. Message History Is Not a Durable Inbox

Spring Integration Message History (when tracking is enabled) helps show which Router, Transformer, Gateway, or handler a message traversed. However, it is not:

- A durable `operationId -> COMPLETED receipt` mapping.
- Proof that an external payment committed.
- A multi-JVM concurrency control mechanism.
- A TTL/replay tombstone retention mechanism.
- An authorization record for a tenant.

To investigate a real duplicate, combine the **business operation ledger, transport coordinates, message headers, trace context, and outcome logs**.

## 18. Diagnosis: Why Did a Duplicate Still Produce a Side Effect?

When an order is found to have been processed twice, check in order:

1. **Business intent:** were the two requests truly the same operation, or two valid operations on the same order?
2. **Operation ID:** did the producer preserve a stable ID across retries/replays?
3. **Key scope:** did the receiver use the right tenant, consumer, and operation type?
4. **Header conversion:** did a Transformer/adapter generate a new ID or strip the business key?
5. **Fingerprint:** did both messages share identical business content or was a key improperly reused?
6. **Store:** was an in-memory store used across two pods? Is `putIfAbsent` atomic in the shared backend?
7. **TTL:** was the dedupe record purged before DLQ replay/redelivery?
8. **Advice:** did the selector mark `SEEN` before the handler and the handler fail? Were duplicates actually discarded or still executed?
9. **Side effect:** did the remote service receive the same idempotency key? Did it retain the key long enough?
10. **Crash window:** did payment commit before the ack/ledger record was lost?
11. **Concurrency:** did two workers execute the operation concurrently before the lock/ledger took effect?
12. **Recovery:** did a late reply or stale attempt overwrite a `COMPLETED` status?
13. **Code path:** did another branch bypass the receiver and call the external API directly?
14. **Audit:** are there sufficient records to verify external references and actual charge counts?

Do not “fix” this by arbitrarily extending TTLs or funneling everything into a single FIFO queue before identifying the root cause. Arrival ordering and business side-effect idempotency are distinct invariants.

## 19. Additional Tests for Key Misconceptions

### 19.1. Marking SEEN Does Not Mean the Handler Succeeded

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class PrematureSeenMarkerTest {
    @Test
    void seenBeforeCommitCanBlockAValidRetry() {
        ConcurrentMetadataStore store = new SimpleMetadataStore();
        String operationKey = IdempotencyKeys.forOperation(
                "TENANT-A", "PAYMENT_CHARGE", "OP-1");

        // Attempt 1: mark seen, then crash before business effect.
        assertNull(store.putIfAbsent(operationKey, "SEEN"));

        // Attempt 2: SEEN-only selector treats this as a duplicate.
        assertNotNull(store.putIfAbsent(operationKey, "SEEN"));

        // No receipt exists to prove the operation COMPLETED.
        // This demonstrates a limitation, NOT proper payment behavior.
    }
}
~~~

This test **deliberately demonstrates an unsafe design**. It only tests the store marker without calling payment logic. If the application requires retries after pre-commit failures, replace the `SEEN` marker with explicit state/recovery or an appropriate transaction.

### 19.2. Delimiters in Keys Must Not Cause Collisions

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotEquals;

class CompositeKeyEncodingTest {
    @Test
    void encodedSegmentsDoNotCollapseDifferentTuples() {
        String first = IdempotencyKeys.forOperation(
                "TENANT:A", "PAYMENT", "OP-1");
        String second = IdempotencyKeys.forOperation(
                "TENANT", "A:PAYMENT", "OP-1");

        assertNotEquals(first, second);
    }
}
~~~

Without proper encoding or a composite DB primary key, two different tuples can yield the same string under naive concatenation.

### 19.3. Do Not Assign a New Operation Just Because of a New Spring Message ID

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class RebuiltMessageStillDuplicateTest {
    @Test
    void rebuiltEnvelopeDoesNotChangeTheBusinessOperation() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-77", "ORD-77",
                new BigDecimal("100000"));

        Message<ChargeCommand> first =
                MessageBuilder.withPayload(command).build();
        Message<ChargeCommand> second =
                MessageBuilder.withPayload(command).build();
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        assertNotEquals(
                first.getHeaders().getId(),
                second.getHeaders().getId());
        assertEquals(
                receiver.handle(first.getPayload()),
                receiver.handle(second.getPayload()));
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

### 19.4. Testing Amount Normalization in Fingerprints

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ChargeFingerprintTest {
    @Test
    void mathematicallyEqualAmountsShareDemoFingerprint() {
        ChargeCommand a = new ChargeCommand(
                "TENANT-A", "OP-1", "ORD-1",
                new BigDecimal("100000"));
        ChargeCommand b = new ChargeCommand(
                "TENANT-A", "OP-1", "ORD-1",
                new BigDecimal("100000.00"));

        assertEquals(
                ChargeFingerprint.of(a),
                ChargeFingerprint.of(b));
    }
}
~~~

In real products, amount normalization must align with currency and monetary rules; do not blindly treat numbers with different scales as equivalent if the business intentionally distinguishes them.

## 20. Test Matrix for Message ID and Idempotency Key

| ID | Scenario | What Must Be Verified | What Must Not Happen |
|---|---|---|---|
| IR-01 | New message, new operation key | Creates business operation once. | Mistakenly discarded. |
| IR-02 | Same message redelivered by broker | Returns receipt/acks duplicate per contract. | Repeated side effect. |
| IR-03 | Same business operation but new Spring Message ID | Still recognized as duplicate. | Re-executed due to new ID. |
| IR-04 | Same Message ID but different business operations due to producer bug | Caught by validation/provenance. | Operations mistakenly merged. |
| IR-05 | One order with valid charge and refund | Two distinct operation keys. | Refund skipped due to same orderId. |
| IR-06 | Same operationId, same fingerprint | Returns same receipt. | Charged again. |
| IR-07 | Same operationId, different amount | OPERATION_CONFLICT. | Silently returns old success or makes a new charge. |
| IR-08 | Same local operationId across two tenants | Tenant scopes isolated. | Tenant B blocked by Tenant A. |
| IR-09 | Two consumers receiving same eventId | Each consumer processes once. | Global marker blocks second consumer. |
| IR-10 | One consumer receives three copies of same eventId | One business effect. | Counted as three new events. |
| IR-11 | Two threads receive same key | Atomic key claim/dedupe. | Both independently trigger side effects. |
| IR-12 | Two JVMs share same key | Durable shared ledger. | Each JVM uses local map and processes twice. |
| IR-13 | Selector records SEEN then handler crashes | Retry/recovery policy does not lose work. | Permanently skipped unprocessed. |
| IR-14 | Handler commits then crashes before SEEN | Remote idempotency/reconciliation. | Second side effect created. |
| IR-15 | DB inbox + business effect in same transaction | Atomic completion per DB contract. | Inbox committed while business update lost. |
| IR-16 | Remote HTTP payment times out after commit | UNKNOWN then reconcile. | Blind retry creating a new charge. |
| IR-17 | Broker ack lost after ledger commit | Duplicate returns previous receipt. | New operation created. |
| IR-18 | Gateway caller retries after reply timeout | Stable operation key. | New UUID generated for same operation. |
| IR-19 | Late reply from old attempt | State/version guard. | FAILED overwrites COMPLETED. |
| IR-20 | Lease expires while old worker still alive | Fencing/reconciliation. | Old worker commits stale state. |
| IR-21 | Metadata store unavailable | Controlled error/degraded policy. | Treated as safely a new key. |
| IR-22 | Metadata store in-memory only, process restarts | Limitation tested or replaced by durable store. | Promising dedupe across restarts. |
| IR-23 | Record TTL 5 minutes, replay after 1 day | Clear retention/replay policy. | Late replay accidentally runs as new. |
| IR-24 | DLQ replay with same event ID | Preserves identity and scope. | Assigning a new ID on every requeue. |
| IR-25 | Outbox publishes same event twice | Consumer-side dedupe. | Notification/payment duplicated. |
| IR-26 | Transformer constructs a new message | Business identity preserved. | Deduplicating by new `headers.id`. |
| IR-27 | Filter rejects message before handler | Clear rejection/seen semantics. | Wrongly marked COMPLETED. |
| IR-28 | Router sends event to two subscribers | Consumer-specific keys. | Only first branch processed. |
| IR-29 | Splitter emits three children with same correlationId | Per-child key. | Children #2 and #3 mistakenly blocked. |
| IR-30 | Aggregator receives duplicate item result | Does not count duplicate for missing item. | Releases incomplete group. |
| IR-31 | Resequencer reorders while receiving duplicates | Both ordering and dedupe work. | Duplicate commits. |
| IR-32 | Claim Check reissues new claim | Preserves operation identity. | New side effect due to different claimId. |
| IR-33 | Scatter–Gather receives duplicate branch reply | Recipient-scoped dedupe. | Two Inventory replies substitute for Fraud. |
| IR-34 | Client-spoofed HTTP header key | AuthN/AuthZ/tenant binding. | Stored receipt leaked. |
| IR-35 | Same key requested by different principal | Does not return unauthorized receipt. | Cross-account leakage. |
| IR-36 | Key contains delimiter characters | Unambiguous composite encoding. | False collisions. |
| IR-37 | Payload canonicalization changes after deploy | Versioning/compatibility. | False conflicts or missed duplicates. |
| IR-38 | Default advice duplicate handling | Test actual mark/discard/error behavior. | Assuming duplicates are always dropped. |
| IR-39 | Gateway duplicate discarded | Caller gets response/timeout per contract. | Silently hanging uncontrolled. |
| IR-40 | Record cleanup after completion | Appropriate tombstone/retention. | Duplicate side effect after key expiry. |
| IR-41 | Old event schema replayed to new handler | Clear scope/version migration. | Processing violating policy. |
| IR-42 | Terminal business failure retried with same key | Returns/recovers per defined state. | Turning permanent rejection into false success. |
| IR-43 | Unknown operation with no receipt | Reconcile/manual action. | Unfounded claim that it didn't commit. |
| IR-44 | Branch bypasses idempotent handler | Detection/system test. | Unprotected side effect. |
| IR-45 | Metrics when 1 event is delivered 5 times | 5 receives, 1 unique operation. | Counting 5 business operations. |

### 20.1. Choosing the Right Test Level

| Level | Best For Testing | Cannot Prove |
|---|---|---|
| **Key derivation unit test** | Tenant/consumer/op scope, fingerprint, normalization. | DB uniqueness or broker ack. |
| **In-memory receiver unit test** | Duplicate returns receipt, conflicts, concurrent fake. | Remote payment idempotency across crashes. |
| **Spring Integration test** | Gateway, Message ID rebuild, selector/advice, channel behavior. | Metadata store durability unless using a real store. |
| **Database integration test** | Unique constraints, transactions, locks/leases, recovery. | Remote HTTP side effects when mocked. |
| **Adapter test** | Broker redelivery, header mapping, retry advice scope. | External payment API commit if not integrated. |
| **System/chaos test** | Crash windows, timeout after commit, multi-node concurrency. | All production failure modes over time. |
| **Security test** | Tenant auth, key spoofing, receipt access, retention. | Full risk coverage without trust-boundary review. |

A **green unit test** only proves in-memory logic matches the fixture; if the goal is preventing double charges after a crash, test at the **exact boundary between broker, durable state, and payment provider**.

## 21. Common Design Mistakes

| Mistake | Consequence | Proper Approach |
|---|---|---|
| Using `MessageHeaders.ID` as business idempotency key. | Rebuilt messages get new IDs, duplicates slip through. | Use stable `eventId`/`operationId` from trusted source. |
| Using `orderId` for all actions on an order. | Valid refunds/adjustments get blocked. | Key by business operation type and instance. |
| Using `traceId` for deduplication. | Multiple operations in one trace collapse into one. | Traces for observability, operation IDs for idempotency. |
| Using Splitter's `correlationId` for each child. | Multiple children treated as duplicates. | Include properly scoped child/operation identity. |
| Using the same key across all event subscribers. | Second subscriber never processes. | Consumer-scoped or operation-specific keys. |
| Generating a new UUID at the consumer on every receive. | Retries always get new keys. | Assign stable operation ID at ingress/producer. |
| Marking `SEEN` before handler and treating as COMPLETED. | Pre-commit crash causes lost processing. | Durable state/transactions/recovery. |
| Marking `SEEN` only after handler without remote idempotency. | Post-commit crash can duplicate effects. | Reconciliation/remote idempotency key. |
| Assuming interceptor always discards duplicates. | Duplicates still hit handler depending on config. | Test actual mark/discard/error behavior. |
| Discarding Gateway duplicates without replying. | Caller times out even though operation finished. | Return stored receipt/status. |
| Using only `SimpleMetadataStore` across multiple nodes. | Each node has isolated state, duplicates run twice. | Durable/shared store with atomic contract. |
| Using only a DB `SELECT` then `INSERT`. | Races between concurrent workers. | Unique constraints/CAS/locking transactions. |
| Equating a DB transaction with a remote HTTP commit. | External effect cannot roll back. | Idempotency at side-effect boundary/reconcile. |
| Retrying on remote timeout assuming it didn't commit. | Double charge. | `UNKNOWN` outcome and status query. |
| Returning previous receipt for same key with different payload. | Hides conflicting data. | Fingerprint/version check, conflict error. |
| Purging dedupe state before the replay horizon. | Late duplicates run as new. | Appropriate retention/tombstones. |
| Reissuing a Claim Check ID and treating it as a new operation. | Same original payload processed twice. | Separate claim ID and operation ID. |
| Deleting keys on failed events and rerunning. | May repeat already committed side effects. | Choose recovery by state and evidence. |
| Treating a FIFO queue as an exactly-once guarantee. | Retries still produce duplicates. | Ordering and idempotency are independent. |
| Treating broker transactions as exactly-once payments. | External HTTP payments can still repeat. | External idempotency/reconciliation. |
| Using user-supplied keys to fetch receipts without authorization. | Leaks another tenant's status/receipts. | Bind keys to principal and resource. |
| Logging operation keys containing email/PII. | Data leaks in logs/metrics. | Opaque IDs, masking, bounded label cardinality. |
| Testing only the single-message happy path. | Misses crash windows, races, replays. | Test matrix covering duplicates/concurrency/restarts. |
| Treating a duplicate of a final FAILURE as success. | Wrong business outcome. | Persist/read final states with clear semantics. |

## 22. Practice Exercises

1. **Inspect Message ID:** create two Spring `Message<ChargeCommand>` instances from the same payload, print `MessageHeaders.ID` and `operationId`; explain why one ID can differ while the operation stays the same.
2. **Dedupe fake:** use `InMemoryIdempotentChargeReceiver` to process the same command three times, asserting only one simulated charge.
3. **Key conflict:** keep `operationId` but change the amount; verify `OPERATION_CONFLICT` instead of returning the old success.
4. **Same order, two operations:** create a CHARGE and an ADJUSTMENT on one order, choose two different operation IDs, and verify both execute.
5. **Multi-tenant:** same local `operationId` across two tenants; verify each tenant has independent state and auth is still enforced.
6. **Consumer scope:** have BillingProjection and NotificationService process the same `eventId`; design keys that don't wrongly block branches.
7. **Delimiter collision:** construct key components containing `:`, testing unambiguous encoding.
8. **Stable normalization:** compare amounts `100000` and `100000.00`, testing policy-based fingerprinting to confirm same operation when valid.
9. **Premature SEEN marker:** mark SEEN before the handler and simulate a crash, showing why valid retries get dropped.
10. **Post-commit marker:** simulate business commit before recording the marker, then crash; design a way to prevent duplicate side effects.
11. **Operation state machine:** add `IN_PROGRESS`/`COMPLETED`/`UNKNOWN` and transitions to the fake, testing that COMPLETED is never returned from UNKNOWN.
12. **Durable inbox:** create a table with unique key `(tenant_id, consumer_name, operation_id)`; test two transactions racing to insert the same key.
13. **Atomic DB work:** write a business projection and receipt in the same DB transaction; kill the transaction mid-way and verify consistent rollback.
14. **Remote payment:** fake a remote provider supporting idempotency keys and status queries; simulate commit success followed by a lost response, verifying retries don't double-charge.
15. **Concurrent workers:** test the same key from two threads and multiple processes, proving a single unique operation effect at DB/provider level.
16. **Lease/fencing:** worker A holds an old lease, B holds a new lease; let A try to commit and verify it is blocked by the version guard.
17. **Spring Integration DSL:** wire `ChargeGateway` → handler, invoke again with the same command, and assert the returned receipts match.
18. **IdempotentReceiverInterceptor:** use `MetadataStoreSelector` or an equivalent selector, test new and duplicate keys, and verify actual mark/discard/error behavior per config.
19. **Retry advice scope:** fail inside the handler after the selector records SEEN; check whether retries are wrongly blocked and adjust the design if needed.
20. **Router/Recipient List:** send one `eventId` to two consumers, implement consumer-specific keys, and test redelivery.
21. **Splitter:** split a batch into three items sharing a correlation ID, assign per-item operation keys, and avoid wrongly blocking item #2.
22. **Aggregator:** send `I-1, I-1, I-2` instead of `I-1, I-2, I-3`; prove duplicates cannot substitute for a missing child.
23. **Claim Check replay:** issue a new claim for the same business operation, verifying the ledger still returns the old receipt once payment has completed.
24. **Broker integration:** send an event through an adapter, change Spring Message ID during deserialization, and verify the business key stays intact and duplicates are handled properly.
25. **DLQ replay:** re-inject an event after a short TTL, demonstrating duplicate-effect risk; design retention/tombstones for the real horizon.
26. **Authorization:** have a tenant B caller submit tenant A's `operationId`; confirm no unauthorized receipt or status is returned.
27. **Monitoring:** emit `OPERATION_ACQUIRED`, `OPERATION_COMPLETED`, and `DUPLICATE_RESULT_RETURNED` logs plus a per-reason dashboard without high-cardinality labels.
28. **Failure runbook:** write recovery procedures for `COMPLETED`, `IN_PROGRESS`, `UNKNOWN`, `FAILED_RETRYABLE`, and `REJECTED_CONFLICT`, distinguishing cases requiring reconciliation.

### Criteria for Evaluating an Implementation

- Does a logical operation have a **stable key** across retries, broker redeliveries, and message rebuilds?
- Does the key separate tenants, consumers, and distinct valid operations?
- Are same-key, different-payload requests detected rather than treated as duplicate successes?
- Does state distinguish **seen** from **completed**?
- Do durable records survive crashes, multi-node deployments, and the replay horizon?
- Do external side effects have remote idempotency or recovery/reconciliation?
- Do Gateway duplicates return the previous receipt/status per contract?
- Are retries/DLQs/timed-out callbacks handled without blindly creating new operations?
- Do Filter/Router/Splitter/Aggregator branches use the right identity granularity?
- Are state stores, transports, and effect-commit boundaries tested directly rather than only mocked?

## 23. Self-Check Questions

**Question 1:** Two Spring messages have different `MessageHeaders.ID` values but the same `operationId`. Can they be a business duplicate?

**Yes.** If the same logical operation is retried or the message is reconstructed, different Spring message IDs do not prove it is a new operation.

**Question 2:** Two messages share the same `orderId`, one a CHARGE command and one a REFUND command. Should they be deduplicated by `orderId`?

**No.** They are two distinct business operations; the key must differentiate operation types and instances.

**Question 3:** Can `correlationId` replace `operationId`?

**Not by default.** Correlation groups messages/request–reply flows and may span multiple child operations; a group ID is insufficient to deduplicate individual side effects.

**Question 4:** Why is `traceId` not an idempotency key?

**Because** multiple operations can share a trace, and retries can create new traces. Traces serve observability, not business identity.

**Question 5:** If a consumer records `SEEN` and crashes before the handler runs, what happens on retry?

If the selector only checks SEEN, the retry can be wrongly blocked. Proper state/recovery/transactions are needed; SEEN is not COMPLETED.

**Question 6:** What if the handler commits and the process dies before recording SEEN?

A redelivery may invoke the handler again. External idempotency, durable result reconciliation, or a shared transaction (when possible) is required.

**Question 7:** When can a duplicate return the previous receipt?

When the key, tenant/resource, fingerprint, and **authoritative COMPLETED outcome** match per contract. Never return a receipt for a spoofed token or an UNKNOWN operation.

**Question 8:** Should the same `operationId` with a different amount be treated as a valid duplicate?

**No.** Verify the fingerprint and reject/investigate the key conflict instead of returning the old SUCCESS.

**Question 9:** Why add `consumerName` to an event dedupe key?

Because a single event may need independent effects in Billing, Notification, and Audit; processed status in one consumer must not block others.

**Question 10:** Does using `SimpleMetadataStore` on one pod guarantee deduplication across three pods?

**No.** Per-pod in-memory stores do not provide atomic shared state across pods or survive restarts.

**Question 11:** Does `ConcurrentMetadataStore.putIfAbsent` mean the business mutation and marker always commit together?

**No.** The atomicity of `putIfAbsent` applies only to the store contract, not external HTTP payments unless additional transactional/idempotency mechanisms exist.

**Question 12:** Does a Gateway timeout mean the payment wasn't charged?

**No.** Payment may have committed while the response was lost; that is an UNKNOWN situation requiring reconciliation.

**Question 13:** With a single Inbox/DB transaction, can duplicates of a business mutation in the same DB be prevented?

**Yes**, if the key is unique, locking/transactions and the business update/receipt truly share the same transaction, and recovery is sound. This does not automatically extend to external systems.

**Question 14:** If a message passes through a Transformer and gets a new Spring Message ID, how do you preserve idempotency?

Keep the stable business `eventId`/`operationId` in the payload or normalized/propagated metadata; derive the key from the authoritative source, not the new instance ID.

**Question 15:** A Splitter creates three children with the same correlation ID. Is deduplicating all of them by correlation ID correct?

**No.** The three children are distinct parts. Per-item identity, such as `batchProcessingId + itemId`, is required.

**Question 16:** Does a Resequencer prevent duplicate side effects?

**Not automatically.** It restores message emission order per the sequence contract; idempotency must protect each individual operation.

**Question 17:** If Claim Check issues a new token for the same original operation, should a new charge be created?

**Not by default.** Claim ID is a payload reference; when replaying the same operation, keep the operation ID and check the durable receipt/idempotency.

**Question 18:** If the metadata store is unavailable, can the key be treated as new and payment proceed?

**Not by default.** It is unknown whether the operation already ran; you need a fail-closed policy or verified remote idempotency/reconciliation.

**Question 19:** What happens if the record TTL expires while the broker can still replay?

An old duplicate may be treated as a new operation. Retention/tombstones/replay policies must cover the expected horizon.

**Question 20:** Does `IdempotentReceiverInterceptor` automatically make all duplicates safe when a handler has side effects?

**No.** The advice/selector helps detect/mark or handle duplicates per configuration. For critical side effects, you still need durable operation state, receipts, concurrency control, and idempotency at the commit boundary.

**Question 21:** Can `Object.hashCode()` be used to store operation fingerprints across deployments?

**No.** Use canonical serialization and a stable fingerprinting mechanism, versioned when needed; hashing does not replace authorization.

**Question 22:** If a duplicate is discarded, is the Gateway guaranteed not to time out?

**No.** If the caller waits for request–reply, silent discarding can drop the reply. Design an appropriate receipt/status or error contract.

**Question 23:** Why does the `IN_PROGRESS` state need leases/fencing?

Because workers can crash, pause, or lose connectivity; leases enable recovery, while fencing/versions protect against an old worker committing after a lease has been reassigned.

**Question 24:** Can “exactly-once” be claimed just because broker transactions are enabled?

**No.** You must specify scope and boundaries. A remote payment API outside the broker transaction can still be invoked again.

## 24. Quick Decision Guide

~~~mermaid
flowchart TD
    I[Message arrives at receiver] --> A{Authenticated and authorized?}
    A -->|No| DENY[Reject / security audit]
    A -->|Yes| K[Derive stable scoped business key]
    K --> F{Valid fingerprint?}
    F -->|No| CONFLICT[Reject conflict]
    F -->|Yes| L{Durable operation state}
    L -->|COMPLETED| OLD[Return previous receipt / duplicate ack]
    L -->|IN_PROGRESS| WAIT[Wait / PENDING / recovery policy]
    L -->|UNKNOWN| RECON[Reconcile external outcome]
    L -->|New or safe retry| WORK[Acquire key + execute safely]
    WORK --> COMMIT[Persist authoritative outcome]
    COMMIT --> ACK[Reply / acknowledge transport]
~~~

This diagram helps frame the right questions **before invoking a side effect**, rather than serving as a complete transaction algorithm. An implementation must guard against races during acquisition, distinguish terminal vs. retryable failures, and handle ledger unavailability.

## 25. Conclusion

**Message ID and idempotency key are not the same concept.** Spring's `MessageHeaders.ID` identifies a specific message instance; a single business event or operation may span multiple messages, deliveries, retries, adapters, JVMs, and trace contexts. Therefore, an **Idempotent Receiver should identify duplicates using a stable business identity** properly scoped to tenant, consumer, and operation, rather than defaulting to message instance IDs, timestamps, or correlation groups.

In Spring Integration, `IdempotentReceiverInterceptor`, `MetadataStoreSelector`, and `ConcurrentMetadataStore` can assist with key checks at endpoints. However, a `SEEN` marker does not mean an operation completed, `SimpleMetadataStore` is not a durable ledger, and discarding duplicates does not automatically return a previous receipt to a Gateway. For critical side effects, combine **unique operation keys, payload fingerprints, durable state/receipts, concurrency control, external API idempotency where available, and reconciliation for UNKNOWN states**.

In the `SPRING_INTEGRATION_PATTERN` module, test every layer: **key derivation → in-memory/unit behavior → Spring Integration flow/advice → database/transport → system crash/retry**. When coordinating with Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway, and error channels, always distinguish **which message is being delivered**, **which operation must execute**, **which result has committed**, and **which redeliveries should simply read the previous outcome**. That is the foundation for building message flows that are reliable, extensible, and traceable when failures occur.
