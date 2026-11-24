# Simulating a Poison Pill in Spring Kafka: Retry, DLT, and Consumer Recovery

A Kafka consumer is processing events sequentially within a partition. The first two records succeed, but the third record always causes the listener to throw an exception. The consumer retries endlessly, the offset does not advance, and subsequent records are held back even though they are completely valid. This is a **poison pill** scenario—a record that the current processing pipeline cannot complete successfully when replayed in the same way.

In **Spring Kafka Reliability Operations → Operations Practice**, simulating a poison pill is more than sending a bad string into Kafka. The lab must observe **offsets before and after the failure, retry counts, per-partition processing order, how the record enters the Dead Letter Topic (DLT), and the consumer's ability to continue reading subsequent records**. At the same time, you must distinguish errors occurring **inside the listener** from errors occurring **before the listener, in the deserializer**—those two scenarios require different configurations.

This lesson uses **Spring Boot 3.x, Spring Kafka 3.x, and Java 17** as the API baseline. Sections covering `DefaultErrorHandler` and `ErrorHandlingDeserializer` follow Spring Kafka 3.x; for Spring Kafka 4.x, check the class names and APIs for your project version. The main lab simulates a **record listener without Kafka container transactions enabled**, so it uses `DefaultErrorHandler`. Near the end, a dedicated section covers **transactional/EOS consumers**, which rely on after-rollback processing.

## 1. Practice Objectives

We want to build a test following this flow:

```text
Topic: poison.lab.input       Partition 0
       |
       +-- offset 0: GOOD-1
       |
       +-- offset 1: POISON    <-- listener always throws
       |
       +-- offset 2: GOOD-2
       |
       v
Spring Kafka @KafkaListener
       |
       +-- GOOD-1 --> processed successfully
       |
       +-- POISON --> fail attempt 1
       |               wait / retry
       |               fail attempt 2
       |               wait / retry
       |               fail attempt 3
       |                    |
       |                    v
       |              DeadLetterPublishingRecoverer
       |                    |
       |                    v
       |           poison.lab.input-dlt
       |
       +-- GOOD-2 --> continues processing
```

**Passing criteria:**

1. `GOOD-1` and `GOOD-2` are processed successfully; no valid record is left behind after the poison pill.
2. `POISON` fails **three times** per `FixedBackOff(200ms, 2L)`—one initial delivery plus two retries.
3. Only **one record** corresponding to `POISON` is published to the DLT, with matching key/value and source metadata.
4. The consumer group eventually commits an offset **past `GOOD-2`** once all records are processed or recovered.
5. If DLT publishing fails, the record must not be silently treated as recovered and skipped.
6. Permanent data errors are distinguishable from transient infrastructure errors so not every exception goes to the DLT.

This lab **intentionally injects failures** and must run only in test or staging environments using dedicated topics and consumer groups. Never send a failing record to a live production topic just to test retries or alerts.

## 2. What Is a Poison Pill, and Why Isn't Every Error One?

| Scenario | Example | Does Retrying the Same Payload Help? | Usually Appropriate Approach |
| --- | --- | --- | --- |
| **Unparseable bad data** | Malformed JSON syntax, incompatible Avro/Protobuf schema | Usually no, unless code/schema changes | `ErrorHandlingDeserializer`, classification, and DLT/quarantine |
| **Parseable data, invalid business state** | Unsupported status, missing customer ID | Usually no | Clear error code, fail-fast or DLT per policy |
| **Logic bug triggered by one input** | `NullPointerException` on a rare structure | Usually not until code is fixed | DLT/quarantine with evidence, then fix and replay |
| **Temporary infrastructure error** | DB timeout, HTTP 503, broker unavailable | Possibly | Bounded retry with backoff; do not prematurely treat record as bad data |
| **System-wide misconfiguration** | Wrong database credentials, broken schema across all messages | Retrying individual records does not help | Halt/alert and fix configuration; avoid flooding DLT with the entire topic |
| **Downstream throttling** | Prolonged API rate limiting | Possibly after waiting | Backoff, circuit breaker, or appropriate orchestration |

A **poison pill** is an operational concept: a record that repeatedly stalls processing. It can be caused by bad data or a code bug, not only `JsonDeserializer` errors. Conversely, a record that fails once and succeeds on retry **is not permanently unprocessable**.

Crucially, **never swallow exceptions in a listener and return normally**. Doing so lets the container treat the record as processed and commit the offset, forfeiting retry and DLT handling even though business work failed.

## 3. Why Can One Poison Pill Stall an Entire Partition?

Kafka stores records in offset order **within each partition**. Consumers read via `poll()` and commit offsets representing the **next position** after processed records. If the record at offset 41 keeps failing without recovery, the consumer cannot simply commit offset 42 without an explicit policy decision to skip/recover that record.

```text
Partition 0:
  40 GOOD   -> processed
  41 BAD    -> listener throws
  42 GOOD   -> waiting
  43 GOOD   -> waiting

DefaultErrorHandler:
  seek/resubmit offset 41
  retry 41
  retry 41
  -> without bounds, later offsets can be delayed indefinitely
```

**This does not automatically stop the entire topic**: a topic can have multiple partitions assigned to separate consumer threads, so an error on one partition need not halt all partitions. Still, if a container has few threads and error handling occupies a thread, one poison pill can inflate lag and affect other partitions managed by that listener. Design must account for retries, concurrency, and poll intervals.

With `DefaultErrorHandler`, Spring Kafka can *seek* back to the failing offset or hold records in the container for redelivery depending on `seekAfterError`. Regardless of the internal mechanics, the goal is **never silently dropping the failing record** before the recoverer confirms it has been handled.

## 4. Choosing the Lab Strategy

We choose a simple model for clear verification:

| Component | Choice |
| --- | --- |
| Source topic | `poison.lab.input` |
| DLT | `poison.lab.input-dlt` |
| Partitions | 1 per topic |
| Consumer group | `poison-lab-group` |
| Input data | String, using `StringDeserializer` |
| Primary poison pill | Payload `"POISON"` causing listener to throw `PoisonRecordException` |
| Retry | `FixedBackOff(200L, 2L)`: **2 retries**, 3 total delivery attempts |
| After retries exhausted | `DeadLetterPublishingRecoverer` sends record to DLT |
| Commit | Record listener container commits after processing/recovery succeeds |
| Test | `@EmbeddedKafka` running a real Kafka broker in tests |
| Transactions | **Container transactions disabled** in the primary lab |

This model focuses on **blocking retry and DLT**. It is ideal for observing a poison pill within a single partition. If production uses `@RetryableTopic` (non-blocking retry) or Kafka transactions, do not copy this error handler directly without reviewing the differences in sections 15 and 16.

## 5. Dependencies for the Test Application

Example `build.gradle` in a Spring Boot project with compatible plugins/BOM:

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

`spring-kafka` includes `@KafkaListener`, `DefaultErrorHandler`, and `DeadLetterPublishingRecoverer`. `spring-kafka-test` provides `@EmbeddedKafka` and `KafkaTestUtils`. The examples below target **Spring Kafka 3.x**; Spring Boot 3.x requires Java 17 or newer. Let Spring Boot's BOM pick compatible patch versions; if using another release line, verify API signatures before copying.

## 6. Configuring Consumer, Producer, and Listener

Create `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: poison-pill-lab

  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: poison-lab-group
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    listener:
      ack-mode: record

app:
  kafka:
    input-topic: poison.lab.input
    dlt-topic: poison.lab.input-dlt
```

Explanation:

- `enable-auto-commit=false`: lets the listener container and error handler control commits based on processing outcomes rather than committing periodically regardless of errors.
- `ack-mode=record`: for a non-transactional **record listener**, the container acknowledges each processed record under the ack mode rules.
- `auto-offset-reset=earliest`: a brand-new consumer group with no committed offset starts from the beginning; it **does not affect** a group that already has a valid committed offset.
- `StringDeserializer`: in the first lab, Kafka bytes decode into a valid String and the error is raised **inside the listener**. This differs from testing a JSON deserialization poison pill.
- `spring.kafka.producer.transaction-id-prefix` is omitted in the primary lab. If enabled and the container auto-configures as transactional, error handling behavior changes and requires the transactional guidance later in this lesson.

Configuring `ack-mode` alone does not guarantee the right error handler is active: register the `DefaultErrorHandler` bean in the next section.

## 7. Creating Dedicated Lab Topics

Use `NewTopic` beans to declare an input topic and a DLT with the same partition count. With Spring Boot and `KafkaAdmin`, missing topics are created automatically when permissions allow:

```java
package com.example.poison;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class PoisonTopicsConfig {

    public static final String INPUT = "poison.lab.input";
    public static final String DLT = "poison.lab.input-dlt";

    @Bean
    NewTopic poisonInputTopic() {
        return TopicBuilder.name(INPUT)
                .partitions(1)
                .replicas(1)
                .build();
    }

    @Bean
    NewTopic poisonDltTopic() {
        return TopicBuilder.name(DLT)
                .partitions(1)
                .replicas(1)
                .build();
    }
}
```

`replicas(1)` is for **single-broker tests**, not production. If your DLT keeps the **same partition** as the source record, the DLT must have matching partitions. In production, provision topics, partitions, retention, and ACLs via standard infrastructure tooling and define explicitly who may read failing payloads.

## 8. Writing a Listener That Intentionally Throws for One Record

First, declare a custom exception type:

```java
package com.example.poison;

public final class PoisonRecordException extends RuntimeException {
    public PoisonRecordException(String message) {
        super(message);
    }
}
```

Next, write the record listener. For lab observation, the class uses `AtomicInteger` and `CountDownLatch`; this is **test-support state** and should not be used for durable business counters in production:

```java
package com.example.poison;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PoisonLabListener {

    private static final Logger log =
            LoggerFactory.getLogger(PoisonLabListener.class);

    public final AtomicInteger poisonAttempts =
            new AtomicInteger();

    public final Set<String> goodValues =
            ConcurrentHashMap.newKeySet();

    public final CountDownLatch goodRecordsProcessed =
            new CountDownLatch(2);

    @KafkaListener(
            topics = PoisonTopicsConfig.INPUT,
            groupId = "poison-lab-group")
    public void onRecord(ConsumerRecord<String, String> record) {
        log.info("Consuming topic={} partition={} offset={} key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key());

        if ("POISON".equals(record.value())) {
            int attempt = poisonAttempts.incrementAndGet();
            log.warn("Injected poison pill failure: attempt={} " +
                            "partition={} offset={}",
                    attempt, record.partition(), record.offset());

            throw new PoisonRecordException(
                    "POISON_PAYLOAD");
        }

        // For test observation only; replace with real business logic.
        goodValues.add(record.value());
        goodRecordsProcessed.countDown();
    }
}
```

In this lab, the `POISON` record **always fails**; retrying cannot succeed without changing the code or data. This lets the test verify what happens when the retry budget is exhausted.

**Do not put `if (payload.equals("POISON"))` into production business code.** In real systems, errors come from data contracts, parsers, or validators, and any fault injection must live in isolated test fixtures or profiles.

Never write `catch (PoisonRecordException e) { log.warn(...); }` and return normally: the container would treat the input as processed, defeating the test.

## 9. Configuring Bounded Retries and a Dead Letter Topic

Spring Kafka 3.x uses `DefaultErrorHandler` for **non-transactional record listeners**. We configure up to two retries followed by routing the failing record to the DLT:

```java
package com.example.poison;

import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class PoisonErrorHandlingConfig {

    @Bean
    DefaultErrorHandler poisonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        template,
                        (record, exception) ->
                                new TopicPartition(
                                        PoisonTopicsConfig.DLT,
                                        record.partition()));

        // If DLT publishing fails, do not treat the record as recovered.
        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(200L, 2L));

        return handler;
    }
}
```

In Spring Boot 3.x, when using the Boot-auto-configured `ConcurrentKafkaListenerContainerFactory`, a `CommonErrorHandler`/`DefaultErrorHandler` bean is automatically wired into it. **If your application defines custom factories**, call `factory.setCommonErrorHandler(handler)` explicitly; simply declaring the bean does not guarantee every custom factory picks it up.

### Reading `FixedBackOff` Correctly

`new FixedBackOff(200L, 2L)` produces:

```text
Delivery #1: initial listener invocation
     |
     +-- fail
     |
     +-- backoff 200 ms
     |
Delivery #2: first retry
     |
     +-- fail
     |
     +-- backoff 200 ms
     |
Delivery #3: second retry
     |
     +-- fail
     |
     v
DeadLetterPublishingRecoverer
     |
     +-- DLT publish succeeds
     |
     v
Source record is considered recovered;
container can advance to the next record.
```

The second argument is the **number of retries after the initial delivery**, not the total number of listener invocations. For exceptions classified as *not retryable*, `DefaultErrorHandler` can invoke the recoverer immediately without executing those two retries.

### Notes on Offset Commits After Recovery

With a record listener, `AckMode.RECORD`, and `DefaultErrorHandler` succeeding, the container commits the recovered record's offset per `ackAfterHandle` (default `true`) and continues. With `AckMode.MANUAL_IMMEDIATE`, committing recovered offsets also requires considering `setCommitRecovered(true)` per documentation and ack configuration.

**Never call `consumer.commitSync()` manually inside a recoverer** to "skip" a record: manual commits can skip other records, break ordering rules, and prevent retries if DLT publishing fails.

### Which Errors Skip Retries, and Which Should Retry?

`DefaultErrorHandler` maintains a default list of **fatal/not-retryable** exceptions, including `DeserializationException` and several conversion/argument-mapping errors; these usually cannot heal by replaying identical bytes.

For explicit business errors, you can classify more exceptions:

```java
handler.addNotRetryableExceptions(
        InvalidSchemaException.class,
        UnsupportedEventTypeException.class);
```

`InvalidSchemaException` and `UnsupportedEventTypeException` here are **application-defined classes**, not built into Spring Kafka. Once added, tests should expect **immediate DLT routing** rather than three delivery attempts.

For `PoisonRecordException` in this lab, **do not** add it to the not-retryable list so we can observe all three attempts as planned.

## 10. Running a Trial with a Test Producer or CLI Tool

Inputs must arrive in **exact order on one partition**:

| Expected Offset in New Topic | Key | Value | Expectation |
| --- | --- | --- | --- |
| 0 | `event-001` | `GOOD-1` | Processed successfully |
| 1 | `event-002` | `POISON` | Fails three times, routed to DLT |
| 2 | `event-003` | `GOOD-2` | Continues after poison pill is recovered |

With `KafkaTemplate`:

```java
template.send("poison.lab.input", 0, "event-001", "GOOD-1")
        .get(10, TimeUnit.SECONDS);

template.send("poison.lab.input", 0, "event-002", "POISON")
        .get(10, TimeUnit.SECONDS);

template.send("poison.lab.input", 0, "event-003", "GOOD-2")
        .get(10, TimeUnit.SECONDS);
```

This is an **illustrative send snippet**: `template` must be a `KafkaTemplate<String,String>` bean, with `TimeUnit` imported from `java.util.concurrent.TimeUnit`. Waiting on each future confirms the broker accepted records in send order; production code does not necessarily send synchronously record-by-record.

Watching the logs shows a typical sequence:

```text
INFO  Consuming offset=0 key=event-001       -> GOOD-1
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=1
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=2
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=3
INFO  Published failed record to DLT
INFO  Consuming offset=2 key=event-003       -> GOOD-2
```

The line "Published failed record to DLT" is an **event you must instrument** if you want that exact log, not a default message Spring Kafka always emits with that wording. In tests, actually read from the DLT rather than trusting logs alone.

## 11. Integration Testing with `@EmbeddedKafka`

A unit test throwing `PoisonRecordException` proves the listener can fail, but it does not verify Kafka offsets, DLT publishing, or consumer redelivery. Therefore, this lab uses an **embedded Kafka broker** from `spring-kafka-test`.

### 11.1. Configuring the Test Context

```java
package com.example.poison;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
        classes = PoisonPillIT.TestApplication.class,
        properties = {
                "spring.kafka.consumer.group-id=poison-lab-group",
                "spring.kafka.consumer.enable-auto-commit=false",
                "spring.kafka.consumer.auto-offset-reset=earliest",
                "spring.kafka.consumer.key-deserializer=" +
                    "org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.consumer.value-deserializer=" +
                    "org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.producer.key-serializer=" +
                    "org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.producer.value-serializer=" +
                    "org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.listener.ack-mode=record"
        }
)
@EmbeddedKafka(
        partitions = 1,
        topics = {
                PoisonTopicsConfig.INPUT,
                PoisonTopicsConfig.DLT
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class PoisonPillIT {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    @Import({
            PoisonTopicsConfig.class,
            PoisonErrorHandlingConfig.class,
            PoisonLabListener.class
    })
    static class TestApplication {
    }

    // Test method added in section 11.2.
}
```

This is a **test class skeleton** without the test method yet. `@EmbeddedKafka` creates the test topics and broker; `bootstrapServersProperty` ensures Spring Boot's producer and consumer connect to the embedded broker instead of a local `localhost:9092` Kafka instance. `@DirtiesContext` reduces the risk of stale contexts or brokers leaking across tests.

Within the same context, declared `NewTopic` beans do not recreate topics that already exist compatibly. In a real test suite, **use unique topics/groups per test context** or isolate contexts so prior offsets do not skew expectations.

### 11.2. Testing the DLT and Subsequent Records

Add these imports to the test class:

```java
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;
```

Add the fields and test method to `PoisonPillIT`:

```java
@Autowired
KafkaTemplate<String, String> template;

@Autowired
EmbeddedKafkaBroker broker;

@Autowired
PoisonLabListener listener;

@Test
void poisonPillGoesToDltAndNextRecordStillProcesses()
        throws Exception {

    Map<String, Object> observerProps =
            KafkaTestUtils.consumerProps(
                    "dlt-observer-" + UUID.randomUUID(),
                    "false",
                    broker);

    observerProps.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    observerProps.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    observerProps.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> dltObserver =
                 new DefaultKafkaConsumerFactory<String, String>(
                         observerProps).createConsumer()) {

        // Read DLT from the beginning; observer uses its own group.
        broker.consumeFromAnEmbeddedTopic(
                dltObserver, PoisonTopicsConfig.DLT);

        template.send(PoisonTopicsConfig.INPUT,
                     0, "event-001", "GOOD-1")
                .get(10, TimeUnit.SECONDS);

        template.send(PoisonTopicsConfig.INPUT,
                     0, "event-002", "POISON")
                .get(10, TimeUnit.SECONDS);

        var lastSend = template.send(
                PoisonTopicsConfig.INPUT,
                0,
                "event-003",
                "GOOD-2").get(10, TimeUnit.SECONDS);

        // Consumer still advances past the poison pill to the next record.
        assertTrue(
                listener.goodRecordsProcessed.await(
                        30, TimeUnit.SECONDS));

        assertTrue(listener.goodValues.contains("GOOD-1"));
        assertTrue(listener.goodValues.contains("GOOD-2"));

        // 1 initial attempt + 2 retries per FixedBackOff.
        assertEquals(3, listener.poisonAttempts.get());

        ConsumerRecord<String, String> dead =
                KafkaTestUtils.getSingleRecord(
                        dltObserver,
                        PoisonTopicsConfig.DLT,
                        Duration.ofSeconds(20));

        assertEquals("event-002", dead.key());
        assertEquals("POISON", dead.value());
        assertEquals(0, dead.partition());

        // DLT observer sees no other messages within the check window.
        assertEquals(0,
                dltObserver.poll(
                        Duration.ofSeconds(2)).count());

        // Committed offset is the next position after the last record.
        long expectedNextOffset =
                lastSend.getRecordMetadata().offset() + 1;

        TopicPartition inputPartition =
                new TopicPartition(PoisonTopicsConfig.INPUT, 0);

        Map<String, Object> inspectorProps =
                KafkaTestUtils.consumerProps(
                        "poison-lab-group",
                        "false",
                        broker);
        inspectorProps.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        inspectorProps.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);

        try (Consumer<String, String> inspector =
                     new DefaultKafkaConsumerFactory<String, String>(
                             inspectorProps).createConsumer()) {

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(20);

            Long committedOffset = null;

            while (System.nanoTime() < deadline) {
                var committed = inspector.committed(
                        Set.of(inputPartition),
                        Duration.ofSeconds(5));
                var offset = committed.get(inputPartition);

                if (offset != null) {
                    committedOffset = offset.offset();
                }
                if (Long.valueOf(expectedNextOffset)
                        .equals(committedOffset)) {
                    break;
                }

                Thread.sleep(100L);
            }

            assertEquals(
                    Long.valueOf(expectedNextOffset),
                    committedOffset);
        }
    }
}
```

**Reading the test results accurately:**

- `goodRecordsProcessed.await(...)` proves the listener reached `GOOD-2` without getting stuck permanently on `POISON`.
- `poisonAttempts == 3` confirms the 2-retry policy, **not** "the listener ran once."
- The DLT consumer receives the exact `key=event-002` and `value=POISON`.
- Querying `committed(...)` uses **group `poison-lab-group`**, not the DLT observer's new group. The offset is compared against `lastSend.offset + 1` rather than a hardcoded `3`, making it resilient even if the topic already held data.
- `poll(2 seconds)` is a **finite-window observation of no duplicates**, not mathematical proof that a duplicate could never arrive later.
- The test intentionally creates a **single-partition** source topic so the ordering and offsets of the three records are straightforward.

This integration test covers a **non-transactional record listener**. It does not verify exactly-once across an input/output Kafka transaction; if EOS is required, write a dedicated test as described in section 16.

### 11.3. Inspecting DLT Headers

`DeadLetterPublishingRecoverer` can attach metadata to trace the source error, including:

| Header | Meaning |
| --- | --- |
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic containing the original record |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Source partition |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Source offset |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Original timestamp |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Exception class recorded by recoverer |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Underlying cause class when present |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace if included in headers |

You can extend the test to assert `dead.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC)` exists and decodes as UTF-8. For partition and offset headers, use the binary byte encoding Spring Kafka writes rather than assuming every header is plain text.

Do not assume every header is populated in every version or publish path. Verify the source **topic/partition/offset/key** and essential error codes against the actual Spring Kafka version in use.

**Security warning:** The DLT may store failing payloads as well as exception messages and stack traces. Set appropriate retention, ACLs, and data masking policies; never dump raw PII or tokens into observability logs.

## 12. Simulating a Transient Error as a Control Against Poison Pills

A thorough test suite must distinguish:

```text
Event A: TRANSIENT-1
  attempt 1 -> DatabaseTimeoutException
  attempt 2 -> succeeds
  -> not sent to DLT

Event B: POISON
  attempt 1 -> PoisonRecordException
  attempt 2 -> PoisonRecordException
  attempt 3 -> PoisonRecordException
  -> DLT
```

You can track a counter for key `TRANSIENT-1` in a test fixture:

```java
private final AtomicInteger transientAttempts =
        new AtomicInteger();

private void processTestValue(String value) {
    if ("TRANSIENT-1".equals(value)
            && transientAttempts.incrementAndGet() == 1) {
        throw new IllegalStateException(
                "Injected temporary dependency timeout");
    }
}
```

With the same `DefaultErrorHandler`, the transient event retries and succeeds without landing in the DLT. Tests should verify **subsequent success, offset advancement, and invocation count**.

In production, transient exceptions should be classified by root cause (timeouts, rate limits, connection pools) with tuned backoff; avoid blanket "retry everything 3 times" policies regardless of error nature.

## 13. Poison Pills Occurring Inside the Deserializer

The scenario above uses `StringDeserializer` and throws inside the listener. A trickier case is a broker holding **bytes that cannot deserialize into a Java type**.

For example, a consumer expects JSON:

```json
{"orderId":"ORD-101","quantity":2}
```

Yet a producer sent:

```text
{"orderId": ???, "quantity": }
```

If `JsonDeserializer` is configured directly, an exception can occur **before `poll()` returns a normal record**, and the listener is never invoked. You cannot handle this merely with a `try/catch` inside `@KafkaListener`.

### 13.1. What Does `ErrorHandlingDeserializer` Do?

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer:

```text
Kafka bytes
    |
    v
ErrorHandlingDeserializer
    |
    v
JsonDeserializer (delegate)
    |
    +-- success --> object passed to @KafkaListener
    |
    +-- fail ----> creates DeserializationException metadata
                    in headers, carrying error details/raw bytes
                    |
                    v
               container error handling
                    |
                    v
               DLT or other policy
```

For a **record listener**, when headers carry a `DeserializationException`, Spring Kafka can route the failing record straight to the container's error handler without invoking the business listener. `DefaultErrorHandler` treats `DeserializationException` as fatal/not-retryable by default, because reparsing identical bytes with the same schema rarely changes the outcome.

### 13.2. Configuring the Deserializer at the Proper Layer

**Spring Kafka 3.x** example with `JsonDeserializer`:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderEvent
        "[spring.json.trusted.packages]": com.example.events
```

`OrderEvent` is an application-defined business DTO; replace the package and class name with your project's type. In Spring Kafka 4.x, Jackson JSON serializer/deserializer APIs change, so **never copy Spring Kafka 3.x `JsonDeserializer` settings verbatim** to 4.x without checking documentation.

When handling deserialization errors, the DLT producer must be able to send **raw `byte[]`**. Spring Kafka can recover original bytes as the DLT value when using `DeadLetterPublishingRecoverer` with `ErrorHandlingDeserializer`. **Do not assume a single `StringSerializer` or `JsonSerializer<OrderEvent>` handles every case** and will serialize raw bytes properly.

A multi-template recoverer pattern:

```java
// Conceptual snippet inside a Spring Kafka 3.x @Configuration.
// stringTemplate and bytesTemplate must use producer factories
// with matching serializers.

Map<Class<?>, KafkaOperations<?, ?>> templates =
        new LinkedHashMap<>();

templates.put(byte[].class, bytesTemplate);
templates.put(String.class, stringTemplate);

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(templates);
```

Key imports: `java.util.Map`, `java.util.LinkedHashMap`, `org.springframework.kafka.core.KafkaOperations`, `org.springframework.kafka.listener.DeadLetterPublishingRecoverer`. When JSON deserializes into `OrderEvent`, also add a matching template for object types sent to the DLT, or use `DelegatingByTypeSerializer` by value type. This is a **configuration snippet** illustrating the idea, not full producer factory/bean wiring.

### 13.3. Testing Deserialization Errors

A separate test scenario:

1. Configure the consumer with `ErrorHandlingDeserializer`, JSON delegate, and `OrderEvent`.
2. Have the test producer use `ByteArraySerializer` to send **truncated or syntactically invalid JSON raw bytes**.
3. Write to an isolated topic/group and wait for the error handler to receive the exception.
4. Assert **the business listener is not invoked** for the bad record (unless `failedDeserializationFunction` overrides this).
5. Assert the DLT holds the **exact raw bytes** or chosen quarantine format.
6. Verify source headers and exception type.
7. Assert a subsequent valid record is still consumed after recovery.

Keep this test **separate** from the in-listener `POISON` test. Never use `StringDeserializer` to simulate a JSON deserialization failure, because it happily decodes bytes into a `String` and invokes the listener anyway.

## 14. What Happens If the DLT Also Fails?

A reliable runbook must also test **recovery failures**. Common causes:

- The DLT topic does not exist and auto-creation is disabled.
- The DLT producer lacks `WRITE` permission.
- The DLT has fewer partitions than the source when the resolver preserves partition numbers.
- The DLT producer's serializer cannot handle the payload type.
- The broker or DLT partition leader is unavailable.
- Payload plus headers exceed size limits after repeated republishes.
- The DLT send times out without the application checking the result.

```text
POISON offset 41
   |
   v
3 failed attempts
   |
   v
DeadLetterPublishingRecoverer
   |
   +-- DLT publish succeeds
   |        |
   |        v
   |   record recovered; continue processing
   |
   +-- DLT publish FAILS
            |
            v
      NOT considered recovered
            |
      retry/seek/alert per policy
```

When the recoverer **throws an exception**, `DefaultErrorHandler` keeps the failing record in the retry/seek cycle per configuration and does not mark it recovered. Setting `recoverer.setFailIfSendResultIsError(true)` improves detection of failed DLT sends instead of treating an errored send future as successful.

Include a negative test: temporarily make DLT publishing fail in a broker/container test and verify **the failing record's offset is not committed as recovered**. Once the DLT recovers, the record must publish and the consumer must resume. Never rely on a single `Thread.sleep` to infer offsets; use a conditional polling loop with a bounded timeout.

**Note:** if production uses an async producer/client while tests only verify `KafkaTemplate.send()` returned a future, DLT durability is not proven. Account for the recoverer's confirmation policy and durable storage guarantees.

## 15. How Do Blocking Retries and `@RetryableTopic` Differ?

They differ significantly. The main lab uses **blocking retry**: `DefaultErrorHandler` waits and redelivers the record within the same container processing thread.

An alternative is **non-blocking retry** using retry topics managed via `@RetryableTopic`/`RetryTopicConfiguration`. Failing records are published to delayed retry topics so the main consumer can keep moving instead of blocking behind old failures.

| Criterion | `DefaultErrorHandler` Blocking Retry | `@RetryableTopic` Non-Blocking Retry |
| --- | --- | --- |
| Retry location | Same source topic/partition via seek or resubmit | Dedicated retry topics |
| Processing order | Closer to partition order since bad records hold subsequent ones | Can **reorder processing** as later records overtake retried ones |
| Long backoff | Can hold/pause the container; requires checking poll intervals | Delays handled via retry topics / scheduling |
| Extra topics | No retry topics needed; DLT only if used | Usually requires retry topics plus DLT |
| Batch listeners | `DefaultErrorHandler` supports dedicated batch semantics | **Non-blocking retry does not support batch listeners** per documentation |
| Container transactions | Can use after-rollback policy instead | **Does not combine directly with container transactions** |
| Goal | Preserve order and handle errors close to source | Prevent one poison pill from stalling the main consumer too long |

Do not mix both models in one test expecting identical ordering or offsets. When ordering by `accountId` or `orderId` matters, moving a failing record to a retry topic lets subsequent records pass ahead of it; the application must redesign idempotency and ordering checks.

## 16. What If the Listener Uses Kafka Transactions / EOS?

**The primary lab does not enable transactions.** For a **Kafka transactional listener**, the framework generally does not rely on the default `DefaultErrorHandler` setup used by non-transactional record listeners; exceptions must abort the transaction, after which **`DefaultAfterRollbackProcessor`** handles seeking, retrying, and recovering.

```text
Transaction T1:
  read input offset 41
  KafkaTemplate.send(output)
  listener throws
     |
     v
  ABORT Kafka transaction T1
     |
     +-- aborted output not visible to read_committed
     +-- consumer offset not committed in T1
     |
     v
  AfterRollbackProcessor
     |
     +-- retry same record
     +-- or recover to DLT per policy
```

**Conceptual** configuration example for Spring Kafka 3.x:

```java
// Configuration on a transactional listener container factory.
// Snippet only; wire the matching KafkaTransactionManager,
// ProducerFactory, and KafkaTemplate for your project version.
DefaultAfterRollbackProcessor<String, String> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(500L, 2L));

factory.setAfterRollbackProcessor(processor);
```

With transactional recovery, if you want **DLT publishing and the recovered consumed offset to commit together in a new Kafka transaction**, configure `DefaultAfterRollbackProcessor` along with a transactional `KafkaTemplate` and `commitRecovered` per your version's guidance. Do not copy the `DefaultErrorHandler` bean from the primary lab and claim exactly-once is tested.

Furthermore, **`@RetryableTopic` non-blocking retries do not combine directly with container transactions**, and batch listeners have different rollback semantics than record listeners. Document both constraints clearly when moving from this lab to an EOS production pipeline.

### What Else Must a Transactional Poison Pill Test Verify?

- Kafka outputs from aborted transactions are **not visible** to `read_committed` consumers.
- Input offsets are **not committed** by aborted transactions.
- Retries and recovery/DLT follow the after-rollback processor policy.
- If the recovered offset commits in a new transaction, it aligns with the DLT publish outcome.
- Side effects in **external databases or APIs outside Kafka transactions** still require idempotency; Kafka EOS does not automatically provide end-to-end exactly-once.

## 17. Batch Listeners, Multiple Partitions, and Processing Order

This lab uses a **single-partition record listener**. Enabling batch listeners or higher concurrency introduces extra concerns:

### Batch Listeners

Suppose a listener receives a poll of 5 records and the third one fails:

```text
Batch: [GOOD-1, GOOD-2, POISON, GOOD-3, GOOD-4]
                         |
                         v
                 throw exception
```

Without indicating the failing index/record, the error handler may have to retry **the entire batch**. Spring Kafka provides `BatchListenerFailedException` to pinpoint the failing record within a batch and enable targeted recovery/retries.

```java
for (int i = 0; i < records.size(); i++) {
    try {
        process(records.get(i));
    } catch (RuntimeException ex) {
        throw new BatchListenerFailedException(
                "Failed at batch index " + i, ex, i);
    }
}
```

This is only a batch listener snippet; `records` is the list passed by the container and `BatchListenerFailedException` is `org.springframework.kafka.listener.BatchListenerFailedException` in Spring Kafka 3.x. When transactions are enabled, batch rollback and replay semantics differ further and must be tested separately.

### Multiple Partitions

```text
Partition 0: GOOD / POISON / GOOD -> delayed during retries
Partition 1: GOOD / GOOD          -> can continue
Partition 2: GOOD / GOOD          -> can continue
```

Depending on concurrency and container retry mechanics, delays can still affect threads handling multiple partitions. **Never conclude "only partition 0 is affected" without testing the real topology.** Multi-partition tests should use fixed keys/partitions, inspect assignments and per-partition consumer lag, and never look only at total group lag.

### `max.poll.interval.ms` and Backoff

Long blocking retries extend listener execution time, affecting `poll()` cadence and group membership. Spring Kafka offers `ContainerPausingBackOffHandler` for long delays; nevertheless, backoff, `max.poll.interval.ms`, and poll timeouts must match real volumes and latencies.

Never use `FixedBackOff.UNLIMITED_ATTEMPTS` in production just because you "don't want to lose messages." It can prevent a poison pill from ever recovering, causing sustained lag and masking systemic misconfigurations.

## 18. Classifying Exceptions to Prevent Misusing the DLT

Suppose a service executes:

```java
void handle(OrderEvent event) {
    validate(event);          // InvalidOrderException
    repository.save(event);   // DataAccessResourceFailureException
    api.notify(event);        // HttpServerErrorException
}
```

A practical policy:

| Exception | Usually Retry? | Handling Approach |
| --- | --- | --- |
| `InvalidOrderException` | No, or minimal | DLT/quarantine with reason code and schema version |
| `DeserializationException` | No | DLT raw bytes, or halt on systemic schema breakage |
| `DataAccessResourceFailureException` | Bounded | Backoff; if prolonged, alert on DB outage |
| API 503 / rate limit | Yes, with tuned backoff | Avoid overloading downstream; consider circuit breaker |
| `NullPointerException` from bug | Per policy, never infinite | Safely preserve failing input, fix code, and replay |
| `AuthorizationException` / bad credentials | Retrying records rarely helps | Alert and fix permissions/config; consider pausing consumer |
| `ProducerFencedException` in transactional flow | Do not reuse fenced producer | Let framework/lifecycle replace producer and investigate identity |

**Dumping every error into the DLT does not equal high reliability.** A 30-minute database outage could flush millions of valid records into the DLT, forcing operations into massive manual replays. Separate validation poison pills from dependency outages.

Whenever a DLT is used to preserve inputs, maintain a **triage and replay process**—never treat the DLT as fire-and-forget.

## 19. Production Runbook for Poison Pills

### Step 1 — Confirm the Symptom

Inspect per-topic/partition consumer lag, committed offsets, and the repeatedly failing record. Collect at minimum:

```text
consumerGroupId = orders-worker
topic           = orders.events
partition       = 3
offset          = 41802
eventId         = evt-...
exceptionType   = InvalidOrderStateException
firstSeen       = ...
deliveryAttempt = ...
appVersion      = ...
schemaVersion   = ...
```

Avoid printing full sensitive payloads on dashboards. Use dedicated access-controlled tools when raw bytes must be inspected.

### Step 2 — Classify the Root Cause

Check the failure tier:
- Deserialization: did the consumer receive an object, or fail before the listener?
- Validation: does the input genuinely violate the contract?
- Business logic: is code handling a valid edge case poorly, or is upstream data corrupt?
- Infrastructure: are DB, API, or Kafka brokers experiencing widespread errors?
- Deployment/schema: are only pods on a new version failing, or all pods?

Never immediately resend the record before knowing why it failed; replaying the same payload may fail again and amplify log noise.

### Step 3 — Verify Retry and DLT Policy

Verify attempt counts, backoff, retry classification, recoverer outcome, DLT topic name, partitions, ACLs, and whether the DLT producer can serialize the value.

If DLT publishing succeeded, correlate the source record via **topic + partition + offset** and DLT headers. If no DLT record exists, do not assume the record vanished: it may still be retrying or the recoverer may be failing.

### Step 4 — Choose the Recovery Action

| Case | Action |
| --- | --- |
| Genuinely corrupt data | Fix at source or emit a corrective record with explicit version/correlation |
| Application bug | Fix code, deploy, then perform controlled DLT replay |
| Producer/consumer schema skew | Align contracts and deploy compatibility before replaying |
| Infrastructure outage | Restore dependency, let retries proceed or restart per runbook |
| DLT overload | Throttle replay rate and batch by reason code |
| Unclear whether side effects committed | Reconcile DB/APIs and ensure idempotency before re-emitting |

### Step 5 — Controlled DLT Replay

Never simply rewind consumer group offsets or blast every DLT record back into the source topic blindly. A safe replay workflow should:

1. Filter records by `reasonCode`, time window, schema version, and fixed payloads.
2. Preserve `eventId`/business keys and link back to original topic/partition/offset for auditing.
3. Specify the **target**: source topic, retry topic, or a dedicated repair topic.
4. Ensure consumers/writers are idempotent so records are never processed twice if source and DLT overlap.
5. Rate-limit concurrency to avoid triggering another outage.
6. Count replayed, completed, and still-failing records; archive reconciliation evidence.
7. Do not purge the DLT immediately upon starting replay; clean up only per approved retention and procedures.

**Processing order:** replaying to the tail of a topic assigns new offsets, potentially altering order relative to records that arrived after the poison pill. If strict per-account or per-order ordering is required, account for that before skipping or recovering.

## 20. Observability and Alerting

A system must detect poison pills **before the DLT fills up or consumer lag climbs for hours**.

| Metric / Event | Purpose |
| --- | --- |
| Listener failure count by exception class | Identifies data bugs and recurring code errors |
| Retry attempts distribution | Flags records consuming excessive attempts |
| DLT publishing success/failure | Ensures the recoverer is not silently dropping records |
| DLT ingress rate | Catches widespread schema/producer deployment regressions |
| Consumer lag per partition | Exposes partitions pinned on a single offset |
| Time since last committed offset movement | Detects stalled consumers |
| `consumer.assignment` / rebalances | Evaluates backoff and concurrency impact |
| DLT age / oldest unresolved item | Tracks unresolved backlog |
| Business idempotency violations | Detects duplicate side effects during replays |
| Input schema version vs. app version | Isolates compatibility mismatches |

Reference structured log event:

```json
{
  "eventType": "kafka.poison-pill.detected",
  "service": "orders-worker",
  "consumerGroupId": "orders-worker",
  "topic": "orders.events",
  "partition": 3,
  "offset": 41802,
  "eventId": "evt-41802",
  "errorType": "InvalidOrderStateException",
  "reasonCode": "UNSUPPORTED_ORDER_STATE",
  "attempt": 3,
  "action": "PUBLISH_DLT",
  "schemaVersion": "2"
}
```

This is an **application-defined schema**, not an automatic event emitted by Spring Kafka in this exact format. Never use high-cardinality `eventId`, `topic`, or `offset` values as unbounded **Prometheus labels**; keep them in structured logs/traces and use low-cardinality labels for metrics.

### Alerts Worth Watching

- DLT publish failure or permission denied: high priority, since recoverer failures can pin offsets.
- Sudden spike in a single reason code: potential system-wide schema deployment bug.
- Lag on one partition failing to drain while the consumer is healthy: likely poison pill or infinite retries.
- High DLT volume in a short window: quality gate should pause downstream rather than assuming normal operations.
- Aging unresolved DLT items: backlog breaching handling SLA.

## 21. Common Implementation Mistakes

| Symptom | Cause | Check / Fix |
| --- | --- | --- |
| Listener loops forever on the same offset | Infinite retries or DLT recoverer failing | Bound backoff; verify DLT topic, ACLs, and serializer |
| Poison pill never enters DLT | Default error handler only logs without a recoverer | Configure `DeadLetterPublishingRecoverer` |
| Attempt count differs from expected | Misread `FixedBackOff(maxAttempts)` or exception treated as fatal | Count **initial attempt + retries**; inspect classifications |
| Subsequent records never process | Failing record not recovered, partition preserves order | Test DLT success and committed offset progress |
| DLT contains `null` or fails serialization | Failure happened in deserializer; DLT template cannot send `byte[]` | Use `ErrorHandlingDeserializer` and a raw-bytes-capable template/serializer |
| Consumer dies before listener | Deserializer throws outside `poll()` | Wrap with `ErrorHandlingDeserializer` |
| DLT written yet source still retries | Recovery failed, offset commit failed, or wrong ack policy | Check recoverer result, ack mode, and group committed offset |
| DLT has duplicates | Send retries/timeouts, replays, or multiple paths | Make DLT consumer idempotent; inspect headers and producer outcomes |
| Test passes because no DLT record appears | Observer started at `latest` or consumer missed messages | Subscribe/assign before sending or seek to beginning |
| Flaky CI tests | Reused topics/groups/offsets or sleep-based timing | Isolate tests, wait on explicit conditions with bounded timeouts |
| Entire topic slows down | Partitions share consumer threads or retries take too long | Inspect assignment/concurrency and backoff/pause behavior |
| Mass DB errors dumped to DLT | Transient errors misclassified | Use circuit breakers, retries, and outage policies |
| `@RetryableTopic` breaks ordering | Failing records go to retry topics while later records overtake them | Define ordering requirements before adopting |
| Using `DefaultErrorHandler` in EOS and swallowing exceptions | Transaction fails to roll back as expected | Use after-rollback processing and let transaction exceptions propagate |
| DLT leaks PII | Uncontrolled raw payload/exception header storage | Enforce ACLs, retention, masking, and quarantine rules |
| Replay creates duplicate side effects | Non-idempotent writer when source and DLT overlap | Enforce unique business keys / inbox / outbox and reconciliation |
| Batch listener retries the whole batch | Missing `BatchListenerFailedException` to pinpoint record | Throw exception with the failing batch index/record |
| Only new deploy fails on records; old deploy works | Schema incompatibility or code bug | Canary, version contracts, and replay after fix |

## 22. Extended Exercises

**Exercise A — No DLT:** replace `DefaultErrorHandler` with a retry policy intentionally omitting a recoverer; observe the offset pinned at `POISON` and rising lag. Run only on test topics for a short window, and restore configuration before touching real traffic.

**Exercise B — Mark Not-Retryable:** add `PoisonRecordException.class` to `addNotRetryableExceptions`; resend the three records on a **fresh** topic/group and confirm the poison pill goes to the DLT after one delivery while `GOOD-2` still processes.

**Exercise C — Transient Error:** make a record fail once and then succeed; assert it is **not** sent to the DLT and the group offset advances.

**Exercise D — DLT Write Failure:** configure a test broker/topic/ACL that breaks DLT publishing with `setFailIfSendResultIsError(true)` enabled; confirm the record is not marked recovered. After fixing the DLT, verify the consumer resumes.

**Exercise E — Raw JSON Bytes:** send malformed JSON with `ByteArraySerializer`, configure `ErrorHandlingDeserializer` and a `byte[]`-capable DLT producer; assert the listener is not called and raw input is preserved per policy.

**Exercise F — Multi-Partition:** use 3 partitions with a poison record on partition 1; record lag and progress per partition with concurrency 1 vs. 3. Compare cross-partition impact risks.

**Exercise G — Transactional Flow:** enable Kafka transactions, switch error recovery to `DefaultAfterRollbackProcessor`, verify aborted outputs are hidden from `read_committed`, and test DLT + recovered offsets under a properly configured transaction policy.

**Exercise H — DLT Replay:** build a repair consumer with a deduplication key, replay a fixed record, verify no duplicate side effects in business tables, and audit the original offset → replay offset mapping.

## 23. Official References

- [Spring Kafka — Handling Exceptions, DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Publishing Dead-letter Records](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#dead-letters)
- [Spring Kafka — Serialization, Deserialization and ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka — Transactions and After-Rollback Behavior](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Testing Applications with Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka — Consumer Concepts and Offset Management](https://kafka.apache.org/documentation/)

**Conclusion:** A thorough poison pill simulation demonstrates **failure at a specific offset**, bounded retries, routing into a **DLT**, the **consumer group continuing to commit offsets**, and subsequent valid records still being processed. For in-listener failures on non-transactional record listeners, use `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`; for pre-listener failures, use `ErrorHandlingDeserializer` with a DLT serializer supporting raw bytes. When Kafka transactions are enabled, verify `DefaultAfterRollbackProcessor` and transaction outcomes separately. A DLT is only **a mechanism to isolate failing records**—true operational reliability comes from accurate error classification, backlog monitoring, data protection, idempotency, and controlled replay procedures.
