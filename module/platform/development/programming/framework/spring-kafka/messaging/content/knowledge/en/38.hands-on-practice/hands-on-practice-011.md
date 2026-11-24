# Simulating Consumer Restart

## 1. Lab Objective

In this hands-on lab, you will simulate a consumer that processes a record successfully at the business layer but stops before acknowledging the offset. When the listener container restarts with the same consumer group, Kafka redelivers the uncommitted record.

The lab uses one topic, one partition, and one consumer so ordering is easy to observe:

1. The producer sends an order event.
2. The consumer receives the record and persists the event to the database.
3. The listener intentionally skips calling `Acknowledgment.acknowledge()` on the first attempt.
4. The listener container stops and then restarts.
5. Because the offset was never committed, the consumer receives the same record again.
6. The idempotency check detects that the event was already processed and avoids creating a second side effect.
7. The listener acknowledges the offset after redelivery.

Expected outcomes:

- The listener receives the same event twice.
- The database contains only one processed row for that event ID.
- The partition offset is committed after redelivery.
- You understand why Kafka can redeliver records after a restart and why consumers must be idempotent.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Kafka
    participant C as Consumer
    participant DB as Database
    P->>K: Publish event E (offset 0)
    K->>C: Deliver E
    C->>DB: Insert processed_event(E)
    DB-->>C: Commit DB transaction
    C--xK: Do not acknowledge offset
    Note over C: Listener container stops
    Note over C: Listener container restarts
    K->>C: Redeliver E (offset 0)
    C->>DB: Check event ID E
    DB-->>C: Already exists, skip side effect
    C->>K: acknowledge()
    K-->>C: Commit next offset (1)
~~~

This lab simulates restarting the Spring Kafka listener container within the same JVM. The H2 database remains alive while the container is stopped. This is a controlled test setup to observe redelivery; the final section explains how to extend this into a full JVM restart with a persistent database.

## 2. Knowledge Applied

| Component | Role in this lab |
|---|---|
| `KafkaTemplate` | Sends events to the test topic |
| `@KafkaListener` | Receives records from the topic |
| Consumer group | Stores committed offsets of the processing stream |
| `AckMode.MANUAL` | Listener explicitly acknowledges offsets |
| `enable.auto.commit=false` | Prevents the Kafka client from auto-committing unexpectedly |
| `KafkaListenerEndpointRegistry` | Retrieves the listener container to stop/start it |
| `AdminClient` | Reads committed offsets for verification |
| `JdbcTemplate` and H2 | Persists markers of processed events |
| Event ID | Idempotency key to eliminate duplicate side effects |

Kafka stores offsets per consumer group and partition. For a record at offset 0, after successful acknowledgment, the committed offset is normally 1 because the committed offset represents the next position to read.

If a consumer stops before committing, the next startup resumes from the latest committed offset. When no committed offset exists yet, `auto.offset.reset=earliest` lets the consumer start from the earliest record still in the log.

## 3. Creating the Project and Dependencies

The example uses Gradle with a Spring Boot version managed by the project. If the project already has plugins and dependency management, only add the missing dependencies.

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.kafka:spring-kafka'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

`spring-kafka-test` provides Embedded Kafka, `KafkaTestUtils`, and utilities to wait for listener partition assignment. H2 stores processed events within the same test context.

Suggested package structure:

~~~text
src/
  main/
    java/com/example/restartlab/
      RestartLabApplication.java
      domain/OrderCreated.java
      service/OrderProcessingService.java
      messaging/RestartLabListener.java
    resources/
      application.yml
      schema.sql
  test/
    java/com/example/restartlab/
      ConsumerRestartIntegrationTest.java
~~~

## 4. Configuring Kafka and the Database

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: restart-lab
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    listener:
      ack-mode: manual
      concurrency: 1

  datasource:
    url: jdbc:h2:mem:restartlab;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:

  sql:
    init:
      mode: always

lab:
  skip-first-ack: false
~~~

Important settings:

- `enable-auto-commit=false`: disables Kafka client auto-commit.
- `ack-mode=manual`: listener must call `acknowledge()` to confirm records.
- `concurrency=1`: uses only one consumer thread for this lab.
- `auto-offset-reset=earliest`: if the group has no committed offset yet, start from log start.
- H2 `DB_CLOSE_DELAY=-1`: keeps the in-memory database alive while the JVM runs, even when the last connection closes.

In the integration test, Embedded Kafka overrides `spring.kafka.bootstrap-servers` so the application connects to the embedded broker. No external Kafka instance is needed for this test.

## 5. Creating the Schema to Store Processed Events

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS processed_event (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
~~~

`event_id` is the primary key so each event is recorded only once. The lab uses one partition and one consumer thread, so the check-then-insert executes sequentially.

In systems with multiple partitions or concurrent consumers, use an atomic insert-if-absent operation per database dialect and a unique constraint. PostgreSQL example:

~~~sql
INSERT INTO processed_event(event_id, order_id, order_status)
VALUES (?, ?, ?)
ON CONFLICT (event_id) DO NOTHING;
~~~

Only update projections or trigger downstream side effects when the insert returns an affected row count of 1. The unique constraint is still necessary to protect against two consumers processing a duplicate nearly simultaneously.

## 6. Creating the Application Class and Event

Create the application class `RestartLabApplication.java`:

~~~java
package com.example.restartlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestartLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RestartLabApplication.class, args);
    }
}
~~~

Create the event `OrderCreated.java`:

~~~java
package com.example.restartlab.domain;

public record OrderCreated(
    String eventId,
    String orderId,
    String status
) {
}
~~~

`eventId` must remain stable across redeliveries. Never generate a new UUID inside the listener on each delivery because a replay would then look like a completely different event.

## 7. Writing the Idempotent Processing Service

Create `OrderProcessingService.java`:

~~~java
package com.example.restartlab.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.restartlab.domain.OrderCreated;

@Service
public class OrderProcessingService {

    private final JdbcTemplate jdbcTemplate;

    public OrderProcessingService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public boolean process(OrderCreated event) {
        Integer count = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM processed_event
            WHERE event_id = ?
            """,
            Integer.class,
            event.eventId()
        );

        if (count != null && count > 0) {
            return false;
        }

        jdbcTemplate.update(
            """
            INSERT INTO processed_event(
                event_id,
                order_id,
                order_status
            )
            VALUES (?, ?, ?)
            """,
            event.eventId(),
            event.orderId(),
            event.status()
        );

        return true;
    }
}
~~~

The service returns:

- `true`: the event ID did not exist yet and was recorded.
- `false`: the event ID was already processed earlier; no further side effects are created.

`@Transactional` ensures the event record write runs inside a database transaction. The listener invokes the service through a Spring bean proxy; when the service call returns, the service transaction has already committed before the listener decides whether to acknowledge.

This is a concise illustration for a sequential consumer. Under concurrent load, replace SELECT-then-INSERT with an atomic insert-if-absent as shown in the PostgreSQL example above; if the insert adds zero rows, skip side effects.

## 8. Writing a Listener That Skips Acknowledgment Once

Create `RestartLabListener.java`:

~~~java
package com.example.restartlab.messaging;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.restartlab.domain.OrderCreated;
import com.example.restartlab.service.OrderProcessingService;

@Component
public class RestartLabListener {

    private final ObjectMapper objectMapper;
    private final OrderProcessingService processingService;

    private final AtomicBoolean skipFirstAck = new AtomicBoolean(true);
    private final AtomicInteger deliveryCount = new AtomicInteger();

    private final CountDownLatch firstProcessedWithoutAck =
        new CountDownLatch(1);

    private final CountDownLatch replayAcknowledged =
        new CountDownLatch(1);

    @Value("${lab.skip-first-ack:false}")
    private boolean skipFirstAckEnabled;

    public RestartLabListener(
            ObjectMapper objectMapper,
            OrderProcessingService processingService) {
        this.objectMapper = objectMapper;
        this.processingService = processingService;
    }

    @KafkaListener(
        id = "restartLabListener",
        topics = "orders.restart-lab",
        groupId = "restart-lab",
        concurrency = "1"
    )
    public void onMessage(
            String payload,
            Acknowledgment acknowledgment)
            throws JsonProcessingException {

        OrderCreated event =
            objectMapper.readValue(payload, OrderCreated.class);

        processingService.process(event);
        deliveryCount.incrementAndGet();

        if (skipFirstAckEnabled
                && skipFirstAck.compareAndSet(true, false)) {
            // Side effect completed, but offset has not been acknowledged.
            firstProcessedWithoutAck.countDown();
            return;
        }

        acknowledgment.acknowledge();
        replayAcknowledged.countDown();
    }

    public boolean awaitFirstProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return firstProcessedWithoutAck.await(timeout, unit);
    }

    public boolean awaitReplayAcknowledged(long timeout, TimeUnit unit)
            throws InterruptedException {
        return replayAcknowledged.await(timeout, unit);
    }

    public int deliveryCount() {
        return deliveryCount.get();
    }
}
~~~

Simulation mechanism:

- `lab.skip-first-ack=true` is enabled only in the integration test.
- On the first delivery, the service inserts the event into the database and the listener returns without acknowledging.
- The test stops the listener container after receiving the `firstProcessedWithoutAck` signal.
- When the container restarts, Kafka redelivers the record because the offset was never committed.
- On the second delivery, the service recognizes the event ID already exists; the listener calls `acknowledge()`.

Never enable `lab.skip-first-ack=true` in production configuration. It is solely a lab toggle to simulate the failure window between side effect persistence and offset commit.

## 9. Writing the Integration Test with Embedded Kafka

Create `ConsumerRestartIntegrationTest.java`. The test uses a single-partition topic and a fixed consumer group to observe offsets deterministically.

~~~java
package com.example.restartlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.restartlab.domain.OrderCreated;
import com.example.restartlab.messaging.RestartLabListener;

@SpringBootTest(properties = {
    "lab.skip-first-ack=true",
    "spring.kafka.consumer.enable-auto-commit=false",
    "spring.kafka.listener.ack-mode=manual",
    "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.restart-lab"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class ConsumerRestartIntegrationTest {

    private static final String TOPIC = "orders.restart-lab";
    private static final String GROUP_ID = "restart-lab";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    RestartLabListener listener;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void redeliversRecordWhenContainerRestartsBeforeAck()
            throws Exception {

        MessageListenerContainer container =
            registry.getListenerContainer("restartLabListener");

        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 1);

        OrderCreated event = new OrderCreated(
            "event-1001",
            "order-1001",
            "CREATED"
        );

        String payload = objectMapper.writeValueAsString(event);

        kafkaTemplate.send(
            TOPIC,
            event.orderId(),
            payload
        ).get(10, TimeUnit.SECONDS);

        // Wait for database side effect to finish; listener has not acknowledged.
        assertThat(
            listener.awaitFirstProcessed(10, TimeUnit.SECONDS)
        ).isTrue();

        // Wait for callback to ensure consumer has stopped before checking offset.
        CountDownLatch stopped = new CountDownLatch(1);
        container.stop(stopped::countDown);
        assertThat(stopped.await(10, TimeUnit.SECONDS)).isTrue();
        assertThat(container.isRunning()).isFalse();

        // Group has no committed offset for this partition yet.
        assertThat(committedOffset()).isNull();

        // Restart listener container with the same group ID.
        container.start();
        ContainerTestUtils.waitForAssignment(container, 1);

        assertThat(
            listener.awaitReplayAcknowledged(10, TimeUnit.SECONDS)
        ).isTrue();

        // MANUAL ack is committed by the container after processing the record.
        await()
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                assertThat(committedOffset()).isEqualTo(1L)
            );

        assertThat(listener.deliveryCount()).isEqualTo(2);

        Integer processedRows = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM processed_event
            WHERE event_id = ?
            """,
            Integer.class,
            event.eventId()
        );

        assertThat(processedRows).isEqualTo(1);
    }

    private Long committedOffset() throws Exception {
        Properties properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString()
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var offsets = admin.listConsumerGroupOffsets(GROUP_ID)
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS);

            var committed = offsets.get(new TopicPartition(TOPIC, 0));

            return committed == null ? null : committed.offset();
        }
    }
}
~~~

The test verifies four independent conditions:

1. `deliveryCount = 2`: the same record was received by the listener twice.
2. `processedRows = 1`: the database recorded the event only once.
3. `committedOffset = 1`: the consumer confirmed the next read position after the record at offset 0.
4. `committedOffset` before the restart is `null`: the first delivery did not commit an offset.

If the test does not observe redelivery, check `AckMode`, `enable-auto-commit`, consumer group, and the timing of stopping the container. Do not add fixed `Thread.sleep()` waits; use latches, `waitForAssignment`, and Awaitility as shown.

## 10. Running the Lab

With the Gradle Wrapper on Linux/macOS:

~~~bash
./gradlew test --tests "com.example.restartlab.ConsumerRestartIntegrationTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.restartlab.ConsumerRestartIntegrationTest"
~~~

Expected result:

~~~text
ConsumerRestartIntegrationTest
  redeliversRecordWhenContainerRestartsBeforeAck() PASSED

Tests run: 1, Failures: 0
~~~

If the project uses Maven, run the corresponding test class:

~~~bash
./mvnw -Dtest=ConsumerRestartIntegrationTest test
~~~

Embedded Kafka starts inside the test context and stops automatically when the context closes. No separate local broker needs to be running for this test.

## 11. Observing Offsets and Consumer Group State

In a standalone Kafka environment, you can inspect the group with the CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group restart-lab
~~~

After the record is acknowledged, partition 0 has a committed offset of 1. If another record arrives at offset 1 and the consumer processes it successfully, the next committed offset will be 2.

You can inspect the topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.restart-lab
~~~

With Embedded Kafka, the test already uses `AdminClient` to verify the committed offset directly. The CLI is only used when running the lab against a standalone broker.

## 12. Why Does the Database Have One Row While the Listener Received Twice?

Kafka and the database are two separate state-storage systems. In this example, the database commits before the listener acknowledges the offset:

~~~text
Database transaction: COMMIT
Kafka offset:          NOT COMMITTED
Consumer container:    STOPPED
~~~

When the consumer restarts, Kafka has no knowledge that the database already processed the event. The broker only knows the group never committed the offset, so it redelivers the record.

On the second delivery:

~~~text
Database lookup: event_id already exists
Business side effect: skipped
Kafka offset: ACKNOWLEDGED
~~~

This is at-least-once delivery behavior. Consumers must accept that a record may be delivered multiple times and guard side effects with idempotency.

## 13. Trying Variations for Deeper Understanding

After the basic test passes, vary one condition at a time and observe the results.

| Experiment | Change | What to observe |
|---|---|---|
| A. Acknowledge immediately | Disable `lab.skip-first-ack` | Listener receives once, offset is committed |
| B. Without idempotency | Remove the event ID check | Record is received twice and side effects may duplicate |
| C. Auto commit enabled | Enable `enable-auto-commit` | Offsets may commit independently of the desired business completion point |
| D. New group ID | Change group ID | New group does not share the old group's committed offsets |
| E. Send two records | Send two events to the same partition | Observe offsets and processing order |
| F. Multiple partitions | Increase partitions and concurrency | Requires atomic idempotency when duplicate events may run concurrently |

In experiment C, do not conclude from a single run that auto-commit always loses data. The outcome depends on poll intervals, commit timing, and when the process stops. The goal is to see why auto-commit is unsuitable when an application must tie offset commits to business processing completion.

## 14. Simulating an Exception Instead of Just Skipping Acknowledge

Another variation is letting the listener write to the database and then throw an exception before acknowledging. In that case, the error handler may retry immediately inside the same container rather than waiting for a restart.

~~~java
processingService.process(event);

if (simulateFailureBeforeAck) {
    throw new IllegalStateException("Simulated crash window");
}

acknowledgment.acknowledge();
~~~

If `DefaultErrorHandler` is configured for retries, the record may be redelivered within the same container lifecycle. To simulate restart specifically as intended in this lab, the test takes the stop/start container path after the listener returns without acknowledging.

Do not use simulated exceptions in the same test if the goal is to isolate restart behavior; the two scenarios involve different retry mechanisms.

## 15. Extending to a Full JVM Restart

The main test restarts the listener container within the same Spring application context. To simulate a real process restart:

1. Replace in-memory H2 with PostgreSQL or a persistent database backed by a volume.
2. Run Kafka and the database outside the consumer's JVM.
3. Use the same `group.id` before and after the restart.
4. Introduce a controlled pause after the database transaction commits but before `acknowledge()`.
5. Force-kill the JVM at that point so the consumer cannot commit the offset.
6. Restart the application with the same configuration.
7. Verify the event is redelivered and the database unique key prevents duplicate side effects.

Do not use in-memory H2 for process restart tests because data is lost when the JVM exits. If using file-based H2, check database recovery and file locks when the process is killed; a separate database server is generally better suited for production-like simulations.

Never use `Runtime.halt()` or kill production processes for testing. Perform these tests in an isolated local/staging environment with dedicated topics, consumer groups, and databases.

## 16. Limitations to Keep in Mind

- Restarting the listener container is not identical to restarting the entire JVM.
- In-memory H2 retains data within the same JVM; it does not prove database crash recovery after a process crash.
- `AckMode.MANUAL` only controls offsets when the listener calls acknowledge; auto-commit must be disabled so no other commit mechanism interferes.
- A record can be redelivered after a rebalance, timeout, or consumer crash, not only after an intentional restart.
- Database idempotency does not automatically protect HTTP calls, emails, or payments. Those side effects require their own idempotency keys or compensation mechanisms.
- Kafka transactions can coordinate Kafka record publishing and Kafka offset commits; they do not automatically form a distributed transaction with a relational database.
- When using batch listeners or multiple partitions, offset commits and processing order are more complex than this single-record/single-partition example.

## 17. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Listener does not receive `Acknowledgment` | Ack mode is not MANUAL/MANUAL_IMMEDIATE | Set `spring.kafka.listener.ack-mode=manual` |
| Record is not redelivered | Offset was committed or auto-commit is enabled | Check committed offset and `enable-auto-commit=false` |
| Listener receives more than twice | Container was not stopped, another retry ran, or test sent duplicates | Check group, container state, and event ID |
| Test cannot find container | Listener ID mismatch | Check `@KafkaListener(id=...)` and registry |
| `waitForAssignment` times out | Broker not ready or listener not subscribed | Check Embedded Kafka and topic |
| Offset does not advance to 1 | Listener did not acknowledge or container has not committed yet | Wait on latch and poll committed offset with timeout |
| Database has duplicate rows | Idempotency check missing or non-atomic under concurrency | Use a unique constraint and insert-if-absent |
| Events reprocessed after deploy | Consumer group or offset changed | Verify group ID and offset reset strategy |

## 18. Completion Checklist

- [ ] Project created with `spring-kafka`, `spring-kafka-test`, JDBC, and H2.
- [ ] Single-partition topic created.
- [ ] Kafka auto-commit disabled.
- [ ] Listener configured with `AckMode.MANUAL`.
- [ ] Event sent with a stable event ID.
- [ ] Event persisted to the database before acknowledging.
- [ ] First acknowledgment intentionally skipped.
- [ ] Listener container stopped after first processing.
- [ ] Confirmed group has no committed offset yet.
- [ ] Container restarted with the same group ID.
- [ ] Confirmed listener receives the same event again.
- [ ] Confirmed database has only one row for the event ID.
- [ ] Confirmed committed offset advances to 1.
- [ ] Tried disabling idempotency to observe duplicate side effects.
- [ ] Distinguished container restart from full JVM restart.

This lab demonstrates that a consumer restart can cause Kafka to redeliver records when offsets have not been committed. A listener may receive the same event multiple times even though the database side effect already completed on the prior attempt. By implementing idempotent processing keyed by event ID, the application preserves accurate business outcomes while still acknowledging offsets after redelivery.
