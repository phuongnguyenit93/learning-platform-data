# Testing Pause and Resume in Spring Kafka

When a downstream system is slow, a database is overloaded, or a dependency is under maintenance, a Kafka-consuming application may need to **temporarily stop receiving new records** without leaving the consumer group. In Spring Kafka, `pause()` and `resume()` on the **listener container** are useful tools for controlling processing flow. However, calling `pause()` does not mean the consumer stops instantaneously, and `resume()` does not guarantee the entire backlog has already been processed successfully.

The **Testing Pause and Resume** topic belongs to **Spring Kafka Reliability Operations → Reliability Testing**. The goal is to design tests that prove three things: **the consumer actually paused**, **messages sent while paused are not processed prematurely**, and **after resuming, the backlog is processed according to the offset/acknowledgment contract**.

```text
                      Kafka topic
                  partition 0: A B C D E
                               |
                               v
                    Spring Kafka container
                     (poll keeps running)
                               |
              +----------------+----------------+
              |                                 |
          RUNNING                            PAUSED
      delivers records                   stops forwarding new
        to listener                      records to listener
              |                                 |
              +----------- resume() ------------+
                               |
                               v
                        process backlog
                               |
                         commit offset
                     per configured AckMode
```

**Distinction:** pausing does not delete messages from Kafka, does not automatically commit offsets, and does not replace retries/DLTs. It only suspends delivering further records to the listener within the pause scope. Handling already-polled records, redelivery after crashes, and offset commits must still be tested separately.

## 1. Testing goals and success criteria

A meaningful test suite must observe the **actual state** of the listener container and **record processing outcomes**, not just verify that the `pause()` method was invoked.

| Situation | What to prove |
| --- | --- |
| Listener running | Consumer has been assigned partitions and processes a probe message |
| Calling `pause()` | Container records the pause request and actually enters the paused state |
| Producer sends after pause takes effect | Producer receives ack, while the listener does not process the message during the observation window |
| Calling `resume()` | Container leaves the paused state and processes the waiting message |
| Pausing while listener is processing a record | In-flight record can finish; do not expect pause to abort an active thread |
| Long pause | Container keeps polling to maintain membership, depending on broker/network health and processing duration |
| Restart/rebalance | Pause state and record redelivery are evaluated against the real lifecycle, not assumptions |
| Offsets/side effects | Zero data loss; duplicate prevention depends on acks and idempotency |

Example of a desired test outcome:

```text
T0    Listener received partition 0
T1    container.pause()
T2    isContainerPaused() == true
T3    Producer sends order-001, Kafka ack succeeds
T4    No processing callback for order-001 during observation window
T5    container.resume()
T6    isContainerPaused() == false
T7    Listener receives order-001 and writes result
```

**T2 is mandatory before T3.** If sent at T1, the record may already be fetched or dispatched to the listener before the pause command takes effect. Such a test easily becomes flaky even when the library works properly.

## 2. How container `pause()` differs from `KafkaConsumer.pause()`

Apache Kafka provides `KafkaConsumer.pause(Collection<TopicPartition>)` and `resume(...)`. Spring Kafka wraps the consumer with listener containers such as `KafkaMessageListenerContainer` and `ConcurrentMessageListenerContainer`.

In applications using `@KafkaListener`, prefer the **container API**:

```java
MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

container.pause();   // Request the container to pause receiving new records.
container.resume();  // Request the container to resume.
```

Reasons:

- `KafkaConsumer` is **not thread-safe**; calling consumer methods directly from an HTTP controller or another thread can violate the Kafka client contract.
- The container manages the consumer thread, poll loop, partition assignments, acknowledgments, error handler, and lifecycle.
- Container `pause()` is a **request applied at a safe point in the consumer loop**, not necessarily an immediately effective state upon return.
- With concurrent containers (*concurrency > 1*), pausing the parent container coordinates child consumers; therefore observe the paused state instead of assuming all threads stopped simultaneously.

Key APIs (Spring Kafka 3.x):

| API | Role |
| --- | --- |
| `pause()` | Requests pausing the listener container's partitions |
| `resume()` | Requests resuming record delivery |
| `isPauseRequested()` | Indicates whether a pause has been requested |
| `isContainerPaused()` | Indicates whether the container is actually in the paused state across its scope |
| `pausePartition(TopicPartition)` | Requests pausing a specific partition if supported by API/version |
| `resumePartition(TopicPartition)` | Allows resuming a specific partition |
| `isPartitionPaused(TopicPartition)` | Observes the actual pause state of a partition |

`pause()` is **not equivalent** to `stop()`. Under listener container pausing, the consumer continues polling appropriately to maintain membership/heartbeats; whereas `stop()` shuts down the container and typically triggers leaving the group or reassigning partitions. Use stop to halt a workload completely; use pause to temporarily suspend delivery while keeping the consumer lifecycle alive.

### 2.1. Pause is local consumer state

If two consumer groups read the same topic, pausing group A **does not pause the topic on the broker** and does not stop group B from reading. If three application instances share the same group, pausing one instance's container does not pause the remaining instances.

```text
                      orders-topic
                       /        \
                      v          v
                 Group billing   Group reporting
                      |              |
                instance A        instance X
                PAUSED            RUNNING
                      |
                instance B
                RUNNING
```

To halt processing across the **entire group**, coordinate state across every instance or design a centralized control plane. A single REST call hitting one random Pod is not enough to pause the whole group.

## 3. What happens in the poll loop during a pause?

A normal consumer continuously calls `poll()` to fetch records and maintain group membership. When a Spring Kafka container is asked to pause, it pauses assigned partitions at an appropriate point and then continues polling to satisfy the consumer group protocol.

```text
Consumer thread:

poll()  -> records [A, B, C]
   |
   +--> listener processes A
   +--> control thread calls container.pause()
   +--> listener may still process already-polled B and C
   +--> finishes current batch
   +--> applies consumer.pause(assigned partitions)
   +--> poll() while paused: fetches no new records from paused partitions
   |
   +--> control thread calls container.resume()
   +--> resumes polling/delivery
```

**Do not expect pause to interrupt an already-running listener callback.** When a poll returns multiple records, the container may continue delivering the remaining records before the paused state takes effect, depending on version/configuration. Spring Kafka provides a `pauseImmediate` option on certain container types: when enabled, pausing can occur right after the current record instead of draining the whole poll, leaving undelivered records to be processed after resume. This still does not abort an in-progress transaction or callback.

If the listener blocks longer than `max.poll.interval.ms`, the consumer can still be deemed unresponsive to polling and trigger a rebalance. **Pausing cannot rescue a listener stuck inside a callback**, because the container must return to the poll loop to maintain heartbeats/liveness.

### 3.1. Pause does not change offsets

Suppose a partition has offsets `0` through `9`. The consumer committed next offset `4` (meaning it processed through offset `3` per the application's ack contract). Pausing does not advance commits to `10` and does not delete records `4..9`.

```text
Kafka log:
offset        0 1 2 3 | 4 5 6 7 8 9
                      ^
                committed next offset = 4

Consumer PAUSED:
  records 4..9 remain in Kafka, or some were already fetched before pause

Consumer RESUMED:
  delivery continues per consumer position/buffer and commit policy
```

A Kafka consumer has a **current position**, a **committed offset**, and possibly **pre-fetched records**. These three concepts need not match. After a crash/rebalance, replay normally relies on committed offsets, not on a log stating `pause()` was called.

If a pause outlasts the topic's retention period, older data may disappear from Kafka before resume; that is a **retention** risk, not pause deleting records. Monitor backlogs and enforce pause duration limits.

## 4. Controlling a listener container by `id`

Example listener:

```java
package com.example.kafka;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
    )
    public void onMessage(String payload) {
        // Validate, run business logic, persist idempotent state.
        System.out.println("Received: " + payload);
    }
}
```

`id="ordersListener"` is the **container ID** used by `KafkaListenerEndpointRegistry` to look up the right listener. Do not confuse container ID with topic or `groupId`. In systems with multiple `@KafkaListener`s, controllers must know which listeners may be paused and never accept untrusted IDs to control arbitrary listeners.

A control service:

```java
package com.example.kafka;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerFlowControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerFlowControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer requireOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
        if (container == null) {
            throw new IllegalStateException("ordersListener is not registered");
        }
        return container;
    }

    public void requestPause() {
        requireOrdersListener().pause();
    }

    public void requestResume() {
        requireOrdersListener().resume();
    }

    public boolean pauseRequested() {
        return requireOrdersListener().isPauseRequested();
    }

    public boolean actuallyPaused() {
        return requireOrdersListener().isContainerPaused();
    }
}
```

`requestPause()` returning quickly does not mean all partitions are paused yet. Operations should therefore distinguish:

```text
pauseRequested = true
isContainerPaused = false
  → command received, but consumer may still be finishing current poll

pauseRequested = true
isContainerPaused = true
  → container has confirmed paused state
```

Similarly, after `resume()`, wait for the paused state to clear before claiming the consumer has resumed. Even once resumed, having no new messages does not imply an error.

## 5. A repeatable test plan avoiding timing flakiness

The test sequence should rely on **barriers and real state**:

```text
1. Create a dedicated topic, consumer group, and one listener.
2. Wait for the container to be assigned partitions.
3. Call pause().
4. Wait for isContainerPaused() == true.
5. Send message X, await successful producer Future completion.
6. Confirm X is not recorded by the listener during the observation window.
7. Call resume().
8. Wait for isContainerPaused() == false.
9. Confirm the listener receives X with the expected output.
```

Start with **one partition and one consumer thread** to eliminate noise from multiple partitions or rebalances. Expand to concurrency > 1 only after the baseline is stable.

**What not to do:**

```java
container.pause();
kafkaTemplate.send(topic, value);
Thread.sleep(100);
assertThat(received).isEmpty();
```

The flaw here is neither waiting for the pause to take effect nor waiting for the producer send to succeed. `Thread.sleep(100)` also depends on CPU speed, broker speed, CI runners, and scheduling, yielding nondeterministic results.

### 5.1. Reliable observation sources

| Source | Used to verify | Limitations |
| --- | --- | --- |
| `isContainerPaused()` | Container has applied the paused state | Does not describe every in-flight event prior to pause |
| `ConsumerPausedEvent` | Receive paused state notifications from the container | Must filter for the right container/partition and await the event |
| `BlockingQueue`/latch in test listener | Whether callback processed a record | Does not by itself prove DB transactions/offsets committed |
| Producer `Future.get()` | Broker received/acked per producer config | Does not prove the listener processed it |
| DB output/idempotency key | Whether business side effects were persisted | Requires explicit transactions and fixtures |
| Consumer group offsets/lag | Backlog and commit progress | Lag need not drop to 0 instantaneously upon resume |

For the negative assertion "no callback while paused," always confirm **pause is active before sending the message**. Then check using a finite observation window long enough to catch stray callbacks without dragging out the suite.

## 6. Test project with Spring Boot 3.x and Spring Kafka 3.x

The example below uses **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, JUnit Jupiter**, `@EmbeddedKafka`, and Awaitility. This is a test-environment scenario; in production, connect to a real Kafka cluster via infrastructure config.

### 6.1. Gradle dependencies

For a Spring Boot project managing versions via BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

Spring Kafka and test modules should use **compatible versions managed by the Spring Boot BOM**. Do not arbitrarily mix Spring Kafka 2.x, 3.x, and Boot 4.x because APIs, packages, container properties, and embedded broker behaviors can differ.

### 6.2. `@EmbeddedKafka` integration test

Example test creating a listener in test configuration, sending a record **after the container is genuinely paused**, and verifying resume delivers it:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
    classes = PauseResumeIntegrationTest.TestApplication.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.missing-topics-fatal=true"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = "orders.pause.test",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PauseResumeIntegrationTest {

    static final String TOPIC = "orders.pause.test";

    @Autowired KafkaListenerEndpointRegistry registry;
    @Autowired KafkaTemplate<String, String> kafkaTemplate;
    @Autowired ReceivedProbe probe;

    @Test
    void pausingStopsDeliveryAndResumingProcessesBacklog()
            throws Exception {

        MessageListenerContainer container =
            Objects.requireNonNull(
                registry.getListenerContainer("ordersListener"));

        // Do not call pause before the consumer is assigned partitions.
        ContainerTestUtils.waitForAssignment(container, 1);

        container.pause();
        await().atMost(Duration.ofSeconds(10))
            .until(container::isContainerPaused);

        assertThat(container.isPauseRequested()).isTrue();

        String payload = "order-pause-001";
        kafkaTemplate.send(TOPIC, payload)
            .get(10, TimeUnit.SECONDS); // Producer acked by Kafka.

        // Record sent AFTER pause must not reach the listener yet.
        assertThat(probe.received.poll(700, TimeUnit.MILLISECONDS))
            .isNull();

        container.resume();
        await().atMost(Duration.ofSeconds(10))
            .until(() -> !container.isContainerPaused());

        // Message remained in Kafka and is processed after resume.
        assertThat(probe.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(payload);
        assertThat(probe.received.poll(300, TimeUnit.MILLISECONDS))
            .isNull();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean
        ReceivedProbe receivedProbe() {
            return new ReceivedProbe();
        }
    }

    static class ReceivedProbe {
        final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "ordersListener",
            topics = TOPIC,
            groupId = "pause-resume-integration-test"
        )
        void onMessage(String payload) {
            received.add(payload);
        }
    }
}
```

The test uses a minimal nested application configuration to focus on pause/resume behavior without needing an HTTP controller. Key points:

1. `@EmbeddedKafka` starts a test-scoped broker and wires its address into `spring.kafka.bootstrap-servers`.
2. `@EnableKafka` enables listener registration; Spring Boot builds `KafkaTemplate` and the listener container factory from the provided dependencies/config.
3. `ContainerTestUtils.waitForAssignment(...)` waits for partition assignment instead of guessing container startup timing.
4. `container.pause()` is the request; `await(...).until(container::isContainerPaused)` is the barrier confirming pause took effect.
5. `KafkaTemplate.send(...).get(...)` awaits producer completion so the test never confuses "message not sent yet" with "listener is paused."
6. `BlockingQueue` records **real callbacks**, rather than merely mocking `MessageListenerContainer.pause()`.
7. `@DirtiesContext` closes the context/broker and prevents leftover listener state from leaking into other suites.

In a large test suite, give each test its own **dedicated topic/group ID or explicit cleanup and isolation** so messages/committed offsets from prior tests do not interfere. With a shared broker, reusing a fixed group ID and existing topic can cause the listener to receive records from outside the current fixture.

**Test limitations:** this test proves pause/resume delivery within a single stable run. It **does not prove exactly-once across crashes**, does not prove pause state survives restarts, and does not replace tests against a real Kafka broker/consumer rebalance.

## 7. Testing *in-flight* records during a pause

An easy-to-write wrong negative test demands **zero callbacks immediately after calling `pause()`**. Valid behavior can be that an active callback or records from the previous poll finish processing.

Simulate a listener with two latches:

```java
final CountDownLatch entered = new CountDownLatch(1);
final CountDownLatch release = new CountDownLatch(1);

@KafkaListener(id = "slowListener", topics = "slow.orders")
public void onMessage(String payload) throws InterruptedException {
    entered.countDown();
    if (!release.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Timed out in test listener");
    }
    processed.add(payload);
}
```

This is an **illustrative fixture**, not a complete test class; `processed` is a thread-safe queue or list provided by the test. Testing steps:

1. Send `A`; await `entered.await(...)` to confirm the listener is currently processing `A`.
2. Call `container.pause()` from the test thread.
3. Check that `isPauseRequested()` may already be `true`, **but do not expect `isContainerPaused()==true` yet** while callback `A` is still blocked.
4. Release the `release` latch so callback `A` finishes.
5. Wait for `isContainerPaused()==true`; only then send `B`.
6. Confirm `B` is not processed during the paused interval; call `resume()` and confirm `B` is processed.

If `pauseImmediate` is enabled (on supported versions/configs), also test how the container retains remaining records from the poll. If not enabled, do not assume a poll that fetched 100 records processes strictly one record after a pause request.

### 7.1. `max.poll.records` is not a guaranteed processing count

`max.poll.records` caps how many records a single `poll()` returns at the Kafka client level; it **does not bound backlog size** or create an automatic business transaction. When testing pause with multiple already-polled records, changing `max.poll.records` can affect how many records continue processing before pause takes effect. Use a small value when you want easy observability, while still basing tests on actual container state and callbacks.

## 8. Using `ConsumerPausedEvent` and `ConsumerResumedEvent`

Spring Kafka emits **application events** for listener container state, including `ConsumerPausedEvent` and `ConsumerResumedEvent`. They are useful for logging, metrics, and tests awaiting state transitions without parsing log text.

Illustrative observer example (Spring Kafka 3.x):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPauseEventLogger {
    private static final Logger log =
        LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("event=kafka.consumer.paused source={} partitions={}",
            event.getSource(), event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("event=kafka.consumer.resumed source={} partitions={}",
            event.getSource(), event.getPartitions());
    }
}
```

The event carries container/consumer details and the affected partitions. With multiple listeners or multiple test contexts, **filter by the exact container ID/topic-partition** before treating an event as evidence for the listener under test. Also avoid writing consumer control logic that calls `KafkaConsumer` directly from an event listener running on the wrong thread.

To test pause/resume without coupling to event-dispatcher details, prefer `isContainerPaused()` as the primary condition and use events as supplementary evidence. When the application handles events asynchronously, awaiting events also requires latches/queues and explicit timeouts.

## 9. Testing per-partition pause/resume

You do not always need to pause the entire listener. For example, a topic has two partitions: partition 0 hits input data requiring investigation, while partition 1 can continue processing normally.

```text
                  orders-topic
                  /          \
                 v            v
            partition 0   partition 1
              PAUSED        RUNNING
                 |            |
              backlog      continues
               grows       processing
```

With Spring Kafka versions supporting partition-level pause:

```java
TopicPartition partition0 =
    new TopicPartition("orders-topic", 0);

MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

container.pausePartition(partition0);

await().atMost(Duration.ofSeconds(10))
    .until(() -> container.isPartitionPaused(partition0));

// Send records to partitions 0 and 1 to test:
// template.send("orders-topic", 0, "k0", "A").get(...);
// template.send("orders-topic", 1, "k1", "B").get(...);
// B can be processed; A must wait until partition 0 resumes.

container.resumePartition(partition0);
await().atMost(Duration.ofSeconds(10))
    .until(() -> !container.isPartitionPaused(partition0));
```

This is a **test skeleton**, assuming the topic has at least two partitions, partition 0 is assigned to the controlled consumer/container, and a consumer group and producer are configured. A complete test must create a two-partition topic, await assignment, send with an **explicit partition**, and observe queues per partition (not just by payload).

With `concurrency > 1`, partitions may be assigned to different child consumers; tests must verify assignments and container scope. `isContainerPaused()` is a **container-wide** pause signal and cannot replace `isPartitionPaused(partition0)` when only a single partition is paused.

### 9.1. Rebalance and partition reassignment

When a consumer group rebalances, partitions can be revoked and reassigned to another consumer. A partition pause request on the old container does not automatically block processing across **every instance**. If the system must preserve "this partition must stay paused" across rebalances, design a **desired state** store and reapply it on partition assignment, and test consistency after a rebalance.

Extended reliability tests should deliberately add/remove consumers or restart an instance, then verify reassigned partitions and the desired pause state. Never assume a successful pause on one consumer acts as a broker-side topic lock.

## 10. Offsets, acknowledgments, and errors after resume

Pause/resume **does not alter the configured ack policy**. Whether using `AckMode.RECORD`, `AckMode.BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE`, commit timing and crash-replay behavior differ.

| Situation | What to understand |
| --- | --- |
| Pause before messages are fetched | Messages remain in Kafka; consumer fetches them once resumed and permitted to read |
| Pause after messages were polled | Container may finish processing fetched records per config before truly pausing |
| Listener succeeds but process dies before offset commit | Records can be redelivered after restart/rebalance |
| Listener fails during resume | Error handler, retry/backoff, DLT, and ack policy decide the outcome; pause does not fix bugs |
| Offset commits before durable business side effect | Risk of losing business effects while records are no longer redelivered as expected |
| Long pause exceeding retention | Backlog can be deleted by Kafka retention; requires monitoring and recovery |

A listener using manual acknowledgment (illustrative snippet):

```java
@KafkaListener(
    id = "paymentsListener",
    topics = "payments.events",
    groupId = "payments-service"
)
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    paymentService.applyIdempotently(
        record.key(), record.value());

    acknowledgment.acknowledge();
}
```

In the snippet above, the container factory must be configured with a **manual ack mode**, such as `ContainerProperties.AckMode.MANUAL` or `MANUAL_IMMEDIATE`, and `paymentService` is an application service. Never call `acknowledge()` before required side effects have committed successfully if the business contract demands at-least-once processing.

Even if pause/resume works flawlessly, a crash after database commit and before Kafka offset commit can lead to **duplicate delivery**. Thus consumer idempotency (unique business keys, deduplication, transactional outbox, etc.) remains an independent requirement alongside pause/resume.

### 10.1. Do not use pause instead of retry/DLT

When a single record fails parsing or breaks a business rule, **pausing the whole container indefinitely** can block all other records. Spring Kafka provides `DefaultErrorHandler`, backoff, `DeadLetterPublishingRecoverer`, and retry topics for record-specific errors.

Pause fits **throughput/capacity issues or temporary dependency outages**, such as database maintenance. Distinguishing these two policies should be tested:

- Single-record data error: handle via the designed retry/skip/DLT path.
- Widespread downstream overload: pause the container or specific partitions in a controlled manner, then resume once recovery conditions hold.

## 11. Testing backpressure: automatic pause and resume by threshold

An application may pause when an internal queue, connection pool, or target service crosses a threshold, and resume once pressure subsides. The design should use **hysteresis** to avoid toggling too rapidly:

```text
Queue depth
   ^
  900 |                x       pause
  800 |---------- PAUSE_THRESHOLD ----------
  600 |               / \___
  400 |                      \__
  200 |---------- RESUME_THRESHOLD ---------
  100 |                            \___ resume
      +------------------------------------> time
```

For example, `pauseThreshold=800` and `resumeThreshold=200`. Using a single threshold causes a queue oscillating around that mark to repeatedly pause/resume (*flapping*), making latency unpredictable and raising operational overhead.

Illustrative control service:

```java
public void adjustFlow(int pendingWork) {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
    if (container == null) {
        throw new IllegalStateException("Listener not found");
    }

    if (pendingWork >= 800 && !container.isPauseRequested()) {
        container.pause();
    } else if (pendingWork <= 200 && container.isPauseRequested()) {
        container.resume();
    }
}
```

This is only **simple threshold logic**. Production should add cooldowns, maximum pause limits, metrics, and alerts when the controller fails to bring the container to the desired state. In multi-node deployments, each node has its own queue depth and instances may need independent pausing or centralized coordination.

### 11.1. Integration test scenario for backpressure

1. Set up a controllable fake capacity gauge.
2. Start the container and verify partition assignment.
3. Set gauge to `900`, call `adjustFlow()`, and await `isContainerPaused()`.
4. Send message `X` after pausing; confirm it has not entered the business handler.
5. Lower gauge to `500`; the container **stays paused** because the resume threshold is not met.
6. Lower gauge to `100`; the controller calls resume, await resumed state.
7. Confirm `X` is processed without being dropped.
8. Oscillate gauge around `800` and `200`; ensure no unwanted bursts of control commands occur.

This test validates control logic and Kafka behavior together. Separate unit tests can mock `MessageListenerContainer` to test threshold decisions faster, though mocks do not prove the real consumer paused/resumed.

## 12. Testing application restarts while paused

Pause is runtime state of the listener container, **not a Kafka topic property persisted on the broker**. When a process dies, the old container no longer exists. A new process can auto-start its listener per configuration and resume consuming records, even if an operator had paused the previous process.

Therefore, clarify the business requirement:

### Case A: pause is only for temporary load shedding

After a restart, the listener can resume normal operation. Tests focus on committed offsets and backlog consumption; do not expect the new container to remember the old pause state.

### Case B: pause is an operational decision that must survive restarts

For example, a data source is suspended for compliance or downstream maintenance. In that case:

1. Persist **desired state** (`PAUSED`/`RUNNING`) in an access-controlled durable database/config store.
2. On startup, load desired state before allowing business message consumption.
3. Coordinate lifecycle/assignment to apply pause at the right moment; do not let the listener consume a message and check desired state too late.
4. Observe actual pause state and alert if out of sync.
5. When an operator resumes, persist the new state and resume across relevant instances.

`autoStartup=false` can help avoid starting listeners before the control plane is ready, though start/assign/pause ordering must be designed explicitly. Calling `pause()` only after the listener has already received a record is insufficient for a requirement that **zero messages may be processed in PAUSED mode**.

### Two-process test scenario

```text
Process A:
  consumer active → pause confirmed → send X → X not processed
  kill/stop process A

Process B:
  load desired state = PAUSED from DB (if policy requires)
  ensure zero side effects for X before resume
  operator changes desired state = RUNNING
  resume/start processing → X commits once per policy
```

Like other recovery tests, measure **business output**, not just a boolean flag in a control service. With hard kills, records processed before offset commit may replay; tests must allow at-least-once delivery and verify idempotency.

## 13. Testing rebalances and multi-consumer operation

Testing one listener with one partition is a starting point, not proof that the application handles scale-out. In a Kafka consumer group, assignments change when members join/leave or the broker/coordinator changes state.

Extended tests should cover:

| Test | How to trigger | What to observe |
| --- | --- | --- |
| Two listener instances in one group | Start a second consumer | Partition distribution and per-instance desired pause state |
| Pause one instance | Pause container A, keep B running | B continues on its partitions, A processes nothing new once paused |
| Rebalance while paused | Stop/restart one instance | Partitions may move owners; do not rely on old owner's pause |
| Container concurrency > 1 | Configure multiple child consumers | Wait for full-container pause, not just one thread |
| Multiple partitions | Send to explicit partitions | Do not confuse container-wide pause with single-partition pause |
| Brief broker disconnect | Test in Kafka Testcontainers/cluster test | Consumer recovers; desired/actual states are monitored |

In these tests, log **message key**, partition, consumer group ID, assignment events, and output correlation IDs to distinguish late-processed messages from messages handled by another consumer in the group.

## 14. `@EmbeddedKafka` vs. Testcontainers?

| Tool | Strengths | Limitations |
| --- | --- | --- |
| Mock `MessageListenerContainer` | Fast unit testing of control service decision logic | No real poll, assignment, broker, or offsets |
| `@EmbeddedKafka` | Tests container, listener, topics, pause/resume, and producer/consumer in CI | Does not fully simulate production networking, auth, or topology |
| Kafka Testcontainers | Runs Kafka broker in a real container, closer to deployment setup | Slower/heavier, requires Docker |
| Staging/environment cluster | Tests security, rebalances, retention, metrics, and real scale | Costlier, requires strict data isolation and management |

A practical recommendation is **unit testing control policies**, **`@EmbeddedKafka` integration tests for core behavior**, and **Testcontainers or staging** for rebalances, broker failures, and multi-consumer concurrency. Do not force every unit test to boot a Kafka broker; likewise, do not treat mocking `pause()` as proof of reliability.

In tests with a real consumer, prioritize:

- Dedicated topics and consumer groups per test suite.
- Waiting for assignment before issuing pause controls.
- Awaiting producer acks and actual container state.
- Polling queues/latches with timeouts; no fixed sleeps.
- Clean teardown of listeners/consumers/brokers.
- Ensuring outputs/side effects and offsets align with ack policy.

## 15. Common testing mistakes

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `pause()` called yet listener still receives a few records | Records already in poll/in-flight; pause is a request | Wait for `isContainerPaused()` before sending test messages |
| Flaky test (passes sometimes, fails sometimes) | Short sleep, didn't wait for assignment or producer ack | Use assignment barrier, Awaitility, `Future.get()` |
| Container not found | Wrong `@KafkaListener` `id` or not registered yet | Check registry and `@EnableKafka` configuration |
| Waiting on `isContainerPaused()` forever | Consumer not started/assigned, listener blocked, or version/config difference | Inspect threads, assignments, listener, and timeouts |
| No message received after resume | Not truly resumed, wrong topic/group, record already processed earlier | Check state, offsets, logs, and outputs |
| Duplicate received on resume | Crash/rebalance before offset commit or non-idempotent writer | Inspect acks/transactions, business keys, and retries |
| Paused one Pod yet outputs still appear | Other Pods/consumers running in same group | Coordinate across whole group or understand partition ownership |
| Partition-level pause has no effect | Partition is not assigned to the targeted container | Inspect assignments and current owner |
| `pause()` drops throughput while lag climbs | Natural consequence of pausing processing | Monitor backlog, retention, and pause SLA |
| Prolonged pause causes old data loss | Retention purged log segments before resume | Enforce pause TTL, alerts, and recovery/backfill |
| App restarts and consumes despite prior pause | Pause state lived only in memory | Persist desired state and manage startup if required |
| `stop()` used instead of `pause()` | Container leaves group/triggers unexpected rebalance | Separate lifecycle from flow control |
| Test checks `isPauseRequested()` and assumes zero delivery | Only requested so far, not actually paused yet | Observe `isContainerPaused()`/effective events |
| Producer send did not await ack | Message may not have reached broker when checked | Await future completion before assertions |

## 16. Monitoring and operating pause/resume

To explain why a consumer is not processing messages, do not log only `pause called`. Structured control logs should contain:

```text
event=kafka.consumer.pause.requested
containerId=ordersListener
groupId=orders-service
reason=DOWNSTREAM_OVERLOADED
requestedBy=flow-controller
requestedAt=2026-11-16T09:00:00Z

event=kafka.consumer.paused
containerId=ordersListener
topic=orders.events
partitions=[0,1]
observedAt=2026-11-16T09:00:01Z

event=kafka.consumer.resumed
containerId=ordersListener
reason=DOWNSTREAM_RECOVERED
observedAt=2026-11-16T09:04:23Z
```

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `consumer_pause_requested` | Desired/requested container state |
| `consumer_paused` | Actual applied state |
| `consumer_pause_duration_seconds` | Total paused duration |
| `kafka_consumer_lag` | Backlog per group/partition |
| `records_processed_total` | Records successfully processed by callbacks per app contract |
| `processing_failures_total` | Listener/downstream failures after resume |
| `rebalances_total` | Detects assignment changes |
| `downstream_queue_depth` | Backpressure signal source |

These metric names are **suggestions for application instrumentation**, not a guarantee that all exist by default in Spring Kafka/Micrometer. Depending on your stack, Kafka client and Spring Kafka metrics may have different names/tags. Avoid putting per-record message keys, order IDs, or correlation IDs in metric labels due to high cardinality; use access-controlled logs/audits for granular identifiers.

A dashboard should show both **requested pause** and **actual pause**, reason and timestamp, consumer lag, assigned partition count, and downstream health. If `pauseRequested=true` while actual remains `false` unusually long, that signals a stuck listener or poll loop unable to reach the pause point and warrants an alert.

### 16.1. Control permissions and safety

If exposing a REST/Actuator endpoint to pause/resume:

1. Authorize which users/tools may invoke it.
2. Audit `requestedBy`, reason, and resulting state.
3. Never allow clients to pass arbitrary container IDs/groups/topics outside allowed scope.
4. Enforce pause duration limits and alert as backlog approaches retention/SLA limits.
5. For multi-node deployments, implement coordinated control rather than hitting one random Pod.
6. Never use resume to bypass unresolved maintenance requirements or security alerts.

## 17. Pre-acceptance test checklist

| What to verify | Reason |
| --- | --- |
| Consumer already has assignment | Pausing before assignment does not prove the same behavior |
| `isContainerPaused()` barrier present | Avoids sending messages before pause takes effect |
| Producer acked by broker | Prevents confusing an unfinished send with a paused consumer |
| Assertion for "no callback while paused" | Proves zero delivery after the pause point |
| Assertion for receiving message after resume | Proves backlog still gets processed |
| Explicit timeouts, no infinite waits | CI tests do not hang on failure |
| Separate in-flight test | Does not assume aborting an active callback |
| Crash offset/side-effect test if required | Pause does not replace idempotency |
| Multi-consumer rebalance/partition tests | Local pause state is not a group-wide lock |
| Startup desired-state test if durable pause needed | Process restarts can auto-consume |
| Teardown and isolation | Prevents leaking messages/offsets/contexts |

## 18. Conclusion

**Testing pause and resume in Spring Kafka** is more than calling `container.pause()` then `container.resume()`. A credible test must distinguish a **pause request** from an **actually effective pause**, wait for partition assignment, send messages **after the paused state holds**, verify the listener skips processing during the observation window, and confirm messages process upon resume.

Pausing keeps the consumer within the poll/group lifecycle rather than stopping it, yet it **does not cancel running callbacks, commit/seek offsets, guarantee exactly-once, or automatically survive process restarts**. Requirements for idempotency, error handling, consumer group rebalances, retention, and cross-node desired state require their own tests. Combining `@EmbeddedKafka`, proper barriers, output assertions, and failure-path scenarios yields a flow-control test suite that can be operated with confidence in production.

## References

- [Spring for Apache Kafka Reference — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): pause/resume APIs, states, and application timing.
- [Spring for Apache Kafka Reference — Pausing and Resuming Partitions](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume-partitions.html): per-`TopicPartition` pause/resume.
- [Spring for Apache Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): consumer/container events, including paused/resumed.
- [Spring for Apache Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils`, and listener testing.
- [Spring for Apache Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): polling, acknowledgments, and container lifecycle.
- [Spring for Apache Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retries, backoff, recoverers, and DLTs.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): consumer groups, pause/resume, offsets, retention, and client behavior.
