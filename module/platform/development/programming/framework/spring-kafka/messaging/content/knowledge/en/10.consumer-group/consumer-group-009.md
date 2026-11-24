# Separating Groups for Broadcasting

## 1. How Is Broadcasting Understood in Kafka?

In Kafka, a producer writes a record to a topic. Multiple consumer groups can subscribe to that same topic, and each group maintains its own reading progress. Therefore, the same record can be received and processed independently by multiple business groups.

This is how the broadcast pattern (emitting one event so multiple independent subscribers all receive it) is implemented using consumer groups:

- Consumers with the same `group.id` divide partitions among themselves. Members within a group compete to process shared work.
- Consumers with different `group.id` values form independent subscriptions. Each group can read every record in the topic according to its own offsets.
- Producers only need to send an event once to the topic. Kafka retains records according to its retention policy so groups can read at their own pace.

For example, when an `OrderCreated` event arrives on the `orders` topic, the system may need to update an order view, check for fraud, and compute revenue. All three business functions need to receive the event, and they must not split records among themselves because each function has its own work to perform.

~~~mermaid
flowchart TD
    P["Order service<br/>Producer"] --> T["Topic orders"]
    T --> G1["Group: order-projection"]
    T --> G2["Group: fraud-monitor"]
    T --> G3["Group: sales-analytics"]
    G1 --> C1["Consumer instances<br/>Projection"]
    G2 --> C2["Consumer instances<br/>Fraud detection"]
    G3 --> C3["Consumer instances<br/>Analytics"]
~~~

In the diagram, each group can read the same `orders` event stream. Inside each group, multiple consumers still divide partitions to increase parallel processing capacity. Groups do not share offsets with each other.

Broadcasting here refers to independent consumption behavior by groups. Kafka does not create a separate physical copy of each record for each group; records reside in the topic log and groups read that log using their own offsets.

## 2. Why Must Group IDs Be Separated?

Suppose the `orders` topic has four partitions and two services both need to receive every event:

- `order-projection` updates read models for order queries.
- `fraud-monitor` analyzes the risk of each order.

If both services share `group.id=orders-service`, Kafka treats all consumers from both services as members of the same group. Each partition is assigned to at most one consumer in the group at a time. As a result, the projection service might receive some records while the fraud monitor receives others. Neither service receives all events anymore.

If separated into distinct groups:

| Topic | Consumer group | Purpose |
|---|---|---|
| `orders` | `order-projection` | Update order read models |
| `orders` | `fraud-monitor` | Fraud analysis |
| `orders` | `sales-analytics` | Aggregate sales metrics |

Each group has its own offsets for each partition. When `order-projection` has processed through offset 120 of P0, `fraud-monitor` may still be at offset 95 of P0. One slow group does not force another group to wait or lose progress.

Design rules:

- Share the same group ID when instances perform the same task and need to divide load.
- Use separate group IDs when each service or business function needs to receive all events to process independently.
- Keep group IDs stable across deployments so consumers resume from committed offsets.
- Distinguish group IDs across environments if they connect to the same Kafka cluster.

Do not generate a group ID per pod or instance if the goal is to scale a single subscriber horizontally. Every pod with a different group ID becomes an independent subscriber, causing all of them to read the entire stream and potentially duplicate business side effects.

## 3. Configuring Multiple Consumer Groups in Spring Kafka

In Spring Kafka, the `groupId` attribute of `@KafkaListener` lets you specify a separate group for each listener. You can centralize environment-aware group names in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest

app:
  kafka:
    consumer:
      groups:
        order-projection: "order-projection-${spring.profiles.active:local}"
        fraud-monitor: "fraud-monitor-${spring.profiles.active:local}"
        sales-analytics: "sales-analytics-${spring.profiles.active:local}"
~~~

The first listener joins the read-model projection group:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${app.kafka.consumer.groups.order-projection}"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

The second listener joins the fraud-checking group:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class FraudMonitorListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${app.kafka.consumer.groups.fraud-monitor}"
    )
    public void inspect(OrderCreatedEvent event) {
        fraudDetectionService.inspect(event);
    }
}
~~~

Both listeners subscribe to the `orders` topic, but with different group IDs. When a producer sends an `OrderCreatedEvent`, both groups can read and process that event at their own pace.

If an application has multiple listeners, specify `groupId` explicitly for each independent subscription. Do not rely on a shared default group ID if those listeners each need to receive the entire event stream.

### Scaling Each Group Independently

You can run multiple instances of the same listener to share load within that group itself. For example, three instances of the projection service all use `order-projection-prod`; two instances of the fraud monitor both use `fraud-monitor-prod`.

~~~mermaid
flowchart LR
    T["Topic orders<br/>P0 · P1 · P2 · P3"]
    T --> G1["order-projection-prod"]
    T --> G2["fraud-monitor-prod"]
    G1 --> A["Projection A<br/>P0, P1"]
    G1 --> B["Projection B<br/>P2, P3"]
    G2 --> C["Fraud A<br/>P0, P1"]
    G2 --> D["Fraud B<br/>P2, P3"]
~~~

Each group divides partitions within its own membership. The same partition can be read independently by one consumer in `order-projection-prod` and another consumer in `fraud-monitor-prod`. The limit of one consumer per partition applies within each group, not across groups.

## 4. Offsets and Start Position of a New Group

Each group stores its own committed offsets for each partition. Kafka stores group offset metadata in the internal `__consumer_offsets` topic. As a result, one subscriber can pause or process slowly while other subscribers keep running.

When a new group is created or a group has no valid offsets left, `auto.offset.reset` determines the starting position:

| Value | Behavior |
|---|---|
| `earliest` | Reads from the oldest record still retained in the partition |
| `latest` | Starts at the end of the log when initializing read position; typically receives only new records written afterward |
| `none` | Raises an error if no valid offset is found |

If you want a new subscriber to receive retained history in Kafka, configure `earliest` before the group starts reading. If you only want new events emitted after the subscriber is deployed, you can choose `latest`.

`auto.offset.reset` only applies when the group has no valid offset. It does not overwrite the committed progress of an existing group. If an old group comes back after stopping, Kafka resumes from its saved offset if that offset is still valid.

`earliest` also cannot recover records already deleted by retention. Therefore, topic retention must be long enough for slow or temporarily paused subscribers to catch up.

## 5. Does One Slow Group Affect Another Group?

In terms of reading progress, each group operates independently. If `fraud-monitor` processes slowly, its committed offsets and consumer lag grow; `order-projection` can still keep reading and committing at its own speed.

However, groups still share Kafka cluster resources. A large number of groups reading the same topic can increase broker read load, network usage, and I/O. Therefore, broadcasting with multiple groups does not have zero cost.

When designing, consider:

- **Number of subscribers:** each independent business function usually needs its own group; avoid creating groups without clear owners or purpose.
- **Retention:** keep records long enough for slow subscribers to catch up.
- **Throughput:** monitor write rate, read rate, and per-group lag separately.
- **Partition count:** choose enough partitions for the desired parallelism of each critical subscriber.
- **Independence:** processing errors in one group should not stall or alter offsets of another group.

If a subscriber does not need full history, consider `latest` when initializing a new group or a controlled replay procedure. Do not change group IDs arbitrarily to deal with lag, as a new group may start from a different position and trigger reprocessing or skipped history.

## 6. Testing Broadcast Behavior

An integration test should prove two things:

1. Two different consumer groups both receive the same record sent once by a producer.
2. Two consumers within the same group share work rather than each receiving a copy of all records.

For example, with Embedded Kafka or Testcontainers, create two listeners with distinct group IDs and use a counter or test probe to wait for each listener to receive the same `eventId`:

Test events can carry a unique ID to correlate across subscribers:

~~~java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String customerId
) {}
~~~

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BroadcastTestListeners {

    private final BlockingQueue<OrderCreatedEvent> projectionEvents =
        new LinkedBlockingQueue<>();

    private final BlockingQueue<OrderCreatedEvent> fraudEvents =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        topics = "orders",
        groupId = "test-order-projection"
    )
    public void projection(OrderCreatedEvent event) {
        projectionEvents.offer(event);
    }

    @KafkaListener(
        topics = "orders",
        groupId = "test-fraud-monitor"
    )
    public void fraud(OrderCreatedEvent event) {
        fraudEvents.offer(event);
    }

    public BlockingQueue<OrderCreatedEvent> projectionEvents() {
        return projectionEvents;
    }

    public BlockingQueue<OrderCreatedEvent> fraudEvents() {
        return fraudEvents;
    }
}
~~~

In the test, send a record with a unique `eventId` to the topic and wait with a timeout for both queues to receive that event:

~~~java
import java.util.concurrent.TimeUnit;

var event = new OrderCreatedEvent(
    "evt-1001",
    "ORD-1001",
    "CUS-42"
);

kafkaTemplate.send("orders", event.orderId(), event).get(10, TimeUnit.SECONDS);

var projectionEvent =
    broadcastTestListeners.projectionEvents().poll(10, TimeUnit.SECONDS);

var fraudEvent =
    broadcastTestListeners.fraudEvents().poll(10, TimeUnit.SECONDS);

assertThat(projectionEvent).isNotNull();
assertThat(fraudEvent).isNotNull();
assertThat(projectionEvent.eventId()).isEqualTo(event.eventId());
assertThat(fraudEvent.eventId()).isEqualTo(event.eventId());
~~~

This example only illustrates observing two independent subscribers; real tests must ensure listeners are initialized, topics are ready, and test groups have no unexpected prior offsets. Use dedicated topics or group IDs per test to prevent cross-run interference.

## 7. Monitoring Each Consumer Group

When operating broadcast consumption, inspect each group individually. The Kafka CLI lets you check committed offsets, log end offsets, lag, and partition assignments:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection-prod
~~~

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group fraud-monitor-prod
~~~

Compare both outputs to see which subscriber is falling behind or lacks active consumers. The lag of `fraud-monitor-prod` is unrelated to the offsets of `order-projection-prod`; each group has its own progress.

Metrics to monitor:

- Consumer lag per group and partition.
- Active consumer count and assigned partition count.
- Record processing rate and average processing duration.
- Rebalance counts and listener errors.
- Time from when a record is written until each subscriber finishes processing it.

## 8. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Services needing broadcast share one `group.id` | Services split records among themselves; each misses events | Use separate group IDs per business function |
| Each replica uses a different group ID | Every replica reads the entire topic, causing unintended duplicate processing | Replicas of the same subscriber share one group ID |
| Changing group ID frequently across deployments | New groups may replay history or start at log end | Keep group IDs stable and only change when a new subscription is needed |
| New group uses `latest` when history is required | Older records still in the topic may be missed | Choose `earliest` when retained data must be replayed |
| Retention is shorter than subscriber downtime | Subscribers cannot catch up on expired records | Size retention for maximum recovery duration |
| Not monitoring per-group lag separately | One subscriber can fall far behind undetected | Build dashboards and alerts per group ID |

## 9. Broadcast Design Checklist

- [ ] Each business function that needs all events has its own group ID.
- [ ] Replicas of the same business function share a group ID.
- [ ] Group IDs are stable and distinguish environments.
- [ ] `earliest` vs. `latest` is explicitly chosen for groups without offsets.
- [ ] Retention is long enough for slow or paused subscribers.
- [ ] Broker load is evaluated when multiple groups read the same topic.
- [ ] Tests verify a single record is received independently by multiple groups.
- [ ] Offsets and consumer lag are tracked separately per group.
- [ ] Listeners are designed to be idempotent to tolerate record redelivery.

Separating group IDs is a straightforward way to implement broadcasting in Kafka: producers write an event once to a topic, each business function has its own consumer group to read independently, and replicas within a function divide partitions for parallel processing. Mastering this boundary helps Spring Kafka systems scale subscribers without accidentally splitting events across business functions that require complete data.
