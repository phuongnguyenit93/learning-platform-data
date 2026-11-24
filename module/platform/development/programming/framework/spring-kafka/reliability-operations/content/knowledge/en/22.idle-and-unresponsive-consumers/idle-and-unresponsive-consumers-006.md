# monitorInterval

In Spring Kafka, a consumer **receiving no records** and a consumer **no longer polling normally** are two very different states. A topic can be completely empty while the consumer remains healthy, continuously calling `KafkaConsumer.poll()` to maintain group membership. Conversely, a listener or Kafka client can get stuck so the poll loop stops progressing even while the topic has data waiting to be processed.

**monitorInterval** is a Spring Kafka listener container property that specifies **how frequently to check whether the consumer is responsive**. It works together with `pollTimeout` and `noPollThreshold` to detect when a consumer has gone too long without completing normal poll cycles, emitting **`NonResponsiveConsumerEvent`** for application observability.

This lesson belongs to the **Idle and Non-Responsive** topic. The focus is not merely setting a `monitorInterval` number, but understanding the three-property triad, distinguishing idle from stuck consumers, curbing false alarms, diagnosing root causes, and recovering safely without losing offsets or triggering rebalance loops.

## 1. Two states: idle and non-responsive

Consider two consumers subscribed to topic `orders.events`.

**Consumer A: topic has no new messages**

    Consumer A:
      poll() -> empty
      poll() -> empty
      poll() -> empty
      ...
      poll() keeps getting called steadily

Consumer A may be **idle**, yet it is operating normally. It maintains heartbeats and group membership, ready to receive new data.

**Consumer B: poll loop stops progressing**

    Consumer B:
      poll() -> records
      processing / other operations
      thread blocked too long
      ...
      has not returned to poll()

Or another case:

    Consumer B:
      calls poll()
      poll() fails to return within expected duration
      ...
      no progress

Consumer B may be classified as **non-responsive** under the monitoring policy. This state requires investigation because it can lead to consumer lag, lost assignments, or offset commit failures.

Key differences:

| Signal | Idle | Non-responsive |
|---|---|---|
| New records from broker? | Likely none | May or may not exist |
| Poll loop still progressing? | Usually yes | Not progressing frequently enough |
| Primary meaning | No data to process | Signs the consumer is slow or stuck |
| Related Spring Kafka event | ListenerContainerIdleEvent | NonResponsiveConsumerEvent |
| Core configuration | idleEventInterval | monitorInterval, noPollThreshold, pollTimeout |
| Action | Usually informational monitoring | Investigate threads, broker, dependencies, and poll interval |

Never use `NonResponsiveConsumerEvent` to report an empty topic; nor treat an idle event as proof the consumer is hung.

## 2. What does monitorInterval actually control?

Spring Kafka schedules a periodic monitoring task for the listener container. **monitorInterval** sets the interval between checks of consumer responsiveness.

Simply put:

    Consumer thread:
      poll() -> listener -> poll() -> listener -> ...

    Monitor task:
      check ----- check ----- check ----- check
         interval = monitorInterval

If the elapsed time since the last poll exceeds the threshold determined by `noPollThreshold` and `pollTimeout`, the container can publish `NonResponsiveConsumerEvent`.

Three quantities must be distinguished:

- **pollTimeout:** maximum wait duration passed to a single `KafkaConsumer.poll()` call, in milliseconds in `ContainerProperties`.
- **noPollThreshold:** multiplier used to define the unacceptable duration without a poll cycle.
- **monitorInterval:** check cadence for the monitor task, typically configured in **seconds**, not milliseconds.

The threshold formula commonly described by Spring Kafka:

    NonResponsiveThreshold = pollTimeout * noPollThreshold

And the detection condition can be approximated as:

    timeSinceLastPoll > NonResponsiveThreshold
      -> monitor task considers consumer non-responsive
      -> publish NonResponsiveConsumerEvent

Do not confuse `monitorInterval` with "maximum seconds to wait before emitting an event". It is only the **sampling cadence**; the evaluation threshold is computed from the other two properties.

## 3. Defaults and units

Across many Spring Kafka versions, common defaults are:

| Property | Common value | Unit | Role |
|---|---:|---|---|
| pollTimeout | 5,000 | ms | Poll wait duration |
| noPollThreshold | 3.0 | multiplier | Multiplied by pollTimeout to form threshold |
| monitorInterval | 30 | seconds | Monitor check cadence |
| idleEventInterval | No idle events unless enabled | ms | No-record threshold |

With these values:

    pollTimeout = 5,000 ms = 5 seconds
    noPollThreshold = 3.0

    Threshold = 5 * 3 = 15 seconds

    monitorInterval = 30 seconds

A consumer crossing 15 seconds will not necessarily trigger an event at second 15 sharp, because the monitor only checks every 30 seconds and depends on JVM scheduling.

**Version note:** Spring Kafka has evolved certain APIs, defaults, and listener container mechanics over time. When integrating, verify `ContainerProperties` Javadoc for your exact dependency. Examples here use common Spring Kafka 3.x APIs; do not assume every property or default is identical in older versions.

## 4. Estimating incident detection time

Suppose:

    pollTimeout = 5 seconds
    noPollThreshold = 3.0
    NonResponsiveThreshold = 15 seconds
    monitorInterval = 10 seconds

The monitor samples at 10, 20, and 30 seconds into an illustrative measurement sequence.

If the consumer stops progressing at second 0:

    T=0s:   Consumer stops polling
    T=10s:  Monitor check; 10s has not exceeded 15s threshold
    T=20s:  Monitor check; 20s > 15s, detected
    T=30s:  Monitor may continue observing unhealthy state

Detection time in this example is around 20 seconds—neither 10 seconds nor exactly 15 seconds.

In principle, under normal scheduler behavior, extra sampling delay can be up to roughly one `monitorInterval` past the threshold. However, GC pauses, CPU starvation, thread scheduling, and container lifecycle transitions can delay actual emission further. Never treat this as a hard real-time deadline guaranteed under all conditions.

If your goal is detection within a few seconds, balance `monitorInterval`, `pollTimeout`, `noPollThreshold`, and false-alarm risk. Lowering `monitorInterval` without adjusting the other parameters does not lower the non-responsive threshold itself.

## 5. monitorInterval is not max.poll.interval.ms

Similar names, two completely different layers:

| Configuration | System | Controls |
|---|---|---|
| monitorInterval | Spring Kafka container | Non-responsive check cadence |
| pollTimeout | Kafka consumer via container | Duration poll waits for records |
| noPollThreshold | Spring Kafka container | Threshold factor based on pollTimeout |
| max.poll.interval.ms | Kafka Consumer group protocol | Allowed interval between polls under group membership rules |

If a consumer processes a poll for too long and exceeds `max.poll.interval.ms`, the Kafka client may be treated as failing to poll frequently enough, triggering a rebalance or lost assignment. That is a **group-membership consequence**.

`NonResponsiveConsumerEvent` is an **application alert** emitted when the container detects an abnormal poll gap. It does not extend the broker/client `max.poll.interval.ms` limit and does not protect partitions from rebalancing.

Example:

    monitorInterval = 10 seconds
    threshold = 30 seconds
    max.poll.interval.ms = 300,000 ms (5 minutes)

The container can emit a non-responsive warning well before the 5-minute mark. This enables early investigation before the consumer actually loses assignments, though it does not guarantee the cause is a deadlock.

Conversely, if `monitorInterval`/threshold is set too high, the Kafka client may already rebalance before the monitor provides any useful signal.

## 6. monitorInterval does not replace idleEventInterval

`idleEventInterval` emits `ListenerContainerIdleEvent` when the container receives no records for a configured interval, while the poll loop may still be running normally.

Example:

~~~java
ContainerProperties props = factory.getContainerProperties();

// Unit milliseconds: 60 seconds without receiving records.
props.setIdleEventInterval(60_000L);

// Unit seconds: monitor checks every 10 seconds.
props.setMonitorInterval(10);
~~~

The two properties answer different questions:

- `idleEventInterval`: "How long has the consumer received no records?"
- `monitorInterval`: "How often should we check whether the poll loop is responsive?"

A `ListenerContainerIdleEvent` can fire after one minute of no data **without** firing `NonResponsiveConsumerEvent`, because the consumer is still polling successfully.

If a consumer becomes non-responsive, do not assume an idle event will also fire at that moment; event emission depends on the poll loop and container mechanics.

## 7. Configuring the three-parameter triad in Spring Kafka

With a `ConcurrentKafkaListenerContainerFactory`, configure as follows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class OrdersConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties props = factory.getContainerProperties();

        // pollTimeout: milliseconds.
        props.setPollTimeout(5_000L);

        // Non-responsive threshold: 3 * 5s = 15s.
        props.setNoPollThreshold(3.0f);

        // Monitor wakes up every 10s (unit seconds).
        props.setMonitorInterval(10);

        // Idle event independent of non-responsive event.
        props.setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

Listener using this factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-processor",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

`OrderCreated` and `orderService` are illustrative application components. The example requires Spring Kafka dependencies, bean configuration, and project-appropriate imports.

This configuration only affects containers created by `ordersListenerFactory`. If the system has multiple listener factories, listeners using other factories will not inherit these values automatically.

**Do not mistake `setMonitorInterval(10)` for 10 milliseconds.** That option takes seconds, whereas `setPollTimeout(5_000L)` takes milliseconds.

## 8. Configuring with Spring Boot vs Java configuration

Spring Boot exposes many Kafka consumer and listener properties, but do not assume every `ContainerProperties` setter has a matching `spring.kafka.listener.*` key across all Boot versions.

A baseline YAML configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Properties like `monitorInterval` and `noPollThreshold` are typically best configured directly via Java `ContainerProperties`, or through an application-managed customizer/factory if supported by your version.

You can customize Spring Boot's default factory bean once you verify the customizer contract. Most importantly, **the listener container must actually use the configured factory**; merely declaring a bean that the listener ignores will have no effect on monitoring.

In multi-instance environments, pods can share the same policy for consistent metric comparisons, though SLOs and poll processing times may vary across consumer groups. One global threshold does not have to fit every workload.

## 9. What is NonResponsiveConsumerEvent?

Spring Kafka provides the **`NonResponsiveConsumerEvent`** application event for cases where the monitor detects a consumer exceeding the non-responsive threshold.

An observer can handle the event via Spring `@EventListener`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPollMonitorListener {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPollMonitorListener.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {

        log.warn(
            "Non-responsive Kafka consumer: listenerId={}, " +
            "timeSinceLastPollMs={}, source={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getSource()
        );
    }
}
~~~

Key details:

- `getTimeSinceLastPoll()` provides the measured duration since the last poll per the event, typically expressed in milliseconds.
- `getListenerId()` helps identify the relevant listener.
- `getSource()` is the application event source; never arbitrarily treat it as a `KafkaConsumer` safe to invoke from another thread.

This observer logs the event; it is not auto-restart code. The event helps contextualize alerts without yet proving the consumer is genuinely deadlocked.

## 10. What should the application event handler do?

Inside the callback, prefer short operations:

1. Write a structured log with `listenerId`, `instanceId`, and time since last poll.
2. Increment a metric counter.
3. Read container state via safe APIs.
4. Send a lightweight signal to a supervisor or monitoring queue.
5. Correlate with other signals before deciding whether recovery is needed.

Example:

~~~java
@Component
public class NonResponsiveConsumerMetrics {

    private final MeterRegistry metrics;

    public NonResponsiveConsumerMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void record(NonResponsiveConsumerEvent event) {

        metrics.counter(
            "kafka.consumer.nonresponsive",
            "listener", event.getListenerId()
        ).increment();
    }
}
~~~

When using a `listenerId` label, keep cardinality bounded; if listener IDs carry per-child or per-pod suffixes, anticipate the series count. Never put `eventId`, partition offsets, or full exceptions into metric labels.

Application event handlers should avoid long blocking network calls, holding locks, or running complex remediation routines. Monitoring tasks must be fast so monitoring itself never becomes a new bottleneck.

## 11. Which thread runs the event handler?

Non-responsive monitoring runs from a container monitoring task—never assume the callback executes on the consumer poll thread. Spring's `ApplicationEventMulticaster` may also dispatch listeners synchronously or asynchronously depending on configuration.

Consequences:

- Never touch a `KafkaConsumer` instance from an event listener on a thread that does not own the consumer.
- Never call `poll()`, `seek()`, `commitSync()`, or `pause()` directly on the raw consumer from an async monitoring callback.
- `KafkaConsumer` is generally not thread-safe; follow the Kafka client's threading contract.
- Never rely on consumer `ThreadLocal` state inside the monitor thread.
- If stop/restart is needed, go through Spring Kafka container APIs and an appropriate lifecycle supervisor.

`KafkaConsumer.wakeup()` is a thread-safe exception in the Kafka client contract, yet it should not be used blindly to "fix" every `NonResponsiveConsumerEvent`. Spring Kafka's container manages polling and lifecycle; interfering with the raw consumer can introduce additional failures.

## 12. Checking container state by listener ID

Spring Kafka provides `KafkaListenerEndpointRegistry` to look up the container for a `@KafkaListener`.

~~~java
@Service
public class ListenerContainerHealth {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerHealth(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

A container with `isRunning() = true` can still be stuck or receiving no data. Combine it with:

- Last poll time or `NonResponsiveConsumerEvent`.
- Committed offset progression.
- Consumer lag and oldest record age.
- Assigned partition count.
- Processing duration and dependency latency.
- Container pause state.
- Kafka consumer group membership.

Never judge a container healthy solely from `isRunning()`, and never declare it dead from a single `NonResponsiveConsumerEvent`.

## 13. Never stop/restart synchronously inside @EventListener

A tempting reaction:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Anti-pattern: avoid calling synchronous stop here.
    registry.getListenerContainer("ordersListener").stop();
}
~~~

This is **not** a recommended production recovery mechanism. Risks include:

- Stopping synchronously can make the caller wait on the very consumer thread that is stuck.
- Monitor events can repeat periodically, issuing repeated stop/restart requests.
- The signal might reflect legitimate slow listener processing.
- A persistent dependency outage will trigger a restart loop.
- Restarting a group member triggers rebalances, potentially increasing lag and duplicates.
- A parent `ConcurrentMessageListenerContainer` owns multiple child consumers; stopping the parent disrupts healthy partitions too.

Instead, let the event handler forward a lightweight signal to a dedicated supervisor. The supervisor checks real state, enforces timeouts/cooldowns, targets only the right container, and coordinates with orchestration if needed.

If stopping a container from an event path is required, do not block directly on the monitor thread; execute via a managed executor/scheduler with bounded queues and lifecycle policies. Verify `stop()` behavior in your Spring Kafka version.

## 14. A supervisor with cooldown and explicit policy

Appropriate model:

    NonResponsiveConsumerEvent
             |
             v
    Lightweight observer
             |
             v
    Bounded signal queue
             |
             v
    Recovery supervisor
             |
             +--> inspect listener container state
             |
             +--> check consecutive count + recent timing
             |
             +--> check lag / processing / dependencies
             |
             +--> decide alert or restart
             |
             v
    Recovery action with backoff

Example policy:

| Condition | Action |
|---|---|
| Single isolated event, listener still processing | Log/metric; do not restart prematurely |
| Two or more consecutive monitor cycles non-responsive | Inspect thread dump and dependencies |
| Dependency outage while consumer still polls | Rate limit/pause per design; no blind restarts |
| Consumer thread genuinely stuck, zero progress | Escalate; controlled restart if contract permits |
| In-flight transaction active | Evaluate abort/fencing and side-effect safety |
| Repeated restarts within a short window | Halt auto-restart and escalate alert |
| Pod/JVM unresponsive | Handled by external liveness/monitoring |

A supervisor should avoid competing restart mechanisms—such as a local scheduler and a Kubernetes liveness probe acting simultaneously—otherwise the system can continuously churn consumer group rebalances.

## 15. Why can NonResponsiveConsumerEvent be a false alarm?

Not every long gap between polls is a deadlock.

Causes that lengthen poll gaps:

- The listener executes slow but completing business logic.
- Database or HTTP calls run slowly.
- `max.poll.records` is large so one poll returns many records.
- Thread pool contention or lock waiting.
- Long JVM GC pauses.
- Container CPU throttling.
- Host resource exhaustion.
- Shutdown, rebalance, or waiting on a lifecycle operation.
- Poll timeout and `noPollThreshold` configured too tight for the workload.
- Intentional inter-poll delays or backpressure configured.

Depending on how the container tracks last poll time, a slow listener or a thread blocked elsewhere can also trigger a "has not polled soon enough" signal. The event does not pinpoint the exact stuck stack frame.

When an event arrives, check thread dumps to distinguish:

    Thread waiting in KafkaConsumer.poll()
        -> investigate client/network/coordinator

    Thread waiting on database socket read
        -> investigate DB timeout/connection pool

    Thread waiting on code lock
        -> investigate deadlock/contention

    Thread processing hundreds of records synchronously
        -> inspect max.poll.records and processing time

Never keep raising `noPollThreshold` blindly just to silence events. If the root cause is a dependency without timeouts, raising the threshold simply blinds incident detection.

## 16. Choosing monitorInterval and pollTimeout for the context

Three illustrative configurations:

| Workload | pollTimeout | noPollThreshold | Threshold | monitorInterval |
|---|---:|---:|---:|---:|
| Lightweight listener expecting frequent polls | 2,000 ms | 3.0 | 6 seconds | 5 seconds |
| Moderate workload | 5,000 ms | 3.0 | 15 seconds | 10 seconds |
| Workload with long poll wait | 10,000 ms | 3.0 | 30 seconds | 10–15 seconds |

These values are **examples for reasoning**, not mandatory templates. Choose based on observed processing-time distributions, Kafka client behavior, CPU scheduling, and the impact of consumer stalls.

Key guidelines:

1. `pollTimeout` serves fetch/poll behavior and should not be altered arbitrarily just to tweak the monitor.
2. `noPollThreshold` sets the tolerance ratio relative to `pollTimeout`.
3. `monitorInterval` should be small enough for timely operational detection without polling excessively.
4. Detection SLOs must include scheduler delay and alert-processing latency.
5. For multi-record polls, factor in `max.poll.records` and total poll processing time.

If `pollTimeout` doubles while `noPollThreshold` stays constant, the non-responsive threshold also doubles. `monitorInterval` does not auto-adjust with it.

## 17. Impact of values that are too small

Suppose:

    pollTimeout = 5,000 ms
    noPollThreshold = 1.1
    monitorInterval = 1 second

The threshold is only 5.5 seconds. A normal poll approaching its timeout, plus minor Java scheduling overhead, GC, or listener setup, can easily breach the threshold and produce useless alerts.

Consequences:

- Non-responsive counter climbs even while the system is processing fine.
- Alert fatigue causes operators to ignore real incidents.
- Overly sensitive supervisor restarts can trigger rebalance storms.
- Consumer redelivery forces side effects to run again.
- Logging/metric overhead and investigation toil increase.

Thresholds need reasonable **headroom** over `pollTimeout`, processing time, and scheduler jitter. Measure real data before tightening values aggressively.

## 18. Impact of values that are too large

Conversely:

    pollTimeout = 5,000 ms
    noPollThreshold = 30
    monitorInterval = 120 seconds

Threshold = 150 seconds. The monitor only checks once every two minutes; detection may lag far behind SLOs.

Consequences:

- Consumer lag builds substantially before any alert fires.
- Offset or group membership errors may have already occurred.
- Dependency outages drag on without a dedicated consumer signal.
- Operations teams struggle to separate brief slowdowns from prolonged hangs.
- Container running state still shows `true` despite zero progress.

If long poll gaps are required for a specialized workload, supplement with metrics like processing duration, per-partition lag, and oldest record age. Never set a huge monitor threshold and assume the system is adequately monitored.

## 19. Impact of max.poll.records

`max.poll.records` limits the maximum records returned by a single `KafkaConsumer.poll()`. With a record listener, the container processes a sequence of records before returning to poll.

Suppose:

    max.poll.records = 500
    Each record takes ~100 ms
    One poll can hold 500 records

    Business processing time ~50 seconds

If monitoring checks poll cadence against a 15-second threshold, a completely valid long batch will trigger non-responsive alerts.

Remediation options:

- Lower `max.poll.records` to match processing throughput.
- Reduce per-record processing latency.
- Enforce timeouts on dependencies.
- Increase concurrency if partition count and dependency capacity allow.
- Offload long-running jobs from the consumer path via durable contracts.
- Tune monitor thresholds after measuring actual processing times.

Merely raising `max.poll.interval.ms` does not eliminate `NonResponsiveConsumerEvent`, as the two mechanisms are independent.

## 20. Slow polling and consumer group rebalances

When a consumer fails to poll often enough, it can be evicted or undergo group membership changes per Kafka's protocol. The group coordinator can reassign partitions to another consumer.

Diagram:

    Consumer A owns partition P0
            |
            v
    A processes too long without polling again
            |
            +--> Spring monitor may emit warning
            |
            v
    max.poll.interval.ms exceeded
            |
            v
    Group membership changes
            |
            v
    Partition P0 may move to Consumer B
            |
            v
    B safely reads from committed offset

If A already applied database side effects without committing the source offset, B may reprocess the same event. Reliability protection therefore requires:

- Stable idempotency keys / `eventId`.
- Bounded dependency timeouts.
- Never committing offsets before durable processing completes.
- Handling assignment/revocation/lost ownership cleanly.
- Fencing stale tasks when async work is involved.
- Monitoring consumer group generations and rebalances.

`monitorInterval` **does not prevent** rebalances; it surfaces an early or concurrent warning so operators can intervene.

## 21. Do pause/resume trigger NonResponsiveConsumerEvent?

When using Spring Kafka `container.pause()`, the container usually preserves poll cadence to keep group membership alive while partitions are paused. Thus, **container-level pause** does not mean the poll loop is hung.

Example:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    container.pause();
}
~~~

As long as the container executes the required polls, it may not emit `NonResponsiveConsumerEvent` merely because it is paused. Still, in-flight records, `pauseImmediate` mode, and container version behavior can affect loop timing.

Distinguish clearly:

| Event | Primary indicator |
|---|---|
| Container pause requested | Pause request recorded |
| Container consumer paused | `ConsumerPausedEvent` or corresponding state |
| Container idle | No records received for configured duration |
| Consumer non-responsive | Poll cadence failed monitor threshold |
| Container stopped | Lifecycle stopped, no longer polling |

Never use `monitorInterval` to implement backpressure. To throttle consumption, use rate limiters, concurrency limits, or proper pause/resume APIs.

## 22. idleBetweenPolls and its relationship to monitoring

`ContainerProperties.idleBetweenPolls` inserts sleep intervals between polls to throttle consumption rate.

Example:

~~~java
ContainerProperties props = factory.getContainerProperties();

props.setIdleBetweenPolls(1_000L);
props.setPollTimeout(5_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
~~~

When an application intentionally pauses between polls, observed gaps between poll cycles grow. An overly sensitive monitor policy might mistake intentional throttling for unresponsiveness.

Never use `idleBetweenPolls` as an exact requests-per-second quota; one poll can still return many records. If using a blocking rate limiter inside the listener, include permit wait times in your processing budget before setting monitor thresholds.

Measure actual poll-to-poll intervals under live workload rather than simply adding numbers on paper to predict whether events will fire.

## 23. NonResponsiveConsumerEvent vs ConsumerStoppedEvent

Both events appear in the same systems yet mean very different things.

**NonResponsiveConsumerEvent**: the monitor observed a consumer failing to advance polls within threshold. The consumer may still be lifecycle-running and not yet stopped.

**ConsumerStoppedEvent**: the consumer actually terminated its lifecycle; the event may include a `Reason` such as `NORMAL`, `ERROR`, `AUTH`, `FENCED`, or `NO_OFFSET` depending on version.

Diagram:

    Consumer fails to poll in time
        |
        v
    NonResponsiveConsumerEvent
        |
        +--> May self-recover
        |
        +--> May remain stuck
                |
                v
        Container may be stopped/restarted
                |
                v
        ConsumerStoppedEvent

Not every `NonResponsiveConsumerEvent` leads to `ConsumerStoppedEvent`, and not every `ConsumerStoppedEvent` is preceded by `NonResponsiveConsumerEvent`. For example, a normal shutdown emits `ConsumerStoppedEvent(NORMAL)` with no poll warnings.

In alerting, non-responsive is typically a warning requiring verification; unexpected stops directly reduce capacity and consumption progress and require separate investigation.

## 24. NonResponsiveConsumerEvent vs ListenerContainerIdleEvent

Suppose topic `orders.created` has zero data for an hour:

    Consumer keeps polling:
       00:00 poll empty
       00:05 poll empty
       00:10 poll empty
       ...
       60:00 poll empty

If `idleEventInterval` is configured, Spring Kafka can emit `ListenerContainerIdleEvent` periodically. Yet this is **absence of data**, not a deadlock.

Another case:

    Topic has new data
       |
       v
    Consumer blocked long in client or listener
       |
       v
    Fails to poll again soon enough
       |
       v
    NonResponsiveConsumerEvent

Even if both events exist in the system, remediation differs:

- Prolonged idle: check producer traffic, topic selection, filters, pause, assignment.
- Non-responsive: check thread dumps, poll intervals, dependencies, and lifecycle.

If both appear on dashboards, chart them as distinct metrics rather than summing them into "Kafka listener errors".

## 25. Monitoring individual child consumers at high concurrency

With `concurrency=4`, one parent `ConcurrentMessageListenerContainer` can manage four child Kafka consumers:

    Parent ordersListener
       |
       +-- Consumer 0 -> P0, P1
       +-- Consumer 1 -> P2, P3
       +-- Consumer 2 -> P4, P5
       +-- Consumer 3 -> P6, P7

If only Consumer 2 hits a deadlock, the other consumers can keep polling and processing normally.

Points to note:

- `NonResponsiveConsumerEvent` can be tied to a specific child container/consumer.
- Never declare the whole consumer group dead from one child's event.
- One parent listener ID can spawn multiple child IDs per Spring Kafka's naming convention.
- Check lag per partition to see which workload slice is impacted.
- Choosing to restart the parent container disrupts all child consumers.
- Stopping a single child must use framework-supported APIs/lifecycle, never raw `KafkaConsumer` manipulation from the monitor thread.

In metrics, use bounded labels like `application`, `group`, `listener`, or managed child index; never use offsets or `eventId` as labels.

## 26. Designing monitoring with structured logs

A helpful log when `NonResponsiveConsumerEvent` fires:

    event_type=NonResponsiveConsumerEvent
    application=order-service
    instance=order-service-pod-2
    listener_id=ordersListener-2
    time_since_last_poll_ms=22000
    monitor_interval_sec=10
    poll_timeout_ms=5000
    no_poll_threshold=3.0
    consumer_lag=12000
    action=investigate

Not all fields come directly from the event. Configuration values and lag must be pulled from application config or other metric sources; never fabricate them just to make logs look rich.

Never log raw `KafkaConsumer` objects, credentials, or full record payloads. If thread dumps are captured automatically, they may expose sensitive stack/local context; apply proper retention and access controls.

Correlate event timestamps, container/client IDs, consumer groups, and pod instances to trace logs leading up to the incident.

## 27. Metrics to combine

Recommended metrics:

| Metric | Purpose |
|---|---|
| kafka_consumer_nonresponsive_total | How often the monitor detected non-responsiveness |
| kafka_consumer_time_since_last_poll_ms | Poll gap observed on event or periodic measurement |
| kafka_consumer_poll_duration | Kafka consumer poll duration |
| kafka_listener_processing_duration | Listener record/batch processing duration |
| kafka_consumer_records_consumed_rate | Record consumption rate |
| kafka_consumer_lag | Uncommitted/unconsumed records per measurement method |
| kafka_consumer_oldest_record_age | Backlog age |
| kafka_consumer_rebalance_total | Consumer group rebalance count |
| kafka_consumer_commit_failures_total | Offset commit failures |
| kafka_consumer_paused | Whether consumer/partition is paused |
| jvm_gc_pause | Stop-the-world GC duration |
| process_cpu_throttling | Container CPU throttling status |
| downstream_latency / timeout | Likelihood of dependency slowdown |

Metric names in this table are **meaning-oriented examples**, not a guarantee that Spring Kafka or Micrometer exports those exact names out of the box. Exact names depend on Kafka client metrics, Micrometer binders, Prometheus conventions, and your observability stack.

Watch trends over time. One brief `NonResponsiveConsumerEvent` with flat lag may be benign; consecutive events paired with rising lag and processing duration are far more actionable.

## 28. How to choose SLOs and alert thresholds?

An SLO might require:

- 99.9% of records processed within 60 seconds.
- No consumer stuck for over 30 seconds without an alert.
- No partition ownerless past the allowed window.
- Retry/error rates within error budget.

To achieve ~30-second stall detection, you might pick:

    pollTimeout = 5 seconds
    noPollThreshold = 3.0
    threshold = 15 seconds
    monitorInterval = 5 or 10 seconds

Under standard sampling, an event can fire on a check following threshold breach. Yet this is not a real-time guarantee if the JVM freezes or the scheduler stalls.

A production alert should require at least two conditions:

1. Consumer flagged non-responsive by the monitor.
2. Evidence of degraded processing progress such as rising lag/oldest age or multiple consecutive abnormal monitor checks.

If a system must detect hard hangs even when the JVM stops emitting events, add **out-of-process monitoring**; local monitors also stop when the JVM dies or the node gets no CPU.

## 29. Distinguishing a stuck poll from a stuck listener

Investigation steps:

**Step 1: inspect thread dumps.**

Find threads named for the Kafka listener container or consumer. Check where stacks are parked:

- `KafkaConsumer.poll` or network client.
- JDBC driver / connection pool.
- HTTP client socket read.
- Object monitor / `LockSupport` / `CompletableFuture.get`.
- Deserialization or business logic.
- Kafka transaction commit/abort.
- `ApplicationEvent` listener running blocking operations.

**Step 2: correlate timing.**

If listener processing duration p99 spiked before `NonResponsiveConsumerEvent`, dependency/business code is likely the bottleneck. If the listener barely ran while polling stalled, look at broker/network/client.

**Step 3: check group state.**

Did the consumer lose assignments? Are rebalances happening? Are committed offsets advancing? Is the pod experiencing GC or CPU throttling?

**Step 4: choose the right action.**

Do not restart Kafka merely because a thread dump shows a socket read waiting within a valid timeout. Conversely, if a task blocks indefinitely and breaches SLOs, enforce timeouts and fix the code.

## 30. Non-responsive does not equal Kafka network timeout

An exception from a Kafka request timeout can fail a poll or broker interaction, yet `NonResponsiveConsumerEvent` can appear **with zero Kafka exceptions**.

Example:

    Listener calls HTTP client with infinite timeout
    HTTP server stops responding
    Consumer thread waits indefinitely
    Fails to return to poll on cadence
    Monitor reports non-responsive

The Kafka broker may be completely healthy with zero network issues between consumer and broker.

Conversely, a broker outage can cause polls to repeatedly error and retry while the container keeps looping in a way that prevents the monitor from seeing a single long blocked poll.

Therefore, never use the event to conclude "broker down". Combine client metrics, broker health, networking, and stack traces.

## 31. Enforcing request timeouts and concurrency limits

To prevent business processing from causing non-responsiveness, bound how long a record can hold the consumer thread:

- HTTP clients with connect, read/response timeouts, and overall deadlines.
- JDBC pools with connection acquisition and query timeouts.
- Bounded thread pools with queue limits.
- Never wait indefinitely on `Future.get()`, `CountDownLatch`, or distributed locks.
- Circuit breakers for unresponsive dependencies.
- Rate limiters / concurrency limits to avoid overloading upstream/downstream.
- Retries with backoff and clear total deadlines.

Rule-of-thumb example:

    ProcessingDeadlinePerRecord = 2 seconds
    max.poll.records = 100
    Worst-case sequential processing ~= 200 seconds

If the group poll interval is 300 seconds, this worst-case processing time sits close to the limit once retries, commits, and scheduling are added. For lower latency, reduce `max.poll.records` or optimize per-record execution.

Deadlines must be realistic: overly short timeouts cause spurious failures and retry storms, while overly long timeouts hinder consumer recovery.

## 32. Impact on offsets and reliability

`NonResponsiveConsumerEvent` does not alter consumer offsets by itself. However, if the application restarts or the consumer loses assignments, polled-but-uncommitted records can be redelivered.

Example:

    Group committed offset = 100
    Consumer polls offsets 100...109
    Succeeds up to 103 without committing yet
    Consumer thread hangs at 104
    Monitor emits event
    Container stops / group rebalances
    New consumer re-reads from committed offset 100

Records 100–103 may then be processed again. Reliability therefore requires:

- Idempotency keyed by `eventId` or a unique business key.
- Never committing offsets prematurely while side effects are still running.
- Tracking group assignments and actual committed offsets.
- Carefully managing manual acknowledgments and async tasks.
- Keeping output and offsets inside the same transaction for Kafka read-process-write transactions.
- Ensuring DLT/recovery never marks a record succeeded when publishing fails.

A supervisor restarting consumers cannot replace idempotency. Consumers can crash without emitting any event, and Kafka still relies on safe reprocessing.

## 33. Should paused consumers have separate alerts?

If an operator intentionally pauses a container due to downstream rate limits, consumer lag may climb—but that does not make the consumer non-responsive.

Define clear state categories:

1. **Running and processing:** consumer polls and listener has throughput.
2. **Running yet paused/idle:** consumer is healthy with low work or intentional pause.
3. **Running yet non-responsive:** poll cadence misses monitor threshold.
4. **Stopped:** container ended its lifecycle.

These states are not a single Spring Kafka enum; they represent an operational classification for dashboard design.

Alerts for prolonged pauses should evaluate backlog/freshness SLOs rather than relying on `NonResponsiveConsumerEvent`. If the JVM still polls normally while paused, non-responsive events are the wrong tool for backlog alerting.

## 34. Testing monitorInterval configuration

Tests must verify that `monitorInterval` and `noPollThreshold` apply to the **factory actually used by the listener**.

Steps:

1. Start a compatible test broker (Embedded Kafka or Testcontainers).
2. Create a listener container with explicit `pollTimeout`, `noPollThreshold`, and `monitorInterval`.
3. Register an `@EventListener` capturing `NonResponsiveConsumerEvent`.
4. Run the consumer normally and verify poll cadence does not falsely trigger errors.
5. Simulate a consumer thread failing to return to poll long enough.
6. Await the event with a test timeout larger than the threshold plus several monitor cycles.
7. Verify the event carries the expected `listenerId` and `timeSinceLastPoll`.
8. Release the blocking condition and verify the consumer recovers per lifecycle.
9. Check offsets/duplicates after restart or rebalance if the test stops the container.

Never assert that an event arrives at an exact millisecond. Emission timing depends on schedulers, machine load, and test environment.

### 34.1. Testing the observer via ApplicationEventPublisher

Observer logic can be unit-tested independently of a broker: publish a synthetic event or call an adapter/service receiving normalized metadata and verify metrics/logs are recorded.

However, such tests **do not prove** the container monitor emits events at the right threshold. That requires integration tests with a listener container and broker or suitable test infrastructure.

### 34.2. Testing when a topic has no records

Create an empty topic; consumer polls return empty steadily. If `idleEventInterval` is enabled, idle events may arrive. Never write a test expecting `NonResponsiveConsumerEvent` merely because there are no records.

### 34.3. Testing a blocked listener

Use a `CountDownLatch` in a business listener to hold the thread after a record is polled:

~~~java
@Component
public class BlockingOrderListener {

    private final CountDownLatch release = new CountDownLatch(1);

    @KafkaListener(
        topics = "orders.monitor-test",
        groupId = "monitor-test-group",
        containerFactory = "testListenerFactory"
    )
    public void consume(String value) throws InterruptedException {
        release.await();
    }

    public void allowCompletion() {
        release.countDown();
    }
}
~~~

Tests must include a `finally` block releasing the latch and stopping the container so the test suite never hangs. Because how the framework determines last poll and handles blocking varies across versions, verify actual events emitted in your test environment rather than assuming behavior solely from the latch.

### 34.4. Testing concurrency

Run multiple child consumers and block only one listener thread. Verify monitoring identifies the right child/source within the limits of the event API, while other children continue processing records and metrics do not misreport the whole group as dead.

## 35. Experimenting with thread dumps and fault injection

A proactive investigation drill:

1. Send a record causing the listener to call a high-latency HTTP stub.
2. Set request timeout longer than the monitor threshold so the signal fires.
3. Capture a thread dump when the event arrives.
4. Correlate thread stacks with listener logs.
5. Inspect downstream latency and request concurrency.
6. Lower request timeouts to appropriate limits.
7. Verify non-responsive event counts drop and consumers stop restarting frequently.

Another scenario simulates CPU throttling or GC pauses. If the JVM hits long stop-the-world pauses, the monitor task itself can also be delayed, causing late events. This proves why JVM and Kubernetes/host monitoring must accompany Kafka monitoring.

Never induce production deadlocks just to validate monitors. Fault injection belongs in controlled test or staging environments with guardrails and rollback plans.

## 36. Runbook when NonResponsiveConsumerEvent fires

Operational workflow:

1. **Determine scope:** `listenerId`, `groupId`, instance/pod, event timestamp, `timeSinceLastPoll`.
2. **Confirm persistence:** isolated occurrence or multiple consecutive monitor cycles?
3. **Check lifecycle:** container running, paused, stopping, or restarting?
4. **Check lag and freshness:** is backlog growing, and on which partitions?
5. **Capture thread dump:** is the consumer thread in poll, listener, lock, DB, or HTTP?
6. **Check dependencies:** latency, timeouts, 429/503 responses, pool saturation.
7. **Check JVM/node:** GC pauses, CPU throttling, OOM, scheduler delays.
8. **Check group:** rebalances, lost partitions, `max.poll.interval.ms`, committed offsets.
9. **Classify root cause:** deadlock, slow processing, dependency outage, or overly sensitive threshold.
10. **Choose recovery:** timeouts, lowering `max.poll.records`, pause/rate limit, or controlled restart.
11. **Control duplicates:** idempotency and transactions on redelivery.
12. **Verify post-fix:** event count, processing latency, lag, commit rate.
13. **Update thresholds and runbooks:** change settings only after measuring the actual cause.

Never respond to every event by raising `monitorInterval`. That merely lengthens the check interval, delaying detection without fixing the root cause.

## 37. Common misconceptions

| Misconception | Reality |
|---|---|
| `monitorInterval` is the maximum time Kafka poll may block | It is the cadence at which the monitor checks |
| `setMonitorInterval(10)` means 10 ms | In common Spring Kafka APIs, the unit is seconds |
| `NonResponsiveConsumerEvent` means the topic has no records | Idle and non-responsive are two distinct states |
| Receiving the event proves the consumer is deadlocked | Could be slow listener, GC, CPU, or tight config |
| Lowering `monitorInterval` lowers the no-poll threshold | Threshold is based on `pollTimeout * noPollThreshold` |
| `noPollThreshold` is a count of failed polls | It is a time-threshold multiplier |
| `monitorInterval` prevents group rebalances | `max.poll.interval.ms` and group protocol operate independently |
| `isRunning()` suffices to prove consumer health | Container can be running while polls stall |
| Idle event alerts on non-responsive consumers | Idle events reflect lack of records |
| Calling `stop()` synchronously in the callback is always safe | Risks blocking the monitor and causing restart loops |
| `KafkaConsumer` is safe to use from any thread | `KafkaConsumer` is not thread-safe |
| Restarting after non-responsive guarantees zero duplicates | Uncommitted records may be redelivered |
| Pausing the container stops the consumer from polling | Container usually keeps polling to preserve membership |
| Monitor can emit events even if the JVM dies | Local monitor dies with the process |

## 38. Production design principles

- Use `monitorInterval` to tune **observation cadence**, not as a Kafka client timeout.
- Pair `noPollThreshold` with `pollTimeout` to define the non-responsive detection threshold.
- Keep units crystal clear: `pollTimeout` in milliseconds, `monitorInterval` in seconds.
- Distinguish `ListenerContainerIdleEvent` from `NonResponsiveConsumerEvent`.
- Track poll duration, processing duration, lag, rebalances, and downstream latency together.
- Never auto-restart the entire group based on a single isolated event.
- Use a supervisor with backoff/cooldown; avoid long synchronous stops inside event callbacks.
- Never manipulate raw `KafkaConsumer` from monitor or async event listener threads.
- Never treat `isRunning=true` as proof of consumer processing progress.
- Enforce timeouts and bounded concurrency for external dependencies.
- Size `max.poll.records` to match per-poll processing time and `max.poll.interval.ms`.
- For pause/backpressure, use container pause/resume APIs instead of simulating throttling via monitor settings.
- Guard side effects with idempotency when restarts or rebalances cause redeliveries.
- Monitor outside the JVM to detect crashes or GC/thread starvation that stall local monitors.
- Test healthy idle topics, blocked listeners, async monitoring, concurrency, and restarts.

## 39. Conclusion

**`monitorInterval` determines how frequently Spring Kafka checks whether a consumer is responsive.** Combined with `pollTimeout` and `noPollThreshold`, it helps surface signs of a stalled poll loop, typically via `NonResponsiveConsumerEvent`. Smaller values enable faster detection at the cost of potential false alarms; larger values slow down diagnosis. No single value fits every listener.

A reliable system treats `monitorInterval` as a **sensor**, not the sole controller. Resolving slow or stuck consumers requires pinpointing causes across the listener, Kafka client, dependencies, JVM, or group lifecycle, and then applying appropriate timeouts, backpressure, retry/recovery, and idempotency. Done right, non-responsive events provide early warning without becoming a source of restart loops and consumer group instability.
