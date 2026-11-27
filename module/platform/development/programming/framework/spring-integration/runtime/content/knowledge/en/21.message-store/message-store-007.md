# Payload Serialization and Compatibility in Spring Integration Message Store

## 1. Why Can Stored Messages Still Be Unreadable?

In the **SPRING_INTEGRATION_RUNTIME** module, messages travel through channels, endpoints, consumers, pollers, and executors. When using `MessageStore` or `MessageGroupStore` to retain messages over time, operators also face a critical problem: **can data written by an older application version still be read and processed after deploying a new version?**

Suppose an order is placed into a durable queue at 09:00:

~~~text
Message<OrderCreatedV1>
payload = OrderCreatedV1("ORD-101", 125000)
headers = { eventId, correlationId, contentType, ... }
~~~

At 09:05, the application is redeployed. The new consumer uses `OrderCreatedV2` with an added `currency` field, a renamed older field, or a moved Java class package. When the remaining message in the store is read, it may fail deserialization, misinterpret the amount, lose correlation headers, or be rejected by the consumer.

The topic **Message store → Payload Serialization and Compatibility** answers:

1. Does `MessageStore` store **objects** or **bytes**? How are payloads and headers represented?
2. What is the difference among business schema compatibility, serializer compatibility, and storage structure compatibility?
3. How to design an envelope with `schemaVersion`, `eventId`, `contentType`, and multi-version codecs.
4. How to test readback, restarts, rolling deployments, replays, release rollbacks, and poison-message handling.
5. What is the impact on transactions, retries, message stores, correlation, threading, and runtime performance?

The goal is not merely "serializable today" but **preserving the ability to read remaining messages tomorrow**.

~~~mermaid
flowchart LR
    P["Old-version producer"] --> E["Encode payload + schemaVersion"]
    E --> S[("Persistent Message Store")]
    S --> N["New-version app\nread & deserialize"]
    N --> V{"Schema supported?"}
    V -->|Yes| U["Map to current model"]
    U --> C["Consumer / aggregator"]
    V -->|No| Q["Quarantine / DLQ\nfor separate handling"]
~~~

## 2. Distinguishing Messages, Payloads, Headers, and Stores

Spring Integration uses Spring Messaging's `Message<?>`, consisting of:

- **Payload:** the business object (e.g. `OrderCreated`), `String`, `byte[]`, or another data structure.
- **Headers:** `id`, `timestamp`, `correlationId`, `sequenceNumber`, `sequenceSize`, `replyChannel`, `errorChannel`, and custom metadata.
- **Channel/endpoint:** defines how messages are sent, received, and processed; not automatically preserved solely by serializing the payload.

A `MessageStore` provides the contract for storing/retrieving messages; `MessageGroupStore` serves **message groups** for components such as aggregators, resequencers, and certain correlation scenarios. `ChannelMessageStore` backs pollable channels/queues. The APIs are related, but you must pick the **store implementation matching what the endpoint requires**.

| Component | What Does It Store? | Compatibility Questions |
| --- | --- | --- |
| In-memory `SimpleMessageStore` | Message references in application memory | Does not survive restarts; easily hides serializer bugs because bytes may not be produced |
| `JdbcChannelMessageStore` with durable queue | Pending messages awaiting polling, stored in DB via provider representation | Message serializer, DB schema, dequeue transactions, whether payload/headers read back cleanly |
| `JdbcMessageStore` or suitable message-group store | Messages and group metadata for correlation/aggregation | Message serialization, group keys, sequences, release/expiry after upgrade |
| Redis, MongoDB, or other backend stores | Implementation/provider-specific representation | Serializers, codecs/mappers, key namespaces, TTLs, exact format/version |
| External broker or object storage outside Spring Integration | Bytes/records per that system's contract | Payload schema, headers, codecs, and adapter acknowledgments |

**Do not assume every persistent store uses JSON or the same serializer.** Some implementations persist representations based on Java serialization; others use dedicated mappers or configurable serializers. Even under `MessageStore`, storage representation and failure modes differ across backends and framework versions.

### Two Serialization Layers Must Both Be Verified

~~~text
Message<OrderCreated>                  (domain object)
         |
         v
Encode domain: JSON/Avro/Protobuf       (payload bytes + version)
         |
         v
Message<byte[]> + Headers               (Spring Message)
         |
         v
Store serializer / persistence mapper   (how store persists full message)
         |
         v
DB / Redis / Mongo / ...
~~~

Converting payloads to JSON `byte[]` **stabilizes the business contract**, yet does not eliminate all compatibility risks if the persistent store still serializes the **outer Message and headers** through another mechanism. Verify both layers against the actual production backend.

## 3. When Do Serialization and Deserialization Occur?

Knowing execution points helps determine whether exceptions surface on the sender thread or the poller thread:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant T as Payload encoder
    participant Q as Durable QueueChannel
    participant DB as Persistent store
    participant R as Polling consumer
    participant D as Payload decoder
    participant H as Business handler
    P->>T: Message<OrderCreated>
    T-->>Q: Message<byte[]> (versioned)
    Q->>DB: Store message (+ headers)
    Note over Q,DB: Encode/serialize outside or inside store
    R->>DB: Poll / claim / remove
    DB-->>R: Stored message
    R->>D: Message<byte[]>
    D->>H: Current OrderCreated
    Note over R,H: Decode, validate, process
~~~

| Boundary | Typical Activity | Possible Failures |
| --- | --- | --- |
| Transformer before store | Encodes domain payload into bytes | Invalid data, mapper does not support type |
| `send()` to store-backed channel | Serializes message per store provider and writes to backend | Non-serializable object/header, connection/transaction error, wrong store schema |
| `receive()` from store | Reads row/document and reconstructs message | Unrecognized class/serializer, corrupt bytes, post-deploy incompatibility |
| Decoder after poll | Converts payload bytes per `schemaVersion` to current model | Unknown version, missing field, incompatible type/enum |
| Business handler | Applies domain rules and side effects | Business errors, duplicates, transaction or dependency failures |

In some providers, conversion may be deferred or occur within another operation; this table shows **logical** boundaries to design observability, without claiming every backend executes the exact same method sequence.

If deserialization of the **outer message** fails when the store reads it, the business decoder never even runs. That requires store-level logging/error handling and a procedure for raw records. If the outer message reads fine but the payload schema is unsupported, the decoder can route the message to a quarantine/error flow.

## 4. Payload Formats and Compatibility Trade-offs

| Format | Benefits | Common Risks | How to Preserve Compatibility |
| --- | --- | --- | --- |
| Java object serialization | Convenient when code and data share the same JVM/version, no business mapper needed | Coupled to class names, `serialVersionUID`, fields, object graph; untrusted deserialization risk | Use only in controlled environments; test cross-version; enforce class allow-lists |
| UTF-8 JSON | Easy to inspect, cross-language, does not require legacy Java classes present | Field renames, number-to-string changes, new enums, missing schema/version; larger payloads | Versioned envelopes, readers accepting older fields per contract, validation |
| Avro | Compact binary, schema resolution, fits schema registries | Incompatible writer/reader schemas or misconfigured registry | Manage schema IDs/versions, compatibility policies, and field defaults |
| Protocol Buffers | Efficient binary, field numbers enable disciplined schema evolution | Reusing field numbers, changing wire types, shifting enum/oneof meanings | Never reuse field tags, reserve deleted fields, test schema evolution |
| CBOR/MessagePack/custom binary | Can be compact/fast | Lacks version rules and inspection tooling | Define schemas, magic/version markers, test historical data |

**Java `Serializable` does not equal backward compatibility.** A class can keep a stable `serialVersionUID` and still fail to read if a field changes to an incompatible type, the class is renamed/moved across packages, classloaders differ, or `readObject`/constructor logic mismatches. `InvalidClassException` and `ClassNotFoundException` are classic symptoms.

For data that persists long-term or crosses multiple application versions, define a **wire contract independent of runtime models**: event type code, schema version, encoding, event ID, correlation ID, and payload bytes. JSON is used in the examples for readability; the principles do not depend on JSON.

## 5. Schema Compatibility Has Multiple Dimensions

Suppose payload version 1:

~~~json
{
  "schemaVersion": 1,
  "eventType": "order.created",
  "eventId": "evt-1001",
  "correlationId": "corr-A",
  "data": {
    "orderId": "ORD-101",
    "amountMinorUnits": 125000
  }
}
~~~

Version 2 adds `currency`:

~~~json
{
  "schemaVersion": 2,
  "eventType": "order.created",
  "eventId": "evt-1002",
  "correlationId": "corr-A",
  "data": {
    "orderId": "ORD-102",
    "amountMinorUnits": 125000,
    "currency": "VND"
  }
}
~~~

In this example, **the v1 contract stipulated all amounts are in VND**. Thus, a v2 decoder can map v1 into the current model with `currency = "VND"`. If v1 allowed multiple currencies without distinguishing them, blindly filling in VND would **corrupt data**; in that case, migrate from a trusted source or route the record to manual error resolution.

| Compatibility Type | Question | In This Example |
| --- | --- | --- |
| **Backward** | Can a **new** reader read **old** data? | V2 decoder receives `schemaVersion=1` and fills VND per v1 contract |
| **Forward** | Can an **old** reader read **new** data? | Only if the old reader accepts new fields/versions; no if it rejects unknown versions |
| **Full** | Are both directions guaranteed? | Requires designing readers/versions and testing both directions |
| **Semantic compatibility** | Once read, is business meaning preserved? | `125000` remains minor currency units (not switched to major units) |

Schema evolution is not just getting a parser to accept new JSON. Parsing can succeed while **breaking meaning**—for instance, renaming `amountMinorUnits` to `amount` without adjusting unit rules, or repurposing a status field for a different state.

### Safe Changes vs. Dangerous Changes

- **Usually easy to evolve:** adding optional fields with valid business defaults; adding metadata that does not alter old decisions; keeping stored field names and types unchanged.
- **Requires a migration plan:** renaming fields, changing package/class names under Java serialization, switching `long` to `String`, changing currency units, changing timestamp formats, removing required fields.
- **Requires testing old readers:** adding new enum values/message types so older code no longer understands new cases.
- **Strictly avoid silently:** failing to parse and returning an empty object, picking arbitrary defaults for money or identifiers, or ignoring unknown event types as if processed successfully.

Version must be **part of the stored data**, not inferred solely from artifact version numbers or deployment timestamps. If both producers coexist during a rolling deployment, one queue can hold payloads of multiple versions simultaneously.

## 6. Standalone Runnable Versioned JSON Codec Example

Java 17+ example using `jackson-databind`. Place the code in `StoredOrderCodec.java`; the program encodes v2, reads back v2, and then reads a simulated v1 record stored earlier. This runs independently of Spring Integration to verify the **wire contract** before attaching a store.

~~~java
package demo.integration;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public final class StoredOrderCodec {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String EVENT_TYPE = "order.created";
    private static final int MAX_BYTES = 1024 * 1024; // 1 MiB demo limit

    private StoredOrderCodec() { }

    public record OrderCreated(
            String orderId, long amountMinorUnits, String currency) { }

    public record Decoded(
            String eventId, String correlationId, OrderCreated order) { }

    // Current writer: only writes schema v2.
    public static byte[] encodeV2(
            OrderCreated order, String eventId, String correlationId)
            throws JsonProcessingException {

        Objects.requireNonNull(order, "order");
        requireValue(eventId, "eventId");
        requireValue(correlationId, "correlationId");
        requireValue(order.orderId(), "orderId");
        requireValue(order.currency(), "currency");

        if (order.amountMinorUnits() <= 0) {
            throw new IllegalArgumentException("Invalid amountMinorUnits");
        }

        ObjectNode root = MAPPER.createObjectNode();
        root.put("schemaVersion", 2);
        root.put("eventType", EVENT_TYPE);
        root.put("eventId", eventId);
        root.put("correlationId", correlationId);

        ObjectNode data = root.putObject("data");
        data.put("orderId", order.orderId());
        data.put("amountMinorUnits", order.amountMinorUnits());
        data.put("currency", order.currency());

        byte[] bytes = MAPPER.writeValueAsBytes(root);
        if (bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Payload too large");
        }
        return bytes;
    }

    // Current reader: accepts v1 and v2.
    public static Decoded decode(byte[] bytes) throws IOException {
        if (bytes == null || bytes.length == 0 ||
                bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid payload size");
        }

        JsonNode root = MAPPER.readTree(bytes);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Invalid envelope");
        }

        int version = root.path("schemaVersion").asInt(-1);
        if (version != 1 && version != 2) {
            throw new IllegalArgumentException(
                    "Unsupported schemaVersion: " + version);
        }

        String type = requiredText(root, "eventType");
        if (!EVENT_TYPE.equals(type)) {
            throw new IllegalArgumentException(
                    "Unexpected eventType: " + type);
        }

        String eventId = requiredText(root, "eventId");
        String correlationId = requiredText(root, "correlationId");
        JsonNode data = root.path("data");
        if (!data.isObject()) {
            throw new IllegalArgumentException("Missing data object");
        }

        String orderId = requiredText(data, "orderId");
        JsonNode amount = data.path("amountMinorUnits");
        if (!amount.isIntegralNumber() ||
                !amount.canConvertToLong() ||
                amount.longValue() <= 0) {
            throw new IllegalArgumentException("Invalid amountMinorUnits");
        }

        // Per v1 business contract: amounts are always in VND.
        String currency = version == 1
                ? "VND"
                : requiredText(data, "currency");

        return new Decoded(eventId, correlationId,
                new OrderCreated(orderId, amount.longValue(), currency));
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Missing/invalid " + field);
        }
        return value.textValue();
    }

    private static void requireValue(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + field);
        }
    }

    public static void main(String[] args) throws Exception {
        OrderCreated order =
                new OrderCreated("ORD-102", 125000L, "VND");
        byte[] newBytes = encodeV2(order, "evt-1002", "corr-A");
        Decoded roundTrip = decode(newBytes);
        if (!order.equals(roundTrip.order())) {
            throw new AssertionError("v2 round-trip failed");
        }

        String legacyJson = """
            {
              "schemaVersion": 1,
              "eventType": "order.created",
              "eventId": "evt-1001",
              "correlationId": "corr-A",
              "data": {
                "orderId": "ORD-101",
                "amountMinorUnits": 125000
              }
            }
            """;
        Decoded old = decode(
                legacyJson.getBytes(StandardCharsets.UTF_8));

        if (!"VND".equals(old.order().currency())) {
            throw new AssertionError("v1 compatibility failed");
        }

        System.out.println("V2 " + roundTrip);
        System.out.println("V1->current " + old);
    }
}
~~~

Expected output:

~~~text
V2 Decoded[eventId=evt-1002, correlationId=corr-A, order=OrderCreated[orderId=ORD-102, amountMinorUnits=125000, currency=VND]]
V1->current Decoded[eventId=evt-1001, correlationId=corr-A, order=OrderCreated[orderId=ORD-101, amountMinorUnits=125000, currency=VND]]
~~~

This is a **codec test**, not a JDBC storage demo. Add the Jackson dependency to the classpath and configure your application's actual message store to verify the persistence layer.

### What Makes the Contract More Durable in This Example?

1. `schemaVersion` explicitly specifies how to read; `eventType` identifies the event kind.
2. `eventId` and `correlationId` live inside the **envelope**, aiding reconciliation even if some outer headers are lost.
3. Writers emit only **one current format**; readers support older formats still residing in the store.
4. The decoder enforces size bounds, validates numeric types, and rejects unknown events/versions rather than guessing.
5. The codec returns the current model; handlers do not need to know about version 1 vs. 2.
6. JSON bytes do not depend on the producer's Java class name, easing deployments and system scaling.

Note: `ObjectMapper` is used as a singleton whose configuration is never mutated after initialization; this pattern is safe across multiple consumer threads. Production may require stronger validators, per-event-type byte limits, and text/identifier normalization conventions.

## 7. Wiring the Codec to Spring Integration Channels and Endpoints

Separating **encode** before the message store and **decode** after retrieval keeps boundaries crisp. Below are two illustrative endpoint methods using `StoredOrderCodec` from Section 6.

~~~java
import java.io.IOException;

import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

@MessageEndpoint
class PersistedOrderTransforms {

    @Transformer(
            inputChannel = "newOrders",
            outputChannel = "durableOrders")
    public Message<byte[]> encode(
            Message<StoredOrderCodec.OrderCreated> input)
            throws IOException {

        Object eventId = input.getHeaders().get("eventId");
        Object correlation = input.getHeaders().get("correlationId");
        if (!(eventId instanceof String id) || id.isBlank() ||
            !(correlation instanceof String corr) || corr.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing eventId/correlationId headers");
        }

        byte[] encoded = StoredOrderCodec.encodeV2(
                input.getPayload(), id, corr);

        return MessageBuilder.withPayload(encoded)
                .copyHeaders(input.getHeaders())
                .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
                .setHeader("payloadSchemaVersion", 2)
                .build();
    }

    // durableOrders is configured as a pollable channel backed by a message store.
    @Transformer(
            inputChannel = "durableOrders",
            outputChannel = "decodedOrders",
            poller = @Poller(fixedDelay = "1000"))
    public Message<StoredOrderCodec.OrderCreated> decode(
            Message<byte[]> input) throws IOException {

        StoredOrderCodec.Decoded decoded =
                StoredOrderCodec.decode(input.getPayload());

        return MessageBuilder.withPayload(decoded.order())
                .copyHeaders(input.getHeaders())
                .setHeader("eventId", decoded.eventId())
                .setHeader("correlationId", decoded.correlationId())
                .build();
    }
}
~~~

**Conditions for this snippet to work:**

- Declare channels `newOrders`, `durableOrders`, and `decodedOrders`, plus a consumer on `decodedOrders`.
- `durableOrders` must be a **pollable queue channel** wired to an appropriate persistent store—not merely a `DirectChannel` named "durable".
- `@Poller` pulls messages from the queue; configure thread pools, transactions, and error handling per runtime needs.
- `copyHeaders(...)` carries required metadata across representations, though system IDs/timestamps of the new message may be regenerated by the builder. **Use a dedicated `eventId` as the stable logical ID**, rather than relying on `MessageHeaders.ID` across every step.
- In real applications, govern schema/content metadata under a controlled contract; `contentType` is metadata only and does not make a message store auto-decode JSON.

If the encoder throws before sending to `durableOrders`, the message is not yet stored by this flow. If the store persisted it and the decoder throws during polling, the outcome depends on poller transactions and store semantics: it may be redelivered, already removed, or routed to an error flow. That is why both failure points must be tested.

### Illustrative XML Durable Queue Configuration

One option is `JdbcChannelMessageStore`. You need compatible JDBC schemas and a configured `DataSource`:

~~~xml
<bean id="orderChannelStore"
      class="org.springframework.integration.jdbc.store.JdbcChannelMessageStore">
    <constructor-arg ref="dataSource"/>
</bean>

<int:channel id="durableOrders">
    <int:queue message-store="orderChannelStore"/>
</int:channel>
~~~

This is an **integration configuration snippet**, not a standalone XML file; you must declare the `int` namespace, Spring context, `dataSource`, run the DDL shipped with your Spring Integration version, and configure the poller/consumer.

Do not confuse `JdbcChannelMessageStore` for pollable channels with `JdbcMessageStore` commonly used for message groups/aggregation. Pick the exact interface and implementation matching the component configured. Using a JDBC store **does not prove payloads are compatible**: verify the outer message's serializer provider and test reading records across new deployments.

## 8. Headers and Correlation Are Data That Must Evolve Too

Versioning the payload alone is not enough. Several headers directly impact runtime:

| Header/Metadata | Role | Issues When Persisted Across Restarts |
| --- | --- | --- |
| `eventId` or custom idempotency key | Identifies the logical event across retries and replays | Must stay stable; do not generate a new ID on every read from store |
| `correlationId` | Groups messages belonging to the same process/group | Changing type from `String` to `UUID` or altering semantics splits groups |
| `sequenceNumber` and `sequenceSize` | Ordering and part count in splitter/aggregator | Missing/wrong types can prevent groups from ever releasing |
| `replyChannel` / `errorChannel` | Reply and error routing paths of a flow | Temporary channel object references become meaningless after restart |
| `contentType` and schema version | Selects the right format decoder | Missing metadata causes wrong decoding or unknown versions |
| `timestamp` / expiration metadata | Timeouts, expiry, retention | Seconds vs. milliseconds, timezones, TTLs, and clock drift must align |

**Especially for `replyChannel` and `errorChannel`:** headers may carry a channel name or a `MessageChannel` reference. A channel object living in the previous application context is not guaranteed to serialize, restore, or forward across restarts. For persistent messages, design resolvable, long-lived reply/error addresses (e.g., durable names/destinations), or use dedicated async callbacks. Never treat a synchronous gateway's temporary reply channel as a durable route.

For an aggregator's `MessageGroupStore`, verify after restart that:

- Messages still hold complete payloads, headers, and sequence metadata.
- The new version's group key/correlation strategy still recognizes older groups.
- The release strategy can finish older groups without hanging due to changed counting/sequence definitions.
- Expiry/timeouts, group cleanup, and locks operate against the same store/region as before.
- In a cluster, multiple instances share state/locking properly; persistence alone does not prevent two consumers from double-processing.

## 9. Compatibility Matrix Before an Upgrade

Before deploying, build a **writer version × reader version × stored data version** matrix. For example:

| Writer | Message in Store | Reader | Expected Outcome |
| --- | --- | --- | --- |
| v1 | schema 1 | v1 | OK (baseline) |
| v1 | schema 1 | v2 | **Must be OK** to upgrade readers first |
| v2 | schema 2 | v2 | OK (current format) |
| v2 | schema 2 | v1 | OK only if old reader supports it; otherwise **forbid arbitrary rollback deploys** |
| v1 + v2 concurrently | schemas 1 and 2 | v2 | **Must be OK** during rolling deployment |
| Record with newer unsupported schema | schema 3 | v2 | Controlled quarantine; do not swallow error and ack |

A safe rollout process is typically **expand → migrate/observe → contract**:

1. Deploy decoders capable of reading both old and new schemas to all active consumers.
2. Confirm new consumers can read **real fixtures captured from the old-version store**, including headers.
3. Only then enable writers to emit the new format.
4. Monitor the share of old-schema records left in the store, decode failures, and backlog.
5. Once old data has been processed/migrated and retention allows, consider removing the legacy decoder.

When an old reader cannot understand a new schema, prepare a **rollback plan**: keep readers compatible, pause new producers, or migrate stored data back to the old format using a verified tool. Never assume rolling back an artifact rolls back stored data.

### Store Schema Changes

Beyond payload schemas, upgrading Spring Integration/DB drivers can also alter **JDBC table schemas**, serialization metadata, key regions, or query behavior. Apply version-matched DDL migrations, take backups, and verify indexes and permissions. Store schema upgrades and domain event schema evolution are **two independent plans**; test them together.

## 10. Retries, Transactions, and Poison Messages

When a payload fails to deserialize, **retrying the exact same bytes** rarely makes the schema valid on its own:

~~~mermaid
flowchart TD
    S[("Persistent Store")] --> R["Poll message"]
    R --> D{"Deserialize succeeded?"}
    D -->|Yes| H["Business handler"]
    D -->|No| T{"Transient? e.g. DB/read timeout"}
    T -->|Yes| B["Bounded retry + backoff"]
    B --> R
    T -->|No| Q["Quarantine raw payload + metadata"]
    Q --> A["Ack/remove per transaction\nafter safe quarantine"]
    H --> O["Commit and continue"]
~~~

Classify errors clearly:

| Error Category | Examples | Handling Approach |
| --- | --- | --- |
| **Transient I/O** | DB/Redis timeout, temporary lock, network blip | Bounded retries with backoff; check transactions/pollers |
| **Compatibility** | Unsupported `schemaVersion`, missing legacy Java class | Do not retry infinitely; alert, upgrade decoder/migrate/quarantine |
| **Corrupt data** | Broken JSON, truncated bytes, checksum failure | Isolate raw record and metadata for investigation |
| **Validation/domain** | Missing required field, wrong amount units | Record error event; never pick arbitrary defaults that corrupt business logic |
| **Downstream failure** | Handler decoded fine but got HTTP 503 | Retry at handler/adapter with idempotency, independent of codec |

If a poller fetches messages from a **store with transactional receive/remove** and a matching transaction manager, rollback can leave the message available for retry. With an in-memory queue or when removal already committed before the failure, you cannot assume the message returns.

### Poison Message Loops

An undecodable message can repeatedly sit at the head of the queue:

~~~text
receive -> decode fails -> rollback -> receive same bytes
       -> decode fails -> rollback -> ...
~~~

Consequences: queue stalls, poller stays busy, connection pool saturates, logs flood, and valid messages behind it are blocked. Mitigations:

- Cap retries and mark compatibility/corruption errors **non-retryable**.
- Define a quarantine/DLQ storing **raw bytes**, exception class, message ID, event ID if readable, store key, and timestamp.
- Ensure saving to quarantine and marking/removing the failing message share proper transaction semantics; when atomicity is required, use the same resource/store or an outbox.
- Track repeated read attempts per message; divert to manual handling or halt the flow cleanly when the outer serializer cannot reconstruct the message.
- After deploying a new decoder, follow an **idempotent replay** procedure without mutating original bytes without audit.

**Hard case:** if the store cannot deserialize even the outer message, a `@ServiceActivator` expecting `Message<byte[]>` never sees the message; retry advice on the handler **cannot fix store-layer failures**. You need store-level error hooks/handlers, backend diagnostics, and controlled tooling to handle raw records directly.

## 11. Reliable Testing: Fixtures, Restarts, Mixed Versions

### 11.1. Long-Lived Fixture Suite

Generate real records using the older producer and keep them as controlled fixtures:

- Valid schema 1, valid schema 2, record missing optional fields.
- Record with extra fields/new enum values, numeric fields near `Long.MAX_VALUE`, and zero/negative amounts.
- Headers `correlationId`, `sequenceNumber`, `sequenceSize`, `contentType`, and application metadata.
- One corrupted payload and one unsupported version to verify quarantine.
- If the store uses Java serialization, fixtures must be **serialized message/provider records**, not merely domain JSON.

Do not test only `new Writer().encode() → new Reader().decode()` in the same source version: that does not prove bytes persisted by an older version read back under the new version.

### 11.2. Test Matrix

| Test | Execution | Pass Signal |
| --- | --- | --- |
| Codec round-trip | Encode v2 then decode v2 | Domain values and `eventId`/`correlationId` match |
| Backward compatibility | Decode v1 bytes with v2 reader | Business defaults mapped accurately per contract |
| Unsupported version | Supply `schemaVersion=99` | Classifiable error; never silently succeeds |
| Real store readback | Write message to **exact production provider**, read back | Payloads/headers intact |
| Restart | Write message, stop app, start different version on same store | Consumer reads and processes cleanly |
| Rolling deployment | Two reader versions running concurrently on queue | Neither version misreads; no unintended duplicates |
| Rollback deploy | New writer already wrote new schema; run old reader | Meets rollback plan; if unsupported, detected early |
| Crash between poll and commit | Deliberately kill instance in test scenario | No out-of-contract message loss; redelivery/dedup works |
| Aggregator after restart | Save incomplete group, restart, send remaining part | Correlation/release does not stall |
| Poison message | Feed corrupt JSON/bad outer bytes | Quarantined/alerted; queue keeps processing |

For JDBC, verify DDL/indexes from the exact version and a transaction manager sharing the `DataSource`. For Redis/MongoDB, test actual serializers, TTLs, region/key prefixes, locking/distribution, and retention. For multi-instance setups, test concurrent consumers rather than single-threaded runs.

### 11.3. Using Legacy Data Snapshots to Test a New Release

Upgrade verification procedure:

~~~text
1. Run app v1 + real persistent store.
2. Send messages while pausing consumer/poller.
3. Snapshot database/store (preserving raw bytes, headers, metadata).
4. Stop app v1.
5. Start app v2 connected to the snapshot.
6. Start consumer; verify decode + side effects + correlation.
7. Check exceptions, DLQ, queue depth, and remaining groups.
8. Test rollback if the system requires reverting to v1.
~~~

Ensure automated tests never accidentally wipe databases or purge production queues; use isolated environments and controlled data.

## 12. Security, Privacy, and Governance of Stored Data

Persistent payloads outlive request/worker threads, so security rules must evolve alongside schemas:

- Never put unnecessary tokens, passwords, sessions, or personal data into payloads/headers. Avoid persisting `MessageChannel`s or framework objects holding state not meant for serialization.
- When using Java native deserialization, **never deserialize untrusted bytes**; control sources, enforce class filtering/allow-lists, and patch libraries. JSON/Avro also require input validation, depth/size limits, and protection against malicious payloads.
- With encryption, store necessary metadata like `encoding`/`keyId` in a structured envelope; keep secret keys in KMS/secret managers. During key rotation, ensure old messages stay readable through retention or migrate cleanly.
- If compressing data, record the algorithm and enforce size limits **after decompression** to guard against payload expansion bombs.
- Avoid logging stack traces containing raw payloads. Log only size, schema version, event type, intentional hashes/checksums, channel, endpoint, and controlled IDs.
- Define retention, TTL, purge policies, and store access controls; message groups/aggregators may hold data longer than queues while awaiting release.
- Ensure backups/restores also preserve **serializer metadata and schema registries**; restoring raw bytes without readers/keys/registries will not restore operation.

## 13. Runtime Performance and Operations

Serialization/deserialization adds CPU, memory allocation, and I/O, especially with large object graphs or heavy JSON/Avro payloads.

| Symptom | Likely Cause | What to Measure |
| --- | --- | --- |
| `send()` to queue unusually slow | Synchronous encode or store write; DB/Redis bottleneck | Encode duration, store write latency, connection pool |
| Poller drains few messages despite deep backlog | Slow deserialization, error/retry loops, lock-holding transactions | Poll latency, decode latency, queue depth, error rate |
| GC spikes after deploy | Oversized payloads, `byte[]` copies, mappers allocating heavily | Allocation rate, heap, GC pauses, payload size distribution |
| Queue stuck on one record | Unknown version/poison message, repeated rollbacks | Offending store key, retry count, DLQ rate |
| Aggregator holds groups forever | Missing `correlationId`/sequence or reader changed semantics | Group age, group size, expiry, release criteria |
| Some instances fail while others succeed | Mixed reader versions or mismatched serializer config | App build ID, schema versions, serializer version |
| Unreadable data after switching stores | Provider-specific serialization and layout differences | Actual stored bytes, metadata, migration strategy |

Do not use `eventId`/`orderId` as metric labels due to high cardinality. Use stable tags: `storeType`, `channel`, `eventType`, `schemaVersion`, `status`, and exception family. Put event IDs into controlled traces/logs for per-message lookup.

### Key Metrics

- `store.write.count`, `store.write.error`, `store.read.count`, `store.read.error`.
- `payload.encode.duration`, `payload.decode.duration`, `payload.bytes` by percentile.
- Pending message count, oldest-message age, group count, and oldest-group age.
- Counts of `unsupported_schema_version`, `corrupt_payload`, and quarantine successes/failures.
- Retry/redelivery counts per logical event; duplicate count caught by deduplication.
- Distribution of active schema versions remaining before retiring legacy readers.

Measure consistently from producer message creation through consumer commit; a durable `MessageStore` does not by itself guarantee exactly-once processing or SLAs.

## 14. Common Pitfalls and Fixes

| Pitfall | Why It Is Wrong | Fix |
| --- | --- | --- |
| "We use JDBC Message Store so any object survives deploys" | JDBC preserves bytes/rows; new classes/serializers may fail to read them | Versioned contracts + real-store upgrade tests |
| "Payload is JSON, so we're safe" | Outer `Message<?>` and headers are still managed by store serializers | Verify envelope, headers, and backend mappers |
| "Java `Serializable` lets us rename packages freely" | Native serialized form depends on class metadata | Stable wire contracts and tested migrations |
| "`contentType` auto-decodes after `getMessage()`" | Header is metadata; an actual converter/decoder must run | Place codecs at explicit boundaries |
| "`correlationId` from `MessageHeaders.ID` lasts forever" | Message IDs can change whenever new messages are built | Create stable logical `eventId`/`correlationId` |
| "DB rollback automatically returns queued messages" | Requires transactional source/store receive and matching ack policy | Verify queue/provider/transaction manager |
| "Adding an optional field is always forward-compatible" | Old readers may reject unknown fields or schema versions | Test both directions and rolling deploys |
| "If deserialization fails, keep retrying until it works" | Bytes/schemas don't change; poison messages loop forever | Quarantine raw bytes and stop infinite retries |
| "Having a persistent message store gives us exactly-once" | Redeliveries and crashes mid-side-effect still cause duplicates | Idempotency/inbox/outbox, transactions, and clear recovery |
| "Upgrading the framework auto-migrates the store" | Store schemas and serialized formats can change | Version pinning, backups, compatibility/migration plans |

## 15. Hands-On Practice and Verification Questions

1. **Codec:** run `StoredOrderCodec.main()`. Change `schemaVersion` in v1 JSON to 99; confirm the decoder rejects it clearly. Test `amountMinorUnits` as a string, negative number, and out-of-`long` range.
2. **Preserve business semantics:** revise the v1 contract so amounts can carry multiple currencies; explain why defaulting to `"VND"` becomes invalid and propose proper migration/lookup.
3. **Channel test:** connect Section 7's encoder/decoder through a `QueueChannel`; log `traceId`, `eventId`, and `correlationId` before and after.
4. **Real persistence test:** swap the in-memory queue for `JdbcChannelMessageStore` with compatible DDL and configuration; send multiple messages, stop the app, and restart the consumer. Verify no messages or headers are lost.
5. **Legacy version after deploy:** have app v1 generate raw rows/serialized messages, then have app v2 read them; do not have v2 hand-craft a v1 fixture and claim outer serializers are compatible.
6. **Poison message:** inject an undecodable record in a test environment; determine whether failure occurs in the store serializer or domain decoder; configure quarantine/DLQ to prevent infinite re-polling.
7. **Aggregator:** send part of a sequence, save the group, restart, and send the remaining part; verify `correlationId`, `sequenceSize`, release strategy, and expiry.
8. **Rolling upgrade:** run two consumer versions concurrently; send schemas 1/2, then test rolling back the reader to verify the compatibility plan.
9. **Safety:** test oversized payloads and unusually deep JSON nesting; verify pre-deserialization limits and safe logging rules.
10. **Performance:** benchmark encode/decode, bytes/record, enqueue/dequeue latency, and GC as payload size grows; identify whether the codec or backend is the bottleneck.

### Deployment Readiness Checklist

- Versioned payload contract and schema evolution rules/registry in place.
- Tested both old data read by new readers and the reverse if rollback is needed.
- Verified actual serializers for **payloads, outer Messages, and headers** on the exact provider/version.
- Stable logical `eventId`/`correlationId` across restarts/retries; sequence metadata preserved.
- Transactions/acks/recovery aligned for durable queues and message groups.
- Raw-byte quarantine for unsupported/corrupt payloads; no infinite retries.
- Metrics broken down by schema version, deserialization errors, queue backlog, and group age.
- Backups, retention, migration plans, and tested restores prior to store/framework upgrades.

## 16. Official Reference Sources

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageStore` and `MessageGroupStore` concepts in flows.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `QueueChannel`, pollable channels, and channel message stores.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC integration and database/schema requirements.
- [Spring Integration API — MessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageStore.html) and [MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html): message/group storage contracts.
- [Spring Integration API — JdbcChannelMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcChannelMessageStore.html): persistent channel storage.
- [Spring Framework — Message / MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): message abstraction and headers.
