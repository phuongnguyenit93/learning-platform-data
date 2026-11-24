# Topics and immutable logs

In Kafka, a **topic** is the logical name of an event stream. A topic's data is divided into **partitions**; each partition is an ordered log where Kafka appends records to the end and assigns each record an **offset**. This organization enables multiple producers to write data, multiple consumers to read independently, and storage and processing capacity to scale by distributing partitions across brokers.

When working with Spring Kafka, `KafkaTemplate` sends records to a topic, and `@KafkaListener` receives records from a topic. To design reliable messaging flows, you need to understand how data is partitioned, within what scope ordering is guaranteed, and how long Kafka retains logs.

## 1. A topic is a logical event stream

A topic names a type of data or an event stream that systems exchange with each other. For example, a sales application might use:

| Topic | Contents |
|---|---|
| `orders.events` | Events occurring throughout an order's lifecycle |
| `payments.events` | Events related to payments |
| `inventory.events` | Changes in inventory |

Producers send records to a topic. Kafka stores records in the topic's partitions. Consumers read records from those partitions according to their consumer group's own reading position.

A topic does not behave like a queue where a record immediately disappears once a consumer retrieves it. Kafka retains data according to the topic's retention policy. Therefore, multiple consumer groups can read the same event stream at different times and maintain independent progress. For example, `order-projection` can build queryable read views, while `order-analytics` reads the same events to aggregate reports.

## 2. A partition is an ordered log

A topic consists of one or more partitions. Each partition is an append-only sequence of records. You can visualize the structure as follows:

```text
Topic: orders.events

Partition 0:  [offset 0] -> [offset 1] -> [offset 2] -> [offset 3] -> ...
Partition 1:  [offset 0] -> [offset 1] -> [offset 2] -> ...
Partition 2:  [offset 0] -> [offset 1] -> [offset 2] -> ...
```

The arrows represent the order of records within the same partition. Each partition has its own log and offset sequence. Offset `5` in partition 0 has no before-or-after ordering relationship with offset `5` in partition 1.

### What does an immutable log mean?

Kafka organizes partitions using an **append-only log** model:

- Producers append new records to the end of a partition's log.
- Written records are not updated in place like rows in a relational database.
- Consumers read the log by advancing through offsets; multiple consumers can read the same record independently.
- Kafka can delete old data based on retention or remove older versions via compaction. Thus, "immutable" describes append-only writes without in-place modification, not that data is kept forever.

For example, when an order's status changes from `CREATED` to `PAID`, the producer typically appends an `OrderPaid` event. The `OrderCreated` event remains an event that happened; the application does not send a command to mutate the old record into `OrderPaid`. Consumers can read both events to reconstruct history or current state.

### Offsets identify reading positions

An offset is a sequential number managed by Kafka within a single partition. When a consumer receives a `ConsumerRecord`, `record.offset()` returns the offset of that record in its corresponding partition.

Offsets have several characteristics to keep in mind:

- An offset is only meaningful together with a topic and partition. When identifying a record, use the triple `(topic, partition, offset)`.
- An offset is not a topic-wide global sequence number and cannot be used to sort records belonging to different partitions.
- An offset is not a timestamp. Two records with increasing offsets are not necessarily spaced by a fixed time interval.
- Offsets do not necessarily start at `0` for the data a consumer observes. Retention, compaction, and control records/transaction markers can cause consumers to observe gaps between offsets.

Consequently, consumers should use offsets to track position within a partition, rather than assuming every consecutive offset corresponds to an application record they are guaranteed to receive.

## 3. Keys determine how records are distributed

Each Kafka record can have a key, value, timestamp, and headers. In many business flows, the key helps route related records to the same partition.

With the default partitioner, the producer uses the key to determine the partition. Records with the same key are typically sent to the same partition as long as the partition count and partitioning configuration remain unchanged. For example, using `orderId` as the key routes events for the same order through the same partition:

```text
key = order-1001  -> Partition 1
key = order-1001  -> Partition 1
key = order-1002  -> Partition 0
key = order-1003  -> Partition 2
```

This is the foundation for consumers to process changes to the same entity in order. If a record has no key, the producer's partitioner selects a partition according to its strategy; you should not rely on an assumption that keyless records are always distributed strictly round-robin record by record.

### Scope of ordering guarantees

Kafka guarantees read ordering within a single partition. If events for the same order are written to the same partition, a consumer can read them in that partition's log order. Kafka does not establish a total order across partitions of the same topic.

For example, partition 0 might contain `OrderCreated` at offset 10, while partition 2 contains `PaymentReceived` at offset 4. You cannot determine which event occurred first merely by comparing these two offsets.

Increasing the partition count must be weighed carefully for order-dependent flows. When the partition count changes, key-to-partition mapping can change; old and new records for the same key may land in different partitions. If business logic requires per-entity ordering, define a partition scaling strategy and data transition approach before changing topic configuration.

## 4. Partitions and replication

Partitions split data and processing load. Kafka can also create multiple replicas for each partition to increase fault tolerance. These are two distinct concepts:

- **Partition count** determines how many independent logs a topic is split into, thereby affecting distribution and parallel processing capacity.
- **Replication factor** determines how many copies of each partition are stored across brokers.

Within a replica set, one replica acts as the leader while the others follow and replicate data from the leader. Normal write operations go through the leader. Replicas that are keeping up with the leader are called in-sync replicas (ISR). When a broker fails, Kafka can elect an eligible replica from the ISR as the new leader, depending on replica state and cluster configuration.

A replication factor of `1` has no backup copy on another broker. For a cluster with at least three brokers, a replication factor of `3` typically provides better fault tolerance. To enforce write acknowledgment levels in production, design both the producer's `acks` and the topic/broker's `min.insync.replicas` together. Raising the replication factor alone without considering write acknowledgment settings is insufficient to determine data safety.

## 5. Kafka manages logs via retention and compaction

Logs can grow continuously, so topics need data cleanup policies. Kafka supports two main mechanisms: retention-based deletion and key-based compaction.

### Retention: keeping data for a time duration or size

With `cleanup.policy=delete`, Kafka marks log segments eligible for deletion based on time limits (`retention.ms`) or size limits (`retention.bytes`). Deletion occurs by segment, so `retention.ms` should not be treated as an exact per-record deletion timer.

For example, if a topic sets `retention.ms=604800000`, data is retained under a time policy of roughly seven days. Once an eligible segment is deleted, consumers can no longer go back and read records that were removed from the log.

Retention applies independently of whether consumers have read the data. A consumer group stopped longer than the retention period may resume and find its committed offset falls before the remaining data. Applications must choose retention aligned with expected maximum downtime and replay needs.

### Compaction: keeping the latest version per key

With `cleanup.policy=compact`, Kafka cleans up older versions of records sharing the same key so the log gradually retains the latest value for each key. Compaction runs in the background and does not necessarily happen immediately after a producer writes a new version.

For example, a topic storing account statuses might receive:

| Offset | Key | Value |
|---:|---|---|
| 0 | `account-01` | `ACTIVE` |
| 1 | `account-02` | `ACTIVE` |
| 2 | `account-01` | `SUSPENDED` |
| 3 | `account-01` | `CLOSED` |

After compaction completes on the relevant segments, Kafka can remove older versions of `account-01` and retain the latest version `CLOSED`. New records are still appended; compaction does not update old records in place the way a database does.

A record with a key and a `null` value is called a **tombstone**. A tombstone signifies key deletion in a compacted topic. Kafka retains tombstones for a configured period so consumers have a chance to observe the deletion signal, after which tombstones can also be cleaned up.

A topic can use `cleanup.policy=compact,delete` to combine both mechanisms. Choose the policy based on the data's purpose: event history typically needs long enough retention for replay, whereas a topic representing the latest state per key may suit compaction.

## 6. Consumer groups and reading positions

Each consumer group maintains its own reading progress per partition. Kafka stores a group's committed offsets in the internal `__consumer_offsets` topic.

Within the same consumer group, a partition is assigned to at most one consumer at a time. One consumer can receive multiple partitions. If a topic has three partitions and the group has two consumers, one consumer may receive two partitions and the other one partition. If the group has more consumers than partitions, some consumers will remain unassigned.

Different groups read independently. For instance, `order-projection` and `order-analytics` can both read `orders.events`; the fact that the first group has read up to offset 100 does not shift the second group's reading position.

Distinguish these two values:

- `record.offset()` is the offset of the record the consumer is currently processing.
- The committed offset is usually the **next position to read**. If a consumer has processed record offset `12` and commits corresponding progress, the committed value is typically `13`.

Applications must coordinate when records are processed versus when offsets are committed. If an offset is committed before successful processing and the process stops, the record may be skipped on resume. If processing finishes without committing and the process stops, the record may be read and processed again. Therefore, consumers generally need to tolerate receiving the same event more than once, especially under at-least-once delivery semantics.

`auto.offset.reset` is only used when the group has no valid offset yet or the stored offset is no longer within the current log range. `earliest` requests starting from the earliest remaining data; `latest` starts from newly written data arriving next. This property does not automatically rewind a group that already has a valid offset back to the beginning of the topic.

## 7. Declaring topics and inspecting records with Spring Kafka

Spring Kafka provides `NewTopic` and `TopicBuilder` to declare topics as beans. When a Spring Boot application has Kafka Admin configured and can connect to the cluster, `NewTopic` beans can be used to ask Kafka to create topics if they do not already exist.

The example below creates a topic with three partitions, a replication factor of three, and a seven-day time retention:

```java
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(3)
                .replicas(3)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .build();
    }
}
```

A replication factor of three requires a cluster with enough suitable brokers. When running Kafka locally with only one broker, use `.replicas(1)` for development. Partition count and replication factor should be chosen according to load, concurrency level, and fault-tolerance requirements of the deployment environment.

For an example using `String` keys and values, serializer/deserializer configuration can be written in `application.yml` as follows:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

The producer uses `KafkaTemplate` to send `orderId` as the key. The consumer receives a `ConsumerRecord` to inspect the topic, partition, and offset Kafka assigned to the record:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
class OrderEventMessaging {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventMessaging(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String eventPayload) {
        // The same orderId is typically routed to the same partition by the default partitioner.
        kafkaTemplate.send("orders.events", orderId, eventPayload);
    }

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        System.out.printf(
                "topic=%s, partition=%d, offset=%d, key=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
        );

        String eventPayload = record.value();
        // Pass eventPayload to the application's business processing step.
    }
}
```

In this example, `publish` sends a record with `orderId` as the key; the key helps group events of the same order into the same partition via the default partitioner. The `consume` method shows the metadata the consumer receives. It is useful when verifying how records are distributed and reconciling consumer group reading progress.

`acks=all` asks the broker to acknowledge according to replicas currently in the ISR. In production, also configure `min.insync.replicas` appropriate for your replication factor and desired fault tolerance. The serializer configuration in this example only suits string payloads; if sending objects, producers and consumers must agree on serialization/deserialization format and schema management.

## 8. Choosing configuration based on business requirements

| Requirement | Decision to make |
|---|---|
| Need to preserve order of events for the same order | Use `orderId` as the key and keep a stable partitioning strategy |
| Need to increase parallel processing capacity | Choose enough partitions for expected concurrency and distribute the consumer group appropriately |
| Need to replay events after an incident | Choose retention longer than expected downtime and replay window |
| Only need to store the latest state per identifier | Consider `cleanup.policy=compact` and clear key/tombstone conventions |
| Need fault tolerance when a broker fails | Align replication factor, `acks`, and `min.insync.replicas` |

Before creating a topic for a business flow, answer three questions: which entity must records be ordered by, how long must the application be able to replay data, and how much data loss is acceptable. The answers will guide appropriate keys, partition counts, retention/compaction, and replication.

## 9. Common misconceptions

1. **Assuming offsets are unique across the entire topic.** Offsets are only unique within a partition; use the topic, partition, and offset triple to locate a record.
2. **Assuming multiple partitions still share a global order.** Kafka only guarantees ordering within each partition. To preserve order per order entity, use an appropriate key and control partition count changes.
3. **Assuming Kafka deletes records once a consumer finishes reading.** Data is retained according to retention or compaction, independently of each consumer group's progress.
4. **Assuming an immutable log means data is never lost.** Retention and compaction can remove data per configuration; choose policies matching replay needs.
5. **Assuming adding more consumers always increases throughput.** Within a group, the number of consumers that can meaningfully process in parallel is bounded by the number of assigned partitions.
6. **Assuming a replication factor of three automatically guarantees every write is confirmed by three copies.** Acknowledgment guarantees also depend on ISR, `acks`, and `min.insync.replicas`.

Once you grasp topics, partitions, offsets, and log lifecycle, you can accurately inspect metadata in Spring Kafka, choose keys to preserve business ordering, and design storage policies aligned with how consumer groups consume events.
