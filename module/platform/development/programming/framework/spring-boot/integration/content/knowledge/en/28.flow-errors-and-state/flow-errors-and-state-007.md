# MetadataStore, IdempotentReceiverInterceptor, and Marking or Filtering Duplicate Messages

## 1. Context and Objectives

Within the **SPRING_BOOT_INTEGRATION** module, Spring Boot integration flows exchange data with HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A recurring problem is that **the same event or request can arrive multiple times**: a broker redelivers when a consumer misses an ACK, a file poller rescans data after a restart, an HTTP caller retries after missing a response, or an application recovers from an older checkpoint.

The **Flow Errors and State** chapter examines how to detect and persist state so a duplicate message does not accidentally trigger a business side effect a second time. Spring Integration provides two key mechanisms:

- **MetadataStore / ConcurrentMetadataStore**: key–value storage describing seen or processed state.
- **IdempotentReceiverInterceptor**: advice attached to a **`MessageHandler`** to decide which message is new and which is duplicate; then **mark**, **route to a discard channel**, or **reject with an exception** depending on configuration.

This is a tool for implementing the **Idempotent Receiver** pattern, yet enabling the interceptor **does not guarantee exactly-once** across the entire system. Real guarantees depend on business keys, when state is written, transactions, error handling, and downstream side effects.

After this lesson, you should be able to:

1. Distinguish technical message identifiers from business/event identifiers.
2. Understand the contracts of `MetadataStore`, `ConcurrentMetadataStore`, and `MetadataStoreSelector`.
3. Attach `IdempotentReceiverInterceptor` to an endpoint using Java DSL or annotations.
4. Choose between **marking duplicates** via headers and **filtering duplicates** via a discard channel per scenario.
5. Design failure handling, post-restart state, multi-instance coordination, and out-of-order events.
6. Test and observe a deduplication flow under realistic redelivery conditions.

## 2. Why Are Messages Redelivered?

Suppose a consumer receives an **OrderPaid** event from a broker:

~~~json
{
  "eventId": "evt-7821",
  "orderId": "ord-204",
  "paymentVersion": 7,
  "paidAt": "2026-11-21T03:20:00Z"
}
~~~

The consumer persists the paid status to the database, then ACKs the message. If the process crashes **after the database commit but before the ACK**, the broker can redeliver event **evt-7821**. Without deduplication, the handler might double-count revenue, send another notification, or insert a second ledger row.

~~~mermaid
sequenceDiagram
    participant B as Message broker
    participant F as Spring Integration flow
    participant D as Database
    B->>F: OrderPaid evt-7821
    F->>D: Commit payment state
    D-->>F: Success
    Note over F: Crash before ACK
    B->>F: Redelivery evt-7821
    F->>F: Check deduplication key
    alt Key already recorded
        F-->>B: Skip duplicate side effect, ACK per policy
    else Key not yet present
        F->>D: Process with business protection
        F-->>B: ACK upon completion
    end
~~~

Common sources of duplicates:

| Source | Why Duplicates Occur | Meaning of Deduplication Key |
| --- | --- | --- |
| Broker **at-least-once** delivery | Lost ACK, retries, or rebalances | Event ID stable across redeliveries |
| HTTP client retry | Timeout after server already processed | Client-supplied idempotency key or business request ID |
| File/SFTP polling | Rescanning after restart, re-reading files/records | Path + fingerprint, or source + offset/record ID |
| CDC/outbox | Replays due to checkpoints or restarts | Event ID or source–position pair |
| Internal retries | Flow retries after processing error | Key of the same business operation |

**Never use the default `message.id` header for deduplication** if it is regenerated upon message transformation, deserialization, gateway entry, or redelivery. IDs supplied by brokers or senders must be verified as stable across retries and unique within the required business scope.

## 3. What Does MetadataStore Store?

### 3.1. MetadataStore vs. ConcurrentMetadataStore

**`org.springframework.integration.metadata.MetadataStore`** has a simple key–value contract:

~~~java
public interface MetadataStore {
    void put(String key, String value);
    String get(String key);
    String remove(String key);
}
~~~

**`ConcurrentMetadataStore`** extends it with atomic operations:

~~~java
public interface ConcurrentMetadataStore extends MetadataStore {
    String putIfAbsent(String key, String value);
    boolean replace(String key, String oldValue, String newValue);
}
~~~

Simplified signatures for illustration. **`putIfAbsent`** returns **`null`** when the key was absent and the new value is placed successfully; if the key already exists, it returns the previous value. **`replace`** swaps the value only if the current value matches the expected old value.

Therefore, checking and writing in two separate calls is unsafe under concurrency:

~~~java
// DO NOT use to guarantee only one consumer claims a key:
if (store.get(key) == null) {
    store.put(key, "seen");
    process(message);
}
~~~

Two workers could both see **`null`** and both execute. For a deduplication gate, use a **`ConcurrentMetadataStore`** with atomic **`putIfAbsent`**:

~~~java
boolean firstArrival = store.putIfAbsent(key, "seen") == null;
if (firstArrival) {
    process(message);
}
~~~

This snippet only covers **claiming the right to process a key**; it does not solve what happens if **`process()` fails after writing the key**. That problem is analyzed later.

### 3.2. Choosing the Right Backend

| Store | Survives Restart? | Coordination Scope | When to Use |
| --- | --- | --- | --- |
| **SimpleMetadataStore** | No | Single application context / JVM | Demos, tests, short-lived single-instance deduplication |
| **PropertiesPersistingMetadataStore** | Yes when flushed/saved properly | Better suited to local state; not a default cluster-shared store | Single process, small state, clear persistence behavior |
| **JdbcMetadataStore** | Yes | Multiple instances sharing a DB with proper transactions | Durable metadata able to participate in JDBC transactions |
| **RedisMetadataStore** | Depends on Redis persistence config | Multiple instances sharing Redis, within topology atomicity limits | High-throughput dedupe gate with TTL/ops evaluation |
| **MongoDbMetadataStore**, **ZookeeperMetadataStore**, others | Per backend | Per backend and its atomicity guarantees | Infrastructure already standardized on that store |

When no store is explicitly referenced, some Spring Integration components look up a bean named **`metadataStore`** and fall back to **`SimpleMetadataStore`**. To control scope explicitly and avoid accidentally falling back to an in-memory store, **inject a clearly named `ConcurrentMetadataStore`** into your flow selector.

**Do not confuse `MetadataStore` with `MessageStore`.** `MetadataStore` holds string key/value pairs for recognition state; `MessageStore` stores full messages or message groups for patterns like aggregators or persistent channels. A metadata record **does not contain enough message data to replay the business operation**.

## 4. How Does MetadataStoreSelector Decide Duplicates?

**`org.springframework.integration.selector.MetadataStoreSelector`** is a **`MessageSelector`** that uses a **`MessageProcessor`** to compute a key from a `Message` and a **`ConcurrentMetadataStore`** to check/set state.

Default flow when **no** value-comparison policy is configured:

~~~mermaid
flowchart TD
    A["Message arrives at handler"] --> B["Compute idempotent key"]
    B --> C["ConcurrentMetadataStore.putIfAbsent(key, value)"]
    C --> D{"Return value"}
    D -->|"null: absent"| E["accept = true"]
    D -->|"Existing value: present"| F["accept = false"]
    E --> G["Handler runs via advice"]
    F --> H["Interceptor marks or filters"]
~~~

Without a custom **`valueStrategy`**, the selector derives the value from the message's **timestamp** header (in the selector's internal representation). With **eventId-based deduplication keys**, the stored value itself is rarely used for decisions, though you must still govern metadata lifecycle, size, and eviction.

Example selector for payment events:

~~~java
@Bean
MetadataStoreSelector paidEventSelector(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

    return new MetadataStoreSelector(message -> {
        OrderPaid event = (OrderPaid) message.getPayload();
        return "order-paid:consumer-v1:" + event.eventId();
    }, store);
}
~~~

Here **`OrderPaid`** is an application DTO with an **`eventId()`** method, such as a Java record:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        long paymentVersion,
        Instant paidAt) {
}
~~~

In production, validate that **`eventId` is non-null/non-blank**, well-formed, and stable across retries. The prefix **`order-paid:consumer-v1`** acts as a namespace scoping **processing purpose** so another consumer cannot accidentally share keys and drop valid messages.

### Choosing Keys by Business Semantics

| Goal | Suggested Key | Avoid |
| --- | --- | --- |
| A payment event updates the ledger once | consumer + `eventId` | Using only `orderId` if an order can receive multiple payment events |
| An HTTP command carries an idempotency key | operation + tenant + `clientRequestId` | Hashing payload alone when identical payloads can represent two valid commands |
| Syncing only the latest version | source + `aggregateId`, value = version | Keying by `eventId` if the goal is rejecting stale versions |
| Splitting lines from files | source/file identity + line offset or record ID | Filename alone if files can be rewritten |
| Preventing duplicate emails for one business action | email type + tenant + `actionId` | Recipient alone, since one person can receive many valid emails |

Keys need appropriate **scoping**, **stability**, and **expiration policies**. Sensitive identifiers should not appear raw in keys/logs if hashed or anonymized identifiers work.

## 5. IdempotentReceiverInterceptor: Marks by Default, Does Not Auto-Drop

**`IdempotentReceiverInterceptor`** is an **advice** applied to **`MessageHandler.handleMessage(Message<?>)`**, not a standalone endpoint and not an interceptor for arbitrary Java methods in your app.

When the selector returns **`false`** because the key already exists:

1. **By default**, the interceptor builds a message with header **`duplicateMessage = true`** and **still invokes the handler**.
2. When **`discardChannel`** is configured, the interceptor routes rejected messages there and **does not invoke the target handler**.
3. When **`throwExceptionOnRejection = true`**, the interceptor **skips the target handler** and throws **`MessageRejectedException`**. If a discard channel is also configured, it sends to the discard channel and may still throw the exception.

Distinctions:

| Configuration | Does Business Handler Receive Duplicate? | Outcome for Duplicate |
| --- | --- | --- |
| Selector only (default) | **Yes** | Message marked with header **`duplicateMessage=true`** |
| `discardChannel` configured | **No** | Message routed to discard channel |
| Discard to `nullChannel` | **No** | Message intentionally dropped |
| `throwExceptionOnRejection=true` | **No** | Throws `MessageRejectedException` |
| Both `discardChannel` and `throwExceptionOnRejection=true` | **No** | Sends to discard then throws exception per configuration |

**Dangerous misconfiguration:** attaching the interceptor assuming it drops duplicates automatically, when by default the handler is still invoked. If the handler ignores the header, side effects run a second time.

## 6. Example 1 — Marking Duplicates So the Handler Decides

Goal: a flow receiving payment events where the handler records audits/metrics on redelivery and chooses the appropriate response. This illustration uses **`SimpleMetadataStore`** to run easily on a single instance; production should replace it with a shared persistent store.

### 6.1. Configuration Beans

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class PaidEventFlowConfiguration {

    @Bean("paymentIdempotencyStore")
    ConcurrentMetadataStore paymentIdempotencyStore() {
        return new SimpleMetadataStore();
    }

    @Bean
    IdempotentReceiverInterceptor markPaidDuplicates(
            @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> "paid:v1:"
                        + ((OrderPaid) message.getPayload()).eventId(),
                store);

        // No discardChannel or throwExceptionOnRejection set:
        // duplicate messages still reach the handler with duplicateMessage header.
        return new IdempotentReceiverInterceptor(selector);
    }

    @Bean
    IntegrationFlow paidEventFlow(
            IdempotentReceiverInterceptor markPaidDuplicates) {

        return IntegrationFlow.from("paidEventsInput")
                .handle("paidEventHandler", "handle",
                        e -> e.advice(markPaidDuplicates))
                .get();
    }
}
~~~

**Omitted imports:** domain classes and standard Spring annotations belong in the application; include **`spring-boot-starter-integration`** or matching Spring Integration modules for your Boot version. **`IntegrationFlow.from("paidEventsInput")`** reads from an input channel named **`paidEventsInput`** fed by a broker adapter or gateway. The example assumes the **`OrderPaid`** DTO was already deserialized from JSON before reaching the handler.

### 6.2. Handler with a Duplicate Branch

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component("paidEventHandler")
public class PaidEventHandler {
    private final PaidOrderService paidOrderService;

    public PaidEventHandler(PaidOrderService paidOrderService) {
        this.paidOrderService = paidOrderService;
    }

    public void handle(Message<?> message) {
        boolean duplicate = Boolean.TRUE.equals(
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE));

        if (duplicate) {
            // Record metrics/audit per policy without re-running side effects.
            return;
        }

        paidOrderService.applyPayment((OrderPaid) message.getPayload());
    }
}
~~~

In this mode, duplicate messages **reach the handler** so the application can decide what to reply or audit. However, because the key is usually written to the store **before `applyPayment` finishes**, simple duplicate checks are not safe if downstream fails. Section 10 explains how to prevent permanently blocking valid messages after errors.

## 7. Example 2 — Filtering Duplicate Messages at the Handler Boundary

If duplicate events can safely be ACKed as handled and **do not need the business handler to inspect them**, configure an explicit discard channel:

~~~java
@Bean
IdempotentReceiverInterceptor dropPaidDuplicates(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

    MetadataStoreSelector selector = new MetadataStoreSelector(
            m -> "paid:v1:" + ((OrderPaid) m.getPayload()).eventId(),
            store);

    IdempotentReceiverInterceptor advice =
            new IdempotentReceiverInterceptor(selector);
    advice.setDiscardChannelName("nullChannel");
    return advice;
}

@Bean
IntegrationFlow dropDuplicateFlow(
        @Qualifier("dropPaidDuplicates")
        IdempotentReceiverInterceptor advice) {

    return IntegrationFlow.from("paidEventsInputForDiscard")
            .handle("paidEventHandler", "handle", e -> e.advice(advice))
            .get();
}
~~~

This is an **alternative** to the mark mode in Section 6, not two flows meant to share one channel and store in production. If copying both examples into one project, pick one strategy, distinct bean/channel names, and clear state namespaces.

**`nullChannel`** is a built-in Spring Integration channel that consumes messages without further processing. Do not confuse it with **leaving `discardChannel` unset**: when unset, the interceptor defaults to **marking** duplicates and **running the handler**.

When you want to observe filtered duplicates, supply an audit channel instead of `nullChannel`:

~~~java
@Bean
MessageChannel duplicateAuditChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow duplicateAuditFlow() {
    return IntegrationFlow.from("duplicateAuditChannel")
            .handle(message -> {
                // Record metrics; omit credentials and sensitive payloads.
                // Avoid letting audit throws disrupt ACKs unintentionally.
            })
            .get();
}
~~~

And set **`advice.setDiscardChannelName("duplicateAuditChannel")`**. This snippet only illustrates wiring; if auditing must be durable, use an appropriate store/queue rather than assuming a synchronous `DirectChannel` persists history.

### When Should You Throw an Exception on Duplicate?

~~~java
advice.setThrowExceptionOnRejection(true);
~~~

When enabled, **`MessageRejectedException`** signals that the selector rejected the message. This is usually **not** ideal for routine duplicates in an at-least-once consumer: the adapter may treat the exception as a failure and **infinitely redeliver the same message**. Enable it only when you intentionally want duplicates routed to an error path, dead-lettered, or returned as errors under an explicit ACK/retry policy.

## 8. Using Annotations on Endpoints

Besides the Java DSL advice chain, Spring Integration supports **`@IdempotentReceiver`** to attach an interceptor by bean name to annotation-configured messaging endpoints:

~~~java
@Bean
IdempotentReceiverInterceptor paidAdvice(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {
    return new IdempotentReceiverInterceptor(
            new MetadataStoreSelector(
                    m -> "paid:v1:"
                            + ((OrderPaid) m.getPayload()).eventId(),
                    store));
}

@Bean
@ServiceActivator(inputChannel = "paidEventsInput")
@IdempotentReceiver("paidAdvice")
MessageHandler paidMessageHandler(PaidEventHandler processor) {
    return processor::handle;
}
~~~

This example assumes **`PaidEventHandler.handle(Message<?>)`** is declared. Using `Message<?>` lets the method reference satisfy `MessageHandler`; the body checks and casts the payload to `OrderPaid` after adapter conversion/validation. Choose **one** endpoint configuration style—**DSL `e.advice(...)`** or **`@IdempotentReceiver`** on the endpoint; never accidentally apply the same selector twice to one message, or the second check will see the key just inserted and treat the very first delivery as a duplicate.

In Java config apps, verify the exact Spring Integration annotation imports and framework version. The interceptor advises a **`MessageHandler`**; placing it on an arbitrary Spring bean method will not deduplicate unless wired through an integration endpoint.

## 9. Choosing a Durable MetadataStore for Production

**`SimpleMetadataStore`** only holds state in process memory. On restart, keys vanish and previously processed events can be accepted as new. Across multiple parallel replicas, each replica holds its own store so multiple replicas can accept the same event.

When shared state across replicas and restarts is required, consider **`JdbcMetadataStore`** or another distributed store offering appropriate atomic operations.

### 9.1. JdbcMetadataStore

Using JDBC requires the Spring Integration JDBC module (e.g., **`org.springframework.integration:spring-integration-jdbc`**), a **`DataSource`**, a matching transaction manager, and the metadata table. Example:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.jdbc.metadata.JdbcMetadataStore;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Bean("paymentIdempotencyStore")
ConcurrentMetadataStore paymentIdempotencyStore(DataSource dataSource) {
    JdbcMetadataStore store = new JdbcMetadataStore(dataSource);
    store.setRegion("paid-events-v1");
    return store;
}
~~~

**`setRegion`** partitions the keyspace so flows/consumers do not collide. Within the same metadata table, keys are distinguished by **`(METADATA_KEY, REGION)`**. Do not change the region on every deployment if deduplication must span deployments.

PostgreSQL DDL example (select the official script matching your database):

~~~sql
CREATE TABLE INT_METADATA_STORE (
    METADATA_KEY VARCHAR(255) NOT NULL,
    METADATA_VALUE VARCHAR(4000) NOT NULL,
    REGION VARCHAR(100) NOT NULL,
    CONSTRAINT INT_METADATA_STORE_PK
        PRIMARY KEY (METADATA_KEY, REGION)
);
~~~

Official Spring Integration scripts for each RDBMS ship inside the JDBC module. Apply them via Flyway/Liquibase or your migration pipeline; **do not assume a starter auto-creates production tables**. Some Spring Integration versions check for the table on startup and fail if it is missing.

**`JdbcMetadataStore`** can participate in JDBC transactions. When metadata writes share **the exact same transaction** as business changes on the same database and transaction manager, rollback undoes the metadata entry too. However, **never assume `@Transactional` on the handler automatically wraps the selector**: the interceptor runs before the handler is called; verify transaction advice ordering, `DataSource` alignment, and actual commit timing.

### 9.2. Redis and Other Distributed Backends

**`RedisMetadataStore`** uses Redis to share metadata across instances. Redis meets high-throughput needs, but you must verify atomic compare-and-set semantics for **your exact version and topology**; for instance, certain `WATCH`-based `replace` operations have limitations in Redis Cluster. Plan persistence, replication, eviction, key TTLs, and unavailability handling.

**Do not treat any persistent store as an exactly-once guarantee for side effects in another backend.** If metadata lives in Redis while business data sits in PostgreSQL or ends in an HTTP call, there is no automatic distributed transaction across them.

### 9.3. Sizing Limits and Key Retention

With **one key per `eventId`**, total keys grow with total seen events:

~~~text
10,000 events/min × 60 × 24 × 7 days
    = 100,800,000 keys per week
~~~

Define a **deduplication window** based on how long brokers may redeliver, manual replay horizons, business SLAs, and compliance rules. Deleting metadata too early lets old events replay as new; keeping keys forever bloats storage.

Not every `MetadataStore` supports per-key TTL natively. When using backend TTLs or a periodic cleanup reaper, prove deletion is safe against replays, retries, and races. Never guess a default TTL without checking the sender's retention period.

## 10. Biggest Trap: Marking Before the Handler Succeeds

When **`MetadataStoreSelector.accept(message)`** runs, it typically writes the key **before** the target handler executes. That marks **admission/claimed**, not proof that **side effects committed**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant M as MetadataStore
    participant H as Business handler
    B->>M: evt-7821
    M->>M: putIfAbsent(evt-7821) succeeds
    M->>H: Allow processing
    H--xH: Database error / timeout
    Note over B,H: Key remains if not synchronously rolled back
    B->>M: Redelivery evt-7821
    M-->>B: Duplicate → filtered out
    Note over B,H: Business effect may be lost
~~~

Distinguish these models carefully:

| Model | What It Guarantees | Main Risk |
| --- | --- | --- |
| Mark key before handler, **no** state rollback | A key is usually admitted once within the retention window | Handler failure after marking blocks redelivery |
| Manual key removal on handler error | May allow retries | Race deleting another worker's key; partial side effect already ran |
| JDBC metadata + business write in **same DB transaction** | Marking and DB side effects commit/roll back together when properly wrapped | Does not cover HTTP, brokers, or external backends |
| **`processed_event`** table with unique constraint in business TX | Protects a consumer directly at the source-of-truth DB | Requires defining ACK timing, state retention, and transactions |
| Idempotent business operation by request key | Retries remain safe even if gates fail or metadata is lost | Must be designed into every relevant side effect |

### 10.1. Example Consumer/Outbox with Business Transaction

When the requirement is "record each payment event once in the payment ledger", a stronger approach is a **unique constraint directly in the business database**:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

PostgreSQL service example:

~~~java
@Service
public class PaidOrderService {
    private final JdbcTemplate jdbc;

    public PaidOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyPayment(OrderPaid event) {
        int accepted = jdbc.update("""
            INSERT INTO processed_event (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "paid-order-v1", event.eventId());

        if (accepted == 0) {
            // Already committed earlier or another transaction owns the key;
            // exact behavior depends on DB isolation/unique locking.
            return;
        }

        int changed = jdbc.update("""
            UPDATE orders SET paid = TRUE
            WHERE order_id = ?
            """, event.orderId());

        if (changed != 1) {
            // Throw RuntimeException to roll back both marker and DB changes.
            throw new IllegalStateException("Unknown order");
        }
    }
}
~~~

Here **`processed_event`** and **`orders`** must belong to **the same `DataSource`/transaction manager**. On update failure, rollback deletes the uncommitted marker; once committed, future redeliveries safely return early. **`ON CONFLICT DO NOTHING`** is PostgreSQL syntax: on other databases use the equivalent syntax and test real concurrency/unique constraints.

This is the **authoritative business-layer guard**, while `IdempotentReceiverInterceptor` can act as an early load-shedding filter. However, if an early filter could block redelivery of an uncommitted transaction, it must never be the sole decision point. Either omit the early filter, verify it shares the same transaction, or use explicit **`IN_PROGRESS / COMPLETED`** states with leases, recovery, and fencing.

### 10.2. Idempotency Differs from Transactions and Exactly-Once

- **Idempotency**: repeating the same operation produces the intended business effect equivalent to running once.
- **Atomic transaction**: a group of changes within one transaction boundary commit or roll back together.
- **Delivery guarantee**: brokers provide at-most-once, at-least-once, or similar delivery; this does not automatically equal exactly-once business effects.
- **Exactly-once effect** across multiple systems: requires appropriate boundaries and protocols, typically combining idempotency, transactional outbox, consumer inbox, reconciliation, or broker-specific features.

Never cite a "duplicate discarded" log line as proof that the business handler succeeded earlier.

## 11. Duplicate Messages Differ from Failed Messages and Out-of-Order Events

**Duplicate:** the same `eventId` (or business operation ID) arrives again, meaning do not re-apply the side effect.

**Out-of-order:** a valid event with an older version arrives after a newer version; not necessarily a duplicate by `eventId`.

**Transient failure:** a new event failed to finish because DB/broker/upstream was unavailable; needs retries and recovery.

**Poison message:** invalid structure/payload that will always fail; needs validation, dead-lettering, and manual remediation.

Example receiving inventory snapshots by **`sku`** and **`sourceVersion`**, accepting only versions **strictly greater** than the latest stored version:

~~~java
@Bean
MetadataStoreSelector inventoryVersionSelector(
        @Qualifier("inventoryVersionStore") ConcurrentMetadataStore store) {

    return new MetadataStoreSelector(
            msg -> "inventory:v1:"
                    + ((InventoryChanged) msg.getPayload()).sku(),
            msg -> Long.toString(
                    ((InventoryChanged) msg.getPayload()).sourceVersion()),
            store)
            .compareValues((oldValue, newValue) ->
                    Long.parseLong(newValue) > Long.parseLong(oldValue));
}
~~~

Example DTO:

~~~java
public record InventoryChanged(
        String sku, long sourceVersion, int availableQuantity) {}
~~~

**`compareValues`** admits newer messages by comparing versions and updating metadata atomically via the store's compare-and-replace. This blocks **older or equal versions**. Still, advancing a checkpoint in `MetadataStore` **does not guarantee side effects finish in order**: versions 7 and 8 can both be admitted concurrently, and the handler for version 7 might write after version 8.

To keep snapshots from regressing, enforce protection directly at the business data store—such as **`UPDATE ... WHERE stored_version < incoming_version`**, optimistic locking, or per-key serialization. Also account for crashes after advancing the checkpoint but before completing the business write.

## 12. Interacting with Brokers, Retries, Error Channels, and ACKs

Placing deduplication into a flow must align with adapter and channel semantics:

~~~text
Inbound broker adapter
   ↓ deserialize / validate
Input channel
   ↓ IdempotentReceiverInterceptor at handler
   ├─ new → handler → DB/update → success → ACK
   ├─ duplicate → mark or discard per policy → appropriate ACK
   ├─ transient error → bounded retry → conditional DLQ/requeue
   └─ invalid/poison → error handling and DLQ per contract
~~~

**ACK, transaction, and error propagation differ across Kafka, RabbitMQ, JMS, HTTP gateways, and file adapters.** Read your actual adapter configuration (manual/auto ack, transaction mode, commit policy, error channels, retry advice) to know when the broker receives ACK.

Common design flaws:

- If **`throwExceptionOnRejection(true)`** raises an error for an already-handled duplicate, a policy treating all exceptions as retryable may loop infinitely.
- If **`discardChannel`** forwards to an audit handler that throws, ACKs can be disrupted depending on the chain. Decide explicitly whether auditing is best-effort or mandatory.
- If dispatching via **`ExecutorChannel`** or async queues, the ingress transaction may not wrap downstream handlers; never expect a thread rollback to undo metadata committed on another thread.
- If retry advice and the idempotent interceptor share an endpoint, **advice order** determines whether retries re-run the selector or run it once; test the real flow rather than guessing from bean names.
- If the metadata store flakes, that is an **infrastructure error**, not a "duplicate" verdict. Never catch all exceptions and silently discard.

**Key rule:** ACK a message only once the system reaches a state where broker redelivery is no longer needed per business contract. For already-completed duplicates, ACKing is normally right; for new messages hitting transient failures, preserve retryability.

## 13. Testing: Both the Selector and Failure Boundaries

### 13.1. Testing the Selector in Isolation

A small test verifying **`putIfAbsent`** for the same key:

~~~java
@Test
void firstMessageAcceptedSecondRejected() {
    ConcurrentMetadataStore store = new SimpleMetadataStore();
    MetadataStoreSelector selector = new MetadataStoreSelector(
            m -> "paid:v1:" + m.getHeaders().get("eventId"),
            store);

    Message<String> first = MessageBuilder.withPayload("paid")
            .setHeader("eventId", "evt-7821")
            .build();

    Message<String> redelivery = MessageBuilder.withPayload("paid")
            .setHeader("eventId", "evt-7821")
            .build();

    assertTrue(selector.accept(first));
    assertFalse(selector.accept(redelivery));
}
~~~

This tests **the selector** only; it does not prove the interceptor marks/filters properly or shares state across two JVMs.

### 13.2. Testing the Flow with Advice

With Spring Integration Test or a small test context containing an input channel and mocked business handler:

1. Send **`evt-7821`** first time → handler invoked once.
2. Resend with **identical `eventId`** and a new `message.id` → in **mark mode**, handler is called with `duplicateMessage=true`; in **discard mode**, handler is not called again.
3. Send **`evt-7822`** → processed normally, unaffected by the prior key.
4. Run two concurrent threads with the same `eventId` → with an atomic store, only one passes the selector.
5. Restart the context/instance and resend → persistent store blocks duplicates; `SimpleMetadataStore` does not.
6. Simulate handler failure after selector writes key → verify redelivery and rollback/recovery per design.
7. Simulate metadata store outage → error routes to retry/error channel rather than being treated as duplicate.
8. With `compareValues`, send version 8 then 7, and 7/8 concurrently → assert **business state**, not just metadata checkpoint.

Example asserting the duplicate header inside a mark-mode test handler:

~~~java
boolean markedDuplicate = Boolean.TRUE.equals(
        message.getHeaders().get(
                IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE));
assertTrue(markedDuplicate);
~~~

### 13.3. Integration Testing with a Real Backend

For **`JdbcMetadataStore`**, test across two application contexts or two instances sharing one DB; use Testcontainers or a real DB to verify unique keys, transaction rollbacks, locking, and restarts. For `RedisMetadataStore`, test against your real Redis topology and verify CAS, failover, and TTL behavior.

**Mocking `MetadataStore` does not prove distributed atomicity.** Unit tests only validate key selection and flow branching. Integration tests prove backend correctness under contention and recovery.

## 14. Observing and Operating a Deduplication Flow

A deduplication policy is hard to operate if it only logs "duplicate detected". Track:

| Metric / Signal | Meaning |
| --- | --- |
| **`messages_received_total`** per consumer/flow | Total intake, including redeliveries |
| **`idempotent_accepted_total`** | New keys admitted |
| **`idempotent_duplicate_total`** | Keys flagged by selector |
| **`idempotent_discarded_total`** by reason | Messages actually routed to discard |
| **`metadata_store_latency / errors`** | Bottlenecks or outages in the state store |
| **`handler_success / failure`** | Distinguishes admitted vs. business-processed |
| **`retry / DLQ / lag`** | Signals active replays or backlogs |
| **`retention/key count`** | Memory and storage growth risk |

Never equate **admitted by selector** with **business committed**. Traces should correlate broker message ID, business `eventId`, idempotency key (masked/hashed if sensitive), metadata operations, and transaction/correlation IDs.

For high-reliability flows, build dashboards comparing:

- `accepted - business_success`: requests still in-flight or failed after admission;
- sudden duplicate spikes: broker redeliveries, retry policies, or bad key formulas;
- rising store timeouts: metadata load, DB locks, Redis saturation;
- rising discards with anomalous ACK/DLQ counts: check discard channels and exception policies.

Never put `eventId`, `tenantId`, or `customerId` into high-cardinality metric labels. Avoid logging full payloads, tokens, or PII; use hashed/masked IDs and controlled sampling.

## 15. Common Pitfalls and Fixes

**"Attaching the interceptor automatically drops duplicates."** False. By default it **sets a header** and still invokes the handler. To drop, configure `discardChannel` or `throwExceptionOnRejection`.

**"`MetadataStore.get()` followed by `put()` is concurrency-safe."** False. Two workers can both read `null`. Use **`ConcurrentMetadataStore.putIfAbsent`** or compare-and-set appropriately.

**"`SimpleMetadataStore` suffices across multiple Kubernetes pods."** False when deduplication must span pods or survive restarts. Use a shared persistent store and test atomicity.

**"Using `headers.id` is enough."** Uncertain: technical message IDs can change on redelivery or transformation. Define a stable business event ID.

**"If the selector wrote the key, the handler definitely succeeded."** False. Keys are written before the handler runs; if an error occurs after admission, redelivery can be blocked. Use transactions, inbox/`processed_event` tables, or proper recovery protocols.

**"Every exception indicates a duplicate."** False. Store errors, network errors, validation errors, and duplicates are distinct states; meter and handle them separately.

**"Just remove the key when the handler fails."** Insufficient. You can collide with concurrent workers or partially executed side effects; inspect old values, in-flight state, and transactions before compensating.

**"Deduplicating by `eventId` solves out-of-order events too."** False. Events with distinct IDs yet older versions can still regress state; enforce version checkpoints and conditional business writes.

**"Shorter TTLs are always cheaper and better."** TTL must at least cover the valid replay horizon; premature eviction allows stale events to reprocess.

**"ACKing once the interceptor accepts is enough."** False if side effects haven't committed. ACK points must reflect processing state per adapter/broker contracts.

## 16. Pre-Deployment Design Checklist

1. Define **what constitutes a duplicate** per consumer: `eventId`, `operationId`, version, or composite key.
2. Scope prefixes/regions cleanly; never collide keys across flows or business domains.
3. Choose **mark mode** if the handler needs to inspect duplicates; choose **discard mode** when duplicates can be dropped outright.
4. Avoid **`throwExceptionOnRejection`** if the adapter will endlessly retry routine duplicates.
5. Use **`ConcurrentMetadataStore`** with atomic `putIfAbsent`/`replace`; verify real backend and topology behavior.
6. Define the timing of **claim, business commit, ACK**, and crash recovery at every point.
7. When business side effects must happen once, enforce unique keys, idempotency keys, or conditional writes directly in the target DB or API.
8. Distinguish **duplicates, out-of-order events, retryable failures, and poison messages** across routing and error channels.
9. Set retention/TTL according to broker redelivery windows and replay needs; monitor metadata growth.
10. Test mark/discard modes, restarts, multi-instance contention, handler failures, store failures, and transaction rollbacks.
11. Measure accepted, discarded, handler success, retries, DLQ, and store latency; keep sensitive data out of logs and metrics.

**Key takeaway:** **`MetadataStore`** holds state, **`MetadataStoreSelector`** checks and sets keys, and **`IdempotentReceiverInterceptor`** governs how duplicate messages travel to handlers. True integration correctness comes from aligning all three with business commits, ACKs, retries, and failure recovery.

## References

- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): metadata contract, store choices, and lifecycles.
- [Spring Integration Reference — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): interceptor mechanics, `duplicateMessage`, `discardChannel`, and `throwExceptionOnRejection`.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): constructors, `putIfAbsent`, and `compareValues`.
- [Spring Integration Reference — JDBC Metadata Store](https://docs.spring.io/spring-integration/reference/jdbc/metadata-store.html): `JdbcMetadataStore`, schema, transactions, and atomicity.
- [Spring Integration Reference — Idempotent Downstream Processing a Split File](https://docs.spring.io/spring-integration/reference/file/splitter.html): checkpoint example with `compareValues`.
- [Spring Integration API — IdempotentReceiverInterceptor](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html): marking, filtering, and rejecting duplicate messages.
