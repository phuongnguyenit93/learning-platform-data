# Testing Transaction Commits in Spring Kafka

## 1. Problem: a successful send does not mean a commit

In a system using **Spring Kafka**, a service may receive messages from an input topic, execute business logic, and publish new messages to an output topic. If the process fails partway through, the system must know which messages were actually published, which were cancelled, and whether consumer group offsets were updated properly.

Checking only that **KafkaTemplate.send(...) does not throw an exception** is not enough. If the producer is inside a Kafka transaction, a record already acknowledged by the broker can still be **aborted** before the transaction finishes. A consumer configured with **read_committed** will not return records belonging to an aborted transaction.

Example:

~~~text
Order processor
     |
     v
beginTransaction()
     |
     +-- send(order-created, O101) ----> Kafka log
     |
     +-- send(order-audited, O101) ----> Kafka log
     |
     +-- commitTransaction()
             |
             +-- Success: both records visible to read_committed
             |
             +-- abort: both records hidden from read_committed
             |
             +-- Lost ACK / process crash: actual state must be verified
~~~

In the **Spring Kafka Reliability Operations → Reliability Testing** chapter, **Testing transaction commits** focuses on building tests that prove this against a real Kafka broker in a test environment rather than relying solely on mocked methods.

Goals:

1. Configure a **transactional producer** using \`transactional.id\` or \`transactionIdPrefix\`.
2. Verify that a transaction commit makes records visible to a \`read_committed\` consumer.
3. Verify that a transaction abort hides records from a \`read_committed\` consumer.
4. Understand the difference between **producer send acknowledgment** and **transaction commit acknowledgment**.
5. Test a **consume → process → produce** flow where outputs and consumer offsets belong to the same Kafka transaction.
6. Design fault injection for failures before commit, after commit, and when the commit outcome is uncertain.
7. Recognize the limits of Kafka transactions when a workflow also writes to databases, HTTP APIs, or files.
8. Capture test evidence, metrics, and runbooks for operating reliable transactions.

The code snippets illustrate the **Spring Kafka 3.x, Kafka clients 3.x, Java 17, and JUnit 5** ecosystem. When upgrading frameworks, cross-check the configuration APIs of the running version; the transaction and isolation concepts here remain central.

## 2. What does a Kafka transaction guarantee?

A Kafka producer can send multiple records within **one transaction**, across one or more partitions/topics, and then **commit** or **abort** as an atomic unit at the Kafka level.

Example:

~~~text
Transaction TX-100
   |
   +-- topic orders: key=O101 value=CREATED
   |
   +-- topic audit:  key=O101 value=CREATED_BY_JOB
   |
   +-- COMMIT
        |
        v
Consumers with isolation.level=read_committed:
  See both records when transaction is committed.
~~~

If the same transaction aborts, a \`read_committed\` consumer does not return either record. The broker may still retain the data and transaction markers in the physical log per Kafka internals, but they are **not treated as visible business records** for read_committed consumers.

### What Kafka transactions do not guarantee automatically

- They do not automatically turn a PostgreSQL \`INSERT\` and a Kafka \`send\` into **one distributed atomic transaction**.
- They do not roll back emails, HTTP requests, payments, file outputs, or cache writes.
- They do not guarantee downstream business handlers will not run twice if consumers or external side effects are not designed to be idempotent.
- They do not guarantee the producer application receives an ACK under every network condition; an **ambiguous commit outcome from the client's perspective** can occur.
- They do not replace validating record keys, payloads, partitioning, schemas, and business logic.

**Exactly-once semantics (EOS)** in Kafka must be understood within the boundary of properly configured Kafka operations: transactional writes and, for consume-transform-produce flows, writing output **together with** committing consumer group offsets inside the transaction. Once data leaves this Kafka boundary, additional reliability design is required.

## 3. Concepts to distinguish

| Concept | Description | Role in tests |
|---|---|---|
| \`transactional.id\` | Transactional producer identifier used with the coordinator to manage epoch/fencing | Verifies ownership and producer fencing behavior |
| \`transactionIdPrefix\` | Prefix Spring Kafka uses to assign transactional.ids to producers in a factory/cache | Configures transactional producers |
| \`enable.idempotence\` | Helps prevent duplicates from producer retries within a producer session and partition | Related to delivery guarantees, but does not replace transactions |
| \`initTransactions()\` | Registers/initializes a transaction-capable producer with the broker | Required before transactions when using KafkaProducer directly |
| \`beginTransaction()\` | Begins a transaction | Scopes the set of records being sent |
| \`commitTransaction()\` | Requests transaction commit | Visibility verification point |
| \`abortTransaction()\` | Aborts a transaction | Kafka-side rollback verification point |
| \`isolation.level=read_committed\` | Consumer returns only records from committed transactions plus non-transactional records | Used to assert guaranteed visibility |
| \`isolation.level=read_uncommitted\` | Consumer may read records from uncommitted or aborted transactions | Used for comparison, not for evaluating EOS |
| LSO / Last Stable Offset | Read boundary for read_committed consumers when an open transaction exists | Explains why data arriving after an open transaction may be held back |
| Producer fencing | A new producer epoch prevents an older producer with the same transactional.id from committing | Prevents two owners from writing under the same identity |
| Consumer group offset | Recorded position for a consumer group | For consume-process-produce, must be tied to the transaction when EOS is required |

**A record having an offset in the Kafka log does not mean its transaction has committed.** A read_committed consumer relies on transaction markers and isolation to decide which records are returned to the application.

### Send ACK differs from commit ACK

~~~text
KafkaTemplate.send(...).get(...) / .join()
               |
               v
Broker ACKed record append per acks config
               |
               X Not yet proof of COMMITTED transaction
               |
               v
KafkaTemplate.executeInTransaction(...) callback finishes
               |
               v
Kafka producer commits transaction
               |
               v
read_committed consumer can now see records
~~~

If an exception occurs inside the \`executeInTransaction\` callback, Spring Kafka attempts to abort the transaction. Tests must verify the **outcome observed from the broker**, not only that the method threw an exception.

## 4. Conditions for testing transactions properly

A reliable integration test requires:

1. A **real broker** at the Kafka protocol level, using EmbeddedKafka or Testcontainers.
2. A genuinely configured transactional producer, not just a mocked KafkaTemplate.
3. A consumer using **read_committed**, with \`enable.auto.commit=false\` and a dedicated group ID per test.
4. Topics and test keys that do not mix data from other tests.
5. Synchronized waiting on record/offset outcomes with timeouts, without \`Thread.sleep\` guessing commit timing.
6. Clear separation between \`send\`, \`commit\`, \`abort\`, and consumer polling.
7. Tests covering **commit success**, **abort**, and **commit failure/uncertain outcome**.
8. Not assuming a test Kafka broker defaults to production-like multi-replica settings.

With a single broker in tests, the Kafka transaction coordinator requires the internal \`__transaction_state\` topic. On a single-broker cluster, you may need:

~~~properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
transaction.state.log.num.partitions=1
offsets.topic.replication.factor=1
~~~

These values are suitable for **single-broker integration tests**, **not** recommended reliability settings for production. Real clusters need replication, min ISR, and availability designed to meet SLAs.

## 5. Choosing EmbeddedKafka vs. Testcontainers

| Characteristic | EmbeddedKafka | Testcontainers with Kafka |
|---|---|---|
| Startup | Broker runs in-process with the test suite via Spring Kafka Test | Kafka runs inside a container |
| Best suited for | Fast integration tests for producer/consumer/transactions | Tests closer to deployment and network environments |
| Docker dependency | Usually no | Yes |
| Commit/abort checks | Yes | Yes |
| Crash/network partition simulation | More limited | Can combine with proxies/chaos tools |
| Production parity | Must check broker version and settings | Can pin matching Kafka image/version |
| Multi-broker testing | Configurable, but more complex | Uses topology suited to the test |

**EmbeddedKafka** is sufficient to prove producer transaction commit/abort logic. **Testcontainers** is especially useful when testing broker, network, and coordinator failures and production-like configurations.

In this lesson, we write broker tests with \`@EmbeddedKafka\` first, then cover extended scenarios with containers and fault injection.

## 6. Test project dependencies

Gradle example for Spring Boot with plugin and dependency management already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

With Maven, the corresponding dependency includes \`spring-kafka-test\` in test scope. Ensure **spring-kafka, spring-kafka-test, and kafka-clients** match the version set managed by the framework; avoid mixing incompatible versions.

Some Spring Boot projects use \`spring-boot-starter-kafka\` depending on the release generation; if that starter is available in your BOM, you can use it. The mandatory dependencies for these examples are \`spring-kafka\` and \`spring-kafka-test\`.

## 7. Configuring a transactional producer

In Spring Kafka, \`DefaultKafkaProducerFactory\` creates transactional producers when given a **transactionIdPrefix**.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

public class KafkaTxProducerSetup {

    public static ProducerFactory<String, String> producerFactory(
            String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);

        factory.setTransactionIdPrefix(
                "order-service-test-" + UUID.randomUUID() + "-");
        return factory;
    }

    public static KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> factory) {
        return new KafkaTemplate<>(factory);
    }
}
~~~

In the example, the prefix is generated **once when creating the factory** to isolate one test instance from another. **Do not generate a new transactional ID for every record send** in an application that needs controlled reuse/fencing: the lifecycle of the transactional producer and prefix must be managed at the application-instance scope.

In production, the prefix should be **unique across concurrently running instances** to avoid unintended fencing, accompanied by an identity management policy when old instances are replaced. If two active processes share the same transactional.id, the older producer can be fenced.

With Spring Boot auto-configuration, a common declaration looks like:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    producer:
      acks: all
      transaction-id-prefix: orders-service-instance-a-
~~~

This is an **illustrative config**; in Kubernetes/multi-instance deployments, do not hard-code the same prefix across all pods. Uniqueness mechanisms must align with deployment identity and the policies of your Spring Kafka version.

Enabling a transactional producer does not automatically ensure the listener container also manages **offsets inside the same Kafka transaction**. That requires dedicated configuration in the consume-process-produce section.

## 8. Testing commit/abort with EmbeddedKafka

This is the core hands-on section. The test suite starts an Embedded Kafka broker, configures a real transactional producer, performs commits/aborts, and polls with a consumer having an explicit isolation level.

### 8.1. Test configuration

~~~java
package com.example.kafka.tx;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@Configuration
public class TxTestConfiguration {

    @Bean
    public ProducerFactory<String, String> txProducerFactory(
            EmbeddedKafkaBroker broker) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);
        factory.setTransactionIdPrefix(
                "tx-it-" + UUID.randomUUID() + "-");

        return factory;
    }

    @Bean
    public KafkaTemplate<String, String> txKafkaTemplate(
            ProducerFactory<String, String> txProducerFactory) {
        return new KafkaTemplate<>(txProducerFactory);
    }
}
~~~

Here Spring Kafka Test provides **EmbeddedKafkaBroker** via context when using \`@EmbeddedKafka\`. A unique prefix on the factory helps prevent fencing from identity reuse across test runs.

### 8.2. Test class: commit is visible, abort is invisible

~~~java
package com.example.kafka.tx;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TxTestConfiguration.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"tx.practice.records"},
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "transaction.state.log.num.partitions=1",
        "offsets.topic.replication.factor=1"
    }
)
class KafkaTransactionCommitIT {

    private static final String TOPIC = "tx.practice.records";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void committedRecordIsVisibleToReadCommittedConsumer() {
        String key = "commit-" + UUID.randomUUID();

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(TOPIC, key, "ORDER_CREATED").join();
            return null;
        });

        assertTrue(containsKey(key, "read_committed",
                Duration.ofSeconds(10)));
    }

    @Test
    void abortedRecordIsHiddenFromReadCommittedConsumer() {
        String key = "abort-" + UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> kafkaTemplate.executeInTransaction(operations -> {
                    operations.send(TOPIC, key, "ORDER_CREATED").join();
                    throw new IllegalStateException("FAIL_BEFORE_COMMIT");
                }));

        assertFalse(containsKey(key, "read_committed",
                Duration.ofSeconds(3)));
    }

    @Test
    void readUncommittedCanObserveAbortedRecord() {
        String key = "aborted-debug-" + UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> kafkaTemplate.executeInTransaction(operations -> {
                    operations.send(TOPIC, key, "ORDER_CREATED").join();
                    throw new IllegalStateException("FORCE_ABORT");
                }));

        assertTrue(containsKey(key, "read_uncommitted",
                Duration.ofSeconds(10)));
        assertFalse(containsKey(key, "read_committed",
                Duration.ofSeconds(3)));
    }

    private boolean containsKey(
            String expectedKey, String isolation, Duration timeout) {

        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());
        props.put(ConsumerConfig.GROUP_ID_CONFIG,
                "tx-it-consumer-" + UUID.randomUUID());
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, isolation);

        try (KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of(TOPIC));
            long deadline = System.nanoTime() + timeout.toNanos();

            while (System.nanoTime() < deadline) {
                var records = consumer.poll(Duration.ofMillis(250));
                for (var record : records) {
                    if (expectedKey.equals(record.key())) {
                        return true;
                    }
                }
            }
            return false;
        }
    }
}
~~~

**How the test works:**

- \`executeInTransaction\` opens a transaction, executes the callback, commits when the callback returns normally, or attempts to abort if the callback throws an exception.
- \`operations.send(...).join()\` waits for Kafka to ACK the record send within the transaction. This **is not yet a commit**.
- Each test uses a **random message key**; tests do not depend on records from other tests.
- Each consumer uses a fresh group ID and \`auto.offset.reset=earliest\` to read the log from the beginning and filter by the test key.
- \`read_committed\` sees only records from committed transactions (or non-transactional records).
- \`read_uncommitted\` can see records from aborted transactions as well, so **never use it to prove exactly-once visibility**.
- Polling uses a **finite deadline**, not \`Thread.sleep\` guessing broker state.

### Notes on negative testing

An assertion saying **"key not seen within 3 seconds"** is meaningful only after proving the producer successfully sent the record before aborting and the test consumer read from the right topic/partition. Placing \`send(...).join()\` before the exception distinguishes "not seen because the transaction aborted" from "not seen because the record was never sent."

In high-load CI environments, use a controlled higher timeout paired with a positive test. You can check the record with read_uncommitted in the same scenario to prove the log contains the aborted record.

### Do tests always see records from other transactions?

No. A \`read_committed\` consumer can temporarily be blocked at the **Last Stable Offset** if an open transaction still exists at a lower offset on the partition. The test suite above waits for the transaction to finish before polling, reducing this risk. When concurrent tests share a topic, an open transaction in another test can cause flakiness; it is best to isolate topics/brokers or avoid running them in parallel depending on test configuration.

## 9. Testing multiple records in the same transaction

A transaction can send multiple records and then commit. Tests must verify **the whole set**, not just a single record:

~~~java
String transactionKey = "order-" + UUID.randomUUID();

kafkaTemplate.executeInTransaction(operations -> {
    operations.send("tx.orders", transactionKey,
            "ORDER_CREATED").join();
    operations.send("tx.audit", transactionKey,
            "AUDIT_CREATED").join();
    return null;
});
~~~

In this test, both topics **tx.orders** and **tx.audit** must be pre-created. After the callback commits, a read_committed consumer on each topic must see the corresponding record with the same key. In the abort scenario, neither topic may return that transaction's records to a read_committed consumer.

A Kafka transaction can span multiple topics/partitions, but **global ordering across partitions is not guaranteed**. Tests should assert counts and key/value sets per partition or business correlation, not assume consumers across two partitions receive records in a strict global order.

### Do not assert record count alone

A test might observe two records while one has the wrong key, value, or topic. Check:

| Check | Reason |
|---|---|
| Correct topic | Did not publish to the wrong destination |
| Correct key | Preserves partitioning and business correlation |
| Correct value/schema | Transaction atomicity does not guarantee valid payloads |
| Correct record count | No missing or duplicate writes within the contract |
| read_committed visibility | Proves records were committed |
| Invisible on abort | Proves isolation |
| No partial output across topics | Proves transaction boundary when supported by broker |

## 10. read_committed vs. read_uncommitted consumers

Imagine a topic containing these records:

~~~text
offset 0: non-transactional A
offset 1: TX-1 record B
offset 2: TX-1 record C
offset 3: TX-1 ABORT marker
offset 4: TX-2 record D
offset 5: TX-2 COMMIT marker
~~~

This is a conceptual diagram; actual markers and log positions depend on Kafka internals.

| Consumer isolation | Business records that may be returned |
|---|---|
| \`read_uncommitted\` | A, B, C, D |
| \`read_committed\` | A, D |

A \`read_committed\` consumer **does not necessarily receive consecutive offsets** because aborted transactional data and control records still occupy positions in the Kafka log. Therefore, do not write tests expecting offsets of two consecutive successful business records to always increment by exactly one.

While a transaction is still **open**, a read_committed consumer may not yet see records beyond the Last Stable Offset even though they appear to be in the log. Account for this behavior in tests so it is not misread as a commit failure.

## 11. KafkaTemplate.executeInTransaction and KafkaTransactionManager

Spring Kafka supports multiple ways to manage transactions:

**Local transactions**: \`KafkaTemplate.executeInTransaction(callback)\` opens and closes a transaction around the callback on a transactional ProducerFactory. Suitable for testing commit/abort as shown above.

**Spring-managed transactions**: \`KafkaTransactionManager\` can be used with \`@Transactional\` and matching KafkaTemplate/container configurations. Spring then manages transactions scoped to the method or listener.

Example transaction manager bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> txProducerFactory) {

    return new KafkaTransactionManager<>(txProducerFactory);
}
~~~

When using \`@Transactional\`, select the right transaction manager in applications that use both a database and Kafka. If the context has multiple PlatformTransactionManagers, an unqualified annotation may pick the wrong manager.

Do not **arbitrarily nest \`executeInTransaction\`** inside an active Kafka transaction scope and assume they form a single transaction. Local transactions have their own lifecycle under KafkaTemplate semantics; clearly decide which component owns the transaction boundary and test that specifically.

## 12. Consume-process-produce: outputs and offsets must commit together

A more critical reliability case than a standalone producer:

~~~text
orders.input
      |
      v
@KafkaListener
      |
      v
Process order
      |
      v
KafkaTemplate.send(orders.enriched)
      |
      v
Kafka transaction COMMIT:
  - output record is committed
  - orders.input offset is committed in the same transaction
~~~

If the listener succeeds and the transaction commits, the input record is marked processed for the consumer group and the output becomes visible to downstream read_committed consumers.

If the listener throws an exception before commit, the Kafka transaction is aborted by the container, uncommitted output records remain invisible to read_committed, and the consumer group offset is **not committed as part of the failed transaction**. The container/error handler may seek/retry per policy, causing the input to be reprocessed.

Crucially, a **Kafka-aware transaction manager is required on the listener container**; setting KafkaTemplate.transactionIdPrefix alone does not automatically place listener offsets in the same transaction.

### Listener container configuration (Spring Kafka 3.2+ illustration)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
transactionalKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory,
        KafkaTransactionManager<String, String> txManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(txManager);
    return factory;
}
~~~

In some older Spring Kafka versions, the container transaction manager API was named **setTransactionManager**. Verify this against your project's version. ConsumerFactory should use:

~~~properties
enable.auto.commit=false
isolation.level=read_committed
~~~

Inside a Spring Kafka listener container, offset commits and retry/seek handling have specific semantics; do not manually call \`consumer.commitSync()\` inside a transactionally managed listener assuming it will join the Kafka transaction.

### Illustrative listener

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderTransformListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderTransformListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.input",
        groupId = "orders-transformer",
        containerFactory =
            "transactionalKafkaListenerContainerFactory"
    )
    public void onOrder(
            String value,
            @Header(KafkaHeaders.RECEIVED_KEY) String key) {

        if ("FAIL_BEFORE_COMMIT".equals(value)) {
            throw new IllegalStateException("TRANSFORM_FAILED");
        }

        kafkaTemplate.send("orders.enriched", key,
                "ENRICHED:" + value);
    }
}
~~~

This snippet assumes KafkaTemplate and the listener container share the appropriate transactional ProducerFactory/transaction context. **Do not use this pattern to claim exactly-once with an external database**. If poison messages must be handled, configure a bounded failure/recovery policy so the listener does not retry infinitely.

## 13. Testing offset commits with a real listener

To prove a consume-process-produce transaction, checking the output is not enough; you must verify whether the **input consumer group offset** changed.

Example record on topic \`orders.input\`, partition 0, offset 10:

~~~text
Input offset = 10

Case SUCCESS
  Listener processes -> sends output
  Kafka TX COMMIT
  Output visible to read_committed
  Group committed offset = 11

Case FAILURE BEFORE COMMIT
  Listener sends output then throws exception
  Kafka TX ABORT
  Output not visible to read_committed
  Group committed offset does not advance to 11 from failed TX
  Input may be redelivered/retried
~~~

In Kafka, the **committed offset is the next position to read**, so after successfully processing offset 10, the group offset normally becomes 11. Tests must calculate partitions, assignments, input records, and groupIds accurately.

### Integration test workflow

1. Create input/output topics in EmbeddedKafka or Testcontainers.
2. Create a transactional listener container using a dedicated consumer group **tx-orders-test-...**.
3. Send an input record and wait for listener processing via \`CountDownLatch\` or a bounded condition check.
4. For the **success path**, read output with read_committed and verify key/value.
5. Use **AdminClient** or consumer metadata APIs to inspect the group's committed offset on the corresponding partition.
6. For the **failure path**, force the listener to throw an exception **after sending but before returning normally**.
7. Block or bound redelivery in the test to observe the aborted state; confirm output is not visible and the group offset did not advance due to the failed transaction.
8. Let the next attempt succeed, verify **one final committed output**, committed offset, and no visible duplicates.

A failure-path test must control **AfterRollbackProcessor**, the error handler, and redelivery timing. Otherwise, the listener may retry and succeed so quickly that by the time the test inspects the offset, the new commit has already happened; then an assertion that "the offset did not advance" no longer reflects the initial failed attempt.

### Inspecting committed offsets with AdminClient

Conceptual example:

~~~java
import java.util.Set;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

// adminClient is created with appropriate bootstrap.servers.
var offsets = adminClient.listConsumerGroupOffsets(
        "orders-transformer-test-group")
        .partitionsToOffsetAndMetadata()
        .get();

var metadata = offsets.get(
        new TopicPartition("orders.input", 0));

// metadata.offset() is the next committed offset when metadata != null.
~~~

This snippet only illustrates reading offsets; properly create/close AdminClient and synchronize with the consumer group in tests. Do not assert a hard-coded initial offset if the broker/topic might already hold records from other tests.

## 14. Testing rollback after sending output

An important failure to test: the listener **already called KafkaTemplate.send(...)**, but an exception happens afterward.

~~~text
Input O101
  |
  v
Listener -> send output O101
  |
  v
Exception before listener completes
  |
  v
Kafka TX ABORT
  |
  +-- Output O101: not visible to read_committed
  |
  +-- Input offset: not committed as a successful TX
~~~

If you only mock \`KafkaTemplate.send\` and verify the method was called once, the test **does not prove rollback visibility**. You must use a real Kafka broker and a read_committed consumer.

To make the test repeatable, a **fail once** toggle can throw an exception on the first attempt and allow the second attempt to succeed:

~~~java
private final AtomicBoolean failOnce = new AtomicBoolean(true);

// Inside demo/test listener:
kafkaTemplate.send("orders.enriched", key,
        "ENRICHED:" + value);
if (failOnce.compareAndSet(true, false)) {
    throw new IllegalStateException("FAIL_AFTER_SEND");
}
~~~

If implementing a listener this way, account for concurrency and partition test state so \`failOnce\` is not shared across unrelated records. When the read_committed consumer eventually sees **one output**, the test should still observe **aborted transaction markers/metrics or two-phase gating** to prove the first output never became committed, rather than concluding solely from total count.

## 15. Choosing the right transaction boundary in Spring

Two concepts are frequently confused:

1. **Kafka producer transaction:** commits/aborts records written to Kafka and can include consumer offsets.
2. **Database transaction:** commits/rolls back SQL/JPA operations.

Example:

~~~text
Business method
   |
   +-- INSERT order into PostgreSQL
   |
   +-- KafkaTemplate.send(order-created)
   |
   v
method returns
~~~

A \`@Transactional\` annotation **does not automatically make PostgreSQL and Kafka into a single XA transaction**. Spring can synchronize commit ordering across transaction managers, yet a crash window remains where one resource committed and the other did not.

### DB-first scenario

~~~text
DB transaction commits
        |
        v
Application crashes
        |
        X
Kafka transaction not yet committed
~~~

Result: the database has the record, but Kafka consumers never see the event.

### Kafka-first scenario

~~~text
Kafka transaction commits
        |
        v
DB transaction fails
        |
        X
Kafka event already visible
~~~

Result: Kafka has the event even though the DB never confirmed the corresponding change.

**Kafka commit tests only prove Kafka transaction atomicity**, not atomicity between Kafka and a SQL database.

### Transactional outbox

For critical DB + event workflows, a widely used option is:

~~~text
Business DB transaction:
   INSERT order
   INSERT outbox_event(order_id, event_type, payload)
   COMMIT
        |
        v
Outbox publisher / CDC
        |
        v
Kafka publish
        |
        v
Consumer idempotency by eventId
~~~

The outbox turns writing business data and recording the event-publish request into **one DB transaction**. The publisher can still send duplicates if the broker receives the message but the ACK is lost, so consumers need deduplication/idempotency. This is not automatic end-to-end Kafka + DB exactly-once.

## 16. Testing commits when a database is involved

For services that write to both a DB and Kafka, add scenarios beyond Kafka-only tests:

| Scenario | DB | Kafka | What to assert |
|---|---|---|---|
| Happy path | Commit | Commit | Row and event are consistent |
| DB fails before commit | Rollback | Unpublished/aborted per orchestration | No false business event published |
| DB commits, Kafka fails | Commit | Not committed | Gap is audited/reconciled/handled via outbox |
| Kafka commits, DB fails | Rollback | Commit | Alert/compensation occurs per design |
| Process crashes between commits | One side may commit | Other side uncertain | Recovery neither loses events nor creates uncontrolled duplicates |
| Outbox publisher retry | Order + outbox committed | Publish may repeat | Event ID dedup and outbox state are accurate |

A sound test must specify the **chosen architecture** (DB-first, Kafka-first, outbox). Do not assert that both roll back when no distributed transaction protocol is present.

### Example outbox schema

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(64) NOT NULL,
    payload        TEXT NOT NULL,
    publish_status VARCHAR(20) NOT NULL
);
~~~

Tests can verify that when the DB transaction rolls back, both the business row and the outbox row are absent; when it commits, both exist. Then test the publisher separately to prove the event reaches Kafka and consumption is idempotent on redelivery.

## 17. Transaction timeout and producer fencing

Kafka transactions have operational limits:

- **transaction.timeout.ms**: how long the broker allows a transaction to remain open before timing out/aborting under Kafka rules.
- **max.block.ms** and request/delivery timeouts: bound producer operations and can impact latency and failures.
- **transactional.id**: identity used by the coordinator to manage producer epochs and fencing.
- **transactional.id.expiration.ms**: broker policy for expiring transactional IDs; understand this before relying on fencing for long-idle systems.

Do not hold a transaction open while calling an HTTP API that might hang for tens of minutes without a timeout. Long transactions degrade read_committed consumer visibility due to the LSO, lock producer resources, and complicate recovery.

### Producer fencing

If two different producers initialize transactions with the **same transactional.id**, the newer producer can fence the older one. The older producer loses permission to commit as a valid owner.

~~~text
Producer A: transactional.id = orders-instance-1
    |
    v
Producer B starts with same transactional.id
    |
    v
Coordinator advances producer epoch
    |
    v
Producer A: fenced, cannot continue valid transactions
~~~

This is an ownership protection mechanism, not a random glitch to retry forever. **ProducerFencedException** typically requires closing the old producer and handling lifecycle/identity rather than retrying the same instance as a transient network error.

### Testing fencing

A dedicated integration test can:

1. Create two KafkaProducers with the same \`transactional.id\`.
2. Call \`initTransactions\` on Producer A and begin a transaction.
3. Call \`initTransactions\` on Producer B with the same identity.
4. Have A attempt a transactional operation/commit and observe the appropriate fencing error.
5. Verify that no transaction from the fenced producer A becomes unexpected valid output.
6. Close both producers in a finally block.

Because the timing of broker epoch updates and network responses affects the exact exception, do not hard-code a single stack trace message as the sole criterion. Rely on exception class/lifecycle and visibility outcomes.

## 18. Simulating failures at commit time

There are three distinct points:

~~~text
1. BEFORE COMMIT:
   Callback already sent, commit not yet called

2. DURING COMMIT:
   Commit request sent, ACK may be lost

3. AFTER COMMIT:
   Broker already committed, app fails on a later step
~~~

### Failure before commit

Test aborts by throwing an exception inside the \`executeInTransaction\` callback as in section 8. This is easy to control, allowing you to assert that Spring Kafka attempts to abort the transaction and verify via polling.

### Failure after commit

Example:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("tx.practice.records", key,
            "COMMITTED").join();
    return null;
});

// Transaction already committed before the next line runs.
throw new IllegalStateException("FAIL_AFTER_COMMIT");
~~~

The final exception **does not roll back the already-completed Kafka transaction**. The test must confirm the record remains visible to read_committed.

### Failure during commit: ambiguous outcome

Simulating a broker crash or network cut right as the client awaits the \`commitTransaction()\` ACK can produce an **ambiguous outcome** from the client's viewpoint. Never conclude "the producer got an exception, so the broker must have aborted."

To simulate realistically, use:

- Kafka via Testcontainers plus a network proxy capable of controlling connections.
- A mechanism supported by the test harness to intercept/fail the commit request.
- Broker/coordinator logs and a read_committed consumer during verification once the cluster stabilizes.
- A unique correlation key to check whether the transaction actually became visible.
- Recovery logic able to handle both **commit succeeded** and **commit did not succeed**.

Do not treat a mocked \`KafkaTemplate.send\` throwing an exception as a simulation of a real commit failure. **Send failures** and **commit failures** happen at different boundaries.

## 19. Testcontainers for broker failure scenarios

Testcontainers is useful when you need to pin a Kafka version and create an isolated environment. Gradle example:

~~~groovy
dependencies {
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Example Testcontainers test structure:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class KafkaTxContainerIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse("apache/kafka:3.8.0"));

    @Test
    void committedRecordIsVisible() {
        String bootstrapServers = kafka.getBootstrapServers();
        // Create transactional ProducerFactory from bootstrapServers.
        // Create topic, send via executeInTransaction, verify read_committed.
    }
}
~~~

The **apache/kafka:3.8.0** tag is just an example for pinning an image version in tests; choose a version compatible with your client and runtime. Testcontainers classes/packages change across versions; verify dependencies and APIs when applying.

**Testcontainers does not automatically simulate commit ACK loss.** If a test merely starts KafkaContainer and calls commit, it is still primarily a happy-path integration test. Testing ambiguity requires an explicit fault-injection scenario such as a network proxy or controlled broker interruption.

## 20. Do not use sleep to assume a commit occurred

Anti-pattern:

~~~java
kafkaTemplate.send(topic, key, value);
Thread.sleep(500);
assertTrue(consumed);
~~~

Wrong because:

- \`send\` may not have been ACKed by the broker yet.
- The record may belong to an uncommitted transaction.
- 500 ms depends on machine and broker load.
- The consumer may not have been assigned partitions yet.
- The test does not control the isolation level.

Instead:

1. Wait on \`send(...).join()\` when confirming the broker ACKed the record inside the transaction.
2. Complete the transaction via \`executeInTransaction\` or a transaction manager.
3. Poll with a \`read_committed\` consumer using a **finite timeout**.
4. Filter using a test key or dedicated topic.
5. For listeners, use latches, Awaitility, or offset/output conditions rather than hard-coded sleeps.

**Send ACK does not replace commit verification.** Tests need the third step.

## 21. Reliability test matrix

| ID | Scenario | Expected result |
|---|---|---|
| TX-01 | Single record and successful commit | read_committed sees the record |
| TX-02 | Two records in one transaction, commit | read_committed sees both records |
| TX-03 | Send then exception before commit | Transaction aborts; read_committed does not see the record |
| TX-04 | Aborted record with read_uncommitted | Can observe the aborted record |
| TX-05 | Transaction across two topics | Entire set commits/aborts properly |
| TX-06 | Listener processes successfully | Output visible + input group offset committed |
| TX-07 | Listener sends then throws | Output aborts; input offset not committed by failed attempt |
| TX-08 | Listener fails once then succeeds | Redelivery and one final committed output |
| TX-09 | Producer fencing | Old producer cannot commit validly after being fenced |
| TX-10 | Transaction timeout | Long transaction handled per broker policy |
| TX-11 | Exception after commit | Record remains visible, not rolled back |
| TX-12 | Network drop during commit | Outcome must be verified, not guessed from client exception |
| TX-13 | DB commits then Kafka fails | Test detects consistency gap/outbox recovery |
| TX-14 | Kafka commits then DB fails | Test does not assume DB rollback cancelled Kafka event |
| TX-15 | Producer restarts with same identity per policy | Fencing/recovery happens in a controlled way |
| TX-16 | Consumer using read_uncommitted | Test demonstrates isolation difference vs. read_committed |
| TX-17 | Multi-partition in same transaction | Does not assume strict ordering across partitions |
| TX-18 | Broker/consumer restart | Output and offsets remain accurate after recovery |

Each case should specify:

- Exact topic and partition.
- Unique transaction key/correlation ID.
- Producer identity and transaction policy.
- Isolation level of the consumer used for assertions.
- Group ID, input offset, and expected committed offset where applicable.
- Exact fault injection point.
- Finite timeouts and resource cleanup.
- Observed durable outcomes, not only application logs.

## 22. Testing transaction commits with retry/DLT

Spring Kafka provides retries, error handlers, DefaultAfterRollbackProcessor, and Dead Letter Topics (DLTs). When a listener container runs transactionally, some failures are handled via **rollback + seek/redelivery**, which differs from error handling in a non-transactional container.

If a record causes a permanent failure:

~~~text
Input record
    |
    v
Listener throws
    |
    v
Kafka TX ABORT
    |
    v
AfterRollbackProcessor / recovery policy
    |
    +-- Bounded retries
    |
    +-- Recovery / DLT per configuration
~~~

To avoid infinite loops, tests must define the retry count and conditions for routing to a DLT. When using a DLT, verify:

- The record has the allowed key/value/headers.
- Primary output is not visible when the processing transaction failed.
- When recovery decides to skip the record, the consumer group offset is handled per the configured recovery mechanism.
- Whether DLT publishing has its own transaction, and which transaction owns the commit.
- Sensitive payloads are not logged in exception/DLT headers.

**Do not assume every combination of non-blocking retry topics and container transactions is supported identically.** Confirm the limits of your Spring Kafka version and design error handling around the transaction model supported by that version's documentation.

## 23. Observing transaction state in operations

Good logs distinguish **send**, **commit attempt**, **committed**, and **aborted**:

~~~text
event=kafka.transaction.begin
transactionRef=tx_02f1
jobExecutionId=835
topic=orders.events

event=kafka.producer.send.acked
transactionRef=tx_02f1
recordCount=2

event=kafka.transaction.committed
transactionRef=tx_02f1
recordCount=2

event=kafka.transaction.aborted
transactionRef=tx_02f2
reasonCode=BUSINESS_PROCESSING_FAILED
~~~

These values illustrate an application audit schema, not default Kafka logs. In multi-threaded apps, proper context propagation is needed to avoid attaching the wrong transactionRef.

If commit fails or the outcome is unknown, use a state like **COMMIT_UNCONFIRMED**—do not automatically log **ABORTED** without evidence that the broker aborted.

Metrics to monitor:

| Group | Metrics |
|---|---|
| Producer | Transaction commit/abort rate, transaction duration, errors |
| Kafka client | Request latency, timeout/error, producer metrics |
| Consumer | Lag, read_committed visibility, committed offsets |
| Listener | Process failures, retries, redelivery, DLT count |
| Broker | Transaction coordinator health, under-replicated partitions, ISR |
| Business | Input/output reconciliation, duplicate keys, missing events |
| Operations | Time to recover, last successful publish/checkpoint |

Specific metrics can be exported via Kafka client JMX, Micrometer/Spring Kafka instrumentation, and broker monitoring. Meter names vary by version; do not assume identical metric names across all deployments.

**Do not use dynamic transactional.id, orderId, or jobExecutionId as uncontrolled Prometheus labels**, as that causes high cardinality; keep dynamic IDs in logs/traces/audits with appropriate retention and access control.

## 24. Runbook when transaction commit fails

When a service reports a commit failure or a read_committed consumer does not see expected output:

1. **Determine scope:** topic, partition, key, transactional.id, producer instance, consumer group, time window.
2. **Classify the error:** send failure, listener exception before commit, producer fenced, transaction timeout, or unknown commit ACK.
3. **Inspect the broker:** availability, transaction coordinator, ISR, replication, relevant logs, and producer metrics.
4. **Read with a read_committed consumer** at the exact offset/partition to determine whether the record was published.
5. **Cross-check read_uncommitted when investigating**, but never treat seeing a record there as a committed success.
6. **For consume-process-produce**, inspect the input group committed offset and output transaction together.
7. **Assess side effects outside Kafka:** DB rows, outbox, API receipts, or emitted files.
8. **Determine replay policy:** do not blindly resend if the outcome is uncertain and downstream is not idempotent.
9. **Recover safely** via reprocessing, idempotency keys, outbox, or compensation depending on architecture.
10. **Reconcile final state**, marking the business event READY only when all required conditions are satisfied.

If a producer was fenced, close the old producer and investigate identity/lifecycle. If a transaction stays open too long, check timeouts and blocking operations. If output is missing while input offsets committed, check whether offsets were committed **outside** the transaction or whether the listener container uses the right transaction manager.

### Do not alter consumer group offsets arbitrarily

Resetting/altering offsets does not recover lost outputs and can cause widespread reprocessing. Before intervening, ensure group consumers are stopped/coordinated properly, record old offsets, and verify downstream idempotency.

## 25. Common mistakes

**Tests that only verify KafkaTemplate.send was called.** Mocks prove only the call; they do not prove broker transaction commits and read_committed visibility.

**Confusing send ACK with commit ACK.** The broker acknowledging a record does not mean the transaction committed.

**Using a read_uncommitted consumer to assert exactly-once.** It can see aborted records, producing false results.

**Omitting transaction.state.log settings on a single-node test broker.** Transactional producers can fail to initialize because internal topics require matching replication settings.

**Sharing transactional.id prefixes across active instances.** Producers can fence each other.

**Using the same unisolated topic/group for every test.** Old data and old offsets cause false positives or false negatives.

**Thread.sleep then assert.** Flaky tests that fail to verify commit boundaries.

**Counting records on only one topic in a multi-topic transaction.** Can miss a producer writing to the wrong topic or payload.

**Assuming business record offsets are consecutive.** Aborted records and transaction markers still occupy log positions.

**Enabling transactions on the producer without enabling them on the listener container.** Consume-process-produce may fail to commit input offsets in the same transaction.

**Manually committing consumer offsets outside the transaction.** Can lose data when outputs have not committed.

**Concluding DB and Kafka are atomic because of `@Transactional`.** Two resources have independent commit boundaries without a proper synchronization protocol.

**Retrying an uncertain commit failure like a normal send failure.** Can create duplicates if the transaction actually committed.

**Assuming post-commit errors make the record disappear.** Application exceptions after commit do not roll back a completed Kafka transaction.

**Ignoring producer fencing.** Continuing to use a fenced producer is not safe recovery.

**Unbounded retries on poison messages.** Listeners can redeliver forever, growing lag and stalling group progress.

**Logging raw payloads/headers for debugging.** Easily leaks PII, tokens, or business data into centralized logs.

## 26. Workflow to implement transaction commit tests

To integrate transaction commit tests into a Spring Kafka pipeline:

1. **Lock down guarantee scope:** Kafka producer-only or consume-process-produce with offsets; which DB/APIs sit outside the transaction.
2. **Set up test broker:** EmbeddedKafka for functional tests, Testcontainers for production-like scenarios and fault injection.
3. **Configure transactional producer:** managed prefix, serializers, and appropriate ACKs.
4. **Create a read_committed consumer with a dedicated group ID:** poll with a deadline and unique test keys.
5. **Test happy-path commit:** verify topic/key/value and record visibility.
6. **Test abort:** send ACKed then throw exception before commit; read_committed sees no record.
7. **Compare read_uncommitted:** observe the aborted record to prove the isolation boundary.
8. **If using a listener:** test co-committing output and input offset, rollback, and controlled redelivery.
9. **Test fencing/timeouts and commit ambiguity:** never assume an exception means the transaction rolled back.
10. **Test side effects outside Kafka:** DB/outbox, APIs, idempotency, and reconciliation.
11. **Add logs/metrics/alerts:** commits, aborts, timeouts, fencing, lag, retries, and business outcomes.
12. **Integrate into CI:** finite timeouts, broker/resource cleanup, avoid parallel tests sharing transactional identities or unisolated topics.

A reliable test suite must prove **the outcome observed by consumers at the transaction boundary**, not merely that a method was called. In Spring Kafka, pairing **commit visible / abort invisible via read_committed** with **consumer offsets inside the same Kafka transaction** for consume-process-produce flows forms a core pillar of reliability testing. When workflows also span databases, APIs, or files, keep guarantee boundaries explicit and add idempotency, outbox, auditing, and reconciliation rather than claiming a Kafka transaction alone solves every data consistency problem.
