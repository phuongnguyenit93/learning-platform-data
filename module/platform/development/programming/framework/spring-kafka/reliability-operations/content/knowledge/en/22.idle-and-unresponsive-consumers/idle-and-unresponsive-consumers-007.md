# noPollThreshold in Spring Kafka: detecting consumers that fail to poll on time

In Spring Kafka, a listener may still be running inside the JVM yet **fail to make progress in its `KafkaConsumer.poll()` loop**. Causes can include an abnormally blocked `poll()` call, an overly slow listener, a hung callback, long GC pauses, or consumer thread CPU starvation. These situations are dangerous because externally the service still appears alive, yet message receipt and processing can stall, consumer lag grows, and eventually the consumer group can rebalance.

`noPollThreshold` is a Spring Kafka listener container setting that helps **detect early signs that a consumer has stopped calling poll within the expected timeframe**. It works alongside `pollTimeout` and `monitorInterval`. When the monitoring mechanism sees too much elapsed time since the last poll relative to the configured threshold, Spring Kafka can emit **`NonResponsiveConsumerEvent`** so the application can log, increment metrics, alert, or support diagnostics.

Key points to remember upfront:

- **`noPollThreshold` is not a duration in milliseconds.** It is a *multiplier* applied to the listener container's `pollTimeout`.
- **`monitorInterval` is the check cadence.** Events do not necessarily fire at the exact instant the threshold is crossed.
- **`NonResponsiveConsumerEvent` is a suspicion signal, not proof that the broker is down or the consumer is dead.**
- **`noPollThreshold` does not automatically restart the consumer, commit offsets, cancel the listener, or control `max.poll.interval.ms`.** Recovery policies must be designed separately.

This lesson focuses on understanding this threshold, configuring it in Spring Boot/Spring Kafka, distinguishing non-responsiveness from idle, pause, and rebalance, and designing operations and tests without turning a liveness warning into a data-loss action.

## 1. poll() sits at the heart of the Kafka consumer lifecycle

A Kafka consumer reads records by repeatedly calling `poll()`. With `@KafkaListener`, Spring Kafka's listener container runs this loop, invokes the listener, and coordinates commits, seeks, retries, or transactions according to configuration.

A simplified model:

```text
Spring Kafka listener container
          |
          v
    KafkaConsumer.poll()
          |
          +-- No records --> return to poll after required housekeeping
          |
          +-- Has records --> invoke @KafkaListener
                                  |
                                  +-- Processing succeeds
                                  +-- Acknowledgement / offset
                                  +-- Retry / recovery on error
          |
          v
       next poll()
```

In a synchronous listener model, record processing usually runs on the consumer container's thread. If a listener runs too long, the consumer thread can **fail to return to `poll()` on time**, even though Kafka's `poll()` itself has no error.

Common symptoms:

1. The consumer still appears in the group member list while lag climbs.
2. The JVM still passes HTTP health checks while a consumer thread makes no progress.
3. One slow-processing partition stalls subsequent records behind it.
4. The consumer gets evicted from the group or rebalances after violating poll-related limits.
5. Thread dumps show the consumer thread waiting on an HTTP response, database lock, future, or inside the Kafka client.

`noPollThreshold` helps surface the "too long without polling" signal so operators can investigate **before or while** the impact spreads.

## 2. How is noPollThreshold calculated?

Three parameters form the monitor mechanism:

| Property | Role | Unit |
|---|---|---|
| `pollTimeout` | Maximum timeout passed to a single poll cycle per container config | Milliseconds |
| `noPollThreshold` | Multiplier used to define an abnormally long gap without polling | Unitless |
| `monitorInterval` | Interval at which the monitor task checks poll progress | Seconds in common container APIs |

Conceptual formula:

```text
no-poll threshold time
  = noPollThreshold × pollTimeout
```

Example:

```text
pollTimeout     = 3,000 ms
noPollThreshold = 3.0
monitorInterval = 10 seconds

Alert threshold = 3 × 3,000 ms = 9,000 ms
Monitor task    = checks periodically every 10 seconds
```

If the monitor observes that the elapsed time since the last poll exceeds roughly 9 seconds, the container can emit `NonResponsiveConsumerEvent`.

**Do not interpret "9-second threshold" as a guarantee an event will fire at exactly 9 seconds.** The monitor task only checks on the `monitorInterval` cadence and is affected by schedulers, CPU, GC, and lifecycle. A poll gap exceeding the threshold may be detected later or go unobserved if it finishes before the next monitor check.

### 2.1. An example timeline

```text
Time (seconds)
0        5        9       10       15       20
|--------|--------|--------|--------|--------|
^                                   ^
last poll                            consumer still has not polled

Configured threshold = 9 s
Monitor every 10 s

At t=10: monitor sees elapsed=10s > 9s -> emits event
At t=20: if still not polling, monitor may continue
         reporting non-responsive state depending on implementation
```

This example assumes the monitor schedule aligns cleanly for readability. At runtime, scheduled task phase can drift and exact marks are not guaranteed.

### 2.2. noPollThreshold is not max.poll.interval.ms

`max.poll.interval.ms` is a Kafka consumer client property representing the maximum allowed interval between `poll()` calls before the consumer risks being considered stalled and losing partition ownership under the group protocol.

`noPollThreshold` only controls **Spring Kafka's observation mechanism**. Emitting an event does not itself trigger a Kafka group rebalance. Conversely, Kafka can revoke consumer ownership even before Spring Kafka's monitor emits an event.

The operational goal is typically setting the monitor threshold early enough to leave investigation headroom before the consumer group's liveness limit, while avoiding false alarms during valid longer processing bursts.

## 3. Three time concepts: poll timeout, monitor interval, max poll interval

These durations are frequently confused:

| Configuration | Layer | What it limits/determines |
|---|---|---|
| `pollTimeout` | Spring Kafka container | Wait duration of one `poll()` call |
| `noPollThreshold` | Spring Kafka container | Multiplier to detect prolonged lack of polling |
| `monitorInterval` | Spring Kafka container | Check cadence of the monitor |
| `max.poll.interval.ms` | Apache Kafka consumer | Liveness limit on cadence of `poll()` calls |
| `session.timeout.ms` | Apache Kafka consumer | Detection limit for dead member sessions per group protocol |
| `heartbeat.interval.ms` | Apache Kafka consumer, protocol-dependent | Heartbeat cadence managed by client per config |
| `idleEventInterval` | Spring Kafka container | No-record duration to emit an idle event |

The same number `30000` can mean very different things across these properties.

### 3.1. A low pollTimeout does not equal high throughput

`pollTimeout` governs how long a poll waits when data is absent and how the container loops polling. Setting the timeout too low can wake the poll loop overly often and add unnecessary overhead.

Changing `pollTimeout` from 5 seconds to 1 second while keeping `noPollThreshold=3` also drops the monitor threshold from 15 seconds to 3 seconds. That can be an unexpected **alerting** change if an operator thought they were only tuning latency.

Treat `pollTimeout` and `noPollThreshold` as a pair when setting alerting policies.

### 3.2. Too long a monitorInterval causes late detection

Suppose:

```text
pollTimeout = 2s
noPollThreshold = 3  -> threshold 6s
monitorInterval = 60s
```

Even though the threshold is 6 seconds, the monitor only runs on a 60-second cycle. A 20-second hang may resolve before the monitor checks, producing no expected signal. Choose `monitorInterval` based on acceptable detection lag, scheduling overhead, and poll thresholds.

### 3.3. Changing noPollThreshold does not change max.poll.interval.ms

Raising `noPollThreshold` only makes the monitor less sensitive. It does not increase how long Kafka allows the listener to go without polling. If work genuinely takes long, address architecture, batch size, timeouts, and poll intervals rather than hiding alerts with a large multiplier.

## 4. Configuring noPollThreshold in Java

A clean way is configuring `ContainerProperties` through the listener container factory.

```java
@Configuration
public class KafkaMonitoringConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    ConcurrentKafkaListenerContainerFactoryConfigurer configurer) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        // Keep the customizations Spring Boot configured.
        configurer.configure(factory, consumerFactory);

        var properties = factory.getContainerProperties();

        // Each poll has a 3-second timeout.
        properties.setPollTimeout(3_000L);

        // Monitor suspects non-responsiveness after 3 × 3 seconds.
        properties.setNoPollThreshold(3.0f);

        // Monitor checks periodically every 10 seconds.
        properties.setMonitorInterval(10);

        return factory;
    }
}
```

This setup shows how to preserve Spring Boot auto-configuration while tuning poll monitoring specifically. The bean name `kafkaListenerContainerFactory` is the default name `@KafkaListener` uses when `containerFactory` is omitted.

Relevant imports:

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

`setNoPollThreshold(3.0f)` passes a `float` literal compatible with signatures accepting float or widened to double in applicable versions. `setPollTimeout(long)` takes milliseconds and `setMonitorInterval(int)` takes seconds in common container APIs; verify against your dependency's Javadoc.

### 4.1. When not using Spring Boot

When creating `ConcurrentKafkaListenerContainerFactory` manually, omit the `Configurer` and set `ConsumerFactory` and `ContainerProperties` directly.

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String> customFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setPollTimeout(5_000L);
    factory.getContainerProperties().setNoPollThreshold(3.0f);
    factory.getContainerProperties().setMonitorInterval(15);

    return factory;
}
```

If Boot auto-configured an error handler, transaction manager, message converter, observation, or listener properties, a custom factory must wire any needed components itself. Never assume a self-created factory inherits everything from the default factory.

### 4.2. Always configure the right factory

An application can define multiple listener factories:

```java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersContainerFactory"
)
public void onOrder(String payload) {
    // ...
}
```

Here, configuring `noPollThreshold` on a different factory will not affect this listener. Verify the exact factory your `@KafkaListener` uses.

You can set different policies for low-latency listeners and long-batch listeners, but each policy must align with its SLO and actual `max.poll.interval.ms`.

## 5. Defaults and threshold selection principles

Across many Spring Kafka versions, `noPollThreshold` defaults to about **3.0** and `monitorInterval` defaults to about **30 seconds**. Treat these as reference figures to verify per version rather than building production monitoring on unverified default assumptions.

Illustrative reference configurations:

| Workload | pollTimeout | noPollThreshold | Computed threshold | monitorInterval |
|---|---:|---:|---:|---:|
| Fast-processing listener | 2 s | 3.0 | 6 s | 5 s |
| Typical listener | 5 s | 3.0 | 15 s | 10 s |
| Long-processing batch listener | 5 s | 6.0 | 30 s | 10 s |
| High-sensitivity monitor test | 1 s | 2.0 | 2 s | 1 s |

These values are illustrative only, not defaults or universal recommendations for every system. A listener regularly taking more than 15 seconds per record when `noPollThreshold × pollTimeout = 15s` can emit events even while executing valid business logic.

### 5.1. Do not raise the threshold just to silence alerts

If a consumer routinely stops polling for 40 seconds because an HTTP dependency lacks a timeout, raising `noPollThreshold` to 20 to "stop the alerts" does not fix the cause. It merely delays monitor detection.

Check:

- Listener processing time p95/p99.
- Records returned per poll (`max.poll.records`).
- Retry/backoff durations.
- HTTP/database timeouts.
- JVM GC pauses.
- CPU saturation or thread contention.
- Consumer group rebalance rate.

Choose an appropriate threshold **after** measuring real poll-time distributions and Kafka liveness boundaries.

### 5.2. Do not set the threshold right next to pollTimeout

A `poll()` call can wait nearly the entire `pollTimeout` when no records exist. Hence, a multiplier too close to 1 can trigger on ordinary jitter. A factor well above 1, with margin for schedulers and networking, usually cuts false positives.

Headroom must be based on your real environment and latency SLOs; no single number fits every consumer group.

## 6. What is NonResponsiveConsumerEvent?

`NonResponsiveConsumerEvent` is an event emitted by Spring Kafka when the monitor detects signs that a consumer has **failed to poll** for longer than the threshold.

You can receive it via Spring `@EventListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaNoPollObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaNoPollObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer appears non-responsive: " +
            "source={}, timeSinceLastPollMs={}",
            event.getSource(),
            event.getTimeSinceLastPoll()
        );
    }
}
```

`getTimeSinceLastPoll()` reports the elapsed duration since the last poll as tracked by Spring Kafka, commonly used to assess severity. Verify the return unit in your version's Javadoc; in common APIs this value is in milliseconds.

The event does **not** mean:

- The Kafka broker has definitely disconnected.
- The consumer has already been evicted from the group.
- The entire listener container is no longer running.
- Offset commits have definitely failed.
- Calling `stop()` or `restart()` is immediately safe at event time.

It is a signal to combine with metrics and logs to investigate the actual root cause.

### 6.1. Event source in concurrent containers

When a listener has concurrency greater than 1, each child consumer runs its own poll loop. One child consumer can stall while others keep polling fine.

Never turn a single consumer's event into "the entire service is dead" before inspecting source/container identity, client ID, partition assignment, and the progress of sibling children.

Analyze by:

- Logical listener ID.
- Container/concurrent-child identity.
- Topic/partition assignment.
- Consumer group.
- Pod/instance.
- Event timestamp.

Granular IDs belong in logs and traces; normalize metric labels to prevent cardinality explosion.

## 7. noPollThreshold and ListenerContainerIdleEvent are two different stories

A consumer can **poll very steadily** yet receive zero records because the producer has sent nothing. That is data *idle*, not a hung consumer.

Conversely, a consumer can have a huge backlog yet **fail to poll** because the listener is stuck in an HTTP call. That is a non-responsive signal.

| State | Polling regularly? | New records? | Appropriate event |
|---|---|---|---|
| Empty topic, consumer still polls | Yes | No | `ListenerContainerIdleEvent` (if idle interval enabled) |
| Listener stuck for long | Not frequently enough | Backlog may exist | `NonResponsiveConsumerEvent` |
| Container paused and keeps polling | May still poll | Delivery paused | `ConsumerPausedEvent`/pause state |
| Consumer group rebalance | May pause briefly | Situational | Rebalance callbacks/consumer metrics |
| Container stopped | No | No | Lifecycle events such as `ContainerStoppedEvent` |

### 7.1. Idle is not an error signal

`idleEventInterval` controls when Spring Kafka emits an event because a listener container received no records for a duration. It helps detect topics missing data relative to business expectations.

`noPollThreshold`, by contrast, checks **poll-loop liveness**, not whether producers are emitting messages.

If a dashboard only tracks "no message received" without "poll progress", operations teams cannot tell an empty topic apart from a hung consumer.

### 7.2. Idle and non-responsive can appear at different times

A listener may start out legitimately idle and later get stuck inside a callback or dependency call. At that point it stops polling and the monitor emits `NonResponsiveConsumerEvent`.

Never use an idle event as proof that the consumer stayed healthy after that moment. Each event reflects only one time window and one kind of observation.

## 8. non-responsive and max.poll.interval.ms

`max.poll.interval.ms` limits how long a Kafka consumer can go between `poll()` calls before violating group protocol progress. Processing a batch for too long can cost the consumer its assignment, triggering redelivery and rebalances.

Suppose:

```text
pollTimeout               = 5 seconds
noPollThreshold           = 3.0
Spring monitor threshold  = 15 seconds
monitorInterval           = 10 seconds
max.poll.interval.ms      = 300,000 ms = 5 minutes
```

Non-responsive events can fire after a few dozen seconds—**well before** the consumer breaches `max.poll.interval.ms`. That is the monitor's benefit: providing early warning to investigate.

Yet there is no rigid coupling between the two limits:

- If Spring's monitor has too high a `noPollThreshold` or long `monitorInterval`, Kafka may evict the consumer before the monitor alerts.
- If the monitor is overly sensitive, it may emit events while the listener is still processing a valid batch.
- If the consumer thread hangs badly, the monitor scheduler may emit an event, though the event callback could also suffer under CPU starvation or shutdown.

### 8.1. max.poll.records and total time of one poll

A common pitfall is budgeting time for **one record** when the container receives **many records per poll**.

Example:

```text
max.poll.records = 200
Average processing per record: 150 ms
Theoretical total: 200 × 150 ms = 30 seconds
Before adding network, database, GC, and error handling
```

If `noPollThreshold × pollTimeout = 15s`, the monitor may emit events while the listener is still working sequentially through the batch.

The right fix is lowering `max.poll.records`, optimizing processing, adding partition-aligned concurrency, or moving long-running work onto a durable queue. Tuning the monitor threshold is only secondary, never a substitute for workload sizing.

### 8.2. Session timeout and heartbeats are not poll progress

Heartbeats may be handled by the consumer client via its own mechanism and group protocol. A consumer can still appear connected for a period even while the application fails to poll quickly enough.

Thus `session.timeout.ms` and `heartbeat.interval.ms` do not replace `noPollThreshold`. They govern separate aspects of group membership and liveness.

Never assume "heartbeats are still succeeding" means the listener is processing messages normally.

## 9. Causes that stall poll progress

### 9.1. Listener calling slow or hung dependencies

```java
@KafkaListener(topics = "orders.events")
public void onOrder(String json) {
    remoteService.callWithoutTimeout(json);
}
```

If the HTTP client lacks proper connect/read timeouts, the listener can hang on an external call. The consumer thread fails to return to `poll()` on time.

Mitigations:

- Configure HTTP connect, read, and overall deadlines.
- Use circuit breakers/bulkheads suited to the business flow.
- Propagate exceptions to the Spring Kafka error handler when work cannot complete.
- Use bounded retries and backoffs instead of infinite loops inside the listener.

### 9.2. Database locks or connection pool exhaustion

A database transaction may wait on a lock, or the listener may wait too long to acquire a connection from the pool.

Metrics to correlate:

- Hikari active/idle/pending connections.
- JDBC query latency.
- Database lock waits/deadlocks.
- Transaction duration.
- Consumer poll progress and group lag.

A non-responsive alert here may be a symptom of a slow database, not a broken Kafka broker.

### 9.3. Retries/backoff blocking the consumer thread

An error handler or application code may wait during retry backoff in a way that keeps the thread from returning to poll often enough.

In modern Spring Kafka, `DefaultErrorHandler` and `ContainerPausingBackOffHandler` offer options for retry/backoff while maintaining polling. When long waits are required, consider container-pausing backoff instead of sleeping for minutes directly inside the listener.

Note: policy-driven backoff is an intentional delay, yet it can still stretch poll intervals if the wait mechanism is not configured compatibly with the container.

### 9.4. A blocked Kafka poll or callback

The original purpose of the non-responsive monitor also covers consumers appearing stuck inside `poll()` or related steps.

Networking, metadata, interceptors, deserializers, callbacks, or Kafka client anomalies can occur. Thread dumps and Kafka client debug metrics help locate the exact wait point.

Never conclude "broker failure" from `NonResponsiveConsumerEvent` alone without inspecting stack traces and thread dumps.

### 9.5. JVM and host resources

Stop-the-world GC, CPU throttling, memory pressure, scheduler starvation, or thread deadlocks can slow down both the monitor and consumer threads.

If multiple consumers across multiple topics signal non-responsiveness simultaneously, check shared pod/node resources before treating each topic as an independent fault.

## 10. Observing with metrics and structured logs

An `@EventListener` can increment an application counter whenever an event arrives.

```java
@Component
public class KafkaPollMonitorMetrics {

    private final MeterRegistry registry;

    public KafkaPollMonitorMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        registry.counter(
                "app.kafka.consumer.non_responsive.events",
                "source_type",
                event.getSource().getClass().getSimpleName()
        ).increment();

        registry.summary(
                "app.kafka.consumer.no_poll.elapsed",
                "source_type",
                event.getSource().getClass().getSimpleName()
        ).record(event.getTimeSinceLastPoll());
    }
}
```

In this example, `MeterRegistry` is Micrometer and `app.kafka.*` names are **custom metrics**, not built-in metrics exported automatically by Spring Kafka.

`DistributionSummary` records durations as plain numbers; if you want histograms with explicit time units, use `Timer` with `TimeUnit.MILLISECONDS`. When changing representations, ensure dashboards and alerts do not confuse milliseconds with seconds.

### 10.1. A helpful log for investigation

```json
{
  "event": "kafka_non_responsive_consumer",
  "service": "orders-service",
  "listenerId": "orders-listener",
  "consumerInstance": "orders-pod-2",
  "timeSinceLastPollMs": 24750,
  "pollTimeoutMs": 5000,
  "noPollThreshold": 3.0,
  "monitorIntervalSeconds": 10
}
```

This is an illustrative log structure emitted by the application. Configuration fields like `pollTimeoutMs` and `noPollThreshold` must be sourced from actual configuration; Spring Kafka events do not necessarily include every JSON field.

Never attach message keys, offsets, event IDs, payloads, or dynamic exception messages to metric labels. Granular identifiers belong in logs/traces when investigating specific consumers.

### 10.2. Maintain separate progress gauges

A non-responsive event counter only tells how many times the monitor fired an alert. It does not state whether the consumer is still stuck or has recovered.

Dashboards should combine:

- Event count/rate over 5–15 minutes.
- Elapsed time since the last observed poll.
- Consumer group lag per partition.
- Processed records rate.
- Listener processing latency p95/p99.
- Rebalance count.
- Container running/paused state.
- JVM CPU, GC pauses, thread count.
- DB/HTTP dependency latency.

If the monitor stops emitting events after the consumer stops, that **does not mean the consumer recovered**. Inspect container lifecycle and current progress.

## 11. Alert design: detect without continuous false alarms

A single event can occur due to a GC pause or a valid large batch. Instead of paging on every event, define severity tiers:

| Level | Example signal | Response |
|---|---|---|
| Observe | Single brief event, flat lag | Record metrics/logs and watch trend |
| Warning | Multiple consecutive events, no processing progress | Inspect thread dumps and dependencies |
| Critical | Non-responsive + rapidly rising lag + near `max.poll.interval` | Handle incident, check rebalances |
| Outage | Container stopped/consumer lost, backlog not shrinking | Follow recovery runbook |

Specific thresholds must be derived from the service's SLOs, throughput, and processing-time distribution.

### 11.1. Avoid causing restart storms

Do not do this directly inside the event handler:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Do not automatically stop/start the entire listener on every event.
}
```

If the root cause is a hung database, restarting consumers immediately may just create extra connections and rebalances without fixing the DB.

If automated recovery is needed, require multiple independent signals, rate limits, cooldowns, retry caps, and differentiate planned pauses from unexpected stalls. For external side effects, ensure idempotency before forcing restarts because records may be redelivered.

### 11.2. Do not treat Spring's threshold as an absolute SLA

Even if `noPollThreshold × pollTimeout = 15s`, the monitor is not a precision-guaranteed watchdog. Actual timing depends on `monitorInterval` and whether the scheduled monitor runs on time.

Define SLAs around **business event age, processing latency, and consumer lag**, then use no-poll events to diagnose why SLOs were breached.

## 12. Event handlers must not manipulate KafkaConsumer arbitrarily

In Spring Kafka, application events may fire on a container management thread or a monitor thread. With a custom async `ApplicationEventMulticaster`, the listener can also run on a separate executor.

`KafkaConsumer` is not thread-safe, so this callback is **not** the place to call `poll()`, `seek()`, `commitSync()`, `pause()`, or `resume()` on the raw consumer.

Dangerous example:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Do not call commitSync() or seek() on the KafkaConsumer
    // obtained from the event on a monitoring thread.
}
```

When record intake must be controlled, prefer `MessageListenerContainer.pause()`, `resume()`, or appropriate container APIs under a safe operational policy. For diagnostic thread dumps, gather JVM data at the monitoring/diagnostic layer rather than mutating consumer state directly.

### 12.1. An event should not trigger heavy work

A lightweight logger or counter is appropriate. Conversely, never let an event handler block on multi-second database calls, synchronous alert delivery, or unbounded external admin API calls.

You can push a signal to an observability system or a dedicated operational-actions queue, letting a controller process it with timeouts and rate limits.

## 13. How do pause/resume relate to noPollThreshold?

Spring Kafka supports pausing/resuming listener containers to reduce intake when downstream is overloaded or a recovery path is unavailable.

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pause();
}
```

During a normal pause, Spring Kafka still coordinates `poll()` to keep consumer group liveness alive without delivering new records from paused partitions. Thus **pausing does not inherently trigger `NonResponsiveConsumerEvent`**.

If a listener is already blocked in a task before the pause takes effect, the monitor may still observe a poll stall; calling pause does not instantly abort that running task.

Cases to distinguish:

| Scenario | Poll progress | NonResponsiveConsumerEvent |
|---|---|---|
| Pause applied, consumer still polls | Polling continues | Not necessarily |
| Pause requested while listener stuck | Poll has not resumed yet | May occur |
| Consumer fully stopped | Container not running | Track via lifecycle events |
| Long retry backoff using container pausing | May keep polling per handler | Depends on runtime behavior |
| Broker has no records | Consumer still polls | Not non-responsive just because empty |

Never use `noPollThreshold` to monitor "paused" state or as a substitute for `ConsumerPausedEvent` and container pause status.

## 14. Retries, error handlers, and no-poll gaps

A failing listener may be handled by `DefaultErrorHandler`, waiting for backoff before retrying.

Example:

```java
@Bean
CommonErrorHandler commonErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(2_000L, 2L)
    );
}
```

This snippet illustrates a 2-second backoff and up to two retries after the initial attempt. Total retry time for a record also includes processing time, exception handling, and poll/seek behavior.

If a backoff policy exceeds `max.poll.interval.ms`, how backoff executes affects liveness. In supported Spring Kafka versions, `ContainerPausingBackOffHandler` can coordinate pausing the container during long backoffs, allowing the poll loop to proceed rather than blocking the consumer thread for the entire wait.

**You cannot deduce whether `NonResponsiveConsumerEvent` will fire solely from `FixedBackOff` values.** Understand which wait mechanism the handler uses and how the monitor observes actual polls.

### 14.1. Non-responsiveness does not prove the error recovered

A record may be retried, temporarily stall consumer polling, and still not have reached the DLT. No-poll alerts only flag slowed poll progress; they do not tell whether retries exhausted or recovery succeeded.

When designing a reliability dashboard, separate:

- Listener failure rate.
- Retry attempts and backoff duration.
- DLT/recovery outcomes.
- Consumer no-poll events.
- Consumer lag and offset commit progress.

## 15. Concurrency and analyzing a single slow consumer

With `@KafkaListener(concurrency = "3")` or `ConcurrentKafkaListenerContainerFactory.setConcurrency(3)`, Spring Kafka typically spawns multiple child consumer containers.

```text
orders-listener
    |
    +-- consumer-0 --> partitions 0, 3
    +-- consumer-1 --> partitions 1, 4
    +-- consumer-2 --> partitions 2, 5
```

If `consumer-1` slows down, partitions 1 and 4 may build lag while `consumer-0` and `consumer-2` keep progressing.

How to investigate:

1. Identify the source/child consumer of the `NonResponsiveConsumerEvent`.
2. Check which partitions are assigned to that child.
3. Compare lag per partition, not only aggregate lag.
4. Capture a thread dump for the slow consumer.
5. Inspect listener processing latency and active dependency calls.
6. Check whether the consumer group rebalanced or lost assignments.

Never raise concurrency automatically without checking partition counts. More concurrency than partitions does not parallelize a single partition's records; excess consumers simply remain unassigned.

### 15.1. An event on a child does not prove the parent stopped

`NonResponsiveConsumerEvent` is an observation signal. `ContainerStoppedEvent` or registry states reflect container stop lifecycles. If one consumer stops polling, the parent concurrent container may still be running and sibling children may keep operating normally.

## 16. When there is no NonResponsiveConsumerEvent yet the system is slow

This is a vital operational scenario. A consumer can poll steadily while business processing still misses SLOs, for example:

- Upstream producer throughput exceeds consumer capacity.
- Each poll returns many records, yet processing stays below the monitor threshold.
- Kafka consumer is intentionally paused for backpressure.
- A retry topic has a large backlog while the main topic isn't stalled.
- Database side effects finished, yet downstream remains slow.
- An event sits in a durable work queue after Kafka acked it.
- Consumer lag grows because partition count or concurrency is insufficient.

Thus, **zero no-poll events does not mean the service is healthy**. Combine with business event latency, consumer lag, throughput, pending work age, and dependency health.

### 16.1. Polling continues yet records go unprocessed

For instance, a listener dispatches work to an in-memory executor and returns immediately:

```java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    workerPool.submit(() -> orderService.process(event));
    // The consumer thread can continue polling steadily.
}
```

In this example, the poll monitor looks completely green while the internal queue grows unbounded or tasks fail after the listener returned. If the container commits offsets before tasks complete, data can be lost on process crash.

This is why `noPollThreshold` is not a complete reliability measure. If async processing is required, design completion-based acks or a durable inbox/work queue with backpressure and idempotency.

## 17. Calculating detection time and choosing settings

When configuring, estimate:

```text
Base detection threshold:
  T = noPollThreshold × pollTimeout

Delay until next monitor check:
  from ~0 up to roughly monitorInterval
  (excluding scheduler delay / GC / CPU starvation)

Actual event timing:
  depends on poll start time, monitor schedule, and runtime
```

Example:

```text
pollTimeout = 4,000ms
noPollThreshold = 4.0
monitorInterval = 5s

T = 4 × 4s = 16s

If the consumer stops polling at t=0:
  the monitor detects the anomaly on a check after T is exceeded.
  The event may arrive around t≈16–21s under steady scheduling.
```

This range is a model estimate, **not an SLA or hard upper bound**. If the scheduler cannot run on time due to GC or node pauses, detection can be later.

### 17.1. Constraint-based configuration guidance

A practical approach:

1. Measure p99 listener processing duration under normal load.
2. Measure maximum inter-poll duration when processing a typical batch.
3. Note `max.poll.interval.ms` and how early you want detection.
4. Pick `pollTimeout` for poll-loop/latency needs, not solely for alerting.
5. Pick `noPollThreshold` so the threshold clears normal jitter while catching stalls worth alerting on.
6. Pick `monitorInterval` short enough for events to have diagnostic value.
7. Enable logs/metrics and measure false-positive rates in staging.
8. Tune per listener factory when workloads differ.

Frame each threshold with a clear goal: "If the consumer stops polling for over X seconds, the team needs to know within at most roughly Y additional seconds."

## 18. Integration testing noPollThreshold

To test that the monitor detects an actual poll stall, use a test Kafka broker (Testcontainers or EmbeddedKafka) and a real listener container. Mocking a `NonResponsiveConsumerEvent` only tests the observer, not whether the monitor works.

### 18.1. Test configuration with short thresholds

Example:

```java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setNoPollThreshold(2.0f);
factory.getContainerProperties().setMonitorInterval(1);
```

Small values keep integration tests fast. Production requires different settings matching latency, records per poll, and liveness requirements.

### 18.2. Intentionally creating a slow listener

A test listener can use a `CountDownLatch`:

```java
@Component
public class SlowListener {

    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch release = new CountDownLatch(1);

    @KafkaListener(
        id = "slow-listener",
        topics = "slow-test-topic",
        groupId = "slow-consumer-group"
    )
    public void listen(String value) throws InterruptedException {
        entered.countDown();

        // Wait with a timeout so the test never hangs indefinitely.
        if (!release.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Test did not release slow listener"
            );
        }
    }

    public boolean awaitEntered() throws InterruptedException {
        return entered.await(10, TimeUnit.SECONDS);
    }

    public void release() {
        release.countDown();
    }
}
```

While the listener waits on the latch, the consumer thread cannot continue its poll loop. With a short enough monitor interval and threshold on a healthy broker, `NonResponsiveConsumerEvent` can be emitted.

Ensure the integration test's `finally` block calls `release()` so threads are never leaked if an assertion fails.

### 18.3. Observing events with a probe bean

```java
@Component
public class NonResponsiveEventProbe {

    private final BlockingQueue<NonResponsiveConsumerEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void capture(NonResponsiveConsumerEvent event) {
        events.offer(event);
    }

    public NonResponsiveConsumerEvent await(
            long timeout,
            TimeUnit unit) throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
```

A test can:

1. Create a dedicated Kafka topic and listener container.
2. Send a record so the listener starts processing.
3. Wait on the `entered` latch to confirm the listener is blocked.
4. Wait for the probe to capture a `NonResponsiveConsumerEvent` within a reasonable timeout.
5. Verify the event comes from the expected listener/container.
6. Verify `timeSinceLastPoll` reflects a meaningful no-poll duration.
7. Release the listener and allow the container to resume polling.
8. Verify the consumer processes remaining records and the group stays stable.

Never assert an event arrives at exact millisecond 2. Monitors run periodically and CI environments have scheduler jitter, so use generous timeouts.

### 18.4. Scenario with no records while still polling

Use the same container on an empty topic. Steady empty polls must remain distinct from a non-polling consumer. Verify the monitor does not spam false events simply because the topic is idle.

If you want to measure idle, enable idle listener events separately and confirm both event types retain distinct meanings.

### 18.5. Pause scenario

Call container `pause()` via the registry, observe actual pause state, and verify the consumer maintains polling/liveness per container mechanics.

Never rely on listener invocation counts to conclude polling is active, since pausing intentionally prevents record delivery to the listener.

### 18.6. GC or CPU contention scenario

In dedicated integration/performance tests, apply controlled load or GC pause simulation to observe how the event monitor reacts. Never destabilize the JVM intentionally in routine unit/integration tests.

When analyzing results, correlate poll gaps with JVM pause times to avoid falsely blaming the Kafka broker.

## 19. Runbook when NonResponsiveConsumerEvent arrives

A solid runbook follows: **determine scope → find where it is blocked → recover safely**.

### Phase A: determine scope

1. Identify listener ID, container/child identity, consumer group, and pod.
2. Record `timeSinceLastPoll`, `pollTimeout`, `noPollThreshold`, `monitorInterval`.
3. Check whether the container is running, paused, stopping, or rebalancing.
4. Check consumer lag, backlogged partitions, and recently processed record counts.
5. Determine whether the event is isolated or sustained/affecting multiple consumers at once.

### Phase B: investigate root cause

1. Capture a thread dump of the suspected consumer thread.
2. Check HTTP/database calls, lock waits, and thread pool saturation.
3. Check retries/backoff, especially long blocking retries.
4. Check JVM GC, CPU throttling, and memory pressure.
5. Check Kafka client metrics, metadata/network errors, and broker health.
6. Compare against `max.poll.interval.ms`, `max.poll.records`, and batch duration.

### Phase C: recover

1. Fix the dependency or code blocking the listener.
2. If pause/backpressure is needed, use container APIs and maintain appropriate polling.
3. Restart/stop only after evaluating redelivery and in-flight side effects.
4. Ensure unprocessed offsets are not prematurely acked or committed.
5. Verify idempotency when consumers may redeliver the same records.
6. Monitor lag dropping and business throughput recovering.
7. Tune monitor thresholds **after** collecting real latency data.

### 19.1. A real-world scenario

An order-processing system sees consumer lag climb from 1,000 to 50,000 records in 10 minutes. The monitor reports one child consumer has not polled for over 40 seconds while sibling children continue progressing.

A thread dump reveals that child is blocked on a database lock. Simply raising `max.poll.interval.ms` or `noPollThreshold` leaves the database lock intact and backlog keeps growing. The fix is resolving database contention/timeouts, shortening transactions, considering lowering `max.poll.records` or adjusting concurrency, and validating redelivery/idempotency.

The no-poll event here was a **directional signal**, not the root cause.

## 20. Common mistakes

**Thinking `noPollThreshold` is measured in milliseconds.** It is a multiplier on `pollTimeout`. Changing `pollTimeout` also changes the monitor threshold.

**Thinking events fire the instant the threshold is crossed.** `monitorInterval` and schedulers introduce delay; the event is not a real-time watchdog.

**Equating non-responsive with idle.** A consumer with no messages can still poll healthily. Idle events and non-responsive events measure two distinct things.

**Raising `noPollThreshold` to mask a hung listener.** It only delays detection; it never fixes HTTP timeouts, DB locks, or CPU starvation.

**Assuming the event guarantees the broker lost connectivity.** The cause can lie in the listener, error handler, JVM, or dependencies.

**Calling `KafkaConsumer.seek/commitSync` from `@EventListener`.** `KafkaConsumer` is not thread-safe, and event handlers may not run on the consumer thread.

**Restarting the container on every event.** Easily causes restart/rebalance storms and duplicate side effects.

**Treating the absence of events as health.** The monitor may not be running on schedule, or the service may still be slow due to internal queues/backlogs despite steady polling.

**Ignoring `monitorInterval`.** A short threshold with a once-a-minute monitor check can miss brief stalls you care about.

**Looking only at total group lag.** One child consumer or one partition can be stuck while other partitions run fine.

**Overlooking `max.poll.records`.** Oversized batches can prevent polling for a long time even when individual records are fast.

**Confusing pause with non-responsive.** Intentionally paused containers usually keep polling; track pause metrics separately.

**Emitting context-free alerts.** A bare event count does not tell processing time, dependencies, group lag, or current state.

**Using monitor events to infer whether offsets committed.** The event is not tied directly to acknowledgment policy; inspect committed offsets and error handlers separately.

## 21. Production rollout process

For an operating Spring Kafka service, follow these steps:

1. Identify each listener factory and its actual `pollTimeout`.
2. Measure listener processing latency, per-poll processing duration, and consumer lag.
3. Cross-check `max.poll.interval.ms`, `max.poll.records`, and retry/backoff policies.
4. Set `noPollThreshold` to the desired ratio over `pollTimeout`.
5. Set `monitorInterval` short enough for actionable detection.
6. Attach `@EventListener(NonResponsiveConsumerEvent)` for lightweight logging and metrics.
7. Build dashboards tracking listeners, child consumers, lag, poll gaps, and dependency latencies.
8. Separate idle, paused, non-responsive, and stopped into distinct states.
9. Trigger alerts on multi-signal correlation; avoid auto-restarts on every event.
10. Ensure all external side effects tolerate redelivery if a consumer loses assignments.
11. Test intentional poll stalls, idle topics, and pauses against a test broker.
12. Re-verify getters, defaults, and units whenever upgrading Spring Kafka or Spring Boot.

### 21.1. Code review question

What does a configuration of `noPollThreshold=3`, `pollTimeout=5000`, and `monitorInterval=30000` **mean**?

- The suspected no-poll threshold is roughly **15,000 ms**.
- The monitor does not check continuously; with a 30-second cycle (or misconfigured value if someone confused seconds vs milliseconds), events can arrive far later than 15 seconds.
- It does not alter `max.poll.interval.ms` and does not auto-restart the consumer.
- Any emitted event must be correlated with processing, lag, GC, and dependency metrics to identify the root cause.

If an operations team cannot explain the difference between **monitor threshold** and **detection timing**, no-poll alerts will be misinterpreted.

## 22. Version-specific references

When implementing, cross-check against your exact Spring Kafka, Spring Boot, and Kafka client versions:

- **Spring for Apache Kafka Reference — Detecting Idle and Non-Responsive Consumers:** `noPollThreshold`, `monitorInterval`, `pollTimeout`, and `NonResponsiveConsumerEvent`.
- **Spring Kafka Javadoc — `ContainerProperties`:** `setNoPollThreshold`, `setMonitorInterval`, `setPollTimeout`, and their respective defaults.
- **Spring Kafka Javadoc — `NonResponsiveConsumerEvent`:** event source, elapsed time, and consumer/container metadata.
- **Spring Kafka Reference — Application Events:** consuming events via `@EventListener`, event publishers, and threading.
- **Spring Kafka Reference — Listener Container Lifecycle:** pause, resume, concurrent containers, and shutdown.
- **Spring Kafka Reference — Error Handling:** retry/backoff, `DefaultErrorHandler`, and `ContainerPausingBackOffHandler`.
- **Spring Boot Reference — Kafka auto-configuration:** listener factory configurer, consumer properties, and container factories.
- **Apache Kafka Documentation — Consumer Configs:** `max.poll.interval.ms`, `max.poll.records`, group membership, `session.timeout.ms`.
- **Micrometer Documentation:** counters, timers, distribution summaries, cardinality, and percentile histograms.

Method names, default values, event getter time units, and scheduling mechanics can vary across dependency versions. When upgrading, verify actual APIs and defaults rather than copying fixed numbers from examples.

**Technical conclusion:** `noPollThreshold` enables Spring Kafka to detect **consumers showing signs of failing to poll for too long**, using a threshold derived from `pollTimeout` and checked periodically per `monitorInterval`. It is a **liveness signal for observation and investigation**, not proof the consumer is dead or an automatic recovery mechanism. Reliable systems pair this signal with listener latency, consumer lag, retries, rebalances, JVM resources, and idempotency to fix root causes without corrupting offset progress or business state.
