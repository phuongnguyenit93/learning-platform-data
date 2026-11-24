# Testing Consumer Idle Events in Spring Kafka

## 1. Problem: how to know a consumer is not receiving new records?

A Spring Kafka application has consumers processing orders, payments, or data sync events. There are times when a topic genuinely has no new messages: overnight, end of a processing cycle, or when upstream pauses publishing. Yet there are also cases where a consumer stops receiving messages due to misconfiguration, lost connectivity, unassigned partitions, a paused consumer, or a stalled `poll()` loop.

In operations, we need a signal indicating **the listener container has received no records for a period of time**, and we need to test that signal. Spring for Apache Kafka provides `ListenerContainerIdleEvent` for this purpose.

```text
Kafka topic / partitions
          |
          v
KafkaConsumer.poll(...)
          |
          +---- Has records ----> @KafkaListener processes records
          |                         |
          |                         +--> If previously idle:
          |                              ListenerContainerNoLongerIdleEvent
          |
          +---- Continuously no records
                    |
                    +---- Exceeds idleEventInterval
                              |
                              v
                    ListenerContainerIdleEvent
                    (can emit repeatedly while still idle)
```

**Testing consumer idle events** means verifying that Spring Kafka actually publishes `ListenerContainerIdleEvent` when no records are delivered to the container, and can publish `ListenerContainerNoLongerIdleEvent` when data resumes. Tests must also distinguish valid idle periods from operational errors, never assuming every gap in messages means a broken consumer.

Desired outcomes:

- Explicit idle threshold configuration that can be shortened specifically in tests.
- Events captured via Spring `@EventListener` or `ApplicationListener`.
- Tests verifying the exact **listener/container**, idle duration, and behavior once messages reappear.
- Tests independent of `Thread.sleep(...)` and exact scheduler/poll timing assumptions.
- Edge cases such as unresponsive polls, pauses, empty partitions, and concurrent consumers addressed separately.

## 2. What is `ListenerContainerIdleEvent`?

`ListenerContainerIdleEvent` resides in package:

```java
org.springframework.kafka.event.ListenerContainerIdleEvent
```

When `idleEventInterval` is configured, the listener container can publish an event after going without records for that duration. While still idle, the event continues to be emitted at that interval—**it is not a one-time event**.

| Property / API | Meaning |
|---|---|
| `getListenerId()` | Listener ID, or container name if no listener ID was declared. |
| `getIdleTime()` | Duration the container has been idle in **milliseconds** when the event was published. |
| `getTopicPartitions()` | Topic-partitions currently assigned to the consumer when the event was created. |
| `getConsumer()` | Kafka `Consumer` reference if available; subject to strict thread-safety constraints. |
| `isPaused()` | Whether the consumer was paused when the event was published. |
| `getContainer()` | Container associated with the event; under concurrency, may be the parent container. |
| `getSource()` | The container object that directly emitted the event. |

**Limitation:** `getIdleTime()` reflects the idle duration recorded by the container, not a clock guaranteed to the exact millisecond. Events depend on the poll loop, scheduling, assignment, and container state. Therefore, assertions should use **reasonable duration bounds and finite timeouts**, rather than requiring the event at exactly 1,000 ms.

### 2.1. `idleEventInterval` and `idleBeforeDataMultiplier`

`ContainerProperties` has key settings:

| Property | Meaning | Common default in Spring Kafka 3.x |
|---|---|---|
| `idleEventInterval` | Threshold/interval between `ListenerContainerIdleEvent` emissions. | `null`: container idle events disabled. |
| `idleBeforeDataMultiplier` | Multiplier applied to the idle threshold **before the consumer receives its first record**. | `5.0`. |
| `idlePartitionEventInterval` | Enables idle events **per partition**. | `null`. |
| `pollTimeout` | Timeout for `KafkaConsumer.poll(...)`; can affect event detection latency. | Varies by container version/config. |
| `monitorInterval` | Monitor cadence in seconds for detecting unresponsive polls. | Typically 30 seconds. |
| `noPollThreshold` | Multiplier relative to `pollTimeout` for treating a poll as unresponsive. | Typically `3.0`. |

For example, if `idleEventInterval = 1,000 ms` and `idleBeforeDataMultiplier = 5.0`, a consumer **that has never received data** may take around 5 seconds of idleness before emitting its first event. Once it has received a record, the threshold returns to about 1 second. This is a common reason a test waiting 2 seconds fails even when `idleEventInterval=1s` is configured correctly.

In integration tests, you can set `idleBeforeDataMultiplier=1.0` to observe startup behavior immediately, or **send one record, confirm the listener received it**, and then wait for idle state. The second approach mirrors the real lifecycle better when testing active → idle → active transitions.

### 2.2. `idleBetweenPolls` is not the idle event interval

`idleBetweenPolls` intentionally sleeps the consumer thread between polls to throttle delivery rate. It is **not the configuration for emitting `ListenerContainerIdleEvent`**. Likewise, Kafka property `max.poll.interval.ms` bounds the maximum time between polls before a consumer is considered unresponsive to the group, not Spring Kafka's message-idle threshold.

### 2.3. Events published by Spring, not messages in a Kafka topic

`ListenerContainerIdleEvent` is a **Spring `ApplicationEvent` inside the same application**, not a record automatically sent by the broker to a topic. To send alerts to external systems, the application must explicitly translate the event into metrics/logs/notifications via an appropriate service.

Consequently, you cannot test this by waiting for a Kafka producer to send a record named `ListenerContainerIdleEvent`. Observe the **Spring ApplicationContext event bus** or a side effect of a registered handler.

## 3. Distinguishing idle from other phenomena

Frequently confused related events:

| Event / state | Trigger | Operational meaning |
|---|---|---|
| `ListenerContainerIdleEvent` | Container received no records past configured idle interval. | No records delivered to consumer; **not by itself proof of failure**. |
| `ListenerContainerNoLongerIdleEvent` | A record arrives after the container emitted an idle event. | Consumer is receiving data again. |
| `ListenerContainerPartitionIdleEvent` | An assigned partition received no records for its interval. | One partition is idle even while others stay active. |
| `ListenerContainerPartitionNoLongerIdleEvent` | An idle partition begins receiving records again. | Tracks per-partition recovery. |
| `NonResponsiveConsumerEvent` | Consumer `poll()` did not return within monitor threshold. | Investigate blocked/slow poll, unlike regular polls returning empty. |
| Consumer paused | Listener container or consumer is paused. | May be intentional (backpressure, retries, operations). |
| High consumer lag | Broker end offset exceeds committed offset/processing progress. | Consumer has an unprocessed backlog; cannot be inferred from idle alone. |
| Container stopped | Listener container is not running. | Normal idle events are not expected once stopped. |

An idle consumer can be completely **healthy** when the broker has no messages. Conversely, a consumer with high lag might still receive no records due to assignment, pause, auth errors, poll configuration, or topology. Reliable alerting combines idle events with lag, assignment state, container liveness, producer rate, and business traffic expectations.

## 4. Configuring idle events in Spring Boot

The examples below target **Java 17+, Spring Boot 3.x, and Spring Kafka 3.x**. Projects on Spring Boot 4.x / Spring Kafka 4.x must cross-check APIs and property names for their version.

### 4.1. Using `application.yml`

Spring Boot supports configuring listener idle intervals via properties:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      auto-offset-reset: earliest
    listener:
      idle-event-interval: 60s
      idle-partition-event-interval: 120s
```

When Boot applies this configuration to the Boot-managed `ConcurrentKafkaListenerContainerFactory`, the container emits `ListenerContainerIdleEvent` after 60 seconds without data, and partition idle events at 120 seconds when supported.

In production, pick thresholds matching the **real data cadence**. A topic that only receives messages at end-of-day should not trigger incidents every minute. You can omit partition idle configuration if only container-level idle detection is needed, reducing unnecessary events.

### 4.2. Configuring `ConcurrentKafkaListenerContainerFactory` directly

When controlling a specific group of listeners, configure a container factory:

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class OrderKafkaListenerConfig {

    @Bean("ordersListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> ordersListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        configurer.configure(factory, consumerFactory);

        factory.getContainerProperties().setIdleEventInterval(60_000L);
        factory.getContainerProperties().setIdlePartitionEventInterval(120_000L);
        return factory;
    }
}
```

`ConcurrentKafkaListenerContainerFactoryConfigurer` preserves baseline Boot settings (deserializers, error handling, and other listener properties) before overriding specific fields. For a completely custom factory, ensure `ConsumerFactory` and related settings are configured explicitly.

Declaring the listener:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderMessageListener {

    @KafkaListener(
            id = "ordersConsumer",
            topics = "orders.events",
            groupId = "orders-worker",
            containerFactory = "ordersListenerFactory")
    public void handle(String payload) {
        // Business processing; do not log unbounded message payloads.
    }
}
```

The listener `id` is a convenient key for filtering idle events. In concurrent containers, child listener IDs can carry suffixes like `ordersConsumer-0`, `ordersConsumer-1`; avoid coupling to exact child names when monitoring the whole listener group.

## 5. Capturing idle events with `@EventListener`

A Spring bean can observe `ListenerContainerIdleEvent`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
class KafkaIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith("ordersConsumer")) {
            return;
        }

        log.info("kafka.consumer.idle listenerId={} idleMs={} "
                        + "partitions={} paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused());
    }
}
```

Spring `ApplicationEvent`s are published within the same `ApplicationContext`. An `@EventListener` handler **can receive events from all listener containers** in the context, so filter by listener ID, container, or an appropriate predicate. Without filtering, a test with multiple listeners can pass falsely on an idle event from an unrelated listener.

You can also write:

```java
@EventListener(condition = "#event.listenerId.startsWith('ordersConsumer')")
public void onIdle(ListenerContainerIdleEvent event) {
    // Monitor only the ordersConsumer listener group.
}
```

When using SpEL in `condition`, ensure compatibility with Spring Framework syntax and parameter-name retention; if compiled without parameter name metadata, prefer documented conditions or Java filtering in the method body as in the first example for easier testing.

### 5.1. Do not perform heavy work on the consumer thread

By default, event listeners run on the **thread publishing the event**, i.e., the consumer thread. If an idle handler performs slow HTTP requests, heavy database queries, or `Thread.sleep`, it can stall the `poll()` loop and cause consumer group issues.

Safer pattern:

```text
Consumer thread
   |
   +-- @EventListener -> update counter / push lightweight event to queue
                           |
                           v
                      Dedicated worker/monitor
                           |
                           +-- Alerts / metrics / policy decisions
```

When only recording metrics/counters, keep the handler short and non-blocking. When network alerts are needed, hand **copied metadata** (listener ID, idle time, partitions) to an executor/queue rather than passing the `Consumer` to another thread to invoke Kafka APIs arbitrarily.

### 5.2. Do not stop child containers on the callback thread

If policy stops an idle listener container, **never call `container.stop()` directly on the consumer thread inside the idle handler**. Doing so causes unnecessary delays and log noise. For concurrent containers, control the **parent concurrent listener container** from a separate coordinator thread rather than stopping a single child container.

For management, look up the container by ID via `KafkaListenerEndpointRegistry` and trigger actions from a dedicated task executor once stopping is genuinely warranted. Normal idleness is not by itself a reason to stop/restart.

## 6. Core testing: record received, goes idle, then becomes active again

A reliable integration test must prove all three logical milestones:

```text
[A] Consumer receives message -> proves consumer was assigned partition
               |
               v
[B] No more messages sent -> receives ListenerContainerIdleEvent
               |
               v
[C] New message sent -> consumer receives +
    ListenerContainerNoLongerIdleEvent
```

This sequence is far better than starting against an empty topic and waiting a few hundred milliseconds, because it also verifies the consumer can actually receive data. It also avoids stumbling over the **default 5x startup idle multiplier** before the first record arrives.

### 6.1. Gradle dependencies

Example Groovy `build.gradle` with Spring Boot plugin/BOM managing versions:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-kafka-test` provides `@EmbeddedKafka` and test utilities. If the application already pulls Spring Kafka through another starter/dependency, preserve the project's dependency layout without mixing incompatible Kafka client versions. This lesson **does not require running Gradle to follow the concepts**, though in real projects integration tests run against embedded or containerized Kafka per the build setup.

### 6.2. Complete integration test with `@EmbeddedKafka`

The example below targets **Spring Boot 3.x / Spring Kafka 3.x / JUnit 5**, using an embedded broker with a dedicated topic. In the test, we set `idleEventInterval=500ms`, `idleBeforeDataMultiplier=1.0`, and `pollTimeout=100ms` to shorten wait times. These short values are **for testing only** and should not be used by default in production.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(
        classes = ConsumerIdleEventIT.TestApplication.class,
        properties = {
                "spring.kafka.consumer.auto-offset-reset=earliest",
                "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
        })
@EmbeddedKafka(
        partitions = 1,
        topics = "orders-idle-it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class ConsumerIdleEventIT {

    @org.springframework.beans.factory.annotation.Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @org.springframework.beans.factory.annotation.Autowired
    IdleOrdersConsumer consumer;

    @org.springframework.beans.factory.annotation.Autowired
    IdleEventProbe events;

    @Test
    void emitsIdleAndNoLongerIdleAfterNewRecord() throws Exception {
        kafkaTemplate.send("orders-idle-it", "first").get(10, TimeUnit.SECONDS);

        // Verify the listener is actually consuming from the test broker.
        assertEquals("first", consumer.messages.poll(15, TimeUnit.SECONDS));

        // Clear any idle events emitted before the first record arrived.
        events.idle.clear();

        ListenerContainerIdleEvent idle =
                events.idle.poll(15, TimeUnit.SECONDS);

        assertNotNull(idle, "Consumer should become idle");
        assertTrue(idle.getListenerId().startsWith("ordersIdleListener"));
        assertTrue(idle.getIdleTime() >= 500L);

        // Only verify recovery events emitted AFTER idleness was confirmed.
        events.noLongerIdle.clear();
        kafkaTemplate.send("orders-idle-it", "second")
                .get(10, TimeUnit.SECONDS);

        assertEquals("second", consumer.messages.poll(15, TimeUnit.SECONDS));

        ListenerContainerNoLongerIdleEvent resumed =
                events.noLongerIdle.poll(15, TimeUnit.SECONDS);

        assertNotNull(resumed, "Consumer should leave idle state");
        assertTrue(resumed.getListenerId().startsWith("ordersIdleListener"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    @Import({IdleKafkaTestConfig.class, IdleOrdersConsumer.class, IdleEventProbe.class})
    static class TestApplication {
    }

    @TestConfiguration
    static class IdleKafkaTestConfig {

        @Bean("idleListenerFactory")
        ConcurrentKafkaListenerContainerFactory<String, String> idleListenerFactory(
                ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
                ConsumerFactory<String, String> consumerFactory) {

            var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
            configurer.configure(factory, consumerFactory);
            factory.getContainerProperties().setIdleEventInterval(500L);
            factory.getContainerProperties().setIdleBeforeDataMultiplier(1.0);
            factory.getContainerProperties().setPollTimeout(100L);
            return factory;
        }
    }

    static class IdleOrdersConsumer {

        final BlockingQueue<String> messages = new LinkedBlockingQueue<>();

        @KafkaListener(
                id = "ordersIdleListener",
                topics = "orders-idle-it",
                groupId = "orders-idle-it-group",
                containerFactory = "idleListenerFactory")
        public void consume(String payload) {
            messages.offer(payload);
        }
    }

    static class IdleEventProbe {

        final BlockingQueue<ListenerContainerIdleEvent> idle =
                new LinkedBlockingQueue<>();
        final BlockingQueue<ListenerContainerNoLongerIdleEvent> noLongerIdle =
                new LinkedBlockingQueue<>();

        @EventListener
        public void onIdle(ListenerContainerIdleEvent event) {
            if (event.getListenerId().startsWith("ordersIdleListener")) {
                idle.offer(event);
            }
        }

        @EventListener
        public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
            if (event.getListenerId().startsWith("ordersIdleListener")) {
                noLongerIdle.offer(event);
            }
        }
    }
}
```

Nested classes `IdleOrdersConsumer` and `IdleEventProbe` are registered in the Spring context via `@Import`, activating `@KafkaListener` and `@EventListener`. `ConcurrentKafkaListenerContainerFactoryConfigurer` pulls base configuration from Spring Boot and attaches `ConsumerFactory`; the test then overrides the three idle-related properties.

**Explanation of choices in the test:**

1. `@EmbeddedKafka` creates an in-test broker rather than connecting to production Kafka. `bootstrapServersProperty` injects the embedded broker address into `spring.kafka.bootstrap-servers`.
2. `KafkaTemplate.send(...).get(timeout)` confirms the producer sent the message to the broker, **not that the consumer processed it**.
3. `consumer.messages.poll(timeout)` waits for the listener to actually receive data. Do not use a fixed sleep to guess partition assignment.
4. After the first record, the test waits for `ListenerContainerIdleEvent` and asserts `listenerId`/`idleTime`.
5. After confirming idle, the test sends a second record and awaits `ListenerContainerNoLongerIdleEvent`.
6. Event handlers merely `offer` to queues, **never blocking the consumer thread**. The test method handles waiting via `poll(timeout)`.
7. Finite timeouts on assertions prevent hanging indefinitely if Kafka or the container fails to start.

This example uses an isolated integration-test context. When a project already has `@SpringBootApplication` and real listener beans, you can use `@SpringBootTest` with production configuration instead of defining `TestApplication`; avoid accidentally starting extra listeners reading the same test topic. In parallel test suites, give each test its own topic/group ID or isolate fixtures/offsets and `ApplicationContext`.

### 6.3. Preventing timing and coordination flakiness

A timer-based test cannot guarantee Kafka polling and thread scheduling hit an exact millisecond mark. Therefore:

- **Do not** assert that the idle event arrives at exactly 500 ms.
- **Do not** call `Thread.sleep(500)` and demand the event already fired.
- **Do not** reuse an unreset `CountDownLatch` from an earlier test.
- **Do** use `BlockingQueue.poll(15, TimeUnit.SECONDS)` or Awaitility to await conditions within bounded timeouts.
- **Do** filter by exact listener ID, especially when the Spring context holds multiple containers.
- **Do** confirm the consumer received a record when testing active → idle.
- **Do** account for `idleBeforeDataMultiplier` when testing startup idleness before the first record.
- **Do** give generous timeouts for embedded broker startup, partition assignment, and slow CI runners.

Checking "no idle event in the first 500 ms" is prone to noise because the container begins polling before the test starts counting. If exact timing bounds matter, test application logic via a clock/test seam or use conditions with clear tolerance instead of assuming test and consumer clocks start together.

## 7. Unit testing handlers without a Kafka broker

Integration tests verify that the framework emits events. Unit tests focus on code **handling** the events: filtering by listener ID, recording metrics, incrementing counters, and enqueuing alerts.

Example pure handler without `@EventListener` for direct unit testing:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.event.ListenerContainerIdleEvent;

public final class IdleEventCounter {

    private final AtomicInteger idleEvents = new AtomicInteger();

    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getListenerId().startsWith("ordersIdleListener")) {
            idleEvents.incrementAndGet();
        }
    }

    public int count() {
        return idleEvents.get();
    }
}
```

A unit test can construct `ListenerContainerIdleEvent` using its Spring Kafka 3.x constructor:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.event.ListenerContainerIdleEvent;

class IdleEventCounterTest {

    @Test
    void countsOnlyEventsForExpectedListener() {
        IdleEventCounter handler = new IdleEventCounter();

        ListenerContainerIdleEvent target = new ListenerContainerIdleEvent(
                this, this, 2_000L, "ordersIdleListener-0",
                List.of(), null, false);

        ListenerContainerIdleEvent other = new ListenerContainerIdleEvent(
                this, this, 2_000L, "billingListener-0",
                List.of(), null, false);

        handler.onIdle(target);
        handler.onIdle(other);

        assertEquals(1, handler.count());
    }
}
```

Exact event constructors may differ across versions, so check the Javadoc matching your project's dependency. This unit test **does not** start a consumer, verify `idleEventInterval`, or prove the framework emits events; it tests only filtering and counting logic.

When the handler sends alerts via a service, mock that service and assert `onIdle` calls it for the target listener and ignores other listeners. Keep handlers thin and move business/alert threshold decisions into a dedicated service for fast testing.

## 8. Testing consumer idleness from startup

Some systems must detect when a consumer receives zero records from startup, such as a topic expected to receive data every minute. In Spring Kafka 3.x, the default `idleBeforeDataMultiplier` of `5.0` lengthens the wait before the first event when no records have arrived yet.

To test startup idleness explicitly:

```java
factory.getContainerProperties().setIdleEventInterval(1_000L);
factory.getContainerProperties().setIdleBeforeDataMultiplier(1.0);
```

Then keep the test topic empty and await the event from the right listener with a generous timeout. **No message needs to be sent** in this test. However, ensure the fresh test group has no leftover backlog and the container actually started with partition assignments; reusing a topic/group with old offsets may cause the consumer to receive a record and break the "idle from startup" assumption.

Checklist for startup idle tests:

1. Use an empty topic and a group ID isolated from other tests.
2. Enable `idleEventInterval` and explicitly configure the pre-first-record multiplier.
3. Wait for the container to be running/assigned if asserting against a real assignment.
4. Await `ListenerContainerIdleEvent` via queue/latch/Awaitility, not fixed sleeps.
5. Verify listener ID; if partition assignment is required, inspect `getTopicPartitions()` after assignment completes.
6. Do not treat the first idle event as proof that the broker is healthy or lag is zero.

If you only want to test business policy on missing data, unit test the policy independently of a broker instead of relying on idle event timing in every test.

## 9. Testing repeated idle events and recovery

Idle events can fire repeatedly while no records arrive. This helps monitoring, though a handler without rate limiting can send alerts endlessly.

### 9.1. Verifying a second event while still idle

Integration test scenario:

```text
1. Container received a record and became idle.
2. Capture idleEvent #1.
3. Publish no further records.
4. Capture idleEvent #2 within a reasonable timeout.
5. Same listener/container; newer idleTime is typically not smaller than the old one.
```

When testing repeated events, use a `BlockingQueue` collecting events rather than a single-use latch. Do not assert that timestamps between two events differ by exactly 500 ms; poll latency and scheduling vary. With real consumers holding assigned partitions, events also depend on pause state and newly arriving records.

### 9.2. Testing `NoLongerIdleEvent`

`ListenerContainerNoLongerIdleEvent` only applies **after the container emitted an idle event** and subsequently receives a new record. If a record arrives too early, the container was never idle by the framework's definition, so no recovery event is expected.

Appropriate sequence:

```text
    record #1 consumed
            |
            v
   ListenerContainerIdleEvent
            |
            v
       record #2 consumed
            |
            v
 ListenerContainerNoLongerIdleEvent
```

When testing, clear stale events from the test probe after confirming idleness and before sending the recovery record. If multiple listeners share one probe, filter by listener ID instead of blindly taking the head of the queue.

## 10. Testing partition-level idleness while container still has traffic

With multi-partition topics, a consumer may receive data on partition 0 while partition 1 is empty. Container-level idle events may **not fire**, because the container is still receiving records; however, partition-level idle events can fire.

To enable:

```java
factory.getContainerProperties().setIdlePartitionEventInterval(2_000L);
```

Observe with:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;

@EventListener
public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
    if (event.getListenerId().startsWith("ordersIdleListener")) {
        log.info("kafka.partition.idle listenerId={} partition={} idleMs={}",
                event.getListenerId(),
                event.getTopicPartition(),
                event.getIdleTime());
    }
}
```

Test scenario with **2 partitions and one listener container with concurrency=1**:

1. Create a two-partition test topic and use an isolated consumer group.
2. Wait for both partitions to be assigned to the same listener if required by the test.
3. Continuously send messages to partition 0 for longer than `idlePartitionEventInterval`.
4. Send no messages to partition 1.
5. Await an event with `getTopicPartition().partition() == 1`; do not require a container-wide idle event.
6. Send a message to partition 1 and assert `ListenerContainerPartitionNoLongerIdleEvent` if testing recovery.

If concurrency exceeds partition count, or another consumer joins the group, assignments may split. Tests must verify assignments before asserting a partition belongs to the observed consumer. Avoid sharing test topics across parallel integration tests.

## 11. Why events might not appear despite no messages

A timed-out `assertNotNull(idleEvent)` does not automatically mean Spring Kafka is broken. Common causes:

| Symptom | Possible cause | How to diagnose |
|---|---|---|
| No idle events at all | `idleEventInterval` not configured, or listener uses a different factory. | Check `containerFactory` on `@KafkaListener` and runtime container properties. |
| No event within 1 second on initially empty topic | Default `idleBeforeDataMultiplier` is 5.0. | Set multiplier to 1.0 in tests, or raise timeout / consume a record first. |
| Event arrives late | `pollTimeout`, scheduling, broker startup, slow CI. | Use larger wait timeout, shorten poll timeout in tests. |
| Container not running | Listener `autoStartup=false`, config error, or container stopped. | Check registry/running state and startup logs. |
| No partitions assigned | Topic/group/rebalance not ready. | Wait for assignment; inspect group/partitions and topic creation. |
| Only `NonResponsiveConsumerEvent` appears | `poll()` is stuck and not returning. | Investigate poll, connectivity, Kafka client, and monitor settings. |
| No container idle, yet one partition is empty | Another partition still has messages. | Use `ListenerContainerPartitionIdleEvent`. |
| Event fired but test missed it | `@EventListener` bean unregistered, wrong listener ID filter, wrong ApplicationContext. | Verify Spring beans/imports and actual IDs. |
| Event belongs to another listener | Event listener receives events from multiple containers. | Filter by `getListenerId()` or source/container. |
| Event handler slows down consumer | Handler performs HTTP/blocking I/O on consumer thread. | Offload heavy work to an executor; keep callbacks fast. |
| Consumer paused | Container/partition explicitly paused; event does not reveal backlog. | Inspect `isPaused`, pause/resume, and consumer lag. |
| Data sent to Kafka but consumer misses it | Group offset, serializer/deserializer, rebalance, or missing assignment. | Check producer send future, test topic/group, error logs. |

An easily missed detail: child containers' `getListenerId()` can carry a **concurrency suffix**, such as `ordersIdleListener-0`. Using `equals("ordersIdleListener")` in the handler can drop all events. To match the whole child group, use `startsWith` with a prefix designed not to collide with other listeners; if multiple IDs share a prefix, filter by parent container or clear naming conventions.

## 12. `NonResponsiveConsumerEvent` is a different problem

`ListenerContainerIdleEvent` can only fire when the consumer poll loop gets to observe that no records arrived. If `KafkaConsumer.poll()` never returns (due to networking/client or blocking issues), missing idle events **do not prove the consumer is healthy**.

Spring Kafka also provides `NonResponsiveConsumerEvent` to report a consumer appearing stuck inside `poll()`. Related settings:

```java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setMonitorInterval(5);
factory.getContainerProperties().setNoPollThreshold(3.0f);
```

`monitorInterval` is in seconds; `noPollThreshold` should exceed 1 to avoid false positives from timing races. Check Javadoc for setter parameter types across API versions. The snippet illustrates that poll timeout and monitor thresholds are **distinct** from the idle interval.

In production, never conclude a poll is stuck just because a topic has no messages. Conversely, never treat `ListenerContainerIdleEvent` alone as sufficient reason to restart a consumer. Evaluate container health, consumer lag, broker connectivity, heartbeats, pause/rebalance state, and upstream status.

### 12.1. Should tests try to hang `poll()` deliberately?

Idle tests should use an empty topic without simulating network failures or trying to block the Kafka client. Testing `NonResponsiveConsumerEvent` is a separate test, usually requiring controlled Kafka client/poll mocks and monitor cadence tuning. Do not randomly break the embedded broker and expect an idle event, because the primary condition triggered may be **non-responsive** rather than idle.

## 13. Writing alerting policies from idle events

When production needs alerts, translate events into metrics or signals evaluated over a time window. For example:

```text
Idle event -> record lastIdleAt, listenerId, idleMs
           -> cardinality-bounded metric/counter
           -> policy:
                - is the topic expecting traffic?
                - what are lag and broker health?
                - is there an active pause/maintenance/rebalance?
                - how long has idleness lasted across cycles?
           -> alert when all conditions hold
```

**Never send one alert per idle event.** Containers can emit repeatedly every `idleEventInterval`; across hundreds of consumers, an unthrottled alert handler causes an alert storm even when an empty topic is normal.

A policy might alert after 5 minutes of continuous idleness **while** the producer is expected to emit records. When `NoLongerIdle` fires, reset state / resolve the alert. Keep metrics free of high-cardinality tags like message keys, event payloads, or unnecessary partition IDs; group by service, listener, and topic where values are bounded and appropriate.

### 13.1. Idle does not prove lag is 0

A consumer may receive no records because it is paused, lacks assignment, fails deserialization, or has unstable metadata/group state, while the broker still holds a backlog. **Consumer lag** must be computed from broker/end offsets vs. committed offsets/consumption progress depending on your monitoring tool. `getIdleTime()` is not a lag measurement and reveals nothing about the last successful commit.

### 13.2. Do not manipulate offsets arbitrarily inside idle handlers

`ListenerContainerIdleEvent.getConsumer()` may expose a Kafka consumer reference. By default event handlers run on the consumer thread, but if Spring's application event multicaster is configured to run asynchronously, the handler may run on a different thread. **`KafkaConsumer` is not thread-safe**; never call `seek`, `pause`, `resume`, `commit`, or consumer methods from a non-owning thread without framework-supported mechanisms.

If you need consumer-position actions when idle, Spring Kafka provides `ConsumerSeekAware.onIdleContainer(...)` for safe interaction with supported callbacks/seek strategies. This is a specialized option and unnecessary for tests merely observing events.

## 14. Testing in CI: Embedded Kafka vs. Testcontainers?

| Option | Best suited when | Pros | Things to watch |
|---|---|---|---|
| `@EmbeddedKafka` | Fast integration tests for listeners/events in the same test JVM. | Needs no external Kafka broker in typical cases. | Must manage topics/groups, broker startup, ports, contexts, and test isolation. |
| Kafka Testcontainers | Testing broker/containers closer to real deployment environments. | Tests networking/container behavior and exact broker images. | Requires Docker/container runtime; slower startup. |
| `MockConsumer` / mock events | Unit testing event handlers or policy logic. | Fast, deterministic, no broker needed. | Does not prove the listener container emits real idle events. |
| Kafka staging/test cluster | End-to-end with security, ACLs, real partitions/rebalances. | Close to operations. | Harder to isolate data/load; do not use per unit test. |

Testcontainers tests may use `KafkaContainer` or `ConfluentKafkaContainer` depending on the chosen Testcontainers/Kafka release. Pass bootstrap servers via `@DynamicPropertySource` or `@ServiceConnection` (when supported by Spring Boot); event capture and assertions stay the same.

Do not force every unit test to rely on a real broker if the logic under test is filtering listener IDs, counting idle events, or rate limiting. Those belong in unit tests; keep a representative set of integration tests to prove wiring and framework behavior.

### 14.1. Isolating consumer groups and test topics

Tests can interfere with each other when sharing topics/groups:

- An earlier test leaves committed offsets so the next test misses expected records.
- Two parallel tests in the same group split partitions, each receiving a subset of records.
- Stale events in a `BlockingQueue` make a later test pass falsely.
- Spring Test context caching keeps containers and observer beans alive from another class.

A straightforward approach is a dedicated test topic per class, dedicated group IDs, and resetting queues/latches before each case. When integration tests span multiple classes in one JVM, `@DirtiesContext` can stop contexts/containers after tests; use it judiciously since it lengthens suite runtime. With a suite-wide shared embedded broker, manage lifecycles and resource isolation explicitly.

## 15. A sleep-free testing strategy

An asynchronous event test must **synchronize on events**, not timing luck:

```text
Producer send future -> get(timeout)        [broker received record]
Consumer queue.poll(timeout)                [listener received record]
Idle probe queue.poll(timeout)              [Spring emitted idle event]
Producer send future -> get(timeout)        [broker received recovery record]
Consumer queue.poll(timeout)                [listener received recovery record]
Resume probe queue.poll(timeout)            [Spring emitted no-longer-idle]
```

Two common misconceptions:

1. **Producer ACK does not mean the consumer consumed.** `KafkaTemplate.send(...).get(...)` only confirms the producer operation per Kafka producer ACK policy. You need a separate listener assertion.
2. **Seeing no records is not the only condition for events.** If the container has not started, `poll()` never returns, or the container stopped, sleeping will not produce an idle event.

With Awaitility, tests can wait on conditions instead of a `BlockingQueue`; however, ensure state checks are thread-safe. Use `AtomicInteger`, `ConcurrentLinkedQueue`, or synchronized state; never read an unsynchronized `ArrayList` mutated by the consumer thread.

### 15.1. What timeouts are appropriate?

The test's idle threshold can be 500 ms, while the event wait timeout should be much wider, such as 10–20 seconds depending on CI. Do not shrink wait timeouts to 600 ms just for "fast" tests: scheduling/rebalances will cause flakiness. On timeout, error messages should state which event type was awaited, which listener ID, and container state if available.

### 15.2. Avoid asserting exact `System.currentTimeMillis()` deltas

Kafka listeners use their own poll loop/timer logic, while the JUnit thread follows separate scheduling. Instead of `assertEquals(500, idle.getIdleTime())`, use a relative check (`idleTime >= threshold` with sensible tolerance) and an upper-bound overall wait timeout. To test rate-limiting algorithms precisely, extract the algorithm into a service with an injectable `Clock` for deterministic unit testing.

## 16. Essential test matrix for consumer idle events

| Test case | Setup | Expectation |
|---|---|---|
| Record then empty | Send record, confirm consumed, stop publishing | `ListenerContainerIdleEvent` fires with matching ID. |
| Idle then active again | After idle, send a new record | `ListenerContainerNoLongerIdleEvent` fires. |
| Empty topic from startup | Send no records, test multiplier = 1.0 | Idle event fires within timeout. |
| Idle interval disabled | Omit `idleEventInterval` | Feature not **configured**; avoid negative tests with overly short timing. |
| Two listeners in one context | One idle listener, one active listener | Handler/test counts events only for the matching listener ID. |
| Multiple partitions | Traffic on one partition, other partition empty | Partition idle event fires when partition interval is enabled. |
| Listener paused | Explicitly pause via proper API | Verify paused state/event; do not infer healthy from idle. |
| Unresponsive poll | Separate test controlling/mocking blocked poll | Observe `NonResponsiveConsumerEvent`, do not force idle event. |
| Repeated idle | Send no records over multiple intervals | Receives multiple events; handler avoids alert storms. |
| Concurrency > 1 | Multiple child containers | Listener IDs carry suffixes; filter matches group/children accurately. |
| Consumer stopped | Stop container cleanly | Do not expect idle events to continue as when running. |

Not every case needs to be a heavy integration test. Keep a few integration tests proving event lifecycles, while filtering, alert rate limits, counters, and policies live in unit tests.

## 17. Common failures and troubleshooting

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Test waits 1 second and gets no idle event | Default pre-data multiplier is 5; startup poll incomplete. | Set `setIdleBeforeDataMultiplier(1.0)` in tests, or consume a record before waiting. |
| `@EventListener` never called | Handler is not in the Spring context. | Register via `@Component`, `@Bean`, or `@Import`; verify right context. |
| All events filtered out | Listener ID has `-0`, `-1` suffix. | Use scoped `startsWith`, or inspect source/container. |
| Events arrive from another consumer | Same application context has multiple listeners. | Filter by listener ID; isolate test fixtures. |
| Test passes even though listener receives no messages | Asserted only idle event without testing consumer callback. | Send initial record and await queue/latch confirming listener works. |
| `NoLongerIdleEvent` never fires | No idle event had occurred before sending the record. | Wait for a real idle event before sending recovery data. |
| No idle event while client is stuck | `poll()` is not returning to detect idleness. | Monitor `NonResponsiveConsumerEvent`, poll/network/client. |
| Container already stopped | `autoStartup=false` or stop called before test. | Check registry, running state, and startup errors. |
| Topic empty yet consumer group has backlog | Wrong assignment/paused/deserialization failure/lag. | Check lag, assignments, pauses, logs, and broker metrics. |
| Flaky test on CI | Timeout too close to idle interval, tests fighting over topic/group. | Use generous queue poll timeouts, isolate topics/groups, avoid fixed sleeps. |
| Event handler slows down consumption | Calling network APIs on consumer thread. | Offload to executor/queue, passing only safe metadata. |
| Alert spam | Idle events repeat every interval. | Rate limit and track alert state, clearing on NoLongerIdle. |
| Partition idle mistaken for container idle | Another partition still has traffic. | Use partition-level listener and check exact scope. |
| Consumer API throws thread-safety errors | Calling `getConsumer()` from async event listener. | Never use Consumer off its owning thread; use proper callback/registry APIs. |

## 18. Project adoption workflow

1. **Define business expectations:** does the topic receive continuous or scheduled traffic? How long of a data gap is normal?
2. **Choose monitoring scope:** container-wide idle or per-partition? Does consumer lag also need tracking?
3. **Enable suitable intervals:** `idleEventInterval` and, if needed, `idlePartitionEventInterval`; account for the pre-first-record multiplier.
4. **Assign clear listener IDs:** simplifies filtering events, logs, and metrics.
5. **Write lightweight handlers:** never block the consumer thread; record minimal metadata and delegate alerting to a dedicated service.
6. **Build integration tests:** create test broker/topic/group, consume one record, await idle event, send next record, and assert recovery event.
7. **Use finite timeouts:** avoid fixed `Thread.sleep`; isolate probes across tests.
8. **Add unit tests:** listener ID filtering, deduplication/rate limiting, and business policy.
9. **Exercise extra failure modes:** pause, rebalance, empty partitions, non-responsive polls, and stopped containers.
10. **Correlate with production telemetry:** lag, consumer health, producer throughput, and maintenance windows before firing critical alerts.

### Exercise 1 — Testing a consumer becoming idle

Create listener `paymentsConsumer` reading topic `payments-test` with `idleEventInterval=1s`. Use `@EmbeddedKafka` to send one record, confirm the listener received it, then await `ListenerContainerIdleEvent` within 15 seconds. Assert `getListenerId()` and `getIdleTime()` without `Thread.sleep(1000)`.

### Exercise 2 — Testing idle → active

After receiving an idle event, send a new record and await `ListenerContainerNoLongerIdleEvent`. Explain why sending the record before the idle event fires does not guarantee a no-longer-idle event.

### Exercise 3 — Testing the pre-first-record multiplier

Leave the topic empty from startup. Compare tests with `idleEventInterval=1000L, idleBeforeDataMultiplier=5.0` vs. `idleBeforeDataMultiplier=1.0`. Do not assert exact timestamps; observe differences in expected timing and timeout configuration.

### Exercise 4 — Multiple listeners and partitions

Create two listeners with distinct IDs and a topic with two partitions. Send data to one partition and leave the other empty. Write a probe that avoids confusing idle events from the other listener and finds the right `ListenerContainerPartitionIdleEvent` by partition ID. Test behavior when concurrency changes.

### Exercise 5 — Preventing alert spam

A consumer idle for 10 minutes can emit dozens of events. Write an `IdleAlertPolicy` that tracks state and sends only one initial alert, escalates by threshold if needed, and clears when `ListenerContainerNoLongerIdleEvent` arrives. Unit test the policy with a controllable clock without a Kafka broker.

### Exercise 6 — Distinguishing idle from a broken consumer

Design a signal table covering idle events, lag, partition assignment, paused state, nonresponsive events, upstream producer rate, and broker connectivity. Define decisions for three cases: legitimately empty topic, topic with backlog while consumer is paused, and unresponsive consumer poll.

## 19. Key principles to remember

- `ListenerContainerIdleEvent` signals **no records received for a duration**, not by itself that the consumer or broker is failing.
- `idleEventInterval` must be enabled; the `null` default emits no events. `idleBeforeDataMultiplier` defaults to **5.0** before the first record in Spring Kafka 3.x.
- Events can **emit repeatedly** while still idle; use rate limiting in observability/alerting.
- `ListenerContainerNoLongerIdleEvent` indicates the consumer received a record after an idle state was recorded by the framework.
- Best tests combine **a test Kafka broker + `@EventListener` + queue/latch/Awaitility**, with generous timeouts and no fixed `sleep`.
- Always verify the listener actually consumed, not just that the producer send succeeded.
- With concurrency, listener IDs can carry child suffixes; event handlers must filter to the right scope.
- `ListenerContainerPartitionIdleEvent` and `NonResponsiveConsumerEvent` answer **different questions**; never infer lag, health, or poll responsiveness from a single idle event.
- Default event handlers can run on the consumer thread; **do not block** or manipulate the Kafka `Consumer` from a non-owning thread.
- In production, combine idleness, lag, assignments, producer rate, and business expectations before alerting or restarting containers.

## 20. Official references

- [Spring for Apache Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): `ListenerContainerIdleEvent`, `ListenerContainerNoLongerIdleEvent`, partition idle events, nonresponsive consumer, and event handling.
- [Spring for Apache Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html): `idleEventInterval`, `idleBeforeDataMultiplier`, `idlePartitionEventInterval`, `pollTimeout`, and monitor settings.
- [Spring Kafka 3.3 API — `ListenerContainerIdleEvent`](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerIdleEvent.html): idle event constructors and getters.
- [Spring Kafka 3.3 API — `ListenerContainerNoLongerIdleEvent`](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerNoLongerIdleEvent.html): event emitted when a listener receives data again.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Kafka configuration in Boot and testing with `@EmbeddedKafka`.
- [Spring Boot 3.5 — Common Kafka Listener Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.kafka.listener.idle-event-interval` and other Kafka properties.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): embedded brokers, `@EmbeddedKafka`, Kafka test utilities, and structuring tests.

