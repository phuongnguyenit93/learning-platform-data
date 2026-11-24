# Simulating Rebalances in Spring Kafka: Safe Practice and Observation

A Spring Kafka service is running steadily with one consumer instance. When a second replica is deployed to raise throughput, Kafka triggers a **rebalance**: consumers in the same group must receive new partition assignments. During this transition, some partitions temporarily have no worker, in-flight records may be redelivered, consumer lag rises, and non-idempotent business operations risk producing duplicate results. Conversely, scaling replicas down without understanding rebalances can make operators mistake paused consumption for Kafka losing data.

This lesson belongs to **Spring Kafka Reliability Operations → Operations Practice** and focuses on **simulating rebalances in an observable, reproducible, and verifiable way**. Using **Java 17, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5, and Embedded Kafka**, we deliberately have consumer A join a group, add consumer B, and then stop B—inspecting partition assignments and processed records at every stage. We then cover Kafka CLI and Kubernetes labs, differences between graceful shutdown and crashes, assignor impacts, relevant timeouts, and how to prevent lost or duplicated records.

Topic names, group IDs, and numbers below are **lab data**. Never stop or scale production consumers without operational approval, load limits, and a recovery plan.

## 1. What Is a Rebalance and Why Simulate It?

Within a **consumer group**, Kafka distributes partitions across consumer members of that group. Under standard consumption, **each partition is assigned to at most one member in the group at any given time**. Whenever membership or topology changes, Kafka recalculates work distribution. That recalculation is a **consumer group rebalance**.

```text
Topic: orders.rebalance.lab
Partitions: P0, P1, P2, P3
Group: orders-rebalance-lab-group

Phase A: single consumer

    P0 ─┐
    P1 ─┤
    P2 ─┼──> Consumer A
    P3 ─┘

Phase B: add consumer

    P0 ─┐
    P1 ─┴──> Consumer A

    P2 ─┐
    P3 ─┴──> Consumer B

Phase C: Consumer B leaves group

    P0 ─┐
    P1 ─┤
    P2 ─┼──> Consumer A
    P3 ─┘
```

The diagram shows one convenient assignment, **not a partition order guaranteed by Kafka**. Actual distribution depends on the assignor, subscriptions, member count, static membership, group protocol version, and cluster state.

### 1.1. Events That Typically Trigger a Rebalance

| Event | Description | Risk if Uncontrolled |
| --- | --- | --- |
| New consumer joins | Scale up replicas, add listener members | Partitions change owners; brief lag spike |
| Consumer stops normally | Rolling deployment, scale down, container stop | Remaining workers must absorb remaining partitions |
| Consumer crashes or loses network | Member stops heartbeating or never sends leave | Waits for timeout/detection before reassigning |
| Processing too slow to poll | Exceeds `max.poll.interval.ms` | Member may be evicted for failing to make progress |
| Topic partition count changes | New partitions added to topic | Group must pick up new work |
| Subscription changes | Consumer subscribes/unsubscribes topics | Assignments recalculated |
| Assignor or group protocol changes | Deploying new configuration | Can alter how partitions are revoked and granted |

**Not every operation is a rebalance.** Calling `pause()` on a consumer or container pauses consumption, yet **does not transfer partition ownership to another member**. Sending more messages, growing backlog, or adding `Thread.sleep(...)` in tests are also unreliable ways to intentionally trigger a rebalance.

### 1.2. What Must Be Verified in This Lab?

A trustworthy rebalance test asserts far more than "the listener was invoked":

1. **Membership:** both A and B genuinely belong to the **same consumer group**.
2. **Ownership:** initially A owns four partitions; once B joins, total assignments remain four, with no partition owned by two members concurrently.
3. **Reassignment:** when B leaves the group, A regains all four partitions.
4. **Progress:** records sent to partitions before and after transitions are still processed by the group.
5. **Offsets:** records reprocessed after errors or rebalances are not mistaken for brand-new events.
6. **Side effects:** when a record is redelivered, target DBs/APIs neither duplicate results nor lose data.
7. **Observability:** revoke/assign timestamps, lag, errors, and recovery times are visible.

A basic Embedded Kafka test checks **assignments and record progress**. Testing process crashes, network partitions, multi-broker failovers, and end-to-end guarantees requires separate advanced tests.

## 2. Related Components and State

```text
                Kafka cluster / group coordinator
                              |
                       member assignment
                              |
                 +------------+-------------+
                 |                          |
           Spring consumer A           Spring consumer B
                 |                          |
            poll / commit                poll / commit
                 |                          |
           @KafkaListener A           @KafkaListener B
                 |                          |
                 +-----------+--------------+
                             |
                        Business sink
```

| Concept | Meaning | Observed in Lab |
| --- | --- | --- |
| `group.id` | Consumer group identifier | A and B share the same group |
| `client.id` | Client identifier for metrics/logs | Distinguishes instances; does not replace group ID |
| Topic partition | Unit of assignment | Set of `TopicPartition`s per member |
| `position` | Consumer's next fetch offset | Can advance ahead of committed offsets |
| Committed offset | Persisted group progress | New owners resume from recorded position |
| Assignment | Partitions currently owned by consumer | Shifts on join and leave |
| Revocation | Partitions taken back from member | Hook for flushing/cleaning state safely |
| Rebalance listener | Callbacks for assign/revoke/lost events | Used to observe lifecycle |
| Consumer lag | Gap between log end and committed progress | Can spike briefly during rebalances |

Kafka offsets are **per-partition positions**. Offset 7 on P0 and offset 7 on P3 are completely different messages. When a record is redelivered due to an ownership change, correlate by **topic, partition, offset**, and business event ID—not merely key or payload value.

## 3. Rebalancing Does Not Delete or Move Records

Kafka persists records in partition logs. When member B takes over P2 and P3 from A, Kafka **does not physically move data** between partitions for a rebalance. What changes is which consumer member is authorized to poll and process those partitions.

```text
P2 log:
offset 10 ── offset 11 ── offset 12 ── offset 13 ──>
                     ^
               committed offset

Before rebalance: A reads P2
After rebalance:   B reads P2 from the committed offset
```

When Kafka commits offset **12**, it normally means the next position to read is **offset 12**, indicating prior records were recorded per consumer group contract. If an application completes a business side effect without committing offset 12 and then loses ownership, the new owner can reread the record that already triggered the side effect.

Therefore:

```text
Rebalance + incomplete commit
    -> possible redelivery
    -> business handler must tolerate duplicates
```

**At-least-once** is the standard design when consumers process data first and commit offsets afterward. It avoids skipping records while requiring idempotency to handle duplicates. Committing before persisting results, or committing despite errors, risks losing business data. Never switch to auto-commit just to make a rebalance test "error-free."

## 4. Two Rebalance Modes: Eager and Cooperative

Not every assignor revokes partitions the same way. Understanding the difference helps read logs accurately and avoid overly brittle test assertions.

### 4.1. Eager Rebalance

With an **eager assignor** such as `RangeAssignor` in a supporting group protocol, members may have their entire assignment revoked and then reassigned during coordination. Even if a partition ends up staying on A, revoked/assigned callbacks can still fire while the group stabilizes.

```text
A holds P0 P1 P2 P3
        |
        | B joins
        v
   Revoke assignments
        |
        v
A gets P0 P1       B gets P2 P3
```

### 4.2. Cooperative Rebalance

With `CooperativeStickyAssignor` and compatible configuration, the group can **incrementally revoke only the partitions that actually need to move** instead of revoking everything at once. This reduces disruption during rolling deployments.

```text
A: P0 P1 P2 P3
       |
       | B joins
       v
A keeps P0 P1, incrementally releases P2 P3
                           |
                           v
B receives P2 P3 after ownership transfers
```

These diagrams show the core idea: cooperative rebalances can take multiple rounds with different callbacks than eager ones. Never assert "every partition is revoked exactly once" across both modes.

**Version scope:** Kafka has multiple group protocol generations (classic vs. newer consumer group protocol). Assignor property names and capabilities vary by broker/client version and protocol. For this lab, pin `RangeAssignor` for predictability; in production, inspect your actual group protocol and assignor before planning a migration.

## 5. Preparing the Lab Project

Requirements:

- Java 17 or newer compatible with your Spring Boot version.
- Matching Spring Boot 3.x and Spring Kafka 3.x.
- JUnit 5, AssertJ, and `spring-kafka-test`.
- No external Kafka cluster needed for the **basic join/leave lab**, which uses Embedded Kafka.

Example Gradle dependencies (with Spring Boot BOM and plugins applied):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management should keep Spring Kafka versions aligned. Never force an arbitrary Kafka client version to "fix rebalance bugs" without checking your application's compatibility matrix.

Directory layout:

```text
src/
├── main/java/com/example/kafka/
│   └── ReliabilityApplication.java
└── test/java/com/example/kafka/
    └── RebalanceSimulationTest.java
```

The test below places the listener fixtures and Spring configuration **inside the test file itself** so you do not need extra source files.

## 6. Test Scenario: A → A+B → A

Fixed **4-partition** topic and single group:

```text
Topic: rebalance.orders.input
Partitions: 4
Group: rebalance-lab-group
```

Phases:

| Phase | Action | Expected Assignment | Test Records |
| --- | --- | --- | --- |
| 1 | Start A; B stopped | A: 4, B: 0 | `phase1-p0` ... `phase1-p3` |
| 2 | Start B in the same group | A: 2, B: 2 | `phase2-p0` ... `phase2-p3` |
| 3 | Stop B gracefully | A: 4, B: 0 | `phase3-p0` ... `phase3-p3` |

We configure `RangeAssignor` so distributing **4 partitions across 2 members subscribed to one topic** yields two partitions per member once settled. Never hardcode that A always owns P0 and P1: member IDs/ordering and assignor decisions are not business contracts.

`@KafkaListener(autoStartup = "false")` lets the test control exactly when A and B start. Never put B in a different consumer group: both members must share the **exact same `groupId`** to rebalance against each other.

## 7. Integration Test with Embedded Kafka

The example below is a **complete Java file** for this lab using `KafkaListenerEndpointRegistry` to start and stop two listener containers. `RecordingConsumers` records handler identities and record coordinates into a `ConcurrentLinkedQueue` for thread-safe inspection.

`RebalanceSimulationTest.java`:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.AfterEach;
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
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
    classes = RebalanceSimulationTest.TestApp.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record",
        "spring.kafka.consumer.properties.partition.assignment.strategy="
            + "org.apache.kafka.clients.consumer.RangeAssignor"
    }
)
@EmbeddedKafka(
    partitions = 4,
    topics = "rebalance.orders.input",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RebalanceSimulationTest {

    private static final String TOPIC = "rebalance.orders.input";
    private static final int PARTITIONS = 4;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApp {
        @Bean
        RecordingConsumers recordingConsumers() {
            return new RecordingConsumers();
        }
    }

    static class RecordingConsumers {

        record Delivery(
                String member,
                String topic,
                int partition,
                long offset,
                String value) {}

        private final ConcurrentLinkedQueue<Delivery> deliveries =
                new ConcurrentLinkedQueue<>();

        @KafkaListener(
            id = "member-a",
            topics = TOPIC,
            groupId = "rebalance-lab-group",
            autoStartup = "false")
        public void consumeA(ConsumerRecord<String, String> record) {
            capture("A", record);
        }

        @KafkaListener(
            id = "member-b",
            topics = TOPIC,
            groupId = "rebalance-lab-group",
            autoStartup = "false")
        public void consumeB(ConsumerRecord<String, String> record) {
            capture("B", record);
        }

        private void capture(
                String member, ConsumerRecord<String, String> record) {
            deliveries.add(new Delivery(
                    member,
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    record.value()));
        }

        List<Delivery> snapshot() {
            return List.copyOf(deliveries);
        }
    }

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Autowired
    private KafkaTemplate<String, String> producer;

    @Autowired
    private RecordingConsumers recorder;

    private MessageListenerContainer container(String id) {
        MessageListenerContainer result =
                registry.getListenerContainer(id);
        if (result == null) {
            throw new IllegalStateException(
                    "Missing test listener container: " + id);
        }
        return result;
    }

    private Set<TopicPartition> owned(
            MessageListenerContainer container) {
        Collection<TopicPartition> assigned =
                container.getAssignedPartitions();
        return assigned == null
                ? Set.of()
                : new HashSet<>(assigned);
    }

    private static void await(
            BooleanSupplier condition, Duration timeout, String reason)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(50); // Bounded polling, not a blind sleep.
        }
        throw new AssertionError(
                "Timed out while waiting for " + reason);
    }

    private void sendOnePerPartition(String phase) throws Exception {
        for (int partition = 0; partition < PARTITIONS; partition++) {
            producer.send(
                    TOPIC,
                    partition,
                    "order-" + partition,
                    phase + "-p" + partition)
                    .get(10, TimeUnit.SECONDS);
        }
    }

    private void awaitPhase(String phase) throws Exception {
        Set<String> expected =
                IntStream.range(0, PARTITIONS)
                        .mapToObj(p -> phase + "-p" + p)
                        .collect(Collectors.toSet());

        await(
                () -> recorder.snapshot().stream()
                        .map(RecordingConsumers.Delivery::value)
                        .collect(Collectors.toSet())
                        .containsAll(expected),
                Duration.ofSeconds(20),
                "all records of " + phase);
    }

    @AfterEach
    void stopContainers() {
        container("member-b").stop();
        container("member-a").stop();
    }

    @Test
    void redistributesPartitionsWhenMemberJoinsAndLeaves()
            throws Exception {

        MessageListenerContainer a = container("member-a");
        MessageListenerContainer b = container("member-b");

        // PHASE 1: only A is running.
        a.start();
        await(
                () -> owned(a).size() == PARTITIONS,
                Duration.ofSeconds(20), "A owns four partitions");

        assertThat(owned(b)).isEmpty();
        sendOnePerPartition("phase1");
        awaitPhase("phase1");

        assertThat(recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase1"))
                .allMatch(e -> "A".equals(e.member())))
                .isTrue();

        // PHASE 2: B joins A's exact group.
        b.start();
        await(
                () -> owned(a).size() == 2 && owned(b).size() == 2,
                Duration.ofSeconds(30),
                "A and B each own two partitions");

        Set<TopicPartition> aOwned = owned(a);
        Set<TopicPartition> bOwned = owned(b);
        Set<TopicPartition> union = new HashSet<>(aOwned);
        union.addAll(bOwned);

        assertThat(aOwned).doesNotContainAnyElementsOf(bOwned);
        assertThat(union).hasSize(PARTITIONS);

        sendOnePerPartition("phase2");
        awaitPhase("phase2");

        Set<String> phase2Members = recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase2"))
                .map(RecordingConsumers.Delivery::member)
                .collect(Collectors.toSet());

        assertThat(phase2Members).contains("A", "B");

        // PHASE 3: B stops gracefully.
        b.stop();
        await(
                () -> owned(a).size() == PARTITIONS,
                Duration.ofSeconds(30),
                "A owns all partitions again");

        sendOnePerPartition("phase3");
        awaitPhase("phase3");

        assertThat(recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase3"))
                .allMatch(e -> "A".equals(e.member())))
                .isTrue();

        Set<String> distinctValues = recorder.snapshot().stream()
                .map(RecordingConsumers.Delivery::value)
                .collect(Collectors.toSet());
        assertThat(distinctValues).hasSize(12);
    }
}
```

In this example:

- `@EmbeddedKafka` provisions a **four-partition** topic on the test broker.
- Both `@KafkaListener` methods have distinct `id`s while sharing **`groupId`**, and do not auto-start when the Spring context boots.
- `registry.getListenerContainer(...)` retrieves the live container to control membership.
- `getAssignedPartitions()` inspects assignments **after waiting for stability**.
- The producer sends **one message to each explicit partition**, avoiding hash-distribution luck across four random keys.
- `await(...)` polls with a bounded timeout against **real state**, rather than `Thread.sleep(2000)` and guessing the group settled.
- `ack-mode=record` with auto-commit disabled lets the container manage progress for this non-transactional lab record listener.

This test verifies **membership, assignments, and delivery progress**—not exactly-once semantics. Even though **12 distinct values** were observed, records can still be redelivered if a fault occurs between a business side effect and offset commit. Pushing `Delivery` into the queue happens **inside the listener before offset commit**, so the queue alone does not prove transactional side effects.

### 7.1. Why Not Assert "Every Record Is Invoked Strictly Once"?

In an at-least-once system, a processed record whose offset has not committed yet can be redelivered upon rebalance or crash. Asserting callback count equals 12 can make tests **flaky** or accidentally test a guarantee Kafka does not provide.

In this lab, we assert:

```text
All 12 expected eventIds/values were observed.
Ownership never overlaps.
Member B actually processes records once assigned partitions.
Member A continues after B leaves the group.
```

If business rules require "never create two invoices," tests must verify an **idempotent sink**—such as a unique constraint on `(event_id)` in a DB—instead of assuming the listener is never invoked twice.

### 7.2. Why Choose `RangeAssignor`?

With **one four-partition topic** and two members subscribed to that topic, `RangeAssignor` ensures Phase 2 settles cleanly with two partitions per member. With `CooperativeStickyAssignor`, the test goal remains that every partition has one rightful owner, though callback counts and order differ.

To properly test **cooperative mechanics**, write a dedicated configuration/test and log callbacks per round. Never apply identical "all partitions revoked" assertions across both modes.

### 7.3. Avoiding Interference from Other Tests

The test uses a fixed topic and group name, so run it **in an isolated test context/broker**. If a suite has multiple classes sharing the same topic/group or running in parallel, assignments and callbacks can collide. Give each fixture unique topic/group names or isolate contexts; never raise timeouts to mask stray consumers joining the group.

## 8. Observing `assigned`, `revoked`, and `lost` Callbacks

The test in section 7 polls assignment snapshots. To know **exactly when rebalances fire**, Spring Kafka supports `ConsumerAwareRebalanceListener`, configured on the listener container's `ContainerProperties`:

```java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

ConsumerAwareRebalanceListener tracer =
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        System.out.println(
                "rebalance_revoked_before_commit partitions=" + partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        System.out.println(
                "rebalance_assigned partitions=" + partitions);
    }
};

factory.getContainerProperties()
        .setConsumerRebalanceListener(tracer);
```

This is a **configuration fragment**: `factory` is a project-declared `ConcurrentKafkaListenerContainerFactory`, and the listener must be attached **before the container starts**. Production code should use a structured logger instead of `System.out.println`.

Key callbacks:

| Callback | When It Matters | Handling Principle |
| --- | --- | --- |
| `onPartitionsAssigned` | Member receives partitions | Load per-partition state/caches if needed; mark new owner |
| `onPartitionsRevokedBeforeCommit` | Revocation finishing before offset commit | Flush/finalize state per design; avoid slow I/O |
| `onPartitionsRevokedAfterCommit` | After the associated offset commit point | Clean up state no longer owned |
| `onPartitionsLost` | Partition ownership lost; commits may no longer be safe | Do not attempt commits as if still owner |

Exact callbacks and ordering depend on container, assignor, group protocol, and version. Never assume `onPartitionsRevoked...` runs in **every** crash: if a process dies abruptly, that process cannot run callbacks. Remaining members receive reassignments through the coordinator once the dead member is detected.

### 8.1. Callbacks Must Be Lightweight and Safe

Never use rebalance callbacks to:

- Call HTTP APIs without tight timeouts for minutes.
- Perform unbounded DB writes or hold open long transactions.
- Manually call `commitSync()` on a **lost** partition just to keep logs clean.
- Kick off async work and assume state is flushed before ownership transfers.
- Emit messages to target topics without idempotency or proper transactions.

Slow callbacks prolong disruption for the entire group. If you maintain per-partition local state, keep checkpoints lightweight, distinguish revoked from lost, and rely on durable storage for recovery.

### 8.2. Distinguishing Callback Traces from Reliable Audit History

```text
2026-... group=orders-rebalance-lab-group
  event=partitions_assigned member=A partitions=[P0,P1,P2,P3]

2026-... group=orders-rebalance-lab-group
  event=partitions_revoked member=A partitions=[P2,P3]

2026-... group=orders-rebalance-lab-group
  event=partitions_assigned member=B partitions=[P2,P3]
```

These are **illustrative logs only**. With an eager assignor, revocation callbacks may list all partitions before reassigning. With cooperative mode, retained partitions stay untouched. Never treat callback counts as processed record counts or retry counts.

## 9. Inspecting Consumer Groups via Kafka CLI

In environments with the Kafka CLI and `DESCRIBE` permissions, inspect group state externally:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --group rebalance-lab-group \
  --describe
```

Illustrative output:

```text
GROUP                  TOPIC                    PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
rebalance-lab-group    rebalance.orders.input   0          101             105             4
rebalance-lab-group    rebalance.orders.input   1          203             204             1
rebalance-lab-group    rebalance.orders.input   2          312             312             0
rebalance-lab-group    rebalance.orders.input   3          418             423             5
```

Inspect members and assignments:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --group rebalance-lab-group \
  --describe --members --verbose
```

Formatting for member IDs, hosts, client IDs, assignments, and states varies across Kafka CLI versions and group protocols. During an active rebalance, fields are transiently unstable; **take multiple snapshots** rather than concluding from one run.

### 9.1. Manual Lab Steps

1. Create a test topic with at least four partitions.
2. Start **one** consumer instance in group `rebalance-lab-group`.
3. Run `--describe --members --verbose` to confirm the first instance owns all partitions.
4. Start a **second instance** in the same group with a distinct `client.id`.
5. Watch assign/revoke logs and recheck assignments.
6. Send messages to every partition and confirm each is processed by its rightful owner.
7. Stop the second instance gracefully and watch the first instance reclaim all assignments.
8. Verify lag drains, DLT stays quiet, and destination data has no duplicates.

To simulate a rolling deployment, repeat with multiple replicas changing **one member at a time** while measuring disruption; avoid stopping/starting the whole group at once when proving graceful rollout.

## 10. Simulating Rebalances with Kubernetes

Suppose you have a lab-only Deployment:

```text
Namespace: kafka-lab
Deployment: orders-consumer-lab
Topic: rebalance.orders.input
Consumer group: rebalance-lab-group
```

The commands below are lab instructions only—**never run them on production**:

```bash
# Verify the right Kubernetes context/namespace before making changes.
kubectl config current-context
kubectl -n kafka-lab get deployment orders-consumer-lab

# Phase 1: one member (assuming concurrency=1 per pod).
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=1

# Phase 2: add member, triggering rebalance.
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=2

# Phase 3: scale down member.
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=1
```

After each step, inspect group assignments via the Kafka CLI or dashboard. Never equate **pod count** with **consumer member count** if pods set `spring.kafka.listener.concurrency > 1` or run multiple listeners in the same group.

### 10.1. Consumer Configuration in Spring Boot

Example for a service running one record listener on the lab topic:

```yaml
app:
  kafka:
    topic: rebalance.orders.input

spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: rebalance-lab-group
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
    listener:
      concurrency: 1
      ack-mode: record
```

This example uses the **classic protocol with a cooperative assignor where client and broker support it**; do not apply it blindly if your cluster runs the newer group protocol with a different assignment model. Serializers, security, timeouts, and error handling must still be configured per application.

`auto-offset-reset: earliest` does **not** make the group reread the entire topic when valid committed offsets exist. When a new member takes over a partition, it resumes from the group's committed position. Never reset offsets as part of normal rebalances.

### 10.2. Safe Rolling Updates

A deployment sequence should aim for:

```text
New pod ready to run consumer
         |
         v
Join consumer group
         |
         v
Partition assignment changes
         |
         v
Old pod stops accepting work / leaves safely
         |
         v
New owner continues from committed offsets
```

Actual order depends on deployment strategy (`RollingUpdate`, `maxSurge`, `maxUnavailable`), readiness/liveness probes, startup latency, termination grace periods, and container shutdown behavior. **Web server readiness does not automatically prove a Kafka listener holds partitions.** For pure Kafka consumer services, readiness should reflect health/processing readiness without triggering restart loops during brief Kafka rebalances.

Control:

- Avoid deploying in a way that churns every member simultaneously when unnecessary.
- Allow enough grace time for in-flight records to finish, commit offsets, or roll back cleanly.
- Ensure SIGTERM shuts down listener containers cooperatively with Kubernetes termination.
- Never report a pod "healthy" solely because the JVM is up while its consumer thread is wedged indefinitely.
- Monitor assigned partition counts, rebalance duration, lag, and instance counts during rollouts.

Graceful shutdown **reduces interrupted work**, though it does not turn an at-least-once consumer into exactly-once.

## 11. How Does Graceful Leave Differ from a Crash?

In section 7's test, we called:

```java
container("member-b").stop();
```

That is a **controlled leave**. Spring Kafka stops the listener, closes the consumer, and runs lifecycle cleanup. It is not equivalent to:

```text
kill -9 JVM
pod lost to node failure
network cut blocking heartbeats
process OOMKilled
```

### 11.1. Graceful Stop

```text
Member B holds P2,P3
       |
       v
Stop requested
       |
       +--> complete/stop processing per container policy
       +--> commit/rollback appropriately
       +--> leave group / close consumer
       |
       v
Group reassigns P2,P3
       |
       v
Member A resumes processing
```

Stop duration and commits depend on listener type, ack mode, transactions, thread state, and timeouts. Never assume every offset committed simply because `stop()` was called.

### 11.2. Crash or Lost Heartbeat

```text
Member B crashes unexpectedly
       |
       X--> Cannot execute B's own cleanup callbacks
       |
       v
Coordinator detects member is no longer valid
       |
       v
Rebalance / reassignment
       |
       v
A receives P2,P3 from committed offsets
       |
       v
Uncommitted records may be redelivered
```

When simulating crashes, use **separate processes/containers** or a Testcontainers/Kubernetes lab. Killing the JUnit JVM itself cannot verify post-crash assertions; run a controller test process that stays alive to drive the producer, watch the group, and reconcile the sink after killing the worker process.

### 11.3. Metrics to Compare

| Behavior | Graceful Stop | Crash |
| --- | --- | --- |
| Consumer runs shutdown callbacks | Yes, per lifecycle | Not guaranteed |
| Sends leave / closes consumer cleanly | Usually yes, per protocol and state | No |
| Time to detect absent member | Typically shorter | Depends on session/heartbeat timeouts |
| In-flight records may redeliver | Still possible | More likely if offsets uncommitted |
| Business side effects auto-roll back | No | No |
| Requires idempotency | Yes | Yes |

Never rely on a fixed number of seconds for crash recovery; measure it directly and document `session.timeout.ms`, poll timeouts, static membership, group protocol, and load.

## 12. Timeouts Affecting Rebalances

Common Kafka consumer properties:

| Property | Governs | Common Mistake |
| --- | --- | --- |
| `session.timeout.ms` | Detects missing heartbeats in classic group protocol within broker bounds | Too high delays crash detection; too low causes false evictions |
| `heartbeat.interval.ms` | Heartbeat cadence in classic protocol; coordinated with session timeout | Confusing it with business processing timeout |
| `max.poll.interval.ms` | Maximum time allowed between `poll()` calls | Slow record handling misses polls and triggers eviction |
| `max.poll.records` | Maximum records returned per `poll()` | Setting too high makes a single poll take too long |
| `partition.assignment.strategy` | Partition grant/revoke algorithm in classic protocol | Changing assignor abruptly during mixed rollouts |
| `group.instance.id` | Static membership when properly configured | Duplicating IDs across pods or thinking static members never rebalance |

Newer group protocols move parts of heartbeat/session tuning broker-side or introduce different properties. Never apply one fixed timeout tuple across all clusters and Kafka versions.

### 12.1. `max.poll.interval.ms` Is a Trap for Slow Processors

Suppose one poll returns 500 records and each takes 3 seconds sequentially:

```text
500 × 3 seconds = 1,500 seconds
```

If time between polls exceeds the configured limit, the consumer can lose partition ownership and enter reassignment. In Spring Kafka, exact behavior also depends on container polling, concurrency, pauses, and listener logic, yet the core issue remains **never letting a single poll block too long**.

Improvements:

- Reduce `max.poll.records` to match real per-record processing times.
- Optimize DB/API queries with strict timeouts and bounded concurrency.
- Offload long work to durable queues/outboxes if needed, preserving commit and idempotency contracts.
- Choose batch listeners or worker architectures suited to high throughput.
- Watch poll interval, processing duration, and lag metrics instead of blindly inflating timeouts.

**Never tweak `session.timeout.ms` alone to fix `max.poll.interval.ms`**: they govern completely different mechanisms.

## 13. Static Membership and Cooperative Rebalancing to Reduce Churn

In systems with stable pod identities and brief restarts, Kafka **static membership** (`group.instance.id`) can prevent unnecessary rebalances depending on group protocol and deployment. Key rules:

- Every concurrently running instance must have a **unique `group.instance.id`**.
- IDs should remain stable across restarts of the same logical instance.
- Never share one static ID across multiple Deployment pods; colliding IDs fence/evict members.
- Static membership does not fix slow processing, prevent every rebalance, or replace timeouts and monitoring.

A StatefulSet with stable identities fits static membership better than a Deployment with random pod names. Still, it is a **deployment choice**, not a setting to turn on blindly in every Spring Kafka service.

**`CooperativeStickyAssignor`** reduces unnecessary revocations during membership changes, though you must verify compatibility across running members and follow safe assignor migration steps. During rolling upgrades, never mix incompatible protocols/assignors within one group without a plan.

## 14. Consumer Lag and Progress After Rebalance

A rebalance often produces a curve like:

```text
Lag
 ^
 |                 /----\
 |                /      \
 |               /        \__
 |______________/             \__________> Time
                 rebalance
```

Producers keep appending while consumers briefly pause assignment or fall behind, causing lag to rise. Once the group stabilizes and processing throughput exceeds arrival rate, lag drains.

| Metric | Meaning |
| --- | --- |
| Rebalance count per consumer/group | Frequency of membership/assignment changes |
| Rebalance duration | Length of coordination disruption |
| Assigned partition count | Flags idle members or missing assignments |
| Committed offset | Persisted group progress |
| Current consumer position | Next fetch position; not always equal to committed offset |
| Consumer lag per partition | Which partitions are falling behind |
| Processing latency | Whether business handler breaches SLAs |
| Commit failures / lost partitions | Progress disruption during ownership transfers |
| DLQ/DLT events | Unprocessable or recovered records |
| Duplicate business event count | How often idempotency suppressed redeliveries |

Spring Kafka/Micrometer and Kafka client metrics expose related measurements, though **exact metric names and tags vary by version and registry**. Inspect live runtime metrics instead of writing alerts from guessed names.

Never use `orderId` or Kafka offsets as metric labels: cardinality is too high. Keep tags bounded to topic, partition, group, client ID, and error codes; inspect individual records via access-controlled structured logs and audits.

### 14.1. Criteria to Confirm Service Recovery

"Group is STABLE" is not enough on its own:

1. Every active partition has a healthy owner.
2. No unhealthy members or colliding static member IDs remain.
3. Lag trends downward relative to input/output rates rather than staying pinned on one partition.
4. Error and commit failure rates return within acceptable thresholds.
5. Business events reconcile with zero unpolicy-approved missing or duplicate side effects.
6. DLT/retry backlogs have clear handling outcomes.

A group with completely stable assignments can still stall on a **poison record** keeping lag flat. Rebalancing never fixes bad data.

## 15. Rebalances and Data Correctness: Redelivery Must Be Designed For

Consider this listener:

```java
@KafkaListener(topics = "orders.rebalance.lab",
               groupId = "orders-rebalance-lab-group")
public void consume(OrderCreated event) {
    paymentService.charge(event.orderId());
    // Offset is committed by the container after the listener returns.
}
```

Failure path:

```text
A receives offset 10
    |
    +--> paymentService.charge() SUCCESS
    |
    +--> A crashes before offset commit
    |
    v
Rebalance -> B receives offset 10
    |
    +--> paymentService.charge() AGAIN?
```

A Kafka consumer group cannot automatically roll back a payment already captured on an external HTTP service. You need a **stable idempotency key** on the payment service or an inbox/outbox pattern.

### 15.1. Inbox Example with a Unique Constraint

One way to deduplicate Kafka events written to a database:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Inside **one DB transaction**, record `event_id` and apply the business update. If `event_id` already exists, handle it as a safe duplicate per rules. Only after the business transaction commits should the container commit Kafka progress per configured policy.

Never split "insert inbox marker" and "write business state" into two uncoordinated transactions expecting exactly-once. If one commits and the other fails, work is either lost or duplicated.

### 15.2. Kafka Transactions Do Not Automatically Cover External Side Effects

For **consume Kafka → process → produce Kafka** flows, Spring Kafka transactions coordinate offsets and output Kafka records to achieve scoped guarantees when properly configured. External databases, HTTP endpoints, emails, and payment gateways **do not join the Kafka transaction automatically**.

When using Kafka transactions:

- Test rollback, redelivery, and after-rollback processors explicitly.
- Configure Kafka observers with `isolation.level=read_committed` to inspect committed outputs.
- Never treat a "delivered all records" rebalance test as proof of end-to-end exactly-once.
- Inject crashes after external side effects and before commit to verify sink deduplication.

## 16. Advanced Test: Triggering a Rebalance Mid-Processing

Section 7's `A → A+B → A` test shifts membership **between batches after records finish**. To test harder failure modes, hold a worker mid-record:

```text
Time        Consumer A                         Consumer B
----        ----------                         ----------
T0          owns P0-P3
T1          polls event-42 on P2
T2          begins database/API work
T3                                             joins group
T4          rebalance / revoked or delayed
T5          processing ends, commit?
T6                                             may receive P2
T7                                             may redeliver event-42
```

For controlled simulation, use a **`CountDownLatch`** in a test double to pause A at a deterministic point until B joins:

```java
CountDownLatch enteredHandler = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

void simulateSlowProcessing() throws InterruptedException {
    enteredHandler.countDown();
    if (!releaseHandler.await(15, TimeUnit.SECONDS)) {
        throw new IllegalStateException("TEST_HANDLER_TIMEOUT");
    }
}
```

This is an **illustrative fixture**, not a complete listener. Always release `releaseHandler` in `finally` so tests never hang. Also do not treat a latch as simulating all Kafka semantics: while A blocks on its poll thread, when the coordinator changes ownership depends on timeouts and protocols, **so partitions will not necessarily transfer to B the instant `b.start()` runs**.

Design targeted tests per scenario:

| Scenario | How to Trigger | What to Verify |
| --- | --- | --- |
| B joins while A is processing | Start B while A waits on test latch | Never two concurrent owners; processing/commits obey policy |
| A exceeds `max.poll.interval.ms` | Hold handler past tight test config timeout | Member loses progress eligibility; record may redeliver |
| A crashes after DB commit | Kill separate worker process before offset commit | Unique business result occurs only once |
| A stops gracefully | Stop container cleanly via lifecycle | B takes over partitions; lag drains |
| Broker/network outage | Testcontainers/network fault in isolated lab | No records lost under durability contract |
| Kafka transaction aborts | Listener throws after `KafkaTemplate.send` | Aborted output hidden from `read_committed` |

For crash tests, never run `kill -9` on the JUnit JVM itself. A **test controller process** must stay alive to drive the producer, inspect the group, and reconcile the sink after killing the worker process.

### 16.1. Assertions for Crash Tests

- Test record is published with a stable `eventId`.
- Worker A confirms it began processing via a deterministic signal.
- Side effect committed at the controlled point.
- Worker A is terminated via the chosen fault injection.
- Worker B takes over the partition and, if uncommitted, redelivers the exact topic-partition-offset.
- Sink holds **one** business result or matching idempotency marker.
- DLT/offset lag is not silently skipped; recovery completes cleanly.

Never assert `listener invocation count == 1` in an at-least-once design. **Consumers may reprocess records while sinks must never duplicate side effects.**

## 17. Bad Tests That Lead to False Conclusions

| Anti-Pattern | Why It Fails | Replace With |
| --- | --- | --- |
| Starting B with a different group ID than A | Two independent groups never rebalance together | Exact same `group.id` |
| Using only `Thread.sleep(2000)` after start | CI/broker scheduling is non-deterministic | Bounded wait on real conditions |
| Sending 4 keys and assuming 1 per partition | Hash functions do not guarantee uniform small samples | Explicit partition sends in tests |
| Counting only revoke/assign callbacks | Callbacks differ across eager/cooperative/protocols | Inspect actual assignments |
| Sharing topics/groups across tests | Stray consumers alter ownership | Isolate test contexts, topics, and groups |
| Using `pause()` to "force a rebalance" | Pausing does not leave the group | Start/stop members or change subscriptions |
| Asserting every event runs strictly once | Rebalances/crashes cause redeliveries | Verify distinct event IDs and sink idempotency |
| Ignoring committed offsets | Read position is not committed progress | Check group offsets after stabilizing |
| Committing offsets before side effects | Crashes lose work | Commit after safe business completion |
| Running unbounded HTTP calls in revoke callbacks | Extends group-wide pauses | Lightweight flushes, bounded I/O, checkpoints |
| Treating graceful stop as a crash | Misses session timeouts and skipped callbacks | Separate-process / chaos tests |
| Treating lag 0 as zero duplicates | Offsets advance even if sink wrote twice | Reconcile event IDs and unique constraints |
| Treating STABLE group as full system health | Poison records or DB errors can still exist | Inspect throughput, lag, sinks, and DLTs |
| Changing `group.instance.id` arbitrarily when scaling | Colliding static IDs fence members | Unique, topology-aligned IDs |
| Dumping raw keys/values into rebalance logs | Risk of leaking sensitive data | Log topic, partition, offset, and safe error codes |

## 18. Operational Checklist for Frequent Rebalances

When dashboards show frequent group rebalances, pinpoint the **root cause** before raising timeouts:

1. **Membership:** are pods crash-looping, autoscaling flapping, or rolling out?
2. **Processing:** is blocking I/O pushing polls past limits, or are long GC pauses stalling threads?
3. **Connectivity:** are there network, DNS, TLS, auth, or coordinator timeout errors?
4. **Assignment:** are partition counts, assignors/group protocols, and subscriptions consistent across members?
5. **Static membership:** are `group.instance.id` values colliding or unstable?
6. **Resources:** do workers have enough CPU, memory, DB connections, and downstream API quota?
7. **Lag:** which partitions are lagging, and are hot keys or poison pills involved?
8. **Commits:** are there `CommitFailedException`, `RebalanceInProgressException`, or lost partitions?
9. **Shutdown:** do readiness checks and termination grace periods let consumers exit cleanly?
10. **Data correctness:** did the business sink suffer duplicates or gaps despite the group recovering?

Fixes may include stabilizing autoscaling, reducing per-poll work, bounding timeouts/using durable queues, adopting a cooperative assignor safely, configuring static membership properly, or removing excess idle consumers. **Inflating session timeouts massively** only delays crash detection and masks symptoms without unsticking wedged handlers.

## 19. Extended Practice Exercises

After running the baseline integration test:

1. **Two-member rebalance:** with 4 partitions, start A then B; verify total assignments always equal 4 once settled.
2. **Scale down:** stop B, verify A reclaims all 4 partitions and consumes every partition's records.
3. **Avoid group mix-ups:** intentionally change B's `groupId` and explain why A and B act as independent groups without rebalancing.
4. **More consumers than partitions:** start 6 consumer members on a 4-partition topic; verify some members get zero partitions.
5. **Compare eager vs. cooperative:** run the lab with `RangeAssignor` and then `CooperativeStickyAssignor` on a compatible protocol; compare revoked/assigned callbacks.
6. **Rebalance listener:** add tracing via `ConsumerAwareRebalanceListener`, logging timestamps, members, and revoked/assigned partitions.
7. **Lag:** produce a steady stream of records while changing membership and compare committed offsets/lag before, during, and after rebalance.
8. **Slow handler:** hold one record with a latch, start B, and observe rebalancing/timeouts; always release the latch in `finally`.
9. **Crash test:** split the consumer into a separate process/container, crash it before offset commit, and verify redelivery with zero duplicate sink effects.
10. **External side effects:** insert into a table with a unique `event_id`, induce redelivery, and prove multiple deliveries produce one business outcome.
11. **Rolling deployment:** in a lab namespace, scale 1 → 2 → 1 replicas and measure rebalance latency, lag, and recovery time.
12. **Static membership:** on a StatefulSet, assign unique static IDs, perform a brief restart, and compare against dynamic membership without assuming all rebalances disappear.
13. **Poison record:** send a record that always fails listener validation, configure DLT/recovery policy, and contrast single-partition lag with rebalance lag.
14. **Operations report:** tabulate each run with trigger, member/partition counts, ownership transfer time, before/after lag, distinct events, duplicate attempts, and business outputs.

## 20. Summary

**Simulating rebalances** reveals what unit tests calling `@KafkaListener` directly can never show: **how partition ownership actually shifts when consumer members join, leave, or fail**. With Spring Kafka, `@EmbeddedKafka`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer.getAssignedPartitions()`, and rebalance callbacks provide a clear, repeatable lab without touching production.

A rebalance does not mean data loss, yet **ownership handoff windows** can increase lag and redeliver uncommitted records. Trustworthy verification measures **assignments, offset progress, processed records, and sink idempotency** together—distinguishing graceful shutdowns from crashes, eager from cooperative modes, and Kafka transactions from external systems. When tested and monitored properly, rolling deployments and consumer scaling become predictable and safe to recover.
