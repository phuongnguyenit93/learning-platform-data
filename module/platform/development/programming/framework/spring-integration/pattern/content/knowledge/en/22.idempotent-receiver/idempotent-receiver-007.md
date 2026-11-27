# Marking Messages Before or After the Business Action

**Idempotent Receiver** is an Enterprise Integration Pattern (EIP) that allows a system to receive the same message again without **executing unintended duplicate business side effects**. In Spring Integration, `IdempotentReceiverInterceptor` can be combined with `MessageSelector` and `MetadataStoreSelector` to detect whether a key has already appeared. However, a more important question than duplicate detection is: **at what moment should a message be recorded as processed?**

If **marking before the business action**, the system easily blocks two workers from executing the same work, yet risks **losing the task** if the application crashes after saving the marker and before the side effect occurs. If **marking after the business action**, retries easily recover unfinished work, yet risk **duplicating the side effect** if the application crashes after the side effect succeeds and before the marker is saved. Both approaches have a **crash window** if the marker and the business task do not share a transaction boundary or lack a coordination protocol.

The article **Marking Messages Before or After the Business Action** belongs to the **Idempotent receiver** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation with Spring Integration to build loosely coupled, extensible, testable, and observable message flows.

**Foundational takeaway:** There is no single “always mark before” or “always mark after” rule valid for every topology. You must distinguish **message seen**, **message in progress**, and **business action committed**. For side effects within **the same database**, use a unique constraint and a shared transaction so **marker recording and business updates commit atomically**. For side effects across external systems, use target-side idempotency, outbox/inbox, or a state machine with explicit recovery.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish duplicate deliveries, duplicate business commands, and new message instances.
2. Understand the exact timing of when `MetadataStoreSelector` writes keys to the store.
3. Understand the exact default behavior of `IdempotentReceiverInterceptor` when the selector rejects a message.
4. Compare the risks of marking **BEFORE** vs. **AFTER** the business action across crash points.
5. Distinguish `RECEIVED`, `PROCESSING`, `SUCCEEDED`, and `FAILED` instead of relying on a single Boolean.
6. Choose stable, namespaced idempotency keys and guard against same-key different-payload conflicts.
7. Use `ConcurrentMetadataStore.putIfAbsent` for atomic key claiming while understanding its limits.
8. Configure Spring Integration Java DSL with advice and a duplicate discard route.
9. Design a shared transaction for markers and business updates within a single database.
10. Build inbox/outbox or remote API idempotency strategies for cross-system side effects.
11. Test crash windows, retries, concurrent workers, broker redeliveries, and timeouts.
12. Instrument metrics, logs, and TTL/reconciliation policies so unfinished messages are never wrongly blocked.

## 2. The Problem: Redelivered Payment

A service receives `InvoicePaymentConfirmed` events and adds the paid amount to the invoice balance:

~~~text
Message:
  tenantId = tenant-a
  eventId = evt-pay-1001
  invoiceId = INV-1001
  paidMinorUnits = 25000
~~~

A message can arrive twice because:

- The broker did not receive an ACK even though the handler committed.
- The consumer restarted or partitions rebalanced.
- The producer retried due to a network timeout.
- The DLQ was replayed.
- The event was re-emitted via event replay or data recovery.

If every delivery executes:

~~~sql
UPDATE invoice_balance
SET paid_minor_units = paid_minor_units + 25000
WHERE tenant_id = 'tenant-a'
  AND invoice_id = 'INV-1001';
~~~

then **the same event** arriving twice will double the paid amount.

~~~mermaid
flowchart LR
    B["Broker: evt-pay-1001"] --> C1["Consumer receives 1st time"]
    B --> C2["Broker redelivery 2nd time"]
    C1 --> D["Idempotent receiver"]
    C2 --> D
    D --> DB[("Business DB")]
    DB --> O["Only one valid business effect"]
~~~

The job of an Idempotent Receiver is not just recognizing two deliveries, but **ensuring the side effect honors the contract** even when an attempt fails at the worst possible moment.

## 3. “Received” Differs from “Executed”

These three statements mean different things:

1. **Message seen**: a delivery attempt reached ingress.
2. **Processing rights claimed**: one worker claimed the key; other workers must not run the same task simultaneously.
3. **Business action completed**: the business change committed or was authoritatively confirmed by the target system per contract.

~~~mermaid
flowchart TD
    M["Message arrives"] --> R["RECEIVED"]
    R --> P["PROCESSING (claim/lock)"]
    P --> A["Business action"]
    A --> S["SUCCEEDED (committed)"]
    P --> F["FAILED / RETRYABLE"]
    F --> P
~~~

An entry in a `MetadataStore` can prove **a key was written to the store**, yet **does not by itself prove** that the business action finished. That distinction determines when marking should occur.

### 3.1. Two Classes of Identifiers

| Identifier | What It Identifies | Suitable as an Idempotency Key? |
|---|---|---|
| `MessageHeaders.ID` | A single Spring `Message` instance | Usually no: retries may create a new instance |
| `eventId` | A business event stable across redeliveries | Usually suitable for event consumers |
| `commandId` | A command with unique business intent | Usually suitable for command receivers |
| `invoiceId` | An invoice | Too broad if an invoice has multiple payment events |
| `traceId` | A trace/span flow | Does not replace event/command identity |
| `deliveryTag` | A single broker delivery | Unstable across redeliveries |
| `correlationId` | A group of related messages | May be too broad if one group has multiple tasks |
| `retryAttempt` | Attempt number | No, because each retry generates a new key |

If a consumer records individual **payment events**, a suggested key is `(tenantId, sourceId, eventId)`; if receiving a **payment command** that may be resent, the key can be `(tenantId, commandId)`. Keys must be assigned **once** at an authoritative source and **preserved unchanged** across retries.

### 3.2. Same Key with Different Payload Is an Error

~~~text
Attempt 1:
  key=(tenant-a, evt-pay-1001)
  paidMinorUnits=25000

Attempt 2:
  key=(tenant-a, evt-pay-1001)
  paidMinorUnits=75000
~~~

Never silently drop the second message as a harmless duplicate. Same key with a different payload can be an **idempotency-key reuse bug, data conflict, or attack**. Store a `requestFingerprint` computed from canonical business fields to verify consistency, excluding fields that vary per delivery such as timestamps, `traceId`, or retry counts.

## 4. Option A: Marking Before the Business Action

Suppose the system does:

~~~text
1. Dedup Store: putIfAbsent(eventId, "seen")
2. If key exists -> skip
3. If key is new -> update invoice
4. ACK broker
~~~

### 4.1. Success Timeline

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant M as MetadataStore
    participant DB as Business DB
    participant B as Broker

    C->>M: putIfAbsent(evt-pay-1001, "seen")
    M-->>C: New key, accepted
    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    C->>B: ACK
~~~

Advantages:

- Atomic `putIfAbsent` can block two workers from claiming the same key.
- Subsequent duplicates are detected early.
- Reduces duplicate business handler execution when the system is healthy.

However, **recording a seen marker beforehand** must not be confused with **a committed business action**.

### 4.2. Dangerous Crash Window

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant M as MetadataStore
    participant DB as Business DB
    participant B as Broker

    C->>M: putIfAbsent(evt-pay-1001)
    M-->>C: Accepted, marker now exists
    Note over C: Crash before UPDATE invoice
    B->>C: Redelivery evt-pay-1001
    C->>M: putIfAbsent(evt-pay-1001)
    M-->>C: Duplicate
    Note over C: Skip, invoice never updated
~~~

This is **lost work**: the marker says “processed”, yet the business logic never ran.

If the marker is committed and survives restarts, the system may permanently skip the task. Thus a `ConcurrentMetadataStore` holding only key-value “seen” entries is insufficient for business flows with critical side effects.

### 4.3. When Is Marking Before Appropriate?

- Side effects are **non-critical** and losing occasional attempts is acceptable.
- Processing can be **self-healed** by an independent reconciliation job.
- The pre-marker represents **PROCESSING/lease**, not **DONE**, with safe takeover if a worker dies.
- The marker and business write live in **the same transaction**, so no independent marker commits before the business action.

For debiting money, payments, ledger entries, or critical access grants, **never** treat standalone mark-before as an exactly-once guarantee.

## 5. Option B: Executing First, Marking Afterward

Suppose the system does:

~~~text
1. Check if key is DONE
2. If not -> update invoice
3. Save DONE marker
4. ACK broker
~~~

### 5.1. Success Timeline

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Business DB
    participant M as MetadataStore
    participant B as Broker

    C->>M: get(evt-pay-1001)
    M-->>C: Not found
    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    C->>M: put(evt-pay-1001, DONE)
    M-->>C: Saved
    C->>B: ACK
~~~

Advantage: if the system dies before the business action starts, the message is redelivered and no `DONE` marker exists yet; it has a chance to reprocess.

### 5.2. Crash Window After the Side Effect

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Business DB
    participant M as MetadataStore
    participant B as Broker

    C->>DB: UPDATE invoice balance
    DB-->>C: Commit OK
    Note over C: Crash before writing DONE
    B->>C: Redelivery evt-pay-1001
    C->>M: get(evt-pay-1001)
    M-->>C: No marker yet
    C->>DB: UPDATE invoice balance a second time
    Note over DB: Double credit / duplicate side effect
~~~

This is a **duplicate effect**: the business work succeeded, yet the completion marker was not recorded.

### 5.3. Race When Two Workers Check First

Even without a crash, naive `get()` then `put()` is unsafe under concurrency:

~~~text
Worker A: get(key) -> absent
Worker B: get(key) -> absent
Worker A: business action
Worker B: business action
Worker A: put(key, DONE)
Worker B: put(key, DONE)
~~~

Both workers can execute the task. Adding `synchronized` inside one JVM only protects that JVM, which is insufficient for multi-instance deployments.

## 6. Comparison Table: Mark-Before vs. Mark-After

| Criterion | Standalone Mark-Before | Standalone Mark-After |
|---|---|---|
| Does marker exist before side effect? | Yes | No |
| Risk when crashing before business action | **Lost work** because key is seen | Can retry |
| Risk when crashing after action, before marker | If action ran, marker exists | **Duplicate side effect** |
| Race between two workers | `putIfAbsent` can protect claim | Simple `get` then `put` is unsafe |
| Does DONE imply committed? | **No** | Intended, yet still has crash window |
| Suitable for highly critical work? | Only with proper recovery/atomicity | Only with idempotent actions/atomicity |
| If target backend is non-transactional | Requires recovery protocol | Requires target-side idempotency |
| If marker and action share a DB transaction | Can commit atomically | Can commit atomically |

A useful classification:

- Standalone mark-before leans toward **at-most-once attempt** on the consumer, risking lost work.
- Standalone mark-after leans toward **at-least-once business attempt**, risking duplicate effects.
- Achieving **effectively-once** business semantics requires atomicity, idempotency, or reconciliation at the target system.

These are **failure-mode tendencies**, not absolute guarantees of any `put()` call.

## 7. Crash-Point Decision Table

| Crash Timing | Standalone Mark-Before | Standalone Mark-After | Single Shared DB Transaction |
|---|---|---|---|
| Before marker and action | Retries as new | Retries as new | Retries as new |
| After marker committed, before action | May wrongly skip | Cannot occur in after order | Marker uncommitted if transaction unfinished |
| After action committed, before marker | Marker exists, outcome unclear | May re-run action | No half-committed state in one transaction |
| After both committed, before ACK | Duplicate detected | Duplicate detected | Duplicate detected via unique key |
| While two workers process same key | Needs atomic claim | `get+put` insufficient | Unique constraint/transaction isolation |
| Remote side effect succeeded, response lost | Marker does not prove outcome | No marker → may retry | Local transaction does not span remote |

**Never test only the happy path.** Intermediate crash points determine the correctness of an Idempotent Receiver.

## 8. How Does Spring Integration `IdempotentReceiverInterceptor` Work?

Spring Integration provides `IdempotentReceiverInterceptor` as an **advice** wrapping `MessageHandler.handleMessage()`. It uses a `MessageSelector` to decide whether a message is accepted or treated as a duplicate.

Points to understand precisely:

- It is **not a standalone EIP endpoint** replacing the business handler.
- It is attached to a handler endpoint's advice chain, e.g., via Java DSL.
- If the selector rejects a message and **no discard channel or throw-exception option is configured**, the interceptor **by default forwards the message to the handler with the `duplicateMessage=true` header**.
- To prevent duplicates from **reaching the handler**, you must explicitly configure `discardChannel` or `throwExceptionOnRejection=true` as appropriate.
- Use `nullChannel` as the discard destination if silent dropping is intended, while weighing ACK/observability implications.

### 8.1. Default Behavior Is Not Auto-Skip

~~~text
New message:
  selector.accept() = true
  -> handler.handleMessage(message)

Duplicate:
  selector.accept() = false
  -> interceptor sets duplicateMessage=true
  -> handler can still be invoked (default)
~~~

If the handler ignores the duplicate header and always writes to the DB, you can still suffer double effects despite adding the advice. This is a **dangerous misconception**.

### 8.2. Conditions to Exclude Duplicates from the Handler

~~~text
Duplicate
  -> discardChannel configured
     -> message routed to discard flow
     -> target handler does not run

Or:
  -> throwExceptionOnRejection=true
     -> MessageRejectedException routed to error flow
     -> target handler does not run
~~~

Choose the right handling path:

- Duplicate truly `DONE`: can acknowledge/no-op.
- Duplicate still `PROCESSING`: may need retry/requeue; **never automatically ACK as DONE**.
- Same key with different fingerprint: report conflict/quarantine.
- Duplicate HTTP request: often should return **the stored result**, not merely drop the message.

## 9. MetadataStoreSelector: When Does Marking Happen?

`MetadataStoreSelector` uses a `MessageProcessor<String>` to compute the key and a `ConcurrentMetadataStore` to persist metadata. For an absent key, the selector uses **`putIfAbsent(key,value)`** to accept the message. This means the marker can be **written when evaluating the selector, before the handler executes the business action**.

~~~mermaid
flowchart TD
    IN["Message arrives"] --> K["Key strategy computes idempotency key"]
    K --> M{"metadataStore.putIfAbsent()"}
    M -->|"New"| H["Handler business action"]
    M -->|"Exists"| D["duplicateMessage / discard / reject"]
~~~

### 9.1. Default Metadata Store Value

In `MetadataStoreSelector`, the default value is derived from the **timestamp header** (string/hex representation depending on implementation). That **does not** mean the stored value is a business action outcome. If you need to store `SUCCEEDED`, error reasons, request fingerprints, or receipts, you must **design dedicated state storage** or a custom value/processor with an explicit contract.

### 9.2. Atomic `putIfAbsent` Does Not Mean Atomic Business Action

`ConcurrentMetadataStore.putIfAbsent` lets one worker atomically claim a key **within the guarantees of the backing store**. However, it does not turn:

~~~text
putIfAbsent + call external API
~~~

into a single shared transaction. When two steps touch two separate resources, the crash window remains.

### 9.3. `compareValues` Is Not Confirmation of DONE

`MetadataStoreSelector` supports `compareValues` to compare old/new values and accept/overwrite per rules, useful for line/file offsets or versions. Never use it to infer “business succeeded” if the value is just a timestamp. An increasing value may indicate progression, yet **does not guarantee the side effect committed**.

## 10. Choosing Keys and Fingerprints with a Contract

Java 17 event example:

~~~java
public record InvoicePaymentConfirmed(
        String tenantId,
        String sourceId,
        String eventId,
        String invoiceId,
        long paidMinorUnits,
        String payloadFingerprint
) {
    public InvoicePaymentConfirmed {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("TENANT_REQUIRED");
        }
        if (sourceId == null || sourceId.isBlank()) {
            throw new IllegalArgumentException("SOURCE_REQUIRED");
        }
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("EVENT_ID_REQUIRED");
        }
        if (invoiceId == null || invoiceId.isBlank()) {
            throw new IllegalArgumentException("INVOICE_ID_REQUIRED");
        }
        if (paidMinorUnits <= 0) {
            throw new IllegalArgumentException("AMOUNT_INVALID");
        }
        if (payloadFingerprint == null
                || payloadFingerprint.isBlank()) {
            throw new IllegalArgumentException("FINGERPRINT_REQUIRED");
        }
    }
}
~~~

`payloadFingerprint` is a fingerprint computed/verified at ingress over **canonical business fields**, such as event type, `invoiceId`, amount, currency, source, and version. Never blindly trust a client-supplied fingerprint as safe: the server must compute/verify it to detect same-key different-content conflicts.

### 10.1. Composite Key to Avoid Collisions

~~~java
import java.io.Serializable;

public record EventDedupKey(
        String tenantId,
        String sourceId,
        String eventId
) implements Serializable {}
~~~

A key of `(tenantId,sourceId,eventId)` fits when `eventId` is stable within each source's namespace. If an API uses a client-supplied `commandId`, scope it by tenant and operation type to prevent two distinct commands from colliding on idempotency keys.

### 10.2. Do Not Use Mutable Values as Keys

Risky choices:

- `Instant.now()` or a UUID generated **on every delivery**.
- `retryAttempt` or broker delivery tags.
- `MessageHeaders.ID` when retries construct new messages.
- `invoice.status`, balance, email, `updatedAt`.
- `invoiceId` alone when multiple valid payment events target the same invoice.

Such keys can fail to block replays or **mistakenly block** distinct transactions.

## 11. Java DSL: Illustrating Pre-Handler Duplicate Blocking

The following configuration demonstrates the behavior of `MetadataStoreSelector` and `IdempotentReceiverInterceptor`: the key is claimed **before** the handler runs. We explicitly route duplicates to `nullChannel` so the handler is not invoked again.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class PreMarkIdempotencyConfiguration {

    @Bean(name = "payments.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    public ConcurrentMetadataStore dedupMetadataStore() {
        return new SimpleMetadataStore();
    }

    @Bean
    public InvoiceEventHandler invoiceEventHandler() {
        return new InvoiceEventHandler();
    }

    @Bean
    public IdempotentReceiverInterceptor invoiceDedupAdvice(
            ConcurrentMetadataStore dedupMetadataStore) {

        MetadataStoreSelector selector =
                new MetadataStoreSelector(message -> {
                    InvoicePaymentConfirmed event =
                            (InvoicePaymentConfirmed)
                                    message.getPayload();

                    return event.tenantId() + ":"
                            + event.sourceId() + ":"
                            + event.eventId();
                }, dedupMetadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        advice.setDiscardChannelName("nullChannel");
        return advice;
    }

    @Bean
    public IntegrationFlow preMarkFlow(
            IdempotentReceiverInterceptor invoiceDedupAdvice) {
        return IntegrationFlow.from("payments.in")
                .handle("invoiceEventHandler", "apply",
                        endpoint -> endpoint
                                .advice(invoiceDedupAdvice))
                .get();
    }
}
~~~

Demo business handler:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class InvoiceEventHandler {

    private final AtomicInteger calls =
            new AtomicInteger();

    public void apply(InvoicePaymentConfirmed event) {
        calls.incrementAndGet();
    }

    public int invocationCount() {
        return calls.get();
    }
}
~~~

Both code snippets are for **observing advice and dedup inside a single JVM**. The business handler only increments an invocation counter and processes no real payments. Never use this marker-only approach as a zero-loss guarantee for critical financial actions.

### 11.1. Difference from Default Behavior

If you omit the line:

~~~java
advice.setDiscardChannelName("nullChannel");
~~~

then duplicates can **still enter the handler** with header `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE` set to `true`. The demo `apply(InvoicePaymentConfirmed)` handler does not inspect headers, so it would increment the count twice. Lesson: **explicitly define the duplicate outcome**, rather than just declaring an interceptor bean.

### 11.2. Correctness of Key Encoding

Joining three fields with `:` is only safe if the contract guarantees they cannot contain the delimiter, or if escaping/length-prefixing is used. In real systems, use a canonical key codec, a collision-free value object encoding, or unique database columns. Never use `tenantId + ":" + eventId` without a namespace and encoding policy.

### 11.3. Store Durability

`SimpleMetadataStore` exists only in memory. After a restart, the “seen” key is gone, so redeliveries may execute again. Production requires an appropriate persistent/concurrent store, yet **a durable marker still does not eliminate the crash window between the marker and the side effect**.

## 12. Simple Selector Unit Test

Before running a full integration test, you can verify the selector's atomic behavior in one JVM:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MetadataStoreSelectorTest {

    @Test
    void firstAcceptWritesMarkerBeforeAnyBusinessAction() {
        SimpleMetadataStore store =
                new SimpleMetadataStore();

        MetadataStoreSelector selector =
                new MetadataStoreSelector(
                        message -> "invoice-payment:" +
                                message.getPayload(),
                        store);

        Message<String> event =
                MessageBuilder.withPayload("evt-1001").build();

        assertTrue(selector.accept(event));

        // Selector already wrote metadata even though no handler ran.
        assertNotNull(store.get("invoice-payment:evt-1001"));

        // Second accept call is treated as duplicate.
        assertFalse(selector.accept(event));
    }
}
~~~

This is direct proof: `MetadataStoreSelector` writes the key when `accept` succeeds, **without waiting for the business action**. Business logic must handle the consequences if a worker dies in between.

## 13. Integration Test: Duplicates Do Not Reach the Handler

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PreMarkIdempotencyConfiguration.class)
class PreMarkIdempotencyFlowTest {

    @Autowired
    @Qualifier("payments.in")
    MessageChannel input;

    @Autowired
    InvoiceEventHandler handler;

    @Test
    void discardsRedeliveryBeforeCallingTargetHandler() {
        InvoicePaymentConfirmed event =
                new InvoicePaymentConfirmed(
                        "tenant-a",
                        "payment-provider",
                        "evt-pay-1001",
                        "INV-1001",
                        25000,
                        "verified-fingerprint");

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertEquals(1, handler.invocationCount());
    }
}
~~~

This test verifies **Spring Integration advice wiring** and the duplicate discard path. It **does not** prove business logic committed, because the handler only increments a counter; nor does it test restarts or multi-instance setups. Use distinct event IDs per test or isolate the Spring context if tests share a `MetadataStore`.

### 13.1. Testing When the Handler Throws an Error

Consider a fake handler:

~~~java
public void apply(InvoicePaymentConfirmed event) {
    throw new IllegalStateException("DB_TEMPORARILY_UNAVAILABLE");
}
~~~

With a mark-before selector and a persistent marker outside the business transaction rollback, the message **already has a marker before the handler throws**. A retry using the same key risks being discarded, **losing the business action**. This failure test matters more than a duplicate-count test.

### 13.2. Do Not Treat the Duplicate Header as “DONE”

If discard is not configured, a handler may receive `duplicateMessage=true`. However, the marker may have been written **before** a failed attempt. The duplicate header only indicates the selector saw the key earlier, **not that the prior attempt succeeded**. For critical business operations, query reliable **business outcome state** instead of unconditionally discarding.

## 14. When Is Standalone Mark-Before Acceptable vs. Not?

| Scenario | Acceptable? | Why |
|---|---|---|
| Rebuildable cache warm-up | Possibly | Lost work is recovered by another job |
| Best-effort metrics emission | Possibly | Duplicates/loss carry separate trade-offs |
| Data sync with periodic reconciliation | Conditionally | Requires recovery process |
| Crediting paid amounts | No, if only using a seen marker | Can lose payments |
| Debiting an account | No | Severe financial consequences |
| Sending confirmation email | Weigh trade-off | Avoids duplicates yet can drop emails |
| Creating a shipment | Not marker-only | Requires idempotent API or state machine |
| Writing events to local database | Should be transactional | Marker and write can commit together |

**Explicitly state business semantics:** is loss acceptable? Can it be replayed? Does the target system support idempotency keys? Do we need to know whether the outcome succeeded? A single Boolean `seen` cannot answer these questions.
## 15. One Database: Marker and Business Action in the Same Transaction

When both the marker and the business change reside in **the same relational database**, the strongest approach is typically:

1. Open **one database transaction**.
2. Use a unique constraint to claim `(tenantId, sourceId, eventId)`.
3. If the key already exists, compare the fingerprint, read the outcome, and **do not update business state again**.
4. If the key is new, execute the business mutation **inside the same transaction**.
5. Commit both the marker and the business mutation **together**.
6. ACK the broker per delivery policy **after the transaction succeeds**.

~~~mermaid
flowchart TD
    IN["Event redelivery"] --> TX["BEGIN DB TRANSACTION"]
    TX --> INSERT{"INSERT dedup key with UNIQUE"}
    INSERT -->|"Key exists"| CHECK["Compare fingerprint / load result"]
    CHECK --> EXIST["Return existing outcome"]
    INSERT -->|"New key"| WRITE["UPDATE business state"]
    WRITE --> COMMIT["COMMIT marker + business state"]
    EXIST --> ACK["ACK per delivery policy"]
    COMMIT --> ACK
~~~

**Critical point:** at the SQL level, `INSERT marker` may execute **before** `UPDATE business`, yet **the marker is never committed separately**. If the UPDATE fails and the transaction rolls back, the marker **also rolls back**. There is no partial state where the marker committed while the business action did not within the same transaction.

### 15.1. Illustrative PostgreSQL DDL

~~~sql
CREATE TABLE invoice_balance (
    tenant_id         VARCHAR(80) NOT NULL,
    invoice_id        VARCHAR(160) NOT NULL,
    paid_minor_units  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, invoice_id),
    CHECK (paid_minor_units >= 0)
);

CREATE TABLE processed_payment_event (
    tenant_id         VARCHAR(80) NOT NULL,
    source_id         VARCHAR(80) NOT NULL,
    event_id          VARCHAR(160) NOT NULL,
    request_hash      VARCHAR(128) NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_id, event_id)
);
~~~

`processed_payment_event` serves as both the dedup ledger and proof that a transaction committed. To replay the exact receipt from the first request, store the result or a reference to the business record as well.

### 15.2. Java Service with `@Transactional`

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalInvoicePaymentService {

    private final JdbcTemplate jdbc;

    public TransactionalInvoicePaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyOutcome apply(
            InvoicePaymentConfirmed event) {

        // Fingerprint is computed and verified at ingress.
        String hash = event.payloadFingerprint();

        int claimed = jdbc.update(
                """
                INSERT INTO processed_payment_event
                    (tenant_id, source_id, event_id, request_hash)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, source_id, event_id)
                DO NOTHING
                """,
                event.tenantId(),
                event.sourceId(),
                event.eventId(),
                hash);

        if (claimed == 0) {
            String previousHash = jdbc.queryForObject(
                    """
                    SELECT request_hash
                    FROM processed_payment_event
                    WHERE tenant_id = ?
                      AND source_id = ?
                      AND event_id = ?
                    """,
                    String.class,
                    event.tenantId(),
                    event.sourceId(),
                    event.eventId());

            if (!hash.equals(previousHash)) {
                throw new IllegalStateException(
                        "SAME_KEY_DIFFERENT_PAYLOAD");
            }

            return ApplyOutcome.ALREADY_APPLIED;
        }

        int updated = jdbc.update(
                """
                UPDATE invoice_balance
                SET paid_minor_units = paid_minor_units + ?
                WHERE tenant_id = ?
                  AND invoice_id = ?
                """,
                event.paidMinorUnits(),
                event.tenantId(),
                event.invoiceId());

        if (updated != 1) {
            throw new IllegalStateException(
                    "INVOICE_NOT_FOUND");
        }

        return ApplyOutcome.APPLIED;
    }
}
~~~

Output enum:

~~~java
public enum ApplyOutcome {
    APPLIED,
    ALREADY_APPLIED
}
~~~

This example uses **PostgreSQL** (`ON CONFLICT DO NOTHING` syntax), Spring JDBC, and a `PlatformTransactionManager` bound to the same `DataSource`. For other dialects, insert-if-absent syntax varies. Top-level `public` types must reside in their own source files.

Core points:

- `processed_payment_event` has a unique key identifying the event.
- The marker and `invoice_balance` are updated in **the same DB transaction**.
- If UPDATE fails, both the marker and the business write roll back.
- Retries after commit encounter the duplicate and do not credit again.
- Two workers with the same key are arbitrated by the **DB's unique constraint**, not lockless `SELECT exists`.

**Real transactions must be configured properly:** the `@Transactional` method must be invoked through a Spring proxy/transaction interceptor, not via self-invocation expecting the annotation to work magically. Verify rollback rules and the shared database transaction manager; run concurrency tests against a real DB.

### 15.3. Crash Mid-Transaction

~~~text
BEGIN
  INSERT marker (uncommitted)
  UPDATE invoice (uncommitted)
  CRASH
ROLLBACK
~~~

After restart, redelivery can claim the key because the marker **never committed**. When the transaction commits successfully, both the marker and the business effect appear together. This **does not** span external HTTP calls or brokers outside the transaction.

### 15.4. Avoid Letting Marker-Only Advice Block Retries Before the Transaction

If the flow has an out-of-transaction `MetadataStoreSelector` with an independent marker, the advice may store `seen` while the service rolls back. Retries get discarded **before reaching the business transaction**. For financial operations, prefer **DB unique ledgers + transactions** rather than using standalone pre-marking as the sole gate. Advice can reduce load once a `SUCCEEDED` outcome is known, but must not block attempts needing recovery.

## 16. Testing Rollbacks and Duplicates with Transactions

Mocking repositories or using `AtomicInteger` alone cannot prove transaction atomicity. Critical tests should use a database with a real unique constraint and a production-like transaction manager.

| Scenario | Action | Expectation |
|---|---|---|
| New event | Send `evt-pay-1001` | 1 marker, balance incremented once |
| Redelivery | Resend same key/fingerprint | Balance does not increase again |
| Same key, changed payload | Change amount and fingerprint | Conflict, no credit applied |
| Missing invoice | INSERT marker then UPDATE 0 rows | Transaction rolls back marker |
| Retry after rollback | Create invoice and resend | Applied cleanly once |
| Two workers with same key | Two concurrent transactions | Only one valid mutation |
| Crash before commit | Drop connection | No half-marker/half-business write |
| Commit succeeded, lost ACK | Redelivery | Duplicate recognized |

### 16.1. JUnit Scenario Testing Rollback

~~~java
@Test
void failedBusinessWriteDoesNotLeaveMarker() {
    InvoicePaymentConfirmed event =
            testPayment("evt-rollback-1", "INV-MISSING");

    assertThrows(IllegalStateException.class,
            () -> invoiceService.apply(event));

    assertEquals(0, processedEventCount(
            event.tenantId(),
            event.sourceId(),
            event.eventId()));

    createInvoice("INV-MISSING");

    assertEquals(ApplyOutcome.APPLIED,
            invoiceService.apply(event));

    assertEquals(1, processedEventCount(
            event.tenantId(),
            event.sourceId(),
            event.eventId()));
}
~~~

This is a **test recipe**: helpers `testPayment`, `processedEventCount`, `createInvoice`, and fixture `invoiceService` must be implemented per project. To test real rollbacks, avoid wrapping the entire test in an outer transaction that changes commit timing compared to production.

### 16.2. Concurrency Test

Launch two workers with separate connections/transactions, the same `(tenantId, sourceId, eventId)`, and the same fingerprint. Use a barrier so both attempts start together, then assert in **the database post-commit** that only one marker and one business mutation exist. `synchronized` inside a single instance does not prove multi-JVM behavior.

## 17. Side Effects Outside the Database: PROCESSING and SUCCEEDED

When the business action is an HTTP call to a payment API, shipping API, or email provider, the local metadata store and the remote action **do not automatically commit in one transaction**.

A Boolean `seen=true` marker lacks sufficient information. Design a **state machine**:

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key
    PROCESSING --> SUCCEEDED: Remote confirmed
    PROCESSING --> RETRYABLE: Known transient error
    PROCESSING --> UNKNOWN: Lost response / timeout
    RETRYABLE --> PROCESSING: Safe retry
    UNKNOWN --> RECONCILING: Query remote
    RECONCILING --> SUCCEEDED: Remote confirmed
    RECONCILING --> PROCESSING: Confirmed not executed
    PROCESSING --> FAILED_FINAL: Non-retryable failure
~~~

Illustrative domain types:

~~~java
import java.time.Instant;

public enum OperationState {
    PROCESSING,
    SUCCEEDED,
    RETRYABLE,
    UNKNOWN,
    FAILED_FINAL
}

public record ProcessingRecord(
        EventDedupKey key,
        String fingerprint,
        OperationState state,
        String ownerToken,
        Instant leaseUntil,
        int attempt,
        String remoteOperationId,
        String businessReceipt
) {}
~~~

`public` types in code blocks require separate source files; this is an example domain model, not a built-in Spring Integration API.

### 17.1. Practical Workflow

1. **Claim the key** with atomic insert-if-absent/CAS.
2. Persist `PROCESSING` along with `ownerToken` and `leaseUntil`.
3. Call the remote API with a **stable idempotency key** if supported.
4. Once definitively confirmed successful, CAS state to `SUCCEEDED` and store the receipt.
5. If a timeout leaves remote execution uncertain, transition to `UNKNOWN` and **reconcile**.
6. Never blindly retry a non-idempotent side effect.
7. ACK/requeue the message per durable state and delivery contract.

### 17.2. Duplicates Arriving in Different States

| Current State | Suggested Behavior |
|---|---|
| `SUCCEEDED` | Return receipt/no-op and ACK |
| `PROCESSING` with active lease | `IN_PROGRESS`, wait or retry later |
| `PROCESSING` with expired lease | Take over via CAS, inspect outcome |
| `UNKNOWN` | Reconcile using remote idempotency key |
| `RETRYABLE` | Retry with backoff and ownership |
| `FAILED_FINAL` | Return stored error or reject per contract |
| Same key with different fingerprint | Reject conflict, never run as new |

**Never assume a `PROCESSING` duplicate equals `SUCCEEDED`** and ACK it as completed. It may be a stuck task.

## 18. Leases, CAS, and Fencing

A worker can die after claiming `PROCESSING`. Setting `leaseUntil` allows another worker to take over upon expiry, yet you must prevent two workers from simultaneously causing side effects.

~~~text
t0: Worker A claims, lease 60s
t1: Worker A hangs
t2: Worker A's lease expires
t3: Worker B takes over
t4: Worker A wakes up and keeps sending remote requests
~~~

A lease **is not enough** to guarantee mutual exclusion if worker A continues running after losing its lease.

### 18.1. Ownership-Based CAS

~~~sql
UPDATE processing_command
SET owner_token = :newOwner,
    lease_until = :newLeaseUntil,
    attempt = attempt + 1
WHERE tenant_id = :tenantId
  AND command_id = :commandId
  AND state = 'PROCESSING'
  AND lease_until < CURRENT_TIMESTAMP
  AND owner_token = :oldOwner;
~~~

Only the worker updating **exactly one row** via CAS becomes the new owner. Upon completion, the `PROCESSING → SUCCEEDED` CAS must verify the owner/version has not changed.

### 18.2. Fencing Tokens

When supported by the downstream resource, pass a **monotonically increasing fencing number**. The resource rejects commands from workers presenting an older fencing number. If the remote resource lacks fencing support, use a **remote idempotency key** or reconciliation. A UUID `ownerToken` only distinguishes internal workers; it does not block late remote side effects by itself.

## 19. Remote API Idempotency

For payments or shipment creation, use the target system's idempotency contract when available:

~~~text
POST /charges
Idempotency-Key: tenant-a/charge-cmd-1001

{
  "accountId": "ACC-1001",
  "amountMinorUnits": 25000,
  "currency": "VND"
}
~~~

This is an **illustrative protocol**, not a claim that every API supports this header. Verify the provider's key scope, retention, same-key/different-body handling, pending responses, and replay behavior.

### 19.1. A Lost Response Does Not Prove Failure

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant R as Remote API
    participant S as State Store

    C->>S: PROCESSING
    C->>R: POST with Idempotency-Key K
    R-->>C: Remote commit succeeds
    Note over C: Response lost due to network
    C->>S: UNKNOWN
    C->>R: Query status or retry K per contract
    R-->>C: Receipt of completed operation
    C->>S: SUCCEEDED + receipt
~~~

Never do this:

~~~java
try {
    remoteCharge();
} catch (Exception ex) {
    metadataStore.remove(key); // WRONG if remote already committed.
    throw ex;
}
~~~

The exception may be a timeout **after** the remote system executed. Removing the marker immediately allows a retry to duplicate the effect. If the API supports neither idempotency nor status queries, use reconciliation/manual intervention when the outcome is unknown.

## 20. Transactional Outbox and Inbox

If the business action involves **writing to the local DB and publishing an event to a broker**, the following flow has a crash window:

~~~text
UPDATE database -> COMMIT -> broker.publish()
~~~

Crashing after the DB commit but before publishing loses the event. **Transactional outbox** solves this by writing the outbound event in the same local transaction.

~~~mermaid
flowchart LR
    IN["Incoming event"] --> TX["DB Transaction"]
    TX --> M["Insert dedup/inbox row"]
    TX --> B["Update business state"]
    TX --> O["Insert outbox event"]
    O --> COMMIT["COMMIT"]
    COMMIT --> PUB["Outbox publisher"]
    PUB --> BROKER["Broker"]
~~~

Simple SQL:

~~~sql
CREATE TABLE outbox_event (
    id            UUID PRIMARY KEY,
    aggregate_id  VARCHAR(160) NOT NULL,
    event_type    VARCHAR(120) NOT NULL,
    payload_json  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMPTZ NULL
);
~~~

When the inbox marker, business update, and outbox entry share a transaction, they commit atomically. The outbox publisher can still **send duplicates** if it publishes and crashes before marking sent, so downstream consumers must also be idempotent.

~~~text
Broker input (at least once)
  -> Inbox unique key + local DB transaction
  -> Business mutation + outbox record
  -> Outbox publisher
  -> Broker (may redeliver)
  -> Downstream idempotent receiver
~~~

There is no “system-wide exactly-once” merely from using an interceptor or outbox in one service.

## 21. Broker ACK: Should Occur After Business Commit

### 21.1. ACK Before Commit

~~~text
ACK broker -> business action -> DB commit
~~~

Crashing after ACK but before DB commit may prevent the broker from redelivering: **lost work**.

### 21.2. ACK After Commit

~~~text
DB commit -> ACK broker
~~~

Crashing after commit but before ACK can cause redelivery: **dedup/idempotency is required**, yet business state is already protected by the unique inbox row and local transaction.

### 21.3. Things to Check

- Is the broker/adapter using auto-ack or manual-ack?
- Which listener attempt is the ACK bound to?
- Does the transaction truly commit before ACK?
- Can the consumer receive the message again after a rebalance/partition shift?
- Are `SUCCEEDED` duplicates ACKed?
- Do `PROCESSING` duplicates need a retry delay or pending queue?
- Do DLQ replays preserve the original idempotency key?

`MessageChannel.send()==true` does not prove the DB committed or the broker ACK succeeded.
## 22. Testing with Fault Injection

Do not just send the same message twice while the system is healthy. A reliable test suite must actively inject failures right at the boundary points.

| Failure Point | How to Simulate | Standalone Mark-Before | Atomic DB Transaction |
|---|---|---|---|
| Before claim | Store unavailable | Must not run action when claim is unclear | Roll back / no effect |
| After claim, before action | Handler crashes | Marker may cause wrongful skip | Marker rolls back if transaction uncommitted |
| During action | UPDATE throws exception | Marker may remain | Neither mutation nor marker persists |
| After action, before marker | Crash | Mark-after may cause duplicates | No half-commit within one transaction |
| After commit, before ACK | Broker redelivery | Depends on marker/outcome | Unique ledger blocks duplicate effect |
| Two workers on same key | Synchronize with barrier | Needs CAS | Unique constraint arbitrates |
| Remote commit, lost response | Timeout | Outcome uncertain | Local DB does not cover remote |
| Lease expired, old worker returns | Pause/resume worker | May duplicate side effects | Needs fencing/remote idempotency |
| Replay after TTL | Delete marker and resend | May re-execute | Retention/business uniqueness policy |

### 22.1. Test Illustrating the Mark-Before Risk

~~~text
Arrange:
  MetadataStore empty
  Fake handler crashes before DB write

Act:
  send event -> selector writes marker -> handler fails
  redeliver event with same key

Assert:
  marker exists
  retry is discarded if advice uses nullChannel
  business effect still has not occurred
~~~

This test proves a **design flaw**, not recommended behavior. In production, a safe test must **fail** if a critical event has not executed yet was ACKed/dropped as if completed.

### 22.2. Test Illustrating the Mark-After Risk

~~~text
Arrange:
  Business action and marker use two independent commits

Act:
  business action succeeds
  crash before DONE marker
  redeliver same event

Assert:
  if action is not idempotent, business action is invoked a second time
~~~

You cannot fix this bug simply by calling `MetadataStore.put` faster after the handler. A crash can always intervene between two independent commits.

### 22.3. Transaction Commit Tests

~~~text
1. Create invoice_balance(initial=0).
2. apply(event) -> paid=25000, processed_event=1.
3. apply(event) a second time -> paid=25000, processed_event=1.
4. apply(same key, different fingerprint) -> conflict.
5. Force UPDATE to fail after INSERT -> marker rolls back.
6. Retry after fixing data -> updates cleanly once.
7. Run two workers concurrently -> single mutation.
8. After commit, simulate lost ACK -> replay does not increment balance.
~~~

These test cases should run against a real database or Testcontainers with a production-compatible DB; mocking `JdbcTemplate` is insufficient to prove transactions/unique constraints.

## 23. Returning Consistent Results to Gateways/APIs

An HTTP API with `Idempotency-Key` typically needs to **return the same business response** for duplicate requests, not merely prevent duplicate side effects.

Contract example:

~~~text
POST /orders/ORDER-101/submit
Idempotency-Key: cmd-1001

First time:
  201 Created
  orderStatus=SUBMITTED

Retry same key + same body:
  201 Created
  same orderId/result (per contract)

Retry same key + different body:
  409 Conflict or contract error

Key is PROCESSING:
  202 Accepted + status URL
  or retryable response per contract
~~~

The HTTP status codes in the example are **design choices**, not mandatory rules for every API. If response replay is needed, store the receipt/result or resource reference **in the same transaction as business state**.

Configuring `IdempotentReceiverInterceptor` solely to send duplicates to `nullChannel` can cause **Gateway timeouts** if the caller expects a reply. Distinguish messages that must not be reprocessed from requests that still require a response.

### 23.1. Canonical Fingerprinting

You do not necessarily hash raw JSON bytes if field ordering or whitespace can vary while business meaning stays equivalent. Canonicalize significant fields: operation, tenant, target resource, minor-unit amount, currency, and version. Exclude `traceId`, retry timestamps, or values that change on each delivery.

### 23.2. PROCESSING Duplicates Must Never Pretend Success

If the first attempt is still running:

- You can return `IN_PROGRESS` or a tracking URL.
- You can short-wait until the first attempt finishes.
- You can retry after backoff.
- Never return `SUCCEEDED` without a confirmed business receipt.
- Never let two attempts both call remote payment merely because requests arrived close together.

## 24. Retention and TTL of Idempotency Markers

Keeping markers forever carries storage costs. Expiring markers too early allows replays of old events to be processed as new events.

~~~text
t0: message published
t0+30 min: normal retry
t0+7 days: replay from DLQ
t0+30 days: manual recovery/reconciliation
~~~

If the TTL is only one hour, an event replayed after seven days can bypass the dedup store.

### 24.1. Durations to Consider

- Broker retention and DLQ retention.
- Possibility of manual replay.
- How long the remote API retains idempotency keys.
- Business audit/compliance.
- Whether events can be re-emitted from history.
- Severity if a side effect executes an extra time.
- Metadata store cost and archiving/tombstone capabilities.

### 24.2. Deleting DONE Markers Requires Another Layer of Protection

If cleanup deletes `DONE` markers, you need a long-lived business uniqueness constraint or a tombstone that still blocks old replays. Purging to optimize store size must never alter the fact that “this event already affected the invoice”.

### 24.3. Tenant Isolation

Keys must be scoped by tenant/source/operation. Never let a client self-declare a `tenantId` different from the authenticated principal to **wrongly block** another tenant's events or query unauthorized outcomes. Authorization must sit at the trust boundary, not merely in key-derivation logic.

## 25. Observability: Separating Claim and Commit

| Metric | What to Observe |
|---|---|
| `idempotency_received_total` | Messages received |
| `idempotency_first_claim_total` | New key claims |
| `idempotency_duplicate_total` | Keys already seen |
| `idempotency_processing_total` | Tasks in PROCESSING |
| `idempotency_succeeded_total` | Confirmed business actions |
| `idempotency_retryable_failure_total` | Retryable errors |
| `idempotency_unknown_total` | Uncertain outcomes |
| `idempotency_fingerprint_conflict_total` | Same key, different content |
| `idempotency_lease_expired_total` | Expired leases |
| `idempotency_takeover_total` | Worker takeovers |
| `idempotency_reconciliation_total` | External action reconciliations |
| `idempotency_business_commit_latency_seconds` | Business commit latency |

Log example:

~~~text
flow=invoice-payment
eventType=InvoicePaymentConfirmed
eventId=evt-pay-1001
tenant=tenant-a
idempotencyState=PROCESSING
claimResult=ACQUIRED
businessCommit=PENDING
traceId=trace-1001
~~~

**`claimResult=ACQUIRED` does not mean the business action finished.** Log confirmed outcomes at the exact business boundary, such as after DB commit or receiving a trusted remote receipt.

Never put `eventId`, account IDs, customer IDs, or idempotency keys into high-cardinality metric labels. Where specific logs require identifiers, enforce access control, redaction, and proper retention.

### 25.1. Signals That Warrant Alerts

- `PROCESSING` exceeding its lease without takeover/reconciliation.
- Spikes in `UNKNOWN` after remote API timeouts.
- `SUCCEEDED` marker with no corresponding business record.
- Committed business record with no marker.
- Same key associated with multiple fingerprints.
- Duplicate spikes after broker rebalances.
- Excessive latency between claim and action.
- Multiple workers on the same key with stale owners/versions.

## 26. Common Anti-Patterns

| Mistake | Consequence | Fix |
|---|---|---|
| Marking DONE before calling business action | Crash → lost work | `PROCESSING` + recovery or atomic transaction |
| Completing business work then committing separate marker | Crash → duplicate effect | Atomic transaction / remote idempotency |
| Assuming interceptor auto-drops duplicates | Handler may still run with duplicate header | Configure discard/throw or inspect header |
| Treating `duplicateMessage` as `SUCCEEDED` | Prior attempt may have failed | Check durable outcome |
| Using `get` then `put` without CAS | Both workers execute | Unique constraint / CAS |
| Key = `MessageHeaders.ID` | Redeliveries have new IDs | Stable event/command ID |
| Key = `invoiceId` | Blocks multiple valid payments on same invoice | Scope by event/command |
| Skipping same-key different-payload requests | Masks conflicts or attacks | Fingerprint validation |
| Using `SimpleMetadataStore` for production dedup across restarts | Markers lost on restart | Persistent metadata / DB inbox |
| Persistent marker with remote side effect | Crash window still exists | Remote idempotency / reconciliation |
| Deleting marker inside timeout catch block | Remote may have committed | `UNKNOWN` / reconcile |
| ACKing before business commit | Lost work | ACK after commit per adapter |
| TTL shorter than replay window | Old events re-run | Retention / tombstones |
| Freely resending remote requests on lease expiry | Old worker may still be running | Fencing / remote idempotency |
| Testing only by sending a duplicate twice | Misses crash bugs | Fault injection / concurrency tests |
| `HashSet` in a single JVM | Does not protect multiple instances | Shared / DB uniqueness |
| Dropping API duplicates without replying | Gateway timeouts / inconsistent responses | Stored receipt / reply path |
| Assuming local transactions protect remote side effects | Not atomic across services | Outbox / inbox / idempotent API |

## 27. Practice Exercises

**Exercise 1 — Crash matrix.** Map crash points before marker, after marker, after business action, and before broker ACK; compare mark-before vs. mark-after.

**Exercise 2 — Selector.** Build a `MetadataStoreSelector` with `SimpleMetadataStore`; prove `accept()` writes the key before the handler runs.

**Exercise 3 — Default advice.** Omit the discard channel, let the handler accept `Message<?>`, and inspect `duplicateMessage`; explain why duplicates still reach the handler.

**Exercise 4 — Discard.** Add `nullChannel`; send an event twice and verify the handler runs once. Force the first attempt to fail and redeliver to expose lost work.

**Exercise 5 — Key scope.** Use `invoiceId` as the key and send two valid payments; explain why it wrongly blocks the second.

**Exercise 6 — Fingerprint conflict.** Same key with two different amounts: must reject rather than silently deduplicating.

**Exercise 7 — Transaction.** Use a PostgreSQL unique ledger and `@Transactional`; test that redelivering an event does not increment balance twice.

**Exercise 8 — Rollback.** Make the invoice UPDATE fail after marker INSERT; confirm the marker rolls back and retries still succeed.

**Exercise 9 — Concurrency.** Two connections concurrently insert the same key; verify only one mutation occurs.

**Exercise 10 — Lost ACK.** Commit the DB then simulate a lost ACK; redelivery must not cause a new side effect.

**Exercise 11 — Remote timeout.** The API executed the charge while the response was lost; use a remote idempotency key/lookup to reconcile.

**Exercise 12 — Lease takeover.** Worker A's lease expires, B takes over, A wakes up; identify where fencing is required.

**Exercise 13 — Outbox.** Write inbox, business state, and outbox in the same DB transaction. Have the publisher send successfully without marking sent, and verify downstream dedup.

**Exercise 14 — Gateway.** Return consistent replies for `SUCCEEDED` duplicates, `IN_PROGRESS`, and same-key-different-body conflicts.

**Exercise 15 — TTL.** Replay from DLQ after one week while marker TTL is one day; design safe retention.

**Exercise 16 — Monitoring.** Emit metrics/logs for claims, commits, duplicates, `UNKNOWN`, reconciliations, stale `PROCESSING`, and fingerprint conflicts.

### Self-Check Questions

1. Does seeing a message mean the business logic committed?
2. Which crash window loses work with mark-before?
3. Which crash window duplicates effects with mark-after?
4. Which operation does `MetadataStoreSelector` use to accept a new key?
5. What does `putIfAbsent` guarantee, and what does it not guarantee?
6. Does `IdempotentReceiverInterceptor` drop duplicates by default?
7. When is a discard channel or throwing an exception needed?
8. Does `duplicateMessage=true` prove the prior attempt `SUCCEEDED`?
9. Why is `MessageHeaders.ID` unsuitable for many retry scenarios?
10. Why can `invoiceId` be an overly broad idempotency key?
11. What must happen for the same key with a different fingerprint?
12. Which crash windows does a single shared transaction protect against?
13. Does inserting the marker before updating in the same transaction mean the marker commits first?
14. Why must `PROCESSING` and `SUCCEEDED` be distinguished?
15. Should a duplicate arriving during `PROCESSING` be ACKed as `DONE`?
16. Does an expired lease stop an old worker from calling an API?
17. Does a remote timeout prove the action never occurred?
18. Why should you never immediately remove the marker inside a timeout catch block?
19. What problem does an outbox solve when writing to the DB and publishing?
20. Why can an outbox publisher still send duplicates?
21. How can ACKing before commit cause lost work?
22. Which replay sources must marker TTL consider?
23. What must an HTTP duplicate return besides skipping re-execution?
24. Which test proves unique constraints and rollbacks work?
25. Why is testing only happy-path duplicates insufficient?

## 28. Implementation Checklist

- [ ] Duplicates are defined by a stable business operation.
- [ ] Keys are scoped by tenant/source/operation and preserved across replays.
- [ ] Fingerprint validation exists for same-key, different-payload requests.
- [ ] `RECEIVED`, `PROCESSING`, `SUCCEEDED`, and `UNKNOWN` are distinguished.
- [ ] A `seen` marker is never treated as proof that business work committed.
- [ ] When sharing one database, marker and side effect use **one transaction**.
- [ ] The database has unique constraints and concurrency tests.
- [ ] For remote side effects, idempotency keys or reconciliation exist.
- [ ] Never use lockless `get+put` without CAS across multiple workers.
- [ ] `IdempotentReceiverInterceptor` is attached to the right handler endpoint.
- [ ] Duplicate path is explicit: header, discard, or exception.
- [ ] Never drop `PROCESSING` duplicates as `SUCCEEDED` without recovery.
- [ ] `MetadataStore` provides appropriate atomicity and durability.
- [ ] Bounded retries, backoff, DLQ, and error flows are defined.
- [ ] Never blindly delete keys when remote outcomes are `UNKNOWN`.
- [ ] Broker ACKs align with the proper transaction/outcome.
- [ ] Leases, CAS, fencing, or remote idempotency guard takeovers.
- [ ] Marker retention covers the replay window or domain uniqueness protects long-term.
- [ ] Downstream handles duplicates idempotently when outbox/broker redelivers.
- [ ] Tests cover crashes before action, after action, before ACK, and concurrency.
- [ ] Tests cover rollbacks, fingerprint conflicts, remote timeouts, and lease expiry.
- [ ] Metrics separate claims, duplicates, commits, `UNKNOWN`, and failures.
- [ ] No PII or high-cardinality keys appear in metric labels.
- [ ] Critical side effects have reconciliation and an audit trail.

## 29. Summary

**Marking messages before or after the business action** is not merely a Spring Integration syntax choice; it is a decision about **crash recovery, delivery guarantees, and business correctness**.

If you mark before and **commit the marker separately**, a crash can cause the system to **lose work**. If you execute the business action first and **commit a separate marker afterward**, a crash can cause **the side effect to execute twice**. `MetadataStoreSelector` writes markers via `putIfAbsent` when accepting a new key, **before the handler runs**, so you must understand its crash window. In addition, `IdempotentReceiverInterceptor` **does not automatically drop duplicate messages by default**: it can set `duplicateMessage=true` and still invoke the handler unless discard or exception throwing is configured.

For side effects **within the same database**, use a unique idempotency key, marker, and business mutation **in one transaction**. For side effects **in external systems**, design `PROCESSING/SUCCEEDED/UNKNOWN`, recoverable CAS/leases, remote idempotency, or reconciliation. When both writing to the DB and emitting broker events, use a transactional outbox and idempotent consumers. Always align ACKs with confirmed outcomes, retain markers long enough, and test real crash points.

These principles allow Idempotent Receiver to work alongside Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation in **SPRING_INTEGRATION_PATTERN** to build flows that are loosely coupled, extensible, observable, and verifiable.

### References

- Spring Integration Reference — Idempotent Receiver: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Integration Reference — Metadata Store: https://docs.spring.io/spring-integration/reference/meta-data-store.html
- Spring Integration Reference — Handling Message Advice: https://docs.spring.io/spring-integration/reference/handler-advice.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — IdempotentReceiverInterceptor: https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html
- Spring Integration API — MetadataStoreSelector: https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html
- Spring Integration API — ConcurrentMetadataStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html
- Spring Integration API — SimpleMetadataStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/SimpleMetadataStore.html
- Spring Framework Reference — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- PostgreSQL — INSERT ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
