# Sending Records Without a Key

A Kafka record consists of a topic, key, value, timestamp, and headers. In many messaging flows, a producer can send a record without providing a key. With Spring Kafka, the simplest way is to call `KafkaTemplate.send(topic, value)`. When the key is `null` and the producer does not specify a partition, the partitioner selects the target partition based on metadata and the configured partitioning policy.

Sending records without a key is suitable for independent data that does not require ordering per business entity, such as telemetry, metrics, logs, or notifications that can be processed individually. This approach can help distribute load across multiple partitions and take advantage of batching. In return, the producer cannot rely on a key to keep related records in the same partition; Kafka only guarantees ordering within each partition, not across the entire topic.

This lesson belongs to the **Producer** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; as well as learning serialization, retry, dead-letter, transactions, exactly-once, concurrency, and testing to operate reliable messaging flows.

## 1. What role does the key play in a Kafka record?

A Kafka record can be described by its main components:

| Component | Role |
| --- | --- |
| Topic | Logical data stream to which the record is sent. |
| Partition | Log segment that receives the record; each partition has its own offset sequence. |
| Key | Value the producer can use to route the record to a partition. |
| Value | Business payload or data to be transmitted. |
| Timestamp | Point in time associated with the record. |
| Headers | Additional metadata such as correlation ID, trace ID, or event type. |
| Offset | Position of the record within a partition after the broker persists it. |

Keys are commonly used to group records by business entity. For example, if the key is `orderId`, events for the same order are usually sent to the same partition by the default partitioner. Consumers can read the events for that order in offset order within the partition.

When the key is `null`, the producer provides no identifier for the partitioner to hash and route by entity. The partitioner selects a partition according to its strategy. Therefore:

- Records without a key can still be sent normally.
- Records are still written to a specific partition; Kafka does not store records outside of a partition.
- Consecutive records may be written to different partitions.
- The producer has no affinity guarantee by orderId, customerId, or any other entity without a key or custom partitioner.
- Global ordering across records of the topic is not guaranteed.

## 2. Sending records without a key using KafkaTemplate

Spring Kafka provides a simple overload to send a value without passing a key:

~~~java
@Service
@RequiredArgsConstructor
public class TelemetryPublisher {

    private static final String TOPIC = "telemetry-events";

    private final KafkaTemplate<String, TelemetryEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, TelemetryEvent>> publish(
            TelemetryEvent event) {
        return kafkaTemplate.send(TOPIC, event);
    }
}
~~~

In this example:

- The target topic is `telemetry-events`.
- The value is `TelemetryEvent`.
- The producer does not provide a key.
- KafkaTemplate uses a producer managed by ProducerFactory.
- The value serializer converts the object into bytes before sending.

The generic key type of KafkaTemplate can still be `String` even though this send has no key. The generic type describes the key type the template can handle; it does not force every record to have a non-null key.

A sample event:

~~~java
public record TelemetryEvent(
    String deviceId,
    double temperature,
    Instant measuredAt
) {}
~~~

In this example, the payload has a `deviceId` field, but the producer does not use that field as the Kafka key. The deviceId data still resides in the value and the consumer can read it. However, the default Kafka partitioner does not automatically extract deviceId from inside the JSON payload to select a partition.

This is a point to distinguish: a field inside the payload does not automatically become the record key. To partition by that field, the producer must pass the field as the key or use a custom partitioner capable of reading the corresponding information.

## 3. Explicitly declaring a null key

The `send(topic, value)` form above is clearest when you want to send without a key. If you need to construct a ProducerRecord before sending, you can set the key to `null`:

~~~java
ProducerRecord<String, TelemetryEvent> record =
    new ProducerRecord<>(
        "telemetry-events",
        null,
        event
    );

kafkaTemplate.send(record);
~~~

This constructor takes the topic, key, and value. A null key indicates that the producer does not provide a key for the record.

If you want to specify a partition while still having no key, you can create a ProducerRecord with a specific partition:

~~~java
ProducerRecord<String, TelemetryEvent> record =
    new ProducerRecord<>(
        "telemetry-events",
        2,
        null,
        event
    );

kafkaTemplate.send(record);
~~~

The example above requests sending to partition 2 while the key remains null. The specified partition must exist in the topic. This approach is useful when the application actively coordinates partitions, though it differs from the default partitioner's automatic partition selection behavior.

You should not specify a fixed partition number for every record without a clear reason. That approach can concentrate load on a single partition and reduce parallelism.

## 4. How does the producer choose a partition when the key is null?

If a record has no key and the producer does not specify a partition, the Kafka partitioner selects the target partition. The selection method depends on the configured partitioner and the Kafka client version.

### 4.1. Default partitioner and sticky partitioning

In modern Kafka clients, the default partitioner typically uses sticky partitioning for keyless records. Instead of switching partitions on every single record, the producer tends to keep sending keyless records to the same partition for a period of time or until that partition's batch is sent. Afterward, the partitioner may switch to another partition.

The goal is to accumulate records into larger batches. Each batch is sent more efficiently than scattering individual small records across multiple partitions immediately.

Illustrative example:

~~~text
Topic telemetry-events has 3 partitions

Send batch A:
  Event 1 ─┐
  Event 2 ─┼──> Partition 1 (accumulating batch)
  Event 3 ─┤
  Event 4 ─┘

Batch is sent, partitioner switches selection:

Send batch B:
  Event 5 ─┐
  Event 6 ─┼──> Partition 0 (next batch)
  Event 7 ─┘

A later send batch may use Partition 2.
~~~

This is only an illustration of sticky behavior, not a fixed distribution schedule. You cannot rely on this diagram to predict which partition a specific event will go to.

Sticky partitioning helps improve batching when records have no key and traffic is not high. However, it does not create business entity affinity. When the partitioner switches to another partition, subsequent events may go to a different partition.

In older Kafka clients or when using a custom partitioner, partition selection may differ. Some older versions use keyless distribution strategies different from modern sticky partitioning. Therefore, when you need to understand the exact behavior, check the Kafka client version and the producer's `partitioner.class` property.

### 4.2. Factors affecting partition selection

The partitioner may consider:

- The list of topic partitions known to the client via metadata.
- Which partitions currently have an available leader.
- The state of batches currently being accumulated per partition.
- The record key if the key is not null.
- A partition directly specified by the application.
- The algorithm of a custom partitioner, if present.

If the producer specifies a concrete partition, the partitioner does not need to select one by key. If the producer does not specify a partition and the key is null, the partitioner uses the strategy for keyless records.

Do not interpret this behavior as "Kafka always round-robins every single record." With sticky partitioning, many consecutive records can go to the same partition to form a batch before switching to another partition.

## 5. Null key vs. empty key

A null key and an empty key are two different states:

| Case | Meaning |
| --- | --- |
| Null key | The record has no key. |
| Empty string key `""` | The record has a String key with an empty value; the key is serialized into non-null byte data. |
| Key `"device-01"` | The record has a specific key for routing by the partitioner. |

With an empty key, the partitioner treats it as a non-null key. The default partitioner can hash the serialized key to select a partition. Because identical empty keys are the same, they are usually routed to the same partition within the same partition topology.

Do not replace a null key with an empty string if the goal is for the partitioner to treat the record as keyless. The two approaches can produce different distributions and semantics.

Example:

~~~java
// No key
kafkaTemplate.send("telemetry-events", event);

// Empty string key
kafkaTemplate.send("telemetry-events", "", event);

// Keyed by device
kafkaTemplate.send("telemetry-events", event.deviceId(), event);
~~~

All three calls send the same value type, but they can produce different partitioning behavior.

## 6. How does sending without a key affect ordering?

Kafka guarantees record ordering within the scope of a single partition. A consumer reads a partition in offset order. Kafka does not create a total order across partitions.

When a producer sends without a key, records may be distributed across multiple partitions. Consequently, if two related events are written to two different partitions, the consumer group can process them in parallel and there is no guarantee which event is observed first across the topic.

For example, two events might be written as follows:

~~~text
Partition 0:
  offset 10: DeviceReported(deviceId=A)
  offset 11: DeviceReported(deviceId=C)

Partition 1:
  offset 20: DeviceReported(deviceId=B)
  offset 21: DeviceReported(deviceId=A)
~~~

Two events for device A appear in two different partitions in this illustrative example. Consumers cannot use offsets to infer global ordering between offset 10 and offset 21, because offsets only have meaning within each individual partition.

If business logic requires sequential processing per device, use deviceId as the key or design an appropriate partitioning scheme. If events are independent and can be processed in any order, sending without a key may be appropriate.

Note also that sticky partitioning may keep a group of keyless records on the same partition within a batch, but this is a batching optimization rather than an entity-level ordering guarantee. Do not rely on sticky behavior in place of a key when business logic requires ordering.

## 7. What are the benefits of sending without a key?

### 7.1. Suitable for independent events

Some data does not need grouping by entity to preserve order:

- Periodic metrics from multiple sources.
- Telemetry or sensor readings that can be processed independently.
- Application logs.
- Statistical or clickstream events.
- Broadcast notifications that do not require ordering by a specific entity.

In these cases, consumers can process each record independently, using timestamps or an eventId inside the payload for analysis without requiring a Kafka key.

### 7.2. Can distribute load across multiple partitions

When there is no key, the default partitioner can distribute batches across multiple partitions. This avoids a single hot key concentrating all records onto the same partition.

However, having no key does not guarantee completely even distribution at every point in time. Sticky partitioning keeps records on one partition for a period of time for batching; traffic volume, metadata, partition count, and the partitioner all affect overall distribution.

If the system has a low-traffic producer, several batches may concentrate on one partition in the short term. When more stable load distribution is needed, measure against actual workloads rather than assuming every record will be round-robined.

### 7.3. Leverages batching and reduces overhead

The Kafka producer groups records into batches per partition. When keyless records stick to the same partition, batches can fill up more before being sent. This helps reduce small requests, take advantage of compression, and increase throughput.

Related configurations include:

- `batch.size`: target batch size per partition.
- `linger.ms`: time the producer waits for more records to accumulate a batch.
- `compression.type`: batch compression algorithm.
- `buffer.memory`: producer memory allocated for records waiting to be sent.

Do not increase linger or batch size excessively if the application is latency-sensitive. Tuning must balance latency, throughput, CPU, and memory.

## 8. When should you NOT send records without a key?

Keyless sending is not suitable when the system needs Kafka to route related events to the same partition.

Examples:

- Events changing the state of the same order must be processed in order.
- Transactions of an account must be processed sequentially by accountId.
- Inventory changes for the same SKU must preserve update order.
- Consumers use partition ownership to serialize processing per entity.

If you omit the key in these situations, events for the same entity can go to multiple partitions. Consumers may receive them on different threads, causing order-dependent logic to break.

You can use a stable business key such as `orderId`, `accountId`, or `sku`:

~~~java
kafkaTemplate.send(
    "order-events",
    event.orderId(),
    event
);
~~~

When using a key, records with the same key are usually routed to the same partition by the default partitioner. This is the foundation for preserving order per key, though you still need to account for partition count changes, custom partitioners, and asynchronous consumer-side processing.

If a simple key cannot be used, design a partition key or partitioner according to business requirements. Headers or fields inside a JSON value do not automatically participate in default partitioning.

## 9. Consumers receiving keyless records

Consumers still read records normally even when the key is null. A listener can receive the payload directly if it only needs to process the value:

~~~java
@Component
public class TelemetryListener {

    @KafkaListener(
        topics = "telemetry-events",
        groupId = "telemetry-processor"
    )
    public void onTelemetry(TelemetryEvent event) {
        telemetryService.process(event);
    }
}
~~~

If it needs to inspect the key and metadata, the listener can accept a `ConsumerRecord`:

~~~java
@Component
public class TelemetryListener {

    @KafkaListener(
        topics = "telemetry-events",
        groupId = "telemetry-audit"
    )
    public void onTelemetry(
            ConsumerRecord<String, TelemetryEvent> record) {

        if (record.key() == null) {
            log.debug(
                "Record without key: topic={} partition={} offset={}",
                record.topic(),
                record.partition(),
                record.offset()
            );
        }

        telemetryService.process(record.value());
    }
}
~~~

The consumer can observe topic, partition, offset, timestamp, headers, and key. When the key is null, `record.key()` returns null; the payload may still contain deviceId or its own business identifier.

The consumer group still distributes partitions among consumers through the normal mechanism. Keyless records do not change how offsets are committed or how the group coordinator manages membership.

## 10. Concurrency and consumer scalability

Suppose a topic has four partitions and a consumer group has two consumers. Kafka can assign two partitions to each consumer. Keyless records written to those partitions will be read by the corresponding consumer.

~~~text
Topic telemetry-events
  Partition 0 ──┐
  Partition 1 ──┼──> Consumer A (group telemetry-processor)
  Partition 2 ──┐
  Partition 3 ──┴──> Consumer B (group telemetry-processor)
~~~

The diagram only illustrates one possible assignment. The actual assignment depends on the partition assignor and the consumer group state.

With Spring Kafka, you can increase the listener container's concurrency:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, TelemetryEvent>
        telemetryListenerContainerFactory(
            ConsumerFactory<String, TelemetryEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, TelemetryEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    return factory;
}
~~~

When a listener uses this factory, Spring Kafka creates multiple consumers belonging to the same group. However, useful concurrency does not exceed the number of partitions assigned to the group. If a topic has two partitions and concurrency is six, at most two consumers have partitions to read at any given time.

Sending without a key can help spread load across partitions, but throughput still depends on partition count, broker capacity, producer speed, and consumer processing time.

## 11. Keyless records on compacted topics

Log compaction uses the key to retain the latest state per key. Therefore, a keyless record cannot represent the latest state of an entity under normal compaction mechanisms.

A tombstone in a compacted topic is a record with a non-null key and a null value. A tombstone marks the corresponding key for removal when compaction runs.

It is important to distinguish:

| Record | Meaning in a compacted topic |
| --- | --- |
| Null key, non-null value | No key for compaction to group by entity. |
| Non-null key, non-null value | A version of data for that key. |
| Non-null key, null value | Tombstone for the corresponding key. |
| Null key, null value | Not a tombstone for a specific business key. |

If a topic is designed to store the latest state by accountId or deviceId, the producer needs to send the corresponding key. Keyless sending is better suited for regular event logs, where each record is an independent event and retention is managed by time/size.

## 12. Tracking the actual partition of a record

Do not assume the partition based on the order of send calls. Read the metadata returned upon a successful send:

~~~java
public void publishAndLog(TelemetryEvent event) {
    kafkaTemplate.send("telemetry-events", event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Failed to send telemetry", exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "topic={} partition={} offset={} timestamp={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                metadata.timestamp()
            );
        });
}
~~~

The metadata indicates which topic, partition, and offset the record was written to according to the send result. This is better evidence than guessing the partition by a loop or an unguaranteed rule.

You can inspect the topic with the Kafka CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic telemetry-events
~~~

The describe command shows the partition count and leader/replicas. To observe actual records, you can use the console consumer or an administrative tool capable of displaying key, partition, and offset.

When reading records with the console consumer, enable key printing if you want to confirm null keys. Distinguish a null key value from an empty string; the display format depends on the tool.

## 13. Testing a keyless producer

An integration test should verify:

1. The producer sends the record to the right topic.
2. The record's key is null.
3. The value is serialized properly.
4. The record is written to a valid partition.
5. The consumer can read the payload.
6. The consumer can observe the partition and offset.
7. There are no false assumptions about ordering across multiple partitions.

Example of verifying send metadata:

~~~java
@Test
void shouldPublishTelemetryWithoutKey() throws Exception {
    TelemetryEvent event = new TelemetryEvent(
        "device-01",
        25.4,
        Instant.now()
    );

    SendResult<String, TelemetryEvent> result =
        kafkaTemplate.send("telemetry-events", event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getProducerRecord().key()).isNull();
    assertThat(result.getProducerRecord().value()).isEqualTo(event);
    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("telemetry-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
}
~~~

The test snippet illustrates the Spring Kafka 3.x API, where SendResult provides ProducerRecord and RecordMetadata. With other Spring Kafka versions, check the corresponding API.

For end-to-end testing, you can use Embedded Kafka or Testcontainers. A consumer test should read the record from the topic and assert the payload. If you want to verify a null key on the consumer side, accept a ConsumerRecord and assert that `record.key()` is null.

Do not write tests requiring a keyless record to always go to partition 0 or requiring multiple records to be distributed in an exact round-robin cycle. Partitioning behavior depends on the partitioner, metadata, batching, and Kafka client version. Tests should verify the real guarantees: null key, right topic, valid partition, and accurate payload.

## 14. Common mistakes and misconceptions

| Misconception or mistake | How to understand/investigate |
| --- | --- |
| Passing no key means the record has no partition. | Every written record belongs to a partition; the partitioner chooses the partition if the application does not specify one. |
| Kafka round-robins every record when the key is null. | Modern default partitioners usually use sticky partitioning; behavior also depends on version and configuration. |
| Keyless records always go to the same partition. | Sticky partitioning only keeps a partition for an interval/batch; it may switch partitions afterward. |
| A deviceId field in JSON automatically becomes the key. | The default partitioner only inspects the record key, not fields inside the value. |
| An empty key is equivalent to a null key. | An empty key is a non-null key and can be hashed to select a partition. |
| Keyless still guarantees ordering by entity. | There is no entity affinity; related records may land in multiple partitions. |
| Keyless always distributes evenly. | Distribution depends on sticky behavior, partition availability, load, and the partitioner. |
| A keyless record can be used as a tombstone for an entity. | A tombstone requires a non-null key and a null value. |
| Increasing consumer concurrency always increases throughput. | Partition count and processing capacity limit useful parallelism. |
| Producer send succeeding means the consumer has processed it. | SendResult only reflects the send outcome per acknowledgement; the consumer processes and commits independently. |

## 15. Checklist for deciding whether to send without a key

Before choosing to send records without a key, answer:

1. Are the records independent of each other from a business standpoint?
2. Is ordering required by orderId, accountId, deviceId, or any entity?
3. Can consumers process records from multiple partitions in parallel?
4. Does the topic have enough partitions for the desired throughput and concurrency?
5. Is the default partitioner suitable, or is explicit partition/custom partitioner selection needed?
6. Is it necessary to log the partition and offset for traceability?
7. Does the topic use log compaction or require key-based tombstones?
8. Do the producer and consumer handle duplicates/idempotency appropriately?
9. Do tests verify that the key is actually null without assuming a fixed partition?
10. Does the system have metrics to observe partition distribution and consumer lag?

Sending records without a key is a valid choice when each event can be processed independently and entity-based routing is not needed. This approach lets the partitioner optimize distribution and batching, though the application must accept that ordering only exists within each partition and there is no entity-level affinity guarantee. When business logic requires sequential ordering for an entity, pass a stable key or design a purposeful partitioner.

