# Choosing Topic and Partition per Message

A Kafka producer must determine two destinations for each record: the topic where it is stored and the partition within that topic. The topic typically represents the event type or data domain, while the partition determines which sub-log the record resides in, which consumer group instance receives it, and what ordering is preserved. The Spring Cloud Stream Kafka Binder lets the application send through an output binding, select a topic per message, and choose a partition via the record key or the framework's partitioning mechanism.

You should not conflate all of these concepts into a single property. Choosing a topic is a routing decision to a destination; choosing a partition is a record distribution decision within the selected topic. A record key usually lets Kafka choose a stable partition for the same key. If you truly need to force a record into a specific numbered partition, that is an option in the lower-level Kafka producer API and requires weighing the trade-off of bypassing part of the binder abstraction.

## 1. Distinguishing topic, partition, and record key

A topic can have multiple partitions. Each partition is an independently ordered log; Kafka does not provide global ordering across partitions.

| Component | Meaning | Example |
|---|---|---|
| Topic | A group of records of the same type or data contract | orders.created |
| Partition | A sub-log within a topic | Partition 0, 1, 2 |
| Record key | A key used for routing and typically for grouping records of the same entity | ORD-1001 |
| Offset | The position of a record within a partition | Offset 125 |

For example, suppose an orders.events topic has 6 partitions. Events for the same order can use orderId as the key so Kafka places them into the same partition. A consumer group can process different partitions in parallel, while ordering within a single partition is maintained in write order.

The record key is neither the topic name nor the partition number. The key helps the partitioner select a partition. The partition number is the routing result, unless the application explicitly specifies a partition using the low-level Kafka API.

## 2. Choosing a fixed topic with an output binding

If an output binding always sends one event type to the same topic, declare destination on the binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

Send a POJO or Message through the binding:

~~~java
@Service
public class OrderPublisher {
    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

The name orders-out-0 is the output binding in the application; orders.created is the target Kafka topic. This approach is easy to manage because topic, content type, binder, and producer settings are declared centrally.

If the application has multiple event types with different policies, you can declare multiple output bindings, each pointing to a topic. This approach fits well when topics are known in advance and each stream needs its own schema, retry, partition count, or security settings.

## 3. Choosing a topic per message with KafkaHeaders.TOPIC

The Kafka Binder has the useTopicHeader property. When enabled, the KafkaHeaders.TOPIC header value of an outbound message overrides the binding's default destination. If the message does not carry this header, the binder uses the destination declared on the binding.

Configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        domain-events-out-0:
          destination: events.default
          content-type: application/json
      kafka:
        bindings:
          domain-events-out-0:
            producer:
              use-topic-header: true
~~~

The producer selects the topic from validated data:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public boolean publish(String targetTopic, DomainEvent event) {
    Message<DomainEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, targetTopic)
        .build();

    return streamBridge.send("domain-events-out-0", message);
}
~~~

When useTopicHeader=true, the example above can send individual messages to different topics through the same binding. If useTopicHeader is not enabled, the topic header is not used to override destination and the binding continues sending to events.default.

The topic header must be a valid Kafka topic name. Validate the value before sending—for example, allow only orders.created, orders.cancelled, and orders.shipped. Never accept an arbitrary topic name from an HTTP request or external message and pass it straight into KafkaHeaders.TOPIC; doing so can allow the application to write to topics outside its authorized scope.

The target topic must exist or be provisioned according to cluster policy. Do not assume enabling useTopicHeader will automatically create every dynamically selected topic. Check autoCreateTopics, AdminClient permissions, replication/partition configuration, and the environment's governance policy.

## 4. Choosing a topic dynamically with a StreamBridge destination

StreamBridge can also send to a destination name instead of a pre-declared binding:

~~~java
streamBridge.send("orders.created", event);
~~~

When no output binding named orders.created exists yet, StreamBridge can create a dynamic output binding to that destination using Spring Cloud Stream's mechanism. This differs from KafkaHeaders.TOPIC:

| Approach | Passed value | Mechanism |
|---|---|---|
| Static binding | orders-out-0 | Declared binding, pre-configured destination |
| KafkaHeaders.TOPIC | Header on Message | Overrides topic per message through a binding with useTopicHeader |
| StreamBridge dynamic destination | Destination name in send | Framework creates and caches a dynamic output binding |

Choose a static binding when the set of topics is fixed. Use the topic header if you want to keep a single binding and vary the topic per message. Use a dynamic destination if the application needs to create bindings for runtime destinations and is prepared to manage caching, provisioning, and security policies for those destinations.

Do not let external input arbitrarily create an unbounded number of destination names. Restrict them with an allowlist or naming rules, enforce publish permissions, and monitor the number of dynamic bindings created.

## 5. Choosing a partition with a Kafka record key

Kafka supports native partitioning. With the Kafka Binder, the standard way to group records by key is to set the Kafka record key. The Kafka producer partitioner selects a partition based on the key and the topic's actual partition count.

You can set the key directly on the message using KafkaHeaders.KEY:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();

streamBridge.send("orders-out-0", message);
~~~

Or configure messageKeyExpression on the output binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

The expression is evaluated on the outbound message and used to set the Kafka record key. Use KafkaHeaders.KEY when code needs to specify the key directly on each message; use message-key-expression when all messages on the binding share the same key extraction rule.

If orderId is used as the key, records for the same order are grouped by key. Different orders may go to different partitions. Kafka guarantees ordering only within a single partition, so a stable key helps preserve the event ordering of the same aggregate in the write stream.

If there is no key, Kafka uses the client's default partitioner to distribute records. You should not rely on keyless default behavior to preserve ordering per customer or per order.

## 6. Distinguishing Kafka record key from partitionKeyExpression

Spring Cloud Stream provides a generic partitioning abstraction across multiple middleware systems. Producer configuration can extract a partition key and compute the partition itself:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

partition-key-expression extracts orderId from the payload. partition-count must be greater than 1 to enable partitioning. By default, Spring Cloud Stream selects a partition using the formula:

~~~text
partition = key.hashCode() % partitionCount
~~~

You can customize partition selection with partition-selector-expression or a PartitionSelectorStrategy bean. partition-key-expression and partition-key-extractor-name are mutually exclusive ways of extracting the key; do not configure both simultaneously on the same binding.

For Kafka, understand the difference:

- Kafka native partitioning uses the record key and the Kafka producer's partitioner.
- Spring Cloud Stream's partitioning abstraction uses the partition key and the framework's partition selection algorithm.
- The two algorithms can yield different results for the same key value.
- partition-key-expression should not be assumed by default to be the Kafka record key.

The Kafka Binder documentation recommends using Kafka's native partitioning in most cases. Binder partitioning is useful when you need a custom key algorithm or want the same Spring Cloud Stream partitioning rules across multiple middleware technologies. If consumers or other systems need to read the Kafka record key, set KafkaHeaders.KEY or configure message-key-expression.

## 7. Choosing a partition with a custom selector

When using the partitioning abstraction, you can change the partition calculation algorithm:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-selector-expression: key.hashCode() % 12
            partition-count: 12
~~~

partition-selector-expression is evaluated with the extracted key variable. The result must fall within the valid partition range from 0 to partitionCount - 1. If complex logic is required, register a bean implementing PartitionSelectorStrategy and specify partition-selector-name.

Only customize the selector when there is a clear requirement, such as compatibility with another producer or distribution according to a published business rule. All producers sending to the same topic must agree on the algorithm if the same key is expected to always go to the same partition.

With producers written in multiple languages, do not assume Java's hashCode is equivalent to another language's hash function. Standardize the hash algorithm and test the same sample key set across all producers.

## 8. partitionCount as a hint for the Kafka Binder

In Spring Cloud Stream, partition-count is the target number of partitions for the partitioning abstraction. For the Kafka Binder, this value also serves as a hint during topic provisioning:

- If the topic does not exist yet and the binder is allowed to create topics, partition count is used together with minPartitionCount to determine the number of provisioned partitions.
- If the topic already exists with more partitions than configured, the binder uses the larger actual partition count.
- If the topic has fewer partitions than configured and autoAddPartitions is disabled, the binder may fail to start.
- If autoAddPartitions is enabled, the binder may request increasing the partition count to match the configuration.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-count: 12
      kafka:
        binder:
          auto-create-topics: true
          auto-add-partitions: false
~~~

This example illustrates provisioning; in production, creating or increasing partitions should follow the Kafka administrator's policy. Do not confuse partition-count with replication-factor: partition count determines the number of sub-logs, whereas replication factor determines the number of replicas of each partition.

## 9. Changing partition count and the impact on the same key

With hash modulo algorithms, a key's partition depends on the partition count. When increasing the partition count, a key may be mapped to a different partition. Older records remain in the old partition, while new records with the same key may go to the new partition.

This can break ordering expectations across an aggregate's history. Kafka preserves ordering within each partition, but it does not automatically reorder old and new records for the same key if they reside in two different partitions.

Before increasing the partition count:

- Determine whether the business logic requires strict ordering by key.
- Check consumer state stores, projections, and replay behavior.
- Determine when to stop or drain producers if needed.
- Plan a migration or versioned topic if changing the partition layout affects the contract.
- Test key mapping before and after the change.

Do not increase partition count arbitrarily just to increase concurrency if key-based ordering is a critical requirement.

## 10. When you truly need to specify a partition number

Key-based routing is the normal choice: the producer supplies the key, and the Kafka partitioner picks the partition. Occasionally, an application needs to send a record to a specific numbered partition, such as in migration tools, testing, or workflows with manually managed partitioning rules.

The Spring Cloud Stream Kafka Binder focuses on key-based routing and the partitioning abstraction. If you need to force an exact partition number, use Spring Kafka's low-level producer API with ProducerRecord:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;

public void publishToExactPartition(
        KafkaTemplate<String, OrderCreated> kafkaTemplate,
        OrderCreated event,
        int partition) {

    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(
            "orders.events",
            partition,
            event.orderId(),
            event
        );

    kafkaTemplate.send(record);
}
~~~

ProducerRecord accepts topic, partition number, key, and value. The partition must exist in the topic; specifying an invalid partition causes the broker/client to report an error. ProducerFactory must have key/value serializers compatible with the data types.

This is the direct Spring Kafka API, not the standard partition routing mechanism of the Spring Cloud Stream binder. The application must manage KafkaTemplate/ProducerFactory, send failures, transactions, and result observation accordingly. Do not add a header named partition to a binder message and assume the binder will treat it as a partition selection directive without verifying the exact contract of the binder version in use.

## 11. Combining per-message topic and key selection

A message can carry both a topic header and a record key. For example, a service sends multiple order event types to their corresponding topics while using orderId as the key:

~~~java
public boolean publishEvent(
        String eventType,
        OrderEvent event) {

    String topic = switch (eventType) {
        case "ORDER_CREATED" -> "orders.created";
        case "ORDER_CANCELLED" -> "orders.cancelled";
        case "ORDER_SHIPPED" -> "orders.shipped";
        default -> throw new IllegalArgumentException("Unsupported event type");
    };

    Message<OrderEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, topic)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();

    return streamBridge.send("domain-events-out-0", message);
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        domain-events-out-0:
          destination: events.default
          content-type: application/json
      kafka:
        bindings:
          domain-events-out-0:
            producer:
              use-topic-header: true
~~~

The example uses an event type allowlist to select the topic. An ORDER_CREATED event goes to orders.created; ORDER_CANCELLED goes to orders.cancelled. Within each topic, orderId is the Kafka record key so events for the same order are routed consistently by Kafka's partitioner.

Target topics must have schemas compatible with their respective producers and consumers. If topics have different schemas, do not combine them onto a single binding sharing the same content type/serializer without a clear conversion strategy.

## 12. Verifying the actual topic and partition after sending

You should not infer the partition solely from configuration. You can ask the Kafka Binder to send metadata for successful records to a channel:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              record-metadata-channel: sentMetadata
~~~

Messages sent to the sentMetadata channel carry the KafkaHeaders.RECORD_METADATA header. The value is the RecordMetadata provided by the Kafka client, containing the topic, partition, and offset where the record was actually written:

~~~java
RecordMetadata metadata = message.getHeaders()
    .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);

log.info("Published to topic={}, partition={}, offset={}",
    metadata.topic(), metadata.partition(), metadata.offset());
~~~

Register a MessageChannel named sentMetadata in the application context and process metadata on that channel. Success metadata helps verify actual routing; send failures go to the producer error channel if configured. Do not log full sensitive payloads when observing send results.

## 13. Common routing errors

| Symptom | Possible cause | How to check |
|---|---|---|
| Messages always go to the default topic | useTopicHeader is not enabled or message lacks KafkaHeaders.TOPIC | Check the producer binding property and header before sending |
| Invalid topic header | Wrong topic name or producer lacks write permission | Check the allowlist, topic existence, and Kafka ACLs |
| Records with the same orderId land in multiple partitions | Unstable key, inconsistent key serializer, or partition count/algorithm changed | Check record key, serializer, and partition metadata |
| Key does not appear at the consumer | Custom header mapper drops KafkaHeaders.KEY or producer did not set key | Check KafkaHeaderMapper and the record on the broker |
| Binder partitioning and another producer pick different partitions | Using two different hash/partitioner algorithms | Standardize on one algorithm or use Kafka native key routing |
| Binder fails to start because topic has too few partitions | partitionCount is larger than existing topic while autoAddPartitions is off | Check actual partition count and provisioning policy |
| Consumer processes out of business order | Same aggregate does not use the same key or consumer processes concurrently without control | Check key, partition, and concurrency/processing order |

## 14. Testing topic and partition selection

A solid test suite should verify both expected routing and metadata returned by the broker:

- Send a message without KafkaHeaders.TOPIC and verify the binder uses the default destination.
- Enable useTopicHeader, send two messages with different topic headers, and verify they arrive at the right topics.
- Send a topic name outside the allowlist and verify the producer rejects it before publishing.
- Send multiple messages with the same orderId and verify they use the same record key and partition.
- Send messages with different orderIds and observe partition distribution.
- Verify that messageKeyExpression and KafkaHeaders.KEY yield the same key result.
- Compare the partition chosen by Kafka native key routing versus Spring Cloud Stream's partitioning abstraction.
- Change the partition count in a test environment and verify a key can be mapped to a different partition.
- If using ProducerRecord to specify a partition, test an existing partition and the error when specifying an out-of-range partition.
- Read RecordMetadata to confirm the actual topic, partition, and offset.

The Test Binder is useful for testing function logic and message headers, but it does not fully simulate Kafka's partitioner, metadata, provisioning, serializers, and ACLs. Integration tests against a real Kafka broker or equivalent broker environment are necessary before release.

## 15. Pre-deployment checklist

- [ ] Selected static binding, KafkaHeaders.TOPIC, or dynamic destination according to needs.
- [ ] If using KafkaHeaders.TOPIC, enabled use-topic-header on the right output binding.
- [ ] Target topics are restricted by an allowlist and have appropriate publish ACLs.
- [ ] Record key is stable, has a compatible serializer, and reflects the business key.
- [ ] Distinguished Kafka native partitioning from Spring Cloud Stream's partitionKeyExpression.
- [ ] If using the partitioning abstraction, partition-count is greater than 1 and selector stays within valid bounds.
- [ ] Verified actual partition count and autoAddPartitions policy.
- [ ] Evaluated the impact of changing partition count on key-based ordering.
- [ ] Explicit partition numbers are used only when truly necessary and with clear understanding of using the Kafka producer API directly.
- [ ] Verified topic, partition, and offset via RecordMetadata or Kafka tooling.
- [ ] Tested routing against real Kafka and monitored producer errors.

Choosing a topic determines where a record is stored; choosing a key or partition determines how the record is distributed within that topic. With the Spring Cloud Stream Kafka Binder, use KafkaHeaders.TOPIC together with useTopicHeader to override the topic per message, and use KafkaHeaders.KEY or messageKeyExpression so Kafka selects a stable partition by key. Only use the partitioning abstraction when you need Spring Cloud Stream's algorithm; if you must specify an exact partition number, use the Kafka producer API directly and explicitly manage the accompanying responsibilities.

## References

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Partitioning](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
