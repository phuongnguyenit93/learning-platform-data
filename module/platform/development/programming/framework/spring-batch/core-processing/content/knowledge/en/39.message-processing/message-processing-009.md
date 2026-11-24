# Payload Serialization

In a Spring Batch system integrated with messaging, an item typically starts as an in-memory Java object. When sending that item over JMS, Kafka, RabbitMQ, or a Spring Integration channel across another process, the object must be converted into a data format the receiver can read. Converting an object into bytes or text is called **serialization**; reconstructing the object from received data is **deserialization**.

Payload serialization is part of the contract between producer and consumer. The producer decides what data goes into the message, how it is encoded, and its schema/version; the consumer must interpret that format accurately to rebuild a meaningful payload. If the two sides disagree, a message may be delivered successfully at the transport layer while the batch worker still fails to process the item.

In Spring Batch, serialization is especially important when jobs exchange data via message channels, remote chunking, remote partitioning, or when a step reads/writes messages from a broker. Distinguish payloads from message headers, serialization from `JobRepository` checkpoints, and data conversion errors from business errors. A solid design keeps payloads compact, uses explicit schemas, stays version-compatible, deserializes safely, and remains reprocessable when messages are delivered multiple times.

## 1. What Is a Payload?

In Spring Messaging, a message typically has two parts:

- **Payload:** the core content the producer wants to transmit, such as an `Order`, a `Payment`, or a list of items.
- **Headers:** metadata describing the message, such as message ID, correlation ID, timestamp, content type, partition key, or routing information.

A message can be pictured like this:

~~~text
Message
  ├── headers
  │     ├── messageId
  │     ├── correlationId
  │     ├── contentType
  │     └── partitionKey
  └── payload
        └── OrderCreated
~~~

The payload represents business data. Headers help systems transport, route, observe, and correlate messages. Do not put all metadata inside the payload when the transport already provides appropriate headers; conversely, do not put critical business fields into headers because many brokers restrict header sizes or types.

Example JSON payload:

~~~json
{
  "orderId": 1001,
  "customerId": "C001",
  "amount": 250.00,
  "currency": "VND"
}
~~~

Headers can carry a job or message correlation ID, but do not replace the `orderId` business key inside the payload. Consumers need the business key to deduplicate and reconcile even if a message is resent with a different message ID.

## 2. Serialization and Deserialization

Serialization turns an object into a transmittable or storable representation:

~~~text
Java object -> serializer -> byte[] / String
~~~

Deserialization performs the reverse:

~~~text
byte[] / String -> deserializer -> Java object
~~~

Example Java object:

~~~java
public class OrderPayload {
    private Long orderId;
    private String customerId;
    private BigDecimal amount;
    private String currency;

    public OrderPayload() {
    }

    // getters and setters
}
~~~

The corresponding JSON representation can be parsed into an `OrderPayload` at the consumer. Both sides must agree on field names, numeric types, date/time formats, enums, null handling, and unknown-field rules.

Serialization does not mean encryption. JSON or Avro payloads are serialized yet still readable unless encrypted. If a payload contains sensitive data, use TLS in transit and potentially encryption at rest or field-level encryption per your threat model.

## 3. Where Does Serialization Fit in Message Processing?

A message-driven pipeline can look like this:

~~~mermaid
flowchart LR
    A[Spring Batch item] --> B[Message producer]
    B --> C[Payload converter / serializer]
    C --> D[Broker or channel]
    D --> E[Deserializer / message converter]
    E --> F[Message consumer]
    F --> G[Batch worker or next step]
~~~

The producer constructs a payload from an item or chunk. The serializer converts the payload into its wire representation. The broker transports bytes along with headers. The consumer reads the message, decodes the payload into an object, and passes it into a processor/writer or another job/step.

Errors can arise at each boundary:

- The producer constructs an object violating the schema.
- The serializer does not support a data type.
- The broker rejects the message due to size or permissions.
- The consumer uses a different schema/version.
- The deserializer cannot reconstruct the type.
- The payload is syntactically valid but violates a business rule.

Record clearly at which layer an error happened. A JSON parse error is not the same as an `Order` validation error; nor is a broker timeout the same as a schema error.

## 4. Messages and Payloads in Spring Messaging

Spring Messaging defines the `Message` abstraction with a payload and headers. A producer can construct a message using `MessageBuilder`:

~~~java
OrderPayload payload = new OrderPayload();
payload.setOrderId(1001L);
payload.setCustomerId("C001");
payload.setAmount(new BigDecimal("250.00"));
payload.setCurrency("VND");

Message<OrderPayload> message = MessageBuilder
        .withPayload(payload)
        .setHeader("correlationId", "orders-export-2026-11-15")
        .setHeader("contentType", "application/json")
        .build();
~~~

An in-memory `Message` object still holds a Java object as its payload. Constructing a `Message` does not automatically mean the object has been serialized to bytes. The transport converter or adapter performs the conversion when the message crosses the corresponding boundary.

Do not confuse a Spring `Message` with the message representation stored by a broker. JMS `Message`, Kafka records, and Spring `Message` have different APIs. Spring Integration converts among them via adapters and converters.

## 5. MessageConverter in Spring Messaging

Spring Messaging provides the `MessageConverter` abstraction to convert between objects and `Message`:

~~~java
public interface MessageConverter {

    Message<?> toMessage(Object payload, MessageHeaders headers);

    Object fromMessage(Message<?> message, Class<?> targetClass);
}
~~~

Converters can build a message from an object or extract an object from a message. Spring Integration uses message conversion at channel/endpoint integration points; the actual converter depends on the transport and configuration.

Not every messaging system uses this exact interface. For example:

- Spring Messaging `MessageConverter` uses an API based on `MessageHeaders`.
- Spring JMS `MessageConverter` works with `jakarta.jms.Session` and `jakarta.jms.Message`.
- Kafka clients use `Serializer<T>` and `Deserializer<T>` to convert values to bytes and back.

Identical interface names do not mean you can pass the same converter to every transport. Choose the exact API matching the adapter/broker in use.

## 6. Choosing a Payload Format

Serialization format affects compatibility, size, speed, debuggability, and how schemas are versioned.

| Format | Strengths | Limitations | Typically Suitable For |
|---|---|---|---|
| JSON | Human-readable, ubiquitous, multi-language support | Payloads are usually larger than binary; requires schema discipline | APIs, events, general integrations |
| Avro | Compact binary, structured schema evolution rules | Requires schemas and compatible tooling | Event streams, data pipelines |
| Protocol Buffers | Small binary, typed contract, code generation | Requires managing `.proto` files and compatibility | Service-to-service, high throughput |
| XML | Mature schemas/XSD and tooling | Verbose, parsing is often heavier than JSON | Enterprise XML-based systems |
| Java native serialization | Quick for prototyping Java object graphs | Class/version coupled, brittle compatibility, security risks | Avoid across untrusted boundaries |

No single format is best for every case. Choose based on consumer contracts, throughput requirements, versioning capabilities, and the ecosystem supported by participating systems.

## 7. JSON Serialization with Jackson

Jackson is commonly used to serialize DTOs to JSON. Define dedicated payload DTOs rather than directly serializing persistence entities or large object graphs.

Example:

~~~java
public record OrderEvent(
        String eventId,
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        Instant occurredAt) {
}
~~~

Serialize:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

String json = objectMapper.writeValueAsString(
        new OrderEvent(
                "evt-1001",
                1001L,
                "C001",
                new BigDecimal("250.00"),
                "VND",
                Instant.parse("2026-11-15T10:30:00Z")));
~~~

Deserialize:

~~~java
OrderEvent event = objectMapper.readValue(json, OrderEvent.class);
~~~

For records or constructor-based DTOs, configure the appropriate Jackson modules/version. For POJOs, follow your application's accessor or annotation conventions. Never use an `ObjectMapper` in tests with different settings from production, as null/date/enum/unknown-property behavior can diverge.

## 8. JSON Dates, Times, and Decimals

Dates and times require formats with explicit timezones. For `Instant`, ISO-8601 UTC is a common choice:

~~~json
{
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Never serialize `LocalDateTime` assuming the consumer knows the timezone. `LocalDateTime` carries no offset/timezone; if an event represents an absolute instant in time, use `Instant` or `OffsetDateTime` and agree on rules.

For monetary amounts, use `BigDecimal` in Java and JSON numbers per contract:

~~~json
{
  "amount": 250.00,
  "currency": "VND"
}
~~~

Do not convert `BigDecimal` to `double` just for simpler serialization. If consumers expect fixed scale, define the serializer/format clearly and test round-trips. JSON numbers do not guarantee every consumer language preserves display scale, so business comparisons should usually rely on numeric value and currency.

## 9. Enums and Stable Values

By default, enums may be serialized using their constant names. Renaming a Java constant can unintentionally change the wire format.

Example:

~~~java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
~~~

If enum names are part of the public contract, treat renaming them as a breaking change. Another option is using stable codes such as `CREATED`, `PAID`, or schema-defined short codes with custom serializers/deserializers.

Tests should verify:

- Valid enum values parse properly.
- Unknown values are handled per contract.
- Whether casing is sensitive or normalized.
- Old values remain readable when producers and consumers upgrade asynchronously.

Do not silently map unknown enums to a valid status like `CREATED`; that can corrupt business logic.

## 10. Payload DTOs vs. Domain Entities

Avoid serializing an entire JPA entity or domain aggregate when consumers only need a subset of data.

Risks:

- Lazy-loaded associations can trigger unexpected queries.
- Circular object graphs can fail or produce complex JSON references.
- Internal fields such as audit columns, password hashes, or tokens can leak.
- Database schema changes accidentally alter the message contract.
- Large payloads increase network traffic, broker storage, and consumer memory.

Create a dedicated DTO/event:

~~~java
public record OrderExportPayload(
        Long orderId,
        String customerCode,
        BigDecimal total,
        String currency) {
}
~~~

A processor or mapper converts the domain object into a payload DTO before sending. The DTO should include only fields consumers need and carry an explicit version/schema contract.

## 11. Envelopes and Event Metadata

A payload can be wrapped in an envelope so consumers know the event type, version, and data:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-15T10:30:00Z",
  "data": {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00,
    "currency": "VND"
  }
}
~~~

An envelope typically contains:

- `eventId`: stable event identifier.
- `eventType`: event type.
- `schemaVersion`: contract version.
- `occurredAt`: business timestamp.
- `correlationId`/`causationId`: links to upstream flows.
- `data`: business payload.

Some fields belong in message headers rather than the body. For example, content type, transport partition keys, and correlation metadata can live in headers; event type/schema version can live in the envelope if messages are saved to files or cross multiple transports. Pick a consistent rule and avoid storing conflicting values for the same metadata in both headers and payload.

## 12. Correlation ID, Message ID, and Business Key

These three identifiers serve different purposes:

| Identifier | Meaning |
|---|---|
| `messageId` | Identifies a single transport delivery/record |
| `correlationId` | Links multiple messages within the same workflow |
| business key | Identifies the business entity, e.g., `orderId` |

When a broker redelivers a message, the message ID may depend on the transport or publishing mechanism; the business key remains the basis for business-level deduplication. If a producer retries publishing and creates a new message ID, a stable `eventId` in the payload lets consumers recognize the same event.

In Spring Batch, job execution/step execution references can be included in metadata for tracing, but should not replace business keys or event IDs.

## 13. JMS Serialization

JMS transmits message types such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. For modern integrations, JSON inside `TextMessage` or binary payloads inside `BytesMessage` are usually easier to govern by contract than `ObjectMessage`.

Spring JMS provides its own `MessageConverter` to convert Java objects to JMS `Message`s and back. For example, a Jackson converter configuration can serialize DTOs to JSON text or bytes depending on the converter and Spring version:

~~~java
@Bean
public MessageConverter orderMessageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}
~~~

Converter APIs can vary across Spring Framework/Jackson versions. Check exact classes, target types, and type mappings in your actual dependencies. If consumers are non-Java, define an independent JSON contract rather than relying on class names in a type header.

## 14. Why Be Cautious with JMS ObjectMessage?

`ObjectMessage` typically relies on Java native serialization. Consumers need compatible classes and can hit issues when:

- Classes change packages or fields.
- Producers and consumers run different application versions.
- Classes are missing from the consumer's classpath.
- Deserialization instantiates unintended object graphs.
- Payloads arrive from untrusted sources.

Java native deserialization has a long history of security vulnerabilities. Never deserialize `ObjectMessage` from untrusted sources or brokers where publish permissions are not tightly restricted. Prefer text/binary formats with explicit schemas such as JSON, Avro, or Protobuf.

If a legacy system forces `ObjectMessage` usage, restrict trusted producers, allowlist permitted classes, keep the JDK/framework updated, and lock down broker permissions. Never treat running inside a private network as sufficient security.

## 15. Kafka Serialization

Kafka records carry keys and values as raw bytes across the wire boundary. Kafka clients use `Serializer<T>` on the producer and `Deserializer<T>` on the consumer:

~~~text
Producer object
  -> Serializer
  -> Kafka record key/value bytes
  -> topic/partition
  -> Deserializer
  -> Consumer object
~~~

Example JSON serializer/deserializer configuration in Spring Kafka using `JsonSerializer` and `JsonDeserializer`:

~~~java
Map<String, Object> producerProps = new HashMap<>();
producerProps.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);

Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class);
consumerProps.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderEvent.class);
~~~

Property names and packages can vary across Spring Kafka versions. Configure trusted packages/type mappings properly and avoid relying on Java class names when producers and consumers use different languages.

Kafka keys are usually serialized separately and can determine partitioning. Keys should be chosen based on ordering/affinity needs, such as `orderId` or `customerId`. Do not confuse the partition key with payload business identity when a contract spans multiple event types.

## 16. Type Headers in JSON Messages

Some converters attach type metadata to headers so the consumer knows the target class. This is convenient in a homogeneous Java ecosystem, but couples the contract to package/class names.

Example:

- Producer sends a type header containing the Java class name.
- Consumer attempts to load that class.
- Producer renames the package or class.
- Older consumers fail to find the class even though JSON fields remain compatible.

For cross-service or cross-language contracts, use a stable `eventType`/`schemaVersion` and an explicit mapping from event type to allowed DTOs. Never let payloads specify arbitrary Java classes for the deserializer to load.

If using Spring Kafka type headers, configure type mappings or default target types. Verify producer and consumer behavior when headers are missing, unrecognized, or outside the allowlist.

## 17. Avro and Schema Registry

Avro uses schemas to describe record structures and serializes data into binary form. Producers and consumers require compatible schemas; a schema registry can manage versions and compatibility policies.

An abridged Avro schema:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "orderId", "type": "long"},
    {"name": "customerId", "type": "string"},
    {"name": "amount", "type": "bytes"},
    {"name": "currency", "type": "string"}
  ]
}
~~~

This example only illustrates structure; decimals are typically modeled with the `decimal` `logicalType` specifying precision/scale and an appropriate `bytes`/`fixed` schema. Never treat raw `bytes` as a decimal without logical-type metadata.

Advantages of Avro:

- Compact binary payloads.
- Versioned schemas.
- Consumers can read older writer schemas using newer reader schemas when compatibility rules allow.
- Multi-language support.

A schema registry does not guarantee every change is safe on its own. Choose backward, forward, or full compatibility according to producer/consumer deployment order and replay procedures.

## 18. Protocol Buffers

Protocol Buffers describe messages in `.proto` files and generate code for target languages.

Example:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  int64 order_id = 1;
  string customer_id = 2;
  string amount = 3;
  string currency = 4;
}
~~~

Field numbers are part of the wire contract. When evolving schemas:

- Never reuse deleted field numbers.
- Use `reserved` for retired field numbers/names when needed.
- Add new fields in a compatible way.
- Verify default-value and field-presence semantics.
- Keep types stable; changing types can misinterpret old data.

In the example, `amount` is a `string` to avoid assuming a decimal mapping; a real contract might use integer minor units or a dedicated `Decimal` message with explicit scale.

## 19. Schema Versioning

Producers and consumers are rarely deployed at the exact same instant. Therefore, payloads need a compatibility strategy:

- **Backward compatibility:** new consumers can read old messages.
- **Forward compatibility:** old consumers can read new messages within defined rules.
- **Full compatibility:** both directions are supported per schema policy.

Changes that are typically low risk:

- Adding optional fields with explicit defaults.
- Adding enum values if consumers have an unknown-value strategy.
- Preserving existing field names, types, and meanings.

Changes that are typically breaking:

- Removing a field required by consumers.
- Changing a numeric type to string.
- Changing a field's semantics while keeping its name.
- Changing date/time timezone or format.
- Changing enum values or renaming wire values.
- Changing currency units or scale without updating the contract.

Do not version structure alone; semantics must also be governed. Changing an `amount` field from gross to net is a breaking change even though its type remains numeric.

## 20. Consumer-Driven Contracts and Rollout

Before a producer emits a new payload version, know which consumers read that topic/queue. A rollout procedure can look like:

1. Define the new schema and check compatibility.
2. Deploy consumers capable of reading both old and new versions.
3. Verify new consumers process old payloads cleanly.
4. Deploy producers emitting the new version.
5. Monitor parse errors, unknown fields, and business validations.
6. Drop support for the old version only after retention/replay windows expire and all consumers have upgraded.

If producers deploy ahead of consumers, new payloads may be rejected by old consumers. In batch jobs, a burst of failing messages can fail steps or inflate skip counts. Test rollout ordering and replayability of older messages.

## 21. Serialization in Remote Chunking

Remote chunking splits work between a manager step and worker steps. The manager reads/processes items and sends chunks to workers over messaging middleware; workers receive chunks and perform writes.

~~~mermaid
flowchart LR
    A[Manager reader] --> B[Manager processor]
    B --> C[Chunk request]
    C --> D[Serializer]
    D --> E[Broker]
    E --> F[Deserializer]
    F --> G[Worker writer]
    G --> H[Business database]
    H --> I[Chunk response]
    I --> J[Manager]
~~~

In this model, payloads can carry chunk items and coordination metadata. Items must be serializable with the active converter/transport. Workers must be able to deserialize the exact types or share a common schema contract.

Avoid sending entities with lazy proxies, open streams, JDBC connections, or unnecessarily huge object graphs. Send small, stable DTOs/commands. If workers need additional data, send business keys so workers fetch from a shared store rather than serializing entire aggregates.

Remote chunking fits when the manager supplies chunks and workers execute the same type of processing/write workload. The broker needs sufficient throughput along with proper backpressure, acknowledgement, and retry mechanisms.

## 22. Serialization in Remote Partitioning

Remote partitioning differs from remote chunking. The manager splits the workload into partitions and sends execution requests to workers. Workers typically use the partition context to read their partition's data from a shared data source.

Request payloads can consist mainly of coordination info such as job/step execution identity, step name, and partition name; business items do not need to be serialized in the request.

This creates clear differences:

| Remote Chunking | Remote Partitioning |
|---|---|
| Manager sends chunk items to workers | Manager sends partition execution requests |
| Payloads can be large because they contain items | Requests are usually small, holding partition metadata |
| Workers process the sent chunk | Workers read their assigned slice of data themselves |
| Item serialization is central | Execution request/context serialization is central |

Do not send a list of millions of keys inside a partition request. Store partition ranges/filters in execution contexts or staging tables and pass suitable references/keys. Ensure workers can access the required data and metadata.

## 23. Payloads Must Respect Message Size Limits

Brokers generally enforce message size limits or producer/consumer cap settings. Oversized payloads can:

- Be rejected by the producer.
- Be rejected by the broker or inflate storage/replication costs.
- Force consumers to allocate excessive heap during deserialization.
- Increase network latency and retry durations.
- Make a single failing message hard to replay or inspect.

With remote chunking, chunk size is both a transaction/recovery parameter and a driver of message size. Do not pick chunk size based solely on database throughput; calculate total bytes after serialization, headers, and protocol overhead.

For very large payloads:

- Send only a business key or reference to object storage.
- Split payloads into messages with sequence/part metadata.
- Use a streaming protocol if supported by the transport.
- Compress when CPU cost and compatibility permit.
- Keep message envelopes small with manifests/checksums for external artifacts.

Do not split chunks arbitrarily if consumers require the full chunk for atomicity. Define how parts are aggregated and retried.

## 24. Compression

Compression reduces transmitted bytes and broker storage, at the cost of CPU, latency, and operational complexity. Producers and consumers must agree on the algorithm and how compressed payloads are indicated.

Check:

- Is the payload actually large enough for compression to pay off?
- Does the broker/client support native compression?
- Is compression applied at the record/batch level or application payload level?
- Does the consumer cap decompressed size to prevent decompression bombs?
- Do metrics distinguish compressed bytes from decompressed bytes?

Do not compress tiny payloads if overhead outweighs savings. With Kafka, compression can be configured at the producer/batch-record level; with JMS or message channels, application-level compression or broker features may be needed. Exact configuration depends on the transport.

## 25. Security During Deserialization

Deserialization processes data arriving from outside the process. Treat payloads as untrusted input, even when the broker is internal.

Principles:

- Never use Java native serialization for payloads from untrusted sources.
- Never enable broad Jackson default typing for external data.
- Use a DTO class allowlist or fixed type mappings.
- Validate schemas and bound collection depth/size.
- Bound message size, decompressed size, and string lengths.
- Never let payloads choose arbitrary classes to load.
- Use TLS, authentication, and authorization for the broker.
- Never log secrets or entire sensitive payloads.

A payload can be syntactically valid yet contain data designed to exhaust memory or trigger dangerous logic. Bound deserialization and follow it with validation.

## 26. Type Metadata and Polymorphic Payloads

If a payload has multiple subtypes, choose how type is represented:

- Event envelope with an `eventType` discriminator.
- Allowlist-controlled JSON type field.
- Schema registry/Avro record type.
- Protobuf message type per schema.
- Separate topics/queues per event family.

Never let payloads declare arbitrary Java class names loaded via reflection. Map type discriminators through a static registry:

~~~java
Map<String, Class<? extends EventPayload>> allowedTypes = Map.of(
        "OrderCreated", OrderCreatedPayload.class,
        "OrderCancelled", OrderCancelledPayload.class);
~~~

Consumers inspect `eventType`, look up the class from the allowlist, and deserialize. If the type is unknown, handle per contract such as quarantine or reject; never dynamically load classes from strings inside messages.

## 27. Validation After Deserialization

Successful deserialization only proves bytes/text can be turned into an object. It does not prove the payload is valid for business processing.

A typical pipeline includes:

1. Check content type and schema version.
2. Deserialize into an allowed DTO.
3. Validate required fields, ranges, and formats.
4. Check business invariants.
5. Check business keys/idempotency.
6. Pass valid items to the processor/writer.

Example:

~~~java
public void validate(OrderEvent event) {
    if (event.orderId() == null) {
        throw new InvalidPayloadException("orderId is required");
    }
    if (event.amount() == null || event.amount().signum() < 0) {
        throw new InvalidPayloadException("amount must be non-negative");
    }
}
~~~

Do not mix parser errors with business validation exceptions. Explicit classification decides which messages retry, which go to quarantine, and which require fixing the producer.

## 28. Malformed Payloads and Poison Messages

A poison message is a message that always fails when processed by a consumer—such as malformed JSON or an unsupported schema version. If the consumer retries infinitely, one message can stall a partition/queue or continuously waste resources.

Common strategies:

- Bounded retries for transient errors.
- No infinite retries for permanent parse/schema errors.
- Route unprocessable messages to a dead-letter queue or quarantine store.
- Record event ID, source, error code, and payload reference for investigation.
- Retain the ability to replay after fixing the consumer or schema.

Do not delete failing messages without leaving an audit trail if the data has business value. In batch jobs, poison messages can halt steps; decide whether to fail the entire job or skip/quarantine based on record independence.

## 29. Acknowledgement and Transactions

Message acknowledgement confirms the consumer processed or accepted a message per broker semantics. It does not automatically mean the business database committed if the two resources do not share a transaction.

Risk example:

1. Consumer receives message.
2. Deserialization succeeds.
3. Database writes and commits.
4. Process dies before ack.
5. Broker redelivers the message.

Consumers must be idempotent so redeliveries do not produce duplicate results.

Opposite risk:

1. Consumer acks the message.
2. Database write fails or has not committed.
3. Broker will no longer redeliver the message.
4. Business data is lost.

Acknowledgement/commit ordering and transaction integration depend on JMS/Kafka/RabbitMQ configuration. Use appropriate transaction/ack modes and still design idempotency for crash windows.

## 30. Exactly-Once vs. Real-World Message Processing

Do not promise "exactly once" merely because a broker supports transactional producers or consumer offset transactions. Transport-scoped exactly-once does not automatically guarantee external database, file, or API side effects occur only once.

A practical design typically uses:

- At-least-once delivery.
- Stable event IDs or idempotency keys.
- Unique constraints/deduplication ledgers.
- Database transactions for business updates.
- Outbox/inbox patterns when coordinating messages and databases.
- Controlled reconciliation and replay.

The inbox pattern stores processed event IDs alongside business updates in one transaction. When seeing an event ID again, the consumer knows the message was already applied and can ack without repeating side effects.

## 31. Serialization and Spring Batch Retry/Skip

Serialization/deserialization failures can occur before `ItemReader` returns an item or before `ItemWriter` sends a message. Identify the boundaries:

- Producer serialization error: the chunk may fail in the writer.
- Consumer deserialization error: the message listener/adapter may fail before the step receives an item.
- Business validation error: the processor may throw a per-item exception.
- Broker timeout: transport exceptions may be retried.

Do not apply the same retry policy to every exception. Permanent schema errors rarely resolve on retry; broker timeouts may be transient.

With a chunk writer sending multiple messages, if some messages publish and a later one fails, retrying the chunk may resend earlier messages. Use stable event IDs and consumer deduplication, or suitable transactional producers/outboxes.

## 32. Never Serialize the Entire ExecutionContext as a Business Payload

Spring Batch `ExecutionContext` is operational state for recovering a step/job. It can hold reader positions, page tokens, resource indices, and small checkpoint data. It is not a general cross-system message contract.

Do not send the entire `ExecutionContext` over a broker as a business payload:

- It may contain implementation-dependent internal keys.
- Some values may not serialize cleanly across versions.
- It may carry sensitive state or incompatible objects.
- Consumers should not depend on internal `JobRepository` metadata.

If a worker needs partition/job info, send a request DTO with explicit fields such as `jobExecutionId`, `stepName`, `partitionId`, or business ranges per the integration contract. Send only fields the worker genuinely needs.

## 33. Message Payloads in Remote Chunking: Designing DTOs

With remote chunking, payloads usually contain a group of items for workers to process. Ensure items:

- Serialize cleanly in the chosen format.
- Contain no non-transferable proxies/resources.
- Have a stable schema between manager and workers.
- Carry business keys and event/chunk correlation.
- Stay within message size limits.

Even if manager and workers share the same Java version/classpath, Java objects still cross a wire format. Sharing a codebase does not mean you can pass raw object references across a broker.

For large chunks, consider sending references to a staging dataset or object storage. Workers can read by range/key, reducing transmitted payloads and avoiding giant messages.

## 34. Message Payloads in Remote Partitioning: Keep Requests Small

In remote partitioning, the manager usually sends requests to execute partitions. Requests should contain just enough metadata for workers to launch the right partition, while business data is read from a shared source.

Conceptual request:

~~~json
{
  "jobExecutionId": 501,
  "stepName": "processOrders.worker",
  "partitionName": "partition-03",
  "fromOrderId": 20001,
  "toOrderId": 30000,
  "inputVersion": "snapshot-2026-11-15"
}
~~~

Workers validate the execution/partition and read data within the range. Do not send a whole list of objects when workers can query the same data source by partition key.

Internal ID fields should be used only within defined trust boundaries and version compatibility guarantees. If workers belong to a different application or version, use an explicit contract DTO rather than serializing internal metadata objects directly.

## 35. Schema Registries and Replay

Message brokers can retain messages longer than a single deployment lifecycle. A newer consumer may have to read messages serialized with an older schema.

A schema registry or schema repository helps:

- Store schema versions.
- Identify schema IDs/versions in messages.
- Validate compatibility before publishing.
- Recover writer schemas during replay.
- Govern when old schemas are retired.

Do not delete old schemas while messages remain within retention or may be replayed from archives. If older messages cannot be read, batch recovery/backfills can be blocked.

## 36. Testing Round-Trip Serialization

Round-trip tests verify an object retains required semantics after serialization and deserialization:

~~~java
@Test
void serializesAndDeserializesOrderEvent() throws Exception {
    OrderEvent original = new OrderEvent(
            "evt-1001",
            1001L,
            "C001",
            new BigDecimal("250.00"),
            "VND",
            Instant.parse("2026-11-15T10:30:00Z"));

    String json = objectMapper.writeValueAsString(original);
    OrderEvent restored = objectMapper.readValue(json, OrderEvent.class);

    assertEquals(original, restored);
}
~~~

Round-trip tests are useful, but insufficient on their own to prove compatibility between two versions. When producer and consumer share the same `ObjectMapper` and class, tests can mask issues like class-name-coupled type headers or schema evolution breaks.

## 37. Testing Independent Wire Contracts

Write tests that inspect the actual JSON/binary representation consumers receive:

- Field names match the contract.
- Required fields are present.
- Internal fields are not leaked.
- Timestamps have the right timezone/format.
- Decimals and enums have stable representations.
- Content type/schema version is correct.
- Correlation/key headers are set properly.
- Unknown fields follow policy.

Small golden fixtures help verify wire contracts. Parse actual JSON into a tree when key ordering is not part of the contract; compare exact byte/string representations only when exact formatting is required.

## 38. Testing Schema Compatibility

For versioned schemas, build fixtures from every producer version that must be supported:

- New consumers read old payload versions.
- Consumers handle new optional fields.
- Unknown enum values take the defined fallback path.
- Missing required fields are rejected explicitly.
- Unsupported versions go to quarantine/DLQ.
- Replaying old messages does not depend on deleted classes.

With Avro/Protobuf, run compatibility checks using your schema registry/tooling. With JSON, validate against JSON Schema and test across old/new mapper configurations.

## 39. Testing Deserialization Errors and Poison Messages

Required tests:

- Malformed JSON.
- Empty or null payloads.
- Unsupported content types.
- Non-existent schema versions.
- Wrong field types.
- Payloads exceeding size limits.
- Polymorphic types outside the allowlist.
- Truncated messages or invalid bytes.

Verify consumers do not ack unprocessed messages under the chosen semantics, or route them properly to a DLQ/quarantine. Check logs/error records include event IDs and error codes without leaking secrets.

## 40. Integration Tests with a Broker

Converter unit tests do not prove adapters and brokers are wired properly. Integration tests can use a broker container or embedded broker matching the transport:

1. Initialize producer and consumer with identical converter/serializer configurations.
2. Send messages with representative payloads and headers.
3. Receive messages at the consumer.
4. Verify payload, content type, correlation ID, and key.
5. Send malformed payloads and verify error handling/DLQ.
6. Simulate redelivery and verify idempotency.
7. Verify acknowledgement/transaction behavior when database writes fail.

Real broker tests catch mismatches between in-memory `Message` objects and wire representations. Keep performance/throughput tests separate so standard test suites stay stable.

## 41. Testing a Spring Batch Message Writer

If a step uses a message-sending writer, integration tests should verify:

- Each item emits the expected single event or contract-defined event count.
- Payloads serialize properly.
- Message keys/partition keys are chosen accurately.
- Publish exceptions drive chunk handling per policy.
- Retries do not create unintended duplicate events.
- Chunk commits/acks align with transport transactions.
- Job restarts resume from checkpoints with stable event IDs.

If a writer publishes multiple messages in a chunk, test failures mid-publish. Verify consumer deduplication or outbox guarantees previously published messages do not create duplicate business effects when the chunk retries.

## 42. Testing Consumers and Batch Restarts

A consumer may write to a database and then ack the message. Tests should simulate the crash window:

1. Receive message with `eventId` `E1`.
2. Write business result and inbox record in the same transaction.
3. Commit.
4. Simulate process death before ack.
5. Broker redelivers `E1`.
6. Consumer checks inbox and does not write the business result again.
7. Consumer acks the redelivery.

For consumers running in a Spring Batch step, clarify whether message acknowledgement is managed by a listener container or the step's transaction. Never assume `JobRepository` checkpoints and broker offsets/acks are automatically atomic.

## 43. Payload Size, Chunk Size, and Backpressure

Large chunks can increase throughput, but also enlarge message payloads. When brokers or workers slow down, the manager may accumulate pending chunks, stressing memory and queue storage.

Measure:

- Average and percentile payload sizes after serialization.
- In-flight message counts.
- Queue/topic lag.
- Deserialization time.
- Worker processing and commit time.
- Retry/redelivery counts.
- DLQ rates.

Backpressure can be controlled via concurrency, prefetch, bounded queues, broker quotas, and chunk size. Do not raise worker concurrency indefinitely if the database or downstream is the bottleneck.

## 44. Observability for Serialization

Useful metrics and logs:

- Serialization success/failure counts.
- Deserialization failure counts by error type/schema version.
- Payload byte size.
- Serialization/deserialization latency.
- Unknown schema/type counts.
- DLQ/quarantine counts.
- Retry/redelivery counts.
- Event types and schema versions.
- Appropriate correlation IDs and business keys.

Do not log full payloads at `INFO` level. On errors, log event ID, content type, schema version, payload size, and error code; store sanitized sample payloads only when data policies allow.

## 45. Common Mistakes

| Scenario | Cause | Fix |
|---|---|---|
| Producer sends cleanly, consumer fails parsing | Sides use mismatched schemas or target types | Lock down contracts and run producer-consumer tests |
| `ClassNotFoundException` on message receipt | Relying on Java class names or native serialization | Use independent DTO/wire schemas and type-mapping allowlists |
| Shifted dates/times | Missing timezones or inconsistent formats | Use `Instant`/`OffsetDateTime` and ISO-8601 |
| Wrong decimal scale/value | Coercing to `double` or vague contracts | Use `BigDecimal` and test numeric semantics |
| Unknown enum fails consumer | Producer added an enum value | Define an unknown-value policy or version schemas |
| Oversized messages | Sending unbounded entities/chunks | Small DTOs, chunk sizing, references to object storage |
| Retries create duplicates | Publish/DB commit/ack not atomic | Stable event IDs, inbox/outbox, and idempotency |
| Poison messages retry forever | Treating parse/schema errors as transient | Bounded retries and DLQ/quarantine |
| Type header loads arbitrary classes | Unrestricted polymorphic deserialization | Allowlist event types and target DTOs |
| Replaying old messages fails | Old schemas/classes were deleted | Keep schema compatibility across retention windows |
| Headers and payload conflict | Metadata duplicated in multiple places | Designate a canonical source for each field |
| Batch restart resends chunks | Some messages published before failure | Stable event IDs and consumer deduplication |
| Consumer acks before DB commits | Acknowledgement uncoordinated with transaction | Suitable transaction/ack mode and inbox pattern |
| Logs leak data | Dumping raw payloads on error | Log metadata, business keys, and payload references |

## 46. Payload Serialization Design Workflow

1. **Identify the boundary:** does the message cross Spring Integration, JMS, Kafka, or another transport?
2. **Define the payload DTO:** include only fields consumers need, with a stable business key.
3. **Define the envelope/headers:** event type, schema version, correlation ID, content type, and key.
4. **Choose a wire format:** JSON, Avro, Protobuf, or a format supported by consumers.
5. **Configure serializer/deserializer:** use the transport's exact abstraction without mixing converter APIs.
6. **Govern schemas/versions:** define compatibility rules and support windows for older payloads.
7. **Bound payloads:** measure byte size, chunk size, nesting, collections, and decompressed size.
8. **Harden deserialization:** allowlist types, validate schemas, never natively deserialize untrusted data.
9. **Define delivery semantics:** acks, retries, redelivery, DLQs, and idempotency.
10. **Integrate with Batch:** understand chunk transactions, checkpoints, and out-of-transaction side effects.
11. **Write contract tests:** round-trip, wire fixtures, schema compatibility, and malformed payloads.
12. **Write integration tests:** send/receive via broker, simulate duplicates, failures, and restarts.
13. **Monitor production:** serialization errors, payload sizes, lag, retries, and DLQs.

## 47. Key Principles to Remember

- Payload holds primary message data; headers carry transport, routing, and correlation metadata.
- Serialization converts objects to bytes/text; deserialization reconstructs objects at consumers.
- Creating a Spring `Message` does not automatically mean the payload has been serialized onto the wire.
- Spring Messaging, Spring JMS, and Kafka clients have distinct converter/serializer APIs.
- JSON is easy to debug; Avro/Protobuf suit binary schema contracts; avoid Java native serialization across trust boundaries.
- Use dedicated DTO/event payloads instead of serializing full entities or object graphs.
- Standardize date/time, decimal, enum, null, and unknown-field behavior.
- Use stable event IDs/business keys for deduplication; message IDs and correlation IDs serve different purposes.
- Version schemas and test compatibility because producers and consumers often deploy independently.
- Remote chunking transmits chunk items; remote partitioning typically transmits smaller execution/partition requests.
- Bound payload size, chunk size, nesting, and decompressed size.
- Never let payloads select arbitrary Java classes on deserialization; use type allowlists.
- Permanent parse/schema errors should generally not retry forever; use replayable DLQs/quarantines.
- Broker acknowledgement is not automatically atomic with business database commits or `JobRepository` checkpoints.
- Use inbox/outbox, unique keys, and idempotency to handle redeliveries and crash windows.
- Test wire contracts, schema compatibility, malformed payloads, broker integration, and batch restarts.

Payload serialization is the data contract across components of a batch and messaging system. When payload DTOs stay small, schemas are versioned, serializers/deserializers match the transport, and consumers are idempotent, messages can be transmitted, replayed, and processed across many workers while preserving business meaning.
