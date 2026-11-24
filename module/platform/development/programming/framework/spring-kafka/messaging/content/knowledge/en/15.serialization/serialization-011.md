# ErrorHandlingDeserializer

## 1. Why Is ErrorHandlingDeserializer Needed?

Kafka stores keys and values as bytes. When a consumer reads a record, the Kafka client invokes a deserializer to convert bytes into an application data type. If the data is invalid, JSON is malformed, a type header points to a nonexistent class, or the schema is incompatible, the deserializer may throw an exception directly inside `poll()`.

The problem is that the exception occurs before the record is passed to the `@KafkaListener` method. If a consumer uses `JsonDeserializer` directly and deserialization fails, the listener never receives a normal record to handle errors in business logic. `DefaultErrorHandler` also needs a record in order to perform retries or recovery.

Spring Kafka provides `ErrorHandlingDeserializer` (EHD) as a wrapper around the real deserializer. EHD invokes the delegate deserializer; if the delegate throws an exception, EHD catches it, returns `null` for the failed key or value, and attaches error details along with the original raw bytes to record headers. The listener container can then use this information to feed the failure into the error-handling mechanism.

```text
Kafka record (byte[] key/value)
             |
             v
    ErrorHandlingDeserializer
             |
             v
       Delegate deserializer
          /          \
         /            \
   deserialize OK   deserialize error
        |                  |
        v                  v
    object value       returns null
                           |
                           v
                 attaches exception header
                 + preserves original raw bytes
                           |
                           v
                 Listener container / error handler
```

EHD does not fix malformed JSON and does not decide retries on its own. It translates deserialization failures into metadata attached to the record so Spring Kafka can handle them at the container level.

## 2. What Is a Delegate Deserializer?

`ErrorHandlingDeserializer` does not decode JSON, Strings, or Avro itself. It wraps another deserializer, known as the **delegate**. The delegate performs the actual conversion; EHD is responsible for catching exceptions if that conversion fails.

Examples:

| Kafka data | Suitable delegate | Role of EHD |
|---|---|---|
| String key | `StringDeserializer` | Catches unexpected delegate errors and attaches key error metadata |
| JSON value | `JsonDeserializer` | Catches JSON/type-mapping errors and provides value exception headers |
| Byte value | `ByteArrayDeserializer` | Wraps errors from the delegate if any occur |

Separate EHDs can be used for keys and values. In practice, many applications wrap only the value because the key is a simple string; if keys can also fail deserialization, configure EHD for the key accordingly.

## 3. Configuration with Spring Boot application.yml

Suppose the `orders` topic holds JSON for `OrderCreated`:

```java
package com.example.messaging.events;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}
```

The consumer can configure EHD as the outer deserializer and `JsonDeserializer` as the delegate:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging.events
```

In this configuration:

- `value-deserializer` is the `ErrorHandlingDeserializer` wrapper class.
- `spring.deserializer.value.delegate.class` specifies `JsonDeserializer` as the delegate.
- `spring.json.value.default.type` configures the default value type for the JSON delegate.
- `spring.json.use.type.headers: false` instructs the JSON delegate to use the configured type instead of record type headers.
- `spring.json.trusted.packages` restricts the permitted DTO packages.

If the key is also JSON and needs protection against key deserialization errors, configure similarly:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.key.default.type: com.example.messaging.OrderKey
```

If the key is a plain string, keeping `StringDeserializer` directly is usually simpler. Avoid wrapping a deserializer that cannot meaningfully fail unless doing so provides operational value.

## 4. Configuration with Java ConsumerFactory

When constructing a `ConsumerFactory` manually, declare EHD in the Kafka client configuration and the delegate class in properties:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                ErrorHandlingDeserializer.class);
        props.put(ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
                JsonDeserializer.class);
        props.put(JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.messaging.events");

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

`ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS` is the property specifying the delegate for values. For keys, use `ErrorHandlingDeserializer.KEY_DESERIALIZER_CLASS`. JSON delegate properties such as default type and trusted packages are still passed in consumer properties for the delegate to read.

Ensure the listener container factory uses this `ConsumerFactory`. If Spring Boot auto-configures a different factory, listeners might continue using the old deserializer if wiring is ambiguous.

## 5. How Does EHD Handle Errors and Exception Headers?

When the delegate succeeds, EHD returns the object normally. When the delegate throws an exception, EHD constructs a `DeserializationException` containing the original raw bytes and error context, and stores that information in the record's headers.

Two important headers are defined by Spring Kafka in `SerializationUtils`:

| Header constant | Used for |
|---|---|
| `SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER` | Key deserialization errors |
| `SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER` | Value deserialization errors |

The failed key/value is typically `null` in the record passed up to the listener/container layer. Headers let the framework distinguish a `null` caused by a deserialization failure from a legitimate `null` value sent by a producer (if the system permits tombstones or `null` payloads).

Raw bytes are preserved in the error details for diagnostics or forwarding failed records to a dead-letter topic. Because headers can hold the original payload and exception details, never log full headers unconditionally; payloads may contain sensitive data or be very large.

## 6. Record Listeners and Error Handlers

With a record listener, the listener container can inspect exception headers before invoking the listener method. Upon detecting a deserialization error, the container passes the record and exception to `CommonErrorHandler` (typically `DefaultErrorHandler`) for retry or recovery.

Listener example:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

If the value fails to deserialize, `onOrder()` does not receive a valid `OrderCreated` to process. The container processes the exception header through the configured error handler. This allows deserialization errors to participate in the same retry/recovery pipeline as listener processing errors, though the two error classes have different causes and may need different retry policies.

Malformed JSON syntax is usually a data error that retries cannot fix. Retrying the same unchanged data repeatedly can stall the partition and build consumer lag. You can classify deserialization exceptions as non-retryable or cap retries very low before sending to a DLT.

## 7. Configuring DefaultErrorHandler and DeadLetterPublishingRecoverer

EHD supplies the record with exception headers so the error handler can recover it. A common configuration uses bounded retries followed by publishing the failed record to a dead-letter topic (DLT):

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

This example configures two retries after the initial attempt, spaced one second apart. Once retries are exhausted, `DeadLetterPublishingRecoverer` publishes the record to a DLT using default naming or an application-configured destination resolver.

For records that failed deserialization, the recoverer can use the raw bytes stored in the exception header to forward the original data. The producer used to publish to the DLT must therefore be able to serialize both normal payloads and raw `byte[]`. If it only uses `JsonSerializer` for all value types, sending raw bytes may fail or produce unexpected payloads.

In production, configure the DLT template with a serializer suited to multiple data types (such as `DelegatingByTypeSerializer` to handle both `byte[]` and deserialized objects) or use a dedicated template for raw bytes. Also create the DLT topic, set appropriate retention, and establish an investigation/replay procedure.

### Classifying Deserialization Errors

Not all deserialization errors warrant the same retry count. For example:

| Error | Usually appropriate behavior |
|---|---|
| Malformed JSON syntax | Do not retry or retry minimally, then DLT |
| Type header pointing to nonexistent class | Fix contract/type mapping; repeated retries rarely help |
| Package not in trusted packages | Update consumer configuration after verifying data source |
| Incompatible schema/version | Update consumer or deploy compatible schema; preserve raw bytes for reprocessing |
| Transient database error after successful deserialization | Retry with backoff suited to business/infrastructure failures |

You can configure `DefaultErrorHandler.addNotRetryableExceptions(...)` for errors that retries cannot fix. Identify the actual exception wrapped inside `DeserializationException` for your version and test the classification before deploying to production.

## 8. Batch Listeners Must Check Per-Record Errors

Batch listeners receive multiple records in one invocation. If a record fails deserialization, EHD yields a record with a `null` value and the corresponding exception header. Because the listener receives the whole batch, the application must identify which record failed to inform the error handler.

Example receiving a list of `ConsumerRecord`s and throwing `BatchListenerFailedException` at the failed record:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);
        Header errorHeader = record.headers().lastHeader(
                SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);

        if (errorHeader != null) {
            throw new BatchListenerFailedException(
                    "Order value could not be deserialized", index);
        }

        orderService.process(record.value());
    }
}
```

In this example, the listener checks the exception header before accessing `record.value()`. When an error is found, the listener reports the index of the failed record to `DefaultErrorHandler` via `BatchListenerFailedException`. The error handler can commit earlier records and retry/recover from the failing position as configured.

If using a batch listener accepting `List<OrderCreated>` instead of `ConsumerRecord`, also inject batch converted headers via `KafkaHeaders.BATCH_CONVERTED_HEADERS` to inspect errors by matching index. In batch listeners, never assume `null` is always a valid JSON `null`; check exception headers before processing.

## 9. Creating Fallback Objects with FailedDeserializationFunction

In some applications, instead of returning `null` when the delegate fails, you can configure a function to build an object representing the failed payload. EHD supports `FailedDeserializationFunction`, which receives `FailedDeserializationInfo` containing the original data, exception, topic, headers, and whether the error occurred in the key or value.

Example DTO capable of representing either a valid event or an error event:

```java
public record OrderMessage(
        String eventId,
        OrderCreated event,
        boolean deserializationFailed,
        String error) {

    static OrderMessage invalid(FailedDeserializationInfo info) {
        return new OrderMessage(
                null,
                null,
                true,
                info.getException().getMessage());
    }
}
```

Fallback builder function:

```java
public class OrderFailedDeserializationFunction
        implements Function<FailedDeserializationInfo, OrderMessage> {

    @Override
    public OrderMessage apply(FailedDeserializationInfo info) {
        return OrderMessage.invalid(info);
    }
}
```

You can configure the function via `spring.deserializer.value.function` with an implementation class matching the consumer's value type. For keys, use `spring.deserializer.key.function`.

A fallback object lets the listener receive a typed value to execute a custom handling path, such as writing failed events to a quarantine store. However, a fallback does not make the original payload valid and does not replace observing exception headers. If the listener treats fallback objects like normal events, data errors can be masked.

Use fallbacks only when the business model has an explicit error state. When the goal is container-managed retry/DLT, letting EHD return `null` with exception headers for the error handler to process is usually preferable.

## 10. Distinguishing Deserialization Errors from Business Errors

These two error classes occur at different stages:

| Criterion | Deserialization error | Business processing error |
|---|---|---|
| Timing | While converting bytes into key/value, before the listener receives a valid record | After the listener is invoked and starts processing the payload |
| Examples | Malformed JSON, wrong type header, missing class, incompatible schema | Database timeout, business rule violation, downstream API failure |
| Does listener receive valid payload? | No; failed key/value is typically `null` with an exception header | Yes, receives the deserialized object |
| Components involved | `ErrorHandlingDeserializer` | Listener and business services |
| Resolution | Fix serializer/schema/type/configuration or preserve raw bytes for investigation | Appropriate retry, data/state fix, or DLT |

Never infinitely retry a structurally invalid JSON record the way you might retry a database timeout. Conversely, do not immediately send every transient dependency outage to the DLT when retries could recover.

## 11. Preserving Raw Bytes and Securing Failed Data

Raw bytes in exception headers are invaluable for investigating undeserializable records and replaying them after fixing the consumer. However, this data may contain personal information, tokens, or sensitive business data.

In operations:

- Do not log full raw bytes or exception headers at INFO/ERROR level without a data-masking policy.
- Restrict DLT access permissions and retention according to data policies.
- Log sufficient metadata for tracing: topic, partition, offset, timestamp, readable event ID if available, and exception type.
- Do not overwrite failed payloads with fallback objects if raw bytes must be preserved for investigation.
- Before replaying, verify the schema and fixed consumer version can read the data before sending it back to the main topic.

EHD is an error-handling aid, not a security filter or schema registry. Validate payloads and control producer sources independently of enabling EHD.

## 12. Testing ErrorHandlingDeserializer

Tests should cover the happy path, error paths, and recovery:

1. **Valid payload:** send valid JSON and verify the delegate deserializes to the DTO and the listener processes it normally.
2. **Malformed JSON:** send invalid JSON bytes and verify EHD returns `null` for the value and attaches the value deserializer exception header.
3. **Invalid type header:** send a record with an unresolvable type header and verify the exception is recorded according to type-header usage settings.
4. **Key error:** configure EHD for keys, send a malformed key, and verify the key exception header is attached.
5. **Record listener:** verify the container routes deserialization errors to the error handler and the listener does not treat invalid payloads as normal DTOs.
6. **Batch listener:** verify the listener inspects headers and throws `BatchListenerFailedException` with the exact failing index.
7. **Retry and DLT:** verify retry counts, DLT destination, and raw-byte preservation when publishing failed deserialization records.
8. **Fallback function:** verify the function receives `FailedDeserializationInfo` and constructs the expected sentinel object if used.
9. **DLT serializer:** verify the DLT template can send both raw `byte[]` and deserialized payloads.
10. **Sensitive data:** verify logs do not print raw payloads or headers containing protected data.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot version. Use broker/container tests to verify end-to-end that the container detects exception headers and the recoverer publishes to the DLT; unit tests on the delegate alone do not prove the container pipeline works properly.

## 13. Common Errors When Configuring EHD

| Symptom | Possible cause | Resolution |
|---|---|---|
| EHD fails to invoke delegate | Missing `spring.deserializer.value.delegate.class` or wrong class name | Check delegate property and serializer dependencies |
| Listener receives `null` | Deserialization failed and EHD returned `null` | Inspect exception headers; do not assume the producer sent a valid `null` |
| No retry/DLT observed | Container lacks the proper error handler or batch listener skips header checks | Verify listener container factory and record/batch handling |
| DLT publish fails for `byte[]` | Producer template lacks a serializer for raw bytes | Configure a serializer supporting both `byte[]` and normal objects |
| JSON still fails despite default type | Payload/schema mismatch or type headers still take precedence | Check JSON, type headers, default type, and `spring.json.use.type.headers` |
| Consumer lags due to bad records | Unnecessary retries on unrecoverable data errors | Classify exceptions, cap retries, and route to DLT |
| Batch listener misses bad records | Only checks for `null` payload without reading exception headers | Consume `ConsumerRecord`/converted headers and inspect headers per index |

## 14. Selection and Rollout Workflow

1. Identify the actual key/value serializers and deserializers for producers and consumers.
2. Choose matching delegates, such as `StringDeserializer` for keys and `JsonDeserializer` for values.
3. Place `ErrorHandlingDeserializer` as the outer deserializer for any part of the record that can fail.
4. Configure delegates via `spring.deserializer.key.delegate.class` or `spring.deserializer.value.delegate.class`.
5. For record listeners, configure an error handler for retry/recovery; classify unretryable data errors.
6. For batch listeners, inspect exception headers per record and report failing records to the error handler.
7. When using a DLT, configure a template capable of sending both raw bytes and normal payloads.
8. Configure a fallback function only when the application has an explicit error-object model.
9. Test valid payloads, malformed payloads, retries, DLT routing, and replay before deploying.

## 15. Summary

- `ErrorHandlingDeserializer` wraps a delegate deserializer and catches exceptions thrown during deserialization.
- On deserialization failure, EHD returns `null` for the failed key/value and attaches an exception header containing error metadata and raw bytes.
- Configure delegates via `spring.deserializer.key.delegate.class` and `spring.deserializer.value.delegate.class`.
- Record listeners can rely on the listener container to forward errors to `DefaultErrorHandler`; batch listeners must check errors per record.
- `DefaultErrorHandler` paired with `DeadLetterPublishingRecoverer` supports bounded retries and routing failed records to a DLT.
- DLT producers need serializers capable of handling both raw `byte[]` and normal payloads.
- `FailedDeserializationFunction` can construct fallback objects, though it does not replace error observability and raw-data preservation.
- Distinguish deserialization errors from business errors to choose appropriate retries, schema fixes, or DLT handling.

When `ErrorHandlingDeserializer` is configured properly, a Spring Kafka application can bring pre-listener failures into the same observability and recovery pipeline, preserve raw payloads for investigation, and prevent a single malformed record from silently stalling the entire consumer stream.
