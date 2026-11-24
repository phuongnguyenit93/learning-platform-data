# Deserialization Failure

Kafka stores keys and values as bytes. The consumer must decode those bytes with a deserializer before Spring Kafka can pass the record to `@KafkaListener`. If the deserializer cannot understand the data, the record never reaches the listener; therefore, catching exceptions inside the listener method cannot handle this failure.

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer. When the delegate fails, the wrapper preserves the raw bytes and exception in record headers, after which the listener container can route the failed record to `DefaultErrorHandler` or a recoverer such as `DeadLetterPublishingRecoverer`. This lets the consumer keep running while preserving the original data for investigation or replay.

## 1. Where Does Deserialization Failure Happen?

The record consumption flow has these main steps:

```mermaid
flowchart TD
    A[Kafka broker returns record bytes] --> B[Kafka Consumer.poll]
    B --> C[Key / Value Deserializer]
    C --> D{Deserialization succeeds?}
    D -->|Yes| E[Decoded ConsumerRecord]
    E --> F[Spring Message Converter]
    F --> G[@KafkaListener]
    D -->|No, with ErrorHandlingDeserializer| H[Preserve raw bytes + DeserializationException header]
    H --> I[Listener container ErrorHandler]
    I --> J[Retry / Recoverer / DLT]
    D -->|No wrapper| K[Exception escapes poll]
    K --> L[Record never reaches listener; container has no ConsumerRecord to recover]
```

Kafka invokes key/value deserializers during `poll()`. If the delegate throws an exception, Kafka does not return a decoded `ConsumerRecord` to the application. Spring cannot invoke `@KafkaListener` with that record and cannot handle it as an exception thrown inside the listener.

`ErrorHandlingDeserializer` bridges this boundary by:

1. Calling the delegate deserializer to decode the key or value.
2. On success, returning the decoded object as normal.
3. On failure, returning `null` for the failed part and adding a header containing `DeserializationException`.
4. The header retains the cause and raw bytes so the error handler/recoverer can handle the bad record.
5. For a record listener, the container detects the error header and invokes the container error handler; the record is not passed into the listener method.

Failures can occur on the key, the value, or both. Check the corresponding header rather than only checking `record.value() == null`.

## 2. Distinguishing Adjacent Error Types

Not every data-related error is a deserialization error. Pinpointing the exact layer helps choose the right fix.

| Error type | When it happens | Examples | Where to handle |
|---|---|---|---|
| Key/value deserialization | Inside `Consumer.poll()` | Malformed JSON, non-UTF-8 bytes, invalid schema ID. | `ErrorHandlingDeserializer`, container error handler, DLT. |
| JSON type resolution | Inside JSON deserializer | Type header points to a missing class or untrusted package. | Fix type header/mapping/trusted packages; preserve raw bytes and recover if needed. |
| Message conversion | After `ConsumerRecord` is deserialized | Converter cannot convert payload to listener parameter. | Message converter and container error handler. |
| Method argument resolution | When Spring prepares to invoke listener | Incompatible method signature or annotation/header. | Fix method signature or argument resolver. |
| Business processing | Inside `@KafkaListener` | Database timeout, business validation, service exception. | `DefaultErrorHandler`, retry, recoverer, or DLT per business policy. |

Spring Kafka's `DefaultErrorHandler` treats `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException`, and `ClassCastException` as fatal by default. These exceptions go straight to the recoverer on the first failure rather than retrying multiple times, since replaying the same bytes usually does not fix format or type errors.

## 3. Configuring ErrorHandlingDeserializer in Spring Boot

Example application consuming JSON `OrderEvent`, using a String key and JSON value:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
```

Here:

- `key-deserializer` and `value-deserializer` are the `ErrorHandlingDeserializer` wrapper.
- `spring.deserializer.key.delegate.class` specifies the real deserializer for keys.
- `spring.deserializer.value.delegate.class` specifies the real deserializer for values.
- `spring.json.value.default.type` is the fallback type when JSON lacks a suitable type header.
- `spring.json.trusted.packages` restricts packages allowed when the type mapper resolves classes.

If the key is always a String and you do not need key errors routed to a DLT, you can use `StringDeserializer` directly for keys and wrap only the value. If an external producer might send malformed keys, wrap the key as shown in the example.

The `spring.deserializer.*.delegate.class` and `spring.json.*` property names are Kafka/Spring Kafka client properties; when placing them under `spring.kafka.consumer.properties`, keep their exact full names. Do not nest `spring.json` as an arbitrary object or alter dotted property names.

### When the Producer Sends Type Headers

Spring Kafka's `JsonSerializer` can write type information into Kafka headers by default. If the consumer receives events from a compatible Spring producer, the deserializer can use type headers to select the class. In that case, align type mappings and trusted packages on both sides.

If a non-Spring producer does not send type headers, configure `spring.json.value.default.type` as shown to pick the target class. You can set `spring.json.use.type.headers: false` when you always want to use the configured type instead of producer-supplied type headers; only do this when the topic has a single clear payload contract.

## 4. Using ErrorHandlingDeserializer via Java Configuration

If you prefer configuring deserializers directly, you can instantiate wrappers with their delegates:

```java
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

var keyDeserializer = new ErrorHandlingDeserializer<>(
        new StringDeserializer());

var valueDelegate = new JsonDeserializer<>(OrderEvent.class);
valueDelegate.addTrustedPackages("com.example.orders");

var valueDeserializer = new ErrorHandlingDeserializer<>(valueDelegate);
```

Pass these instances into `DefaultKafkaConsumerFactory`:

```java
import java.util.Map;

import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

var consumerFactory = new DefaultKafkaConsumerFactory<String, OrderEvent>(
        consumerProperties,
        keyDeserializer,
        valueDeserializer);
```

Once deserializer instances are supplied to the factory, class settings in consumer properties do not replace the passed-in instances. Either configure delegates directly or let the factory instantiate delegates from properties; do not mix both and assume they merge automatically.

## 5. Configuring DefaultErrorHandler and DeadLetterPublishingRecoverer

For a record listener, the container detects deserialization exception headers and invokes `CommonErrorHandler`. You can use `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` to publish failed records to a DLT:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> dltTemplate) {
    var recoverer = new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + "-dlt", record.partition()));

    // Retryable errors: max 2 retries, 1 second apart.
    // DeserializationException is fatal by default so it is recovered immediately.
    return new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));
}
```

With `FixedBackOff(1_000L, 2L)`, a record gets up to three delivery attempts: the initial attempt plus two retries. However, `DeserializationException` is in `DefaultErrorHandler`'s default fatal set, so the recoverer is called on the first failure; retry backoff mainly applies to other retryable exceptions.

With Spring Boot, declaring a `DefaultErrorHandler` bean is normally picked up automatically by the auto-configured listener container factory. If you build a custom factory, call `factory.setCommonErrorHandler(kafkaErrorHandler)` to ensure listeners use the right handler.

The DLT topic in the example uses the same partition index as the source topic; create the DLT with at least as many partitions and verify write permissions for the recoverer principal. `DeadLetterPublishingRecoverer` attaches headers describing the exception and source record location. The exception header created by `ErrorHandlingDeserializer` is not the sole storage for original data; the recoverer restores raw bytes into the key/value so the DLT keeps the original payload.

### Why Does the DLT Producer Need to Support `byte[]`?

When deserialization fails, `DeadLetterPublishingRecoverer` restores the raw value as `byte[]` so the DLT retains the original data. If `KafkaTemplate` only has `JsonSerializer<OrderEvent>`, publishing the failed record can fail because the serializer receives a byte array instead of an `OrderEvent`.

A producer used for a DLT should support both raw bytes and normal objects. Example using `DelegatingByTypeSerializer`:

```java
import java.util.Map;

import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        Map<String, Object> producerProperties) {

    var keySerializer = new DelegatingByTypeSerializer(Map.of(
            byte[].class, new ByteArraySerializer(),
            String.class, new StringSerializer()));

    var valueSerializer = new DelegatingByTypeSerializer(Map.of(
            byte[].class, new ByteArraySerializer(),
            OrderEvent.class, new JsonSerializer<>()));

    return new DefaultKafkaProducerFactory<>(
            producerProperties, keySerializer, valueSerializer);
}

@Bean
KafkaTemplate<Object, Object> dltTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
```

The serializer map must cover every key/value type that can reach the DLT. The example above supports String keys, raw `byte[]` keys, `OrderEvent`, and raw `byte[]` values. If a topic carries multiple event types, add matching serializers or use a unified wire format. Never force raw bytes through a JSON serializer, as that alters or corrupts the original payload.

## 6. Reading Exception Headers and Raw Bytes

`ErrorHandlingDeserializer` uses separate headers for keys and values. You can inspect headers on `ConsumerRecord` when logging or handling manually:

```java
import org.springframework.kafka.support.serializer.SerializationUtils;

var keyFailure = record.headers().lastHeader(
        SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER);

var valueFailure = record.headers().lastHeader(
        SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);
```

The headers hold serialized exceptions in Spring Kafka's format. To extract the exception, use `SerializationUtils` instead of parsing byte arrays manually:

```java
var exception = SerializationUtils.getExceptionFromHeader(
        record,
        SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER,
        logAccessor);
```

`logAccessor` in this example is the application's `org.springframework.core.log.LogAccessor`. Exception headers can contain stack traces/causes and raw bytes; do not write entire headers or sensitive payloads to production logs. Log topic, partition, offset, exception class, and correlation/event ID if available.

## 7. Distinguishing `null` from Tombstones vs. `null` from Deserialization Failures

On compacted topics, Kafka allows tombstones: records with a key and a `null` value. This is valid data representing key deletion during log compaction.

`ErrorHandlingDeserializer` also returns `null` for the payload part that failed deserialization. Therefore, you must not assume every record with `value() == null` is a poison record.

| Case | `record.value()` | Deserialization exception header | Meaning |
|---|---|---|---|
| Valid tombstone | `null` | Absent | Key deletion event; process according to compacted topic semantics. |
| Malformed JSON value | `null` | Value exception header present | Value deserialization failed. |
| Malformed key | May still have valid value | Key exception header present | Key could not be decoded; preserve raw key for investigation/recovery. |
| Listener intentionally accepts nullable payload | `null` | Absent | Check topic contract and converter before processing. |

When using `ErrorHandlingDeserializer`, the record listener container checks exception headers. If writing a custom batch listener or manual record inspection logic, check the corresponding header rather than relying solely on null checks.

## 8. JSON Deserialization Failure Due to Type Headers or Packages

Some failures stem not from JSON syntax, but from how the Java type is chosen:

### Type Header Contains a Nonexistent Class Name

A Spring producer may write a class name into headers. If the consumer lacks that class, renamed its package, or uses a different DTO, type resolution can fail.

Solutions:

- Use `spring.json.type.mapping` to map stable tokens to classes per service.
- Or disable type headers and configure a default type when the topic carries a single event type.
- Maintain backward compatibility when renaming packages/classes; Java class names should not become long-term wire-format contracts.

Example type mapping:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: order-created:com.example.producer.OrderCreatedEvent
    consumer:
      properties:
        spring.json.type.mapping: order-created:com.example.consumer.OrderCreatedEvent
```

Both services share the `order-created` token while using separate Java classes, as long as the payload is compatible. When multiple event types exist, declare each token/class mapping and test producer-consumer compatibility.

### Trusted Packages Rejected

`JsonDeserializer` checks allowed packages before instantiating objects from type headers. By default, only basic Java packages like `java.util` and `java.lang` are trusted; application event packages must be declared explicitly:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.orders,com.example.shared.events
```

Do not set `*` in production just to silence errors. Wildcards allow deserializing classes from any package specified in a type header and widen the attack surface. Restrict packages or use explicit type mappings/fixed target types instead.

## 9. JSON Deserialization Failure Due to Incompatible Payloads

Common causes:

| Symptom | Possible cause | How to handle |
|---|---|---|
| `Unexpected character` or `JsonParseException` | Producer sent malformed JSON, truncated payload, or non-JSON text. | Inspect raw bytes, encoding, and producer serializer. |
| `MismatchedInputException` | JSON shape differs from target DTO, e.g., object instead of array or string instead of number. | Compare JSON contract with DTO; version events on structural changes. |
| `UnrecognizedPropertyException` | JSON contains a field rejected by the configured mapper. | Inspect `ObjectMapper`; define clear unknown-fields and compatibility policies. |
| `InvalidDefinitionException` | DTO lacks a suitable constructor/creator, or a needed module/serializer is unregistered. | Check DTO, Jackson modules, and `ObjectMapper`. |
| Date/time parsing error | Producer and consumer disagree on format or timezone. | Use ISO-8601, appropriate temporal types, and Jackson Java Time module. |
| Value read as `String` or `byte[]` | Consumer uses wrong deserializer or producer uses a different wire format. | Align serializer/deserializer or configure converter per contract. |
| Incompatible type header | Producer sends a class token/FQCN unknown to the consumer. | Use type mapping or configure a default target type. |

Since Spring Kafka 2.3, JSON-aware components are configured with an enhanced `ObjectMapper` that has compatibility-friendly defaults, including disabling `FAIL_ON_UNKNOWN_PROPERTIES` by default. If the application supplies its own custom `ObjectMapper`, behavior may differ; verify the actual config instead of assuming all unknown fields fail.

## 10. Schema Registry and Avro/Protobuf

With Avro, Protobuf, or JSON Schema, deserialization can fail due to schema IDs, subjects, versions, or Schema Registry connectivity:

- Payload lacks a schema ID matching the wire format.
- Producer and consumer use different serializers/deserializers.
- Subject naming strategy registers the schema under an unexpected subject.
- New schema is incompatible with the reader schema or generated class.
- Schema Registry is unreachable, times out, or returns authentication/authorization errors.
- Consumer lacks the runtime dependency matching the schema format.

Investigation approach:

1. Preserve raw bytes and inspect the wire format before changing code.
2. Identify the schema ID/subject/version written by the producer.
3. Check the registry's subject naming strategy and compatibility mode.
4. Check the consumer's generated classes and runtime libraries.
5. Distinguish permanent data errors from transient Registry connection errors.
6. Check credentials, TLS truststore, DNS, and timeouts when the deserializer calls the Registry.

If the Registry is temporarily unreachable, the exception may be wrapped in `DeserializationException` and classified as fatal by `DefaultErrorHandler` by default. Only configure retries for confirmed transient infrastructure errors; invalid schema data or missing schema IDs will not fix themselves after a few retries.

## 11. Deserialization Errors and Retries: When Should You Retry?

By default, `DefaultErrorHandler` does not retry `DeserializationException`, passing it straight to the recoverer. This is usually the right choice for malformed JSON, wrong type headers, untrusted packages, or incompatible schemas: re-reading the exact same bytes yields the exact same failure.

| Cause category | Does retry help? | How to handle |
|---|---|---|
| Malformed JSON or truncated payload | No | DLT, inspect producer/raw bytes. |
| Wrong class/type mapping | No, unless a deployment/config fix is rolling out within an intentional retry window | DLT or pause consumer to fix config; replay after fixing. |
| Missing trusted package | Usually no | Fix narrow allowlist and replay. |
| Incompatible schema or wrong schema ID | No | Fix schema/producer contract, DLT, and replay. |
| Schema Registry timeout/connection reset | Possibly | Classify the specific cause as retryable, use bounded backoff, and monitor Registry. |
| Message conversion due to wrong DTO contract | Usually no | Fix converter/DTO or version the event. |

To retry transient Registry exceptions, you can adjust `DefaultErrorHandler` classification using `addRetryableExceptions(...)` or `setClassifications(...)`. Inspect the cause chain and ensure only genuinely transient exceptions are retried; marking all `DeserializationException` instances retryable can stall partitions indefinitely on poison records.

Illustrative example only when a dedicated custom exception represents transient Registry failures:

```java
var handler = new DefaultErrorHandler(recoverer,
        new FixedBackOff(1_000L, 3L));

handler.addRetryableExceptions(SchemaRegistryUnavailableException.class);
```

In practice, the deserializer must translate transient Registry failures into an exception type/cause recognized by the classifier. Do not wrap every exception into one generic retryable custom exception.

## 12. Using `failedDeserializationFunction` When a Sentinel Object Is Needed

`ErrorHandlingDeserializer` supports `failedDeserializationFunction`, which receives `FailedDeserializationInfo` and produces a fallback object for the listener. This helps when the application wants to route failures through a separate branch inside the same listener method.

```java
import java.util.function.Function;
import org.springframework.kafka.support.serializer.FailedDeserializationInfo;

public interface Thing {
}

public record BadThing(FailedDeserializationInfo failure) implements Thing {
}

public class FailedThingProvider implements Function<FailedDeserializationInfo, Thing> {

    @Override
    public Thing apply(FailedDeserializationInfo info) {
        return new BadThing(info);
    }
}
```

Attach the provider to the wrapper when constructing the deserializer manually:

```java
ErrorHandlingDeserializer<Thing> wrapper =
        new ErrorHandlingDeserializer<>(delegateDeserializer);
wrapper.setFailedDeserializationFunction(new FailedThingProvider());
```

Here `delegateDeserializer` is a `Deserializer<Thing>` configured for the application's actual wire format and target type.

This is an illustrative pattern; the sentinel type must match the application's model. The listener must recognize the sentinel before running business logic. If the listener treats the sentinel like a normal event, deserialization errors can turn into bogus business data. For most consumers that need a DLT, letting the container error handler deal with bad records is simpler and safer.

## 13. Validator for Deserialized Data

Since Spring Kafka 3.1, `ErrorHandlingDeserializer` can use a `Validator`. If the delegate deserializes successfully yet the object fails validation, the wrapper still creates an equivalent deserialization failure and retains raw data for the error handler.

```java
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.validation.Validator;

var deserializer = new ErrorHandlingDeserializer<>(
        new JsonDeserializer<>(OrderEvent.class));
deserializer.setValidator(orderEventValidator);
```

This validation fits structural checks at the deserialization boundary, such as required fields or payload version. Business rules depending on databases or current state should stay in the service layer and follow business retry policies. Do not confuse `ErrorHandlingDeserializer`'s `Validator` with validating every side effect of the listener.

## 14. Batch Listeners Must Handle Deserialization Failures Explicitly

For record listeners, the container can detect exception headers and invoke the error handler automatically. For batch listeners, the application must inspect headers across the batch and identify the failing record using `BatchListenerFailedException`.

Example listener receiving `ConsumerRecord` to keep metadata and inspect headers:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.commons.logging.LogFactory;
import org.springframework.core.log.LogAccessor;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.support.serializer.SerializationUtils;
import org.springframework.kafka.support.serializer.DeserializationException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersBatchListener {

    private final LogAccessor logAccessor =
            new LogAccessor(LogFactory.getLog(getClass()));

    @KafkaListener(topics = "orders.events", containerFactory = "batchFactory")
    public void listen(List<ConsumerRecord<String, OrderEvent>> records) {
        for (ConsumerRecord<String, OrderEvent> record : records) {
            DeserializationException failure = SerializationUtils.getExceptionFromHeader(
                    record, SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER, logAccessor);
            if (failure == null) {
                failure = SerializationUtils.getExceptionFromHeader(
                        record, SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER, logAccessor);
            }

            if (failure != null) {
                throw new BatchListenerFailedException(
                        "Kafka record cannot be deserialized", failure, record);
            }

            process(record.value());
        }
    }

    private void process(OrderEvent event) {
        // Process valid event.
    }
}
```

In a batch, you must pinpoint the failed record so `DefaultErrorHandler` knows which offset to retry/recover. Throwing a plain exception can trigger fallback behavior that retries the entire batch. For DLT routing, configure `DefaultErrorHandler` with `DeadLetterPublishingRecoverer`; `@RetryableTopic` does not support batch listeners.

If the listener receives `List<OrderEvent>` instead of `ConsumerRecord`, inspect the corresponding `KafkaHeaders.BATCH_CONVERTED_HEADERS` list to check deserialization exceptions by index. Use `SerializationUtils.byteArrayToDeserializationException()` or `SerializationUtils.getExceptionFromHeader()` instead of deserializing headers manually.

## 15. Diagnosing via Logs, Topic, Partition, and Offset

When an error occurs, collect details in order:

1. **Identify the record:** topic, partition, offset, timestamp, key, and consumer group.
2. **Identify the failing field:** key or value exception header.
3. **Read the exception chain:** class, message, and root cause from Jackson, Schema Registry, or custom deserializer.
4. **Preserve raw bytes:** send the bad record to a DLT or inspection tool capable of storing original bytes.
5. **Cross-check the producer:** serializer, content type, schema ID, type headers, and event version.
6. **Cross-check the consumer:** delegate deserializer, target type, trusted packages, type mapping, and `ObjectMapper`.
7. **Check offsets:** confirm whether the record is retrying at the same offset or was recovered/committed.
8. **Fix and replay:** resolve the root cause first, then replay within a controlled scope and rate.

Do not log raw payloads if they contain PII, tokens, or sensitive data. Log a hex prefix or byte size, checksum, event ID, and Kafka coordinates for tracing; store raw payloads in a DLT with proper ACLs and retention.

## 16. Testing Deserialization Failures

Have dedicated tests for each layer and each type of malformed record.

| Scenario | Result to verify |
|---|---|
| Valid JSON | Listener receives the expected `OrderEvent`. |
| Malformed JSON | Listener is not called; error handler receives the record with an exception header. |
| Value deserialization fails | Raw value is preserved and DLT receives exact original bytes. |
| Key deserialization fails | Key failure header is recognized; raw key is not lost. |
| Valid tombstone | `null` value is not mistaken for a deserialization failure. |
| Missing class in type header | Type resolution error is routed to error handler/DLT. |
| Rejected trusted package | Consumer does not instantiate object; raw bytes remain in DLT. |
| Schema Registry temporarily unreachable | Retry happens only if the transient exception is classified as retryable. |
| DLT receives both normal events and raw bytes | Serializer routes `OrderEvent` and `byte[]` properly. |
| Batch contains one bad record | Batch handler identifies exact record/index and handles offsets per policy. |

Integration test examples should read the DLT with `ByteArrayDeserializer` to compare original payloads:

```java
import java.nio.charset.StandardCharsets;

byte[] original = "{not-valid-json".getBytes(StandardCharsets.UTF_8);
// Send raw bytes to source topic using a test producer with ByteArraySerializer.
// Wait for DLT record to appear using a consumer with ByteArrayDeserializer.
assertThat(dltRecord.value()).isEqualTo(original);
```

This is an illustrative assertion. A complete test needs isolated topics/groups, finite-timeout polling for the DLT, and assertions on exception headers, source topic, partition, and offset. Avoid fixed `Thread.sleep` calls to guess when a record has been recovered.

## 17. Common Pitfalls

| Symptom | Cause | How to handle |
|---|---|---|
| Listener is not called and consumer repeats poll errors | Using deserializer directly without `ErrorHandlingDeserializer`. | Wrap key/value deserializers with `ErrorHandlingDeserializer`. |
| `record.value()` is null with no exception header | Could be a valid tombstone or contract-allowed null payload. | Check headers and topic semantics; do not infer solely from null. |
| DLT publish fails on deserialization error | DLT producer only serializes DTOs and lacks raw `byte[]` support. | Use `DelegatingByTypeSerializer` for bytes and objects. |
| Type header points to nonexistent class | Producer and consumer drifted in package/version. | Use stable type mappings or a fixed target type. |
| `The class ... is not in the trusted packages` | Event package is not trusted. | Add specific packages; avoid broad wildcards. |
| JSON with new field breaks consumer | Custom `ObjectMapper` enables strict unknown-property checks or DTO is incompatible. | Check `ObjectMapper`, compatibility, and schema evolution. |
| Avro/Protobuf cannot find schema | Invalid schema ID, subject, or Registry connection. | Check wire format, subject strategy, schema version, and registry. |
| Retries loop on the same bad payload | `DeserializationException` is retried as transient via custom classification. | Mark data errors non-retryable; recover to DLT. |
| Batch listener fails to route exact bad record to DLT | Exception headers unchecked or `BatchListenerFailedException` not thrown. | Inspect each record/header and pinpoint failed record/index. |
| DLT payload differs from original bytes | Raw bytes were re-serialized as JSON/string. | Publish raw `byte[]` using `ByteArraySerializer`. |

## 18. Operational Checklist

- Key/value deserializers are wrapped with `ErrorHandlingDeserializer` on flows requiring bad-data recovery.
- Delegate deserializer and target type match the producer's wire format.
- Trusted packages are restricted to actual packages.
- Type headers and type mappings have a clear producer/consumer contract.
- `DefaultErrorHandler` classifies permanent data errors as non-retryable.
- DLT topic is created with sufficient partitions, retention, and ACLs.
- DLT producer supports both raw `byte[]` and normal objects.
- Batch listeners inspect deserialization exception headers per record.
- Tombstones are distinguished from deserialization failures via exception headers.
- Logs include topic/partition/offset and root cause without leaking sensitive payloads.
- Tests verify raw bytes reach the DLT unaltered.
- There is a procedure to fix the producer/schema before replaying recovered records.

## 19. Key Takeaways

- Deserialization happens inside `Consumer.poll()`, before `@KafkaListener` receives the record.
- `ErrorHandlingDeserializer` wraps the delegate, returns `null` for the failed part, and stores `DeserializationException` plus raw bytes in headers.
- Record listeners are routed by the container to the error handler; the listener never receives the bad record.
- `DefaultErrorHandler` treats `DeserializationException` as fatal by default and calls the recoverer immediately instead of retrying bad data.
- `DeadLetterPublishingRecoverer` can preserve raw bytes in the DLT; the producer needs serializers for both `byte[]` and normal objects.
- JSON type headers, trusted packages, type mappings, DTOs, and `ObjectMapper` are key points to check on JSON deserialization failures.
- Schema Registry errors can be permanent data issues or transient infrastructure issues; retry only explicitly classified transient cases.
- Batch listeners must check exception headers and report the failed record/index via `BatchListenerFailedException`.
- A `null` value is not automatically an error; valid tombstones have no deserialization exception header.
- Preserve raw bytes and Kafka metadata to investigate, fix the root cause, and replay safely.

When deserialization fails, the first priority is preserving the record and pinpointing whether the failure occurred in the key, value, type mapping, schema, or message conversion. `ErrorHandlingDeserializer` brings pre-`poll()` errors into Spring Kafka's error-handling pipeline; `DefaultErrorHandler` classifies failures, and `DeadLetterPublishingRecoverer` stores bad records for inspection. When the DLT retains raw bytes and the system cleanly separates permanent data errors from transient infrastructure failures, the consumer can keep processing without losing evidence of bad events.

## References

- [Spring for Apache Kafka — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — ErrorHandlingDeserializer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/serializer/ErrorHandlingDeserializer.html)
- [Spring Kafka — DeserializationException API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/serializer/DeserializationException.html)
- [Spring Kafka — DeadLetterPublishingRecoverer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html)
