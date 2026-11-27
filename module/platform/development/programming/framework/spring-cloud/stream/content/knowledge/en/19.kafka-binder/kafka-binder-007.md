# Mapping KafkaHeaders and Topic, Partition, and Offset Metadata

When Spring Cloud Stream receives a record from Kafka, the application often only needs the payload for business processing. However, many operational tasks need to know which topic, which partition, and what offset the record came from: logging for traceability, detecting duplicate processing, investigating errors, reconciling consumer progress, or forwarding events while preserving the message key.

The Kafka binder integrates with Spring Kafka to translate Kafka record metadata into Spring Message headers. The **KafkaHeaders** class provides constants to access these headers without hardcoding string names manually. On the outbound side, special headers also let you specify the message key, target topic, or receive metadata after the broker confirms a successful send.

This lesson focuses on reading and using topic, partition, and offset metadata; distinguishing Spring Message headers from Kafka record headers; and tracking outbound record metadata.

## 1. Kafka Records and Spring Messages

A Kafka record has these primary components:

- **Topic:** the data stream the record was written to.
- **Partition:** the specific partition within the topic.
- **Offset:** the position of the record within that partition.
- **Key:** optional key used for routing and preserving ordering per partition.
- **Value:** the record's payload.
- **Timestamp:** the timestamp attached to the record according to Kafka's timestamp type.
- **Headers:** a set of key/value metadata sent by the producer alongside the record.

Spring Cloud Stream converts the record into a Spring `Message` for the function to process. A Spring `Message` contains a payload and Spring Messaging headers. When receiving a record, the Kafka binder/Spring Kafka adds special headers to represent record metadata, such as received topic, received partition, and offset.

~~~mermaid
flowchart LR
    A[Kafka record] --> B[Kafka binder and Spring Kafka]
    B --> C[Spring Message]
    C --> D[Function or Consumer]
    C --> E[Payload]
    C --> F[Message headers]
    F --> G[Topic]
    F --> H[Partition]
    F --> I[Offset]
    F --> J[Timestamp and key]
~~~

Key takeaway: the payload holds business data; metadata lives in headers. For instance, `OrderCreated` may contain `orderId` and `total`, whereas topic/partition/offset describe the record's transport position in Kafka. You do not need to add these fields to business JSON solely for logging or checking record position.

## 2. What Is KafkaHeaders?

**org.springframework.kafka.support.KafkaHeaders** is a class containing header constants for Spring Kafka integration. The Kafka binder uses these headers when mapping between Spring `Message` and Kafka records.

Commonly used headers:

| Constant | Direction | Meaning |
|---|---|---|
| **KafkaHeaders.RECEIVED_TOPIC** | Inbound | The topic from which the record was received. |
| **KafkaHeaders.RECEIVED_PARTITION** | Inbound | The partition containing the received record. |
| **KafkaHeaders.OFFSET** | Inbound | The offset of the received record within the partition. |
| **KafkaHeaders.RECEIVED_TIMESTAMP** | Inbound | The timestamp of the received record. |
| **KafkaHeaders.RECEIVED_KEY** | Inbound | The key of the received record, if present. |
| **KafkaHeaders.TOPIC** | Outbound | Target topic when the binder is configured to allow using the topic header. |
| **KafkaHeaders.MESSAGE_KEY** | Outbound | The key sent with the record. |
| **KafkaHeaders.PARTITION** | Outbound | Target partition in outbound flows supporting partition specification. |
| **KafkaHeaders.RECORD_METADATA** | Send result | `RecordMetadata` returned by the Kafka client after a successful send. |
| **KafkaHeaders.ACKNOWLEDGMENT** | Inbound | The `Acknowledgment` object when the binding uses manual acknowledgement mode. |

Inbound headers like `RECEIVED_TOPIC` and `RECEIVED_PARTITION` are populated from record metadata; they are not fields that business producers need to manually add to Kafka record headers.

### Notes on Constant Names by Version

Spring Kafka constant names changed across certain versions:

- Starting in Spring Kafka 2.9, **RECEIVED_PARTITION** replaced the old **RECEIVED_PARTITION_ID**; the old name is marked deprecated in the corresponding versions.
- Starting in Spring Kafka 2.9, **RECEIVED_KEY** replaced **RECEIVED_MESSAGE_KEY**; the old name is marked deprecated.
- In older versions, source code may need to use the older constant names.

Use the constants provided by the Spring Kafka dependency managed by your project's Spring Cloud Stream BOM. Do not hardcode internal strings like `kafka_receivedPartition` or `kafka_receivedTopic` when constants are available, as names and aliases can vary across versions.

## 3. Reading Topic, Partition, and Offset from Consumer<Message<T>>

In the functional model, a `Consumer` can accept the full `Message` to access both the payload and headers:

~~~java
import java.util.function.Consumer;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderMetadataFunctions {

    @Bean
    public Consumer<Message<OrderCreated>> inspectOrderRecord() {
        return message -> {
            String topic = message.getHeaders()
                    .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
            Integer partition = message.getHeaders()
                    .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
            Long offset = message.getHeaders()
                    .get(KafkaHeaders.OFFSET, Long.class);

            OrderCreated event = message.getPayload();
            log.info(
                    "Received orderId={}, topic={}, partition={}, offset={}",
                    event.orderId(), topic, partition, offset
            );
        };
    }
}
~~~

In this example, the function reads three values:

- **topic** is the source topic name.
- **partition** is the partition index containing the record.
- **offset** is the record's position within that partition.

Do not cast every header to `String`. An offset is a 64-bit integer and a partition is an integer; read the exact types provided by Spring Kafka. If compatibility across multiple versions or custom header mappers is needed, verify the actual types in an integration test.

An example binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: inspectOrderRecord
    stream:
      bindings:
        inspectOrderRecord-in-0:
          destination: orders
          group: order-audit
          content-type: application/json
~~~

With the binding above, the consumer receives data from the `orders` topic. Metadata values come from the actual record delivered by Kafka, not from the binding name. The binding name is `inspectOrderRecord-in-0`; the topic name is `orders`. These two names serve different purposes.

### When the Key Can Be Null

Kafka allows records without keys. When the key is `null`, the received key header may be absent from the Spring `Message`. Therefore, read the key as an optional header:

~~~java
Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
if (key == null) {
    log.debug("Record has no key");
}
~~~

Do not treat a `null` key as a default identifier across events. If idempotency or business-based partitioning is required, the producer must emit a meaningful key and the consumer must check for missing keys.

## 4. Meaning of Topic, Partition, and Offset

These three fields are typically logged together to identify a record's exact position:

~~~text
topic = orders
partition = 2
offset = 18427
~~~

This can be read as the record at offset 18427 of partition 2 in the `orders` topic.

### Topic

A topic is the logical data stream name. An application can read from multiple topics via multiple input bindings or via a binding configured with a pattern. Topic metadata tells you which topic a record actually came from, which is useful when one binding reads multiple topics or uses a pattern.

### Partition

A partition is the unit of storage and parallelism inside a topic. Partition indices typically start at 0. Kafka guarantees record ordering within a single partition, not global ordering across multiple partitions.

The partition helps determine:

- Which consumer in the group was assigned to process the record.
- The ordering boundary guaranteed by Kafka.
- Where to inspect when a partition lags or loses its leader.
- The record's location during investigation or data replay.

### Offset

An offset is a record's position within a partition. It increases as records are written to the partition, but it is not a global sequence number across the topic.

Points to remember:

- An offset only has meaning together with its topic and partition.
- Two different partitions can both have offset 100.
- An offset is not a timestamp and does not indicate processing time.
- An offset is not a count of records read.
- Topic compaction, transactions, and internal mechanisms can create gaps in observed offset sequences.

Therefore, the position identifier should be the triplet **topic + partition + offset**. Never use offset alone as a system-wide primary key.

### Record Offset vs. Committed Offset

**KafkaHeaders.OFFSET** represents the offset of the record currently being processed. Meanwhile, a consumer group's committed offset usually represents the next position the group will read in the partition. Thus, if a consumer has processed the record at offset 25 and commits progress afterward, the committed offset may be 26.

Reading the offset header does not mean the offset has been committed. Committing depends on acknowledgement mode, transactions, binder configuration, and message processing completion. If manual acknowledgement control is needed, use the acknowledgement mechanism supported by the Kafka binder and do not manually update offsets based solely on the header value.

## 5. Logging and Tracing with Metadata

When logging, combine the business event ID with the Kafka position:

~~~java
@Bean
public Consumer<Message<OrderCreated>> auditOrders() {
    return message -> {
        var headers = message.getHeaders();

        String topic = headers.get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = headers.get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = headers.get(
                KafkaHeaders.OFFSET, Long.class);

        OrderCreated event = message.getPayload();
        log.info(
                "order event: eventId={}, orderId={}, source={}-{}@{}",
                event.eventId(),
                event.orderId(),
                topic,
                partition,
                offset
        );
    };
}
~~~

This information is useful when:

- Finding a record in Kafka by topic, partition, and offset.
- Correlating application logs with Kafka admin tools.
- Investigating slow consumers or poison-pill records.
- Recording source position when forwarding a record to another destination.
- Comparing redelivery counts and identifying duplicate processing.

Do not dump the entire header map into logs by default. Headers can contain sensitive data, tokens, routing details, or internal metadata. Log only necessary fields and apply data-masking policies.

## 6. Using @Header to Extract Individual Values

If a handler only needs a few fields, parameters can be annotated with **@Header** in listener APIs that support it. With Spring Cloud Stream function beans, the simplest and clearest approach is to accept `Message<T>`; this keeps payload and metadata together in one unified object.

Example of a service-layer handler accepting extracted values:

~~~java
public void recordPosition(
        OrderCreated event,
        String topic,
        Integer partition,
        Long offset) {
    positionRepository.save(
            event.eventId(), topic, partition, offset);
}
~~~

The consumer can read headers and pass them to the service:

~~~java
@Bean
public Consumer<Message<OrderCreated>> positionConsumer(
        PositionService service) {
    return message -> {
        var headers = message.getHeaders();
        service.recordPosition(
                message.getPayload(),
                headers.get(KafkaHeaders.RECEIVED_TOPIC, String.class),
                headers.get(KafkaHeaders.RECEIVED_PARTITION, Integer.class),
                headers.get(KafkaHeaders.OFFSET, Long.class)
        );
    };
}
~~~

Avoid coupling the domain layer directly to the `KafkaHeaders` class unnecessarily. You can map metadata into an internal record:

~~~java
public record KafkaRecordPosition(
        String topic,
        int partition,
        long offset) {
}
~~~

Then the messaging adapter creates `KafkaRecordPosition` and passes it to the service. This keeps business logic easier to test and less coupled to the framework.

## 7. Distinguishing KafkaHeaders from Kafka Record Headers

These two concepts are related but not identical:

| Concept | Where It Lives | Example |
|---|---|---|
| Spring Message headers | Inside the application's `Message` object. | `contentType`, `correlationId`, `kafka_receivedTopic`. |
| Kafka record headers | Inside the record stored on Kafka; each header is a key and `byte[]` value. | `traceparent`, `tenant-id`, `event-source`. |
| Kafka record metadata | Belongs to the record managed by Kafka. | Topic, partition, offset, timestamp, key. |
| `KafkaHeaders` constants | Java constants to access/map metadata in Spring. | `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`. |

For example, **KafkaHeaders.RECEIVED_TOPIC** is a Spring `Message` header provided by the adapter to describe the source topic. It is not a business field written by the producer into Kafka record headers.

Conversely, a custom header like **tenant-id** can be added to a Spring `Message` by the producer, mapped by the Kafka binder to a Kafka record header, and read back by the consumer through a Spring `Message`. The header mapper is responsible for converting between the two representations.

### Default Header Mapper

The Kafka binder uses a header mapper to map Spring Messaging headers to Kafka Headers and vice versa. Kafka has supported native headers since `kafka-clients` 0.11.0.0. The **spring.cloud.stream.kafka.binder.headers** property is a legacy compatibility setting, only needed when communicating with Spring Cloud Stream 1.3.x or earlier applications using `kafka-clients` older than 0.11.0.0.

If you need custom mapping, you can specify a mapper bean:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: kafkaBinderHeaderMapper
~~~

The specified bean must implement the header mapper type supported by the binder. If a custom mapper drops a header, the consumer will not receive it even if the producer set it. Therefore, when replacing the default mapper, test both outbound and inbound directions.

### Filtering Headers with headerPatterns

Kafka producer bindings support **headerPatterns**, a list of patterns deciding which Spring Message headers are mapped to Kafka record headers. By default, the binder maps all eligible headers except reserved framework headers such as `id` and `timestamp`.

Example allowing only specific business headers:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              header-patterns: eventType,tenant-*,traceparent
~~~

When using an allowlist, headers not matching any pattern will not be sent to Kafka. Do not accidentally filter out headers that consumers or observability systems depend on. Verify against actual records after publishing.

## 8. Setting the Message Key When Sending Records

The message key is a component of the Kafka record, not the payload and not a regular Kafka record header. In Spring Cloud Stream, you can set the key using **KafkaHeaders.MESSAGE_KEY**:

~~~java
@Bean
public Supplier<Message<OrderCreated>> orderPublisher() {
    return () -> {
        OrderCreated event = nextOrder();
        return MessageBuilder.withPayload(event)
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .build();
    };
}
~~~

Kafka uses the key to select a partition via the default partitioner or a configured partitioner. Records with the same key are typically routed to the same partition when partition count and partitioning algorithm remain unchanged. This is useful for preserving the ordering of events for the same order.

You can use the Kafka binder's **messageKeyExpression**:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

The expression is evaluated on the outgoing message. If the key must come from a header, you can use an expression such as **headers['tenantKey']**. For a processor function that needs to preserve the key from the incoming record, you can reference the received key header:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          enrichedOrders-out-0:
            producer:
              message-key-expression: headers['kafka_receivedMessageKey']
~~~

The exact header name depends on the Spring Kafka version. In new code, prefer **KafkaHeaders.RECEIVED_KEY**; binder configuration can reference the corresponding wire/Message header name according to version documentation. With reactive functions, the application must explicitly copy required metadata from incoming messages to outgoing messages because the framework cannot assume how headers should be propagated across arbitrary reactive operators.

Do not use `offset` as the message key just because offsets are unique within a partition. If you want to keep all events for the same `orderId` on one partition, the key must be `orderId` or an equivalent business key.

## 9. Selecting the Target Topic with KafkaHeaders.TOPIC

By default, the output binding's `destination` determines the target topic. The Kafka binder has a **useTopicHeader** property allowing the topic to be overridden via the **KafkaHeaders.TOPIC** header:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        eventRouter-out-0:
          destination: default-events
      kafka:
        bindings:
          eventRouter-out-0:
            producer:
              use-topic-header: true
~~~

When this property is enabled, if an outgoing `Message` contains `KafkaHeaders.TOPIC`, the binder uses the header value as the target topic name; otherwise, the binder falls back to the default `destination`. By default, **useTopicHeader** is `false`.

Example:

~~~java
Message<String> message = MessageBuilder
        .withPayload("customer updated")
        .setHeader(KafkaHeaders.TOPIC, "customer-events")
        .setHeader(KafkaHeaders.MESSAGE_KEY, "CUS-100")
        .build();
~~~

This provides dynamic routing on the producer side. Enable it only when the application genuinely needs to choose topics at runtime and the allowed set of topics is strictly controlled. Never take an arbitrary topic name from an external request and send directly to it; doing so can cause the application to publish data to unintended topics or widen the access surface.

## 10. Receiving RecordMetadata After a Successful Send

Inbound metadata describes the record that was read. On the producer side, if you need to know which partition and offset the broker wrote the record to, the Kafka binder provides **recordMetadataChannel**.

When a send succeeds, the binder forwards the result message to the specified `MessageChannel` and attaches the **KafkaHeaders.RECORD_METADATA** header. The header value is an **org.apache.kafka.clients.producer.RecordMetadata** object returned by the Kafka client.

Configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              record-metadata-channel: orderRecordMetadataChannel
~~~

Declaring the channel and metadata-handling flow:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProducerMetadataConfiguration {

    @Bean
    public MessageChannel orderRecordMetadataChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderRecordMetadataFlow() {
        return IntegrationFlow
                .from("orderRecordMetadataChannel")
                .handle((payload, headers) -> {
                    RecordMetadata metadata = headers.get(
                            KafkaHeaders.RECORD_METADATA,
                            RecordMetadata.class);

                    if (metadata != null) {
                        log.info(
                                "Sent to topic={}, partition={}, offset={}",
                                metadata.topic(),
                                metadata.partition(),
                                metadata.offset()
                        );
                    }
                    return null;
                })
                .get();
    }
}
~~~

Upon successful publish, `RecordMetadata` provides:

- **topic():** the topic where Kafka wrote the record.
- **partition():** the selected partition.
- **offset():** the offset assigned to the record.
- **timestamp():** the timestamp returned by the Kafka client/broker in record metadata.

This metadata is useful for send reconciliation, audit logging, or persisting record positions. It only appears on the successful send result path when `recordMetadataChannel` is configured. If a send fails, the error routes to producer error handling/error channel if configured; there is no successful `RecordMetadata` for that attempt.

Do not confuse `RecordMetadata` with `RECEIVED_TOPIC`/`RECEIVED_PARTITION`/`OFFSET` headers. `RecordMetadata` belongs to the producer's send result; `RECEIVED_*` headers describe a record received by a consumer.

## 11. Forwarding Records and Preserving Essential Metadata

A processor receives records from the `orders` topic and sends results to `enriched-orders`. If it needs to preserve the key, correlation ID, or selected business headers, the application must explicitly decide which headers to forward.

Example:

~~~java
@Bean
public Function<Message<OrderCreated>, Message<OrderEnriched>> enrichOrder(
        CustomerDirectory customers) {
    return input -> {
        OrderCreated event = input.getPayload();
        Customer customer = customers.find(event.customerId());

        OrderEnriched enriched = new OrderEnriched(
                event.orderId(),
                event.customerId(),
                customer.segment(),
                event.total()
        );

        return MessageBuilder.withPayload(enriched)
                .setHeader(
                        KafkaHeaders.MESSAGE_KEY,
                        input.getHeaders().get(KafkaHeaders.RECEIVED_KEY))
                .setHeader(
                        "correlationId",
                        input.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

This snippet forwards only the selected key and correlation ID. Do not blindly copy all headers from inbound to outbound:

- **RECEIVED_TOPIC** describes the source topic; keeping it verbatim may cause downstream systems to mistake it for the target topic.
- **RECEIVED_PARTITION** and **OFFSET** describe the old record's position, not the new record's position.
- **RECORD_METADATA** belongs to a previous send result, not the metadata of the new send.
- `ACKNOWLEDGMENT` or `CONSUMER` headers belong to the current consumer and should not be emitted as business metadata.

If downstream systems need source lineage, use dedicated business headers such as **sourceTopic**, **sourcePartition**, **sourceOffset**, or a well-defined provenance structure. That way, source position data is retained as historical context without being confused with the new record's Kafka metadata.

## 12. Metadata, Partitions, and Ordering

Topic, partition, and offset are often examined alongside the message key to explain ordering:

~~~text
orders / partition 0:
  offset 10: orderId=A, status=CREATED
  offset 11: orderId=B, status=CREATED
  offset 12: orderId=A, status=PAID

orders / partition 1:
  offset 4: orderId=C, status=CREATED
  offset 5: orderId=C, status=PAID
~~~

Kafka guarantees ordering within each partition. If both events for `orderId=A` are sent with the same key and partitioning does not change, they land on the same partition in write order. You cannot compare offset 12 of partition 0 with offset 5 of partition 1 to deduce which event occurred first across the whole topic.

When processing in parallel:

- Key records by the aggregate or business entity requiring ordering.
- Do not use partition index as a business identifier.
- Do not assume increasing partition count will preserve the same key-to-partition mapping for future records.
- Use event timestamps or business sequence numbers when ordering must be compared beyond a single partition.
- Monitor consumer lag per partition rather than looking at a single isolated offset.

Metadata aids observation and investigation, but does not enforce business ordering on its own. If a consumer processes multiple records from the same partition asynchronously, the application must still control concurrency to avoid completing business steps out of order.

## 13. Using Metadata for Auditing and Duplicate Detection

Topic-partition-offset is a record's coordinate in the Kafka log. You can use this triplet to record processing origin or detect whether a record was observed previously.

Example position key:

~~~java
public record RecordPosition(
        String topic,
        int partition,
        long offset) {
}

static RecordPosition positionOf(Message<?> message) {
    var headers = message.getHeaders();
    return new RecordPosition(
            headers.get(KafkaHeaders.RECEIVED_TOPIC, String.class),
            headers.get(KafkaHeaders.RECEIVED_PARTITION, Integer.class),
            headers.get(KafkaHeaders.OFFSET, Long.class)
    );
}
~~~

An audit table can store the record position alongside the event ID and processing timestamp. If the same position appears again, it indicates the record was redelivered or audit logic wrote a duplicate. However, do not rely solely on Kafka position for business-level deduplication:

- A business event might be replayed as a new record with a different offset.
- The same event might be published to two different topics.
- Producer retries can create duplicate records with different offsets.
- Reprocessing or republishing can alter the partition.

Therefore, use **eventId** or an idempotency key for business deduplication. Use topic/partition/offset to identify a specific occurrence in the Kafka log.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Topic header returns `null` | Function does not accept `Message` or reads the wrong inbound header. | Accept `Message<T>` and use `KafkaHeaders.RECEIVED_TOPIC`. |
| `RECEIVED_PARTITION` not found | Older Spring Kafka version uses `RECEIVED_PARTITION_ID`, or binding does not supply the expected header. | Check dependency version and use the version-appropriate constant. |
| Offset cast to `Integer` overflows | Kafka offsets are 64-bit integers. | Use `Long` or `long`. |
| Using offset as a global ID | Offsets are only unique within a single partition. | Combine with topic and partition, or use `eventId` for business logic. |
| Confusing record offset with committed offset | Header describes the record being processed; commit usually stores the next position. | Inspect ack mode and committed offset state separately. |
| Received key is `null` | Producer did not set a key or record genuinely has a `null` key. | Read header optionally and clarify producer key policy. |
| Custom header does not reach consumer | Header mapper or `headerPatterns` filtered out the header. | Inspect two-way mapper and allowed patterns. |
| Topic header does not change destination | `useTopicHeader` is not enabled or `TOPIC` header is missing. | Check extended producer property and header name. |
| Missing `RECORD_METADATA` | `recordMetadataChannel` is not configured or send failed. | Check channel bean, binding property, and producer error channel. |
| Downstream sees old topic/offset | Processor copied inbound Kafka metadata onto outbound message. | Forward only keys/business headers; use dedicated `sourceTopic`/`sourceOffset` if provenance is needed. |
| Logs show offset jumps but processing looks short of records | Offsets can have gaps due to compaction, transactions, or records filtered from the consumer. | Check logs, isolation level, and actual records; do not treat offset gaps as data loss. |

When investigating, identify whether the application is acting as a producer or consumer. For consumers, inspect `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, and `OFFSET`. For producers, inspect `MESSAGE_KEY`, `TOPIC`, `useTopicHeader`, and `RECORD_METADATA`. Then check the header mapper, Spring Kafka version, and broker logs.

## 15. Testing Kafka Metadata

The Test Binder is useful for testing functions and bindings at the Spring Cloud Stream level, but it does not fully simulate broker-assigned metadata such as partitions and offsets. To accurately verify record metadata, write integration tests with a test Kafka broker, such as Embedded Kafka or Testcontainers.

Recommended test matrix:

| Scenario | Setup | What to Verify |
|---|---|---|
| Inbound record | Send record to configured topic. | Message has accurate `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, and `OFFSET`. |
| Multiple partitions | Send different keys or configure a multi-partition test topic. | Metadata reflects the actual partition selected by the broker. |
| Keyless record | Send record with `null` key. | Consumer handles missing key header gracefully. |
| Consecutive offsets | Send multiple records to the same partition. | Offsets increase in log order, without assuming contiguity if compaction/transactions apply. |
| Custom header | Send `correlationId` or `tenant-id`. | Header passes through mapper and consumer reads it accurately. |
| Filtered headers | Configure restrictive `headerPatterns`. | Only headers matching the pattern are transmitted. |
| Dynamic topic | Enable `useTopicHeader` and send `KafkaHeaders.TOPIC`. | Record is written to the topic chosen by the header. |
| Producer result | Configure `recordMetadataChannel`. | Channel receives result message with `KafkaHeaders.RECORD_METADATA`. |
| Forwarding processor | Consume record and publish to another topic. | Key and business headers are preserved; inbound metadata is not mistaken for outbound metadata. |
| Consumer restart | Stop and restart consumer. | Records may be redelivered per offset/ack semantics; deduplication logic works. |

In integration tests, read records back from the broker or use a test consumer to verify topic, partition, offset, and key. Compare the producer's `RecordMetadata` with the consumer's inbound metadata to confirm that the producer receives the successful write location while the consumer receives the delivered record location.

## 16. Pre-Deployment Checklist

- [ ] Consumer accepts `Message<T>` when Kafka metadata must be read.
- [ ] `KafkaHeaders` constants are used instead of hardcoded string names.
- [ ] Topic, partition, and offset are read with the correct data types.
- [ ] Positions are recorded using the topic-partition-offset triplet.
- [ ] `eventId` or an idempotency key is used for business deduplication.
- [ ] Reading `OFFSET` is not treated as committing an offset or ACK.
- [ ] Consumer `RECEIVED_*` headers are distinguished from producer `TOPIC`/`MESSAGE_KEY`.
- [ ] `RECEIVED_PARTITION`, `OFFSET`, and `RECORD_METADATA` are not forwarded as metadata of a newly emitted record.
- [ ] Header mapper and `headerPatterns` do not unintentionally strip required custom headers.
- [ ] `useTopicHeader` is enabled only when dynamic routing is needed and valid topics are restricted.
- [ ] `recordMetadataChannel` is used when outbound record position must be confirmed after a successful send.
- [ ] Integration tests run against real Kafka or a test broker to validate metadata.
- [ ] Logs do not expose sensitive payloads or the entire header map.

The Kafka binder maps record metadata into Spring Message headers so applications can read topic, partition, and offset directly inside functions. **KafkaHeaders.RECEIVED_TOPIC**, **RECEIVED_PARTITION**, and **OFFSET** describe the inbound record; **MESSAGE_KEY** and **TOPIC** support outbound options; **RECORD_METADATA** provides the outbound record's position after a successful send when a result channel is configured. By properly distinguishing record metadata from message headers, using the topic-partition-offset triplet, and testing against a Kafka broker, applications can trace events and handle delivery accurately.

## References

- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/config-options.html)
- [Spring for Apache Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Spring for Apache Kafka — Receiving Messages and Record Metadata](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
