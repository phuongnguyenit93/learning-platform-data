# Testing Non-Responsive Consumers in Spring Kafka Reliability Operations

When a Spring Kafka application consumes messages, the consumer must repeatedly return to the `poll()` loop to fetch new records and maintain coordination with the consumer group. Under failure conditions, the interval between `poll()` calls can stretch abnormally: a listener takes too long to process, a thread blocks, a remote API stops responding, the system is overloaded, or a Kafka client/network issue stalls polling progress.

Checking only "is the application running" or "is the Kafka broker up" can miss a consumer that **is no longer making progress**. Spring Kafka provides `NonResponsiveConsumerEvent` to help detect when no polling activity has occurred for longer than a configured threshold.

The **Testing Non-Responsive Consumers** practice belongs to the **Reliability Testing** chapter of **Spring Kafka Reliability Operations**. The goal is to build a reproducible test proving the consumer monitor detects stalled polling, distinguish it from an idle consumer, and understand the limits of the detection mechanism.

> **Key point:** `NonResponsiveConsumerEvent` only indicates that the time without polling exceeded the monitor threshold. It **does not automatically diagnose the root cause**—whether the Kafka broker failed, the network hung, or the listener took too long. Identifying the cause requires thread dumps, metrics, logs, and layered fault tests.

Examples primarily target Java 17, Spring Boot 3.x, and the Spring Kafka 3.x line. When using Spring Kafka 4.x or another version, verify actual packages, APIs, and configurations in your project's dependencies. Test time thresholds are intentionally small, not recommended production values.

## 1. What is a non-responsive consumer?

A healthy Kafka consumer continuously loops:

```text
Consumer container thread
        |
        v
    consumer.poll(...)
        |
        +-- Has records --> invoke message listener
        |                      |
        |                      v
        |                finish processing
        |                      |
        +<---------------------+
        |
        v
    next consumer.poll(...)
```

When the listener blocks for seconds, minutes, or longer, the thread cannot call the next `poll()`. The Spring Kafka monitor tracks the elapsed time related to polling activity and emits an event if it exceeds the threshold.

For example:

```text
Time           00:00     00:01     00:02     00:03     00:04
               |---------|---------|---------|---------|
poll()         ^
record handler [----------------------------- blocked ...
monitor                  ^             ^
                      check          check
                                      |
                                      v
                        NonResponsiveConsumerEvent
```

This event is an **in-application** monitoring signal, distinct from Kafka evicting the consumer from the group for exceeding `max.poll.interval.ms`. The two mechanisms operate at different layers and can fire at different times.

### Common root causes

- Listener makes HTTP/gRPC calls with no timeout or an overly long timeout.
- Listener waits on database locks, connection pools, or long-running transactions.
- Deadlocks, lock contention, or a `CountDownLatch.await()` that is never released.
- CPU starvation, major GC pauses, or executor saturation.
- Kafka client encountering an issue inside `poll()` or network/broker stalls.
- A single record taking too long to process, keeping the consumer from returning to `poll()`.
- Batch size configured too large relative to the allowed interval between polls.

The event reports "did not poll at the expected cadence," not "the consumer is definitely dead."

## 2. Distinguishing non-responsive, idle, and lag

These three states are easily confused:

| State | Symptom | Meaning |
| --- | --- | --- |
| **Idle consumer** | `poll()` keeps running, but no new records arrive. | Consumer may be completely healthy; topic simply has no data. |
| **Non-responsive consumer** | No polling activity observed for longer than the threshold. | Thread may be blocked, processing too slowly, or polling is stuck. |
| **High consumer lag** | Consumer group has many unprocessed records behind the log end offset. | Consumption throughput trails producer rate; consumer may still be polling. |

In Spring Kafka, `ListenerContainerIdleEvent` and `NonResponsiveConsumerEvent` have **different meanings**.

```text
No messages, consumer still polling:
  poll(empty) -> poll(empty) -> poll(empty)
  => May be IDLE, not necessarily NON-RESPONSIVE.

Listener receives a message then blocks:
  poll(records) -> listener blocked -> never returns to poll
  => May emit NonResponsiveConsumerEvent.

Producer sends fast, consumer polls steadily:
  poll -> process -> poll -> process
  lag grows due to low throughput
  => High lag, but not necessarily NonResponsiveConsumerEvent.
```

Therefore, never use `NonResponsiveConsumerEvent` as the sole indicator of consumer health. It is one signal in a progress-monitoring system.

## 3. How `NonResponsiveConsumerEvent` works

The Spring Kafka listener container runs a periodic monitor. When configured appropriately, the monitor checks how long it has been since the last poll; once that duration exceeds the threshold, the container can emit `NonResponsiveConsumerEvent`.

Key properties on `ContainerProperties`:

| Property | Purpose |
| --- | --- |
| `pollTimeout` | Timeout for a single `KafkaConsumer.poll(Duration)` call in the container, in milliseconds. |
| `noPollThreshold` | Multiplier applied to `pollTimeout` to define the no-poll threshold before alerting. |
| `monitorInterval` | Check interval of the monitor, typically configured in seconds on `ContainerProperties`. |

Conceptual threshold:

\[
T_{\mathrm{nonresponsive}} \approx
\mathrm{noPollThreshold}\times\mathrm{pollTimeout}
\]

Example:

```text
pollTimeout      = 1,000 ms
noPollThreshold  = 3.0
monitorInterval  = 1 second

Base threshold   = 3,000 ms
Monitor checks every 1 second
=> Event may appear after crossing the threshold,
   not necessarily at the exact 3,000 ms mark.
```

Exact properties, defaults, and APIs can depend on the Spring Kafka version. In many Spring Kafka versions, `noPollThreshold` defaults to `3.0` and `monitorInterval` defaults to around 30 seconds. Do not rely on those defaults for a test that only waits a few seconds; tests must **configure them explicitly**.

`noPollThreshold` should exceed `1.0` to reduce false alerts caused by skew between the poll thread and monitor checks.

### When the monitor checks, when does the event fire?

Suppose a 1.5-second threshold with a 1-second monitor interval:

```text
t = 0.0s: last poll
t = 1.0s: monitor check, has not exceeded 1.5s
t = 2.0s: monitor check, exceeded threshold
           -> NonResponsiveConsumerEvent
```

Never write a test asserting the event **must appear at exactly 1.5 seconds**. Actual timing is affected by thread scheduling, Spring context startup, and scheduler jitter. Reliable tests wait on a condition with a generous timeout.

## 4. Relationship to Kafka consumer parameters

`NonResponsiveConsumerEvent` is a Spring Kafka feature; the Kafka client has its own timeouts.

| Parameter / mechanism | Controls | Common confusion |
| --- | --- | --- |
| Spring container `pollTimeout` | Wait timeout per container poll call. | Not the total time a listener is allowed to process a record. |
| `noPollThreshold` | Spring Kafka monitor threshold for suspicious no-poll gaps. | Not the group membership timeout. |
| `monitorInterval` | How often the monitor checks the consumer. | Not the consumer heartbeat interval. |
| `max.poll.interval.ms` | Maximum gap between poll calls under Kafka consumer group protocol. | Can trigger a rebalance on slow processing, but is not Spring's monitor event. |
| `session.timeout.ms` | Deadline to detect consumer session loss with the group coordinator under the group protocol. | Does not directly reflect record-processing callback speed. |
| `heartbeat.interval.ms` | Heartbeat cadence in group protocol modes using this setting. | Having heartbeats does not guarantee the listener finished processing records. |
| `max.poll.records` | Maximum records returned per poll. | Too large a batch can lengthen the processing loop and raise poll-interval risk. |

For example, a listener processing a batch of 500 records where each record takes 2 seconds:

```text
500 records × 2 seconds ≈ 1,000 seconds of sequential processing
```

Even though `consumer.poll()` returned normally, the listener will take a very long time before calling poll again. This can emit `NonResponsiveConsumerEvent` and can also violate `max.poll.interval.ms`.

**Increasing `max.poll.interval.ms` does not fix an infinitely hung listener.** Likewise, lowering `noPollThreshold` does not make a stuck consumer work again; it only changes alert sensitivity.

### Distinguishing pause and stop

A consumer **paused** via Spring Kafka's supported APIs may continue polling to maintain group membership, depending on container state and operation. Thus, a valid paused state does not necessarily trigger non-responsive events.

`stop()` on a container is a lifecycle operation; once stopped, it is no longer expected to poll. When testing events, confirm the container is in the expected running state.

## 5. Goals of a non-responsive consumer test

A complete test should prove at minimum:

1. The container initializes, registers the listener, and joins the Kafka consumer group.
2. The listener receives a test message.
3. The listener is held incomplete so the container cannot return to poll.
4. The monitor emits one or more `NonResponsiveConsumerEvent`s within a bounded time window.
5. The event is captured by an observer listener with the right container/listener ID.
6. Once unblocked, the callback can finish and the container resumes operating per contract.
7. The test always releases latches/workers in `finally` so the suite never hangs.

In addition to the positive test, include a **negative test**: when a consumer processes quickly and polls normally, it must not report non-responsive due to miscalculated timeouts or an unstable setup.

Not every test needs to simulate a dead broker. A latch-based test is an effective way to verify the **no-poll detection mechanism**. A separate fault-injection test proves how the application behaves under real network/broker failures.

## 6. Test tiers: unit, integration, and fault injection

| Test tier | Purpose | Technique |
| --- | --- | --- |
| **Event handler unit test** | Ensure events are classified, logged, and fed into metrics/alerts properly. | Construct synthetic events/probes or invoke handler logic with mapped inputs. |
| **Embedded Kafka integration test** | Prove the container monitor emits events when a listener fails to return to poll. | `@EmbeddedKafka`, `CountDownLatch`, `@EventListener`, timeouts. |
| **Lifecycle recovery integration test** | Verify alert policy, unblocking the listener, resuming consumption, no restart loops. | Embedded Kafka/Testcontainers, awaiting states and records. |
| **Network fault injection** | Exercise broker/network errors affecting polling, coordinator, or metadata. | Controlled proxy, Testcontainers/Toxiproxy, isolated test Kafka environment. |
| **Soak/performance test** | Verify stable detection and recovery under high load, GC, DB/HTTP latency. | Long runs, multiple partitions, metrics, chaos scenarios. |

The latch-based test should be the **foundational test**, because it is easy to reproduce and does not depend on a network fault whose behavior varies across Kafka client versions.

## 7. Dependencies and configuration for integration tests

Gradle example using Spring Boot-managed compatible versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

`spring-kafka-test` provides `@EmbeddedKafka` and utilities to wait for consumer partition assignment.

In Spring Boot tests, configure String serializers and deserializers to keep fixtures simple:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.auto-offset-reset=earliest
```

These properties are examples for a **test profile**. In production, serializers/deserializers must match the message contract and have dedicated deserialization error handling.

Never use production topics or production consumer groups in tests. Isolate test consumer groups so running applications are unaffected.

## 8. Configuring the monitor with small thresholds in tests

In this example, we choose:

```text
pollTimeout      = 500 ms
noPollThreshold  = 3.0
monitorInterval  = 1 second
base threshold   = 1.5 seconds
```

Configuring the `ConcurrentKafkaListenerContainerFactory` bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class NonResponsiveTestKafkaConfig {

    @Bean("nonResponsiveTestFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    nonResponsiveTestFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.getContainerProperties().setPollTimeout(500L);
        factory.getContainerProperties().setNoPollThreshold(3.0f);
        factory.getContainerProperties().setMonitorInterval(1);

        return factory;
    }
}
```

Here:

- `setPollTimeout(500L)` keeps the expected threshold small.
- `setNoPollThreshold(3.0f)` expects an event after a no-poll gap longer than `3 × 500ms`.
- `setMonitorInterval(1)` makes the monitor check frequently enough for integration tests.
- `setConcurrency(1)` enforces a single consumer thread for one partition.

**Do not copy these ultra-low thresholds to production** if normal record processing takes more than a few seconds. Overly sensitive thresholds generate noisy alerts and can even trigger dangerous self-healing loops if the app auto-restarts.

In applications with multiple listener factories, confirm the test `@KafkaListener` uses the exact `containerFactory`. Tuning one factory has no effect on a listener running on another factory.

## 9. Creating an intentionally unresponsive test listener

Use `CountDownLatch` instead of `Thread.sleep(10000)` so the test explicitly controls when the callback is allowed to finish.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.KafkaListener;

public final class BlockingOrderListener {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final CountDownLatch completed = new CountDownLatch(1);
    final AtomicInteger deliveryCount = new AtomicInteger();

    @KafkaListener(
            id = "blocked-order-consumer",
            topics = "nonresponsive-consumer-it",
            containerFactory = "nonResponsiveTestFactory")
    public void onOrder(String message) throws InterruptedException {

        deliveryCount.incrementAndGet();
        entered.countDown();

        try {
            // Test intentionally holds the listener while processing.
            // Bounded timeout prevents CI from hanging indefinitely.
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Test fixture timed out");
            }
        } finally {
            completed.countDown();
        }
    }
}
```

Once the listener enters `onOrder(...)`, the consumer thread cannot return to the poll loop until the method finishes.

Advantages of this fixture:

- `entered` confirms the message was received, without guessing via arbitrary sleeps.
- `release` unblocks deterministically.
- `completed` lets the test wait for the callback to exit.
- The timeout guards against early test failure or abnormal teardown.
- `deliveryCount` helps verify message delivery.

**This simulates a blocked listener**, not `KafkaConsumer.poll()` hanging inside the Kafka client. That distinction must be stated clearly in test conclusions.

## 10. Collecting `NonResponsiveConsumerEvent`

Spring Kafka publishes container events via Spring's application event mechanism. Build a probe to collect events into a thread-safe queue:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

public final class NonResponsiveEventProbe {

    final BlockingQueue<NonResponsiveConsumerEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onEvent(NonResponsiveConsumerEvent event) {
        String listenerId = event.getListenerId();

        if (listenerId != null
                && listenerId.startsWith("blocked-order-consumer")) {
            events.offer(event);
        }
    }
}
```

With concurrent listener containers, the event's ID may carry a suffix identifying a child consumer depending on container structure. Therefore tests should not compare ID strings overly rigidly if concurrency settings change.

`LinkedBlockingQueue` is suitable for passing events from the monitor thread to the test thread. In a real monitoring app, never buffer unbounded events in memory; use bounded queues, aggregate metrics per container, and deduplicate alerts.

### Event contents

`NonResponsiveConsumerEvent` provides details such as listener/container identity and elapsed time since polling relevant to the alert. For example:

```java
long elapsedMs = event.getTimeSinceLastPoll();
String listenerId = event.getListenerId();
```

These values help tag logs/metrics with the exact container.

Do not blindly call `KafkaConsumer` methods from the monitor/event thread. `KafkaConsumer` is not a general thread-safe API; exceptions like `wakeup()` have specific usage rules and must be handled carefully. An event handler that merely records an alert is much safer than one that arbitrarily seeks, commits, or polls from another thread.

## 11. Integration test with `@EmbeddedKafka`

We combine:

1. An Embedded Kafka broker with one topic and one partition.
2. A Spring Boot application context with `KafkaTemplate`.
3. `BlockingOrderListener` registered via `@KafkaListener`.
4. `NonResponsiveEventProbe` receiving events.
5. A test that sends a message, waits for the callback to block, and awaits the event.

Structurally complete integration test class example:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "nonresponsive-consumer-it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@Import(NonResponsiveConsumerIT.FixtureConfiguration.class)
class NonResponsiveConsumerIT {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    BlockingOrderListener blockingListener;

    @Autowired
    NonResponsiveEventProbe eventProbe;

    @Test
    void emitsEventWhenListenerDoesNotReturnToPoll()
            throws Exception {

        try {
            var container =
                    registry.getListenerContainer("blocked-order-consumer");

            assertThat(container).isNotNull();

            // Wait for the consumer to actually be assigned partitions.
            ContainerTestUtils.waitForAssignment(container, 1);

            template.send(
                    "nonresponsive-consumer-it",
                    "order-1",
                    "payload").get(10, TimeUnit.SECONDS);

            assertThat(
                    blockingListener.entered.await(
                            10, TimeUnit.SECONDS))
                    .as("Listener should receive the test message")
                    .isTrue();

            NonResponsiveConsumerEvent event =
                    eventProbe.events.poll(8, TimeUnit.SECONDS);

            assertThat(event)
                    .as("Monitor should detect lack of polling")
                    .isNotNull();

            assertThat(event.getListenerId())
                    .startsWith("blocked-order-consumer");

            assertThat(event.getTimeSinceLastPoll())
                    .isGreaterThan(0L);

        } finally {
            // Always release the consumer thread,
            // even if the assertions above fail.
            blockingListener.release.countDown();
        }

        assertThat(
                blockingListener.completed.await(
                        5, TimeUnit.SECONDS))
                .as("Listener should be released after the test")
                .isTrue();
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableKafka
    static class FixtureConfiguration {

        @Bean("nonResponsiveTestFactory")
        ConcurrentKafkaListenerContainerFactory<String, String>
        nonResponsiveTestFactory(
                ConsumerFactory<String, String> consumerFactory) {

            var factory =
                    new ConcurrentKafkaListenerContainerFactory
                            <String, String>();

            factory.setConsumerFactory(consumerFactory);
            factory.setConcurrency(1);
            factory.getContainerProperties().setPollTimeout(500L);
            factory.getContainerProperties().setNoPollThreshold(3.0f);
            factory.getContainerProperties().setMonitorInterval(1);

            return factory;
        }

        @Bean
        BlockingOrderListener blockingListener() {
            return new BlockingOrderListener();
        }

        @Bean
        NonResponsiveEventProbe eventProbe() {
            return new NonResponsiveEventProbe();
        }
    }
}
```

### Assumptions of this example

- The application has `@SpringBootApplication` or an appropriate Spring Boot configuration for `@SpringBootTest` to find a context.
- `BlockingOrderListener` and `NonResponsiveEventProbe` are the two classes from previous sections added to test sources.
- The test uses `spring-kafka-test` compatible with the application's Spring Kafka version.
- KafkaTemplate and ConsumerFactory are auto-configured by Spring Boot with String serializers/deserializers per the illustrative properties.
- Only one `blocked-order-consumer` instance exists in the test context; topic and group are not shared with interfering tests.
- `@EmbeddedKafka` creates an isolated test broker and binds it via `spring.kafka.bootstrap-servers`.
- A real consumer is running, not merely a listener object invoked directly in a unit test.

Different versions may support different utility overloads and Embedded Kafka properties. The invariant test flow is **wait for partition assignment, send record, wait for listener block, then receive event**, without forcing every import line to one exact release.

### Why wait for partition assignment?

If you send immediately when the test context boots, the consumer may not have received partitions yet. With `auto.offset.reset=latest`, a new consumer can miss records sent before its starting position is established. Using `earliest` in tests and waiting for assignment reduces race conditions; waiting for assignment also proves the container joined the Kafka group before testing begins.

### Why not just use `Thread.sleep(3000)`?

A test like:

```java
Thread.sleep(3000);
assertThat(events).isNotEmpty();
```

does not prove the listener received a message and blocked. On slow CI, three seconds can elapse before the consumer even joins the group. Tests with latches and event queues are far more reliable because they wait on **conditions**, not guessed durations.

### Why can tests receive multiple events?

The monitor may continue emitting `NonResponsiveConsumerEvent` on subsequent periodic checks while the consumer has still not returned to poll. Tests only need to assert **at least one matching event**. In real applications, if alerts repeat, apply cooldowns or coalescing per listener/container ID.

## 12. Testing consumer recovery after unblocking

Detecting the event is half the story. Reliability testing must prove that once the blocking condition disappears, the consumer resumes processing.

Extend the fixture to track the next delivery:

```java
final CountDownLatch secondDelivered = new CountDownLatch(1);

@KafkaListener(
        id = "blocked-order-consumer",
        topics = "nonresponsive-consumer-it",
        containerFactory = "nonResponsiveTestFactory")
public void onOrder(String message) throws InterruptedException {
    int count = deliveryCount.incrementAndGet();

    if (count == 1) {
        entered.countDown();
        if (!release.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Fixture timed out");
        }
        completed.countDown();
    } else {
        secondDelivered.countDown();
    }
}
```

After the test receives the event:

```java
blockingListener.release.countDown();

assertThat(
        blockingListener.completed.await(
                5, TimeUnit.SECONDS))
        .isTrue();

template.send(
        "nonresponsive-consumer-it",
        "order-2",
        "second-payload").get(10, TimeUnit.SECONDS);

assertThat(
        blockingListener.secondDelivered.await(
                10, TimeUnit.SECONDS))
        .as("Consumer should process another record after release")
        .isTrue();
```

This is a **replacement extension of the listener method** in the fixture—never run two `@KafkaListener` methods with the same ID concurrently in the same test context.

Note: if the first callback blocks **too long**, the consumer may exceed `max.poll.interval.ms` and trigger a rebalance. The test may still recover after reassignment, though latency and record ordering differ from a short monitor test. To test only the monitor event cleanly, keep the block shorter than the poll interval limit and avoid mixing in a rebalance scenario unintentionally.

### Do not rely on "events disappearing immediately" as the sole recovery signal

Events are point-in-time notifications. Once the listener is unblocked, events already sitting in the queue are not removed automatically. Moreover, the monitor might emit one more event right before the consumer returns to poll.

Measure recovery by **poll/receive progression**, processing new messages, and appropriate metrics—not just `events.isEmpty()`.

## 13. Negative test: healthy consumer is not falsely flagged

A negative test catches overly sensitive thresholds or probes capturing events from the wrong source.

Scenario:

1. Use a simple non-blocking listener that returns immediately.
2. Wait for partition assignment.
3. Send several records and confirm all are processed.
4. Over a reasonably sized observation window, confirm zero `NonResponsiveConsumerEvent`s fire for that listener.
5. Exclude events from other listeners in the same context.

A normal listener:

```java
public final class FastListener {
    private final CountDownLatch received = new CountDownLatch(3);

    @KafkaListener(
            id = "fast-consumer",
            topics = "fast-consumer-test",
            containerFactory = "nonResponsiveTestFactory")
    public void onMessage(String payload) {
        received.countDown();
    }
}
```

To verify "no event," use a probe filtering for `fast-consumer` and a finite observation window, **without claiming no event could ever happen forever**. A negative result holds only within the measured duration and test environment.

Negative tests can experience noise if a CI machine pauses the JVM too long, hits an unusual GC pause, or gets overloaded. This is why thresholds must not be set too small and timing assertions must not be overly tight.

## 14. Limitations of latch-based tests

A fixture using `CountDownLatch` proves one specific case: **the consumer fails to return to poll because the message handler is waiting**. It does not necessarily simulate:

- Half-open TCP connections between Kafka client and broker.
- Kafka client threads stuck deep inside `poll()`.
- Abnormal DNS or TLS handshakes.
- Slow broker metadata/coordinator responses.
- Prolonged consumer group rebalances.
- An application experiencing real CPU starvation.

Thus, the accurate conclusion is:

> "With the tested monitor configuration, when the listener does not complete and polling fails to advance past the threshold, Spring Kafka emits `NonResponsiveConsumerEvent` as expected."

**Do not conclude:** "This test proves the application automatically recovers from every Kafka network failure." That requires dedicated network fault testing and recovery strategies.

## 15. Fault injection: simulating network/broker issues

For deeper reliability testing, use an isolated Kafka test environment such as Testcontainers Kafka combined with a network proxy like Toxiproxy.

Goals can include:

- Injecting latency or severing connections between consumer and broker.
- Creating intermittent network dropouts followed by recovery.
- Stopping or restarting a broker in a test cluster.
- Simulating a network partition between consumer and broker.
- Observing listener containers, error events, consumer group assignments, and post-recovery consumption.

Diagram:

```text
Spring Kafka Consumer
        |
        v
  Network proxy (Toxiproxy)
        |
        v
    Kafka Broker
        |
        v
  Topic/Partitions
```

**Important note when proxying Kafka:** the Kafka client does not use only the bootstrap address. After fetching metadata, clients connect to brokers via `advertised.listeners`. If advertised endpoints bypass the proxy, a test that "cut the bootstrap connection" still lets real traffic flow straight to the broker without simulating the outage. All broker endpoints must route through the test network as designed.

Do not use network faults to force a Kafka client into an infinite hang based on rigid assumptions. The Kafka client has timeouts and reconnects and may keep returning empty polls, throwing exceptions, rebalancing, or retrying **without emitting `NonResponsiveConsumerEvent`**. That can still be valid behavior depending on the fault.

A good fault-injection test records:

1. The fault was triggered at the intended endpoint.
2. Whether the consumer is still polling.
3. Which events appeared (`NonResponsiveConsumerEvent`, error events, rebalances, stopped, etc.).
4. How the consumer group was affected.
5. Whether all records finished processing after the fault cleared.
6. Whether duplicates occurred due to retries/offset commits.
7. Whether the application had to restart containers or processes.

## 16. Production event handlers: observe first, react with control

Upon receiving `NonResponsiveConsumerEvent`, the first action should normally be **structured logging and incrementing metrics**, not automatically killing the consumer.

Example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public final class ConsumerResponsivenessObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerResponsivenessObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
                "kafka.consumer.nonresponsive listenerId={} "
                    + "timeSinceLastPollMs={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll()
        );

        // Increment metrics or notify monitoring here.
        // Do not invoke non-thread-safe KafkaConsumer operations
        // directly from the event thread.
    }
}
```

Event handlers should execute quickly. If a handler makes slow HTTP calls to an alerting system, it can itself stall the event-publishing thread or overload monitoring.

### Information to include in alerts

- `listenerId` and container ID.
- Application instance/pod/host.
- Consumer group ID.
- Relevant topic/partition if identifiable.
- `timeSinceLastPollMs`.
- Event start time and repeat count.
- Kafka consumer lag per partition.
- Last successfully processed offset and timestamp.
- `max.poll.interval.ms`, `pollTimeout`, `noPollThreshold`, `monitorInterval`.
- CPU, GC pauses, active threads, blocked threads, DB/HTTP latency.

Never dump full `ConsumerRecord` objects or unfiltered payloads into alerts. Message data may contain PII or internal details.

## 17. Should containers auto-restart when receiving this event?

**Do not restart automatically by default on every event.** Consider what can happen:

- The listener is processing a valid record that simply takes longer.
- An external API is waiting to respond; restarting the container does not erase external side effects.
- A "poison" message repeatedly blocks the listener; restarting only creates a crash loop.
- `max.poll.interval.ms` or rebalancing already stripped the consumer's assignment; restarting adds extra churn.
- If the listener uses transactions or manual acknowledgments, restarting can trigger redelivery.
- Events emit repeatedly, causing multiple restart commands to race.

A remediation policy should consider:

| Condition | Suggested action |
| --- | --- |
| Single brief event, low lag, consumer subsequently progresses | Log/metric and monitor. |
| Consecutive events with zero offset progression | Alert and capture thread dumps before intervening. |
| Thread stuck on remote call | Check timeouts, circuit breakers, dependency health. |
| Thread genuinely hung inside Kafka poll/network | Consider supported wakeup/stop/restart with lifecycle control. |
| Repeated crash/restart on the same record | Investigate poison records, retries/DLT, and idempotency. |
| Consumer group constantly rebalancing | Inspect poll intervals, batch sizes, static membership, and resources. |

If automated recovery is required:

1. Apply a **cooldown** to prevent continuous restarts.
2. Allow only one active remediation per container at a time.
3. Inspect container state and current assignments.
4. Persist the root-cause event before restarting.
5. Use container lifecycle APIs matching your version and thread contract.
6. Wait for the container to stop completely before starting again if policy demands.
7. Cap restart attempts and escalate to operators if no progress occurs.
8. Verify message processing idempotency across redeliveries.

**Never call `consumer.poll()`, `commitSync()`, or `seek()` arbitrarily from the event thread.** `KafkaConsumer` enforces strict thread-ownership rules, and mutating offsets while a worker is processing a record can break ordering and correctness.

## 18. `wakeup()` is not a "fix every consumer" button

The Kafka consumer API provides `wakeup()`, which may be called from another thread per Kafka client rules to interrupt interruptible consumer operations. However:

- It does not cause a listener callback blocked on DB/HTTP I/O to exit on its own.
- It does not replace network or transaction timeouts.
- It can raise an exception handled by the Kafka client/container under its own lifecycle.
- It does not confirm the current record was committed or finished.
- Calling it indiscriminately makes operational incidents harder to diagnose.

Therefore, if the application uses wakeup as part of recovery, test both polling during real I/O and blocking **inside the listener**. Never call `wakeup()` without understanding how your container version handles exceptions and offsets.

## 19. Impact on at-least-once and offset commits

A consumer that stops polling for too long can trigger group timeouts or rebalances. When a partition is reassigned to another consumer, uncommitted messages can be redelivered.

Suppose:

```text
Consumer A polls record offset=100
        |
        v
Listener A calls remote API, takes too long
        |
        v
max.poll.interval.ms exceeded
        |
        v
Group changes assignments
        |
        v
Consumer B receives partition, may re-read offset=100
        |
        v
Remote operation risks executing twice
```

Redelivery extent depends on commit mode, transactions, and committed offsets. Yet the general rule for at-least-once processing is that **the same record can be processed more than once** during failures or rebalances.

Hence, reliability tests should not assert only "event emitted." For critical business flows, also verify:

- A stable business key/idempotency key in messages.
- Tracking of successfully processed offsets.
- Zero duplicate side effects or working deduplication.
- Distinguishing in-flight records from acked/committed records.
- Retries and DLTs for poison records.
- Once the consumer recovers, offset progression resumes from a valid position.

Never use the event to auto-commit offsets for partially processed records just to "make lag drop." That risks data loss.

## 20. Test differences by ack mode and batch processing

Spring Kafka supports multiple ack/commit modes via the container. Tests must reflect the real policy:

| Processing style | What to verify when consumer stops polling |
| --- | --- |
| Record listener, default container ack | Whether the in-flight message was committed; whether restart redelivers it. |
| Manual ack | Whether listener acks before or after side effects; how blocking before ack replays. |
| Batch listener | Whether a large batch stretches the poll gap; whether failing records affect the whole batch. |
| Transactional Kafka processing | How transaction timeouts, abort/retry, and in-transaction offset commits behave. |
| Concurrent listener containers | Which child emitted the event; whether one partition or many are affected. |
| Retry/DLT | Whether poison records have bounded retries or block a worker indefinitely. |

A test with one partition and one consumer proves monitor logic, yet **does not represent multi-partition/concurrency setups**. When scaling up, attach probes per listener/container ID and verify full assignments.

### Do not mask issues with high concurrency

Raising concurrency can improve aggregate throughput while one child is blocked, yet that blocked child still holds its assigned partitions and stops processing new records on them. Total lag might look fine while one partition falls behind. Monitor lag and last processed offset **per partition** when strict progress guarantees matter.

## 21. Avoiding flakiness in CI

Real-time and multi-threaded tests face sources of variance: Embedded Kafka startup, JVM warmup, CI schedulers, GC, rebalancing, and log I/O.

Mitigations:

1. **Wait for partition assignment** before sending records.
2. **Wait for the listener entered latch** before awaiting the event.
3. **Set test thresholds small enough yet away from 0**: `pollTimeout=500ms`, `noPollThreshold=3.0`, `monitorInterval=1s` is just one example.
4. **Use bounded waits** for events rather than sleep-then-check.
5. **Do not assert exact event timestamps**; assert the event arrives within a generous window.
6. **Filter events by listener ID**; a Spring context may contain multiple KafkaListeners.
7. **Always release latches in `finally`**.
8. **Do not run tests sharing groups/topics/fixtures** if they can steal records.
9. **Do not depend on cross-partition delivery order** unless required by the application.
10. **Clean up/restart contexts thoughtfully**, avoiding killing active consumers mid-test.
11. **Do not use production thresholds** in short tests if the monitor defaults to 30 seconds.
12. **Collect logs/topic/group diagnostics on failure** to separate setup bugs from feature bugs.

### Controlling test teardown

If an assertion fails before calling `release.countDown()`, the consumer thread can stay blocked. Thus `try/finally` is mandatory. In addition, the listener fixture should include an internal timeout so it exits on its own if the test runner dies unexpectedly.

If using `@DirtiesContext` to isolate tests, weigh the cost of restarting Embedded Kafka across many tests. Never call `context.close()` arbitrarily mid-suite if other beans still use consumers/containers.

## 22. Debugging when `NonResponsiveConsumerEvent` is not received

Suppose a test waits 10 seconds and receives no event. Check in order:

### 22.1. Did the listener receive the message?

If `entered.await(...)` fails, possible causes include:

- Container has not been assigned partitions.
- Producer sent to the wrong topic.
- Wrong group or deserializer.
- Embedded Kafka bootstrap servers not wired properly.
- Container factory or KafkaListener bean not registered.
- Topic/partition missing or wrong test profile active.

**Do not investigate the monitor before proving the listener actually began processing.**

### 22.2. Is the right factory attached?

`@KafkaListener` must specify `containerFactory="nonResponsiveTestFactory"` if thresholds were set on that factory. If forgotten, the listener may use the default `kafkaListenerContainerFactory` whose monitor threshold exceeds the test wait window.

### 22.3. Is the monitor checking at the expected cadence?

Verify the runtime values of `pollTimeout`, `noPollThreshold`, and `monitorInterval` on the running container. If the threshold is a few seconds while the monitor checks once every 30 seconds, an 8-second test wait is too short.

### 22.4. Did the callback genuinely block?

A test listener method can exit early because:

- The latch was already counted down by an earlier test.
- Test code blocks only on a specific payload that was not matched.
- An exception terminated the callback.
- The test sent records to a different listener.

Use `entered`, `completed`, and invocation counts to confirm state.

### 22.5. Is the probe registered in the Spring context?

`@EventListener` only works on Spring-managed beans. If a test instantiates `new NonResponsiveEventProbe()` manually without registering it as a bean, the event publisher never notifies it.

### 22.6. Were events filtered out by ID?

Concurrent containers can emit events with suffixed IDs. Exact string comparisons in the probe can drop valid events.

### 22.7. Did application threads stall globally?

If the entire JVM paused for a long time or CI runners were starved of resources, the monitor cannot run on schedule either. Timing tests can skew and need CPU/GC/scheduling analysis.

## 23. Debugging when events fire even though the consumer seems "healthy"

A non-responsive warning does not automatically mean a Kafka client bug.

Questions to check:

- Is the listener processing a valid record that legitimately takes a long time?
- Is a synchronous retry/backoff holding the listener thread?
- Is the database hitting lock waits?
- Is a remote API call missing a timeout?
- Are too many records returned per poll via `max.poll.records`?
- Are thread pools/CPU/GC overloaded?
- Was the monitor threshold set lower than normal P99 processing time?
- Is the container in the middle of start/stop/rebalance?
- Did the event originate from a different child container?

If valid business processing routinely takes long, optimize processing, shrink batch/poll sizes, offload slow work from the consumer thread, or tune configuration. Raising thresholds solely to silence alerts can hide a real bottleneck.

## 24. Investigating a genuinely stuck consumer

An operational runbook might follow:

1. Identify `listenerId`, group, topic/partition, instance, and event timestamp.
2. Check `timeSinceLastPollMs` and repeat count.
3. Inspect consumer lag/offset progression per partition.
4. Capture **thread dumps** to see whether consumer threads are in `poll()`, listener callbacks, JDBC, HTTP, or lock waits.
5. Check CPU, GC pauses, thread pools, and connection pools.
6. Check broker health, network latency, coordinator/rebalance logs.
7. Compare `max.poll.interval.ms` against P99 processing time.
8. Only after classifying the root cause, choose a fix: timeouts, retries, DLT, higher parallelism, fixing deadlocks, or controlled restarts.
9. After recovery, confirm messages process properly with zero data loss and zero duplicate side effects.

Never conclude a thread is deadlocked from `timeSinceLastPollMs` alone. It is a trigger to start investigation.

## 25. Observability: metrics, logging, and alerts

Useful signals:

| Signal | Content | Usage |
| --- | --- | --- |
| `nonresponsive_event_total` | Event count by listener/group and environment. | Detect rising alert frequency. |
| `time_since_last_poll_ms` | No-poll duration reported by monitor. | Separate brief blips from prolonged stalls. |
| Consumer lag per partition | Unconsumed records vs. end offset. | Spot stalled progress and backlogs. |
| Last processed offset/time | Most recent successful offset/timestamp. | Detect lack of progress while app stays up. |
| Listener processing duration | P50/P95/P99 record/batch handling time. | Tune batch size and poll intervals. |
| Retry/DLT count | Repeating business errors. | Distinguish poison records from infrastructure issues. |
| Rebalance count/duration | Frequency of group assignment changes. | Correlate with poll intervals. |
| JVM threads/GC/CPU | Resource pressure. | Diagnose stalled threads. |
| DB/HTTP latency | Latency of dependencies outside Kafka. | Pinpoint where listeners block. |

The metric names above are **design suggestions**, not all exported verbatim by Spring Kafka/Micrometer out of the box. For custom metrics, use low-cardinality tags like `listenerId`, `groupId`, and environment; never put per-message keys or offsets in metric tags.

### When to alert?

Policy example:

```text
If one NonResponsiveConsumerEvent occurs:
  -> log WARN, increment counter, record lastPollGap

If events repeat and offset progression stalls:
  -> alert operator + capture thread dump

If lag exceeds SLA or consumer leaves group:
  -> higher-severity incident

If consumer recovers and processes a new record:
  -> record recovered state, resolve alert after cooldown
```

These are **operational suggestions**, not Spring Kafka defaults. Choose thresholds based on data processing times and business needs.

## 26. Hands-on exercises

Build `orderEventsListener` consuming order events from topic `orders-events` and calling a remote service to check product status. Sometimes the remote service takes 20 seconds to respond.

### Part A – Detection

1. Create a `ConcurrentKafkaListenerContainerFactory` with test-appropriate `pollTimeout`, `noPollThreshold`, and `monitorInterval`.
2. Create a test listener using `CountDownLatch` to block after receiving a record.
3. Create an event probe capturing `NonResponsiveConsumerEvent` filtered by listener ID.
4. Use `@EmbeddedKafka` to send a record and wait for partition assignment.
5. Assert an event fires after the listener blocks, using a bounded timeout.
6. Release the latch inside `finally`.

### Part B – Recovery

1. Let the listener complete, then send a subsequent record.
2. Confirm the consumer actually resumes receiving and processing messages.
3. Verify zero duplicate side effects when callbacks complete/retry.
4. Try lengthening the block to observe the impact of `max.poll.interval.ms` and rebalances.

### Part C – Real faults

1. Use a test Kafka cluster + proxy to test network latency and disconnects.
2. Record whether `NonResponsiveConsumerEvent` fires under each fault type.
3. Observe group assignments and lag.
4. Restore the network and verify the consumer resumes consuming.
5. Do not treat "no non-responsive event" as a test failure if the client kept polling normally under that fault.

### Part D – Operations

1. Add structured logging with listener ID, time without polling, and host.
2. Add an alert only when zero offset progression persists across multiple cycles.
3. Capture thread dumps when events repeat.
4. Test one listener blocked on HTTP alongside one listener processing normally.
5. Discuss the impact of container restarts on at-least-once delivery and idempotency.

### Self-assessment questions

- What is the difference between `ListenerContainerIdleEvent` and `NonResponsiveConsumerEvent`?
- Why does a non-responsive event not prove the Kafka broker is down?
- What are the distinct roles of `monitorInterval`, `pollTimeout`, and `noPollThreshold`?
- Why should you not assert the event arrives at the exact moment `noPollThreshold × pollTimeout`?
- If a listener blocks in an HTTP call, is `wakeup()` guaranteed to recover the listener?
- How does `max.poll.interval.ms` relate to taking too long on a batch?
- After a Kafka rebalance, why can a record be processed again?
- How do you distinguish an idle consumer, a blocked consumer, and a consumer that simply has high lag?

## References

- [Spring for Apache Kafka Reference – Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): listener container events, including `NonResponsiveConsumerEvent`.
- [Spring for Apache Kafka Reference – Non-Responsive Consumer](https://docs.spring.io/spring-kafka/reference/kafka/non-responsive-consumer.html): monitor settings and detecting consumers that stop polling.
- [Spring for Apache Kafka Reference – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html): `pollTimeout`, `noPollThreshold`, `monitorInterval`, and container settings.
- [Spring for Apache Kafka Reference – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `spring-kafka-test`, listener testing.
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.interval.ms` and Kafka consumer settings.
- [Apache Kafka – KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi): poll rules, timeouts, wakeup, and thread safety.
- [Testcontainers – Kafka Module](https://java.testcontainers.org/modules/kafka/): containerized Kafka testing, suited for integration and fault injection.

