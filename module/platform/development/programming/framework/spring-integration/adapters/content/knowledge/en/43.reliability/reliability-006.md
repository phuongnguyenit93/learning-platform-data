# Idempotent Receiver for Inbound Adapters

**Chapter:** Reliability  
**Lesson:** Idempotent receiver for inbound adapters  
**Module:** Spring Integration Adapters  
**Scope:** Designing flows that receive messages from files/SFTP, HTTP, JMS, AMQP, Kafka, or databases, detect duplicates, and protect business tasks from repeated side effects. Covers inbound adapters, gateways, pollers, `MessageChannel`, Spring Integration Idempotent Receiver, `MetadataStore`, retry, acknowledgement, transactions, dead-lettering, and connection lifecycles.

## 1. Why can an inbound adapter receive the same message multiple times?

An inbound adapter converts events or data from an external system into a **Spring `Message`** and places it onto a **`MessageChannel`**. In practice, many sources only guarantee **at-least-once** delivery: a message can arrive more than once.

Examples:

- **SFTP/File:** Poller sees an old file after restart, metadata filter is reset, a file is re-uploaded, or the same record appears across two imports.
- **HTTP:** Client times out after the server already processed the request and resends the same operation.
- **JMS/AMQP:** Consumer rolls back or connection drops before acknowledgement, causing the broker to redeliver.
- **Kafka:** Consumer finishes processing before committing offsets and receives the record again after a rebalance.
- **JDBC:** Poller re-reads rows not yet marked processed, or a transaction rolls back.
- **Batch/integration:** An intentional replay enters through the same path as the initial message.

If the handler calls an order-creation API, charges money, saves reports, or writes files, duplicate processing can cause **invalid side effects**. The **Idempotent Receiver** pattern solves this so that *the same business operation can be received multiple times without creating unintended extra business effects*.

### 1.1. Running example

An application receives orders from three channels:

~~~text
SFTP inbound polling --+
                      +--> normalize --> inboundOrdersChannel
HTTP inbound gateway -+                          |
                                                 v
                                idempotency check / guard
                                                 |
                                   order business handler
                                                 |
                                    database + partner API
~~~

An order has `tenantId=T42`, `orderId=ORD-971`. Receiving two messages representing **the same order-creation operation** must not create two records or call the partner twice uncontrollably.

However, if the business has **two legitimately distinct operations** on the same order (for example, create and cancel, or an update version 2), they must not be treated as duplicates merely because they share `orderId`. That is why **defining the idempotency key** matters more than the filter itself.

## 2. What is an Idempotent Receiver?

In enterprise integration patterns, **Idempotent Receiver** enables an endpoint to recognize and handle previously seen messages under a consistent policy. It can:

1. **Discard duplicates** before the handler creates side effects.
2. **Mark duplicates** so the handler takes an alternate branch.
3. **Return the stored result** of the previous execution, for request-reply systems with a result store.
4. **Reconcile uncertain states** instead of blindly dropping or replaying.

Business idempotency differs from filtering identical Java objects. Two Spring `Message` instances with different `id` headers can still represent the same order. Conversely, two events on the same aggregate can still be two valid operations.

### 2.1. Basic rule

For an **operation key `K`**, the desired state behavior is typically:

~~~text
first(K)     -> process or take ownership of processing K
duplicate(K) -> do not create extra business side effects on your own
new(K2)      -> process normally if it is a different operation
~~~

This is the business goal. A **metadata selector** only answers whether a key has been marked; end-to-end idempotency also depends on transactions, concurrency, target systems, and error policies.

### 2.2. How does idempotency differ from deduplication?

| Concept | Focus | Limitation |
| --- | --- | --- |
| **Deduplication** | Detecting deliveries with the same key | Does not itself prove the first execution succeeded |
| **Idempotent business operation** | Repeating the same operation without unintended business changes | Requires matching contracts/databases/downstream support |
| **Exactly-once processing** | Overall semantics where each operation has exactly one effect | Cannot be inferred from an inbound filter alone |
| **At-least-once delivery** | Source may resend to prevent message loss | Application must expect duplicates |
| **At-most-once delivery** | Avoids resends by accepting risk of message loss | Does not guarantee all business work executes |
| **Replay** | Controlled re-sending of an event/operation | Must distinguish valid replays from new events |

**Conclusion:** Idempotent Receiver is **one protective layer**; it usually needs to work together with unique constraints, transactional inbox/outbox, downstream idempotency keys, and reconciliation.

## 3. Where Idempotent Receiver sits in Spring Integration

Spring Integration has two control layers that are easy to confuse:

- **Source-level filter:** Selects which files or records the inbound adapter/poller accepts—such as *accept-once file filters*, persistent file filters, and metadata filters. These operate **at the source side**, depending on the adapter.
- **Message-level idempotent receiver:** Blocks or flags duplicates **after a message enters the flow**, close to the side-effecting handler. Related mechanisms include **`IdempotentReceiverInterceptor`**, **`MessageSelector`**, and **`MetadataStoreSelector`**.

Never assume a source filter replaces business checks, or that a handler idempotent receiver replaces managing broker checkpoints.

### 3.1. Flow diagram

~~~mermaid
flowchart LR
    SRC["File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC source"] --> ADP["Inbound adapter / gateway / poller"]
    ADP --> CH["MessageChannel"]
    CH --> KEY["Determine operation key"]
    KEY --> GUARD["IdempotentReceiverInterceptor / MessageSelector"]
    GUARD -->|New| HANDLER["Business handler"]
    GUARD -->|Duplicate| DUP["Discard / mark / cached result"]
    HANDLER --> DB["Database / external system"]
    HANDLER --> STATE["Processed state / inbox"]
    DUP --> AUD["Metrics / audit"]
    STATE --> AUD
~~~

A Spring Integration **advice** is attached to the **appropriate endpoint/handler**; simply declaring a bean does not protect all inbound adapters automatically. If parsing or another step causes side effects **before** the guard, those side effects can still repeat.

### 3.2. Where to place the guard

Identify the **first side effect**:

1. Receive message and read metadata.
2. Normalize the information needed to build the key.
3. Check/register the key with an appropriately atomic mechanism.
4. Execute the business handler or route duplicates.
5. Record the outcome and handle ack/checkpoint.

If data must be parsed just to extract the key, the parser needs its own error handling. If DB updates or HTTP calls happen before the guard, the idempotent receiver cannot protect those operations.

## 4. Related Spring Integration APIs

| Component | Role | Things to watch |
| --- | --- | --- |
| **`IdempotentReceiverInterceptor`** | Advice implementing the idempotent receiver pattern around a fitting handler | Must configure selector and duplicate behavior |
| **`MessageSelector`** | Decides whether a message is accepted or treated as duplicate | Key-identification logic must be well defined |
| **`MetadataStoreSelector`** | Uses a metadata store to select messages by key/value | Store must fit concurrency and durability needs |
| **`MetadataStore`** | Persists key/value state | In-memory stores do not survive restarts |
| **`ConcurrentMetadataStore`** | Supports atomic update operations per contract | Needs a distributed atomic backend when running across instances |
| **`MessageChannel`** | Delivers messages to handlers/duplicate routes | `DirectChannel` is not a durable broker by itself |
| **`MessageFilter`** | Another flow-level filter/routing option | Does not itself coordinate transactions with side effects |
| **`AcceptOnceFileListFilter`** | Filters already-seen files in inbound file adapters | Not equivalent to business-operation deduplication |
| **Persistent file filters** | Tracks files in an appropriate metadata store | Must choose keys and file-modification policies carefully |
| **`ErrorMessage` / `errorChannel`** | Routes processing errors | Does not decide ack/DLQ or business state automatically |

### 4.1. Important note on the duplicateMessage header

Depending on how **`IdempotentReceiverInterceptor`** is configured, a duplicate **may be marked with a header** such as `duplicateMessage` for downstream awareness rather than automatically being blocked from the handler. To **prevent the business handler from executing** on duplicates, explicitly configure **discard channel/rejection behavior** per your library version's API.

Do not write tests that merely assert the selector returns `false` and assume the business handler never ran. Test **actual handler invocations**.

### 4.2. Source file filters and message filters differ

~~~text
SFTP persistent filter:
    "Has remote file X already been accepted for download?"

Message-level idempotent receiver:
    "Has operation Y represented by a record inside file X
     already been processed per business contract?"
~~~

One file can contain 1,000 records; one record can fail while the remaining 999 succeed. File-level filtering cannot answer per-operation status.

## 5. Designing truly business-meaningful idempotency keys

An **idempotency key** is a stable identifier for *one business operation*, not necessarily a transport message identifier.

### 5.1. Comparing key strategies

| Key | Suitability | Issue |
| --- | --- | --- |
| **Spring `MessageHeaders.ID`** | Usually unsuitable for cross-delivery business dedupe | New messages typically get new IDs |
| **Freshly generated HTTP request ID** | Suitable only if caller reuses the exact same ID on retries | Callers generating new IDs defeat duplicate detection |
| **Kafka topic + partition + offset** | Useful for deduplicating **the transport record itself** | Republishing the same event gets a new offset |
| **`JMSMessageID` / broker delivery ID** | Useful across some redeliveries | Can change if republished through another broker |
| **File path + mtime/size** | Useful for filtering file versions | Insufficient per record or when content changes under same name |
| **Tenant + operation type + business ID + version** | Usually fits well-defined business flows | Avoid merging genuinely distinct operations |
| **Content hash** | Fits when payload equality defines duplication | Identical content may not mean identical intent; serialization changes alter hashes |

### 5.2. Example key for an order

~~~text
tenantId    = T42
operation   = CREATE_ORDER
orderId     = ORD-971
version     = 1

idempotencyKey = "order:create:v1:T42:ORD-971"
~~~

If the same order ID can emit **`UPDATE_ORDER:v2`**, it needs a different key. If the same `CREATE_ORDER` is replayed because the HTTP response was lost, the key must stay unchanged.

### 5.3. Rules for constructing keys

1. **Stable:** Does not change on retries, redeliveries, polls, or replays.
2. **Unique per intent:** Two valid distinct operations never collide.
3. **Scoped:** Includes tenant, application, operation type, or version where needed.
4. **Canonical:** Standardizes casing, whitespace, timestamps, timezones, and encoding.
5. **Bounded size:** Never embed raw payloads or PII in key names.
6. **Traceable:** Links keys back to business records without exposing sensitive data.
7. **Clear retention:** Knows how long a key stays valid or when it expires.

Never use `message.toString()` as a key. Its representation can change due to headers, payload wrappers, or library formatting.

### 5.4. When a message lacks a key

**Never** silently assign a shared default key like `unknown` to every message missing a business ID. That can cause valid messages to be dropped en masse.

Pick an explicit policy:

- Reject and route to a validation error channel/quarantine.
- Require upstream to supply the key per contract.
- Use a **documented and tested** fallback strategy if permitted by business rules.

## 6. MetadataStore and durability

**`MetadataStoreSelector`** relies on a metadata store to decide whether a key was accepted previously. Choosing the wrong store defeats deduplication on scale-out or restarts.

### 6.1. In-memory vs. persistent stores

| Store | When appropriate | Limitations |
| --- | --- | --- |
| **`SimpleMetadataStore`** | Demos, unit tests, or single-process flows not requiring cross-restart dedupe | Lost on restart; not shared across instances |
| **JDBC-backed metadata store** | Need durability and multi-instance coordination with a suitable DB | DB connections, transactions, schema, cleanup, and contention |
| **Redis-backed metadata store** | Need shared state and high throughput | Must evaluate persistence, atomic ops, eviction, failover |
| **Other supported shared stores** | Fits specific topologies | Must read atomicity and recovery contracts |

Exact bean/store names depend on the Spring Integration version. Regardless of backend, verify the store provides **atomic read/write** per contract and **does not lose keys** when an instance restarts.

### 6.2. Race condition between two consumers

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant S as Shared metadata store
    A->>S: Check key K
    B->>S: Check key K
    S-->>A: Not found
    S-->>B: Not found
    A->>S: Mark K
    B->>S: Mark K
    Note over A,B: If check-then-put is non-atomic, both may process
~~~

A **separate read then write** fails under concurrency. You need **`put-if-absent`/`compare-and-set`** semantics, or database unique constraints/locks/transactions. Across multiple instances, atomicity must live in the **shared backend**, not a JVM-local `synchronized` block.

### 6.3. Durability, TTL, and eviction

If dedup keys expire after 7 days while the source can replay 30-day-old events, the system may reprocess old events after day 7. Set retention based on:

- Maximum source replay/redelivery window.
- Business correctness window (e.g., preventing duplicate payments across an order's lifecycle).
- Data retention and privacy policies.
- Metadata store capacity and performance.
- Approved reset/migration procedures.

**TTL is not always safe.** For operations with permanent consequences, unique constraints or durable business idempotency records are often better than short-lived caches.

## 7. Java DSL configuration example and IdempotentReceiverInterceptor

This is an **illustrative design example** using Spring Integration Java DSL. Verify imports, overloads, and your project's Spring Integration version when running; `OrderService` and duplicate handlers are application-defined.

### 7.1. MetadataStoreSelector + advice beans

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
public class InboundIdempotencyConfig {

    @Bean
    public MessageChannel inboundOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel duplicateOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    public ConcurrentMetadataStore exampleMetadataStore() {
        // Single-JVM illustration ONLY: multi-instance production needs a shared store.
        return new SimpleMetadataStore();
    }

    @Bean
    public IdempotentReceiverInterceptor orderIdempotentAdvice(
            ConcurrentMetadataStore exampleMetadataStore,
            @Qualifier("duplicateOrdersChannel") MessageChannel duplicates) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    String tenant = requireHeader(message, "tenantId");
                    String operationId = requireHeader(message, "operationId");
                    return "order:create:v1:" + tenant + ":" + operationId;
                },
                exampleMetadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        // Configure duplicate route so the business handler does not execute
        // when the selector rejects the message.
        advice.setDiscardChannel(duplicates);
        return advice;
    }

    private static String requireHeader(
            org.springframework.messaging.Message<?> message, String name) {
        Object value = message.getHeaders().get(name);
        if (value == null || value.toString().isBlank()) {
            throw new IllegalArgumentException("Missing header: " + name);
        }
        return value.toString();
    }

    @Bean
    public IntegrationFlow ordersProcessingFlow(
            OrderService orderService,
            IdempotentReceiverInterceptor orderIdempotentAdvice) {

        return IntegrationFlow.from("inboundOrdersChannel")
                .handle(orderService, "createOrder",
                        endpoint -> endpoint.advice(orderIdempotentAdvice))
                .get();
    }
}
~~~

**Explanation:**

- Messages from inbound adapters enter `inboundOrdersChannel`.
- Handler `OrderService.createOrder(...)` carries the **advice**.
- The selector computes the key from two stable headers, and the store checks whether the key was seen.
- Duplicates route to `duplicateOrdersChannel` as configured; never treat logging a duplicate as business success blindly.
- `SimpleMetadataStore` is demo-only. Replace it with a **persistent shared atomic store**—never ship it unchanged to multi-pod production.
- `OrderService.createOrder` and the headers are **application contracts**, not Spring-generated defaults.

**Important note:** An interceptor that records the key upon receipt may mark the key **before the business handler actually commits**. This example teaches wiring, not guaranteed exactly-once or crash safety. Later sections show how to upgrade to a production design.

### 7.2. Duplicate handling flow

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DuplicateOrdersHandler {

    @ServiceActivator(inputChannel = "duplicateOrdersChannel")
    public void acceptDuplicate(Message<?> message) {
        // Record metrics/audit by operationId. Do not call createOrder again.
        // Do not log raw payloads or PII.
        // For request-reply, return a response per contract.
    }
}
~~~

In a one-way flow, a duplicate can be acked after confirming the prior run succeeded. However, if the key was marked before business commit or remains `PROCESSING`, **never assume the duplicate already completed**. Look up business state and decide whether to wait, retry, or reconcile.

### 7.3. What if you do not use IdempotentReceiverInterceptor?

You can use a **`MessageFilter`** with a `MessageSelector` and discard channel, or write a service handler backed by a **database unique constraint**. The choice depends on:

- Where should the guard sit?
- Should duplicates return a business response or simply be discarded?
- Do metadata and side effects share a transaction?
- Is multi-instance coordination required?
- How must replays compare payloads, versions, and states?

Do not force every inbound adapter through an interceptor if the source or DB already offers a better business-level idempotency mechanism.

## 8. Biggest hazard: marking processed before processing completes

Consider a naive implementation:

~~~text
T0: receive(K)
T1: putIfAbsent(K, "seen") -> success
T2: business handler calls downstream
T3: downstream times out or process crashes
T4: broker redelivers K
T5: selector sees K "seen" -> marks duplicate -> discards
~~~

At T3 there may be no business outcome yet. If T5 drops the message, the system has turned **at-least-once** into a **lost business operation**.

### 8.1. Minimum four states for an inbox

~~~text
NEW
  -> PROCESSING
  -> COMPLETED
  -> FAILED_RETRYABLE
  -> FAILED_FINAL / NEEDS_RECONCILIATION
~~~

Distinguish:

- **`COMPLETED`:** Evidence exists that business effects committed or final outcome was confirmed.
- **`PROCESSING`:** A worker currently owns the operation; needs lease/timeout to avoid permanent stalls.
- **`FAILED_RETRYABLE`:** Allowed to retry per policy using the same operation key.
- **`NEEDS_RECONCILIATION`:** Unclear if downstream processed it; do not replay blindly.
- **`FAILED_FINAL`:** Input or business error confirmed unprocessable.

A single boolean `seen=true` cannot express these states.

### 8.2. Transactional inbox pattern

If business side effects live in the **same database**, use one transaction:

1. Insert the inbox row with a unique key.
2. If the key already exists, read the stored result/state.
3. If absent, execute DB business logic and set `COMPLETED` **in the same transaction**.
4. Commit the inbox record and business changes together.

If the transaction rolls back before commit, the key is not persisted as completed; a later delivery can run. If the key collides after commit, return or skip based on the stored outcome.

~~~sql
-- Illustrative SQL model; locking and ON CONFLICT syntax vary by DB.
CREATE TABLE inbound_inbox (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_key      VARCHAR(250) NOT NULL,
    payload_hash       VARCHAR(128) NOT NULL,
    state              VARCHAR(40) NOT NULL,
    result_reference   VARCHAR(250),
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

The unique constraint prevents two workers from inserting the same inbox row simultaneously. Yet when the side effect is an **external HTTP API**, a local DB transaction does not span the remote call: you still need downstream idempotency keys, outbox, or reconciliation.

### 8.3. Balancing duplicate suppression vs. outcome replay

For an **HTTP inbound gateway**, a retrying caller usually expects **the same business result**. Merely discarding the duplicate without replying can leave the caller timing out endlessly.

For a committed **JMS one-way event**, you can accept the duplicate and ack without re-running the handler.

For an **in-flight `PROCESSING` event**, return an accepted/pending status or ask the caller to retry per contract; never fake success before an outcome exists.

## 9. Transactions, acknowledgement, and checkpoints

An idempotent receiver does not replace the message source's **ack/offset commit**. To avoid loss or duplicate work, clarify **who is responsible** at every boundary.

| Source | Checkpoint/ack point | Risk if key is marked too early |
| --- | --- | --- |
| **HTTP inbound** | HTTP response sent to caller | Returning success before business commits |
| **JMS** | Session acknowledgement / transaction commit | Acking discarded message even though first run failed |
| **AMQP** | Ack/nack and DLX/redelivery policy | Acking before persisting outcome durably |
| **Kafka** | Consumer offset commit, ack mode, and error handler | Committing offset before business side effects finish |
| **File/SFTP** | File filter, staging, archive/move, metadata | File skipped on next poll even though records remain unfinished |
| **JDBC polling** | Row claim, processed flag, transaction | Row marked processed before external call succeeds |

Never deduce exact ack behavior solely from `DirectChannel` or `IdempotentReceiverInterceptor` without inspecting the listener container, error handler, transaction manager, thread boundaries, and adapter configuration.

### 9.1. Two integration test scenarios

**Scenario A — Business succeeds, ack fails:** Source redelivers. The receiver must see `COMPLETED`, skip creating a second side effect, and complete the ack per policy.

**Scenario B — Marker written, business fails:** Source redelivers. The receiver **must not skip unconditionally**; it needs marker rollback, lease/retry, or inbox-state inspection.

### 9.2. Transaction boundaries do not span every system

A single JDBC transaction does not automatically encompass an SFTP server, HTTP partner, and Kafka broker without a matching transaction/coordination protocol. Across multiple systems, practical designs typically combine:

- At-least-once delivery.
- Business idempotency with stable keys.
- Inbox/outbox to coordinate local state.
- Reconciliation for uncertain remote outcomes.
- Bounded retries and dead-letter handling.

Never claim **end-to-end exactly-once** simply because an in-memory selector detected duplicates.

## 10. Retry, redelivery, recoverer, and duplicate detection

Retry and idempotency complement each other:

- **Retry:** Re-attempts transient failures, potentially calling the handler multiple times.
- **Redelivery:** Source re-sends when ack/commit was not received.
- **Idempotency:** Reduces or prevents repeated business effects.
- **Recoverer/DLQ:** Decides what happens once retries are exhausted or errors are non-retryable.

~~~mermaid
flowchart TD
    IN["Source event K"] --> KEY["Compute stable operation key"]
    KEY --> STATE{"Inbox/selector state"}
    STATE -->|New| EXEC["Handle business operation"]
    STATE -->|Completed| ACK["Return cached result / ack duplicate"]
    STATE -->|Processing| WAIT["Wait / retry / reconcile"]
    STATE -->|Failed/retryable| EXEC
    EXEC --> R{"Outcome"}
    R -->|Success| DONE["Persist COMPLETED + result"]
    R -->|Transient failure| RETRY["Bounded retry + backoff"]
    RETRY --> EXEC
    R -->|Exhausted/unknown| REC["Recovery store / DLQ / reconciliation"]
    REC --> AUD["Audit + owner + replay policy"]
    DONE --> ACK
~~~

### 10.1. Multi-layer retry amplification

If a handler retries 3 attempts and the broker redelivers 4 times, total downstream calls can reach **12**, excluding HTTP client retries. Strong dedup keys curb duplicate side effects, but do not replace **retry budgets** and backpressure.

### 10.2. When should a marker be removed after failure?

A "seen key" metadata store may need to delete a marker when the handler produced no side effect so processing can retry. However, **blindly deleting markers is also dangerous** if downstream committed while the response was lost.

Only remove or transition markers based on **outcome evidence** and designed concurrency rules. For ambiguous HTTP timeouts, prefer `NEEDS_RECONCILIATION` over deleting the key and resending blindly.

### 10.3. Recovery must preserve the operation key

When a message goes to a DLQ and is replayed, keep the **original operation ID**, adding a separate `replayAttempt` or `replayId` for auditing. Generating a brand-new idempotency key on every replay defeats deduplication.

## 11. File and SFTP inbound: two layers of deduplication

File/SFTP clearly illustrates the difference between **file filtering** and **business idempotency**.

### 11.1. File-layer filtering

An inbound adapter/poller can use an **accept-once** or **persistent metadata filter** to avoid re-downloading seen files. Keys typically use path and file modification metadata per adapter.

This controls **file discovery**, not confirmation that every record inside the file succeeded.

~~~text
/incoming/orders-2026-11-23.csv
   record 1: ORD-971  -> COMPLETED
   record 2: ORD-972  -> FAILED_RETRYABLE
   record 3: ORD-973  -> COMPLETED

File-level: "file downloaded"
Record-level: "ORD-971, ORD-973 completed; ORD-972 still pending"
~~~

### 11.2. Scenarios where a file is uploaded multiple times

If a partner uploads the same file under a new name, a path-based filter treats it as new. Yet business operation keys still collide and are protected by the inbox. Conversely, if a partner updates content while keeping the same filename, a path-only filter may skip a valid update.

The design must establish the contract:

- Are files **immutable** after upload or editable?
- Do filenames carry versions/checksums?
- Is there an `upload-complete` state or atomic rename to avoid reading partial files?
- After which step should remote files be moved/renamed/cleaned up?
- If one record fails, do you hold the entire file or process partially?

### 11.3. Persistent accept-once filters and restarts

In-memory filters forget accepted files on restart. Persistent metadata filters protect across restarts **if** the store is durable and properly shared across instances.

However, a file accepted once whose processing later failed may still be excluded from future polls. Therefore, design **filter-metadata rollback/cleanup or per-record recovery** aligned with the real file lifecycle, never assuming the filter knows whether side effects committed.

## 12. HTTP inbound gateway: duplicates do not always just return 200

With an HTTP inbound gateway, duplicates usually occur when callers resend after timeouts, network errors, or intentional retries. The application needs a **request idempotency contract**:

1. Client sends an **`Idempotency-Key`** or stable business operation ID.
2. Server scopes the key by tenant + operation + endpoint/version as needed.
3. If **unseen**, server processes and saves the result in the inbox.
4. If **already `COMPLETED`** with the same request fingerprint, return the **same business result** or reference per contract.
5. If **`PROCESSING`**, return a pending/accepted status or temporary response per API contract.
6. If the key exists with a different request body, return **conflict** rather than treating it as a valid duplicate.

### 12.1. HTTP contract example

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-create-T42-ORD-971

{"tenantId":"T42","orderId":"ORD-971","amount":150000}
~~~

When a result already exists:

~~~json
{
  "operationId": "order-create-T42-ORD-971",
  "status": "COMPLETED",
  "orderReference": "ORD-971"
}
~~~

This outline is illustrative. Real systems must specify status codes, response bodies, replay windows, fingerprint checks, and key scoping so other clients cannot guess or hijack keys.

### 12.2. Why discarding duplicates can hang HTTP callers

If an interceptor routes duplicates to a **one-way discard channel** while the caller waits on a **gateway** reply, nothing guarantees the caller receives a business result. It may time out or miss a reply depending on endpoint configuration.

For inbound gateways, an **idempotent service** reading the inbox and returning cached results usually fits better than discarding. If using an interceptor, give the duplicate path a **valid reply** and test request-reply semantics thoroughly.

## 13. JMS, AMQP, and Kafka: idempotency with brokers

### 13.1. JMS inbound

JMS has message IDs and redelivery metadata, but business deduplication should use an **operation ID** if operations can be republished or bridged. When a listener rolls back, the same message may arrive again; the metadata store must not block the new delivery if the previous run never committed business work.

Test:

- Processing succeeds but session commit fails → redelivery creates no duplicate side effects.
- Handler fails before commit → next delivery still has a path to reprocess.
- DLQ threshold reached → failure record persisted with a replay policy.

### 13.2. AMQP/RabbitMQ inbound

RabbitMQ uses consumer ack/nack and dead-letter exchanges per configuration. An idempotent receiver protects the business handler; it **does not directly decide** broker ack/nack. Once a recoverer durably saves a failure and returns normally, the adapter/container may ack per policy. If persistence fails, the message must remain retained per verified strategy.

Never rely solely on the `redelivered` flag: valid duplicates can also arrive via a fresh publish with `redelivered=false`.

### 13.3. Kafka inbound

Kafka offsets and event IDs serve two roles:

~~~text
Transport identity:
    topic + partition + offset

Business operation identity:
    tenant + eventId + operation/version
~~~

To avoid reprocessing **the exact same record** after a rebalance, transport keys help. If a publisher **republishes the same business event** at a new offset, you need a business key to deduplicate. For Kafka consumers, test real offset commits, ack modes, listener error handlers, DLT, and transactions.

### 13.4. Broker-level dedupe vs. app-level dedupe

A broker may reduce duplicates within specific bounds, but cannot prevent duplicate side effects if a consumer crashes after a DB commit and before acking. **Application-level idempotency** and database constraints remain necessary.

## 14. JDBC inbound polling: row states and unique keys

With a **JDBC inbound adapter**, pollers select matching rows and emit messages. If the query does not update row state or a transaction rolls back, the same row can reappear on the next poll.

### 14.1. Business row states

~~~text
NEW -> CLAIMED -> PROCESSING -> COMPLETED
                    |             |
                    v             v
               RETRY_PENDING   ARCHIVED
                    |
                    v
              NEEDS_RECONCILIATION
~~~

In multi-poller designs, use **claim tokens, optimistic locking, transactions, or database row locks** so two workers never pick up the same unprocessed row. `SELECT ... WHERE processed=false` alone fails when multiple instances poll concurrently.

### 14.2. Distinguishing row ID and operation ID

Suppose a staging row has `row_id=901`, `order_id=ORD-971`. If upstream inserts the same event again as `row_id=902`, row-ID deduplication misses the business duplicate.

Designs can combine:

- **Row key:** Good for preventing re-reading the same row in one cycle.
- **Business operation key:** Good for preventing duplicate orders across distinct records.
- **Unique constraint:** Enforces DB invariants under concurrency.

Some systems require **all three**.

### 14.3. When side effects live outside the DB

If a poller reads a DB row and calls an external HTTP API, no simple JDBC transaction makes these three atomic:

1. Marking the row processed in the DB.
2. Sending the HTTP request to the partner.
3. Receiving the partner's response/ack.

Use **outbox/inbox**, partner-side idempotency keys, `OUTCOME_UNKNOWN` states, and reconciliation. If the partner API lacks idempotency, carefully evaluate duplicate risks before enabling retries.

## 15. Handling concurrent messages and scale-out

In production, flows commonly involve:

- Multiple consumer threads inside one JVM.
- Multiple pods/instances sharing a Kafka topic or RabbitMQ queue.
- Two different sources sending the same business operation.
- Replay jobs running alongside live ingestion.

A per-instance `HashSet` or `SimpleMetadataStore` cannot prevent system-wide duplicates when two instances receive the same business key concurrently.

### 15.1. Atomic claim design

Safer pseudocode for business state:

~~~text
handle(message):
    key = canonicalBusinessKey(message)
    fingerprint = normalizedPayloadFingerprint(message)
    claim = inbox.tryInsertOrLock(key, fingerprint)

    if claim == ALREADY_COMPLETED:
        return inbox.previousResult(key)

    if claim == SAME_KEY_DIFFERENT_PAYLOAD:
        return conflictAndAudit(key)

    if claim == IN_PROGRESS:
        return pendingOrRetryAccordingToContract(key)

    if claim == OWNED:
        result = performBusinessOperationWithIdempotency(key)
        inbox.completeAtomicallyWhenPossible(key, result)
        return result

    return recordRecoveryNeeded(key)
~~~

**Strengths:** Separates `COMPLETED` from `IN_PROGRESS` and never treats claiming a key as proof of successful completion.

### 15.2. Leases and fencing

If worker A claims key `K` and loses connectivity, worker B may need to take over. A timed lease enables recovery, yet if A wakes up and still sends downstream, parallel execution can occur.

For critical tasks, use **fencing tokens or versions** so downstream/local state rejects stale owners where supported. Lease timeouts **do not guarantee** the old worker stopped creating side effects.

### 15.3. Payload fingerprints and conflict detection

Same operation key with a different payload should be a **conflict**, unless the contract explicitly defines merging rules:

~~~text
K = order:create:T42:ORD-971

Message A: amount=150000, currency=VND
Message B: amount=999000, currency=VND

If K matches but business input differs:
    Do not silently drop B as a normal duplicate.
    Do not blindly run B as a new operation.
    Route to contract check and preserve conflict evidence.
~~~

Compute fingerprints from approved canonical fields, avoiding unstable serialization details or putting raw PII into keys/metrics.

## 16. Key lifecycle: retention, schema changes, and replay

### 16.1. Retention policy

How long must an idempotency record stay? No single TTL fits all systems. Consider:

1. Broker retention and redelivery window.
2. How long users/partners may retry requests.
3. Manual replay or backfill windows.
4. Permanence of side effects like order creation or payments.
5. Data retention and privacy deletion rules.
6. DB/Redis cost and key archiving mechanisms.

If a transaction must **never** run twice permanently, a 24-hour cache TTL is usually insufficient. DB unique constraints or persistent business states must continue guarding the operation.

### 16.2. Key namespaces and versions

When a business contract changes, versioned namespaces may be needed:

~~~text
payments:charge:v1:tenant42:order971
payments:charge:v2:tenant42:order971
~~~

**Never bump key versions on every deployment**, because that lets previously completed operations run again as new ones. Change versions only when **operation semantics or deduplication contracts genuinely change** and include a migration plan.

### 16.3. Replays with vs. without deduplication

Two distinct needs:

- **Redelivery/retry:** Needs duplicate protection; keep the original operation key.
- **Reprocessing data with new logic:** May legitimately need a new job ID or operation type to produce a fresh result.

Replay policies should define **approvers, current business state, key reuse vs. regeneration, throughput caps, and rollback**. Never wipe an entire metadata store or inbox table just to "re-run faster."

## 17. Idempotent receiver and MessageChannel

**`MessageChannel`** affects threading, ordering, and error propagation. It does not determine whether a message was processed exactly once.

| Channel/mechanism | Things to watch |
| --- | --- |
| **`DirectChannel`** | Synchronous dispatch usually on sender thread; exceptions may propagate to caller per endpoint |
| **`ExecutorChannel`** | Switches threads; upstream transaction/thread context does not propagate automatically |
| **`QueueChannel`** | Buffers messages, but durability depends on backing store config |
| **`PublishSubscribeChannel`** | One event can reach multiple subscribers, each with its own side effect |
| **`MessageBridge`** | Connects channels; does not imply business deduplication |
| **Pollable channel** | Poller and handler boundaries have separate retry/error mechanics |

### 17.1. Does fan-out need multiple idempotency keys?

If one order event must:

1. Save the order in DB.
2. Send an email notification.
3. Sync to accounting.

A single global `orderId` key with **one processed flag** can break: DB succeeds while email fails, and on retry the entire message gets blocked.

Separate **per-consumer/per-operation keys**:

~~~text
order-db:create:T42:ORD-971
notification:send-confirmation:T42:ORD-971
accounting:export-invoice:T42:ORD-971
~~~

Each side effect has independent ownership, outcome, and retry/recovery. For fan-out, an outbox can ensure no downstream consumer misses an event when one branch fails.

### 17.2. Which headers can be lost?

Transformers or gateways may construct new messages, altering or dropping custom application headers unexpectedly. Verify that `tenantId`, `operationId`, and `correlationId` survive across adapter boundaries per contract.

Never use a randomly generated hop header as an idempotency key; derive keys from **canonical business payloads or stable source metadata**.

## 18. Error handling and duplicate decisions

Inbound adapters need **two clear paths**:

1. **Already-processed duplicate:** Do not run the business handler again, yet still honor reply/ack contracts.
2. **Unprocessable message:** Validation failures, business errors, exhausted retries, or unknown outcomes need error flows/quarantine/recovery.

### 18.1. Decision table

| State | Handling | Can source be acked? |
| --- | --- | --- |
| New key, business `COMMITTED` | Save result, move to `COMPLETED` | Per source config, after commit proof |
| Duplicate key, `COMPLETED` | Return cached result or ack duplicate | Usually yes once contract/ack is verified |
| Duplicate key, `PROCESSING` | Wait, report pending, bounded retry | Depends on source and state storage |
| Duplicate key, different payload | Conflict/quarantine | Needs clear policy; never return blind success |
| Claimed key, business `FAILED` | Retry/rollback or recovery | Do not ack if doing so drops responsibility |
| Downstream outcome `UNKNOWN` | Reconcile before replay | Ack only if state is durably persisted per design |
| `MetadataStore` unavailable | Fail closed or use approved fallback | Never bypass guard and run unchecked in parallel |

**Note:** A duplicate decision **is not the same as a business error**. For many APIs, duplicates of completed operations return the original success result. For event consumers, duplicates can be acked quietly.

### 18.2. Duplicate path failures

If the discard channel has an audit handler that fails, exception and ack behavior depends on channel/endpoint configuration. Distinguish:

- Best-effort audits/metrics that may not block business outcomes.
- Mandatory state writes needed to verify recovery that must not be skipped.
- Duplicates currently `PROCESSING`, which may need retry/waiting rather than log-and-ack.

### 18.3. Avoiding infinite error loops

~~~text
Main handler failure -> error channel
Error channel -> retries same handler
Idempotency marker still "seen"
Handler on retry gets discarded -> false "success"
~~~

When wiring retries, error channels, and idempotent guards, enforce a clear state machine so a failure never turns into a falsely acked duplicate or an infinite retry loop.

## 19. Recommended production architecture

For critical tasks with side effects, an architecture may include:

~~~mermaid
flowchart TD
    S["Inbound adapter / gateway"] --> V["Validate + canonical key"]
    V --> IN["Transactional inbox / atomic claim"]
    IN --> Q{"Operation state"}
    Q -->|New / retryable| H["Business handler"]
    Q -->|Completed| CACHE["Cached result / duplicate ack"]
    Q -->|Processing| P["Pending / lease / retry"]
    Q -->|Conflict| C["Quarantine + audit"]
    H --> DB["Local DB side effect"]
    H --> OUT["Outbox entry for remote call"]
    DB --> DONE["Persist result + COMPLETE"]
    OUT --> WORK["Outbound worker + idempotency key"]
    WORK --> API["Remote API / broker"]
    API --> REC["Reconciliation + outcome"]
    REC --> DONE
    DONE --> ACK["Ack source / reply"]
~~~

Not every application needs every piece. For events updating only a local DB table, **transaction + unique key** may suffice. For workflows spanning multiple external systems, **inbox/outbox + idempotency + reconciliation** should be evaluated.

### 19.1. Local transaction example

Annotated pseudocode:

~~~java
@Transactional
public OrderResult receive(CreateOrder command) {
    String key = operationKey(command);

    InboxEntry existing = inbox.findAndLockOrClaim(key);

    if (existing.isCompleted()) {
        return existing.previousResult();
    }
    if (existing.isOwnedByAnotherWorker()) {
        throw new ProcessingInProgressException(key);
    }
    if (existing.hasDifferentPayloadFingerprint(command)) {
        throw new IdempotencyConflictException(key);
    }

    // Changes below must share the transaction when using local JDBC.
    Order order = orderRepository.createIfAbsent(command);
    inbox.markCompleted(key, order.toResult());
    return order.toResult();
}
~~~

This is **design pseudocode**, not built-in Spring Data/JPA methods: `findAndLockOrClaim`, `createIfAbsent`, `previousResult`, and the exceptions are application-defined APIs. In real implementations, guard against **two transactions both seeing no key**, using unique constraints/locking and proper SQL conflict handling.

### 19.2. Outbox for non-database side effects

Within the same transaction that updates business state, write an **outbox event**. A separate outbound worker reads the outbox and calls the external system with an **idempotency key**. If the call succeeds before the outbox is marked sent, retrying uses the same key, curbing duplicate downstream effects.

Never call a partner HTTP endpoint directly inside a long DB transaction and assume exactly-once. A local DB transaction cannot roll back side effects already executed in external systems.

## 20. Test matrix for idempotent receivers

Tests must prove **real behavior** across handlers, stores, transactions, and source adapters—not just unit tests checking whether `MetadataStoreSelector` returns true or false.

| Test | Setup | Expectation |
| --- | --- | --- |
| First message | New key | Handler called once, outcome saved |
| Redelivery after success | Same operation key | No second side effect created |
| Different operations | Different valid keys | Both processed |
| Same key, different payload | Different fingerprint | Conflict/quarantine; never silently dropped |
| Missing key | Missing tenant/event ID | Explicit reject/validation flow |
| Concurrent duplicates | Two threads, same key | Atomic claim; never both applying effects |
| Multiple instances | Two pods sharing store | No duplicates from per-JVM caching |
| Restart | Restart app between deliveries | Processed state survives if required |
| Crash after marker | Marker saved, business not committed | Operation not permanently dropped |
| Commit then ack failure | DB commits, broker redelivers | Duplicate recognized, ack completed properly |
| HTTP outcome unknown | Server may have committed | Reconciled; not blindly re-sent |
| Store outage | `MetadataStore` disconnected | Fails safe per policy, never bypasses guard |
| Key TTL expiry | Old event replayed after cleanup | Matches retention contract |
| Reply gateway | HTTP retry with same key | Returns cached result/pending/conflict per contract |
| Fan-out partial failure | Consumer A succeeds, B fails | A does not repeat; B still retries |
| DLQ replay | Replay with owner and approval | Business key and audit trail preserved |

### 20.1. Testing duplicate headers and discard behavior

For **`IdempotentReceiverInterceptor`**, assert:

1. On a new key, the handler runs and produces the expected result.
2. On a duplicate key **without a discard channel**, verify your version's duplicate header/handler behavior.
3. **With a discard channel**, duplicates route correctly and the business handler **creates no side effects**.
4. If the duplicate path fails, source ack/commit matches the chosen policy.
5. Request-reply gateways return replies conforming to contract.

### 20.2. Failure and rollback injection tests

Failure injection points:

~~~text
F1: before key claim
F2: after key claim, before business handler
F3: after local DB side effect, before transaction commit
F4: after transaction commit, before broker ack
F5: after remote API side effect, before response
F6: during failure archive/DLQ publish
F7: during process restart / rebalance
~~~

At each point, verify **zero lost operations** and **zero duplicate business effects outside contract**.

### 20.3. Independent producer testing

Do not only send the exact same message twice inside one test. Simulate **two different sources** or an event republished with a new transport ID but the same business operation key. This exposes flawed deduplication tied too tightly to framework or broker message IDs.

## 21. Metrics, logging, and auditing

### 21.1. Essential metrics

| Metric | Purpose |
| --- | --- |
| `inbound_messages_total` | Total messages received by source |
| `idempotent_accepted_total` | New messages/keys accepted |
| `idempotent_duplicate_total` | Duplicates detected |
| `idempotent_conflict_total` | Same key with different payload per contract |
| `idempotency_store_error_total` | Store or atomic claim errors |
| `idempotency_in_progress` | Operations without a final outcome yet |
| `idempotency_completed_total` | Operations genuinely completed |
| `idempotency_reconciled_total` | Unknown outcomes reconciled |
| `idempotency_replay_total` | Approved replays |
| `inbound_ack_latency` | Time from receipt to ack/reply |
| `inbound_redelivery_total` | Observed source redeliveries |
| `inbox_oldest_pending_age` | Age of oldest incomplete operation |

Never use **`operationId`, tenant ID, or message ID** as high-cardinality metric labels if that generates millions of series. Put correlation metadata in access-controlled traces/logs and limit exposure of sensitive data.

### 21.2. Structured logging

~~~json
{
  "event": "idempotent_receiver.duplicate_detected",
  "flow": "orders-inbound",
  "source": "jms-orders",
  "operationType": "CREATE_ORDER",
  "operationKeyRef": "hash:7c5d...",
  "decision": "ALREADY_COMPLETED",
  "messageCorrelationId": "trace-84021",
  "processingOutcome": "cached-result",
  "occurredAt": "2026-11-23T08:10:15Z"
}
~~~

This is an **application schema example**, not full data auto-logged by Spring Integration. Depending on policy, store a hash or reference instead of raw business keys. Never log raw tokens, SFTP passwords, `Authorization` headers, personal data, or partner payloads unnecessarily.

### 21.3. High-priority alerts

- Sudden spike in duplicate rate after deploy, restart, or broker rebalance.
- Inbox/metadata store unavailable.
- Operations stuck in `PROCESSING` too long or repeated lease expirations.
- Frequent `SAME_KEY_DIFFERENT_PAYLOAD` conflicts.
- Growing DLQ/pending backlog while ack rate stays high.
- Unexpected key store evictions or memory resets.
- Duplicates causing HTTP inbound gateway timeouts.
- Same operation executed multiple times across instances.
- Surge in `OUTCOME_UNKNOWN` states after a downstream incident.

## 22. Runbook for duplicates and idempotency failures

### 22.1. Step 1 — Scope the incident

Gather:

1. Source adapter, queue/topic/file, poller, and endpoint.
2. Environment, tenant, business operation, and correlation ID.
3. Last successful execution of the business handler.
4. State of the idempotency store, inbox, and database transactions.
5. Retries, broker redeliveries, offsets/acks, and dead-letter state.
6. Recent deployments, restarts, rebalances, or key-strategy changes.

### 22.2. Step 2 — Classify the incident

| Category | Symptoms | Action |
| --- | --- | --- |
| **Harmless duplicate** | Inbox `COMPLETED`, payload matches | Ack or return cached result per contract |
| **Missing business effect** | Key marked yet no outcome | Hold/reopen per procedure; reconcile before reprocessing |
| **Concurrent processing** | Two workers claimed same key | Check atomic store, unique constraints, leases/fencing |
| **Store reset/eviction** | Duplicates after restart or TTL | Restore store/retention, inspect repeated side effects |
| **Upstream bad key** | Same key used for two different requests | Quarantine, fix contract with producer |
| **Downstream outcome unknown** | Timeout after sending | Query partner state before replaying |
| **Ack mismatch** | Source acked before business commit | Fix transaction/error path, investigate potentially lost messages |

### 22.3. Step 3 — Safe replay

Before replaying:

- Re-read business state and downstream results if available.
- Verify the original operation ID and payload fingerprint.
- Decide whether to reuse the key or intentionally create a **new operation**.
- Obtain owner/approval if payments, sensitive data, or production are involved.
- Rate-limit replays and run a canary if backlog is large.
- Record audit trail: who replayed, why, outcome, and whether side effects occurred.

**Never truncate the inbox table or flush all of Redis just to replay one message.** Doing so can let thousands of completed operations re-run.

### 22.4. Step 4 — Close the incident

Close only when:

1. No incomplete operations remain skipped.
2. No duplicate side effects exist beyond accepted tolerances.
3. Source checkpoints/acks/offsets match business state.
4. Inbox, metadata store, and DLQ are durable, owned, and monitored.
5. Discrepancies with downstream have been reconciled.
6. Root causes in key strategy, transactions, broker, or concurrency are fixed or explicitly waived.

## 23. Common anti-patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Using `MessageHeaders.ID` as business key | Retries arrive with new IDs | Use a stable operation ID |
| Using `orderId` for both CREATE and UPDATE | Blocks valid later events | Namespace by operation/version |
| `SimpleMetadataStore` in a multi-pod cluster | Each pod treats the same key as new | Shared atomic persistent store |
| Non-atomic check-then-put | Two workers process simultaneously | CAS/unique constraint/transaction |
| Recording `seen` and treating it as `COMPLETED` | Crashes drop business operations | State machine/transactional inbox |
| Defaulting to discard duplicates on HTTP gateways | Callers miss proper replies | Cached result/pending/conflict response |
| Treating SFTP file filter as proof all rows succeeded | Failed records get skipped | Per-record business state and recovery |
| Deleting keys after every timeout | Repeats externally committed side effects | Reconcile before retrying |
| Setting TTL shorter than replay window | Old replays trigger second side effects | Retain per business window |
| Skipping payload fingerprint checks | Same key with different data gets dropped | Conflict detection |
| One shared key across all subscribers | Branch A succeeding blocks branch B from retrying | Per-operation/per-consumer state |
| Relying solely on broker duplicate flags | Republished events lack redelivered flags | Business operation key |
| Never testing acks after duplicates | Lost messages or endless redeliveries | Adapter/container integration tests |
| Logging sensitive payloads/keys in metrics/logs | Data exposure, cardinality explosion | Redaction, references, low-cardinality labels |
| Generating new keys on replay | Breaks idempotency across replays | Keep operation ID, separate replay audit ID |
| Infinite retries when store is unreachable | Overloads source and backlog | Fail-safe, backoff, alerts, capacity plan |
| No cleanup/retention policy | Metadata store bloats or evicts blindly | Lifecycle, archiving, risk-based review |

## 24. Hands-on scenario: SFTP, JMS, and HTTP all creating orders

The **Learning Orders** system receives orders from:

- An hourly CSV file via SFTP.
- A JMS queue carrying order-creation events.
- An HTTP inbound gateway for direct client submissions.

All normalize to:

~~~yaml
# Illustrative business contract; not default Spring headers
tenantId: T42
operationType: CREATE_ORDER
orderId: ORD-971
operationVersion: 1
payloadFingerprint: sha256-of-canonical-business-fields
correlationId: trace-84021
source:
  adapter: sftp-or-jms-or-http
idempotency:
  key: order:create:v1:T42:ORD-971
~~~

### 24.1. First batch

SFTP delivers record `ORD-971`. The receiver claims the key, writes the DB transaction, and records `COMPLETED`. The file checkpoint updates per source workflow, keeping required audit metadata.

### 24.2. JMS redelivery/duplicate

A JMS event with the same business key arrives later. The receiver finds `COMPLETED` with a matching fingerprint and does not call `createOrder` a second time. The broker acks per design and logs the duplicate with `source = JMS`.

### 24.3. HTTP client retry

The client missed the initial HTTP response and resends with the same `Idempotency-Key`. The API reads the saved result and returns the **order reference** per contract instead of silently discarding and letting the client time out again.

### 24.4. Same key, different payload

The client sends a different amount under the same operation ID. The system records `IDEMPOTENCY_CONFLICT`, neither silently dropping the request nor creating a second order. The owner or client must clarify whether it is a bad request or an improperly identified new operation.

### 24.5. Crash between claim and commit

Suppose a pod crashes after marking `PROCESSING` but before committing. The next worker sees an incomplete state, checks the lease and business outcome, and takes over per policy. Never treat `PROCESSING` as `COMPLETED`.

### 24.6. Verification flow

~~~mermaid
flowchart TD
    A["Source event / file record / HTTP request"] --> B["Canonical key + fingerprint"]
    B --> C["Atomic inbox claim"]
    C --> D{"Existing state?"}
    D -->|Completed + same payload| E["Ack / cached result"]
    D -->|Different payload| F["Conflict + audit"]
    D -->|Processing| G["Pending / reconcile"]
    D -->|New| H["Transactional business operation"]
    H --> I{"Commit succeeded?"}
    I -->|Yes| J["Store COMPLETED + result"]
    I -->|No| K["Retry/recovery per source"]
    J --> E
    K --> L["No lost message + failure evidence"]
~~~

## 25. Self-check exercises

### Exercise 1. Message ID changes after replay

**Scenario:** A Kafka event is republished at a new offset with a new Spring Message ID, while `businessEventId` stays unchanged. The receiver uses the message ID as its key.

**Answer:** The receiver can process duplicates. You need a stable business event/operation key to deduplicate across republishes, not just transport IDs.

### Exercise 2. Key saved before handler runs

**Scenario:** `MetadataStore` marks the key, then the handler fails before DB commit. The source redelivers and the selector reports duplicate.

**Answer:** Risk of losing the operation. Synchronize state with the business transaction, or use an inbox (`PROCESSING`/`COMPLETED`) with recovery and outcome checks.

### Exercise 3. Two pods running concurrently

**Scenario:** Each pod has its own `SimpleMetadataStore`. Both receive the same operation.

**Answer:** Both can treat the key as new. You need a shared atomic metadata store or unique constraint/transactional inbox to coordinate across instances.

### Exercise 4. HTTP duplicate discarded

**Scenario:** An HTTP inbound gateway receives the same request again; the duplicate route only logs and sends no reply.

**Answer:** The client can keep timing out. Return a cached result, pending status, or conflict per HTTP contract; test request-reply and never fake success before business commit.

### Exercise 5. SFTP file with multiple records

**Scenario:** A filter marks the CSV as downloaded, but the second record fails. After a restart, the file is not read again.

**Answer:** File accept-once does not confirm each record succeeded. You need per-record state, recovery/quarantine, and a file checkpoint policy.

### Exercise 6. Same key, different payload

**Scenario:** Two requests share an idempotency key but carry different amounts.

**Answer:** Do not automatically treat as a valid duplicate. Compare fingerprints/canonical data and return a conflict or route to reconciliation per contract.

### Exercise 7. TTL shorter than replay window

**Scenario:** Dedup keys are deleted after one day, yet the system permits replaying events within one week.

**Answer:** Once a key expires, an old event can trigger a second side effect. Extend retention or enforce longer-lived protection at the business layer.

### Exercise 8. Two-consumer fan-out

**Scenario:** Consumer A saves to DB successfully; B fails sending email. A single shared `processed=true` flag prevents both from running again.

**Answer:** Wrong operation boundary. Separate idempotency state per consumer/side effect or use an outbox for reliable distribution.

## 26. Checklist for implementing an idempotent receiver

1. **Define the operation:** Know the exact business action that must not repeat.
2. **Stable key:** Tenant + operation + business ID/version per contract, independent of random headers.
3. **Check fingerprints:** Same key with different payload requires a conflict policy.
4. **Place guard early:** Before protected side effects, after reliable key normalization.
5. **Understand the interceptor:** Duplicates may be header-marked; configure discard/handling and test handler invocations.
6. **Pick the right store:** Demos can be in-memory; multi-instance production needs a shared atomic/durable store or DB inbox.
7. **Never equate seen with completed:** Separate `PROCESSING`, `COMPLETED`, `FAILED`, and `OUTCOME_UNKNOWN`.
8. **Handle concurrency:** Atomic claims, unique constraints, leases/fencing as needed.
9. **Match source semantics:** File/SFTP checkpoints, JMS/AMQP acks, Kafka offsets, JDBC row claims, HTTP replies.
10. **Clear transactions:** With a local DB, align inbox and side effects in one transaction where feasible.
11. **Downstream idempotency:** Use stable keys and reconciliation for remote APIs/side effects.
12. **Bounded retry:** Separate retryable/non-retryable; avoid unbounded stacked retries.
13. **Durable recovery:** DLQ/quarantine/error flow with owners, retention, replay policies, and verification.
14. **Replay with right keys:** Keep the operation ID, separate the replay audit ID.
15. **Justified retention:** TTL covers replay and correctness windows without blind eviction.
16. **Safe scale-out:** Test two pods/threads, restarts, and store outages.
17. **Proper gateway contract:** Duplicates return meaningful cached results, pending states, or conflicts.
18. **Independent fan-out:** Each side effect/consumer tracks its own state when needed.
19. **Observability:** Track dedup rate, conflicts, pending age, store errors, redeliveries, and reconciliations.
20. **Security:** Redact secrets/PII; restrict access to metadata stores and replay tools.
21. **Failure-injection testing:** Crash before/after claims, commits, acks, and remote calls.
22. **Runbooks:** Guide finding lost operations, genuine duplicates, and safe replays.

## 27. Summary

**Idempotent receiver for inbound adapters** protects Spring Integration flows against redeliveries, retries, and replays creating duplicate work. **`IdempotentReceiverInterceptor`**, **`MessageSelector`**, and **`MetadataStoreSelector`** help detect duplicates at handlers; file/SFTP accept-once filters help avoid re-reading sources. However, **never treat a `seen` flag in a metadata store as proof that business work succeeded**.

Reliable design starts with the **right business operation key**, continues with **atomic claims and durability**, **transactional inboxes or unique constraints** where fitting, **downstream idempotency**, and **adapter-accurate acks/checkpoints**. HTTP gateways owe contracted replies; JMS/AMQP/Kafka require testing redelivery and commits; File/SFTP must separate file-level filters from per-record outcomes; JDBC needs row states and transactions. Finally, **retry, dead-lettering, replay, correlation, monitoring, and reconciliation** must connect together so the system not only cuts duplicates, but also **never drops valid operations when errors occur**.
