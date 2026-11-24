# Records Failing Before Entering the Listener in Spring Kafka

In Spring Kafka, not every failing record reaches the `@KafkaListener` method body before throwing an exception. Some records fail **right while `KafkaConsumer.poll()` deserializes the key/value**, when Spring converts the payload into the Java type requested by the listener, or when the framework resolves parameters before invoking the method. The typical outcome is that **the listener is never invoked**, even though the record exists in a topic/partition and the consumer may keep hitting the same offset repeatedly.

In the **Deserialization and Schemas** chapter of Spring Kafka Reliability Operations, this is a very important reliability scenario. If handled poorly, a corrupted record (poison pill) can stall a partition, drive up consumer lag, create futile retry loops, or be skipped without a trace. When handled properly, the system logs the error, routes the record to a dead-letter topic (DLT), and continues processing valid records while preserving enough metadata for investigation.

This lesson focuses on the boundary between the Kafka client, Spring Kafka listener container, message converter, and listener method; how to use `ErrorHandlingDeserializer`; how to route errors to `DefaultErrorHandler`/`DeadLetterPublishingRecoverer`; and key considerations around schemas, batch listeners, offsets, and operations.

## 1. Which layers does a record pass through before running @KafkaListener?

A Kafka record travels from `byte[]` on the broker to a domain object across multiple steps:

~~~text
Kafka broker
    |
    | topic / partition / offset / key bytes / value bytes / headers
    v
KafkaConsumer.poll()
    |
    +--> key deserializer
    |
    +--> value deserializer
    |        |
    |        +--> may throw SerializationException
    |
    v
ConsumerRecord<K, V>
    |
    v
Spring Kafka listener container
    |
    v
RecordMessagingMessageListenerAdapter
    |
    +--> message conversion / header mapping
    |
    +--> resolve method arguments
    |
    +--> validation if configured
    |
    v
@KafkaListener method
    |
    +--> business logic
~~~

Where the error occurs determines which mechanism can see the exception and how recovery should work.

For example, invalid JSON manifests differently depending on the stage:

- If `JsonDeserializer` directly throws an exception in poll, `@KafkaListener` has never been invoked.
- If `ErrorHandlingDeserializer` wraps `JsonDeserializer`, the error is attached to the record as exception information so the container has a basis to handle it.
- If deserialization to `String` succeeds but the message converter fails to build `OrderCreated`, the error happens at the conversion/argument resolution layer.
- If the method is invoked and the domain service rejects a negative amount, that is a business error inside the listener.

Do not collapse all four cases into a single retry loop.

## 2. Error types occurring before the listener body

| Stage | Example | Has listener method run? | Handling direction |
|---|---|---|---|
| Key deserialization | Key bytes incompatible with deserializer | No | `ErrorHandlingDeserializer` for key |
| Value deserialization | Malformed JSON syntax, invalid Avro schema ID | No | `ErrorHandlingDeserializer` for value |
| Type resolution | JSON type header points to untrusted class | No | Restrict type mapping and classify error |
| Message conversion | `String` or `Map` cannot convert to `OrderCreated` | Usually no | `CommonErrorHandler` and conversion policy |
| Argument resolution | Method parameter mismatch or missing required data | Usually no | Fix listener contract, classify fatal |
| Pre-invocation validation | Payload constraint fails | Possibly no | DLT/quarantine if permanent data error |
| Business processing | Database loses connection after method runs | Yes | Bounded retry, idempotency |
| Consumer poll/network | Coordinator or broker transient error | No | Container lifecycle and consumer error handling |

A permanent data error will **not** turn valid by re-reading the same bytes hundreds of times. Conversely, being unable to reach a schema registry or dependency over the network can be a transient incident. Classify by actual root cause, not merely the outer wrapper exception name.

## 3. How does a poison pill cause a loop at the same offset?

Suppose partition 2 of topic `orders.events` contains:

~~~text
offset 100: valid JSON
offset 101: truncated JSON bytes
offset 102: valid JSON
offset 103: valid JSON
~~~

If the consumer uses `JsonDeserializer` directly and record 101 throws an exception during poll:

~~~text
poll() reads up to offset 101
          |
          v
JsonDeserializer throws exception
          |
          v
Cannot build valid domain ConsumerRecord
          |
          v
Listener is not invoked
          |
          v
Next poll / improper recovery
          |
          v
Hits offset 101 again
          |
          +--> consumer lag increases
          +--> continuous repeated logs
          +--> records 102, 103 are blocked
~~~

With the Kafka client, a normal deserialization error occurs before Spring has a complete record to pass to the listener. A regular `CommonErrorHandler` cannot arbitrarily treat this as a `ConsumerRecord` listener exception without proper record context. Spring Kafka may log a message recommending configuring `ErrorHandlingDeserializer` to handle this type of failure.

This is why merely writing `try/catch` inside `@KafkaListener` does not solve deserialization poison pills: that code never gets a chance to execute.

Do not handle this by mechanically increasing `max.poll.interval.ms` or changing retry counts. You must make the container **recognize the failed record** and apply a recovery policy that can advance offsets once the record has been safely stored or handled.

## 4. What problem does ErrorHandlingDeserializer solve?

`ErrorHandlingDeserializer` is a Spring Kafka deserializer wrapper. It calls the real **delegate deserializer** to turn bytes into Java objects. If the delegate fails, the wrapper preserves the error details and raw bytes in metadata/headers so the container can detect it and route the record to the error handler.

~~~text
KafkaConsumer.poll()
          |
          v
ErrorHandlingDeserializer
          |
          +--> Delegate JsonDeserializer succeeds
          |             |
          |             v
          |       ConsumerRecord<OrderCreated>
          |             |
          |             v
          |         Listener
          |
          +--> Delegate JsonDeserializer fails
                        |
                        v
              Write DeserializationException info
              to header / record metadata
                        |
                        v
              Container recognizes failure
                        |
                        v
              DefaultErrorHandler / recoverer
                        |
                        v
                  DLT / recovery
~~~

When no fallback function is configured, an undeserializable value typically becomes `null` at the delegate result layer, accompanied by an error header. For record listeners, the container can inspect the deserialization exception header **before invoking the listener** and route the failure to the appropriate handler.

**Do not assume every null payload is a deserialization error.** Kafka permits records with `null` values (tombstones) to signify deleting a key in compacted topics. A valid tombstone does not carry the same deserialization-exception header. Distinguish valid nulls from failed records using error metadata, not just `value == null`.

A fallback function can be configured to produce a replacement value on deserialization failure in certain cases, but this must be an intentional business decision. Never let a fallback silently turn corrupted data into a fake "valid" event.

## 5. Configuring ErrorHandlingDeserializer in Spring Boot

For a String key and JSON `OrderCreated` value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
    listener:
      ack-mode: record
~~~

Meaning:

- `key-deserializer` and `value-deserializer` use the wrapper to catch delegate errors.
- `spring.deserializer.key.delegate.class` selects `StringDeserializer`.
- `spring.deserializer.value.delegate.class` selects `JsonDeserializer`.
- `spring.json.value.default.type` specifies the default event type if aligned with the type-header strategy in use.
- `spring.json.trusted.packages` allows only trusted Java packages.
- `enable-auto-commit: false` lets the container manage offset commits according to acknowledgement mode.

Equivalent configuration in `application.properties`:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
spring.kafka.listener.ack-mode=record
~~~

Exact property names must match the application's Spring Boot/Spring Kafka version. If creating a custom `ConsumerFactory`, configure the wrapper and delegate deserializers properly on the factory actually used by `@KafkaListener`.

### Should both key and value be wrapped?

You may wrap only the value if the contract guarantees keys are always safely decoded. However, **keys can also be corrupted**. If the key deserializer throws directly before the value is processed, the consumer can still hit a poll error loop. Wrapping both key and value gives the error handler the data needed for both error types.

If using Avro or Protobuf, the delegate deserializer need not be `JsonDeserializer`. You can still wrap the real wire-format/schema-registry deserializer inside `ErrorHandlingDeserializer`, as long as the delegate implements the Kafka `Deserializer` API.

## 6. How do errors before and after deserialization differ?

Suppose a topic stores JSON:

~~~json
{"eventId":"evt-100","orderId":"O-100","amount":120}
~~~

The listener expects:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

### Case A: raw bytes fail to parse as JSON

~~~text
{"eventId":"evt-101","orderId":
~~~

`JsonDeserializer` fails right inside poll. `ErrorHandlingDeserializer` stores error details so the container can handle it. `onOrder` never runs.

### Case B: valid JSON but wrong data type

~~~json
{"eventId":"evt-102","orderId":"O-102","amount":"not-a-number"}
~~~

If `OrderCreated.amount` is numeric, object deserialization or conversion may fail, depending on the deserializer and message converter in use. In either case, the listener may not be invoked.

### Case C: valid JSON and types, but violates business rules

~~~json
{"eventId":"evt-103","orderId":"O-103","amount":-50}
~~~

The object constructs successfully. The listener or validation layer then detects the negative amount. This is a domain error, not a deserialization error, and should be classified with a business exception.

### Case D: valid null payload

A tombstone carrying key `O-104` and a `null` value. If a compacted topic uses tombstones, the consumer must have an explicit contract for null payloads. Never send every null to the DLT without checking for a deserialization error header.

## 7. Message conversion and method argument resolution

Deserializers do not always produce domain objects directly. A consumer might deserialize the value into `String` or `byte[]`, and then a Spring Kafka `MessageConverter` converts it to the parameter declared by `@KafkaListener`.

~~~text
Kafka byte[]
   |
   v
StringDeserializer
   |
   v
String payload
   |
   v
Spring MessageConverter
   |
   +--> convert to OrderCreated
             |
             +--> success --> method is invoked
             |
             +--> error -------> error handler
~~~

For example, the listener takes `OrderCreated` while the factory uses a `RecordMessageConverter` that builds objects from JSON. If the payload does not match the type, conversion fails **after poll but before the listener body**. At that point, `ErrorHandlingDeserializer` does not catch it because the delegate deserializer succeeded.

The Spring Kafka container can route conversion, argument resolution, or validation errors to `CommonErrorHandler`. `DefaultErrorHandler` may classify certain exceptions like `DeserializationException`, `MessageConversionException`, `ConversionException`, or `MethodArgumentResolutionException` as fatal/non-retryable depending on version defaults. When building policies, check the actual classifier list and add domain exceptions used in your application.

Do not let outer wrappers turn every exception into a generic `RuntimeException` and retry infinitely. Keep the cause chain intact so you can tell whether the failure occurred in the deserializer, converter, or business logic.

## 8. DefaultErrorHandler and DeadLetterPublishingRecoverer

A common error handler for record listeners:

~~~java
@Configuration
public class KafkaConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

In this example:

- `FixedBackOff(1_000L, 2L)` permits up to two retries after the first attempt for retryable errors.
- `InvalidEventException` represents a business error that should not be retried with the same payload.
- `DeadLetterPublishingRecoverer` receives unrecoverable records and publishes them to the DLT.
- The factory uses the configured `CommonErrorHandler`.

Note: deserialization errors are typically treated as fatal/non-retryable by `DefaultErrorHandler` in modern Spring Kafka versions, though specific behavior can be changed via the classifier. A broken JSON record should usually go to recovery promptly; retrying a few times will not fix the bytes.

`DefaultErrorHandler` handles errors properly only if the container can pass the exception to it. For deserialization errors inside `KafkaConsumer.poll()`, `ErrorHandlingDeserializer` is the essential mechanism that feeds failing record context into the error handler flow instead of letting poll fail repeatedly.

## 9. What payload does the DLT receive when deserialization fails?

When the deserializer fails to create `OrderCreated`, the recoverer cannot emit a valid domain object. Spring Kafka can use the raw bytes saved by `ErrorHandlingDeserializer` to write the original record to the DLT. Hence, the DLT producer must handle two value shapes:

1. A successfully deserialized object, such as `OrderCreated`, where the listener threw a business error.
2. Raw `byte[]` from a record that failed at the deserialization layer.

Diagram:

~~~text
Valid JSON record value
       |
       v
OrderCreated object
       |
       +--> domain error
                |
                v
           DLT value: OrderCreated

Malformed JSON record value
       |
       v
ErrorHandlingDeserializer
       |
       +--> deserialization error
                |
                v
           DLT value: raw byte[]
~~~

If the DLT `KafkaTemplate` uses only a `JsonSerializer` for domain objects, it may fail to preserve raw bytes as intended. Configure a serializer that dispatches by value type or use dedicated `KafkaTemplate` instances as appropriate.

### Conceptual example of a type-based serializer

In Spring Kafka versions supporting `DelegatingByTypeSerializer`, you can prepare a serializer map for value types:

~~~java
Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();

serializers.put(
        byte[].class,
        new ByteArraySerializer()
);

serializers.put(
        OrderCreated.class,
        new JsonSerializer<OrderCreated>()
);

Serializer<Object> dltValueSerializer =
        new DelegatingByTypeSerializer(serializers);
~~~

This example illustrates selecting serializers for `byte[]` and domain objects. When wiring a real `ProducerFactory`/`KafkaTemplate`, use matching generic types, key serializers, Kafka producer properties, and handle additional payload types if the topic carries multiple event classes.

If a DLT is shared across domains, ensure every value type has a matching serializer. Also check header serialization and DLT message size limits, as exception metadata can increase record size.

## 10. DLT topics and partitions must be prepared

By default, `DeadLetterPublishingRecoverer` usually selects `<source-topic>.DLT` with the same partition count as the source.

~~~text
orders.events / partition 0 --> orders.events.DLT / partition 0
orders.events / partition 1 --> orders.events.DLT / partition 1
orders.events / partition 2 --> orders.events.DLT / partition 2
~~~

If the source topic has eight partitions while the DLT only has three, forcing a partition higher than what exists can cause send failures. Provision the DLT with matching partitions or use a destination resolver returning a negative partition (`-1`) so the producer picks a partition automatically.

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        -1
                )
        );
~~~

Partition `-1` does not exist on the broker; here it indicates not pinning a target partition so the producer picks one via Kafka client mechanics.

If DLT publishing fails due to serializer, topic, partition, ACL, or broker issues, recovery must not be treated as safely completed. Ensure publish errors are surfaced and source offsets do not advance as if the failed record were safely stored.

## 11. ErrorHandlingDeserializer and record listeners

With a record listener, the method typically receives the domain object directly:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

If `ErrorHandlingDeserializer` detects a value error, the container can route the exception to the error handler **without invoking `onOrder`**. There is no need to write `try/catch` for JSON parsing inside `onOrder` because the error occurs beforehand.

If `onOrder` throws an error due to the database, the error handler processes that exception according to business retry policy. Both cases share the error handler while differing in error classification and data recovery path.

If you need to customize error logging/routing, do so in the error handler, recoverer, or a dedicated error-handling component. Never turn invalid data into a fake domain object just to invoke the listener method.

## 12. Batch listeners must handle deserialization errors carefully

A batch listener receives multiple records in a single call. When using `ErrorHandlingDeserializer`, records with deserialization errors may be represented with a null value or fallback value alongside a deserialization-exception header, depending on configuration and version.

~~~text
poll batch:
  record 0: valid
  record 1: valid
  record 2: deserialization error, value may be null
  record 3: valid
        |
        v
Batch listener
        |
        +--> detects record 2 failure via header
        |
        +--> throws BatchListenerFailedException(index=2)
        |
        v
DefaultErrorHandler handles the failure per batch policy
~~~

One approach is accepting `List<ConsumerRecord<...>>` for full access to headers and offsets:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-batch",
        containerFactory = "batchFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        // Before calling domain logic, check whether the record
        // has a deserialization-exception header.
        // You can use KafkaUtils.getExceptionFromHeader(...)
        // with SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        // per the Spring Kafka API in use.

        if (hasDeserializationFailure(record)) {
            throw new BatchListenerFailedException(
                    "Invalid record in batch",
                    index
            );
        }

        orderService.process(record.value());
    }
}
~~~

`hasDeserializationFailure` represents logic that retrieves the deserialization-exception header via the appropriate Spring Kafka helper; this is an application extension point. In real implementations, you can use `KafkaUtils.getExceptionFromHeader` with the header name and `LogAccessor` to obtain the `DeserializationException` without manually deserializing Java objects from untrusted headers.

`BatchListenerFailedException` allows reporting the failing record's position in the batch to the error handler. In Spring Kafka versions supporting the overload taking an index, the example above expresses the handling intent. Verify the exact API and batch error-handler semantics of your dependency when implementing.

If a batch listener skips null payloads without checking headers, it may accidentally treat a deserialization failure as a valid tombstone. If it throws a generic exception without pinpointing the failed record, the error handler may have to retry the entire batch, causing valid records before the failure to be reprocessed.

### Distinguishing batch processing failures

If record 2 deserialized cleanly but `orderService.process` throws an exception, catch the business error at that exact index and use `BatchListenerFailedException` to tell the handler which record failed. Preceding records that already succeeded must be idempotent because they can be redelivered depending on commit/recovery policies.

## 13. Schema Registry and schema-based deserialization errors

With Avro or Protobuf, the deserializer may need to read a schema ID from the record and contact Schema Registry or consult a schema cache to decode bytes. Pre-listener failures can include:

- Schema ID does not exist or data was encoded in the wrong format.
- Schema is incompatible with the model expected by the consumer.
- Schema Registry is unavailable due to connection errors.
- Missing Schema Registry credentials/ACLs.
- Type mapping does not match the listener signature.
- Corrupted bytes or producer wrote with the wrong serializer.

The same wrapper exception can stem from different causes. For example, a Schema Registry timeout may be transient, whereas a nonexistent schema ID may be a permanent data error. Classification must rely on root cause and how the delegate deserializer reports failures.

A basic setup wraps the Avro deserializer with `ErrorHandlingDeserializer` just like JSON, replacing `delegate.class` with your library's corresponding Avro deserializer. Do not copy `spring.json.*` properties onto an Avro/Protobuf delegate that does not understand them.

For schema-based data, ensure you:

1. Establish an appropriate schema compatibility policy.
2. Version event contracts.
3. Monitor Schema Registry availability and caching.
4. Test new producers against running consumers.
5. Distinguish permanent contract errors from transient registry/network errors.
6. Preserve raw bytes and metadata if records must go to a DLT.

A valid schema does not prove an event is valid for business logic. An order with a negative amount can still conform to the schema yet be rejected by domain validation.

## 14. Type headers and deserialization safety

Spring Kafka's `JsonDeserializer` can use type information in Kafka headers to determine the Java class. If a producer sends a bad type header or a header is spoofed, deserialization may be rejected before the listener.

Safety principles:

- Restrict `spring.json.trusted.packages` strictly to event packages actually needed.
- Never use a wildcard trusting all classes unless data is completely controlled.
- For topics with a single event type, consider configuring an explicit default type and disabling arbitrary type headers.
- Use schema/type mapping allowlists for multi-event topics.
- Never deserialize native Java objects from untrusted sources.
- Never take arbitrary class names from payloads as types to instantiate.
- Grant least-privilege Kafka ACLs to producers writing to topics.

A record failing due to an untrusted type header should not be "fixed" by opening trusted packages to everything just to silence the error. That can weaken system security. Inspect the producer contract and source principal instead.

## 15. Error classification and retry limits

Failing before the listener does not mean every error is non-retryable. Separate the groups:

| Error type | Self-heals on retry with same bytes? | Typical policy |
|---|---|---|
| Truncated/malformed JSON | No | DLT/quarantine |
| Nonexistent schema ID | Usually no, needs producer/registry fix | DLT and investigation |
| Untrusted class/type header | Should not retry arbitrarily | Quarantine, verify contract |
| Incompatible type conversion | Usually no | DLT or fix converter/contract |
| Permanent validation failure | No | DLT, fix data |
| Transient Schema Registry disconnect | Possibly | Bounded retry and alerting |
| Transient database disconnect in listener | Possibly | Blocking/non-blocking retry with backoff |
| Converter configuration bug | Usually does not self-heal | Fix application, limit retries |
| Valid tombstone | Not an error | Handle per contract |

`DefaultErrorHandler` can use a classifier to avoid retrying permanent data errors. For errors worth waiting to recover, set bounded attempt counts and durations; never let a single record hold up a partition indefinitely.

If an error happens inside the delegate deserializer due to a transient dependency, evaluate whether retrying actually helps before routing to DLT. For some systems, pausing the consumer and restoring the dependency is better than dumping batches of valid records into the DLT.

## 16. Offsets, acknowledgements, and duplicate windows

When a record skips the listener and routes to a recoverer, offset behavior remains crucial.

~~~text
record offset 200: valid --> listener succeeds
record offset 201: broken JSON --> ErrorHandlingDeserializer
                                      |
                                      v
                                  DLT publish
                                      |
                                      +--> succeeds
                                      |       |
                                      |       v
                                      |   container marks recovered
                                      |
                                      +--> fails
                                              |
                                              v
                                      not safely recovered
~~~

If DLT publishing succeeds and the error handler treats the record as recovered, the container can advance the offset per ack/error-handler policy. If DLT publishing fails, the source offset should not be committed as though the data were saved.

There is a duplicate window: DLT publishing succeeds, then the application stops before committing the source offset. When another consumer picks up the partition, offset 201 may be read again and sent to the DLT a second time. Hence, DLT consumers and replay tools need idempotency.

If a listener already performed database side effects before a conversion/processing error occurred elsewhere, records can be redelivered. Use event IDs, unique constraints, or an inbox/processed-events table to prevent duplicate processing.

`AckMode` (`RECORD`, `BATCH`, or `MANUAL`) governs when the container commits offsets; it **cannot fix broken JSON bytes**. Choose ack mode and error handler together to control the exact moment a failing record is skipped/recovered.

## 17. Logs and metrics for diagnosing pre-listener errors

When the listener method does not run, logs inside that method do not appear either. Observe at the consumer container and error handler layers.

Record:

- Consumer group ID.
- Original topic, partition, and offset.
- Key in a safely redacted or hashed form.
- Exception class and error code.
- Error type: key deserialization, value deserialization, conversion, or validation.
- Producer version/schema version if available.
- DLT destination and publish outcome.
- Attempt count and processing duration.
- First and last error timestamps.

A structured log:

~~~text
event_type=kafka_record_rejected
group=order-service
topic=orders.events
partition=2
offset=201
stage=value_deserialization
exception=RecordDeserializationException
action=publish_dlt
destination=orders.events.DLT
~~~

Exception names in the log are illustrative; Spring Kafka may wrap errors under different classes depending on origin and version.

Do not log full raw bytes, secrets, or arbitrary headers. Corrupted payloads can contain sensitive data or control characters causing log forging. Cap message lengths and sanitize fields written to logs.

Monitoring signals:

| Signal | Meaning |
|---|---|
| Deserialization failure rate | Records that cannot be decoded |
| Conversion failure rate | Payloads failing conversion to listener parameter |
| DLT publish rate | Failed records routed out |
| DLT publish errors | Records failing safe persistence to DLT |
| Consumer lag by partition | Whether a poison pill is blocking a partition |
| Rebalance count | Whether consumer assignments churn during errors |
| Schema registry error rate | Whether the issue is a registry infrastructure failure |
| Failed record size | Unusual or oversized payloads |
| Exception classification | Permanent vs. transient error |
| Oldest DLT record age | How long failed records have been sitting |

Some metrics must be added by the application; Kafka/Micrometer metric names and availability vary by version and exporter.

## 18. Investigation runbook when @KafkaListener is not invoked

Follow these steps to analyze an incident:

1. **Confirm the record exists.** Identify topic, partition, offset, and consumer group.
2. **Check pre-listener logs.** Look for `SerializationException`, `DeserializationException`, `MessageConversionException`, type mapping, or schema registry errors.
3. **Determine whether key or value failed.** Key and value deserializers can fail independently.
4. **Check the actual deserializer.** Is `ConsumerFactory` using `ErrorHandlingDeserializer` or `JsonDeserializer` directly?
5. **Inspect the delegate.** Does wire format match JSON/Avro/Protobuf and the right type/schema?
6. **Check headers/type mapping.** Are trusted packages, default type, and contracts aligned?
7. **Check the converter.** Is conversion from `String`/`Map` to the event class happening before listener invocation?
8. **Classify root cause.** Permanently corrupted bytes or transient dependency/schema registry failure?
9. **Check the error handler.** Is `CommonErrorHandler` registered on the right listener factory?
10. **Check the DLT.** Does the topic exist, does the serializer accept raw bytes, and are ACLs and partitions valid?
11. **Verify offsets.** Was the record recovered per policy or is it still blocking the partition?
12. **Monitor post-recovery.** Are consumer lag and deserialization error rates dropping?

Do not rush to reset offsets to bypass a poison pill. Skipping without a DLT or audit trail can lose critical business events. Intervene on offsets manually only under controlled procedures after deciding what data must be preserved.

## 19. Practical failure scenarios

### Listener does not run while consumer lag rises

Check deserializer exceptions in poll, group assignment, and converters. If the same offset fails repeatedly, wrap the deserializer with `ErrorHandlingDeserializer` and configure recovery rather than infinitely scaling concurrency.

### Container reports it cannot handle SerializationException directly

This indicates the failure occurred before a `ConsumerRecord` reached the error handler. Use `ErrorHandlingDeserializer` with the properly formatted delegate so the failure can be represented on a record/header and recovered.

### Key fails deserialization while value is valid

If only the value deserializer is wrapped, key errors still prevent poll from returning a record. Consider wrapping both key and value; the DLT producer must also support raw key bytes when original failure data needs to be kept.

### Listener receives null and misprocesses it

Distinguish valid tombstones from nulls caused by `ErrorHandlingDeserializer` carrying exception headers. In batch listeners, inspect each record and error position before calling domain services.

### Misconfigured message converter

If the consumer deserializes `String` cleanly while the listener expects `OrderCreated` and the converter is wrong, fix the message converter/type mapping. This is not an error recoverable by retrying the same payload.

### Schema Registry loses connectivity

Separate transient registry failures from nonexistent schema IDs. Avoid dumping batches of valid records into the DLT during brief registry outages when bounded retry/backpressure is more sensible.

### DLT publishing fails due to raw bytes

Check the DLT producer's value/key serializers. It must accept `byte[]` from failed deserialization records, not just JSON objects.

### DLT publishing succeeds yet duplicates appear

The consumer may have crashed between publishing to the DLT and committing the source offset. Use event IDs and idempotent mechanisms to control duplicates; do not assume cross-topic recovery is end-to-end exactly once.

## 20. Pre-production test scenarios

An integration test suite should cover:

| Input | Expectation |
|---|---|
| Valid JSON matching contract | Listener invoked once in normal flow |
| Truncated JSON | Listener does not run; error handler receives failure; DLT stores raw bytes |
| Bad key bytes | Key error caught without stalling the partition indefinitely |
| Syntactically valid JSON with wrong field type | Deserialization/conversion error classified and recovered |
| Type header outside trusted packages | Class trust not blindly expanded; record handled safely |
| Tombstone null value | Handled per contract, not mistakenly treated as a poison pill |
| Validation error | Domain exception classified non-retryable |
| Temporary database outage | Bounded retry with backoff |
| Missing DLT or missing ACL | Recovery reports error, does not mark false success |
| Object-only DLT serializer | Verifies raw-byte handling or catches serializer gap |
| Crash after DLT publish before offset commit | Redelivery possible; replay/idempotency remains safe |
| Batch with a failed record in the middle | Exact failed index handled and already-processed records protected |

Tests should use embedded Kafka/Testcontainers or an integration environment matching the application's version; the goal is proving the full path from bytes through consumer and error handler to the DLT. A unit test calling the listener method directly cannot test failures raised before the method runs.

## 21. Configuration and operations checklist

- Identify whether failures occur in poll/deserializer, conversion/argument mapping, or inside the method.
- Configure `ErrorHandlingDeserializer` for key/value delegates exposed to bad data.
- `Delegate.class` matches the actual wire format and Schema Registry.
- Trusted packages/type mappings are restricted.
- `MessageConverter` and method signatures share a clear contract.
- Never confuse null tombstones with null values from deserialization errors.
- `DefaultErrorHandler` is attached to the right listener factory.
- Permanent data errors are classified non-retryable.
- Retries for infrastructure errors have bounded attempts, backoff, and deadlines.
- `DeadLetterPublishingRecoverer` uses the proper `KafkaTemplate` and serializers.
- DLT supports raw `byte[]` when deserialization fails.
- DLT topics/partitions, replication, retention, and ACLs are provisioned.
- DLT publish failures are never treated as recovery success.
- Batch listeners inspect deserialization exception headers and report failed indices.
- Event IDs remain stable across recovery and replay.
- Listener/database/API side effects have idempotency controls.
- Logs include topic, partition, offset, and exception without leaking raw secrets.
- Metrics and alerts cover poison pills, DLT errors, consumer lag, and Schema Registry.
- Quarantine/replay procedures have access control and auditing.
- Malformed payloads, schema mismatches, and DLT failures have been tested before deployment.

**Conclusion:** When a record fails before entering `@KafkaListener`, `try/catch` inside the method is not the right fix. Determine whether the error arises in the deserializer, converter, or argument resolution; use `ErrorHandlingDeserializer` when errors occur during poll; route errors with full metadata to `CommonErrorHandler`/`DeadLetterPublishingRecoverer`; and ensure raw bytes, topic/partition/offset, and recovery outcomes are handled safely. This enables consumers to move past poison pills without silently dropping records or entering infinite retry loops.

