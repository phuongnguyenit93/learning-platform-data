# Testing Transaction Rollbacks in Spring Kafka

## 1. Goal: what to prove when a transaction fails

In an event-driven system, claiming "transaction rollback succeeded" is credible only when we prove **observable consequences**. A Java call throwing an exception or a log line saying "rollback" is not enough to conclude data is truly safe.

Suppose the application consumes events from topic `orders.in`, processes them, and publishes results to `orders.out`:

```text
orders.in
    |
    v
@KafkaListener
    |
    +-- validate/transform event
    |
    +-- KafkaTemplate.send(orders.out)
    |
    +-- succeed or throw exception
```

With a properly configured **Kafka transaction**, if the listener throws an error after sending output but before finishing the attempt, the system expects:

1. The active Kafka transaction is **aborted**.
2. Records sent to `orders.out` inside the failed transaction are **not visible** to consumers with `isolation.level=read_committed`.
3. The input record's offset is **not committed as a successful processing attempt** in that transaction.
4. The container can seek and reprocess the record according to the after-rollback/recovery policy.
5. When the retry attempt succeeds, the output is committed and the input offset is committed in the same successful Kafka transaction.

This verifies the **consume → process → produce** model within Kafka's boundary. It **does not automatically guarantee exactly-once** for databases, HTTP APIs, emails, or other side effects outside Kafka.

In the context of **Spring Kafka Reliability Operations → Reliability Testing**, this lesson walks through concepts, configuration, JUnit examples with an embedded broker, failure points, verifying offsets/outputs, and pitfalls that cause false-green tests.

## 2. Which rollback is being tested?

The word "transaction" in a Spring application can refer to several different mechanisms. Before writing tests, explicitly state the **transaction manager** and the protected resources.

| Transaction | Managed resources | What rollback can do | What it does not do automatically |
| --- | --- | --- | --- |
| Kafka producer transaction | Records sent by a transactional producer | Aborts uncommitted records, making them invisible to `read_committed` | Does not undo HTTP/DB side effects |
| Kafka consumer-initiated transaction | Kafka output + group offsets sent into the transaction | Atomically commits or aborts output and offsets inside Kafka | Does not guarantee business logic runs only once |
| JDBC transaction | DB changes participating in the same transaction | Rolls back uncommitted insert/update/delete statements | Does not abort an independent Kafka producer |
| External service operation | Depends on API contract | May have compensating actions or idempotency | Does not automatically join a Kafka transaction |
| Spring `@Transactional` | Chosen transaction manager | Follows manager/propagation policy | Does not mean every system shares one ACID transaction |

Three typical test scenarios:

- **Producer-only:** verify that a transactional `KafkaTemplate` sends two records and then fails; both must be aborted.
- **Consumer + producer:** listener reads an event, sends output, and then fails; output is aborted, offset is not committed, and the record is reprocessed.
- **Kafka + database:** listener writes to a DB and sends to Kafka; test failures at each boundary, since the two resources do not automatically share a global atomic commit.

This lesson uses the second scenario as the main case; producer-only is an easy-to-isolate foundation for understanding the principles.

## 3. Why is isolation.level=read_committed required?

Kafka can retain records on the log that were sent in a transaction and later **aborted**. A consumer with `isolation.level=read_uncommitted` can observe records from aborted transactions. Meanwhile, a consumer with `read_committed` returns only committed records or non-transactional records.

```text
Kafka log of orders.out

Offset 10: BEGIN transaction T1
Offset 11: output A of T1
Offset 12: ABORT T1
Offset 13: BEGIN transaction T2
Offset 14: output B of T2
Offset 15: COMMIT T2

read_uncommitted: may see A and B
read_committed:   sees only B
```

The diagram above is conceptual, not the physical log format or how control records appear in every tool. Key point: **rollback tests must use a `read_committed` consumer to verify that business output was not published**.

If a test uses `read_uncommitted` and asserts "no record may exist in the Kafka log," it can fail even when transaction abort works properly. Conversely, if it only asserts that a Java callback threw an exception without reading output with the right isolation, the test has not proven the transactional effect.

### Does the producer need real transactions?

Yes. The Kafka producer must have a valid `transactional.id`, configured in Spring Kafka via a transaction-capable `ProducerFactory` or Boot property `spring.kafka.producer.transaction-id-prefix`. Setting only `enable.idempotence=true` does not turn multiple sends and an offset commit into a consume-process-produce transaction.

An idempotent producer helps reduce duplicates from producer retries under certain conditions; Kafka transactions provide the **commit/abort** mechanism for writes and offsets included in the transaction.

## 4. How does a transactional listener work?

When a Spring Kafka listener container is configured with `KafkaTransactionManager`, the container can start a Kafka transaction before invoking the listener. The listener sends records using a `KafkaTemplate` backed by **the same transaction-capable producer factory**; upon successful processing, the container sends offsets into the transaction and commits.

```text
KafkaListenerContainer
        |
        v
begin Kafka transaction T
        |
        v
poll record from orders.in
        |
        v
listener(record)
        |
        +-- template.send("orders.out", result)
        |
        +-- success?
              |
              +-- YES: send consumer offsets to T
              |        commit T
              |
              +-- NO:  abort T
                       invoke after-rollback recovery
                       seek/retry/redelivery as configured
```

Several details:

- A Kafka consumer **does not become a transactional producer by itself**. A Kafka transaction is created by the producer and uses the mechanism for sending consumer group offsets into the transaction.
- `enable.auto.commit=false` is an essential requirement; never let the consumer auto-commit offsets independently while the container manages transactions.
- `isolation.level=read_committed` should be configured on both the application consumer and the output verification consumer when only committed data should be processed.
- The container must actually know about `KafkaTransactionManager`, not just have `@Transactional` on an arbitrary method.
- Failures must **propagate out of the listener** so the container recognizes that the transaction failed. Catching the exception and returning normally can cause the container to commit outputs/offsets as if it succeeded.

**Guarantee scope:** Kafka can guarantee output records and input offsets within the same Kafka transaction. Java method execution, DB reads, or API calls from the listener may execute multiple times across rollback and redelivery. Processing logic and side effects must tolerate re-invocation.

## 5. Setting up a test project with Spring Boot 3 and Spring Kafka 3

The following examples use **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**, JUnit 5, and `spring-kafka-test`. These are illustrative versions and APIs; Spring Kafka 4 or other Boot versions may change methods/packages, so use your project's consistent dependency set.

### 5.1. Maven dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Keep `spring-kafka` and `spring-kafka-test` compatible through Spring Boot dependency management; do not randomly mix Kafka client and broker versions.

### 5.2. application.yml for the consumer-initiated transaction example

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: orders-tx-
      acks: all
    consumer:
      group-id: orders-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      isolation-level: read_committed
      auto-offset-reset: earliest

app:
  kafka:
    input-topic: orders.in
    output-topic: orders.out
```

Setting `spring.kafka.producer.transaction-id-prefix` causes Spring Boot, under matching auto-configuration, to create a `KafkaTransactionManager` and wire it into the Boot-managed listener container factory. Do not just look at YAML and conclude transactions work: verify the `KafkaTransactionManager` bean, producer factory, and listener factory use the right configuration.

The transactional ID prefix must **not collide across concurrently running instances**. The `orders-tx-` example above is only suitable as a single-instance illustration. In Kubernetes or when scaling multiple pods, use a managed per-instance prefix to avoid unintended producer fencing.

**Note:** many codebases build `ConcurrentKafkaListenerContainerFactory` or `ProducerFactory` manually. When doing so, auto-configuration may no longer bind the transaction manager to the factory you use; attach the transaction manager explicitly using the API of your project's Spring Kafka version.

### 5.3. Why disable auto offset commit?

If the consumer auto-commits offsets, an exception after an offset commit would mark the record processed even though the Kafka output was aborted. A prerequisite for consume-process-produce transactions is that **offsets belong to the container-coordinated transaction**, not independent consumer progress commits.

## 6. Listener that intentionally fails after sending output

The goal is a controllable failure test: **the first attempt sends output then throws an exception; the second attempt sends output and succeeds**.

### 6.1. Illustrative listener

```java
package com.example.kafka;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CountDownLatch;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class FailOnceOrderListener {

    private final KafkaTemplate<String, String> template;
    private final AtomicInteger attempts = new AtomicInteger();
    private final CountDownLatch successfulAttempt = new CountDownLatch(1);

    public FailOnceOrderListener(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @KafkaListener(
            id = "orders-rollback-listener",
            topics = "orders.in")
    public void handle(String payload) throws Exception {
        int attempt = attempts.incrementAndGet();

        // Send inside the transaction opened by the listener container.
        template.send("orders.out", "order-1", payload.toUpperCase())
                .get(10, TimeUnit.SECONDS);

        if (attempt == 1) {
            throw new IllegalStateException(
                    "Simulated failure after output send");
        }

        // Latch tells the test the retry reached the end of the listener;
        // transaction commit happens AFTER the method returns.
        successfulAttempt.countDown();
    }

    public int attempts() {
        return attempts.get();
    }

    public boolean awaitSuccessfulAttempt(long timeout, TimeUnit unit)
            throws InterruptedException {
        return successfulAttempt.await(timeout, unit);
    }
}
```

**Fixture scope note:** the listener counts `attempts` in a global variable. It fits an isolated single-partition integration test sending **one event**, not per-event error handling in production. In multi-record or parallel tests, track state by key or use controlled fault injection.

Why is `template.send(...).get(...)` called before the exception? We want the broker to have received the send under transaction T1 before the application intentionally throws. This makes the test far more valuable than throwing **before any record is sent**.

Calling `get(...)` waits for the send result, but **does not commit the transaction**. If the listener throws an exception, the container can still abort T1. That T1's event was transiently written by Kafka does not mean a `read_committed` consumer will see it.

### 6.2. Do not use executeInTransaction inside a listener transaction

When the container has already opened a transaction, calling:

```java
template.executeInTransaction(ops -> {
    ops.send("orders.out", payload);
    return null;
});
```

is not a safe way to "join the active transaction." `executeInTransaction(...)` has semantics for creating a template-local transaction, which can become an independent/nested transaction relative to the existing one; output could commit **before** the outer listener throws. To send output in the same transaction managed by the listener container, call `template.send(...)` directly with the same producer factory/transaction context.

This is a major testing trap: if a test only asserts that the listener throws without inspecting `read_committed` output, an independent transaction can slip past unnoticed.

## 7. Integration test with Embedded Kafka

To verify real rollbacks, you need a test Kafka broker rather than just mocking `KafkaTemplate`. `@EmbeddedKafka` from `spring-kafka-test` supplies an in-process broker during testing.

### 7.1. Minimal application class

```java
package com.example.kafka;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaReliabilityApplication {
}
```

Place the listener in a subpackage of the application. In the test, `@SpringBootTest(classes = KafkaReliabilityApplication.class)` initializes Spring Kafka and the listener bean.

### 7.2. Testing rollback and redelivery

```java
package com.example.kafka;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(
        classes = KafkaReliabilityApplication.class,
        properties = {
            "spring.kafka.producer.transaction-id-prefix=rollback-it-",
            "spring.kafka.consumer.enable-auto-commit=false",
            "spring.kafka.consumer.isolation-level=read_committed",
            "spring.kafka.consumer.auto-offset-reset=earliest",
            "spring.kafka.listener.ack-mode=record"
        })
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.in", "orders.out"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaTransactionRollbackIT {

    @Autowired
    private KafkaTemplate<String, String> template;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Autowired
    private FailOnceOrderListener listener;

    @Test
    void abortedOutputIsInvisibleAndInputIsRedelivered()
            throws Exception {

        // Application producer has transaction-id-prefix.
        // Publish input inside a committed transaction.
        template.executeInTransaction(ops -> {
            ops.send("orders.in", "order-1", "created");
            return null;
        });

        // Signal that the second attempt reached the end of the method.
        assertTrue(listener.awaitSuccessfulAttempt(
                20, TimeUnit.SECONDS));
        assertTrue(listener.attempts() >= 2);

        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "verify-" + UUID.randomUUID(),
                        "false",
                        broker);

        consumerProps.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        consumerProps.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        consumerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG,
                "read_committed");
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        try (var consumer =
                     new KafkaConsumer<String, String>(consumerProps)) {
            broker.consumeFromAnEmbeddedTopic(
                    consumer, "orders.out");

            var visible = KafkaTestUtils.getRecords(
                    consumer, Duration.ofSeconds(10));

            assertEquals(1, visible.count());
            assertEquals(
                    "CREATED",
                    visible.iterator().next().value());

            var more = KafkaTestUtils.getRecords(
                    consumer, Duration.ofMillis(500));
            assertEquals(0, more.count());
        }
    }
}
```

In this example:

1. The input event is published in an independent transaction opened and committed by the **test producer**; the listener then consumes the event.
2. On its first attempt, the listener sends `CREATED` to the output and intentionally throws.
3. The container aborts the first transaction and applies its after-rollback mechanism. With a transient failure that succeeds on the second try, the record is reprocessed.
4. On the next attempt, the listener sends `CREATED` and returns normally; the container commits the transaction.
5. The verification consumer uses `read_committed` and sees only **one** output, not the record sent by the aborted transaction.

This test uses real configuration and an integration-level broker, **not just Mockito**. Still, it assumes:

- Boot wired `KafkaTransactionManager` to the listener container factory in use.
- The broker/test environment supports transactional producers.
- No other events on the same topics or other listener instances in the same group alter the data.
- The after-rollback mechanism allows reprocessing the record rather than another recovery policy skipping it prematurely.

**Watch for real transactions:** if a custom listener factory omits the transaction manager, tests may throw "No transaction in process" when a transactional template sends outside a transaction, or behave unexpectedly. Inspect factory configuration if integration does not work as intended.

### 7.3. Why use a latch instead of Thread.sleep?

`Thread.sleep(5000)` does not prove that the listener redelivered; it merely waits for time to pass. A latch lets the test wait for a meaningful event. The latch timeout bounds the wait so the test does not hang forever on failure.

However, the latch counts down **before the Kafka transaction commits** because the listener method has not yet returned. Therefore, output assertions must still rely on a **`read_committed` consumer with a poll timeout** to confirm commit; do not infer from the latch that the transaction has committed.

### 7.4. Separating test classes or ensuring isolation

The fixture holds state in `AtomicInteger` and `CountDownLatch`. If multiple tests share the same Spring context, broker, topic, and listener bean, the "first" attempt may have already happened in an earlier test. For larger suites:

- Isolate tests into separate classes/contexts.
- Create uniquely named test topics and consumer groups where architecture allows.
- Reset test state safely or build per-test listener fixtures.
- Avoid running tests in parallel when they share topics and groups.
- Use `@DirtiesContext` deliberately when full listener/broker teardown is required between scenarios.

If Maven uses the `*IT` class suffix, configure Maven Failsafe or rename to `*Test` so the runner executes it. Do not assume `mvn test` automatically runs every `*IT.java` file by default.

## 8. Unit/integration testing producer-only rollbacks

Before testing consumer-initiated transactions, you can write a small test showing how `KafkaTemplate.executeInTransaction` behaves without a listener.

### 8.1. Rollback when callback throws an exception

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void producerTransactionAbortsOnException() {
    assertThrows(IllegalStateException.class, () ->
            template.executeInTransaction(ops -> {
                ops.send("tx.output", "A", "first");
                ops.send("tx.output", "B", "second");
                throw new IllegalStateException("force abort");
            }));
}
```

This is a test method inside a test class that already has a transactional `KafkaTemplate` and broker topic `tx.output`. If reusing the previous example's configuration, add the topic to `@EmbeddedKafka` or pick an already provisioned topic.

**Asserting the exception is not enough.** After the callback throws, open a fresh `read_committed` consumer, seek to the start of the test topic (or from a pre-test offset), poll for a bounded duration, and assert **no A or B records are seen**.

### 8.2. Normal transaction commit

```java
@Test
void committedProducerTransactionIsVisible() {
    template.executeInTransaction(ops -> {
        ops.send("tx.output", "C", "committed");
        return null;
    });
    // Use a read_committed consumer to assert record C exists.
}
```

Two contrasting tests show the difference between **abort** and **commit**. Separate topics or offset boundaries so the commit test does not accidentally read data from another scenario.

### 8.3. Why producer-only tests do not prove offset rollback

`executeInTransaction` above does not read records via `@KafkaListener` and does not send consumer offsets into the transaction. Thus it only proves **output records are committed/aborted**, and cannot prove consumer group redelivery behavior. To verify offsets, use a **listener-container transaction** test or explicitly invoke the APIs that send offsets into the transaction with the right group metadata.

## 9. Verifying offset rollback properly

A common source of false conclusions: **the consumer polled a record** does not mean its offset was committed. The Kafka consumer holds its read position in memory, whereas the group committed offset lives on the broker.

```text
Consumer position: may already be past record N after poll
Group committed offset: offset used when a new consumer joins/restarts
```

When a Kafka transaction aborts, offsets sent into that transaction are **not treated as committed**. The container may seek or cause the record to be re-read depending on version and recovery policy.

### 9.1. How to verify at the integration level

A strong test should:

1. Use a dedicated test consumer group.
2. Send a committed input event.
3. Have the listener process the first attempt and throw.
4. Verify the record is redelivered (for example `attempts >= 2` and the same input key).
5. Verify aborted output from the failed attempt is invisible under `read_committed`.
6. Allow the next attempt to succeed and read the **group committed offset** via `AdminClient.listConsumerGroupOffsets(...)` or a new consumer in the same group once settled.
7. Verify the offset advanced past that record after success; if using a new consumer in the same group, control rebalances and stop the old listener before observing to avoid races.

The listener receiving the same message twice proves **redelivery**, but alone does not prove every detail of broker offset commits: rebalances, explicit seeks, and recovery policies can also trigger replay. To confirm committed offsets, inspect the group's metadata.

### 9.2. Do not confuse consumer position with committed offset

APIs like `consumer.position(partition)` show the read position of that specific consumer instance. When verifying that a transaction committed the **consumer group's** offset, inspect the group committed offset, not just the post-poll position.

The committed offset advances to the **next offset** after the processed record. For example, once a record at offset 5 is committed as processed, the committed offset is typically 6. This is standard Kafka consumer offset semantics, not the broker "skipping" a record.

### 9.3. Testing pre/post rollback at a deterministic boundary

If you want to inspect the exact committed offset **right after a transaction aborts**, avoid using a fail-once fixture that immediately retries and succeeds because the window between attempts is too short. Use fault injection that holds the consumer in a controlled failing state, pause the listener container, or configure an appropriate backoff, then measure with AdminClient before allowing processing to continue.

Do not insert an arbitrary `Thread.sleep` and treat it as a transaction boundary; use latches/futures and coordinate test timing using mechanisms supported by the container/broker.

## 10. Testing different failure points in the transaction lifecycle

A credible rollback test checks more than one throw site.

| Failure point | Example | What to verify |
| --- | --- | --- |
| Before sending output | Validation throws immediately | No output; offset not committed as successful |
| After sending output, before listener returns | Simulated failure in the example | Transactional output aborted; record can redeliver |
| During broker send/ack | Broker temporarily disconnects | Transaction not falsely reported successful; failure observed |
| During Kafka transaction commit | Fencing, timeout, or broker error | Outcome may need reconciliation; do not blindly retry side effects |
| After DB commit but before Kafka commit | Kafka commit fails | DB may already be committed; reprocessing risks DB duplicates |
| During recover/DLT step | DLT publish fails | Do not mark record processed if recovery failed |
| Consumer rebalance on slow processing | `max.poll.interval.ms` exceeded | Must verify partition ownership and transaction lifecycle |
| Process crash | JVM killed before commit | Do not assume cleanup callbacks run; verify outcome from broker |

For testing **real broker/commit failures**, Embedded Kafka is helpful for basic scenarios but does not always fully represent a production cluster. Disconnects, broker restarts, fencing, and network partitions warrant considering **Testcontainers Kafka**, controlled fault injection, or a dedicated integration environment.

## 11. Retries/redelivery after rollback: avoiding infinite loops

A failing record can be re-read repeatedly. If the error is transient, redelivery can resolve it. If it is a poison pill (unprocessably bad payload), infinite looping stalls the partition.

Spring Kafka provides **AfterRollbackProcessor**, typically `DefaultAfterRollbackProcessor` in transactional containers, to decide how to seek/retry/recover after rollback. The design must:

- Classify retryable vs. non-retryable exceptions.
- Bound retry attempts and apply backoff.
- Once retries are exhausted, fail/stop, alert, or publish to a DLT per policy.
- Never silently commit the offset if recovery has not produced a durable, investigable state.
- Verify that records after the poison pill continue processing once policy completes.

**Distinguish three concepts:**

| Mechanism | Meaning | Risk if misunderstood |
| --- | --- | --- |
| Kafka transaction rollback | Aborts output and offsets of the failed attempt | Does not fix bad data or broken dependencies |
| Listener retry/redelivery | Re-invokes processing for the record | Can duplicate side effects outside Kafka |
| DLT/recovery | Routes unprocessable records to an investigation path | If DLT publish fails while offset commits, trace can be lost |

### 11.1. Configuring recovery in a transactional container

Conceptual Spring Kafka 3.x snippet:

```java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
var afterRollback = new DefaultAfterRollbackProcessor<>(
        recoverer,
        new FixedBackOff(1000L, 2L));

// Attach afterRollback to the Kafka listener container factory using
// the API of your Spring Kafka version.
```

This is a **policy illustration snippet**, not a complete config class. `FixedBackOff(1000L, 2L)` sets a 1-second interval and at most two retries per Spring retry/backoff API semantics. Final attempt counts should be verified by tests rather than ambiguously interpreting "2 means 2 total."

To **recover a record and commit the recovered offset inside a new Kafka transaction**, Spring Kafka provides mechanisms such as `commitRecovered` together with `KafkaTemplate` on `DefaultAfterRollbackProcessor` when configured properly. Do not copy a few lines from an example to production without checking:

- Is the recovered record sent to the DLT using a transactional producer?
- Are recovery and the offset committed in the required Kafka transaction?
- Is DLT publishing confirmed before marking the record recovered?
- After a mid-step process crash, could a DLT duplicate or record loss occur?

Choose recovery by semantics, not just the wish that "the consumer stops throwing."

### 11.2. Testing DLT separately from the rollback test

A poison-pill test can:

1. Send an invalid record.
2. Make the listener always throw the classified exception.
3. Wait until attempts exceed the configured threshold.
4. Use a `read_committed` consumer on the DLT topic to confirm the record was published.
5. Verify the input offset is handled per recovery policy, and a subsequent valid record proceeds.
6. Confirm no business output records exist from aborted attempts.

Do not reuse the `FailOnceOrderListener` fixture to infer poison-pill policy: it fails only once and then succeeds, never entering the post-retry recovery branch.

## 12. Kafka + database: non-atomic rollback across two systems

A common production flow is:

```text
orders.in -> listener
                |
                +-- UPDATE orders database
                |
                +-- KafkaTemplate.send(orders.out)
```

If the Kafka transaction aborts after the JDBC transaction committed, the DB change **does not automatically roll back**. Conversely, if the DB fails before the Kafka transaction commits and the exception propagates, the Kafka transaction can abort, though you must understand Spring's transaction ordering and application design.

### 12.1. Testing failure before DB commit

While the JDBC transaction is active and the method throws an exception, SQL changes in that transaction can roll back. Yet the Kafka container still needs to receive the exception to abort the Kafka transaction; if the exception is caught and treated as success, Kafka may commit unintended writes.

### 12.2. Testing failure after DB commit

```text
T1: Kafka container starts transaction
T2: @Transactional(JDBC) service updates DB
T3: JDBC transaction COMMITS
T4: KafkaTemplate sent output
T5: Kafka transaction COMMIT fails
T6: Listener record is redelivered
```

If the next attempt updates the DB again or sends an email again, side effects can duplicate. Spring does not provide a default two-phase distributed ACID transaction committing Kafka and JDBC as one atomic unit.

Synchronized transaction setups can narrow the window of desynchronization, yet a failure window between the two commits remains. For critical workflows, consider:

- **Idempotent database writes** keyed by event ID or business key.
- **Transactional outbox**: write business changes and an outbox row in one JDBC transaction; a publisher/CDC sends to Kafka afterward.
- **Inbox/processed-event table**: check processed event IDs to block duplicate side effects.
- Saga/compensation when coordinating multiple services is unavoidable.

### 12.3. Testing DB idempotency after a Kafka rollback

Example table:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(80) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Scenario:

1. Listener receives `eventId=EV-1` and the DB inserts `processed_event` with a unique key.
2. Kafka transaction fails after the DB commits.
3. The same event is redelivered.
4. Second-attempt logic detects `EV-1` already exists and does not duplicate DB side effects.
5. Kafka processing can still emit appropriate output and commit the offset.

**Never use `Kafka offset` as the business deduplication key** if events can be republished to new partitions/offsets. Use a durable event ID supplied by the business producer.

For outbox designs, tests must also verify events are not lost if the publisher crashes, can be re-sent, and downstream consumers are idempotent if needed.

## 13. Commit vs. rollback tests: expectation matrix

| Scenario | `read_committed` output | Input offset | Subsequent behavior |
| --- | --- | --- | --- |
| Listener sends and returns normally | Output visible after commit | Committed with transaction | Advances to next record |
| Listener throws before send | No output | Not committed as success | Redelivery/recovery |
| Listener sends then throws | Aborted output not visible | Not committed as success | Redelivery/recovery |
| Listener throws, catches, then returns | May commit | May commit | **Wrong if rollback was intended** |
| Listener sends via independent transaction then throws | Independent output may commit | Container tx may abort offset | **Risk of duplicate output** |
| Retry succeeds after rollback | Only committed output from winning attempt | Committed on winning attempt | Continues |
| Poison pill exhausts retries, moves to DLT | DLT depends on recovery transaction | Follows recover/commit policy | Can continue if recovery succeeds |
| DB commits then Kafka transaction fails | Kafka output may abort | Kafka offset uncommitted | DB side effect needs idempotency |
| JVM crashes before commit | Uncommitted output invisible to read_committed | Uncommitted by that tx | Recovered via broker/rebalance |

This matrix represents **expected contract behavior when transactions are configured properly**. Depending on crash timing and ambiguous transaction outcomes, inspect broker state or metadata rather than relying on application stack traces.

## 14. Tests must not rely solely on Mockito

Mockito is useful for unit testing logic:

```java
verify(kafkaTemplate).send("orders.out", "order-1", "CREATED");
```

But verifying that call does not prove:

- The producer started a Kafka transaction.
- The record was successfully delivered to the broker.
- The record was aborted or committed.
- A `read_committed` consumer sees it.
- The input offset committed together with the output.
- The container redelivers after rollback.

Therefore, separate two test tiers:

| Tier | Goal | Appropriate tools |
| --- | --- | --- |
| Unit | Payload transformation, error classification, business rules | JUnit/Mockito |
| Kafka integration | Producer transaction commit/abort, output visibility | `@EmbeddedKafka` + real Kafka consumer |
| Listener integration | Output rollback + redelivery + offset semantics | Transactional listener container + broker |
| DB + Kafka | Failures between two transactions and idempotency | Test DB + broker or Testcontainers |
| Reliability/chaos | Broker restarts, network partitions, fencing, process crashes | Integration environment with controlled fault injection |

Never rename a mock-based unit test to "transaction rollback test" when no real transaction is being verified.

## 15. Sources of flakiness in transaction tests

### 15.1. Shared topics/groups across tests

If multiple tests reuse `orders.in`, `orders.out`, and group `orders-processor`, old events can be consumed or cause false assertions.

Solutions:

- Isolate brokers/contexts for critical tests.
- Use dedicated test topics/groups where appropriate.
- Use unique input keys/event IDs.
- When tests read output, assert only records matching the test's event ID.
- Never delete production metadata or "reset offsets" on a real group to run tests.

### 15.2. Test reads too early

In Kafka, send callbacks, listener returns, and broker commits do not happen instantaneously at the same moment. Tests must wait on **a meaningful condition** with a timeout, then use a `read_committed` consumer to verify committed output.

Do not rely on a fixed `Thread.sleep(1000)`; on slow CI runners, transactions may take longer, causing random failures.

### 15.3. Duplicate producer transactional IDs

Two active producers with the same `transactional.id` can fence each other. In parallel test runs or scaled applications, manage prefixes so they do not collide unintentionally.

### 15.4. Broker lacks transaction capability

In a production Kafka cluster, the transaction coordinator relies on proper replication/ISR settings. Embedded test brokers are configured for test usage, whereas running a single-node Kafka yourself requires tuning internal transaction state log properties for dev. Transaction initialization failures can be broker misconfigurations, not listener bugs.

### 15.5. Deserializer fails before the listener

If a payload fails to parse during deserialization, the `@KafkaListener` method may **never be invoked**. That is a different reliability branch: use `ErrorHandlingDeserializer` and a matching recovery/poison-pill policy. Do not use deserialization errors to test "throwing after the listener sends output," because the failure point is different.

### 15.6. Wrong offset commits from auto-commit or manual ack

A test may report "record was not redelivered" because the consumer committed offsets through a mechanism outside the Kafka transaction. When testing rollbacks, verify `enable.auto.commit=false`, the container transaction manager, ack mode, and the actual error handler/recovery policy.

## 16. Fencing, timeouts, and uncertain commit outcomes

Kafka transactions have safeguards when a producer identity/epoch is superseded or a transaction times out. Examples:

- `ProducerFencedException` when an older producer is fenced.
- Transaction timeout causing the broker to abort an unfinished transaction.
- Rebalances and partition ownership changes when processing takes too long.
- Network interruption right at commit: the client cannot immediately tell whether the broker committed.

In these situations:

1. Do not treat every Kafka exception as transient and retry endlessly with the same producer.
2. For fatal/fencing errors, let the container and producer factory handle them per contract, which may require creating a new producer or restarting the container.
3. Monitor transaction duration, `max.poll.interval.ms`, session timeouts, and related broker/producer settings.
4. Use event IDs and idempotency so business results stay accurate across redeliveries or uncertain outcomes.
5. Reconcile `read_committed` outputs and committed group offsets rather than guessing from logs.

### Should fencing tests use an embedded broker?

You can build a test with two transactional producers sharing a `transactional.id` and deliberately initialize the newer producer to fence the older one. However, that is a separate test requiring tight control over producer creation timing, open transactions, and client error handling. Do not bundle it into a basic fail-once test, as it easily introduces flakiness and blurs the rollback goal.

## 17. Logging and metrics for transaction rollbacks

When investigating, logs should include these fields where permitted:

```text
consumerGroup
listenerId
topic
partition
offset
eventId
transactionOutcome: COMMITTED | ABORTED | UNKNOWN
attempt
errorCategory
traceId
deploymentInstance
```

Example:

```json
{
  "event": "kafka_record_processing_failed",
  "consumerGroup": "orders-processor",
  "topic": "orders.in",
  "partition": 0,
  "offset": 125,
  "eventId": "EV-1042",
  "errorCategory": "DEPENDENCY_TIMEOUT",
  "attempt": 1
}
```

Never log tokens, credentials, sensitive raw payloads, or full headers. Nor should you claim a transaction `ABORTED` solely because the listener threw an exception: inspect transaction/producer state and broker outcomes when precision matters.

Suggested metrics:

| Metric | Meaning |
| --- | --- |
| `kafka_listener_failed_total{listener,errorCategory}` | Processing failure count |
| `kafka_transaction_aborted_total{service}` | Tracks transaction aborts if supported by instrumentation |
| `kafka_listener_redelivery_total{listener}` | Detects rising retries/redeliveries |
| `kafka_dlt_published_total{topic,errorCategory}` | Tracks records routed to DLT |
| Consumer lag by group | Detects partitions stalled after repeated rollbacks |
| Transaction duration/p95 | Detects long-running transactions |
| Time since last committed event | Detects stalled pipelines |

These are **illustrative custom metric names**, not guaranteed default Spring Kafka or Micrometer metrics. Avoid using `eventId`, offset, or exception messages as high-cardinality labels; keep those in logs/traces.

## 18. Investigation workflow when a rollback test fails

Suppose the "aborted output is invisible" test reports two records instead of one. Walk through in order:

1. **Check the verifier:** does the output consumer use `isolation.level=read_committed`? Are there records from another test?
2. **Check the listener:** did the exception propagate, or was it caught and returned normally?
3. **Check the producer:** does `KafkaTemplate` use the transaction-capable producer factory and the container's transaction?
4. **Check the transaction manager:** does the listener factory have `KafkaTransactionManager` attached?
5. **Check nested transactions:** was `executeInTransaction(...)` called inside the listener, causing independent output commits?
6. **Check recovery:** is the after-rollback processor publishing additional output/DLT records per policy?
7. **Check test isolation:** do the broker/topic/group hold leftover data from a previous test?
8. **Check listener invocation count:** did the first attempt throw at the intended point after send?
9. **Check group offsets:** after the aborted attempt, was auto-commit or out-of-transaction acking active?
10. **Check external side effects:** did a real duplicate land in DB/HTTP, or was it merely an aborted record in the log?

If the test sees no output even though the listener succeeded, check:

- Did the second transaction actually finish committing?
- Is the verifier assigned to the right topic/partition?
- Is `auto.offset.reset` appropriate when the group has no offset yet?
- Did the consumer poll long enough; was it given the embedded broker's bootstrap servers?
- Was the producer fenced or did the transaction coordinator fail?
- Did output go to another topic due to property configuration?

## 19. Hands-on exercises

**Exercise 1 — Producer rollback.** Create a transactional `KafkaTemplate` and test topic. Inside `executeInTransaction`, send two records and throw an exception. Use a `read_committed` consumer to prove neither is visible; adjust the callback to commit and verify visibility.

**Exercise 2 — Fail-once listener.** Build a `@KafkaListener` that sends output and throws on the first delivery, then succeeds on the second. Using `@EmbeddedKafka`, assert two deliveries and only one committed output.

**Exercise 3 — Observing committed offsets.** Using a dedicated test group, pause processing after the first failure and inspect the committed offset via AdminClient. Allow the retry to succeed and inspect again; explain the difference between consumer position and committed offset.

**Exercise 4 — Poison pill and DLT.** Make the listener always throw on an invalid payload. Configure bounded after-rollback recovery with backoff. Verify the DLT receives the record per policy and the consumer processes subsequent valid records.

**Exercise 5 — Catching exceptions improperly.** Change the listener to catch the exception and return normally. Observe outputs/offsets and explain why the container can commit instead of rolling back.

**Exercise 6 — Nested transaction.** Intentionally call `KafkaTemplate.executeInTransaction` inside a transactional listener, then throw in the outer listener. Observe that the independent transaction's output can commit even though the outer offset transaction aborts. Then fix it to use `template.send` directly.

**Exercise 7 — DB side effects.** Have the listener insert into a DB and fail the Kafka transaction. Redeliver the same event and observe duplicates or unique constraint violations. Add `processed_event(event_id)` with a unique key or a transactional outbox, then verify the final result.

**Exercise 8 — Broker failure.** Using a controlled integration environment, restart the broker or drop connections while a transaction is open. Distinguish failures before send, after send, and near commit; never use sleep to infer transaction outcome.

**Exercise 9 — Group rebalancing.** Process a record longer than the poll interval threshold in a test environment and observe container behavior. Design timeouts, concurrency, and recovery to avoid infinite retries.

**Exercise 10 — Monitoring.** Add correlation logs with `topic/partition/offset/eventId`, measure listener failures, redeliveries, and DLTs. Create an alert when consumer lag rises alongside consecutive failures.

## 20. Verification summary required before declaring success

| What to prove | Method |
| --- | --- |
| Real producer uses Kafka transactions | Inspect producer factory/transaction manager and broker integration |
| Output in failed transaction is aborted | `read_committed` consumer sees no failed-attempt record |
| Successful attempt produces output | `read_committed` consumer sees committed record |
| Input is not marked processed after rollback | Redelivery of same record and/or inspect committed group offset |
| No duplicate output after retry | Assert only one committed business output per event ID |
| Poison pill does not stall forever | Test recovery/DLT and processing of subsequent record |
| DB/API side effects do not duplicate | Separate idempotency/outbox tests |
| Tests are not timing-flaky | Latches, bounded polling, isolated fixtures |
| Failures are investigable | Structured logs, metrics, and trace/correlation IDs |

**Conclusion:** Testing Spring Kafka transaction rollbacks is more than `assertThrows(...)`. A credible test needs a **real broker**, a Kafka transaction wired to the right listener container, a verifier using **`read_committed`**, and assertions covering **outputs, offsets, redelivery, and side effects**. When an error happens after `send` but before commit, that attempt's output must be aborted and the input offset must not commit as a success; the record can then be reprocessed under the after-rollback policy. For databases and external APIs outside Kafka, add idempotency/outbox or appropriate transactional mechanisms because Kafka rollback does not automatically undo those systems.

### References

- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
