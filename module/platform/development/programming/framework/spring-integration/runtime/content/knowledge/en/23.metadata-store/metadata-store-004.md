# Metadata Key Expressions in Spring Integration Runtime

## 1. What Problem Does a Metadata Key Expression Solve?

In **SPRING_INTEGRATION_RUNTIME**, messages can be resent due to retries, broker redelivery, poller restarts, network errors, or operator replays. A message may carry a new `MessageHeaders.ID` yet represent **the same business event**. If the handler writes an order, issues an invoice, or calls a payment API multiple times, the system can create duplicate side effects.

Spring Integration provides `MetadataStore` to store **small string key–value state**. When used with the **Idempotent Receiver** pattern, a `MetadataStoreSelector` derives a key from the message, checks whether the key already exists, and decides whether to accept or mark/reject the message.

A **metadata key expression** is a Spring Expression Language (SpEL) expression that computes that key, typically configured via the `key-expression` attribute on `<int:idempotent-receiver>`. It is neither a SQL query nor an automatic feature of the `MetadataStore` interface.

Example of the same shipment being received twice:

~~~text
Message A: payload.shipmentId = "SHP-101", headers.tenantId = "shop-1"
Message B: payload.shipmentId = "SHP-101", headers.tenantId = "shop-1"

key-expression = 'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId

A -> metadata key "shipment:v1:shop-1:SHP-101" -> absent -> accept
B -> metadata key "shipment:v1:shop-1:SHP-101" -> present -> duplicate
~~~

This lesson belongs to the **Metadata store** chapter, focusing on how to **choose a key aligned with the logical identity of the work**, how to apply that expression at a consumer endpoint, and the runtime implications for concurrency, retries, transactions, message stores, correlation, errors, and performance.

~~~mermaid
flowchart LR
    M["Message"] --> K["Evaluate key-expression"]
    K --> S{"ConcurrentMetadataStore.putIfAbsent(key, value)"}
    S -->|New key| A["Message accepted"]
    S -->|Existing key| D{"Duplicate policy"}
    A --> H["Message handler"]
    D -->|discard-channel| Q["Duplicate channel"]
    D -->|no discard| F["Set header duplicateMessage=true"]
    F --> H
    D -->|throwExceptionOnRejection| E["MessageRejectedException"]
~~~

Note: the key is usually **registered before the business handler completes**. Key-based deduplication alone is not sufficient to guarantee that the business transaction committed or that processing happened exactly once.

## 2. Components to Distinguish

| Component | Responsibility | Input and Output |
| --- | --- | --- |
| `MetadataStore` | Store/get/remove metadata | `String key → String value` |
| `ConcurrentMetadataStore` | Adds atomic update operations | `putIfAbsent(key, value)` and `replace(key, old, new)` |
| `MetadataStoreSelector` | Extracts key/value and evaluates new vs. duplicate | `Message<?> → boolean accept` |
| `IdempotentReceiverInterceptor` | Applies selector result to `MessageHandler.handleMessage()` | Pass through, set duplicate header, or discard/throw |
| `key-expression` | SpEL to **generate the key** for the selector | `Message<?> → String key` |
| `value-expression` | SpEL to **generate the value** stored with the key | `Message<?> → String value` |
| `compare-values` | Compares stored and new values for the same key | `(oldValue, newValue) → boolean` |

Two key points:

1. **`MetadataStore` does not understand SpEL.** It knows `get`, `put`, and `remove`. `ConcurrentMetadataStore` adds `putIfAbsent` and `replace`. The `key-expression` evaluation belongs to the endpoint/selector using the store.
2. **`MessageStore` is distinct from `MetadataStore`.** A message store persists messages or message groups; a metadata store persists markers/idempotency state. Both may use JDBC, Redis, or other backends, but neither replaces the other's role.

For instance, when polling SFTP, a persistent accept-once file filter can use a metadata store to remember already-seen files. However, how the **file filter** constructs its keys is defined by the filter/adapter, potentially combining prefix/path/modified time; the `key-expression` attribute on **idempotent receiver** is not automatically used by a file filter. Always identify the exact component owning key generation.

## 3. SpEL Evaluation: The Root Object Is the Message

On `<int:idempotent-receiver key-expression="...">`, the expression is passed to `MetadataStoreSelector`'s `ExpressionEvaluatingMessageProcessor`. In this case, **the evaluation root is the incoming `Message<?>`**. Therefore, you can access:

- `payload`: the business data.
- `headers`: the metadata map attached to the message.
- `headers['tenantId']`, `headers['eventId']`: specific header values.
- `payload.shipmentId`: a payload property if the payload exposes a SpEL/JavaBean-compatible accessor.

Example using a POJO with `getShipmentId()` so `payload.shipmentId` resolves cleanly:

~~~java
public final class Shipment {
    private final String shipmentId;
    private final String status;

    public Shipment(String shipmentId, String status) {
        this.shipmentId = shipmentId;
        this.status = status;
    }

    public String getShipmentId() {
        return shipmentId;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Comparison of key choices:

| Expression | Expected Key | Notes |
| --- | --- | --- |
| `headers['eventId']` | `evt-182` | Good when event ID is stable and unique per logical event |
| `'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId` | `shipment:v1:shop-1:SHP-101` | Includes namespace and tenant to avoid key collisions |
| `payload.shipmentId` | `SHP-101` | Dangerous if multiple tenants can share the same shipment ID |
| `headers['id'].toString()` | Transport message UUID | Typically **not stable across redelivery** or recreated messages |
| `headers['correlationId']` | Flow group ID | Can erroneously merge distinct messages belonging to the same group |
| `payload.toString()` | Depends on object `toString()` | Should not be used: fragile and may expose sensitive data |

**Choose identity at the business unit you need to deduplicate.** If two messages share `orderId` but represent distinct events `order.created` and `order.cancelled`, you cannot use `orderId` alone and drop one of them. Use `eventType + eventId`, or `tenant + orderId + operationType` per contract.

### SpEL Expressions and Interpolation

In XML, `key-expression` takes **raw SpEL**, without wrapping the entire value in `#{...}` like a bean-property reference. For example:

~~~xml
key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
~~~

The single quotes around `shipment:v1:` and `:` are **SpEL string literals**. The outer double quotes are XML attribute syntax. For headers containing dots or hyphens, `headers['x-correlation-id']` is clearer than `headers.x-correlation-id`.

Deployed expressions should be treated as **trusted configuration**. Never take SpEL strings directly from HTTP headers or user payloads and parse/evaluate them with arbitrary bean access.

## 4. Designing Stable, Unique, and Properly Scoped Keys

A good key must simultaneously satisfy:

1. **Stability:** the same logical event produces the same key across retries, redeliveries, restarts, or processing on another node.
2. **Proper scoping:** two distinct events must never accidentally produce the same key.
3. **Namespacing:** separate system, tenant, event/operation type, and key versions when needed.
4. **Canonical form:** trim, normalize casing, format IDs and delimiters consistently.
5. **Manageability:** length suitable for the backend, without leaking tokens/PII or creating uncontrolled cardinality.

An illustrative format:

~~~text
<environment>/<application>/<operation>/v<keyVersion>/<tenant>/<businessId>
prod/billing/issue-invoice/v1/shop-1/INV-2026-0021
~~~

This is an **application-designed key convention**, not a format imposed by Spring Integration. When using `/` as a delimiter, ensure each segment cannot contain `/` or encode segments properly to prevent key collisions.

**Example of a collision when concatenating without delimiters:**

~~~text
tenant="ab", order="c"   -> "abc"
tenant="a",  order="bc"  -> "abc"
~~~

Joining with escaped delimiters or encoding each field prevents this bug:

~~~text
order:v1:ab:c
order:v1:a:bc
~~~

For case sensitivity, only normalize case if the ID contract allows it. For example, `SHP-ab` and `SHP-AB` might be two distinct IDs in a system. Do not silently call `toLowerCase()` and erase business distinctions.

### Key Naming, Versioning, and Migration

| Change | Risk | Mitigation |
| --- | --- | --- |
| From `headers['eventId']` to `payload.orderId` | Old and new data use two different identity definitions | Plan a parallel-run window or key migration |
| Changing prefix `shipment:v1` to `shipment:v2` | Old duplicates may be accepted as new | Preserve compatibility or migrate metadata in a verified way |
| Changing ID normalization | Same event produces two different keys | Align producer and consumer on the same contract |
| Changing tenant namespace | Multiple tenants may share keys and block each other | Include stable tenant ID or isolate store scopes |
| Adding new shards/nodes | Per-node in-memory stores do not see other nodes' keys | Use a shared store supporting cross-node atomic operations |

A key needs **a version for its identity rule**, which does not have to match the payload schema version. When changing serializers without changing identity, you can keep the same key version so deduplication state remains valid.

## 5. XML Configuration: `key-expression` for Idempotent Receiver

The clearest place to see `key-expression` is the Spring Integration XML namespace. The fragment below uses a service activator backed by a handler bean, and an interceptor marks a shipment as duplicate if its key is already recorded:

~~~xml
<!-- Fragment: requires int namespace, shipmentService bean, and valid channels. -->
<bean id="dedupStore"
      class="org.springframework.integration.metadata.SimpleMetadataStore"/>

<int:channel id="shipments"/>

<int:service-activator id="shipEndpoint"
                       input-channel="shipments"
                       ref="shipmentService"
                       method="handle"/>

<int:idempotent-receiver
    id="shipmentIdempotent"
    endpoint="shipEndpoint"
    metadata-store="dedupStore"
    key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
    discard-channel="nullChannel"/>
~~~

Here:

- `endpoint="shipEndpoint"` is the **endpoint ID** to advise, not the channel name.
- `metadata-store="dedupStore"` is the `ConcurrentMetadataStore` bean used to store keys.
- `key-expression` computes the key for each message before the handler is invoked.
- `discard-channel="nullChannel"` intentionally **drops** duplicates; if you want to monitor them, send to a channel with a subscriber receiving duplicates.
- `SimpleMetadataStore` holds state only in the current context's memory; restarts lose keys, so it fits **demos**, not cross-restart deduplication requirements.

**Expected outcome:** two messages with the same `tenantId` and `shipmentId` sent consecutively: the first reaches `shipmentService.handle(...)`, and the second is discarded to `nullChannel`. If the tenant differs while the shipment ID is identical, the keys differ so both are processed.

### Configuring `value-expression`

Often only the key is needed to decide "already seen?". `MetadataStoreSelector` stores the **timestamp header** as the default value (in a string representation chosen by the selector). You can customize the value:

~~~xml
<int:idempotent-receiver
    id="shipmentWithValue"
    endpoint="shipEndpoint"
    metadata-store="dedupStore"
    key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
    value-expression="headers['eventId']"
    discard-channel="nullChannel"/>
~~~

This is an **alternative configuration**—do not declare it alongside the previous interceptor bean on the same endpoint when demonstrating a single check. `value-expression` does not by itself alter the rule "if the key exists, it is duplicate." When you want to **compare old and new values** to decide whether to accept the message, configure `compare-values` explicitly.

Ensure `eventId` provides a valid String value; if the header is missing or SpEL throws, the message may fail during key/value selection before the handler runs.

### Mutually Exclusive Attributes

| Attribute | Function | Relationship |
| --- | --- | --- |
| `selector` | Application-provided `MessageSelector` bean | Cannot be used with `metadata-store` and `key-strategy`/`key-expression` |
| `key-expression` | SpEL generating idempotent key | Cannot be used with `key-strategy` |
| `key-strategy` | `MessageProcessor` bean generating key | Cannot be used with `key-expression` |
| `value-expression` | SpEL generating value | Cannot be used with `value-strategy` |
| `value-strategy` | `MessageProcessor` bean generating value | Cannot be used with `value-expression` |
| `compare-values` | `BiPredicate<String,String>` bean comparing old/new | Only used when values carry comparable meaning |
| `throw-exception-on-rejection` | Throws when duplicate is rejected | Must understand rollback/retry impact |

The XML fragment uses the `int` namespace and schema matching your Spring Integration version. In Spring Boot/Java configuration, you can use Java DSL or annotations; XML is not required.

## 6. Equivalent Java Configuration: `MetadataStoreSelector`

The Java API uses a `MessageProcessor<String>` instead of SpEL. This is advantageous when key generation needs validation, canonicalization, hashing, or complex business rules:

~~~java
ConcurrentMetadataStore metadataStore = new SimpleMetadataStore();

MetadataStoreSelector selector = new MetadataStoreSelector(
    message -> {
        Shipment shipment = (Shipment) message.getPayload();
        String tenant = (String) message.getHeaders().get("tenantId");

        if (tenant == null || tenant.isBlank() ||
                shipment.getShipmentId().isBlank()) {
            throw new IllegalArgumentException("Missing stable identity");
        }

        return "shipment:v1:" + tenant + ":" + shipment.getShipmentId();
    },
    metadataStore
);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
advice.setDiscardChannelName("nullChannel");
~~~

The snippet above illustrates the **core logic**; the `Shipment` type, imports, and Spring bean wiring appear in the complete example in section 7. Comparison:

| XML SpEL | Java Callback |
| --- | --- |
| `key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"` | `message -> "shipment:v1:" + tenant + ":" + shipment.getShipmentId()` |
| Concise, well suited for simple formulas | Easy to set breakpoints, validate inputs, and write unit tests |
| SpEL uses the framework's evaluation context | Java compiler catches method/type errors better |
| Configured via XML attributes | Register selector/interceptor beans via `@Configuration` |

Both approaches serve **idempotent key selection**. If you need to share one formula between XML and Java, place canonicalization logic in a separate bean/service and reference it in the supported way. Do not attach both interceptors to one endpoint unless you intentionally want two distinct checking layers.

## 7. Complete Java Example: Receive Shipments, Drop Duplicates

Java 17+, Spring Boot compatible with Spring Integration. Place all code in `MetadataKeyDemoApplication.java` under package `demo.integration`. Requires Spring Integration Core or a compatible `spring-boot-starter-integration` dependency and component scanning on this package.

~~~java
package demo.integration;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IdempotentReceiver;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class MetadataKeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataKeyDemoApplication.class, args);
    }

    @Bean("shipments")
    MessageChannel shipments() {
        return new DirectChannel();
    }

    @Bean("shipmentMetadataStore")
    ConcurrentMetadataStore shipmentMetadataStore() {
        return new SimpleMetadataStore();
    }

    @Bean("shipmentIdempotentAdvice")
    IdempotentReceiverInterceptor shipmentIdempotentAdvice(
            @Qualifier("shipmentMetadataStore") ConcurrentMetadataStore store) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    Shipment shipment = (Shipment) message.getPayload();
                    String tenant = Objects.toString(
                            message.getHeaders().get("tenantId"), "");

                    if (tenant.isBlank() || shipment.id().isBlank()) {
                        throw new IllegalArgumentException(
                                "tenantId and shipment.id are required");
                    }

                    return "shipment:v1:" + tenant + ":" + shipment.id();
                },
                store
        );

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);
        advice.setDiscardChannelName("nullChannel");
        return advice;
    }

    @Bean
    ApplicationRunner produce(
            @Qualifier("shipments") MessageChannel input,
            @Qualifier("shipmentMetadataStore") ConcurrentMetadataStore store) {

        return args -> {
            send(input, "shop-1", "SHP-101");
            send(input, "shop-1", "SHP-101"); // duplicate
            send(input, "shop-2", "SHP-101"); // different tenant

            System.out.println("storedKey="
                    + store.get("shipment:v1:shop-1:SHP-101"));
        };
    }

    private static void send(
            MessageChannel input, String tenant, String shipmentId) {

        Message<Shipment> message = MessageBuilder
                .withPayload(new Shipment(shipmentId))
                .setHeader("tenantId", tenant)
                .setHeader("traceId", "trace-" + tenant + "-" + shipmentId)
                .build();
        input.send(message);
    }
}

// Illustrative domain record, kept package-private in the same file.
record Shipment(String id) { }

@MessageEndpoint
class ShipmentEndpoint {

    private final AtomicInteger processed = new AtomicInteger();

    @ServiceActivator(inputChannel = "shipments")
    @IdempotentReceiver("shipmentIdempotentAdvice")
    public void handle(Shipment shipment) {
        System.out.println("PROCESS #" + processed.incrementAndGet()
                + " shipment=" + shipment.id());
    }
}
~~~

Expected behavioral output:

~~~text
PROCESS #1 shipment=SHP-101
PROCESS #2 shipment=SHP-101
storedKey=<stored timestamp string>
~~~

**The two PROCESS lines** above correspond to `shop-1` first occurrence and `shop-2` first occurrence. The duplicate second message for `shop-1` does not reach the handler. Because the print only includes `shipmentId`, the log omits the tenant; in real systems log tenant or trace ID as well to distinguish them.

`storedKey` is not `null` by default: upon the first acceptance, `MetadataStoreSelector` wrote a value for the key. The default value is derived from the timestamp header and can vary across messages/runs. The demo primarily confirms **key existence**, without relying on the value format as a business contract.

**Intentional limitation:** `SimpleMetadataStore` is process-local memory. The demo shows deduplication within a single run, not duplicate prevention across two parallel app instances or across restarts.

### Using `@IdempotentReceiver` or Java DSL

`@IdempotentReceiver("shipmentIdempotentAdvice")` is placed on the same method carrying a messaging annotation, such as `@ServiceActivator`. The name must match the `IdempotentReceiverInterceptor` bean in the Spring context.

With Java DSL, you can attach the interceptor at the endpoint:

~~~java
@Bean
IntegrationFlow shipmentFlow(
        ShipmentService service,
        IdempotentReceiverInterceptor shipmentIdempotentAdvice) {

    return IntegrationFlow.from("shipments")
            .handle(service, "handle",
                    e -> e.advice(shipmentIdempotentAdvice))
            .get();
}
~~~

This is an **alternative** to `@MessageEndpoint` in the demo, requiring a `ShipmentService` bean and imports. Do not run both consumers on the same `DirectChannel` simultaneously if you want each message processed once by a single endpoint.

## 8. Does the Selector Accept, Discard, or Mark Duplicates?

When `MetadataStoreSelector` evaluates a key:

1. Compute the key from the message.
2. Compute the value from the message (by default from the timestamp header or a custom strategy).
3. Call atomic insert via `ConcurrentMetadataStore.putIfAbsent(key, value)`.
4. If the key **is absent**: write key/value and return `true`.
5. If the key **already exists**: normally return `false`; optionally use `compareValues` to accept the new value under replacement rules.

`IdempotentReceiverInterceptor` handles a `false` result as follows:

| Interceptor Configuration | When Selector Returns `false` | Is Handler Invoked? |
| --- | --- | --- |
| No `discardChannel`, no exception thrown | Creates a message with header `duplicateMessage = true` | **Yes**; downstream must decide what to do |
| `discardChannel = "nullChannel"` | Routes duplicate to sink to drop it | **No** |
| `discardChannel = "duplicates"` | Routes duplicate to a channel for logging/investigation | **No** (separate duplicate consumer runs) |
| `throwExceptionOnRejection = true` | Throws `MessageRejectedException` per contract | **No**; watch rollback and retry impact |
| Both discard channel **and** throw on rejection | Sends duplicate to discard, then may still throw | **No**; avoid ambiguous configuration |

The `duplicateMessage` header is **the idempotent interceptor's signal**; it is not present by default on all messages. Use `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE` or the framework-defined header name rather than inventing a mismatched string.

Distinguish two policies:

- **Detect only:** still delivers duplicates to the handler, which inspects the flag and skips non-idempotent work if needed. Fits cases where downstream needs to know about duplicates for auditing.
- **Reject/discard:** drops duplicates before the handler, simpler when duplicates must not trigger business logic. Requires measuring discards and ensuring the first key's business work actually completed.

## 9. `value-expression` and `compareValues`: One Key Can Represent Progress

Sometimes individual records do not each need their own key. For example, a poller/splitter processing a 10,000-line file can use `fileName` as the key and `lineNumber` as the value to remember the last accepted line.

~~~text
key   = "file:v1:orders-2026-11-22.csv"
value = "125"

message line 126 -> compare old=125, new=126 -> accept, replace
message line 124 -> compare old=126, new=124 -> reject
~~~

Illustrative Java example:

~~~java
ConcurrentMetadataStore store = new SimpleMetadataStore();

MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> "file:v1:" + message.getHeaders().get("fileName"),
        message -> String.valueOf(message.getHeaders().get("lineNumber")),
        store
);

selector.setCompareValues((oldValue, newValue) -> {
    long oldLine = Long.parseLong(oldValue);
    long newLine = Long.parseLong(newValue);
    return newLine > oldLine;
});
~~~

`compareValues` accepts a `BiPredicate<String, String>` where the **first parameter is the old value** and the second is the new value. When the predicate accepts, the selector can replace the value via an implementation-provided atomic update and continue accepting the message. This logic works well when *there is a single monotonically advancing progress marker*.

**Important ordering warning:** if lines are processed concurrently or can arrive out of order, receiving line 126 first makes line 125 look stale and get skipped **even though it was never processed**. Use this high-water mark pattern only when the source, consumer, and processing policy guarantee ordering or when skipping lower values is valid.

Another option is keying by `fileName + lineNumber` to track each line individually, though key count scales with line count. Consider retention, grouping/correlation, and progress compaction strategies suited to your volume.

### Do Not Confuse `value-expression` with Key

In the line-number example:

- `key-expression` selects the **identity unit** (the filename).
- `value-expression` selects the **progress value** (the line number).
- `compare-values` decides **whether progress may advance**.

Without `compareValues`, an already-existing file key typically marks subsequent lines as duplicates even when their line numbers differ; setting `value-expression` alone does not solve the update logic.

## 10. Consumer Contention: Why Is `ConcurrentMetadataStore` Needed?

Suppose two executor workers receive the same logical event nearly simultaneously:

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant S as ConcurrentMetadataStore
    participant W2 as Worker 2
    W1->>S: putIfAbsent("shipment:shop1:SHP101", value1)
    W2->>S: putIfAbsent("shipment:shop1:SHP101", value2)
    S-->>W1: null (insert succeeded)
    S-->>W2: value1 (already exists)
    W1->>W1: handler processes
    W2->>W2: duplicate -> discard / mark
~~~

If code only ran `if (store.get(key) == null) store.put(key, value)`, two workers could **both observe the key as absent** and both process it. `ConcurrentMetadataStore.putIfAbsent` provides an atomic insert contract.

However, system-wide atomicity depends on the backend:

| Backend | Synchronization Scope | Recommendation |
| --- | --- | --- |
| `SimpleMetadataStore` | Within the same app/JVM | Suitable for unit tests and single-process apps |
| `PropertiesPersistingMetadataStore` | Memory/file per configuration | Do not assume a shared file across nodes acts as a distributed lock |
| `JdbcMetadataStore` | DB data via queries/transactions/unique constraints | Verify DDL, transaction manager, and multi-instance behavior |
| `RedisMetadataStore` | Redis when sharing key namespace/instance | Verify availability, eviction/TTL, and failover configuration |
| `MongoDbMetadataStore` / other backends | Per provider's atomic capabilities | Test conflicts, connection failures, and retention |
| Custom store | Per `putIfAbsent`/`replace` implementation | Test concurrency, restarts, and network faults |

A store implementing only `MetadataStore` without proper atomic methods may be **insufficient** for an idempotent receiver under concurrency.

### Write the Key Before or After Business Commit?

`MetadataStoreSelector` writes the key when the message is **accepted**, before the handler finishes successfully. This introduces a risk:

~~~text
putIfAbsent(key) -> succeeds
handler calls DB/API -> fails
message retried with same key -> selector sees duplicate -> blocks it
~~~

Therefore, this interceptor protects the **receive/mark-seen** step, without guaranteeing the entire business transaction completed. For critical work, consider:

- An **inbox table** with a unique constraint on event ID in the same DB transaction as business effects.
- A `RECEIVED → PROCESSING → COMPLETED/FAILED` state machine separating "seen" from "completed".
- Explicit recovery or compensation when a key was recorded but the handler failed.
- Bounded TTL/lease/retry state where supported, avoiding permanently locking incomplete work.
- Passing an idempotency key to external APIs; if the API lacks support, add outcome reconciliation.

Do not blindly call `store.remove(key)` in every `catch` block: if another worker already handled or updated the key, hasty deletion opens the door to duplicates. When conditional deletion/replacement is needed, design ownership/versioning and appropriate atomic operations.

## 11. Retries, Transactions, Pollers, and Executors in Real Flows

Metadata selection executes when an endpoint processes a message. Where that endpoint sits across channel types determines threading, error handling, and observable duplication.

| Boundary | What Happens at Runtime | What Must Be Checked |
| --- | --- | --- |
| `DirectChannel` | Idempotent advice and handler typically run synchronously on the `send()` thread | Whether exceptions propagate to sender, and whether transaction covers both store and business DB |
| `ExecutorChannel` | Selector/handler run on a worker thread after async handoff | Worker error flow, pool saturation, and shared store across workers |
| `QueueChannel` + poller | Selector is invoked when message is pulled for processing | Dequeue timing, transaction, and redelivery possibilities |
| Broker inbound adapter | Broker may redeliver the same event when ack fails | Keep key stable across deliveries; consistency between ack and business state |
| Dynamically registered `IntegrationFlow` | Endpoints start/stop with flow lifecycle | Whether store/advice beans outlive stop/remove, and whether key namespaces are reused |

### Advice Ordering and Retries

Suppose retry and idempotent advice are both placed on one endpoint:

~~~text
Retry outside -> each attempt may pass through the idempotent selector
Idempotent outside -> each logical message checks the key before inner retries
~~~

When the idempotent selector sits **inside retry**, the key written on the first attempt can make the next attempt look like a duplicate. When the selector sits **outside retry**, an inner retry loop can run multiple attempts while marking the key once, though if all attempts fail the key still remains.

Thus, advice ordering must be decided alongside the **commit/recovery contract**. Combining transaction advice, poller retries, and broker redelivery demands fault injection at the exact boundaries. Never assume a particular advice order automatically yields "exactly once".

### Transactions

`ConcurrentMetadataStore` does not automatically enlist in a transaction with your business database. For example, with metadata in Redis and business data in JDBC, a JDBC rollback does not delete the Redis key. Even when both use JDBC, confirm that the transaction manager/DataSource, isolation level, and timing of store calls actually participate in the right transaction.

If metadata writes commit separately before the handler fails, `@Transactional` on the handler does not guarantee the key rolls back. Verify via actual store and DB state after failure, not just rollback logs.

### Correlation and Message Identity

Headers like `correlationId`, `sequenceNumber`, and `sequenceSize` are helpful when splitters/aggregators join messages of a group, yet are typically **insufficient** to identify independent events. Multiple parts in the same group share `correlationId`; using it as a unique key will drop subsequent parts. A splitter idempotency key may need `correlationId + sequenceNumber`, if sequences are stable for the logical group.

`MessageHeaders.ID` can change when a message is reconstructed; for broker redelivery, choose an application `eventId`/`operationId` kept stable by the producer. Never use thread names, receive timestamps, or newly generated per-delivery UUIDs as idempotent keys.

## 12. Durable Persistence, Restarts, and Key Lifecycle

Without a persistent store configured, an application using `SimpleMetadataStore` loses metadata after restart. This can lead to duplicate processing of messages resent by the broker.

~~~text
T0: app A accepts eventId=evt-7 -> key sits in A's memory
T1: app A restarts -> memory wiped
T2: broker redelivers evt-7 -> key absent -> app A treats it as new
~~~

To retain markers across restarts, select a suitable backend (`JdbcMetadataStore`, `RedisMetadataStore`, `MongoDbMetadataStore`, or another persistent implementation as needed). Pay attention to DB schema, credentials, namespaces, flush/commit, backups, startup recovery, and availability.

`PropertiesPersistingMetadataStore` can persist to a file, but by default typically writes state on normal context shutdown or when `flush()` is called per contract. Do not assume an abrupt crash preserves unflushed keys.

### Retention and TTL

Writing keys forever causes unbounded store growth. If the application defines a 30-day deduplication window, design an expiration/cleanup mechanism:

- **Deduplication retention** must exceed the permitted broker redelivery/replay window, otherwise old duplicates slip through after early deletion.
- **Mistakenly deleting** a key while a handler is still executing can let a second worker accept the same event.
- Once data expires, the application needs an explicit policy on whether to treat an old event as new, send it for review, or reject it based on event age.
- If using a TTL-capable backend, verify the backend's own TTL and eviction policies; do not assume every `MetadataStore` provides automatic TTL.

Reducing cardinality with `compareValues` fits certain monotonically advancing flows but cannot replace per-event keys for all problems.

## 13. Debugging Wrong Expressions, Wrong Keys, or Escaped Duplicates

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Empty key, not found in store | Missing header, null payload property, SpEL evaluation error | Log payload/header types safely; test expression with sample messages |
| Messages from two tenants treated as duplicates | Key omits tenant or normalization causes collision | Compare computed keys (masked) and key namespaces |
| Every message after the first is blocked | `key-expression` returns a constant or same ID for the whole flow | Evaluate expression against multiple distinct event payloads |
| Duplicates still reach handler | No `discardChannel`, interceptor only sets `duplicateMessage=true` | Check duplicate header and discard configuration |
| Duplicate blocked after one handler error | Key written before commit; retry reuses key | Trace timeline of metadata write → handler → transaction |
| Restart causes old events to rerun | Using `SimpleMetadataStore` or unflushed/non-durable store | Test stop/restart with the backing store |
| Two instances run the same event | Instances use separate stores or non-atomic ops | Confirm shared `ConcurrentMetadataStore`; test concurrent sends |
| `compareValues` skips valid events | High-water mark with out-of-order messages | Switch to per-event keys or enforce strict ordering |
| Logs contain PII in keys | Raw email/customer identifier concatenated into key | Use opaque IDs or versioned keyed hashes |
| Store grows large and lookups slow down | No retention, overly long keys, unsuitable indexes/connections | Measure key count, p95 lookup, backend indexes, and purge jobs |

### Immediate Inspection Checklist

1. Pick **two concrete messages**: one that must be accepted and one that must be treated as duplicate; record logical event ID, tenant, operation, and payload type.
2. Compute the **expected key** per contract outside the handler.
3. Verify the actual expression/callback against the real message root: `payload` and `headers`.
4. Log the `putIfAbsent` result or selector decision (masking sensitive data), and inspect the metadata value.
5. Check whether the interceptor has a `discardChannel` or only sets the `duplicateMessage` header.
6. Inject a fault **after selector acceptance but before business commit**, and verify how message retries behave.
7. Repeat testing with two concurrent consumers, across a restart, and across two instances sharing the store.
8. Monitor metrics: `dedupe.accepted`, `dedupe.duplicate`, `dedupe.selector.error`, store latency, key count, and retry/redelivery counts.

**Never tag metrics with `eventId`, `orderId`, or full metadata keys** because cardinality explodes. Use labels like `endpoint`, `operation`, `tenantTier` (if low-cardinality and permitted), `result`, and `storeType`; put event IDs in traces/logs per security policy.

## 14. Security and Performance of Key Expressions

Expressions run on the message-ingestion path; if an expression queries a database or external service, latency multiplies across messages and bottlenecks `DirectChannel`, pollers, or executors.

Guidelines:

- Keep key expressions **deterministic and lightweight**. Read available properties/headers; avoid side effects, HTTP/DB calls, or randomness.
- If a key needs hashing, version the algorithm and normalize inputs before hashing; test collisions and encoding.
- Avoid putting raw emails, tokens, document contents, or sensitive payloads verbatim into metadata keys unnecessarily.
- Never allow clients to supply **SpEL code to evaluate**. Clients only send data; the application configures the expression.
- Metadata backends should have least-privilege access, proper backups, and latency metrics on `putIfAbsent` and `replace`.
- Do not ignore store availability failures: if the store temporarily disconnects, explicitly decide fail-open vs. fail-closed; for expensive side effects, fail-open risks duplicates while fail-closed can throttle throughput.
- To increase concurrency, ensure keys distribute well and avoid an overly broad key that treats all traffic as duplicates.

### Performance Test Matrix

| Test Case | What to Observe |
| --- | --- |
| 10,000 unique messages | Selector throughput, backend latency, key growth |
| 10,000 messages with the same key | Handler invocation count, contention, and backend load |
| Multiple tenants with identical business IDs | Whether collisions occur |
| Multiple instances receiving the same event | Whether `putIfAbsent` allows only one accept in the shared store |
| Store disconnects | Error flow, backpressure, retries, and ack behavior |
| Reconnect after restart | Whether metadata persists or vanishes, whether duplicates reprocess |

With transactions, metadata writes and business side effects should be measured on the same timeline to catch "key written but work unfinished." Rising duplicate counters do not automatically indicate a bug; compare against redelivery sources and logical event counts.

## 15. Hands-On Exercises and Reasoning Scenarios

1. **Basic key:** run the Java demo in section 7; verify two messages for `shop-1`/`SHP-101` process once, while `shop-2` is still processed.
2. **Missing tenant in key:** change the selector to `shipment.id()` only and observe one tenant being wrongly dropped; restore the proper key.
3. **XML expression:** port the same Java formula to `key-expression` on `<int:idempotent-receiver>`; check literal quotes and `payload.shipmentId` with a POJO getter.
4. **No discard:** remove the discard channel; verify the handler receives the duplicate with `duplicateMessage=true` and handle the flag intentionally.
5. **Error before commit:** make the handler throw after the selector writes the key. Resend the same logical message; explain why it can be blocked and how to design an inbox/transaction/recovery flow.
6. **Progress value:** try `key=fileName`, `value=lineNumber`, and `compareValues`; send lines 1, 2, 4, 3 to observe the out-of-order effect.
7. **Concurrency:** send 100 messages with the same key from multiple threads in one JVM; next try two instances with a shared JDBC/Redis store matching your real version and setup.
8. **Restart:** replace `SimpleMetadataStore` with a persistent store and run the producer before/after restart, verifying metadata survives.
9. **Schema evolution:** add `eventType` to a v2 key; plan the rollout so old duplicates do not slip through.
10. **Diagnosis:** send an input missing `tenantId`; confirm no handler side effect occurs and the selector error is reported to the proper error flow/transaction boundary.

### Self-Check Questions

- Why is `headers['id']` usually a poor choice for an idempotent key?
- Which object is `key-expression` evaluated against? If the payload is a `String`, will `payload.shipmentId` work?
- What is the difference between `key-expression` and `value-expression`? When is `compareValues` truly necessary?
- Why is `putIfAbsent` better than `get()` followed by `put()` with concurrent consumers?
- If the selector writes a key successfully but the handler rolls back, does the metadata key automatically roll back?
- When configured without a `discardChannel`, does a duplicate still enter the handler?
- Is an in-memory metadata store sufficient for two app instances on two hosts and replays after restart?

## 16. Official References

- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): key–value contract, backends, and default metadata store.
- [Spring Integration — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): `key-expression`, `value-expression`, `compare-values`, `discardChannel`, and `@IdempotentReceiver`.
- [Spring Integration — SpEL](https://docs.spring.io/spring-integration/reference/spel.html): message root, `payload`, and `headers`.
- [Spring Integration Javadoc — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): `putIfAbsent`, selector constructors, and `compareValues`.
- [Spring Integration Javadoc — IdempotentReceiverInterceptor](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html): duplicate, discard, and exception semantics.
- [Spring Integration Javadoc — ConcurrentMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html): atomic `putIfAbsent` and `replace`.
- [Spring Integration Javadoc — IdempotentReceiver annotation](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IdempotentReceiver.html): method-level attachment.
