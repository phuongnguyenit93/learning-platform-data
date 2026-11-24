# ErrorHandlingDeserializer

In Kafka, data reading errors do not always occur inside the **@KafkaListener** method. If the record bytes cannot be converted into a Java object, the Kafka consumer may throw an exception directly during the **poll** step, before Spring Kafka invokes the listener. For a consumer reading continuously, a corrupted record at a fixed offset can become a **poison pill**: the consumer starts, polls up to that record, fails, and still cannot process subsequent records.

Spring Kafka's **ErrorHandlingDeserializer** bridges the gap between the Kafka client deserialization step and the listener container's error-handling mechanism. It wraps a real deserializer (delegate), catches errors from the delegate, preserves information about the error and the raw bytes in the record's metadata/headers, and then allows the Spring Kafka container to route the error through **DefaultErrorHandler** and the recovery policy instead of getting stuck at poll.

In the **Deserialization and Schemas** chapter of **Spring Kafka Reliability Operations**, this is a critical configuration when reading JSON, Avro, Protobuf, or other schema-based formats. The goal is not to ignore corrupted data at all costs, but to **avoid stalling the consumer, avoid silently losing data, and have sufficient evidence for recovery**.

## 1. Where do errors occur in the consumer pipeline?

A typical record processing flow:

~~~mermaid
flowchart TD
    A["Kafka partition: key bytes + value bytes"] --> B["KafkaConsumer.poll()"]
    B --> C["Key deserializer + value deserializer"]
    C --> D["Spring Kafka listener container"]
    D --> E["Message converter / argument binding (if any)"]
    E --> F["@KafkaListener"]
    F --> G["Business service / downstream"]
~~~

Different types of errors can arise at each step:

| Location | Example | Mechanism to check |
|---|---|---|
| Poll / deserializer | Malformed JSON, incompatible Avro writer schema, untrusted class | ErrorHandlingDeserializer, consumer error handling |
| Message conversion | Jackson object conversion, header type mapping, conversion to listener argument | Converter error handling, listener container |
| Listener invocation | Business validation, NullPointerException, database timeout | DefaultErrorHandler, BackOff, DLT |
| Downstream | HTTP 503, database deadlock, connection pool exhaustion | Controlled retry, idempotency, circuit breaker |
| Offset commit | Broker unavailable, consumer lost assignment | Commit/rebalance handling, monitoring |

**ErrorHandlingDeserializer handles errors thrown by the delegate deserializer.** It does not automatically catch every error occurring at downstream layers. If deserialization succeeds but business validation fails in the listener, that error follows the normal listener exception flow.

### 1.1 Scenario without ErrorHandlingDeserializer

Suppose the `orders` topic has the following records:

| Partition | Offset | Data | Result |
|---|---:|---|---|
| orders-0 | 100 | Valid OrderCreated JSON | Readable |
| orders-0 | 101 | Truncated JSON | JsonDeserializer fails |
| orders-0 | 102 | Valid OrderCreated JSON | Not reached by listener yet |
| orders-0 | 103 | Valid OrderCreated JSON | Not reached by listener yet |

With JsonDeserializer called directly by the Kafka consumer, the exception may occur right inside poll. The container has not received a valid ConsumerRecord for offset 101, so the error handler intended for listener errors does not have a complete record to process as it would for a business exception.

If an operator merely restarts the consumer, record 101 remains in the log and can fail the consumer at the same offset again. If the operator manually seeks to 102 to bypass the error without saving the original record, record 101 can be skipped without any way to investigate.

### 1.2 When using ErrorHandlingDeserializer

Instead of letting the delegate exception escape directly from poll, the wrapper:

1. Receives bytes from the Kafka client.
2. Calls the configured delegate deserializer.
3. If successful, returns the key/value normally.
4. If it fails, stores error metadata in Kafka record headers and returns a replacement value (usually null by default).
5. The Spring Kafka container detects the error header and forwards the error to the error handler via the corresponding mechanism.
6. The recoverer can write the record to a DLT and let the consumer continue, or retain the error if recovery has not succeeded.

~~~mermaid
flowchart TD
    B["Byte[] from Kafka"] --> W["ErrorHandlingDeserializer wrapper"]
    W --> D["Delegate: JsonDeserializer, Avro, ..."]
    D --> E{"Deserialize succeeded?"}
    E -->|Yes| V["Return Java value"]
    V --> L["Container / listener"]
    E -->|No| H["Write DeserializationException and raw bytes to header"]
    H --> N["Return fallback/null"]
    N --> C["Spring Kafka container detects error header"]
    C --> EH["DefaultErrorHandler"]
    EH --> RC["Recoverer / DLT / retry per policy"]
~~~

This mechanism brings the problem into a processing path with offsets and metadata, where the application can decide on recovery transparently.

## 2. ErrorHandlingDeserializer is a wrapper, not a parser

ErrorHandlingDeserializer does not know how to decode JSON, Avro, or Protobuf on its own. It **delegates** to a specialized deserializer.

Example:

~~~text
Kafka key bytes
  -> ErrorHandlingDeserializer
     -> StringDeserializer
        -> String key

Kafka value bytes
  -> ErrorHandlingDeserializer
     -> JsonDeserializer
        -> OrderCreated object
~~~

When the delegate succeeds, the listener receives the result just as if there were no wrapper. When the delegate fails, the wrapper provides the mechanism to route the error back to Spring Kafka.

| Component | Role |
|---|---|
| ErrorHandlingDeserializer | Wraps the delegate, catches deserialization exceptions, and stores error information |
| StringDeserializer | Converts key bytes to String |
| JsonDeserializer | Converts JSON bytes to a Java object |
| Avro/Protobuf deserializer | Uses a dedicated wire format and schema to read records |
| DefaultErrorHandler | Decides retry, skip/recover, and offset handling when the container detects an error |
| DeadLetterPublishingRecoverer | Publishes unprocessable records to a destination topic |
| KafkaMessageListenerContainer | Coordinates poll, listener invocation, error handling, and offset commit |

Switching a JSON deserializer to an Avro deserializer does not change the wrapper principle, though the classes, schema registry configuration, and specific exception types may differ.

## 3. Spring Boot configuration with key and value delegates

Configuring a consumer reading String keys and JSON values:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-projection-prod
      enable-auto-commit: false
      auto-offset-reset: earliest

      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer

        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
        spring.json.use.type.headers: false

    listener:
      ack-mode: record
~~~

In this example:

- The Kafka consumer invokes ErrorHandlingDeserializer for **both key and value**.
- Each wrapper knows which delegate to call via its corresponding property.
- The value delegate is JsonDeserializer.
- When the producer does not provide suitable Spring type headers, JSON configuration allows specifying the target type explicitly.
- Trusted packages are restricted to the allowed model package; do not arbitrarily open them to all packages.
- The container manages offsets because auto-commit is disabled; ack mode is chosen for the record listener model.

The **OrderCreated** class and **com.example.orders** package are illustrative only and should be replaced according to the real application contract.

### 3.1 Key properties

| Property | Meaning |
|---|---|
| spring.kafka.consumer.key-deserializer | Deserializer called by the Kafka client for the key; use ErrorHandlingDeserializer when wrapping the key |
| spring.kafka.consumer.value-deserializer | Deserializer called by the Kafka client for the value; use ErrorHandlingDeserializer when wrapping the value |
| spring.deserializer.key.delegate.class | Actual deserializer used to convert key bytes |
| spring.deserializer.value.delegate.class | Actual deserializer used to convert value bytes |
| spring.json.value.default.type | Default type for JSON values if appropriate for how type headers are used |
| spring.json.trusted.packages | Restricts packages allowed to deserialize under Spring JSON configuration |
| spring.json.use.type.headers | Determines whether to use metadata type headers according to the payload contract |

Dotted keys inside the **consumer.properties** block are passed through to the delegate deserializer. They are not broker configurations. If using a newer framework version with different Java configuration or type mapping, prioritize the system's actual contract.

### 3.2 Is wrapping only the value enough?

If keys are always valid Strings, you may wrap the value first. However, key deserialization can also fail—for example, when the key uses a custom format or a producer sends bytes that are invalid under the contract.

If only the value is wrapped:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Errors from an unwrapped key delegate will not follow the same header recovery mechanism. For systems that need poison-pill protection for both keys and values, evaluate wrapping both.

## 4. Configuration in Java

When a project creates its own ConsumerFactory, it can supply delegates directly instead of only declaring class names.

Structural example:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> orderConsumerFactory() {

    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG,
              "order-projection-prod");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
              false);

    ErrorHandlingDeserializer<String> keyDeserializer =
        new ErrorHandlingDeserializer<>(
            new StringDeserializer()
        );

    JsonDeserializer<OrderCreated> jsonDeserializer =
        new JsonDeserializer<>(OrderCreated.class);

    ErrorHandlingDeserializer<OrderCreated> valueDeserializer =
        new ErrorHandlingDeserializer<>(jsonDeserializer);

    return new DefaultKafkaConsumerFactory<>(
        props,
        keyDeserializer,
        valueDeserializer
    );
}
~~~

This example assumes the OrderCreated model is already defined. JsonDeserializer configuration may also need type mapping, trusted packages, and type header handling per the producer-consumer contract.

An important principle: **choose one clear mechanism for configuring delegates**. If you instantiate ErrorHandlingDeserializer with a delegate object in Java, do not also declare a conflicting delegate class in properties unless intentional. Check the constructors and property binding of the Spring Kafka version in use.

### 4.1 Multiple ConsumerFactories

An application may have ConsumerFactories for JSON, Avro, and plain text. Enabling the wrapper on the JSON factory does not mean the Avro listener is also protected.

Map them out per listener:

~~~text
ordersListener   -> ordersFactory -> ErrorHandlingDeserializer + JsonDeserializer
paymentsListener -> avroFactory   -> ErrorHandlingDeserializer + AvroDeserializer
auditListener    -> textFactory   -> StringDeserializer (if acceptable)
~~~

Each factory needs verification of its key/value delegates, error handler, recoverer, and corresponding DLT producer.

## 5. Headers containing DeserializationException

When the delegate throws an exception, ErrorHandlingDeserializer stores the error information in the record's headers. The header is used by the Spring Kafka container to recognize a deserialization failure and may include:

- Exception type and cause.
- Topic, key/value context.
- Raw data bytes that could not be converted into an object.
- Metadata needed for error handling.

Error headers can exist for the **key**, the **value**, or both. Header names and encoding are defined by Spring Kafka via internal/public constants depending on version; do not guess or invent header names manually.

### 5.1 Is a default null value a tombstone?

Not necessarily.

A Kafka compacted topic can contain a **tombstone**: a record with a valid null value representing deletion of a key. ErrorHandlingDeserializer can also return null when the value fails to deserialize.

Distinguish the two cases:

| Case | Value in application | Has deserialization exception header? |
|---|---|---|
| Valid tombstone | null | No, if the delegate did not fail |
| Valid JSON null per contract | May be null depending on delegate | No, if deserialization succeeded |
| Value deserialization failed | null by default fallback | Yes |
| Failed-deserialization function returns a replacement object | Custom object from function | Error metadata must still be checked per policy |

With a standard record listener, the Spring Kafka container can intercept the failed record before invoking the listener and route it to the error handler. With batch listeners or custom handling approaches, developers must take special care not to mistake an error null for a tombstone.

**Do not use `value == null` alone to conclude a record is corrupted**, and do not use null to automatically delete data without checking the contract/metadata.

### 5.2 Error metadata is not a business schema

Headers added by ErrorHandlingDeserializer serve consumer infrastructure. They should not become a permanent part of a business event schema or be blindly copied across every topic.

When forwarding messages or replaying a DLT:

- Retain source metadata for tracing when needed.
- Do not allow a Java-serialized exception header to be automatically deserialized without control by another service.
- Do not depend on internal header formats across framework versions.
- Ensure raw payloads, stack traces, or sensitive information are not exposed via logs/monitoring.

## 6. Combining DefaultErrorHandler and DLT

ErrorHandlingDeserializer **does not decide on its own to skip a record or send it to a DLT**. It feeds deserialization errors into Spring Kafka's error handling system. There must be a clear recovery policy, especially when a record cannot be validly processed.

Example using DefaultErrorHandler and DeadLetterPublishingRecoverer:

~~~java
@Configuration
public class OrderConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
            );

        DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(0L, 0L)
            );

        return handler;
    }
}
~~~

In the example above, **FixedBackOff(0L, 0L)** means no retries before attempting recovery via the handler. This policy is usually suitable for permanently corrupted payloads, because re-feeding the same bytes to the same delegate usually keeps failing.

However, if the delegate fails because of a transient dependency issue such as an unavailable schema registry, **do not treat every error as a poison payload by default**. Errors must be classified and policies adjusted to avoid flooding the DLT during an infrastructure outage.

### 6.1 Attaching the error handler to the listener container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection-prod",
    containerFactory = "ordersListenerFactory"
)
public void onOrder(OrderCreated order) {
    projectionService.apply(order);
}
~~~

If a record cannot be deserialized and the error header is recognized by the container, the listener does not process the corrupted object as a valid event. The error handler decides recovery. If the record is valid but `projectionService.apply()` throws an exception, the same handler can handle the business error according to its own classifier/backoff.

### 6.2 Do not treat logging and skipping as complete recovery

If no proper recoverer is configured, some handler defaults may log the exception and finish error handling per policy. This can let offsets advance, while leaving the raw payload unpreserved in an easily accessible investigation channel.

For important events, clearly define:

1. Where are corrupted records stored?
2. Who receives alerts?
3. How do you locate the raw bytes and source contract/schema?
4. How do you replay once the bug is fixed?
5. Does a recovery failure prevent offsets from advancing?

Do not treat "the consumer is no longer stuck" as the sole criterion for success.

## 7. The DLT producer must be able to serialize raw bytes

This is the easiest point to get wrong when combining ErrorHandlingDeserializer with DeadLetterPublishingRecoverer.

On a value deserialization error, the failed payload is not a valid OrderCreated object. For investigation or replay, Spring Kafka can publish the **raw bytes of the original value** to the DLT. On a key error, raw key bytes may also need to be preserved.

Therefore, the DLT producer may have to send multiple data types:

- **byte[]** for a key or value that failed to deserialize.
- **String** for a key that deserialized successfully.
- **OrderCreated** or a valid object for records that failed in listener/business logic.

If the DLT KafkaTemplate is hard-configured with only JsonSerializer or StringSerializer without handling byte[], DLT publishing can fail or alter the original payload.

### 7.1 Using a type-routing serializer

One approach is using **DelegatingByTypeSerializer** with ByteArraySerializer for raw bytes and the corresponding serializer for valid objects.

Illustrative example:

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory() {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ProducerConfig.ACKS_CONFIG, "all");

    Map<Class<?>, Serializer<?>> keySerializers =
        new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers =
        new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(OrderCreated.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
        props,
        new DelegatingByTypeSerializer(keySerializers),
        new DelegatingByTypeSerializer(valueSerializers)
    );
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {

    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

This is a sample structure for a contract with only String keys, OrderCreated values, and raw `byte[]` on deserialization failure. In a real application, you may need additional serializers for other event types, null values, headers, or schema-aware serializers per contract.

DelegatingByTypeSerializer instantiation and type matching behavior must be verified against the specific Spring Kafka version. If the application already has multiple KafkaTemplates, you can also design the recoverer to select the template by record type.

### 7.2 Why preserve raw bytes?

Raw bytes help:

- Determine what the producer actually sent.
- Compare the payload against the writer schema and reader schema.
- Recover data if the fix is solely on the consumer side.
- Reprocess after updating type mapping or schema registry.
- Distinguish network/registry errors from permanently invalid payloads.

If the DLT only writes a JSON message saying "deserialize failed", the original data may be lost. Preserving raw bytes must be accompanied by appropriate ACLs and sensitive-data management.

### 7.3 DLT publish failure is a critical error

The DLT topic needs enough partitions if the recoverer preserves the partition number:

~~~text
orders partition 3
       -> orders.DLT partition 3
~~~

If `orders.DLT` only has two partitions, publishing to partition 3 is invalid.

In addition, you need:

- Available brokers and DLT topic.
- WRITE permissions for the recovery producer.
- Correct serializer for the actual runtime type.
- Sufficient message size limit for the raw payload and headers.
- Appropriate ACK/durability settings.
- A mechanism to detect DLT send failures.

For versions that support it, the recoverer can be configured to inspect the send result, such as the **failIfSendResultIsError** option, to avoid treating recovery as successful when the broker did not acknowledge writing to the DLT. Verify the API semantics and timeouts for your project's version.

## 8. How do key errors and value errors differ?

A Kafka record has independent key and value serialization. Both can use different schemas or serializers.

### 8.1 Value deserialization error

Example:

~~~text
topic: orders
partition: 0
offset: 501
key bytes: "order-1001"
value bytes: {"orderId":"order-1001","amount":
~~~

The String key can be read, while the JSON value is truncated.

When the value delegate fails:

- ErrorHandlingDeserializer for the value stores error metadata.
- The key can still be a valid String.
- The container can route the error to DefaultErrorHandler.
- The recoverer needs to publish the original value as `byte[]` if preserving the original is desired.

### 8.2 Key deserialization error

For example, a producer sends a binary key in a custom format while the consumer configures String or an incompatible schema-aware key deserializer.

If the key delegate fails:

- The Java key may be null under the default fallback.
- Key error metadata is stored.
- The Java value may still be valid.
- The recoverer should consider preserving raw key bytes to trace partitioning and the business key.

Do not configure only a value ErrorHandlingDeserializer and assume all deserialization errors are managed.

### 8.3 If both key and value fail

A record can carry both error metadata entries. When collecting diagnostics, record clearly which field failed rather than just logging "value is null" and overlooking the key error.

In the DLT, preserve raw key/raw value according to the capabilities of the recoverer and serializers. Reconstructing the business key must be done carefully; do not guess a key from data that failed deserialization.

## 9. Schema errors: corrupted payload or incompatible contract?

With JSON, Avro, Protobuf, and schema-aware formats, deserialization failures can come from multiple causes.

| Category | Symptom | How to investigate |
|---|---|---|
| Corrupted bytes | JSON missing closing brace, truncated payload | Compare raw bytes, producer serializer, and transport |
| Wrong type mapping | Header points to a nonexistent class | Check type headers, mapping, and consumer version |
| Incompatible writer/reader schema | Delegate cannot convert a field or type | Compare schema IDs, versions, and compatibility policy |
| Schema Registry unavailable | Deserializer cannot fetch schema | Check network, registry health, cache, and auth |
| JSON trusted package | Class type header rejected | Check allowed packages and producer contract |
| Syntactically valid but business-invalid data | Negative amount, missing business key per rule | Bean validation/business validation, not necessarily a deserialize failure |
| Misconfiguration | Delegate class or format mismatch | Check ConsumerFactory and producer format |

**Do not turn every schema error into an infinite retry problem.**

If bytes are permanently incompatible with the consumer schema, retrying the same bytes with the same configuration will not fix it. Recovery/DLT followed by fixing the contract may be more appropriate.

If the error is caused by a registry outage, it may recover when the registry comes back. A policy that routes immediately to the DLT can flood the DLT and will not help the service recover. You must know the specific exception class/cause and deserializer capabilities to classify properly.

### 9.1 ErrorHandlingDeserializer does not replace Schema Registry

For Avro/Protobuf or JSON Schema from a registry, ErrorHandlingDeserializer only wraps the schema-aware deserializer. It does not:

- Register a new schema on behalf of the producer.
- Bypass schema compatibility policy.
- Automatically fix writer/reader schemas.
- Automatically determine the right business version.
- Automatically download schemas when the delegate is unconfigured.
- Change the topic's wire format.

Schema compatibility and producer-consumer rollouts must be managed separately. ErrorHandlingDeserializer is a **detection and recovery mechanism when decoding fails**, not a schema migration tool.

### 9.2 Safe schema rollout

Some practices:

1. Identify the format and schema of records already existing in the topic.
2. Check compatibility for both new producers and old consumers.
3. Deploy consumers able to read both old and new data versions before the producer changes format, if required by the contract.
4. Monitor deserialization metrics and DLT before, during, and after rollout.
5. Keep raw data/event IDs to investigate if incompatible records appear.
6. Have a rollback plan, because rolling back code does not automatically delete new-format records already written to Kafka.

## 10. Record listener: avoid calling business logic for failed payloads

With a standard record listener, the Spring Kafka container can detect the deserialization exception header and route the record to the error handler before invoking the listener.

Example:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection-prod",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderCreated event) {
        service.apply(event);
    }
}
~~~

If the record is valid, the listener receives OrderCreated. If the value delegate fails, do not rely on the listener receiving null and skipping the record itself; the container/error handler mechanism must take responsibility and should be verified in an integration test.

### 10.1 Do not conflate data errors with tombstones

If a compacted topic has valid tombstones, the listener needs an explicit contract for null values. Null does not automatically equate to an error.

With Spring Kafka, `@KafkaListener` argument binding when handling null/tombstones has specific annotation/type requirements depending on version; for example, the framework provides `KafkaNull` to represent a null value in certain conversion flows.

Distinguish between:

- Valid null per topic contract.
- Null caused by EHD failure with an exception header present.
- Null returned by business mapping.

Do not silently acknowledge a failed record just because the payload is null.

## 11. Batch listener: read error metadata intentionally

With a batch listener, a single invocation can receive multiple records. Some batch flows allow the listener to receive a list containing null elements and error headers at the corresponding index instead of throwing an individual exception before invoking the listener.

Example of a listener receiving ConsumerRecord to inspect raw headers:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch",
    containerFactory = "ordersBatchFactory"
)
public void handle(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);

        Header failure = record.headers().lastHeader(
            SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        );

        if (failure != null) {
            throw new BatchListenerFailedException(
                "Value deserialization failed at batch index " + i,
                i
            );
        }

        batchService.processOne(record.value());
    }
}
~~~

This is a conceptual example; imported classes, the `BatchListenerFailedException` constructor, and how the framework passes headers to batches depend on the Spring Kafka version. Some batch listeners receive a payload list and a separate list of converted headers via `KafkaHeaders.BATCH_CONVERTED_HEADERS`.

**Batch index is not Kafka offset.** If a batch contains records from multiple partitions, the index is the record's position in the list. When reporting an error, use the exact index in the original list so DefaultErrorHandler knows what has been processed and what needs recovery.

### 11.1 Avoid silent failures in batches

An anti-pattern:

~~~java
for (OrderCreated order : orders) {
    if (order == null) {
        continue;
    }
    service.apply(order);
}
~~~

The code above can skip an undeserializable record without writing to a DLT, without alerting, and without preserving raw bytes. If the batch returns normally, the container may commit the batch's offsets, causing the failed record to be bypassed.

For batches containing deserialization errors, a clear policy is required: throw `BatchListenerFailedException` with the index, or use a recovery flow appropriate for the running framework version.

### 11.2 Distinguish general batch errors from deserialization failures

If a listener throws a generic `RuntimeException`, DefaultErrorHandler may have to retry the entire batch when it does not know which record failed. When the failed record is identified by index, `BatchListenerFailedException` helps narrow the scope of retry/recovery.

This is especially important if preceding records have already produced side effects. Retrying the whole batch can re-run records that already succeeded. Idempotency is still needed even with partial batch handling.

## 12. failedDeserializationFunction: returning a fallback value

ErrorHandlingDeserializer has an optional mechanism to provide a **failedDeserializationFunction**. When the delegate fails, the function can create an object representing the failure based on information such as topic, raw bytes, and the exception.

This approach can be useful when the application needs to wrap bad data in a special domain envelope for controlled handling. However, it is a risky option.

If the function returns a **fake OrderCreated** just to avoid null, the listener may:

- Assume the payload was validly deserialized.
- Cause business side effects based on untrusted data.
- Commit offsets without sending raw bytes to the DLT.
- Obscure signs of corrupted data if error metadata is not checked.

Therefore:

- Do not use a fallback to "auto-repair" ambiguous payloads.
- If choosing a fallback object, it should be a clearly typed error representation, not masquerading as a valid event.
- Preserving raw bytes and the exception must still be defined.
- Ensure the consumer/lifecycle actually processes the error header as intended.
- Test with real corrupted payloads, not just unit tests of the function.

For most business consumers needing to quarantine failed records, **ErrorHandlingDeserializer + DefaultErrorHandler + DLT** is simpler and easier to audit than inventing fallback business objects.

## 13. Validation after deserialization

Successful deserialization does not mean the event is valid for business rules.

JSON example:

~~~json
{
  "orderId": "",
  "amount": -100,
  "currency": "USD"
}
~~~

The JSON above can parse into OrderCreated successfully, yet fail the application's validation rules.

Distinguish three layers:

1. **Wire format / schema parsing**: can bytes be converted to the expected type?
2. **Structural validation**: are required fields and format constraints valid?
3. **Business validation**: are the state/values acceptable to the business domain?

In some Spring Kafka versions, ErrorHandlingDeserializer supports integrating a validator after the delegate; if validation fails, the framework can store error information similarly to a deserialization failure. This capability depends on version and must be configured accurately.

A more common approach is validation inside the service/listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection-prod"
)
public void onOrder(OrderCreated event) {

    orderValidator.validate(event);
    projectionService.apply(event);
}
~~~

When validation throws an exception, DefaultErrorHandler applies the listener's classifier and recoverer. For example, `InvalidOrderPayloadException` should be classified as non-retryable if the payload itself cannot become valid through retries.

Do not mix schema errors, validation errors, and dependency errors; they typically require different policies.

## 14. Can retry make a deserialization error go away on its own?

Most permanently corrupted payloads do not change when the consumer retries. If the error is:

~~~text
Invalid JSON at offset 501
~~~

then reading the same `byte[]` at offset 501 again with the same JsonDeserializer will usually hit the same error.

Repeated retries can cause:

- The consumer to hold the partition for a long time.
- Lag to increase.
- The DLT to receive the record only after wasted delays.
- Repeated noisy logs.
- Increased load on the schema registry or other dependencies.

However, some errors depending on external state can be transient, such as a temporary Schema Registry timeout. In that case, find the root cause before deciding to skip retries.

| Error | Should retry? | Reason |
|---|---|---|
| Permanently corrupted JSON | Usually no | Bytes do not change |
| Type not in trusted packages | Usually no | Configuration/contract fix needed |
| Reader class not found due to bad deploy | Cannot self-heal with isolated retries | Correct code rollout needed |
| Schema Registry timeout | Possibly | Dependency may recover |
| Registry returns schema ID not found | Needs investigation | May be wrong registry/cluster or corrupted data |
| Temporary network outage | Possibly | Chance to recover once connectivity returns |

Remember that in Spring Kafka, certain deserialization-related exception types are treated as fatal/non-retryable by the default classifier. Actual policy must be verified on the version in use. If you want to retry transient registry errors, do not simply enable retries for all `DeserializationException`; have a strategy to classify causes or handle the dependency appropriately.

## 15. Offset commit after a failed record is recovered

An undeserializable record still occupies an offset in the Kafka log. After successful recovery, the application usually needs to advance past that offset to process subsequent records.

Suppose:

~~~text
orders-0 offset 100: valid
orders-0 offset 101: malformed JSON
orders-0 offset 102: valid
~~~

A desired flow:

1. Process offset 100 successfully.
2. When reading 101, ErrorHandlingDeserializer captures the error.
3. DefaultErrorHandler invokes the recoverer.
4. DLT is written successfully with the raw bytes and metadata of 101.
5. The container applies the ack/commit policy to continue from after 101.
6. The listener processes offset 102.

Do not automatically assume invoking the recoverer means the offset has definitely been committed immediately. AckMode, commitSync/commitAsync, container lifecycle, and options such as `commitRecovered` (when applicable) affect commit timing.

### 15.1 DLT and committed offset are two separate operations

Kafka does not automatically guarantee atomicity between writing to the DLT and committing the consumer offset if they are not coordinated within an appropriate transaction.

Failure windows to consider:

- DLT write finishes, process crashes before offset commit: record 101 may be read again and sent to the DLT a second time.
- DLT publish fails but the handler considers it recovered: the offset may advance and the original record is not quarantined as intended.

Therefore, ensure the recoverer detects send failures and design the DLT consumer/replay to be idempotent. Do not claim exactly-once just because ErrorHandlingDeserializer is enabled.

### 15.2 Manual acknowledgment

If the listener uses `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, recovery and offset commit must be coordinated under their specific semantics. Do not try to manually acknowledge a failed record inside the listener if the listener was never invoked.

With supported versions/configurations, DefaultErrorHandler has an option to commit recovered records in certain ack modes. Check the contract and integration tests before enabling.

## 16. Observability and alerting

The most important signal is the **rate of records failing deserialization**, though one metric alone is not enough to draw conclusions.

| Signal | What to look for |
|---|---|
| Deserialization failure rate | Error rate by topic, partition, and consumer group |
| Exception class/root cause | JSON parse, schema mismatch, registry timeout, trusted package |
| DLT publish success/failure | Whether recovery is actually writing raw bytes |
| Consumer lag | Whether a partition is blocked by a poison record |
| Offset progression | Whether offsets after the failed record are being processed |
| Schema versions | Which producer/consumer rollout preceded the errors |
| Retry attempts | Whether there are futile retries or retry storms |
| Broker/registry availability | Whether there is a widespread dependency outage |
| Recovery latency | How long from deserialization error until successful quarantine |

Logs should include metadata without needing the full payload:

~~~text
listenerId=orders-consumer
groupId=order-projection-prod
topic=orders
partition=0
offset=501
errorStage=VALUE_DESERIALIZATION
exception=SerializationException
action=DLT_PUBLISH
dltTopic=orders.DLT
~~~

If payloads contain personal, financial, or secret data, do not log raw bytes into application logs. Store raw bytes in the DLT with corresponding ACLs, retention, audit, and access permissions.

### 16.1 Distinguishing a single poison record from a widespread outage

If a single offset keeps failing while other partitions are healthy, it is likely a specific payload/contract issue.

If thousands of records across multiple topics fail simultaneously, check:

- Schema Registry.
- Security credentials/ACL.
- A producer that just changed format.
- A consumer that just deployed a new class/schema.
- Wrong environment profile or registry URL.
- Broker/network health.

Do not let a registry outage turn into thousands of DLT records before operators notice an unsuitable error classification policy.

### 16.2 Verifying the DLT is replayable

A DLT that has records but cannot be replayed because the serializer altered raw bytes or the schema ID was lost is also a form of recovery failure.

Record:

- Original topic/partition/offset.
- Key/value raw bytes when needed.
- Schema ID or version if the wire format carries that information.
- Exception type.
- Time of error and service version.
- Replay outcome or quarantine status.

## 17. Investigation runbook when hitting a poison pill

When a consumer reports deserialization errors or fails to advance past an offset:

1. Identify the failing group id, topic, partition, and offset.
2. Check whether the error occurred in poll, delegate deserializer, converter, or listener.
3. Confirm the actual ConsumerFactory configures ErrorHandlingDeserializer on the corresponding key/value.
4. Check the delegate class and JSON/schema registry configuration.
5. Collect the exception class, cause, and record metadata.
6. Determine whether the record can recover via retry or is a permanently corrupted payload.
7. Check the listener factory's DefaultErrorHandler and recoverer/DLT.
8. Confirm the DLT producer can serialize `byte[]` when value/key fails to deserialize.
9. Check the DLT topic, partitions, ACLs, ACK, and publish success.
10. After recovery, monitor committed offsets and processing of subsequent records.
11. If many records fail simultaneously, check schema rollouts and registry/network before routing bulk data to the DLT.
12. Plan to fix the payload or consumer and replay quarantined records.

Do not directly edit group offsets in production without knowing which data is being skipped. A seek/reset operation can get the consumer moving again while removing records from audit and recovery workflows.

## 18. Testing with real corrupted payloads

Integration tests against a real Kafka broker or Testcontainers are needed. Unit tests calling `@KafkaListener` directly bypass KafkaConsumer's deserializer and do not prove ErrorHandlingDeserializer works.

### 18.1 Testing corrupted JSON value

Scenario:

1. Create topics `orders` and `orders.DLT` with matching partitions.
2. Configure the consumer with ErrorHandlingDeserializer + JsonDeserializer.
3. Use a producer with ByteArraySerializer to send malformed JSON bytes as the value.
4. Keep the key valid.
5. Confirm the business listener does not process the corrupted record.
6. Confirm the handler/recoverer is triggered.
7. Read the DLT with ByteArrayDeserializer and compare raw value bytes with what was sent.
8. Confirm subsequent valid records are still processed.
9. Verify offsets and source metadata.

Test data example:

~~~text
key: order-1001
value bytes: {"orderId":"order-1001","amount":
~~~

### 18.2 Testing corrupted key

- Use a key serializer emitting bytes incompatible with the key delegate.
- Configure key ErrorHandlingDeserializer.
- Confirm the key exception is detected.
- Confirm recovery stores raw key bytes as configured.
- Confirm a valid value is not lost when the error is only in the key.

### 18.3 Testing valid tombstone

- Send a record with a valid null value to a compacted topic or test topic.
- Confirm no deserialization exception header appears.
- Confirm the listener/tombstone handler handles null according to contract.
- Compare against a record with a corrupted JSON value.

### 18.4 Testing Schema Registry failure

- Use a schema-aware delegate.
- Simulate an unavailable registry in an isolated environment.
- Confirm the exception and retry/recovery policy behave as designed.
- Restore the registry.
- Confirm the record can be processed or quarantined per policy.
- Do not enable infinite retries for infrastructure errors.

### 18.5 Testing DLT producer serializer

- Send a corrupted payload.
- Intentionally configure a DLT serializer that does not support `byte[]` in a test environment.
- Confirm the recovery failure is detected.
- Fix the serializer/DelegatingByTypeSerializer.
- Confirm the DLT receives the exact raw bytes.
- Confirm the record is not lost when DLT publish fails.

### 18.6 Testing batch listener

- Poll a batch containing valid records and one record that fails deserialization.
- Confirm the listener receives or detects exception metadata according to the batch mechanism of the version in use.
- Throw `BatchListenerFailedException` with the exact index when appropriate.
- Confirm records before the error are not reprocessed outside policy.
- Confirm the failed record is recovered and subsequent records continue.
- Check for duplicate side effects and per-partition offset commits.

## 19. Misconceptions to avoid

**"ErrorHandlingDeserializer fixes broken JSON."** No. It preserves error information and routes the record to error handling; it does not turn the payload into valid data.

**"Enabling ErrorHandlingDeserializer solves all listener errors."** No. Post-deserialization errors still require DefaultErrorHandler, BackOff, and a recovery policy.

**"Failed records go to the DLT automatically."** Not automatically. You must configure a recoverer, KafkaTemplate, DLT topic, and proper serializers.

**"A null value is always a tombstone."** False. A null value can be the fallback from a deserialization failure; distinguish via exception metadata.

**"Wrapping the value is enough for all cases."** False if the key deserializer can also fail.

**"Sending to DLT with JsonSerializer always preserves raw bytes."** Not guaranteed. You need serializers supporting both `byte[]` and valid objects.

**"Every deserialization error should be retried dozens of times."** No. Permanently invalid payloads usually do not fix themselves on retry.

**"If the consumer keeps running, data was preserved."** No. Records may have been skipped if recovery only logged without saving raw bytes.

**"A Schema Registry outage is the same as a corrupted payload."** No. A registry outage can be a transient dependency failure and requires its own policy.

**"One successful DLT publish means exactly-once."** No. A crash between DLT publish and offset commit can still produce duplicate DLT records.

**"Batch listeners automatically know which record failed just like record listeners."** Not always. You must inspect headers and failed indices according to how batch listeners work.

## 20. Design and operations checklist

**Deserializer and schema**

- [ ] ConsumerFactory actually wraps the key/value delegates needing protection.
- [ ] Delegate classes and schema/type mapping are configured properly.
- [ ] Trusted packages are restricted according to contract.
- [ ] Schema registry configuration is verified in the target environment.
- [ ] Parse errors, registry errors, and business validation are distinguished.

**Error handler and recovery**

- [ ] Listener container uses DefaultErrorHandler/recoverer on the right factory.
- [ ] Non-recoverable errors are not futilely retried.
- [ ] Transient dependency errors have an appropriate policy.
- [ ] DLT routing, ACLs, partitions, and durability are clearly designed.
- [ ] DLT producer supports raw `byte[]` for failed keys/values.
- [ ] DLT publish failure is not treated as successful recovery.
- [ ] Committed offsets and recovery outcomes are reconciled.

**Data and security**

- [ ] Raw bytes are preserved when needed for replay.
- [ ] Exception headers are not abused as a business contract.
- [ ] Sensitive payloads are not logged.
- [ ] DLT has appropriate retention, access control, and deletion procedures.
- [ ] Event IDs and source metadata exist to reconcile duplicates.

**Testing and observability**

- [ ] Corrupted JSON/Avro/Protobuf bytes tested according to actual format.
- [ ] Both key errors and value errors tested.
- [ ] Valid tombstones tested.
- [ ] DLT serializer and send failures tested.
- [ ] Batch listener tested if the application uses batching.
- [ ] Metrics exist for deserialize failures, DLT, lag, and offset progression.
- [ ] Runbook exists for schema fixes, dependency restoration, and DLT replay.

**ErrorHandlingDeserializer** is the recovery boundary between Kafka deserialization and Spring Kafka container error handling. By wrapping the delegate, storing the exception along with raw bytes in metadata, and allowing the handler to process failed records in a controlled manner, it reduces the risk of a poison pill stalling the consumer. Reliability is only complete when combined with proper schema configuration, durable recoverer/DLT, raw-byte-capable serializers, timely offset commits, idempotency, and production investigation/replay capabilities.

