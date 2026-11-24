# Queue Model via Consumer Groups

## 1. Why Can Kafka Act Like a Queue?

Kafka stores events in a topic as an ordered log. Producers write records to the topic; consumers read records by offset. Kafka does not delete a record immediately after a consumer finishes reading it. Records are kept according to the topic's retention policy, while each consumer group tracks its own reading progress.

When multiple consumers share the same `group.id`, Kafka divides the topic's partitions among those consumers. Each record belonging to a partition is delivered to one consumer in the group at a time. Consumers in the same group therefore compete to process the shared workload. This is how consumer groups create a model similar to a queue with competing consumers.

The key point to remember is that the queue behavior here is a way of organizing consumption. The data remains in the Kafka log; processing progress is represented by each group's offsets.

## 2. Topics, Partitions, and Consumer Groups Working Together

The three concepts play distinct roles:

| Component | Role |
|---|---|
| Topic | Event stream that producers write to and consumers subscribe to read |
| Partition | Unit of storage, ordering, and load distribution for a topic |
| Consumer group | A group of consumers sharing topic reading work and tracking progress under a group ID |

For example, topic `orders` has six partitions. Group `order-processor` has three consumers. Kafka assigns the partitions to the consumers in the group, such as:

| Consumer in group `order-processor` | Assigned Partitions |
|---|---|
| Consumer A | P0, P1 |
| Consumer B | P2, P3 |
| Consumer C | P4, P5 |

Each partition is assigned to at most one consumer in the same group at a time. A single consumer can receive multiple partitions. The exact assignment is determined by Kafka's partition assignment mechanism; the table above simply illustrates a balanced split.

The diagram below shows two independent groups reading the same topic:

~~~mermaid
flowchart LR
    T["Topic orders<br/>P0 ... P5"]
    T --> G1["Group order-processor"]
    T --> G2["Group fraud-monitor"]
    G1 --> A["Consumer A"]
    G1 --> B["Consumer B"]
    G1 --> C["Consumer C"]
    G2 --> D["Consumer D"]
    G2 --> E["Consumer E"]
~~~

In `order-processor`, consumers A, B, and C split the partitions so a record is processed by only one member of the group at a time. The `fraud-monitor` group has its own reading progress and also reads records from topic `orders`. Thus, the same event can be received and processed independently by each group—for example, for order processing and for fraud checks.

You can draw the following parallels:

- Consumers with the same group ID behave like workers pulling jobs from a single queue.
- Two different group IDs behave like two independent subscribers; each system can read the same event stream.
- One consumer stopping does not make records disappear. Other consumers in the group can take over its partitions after Kafka redistributes them.

## 3. Consumer Groups Determine Parallel Processing Capacity

The number of usefully active consumers in a group is bounded by the topic's partition count.

Suppose a topic has six partitions:

| Consumers in Group | Outcome |
|---:|---|
| 1 | One consumer reads all six partitions |
| 3 | Three consumers share the six partitions |
| 6 | Up to six consumers each have a partition to read |
| 8 | Up to six consumers have partitions; two consumers remain unassigned |

Increasing consumers beyond the partition count does not increase parallelism for that topic. If more independent processing streams are needed, consider increasing partitions while evaluating impacts on key ordering, data distribution, and broker resources.

### Record Ordering

Kafka guarantees ordering within a single partition, not a global order across multiple partitions. If a producer sends events with the same key, such as `orderId`, those records are normally routed to the same partition by the active partitioner. This allows events for the same order to be read in order within that partition.

Therefore, when designing a topic, pick a key based on the business entity that requires ordering. Without a suitable key, records can spread across multiple partitions and be processed concurrently in different orders.

### Multiple Instances of a Spring Kafka Application

Replicas of the same service typically share a group ID. For example, three pods of the order-processing service all join group `order-processor`; Kafka divides partitions among the consumers across all three pods.

Within a Spring Kafka application, the listener container's `concurrency` setting can spawn multiple consumers in the same group. If each pod sets `concurrency = 3` and there are two pods, the group can have six consumers in total. The number of consumers that actually receive partitions is still capped by the number of subscribed partitions.

When consumers join, leave the group, or lose connectivity, Kafka may perform a rebalance to reassign partitions. During a rebalance, reading may pause briefly; afterwards, the new consumer resumes from the group's committed progress.

## 4. Offsets Are Progress Specific to Each Group

Kafka tracks offsets by the combination of group ID, topic, and partition. Two groups reading the same topic do not share offsets. Group `order-processor` may have progressed to one position while `fraud-monitor` is still reading at an earlier position.

A committed offset is the saved checkpoint allowing a group to resume after a consumer restarts or a partition is handed to another consumer. Reading a record neither deletes it from the topic nor means business processing has safely completed.

For processing that writes data or calls external services, the order of processing and committing matters greatly:

1. If the application finishes processing and then crashes before committing the offset, the record may be read and processed again.
2. If the application commits the offset before processing completes, a failure afterward can cause business work to be skipped when the group resumes reading.

Therefore, applications generally need to succeed in processing before confirming progress, and design business operations to be idempotent to tolerate redelivered records. Delivering a record to one member of a group does not guarantee that business side effects occur only once.

The `auto.offset.reset` property only determines the starting position when the group has no valid offset. For example, `earliest` starts from the oldest record still retained in the topic; it does not recover data whose retention has expired. Once a group has a valid offset, Kafka resumes from the saved offset.

## 5. Declaring a Consumer Group with Spring Kafka

You can configure the group ID and initial read policy in `application.yml`:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

A listener joining that group:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${spring.kafka.consumer.group-id}",
        concurrency = "3"
    )
    public void consume(String payload) {
        // Validate and process the order event.
        // Only confirm progress after processing according to the chosen policy.
    }
}
~~~

In this example:

- `groupId` identifies the subscription identity and reading progress of the order-processing service.
- `concurrency = "3"` instructs the listener container to create three concurrent consumers in the group.
- `enable-auto-commit: false` disables periodic auto-committing by the consumer client; Spring Kafka manages offset confirmation according to the listener container's ack mode configuration.
- `auto-offset-reset: earliest` applies when the group has no valid offset yet.

The example uses `String` to focus on the group mechanism. Real applications need deserializers matching the payload format, error handling, and an ack mode aligned with business requirements. When running multiple replicas, replicas of the same service must join the same group ID to share load.

If another service also needs to receive every `orders` event, that service should use its own group ID, such as `fraud-monitor`. If it shares `order-processor`, the two services will split partitions and each will only receive its assigned subset of data instead of both receiving all events.

## 6. Choosing a Group Model for Real-World Problems

When designing consumer groups for a messaging flow, answer these questions:

- **Who needs to receive the events?** Replicas of the same business function should share a group ID. Each independent business function needing all events should have its own group ID.
- **How much parallelism is needed?** Choose partition counts based on throughput and desired parallelism; useful consumers in a single group cannot exceed assigned partitions.
- **Which entity needs ordering preserved?** Choose a suitable message key, such as `orderId`, and keep events for that key in the same partition.
- **What happens on failure?** Determine when offsets are committed, how retries work, and how duplicate side effects are prevented. Monitor consumer lag to see how far a group is behind the end of the log.
- **What happens when scaling the application?** Anticipate rebalances when consumers scale up, scale down, or disconnect; ensure listeners can safely resume from committed offsets.

For instance, topic `orders` has six partitions. Group `order-processor` runs three consumers to share order-processing load. Group `fraud-monitor` runs two consumers for fraud checking. Both groups can read the entire `orders` event stream, yet each group has independent members, partition assignments, and offsets. When a consumer in `order-processor` stops, Kafka reassigns partitions to the remaining members and the group continues from its committed progress.

That is the foundation of the queue model via consumer groups in Kafka: **same group shares work; different groups have independent consumption progress**. Understanding this boundary helps you design partition counts, consumer counts, group IDs, and commit mechanisms suited to each Spring Kafka workload.
