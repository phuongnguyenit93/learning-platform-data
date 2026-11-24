# Building a Consumer with Retry and DLT in Spring Kafka

## 1. Lab Objectives

A Spring Kafka consumer receives order update events from the `orders.events` topic. When the database connection is interrupted for a few seconds, the system should perform **bounded retries** to avoid losing work. When an event cannot be processed because of malformed JSON or a missing order ID, retrying repeatedly is useless; the consumer should **route the record to a Dead Letter Topic (DLT)** for investigation or controlled reprocessing.

Without this strategy, a single bad record can keep a partition stuck at one offset indefinitely, or an overly broad error handler can skip the record without preserving evidence. Conversely, excessive retries can increase Kafka lag, overload the database, trigger redeliveries, and cause duplicate business side effects.

The lesson **"Building a Consumer with Retry and DLT"**, part of the **Operations Practice** group in the **Spring Kafka Reliability Operations** module, walks through a resilient processing flow:

```text
                      Apache Kafka
                    topic: orders.events
                            |
                            v
                      @KafkaListener
                            |
                            v
                   Parse + validate event
                            |
                    +-------+-------+
                    |               |
                  Valid          Invalid
                    |               |
                    v               v
             Business service   Non-retryable
                    |               |
             +------+-----+         |
             |            |         |
          Success   Transient error |
             |            |         |
             v            v         |
          Offset      Retry + backoff
          advances         |
                         +-- Success --> offset advances
                         |
                         +-- Retries exhausted ---+
                                                  |
                                                  v
                                    DeadLetterPublishingRecoverer
                                                  |
                                                  v
                                        orders.events.DLT
                                                  |
                                          Audit + alerting
                                          + controlled replay
```

After this lesson, you will be able to:

1. Configure Spring Boot 3.x / Spring Kafka 3.x to read from and write to Kafka safely.
2. Build a `@KafkaListener` that separates business errors from infrastructure errors into distinct categories.
3. Use `DefaultErrorHandler`, `FixedBackOff`, and `DeadLetterPublishingRecoverer` for bounded retries followed by DLT routing.
4. Understand the relationship between handler success, DLT publishing, and consumer offset commits.
5. Protect business side effects with transactions and idempotency.
6. Isolate the DLT consumer and avoid creating an infinite DLT → DLT forwarding loop.
7. Write integration tests with embedded Kafka and design tests against production-compatible databases and brokers.
8. Set up metrics, alerts, retention, and a safe replay workflow.

The examples use Java 17+, Spring Boot 3.x, Spring Kafka 3.x, PostgreSQL, and JUnit 5. Specific APIs and behavior may differ across Spring Kafka / Kafka client versions; verify against your actual version before operating in production.

## 2. Choosing a Strategy: Consumer-Side Retry or Topic-Based Retry?

In Spring Kafka, there are two common approaches:

| Strategy | Mechanism | Advantages | Trade-offs |
| --- | --- | --- | --- |
| **Blocking retry** | `DefaultErrorHandler` retries the record within the container, optionally seeking/resubmitting according to policy | Centralized configuration, easy to preserve per-partition ordering in simple cases | The partition/consumer can slow down or be blocked during retries |
| **Non-blocking retry** | `@RetryableTopic` forwards the record through one or more retry topics on a delayed schedule | Prevents one failing record from holding up the source partition for too long | Increases topic/consumer topology; requires managing ordering and offsets across separate topics |
| **DLT** | Sends unprocessable records to a dead-letter topic | Preserves failure evidence and allows the main flow to continue on valid recovery | Requires storage, alerting, access control, and post-DLT handling procedures |

The main lab chooses **blocking retry + DLT**, because it clearly demonstrates an end-to-end flow with `DefaultErrorHandler`.

Toward the end, this lesson introduces how to switch to `@RetryableTopic` when a poison record must not block a partition for too long. **Do not enable both retry layers simultaneously without calculating the total number of attempts**, because a single record could be retried across multiple tiers.

### Distinguishing Terminology

- **Retry**: an operation fails and is attempted again.
- **Recoverer**: the component invoked when an error is no longer retried under the policy, such as publishing the record to a DLT.
- **DLT**: the topic holding records that require investigation or handling outside the main consumption path.
- **Replay**: the deliberate operation of reintroducing a record from the DLT back into the processing pipeline.
- **Skip**: allowing the source to advance past a failing record under a defined policy. A successful DLT publish may be the condition for the error handler to treat the source record as recovered, but it does **not** mean the business logic for that record succeeded.

## 3. Designing the Business Scenario

Input event:

```json
{
  "eventId": "evt-20261115-001",
  "orderId": "order-42",
  "version": 7,
  "status": "PAID"
}
```

The source topic is `orders.events` with 3 partitions. The error topic is `orders.events.DLT` with **at least 3 partitions** if you want to preserve the source record's partition number.

We assume three outcome categories:

| Scenario | Exception/Condition | Policy |
| --- | --- | --- |
| Valid event, DB available | No exception thrown | Persist business state; container manages offset commit |
| Temporary DB outage | `TransientDataAccessException` or application-defined transient exception | Retry with backoff; send to DLT when exhausted |
| Malformed JSON, blank eventId/orderId, invalid version | `InvalidOrderEventException` | No retry; route to DLT immediately |
| Unclassified errors outside defined categories | Other exceptions | Must have an explicit policy: fail/retry/DLT by severity; do not assume programming bugs are transient |
| DLT broker/topic unavailable | DLT publish failure | Must not mark the source record as handled; requires alerting and recovery |

In this example, **invalid events are still valuable for investigation**, so they are sent to the DLT rather than merely logged and dropped.

### Attempt Counts Must Be Explicitly Defined

We use:

```text
Initial delivery: 1
Retries after failure: 2
Maximum handler invocations in simple case: 3

Backoff between retries: 1 second
```

This is the interpretation of `FixedBackOff(1000L, 2L)`: **two retries after the initial processing attempt**, in the normal case without assignment changes, rollbacks, or rebalances. Do not confuse the second parameter with the "total number of attempts."

With restarts or rebalances, the actual number of processing attempts can be higher because uncommitted records can be redelivered. Therefore, the business handler must still be idempotent.

## 4. Project Structure

A suitable directory layout:

```text
order-consumer/
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/orderconsumer/
│   │   │   ├── OrderConsumerApplication.java
│   │   │   ├── config/KafkaConsumerConfiguration.java
│   │   │   ├── config/KafkaTopicConfiguration.java
│   │   │   ├── model/OrderEvent.java
│   │   │   ├── consumer/OrderEventListener.java
│   │   │   ├── consumer/OrderDltListener.java
│   │   │   ├── service/OrderProjectionService.java
│   │   │   ├── service/DltAuditService.java
│   │   │   └── error/
│   │   │       ├── InvalidOrderEventException.java
│   │   │       └── TemporaryOrderDependencyException.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── db/migration/V1__order_projection.sql
│   └── test/
│       └── java/com/example/orderconsumer/
│           ├── OrderEventListenerTest.java
│           └── OrderKafkaIntegrationTest.java
```

Classes are presented by section and packages/imports can be adapted to your project. The code snippets below are practice examples; a production system must add Kafka authentication, schema registry, observability, migrations, and security policies.

## 5. Required Dependencies

For a Gradle project using a compatible Spring Boot plugin/BOM:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'

    // Use when running PostgreSQL integration tests with a container.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages the versions of many dependencies via its BOM; choose a Spring Boot 3.x release compatible with your application's Spring Kafka 3.x version. Do not mix arbitrary versions without verifying compatibility.

Library groups:

- `spring-kafka`: listener containers, Kafka producer/consumer, common error handler, recoverers.
- `spring-boot-starter-jdbc`: `JdbcTemplate` and transaction manager for database side effects.
- `spring-boot-starter-actuator`: foundation for health/metrics; full metrics may require Micrometer/Prometheus configuration.
- `spring-kafka-test`: embedded test broker and `KafkaTestUtils`.
- `Testcontainers`: when production-like Kafka/PostgreSQL and separate-process fault injection are needed.

Do not use `spring-retry` and `@Retryable` as an implicit substitute for `DefaultErrorHandler` when the goal is managing Kafka records and offsets. They operate at different layers and can create nested retries.

## 6. Kafka Configuration in application.yml

The example uses String keys and values to **parse JSON inside the listener**. This ensures JSON errors in the example are classified as non-retryable business errors instead of failing at the Kafka deserializer layer before the listener is invoked.

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: ${KAFKA_GROUP_ID:order-projection-v1}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        isolation.level: read_committed

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    orders:
      topic: ${ORDERS_TOPIC:orders.events}
      dlt-topic: ${ORDERS_DLT_TOPIC:orders.events.DLT}

logging:
  level:
    org.springframework.kafka: INFO
    com.example.orderconsumer: INFO
```

**Explanation of key choices:**

- `enable-auto-commit=false`: lets the listener container control offset commits according to the ack mode.
- `ack-mode: record`: the container tracks progress record-by-record after the handler succeeds or the record is recovered by the error handler per configuration.
- `concurrency: 1`: one Kafka consumer thread per instance for this lab; increasing concurrency allows multiple consumers in the same group to process multiple partitions in parallel.
- `max-poll-records: 100`: caps the number of records returned per poll; must be coordinated with processing time and `max.poll.interval.ms`.
- `auto-offset-reset: earliest`: applies only when the group has no valid committed offset or the offset is out of retention range; it does not force an active group to reread from the beginning.
- `isolation.level: read_committed`: the consumer reads only committed records from transactional producers if the source uses transactional production. It does not make JDBC side effects exactly-once.
- `acks: all`: the producer waits for acknowledgments per Kafka policy; production also requires considering `min.insync.replicas`, replication, delivery timeout, and producer errors.

Note: security configuration (TLS, SASL, ACLs, secrets) must be added according to your cluster. Never commit passwords or API keys into source control.

## 7. Preparing the Source Topic and DLT

The `DeadLetterPublishingRecoverer` setup below sends failed records to the **same partition number** on the DLT topic:

```text
orders.events-0  -> orders.events.DLT-0
orders.events-1  -> orders.events.DLT-1
orders.events-2  -> orders.events.DLT-2
```

This is a convenient choice for traceability. It requires the DLT topic to have at least as many partitions as the source topic. If the DLT has fewer partitions, publishing to a nonexistent partition will fail.

For local/test environments, topics can be created using `NewTopic`:

```java
package com.example.orderconsumer.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${app.kafka.orders.topic}")
                String topicName) {

        return TopicBuilder.name(topicName)
            .partitions(3)
            .replicas(1)
            .build();
    }

    @Bean
    NewTopic ordersDltTopic(
            @Value("${app.kafka.orders.dlt-topic}")
                String topicName) {

        return TopicBuilder.name(topicName)
            .partitions(3)
            .replicas(1)
            .build();
    }
}
```

Spring Kafka can use `KafkaAdmin` to create `NewTopic` beans when permissions and configuration allow. In production, topics should generally be created and managed via Terraform, operators, CLI, or Kafka governance workflows, because DLT topics need their own security policies, retention, replication, and partition counts.

**Never use a replication factor of 1 in production if broker fault tolerance is required.** The `replicas(1)` example is for local use only. Whenever the source topic's partition count increases, verify that the DLT has enough partitions for the same-partition routing strategy.

### Should Source and DLT Use the Same Retention?

Not by default. The DLT serves investigation and replay, so its retention period may differ from the source depending on compliance, storage capacity, security, and handling workflows. Retention that is too short may cause failed records to expire before operators handle them; retention that is too long may store PII unnecessarily.

## 8. Defining the Event and Exceptions

Application record:

```java
package com.example.orderconsumer.model;

public record OrderEvent(
        String eventId,
        String orderId,
        long version,
        String status) {
}
```

Two illustrative exceptions:

```java
package com.example.orderconsumer.error;

public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }

    public InvalidOrderEventException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

```java
package com.example.orderconsumer.error;

public class TemporaryOrderDependencyException
        extends RuntimeException {

    public TemporaryOrderDependencyException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Error policy:

- `InvalidOrderEventException`: error **not expected to resolve when retrying the same payload**; route to DLT immediately.
- `TemporaryOrderDependencyException`: **recoverable** error caused by a downstream system being temporarily unavailable; perform bounded retries.
- Spring Data Access's `TransientDataAccessException`: an example of JDBC transient errors; also eligible for retry.

Avoid overly broad exception types such as `Exception.class`, because programming or configuration bugs would be retried unnecessarily. When handling HTTP client exceptions, classify based on actual status codes and timeouts instead of assuming every HTTP error is transient.

## 9. Writing the Listener to Read and Validate Events

The listener receives a raw JSON string, parses it with Jackson, and passes it to the business service. Parse and validation errors are explicitly classified before reaching the error handler.

```java
package com.example.orderconsumer.consumer;

import com.example.orderconsumer.error.InvalidOrderEventException;
import com.example.orderconsumer.model.OrderEvent;
import com.example.orderconsumer.service.OrderProjectionService;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

    private final ObjectMapper mapper;
    private final OrderProjectionService service;

    public OrderEventListener(
            ObjectMapper mapper,
            OrderProjectionService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
        id = "order-projection-listener",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onMessage(
            ConsumerRecord<String, String> record) {

        OrderEvent event;

        try {
            event = mapper.readValue(
                record.value(), OrderEvent.class
            );
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException(
                "Malformed order event JSON", ex
            );
        }

        validate(event);

        // The service must have appropriate idempotency and transaction handling.
        service.apply(event);

        log.debug(
            "event=orders.processed topic={} partition={} " +
            "offset={} eventId={}",
            record.topic(),
            record.partition(),
            record.offset(),
            event.eventId()
        );
    }

    private static void validate(OrderEvent event) {
        if (event == null ||
                event.eventId() == null ||
                event.eventId().isBlank() ||
                event.orderId() == null ||
                event.orderId().isBlank() ||
                event.version() < 1 ||
                event.status() == null ||
                event.status().isBlank()) {

            throw new InvalidOrderEventException(
                "Missing or invalid order event fields"
            );
        }
    }
}
```

**Do not catch every `RuntimeException` and return normally.** If the service throws an exception and the listener swallows it, the container may advance the offset according to the ack mode even though the business operation failed.

**Do not log entire raw payloads or exception messages from external sources** if messages may contain PII, tokens, or sensitive data. Correlation logs can use validated/approved `eventId`/key fields; for JSON parsing failures, topic/partition/offset and exception type are sufficient.

### A Note on Ordering

Kafka guarantees offset order **within each partition** during sequential consumption, not global order across partitions. If each order emits multiple versions, choose a stable event key based on `orderId` so events for the same order usually land on the same partition (given a consistent partitioner and unchanged partition count), and ensure the writer enforces version checks so older events cannot overwrite newer state.

## 10. Writing Business Data Idempotently

A record can be reprocessed after a retry, rebalance, or crash. With Kafka at-least-once delivery, business side effects must be protected regardless of how many times the listener is invoked.

PostgreSQL example:

```sql
CREATE TABLE processed_order_event (
    projection_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    event_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Using `JdbcTemplate` inside a single transaction:

```java
package com.example.orderconsumer.service;

import com.example.orderconsumer.model.OrderEvent;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                projection_name, event_id
            ) VALUES ('orders-projection', ?)
            ON CONFLICT (projection_name, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            // This event was already applied in a previous delivery.
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, event_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                event_version = EXCLUDED.event_version,
                current_status = EXCLUDED.current_status,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_projection.event_version
                < EXCLUDED.event_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

In this example:

1. Both the marker insert and the projection update use the same datasource and transaction manager.
2. If an exception occurs before commit, both statements roll back together.
3. If the DB commits successfully but the Kafka offset has not been committed yet, a duplicate delivery hits the existing marker and produces no duplicate effect.
4. The version condition prevents an older event version from overwriting a newer state.
5. The marker only confirms that the event passed through the application logic; it does not prove that external side effects outside the DB succeeded.

**Note:** If an event must trigger side effects outside the transaction—such as sending emails, processing payments, or publishing to Kafka—you must add an outbox pattern or downstream idempotency. A PostgreSQL transaction does not automatically cover HTTP calls or Kafka offset commits.

If the database requires processing every version in strict contiguous sequence, checking `version > current` alone is not enough: you also need gap detection, replay design, and pending-state handling.

## 11. Configuring DefaultErrorHandler and DeadLetterPublishingRecoverer

This is the core mechanism.

A `DefaultErrorHandler` catches listener exceptions, retries according to a `BackOff`, and invokes the recoverer once retries are exhausted. `DeadLetterPublishingRecoverer` publishes failed records to the DLT topic.

```java
package com.example.orderconsumer.config;

import com.example.orderconsumer.error.InvalidOrderEventException;
import com.example.orderconsumer.error.TemporaryOrderDependencyException;

import org.apache.kafka.common.TopicPartition;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    CommonErrorHandler orderCommonErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.orders.dlt-topic}")
                String dltTopic) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                    dltTopic, record.partition()
                )
            );

        // If DLT publishing fails, the record must not be considered recovered.
        recoverer.setFailIfSendResultIsError(true);

        // 2 retries after the initial delivery, 1 second apart.
        FixedBackOff backOff =
            new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

        // Expected data errors will not resolve on retry.
        handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
        );

        // Temporary error categories allowed to retry.
        handler.addRetryableExceptions(
            TemporaryOrderDependencyException.class,
            TransientDataAccessException.class
        );

        return handler;
    }
}
```

### About Exception Classification

`DefaultErrorHandler` includes Spring Kafka's default exception classification, which marks certain fatal exceptions—such as matching serialization/deserialization/conversion errors—as non-retryable. `addRetryableExceptions` adds retryable types, and `addNotRetryableExceptions` marks non-retryable types.

**Do not assume calling `addRetryableExceptions(...)` creates an allowlist that excludes all other exceptions.** By default, the error handler may still retry other exceptions not on the fatal list. When you want a strict policy where "only transient categories are retried," verify the classification / default-false behavior of your Spring Kafka version, or wrap errors at the service boundary into a controlled set of exceptions and explicitly test unclassified cases.

### About DLT Publication

The recoverer in this example routes to a **fixed DLT topic** while preserving `record.partition()`. The source and DLT topics must have matching partitions. With a `StringSerializer` producer, the source record here was deserialized as a `String`, so the DLT `KafkaTemplate` can also send strings safely.

`setFailIfSendResultIsError(true)` instructs the recoverer to treat DLT send errors as failures instead of silently concluding the publish succeeded. Wait times and confirmation semantics also depend on `KafkaTemplate`, producer settings, and the Spring Kafka version. Production requires tuning delivery timeout, `acks`, retries, and monitoring publish errors.

A recoverer can attach headers describing the source topic/partition/offset and exception class/message. Avoid leaking PII via exception messages, DLT payloads, and headers.

## 12. Attaching the Error Handler to the Listener Container Factory

Spring Boot can auto-wire a `CommonErrorHandler` bean in appropriate configurations, but to make the wiring explicit, the example defines a factory named `kafkaListenerContainerFactory`:

```java
package com.example.orderconsumer.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler orderCommonErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(
            orderCommonErrorHandler
        );

        factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
        );

        factory.setConcurrency(1);
        return factory;
    }
}
```

The bean name `kafkaListenerContainerFactory` matches the default name used by `@KafkaListener`; the listener earlier also specifies this name explicitly.

**Factory management must be consistent.** If the project already uses Spring Boot's `ConcurrentKafkaListenerContainerFactoryConfigurer` and customizers, building a factory manually must preserve required security, observation, converter, interceptor, and consumer properties. You can use the Boot configurer to inherit standard configuration and then attach the error handler.

### Lifecycle of a Failing Record

Suppose the handler receives a record at source offset 105:

```text
orders.events partition 2 offset 105
                 |
                 v
           Listener attempt 1
                 |
          transient exception
                 |
            backoff 1s
                 |
                 v
           Listener attempt 2
                 |
          transient exception
                 |
            backoff 1s
                 |
                 v
           Listener attempt 3
                 |
          transient exception
                 |
                 v
      DeadLetterPublishingRecoverer
                 |
                 v
    orders.events.DLT partition 2
                 |
           publish succeeds?
           /             \
         Yes              No
         |                 |
         v                 v
    Handler recovery   Recovery failure,
    completed          source must not
         |             silently advance
         v
    Container may
    commit source
    offset under
    configured policy
```

**A DLT record is not business success.** The consumer group may advance past offset 105 once the message is recovered to the DLT, but a separate handling workflow must still resolve the failed record.

Do not infer exact commit counts from this diagram; commit timing depends on ack mode, container error handling, transactions, and producer/consumer settings.

## 13. How Kafka Offsets Interact with Retries and DLT

There are four distinct events:

1. The Kafka consumer polls a record.
2. The business handler processes the record and may commit to the database.
3. The recoverer may send a failing record to the DLT.
4. The container commits the consumer group's offset.

By default, these **do not form a single atomic transaction**.

| Situation | Business DB | Source Kafka Offset | Consequence |
| --- | --- | --- | --- |
| Listener succeeds, offset commit succeeds | Updated | Advances | Normal processing |
| DB commits, process dies before offset commit | Updated | Not advanced | May be redelivered; requires idempotency |
| Listener fails, retry succeeds | Depends on transaction; eventually completes | Advances on success per policy | No DLT needed |
| Retries exhausted, DLT publish succeeds, source offset commits | Business incomplete | Advances | Record waiting in DLT |
| DLT publish fails | Business incomplete | Not marked as recovered | Requires retry/error alerting and avoiding record loss |
| DLT publish succeeds, but process dies before source offset commit | Business incomplete | May not advance | May produce duplicate DLT records on source replay |

The last point is critical: **the DLT can also contain duplicate records** when a failure happens at the boundary between DLT publish and offset commit. DLT audit and replay systems should enforce a deduplication key—for example combining group/service, source topic, partition, offset, or business event ID.

### Do We Need Kafka Transactions?

If you need exactly-once semantics in a purely Kafka-based consume → transform → produce pipeline, you can use Kafka transactions and a producer transaction manager with proper offset coordination. However, synchronizing with PostgreSQL, HTTP, or email is a separate problem; Kafka transactions do not automatically turn external non-Kafka side effects into exactly-once operations.

This lab chooses an easy-to-reason-about model: **at-least-once + idempotent JDBC + DLT with publish confirmation**.

## 14. Why Deserialization Errors Need Special Handling

In the main example, the Kafka value is a String, so JSON parsing occurs inside the listener. However, many applications configure directly:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
```

If JSON fails to deserialize, the exception occurs **before `@KafkaListener` ever receives the event**. In that case, `try/catch` logic inside the listener never runs.

Spring Kafka provides `ErrorHandlingDeserializer` to surface deserialization failures to the container and error handler layer.

Conceptual configuration example:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orderconsumer.model.OrderEvent
        spring.json.trusted.packages: com.example.orderconsumer.model
```

With this configuration, the listener receives `OrderEvent` directly when the payload is valid. When a deserialization exception occurs, `ErrorHandlingDeserializer` passes the failure details so the error handler can handle it instead of looping endlessly during poll.

**Note on DLT serialization:** for failed deserialization, the recoverer may need to publish **the original `byte[]`**, whereas valid records have type `OrderEvent`. The DLT producer must have a serializer supporting the actual type being sent; you can use `DelegatingByTypeSerializer` mapping `byte[].class -> ByteArraySerializer` and `OrderEvent.class -> JsonSerializer`, or use a dedicated recoverer/producer. If you still use a `KafkaTemplate` with `StringSerializer` from the main example, do not assume it can write objects or `byte[]` produced by a typed-deserializer setup.

Additionally, trusted package settings, schema compatibility, and preservation of original payloads must be managed securely; never use wildcard packages in untrusted environments just to suppress deserialization errors.

## 15. What Does a DLT Record Contain?

A record in `orders.events.DLT` typically preserves the original source record's key and value, and can carry headers describing the failure origin, such as:

- Original topic.
- Original partition.
- Original offset.
- Original consumer group (depending on version/configuration).
- Exception class, cause, and message (per recoverer configuration).
- Timestamp and related metadata.

Descriptive example:

```text
DLT topic:     orders.events.DLT
DLT partition: 2
DLT key:       order-42
DLT value:     {"eventId":"evt-42","orderId":"order-42",...}

Headers (illustrative):
  originalTopic     = orders.events
  originalPartition = 2
  originalOffset    = 105
  exceptionClass    = TemporaryOrderDependencyException
```

Exact physical header names must use the constants/APIs of your Spring Kafka version, such as the constants in `KafkaHeaders`. Do not parse a custom header name unless a producer explicitly writes that header.

### DLT Data Security

The DLT is **a copy of data that can contain failing payloads and exception metadata**. Apply:

1. Dedicated Kafka ACLs granted only to services and personnel needing investigation access.
2. Appropriate retention to avoid storing PII indefinitely.
3. Log redaction and secret masking in the error handler and DLT consumer.
4. Encryption and data protection rules equal to or stricter than the source topic.
5. Auditing of who accesses, replays, or downloads DLT payloads.
6. Limiting exception message content to avoid placing SQL queries, credentials, or raw HTTP bodies into headers.

## 16. Should You Create a @KafkaListener to Automatically Read the DLT?

You can, but **never allow the DLT consumer to automatically forward failures into another DLT indefinitely**.

A DLT handler should perform **auditing, quarantine, and alerting**, not replay back to the source automatically upon reading:

```text
orders.events.DLT
        |
        v
   DLT audit consumer
        |
        v
  Persist error case / alert
        |
        v
  Manual review or approved replay
```

Example DLT consumer class:

```java
package com.example.orderconsumer.consumer;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderDltListener {

    private final DltAuditService auditService;

    public OrderDltListener(DltAuditService auditService) {
        this.auditService = auditService;
    }

    @KafkaListener(
        id = "orders-dlt-audit",
        topics = "${app.kafka.orders.dlt-topic}",
        groupId = "orders-dlt-audit-group",
        containerFactory = "dltListenerContainerFactory"
    )
    public void onDlt(
            ConsumerRecord<String, String> record) {

        auditService.recordFailure(record);
    }
}
```

**Important:** `dltListenerContainerFactory` here must be configured **separately**, with a bounded error policy, and must not reuse the recoverer that publishes to `orders.events.DLT`—otherwise it could create `orders.events.DLT.DLT` or keep looping on the same bad record. If the audit DB is down, the DLT audit consumer itself needs bounded retry/backoff and alerting while leaving the record unacknowledged; do not swallow errors and commit.

If the audit pipeline is not designed yet, **do not enable the DLT listener**. You can still operate the DLT initially using monitoring, `AdminClient`, and manual inspection tools. The DLT functions independently of whether a DLT consumer exists.

### DLT Audit Storage Schema Example

```sql
CREATE TABLE order_dlt_case (
    source_topic VARCHAR(200) NOT NULL,
    source_partition INTEGER NOT NULL,
    source_offset BIGINT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    failure_type VARCHAR(200),
    state VARCHAR(30) NOT NULL DEFAULT 'NEW',
    reviewer VARCHAR(100),
    PRIMARY KEY (
        source_topic, source_partition, source_offset
    )
);
```

Keying by source record coordinates prevents creating duplicate cases for the same source offset if the DLT receives duplicate records. If different systems or consumer groups share the table, add the consumer projection/group to the key per business policy.

Do not use the **DLT offset** as the primary identity of a source event: a single source record can appear at multiple DLT offsets across repeated recoveries.

## 17. Monitoring Retries and DLT with Metrics and Logs

Key metrics to track:

| Metric/Event | Meaning | Alerting Suggestion |
| --- | --- | --- |
| Consumer lag | Source is falling behind or blocked on an error | Lag growing continuously or breaching SLA |
| Handler error rate | Exception rate across deliveries | Abnormal spike by error category |
| Retry attempts | Infrastructure instability | High retry rate even before DLT increases |
| DLT publish rate | Rate of records unprocessable under policy | Any critical event or threshold above baseline |
| DLT publish failure | Failed to route bad records to the DLT | Critical alert |
| DLT backlog / `NEW` cases | Unresolved failed records | Backlog older than handling SLA |
| Processing latency | Handler + downstream duration | p95/p99 breaching SLA |
| DB/HTTP failure | Upstream/downstream failures | Correlate with retries |
| Rebalance frequency | Group changing partition ownership | Frequent rebalances causing duplicates/slowdowns |
| Duplicate suppression | Count of handler calls seeing an already-processed `eventId` | Rising counts indicate redeliveries |

Metrics can come from the Kafka client, Spring Kafka/Micrometer, or custom application instrumentation. Do not assume every name in this table is available out of the box. For example, an application counter might be named `orders_consumer_retry_errors_total`, but you must instrument it yourself if the current stack does not provide it.

### Logs Should Record Error Category and Kafka Coordinates

```text
WARN event=orders.retryable_failure
     topic=orders.events partition=2 offset=105
     exceptionType=TransientDataAccessResourceException

ERROR event=orders.dlt_recovered
      sourceTopic=orders.events sourcePartition=2
      sourceOffset=105 dltTopic=orders.events.DLT
      reason=RETRIES_EXHAUSTED
```

Do not log `event=orders.dlt_recovered` before **confirming the publish actually succeeded**. Use recoverer callbacks/observations or appropriate downstream evidence.

If logs include `eventId` from the payload, only log a validated `eventId` that is approved for logging. For malformed JSON errors, topic-partition-offset coordinates are enough for authorized tools to inspect the source record.

## 18. Pre-Deployment Error Policy Table

A real project should maintain a classification table:

| Exception Category | Retry? | Backoff | When Retries Exhausted |
| --- | --- | --- | --- |
| `TemporaryOrderDependencyException` | Yes | 1s, 2 retries (example) | DLT |
| `TransientDataAccessException` | Yes | 1s, 2 retries | DLT |
| `InvalidOrderEventException` | No | None | Immediate DLT |
| JSON deserialization error | No, or per explicit policy | None | DLT with appropriate raw bytes/headers |
| Authentication/permission failure | Usually no rapid retry | Fix config, alert | Per runbook; avoid retry storms |
| HTTP 429 | Yes when honoring `Retry-After` and rate limits | Longer backoff / jitter | DLT/quarantine or fail per business rules |
| HTTP 400 due to invalid request | No | None | DLT |
| DLT serialization/publishing error | Must not be marked succeeded | Retry/alert per producer policy | Keep recovery pending |
| Unknown programming error | Do not assume transient | Classify/alert | DLT or fail-stop per data requirements |

**DLT is not mandatory for every exception.** For systems requiring "no critical financial record may ever be skipped," the policy may be to halt the partition/job for investigation rather than committing the source offset after DLT routing. The business meaning of routing to a DLT must be agreed upon beforehand.

## 19. Writing a Test Without Depending on a Production Broker

You can use `spring-kafka-test` to run an embedded broker, create both source and DLT topics, and verify invalid records are published to the DLT.

Test goals:

- Source topic has sufficient partitions.
- DLT topic has the same partition count.
- Real listener and error handler are initialized.
- Send invalid JSON or an event with missing fields.
- Wait for the consumer to process; verify the record appears in the DLT.
- Check the DLT key/value and source metadata headers.
- Do not depend on consumer member ordering or fixed `Thread.sleep` calls.

Illustrative annotation setup:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-it",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "app.kafka.orders.topic=orders.events",
    "app.kafka.orders.dlt-topic=orders.events.DLT"
})
@EmbeddedKafka(
    partitions = 3,
    topics = {
        "orders.events",
        "orders.events.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class OrderKafkaIntegrationTest {
    // Test methods are shown in the next section.
}
```

This test assumes the Spring Boot context includes a datasource/transaction manager and business beans; if the application connects to PostgreSQL, use a dedicated test database or Testcontainers. Never point integration tests at a production database.

### Testing a Malformed Record Reaching the DLT

Sample test method:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@Autowired
private KafkaTemplate<String, String> kafkaTemplate;

@Autowired
private EmbeddedKafkaBroker embeddedKafka;

@Test
void invalidJsonIsPublishedToDlt() throws Exception {

    String payload = "{bad-json";

    // The source listener must be running/assigned according to
    // the integration test configuration before sending.
    kafkaTemplate.send(
        "orders.events", 0, "order-42", payload
    ).get(10, TimeUnit.SECONDS);

    Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.consumerProps(
            "dlt-verifier-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        )
    );

    props.put("auto.offset.reset", "earliest");

    try (Consumer<String, String> verifier =
            new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new StringDeserializer()
            ).createConsumer()) {

        // The utility subscribes to and polls the specified topic.
        ConsumerRecord<String, String> dlt =
            KafkaTestUtils.getSingleRecord(
                verifier,
                "orders.events.DLT",
                Duration.ofSeconds(20)
            );

        assertEquals("order-42", dlt.key());
        assertEquals(payload, dlt.value());
        assertEquals(0, dlt.partition());
    }
}
```

The example uses `getSingleRecord` because only one failing record is sent in an isolated test. If multiple DLT records exist, do not use a "single" helper assuming Kafka will always return just one message. Use a polling loop with a timeout and match records by key or source metadata.

**Note:** For test stability, wait until the source listener container receives partition assignments (via `KafkaListenerEndpointRegistry` or `ContainerTestUtils.waitForAssignment(...)`) before publishing. With `auto-offset-reset=earliest` and isolated topics, there is less risk of missing records during startup, but waiting for a ready signal is still good practice.

## 20. Testing Retry Success and Retry Exhaustion

A DLT test for malformed JSON only proves the non-retryable path. Transient failures must also be tested.

### 20.1. Retry Success

Use a simulated dependency that throws an exception on the first two attempts and succeeds on the third:

```java
import java.util.concurrent.atomic.AtomicInteger;

import com.example.orderconsumer.error.TemporaryOrderDependencyException;

public final class FlakyOrderGateway {

    private final AtomicInteger attempts =
        new AtomicInteger();

    public void apply(OrderEvent event) {
        int current = attempts.incrementAndGet();

        if (current <= 2) {
            throw new TemporaryOrderDependencyException(
                "Temporary DB/network failure",
                new IllegalStateException("test-only")
            );
        }
    }

    public int attempts() {
        return attempts.get();
    }
}
```

When this injected gateway is invoked in a consumer test for a single record, verify that:

- The handler is retried according to configuration.
- The third attempt succeeds.
- No DLT record is produced for that event.
- The business output appears exactly once.
- The consumer group continues processing subsequent records.

Merely asserting `attempts == 3` is insufficient if the test does not verify the business effect and offset progress.

### 20.2. Retry Exhaustion

If the dependency always throws `TemporaryOrderDependencyException`:

- The handler is called initially, then retried according to backoff.
- Once retries are exhausted, the recoverer publishes to the DLT.
- The DLT record preserves payload/key and source information.
- The source partition can continue after the error handler recovers successfully under the ack policy.
- No business output exists for the failed record.

In integration tests, also verify **forward progress of subsequent records**: send a valid event right after the poison record to the same partition, and verify it is eventually processed after the failing record is recovered.

Do not assert exact millisecond timings. Backoff, schedulers, Kafka polls, and CI load introduce timing jitter; use bounded timeouts and assert the final outcome.

## 21. Testing DLT Publish Failures

An often overlooked scenario: the recoverer fails to publish to the DLT because the topic does not exist, ACLs lack permission, or the producer fails.

Test design:

1. Send a failing record to the source topic.
2. Make the target DLT unavailable in an isolated test environment or simulate a `KafkaTemplate` send failure.
3. Verify the error handler **does not falsely record recovery as successful**.
4. Verify the source group does not silently skip the record just because DLT publishing failed.
5. Ensure logs/metrics raise alerts for the producer/DLT failure.
6. Restore the DLT and observe proper retry/recovery behavior.

This is an **infrastructure-level** test and must never be performed by deleting a production topic or revoking real ACLs. Use an embedded broker, Testcontainers, or a producer test double that can control send outcomes.

By design, `setFailIfSendResultIsError(true)` ensures publish errors are surfaced. However, how the container handles recovery failures, subsequent retry counts, and seeks depends on error handler state and configuration. Run integration tests against your target Spring Kafka version.

## 22. Testing Offsets and Idempotency on Consumer Crash

A classic production failure:

```text
Consumer A receives event evt-42
       |
       v
Business DB COMMITTED
       |
       X JVM dies before Kafka offset commit
       |
       v
Consumer B receives evt-42 again after rebalance
       |
       v
Business service sees marker evt-42 already exists
       |
       v
No duplicate side effect created
```

This is where **at-least-once + idempotency** must be verified:

- The event is replayed when the source committed offset has not advanced past it.
- Multiple handler invocations may occur for the same event.
- The DB marker is not duplicated.
- The projection holds only one valid version of state.
- The consumer continues consuming subsequent records after B takes over the partition.

**Do not use `container.stop()` indiscriminately as a substitute for a crash.** Graceful shutdown can allow the handler to finish and commit offsets. For real crash tests, use an independent consumer process/container and inject a fault after DB commit and before Kafka offset commit; then kill the process and inspect the committed offset on the broker.

Testcontainers or a staging lab is better suited for this scenario. Embedded Kafka in the same JVM is mainly useful for join/leave and basic retry integration tests.

## 23. Does Blocking Retry Affect Ordering and Lag?

Yes. When retrying a failed record, processing on that partition is delayed. If many events arrive rapidly, consumer lag on that partition can climb.

Example:

```text
Partition 1:
  offset 100 -> DB error, 2 retries
  offset 101 -> waiting
  offset 102 -> waiting
  offset 103 -> waiting
```

The benefit is not rushing ahead to later events while an earlier event remains unresolved, in models that require sequential processing. The cost is reduced throughput when downstream dependencies slow down.

With `FixedBackOff(1000L, 2L)` and thousands of failing records, total wait time can become substantial. Raising the retry limit indefinitely is an easy way to build a backlog without fixing an outage.

### Metrics to View Side by Side

- Rate of retryable exceptions.
- Handler time spent waiting/backing off.
- Consumer lag per partition.
- p95/p99 processing time per event.
- Rate of events recovered to the DLT.
- DB/HTTP latency and error rate.
- Rebalance frequency and poll interval.

If the issue is a prolonged outage, a circuit breaker or policy-driven pause/resume strategy may be better than fast retries. However, when pausing a consumer you must understand the container's heartbeat and poll behavior; calling `pause()` does not mean leaving the group.

## 24. Alternative: @RetryableTopic for Non-Blocking Retry

When a poison record must not hold up the source partition for too long, Spring Kafka supports `@RetryableTopic`.

Conceptual model:

```text
orders.events
    |
    +-- Processing succeeds --> done
    |
    +-- Transient error
            |
            v
      orders.events-retry-...
            |
         backoff
            |
       +----+-----+
       |          |
     success    exhausted
       |          |
       v          v
      done    orders.events-dlt
```

Illustrative configuration snippet:

```java
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableKafkaRetryTopic
class RetryTopicsConfiguration {
}

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0,
        maxDelay = 4000
    ),
    include = {
        TemporaryOrderDependencyException.class
    }
)
@KafkaListener(
    topics = "${app.kafka.orders.topic}",
    groupId = "${spring.kafka.consumer.group-id}"
)
public void onMessage(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

This snippet **illustrates the mechanism** and is not meant to be dropped as-is into the earlier String listener / `DefaultErrorHandler` pipeline. When using non-blocking retries in practice:

1. Choose the proper serializers/deserializers, topic names, and producer templates for source, retry, and DLT topics.
2. Define attempt counts, delays, and how many retry topics to create.
3. Configure handlers for non-retryable exceptions and a dedicated DLT path.
4. Do not stack 3 blocking retries on top of 4 non-blocking retries without intentionally calculating total attempts.
5. Verify per-key event ordering and business version checks.
6. Manage offsets and consumer groups of retry topics independently from the source topology.
7. Review DLT handlers, retention, ACLs, and metrics across all retry and DLT topics.

**Non-blocking retry can alter per-partition processing order.** When record X is routed to a retry topic, record Y behind it on the source topic may be processed before X. For accounts, payments, or versioned state machines, design strict ordering/version checks. Do not choose `@RetryableTopic` merely to "avoid waiting" if the domain requires strict per-key processing order.

Spring Kafka provides multiple ways to configure non-blocking retries: `@RetryableTopic`, `RetryTopicConfiguration`, topic naming/exception policies, and `@DltHandler`. Consult the exact API version used by your project for annotation details; do not copy the entire blocking configuration from the earlier example to non-blocking without adjusting the topology.

## 25. The DLT Is Not a Queue for Infinite Automatic Replay

A dangerous anti-pattern:

```text
Source -> error -> DLT
                   |
                   v
              Auto replay
                   |
                   v
                 Source
                   |
               fails again
                   |
                   v
                  DLT
                   |
                   ... indefinitely
```

This causes:

- Increased record volume, storage cost, and Kafka traffic.
- Retry storms against databases and APIs.
- Difficulty determining the root cause and failure count of an event.
- Repeated side effects if the handler is not idempotent.
- Masking of business errors that actually require manual data correction.

The DLT should be treated as **a quarantine area with an owner and a handling process**, not a "trash bin" or an infinite retry queue.

A safe replay workflow:

1. Inspect the DLT case and root cause.
2. Confirm the target system has recovered or the payload has been validly corrected.
3. Reconcile `eventId` against the business DB to prevent duplicate processing.
4. Approve replay scope: event IDs/offsets, count, schedule, and operator.
5. Publish to a **replay topic** or the source per procedure with a marker/correlation ID and a bounded replay count.
6. Monitor outcomes, keep the source DLT audit record, and update case status (`RESOLVED`/`REOPENED`) as needed.
7. Do not delete DLT records immediately upon publishing a replay without confirming the business outcome per policy.

If a payload must be fixed to become valid, record the new payload version along with the reason. Never silently overwrite the original event and destroy auditability.

## 26. Operations Runbook When DLT Rate Spikes

Suppose a dashboard shows the DLT rate jumping from 0 to 500 events/minute.

**Step 1 — Confirm scope.** Check consumer group, topic, partition, release version, spike start time, and count of unique `eventId`s. Do not rely solely on DLT offset counts.

**Step 2 — Classify exceptions.** Inspect whether errors are JSON, DB, API, permissions, schema, or code regressions. Use exception class/error code logs; avoid exposing raw payloads.

**Step 3 — Assess data impact.** Are source offsets advancing? Is consumer lag growing or shrinking? Are critical business events quarantined without completion?

**Step 4 — Check infrastructure.** Inspect DB/HTTP latency, Kafka DLT topic availability, producer errors, quotas/ACLs, and broker health. If the DLT producer is failing, do not declare that failures are safely quarantined.

**Step 5 — Choose mitigation.** Roll back a canary, reduce concurrency, pause the consumer per runbook, or fix data/DB issues. Never reset group offsets arbitrarily.

**Step 6 — Recover and replay.** Once the root cause is resolved, perform bounded replay and reconcile by business IDs.

**Step 7 — Close the incident.** Record impacted event counts, time to recovery, resolved cases, any missing/duplicate data, and preventive configuration changes.

An unmonitored DLT topic can leave an application looking "green" while the business silently loses data for days.

## 27. Common Implementation Pitfalls

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Malformed JSON causes endless consumer polling | Deserializer throws before listener | Parse String inside listener or use `ErrorHandlingDeserializer` |
| Endless retries on bad data | Non-retryable exceptions not classified | `addNotRetryableExceptions` for data errors |
| Transient errors sent to DLT too early | Retry limit too low or exception misclassified | Review classification, backoff, and policy |
| One bad record stalls a partition for too long | Long blocking retries | Cap backoff/attempts or consider retry topics |
| DLT receives no records | Wrong topic/partition/ACL/serializer | Check DLT partition count and producer errors |
| DLT publish fails yet offset still advances | Improper recovery confirmation/ack policy | Verify `setFailIfSendResultIsError` and integration tests |
| DLT record containing `byte[]` fails to send | Producer uses `StringSerializer` while payload is `byte[]` | Use a DLT serializer supporting raw bytes or a dedicated producer |
| DLT audit listener creates `DLT.DLT` | Reuses source error handler | Dedicated DLT container factory with no recursive recovery |
| Already-processed event writes again | DB commits before Kafka offset commit | Idempotency marker / unique constraint |
| DLT contains duplicate records | DLT publish succeeded before source offset committed | Audit by original topic/partition/offset |
| Lag climbs even though Kafka is healthy | Handler retries or slow downstream | Monitor retry waits, DB latency, partition lag |
| Low DLT rate yet business data is missing | Records filtered/acked incorrectly or side effects failed | Reconcile business keys and outputs |
| Infinite DLT and replay loop | Unbounded auto-replay | Manual/approved replay with a retry budget |
| Non-blocking retry breaks order | Subsequent records run ahead of retried record | Event versioning and ordering policies |
| Handler swallows exceptions | `catch (Exception)` and `return` | Let the error handler handle failures and test offset progress |
| Consumer repeats retries after every deploy | Group offset uncommitted or process crash | Distinguish redelivery from in-process retries |
| Tests pass locally but fail in CI | Asynchronous Kafka assignment and fixed `sleep`s | Use Awaitility, ready signals, and isolated topics/groups |
| Cannot trace DLT record back to source | Missing/stripped metadata headers | Preserve source `KafkaHeaders` and audit records |
| Environments share the same `groupId` | Offsets or workloads split unexpectedly | Scope groups by application and environment |
| Logs leak secrets from exceptions | Unredacted raw payloads or stack traces | Field allowlists and access controls |
| Image rolled back but DB remains corrupted | Side effects already committed | Compensation/reconciliation, not just code rollback |

## 28. Production Readiness Checklist for Consumers

| Item | Question |
| --- | --- |
| Error classification | Are retryable and non-retryable exceptions clearly defined? |
| Attempt count | Are retry limits finite with reasonable backoff? |
| Poll/timeout | Do wait and processing times fit within `max.poll.interval.ms`? |
| DLT topology | Does the DLT topic exist with enough partitions, replication, and ACLs? |
| Producer | Does the DLT producer use the right serializer, `acks`, and delivery timeout? |
| Commit semantics | Are ack mode, auto-commit, error handler, and offset commits clear? |
| Idempotency | Can rebalances/crashes replay events without duplicating side effects? |
| Ordering | Will retry topics or partition concurrency break business ordering? |
| Monitoring | Are lag, retry rate, DLT rate, DLT publish failures, and alerts in place? |
| DLT ownership | Is there an owner/team and SLA for handling DLT cases? |
| Security | Does the DLT have proper ACLs, retention, and PII policies? |
| Replay | Is there a bounded, audited, and approved replay runbook? |
| Testing | Have transient success, exhaustion, malformed events, DLT outage, and crash windows been tested? |
| Rollout | Are canary/rollback plans and business output checks in place? |
| Versioning | Are new and old consumers compatible with schemas and target data? |

If the answer to any critical item is "unknown," add tests or design safeguards before scaling in production.

## 29. Extended Practice Exercises

Create an `order-projection-consumer` application with a 3-partition source topic and a corresponding DLT.

### Part A — Basic Consumer

1. Configure `StringDeserializer` for JSON payloads.
2. Implement `OrderEventListener` with parse/validate logic as shown in the example.
3. Create two exception categories: transient and invalid payload.
4. Configure `DefaultErrorHandler` with `FixedBackOff(1000, 2)`.
5. Use `DeadLetterPublishingRecoverer` preserving the partition number.

### Part B — Failure Scenarios

1. Send a valid event; verify the DB contains the expected projection.
2. Send malformed JSON; verify the record reaches the DLT without lengthy retries.
3. Simulate two DB failures followed by recovery; verify the event is processed and not sent to the DLT.
4. Simulate a sustained DB outage; verify the record is routed to the DLT after the retry budget is exhausted.
5. Force DLT publishing to fail; verify alerts fire and the source record is not silently lost.

### Part C — Idempotency and Restarts

1. Send the same `eventId` twice; verify only one marker record exists.
2. Send version 5 then version 4 of the same order; the projection must not regress.
3. Crash the consumer after DB commit but before offset commit in an independent process.
4. After rebalance, verify the event may replay while business output is not duplicated.

### Part D — Operations

1. Build a dashboard showing consumer lag, retry/DLT rates, and DB latency.
2. Create alerts for DLT publish failures or case backlogs exceeding SLA.
3. Design an audit table keyed by original topic/partition/offset.
4. Write a runbook to replay 10 DLT events after resolving the root cause.
5. Propose when to switch to `@RetryableTopic` and document the ordering risks.

Lab reports should record: source topic/partition/offset, `eventId`, exception type, attempts, recovery outcome, offset state, and actual business side effect count.

## 30. Summary

A reliable **Spring Kafka consumer with retry and DLT** requires more than a single annotation. The key parts are: a listener that lets errors propagate to the container; a retry/backoff policy separating transient from non-retryable errors; a recoverer that routes unprocessable records to a DLT; offset/ack policies consistent with recovery; and an **idempotent** business handler able to withstand redeliveries after commit failures or rebalances.

For workloads requiring per-partition ordering, `DefaultErrorHandler` with blocking retries is a straightforward starting point. When you cannot afford to block a source partition for a long-failing record, `@RetryableTopic` may be a better fit, though it demands careful management of retry topics, offsets, and ordering. Regardless of the model, **the DLT is a quarantine area that must be actively operated**, not proof that business processing succeeded.

Verify via integration tests across all scenarios: retry success, retry exhaustion, payload errors, DLT publish failures, and consumer crashes between DB commit and offset commit; alongside dashboards, alerts, and controlled replay runbooks. With those pieces in place, the system can survive temporary outages, avoid silently dropping problematic records, and preserve accurate business outcomes across retries and rebalances.
