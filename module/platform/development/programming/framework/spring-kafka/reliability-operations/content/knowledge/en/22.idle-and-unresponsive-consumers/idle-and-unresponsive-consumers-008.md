# pollTimeout

In Spring Kafka, a Kafka listener does not receive records passively via broker "callbacks" whenever data arrives. Instead, the Kafka consumer runs a **`poll()`** loop: requesting/receiving data from brokers, participating in consumer group coordination, handling internal events, and delivering received records to the listener container. When no records are ready, `poll()` may have to wait.

**`pollTimeout`** is an important property on the Spring Kafka listener container that specifies **the maximum duration a single `KafkaConsumer.poll(Duration)` call can wait under normal conditions**. It affects poll-loop cadence, how the container observes idle state, how frequently lifecycle conditions are checked, and how non-responsive consumers are diagnosed.

In the **Idle and Non-Responsive** chapter, `pollTimeout` must be understood alongside `idleEventInterval`, `idlePartitionEventInterval`, `NonResponsiveConsumerEvent`, `noPollThreshold`, and `monitorInterval`. Most importantly: **`pollTimeout` is not a per-record processing timeout, not a transaction deadline, and not `max.poll.interval.ms`**.

## 1. The Kafka consumer poll loop

Conceptually, a Spring Kafka listener container performs:

~~~text
Spring Kafka listener container
          |
          v
       poll(timeout)
          |
          +---- Records ready -> returns ConsumerRecords
          |
          +---- No records -> waits up to timeout
          |
          v
   Container delivers records to listener
          |
          v
   Error handling / acknowledgment / transaction
          |
          v
       next poll(timeout)
~~~

When records are returned, the container dispatches them according to record listener or batch listener mode, ack mode, error handler, and transaction configuration. When no records exist, `poll()` usually returns an empty set once the timeout elapses; the container can then continue the loop to run lifecycle checks.

Plain Kafka consumer API example:

~~~java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(3_000));
~~~

The `Duration` argument is the **maximum wait for a single poll call**, not a forced interval saying "only receive data every three seconds". If fetched data is already available, `poll()` can return early; if the consumer needs to join a group or run callbacks, actual timing also depends on the Kafka client and scheduler.

Spring Kafka uses this consumer API internally inside the listener container. In applications using `@KafkaListener`, you normally **never call `consumer.poll()` manually** inside the listener; the container owns polling.

## 2. Defining Spring Kafka's pollTimeout

Spring Kafka provides `ContainerProperties.setPollTimeout(long)` to configure the wait timeout per `poll()` cycle.

Example:

~~~java
factory.getContainerProperties().setPollTimeout(3_000L);
~~~

The value is expressed in **milliseconds**: `3_000L` equals three seconds. Across many Spring Kafka versions, `pollTimeout` defaults to **5,000 ms**; always verify the API and defaults of your deployed version.

Primary effects:

- **Short timeout**: the consumer returns from empty polls more often, giving the container more frequent opportunities to check idle/lifecycle state, though it may increase overhead.
- **Long timeout**: when a topic has no data, the consumer may wait longer inside a single poll call, reducing empty polls; time granularity of some post-poll checks may decrease.
- **When records are available**: `poll()` can return before the timeout; setting `pollTimeout=5s` does not inherently add five seconds of latency to each message.
- **When a listener processes records slowly**: processing time falls outside `pollTimeout`'s wait boundary.

Never treat `pollTimeout` as a direct lever to boost throughput. In most applications, throughput bottlenecks sit in partition count, business logic, batch size, serializers, databases, or HTTP dependencies.

## 3. Configuring pollTimeout on a listener container factory

A basic complete Spring Kafka configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // Consumer poll() may wait up to 2 seconds when no data is available.
        factory.getContainerProperties().setPollTimeout(2_000L);

        return factory;
    }
}
~~~

Listener using the factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-processor",
            groupId = "orders-service",
            topics = "orders.events",
            containerFactory = "orderListenerFactory")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

`OrderEvent` and `OrderService` are illustrative domain types. Running a real application also requires configuring Kafka bootstrap servers, key/value deserializers, topics, and required dependencies.

Key points:

1. `pollTimeout` belongs to **container properties**, not Kafka broker properties.
2. `factory.setConcurrency(3)` controls child consumer containers; `pollTimeout` applies to the poll loop of those container-created consumers.
3. If an application has multiple container factories, configure the exact factory used by `@KafkaListener`.
4. If creating listener containers manually outside `@KafkaListener`, set the property on those containers' own `ContainerProperties`.
5. Do not mistakenly edit `spring.kafka.consumer.properties.max.poll.interval.ms` thinking you changed `pollTimeout`; those are two distinct limits.

### 3.1. Spring Boot property

Spring Boot lines supporting `spring.kafka.listener.poll-timeout` can map the duration onto the default container, for example:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
~~~

In applications that define custom `ConcurrentKafkaListenerContainerFactory` beans, verify whether Boot configuration is applied to that factory. If the factory is not configured via `ConcurrentKafkaListenerContainerFactoryConfigurer` or an equivalent mechanism, a YAML property may not automatically populate custom factory properties.

Set it directly on the container factory when explicit control is needed; check property bindings for your Spring Boot version before assuming runtime uses the expected value.

## 4. pollTimeout does not mean "wait the full time before receiving records"

Example `pollTimeout = 5_000 ms`:

~~~text
T0     Consumer calls poll(5s)
T0+20ms Broker/consumer already has available record
T0+25ms poll returns and container starts processing
~~~

In this scenario, the record is not held back for five seconds. `pollTimeout` is a cap on how long a poll waits, not a mandatory batch timer.

Conversely, if the topic is empty:

~~~text
T0     poll(5s)
T0+5s  poll may return empty
T0+5s  container checks state, then calls next poll
~~~

Actual timing is influenced by the Kafka client, consumer group state, scheduler, and in-flight requests. Thus a system with no data sees repeated empty polls, though you should not assume polls begin at exact 0, 5, 10, 15 second marks.

## 5. Impact on idleEventInterval

Spring Kafka provides `idleEventInterval` to emit `ListenerContainerIdleEvent` when a container receives no records for a configured duration. When evaluating event emission timing, consider `pollTimeout` because the container typically checks idle conditions during poll loop execution.

Example:

~~~java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setIdleEventInterval(10_000L);
~~~

Illustrative flow when there are no records:

~~~text
poll ~1s -> empty -> poll ~1s -> empty -> ...
                           |
                    after idle long enough
                           |
                           v
               ListenerContainerIdleEvent
~~~

With a very long poll timeout, the idle check may only run when the container gets a chance to execute that check branch. That can cause the event to appear **later than the configured idle threshold**.

### 5.1. Choosing pollTimeout relative to idleEventInterval

Suppose an application wants an idle signal after roughly 15 seconds. An easier-to-observe configuration might be:

~~~java
factory.getContainerProperties().setPollTimeout(2_000L);
factory.getContainerProperties().setIdleEventInterval(15_000L);
~~~

Do not set `pollTimeout` much larger than `idleEventInterval` and expect the event to always fire right at 15 seconds. Events are not real-time timers; latency also depends on scheduling and the poll loop.

However, there is also no need to shrink `pollTimeout` down to a few milliseconds just for ultra-tight event timestamps. Doing so creates excessive empty poll cycles and monitoring overhead.

### 5.2. Idle does not mean non-responsive consumer

An **idle** container can still run `poll()` normally and receive empty record sets. This is routine for low-traffic topics.

A **non-responsive** container may be stuck inside a poll call or fail to return to the poll loop as expected. The two situations require different metrics and actions:

| Situation | Does polling continue? | Are there records? | How to interpret |
|---|---|---|---|
| Empty topic, healthy consumer | Yes | No | Normal idle. |
| One partition has no data | Yes | Other partitions may have data | Partition idle, not necessarily container idle. |
| Listener takes too long between polls | Irregular | Backlog may exist | Risk of violating `max.poll.interval.ms`. |
| Consumer stuck inside poll/request | Fails to return on expected schedule | Indeterminate | Investigate non-responsiveness. |
| Container stopped | No | No | Lifecycle stopped; not running idle. |

## 6. pollTimeout and NonResponsiveConsumerEvent

Spring Kafka provides `NonResponsiveConsumerEvent` to help detect consumers failing to perform/complete polling as expected under the container's monitor mechanism. Related settings include:

- **`pollTimeout`**: wait duration of a single poll call.
- **`noPollThreshold`**: multiplier used alongside poll timeout to define the no-poll check threshold.
- **`monitorInterval`**: monitor check cadence for consumer state; its unit follows your version's API.
- **`NonResponsiveConsumerEvent`**: application event signaling that a consumer appears non-responsive per the monitor threshold.

Example:

~~~java
factory.getContainerProperties().setPollTimeout(2_000L);
factory.getContainerProperties().setNoPollThreshold(3.0f);
factory.getContainerProperties().setMonitorInterval(5);
~~~

Conceptually:

~~~text
pollTimeout         = 2 seconds
noPollThreshold     = 3.0
product threshold   = roughly 6 seconds
monitorInterval     = check every 5 seconds
~~~

A ~6-second threshold does **not** guarantee an event fires at second 6 sharp. The monitor runs on its own schedule; the event can fire on a check after crossing the threshold. Moreover, a container may fail to return to polling because record processing takes too long, not solely because Kafka networking hung.

`monitorInterval` in `ContainerProperties` is commonly configured in seconds, whereas `pollTimeout` uses milliseconds. This unit mismatch is a very common mistake when operators translate values between Java APIs and YAML.

### 6.1. Why balance all three parameters?

A noisy configuration:

~~~text
pollTimeout = 10 seconds
noPollThreshold = 1.1
monitorInterval = 1 second
~~~

When a normal poll takes nearly 10 seconds, the product threshold is only ~11 seconds. Too small a margin triggers alerts on ordinary scheduling jitter or valid callback paths.

Another configuration:

~~~text
pollTimeout = 1 second
noPollThreshold = 20
monitorInterval = 60 seconds
~~~

The threshold is ~20 seconds yet the monitor only checks every 60 seconds. Incidents may go unreported promptly even though the internal threshold is much lower.

Pick `monitorInterval` small enough to detect faults per operational SLOs, without making it so short it creates unnecessary overhead. The `noPollThreshold × pollTimeout` threshold needs enough headroom to distinguish normal polls from genuinely slow or stuck consumers under real load.

### 6.2. Receiving NonResponsiveConsumerEvent

Example:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaNonResponsiveObserver {

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn("Kafka consumer non-responsive: source={}, container={}",
                event.getSource(),
                event.getContainer());
    }
}
~~~

`log` is the class logger. Upon receiving the event, do not immediately reset offsets or conclude the broker definitely failed. Inspect thread dumps, listener processing time, Kafka client logs, rebalances, pause state, and other timeouts.

## 7. pollTimeout and idlePartitionEventInterval

`idlePartitionEventInterval` tracks **individual topic-partitions** that receive no records within a configured interval. `pollTimeout` remains the wait duration of the underlying poll loop.

Example:

~~~java
factory.getContainerProperties().setPollTimeout(1_500L);
factory.getContainerProperties().setIdlePartitionEventInterval(30_000L);
~~~

Diagram:

~~~text
Topic orders.events
  p0: continuous records --+
  p1: silent 30 seconds ---+----> listener container keeps polling
  p2: continuous records --+
                                 |
                                 v
                     PartitionIdleEvent for p1
~~~

While other partitions have records, `poll()` may return early. When the entire topic is empty, polls may wait nearly the full timeout. Thus partition idle emission can be influenced by how the container cycles through polls, though it is not simply "emit one idle event every `pollTimeout`".

If a partition is **paused**, the container may receive no records from that partition even while producers keep writing. Before concluding upstream is silent, check pause state and consumer lag.

## 8. pollTimeout when the container is paused

Spring Kafka lets you pause the whole container or individual partitions to throttle load. Pausing does not necessarily halt polling altogether; the consumer usually must maintain certain activities for the consumer group.

Some Spring Kafka versions support **`pollTimeoutWhilePaused`** to use a separate poll wait duration while the container is paused. Thus:

- `pollTimeout` governs the normal poll loop.
- `pollTimeoutWhilePaused`, if supported and applied while paused, tunes polling during pause.
- `pause()` does not mean `stop()`.
- Changing `pollTimeout` alone may not alter all poll cadence while paused.

Example configuration on container properties when supported by your API version:

~~~java
factory.getContainerProperties().setPollTimeout(5_000L);
factory.getContainerProperties().setPollTimeoutWhilePaused(200L);
~~~

Wait times while paused can be shorter so the container reacts quickly to resume commands and lifecycle checks. Still, that does not cause the consumer to receive records from paused partitions.

When handling backpressure, review `pauseImmediate`, `idleBetweenPolls`, container state, and retry behavior in your Spring Kafka version. These parameters serve different objectives; never change them all at once without measuring impact.

## 9. pollTimeout and idleBetweenPolls

Spring Kafka allows configuring a sleep **between polls** via `idleBetweenPolls` in supported versions. This property differs from `pollTimeout`:

~~~text
poll(timeout):
    may wait for data inside the poll call itself

idleBetweenPolls:
    intentional sleep between poll cycles, per container policy
~~~

Example:

~~~java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setIdleBetweenPolls(200L);
~~~

On an empty topic, time between iterations includes **actual poll duration + inter-poll sleep + processing overhead**. Never assume `1_000ms` is the exact total period between poll starts.

Inter-poll sleeps can help throttle data intake, yet must account for `max.poll.interval.ms`. If a listener processes a slow batch and then deliberately sleeps long between polls, the consumer may call the next poll too late and be deemed non-progressing by the Kafka group coordinator.

## 10. pollTimeout is not max.poll.interval.ms

These are the two most commonly confused concepts:

| Property | Belongs to | Purpose |
|---|---|---|
| `pollTimeout` | Spring Kafka listener container | Maximum timeout for **a single** `poll(Duration)` call. |
| `max.poll.interval.ms` | Kafka consumer client | Limit on time between `poll()` calls, used to detect applications failing to poll often enough. |
| `session.timeout.ms` | Kafka consumer group | Governs broker liveness/session checks for members via heartbeats. |
| `heartbeat.interval.ms` | Kafka consumer (protocol-dependent) | Heartbeat cadence per consumer group protocol. |
| `request.timeout.ms` | Kafka client | Client wait limit for network request responses. |
| `fetch.max.wait.ms` | Kafka consumer/broker fetch | Broker-side wait cap before returning a fetch when minimum bytes aren't met, per fetch config. |

Example:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
    consumer:
      properties:
        max.poll.interval.ms: 300000
~~~

This does **not** mean each record has at most 2 seconds to be processed. It means the container normally polls with a two-second timeout, while the consumer group limit between polls is 300 seconds in this example.

A batch listener taking 350 seconds can violate `max.poll.interval.ms` even if `pollTimeout` is only 500 milliseconds. The issue is **the listener failing to return to poll soon enough**, not the wait inside an empty poll.

### 10.1. Example of violating max.poll.interval.ms

~~~text
T0: consumer.poll(2s) returns 500 records
T0+1s: listener begins processing batch
T0+320s: listener finally finishes
T0+320s: consumer prepares for next poll
~~~

If `max.poll.interval.ms = 300_000`, the consumer can lose group membership or suffer generation/assignment consequences per client version and group protocol, even though `pollTimeout` never exceeded two seconds.

Proper fixes include optimizing batches, lowering `max.poll.records`, bounding dependency call times, or designing appropriate async processing. Lowering `pollTimeout` alone never fixes a listener taking too long on batches.

## 11. pollTimeout and graceful shutdown

When an application receives a stop signal, the Spring Kafka container coordinates with consumer threads to exit the poll loop and close `KafkaConsumer`.

~~~text
SIGTERM / ApplicationContext shutdown
                 |
                 v
container.stop() / Spring lifecycle stop
                 |
                 v
wake up / coordinate poll loop, run shutdown
                 |
                 v
consumer closes and ContainerStoppedEvent fires
~~~

A long `pollTimeout` can influence how often a container naturally exits poll when idle. However, `KafkaConsumer` supports **`wakeup()`** to break out of a blocking poll on many shutdown paths; therefore **never assume stop delay always equals the full `pollTimeout`**.

Actual stop time depends on:

- Whether the listener is mid-record/batch or waiting in `poll()`.
- HTTP/database dependency timeouts.
- Offset commits and Kafka transaction commits/aborts.
- Error handlers, retries, and backoffs.
- Container `shutdownTimeout`.
- Spring lifecycle shutdown phase timeout.
- Kubernetes termination grace period.

If a listener is stuck waiting 60 seconds for an HTTP response lacking a proper timeout, shrinking `pollTimeout` from 5 seconds to 500ms will not speed up shutdown: the consumer is inside **business processing**, not waiting in poll.

### 11.1. Coordinating with Spring Boot and Kubernetes

Example:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s

server:
  shutdown: graceful
~~~

When running on Kubernetes, `terminationGracePeriodSeconds` must cover the full shutdown budget with headroom for cleanup and closing connections.

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

If the container receives `SIGKILL` before stopping cleanly, application lifecycle events are not guaranteed to fire and uncommitted offsets may be reprocessed. Idempotency is therefore essential—not just tuning poll timeouts.

## 12. pollTimeout, throughput, and CPU/network overhead

Picking too short a `pollTimeout` causes frequent empty polls when topics have very little traffic. Overhead includes internal loop iterations, status checks, and scheduling, even though Kafka clients/brokers apply their own fetch optimizations.

A longer timeout cuts down empty polls, yet makes application idle/lifecycle checks coarser when no data arrives.

| Setting | Potential benefit | Risks to consider |
|---|---|---|
| 100–500 ms | Faster response for certain post-poll checks | More empty poll loops on low-data topics. |
| 1–5 seconds | Simple balance for many workloads | Idle event timing depends on poll cadence. |
| Tens of seconds | Fewer empty polls on very sparse topics | Monitor/idle detection becomes less responsive; review other timeouts. |
| Custom while paused | Separates pause and running behavior | Must verify `pollTimeoutWhilePaused` and container state. |

Ranges in the table are **examples for trade-off analysis**, not benchmarks or universal recommendations. Measure on real workloads instead of guessing.

Notably, when a topic has plenty of records, `poll()` can return quickly under both short and long timeouts. Throughput is then dominated by `max.poll.records`, message processing, and consumer/partition counts.

## 13. pollTimeout and max.poll.records

`max.poll.records` is a Kafka consumer property capping records returned per `poll()`. It does **not** set poll wait time, but governs how much work the container processes before the next poll.

Example:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
    consumer:
      properties:
        max.poll.records: 200
        max.poll.interval.ms: 300000
~~~

If each record averages 500ms and the container processes 200 records sequentially, total business time is roughly 100 seconds before overhead; that matters far more to `max.poll.interval.ms` than `pollTimeout=2s` does.

When investigating consumers not polling often enough, examine:

1. Records per poll and assigned partition count.
2. Listener type (record vs batch).
3. Average and high-percentile processing latency.
4. Whether retries/backoff hold the consumer thread.
5. Timeouts on API/database calls inside the listener.
6. `max.poll.interval.ms` and pause/resume paths.

Never raise `max.poll.interval.ms` indefinitely to hide a stuck listener. Fix the root cause and bound processing time.

## 14. Event monitoring with @EventListener

Observe idle and non-responsive events to separate "no data" from "consumer stuck".

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPollingObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerPollingObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info("Kafka listener idle: source={}", event.getSource());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn("Kafka consumer non-responsive: source={}",
                event.getSource());
    }
}
~~~

These events are **in-JVM Spring application events**; they have no separate Kafka topic or offset. Events may be published on consumer/container threads and processed synchronously under the default multicaster. Keep handlers brief, avoid slow HTTP/DB calls, and never manipulate `KafkaConsumer` directly from an improper thread.

Seeing `ListenerContainerIdleEvent` alone does not prove cluster health; seeing `NonResponsiveConsumerEvent` alone does not prove the Kafka broker is dead. Combine logs and metrics to classify accurately.

## 15. Observing with metrics and logs

A dashboard for the Idle and Non-Responsive chapter should include:

| Signal | Question to answer |
|---|---|
| Consumer poll rate / poll latency | Is the consumer polling regularly and how long do polls take? |
| Time since last poll | How long has the consumer failed to return to the poll loop? |
| `NonResponsiveConsumerEvent` count | How many monitor signals flagged a stuck consumer? |
| `ListenerContainerIdleEvent` count | Over what periods did the container receive no records? |
| Partition idle events | Which partition gets no records despite container-wide traffic? |
| Consumer lag per partition | Is there an uncommitted backlog? |
| Listener processing latency | Is business processing slowing down polls? |
| Rebalance count/duration | Is the consumer constantly losing group membership? |
| Container running / paused state | Is the consumer running, paused, or stopped? |
| Broker request latency / failures | Are networking or brokers having issues? |

Illustrative structured log:

~~~text
service=orders-worker
listener_id=orders-processor
group_id=orders-service
poll_timeout_ms=2000
no_poll_threshold=3.0
monitor_interval_seconds=5
event_type=NonResponsiveConsumerEvent
instance_id=orders-worker-2
~~~

These fields are metadata added by the application/monitoring layer; not all are default event properties. Avoid putting event IDs, offsets, or record keys into metric labels because cardinality explodes quickly.

### 15.1. Investigating a non-responsive alert

When `NonResponsiveConsumerEvent` arrives:

1. Check whether the **container is running, paused, or stopping**.
2. Inspect time-since-last-poll metrics and listener processing durations.
3. Capture a thread dump if the consumer thread appears blocked.
4. Check Kafka client network logs, broker health, and authentication.
5. Cross-check the effective `pollTimeout × noPollThreshold` and `monitorInterval`.
6. Check `max.poll.interval.ms` and signs of group rebalances.
7. Check retries/backoff, blocking API/database calls, and lock contention.
8. Only change timeouts after determining whether the consumer is stuck in **poll**, **listener processing**, or **shutdown**.

If the consumer keeps polling empty normally on an empty topic, that is **idle**, not non-responsive. If the consumer is blocked inside an HTTP call, lowering `pollTimeout` will not fix anything.

## 16. Common pollTimeout misconfigurations

### 16.1. Setting it too low just to cut message latency

`pollTimeout=100ms` does not guarantee sub-100ms record latency, because end-to-end latency includes producer batching, broker fetches, partition assignment, consumer scheduling, business processing, and commits.

For strict latency goals, measure end-to-end timestamps/lag and fix the true bottleneck.

### 16.2. Setting it too high while ignoring idle monitoring

A poll timeout of tens of seconds makes idle-event check cycles coarse. If you need to detect "no records from source for 10 seconds", choose a poll timeout suited to that observation granularity.

### 16.3. Setting noPollThreshold below normal poll behavior

A monitor threshold too close to legitimate poll times causes unnecessary non-responsive alerts. Factor in real latencies and scheduling jitter.

### 16.4. Using too long a monitorInterval

The monitor only runs periodically. If `monitorInterval` is far larger than the non-responsive threshold, incidents are detected later than desired.

### 16.5. Confusing pollTimeout with max.poll.interval.ms

A listener spending 10 minutes on a batch cannot be "saved" by shrinking `pollTimeout` to 100ms. You must reduce time held between polls or redesign processing.

### 16.6. Believing pollTimeout equals shutdownTimeout

`pollTimeout` controls how poll waits for data; `shutdownTimeout` sets the container's stop-wait budget. `KafkaConsumer` wakeup and in-flight tasks make their relationship non-trivial.

### 16.7. Editing YAML only while the listener uses another custom factory

When an application has multiple `@KafkaListener(containerFactory="...")` beans, Boot listener properties may not apply to custom factories. Verify effective container property values at runtime.

## 17. Testing pollTimeout with a real Kafka broker

Use Embedded Kafka or Kafka Testcontainers to test listener container behavior and application events. Mocking a Java listener method call is insufficient to verify `KafkaConsumer` poll behavior.

A test suite can cover:

1. **Empty topic:** configure a short `pollTimeout`; verify the consumer container stays running and emits idle events when thresholds are reached.
2. **Records arrive mid-poll:** send a record after startup; verify the listener receives it without waiting the full `pollTimeout`.
3. **Idle event timing:** set `idleEventInterval` several times larger than `pollTimeout`; wait for the event via a bounded-timeout latch/queue.
4. **Partition idle:** leave one partition empty while another has data; verify partition idle events if enabled.
5. **Non-responsive consumer:** use a failpoint/proxy/test harness to stall polling, observe monitor events, and verify recovery.
6. **Slow listener:** inject controlled business delay; demonstrate a short `pollTimeout` does not alter processing limits.
7. **Pause/resume:** verify `pollTimeoutWhilePaused` behavior if configured and supported.
8. **Shutdown:** call `container.stop()` on an empty topic or active listener; measure stop callbacks and shutdown time.
9. **Concurrency:** run multiple child containers; confirm metrics/events attribute to the right consumer/container.
10. **Restart/rebalance:** test timeouts and lifecycle when a consumer loses and regains partitions.

### 17.1. Example test capturing ListenerContainerIdleEvent

Probe inside the Spring context:

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdleEventProbe {

    private final BlockingQueue<ListenerContainerIdleEvent> queue =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        queue.offer(event);
    }

    public ListenerContainerIdleEvent await(Duration timeout)
            throws InterruptedException {
        return queue.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Test with a container factory that enabled `idleEventInterval`:

~~~java
@Test
void emptyTopicEventuallyProducesIdleEvent() throws Exception {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-processor");

    assertThat(container).isNotNull();

    if (!container.isRunning()) {
        container.start();
    }

    ListenerContainerIdleEvent event =
            idleProbe.await(Duration.ofSeconds(30));

    assertThat(event).isNotNull();
}
~~~

`registry` is the injected `KafkaListenerEndpointRegistry` bean and `idleProbe` is the probe above. The empty topic and consumer group must be isolated so records from other tests do not break idle conditions.

If the test context contains multiple listeners, filter events by listener/container ID so you don't pick up another listener's event. Never use fixed `Thread.sleep()` instead of bounded condition waits.

### 17.2. Verifying pollTimeout does not impose record latency

Test scenario:

~~~text
1. Start container with pollTimeout=5s
2. Wait until consumer has partition assignments
3. Send new record at T0
4. Use a latch to capture when listener processes record
5. Compute T_listener - T0
~~~

Observed latency varies by test runner, broker, and scheduler. Tests should never assert an unrealistic SLA like "guaranteed under 1ms". The objective is proving the consumer can receive records **well before the full `pollTimeout` elapses** under normal conditions.

### 17.3. Testing non-responsive requires dedicated fault injection

A unit test calling `onNonResponsive()` directly does not prove the container monitor detects hung consumers. To test real events, induce a state where the consumer stops polling/returning within the threshold, then await the event.

You can use a test-specific blocking listener or proxy/network fault, while clearly distinguishing **listener blocking** from **consumer poll blocking**. Measure actual timing and state to avoid false-positive tests.

Never leave long-running or uncleaned fault injections on shared CI runners. Always enforce timeouts and release latches, consumers, topics, and processes when tests finish.

## 18. Choosing pollTimeout by goal

| Operational goal | Configuration guidance |
|---|---|
| Steady-traffic topic needing stable throughput | Keep a moderate value; optimize listener/batch/concurrency before lowering `pollTimeout`. |
| Very low-traffic topic | Avoid overly short timeouts that cause excessive empty polls. |
| Detect container idle within seconds | Pick `pollTimeout` aligned with `idleEventInterval` and scheduler capabilities. |
| Fast non-responsive alerts | Tune `pollTimeout`, `noPollThreshold`, and `monitorInterval` as one triad. |
| Container may pause for backpressure | Verify `pollTimeoutWhilePaused` and pause/resume mechanics. |
| Slow record processing in listener | Focus on processing time, `max.poll.interval.ms`, `max.poll.records`, and dependency timeouts. |
| Slow shutdown | Measure whether waiting in poll or processing; check wakeup and `shutdownTimeout`. |
| Multiple listeners/factories in app | Verify the property applies to the actual factory/container in use. |

No single `pollTimeout` fits every system. Start with a moderate setting, measure real poll durations, idle-event delivery, error rates, and shutdown speed, then adjust deliberately.

## 19. Production checklist

Before changing `pollTimeout` in a running Spring Kafka system, answer:

- How many consumer threads does the listener run, and how many partitions does each hold?
- Is the consumer mostly waiting on data or bottlenecked by processing?
- Which factory sets `pollTimeout`, and is a custom factory overriding it?
- What defaults and units apply in your Spring Kafka / Boot version?
- Are `idleEventInterval` and `idlePartitionEventInterval` enabled?
- What non-responsive threshold does `noPollThreshold × pollTimeout` produce?
- Is `monitorInterval` frequent enough relative to that threshold?
- Does the consumer use `pollTimeoutWhilePaused` or `idleBetweenPolls`?
- Is `max.poll.interval.ms` large enough for batch/record processing times?
- Are poll latency, processing latency, lag, and rebalances instrumented?
- Has shutdown been tested on both empty topics and busy listeners?
- Are idle alerts distinguished from partition pauses, upstream outages, and non-responsiveness?
- Do tests use a real broker and await observable conditions instead of rigid timings?

**`pollTimeout`** is the control knob for **how long a single Kafka consumer poll cycle waits**, not a business processing limit. In the **Idle and Non-Responsive** chapter, its value lies in coordinating with idle-event intervals, the non-responsive consumer monitor, and listener container lifecycle. Understanding `pollTimeout`'s exact boundaries helps applications observe accurately, avoid false alarms, and avoid tweaking the wrong timeout when the real culprit is listener processing, consumer groups, or dependencies outside Kafka.
