# How Many Consumer Groups Receive a Single Record?

## 1. A Single Record Can Be Read by Multiple Consumer Groups

In Kafka, a record is written to a partition of a topic. Multiple consumer groups can subscribe to the same topic, and each group maintains its own reading progress. Therefore, a single record can be read independently by multiple different groups.

For example, when Order Service publishes an `OrderCreated` record to the `orders` topic, three systems may all be interested:

- Inventory Service reserves stock.
- Notification Service sends emails or notifications.
- Analytics Service updates reports.

Each system uses its own `group.id`. All three groups can read the `OrderCreated` record, with each group processing at its own pace.

```text
                         Topic: orders
                    Partition 0, 1, 2, ...
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
      Group inventory   Group notification   Group analytics
             |                |                |
       reserve stock    send notifications   update reports
```

There is no fixed limit such as a record only being read by one or two groups. In the model, many independent groups can read the same record. Practical limits come from broker resources, consumer count, read throughput, retention, and the processing capacity of the receiving systems.

An important condition is that the group must subscribe to the topic and have a starting position that allows reaching that record while the record is still retained. A new group starting from `latest` may skip records that already existed before the group started; records already deleted by retention cannot be read again from the topic.

## 2. Different Consumer Groups: Per-Group Fan-Out

Kafka stores records in partition logs. Consumers actively poll data from brokers; Kafka does not create a separate physical copy of a record for each group when the record is published.

Each group has its own committed offsets per partition. Consequently, the same record can be read by group A today, by group B later, and re-read multiple times by group C during replay. Groups do not need to process at the same speed or commit at the same time.

For example, an `OrderCreated` record at offset `120` in `orders-1`:

| Consumer group | Progress before reading | Behavior with record at offset 120 |
|---|---:|---|
| `inventory-service` | 120 | Reads and processes the record |
| `notification-service` | 115 | Reads subsequent records, including offset 120 |
| `analytics-service` | 121 | Already passed this record; does not re-read in normal flow |

If `analytics-service` has already committed offset `121`, that group does not automatically rewind to offset `120` just because another group is reading this record. To re-read it, you must explicitly reset offsets or create a new group with an appropriate starting policy.

This is the fan-out mechanism at the consumer group level: each group is an independent logical subscriber. Kafka simply stores logs by topic/partition; the progress state of each group is managed separately.

## 3. Consumers in the Same Group: Sharing Partitions

A common point of confusion is that while multiple consumer groups can read the same record, multiple consumers belonging to the **same group** do not each receive a copy of that record.

Within a consumer group, each partition at any given time is assigned to at most one consumer member. Consumers in the group divide partitions among themselves to increase parallel processing capacity.

Suppose the `orders` topic has 3 partitions and the `inventory-service` group has 3 consumers:

```text
Topic orders
  Partition 0 ─────▶ inventory consumer A
  Partition 1 ─────▶ inventory consumer B
  Partition 2 ─────▶ inventory consumer C
```

A record in partition 1 is processed by consumer B within this group. Consumers A and C do not receive that same record within the same group. When another group also subscribes to the `orders` topic, that group has its own assignment and can also read the record in partition 1.

### Comparing the Two Cases

| Configuration | Behavior |
|---|---|
| Multiple consumers with the same `group.id` | Share partitions and processing load; a partition is owned by at most one member in the group at a time |
| Multiple consumer groups with different `group.id` values | Each group reads the same topic independently and can read the same record |

Therefore, if you want multiple services to all receive events, use different group IDs. If you want multiple instances of the same service to divide the work, use the same group ID.

## 4. Example of Three Groups Reading the Same Topic

Suppose the `orders` topic has 4 partitions. There are three business groups:

| Group ID | Number of consumers | Purpose |
|---|---:|---|
| `inventory-service` | 2 | Reserve stock and update inventory |
| `notification-service` | 1 | Send emails and notifications |
| `analytics-service` | 4 | Build analytics metrics |

Each group has its own assignment:

```text
                         Topic orders
                    P0    P1    P2    P3
                     |     |     |     |
       +-------------+-----+-----+-----+-------------+
       |                   |                   |
       v                   v                   v
 inventory-service  notification-service  analytics-service
   Consumer A/B       Consumer N             Consumer X/Y/Z/W
 share 4 partitions reads all 4 partitions  share 4 partitions
```

If an `OrderCreated` record resides in partition 2:

- `inventory-service` has one consumer assigned to partition 2 read the record.
- `notification-service` has its single consumer read that record.
- `analytics-service` has one consumer assigned to partition 2 read that record.

Thus, the record can be processed three times at the system level, once by each group in normal processing flow. Each group can succeed, retry, or lag independently of the other two groups.

With 4 partitions, `analytics-service` can use at most 4 active consumers for this topic in the group. If scaled up to 6 consumers, two consumers may not be assigned any partition. Increasing the number of consumers in a single group does not create extra record copies for each consumer.

## 5. Group ID Determines Logical Subscriber Identity

`group.id` is the consumer group identifier. Kafka uses it to manage membership, assignments, and committed offsets. Instances of the same service typically share a stable group ID to divide load and resume from saved progress.

Example Spring Boot configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-service
      auto-offset-reset: earliest
```

When multiple instances of Inventory Service run with `group.id=inventory-service`, they join the same group. If Notification Service accidentally uses this same group ID as well, the two services will split partitions and records; they will no longer each independently receive all events.

Conversely, if a random group ID is generated on every startup, each run may be treated as a new subscriber. With `auto.offset.reset=earliest`, the new group may re-read all retained data; with `latest`, the group may only receive records written after it started. This is usually unintended behavior for a business consumer that needs to maintain progress.

Practical rules:

- Same service needing horizontal scaling: share a stable group ID.
- Two services needing to independently receive the same events: use different group IDs.
- One-off replay or analytics job: can use its own group ID, but starting offset and retention must be chosen intentionally.

## 6. Independent Offsets Between Groups

Kafka stores reading progress by consumer group and partition. Because each group has its own committed offsets, one group does not alter the progress of another group.

For example, on the same `orders` topic, partition 0:

| Group ID | Committed offset | Interpretation |
|---|---:|---|
| `inventory-service` | 250 | Group continues from offset 250 |
| `notification-service` | 210 | Group is reading further behind |
| `analytics-service` | 300 | Group has read further ahead than the other two groups |

If `notification-service` is stopped for an hour, the other two groups continue reading and committing their own offsets. When Notification Service starts back up, it resumes from the committed offset of the `notification-service` group itself, provided the data to be read is still within retention.

This keeps downstream systems independent in uptime and processing speed. One lagging consumer group does not force other groups to stop.

## 7. auto.offset.reset and Whether a New Group Can Read Old Records

A group can only read a record if its starting offset is at or before that record and the record is still in the log. When a group does not yet have a valid committed offset, Kafka uses `auto.offset.reset` to pick the starting point.

| Configuration | Behavior when the group has no valid offset |
|---|---|
| `earliest` | Starts from the earliest existing offset of the partition |
| `latest` | Starts from the current end offset; typically only receives records written after the group joins |
| `none` | Throws an error if no valid committed offset exists |

For example, if a topic already has records from offset `0` to `99` before `reporting-service` runs:

- If the new group uses `earliest`, it can read from the oldest retained offset.
- If the new group uses `latest`, it starts at the end of the log and does not read records written before its start point.
- If the record at offset `20` has already been deleted by retention, no configuration can make that record reappear from the current topic.

`auto.offset.reset` is only used when the group has no valid committed offset or the offset is no longer valid. It does not overwrite an existing committed offset. To replay a group that already has progress, you need an explicit offset reset or a new group ID.

## 8. Can a Single Group Receive a Record Multiple Times?

Yes. Distinguish **a single logical read by a group** from the number of times a record is actually delivered to the application. Kafka consumers are typically deployed with at-least-once semantics: if the application processes a record successfully but stops before committing the offset, the record can be redelivered after a restart or rebalance.

Example:

1. `inventory-service` reads the record at offset `250`.
2. The service updates the database successfully.
3. The process stops before committed offset `251` is persisted.
4. A new consumer receives the partition and resumes from the old committed offset.
5. The record at offset `250` is redelivered.

Therefore, you should not assume each group receives a record strictly once. Design idempotent consumers, such as storing processed `eventId` values with a unique constraint or using business keys so repeated operations produce no additional side effects.

Producer idempotence and consumer idempotency solve different problems. An idempotent producer protects internal producer retries within Kafka's scope; it does not automatically prevent a consumer from reprocessing a record after a restart, nor does it deduplicate new sends explicitly invoked by the application.

## 9. How Does One Group Read Multiple Topics?

A consumer group can subscribe to multiple topics. That group maintains independent offsets for each partition of all subscribed topics. Any other group can also subscribe to the same set of topics or only a subset of them.

For example, Notification Service needs to receive both order creation and payment events:

```java
@Component
public class NotificationListener {

    @KafkaListener(
            topics = {"orders", "payments"},
            groupId = "notification-service")
    public void onEvent(String payload) {
        // Classify and handle event.
    }
}
```

The `notification-service` group has assignments for the partitions of both topics. If Analytics Service also subscribes to `orders` and `payments` with `groupId=analytics-service`, the Analytics group can independently read records from those two topics.

If you need to route each event type to separate handler methods, you can declare multiple `@KafkaListener` methods or use `@KafkaHandler` with the appropriate configuration. The key point is that the group ID determines progress and partition sharing; it does not classify payloads by business type on its own.

## 10. Implementing Multiple Groups with Spring Kafka

In Spring Kafka, the `groupId` attribute of `@KafkaListener` specifies the consumer group for the endpoint. You can declare two listeners on the same topic with different group IDs:

```java
@Component
public class OrderEventListeners {

    @KafkaListener(
            topics = "orders",
            groupId = "inventory-service")
    public void updateInventory(OrderCreated event) {
        // Inventory processes independently.
    }

    @KafkaListener(
            topics = "orders",
            groupId = "analytics-service")
    public void updateAnalytics(OrderCreated event) {
        // Analytics also receives the topic's records.
    }
}
```

The two listeners form two independent groups, and each group has its own progress. You need to configure a deserializer/converter compatible with the `OrderCreated` type.

If `spring.kafka.consumer.group-id` is used as a default, `groupId` declared directly on `@KafkaListener` overrides the default group ID for that endpoint. Name groups after the service or processing purpose to prevent two business flows from accidentally sharing a group.

### Scaling Horizontally Within a Group

To run multiple consumers in the same group, you can increase the number of application instances or set concurrency on the listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        concurrency = "3")
public void updateInventory(OrderCreated event) {
    // Process a record assigned to this consumer.
}
```

`concurrency=3` instructs the container to create three consumers for the endpoint in that group. The number of consumers actually assigned partitions cannot exceed the number of partitions the group receives from the topic subscription. If the topic only has two partitions, at most two consumers have active partitions at a time; the remaining consumer receives no partitions.

## 11. Do Multiple Groups Cause Kafka to Store Multiple Copies of Data?

Not in the sense of each group having its own physical copy. A record is stored once in the partition log, with the number of replicas determined by the replication factor. Groups read the same log and store their own progress in Kafka's offset management mechanism (the internal `__consumer_offsets` topic).

However, adding groups still increases read load:

- Each group has its own consumers and generates fetch requests.
- Brokers must serve additional read traffic, network bandwidth, and metadata.
- Downstream applications use their own CPU, memory, connections, and database resources.
- If multiple groups read slowly, they may hold old progress while retention continues to apply according to the topic configuration.

Thus, multiple groups do not multiply data copies on disk by the number of groups, but they can significantly increase consumer-serving overhead. Monitor consumer lag, fetch rate, broker network, request latency, and receiving system load.

## 12. Viewing Each Group's Progress with Kafka CLI

The following command displays the offsets and lag of a consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group inventory-service
```

Run similarly for `notification-service` and `analytics-service` to see that each group has independent progress. Common columns:

| Column | Meaning |
|---|---|
| `GROUP` | Consumer group being queried |
| `TOPIC` / `PARTITION` | Partition for which the group has progress |
| `CURRENT-OFFSET` | Committed offset of the group |
| `LOG-END-OFFSET` | End offset used to compare progress |
| `LAG` | Offset distance between end and committed offset |

For example, the same partition may display:

```text
GROUP                 TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
inventory-service     orders  0          250              300             50
notification-service orders  0          210              300             90
analytics-service    orders  0          300              300             0
```

Analytics has committed up to the end of the log at the time of observation, while Inventory and Notification still have different lag values. This does not affect the offsets of the remaining groups.

If a group does not yet have a committed offset, some columns may display `-`. That does not mean the topic has no records; the group may not have started reading or may not have committed offsets yet.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Multiple services share one `group.id` when independent reception is needed | Services split partitions; each record does not reach all services | Use a separate group ID for each logical subscriber |
| Each instance of the same service uses a different group ID | Each instance independently reads the entire stream, causing duplicate processing at the system level | Share a stable group ID across replicas of the same service |
| Generating a random group ID on every restart | New group does not inherit old offsets; may replay or skip data depending on reset policy | Use a stable group ID for long-lived consumers |
| Assuming multiple consumers in the same group all receive the same record | Broken fan-out design and missed processing | Distinguish work-sharing within a group from fan-out across groups |
| Assuming each group has its own copy of the topic | Misunderstanding storage usage and retention | Remember that groups read the same partition log while offsets are stored separately |
| Assuming a group receives a record strictly once | Side effects can be duplicated on restart/rebalance | Design idempotent consumers and commit after processing |
| Setting `latest` for a new group while expecting to read history | Group skips records prior to its starting point | Use `earliest` if retained historical data must be read, or perform a controlled offset reset |

## 14. Test Scenarios for Fan-Out and Work-Sharing

You can verify the behavior using a test topic and three independent groups:

1. Create an `orders` topic with at least two partitions.
2. Start two consumers in the `inventory-service` group.
3. Start one consumer in the `notification-service` group.
4. Start one consumer in the `analytics-service` group.
5. Send a record with a fixed key to determine its partition.
6. Verify that one member of each group reads the record; the two consumers in the same Inventory group do not both receive a copy of that record.
7. Stop Notification Service, continue sending records, and verify the remaining two groups still read them.
8. Restart Notification Service with the same group ID and verify it resumes from that group's committed offset.
9. Test a new group with `earliest` and `latest` to observe the difference when reading historical records.
10. Have a listener process successfully but stop before committing to confirm the record can be redelivered within the same group.

When testing, do not rely only on console logs. Record `eventId`, `groupId`, topic, partition, and offset in test results to determine which group processed a record and whether it was redelivered.

## 15. Summary

- A single record can be read independently by multiple different consumer groups subscribed to the same topic.
- Each group has its own committed offsets; one group lagging or stopping does not cause other groups to lose progress.
- Consumers in the same group share partitions; a partition is assigned to at most one member of the group at a time.
- To have multiple services receive events, use different group IDs; to scale a single service horizontally, instances share the same group ID.
- A new group can only read historical data if its starting offset permits it and the records are still within retention.
- Kafka does not create a physical copy of a topic per group; multiple groups still increase read load and downstream resource usage.
- At-least-once delivery can cause a record to be redelivered within the same group; consumers must be idempotent.

By properly distinguishing fan-out across consumer groups from work-sharing within a group, you can design multiple services that react to an event while still scaling each service independently with Spring Kafka.
