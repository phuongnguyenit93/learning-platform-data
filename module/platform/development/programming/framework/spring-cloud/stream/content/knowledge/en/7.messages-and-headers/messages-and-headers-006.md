# Mapping Headers Between Spring Messaging and Broker Protocols

In Spring Cloud Stream, a message contains more than just a payload. It also has headers holding metadata such as event type, correlation ID, content type, partition key, or tracing information. When a message passes through a binding, the binder must convert this metadata into a structure supported by the broker; when receiving a message, the binder performs the reverse mapping so the application can read headers via Spring Messaging.

The mapping mechanism is not identical across Kafka, RabbitMQ, and Pulsar. Each protocol has its own metadata model: Kafka uses binary key/value headers, RabbitMQ uses AMQP properties and field tables, and Pulsar has message properties alongside dedicated metadata fields. Understanding these differences helps design portable headers, avoid data loss when switching binders, and accurately distinguish application message data from broker-generated metadata.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish payloads, Spring Message headers, and broker-managed metadata.
- Create and read headers using Spring Messaging `Message<T>` and `MessageBuilder`.
- Explain how binders map headers between Spring Messaging and Kafka, RabbitMQ, or Pulsar.
- Distinguish headers from Kafka keys, RabbitMQ routing keys, and Pulsar message keys.
- Select which headers to forward across bindings and control metadata copying.
- Recognize data type limits, size constraints, and conversion rules for each protocol.
- Test headers at the function, binding, and real broker levels.

## 1. Payload, Message, and Headers

Spring Messaging represents a message with the `Message<T>` interface. A message has two parts:

- **Payload**: the primary content the application wants to transmit, such as an `OrderCreated` object.
- **Headers**: metadata describing the message or supporting routing, correlation, formatting, and processing.

Payload example:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}
~~~

Creating a message with payload and metadata:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-2026-001")
        .setHeader("tenantId", "tenant-a")
        .setHeader("schemaVersion", 2)
        .build();
~~~

In this example:

- The payload is the order data.
- `eventType` specifies the event kind.
- `correlationId` links the message to a workflow or originating request.
- `tenantId` identifies the tenant in a multi-tenant system.
- `schemaVersion` is metadata describing the contract version in this example.

These headers are application-defined metadata. They do not automatically become part of a JSON payload. When the binder sends the message, the binder or message converter processes the payload and maps headers according to the broker's capabilities.

### MessageHeaders and Framework Headers

`MessageHeaders` is an immutable map-like structure holding Spring Message headers. Some common headers include:

| Header | Purpose |
|---|---|
| `id` | Message identifier within Spring Messaging |
| `timestamp` | Message creation timestamp according to Spring Messaging |
| `contentType` | Hints at the payload format for conversion |
| `correlationId` | Links messages belonging to the same processing flow |
| `replyChannel` | Reply channel in supported internal messaging patterns |
| `errorChannel` | Error handling channel in the Spring Integration ecosystem |

Not every Spring header is sent intact over the broker. Headers such as `id`, `timestamp`, `replyChannel`, or `errorChannel` have in-process meaning; they may be regenerated, stripped, or unrepresentable in the target protocol. The `contentType` header may be used during conversion and mapped according to the binder's rules.

Therefore, treat received message headers as metadata interpreted by the binder, not a byte-for-byte copy of the entire `MessageHeaders` from the sender side.

## 2. Creating, Reading, and Transforming Headers

### Creating Messages with MessageBuilder

`MessageBuilder` creates a new message from a payload and the required headers:

~~~java
Message<OrderCreated> outbound =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", correlationId)
        .setHeader("sourceService", "order-service")
        .build();
~~~

`MessageBuilder.fromMessage(existing)` can be used when creating a new message based on an existing one. However, copying all headers can carry internal metadata, sensitive data, or values incompatible with the target broker. In cross-system integration flows, explicitly choose which headers are allowed to be forwarded.

### Reading Headers in a Consumer

A consumer can accept a plain payload if it only needs business data:

~~~java
@Bean
Consumer<OrderCreated> inventory() {
    return event -> updateInventory(event);
}
~~~

When metadata is needed, declare the Consumer to accept `Message<OrderCreated>`:

~~~java
@Bean
Consumer<Message<OrderCreated>> inventory() {
    return message -> {
        OrderCreated event = message.getPayload();
        String correlationId =
            message.getHeaders().get("correlationId", String.class);

        updateInventory(event, correlationId);
    };
}
~~~

Use `getPayload()` to read business data and `getHeaders()` to access metadata. When reading a typed header, request the expected type or verify the type before casting; the received value may have been converted by the binder.

### Forwarding Only Needed Headers

A Function often receives a message, transforms the payload, and emits a new message. Example:

~~~java
@Bean
Function<Message<OrderCreated>, Message<EnrichedOrder>> enrichOrder() {
    return input -> {
        OrderCreated event = input.getPayload();
        EnrichedOrder result = enrich(event);

        MessageBuilder<EnrichedOrder> output =
            MessageBuilder.withPayload(result)
                .setHeader("eventType", "EnrichedOrder");

        Object correlationId =
            input.getHeaders().get("correlationId");

        if (correlationId != null) {
            output.setHeader("correlationId", correlationId);
        }

        Object tenantId = input.getHeaders().get("tenantId");
        if (tenantId != null) {
            output.setHeader("tenantId", tenantId);
        }

        return output.build();
    };
}
~~~

This example forwards only `correlationId` and `tenantId`, while updating `eventType`. This creates an explicit header contract on the output. Avoid blindly copying all input headers because some headers only have meaning in an upstream hop or contain data that must not be exposed.

## 3. Mapping Process Between Spring Messaging and the Broker

On the sending side, the high-level flow is as follows:

1. A function or service creates a `Message<T>` containing payload and headers.
2. Spring Cloud Stream selects the output binding and binder.
3. The message converter transforms the payload into a suitable transport representation.
4. The header mapper or binder integration mechanism selects transferable headers and converts values to protocol data types.
5. The broker stores or routes the message using its native metadata.

On the receiving side, the process runs in reverse:

1. The broker delivers the message with native metadata to the binder.
2. The binder reads the metadata and maps supported fields into Spring Message headers.
3. The message converter decodes the payload according to the content type and function input type.
4. The consumer receives the payload along with the mapped headers.

~~~mermaid
flowchart LR
    A["Function / Service"] --> B["Spring Message<br/>payload + headers"]
    B --> C["Output binding"]
    C --> D["Binder + header mapper"]
    D --> E["Broker native message<br/>payload + metadata"]
    E --> F["Binder + header mapper"]
    F --> G["Input binding"]
    G --> H["Spring Message"]
    H --> I["Consumer / Function"]
~~~

Not every header passes through every step. Some metadata maps to native broker fields; some custom headers are stored as extended properties; some internal headers are dropped. If metadata must survive across multiple brokers, define an application header set with simple types, stable names, and tests on both ends.

## 4. Mapping Headers with Kafka

A Kafka record has a payload value, record key, timestamp, partition, and list of headers. Kafka headers are key/value pairs where the value is a byte array. A single record can contain multiple headers with the same name; thus, Kafka's header model can represent multiple values for one key.

The Spring Cloud Stream Kafka binder integrates with Spring Kafka's header mapping mechanisms to convert headers between Spring Messages and Kafka records. Headers with simple types such as strings or byte arrays are generally straightforward to map. Other object types may require serialization/deserialization mechanisms or type metadata used by the mapper. Exact mapping behavior depends on the Spring Kafka version, binder, and header mapper configuration.

### Headers Are Not Record Keys

Distinguish between the following fields:

| Kafka component | Role |
|---|---|
| Record key | Commonly used by the partitioner to choose a partition; may participate in compaction |
| Record headers | Key/byte-value metadata attached to a record |
| Record timestamp | Record timestamp per producer/broker timestamp policy |
| Partition and offset | Record position managed by Kafka |
| Consumer group | Group of consumers sharing partitions and tracking offset progress |

If you want all events for the same order to land in the same partition, configure the key using `orderId`. Putting `orderId` in a custom header does not automatically make Kafka use it as the record key.

Example creating a message with a correlation header:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("eventType", "OrderCreated")
        .build();
~~~

If you need to set a Kafka key, use producer properties or the binder/API support documented for that version to pass the key properly. Do not assume a custom `key` or `partitionKey` header automatically replaces the record key.

### Header Mappers and Data Types

Kafka only stores byte arrays in headers. When sending a Java value other than a byte array, the header mapper must convert that value into bytes. Upon receipt, the mapper may restore the type based on its rules and metadata. If the producer and consumer use different mappers, headers may arrive as strings, byte arrays, or fail to restore their original type.

For cross-service contracts, prefer simple values such as:

- UTF-8 strings for `correlationId`, `eventType`, and `tenantId`.
- Digit strings or agreed integer representations for versions.
- Byte arrays when the application genuinely requires binary metadata.

Do not pass arbitrary Java objects and rely on the consumer having the exact same class or deserialization mechanism. Never enable deserialization of untrusted objects just to preserve header types.

## 5. Mapping Headers with RabbitMQ

RabbitMQ uses AMQP message properties and a headers table. Several common metadata items are represented as standard AMQP properties, for example:

- `contentType` and `contentEncoding`: describe payload format and encoding.
- `correlationId`: links requests and responses or related messages.
- `messageId`: application-level message identifier.
- `replyTo`: address or routing destination used for replies.
- `type`: application-defined message type.
- `timestamp`: message timestamp per AMQP metadata.
- `priority`, `expiration`, `deliveryMode`: message control or transport attributes.

Custom headers can be stored in the AMQP headers table. RabbitMQ and AMQP clients only support value types allowed by the protocol's data type table. Not every Java object can be converted directly into a valid field table entry.

### Routing Keys Are Not Custom Headers

With direct or topic exchanges, the routing key determines which queues receive a message based on bindings. Custom headers such as `tenantId` or `eventType` are merely metadata, unless the application uses a headers exchange and configures bindings based on those headers.

Example of a message with metadata:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

The message can be sent to the exchange and routing key configured by the binding/binder. Custom headers do not alter the routing key on their own. If you need routing by tenant or event type, configure the appropriate exchange, routing key, and bindings; with a headers exchange, ensure header names and types match the binding criteria.

### Inspecting on RabbitMQ

The RabbitMQ Management UI or administration tools can display exchanges, queues, bindings, message counts, and message metadata when messages are inspected. When checking headers, verify the name, type, and value. Some values may be represented using AMQP field types rather than the original Java type.

If a header does not appear at the consumer, check:

1. Did the producer actually set the header before sending?
2. Does the header mapper/binder allow mapping that header name?
3. Is the value type supported by the AMQP headers table?
4. Is any binding configuration stripping or overwriting the header?
5. Is the consumer reading from the expected queue and corresponding message?

## 6. Mapping Metadata with Apache Pulsar

A Pulsar message has a payload and native metadata. Alongside broker-managed fields, Pulsar supports message properties as string key/value pairs. Messages also have dedicated fields such as key, ordering key, event time, sequence ID, schema version, and message ID.

Concepts to distinguish:

| Field or related structure | Role |
|---|---|
| Properties | String key/value map attached by the application |
| Key | Message key, which may participate in routing or key-based processing |
| Ordering key | Key used to preserve ordering as supported by the broker |
| Event time | Event occurrence timestamp supplied by the producer |
| Sequence ID | Sequence number used by the producer |
| Message ID | Broker-assigned identifier for message position |
| Publish time | Timestamp when the broker recorded the message |
| Subscription | Structure tracking consumption progress of a subscriber group on a topic; not a per-message property |

The Spring Cloud Stream Pulsar binder maps supported headers and attributes to Pulsar native metadata. Exact rules depend on the binder version and configuration. Do not assume every Spring Message header becomes a Pulsar property, or that custom headers retain their Java types.

Example of string-based metadata:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

When mapped to Pulsar properties, values need a clean string representation. If a header needs to control partitioning or ordering, use the binder-supported key/ordering key attributes rather than merely setting a similarly named custom property.

### Inspecting Pulsar Metadata

Use appropriate admin tools or clients to view topics, subscriptions, and statistics. When verifying properties, use a dedicated test consumer to read messages and print metadata. Avoid using a production application's subscription for testing, as reading messages can advance cursors or alter consumption state.

## 7. Standard Headers and Custom Headers

Headers should be divided into two groups by purpose:

**Standard or transport headers** carry broad messaging meaning, such as content type, correlation ID, message ID, or reply destination. Binders may map several of these headers to native broker fields.

**Application custom headers** describe business or processing context, such as `eventType`, `tenantId`, `sourceService`, or `traceparent`. These headers must be clearly defined and agreed upon between producers and consumers.

Avoid naming a custom header the same as a broker-reserved field if its semantics differ. For example, a custom header named `timestamp` can be confused with the transport timestamp; use a clearer name like `businessOccurredAt` when representing business occurrence time.

### Naming Conventions

A simple convention reduces errors when switching brokers:

- Use stable, readable ASCII names with consistent casing.
- Pick a single naming style, such as `correlationId` or `correlation-id`, and apply it consistently.
- Define the data type and representation for each header.
- Document required headers, optional headers, and single-hop headers.
- Avoid embedding large payloads in headers.
- Do not use headers to store core business data requiring long-term guarantees.

Header names may be case-sensitive depending on the map and protocol. Some brokers or clients may normalize representations. Therefore, avoid creating two headers that differ only in letter case.

## 8. HeaderMode and Binder Capabilities

Spring Cloud Stream provides mechanisms to control how headers are transmitted across a binding. Depending on the binder, you may encounter modes such as:

| Mode | General meaning |
|---|---|
| `headers` | Uses the broker's native header mechanism when supported by the binder |
| `embeddedHeaders` | Packages header metadata alongside the payload in an embedded header format |
| `none` | Does not transmit headers via Spring Cloud Stream's header mechanism |

Not all binders support these modes in the same way or share the same defaults. Some binders have native header support; others may require embedded headers. Check the documentation for the exact version of your binder and binding before setting `headerMode`.

If using embedded headers, consumers must understand the same packaging format. A native broker consumer or non-Spring Cloud Stream application may see the packaged metadata as part of the payload if it does not decode according to the expected rules.

If choosing `none`, do not expect custom headers to be preserved on the receiving side. Keep essential information in the payload or use another metadata channel with an explicit contract.

## 9. Filtering Headers and Protecting Data

Headers sent through a broker can reach many applications and storage environments. Do not treat headers as private or inherently trustworthy data.

Key principles:

- Forward only headers needed by the next hop.
- Never put access tokens, passwords, session cookies, or authentication credentials into custom headers.
- Do not trust `tenantId`, `userId`, or `role` values from external messages without verifying authorization.
- Never deserialize arbitrary Java objects from untrusted headers.
- Limit the size and count of headers to avoid increasing storage, network, and logging overhead.
- Avoid dumping all headers into logs if they might contain sensitive data.

Correlation ID and trace context are valuable for observing processing flows, provided teams agree on policies for generation, validation, and forwarding. Never use trace headers as proof of user authentication or business authorization.

### Header Allowlist

You can build an application-layer allowlist to decide which headers are forwarded:

~~~java
private static final Set<String> FORWARDED_HEADERS =
    Set.of("correlationId", "tenantId", "traceparent");

MessageBuilder<EnrichedOrder> copyAllowedHeaders(
        Message<?> input,
        EnrichedOrder payload) {

    MessageBuilder<EnrichedOrder> output =
        MessageBuilder.withPayload(payload);

    for (String name : FORWARDED_HEADERS) {
        Object value = input.getHeaders().get(name);
        if (value != null) {
            output.setHeader(name, value);
        }
    }

    return output;
}
~~~

An allowlist helps control metadata crossing service boundaries. When adding a new header, update the contract and tests to avoid accidentally leaking internal data.

## 10. Testing Header Mapping

Headers should be verified at three levels.

### Unit Tests for Message Logic

Verify that functions create and forward the right headers:

Assume `enrich` is the function under test, receiving a Spring Message and returning the resulting message after applying the header allowlist.

~~~java
@Test
void preservesCorrelationId() {
    OrderCreated event = new OrderCreated(
        "evt-1", "order-1", new BigDecimal("100.00")
    );

    Message<OrderCreated> input =
        MessageBuilder.withPayload(event)
            .setHeader("correlationId", "corr-1")
            .setHeader("tenantId", "tenant-a")
            .build();

    Message<EnrichedOrder> output = enrich(input);

    assertEquals(
        "corr-1",
        output.getHeaders().get("correlationId")
    );
    assertEquals(
        "tenant-a",
        output.getHeaders().get("tenantId")
    );
}
~~~

Unit tests prove that application logic preserves or alters headers as designed. They do not prove that the binder transmits headers across a broker.

### Binding Tests

Use the test binder to send messages into a binding, receive messages on an output channel or test destination, and inspect payload and headers. The test binder is well-suited for verifying integration at the Spring Cloud Stream level without a real broker.

### Broker Integration Tests

With a real Kafka, RabbitMQ, or Pulsar instance, send messages through the binder and read them back with a test consumer. Check:

- Do custom headers appear on the receiving side?
- Are header names altered or normalized?
- Are value types preserved or converted to strings/bytes?
- Are duplicate-named headers preserved, merged, or reduced to a single value?
- Are native metadata fields such as key, routing key, event time, or message ID set properly?
- Which internal headers are stripped as designed?

When running round-trip tests, use a dedicated test group/subscription to avoid altering the application's consumption progress. Record the binder and broker versions because mapping behavior can vary across releases.

## 11. Common Header Mapping Issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Header present at producer but lost at consumer | Binder does not map that header, header is filtered, or header mode is unsuitable | Inspect mapper, binding config, and native header support |
| Header arrives as a byte array | Protocol stores values as bytes or mapper did not restore type | Check serializer/deserializer and type conventions |
| Header object fails to deserialize | Producer and consumer disagree on type or type metadata | Use scalar/string types or explicit schemas |
| Header gets overwritten | Same header name set at multiple layers or broker maps it to a standard field | Identify header source and precedence rules |
| Correlation ID lost between functions | Function creates a new message without forwarding required headers | Use an allowlist to copy headers |
| Kafka partition ignores `partitionKey` header | Record key is not configured; header does not automatically determine partition | Set the Kafka key via the proper producer/binder mechanism |
| RabbitMQ message routed to wrong queue | Routing key or exchange binding is incorrect | Inspect exchange, routing key, and queue bindings |
| Pulsar does not preserve header types | Pulsar properties are string key/value pairs | Standardize value serialization and parsing |
| Non-Spring consumer cannot understand metadata | Embedded headers or mapper-specific format is in use | Align protocol conventions and test with an external client |
| Message grows unexpectedly large | Too many headers or headers carrying large data | Reduce header count and size, keeping only essential metadata |

When a header is lost, pinpoint which layer dropped it: before sending, during mapping, at the broker, or when the binder builds the Spring Message on the receiving side. Checking payload, native metadata, and Spring headers in sequence narrows down the issue more accurately.

## 12. Hands-On Walkthrough: Propagating Correlation ID Across Three Brokers

Create an order event processing flow with a publisher, function, and consumer:

1. Publisher creates `Message<OrderCreated>` with `eventType`, `correlationId`, and `tenantId`.
2. Function receives `Message<OrderCreated>` and transforms the payload into `EnrichedOrder`.
3. Function builds a new output message and forwards only headers in the allowlist.
4. Consumer receives `Message<EnrichedOrder>`, reads `correlationId`, and logs it alongside `orderId`.
5. Run unit tests to verify payload and headers at each step.
6. Run binding tests to verify the message traverses the bindings.
7. Run integration tests with Kafka, then inspect record headers and record key separately.
8. Repeat with RabbitMQ, inspecting AMQP properties, headers table, and routing key.
9. Repeat with Pulsar, inspecting message properties, key, and event time.
10. Compare which headers remain intact, which map to native metadata, and which are unsupported.
11. Try sending a header with an unsupported type or excessive size in a test environment to observe errors and system behavior.
12. Finalize the shared header contract table for producers and consumers.

Sample contract table:

| Header name | Representation type | Required | Purpose |
|---|---|---|---|
| `eventType` | String | Yes | Event classification |
| `correlationId` | String | Yes in traceable flows | Links processing steps |
| `tenantId` | String | Per tenant model | Identifies tenant context |
| `traceparent` | String | Per tracing policy | Propagates trace context |
| `sourceService` | String | Per contract | Identifies emitting service |

Upon completion, you should be able to explain why a Spring Message header does not necessarily become an identical native field on every broker, and know how to design an application header set that travels reliably across binders.

## Conclusion

Spring Messaging represents messages with payloads and headers, while Kafka, RabbitMQ, and Pulsar have distinct metadata models. Binders and header mappers handle translating between those worlds; consequently, a Spring header is not guaranteed to appear identically across every protocol.

Separate payloads from metadata, distinguish headers from broker keys and routing metadata, standardize header names and types, forward only necessary data, and run round-trip tests on a real broker. Such design ensures correlation, tracing, and business context travel reliably across functions and bindings without over-coupling to a single broker.
