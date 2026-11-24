# Handling Deserialization Errors Before the Listener

A Kafka consumer receives keys and values as raw bytes and invokes a deserializer to convert them into the types used by the application. This process happens inside the Kafka consumer's `poll()` loop, before Spring Kafka calls the `@KafkaListener` method.

If bytes are malformed, JSON is invalid, the schema is incompatible, or the deserializer throws an exception, the listener method may never be invoked. Consequently, a `try/catch` inside the listener cannot catch deserialization errors occurring before the listener. Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer, record the failure in the record's headers, and let the container error handler apply retry or dead-letter policies.

This lesson belongs to the **Error Handling** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, mastering topics, partitions, offsets, and consumer groups, alongside serialization, retries, dead-letter topics, transactions, exactly-once semantics, concurrency, and testing for reliable messaging pipelines.

## 1. Deserialization Runs Before the Listener Is Invoked

The record consumption flow normally proceeds in this order:

1. The consumer calls `poll()` to fetch data from the broker.
2. The Kafka client receives the record's key/value bytes.
3. ErrorHandlingDeserializer calls the delegate key/value deserializer to convert bytes into Java types.
4. Spring Kafka passes the deserialized record to the listener container.
5. The container invokes the `@KafkaListener` method.
6. The listener executes business logic and the container manages acknowledgment/commits per configuration.

~~~mermaid
flowchart TD
    A[Kafka broker returns record bytes] --> B[Consumer poll]
    B --> C[ErrorHandlingDeserializer wrapper]
    C --> D[Delegate key/value deserializer]
    D --> E{Deserialization succeeded?}
    E -->|Yes| F[Spring listener container]
    F --> G[@KafkaListener method]
    G --> H[Execute business logic]
    E -->|No| I[Exception and raw bytes]
    I --> J[Metadata in record header]
    J --> K[Container error handler]
    K --> L[Retry or DLT]
~~~

Without a wrapper deserializer, an exception can escape directly from `poll()`. The container then lacks a normal Java record to pass to the listener method. That is the core difference between a deserialization error and a business error inside the listener.

## 2. Distinguishing Deserialization Errors from Listener Errors

The two error types occur at different moments and require different handling:

| Error Type | Timing | Listener Method Called? | Examples |
| --- | --- | --- | --- |
| Deserialization error | During poll, converting bytes into key/value | Usually no | Malformed JSON, incompatible schema, invalid type header |
| Message conversion error | Converting record/payload into listener parameters | May fail before entering method | Cannot convert payload to parameter type |
| Listener/business error | While executing listener code | Yes | Database timeout, business validation failure |
| Downstream error | Calling an external system | Yes | HTTP 503, exhausted connection pool |

Example listener with `try/catch`:

~~~java
@KafkaListener(topics = "order-events", groupId = "billing-service")
public void onOrderEvent(OrderEvent event) {
    try {
        billingService.process(event);
    }
    catch (Exception exception) {
        log.error("Failed to process order event", exception);
    }
}
~~~

The code above only catches exceptions thrown after the listener method is entered. If `JsonDeserializer` throws an exception inside `poll()`, the `event` object is never created and the method is never invoked. Therefore, handling must happen at the deserializer/container layer.

## 3. Why Deserialization Errors Can Stall Consumer Progress

Suppose a partition holds these records:

~~~text
order-events-0

offset 100: valid JSON
offset 101: invalid JSON
offset 102: valid JSON
~~~

The consumer reads offset 100 successfully. When polling record 101, the deserializer fails. If the exception is not converted into a handleable record, the consumer cannot pass that record to the listener normally.

If the error repeats at the same offset, the consumer can keep hitting the same failure and fail to advance to offset 102. This is a poison-record scenario: one bad record can stall partition progress.

Never skip the error arbitrarily. Retain the record information, determine the root cause, and then choose retry, DLT, data repair, or controlled replay.

## 4. What Problem Does ErrorHandlingDeserializer Solve?

`ErrorHandlingDeserializer` is a Spring Kafka wrapper deserializer. It wraps a delegate deserializer such as `StringDeserializer` or `JsonDeserializer`.

When the delegate deserializes successfully, the wrapper returns the normal object. When the delegate throws an exception, the wrapper:

- Captures exception details and the raw bytes of the failing data.
- Attaches error metadata to Kafka record headers using Spring Kafka's mechanism.
- Returns `null` for the failing key/value portion instead of letting the exception escape directly from `poll()`.
- Allows the container error handler to recognize the record with a deserialization error and execute recovery.

~~~text
Kafka Consumer
    |
    v
ErrorHandlingDeserializer
    |
    +-- delegate deserializes successfully --> Object
    |
    +-- delegate throws exception
            |
            +--> store DeserializationException and raw bytes in header
            |
            +--> return null for the failing part
            |
            v
       Container error handling
            |
            +--> retry / recover / DLT
~~~

The wrapper does not repair payloads itself or turn malformed JSON into valid JSON. Its goal is to preserve error details and route the record into an error-handling path that Spring Kafka can manage.

## 5. Configuring ErrorHandlingDeserializer in Spring Boot

A common setup declares the wrapper for both key and value and specifies their respective delegates:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
~~~

In this configuration:

- `key-deserializer` is ErrorHandlingDeserializer.
- `spring.deserializer.key.delegate.class` specifies StringDeserializer to decode keys.
- `value-deserializer` is also ErrorHandlingDeserializer.
- `spring.deserializer.value.delegate.class` specifies JsonDeserializer to decode values.
- `spring.json.value.default.type` supplies the default Java type for JSON values.
- `spring.json.trusted.packages` restricts allowed packages when JsonDeserializer processes type information.

If only values require complex deserialization, you can wrap just the value and keep an appropriate key deserializer. Still, wrapping both sides lets you handle malformed key bytes gracefully if keys use custom serialization/deserialization.

Do not set trusted packages to `*` merely to silence type errors. Restrict it to the event types the consumer actually expects and avoid relying on type headers containing internal classes from another service when type mapping or neutral contracts can be used.

## 6. Configuring the Delegate in Java

You can configure the wrapper in Java when building deserializers programmatically:

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    JsonDeserializer<OrderEvent> jsonDelegate =
        new JsonDeserializer<>(OrderEvent.class);

    ErrorHandlingDeserializer<OrderEvent> valueDeserializer =
        new ErrorHandlingDeserializer<>(jsonDelegate);

    return new DefaultKafkaConsumerFactory<>(
        props,
        new StringDeserializer(),
        valueDeserializer
    );
}
~~~

This example wraps the value deserializer while keeping `StringDeserializer` for keys. To wrap keys too, create an `ErrorHandlingDeserializer` for the key and pass it to the `ConsumerFactory` constructor.

When configuring via constructor, do not also configure conflicting delegates via properties. Pick one clear way to instantiate the delegate and verify the actual `ConsumerFactory` used by the listener container.

## 7. Where Is Exception Metadata Stored?

When deserialization fails, `ErrorHandlingDeserializer` attaches exception details to a dedicated header on the record. Spring Kafka provides constants to access key and value error headers so applications do not need to hard-code header names.

Two cases:

- Key deserialization error: key error metadata is attached to the corresponding header.
- Value deserialization error: value error metadata is attached to the corresponding header.

The error info includes the exception and raw bytes needed to recover or route the record to a DLT. This header is internal metadata supporting Spring Kafka error handling; do not treat it as a stable business header for other services to depend on.

If a listener receives a record with a `null` value, do not immediately assume the producer sent `null`. `null` may result from a deserialization failure captured by `ErrorHandlingDeserializer`. Inspect exception headers before treating `null` as business data.

## 8. Distinguishing Real Null Values from Deserialization Failures

A record can have a `null` value for several reasons:

1. The producer intentionally sent a `null` value.
2. A compacted topic received a tombstone with a non-null key and `null` value.
3. ErrorHandlingDeserializer returned `null` because value bytes failed to decode.
4. Another converter or mapping produced a `null` payload.

Therefore, a `null` payload alone is insufficient to tell whether a record suffered a deserialization error.

When pairing ErrorHandlingDeserializer with a container error handler, Spring Kafka can detect the exception header and route the record to the error handler before invoking the listener method. Consequently, do not assume the listener will receive a `null`-valued record to inspect headers manually.

If implementing a custom error handler or recoverer, you can inspect headers via `ErrorHandlingDeserializer.VALUE_DESERIALIZER_EXCEPTION_HEADER` and `ErrorHandlingDeserializer.KEY_DESERIALIZER_EXCEPTION_HEADER`. Use `ConsumerRecord.headers().lastHeader(...)` to read the corresponding error metadata. Only handle `null` inside the listener itself when your actual configuration lets the record reach the listener and the application clearly defines acknowledgment, retry, and raw-byte retention.

In standard flows, let the container error handler own recovery of failed records. Avoid merely logging and returning from the listener, since the container may treat the call as successful and advance the offset while raw bytes remain unpersisted.

## 9. DefaultErrorHandler Processing Deserialization Exceptions

`DefaultErrorHandler` is the standard error handler in modern Spring Kafka. It supports retries, backoff, and recovery for record listeners, and can be paired with `DeadLetterPublishingRecoverer` to route unprocessable records to a DLT.

Configuration example:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    return handler;
}
~~~

The example above illustrates a one-second backoff and up to two retries after the initial attempt before invoking the recoverer. The error handler can be attached to the listener container factory or configured according to your application's Spring Kafka wiring.

Certain exceptions such as `DeserializationException` are classified as fatal/non-retryable by default in modern versions of `DefaultErrorHandler`, because retrying the same invalid payload rarely heals the data. Verify the classification list for your Spring Kafka version and customize intentionally if a deserialization failure is genuinely caused by a transient dependency.

## 10. Attaching DefaultErrorHandler to the Listener Container Factory

Factory example for a record listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "billing-service",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    billingService.process(event);
}
~~~

`setCommonErrorHandler` attaches the error handler to listener containers created from that factory. If the application has multiple factories, ensure the factory actually used by the listener is properly configured.

Do not just declare a `DefaultErrorHandler` bean and assume every listener automatically uses it if the project defines custom container factories or custom wiring. Verify the effective configuration in the application context.

## 11. Routing Failed Records to a Dead Letter Topic

`DeadLetterPublishingRecoverer` is a common recoverer for publishing failed records to a dead-letter topic (DLT). The DLT retains records unprocessable on the main stream so operations teams can investigate, repair data, or replay them.

Example creating the recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

With the common default setup, the recoverer derives the target topic by appending `.DLT` to the source topic name and preserves the matching partition. The DLT topic must be pre-created or created by an appropriate provisioning mechanism; if keeping partition numbers, the DLT needs enough partitions matching the source topic.

You can customize the destination resolver to route to a dedicated topic name:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("deserialization-errors", record.partition())
    );
}
~~~

This example illustrates routing into a centralized DLT. The target topic must still contain the matching partition index; if partition counts are insufficient, publishing can fail. You can select a different partition or use a topology-appropriate resolver when aggregating errors from multiple topics.

## 12. The DLT Must Preserve Raw Bytes When Deserialization Fails

An important detail: when value deserialization fails, no value object exists; `ErrorHandlingDeserializer` returns `null` and stores raw bytes along with exception metadata. When the recoverer forwards the record to the DLT, Spring Kafka can restore the original bytes from the error metadata so the DLT retains the failing payload.

Therefore, the producer used for DLT publishing must be able to serialize both:

- Normally deserialized objects in other recovery scenarios.
- Raw `byte[]` from records with deserialization failures.

If the DLT template only uses `JsonSerializer` for every value, publishing raw `byte[]` may produce the wrong format or fail. Configure a serializer that supports both `byte[]` and normal objects—for example, `DelegatingByTypeSerializer` with a `ByteArraySerializer` delegate for `byte[]` and `JsonSerializer` for objects.

Skeleton value serializer configuration:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

Place `byte[]` before `Object` in the map so the specific type matches ahead of the catch-all delegate. Key serializer configuration must likewise support both actual key types and raw `byte[]` if key deserialization can fail.

Test the DLT with genuinely malformed payload bytes, then consume the DLT as `byte[]` to confirm raw payloads are preserved intact. Do not merely check that a record exists in the DLT; inspect key/value bytes and exception headers.

## 13. Are Retries Appropriate for All Deserialization Errors?

Not every deserialization error should be retried.

| Cause | Does Retry Help? | Recommended Handling |
| --- | --- | --- |
| Malformed JSON syntax | Usually no | DLT, investigate producer or repair data. |
| Incompatible field type change | Usually no | Check schema evolution and version contracts. |
| Type header points to nonexistent class | Usually no | Use stable type mapping/contracts. |
| Schema Registry temporarily unreachable | Possibly | Bounded retry with backoff; monitor dependency. |
| Custom deserializer fails due to transient config issue | Possibly | Restore dependency/configuration, then retry under control. |
| Truncated payload or corrupted bytes | Usually no | DLT and investigate origin or transport. |

`DefaultErrorHandler` has default exception classifications; if you need to change them, configure retryable/non-retryable types according to actual root causes. Never mark all `DeserializationException` instances retryable, as poison records can block partitions for extended periods.

If an outer wrapper hides the specific cause, inspect the cause chain or `DeserializationException` metadata to classify. Keep retry counts finite and backoffs appropriate.

## 14. Offsets and Poison Records

If a failing record undergoes blocking retries, the partition may wait on that record until processing succeeds or the recoverer finishes. Once the recoverer successfully publishes the record to the DLT and the error handler marks recovery complete, the container can advance the offset per handler and AckMode semantics.

This lets the partition move on to subsequent records, subject to several caveats:

- DLT publishing must succeed before the source record is considered recovered.
- If DLT publishing fails, the error handler may keep retrying recovery per configuration.
- Offset commits must follow container and transaction semantics.
- Uncommitted records can be re-read after a crash or rebalance.
- Never skip a record just to lower lag without preserving raw bytes or an explicit business decision.

A DLT is a holding area for investigating failing records, not an automatic schema-repair engine. To replay, fix the consumer/producer contract or transform records into a supported format before re-injecting them into the proper stream.

## 15. Key Deserialization vs. Value Deserialization Errors

Kafka keys and values use separate deserializers, so failures can happen on either side.

**Key errors:**

- Key can become `null` after the wrapper records the error.
- Raw key bytes are stored in exception metadata.
- The partitioner is no longer involved since the record is already in a partition; the consumer is reading the key from the log.
- The DLT needs a serializer supporting raw `byte[]` for keys.

**Value errors:**

- Value can become `null` after the wrapper records the error.
- Raw value bytes are stored in exception metadata.
- Listeners must not treat `null` as a normal payload if an exception header is present.
- The DLT must retain raw values for analysis/replay.

Do not wrap only the value deserializer if keys can also carry invalid data that needs controlled handling. Conversely, wrapping keys is unnecessary when key contracts are simple, reliable, and key failures are out of scope.

## 16. Batch Listeners and Deserialization Errors

With a batch listener, a single poll can return many records. If one record in the batch fails to deserialize, `ErrorHandlingDeserializer` can preserve the error in that record's headers and return `null` for the failing key/value. Application handling must align with the batch converter and error handler.

If the listener accepts `List<ConsumerRecord<K,V>>`, it can inspect each record and its error headers before running business logic. Never assume every element holds a valid payload.

If the listener accepts converted `List<V>`, verify whether the converter preserves error metadata and raw records. For batches requiring per-record recovery, accepting `ConsumerRecord` usually provides better visibility into topic/partition/offset and error headers.

When a batch listener fails, `BatchListenerFailedException` can pinpoint the failing record index for `DefaultErrorHandler`. However, deserialization errors occurring before listener execution have distinct semantics; test with your exact Spring Kafka version and batch factory, especially when per-record DLT routing is required.

## 17. Observing and Investigating Deserialization Failures

When a record is routed to a DLT, logs and metrics should be sufficient to trace its origin:

- Source topic, partition, and offset.
- Consumer group and client ID.
- Whether the failure occurred on key or value.
- Exception class and cause chain.
- Event ID or correlation ID if extractable from metadata.
- Raw payload size and schema/type version if available.
- Retry attempt count and recovery timestamp.
- Destination DLT topic, partition, and offset.

Do not log entire raw bytes by default, since payloads may contain sensitive data or be excessively large. You can log payload length, a hash, or a controlled snippet per security policy.

Monitor additionally:

- Deserialization failure counts by topic/group.
- DLT publish successes/failures.
- Retry counts and recovery counts.
- Source topic consumer lag.
- Number of records accumulated in the DLT.
- Schema registry or related dependency errors.

If errors spike abruptly after a producer deployment, inspect serializers, schema versions, type headers, and new payload fixtures. If multiple topics fail simultaneously, investigate shared dependencies such as schema registry or deserializer settings.

## 18. Testing Pre-Listener Deserialization Errors

Tests should confirm the listener is not called with an invalid payload and that the record is handled per policy.

Important scenarios:

1. Send valid JSON and verify the listener receives the expected object.
2. Send syntactically invalid JSON and verify ErrorHandlingDeserializer captures the exception.
3. Verify the listener does not process the invalid payload as a valid event.
4. Verify DefaultErrorHandler applies retries/recovery per configuration.
5. Verify the record ultimately arrives in the DLT.
6. Consume the DLT as `byte[]` and compare raw bytes against the originally sent payload.
7. Test key errors and value errors separately.
8. Verify DLT publish failure does not erroneously commit the source offset.
9. Verify subsequent records in the partition proceed after recovery.
10. Test batch listeners if the application uses batch mode.

Unit test example for the delegate deserializer:

~~~java
@Test
void invalidJsonShouldBeCapturedByErrorHandlingDeserializer() {
    JsonDeserializer<OrderEvent> delegate =
        new JsonDeserializer<>(OrderEvent.class);

    ErrorHandlingDeserializer<OrderEvent> deserializer =
        new ErrorHandlingDeserializer<>(delegate);

    Headers headers = new RecordHeaders();
    byte[] invalidJson = "{invalid-json".getBytes(StandardCharsets.UTF_8);

    OrderEvent result =
        deserializer.deserialize("order-events", headers, invalidJson);

    assertThat(result).isNull();
    assertThat(headers.lastHeader(
        ErrorHandlingDeserializer.VALUE_DESERIALIZER_EXCEPTION_HEADER
    )).isNotNull();
}
~~~

This is an illustrative unit test skeleton. Initialize/configure the deserializer according to your Spring Kafka version and assert that the exception header is populated correctly. Only an integration test with a broker proves the container error handler and DLT recoverer are wired end-to-end.

## 19. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `try/catch` in listener misses JSON errors | Exception occurs during poll before listener invocation | Wrap delegate with ErrorHandlingDeserializer |
| Consumer loops on the same offset | Deserialization exception not handed to container error handling | Check EHD and container error handler |
| Listener receives `null` value | Deserialization failure or producer sent `null`/tombstone | Inspect exception header before processing `null` |
| DLT loses original payload | DLT template lacks `byte[]` support or raw bytes not restored | Use type-based serializer and test raw bytes |
| DLT publish fails | Destination topic/partition missing or incompatible serializer | Check DLT topology, ACLs, and template |
| Pointless repeated retries | Invalid schema/format cannot self-heal | Classify as non-retryable and route to DLT |
| Consumer blocked by poison record | Recovery incomplete or handler not advancing offset | Check retries, recoverer, and commit semantics |
| Type header causes deserialization failure | Consumer lacks class or package is untrusted | Use default type/type mapping and stable contracts |
| Unexpected `null` key | Key deserializer failed or key is genuinely `null` | Inspect key exception header |
| Batch mishandles failing record | ConsumerRecord/headers missing or failed index unidentified | Test batch converter and error handling specifically |

## 20. Operational Checklist

Before deploying a consumer to production, verify:

1. Key/value deserializers are wrapped with ErrorHandlingDeserializer where deserialization errors must be managed.
2. Delegate classes are configured properly for both key and value sides.
3. JsonDeserializer has bounded default type/type mapping and restricted trusted packages.
4. Exception headers are checked before treating `null` as valid business data.
5. DefaultErrorHandler is attached to the right listener container factory.
6. Retries/backoff are bounded and error classifications are intentional.
7. DeadLetterPublishingRecoverer has an appropriate destination resolver.
8. DLT topics have sufficient partitions, retention, and ACLs.
9. DLT producer serializers support raw `byte[]` alongside required object types.
10. The DLT preserves raw key/value and investigation metadata.
11. Offsets advance only after successful recovery per chosen semantics.
12. Metrics/logs track deserialization failures, retries, DLTs, and consumer lag.
13. Integration tests cover real malformed payloads against a broker.
14. Runbooks exist for investigating, fixing contracts, and replaying failed records.

Deserialization errors happen before the listener and must therefore be handled at the deserializer and listener container layers. ErrorHandlingDeserializer turns exceptions into metadata attached to the record, enabling DefaultErrorHandler and DeadLetterPublishingRecoverer to retry or route records to a DLT. When raw bytes, DLT serializers, offsets, and retry policies are configured correctly together, consumers can get past poison records while retaining everything needed for investigation and recovery.

