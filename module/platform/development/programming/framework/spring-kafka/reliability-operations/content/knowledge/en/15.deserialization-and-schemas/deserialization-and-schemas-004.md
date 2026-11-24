# Value Deserialization Errors

In Spring Kafka, a **value deserialization error** occurs when the consumer has fetched a record's bytes from Kafka but **cannot convert the value portion into the data type the application expects**. This is one of the easiest errors to stall consumer offset progression because deserialization usually happens **inside the `KafkaConsumer.poll()` call**, before the method annotated with **@KafkaListener** receives the record.

For example, a producer writes JSON with an invalid string for the `quantity` field, while the consumer is configured with `JsonDeserializer` to build `OrderCreated`. If the deserializer throws an exception, the listener has not been invoked yet, so a `try/catch` inside the listener has no chance to catch it. A standard error handler configuration that does not account for poll errors can also cause the same record to be fetched repeatedly while the consumer keeps failing.

In reliable operations, the goal is not merely to "keep the consumer running". The system must **preserve the failing record for investigation**, determine whether the error comes from data or configuration/schema, choose retry/recovery intentionally, and advance offsets only after the error-handling policy completes.

## 1. Where does value deserialization sit in the pipeline?

A Kafka record has a key, value, headers, topic, partition, and offset. Kafka stores keys and values as bytes. When the consumer reads a record, client deserializers convert them from bytes into Java objects.

~~~mermaid
flowchart TD
    A["Producer writes bytes to Kafka"] --> B["Kafka topic / partition"]
    B --> C["KafkaConsumer.poll()"]
    C --> D["Key deserializer"]
    D --> E["Value deserializer"]
    E --> F{"Value readable?"}
    F -->|Yes| G["Spring Kafka listener adapter"]
    G --> H["@KafkaListener processes business logic"]
    F -->|No| I["Deserialization failure"]
    I --> J["ErrorHandlingDeserializer / error handling"]
    J --> K["Recovery: DLT, quarantine, or controlled stop"]
~~~

Distinguish two easily confused error classes:

- **Deserialization error:** the Kafka client/deserializer fails to convert bytes into an object, occurring during or around poll.
- **Message conversion / listener binding error:** the bytes were accepted by the deserializer, but Spring Messaging cannot convert the object to the listener method parameter or subsequent validation fails.

The two errors differ in timing, exception types, and recovery paths. Configuring `ErrorHandlingDeserializer` primarily addresses the first class of errors.

## 2. Illustrative example of a value error

A producer sends the following record:

~~~json
{
  "eventId": "evt-1001",
  "orderId": 456,
  "quantity": "not-a-number"
}
~~~

The consumer expects a Java record:

~~~java
package com.example.orders.events;

public record OrderCreated(
        String eventId,
        long orderId,
        int quantity
) {}
~~~

When `JsonDeserializer` cannot construct the object because the `quantity` field is incompatible, the error may originate from Jackson and get wrapped in a Kafka `SerializationException` or a Spring Kafka exception.

Another record might contain non-JSON bytes:

~~~text
7B 22 65 76 65 6E 74 49 64 22 3A FF FE 00
~~~

Those bytes certainly cannot produce an `OrderCreated` object. Yet the Kafka broker does not validate JSON/Java types when storing records: it simply stores bytes. Thus, a topic can contain records that the current consumer version cannot read.

## 3. Common root causes

| Cause group | Example | Investigation path |
|---|---|---|
| Malformed payload | Truncated string, non-JSON bytes | Safely inspect raw bytes and producer serializer |
| Incompatible schema | Consumer requires a new field while producer uses old format | Check schema/version and compatibility rules |
| Invalid data type | String instead of integer, nonexistent enum value | Inspect JSON fields and object mapping |
| Wrong deserializer config | Using StringDeserializer for Avro bytes | Identify the actual producer serializer |
| Wrong/missing type header | Header points to a class that no longer exists | Check type mappings and JsonDeserializer config |
| Trusted packages | JsonDeserializer does not trust package from type header | Configure proper package allowlist |
| Schema Registry | Cannot fetch schema ID, registry timeout | Check registry, schema ID, credentials, network |
| Class/version mismatch | Consumer class lacks needed field/constructor | Check deployed artifact and contract |
| Poison record | One fixed record always throws an exception | Locate topic-partition-offset and route to recovery |
| Mixed formats | Topic mixes JSON, String, and Avro without envelope | Standardize event contract or use appropriate deserializer |

Do not lump all deserialization errors into "bad JSON". Avro, Protobuf, JSON Schema, and custom binary formats all have their own failure modes. Diagnosis must start from the encoding/serializer the producer actually used.

## 4. Why try/catch inside @KafkaListener is not enough

A listener might contain:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(OrderCreated event) {
    try {
        inventoryService.reserve(event);
    } catch (RuntimeException ex) {
        log.error("Business processing failed", ex);
        throw ex;
    }
}
~~~

This code runs **only after the listener container has received a compatible value**. If `KafkaConsumer.poll()` throws a deserializer error beforehand, `onOrder` is never called.

An improper configuration can create a loop:

~~~text
poll -> deserializer throws -> poll fails
poll -> same record -> deserializer throws -> poll fails
poll -> same record -> deserializer throws -> poll fails
...
~~~

The offset of the offending record has not been handled according to the desired policy. Blindly increasing retry counts will not fix bytes or schemas either.

The standard approach in Spring Kafka is placing **ErrorHandlingDeserializer** as a wrapper around the value deserializer. When the delegate deserializer fails, the wrapper preserves error details in headers so the container/error handler can identify the failed record instead of letting the error escape from poll without proper record context.

## 5. How does ErrorHandlingDeserializer work?

**ErrorHandlingDeserializer** is a Spring Kafka deserializer wrapper. It hands bytes to a configured **delegate deserializer**. If the delegate succeeds, it returns the object normally. If the delegate fails, it records the data and exception details in the corresponding header and informs the container that the record needs error-path handling.

~~~mermaid
flowchart TD
    A["Value bytes from Kafka"] --> B["ErrorHandlingDeserializer"]
    B --> C["Delegate: JsonDeserializer"]
    C --> D{"Deserialize succeeded?"}
    D -->|Yes| E["Return OrderCreated to listener"]
    D -->|No| F["Write DeserializationException info to header"]
    F --> G["Value may be null / fallback object"]
    G --> H["Container and error handler detect failed record"]
    H --> I["Recovery / DLT per configuration"]
~~~

In standard record listener configurations, the container detects the deserialization error header and routes the record through the error handler without invoking the business listener with a broken value. This lets **DefaultErrorHandler** and **DeadLetterPublishingRecoverer** process the failed record per policy.

Key points:

- `ErrorHandlingDeserializer` **does not repair payloads on its own**.
- It **does not automatically publish to a DLT** unless a recoverer is configured.
- It may return null when the delegate fails; never treat every null as a valid business event.
- It gives the error handler sufficient record and exception context.
- When needing a DLT for raw bytes, the recovery producer must be able to serialize byte arrays.

## 6. Configuring ErrorHandlingDeserializer for values with Spring Boot

Example application receiving JSON `OrderCreated`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

Meaning:

- **value-deserializer** selects `ErrorHandlingDeserializer` as the outer layer.
- **spring.deserializer.value.delegate.class** specifies `JsonDeserializer` to convert bytes into objects.
- **spring.json.trusted.packages** permits only required packages if type metadata is used.
- **spring.json.value.default.type** specifies the target class when not using type headers.
- **spring.json.use.type.headers: false** lets this example standardize the target type instead of depending on headers sent by the producer.
- **enable-auto-commit: false** lets the listener container manage offset progression per acknowledgement semantics.

Adjust class names, packages, serializers, and Kafka bootstrap settings for your application. The dotted keys sit under **consumer.properties** to pass through to Kafka client/delegate configuration. If another YAML file or a Java-defined `ConsumerFactory` overrides these values, actual behavior may differ.

Do not set **spring.json.trusted.packages: '*'** just to "make errors go away" without understanding the type headers and producer trust level. Choose explicit package allowlists or type mappings. Type headers and class deserialization are part of the input surface that must be controlled.

## 7. Configuring via Java ConsumerFactory

If the application manages consumer properties and deserializers in code, `ErrorHandlingDeserializer` can wrap the delegate directly:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class ConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {

        Map<String, Object> properties = new HashMap<>();
        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                "inventory-service"
        );
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false
        );

        JsonDeserializer<OrderCreated> delegate =
                new JsonDeserializer<>(OrderCreated.class);

        delegate.addTrustedPackages(
                "com.example.orders.events"
        );

        ErrorHandlingDeserializer<OrderCreated> safeValue =
                new ErrorHandlingDeserializer<>(delegate);

        return new DefaultKafkaConsumerFactory<>(
                properties,
                new StringDeserializer(),
                safeValue
        );
    }
}
~~~

This example builds the deserializer programmatically and passes it directly to the factory, so adding a value deserializer class in properties is unnecessary. When using constructor APIs with a target type, pay attention to whether type headers are enabled; if producers send different type metadata, mappings must align.

Do not configure programmatic properties and property files simultaneously in multiple places without checking precedence. In Spring Boot deployments, you can use `KafkaProperties`/auto-configuration or build properties from environment settings rather than hardcoding bootstrap servers as in this learning example.

## 8. Key deserialization and value deserialization are two separate paths

Every Kafka record can have a key and a value, and each is deserialized independently.

| Aspect | Key | Value |
|---|---|---|
| Consumer property | key-deserializer | value-deserializer |
| ErrorHandlingDeserializer delegate | spring.deserializer.key.delegate.class | spring.deserializer.value.delegate.class |
| Error source | Key bytes | Value bytes |
| Error header | Key error header | Value error header |
| Recovery payload | Original key needs suitable serializer | Original value needs suitable serializer |

If the producer uses `StringSerializer` for keys and `JsonSerializer` for values, you can keep `StringDeserializer` for keys and wrap only the value with `ErrorHandlingDeserializer`. However, if keys also risk deserialization failures, consider wrapping the key as well:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
        spring.json.use.type.headers: false
~~~

Wrapping both does not mean both always fail. It ensures deserialization errors in either key or value have an explicit recovery path. However, the DLT producer will have to support original keys/values whenever the corresponding side fails.

## 9. DefaultErrorHandler and DLT for failed values

`ErrorHandlingDeserializer` lets the container recognize failed records; the error handler decides how to process them. A common choice is **DefaultErrorHandler** combined with **DeadLetterPublishingRecoverer**.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class RecoveryConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> recoveryTemplate) {

        return new DeadLetterPublishingRecoverer(
                recoveryTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );
    }

    @Bean
    DefaultErrorHandler errorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        var handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        return handler;
    }
}
~~~

This is an example of recovery wiring. **KafkaTemplate<Object, Object>** must be constructed with appropriate producer serializers; otherwise, failed records may fail to publish to the DLT.

When record value deserialization fails, the error usually cannot be resolved by feeding the same bytes through the same delegate deserializer repeatedly. Modern versions of `DefaultErrorHandler` treat many deserialization/conversion errors as non-retryable under default classification, though you should never rely on defaults without verifying your version and application policy.

State these principles clearly:

- Permanently broken data/schema → quarantine/DLT, fix producer or contract.
- Schema Registry temporarily unavailable → may need retries with a different strategy or controlled pause, depending on exception classification and outage duration.
- Deployment-wide deserializer misconfiguration → fix configuration; dumping the entire topic into a DLT is likely the wrong choice.
- Single-record data error → record-level recovery, preserve evidence, and continue consuming when safe.

### Attaching the handler to the container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler errorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

Listeners must select this factory by name or rely on an appropriate default bean. If a listener uses a different factory, the error handler above will not cover that record.

## 10. DLT for deserialization errors must preserve raw bytes

This is critical: a record with a value deserialization error does not necessarily have a domain object to republish. When using `ErrorHandlingDeserializer`, Spring Kafka can supply the **raw value bytes** of the failed record to `DeadLetterPublishingRecoverer` for sending to the DLT.

If the recovery producer only has `JsonSerializer` for `OrderCreated`, it may fail to handle a byte array from a failed record properly. The DLT publisher needs to support both valid objects (business errors) and raw bytes (deserialization errors).

The solution is using a serializer that branches by value type. With Spring Kafka versions supporting **DelegatingByTypeSerializer**, you can define a mapping:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

// Illustrates value serializer configuration for the recovery producer.
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<OrderCreated>());

Serializer<Object> recoveryValueSerializer =
        new DelegatingByTypeSerializer(delegates, true);
~~~

`recoveryValueSerializer` must be wired into the DLT's `ProducerFactory`/`KafkaTemplate`. This snippet illustrates only the value serialization part, not a complete producer bean.

Also check the key serializer: if keys can fail deserialization and raw key bytes must go to the DLT, the producer needs key mapping too. If keys are always valid Strings, `StringSerializer` may suffice.

Do not convert broken bytes into a fake JSON string, Base64, or placeholder object without preserving original metadata. Altering the format can destroy the ability to investigate the real root cause and complicate replay after fixing schemas.

## 11. Metadata in DLT records

When publishing to a DLT, `DeadLetterPublishingRecoverer` can add headers describing the original record and exception. Information worth keeping includes:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp and timestamp type when available.
- Consumer group that processed it.
- Exception class, message, and permitted diagnostic details.
- Business event ID or correlation ID if available.

Example:

~~~text
DLT topic: orders.created.DLT
DLT partition: 2
DLT offset: 501

Original topic: orders.created
Original partition: 2
Original offset: 128
Failure type: DeserializationException
Underlying cause: MismatchedInputException
~~~

The DLT offset is a new offset, **not** the original offset. During investigation, combine DLT metadata with the original topic-partition-offset to trace the failing record's bytes.

Exact header names and formats vary across Spring Kafka versions. When code reads headers, prefer existing `KafkaHeaders` or `SerializationUtils` constants/APIs from your exact dependency rather than hardcoding guessed header names.

Exception headers can contain stack traces, class names, and sensitive contents. Control ACLs, retention, and log/export pipelines for the DLT; do not expose full raw payloads or exception messages on dashboards.

## 12. DLT partition count and write permissions

If the recoverer selects a destination with the same partition index as the source record:

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
)
~~~

the DLT must have enough partitions. For instance, if the source topic has partitions 0–7 while the DLT only has partitions 0–3, records from partitions 4–7 cannot be published at the same index.

You can return a negative partition in the destination resolver so `DeadLetterPublishingRecoverer` does not assign an explicit partition and lets the producer pick one, if suitable for operational needs:

~~~java
(record, exception) -> new TopicPartition(
        "shared-deserialization.DLT",
        -1
)
~~~

Confirm this behavior for your version and test against real topics. When not preserving the index, DLT headers must allow tracing back to the original partition.

Minimum permissions typically include:

| Principal | Related permissions |
|---|---|
| Source consumer | READ source topic, consumer group permissions |
| DLT producer | WRITE DLT topic |
| DLT consumer/recovery service | READ DLT topic, consumer group permissions |
| Topic provisioning | CREATE/ALTER only if delegated |

A value deserialization failure cannot be solved by granting `ALL` across the cluster. ACLs must be scoped to the proper resources, and DLT publishing should be monitored separately from business listener failures.

## 13. Null values: null alone does not prove a deserialization error

In some topics, a **null value** is valid. For example, a tombstone in a compacted topic has a null value to represent a key deletion.

Conversely, `ErrorHandlingDeserializer` can also return a null value when the delegate fails deserialization and attaches an exception header.

Therefore, applications should not use a rule like:

~~~java
if (record.value() == null) {
    // Value deserialization definitely failed.
}
~~~

That rule breaks in systems with tombstones, valid null payloads, or fallback records. To detect deserialization failures, check the **exception header** or the error object/exception supplied by the Spring Kafka container.

When handling null values in listeners, confirm the domain contract: on compacted topics, tombstones are usually business conditions needing dedicated handling; if a topic forbids null values, validation can run as a step after deserialization. Do not collapse both cases into the same DLT policy.

## 14. JSON type headers and class mapping

`JsonDeserializer` has several ways to determine the target class:

1. Explicitly configured target class.
2. Type headers sent by the producer.
3. Type mappings or custom type resolvers.
4. Custom deserializers.

Common failures:

- Producer sends a type header pointing to an old class package after refactoring.
- Consumer does not trust the package in the type header.
- A consumer reads multiple event types while pinned to a single target class.
- Producer/consumer run different library versions with incompatible type metadata.
- Event schema changed without maintaining readability of older records.

If a topic contains only `OrderCreated`, you can configure the target type explicitly without relying on type headers. If a topic carries multiple event types, use a stable envelope or controlled type mappings.

Do not set trusted packages to a wildcard as a permanent fix for errors. A wildcard only widens what types can be instantiated; it does not guarantee schema compatibility and increases the risk of processing untrusted data.

## 15. Schema Registry, Avro, Protobuf, and JSON Schema

In systems using Schema Registry, bytes may carry a schema identifier. The deserializer fetches or caches the schema and then constructs objects or generic records according to the format.

Errors can happen at multiple layers:

| Layer | Symptom | What to verify |
|---|---|---|
| Wire format | Wrong magic byte/schema ID | Producer serializer, topic contract |
| Registry access | Timeout, 401/403, DNS failure | Registry URL, auth, network |
| Schema not found | Schema ID does not exist or cannot be retrieved | Registry cluster, retention/schema catalog |
| Compatibility | Incompatible reader/writer schemas | Versions and compatibility policy |
| Specific class | Generated class not found | Classpath, artifact version |
| Logical type | Timestamp/decimal mapping error | Conversion and runtime version |

When the registry is temporarily unavailable, sending every record to the DLT can generate huge numbers of unnecessary records. Distinguish **per-record data errors** from **infrastructure outages affecting the entire consumer**. During a broad outage, controlled stopping or pausing, alerting, and infrastructure recovery may be more appropriate.

`ErrorHandlingDeserializer` remains useful when wrapping those deserializers, but only to route failures onto the recovery path. It does not replace schema governance and compatibility.

## 16. ErrorHandlingDeserializer does not fix schema errors

Some teams configure `ErrorHandlingDeserializer` and consider schema problems solved. In reality, it only ensures errors are **observed and routed properly**.

Address the root causes:

- Define event contracts and versioning.
- Choose backward/forward/full compatibility per consumer/producer needs.
- Enforce schema validation in CI/CD.
- Run producer/consumer compatibility tests before deployment.
- Maintain readability for older records still retained in topics.
- For breaking changes, consider a new topic or explicitly migrated event version.
- Avoid relying on internal Java class names as long-term contracts between services.

For instance, a producer rolls out a new version and sends fields an older consumer does not understand. The older consumer might DLT many records, yet routing to DLT does not restore compatibility between the two services. You must roll back the producer, upgrade the consumer, or design a mutually compatible format across versions.

## 17. When to retry vs. when to route to DLT?

A key principle: **same bytes + same deserializer config + same schema usually yields the same outcome**. Hence, a genuinely malformed payload will usually fail again if retried immediately.

Classify accordingly:

| Cause | Usually appropriate handling |
|---|---|
| Malformed JSON / corrupted bytes | Non-retryable, DLT/quarantine |
| Unsupported event version | DLT or stop to deploy a compatible consumer |
| Type header/class no longer exists | Fix mapping/classpath; consider pausing if widespread |
| Misconfigured JSON trusted packages | Fix allowlist; consider stopping consumer instead of mass DLT |
| Schema Registry outage | Investigate infrastructure, bounded retry or pause |
| Schema ID does not exist | Check registry/source; DLT if permanent data error |
| Single poisoned record | Per-record recovery, preserve bytes |
| Wrong producer serializer topic-wide | Fix producer/contract and plan replay |

No single rule fits all systems. What matters is choosing policies by **root cause** and impact on backlog, DLT capacity, and SLAs.

## 18. Batch listeners require extra care

With a record listener, the Spring Kafka container can usually detect deserialization exception headers and route the failed record to the error handler.

With a **batch listener**, one poll contains multiple records. `ErrorHandlingDeserializer` may produce a record with a null value and an error header, but the batch listener/application may need to **identify the position of the failing record in the batch** and report the failure in a way the batch error handler understands.

Conceptually:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "orderBatchFactory"
)
public void onBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {

        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        // Check the deserialization-exception header using
        // the constant/API of your Spring Kafka version.
        // If the record failed, report the index to the batch error handler.
    }

    batchService.process(records);
}
~~~

In versions supporting **BatchListenerFailedException**, the listener can report the failed record's position so the batch error handler processes the slice properly. Header names/APIs and semantics differ across versions, so consult the Javadoc/documentation of your running dependency.

Do not let a batch listener silently skip records with null values and return normally if null actually indicates a value deserialization failure. That can commit offsets without recording or properly recovering the failed record.

Clarify:

- Whether the batch contains records from multiple partitions.
- How the failed record's index is reported.
- How records before/after the error are retried or committed.
- Whether a transactional listener container is in use.
- Whether DLT publishing preserves raw bytes and original metadata.

## 19. Message conversion failures differ from deserialization failures

Sometimes the value deserializer returns a valid `String` or `byte[]`, while `@KafkaListener` expects `OrderCreated`. Spring's `MessageConverter` attempts to convert the value into the domain object and fails at the adapter layer.

Example:

~~~java
@KafkaListener(topics = "orders.created")
public void onOrder(OrderCreated order) {
    // ...
}
~~~

If the deserializer returns a String containing JSON without an appropriate message converter, the error does not necessarily come from Kafka `JsonDeserializer`. Simply wrapping `StringDeserializer` in `ErrorHandlingDeserializer` will not produce an `OrderCreated` object.

For message conversion failures, inspect:

- What Java type the consumer value deserializer actually returns.
- The listener parameter type.
- Whether `RecordMessageConverter` or `BatchMessageConverter` is configured properly.
- Type headers, content types, and conversion hints.
- Exception types from the listener adapter and error handler.

Do not confuse **DeserializationException** with **MessageConversionException** or **MethodArgumentResolutionException**. All three can prevent the listener from processing a record, yet they require fixes at different layers.

## 20. Deserialization errors when using @RetryableTopic

**@RetryableTopic** is a non-blocking retry mechanism that routes failed records through retry topics. However, deserialization errors happen before the listener and may not suit the same retry pipeline meant for business errors.

A malformed JSON record will not become valid JSON after passing through retry topics. If the error handler/recovery infrastructure routes it straight to the DLT, that behavior usually makes more sense than retrying fruitlessly for minutes.

If using `@RetryableTopic`:

- Identify which consumers read source/retry topics and each container's deserializers.
- Verify which error path `ErrorHandlingDeserializer` feeds deserialization errors into.
- Ensure DLT/retry producers can send raw bytes.
- Do not equate retry-topic topology attempts with `DefaultErrorHandler`'s blocking retry count.
- If the error is a Schema Registry outage, design retry/pause choices around infrastructure.
- Test malformed records in the real topology, not just exceptions thrown by the listener.

Routing records to new topics also alters ordering. If the domain requires per-key ordering, evaluate that impact before applying non-blocking retries to a broad error class.

## 21. Offset commits and record loss risks

After a listener/container handles a failed record, committed offsets can advance if the recovery policy treats the record as handled. That is sound if raw bytes were durably saved to a DLT, yet wrong if recovery publishing failed or the record was skipped without a trace.

Distinguish five states:

1. **Poll succeeded:** consumer received the data.
2. **Deserialization succeeded:** Java value was constructed.
3. **Listener succeeded:** business logic completed.
4. **Recovery succeeded:** failed record was routed to recovery per policy.
5. **Offset commit succeeded:** broker persisted consumer group progress checkpoint.

These five states are not identical. A record may fail deserialization, be sent to the DLT successfully, and only then commit its offset. Another record may be processed successfully by the listener, crash before commit, and get redelivered.

With asynchronous recoverer publishing, configure proper send-result checking. `DeadLetterPublishingRecoverer` offers options in supported versions to fail if the send result errors, such as **setFailIfSendResultIsError(true)**. Check version semantics and timeouts so you never mark a record recovered when it was not actually persisted.

Do not use `consumer.seek()` or `commitSync()` manually to jump past failed records without data-preservation procedures and authorization. That can be data loss disguised as "the consumer stopped throwing errors".

## 22. Quarantine and replay after fixing schemas

A DLT or quarantine topic should preserve raw byte values, source metadata, and error causes. After fixing the deserializer/schema, controlled replay can proceed.

A workflow:

1. Locate failed records by original topic, partition, offset, and event ID.
2. Retrieve raw bytes and headers to inspect the format.
3. Identify the producer version and consumer schema involved.
4. Fix the serializer/deserializer, schema compatibility, or mapping.
5. Test parsing against a copy of the data in a safe environment.
6. Choose the target topic for replay and clarify offset/key semantics.
7. Preserve business event IDs so idempotency works.
8. Replay with rate limiting and monitor successes/failures.
9. Mark records as processed or record a replay audit trail.
10. Monitor DLT backlog and recurring errors.

Do not blindly replay an entire DLT if it contains heterogeneous error types. Some records may have permanently invalid bytes or represent events already completed through another path.

Replay is a business and operational action, not just copying bytes. If the system requires strict ordering, replaying an old record at the tail of a topic may not restore the original processing order.

## 23. Logging and metrics

When a consumer hits value deserialization errors, logs should distinguish source record details from recovery outcomes.

Structured log example:

~~~text
event=kafka_value_deserialization_failed
service=inventory-service
consumer_group=inventory-service
topic=orders.created
partition=3
offset=824
delegate_deserializer=JsonDeserializer
exception_class=DeserializationException
root_cause=MismatchedInputException
recovery_target=orders.created.DLT
~~~

Do not log full payloads if they contain PII, payment details, or secrets. When raw bytes must be kept, store them in a DLT/quarantine protected by ACLs and retention rather than dumping full contents into centralized logs.

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Value deserialization failure rate | Value parsing failures by service/topic |
| Root cause class | JSON/schema/registry/config error |
| DLT publish success/failure | Confirms whether failures were saved for recovery |
| DLT ingress rate | Records entering the DLT |
| DLT lag and oldest record age | Recovery processing backlog |
| Consumer lag | Whether the source topic is advancing |
| Rebalance count | Assignment shifts due to consumer errors/restarts |
| Recovery publisher latency | DLT publish latency |
| Schema Registry error rate | Detects system-wide outages |
| ErrorHandlingDeserializer error count | Detects pre-listener errors |

Metric tags should use low-cardinality values: service, topic, exception group, environment. Do not put event IDs, offsets, keys, raw payloads, or exception messages into metric tags. Keep per-record tracing values in access-controlled logs.

### Detecting mass incidents

If a few isolated records are malformed, per-record DLT may suffice. If after a deployment the consumer suddenly reports deserialization errors for most records across multiple partitions, treat it as a **deployment-wide compatibility or configuration incident**. Continuing bulk DLT routing can waste useful business progress and flood the recovery pipeline.

Alert on error **rates**, start times, deployed versions, topic/schema IDs, and SLA impact.

## 24. Testing against a Kafka broker

To prove the recovery path works, write integration tests using compatible `EmbeddedKafka` or `Testcontainers`. Unit tests of `JsonDeserializer` or services do not prove poll/error-handler/DLT wiring.

Basic scenario:

1. Create a source topic with multiple partitions and a DLT with matching partition counts.
2. Configure `ErrorHandlingDeserializer` with `JsonDeserializer` delegate.
3. Send a valid JSON record and confirm the business listener is invoked.
4. Send a value with malformed bytes to a specific partition.
5. Confirm the listener does not process the malformed record as a valid `OrderCreated`.
6. Confirm the error handler detects `DeserializationException`.
7. Confirm the record reaches the DLT with raw bytes preserved.
8. Verify original topic/partition/offset and exception headers.
9. Confirm the consumer continues to valid records after the error when recovery succeeds.
10. Create a test where the DLT producer fails to publish and confirm recovery is not marked successful.
11. Test valid tombstones/null values if the topic supports them.
12. Verify offset/rebalance/replay behavior per `AckMode`.

Do not rely solely on `Thread.sleep` with fixed delays. Use polling assertions with timeouts to await DLT records or listener execution. In multi-partition concurrent tests, use event IDs or topic-partition-offsets to correlate outcomes accurately.

### Testing schema compatibility

Beyond container integration tests, maintain contract tests using real serialized data from old and new producer versions:

- New producer → old consumer.
- Old producer → new consumer.
- Missing optional field.
- Added unknown field.
- Null/missing field.
- Unknown enum value.
- Schema Registry unavailable.
- Generated class missing from classpath.
- Type header carrying an untrusted class package.

These tests help prevent production failures before malformed records ever get written to Kafka.

## 25. Runbook when a consumer stalls on value deserialization failure

When logs report a consumer cannot deserialize values:

1. Identify service, consumer group, topic, partition, offset, and start time.
2. Check whether the error occurs before the listener or during message conversion.
3. Collect exception class, root cause, delegate deserializer, and schema ID if present.
4. Verify whether the consumer uses `ErrorHandlingDeserializer` or a direct delegate.
5. Check whether the error affects one record or bulk records after a deployment.
6. Inspect producer serializer, event version, and type headers.
7. If using Schema Registry, check URL, auth, schema ID, and health.
8. Inspect `DefaultErrorHandler`, classification, recoverer, and DLT topic.
9. Confirm the `KafkaTemplate`/serializer supports raw bytes when values are corrupted.
10. Verify DLT existence, partition count, retention, and producer WRITE ACLs.
11. Check DLT publish success/failure and committed offsets.
12. Do not manually seek/skip without a data-preservation decision.
13. If caused by a broad deployment/schema error, consider pausing or rolling back per runbook instead of bulk DLT.
14. After fixing, replay with controlled rate and idempotency.
15. Monitor source lag, DLT backlog, and error rates post-recovery.

In incidents affecting multiple consumers, prioritize identifying which producer/dependency/schema version changed recently. Broad configuration errors should not be handled by increasing retries indefinitely or deleting failing records.

## 26. Common mistakes

**Wrapping only try/catch inside @KafkaListener.** The listener never runs when poll value deserialization fails beforehand.

**Using ErrorHandlingDeserializer but forgetting the delegate.** The wrapper needs to know the real deserializer to convert bytes.

**Assuming a null value is a deserialization failure.** Valid tombstones/nulls must be distinguished using exception headers.

**Increasing retries for malformed bytes.** Same data and same schema will usually fail again; retries do not fix payloads.

**Sending every exception to DLT without classifying outages.** Registry downtime or widespread misconfiguration can flood the DLT.

**Overlooking the DLT serializer.** Raw `byte[]` from failed records may fail to send with a serializer meant only for domain objects.

**Putting original offset onto the new Kafka record as the DLT offset.** Kafka assigns a new offset; preserve original metadata via headers.

**Setting trusted packages to a wildcard to dodge errors.** Determine exact target types/type mappings rather than widening trust unnecessarily.

**Committing or seeking past errors before durable recovery.** Can destroy the ability to replay records.

**Watching only source topic consumer lag.** The DLT may be accumulating unresolved failed records.

**Using batch listeners without inspecting exception headers.** Records with null values from deserialization failures may be skipped or treated as valid.

**Replaying DLT without idempotency.** Events may already have been partially processed or duplicated elsewhere.

## 27. Pre-production checklist

**Deserializer and schema**

- [ ] Consumer has a value deserializer compatible with the producer's format.
- [ ] `ErrorHandlingDeserializer` is configured when poll-error recovery is needed.
- [ ] Delegate value deserializer is specified accurately.
- [ ] Type headers, target types, and trusted packages are verified.
- [ ] Compatibility tests exist for schemas and older data versions.

**Recovery**

- [ ] `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` are attached to the real listener container.
- [ ] DLT producer supports both raw bytes and domain objects as needed.
- [ ] DLT topic/partitions/replication/retention and ACLs are provisioned.
- [ ] Recovery publish failures are detected and reported as errors.
- [ ] Offsets do not advance if recovery has not met policy conditions.

**Business and operations**

- [ ] Valid tombstones/nulls are distinguished from deserialization failures.
- [ ] Procedures exist for handling bulk schema/configuration errors.
- [ ] DLT has an owner, dashboard, and replay runbook.
- [ ] Consumers are idempotent when records are redelivered.
- [ ] Logs/metrics include topic-partition-offset, exception, and schema metadata.
- [ ] Integration tests cover malformed bytes, raw DLT payloads, and producer failures.

## 28. Design principles

**Value deserialization errors** occur at the boundary between bytes in Kafka and Java objects in the consumer. When an error occurs inside `KafkaConsumer.poll()`, the business listener cannot handle it with `try/catch`. Wrapping the delegate with `ErrorHandlingDeserializer` lets Spring Kafka bring errors and raw data onto the error/recovery path, where `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` can handle them by policy.

Distinguish isolated data errors from deployment-wide schema/configuration incidents; never retry permanently invalid payloads infinitely; preserve raw bytes and DLT metadata; ensure the recovery producer supports appropriate serializers; and advance offsets only after recovery completes under chosen semantics. Combined with contract testing, observability, DLT replay, and idempotency, the system can continue processing valid records while keeping complete evidence to repair undeserializable ones.
