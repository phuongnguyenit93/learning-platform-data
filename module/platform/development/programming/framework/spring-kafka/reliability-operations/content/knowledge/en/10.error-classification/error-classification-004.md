# DeserializationException

## 1. DeserializationException in Spring Kafka

Kafka stores a record's key and value as byte arrays. When a consumer reads a record, the Kafka client invokes a deserializer to convert those bytes into the data type used by the application, such as String, JSON object, Avro, or Protobuf.

If the data is malformed, the schema is incompatible, type information is missing, or the delegate deserializer throws an exception, conversion can fail. In Spring Kafka, this error is typically represented by `DeserializationException` and routed into the listener container's error handling mechanism.

Common causes:

- Malformed, truncated, or improperly encoded JSON.
- Payload does not match the schema or event version expected by the consumer.
- Invalid type header or unable to map to a class.
- Deserializer does not support the byte format sent by the producer.
- Schema registry is unreachable or the corresponding schema is not found.
- Empty key or value where the application/deserializer does not allow it.
- Data written by another producer with a different serializer or contract.

An important operational point: deserialization errors occur before the listener method receives the payload. Therefore, a deserialization error can prevent the listener from being invoked for that record. You need a mechanism that passes errors from the deserializer to the listener container so the error handler has enough information about the record, offset, and partition to recover.

## 2. Where does DeserializationException occur in the read flow?

### 2.1. Normal flow

When data is valid, the basic path is:

1. The consumer polls records from the broker.
2. The Kafka client retrieves the key and value byte arrays.
3. The key deserializer and value deserializer convert bytes into objects.
4. The Spring listener container receives the deserialized ConsumerRecord.
5. The container passes the payload to the `@KafkaListener` method.
6. The listener executes business logic.
7. The container commits the offset according to the acknowledgment mode if processing succeeds.

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Kafka consumer
    participant D as Deserializer
    participant LC as Spring listener container
    participant L as Listener

    C->>B: poll/fetch
    B-->>C: Record bytes
    C->>D: deserialize key/value
    D-->>C: Object
    C->>LC: ConsumerRecord
    LC->>L: Invoke listener
    L-->>LC: Success
    LC->>B: Commit offset per ack mode
~~~

### 2.2. Flow when deserialization fails

If a deserializer throws an exception, the listener does not receive a valid object. When using a raw deserializer directly and the exception escapes the Kafka consumer poll, the container may not have a normal ConsumerRecord to pass to the record-level error handler.

Spring Kafka's `ErrorHandlingDeserializer` bridges this gap: it wraps the actual deserializer (delegate), catches deserialization errors, stores the error details along with the raw bytes in special headers, and returns null so the consumer can still pass the record and metadata to the container.

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Kafka consumer
    participant E as ErrorHandlingDeserializer
    participant LC as Spring listener container
    participant EH as Error handler
    participant DLT as Dead-letter topic

    C->>B: poll/fetch
    B-->>C: Record bytes
    C->>E: deserialize
    E->>E: Call delegate deserializer
    E-->>E: Conversion exception
    E->>E: Store exception and raw bytes in headers
    E-->>C: Record with null payload
    C->>LC: ConsumerRecord and error headers
    LC->>EH: Forward deserialization error
    EH->>DLT: Publish record if recovered
~~~

The container/error handler can classify the failed record, skip unhelpful retries, or route the record to a DLT. The record retains its topic, partition, offset, timestamp, and headers for investigation.

### 2.3. Why is the listener not invoked?

The listener method expects a deserialized payload. When the value deserializer cannot construct an object, there is no properly typed payload to invoke a standard listener method.

With ErrorHandlingDeserializer, the container receives a record with a null payload accompanied by a header containing error details. The container detects this header and forwards the error to the error handler. A null payload in this case must not be treated as a valid business event.

If the application allows valid null values (tombstones in compacted topics), you must distinguish genuine tombstones from null caused by deserialization failure using the error header. Checking only whether the payload is null is insufficient.

## 3. DeserializationException and ErrorHandlingDeserializer

### 3.1. ErrorHandlingDeserializer as a wrapper

`ErrorHandlingDeserializer` is a Spring Kafka deserializer, not a serializer replacement for JSON, String, or Avro. It wraps a delegate deserializer that performs the actual conversion.

Example with JSON:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

In this configuration:

- Kafka uses ErrorHandlingDeserializer for the value.
- ErrorHandlingDeserializer invokes JsonDeserializer as the delegate.
- If the JSON is valid, the listener receives the deserialized object.
- If the JSON is invalid, the wrapper stores the error details and raw bytes in headers, then returns null for the container to handle.

If the key can also fail deserialization, wrap the key deserializer similarly using the key delegate property. Wrapping only the value does not protect against key deserializer failures.

### 3.2. Java configuration

You can instantiate the deserializer in Java and wrap a delegate:

~~~java
Map<String, Object> consumerProperties = new HashMap<>();

consumerProperties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
consumerProperties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-service"
);
consumerProperties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);
consumerProperties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProperties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);
consumerProperties.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    JsonDeserializer.class
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(consumerProperties);
~~~

This is an illustrative example. When using Spring Boot, keep configuration in a single unified source to prevent a custom consumer factory from overriding Boot properties. When configuring directly, verify the exact constants and APIs for the running Spring Kafka version.

### 3.3. Delegate deserializer

The delegate is the component performing actual deserialization. Examples:

| Format | Common delegate |
|---|---|
| UTF-8 string | `StringDeserializer` |
| JSON object | Spring Kafka `JsonDeserializer` |
| Byte array | `ByteArrayDeserializer` |
| Avro | Avro deserializer corresponding to schema registry |
| Protobuf | Protobuf deserializer from the chosen library |

Errors can come from the delegate or its dependencies, such as schema registry. ErrorHandlingDeserializer does not fix data on its own and does not make incompatible schemas valid. It only translates the error into information that the container/error handler can process.

## 4. Error-carrying contents and headers

### 4.1. Deserialization error headers

When a delegate fails, ErrorHandlingDeserializer stores exception details in special record headers. Spring Kafka distinguishes key and value errors, commonly using headers named:

- `springDeserializerExceptionKey`: error while deserializing the key.
- `springDeserializerExceptionValue`: error while deserializing the value.

The header holds serialized error information so it can travel inside a Kafka ConsumerRecord. Spring Kafka can read this header and reconstruct the appropriate exception for error handling.

Header names and serialization details are internal Spring Kafka contracts; applications should use framework APIs to access them rather than manually creating or modifying these headers. Headers may be stripped or altered during processing, so persist error metadata before performing any operation that removes headers if required by your workflow.

### 4.2. Raw bytes and original data

When deserialization fails, the null value seen by the listener/container does not contain the original payload. The exception information retained by ErrorHandlingDeserializer can carry the original bytes, allowing the error handler or dead-letter recoverer to restore the data when publishing to a DLT.

This is crucial when handling poison pills: failed records must still be preserved for investigation and replay. If the DLT contains only null without raw bytes or original metadata, operations may be unable to reproduce the cause.

Do not log raw bytes in full by default. Payloads may contain personal data, tokens, or sensitive information. Restrict DLT access, apply appropriate retention, and extract only what is necessary for investigation.

### 4.3. Useful metadata for diagnostics

When recording errors, preserve these fields:

- Source topic.
- Partition and offset.
- Record timestamp.
- Key if safely readable.
- Correlation ID, trace ID, or event ID headers if present.
- Exception type and cause chain.
- Payload size and a fingerprint/hash if correlation is needed.
- Deserializer name and expected schema/version.

If key deserialization also failed, do not assume the key is already a String or object. You may need to extract raw key bytes from the exception/header and note that the key could not be converted.

## 5. Distinguishing deserialization errors from payload conversion errors

Spring Kafka performs multiple data conversion steps. You must identify which step failed in order to choose the right handling mechanism.

| Step | Component | Example error | Can listener be invoked? |
|---|---|---|---|
| Bytes to key/value | Kafka deserializer | Malformed JSON, non-existent schema | Usually no valid payload to invoke listener |
| Spring Message conversion | MessageConverter | Payload cannot convert to listener parameter | Listener method may not have been invoked successfully |
| Type mapping | JsonDeserializer/type mapper | Invalid type header or untrusted class | Fails during deserialization step |
| Business logic | Listener method | Validation, database, or service failure | Listener has been invoked |

`DeserializationException` refers to an error converting bytes to an object at the deserializer layer. An exception thrown by MessageConverter or business code is an error at a different step, even though both can flow through the error handler.

Examples:

- Malformed JSON syntax: error in JsonDeserializer.
- Valid JSON but target class not allowed to deserialize: deserializer mapping/type error.
- JSON converted to object but required field missing per business rules: listener may receive the object and throw a validation exception.
- Valid payload object but database times out: error inside listener/downstream.

Do not convert every exception into a DeserializationException. Classify at the proper layer so retries and DLT behave appropriately.

## 6. Handling DeserializationException with DefaultErrorHandler

### 6.1. Role of the error handler

`DefaultErrorHandler` is Spring Kafka's standard error handler for record listeners. It can classify exceptions, retry with backoff, and invoke a recoverer once attempts are exhausted.

Deserialization errors are usually unrecoverable by resending the exact same byte sequence with the same deserializer and schema. Therefore, repeated retries usually do not help and only keep the partition blocked longer.

Deserialization errors can be configured as fatal/non-retryable and routed directly to the recoverer. In Spring Kafka, deserialization exceptions such as DeserializationException are typically classified as non-retryable by DefaultErrorHandler's default classification; verify your version and classification configuration if the application customizes the error handler.

### 6.2. Example using DefaultErrorHandler

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
    DeadLetterPublishingRecoverer recoverer
) {
    var backOff = new FixedBackOff(1_000L, 2L);

    var errorHandler = new DefaultErrorHandler(recoverer, backOff);

    errorHandler.addNotRetryableExceptions(
        DeserializationException.class
    );

    return errorHandler;
}
~~~

This example illustrates the declaration. DefaultErrorHandler may already classify deserialization errors as non-retryable by default; explicit declaration makes application policy readable, though duplicate registration or unintended overrides must be avoided. Retry counts and backoff must reflect actual error types.

For temporary downstream failures, retry with backoff can be appropriate. For malformed payloads, retrying the same bytes typically repeats the same error. You can route the record straight to a DLT to preserve data and continue processing subsequent records per policy.

### 6.3. When should you retry?

Classify by cause:

| Error type | Is retry helpful? | Handling approach |
|---|---|---|
| Malformed JSON syntax | Usually no | DLT; fix producer or data |
| Non-existent Schema ID | Possibly if schema registry is temporarily unreachable; no if schema truly missing | Distinguish connectivity error from missing schema |
| Invalid type header | Usually no | Check producer contract and type mapping |
| Target class absent in application | No if current artifact does not change | Fix dependency or mapping |
| Database error after deserialization | Possibly | Retry with backoff per downstream policy |
| External service timeout | Possibly | Bounded retry, circuit breaker, and DLT on failure |
| Payload too large or exceeds limit | No with the same payload | Adjust producer/broker or redesign payload |

Some schema library exceptions can represent either a transient network issue or a permanent contract error. Do not lump them into a single group based only on the outer wrapper exception name; inspect the cause chain and specific error code.

## 7. Routing failed records to a Dead Letter Topic

### 7.1. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` is the common recoverer used to publish unprocessable records to a dead-letter topic (DLT). It preserves source information such as topic, partition, offset, and exception in dead-letter headers managed by Spring Kafka.

Example creating a recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
    KafkaTemplate<Object, Object> dltTemplate
) {
    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
    );
}
~~~

This example routes records from `orders` to `orders.DLT`, preserving the corresponding partition number. If the DLT has fewer partitions than the source topic or lacks the corresponding partition, publishing can fail. Create the DLT with an appropriate partition count or choose a different routing strategy.

With multiple topics, you can route by topic name, error category, or business domain. Avoid creating DLT topics dynamically per exception message, as that can create too many topics and increase operational overhead.

### 7.2. DLT must preserve raw bytes when deserialization fails

For records that fail deserialization, the payload object has no valid value. ErrorHandlingDeserializer preserves raw bytes and the exception in headers; Spring Kafka's recoverer can restore the original payload when publishing to the DLT.

Therefore, the producer used to send to the DLT must be able to serialize both normal objects and original byte[]. If the DLT template only uses JsonSerializer for one object type, sending raw bytes may fail or be serialized into unwanted JSON.

You can use a serializer supporting multiple types, such as `DelegatingByTypeSerializer`, mapped for byte[] and valid event types. Exact configuration depends on the KafkaTemplate generic type and Spring Kafka/Kafka client version.

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<>());

Serializer<Object> valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

This snippet illustrates the concept of a payload-type-based serializer. Verify constructors and generic signatures in the version you use; some setups require a default serializer for other classes or superclass-based mapping.

### 7.3. DLT headers

When publishing to a DLT, Spring Kafka adds metadata to aid investigation:

- Original topic, partition, and offset.
- Source timestamp.
- Exception class and exception message.
- Stack trace or exception info depending on header configuration.
- Original headers preserved per framework policy.

Avoid stripping deserialization exception headers before the recoverer has a chance to restore raw bytes. If the application manually removes headers or constructs a new record solely from the null payload, the DLT may lose the original data.

### 7.4. Handling errors when publishing to the DLT

DLT publishing can also fail due to broker, authorization, serializer, or network errors. In that case, do not assume the source record was successfully recovered.

Decide:

- Whether the recoverer throws an exception when DLT publish fails.
- Whether the error handler retries recovery.
- Whether the source offset is committed only after DLT publish succeeds per configuration.
- Whether metrics/alerts exist for DLT publish failures.
- How operational workflows handle stuck records.

A DLT is only useful if original data is preserved and operations can detect, analyze, and replay records.

## 8. Configuring ErrorHandlingDeserializer in Spring Boot

Example JSON value configuration:

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
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

This configuration wraps the value deserializer. If the key also uses a deserializer that can fail, configure the key with ErrorHandlingDeserializer and the corresponding key delegate.

Key points to watch:

- The ErrorHandlingDeserializer class name must match the Spring Kafka package.
- The delegate class must be present in runtime dependencies.
- JsonDeserializer trusted packages should be restricted to permitted packages.
- If not using type headers, configure an appropriate default type or type mapping.
- Producer and consumer must agree on schema, encoding, and contract.
- If using multiple consumer factories, apply the configuration to the exact factory used by the listener container.

### 8.1. Configuring delegates via constructor or supplier

Spring Kafka supports creating ErrorHandlingDeserializer with delegates supplied via configuration or code. When complex delegate configuration is needed, you can define a deserializer bean or supplier per the current version's API.

Do not create a single shared delegate that is unsafe across multiple consumers if the implementation holds mutable state. Deserializers are generally instantiated per consumer; respect the lifecycle and thread-safety of the delegate library.

### 8.2. Key and value must be handled separately

The value may be valid while the key fails, or vice versa. If you only configure ErrorHandlingDeserializer for the value, key errors can still cause poll failures.

Example configuring both:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

In this configuration, keys are converted to String and values to JSON events. If the key fails, the listener must not be invoked as if the record had a valid key. The error handler must receive the error details and the DLT must retain raw key bytes if investigation is needed.

## 9. Error classification and recovery design

A practical strategy should separate errors unfixable by retry from temporary errors.

### 9.1. Non-retryable data errors

Example malformed JSON:

~~~json
{"orderId": "O-100", "amount":
~~~

The deserializer cannot convert these bytes into an object. Resending the same record does not make the JSON valid. Appropriate handling is usually:

1. Record the DeserializationException and record position.
2. Route the record with raw bytes to the DLT.
3. Advance the consumer per recoverer policy.
4. Alert the producer owner or contract-owning team.
5. Fix the data source or build a remediation and replay workflow.

### 9.2. Potentially temporary infrastructure errors

For example, the delegate needs to access schema registry, which is temporarily unresponsive. Depending on the root exception, the error may be transient and retrying can help.

However, retries must have limits and backoff. If the schema ID genuinely does not exist, infinite retries only inflate consumer lag.

Classify based on the cause chain, exception type, and delegate library error codes rather than solely on the outermost wrapper being DeserializationException.

### 9.3. Poison pill

A poison pill is a record that a consumer repeatedly cannot process, such as a malformed payload or incompatible schema. Without a recovery mechanism, the record can stall the partition at the same offset and block subsequent records depending on how the error handler operates.

For poison pills:

- Identify the record by topic, partition, offset, and event ID if readable.
- Preserve raw bytes and error headers.
- Avoid infinite retries on the same data.
- Route to a DLT after an appropriate retry policy.
- Alert when the DLT rate rises.
- Replay only after fixing the contract or data.

Never silently discard errors without recording them, as that loses track of unprocessable records.

## 10. Distinguishing deserialization errors from tombstones

A Kafka compacted topic can contain tombstones: records with a key and a null value used to indicate key deletion in compacted streams.

A tombstone is not a DeserializationException. It is a valid record with a null value under Kafka semantics.

With ErrorHandlingDeserializer, a deserialization failure can also result in a null value, but accompanied by an error header. Therefore:

| Case | Value | Deserialization error header | Meaning |
|---|---|---|---|
| Tombstone | null | Absent | Valid key-deletion record |
| Deserialization error | null per wrapper mechanism | Present | Payload bytes could not be converted |
| Valid null-value event per contract | null | Absent | Depends on application semantics |

Listeners or error handlers must check the error header to distinguish them. Do not send every null record to a DLT without determining whether it is a tombstone or a deserialization error.

If an application uses tombstones to delete caches or read models, mistakenly ignoring tombstones causes stale data. Conversely, treating a deserialization-failed record as a tombstone can mistakenly delete business data.

## 11. Observing and diagnosing DeserializationException

### 11.1. Required logs

When the error handler receives a deserialization error, log the following:

- Topic, partition, offset.
- Which field failed: key or value.
- Exception class and cause chain.
- Deserializer delegate in use.
- Event type or schema ID if readable from headers/bytes.
- Raw payload size.
- Correlation ID or trace ID if present.
- DLT destination and publish result.

Do not log full payloads by default. For sensitive data, log only a hash, size, or redacted snippet if permitted by security policy.

### 11.2. Metrics to monitor

| Metric | Meaning |
|---|---|
| Deserialization error count | Number of records failing deserialization |
| Error rate by topic | Which topic has a high error rate |
| Key deserialization failures | Errors on keys |
| Value deserialization failures | Errors on values |
| DLT publish success/failure | Record recovery reliability |
| DLT record rate | Number of records routed to DLT |
| Consumer lag | Impact of errors on group progress |
| Error class distribution | Breakdown of malformed, schema, type mapping, or infrastructure errors |

Metric labels must have low cardinality. Topic, key/value, and exception group are better than event ID or raw message. Do not use offset, key, or payload as metric labels because value counts can grow unboundedly.

### 11.3. Inspecting records in the DLT

When retrieving a record from a DLT, cross-check:

- Dead-letter topic and partition.
- Original topic, partition, and offset.
- Raw key/value bytes.
- Deserialization exception headers.
- Schema/type metadata.
- Producer send timestamp and consumer processing timestamp.
- Consumer application version.

If DLT records are deserialized using the same failing delegate, you may hit exceptions again when reading the DLT. For DLTs containing raw bytes, use a dedicated consumer reading byte[] or a safe deserializer for investigation.

## 12. Production handling procedure for a DeserializationException

1. **Locate the record:** extract topic, partition, offset, group ID, and timestamp from logs/error handler.
2. **Identify key or value:** inspect the corresponding error header and cause chain.
3. **Preserve payload:** verify ErrorHandlingDeserializer retains raw bytes and the recoverer does not drop them.
4. **Classify cause:** malformed JSON, schema mismatch, type header, classpath, encoding, or infrastructure error.
5. **Decide on retry:** retry only when the cause can self-recover; avoid infinite retries on data errors.
6. **Recover:** publish to DLT with raw bytes and source metadata; verify DLT publish succeeded.
7. **Monitor offset:** confirm the group advances past the record after recovery per error handler policy.
8. **Fix source:** update producer contract, schema, type mapping, or data.
9. **Controlled replay:** read the DLT with an appropriate consumer, fix payloads if necessary, and resend to the target topic per procedure.
10. **Close incident:** document root cause, affected record count, and replay outcome.

Do not reset offsets for the entire group just because of a single deserialization-failed record. Handle the specific record per partition and recoverer policy to avoid unintended wide-scale replays.

## 13. Testing ErrorHandlingDeserializer and DLT

You can use Embedded Kafka or a Kafka test broker to test both valid and invalid records.

### 13.1. Valid record

1. Create a test topic.
2. Configure ErrorHandlingDeserializer with a JsonDeserializer delegate.
3. Send valid JSON matching the event class.
4. Verify the listener receives the expected object.
5. Verify no deserialization error header is present.
6. Verify the offset is committed according to acknowledgment mode.

### 13.2. Malformed JSON

1. Send raw bytes that are not valid JSON.
2. Verify ErrorHandlingDeserializer catches the delegate exception.
3. Verify the business listener does not receive a dummy object.
4. Verify the container/error handler receives the error details.
5. Verify the record is routed to the DLT per policy.
6. Read the DLT using ByteArrayDeserializer and verify raw bytes match the source payload.
7. Check source metadata and exception headers.

### 13.3. Key deserialization failure

1. Configure the key with ErrorHandlingDeserializer and an appropriate delegate.
2. Send invalid key bytes per encoding or contract.
3. Verify the key error is recognized separately.
4. Verify the DLT preserves the original key bytes.
5. Verify the record is not misinterpreted as having a valid null key.

### 13.4. DLT publish failure

1. Configure the DLT producer with an incompatible serializer or denied write permissions in test.
2. Send a deserialization-failing record.
3. Verify the recoverer reports the DLT publish error.
4. Verify the source offset does not advance in a way that loses the record.
5. Restore permissions/serializer and test retry/recovery per policy.

### 13.5. Tombstone

1. Send a record with a valid key and null value to a compacted test topic.
2. Verify ErrorHandlingDeserializer does not attach an error header if it is a valid tombstone.
3. Verify the listener or tombstone-handling flow works per contract.
4. Compare against a record with malformed value bytes.

Tests should verify raw payload, metadata, DLT, and committed offsets. Merely checking that an exception was logged is not enough to prove safe record recovery.

## 14. Common implementation mistakes

**Not using ErrorHandlingDeserializer:** the deserializer throws during poll, the listener never receives the record, and the record-level error handler lacks a ConsumerRecord to recover cleanly.

**Wrapping only the value deserializer:** keys can fail deserialization and break poll before the listener is invoked.

**Infinitely retrying malformed payloads:** the same bytes and same delegate keep failing, blocking the partition and increasing lag.

**Not preserving raw bytes:** the DLT contains only null, leaving operations unable to reproduce or fix the payload.

**DLT serializer not supporting byte[]:** the recoverer cannot publish original data after a deserialization failure.

**Overly broad trusted packages:** JsonDeserializer can instantiate objects from unexpected type headers. Restrict trusted packages and use explicit type mappings.

**Confusing tombstones with deserialization failures:** a null value can be a valid deletion record; check error headers before handling.

**Swallowing exceptions in the listener:** if the listener is invoked, catches an error, and returns normally, the container may commit even though business logic did not complete.

**Not distinguishing schema registry outage from schema mismatch:** the two errors have different retry policies.

**Replaying DLT without idempotency:** resending a record that was previously partially processed can produce duplicate side effects.

## 15. Operational principles

- Use ErrorHandlingDeserializer to wrap delegates when you want the listener container to handle deserialization errors at the record level.
- Wrap both key and value if both deserializers can fail.
- Keep delegates, serializers, and schema contracts consistent between producer and consumer.
- Distinguish DeserializationException from message conversion errors and business errors.
- Recognize that malformed/type-mapping errors are normally non-retryable; retry infrastructure errors only with justification.
- Use DefaultErrorHandler with explicit exception classification, bounded backoff, and a clear recoverer.
- Configure the DLT producer to serialize both normal objects and raw byte[].
- Preserve raw bytes, exception metadata, topic, partition, and offset during recovery.
- Distinguish valid tombstones from null payloads caused by deserialization errors using headers.
- Restrict DLT access and retention because payloads may contain sensitive data.
- Monitor error rate, DLT rate, publish failures, and consumer lag.
- Replay only after fixing the root cause and ensuring downstream idempotency.

DeserializationException indicates that the consumer cannot convert record bytes into an object under the current contract. ErrorHandlingDeserializer forwards the error along with the original data to the Spring listener container, where DefaultErrorHandler and DeadLetterPublishingRecoverer can perform controlled retries or persist the record to a DLT. Retaining raw bytes, classifying causes accurately, and ensuring offsets advance only after policy-compliant recovery form the foundation for handling poison pills without silently losing data.
