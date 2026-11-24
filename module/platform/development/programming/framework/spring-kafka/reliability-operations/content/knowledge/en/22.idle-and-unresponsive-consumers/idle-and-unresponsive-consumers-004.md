# Detecting containers with no messages

In Spring Kafka, a listener container can be **RUNNING** yet receive no new records delivered to **`@KafkaListener`** for seconds or minutes. This state is not necessarily a fault: the topic may have no producer, partitions may be empty, the consumer may have caught up with the backlog, or the system may have intentionally paused to shed load. However, having **no messages** can also mask a failure: the consumer may have no assigned partitions, be pointed at the wrong topic or consumer group, remain paused without resuming, have a stalled poll thread, or fail to resume processing after a rebalance.

Spring Kafka provides **application events** for observing container idle state, notably **ListenerContainerIdleEvent** when no records are delivered within a configured interval and **ListenerContainerNoLongerIdleEvent** when data resumes after an idle period. For cases where the poll thread appears to stop making progress, Spring Kafka provides a separate monitoring mechanism that emits **NonResponsiveConsumerEvent**. These three signals answer different questions and must not be conflated.

This lesson belongs to the **Idle and Non-Responsive** chapter of the **Spring Kafka Reliability Operations** module. Its goal is to distinguish *empty topic*, *normal idle consumer*, *running container unable to process*, and *blocked consumer poll*, and then design appropriate metrics, alerts, runbooks, and recovery strategies without causing restart loops or duplicate side effects.

## 1. What does "no messages" actually mean?

A consumer can lack messages at several layers:

1. **Broker has no new records:** the topic receives no data; the consumer polls normally and repeatedly gets empty results.
2. **Group's partitions are caught up:** Kafka still holds records in the topic, but the group has committed up to the end of the log.
3. **Consumer has no assigned partitions:** the application has a listener, yet holds no partitions to read.
4. **Container is intentionally paused:** the consumer may keep polling to retain membership without delivering data to the listener.
5. **Data exists but does not reach the listener:** caused by deserialization failures, rebalances, error handling/backoff, transaction isolation, or misrouting/misconfiguration.
6. **Poll is not progressing:** the consumer thread is stuck in poll or blocked elsewhere so it fails to return to poll on time.
7. **Listener receives records but processing never completes:** from the application's perspective, no business work succeeds even though the Kafka consumer keeps reading messages.

Therefore, **listener silence** is not a comprehensive health metric.

| Question | Appropriate signal |
|---|---|
| Has the listener received records recently? | ListenerContainerIdleEvent, time since last record delivered |
| Is the consumer continuing to poll on time? | NonResponsiveConsumerEvent, poll telemetry, consumer thread state |
| Does the topic/partition have unprocessed data? | Committed offset, log end offset, consumer lag |
| Is the container running or stopped? | Listener container running state, lifecycle events |
| Is the consumer assigned partitions? | Assignment/rebalance events, consumer group describe |
| Is the container/partition paused? | Pause requested/effective state, pause/resume events |
| Are records succeeding in business processing? | Listener success/failure metrics, processing latency, side-effect confirmation |

## 2. Empty Kafka polls can be completely normal behavior

A Kafka consumer does not have to receive data on every `poll()`. When a partition has no new records, the consumer still calls poll to keep the group protocol advancing, handle rebalances, and wait for new data.

~~~text
Kafka topic has no new records
            |
            v
KafkaConsumer.poll()
            |
            +-- returns 0 records
            |
            v
Container keeps polling per lifecycle
            |
            v
Listener is not invoked
            |
            v
Container remains RUNNING and healthy
~~~

This commonly happens with on-demand event topics such as `OrderCancelled`, `AdminCommand`, or daily reconciliation streams. If the system expects hours without data, an idle event is operational telemetry, not a critical alarm.

Conversely, if a topic receives thousands of records per minute and the listener suddenly receives none, inspect assignment, paused state, lag, and consumer threads.

## 3. Distinguishing idle, paused, stopped, and non-responsive

| State | Container running? | Can poll continue? | Listener receiving messages? | Indicates an error? |
|---|---|---|---|---|
| Idle, topic has no records | Yes | Yes | No new records yet | Not necessarily |
| Idle, group caught up | Yes | Yes | No records to deliver | Not necessarily |
| Paused | Usually yes | Can continue to keep membership | No records delivered for paused partitions | May be intentional backpressure |
| Stopped | No | No | No | Depends on stop reason |
| Non-responsive poll | May still report running | Signs it cannot poll as expected | May receive no records | Requires investigation |
| Listener processing a slow record | Yes | May not have returned to poll yet | Current invocation unfinished | Depends on latency/SLO |
| No partitions assigned | Container may be running | Yes | No partitions to deliver from | Depends on config/group |

**Running=true only states that the container is in a lifecycle state.** It does not prove records are being delivered, does not prove threads are unblocked, and does not prove business side effects completed.

## 4. ListenerContainerIdleEvent

Spring Kafka can emit **ListenerContainerIdleEvent** when a listener container receives no records during the interval configured via **idleEventInterval**.

General properties:

- Idle is measured from the last data receipt/delivery per the container implementation, not from the last successful offset commit.
- Events can repeat while the container stays idle; one event does not mean a new "idle session" just began.
- Without configuring `idleEventInterval`, do not assume the application automatically emits idle events at your desired threshold.
- When data resumes after an idle state, the framework can emit **ListenerContainerNoLongerIdleEvent**.
- Container-level and partition-level events are not strictly equivalent.

Diagram:

~~~text
Application starts
        |
        v
Container polls
        |
        +-- Has records --> deliver to listener --> reset container idle cycle
        |
        +-- No records
                 |
                 v
          Time without data
                 |
          >= idleEventInterval
                 |
                 v
          ListenerContainerIdleEvent
                 |
                 +-- Still no data
                 |       |
                 |       v
                 |   May emit additional idle events
                 |
                 +-- Data returns
                         |
                         v
                 ListenerContainerNoLongerIdleEvent
~~~

Actual event cadence depends on the poll cycle, configuration, and Spring Kafka version. Never build logic requiring an event at an exact millisecond.

## 5. Configuring idleEventInterval

With `@KafkaListener` and a listener container factory, configure idle detection on **ContainerProperties**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // 30,000 ms without a message per container semantics.
    factory.getContainerProperties().setIdleEventInterval(30_000L);

    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

In this example, if the container continuously receives no records for long enough, Spring Kafka can emit an idle event for observation. **30 seconds** is only an illustration, not a universal recommendation.

Choose the interval based on topic characteristics:

- Continuous-data topics: a few dozen seconds can surface anomalies early.
- Low-traffic topics: too short an interval produces noisy normal idle events.
- Scheduled topics: base it on the interval between expected batches.
- Rare command topics: combine with producer SLAs or synthetic heartbeats instead of treating every gap as an incident.

Do not set an interval of a few milliseconds to be "as sensitive as possible"; the listener container can emit excessive events and log noise without making fault detection more reliable.

### 5.1. Idle before ever receiving data

Some Spring Kafka versions support properties affecting the first idle report, such as a multiplier for the wait before any data has arrived. Post-startup behavior may differ from idle behavior after records have already been processed.

When designing alerts, distinguish:

- **Startup idle:** the listener just started and has never seen a record.
- **Operational idle:** the listener previously processed data and then went silent.
- **Expected quiet period:** the topic only receives events during specific windows or on demand.

Never conclude the producer is broken just because a newly started listener has not received its first record yet. Check assignments, producer schedule, and initial-idle configuration for your library version.

## 6. Listening to idle events in Spring

You can use Spring **`@EventListener`** to receive application events.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventLogger {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Kafka listener idle: listener={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

**`getIdleTime()`** represents the idle duration reported by the framework event, typically in milliseconds. It should not be interpreted as "time since the last successful business commit".

An application may have multiple Kafka listeners. Event listeners should filter by listener ID, consumer group, source container, or relevant metadata before applying policies to a specific topic.

Example:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    if (!event.getListenerId().startsWith("orders-listener")) {
        return;
    }

    idleMetrics.recordIdleObservation(
        "orders-listener",
        event.getIdleTime()
    );
}
~~~

With concurrent containers, the listener ID in the event may reflect child container identity per Spring Kafka's naming convention; prefix filtering in the example is just one application policy. In production, verify exact naming/identity rules for your version and container setup.

## 7. ListenerContainerNoLongerIdleEvent

When an idle listener starts receiving data again, **ListenerContainerNoLongerIdleEvent** identifies the recovery point:

~~~java
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;

@EventListener
public void onActiveAgain(ListenerContainerNoLongerIdleEvent event) {
    log.info(
        "Kafka listener received data after idle: listener={}",
        event.getListenerId()
    );
}
~~~

This event can be used to:

- Close a "no messages" incident if other conditions have also recovered.
- Measure the duration between idle detection and message resumption.
- Observe changes in data cadence after a rollout or producer outage.
- Confirm a listener received data after startup.

However, **NoLongerIdleEvent does not prove the listener completed business processing**. The record may have just been delivered while the downstream service called by the listener still fails. Pair it with listener success counters or processed-event metrics when measuring business progress.

### 7.1. Idle events can repeat

Suppose a listener receives no records for 5 minutes with `idleEventInterval` set to 30 seconds. The framework can emit multiple `ListenerContainerIdleEvent` instances during that single quiet period.

Do not create a new ticket for every idle event. Use a state machine:

~~~text
ACTIVE
   |
   | first idle event of the idle session
   v
IDLE_OPEN
   |
   +-- subsequent idle events -> update idle age/metric
   |
   +-- no-longer-idle -> close idle session
   |
   +-- container stop/rebalance -> close/transition state per lifecycle
~~~

Incidents should be keyed by listener/consumer/assignment and state, rather than per event callback.

## 8. Tracking per-partition idle

A consumer may own multiple partitions where only one partition receives new data. The container keeps receiving records continuously, so **container-level idle fails to detect a single unusually silent partition**.

Example:

~~~text
orders.events:

partition 0 -> 100 records/s  -> ACTIVE
partition 1 ->   0 records/s  -> IDLE
partition 2 ->  30 records/s  -> ACTIVE

Overall container receives records continuously
        |
        v
ListenerContainerIdleEvent may not reflect P1 alone
~~~

Spring Kafka supports per-partition idle events in applicable versions, including **ListenerContainerPartitionIdleEvent** and **ListenerContainerPartitionNoLongerIdleEvent**. You can configure the check interval via **idlePartitionEventInterval** on container properties where the API is present.

Example:

~~~java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(60_000L);
~~~

Points to keep in mind:

- A partition with no data can be completely normal for low-activity keys.
- A newly assigned partition may never have received a record yet.
- During rebalances, owner identity and observation start time change.
- Listener-level idle age is not the same as maximum partition idle age.
- With thousands of partitions, per-partition metrics require cardinality and lifecycle management.

For high-traffic topics, partition-level idle can help catch faulty producer partitioners, silent business shards, or traffic skew.

## 9. Idle does not mean non-responsive consumer

A common mistake is treating container idle events and non-responsive consumer events as the same alert.

**ListenerContainerIdleEvent** means no records were delivered to the listener during the observation window. Polling may still be running normally.

**NonResponsiveConsumerEvent** is emitted when Spring Kafka's monitor detects that a consumer has not completed a poll or made poll progress within the configured threshold. It is an indicator worth investigating around threads or networking, not automatic proof that the broker is down.

~~~text
Scenario A: empty topic
  poll() -> 0 records
  poll() -> 0 records
  poll() -> 0 records
  => idle, yet poll remains responsive

Scenario B: consumer poll thread is blocked
  poll() starts
       |
       +-- Does not return within expected time
       |
       v
  Monitor detects non-responsive
~~~

Therefore:

- Idle events usually carry **INFO/WARNING severity depending on business context**.
- Non-responsive events can carry **WARNING/CRITICAL severity depending on poll stall duration**.
- Both must be correlated with state, lag, assignment, pause, and broker health.

## 10. Configuring NonResponsiveConsumerEvent

Spring Kafka includes a monitor that periodically checks poll progress. Related properties typically include:

- **pollTimeout:** maximum wait time for a single poll call configured by the container.
- **noPollThreshold:** multiplier relative to `pollTimeout` defining suspiciously long gaps without poll progress.
- **monitorInterval:** interval at which the monitor task checks the condition.

Example:

~~~java
var props = factory.getContainerProperties();

// Poll timeout: 3 seconds.
props.setPollTimeout(3_000L);

// Conceptual threshold: time since last poll
// exceeding 3x poll timeout may trigger an alert.
props.setNoPollThreshold(3.0f);

// Monitor checks every 10 seconds.
props.setMonitorInterval(10);
~~~

This example illustrates APIs present in supported Spring Kafka versions. Values like 3.0 and 10 seconds are not mandatory defaults or SLA formulas; check exact parameter types and conditions in the Javadoc for your deployed version.

Actual emission time depends on the **monitor cycle** and thread state. If the threshold equals 9 seconds while the monitor runs every 10 seconds, the event can appear later than the 9-second mark; do not treat the monitor timer as a real-time clock.

### 10.1. Listening to NonResponsiveConsumerEvent

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.warn(
        "Kafka consumer may be non-responsive: listener={}, msSincePoll={}",
        event.getListenerId(),
        event.getTimeSinceLastPoll()
    );

    // Only record metrics / request investigation.
    // Do not unconditionally restart the listener here.
}
~~~

Do not automatically stop and restart the container every time this event arrives. If the cause is a network outage, broker failover, or a deadlocked thread, repeated restarts can trigger rebalance storms, duplicates, and make root-cause analysis harder.

## 11. Why can a consumer become non-responsive?

Common root causes:

| Cause | Symptoms | Investigation action |
|---|---|---|
| Blocked poll / slow network | Non-responsive event, network timeouts, broker errors | Check broker/connection/client logs |
| Listener processing too slow | Rising processing latency, poll not returning | Measure listener, HTTP/DB timeouts, batch size |
| GC stop-the-world | Large JVM pauses, monitor timer may also slip | Inspect GC logs, heap, CPU |
| Thread starvation | Consumer thread fails to get scheduled promptly | Thread dump, CPU throttling, executor contention |
| Synchronized lock/deadlock | Thread stuck BLOCKED/WAITING | Thread dump, lock graph |
| Prolonged blocking retries | Error handler backoff and retry attempts climb | Inspect BackOff, listener exceptions |
| Lifecycle shutdown/rebalance | Container stopping, assignments changing | Inspect lifecycle/rebalance events |
| Consumer API called from wrong thread | IllegalStateException/concurrent access | Use container APIs instead of raw KafkaConsumer |

A non-responsive event is a **symptom**. It does not identify the root cause and does not mean every partition in the group lost data.

## 12. Configuring idle and non-responsive in the same factory

Illustrative factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    var props = factory.getContainerProperties();

    // Detect container having no messages.
    props.setIdleEventInterval(30_000L);

    // Detect individual partitions having no messages.
    props.setIdlePartitionEventInterval(60_000L);

    // Observe ability to continue polling.
    props.setPollTimeout(3_000L);
    props.setNoPollThreshold(3.0f);
    props.setMonitorInterval(10);

    return factory;
}
~~~

Separate alerting policies:

- 30-second container idle: record metric and evaluate against expected traffic.
- 60-second partition idle: check producer traffic on that partition.
- Non-responsive beyond monitor threshold: investigate poll/consumer threads and connectivity.

Never assign all three the same severity or connect them to the same automatic container-restart script. Their semantics are fundamentally different.

## 13. Event listeners should do lightweight work

Spring application events in a Kafka listener container may be published from a consumer/container-related thread by default. If `@EventListener` performs long blocking operations, the observability logic itself can slow down the consumer.

Avoid:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    // Do not call a synchronous HTTP monitoring endpoint
    // and block for seconds directly inside the event callback.
    incidentApi.createTicketSynchronously(event);
}
~~~

Instead:

1. Update fast in-memory gauges/counters.
2. Emit rate-limited logs.
3. If ticket creation is needed, push sanitized events onto a bounded queue.
4. Let a separate worker call the alerting system with timeouts/retries.
5. If the queue fills up, increment a dropped-notifications metric; never block the poll thread indefinitely.

If the application configures an **asynchronous `ApplicationEventMulticaster`**, event callbacks can run on a different thread. In that case, **never use the `Consumer` object from the event to call `KafkaConsumer` APIs from a foreign thread**; `KafkaConsumer` does not support arbitrary concurrent access. Container operations must go through safe lifecycle-management APIs.

## 14. Building a tracker for last message receipt time

Idle events are useful for threshold detection, but many systems also want a dashboard showing **seconds since last message**. You can instrument the listener to record both record delivery time and successful processing time separately.

Example:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class MessageProgressTracker {

    private final AtomicLong lastDeliveredNanos =
        new AtomicLong(0L);

    private final AtomicLong lastSucceededNanos =
        new AtomicLong(0L);

    public void onDelivered() {
        lastDeliveredNanos.set(System.nanoTime());
    }

    public void onSucceeded() {
        lastSucceededNanos.set(System.nanoTime());
    }

    public double secondsSinceLastDelivered() {
        return elapsedSeconds(lastDeliveredNanos.get());
    }

    public double secondsSinceLastSucceeded() {
        return elapsedSeconds(lastSucceededNanos.get());
    }

    private double elapsedSeconds(long mark) {
        if (mark == 0L) {
            return -1.0; // No event observed yet.
        }
        long elapsed = System.nanoTime() - mark;
        return Math.max(0L, elapsed) / 1_000_000_000.0;
    }
}
~~~

**`System.nanoTime()`** is well suited for measuring elapsed duration within the same JVM. Do not persist `nanoTime` across restarts; if you need audit timestamps across instances, also store `Instant.now()` or a UTC `Clock`.

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    progressTracker.onDelivered();

    orderService.process(event);

    progressTracker.onSucceeded();
}
~~~

The two metrics must remain separate:

- **lastDelivered:** the most recent time the listener started receiving a record.
- **lastSucceeded:** the most recent time business logic completed without throwing an exception.

If a listener receives 100 records/s and every single one fails, `lastDelivered` age stays tiny while `lastSucceeded` age climbs. Looking at idle events alone will miss this business failure completely.

### 14.1. Limitations of in-memory trackers

A bean-level tracker typically aggregates across all partitions handled by that listener instance. During a rebalance, it does not automatically know which partitions the instance lost; after a restart, it has no prior data.

If you need to detect a silent shard:

- Maintain state per `TopicPartition` with an assignment epoch.
- Clear/close state upon revoke or loss.
- Keep separate clocks/timestamps per partition.
- Do not treat a partition that has never seen a message as proof of producer failure if key-based traffic is sparse.

## 15. Micrometer gauge for silence duration

With Spring Boot and Micrometer integration, you can export custom metrics:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public void registerProgressMetrics(
        MeterRegistry registry,
        MessageProgressTracker tracker) {

    Gauge.builder(
        "app.kafka.listener.since.last.delivered.seconds",
        tracker,
        MessageProgressTracker::secondsSinceLastDelivered
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.listener.since.last.success.seconds",
        tracker,
        MessageProgressTracker::secondsSinceLastSucceeded
    )
    .tag("listener_id", "orders-listener")
    .register(registry);
}
~~~

These metric names are **custom conventions**, not built-in metrics available across every Spring Kafka version. When the tracker has never seen a record, the example returns `-1` instead of reporting a bogus huge duration; dashboards should display **`NEVER_SEEN`** distinctly.

A gauge is not a tool for verifying offset commits. Pair it with error handler, offset commit, and end-to-end processing metrics.

## 16. Measuring continuous idle time with a state machine

Because idle events can repeat during a single quiet period, measuring **the length of an idle session** requires tracking transitions rather than counting callbacks.

~~~text
UNKNOWN / STARTUP
       |
       | receives message
       v
ACTIVE
       |
       | exceeds idle threshold
       v
IDLE(startAt, reason=NO_MESSAGES)
       |
       +-- subsequent idle events:
       |      update currentIdleSeconds
       |
       +-- no-longer-idle event:
       |      completedIdleDuration
       |      return to ACTIVE
       |
       +-- stop/revoke:
              close state with specific endReason
~~~

Note: if you only start a timer when the **first idle event** arrives, you are measuring "time since the framework detected idle", **not** the full elapsed time since the last record. To report true silence age, use the last record/delivery timestamp or the `idleTime` supplied by the event to derive the exact meaning.

Example:

~~~text
Last record received: t=00
idleEventInterval: 30s
First idle event: t≈30
Second idle event: t≈60
Record resumed: t=90

Silence duration ≈ 90s
Time since first idle alert ≈ 60s
~~~

Both quantities are useful, serving different purposes. When defining SLOs or alerts, document the exact definition.

## 17. Container idle vs partition idle

If a container has `concurrency=3`, there can be three consumer threads:

~~~text
orders-listener
    |
    +-- child-0 -> P0, P3 -> P0 receives records
    |
    +-- child-1 -> P1, P4 -> receives no records
    |
    +-- child-2 -> P2, P5 -> P5 receives records
~~~

An idle event from `child-1` does not mean every listener instance in the consumer group is idle. Conversely, high aggregate throughput across the group can mask a single partition that has received no messages for too long.

Metric layers you may need:

- **Container-level:** which child consumer has been idle for how long.
- **Listener-level:** whether at least one consumer is receiving records.
- **Partition-level:** how long each partition has gone without records.
- **Group-level:** total progress and lag across all partitions.
- **Business-level:** time since last successful event for a flow or event type.

Never mix these layers under a generic metric named "Kafka idle duration" without specifying the aggregation.

## 18. When no partitions are assigned

A `@KafkaListener` can initialize successfully without owning any partitions:

- The consumer group has more members than partitions.
- The assignor has not finished rebalancing.
- A pattern subscription does not match the intended topic.
- The topic has not been created yet or metadata is unavailable.
- The container is stopped, configured with `autoStartup=false`, or a different listener ID is being observed.

Example:

~~~text
Topic has 3 partitions
Consumer group has 5 active consumers

=> Up to 2 consumers may receive no partition assignment
=> Those consumers receive no messages
=> Not necessarily a fault
~~~

A container with zero assignments cannot be evaluated the same way as a container holding 3 partitions with heavy lag. Add **`assigned_partition_count`** to dashboards and alert rules.

During rebalances, temporarily lacking an assignment can be a transient state. Alerts should include an appropriate grace window rather than opening an incident on every rollout.

## 19. Checking consumer lag and progress

To distinguish normal idle from abnormal message absence, compare committed offsets with log end offsets:

~~~text
Consumer group committed offset: 1200
Partition log end offset:       1200

lag = 0
=> no uncommitted backlog under that offset measurement
~~~

Another case:

~~~text
Consumer group committed offset: 1200
Partition log end offset:       1250

lag = 50
=> data exists that the group has not committed yet
~~~

If a listener stays idle for a long time while lag is high, investigate. However:

- Lag can reflect records currently being processed but not yet committed.
- Kafka transactions with `read_committed` can cause LSO to cap readable data below LEO.
- Topic retention and offset reset policies affect replayability.
- A paused partition can keep lag climbing even while the consumer remains healthy.
- Group-level lag does not prove every member must receive messages.

Therefore, **idle + lag + assignment + paused/running + poll responsiveness** is a far stronger diagnostic than any single metric.

## 20. Kafka CLI does not show Spring idle events

Kafka provides a consumer group inspection tool:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-worker \
  --describe
~~~

Example output:

~~~text
TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders.events  0          1200            1200            0
orders.events  1           550             650          100
orders.events  2           920             920            0
~~~

The CLI shows offset/lag status and can display assignment details depending on version/tool output. It **does not know** whether the Spring listener emitted `ListenerContainerIdleEvent` and does not know whether business operations inside the listener succeeded.

To diagnose, combine:

- CLI group membership/offsets.
- Spring listener/container events and lifecycle state.
- Producer publish rates / topic ingress.
- Listener success/failure metrics.
- JVM thread dumps and Kafka client logs when poll non-responsiveness is suspected.

## 21. A paused container can look idle

When a container is paused:

~~~text
Downstream overloaded
        |
        v
PauseService calls container.pause()
        |
        v
Consumer may keep polling to maintain membership
        |
        v
Listener receives no new records
        |
        v
Time since last message keeps increasing
~~~

That does not mean the consumer failed. It may be adhering to backpressure policy. Yet if the pause is forgotten or never resumed after downstream recovers, the system can remain stalled longer than intended.

Therefore, when an idle event fires, check:

1. **`isPauseRequested()`**: did the application request a pause?
2. **`isConsumerPaused()`**: has the pause taken effect?
3. Are there partition-specific pauses?
4. Who requested the pause, why, and when?
5. Have resume conditions been met?

Never call `resume()` solely because the listener is idle if the pause protects a degraded dependency. Base decisions on system health and pause-request ownership.

## 22. A poison record can stall business progress

A listener may receive a failing record and retry it repeatedly. How this looks in metrics depends on:

- Is the listener method being re-invoked?
- Is error-handler retry blocking or non-blocking?
- Did the record fail deserialization before reaching the listener?
- Does the consumer keep polling during backoff?
- Has the record been routed to a DLT or retry topic yet?

Example:

~~~text
Topic P0 offset 150 is a poison record
        |
        v
Listener/Deserializer fails
        |
        v
ErrorHandler retries repeatedly
        |
        v
No business success
        |
        v
Offset stalls / lag grows
~~~

A "time since last success" metric will climb, while "time since last delivery" may keep resetting as the record is redelivered. Not every failure scenario emits idle events.

If a single offset appears in logs hundreds of times, classify transient vs permanent errors, inspect error handler/BackOff, and verify DLT recovery instead of treating it as "topic has no messages".

## 23. No messages due to pre-listener deserialization failures

Kafka deserializers run during `Consumer.poll()`, before `@KafkaListener` receives an object. If the payload is malformed and the deserializer throws an exception, the listener may never be called.

In Spring Kafka, **`ErrorHandlingDeserializer`** places deserialization failure details into headers so the container/error handler gets a chance to handle the record.

Without proper configuration, a poison pill can cause the same offset to fail repeatedly while listener invocation counters never increment. Inspect:

- Errors from `KafkaConsumer.poll()` and deserializers.
- `ErrorHandlingDeserializer` setup for keys/values.
- `DefaultErrorHandler` classification.
- `DeadLetterPublishingRecoverer` and whether the serializer supports raw bytes.
- DLT publish failures, offset commits, and record replays.

Never assume the producer stopped sending just because `@KafkaListener` isn't invoked. Inspect logs at the poll/deserialization boundary.

## 24. No messages due to read_committed and open transactions

A Kafka consumer with **`isolation.level=read_committed`** only reads committed transactional records and non-transactional records per protocol. If a transaction remains open on a partition, the **Last Stable Offset (LSO)** can trail behind the Log End Offset (LEO).

Example:

~~~text
Topic partition log:
  offset 200: committed
  offset 201: transaction T still open
  offset 202: another record written after T

LEO advances while LSO remains stuck at unsettled boundary T
        |
        v
read_committed consumer cannot read past LSO
        |
        v
Listener may go idle even as log end offset climbs
~~~

Once transaction T commits or aborts, LSO can advance. If you only inspect `LEO - committed offset`, you might falsely report "consumer stopped polling" while it is strictly obeying isolation semantics.

Check transaction timeouts, producer commit/abort rates, broker coordinator health, isolation level, and how your exporter defines offsets/lag.

## 25. When should you alert on idle?

Never apply a blanket "no messages in 30 seconds" alert to every topic.

An alert should account for:

- Does the topic have a data-production schedule?
- Is there an SLA guaranteeing at least one event within an interval?
- Is producer ingress actually greater than 0?
- Does the consumer own partitions?
- Does the group have lag?
- Is the container paused or stopped by request?
- Is a deployment/rebalance underway?
- Are there poll/deserialization/recovery errors?
- How long ago did the listener last succeed in business processing?

Example policy:

| Stream | Expectation | Suggested alert |
|---|---|---|
| Continuous payment events | Data every minute | Prolonged idle + producer ingress > 0 + lag > 0 |
| Daily settlement | One batch per day | Batch not received past expected deadline |
| Rare admin command | May stay silent for days | Do not alert on idle alone; monitor container health separately |
| Retry topic | Records arrive only on errors | Do not alert on idle; alert on retry backlog/oldest age |
| DLT | Records only during recovery | Do not alert on DLT idle; alert on DLT publish failures and backlog |

**An idle event is an observability signal, not a universal SLO for every consumer.**

## 26. Synthetic heartbeats and end-to-end checks

For pipelines requiring continuous proof of message delivery capability, you can design a **heartbeat event** or synthetic probe with a dedicated ID, sent periodically by a producer and processed by the consumer.

~~~text
Heartbeat producer
       |
       v
Kafka topic / partition
       |
       v
Spring Kafka consumer
       |
       v
Record heartbeatId, sentAt, receivedAt, processedAt
       |
       v
End-to-end latency dashboard and missing-heartbeat alert
~~~

Heartbeats must be designed carefully:

- Do not mix with business commands if schemas or ordering forbid it.
- Know which partition heartbeats go to; a heartbeat on one partition does not prove all partitions are healthy.
- Record `sentAt`/`receivedAt`/`processedAt` to separate producer delay from consumer delay.
- Do not subtract timestamps from machines with large clock skew to compute exact elapsed durations without accounting for skew.
- Heartbeats do not replace Kafka broker, consumer group, and business-processing monitoring.

A synthetic heartbeat is a helpful addition when **normal silence** is indistinguishable from a **dead producer**.

## 27. Tracking distinct silence timestamps

A reliability system often needs multiple timestamps:

| Timestamp/duration | Definition | Purpose |
|---|---|---|
| `lastProducedAt` | Most recent time producer confirmed event publish | Detect producer stopping writes |
| `lastFetchedAt` | Most recent time consumer poll received data | Detect missing input |
| `lastDeliveredAt` | Most recent time listener was invoked | Detect listener not receiving records |
| `lastSucceededAt` | Most recent time business logic completed | Detect continuous processing failures |
| `lastCommittedAt` | Most recent time group offset progress was recorded | Detect stalled commits |
| `lastRebalanceAt` | Most recent time assignment changed | Distinguish silence due to rebalances |
| `idleStartedAt` | Timestamp when container was marked idle | Measure idle session duration |
| `nonResponsiveDetectedAt` | Timestamp when monitor detected poll stall | Investigate threads/polling |

These timestamps may come from different instrumentation sources. Lumping them under a single "last message time" label will mislead on-call engineers.

To measure **elapsed duration within one JVM**, use `System.nanoTime()`. For auditing and correlation across instances, record UTC timestamps and account for possible clock skew.

## 28. Metrics and dashboards

A dashboard for the Idle and Non-Responsive chapter can include:

**Container state**

- Running/stopping/stopped.
- Assigned partition count.
- Pause requested/effective status.
- Last rebalance age.

**Traffic and processing**

- Records fetched/delivered per second.
- Listener success/failure rate.
- Seconds since last delivered message.
- Seconds since last successful processing.
- Lag and oldest record age per partition.

**Idle behavior**

- Idle event count.
- Current idle age.
- Completed idle interval duration.
- No-longer-idle event count.
- Partition idle count and max partition idle age.

**Poll responsiveness**

- Non-responsive event count.
- Time since last poll from appropriate client/container metrics.
- Poll latency and request latency.
- `max.poll.interval.ms` violations, rebalance count.
- Thread/GC health and blocked time.

**Recovery**

- Retry attempts/exhausted.
- Deserialization failures.
- DLT publish success/failure.
- Container restarts and manual interventions.

Spring Kafka does not emit all of these metrics out of the box. Some come from Kafka client metrics, Micrometer observations, and broker/consumer-group monitoring; metrics such as `lastSucceededAt` or `currentIdleAge` typically require application instrumentation.

## 29. Prometheus: multi-condition alert example

Suppose the application exports custom metrics:

- `app_kafka_listener_since_last_delivered_seconds`.
- `app_kafka_listener_running`.
- `app_kafka_listener_paused`.
- `app_kafka_listener_assigned_partitions`.
- `kafka_consumergroup_lag` from a suitable exporter.

Conceptual alert:

~~~promql
(
  app_kafka_listener_since_last_delivered_seconds > 120
)
and on (listener_id)
(
  app_kafka_listener_running == 1
)
and on (listener_id)
(
  app_kafka_listener_paused == 0
)
~~~

This is **illustrative PromQL based on custom metrics**. In real systems, exporter labels and metric semantics must be aligned so joins work; you may need group labels, `group_left`, or recording rules.

A stronger alert should also check:

- Active producer traffic or significant backlog exists.
- Not inside a startup/rebalance grace window.
- Consumer holds partition assignments.
- No maintenance suppression is active.

Never trigger a critical page purely from an idle-age gauge on a low-traffic topic.

## 30. Never put event payloads or IDs into metric labels

In Prometheus/Micrometer, high-cardinality labels multiply time series, hurting performance and storage costs.

Suitable labels:

- `service`.
- `listener_id`.
- `consumer_group`.
- `topic`.
- `exception_category`.
- `state`.

Labels to evaluate carefully:

- `partition` (can be numerous; keep bounded).
- `client_id`/`instance_id` (acceptable if cardinality is controlled).

Never include:

- `eventId`.
- `orderId`.
- `userId`.
- raw exception messages.
- full Kafka keys or payloads.

Event IDs and offsets belong in logs/traces. When rebalances change assignments, remove or close per-partition metrics on the old owner to avoid stale series making dashboards report a partition as idle on an instance that no longer owns it.

## 31. Operating via @EventListener: avoid drastic actions

An anti-pattern:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    MessageListenerContainer container =
        registry.getListenerContainer(event.getListenerId());

    // Do not restart immediately solely due to an idle event.
    container.stop();
    container.start();
}
~~~

Problems:

- The topic may simply be empty; restarting will not conjure messages.
- Stop/start churns consumer group assignments.
- If multiple instances share this policy, it can cause a rebalance storm.
- Pending offsets and in-flight work may be disrupted.
- The root cause in the producer, Schema Registry, or downstream dependency remains unaddressed.

Instead:

1. Record the idle age.
2. Inspect running, paused, assignment, and lag states.
3. Distinguish normal idle from non-responsive poll.
4. Trigger automated recovery only with concrete evidence and rate-limited retries.
5. Alert operators when conditions breach SLOs.

If a genuinely wedged container must be restarted, use a supervisor with a state machine, rate limiting, producer/transaction lifecycle checks, and idempotency—never call synchronous stop/start inside a listener event callback.

## 32. Runbook: listener has no messages and lag is 0

### Step 1: Determine if it is a low-traffic topic

Inspect producer schedules, publish rates, hourly/daily event volumes, and input SLAs. A topic can be completely quiet while the entire system is healthy.

### Step 2: Check subscription

- Is the listener subscribed to the right topic or topic pattern?
- Does the Group ID match the environment?
- Does the topic exist with the expected partitions?
- Does the consumer have assigned partitions?

### Step 3: Check state

Is the container running or stopped? Is it paused for backpressure? Were there recent assignments or rebalances?

### Step 4: Verify the producer

Inspect producer send success/error metrics, topic ingress rate, and authorization/serializer errors. If the producer has stopped, the consumer is simply reflecting upstream silence.

### Step 5: Evaluate alerting

If there is no data-arrival SLA, keep idle metrics informational. If an expected periodic heartbeat exists, check the end-to-end heartbeat signal and open an incident if the deadline passes.

## 33. Runbook: listener is idle yet lag is large

This usually warrants immediate investigation because uncommitted data exists for the group.

1. Inspect lag per partition; identify affected partitions.
2. Check consumer assignments and group rebalances.
3. Check `isPauseRequested()`/`isConsumerPaused()` and partition pauses.
4. Check poll responsiveness, non-responsive events, and thread dumps.
5. Check listener processing latency, retries/backoff, and errors.
6. Check for deserialization/poison records before `@KafkaListener`.
7. If `isolation=read_committed`, inspect open transactions and LSO.
8. Check Kafka ACLs, broker/coordinator health, and network errors.
9. Never reset offsets or force-commit before understanding unprocessed data.
10. After remediation, verify record success, committed offsets, and lag dropping.

If a partition is intentionally paused, do not force a resume while downstream is unhealthy just to make lag drop. Balance backpressure against retention and backlog budgets.

## 34. Runbook: NonResponsiveConsumerEvent increasing

### Step 1: Inspect threads and JVM

Capture a thread dump where permitted. Look for Kafka consumer threads `BLOCKED` or `WAITING` on locks, HTTP/database calls, producer sends, polls, or retry handlers.

### Step 2: Inspect timeouts

- `pollTimeout`.
- `noPollThreshold`.
- `monitorInterval`.
- `max.poll.interval.ms`.
- HTTP connect/read timeouts.
- Database statement/lock timeouts.

If the monitor threshold is smaller than normal legitimate poll or processing latency, detection may be overly sensitive. Never silence alerts by raising timeouts infinitely without measuring reality.

### Step 3: Check Kafka infrastructure

Broker request latency, disconnects, authentication, coordinator changes, leader/ISR, and networking.

### Step 4: Decide whether intervention is needed

If the consumer self-recovers and resumes polling, record the duration and error source. If threads are genuinely wedged, consider rate-limited recovery, guard duplicate side effects via idempotency, and avoid restarting the whole group simultaneously.

### Step 5: Verify aftermath

Inspect uncommitted offsets, listener outputs, DLT/retry backlogs, and business side effects after container recovery.

## 35. Runbook: container paused and forgotten

Having no messages can result from a legitimate pause request that was never resumed.

Check:

- Pause reason, requester, and timestamp.
- Whether the downstream circuit breaker or queue is now healthy.
- Whether low-watermark resume conditions are satisfied.
- Whether a manual-maintenance reason is still active.
- Whether the container still owns those partitions or a rebalance occurred.
- Whether a requested resume actually took effect.
- Current retention window and oldest record age.

Resuming should be coordinated with subsequent throughput monitoring. If a large backlog accumulated, throttle or scale capacity appropriately so downstream is not overwhelmed when queued records flood back in.

## 36. Testing detection of containers with no messages

An integration test suite should cover these scenarios:

### 36.1. Empty topic

Start a listener on an empty topic and wait past the interval. Verify `ListenerContainerIdleEvent` fires per policy while the container remains running without automatic restarts.

### 36.2. Data arrives after idle

After receiving an idle event, publish a valid record. Verify the listener receives the data and `ListenerContainerNoLongerIdleEvent` is observed if supported by the version/container.

### 36.3. Repeated idle events

Keep the topic empty across multiple intervals. Verify the tracker does not open multiple incidents or idle sessions for a single silent period.

### 36.4. Partition idle

Create a multi-partition topic and publish to only one partition. Verify partition-level idle instrumentation does not falsely report the whole container idle when other partitions have traffic.

### 36.5. Paused container

Call `pause()`, publish new records, and verify pause state and lag. Do not expect the listener to receive records on paused partitions until resumed.

### 36.6. Unassigned consumer

Run a group with more consumers than partitions. Verify an unassigned consumer is not classified as faulty solely for receiving no messages.

### 36.7. Blocked poll thread

In a controlled test environment, stall consumer poll progress or run an operation exceeding the threshold. Observe `NonResponsiveConsumerEvent` and verify no restart loop occurs.

### 36.8. Retries and poison records

Send records that fail deserialization or throw listener exceptions. Verify metrics distinguish "no delivered messages" from "delivered but failing", and verify error handling/recovery processes records per policy.

### 36.9. Rebalance while idle

Add/remove a consumer member. Verify the tracker resets/closes state per assignment epoch and does not leave stale partition idle metrics on the previous owner.

### 36.10. Forced shutdown

Abruptly terminate the JVM in a test. Verify monitoring does not treat a dead process as an infinitely growing idle interval and keeps liveness alerts separate from idle alerts.

Never test by disrupting production topics, shutting down shared brokers, or resetting offsets on live business groups. Use a test Kafka cluster and dedicated containers/consumer groups.

## 37. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating every idle event as a consumer fault | Noisy alerts and unnecessary restarts | Factor in traffic expectations, lag, and assignments |
| Confusing idle with non-responsive poll | Misdiagnosed root cause | Use `NonResponsiveConsumerEvent` and poll metrics separately |
| Looking only at `running=true` | Misses paused, unassigned, and poll-blocked states | Combine lifecycle, pause, assignment, and poll signals |
| Leaving `idleEventInterval` unset | No events emitted at desired threshold | Configure and verify on the actual factory |
| Counting each idle event as a new incident | Many tickets for a single idle stretch | State machine, deduplication, rate limiting |
| Aggregating one child's idle to whole group | Misreported scope | Use child/partition/group-level metrics |
| Looking only at lag = 0 | Misses stopped producers | Compare expected producer rate/heartbeats |
| Looking only at high lag | Fails to distinguish paused, poison, LSO | Inspect root cause and commit progress |
| Using `lastDelivered` instead of `lastSucceeded` | Misses continuously failing listeners | Track both timestamps independently |
| Restarting in `@EventListener` on every idle | Rebalance storms/duplicates | Recover only after diagnosis and with rate limiting |
| Calling slow sync HTTP in event handler | Blocks consumer/event thread | Fast metric updates, async bounded notifications |
| Using `KafkaConsumer` from async event thread | Violates thread safety | Control via container APIs |
| Not closing idle state on revoke/stop | Stale gauges, false alerts | Lifecycle-aware tracking |
| Alerting rare-event topics like realtime topics | Continuous false positives | Topic-specific SLAs and arrival schedules |
| Not distinguishing startup idle | Immediate alerts before any record ever arrived | Startup grace and never-seen state |
| Using `eventId`/`customerId` metric labels | Cardinality explosion | Put IDs in logs/traces; keep labels bounded |
| Ignoring DLT/deserialization errors | Poison pills mistaken for missing data | `ErrorHandlingDeserializer`/error handler |
| Assuming `read_committed` always reads to LEO | False faults when LSO is held by open transactions | Inspect transaction state and LSO |

## 38. Production checklist

Before deploying container no-message detection:

1. Have you clearly defined whether "no messages" means no fetch, no delivery, or no successful processing?
2. Does the topic have an expected arrival pattern and data SLO?
3. Is `idleEventInterval` configured to the intended value on the actual container factory?
4. Do event listeners properly capture `ListenerContainerIdleEvent` and `NoLongerIdleEvent`?
5. Do you need per-partition idle events rather than container-wide idle alone?
6. Are event IDs/listener IDs handled properly for concurrent child containers?
7. Are repeated idle events deduplicated into a single idle period?
8. Are seconds since last delivered and last successful processing measured separately?
9. When a container is paused, do metrics and alerts recognize the pause reason?
10. Are running, paused, stopped, assigned partition count, and rebalances clearly distinguished?
11. Is a `NonResponsiveConsumerEvent` monitor configured with suitable `pollTimeout`/`noPollThreshold`/`monitorInterval`?
12. Do event handlers avoid blocking I/O and cross-thread `KafkaConsumer` access?
13. Is idle combined with group lag, producer traffic, and oldest unprocessed record age?
14. Are `isolation=read_committed` and potential LSO stalls accounted for?
15. Are deserialization failures, retries/backoff, and DLT publish failures monitored?
16. Are startup grace and never-seen states handled for listeners that have never received data?
17. Are alert policies differentiated across continuous, scheduled, and rare-event topics?
18. Are metric label cardinalities bounded and stale states cleaned up on partition revoke or instance stop?
19. Are runbooks ready for idle+lag=0, idle+lag>0, prolonged pause, and non-responsive polls?
20. Do integration tests cover empty topics, resume, pause, rebalance, poison records, and forced shutdown?

**Conclusion:** Detecting containers with no messages in Spring Kafka goes beyond waiting for a `ListenerContainerIdleEvent`. Idle is the absence of delivered data over a period; non-responsive indicates consumer polling is not progressing as expected; paused/stopped and unassigned states each have distinct operational causes. A reliable system combines **idle events, no-longer-idle events, `NonResponsiveConsumerEvent`, assignment, pause state, lag, producer ingress, and listener success metrics** to determine whether silence is normal or hiding an incident. With proper classification, alerts become actionable, restart loops are avoided, and record recovery stays protected without duplicates or bad offset commits.
