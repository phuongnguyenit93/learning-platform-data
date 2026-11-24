# Messaging — Cleaning Up Broker State, Offsets, and Resources After Each Test Group

## 1. Why doesn't "the test finished" mean the broker is clean?

In messaging tests, one test sends an `OrderCreated` event through Kafka and asserts the consumer received the exact payload. JUnit reports green. The next test also uses topic `orders` and group `order-processor` yet receives a leftover old record, or fails to receive the new record because the group already committed its offset during the previous run. Some tests also leave behind consumer threads, unacked AMQP queues, dead-letter messages, Kafka Streams state stores, listener containers, or connection pools after assertions finish.

There is nothing contradictory here: **brokers are stateful systems**, not Java mocks that live solely inside one method.

A messaging test group must distinguish at least four kinds of state:

1. **Message state:** Kafka records on partitions; RabbitMQ messages in queues/DLQs; JMS messages and durable subscriptions.
2. **Consumer progress:** Kafka group committed offsets; RabbitMQ acknowledgments/in-flight messages; JMS acknowledgments/session transactions.
3. **Broker metadata:** Kafka topics/partitions/group metadata, ACLs/configs, RabbitMQ exchanges/queues/bindings/vhosts, JMS destinations/subscriptions.
4. **Client/process resources:** producers, consumers, Spring listener containers, channels/connections, `AdminClient`, executors, Testcontainers containers, and the Spring `ApplicationContext` cache.

**Deleting messages alone does not mean consumer progress was reset.** Specifically in Kafka, **deleting a topic does not automatically erase all consumer-group offsets immediately**, and setting `auto.offset.reset=earliest` does not rewind a group that has already committed back to offset 0. If a valid committed offset remains, the consumer normally starts at that committed offset.

This lesson explains how to **clean up broker state, offsets, and resources after each test group**, using a runnable example in **Java 17 + Spring Boot 3.3 + Spring Kafka + Kafka Testcontainers + JUnit Jupiter**, and then extends to RabbitMQ and JMS. The goal is independent, repeatable tests that never corrupt shared broker data and never confuse cleanup with verifying business behavior.

## 2. What you will master after this lesson

After completing it, you will be able to:

1. Explain the difference between Kafka message logs, current consumer position, and committed group offsets.
2. Explain the exact effects of `group.id`, `auto.offset.reset`, `enable.auto.commit`, `commitSync`, and `seekToBeginning`.
3. Distinguish **creating a new consumer group**, **resetting offsets**, **deleting a consumer group**, and **deleting a topic** — they are not synonymous.
4. Design isolation for each `@Test`, test class, test suite, or CI run.
5. Structure `@BeforeEach`/`@AfterEach`/`@AfterAll` and `@Testcontainers` lifecycles at the right scope.
6. Write Kafka integration tests using randomized topics/groups, real Kafka producers, real consumers, manual offset commits, and finite deadlines.
7. Close consumers before deleting groups/topics and avoid `GroupNotEmpty`/consumer-rebalance races.
8. Know when **you do not need to manually delete every group offset** because the test broker container is destroyed completely after the test class.
9. Handle cleanup when assertions fail; never swallow critical teardown errors.
10. Avoid destructive cleanup on shared staging/production brokers.
11. Understand RabbitMQ `ack`/`nack`, unacked messages, queue purge/delete, DLQs, and vhost isolation.
12. Understand JMS durable subscriptions, unacknowledged deliveries, sessions, and destination lifecycles.
13. Diagnose tests that pass in isolation yet fail in the full suite due to stale state, context caching, listener rebalances, and parallelism.
14. Report clearly which tests executed, which broker was used, which state was reset, and the limits of your conclusions.

## 3. A "what must be cleaned up?" matrix by broker type

| System | Primary data | Consumption progress | Metadata/resources easily left behind |
| --- | --- | --- | --- |
| Kafka | Records per topic-partition, retention/compaction | Group committed offsets in Kafka broker; consumer position in client | Topics, consumer group metadata, stream state stores, transactions, producers, listeners, admin clients |
| RabbitMQ | Ready messages in queues, DLQ/delayed queues | Acknowledgments, unacked deliveries, consumer/channel state | Exchanges, bindings, queues, vhosts, connections/channels, retry/DLQ |
| JMS/ActiveMQ Artemis | Queue/topic messages, DLQ | Acknowledgments, transacted sessions, durable subscription cursors | Durable subscriptions, destinations, sessions, connections, client IDs |
| Pulsar | Topic ledger/backlog | Subscription cursor/ack state | Subscriptions, namespaces, tenants, topics, producers/consumers |
| Redis Streams | Stream entries | Consumer group pending-entry list, last-delivered ID | Streams, groups, consumers, keys, TTL |

The runnable lesson uses Kafka because **offsets** are a central concept. However, the broader principle holds everywhere: **message data, consumer progress, and client lifecycles are separate sources of state**.

### 3.1. Test cleanup does not replace a strong test oracle

A test can clean everything up impeccably yet still fail to verify real business behavior. For instance, `assertNotNull(kafkaTemplate)` followed by deleting the topic at method end does not prove records were sent, key/value serialization worked, or a consumer read and committed offsets properly.

A reliable integration test should include:

- Concrete input/fixtures.
- Send/receive actions against a real broker or designated test engine.
- Assertions on payload/key/headers or committed offsets per contract.
- Finite deadlines/timeouts.
- Cleanup of state/resources matching the allocated scope.

## 4. Three Kafka concepts you must keep separate

### 4.1. Log offsets belong to a topic-partition

Kafka stores records per partition. Each record has an increasing `offset` **within that partition**. An offset is not a global ID across all topics.

Example:

```text
topic: orders-it-001, partition 0

offset 0 -> key order-1, value CREATED
offset 1 -> key order-2, value CREATED
offset 2 -> key order-3, value CANCELLED
```

If you create a single partition, every record appends sequentially inside that partition. With multiple partitions, there is no absolute total order across partitions.

**An offset only has meaning together with a topic and partition.** Never assert "the last offset is 3" if other tests can append to the same partition.

### 4.2. Consumer position belongs to a consumer instance

While a `KafkaConsumer` polls records, it tracks a **current read position** per assigned partition. `position(tp)` represents the offset of the next record the consumer will read on that partition.

Position can advance after `poll()` **before committing**. If a consumer crashes right after processing a message without committing, a fresh consumer in the same group can re-read the record from the older committed offset.

### 4.3. Group committed offsets live on the broker

Kafka stores the offset committed by a consumer group. It is normally the **next offset to read**, not the last offset already processed.

Example:

```text
Consumer reads record at offset 0, processes successfully.
commitSync() commits offset 1.

Consumer in the same group restarts:
-> next read position normally starts at offset 1.
New consumer group, auto.offset.reset=earliest:
-> starts at earliest available record, usually offset 0
   in a fresh test topic.
```

Confusing position, committed offsets, and the message log is a common reason tests "lose" or "duplicate" messages.

## 5. `auto.offset.reset=earliest` is not a broker reset button

The Kafka setting:

```properties
spring.kafka.consumer.auto-offset-reset=earliest
```

is used only when a consumer group **has no committed offset** for a partition or its committed offset is no longer valid due to deletion/retention. If the group already committed a valid offset, `earliest` does not rewind the consumer to the start of the log.

| State | What does `auto.offset.reset=earliest` do? |
| --- | --- |
| Fresh group, no offsets | Reads from earliest available offset |
| Group already committed valid offset 12 | Starts from committed offset 12 |
| Group offset points outside retention range | May reset according to policy |
| Code calls `seekToBeginning` after assignment | Local consumer position changes; does not clear group commits |
| Old group completely deleted, group ID reused | Group has no stored progress; reset policy applies next time |
| Topic deleted while group metadata lingers briefly on broker | Do not assume all offsets/group records vanish synchronously |

**Do not fix a "message not seen" test by switching `latest` to `earliest` and claiming you reset offsets.** Ask what the group ID is, which offset was already committed, where the topic starts, and whether the consumer actually joined/got assigned.

## 6. When are group offsets committed?

### 6.1. Auto commit

`enable.auto.commit=true` makes the Kafka consumer periodically auto-commit positions per config. Tests that merely `poll` and wait a few seconds create hard-to-control group progress and flakiness.

For tests demonstrating offset semantics, use:

```java
props.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false);
```

After verifying processing succeeded, call `commitSync()` explicitly.

### 6.2. Manual commit

```java
try (KafkaConsumer<String, String> consumer =
             createConsumer(groupId)) {
    consumer.subscribe(List.of(topic));
    List<ConsumerRecord<String, String>> records =
            readAtLeast(consumer, 1);
    assertEquals("CREATED", records.get(0).value());
    consumer.commitSync();
}
```

This is a **pattern inside the runnable class in section 12**, relying on helpers defined there. In a single-message test, committing after the assertion is easy to follow. In real consumer processing, commit **only when processing is done per the delivery guarantee**; never commit before updating the database and call that exactly-once.

### 6.3. Kafka delivery semantics

- **At-most-once:** can lose messages if committing before processing and then crashing.
- **At-least-once:** can re-read messages after a crash; needs an idempotent handler.
- **Exactly-once in Kafka:** relies on transaction/idempotent producer/consumer mechanics and specific conditions; it does not automatically apply to external database side effects.

Never use offset cleanup to hide a non-idempotent handler. Duplicate/redelivery tests must assert that business logic prevents double processing.

## 7. Designing isolation scopes: test, class, suite, CI run

| Scope | Strategy | Benefits | Notes |
| --- | --- | --- | --- |
| Each `@Test` | Unique topic/group, dedicated consumer | Avoids state collisions | Many topics if not cleaned up |
| Test class | One static `KafkaContainer`, unique topics per method | Single broker startup, easier group cleanup | Class-scoped broker; context cache must align with lifecycle |
| Integration suite group | One shared `KafkaContainer` across classes | Cuts startup overhead | Needs isolated names, consistent lifecycle/app contexts |
| One CI job | Dedicated broker container per job, unique namespaces | Runs multiple suites | Never share across concurrent jobs |
| Shared staging broker | Prefixed/permissioned namespaces/topics/groups | Lower infra cost | Never delete/alter others' resources; state/race risks |
| Production | Never use as a test cleanup target | None | Never delete topics/groups/queues to "clean up tests" |

A useful rule:

**The wider a broker is shared, the stricter resource ownership and scoping must be.** If a broker belongs exclusively to one JUnit class and Testcontainers destroys it at the end of the class, **all topic logs and consumer-group offsets** inside that broker vanish with the container/ephemeral volume. You do not strictly need API calls to delete every individual consumer group.

If the broker outlives the class, manage topic/group lifecycles explicitly and track who owns which resources.

## 8. Cleanup plan for a Kafka test group

An intentional teardown follows this sequence:

```text
Test setup
   |
   +-- Start isolated Kafka broker (per class)
   +-- Generate unique topic and group IDs
   +-- Create topic explicitly, await AdminClient result
   +-- Create producer/consumers
   |
Test action
   |
   +-- Send record and await send future
   +-- Subscribe, poll until deadline, and assert records
   +-- Commit offset only when the test requires it
   |
Per-test teardown
   |
   +-- Stop/close all test-created consumers and listeners
   +-- Wait for in-flight sends/processing to finish (bounded)
   +-- Delete owned test topic if broker stays alive
   +-- Close AdminClient, producer, and other handles
   |
After test CLASS
   |
   +-- Testcontainers extension stops class-owned broker
   +-- Broker logs / group offsets / ephemeral storage vanish
```

**Order matters:** never delete a topic/group while a consumer is still polling or `@KafkaListener` is rebalancing; that triggers random errors, log noise, or `group-not-empty` failures. Never stop the broker before finishing assertions/cleanup that need the broker.

### 8.1. Cleanup failures are real signals

An `@AfterEach` calling `deleteTopics` can fail due to permissions, broker unavailability, or timeouts. Never write `catch(Exception ignored) {}` making the suite look green while leaking state. Against a private broker about to be destroyed, you might choose to log secondary cleanup issues and let container teardown finish; **report accurately** rather than claiming "topic deleted successfully" without confirmation.

In the runnable example, `@AfterEach` surfaces cleanup failures while still closing `AdminClient` inside `finally`.

## 9. Kafka `deleteTopics`, `deleteRecords`, and `deleteConsumerGroups` differ

### 9.1. Deleting topics

```java
admin.deleteTopics(List.of(topic))
        .all()
        .get(15, TimeUnit.SECONDS);
```

Requests the broker to delete test-owned topics. Metadata/data deletion can have propagation delay; API completion does not always mean every broker view converged instantaneously. If immediately creating **the exact same topic name**, use bounded polling to confirm the topic is gone; simpler still, never reuse topic names.

**On a shared broker, delete only topics created by the test itself.** Never call `deleteTopics(List.of("orders"))` on a shared topic just because a test wants "clean data".

### 9.2. Deleting records

Admin API `deleteRecords` truncates logs up to certain offsets without necessarily altering all group committed offsets. It also depends on partitions/retention and does not necessarily restore an "empty topic starting at offset 0".

Therefore **do not use `deleteRecords` like a database `repository.deleteAll()`**. In tests, creating a unique topic and discarding the topic/broker is easier and safer.

### 9.3. Deleting consumer groups

The Kafka Admin API supports `deleteConsumerGroups` for groups **with no active members**:

```java
admin.deleteConsumerGroups(List.of(groupId))
        .all()
        .get(15, TimeUnit.SECONDS);
```

This is an **extension snippet**; the runnable class does not call it because the private broker is destroyed completely after the class. On a shared broker, run this only after all consumers/listeners in the group have stopped, and only for test-owned group IDs. If the group still has active members, the broker rejects it (e.g., `group-not-empty`).

**Deleting a group does not delete records in the topic.** Another group can still read those records at its own offsets.

### 9.4. Resetting group offsets

Kafka tooling/admin APIs allow resetting offsets to earliest/latest/specific offsets, provided the group is inactive as required. This **changes consumption progress**, without deleting the message log.

Be careful: resetting a group can replay side effects or skip messages. Never run group resets outside test scope, especially in shared/staging/production environments.

### 9.5. Using `seekToBeginning`

`consumer.seekToBeginning(partitions)` moves the **current consumer's position** after partitions are assigned. It does not clear the group's committed offsets and does not synchronize other consumers in the same group back to the start.

If a test wants to re-read within the same instance, `seek` may fit. If a test wants to verify restart semantics, close the instance, create a new consumer in the same group, and observe the real **committed offset** — never use `seek` to fake restart behavior.

## 10. A dedicated container can be the best cleanup strategy

With Testcontainers:

```java
@Testcontainers
class KafkaGroupTest {
    @Container
    static KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse(
                            "confluentinc/cp-kafka:7.6.1"));
}
```

In **Spring Boot 3.3 / Testcontainers 1.x**, `org.testcontainers.containers.KafkaContainer` and module `org.testcontainers:kafka` are the matching choices. Newer Testcontainers documentation may use other classes such as `org.testcontainers.kafka.ConfluentKafkaContainer`/`org.testcontainers.kafka.KafkaContainer` and updated module artifacts — never mix newer-version APIs into an older example without updating dependencies and imports together.

- `@Container static`: the broker stays alive across methods in the class.
- The JUnit Testcontainers extension manages start/stop per class.
- Group/topic state accumulates **within the class** if IDs are reused.
- When the class broker stops/is removed, ephemeral test broker state vanishes.
- Spring TestContext caches can outlive the JUnit class → avoid reusing Kafka client beans pointing to a stopped broker.

The example uses unique topics/groups per method and a single test class, keeping lifecycles simple.

**Limitation:** A single-node `KafkaContainer` does not prove production replication/failover, multi-broker partition leadership, or managed-cluster ACLs/TLS.

## 11. Runnable project: Spring Boot 3.3 + Java 17 + Kafka Testcontainers

The project includes:

- Minimal Spring Boot application class so Boot creates Spring Kafka beans.
- Real Kafka broker in Testcontainers with `@ServiceConnection`.
- Spring `KafkaTemplate<String,String>` for sending records.
- Kafka `AdminClient` for creating/deleting test-owned topics.
- Self-managed `KafkaConsumer<String,String>` for observing exact offsets.
- Four JUnit methods testing consumption, consumer-group independence, commit/resume, and uncommitted redelivery.
- `@BeforeEach` provisions a unique topic, `@AfterEach` deletes the topic and closes admin, `try-with-resources` closes consumers.
- Broker container stops after the class — wiping any remaining group offsets.

All tests require a working Docker or compatible container runtime; **never silently skip** if Kafka cannot start.

### 11.1. Directory tree

```text
kafka-test-cleanup/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/messaging/
    │   └── MessagingLabApplication.java
    └── test/java/example/messaging/
        └── KafkaGroupCleanupTest.java
```

### 11.2. `settings.gradle`

```groovy
rootProject.name = 'kafka-test-cleanup'
```

### 11.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3 dependency management controls compatible Spring Kafka/Testcontainers client library versions. `org.testcontainers:kafka` corresponds to Testcontainers **1.x** managed by Boot 3.3; in Testcontainers 2.x, package/artifact names and modules changed, requiring an explicit migration check.

Do not use `spring-boot-starter-kafka` assuming it exists in Boot 3.3 if that artifact is not part of that version's starter set; the exact dependency here is **`org.springframework.kafka:spring-kafka`**.

`spring-boot-testcontainers` provides `@ServiceConnection` integration. `org.testcontainers:junit-jupiter` manages test container lifecycles. Kafka image `confluentinc/cp-kafka:7.6.1` is an intentional choice for Testcontainers 1.x; production/release pipelines must maintain versions/digests per security policy.

### 11.4. `MessagingLabApplication.java`

**`src/main/java/example/messaging/MessagingLabApplication.java`:**

```java
package example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingLabApplication.class, args);
    }
}
```

The app has no background `@KafkaListener`. This is deliberate so manual consumers can test offset semantics without an unexpected listener container joining the group or consuming messages.

In real projects with `@KafkaListener`/`ConcurrentMessageListenerContainer`, teardown must also stop listener containers and account for assigned partitions/rebalances.

## 12. `KafkaGroupCleanupTest.java` — four integration tests

**`src/test/java/example/messaging/KafkaGroupCleanupTest.java`:**

```java
package example.messaging;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.core.KafkaTemplate;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=" +
        "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=" +
        "org.apache.kafka.common.serialization.StringSerializer"
})
class KafkaGroupCleanupTest {

    @Container
    @ServiceConnection
    static KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse(
                            "confluentinc/cp-kafka:7.6.1"));

    @Autowired
    KafkaTemplate<String, String> template;

    private AdminClient admin;
    private String topic;
    private boolean created;

    private static String unique(String prefix) {
        return prefix + "-" +
                UUID.randomUUID().toString()
                        .replace("-", "");
    }

    @BeforeEach
    void createIsolatedTopic() throws Exception {
        topic = unique("orders-it");
        created = false;
        admin = AdminClient.create(Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers()));

        admin.createTopics(List.of(
                new NewTopic(topic, 1, (short) 1)))
                .all()
                .get(15, TimeUnit.SECONDS);

        created = true;
    }

    @AfterEach
    void cleanupOwnedTopic() throws Exception {
        if (admin == null) {
            return;
        }

        try {
            if (created) {
                admin.deleteTopics(List.of(topic))
                        .all()
                        .get(15, TimeUnit.SECONDS);
            }
        }
        finally {
            admin.close(Duration.ofSeconds(5));
        }

        // No global group delete: Kafka broker is private
        // to this class and will be removed by Testcontainers.
    }

    private KafkaConsumer<String, String> consumer(
            String groupId) {
        Map<String, Object> props = new HashMap<>();

        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                groupId);
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        props.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");
        props.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false);
        props.put(
                ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG,
                false);

        return new KafkaConsumer<>(props);
    }

    private void send(String key, String value)
            throws Exception {
        template.send(topic, key, value)
                .get(15, TimeUnit.SECONDS);
    }

    private List<ConsumerRecord<String, String>> readAtLeast(
            KafkaConsumer<String, String> consumer,
            int expected) {
        List<ConsumerRecord<String, String>> found =
                new ArrayList<>();

        long deadline = System.nanoTime()
                + Duration.ofSeconds(15).toNanos();

        while (found.size() < expected
                && System.nanoTime() < deadline) {
            ConsumerRecords<String, String> batch =
                    consumer.poll(Duration.ofMillis(250));

            batch.forEach(found::add);
        }

        assertTrue(
                found.size() >= expected,
                "Expected at least " + expected +
                        " records but received " + found.size());

        return found;
    }

    @Test
    void consumesTwoRecordsFromFreshGroup() throws Exception {
        send("order-1", "CREATED");
        send("order-2", "PAID");

        try (KafkaConsumer<String, String> c =
                     consumer(unique("group-a"))) {
            c.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> values =
                    readAtLeast(c, 2);

            assertEquals(2, values.size());
            assertEquals("order-1", values.get(0).key());
            assertEquals("CREATED", values.get(0).value());
            assertEquals("order-2", values.get(1).key());
            assertEquals("PAID", values.get(1).value());

            c.commitSync();
        }
    }

    @Test
    void differentGroupCanReadSameRecord()
            throws Exception {
        send("order-3", "CREATED");

        String groupA = unique("group-a");
        String groupB = unique("group-b");

        try (KafkaConsumer<String, String> first =
                     consumer(groupA)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);
            assertEquals("CREATED", batch.get(0).value());

            first.commitSync();
        }

        try (KafkaConsumer<String, String> second =
                     consumer(groupB)) {
            second.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(second, 1);

            assertEquals("CREATED", batch.get(0).value());
            second.commitSync();
        }
    }

    @Test
    void sameGroupResumesAfterCommittedOffset()
            throws Exception {
        String groupId = unique("resume-group");

        send("order-4", "CREATED");

        try (KafkaConsumer<String, String> first =
                     consumer(groupId)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);

            assertEquals("CREATED", batch.get(0).value());

            first.commitSync();
        }

        send("order-4", "PAID");

        try (KafkaConsumer<String, String> restarted =
                     consumer(groupId)) {
            restarted.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(restarted, 1);

            // The committed offset skips the prior CREATED record.
            assertEquals(1, batch.size());
            assertEquals("PAID", batch.get(0).value());

            restarted.commitSync();
        }
    }

    @Test
    void uncommittedRecordIsRedeliveredAfterRestart()
            throws Exception {
        String groupId = unique("uncommitted-group");

        send("order-5", "CREATED");

        try (KafkaConsumer<String, String> first =
                     consumer(groupId)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);

            assertEquals("CREATED", batch.get(0).value());

            // Deliberately do not commit.
        }

        try (KafkaConsumer<String, String> restarted =
                     consumer(groupId)) {
            restarted.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(restarted, 1);

            // No committed progress: earliest applies.
            assertEquals("CREATED", batch.get(0).value());

            restarted.commitSync();
        }
    }
}
```

### 12.1. Why does the runnable suite have only one class?

The Testcontainers JUnit extension stops static `@Container` after the class completes, while Spring TestContext can cache the context across classes. Another class reusing Kafka producer/listener beans configured with a stopped broker's bootstrap address will fail.

A single class avoids that reuse pitfall in this lab. For multi-class suites, use a Spring-managed container lifecycle or a singleton container pattern compatible with context caching; **do not** copy the same static container into multiple classes assuming Spring contexts and JUnit containers share the same lifetime.

### 12.2. Why create a new topic per test?

`@BeforeEach` generates a random topic name prefixed `orders-it-`. Tests do not contend over log data regardless of execution order. Each topic has **one partition** so ordering assertions across two records are unambiguous.

Do not share a fixed `orders` topic and call `deleteRecords`/`resetOffsets` before every test — that can collide with other groups, create races, and fail to reset all state.

### 12.3. Why use a new group ID per scenario?

- `differentGroupCanReadSameRecord` proves offsets belong to groups; group B still reads the record A already committed.
- `sameGroupResumesAfterCommittedOffset` intentionally reuses **the same group ID within one test** to prove restart/resume.
- `uncommittedRecordIsRedeliveredAfterRestart` reuses the group ID yet **omits committing** the first time, so the second instance reads from `earliest`.
- Tests stay independent because topic/group names differ across methods.

Never assert business results based on random timestamps/UUIDs; unique names serve isolation only.

### 12.4. Why use manual `KafkaConsumer` instead of `@KafkaListener`?

In a lesson focused on offsets, a manual consumer cleanly isolates:

- `subscribe` and group assignment.
- `poll` returning batches.
- When `commitSync` is called.
- `close` ending group membership.
- Exact consumer group ID.

`@KafkaListener` with Spring Kafka's listener container auto-commits/acks per `AckMode` and consumer factory config. That fits testing real applications, yet adds another lifecycle/offset-management layer to a foundational offset experiment.

### 12.5. Why must the consumer be inside `try-with-resources`?

`KafkaConsumer` holds I/O/network resources and group membership. `close()` releases resources and leaves the group cleanly. If a test fails an assertion mid-method without closing the consumer, the broker may still see an active member until session timeout expires; group teardown fails and other tests experience rebalances.

`try-with-resources` guarantees closing even when the test body throws. `AdminClient` is closed in `@AfterEach`'s `finally` block.

### 12.6. Why not delete groups after every method?

The broker belongs exclusively to one class and is removed by Testcontainers at the end of the class. Thus leftover group metadata/committed offsets cannot leak to other test groups. We delete topics per method to practice resource hygiene and avoid unbounded topic growth inside a long class.

When tests share a long-lived **shared broker**, add group cleanup once all consumers have stopped; that introduces shared-state risks covered in section 15.

### 12.7. A caveat on asynchronous cleanup

`AdminClient.deleteTopics(...).all().get(...)` confirms the admin request finished per API, **not that every broker node/metadata cache saw the topic disappear instantaneously**. The sample never reuses topic names, so it never depends on "delete then recreate the exact same name" within milliseconds.

### 12.8. Does `@ServiceConnection` actually support Kafka?

In Spring Boot 3.3, `spring-boot-testcontainers` provides `KafkaConnectionDetails` for supported Kafka Testcontainers types. Placing `@ServiceConnection` on a static typed `KafkaContainer` lets Boot configure Spring Kafka's connection to the test broker without hardcoding `localhost:9092`.

Manual consumers and `AdminClient` in the lab read `kafka.getBootstrapServers()` directly for clarity and to avoid reading `KafkaProperties.getBootstrapServers()` which is not mutated by connection details. Spring's `KafkaTemplate` is configured by Boot via the service connection.

**Do not** simultaneously pair `@ServiceConnection` with `@DynamicPropertySource` on the same container unless you fully understand configuration precedence.

## 13. Running Gradle and expected results

Requirements: JDK 17, compatible Gradle Wrapper (e.g., Gradle 8.7), dependency download access, Docker/compatible container runtime, and the Confluent Kafka image.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.messaging.KafkaGroupCleanupTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.messaging.KafkaGroupCleanupTest
```

**Expected result:** **4 JUnit test methods pass** once `KafkaContainer` starts, `KafkaTemplate`/Consumer/`AdminClient` connect, and the broker creates/deletes topics. If Docker is unavailable, tests fail at container bootstrap; that is an infrastructure failure, not a test "passing by skipping".

These are **expected results from the code**, not claims of running Gradle/Docker during authoring. Startup time, mapped broker port, and container ID are dynamic.

### 13.1. Kafka logs are not fixed expected stdout

Logs include broker startup, client cluster metadata, group assignments/rebalances, and topic deletion. Never assert log text byte-for-byte: Kafka/driver versions evolve. Base assertions on records, keys, group behavior, and cleanup API results.

### 13.2. Does Spring Boot need to run an HTTP server?

No. `@SpringBootTest` defaults to MOCK web environment, yet the project has no `starter-web`; it still builds the application context needed to inject `KafkaTemplate`. We are testing the messaging boundary with no HTTP endpoints.

### 13.3. How to report test status

Report clearly:

```text
Kafka integration suite:
- Test class executed: KafkaGroupCleanupTest
- Methods expected: 4
- Actual passed/failed/skipped: see JUnit/Gradle report
- Broker: KafkaContainer (class scope)
- Topic scope: one unique topic per test method
- Consumer group scope: unique per scenario
- Cleanup: topic delete request per method, broker teardown per class
```

This is a **report template**, not measured logs. Never write `PASSED 4/4` unless you actually executed the tests and verified the report.

## 14. How does cleanup differ when the app uses `@KafkaListener`?

A typical Spring Boot messaging application uses:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service")
public void onMessage(String payload) {
    // business processing
}
```

This is an **illustrative snippet**, not part of the runnable lab. When loading the Spring context, listener containers may auto-start, join groups, poll, and commit offsets per configuration. If you share the same topic/group with a manual `KafkaConsumer` in a test, records can be consumed by the other consumer → tests become nondeterministic.

### 14.1. Stop listener containers before cleanup

In a test with Spring Kafka listeners, inject the registry:

```java
@Autowired
KafkaListenerEndpointRegistry listenerRegistry;
```

And during teardown of a dedicated test context/group:

```java
for (MessageListenerContainer container
        : listenerRegistry.getListenerContainers()) {
    container.stop();
}
```

**This is an illustrative snippet**, requiring imports `org.springframework.kafka.config.KafkaListenerEndpointRegistry` and `org.springframework.kafka.listener.MessageListenerContainer`. `stop()` may require bounded waiting/callbacks depending on listener container semantics and version; do not assume every `stop()` return means all in-flight work has finished.

Crucially: the registry may contain **listeners not owned by the test** in a shared application context. Never stop global listener beans and leave other tests reusing that context without restarting them.

### 14.2. When listeners have in-flight messages

A listener processing a message takes several seconds; teardown begins deleting the topic before the callback finishes. Results can include late DB writes, commit errors, duplicate redeliveries, or subsequent tests reading stray side effects.

Solutions:

- Await business assertions with a deadline.
- Stop listeners and wait for clean shutdown.
- Commit/ack per handler contract.
- Ensure no in-flight callbacks remain targeting other tests' state.
- Only then delete owned resources.
- Use dedicated contexts/brokers when sharing lifecycles gets too tricky.

### 14.3. `ConsumerFactory`, `KafkaTemplate`, and `KafkaAdmin`

Spring-managed clients differ from test-created consumers:

- `KafkaTemplate` uses a producer factory; producers may be cached/reused.
- `DefaultKafkaConsumerFactory` creates consumers per listener/test; each consumer must close.
- `KafkaAdmin` can create `NewTopic` beans at context startup.
- `KafkaListenerEndpointRegistry` manages listener containers.
- Manually created Java `AdminClient` instances must be closed.
- Executors, schedulers, retry topics, and DLQ consumers can outlive a test method.

Never create a manual `KafkaConsumer` and clean up only that instance while `@KafkaListener` keeps running in the same context.

## 15. On a shared broker: cleaning up consumer groups safely

Using a shared Kafka broker across multiple test classes/runs complicates cleanup. A clear ownership/permission workflow:

1. Create topic `it-<runId>-orders` and group `it-<runId>-consumer`, recording the owner/run ID.
2. Producer sends records and awaits futures.
3. Consumer/listener processes records and commits/acks as required.
4. Stop/close **all active consumers** belonging to the test group.
5. Wait for the broker group to enter inactive/empty state with a bounded deadline if needed.
6. Use `AdminClient` to delete consumer groups **matching only the IDs created by this run**.
7. Delete topics owned by this run; await deletion convergence if reusing names (better not to reuse).
8. Close `AdminClient` and other resource handles.
9. Surface errors accurately; never swallow `GroupNotEmptyException`.
10. Clean up orphaned test resources via a job using allowlists/prefixes/TTLs; never touch production resources.

### 15.1. Snippet for deleting a closed group

```java
try (AdminClient admin = AdminClient.create(
        Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers))) {
    admin.deleteConsumerGroups(List.of(ownedGroupId))
            .all()
            .get(15, TimeUnit.SECONDS);
}
```

This is a **standalone API snippet**; `bootstrapServers` and `ownedGroupId` must be supplied from test scope. If the group is missing or still has active members, the operation can throw. Do not force every test to delete groups when private containers are already destroyed.

### 15.2. Never delete a group while members remain active

Kafka allows deleting a group only when it has zero active members. While `@KafkaListener` stays alive, `deleteConsumerGroups` typically fails. Fix by stopping/closing the right listener/consumer rather than retrying infinitely or mutating someone else's group offsets.

### 15.3. Watch out for reused consumer group IDs

Identifiers like `test-group` or `inventory-consumer` repeated across classes/CI builds keep old commits on the broker. Consequences:

- Test run B starts at run A's offset, skipping new fixtures.
- Test run B sees old retained records with a new group on a shared topic.
- Stale group metadata complicates debugging.
- Parallel jobs trigger rebalances against each other when group IDs collide.

Use scoped IDs: test suite/run/class/method with sanitized UUIDs or unique suffixes. Keep Kafka topic naming/length limits and valid character sets in mind.

## 16. Inspect current offsets instead of guessing

Kafka `AdminClient` can inspect group offsets:

```java
Map<TopicPartition, OffsetAndMetadata> offsets =
        admin.listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get(15, TimeUnit.SECONDS);
```

This is an **illustrative snippet** requiring `TopicPartition`, `OffsetAndMetadata`, and `admin`/`groupId` variables in scope. Across newer Kafka client versions, some Admin APIs may be deprecated or offer different overloads; check the exact version managed by your Spring Boot BOM.

What to check:

- Exact group ID.
- Exact topic/partition IDs.
- Committed offsets are valid and within the log range.
- End offsets (log end) if computing lag.
- Whether the group has active members.

Kafka's `kafka-consumer-groups.sh` also offers:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group it-example-group
```

**This is only an illustrative command** when the broker is actually listening on `localhost:9092`. With Testcontainers dynamic mapped ports, pass `kafka.getBootstrapServers()` or the corresponding environment variable rather than hardcoding `localhost:9092`.

### 16.1. Offset reset CLI only on inactive groups

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <owned-test-group> \
  --topic <owned-test-topic> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Angle-bracket strings are placeholders to substitute, not an immediately runnable command. To apply, switch to `--execute` **after** dry-run and after confirming the broker/group/topic belong to tests. Never reset a shared group processing production events.

**Never use offset reset as "default cleanup"**: resetting can re-trigger side effects when test consumers re-run handlers.

## 17. Topic deletion: why is it not like deleting a SQL row?

In Kafka, a topic encompasses metadata, partitions, logs, leaders/replicas, retention, ACLs, quotas, and subscribed clients. Deleting a topic:

- Can be asynchronous at the broker/controller level.
- Can cause consumers to receive metadata errors/rebalances.
- Is not equivalent to "delete records and reset all committed offsets to 0".
- Can disrupt running producers/listeners.
- Can break other workloads if the topic is shared.
- Does not clear local Kafka Streams state stores or database side effects.

Using unique topics **and never reusing names** is usually far simpler than trying to synchronize delete/recreate on the same name in parallel CI.

If the broker environment forbids topic deletion, alternatives include:

- Dedicated broker container per test class destroyed afterward.
- Dedicated topic prefixes with authorized cleanup jobs.
- Short retention on test topics without mistaking retention for instant cleanup.
- Scheduled admin cleanup jobs using allowlists/run TTLs.

Never alter broker-wide `delete.topic.enable` or cluster ACLs casually just to make one test green.

## 18. Dead-letter topics, retry topics, and Spring Kafka retries

In Spring Kafka, processing failures can involve:

- Retrying the same record.
- Suffixed or custom-named retry topics.
- Dead-letter topics (DLT).
- Backoff timers/scheduled retries.
- Dedicated consumer groups for retry/DLT.
- Failed records carrying specialized headers/serializers.

If a test deletes only the **main topic** while leaving retry/DLT topics and messages behind, later tests can observe old failures or background listeners continuing to process.

An integration test group must inventory **every topic created by the workflow**, e.g.:

```text
it-run42.orders
it-run42.orders-retry-0
it-run42.orders-retry-1
it-run42.orders-dlt
```

These are **illustrative names**, not a claim that Spring Kafka always generates those exact suffixes; `@RetryableTopic` configuration, retry policies, and naming strategies decide the real names.

Clean up in order:

1. Confirm retry/DLT assertions are complete.
2. Stop listeners/consumer groups.
3. Cancel pending scheduled tasks/callbacks.
4. Delete all owned topics/queues or destroy the broker.
5. Close producers/admin clients.
6. Never delete shared system DLT topics.

### 18.1. Do not let cleanup mask retry bugs

If a handler fails and sends a message to the DLT, the test must assert the **DLT record** before deleting. Deleting right after sending does not test retry behavior and can hide a consumer that never got a chance to process.

### 18.2. Exactly-once and Kafka transactions

Spring Kafka transactional producers use a `transactional.id` and broker-side state. Two parallel test runs sharing the same transactional ID can trigger producer fencing. Use unique transactional ID prefixes per test run or isolated brokers; close/stop producer factories before destroying the broker.

Deleting topics/group offsets **does not automatically clear** all transactional producer metadata in a way that resets the transaction protocol. Private disposable brokers are usually much cleaner for complex transactional tests.

## 19. RabbitMQ: purging a queue does not clear all messaging state

RabbitMQ uses a different model from Kafka:

```text
Publisher
   |
Exchange --binding--> Queue
                      | ready messages
                      | unacked deliveries
                      v
                   Consumer
                      |
                    ack / nack
                      |
                      +--> accepted, removed
                      +--> requeue (if requested)
                      +--> dead-letter flow (if configured)
```

In RabbitMQ, distinguish:

- **Ready messages:** waiting in the queue for a consumer.
- **Unacked deliveries:** delivered to a consumer yet awaiting ack/nack; these can be requeued when the channel/connection closes.
- **DLQ:** a separate queue holding dead-lettered messages.
- **Exchange/binding/queue metadata:** does not vanish when purging messages.
- **Consumers/channels/connections:** process resources that must be stopped/closed.

### 19.1. `purgeQueue` does not delete exchanges and bindings

Spring AMQP offers `AmqpAdmin.purgeQueue(queueName, false)` or equivalent APIs to clear ready messages on test-owned queues. However:

- Purging does not delete queues/exchanges/bindings.
- In-flight unacked deliveries can reappear after consumer disconnect/nack depending on lifecycle.
- DLQs still hold their own messages.
- Delayed/scheduled messages may sit in separate extensions/queues.
- If another test shares the queue, purging destroys its state.

On a dedicated test broker/vhost, purging can fit specific testcases. On shared queues, **never** purge as a global reset.

### 19.2. Snippet for deleting a test-owned queue

```java
// Run only after all test consumers have stopped,
// and the queue belongs exclusively to this test.
amqpAdmin.deleteQueue(ownedQueueName);
```

This is a **code snippet**; `amqpAdmin` (`AmqpAdmin`) and `ownedQueueName` must come from test configuration. Queue deletion is destructive: it deletes ready messages and associated queue bindings; never call it on production/shared queues.

### 19.3. Vhosts and resource names

In large RabbitMQ suites, a dedicated vhost per CI run gives strong isolation: policies, exchanges, queues, and consumer connections get independent namespaces. Creating/deleting vhosts may require elevated admin privileges, so follow team policy. When using a private `RabbitMQContainer` per class/suite, destroying the container is the cleanest broker reset.

### 19.4. DLQs and retries

Negative-handling tests should assert:

1. Message published to main exchange/queue.
2. Consumer receives and throws under the right condition.
3. Retry/requeue logic executes per policy.
4. Message eventually lands in the DLQ (if required by contract).
5. `x-death`/retry count headers behave properly if checked.
6. Clean up main queue + DLQ + consumers after assertions.

Never delete the DLQ before the test asserts on it; never treat queue length 0 as proof of successful processing — the message may be unacked or already moved to the DLQ.

## 20. JMS/ActiveMQ Artemis: durable subscriptions are another kind of state

JMS has queues and topics; with durable subscriptions, the broker can retain subscriptions and message backlogs **after a consumer disconnects**. Stopping a listener therefore does not necessarily delete the subscription.

Resources to account for:

- JMS `Connection` and `Session`.
- `MessageConsumer`/`MessageProducer`.
- Queue/topic destinations.
- Durable subscription names and client IDs.
- Acknowledgment modes / transacted sessions.
- Dead-letter addresses/queues.
- Redelivery delays and scheduled messages.
- Test broker container/embedded broker process.

If a test creates a durable subscription, cleanup may need **unsubscribe** once the subscriber is inactive, per JMS provider APIs/rules. For example, JMS `Session` has `unsubscribe(subscriptionName)` for named durable subscriptions in the right context. Never treat `consumer.close()` as proof the broker removed durable state.

### 20.1. When a JMS transaction rolls back

With transacted sessions, message receive/ack can roll back and redeliver. A test checking "queue empty" right after a method may fail if the transaction rolled back or the session closed before committing. Assert commit/rollback/redelivery per contract and clean up after the transaction outcome is settled.

### 20.2. ActiveMQ Artemis test container

Testcontainers supports `ArtemisContainer` in matching versions; Spring Boot provides `ArtemisConnectionDetails` for typed containers when using service connections. Pick matching module versions and broker images. A single Artemis container does not represent a full clustered HA topology.

## 21. Spring TestContext cache and broker lifecycle are two different clocks

Spring Boot integration tests use Spring TestContext caching to avoid reloading application contexts repeatedly. Meanwhile, the JUnit Testcontainers extension may stop a static `@Container` when **one class** finishes.

Failure scenario:

```text
Test Class A:
    @SpringBootTest -> ApplicationContext cached
    @Container static Kafka broker A started
    KafkaTemplate points to bootstrap broker A
    methods PASS
    JUnit extension stops broker A

Test Class B:
    Spring reuses cached ApplicationContext
    KafkaTemplate still points to stopped broker A
    KafkaContainer broker B may have another port
    methods FAIL / timeout
```

Solutions:

- Align broker lifecycle with the context, e.g., a Spring-managed container bean in test configuration.
- Or a singleton container pattern whose lifetime matches the JVM test process/context.
- Or explicit per-class context isolation, accepting the bootstrap cost.
- Never abuse `@DirtiesContext` as "clear Kafka messages"; it only evicts the Spring context cache and does not clear remote broker state.
- Never let JUnit stop a static broker at the end of one class while expecting another class to safely reuse a cached context.

**Cleaning messaging state** and **cleaning Spring context state** are two separate actions that may need coordination without substituting for one another.

## 22. Parallel tests: three common race sources

### Race A — Two tests share the same topic and group

Two consumers in the same group split partitions rather than both receiving all messages. Test A can "eat" Test B's message; Test B times out even though the producer succeeded.

**Fix:** unique group/topic per test when independent consumption is needed.

### Race B — Two tests share the same topic with different groups

Each group reads every message on the topic, including fixtures from the other test. Unexpected extra records appear.

**Fix:** unique topics or strict filter/key namespaces; separate groups alone are not always enough.

### Race C — Test A's cleanup deletes Test B's resource

Test A's `@AfterEach` deletes shared topic `orders-test` while B is still polling. B hits metadata errors/timeouts. This is an **isolation bug** in test infrastructure, not a Kafka bug.

**Fix:** give each test its own ownership scope. Under parallel execution, use unique resources and let teardown touch only owned names.

### 22.1. Testcontainers JUnit parallel considerations

The Testcontainers JUnit Jupiter extension in many versions is documented primarily for sequential execution. For parallel execution, evaluate module lifecycles, state isolation, and resource pressure; never assume the extension prevents every shared-container race.

In the lab, keep the class sequential. If the repo enables JUnit parallel execution globally, annotate classes carrying shared static containers/state appropriately (e.g., `@Execution(ExecutionMode.SAME_THREAD)` with proper imports), or isolate them in a dedicated Gradle task.

## 23. Polling with deadlines instead of fixed sleeps

Message delivery is asynchronous. After producer `send()`, a consumer may need time to join the group and receive partition assignments before reading records.

Do not do this:

```java
template.send(topic, "key", "value");
Thread.sleep(1000);
assertEquals(1, received.size());
```

This is an **anti-pattern**:

- Does not await the send future, so broker ack is unverified.
- Sleeping 1 second may be too long or too short.
- A shared `received` collection can race if updated by a listener thread.
- No visibility into offset/assignment/group state.

In the lab:

```java
template.send(topic, key, value)
        .get(15, TimeUnit.SECONDS);

while (records.size() < expected
        && System.nanoTime() < deadline) {
    ConsumerRecords<String, String> batch =
            consumer.poll(Duration.ofMillis(250));
    batch.forEach(records::add);
}
```

Strengths:

- Awaits producer send future completion with a timeout.
- Polls consumer up to a deadline.
- Asserts exact record count/contents.
- Closes consumer via `try-with-resources`.
- Never asserts exact millisecond timing.

In systems with Kafka listeners/background work, Awaitility or a timed `CountDownLatch` can work, provided thread safety is ensured and post-teardown callbacks are avoided.

## 24. Message ordering and offset assertions: do not overstate evidence

In the lab, each topic has one partition. Hence `CREATED` and `PAID` sent sequentially can be verified in order on that single partition.

With multi-partition topics:

- Order is guaranteed only **within a single partition**.
- Same keys usually route to the same partition via the partitioner, though behavior depends on partitioner/config/schema.
- Group members may be assigned subsets of partitions.
- `poll()` can return records from multiple partitions; iteration order is not a global event ordering contract.
- Offsets cannot be compared directly across different partitions.
- Producer retries/idempotence and `max.in.flight.requests` affect ordering under failures.

Never write a test assuming all messages on a multi-partition topic have global order. When domain ordering per aggregate key is needed, design keys/partitioning and assert at the matching granularity.

### 24.1. Lag is not committed offset

Consumer lag is typically log end offset minus committed group offset per partition. It is a diagnostic metric, not proof that business processing completed: handlers might commit before side effects, or retry pipelines may still be pending.

During cleanup, lag equal to 0 does not guarantee there are no in-flight callbacks, DLQ messages, or pending database writes.

## 25. Kafka Streams: state stores and internal topics need separate cleanup

A `KafkaStreams` application can create:

- Local state stores on disk.
- Changelog topics.
- Repartition topics.
- Internal consumer groups/transactional producer IDs.
- RocksDB state directories.
- Background stream threads.

If a test deletes only the input topic while the `KafkaStreams` client stays running, internal topics/stores can survive and contaminate subsequent tests.

With Spring Kafka Streams:

1. Use a unique `application.id` per test group.
2. Stop the `KafkaStreams` instance and wait for close.
3. Manage owned internal topics by `application.id` or destroy a private broker.
4. Delete test-owned local state directories where appropriate.
5. Never share `application.id`/state dirs across parallel runs.
6. Never delete internal topics of other stream applications.

A class-scoped static `KafkaContainer` destroyed after tests cleans broker-side state, **yet JVM local filesystem state stores** still need attention if durable test directories are configured.

## 26. Retry and dead-letter tests must wait for stable conditions

In message-driven tests:

```text
send record
    |
listener consumes
    |
business operation fails
    |
retry scheduled
    |
DLQ/DLT receives record
    |
assert payload/headers/retry count
    |
stop listener / clean up all resources
```

If teardown begins right after `KafkaTemplate.send().get()`, the test can delete the topic before the listener finishes retrying. Producer send acknowledgment **is not** consumer processing acknowledgment.

Tests should wait for observable outcomes (DB row, emitted event, DLT record, callback flag) with a timeout. Clean up only after verifying behavior or when aborting safely after a test failure.

### 26.1. Cleanup when tests fail before assertions

JUnit `@AfterEach` still runs if a test method throws an assertion/error in most normal cases. However, if the JVM is killed, the Docker daemon drops, or the process crashes, callbacks are not guaranteed to run. Private Testcontainers brokers with resource cleanup reduce orphan leaks, though CI still needs container/volume retention policies and watchdogs.

Never treat `@AfterEach` like a distributed transaction that can roll back all effects if the process is killed.

## 27. Security: never clean up shared resources with overly broad permissions

A test account permitted to delete any Kafka topic or RabbitMQ vhost can cause severe outages if pointed at the wrong environment.

Rules:

- CI integration brokers use isolated containers/namespaces.
- Never grant production credentials or write network access to test jobs unless strictly required.
- Give each run a unique prefix and ownership metadata.
- Clean up only against an allowlist of resources created by that run.
- Never run wildcard deletes across all topics/queues.
- Never reset offsets for production consumer groups.
- Never call RabbitMQ `purgeQueue`/`deleteQueue` on shared queue names.
- Never log SASL passwords, client certificates, auth headers, or PII inside messages.
- When tests require OAuth/SASL/TLS, generate test-only secrets and verify broker policy separately.
- Clean up test volumes, logs, and DLQs holding synthetic payloads per retention.
- On shared brokers, enforce scoped admin ACLs so tests cannot delete resources outside their namespace.

**If you are unsure whether a resource belongs to the test, do not delete it.** Using private broker containers is the simplest way to minimize blast radius.

## 28. Troubleshooting: passes alone, fails in the full suite

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Consumer misses new messages | Group already committed higher offset, shared topic, another listener stole record | Unique group/topic, inspect committed offsets |
| Fresh group reads old messages | Shared topic still holds retained records | Unique topic or private broker |
| `earliest` still skips early records | Group already has valid committed offset | Use fresh group or explicit offset reset |
| Message reappears on restart | Consumer never committed offset | Test at-least-once, idempotent processing |
| `GroupNotEmptyException` deleting group | Consumer/listener still active | Stop/close, wait for group inactive with timeout |
| `UnknownTopicOrPartitionException` in teardown | Topic never created or already deleted | Delete only owned-created topics, idempotent cleanup |
| Admin delete succeeds yet recreating same name fails | Topic deletion/metadata propagation not converged | Unique topic names; if reusing, bounded wait |
| Kafka client `TimeoutException` | Broker/startup/network/group assignment issue | Check bootstrap servers, image, logs |
| `KafkaTemplate` send passes, listener assertion fails | Send ack ≠ consume/ack | Await consumer outcome/offsets, isolate groups |
| Tests fail after previous class ran | Spring context cache points to stopped broker | Fix container/context lifecycle |
| Producer/consumer threads stay alive | Resources not closed | `try-with-resources`, stop listeners, `admin.close` |
| Main topic deleted yet DLT remains | Separate retry/DLT topics | Inventory all owned topics |
| Rabbit queue empty yet DLQ has records | Rejected/dead-lettered | Assert DLQ, clean up separately |
| Message returns after Rabbit purge | Unacked delivery requeued | Stop/ack/nack consumer before purge |
| JMS durable subscription keeps backlog | Closed consumer without unsubscribing | Unsubscribe per provider semantics |
| Parallel tests collide | Shared topics/groups/queues/resets | Unique namespaces or serialize tests |
| Stale Kafka Streams state | Reused internal topics/local state stores | Unique `application.id`, clean state dir |
| No Docker environment | Testcontainers runtime unavailable | Run stage on Docker-capable runner |
| Tests skipped yet Gradle green | Filters/conditional tests disabled | Report executed/skipped explicitly |
| Shared-broker cleanup breaks other tests | Wrong ownership scope | Never delete shared resources, use private broker |

### 28.1. Reading logs by layer

- **Container startup:** Kafka image pull, advertised listeners, Testcontainers environment.
- **Producer:** bootstrap address, serialization, send future, authorization.
- **Consumer:** group join, partition assignment, offsets, poll/commit errors.
- **Listener:** application handler, retries, ack mode, exception handler.
- **Admin:** topic/group existence, delete permissions, group membership, timeouts.
- **Spring:** context cache, bean lifecycles, `@ServiceConnection`/`@DynamicPropertySource` precedence.

Fix the exact failing layer instead of slapping a larger global timeout on every failure.

## 29. Practice exercises

### Exercise 1 — Fresh group vs. committed group

Run `sameGroupResumesAfterCommittedOffset` and `differentGroupCanReadSameRecord`. Explain: a restarted same group resumes from its committed offset; a fresh group from `earliest` sees existing records. Switch `auto.offset.reset` to `latest` in a sandbox branch and observe the effect on uncommitted groups.

### Exercise 2 — Remove manual commit

In `sameGroupResumesAfterCommittedOffset`, temporarily remove `first.commitSync()`. The restarted consumer can re-read `CREATED` before `PAID`. Restore it and explain why at-least-once delivery requires idempotent handlers.

### Exercise 3 — Fixed group ID

Change the unique group helper to return `"test-consumer"` and run the suite repeatedly against a shared broker. Describe false positives/flakiness from committed offsets and rebalances. Restore unique IDs.

### Exercise 4 — Shared topic

Change setup to use a single `orders-test` topic across all methods without deleting between tests. Observe old records skewing expectations when fresh groups read from `earliest`. Restore per-test topics.

### Exercise 5 — Try deleting a group while consumers are active

On a sandbox broker, keep a consumer subscribed/polling and call `deleteConsumerGroups` with that group ID. Observe the group-not-empty error, then close the consumer and retry with a timeout. Never try this on shared/staging groups.

### Exercise 6 — Cleanup after exception

Create a test that intentionally asserts `assertEquals("wrong", record.value())`. Verify `try-with-resources` still closes the consumer and `@AfterEach` still runs owned topic cleanup. Restore the assertion so the suite passes.

### Exercise 7 — RabbitMQ ready vs. unacked

Create a dedicated `RabbitMQContainer`, publish a message, consume without acking, and inspect ready/unacked state; after closing the consumer/channel, verify requeue behavior. Compare `purgeQueue`, `deleteQueue`, and stopping the consumer.

### Exercise 8 — RabbitMQ DLQ cleanup

Create a test queue with DLX/DLQ, reject a message with `requeue=false`, assert the DLQ record, then clean up **both the main queue and DLQ**. Never delete the DLQ before asserting.

### Exercise 9 — JMS durable subscription

Using an Artemis test broker, create a durable subscription with a unique client ID, disconnect, publish an event, reconnect, and assert the backlog. Unsubscribe/destroy test resources once inactive. Distinguish closing a consumer from unsubscribing.

### Exercise 10 — `@KafkaListener` Spring context cache

Create a `@KafkaListener` test in a dedicated context; run two classes sharing config with per-class container lifecycles. Observe why cached producers/listeners can hold a stopped bootstrap server, then fix it with proper lifecycle alignment.

### Exercise 11 — Retry/DLT isolation

Add Spring Kafka retry/DLT config and a test handler that intentionally fails. Assert the DLT record, then clean up the entire run's topic group. Never use wildcard deletes.

### Exercise 12 — Parallel CI jobs

Suppose two CI jobs share one test Kafka broker. Design run-ID-prefixed topic names and non-overlapping group IDs; apply per-job namespaces/ACLs and clean up only owned resources. When should you switch to broker-per-job?

### Exercise 13 — Kafka Streams state stores

Create a Kafka Streams test with stateful aggregation and run it twice with the same `application.id`/`state.dir`. Observe how leftover local state changes results; fix with a unique `application.id` and state dir/broker cleanup.

### Exercise 14 — Teardown reporting

Add a test report recording topic/group names, whether `deleteTopics` futures succeeded, broker container lifecycle, and active consumer count at shutdown. Never log SASL credentials or sensitive payloads.

## 30. Pre-finalization Messaging QA checklist

- [ ] Identified broker type (Kafka/RabbitMQ/JMS/other) and whether it is test-only or shared.
- [ ] Distinguished message state, consumer progress, and metadata as separate layers.
- [ ] Did not treat Kafka topic deletion as resetting all committed group offsets.
- [ ] Did not treat `auto.offset.reset=earliest` as resetting a group with valid commits.
- [ ] Kafka tests use unique topic/group IDs matched to their isolation scope.
- [ ] Consumer tests use timeouts/bounded polling, never fixed sleeps.
- [ ] Tests await producer send futures when proving messages were sent.
- [ ] Manual commits occur only after appropriate actions/assertions.
- [ ] Consumers/producers/admin/listener resources are closed/stopped.
- [ ] Teardown never deletes a group while active consumers remain.
- [ ] Deletes only test-owned topics/queues/groups.
- [ ] With class-scoped brokers, container lifecycle aligns with Spring context cache.
- [ ] Static containers are not blindly shared across classes.
- [ ] Parallel tests never reset or delete each other's resources.
- [ ] DLT/retry topics, retry listeners, and scheduled callbacks accounted for.
- [ ] RabbitMQ cleanup accounts for ready, unacked, DLQ, and exchanges/bindings.
- [ ] JMS cleanup accounts for durable subscriptions, sessions, and transactions.
- [ ] Kafka Streams cleanup accounts for `application.id`/internal topics/local state stores.
- [ ] `@DirtiesContext` not used as a substitute for broker cleanup.
- [ ] Observable cleanup failures are not swallowed.
- [ ] Never conclude tests passed when actually skipped/missing a broker.
- [ ] Never delete/purge/reset staging/production resources.
- [ ] CI orphan cleanup policy exists using allowlists/TTLs.
- [ ] Assertions verify actual messages/offsets/outcomes, not merely bean existence.

## 31. Final decision flow

```text
Messaging integration test needs state isolation?
         |
         +--> Private broker in Testcontainers?
         |       |
         |       +--> Per-test unique topics/groups
         |       +--> Close consumer/listener/admin/producer
         |       +--> Delete owned topics if needed
         |       +--> Dispose broker after test group/class
         |            -> Broker offsets/logs are reset
         |
         +--> Shared broker across classes/runs?
                 |
                 +--> Namespace resources by run ID
                 +--> Stop active consumers/listeners
                 +--> Assert outcome and commit/ack state
                 +--> Delete ONLY owned inactive groups
                 +--> Delete ONLY owned topics/queues/DLQ
                 +--> Await admin operations with deadlines
                 +--> Track orphan cleanup, never wildcard
```

**Key takeaway:** "Cleaning up messaging tests" is not a single delete command. **Kafka records, consumer offsets, group memberships, and resource handles each have their own lifecycle; the same goes for RabbitMQ unacked deliveries, DLQs, and JMS durable subscriptions.** For many integration suites, the least error-prone strategy is **a dedicated test broker container per test group, unique namespaces per method, closing consumers in the right order, and destroying the broker afterward**. When forced to use a shared broker, strictly manage ownership, offset/group state, admin operations, and protection of non-test resources.

## 32. Official References

- Apache Kafka — Consumer configuration, `auto.offset.reset`, and `enable.auto.commit`: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka — Basic operations, consumer groups/offset resets: https://kafka.apache.org/documentation/#basic_ops_consumer_group
- Apache Kafka — `KafkaConsumer` Javadoc (`poll`, `commitSync`, `close`, `position`, `seek`): https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
- Apache Kafka — Admin API, `deleteTopics`/`deleteConsumerGroups`: https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/admin/Admin.html
- Spring Boot 3.3 — Apache Kafka support: https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html
- Spring Boot 3.3 — Testcontainers `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Kafka — Testing applications, `@EmbeddedKafka`, and `KafkaTestUtils`: https://docs.spring.io/spring-kafka/reference/testing.html
- Spring Kafka — Container lifecycle, manual acknowledgments: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka — Retry topics and dead-letter topics: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Testcontainers Java — Kafka module, version-dependent API: https://java.testcontainers.org/modules/kafka/
- Testcontainers Java — JUnit Jupiter lifecycle: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Lifecycle and Spring context cache caveats: https://testcontainers.com/guides/testcontainers-container-lifecycle/
- RabbitMQ — Consumer acknowledgements and confirms: https://www.rabbitmq.com/docs/confirms
- RabbitMQ — Queues and queue lifecycle: https://www.rabbitmq.com/docs/queues
- RabbitMQ — Dead-letter exchanges: https://www.rabbitmq.com/docs/dlx
- Spring AMQP — `RabbitAdmin` / `AmqpAdmin`: https://docs.spring.io/spring-amqp/reference/amqp/admin.html
- Jakarta Messaging — Durable subscriptions and Session semantics: https://jakarta.ee/specifications/messaging/3.1/
- ActiveMQ Artemis — Address/queue/consumer management: https://activemq.apache.org/components/artemis/documentation/latest/
- JUnit Jupiter — Lifecycle annotations and execution: https://docs.junit.org/current/user-guide/
