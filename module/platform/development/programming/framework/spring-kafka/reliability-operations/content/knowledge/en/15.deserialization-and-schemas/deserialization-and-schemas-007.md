# Incompatible Serializers and Deserializers

In Spring Kafka, producers use a **serializer** to convert keys/values from Java objects into bytes, while consumers use a **deserializer** to restore data from the bytes Kafka stores. When the two sides disagree on wire format, encoding, data types, JSON type headers, or schemas, records may be persisted cleanly by brokers yet fail to be read by consumers. Sometimes a deserializer still returns an object whose data has the wrong meaning—a failure even more dangerous than a clear exception.

This is a reliability problem: a single bad record can cause a consumer to loop at the same offset, grow lag, block subsequent records on the partition, or fail even when routing to a DLT. Resolution must start from the **producer–consumer data contract**, not from mechanically increasing retry counts.

## 1. Where do serializers and deserializers sit?

~~~mermaid
flowchart LR
    A["Producer Java object"] --> B["Serializer"]
    B --> C["Kafka: key/value bytes"]
    C --> D["Deserializer"]
    D --> E["Spring listener Java object"]
    B -. "Serialization error" .-> F["Producer send failure"]
    D -. "Deserialization error" .-> G["Consumer error/recovery"]
~~~

Kafka brokers do not understand Java DTOs, JSON, or Avro on their own. Brokers store byte arrays, headers, topic, partition, offset, and timestamp. Format is an agreement between applications.

A compatible pair:

~~~text
Producer: JsonSerializer<OrderCreatedEvent>
  -> {"eventId":"evt-1","orderId":"ord-9","amount":150000}
  -> Kafka topic "orders"
  -> JsonDeserializer<OrderCreatedEvent>
  -> Listener receives OrderCreatedEvent
~~~

An incompatible pair:

~~~text
Producer: StringSerializer with value "ord-9|CREATED|150000"
  -> Kafka stores UTF-8 bytes
  -> Consumer: JsonDeserializer<OrderCreatedEvent>
  -> JSON parse error during poll()
~~~

Distinguish three layers:

| Layer | Function | Common errors |
|---|---|---|
| Producer serializer | Object → bytes before sending | Cannot serialize field, wrong serializer type |
| Consumer deserializer | Bytes → object inside Kafka consumer | Format mismatch, unknown schema, bad type header |
| Spring message converter/listener adapter | Object → `@KafkaListener` parameter type | Incompatible converter, wrong listener signature |

A consumer using `StringDeserializer` can read a JSON string as `String` without errors. Yet if the listener requires `OrderCreatedEvent` without a matching converter, the failure appears only at parameter conversion.

## 2. Common incompatibility patterns

| Producer sends | Consumer expects | Consequence |
|---|---|---|
| `StringSerializer` with plain text | `JsonDeserializer` | JSON parse error |
| `JsonSerializer` producing JSON object | `StringDeserializer` | May receive JSON string but wrong listener type |
| `ByteArraySerializer` containing binary | `StringDeserializer` | Garbled or meaningless decoded data |
| Avro/Protobuf with Schema Registry wire format | JSON deserializer | Parse error on first byte |
| JSON with Java FQCN type header | Consumer lacks that class | Class not found / type resolution failure |
| JSON without type header | `JsonDeserializer` without default type | Unknown target Java class |
| JSON schema v2 | Consumer understands only schema v1 | Missing field, enum/value mismatch |
| Key serializer changes type or encoding | Old key deserializer | Key error or altered partitioning |
| Custom compressed/encrypted payload | Consumer lacks matching decode step | Unparseable bytes |

Not every mismatch throws an exception. For example, changing currency units from whole units to cents may still parse as an integer while producing wrong business outcomes. Reliability requires both **wire compatibility** and **semantic compatibility**.

## 3. Consistent JSON configuration in Spring Boot

Suppose topic `orders` contains only one type, `OrderCreatedEvent`. The producer sends JSON without depending on the producer's Java class name; the consumer declares the target type explicitly.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders
    listener:
      ack-mode: record
~~~

Reasons for these settings:

- `StringSerializer` and `StringDeserializer` agree on string keys.
- `JsonSerializer` writes JSON for values.
- `spring.json.add.type.headers: false` stops the producer from embedding Java class names in type headers.
- `spring.json.value.default.type` and `spring.json.use.type.headers: false` tell the consumer the target type without needing type headers.
- `ErrorHandlingDeserializer` wraps the delegate so parse errors can enter Spring Kafka's recovery mechanism.
- `trusted.packages` restricts valid packages; never widen to `*` just to suppress errors.

Example DTO and listener:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long amount) {
}

@Component
class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

The configuration above works only when all topic values follow the corresponding contract. If the same topic carries multiple event types, a single default type is insufficient; use type mappings, envelopes, or a schema-aware format.

## 4. Java type headers create coupling between services

Spring Kafka `JsonSerializer` can attach Java type information in Kafka headers; `JsonDeserializer` can use those headers to decide which class to instantiate.

~~~text
Service producer:
  com.producer.events.OrderCreated

Type header:
  com.producer.events.OrderCreated

Service consumer:
  com.consumer.api.OrderCreatedEvent

Consumer lacks producer's class or does not trust the package.
~~~

The two applications' JSON payloads may be completely compatible, yet the consumer still fails because of the class name in the header. When services have separate codebases, avoid turning Java FQCNs into a public protocol.

Approaches:

1. For single-event-type topics: disable type headers and declare a default target type.
2. For multiple event types: use logical type mappings sharing tokens while each side maps to its own class.
3. Use an envelope with `eventType` and `schemaVersion`, then dispatch per business contract.
4. Use Avro, Protobuf, or JSON Schema with an explicit registry/contract.

Example logical token:

~~~yaml
# Producer
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: orderCreated:com.producer.events.OrderCreated
~~~

~~~yaml
# Consumer
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: orderCreated:com.consumer.events.OrderCreatedEvent
        spring.json.trusted.packages: com.consumer.events
~~~

The producer must enable sending type headers and the consumer must actually use type headers for this mapping to take effect. Never configure mappings while disabling type headers on both sides and expecting the framework to match classes by token automatically.

Never fix `not in trusted packages` errors with `spring.json.trusted.packages: "*"` in production. Trust only specific packages and verify which sources are allowed to send those type mappings.

## 5. Key serializers are also part of the contract

Keys are not just metadata for listeners. Kafka uses **key bytes** to choose partitions via the partitioner. If a producer switches keys from `String` to custom binary serialization, the same business ID can hash to a different partition.

~~~text
Producer v1: key = StringSerializer("order-42")
Producer v2: key = custom binary serializer(orderId=42)

=> Key bytes differ.
=> Key-based partition assignment may differ.
=> Event ordering for the same order is no longer as expected.
~~~

If the consumer still uses `StringDeserializer` for binary keys, records may fail before the listener receives the value, or produce gibberish strings. Therefore:

- Document the key schema separately from the value schema.
- Verify partitioning/ordering impacts when changing key serializers.
- If key failures also need recovery, wrap the key deserializer with `ErrorHandlingDeserializer`.
- The DLT publisher must be able to serialize raw key bytes when key deserialization fails.
- Major key contract changes may require a new topic and phased migration.

You cannot fix a key mismatch merely by changing the JSON value deserializer.

## 6. Schema evolution: even JSON can still be incompatible

Producer v1 writes:

~~~json
{
  "eventId": "evt-88",
  "orderId": "ord-120",
  "amount": 120000
}
~~~

Producer v2 renames a field and adds currency info:

~~~json
{
  "eventId": "evt-88",
  "orderId": "ord-120",
  "totalAmount": 120000,
  "currency": "VND"
}
~~~

An old consumer may expect `amount`. Depending on its mapper/constructor/validation, it may fail with a missing property or silently populate a default value. Both must be handled.

Changes to evaluate carefully:

| Schema change | Risk |
|---|---|
| Add optional field with default | Usually easier to keep compatible if consumers ignore unknown fields |
| Add required field | Old consumers may not understand, or old data lacks the field |
| Rename/delete field | Consumers may receive null/default or fail |
| Change String ↔ Number type | Conversion error or semantic corruption |
| Add enum value | Old consumers may lack matching case |
| Change money/timestamp units | May parse cleanly yet compute wrong results |
| Change nesting or structure | DTO mapping failure |
| Change wire-format framing | Deserializer cannot read it at all |

Schema compatibility should be tested at both parse and business levels. Post-deserialization validation helps prevent "syntactically valid" objects with broken invariants from being committed.

## 7. Avro, Protobuf, and Schema Registry

Avro/Protobuf serializers paired with Schema Registry write records in a wire format carrying a schema ID. Bytes are not necessarily UTF-8 JSON.

~~~text
Producer: Schema Registry-aware Avro serializer
  -> [magic byte][schema ID][binary payload]
  -> Kafka
Consumer: JsonDeserializer
  -> parse error because payload is not JSON text
~~~

Conversely, a consumer using a Schema Registry deserializer to read plain JSON may report `Unknown magic byte` or framing errors. In raw Kafka, there is no automatic format sniffer across Avro, Protobuf, and JSON for arbitrary payloads.

Systems must align on:

- Serializers/deserializers sharing the **same wire protocol** and registry vendor.
- Registry URL, credentials, subject-naming strategy, and schema ID format.
- Compatibility policy such as `BACKWARD`/`FORWARD`/`FULL` per the registry in use.
- Reader schema, writer schema, and handling of older versions.
- Compatible serializers for retry/DLT when payloads may be raw bytes.

`schema ID not found` errors can stem from pointing to the wrong registry, wrong subject/ID, or deleted schemas. Timeouts reaching the registry are infrastructure issues suited to retries, unlike permanently unparseable payload errors.

## 8. Identifying failures by exception and origin layer

Example symptoms:

~~~text
RecordDeserializationException:
  Error deserializing key/value for partition orders-2 at offset 418

DeserializationException: failed to deserialize

JsonParseException: Unexpected character ...

IllegalArgumentException:
  The class '...' is not in the trusted packages

IllegalStateException:
  No type information in headers and no default type provided
~~~

Exact wording varies by library and version. During investigation, preserve the exception class/cause chain, topic, partition, offset, and producer/consumer release versions.

| Symptom | Hypothesis to check |
|---|---|
| JSON parse error on first byte | Consumer is reading non-JSON string/binary |
| Unknown magic byte | Schema Registry deserializer reading wrong wire format |
| ClassNotFound/type mapping error | Type header references a class absent on consumer |
| Trusted packages error | Package/type ID not permitted |
| No type information | Missing both type header and default type |
| Consumer fails repeatedly at exact offset | Poison record lacks proper recovery |
| Producer `SerializationException` | Record may never have reached the broker |
| Listener `ClassCastException` | Deserialization or message conversion returned wrong type |
| No exception yet wrong fields | Schema/encoding/semantic mismatch |
| All records fail right after deploy | SerDe config change or breaking schema rollout |

If one record fails, trace that record's producer. If an entire partition/topic fails after a point in time, check rollout changes, schemas, and consumer factory configurations.

## 9. Why can't DefaultErrorHandler solve poll errors alone?

If the Kafka client's deserializer throws an exception inside `poll()`, the container does not yet have a valid `ConsumerRecord` to pass to the listener. Adding `DefaultErrorHandler` alone may not suffice; the consumer may repeat the failure at the same offset.

Spring Kafka's `ErrorHandlingDeserializer` wraps the delegate deserializer, catches parse failures, and places error metadata in record headers so the container/error handler can route the record to recovery.

~~~mermaid
flowchart TD
    A["Kafka record bytes"] --> B["ErrorHandlingDeserializer"]
    B -->|Delegate OK| C["Java object -> @KafkaListener"]
    B -->|Delegate fail| D["Deserialization exception metadata"]
    D --> E["Container error handler"]
    E --> F["DLT / quarantine"]
~~~

`ErrorHandlingDeserializer` does not repair data or upgrade schemas on its own. It enables **not losing the ability to advance offsets** when hitting a poison record, provided recovery is designed properly.

## 10. Wrapping both key and value when needed

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders
~~~

Use the right delegates matching the actual producer. If a topic carries binary `Long` keys while config uses `StringDeserializer`, merely adding the wrapper helps recover errors raised—it does **not** turn a String deserializer into a compatible Long deserializer.

Spring Kafka can retain raw bytes and exception metadata to publish unparseable records to the DLT. The DLT producer must have suitable serializers for that data. Avoid sharing one consumer factory across multiple topics with different wire formats unless explicit dispatch is designed.

## 11. DefaultErrorHandler and DLT for unparseable records

Example error handler for non-transactional listeners:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> deadLetterTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        deadLetterTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        org.springframework.kafka.support.serializer.DeserializationException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

When a payload cannot be parsed under the contract, waiting another second rarely helps. Non-retryable classification routes the record to DLT/quarantine faster. The DLT needs enough partitions if the destination resolver keeps the source partition.

If DLT publishing fails, never treat recovery as finished and commit past the source record. Saving unreadable records is a data-protection step, not business completion.

For Kafka transactional listeners, rollback/recovery flows may use `DefaultAfterRollbackProcessor` instead of a similar non-transactional `DefaultErrorHandler`; confirm transaction boundaries before applying.

## 12. The DLT serializer must handle raw bytes

A common secondary failure: `ErrorHandlingDeserializer` catches the JSON error, yet `DeadLetterPublishingRecoverer` fails to publish because the DLT producer is configured only for Java DTOs. On deserialization errors, keys/values going to the DLT can be raw `byte[]`.

An example serializer dispatching delegates by data type (in Spring Kafka versions supporting `DelegatingByTypeSerializer`):

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

Serializer<Object> dltValueSerializer =
        new DelegatingByTypeSerializer(delegates, true);
~~~

This outlines a value serializer setup: bytes use `ByteArraySerializer`, while other objects use JSON. Wire this serializer into the corresponding producer factory. If keys can also fail deserialization, check the key serializer too. Constructor APIs and dispatch logic may vary across Spring Kafka versions.

Another strategy is designing a DLT that stores raw key/value bytes alongside a consistent metadata envelope, though that requires deliberate conversion and keeping full provenance. Never just switch the producer to `ByteArraySerializer` while the recoverer can still send Java objects.

## 13. Producer serialization errors: no record for consumers to retry

Serialization errors on the producer usually occur before the record is written successfully. A consumer DLT cannot rescue an event the producer never sent.

Example with Spring Kafka 3.x:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        try {
            kafkaTemplate.send("orders", event.orderId(), event)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        log.error("Publish failed: {}", event.eventId(), error);
                    }
                });
        }
        catch (RuntimeException error) {
            log.error("Publish failed before completion", error);
            throw error;
        }
    }
}
~~~

Spring Kafka 3.x uses `CompletableFuture` for `send`; older versions use different future APIs. Exceptions can be thrown synchronously or reported in the future/callback. For critical business events, persist publish failures durably—such as via transactional outbox—and fix the cause before resending.

Do not infinitely retry a serializer failure that does not recognize a class/format; fix the serialization contract, model, or producer configuration.

## 14. Pre-listener errors differ from post-listener errors

An easily confused example: the producer writes a JSON object, the consumer configures `StringDeserializer`, and the listener declares `OrderCreatedEvent`.

~~~text
Kafka bytes: {"eventId":"evt-1"}
     |
StringDeserializer
     v
Java String: "{\"eventId\":\"evt-1\"}"
     |
Spring listener adapter
     v
No suitable converter to convert String -> OrderCreatedEvent
~~~

This can be a conversion/invocation error rather than a Kafka deserializer error. If you classify only `DeserializationException` and forget `MessageConversionException`, retry/recovery policies become inconsistent.

One diagnostic technique is checking the data type **returned by the configured deserializer** versus what the listener expects, rather than looking solely at raw payloads. Avoid permanently changing production code into a `String` listener just to mask conversion errors; fix the contract at the right layer.

## 15. Inspecting raw bytes and Kafka headers

When formats are unclear, verify what the broker actually stored. Do not guess solely from Java DTOs, topic names, or a "send success" log.

Procedure:

1. Identify topic, partition, offset, and key of the failing record.
2. Identify the producer instance and version that sent that record.
3. Compare producer key/value serializers against consumer deserializers.
4. Inspect type headers, schema IDs, encodings, and custom framing.
5. Retrieve raw bytes safely (hash/hex preview, without logging sensitive data).
6. Compare against nearby successfully processed records.
7. Check deployment timestamps of producers, consumers, and Schema Registry.
8. Verify raw bytes decode cleanly under the right format before replaying.

Preliminary identification example:

~~~text
7B 22 65 76 65 6E 74 49 64 ...
^  ^
{  "
Likely the start of a UTF-8 JSON object

00 00 00 01 A7 ...
^
Likely Schema Registry-style framing, though you must inspect
wire protocol, schema ID, and full bytes rather than guessing from 1 byte.
~~~

If needing a debug tool to read raw values, use `ByteArrayDeserializer` with a **different** group ID from the production consumer, or read at a specific offset with an appropriately authorized tool. Never reset a production group's offset just to inspect a record.

## 16. Poison records, offsets, and lag

A broken record at offset 418 can block later records in the same partition:

~~~text
orders-2:
  417: read OK
  418: invalid JSON -> poll fail
  419: valid record
  420: valid record
~~~

Without a recovery mechanism, the consumer can fail continuously at 418 while group lag grows. After configuring `ErrorHandlingDeserializer`, the handler can route record 418 to the DLT so the group advances per policy.

Never "put out fires" by arbitrarily resetting or skipping offsets: doing so can forfeit business event processing. If an emergency skip is truly necessary, require approval, raw record preservation, and an explicit replay plan.

When record 418 is quarantined, also weigh ordering invariants. If 419 depends on 418, letting 419 run immediately may break business logic even though the Kafka consumer is moving again.

## 17. Compatible schema rollouts

Changing wire contracts when producers and consumers deploy independently requires sensible upgrade ordering. One strategy is **expand then contract**:

~~~text
A. Consumer v1 is reading schema v1.
B. Deploy consumer v2 able to read both v1 and v2.
C. Producer starts emitting schema v2.
D. Monitor old consumers, retry topics, and DLT containing v1.
E. Only after retention/replay windows expire, drop v1 support.
~~~

Technical practices:

- `eventType` + `schemaVersion` envelopes and upcasters for older events.
- Schema Registry compatibility checks in CI/CD.
- Contract tests on **real serialized bytes**, not just mocked DTOs.
- Post-deserialization validation for required fields, currency, timezone, and enums.
- Tolerant-reader consumers with intentional defaults/aliases, without swallowing errors into corrupt data.
- Dual-read or new topics for major wire-format shifts.
- Preserving event IDs/idempotency across retries and replays.

Note that DLT or retry topics may retain older-version records longer than the source topic. Before removing schema v1 support, plan for replaying older DLT records too, not just today's live consumers.

## 18. Retry topics and transactions also need compatible SerDe

If the application uses non-blocking retries, records are forwarded across multiple topics. Both the producer forwarding to retry topics and the retry consumer need serializers/deserializers compatible with the emitted data. Sometimes the main topic works while the retry topic fails due to a different factory or misconfigured raw bytes.

Kafka transactions can coordinate certain Kafka publishes and offset commits within a configured transaction, yet cannot make a format-mismatched deserializer read incompatible bytes. If listeners have database/HTTP side effects, idempotency or inbox/outbox patterns are still required to prevent duplicate effects on replay.

Do not mix non-transactional `DefaultErrorHandler` settings with transactional rollback flows without analyzing semantics. Fixing SerDe and defining the recovery path must come before tuning transactions/retries.

## 19. Observability and alerting

| Metric | Purpose |
|---|---|
| Producer serialization/send failures | Detects unsent events |
| Consumer deserialization errors by topic | Identifies format mismatches and poison records |
| Exception type/cause, app version | Correlates incidents with deployments |
| Lag pinned at a single offset | Detects stuck consumers |
| JSON type ID / schema ID errors | Spots coupling or schema mismatches |
| Schema Registry latency/error rate | Separates registry outages from broken payloads |
| DLT count by source and exception | Tracks quarantined events |
| DLT publish failures | Catches secondary serializer bugs |
| Replay success/failure and duplicate rate | Evaluates safe recovery |

Metric tags should be low cardinality such as topic, event type, and exception class. Event IDs and offsets belong in logs/traces, not metric labels with millions of values.

Alerts should distinguish **a single poison record** from **mass errors after a deployment**. If all new records fail, rolling back or pausing the source may be needed rather than flushing the entire backlog to the DLT.

## 20. Runbook for serializer/deserializer failures

1. **Scope:** which topics, partitions, offsets, producer versions, and consumer groups are affected?
2. **Locate layer:** producer serializer, Kafka deserializer, Spring message converter, or listener logic?
3. **Compare configs:** key/value SerDe, target types, trusted packages, type headers, and registry.
4. **Inspect evidence:** exception class/cause, raw byte previews, headers, schema ID/version.
5. **Determine blast radius:** one record, one producer instance, or all records after a rollout?
6. **Classify:** permanently wrong format, breaking schema, misconfigured class/type, or transient registry outage?
7. **Preserve records:** use `ErrorHandlingDeserializer` and appropriate DLT/quarantine for unreadable records; verify the DLT publisher supports bytes.
8. **Fix the root cause:** update producer/consumer/schema contracts, not just retry attempts.
9. **Evaluate side effects:** idempotency, key ordering, and business state prior to replay.
10. **Compatible rollout:** consumers read both old and new data before producers switch.
11. **Controlled replay:** retain event IDs and provenance, and re-monitor exceptions/lag/DLT.
12. **Verify post-fix:** all necessary consumers advance offsets with no new serialization errors and no duplicated business actions.

## 21. Principles to remember

- Kafka stores **bytes**, not the producer's Java type safety.
- Treat keys and values as two independent serialization contracts.
- Distinguish producer send failures from consumer poll failures and Spring listener conversion failures.
- Avoid coupling via Java FQCNs across service boundaries unless truly necessary.
- Use default target types, logical type mappings, or envelopes appropriately.
- Validate schema evolution at both wire and semantic levels.
- With Avro/Protobuf, producers and consumers must share the same wire protocol and registry.
- `ErrorHandlingDeserializer` feeds deserialization failures into recovery; it does not repair payloads.
- DLT producers must support raw bytes for deserialization failure cases.
- Do not retry permanently malformed payloads infinitely; route to DLT and fix contracts.
- Never reset/skip offsets carelessly just to "get unstuck".
- Test compatibility with real serialized bytes and deploy consumers ahead of producers whenever possible.
- Preserve idempotency and event IDs whenever records may be reprocessed.

**Incompatible serializers and deserializers are data contract failures between Kafka applications.** Pinpointing the exact bytes written, actual SerDe classes, type/schema metadata, and exception origin layer reveals the right fix. For corrupted data, `ErrorHandlingDeserializer` and DLTs enable safe quarantine; for schema changes, versioning and compatible rollouts are required. Combining those practices with validation, observability, and idempotency lets Spring Kafka consumers recover without silently dropping business data.
