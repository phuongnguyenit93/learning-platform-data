# NonResponsiveConsumerEvent

In Spring Kafka, a normal consumer continuously calls `poll()` to fetch records, maintain consumer group progress, and continue processing data. When a consumer **becomes unresponsive for a long time**, the listener may stop receiving new records even though the pod remains `Running`, the JVM has not crashed, and the TCP connection to Kafka still exists. This is a hard-to-detect failure mode if the system relies solely on application health checks or on whether the container has stopped.

Spring Kafka provides the application event **`NonResponsiveConsumerEvent`** to detect signs that the consumer thread has not returned to the `poll()` loop for longer than a monitoring threshold. The event is published by the listener container's monitor mechanism when the time since poll activity exceeds a threshold derived from `pollTimeout` and `noPollThreshold`. It is **an alert signal requiring investigation**, not definitive proof that the Kafka broker died, not a listener exception, and it does not automatically fix the failure.

This lesson explains when the event appears, how to configure the monitor, how to receive the event in a Spring Boot application, how to distinguish a stuck consumer from slow record processing, and operational workflows to recover without losing data or creating retry/rebalance storms.

## 1. Normal consumer vs. non-responsive consumer

A simple Kafka consumer loop looks like:

```text
                       +-------------------+
                       | Consumer.poll()   |
                       +---------+---------+
                                 |
                                 v
                       Any records returned?
                           /          \
                          No          Yes
                           |            |
                           |            v
                           |       Listener processes
                           |            |
                           +------<-----+
                                 |
                                 v
                         Next poll iteration
```

In Spring Kafka, the listener container manages the consumer thread, calls `poll()`, passes records into the listener, handles acknowledgments/offsets, and performs container tasks. Applications normally do not write their own `while(true)` poll loop.

Failures can prevent the consumer from advancing to the next poll:

- `poll()` or a Kafka client operation is waiting unusually long due to network, broker/coordinator, or library issues.
- The listener takes too long processing records—for example, a long HTTP timeout or an unreleased database lock.
- A callback related to commit/transaction/seek/rebalance is blocked or deadlocked.
- The JVM stalls due to long GC pauses, CPU saturation, or threads contending for resources.
- A flow gets stuck in user code and never returns control to the container.

**Subtle point:** the event is named `NonResponsiveConsumerEvent`, not `KafkaBrokerDownEvent`. The monitor observes the symptom "consumer is not polling on schedule," so the cause may lie in the client, listener, JVM, or Kafka infrastructure. Investigate with thread dumps, logs, metrics, and group state before concluding.

## 2. What is NonResponsiveConsumerEvent?

`NonResponsiveConsumerEvent` resides in package:

```java
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

This is a **Spring application event** published by the Kafka listener container when the monitor detects the consumer has not met the poll threshold. Applications can receive it via `@EventListener` or Spring's `ApplicationListener` mechanism.

Operationally, the event tells you:

1. Which listener/consumer the monitor flagged as unresponsive.
2. How long it has been since poll activity tracked by the container.
3. The corresponding topic-partition/consumer context, per your version's API.
4. A moment to write logs, increment metrics, raise alerts, or trigger a **controlled** recovery action.

It does **not** automatically:

- Stop the listener container or restart the pod.
- Call `consumer.wakeup()` or force `poll()` to exit.
- Commit or roll back offsets.
- Route failing records to the DLT.
- Change assignments or move partitions to another consumer.
- Identify the exact cause blocking the consumer thread.

Therefore, treat the event as part of **observability and incident response**. You must build a separate response policy if automated actions are desired.

## 3. Three parameters determining when the event is published

Key settings live on `ContainerProperties`:

| Property | Meaning | Unit |
|---|---|---|
| `pollTimeout` | Maximum duration passed to the consumer `poll()` call in normal cycles. | Milliseconds. |
| `noPollThreshold` | Threshold multiplier used to determine the consumer has gone too long without poll progress per the monitor. | Unitless factor. |
| `monitorInterval` | Interval between monitor checks of consumer status. | Seconds. |

Under common Spring Kafka defaults, `pollTimeout` is **5,000 ms**, `noPollThreshold` is **3.0**, and `monitorInterval` is **30 seconds**. These values can differ due to application configuration or framework version; always inspect the listener container's effective values when investigating.

Approximate time threshold:

```text
T_threshold ≈ pollTimeout × noPollThreshold
```

If `pollTimeout = 5,000 ms` and `noPollThreshold = 3.0`:

```text
T_threshold ≈ 5,000 × 3 = 15,000 ms = 15 seconds
```

The monitor does not run continuously every millisecond. If `monitorInterval = 30 seconds`, detection time depends on the phase of the monitor sweep; it can be later than the exact moment the threshold was crossed. **Do not treat a 15-second threshold as a guarantee the event appears at the exact 15th second.**

### Threshold adjustment examples

| `pollTimeout` | `noPollThreshold` | Calculated threshold | `monitorInterval` |
|---:|---:|---:|---:|
| 5,000 ms | 3.0 | 15 seconds | 30 seconds |
| 5,000 ms | 6.0 | 30 seconds | 10 seconds |
| 1,000 ms | 5.0 | 5 seconds | 5 seconds |
| 10,000 ms | 3.0 | 30 seconds | 15 seconds |

The rows are illustrative examples, not a fixed recommendation table. Lowering thresholds too far can cause continuous alerts whenever a listener occasionally processes a record slower than usual.

## 4. Configuring the monitor in ConcurrentKafkaListenerContainerFactory

A clear way to configure this is directly on the listener container factory's `ContainerProperties`:

```java
@Configuration
public class KafkaMonitorConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            monitoredKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);

        // Timeout per poll: 5 seconds.
        factory.getContainerProperties().setPollTimeout(5_000L);

        // Flag unresponsive when elapsed time exceeds
        // roughly 3 times the poll timeout.
        factory.getContainerProperties().setNoPollThreshold(3.0f);

        // Monitor checks on a 10-second cycle.
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

Listeners wanting this factory must reference the exact name:

```java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "monitoredKafkaListenerContainerFactory"
)
public void onOrder(ConsumerRecord<String, String> record) {
    orderService.process(record.value());
}
```

When Spring Boot creates a default factory or the application has multiple factories, verify events come from the **actual factory/container running the listener**. Configuring a factory that the listener does not use will not change that listener's behavior.

`monitorInterval` is a monitoring period **in seconds**, whereas `pollTimeout` is expressed **in milliseconds**. Confusing units can create overly aggressive monitoring, delayed alerts, or completely unexpected behavior.

## 5. Receiving NonResponsiveConsumerEvent with @EventListener

Example listener recording logs and metrics per event:

```java
@Component
public class NonResponsiveConsumerMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(NonResponsiveConsumerMonitor.class);

    private final MeterRegistry meterRegistry;

    public NonResponsiveConsumerMonitor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer not responsive: listenerId={}, " +
            "timeSinceLastPollMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());

        meterRegistry.counter(
                "app.kafka.consumer.nonresponsive.events",
                "listener", event.getListenerId())
                .increment();
    }
}
```

Key imports:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;
```

The example assumes the application already configured Micrometer `MeterRegistry`. `app.kafka.consumer.nonresponsive.events` is a **custom application metric**, not a mandatory default metric name from Spring Kafka.

`getTimeSinceLastPoll()` represents the milliseconds the event reports the consumer has gone without poll progress as measured by the container. `getListenerId()` correlates with the endpoint/container; `getTopicPartitions()` provides partition context when available. Check exact API/event field signatures against the Spring Kafka version used by your project.

In applications with many listeners, also log `application`, `pod`, `consumerGroup`, `listenerId`, and `topicPartition`. There is no need to log record payloads just to detect an unresponsive consumer; this event is not a business record being processed.

## 6. Events can repeat and do not equal new incidents

If the consumer remains stuck across multiple `monitorInterval` cycles, the application can receive **multiple `NonResponsiveConsumerEvent` instances for the same condition**. If every event opens a ticket, pages directly, or restarts the consumer, the system creates a notification storm and recovery loop.

Alert design should include:

- **Deduplication** by listener ID, instance, and incident window.
- **Cooldown** between repeated alerts for the same cause.
- **Escalation** when the condition persists or multiple members are affected.
- **Resolved signal** when the consumer resumes normal polling, measured via real metrics/health.
- **Never assume** one event means a newly broken consumer.

Example logic:

```text
T0: first NonResponsiveConsumerEvent received
    -> log warning; mark incident OPEN

T1: subsequent events for same listener/pod
    -> increment counter, update duration; do not open new incident

T2: poll operates normally and lag progresses
    -> confirm recovery; close incident
```

Merely receiving no further events is not enough to conclude the consumer is healthy: the container may have stopped or the pod may have crashed. Combine container state, group assignment, poll rate, committed offsets, and downstream application health.

## 7. Why not call KafkaConsumer arbitrarily in event handlers?

Kafka `Consumer` is not thread-safe. `NonResponsiveConsumerEvent` is published by the monitoring mechanism, which may not run on the same thread calling `poll()`. Therefore, **never arbitrarily call `consumer.poll()`, `commitSync()`, `seek()`, or `pause()` on the consumer obtained from the event**.

Spring Kafka provides `MessageListenerContainer` APIs to control lifecycle, pause/resume, and certain coordinated operations. When you need to manipulate a consumer in the proper thread context, use framework-supported mechanisms instead of passing raw consumers through asynchronous callbacks.

Kafka `Consumer.wakeup()` is a notable exception: it is designed to be callable from another thread to wake up `poll()` or certain blocking methods. However:

- `wakeup()` can raise `WakeupException` on the consumer thread.
- It is an intervention into the poll flow, **not a safe default recovery action**.
- If the consumer is blocked in business code, DB locks, or operations unresponsive to Kafka wakeup, `wakeup()` will not cure the root cause.
- Verify how the Spring container handles wakeup and lifecycle in your current version.
- Do not call wakeup repeatedly on every event without limits/cooldowns.

Example **solely to illustrate the mechanism, not as a default policy**:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.error("Consumer appears stuck: {}", event.getListenerId());

    // Enable only when approved by runbook and guarded by safety checks.
    // if (recoveryPolicy.shouldWakeup(event)) {
    //     event.getConsumer().wakeup();
    // }
}
```

In many systems, a better first step is **collecting thread dumps, logs, and metrics** before stopping/restarting. Restarting immediately can destroy deadlock evidence and trigger an unnecessary rebalance.

## 8. Distinguishing poll timeout from max.poll.interval.ms

Two similarly named settings address different problems:

| Setting | Component | Role |
|---|---|---|
| `ContainerProperties.pollTimeout` | Spring Kafka container | How long each Kafka `poll()` call waits for records during normal operation. |
| `noPollThreshold` | Spring Kafka container | Threshold factor used by the monitor to detect an unresponsive consumer. |
| `monitorInterval` | Spring Kafka container | Interval at which the monitor evaluates poll status. |
| `max.poll.interval.ms` | Kafka consumer client | Time limit between `poll()` calls per consumer group rules; exceeding it can cause membership loss/rebalance. |
| `session.timeout.ms` | Kafka consumer/group protocol | Governs detecting a member no longer responding to heartbeats per group mechanics. |

**`NonResponsiveConsumerEvent` does not mean Kafka has already exceeded `max.poll.interval.ms`.** Spring Kafka's monitor has its own threshold and may publish the event before the client is actually evicted by the group coordinator, or detect it later depending on configuration.

Example:

```text
pollTimeout          = 5 seconds
noPollThreshold      = 3
monitorInterval      = 10 seconds
max.poll.interval.ms = 300 seconds

Monitor threshold is approximately 15 seconds.
Group poll interval threshold is 300 seconds.
```

A `NonResponsiveConsumerEvent` at a few tens of seconds does not prove the consumer lost its assignment. Conversely, if the listener stays stuck for several minutes, Kafka can trigger group timeout and rebalance; in that case, the early event provides a warning before the incident widens.

## 9. Blocked poll or overly slow listener processing?

This is the most important triage question. The event states the consumer is not progressing in polling; the cause could be:

**Case A — Stuck inside Kafka client `poll()`:**

```text
Consumer thread
  -> KafkaConsumer.poll()
       -> network/coordinator/selector ...
          (waiting abnormally)
```

Investigate broker/network, DNS, TLS, coordinator, client logs, Kafka request latency, and thread dumps.

**Case B — Poll returned records yet listener holds the thread too long:**

```text
Consumer thread
  -> KafkaMessageListenerContainer.invokeListener(...)
       -> OrderService.process(...)
            -> RestClient.execute(...)
               (very long HTTP timeout)
```

Investigate dependency timeouts, thread pools, database locks, and record processing. Do not focus on fixing the Kafka broker if thread dumps show the consumer is stuck in an HTTP client.

**Case C — JVM stop-the-world GC or CPU starvation:**

```text
Multiple application threads stop progressing together
Long GC pause / CPU throttling / scheduler starvation
```

Investigate GC logs, CPU quotas, container throttling, and memory pressure. If the entire JVM shows signs of stalling, a Kafka-specific restart may merely hide a resource issue.

**Case D — Blocked transaction or rebalance callback:**

```text
Consumer thread
  -> commit callback / after rollback /
     rebalance listener / transaction integration
       -> blocking operation
```

Evaluate application-written callbacks, processing durations, deadlocks, and transaction coordinator status.

## 10. Correlation with consumer lag and group assignment

When a consumer does not poll, committed offsets may stop advancing and consumer lag can rise if producers keep writing records. Yet **rising lag does not necessarily mean the consumer is stuck in poll**: it can also come from input load exceeding throughput, heavy retries, or intentionally paused partitions.

Example:

```text
orders-2
  committed offset = 150
  log end offset   = 350
  lag              = 200

After 60 seconds:
  committed offset = 150
  log end offset   = 550
  lag              = 400
```

If `NonResponsiveConsumerEvent` also occurs for the listener owning `orders-2` around the same time, that is a strong signal to investigate the consumer thread. Still, verify:

- Is the partition currently assigned to the consumer?
- Is the container paused globally or per-partition?
- Is a record retrying/processing inside a long listener invocation?
- Did the group rebalance and change assignments?
- Is the producer actually still writing data?

You can inspect the group via CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members --verbose
```

These commands show assignments, members, committed offsets, and lag. Kafka CLI **does not directly reflect Spring's `NonResponsiveConsumerEvent`**; that event is emitted inside the JVM and must be read from application logs/metrics.

## 11. NonResponsiveConsumerEvent vs. other application events

Spring Kafka has multiple events related to consumer lifecycle and pause/resume:

| Event | Signal | What not to misunderstand |
|---|---|---|
| `NonResponsiveConsumerEvent` | Monitor detects consumer failed to advance polling past threshold. | Does not prove broker is down or assignment is lost. |
| `ConsumerPausedEvent` | Consumer/container paused at the corresponding level. | Not necessarily an incident; may be operational pause. |
| `ConsumerResumedEvent` | Consumer/container resumed. | Does not guarantee backlog is cleared. |
| `ConsumerPartitionPausedEvent` | A partition was paused via supported API. | Does not make the Kafka group move the partition to another member. |
| `ConsumerPartitionResumedEvent` | A partition was resumed. | Does not prove listener processing succeeded. |
| `ConsumerStoppedEvent` | Consumer thread/container stopped, with reason per version. | Not the sole indicator of a non-responsive poll. |

Events can appear close together during an incident. For example, a listener hangs, the monitor emits `NonResponsiveConsumerEvent`, an operator stops the container, and then `ConsumerStoppedEvent` arrives. This is a **state sequence**, not multiple independent incidents.

When a container is intentionally paused, understand how the monitor measures polling in your current version; do not assume "paused" means "non-responsive consumer." When paused properly, the container can still continue calling `poll()` to maintain group membership.

## 12. Designing alerts with sensible thresholds

Do not set `noPollThreshold` low just to generate more alerts. Choose settings based on:

1. Actual `pollTimeout` of the listener container.
2. Normal record processing time and p99 processing latency.
3. HTTP/database timeouts and retry/backoff settings.
4. `max.poll.interval.ms` and consumer group stability requirements.
5. Desired alert latency, `monitorInterval`, and cost of false positives.
6. The application's ability to self-recover after a slow downstream spell.

For instance, a service with p99 record processing around 2 seconds and `pollTimeout=5s` might start with a monitor threshold around a few tens of seconds and tune from metrics. By contrast, a service processing 90-second batches needs its own policy; a 15-second threshold can alert on valid batches, though it remains a sign worth checking regarding `max.poll.interval.ms`.

Consider two alert tiers:

- **Warning:** a listener exceeds the non-responsive threshold for one or a few monitor sweeps, with no sign of losing group membership yet.
- **Critical:** multiple members affected simultaneously, lag spiking, committed offsets stalled for long periods, continuous group rebalances, or downstream SLA violations.

Using exactly two tiers is not mandatory; what matters is distinguishing **transient symptoms** from **incidents needing urgent intervention**.

## 13. Avoiding restart storms during auto-recovery

A naive automation:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    container.stop();
    container.start();
}
```

**Do not deploy this pattern.** Events can repeat, the monitor thread may differ from the consumer thread, stop/start has its own lifecycle, and closely spaced events can trigger continuous restarts, rebalance storms, or mask the root cause.

A better self-healing controller needs to:

- Record first detection time, repetition count, and duration.
- Capture thread dumps or stack info before intervening if permitted by the system.
- Trigger recovery only when an **explicit policy** is met (e.g., repeatedly no progress across multiple monitor checks, not currently deploying, not intentionally paused).
- Cap restarts within a time window and enforce a cooldown.
- Coordinate lifecycle on an appropriate thread/executor without blocking the event listener.
- Verify Kafka group rejoin, assignment, committed offsets, and lag after restart.
- Escalate to operators if it fails to recover or immediately recurs.

When the consumer uses Kafka transactions, restarting can abort in-flight transactions and cause record redelivery. Ensure listeners are idempotent and control external side effects before automating stop/start.

## 14. Runbook: NonResponsiveConsumerEvent after deployment

Suppose after deploying a new release, logs show:

```text
Kafka consumer not responsive:
listenerId=orders-consumer-0
timeSinceLastPollMs=48000
partitions=[orders-2, orders-5]
```

This is an illustrative application log, not a mandatory default format of Spring Kafka.

**Step 1 — Determine scope.** How many pods/listeners see the event? Which topics/partitions are assigned? Is one instance affected or all consumers in the group?

**Step 2 — Gather state.** Collect event timestamps, `pollTimeout`, `noPollThreshold`, `monitorInterval`, `max.poll.interval.ms`, committed offsets, lag, and deployment status.

**Step 3 — Capture thread dumps.** Locate whether the consumer thread is inside `poll()`, listener code, HTTP/DB calls, commit/transaction, or callbacks. Do not conclude root cause solely from the exception/event name.

**Step 4 — Check the Kafka cluster.** Inspect broker/controller/coordinator health, network, DNS/TLS, request latency, and client logs if the thread is waiting on the Kafka client.

**Step 5 — Check dependencies.** If the thread is blocked inside the listener, inspect HTTP/database timeouts, locks, queue depths, thread pools, and circuit breakers.

**Step 6 — Check JVM/host.** Inspect GC pauses, CPU throttling, memory pressure, OOMs, and signs of thread starvation.

**Step 7 — Decide intervention.** Fix dependencies, throttle concurrency, pause consumption, adjust timeouts, or perform a controlled restart. Never "fix" it by raising `noPollThreshold` merely to hide the incident.

**Step 8 — Verify recovery.** Consumer returns to normal polling, group assignments stabilize, committed offsets advance, lag drops, and error rates/DLT do not spike abnormally.

**Step 9 — Post-incident follow-up.** Archive thread dumps/metrics, document root cause, improve timeouts or instrumentation, and update runbooks so next time does not trigger a restart storm.

Do not reset consumer offsets or seek to log end simply because a consumer got stuck; those actions can skip unprocessed records.

## 15. When the event appears yet the pod remains Ready

A Kubernetes `readinessProbe` may check an HTTP endpoint returning 200 while the Kafka consumer thread is blocked. The JVM stays alive, HTTP threads remain free, and the pod continues receiving traffic, so Kubernetes does not replace the pod automatically.

A health signal for Kafka consumption can combine:

- Most recent `NonResponsiveConsumerEvent` and elapsed time since then.
- Last poll/offset commit timestamp from appropriate container/metrics.
- Listener container running state and assigned partitions.
- Whether consumer lag is growing.
- Whether the container is intentionally paused for an incident.
- Group rebalances or other exceptions around the same time.

Do not necessarily turn **every** `NonResponsiveConsumerEvent` into an immediate readiness failure; if readiness flaps continuously, the system can trigger widespread pod restarts/rebalances simultaneously. Prefer alerting first, bounded self-recovery second, and failing readiness only when the consumer truly violates SLOs.

Liveness failure can cause Kubernetes to restart the pod; that is a heavy action that must be weighed carefully when records have uncommitted side effects. If applied, ensure idempotency, grace periods, and sufficient group capacity to handle replacement members.

## 16. Testing event behavior

For integration tests, use Kafka Testcontainers or embedded Kafka, a real listener container, and a simulated dependency. Scenario:

1. Create a test topic and consumer group, and configure `pollTimeout`, `noPollThreshold`, and `monitorInterval` small enough for tests without being so tight as to cause flakiness.
2. Create a normal listener and confirm the consumer receives records.
3. Simulate a blocked handler (e.g., `CountDownLatch`) or a slow dependency **in an isolated test environment**.
4. Listen for `NonResponsiveConsumerEvent` using an `@EventListener` bean, recording listener ID and elapsed time.
5. Wait for the event with a timeout-bounded await instead of a fixed `Thread.sleep`.
6. Release the latch so the listener resumes; confirm the consumer keeps polling and committed offsets advance per ack mode.
7. If needed, confirm the monitor stops emitting alerts once the consumer operates normally again.
8. Add a test for proper pausing to separate intentional pauses from blocked consumers.

Never intentionally lock consumer threads or call Kafka `Consumer.wakeup()` on production topics for testing. Scenarios capable of triggering group rebalances or duplicate processing must use isolated environments and dedicated consumer groups.

When testing with a blocking listener, the simulated dependency timeout should be shorter than `max.poll.interval.ms` or the test must explicitly handle rebalance possibilities. Do not consider a test failed just because no event appeared at the exact threshold second: `monitorInterval` introduces detection latency.

## 17. Common operational mistakes

| Symptom | Possible cause | How to handle |
|---|---|---|
| Repeated `NonResponsiveConsumerEvent` for same listener | Consumer remains stuck across multiple monitor sweeps. | Deduplicate alerts; inspect thread dumps, do not restart on every event. |
| Event after a long processing batch | Listener does not return to poll fast enough. | Measure batch duration, lower `max.poll.records`, or optimize dependencies/timeouts. |
| Event appears even when broker is healthy | Consumer thread blocked in business code, DB, or JVM stall. | Inspect consumer thread stack trace and non-Kafka metrics. |
| No event seen despite rising consumer lag | Consumer still polling yet processing slowly, intentionally paused, or monitor cycle not reached. | Check `monitorInterval`, pause state, listener throughput, and offsets. |
| Group continuously rebalances after event | Processing exceeds `max.poll.interval.ms` or restart storm. | Inspect processing/poll durations, restart policy, and group logs. |
| `wakeup()` fails to unstick consumer | Thread stuck in HTTP/DB or deadlock outside Kafka. | Fix the root blocker in stack trace; do not call wakeup repeatedly. |
| Alert does not identify failing instance | Metrics only tagged with topic or group, missing listener ID/pod. | Add listener ID, instance/pod, timestamp, and assignment to logs. |
| Events stop yet lag does not drop | Consumer stopped, holds no assignments, or keeps failing during processing. | Check container state, group assignment, committed offsets, and DLT. |
| Monitor alerts too frequently | `noPollThreshold` too low for real processing durations. | Tune after measuring p99 processing latency and `max.poll.interval.ms`. |

## 18. Operational principles

- Treat `NonResponsiveConsumerEvent` as **a symptom that the consumer is not progressing in polling**, not a root-cause conclusion.
- Understand the relationship among `pollTimeout`, `noPollThreshold`, and `monitorInterval`, especially milliseconds versus seconds.
- Receive events via `@EventListener` and log listener ID, elapsed time, partition context, and instance/pod.
- Separate Spring Kafka's monitor alerts from Kafka client `max.poll.interval.ms` and group membership.
- Never call non-thread-safe `KafkaConsumer` methods from event listeners; use `wakeup()` only when governed by an approved recovery policy.
- Never stop/start containers or restart pods on **every** event without deduplication, cooldowns, and guardrails.
- Prioritize thread dumps, dependency latency, broker/client logs, GC, and CPU metrics to find root causes.
- Combine the event with group assignment, committed offsets, lag, retry/DLT, and business throughput.
- Never reset offsets to clear lag before determining which records were already processed.
- Verify side effects/idempotency if an in-flight transaction or listener invocation can be aborted and redelivered after restart.
- Test in isolated environments with controlled listener blocking; never break production consumers to verify event emission.

**`NonResponsiveConsumerEvent`** adds an important monitoring layer to Spring Kafka: the application can detect when a consumer thread appears not to return to polling within the threshold, even while the JVM and pod remain alive. Reliability does not come from the event merely being published—it comes from how operations **set sensible thresholds, gather evidence, perform bounded recovery, and confirm that offsets and business processing genuinely resume advancing**.
