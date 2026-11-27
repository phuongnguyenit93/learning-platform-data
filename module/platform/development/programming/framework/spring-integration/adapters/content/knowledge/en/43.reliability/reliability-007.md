# MetadataStoreSelector

**Chapter:** Reliability  
**Lesson:** MetadataStoreSelector  
**Module:** Spring Integration Adapters  
**Language:** English  
**Context:** Connecting external systems with inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with File, SFTP, HTTP, JMS, AMQP, Kafka, and databases, focusing on message contracts, idempotency, errors, transactions, and connection lifecycles.

> **Focus:** `MetadataStoreSelector` is a small yet important Spring Integration component for deciding **which messages are accepted based on keys/values in a metadata store**. Understanding when keys are stored, `putIfAbsent`/`replace` semantics, key/value strategies, and the boundary between **"selected"** and **"business completed"** is essential so messages are never lost when errors happen.

## 1. Real-world problem

A Spring Integration system receives messages from many sources. External systems can send duplicates, pollers can re-read after restarts, listeners can receive redeliveries after rollbacks, and operators can replay messages from dead-letter queues (DLQs).

For example, `orders-2026-11-23.csv` is downloaded by an SFTP inbound adapter. A file splitter emits a message per line; several lines finish processing before the application restarts. After restart, the system needs to know **which lines were already accepted** to avoid accidentally repeating the whole job.

Another example: an HTTP inbound gateway receives `CREATE_ORDER` with `tenantId=T42` and `orderId=ORD-971`. The client times out and resends the same operation. If processed twice, downstream could create two orders. A message selector keyed by **business operation key** helps detect subsequent arrivals.

Yet a key-based selector is only **one deduplication layer**, not a complete end-to-end transaction:

- If the key is saved before the DB write and the process crashes, future deliveries may be rejected even though the order was never created.
- If two instances use two separate stores, both may accept the same key.
- If the key relies only on filename, two different files sharing a name may be treated as duplicates.
- If an external API committed before the response was lost, retrying without downstream idempotency can still duplicate side effects.

**Goal:** Use `MetadataStoreSelector` in its proper role, paired with the right store, key/value strategy, and error/ack semantics per adapter.

### 1.1. What you will be able to do after this lesson

1. Explain `MetadataStoreSelector` relative to `MessageSelector`, `IdempotentReceiverInterceptor`, and persistent file filters.
2. Understand `accept(Message<?>)`, `keyStrategy`, `valueStrategy`, `compareValues`, and `ConcurrentMetadataStore`.
3. Write and test selectors for **first-seen keys**, **monotonically increasing versions**, or **sequence numbers** when ordering is guaranteed.
4. Choose in-memory, JDBC, Redis, or other persistent stores to fit scale-out and durability needs.
5. Integrate a selector into an inbound processing flow without accidentally turning business failures into skipped duplicates.
6. Design recovery, replay, idempotency, acknowledgement, and transactions for File/SFTP, HTTP, JMS, AMQP, Kafka, and JDBC.
7. Monitor behavior and detect stale keys, collisions, crash windows, and metadata store failures.

## 2. Placing MetadataStoreSelector in the right architecture

In Spring Integration, an inbound adapter/gateway creates a `Message<?>` and sends it to a `MessageChannel`. A consumer/handler receives the message and runs logic. A `MessageSelector` returns a `boolean`:

- `true`: The message is **accepted** under the selector's condition.
- `false`: The message is **rejected** under the selector's condition.

`MetadataStoreSelector` is a `MessageSelector` implementation that uses a metadata store to remember key/value state across messages.

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound adapter / gateway / poller"]
    IN --> CH["MessageChannel"]
    CH --> SEL["MetadataStoreSelector"]
    SEL --> STORE["ConcurrentMetadataStore"]
    STORE --> SEL
    SEL -->|accept = true| H["Business handler"]
    SEL -->|accept = false| REJ["Duplicate route / marker / rejection"]
    H --> OUT["DB / external API / outbound adapter"]
    H -.-> LOG["Business outcome + audit"]
    REJ -.-> LOG
~~~

**Important:** `MetadataStoreSelector` only supplies the `accept` decision. It **is not an inbound adapter**, **does not read files**, **does not create a DLQ**, **does not decide broker acks/offsets**, and **does not mark a business task as complete**.

### 2.1. Components that commonly work together

| Component | Role |
| --- | --- |
| `MetadataStoreSelector` | Computes key/value and decides whether to accept a message |
| `MessageProcessor<String>` | Strategy for extracting a key or value from a message |
| `ConcurrentMetadataStore` | Key/value store providing atomic update operations per contract |
| `IdempotentReceiverInterceptor` | Advice wrapping `MessageHandler`, using a selector to mark or reject messages |
| `MessageFilter` | Filter endpoint using `MessageSelector` to forward or discard messages |
| `MessageChannel` | Path to handler or duplicate/error flow |
| Accept-once file filter | Prevents re-accepting/downloading files at the file level |
| Transactional inbox | Tracks **`PROCESSING`/`COMPLETED`/`FAILED`** states, attachable to business transactions |
| Broker offset/ack | Manages JMS/AMQP/Kafka delivery, independent of the selector |

## 3. API contract of MetadataStoreSelector

`MetadataStoreSelector` lives in package:

~~~java
import org.springframework.integration.selector.MetadataStoreSelector;
~~~

It implements `MessageSelector` and uses `MessageProcessor<String>` along with `ConcurrentMetadataStore`. Common constructors:

~~~java
new MetadataStoreSelector(keyStrategy);
new MetadataStoreSelector(keyStrategy, valueStrategy);
new MetadataStoreSelector(keyStrategy, concurrentMetadataStore);
new MetadataStoreSelector(keyStrategy, valueStrategy, concurrentMetadataStore);
~~~

Each `keyStrategy`/`valueStrategy` is a **`MessageProcessor`** accepting `Message<?>` and returning a `String` used as the key or value. Java lambdas can be used when types infer cleanly.

### 3.1. What does `accept(Message<?>)` actually do?

Under normal logic, the selector:

1. Reads the message and computes the **key** via `keyStrategy`.
2. Computes the **value** via `valueStrategy`, or uses the **timestamp header** by default.
3. Executes `ConcurrentMetadataStore.putIfAbsent(key, value)`.
4. If the key **did not exist**, the operation stores the value and the selector returns `true`.
5. If the key **already existed**, the selector returns `false`, unless `compareValues` is configured and allows a new version/value that the store updates atomically.

~~~mermaid
flowchart TD
    M["Message"] --> K["keyStrategy(message)"]
    K --> V["valueStrategy(message) or timestamp header"]
    V --> PUT["ConcurrentMetadataStore.putIfAbsent(key, value)"]
    PUT --> HAS{"Key already exists?"}
    HAS -->|No| A["Store key/value -> accept=true"]
    HAS -->|Yes, no compareValues| R["accept=false"]
    HAS -->|Yes, with compareValues| C{"compareValues(old,new)?"}
    C -->|No| R
    C -->|Yes| CAS["replace(key,old,new) atomic"]
    CAS -->|Succeeded| A
    CAS -->|Failed| RETRY["Re-evaluate per store/selector semantics"]
~~~

This is a **conceptual diagram**, not modeling every internal contention-loop detail of the implementation. The key takeaway is that **accepting a new key or replacing a value must rely on atomic operations**, never separate `get` then `put` calls.

### 3.2. The default value is not business state

When no `valueStrategy` is supplied, the selector uses the **message timestamp header** as the metadata value (Javadoc describes its hex representation). The timestamp is stored simply to provide a valid value; **it is not proof that the task committed**, nor is it an expiration or business checkpoint.

If you want to store a **sequence number**, **version**, **watermark**, or another meaningful value, supply an explicit `valueStrategy` and test the comparison logic. Never treat timestamps as business ordering.

### 3.3. Four questions you cannot skip

| Question | If left unanswered |
| --- | --- |
| What does the key **describe**? | Easy to accidentally drop valid messages or accept duplicates |
| What **semantics** does the value carry? | May overwrite checkpoints wrongly when using `compareValues` |
| Is the store **atomic/durable**? | Two instances both accept; restarts forget state |
| Does `accept=true` mean **received** or **completed**? | Business operations may be lost on crash or retry |

## 4. ConcurrentMetadataStore is the foundation of the decision

`ConcurrentMetadataStore` extends `MetadataStore` with two crucial operations:

~~~java
String oldValue = store.putIfAbsent(key, value);
boolean changed = store.replace(key, expectedOldValue, newValue);
~~~

- `putIfAbsent` **returns `null` when the write succeeds**, or returns the existing value if the key already exists.
- `replace` only updates the value if the current value equals `expectedOldValue`; `true` means the swap succeeded.

These operations are **atomic within the backend's contract**, helping prevent race conditions across messages sharing a key.

### 4.1. Why not use get then put?

~~~text
Instance A: get(K) -> null
Instance B: get(K) -> null
Instance A: put(K, A)
Instance B: put(K, B)
Result: both A and B believe they own processing of K.
~~~

With atomic `putIfAbsent`:

~~~text
Instance A: putIfAbsent(K, A) -> null      -> accepted
Instance B: putIfAbsent(K, B) -> "A"       -> rejected
~~~

**Scale-out note:** `SimpleMetadataStore` can be atomic within a single instance, but **each JVM having its own store** provides no distributed coordination. You need a genuinely shared store when multiple pods/instances can see the same operation.

### 4.2. Verify backend correctness

For `JdbcMetadataStore`, Redis, MongoDB, ZooKeeper, or other supported backends, check:

1. Are `putIfAbsent` and `replace` genuinely atomic in your deployed topology?
2. Can keys be lost on restart, eviction, failover, or transaction rollback?
3. Is there unusual contention or latency when many consumers compete on a key?
4. Are namespaces/regions/prefixes used so multiple flows do not collide?
5. Does the backend have specific limitations—such as `replace` in certain Redis Cluster configs?
6. Are retention, deletion, and key-protection policies appropriate for business data?

**Checking the implementation name alone is insufficient:** test durability and atomicity in your real deployment topology.

## 5. Key strategy: choosing the right duplicate identifier

A good `keyStrategy` must derive from a concrete **business contract** or **checkpoint contract**, not merely the message object.

### 5.1. Common key examples

| Flow | Suggested key | Must verify |
| --- | --- | --- |
| HTTP create order | tenant + operation + order ID/version | Client keeps key on retries; body fingerprint unchanged |
| SFTP file-level | remote source + path + file generation | Is an overwritten file with the same name a new version? |
| File splitter per-line | file generation + line/record ID | Could reordering or inserting lines shift line numbers? |
| JMS/AMQP event | tenant + business event ID | Does republishing preserve the event ID? |
| Kafka transport record | topic + partition + offset | Only prevents re-reading the same record, not republishing the same event |
| Kafka business event | producer event ID/operation ID | Stable across resends and backfills? |
| JDBC poller | business row ID + action/version | Could a second row represent the same operation? |
| Workload pipeline | workflow run + operation/target | Do retries of the same job preserve the operation identifier? |

**`MessageHeaders.ID` is usually unsuitable as a business idempotency key** because each delivery or transformation can generate a new message ID. `MessageHeaders.TIMESTAMP` is not a business ID either.

### 5.2. Keys must be properly namespaced

~~~text
Poor:
    order-971

Better:
    order:create:v1:tenant-T42:order-971

Different operation:
    order:cancel:v1:tenant-T42:order-971
~~~

If multiple flows share one metadata store, a bare `order-971` key causes collisions between `CREATE_ORDER` and `CANCEL_ORDER`. Business-meaningful prefixes prevent collisions.

### 5.3. Missing or invalid keys

When a message lacks a tenant ID or operation ID:

- **Never** fall back to an empty string or `"UNKNOWN"` for all messages.
- Route to validation/quarantine with a clear reason.
- Or use a fallback **permitted by the business contract** and covered by tests.

An invalid shared key can cause worse **data loss** than an explicit exception, because subsequent valid messages get rejected by the selector as duplicates.

### 5.4. Hashing and data protection

If a key contains emails, personal identifiers, or sensitive data, consider a **namespaced hash or protected reference** instead of putting raw PII into metadata stores, metric labels, or logs. Keep keys stable across restarts, migrations, and replays; changing hash algorithms or salts requires a compatibility plan.

## 6. Value strategy: meaning of the stored value

The **key** identifies the group of messages to track; the **value** determines what information is stored for that key.

Not every case needs a complex value. **Accept-first-seen** works with the default value at the selector level, while other scenarios need:

- Document version or revision.
- Sequence number of a record in a file.
- Processing watermark for an ordered event stream.
- Source object checksum or ETag.
- Markers/checkpoints governed outside the selector.

### 6.1. Key/value table

| Scenario | Key | Value | Accept rule |
| --- | --- | --- | --- |
| Accept operation first time only | business operation ID | Timestamp/default | Accept if key does not exist yet |
| Increasing update versions | entity ID | version number | Accept if key is new or new version qualifies |
| File split by sequence | file generation | sequence number | Accept increasing numbers if ordering is guaranteed |
| Detect modified file | file identity/path | file version/checksum | Accept when version genuinely changes |
| Poller checkpoint | source stream ID | event watermark | Advance watermark only when safe with ordering/commits |

**Never use values to store raw payloads, access tokens, or secrets.** A metadata store holds technical markers, not secured business data records.

### 6.2. When you need to store business outcomes

`MetadataStoreSelector` is not designed to replace a **result cache, inbox record, or audit store**. When you must return the HTTP response of a completed request, store `COMPLETED` and the result reference in a dedicated business store with proper transactions and unique keys.

A `seen` timestamp does not tell you whether an HTTP callback succeeded, a Kafka offset committed, or a bank transfer was confirmed.

## 7. compareValues: conditionally accepting new values

Since **Spring Integration 5.3**, `MetadataStoreSelector` supports **`compareValues`** via a `BiPredicate<String,String>`.

- First parameter: **old value** currently in the metadata store.
- Second parameter: **new value** computed from the incoming message.
- If the predicate returns `true`, the selector attempts to update the old value to the new value via atomic `replace`.
- If the predicate returns `false`, the message is rejected for not meeting the update condition.

~~~java
selector.setCompareValues((oldValue, newValue) ->
        Integer.parseInt(newValue) > Integer.parseInt(oldValue));
~~~

This is an example of **accepting only increasing versions**. Validate types, ranges, and encoding—never assume every string parses into a valid integer.

### 7.1. Mistakes with compareValues

| Mistake | Consequence |
| --- | --- |
| Swapping `old/new` argument order | Accepts older versions, rejects newer ones |
| Lexicographical string comparison | `"10"` is treated as smaller than `"9"` |
| Comparing delivery timestamps as business versions | Later duplicate is treated as "newer" |
| Not handling nulls/malformed formats | Unhandled exceptions enter error paths |
| Using a high-watermark for out-of-order events | Drops unprocessed events with smaller numbers |
| Overwriting markers before processing commits | Restarts skip unfinished operations |
| Keying by file path without generation/version | New file with same name gets wrongly rejected |

### 7.2. High-watermarks only work with ordering guarantees

Suppose a file has lines 1, 2, 3 and the selector stores **max sequence**:

~~~text
Old checkpoint: 1
Receive line 3 -> compareValues(1,3) = true -> store 3
Receive line 2 -> compareValues(3,2) = false -> discard line 2
~~~

If line 2 **was never processed**, this high-watermark approach loses data. Therefore:

- Only use monotonic watermarks when processing is **strictly ordered** and checkpoints update only after committed results.
- For parallel/out-of-order processing, use **per-event/per-line keys** or a structure tracking sequence gaps.
- A boolean predicate comparing two values **does not create contiguous-commit guarantees**.

### 7.3. compareValues is not a business compare-and-set

`ConcurrentMetadataStore.replace` prevents overwriting a store entry that changed unexpectedly. Yet accepting a message **does not mean business side effects committed atomically with that value**. Coordinate with transactions/inboxes or reconciliation to cover the failure window.

## 8. Plain Java example: first-seen selector

This example illustrates the API in Spring Integration versions providing `MetadataStoreSelector`, `SimpleMetadataStore`, and `MessageBuilder`.

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class FirstSeenDemo {
    public static void main(String[] args) {
        ConcurrentMetadataStore store = new SimpleMetadataStore();

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    String tenant = message.getHeaders().get("tenantId", String.class);
                    String operationId =
                            message.getHeaders().get("operationId", String.class);
                    if (tenant == null || operationId == null) {
                        throw new IllegalArgumentException("Missing stable business key");
                    }
                    return "order:create:" + tenant + ":" + operationId;
                },
                store
        );

        Message<String> first = MessageBuilder.withPayload("create-order")
                .setHeader("tenantId", "T42")
                .setHeader("operationId", "ORD-971")
                .build();

        Message<String> redelivery = MessageBuilder.withPayload("create-order")
                .setHeader("tenantId", "T42")
                .setHeader("operationId", "ORD-971")
                .build();

        System.out.println(selector.accept(first));      // true
        System.out.println(selector.accept(redelivery)); // false
    }
}
~~~

**Meaning:** Two messages with different Spring message IDs still produce the same business key. The first is accepted and recorded; the second is rejected. The example runs in **one JVM** with no transactions or restart durability.

### 8.1. Never use SimpleMetadataStore as production proof

After a restart, a fresh `SimpleMetadataStore` holds no prior keys and `selector.accept(redelivery)` returns `true`. Across multiple instances, separate JVMs can each return `true`.

To deduplicate across clusters and restarts, choose a **persistent shared `ConcurrentMetadataStore`** or design a **transactional inbox** aligned with business correctness.

## 9. Java example: valueStrategy and compareValues

A clear use case is processing **the latest revision** of a document from a source with numbered revisions where business rules only care about increasing versions.

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class RevisionDemo {
    public static void main(String[] args) {
        ConcurrentMetadataStore store = new SimpleMetadataStore();

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> "doc:" + require(message, "documentId"),
                message -> require(message, "revision"),
                store
        );

        selector.setCompareValues((oldValue, newValue) ->
                Long.parseLong(newValue) > Long.parseLong(oldValue));

        Message<String> rev1 = msg("A-42", "1");
        Message<String> rev1Again = msg("A-42", "1");
        Message<String> rev2 = msg("A-42", "2");
        Message<String> stale = msg("A-42", "1");

        System.out.println(selector.accept(rev1));       // true
        System.out.println(selector.accept(rev1Again));  // false
        System.out.println(selector.accept(rev2));       // true
        System.out.println(selector.accept(stale));      // false
    }

    static String require(Message<?> message, String header) {
        String value = message.getHeaders().get(header, String.class);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing header: " + header);
        }
        return value;
    }

    static Message<String> msg(String documentId, String revision) {
        return MessageBuilder.withPayload("document-data")
                .setHeader("documentId", documentId)
                .setHeader("revision", revision)
                .build();
    }
}
~~~

### 9.1. Conditions for using this example safely

A revision selector fits when **only the highest revision** matters. If the business requires executing **every revision in order**, accepting revision 4 before revision 3 and then dropping revision 3 is **wrong**.

Before using `compareValues`, confirm:

1. Are events **latest snapshots** or **sequential deltas**?
2. Can revisions arrive out of order?
3. Must every revision be processed?
4. Does updating the metadata value share a transaction with the business effect?
5. Must external outcomes be verified before raising the watermark?

## 10. Combining MetadataStoreSelector with IdempotentReceiverInterceptor

`MetadataStoreSelector` makes the decision. `IdempotentReceiverInterceptor` is an **AOP Advice** applied to `MessageHandler.handleMessage()` on a configured endpoint.

When the selector rejects a message:

- If **no** `discardChannel` is set and throwing on rejection is disabled, `IdempotentReceiverInterceptor` may **forward the message to the handler with the `duplicateMessage=true` header** so the handler decides.
- If a **discard channel** or `throwExceptionOnRejection` is configured, rejected messages **are not sent to the target handler** per configured behavior.

This differs from assuming "selector returns false means the message is dropped in every case." Test the real execution path.

### 10.1. Example attaching advice in Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
public class IdempotentEndpointConfiguration {

    @Bean
    public MetadataStoreSelector orderMetadataSelector(
            ConcurrentMetadataStore sharedMetadataStore) {
        return new MetadataStoreSelector(
                message -> "orders:v1:"
                        + message.getHeaders().get("tenantId")
                        + ":"
                        + message.getHeaders().get("operationId"),
                sharedMetadataStore
        );
    }

    @Bean
    public IdempotentReceiverInterceptor orderIdempotentAdvice(
            MetadataStoreSelector orderMetadataSelector,
            MessageChannel duplicateOrdersChannel) {

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(orderMetadataSelector);
        advice.setDiscardChannel(duplicateOrdersChannel);
        return advice;
    }

    @Bean
    public IntegrationFlow orderProcessingFlow(
            OrderProcessor orderProcessor,
            IdempotentReceiverInterceptor orderIdempotentAdvice) {
        return IntegrationFlow.from("ordersInputChannel")
                .handle(orderProcessor, "process",
                        endpoint -> endpoint.advice(orderIdempotentAdvice))
                .get();
    }
}
~~~

**Requirements for using the sample code:**

- `OrderProcessor` is application-defined.
- `ordersInputChannel` and `duplicateOrdersChannel` must be declared with proper subscribers.
- `sharedMetadataStore` must fit durability/concurrency needs. Never use `SimpleMetadataStore` in multi-instance production if shared state is required.
- `tenantId`/`operationId` headers must be populated and validated upstream.
- Check builder APIs/overloads against your project's Spring Integration version.

**Failure risk:** If the metadata key is saved and `OrderProcessor.process` fails, later messages may be rejected. Wrapping the handler with advice **does not close** the failure window between store write and business commit.

### 10.2. When duplicates need a business response

For an HTTP inbound gateway, routing duplicates to a one-way `duplicateOrdersChannel` may **fail to send a reply to the caller**. Clients experience timeouts or contract violations.

If the API requires idempotent HTTP responses, design the endpoint to **read the result cache/inbox and return the same result**, or return `PENDING`/`CONFLICT`. Never substitute a discard-only handler for a request-reply contract without tests.

### 10.3. Using MessageFilter when appropriate

`MetadataStoreSelector` can also be passed to a `MessageFilter`. The filter then decides the **accept/reject** path ahead of downstream handlers rather than wrapping a handler as advice.

Comparison:

| Criterion | `MessageFilter` | `IdempotentReceiverInterceptor` |
| --- | --- | --- |
| Position | Explicit filter endpoint in flow | Advice attached to handler |
| Selector logic | Can use `MetadataStoreSelector` | Can use `MetadataStoreSelector` |
| Duplicates | Explicit discard/reject route | Marks header or discards per config |
| Applicability | Filtering messages before a handler | Idempotent receiver pattern at endpoint |
| Not guaranteed | Business transactions or durability | Business transactions or durability |

## 11. MetadataStoreSelector and File/SFTP inbound adapters

File and SFTP adapters typically have **file discovery/download filters** such as accept-once or persistent accept-once. They answer:

> Should this source file be picked up or downloaded again during the current poll?

Downstream `MetadataStoreSelector` answers a different question:

> Has the message/record derived from this file already been processed or selected before?

### 11.1. File-level filters differ from record-level selectors

~~~text
SFTP /orders/import-2026-11-23.csv
  Line 1: ORD-971 -> business COMPLETED
  Line 2: ORD-972 -> handler FAILED
  Line 3: ORD-973 -> business COMPLETED

File filter: has the file been received/downloaded?
Record selector: what key/value does each operation carry?
Inbox: what business outcome did each operation reach?
~~~

If the file filter marked the file while line 2 remained unprocessed, the file cannot be considered finished. Track state/recovery at the record level and plan file re-reading where appropriate.

### 11.2. Configuring MetadataStoreSelector for FileSplitter

`FileSplitter` can emit a `sequenceNumber` header when configured. An example uses **file identity as the key**, **sequence number as the value**, and `compareValues` to accept strictly increasing numbers.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

// Safe ONLY when lines execute in order with reliable checkpoints.
MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> message.getHeaders()
                .get(FileHeaders.ORIGINAL_FILE, java.io.File.class)
                .getAbsolutePath(),
        message -> String.valueOf(message.getHeaders()
                .get(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER)),
        sharedStore
);
selector.setCompareValues((oldValue, newValue) ->
        Integer.parseInt(oldValue) < Integer.parseInt(newValue));
~~~

In this example, `sharedStore` is an application-configured `ConcurrentMetadataStore`. The logic follows the pattern documented by Spring Integration, yet **does not by itself guarantee zero lost lines after a crash**.

### 11.3. Two hazards of file high-watermarks

**Hazard A — out-of-order processing:**

~~~text
File F has lines 1, 2, 3.
Line 3 is selected before line 2.
Store high-watermark = 3.
Line 2 arrives later -> rejected even though never business-committed.
~~~

**Hazard B — selector marks before commit:**

~~~text
Line 2 is accepted, store = 2.
Business handler fails before persisting result.
Application restarts and re-reads line 2.
Selector sees old = 2, new = 2 -> rejects.
~~~

To guarantee per-line processing, consider **per-line operation keys + transactional inbox** or advancing checkpoints **only after** commit proof and ordering guarantees.

### 11.4. File identity must include generation

If a partner overwrites the same file path later in the day, keying solely by absolute path shares checkpoints with the previous file. Define a contract specifying **file immutability**, **version/ETag/checksum**, upload-complete markers, retention, and whether reprocessing is permitted.

## 12. SFTP streaming and session lifecycles

An SFTP streaming inbound adapter carries sessions/resources that must close on time; `FileSplitter` or downstream flows may be involved in releasing the session once the stream is consumed.

When placing a selector:

- Never let a duplicate rejection skip closing resources.
- Ensure error/recovery paths still close streams/sessions per adapter and splitter contracts.
- If only some records finished processing, define how the remote file can be replayed.
- Design persistent file filters or metadata stores consistently with local staging/checkpoints.
- Avoid holding SFTP sessions open during long downstream retries.

**Downloaded files or closed streams do not mean all records committed at the destination.** Separate transfer state from business processing state.

## 13. HTTP inbound: is a selector enough for idempotent responses?

Suppose a client calls:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: create-order-T42-ORD-971

{"tenantId":"T42","orderId":"ORD-971","amount":150000}
~~~

If the HTTP gateway finds the key unseen, the system creates the order and returns `201` with the order reference. If the client times out, the retry sends the same key with a **new Spring Message ID and timestamp**. A selector keyed by the business key detects the duplicate.

Yet **detecting duplicates alone is insufficient**. HTTP contracts typically need:

| State for same key | Appropriate response |
| --- | --- |
| **`COMPLETED`**, same fingerprint | Return stored result per contract |
| **`PROCESSING`** | Return pending/accepted or wait within latency budget |
| **`FAILED_FINAL`** | Return stored business error |
| **`OUTCOME_UNKNOWN`** | Return status requiring reconciliation; never fake success |
| Same key, **different payload** | `409 Conflict` or equivalent contract error |

Therefore, for HTTP gateways needing meaningful idempotent responses, use a **business inbox/result store** and let the gateway return a response rather than relying solely on `discardChannel`.

### 13.1. What happens if a selector rejects before the gateway replies?

If duplicates route to a `DirectChannel` that only logs, the caller may receive no expected reply and time out. Even though the selector's boolean logic worked, the HTTP contract breaks.

**Test criterion:** Two requests with the same key and payload must receive consistent responses; the second request creates no extra side effects.

## 14. JMS, AMQP, and Kafka: duplicates from redelivery

`MetadataStoreSelector` can sit near a handler receiving broker messages. However, brokers/containers manage **ack/nack, transactions, redelivery, offset commits, and DLQ/DLT** via their own mechanics.

| Source | Duplicate happens when | Must verify additionally |
| --- | --- | --- |
| JMS | Session rollback, missing acknowledgement, republish | Transacted session, redelivery count, DLQ policy |
| AMQP/RabbitMQ | Nack/requeue, consumer crash, republish | Ack mode, DLX, requeue, and listener container |
| Kafka | Consumer rebalance, uncommitted offset, republish | Offsets/partitions, transactions, error handler, DLT |

### 14.1. Transaction boundaries

If the selector writes the key to the metadata store **outside the business transaction** and the handler fails:

~~~text
1) selector.accept(K) = true; store now holds K
2) handler DB write fails -> business transaction rolls back
3) JMS/AMQP/Kafka redelivers K
4) selector.accept(K) = false
5) message may be discarded/acked per adapter configuration
~~~

The result can be an **unfinished business operation whose source message will never be reprocessed**.

Mitigations depending on architecture:

- Use stores and business transactions with verified coordinated semantics.
- Use a transactional inbox/unique constraint to record results and states in the same DB transaction.
- Use `PROCESSING`/`COMPLETED` with explicit recovery logic rather than a bare `seen` marker.
- When downstream commit status is unknown, reconcile before replaying.
- Test real ack/offset behavior in a broker test environment.

### 14.2. Kafka offsets and business event IDs

~~~text
Transport identity:
    topic=orders, partition=4, offset=101

Business identity:
    tenant=T42, operation=CREATE_ORDER, orderId=ORD-971
~~~

If the same event is republished at offset 205, a `topic+partition+offset` key **will not** detect the business duplicate. Choose keys by intent: preventing reprocessing of the same transport record vs. preventing repeating the same operation across deliveries/sources.

### 14.3. Note on broker exactly-once

A broker or framework may support strong transactions/semantics within a **specific scope**. Never assume it guarantees exactly-once side effects across external DBs, REST APIs, SFTP, or non-broker services. Idempotent Receivers and downstream controls remain essential.

## 15. JDBC inbound: row polling and selectors

A JDBC inbound adapter can poll `NEW` records and emit messages. Two IDs exist:

- **Row ID** in the staging table: identifies a physical row.
- **Business operation ID:** identifies a meaningful business task.

If upstream inserts two distinct rows for the same operation, a row-ID selector misses the business duplicate.

### 15.1. Example row states

~~~text
NEW -> CLAIMED -> PROCESSING -> COMPLETED
                    |
                    +-> RETRYABLE_FAILURE
                    |
                    +-> NEEDS_RECONCILIATION
~~~

With multiple active pollers, use row claiming with proper locking/optimistic versioning/transactions; `SELECT ... WHERE processed = false` alone cannot stop two workers from picking the same row.

### 15.2. Why use unique constraints?

Local DB side effects can share a transaction with an inbox marker:

~~~sql
-- Illustrative schema, not a JDBC inbound adapter configuration.
CREATE TABLE inbound_inbox (
    tenant_id           VARCHAR(100) NOT NULL,
    operation_key       VARCHAR(240) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    operation_state     VARCHAR(40) NOT NULL,
    result_ref          VARCHAR(240),
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

Unique constraints protect against concurrent races at the DB layer. If the message is already `COMPLETED`, retries return the cached result; if still `PROCESSING`, use leases/reconciliation.

**`MetadataStoreSelector` does not manage these states automatically.** A business inbox is a complementary design, not merely swapping metadata store types.

## 16. Critical failure window: saving keys before business commit

When using `MetadataStoreSelector`, accepting a key can **write the key/value to the store before the business handler finishes**.

~~~mermaid
sequenceDiagram
    participant B as Broker / Adapter
    participant S as MetadataStoreSelector
    participant M as MetadataStore
    participant H as Business handler
    participant D as Database
    B->>S: Message operation=ORD-971
    S->>M: putIfAbsent(K, value)
    M-->>S: null (new key)
    S->>H: accept=true
    H->>D: Write business data
    Note over H,D: Crash/rollback before commit
    B->>S: Redelivery same operation K
    S->>M: putIfAbsent(K, value2)
    M-->>S: oldValue (key already exists)
    S-->>B: accept=false
~~~

In this scenario, a metadata key exists while the business effect **does not**. If the duplicate is discarded and the source acks, the operation can be lost.

### 16.1. Separating three states

| State | Can be inferred from basic `MetadataStoreSelector`? | What is needed |
| --- | --- | --- |
| **`SEEN` / `CLAIMED`** | Yes: key has been stored | Metadata store |
| **`COMPLETED`** | **No** | Business record/transaction/result store |
| **`OUTCOME_UNKNOWN`** | **No** | Reconciliation after timeout/crash |

This is why `MetadataStoreSelector` works well **as a selector/guard for well-defined cases**, but should never be the sole basis for claiming **end-to-end exactly-once**.

### 16.2. When is "mark before processing" acceptable?

Some flows tolerate those semantics—for instance, suppressing resends of **non-critical notifications** with no strict durability requirement and acceptable crash-loss odds. Document the **actual delivery guarantee**, owner, and acceptable loss level.

For **orders, payments, valuable data transfers, or critical state updates**, choose stronger outcome protection.

### 16.3. Transactional inbox

A common pattern when business logic shares the same database:

1. Start transaction.
2. Insert/claim row with unique business key.
3. Apply business data changes.
4. Write `COMPLETED` and result to inbox.
5. Commit business data and completion state together.

On rollback, no false `COMPLETED` marker remains. If the event redelivers after commit, read back the saved outcome.

**Note:** If the side effect calls external HTTP/SFTP/JMS, a local DB transaction **does not cover** that system; you need downstream idempotency and/or outbox/reconciliation.

## 17. compareValues is not itself a committed checkpoint

For split files or sequenced sources, `compareValues` is often used as a **high-watermark**. Yet "message N was accepted by the selector" does not mean "every message up to N succeeded."

### 17.1. Conditions for reliable sequence checkpoints

1. **Guaranteed order:** Messages arrive and execute in the expected sequence.
2. **No gaps:** If N is checkpointed, all messages before N are complete or handled per policy.
3. **Post-commit checkpoint:** Values advance only after business outcomes are safe, or via real transactional rollback/checkpointing.
4. **No generation mix-ups:** New files or streams never reuse keys from prior generations.
5. **Clear recovery:** Defined handling when crashes happen between checkpoint and ack.

A `compareValues` checking only `new > old` **satisfies only the first condition arithmetically**, not the other four.

### 17.2. Gap-aware checkpoints

For out-of-order events, you may need:

~~~text
Committed contiguous checkpoint = 40
Events completed after 40: {42, 43}
Event 41 not yet completed

Do not advance committed checkpoint to 43.

When 41 completes:
    41, 42, 43 are all completed
    -> only now advance contiguous checkpoint to 43
~~~

Maintaining a `completed gaps` structure and separate transactions belongs to the application or a dedicated checkpoint system; **it does not come automatically from a single `MetadataStoreSelector` string value**.

## 18. Difference between a metadata store and a message store

Similar names, different roles:

| Store type | Typical content | Role |
| --- | --- | --- |
| **`MetadataStore`** | String key/value pairs | Checkpoints, markers, versions, filter state |
| **`MessageStore`** | Spring `Message` objects/groups per implementation | Persists messages for queues, aggregators, or related patterns |
| **Business inbox** | Operation ID, payload fingerprint, state, result | Guarantees business workflows and idempotent responses |
| **Outbox** | Outbound events or commands awaiting send | Coordinates side effects to external systems |
| **DLQ / quarantine** | Failure records or unprocessable messages | Investigation, data fixes, replay |

`ConcurrentMetadataStore` provides atomic key/value operations. It **does not replace** full message persistence, retry queues, or business result stores.

### 18.1. Why not store payloads in metadata values?

`MetadataStoreSelector` values are designed for **lookup/comparison**, not for:

- Storing large binary files or complex JSON payloads.
- Recording raw access tokens, cookies, passwords, or PII.
- Replacing multi-step business state tracking.
- Creating immutable audit evidence per compliance standards.

When full failed messages must be retained, use a dedicated failure store or durable broker with clear schemas, retention, and permissions.

## 19. Configuring durable and safe stores

Spring Integration offers store implementations for diverse needs, including `SimpleMetadataStore`, `PropertiesPersistingMetadataStore`, `JdbcMetadataStore`, `RedisMetadataStore`, `MongoDbMetadataStore`, `ZookeeperMetadataStore`, and others depending on version/module.

### 19.1. Comparing pros and cons

| Store | Strengths | Limitations to evaluate |
| --- | --- | --- |
| `SimpleMetadataStore` | Compact, simple, handy for unit tests | In-memory; lost when JVM stops |
| Properties-backed | Can persist state to a file | Flush/restart/crash and multi-instance sharing need careful review |
| JDBC-backed | Durable, leverages DB ops and transactions | Locking, schema, throughput, transaction boundaries |
| Redis-backed | Shared, low latency in fitting topologies | Persistence/eviction/failover and atomic ops per configuration |
| MongoDB-backed | Shared document persistence | Verify write concerns and atomicity per contract |
| ZooKeeper-backed | Distributed coordination state for specific cases | Availability/ops overhead and ACLs |
| Custom `ConcurrentMetadataStore` | Tunable for bespoke systems | Must implement `putIfAbsent`, `replace`, and race handling accurately |

### 19.2. An operational caveat with Redis Cluster

Spring Integration Redis documentation notes that `RedisMetadataStore.replace()` has limitations in **Redis Cluster** because the `WATCH` mechanism used for atomicity is not supported in the described cluster setup. Never **assume** every Redis deployment delivers identical `compareValues`/CAS guarantees.

When using `compareValues` with Redis or any distributed backend, **verify exact version limits, topology, atomic ops, and concurrency tests**—never test only single-instance `putIfAbsent`.

### 19.3. PropertiesPersistingMetadataStore and crashes

A properties-backed store may flush to disk only upon **clean `ApplicationContext` shutdown** unless flushed via supported hooks. A crash or `kill -9` can lose recent state. For critical ingestion, never rely on file-based persistence without crash testing.

### 19.4. Namespacing and access control

One shared store may hold keys from many flows. Enforce:

- Prefixes per application/flow/environment/tenant.
- Separation of production and dev keys if environments share a backend.
- ACLs/DB permissions limiting who can read/edit/delete metadata.
- Backups, retention, cleanup, and capacity planning.
- Alerts on abnormal bulk key deletions.

Accidentally wiping a metadata store can make **thousands of old messages look brand new**, triggering duplicate side effects.

## 20. When the metadata store is unavailable

Suppose the selector tries `putIfAbsent(K,V)` and Redis/DB times out.

Options:

| Approach | When fitting | Risk |
| --- | --- | --- |
| **Fail closed**: throw exception/hold message at source | Sensitive business operations | Backlog grows; needs retries and alerts |
| **Quarantine**: save failure in a separate durable store | Independent failure store exists and contract allows | Must ensure no ack before persistence |
| **Fail open**: bypass idempotency guard | Only with strong approved downstream controls | Increases duplicate side effects |
| **Pause ingestion** | Broad store outage while source can buffer | Lag, SLAs, and recovery runbooks |

For order creation or sensitive writes, **automatic fail-open** is usually high risk. If the metadata store is the sole deduplication layer, never silently continue unchecked.

### 20.1. Store errors vs. downstream errors

If a DB metadata store fails, retrying inside the selector may recover from transient connection blips. However, retrying will not fix bad schemas, invalid keys, or missing permissions.

Avoid:

~~~text
metadata store timeout
 -> infinite selector retries
 -> consumer thread held
 -> broker backlog grows
 -> source keeps redelivering
 -> retry storm
~~~

Cap attempts, apply backoff/jitter per library, add circuit breakers when needed, and alert operations that **deduplication is unavailable**.

## 21. Choosing between first-seen selectors and compareValues

| Requirement | Recommendation |
| --- | --- |
| Accept only unseen business IDs | First-seen `putIfAbsent` by operation key |
| Only care about snapshots with newer versions | `compareValues(newVersion > oldVersion)` if versions are monotonic and out-of-order drops are intended |
| Must process every event in order | Do not use a simple high-watermark if gaps can occur; use ordered processing/safe checkpoints |
| Must return the same HTTP result on retry | Business inbox/result store, optionally paired with a selector |
| Deduplicate across two sources | Business-layer key, shared store, or unique constraint |
| Never lose operations across crashes | Transactional inbox/outbox + proper ack/commit |
| Avoid re-downloading old files only | Persistent file filter at the source layer |
| Detect same key with different body | Fingerprint/compare business inputs separately, not default timestamps/values |

**Never pick `compareValues` just to "allow retries."** Retrying an incomplete operation requires business state and outcome verification; incrementing a numeric metadata value is not a full state machine.

## 22. XML/annotation configuration: ways to attach a selector

Java DSL is one option, though older Spring Integration systems may use XML namespaces, endpoint annotations, or Java config.

### 22.1. XML fragment example

~~~xml
<!-- Illustrates idempotent-receiver attributes; requires real namespaces,
     bean names, and endpoint from application configuration. -->
<int:idempotent-receiver
    id="ordersIdempotency"
    endpoint="ordersHandler"
    metadata-store="sharedMetadataStore"
    key-expression="'orders:' + headers['tenantId'] + ':' + headers['operationId']"
    discard-channel="duplicatesChannel"
    throw-exception-on-rejection="false" />
~~~

Verify **namespace schemas/attributes** for your Spring Integration version and confirm endpoint `ordersHandler` exists. This snippet does not create `sharedMetadataStore`, `duplicatesChannel`, or business transactions on its own.

### 22.2. With compareValues

~~~xml
<!-- value and compareValues can be configured via strategies/beans
     per your version's XML schema. -->
<int:idempotent-receiver
    endpoint="revisionHandler"
    metadata-store="sharedMetadataStore"
    key-expression="'doc:' + headers['documentId']"
    value-expression="headers['revision'].toString()"
    compare-values="revisionComparePredicate" />
~~~

Bean `revisionComparePredicate` must be a `BiPredicate<String,String>` taking **old then new**. Before production, verify data types and version semantics.

### 22.3. Annotation endpoints

Spring Integration supports `@IdempotentReceiver` on messaging endpoints in suitable Java config setups. The annotation references an interceptor bean; it **does not generate key/value strategies** and **does not attach idempotency to every handler automatically**.

Whether using XML, Java DSL, or annotations, verify:

1. Does the advice/filter actually execute before the side effect being protected?
2. Are duplicates marked, sent to a discard channel, or throwing an exception?
3. Do error/ack semantics align with the inbound adapter?
4. Does selector state stay durable and consistent across restarts/scale-out?

## 23. Unit testing the selector

First verify **boolean decisions** and metadata value updates independently of adapters/brokers.

### 23.1. JUnit 5: accept and reject

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MetadataStoreSelectorTest {

    @Test
    void acceptsOnlyFirstSeenOperationKey() {
        SimpleMetadataStore store = new SimpleMetadataStore();
        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> String.valueOf(
                        message.getHeaders().get("businessOperationId")),
                store);

        var first = MessageBuilder.withPayload("payload-A")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        var duplicate = MessageBuilder.withPayload("payload-A")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        var anotherOperation = MessageBuilder.withPayload("payload-B")
                .setHeader("businessOperationId", "create:T42:972")
                .build();

        assertTrue(selector.accept(first));
        assertFalse(selector.accept(duplicate));
        assertTrue(selector.accept(anotherOperation));
    }

    @Test
    void acceptsIncreasingRevisionOnly() {
        SimpleMetadataStore store = new SimpleMetadataStore();
        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> String.valueOf(
                        message.getHeaders().get("documentId")),
                message -> String.valueOf(
                        message.getHeaders().get("revision")),
                store);
        selector.setCompareValues((oldValue, newValue) ->
                Long.parseLong(newValue) > Long.parseLong(oldValue));

        var v1 = MessageBuilder.withPayload("doc")
                .setHeader("documentId", "D-100")
                .setHeader("revision", 1)
                .build();
        var v2 = MessageBuilder.withPayload("doc")
                .setHeader("documentId", "D-100")
                .setHeader("revision", 2)
                .build();

        assertTrue(selector.accept(v1));
        assertFalse(selector.accept(v1));
        assertTrue(selector.accept(v2));
        assertFalse(selector.accept(v1));
        assertEquals("2", store.get("D-100"));
    }
}
~~~

In the first test, `String.valueOf(null)` produces `"null"` if a header is absent; that is **not production validation**. This test intentionally focuses on selector APIs. In real applications, the key strategy must reject missing/invalid headers before touching the store.

### 23.2. Testing compareValues across keys

Do not test only one key. Verify:

- Document A's version does not affect document B.
- `old=9, new=10` is accepted via numeric comparison.
- `old=10, new=9` is rejected.
- `old=10, new=10` is rejected.
- Invalid revisions do not corrupt the store or write bad values.
- Concurrent threads submitting revisions accept **only according to the atomic policy**.

### 23.3. Testing handler invocations

A correct boolean selector is not enough. With `IdempotentReceiverInterceptor`, test:

1. First-seen message → business handler runs.
2. Duplicate with discard channel → business handler does not run a second time.
3. Duplicate without discard → `duplicateMessage` header is handled per contract.
4. Discard handler fails → upstream and ack behavior is verified.
5. Handler fails after selector accept → redeliveries are not lost due to stale markers.

## 24. Concurrency and crash-recovery testing

### 24.1. Multiple threads with the same key

Goal: prove **atomic `putIfAbsent` accepts the exact right count** per contract.

~~~text
Setup:
    20 concurrent tasks
    same tenant=T42 and operationId=ORD-971
    same shared ConcurrentMetadataStore

Expected for first-seen selector:
    accept=true for exactly 1 task
    accept=false for 19 tasks

However:
    the accepted task's business outcome must still be verified.
~~~

This tests atomicity **at the selector layer**, which alone is insufficient to claim business exactly-once.

### 24.2. Multiple instances

Run two consumers against the same shared store:

- Instance A receives message `K`.
- Instance B receives duplicate `K` simultaneously.
- Only one instance accepts under first-seen semantics.
- Restart both; `K`'s state remains when the store is durable.
- Exercise failover/eviction matching real topology.

If a test runs two threads using a single `SimpleMetadataStore`, it **fails to test per-JVM isolated-store bugs**.

### 24.3. Failure injection matrix

| Failure point | What to observe |
| --- | --- |
| Before `putIfAbsent` | No marker written; source can retry |
| After `putIfAbsent`, before handler | Marker exists while business never ran |
| After local DB write, before commit | Does rollback leave a bad marker behind? |
| After DB commit, before broker ack | Does redelivery avoid a second side effect? |
| After HTTP send, before response | Is `OUTCOME_UNKNOWN` tracked and reconciled? |
| During concurrent `replace` | Could values regress or overwrite wrongly? |
| Metadata store unavailable | Does it fail safe or bypass dedup dangerously? |
| Restart / `kill -9` | Do persistence and resume behave properly? |
| TTL / key cleanup | Do old replays create unexpected duplicates? |

**Test every failure point**, because "happy path passes" does not prove reliability.

## 25. Adapter and ack/offset testing

### 25.1. File/SFTP

- File is downloaded once and filtered on subsequent polls per contract.
- App restarts do not unintentionally re-read files when the metadata store is durable.
- If one record in a file fails, unfinished records remain recoverable.
- Overwritten files at the same path with a new generation are not misclassified.
- If using `FileSplitter` high-watermark, test line 3 arriving before line 2.
- Verify SFTP streams/sessions close after success, rejection, and errors.

### 25.2. HTTP

- Two requests with the same `Idempotency-Key` and body get consistent responses.
- Matching key with a different body returns conflict.
- Second request arriving while the first is `PROCESSING` receives pending/wait per contract.
- Handler failures are not "stamped" as success by the selector.
- Timeout contracts behave cleanly on request-reply gateways.

### 25.3. JMS/AMQP

- After business commit and before ack, broker redelivery creates no new side effects.
- After business rollback, redelivery still has a valid processing path.
- Duplicate discard/reply does not cause premature ack when the operation is incomplete.
- DLQ routing follows broker policy rather than assuming the selector creates it.

### 25.4. Kafka

- Consumer rebalance after local commit creates no duplicates.
- Same business event republished at a new offset is still caught when business dedup is needed.
- Offset commits never advance past unprocessed or unpersisted messages.
- DLT replay preserves the operation key and maintains an audit trail.

### 25.5. JDBC

- Competing pollers claim rows cleanly under transactions.
- Same business operation appearing in two rows is deduplicated at the business level.
- Rollbacks never leave false `COMPLETED` states.
- Outbound HTTP timeouts reconcile before marking rows processed.

## 26. Observability, metrics, and auditing

### 26.1. Metrics to monitor

| Suggested application metric | Meaning |
| --- | --- |
| `metadata_selector_accept_total` | Messages accepted by the selector |
| `metadata_selector_reject_total` | Messages treated as duplicate/stale |
| `metadata_selector_compare_accept_total` | New versions/values accepted |
| `metadata_store_operation_error_total` | Metadata store operation errors |
| `metadata_store_cas_conflict_total` | Contention signals on state updates, if instrumented |
| `metadata_store_latency_seconds` | Store latency impacting throughput/acks |
| `idempotency_conflict_total` | Same key with different business payload |
| `idempotency_in_progress_age` | Age of incomplete operations |
| `inbound_redelivery_total` | Actual redeliveries per adapter |
| `recovery_pending_total` | Messages in failure stores or awaiting reconciliation |
| `replay_total` | Approved replays, succeeded/failed |

These are **application-suggested metric names**, not all auto-created by Spring Integration. Avoid putting message IDs/business IDs in metric labels if that explodes cardinality. Keep correlation IDs in properly access-controlled structured logs/traces.

### 26.2. Sample structured log

~~~json
{
  "event": "metadata_selector.rejected",
  "flow": "sftp-orders-to-jdbc",
  "sourceAdapter": "sftp",
  "operationType": "CREATE_ORDER",
  "operationKeyRef": "sha256-prefix:91ac...",
  "decision": "ALREADY_SEEN",
  "businessOutcome": "UNKNOWN",
  "correlationId": "trace-84021",
  "metadataBackend": "jdbc",
  "observedAt": "2026-11-23T09:00:00Z"
}
~~~

In this log, `ALREADY_SEEN` and `businessOutcome=UNKNOWN` **must not be equated with business success**. A dashboard counting rejected messages without cross-checking completed outcomes can hide dropped operations.

Never log raw access tokens, SFTP passwords, `Authorization` headers, private keys, or sensitive payloads just for deduplication analysis.

### 26.3. Critical alerts

- Rejection rate spikes after a restart or deployment.
- Metadata store resets/evictions or sudden key-space growth.
- Many-to-one key collisions across tenants/operations.
- `compareValues` rejecting batches of out-of-order records.
- High consumer ack rate paired with falling business completion rate.
- Rising operations in `PROCESSING` or `UNKNOWN` state.
- Rising store latency causing poller lag or consumer backlog.
- Replays using new keys causing duplicate side effects.

## 27. Runbook: handling false selector rejections

### 27.1. Symptoms

A batch of orders is missing from the DB after ingesting an SFTP file. Logs show the selector rejected them as duplicates.

### 27.2. Investigation steps

1. Identify the actual **flow, adapter, handler, and selector placement**.
2. Locate the rejected message/business operation key and current metadata value.
3. Check whether `keyStrategy` and `valueStrategy` caused collisions or version errors.
4. Check outcomes in the business DB, inbox, and downstream APIs.
5. Review restart, scale-out, replay, and retry history, and check for out-of-order sources.
6. Verify store atomicity/durability in the active topology.
7. Cross-check ack/offset/file-filter states to see if the source still holds the messages.
8. Never delete keys before confirming whether operations already committed.

### 27.3. Decision matrix

| Finding | Decision |
| --- | --- |
| Key exists, business `COMPLETED` | Keep marker; valid duplicate, do not replay |
| Key exists, business never ran | Repair marker/state and run controlled replay |
| Key exists, downstream outcome unclear | Reconcile before retrying |
| Two keys merged due to bad key strategy | Fix key namespace, identify all skipped operations |
| Store lost keys after restart | Investigate real duplicates, migrate to durable store |
| High-watermark skipped unprocessed sequence | Lower/reset checkpoint carefully or replay gaps via inbox |
| Store outage | Fail safe per policy, prevent bad acks |

### 27.4. When replay is required

Before replaying:

- Obtain owner/approval if the operation has sensitive side effects.
- Identify the **original operation key** and request fingerprint.
- Confirm whether downstream processed the first attempt.
- If metadata must be edited/deleted, target **only the exact key/namespace** with concurrency protection.
- Throttle throughput; run a canary before scaling up for large backlogs.
- Record audit trail: reason, actor, scope, before/after state, and result.

**Never flush an entire Redis instance or metadata table just to fix one skipped order.** That turns thousands of old events back into "new" ones.

## 28. End-to-end scenario: FileSplitter updating reports

An application pulls hourly transaction files via SFTP, splits records with `FileSplitter`, saves reports to JDBC, and emits events to Kafka.

### 28.1. Initial architecture

~~~mermaid
flowchart LR
    SFTP["SFTP inbound + file filter"] --> FILE["Local file / stream"]
    FILE --> SPLIT["FileSplitter"]
    SPLIT --> CH["MessageChannel"]
    CH --> SEL["MetadataStoreSelector"]
    SEL --> JDBC["JDBC business handler"]
    JDBC --> KAFKA["Kafka outbound"]
    SEL --> META["Shared metadata store"]
    KAFKA --> OUTBOX["Delivery / reconciliation status"]
~~~

### 28.2. Scenario A — lines processed in order

File F generation G1 has lines 1, 2, 3. Selector saves `key=F:G1` with values 1, 2, 3 via `compareValues`. Without failures, parallel processing, and with safe checkpoints, the flow skips already-sequenced lines after restart.

### 28.3. Scenario B — failure between select and JDBC commit

Selector accepts line 2 and saves `value=2`. The JDBC transaction fails before commit; the app restarts. Line 2 is re-emitted, yet `compareValues(old=2, new=2)` rejects it.

**Lesson:** A watermark in a metadata store does not prove a JDBC commit. You need a transactional inbox or checkpoints tied to real business outcomes.

### 28.4. Scenario C — out-of-order parallel processing

Lines 2 and 3 dispatch to two workers. Line 3 updates value to 3 before line 2 finishes. The selector then rejects line 2. If every line must be processed, a simple `max sequence` cannot be used.

**Fix:** Switch to `key = file-generation + record-business-id` and store per-record outcomes, or enforce ordered processing with contiguous checkpoints.

### 28.5. Scenario D — Kafka publish succeeded, confirmation lost

JDBC committed and the Kafka producer published the event, but the process crashed before updating send status. On restart, the pipeline may re-emit the event.

**Handling:** Use a transactional outbox or supported publish/reconcile strategy; the Kafka consumer still needs its own idempotency. Inbound `MetadataStoreSelector` cannot guarantee outbound Kafka exactly-once across the DB.

### 28.6. Improved design

~~~mermaid
flowchart TD
    SRC["SFTP + file generation"] --> SPLIT["FileSplitter/record parser"]
    SPLIT --> KEY["Canonical business operation key"]
    KEY --> INBOX["Transactional inbox / atomic claim"]
    INBOX --> CHECK{"State?"}
    CHECK -->|Completed| ACK["Skip side effect / cached outcome"]
    CHECK -->|Processing| WAIT["Wait / lease / investigate"]
    CHECK -->|New| DB["JDBC business transaction"]
    DB --> OB["Outbox entry in same transaction"]
    OB --> WORK["Outbound Kafka worker"]
    WORK --> RES["Result / reconciliation"]
    RES --> COMPLETE["Mark COMPLETED"]
    COMPLETE --> ACK
    CHECK -->|Conflict| ERR["Quarantine + audit"]
~~~

In this design, `MetadataStoreSelector` can remain an **optimization** to filter early noise, while the **inbox/business unique constraint** owns correctness across crashes. If a selector sits ahead of the inbox, verify it never blocks incomplete operations.

### 28.7. Illustrative audit record

~~~json
{
  "eventId": "SFTP-REPORT-REPLAY-004",
  "sourceFile": "orders-2026-11-23.csv",
  "fileGeneration": "sha256:example",
  "recordNumber": 2,
  "businessOperationKey": "order:create:T42:ORD-972",
  "selectorDecision": "ALREADY_SEEN",
  "businessOutcome": "NOT_COMMITTED",
  "recoveryDecision": "RECONCILE_AND_REPLAY",
  "owner": "integration-platform",
  "verification": "pending"
}
~~~

This is an illustrative application schema. Never automatically translate `selectorDecision=ALREADY_SEEN` into `businessOutcome=COMPLETED`.

## 29. Common anti-patterns

| Anti-pattern | Why it is wrong | Fix |
| --- | --- | --- |
| Using Spring Message ID as business key | ID can change across redeliveries/transforms | Use a stable operation ID |
| Using file path alone for overwritable files | New file generation treated as duplicate | Add generation/version or immutable upload contract |
| Omitting `valueStrategy` assuming value is business version | Default is message timestamp | Provide explicit `valueStrategy` |
| Comparing strings `"10" > "9"` lexicographically | Lexical order differs from numeric order | Parse and validate numeric revisions |
| Swapping `compareValues` parameter order | Older versions can replace newer ones | `oldValue` first, `newValue` second |
| High-watermark with out-of-order processing | Unprocessed messages get skipped | Ordered processing/gap tracking/per-record keys |
| Treating selector accept as business completed | Crashes after marking drop operations | Inbox + transactions/reconciliation |
| `SimpleMetadataStore` across multiple pods | Store is not shared | Shared atomic durable store |
| Separate `get` then `put` | Race conditions between consumers | Atomic `putIfAbsent`/`replace` |
| Ignoring Redis/DB topology limits | CAS lacks expected guarantees | Test specific backend and version |
| Discarding HTTP gateway duplicates with no reply | Callers time out repeatedly | Cached result/pending/conflict responses |
| Forgetting source ack/offset semantics | Lost messages or infinite redeliveries | Adapter/container integration tests |
| Deleting keys on HTTP timeouts | Side effects may already have committed | Reconcile before retrying |
| Flushing metadata casually while debugging | Old events look brand new | Scoped changes + approval + audit |
| One shared key across multiple side effects | Branch A success hides branch B failure | Per-consumer/per-operation keys/outbox |
| Embedding PII or raw credentials in keys | Leaks through metadata/logs | Hashing/references and ACLs |
| TTL shorter than replay window | Replays create duplicates | Retain per business correctness window |
| No runbook for stale markers | Operators replay recklessly | Clear states, owners, and failure evidence |

## 30. Self-check exercises

### Exercise 1. First arrival and duplicate

A selector keyed by `order:create:T42:ORD-971` uses `SimpleMetadataStore`. The first message is accepted; the second carries the same operation key with a different Spring Message ID.

**Answer:** The second message is rejected under first-seen semantics in the same store. Different Spring Message IDs have no effect when `keyStrategy` relies on the operation ID.

### Exercise 2. JVM restart

After an application restart, an old message is accepted again by the selector even though it was previously processed.

**Answer:** Using `SimpleMetadataStore` loses in-memory state. You need a persistent/shared store or transactional inbox, verified with restart tests.

### Exercise 3. Old and new compareValues

`Old = "9"`, `New = "10"`. You write `old.compareTo(new) < 0`.

**Answer:** Lexicographical comparison fails on multi-digit numbers. Parse integers and compare numerically after validation.

### Exercise 4. Out-of-order records

A file has lines 1, 2, 3; line 3 arrives before line 2; the selector stores maximum sequence.

**Answer:** Line 2 can be rejected even though never completed. Do not use a simple high-watermark if every record must run without guaranteed ordering.

### Exercise 5. Crash after putIfAbsent

The store persisted `K`; the business transaction failed. The broker redelivers.

**Answer:** A simple selector may reject `K`, losing the operation if discarded/acked. Use inbox/transaction state or recovery so uncompleted `K` remains processable.

### Exercise 6. HTTP request-reply

A client retries the same `Idempotency-Key`; the duplicate route only logs.

**Answer:** Insufficient. The API must return a cached business result, pending status, or conflict per contract rather than leaving the caller to time out endlessly.

### Exercise 7. Two pods and atomicity

Two pods each run their own `SimpleMetadataStore`. Both receive `K`.

**Answer:** Both can accept. You need a shared store or unique constraint where real coordination occurs.

### Exercise 8. New file generation

A partner uploads a new file with the same name but updated contents. The selector uses only the absolute path as key.

**Answer:** The new file may be mistaken for a duplicate of the old one. Add version/generation/checksum or enforce immutable upload contracts.

### Exercise 9. Intentional new version

A document with the same ID updates to revision 2. Business policy requires only the latest revision.

**Answer:** Using `valueStrategy=revision` and `compareValues(new > old)` can fit if versions are monotonic and concurrency/backfill and transaction semantics are verified.

### Exercise 10. Metadata store outage

The Redis metadata store becomes unreachable while the adapter still receives thousands of orders.

**Answer:** Do not automatically fail open if it is the sole deduplication layer. Use fail-safe policies, buffering/backpressure, alerts, and bounded retries; even with strong downstream idempotency, bypassing the guard requires explicit approval.

## 31. Checklist for implementing MetadataStoreSelector

1. **Right purpose:** Use the selector for accept/reject decisions, not as a transaction coordinator.
2. **Right key:** Tie keys to business operations or checkpoint contracts, properly namespaced and versioned.
3. **Right value:** Know the default is a timestamp; use versions/sequences only with an explicit `valueStrategy`.
4. **Right `compareValues`:** Old first, new second; validate types and update semantics.
5. **Clear ordering:** High-watermarks must never drop out-of-order events or unprocessed gaps.
6. **Atomic store:** Verify `putIfAbsent`/`replace` in your actual topology.
7. **Durable store:** When surviving restarts is required, use a persistent shared store and test crashes/failovers.
8. **Never mark early and forget outcomes:** Use inboxes/transactions/reconciliation for critical work.
9. **Clear duplicate behavior:** Interceptor marks headers, discards, or throws per configuration.
10. **Advice attached at the right point:** Keep side effects from running ahead of the guard.
11. **Separate source and business state:** File filters/checkpoints do not equal business completion.
12. **Proper acks:** Verify JMS/AMQP/Kafka commit/ack/offset behavior with real integration tests.
13. **Proper HTTP replies:** Duplicates return valid cached results, pending states, or conflicts.
14. **Proper JDBC state:** Row claims, unique constraints, and transactions clearly designed.
15. **Proper retry/replay:** Preserve operation keys; use DLQ/reconciliation for unknown outcomes.
16. **Independent fan-out:** Per-consumer/per-effect idempotency when branches have independent side effects.
17. **Clear key lifecycle:** Retention, eviction, migration, backups, and scoped cleanup.
18. **Safe store outages:** No uncontrolled dedup bypass; enforce backpressure and alerts.
19. **Observability:** Monitor accepts/rejects, store errors, stale keys, and business completion.
20. **Security:** Exclude secrets/PII from keys/values/logs; restrict metadata edit/delete permissions.
21. **Concurrency testing:** Multi-threaded/multi-instance runs, restarts, Redis/DB failovers, and version races.
22. **Crash-window testing:** After selector accept, before commit, after commit, and before ack.
23. **Runbooks:** Assign owners and procedures to inspect/replay specific keys.
24. **Version awareness:** Verify imports, DSL, store semantics, and `compareValues` against your Spring Integration version.

## 32. References

Official sources for checking APIs and semantics against your active version:

1. **Spring Integration – Idempotent Receiver Enterprise Integration Pattern**  
   https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
2. **Spring Integration – Metadata Store**  
   https://docs.spring.io/spring-integration/reference/meta-data-store.html
3. **Spring Integration – File Splitter / Idempotent Downstream Processing a Split File**  
   https://docs.spring.io/spring-integration/reference/file/splitter.html
4. **Spring Integration Javadoc – MetadataStoreSelector**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html
5. **Spring Integration Javadoc – ConcurrentMetadataStore**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html

Java/XML snippets in this lesson are **learning examples**; projects must select dependencies and verify APIs against their exact Spring Integration/Spring Retry/Spring Boot versions. Never copy configurations directly to production while skipping transactions, ack semantics, and corresponding tests.

## 33. Summary

`MetadataStoreSelector` is a `MessageSelector` backed by a `ConcurrentMetadataStore` to filter messages via **keys/values**. For new keys, it relies on `putIfAbsent` to accept; for existing keys, `compareValues` enables conditional acceptance and updates when backed by a store supporting atomic updates. `IdempotentReceiverInterceptor` or `MessageFilter` brings this decision into processing flows.

Most importantly, **never equate the selector storing a key with the business operation finishing**. File/SFTP filters operate at file ingestion; JMS/AMQP/Kafka manage redeliveries and acks/offsets; HTTP gateways owe business replies; JDBC needs row states and transactions; and multi-system data flows typically require **stable operation keys, unique constraints, transactional inboxes/outboxes, idempotent downstreams, and reconciliation**. When these boundaries are respected, `MetadataStoreSelector` becomes a reliable tool for cutting duplicate processing **without dropping messages that never actually succeeded**.
