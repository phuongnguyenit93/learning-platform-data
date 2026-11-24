# NonResponsiveConsumerEvent

In a Spring Kafka application, a consumer may stop receiving records either because **the topic currently has no new data** or because **the consumer thread is no longer executing its `poll()` loop on schedule**. On the surface, both look similar—the listener goes quiet and processed record counts stop climbing—yet investigation and recovery differ completely.

`NonResponsiveConsumerEvent` is a Spring Kafka application event designed to warn about the second case: the listener container detects that the time elapsed since `poll()` activity exceeds the monitoring threshold. The event surfaces consumers at risk of being stuck in Kafka client calls, listener business code, transactions, callbacks, or starved of JVM CPU needed to progress.

In the **Idle and Non-Responsive** chapter of Spring Kafka Reliability Operations, what matters is not merely receiving the event, but distinguishing it from **idle events** when the consumer is still polling normally, understanding detection thresholds, gathering evidence, and avoiding automated reactions that cause continuous consumer group rebalances or duplicate data processing.

## 1. How does an idle consumer differ from a non-responsive consumer?

A Spring Kafka listener container drives the Kafka consumer in a loop:

```text
           +--------------------+
           | consumer.poll(...) |
           +----------+---------+
                      |
               +------+------+
               |             |
           No records    Has records
               |             |
               |             v
               |       @KafkaListener
               |       processes record
               |             |
               +------+------+
                      |
                      v
                Polling continues
```

When a topic has no new records, `poll()` returns an empty batch and the container keeps polling. That is **data idle**, which is often completely normal. In a non-responsive situation, the container observes that the consumer has made no poll progress for an abnormally long time.

| State | Consumer still polling? | Listener receiving records? | Initial assessment |
|---|---|---|---|
| Topic has no new records | Usually yes. | No. | Likely normal idle. |
| Partition intentionally paused | Container usually keeps polling to stay in group. | No new records from paused partitions. | Controlled consumption state. |
| Listener takes very long on a record | May not have returned to next poll yet. | Busy processing received record. | May become non-responsive if threshold breached. |
| Consumer stuck in Kafka client or callback | Poll not progressing as expected. | May receive no new records. | Investigate non-responsiveness. |
| Container stopped | Consumer loop no longer running. | No. | Lifecycle stopped, not merely idle. |

**No messages** does not mean **hung consumer**. Conversely, a thread stuck mid-record can stall throughput metrics even while Kafka itself is healthy.

## 2. Distinguishing Spring Kafka application events

Key events in the idle and non-responsive family:

| Event | Condition reflected | Usage |
|---|---|---|
| `ListenerContainerIdleEvent` | Container received/delivered no new records within configured `idleEventInterval`. | Monitor quiet topics, trigger idle-appropriate actions. |
| `ListenerContainerNoLongerIdleEvent` | Container resumes receiving data after an idle state. | Confirm data flow has resumed. |
| `NonResponsiveConsumerEvent` | Monitor sees poll activity gap exceed threshold. | Alert on risk of blocked or stalled consumer. |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Consumer/container paused or resumed. | Track backpressure control. |
| `ConsumerStoppedEvent` | Consumer/container stopped with reason per API. | Lifecycle and recovery diagnostics. |

Example of a topic receiving order events only every few minutes:

```text
12:00:00 — poll() returns record and listener processes it
12:00:05 — poll() returns empty
12:00:10 — poll() returns empty
12:00:15 — poll() returns empty
...
12:01:00 — idle interval reaches threshold
             -> ListenerContainerIdleEvent may fire
```

This is not `NonResponsiveConsumerEvent`, because the consumer keeps polling steadily.

Conversely:

```text
12:00:00 — poll() returns record
12:00:01 — listener calls HTTP dependency
12:00:35 — HTTP call still blocking, consumer has not polled again
             -> monitor may emit NonResponsiveConsumerEvent
```

**Both look like a silent listener, yet their causes and risk profiles are completely different.**

## 3. What does NonResponsiveConsumerEvent tell you?

The event resides in package:

```java
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

The Spring Kafka listener container includes a monitor that checks how long the consumer has gone without expected poll progress. When the gap exceeds `pollTimeout × noPollThreshold` during a check, the container can publish `NonResponsiveConsumerEvent` through Spring's application event infrastructure.

Event details can be used to:

- Identify the affected listener/container ID.
- Record time elapsed since polling as tracked by the container.
- Identify related topic-partitions from available metadata.
- Correlate the event with pod, thread, consumer group, and incident timeline.
- Increment counters, send deduplicated alerts, or capture diagnostic evidence.

The event **does not by itself prove**:

- The Kafka broker disconnected or the cluster is unavailable.
- The consumer was definitely evicted by the group coordinator.
- The in-flight record failed or was routed to a DLT.
- Committed offsets were lost, reset, or advanced.
- A Java deadlock occurred, as a long-running listener produces the same symptom.

Nor does the event automatically call `stop()`, `restart()`, `seek()`, `commitSync()`, or `wakeup()` to recover. **Detection** and **recovery action** are two separate layers.

## 4. Three key parameters: pollTimeout, noPollThreshold, monitorInterval

`ContainerProperties` lets you configure non-responsive thresholds:

| Setting | Meaning | Unit |
|---|---|---|
| `pollTimeout` | Duration the consumer may wait inside each normal `poll()` call. | Millisecond |
| `noPollThreshold` | Multiplier applied to `pollTimeout` to form the non-responsive threshold. | Unitless |
| `monitorInterval` | Interval between monitor checks. | Second |

Intuitively:

```text
Approximate non-responsive threshold:

T_threshold = pollTimeout × noPollThreshold

Example:
pollTimeout     = 5,000 ms
noPollThreshold = 3.0

T_threshold = 15,000 ms = 15 seconds
```

In common Spring Kafka versions, defaults are `pollTimeout=5,000 ms`, `noPollThreshold=3.0`, and `monitorInterval=30 seconds`. Treat these as reference defaults; in operations, inspect **actual container values**, because Boot/custom factories can override them and framework releases can change defaults.

`monitorInterval` is not the detection threshold; it is the **scan cadence**. If the threshold is 15 seconds while the monitor only scans every 30 seconds, the event may fire well after the threshold was crossed.

Examples:

| `pollTimeout` | `noPollThreshold` | Computed threshold | `monitorInterval` |
|---:|---:|---:|---:|
| 5,000 ms | 3.0 | 15 seconds | 30 seconds |
| 5,000 ms | 6.0 | 30 seconds | 10 seconds |
| 2,000 ms | 4.0 | 8 seconds | 5 seconds |
| 10,000 ms | 3.0 | 30 seconds | 15 seconds |

These numbers only illustrate the math, not a universally optimal preset. Too low a threshold causes false positives for listeners with legitimate long processing; too high a threshold delays detecting stuck consumers.

## 5. Configuring a monitored listener container

Example using `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerMonitorConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            monitoredListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setNoPollThreshold(4.0f);
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

This configuration sets a non-responsive threshold of roughly 20 seconds with the monitor scanning every 10 seconds. Listener using the factory:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "monitoredListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        orderService.process(record.key(), record.value());
    }
}
```

In applications with multiple listener factories, configuring `monitoredListenerFactory` does not automatically update listeners still using the default factory. Confirm `containerFactory` on each endpoint or shared configuration actually in use.

Furthermore, `pollTimeout` is a **container** setting, whereas `max.poll.interval.ms` is a **Kafka consumer client** setting. The two do not replace each other.

## 6. Receiving events with @EventListener

Use a Spring event listener to log and count alert occurrences:

```java
@Component
public class ConsumerResponsivenessMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerResponsivenessMonitor.class);

    private final MeterRegistry metrics;

    public ConsumerResponsivenessMonitor(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer non-responsive: listenerId={}, " +
            "elapsedMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());

        metrics.counter(
                "app.kafka.nonresponsive.events",
                "listener", event.getListenerId())
                .increment();
    }
}
```

Illustrative imports:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;
```

`getTimeSinceLastPoll()` reports the elapsed milliseconds observed by the event from container poll tracking. `getTopicPartitions()` gives related topic-partition context. `getListenerId()` identifies the listener/container; in multi-replica deployments, include pod/instance and consumer group in logs.

`app.kafka.nonresponsive.events` is a **custom metric name**, not a default Spring Kafka metric. To avoid high cardinality, never put event IDs, offsets, or full dynamic topic-partition lists into Prometheus labels arbitrarily.

**Note:** if no `MeterRegistry` bean is configured, omit the metric lines above or include Micrometer properly. Keep event callbacks fast; never run slow HTTP/DB calls or block the publishing thread.

## 7. Monitoring idle and non-responsive side by side

To avoid confusing "no new records" with "stuck consumer", observe `ListenerContainerIdleEvent` alongside it:

```java
@Configuration
class KafkaIdleConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            idleAwareListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);

        // Emit idle event when no messages arrive for 60 seconds.
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        // Still monitor non-responsiveness via poll monitor.
        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setNoPollThreshold(4.0f);
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Example event listener:

```java
@Component
public class IdleAndStuckConsumerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(IdleAndStuckConsumerEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info("Kafka listener idle: {}", event.getListenerId());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be stuck: listenerId={}, elapsedMs={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll());
    }
}
```

Here `ListenerContainerIdleEvent` and `NonResponsiveConsumerEvent` measure **two distinct phenomena**. If a listener receives no messages while continuing to poll steadily, idle events are expected without non-responsive events. If a listener blocks during processing, the monitor can emit non-responsive events even while the topic keeps receiving new data.

Never use idle events as a default trigger to restart pods: on low-traffic topics, a healthy consumer can stay idle for hours.

## 8. Distinguishing noPollThreshold from max.poll.interval.ms

`max.poll.interval.ms` is a Kafka consumer group rule: if the gap between `poll()` calls exceeds the limit, the consumer risks being deemed stalled and losing group membership per client/coordinator behavior. `NonResponsiveConsumerEvent` relies instead on Spring Kafka's monitor threshold.

Configuration example:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 300
```

Suppose the container has:

```text
pollTimeout             = 5 seconds
noPollThreshold         = 4.0
monitorInterval         = 10 seconds
max.poll.interval.ms    = 300 seconds

Monitor threshold ≈ 20 seconds
Kafka poll interval limit = 300 seconds
```

At 25–30 seconds, `NonResponsiveConsumerEvent` may already fire, yet the group has not necessarily rebalanced. The event is an **early warning**, not confirmation that Kafka's `max.poll.interval.ms` was breached.

Conversely, if listener code takes many minutes per record, the consumer can lose assignments after breaching Kafka's limit; early monitor detection helps operations intervene before risk escalates.

Never crank `max.poll.interval.ms` excessively high just to dodge rebalances when business code hangs. Evaluate `max.poll.records`, batch duration, external timeouts, and retry policies to keep polling within sensible bounds.

## 9. Common causes of non-responsiveness

### 9.1. Listener calling slow dependencies

Example:

```java
@KafkaListener(topics = "orders")
public void processOrder(String payload) {
    // If the HTTP client lacks a timeout, the consumer thread can be held for a long time.
    inventoryClient.reserve(payload);
}
```

If `inventoryClient.reserve` waits indefinitely, the container never returns to poll. The monitor may report non-responsiveness even while Kafka brokers and partition assignments are completely healthy.

**Resolution:** enforce connect/read/response timeouts, circuit breakers, bulkheads, and bounded retries; avoid blocking the consumer thread unnecessarily.

### 9.2. Database locks or connection pool exhaustion

The consumer thread blocks waiting for a connection or waiting on a transaction lock:

```text
Kafka consumer thread
  -> OrderService.save(...)
     -> HikariCP getConnection()
        or PostgreSQL lock wait
           (blocks for a very long time)
```

Check active/idle/pending connections, query latency, deadlocks, lock contention, and transaction timeouts.

### 9.3. Blocking Kafka client, commits, or transactions

The consumer may be waiting on networking, the coordinator, `commitSync()`, callbacks, or a Kafka transactional producer. Thread dumps and Kafka client logs distinguish this from slow listener logic.

### 9.4. GC pauses, CPU starvation, or deadlocks

If the JVM suffers long stop-the-world GC pauses or CPU throttling, multiple threads stall simultaneously. In that case the problem is not Kafka-specific; restarting the listener container may not fix the root cause.

### 9.5. Thread-blocking backoffs or user code

A long `Thread.sleep(...)`, an untimed `Future.get()`, or synchronous retries whose total duration grows too large can keep the consumer from polling. Use bounded backoff policies, track total duration, and consider retry topics if ordering/transaction constraints permit.

## 10. Can the event be used to automatically wake up the consumer?

`NonResponsiveConsumerEvent` provides context about the consumer. Kafka's `Consumer.wakeup()` is designed to be called from another thread to wake a consumer out of wakeup-aware blocking operations. However, **do not call `wakeup()` automatically on every event**:

- `wakeup()` can trigger `WakeupException` on the consumer thread.
- If the thread is blocked in HTTP/database I/O or an application deadlock outside Kafka, `wakeup()` will likely do nothing.
- The container has its own lifecycle and error handling; interfering requires understanding how the container handles `WakeupException`.
- Repeated calls across events can destabilize the container, increase rebalances, and generate more errors.

Conceptual illustration—**log only by default, do not auto-wakeup**:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.error("Consumer seems stuck: {}", event.getListenerId());

    // Only when an approved runbook/control mechanism permits:
    // if (recoveryPolicy.shouldWakeup(event)) {
    //     event.getConsumer().wakeup();
    // }
}
```

Kafka `Consumer` is not safe for arbitrary cross-thread use; `wakeup()` is a special-case exception. **Never call `event.getConsumer().poll()`, `commitSync()`, or `seek()` from a monitoring callback.**

Prioritize capturing thread dumps, consumer group state, and metrics before altering lifecycle. If stop/restart is truly required, coordinate via container APIs and a dedicated executor with cooldowns and attempt limits.

## 11. Why restarting immediately on the event is usually dangerous

A seemingly convenient but unsafe handler:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    container.stop();
    container.start();
}
```

Do **not** deploy that code in production. The monitor can emit repeated consecutive events while the same consumer stays stuck. Stopping/starting the container on each event can cause:

- Rebalance storms across the consumer group.
- Record redeliveries because prior transactions or offsets did not commit.
- Duplicate execution of non-Kafka external side effects.
- Resource waste spawning new consumers without resolving the DB/HTTP outage.
- Loss of thread dumps and root-cause evidence before operators can inspect them.

Automated recovery policies require **deduplication, cooldowns, rate limits, incident state**, and recovery confirmation criteria. When root cause cannot be determined or faults recur, escalate to an operator instead of looping restarts endlessly.

## 12. Thread dumps are critical evidence

When the event fires, inspect what the consumer thread is doing. With JVM access, `jcmd` can capture a thread dump:

```bash
# PID here is the Java process ID in the pod/VM under investigation.
jcmd 1 Thread.print > /tmp/consumer-thread-dump.txt
```

This example assumes the Java process is PID 1; in real environments, identify the actual PID and available `jcmd` tool. If JDK tools are absent from the runtime container, capture thread dumps using your approved operational mechanism.

Stacks to distinguish:

```text
Case A — blocked in application HTTP:
KafkaMessageListenerContainer...
  -> OrderService.process
     -> HttpClient.execute
        -> socket read

Case B — blocked in database:
KafkaMessageListenerContainer...
  -> OrderRepository.save
     -> JDBC execute
        -> database lock/connection wait

Case C — Kafka client/coordinator:
KafkaMessageListenerContainer...
  -> KafkaConsumer.poll / commit
     -> NetworkClient / coordinator...

Case D — JVM-wide stall:
Multiple threads stalled simultaneously,
CPU throttling / long GC / deadlock
```

A thread dump is a single snapshot, not absolute proof; compare multiple samples taken intervals apart when possible alongside dependency timeouts, heap/GC metrics, and Kafka logs to avoid misdiagnosis.

## 13. Correlating events with consumer lag and assignments

A non-responsive consumer can freeze committed offsets while producers keep writing. Example:

```text
Topic: orders; partition: 2

T0:
  committed offset = 1,200
  log-end offset   = 1,300
  lag              = 100

T1 (after 5 minutes):
  committed offset = 1,200
  log-end offset   = 2,100
  lag              = 900
```

If `NonResponsiveConsumerEvent` arrives during that same window from the listener owning partition 2, investigate urgently. Still, lag can also grow if throughput trails producer rate, failing records are retrying, or partitions are intentionally paused.

Inspect the consumer group via Kafka CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-service

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-service \
  --members --verbose
```

The CLI inspects members, assignments, offsets, and lag. It **does not know Spring Kafka just emitted `NonResponsiveConsumerEvent`**; that signal must come from the application. Correlate event logs with pod, consumer group, partition ownership, listener/container ID, and timestamps.

## 14. Non-responsiveness during intentional pauses

Spring Kafka `pause()` and `pausePartition(...)` instruct the container to stop delivering new records for the paused scope, yet the consumer usually keeps polling to preserve group membership. Therefore:

- Receiving no messages from a paused partition is **expected behavior**.
- Presence or absence of `ListenerContainerIdleEvent` depending on config does not prove the consumer is stuck.
- `NonResponsiveConsumerEvent` while paused still requires checking whether the consumer thread genuinely stopped advancing polls or another task is blocking it.
- Pausing does not abort an already running transaction or cancel records already fetched prior to the pause.

If your team uses pause to protect overloaded dependencies, expose **intentional pause state** in monitoring to avoid false throughput/lag alerts. At the same time, do not disable non-responsive alerts simply because a container is paused: the consumer still needs healthy polling and lifecycle progression.

## 15. Multi-instance deployments and container IDs

A `@KafkaListener` running with `concurrency > 1` spawns multiple child containers/consumer threads. In Kubernetes, multiple pods of the same service share the same application-level listener ID.

Example:

```text
orders-service
  Pod A
    orders-consumer-0 -> orders-0, orders-3
    orders-consumer-1 -> orders-1

  Pod B
    orders-consumer-0 -> orders-2, orders-5
    orders-consumer-1 -> orders-4
```

Assignments are illustrative; the Kafka assignor decides actual mappings. If an alert only includes `listenerId=orders-consumer-0` without pod/instance, operators cannot tell which consumer actually stalled.

Structured logs should include:

```text
event=kafka_consumer_nonresponsive
service=orders-service
instance=orders-service-pod-a
listener_id=orders-consumer-0
consumer_group=orders-service
elapsed_ms=48000
assigned_partitions=orders-0,orders-3
action=ALERT_ONLY
```

This is an application-generated format example, not a built-in Spring Kafka log format.

When a partition moves to a new pod via rebalance, older events only reflect the owner at emission time. If automated recovery is used, orchestration must check the **current owner** rather than sending stop/pause commands to a pod that already lost assignment.

## 16. Monitoring and deduplicated alerting

`NonResponsiveConsumerEvent` can emit repeatedly across multiple `monitorInterval` cycles while the stall persists. Do not create a new ticket or page on every individual event.

Signals to combine:

| Signal | Meaning |
|---|---|
| `NonResponsiveConsumerEvent` count per listener/instance | Detects stuck or prolonged-processing symptoms. |
| Time since poll reported by event | Measures stall severity relative to monitor threshold. |
| Listener invocation duration | Separates legitimately slow work from blocked Kafka polls. |
| Consumer committed offsets and lag | Confirms whether processing progress has halted. |
| Consumer group rebalance rate | Detects membership loss or restart storm impacts. |
| Dependency p95/p99 latency, timeout rate | Pinpoints HTTP/DB calls holding the consumer thread. |
| JVM GC pauses, CPU throttling, thread pools | Uncovers resource contention or thread starvation. |
| Retry/DLT ingress and transaction aborts | Shows whether failing records are moving to recovery flows. |

Apply cooldowns to repeated alerts, and close incidents only when polling/processing recovers **and** committed offsets or business throughput advance again. Absence of new events alone does not prove consumer health; the container may have stopped or the pod restarted.

For multi-consumer systems, add an aggregation layer so a single database outage does not fire separate critical pages for every partition.

## 17. Incident investigation runbook

When receiving `NonResponsiveConsumerEvent` in production:

**Step 1 — Capture context.** Record timestamp, service/pod, listener/container ID, group ID, `getTimeSinceLastPoll()`, and relevant topic-partitions.

**Step 2 — Verify configuration.** Read effective `pollTimeout`, `noPollThreshold`, `monitorInterval`, `max.poll.interval.ms`, and `max.poll.records`. Did anything change in the latest deployment?

**Step 3 — Check lifecycle.** Is the container running, paused, or stopped? Did a rebalance occur? Is the partition still assigned to the event-emitting member?

**Step 4 — Capture thread dump.** Identify whether the consumer thread is blocked in `poll()`, business listener logic, JDBC, HTTP, transactions, or callbacks.

**Step 5 — Check dependencies and JVM.** Inspect broker/coordinator, networking, TLS/auth, database locks, HTTP timeouts, GC, CPU throttling, and thread pools.

**Step 6 — Check Kafka progress.** Are committed offsets frozen? How fast is lag growing? Are there retries/DLT traffic or aborted transactions during the same period?

**Step 7 — Choose root-cause remediation.** Fix the dependency or timeouts; consider controlled pauses; only wakeup/restart when supported by mechanics and runbooks.

**Step 8 — Confirm recovery.** Verify polling resumes, group assignments stabilize, committed offsets advance, lag drops, and business side effects do not duplicate.

**Step 9 — Record postmortem.** Archive thread dumps/metrics and add appropriate timeouts, backpressure, idempotency, or alerts for the future.

Never reset consumer offsets just to drop lag before identifying which records were already processed and which require replay.

## 18. Runbook when events appear right after deployment

After deploying new code, events appear alongside consumer group rebalances:

1. Check listener concurrency and `max.poll.records` changes; larger batches can lengthen a single processing cycle.
2. Check whether modified HTTP clients, JDBC pools, or `@Transactional` boundaries introduced locks or blocking waits.
3. Compare per-record processing times before and after deployment.
4. Check CPU/memory limits, pod restarts, GC, and thread dumps on affected instances.
5. Check consumer assignments and group timeouts; a rebalance does not automatically mean Kafka broker failure.
6. If rolling back, ensure idempotency for records already processed but not yet committed.
7. Confirm after rollback/fix that sustained events stop, offsets advance, and DLT rates stay normal.

Simply raising `noPollThreshold` to silence alerts leaves the processing stall intact and eventually leads to `max.poll.interval.ms` violations. Raise monitor thresholds only when backed by evidence of legitimate workload timing.

## 19. Testing NonResponsiveConsumerEvent

Test using Kafka Testcontainers or an embedded broker and a real listener container:

1. Create a dedicated test topic, consumer group, and listener.
2. Set `pollTimeout`, `noPollThreshold`, and `monitorInterval` small enough for fast tests without making them overly tight and flaky.
3. Register an `@EventListener` to collect `NonResponsiveConsumerEvent`.
4. Send a record causing the listener to block on a `CountDownLatch` longer than the monitor threshold.
5. Use an await condition with a timeout rather than expecting exact mathematical emission timing.
6. Verify the event carries meaningful listener context and elapsed time.
7. Release the latch; verify the listener finishes, the consumer resumes polling, and committed offsets advance per ack mode.
8. Add an empty-topic scenario to test idle behavior separately and avoid confusing it with non-responsiveness.
9. If needed, simulate restarts or rebalances to verify whether recovery causes duplicates.

Never intentionally block production consumers to validate events. In tests, clean up latches and executors even on failure so the test JVM never hangs indefinitely.

## 20. Common misconceptions

| Symptom | Misconception | Correct approach |
|---|---|---|
| Listener logs no new records | Consumer is stuck. | Check if topic has data, poll/idle events, group assignment, and pause state. |
| `ListenerContainerIdleEvent` appears | Broker is unresponsive. | Usually means no records arrived; consumer may still be polling normally. |
| `NonResponsiveConsumerEvent` appears | Broker is definitely down. | Inspect consumer threads, HTTP/DB, transactions, JVM, and Kafka networking. |
| Event fires before `max.poll.interval.ms` | Kafka already evicted consumer from group. | Spring monitor has a separate threshold; check actual group membership. |
| Repeated events appear | Multiple new incidents. | Likely the same consumer stuck across monitor ticks; deduplicate/cooldown. |
| Calling `wakeup()` has no effect | Kafka client doesn't support wakeup. | Thread is likely blocked outside Kafka; fix dependency or deadlock. |
| Lag drops after restart while DLT rises | Fully recovered. | Inspect records sent to DLT and business outcomes. |
| Pod Ready yet non-responsive | Health check cannot be wrong. | HTTP readiness can stay green while Kafka consumer threads are blocked. |
| Paused consumer receives no records | Consumer is non-responsive. | Intentional pause differs from poll stall; check requested/applied state. |

## 21. Operational checklist

- [ ] Clearly distinguish **data idle** from **consumer failing to make poll progress**.
- [ ] Configure `pollTimeout`, `noPollThreshold`, and `monitorInterval` with the right units.
- [ ] Know Kafka client `max.poll.interval.ms` and real p99 processing latency.
- [ ] Capture `NonResponsiveConsumerEvent` via `@EventListener`, logging listener ID and instance/pod.
- [ ] Correlate events with committed offsets, lag, assignments, pause state, and retry/DLT metrics.
- [ ] Enforce timeouts/circuit breakers on dependencies that could block consumer threads.
- [ ] Be able to capture thread dumps and JVM metrics during incidents.
- [ ] Never call `KafkaConsumer` from foreign threads except permitted APIs like `wakeup()` under a strict procedure.
- [ ] Never stop/start pods or containers on every event without cooldowns and idempotency.
- [ ] Never reset offsets to skip backlog without an explicit business decision.
- [ ] Define incident closure criteria based on consumer polling, offsets, and business progress.
- [ ] Test both healthy idle and true non-responsive scenarios in isolated environments.

## 22. Conclusion

`NonResponsiveConsumerEvent` is an essential observability signal for spotting Spring Kafka consumers showing signs of **failing to return to `poll()` on schedule**. It differs fundamentally from `ListenerContainerIdleEvent`: one warns of consumer stagnation, while the other reflects an absence of incoming records over a period.

In operations, treat the event as **the starting point for investigation**, not proof of broker failure or a command to restart immediately. Combining sensible monitor settings, thread dumps, dependency metrics, consumer lag, and group assignments pinpoints root causes; rate-limited recovery, idempotency, and verified business progress resolve incidents without creating duplicates or rebalance storms.
