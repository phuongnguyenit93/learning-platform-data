# idleEventInterval

In Spring Kafka, a Kafka consumer can be running normally while **receiving no records** for a long period of time. This can be completely valid for a low-traffic topic, or a sign worth investigating when the application expects continuous data. The **`idleEventInterval`** property enables the listener container to publish a **`ListenerContainerIdleEvent`** when no messages have been received within an application-configured duration.

This is an observability mechanism from the **Idle and Non-Responsive** chapter: it helps detect and react to a lack of incoming records, but must be distinguished from cases where a consumer is stuck in `poll()`, intentionally paused, not yet assigned any partitions, or reading a topic that genuinely has no data.

**Key takeaway:** `idleEventInterval` does not automatically retry, control offsets, restart the consumer, or prove that Kafka is experiencing an outage. It only configures **when Spring Kafka publishes an application event notifying that the listener is idle**.

## 1. What does listener container idle mean?

A listener container typically repeats the following loop:

~~~text
consumer.poll()
      |
      +-- Has records --> dispatch to @KafkaListener
      |                     |
      |                     +--> handle success/failure per handler
      |
      +-- No records --> continue polling
                                |
                                +--> idle for configured interval?
                                          |
                                          +-- Yes --> ListenerContainerIdleEvent
~~~

When `idleEventInterval` is configured, Spring Kafka tracks the elapsed time since the most recent record. If `poll()` returns no records and the duration without receiving data reaches the threshold, the container can publish a `ListenerContainerIdleEvent`. While the idle state persists, the event is emitted **repeatedly at the idle interval**, rather than only once.

Example:

~~~text
idleEventInterval = 60,000 ms

12:00:00   Consumer receives last record
12:01:00   No new records -> emits IdleEvent
12:02:00   Still no records -> emits IdleEvent
12:03:00   Still no records -> emits IdleEvent
12:03:20   Receives new record -> no longer idle
~~~

The timeline above is an **approximate illustration**. Actual timing depends on `pollTimeout`, scheduling, when the container checks, and related settings such as `idleBeforeDataMultiplier`. `idleEventInterval` is not a millisecond-exact real-time clock.

Idle means **receiving no records**, not "the business listener has finished all tasks". A listener may still be executing long-running asynchronous work on another thread while the consumer is considered idle at the poll layer.

## 2. Units, defaults, and emission timing

The property is configured in **milliseconds**:

~~~java
containerProperties.setIdleEventInterval(60_000L);
~~~

This sets the base idle observation interval to 60 seconds. In common Spring Kafka versions, `idleEventInterval` defaults to `null`, meaning **idle event emission is disabled** unless configured.

Several parameters need to be distinguished:

| Property | Meaning | Notes |
|---|---|---|
| `idleEventInterval` | Interval between idle events when no messages arrive | Milliseconds, default `null` |
| `idleBeforeDataMultiplier` | Multiplier applied to idle interval before the container receives its first record | Default `5.0` in supported versions |
| `idlePartitionEventInterval` | Tracks idle state **per partition** | Emits a different event type |
| `pollTimeout` | Timeout duration for a single `poll()` call | Can affect idle observation delay |
| `monitorInterval` | Frequency at which the monitor checks for non-responsive consumers | Measured in seconds |
| `noPollThreshold` | Threshold to classify a consumer poll as non-responsive | Multiplier relative to `pollTimeout` |
| `idleBetweenPolls` | Intentional sleep between polls for throttling | Not an idle event interval |

**Do not confuse `idleEventInterval` with `idleBetweenPolls`.** The former only enables event notifications. The latter actively slows down the poll loop and must be accounted for against `max.poll.interval.ms`.

## 3. Configuration for @KafkaListener via container factory

For applications using `@KafkaListener`, you can configure `idleEventInterval` on `ConcurrentKafkaListenerContainerFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaIdleMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

A listener using this factory:

~~~java
@Component
public class OrderConsumer {

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerFactory")
    public void onOrder(OrderEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

In this example, if the consumer receives no new records within the applicable idle interval, Spring Kafka publishes a `ListenerContainerIdleEvent`. The listener does not need to implement its own timer, manually call Kafka `poll()`, or add a sleep inside `onOrder`.

If a factory is reused by multiple `@KafkaListener` methods, all listeners created from that factory may inherit the same idle configuration. This matters when you only want to observe certain topics: either create a separate factory or define appropriate logging/alerting policies per listener.

## 4. Configuration for manually created KafkaMessageListenerContainer

In applications not using `@KafkaListener`, you can configure `ContainerProperties` directly:

~~~java
@Bean
KafkaMessageListenerContainer<String, String> manualListenerContainer(
        ConsumerFactory<String, String> consumerFactory,
        MessageListener<String, String> messageListener) {

    ContainerProperties properties = new ContainerProperties("audit-events");
    properties.setGroupId("audit-processor");
    properties.setMessageListener(messageListener);
    properties.setIdleEventInterval(30_000L);

    return new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );
}
~~~

Here:

- The topic is `audit-events`.
- The consumer group is `audit-processor`.
- The idle interval is set to 30 seconds.
- The event is emitted by this container, not from a separate Kafka topic.

`ListenerContainerIdleEvent` is an **in-process Spring application event**, not a Kafka record automatically sent to a Kafka broker.

## 5. Behavior before the first record arrives

An easily misunderstood detail is `idleBeforeDataMultiplier`. Starting from Spring Kafka 2.8, supported versions include this multiplier, documented with a default of **5.0**. This multiplier is used **before the consumer receives its first record**.

Suppose:

~~~java
factory.getContainerProperties().setIdleEventInterval(60_000L);
factory.getContainerProperties().setIdleBeforeDataMultiplier(5.0);
~~~

Expected milestones:

~~~text
Container starts, no records received yet
    |
    | Initial idle threshold approx:
    | 60 seconds * 5 = 300 seconds
    v
First idle event may appear after ~5 minutes
    |
    v
Container receives first record
    |
    | Then uses base interval of 60 seconds
    v
If no new records, idle events follow ~60-second intervals
~~~

Summary table:

| State | Formula | Duration |
|---|---|---|
| Never received data yet | `idleEventInterval × idleBeforeDataMultiplier` | 60s × 5 = 300s |
| Received at least one record | `idleEventInterval` | 60s |
| `idleEventInterval` disabled | No event emitted solely for idle | — |

Actual timing also depends on poll cadence and version. If a newly started consumer does not emit an idle event after exactly 60 seconds, check **`idleBeforeDataMultiplier` first** rather than immediately concluding the application event listener is broken.

You can adjust the multiplier when business requirements need faster startup alerts. However, setting it too low on a very low-traffic topic can generate meaningless noise.

## 6. Listening to ListenerContainerIdleEvent with @EventListener

A common pattern is registering a Spring event listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEventObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "Kafka consumer idle: listenerId={} idleMs={} partitions={} paused={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions(),
            event.isPaused()
        );
    }
}
~~~

Key methods:

| Method | Information |
|---|---|
| `getListenerId()` | Listener ID or container bean name |
| `getIdleTime()` | Duration the container has received no records, in milliseconds |
| `getTopicPartitions()` | Set of partitions assigned when the event was created |
| `getConsumer()` | Kafka consumer reference when available |
| `isPaused()` | Indicates whether the consumer was paused when the event was published |
| `getSource(Class)` | Direct container that emitted the event |
| `getContainer(Class)` | Corresponding container, which may be the parent when source is a child |

An application receives events from **all containers in the application context** if unfiltered. Therefore, on systems with multiple topics and listener factories, do not treat every idle event as an error on a single listener.

## 7. Filtering events by listener ID

Example monitoring only `orders-consumer`:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {

    MessageListenerContainer parent =
            event.getContainer(MessageListenerContainer.class);

    if (!"orders-consumer".equals(parent.getListenerId())) {
        return;
    }

    log.info(
        "orders-consumer idle for {} milliseconds; assigned={}",
        event.getIdleTime(),
        event.getTopicPartitions()
    );
}
~~~

Note that `source` may be a child container when concurrency is greater than 1, while `container` is the parent. When filtering by ID, comparing the parent's listener ID is usually clearer if targeting the entire logical `@KafkaListener`.

Spring Kafka also supports `@EventListener(condition = "...")` with SpEL. For concurrent containers, child IDs typically carry a suffix per container naming rules. Do not hardcode a child suffix as if it were a stable identity across restarts or rebalances.

If using a SpEL condition, keep the expression simple and verify the exact exposed properties. Avoid assuming all event types share the same `listenerId` semantics without checking the API.

## 8. When records resume: ListenerContainerNoLongerIdleEvent

After a container has emitted `ListenerContainerIdleEvent`, if it receives a new record, Spring Kafka can publish `ListenerContainerNoLongerIdleEvent` (supported since Spring Kafka 2.6.2).

A sequence:

~~~text
12:00:00  Processes last record
12:01:00  ListenerContainerIdleEvent
12:02:00  ListenerContainerIdleEvent
12:02:15  Receives new record
12:02:15  ListenerContainerNoLongerIdleEvent
12:02:15  Listener processes record
~~~

Observer:

~~~java
@Component
public class KafkaIdleTransitionObserver {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "CONSUMER_IDLE listener={} idleMs={} paused={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.isPaused()
        );
    }

    @EventListener
    public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "CONSUMER_ACTIVE_AGAIN listener={} previousIdleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

When designing alerts, treat `ListenerContainerIdleEvent` and `ListenerContainerNoLongerIdleEvent` as **a transition pair**. If every idle event opens a new incident, a consumer idle for 30 minutes could generate dozens of tickets.

The no-longer-idle event proves the consumer received a record again, but does not guarantee that the record was processed and committed successfully by the business listener. Record-processing and offset metrics are still needed to evaluate the data path.

## 9. Container-wide idle vs per-partition idle

A concurrent consumer may receive heavy traffic from partition 0 while **receiving zero records from partition 1**.

~~~text
orders partition 0: 100 records/s
orders partition 1:   0 records/s
orders partition 2:  80 records/s
~~~

If the container continues receiving records from other partitions, it may **not emit a global `ListenerContainerIdleEvent`** even though an individual partition has gone silent.

Spring Kafka provides the configuration:

~~~java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(120_000L);
~~~

This property enables **`ListenerContainerPartitionIdleEvent`** emission for any partition that receives no records within the specified interval. This is a different event type from `ListenerContainerIdleEvent`.

Example observer:

~~~java
@Component
public class PartitionIdleObserver {

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.info(
            "Partition idle: listener={} partition={} idleMs={}",
            event.getListenerId(),
            event.getTopicPartition(),
            event.getIdleTime()
        );
    }
}
~~~

Use global idle to know **the consumer is receiving no records at all**; use partition idle to know **a specific partition has no data**. In systems sharded by tenant or key, tracking partition idle can be useful, provided you understand that a low-traffic partition is completely normal and not necessarily an error.

## 10. Idle events vs NonResponsiveConsumerEvent

This is the most important distinction in the chapter.

**Idle:** `poll()` still returns normally, but there are no records to deliver. The container is able to reach the elapsed-idle-time check and publish the event.

**Non-responsive:** `poll()` is blocked for too long or fails to return control to the container within the expected timeframe. In this case, the container **cannot emit idle events through the normal mechanism** because the consumer thread has not exited `poll()`.

| Characteristic | `ListenerContainerIdleEvent` | `NonResponsiveConsumerEvent` |
|---|---|---|
| Primary condition | No messages received within the configured interval | Consumer `poll()` held beyond monitor threshold |
| Poll loop | Still progressing so idle checks can run | May fail to return on time |
| Configuration | `idleEventInterval` | `pollTimeout`, `monitorInterval`, `noPollThreshold` |
| Interpretation | "No new data" | "Consumer appears unresponsive" |
| Action | Check traffic, assignment, pause, lag/SLO | Investigate poll block, broker/client/network, thread state |
| Means broker down? | No | Does not by itself prove the broker is down either |

Spring Kafka includes a monitor that emits `NonResponsiveConsumerEvent` when `poll()` does not return within the threshold. Per documentation, `noPollThreshold` defaults to about `3.0` times `pollTimeout`, and the monitor checks every `monitorInterval` (default 30 seconds). `noPollThreshold` should be greater than 1.0 to reduce false alarms from race conditions.

Illustrative configuration example:

~~~java
var props = factory.getContainerProperties();

props.setIdleEventInterval(60_000L);
props.setMonitorInterval(30);
props.setNoPollThreshold(3.0f);
~~~

Adjusting monitor thresholds must be based on poll timeout and deployment environment; do not pick arbitrary numbers just to reduce alert volume. When `poll()` is genuinely stuck, raising the threshold delays detection.

## 11. A paused consumer can look idle

When operators call:

~~~java
container.pause();
~~~

The Spring Kafka container typically continues calling `poll()` to maintain consumer group membership, without delivering records from paused partitions. Consequently, the container can satisfy the **no data received** condition and emit idle events.

`ListenerContainerIdleEvent.isPaused()` indicates the pause state at the time of the event.

Example:

~~~java
@EventListener
public void handleIdle(ListenerContainerIdleEvent event) {
    if (event.isPaused()) {
        log.debug(
            "Idle expected while paused: listener={} idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
        return;
    }

    log.warn(
        "Unpaused consumer has no incoming records: listener={} idleMs={}",
        event.getListenerId(),
        event.getIdleTime()
    );
}
~~~

Even when the consumer is not paused, idle can still be normal if the topic has low traffic or the backlog is zero. `isPaused()` only helps rule out one cause; it does not by itself classify an event as an error.

Do not use idle events as a reason to automatically call `resume()` on every paused container; pausing may be due to maintenance, a circuit breaker, or intentional backpressure.

## 12. Idle is not consumer lag

An idle consumer can be in several different states:

| Scenario | Can idle appear? | Consumer lag |
|---|---|---|
| Topic has no new records, consumer is caught up | Yes | Low or 0 |
| Consumer intentionally paused | Possible | Increases if producer keeps sending |
| Consumer has no partition assignment | May lack data | Depends on partitions/group |
| Only one partition has no traffic | Global idle may not fire | Other partitions still advance |
| Consumer is stuck inside poll | Idle event may not fire | May increase |
| Failing record in blocking retry | Depends on error handler/poll flow | May increase |
| Upstream producer unable to send | Yes | Low despite business flow disruption |

**Idle events are not a backlog measurement.** To know whether a consumer is falling behind, inspect committed offsets and log-end offsets per partition or equivalent metrics.

For example, if a topic finishes processing 100,000 records and stops receiving new ones: the consumer will go idle, which is a completely healthy state. Conversely, if a topic has continuous records but the consumer is stuck on a poison record, lag can grow high without emitting the expected idle event.

## 13. No-data conditions and the business heartbeat problem

An order-event service might expect at least one event per minute during peak hours. However, natural traffic fluctuates by hour and day. Relying on `idleEventInterval = 60s` to page an operator whenever no orders arrive is unreasonable.

If the business genuinely requires a continuous signal, design a dedicated **heartbeat event** or monitor upstream producer throughput. In that case:

- The heartbeat should have an appropriate contract and topic.
- Do not confuse a heartbeat with a business transaction.
- A consumer confirming heartbeat receipt does not prove database writes for orders succeeded.
- Consumer groups only read committed records according to transaction/isolation configuration.
- DLT and retry logic should not fabricate synthetic heartbeats to mask an outage.

`idleEventInterval` serves to observe **no incoming messages**, whereas business SLOs require broader signals: producer liveness, pipeline backlog, success rate, and end-to-end latency.

## 14. Impact of pollTimeout on emission timing

`idleEventInterval` is not enforced by an independent millisecond-accurate scheduled timer. The idle check runs when the consumer/container gets a chance to progress through the poll loop and observes no records.

If `pollTimeout` is large or polls are slow, the event may be emitted **later than the configured threshold**. Example:

~~~text
idleEventInterval = 10 seconds
pollTimeout = 5 seconds

Event may be observed after ~10-15 seconds
depending on when poll returns and internal processing time.
~~~

This only illustrates timing precision, not an exact formula. `poll()` can return early when data arrives and is affected by assignment/rebalances and other activity.

Do not use idle events as a scheduler guaranteeing "run task at exactly 12:00:10". If you need exact triggers or custom business timeouts, use a dedicated scheduler or workflow.

## 15. Impact of concurrency

A `ConcurrentMessageListenerContainer` creates multiple child consumers. For example, `concurrency = 3`:

~~~text
orders-consumer
   |
   +-- child consumer 0 -> partitions 0,3
   +-- child consumer 1 -> partitions 1,4
   +-- child consumer 2 -> partitions 2,5
~~~

Each child consumer has its own poll loop and record-delivery schedule. Therefore, one child may be idle while another continuously receives records. When `idleEventInterval` is configured on the factory, events can be emitted from individual child containers.

Operational consequences:

- One logical `@KafkaListener` can emit **multiple idle events** from multiple child consumers.
- Do not count cluster-wide events as the number of times the topic stopped receiving data.
- `event.getSource(...)` is typically the child container that emitted the event.
- `event.getContainer(...)` can be the parent `ConcurrentMessageListenerContainer`.
- Child listener IDs may carry suffixes; normalize them before attaching metrics.
- If concurrency exceeds the number of partitions, some consumers may receive no partition assignment; having no records is not necessarily an issue.

If the goal is to evaluate whether **the entire application service is receiving no data**, aggregate across all relevant consumers/instances rather than relying on a single child's idle event.

## 16. Event source, parent container, and group visibility

`ListenerContainerIdleEvent` carries references:

~~~java
MessageListenerContainer source =
        event.getSource(MessageListenerContainer.class);

MessageListenerContainer parent =
        event.getContainer(MessageListenerContainer.class);
~~~

`source` helps trace the specific consumer; `parent` maps back to the logical listener container. For consumers created via `@KafkaListener`, `event.getListenerId()` returns the container ID at the time of the event.

An application deployed across 5 pods has 5 separate Spring application contexts. Events are published **inside that pod's JVM**; they are not automatically broadcast via Kafka to other pods.

To build a consumer-group-wide dashboard:

1. Have each pod export metrics/logs for its local events.
2. Aggregate in the monitoring system by application, listener ID, group ID, and instance.
3. Trace source child containers and partitions when exact analysis is needed.
4. Do not assume receiving an event on pod A means pod B or the whole group is idle.

## 17. Handling events on the consumer thread

By default, Spring's application event multicaster typically invokes listeners **synchronously on the event-publishing thread**. For `ListenerContainerIdleEvent`, this is usually the consumer thread.

Therefore, event handlers must be **fast and non-blocking**.

Do not do this:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    Thread.sleep(120_000L);
    externalApi.rebuildAllCaches();
}
~~~

This can block the consumer thread, cause poll delays, and disrupt the group lifecycle. It also skews `idleEventInterval`: while the handler is blocking, the consumer cannot continue polling to publish subsequent idle events.

Do this instead:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    log.info(
        "Listener idle: id={} idleMs={} partitions={}",
        event.getListenerId(),
        event.getIdleTime(),
        event.getTopicPartitions()
    );

    metricsRecorder.recordIdle(event.getListenerId());
}
~~~

If you need to send alerts to an external service, use an asynchronous mechanism, bounded queue, or alerting pipeline. Never let an alert-delivery failure break the consumer poll loop.

## 18. Thread safety when switching the event multicaster to async

`ListenerContainerIdleEvent` can hold a reference to the Kafka `Consumer` via `getConsumer()`. Java's `KafkaConsumer` is **not thread-safe**.

If the event listener runs synchronously on the consumer thread, certain operations on the consumer reference may be safe according to framework rules. However, if the application configures Spring's application event multicaster to run on an async executor, the listener can execute on a different thread.

In that case:

- **Do not** call `event.getConsumer().seek(...)`, `pause(...)`, or `resume(...)` from an async handler.
- If lifecycle operations are needed, use `MessageListenerContainer` or registry APIs on an appropriate thread.
- If seeking on idle is required, look at `ConsumerSeekAware.onIdleContainer(...)` in the listener, which Spring Kafka designed for that use case.
- Do not cache the `KafkaConsumer` reference long-term or pass it to an administrative thread.
- Do not manually call `consumer.poll()` from an event listener.

This is a thread-ownership issue, not a question of whether the event type carries a reference.

## 19. Do not call container.stop() directly on the idle-event thread

One use case is "if the consumer is idle for 10 minutes, stop the listener". However, calling `container.stop()` directly on the consumer thread emitting the event can cause delays or unnecessary logs.

Safe approach: **hand off the stop request to a dedicated control thread**, and if the event came from a child container of a concurrent container, stop the **parent container** rather than only the child.

Control service sketch:

~~~java
@Component
public class IdleStopPolicy {

    private final KafkaListenerEndpointRegistry registry;
    private final Executor controlExecutor;

    public IdleStopPolicy(
            KafkaListenerEndpointRegistry registry,
            @Qualifier("kafkaControlExecutor") Executor controlExecutor) {
        this.registry = registry;
        this.controlExecutor = controlExecutor;
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getIdleTime() < 600_000L) {
            return;
        }

        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        if (!"nightly-import-consumer".equals(parent.getListenerId())) {
            return;
        }

        controlExecutor.execute(() -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("nightly-import-consumer");

            if (container != null && container.isRunning()) {
                container.stop();
            }
        });
    }
}
~~~

`kafkaControlExecutor` is an application-configured executor bean with an appropriate thread count and queue; the snippet only illustrates moving the control action off the consumer thread. Before using in production, consider policy, operational permissions, thread pool saturation, and how the container should be restarted.

**Do not automatically stop a production consumer that continuously receives events per SLO just because it experiences a brief idle period.** Stopping the container can trigger partition rebalances; pause has different semantics from stop.

## 20. When to use ConsumerSeekAware.onIdleContainer?

Sometimes an application wants to observe assigned consumer positions or perform an intentional seek when the container goes idle. Spring Kafka provides `ConsumerSeekAware` with the `onIdleContainer(...)` callback for this use case.

Conceptual example:

~~~java
@Component
public class IdleAwareListener implements ConsumerSeekAware {

    @Override
    public void onIdleContainer(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        log.debug("Consumer positions when idle: {}", assignments);
        // If seeking is truly necessary, use the callback under a controlled policy.
    }

    @KafkaListener(topics = "snapshot-events", groupId = "snapshot-reader")
    public void listen(String payload) {
        snapshotService.apply(payload);
    }
}
~~~

The API signature may vary by version and requires proper imports for `ConsumerSeekAware` and nested `ConsumerSeekCallback`. The example illustrates observing **current positions when idle**, and does not recommend automatically seeking to the beginning of the topic whenever no records arrive.

Automatically seeking inside an idle callback can cause massive replays, duplicate DB side effects, or break consumer group progress. If a use case requires replay, clearly define conditions, idempotency, operational authorization, and how many records to re-read.

## 21. When is idle normal?

Several scenarios produce idle events without an incident:

- A `daily-report-trigger` topic only publishes once per day.
- A `fraud-alert` topic has little data when the system is operating smoothly.
- The consumer has caught up and the producer has no new events.
- Staging/test environments have virtually no traffic.
- The consumer is intentionally paused for maintenance or backpressure.
- A listener reads a low-traffic partition within a concurrent group.
- The producer is undergoing a planned shutdown with nothing more to send.

For these topics, use `idleEventInterval` for INFO/DEBUG logging or observational state tracking. Do not attach a SEV1 alert merely because the event was emitted.

If a topic has an SLO like "must have an event every 5 minutes", explicitly document the SLO, operating hours, and expected data source; then combine idle events with producer health and business traffic checks.

## 22. When can idle signal an incident?

Cases requiring investigation:

- The topic has an active producer sending records, yet the consumer receives none while lag climbs.
- The consumer was paused by a control loop and never resumed.
- The consumer just rebalanced and lost its expected partition assignment.
- ACL/authorization or metadata issues prevent the consumer from reading the right topic.
- The listener is misconfigured with the wrong topic name or group ID.
- An upstream producer stopped publishing unexpectedly.
- Downstream processing is failing and the consumer is stuck in retry/backoff; inspect additional signals because idle events may not fire if poll does not return.
- One business-critical partition stops receiving data while other partitions continue.

Idle is a signal to **scope the investigation**, not proof of the root cause.

## 23. Observing idle alongside consumer lag and assignment

A reliable dashboard should include:

| Metric/event | Meaning |
|---|---|
| `ListenerContainerIdleEvent` count | How often the container reported no incoming data |
| `ListenerContainerNoLongerIdleEvent` count | How often the consumer resumed receiving data |
| Last record received timestamp | Time elapsed since the last received record |
| Consumer group lag | Remaining backlog waiting to be processed |
| Partition assignment | Which partitions the consumer currently owns |
| Pause requested/effective state | Is data missing because of a pause? |
| `NonResponsiveConsumerEvent` count | Consumer poll may be blocked |
| Producer send success/error | Is upstream actually publishing records? |
| Error handler retry/DLT | Are there failing or poison records? |
| Record processing success/latency | Is the business handler actually working? |

Use low-cardinality labels: application, listener ID, topic, group, and event type. Avoid creating separate metric series for high-churn values like event ID, offset, or thread ID.

If you want to measure "how long since the last record", `event.getIdleTime()` provides that metadata directly. There is no need to build a millisecond-exact custom timer if the goal is simply alerting on traffic loss.

## 24. Reducing event and alert spam

Because `ListenerContainerIdleEvent` fires repeatedly while a container stays idle, a listener with `idleEventInterval = 5_000L` can produce many logs/events when a topic is legitimately empty.

If 50 child consumers are idle for one minute:

~~~text
interval = 5 seconds
~12 idle events/consumer/minute
50 consumers x 12 = ~600 idle events/minute
~~~

This estimate assumes all consumers have passed the initial threshold and poll/scheduling checks run steadily.

Strategies:

- Choose an interval aligned with each topic's traffic pattern and SLO.
- Log only the transition into idle at WARN; log repeated events at DEBUG or aggregate them.
- Use `ListenerContainerNoLongerIdleEvent` to close incidents.
- Add cooldowns/rate limits for notifications.
- Aggregate by parent listener or group if the business only needs one alert.
- Do not send synchronous HTTP alerts directly on the consumer thread.
- Ignore or separately classify idle periods during maintenance/pause windows.
- Use an "idle state" gauge metric rather than opening a ticket per event.

Do not try to eliminate all idle events because they help investigate outages; the goal is separating telemetry from operational actions.

## 25. Combining with backpressure and pause

A consumer paused due to downstream overload will receive no new records from paused partitions. If `idleEventInterval` is enabled, this condition can emit idle events.

However, an event does not necessarily mean you should resume:

~~~text
Database overloaded
        |
        v
Backpressure monitor requests pause
        |
        v
Container receives no new records
        |
        v
ListenerContainerIdleEvent (paused=true)
        |
        v
Operator must inspect pause reason before deciding to resume
~~~

If an application has multiple pause sources (manual maintenance, circuit breaker, rate limiter), maintain a unified control plane. Never let an independent idle observer call `resume()` on every idle event, as that defeats backpressure and can trigger a retry storm.

## 26. Manual ack, transactions, and idle

`idleEventInterval` does not alter delivery guarantees.

With `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, the application must still acknowledge records after critical side effects complete. The consumer subsequently going idle does not turn an unacknowledged record into "processed".

With a transactional listener container, Kafka outputs and input offsets can be committed inside a Kafka transaction. An idle event only reflects the absence of new records; it neither commits/aborts an in-flight transaction nor opens a new Kafka transaction.

A timeline:

~~~text
Record A received
    |
Business listener updates DB
    |
DB transaction commits
    |
Kafka offset commit may succeed/fail
    |
Consumer receives no new records
    |
Idle event appears when interval elapses
~~~

**Idle does not confirm that record A's DB write is safe or that its Kafka offset committed.** If record A is redelivered after a crash, the consumer still needs database-level idempotency.

## 27. Multi-pod consumer group considerations

Suppose consumer group `order-projection` runs across three pods:

~~~text
pod-A: partitions 0,1  -> continuous traffic
pod-B: partitions 2,3  -> idle
pod-C: partitions 4,5  -> continuous traffic
~~~

`pod-B` may publish idle events while the overall group continues progressing normally. A system-wide alert triggered by a single idle event would be misleading.

To evaluate the entire group:

1. Collect consumer group membership and partition assignments.
2. Compare ingress and lag per partition.
3. Identify which pod and child container emitted the event.
4. Check for hotspots/imbalance caused by producer partition keys.
5. Observe actual processing on the remaining pods.
6. Alert only if the business SLO requires traffic on those specific partitions.

If `concurrency` exceeds the partition count, some child consumers may hold no assignment. Do not expect every child to receive records.

## 28. Testing idle and active transitions

To verify `idleEventInterval` behavior, design an integration test against an appropriate Kafka broker:

1. Create a test topic, a fresh consumer group, and a listener factory with a small `idleEventInterval`.
2. Adjust `idleBeforeDataMultiplier` so the startup threshold fits the test duration.
3. Register an `@EventListener` to capture `ListenerContainerIdleEvent`.
4. Send no records and wait for the event after the threshold.
5. Use `event.getListenerId()` to confirm the expected listener.
6. Send a valid record and verify `ListenerContainerNoLongerIdleEvent`.
7. Verify the listener actually receives and processes the record.
8. Pause the container, observe `isPaused()`, and distinguish pause-induced idle.
9. Create a scenario where one partition is idle while another has traffic to verify `idlePartitionEventInterval`.
10. Stop the listener/container and clean up resources after the test.

Because startup thresholds involve a multiplier and event timing depends on polling, tests should use latches/await with generous timeouts—**never assert that an event appears at an exact millisecond**.

These are suggested test scenarios for learners; no test application execution is performed while authoring this lesson.

## 29. Runbook: no idle events even though the topic is silent

When a consumer is expected to emit `ListenerContainerIdleEvent` but none appear:

1. **Check configuration:** Is `idleEventInterval` `null` or applied to a different factory?
2. **Check listener startup:** Is `container.isRunning()` true?
3. **Check event registration:** Is the `@EventListener` observer registered as a Spring bean?
4. **Check initial multiplier:** Is `idleBeforeDataMultiplier` extending the threshold before the first record?
5. **Check consumer activity:** Are there truly no records? Are heartbeat or business records arriving?
6. **Check polling:** Is `poll()` returning, or are `NonResponsiveConsumerEvent` events appearing?
7. **Check concurrency:** Are events arriving from a child container with a different listener ID than your filter expects?
8. **Check application event multicaster:** Is the event handler throwing an error or filtered out by a condition?
9. **Check poll timeout:** Has the container had an opportunity to evaluate the idle interval?
10. **Check logs/metrics:** Are logging levels, alert suppression, or rate limits hiding the event?

If `poll()` never exits, idle events may never be generated. That is the cue to inspect the non-responsive monitor rather than just increasing the idle interval.

## 30. Runbook: idle events firing while producer sends continuously

This scenario requires evidence-based investigation:

1. Identify listener ID, parent/child container, instance, and assigned partitions.
2. Compare the consumer's topic and group ID against the topic the producer actually writes to.
3. Check Kafka consumer lag by partition.
4. Check whether the consumer is paused via `event.isPaused()` and container state.
5. Inspect group membership and rebalance logs.
6. Verify the producer is sending to the right cluster, namespace, and topic.
7. Check ACL/authentication and deserialization exceptions.
8. If one partition is hot while another is idle, use partition-level metrics/events.
9. Check if a blocking event handler is stalling the poll loop.
10. If offset/seek intervention is needed, use a dedicated audited procedure; never seek automatically from an idle observer.

If the producer sent to Kafka but the consumer hasn't polled it, lag increases. If the producer wrote to the wrong cluster, lag on the observed cluster remains 0 even though upstream "reports sent". Always cross-check bootstrap addresses, topics, and metadata on both sides.

## 31. Runbook: idle events causing alert fatigue

1. Measure event counts per listener/partition alongside traffic patterns.
2. Check initial startup multiplier, concurrency, and pod count.
3. Switch from per-event alerts to **stateful alerts** triggered on transition into idle.
4. Use no-longer-idle events to clear alert state.
5. Suppress idle alerts during permitted maintenance pauses.
6. Increase the interval if aligned with SLOs—never raise it solely to hide outages.
7. Aggregate metrics by listener/group instead of per-child notifications.
8. Check producer health before paging an operator.
9. Configure cooldown/notification windows.
10. Define clear ownership and concrete runbook actions for alert recipients.

If a topic only publishes daily, do not configure a 10-second idle threshold with high severity. Idle is a traffic characteristic, not automatically a fault.

## 32. Common mistakes

### Confusing idle with a non-responsive consumer

Idle means no records are arriving while polling may still be working. Non-responsive means poll is not returning on time. Use the two distinct event types accordingly.

### Treating `idleEventInterval` as a retry timeout

This property does not retry, seek, or route to a DLT. Error handlers and backoffs govern retry/recovery for failing records.

### Ignoring `idleBeforeDataMultiplier`

Before the first record, the event threshold can be several multiples of the base interval. Not seeing an event after one base interval is not necessarily a bug.

### Concluding the whole topic is idle because one child is idle

With concurrency, each child owns different partitions. Aggregate across the group and partitions.

### Stopping the container from the consumer thread

This can cause delays and unnecessary log noise. Hand off to a control thread and stop the parent concurrent container properly.

### Using KafkaConsumer from an async event handler

`KafkaConsumer` is not thread-safe. If the multicaster is configured asynchronously, do not invoke methods on the consumer reference from another thread.

### Performing synchronous alerting I/O inside the callback

A slow HTTP request can stall the consumer thread's poll loop, creating cascading issues.

### Using idle events as the sole readiness signal

Idle can occur when a topic is empty; it does not mean the consumer is broken or the process is not ready.

### Ignoring pause state and lag

Idle while paused can be completely intentional. Combine `isPaused()`, lag, and the backpressure reason.

## 33. idleEventInterval design checklist

- [ ] Enable `idleEventInterval` only when there is a clear observability use case.
- [ ] Choose the interval based on each listener/topic's traffic pattern and SLO.
- [ ] Remember the value is in milliseconds and defaults to `null`.
- [ ] Account for `idleBeforeDataMultiplier` before the first record arrives.
- [ ] Understand that events fire when `poll()` yields no records and may repeat while idle continues.
- [ ] Listen for `ListenerContainerIdleEvent` via `@EventListener` or `ApplicationListener`.
- [ ] Filter parent/child listener IDs appropriately for concurrency.
- [ ] Optionally use `ListenerContainerNoLongerIdleEvent` to confirm records have resumed.
- [ ] When per-partition visibility is needed, use `idlePartitionEventInterval` and its corresponding event.
- [ ] Distinguish idle from `NonResponsiveConsumerEvent`.
- [ ] Never block the consumer thread inside an event handler.
- [ ] Never operate on `KafkaConsumer` from an async event callback.
- [ ] Do not stop a child container on the consumer thread; use a control thread and the parent container.
- [ ] Do not treat idle as offset commit, business success, or readiness.
- [ ] Combine with lag, assignment, paused state, producer throughput, and error/DLT metrics.
- [ ] Use stateful alerting/cooldowns to prevent spam from repeated events.
- [ ] Maintain runbooks for missing events, unexpected idle, and alert overload.

## 34. References

- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka API — ListenerContainerIdleEvent](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerIdleEvent.html)

**Conclusion:** `idleEventInterval` helps Spring Kafka detect and notify when a **listener container receives no new records** for a configured duration. It is valuable for traffic observability, maintenance coordination, and detecting upstream input loss, but it is not proof of consumer failure. When designing operations, factor in the initial multiplier, concurrency, partition-level idle, pause state, and consumer lag; and keep `NonResponsiveConsumerEvent` separate for cases where `poll()` fails to return. Use events to enrich observability and informed decisions, without letting the event handler itself endanger the consumer thread.
