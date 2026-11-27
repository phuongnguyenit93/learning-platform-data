# Lab: Message Distribution Across Multiple Groups

In Spring Cloud Stream, a single destination can serve multiple consuming groups. Each group has its own purpose, such as updating inventory, sending notifications, and aggregating revenue. How consumer groups are configured determines whether messages are split across multiple instances doing the same job or delivered to multiple groups so each group performs an independent job.

This lab uses the same `orders.placed` stream to verify two behaviors:

- **Multiple distinct groups:** each group receives the entire event stream to perform a separate task.
- **Multiple instances in the same group:** instances share the work; each message is delivered to one consumer in the group according to the broker's mechanism.

Distinguish a group from an instance. A group name represents a logical consuming stream; an instance is a running process participating in that group. Changing a group name can alter distribution behavior and read position, so groups must be named intentionally.

## 1. Distribution model to observe

Suppose the order service emits events to the `orders.placed` destination. Three downstream groups have different responsibilities:

- `inventory-v1`: updates inventory.
- `notifications-v1`: sends notifications to customers.
- `sales-analytics-v1`: updates sales metrics.

~~~text
                         orders.placed
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
        Group inventory   Group notifications  Group analytics
             |                 |                 |
        +----+----+       +----+----+        +----+----+
        |         |       |         |        |         |
      App A     App B    App A     App B     App A     App B
      (same     (same    (same     (same     (same     (same
       group)    group)   group)    group)    group)    group)
~~~

Each group is an independent consuming stream. When an event is published to the destination, each group gets the opportunity to receive that event. Inside each group, the broker distributes work across the group's consumer members.

| Configuration | Expected outcome |
|---|---|
| Three bindings with the same destination, three different groups | Each group receives the destination's events |
| Two instances with the same destination and same group | Both instances share the group's workload |
| Two instances with the same destination but different groups | Each instance/group receives its own stream; both may process the same event |
| Each instance uses its own anonymous group | Instances typically behave as independent groups without sharing a durable consumption progress |

This does not mean the broker always delivers messages strictly once end-to-end. When a consumer finishes processing before acknowledging or committing the offset, the message may be redelivered. Therefore, consumers still need idempotent processing based on an event ID or business key.

## 2. Preparing the event and consumers

Use a simple event that all groups receive:

~~~java
import java.math.BigDecimal;

public record OrderPlaced(
    String eventId,
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}
~~~

Create three `Consumer<OrderPlaced>` beans. Each bean represents a single responsibility:

~~~java
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderGroupConsumers {

    private static final Logger log =
        LoggerFactory.getLogger(OrderGroupConsumers.class);

    @Bean
    Consumer<OrderPlaced> inventoryProjection() {
        return event -> log.info(
            "INVENTORY eventId={} orderId={}",
            event.eventId(),
            event.orderId()
        );
    }

    @Bean
    Consumer<OrderPlaced> notificationSender() {
        return event -> log.info(
            "NOTIFICATION eventId={} customerId={}",
            event.eventId(),
            event.customerId()
        );
    }

    @Bean
    Consumer<OrderPlaced> salesAnalytics() {
        return event -> log.info(
            "ANALYTICS eventId={} total={} currency={}",
            event.eventId(),
            event.total(),
            event.currency()
        );
    }
}
~~~

In a real application, replace the logging calls with the corresponding business operations. Do not make one consumer perform all tasks if those tasks have different deployment lifecycles, scaling needs, or error policies. Separating consumers allows each group to be scaled and operated independently.

With the three beans above, Spring Cloud Function recognizes three functions by bean name. Spring Cloud Stream creates the input bindings:

| Bean | Input binding |
|---|---|
| `inventoryProjection` | `inventoryProjection-in-0` |
| `notificationSender` | `notificationSender-in-0` |
| `salesAnalytics` | `salesAnalytics-in-0` |

## 3. Configuring three groups reading one destination

The example below uses the Kafka binder. All three bindings point to the `orders.placed` topic, yet each binding has its own group:

~~~yaml
spring:
  application:
    name: order-group-lab

  cloud:
    function:
      definition: "inventoryProjection;notificationSender;salesAnalytics"

    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.placed
          group: inventory-v1
          content-type: application/json

        notificationSender-in-0:
          destination: orders.placed
          group: notifications-v1
          content-type: application/json

        salesAnalytics-in-0:
          destination: orders.placed
          group: sales-analytics-v1
          content-type: application/json

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
        bindings:
          inventoryProjection-in-0:
            consumer:
              startOffset: earliest
          notificationSender-in-0:
            consumer:
              startOffset: earliest
          salesAnalytics-in-0:
            consumer:
              startOffset: earliest
~~~

Explanation:

- `spring.cloud.function.definition` activates the three independent consumers. Semicolons separate the functions.
- All three input bindings share the `orders.placed` destination.
- Each binding has its own group, so each group tracks its own consumption progress.
- `startOffset: earliest` instructs the Kafka binder to start from the earliest offset when a group has no committed offsets yet. If the group already has offsets, the consumer resumes from the saved offsets; this property does not reset existing offsets.
- `KAFKA_BROKERS` allows changing the broker address per environment.

Group names should stay stable across deployments if you want consumption progress to continue. For example, `inventory-v1` represents the inventory processing group. Do not generate a new group on every startup unless you intend to replay all data.

## 4. Starting Kafka and testing fan-out across groups

Create the topic with four partitions so later scaling steps can observe in-group distribution:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic orders.placed --partitions 4 --replication-factor 1
~~~

For Kafka on Windows, the script may reside in `bin\windows` and use the `.bat` extension, depending on the distribution.

Start the Spring Boot application:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Open another terminal and send several events to the topic:

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders.placed
~~~

Enter each JSON payload on a single line:

~~~json
{"eventId":"evt-001","orderId":"ord-1001","customerId":"cus-01","total":125000,"currency":"VND"}
{"eventId":"evt-002","orderId":"ord-1002","customerId":"cus-02","total":85000,"currency":"VND"}
{"eventId":"evt-003","orderId":"ord-1003","customerId":"cus-03","total":210000,"currency":"VND"}
~~~

Observe the application logs. For each event ID, you should see one `INVENTORY` line, one `NOTIFICATION` line, and one `ANALYTICS` line. For example:

~~~text
INVENTORY eventId=evt-001 orderId=ord-1001
NOTIFICATION eventId=evt-001 customerId=cus-01
ANALYTICS eventId=evt-001 total=125000 currency=VND
~~~

The order of log lines may vary because groups consume independently. What matters is confirming that each event was processed across all three groups. Groups are not required to process at the exact same instant or finish in the same order.

You can build a results table:

| Event ID | inventory-v1 | notifications-v1 | sales-analytics-v1 |
|---|---|---|---|
| evt-001 | Yes | Yes | Yes |
| evt-002 | Yes | Yes | Yes |
| evt-003 | Yes | Yes | Yes |

If a group does not receive events, check whether the function is activated, the binding name, destination, group, broker connectivity, and current offsets. If the group already existed from an earlier run, it may be reading from its committed offset rather than re-reading older records.

## 5. Testing two instances in the same group

After verifying fan-out, run two instances of the same application. Keep the groups unchanged in YAML and start the application twice in two terminals or separate processes.

~~~text
Instance A                         Instance B
    |                                  |
    +---------- inventory-v1 ----------+
    |                                  |
    +-------- notifications-v1 --------+
    |                                  |
    +------- sales-analytics-v1 --------+
~~~

For each group, both instances join the same consumer group. Kafka distributes partitions among the consumer members. Each record in a partition is processed by one member in the group during normal operation; other groups still maintain independent read progress.

Send more events, such as `evt-004` through `evt-020`. Observe the logs of both processes:

- Events within the same group are split between instance A and B according to partition assignment.
- The total number of distinct event IDs processed within a group must match the number of events sent, after accounting for errors and redeliveries.
- The same event ID still appears in every logical group: inventory, notification, and analytics.
- Do not expect an exact 50/50 split between the two instances. Distribution depends on partition count, keys, load, and rebalance timing.

If the topic only has one partition, only one consumer in the group can be assigned that partition at a time. The other instance may process zero records in that group. Thus, parallel active consumers within a Kafka group are bounded by the number of assigned partitions.

This highlights an important distinction between two scaling approaches:

- Adding instances in the same group divides the work of a single task, within partition limits.
- Creating a new group creates an additional independent consuming stream, causing the new group to also read the destination's events.

Do not change the group ID when you only intend to add an instance. If each instance accidentally uses a different group, they will receive duplicate streams and may execute the same side effects multiple times.

## 6. Inspecting Kafka consumer groups and lag

Use the following command to inspect a group's status:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group inventory-v1
~~~

The output typically includes these fields:

| Field | Meaning |
|---|---|
| TOPIC | Topic the group is reading |
| PARTITION | Partition being described |
| CURRENT-OFFSET | Offset committed by the group |
| LOG-END-OFFSET | Latest offset currently available on the partition |
| LAG | Number of records the group is behind the end of the log |
| CONSUMER-ID | Consumer member receiving the partition |
| HOST | Host running the consumer |
| CLIENT-ID | Kafka client identifier |

Run the same command for `notifications-v1` and `sales-analytics-v1`. Each group has its own offsets and lag. One group processing fast does not mean the other groups are keeping up.

If lag grows continuously:

1. Check producer rate versus consumer processing rate.
2. Identify which partitions have high lag.
3. Check whether consumers are making slow or blocking calls to external services.
4. Check the partition count and active instance count.
5. Check for repeated rebalances, processing errors, or prolonged retries.
6. Only add instances when enough partitions exist and downstream systems can handle the load.

Do not put event IDs or order IDs into high-cardinality metric labels. Use logs and traces to look up individual event details; metrics should use bounded-cardinality labels such as group, topic, outcome, and error type.

## 7. Experimenting with creating a new group and re-reading data

Create a new group, such as `inventory-rebuild-v1`, to simulate a new consumer needing to build a read model from event history.

With Kafka, a new group has no committed offsets yet. When configured with `startOffset: earliest`, the consumer can read from the beginning of data still retained on the topic. If older data has already expired or been deleted, the group cannot replay that data from Kafka.

When creating a new group, observe:

- The new group has its own offsets.
- The old group continues at its current read position.
- The new group does not shift the old group to a different offset.
- If you reuse the exact group name of an already-running application, the new consumer joins the existing group and shares read progress instead of creating an independent copy.

Replaying can cause consumers to re-execute side effects. Before rebuilding a read model, decide which operations are safe to re-run, whether to target a separate database/schema or wipe and rebuild data, and whether event handlers are idempotent.

## 8. Comparing semantics across Kafka, RabbitMQ, and Pulsar

The group concept has a common meaning in Spring Cloud Stream, yet binders map it to each broker's native structures.

| Broker | What a group typically maps to | Different groups | Multiple instances in the same group |
|---|---|---|---|
| Kafka | Consumer group ID | Each group has separate offsets and reads the topic independently | Consumers divide partitions |
| RabbitMQ | Queue bound to the exchange/destination | Each group has a separate queue receiving routed copies | Consumers compete on the same queue |
| Pulsar | Subscription name | Each independent subscription reads the topic | Consumers in the same subscription divide messages per subscription type |

### Kafka

Kafka stores events in topics partitioned into partitions. Each consumer group maintains separate offsets per topic-partition. Multiple groups reading the same topic do not share offsets; each group can read all partitions at its own pace.

Within a group, Kafka assigns each partition to at most one consumer member at a time. When members join or leave, Kafka may rebalance and reassign partitions. Rebalances change assignments and can briefly pause processing.

Ordering is guaranteed within a single partition. If events for the same order must stay in sequence, the producer should use order ID as the key so events with the same key land in the same partition. There is no global order across partitions.

### RabbitMQ

The Rabbit binder maps a destination to an exchange and a group to a consuming queue. Different groups have separate queues bound to the exchange, so each queue receives copies of messages according to routing rules. Multiple consumers in the same group read from one queue and compete for messages.

The queue is where each group's backlog is stored. If consumers in the notification group slow down, that group's queue can grow while the inventory group continues processing normally. That is why each group must be monitored individually.

When no group is configured, the binder may create an anonymous/independent queue depending on configuration. For consumers needing durable progress across restarts, declare a stable group and verify queue names, durability, bindings, and dead-letter policies in RabbitMQ.

### Apache Pulsar

Pulsar uses subscriptions to manage topic consumption progress. In the Spring Cloud Stream Pulsar binder, `group` is used to determine the subscription according to binder rules and version. Different subscriptions receive independent event streams; multiple consumers in the same subscription share work according to the subscription type.

Common subscription types:

| Subscription type | Behavior |
|---|---|
| Exclusive | One active consumer on the subscription |
| Failover | One active consumer; other consumers act as standby |
| Shared | Multiple consumers share messages; global ordering is not guaranteed |
| Key_Shared | Multiple consumers split messages by key; same key stays on one consumer per Pulsar semantics |

If business logic requires ordering by order ID, choose the appropriate subscription type and message key, then test with the binder version in use. The property name for configuring subscription type lives in the Pulsar binder's extended consumer properties; do not use Kafka or RabbitMQ properties in its place.

## 9. How to interpret test results on each broker

A proper fan-out test must confirm each group receives events independently. A proper scale-out test must confirm multiple instances in the same group share work.

| Observation | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| New group/subscription | New group offsets | New queue created and bound | New subscription |
| Two instances in same group | Divide partitions | Compete on the same queue | Split messages per subscription type |
| Backlog monitoring | Consumer lag per partition | Ready/unacknowledged counts on queue | Backlog per subscription |
| Membership change | Rebalance | Consumer registration/cancel | Consumer attach/detach and redistribution |
| Replay | Offset reset or new group | Depends on queue durability and remaining messages | Subscription cursor/position |

Do not run Kafka administrative commands against RabbitMQ or Pulsar. Inspect using each broker's native tools: Kafka consumer group commands, RabbitMQ Management UI/CLI, and Pulsar Admin. Exact options and capabilities depend on broker and binder versions.

## 10. Error handling, redelivery, and idempotency

Delivering a message to a group does not imply side effects occur strictly once. For example, a consumer may update the database successfully and then stop before acknowledgment or offset commit completes. The broker may redeliver the message.

Consumers need an event ID or business key to guard against duplicate processing. For side effects in the same database, record the processed event marker in the same transaction as the data change:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(200) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The primary key includes `consumer_name` so the same event can be processed independently by inventory, notification, and analytics. Using a shared deduplication table without distinguishing the consumer could cause inventory's processing to unintentionally skip notification.

High-level processing flow:

~~~text
Receive event
   |
   v
Try inserting (consumer_name, eventId)
   |
   +---- Already exists ----> Do not repeat side effect
   |
   +---- Newly inserted ----> Execute business logic
                                |
                                v
                             Commit
~~~

If side effects occur outside the database, such as calling a payment gateway or sending emails, you need an idempotency key or reconciliation mechanism on the target service. Simply saving the event ID in a local database cannot undo an already-succeeded external request.

Each group has its own retry and DLQ policies per the binder. A failing group should not halt other groups if the broker and configuration isolate backlogs independently. Still, producers, brokers, and consumers may share physical resources, so a broker overload can impact multiple groups.

## 11. Common pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Using different groups for replicas of the same service | Each replica receives the entire stream and may repeat side effects | Use the same group ID across replicas of a single task |
| Sharing a group across two distinct business tasks | Tasks compete for messages; each event reaches only one task | Create a separate group for each task needing all events |
| Changing group ID on deploy without a plan | Creates a new read cursor, potentially replaying or skipping data per offset policy | Keep groups stable or plan migration/replay |
| Adding instances without adding Kafka partitions | Excess consumers have no partitions to process | Evaluate partition count and throughput |
| Assuming all groups process simultaneously or in the same order | Log order and timestamps differ | Design around each broker's semantics |
| Assuming messages are processed strictly once | Redeliveries can repeat side effects | Idempotency and deduplication |
| Using anonymous groups for consumers that need persisted offsets | Consumption progress is not shared stably | Declare explicit groups |
| Using event ID as a metric label | Cardinality explodes | Use logs/traces for detailed identifiers |

## 12. Integrated lab exercise

Work through these steps in order to observe both fan-out and load balancing:

1. Create the `orders.placed` topic with at least four partitions.
2. Run the application with three consumer functions and three distinct groups.
3. Send at least five events with distinct event IDs.
4. Confirm each event ID appears in the logs of all three groups.
5. Start a second instance with the same configuration and the same group IDs.
6. Send ten to twenty more events; confirm the two instances share load within each group.
7. Run `kafka-consumer-groups --describe` to inspect partition assignments and lag.
8. Create a new group with `startOffset: earliest`; observe the new group re-reading retained data.
9. Stop one instance under load; observe the rebalance and how the remaining consumer continues.
10. Simulate a consumer finishing processing before stopping prior to commit; confirm idempotency prevents duplicate side effects.
11. Repeat fan-out on RabbitMQ or Pulsar and compare queue/subscription semantics.

### Completion criteria

Learners complete the lab when they can:

- Explain why different groups all receive events from the same destination.
- Explain why instances in the same group share work.
- Configure multiple consumer functions with a shared destination and separate groups.
- Run two instances with the same group ID without causing unintended duplicate processing.
- Observe offsets, lag, queue backlog, or subscription backlog per group.
- Explain partition limits, rebalances, and message ordering.
- Design idempotency suited for redeliveries and side effects.
- State the differences among Kafka consumer groups, RabbitMQ group queues, and Pulsar subscriptions.

## 13. Official references

- [Spring Cloud Stream — Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) — group semantics and how Spring Cloud Stream maps consumers.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — input binding names derived from function names.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — Kafka binder configuration.
- [Apache Kafka — Consumer groups](https://kafka.apache.org/documentation/#intro_consumers) — group membership, partition assignment, and offsets.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — destinations, exchanges, queues, and groups.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers) — competing consumers and acknowledgments.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — Pulsar binder configuration.
- [Apache Pulsar — Messaging concepts](https://pulsar.apache.org/docs/concepts-messaging/) — subscriptions, consumers, and message distribution.
