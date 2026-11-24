# Consumer idle time

In a Spring Kafka system, **consumer idle time** can describe how long a listener goes without receiving new records, the fraction of time the consumer spends waiting inside `poll()`, or the elapsed time since the most recent `poll()` call. These three interpretations differ in cause and operational impact. A consumer receiving few records may be completely healthy; a consumer steadily receiving records yet blocking on a database call may be hurtling toward `max.poll.interval.ms` and a rebalance.

The **Consumer idle time** topic belongs under Monitoring and metrics because the goal is measuring the right state, observing the root cause, and then deciding when to alert or intervene. Spring Kafka supports `idleEventInterval` and application events such as `ListenerContainerIdleEvent` and `ListenerContainerNoLongerIdleEvent`. Meanwhile, the Kafka consumer client has metrics around polling and idle ratio. Never lump all of them into a single metric named "idle" and conclude the system is good or bad.

A reliable operational design must answer: is the consumer still polling; are partitions assigned to the consumer; does Kafka have new records; are records paused or blocked by transactions; and is the listener processing received records successfully?

## 1. Three distinct interpretations of consumer idle time

| Concept | What is measured | Practical meaning |
|---|---|---|
| **Listener idle duration** | Time since the container last received/delivered a record to the listener | Detects consumers seeing no records over a period |
| **Poll idle ratio** | Ratio of time the consumer waits in `poll()` versus time spent processing outside `poll()` | Assesses whether the consumer is waiting on data or busy processing |
| **Time since last poll** | Elapsed time since the most recent `KafkaConsumer.poll()` call | Detects blocked consumer threads risking poll interval violations |

For example, a topic receives only one event per hour. The consumer keeps calling `poll()`, returning no new records. `ListenerContainerIdleEvent` fires past the threshold, and `poll-idle-ratio-avg` stays high. Neither signal **proves** the consumer is broken. Conversely, a listener processing a single record for ten minutes may miss firing idle events on schedule because the consumer thread never returns to the poll loop, while time-since-last-poll climbs dangerously.

Therefore, dashboards should separate signals into groups: **consumer availability**, **listener traffic/idle**, **processing latency**, **consumer lag**, and **downstream health**.

## 2. When does listener-container idle occur?

A Kafka listener processing loop typically looks like:

```text
Kafka broker
      |
      v
KafkaConsumer.poll()
      |
      +---- has records ----> @KafkaListener
      |                         |
      |                         v
      |                    process / ack / commit
      |
      +---- no records -----> keep polling
      |
      v
Container tracks elapsed time without records
      |
      +---- exceeds idleEventInterval
                    |
                    v
           ListenerContainerIdleEvent
```

`idleEventInterval` is the threshold the Spring Kafka listener container uses to report that no records arrived for a sustained interval. It **does not make the broker send more data**, does not trigger retries, and does not stop the listener. When data resumes after an idle period, the container can emit `ListenerContainerNoLongerIdleEvent` to signal the idle state ended.

When a `poll()` returns no records, the consumer has not stopped; it can still maintain group membership and keep polling. An idle event milestone is an application-layer signal, not a Kafka protocol error.

## 3. Configuring `idleEventInterval` in Spring Kafka

To receive idle events on a listener factory, configure `ContainerProperties` directly:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties properties = factory.getContainerProperties();
        properties.setIdleEventInterval(60_000L);
        properties.setPollTimeout(1_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`OrderEvent` is only an illustrative data type; the application must provide deserializers, `ConsumerFactory`, and real Kafka connection settings. `60_000L` sets a **60-second** idle threshold, while `pollTimeout=1_000L` bounds a single `poll()` wait to about one second. These two properties are **not equivalent**.

The listener wired to this factory:

```java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void handle(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

Setting `idleEventInterval` on a factory means all containers created by that factory share the same idle policy. If one factory serves multiple listeners with different traffic cadences, consider splitting factories or picking a fitting threshold. Never assume a property applies to a listener just because it sits in another bean not referenced by the annotation.

## 4. Listening for `ListenerContainerIdleEvent`

Spring Kafka publishes idle events via Spring's application event mechanism; a bean can listen with `@EventListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventLogger {

    private static final Logger log = LoggerFactory.getLogger(
            KafkaIdleEventLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime());
    }
}
```

`getIdleTime()` represents the idle duration recorded by the event in milliseconds; `getListenerId()` provides the framework-assigned listener/container identifier. In `ConcurrentMessageListenerContainer`, there are multiple child consumer containers, so the identifier reported by the event may be more detailed than the `@KafkaListener` ID and should be inspected at runtime.

Receiving an idle event should not automatically trigger an incident. If a topic expects no events over weekends, this can be normal telemetry. Likewise, while a listener is intentionally paused, an idle event is insufficient to conclude the producer stopped sending records.

## 5. When data resumes: `ListenerContainerNoLongerIdleEvent`

To know **when idle ends**, also observe the event emitted when the listener receives data again:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaActivityObserver {

    private final ListenerStatusRecorder recorder;

    public KafkaActivityObserver(ListenerStatusRecorder recorder) {
        this.recorder = recorder;
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        recorder.markActive(event.getListenerId());
    }
}
```

`ListenerStatusRecorder` is an application-defined interface/bean storing monitoring state. The *no longer idle* event does not prove the listener succeeded at business side effects: the newly delivered record could throw an exception, enter retries, or go to the DLT. Confirming processing success requires dedicated metrics/ack/transaction outcomes.

For observability systems, pairing idle and no-longer-idle events models an `ACTIVE -> IDLE -> ACTIVE` state transition. Avoid opening a new incident for every repeated idle event, as Spring Kafka can publish idle events periodically while no records arrive.

## 6. Timeline: a consumer with genuinely no traffic

Suppose `idleEventInterval=60_000`, and a Kafka topic receives records only at the start and three minutes later:

```text
t=0s       listener receives record #1
            |
t=30s      consumer keeps polling, no new records yet
            |
t≈60s      ListenerContainerIdleEvent
            |
t≈120s     may emit next idle event
            |
t≈180s     listener receives record #2
            |
            +--> ListenerContainerNoLongerIdleEvent
            |
            v
          listener returns to active state
```

Timestamps marked `≈` are illustrative. Events may fire later than the threshold due to poll cycles, processing duration, scheduling, or how the container tracks idle time. Never build millisecond-exact business deadlines on when a Spring application event fires.

If an application starts up and has never received any record, the container can still be marked idle after the configured interval depending on lifecycle and version properties. Hence **never received**, **idle after last record**, and **stopped/unassigned** should be separated clearly in monitoring.

## 7. Container-wide idle vs. per-partition idle

A consumer can be assigned multiple partitions. If one partition steadily carries records, the container may not be considered idle even if another partition is silent:

```text
Topic orders:

orders-0 --> 20 records/s --> Consumer A
orders-1 -->  0 records/s --> Consumer A
orders-2 -->  2 records/s --> Consumer A

Consumer A still receives records, so the container is not necessarily idle overall.
```

Spring Kafka also supports `idlePartitionEventInterval` to emit events at **per-partition** granularity when you need to observe silence on a specific partition. In supported versions, the corresponding events are `ListenerContainerPartitionIdleEvent` and `ListenerContainerPartitionNoLongerIdleEvent`.

```java
ContainerProperties properties = factory.getContainerProperties();

properties.setIdleEventInterval(120_000L);          // container
properties.setIdlePartitionEventInterval(60_000L); // partition
```

These two event types answer different questions. If the goal is "is the service receiving any records at all?", monitor listener container idle. If the goal is "is partition `orders-1` silent while other partitions stay active?", use partition idle events or per-partition metrics.

When multiple replicas belong to the same group, only the instance currently assigned a partition can observe that partition at the listener-container layer. For a group-wide view, aggregate by `group + topic + partition` alongside assignment/rebalance state and current owner.

## 8. Kafka consumer metric `poll-idle-ratio-avg`

The Kafka client exposes a metric commonly named **`poll-idle-ratio-avg`** in consumer metrics. It represents the fraction of time the consumer spends waiting inside `poll()` versus working on the application side between polls, per the running Kafka client version's definition.

Practical interpretation:

| Approximate value | Common interpretation | What else to check |
|---:|---|---|
| Near `1.0` | Consumer spends most of its time waiting in poll | Are new records arriving? Low-traffic topic or paused consumer? |
| Around `0.5` | Poll wait time and non-poll processing time are roughly balanced | Batch size, throughput, and listener latency |
| Near `0.0` | Consumer is very busy outside poll, or held in processing | Slow listener, downstream latency, time between polls |

This is a **ratio**, not idle milliseconds. `0.9` does not mean the consumer received no records for 900 ms or 90 seconds. A consumer busy processing high traffic can have a low poll-idle ratio while delivering high throughput; that is not necessarily an error. Conversely, a low ratio paired with a high `time-between-poll-max` signals a blocked consumer thread.

Metric names across JMX, Micrometer Kafka client binders, and Prometheus exporters vary by version. Inspect actual meters/series before building dashboards; never assume an exporter emits one fixed string across every cluster.

## 9. `time-between-poll` and `last-poll-seconds-ago`

The Kafka consumer client also provides metrics reflecting `poll()` cadence such as `time-between-poll-avg`, `time-between-poll-max`, or `last-poll-seconds-ago` in supported versions. These metrics are critical when a consumer becomes **unresponsive**, not merely when data is absent.

Example:

```text
Consumer A:
  poll-idle-ratio-avg      0.95
  time-between-poll-max  1.2 s
  lag                    0

Interpretation:
  consumer polls frequently and waits for records, with no visible backlog.

Consumer B:
  poll-idle-ratio-avg      0.01
  time-between-poll-max  280 s
  max.poll.interval.ms   300000
  lag                    rising

Interpretation:
  risk of breaching poll interval due to overly slow listener/downstream processing.
```

Numbers above are illustrative. Understand how each metric is sampled over windows and whether it updates while no poll occurs. Under some conditions, sample-based metrics may not immediately reflect a completely wedged thread. Therefore, combine application logs, thread dumps, and Spring Kafka's non-responsive monitor mechanism.

## 10. Distinguishing idle from `NonResponsiveConsumerEvent`

This is a crucial distinction in **Monitoring and metrics**:

```text
Scenario A — No traffic:
  poll() runs regularly
  no records returned
  may emit ListenerContainerIdleEvent
  group membership stays stable

Scenario B — Wedged listener:
  previous poll() returned records
  listener hangs on HTTP/SQL call
  consumer thread fails to return to poll()
  container monitor may emit NonResponsiveConsumerEvent
  risk of max.poll.interval.ms breach and rebalance
```

Spring Kafka includes non-responsive consumer detection via properties like `monitorInterval`, `noPollThreshold`, and `pollTimeout` on the container depending on version. A non-responsive event warns about **consumer thread/poll progress**, whereas an idle event only reports **no records received**.

A listener stuck processing a record for minutes may never reach periodic idle-event emission code; absence of idle events **does not prove** the consumer thread is healthy. To investigate, correlate `max.poll.interval.ms`, listener duration, heartbeats, rebalances, consumer metrics, and non-responsive events.

## 11. `max.poll.interval.ms` is not an idle interval

Three commonly confused parameters:

| Setting | Unit/context | Function |
|---|---|---|
| `ContainerProperties.idleEventInterval` | ms, Spring Kafka | When to emit a listener idle event |
| `ContainerProperties.pollTimeout` | ms, Spring Kafka/Kafka poll | Maximum time a single `poll()` waits during normal polling |
| `ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG` | ms, Kafka consumer | Maximum interval between `poll()` calls before Kafka deems the consumer stalled |

For instance, `idleEventInterval=30_000` does not mean Kafka rebalances the consumer after 30 seconds without records. As long as the container keeps polling, group membership can stay intact for hours on an empty topic.

Conversely, `max.poll.interval.ms=300000` is not a 5-minute wait before emitting an idle event. It is a consumer liveness/progress bound. If a listener blocks on downstream calls longer than this bound, it risks losing partition assignment, hitting `CommitFailedException`, or triggering redelivery after rebalance.

A healthy system can emit thousands of idle events with zero rebalances; or rebalance constantly due to slow listeners while emitting almost no expected idle events.

## 12. Why consumer idle does not equal zero consumer lag

**Consumer lag** is the distance between a group's committed offset and the appropriate end position of the Kafka log. **Idle time** is how long the container received no records. The two can diverge widely:

| Situation | Idle | Lag | Likely meaning |
|---|---|---|---|
| Topic empty and group caught up | High | Near 0 | Usually normal |
| Producer writing fast yet consumer paused | High | Rising | Intentional backpressure or failed resume |
| Listener processing records very slowly | May not fire on time | Rising | Bottleneck in listener/downstream |
| Producer writes to only one partition | Some partitions idle | Skewed lag | Key skew or uneven partitioning |
| Open transaction holds back LSO | May rise | Depends on how dashboard computes lag | Records not yet visible to `read_committed` consumers |
| Consumer lacks assignments | Do not treat as normal idle for that partition | Inspect group | Member unassigned or rebalancing |

Especially with `isolation.level=read_committed`, the Last Stable Offset (LSO) may stall due to an open transaction. The broker holds records past it, yet the consumer cannot read them yet. An idle event in that case does not mean the producer stopped sending; inspect transaction visibility and log boundaries.

If a downstream outage forces the container to pause, rising lag is expected. Alert on pause duration and oldest record age if needed, but never reset offsets to "clear lag"; resetting forward loses data and resetting backward creates duplicates.

## 13. Idle when a container or partition is paused

In Spring Kafka, `pause()`/`resume()` temporarily control record delivery without necessarily forcing the consumer to leave the group. When a listener container pauses because a downstream API is overloaded, the consumer can keep polling per lifecycle to preserve membership.

```text
Downstream returns 429/503 repeatedly
          |
          v
Controller calls container.pause()
          |
          v
Container receives no more new records
          |
          v
Idle time rises / idle events may fire
          |
          v
This may be an intentional operational state
```

If idle events fire during a pause, do not assume the producer stopped or brokers lost data. Display `PAUSED` state, pause reason, and pause timestamp on dashboards. Some Spring Kafka versions emit pause-related events, yet the most reliable approach is pairing with APIs/metrics from the managing listener container.

Never automatically call `resume()` merely because an idle event arrived: the pause may be driven by a circuit breaker or quota and must stay active until downstream recovers. Multiple pause triggers need clear ownership coordination so one observer does not accidentally unpause an error handler's pause.

## 14. Custom metric: time since most recent record

If operations needs a **continuous gauge** showing seconds since the last record instead of discrete idle events, record activity in the listener and register an application Micrometer gauge.

The example below uses `System.nanoTime()` so elapsed time remains monotonic across wall-clock jumps. Before any record arrives, the gauge returns `NaN` rather than pretending the consumer already processed a record:

```java
import java.util.concurrent.atomic.AtomicLong;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerActivity {

    private final AtomicLong lastRecordNanos = new AtomicLong(-1L);

    public OrderListenerActivity(MeterRegistry registry) {
        Gauge.builder("app.kafka.listener.since_last_record.seconds", this,
                        OrderListenerActivity::secondsSinceLastRecord)
                .description("Seconds since a record entered the orders listener")
                .tag("pipeline", "orders")
                .register(registry);
    }

    public void recordReceived() {
        lastRecordNanos.set(System.nanoTime());
    }

    public double secondsSinceLastRecord() {
        long previous = lastRecordNanos.get();
        if (previous < 0L) {
            return Double.NaN;
        }

        long elapsed = System.nanoTime() - previous;
        return Math.max(0L, elapsed) / 1_000_000_000.0;
    }
}
```

Hook the tracker at the entry of the listener:

```java
@Component
public class OrdersTrackedListener {

    private final OrderListenerActivity activity;
    private final OrderService orderService;

    public OrdersTrackedListener(
            OrderListenerActivity activity,
            OrderService orderService) {
        this.activity = activity;
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersTrackedListener",
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderEvent event) {
        activity.recordReceived();
        orderService.processIdempotently(event);
    }
}
```

**Limitations of this example:** the gauge measures time since a record **entered the listener method**, not time since a record committed on the broker, does not measure per partition, and does not distinguish stopped/unassigned consumers. If deserialization fails before the listener is called, the gauge does not reset even though the Kafka consumer fetched a record. When the listener has never received a record, `NaN` must be handled explicitly on dashboards rather than defaulting to 0.

When multiple child consumers share one bean, this gauge reflects **shared listener-logic idleness**, not each child individually. Tracking per child or partition requires per-assignment state, cleanup after rebalances, and cardinality control.

## 15. Idle duration, processing latency, and business success are three separate metrics

A record might arrive at the listener at `t0`, spend 40 seconds in database processing, and finally fail. If a gauge tracks from listener entry, it resets at `t0`. If a timer measures processing duration, it records ~40 seconds. If a business success counter increments only when transactions complete, it stays unchanged.

```text
t0:    @KafkaListener invoked
       |   -> since_last_record resets
       |
t0+40s: listener throws exception
       |   -> processing timer reflects 40 seconds
       |   -> business_success does not increment
       v
Error handler retries or sends to DLT
```

Never treat time since the last record as "processing latency" or "business wait time." A consumer steadily receiving records has low idle duration yet could be failing every record into the DLT. Conversely, a long-idle consumer may have completed all work with zero errors.

Dashboards should display at least **records received**, **listener processing duration**, **processing outcomes**, **consumer lag**, and **idle/no-longer-idle state**. With DLT/retries, add retry attempts, DLT publish success/failure, and related topic backlogs.

## 16. Accessing metrics from the Kafka consumer client

`KafkaConsumer` has a `metrics()` API for client metrics, yet the Kafka consumer object is **not thread-safe** and is owned by the listener container. Never capture a reference from an event into a singleton for a background scheduler to call `metrics()` and consumer methods from another thread.

Instead, use the Micrometer Kafka client metrics binder, a JMX exporter, or instrumentation provided by your Spring Boot/Kafka client version. When using a binder, verify exact metric groups/names at runtime before writing queries.

Key metric groups to watch:

```text
Consumer poll/progress:
  poll-idle-ratio-avg
  time-between-poll-avg / time-between-poll-max
  last-poll-seconds-ago

Consumer fetch / lag:
  records-consumed-rate
  records-lag-max
  fetch-rate / fetch-latency

Consumer group lifecycle:
  rebalance count/rate
  assigned partitions
  commit rate/failure logs
```

Not every metric exists in every client version and binder. If an expected metric is missing, check which runtime exposes Kafka client metrics and whether exporters filter or rename metrics. Never try to infer poll health solely from a Spring listener timer `spring.kafka.listener`: that timer mainly measures listener execution, not empty-poll wait intervals.

## 17. Alert thresholds must depend on expected traffic

An idle interval that makes sense for a real-time payment topic produces meaningless noise on a topic published only nightly.

| Stream | Expected traffic | How to use idle time |
|---|---|---|
| Real-time payment events | Steady records during processing hours | Alert past SLO threshold after confirming producer/consumer health |
| Hourly batch events | Empty most of the time | Alert only after batch schedule plus grace margin |
| Low-traffic audit topic | No minimum cadence | Observe telemetry; do not auto-page on idle |
| Retry topic | Records appear only on retries | Idle is usually a healthy state |
| DLT | Should rarely receive records | Alert when **DLT grows**, not when idle |
| Heartbeat topic with SLA contract | Producer emits periodic pulses | Idle time helps verify contract compliance |

If the business does not guarantee a minimum traffic floor, you cannot infer an outage from "10 minutes without records." Base alerts on valid producer heartbeats, incoming volume abnormally below baseline, or rising consumer lag paired with low fetch rates.

For business-hours topics, factor schedules, holidays, and timezones into alert evaluation. Firing alerts at 3 a.m. when traffic is normally silent only breeds alert fatigue.

## 18. Combining Micrometer/Prometheus and dashboard design

For the custom gauge in the example, the Prometheus exporter may normalize `app.kafka.listener.since_last_record.seconds` to a name like `app_kafka_listener_since_last_record_seconds` depending on Micrometer/exporter version. To avoid broken queries, verify the exact exported name and tags.

Illustrative PromQL once the gauge name is verified:

```promql
# Track time since last record for the orders pipeline
app_kafka_listener_since_last_record_seconds{pipeline="orders"}
```

When multiple replicas run, each instance exposes its own gauge; decide whether you want **which instance has no records** or **whether the entire pipeline has no records**. Never take `max` across all replicas and declare the whole system idle just because one instance has no assigned partitions or recently restarted.

Never put `event_id`, `order_id`, `offset`, or Kafka keys as tags on gauges or listener timers. Those carry huge cardinality; keep them in structured logs or traces. Better tags are `service`, `pipeline`, `listener`, `group`, and, when genuinely needed, strictly bounded `topic`/`partition`.

A dashboard should place side by side:

```text
Order Kafka pipeline

  Consumer group lag       0 / rising / falling
  Records consumed rate    0 / n records/s
  Listener idle time       seconds since last record
  Poll idle ratio          fraction spent waiting in poll
  Time since last poll     indicator of blocked thread
  Listener p95/p99         processing duration
  Rebalance / pause        lifecycle state
  DLT / retry              recovery status
```

Putting them side by side lets operations distinguish **idle because work finished**, **idle because paused**, **slow due to processing**, and **not receiving data despite broker records**.

## 19. Alert lifecycle: do not report missing traffic when unassigned

A container may be starting, shutting down, paused, or rebalancing. In those states, timers tracking time since the last record or idle states must be read in context.

Example monitoring state diagram:

```text
STARTING
   |
   v
ASSIGNED + ACTIVE
   |
   +---- no records past threshold -------> ASSIGNED + IDLE
   |                                           |
   |                                      new record arrives
   |                                           |
   <-------------------------------------------+
   |
   +---- intentional pause ----------------> PAUSED
   |
   +---- partition revoked ----------------> REBALANCING / UNASSIGNED
   |
   +---- stop -----------------------------> STOPPED
```

Do not retain stale per-partition idle state on instance A forever after the partition moved to instance B. If tracking per partition, use revoke/assigned callbacks or lifecycle events to clear stale state and track the current owner. In multi-replica groups, central dashboards should aggregate by active assignment rather than summing every idle event emitted by every replica.

`ListenerContainerIdleEvent` is not the ultimate consumer **liveness** signal. If a JVM is killed or crashes, Spring application events may not fire; readiness/liveness probes, instance heartbeats, and consumer group monitoring must be designed independently.

## 20. Common operational failures

| Symptom | Possible cause | Investigation path |
|---|---|---|
| Idle events fire on a healthy topic | Sparse traffic or container assigned low-traffic partitions | Check expected traffic, assignments, and producer rate |
| No idle event past threshold | Listener uses another factory, `idleEventInterval` unset, consumer blocked, or event listener unregistered | Check bean wiring, poll lifecycle, and event multicaster |
| Repeated idle events create multiple incidents | Idle state persists and events emit periodically | Use state machines/alert dedup per listener or partition |
| Consumer lag rises while idle events fire | Consumer paused, missing assignments, blocked fetches, or transaction LSO | Check pause, group, lag, broker/producer, and isolation |
| No records received yet `poll-idle-ratio-avg` is high | Consumer waiting in poll due to sparse data | Confirm whether new data is genuinely expected |
| Consumer rebalances on poll timeout | Slow listener, `time-between-poll-max` near limit | Check downstream timeouts, batch size, and `max.poll.interval.ms` |
| Gauges stay high after listener stops | Custom gauge does not follow lifecycle/assignments | Clear or mark inactive on container stop; never treat stale metrics as live |
| `NoLongerIdleEvent` fires yet business fails | Record delivered yet listener throws | Watch error handlers, retry/DLT, and business success |
| Only one partition silent while container stays active | Other partitions carry traffic | Use `idlePartitionEventInterval` or partition metrics |
| Prometheus lacks metric despite running listener | Registry/exporter unconfigured, wrong metric name, or custom gauge unregistered | Check `MeterRegistry`, scrapes, labels, and live series |

During incidents, the first question is "**are new records expected to arrive right now?**" If no, idleness may be completely normal. If yes, proceed to compare producer, broker, assignments, pause state, consumer polling, and listener errors.

## 21. Essential integration tests

Use a Kafka test broker or Testcontainers with a listener configured with a short `idleEventInterval` in test environments. Use latches/queues to capture events instead of sleeping a fixed duration and grepping logs.

```java
@Component
public class IdleEventTestProbe {

    private final BlockingQueue<String> idle = new LinkedBlockingQueue<>();
    private final BlockingQueue<String> active = new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        idle.offer(event.getListenerId());
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        active.offer(event.getListenerId());
    }

    public String awaitIdle(Duration timeout) throws InterruptedException {
        return idle.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public String awaitActive(Duration timeout) throws InterruptedException {
        return active.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

Tests should ensure the container received partition assignments before timing idle thresholds, and when multiple child containers exist, filter for the exact listener/container ID being observed. Clear old state/queues after each test case so leftover events do not leak.

Scenarios worth testing:

1. **No records:** listener container polls normally, emitting idle events past the threshold.
2. **Records resume:** listener receives records after an idle phase and emits a no-longer-idle event.
3. **Continuous records:** no false idle events when inter-record gaps stay below threshold.
4. **Two partitions with different cadences:** container stays active while one partition is idle; partition idle events distinguish them.
5. **Pause/resume:** do not misclassify idle events during pause as producer outages.
6. **Listener blocking:** non-responsive/poll-interval monitoring catches hangs distinctly from normal idleness.
7. **Rebalance:** monitoring state updates on assignment changes and old owners stop reporting stale state.
8. **Deserialization/retry failures:** method-level idle gauges miss pre-listener failures; DLT/retry metrics still reflect the incident.
9. **Custom gauge:** initial no-record state is represented clearly, resets accurately on new records, and climbs with time.
10. **Multi-instance:** dashboard aggregations do not flag the whole pipeline idle just because one replica holds no partitions.

Tests should verify **events were emitted**, **listeners received records**, **group/partition assignments**, and **appropriate offset/processing outcomes**. Seeing an idle event alone does not prove a consumer group works end-to-end.

## 22. Runbook when consumer is abnormally idle

When alerts show a consumer idle longer than expected, investigate as follows:

1. **Check the traffic contract:** how many records is the producer expected to emit, during which hours, and are batch/holiday schedules active?
2. **Determine scope:** listener ID, consumer group, topic, partition, instance, and current assignments.
3. **Distinguish states:** is the container running, idle, paused, unassigned, rebalancing, or stopped?
4. **Inspect broker data:** does the topic have new records, are end offsets/LSO advancing, and is the producer hitting publish errors?
5. **Inspect poll responsiveness:** is the consumer still calling poll regularly, or are there `NonResponsiveConsumerEvent`s, `max.poll.interval.ms` warnings, or heartbeat issues?
6. **Inspect lag:** does the group have a backlog it is failing to fetch, or has it genuinely caught up with the log?
7. **Inspect listener/downstream:** are slow HTTP/DB calls, retries, DLT, or deserialization preventing records from reaching the listener method?
8. **Remediate at the right point:** fix the producer, resume the container per policy, restore downstream, or fix consumer bugs; never reflexively reset offsets.
9. **Verify recovery:** observe no-longer-idle events, throughput, committed offsets, consumer lag, and business success.
10. **Refine alerts:** include pause/assignment state and expected traffic to cut false positives.

A good alert explains *why idleness is abnormal*. For example, "payment listener received no records for 8 minutes during peak hours, producer publish rate remains 100 records/s, group lag is rising, container is not paused" carries far stronger signal than "consumer idle 8 minutes."

Never run `seekToEnd`, reset group offsets, or spin up a new group just to silence an alert without finding the root cause. Those actions can skip unprocessed records or create duplicates while leaving producer outages or wedged consumers unresolved.

## 23. Core principles

1. **Consumer idle time has no single definition:** separate listener idle duration, poll idle ratio, and time since last poll.
2. `idleEventInterval` emits `ListenerContainerIdleEvent` when a container receives no records long enough; the event does not alter retries, offsets, or consumer lifecycles.
3. Observe `ListenerContainerNoLongerIdleEvent` to know when data resumes, without treating it as proof of business processing success.
4. When multiple partitions share one consumer, the container can stay active even while one partition is idle; use partition idle events when needed.
5. `poll-idle-ratio-avg` is the fraction of time spent waiting in poll, **not seconds since the last record**.
6. `time-between-poll` and `NonResponsiveConsumerEvent` catch wedged consumer threads; never use idle events in their place.
7. Alerts are useful only with expected traffic and context: assignments, pauses, lag, producer health, LSO, and environment.
8. Never run blocking HTTP/DB calls in synchronous default event observers; never touch Kafka consumer objects from other threads.
9. Custom gauges must define exact measurement points, handle no-record states, respect stop/rebalance lifecycles, and bound metric tag cardinality.
10. Combine listener idle, Kafka client metrics, processing latency, retries/DLT, consumer lag, and business outcomes to diagnose reliability.

**Conclusion:** measuring consumer idle time identifies when a listener is resting or missing expected data, yet it only makes sense alongside polling health, partition ownership, and actual data flow. In Spring Kafka, `idleEventInterval` and idle events provide container-layer observability signals; Kafka client metrics help gauge time waiting inside `poll()` and consumer progress. Separating these signals cleanly lets operations reduce false positives, catch wedged consumers early, and avoid unnecessary offset resets or restarts.
