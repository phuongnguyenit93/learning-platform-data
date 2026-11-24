# Recovering Original Values to the DLT

When a Kafka consumer fails to deserialize a record, the failure usually occurs **before the business listener receives an object**. For example, a producer sends syntactically invalid JSON, a message has an incompatible schema, or serializer and deserializer disagree. If the system only logs the exception and forwards a record with a null value to the dead-letter topic (DLT), the operations team loses the exact bytes needed to investigate and repair the data.

In Spring Kafka, combining **ErrorHandlingDeserializer** with **DeadLetterPublishingRecoverer** allows forwarding undeserializable records to the DLT while **recovering the original value**—meaning the value bytes received from Kafka before deserialization failed. The DLT retains the failing payload for analysis or replay after fixing schemas, configurations, or application code.

This lesson focuses on payload integrity when handling deserialization failures, and explains the requirements for producer serializers, Kafka headers, DLT consumers, offsets, idempotency, and operations.

## 1. What is the original value?

At the broker layer, a Kafka record consists of key bytes, value bytes, headers, timestamp, and position metadata. The Kafka broker does not require knowing the payload's Java class. The consumer receives bytes and uses a deserializer to convert them into objects.

~~~text
Producer
  |
  | serialize OrderEvent into bytes
  v
Kafka broker
  |
  | topic=orders, partition=2, offset=105
  | value bytes: 7B 22 6F 72 64 65 72 ...
  v
Kafka Consumer
  |
  | JsonDeserializer<OrderEvent>
  +------ success ---------> OrderEvent object
  |
  +------ failure ---------> DeserializationException
~~~

The **original value** in a deserialization error scenario is the byte sequence that was written to Kafka and handed to the consumer's deserializer. It is not necessarily a valid JSON string, nor can it necessarily be converted into the desired Java class.

For example, the producer sends:

~~~text
{"orderId":"O-1001","amount":}
~~~

The JSON above has invalid syntax at the `amount` field. With `JsonDeserializer` for `OrderEvent`, an object cannot be constructed. However, the bytes containing the broken JSON remain highly valuable: operators can spot the mistake and identify which producer or schema caused it.

Clearly distinguish three entities:

| Component | Meaning |
|---|---|
| **Raw value bytes** | Payload received from Kafka, prior to consumer deserialization |
| **Deserialized value** | Java object produced when the deserializer succeeds |
| **DLT record value** | Data serialized by the recoverer's producer and written to the DLT topic |

The goal when recovering the original value is for the DLT record to hold the **original raw bytes** when deserialization fails, rather than leaving an empty value or turning broken data into a fake object.

## 2. Why are deserialization failures hard to handle?

In the normal path, the Kafka client invokes the deserializer inside `consumer.poll()`. With a standard deserializer, if deserialization fails and the exception escapes poll, the listener never receives an object-converted `ConsumerRecord`. The application cannot just use a `try/catch` inside `@KafkaListener` to catch this error.

Example listener:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

If the deserializer throws an error before the method is invoked, the code inside `onOrder()` has no opportunity to inspect the raw value. An improperly configured error handler can also enter a poll error loop on the same record, stalling the partition.

Common failure sources:

- Syntactically broken JSON or truncated data.
- Numeric, enum, or timestamp fields with values unconvertible to Java types.
- Avro, Protobuf, or JSON Schema incompatible with the consumer.
- Schema registry temporarily unreachable.
- Producer and consumer using different formats or serializers.
- Invalid type header, nonexistent class, or mismatched trusted packages configuration.
- Key deserialization failure, even when the value is valid.

Some errors are **permanent** (raw bytes are genuinely invalid), while some may be **transient** (schema registry unavailable). Classify properly to decide between brief retries, DLT recovery, or infrastructure remediation.

## 3. What bottleneck does ErrorHandlingDeserializer solve?

**ErrorHandlingDeserializer** is a Spring Kafka deserializer wrapper. It calls a real delegate deserializer, such as `JsonDeserializer`. When the delegate throws an exception, the wrapper writes the error information and original bytes into a `DeserializationException`-backed header so the listener container/error handler can access the failure.

~~~text
Kafka poll
   |
   v
ErrorHandlingDeserializer
   |
   v
Delegate JsonDeserializer
   |
   +-- succeeds --> return OrderEvent
   |
   +-- fails
          |
          +-- store DeserializationException in header
          |     (exception contains raw bytes)
          |
          +-- return null or configured fallback
          |
          v
Listener container detects deserialization header
          |
          v
Error handler / recoverer
~~~

Key point: the value in `ConsumerRecord` along the error path may be **null** because no object was created. However, **raw bytes are not necessarily lost**; they are carried along via the exception metadata provided by `ErrorHandlingDeserializer`.

Spring Kafka uses dedicated headers for key and value deserialization exceptions. This is internal error-handling metadata, distinct from `DLT_ORIGINAL_TOPIC` and `DLT_ORIGINAL_OFFSET` headers used to trace source position after moving to the DLT.

Do not manually parse a Java-serialized exception header by decoding it as UTF-8. For versions using a serialized exception format, let Spring Kafka handle it or use the corresponding utility from your exact library version. Exception-object headers are not a long-term cross-system exchange format.

## 4. Mechanism for recovering the original value to the DLT

When combining **DeadLetterPublishingRecoverer** with `ErrorHandlingDeserializer`, Spring Kafka versions support using raw data from the deserialization failure info to populate the value of the **`ProducerRecord` sent to the DLT**.

Ideal flow:

~~~text
orders/P2/105
   value bytes = malformed JSON
           |
           v
ErrorHandlingDeserializer
   delegate fails to build OrderEvent
   ConsumerRecord.value() may be null
   DeserializationException holds raw bytes
           |
           v
DefaultErrorHandler
   error is non-retryable or retries exhausted
           |
           v
DeadLetterPublishingRecoverer
   detects value deserialization error
   extracts raw bytes from exception metadata
   sets ProducerRecord.value() = byte[]
           |
           v
DLT Producer (ByteArraySerializer)
           |
           v
orders.DLT/P2/<new offset>
   value bytes = original malformed JSON
~~~

In Spring Kafka versions supporting this recovery capability, the recoverer can restore original bytes into the DLT record value instead of sending null. Exact capabilities, header setup, and simultaneous key/value handling must be verified against your Spring Kafka version.

From a data standpoint, two things must be kept distinct:

1. **Recovered value:** the initial raw bytes, so they can be inspected or re-decoded later.
2. **Source metadata:** original topic/partition/offset, exception class/message, and traceability info.

If the DLT record has the original offset yet its value is null, the goal of recovering the original value has not been met. Conversely, if the value retains the bytes without source metadata, provenance investigation also becomes difficult.

## 5. Configuring ErrorHandlingDeserializer with Spring Boot

Example consumer reading an `orders` topic containing JSON values and String keys:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderEvent
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
~~~

Meaning:

- **value-deserializer** is the `ErrorHandlingDeserializer` wrapper.
- **spring.deserializer.value.delegate.class** specifies `JsonDeserializer` to perform actual deserialization.
- **spring.json.value.default.type** declares the default value type when required type headers are absent.
- **spring.json.trusted.packages** restricts packages allowed to deserialize to avoid trusting uncontrolled classes.
- **enable-auto-commit: false** lets the container manage commit timing per listener/error-handler policy.

`com.example.orders.OrderEvent` is an example class; change it to your real model. When producers use type headers, default type and header usage configuration must align with the project's serialization strategy.

Do not use `*` for trusted packages in production just to bypass deserialization errors; verify producer format, class mapping, and security rules first.

### If the key can also fail deserialization

To handle key failures systematically, use `ErrorHandlingDeserializer` for the key too:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderEvent
        "[spring.json.trusted.packages]": com.example.orders
~~~

When key deserialization fails, the recoverer also needs a DLT producer capable of writing **raw key bytes**. Do not configure `ByteArraySerializer` solely for values and neglect key-failure cases.

## 6. DefaultErrorHandler and DeadLetterPublishingRecoverer

For a listener container not using Kafka transactions, you can combine `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`:

~~~java
@Configuration
public class OrdersErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltKafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        return errorHandler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler ordersErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
~~~

This is a structural example. The application must declare `dltKafkaTemplate` with a suitable producer factory and serializers; having only an error handler is not enough to send failing bytes.

**DefaultErrorHandler** classifies several exceptions as fatal/non-retryable by default, including many deserialization or conversion cases. For malformed data errors, repeated retries rarely help. For transient infrastructure errors, consider bounded retries and recoverability.

When an error is classified as non-retryable, the handler can route the record straight to the recoverer without exhausting the `FixedBackOff` chain. Do not assume every `DeserializationException` will always be retried for the configured retry count.

When a container uses Kafka transactions, post-rollback mechanisms typically involve `AfterRollbackProcessor` and require separate configuration. Do not mechanically apply non-transactional `DefaultErrorHandler` examples.

## 7. The DLT producer's serializer is the deciding factor

This commonly causes operational failures: **normal records** have an `OrderEvent` value, whereas **records failing deserialization** must be written to the DLT as `byte[]`.

If the DLT producer only configures `JsonSerializer` for `OrderEvent`, raw `byte[]` may not be written as expected. If the DLT producer only configures `ByteArraySerializer`, normal records failing inside the business listener (with `OrderEvent` values) may fail to publish.

The producer serving `DeadLetterPublishingRecoverer` must support every runtime type the recoverer can emit:

| Error source | Key in DLT ProducerRecord | Value in DLT ProducerRecord | Serializer requirement |
|---|---|---|---|
| Business listener throws after successful deserialization | String (example) | `OrderEvent` | `StringSerializer`, `JsonSerializer` |
| Value deserialization failed | String (if key valid) | raw `byte[]` | `StringSerializer`, `ByteArraySerializer` |
| Key deserialization failed | raw `byte[]` | `OrderEvent` or `byte[]` depending on value outcome | `ByteArraySerializer` for key, matching serializer for value |
| Both key and value failed deserialization | raw `byte[]` | raw `byte[]` | `ByteArraySerializer` for both key and value |

Spring Kafka's **DelegatingByTypeSerializer** selects a serializer by runtime class. Another option is configuring the recoverer with multiple `KafkaTemplate`s and selecting the matching template by value type in supported versions.

### Example producer factory supporting objects and raw bytes

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    Map<Class<?>, Serializer<?>> keySerializers = new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers = new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(
            OrderEvent.class,
            new JsonSerializer<OrderEvent>());

    return new DefaultKafkaProducerFactory<>(
            props,
            new DelegatingByTypeSerializer(keySerializers),
            new DelegatingByTypeSerializer(valueSerializers));
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

The classes and producer properties above illustrate type-based serializer selection. Adjust value classes, serializer maps, security, bootstrap servers, and API overloads for your exact Spring Kafka version.

Along the value deserialization failure branch:

~~~text
ProducerRecord.value() = byte[]
         |
         v
DelegatingByTypeSerializer
         |
         v
ByteArraySerializer
         |
         v
Kafka DLT preserves raw bytes
~~~

`ByteArraySerializer` writes the received bytes verbatim rather than turning broken JSON into new JSON. That matters when preserving exact byte contents for diagnostics.

### Only one type of DLT record

If a DLT is dedicated solely to deserialization errors and every value is bytes, you can pick `ByteArraySerializer` directly. However, if the same DLT also receives business errors with object values, you need a separate producer path or a serializer supporting multiple runtime types.

Do not configure a one-size-fits-all serializer solely because the source listener declares `OrderEvent`. The Java type sent to the DLT by the recoverer can differ from what the listener receives.

## 8. Reading the DLT with ByteArrayDeserializer

A DLT consumer meant for investigation should generally read **raw bytes**, even when payloads violate schemas. Reusing the source topic's `JsonDeserializer<OrderEvent>` for the DLT is a common mistake: records that failed deserialization once will fail again in the DLT.

Example of configuring an independent consumer reading bytes:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.trusted.packages]": com.example.orders
~~~

In practice, create a dedicated `ConsumerFactory` or listener container factory for the DLT using `ByteArrayDeserializer` for values, rather than altering the application's primary consumer configuration.

Example:

~~~java
@Bean
ConsumerFactory<byte[], byte[]> rawDltConsumerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-dlt-investigation");
    props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new ByteArrayDeserializer(),
            new ByteArrayDeserializer());
}

@Bean
ConcurrentKafkaListenerContainerFactory<byte[], byte[]>
        rawDltListenerFactory(
                ConsumerFactory<byte[], byte[]> rawDltConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<byte[], byte[]>();
    factory.setConsumerFactory(rawDltConsumerFactory);
    return factory;
}
~~~

DLT listener:

~~~java
@KafkaListener(
        topics = "orders.DLT",
        groupId = "orders-dlt-investigation",
        containerFactory = "rawDltListenerFactory")
public void investigate(ConsumerRecord<byte[], byte[]> record) {
    byte[] rawValue = record.value();

    log.warn(
            "DLT record topic={}, partition={}, offset={}, bytes={}",
            record.topic(),
            record.partition(),
            record.offset(),
            rawValue == null ? -1 : rawValue.length);

    failureStore.persistRawRecord(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            rawValue,
            record.headers());
}
~~~

With a DLT containing both business listener failures and deserialization failures, `ByteArrayDeserializer` can still read the bytes stored by Kafka. However, the byte format of business-listener failures is determined by the DLT producer (e.g., JSON), while the bytes of deserialization failures are the restored originals. The DLT consumer must distinguish them or preserve raw bytes without forcing them into one schema.

Do not print entire raw payloads into production logs. Payloads may contain sensitive data, non-UTF-8 bytes, or very large contents. Store safely and display only in access-controlled diagnostic tools.

## 9. Headers indicating a deserialization failure

After the recoverer publishes to the DLT, records can carry failure and origin metadata:

| Header group | Meaning |
|---|---|
| `DLT_ORIGINAL_TOPIC` | Source topic recorded by the recovery mechanism |
| `DLT_ORIGINAL_PARTITION` | Source partition |
| `DLT_ORIGINAL_OFFSET` | Source offset |
| `DLT_EXCEPTION_FQCN` | Exception class at recovery time |
| `DLT_EXCEPTION_MESSAGE` | Error message if provided |
| Key/value exception headers | Distinguishes key vs. value deserialization errors when supported by version |

Constant names, retention of exception headers, and recoverer defaults depend on the Spring Kafka version. In modern versions, `DeadLetterPublishingRecoverer` can add DLT metadata without keeping the Java-serialized `DeserializationException` header as a permanent part of the payload.

During investigation, record separately:

~~~text
current:
  topic: orders.DLT
  partition: 2
  offset: 18

original:
  topic: orders
  partition: 2
  offset: 105

payload:
  type: raw-bytes
  size: 31

failure:
  phase: value-deserialization
  exception: RecordDeserializationException
~~~

The format above is an example application-created audit record, not a Kafka-generated format. Actual exception classes may be `DeserializationException` or another wrapper depending on the processing path.

Do not confuse original offsets with DLT offsets; they belong to separate logs. Original offset is only a reference position, not a business idempotency key.

## 10. Does byte recovery preserve data verbatim?

When the pipeline is configured correctly without custom transformations, the raw `byte[]` retained by `ErrorHandlingDeserializer` can be published by `ByteArraySerializer` to the DLT to preserve the initial bytes.

However, understand the limits:

- If the original producer serialized bad data before sending to Kafka, original bytes reflect only **what was written to Kafka**, not the initial in-memory object on the producer.
- If the application or a custom recoverer alters bytes, the DLT payload may differ from source raw bytes.
- If the DLT producer uses a serializer other than `ByteArraySerializer` for `byte[]`, data can be altered or fail to publish.
- If data is dropped because the Kafka record is too large, retention expired, or publishing failed, having headers does not guarantee bytes were preserved.
- If the key failed, key bytes must also be preserved properly; restoring only the value is insufficient for some workflows.

To verify integrity, compare raw bytes of the source record and DLT record using `Arrays.equals` or an appropriate cryptographic hash:

~~~java
assertThat(dltRecord.value())
        .containsExactly(sourceBytes);
~~~

Direct byte comparison is better than comparing JSON strings because whitespace, encoding, or field-ordering differences can be masked if parsed and re-serialized.

## 11. Distinguishing deserialization failures from business listener failures

These two scenarios require different DLT handling.

### Case A: deserialization failure

~~~text
Kafka bytes
   |
   v
JsonDeserializer
   |
   +-- error, cannot build OrderEvent
   |
   v
ErrorHandlingDeserializer preserves raw bytes
   |
   v
DeadLetterPublishingRecoverer
   |
   v
DLT value = original byte[]
~~~

The business listener never processed the record. After fixing the schema or deserializer, raw bytes from the DLT can be decoded again.

### Case B: business listener failure

~~~text
Kafka bytes
   |
   v
JsonDeserializer succeeds
   |
   v
OrderEvent object
   |
   v
Business listener database error
   |
   v
DeadLetterPublishingRecoverer
   |
   v
DLT value = OrderEvent (written by DLT serializer)
~~~

In Case B, there is no automatic reason for the recoverer to swap the value with original raw bytes from the deserializer, because deserialization succeeded and no deserialization exception metadata exists. If an application requires keeping source bytes **for every error type**, including business errors, you must explicitly design byte preservation or a payload envelope at consume time; do not mistake that for default DLT recoverer behavior.

## 12. What if key deserialization fails?

Keys also pass through the consumer's deserializer. An invalid key can prevent the listener from receiving a record even when the value is valid.

With `ErrorHandlingDeserializer` on the key:

~~~text
key raw bytes:   FF FE 00
value raw bytes: valid JSON

StringDeserializer key -> fails

DLT:
  key   = original key bytes
  value = OrderEvent or bytes depending on value status
~~~

In this setup, the DLT `ProducerRecord` key may be `byte[]` even though the business listener normally uses `String`. The producer serializer must support `byte[]` for keys, as shown with `DelegatingByTypeSerializer`.

If both key and value fail, `byte[]` must be supported for both. A recoverer handling value failures while assuming keys are always `String` can fail during DLT publishing.

Do not use `String.valueOf(key)` to recover key bytes. If the key had broken encoding, converting to `String` can substitute characters or lose original bytes.

## 13. Should deserialization exceptions be retried?

Not all deserialization errors belong to the same group.

| Error type | Chance of self-recovery | Direction commonly considered |
|---|---|---|
| Syntactically invalid JSON | Very low | Early DLT, keep original bytes |
| Unsupported enum/value | Low without code/schema change | DLT or fix consumer then replay |
| Incompatible event schema | Low for current processing attempt | DLT, deploy compatible schema |
| Schema registry temporarily unavailable | Can recover | Bounded retry, monitor dependency |
| Type header points to nonexistent class | Usually needs config fix | DLT or fix class mapping |
| Security or trusted package error | Needs investigation first | Do not broaden trust arbitrarily |

`DefaultErrorHandler` typically treats deserialization and conversion errors as fatal/non-retryable under its default classifier. Check your specific Spring Kafka version's policy and application rules.

Never retry a syntactically invalid record forever. It can block the partition and grow consumer lag with no chance of succeeding. Conversely, if the error stems from a temporarily unavailable external dependency, a short retry or controlled non-blocking retry policy may be reasonable.

## 14. Failed records passing through retry topics and DLT

If the application uses non-blocking retries, records may be forwarded across multiple topics before reaching the DLT. For deserialization errors, be especially careful because payloads may never become Java objects along the main hop.

Points to verify:

- Whether your Spring Kafka version's retry infrastructure supports the error path in use.
- Whether the forwarder preserves raw bytes and deserialization failure metadata across hops.
- Whether every hop's producer can serialize `byte[]`.
- Whether retry-topic consumers hit the same error and recover properly.
- Whether the target DLT preserves original topic, partition, offset, and event correlation.

Do not assume slapping `@RetryableTopic` on a listener makes all pre-listener deserialization failures flow cleanly through the entire retry topology. Recoverability depends on how `ErrorHandlingDeserializer`, the listener container, and recoverers interact in your exact version and setup.

If the primary goal is preserving raw bytes of schema-invalid records, a direct DLT path via `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` is usually easier to control than retrying the same broken data multiple times.

## 15. Replaying original values from the DLT

The DLT stores failed data for handling after fixing the consumer, schema, or producer. During replay, keep raw bytes intact if the goal is re-attempting the fixed deserialization.

A safe workflow:

1. Identify the DLT record by current topic/partition/offset.
2. Read original topic/partition/offset headers and event ID if present.
3. Save raw bytes for reference; do not edit payloads before knowing the root cause.
4. Verify the fixed schema, serializer, and deserializer versions.
5. Check whether the record already caused side effects in other runs.
6. Choose a replay topic or controlled manual processing tool.
7. Publish bytes with `ByteArraySerializer` if preserving exact original payloads.
8. Record replay ID, operator, reason, and timestamp; cap replay attempts.
9. Monitor outcomes and verify no infinite DLT → replay → DLT loop occurs.

Example publishing raw bytes to a replay topic:

~~~java
ProducerRecord<byte[], byte[]> replayRecord =
        new ProducerRecord<>(
                "orders-replay",
                originalKeyBytes,
                originalValueBytes);

rawKafkaTemplate.send(replayRecord);
~~~

This assumes `rawKafkaTemplate` has `byte[]`-compatible serializers for both key and value. Do not copy directly to production without defining partition strategy and ordering.

When replaying to another topic, new offsets are assigned by the broker. Original offset headers are for tracing only and must not be used as offsets to commit for the consumer group on the replay topic.

If the payload itself is broken beyond consumer-side schema fixes, a separate data normalization step may be needed to build a new payload while preserving provenance of the broken original. That is **data repair**, distinct from verbatim raw-byte replay; clearly record before and after versions for auditing.

## 16. Situations where original values are easily lost

### Consumer uses JsonDeserializer directly

If an exception escapes poll before `ErrorHandlingDeserializer` packages details, the listener container may lack a complete recoverable record. Do not add `DeadLetterPublishingRecoverer` while skipping the wrapper configuration.

### DLT producer uses only JsonSerializer

The recoverer prepares to send `byte[]`, yet the producer picks a serializer meant only for `OrderEvent`. The record may fail to publish or get altered. Support `byte[]` on the DLT producer.

### Custom recoverer uses record.value() to build DLT records

When deserialization fails, `record.value()` may be null. If a custom recoverer ignores exception metadata, the DLT receives null and loses raw bytes. Use Spring Kafka's recovery mechanism or handle raw bytes from metadata intentionally.

### DLT consumer reuses JsonDeserializer<OrderEvent>

The DLT consumer hits the deserialization error again and may fail to read the record. For investigative pipelines, use `ByteArrayDeserializer` and parse against schemas only when needed.

### System copies records without copying headers

Raw bytes may survive, while original topic/offset or exception metadata is lost. Preserve event IDs and headers under an explicit policy.

### DLT producer writes without acknowledgement checks

The application may think it sent to the DLT when publishing actually failed. Check send results, retry/recovery failures, and source offset commits.

### DLT retention is too short

Payloads are written properly yet expire before operations investigates. Configure retention to match incident-handling workflows.

## 17. DLT publish failures and offset commits

Forwarding a failed record to a DLT is a Kafka produce operation. It can fail due to unavailable brokers, missing ACLs, nonexistent destination partitions, serializer bugs, oversized records, or timeouts.

When DLT publishing fails, never assume recovery succeeded. Verify whether your Spring Kafka version awaits send results and detects publish errors per recoverer settings; you may need to enable fail-on-send-error or verify send outcomes accordingly.

If the DLT record was published yet the source offset was not committed before the app crashed, the source record can be redelivered and published again. Two DLT records can carry identical raw bytes and original topic/partition/offset with different DLT offsets.

~~~text
orders/P2/105
   |
   +--> orders.DLT/P2/18
   |
   | crash before source commit
   |
   +--> orders.DLT/P2/19

Two DLT records may share the same source.
~~~

Thus, preserving original values aids investigation and **does not automatically guarantee exactly-once**. When handling errors or replaying, use event IDs, content hashes, or provenance tuples to detect duplicates; deduplication decisions must follow business semantics.

## 18. Testing byte recovery with Kafka integration tests

A useful test sends **genuinely invalid bytes** to Kafka and confirms the DLT retains those exact bytes.

Conceptual test example:

~~~java
byte[] invalidJson =
        "{\"orderId\":\"O-1001\",\"amount\":}".getBytes(
                StandardCharsets.UTF_8);

rawProducer.send(
        new ProducerRecord<>(
                "orders",
                "O-1001".getBytes(StandardCharsets.UTF_8),
                invalidJson));

// Wait for main consumer to handle the error and recoverer to publish to DLT.
// DLT consumer uses ByteArrayDeserializer.
ConsumerRecord<byte[], byte[]> dltRecord =
        awaitDltRecord("orders.DLT");

assertThat(dltRecord.value())
        .containsExactly(invalidJson);
~~~

In the example, `rawProducer` and `awaitDltRecord` are application-provided test helpers, not built-in APIs. You can use `EmbeddedKafka` or Testcontainers Kafka to run integration tests. Await conditions with timeouts instead of long fixed sleeps.

Cases to test:

1. Invalid JSON value: DLT value matches the initial bytes, not null.
2. Valid value with business listener failure: DLT producer serializes the object properly.
3. Key deserialization failure: DLT carries the corresponding key bytes.
4. Both key and value fail: DLT preserves both raw byte segments when supported by configuration.
5. DLT producer missing `byte[]` serializer: test detects publish failure rather than silently dropping records.
6. DLT consumer using `ByteArrayDeserializer`: reads failing payloads cleanly.
7. Original topic/partition/offset headers: investigative metadata is preserved accurately.
8. Crash/restart: do not assume only a single DLT record ever exists.
9. Payload with non-UTF-8 bytes: bytes remain intact without decoding and re-encoding.
10. Failed DLT publish: error handler fails/retries properly without falsely committing offsets.

If a test only sends valid JSON and intentionally throws `RuntimeException` inside the listener, it **does not prove** raw-byte recovery on deserialization failure. You must trigger the failure right at the delegate deserializer to test the feature properly.

## 19. Operations and observability

When deserialization errors arise in production, the most critical details are:

- Source topic/partition/offset.
- DLT topic/partition/offset.
- Whether key deserialization succeeded.
- Whether value deserialization succeeded.
- Byte size saved to the DLT.
- Exception class, root cause, and related schema/version.
- Producer application or producer client ID if known.
- DLT publish outcome and recovery failures.
- Number of records sitting in the DLT and investigation wait time.

Recommended log example:

~~~text
eventId=unknown
original=orders/P2/105
dlt=orders.DLT/P2/18
failurePhase=value-deserialization
exception=JsonParseException
originalValueSize=31
dltValueSize=31
recovery=published
~~~

Do not log full raw bytes just to build dashboards. For failing data that may contain PII or credentials, store it in a system with proper retention and access permissions. If displaying partial payloads is needed, apply masking and size limits.

Metrics should count errors by topic and exception category, DLT publish successes/failures, unresolved DLT records, and backlog age. Avoid putting offsets, event IDs, or full payloads in metric labels due to high cardinality.

## 20. Security when storing undeserialized data

Raw bytes can contain unexpected or deliberately malicious data. Keeping them intact in the DLT helps investigation, yet requires protection:

- Give the DLT stricter ACLs than the main topic if payloads contain sensitive data.
- Never auto-parse or execute DLT contents in unsandboxed diagnostic tools.
- Cap display, download, and storage sizes.
- Apply retention per security and compliance policies.
- Never accept arbitrary type headers from untrusted records just to make replay pass.
- Avoid logging serialized exceptions containing environment details, stack traces, or payload contents beyond what is necessary.

The DLT is not exempt from input validation. A record that failed deserialization must still be treated as untrusted data until verified and processed by appropriate mechanisms.

## 21. Common misconceptions

**Listeners can catch all deserialization errors with try/catch.** False. Errors usually occur before the listener is invoked, inside the consumer deserializer.

**A record with value=null means original bytes are lost.** Not necessarily. With `ErrorHandlingDeserializer`, raw bytes can be kept in `DeserializationException` headers for the recoverer to use.

**Using DeadLetterPublishingRecoverer alone suffices to preserve original bytes.** False across configurations. The consumer must preserve deserialization failure info, and the DLT producer must support `byte[]`.

**JsonSerializer can write any raw bytes exactly as received from the broker.** Never assume that. When the goal is preserving `byte[]`, use `ByteArraySerializer` or a runtime-type-dispatching serializer.

**The DLT consumer should use the same JsonDeserializer as the main topic.** Unsuitable for all records. Already-broken payloads will fail deserialization again; `ByteArrayDeserializer` reads raw bytes for investigation.

**Original value means the Java object before the producer serialized it.** False. It means the Kafka record's bytes before consumer deserialization, which may already differ from the producer's original object.

**All deserialization errors should be retried multiple times.** False. Bad payloads or incompatible schemas usually require fixing data or code; retries do not heal them.

**A successful DLT publish means no duplicate records.** False. If the source offset was not committed, the record can be processed and sent to the DLT again.

**Having original topic and offset guarantees replay will always succeed.** False. Source records can expire past retention and payloads may still be malformed; replay needs error handling and idempotency.

## 22. Implementation guide

To recover original values to the DLT reliably:

1. Wrap key/value delegates needing protection with `ErrorHandlingDeserializer`.
2. Classify deserialization errors, routing permanent data failures to the appropriate DLT.
3. Configure `DeadLetterPublishingRecoverer` with provisioned target topics/partitions.
4. Equip the recoverer's `KafkaTemplate` to support both normal objects and raw `byte[]`.
5. When keys can fail, support `ByteArraySerializer` for keys on the DLT producer.
6. Use `ByteArrayDeserializer` in investigative DLT consumers rather than forcing failing payloads into objects.
7. Keep original topic/partition/offset and exception metadata separate from current DLT metadata.
8. Test with intentionally malformed raw bytes and compare byte-for-byte in the DLT.
9. Monitor publish failures, DLT backlog, retention, and access permissions.
10. Design controlled replay and data repair while preserving event correlation and idempotency.

**Recovering original values to the DLT** does not mean repairing bad data instantaneously. It is a mechanism to **avoid losing original evidence** when a consumer cannot deserialize a record. When `ErrorHandlingDeserializer` retains raw bytes and `DeadLetterPublishingRecoverer` sends them through a producer with compatible serializers, operations teams can inspect exact payloads, find schema/format root causes, fix the system, and replay safely. Achieving end-to-end reliability still requires handling offsets, publish failures, duplicates, security, and business recovery workflows.
