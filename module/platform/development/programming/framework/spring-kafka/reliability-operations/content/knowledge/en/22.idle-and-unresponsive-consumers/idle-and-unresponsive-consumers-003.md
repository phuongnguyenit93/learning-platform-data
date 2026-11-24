# idleBeforeDataMultiplier

In Spring Kafka, a listener container can start successfully without receiving any records yet. This can be completely normal: a newly created topic, a producer that has not started publishing events yet, a first-time deployment, or a partition that currently has no data. If an application immediately fires a "consumer idle" alert using the same threshold meant for steady-state operation, operations teams can easily get flooded with unnecessary alerts.

Spring Kafka's **`idleBeforeDataMultiplier`** property addresses this exact scenario. It is a **multiplier applied to `idleEventInterval` during the phase before the listener container receives its first data**. Once data has been received, idle event emission uses the regular idle threshold. This is a small detail, yet very important when monitoring Kafka consumers during startup, scale-out, and new topic rollouts.

This lesson examines the nature of the property, how to configure it, its relationship with `ListenerContainerIdleEvent`, how to distinguish an idle consumer from a non-responsive consumer, the impact of concurrency and pause, how to design alerts, and how to test to reduce false positives without missing real incidents.

## 1. Why does idleBeforeDataMultiplier exist?

Suppose an order-processing service is configured to emit an idle event after **10 seconds without receiving records**. In an active production environment, 10 seconds with no data can be worth attention if the system normally receives hundreds of events per second.

However, when starting a new consumer, the following can happen before the first message arrives:

- The producer is deploying or has not started emitting events.
- The topic has no existing backlog.
- The consumer group was just created and starts at the end of the log.
- The Kafka consumer is completing subscription and partition assignment.
- Business flows only emit events when users perform actions.
- A scaled-out instance is assigned partitions that currently have no traffic.

In such cases, treating a lack of messages **right from startup** as equivalent to "running steadily and suddenly going silent" is unreasonable.

`idleBeforeDataMultiplier` provides a **longer initial grace window** without loosening the idle threshold for the consumer's entire lifecycle.

~~~text
Consumer startup
       |
       | Never received a record yet
       | Initial idle threshold:
       | idleEventInterval × idleBeforeDataMultiplier
       v
First record received
       |
       | From here, uses normal
       | idleEventInterval
       v
Consumer continues processing
~~~

**Key point:** This multiplier does not make the consumer wait before polling and does not delay the first record. It adjusts **when idle events appear**, i.e., the observation signal when no data has been received yet.

## 2. Relationship between idleEventInterval and idleBeforeDataMultiplier

The two properties serve distinct roles.

| Property | Role | Example |
|---|---|---|
| `idleEventInterval` | Duration without receiving records before emitting an idle event | 10,000 ms |
| `idleBeforeDataMultiplier` | Multiplier for the idle threshold before any record has been received | 3.0 |
| `idlePartitionEventInterval` | Version-dependent, detects idle per individual partition | Separate per-partition threshold, distinct from container-wide idle |

A practical mental model:

~~~text
Threshold before first data arrives
  ≈ idleEventInterval × idleBeforeDataMultiplier

Threshold after data has arrived
  ≈ idleEventInterval
~~~

The "≈" reminds us that idle events are signals driven by consumer/container activity and the poll cycle, not real-time timers guaranteeing millisecond-exact emission.

### 2.1. Numerical example

Suppose:

- `idleEventInterval = 10_000L`, which equals 10 seconds.
- `idleBeforeDataMultiplier = 3.0`.

When a newly started container has **never received a record**, the threshold before emitting an idle event is approximately 30 seconds. After a record arrives, subsequent periods without records are evaluated against the normal 10-second threshold.

| Phase | Has received a record yet? | Corresponding idle threshold |
|---|---|---|
| After startup, topic has no messages | No | About 30 seconds |
| Consumer receives first record | Yes | Reset upon data receipt |
| Topic subsequently goes silent | Yes | About 10 seconds |
| Another idle period later | Yes | About 10 seconds |

This is not a mechanism that triples every idle interval; the multiplier only applies during the **before data** phase.

### 2.2. Timeline

~~~text
Time:            0s     10s     20s     30s     40s     50s
                |-------|-------|-------|-------|-------|

Consumer starts ^
First record has not arrived yet
Pre-data threshold = 30s
                                       |
                                       v
                             Idle event may appear

Record then arrives around 42s
                                                  ^
                                                  |
                                        From here, idle interval = 10s
~~~

If the first record arrives before the initial threshold, the pre-data idle condition may never trigger; subsequent idle monitoring uses the regular threshold.

### 2.3. Can the multiplier be less than 1?

The primary purpose is to **extend the time before the first idle event**, so a factor greater than 1 is typically chosen. Do not arbitrarily set 0, negative numbers, or extreme values. Validation behavior, valid ranges, and default values must be verified against the running Spring Kafka version.

Some Spring Kafka versions default this multiplier to **5.0**. However, when designing strict alerts, check the actual default in `ContainerProperties` for your exact dependency rather than assuming a figure from another version's documentation.

## 3. idleEventInterval must be enabled first

`idleBeforeDataMultiplier` **does not enable idle event emission on its own**. It only scales the threshold when the idle event feature is already configured.

In Spring Kafka, `idleEventInterval` is typically unset/disabled by default; to receive `ListenerContainerIdleEvent`, you must configure an appropriate interval.

Example:

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(10_000L);

factory.getContainerProperties()
        .setIdleBeforeDataMultiplier(3.0);
~~~

If you only configure:

~~~java
factory.getContainerProperties()
        .setIdleBeforeDataMultiplier(3.0);
~~~

without configuring the idle event interval, the application should not expect idle events to appear just because the multiplier has a value.

### 3.1. Impact on the consumer

`idleBeforeDataMultiplier` does not directly alter:

- Kafka topic subscription.
- Partition assignment.
- Poll timeout.
- Group heartbeat.
- Offset commits.
- `DefaultErrorHandler` retry/backoff.
- How `@KafkaListener` converts payloads.
- Batch size or records returned per poll.

It belongs to **container observability/lifecycle event timing**, not rate limiting or broker configuration.

## 4. Java configuration on ConcurrentKafkaListenerContainerFactory

Suppose an application consumes order events from `orders.events` and needs alerts when a running consumer suddenly receives no data.

~~~java
@Configuration
public class OrdersKafkaConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setIdleEventInterval(10_000L);

        factory.getContainerProperties()
                .setIdleBeforeDataMultiplier(3.0);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-processing",
            containerFactory = "ordersListenerFactory")
    public void consume(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

This example assumes `OrderEvent`, `OrderService`, and `ConsumerFactory` are properly declared in the application. Specific `ContainerProperties` APIs must match your Spring Kafka version.

### 4.1. The listener factory must be the one actually in use

An application may have multiple `ConcurrentKafkaListenerContainerFactory` beans. If you enable the multiplier on factory A while `@KafkaListener` points to factory B, the change will not affect the target listener.

When investigating missing idle events or events firing too early, verify:

1. Listener ID.
2. `containerFactory` value on the annotation.
3. `ContainerProperties` of the running container.
4. Actual `idleEventInterval` and multiplier settings.
5. Container startup lifecycle.

Never conclude a feature is broken simply because a configuration bean exists.

### 4.2. Configuration when creating containers directly

If creating a Kafka listener container in Java without `@KafkaListener`:

~~~java
ContainerProperties properties =
        new ContainerProperties("orders.events");

properties.setGroupId("orders-processing");
properties.setIdleEventInterval(10_000L);
properties.setIdleBeforeDataMultiplier(3.0);

var container =
        new KafkaMessageListenerContainer<>(
                consumerFactory, properties);
~~~

This snippet only shows where to set the properties; attach a listener, configure error handling, and start the container properly per lifecycle before using in a real system.

## 5. Listening to ListenerContainerIdleEvent

Once `idleEventInterval` is configured, Spring Kafka can publish `ListenerContainerIdleEvent` when the listener receives no records within the applicable interval.

Example application event listener:

~~~java
@Component
public class KafkaIdleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleTimeMs={}, " +
                "partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions());
    }
}
~~~

`getIdleTime()` lets you observe how long the container considers itself idle when the event is emitted. `getListenerId()` and `getTopicPartitions()` provide container/partition context per your version's API.

**Do not interpret `event.getIdleTime()` as exact milliseconds since JVM startup** in all cases. It reflects idle duration as tracked by the container's record-receipt logic; polling, rebalances, pauses, and record arrival timing affect the value.

### 5.1. An idle event does not mean the consumer is dead

A Kafka consumer can continuously call `poll()`, maintain group membership, and exchange valid metadata and heartbeats while **having zero records to process**. In that case, the listener is idle while the consumer is completely healthy.

Therefore:

- An idle event is a **lack-of-data signal**.
- A non-responsive consumer is a **liveness/poll issue**.
- A stopped container is a **lifecycle state**.
- An unavailable broker is a **connectivity/infrastructure issue**.

They may be related, but they are not identical.

### 5.2. Do not turn every idle event into a page

If a topic has naturally sparse data, the container can emit many normal idle events. A callback sending an email or page per event quickly causes alert fatigue.

Use events to update metrics or state, then alert according to policy: expected data latency, upstream activity, consumer lag, partition assignment, and business criticality.

## 6. ListenerContainerNoLongerIdleEvent

When a container that was previously marked idle receives a record again, Spring Kafka can publish `ListenerContainerNoLongerIdleEvent`. This event is useful for closing a "no data" incident or measuring how long the pipeline went without records.

~~~java
@Component
public class KafkaIdleLifecycleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleLifecycleEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
                "Idle: listener={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime());
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {
        log.info(
                "Data resumed after idle: listener={}",
                event.getListenerId());
    }
}
~~~

Depending on version and how the container publishes events, specific metadata fields may differ. The example uses common event API methods; add corresponding imports in real source code.

### 6.1. Using it for incident lifecycle

~~~text
Container receives data steadily
          |
          v
No records received for threshold duration
          |
          v
ListenerContainerIdleEvent
          |
          v
Incident opened at warning level
          |
          v
New record received
          |
          v
ListenerContainerNoLongerIdleEvent
          |
          v
Incident evaluated for closure
~~~

If the container never previously emitted an idle event, do not assume a "no longer idle" event will always fire for the first record. Incident-tracking logic should handle cases where no incident is currently open.

## 7. Distinguishing three critical phases

To understand the multiplier, divide the consumer lifecycle into phases:

### 7.1. Phase A — container just started, never received a record

This is the phase `idleBeforeDataMultiplier` targets. The idle threshold is stretched relative to `idleEventInterval` to reduce startup false positives.

### 7.2. Phase B — container receives its first record

Once a record arrives, the consumer exits the "before data" state and has a record-receipt history. Subsequent idle checks use the regular `idleEventInterval`.

### 7.3. Phase C — ran with data, then went silent later

This operational situation differs from Phase A. If a steady-traffic system suddenly receives no records, early detection using the normal idle interval has high diagnostic value.

| Phase | Does the multiplier apply? | Operational signal |
|---|---|---|
| Newly started, no records yet | Yes | Could be normal startup or missing upstream |
| Received first data | Switches to regular idle threshold | Confirms data flow has started |
| Silent after running for a while | No longer a startup grace reason | Check producer/upstream, lag, assignment, and errors |

Setting a very large multiplier can delay detecting an incident **right after service deployment**, though you should not expect it to keep delaying alerts once the system has already received records.

## 8. idleBeforeDataMultiplier vs idleBetweenPolls

Two similar names with very different semantics:

| Property | Effect |
|---|---|
| `idleBeforeDataMultiplier` | Multiplier for the idle event threshold before the first data arrives |
| `idleEventInterval` | Duration without receiving records to publish an idle event |
| `idleBetweenPolls` | Makes the container sleep between polls per configuration, affecting poll cadence |
| `pollTimeout` | Maximum time a single poll call may wait |

`idleBeforeDataMultiplier` does not make `KafkaConsumer.poll()` wait N times longer and is not a throttling mechanism. If you need backpressure, evaluate pause/resume, concurrency, bounded queues, or rate limiting depending on your problem.

### 8.1. Example of a common misconception

If your goal is "read Kafka slower so the database isn't overloaded", setting:

~~~java
properties.setIdleBeforeDataMultiplier(100.0);
~~~

will **not** solve the throughput issue. It only alters idle observation before any data arrives; once the topic has records, the consumer still processes them per existing configuration.

If your goal is "don't alert idle during the first minute of deployment", the multiplier may be appropriate.

## 9. idleBeforeDataMultiplier and NonResponsiveConsumerEvent

Spring Kafka also provides `NonResponsiveConsumerEvent` for cases where a consumer **fails to complete a poll or fails to poll within the monitor threshold**.

Two events compared:

| Aspect | `ListenerContainerIdleEvent` | `NonResponsiveConsumerEvent` |
|---|---|---|
| Question | Have records been received recently? | Is the consumer polling / making poll progress? |
| Can the consumer be healthy? | Yes, an empty topic still causes idle | Needs investigation because poll may be blocked |
| Related to `idleBeforeDataMultiplier`? | Yes, before first data | Not the multiplier's purpose |
| Investigation focus | Producer, subscription, assignment, traffic | Thread dump, poll blocking, deadlock, network/lifecycle |
| Specific failing record? | Not necessarily | Not necessarily |

A completely empty topic can make a listener idle even while `KafkaConsumer` polls steadily. Conversely, a consumer stuck inside a poll call or in processing that never returns to poll may trigger non-responsive investigation even right after receiving a record.

### 9.1. Do not use the multiplier to "fix" non-responsive consumers

If an application has a stuck poll, raising `idleBeforeDataMultiplier` may delay idle alerts, but **does not fix why the consumer stopped polling**.

You must inspect the non-responsive monitor, listener processing duration, `max.poll.interval.ms`, CPU/GC, and thread dumps.

## 10. How do idle and topic data arrival relate?

A listener may receive no records for many reasons:

1. The producer genuinely has not published data yet.
2. The consumer group is at the end of the log and no new records exist.
3. The listener subscribed to the wrong topic or pattern.
4. The topic has records, but in partitions not assigned to that consumer.
5. The consumer container is paused.
6. Consumer group membership is rebalancing.
7. The deserializer/converter fails before the listener receives the object.
8. The consumer has authorization or network errors.
9. A record is being retried, delaying subsequent records.

`idleBeforeDataMultiplier` does not classify causes. It only scales event emission timing for the "never received data" state. Pinpointing faults requires combining logs, assignments, consumer lag, producer throughput, and error events.

### 10.1. Traffic on a topic does not mean every listener instance receives records

Within a consumer group, partitions are distributed across consumers. If total consumers exceed partition count, some consumers may get no assignment or have no data on their assigned partitions.

Thus, "one pod hasn't received a message in 30 seconds" is not necessarily abnormal even when the overall topic has traffic.

## 11. Concurrent containers and multiplier scope

With `ConcurrentMessageListenerContainer`, one listener ID can create multiple child consumers according to `concurrency`.

~~~text
@KafkaListener(id="ordersListener")
                 |
                 v
ConcurrentMessageListenerContainer
      |              |              |
      v              v              v
  consumer-0      consumer-1      consumer-2
  partition 0     partition 1     partition 2
      |              |              |
   Has data       No data yet     Has data
~~~

When observing idle events:

- One child consumer may not have received any records yet even though other children have.
- Startup/assignment times for each child consumer may differ.
- Never assume an event from one child equals the entire group/topic being inactive.
- Inspect the listener/container ID and partitions attached to the event.

### 11.1. Avoiding false alarms at high concurrency

For example, a topic has 6 partitions, each pod has concurrency 3, and there are 2 pods total. If just one partition has sparse data, the consumer managing that partition can stay idle for a long time.

A service-wide "pipeline down" alert based solely on one consumer's idle event will be inaccurate. Instead:

1. Identify partition assignments.
2. Compare input traffic per partition.
3. Check partition-specific lag.
4. Distinguish no-data-in-topic from paused/stuck consumers.
5. Escalate severity only if business SLOs are impacted.

### 11.2. A multiplier does not replace per-partition thresholds

If your goal is detecting "partition 2 receives no records while partition 1 stays active", look at per-partition idle mechanisms (`idlePartitionEventInterval` and corresponding events in supported versions).

`idleBeforeDataMultiplier` tunes **the container's initial idle event threshold**, without providing per-partition traffic anomaly detection on its own.

## 12. When should you set a large multiplier?

A larger multiplier can help when:

- New topics exist where producers deploy after consumers.
- Test/staging environments have minimal traffic.
- Pipelines only run on intermittent scheduled events.
- Multiple services start in sequence and need a grace period.
- A consumer group scales out and some partitions have no traffic yet.
- During deployments, you want to avoid paging for "no records in the first few seconds".

However, an overly large multiplier has drawbacks:

- Detecting a misconfigured subscription at startup takes longer.
- A producer expected to emit right after startup that fails may not trigger early alerts.
- Operations teams may mistakenly view prolonged silence as normal.
- When the initial wait exceeds the SLO, event signals may arrive too late.

Choose the multiplier based on **actual startup time, expected data cadence, and SLOs**, not by picking a large number simply to suppress alerts.

## 13. Formula for choosing a multiplier from a time budget

Suppose:

- After startup, you tolerate up to 90 seconds before the first record arrives.
- Once the pipeline is active, you want to detect silences of around 15 seconds.

You can choose:

~~~text
idleEventInterval = 15 seconds
idleBeforeDataMultiplier = 90 / 15 = 6.0

Initial threshold ≈ 90 seconds
Normal threshold ≈ 15 seconds
~~~

Illustrative examples:

| Idle interval | Multiplier | Corresponding pre-data threshold |
|---|---:|---:|
| 5 seconds | 2.0 | 10 seconds |
| 10 seconds | 3.0 | 30 seconds |
| 15 seconds | 6.0 | 90 seconds |
| 60 seconds | 2.0 | 120 seconds |

These values only illustrate the multiplication, not universal recommended thresholds. Actual event timing can be later due to polling and lifecycle behavior.

### 13.1. Choosing by topic type

| Workload type | How to think about thresholds |
|---|---|
| Continuous event streaming | Short normal idle; moderate startup grace |
| Scheduled job every 5 minutes | Idle events should not treat 30 seconds of silence as an incident |
| Transaction topic driven by user actions | Long idle periods may be acceptable; supplement with upstream business SLOs |
| DLT/quarantine | Idle is usually the desired state; never page for lack of data |
| Topics in integration tests | Grace period avoids test idle alerts before producer setup completes |

For DLTs, "no new records" is usually a good sign, so alerting policies should focus on records **entering** the DLT rather than idle state.

## 14. Service startup does not equal data arrival

A listener container can be in the `running` lifecycle state while:

- Partition assignment has not finished.
- No new traffic exists.
- Assigned partitions are empty.
- Paused by policy.
- Suffering consumer runtime errors.

Therefore, "no records seen after startup" is not proof that `@KafkaListener` is broken.

When debugging:

1. Check whether the container started and is running.
2. Check consumer group subscription and assignment.
3. Check the Kafka topic and upstream producer.
4. Check committed offsets and end offsets.
5. Check per-partition traffic.
6. Check whether the consumer is paused.
7. Check pre-listener exceptions like deserialization or authorization.

The multiplier only tunes **when** you receive an idle notification; it never explains **why** data has not arrived.

## 15. Impact of consumer pause

Spring Kafka supports `container.pause()` and `container.resume()` to stop delivering records when downstream is overloaded. When paused, the consumer may continue polling to preserve group membership, without delivering new records to the listener.

If the listener receives no records while paused, idle signals may fire depending on calculation rules and container state in your version. Some event APIs expose `isPaused()` to report pause status.

### 15.1. Do not page on planned pauses

A sensible runbook:

- If the container is paused for scheduled maintenance, treat idle as expected.
- If paused due to queue overload, alert on **backpressure duration**, queue depth, or downstream failure—not idle duration alone.
- If not paused while the topic has input traffic and the consumer gets no records, investigate further.

`idleBeforeDataMultiplier` is not an "ignore idle when paused" feature. To avoid false alerts, combine container pause state and pause reason from your management layer.

### 15.2. Resume does not reset business data

`resume()` does not commit offsets, seek to the beginning of the topic, or make old records vanish. After resuming, the listener continues delivery based on consumer/offset state and the error handler.

Do not use idle events as a trigger to automatically resume every container; if paused because downstream is degraded, auto-resuming can cause a retry storm.

## 16. Batch listeners and record listeners

Spring Kafka supports both record listeners and batch listeners. In both cases, idle events refer to **intervals without receiving data**, not "total business objects processed successfully".

### 16.1. Record listener

~~~java
@KafkaListener(
        id = "ordersRecordListener",
        topics = "orders.events")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

With a record listener, one poll can fetch multiple records and the adapter invokes the method multiple times. Idle events do not have a 1:1 relationship with individual method invocations.

### 16.2. Batch listener

~~~java
@KafkaListener(
        id = "ordersBatchListener",
        topics = "orders.events",
        containerFactory = "ordersBatchFactory")
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

With a batch listener, a single method invocation can carry many records. Do not equate "one method call" with "one record" when observing idle. If batch processing is very slow, the consumer can hit poll-interval issues even right after receiving data.

### 16.3. Processing errors vs lack of data

A listener receiving records and repeatedly throwing exceptions does not mean the container is idle in the sense of "receiving no records". Track exception, retry, DLT, and consumer lag metrics alongside idle events.

## 17. Non-responsive consumers cannot be fixed with a multiplier

A consumer unable to poll for an extended time may be suffering from:

- Infinite blocking in listener code.
- Thread deadlocks.
- Hanging database queries without timeouts.
- Slow HTTP clients.
- CPU/GC pressure.
- Network or Kafka client failures.
- Misconfigured error handler/backoff.

In these cases:

1. Check `NonResponsiveConsumerEvent` or poll-monitoring signals.
2. Capture a thread dump.
3. Identify what the consumer thread is doing.
4. Check `max.poll.interval.ms` and group rebalances.
5. Check I/O timeouts and circuit breakers.
6. Recover the dependency or fix the code.

Raising `idleBeforeDataMultiplier` only shifts when the first pre-data idle alert fires; it does not make the consumer poll or escape a deadlock.

## 18. Application events may run on the container thread

Spring application events are dispatched synchronously unless an asynchronous multicaster is configured. Therefore, an `@EventListener` handling idle events may execute on the thread the container uses when publishing the event.

An event listener should:

- Write brief logs.
- Update lightweight counters/gauges.
- Store thread-safe state.
- Forward notifications to a controlled async pipeline.

It should not:

- Sleep for seconds.
- Perform database or HTTP calls without timeouts.
- Call `KafkaConsumer.seek(...)` or `pause(...)` directly from the event callback without respecting consumer thread ownership.
- Repeatedly trigger container restarts/stops.
- Log full payloads or sensitive Kafka headers.

### 18.1. Lightweight callback example

~~~java
@Component
public class OrdersIdleMonitor {

    private final AtomicLong lastIdleEventMs =
            new AtomicLong(-1L);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().contains("ordersListener")) {
            return;
        }

        lastIdleEventMs.set(System.currentTimeMillis());
    }

    public long lastIdleEventMs() {
        return lastIdleEventMs.get();
    }
}
~~~

This illustrates tracking local state rather than a complete health check. Depending on listener ID naming and concurrency, `getListenerId()` may carry suffixes or specific naming patterns, so avoid relying on loose substring matching for ownership in production.

## 19. Alerting: an idle event is a signal, not a conclusion

An alerting policy should combine at least:

1. Whether the topic is expected to have traffic.
2. Whether the upstream producer is emitting records.
3. Whether the consumer group has appropriate assignments.
4. Consumer lag and age of unprocessed records.
5. Whether the container is running or paused.
6. Whether the consumer polls and heartbeats normally.
7. Whether this is startup phase or steady state.
8. Whether a maintenance window or intentional throttle is active.

Examples:

| Scenario | Idle event | Appropriate alert |
|---|---|---|
| New topic and producer has not started on schedule | Possible | Low-priority notice or no alert |
| High-traffic transactional topic, consumer gets no records | Possible | Investigate immediately, especially if lag grows |
| Consumer paused for maintenance | Possible | Track maintenance duration |
| Consumer has no partition assignment | Possible | Investigate group/assignment before reporting data loss |
| DLT has no messages | Possible | Normally healthy |
| Consumer is not polling | Idle event not guaranteed | Alert via non-responsive/poll metrics |

### 19.1. Avoid counting repeated idle events as separate incidents

If a container stays idle, it can keep publishing idle events per configuration. An incident management system must not open a new ticket for every event.

Use a stable identity, such as application + listener/container ID + instance, and maintain:

- Open/closed incident state.
- Timestamp when idle began.
- SLO-based severity.
- Cooldown or deduplication window.
- Automatic closure evaluation when data returns.

## 20. Metrics for observing idleBeforeDataMultiplier

Not all metrics below are emitted by Spring Kafka by default; many require custom instrumentation.

| Metric | Purpose |
|---|---|
| Idle event count/rate | Detect how often the listener enters idle |
| Time to first record | Measure elapsed time from container ready to first record |
| Idle duration distribution | Understand normal quiet periods for the workload |
| Consumer records consumed rate | Confirm records are being received |
| Consumer lag by partition | See whether backlog is growing or shrinking |
| Last successful processing timestamp | Measure business progress |
| Producer send rate | Verify whether upstream input exists |
| Container running/paused state | Identify lifecycle status |
| Poll duration/non-responsive count | Detect stuck consumers |
| Partition assignment count | Distinguish lack of traffic from lack of assignment |

### 20.1. Time to first record vs idle duration

`idleBeforeDataMultiplier` affects **the idle-event threshold before any records arrive**. However, measuring that a consumer received its first record after 50 seconds is a separate metric. To understand startup behavior, instrument a first-record timestamp or corresponding event; do not infer exact first-record timing solely from idle event counts.

### 20.2. Metric tags

Tags should remain bounded:

- Application/service.
- Environment.
- Listener ID.
- Topic (from a controlled set).
- Instance if bounded.

Avoid using Kafka offsets, event IDs, record keys, exception messages, or long raw partition assignment lists as metric tags that cause high cardinality. Record-level details belong in structured logs or traces.

## 21. Example recording idle via Micrometer

~~~java
@Component
public class KafkaIdleMetrics {

    private final Counter idleEvents;
    private final Counter noLongerIdleEvents;

    public KafkaIdleMetrics(MeterRegistry meterRegistry) {
        idleEvents = Counter.builder(
                "app.kafka.listener.idle.events")
                .description("Listener idle application events")
                .register(meterRegistry);

        noLongerIdleEvents = Counter.builder(
                "app.kafka.listener.no_longer_idle.events")
                .description("Listener resumed receiving records")
                .register(meterRegistry);
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        idleEvents.increment();
    }

    @EventListener
    public void onDataBack(
            ListenerContainerNoLongerIdleEvent event) {
        noLongerIdleEvents.increment();
    }
}
~~~

This is an instrumentation example. `MeterRegistry` and `Counter` belong to Micrometer; the project needs the corresponding dependencies and imports. If there are multiple listeners, choose a stable tag set for grouping rather than creating new meters per message.

### 21.1. Cardinality considerations with concurrent containers

In systems with many pods and child consumers, metric series counts can explode if tags include dynamic client IDs, pod UIDs, and partition lists. Establish a stable taxonomy and add granularity only when needed for debugging.

## 22. Testing the multiplier with integration tests

The test objective is proving that **the initial threshold** is longer than the normal threshold before data arrives, and after data arrives, idle events use the normal threshold.

You can use an embedded Kafka broker or Testcontainers. Because event publishing is tied to the poll cycle, use generous test timeouts rather than asserting millisecond-exact timing.

### 22.1. Scenario with no records yet

1. Create an empty test topic with no backlog for a new group.
2. Configure `idleEventInterval = 1_000L`.
3. Configure `idleBeforeDataMultiplier = 3.0`.
4. Start the listener container.
5. Collect `ListenerContainerIdleEvent` using a thread-safe event collector.
6. Verify no event is expected at the normal 1-second threshold per configured policy.
7. Verify an idle event arrives after the appropriate initial wait, allowing tolerance for polling/scheduling.

Do not use durations too small relative to startup and `pollTimeout`, or tests will be flaky.

### 22.2. Scenario where the first record arrives early

1. Start the container on a new topic.
2. Send a record before the initial threshold elapses.
3. Verify the listener receives the record.
4. Stop the producer.
5. Observe an idle event after roughly the normal `idleEventInterval`.
6. Confirm it does not wait for multiplier × interval again as if no data had ever arrived.

### 22.3. Scenario after the first idle period

1. Leave the container without records long enough for an idle event to fire.
2. Send a record.
3. Observe `ListenerContainerNoLongerIdleEvent` if supported and applicable to lifecycle.
4. Stop sending records.
5. Confirm idle detection continues using the post-data threshold.

### 22.4. Concurrency scenario

1. Create a multi-partition topic.
2. Run the listener with `concurrency > 1`.
3. Send data to one partition and none to another.
4. Collect events along with listener ID/partition metadata.
5. Verify the dashboard does not misclassify one child's idle as group-wide downtime.

### 22.5. Paused container scenario

1. Start the container and verify data was received.
2. Pause the container.
3. Observe events/state in your Spring Kafka version.
4. Verify alerts exclude intentional pauses.
5. Resume and send more records.
6. Verify no records are lost and offsets advance properly.

### 22.6. Non-responsive consumer scenario

To demonstrate the difference, create a controlled blocked listener/poll scenario in an integration test and observe the non-responsive monitor. Never use idle events as the sole signal to judge poll health.

## 23. Example event collector for testing

A minimal collector:

~~~java
@Component
public class IdleEventCollector {

    private final BlockingQueue<ListenerContainerIdleEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        events.offer(event);
    }

    public ListenerContainerIdleEvent awaitIdle(
            long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
~~~

This is a simple test helper; a real integration test suite needs:

- Filtering events by test listener/container.
- Resetting the collector between tests.
- Bounding the queue if tests run long.
- Using the same application context or appropriately injected collector.
- Avoiding assertions that depend on event ordering across multiple consumers.

When checking timing, record event receipt timestamps relative to container start. Never assert against overly tight intervals, because thread scheduling and Kafka polling are not real-time clocks.

## 24. Runbook: idle events arrive too early after startup

1. Confirm the running listener ID and container factory.
2. Read the actual `idleEventInterval`.
3. Read the actual `idleBeforeDataMultiplier`.
4. Check whether the listener already received any record before the event.
5. Check whether pre-existing backlog records were consumed immediately after startup.
6. Check whether the container restarted without initializing a fresh consumer as expected.
7. Inspect startup, first-record, and event timestamps.
8. Check Spring Kafka version and default values.
9. Compare against poll timeout and concurrency.

If the listener received even a single record, the "before data" phase may already have ended; emitting idle events at the normal interval afterward is not a multiplier bug.

### 24.1. Do not fix solely by raising the multiplier

If events arrive early because the producer is genuinely down, increasing the multiplier only hides the outage. If startup grace is truly insufficient, increasing the multiplier may be right. Distinguish the two causes using producer metrics and time-to-first-record.

## 25. Runbook: no idle events despite an empty topic

1. Confirm `idleEventInterval` is enabled.
2. Confirm the container started and is running.
3. Confirm the right listener factory is bound.
4. Check the initial wait: `interval × multiplier` may be longer than expected.
5. Check whether the event listener bean is scanned/registered by Spring.
6. Check whether event filtering logic drops the event due to listener ID mismatch.
7. Check whether the container is paused, stopped, or stuck in poll.
8. Inspect logs and the application event multicaster.
9. Check poll interval/timeout before assuming events are lost.

If the initial threshold is 5 minutes, seeing no idle event after 30 seconds is expected behavior. If the consumer cannot poll, investigate non-responsiveness rather than waiting for idle events.

## 26. Runbook: data received yet idle still uses the long threshold

1. Confirm the record was actually **received by the consumer/container**, not merely published by the producer.
2. Verify the record landed in the listener's target group/partition.
3. Check whether the event is emitted by another child consumer that has never received a record.
4. Inspect listener ID and instance in event metadata.
5. Check the most recent restart or rebalance.
6. Check for multiple listener factories with different multipliers.
7. Inspect event timestamps and poll scheduling.
8. Check Spring Kafka version and property semantics.

Especially with concurrent consumers, one child receiving data does not necessarily mean all other children have received data. Do not assume the entire container/group shares one message history if the implementation tracks per consumer.

## 27. Runbook: idle alert fires while consumer lag is 0

1. Check whether the producer is publishing records.
2. Check whether the topic actually received new data during the alert window.
3. Inspect consumer group committed offsets and end offsets.
4. Check the partition assignment of the event-emitting instance.
5. Confirm whether the workload is naturally sparse.
6. Check for planned maintenance or intentional pauses.
7. If there is no input and lag is 0, lower alert severity per business expectations.
8. If upstream is required to emit periodically, alert on upstream SLO rather than blaming the consumer immediately.

An idle consumer with no records to read can be a completely healthy state.

## 28. Runbook: idle alert fires while consumer lag grows

1. Identify which partitions show growing lag.
2. Verify the consumer container is running.
3. Check partition assignments and group rebalances.
4. Check consumer pause or backpressure state.
5. Check for deserialization failures or an error handler stuck on a poison pill.
6. Check consumer poll responsiveness and thread dumps.
7. Check Kafka network/authentication/authorization errors.
8. Compare producer rate and consumer records-consumed rate.
9. Fix the root cause, then monitor lag and oldest-record age dropping.

If lag grows while zero records are delivered, this may be a serious incident; the multiplier only tunes startup signaling, not recovery.

## 29. Runbook: NonResponsiveConsumerEvent alongside idle

1. Do not assume both events mean the same thing.
2. Verify whether the consumer thread is calling poll steadily.
3. Inspect thread dumps and GC pauses.
4. Check listener processing time and downstream timeouts.
5. Cross-check monitor interval, poll timeout, and `max.poll.interval.ms`.
6. Inspect group rebalances.
7. Prioritize resolving poll responsiveness if the consumer is stuck.
8. After recovery, resume evaluating idle against expected data traffic.

A consumer silent because there is no data is fundamentally different from a consumer unable to execute poll.

## 30. Common mistakes

**Thinking the multiplier slows Kafka polling.** The property only scales the idle event threshold before first data.

**Setting the multiplier while forgetting `idleEventInterval`.** The multiplier does not enable events on its own.

**Assuming the multiplier applies to every idle period.** After receiving data, the mechanism uses the normal idle threshold.

**Assuming an idle event is a broker failure.** An empty topic or a consumer at the end of the log can still go idle normally.

**Assuming no idle events means the consumer is healthy.** The consumer may be stopped, non-responsive, or have idle events disabled.

**Alerting on every DLT idle event.** A silent DLT is normally healthy.

**Aggregating one child consumer's idle into whole-group downtime.** You must inspect assignments and concurrency.

**Ignoring pause state.** Intentional pauses can create long stretches without incoming data.

**Cranking the multiplier huge to silence alerts.** This can hide startup failures and delay detection.

**Using idle events to unconditionally restart containers.** Restarts trigger rebalances and do not fix missing upstream data.

**Running heavy HTTP/database work inside `@EventListener`.** This can block event dispatch and disrupt the container.

**Skipping tests with realistic poll scheduling.** Reading config alone does not prove thresholds behave properly at runtime.

## 31. Implementation checklist

### Configuration

- [ ] Identified whether the workload has continuous or sparse traffic.
- [ ] `idleEventInterval` is enabled only when idle events are genuinely needed.
- [ ] `idleBeforeDataMultiplier` is chosen based on startup grace and SLOs.
- [ ] Verified defaults and APIs on the exact Spring Kafka version.
- [ ] Configured on the actual listener factory/container in use.
- [ ] Clearly separated `idleBetweenPolls`, `pollTimeout`, and idle thresholds.

### Application events

- [ ] Listener registered for `ListenerContainerIdleEvent`.
- [ ] Handling for `ListenerContainerNoLongerIdleEvent` if needed to close incidents.
- [ ] Event callbacks are lightweight and never touch `KafkaConsumer` from the wrong thread.
- [ ] Listener/instance/partition context captured to avoid misaggregation.
- [ ] Repeated idle events do not generate a fresh alert each time.

### Observability

- [ ] Consumer lag, input producer rate, and records consumed rate instrumented.
- [ ] Signals for consumer running/paused/assignment states present.
- [ ] Non-responsive monitoring is independent of idle events.
- [ ] Time-to-first-record metric captured when startup timing matters.
- [ ] Alerts distinguish startup, steady state, and maintenance.
- [ ] Metric tags have low cardinality; event IDs are excluded from metrics.

### Testing

- [ ] Empty topic before first data waits for the multiplied threshold.
- [ ] Early arrival of the first record activates the normal idle threshold afterward.
- [ ] Prolonged listener idle emits events according to policy.
- [ ] When data resumes, no-longer-idle events behave as expected.
- [ ] Concurrent consumers/partitions are not misclassified.
- [ ] Pause/rebalance/restart tested if relevant to the system.
- [ ] Test timing includes tolerance for poll and scheduler jitter to avoid flaky assertions.

## Conclusion

`idleBeforeDataMultiplier` is the multiplier for `idleEventInterval` during the phase when **a Spring Kafka listener container has not yet received its first data**. It helps prevent premature idle events during startup or when topics are initially empty, while preserving normal silence-detection thresholds once the consumer has received data. This property does not alter poll cadence, offset commits, retries, or broker connectivity.

To operate effectively, enable `idleEventInterval` on the container actually in use, choose the multiplier based on startup grace and SLOs, and observe `ListenerContainerIdleEvent` alongside data-resumption events. Always separate **idle due to no records** from **non-responsive consumer due to stalled polling**, and combine partition assignment, lag, producer rate, pause state, and lifecycle signals. A well-chosen multiplier cuts false alerts without replacing comprehensive Spring Kafka consumer reliability monitoring.
