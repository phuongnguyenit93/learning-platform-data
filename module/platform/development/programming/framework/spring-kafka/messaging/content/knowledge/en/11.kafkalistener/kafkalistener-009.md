# Declaring topicPartitions

`@KafkaListener` can receive records by subscribing to one or more topics, or by being assigned a specific set of partitions directly. When you need to specify the exact topics and partitions a listener reads from, Spring Kafka provides the `topicPartitions` attribute along with the nested annotations `@TopicPartition` and `@PartitionOffset`.

In the `SPRING_KAFKA_MESSAGING` module, consumers typically use `@KafkaListener` to receive events from Kafka. Declaring `topicPartitions` is useful when the application must control the exact partition range being read, process a pre-partitioned data stream, or run a scoped replay task. Because this is a manual assignment mechanism, it is important to understand its impact on consumer groups, rebalances, offsets, and scalability.

## 1. What Is `topicPartitions` Used For?

A topic can consist of multiple partitions. When a listener subscribes to a topic, the Kafka group coordinator distributes partitions among consumer members in the same group. When a listener declares `topicPartitions`, the application specifies directly which partitions the consumer reads.

Example topic `orders` with four partitions:

```text
orders
├── partition 0
├── partition 1
├── partition 2
└── partition 3
```

If a listener is declared to read only partitions `0` and `2`, it receives records from those two partitions. Records in partitions `1` and `3` are outside this listener's scope.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class OrderPartitionListener {

    @KafkaListener(
            id = "ordersPartitionListener",
            groupId = "orders-partition-reader",
            topicPartitions = @TopicPartition(
                    topic = "orders",
                    partitions = { "0", "2" }
            )
    )
    public void listen(String payload) {
        System.out.println("Received order event: " + payload);
    }
}
```

In this example, `partitions` is a list of partition indices as strings. Kafka numbers partitions starting at `0`; the topic must exist and have the declared partitions. `topicPartitions` does not create new topics or partitions.

## 2. Declaring Multiple Topics and Partitions

`topicPartitions` accepts an array of `@TopicPartition`, so a single listener can read partitions belonging to multiple different topics:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class IntegrationPartitionListener {

    @KafkaListener(
            id = "integrationPartitionListener",
            groupId = "integration-reader",
            topicPartitions = {
                    @TopicPartition(
                            topic = "orders",
                            partitions = { "0", "1" }
                    ),
                    @TopicPartition(
                            topic = "payments",
                            partitions = { "2" }
                    )
            }
    )
    public void listen(ConsumerRecord<String, String> record) {
        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s value=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value()
        );
    }
}
```

The listener above receives records from `orders-0`, `orders-1`, and `payments-2`. Because multiple topics can invoke the same listener method, inspect `record.topic()` before applying data-type-specific business rules.

When using `topicPartitions`, do not simultaneously declare `topics` or `topicPattern` expecting to merge the two mechanisms. `topicPartitions` is an explicit partition assignment option with its own precedence on the endpoint; choose one clear declaration style per listener.

## 3. Difference Between Topic Subscription and Partition Assignment

This is the most critical distinction when using `topicPartitions`.

| Declaration style | Consumer mechanism | Who distributes partitions? | Automatic group rebalance? |
|---|---|---|---|
| `topics = "orders"` | `subscribe()` | Kafka group coordinator | Yes |
| `topicPattern = "orders\\..*"` | `subscribe()` by pattern | Kafka group coordinator | Yes |
| `topicPartitions = @TopicPartition(...)` | `assign()` | Application declares partitions | No |

When subscribing, the consumer registers interest in topics and participates in group management. Kafka distributes partitions among members and rebalances when members join, leave the group, or metadata changes.

When manually assigning, the application passes the explicit `TopicPartition` list directly to the consumer. The consumer does not use the group coordinator to distribute partitions and does not automatically rebalance when other instances join or leave. If deploying multiple instances, the system itself must ensure each partition is assigned to the intended instance.

`groupId` can still be used to store committed offsets, but it does not turn manual assignment into a subscription. If two instances both declare and read the same partition, both may process the same records; if they also share a group ID for committing offsets, they may overwrite each other's progress. Do not use `topicPartitions` as a substitute for consumer group load balancing.

## 4. Using `@PartitionOffset` to Set the Starting Position

Beyond specifying partitions, Spring Kafka lets you declare initial offsets via `partitionOffsets` and `@PartitionOffset`:

The `@PartitionOffset` annotation resides in the `org.springframework.kafka.annotation` package alongside `@KafkaListener` and `@TopicPartition`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.PartitionOffset;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class OrderReplayListener {

    @KafkaListener(
            id = "ordersReplayListener",
            groupId = "orders-replay",
            topicPartitions = @TopicPartition(
                    topic = "orders",
                    partitionOffsets = {
                            @PartitionOffset(
                                    partition = "0",
                                    initialOffset = "100"
                            ),
                            @PartitionOffset(
                                    partition = "1",
                                    initialOffset = "250"
                            )
                    }
            )
    )
    public void listen(String payload) {
        // Process replay data starting from the specified offsets.
    }
}
```

In this example, the listener is assigned partitions `0` and `1` of topic `orders`; Spring Kafka seeks to the declared offsets when applying initial offset configuration for those partitions. An offset is a position within an individual partition, not a topic-wide global sequence number.

`initialOffset` is declared as a string so the annotation can use configuration values or placeholders as supported by Spring. Check the seek semantics of the Spring Kafka version you are using and test both initial startup and restarts: an explicit seek may cause the listener to re-read or skip data relative to existing committed offsets.

If no explicit offset seek is declared, the consumer uses the group's committed offset if available; when no valid committed offset exists, `auto.offset.reset` determines the starting position, such as `earliest` or `latest`. Do not confuse `initialOffset` with `auto.offset.reset`: one is a seek position directed by listener configuration, while the other is the Kafka consumer's fallback policy when no valid offset exists.

## 5. Distinguishing Partition Assignment from Acknowledgment/Commit

`topicPartitions` determines **which partitions the consumer reads**. It does not determine **when offsets are committed**.

Spring Kafka manages commits according to the listener container's `AckMode`, such as `RECORD`, `BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE`. Commit behavior also depends on `enable.auto.commit` and container settings. Therefore:

- You can manually assign partitions while still using container-managed automatic offset commits.
- You can use manual acknowledgment on a listener subscribed to topics normally.
- `@PartitionOffset(initialOffset = ...)` is an initial seek setting; it is not an offset commit command.
- Committing an offset records the consumer group's processed progress; it does not alter the assigned partition list.

If a listener uses manual acknowledgment, configure the corresponding `AckMode` and acknowledge only after business processing succeeds. Do not try to use `topicPartitions` to fix duplicate errors or out-of-order commits; design acknowledgment, idempotency, and error handling separately.

## 6. Combining `topicPartitions` with Concurrency

`@KafkaListener` can configure `concurrency` so Spring Kafka creates multiple consumers running concurrently in the listener container. When using explicit partition assignment, Spring Kafka distributes the declared partitions among child consumers per container configuration.

```java
@KafkaListener(
        id = "ordersConcurrentListener",
        groupId = "orders-concurrent-reader",
        concurrency = "2",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = { "0", "1", "2", "3" }
        )
)
public void listen(String payload) {
    process(payload);
}
```

With four partitions and concurrency two, the container can divide work across two child consumers. If concurrency exceeds the number of assigned partitions, some child consumers will have no partitions to read. Raising concurrency neither increases the partition count nor adds parallelism beyond the number of partitions holding data.

If every application instance launches a listener with the exact same explicit assignment, every instance will independently read the same set of partitions. Concurrency inside one instance does not coordinate partition splitting across separate instances. You must design a deployment-level partition allocation scheme if each partition should have only a single owner.

## 7. When Should You Use `topicPartitions`?

| Scenario | Should you use it? | Reason |
|---|---|---|
| A replay job must read a few specific partitions | May fit | Read scope is strictly controlled |
| Application has partition routing/ownership managed externally | Fits | Can bind listeners to externally allocated partitions |
| Each consumer instance must read a fixed partition set per topology | May fit | Requires ownership management during scaling/restarts |
| Standard service needing automatic consumer scaling within a group | Usually not recommended | `topics` and `subscribe` let Kafka rebalance automatically |
| Multiple instances running and wanting Kafka to split partitions automatically | Not recommended | Manual assignment does not coordinate across instances |
| Topic whose partition count changes frequently | Requires caution | Explicitly declared partition lists may need updating |

For most standard event-processing services, topic subscription is simpler and easier to scale. Use explicit assignment only when there is a clear operational or routing requirement.

## 8. Configuring Topic and Group ID

Basic consumer configuration example:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-partition-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
```

If `groupId` is declared directly on `@KafkaListener`, it is used for that listener; otherwise, the listener can inherit the group ID from the consumer factory configuration. Choose a stable group ID if committed offsets should be shared across restarts of the same logical consumer.

With manual assignment, the group ID mainly ties into offset commits and consumer identity for related mechanisms; it does not make Kafka distribute partitions. Avoid sharing the same group ID across instances assigned overlapping partitions without an explicit commit/ownership design.

Topics and partitions must be provisioned beforehand. If a topic does not exist yet or a partition index is invalid, the listener may fail to start or encounter errors creating the consumer assignment. Manage topics via `KafkaAdmin`/`NewTopic` or provisioning pipelines and verify partition counts before deploying the listener.

## 9. Testing Listeners That Use `topicPartitions`

Tests should prove that the listener receives the expected partitions and ignores records from out-of-scope partitions.

Recommended test scenarios:

- Create a test topic with at least three partitions.
- Send records to each partition using a producer that specifies the target partition.
- Start a listener assigned a subset, e.g., partitions `0` and `2`.
- Verify the listener receives records from the two assigned partitions and does not receive records from partition `1`.
- Inspect `ConsumerRecord.partition()` metadata or the `KafkaHeaders.RECEIVED_PARTITION` header.
- Test `@PartitionOffset` on initial startup and on restart when a committed offset already exists.
- If concurrency is greater than one, verify how Spring Kafka splits partitions across child consumers.
- If deploying multiple instances, test overlapping partition assignments to observe duplicate processing and commit race risks.

Embedded Kafka or Testcontainers can be used. Create a dedicated topic per test, set the partition count explicitly, and use a unique group ID so offsets from earlier tests do not affect results.

## 10. Common Pitfalls

- **Confusing `topicPartitions` with `topics`:** one performs manual partition assignment, while the other subscribes for group-coordinator distribution.
- **Assuming manual assignment rebalances automatically:** when an instance dies or a new one joins, the application must update ownership/assignment via its own mechanism.
- **Declaring nonexistent partitions:** a listener cannot read uncreated partitions; check topic metadata before deploying.
- **Confusing initial offset with committed offset:** an explicit seek can alter the starting position relative to saved progress; test restarts.
- **Assuming `auto.offset.reset` always overrides `initialOffset`:** these are separate mechanisms; `auto.offset.reset` is only a fallback when no valid committed offset exists.
- **Thinking assignment controls commits:** commit mode is an independent setting on the listener container.
- **Using the same group ID and same partitions across multiple instances:** can cause duplicate processing and overwrite committed offsets.
- **Increasing concurrency without increasing partitions:** extra child consumers will have no partitions to process.
- **Failing to update partition lists when a topic grows:** listeners using explicit assignment may ignore newly added partitions.
- **Using manual assignment for systems needing auto-scaling:** managing ownership is more complex than topic subscription.

## 11. Checklist Before Using `topicPartitions`

- [ ] There is a clear requirement to specify partitions rather than subscribe to the topic.
- [ ] The topic already exists and all partition indices are valid.
- [ ] Understood that the listener uses manual assignment with no automatic group rebalance.
- [ ] A plan exists to allocate partitions across instances and handle ownership on scale/restart.
- [ ] Group ID is chosen consistently with the committed offset strategy.
- [ ] `initialOffset` is used intentionally and tested across restarts.
- [ ] Assignment, seek, acknowledgment, and offset commit are clearly distinguished.
- [ ] Concurrency does not exceed needs or the number of assigned partitions.
- [ ] Producer/consumer tests verify the exact partitions read.
- [ ] Monitoring is in place for partition assignment, lag, listener errors, and duplicate processing.

`topicPartitions` allows Spring Kafka to bind a listener to specific partitions and can combine with `@PartitionOffset` to control the starting position. In return, the application takes responsibility for managing partition assignment and ownership lifecycle. When you want Kafka to balance load and rebalance automatically across instances, subscribing via `topics` is usually the better choice.
