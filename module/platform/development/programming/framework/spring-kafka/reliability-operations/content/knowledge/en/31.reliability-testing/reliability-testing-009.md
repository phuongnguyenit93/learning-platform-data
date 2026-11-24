# Testing Exactly-Once Flows in Spring Kafka Reliability Operations

In a Spring Kafka application, a consumer receives payment events, computes results, and publishes events to another topic. When the process fails **after sending output but before completing processing**, what happens? Does the consumer re-read the input? Does the output appear twice? Is the consumer group offset committed even though the output rolled back?

Those are the questions that must be answered by **integration tests for an exactly-once flow**. A unit test that only verifies `KafkaTemplate.send(...)` was called once is not enough to prove correctness, because bugs usually live at the boundary of **Kafka transactions, producer output, consumer offsets, and broker commits**.

This lesson belongs to **Spring Kafka Reliability Operations → Reliability Testing**, focusing on a **Kafka input → processing → Kafka output** flow managed by Spring Kafka transactions. We will build the configuration, write a broker-backed test, intentionally inject a mid-flight failure, verify the output a `read_committed` consumer actually sees, check the committed offset, and then expand into retries, restarts, fencing, and writing data outside Kafka.

Java examples use **Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka 3.x, and Java 17** as the baseline. When using Spring Kafka 4.x or Spring Boot 4.x, cross-check API signatures, Kafka client versions, and compatible configuration; the underlying Kafka transaction principles remain foundational.

## 1. What does "exactly once" actually guarantee?

Saying "the consumer processes exactly once" is easily misunderstood. In Spring Kafka, **exactly-once semantics (EOS)** for Kafka transactions aim to guarantee consistent recording of **read → process → write**: **output records written to Kafka and consumer offsets are committed in the same Kafka transaction**.

That does **not** mean the listener method or business code executes only once. When a transaction rolls back, Kafka can redeliver the same input so the listener runs again.

| Aspect | What can happen under Kafka EOS | Is it guaranteed "only once"? |
| --- | --- | --- |
| Listener invocation | May be called multiple times for the same input after rollback | **No** — reading/processing is at-least-once in nature |
| Output sent in an aborted transaction | Record may physically exist in the log but is hidden from `read_committed` consumers | **Not treated as a committed output** |
| Kafka output of a successful transaction | Successful record becomes visible to `read_committed` consumers | **Yes**, within the Kafka transaction scope of a properly designed flow |
| Consumer group input offset | Included in the transaction alongside output; rollback does not commit that offset | **Yes**, sharing the Kafka transaction commit boundary |
| Separate database write, REST call, email send | May have already created side effects even if the Kafka transaction rolls back | **No**, Kafka EOS does not automatically cover systems outside Kafka |
| Two distinct inputs with duplicate business IDs | Both records can still be processed as two valid inputs | **No** automatic deduplication by business key |

Desired example:

```text
input topic: orders.in
    offset 42: {"orderId":"O-42","status":"PAID"}
          |
          v
  @KafkaListener processes
          |
          +--> KafkaTemplate.send("orders.out", ...)
          |
          +--> records input offset 43 in the same transaction
          |
          v
   COMMIT Kafka transaction
          |
          v
read_committed consumer sees 1 output
group offset after commit = 43
```

When an error occurs before commit:

```text
Attempt 1:
  read offset 42
  send output into Kafka transaction T1
  listener throws exception
  ABORT T1 --> output invisible to read_committed
               offset 43 is not committed

Attempt 2:
  re-read offset 42
  send output into Kafka transaction T2
  listener succeeds
  COMMIT T2 --> output becomes visible
                offset 43 is committed
```

**Critical testing criterion:** the listener executed again, yet the `read_committed` consumer observes **only one committed Kafka result**, and the consumer group advanced to the right offset. You cannot prove EOS simply from `attemptCount == 1`; in fact, a rollback test typically expects `attemptCount >= 2`.

## 2. Comparing at-most-once, at-least-once, and Kafka exactly-once

| Strategy | Typical implementation | Crash risk | What tests must confirm |
| --- | --- | --- | --- |
| **At-most-once** | Commit offset before processing/output succeeds | Results can be lost if the process dies after offset commit | Items may be lost; no replay expected |
| **At-least-once** | Process/send output then commit offset separately | Duplicate output possible if crashing before offset commit | Replay occurs; downstream writers/consumers need dedup |
| **Kafka exactly-once read–process–write** | Kafka output and consumed offsets share one transaction | Listener may replay, but aborted output is invisible to `read_committed` | Single committed result, consistent offsets, no aborted record leaks |

Kafka EOS does not prevent another producer or client from **explicitly sending the same payload twice** in two separate committed transactions. Nor does it enforce "an order must only be paid once" by business key. That is a business invariant requiring its own unique keys, idempotency, or deduplication.

Therefore, clearly name two test layers:

- **Transactional EOS test:** do Kafka output and input offset commit/roll back together?
- **Business idempotency test:** if two separate inputs carry the same `orderId`, are business outcomes duplicated?

This lesson prioritizes the first test, then explains how to add the second.

## 3. How Spring Kafka implements read–process–write transactions

When a listener container is configured with a `KafkaAwareTransactionManager` (in Spring Kafka 3.x, typically `KafkaTransactionManager`), the container starts a Kafka transaction **before invoking the listener**.

Success flow:

```text
KafkaMessageListenerContainer
        |
        v
BEGIN Kafka transaction
        |
        v
Consumer.poll() / record reaches listener
        |
        v
@KafkaListener
    KafkaTemplate.send(output)
        |
        v
Listener returns normally
        |
        v
sendOffsetsToTransaction(
    next consumed offset,
    consumer group metadata
)
        |
        v
COMMIT Kafka transaction
        |
        +--> output visible to read_committed
        |
        +--> consumer group offset committed
```

Failure flow:

```text
BEGIN Kafka transaction
      |
      v
@KafkaListener
      |
      +--> send output
      +--> throw RuntimeException
      |
      v
ABORT Kafka transaction
      |
      +--> output invisible to read_committed
      +--> offset not committed in that transaction
      |
      v
AfterRollbackProcessor / seek / replay
      |
      v
Same input can be re-read
```

In Spring Kafka 3.x, **`EOSMode.V2` is the supported EOS mode**, coordinating group metadata and the producer for proper broker fencing. The system requires a Kafka broker supporting the relevant protocol (Kafka broker **2.5+** for EOS V2 per Spring Kafka 3.x documentation); for new deployments, pick broker/client versions supported by your project's current stack.

Core prerequisites:

1. The producer has a **`transactional.id`**, usually via `transactionIdPrefix` on the producer factory.
2. The listener container runs with a real **Kafka transaction manager**, not merely a transactional `KafkaTemplate` while the container still commits offsets via another path.
3. `enable.auto.commit=false` on the consumer; let the container manage offsets.
4. Downstream consumers use **`isolation.level=read_committed`** when they must not see outputs from aborted transactions.
5. Outputs are sent **inside the listener's transaction**, not through another producer outside the transaction.
6. Exceptions that should trigger transaction rollback are **allowed to propagate out of the listener** per the designed error handling mechanism.
7. Every concurrently running application instance has a **distinct transaction ID prefix** to prevent unintended producer fencing.

## 4. Spring Boot configuration for Kafka transactions

Example `application.yml` for an environment with a Kafka broker:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: orders-eos-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: "orders-eos-${HOSTNAME:local}-"

app:
  kafka:
    topics:
      input: orders.in
      output: orders.out
```

With **Spring Boot 3.x**, setting `spring.kafka.producer.transaction-id-prefix` under matching auto-configuration causes Boot to create `KafkaTransactionManager` and wire it into the Boot-managed listener container factory. If your project defines custom `ConcurrentKafkaListenerContainerFactory` or producer factory beans, **verify that the exact bean used by the listener actually has the transaction manager configured**; a YAML property alone does not guarantee custom factories use it.

Meaning of the properties:

| Property | Reason |
| --- | --- |
| `transaction-id-prefix` | Enables producer transactions; factory assigns specific `transactional.id` values |
| `enable-auto-commit=false` | Prevents Kafka consumer from committing offsets outside the flow |
| `isolation-level=read_committed` | Inputs from transactional producers show only committed records |
| `auto-offset-reset=earliest` | When a new group has no offset, reads from the start so new tests/flows are not missed |
| `group-id` | Identifies the consumer group; committed offsets are tracked per topic/partition/group |
| `key/value serializer` | Producer writes data in the right format |
| `key/value deserializer` | Consumer reads data in the right format |

**Do not copy `transaction-id-prefix: orders-eos-local-` verbatim across multiple production pods.** Spring Kafka requires distinct prefixes across concurrently running instances. Inject an appropriate pod/instance identifier from deployment infrastructure. Pick a meaningful prefix that does not expose secrets or sensitive data.

### Using minimal Gradle configuration

For Spring Boot applications using a BOM/plugin for version management:

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

Depending on the project, Spring Kafka dependencies may also come from a starter or internal platform BOM. What matters is that **Spring Boot, Spring Kafka, Kafka client, and broker versions are compatible**. `spring-kafka-test` provides `@EmbeddedKafka`, `KafkaTestUtils`, and broker-backed testing utilities; mocking `KafkaTemplate` cannot substitute for broker transactions.

## 5. Business listener for a Kafka → Kafka flow

A simple application receives a text order event and writes the result to another topic:

```java
package com.example.eos;

import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderForwardingListener {

    private final KafkaTemplate<String, String> template;
    private final String outputTopic;

    public OrderForwardingListener(
            KafkaTemplate<String, String> template,
            @Value("${app.kafka.topics.output}") String outputTopic) {
        this.template = template;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(topics = "${app.kafka.topics.input}")
    public void onOrder(ConsumerRecord<String, String> input)
            throws Exception {

        String output = "processed:" + input.value();

        // Send participates in the listener container's transaction
        // when the container is configured with KafkaTransactionManager.
        template.send(outputTopic, input.key(), output)
                .get(10, TimeUnit.SECONDS);
    }
}
```

The example calls `get(...)` to surface producer errors immediately in an illustrative method; this is **not mandatory** for every listener. With Kafka transactions, the framework awaits required sends when ending the transaction; high-throughput applications can send asynchronously and handle errors cleanly via the transaction. Regardless of approach, **never treat `send()` returning a future as proof that the transaction committed**.

Do not call `template.executeInTransaction(...)` inside a listener container **when the goal is to send output inside the container's active transaction**. That method can create a **separate Kafka transaction**, breaking the intended shared commit boundary between output and offset. `executeInTransaction` fits producer-initiated operations outside a listener, such as publishing test inputs.

Never call `consumer.commitSync()` manually inside a transactional listener. Offsets must be sent into the **producer's transaction** via the container; committing on the consumer directly breaks output-offset atomicity testing.

## 6. Main test: failure after sending output but before commit

This is the most important test in the lesson. We want to verify a failure during the **danger window**:

```text
read input
   |
process
   |
send output (broker already received record inside transaction)
   |
   X  <-- intentionally throw exception here
   |
send offsets + commit  (attempt 1 must not reach here)
```

If transactions work properly:

- **First attempt** reads input, sends output, and throws an exception. Kafka transaction **aborts**.
- **Next attempt** receives the input again, sends output, and completes. Transaction **commits**.
- A `read_committed` consumer sees **exactly one output**.
- The group offset advances to the **next position** after the processed input; the rolled-back first attempt does not advance the group offset.
- The listener may run **twice** (or more under environmental errors), which **does not contradict** Kafka EOS.

### 6.1. Embedded broker with `@EmbeddedKafka`

The test needs a transaction-capable broker. For a single-broker test setup, Kafka requires lowering the internal transaction state topic's replication factor and min ISR to 1:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = { "eos.it.input", "eos.it.output" },
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

This is a **configuration solely for single-node test brokers**. Never copy `transaction.state.log.replication.factor=1` to a multi-broker production Kafka cluster; production transaction durability requires proper replication, ISR, and availability.

### 6.2. Complete integration test

Example file `src/test/java/com/example/eos/EosFlowIT.java`:

```java
package com.example.eos;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = EosFlowIT.TestApplication.class,
    properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=eos-it-tx-",
        "spring.kafka.consumer.group-id=eos-it-workers"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = { "eos.it.input", "eos.it.output" },
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class EosFlowIT {

    private static final String INPUT = "eos.it.input";
    private static final String OUTPUT = "eos.it.output";
    private static final String GROUP = "eos-it-workers";

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    FailingOnceForwarder forwarder;

    @Test
    void abortedOutputIsInvisibleAndOffsetCommitsWithSuccess()
            throws Exception {

        // Send INPUT in an independent Kafka transaction in the test.
        // KafkaTemplate has transactions enabled, so do not call send()
        // outside a transaction.
        template.executeInTransaction(operations -> {
            try {
                operations.send(INPUT, "order-42", "paid")
                        .get(10, TimeUnit.SECONDS);
            } catch (Exception ex) {
                throw new IllegalStateException(
                        "Cannot prepare test input", ex);
            }
            return null;
        });

        Map<String, Object> observerProps =
                consumerProperties(
                        "eos-output-observer-" + UUID.randomUUID());
        observerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

        try (Consumer<String, String> observer =
                     new DefaultKafkaConsumerFactory<String, String>(
                             observerProps).createConsumer()) {

            // Assign topic and seek to start to observe entire output
            // history; aborted records remain hidden by read_committed.
            broker.consumeFromAnEmbeddedTopic(observer, OUTPUT);

            ConsumerRecord<String, String> output =
                    KafkaTestUtils.getSingleRecord(
                            observer, OUTPUT, Duration.ofSeconds(30));

            assertEquals("order-42", output.key());
            assertEquals("processed:paid", output.value());

            // Expect only one committed output in this test case.
            assertEquals(0,
                    observer.poll(Duration.ofSeconds(2)).count());
        }

        // First attempt threw and rolled back; input was redelivered.
        assertTrue(forwarder.attempts.get() >= 2);

        // Prove consumer group offset was committed after the
        // successful transaction, not just by checking output.
        Map<String, Object> groupProps =
                consumerProperties(GROUP);

        TopicPartition inputPartition =
                new TopicPartition(INPUT, 0);

        try (Consumer<String, String> groupInspector =
                     new DefaultKafkaConsumerFactory<String, String>(
                             groupProps).createConsumer()) {

            var offsets = groupInspector.committed(
                    Set.of(inputPartition), Duration.ofSeconds(10));

            assertNotNull(offsets.get(inputPartition));
            assertEquals(1L,
                    offsets.get(inputPartition).offset());
        }
    }

    private Map<String, Object> consumerProperties(String groupId) {
        Map<String, Object> props =
                KafkaTestUtils.consumerProps(groupId, "false", broker);
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return props;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {

        @Bean
        FailingOnceForwarder forwarder(
                KafkaTemplate<String, String> template) {
            return new FailingOnceForwarder(template);
        }
    }

    static class FailingOnceForwarder {

        private final KafkaTemplate<String, String> template;
        final AtomicBoolean failFirst = new AtomicBoolean(true);
        final AtomicInteger attempts = new AtomicInteger();

        FailingOnceForwarder(
                KafkaTemplate<String, String> template) {
            this.template = template;
        }

        @KafkaListener(
            topics = INPUT,
            groupId = GROUP
        )
        public void handle(ConsumerRecord<String, String> input)
                throws Exception {

            attempts.incrementAndGet();

            // Wait for broker ack so failure injection truly sits
            // AFTER a successful send but BEFORE commit.
            template.send(
                    OUTPUT,
                    input.key(),
                    "processed:" + input.value())
                    .get(10, TimeUnit.SECONDS);

            if (failFirst.compareAndSet(true, false)) {
                throw new IllegalStateException(
                        "Injected failure before transaction commit");
            }
        }
    }
}
```

**Meaning of each milestone in the test:**

1. `@SpringBootTest` initializes real Kafka auto-configuration and the listener container, without mocking `KafkaTemplate` or `JobRepository`.
2. `@EmbeddedKafka` runs the test Kafka broker and maps bootstrap servers into Spring Boot.
3. `transaction-id-prefix` enables Kafka producer transactions; the listener container is configured with the Boot-created transaction manager.
4. `FailingOnceForwarder` sends output and **waits for the broker send ack** before intentionally throwing.
5. The exception leaves the listener, causing the first transaction to **roll back**; after-rollback behavior allows redelivering the input.
6. The second attempt completes; output and consumed offset are committed.
7. An independent observer using `read_committed` cannot see output from the aborted transaction.
8. Querying the committed offset of the **exact processing consumer group**; with a fresh topic and one record at partition 0 offset 0, the expected committed offset is **1**, i.e., the next position.

In test suites running multiple tests in parallel, create **a separate topic, consumer group, and transaction ID prefix per test context** so state is never shared. The example above intentionally has **one test case and an isolated broker**, giving the input offset 0. If a project uses a shared broker or pre-existing data, **do not hard-code offset 1**; capture the input offset returned by the producer and assert `committed == input.offset() + 1` on the matching partition.

### 6.3. Why assert the offset as well?

Suppose a test only asserts that the output consumer received one record. A misconfiguration could let the output commit succeed while the input offset **remained uncommitted**. After a consumer restart, it would re-read the input and could produce a second output. Observing "one output record at time T" does not prove both offset and output went through the same transaction.

Hence, a reliable test should observe **both sides**:

```text
Given: INPUT offset 0, group eos-it-workers

Failure 1:
  listener attempts >= 1
  Kafka transaction ABORT
  no committed output from attempt 1
  group offset has not advanced to 1 from attempt 1

Success 2:
  listener attempts >= 2
  Kafka transaction COMMIT
  read_committed output count == 1
  group committed offset == 1
```

The test above inspects the group offset **after the successful attempt**. To directly prove the state after rollback and before retry, add a controlled synchronization point (such as a test-only latch or pausing the listener after failure) and query the offset at the intermediate point. Do not use arbitrary `Thread.sleep` calls to guess timing: synchronization conditions should reflect the exact rolled-back transaction boundary.

## 7. Transaction states: `read_committed` vs. `read_uncommitted`

A producer output may already have been appended to the partition log by the broker while the transaction ultimately **aborts**. A `read_uncommitted` consumer can read that record; a `read_committed` consumer **does not return** aborted records.

```text
Physical output topic:
  offset 0  -> record of T1  [ABORTED]
  offset 1  -> control marker T1
  offset 2  -> record of T2  [COMMITTED]
  offset 3  -> control marker T2

read_committed consumer:
  sees only record of T2

read_uncommitted consumer:
  can see records of T1 and T2
```

The offsets above are **illustrative only**; actual Kafka control batches and offset generation depend on the broker and transactions. Never assume "two business input/output events" equal "two consecutive offsets" when the log contains transaction markers or aborted records.

**Common false-negative test bug:** if the observer uses the default `read_uncommitted`, it may report duplicate outputs and lead the team to conclude EOS is broken, even though downstream production systems using `read_committed` see only committed outputs.

**Common false-positive test bug:** if the observer reads only from the latest offset (`auto.offset.reset=latest`) or polls too early, it may miss both aborted and committed outputs; configure consumer topic/offset explicitly, assert the exact expected record, and confirm no extra committed records remain.

Creating two observers with different isolation levels is a helpful educational check, but the authoritative Kafka EOS assertion must rely on **`read_committed`**.

## 8. Different fault-injection test scenarios

Section 6 focused on the hardest window: **output already sent inside the transaction, before commit occurs**. A complete integration test suite should cover this matrix:

| Failure point | Expected Kafka transaction/offset | Key assertion |
| --- | --- | --- |
| Before listener begins processing | No output yet; offset unchanged | After recovery, input is still processed |
| After business logic, before `KafkaTemplate.send` | Aborts, no new output, offset not committed | Input replays and yields one committed output |
| **After broker acks output, before commit** | **T1 output aborted, offset not committed** | `read_committed` sees one T2 output after replay |
| During commit, commit outcome uncertain | Must verify Kafka transaction outcome via consumer/offset, never guess | No duplicate business output on recovery |
| After Kafka commit, before logger/HTTP caller receives ack | Output and offset already committed | Restart/rebalance does not reprocess from old offset |
| Rebalance mid-processing | Transaction/offset tied to valid group generation | Does not commit stale offsets; no duplicate outputs |
| Producer fenced | Transaction cannot be committed by old producer | Replacement instance operates safely |
| Consumer process killed | In-flight transaction aborts/times out per broker | Next group member replays input and commits one result |
| Chronic poison pill | Multiple rollbacks, policy ultimately decides recover/DLT/fail | Never silently commits offset and loses the message |
| Two distinct inputs share `businessId` | Kafka can commit two corresponding outputs | Business dedup must be tested separately |
| Writer updates database then Kafka rolls back | DB side effect may have committed | Outbox/inbox/idempotency keeps data safe |

For each case, explicitly document **which transaction is expected to commit**, **which offset must advance**, **which topics to observe**, **how many times the listener may run**, and **the business outcome**. Never write a blanket assertion "listener invoked once" across all failure cases: it contradicts transactional consumption design.

## 9. Testing real crashes/restarts instead of just throwing exceptions

Throwing an exception from the listener tests rollback, yet does not fully simulate **a JVM being killed mid-transaction**. To test real restarts:

1. Run the consumer application as a **separate process/container** with a transactional producer and group `eos-test-group`.
2. Produce an input record with a known ID/offset.
3. Drive the application to the point **after producer send ack but before transaction commit**. Use a barrier/latch or test-only hook to pause at that exact point.
4. Forcibly kill the process/container at that moment; do not use graceful shutdown when simulating a crash.
5. Start a new application instance with the **same consumer group**, a **distinct transaction ID prefix for concurrent instances**, and the same broker/repository config.
6. Wait for the broker to detect/resolve the old transaction and the consumer group to reassign partitions.
7. Query output with `read_committed` and inspect the group's committed offset.
8. Assert **one committed result** and that the offset advanced past the input; reject duplicate outputs.

**Do not confuse "killed the process" with "broker immediately aborted the transaction in the same millisecond."** A Kafka transaction can remain open until timeout/fencing/recovery; a `read_committed` consumer may be held at the last stable offset until the broker resolves the transaction. Tests must use suitable timeouts and observe state instead of concluding "no record exists" while the old transaction is still unresolved.

To precisely control crash timing, use Testcontainers, a test-only harness with a latch, or a fault-injection hook. **Never leave crash/fault-injection endpoints in production.**

## 10. Testing producer fencing and transactional IDs

Transactional Kafka producers use `transactional.id` to bind transaction sessions to the broker. If a newer producer uses the same transactional ID, the old producer can be **fenced**: it loses authority to commit transactions with the stale epoch. This is a key defense against zombie producers.

In Spring Kafka 3.x, `DefaultKafkaProducerFactory` creates transactional producers using `transactionIdPrefix + suffix`. Starting in Spring Kafka 3.2, suffix management and caching exist; configuring cache limits too low for concurrency can trigger `NoProducerAvailableException`.

Scenarios to test:

- Two **concurrently running instances** intentionally sharing the **same transaction ID prefix**: observe fencing risks, then fix to unique prefixes.
- An old consumer paused for a long time and replaced/rebalanced: must not commit stale offsets with expired consumer group metadata.
- Transaction timeout or producer idle too long: ensure errors are observed and the flow recovers per runbook.
- Increasing listener concurrency from 1 to N: verify the producer pool/cache and transaction prefix support concurrent transactions.

**Never share a single fixed transactional.id across all partitions and all pods.** Likewise, do not spin up multiple producers with the same ID assuming Kafka will "load balance" them; fencing will cause continuous failures.

Basic EOS tests verify atomicity; fencing tests verify **behavior when ownership changes**, an issue that shows up clearly in production clusters.

## 11. Batch listeners, record listeners, and commit boundaries

Spring Kafka provides record listeners and batch listeners. With transactions, the container sends processed offsets into the transaction before commit; the transaction scope can cover **one record** or **one batch of records**, depending on listener/container type.

For the **record listener** in the example:

```text
Input record R1 -> Kafka transaction T1
Input record R2 -> Kafka transaction T2
...
```

For a **batch listener**, one transaction can encompass the entire batch processed by the listener:

```text
Poll: R1, R2, R3 -> listener processes batch
                        |
                   Kafka transaction
                        |
             +----------+-----------+
             |                      |
        all succeed           R2 throws
             |                      |
          COMMIT                  ABORT
             |                      |
       offsets progress       batch may replay
```

If a batch listener already sent output for R1 and then failed on R2 before commit, the batch transaction's results can be aborted **together**, not just R2's output. Asserting "only R2 is re-read" is invalid unless a dedicated framework handling/seek mechanism is explicitly configured.

For batch listeners and poison pills, test partial processing scenarios thoroughly; a record-listener test does not prove batch-listener semantics.

### `AckMode` and manual ack

In non-transactional containers, `AckMode.RECORD` and `AckMode.BATCH` determine how consumer offsets commit. In transactional containers, offsets are sent into the Kafka transaction with semantics matching the record/batch listener. **Do not use manual consumer commits outside the transaction** to "speed up" offsets; doing so can break EOS boundaries.

## 12. Retries, after-rollback, and Dead Letter Topics

A record can fail permanently, such as an invalid payload. If every delivery throws, the transaction rolls back and the record may replay repeatedly. Spring Kafka offers after-rollback/recoverer mechanisms and DLTs to keep a poison pill from stalling a partition indefinitely.

Distinguish these outcomes:

| Outcome | Primary Kafka output topic | Input offset | DLT |
| --- | --- | --- | --- |
| Processing succeeds | Output committed | Committed in same transaction | Not needed |
| Error, rollback to retry | Output in transaction aborted | Offset for failed attempt not committed | Not routed yet |
| Retries exhausted, policy routes to DLT | No successful business output | Committed/marked recovered per transaction policy | One failed record written to DLT when recoverer succeeds |
| Recoverer/DLT publish fails | Must not silently mark input complete | Must fail/retry per policy | DLT has not received the record |

Spring Kafka provides `DefaultAfterRollbackProcessor` and `DeadLetterPublishingRecoverer`. With transactional listeners, inspect the exact post-rollback configuration, when the DLT publish happens, and how the **recovered offset commits**. A recovery setup may use a transactional KafkaTemplate and `commitRecovered` on the after-rollback processor, but it must be wired per API/version and verified with real tests.

**Never treat DLT existence as automatic proof of exactly-once.** Tests must check:

1. The bad record went through the retry count specified by policy.
2. Primary output contains **no** wrong result or leaked aborted result.
3. The DLT contains the failed record with enough original correlation/topic/partition/offset metadata for investigation.
4. Input offset is handled intentionally per recovery policy.
5. If DLT send fails, the record is not "lost" because a handler swallowed the exception.

Another trap: a listener catches `Exception`, merely logs, and **returns normally**. The container can treat processing as successful and commit the transaction/offset even though no valid output was produced. When rollback is desired, exceptions must reach the error handler/transaction manager per contract; do not swallow errors and expect Kafka to replay anyway.

## 13. Kafka EOS does not automatically guarantee exactly-once with databases

A very common design mistake is enabling Kafka transactions and assuming a database automatically shares the same transaction.

Example:

```text
@KafkaListener
     |
     +--> UPDATE orders SET processed=true ...  (DB commit)
     |
     +--> KafkaTemplate.send("orders.out", ...)
     |
     +--> Kafka transaction ABORT
```

Even though the Kafka output aborts and the input replays, **the database may have already committed** the change. If the next attempt invokes a non-idempotent side effect (charging money, incrementing a counter, sending email), business logic repeats.

| Resource | Covered by default by Kafka transaction? |
| --- | --- |
| Output records sent through a transaction-participating producer | **Yes** |
| Consumer offsets added to the same transaction by the container | **Yes** |
| SQL tables via a separate transaction manager | **Not automatically** |
| REST APIs, email, payment gateways | **No** |
| Files on object storage | **No** |
| Another Kafka producer not participating in the transaction | **No** |

Spring Kafka can synchronize Kafka transactions with another transaction manager at the application level, yet **transaction synchronization does not turn DB and Kafka into a single atomic distributed ACID transaction**. One transaction can commit first while the other fails. Therefore, test the crash window between commits.

### Common strategies

- **Idempotent consumer:** process inputs keyed by `eventId`/`businessId` in the database with a unique constraint so replays never duplicate side effects.
- **Inbox/dedup table:** persist the processed message ID and business update **in the same DB transaction**.
- **Transactional outbox:** update domain data and insert an outbox row in **one DB transaction**, then a separate publisher emits outbox events to Kafka. Because the publisher can retry, downstream still needs idempotency.
- **Saga/compensation:** coordinate distributed business steps with explicit compensating actions.
- **Idempotency key at the target system:** when calling payment APIs or external services, the target system recognizes repeated requests and avoids duplicating results.

**Tests for DB + Kafka must not assert only a single Kafka output record.** Also verify actual row counts/business values in the database, unique keys, outbox status, and replay outcomes.

Example invariant when a message is delivered twice:

```text
eventId = payment-event-42

Kafka input delivered twice
Listener invoked twice (or more)
DB payment effects for eventId = exactly one
Published business outcome per eventId = exactly one
```

This invariant comes from **idempotency design**, not merely from enabling Kafka transactions.

## 14. Unit testing transactions vs. broker tests: not interchangeable

A unit test can be helpful:

```java
@Test
void transformsOrderValue() {
    assertEquals(
            "processed:paid",
            OrderTransformer.transform("paid"));
}
```

Or using Mockito to confirm the listener calls `KafkaTemplate` with the right key/value. Those tests verify **Java logic or interactions** without running a Kafka broker, and therefore cannot prove:

- The producer used a transactional ID.
- The listener container actually opened a transaction.
- `sendOffsetsToTransaction` was called properly with group metadata.
- The broker committed/aborted properly.
- `read_committed` consumers do not see aborted records.
- Producers get fenced under ownership changes.
- Inputs replay after rollback at real Kafka offsets.
- Rebalances/transaction timeouts do not lose data.

So layer your tests:

| Test type | Purpose | Cannot prove |
| --- | --- | --- |
| Transformer/service unit test | Transformation logic, validation, idempotency keys | Broker Kafka transactions |
| `@EmbeddedKafka` integration test | Outputs, offsets, abort/commit with an integrated broker | Every property of a production cluster |
| Testcontainers Kafka | Containerized broker simulating process/network closer to production | Cannot replace full multi-broker chaos testing |
| DB + Kafka integration test | Consistency and idempotency across two resources | Every failure mode of a distributed cluster |
| Chaos/failure-injection test | Crashes, rebalances, timeouts, partitions, producer fencing | Does not replace business correctness tests |

## 15. When to use Testcontainers instead of `@EmbeddedKafka`

`@EmbeddedKafka` works well for fast dev loops and CI when verifying real Kafka transactions inside a Spring context. However, when testing **`transactional.id` fencing across restarts**, network faults, real broker versions, or multi-container deployments, Testcontainers gives process and environment control closer to production.

Deployment skeleton:

```text
@Testcontainers
  |
  +-- KafkaContainer (broker)
  +-- PostgreSQLContainer (when testing DB side effects)
  |
  +-- @DynamicPropertySource
        spring.kafka.bootstrap-servers = kafka.getBootstrapServers()
  |
  +-- Spring Boot app/context or app in a separate container
        |
        +-- transactional @KafkaListener
        +-- transactional KafkaTemplate
  |
  +-- Test producer sends input
  +-- read_committed consumer reads output
  +-- Query consumer group committed offset
```

Use the **Testcontainers module/API compatible with your project version** (Kafka container packages differ across Testcontainers releases). For JVM-kill tests, run the app in a separate test process/container; `@SpringBootTest` running inside the same JUnit JVM cannot kill its whole process while keeping the test runner alive to assert.

For a **single-broker** Kafka container, internal transaction topics must have replication/min ISR settings that allow transactions to run. In multi-broker production clusters, these values must follow real durability policies rather than single-node test defaults.

### A note on CI stability

An EOS test easily turns flaky when:

- The test suite reuses the same topics/groups from prior runs.
- Producer transactional IDs are shared with tests running in parallel.
- Using `Thread.sleep(1000)` and asserting a record is absent while the transaction has not resolved.
- A test consumer starts at `latest` after the output already committed.
- Not waiting for the producer send ack before injecting a failure.
- The broker lacks internal transaction topic config so `initTransactions` times out.
- The test context is cached while a bean's `AtomicBoolean failFirst` is not reset between tests.
- The test counts messages from a single poll rather than waiting for a stable outcome.

Use **a dedicated topic/group/prefix per scenario**, adequate timeouts for Kafka transactions, and event/condition-based synchronization. Key expected data by unique IDs so records from other tests cannot skew results.

## 16. Observing and checking committed offsets properly

For consumer groups, Kafka's committed offset is the **next position to consume**, not the offset of the record just processed. If an input on partition 2 at offset 42 is processed and committed successfully, the group offset will normally be **43** on partition 2.

Check the **exact group ID and TopicPartition**:

```java
TopicPartition tp = new TopicPartition("orders.in", 2);

try (Consumer<String, String> inspector =
         consumerFactory.createConsumer()) {

    var committed = inspector.committed(
            Set.of(tp), Duration.ofSeconds(10));

    assertNotNull(committed.get(tp));
    assertEquals(43L, committed.get(tp).offset());
}
```

This code is an excerpt from a test and assumes `consumerFactory` is already configured and the input record truly had offset 42. In the section 6 test, we used a fresh topic, partition 0, and first record at offset 0, so the expected value is 1.

Kafka transaction control batches and aborted records can make the **log end offset** differ from the count of observed business messages. A `read_committed` consumer can observe unexpected lag while an open transaction exists. Never substitute "how much log end offset grew" for counting committed business outputs.

## 17. Metrics and logs needed for testing/reliability

When investigating EOS failures, log or observe:

| Field or metric | Why it is needed |
| --- | --- |
| `eventId`/`businessKey` | Links a business operation across replays |
| `topic`, `partition`, `offset` | Identifies the actual Kafka input |
| `consumerGroupId` | Identifies where consumed offsets commit |
| Controlled `transactional.id` / instance ID | Investigates producer fencing and transaction identity |
| `attempt` / delivery attempt | Shows whether the input was reprocessed |
| `transaction begin/commit/abort` | Distinguishes sent outputs from committed outputs |
| `output topic/key` | Identifies the Kafka result |
| `ProducerFencedException`, timeout, commit error | Classifies transaction infrastructure errors |
| `DLT topic` and original offset | Investigates recovered poison pills |

Do not log full message payloads, secrets, customer PII, or payment data in traces. For transaction IDs, log values only per operational policy to avoid leaking sensitive environment metadata into public logs.

When a listener reprocesses the same record, **do not immediately conclude EOS is broken**. Inspect outputs visible to `read_committed`, committed offsets, and transaction outcomes. Conversely, if a business side effect outside Kafka happens twice, that is an idempotency/end-to-end consistency bug even if Kafka EOS itself worked properly.

## 18. Troubleshooting common test failures

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| `TimeoutException` opening transaction on Embedded Kafka | Single-node broker missing internal transaction topic config | Check `transaction.state.log.replication.factor=1` and `min.isr=1` for test env |
| Test sees two outputs after one rollback | Observer uses `read_uncommitted`, or output was sent outside transaction | Read with `read_committed`; check transaction manager and producer |
| Sees no output at all | Consumer started at `latest`, transaction not committed yet, listener not running | Check bootstrap, group, offset start, listener startup |
| Listener invoked twice | Normal rollback/replay | Assert only **one committed output**, not single invocation |
| Output appears once, but reprocesses on restart | Offset did not commit with transaction | Check container transaction, group ID, and committed offset |
| Transaction commits, but output is unexpected | `send()` outside transaction or swallowed exception | Inspect templates/producers and exception handling |
| `ProducerFencedException` | Shared transaction ID across instances, stale producer, or epoch mismatch | Unique prefix per instance, check redeploy/rebalance |
| `NoProducerAvailableException` | Transactional producer pool/cache too small for concurrency | Tune suffix cache, concurrency, and retry/backoff |
| Poison pill stalls partition forever | Missing proper recoverer/after-rollback policy | Test retry exhaustion, DLT, and recovered offsets |
| DLT has record, but offset still does not advance | DLT publishing and offset recovery misaligned | Inspect `DefaultAfterRollbackProcessor` and transactional recoverer |
| DB writes twice while Kafka outputs once | Kafka transaction does not cover DB | Inbox/outbox/idempotency and DB side-effect tests |
| Test passes on dev laptop, fails in CI | Shared topics/groups/prefixes, timing, or broker version differences | Isolate tests, synchronize transaction milestones, fix compatibility |
| Test using mocked KafkaTemplate reports EOS pass | No real broker or offset transaction | Add broker-backed integration tests |
| Consumer lag stays non-zero despite no new outputs | Transaction markers, open transactions, lag semantics | Inspect committed offsets/LSO instead of relying on lag alone |
| `@KafkaListener` catches exception and returns | Container may commit despite business failure | Propagate errors to trigger transaction rollback/error policy |
| Test kills JVM then cannot read result immediately | Broker waiting on timeout/transaction resolution | Wait conditionally with reasonable timeouts |
| Multi-partition setup asserts a single shared offset | Offsets are **per-partition** values | Track keys per TopicPartition and compare matching input offsets |

## 19. Acceptance criteria for an exactly-once flow

Before considering a Kafka EOS implementation reliable, tests must prove at least these requirements:

1. **Configuration:** transactional producer and listener container transaction manager are genuinely enabled; consumer auto-commit is off.
2. **Happy path:** a single input produces the right output, and the offset commits on the right partition/group.
3. **Rollback window:** intentional failure after broker output ack but before transaction commit; aborted output is invisible to `read_committed`.
4. **Replay:** input is redelivered after rollback, and the listener actually runs again.
5. **Committed output:** after recovery, only one committed output exists for the scenario's input.
6. **Committed offset:** group advances past the processed input; restarting the same group does not replay from the old offset.
7. **Isolation:** test observer uses `read_committed`, with isolated topics/groups/transaction ID prefixes.
8. **Failure policy:** poison pills, retry exhaustion, and DLTs are handled without swallowing or losing messages.
9. **Concurrency:** transaction ID prefixes and producer pools function when multiple listeners/pods process concurrently.
10. **External effects:** if databases/APIs are involved, test side effects/idempotency separately; never claim "end-to-end exactly once" from Kafka output alone.
11. **Observability:** enough topic/partition/offset/event ID details exist to explain any replay.
12. **Recovery:** crashes, rebalances, or broker timeouts do not cause duplicate committed Kafka results or out-of-policy input loss.

These criteria are a **test design framework**, not a built-in `@ExactlyOnceTest` annotation in Spring Kafka. Adapt them to your project's actual record listeners, batch listeners, DLT policies, and output types.

## 20. Extended hands-on exercises

**Exercise 1 — Happy path and offset.** Disable fault injection, send one record, assert one output and that the group offset advances past the record. Compare `read_committed` and `read_uncommitted` when only a successful transaction exists.

**Exercise 2 — Abort and replay.** Enable fault injection after output send ack as shown in the lesson. Assert the listener retries and no duplicate output appears on a `read_committed` consumer. Add a latch to pause after rollback, inspect the unadvanced offset, then allow the retry.

**Exercise 3 — Multiple records.** Send 10 input keys on one partition; intentionally fail on the 5th record, ensuring outputs and committed offsets reflect every successful transaction accurately. Then expand to two partitions and verify offsets per partition.

**Exercise 4 — Fencing.** Run two app instances with the same transaction prefix to observe fencing errors in a test environment, then configure unique prefixes and confirm both process their assigned partitions cleanly.

**Exercise 5 — Poison pill/DLT.** Send an always-failing record, configure retries/after-rollback recoverer, assert the record reaches the DLT per policy with enough original offset info to investigate, and confirm downstream never receives bad output.

**Exercise 6 — Database side effects.** Increment a database counter inside the listener and intentionally abort the Kafka transaction. Observe the counter incrementing again when the input replays. Then add an inbox table with unique `eventId`, write domain state and inbox row in one DB transaction, and assert only one business effect occurs.

**Exercise 7 — Kill and restart.** Use Testcontainers to run a separate consumer app, kill it right between output send and commit, and restart with the same group. Assert a single committed output and no lost offset; record how long the broker takes to resolve the old transaction.

**Exercise 8 — Test infrastructure isolation.** Run the test suite in parallel with separate topics/groups/prefixes; verify zero inter-test interference or unintended producer fencing.

## 21. Official references

- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka Reference — Handling Exceptions / After-Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Testing Applications, Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka Documentation — Transactions and Semantics](https://kafka.apache.org/documentation/)
- [Spring Kafka Reference — Transactional Outbox and transaction synchronization considerations](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)

**Conclusion:** A reliable **exactly once flow** test does not assert "the listener was invoked only once," but rather that **Kafka outputs and consumed offsets commit together or roll back together**. Intentionally inject failures **after the output is acknowledged by the broker but before the transaction commits**, prove the listener can receive the input again, then use a `read_committed` consumer to verify only **one committed output** exists and query the **committed offset** of the right consumer group. Add crashes, fencing, DLTs, and idempotency for external systems outside Kafka so reliability claims match real boundaries instead of mistaking Kafka EOS for end-to-end exactly-once business processing across the entire architecture.
