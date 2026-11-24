# Testing After-Rollback Redelivery in Spring Kafka

A Spring Kafka consumer processing orders encounters a mid-flight failure. When the listener runs inside a **Kafka transaction**, the framework can roll back the current transaction, reposition the consumer back to the unprocessed record, and redeliver that exact record on the next poll. This mechanism is called **after-rollback redelivery**. It matters because a system that merely "retries on exception" does not necessarily preserve offset state and output data integrity, especially when a listener reads from one topic and publishes to another.

This lesson belongs to **Spring Kafka Reliability Operations → Reliability Testing**. We will build an integration test using **Spring Boot 3.x, Spring Kafka 3.x, Java 17, JUnit 5, and Embedded Kafka** to prove these conditions: the listener fails on the first attempt, the first transaction rolls back, the same `topic-partition-offset` is redelivered, the second attempt succeeds, and the output topic holds only **one committed result**. At the end we extend to retry exhaustion, `DefaultAfterRollbackProcessor`, dead-letter topics (DLT), idempotency, restarts, and test mistakes that produce false results.

## 1. What is after-rollback redelivery really?

Suppose a source record:

```text
Topic: orders.in
Partition: 0
Offset: 42
Key: order-101
Value: {"amount":120}
```

The listener performs:

1. Reads the record at offset 42.
2. Builds `validated:order-101` and sends it to `orders.out`.
3. Encounters an exception before the transaction commits.
4. Spring Kafka rolls back the Kafka transaction.
5. The after-rollback processor adjusts the consumer position so the failed record is included in the next poll.
6. The listener receives offset 42 again and processes it successfully.

```text
orders.in: partition 0
    offset 41 [processed]
    offset 42 [order-101] <----------------------------+
                  |                                   |
              poll #1                                 |
                  |                                   |
                  v                                   |
           Kafka listener                             |
                  |                                   |
                  +--> send orders.out (uncommitted)  |
                  +--> throw exception                |
                  |                                   |
             ROLLBACK Kafka TX                        |
                  |                                   |
                  +--> after-rollback seek/reposition +
                                                      |
              poll #2: offset 42 <--------------------+
                  |
                  v
           Kafka listener
                  |
                  +--> send orders.out
                  +--> return normally
                  |
              COMMIT Kafka TX
                  |
                  v
       orders.out: 1 committed result
```

Typically, `DefaultAfterRollbackProcessor` is used with a transactional listener container to reposition records after a rollback. However, **redelivery is a behavior that must be verified via actual `ConsumerRecord` metadata**, rather than inferred solely from how many times a Java method was called.

### 1.1. Concepts to distinguish

| Concept | Meaning | What to test |
| --- | --- | --- |
| **Retry** | Reattempting processing after a failure; can happen at multiple layers | Attempt count, interval, bounds |
| **Redelivery** | Broker/container delivers the record again to the listener | Same `topic`, `partition`, `offset`, key |
| **Rollback** | The current transaction is not committed | Output from failed attempt is invisible to `read_committed` |
| **Offset commit** | Persists consumer group progress | Offset advances only after successful processing per contract |
| **Recovery** | After failed attempts, choose skip, DLT, or stop | No silent record loss, how offsets are handled |
| **Replay** | Explicitly reprocessing historical / DLT records | Not identical to automatic in-transaction redelivery |

Retries can happen **inside a single method** without ever re-polling Kafka. In this lesson, we test **container-level redelivery**: the same record enters `@KafkaListener` a second time after a rollback, not re-calling the listener method manually in a unit test.

## 2. Prerequisites for transactional after-rollback behavior

Three layers must work together:

```text
Kafka Consumer
      |
      v
Spring Kafka listener container
      |
      +--> KafkaTransactionManager / KafkaAwareTransactionManager
      |            |
      |            +--> Kafka TX begin / commit / rollback
      |
      +--> listener processes record
      |
      +--> AfterRollbackProcessor on transaction rollback
      |
      v
Kafka producer: sends output in the corresponding transaction
```

Practical prerequisites:

- The producer factory is configured with a unique **transactional ID prefix** appropriate for the instance scope.
- The listener container uses `KafkaTransactionManager` (or a Kafka-compatible transaction manager) to manage transactions around receiving/processing.
- Consumer auto-commit is not enabled to commit offsets outside the transaction lifecycle.
- The listener must **throw exceptions outward** when a transaction rollback is intended. Catching an error to merely `log.warn(...)` and return normally causes the container to treat processing as successful.
- Output data in Kafka transactions must be observed using a consumer with `isolation.level=read_committed` so aborted records are not visible.
- Tests must use explicit time limits and wait conditions, avoiding `Thread.sleep(...)` as the primary synchronization mechanism.

**Note:** Kafka transactions protect Kafka operations joined to the transaction and consumption offsets sent into the transaction by the container. They do not automatically turn a PostgreSQL write, REST API call, or email send into a single atomic transaction with Kafka.

## 3. Why use `DefaultAfterRollbackProcessor` instead of only `DefaultErrorHandler`?

Spring Kafka has multiple error-handling mechanisms. For **non-transactional record listeners**, `DefaultErrorHandler` is typical: it handles record exceptions, backoff, recoverers, and seek/resubmit per configuration. For **transactional listener containers**, exceptions generally must escape so the Kafka transaction rolls back; then **`AfterRollbackProcessor`** handles the remaining records and consumer position.

| Context | Typical mechanism | What not to confuse |
| --- | --- | --- |
| Record listener without container transactions | `DefaultErrorHandler` | No Kafka TX exists to roll back output |
| Listener running inside a Kafka transaction | `DefaultAfterRollbackProcessor` | Exceptions must trigger rollback before redelivery |
| Non-blocking retry topic | `@RetryableTopic` / retry topics | A different retry pipeline, not in-consumer post-rollback seek |
| Batch listener | Pinpointing the failed record depends on listener and exception | Do not assume every failed batch redelivers a single item |

`DefaultAfterRollbackProcessor` can use a backoff and recoverer when a record keeps failing. A recover/skip configuration after N attempts **changes test expectations**: you cannot assert "redeliver forever" if policy permits recovering and skipping the record.

In the main test, we intentionally fail **exactly once then succeed** to verify the rollback → redelivery path independently of default recovery thresholds.

## 4. Test model and success criteria

Design two topics with one partition each:

```text
orders.rb.input  -->  @KafkaListener  --> orders.rb.output
                             |
                             +-- attempt #1: send then throw
                             |
                             +-- attempt #2: send then return
```

Assume a record with key `order-101` and value `120`:

| Condition | Expected outcome |
| --- | --- |
| Attempt #1 | Listener receives record and throws simulated error |
| Transaction #1 | Rolled back; attempt #1 output is not committed |
| Attempt #2 | Listener receives the exact same `topic-partition-offset` |
| Transaction #2 | Commits successfully |
| Observing output with `read_committed` | Exactly one message `accepted:120` |
| Offset and key | Both deliveries have the same `topic`, `partition`, `offset`, and `key` |
| Test duration | Bounded timeout; does not hang if redelivery never arrives |

**What tests should not claim:** "Kafka is guaranteed to invoke the listener exactly twice in every production environment." In an isolated single-fixture scenario with no restart/rebalance and a single simulated fault, two deliveries are the test's expectation. In real environments, crashes/rebalances and other failure modes can cause additional deliveries; consumers must be designed to tolerate repeat processing.

## 5. Preparing the test project

Illustrative `build.gradle` with a specific Spring Boot 3.x version; in a real project, use your project-managed BOM/versions:

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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this practice:

- `spring-kafka` provides `@KafkaListener`, `KafkaTemplate`, the transaction manager, and `DefaultAfterRollbackProcessor`.
- `spring-kafka-test` provides `@EmbeddedKafka`, `EmbeddedKafkaBroker`, and `KafkaTestUtils`.
- `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring Boot test utilities.
- Tests use an embedded broker, **requiring no external Kafka cluster**, though they do not prove networking, auth, ACLs, multi-broker failover, or production broker configurations.

A possible project structure:

```text
src/
├── main/
│   └── java/com/example/kafka/
│       └── ReliabilityApplication.java
└── test/
    └── java/com/example/kafka/
        └── AfterRollbackRedeliveryTest.java
```

Here the example places the test listener bean and container configuration inside the test class itself so learners can see the full setup in one place.

## 6. Enabling Kafka transactions for the listener

In Spring Boot, a transactional producer is usually enabled via `spring.kafka.producer.transaction-id-prefix`. Beyond enabling Kafka transactions on the producer, the listener container **must have a transaction manager attached** to handle listener failures via the rollback path.

Test setup using `@SpringBootTest` and `@EmbeddedKafka`:

```java
@SpringBootTest(
    classes = {
        AfterRollbackRedeliveryTest.App.class,
        AfterRollbackRedeliveryTest.KafkaTestConfig.class
    },
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=rb-test-"
            + "${random.uuid}-"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.rb.input", "orders.rb.output"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

This is an **annotation fragment**, used in the complete test class in section 9. `bootstrapServersProperty` lets Spring Embedded Kafka register the broker address into the property read by Spring Boot Kafka auto-configuration.

Key points:

1. `enable-auto-commit=false`: prevents the consumer from periodically committing offsets outside container control.
2. `isolation.level=read_committed`: ensures the consumer sees only records committed in Kafka transactions, not records from aborted transactions.
3. `transaction-id-prefix`: enables the producer factory to create transactional producers; prefixes must be managed **uniquely across instances** that can run concurrently in real environments.
4. `auto-offset-reset=earliest`: suits test fixtures when a group has no committed offset yet; not a recovery rule for groups that already have offsets.

Do not share the same fixed `transactional.id` across multiple concurrently active application instances: they can fence each other. In production, prefixes can incorporate a stable instance identifier unique per lifecycle and orchestration constraints.

## 7. Configuring `KafkaTransactionManager` and the after-rollback processor

In Spring Kafka 3.x, `ConcurrentKafkaListenerContainerFactory` can be configured to use a Kafka transaction manager. Test configuration class example:

```java
@TestConfiguration
static class KafkaTestConfig {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean("kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            KafkaTransactionManager<String, String> transactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(transactionManager);

        // Use default ARP to seek/redeliver after rollback.
        factory.setAfterRollbackProcessor(
                new DefaultAfterRollbackProcessor<>());

        return factory;
    }

    @Bean
    FlakyOrderListener flakyOrderListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        return new FlakyOrderListener(kafkaTemplate);
    }
}
```

`@TestConfiguration` and `@Bean` are Spring Boot/Spring annotations; `ProducerFactory`, `ConsumerFactory`, `KafkaTemplate`, `ConcurrentKafkaListenerContainerFactory`, `KafkaTransactionManager`, and `DefaultAfterRollbackProcessor` are Spring Kafka classes. `FlakyOrderListener` is defined in section 8.

**Why set concurrency to 1?** We want a deterministic test with one partition and one listener thread. With multiple partitions, threads, or group members, correctness must still hold, though callback ordering becomes harder to predict.

**Why use the default ARP?** The immediate goal is only to verify a single failure followed by redelivery. Backoff, recoverer/DLT, and retry-limit settings should be verified in separate tests rather than mixed together so root causes are never conflated.

In Spring Boot versions that auto-configure a Kafka transaction manager from the producer transaction prefix property, if you declare a bean manually as in the example, avoid accidentally creating two transaction managers for the same purpose. Production configs should verify which bean is actually injected into the listener container.

## 8. Listener fixture: fail first, succeed next

So the test can observe events, the listener tracks:

- An `AtomicInteger` counting how many times the callback received records in the fixture.
- A thread-safe queue recording `topic`, `partition`, `offset`, and key for each delivery.
- A `CountDownLatch` signaling to the test that a successful attempt occurred.

```java
static class FlakyOrderListener {

    record Delivery(
            String topic, int partition, long offset, String key) {}

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final AtomicInteger attempts = new AtomicInteger();
    private final ConcurrentLinkedQueue<Delivery> deliveries =
            new ConcurrentLinkedQueue<>();
    private final CountDownLatch successfulAttempt =
            new CountDownLatch(1);

    FlakyOrderListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.rb.input",
        groupId = "rollback-demo-group",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrder(ConsumerRecord<String, String> record) {
        deliveries.add(new Delivery(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()));

        int currentAttempt = attempts.incrementAndGet();

        // Send participates in the listener container's Kafka transaction.
        kafkaTemplate.send(
                "orders.rb.output",
                record.key(),
                "accepted:" + record.value());

        if (currentAttempt == 1) {
            throw new IllegalStateException("SIMULATED_FIRST_FAILURE");
        }

        successfulAttempt.countDown();
    }

    boolean awaitSuccessfulAttempt(Duration timeout)
            throws InterruptedException {
        return successfulAttempt.await(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    List<Delivery> recordedDeliveries() {
        return List.copyOf(deliveries);
    }
}
```

On the first attempt, `kafkaTemplate.send(...)` **was called**, yet the listener threw an exception, triggering a transaction rollback. This differs from throwing before sending: if a test only throws from the start, it tests redelivery without testing whether output from the first Kafka transaction was aborted.

`successfulAttempt.countDown()` runs before the container finishes committing the transaction. Therefore, tests **must not** merely wait on the latch and declare output committed: a `read_committed` output consumer is needed to read and confirm the final result.

The fixture uses in-JVM state to force a first-time failure; this is **not** a retry counter for production. In real systems, records need idempotency and an appropriate recovery policy so they are not mishandled across process restarts.

## 9. Complete integration test with Embedded Kafka

The listing below combines the configuration and fixture into **a single test file** ready to run with the listed dependencies.

`AfterRollbackRedeliveryTest.java`:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@SpringBootTest(
    classes = {
        AfterRollbackRedeliveryTest.App.class,
        AfterRollbackRedeliveryTest.KafkaTestConfig.class
    },
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=rollback-test-"
            + "${random.uuid}-"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.rb.input", "orders.rb.output"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class AfterRollbackRedeliveryTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class App {}

    @TestConfiguration
    static class KafkaTestConfig {

        @Bean
        KafkaTransactionManager<String, String> kafkaTransactionManager(
                ProducerFactory<String, String> producerFactory) {
            return new KafkaTransactionManager<>(producerFactory);
        }

        @Bean("kafkaListenerContainerFactory")
        ConcurrentKafkaListenerContainerFactory<String, String>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTransactionManager<String, String> transactionManager) {

            var factory =
                    new ConcurrentKafkaListenerContainerFactory<
                            String, String>();
            factory.setConsumerFactory(consumerFactory);
            factory.setConcurrency(1);
            factory.getContainerProperties()
                    .setKafkaAwareTransactionManager(transactionManager);
            factory.setAfterRollbackProcessor(
                    new DefaultAfterRollbackProcessor<>());
            return factory;
        }

        @Bean
        FlakyOrderListener flakyOrderListener(
                KafkaTemplate<String, String> template) {
            return new FlakyOrderListener(template);
        }
    }

    static class FlakyOrderListener {
        record Delivery(String topic, int partition, long offset, String key) {}

        private final KafkaTemplate<String, String> template;
        private final AtomicInteger attempts = new AtomicInteger();
        private final ConcurrentLinkedQueue<Delivery> deliveries =
                new ConcurrentLinkedQueue<>();
        private final CountDownLatch succeeded = new CountDownLatch(1);

        FlakyOrderListener(KafkaTemplate<String, String> template) {
            this.template = template;
        }

        @KafkaListener(
            topics = "orders.rb.input",
            groupId = "rollback-demo-group",
            containerFactory = "kafkaListenerContainerFactory")
        public void onOrder(ConsumerRecord<String, String> record) {
            deliveries.add(new Delivery(
                    record.topic(), record.partition(),
                    record.offset(), record.key()));

            int attempt = attempts.incrementAndGet();
            template.send(
                    "orders.rb.output",
                    record.key(),
                    "accepted:" + record.value());

            if (attempt == 1) {
                throw new IllegalStateException("SIMULATED_FIRST_FAILURE");
            }
            succeeded.countDown();
        }
    }

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Autowired
    private FlakyOrderListener listener;

    @Test
    void rollsBackThenRedeliversSameRecordAndCommitsOnlyOnce()
            throws Exception {

        // Transactional KafkaTemplate: send input in its own transaction.
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                    "orders.rb.input", "order-101", "120").join();
            return null;
        });

        assertThat(listener.succeeded.await(20, TimeUnit.SECONDS))
                .as("Listener should succeed after redelivery")
                .isTrue();

        // Two callbacks correspond to the same logical record at the same offset.
        List<FlakyOrderListener.Delivery> received =
                List.copyOf(listener.deliveries);
        assertThat(received).hasSize(2);
        assertThat(received.get(1))
                .isEqualTo(received.get(0));
        assertThat(received.get(0).key())
                .isEqualTo("order-101");
        assertThat(received.get(0).topic())
                .isEqualTo("orders.rb.input");

        // Observer sees only COMMITTED output.
        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "rb-observer-" + UUID.randomUUID(),
                        "false", broker);
        consumerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        var observerFactory =
                new DefaultKafkaConsumerFactory<String, String>(
                        consumerProps,
                        new StringDeserializer(),
                        new StringDeserializer());

        try (Consumer<String, String> observer =
                     observerFactory.createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    observer, "orders.rb.output");

            ConsumerRecord<String, String> output =
                    KafkaTestUtils.getSingleRecord(
                            observer,
                            "orders.rb.output",
                            Duration.ofSeconds(20));

            assertThat(output.key()).isEqualTo("order-101");
            assertThat(output.value()).isEqualTo("accepted:120");

            ConsumerRecords<String, String> unexpected =
                    KafkaTestUtils.getRecords(
                            observer, Duration.ofMillis(500));
            assertThat(unexpected.count()).isZero();
        }
    }
}
```

**What the test proves:** the exact same Kafka record was redelivered to the listener; the first attempt rolled back so **no committed output exists** from that attempt; after the successful attempt, the `read_committed` observer receives exactly one output for this fixture.

**Implementation takeaway:** `getSingleRecord(...)` verifies one record within the test's poll scope and the next poll helps catch early duplicates. For larger systems, define a **clear test window**, fixed input count, isolated topics/groups, and reconcile final results rather than claiming the system can never produce duplicates from a single small test.

### 9.1. Why send the input via `executeInTransaction(...)`?

When `KafkaTemplate` is configured with a transactional producer factory, calling `send(...)` directly outside a transaction may be rejected depending on configuration and API. In the test:

```java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("orders.rb.input", "order-101", "120").join();
    return null;
});
```

We create **a separate transaction to send the fixture to the input topic**, after which the listener uses the container's transaction to process that record. These are two distinct transactions serving different purposes; do not assume the test callback shares a transaction with the listener thread.

### 9.2. Why assert the offset instead of just the key?

`orderId` or keys can appear across multiple Kafka records. Two records with the same key but different offsets are **not the same delivery**. Tests must compare all of:

```text
topic
partition
offset
key
```

`topic-partition-offset` uniquely identifies a record's position in the Kafka log. For the exact same record redelivered after a rollback, the offset must match. You do not need to hard-code offset `0`, because a test topic might already contain prior data or the broker may write internal records depending on configuration.

### 9.3. Why is `read_committed` mandatory for the observer?

An aborted Kafka transaction **does not immediately physically delete written records from the log**. A `read_uncommitted` consumer can see records from aborted transactions. Thus, if you read the output topic with a default consumer without controlling isolation, the test may observe **two messages** and wrongly conclude rollback failed.

In the test, the observer sets:

```java
consumerProps.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

This is the proper way to observe results **eligible for transactional reading** in Kafka. Never replace `read_committed` with a longer sleep to "wait for the failed record to disappear."

## 10. Testing offset commits after redelivery

Verifying that the same offset is redelivered is one part of the lesson. With transactional consumers, you also need to understand the link between **successful processing** and **consumer group progress**:

```text
Attempt #1 (FAILED)
   input offset 42
   output send in transaction
   exception
   TX abort
   input offset NOT successfully committed as processed

Attempt #2 (SUCCESS)
   input offset 42 redelivered
   output send
   listener returns
   TX commit (including offset progress via container)
   next record can be consumed
```

To test committed offsets accurately, use `AdminClient.listConsumerGroupOffsets(groupId)` or equivalent Kafka Admin tools **after the second transaction has committed**. Note that Kafka commits the **next offset**: after successfully processing offset 42, the committed offset for that partition is typically **43**, not 42.

You do not need AdminClient in the basic test if the goal is only redelivery + committed output. Offset tests should use a **unique group ID**, bounded polling/commit checks, and no other records in the same group shifting progress during assertions.

In environments with `isolation.level=read_committed`, records from open transactions can stall the last stable offset. This affects lag and output visibility, so never use a single lag snapshot to deduce exactly whether a rollback occurred.

## 11. When the listener always fails: backoff, recovery, and DLT

The test in section 9 intentionally succeeds on the second attempt. However, you also need an independent test for a **poison record**: a message with invalid content that fails forever unless remediated.

Example:

```text
orders.rb.input offset 43, value="not-a-number"
   |
   +-- attempt 1 FAILED -> rollback
   +-- attempt 2 FAILED -> rollback
   +-- attempt 3 FAILED -> rollback
   |
   +-- recover / publish DLT / stop, depending on policy
```

Without a limit, a poison record can stall the partition. `DefaultAfterRollbackProcessor` can combine a `BackOff` and a recoverer to decide after how many failures to handle the record differently.

Example configuration **for a dedicated recovery test**:

```java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.util.backoff.FixedBackOff;

var processor =
        new DefaultAfterRollbackProcessor<String, String>(
                (record, error) -> {
                    // Demo: record recovery event with test counter.
                    // Production needs a durable recoverer or DLT.
                    recoveryCounter.incrementAndGet();
                },
                new FixedBackOff(100L, 2L));

factory.setAfterRollbackProcessor(processor);
```

`recoveryCounter` is a test variable defined by the test class; the snippet above is an illustrative fragment, not a standalone class. `FixedBackOff(100L, 2L)` sets a 100 ms interval and retry budget per `BackOff` semantics; verify via actual assertions rather than guessing from total callback counts. If the recoverer **merely increments a counter and drops the record**, the record risks disappearing from normal processing; that is not a safe production data strategy.

### 11.1. Dead-letter publishing recoverer

For unprocessable data, you usually want to send an eligible failure event to a DLT:

```text
orders.rb.input
    |
    +-- failed attempts --> rollback / redelivery
                               |
                               v
                   after-rollback recoverer
                               |
                               v
                       orders.rb.input.DLT
```

Spring Kafka provides `DeadLetterPublishingRecoverer` to publish records to a target topic once failures are classified. When using it with transactional after-rollback processing, examine:

- Which **transaction** writes the DLT record, and whether the recovery outcome commits.
- Whether the recovered/skipped record's offset is committed **properly** so it does not redeliver forever when the process restarts.
- `commitRecovered` and the Kafka operations/template passed to the processor must match the **ack mode**, transaction manager, and Spring Kafka version in use. These settings take more than flipping a single flag.
- The DLT has its own partitions, retention, access permissions, serialization, and replay consumer.
- Payloads/headers may contain sensitive data or exception details; apply protection policies like any other topic.

**Recovery tests must assert more than redelivery tests:** policy-compliant delivery counts, a committed DLT record, post-recovery offset, zero wrong business outputs, and a working replay/repair path. Never treat "logged the error" as complete recovery.

### 11.2. Do not equate `@RetryableTopic` with after-rollback redelivery

`@RetryableTopic` typically builds a **non-blocking retry flow across separate topics**, with its own delays and routing. After-rollback redelivery reprocesses the record after rollback within the corresponding transactional listener/container thread. The two approaches have different offset, ordering, transaction, and topology semantics.

For a given test, pick **the** strategy used in production and write assertions matching that strategy. Do not expect "same topic-partition-offset" for a record published to a separate retry topic.

## 12. Batch listeners vs. record listeners: differences on rollback

The main test uses a **record listener**:

```java
@KafkaListener(topics = "orders.rb.input")
public void onOrder(ConsumerRecord<String, String> record) { ... }
```

With a **batch listener** receiving a `List<ConsumerRecord<K,V>>`, a single poll can supply multiple records. When a transaction rolls back, the remaining records in the poll may be reprocessed; isolating a single record for recovery requires the framework to know which record failed or using a suitable batch-handling strategy.

| Situation | What to verify |
| --- | --- |
| Record listener, one failing record | Exact same offset is redelivered |
| Poll contains multiple records, one fails | Remaining records are seeked/replayed per policy |
| Batch listener throws generic exception | Does not automatically pinpoint the exact failing item |
| Batch listener supplies failing record info | Recovery can locate the record via supported APIs |
| Batch DLT/recovery | Does not wrongly write the entire batch as one failed item if only one record is bad |

In Spring Kafka, `BatchListenerFailedException` is a mechanism for passing the failing record's position in a batch when supported by configuration and version. When testing batch behavior, build **at least three records**, fail on the middle record, and verify replay scope and per-record output. A single-record test will miss batch rollback differences.

## 13. Beware of side effects outside Kafka

Suppose a listener does both:

```java
@KafkaListener(topics = "orders.rb.input")
public void process(OrderEvent event) {
    paymentService.charge(event.orderId());
    kafkaTemplate.send("orders.rb.output", event.orderId(), "CHARGED");
    throw new IllegalStateException("SIMULATED_FAILURE");
}
```

If the Kafka transaction rolls back, the Kafka output can abort. Yet **the charge request already sent to the payment service does not roll back automatically**. When the record is redelivered, the listener may charge again. Therefore:

```text
Kafka TX rollback  !=  External side effect rollback
```

To tolerate redelivery:

1. **Stable idempotency key:** such as `orderId` or `source event ID` per contract; repeating the same key does not create a new transaction.
2. **Transactional outbox/inbox:** if writing to a database, use a transaction and unique constraint to record processed events alongside business data; publish results via a separate worker.
3. **Reconciliation capability:** after an API timeout, actual state may be unknown; query by key before retrying.
4. **Never use attempt number as an idempotency key:** a redelivered record with a different attempt count must be recognized as the same business operation.
5. **Test fake side effects:** mock/stub services with counters and assert the application does not create duplicate side effects, not just output topic checks.

Kafka provides certain exactly-once guarantees for **in-Kafka consume-process-produce flows when transactions are configured properly**. That **does not** automatically extend to databases or HTTP APIs outside Kafka. Hence idempotency remains necessary at business boundaries.

## 14. Avoiding flaky tests: synchronize on events, do not guess with time

Kafka is asynchronous. If a test merely does:

```java
kafkaTemplate.send("orders.rb.input", "key", "value");
Thread.sleep(1000);
assertThat(attempts.get()).isEqualTo(2);
```

then the outcome depends on broker startup speed, partition assignment, CI CPU, and broker networking. A fast machine may pass while a loaded machine fails.

### 14.1. Waiting on the right conditions

In the example, we use:

```java
assertThat(listener.succeeded.await(20, TimeUnit.SECONDS)).isTrue();
```

and `KafkaTestUtils.getSingleRecord(...)` with an explicit `Duration`. The latch proves the listener reached the success point; the `read_committed` consumer proves output committed. They complement each other.

If you need to confirm the listener **has been assigned partitions** before sending:

```java
// Retrieve the container by listener id and use an assignment-wait utility.
// No need to just sleep for a fixed duration.
```

Spring Kafka Test provides `ContainerTestUtils.waitForAssignment(...)`. For tests needing control over multiple containers and partitions, assign a fixed `id` to `@KafkaListener`, retrieve the container from `KafkaListenerEndpointRegistry`, and wait for the exact partition count to be assigned before sending fixtures.

### 14.2. Isolating tests

| Cause of flakiness | Solution |
| --- | --- |
| Reusing topics/groups across tests | Separate topics or groups, isolated contexts |
| Previous test's listener still running | Stop containers/contexts and avoid hidden shared state |
| Shared `AtomicInteger` not reset | Create a new listener per test or reset deterministically |
| Broker has not assigned partitions yet | Wait for assignment/events instead of sleeping |
| Transactional KafkaTemplate sends fixture without TX | `executeInTransaction(...)` or a separate test producer |
| Observer uses `read_uncommitted` | Set `isolation.level=read_committed` |
| Asserting offset is always 0 | Compare offsets across two deliveries, do not hard-code |
| Timeout too short | Finite timeout with CI headroom and clear failure messages |
| Parallel tests sharing a group | Use independent groups or disable parallelism for this scenario |
| Asserting only callback count | Also assert matching offset, committed output, recovery state |

For large suites, `@DirtiesContext` can prevent listener beans and embedded brokers from earlier tests from affecting later tests. However, restarting contexts and brokers is expensive; it is best to combine **dedicated topics/groups** with well-managed test lifecycles.

### 14.3. Do not indiscriminately enable payload debug logging

In failure tests, `ConsumerRecord.value()` can hold sensitive information. In production, avoid logging raw records or exceptions carrying serializer/deserializer payloads. Log `topic`, `partition`, `offset`, attempt, safe error codes, and approved correlation IDs; sensitive item keys should be tokenized.

## 15. Expanding into a reliability test matrix

A "fail first, succeed next" test is a starting point, not complete reliability verification.

| Scenario | How to build fixture | Expectation |
| --- | --- | --- |
| Fail once then succeed | Throw on attempt 1 | Same offset redelivered; one committed output |
| Always fail | Throw on every attempt | Backoff, recover/DLT, or stop per policy |
| Fail right before output send | Throw before `kafkaTemplate.send(...)` | Redelivery, no output from first attempt |
| Fail after output send | Send then throw | First TX output aborted, only winning TX output visible |
| Send fails before commit | Simulated producer failure | Transaction fails/rolls back; listener return not treated as success |
| Two records in same poll | Record 1 succeeds, record 2 fails | Rollback/replay scope matches container and transaction |
| Multiple partitions | Failing record on partition A | Check partition B position and progress per configuration |
| Process restart mid-processing | Stop worker before commit | Consumer group redelivers uncommitted record |
| Rebalance while processing | Change group membership | No record loss; duplicate processing must be safe |
| Poison record to DLT | Recovery policy with bounded backoff | DLT has durable record, offset handled properly |
| External DB/API side effect | Stub service with idempotency key | No duplicate side effects |
| `read_uncommitted` observer | Test consumer using wrong isolation | Shows difference, clarifies aborted records |

**Important for restart tests:** an `AtomicInteger` inside a listener resets when the JVM restarts, so it cannot serve as proof of how many times a record was processed across multiple processes. Use Kafka identities/offsets, event audits, and external data to verify outcomes.

## 16. Observing rollbacks and redeliveries in operations

Production systems need visibility when redeliveries spike unexpectedly:

```text
event=kafka_listener_attempt_failed
listener=orders-consumer
topic=orders.in
partition=0
offset=42
error_code=TRANSIENT_PARTNER_FAILURE

event=kafka_transaction_rolled_back
listener=orders-consumer
topic=orders.in
partition=0

event=kafka_record_recovered
listener=orders-consumer
topic=orders.in
partition=0
offset=42
recovery=DLT
```

This is a **suggested event schema**, not verbatim default lines emitted by Spring Kafka. You can use container listeners, Micrometer metrics, interceptors, or custom recoverers to emit suitable events while avoiding sensitive payloads.

Metrics to watch:

- Processing failures by listener/topic/error code.
- Records recovered, sent to DLT, or still pending.
- Redelivery latency, transaction duration, and abort rate.
- Consumer lag by **partition**, noting differences among current position, committed offset, and last stable offset.
- Repeated failure rate on the same offset; a chronically failing offset can slow down its partition.
- Producer fencing/transaction timeouts, rebalances, and consumer poll timeouts.

Do not use `topic-partition-offset` as a label on time-series metrics: cardinality can grow huge. It fits better as a searchable field in protected logs or audits.

## 17. Common implementation/test errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Listener called once then never redelivered | Exception swallowed, container transactions disabled, recovery already skipped | Let exception propagate; inspect transaction manager/ARP |
| Test sees two outputs | Observer uses `read_uncommitted` or two transactions committed | Use `read_committed`, isolated topics/groups, check metadata |
| Test reports success before Kafka commits | Only waited on latch inside listener | Poll committed output after latch |
| Consumer does not receive test message | Partitions not assigned yet, wrong group/offset, wrong topic | Wait for assignment, use unique group, verify fixture send |
| `KafkaTemplate.send` reports no transaction | Transactional template called outside TX | Use `executeInTransaction` when sending fixtures |
| Transactional producer gets fenced | Duplicate `transactional.id` across instances | Design unique prefix/instance IDs |
| Test callback count varies randomly | Consumer rebalance, parallel tests, shared listener state | Isolate topics/groups/contexts and test window |
| Poison record stuck forever | No clear backoff/recovery policy | DLT or fail/stop per contract, check offsets |
| DLTed record comes back after restart | Recovery/offset commit incompatible with transaction | Check `commitRecovered`/ack mode and transaction boundary |
| DB writes twice even though Kafka has one output | DB is not inside the Kafka transaction | Idempotency/inbox/outbox and DB integration tests |
| Test calls `@KafkaListener` method directly | Bypasses broker, transactions, and ARP | Use Embedded Kafka/Testcontainers integration tests |
| Using `@RetryableTopic` and asserting same offset | Retries happen on different topics | Write tests matching the actual topology |
| Logging exception and entire `ConsumerRecord` | Can expose business data | Log metadata + approved error codes |

## 18. Advanced exercises

After getting the basic test passing, work through these in order:

1. **Move the failure point:** throw an exception before `kafkaTemplate.send(...)`, run the test, and explain why "one committed output" still passes while no longer verifying aborted output from the first attempt.
2. **Keep failure after send:** verify the `read_committed` observer sees only output from the winning attempt; if switched to `read_uncommitted`, note the difference without treating it as a framework bug.
3. **Verify same offset:** record `topic`, `partition`, `offset`, and `key` across attempts; prove the exact same record was redelivered rather than two records with duplicate keys.
4. **Poison record:** make the listener always throw; configure finite backoff and a clear recovery policy to prevent partition stalls.
5. **DLT:** replace the log-only recoverer with `DeadLetterPublishingRecoverer`, create the DLT topic, verify one committed record, and ensure the replay path is idempotent.
6. **Post-recovery offset:** inspect the committed consumer group offset and compare with the source offset; note that Kafka commits the next position.
7. **Multiple input records:** send three records and fail on the second. Observe rollback scope and which records replay as container polling/chunk boundaries change.
8. **Restart:** stop the listener/container before commit, restart the group, and verify the uncommitted record is redelivered. Do not rely on an in-JVM counter as the sole evidence.
9. **External side effects:** replace the output send with a database/API stub containing a counter; simulate a timeout after the side effect succeeds and add idempotency.
10. **CI:** run the test repeatedly in an isolated environment. If flaky, wait on partition assignment and commit events using bounded conditions instead of increasing `Thread.sleep`.

## 19. Summary

After-rollback redelivery in Spring Kafka is a key mechanism of **transactional listeners**: when processing fails, the Kafka transaction rolls back and the listener container can re-queue unprocessed records for consumption. Proper tests must verify **both sides simultaneously**:

- **Input:** the same `topic-partition-offset` is redelivered after rollback, not merely a Java method invoked twice.
- **Output:** records sent inside the aborted transaction **are invisible to `read_committed`**, while the winning transaction produces the committed result.

`EmbeddedKafka`, `@KafkaListener`, `DefaultAfterRollbackProcessor`, `KafkaTransactionManager`, `KafkaTestUtils`, and primitives like `CountDownLatch` make it possible to build a deterministic scenario. Moving toward production, also verify backoff, poison records/DLTs, committed offsets, idempotency for side effects outside Kafka, and crash recovery. **Do not mistake a passing redelivery test for an end-to-end exactly-once guarantee across the whole system**; reliability must be proven at each real transaction boundary and data boundary.
