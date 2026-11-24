# Testing Rebalances in Spring Kafka: Consumer Group Reliability Testing

## 1. Goals and problem statement

In an event-driven system using Apache Kafka, Spring Kafka typically runs multiple consumer instances under the same `group.id` to share load. When a new instance joins, an instance stops, a consumer misses heartbeats, or a topic's partition count changes, Kafka can perform a **consumer group rebalance**: revoking and redistributing partition ownership.

In development, a single `@KafkaListener` can run smoothly for hours. Yet once deployed to Kubernetes and scaled from two replicas to three, the system may suddenly experience duplicate record processing, rising consumer lag, failed offset commits, or stalled partitions. These issues often appear **right at the moment partition ownership changes**.

The **"Testing Rebalances"** lesson in the **Reliability Testing** chapter of **Spring Kafka Reliability Operations** focuses on verifying application behavior when consumer group membership changes.

After this lesson, you will be able to:

1. Explain rebalances, partition assignment, revocation, and their relationship to `group.id`.
2. Distinguish planned rebalances when members join/leave from disconnects, process crashes, and exceeding `max.poll.interval.ms`.
3. Use `spring-kafka-test` and an embedded Kafka broker to build a controlled rebalance integration test.
4. Verify that all partitions are assigned, no two stable members own the same partition, and data continues to be consumed after membership changes.
5. Test offsets, retries, business handler idempotency, and the limits of at-least-once guarantees.
6. Observe `onPartitionsAssigned`, `onPartitionsRevoked` callbacks, and lost-partition scenarios.
7. Avoid flaky tests caused by assuming partition order, fixed sleeps, shared group IDs, or waiting on the wrong event.
8. Design tests for rolling deployments, scaling up/down, slow processing, and crashes using appropriate infrastructure.

Examples use Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka broker, and JUnit 5. API names or group protocol strategies may vary across Kafka/Spring Kafka versions; the examples below state test environment assumptions explicitly.

## 2. What is a rebalance?

A consumer group can contain one or more consumers sharing a `group.id`. For a multi-partition topic, Kafka assigns each partition to **at most one member in the same group at a time once the group state stabilizes**. One consumer can own multiple partitions; if there are more consumers than partitions, some consumers receive no partitions.

Example topic `orders.events` with four partitions:

```text
Before scaling:
  Consumer group: order-processors

  Member A
    ├── orders.events-0
    ├── orders.events-1
    ├── orders.events-2
    └── orders.events-3

After Member B joins:
  Member A                      Member B
    ├── orders.events-0           ├── orders.events-2
    └── orders.events-1           └── orders.events-3
```

Exact distribution depends on the assignor, subscriptions, and metadata; Kafka does not guarantee splitting 0,1 to A and 2,3 to B as shown in the diagram every time. What must be verified is **full partition coverage**, zero overlap once assignments stabilize, and continued application processing.

### Events that typically trigger a rebalance

| Situation | Real-world example | Testing implication |
| --- | --- | --- |
| Member added | Scaling replicas up or increasing consumer threads in same group | Partitions may move from old members to new members |
| Planned member leave | Rolling deploy calling `stop()` and graceful shutdown | Partitions are returned to the group relatively quickly |
| Consumer crash | Container killed, JVM loses network | Coordinator detects lost member via heartbeat/session timeout or matching group protocol |
| Poll loop blocked too long | Synchronous processing exceeds `max.poll.interval.ms` | Consumer may be evicted from group and lose ownership |
| Subscription/topic change | Adding topics, changing regex subscription | Assignments are recomputed |
| Partition count change | Topic scaled from 4 to 8 partitions | Assignments must cover the new partitions |
| Coordinator/group protocol state change | Broker/coordinator failover, group protocol transitions | Consumers must recover after a brief instability period |

**Not every configuration change triggers a rebalance.** For example, calling `pause()` on a consumer container only pauses polling/delivery within the container; it does not mean the consumer left the group. Pause/resume tests do not substitute for rebalance tests.

## 3. Concepts needed for accurate assertions

- **Group member**: a consumer managed by the coordinator inside a consumer group.
- **TopicPartition**: a pair of topic name and partition number, e.g., `orders.events-2`.
- **Assigned partitions**: the set of partitions a member is currently permitted to consume.
- **Revoked partitions**: partitions a consumer is handing over/returning to the group via callbacks.
- **Lost partitions**: partitions whose ownership the consumer lost, potentially without running the normal revoke path.
- **Offset**: a record's position in a partition; each partition has its own offset sequence.
- **Committed offset**: the next position saved for the group, typically used as the starting point when another member takes over.
- **Consumer position**: a running consumer's next read position, not necessarily immediately synced with the committed offset.
- **Lag**: the difference between the topic's end position and the consumed/committed position as defined by your monitoring system.

In a test, do not just assert "consumer B has started." A consumer can be running while holding zero partitions or still waiting for assignment.

Nor should receiving the right count of records in a single run be treated as proof of zero duplicates under all crash scenarios. Under at-least-once delivery, executing business side effects before committing offsets can cause records to be redelivered after a rebalance.

## 4. Key invariants to test

For a group consuming a four-partition topic with two active members, verify:

| Invariant | Appropriate assertion | What to avoid assuming |
| --- | --- | --- |
| Partition coverage | Union of members' assignments equals all 4 partitions | Do not hard-code partition 0 always belonging to A |
| No overlapping ownership when stable | Intersection of assignment sets is empty | Do not assert during transitional phases |
| New consumer can take work | After joining, B receives at least one partition (given matching data/assignor) | Do not assert only `isRunning()` |
| Leaving member does not stall partitions | When B stops, A regains all partitions | Do not confuse graceful stop with a crash |
| Data continues to be processed | Publish events after rebalance, receive all business keys | Do not rely solely on assign callbacks |
| Offsets can recover | After commit and handoff, new events are read; old events are not skipped outside policy | Do not assume exactly-once by default |
| Business outcome stays accurate on redelivery | Business sink has idempotency keys or version checks | Do not treat total callback count as unique business count |
| Reasonable time bounds | Wait with timeout until assignments stabilize | Do not call `Thread.sleep(5000)` and guess the group settled |

Invariants should be verified at **the point where the group has stabilized**. During a rebalance, callbacks and assignments on each member can update at slightly different times. Tests must wait for the desired final condition rather than taking an arbitrary snapshot.

## 5. How eager vs. cooperative rebalances affect tests

Kafka supports multiple partition assignment strategies. Two styles to understand:

**Eager rebalancing:** a rebalance may require members to give up all assignments before receiving new ones. The application may pause processing more broadly.

**Cooperative/incremental rebalancing:** some partitions stay with their previous owner; only partitions that need to move are revoked across one or more rounds. This can reduce disruption during membership changes.

Example consumer configuration using the cooperative assignor:

```properties
spring.kafka.consumer.properties.partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

When using this strategy, **do not assert that every partition on A is revoked** whenever B joins. Only a subset may change hands.

Beyond assignors, newer Kafka releases introduce changes to the **consumer group protocol** and broker-side assignment strategies. Tests should record the Kafka broker version, consumer client version, protocol, and assignor in use. You cannot infer the exact callback sequence for every configuration from a single diagram.

### Meaning of callbacks

In Spring Kafka, `ConsumerAwareRebalanceListener` lets you observe:

- `onPartitionsAssigned(Consumer, partitions)`: callback when partitions are assigned.
- `onPartitionsRevokedBeforeCommit(Consumer, partitions)`: callback before revocation-related commits in the container lifecycle.
- `onPartitionsRevokedAfterCommit(Consumer, partitions)`: callback after revocation-related commits.
- Lost-partition callbacks when supported by the API version: distinguish controlled revocation from lost ownership.

Never make a callback the sole test assertion. To verify who owns partitions at the end of a rebalance, read assignment state from the containers or appropriate consumer metrics.

## 6. Choosing the right test level: unit, embedded broker, Testcontainers, and staging

Not every test needs a three-broker cluster. Picking the right layer keeps tests fast and meaningful.

| Layer | Purpose | Limitations |
| --- | --- | --- |
| Listener/handler unit test | Verify logic on assigned/revoked callbacks, local state cleanup, idempotent handlers | Does not simulate the coordinator or real rebalances |
| Embedded Kafka integration test | Starts a real broker inside the test JVM, forms groups, joins/leaves, sends and receives messages | Does not fully simulate network/container/independent-process faults |
| Testcontainers or dedicated test cluster | Runs a broker and multiple independent consumer processes/containers; kills, restarts, network failures | Slower and requires Docker/appropriate infrastructure |
| Staging/chaos tests | Rolling deploys, autoscaling, coordinator disruption, real lag and alerts | Resource-intensive; not suited as per-commit unit tests |

The first hands-on example uses an **embedded broker** to verify rebalances on planned member joins and leaves. Crash and missed-heartbeat scenarios are separated because they need different fault-injection mechanisms.

## 7. Dependencies for integration tests

Gradle project example using Spring Boot 3.x with Spring Boot-managed dependency versions:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Components:

- `spring-kafka`: listener containers, KafkaTemplate, consumer factories.
- `spring-kafka-test`: `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils`, and `ContainerTestUtils`.
- `spring-boot-starter-test`: JUnit 5, AssertJ/Mockito, and version-matched test utilities.
- `awaitility`: waits on asynchronous conditions with timeouts instead of fixed `Thread.sleep`.

You can use `@SpringBootTest` when testing your application's actual `@KafkaListener` configuration. The test below uses `@SpringJUnitConfig` and creates listener containers directly to control members A and B explicitly without interference from other listeners in a Spring Boot context.

## 8. Test model explicitly creating two group members

Assume a test topic with four partitions:

```text
Embedded Kafka broker
  Topic: orders.rebalance.it
  Partitions: 0, 1, 2, 3

Group: rebalance-it-group
   |
   +-- Container A
   |     concurrency = 1
   |     groupId = rebalance-it-group
   |
   +-- Container B
         concurrency = 1
         groupId = rebalance-it-group
```

Test sequence:

1. Start A and wait for A to be assigned all four partitions.
2. Start B and wait for both A and B to be assigned partitions.
3. Verify total assignments cover all four partitions and the two members do not overlap.
4. Publish one event directly to each partition and verify they are processed.
5. Stop B and wait for A to regain all four partitions.
6. Publish another event and verify the application keeps consuming.
7. Stop containers and destroy the producer in `finally`.

Using four partitions lets both members receive work without relying on a specific distribution order.

## 9. Sample rebalance integration test with Spring Kafka

This is a self-contained test using Spring Kafka 3.x, JUnit 5, and Awaitility. To focus on group assignment, it constructs `ConcurrentMessageListenerContainer` directly rather than an auto-starting `@KafkaListener`.

```java
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = RebalanceIntegrationTest.Config.class)
@EmbeddedKafka(
    partitions = 4,
    topics = "orders.rebalance.it"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RebalanceIntegrationTest {

    private static final String TOPIC = "orders.rebalance.it";
    private static final String GROUP = "rebalance-it-group";

    @Autowired
    EmbeddedKafkaBroker broker;

    @Configuration
    static class Config {
    }

    private ConcurrentMessageListenerContainer<String, String>
    newMember(
            ConsumerFactory<String, String> consumerFactory,
            String memberName,
            ConcurrentMap<String, String> receivedBy,
            List<String> transitions) {

        ContainerProperties properties =
            new ContainerProperties(TOPIC);

        properties.setGroupId(GROUP);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        properties.setMessageListener(
            (MessageListener<String, String>) record ->
                receivedBy.put(record.key(), memberName)
        );

        properties.setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {

                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    transitions.add(
                        memberName + ":ASSIGNED:" + partitions
                    );
                }

                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    transitions.add(
                        memberName + ":REVOKED:" + partitions
                    );
                }
            }
        );

        ConcurrentMessageListenerContainer<String, String> container =
            new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties
            );

        container.setBeanName(memberName);
        container.setConcurrency(1);
        return container;
    }

    private static Set<TopicPartition> assigned(
            ConcurrentMessageListenerContainer<?, ?> container) {

        Collection<TopicPartition> current =
            container.getAssignedPartitions();

        return current == null
            ? Set.of()
            : Set.copyOf(current);
    }

    @Test
    void reassignsPartitionsOnJoinAndLeave()
            throws Exception {

        Map<String, Object> consumerProps =
            new HashMap<>(
                KafkaTestUtils.consumerProps(
                    GROUP, "false", broker
                )
            );

        consumerProps.put(
            "auto.offset.reset", "earliest"
        );

        DefaultKafkaConsumerFactory<String, String> consumerFactory =
            new DefaultKafkaConsumerFactory<>(
                consumerProps,
                new StringDeserializer(),
                new StringDeserializer()
            );

        DefaultKafkaProducerFactory<String, String> producerFactory =
            new DefaultKafkaProducerFactory<>(
                KafkaTestUtils.producerProps(broker),
                new StringSerializer(),
                new StringSerializer()
            );

        KafkaTemplate<String, String> producer =
            new KafkaTemplate<>(producerFactory);

        ConcurrentMap<String, String> receivedBy =
            new ConcurrentHashMap<>();

        List<String> transitions =
            new CopyOnWriteArrayList<>();

        ConcurrentMessageListenerContainer<String, String> a =
            newMember(
                consumerFactory, "A", receivedBy, transitions
            );

        ConcurrentMessageListenerContainer<String, String> b =
            newMember(
                consumerFactory, "B", receivedBy, transitions
            );

        try {
            // Initially the group has only member A.
            a.start();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertEquals(4, assigned(a).size())
                );

            // Member B joins; Kafka redistributes partitions.
            b.start();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    Set<TopicPartition> pa = assigned(a);
                    Set<TopicPartition> pb = assigned(b);

                    assertFalse(pa.isEmpty());
                    assertFalse(pb.isEmpty());
                    assertTrue(Collections.disjoint(pa, pb));

                    Set<TopicPartition> all =
                        new HashSet<>(pa);

                    all.addAll(pb);
                    assertEquals(4, all.size());
                });

            // Send one message directly to each partition.
            for (int partition = 0; partition < 4; partition++) {
                String key = "after-join-" + partition;

                producer.send(
                    TOPIC, partition, key, "payload"
                ).get(10, TimeUnit.SECONDS);
            }

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    for (int partition = 0; partition < 4; partition++) {
                        assertTrue(
                            receivedBy.containsKey(
                                "after-join-" + partition
                            )
                        );
                    }
                });

            // B leaves the group gracefully.
            b.stop();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertEquals(4, assigned(a).size())
                );

            producer.send(
                TOPIC, 3, "after-leave", "payload"
            ).get(10, TimeUnit.SECONDS);

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertTrue(
                        receivedBy.containsKey("after-leave")
                    )
                );

            assertTrue(
                transitions.stream()
                    .anyMatch(t -> t.startsWith("B:ASSIGNED:"))
            );

        } finally {
            if (b.isRunning()) {
                b.stop();
            }

            if (a.isRunning()) {
                a.stop();
            }

            producerFactory.destroy();
        }
    }
}
```

### What did the test prove?

- A real Kafka broker and a consumer group participated in the group protocol.
- A received all partitions when running alone.
- B joined and the group settled into a two-owner state with non-overlapping assignments once the wait condition held.
- After assignment, the producer sent messages to all four partitions and the handlers received their keys.
- When B stopped cleanly, A regained all partitions and continued processing new messages.

### What did the test not prove yet?

- Did not simulate a process crash or network loss; `b.stop()` is a **graceful leave**.
- Did not measure exact failover duration on heartbeat timeout.
- Did not verify end-to-end exactly-once.
- Did not verify business handler side effects because the example only records keys in a `ConcurrentHashMap`.
- Did not test a specific production `@KafkaListener`.
- Does not guarantee callbacks appear in the exact same order across every assignor and Kafka protocol.

**Note:** `receivedBy.put(key, memberName)` overwrites how many times a key was delivered. It only verifies **that the event was consumed**. To check for duplicates, use a per-key counter or a business table with an idempotency key.

## 10. Why use Awaitility instead of Thread.sleep?

Rebalancing is asynchronous: a member must start, subscribe, poll, coordinate with the group coordinator, and receive its assignment. Duration depends on CPU, the test broker, and CI runners.

Tests easily turn flaky when using:

```java
b.start();
Thread.sleep(3000);
assertEquals(2, assigned(a).size());
```

There are two problems:

1. Three seconds can be too short on slow CI or unnecessarily slow locally.
2. Exactly `2` is not always the right condition in another topology; assignment policies can differ from rigid expectations.

A better approach:

```java
b.start();

await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> pa = assigned(a);
        Set<TopicPartition> pb = assigned(b);

        assertFalse(pa.isEmpty());
        assertFalse(pb.isEmpty());

        Set<TopicPartition> all = new HashSet<>(pa);
        all.addAll(pb);

        assertTrue(Collections.disjoint(pa, pb));
        assertEquals(4, all.size());
    });
```

The test waits on **the condition the system must reach**, with a finite timeout. On timeout, reporting the final assignments of A and B makes debugging far clearer than a bare assertion failure after a sleep.

Avoid timeouts of a few hundred milliseconds on CI. Also avoid overly long timeouts that take minutes to catch a real bug. A range of 20–60 seconds is usually a sensible starting point for embedded group tests, tuned to your environment and startup times.

## 11. Observing rebalances when using @KafkaListener

In real applications, consumers are usually created via `@KafkaListener`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "order-events-listener",
        topics = "orders.events",
        groupId = "order-processors",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        // Business processing using record.key() and record.value().
    }
}
```

To observe assignments of a specific listener, retrieve its container from `KafkaListenerEndpointRegistry`:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("order-events-listener");
```

`registry` assumes an injected `KafkaListenerEndpointRegistry` bean. You can use `container.start()`/`stop()` in tests to control a listener's lifecycle. However, to test two members in the same group, you need **two actual consumers**—such as two independent containers, two listener instances with the same `groupId`, or two application instances.

Watch out: the `@KafkaListener` `id` is the endpoint/container ID. When a listener does not specify `groupId` explicitly, the `id` attribute can affect the group ID under annotation rules. In rebalance tests, always specify `groupId` explicitly so you never accidentally create two different groups.

### Registering ConsumerAwareRebalanceListener on the container factory

Example factory configuration with observation callbacks:

```java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderKafkaContainerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(
            OrderKafkaContainerConfiguration.class
        );

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    orderKafkaContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);

        factory.getContainerProperties()
            .setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        log.info(
                            "event=kafka.partitions.assigned partitions={}",
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        log.info(
                            "event=kafka.partitions.revoked partitions={}",
                            partitions
                        );
                    }
                }
            );

        return factory;
    }
}
```

Listeners using this factory must declare `containerFactory="orderKafkaContainerFactory"`. The example shows how to observe the lifecycle; not every application needs to log detailed partition lists at `INFO` continuously. When a group has many topics/partitions and frequent rebalances, control log volume.

**Do not perform slow work, call APIs with long timeouts, or wait on arbitrary locks inside rebalance callbacks.** Callbacks run on the poll/consumer thread; blocking there stalls the group and can trigger further rebalances.

## 12. Offsets are central to reliability during a rebalance

Suppose a partition holds records at offsets 100, 101, 102. Consumer A receives 100 and updates the database, then the process terminates before the corresponding offset commits.

```text
Partition 0:  ... 100 101 102 ...

Consumer A:
  poll offset 100
  process and write business DB -> COMMITTED
  Kafka offset 101 not yet committed
                |
                X process crash
                |
                v
Consumer B takes Partition 0:
  reads from old committed offset
  may receive offset 100 again
```

That is why **at-least-once delivery can lead to duplicate processing**. Rebalancing does not automatically create exactly-once semantics in external databases or APIs.

### Offsets to distinguish

| Value | Meaning |
| --- | --- |
| `record.offset()` | Offset of the record currently being processed |
| Consumer position | Next read position of the consumer in the current session |
| Committed offset | Next offset persisted for the group |
| End offset | Current end position of the partition |
| Business processed key | Record of which side effects the application has already completed |

Do not equate "the consumer received the message" with "the offset committed." Receiving a record, finishing the handler, committing the business transaction, and committing the Kafka offset are distinct events.

### AckMode and auto-commit

In the test example, `KafkaTestUtils.consumerProps(GROUP, "false", broker)` disables auto-commit; the container sets `AckMode.RECORD` so the container manages commits per record lifecycle.

In Spring Kafka, review these settings:

- `enable.auto.commit` on the Kafka consumer.
- `ContainerProperties.AckMode` on the listener container.
- Manual acknowledgment usage, if any.
- Transaction manager/Kafka transactions, if used.
- Error handler, retry topics/DLT, and seek/recover behavior.

Do not mix auto-commit, manual ack, and transactions unintentionally. Each model has different confirmation boundaries.

## 13. Testing zero data loss across ownership handoff

An integration test should send multiple records to **each partition**, trigger a rebalance, and verify every business key is ultimately processed.

Example sending one record to a specific partition:

```java
for (int partition = 0; partition < 4; partition++) {
    producer.send(
        "orders.rebalance.it",
        partition,
        "event-" + partition,
        "payload"
    ).get(10, TimeUnit.SECONDS);
}
```

When verifying an entire 100-record batch, use a unique business key such as `orderId + eventVersion` and a result store queryable by key.

Appropriate assertions:

1. Every published key appears successfully in the output within the deadline.
2. Once the group stabilizes, each partition has one final owner.
3. When a member stops, its partitions move to another member.
4. Under at-least-once, if the test intentionally creates a failure window around commit, duplicate handler calls may occur while **business outputs stay accurate** via idempotency.
5. No partition exhibits continuously growing lag after the group stabilizes.

This contrasts with an overly strict assertion:

```java
assertEquals(100, callbackInvocationCount.get());
```

If a test genuinely simulates a crash/rollback around commit, 100 unique business events can produce more than 100 callback invocations. Callback count is not valid business side-effect count. Assert business keys or final data state instead.

## 14. Testing idempotent processing around rebalances

A practical approach is for the writer to guard results with a **business idempotency key**. For events carrying an `eventId` and version:

```sql
CREATE TABLE processed_kafka_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

The application processes inside a database transaction:

```java
@Transactional
public void applyOrderEvent(OrderEvent event) {
    int inserted = jdbc.update(
        """
        INSERT INTO processed_kafka_event (
            consumer_name, event_id
        )
        VALUES (?, ?)
        ON CONFLICT (consumer_name, event_id)
        DO NOTHING
        """,
        "order-projection",
        event.eventId()
    );

    if (inserted == 0) {
        // This event was already applied successfully.
        return;
    }

    jdbc.update(
        """
        INSERT INTO order_projection (
            order_id, current_status
        )
        VALUES (?, ?)
        ON CONFLICT (order_id)
        DO UPDATE SET
            current_status = EXCLUDED.current_status
        """,
        event.orderId(),
        event.status()
    );
}
```

This code assumes `JdbcTemplate jdbc`, the `OrderEvent` model, the `order_projection` table, and an appropriate JDBC transaction manager. SQL syntax targets PostgreSQL. Within one transaction, the dedup marker insert and projection update commit or roll back together on one datasource.

**Watch out for event ordering and version monotonicity.** If an older event replays after a newer event, an unconditional upsert can regress state. For projections requiring ordering/versioning, add `eventVersion` and update only when the incoming version is newer; a duplicate-marker alone only solves part of the problem.

### Testing the failure window between business commit and offset commit

To verify true idempotent design, a test can:

1. Have consumer A receive event X.
2. Let the DB transaction process X and commit.
3. Terminate the process/consumer **before X's Kafka offset commits**.
4. Let member B take over the partition.
5. Confirm X can be redelivered.
6. Verify the `processed_kafka_event` table holds only one valid marker and the projection was not applied twice.

Step 3 requires fault injection at the exact boundary; **calling `container.stop()` arbitrarily after a `Thread.sleep` cannot guarantee it**. A graceful stop can wait for the handler to finish and commit offsets before leaving the group.

Use an independent consumer process/container and kill the process, paired with a signaled gate/fault-injection point in the test harness. The test must prove the committed offset actually stayed at the prior position before expecting replay.

## 15. Testing graceful leave vs. consumer crash

Two frequently confused scenarios:

### Graceful leave

```text
Member B running
      |
      v
container.stop()
      |
      v
Controlled close/leave group
      |
      v
Coordinator redistributes partitions
      |
      v
Member A takes over
```

Benefits of this test:

- Evaluates normal rolling deployments.
- Verifies revoke/assign callbacks.
- Verifies container cleanup and continued consumption after shutdown.
- Runs fast inside embedded integration tests.

However, a graceful leave does not accurately represent **power loss, SIGKILL, or complete network loss**.

### Crash or lost heartbeat

```text
Member B running
      |
      X process lost / connection dropped
      |
      v
Coordinator waits to detect membership failure
      |
      v
Member B loses ownership
      |
      v
Member A is assigned partitions
      |
      v
Uncommitted records may be re-read
```

Tests need Testcontainers, an independent process, or a staging environment capable of process kills/network partitions. Observe the actual session timeout and group protocol in use; do not assume every Kafka release uses the exact same timeout formula.

### Expectation matrix

| Scenario | How to trigger | What matters |
| --- | --- | --- |
| Join | Start B in same group | Assignments split, processing continues |
| Leave | Stop B cleanly | A takes over, no stalled partitions |
| Crash | Kill process B without graceful close | Timeout/failover, replay, and idempotency |
| Network partition | Block connectivity between B and broker | Membership loss detection, reconnect behavior |
| Poll timeout | Block processing beyond max poll interval cleanly | Lost assignment, commit failure/recovery, processing outcome |
| Scale down | Reduce replica count | Lag stabilizes again, zero dropped records |
| Rolling upgrade | Replace multiple members sequentially | Minimal disruption per strategy, zero corrupted data |

## 16. Testing slow processing and max.poll.interval.ms

A Kafka consumer must call `poll()` frequently enough. If synchronous batch processing takes too long and fails to return to poll within the limit, the group can treat the member as unable to make progress.

Common properties to understand:

```properties
spring.kafka.consumer.properties.max.poll.interval.ms=300000
spring.kafka.consumer.properties.session.timeout.ms=45000
spring.kafka.consumer.max-poll-records=500
```

These values are **configuration examples**, not recommendations to copy verbatim for every workload. How session timeouts and heartbeats behave depends on the group protocol and Kafka version. Newer Kafka versions may manage timeouts differently from the classic group protocol.

A test can use a mock message listener waiting on a `CountDownLatch`:

```java
CountDownLatch handlerEntered = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

MessageListener<String, String> slowHandler = record -> {
    handlerEntered.countDown();

    boolean released;
    try {
        released = releaseHandler.await(
            20, TimeUnit.SECONDS
        );
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Handler interrupted", ex
        );
    }

    if (!released) {
        throw new IllegalStateException(
            "Controlled test timeout"
        );
    }
};
```

To test `max.poll.interval.ms`, use a **short threshold suited to the test environment**, avoiding thresholds so tiny that slow CI runners evict the member immediately. After confirming the handler entered via `handlerEntered.await(...)`, hold it long enough to trigger the target condition, observe assignments, and release in `finally`.

In Spring Kafka, the container can use pausing to keep polling during asynchronous listener handling; thus you must understand how the real application consumes and acknowledges. Never assume every slow handler always triggers a rebalance.

### What not to do

- Do not block a test thread indefinitely.
- Do not rely strictly on `Thread.sleep()` to hit exact callback timing.
- Do not shrink timeouts until tests fail flakily on CI machines.
- Do not call real network APIs from listener callbacks when only simulating latency/failure.
- Do not confuse `max.poll.interval.ms` with `session.timeout.ms` — one governs poll progress, while the other governs detecting a member unresponsive to group heartbeats/protocol.

## 17. Rebalances and per-key ordering

Kafka guarantees record ordering **within a single partition** by offset when read sequentially; it does not guarantee a global order across partitions.

If records with the same `orderId` are produced with a consistent key and partitioner, they typically land in the same partition (assuming consistent partition count and partitioner config). When a partition changes owners on rebalance, the new member resumes from the group's committed offset.

Yet effective ordering at the business sink also depends on:

- Whether retry/seek reintroduces an older record into processing.
- Whether the handler processes asynchronously and acknowledges before work truly finishes.
- Whether failed records move to a retry topic, altering order relative to the main topic.
- Whether events carry versions to prevent older state from overwriting newer state.
- Whether producers changed keys, partition counts, or partitioners between publishes.

### Simple ordering test

Send sequentially to the same partition:

```text
order-42 version 1
order-42 version 2
order-42 version 3
```

Let consumer A consume part of them, then add B or transfer ownership cleanly. Finally verify the business projection never regressed in version and reflects every required version.

If the goal is verifying **strict processing order**, the handler should record the sequence of offsets/versions per partition; never rely on log timestamps across multiple threads, because log lines can interleave.

## 18. Testing with retries, DLTs, and error handlers

In systems with business or infrastructure failures, a rebalance can happen while a container is retrying a record or routing to a DLT.

Mechanisms to distinguish:

- `DefaultErrorHandler` with bounded seek/retry inside the listener container.
- Non-blocking retries via retry topics, if used by the application.
- Dead-letter publishing via `DeadLetterPublishingRecoverer`.
- Kafka transactions and offset commit boundaries.
- Manual acknowledgment and unacknowledged record state.

A valuable test scenario:

1. A is processing record X; the handler throws a transient error.
2. Before or during retry, B joins the group.
3. The partition holding X may change ownership.
4. X is ultimately processed successfully or routed to the DLT per configured policy.
5. The system neither loops infinitely, drops messages, nor creates duplicate side effects.

**Do not assume routing X to the DLT means business event X succeeded.** The DLT is a quarantine/audit channel for failures. Tests should check output state, retry counts, the DLT record, and committed offsets.

With Spring Kafka and Kafka transactions, exactly-once has bounded scope: consume-transform-produce operations inside a Kafka transaction coordinate with offset commits, whereas HTTP or database calls outside Kafka do not automatically gain exactly-once. Add idempotency/outbox or dedicated coordination mechanisms.

## 19. Static membership, cooperative assignors, and rolling deployments

Some systems use static membership via `group.instance.id` to reduce unnecessary rebalances when the same member restarts quickly.

Concept:

```text
Dynamic membership:
  a member leaving and returning usually gets a new
  identity treated as a new session by the coordinator.

Static membership:
  a member has a stable group.instance.id,
  so the coordinator can recognize the same logical member.
```

Static membership does not eliminate all rebalances and can slow down takeover in some crash cases because the coordinator waits for the timeout. In tests, configure a unique ID per live member; two consumers sharing the same `group.instance.id` can cause fencing or membership errors.

For rolling deployments:

- Record when member A stops.
- Identify partitions reassigned to B/C.
- Track consumer lag and recovery duration.
- Confirm zero duplicate side effects in business data.
- Repeat with a member killed rather than stopped cleanly.

Choosing cooperative assignment, static membership, and optimal shutdown grace periods should be based on real measurements. Do not crank up every timeout just to make tests "pass," as that can lengthen crash recovery time.

## 20. Observing rebalances through logs and metrics

To investigate after tests, log messages should connect **group, member, topic, partition, and timestamp**.

Example:

```text
INFO event=kafka.member.started group=order-processors member=pod-A
INFO event=kafka.partitions.assigned group=order-processors member=pod-A partitions=[orders.events-0,orders.events-1]
INFO event=kafka.partitions.revoked group=order-processors member=pod-A partitions=[orders.events-1]
INFO event=kafka.partitions.assigned group=order-processors member=pod-B partitions=[orders.events-1]
INFO event=kafka.message.handled group=order-processors partition=1 offset=321 eventId=evt-42
```

Useful fields:

| Field | Role |
| --- | --- |
| `groupId` | Group undergoing rebalance |
| `memberName` or instance ID | Processing node/container |
| `topic` and `partition` | Partition ownership |
| `event` | Assigned/revoked/lost/handled/committed |
| `offset` | Record position |
| `eventId` | Correlation to business outcome |
| `timestamp` | Analyzing processing pauses |
| `exceptionType` | Commit, poll, handler, or coordinator errors |
| `lag` | Consumption delay per defined metric |

Important metrics may include:

- Consumer group rebalance count over a time window.
- Rebalance duration and time without progress.
- Consumer lag before, during, and after rebalance.
- Number of partitions currently assigned per member.
- Commit failure/retry frequency.
- Record processing time and poll loop latency.
- Unique business events processed and duplicate delivery counts.

Specific metrics depend on the Kafka client, Micrometer, and instrumentation setup; do not assume every metric name appears automatically just because Spring Kafka is present. Some metrics such as per-partition ownership must come from containers, Kafka AdminClient, or metric exporters.

**Never use per-message event IDs as time-series metric labels** if you want to avoid cardinality explosions. Event IDs belong in logs, traces, or audit tables.

## 21. Causes of flaky rebalance tests

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Test times out waiting for assignment | Broker not ready or consumer not polling yet | Wait on real conditions, raise timeout sensibly, inspect broker logs |
| A keeps all four partitions after B.start | B has not joined the right group or has a different group ID | Check `group.id`, subscription, container state |
| Neither member gets partitions | Missing topic, metadata not ready, misconfiguration | Pre-create topic, inspect startup/consumer errors |
| Test demands A always gets partitions 0,1 | Assignment depends on assignor | Assert union, disjointness, and non-emptiness |
| Revoke callback fires multiple times | Multiple assignment rounds / cooperative strategy | Do not assert "exactly once" without basis |
| Expected revoke callback not seen | Listener unregistered, different group protocol, different callback | Check wiring and observe final assignments |
| Stop() fails to reproduce duplicates | Graceful shutdown commits offsets | Use process kill/fault injection to test crashes |
| Old events from prior test appear | Reused group ID/topic/offset or shared broker | Isolate group IDs/topics, clean up context |
| `auto.offset.reset=latest` causes test to miss events | Producer sent before consumer received assignment | Use earliest for tests or send after assignment |
| `@KafkaListener` auto-starts unexpectedly | Context creates extra uncontrolled consumers | Disable auto-startup or test isolated containers directly |
| Test passes locally but fails in CI | Different thread scheduling, startup speed, CPU | Awaitility, timeouts, resource limits, diagnostics |
| Topic has only one partition | Second member gets no partitions | Provision more partitions than members under test |
| `max.poll.interval.ms` too low | Test environment slower than expected | Tune threshold and use accurate signals |
| Records missing after rebalance | Consumer uncommitted, error handler retrying or paused | Check committed offsets, assignments, pauses, logs |
| Asserting callback count equals published count | Redelivery/retry increases callbacks | Assert unique business keys |
| Ordering test fails even though Kafka preserves per-partition order | Async handler/retry topic changed business ordering | Test per partition/version and processing policy |
| Duplicates appear in DB | Side effect committed before Kafka offset | Unique keys, idempotency markers, transactional design |
| Repeated test runs leave lingering containers | Missing `finally` cleanup, unclosed context | Stop containers and destroy producers |
| Static member fenced | Duplicate `group.instance.id` | Unique ID per live member |
| Lag spikes after rebalance | Member unassigned, backpressure, or slow writer | Measure poll, DB latency, assignments, and queues |

## 22. Reliability test matrix you can adopt for projects

To turn this lesson into a systematic test suite:

| Test ID | Scenario | Assignment expectation | Data expectation |
| --- | --- | --- | --- |
| RB-01 | Single member starts | A receives all partitions | Subsequent events processed |
| RB-02 | Member B added | A/B share partitions without overlap | Zero lost events |
| RB-03 | B stopped cleanly | A regains all partitions | Continues processing new events |
| RB-04 | Stop A while B runs | B takes over A's partitions | Zero lost events; accurate output |
| RB-05 | Two members start nearly together | Group stabilizes | Zero duplicate side effects |
| RB-06 | Kill consumer process | Coordinator detects lost member | Replay handled idempotently |
| RB-07 | Processing exceeds poll interval | Member may lose ownership | Clear recovery behavior |
| RB-08 | Retry during join | Assignments change per policy | Record processed or DLTed as expected |
| RB-09 | Same key sent to one partition | Ownership shifts on rebalance | Business version/order accurate |
| RB-10 | Scale 1 → 2 → 3 → 1 | Reassignments drop zero partitions | Unique business event total accurate |
| RB-11 | Cooperative assignor | Only needed partitions move | Do not enforce full revoke |
| RB-12 | Static membership restart | Member returns with valid identity | Recovers per timeout/protocol |
| RB-13 | Topic partition count increases | Assignments cover new partitions | New events processed |
| RB-14 | Broker restart in lab | Consumers reconnect/rebalance | Recovers within designed SLA |
| RB-15 | Crash between DB commit and offset commit | Record can replay | Exactly one business effect |

RB-01 through RB-04 fit embedded brokers and container lifecycles. RB-06, RB-14, and RB-15 fit independent processes/containers or test infrastructure with targeted fault injection. Do not cram every scenario into one fast CI unit test; tiering keeps suites stable and easy to debug.

## 23. Recommendations for Testcontainers or standalone clusters

Embedded Kafka suffices for basic group coordination checks. When a **real crash** is needed, run consumers A and B in two separate JVMs/containers connected to the same test Kafka broker:

```text
Test runner
   |
   +-- Kafka broker/container
   |
   +-- Consumer application A/container
   |       group=order-processors-it
   |
   +-- Consumer application B/container
   |       group=order-processors-it
   |
   +-- Business DB test/container
```

Workflow:

1. Create the topic and verify the desired partition count.
2. Start A and wait for observable assignment.
3. Start B and confirm the rebalance stabilizes.
4. Publish data with known business keys and source offsets.
5. Inject the fault by killing a process or blocking the network at the test checkpoint.
6. Wait for the group to reassign partitions.
7. Reconcile database state and committed offsets.
8. Restart the member and confirm no duplicate side effects occur.
9. Clean up containers/topics/data after the test.

Fault-control options depend on the platform, such as Docker stop/kill, a network proxy, or orchestration APIs. **Stopping a container gracefully may still allow shutdown hooks to run**, so simulating a crash requires a forceful termination mechanism and verifying the producer/consumer process died.

You do not need a production cluster just to test RB-02. However, for SLA/failover requirements during broker outages, a single embedded broker cannot prove quorum, leadership, or replication behavior of a production cluster.

## 24. Common misconceptions about Kafka rebalances

### "B started means B has received partitions"

False. `isRunning()` reflects container lifecycle state; group partition assignment is asynchronous. Wait for assignment and/or message consumption.

### "Rebalances only happen when a member dies"

False. Scaling up/down, changing subscriptions, adding partitions, or coordinator changes can all trigger rebalances.

### "Increasing concurrency always speeds up processing"

No. If a topic has four partitions and you spawn eight consumer threads in the same group/subscription, some consumers receive zero partitions. Throughput also depends on CPU, DB, network, and rebalance overhead.

### "Any error log during a rebalance means lost messages"

False. Revoke/commit/retry logs can appear during handoff. Inspect committed offsets and business outputs before concluding data loss.

### "The same message is processed strictly once"

Not by default. Under at-least-once delivery and failures around commit, records can be redelivered. To keep business outcomes free of duplicates, use idempotency or appropriate transaction boundaries.

### "Stopping a listener cleanly fully simulates a crash"

False. A graceful stop usually gets a chance to finish processing and commit; a process crash can lose ownership without normal cleanup.

### "Every rebalance must revoke all partitions"

Not true with cooperative assignment. Only partitions that actually need to move may be revoked.

### "One consumer preserves order across the whole topic"

False. Kafka preserves ordering within each partition; parallel multi-partition processing has no global total order.

### "Checking assignment alone is enough"

False. Correct assignment does not prove handlers are unstuck, error handlers are not looping endlessly, or business data is free of duplicates. Test both liveness and business correctness.

## 25. Hands-on exercises

Build a Spring Kafka application processing `OrderStatusChanged` events with `eventId`, `orderId`, `version`, and `status`.

### Part A — Embedded integration test

1. Create a four-partition topic with `@EmbeddedKafka`.
2. Create two listener containers A and B sharing `group.id`.
3. Start A then B; log assigned/revoked events.
4. Verify the union of assignments covers all four partitions and their intersection is empty.
5. Publish 40 events across partitions and await all 40 unique event keys.
6. Stop B and wait for A to regain all partitions.
7. Publish 10 more events and verify the application keeps processing.

### Part B — Business idempotency

1. Create a `processed_event` table with a unique key on business event ID.
2. Within the same DB transaction, insert the marker and update order status.
3. Send the same event ID multiple times to simulate replay.
4. Verify the projection reflects only one application per event.
5. Add a version rule so older events cannot overwrite newer events.

### Part C — Crash and offsets

1. Run consumers in independent processes/containers.
2. Trigger a controlled crash after DB commit but before offset commit.
3. Let another consumer take over the partition.
4. Observe that the same offset/event can be re-read.
5. Verify business results are not duplicated.
6. Record the time from crash until consumption recovers.

### Part D — Advanced challenges

Try cooperative assignors, graceful rolling deploys, and increasing partition counts. Compare **partial revoke**, **full revoke**, **member lost**, and **no rebalance** cases. Explain which callbacks and metrics distinguish them.

Each scenario report should include: group ID, broker/client versions, assignor/protocol, partition count, member count, trigger sequence, before/after assignment sets, published event count, unique processed event key count, redelivery count, and recovery duration.

## 26. Conclusion

**Testing rebalances** in Spring Kafka does not stop at seeing consumers start and stop. A credible test must verify that the Kafka group actually transfers partition ownership, members continue consuming after changes, and business data stays accurate even when records are reprocessed around offset commit boundaries.

With **embedded Kafka**, you can test joins, graceful leaves, partition assignments, and data flow quickly and deterministically using Awaitility and partition-set assertions. For **process crashes, missed heartbeats, timeouts, network partitions, or failures right after business commits**, use container/cluster-level fault injection tests for accurate simulation. Regardless of tier, distinguish final assignments from transitional callbacks, committed offsets from processed records, and at-least-once delivery from business idempotency.

Combining a test matrix, group ownership logs/metrics, and output data verification lets Spring Kafka applications operate through scale-ups/downs, rolling deployments, and consumer failures without dropping work or corrupting business state.
