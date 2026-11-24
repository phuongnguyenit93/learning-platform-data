# BatchMessagingMessageConverter

When using a batch listener in Spring Kafka, a single `poll()` can return multiple `ConsumerRecord` instances. The application can either receive that list of records directly or let Spring convert it into a Spring `Message` whose payload is a list of values with matching headers. `BatchMessagingMessageConverter` handles the latter conversion step.

This converter is particularly useful when a listener wants to accept `List<OrderCreated>`, `Message<List<OrderCreated>>`, or `List<Message<OrderCreated>>` instead of manually unpacking each `ConsumerRecord`. It also gathers metadata such as key, topic, partition, offset, and timestamp into lists aligned with the payload order, helping the application trace every element in the batch.

An important distinction: `BatchMessagingMessageConverter` converts message representation inside Spring Kafka. It does not determine how many records are fetched, does not enlarge Kafka producer batches, and does not create atomic processing guarantees for the batch. Batch size, poll cadence, commits, and error handling remain governed by the consumer, listener container, and application policy.

## 1. What does BatchMessagingMessageConverter do?

`BatchMessagingMessageConverter` is an implementation of `BatchMessageConverter`. It takes a list of `ConsumerRecord` instances from the listener container, extracts each record's value into a payload collection, and maps each record's metadata into Kafka headers on a Spring `Message`.

Example batch with three records:

```text
ConsumerRecords in a single poll
  record 0: key=order-10, partition=0, offset=120, value=...
  record 1: key=order-11, partition=1, offset=88,  value=...
  record 2: key=order-12, partition=0, offset=121, value=...
                    |
                    v
       BatchMessagingMessageConverter
                    |
                    v
Message<List<OrderCreated>>
  payload: [event-10, event-11, event-12]
  RECEIVED_KEY:       [order-10, order-11, order-12]
  RECEIVED_PARTITION: [0, 1, 0]
  OFFSET:             [120, 88, 121]
```

An element's position in each header list corresponds to the payload's position. Thus, `payload.get(1)`, `keys.get(1)`, `partitions.get(1)`, and `offsets.get(1)` all describe the second record in the batch.

If a `RecordMessageConverter` is passed to the constructor, `BatchMessagingMessageConverter` uses it to convert each record before placing its value into the payload list. This supports signatures such as `List<OrderCreated>` when the Kafka consumer originally receives JSON as `String`, `byte[]`, or `Bytes`.

## 2. Distinguishing conversion layers in the batch flow

A batch message passes through several layers, each with a distinct responsibility:

| Component | Responsibility |
|---|---|
| Kafka `Deserializer` | Converts key/value bytes into Java types received by the consumer |
| `RecordMessageConverter` | Converts a single `ConsumerRecord` into a Spring `Message` or converts record payload to a target type |
| `BatchMessagingMessageConverter` | Converts a list of `ConsumerRecord` into a Spring `Message` with a collection payload and list-based headers |
| `@KafkaListener` argument resolver | Binds converted payloads/headers to listener method parameters |
| Listener container | Manages polling, listener invocation, rebalances, acknowledgements, and commits |

For example, if the consumer uses `StringDeserializer`, each record's value is a JSON string. `StringJsonMessageConverter` converts each JSON string into `OrderCreated`; `BatchMessagingMessageConverter` collects those objects into `List<OrderCreated>`.

```text
Kafka byte[]
    |
    v
StringDeserializer
    |
    v
JSON String in ConsumerRecord
    |
    v
StringJsonMessageConverter (per record)
    |
    v
OrderCreated
    |
    v
BatchMessagingMessageConverter (whole batch)
    |
    v
Message<List<OrderCreated>> + batch headers
```

If the consumer already uses `JsonDeserializer<OrderCreated>` and receives `OrderCreated` objects directly from the Kafka client, the batch converter does not need to parse JSON again. You can then use `BatchMessagingMessageConverter` without passing a record converter to collect the already-deserialized values and their headers.

## 3. Enabling batch listener on the container factory

For a listener to receive multiple records in one call, the container factory must enable batch mode via `setBatchListener(true)`. Then configure the batch converter using `setBatchMessageConverter(...)`.

The example below uses Spring Kafka 3.3.x, where JSON is read as a `String` by the Kafka client and converted into objects using `StringJsonMessageConverter`:

```java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setBatchMessageConverter(
                new BatchMessagingMessageConverter(
                        new StringJsonMessageConverter()));
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
```

`setBatchListener(true)` instructs the listener container to invoke the method in batches. `setBatchMessageConverter(...)` sets the converter used to turn the record list into a Spring `Message`. `setConcurrency(3)` creates up to three consumers for the container; how many consumers actually receive partitions still depends on partition count and the consumer group.

If the listener only needs `List<ConsumerRecord<String, String>>`, it can receive the record list directly without a batch message converter. The converter is helpful when you want payloads and headers modeled via Spring Messaging.

## 4. Configuring a compatible deserializer

Because the example above uses `StringJsonMessageConverter`, the consumer needs to receive values as `String`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-batch-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        "[max.poll.records]": 300
    listener:
      type: batch
      ack-mode: batch
```

`max.poll.records` caps the maximum number of records returned in one poll, not the byte size of the batch. In the Java configuration above, `setBatchListener(true)` and `AckMode.BATCH` were set directly on the factory; if using Spring Boot's auto-configured setup, `spring.kafka.listener.type: batch` and `ack-mode: batch` can configure the default listener. Avoid configuring conflicting values in both places.

If the consumer uses `JsonDeserializer<OrderCreated>` instead of `StringDeserializer`, the `ConsumerRecord` value is already `OrderCreated`. The batch converter configuration can then be simpler:

```java
factory.setBatchListener(true);
factory.setBatchMessageConverter(new BatchMessagingMessageConverter());
```

The converter's no-arg constructor uses a default record converter for message mapping (as of Spring Kafka 3.3.11); it does not automatically turn an arbitrary JSON string into a domain object. To parse JSON from `String`, pass `StringJsonMessageConverter` as shown in the main example. In older versions, the no-arg constructor has no default record converter; when JSON conversion is required, pass the converter explicitly.

## 5. Receiving List<Foo> and batch headers

When the batch converter has a `RecordMessageConverter`, the listener can declare its payload parameter as a single-type-parameter collection, such as `List<OrderCreated>`. Spring uses that generic type as the target type for each record.

```java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-batch-reader",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onOrders(
            List<OrderCreated> events,
            @Header(KafkaHeaders.RECEIVED_KEY) List<String> keys,
            @Header(KafkaHeaders.RECEIVED_PARTITION) List<Integer> partitions,
            @Header(KafkaHeaders.OFFSET) List<Long> offsets) {

        for (int i = 0; i < events.size(); i++) {
            orderService.handle(
                    events.get(i), keys.get(i), partitions.get(i), offsets.get(i));
        }
    }
}
```

Important list headers:

| Header | Common type in batch listeners | Meaning |
|---|---|---|
| `KafkaHeaders.RECEIVED_KEY` | `List<String>` | Key of each record |
| `KafkaHeaders.RECEIVED_TOPIC` | `List<String>` | Topic of each record |
| `KafkaHeaders.RECEIVED_PARTITION` | `List<Integer>` | Partition of each record |
| `KafkaHeaders.OFFSET` | `List<Long>` | Offset of each record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | `List<Long>` | Timestamp of each record |
| `KafkaHeaders.RECEIVED_TIMESTAMP_TYPE` | `List<String>` | Timestamp type returned by Kafka |

Header lists are aligned with the payload order. Check list sizes and header presence before indexing if your application uses a custom converter or header mapper. Do not assume all records in a batch come from the same partition: a single poll can contain records from multiple partitions.

## 6. Receiving Message<List<Foo>> to group payloads and headers

If you want to receive the entire payload along with Spring headers in one parameter, the listener can use `Message<List<OrderCreated>>`:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(Message<List<OrderCreated>> message) {
    List<OrderCreated> events = message.getPayload();

    List<Long> offsets = message.getHeaders()
            .get(KafkaHeaders.OFFSET, List.class);
    List<Integer> partitions = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, List.class);

    for (int i = 0; i < events.size(); i++) {
        process(events.get(i), partitions.get(i), offsets.get(i));
    }
}
```

This signature is convenient when reading multiple headers, accessing the payload as a block, or passing the Spring `Message` to another processing layer. When using the generic `Message<List<OrderCreated>>`, the converter still relies on inferring the element type from the payload's generic parameter.

## 7. Receiving List<Message<Foo>> to keep per-record headers

In some scenarios, each record must be processed as an independent Spring `Message` with its own payload and headers. You can declare `List<Message<OrderCreated>>` if the record converter supports this type:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-message-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrderMessages(List<Message<OrderCreated>> messages) {
    for (Message<OrderCreated> item : messages) {
        String key = item.getHeaders()
                .get(KafkaHeaders.RECEIVED_KEY, String.class);
        Integer partition = item.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = item.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        process(item.getPayload(), key, partition, offset);
    }
}
```

This approach is useful when each record has distinct business headers or metadata and the handler wants a complete message object. In return, it allocates an extra `Message` object per record, which can increase memory allocation overhead compared to `List<Foo>` with list headers.

Do not confuse `List<Message<Foo>>` with a single `Message<List<Foo>>`: the first creates a separate message per record, whereas the second wraps the entire batch in one message.

## 8. Using RecordMessageConverter to convert individual records

The `BatchMessagingMessageConverter(RecordMessageConverter)` constructor lets you specify how each record is converted—for example, from a JSON string to a POJO:

```java
@Bean
public BatchMessageConverter orderBatchMessageConverter() {
    RecordMessageConverter recordConverter =
            new StringJsonMessageConverter();
    return new BatchMessagingMessageConverter(recordConverter);
}
```

When the listener declares `List<OrderCreated>`, the converter extracts the generic type `OrderCreated` and converts each record value to that type. This enables listeners to receive domain objects while the Kafka consumer still uses `StringDeserializer`.

If the producer sends Spring Kafka type headers, the JSON converter can use a type mapper to determine the type. By default, the target type is typically inferred from the listener parameter (`INFERRED`). When you need to prioritize the type ID in headers, configure type precedence to `TYPE_ID` using the type mapper API appropriate for your version. Ensure type mapping and trusted packages are controlled and that producer and consumer agree on the contract.

Inferring types from listener parameters works most cleanly when `@KafkaListener` is placed directly on a method. With a class-level `@KafkaListener` combined with multiple `@KafkaHandler` methods, Spring must convert the payload first in order to select the right handler; in that case, type metadata in headers or explicit type mapper configuration is required to resolve the right type.

For Spring Kafka 4.x, JSON converter classes are renamed for Jackson 3, such as `JacksonJsonMessageConverter` and its variants. The `StringJsonMessageConverter` examples in this lesson use the Spring Kafka 3.3.x API. Choose the converter matching your project's major version.

## 9. Header mapping and raw ConsumerRecord

The batch converter maps Kafka record headers into Spring `Message` headers. If your application uses custom headers, you can configure a dedicated `KafkaHeaderMapper`:

```java
BatchMessagingMessageConverter converter =
        new BatchMessagingMessageConverter(new StringJsonMessageConverter());
converter.setHeaderMapper(new DefaultKafkaHeaderMapper());
```

Only replace the header mapper when you need explicit control over which header types cross the Kafka/Spring boundary. Some headers may be complex Java types; define explicit mapping and serialization rules to avoid errors when producer and consumer use different languages or versions.

If the listener needs access to the original `ConsumerRecord` list after the converter builds the payload, enable the raw record header:

```java
BatchMessagingMessageConverter converter =
        new BatchMessagingMessageConverter(new StringJsonMessageConverter());
converter.setRawRecordHeader(true);
```

When enabled, the converter adds `List<ConsumerRecord<?, ?>>` under the `KafkaHeaders.RAW_DATA` header. The listener can read that header for original metadata or pass records to a component expecting Kafka APIs. The values and keys inside `ConsumerRecord` remain the data produced after Kafka deserialization; the raw record header does not automatically preserve raw pre-deserialization bytes.

## 10. Batch converter does not control batch size

`BatchMessagingMessageConverter` only converts the records the container has already received from the consumer. Batch size and cadence are governed by Kafka consumer settings and data availability:

| Property | Role | Impact |
|---|---|---|
| `max.poll.records` | Maximum records returned in one poll | Caps batch element count at the consumer level |
| `fetch.min.bytes` | Bytes the broker tries to accumulate before returning a fetch response | Can improve fetch efficiency under high load at the cost of wait time |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy fetch when data is insufficient | Affects fetch latency under low load |
| `fetch.max.bytes` | Byte limit for a fetch response | Caps overall fetched data |
| `max.partition.fetch.bytes` | Byte limit fetched from a single partition | Affects data retrieved per partition |
| `max.poll.interval.ms` | Maximum gap between two polls | Must be large enough for batch processing duration |
| `concurrency` | Number of consumers in the listener container | Increases parallel processing across partitions |

A batch can be smaller than `max.poll.records` because the broker does not yet have enough records or the consumer is assigned only a subset of partitions. The converter does not pull additional records from the next poll, nor does it split a batch into smaller batches.

If a listener takes too long to process a batch, the consumer may exceed `max.poll.interval.ms` and be deemed non-progressing. Balance `max.poll.records`, per-record processing time, concurrency, and downstream timeouts. Simply increasing `max.poll.interval.ms` will not fix stalled queues or unbounded processing.

## 11. A batch can contain multiple partitions

One poll can return records from multiple partitions assigned to the same consumer. Records within each partition keep their offset order, yet there is no guaranteed global order across partitions.

Example batch:

```text
Index 0: partition 0, offset 10
Index 1: partition 1, offset 25
Index 2: partition 0, offset 11
Index 3: partition 2, offset 7
```

Do not assume offsets increase monotonically across the entire batch. If business logic requires ordering per aggregate, the producer must route events for the same aggregate to the same partition using a stable key. In the listener, use `RECEIVED_PARTITION` and `OFFSET` to trace each record accurately.

When concurrency is enabled, each child consumer processes the set of partitions assigned to it. Concurrency does not let the same partition be processed simultaneously by multiple consumers in the same group. Increasing concurrency helps only when there are enough partitions and downstream systems can handle the load.

## 12. Handling payload conversion errors

Several kinds of errors can occur in a batch pipeline:

| Error type | Where it occurs | How to handle |
|---|---|---|
| Kafka deserialization error | Before `poll()` returns records to the listener | Use `ErrorHandlingDeserializer`, inspect exception headers, and configure an error handler |
| Message conversion error | When `RecordMessageConverter` converts a value to the listener's target type | Check `KafkaHeaders.CONVERSION_FAILURES` and pinpoint the failed index |
| Business validation/processing error | Inside the listener method | Identify the failed record, throw `BatchListenerFailedException` if the index is known, or apply a suitable batch retry policy |

When a record fails conversion in the batch converter, its corresponding slot in the payload list may be `null`; the exception is recorded at the same index in `KafkaHeaders.CONVERSION_FAILURES`. Listeners should inspect this header before processing payloads so a `null` from a conversion failure is not mistaken for a valid tombstone.

Example detecting conversion errors:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<OrderCreated> events,
        @Header(KafkaHeaders.CONVERSION_FAILURES)
        List<ConversionException> conversionFailures) {

    for (int i = 0; i < events.size(); i++) {
        ConversionException failure = conversionFailures.get(i);
        if (failure != null) {
            throw new BatchListenerFailedException(
                    "Failed to convert record at index " + i, failure, i);
        }

        process(events.get(i));
    }
}
```

`KafkaHeaders.CONVERSION_FAILURES` holds a per-element list of failures; if no failure occurred at an index, that entry is `null`. Verify this API and exception type against the Spring Kafka version you are using.

## 13. Deserialization errors with ErrorHandlingDeserializer

The deserializer runs before the listener container can invoke the listener method. Consequently, if the deserializer throws an exception, the listener cannot catch it with a normal `try/catch` inside the payload loop.

With batch listeners using `ErrorHandlingDeserializer`, deserialization errors are stored in record headers. The batch converter places per-record converted headers into `KafkaHeaders.BATCH_CONVERTED_HEADERS`, a list of maps indexed identically to the batch. You can inspect exception headers to identify the failed record.

The `BATCH_CONVERTED_HEADERS` header is populated when the converter uses a `KafkaHeaderMapper` to map native Kafka headers to Spring headers. Without a mapper, the converter may retain native headers in `KafkaHeaders.NATIVE_HEADERS`; verify the header mapper configuration before assuming `BATCH_CONVERTED_HEADERS` is always present.

Illustrative example checking headers and reporting an error at the exact index:

```java
@KafkaListener(topics = "orders.created", groupId = "order-batch-reader")
public void onOrders(
        List<OrderCreated> events,
        @Header(KafkaHeaders.BATCH_CONVERTED_HEADERS)
        List<Map<String, Object>> convertedHeaders) {

    for (int i = 0; i < events.size(); i++) {
        Map<String, Object> headers = convertedHeaders.get(i);
        Object deserFailure = headers.get(
                SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);

        if (deserFailure != null) {
            throw new BatchListenerFailedException(
                    "Failed to deserialize record at index " + i,
                    new IllegalStateException("Value deserialization failed"), i);
        }

        process(events.get(i));
    }
}
```

Example consumer configuration wrapping `JsonDeserializer` with `ErrorHandlingDeserializer`:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
```

In this setup, the Kafka client attempts to deserialize JSON into `OrderCreated`; if the delegate fails, `ErrorHandlingDeserializer` preserves the exception and raw bytes in record headers for the batch listener/error handler. Conversely, when using `StringDeserializer` with `StringJsonMessageConverter`, JSON syntax errors occur during message conversion and appear in `KafkaHeaders.CONVERSION_FAILURES`.

In real applications, deserialize the header bytes into a `DeserializationException` using the appropriate `SerializationUtils` API to log or route the cause and raw data to a DLT. For key errors, also check `SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER`. When using `DeadLetterPublishingRecoverer`, the producer needs serializers capable of handling both domain payloads and raw `byte[]` from failed records.

## 14. Handling partial batch failures

A batch listener can process multiple records in one invocation. If the third record fails after the first two succeeded, the application must tell the container which index failed so it can retry/recover the remainder accurately.

Spring Kafka supports `BatchListenerFailedException` to pinpoint the failing record by its index in the batch:

```java
@KafkaListener(topics = "orders.created", groupId = "order-batch-reader")
public void onOrders(List<OrderCreated> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            orderService.handle(events.get(i));
        } catch (TransientOrderException ex) {
            throw new BatchListenerFailedException(
                    "Order processing failed at index " + i, ex, i);
        }
    }
}
```

When using a batch-aware error handler such as `DefaultErrorHandler`, the index helps the framework determine which records succeeded and which need seeking/retrying or recovery. If the listener throws a regular exception without identifying the failed record, the framework may have to fall back to retrying the entire batch, which can reprocess earlier records.

Throwing `BatchListenerFailedException` does not automatically roll back earlier side effects. If the listener already wrote to the database for the first two records before failing, those changes persist unless wrapped in an appropriate transaction. Use idempotency or transactions for side effects, and report an accurate index only when the application knows which record failed.

## 15. Acknowledgment and offset commit

With batch listeners, `AckMode` controls when the container commits offsets for processed records. `AckMode.BATCH` is a common choice: the container commits after the entire poll batch completes successfully. If the listener fails, the error handler governs retries, recovery, and commit progress according to batch policy.

Key principles:

- Do not commit the whole batch's offsets before processing completes if you want to avoid skipping failed records.
- When using `MANUAL` or `MANUAL_IMMEDIATE`, acknowledge only after the batch or corresponding work unit is completed as designed.
- When using `BatchListenerFailedException` with a supporting error handler, provide the exact index so the framework can handle succeeded and failed portions properly.
- If the listener processes in parallel, track completion per partition and never commit past records that are still running.

Example manual acknowledgment for a batch:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "manualBatchListenerContainerFactory")
public void onOrders(
        List<OrderCreated> events,
        Acknowledgment acknowledgment) {

    orderService.handleBatchAndPersist(events);
    acknowledgment.acknowledge();
}
```

This listener's factory must be configured with `MANUAL` or `MANUAL_IMMEDIATE` AckMode accordingly. Only call `acknowledge` after the work to be confirmed has finished. If batch processing is non-atomic and can partially succeed, clearly define checkpoint storage and retry behavior before adopting manual acks.

## 16. Header lists and null/tombstone data

In compacted topics, a record with a key and a `null` value can act as a tombstone marking key deletion. This is still a valid record in the batch. Do not discard all `null` elements without checking why they are null.

At least three cases must be distinguished:

1. An intentional `null` value from the producer, such as a tombstone.
2. A `null` value returned by `ErrorHandlingDeserializer` when deserialization fails, accompanied by an exception header.
3. A `null` payload produced when `BatchMessagingMessageConverter` fails conversion, accompanied by `KafkaHeaders.CONVERSION_FAILURES`.

Inspect error headers before deciding how to handle `null`. For tombstones, the listener should perform key-deletion logic; for deserialization or conversion errors, retry, route to a DLT, or halt according to error policy.

## 17. Custom SmartMessageConverter and header mapper

In Spring Kafka versions supporting `setMessagingConverter(...)`, `BatchMessagingMessageConverter` can use a Spring Messaging `SmartMessageConverter` to convert payloads based on content type or custom conversion rules. This is useful when the application converts based on `MessageHeaders.CONTENT_TYPE` or reuses Spring Messaging conversion logic.

```java
BatchMessagingMessageConverter batchConverter =
        new BatchMessagingMessageConverter(new MessagingMessageConverter());
batchConverter.setMessagingConverter(mySmartMessageConverter);
factory.setBatchMessageConverter(batchConverter);
```

`setMessagingConverter` was added in newer versions (as of Spring Kafka 3.3.11). If your project uses an older version, use an appropriate `RecordMessageConverter` or upgrade the library before calling this API. You do not need an extra `SmartMessageConverter` if `StringJsonMessageConverter` already handles your payload types.

## 18. Outbound limitation

`BatchMessagingMessageConverter` is designed for the inbound batch-listener path. Although the `BatchMessageConverter` interface defines `fromMessage(...)`, this implementation does not support converting a Spring `Message<?>` into a list of `ProducerRecord` instances and throws `UnsupportedOperationException` if called. Therefore, do not use it as an outbound converter for `KafkaTemplate.send(Message<?>)`.

If you need to send multiple records, create individual `ProducerRecord` instances and send them via `KafkaTemplate` or the Kafka producer using the appropriate API. The Kafka producer automatically groups records per partition into network batches based on `batch.size`, `linger.ms`, and other producer settings. If business requirements demand multiple records commit or abort together, use Kafka transactions; the batch converter provides no atomic guarantees.

## 19. Testing BatchMessagingMessageConverter

Test conversion logic separately as well as the full batch listener flow.

### Unit testing conversion

Verify the converter builds a payload list in the right order with the right element types, and that header lists have matching lengths. For JSON converters, test valid payloads, Unicode, incompatible fields, and malformed JSON. If using a custom header mapper, verify required headers are preserved.

### Integration testing with a test Kafka broker

An integration test should:

1. Start a test broker and create a topic with multiple partitions.
2. Send multiple records with different keys so data lands across multiple partitions.
3. Use a batch listener factory with `setBatchListener(true)` and `BatchMessagingMessageConverter`.
4. Verify the listener receives a collection with the expected payloads and metadata.
5. Test `List<Foo>`, `Message<List<Foo>>`, or `List<Message<Foo>>` according to your target signature.
6. Send a record with invalid JSON or undeserializable payload to verify conversion/deserialization failure handling.
7. Verify `BatchListenerFailedException` pinpoints the right index and the error handler retries/recovers as designed.
8. Verify offset commits after a successful batch, a failed batch, and shutdown.

Suggested test matrix:

| Case | Expectation |
|---|---|
| Batch with all valid records | Payload list preserves order and full element count |
| Multi-partition batch | Partition/offset headers match each payload |
| Invalid JSON | Conversion failure detected at the exact index |
| Deserializer failure | Exception header/raw data handled via error handler |
| Single business record failure | Correct record retried/recovered when index is supplied |
| Tombstone | Intentional null handled per contract |
| Poll with no records | Listener container does not invoke the batch listener for empty polls; do not expect an empty `List` |
| Listener with concurrency | Each consumer processes its assigned partitions without sharing mutable state |

## 20. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Listener receives individual records instead of a List | Factory has not enabled batch listener or endpoint uses another factory | Check `setBatchListener(true)` and `containerFactory` |
| Payload remains String/byte[] | Missing `RecordMessageConverter` to convert JSON to target type | Configure `BatchMessagingMessageConverter(new StringJsonMessageConverter())` or a POJO deserializer |
| Header is scalar instead of List | Listener runs in record mode or uses a different parameter type | Verify batch mode and listener signature |
| Payload and header indexes misaligned | Custom converter or handler filtered one list without filtering metadata lists identically | Keep index alignment or switch to `List<Message<Foo>>` |
| One bad record retries the whole batch | Failed index not supplied or error handler falls back to batch retry | Throw `BatchListenerFailedException` with the exact index |
| `NullPointerException` on null element | Tombstone not distinguished from conversion/deserialization failure | Inspect `CONVERSION_FAILURES` and `BATCH_CONVERTED_HEADERS` |
| Oversized batch times out listener | High `max.poll.records` or slow downstream processing | Shrink batch, scale processing capacity, or adjust poll interval with justification |
| Increasing concurrency does not increase throughput | Not enough partitions or downstream is the bottleneck | Inspect assignment, lag, CPU, and connection pools |

## Pre-production checklist for batch converters

- Factory enables `setBatchListener(true)` and the endpoint references the right factory.
- `BatchMessagingMessageConverter` and `RecordMessageConverter` are compatible with the deserializer.
- Listener generic type is a collection with a clear single element type.
- Header lists are indexed in alignment with the payload list.
- Understood that a batch may contain records from multiple partitions with no global ordering.
- `max.poll.records`, `max.poll.interval.ms`, concurrency, and processing time are balanced.
- Conversion failures and deserialization failures are distinguished, with proper retry/DLT paths.
- `BatchListenerFailedException` provides the exact index for partial-failure handling.
- Acknowledgements/commits happen only after the defined processing boundary.
- Intentional nulls/tombstones are distinguished from conversion or deserialization failure nulls.
- Metrics exist for batch size, processing duration, retries, DLT, and consumer lag.
- Tested with multi-partition batches, partial failures, tombstones, and multiple consumer instances.

`BatchMessagingMessageConverter` lets batch listeners work with payloads and metadata in the Spring Messaging model. When paired cleanly with the right record converter, deserializer, header mapping, and error handling, applications can process multiple records per listener invocation while tracing every record, controlling partial failures, and committing offsets safely.
