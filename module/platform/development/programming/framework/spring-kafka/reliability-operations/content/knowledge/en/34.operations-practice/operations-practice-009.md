# Simulating Producer Fencing in Spring Kafka — Operations Practice and Recovery

## 1. Context: Two Producers Believe They Own the Same Transaction

A Spring Kafka system publishes events after processing orders. The application runs two replicas:

```text
             Kafka cluster
                  |
         Transaction coordinator
                  |
        transactional.id = orders-tx-0
                /       \
               /         \
              v           v
          Replica A    Replica B
          Producer A   Producer B
          (old epoch)  (new epoch)
```

Replica A is mid-transaction when it stalls or loses connectivity. Replica B starts up and acquires **the same `transactional.id`**. The Kafka coordinator issues a new producer generation and **fences** the older generation. When A tries to continue its transaction, the broker rejects A's operations so two different producers can never write to the same transactional state stream concurrently.

This mechanism is **producer fencing**. It is both a correctness safeguard for Kafka transactions and an operational signal you must understand:

- **Expected fencing:** a new process replaces an old producer, so the old producer must stop.
- **Unwanted fencing:** two active replicas accidentally share a transactional ID, causing them to steal ownership and fail repeatedly.
- **Deployment-bug fencing:** the same transaction prefix is copied verbatim across every pod, a transactional producer cache is misused, or code fails to close a fenced producer.
- **Flapping-incident fencing:** a worker stalls for a long pause and a new process takes ownership; when the old worker wakes up, it must not commit a transaction it no longer owns.

This lab belongs to **Spring Kafka Reliability Operations → Operations Practice → Simulating Producer Fencing**. The goal is not merely making a test throw `ProducerFencedException`, but understanding **why it happens, what Kafka protects, which data becomes visible, and when the application must stop or restart**.

We use **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka client 3.x, JUnit 5, and Embedded Kafka**, plus an optional **Testcontainers** setup closer to real deployments. If your project already uses Spring Boot 4 / Spring Kafka 4, keep the same fencing model and adjust test dependencies, Kafka client APIs, and embedded broker settings to match your version.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `transactional.id`, `producerId`, `producer epoch`, and `client.id`.
2. Spin up a Kafka broker suited for transactional producer integration tests.
3. Instantiate **two `KafkaProducer` instances sharing a `transactional.id`** to reproduce producer fencing.
4. Assert that the old producer cannot commit, the new producer commits, and `read_committed` reads only valid committed records.
5. Distinguish fencing from transaction timeouts, consumer rebalance/static-membership fencing, and authorization failures.
6. Understand the behavior of `spring.kafka.producer.transaction-id-prefix` across Spring Boot replicas.
7. Design recovery that never blindly retries on a fenced producer.
8. Write regression tests, metrics, alerts, and production runbooks.

---

## 2. Background: Kafka Producers Have Two Identity Layers

### 2.1. `client.id` Is Not a Transactional Identity

A producer may configure:

```properties
client.id=orders-producer-node-A
```

`client.id` labels clients in broker logs, metrics, and diagnostics. It **does not** govern whether a producer is authorized to continue a Kafka transaction.

Two producers with the same `client.id` do not automatically fence each other; they simply become harder to tell apart in logs and metrics.

### 2.2. `transactional.id` Represents the Logical Owner of a Transactional Producer

A transactional Kafka producer configures:

```properties
transactional.id=orders-publisher-slot-0
```

This ID allows the Kafka coordinator to link producer sessions across restarts and **fence older producer generations**. Kafka guarantees that at any point in time, a single transactional identity never has two active producer epochs operating as current owner.

**Never share a `transactional.id` across two independent producers that need to run concurrently.**

### 2.3. `producerId` and `producer epoch`

The Kafka broker/coordinator manages producer IDs and epochs. Conceptually:

```text
Initial state:
  transactional.id = orders-publisher-slot-0
  producerId       = P
  producerEpoch    = 7
  Producer A is allowed to write transactional records

Producer B calls initTransactions() with the same transactional.id:
  transactional.id = orders-publisher-slot-0
  producerId       = P (illustrative)
  producerEpoch    = 8
  Producer B becomes the new owner

Producer A:
  producerEpoch    = 7
  attempts commit/send -> rejected due to stale epoch
```

These numbers and ID reuse are illustrative. **Do not rely on whether `producerId` increments to detect fencing**; Kafka manages epochs and producer identities per version, and API error behavior is the contract to test.

### 2.4. Comparing Four Concepts

| Concept | Where Used | Governs Transactional Producer Fencing? |
| --- | --- | --- |
| `client.id` | Logs, metrics, client diagnostics | No |
| `transactional.id` | Kafka transaction coordinator | Yes |
| `producerId` | Broker/client protocol state | Participates |
| `producer epoch` | Fences older producer generations | Yes |
| `group.id` | Consumer group offsets and assignments | Not a transactional producer identity |
| `group.instance.id` | Consumer static membership | Can trigger a separate **consumer fencing** error |

Never confuse `ProducerFencedException` with `FencedInstanceIdException` from consumer static group membership. Both contain *fenced*, yet belong to completely different mechanisms.

---

## 3. Why Must Kafka Fence Producers?

Suppose producer A is executing a transaction:

```text
A: beginTransaction()
A: send(order-100, "CREATED")
A: send(order-101, "CREATED")

[Application A loses contact]
[Orchestrator starts B to take over]

B: initTransactions() with same transactional.id
B: beginTransaction()
B: send(order-102, "CREATED")
B: commitTransaction()

[A wakes up]
A: commitTransaction()   <-- rejected
```

If both A and B could commit under the same identity without epoch fencing, a stale worker could publish data after ownership had already moved to another worker, breaking ownership and recovery invariants of Kafka transactions.

Kafka uses the transaction coordinator to track generations and stop zombie producers. This mechanism **does not prevent every business duplicate in every architecture**; for instance, two **different** transactional IDs can still send the same business event twice if application logic duplicates it.

### 3.1. What Is a "Zombie" Producer?

A zombie producer is a producer **still executing somewhere** that **is no longer the rightful owner** of its transactional identity. It can arise when:

- A process hits a long stop-the-world GC pause.
- A worker loses network connectivity and later reconnects.
- An orchestrator replaces a container before the old instance fully stops.
- Two replicas are misconfigured with the same transactional ID.
- A scheduled task moves to a new node before the old node releases resources.

Kafka fencing forces the zombie producer to fail instead of committing as if nothing happened.

### 3.2. Fencing Is Fatal for the Old Producer Instance

After `ProducerFencedException`, the old producer must be treated as **permanently unusable**. Never catch the exception and call `send` or `commitTransaction` repeatedly on that same `KafkaProducer`.

The right response is closing the fenced producer, halting the work whose ownership was lost, logging diagnostic context, and letting the coordinator/orchestrator or service owner create a fresh producer and recover safely.

---

## 4. Practice Objectives and Expected Outcomes

We will build an integration test with two producers:

```text
Kafka Embedded Broker
  topic: fencing.same-id.it, 1 partition

Producer A:
  transactional.id = fencing-it-slot-1
  initTransactions()
  beginTransaction()
  send(A_UNCOMMITTED) -> broker appends in transaction A

Producer B:
  transactional.id = fencing-it-slot-1  [SAME AS A]
  initTransactions() -> Kafka bumps epoch / fences A
  beginTransaction()
  send(B_COMMITTED)
  commitTransaction() -> OK

Producer A:
  commitTransaction() -> ProducerFencedException

Consumer:
  isolation.level = read_committed
  seek earliest
  reads B_COMMITTED
  DOES NOT read aborted A_UNCOMMITTED

Outcome:
  A cannot commit
  B becomes the active producer
  Consumer does not see A's aborted transaction
```

Alongside the primary scenario, we need a **negative control**:

- Producers A and B use **distinct** `transactional.id`s.
- Both can commit.
- A `read_committed` consumer observes both records.

This proves the test does not fail arbitrarily—**the trigger is specifically contention over the same `transactional.id`**.

---

## 5. Two Principles for Setting Up a Test Broker

### 5.1. One Broker Suffices to Simulate Fencing

Producer fencing is governed by the transaction coordinator and producer epochs. A single Kafka broker with compatible internal transaction-state topic settings works for testing this.

For a **single broker**, lower replication and min ISR for internal topics:

```properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
offsets.topic.replication.factor=1
```

If forgotten, `initTransactions()` can time out because default broker replication factors cannot be met on a single node. That is a **test setup bug**, not proof of producer fencing.

### 5.2. Single-Broker Tests Do Not Prove Production Resilience

This test verifies **fencing logic and transaction visibility**, not leader failover, ISR durability, or coordinator survival when multiple brokers fail sequentially. Those require a multi-broker cluster or preproduction environment.

---

## 6. Configuring the Spring Boot + Kafka Test Project

### 6.1. Layout

```text
kafka-fencing-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/com/example/fencing/
            ├── ProducerFencingIT.java
            ├── DistinctIdIT.java
            └── SpringTransactionalPublisherIT.java
```

Reproducing fencing with raw Kafka clients does not require a full business app, though a Spring Boot project is useful if extending to `KafkaTemplate` and `KafkaTransactionManager`.

### 6.2. `build.gradle` for Spring Boot 3.x

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'org.springframework.kafka:spring-kafka-test'

    // Optional if also running Kafka via Docker.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'kafka-fencing-lab'
```

**Why not pin a separate `kafka-clients` version?** Spring Boot's BOM aligns client versions with Spring Kafka. If another dependency overrides it, inspect the dependency tree and compatibility matrix before running tests.

### 6.3. Selecting Dependencies by Boot Release

The example targets **Boot 3.x / Spring Kafka 3.x**. On **Boot 4.x / Spring Kafka 4.x**, projects may use modularized Kafka starters/tests:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-kafka'
testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
```

In that case, use the matching KRaft Embedded Kafka setup rather than legacy ZooKeeper test APIs. This lesson keeps Boot 3.x samples for a consistent baseline.

---

## 7. Core Lab: JUnit Creating Two Producers with the Same `transactional.id`

Below is a Java test runnable inside a Spring test context. We use `@EmbeddedKafka` for the broker while explicitly instantiating two Apache Kafka `KafkaProducer` objects so we control the **exact** `transactional.id` rather than relying on `DefaultKafkaProducerFactory`'s internal suffixing and caching.

### 7.1. Full Test

Create `src/test/java/com/example/fencing/ProducerFencingIT.java`:

```java
package com.example.fencing;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.ProducerFencedException;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ProducerFencingIT.TestConfig.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"fencing.same-id.it", "fencing.distinct-id.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers",
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1",
        "auto.create.topics.enable=false"
    }
)
class ProducerFencingIT {

    private static final String SAME_ID_TOPIC =
        "fencing.same-id.it";

    private static final String DIFFERENT_ID_TOPIC =
        "fencing.distinct-id.it";

    @Configuration
    static class TestConfig {
        // Embedded broker registered by spring-kafka-test.
    }

    @Autowired
    EmbeddedKafkaBroker broker;

    private Properties producerProps(
            String transactionalId, String clientId) {

        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString());
        props.put(ProducerConfig.CLIENT_ID_CONFIG, clientId);
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            transactionalId);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.RETRIES_CONFIG, 5);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
        props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG,
            30_000);
        return props;
    }

    private Properties consumerProps() {
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString());
        props.put(ConsumerConfig.GROUP_ID_CONFIG,
            "fencing-observer-" + java.util.UUID.randomUUID());
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
            "read_committed");
        return props;
    }

    private List<String> committedValues(
            String topic, String expectedValue) {

        List<String> values = new ArrayList<>();
        TopicPartition partition =
            new TopicPartition(topic, 0);

        try (KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(consumerProps())) {

            consumer.assign(List.of(partition));
            consumer.seekToBeginning(List.of(partition));

            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(15);

            boolean found = false;

            while (System.nanoTime() < deadline && !found) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(250));

                for (ConsumerRecord<String, String> record
                        : records) {
                    values.add(record.value());
                    if (expectedValue.equals(record.value())) {
                        found = true;
                    }
                }
            }
        }
        return values;
    }

    @Test
    void newerProducerFencesOlderProducerWithSameId()
            throws Exception {

        String transactionalId = "fencing-demo-slot-1";

        try (KafkaProducer<String, String> a =
                 new KafkaProducer<>(
                     producerProps(transactionalId, "producer-A"));
             KafkaProducer<String, String> b =
                 new KafkaProducer<>(
                     producerProps(transactionalId, "producer-B"))) {

            // 1. A acquires ownership and begins a transaction.
            a.initTransactions();
            a.beginTransaction();

            a.send(new ProducerRecord<>(
                SAME_ID_TOPIC, "A", "A_UNCOMMITTED"))
                .get(10, TimeUnit.SECONDS);

            // 2. B initializes with the same transactional.id.
            //    Coordinator advances to a new producer epoch.
            b.initTransactions();
            b.beginTransaction();

            b.send(new ProducerRecord<>(
                SAME_ID_TOPIC, "B", "B_COMMITTED"))
                .get(10, TimeUnit.SECONDS);

            b.commitTransaction();

            // 3. A is rejected when committing the stale transaction.
            assertThrows(
                ProducerFencedException.class,
                a::commitTransaction);

            // Never continue using A after fencing.
        }

        // 4. read_committed does not see A_UNCOMMITTED.
        List<String> committed =
            committedValues(SAME_ID_TOPIC, "B_COMMITTED");

        assertTrue(committed.contains("B_COMMITTED"));
        assertFalse(committed.contains("A_UNCOMMITTED"));
        assertEquals(List.of("B_COMMITTED"), committed);
    }

    @Test
    void distinctTransactionalIdsCanBothCommit()
            throws Exception {

        try (KafkaProducer<String, String> a =
                 new KafkaProducer<>(
                     producerProps(
                         "fencing-distinct-A", "producer-A2"));
             KafkaProducer<String, String> b =
                 new KafkaProducer<>(
                     producerProps(
                         "fencing-distinct-B", "producer-B2"))) {

            a.initTransactions();
            b.initTransactions();

            a.beginTransaction();
            a.send(new ProducerRecord<>(
                DIFFERENT_ID_TOPIC, "A2", "A2_COMMITTED"))
                .get(10, TimeUnit.SECONDS);
            a.commitTransaction();

            b.beginTransaction();
            b.send(new ProducerRecord<>(
                DIFFERENT_ID_TOPIC, "B2", "B2_COMMITTED"))
                .get(10, TimeUnit.SECONDS);
            b.commitTransaction();
        }

        List<String> committed =
            committedValues(
                DIFFERENT_ID_TOPIC, "B2_COMMITTED");

        assertTrue(committed.contains("A2_COMMITTED"));
        assertTrue(committed.contains("B2_COMMITTED"));
        assertEquals(2, committed.size());
    }
}
```

### 7.2. What Does This Test Prove?

- `a.initTransactions()` establishes A as the valid producer for the chosen transactional ID.
- `a.beginTransaction()` and `a.send(...).get(...)` write a record into A's **uncommitted** transaction.
- `b.initTransactions()` with the **same ID** instructs the coordinator to initialize a new generation; A's open transaction is aborted/ended during recovery/fencing.
- `b.commitTransaction()` succeeds for the new transaction.
- `a.commitTransaction()` must fail because producer A no longer holds commit authority.
- A `read_committed` consumer returns only records from committed transactions, hiding the aborted transaction's record from the application layer.
- The negative control uses **two distinct IDs** and shows both producers commit cleanly.

**Version and timing note:** the example uses an explicit sequence, awaiting A's send future and letting B call `initTransactions` before A commits. In other variations, fencing errors may surface at `send`, `flush`, `commitTransaction`, or in callbacks, and may be wrapped by Kafka exceptions. Tests must assert the exception type at the right operation for your target Kafka client version rather than matching fixed log strings.

### 7.3. Why Send A's Record Before B Appears?

If A never began a transaction or sent a record, it would still be fenced when B uses the same ID, yet we would not observe **uncommitted/aborted** data visibility. Sending A's record into an open transaction before B initializes verifies both *fencing* and *transactional visibility*.

### 7.4. Why Not Call `abortTransaction()` on A After Fencing?

Fencing is fatal to the old producer; afterward A is no longer a valid owner. Calling `abortTransaction()` or `commitTransaction()` again is unsafe recovery and will throw again. Close the old producer; the new rightful producer and coordinator handle cleanup per the transaction protocol.

### 7.5. Expected Output When Running the Test

```text
[Producer A] initTransactions OK
[Producer A] begin + send A_UNCOMMITTED OK
[Producer B] initTransactions using same transactional.id OK
[Producer B] begin + send B_COMMITTED OK
[Producer B] commitTransaction OK
[Producer A] commitTransaction -> ProducerFencedException
[Consumer read_committed] -> B_COMMITTED only

Second test:
[Producer A2, tx.id A] commit OK
[Producer B2, tx.id B] commit OK
[Consumer read_committed] -> A2_COMMITTED, B2_COMMITTED
```

Actual logs vary by Kafka version. Never assert exact log strings; assert exception categories and **consumer outcomes**.

---

## 8. Checking with `read_uncommitted`: Observing Aborted Transaction Records

In Kafka, a record appended to the log inside transaction A can still be read by a consumer configured with `isolation.level=read_uncommitted` even though the transaction ultimately aborted. A `read_committed` consumer hides that record.

To extend the test, add another consumer:

```java
Properties props = consumerProps();
props.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_uncommitted");

try (KafkaConsumer<String, String> c =
        new KafkaConsumer<>(props)) {

    TopicPartition tp =
        new TopicPartition("fencing.same-id.it", 0);

    c.assign(List.of(tp));
    c.seekToBeginning(List.of(tp));

    // Poll until the scenario records are observed.
    // Observe A_UNCOMMITTED and B_COMMITTED
    // depending on Kafka log/retention and test isolation.
}
```

### 8.1. Meaning of the Results

| Record | Transaction Status | `read_uncommitted` Consumer | `read_committed` Consumer |
| --- | --- | --- | --- |
| `A_UNCOMMITTED` | A fenced, transaction aborted | May see appended record | **No** |
| `B_COMMITTED` | B committed successfully | Yes | Yes |
| Control markers | Kafka transaction protocol | Not exposed as normal business records | Not exposed as normal business records |

Never use `read_uncommitted` for business consumers that must see only committed transactional records. This is especially critical when verifying "no partial transactions leak."

### 8.2. Why Asserting Values Alone Is Not Enough

If multiple tests share a topic with leftover data, seeing `B_COMMITTED` does not prove it came from the current run. This test uses dedicated topics; in larger suites, use test-namespaced topics/transactional IDs, fresh consumer groups, or isolated brokers. In shared environments, embed a correlation/test-run ID in keys/values and match precisely.

---

## 9. Moving This Scenario into Testcontainers

### 9.1. When to Choose Testcontainers

Embedded Kafka suffices to reproduce fencing. Testcontainers fits better when you want to:

- Run the broker in a separate process/container rather than the test JVM.
- Pin a specific Kafka image and broker version.
- Combine Kafka, databases, mock APIs, and network proxies.
- Simulate restarts/pauses and reconnections.
- Collect Kafka container logs and metrics for production-like analysis.

Testcontainers does not create an HA cluster by default: one Kafka container is still **a single broker**.

### 9.2. Kafka Container with Internal Transaction State Topic

Testcontainers 1.x example:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class KafkaContainerFencingIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"))
            .withEnv(
                "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
            .withEnv(
                "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
            .withEnv(
                "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1");

    @Test
    void reproduceFencing() throws Exception {
        String bootstrap = kafka.getBootstrapServers();

        // Create the topic with AdminClient before sending.
        // Use bootstrap in producerProps(...).
        // Repeat the Producer A / Producer B scenario
        // with the same transactional.id as in section 7.
    }
}
```

**Important:** this demonstrates **container infrastructure only**, not a full standalone test; create the topic and `KafkaProducer`/`KafkaConsumer` instances as in section 7. In newer Testcontainers versions, Kafka container modules/packages changed—use `org.testcontainers.kafka.ConfluentKafkaContainer` per your installed version's docs.

If environment variables are not picked up by the container startup script as expected, inspect effective broker configurations and container logs. The transaction coordinator must initialize cleanly before simulating fencing.

### 9.3. Creating the Topic with `AdminClient`

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;

try (AdminClient admin = AdminClient.create(
        Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers()))) {

    admin.createTopics(List.of(
        new NewTopic(
            "fencing.container.it",
            1,
            (short) 1)))
        .all()
        .get(15, TimeUnit.SECONDS);
}
```

If reusing a fixed topic name against a stateful container, handle `TopicExistsException` explicitly. Never enable auto-create just to "simplify tests" and accidentally mask ACL or topic configuration bugs.

### 9.4. Does Adding Another Kafka Broker Help Reproduce Fencing Better?

No. Producer fencing is a **transaction coordinator and epoch** mechanism; one broker suffices for those semantics. Multiple brokers are only needed when testing coordinator failover, ISR, and availability. Spinning up three brokers while still misconfiguring transactional IDs will not make this error go away.

---

## 10. Spring Kafka `transaction-id-prefix` in Real Applications

### 10.1. Spring Boot Configuration

Spring Boot / Spring Kafka creates a transactional producer factory when configured with:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
```

`localhost:9092` is for local use only; in Kubernetes/CI, inject bootstrap servers from the environment/platform.

When a transaction ID prefix is configured, Spring Kafka manages transactional producers via `DefaultKafkaProducerFactory`. Spring Boot auto-configures the matching transaction manager and template when bean conditions match. **Do not equate the prefix with a single fixed `transactional.id`**: the factory generates suffixed IDs for cached producers and concurrent transactions.

### 10.2. How Does the Producer Factory Generate Transactional IDs?

Conceptually:

```text
Spring Boot property:
  transaction-id-prefix = orders-node-A-

DefaultKafkaProducerFactory:
  transactional.id = orders-node-A-0
  transactional.id = orders-node-A-1
  transactional.id = orders-node-A-2
  ...

Another replica:
  transaction-id-prefix = orders-node-B-
  transactional.id = orders-node-B-0
  transactional.id = orders-node-B-1
  ...
```

Actual suffixes and pooling behavior vary across Spring Kafka versions and suffix strategies. **Do not write production tests assuming a hardcoded suffix format.** The rule is that transactional IDs managed by the factory must never collide across two concurrently active producer owners.

### 10.3. Mistake: Two Replicas Sharing Prefix and Suffix Space

```text
Replica A:
  transaction-id-prefix = orders-tx-
  producer.id = orders-tx-0

Replica B:
  transaction-id-prefix = orders-tx-
  producer.id = orders-tx-0

Replica A <---- FENCED ----> Replica B
```

If both replicas generate the same `transactional.id`, they repeatedly fence each other, especially after scale-out or rolling deployments. This is a common misconfiguration.

### 10.4. Prefix Naming Strategies

One approach uses **logical owner identity**:

```text
Service: orders-publisher
Namespace: production
Logical owner: shard-03

transaction-id-prefix = orders-prod-shard-03-
```

Key considerations:

1. Prefixes must be **unique among concurrently active owners**.
2. If an owner is replaced while the old process might still be alive, reusing the same identity **can be intentional** to fence zombies.
3. If every restart generates a random UUID even for the same logical owner, Kafka cannot use a shared `transactional.id` to fence the old producer; assignment-layer fencing/leases are also needed.
4. If every replica emits the exact same static prefix, that is a collision bug.
5. When using `HOSTNAME` or Kubernetes pod names, remember Deployment pod names change on every rollout; use StatefulSet ordinals or stable assignment IDs when continuous owner identity is required.

No single prefix formula fits every system. Define **who owns transaction scope**, replica counts, shard/partition ownership, and how workers are replaced.

### 10.5. Do Not Mint a Fresh Random ID per Transaction Just to Avoid Fencing

```text
transactional.id = random UUID every send
```

While this avoids collisions between producers, it defeats a core purpose of stable transactional IDs: letting a new producer session fence a stale session of the same logical owner. It also bloats the Kafka coordinator with unnecessary transactional IDs. Never use random per-message IDs as a blanket "fix" for fencing.

---

## 11. Spring Kafka Transactions with `KafkaTemplate`

### 11.1. Using a Spring-Managed Transactional Producer

Once `transaction-id-prefix` is set, a service can publish atomically inside a Kafka transaction:

```java
package example.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class TransactionalOrderPublisher {

    private final KafkaTemplate<String, String> template;

    public TransactionalOrderPublisher(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void publishOrder(
            String orderId, String json) {

        template.executeInTransaction(operations -> {
            operations.send(
                "orders.events", orderId, json);
            return null;
        });
    }
}
```

This lets Spring Kafka borrow a transactional producer from the factory and manage begin/commit/abort around the callback. It differs from the raw `KafkaProducer` example in section 7, where we intentionally instantiate two producers with identical IDs to trigger fencing deterministically.

### 11.2. `@Transactional` with Kafka

Spring Kafka provides `KafkaTransactionManager` to manage Kafka transactions. In applications also using a database/JPA, qualify which transaction manager is intended:

```java
@Transactional("kafkaTransactionManager")
public void publishInKafkaTransaction(...) {
    kafkaTemplate.send(...);
}
```

This illustrates wiring structure; use actual bean names and properly configured factories. Never place an unqualified `@Transactional` and assume Kafka and JDBC share a single ACID transaction.

### 11.3. How Does Fencing Surface Through Spring?

When a `KafkaProducer` inside the factory is fenced:

- Send or commit operations fail with `ProducerFencedException` or an epoch-related cause.
- Spring transaction synchronization may wrap the exception per integration layer.
- The factory must not continue reusing a fatally errored producer.
- The application should classify this as an **ownership / fatal transactional producer error**, not a single-record serialization error that can be skipped.

To write **deterministic fencing tests**, use raw `KafkaProducer` instances as in section 7. Testing Spring-managed factories requires pinning exact transactional IDs or controlling the suffix strategy and starting matching contexts/instances—never assume "two `KafkaTemplate`s will automatically fence."

---

## 12. Valid Fencing vs. Misconfigured Fencing

### 12.1. Valid Case: Failover of One Logical Owner

```text
Shard 03 -> owner A
A is processing transaction T, then loses lease

Shard 03 -> owner B
B receives valid assignment
B uses shard 03's transactional identity
Kafka fences A

A wakes up -> ProducerFencedException
A cannot publish anymore
```

Fencing protects correctness. Still, transferring ownership of a **business shard** must be coordinated by an orchestrator/lease manager, not solely by Kafka transactional IDs. Kafka has no visibility into A's non-Kafka side effects.

### 12.2. Invalid Case: Every Pod Shares the Same Name

```text
orders-service pod-1 -> orders-tx-0
orders-service pod-2 -> orders-tx-0
orders-service pod-3 -> orders-tx-0
```

If every pod believes it owns `orders-tx-0`, producer epochs keep bumping continuously, causing transaction failures, poor throughput, retry loops, and unstable processing.

Fix this by namespacing transactional IDs by owner, replica, or shard so two active owners never collide.

### 12.3. A Paused Pod Differs from a Dead Pod

If pod A stalls, the orchestrator may start pod B. Pod A can wake up after B already took over. Producer fencing blocks A from committing with its stale epoch, yet **A may still trigger external non-Kafka side effects** if it calls HTTP/DB endpoints before hitting the Kafka fencing exception.

Therefore, enforce lease/fencing tokens at business resource layers or use idempotency/outbox patterns for non-Kafka operations.

---

## 13. Fencing and Related Exceptions

### 13.1. `ProducerFencedException`

`org.apache.kafka.common.errors.ProducerFencedException` indicates a producer was fenced because another producer initialized with the same transactional identity or producer epoch ownership shifted.

This is **fatal for the fenced producer instance**. Never retry sends or commits on that instance.

### 13.2. `InvalidProducerEpochException`

A protocol error indicating an invalid producer epoch. Depending on broker/client paths and timing, operators may encounter this or a similar root cause when an epoch is stale. Inspect the full stack trace/cause chain and Kafka logs rather than regex-matching one message.

### 13.3. `OutOfOrderSequenceException`

Relates to idempotent producer sequence tracking. Do not assume every sequence error stems from a duplicate `transactional.id`. Analyze producer epoch/transaction state, broker responses, and client behavior.

### 13.4. `TransactionAbortedException` and Timeouts

A transaction can abort due to timeouts or application errors. An aborted transaction **is not necessarily producer fencing**. For abortable errors, client APIs may abort and continue in some cases; for a fenced producer, do not do so.

### 13.5. `TransactionalIdAuthorizationException`

If the principal lacks permission for the transactional ID, the broker rejects `initTransactions()` or transaction operations. This is a **security/ACL issue**—never "fix" it by randomizing IDs or granting wildcard ACLs.

### 13.6. `FencedInstanceIdException`

A consumer using `group.instance.id` (static membership) can be fenced if two consumers contend for the same static member identity. That happens in the **consumer group coordinator**, distinct from producer transaction epoch fencing. The names look similar, yet the runbooks and configurations differ completely.

### 13.7. Identification Table

| Exception / Symptom | Typical Context | Direction |
| --- | --- | --- |
| `ProducerFencedException` | Transactional producer lost ownership | Close stale producer; check ID collisions/leases |
| `InvalidProducerEpochException` | Invalid producer epoch | Investigate epoch state and nested causes |
| `OutOfOrderSequenceException` | Inconsistent sequence tracking | Inspect idempotent producer / retries |
| Transaction timeout | Transaction held open too long | Check processing duration and broker max timeout |
| Transactional ID authorization | Missing ACLs | Grant least-privilege permissions |
| `FencedInstanceIdException` | Duplicate consumer static membership | Fix `group.instance.id`, not tx prefix |
| `TimeoutException` from `initTransactions` | Broker/coordinator not ready or internal topic short on ISR | Verify broker setup before assuming fencing |

---

## 14. Why Never Catch `ProducerFencedException` and Retry?

This is an anti-pattern:

```java
while (true) {
    try {
        producer.commitTransaction();
        break;
    } catch (ProducerFencedException ex) {
        // WRONG: producer lost ownership; retrying will not restore it.
        Thread.sleep(1000);
    }
}
```

Once a producer is fenced, its old epoch never becomes valid again. Retrying on the same instance stalls recovery and hides the root cause.

### 14.1. Proper Recovery Flow

```text
Catch ProducerFencedException
            |
            v
  Mark producer instance unusable
            |
            v
  Stop affected workflow / partition
            |
            v
  Close producer and stop stale owner
            |
            v
  Collect tx.id / owner / epoch diagnostics
            |
            v
  Reconcile Kafka and business outcomes
            |
            v
  Coordinator assigns owner legitimately
            |
            v
  New producer initializes transaction
            |
            v
  Resume only if idempotency/offset safe
```

**Not** every producer should be manually recreated inside a `catch` block. With Spring-managed producers and orchestration, it is usually safer to let container lifecycle/restart policies take over once the failed owner is identified.

### 14.2. When Should You Alert?

If fencing happens once during a clean logical ownership handoff, it can be an expected recovery event. If the same transactional ID is repeatedly fenced over several minutes while replicas appear healthy, that signals a **transactional ID collision** and warrants an immediate alert.

Avoid configuring "any `ProducerFencedException` is Sev-1" if the system uses valid failover handoffs; tie alerts to business output impact and frequency.

---

## 15. Comparing Fencing with Transaction Timeouts

An independent transaction timeout also causes aborts and producer failures, though its cause differs from transactional ID contention.

| Aspect | Producer Fencing | Transaction Timeout |
| --- | --- | --- |
| Trigger | Another producer takes the same ID / new epoch ownership | Transaction runs past time limit |
| Symptom | Fencing / invalid epoch errors | Timeout / abort-related errors |
| Requires Producer B? | In ID-collision tests: yes | No |
| Fixed by raising timeout? | No | Only when transaction duration is legitimately longer |
| Fixed by unique ID per active owner? | Often yes | Insufficient |
| Uncommitted data | Hidden from `read_committed` once aborted | Same |
| Recovery | Stop stale owner, reinitialize legitimately | Investigate duration, timeout, and idempotent retry |

### 15.1. `transaction.timeout.ms` and Broker Max Timeout

`KafkaProducer` configures `transaction.timeout.ms`; the broker configures `transaction.max.timeout.ms`. If a client requests a timeout exceeding the broker's maximum, `initTransactions` / transaction setup is rejected accordingly.

For slow workloads, never raise transaction timeouts indefinitely because:

- Long-running transactions stall the Last Stable Offset, blocking `read_committed` consumers.
- Large volumes of uncommitted records pile up.
- Failure recovery slows down.
- Underlying latency/bottlenecks stay hidden.

A job processing millions of records should split work into smaller transactions/partitions rather than holding one Kafka transaction open for hours.

---

## 16. Is Producer Fencing Related to Idempotence?

Related, yet not identical.

### 16.1. Idempotent Producer

An idempotent Kafka producer uses producer IDs and sequence numbers to prevent duplicate records caused by **producer retries** within protocol/session bounds.

```yaml
spring:
  kafka:
    producer:
      properties:
        enable.idempotence: true
```

This does not guarantee every business event appears once. If a service calls `send` twice for the same order due to a retried HTTP request, Kafka still writes two valid events.

### 16.2. Transactional Producer

A transactional producer adds `transactional.id`, begin/commit/abort, producer epoch fencing, and atomic coordination of records and offsets within Kafka transactions.

```text
Idempotent:
  prevents certain duplicates from send retries within a producer session

Transactional:
  atomic visibility of records within a transaction
  ownership fencing by transactional.id
  can enlist Kafka consumed offsets in the transaction
```

Without `transactional.id`, testing two idempotent producers sharing `client.id` will not produce transactional producer fencing in this way.

### 16.3. Business Idempotency Is Still Required

Even when producer A is fenced completely accurately:

- Worker B may reprocess an input that already committed to a DB.
- The app may emit a new event for the same business operation on duplicate requests.
- Consumers may reprocess records if offset commits did not finish.
- External HTTP/payment/email side effects can repeat.

Therefore, enforce stable event/business IDs, unique constraints, transactional outboxes, or appropriate deduplication.

---

## 17. What If Producer A Sent a Message Before Being Fenced?

Three scenarios must be distinguished.

### 17.1. Message Belongs to A's Uncommitted Transaction

```text
A begin
A send X (broker append)
B inits with same transactional.id
A transaction aborted/fenced
B commit Y

read_committed -> Y
read_uncommitted -> may see both X and Y
```

X is not considered a committed business record.

### 17.2. A Committed Before B Initialized

```text
A begin
A send X
A commit -> success

B inits with same transactional.id
B begin, send Y, commit

read_committed -> X and Y
```

Fencing **does not erase** previously committed transactions. It only prevents A from committing transactions **after its epoch expires**.

### 17.3. A Wrote to an External DB Before Being Fenced

```text
A begins Kafka transaction
A updates PostgreSQL -> COMMIT
B init same tx.id, fences A
A Kafka commit fails
```

Kafka does not roll back PostgreSQL. When B reprocesses the input, the DB can hit duplicates or create new side effects if idempotency is missing. That is why producer fencing is not a whole-application distributed transaction.

---

## 18. Spring Kafka Consumer–Producer Transactions and Fencing

A consumer reading input and publishing output can use Kafka transactions to bind **output Kafka records** and **consumed offsets** together (when container and transaction manager are configured properly).

```text
Consumer group orders-transform
          |
      input record E
          |
          v
  Kafka transactional producer
          |
  send transformed output
  send offsets to transaction
          |
          v
    commit transaction
```

When an older owner is fenced before committing:

- Uncommitted outputs from the old producer remain invisible to `read_committed` consumers.
- Uncommitted offsets from the old Kafka transaction allow safe replay after recovery.
- The new owner can receive and reprocess the input legitimately.
- Side effects outside Kafka still require idempotency.

### 18.1. `sendOffsetsToTransaction` (Kafka Client API)

In the raw Kafka Producer API, Kafka-to-Kafka transactions can enlist offsets:

```java
// API illustration: consumerGroupMetadata comes from consumer
// and the offsets map is supplied accurately by the application.
producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata());
```

This lab's test **does not need** to call this API because it demonstrates producer fencing and transactional visibility only. When adding source consumers/offsets, test group assignments, transaction fencing, and restart/replay semantics explicitly.

### 18.2. No Automatic Synchronization with JDBC

`KafkaTransactionManager` does not automatically create atomicity with a `DataSourceTransactionManager`. Pipelines requiring effectively-once **business effects** typically add transactional outboxes, idempotent consumers, or business-key reconciliation.

---

## 19. Simulating Fencing in Kubernetes and Multi-Replica Deployments

### 19.1. Misconfiguration to Reproduce (Test/Staging Only)

Two replicas both configure:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

If each replica generates suffix `0`, their actual transactional IDs collide. Once traffic flows through both, one gets fenced; if both keep recreating producers, a **fencing storm** erupts.

Never deploy this configuration intentionally to production just to observe failures.

### 19.2. Configuring by Logical Owner

Example where an operator assigns partitions/shards:

```text
Deployment logical owner 0:
  transaction-id-prefix = orders-live-owner-0-

Deployment logical owner 1:
  transaction-id-prefix = orders-live-owner-1-

Deployment logical owner 2:
  transaction-id-prefix = orders-live-owner-2-
```

With a StatefulSet, the ordinal can supply a stable logical owner ID in certain topologies. With a Deployment, pod names change on every rollout, so understand how the app maintains continuous ownership.

### 19.3. When an Old Worker Wakes Up

If an old worker loses its lease and a new worker takes the same logical owner identity, Kafka fencing stops the old worker from publishing afterward. Still, the old worker must **halt non-Kafka work itself** once its lease expires. Enforce lease/fencing tokens or DB ownership checks at business resource layers whenever required.

### 19.4. Common Sources of ID Collisions

- Copying the same `transaction-id-prefix` across all replicas via a shared ConfigMap.
- Hardcoding a fixed `transactional.id` in the app instead of letting the producer factory manage instances.
- Two environments (staging/prod) accidentally pointing to the same Kafka cluster with the same prefix.
- Two workers receiving the same logical owner due to a scheduler/lease race.
- Rolling restarts not waiting for the old process to stop when identity assignment lacks fencing/recovery rules.
- Suffixes built from unset/fallback env vars causing every pod to emit the exact same ID.

---

## 20. Observing Producer Fencing in Logs, Metrics, and Tracing

### 20.1. Structured Logging

A useful structured event log:

```text
event=kafka_producer_fenced
service=orders-publisher
environment=staging
owner=shard-03
transactionalId=orders-staging-shard-03-0
clientId=orders-publisher-pod-6
pod=orders-publisher-pod-6
operation=commitTransaction
exception=ProducerFencedException
action=close_stale_producer
```

Include only necessary operational metadata. Never log customer payloads, credentials, SASL configs, or private keys.

### 20.2. Signals to Monitor

| Signal | Explanation |
| --- | --- |
| Count of producer fencing exceptions | Distinguishes collisions from expected ownership transfers |
| Transaction commit failures | Measures impact on outputs |
| Transaction abort rate | Separates business aborts from fencing |
| Kafka producer send errors/latency | Tracks broker/client health |
| Consumer group lag | Detects stalled replays or processing |
| Rebalance frequency | Flags assignment instability |
| Producer instance restarts | Detects fencing-induced crash loops |
| Business output count / duplicate keys | Confirms correctness |
| Kafka broker transaction coordinator logs | Tracks epoch and owner transitions |
| DLT/backlog (if pipeline uses one) | Ensures failing records are handled/reconciled |

Never use `transactionalId` as a metric tag if producers/sessions create unbounded IDs; use bounded tags like logical owner, shard, or namespace, and log full IDs in controlled logs.

### 20.3. Distinguishing Expected vs. Unexpected Fencing

Example of a clean failover:

```text
T=10:00:00 A's lease expires
T=10:00:02 B becomes owner
T=10:00:03 B init tx.id
T=10:00:04 A is fenced and stops

Expected: one fencing event on handoff.
```

Example of a misconfigured collision:

```text
T=10:00:00 A init tx.id
T=10:00:01 B init same tx.id -> fences A
T=10:00:02 A recreates producer -> fences B
T=10:00:03 B recreates producer -> fences A
...
```

This is a collision / fencing storm requiring rapid intervention. Fixing retry code alone will not stop it while the prefix conflict persists.

---

## 21. Runbook When `ProducerFencedException` Occurs

### Step 1 — Confirm Scope

Record:

- Service, namespace, deployment version, pod ID.
- Actual `transactional.id` and `client.id`.
- Timestamp and operation (`initTransactions` / `send` / `commit`).
- Kafka cluster, broker versions, and coordinator logs.
- Active replica count and owner/shard assignments.
- Recent rollouts, pod restarts, lease handoffs, or network disruptions.

### Step 2 — Check for Collisions

If two pods/instances log the same transactional ID within the same window:

- Verify whether it is a valid failover of **the same logical owner**.
- If not, inspect `transaction-id-prefix`, suffix strategies, and owner identities.
- Audit ConfigMaps, Helm charts, environment variables, and fallback defaults.
- Stop continuous restart loops if causing widespread impact.

### Step 3 — Never Attempt to Commit a Fenced Producer

Do not retry directly on the stale producer. Ensure the deposed worker stops writing to Kafka or executing unprotected non-Kafka side effects.

### Step 4 — Reconcile State

Determine:

- Whether A's transaction committed before B initialized.
- Whether A's records belong to an aborted or committed transaction.
- Which business events B has already written.
- Whether the consumer group replayed any records.
- Which DB/external side effects occurred prior to fencing.

When needed, read topics with a `read_committed` consumer and reconcile by event ID / business key. Never use `read_uncommitted` to decide whether an event was legitimately published.

### Step 5 — Fix Ownership / Identity

Select an appropriate transactional ID prefix/schema. If caused by two replicas sharing a prefix, enforce uniqueness across active owners. If it was a valid failover, ensure the old owner truly stopped and the new owner has authority to proceed.

### Step 6 — Controlled Recovery

- Close stale producers.
- Initialize a new producer **only once ownership is valid**.
- Maintain idempotent business processing.
- Resume source offsets per contract.
- Check producer transactions, consumer lag, and DLTs.
- Reconcile business outputs and verify zero duplicate side effects.

### Step 7 — Prevent Recurrence

Add tests verifying:

1. Two live replicas never produce the same transactional IDs outside ownership handoffs.
2. When a new owner initializes with the same ID, the old producer is fenced and stops.
3. No retries occur on the old producer after fencing.
4. Business outputs do not duplicate across replays.
5. Alerts distinguish expected failovers from collision storms.

---

## 22. Common Pitfalls When Simulating Producer Fencing

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Forgetting `transaction.state.log.replication.factor=1` on single broker | `initTransactions` times out | Adjust test broker settings |
| Setting `enable.idempotence=true` without `transactional.id` | No transactional fencing occurs | Configure a transactional producer |
| Sharing `client.id` expecting fencing | Test throws no exception | Share the **same `transactional.id`** |
| Two producers with distinct transactional IDs | Both commit | Expected behavior; use as negative control |
| Letting A commit before B initializes | A is not fenced on already-committed tx | Keep A's transaction open until B inits |
| Not awaiting A's `send` future | Varying test races/timing | Await ACK before B inits |
| Using `read_uncommitted` to assert invisible records | Sees A's aborted record | Use `read_committed` |
| Asserting exact Kafka log strings | Tests break on upgrades | Assert exceptions + committed outputs |
| Using Spring Kafka prefix without controlling suffixes | Fails to reproduce exact ID collision | Use raw `KafkaProducer` for deterministic tests |
| Catching exception and retrying same producer | Fencing loop | Close stale producer |
| Using random ID per transaction | Loses effective zombie fencing | Namespace by owner/shard |
| Assuming Kafka tx makes DB atomic | Duplicate side effects | Outbox / idempotency |
| Running tests on shared broker topics | Cross-test data pollution | Isolate topics and tx IDs |
| Forgetting DLT/offset consequences | Incomplete business reconciliation | Test end-to-end recovery |
| Restarting Docker container changes mapped port | App keeps stale bootstrap | Use stable endpoints or recreate context |
| Claiming single-broker test proves cluster HA | Ignores ISR and failover | Multi-broker / staging suite |
| Assigning same prefix to all pods | Fencing storm | Unique concurrent owners |

---

## 23. Extending the Lab: Controlled Owner Handoff

An advanced test can simulate an orchestrator reassigning a shard:

```text
Lease table:
  owner_key = orders-shard-03
  holder = pod-A
  lease_version = 41

A:
  obtains lease 41
  begins tx for orders-shard-03

Lease expires:
  B obtains lease 42
  B initializes same Kafka tx identity
  B commits new transaction

A resumes:
  Kafka commit -> fenced
  DB write guarded by lease_version=41 -> rejected
```

Kafka fencing protects Kafka outputs; **lease version checks** protect non-Kafka resources. Verify:

- A cannot publish its stale Kafka transaction.
- A cannot update the DB once `lease_version` has advanced.
- B processes the right input/offset state.
- If A committed a business effect before handoff, B deduplicates by event ID.

This extension demonstrates the difference between **Kafka transactional fencing** and **distributed ownership fencing** across an entire workflow.

---

## 24. Failure and Control Test Matrix

A thorough production test suite covers:

| ID | Scenario | Assertion |
| --- | --- | --- |
| F01 | A/B share transactional ID | A throws `ProducerFencedException` after B inits |
| F02 | A/B distinct transactional IDs | Both commit successfully |
| F03 | A uncommitted when fenced | `read_committed` does not see A |
| F04 | A commits before B inits | A's committed transaction remains visible |
| F05 | A tries sending again after being fenced | Old producer is never reused |
| F06 | B is slow yet still valid owner | No spurious new producer / self-fencing |
| F07 | Two Spring replicas share prefix | Collision caught by logs/metrics |
| F08 | Unique prefix per live owner | Zero self/peer fencing under concurrent load |
| F09 | Transaction timeout without B | Distinguished from fencing |
| F10 | Missing transactional ID ACL | Authorization error, not fencing |
| F11 | Duplicate consumer static ID | `FencedInstanceIdException`, separate runbook |
| F12 | Kafka tx + PostgreSQL effect | Replay does not duplicate DB state |
| F13 | Broker restart | Transactions recover/reinitialize cleanly |
| F14 | Rolling version upgrade | Ownership semantics preserved |
| F15 | Producer metrics alerts | Expected handoffs do not page at wrong severity |

### 24.1. Tests That Should Not Be Merged Into One

- **Unit tests:** prefix generators, owner assignment, error classifiers.
- **Embedded Kafka:** fencing and transaction visibility.
- **Testcontainers Kafka + DB:** idempotency and crash-window recovery.
- **Cluster tests:** coordinator failover, ISR, and durability.
- **Preproduction:** auth/ACLs, cluster load, and rolling deploys.

A test simulating fencing with two raw producers does not prove the whole system self-recovers cleanly. Add scoped tests for each layer.

---

## 25. Practice Exercises

### Exercise 1 — Basic Producer Fencing

Set up a single-broker `@EmbeddedKafka`. Create A and B sharing a `transactional.id`; have A send an uncommitted record, then B call `initTransactions` and commit another record.

Requirements:

- A throws `ProducerFencedException` when attempting to commit.
- B commits successfully.
- A `read_committed` consumer sees only B's record.

### Exercise 2 — Negative Control

Keep the same test using two distinct `transactional.id` values.

Requirements: both A and B commit, the consumer sees both records, and explain why `client.id` does not decide the outcome.

### Exercise 3 — Already-Committed Transaction

Let A commit before B initializes with the same ID, then have B commit a new record.

Requirements: `read_committed` sees both A and B; prove fencing does not erase previously committed transactions.

### Exercise 4 — `read_uncommitted` vs. `read_committed`

In the test where A is fenced mid-transaction, create two consumers with the two isolation levels.

Requirements: explain why `read_uncommitted` can observe A's appended record in the log whereas `read_committed` does not.

### Exercise 5 — Prefix Collision Between Two Replicas

Start two Spring application contexts sharing `transaction-id-prefix=orders-tx-` and run concurrent transactions. Record the actual transactional IDs allocated by the factories.

Requirements: pinpoint when collisions occur under the suffix strategy rather than assuming two templates always collide on `-0`.

### Exercise 6 — Logical Owner Prefix

Write a generator taking `environment`, `service`, and `shardId` and returning a stable prefix. Test uniqueness across active owners and identical prefixes when an owner is replaced.

Requirements: contrast stable logical-owner prefixes with random per-transaction UUIDs.

### Exercise 7 — Recovery Handler

Write a wrapper around a transactional publisher. When fenced, do not retry on the old instance; signal loss of ownership, close the producer, and let orchestration restart legitimately.

Requirements: verify no retry loop occurs and sufficient exception context is logged.

### Exercise 8 — Kafka + Database

Use Testcontainers Kafka + PostgreSQL. Producer A commits a DB business row, then its Kafka transaction gets fenced before commit; B replays the input.

Requirements: unique business keys and reconciliation prevent DB duplicates; analyze Kafka vs. DB transaction boundaries.

### Exercise 9 — Broker Failure Differs from Fencing

Without creating producer B, cut Kafka networking while A commits and inspect timeouts/retriable exceptions. Compare exceptions and recovery against the shared-`transactional.id` scenario.

Requirements: never lump timeouts together with `ProducerFencedException`.

### Exercise 10 — Operations Runbook

A 5-pod Deployment shares `transaction-id-prefix=orders-prod-` and logs hundreds of fencing events per minute.

Write a runbook identifying owners, IDs, collision sources, mitigation steps, recovery, and criteria to declare data integrity verified.

### Exercise 11 — Zombie Failover Simulation

Pause A after sending a record before commit; have B claim the same identity and commit. Wake A and attempt commit. Extend with a lease version guard on the DB writer.

Requirements: both Kafka and the DB reject the stale owner.

### Exercise 12 — Dashboard

Design a dashboard displaying fenced producers by service/owner, transaction failures, consumer lag, aborted transactions, restart rates, and duplicate business effects. Define alerts separating expected handoffs from fencing storms.

---

## 26. Pre-Production Checklist

- [ ] `transactional.id` represents a clear logical owner/producer identity.
- [ ] No two independent producers needing concurrent operation share a `transactional.id`.
- [ ] Spring Kafka `transaction-id-prefix` is namespaced properly across replicas/shards.
- [ ] Fenced old producers are closed without retrying sends/commits on the deposed instance.
- [ ] Producer ID/epoch fencing is distinguished from consumer `group.instance.id` fencing.
- [ ] Tests use proper transaction-enabled Kafka broker settings.
- [ ] Tests include both a positive same-ID case and a negative distinct-ID control.
- [ ] `read_committed` never exposes records from aborted transactions.
- [ ] Transactions committed before fencing remain intact.
- [ ] Timeouts, ACLs, and out-of-order sequences are classified separately.
- [ ] Non-Kafka business side effects have idempotency/lease protection.
- [ ] Consumer offset replays are tested for Kafka-to-Kafka workflows.
- [ ] Monitoring distinguishes expected failovers from collision storms.
- [ ] Rollout/rollback plans account for transaction ownership and business state.
- [ ] Production-like tests use compatible broker and client versions.
- [ ] Single-broker tests are never cited as proof of cluster failover or durability.

## 27. Conclusion

**Producer fencing protects Kafka transactions—it is not merely an exception to suppress.** When two producers share a `transactional.id`, the coordinator lets only the current generation mutate transactional state; the older producer loses authority and must stop.

The core experiment is clear:

```text
A init + begin + send (uncommitted)
B init with same transactional.id
B begin + send + commit succeeds
A commit -> ProducerFencedException

read_committed -> sees only B's committed record
```

Building on this, a Spring Kafka system needs clear operational rules: **zero transactional ID collisions across active owners**, explicit failover ownership, no reuse of fenced producers, and idempotency plus reconciliation for side effects outside Kafka.

Once you can simulate fencing and explain exactly which records are visible or aborted, operators can tell **expected failover fencing** apart from **misconfigured fencing storms**, resolving incidents without accidentally introducing duplicate business effects.

## 28. References

- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): `transactional.id`, idempotence, acks, and timeouts.
- [Apache Kafka — Design: Transactions](https://kafka.apache.org/documentation/#transactions): transactional producers, fencing, and consumer visibility.
- [KafkaProducer Javadoc](https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html): `initTransactions`, `beginTransaction`, `commitTransaction`, and `abortTransaction`.
- [Kafka ProducerFencedException Javadoc](https://kafka.apache.org/37/javadoc/org/apache/kafka/common/errors/ProducerFencedException.html): meaning of producer fencing errors.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager`, `DefaultKafkaProducerFactory`, and transaction ID prefixes.
- [Spring Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` and `EmbeddedKafkaBroker`.
- [Spring Boot — Apache Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration and Kafka transaction properties.
- [Testcontainers Kafka Module](https://java.testcontainers.org/modules/kafka/): real brokers in Docker.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `isolation.level=read_committed`.
