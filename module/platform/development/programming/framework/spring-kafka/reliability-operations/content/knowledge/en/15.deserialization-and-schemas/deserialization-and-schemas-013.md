# Dead-Lettering for Format Errors

In a Spring Kafka system, a record does not always reach `@KafkaListener` as a valid Java object. Kafka stores **keys and values as bytes**, and consumers must deserialize, convert data types, and validate schemas before invoking business logic. If a payload is truncated, JSON is invalid, type information is missing, or the schema is incompatible, errors can occur **right inside `poll()` or in the message conversion layer**, even before the listener method executes.

**Dead-lettering for format errors** is the mechanism for isolating unreadable or contract-violating records into a Dead Letter Topic (DLT), preserving both the payload and source metadata for investigation. When designed properly, a poison record neither stalls the entire consumer at the same offset nor gets silently dropped without traceability.

The focus of this lesson is coordinating `ErrorHandlingDeserializer`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, and DLT serializers. Retrying or routing to a DLT is only part of the picture: you must also decide which errors are recoverable, how to preserve raw bytes verbatim, and how to fix and replay safely.

## 1. At which layers do format errors occur?

A typical consumption flow includes these steps:

```text
Kafka broker stores key/value bytes
           |
           v
KafkaConsumer.poll()
           |
           v
KeyDeserializer / ValueDeserializer
           |
           v
Spring Kafka message converter / argument resolver
           |
           v
@KafkaListener method
           |
           v
Validation and business processing
```

Not every error labeled "format" happens at the same place. Where the failure occurs determines whether the framework already has a `ConsumerRecord` and raw payload to forward to the DLT.

| Layer | Error example | Measure to consider |
|---|---|---|
| Kafka deserializer | Non-JSON bytes, broken Avro framing, unconvertible enum | Use `ErrorHandlingDeserializer` so errors enter container error handling |
| Schema/serialization registry | Schema ID not found, incompatible schema, registry timeout | Separate permanent payload errors from transient dependency failures |
| Spring message conversion | Wrong type header, converter cannot adapt to listener parameter | `DefaultErrorHandler` and recoverer; retain type/schema metadata |
| Listener argument resolution | Payload mismatches method signature | Fix contract/method and store failed record for investigation |
| Bean validation or domain validation | Missing required field, out-of-range value | Clearly classify data errors, business rejections, and transient errors |

For example, the value is the byte string `{"orderId":` missing its closing brace. `JsonDeserializer` can throw an exception right during consumer poll. Conversely, a JSON payload may be syntactically valid yet omit `orderId` required by the domain model; then the error appears only when the converter or listener validation runs. Therefore, format error handling must cover **both pre- and post-deserialization failures**.

## 2. Why can a consumer get stuck before the listener?

If the Kafka consumer is configured directly with `JsonDeserializer` or a custom deserializer, an error inside `deserialize()` can make `KafkaConsumer.poll()` throw an exception. The container has not received a deserialized record to deliver to the listener. Merely adding `try/catch` inside `@KafkaListener` will not resolve this error because the method is never invoked.

Example error-prone configuration:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
```

When a record contains bad bytes, the container can repeatedly hit the error at that read position. The error handler cannot always handle it with normal seeks if there is no valid `ConsumerRecord` identifying the failing record. Such a toxic record can block progress for all subsequent records.

Spring Kafka provides `ErrorHandlingDeserializer` to **wrap the real deserializer**. It catches `DeserializationException` from the delegate, stores error details in headers, and gives the container a way to process the failed record via the error handler instead of merely receiving an exception out of `poll()`.

## 3. Configuring `ErrorHandlingDeserializer`

Example consumer receiving string keys and JSON values mapped to `OrderCreated`. The value deserializer is wrapped by `ErrorHandlingDeserializer`, with `JsonDeserializer` as delegate:

```properties
spring.kafka.consumer.enable-auto-commit=false

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

In this example, `com.example.events.OrderCreated` is an illustrative application class. Actual classes, trusted packages, type headers, and schemas must match the producer. Never use `spring.json.trusted.packages=*` arbitrarily in production; allow only required packages and control data sources.

When the delegate fails deserialization, `ErrorHandlingDeserializer` records the exception in the record's headers. The container detects the relevant header and routes the failed record to the error handler. With `DeadLetterPublishingRecoverer`, the raw payload of the failed record can be restored for publishing to the DLT instead of publishing a data-losing `null` value.

### 3.1. Deserialization errors on keys

Keys can fail too—for example, a producer writes binary keys while the consumer expects a JSON key or UUID. When the key deserializer can fail, wrap **both key and value**, not just the value:

```properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
```

`StringDeserializer` accepts many UTF-8 byte sequences without throwing on every malformed character; the example illustrates wrapping the key rather than proving every malformed key string will trigger an error. To enforce specific key rules, use an appropriate custom deserializer/validator.

When key deserialization fails, the DLT publisher may have to write **raw key `byte[]`**, not `String`. Thus, DLT serializer design must account for both failed keys and failed values.

### 3.2. Errors originating from Schema Registry

When using Avro, Protobuf, or JSON Schema with a registry, the delegate inside `ErrorHandlingDeserializer` can be the registry library's deserializer rather than `JsonDeserializer`. In principle:

```text
ErrorHandlingDeserializer
          |
          v
Actual deserializer (Avro / Protobuf / JSON Schema)
          |
          +--> decode succeeds --> listener
          |
          +--> error -------------> exception header --> error handler
```

Delegate configuration, Schema Registry URL, authentication, and subject naming strategy depend on the chosen serialization library. Do not apply Spring Kafka's `JsonDeserializer`-specific properties as though they controlled Avro or Protobuf. Distinguish **genuinely wrong/missing schema IDs** from **temporary Schema Registry disconnects**: dependency errors may need retries or pausing the consumer instead of dumping huge numbers of valid events into the DLT.

## 4. From exception to DLT with `DefaultErrorHandler`

Once `ErrorHandlingDeserializer` feeds deserialization errors into the container's error-handling mechanism, `DefaultErrorHandler` decides retries and recovery. For syntactically invalid data or explicitly unsupported schemas, retrying the same bytes rarely helps. In modern Spring Kafka versions, exceptions such as `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException`, and `ClassCastException` are classified as fatal/not-retryable by default; verify the exact list for your version.

An illustrative configuration:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Recoverer fails if sending to DLT does not succeed.
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    // For application-defined contract errors:
    handler.addNotRetryableExceptions(
            UnsupportedMessageSchemaException.class,
            InvalidMessageFormatException.class);

    return handler;
}
```

In this example, retryable errors get up to two retries after the initial attempt; exceptions marked not-retryable go straight to the recoverer. The domain exceptions are illustrative application classes. `DeadLetterPublishingRecoverer` publishes failed records to `<source-topic>.DLT` with the destination partition matching the source partition; the DLT must have **at least as many partitions** so the resolver does not target a nonexistent partition.

`setFailIfSendResultIsError(true)` instructs the recoverer to fail when Kafka sending to the DLT fails in supported versions, rather than treating recovery as succeeded. Configure reasonable send timeouts, check broker acknowledgements, and ensure topics/ACLs/serializers are valid. If recovery fails, the source offset must not be treated as a successfully recovered record.

### 4.1. Attaching the handler to the right listener factory

```java
@Bean(name = "orderListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}

@KafkaListener(
        topics = "orders",
        groupId = "order-processing",
        containerFactory = "orderListenerContainerFactory")
public void handleOrder(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

The `handleOrder()` listener does not need to catch JSON deserialization exceptions itself. For undeserializable payloads, the method is usually never invoked; the container/error handler handles the record via the exception header. The listener remains responsible for business validation, idempotency, and throwing explicit exceptions if decoded data is invalid.

Do not call `acknowledge()` inside a `finally` block as a way to "skip" failing records. Offset commits must follow container acknowledgment and recovery policies; completing recovery does not mean the business request succeeded.

## 5. DLT serializers: preserving raw bytes on broken payloads

This is the easiest mistake when implementing dead-lettering for format errors. In normal processing, producers send an `OrderCreated` object and `JsonSerializer` converts it into bytes. When consumer deserialization fails, `DeadLetterPublishingRecoverer` can restore **raw bytes of the failing payload** from the info saved by `ErrorHandlingDeserializer`.

If the DLT `KafkaTemplate` always uses `JsonSerializer<OrderCreated>`, it may fail to handle raw `byte[]` as desired. Conversely, if it always uses `ByteArraySerializer`, it will not fit records that failed at the listener layer whose values are already-deserialized domain objects. Therefore, a DLT can receive at least two value shapes:

| Error source | Data passed to DLT publisher | Serializer usually needed |
|---|---|---|
| Value deserialization failed | Restored raw value `byte[]` | `ByteArraySerializer` |
| Key deserialization failed | Restored raw key `byte[]` | `ByteArraySerializer` for key |
| Exception in listener after deserialization | Value is a valid Java object | `JsonSerializer`, Avro serializer, or contract's serializer |
| Record with mixed key/value types | Key or value varies by runtime type | Type-dispatching serializer or multiple templates |

In Spring Kafka, `DelegatingByTypeSerializer` can select a serializer by **runtime type**. The following example illustrates a DLT template supporting raw bytes for broken records and JSON for deserialized objects (add standard imports):

```java
@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildProducerProperties());

    Map<Class<?>, Serializer<?>> keySerializers = new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers = new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(Object.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
            props,
            new DelegatingByTypeSerializer(keySerializers, true),
            new DelegatingByTypeSerializer(valueSerializers, true));
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        @Qualifier("dltProducerFactory")
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Here, `byte[]` is checked before `Object.class`; the `true` parameter enables matching assignable types. `Object.class` is an illustrative fallback for JSON objects and is unsuitable if the application uses multiple distinct serialization formats. For Avro/Protobuf/Schema Registry, use matching serializers or separate DLT templates. When the project inherits security/durability producer settings from Spring Boot, ensure `KafkaProperties` actually carries TLS/SASL, acks, retries, and other parameters; `buildProducerProperties` overloads can vary across Spring Boot versions.

For keys that are neither `String` nor `byte[]`, add the matching key serializer. The DLT publisher must handle *both* broken and unbroken key/value cases. Picking the wrong serializer causes recovery itself to fail and leaves the failing record blocking the consumer.

## 6. When a record enters the DLT, what information must be kept?

A DLT record must carry enough provenance to answer: where did the failing record come from, what were the original bytes, which layer failed, and how can it be replayed? `DeadLetterPublishingRecoverer` adds headers identifying origin and exceptions. Constants such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, and `KafkaHeaders.DLT_ORIGINAL_OFFSET` retrieve part of this info; systems may also use corresponding error and timestamp headers.

Example of a DLT record:

```text
Current Kafka record:
  topic: orders.DLT
  partition: 3
  offset: 824
  value: 7b 22 6f 72 64 65 72 49 64 22 3a ... (failing bytes)

Source info:
  original topic: orders
  original partition: 3
  original offset: 241
  exception class: ...DeserializationException

Business info (if supplied by producer):
  event-id: evt-7b82
  schema-version: 5
  correlation-id: req-4902
```

Offset 824 belongs to the **DLT**, while offset 241 belongs to the source topic; the two are separate coordinates. The DLT also has independent retention, so never assume failing records remain forever.

Internal exception headers from `ErrorHandlingDeserializer` can contain exception data serialized by Spring Kafka mechanics. `DeadLetterPublishingRecoverer` has its own rules for restoring payloads and retaining/stripping internal error headers before publishing to the DLT, depending on version and configuration. Do not build operations assuming every internal header is readable as UTF-8. Use supported DLT metadata, preserve event IDs, and add clear application headers when needed.

Do not log full raw payloads or stack traces containing personal data, tokens, or secrets. DLT access must be permission-controlled; retention should fit investigation windows and security rules.

## 7. JSON syntax errors vs. incompatible schemas

These two error types often produce similar deserialization/conversion exceptions, yet their remediation differs.

### 7.1. Syntactically invalid JSON

Payload:

```json
{"orderId": "ORD-100", "amount":
```

This is incomplete JSON. Retrying the exact same bytes will never make it valid. The DLT must keep raw bytes so the producer owner can find the cause: serialization bug, truncation prior to publish, or a producer violating the contract.

If the data is critical and reconstructible from a reliable source of truth, operations can repair the source or emit a new properly formatted event. Never manually "patch" bytes in production without clear business meaning and audit procedures.

### 7.2. Valid JSON that mismatches the Java model

Payload:

```json
{"orderId": "ORD-100", "amount": "not-a-number"}
```

The JSON is syntactically valid yet cannot convert into `BigDecimal` or the configured domain object. Causes may include a producer contract change or a missing mapping on the consumer. Fix by repairing the producer/schema, deploying a compatible consumer, or running a controlled transformation workflow.

### 7.3. Schema ID/version no longer compatible

With Avro/Protobuf/JSON Schema via a registry, payloads may be validly encoded yet consumers cannot decode them because a schema ID is missing, the version is incompatible, or the registry is unavailable. These cases **are not equivalent**:

- Nonexistent schema ID or broken framing: usually cannot self-heal with retries alone.
- Consumer does not yet support the new event version: upgrade the consumer or apply schema compatibility strategies.
- Registry temporarily disconnected: can recover once the dependency returns; use backoff/circuit breakers instead of defaulting everything to DLT.
- Wrong registry credentials/ACL: fix operationally; continuous retries can trigger storms.

Do not lump every Schema Registry exception into "permanently corrupted data". If a registry outage sends thousands of valid events into the DLT, the system builds a massive backlog and unnecessary replay work. Classification must rest on root cause and business impact.

## 8. When not to retry vs. when to pause the consumer?

`DefaultErrorHandler` supports retryable/not-retryable classification. For confirmed syntactically broken payloads, non-retry and DLT are usually appropriate. For network errors to a registry or recoverable dependencies, retrying with backoff or pausing consumption may be better.

| Condition | Recommended policy | Why |
|---|---|---|
| Repeatedly unparseable raw bytes | Immediate DLT, no retries on same payload | Data error does not change on its own |
| Known unsupported message type/version | DLT/quarantine; update consumer then replay | Requires deploying new schema/code |
| Registry timeout of a few seconds | Bounded retry, backoff, and alert | Dependency can recover on its own |
| Prolonged registry outage | Controlled throttling/pause, evaluate DLT thresholds | Avoids flooding DLT with valid events |
| Wrong registry credentials/ACL | Alert and fix configuration | Retries cannot fix access permissions |
| Valid business validation rejection | Handle as business outcome instead of blind DLT | Not every rejection is a broken message |

Note: errors converted into `DeserializationException` by `ErrorHandlingDeserializer` may be treated as fatal by default classifiers. If the root cause is a temporary registry incident, overriding retry classification must be carefully designed and tested; do not simply add an arbitrary `RetryableException` expecting all delegate errors to become retryable. You may need deserializer structuring or custom handling to preserve root causes and avoid retrying the wrong error classes.

## 9. Committing offsets after recovery

After DLT publishing succeeds, the container can advance past the failing record according to the ack mode and error handler policy. **Saving a record to the DLT is a recovery outcome, not successful business processing.**

Example topic `orders-3`:

| Offset | Result |
|---:|---|
| 240 | Listener processed normally |
| 241 | Value deserialization failed, recovered to `orders.DLT` |
| 242 | Next valid record |

For the consumer to advance past offset 241, the group's final committed offset must move beyond that record (typically 242 after corresponding processing/recovery). When using `DefaultErrorHandler`, the interaction among `ackAfterHandle`, acknowledgment mode, and recovery determines when commits happen. With `setCommitRecovered(true)`, `DefaultErrorHandler` requires `AckMode.MANUAL_IMMEDIATE`; this is a distinct setting and is not enabled automatically by adding a DLT recoverer.

If the DLT publisher reports an error (e.g., nonexistent topic, wrong serialization, or broker failed to acknowledge), **never** treat the record as recovered and commit past it as if it were safely persisted to the DLT. Log/alert clearly and retain the ability to retry/re-recover once the issue is resolved.

There is no default atomicity between DLT publishing and source consumer offset commits. A crash can occur after the DLT receives the record yet before the offset commits, causing a source record to be sent to the DLT multiple times after a restart. Use stable event IDs or `(originalTopic, originalPartition, originalOffset)` to deduplicate during investigation/replay. If atomicity within Kafka scope is required, evaluate transactional recovery with `DefaultAfterRollbackProcessor` and properly configured Kafka transactions; those transactions do not cover database or HTTP side effects automatically.

## 10. Risks of retry topics for format errors

With `@RetryableTopic`, a failed record can be forwarded through retry topics before reaching the DLT. However, an undeserializable record will fail again in the retry-topic consumer if the same deserializer is applied and the payload remains unchanged. Merely changing the topic name does not fix data.

For format errors unrecoverable by retrying, prefer routing straight to DLT/quarantine to avoid spawning multiple copies of poison messages. If using non-blocking retries for recoverable errors, verify:

- Whether retry-topic listeners can read keys/values and metadata of failed records.
- Whether serializers publishing to retry topics handle both raw bytes and regular objects.
- Whether exception classification separates transient schema/registry failures from permanently bad payloads.
- Whether per-key ordering may shift because records sit on retry topics while the main topic keeps advancing.
- Whether the final DLT has enough retention and metadata for replay after fixing the root cause.

Never configure multi-tier retries without knowing total attempt counts and retention windows. A retry storm from a post-release schema incompatibility can generate heavier load than normal traffic.

## 11. Batch listeners, conversion errors, and broken keys

With a batch listener, one poll holds multiple records. An undeserializable value must be isolated without losing or endlessly repeating other records. `ErrorHandlingDeserializer` remains essential for Kafka deserializer-layer errors; error metadata can attach to records inside the batch.

If an error occurs post-deserialization in conversion/binding, the batch listener may need `BatchListenerFailedException` with the appropriate index/record so the error handler knows which portion completed. Throwing a generic exception without pinpointing the failed record may make the framework retry the whole batch, repeating side effects already executed on preceding records.

Example of a batch listener checking schema versions after decoding into objects:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch",
        containerFactory = "batchOrderContainerFactory")
public void consumeBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        OrderCreated event = records.get(i).value();
        try {
            schemaValidator.assertSupported(event);
            orderService.processIdempotently(event);
        }
        catch (UnsupportedMessageSchemaException ex) {
            throw new BatchListenerFailedException(
                    "Unsupported schema at index " + i, ex, i);
        }
    }
}
```

In this example, the factory must enable batch listener mode and have a matching error handler. Separately test batch behavior when `ErrorHandlingDeserializer` sets failing values to `null`, when key deserialization fails, and when the message converter fails to build objects. Never treat `null` as a valid event when it actually represents a deserialization failure.

## 12. Designing DLT topics for malformed payloads

DLTs hold potentially malformed, unverified, or hard-to-decode data; they require explicit storage policies and access controls.

| Component | Operational requirement |
|---|---|
| Topic naming | Clear conventions and ownership, e.g., `<source>.DLT`; do not confuse with retry topics |
| Partitions | Destination resolver targets valid partitions; if preserving source partitions, DLT needs enough partitions |
| Replication and durability | `acks=all`, appropriate replication factor and `min.insync.replicas` |
| Retention | Long enough to detect, investigate, fix, and replay; avoid expiring before remediation finishes |
| ACLs | Only recovery services write; operations/triage read per least privilege |
| Key/value serializers | Accept raw `byte[]` and deserialized object types if multiple paths write to DLT |
| Schema provenance | Preserve original topic, offset, event ID, and schema ID/version if available |
| Observability | Track publish failures, DLT backlog, exception classes, and error rates by version |

A single DLT shared across multiple streams with different schemas requires special caution. If billing and audit write failures to one DLT with multiple consumer groups replaying automatically, cross-domain misprocessing can happen. Separate DLTs by stream or build a dispatcher with explicit ownership. A DLT is not a "junk drawer" topic for ignoring data governance.

## 13. Reading the DLT for investigation without re-triggering deserialization errors

An investigative DLT consumer should generally **read raw bytes** or use a deserializer tolerant of broken payloads, rather than reusing the exact deserializer that failed on the source topic.

Example creating a consumer factory for triage:

```java
@Bean("dltTriageConsumerFactory")
ConsumerFactory<byte[], byte[]> dltTriageConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-dlt-triage");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);

    return new DefaultKafkaConsumerFactory<>(props);
}
```

This illustrates a byte-reading triage consumer, not a listener auto-processing every DLT record. When a DLT can contain objects serialized under different types, interpreting payloads requires consulting content-type/schema metadata and the corresponding contracts. Raw bytes avoid repeating format failures when opening records, yet do not make payloads trustworthy on their own.

Triage should capture DLT coordinates, original topic/partition/offset, exceptions, event IDs, schema versions, and technical errors. Export payloads only in hex/base64 or bounded, controlled decoding—especially when data may contain sensitive content.

## 14. Replaying after fixing format or schema errors

Once the root cause is found and compatible consumer/producer versions exist, DLT records can be replayed to the source topic or through a dedicated reprocessing pipeline. Replaying **does not fix** broken payloads on its own. If bytes were truncated and cannot be reconstructed accurately, you may need to emit fresh events from the source of truth rather than resending broken payloads.

A controlled workflow:

1. Identify the DLT record set by reconciled topic, partition, offset, and/or event ID.
2. Classify: permanent format bug, schema mismatch, transient dependency, or consumer bug.
3. Fix the root cause and test a sample representing each error class.
4. Decide whether to keep raw bytes verbatim or transform to a new schema with an audit trail.
5. Set replay count caps, rate limits, an owner, and change approval.
6. Replay a few canary records while watching the source topic, business outcomes, and DLT re-entry.
7. Ramp gradually, reconciling published counts against business-processed counts.

Replay creates a **new record with a new offset** in the target topic. It does not place the record back at its old partition offset, so business ordering can shift. Consumers need idempotency and often state version checks if older events arrive after newer ones.

Never run an always-on DLT listener automatically shipping every record back to the source topic. If the bug is unfixed, an `orders -> orders.DLT -> orders -> ...` loop forms. Replay-count metadata and a final quarantine sink help cap loops, provided metadata survives each recovery hop.

## 15. Observing format errors in production

Recommended metrics:

- Total deserialization/conversion failures by topic, exception class, and consumer version.
- Rate of records routed to DLT due to format errors, schema errors, and registry errors.
- DLT publish successes/failures/timeouts; DLT record counts and oldest pending record age.
- Source topic consumer lag, rebalance counts, commit failures, and actual throughput.
- Schema errors by producer version/schema ID when metadata is available.
- DLT re-entry rate after replay and counts exceeding replay caps.

Logs should include source coordinates, DLT coordinates on successful send, exception class, root cause, schema metadata, listener/group, and correlation ID. Never use individual event IDs/offsets as metric labels due to high cardinality; keep them in structured logs or audits. Especially, never write full failing payloads to default logs because payloads can contain untrusted or sensitive data.

If format errors spike suddenly after a deployment, compare producer, consumer, and schema versions. If multiple consumers fail simultaneously during one window while payloads look valid, check Schema Registry/network outages before deciding on bulk replays. When DLT backlogs grow, pause deployments or throttle throughput to avoid filling storage.

## 16. Common implementation mistakes

| Symptom | Possible cause | Remediation |
|---|---|---|
| `@KafkaListener` never called, consumer keeps failing in `poll()` | Delegate deserializer throws directly without `ErrorHandlingDeserializer` | Wrap appropriate deserializer and attach `DefaultErrorHandler` with recoverer |
| DLT holds `null` instead of failing payload | Raw bytes not recovered properly or custom serializer/recoverer dropped payload | Check `ErrorHandlingDeserializer`, `DeadLetterPublishingRecoverer`, and actual DLT data |
| DLT publish keeps throwing serialization errors | DLT template supports only objects or only byte arrays | Use type-dispatching serializer or dedicated templates |
| Key error breaks DLT publishing | DLT key serializer rejects `byte[]` | Add `ByteArraySerializer` branch for keys and test key deserialization failures |
| Valid payloads flood DLT en masse | Schema Registry outage, wrong type mapping, or incompatible consumer | Check root cause, schema/config, and throttle before replaying |
| Recoverer logs success yet DLT has no records | Send future failed unreported | Enable fail-on-send-error appropriately; verify timeouts/acks, topic, and offsets |
| DLT topic misses records from higher partitions | DLT has fewer partitions than source while resolver preserves partition index | Add DLT partitions or pick a valid resolver |
| DLT replay hits the exact same error | Root cause unfixed or raw bytes unparseable | Halt replay, classify errors, and fix the data contract |
| Duplicate records in DLT | Crash after DLT publish before source offset commit | Deduplicate using original topic/partition/offset or event ID |
| Batch listener misprocesses records after format error | Failed index unidentified or wrong batch/converter configuration | Test `BatchListenerFailedException`, error headers, and acknowledgment mode |

When investigating, start with the original topic/partition/offset and pinpoint whether the error occurred in the **Kafka deserializer**, **message conversion**, or **business validation**. This order prevents tweaking the error handler when the true root cause lies in schemas/serializers, or vice versa.

## 17. Essential integration tests

In a Kafka test environment, deliberately send records covering:

1. Valid JSON matching type: listener is invoked and completes normally.
2. Syntactically broken JSON: business listener is not invoked; record reaches DLT with raw bytes intact.
3. Valid JSON mismatching model: observe conversion/deserialization error and matching DLT path.
4. Key deserialization failure: DLT producer handles raw key bytes cleanly.
5. Value object deserialized yet validation fails: DLT template serializes regular objects properly.
6. Unsupported schema version error: record quarantined per policy with provenance preserved.
7. Registry timeout: application does not trigger an out-of-policy DLT storm.
8. Nonexistent DLT topic or denied ACL: recoverer reports failure without marking false recovery success.
9. Restart before/after offset commit: no lost records; duplicates may happen yet are handled safely.
10. Replay of a canary record after fixing root cause: record processes cleanly without looping back to DLT.

Inspect key/value bytes, source headers, exception classes, committed offsets, and listener invocation counts. Checking only "the DLT has one record" is insufficient because the DLT might hold a format-altered value or lack original metadata.

## 18. Format-error incident runbook

When the DLT spikes due to deserialization/schema errors, proceed in order:

1. **Scope:** identify cluster, source topic, partitions, group, listener, deployed versions, and error start time.
2. **Confirm error path:** determine whether exceptions originate from the delegate deserializer, Spring message converter, or listener validation.
3. **Inspect payloads:** fetch an authorized DLT sample; inspect raw bytes, original headers, type/schema IDs, and event IDs.
4. **Assess severity:** affected record counts, consumer lag, registry outages, and downstream dependencies.
5. **Contain blasts:** if caused by a release or Schema Registry, roll back or throttle before DLT backlogs spread.
6. **Fix root cause:** update serializers/deserializers, schema compatibility, producer contracts, or registry config.
7. **Test:** replay a small batch in staging or as a controlled canary.
8. **Replay:** select approved records with replay caps, rate limits, and idempotency.
9. **Reconcile:** compare DLT records processed, replays published, business completions, and remaining errors.
10. **Prevent recurrence:** add contract tests, schema evolution policies, alerts, and owner-assigned runbooks.

Never manually edit committed offsets just to "step past" a failing record that has not been saved in the DLT or backed by a business decision. Advancing offsets forward risks dropping record processing; rewinding backward risks replaying large volumes of already-completed data.

## 19. Core principles

For dead-lettering of format errors to work reliably in Spring Kafka:

1. Distinguish errors occurring in the deserializer, converter, and business validation.
2. Use `ErrorHandlingDeserializer` to bring Kafka deserializer errors into container error handling.
3. Use `DefaultErrorHandler` with sensible exception classification; do not futilely retry broken syntax.
4. Use `DeadLetterPublishingRecoverer` with DLT send-result verification; never silently mark failed recovery as success.
5. Design DLT serializers supporting both raw `byte[]` on decode failures and regular objects on listener failures; cover both keys and values.
6. Preserve original provenance, schema metadata, and event IDs for investigation and replay.
7. Separate permanent payload errors from recoverable dependency/Schema Registry outages.
8. Manage offset commits, duplicates, idempotency, and replay loops separately from DLT publishing.
9. Monitor DLT backlogs, publish errors, schema versions, and consumer lag; limit logging of sensitive data.
10. Replay only after the root cause is fixed and verified via canary runs and business reconciliation.

**Conclusion:** dead-lettering for format errors is more than adding a DLT topic. You must ensure the consumer can represent *pre-listener* failures as recoverable records, the DLT retains enough original data for investigation, the publisher has type-accurate serializers, and retry/replay workflows neither lose data nor create loops. When these boundaries are clearly engineered, Spring Kafka can continue consuming despite poison records while preserving evidence to repair data contracts and recover under control.
