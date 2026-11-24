# Spring for Apache Kafka and the Partitioned Log Model

Spring for Apache Kafka brings Spring abstractions into Apache Kafka: `KafkaTemplate` for sending records, `@KafkaListener` and listener containers for receiving records, along with mechanisms for offset management, transactions, retries, and data conversion. To use these APIs properly, you first need to understand how Kafka organizes data into topics and partitions.

Kafka does not work like a simple queue where a message is removed from the queue after a consumer processes it. Each topic consists of one or more partitions; each partition is an ordered log where records are appended to the end. Consumers read the log by offset and save their progress by consumer group. A record that has been read usually remains in the log according to the topic's retention or compaction policy.

The partition model determines ordering, scalability, load distribution, and how Spring Kafka runs consumers concurrently. Choosing keys, partition counts, and group IDs are architectural decisions that directly affect business behavior.

## 1. Topics, partitions, and logs

### 1.1. A topic is a logical data stream

A topic is a logical name for producers to write records to and consumers to subscribe to. For example, an e-commerce system might use topics:

- orders: order events.
- payments: payment events.
- inventory: inventory changes.
- shipment: delivery updates.

A topic identifies a type of data or event stream. Inside a topic, Kafka divides data into partitions to distribute storage and processing.

### 1.2. A partition is an ordered commit log

A partition is a sequence of records appended in order. Each record in a partition is assigned an increasing offset based on its position in the log.

Example topic orders with three partitions:

~~~text
orders
  partition 0: offset 0 -> 1 -> 2 -> 3 -> ...
  partition 1: offset 0 -> 1 -> 2 -> 3 -> ...
  partition 2: offset 0 -> 1 -> 2 -> 3 -> ...
~~~

Offsets only have meaning within a single partition. Partition 0 offset 12 and partition 1 offset 12 are two different positions. There is no global offset ordering every record across the entire topic.

Kafka guarantees read order within a topic-partition according to the order records were written to that partition. Kafka does not guarantee global ordering across partitions. If two producers write concurrently to two different partitions, consumers cannot infer global business order solely from offsets.

### 1.3. How a log differs from a traditional queue

In a traditional queue, messages are typically deleted or removed from the queue after being acknowledged. In Kafka, consumers commit offsets to save reading progress; committing an offset does not delete the record from the partition.

Records are retained according to retention settings, such as time or size. A compacted topic can retain the latest record per key and remove some older versions, but compaction does not alter the offset order of the remaining records.

This allows multiple consumer groups to read the same topic independently. One group can process data in near real-time; another group can re-read the log to rebuild projections or run reports.

## 2. Partition keys decide where records are stored

### 2.1. Why are keys needed?

A record sent by a producer can include:

- Topic: name of the data stream.
- Key: key used for routing and partitioning.
- Value: payload of the event.
- Headers: additional metadata.
- Timestamp: timestamp attached to the record.

When a producer sends records with the same key, the default partitioner typically chooses the same partition for that key under the same topic/partitioner configuration. Thus, records for the same business entity can be read in order within one partition.

For example, using orderId as the key:

| Record | Key | Partition |
|---|---|---:|
| OrderCreated | order-42 | 1 |
| PaymentAuthorized | order-42 | 1 |
| OrderPacked | order-42 | 1 |
| OrderShipped | order-42 | 1 |
| OrderCreated | order-77 | 0 |

If order-42's records are written sequentially to the same partition, a consumer reading that partition will see them in write order.

### 2.2. Choosing keys by aggregate or entity

Choose keys based on the unit for which the system must preserve order:

- orderId if event ordering per order is required.
- accountId if change ordering on the same account is required.
- customerId if activity ordering for one customer is required.
- deviceId if telemetry ordering for one device is required.

Avoid random keys for events that require per-entity ordering. If the key is null, the producer can distribute records using sticky/batching strategies; records for the same entity will then not necessarily land in the same partition.

Do not use timestamps as keys if the goal is per-entity ordering. Timestamps can collide, suffer clock skew, or arrive late; they do not replace a stable identifier key.

### 2.3. Keys do not create business ordering if producers send out of order

A partition only preserves append order. If two services send events for the same orderId concurrently, whichever record reaches the broker first can be appended first. Kafka does not inherently know that OrderCreated must precede OrderShipped.

If strict business ordering is required, the application must ensure publishing order, such as serializing publishes per aggregate, using a transactional outbox ordered by sequence, or storing an aggregate version so consumers can detect out-of-order events.

### 2.4. Changing partition count can change key mapping

If the partition count changes, the partitioning algorithm may route the same key to a different partition. Old records remain in the old partition; new records may land in the new partition. Consumers then no longer have a single log containing the key's entire history.

Therefore, increasing partitions is not completely neutral for per-key ordering. Before increasing partitions, evaluate:

- Does per-aggregate ordering need to be preserved across the entire history?
- Do any consumers rely on fixed partition assignments?
- Can a transition period where old and new data for the same key live in two partitions be tolerated?
- Are versions, sequence numbers, or a migration/repartition topic needed?

## 3. Replication, leaders, and availability

Each partition has one leader replica and can have follower replicas on different brokers. Producers write to the leader; followers replicate the log from the leader. Consumers usually read from the leader, unless configuration and clients support alternative replica fetching mechanisms.

Replication factor is the number of copies of a partition. For example, a replication factor of 3 means a partition has three replicas across eligible brokers. Replicas do not create three extra logical records for consumers; they are copies for recovery when a broker fails.

Important configurations:

- replication.factor: number of replicas when the topic is created.
- min.insync.replicas: minimum number of replicas that must be in-sync for certain write conditions.
- acks: level of acknowledgement requested by the producer.
- enable.idempotence: helps producers retry more safely against certain protocol-level retry failures.

For example, with acks=all and min.insync.replicas=2, the broker only acknowledges a write when the corresponding ISR conditions are met. If the number of in-sync replicas drops below the threshold, the producer can receive an error rather than an acknowledgement for a less durable write. Design replication factor, min.insync.replicas, and acks together according to durability and availability goals.

Replication does not replace backups, schema governance, or disaster recovery strategies. It protects partitions against certain broker failures, but does not protect against a producer sending bad data or an application processing business logic incorrectly.

## 4. Consumer groups and partition distribution

### 4.1. A consumer group is a team sharing work

A consumer group has a group.id. Consumers in the same group divide up the topic's partitions so that each partition is assigned to at most one consumer in the group at a time.

If a topic has six partitions and the group has three consumers, each consumer can receive roughly two partitions. If the group has eight consumers but the topic only has six partitions, at least two consumers will have no partitions to read from that topic.

One partition is not processed concurrently by two consumers in the same group under standard assignment. However, two different groups can read the same partition independently, each with its own offsets.

~~~text
Topic: orders (6 partitions)

Consumer group: order-projection
  consumer A <- P0, P1
  consumer B <- P2, P3
  consumer C <- P4, P5

Consumer group: analytics
  consumer X <- P0, P1, P2
  consumer Y <- P3, P4, P5
~~~

The order-projection group and the analytics group both read the same topic, each with its own progress and purpose.

### 4.2. Parallel consumers are bounded by partition count

Within a consumer group reading a single topic, the number of consumers that can genuinely read in parallel is bounded by the number of assigned partitions. Increasing concurrency beyond the partition count does not automatically create more partitions or increase parallel reading.

For example, if a topic has four partitions:
- concurrency=1: one consumer reads all four partitions.
- concurrency=2: two consumers share four partitions.
- concurrency=4: up to four consumers read concurrently, one partition each.
- concurrency=8: up to four consumers receive assignments; the remaining consumers sit idle for this topic.

If a listener subscribes to multiple topics, assignment depends on the total set of partitions and the assignor strategy. Check actual assignments rather than looking only at configured concurrency.

### 4.3. Rebalance

When consumers join or leave a group, or partitions/topics change, Kafka can perform a rebalance to recompute assignments. During a rebalance, processing may pause or partitions may move to other consumers.

Rebalances can occur when:
- Application instances start or stop.
- A consumer misses heartbeats or fails to poll in time.
- Concurrency changes.
- A topic gets new partitions.
- Group membership or subscriptions change.

Processing too slowly inside a listener can prevent a consumer from polling in time and cause it to be considered dead. Configure max.poll.interval.ms, max.poll.records, and concurrency based on actual processing times. Do not blindly increase max.poll.interval.ms; consider batch processing, reducing processing time, or offloading heavy work to a controlled pipeline.

## 5. Offsets and processing progress

### 5.1. An offset is a read position, not a global message ID

Consumers track offsets per topic-partition. Committed offsets represent the progress saved by the group so it can resume after a restart or rebalance.

If a consumer group committed offset 120 for partition 2, the next read typically starts from the next position according to Kafka consumer semantics. A committed offset does not guarantee every prior record completed its business side effects if the application committed too early.

### 5.2. auto.offset.reset

auto.offset.reset only applies when a group has no valid committed offset for a partition, or the committed offset is no longer available due to retention. Common values:

- earliest: start from the earliest record remaining in the log.
- latest: start from the current end of the log, skipping older un-offset backlog.
- none: throw an error if no valid offset is found.

Do not confuse auto.offset.reset with resetting offsets for a group that already has progress. For intentional replay, use admin tools or ConsumerSeekAware/seek APIs appropriately, with a plan for duplicates and side effects.

### 5.3. Offset commits and duplicates

If a consumer performs side effects before committing offsets, the application can reprocess records if the process stops after the side effect but before the commit. This is a common cause of duplicates in at-least-once models.

If you commit offsets before side effects finish, records can be skipped when the consumer restarts. Thus, the order of commit and processing must be chosen according to desired semantics.

Design idempotent consumers using message IDs or business keys, use appropriate transactions, and store business checkpoints if needed. Do not infer exactly-once for external databases solely from Kafka offset commits.

## 6. Sending records with KafkaTemplate

KafkaTemplate is the high-level Spring abstraction wrapping the Kafka producer. Send methods return `CompletableFuture<SendResult<K,V>>`, allowing asynchronous result handling.

### 6.1. Sending with a key to keep aggregate records on one partition

Below is a service fragment using `KafkaTemplate<String, String>`:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String eventPayload) {

        return this.kafkaTemplate.send(
                "orders",
                orderId,
                eventPayload);
    }
}
~~~

orderId is the record key. With the default partitioner and the same partition topology, records with the same key are routed to the same partition, giving them append order in that partition for that aggregate.

### 6.2. Checking send results

~~~java
publisher.publish("order-42", "OrderCreated")
        .whenComplete((result, error) -> {
            if (error != null) {
                // Record send failure and handle per retry policy.
                return;
            }

            var metadata = result.getRecordMetadata();

            System.out.printf(
                    "topic=%s partition=%d offset=%d%n",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
        });
~~~

The send result provides the broker metadata of the record successfully sent per producer configuration. Topic, partition, and offset are important information for tracing records.

Do not treat calling send() as proof that the broker confirmed it. For critical operations, handle the CompletableFuture and failure paths explicitly. Avoid blocking indefinitely with get(); if synchronous waiting is needed, use an appropriate timeout and account for ambiguous timeouts where the broker may already have received the record.

### 6.3. Sending to a specific partition

KafkaTemplate supports sending to a specific partition:

~~~java
kafkaTemplate.send("orders", 2, "order-42", "OrderCreated");
~~~

Use explicit partitions only when the application truly owns the partitioning rules or has specific operational requirements. If you only want per-entity ordering, usually prefer keys and partitioners over hard-coding partition numbers. Explicit partitions tightly couple the application to topic topology.

## 7. Receiving records with @KafkaListener

### 7.1. Basic listener

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection",
            concurrency = "3")
    public void onOrder(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String payload = record.value();

        int partition = record.partition();
        long offset = record.offset();

        // Update projection by orderId.
    }
}
~~~

The listener receives a ConsumerRecord to access key, value, topic, partition, offset, timestamp, and raw headers. If only the payload is needed, the method can accept String or a corresponding domain type after configuring deserializers/message converters.

concurrency=3 instructs the listener container to create three consumer instances in the same group. The actual number of assigned partitions determines how many consumers can be active simultaneously.

### 7.2. Configuring the container factory

If you need to explicitly configure concurrency and poll timeout, you can create a ConcurrentKafkaListenerContainerFactory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setPollTimeout(3000);

    return factory;
}
~~~

This is a configuration fragment inside a @Configuration class. When using Spring Boot, Boot typically auto-configures the consumer factory and listener container factory; only create a separate factory when different policies are needed or you want explicit control over a specific listener.

### 7.3. Receiving metadata via headers

Spring Kafka maps record metadata into message headers. Common headers include:

- KafkaHeaders.RECEIVED_TOPIC.
- KafkaHeaders.RECEIVED_PARTITION.
- KafkaHeaders.OFFSET.
- KafkaHeaders.RECEIVED_KEY.
- KafkaHeaders.RECEIVED_TIMESTAMP.

You can receive these values using @Header or by accepting ConsumerRecord/ConsumerRecordMetadata. For processing that requires logging and tracing, topic + partition + offset is a useful position identifier; combine it with a business message ID for cross-system tracing.

## 8. Creating topics and choosing partition counts

Topics can be declared using a NewTopic bean and TopicBuilder:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
~~~

This is a sample configuration requiring KafkaAdmin and a cluster with enough eligible brokers for three replicas. TopicBuilder declares the partition count and replication factor when the topic is created. Changing settings on an existing topic depends on admin operations and Kafka's mutability rules; do not assume creating a bean will reduce partition counts or automatically migrate old records.

### 8.1. Choosing the partition count

Partition count affects:
- Maximum parallelism within a consumer group.
- Replicas and data distribution across brokers.
- Number of segment files, metadata, and administrative overhead.
- Ability to scale throughput when adding consumers.
- Key mapping and per-aggregate ordering semantics.

Do not pick a partition count solely based on the current number of application instances. Estimate throughput, record size, number of consumer groups, growth rate, and scaling targets. Too few partitions restrict parallelism; too many partitions increase metadata, segment files, and rebalance overhead.

### 8.2. Partition count and consumer concurrency

Spring Kafka concurrency is the number of consumers created for a listener container, while partition count is the number of data units that can be distributed within a group. Concurrency should be chosen based on partition count, processing capacity, and downstream capacity.

If a topic has six partitions, concurrency 3 usually lets three consumers share the load. If concurrency is 12, at least six consumers will have no partitions from that topic. With multiple topics, assignment results depend on the total partitions in the subscription.

## 9. Partition assignment and specialized listeners

By default, when @KafkaListener declares topics or topicPattern, the Kafka consumer group distributes partitions automatically via the partition assignor.

If you need to explicitly assign partitions to a listener, Spring Kafka supports topicPartitions:

~~~java
@KafkaListener(
        id = "priority-orders",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = { "0", "1" }))
public void listenPriorityOrders(ConsumerRecord<String, String> record) {
    // Process partitions 0 and 1.
}
~~~

Manual assignment is useful for specialized workloads, but it changes how partitions are managed and should not be used merely to pin consumers to partitions if group management already meets requirements.

If using ConsumerSeekAware or seek APIs, clearly define the initial offset, replay range, and duplicate impact. Seeking changes the read position; it does not delete or modify the log.

## 10. Transactions and exactly-once in Kafka

Spring Kafka supports Kafka transactions via a transactional producer factory, KafkaTransactionManager, and transactional listener containers.

To enable transactions, configure DefaultKafkaProducerFactory with a transactionIdPrefix. Spring will manage transactional producers. When a listener container initiates a transaction, consume-process-produce can be coordinated so that output records and offsets commit in the same Kafka transaction.

This supports exactly-once semantics within the scope of Kafka read-process-write. However, it does not automatically include external databases, HTTP APIs, or side effects outside Kafka. When both a database and Kafka participate in business operations, design outbox/inbox, transaction synchronization, or compensating workflows according to consistency requirements.

Non-blocking retry topics do not combine with container transactions in Spring Kafka per the documented mechanism. When choosing a retry topology, decide clearly between blocking retry, retry topics, and transaction semantics; do not combine features without checking the limitations of the version in use.

## 11. Retry, DLT, and partition ordering

When a listener fails, there are two common approaches:

- Blocking retry: the listener container retries the record before continuing according to the error handler/backoff policy. This can keep the partition blocked during retries.
- Non-blocking retry: the record is forwarded to a retry topic with a delay; another consumer processes it later. Once attempts are exhausted, the record can be sent to a Dead Letter Topic (DLT).

Spring Kafka provides @RetryableTopic and @DltHandler to configure retry topics/DLT for listeners. Non-blocking retry creates additional topics and listener containers. An important point: when using retry topics, the original topic's ordering is no longer preserved as before because failed records may be processed after subsequent records.

If per-aggregate ordering is mandatory, consider blocking retry, separating processing streams by key, or storing sequences/versions so consumers can detect gaps. Do not look only at retry success while ignoring ordering consequences.

## 12. Common issues and diagnostics

### 12.1. Events for the same entity processed out of order

Check whether the producer uses a stable key, whether the partitioner is consistent, whether producers publish concurrently, whether the partition count changed, and whether retry topics disrupted ordering. Kafka only preserves append order within a single partition.

### 12.2. Increasing concurrency does not increase throughput

Check the partition count and assignments. If a consumer already owns a single partition or downstream is saturated, adding more consumers will not increase throughput. Also check poll duration, processing time, executor queues, and rebalances.

### 12.3. Consumer re-reads records

Check group.id, offset commits, acknowledgment mode, auto.offset.reset, and whether listeners are restarting/rebalancing. If side effects completed but the offset did not commit, records can be redelivered. Consumers must be idempotent.

### 12.4. Consumer skips backlog after creating a new group

If a group has no offsets and auto.offset.reset=latest, the consumer starts from the current end of the log. If you want to read retained records from the beginning, configure earliest for the new group or intentionally reset offsets.

### 12.5. Hot partitions

If one key generates most of the traffic, all records for that key must go through one partition to preserve ordering. That partition can become a hot partition even while other partitions are lightly loaded. Inspect record distribution across partitions and key design. Do not arbitrarily split keys if doing so breaks business ordering.

### 12.6. Records are sent but consumer does not receive them

Check topic, key, partition, serializer/deserializer, group.id, ACLs, offsets, retention, subscription, and consumer lag. Inspect the producer future to see whether sending succeeded or failed; inspect consumer assignments and committed offsets to locate where the records are.

## 13. Testing with Spring Kafka

Spring Kafka provides spring-kafka-test to support testing. Depending on goals, you can use EmbeddedKafkaBroker or Testcontainers running a real broker.

Recommended test groups:
1. Producer sends a keyed record and verifies partition/offset metadata.
2. Two records with the same key are written to the same partition in the test configuration.
3. Listener receives the expected key, value, topic, partition, and offset.
4. Consumer group resumes reading from the committed offset after a restart.
5. Multiple listener consumers share partitions according to concurrency.
6. Rebalancing occurs when adding or stopping consumers.
7. Processing errors trigger retry/DLT according to configuration.
8. Transaction rollback does not leave output records and offsets in an inconsistent state.
9. Consumer is idempotent when the same record is redelivered.

Do not assert that two records with different keys always land in different partitions; hashes can collide and Kafka does not guarantee even distribution for every pair of keys. Test the property that must hold: the same key under the same topology/partitioner routes deterministically, and order is observed within that partition.

## 14. Production design checklist

- [ ] Topics are named clearly by data stream or domain event.
- [ ] Partition count is based on throughput, parallelism, growth, and operational cost.
- [ ] Keys represent the aggregate/entity requiring ordering.
- [ ] Producers do not send for the same aggregate concurrently if strict publish order is needed.
- [ ] Replication factor, min.insync.replicas, and acks are designed together.
- [ ] Consumer group IDs are stable per application and processing purpose.
- [ ] Concurrency does not exceed partition/downstream needs.
- [ ] max.poll.interval.ms and max.poll.records fit processing duration.
- [ ] Offset commits/acknowledgments align with side effects and idempotency.
- [ ] Retry topics/DLT are chosen with ordering implications in mind.
- [ ] Transaction semantics are understood within Kafka and external systems.
- [ ] Monitoring covers lag, throughput, processing latency, rebalances, failed sends, and DLT.
- [ ] Plans exist for increasing partitions, changing keys, or migrating topics.
- [ ] Integration tests against a broker cover assignment, offsets, retries, and transactions.

## References

- Spring for Apache Kafka Reference — Introduction, version compatibility and features: https://spring.io/projects/spring-kafka/
- Spring Kafka Reference — Sending Messages and KafkaTemplate: https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html
- Spring Kafka Reference — @KafkaListener, partition assignment, concurrency and record metadata: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka Reference — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html
- Apache Kafka Documentation — Topics, partitions, records and ordering: https://kafka.apache.org/documentation/
- Apache Kafka Protocol — Partitioning and ordered commit logs: https://kafka.apache.org/protocol.html
