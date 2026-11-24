# ListenerContainerNoLongerIdleEvent

In **Spring Kafka**, **ListenerContainerNoLongerIdleEvent** is an **application event** published when a **message listener container that had been identified as idle** begins **receiving records again**. This event marks the transition from **no records received for a period of time** to **data being delivered to the consumer/container**, helping operations distinguish "input temporarily quiet" from "data flow has just resumed."

It is an observational signal for **the stream of records at the listener container**, not confirmation that business logic succeeded, nor proof on its own that the consumer group has fully recovered. For example, a newly fetched record can trigger the no-longer-idle event yet the listener still throws an exception afterward. To conclude that the pipeline is healthy again, combine the event with listener success rate, consumer lag, downstream health, and recovery metrics.

For this event to have meaning, the application must **configure idle detection** on the listener container, commonly via **ContainerProperties.setIdleEventInterval(...)**. Spring Kafka tracks the duration without received records and can publish **ListenerContainerIdleEvent**. When a record arrives after an idle state has been recorded, the framework can publish the corresponding **ListenerContainerNoLongerIdleEvent**.

This lesson focuses on the conditions for event publication, safe listening, the meaning of properties, concurrency and pause/rebalance effects, measuring idle duration, and operating when traffic returns.

## 1. Why know when a container is "no longer idle"?

An event-driven system can have completely normal periods with no traffic:

- A topic only has data during business hours.
- Producers publish in batches every few minutes.
- One partition receives very few records due to key distribution.
- A pipeline goes quiet after draining a backlog.
- Upstream stops publishing during maintenance.
- A consumer temporarily pauses for backpressure, then resumes.

When data begins arriving again, operations typically want to know:

1. Which container just transitioned from idle to active?
2. How long did the idle period last?
3. Which partitions belong to that container's scope?
4. Were records actually processed successfully or did they just arrive?
5. Has consumer lag started decreasing?
6. Did the event occur after a pause/rebalance or an upstream outage?
7. Should the "no traffic" alert be cleared, or is further verification needed?

**ListenerContainerNoLongerIdleEvent** answers the core part: **the container has received data again after a period identified as idle**. Questions about business success and health still require independent observation.

## 2. Idle and no-longer-idle in the container lifecycle

Suppose a container holds partition assignments and received its most recent record at time T0.

~~~text
T0          Container receives a record
T0 + 5s     No new records
T0 + 10s    Reaches idleEventInterval, framework publishes idle event
T0 + 20s    Still no records; may continue publishing idle events
T0 + 25s    Container receives a new record
T0 + 25s    Publishes no-longer-idle event per version mechanics
T0 + 25s+   Container continues receiving and processing data
~~~

These timestamps are illustrative only. Idle detection and application event dispatch depend on poll cadence, container scheduling, thread processing, interval values, and Spring Kafka version; do not treat the event as an absolute millisecond-precision timer.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVING
    RECEIVING --> IDLE: No records for idleEventInterval
    IDLE --> IDLE: Still no records
    IDLE --> RECEIVING: Record arrives, emit NoLongerIdleEvent
    RECEIVING --> IDLE: Again no records for interval
~~~

Receiving a record while the container is operating normally **does not produce a NoLongerIdleEvent**. The event is meaningful because **there was a preceding idle state**.

## 3. Comparison with ListenerContainerIdleEvent

The two events complement each other:

| Event | When it appears | What it tells you |
|---|---|---|
| **ListenerContainerIdleEvent** | Container receives no records within configured idle interval | Container is idle per detection rules |
| **ListenerContainerNoLongerIdleEvent** | Container begins receiving records after being idle | Record flow has returned at the container |
| **ListenerContainerPartitionIdleEvent** | A partition is identified as idle, in supported versions | Idle at the TopicPartition level |
| **ListenerContainerPartitionNoLongerIdleEvent** | A partition receives records again after being idle, in supported versions | State transition at the partition level |

A container with multiple partitions can receive steady data on P0 yet no data on P1. In that case, **container-level events** may not accurately reflect P1's individual idle state. If partition-by-partition monitoring is needed, choose version-supported partition-specific events/metrics rather than inferring from a single shared event.

Important: **ListenerContainerNoLongerIdleEvent is not an event recording that "the listener method succeeded."** It can appear before business logic completes or before the corresponding offset is committed.

## 4. Conditions for publishing the event

In a standard configuration, enable the listener container's idle detection using a **positive idleEventInterval**.

Typical sequence:

1. The container is started and able to poll/receive records.
2. No records are received within `idleEventInterval`.
3. The container publishes an idle event and records the idle state.
4. A record is received again by the container.
5. Spring Kafka publishes **ListenerContainerNoLongerIdleEvent**.

If **idleEventInterval is not enabled** or is larger than the actual quiet period, the application may see no idle event and therefore no observable transition to no-longer-idle.

A 2-second gap between messages will typically **not produce an event** if `idleEventInterval` is 30 seconds.

This event is based on **records received by the container**, not on upstream producers sending messages. A producer succeeding in sending does not prove the consumer fetched the record; the consumer might be paused, lack assignment, be rebalancing, lack permissions, or be reading at another position.

## 5. Configuring idleEventInterval

Spring Kafka listener factory example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        // Detect container idle with an illustrative 10-second threshold.
        factory.getContainerProperties()
                .setIdleEventInterval(10_000L);

        return factory;
    }
}
~~~

Listener using the factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        service.process(event);
    }
}
~~~

**10_000L is in milliseconds**, equivalent to 10 seconds. This is an illustrative threshold, not a suitable value for every system.

When defining a custom listener factory, preserve other settings required by the application, such as message converters, concurrency, AckMode, error handlers, transaction managers, and customizers. If the listener does not actually use the factory with idle detection enabled, you may not receive the expected events.

## 6. Choosing idleEventInterval

The interval value should be based on **traffic patterns** and **monitoring goals**, not just an easy-to-remember round number.

| Workload type | Normal data gaps | How to choose threshold |
|---|---|---|
| Continuous payment events | Very few long gaps | Can choose a relatively short threshold to detect silent upstream |
| Batch import every 10 minutes | No records between batches | A 10-second threshold creates idle/no-longer-idle every batch, which may be expected |
| Low-volume admin events | Several hours with no records | Short thresholds easily emit noisy, low-value telemetry |
| IoT burst traffic | Multiple bursts and quiet gaps | Choose interval based on burst cycles/SLA |
| Operational heartbeat topic | Steady cadence | Can set threshold to a few multiples of expected period |

Setting the interval too low can cause the system to emit **many idle/no-longer-idle pairs** due to natural traffic fluctuations. Setting it too high prevents quick detection of short outages.

To avoid noisy alerts, separate the threshold for **publishing events** from the threshold for **sending alerts**. For instance, receiving an event after 30 seconds of idle does not necessarily warrant paging; the upstream SLA might be 5 minutes.

## 7. Listening for the event with @EventListener

Spring lets you listen for application events using **@EventListener**.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaActivityEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaActivityEventLogger.class);

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        log.info(
            "Kafka listener no longer idle: listenerId={}, idleMs={}, partitions={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions()
        );
    }
}
~~~

The example uses common properties of the event such as **listener ID**, **idle time**, and **topic partitions**. Exact getter/API names can vary across Spring Kafka versions; check your current dependency when compiling.

Callbacks should be **short and non-blocking**. Logging and incrementing metrics are usually appropriate. Do not directly invoke REST APIs, long database transactions, or complex recovery tasks inside a synchronous event handler.

The handler's purpose is to **record the transition back to active state**, not turn it into a mandatory business-processing step before the listener can proceed.

## 8. Properties to understand

Depending on the Spring Kafka version, the event provides similar metadata:

| Property | Operational meaning |
|---|---|
| **listenerId** | Identifier of the container/listener publishing the event |
| **idleTime** | Idle duration reported by the event, typically in milliseconds |
| **topicPartitions** | TopicPartitions associated with the consumer/container publishing the event |
| **consumer** | Associated consumer, if provided by the version's API |
| **paused** | Pause status metadata in supported versions |
| **source/container** | Event source per Spring's application event model |

Notes:

- **idleTime** does not mean the processing latency of the first record after idle.
- **topicPartitions** is the relevant assignment scope; do not assert that the newly received record came from **every partition** in that list.
- **listenerId** is useful for categorizing services/containers; with concurrency, IDs may carry a child-container suffix.
- **consumer** must only be accessed following `KafkaConsumer` thread-safety rules.
- **paused** or related state helps explain that no records arrived because of a pause, not necessarily because upstream stopped.

Do not rely solely on this event to infer the **key, value, offset, or business result** of the arriving record. Such details should be recorded in the listener or interceptor per security policy.

## 9. Listener ID and concurrent containers

A **ConcurrentMessageListenerContainer** can create multiple child listener containers/consumers. When `@KafkaListener` has **concurrency = 3**, each child consumer has its own assignment and record-receipt cadence.

Example:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "order-service",
    concurrency = "3"
)
public void onOrder(OrderEvent event) {
    service.process(event);
}
~~~

In common Spring Kafka versions, child container IDs can look like:

~~~text
ordersListener-0
ordersListener-1
ordersListener-2
~~~

Therefore, a handler filtering solely by exact equality with `"ordersListener"` may miss events from child containers, depending on event source and version.

A safe filtering example following application conventions:

~~~java
@EventListener
public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
    String listenerId = event.getListenerId();

    if (listenerId == null
            || !listenerId.startsWith("ordersListener")) {
        return;
    }

    log.info(
        "orders listener resumed traffic: id={}, idleMs={}",
        listenerId,
        event.getIdleTime()
    );
}
~~~

When multiple listener IDs share a similar prefix, inspect the ID structure to avoid false matches. Maintain an explicit set of IDs or managed mapping instead of relying solely on `startsWith`.

**One child container leaving idle does not mean all other child containers have received data.** One consumer may be assigned a hot partition while another sits on a low-traffic partition and stays idle.

## 10. Application event publication and execution flow

Under standard Spring application event settings, a **synchronous ApplicationEventMulticaster** dispatches event listeners on the thread publishing the event. For Kafka container events, this can be **the consumer thread**.

If `@EventListener` runs long, it can delay consumer polling/dispatching, increase processing lag, and even impact **max.poll.interval.ms** when combined with long listener processing.

Do not:

~~~java
@EventListener
public void onNoLongerIdle(
        ListenerContainerNoLongerIdleEvent event) {

    // Avoid: blocking remote call inside a consumer event callback.
    remoteMonitoringApi.postActivityState(event.toString());
}
~~~

Do:

- Write concise structured logs.
- Increment counters or update timestamp gauges.
- Push a small signal to a bounded internal queue if further processing is needed.
- Use controlled async event handling if network I/O is truly required.
- Isolate telemetry errors so they cannot break the consumer flow.

Note: if shifting event handling to another thread with **@Async** or an async event multicaster, **do not use `KafkaConsumer` from `event.getConsumer()` on that thread**. `KafkaConsumer` requires thread confinement, and arbitrarily calling pause/seek/commit from another thread can cause errors or races.

## 11. Warning about getConsumer()

Some Kafka listener container events can carry a **KafkaConsumer** reference. This reference is only usable within the proper thread context and does not mean the application is allowed to control the consumer from everywhere.

Points to remember:

1. `KafkaConsumer` is generally not thread-safe.
2. The Spring Kafka container owns the consumer loop.
3. Async `@EventListener` usually runs outside the consumer thread.
4. Calling `consumer.seek()`, `commitSync()`, `pause()`, or `resume()` from an external thread can be unsafe.
5. Receiving a no-longer-idle event is not a reason to seek or commit manually.
6. If flow control is needed, prefer container-provided **MessageListenerContainer.pause()/resume()** or **pausePartition()/resumePartition()** APIs.

If interacting with the consumer on the proper thread via framework-permitted APIs is necessary, do so inside callbacks designed for that purpose with clear lifecycle awareness. For observability, reading event attributes is usually sufficient.

## 12. Do not equate "no longer idle" with "consumer healthy"

The event signals that the container **has received records again**. It **does not prove**:

- The listener processed the record without errors.
- Business side effects committed in the database.
- The Kafka offset was committed.
- Consumer group lag dropped to 0.
- Every assigned partition is receiving data.
- Retry/DLT queues have drained.
- Downstream HTTP APIs or databases have recovered.
- All application instances are operating normally.

Example:

~~~text
Container IDLE for 60 seconds
    |
    v
New record arrives
    |
    v
ListenerContainerNoLongerIdleEvent
    |
    v
Listener throws IllegalArgumentException
    |
    v
DefaultErrorHandler -> DLT
~~~

The no-longer-idle event occurred, yet business processing still failed. If a dashboard immediately flips the entire service state to "HEALTHY" based solely on this event, it can hide a downstream outage.

It is better to keep two independent states:

- **Input activity:** active or idle.
- **Processing health:** success, erroring, paused, lagging, or unavailable.

## 13. Distinguishing an idle container from a consumer that stopped polling

This is a critical comparison in **Spring Kafka Reliability Operations**.

| Situation | Poll loop | Records | Useful events/metrics |
|---|---|---|---|
| Empty topic, healthy consumer | Polling steadily | None | ListenerContainerIdleEvent |
| Topic receives data again | Polling steadily | Present | ListenerContainerNoLongerIdleEvent |
| Listener/consumer thread blocked | Polling may stall | No progress | NonResponsiveConsumerEvent, poll metrics, thread dumps |
| Consumer paused | Polling usually continues | Not dispatched from paused partitions | ConsumerPausedEvent, pause state, idle metrics |
| Consumer stopped | No polling after stop | None | Lifecycle events |
| No partitions assigned | Poll/group activity may continue | None from assignment | Assignment/rebalance metrics |

**NonResponsiveConsumerEvent** reflects that the container detected poll was not progressing on time per Spring Kafka's monitoring mechanism; it is not synonymous with `ListenerContainerIdleEvent`.

For instance, a topic with no records for 10 minutes while the consumer polls steadily may simply be idle, not non-responsive. Conversely, a deadlocked listener preventing the consumer from polling may not have produced a no-longer-idle event even while upstream sends many records.

## 14. Pause/resume and NoLongerIdleEvent

A **paused** container suspends receiving data from paused partitions, yet usually keeps polling to maintain group membership. Upon resuming and receiving records, the container can publish no-longer-idle if it had previously reached an idle state per version/configuration.

However, do not automatically conclude:

~~~text
ConsumerResumedEvent == ListenerContainerNoLongerIdleEvent
~~~

The two events have different meanings:

- **ConsumerResumedEvent:** consumer/partition resumption has been applied.
- **ListenerContainerNoLongerIdleEvent:** data is arriving again after an idle period.

Resume can happen while the topic is still empty, in which case there are no records yet and the container cannot be considered "no longer idle." Conversely, a container can leave idle naturally when a producer sends new records without any pause/resume.

If the system uses backpressure, record pause state, resume events, idle/no-longer-idle, and actual processing throughput together to see the true recovery curve.

## 15. Idle events in consumers with Kafka transactions

With transactional Kafka processing, the event remains primarily a **record-receipt** signal, not a transaction commit.

Suppose:

1. Container receives a record after an idle period.
2. `NoLongerIdleEvent` is published.
3. Transactional listener starts processing.
4. Listener sends output records via `KafkaTemplate`.
5. Database or Kafka transaction fails.
6. Transaction aborts; input may be redelivered.

The event in step 2 does not prove the transaction in step 5 succeeded. When assessing reliable processing, combine it with:

- Transaction commit/abort metrics.
- Listener processing duration.
- Offset commits/transactional offsets.
- `AfterRollbackProcessor` activity.
- DLT/recovery outcomes.

If the input consumer uses **read_committed**, an open upstream transaction can prevent records from being returned to the consumer even though the producer already wrote bytes to Kafka. The container may appear idle until the transaction commits and records become readable under the isolation setting.

## 16. Container-level events and partition-level events

A consumer can be assigned multiple partitions. When P0 has continuous data while P1 has no records for several hours, container-level idle detection may not reveal P1's problem.

If your Spring Kafka version supports it, you can configure/observe **partition idle** via the corresponding property and events. For example, some versions provide **ContainerProperties.setIdlePartitionEventInterval(...)** to detect individual partitions going idle.

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(30_000L);

// If the version supports partition idle detection:
factory.getContainerProperties()
        .setIdlePartitionEventInterval(60_000L);
~~~

For partition-specific events:

~~~java
import org.springframework.kafka.event
        .ListenerContainerPartitionNoLongerIdleEvent;

@EventListener
public void onPartitionNoLongerIdle(
        ListenerContainerPartitionNoLongerIdleEvent event) {

    log.info("Kafka partition is active again: {}", event);
}
~~~

The second snippet illustrates the event/API names in supported versions; verify the exact package and metadata availability in your dependency.

Use partition-level observability when the goal is detecting **hot/cold partitions**, skewed key distribution, or a partition not being written by producers as designed.

## 17. Structured logging for state transitions

An event log should carry enough information for operators to trace which listener became active again without causing unbounded log volume.

Example:

~~~text
event=kafka_listener_no_longer_idle
service=orders-service
listener_id=ordersListener-1
consumer_group=order-service
idle_duration_ms=45123
assigned_partition_count=2
container_state=RUNNING
timestamp=2026-11-15T10:15:30Z
~~~

This is an illustrative format, not Spring Kafka's default log format. Consumer group, container state, and service may need to be supplied from application configuration, since not every field is directly available on the event across all versions.

Fields to consider:

- Service, environment, and version.
- Listener ID or child container ID.
- Idle duration reported by the event.
- Relevant topic/partitions.
- Pause state if applicable.
- Event timestamp.
- Expected cause, if the system has maintenance or recovery context.

Do not log message payloads, credentials, or sensitive data merely to record the transition from idle to active.

## 18. Metrics for ListenerContainerNoLongerIdleEvent

Suitable metrics:

| Metric | Meaning |
|---|---|
| **kafka.listener.no_longer_idle.events** | Counter of times the container exited idle |
| **kafka.listener.idle.events** | Counter of times the container was identified as idle |
| **kafka.listener.reported_idle_duration** | Histogram/distribution of idle intervals |
| **kafka.listener.last_activity_timestamp** | Timestamp showing signs that records returned |
| **kafka.listener.processing.success** | Counter of successful business processing, measured separately |
| **kafka.listener.processing.failure** | Counter of business errors, measured separately |
| **kafka.consumer.lag** | Group/partition backlog |
| **kafka.consumer.poll.rate** | Verifies poll loop |
| **kafka.listener.paused** | Whether the container is paused |
| **kafka.listener.assignment.count** | Whether partition assignments exist |

Metric names are **suggested conventions**, not all emitted out of the box by Spring Kafka. With Micrometer, you can register custom counters/timers inside an event listener.

Do not use offsets, event IDs, keys, or full exception messages as metric tags. Use only low-cardinality dimensions such as service, normalized listener ID, topic, and environment.

For concurrent containers, if listener IDs include child numeric suffixes, cardinality is usually bounded yet can shift during scale-out; consider aggregating by logical listener ID on dashboards.

## 19. Micrometer integration example

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class KafkaIdleTransitionMetrics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleTransitionMetrics.class);

    private final MeterRegistry registry;

    public KafkaIdleTransitionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        String listenerId = event.getListenerId();

        registry.counter(
                "kafka.listener.no.longer.idle.events",
                "listener", listenerId
        ).increment();

        registry.timer(
                "kafka.listener.reported.idle.duration",
                "listener", listenerId
        ).record(
                Math.max(0L, event.getIdleTime()),
                TimeUnit.MILLISECONDS
        );

        log.info(
            "Listener active again: id={}, idleMs={}",
            listenerId,
            event.getIdleTime()
        );
    }
}
~~~

The example assumes `MeterRegistry` is supplied by Micrometer/Actuator and uses compatible version event getters. To avoid excessive cardinality, do not include per-record identifiers in tags. If listener IDs are dynamically generated or very numerous, normalize to logical listener IDs before tagging.

This metric measures **transitions out of idle** and **event-reported idle length**, not transaction commit success or end-to-end business latency.

## 20. Do not alert on every no-longer-idle event

Some systems operate in bursts: idle 30 seconds, receive a burst of data, idle again. In such cases, repeated `NoLongerIdleEvent` occurrences can be normal.

More sensible alerting rules:

- Idle lasts longer than SLA on a topic that should always have traffic.
- Consumer lag rises simultaneously with too few processed records.
- Listener just became no-longer-idle yet processing failure rate spikes suddenly.
- No-longer-idle events exhibit **flapping** outside expected traffic rhythms.
- One partition remains idle while other partitions receive records steadily and business contracts require even distribution.
- After upstream recovery, no listener successes occur despite a no-longer-idle event.
- Container stops polling, rather than merely receiving no records.

If the goal is simply noting "traffic is back," emit an informational event/log. There is no need to page on-call by default every time records arrive after idle.

## 21. Idleness and low throughput

**Idle** is not synonymous with **low throughput**.

Example:

| Case | Idle event emitted? | Observation |
|---|---|---|
| No records for 60s, idle threshold 30s | Likely yes | Container received no data long enough |
| One record every 10s, threshold 30s | Usually no | Low throughput yet idle interval never reached |
| Consumer receives records fast yet listener fails constantly | Usually no | Not idle, yet pipeline is unhealthy |
| Consumer paused | May look idle depending on mechanics/version | Must check pause state |
| Consumer has no assignment | Receives no records | Do not infer upstream stopped sending |
| read_committed waiting on upstream transaction | May receive no records | Data may already sit in broker yet remain invisible |

Thus, a no-longer-idle event only identifies that **record flow returned after a long enough silence**, not the average records/sec over a wide window.

## 22. Interaction with retry and DLT

In systems using **DefaultErrorHandler**, redelivery of a failing record may affect container "record received" observations depending on implementation and retry type. Do not assume a `NoLongerIdleEvent` always represents **a brand-new business event**.

In systems using **@RetryableTopic**, each retry topic may have its own listener container. A listener on a retry topic can go idle and then no-longer-idle when a retry record arrives, while the main topic listener stays active or vice versa.

Operational points:

- Distinguish logical listener IDs from retry-stage listener IDs.
- Do not sum no-longer-idle counts across all retry containers as the count of new business events.
- A DLT listener can become no-longer-idle when an error record arrives; that **is not successful recovery**.
- During a downstream outage, consumer lag and retry/DLT ingress can rise immediately after the event signals active input.
- Maintain separate metrics for listener success, recovery success, and publish failures.

If using event-based automation, never trigger DLT replay solely because the DLT listener became no-longer-idle; replay requires business policy and idempotency.

## 23. Effects of rebalance and restart

A container can gain or lose partition assignments during a consumer group rebalance. When assignments change, record sources and idle detection state can shift accordingly.

Example:

1. Consumer C1 is idle because it was assigned low-traffic partitions.
2. Consumer C2 leaves the group.
3. Rebalance moves a hot partition to C1.
4. C1 receives records.
5. C1 can transition from idle to active.

`NoLongerIdleEvent` in this situation **does not necessarily mean the producer just restarted**. It may simply stem from a **new partition assignment**.

After a restart, prior idle state on the old container is not automatically preserved as durable business state. Do not design logic using `NoLongerIdleEvent` as a unique marker across process restarts.

On dashboards, combine milestones:

- Container started/stopped.
- Partitions assigned/revoked.
- Idle/no-longer-idle events.
- Pause/resume events.
- Consumer lag and records-consumed-rate.

That allows distinguishing upstream traffic recovery from rebalances and assignment shifts.

## 24. When the container was idle yet no NoLongerIdleEvent appears

Several causes:

| Symptom | Possible explanation |
|---|---|
| Producer sent data yet no event | Records have not been fetched/received by container yet |
| Container no longer running | No consumer loop left to receive records |
| Consumer group reading different topic/partition | Records are outside assignment |
| Consumer paused | Data from paused partitions is not dispatched yet |
| isolation.level=read_committed | Transactional output not committed yet so not visible |
| Deserializer or poll failure | Consumer has not moved records into normal processing flow |
| Listener factory did not enable idleEventInterval | Required idle detection mechanism is missing |
| Never emitted idle event | No preceding idle state to transition to no-longer-idle |
| Event handler not registered | Event may be published yet application is not listening |
| Event listener filters wrong ID | Concurrent child IDs differ from expected ID |
| Custom ApplicationEventMulticaster | Dispatch/async/error behavior differs from default |

Do not hastily conclude Spring Kafka "lost an event." Verify configuration, container state, assignment, and the exact conditions for no-longer-idle.

## 25. When the event appears yet data still fails to process

This is a special case that must be separated clearly.

~~~text
NoLongerIdleEvent at 12:00:00
Listener exception at 12:00:00.050
DefaultErrorHandler retry
DLT recovery at 12:00:04
Consumer group lag remains high
~~~

The event announces **records arrived after idle**. It does not guarantee:

- Records had no deserialization or conversion errors.
- Retries succeeded.
- DLT publishing succeeded.
- Business state was written to the database.
- Offsets were committed.

If you want to verify processing-flow recovery, use an application-managed state machine:

~~~text
INPUT_IDLE
  |
  v
INPUT_ACTIVE_OBSERVED
  |
  +--> PROCESSING_HEALTHY   (after success metrics meet conditions)
  |
  +--> PROCESSING_ERRORING  (when failure rate is high)
~~~

Do not jump directly from `INPUT_IDLE` to `PROCESSING_HEALTHY` based solely on `ListenerContainerNoLongerIdleEvent`.

## 26. Example monitoring application status

A simple monitoring component can store the latest timestamp when a container became no-longer-idle for status display.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class ListenerActivitySnapshot {

    private final Map<String, Instant> lastReturnFromIdle =
            new ConcurrentHashMap<>();

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        lastReturnFromIdle.put(
                event.getListenerId(),
                Instant.now()
        );
    }

    public Instant lastReturnFromIdle(String listenerId) {
        return lastReturnFromIdle.get(listenerId);
    }
}
~~~

This is **in-memory diagnostic state**. It is lost on restart and only records transitions **out of idle**, not updating on every new record. Do not use it as the source of truth for business checkpoints or SLAs across restarts.

If long-term auditing is needed, emit metrics/logs to an observability system or write bounded durable activity state, avoiding synchronous database writes inside consumer event callbacks.

## 27. Testing with EmbeddedKafka or Testcontainers

To verify no-longer-idle emission conditions, use a real broker in an integration test. Unit tests constructing event objects manually only verify the event listener, not that the container publishes events at the right time.

Scenario:

1. Create a dedicated Kafka topic and consumer group for testing.
2. Configure the listener factory with a short yet stable **idleEventInterval**.
3. Start the container and wait for partition assignment.
4. Publish no records for longer than the idle threshold.
5. Verify **ListenerContainerIdleEvent** appears.
6. Publish a valid record to the test topic.
7. Wait for **ListenerContainerNoLongerIdleEvent**.
8. Verify listener ID/partitions and reasonable idle duration.
9. Verify the listener method actually receives the record.
10. Wait less than `idleEventInterval` and publish another record; do not expect an extra no-longer-idle event.
11. Wait for the container to go idle again, publish a record, and verify a new state transition cycle.
12. Clean up contexts/groups and topics as needed.

Use **polling assertions or latches with timeouts** instead of fixed `Thread.sleep` as pass/fail criteria. Do not require the event to arrive on an exact millisecond mark because scheduling and poll timing can vary.

## 28. Recorder example for integration tests

A test support bean can collect event names and listener IDs:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdleTransitionRecorder {

    private final List<String> transitions =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        transitions.add("IDLE:" + event.getListenerId());
    }

    @EventListener
    public void onActive(
            ListenerContainerNoLongerIdleEvent event) {
        transitions.add("ACTIVE:" + event.getListenerId());
    }

    public List<String> transitions() {
        return List.copyOf(transitions);
    }

    public void clear() {
        transitions.clear();
    }
}
~~~

In an integration test:

- Wait until the recorder observes IDLE for the target listener.
- Publish a Kafka record.
- Wait for ACTIVE on the corresponding listener.
- Check an independent listener processing counter or latch.
- Do not depend on strict event ordering across multiple child containers when concurrency is high.
- Use isolated test contexts or reset the recorder between tests to prevent contamination.

Initial records right after startup can generate activity before the idle timer hits its threshold; design test timing cleanly.

## 29. Testing concurrency and partition-specific idle

With **concurrency=2** and a topic with at least two partitions:

1. Wait for assignments to stabilize for each child consumer.
2. Send records continuously to P0; send none to P1.
3. Observe container-level idle events per child assignment.
4. Cross-check child listener IDs in the events.
5. If partition-level behavior is needed, enable partition idle events supported by your Spring Kafka version.
6. Send a record to P1 after an idle period.
7. Verify the event matches the partition receiving data again.
8. Verify one child/partition becoming active does not make you infer the entire group is active.

If both partitions are assigned to the same consumer, container-level events cannot separate P0 and P1. The test must verify assignments before asserting child container behavior.

This is why distinguishing container-level from partition-level no-longer-idle is so important.

## 30. Testing pause and resume

Another test:

1. Start the listener and wait for assignment.
2. Call `container.pause()` and wait for actual paused state.
3. Wait for idle detection per configuration under appropriate conditions.
4. Publish a record while the consumer is paused.
5. Verify the record has not been received by the listener while still paused.
6. Call `container.resume()`.
7. Wait for actual resumed state.
8. Verify the record is received.
9. Observe whether a no-longer-idle event occurs depending on the version's idle state semantics.
10. Verify consumer lag and offset ack/commit.

Important: **Do not use the appearance of ConsumerResumedEvent as a substitute assertion for ListenerContainerNoLongerIdleEvent**. They are events with different meanings.

If the test had records already polled before pausing, they may still be in-flight; exclude them from assertions checking newly arrived records.

## 31. Runbook: NoLongerIdleEvent not received

When upstream reports "data is sending again" yet no event is seen:

1. Verify service, listener ID, container factory, and group ID.
2. Check that **idleEventInterval** is enabled on the right container.
3. Check whether **ListenerContainerIdleEvent** appeared previously.
4. Confirm the listener container is running and holds assignments.
5. Check the actual topic/partition the producer wrote to.
6. Check consumer paused state or partition pauses.
7. Check `isolation.level` and upstream transactional commits if applicable.
8. Check poll rate, `NonResponsiveConsumerEvent`, and consumer thread health.
9. Check deserialization, conversion, authorization, and broker errors.
10. Check listener ID filtering, especially child IDs when concurrency is high.
11. Verify the `@EventListener` bean is scanned and check application event multicaster configuration.
12. Send a valid test record to the right topic/partition following safe procedures.
13. Cross-check events, listener invocations, and committed offsets.
14. If the event still does not appear, record the Spring Kafka version and its event APIs for deeper investigation.

Do not "fix" it by faking a `NoLongerIdleEvent` and marking the pipeline healthy; doing so hides configuration bugs or real consumer failures.

## 32. Runbook: event appears yet pipeline still fails

When `NoLongerIdleEvent` appears after an outage yet business metrics remain bad:

1. Record the event timestamp and listener ID.
2. Check processing success/failure after that timestamp.
3. Cross-check consumer group lag per partition.
4. Check error handler retries, DLT ingress, and recovery failures.
5. Check database/API latency and availability.
6. Determine whether the listener receives records yet fails before commit.
7. Check transactional commits/aborts if the container is transactional.
8. Check whether side effects have idempotency upon record redelivery.
9. For retry topics, check the status of each retry listener container.
10. Only transition the incident state to recovered once business health criteria are satisfied.

The event can be **the first sign of traffic recovery**, but not the final proof of service recovery.

## 33. Common misconceptions

**Every new record emits NoLongerIdleEvent.** False: the event is for transitioning from idle back to receiving data.

**If a producer sends a record, the event will definitely appear.** False: the consumer must actually receive the record after an applicable idle state.

**Expecting the event without configuring idleEventInterval.** Idle detection must be enabled.

**NoLongerIdleEvent proves business processing succeeded.** The event only speaks to input activity.

**NoLongerIdleEvent is equivalent to ConsumerResumedEvent.** Resume is a pause control action; no-longer-idle is data arriving after idle.

**An idle container means no polling.** The consumer can still poll steadily when the topic has no data.

**An idle container means the consumer is hung.** Cross-check with `NonResponsiveConsumerEvent` and poll metrics.

**One child container active means the whole group is active.** Concurrent containers have different assignments and activity.

**The event's topicPartitions are all partitions that just received records.** It may merely describe relevant assignments, not the exact records triggering the event.

**Calling consumer APIs from an async event handler is always safe.** `KafkaConsumer` is not thread-safe.

**NoLongerIdleEvent must trigger a pager alert.** With bursty traffic, the event can be completely normal.

**Using the event as durable audit state.** Application events and local memory do not replace durable logs/metrics.

## 34. Production checklist

**Configuration**

- [ ] `idleEventInterval` is set on the right listener factory/container.
- [ ] Idle threshold reflects traffic patterns and SLAs.
- [ ] Handlers exist for `ListenerContainerIdleEvent` and `ListenerContainerNoLongerIdleEvent` where needed.
- [ ] Container-level and partition-level events are distinguished.
- [ ] Listener IDs and child container IDs are filtered accurately.

**Runtime safety**

- [ ] Event handlers are lightweight and never block the consumer thread.
- [ ] `KafkaConsumer` is never called from an async thread.
- [ ] `NoLongerIdleEvent` is never used to commit/seek offsets.
- [ ] The event is not treated as processing success.
- [ ] Events are interpreted properly during paused/rebalance states.

**Observability**

- [ ] Structured logs capture `listenerId`/`idleTime`/`partitions`.
- [ ] Metrics exist for no-longer-idle counts and idle duration.
- [ ] Separate metrics exist for processing success/error.
- [ ] Dashboards cross-check consumer lag, poll rate, and assignments.
- [ ] Alerts are aligned with SLAs to avoid flapping under burst traffic.

**Testing**

- [ ] Integration test covers idle → receive record → no-longer-idle.
- [ ] Test confirms no event is emitted on every subsequent normal record.
- [ ] Test covers concurrency/child listener IDs.
- [ ] Test covers pause/resume and returning input.
- [ ] Test covers event appearing while listener processing fails.
- [ ] Runbook exists for when the event does not appear as expected.

## 35. Conclusion

**ListenerContainerNoLongerIdleEvent** is a Spring Kafka application event signal indicating that **the listener container has received records after previously being identified as idle**. It complements `ListenerContainerIdleEvent`, helping track periods when data flow resumes after silence.

To use it properly, enable **idleEventInterval**, listen for the event via **@EventListener**, log listener ID and idle duration, understand concurrent child container states, and keep callbacks lightweight so they do not affect the consumer thread. Specifically, do not equate this event with consumer resume, transaction commit, or successful business processing.

In Spring Kafka operations, `NoLongerIdleEvent` is valuable as an **input activity indicator**. Combine it with **processing success, consumer lag, poll metrics, DLT/retry, pause/rebalance, and downstream health** to know whether the system truly recovered from an idle period or merely received one more record.
