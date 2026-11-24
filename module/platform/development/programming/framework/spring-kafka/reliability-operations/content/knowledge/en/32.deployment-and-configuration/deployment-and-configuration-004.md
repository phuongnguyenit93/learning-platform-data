# Configuring Listener Container Factories in Spring Kafka

## 1. Context: Why the Listener Container Factory Determines Reliability

In Spring Kafka, a method annotated with `@KafkaListener` looks deceptively simple:

```java
@KafkaListener(topics = "orders.events")
public void onOrder(String payload) {
    process(payload);
}
```

Behind that method, however, sits a **listener container** responsible for creating Kafka consumers, calling `poll()`, dispatching records to the method, handling exceptions, managing consumer groups/rebalances, committing offsets, and starting/stopping properly with the application lifecycle. If the factory is misconfigured, business code may appear to "work" in test environments while causing data loss, duplicate processing, consumer lag, continuous rebalancing, or silently skipping poison messages when deployed across multiple replicas.

**Configuring listener container factories** belongs to the *Deployment and Configuration* chapter of *Spring Kafka Reliability Operations*. This lesson focuses on how to choose and configure `ConcurrentKafkaListenerContainerFactory` for a service built for durable operations.

After this lesson, you will be able to:

- Distinguish `ConsumerFactory`, `KafkaListenerContainerFactory`, `ConcurrentMessageListenerContainer`, and `@KafkaListener`.
- Use Spring Boot auto-configuration or define multiple factories per workload type.
- Choose `AckMode`, concurrency, poll timeout, idle events, and consumer properties on a sound basis.
- Combine `DefaultErrorHandler`, backoff, `DeadLetterPublishingRecoverer`, and deserialization policies.
- Understand offset commits, at-least-once delivery, idempotency, transactions, retries, and the boundary between Kafka and databases.
- Configure record listeners and batch listeners without confusing their semantics.
- Control startup/pause/resume, and observe consumer lag, rebalances, and non-responsive consumers.
- Test factories with broker integration tests and deploy multiple replicas safely.

Java examples target **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x**. With Boot 4/Spring Kafka 4, certain Spring Boot auto-configuration packages and APIs may change; always check against your actual version rather than copying imports across major framework generations.

---

## 2. Four Configuration Layers to Distinguish

```text
application.yml / environment / secrets
                 │
                 ▼
          ConsumerFactory<K, V>
       ├── bootstrap servers
       ├── group ID / client ID
       ├── key/value deserializer
       ├── max.poll.records / interval
       ├── isolation level
       └── TLS / SASL / other consumer configs
                 │
                 ▼
  ConcurrentKafkaListenerContainerFactory<K, V>
       ├── concurrency
       ├── batchListener
       ├── CommonErrorHandler
       ├── record/message converter
       ├── record filter/interceptor
       └── ContainerProperties template
              ├── AckMode
              ├── pollTimeout
              ├── idleEventInterval
              ├── autoStartup
              ├── observationEnabled
              └── lifecycle / commit controls
                 │
                 ▼  container created for each endpoint
      ConcurrentMessageListenerContainer
                 │
            N child containers
                 │
            KafkaConsumer.poll()
                 │
                 ▼
     @KafkaListener application method
                 │
       success / throw exception
                 │
                 ▼
       commit / retry / DLT / seek
```

### 2.1. `ConsumerFactory`: Defines How `KafkaConsumer` Instances Are Created

`ConsumerFactory<K,V>` manages the configuration used when instantiating a `KafkaConsumer`, such as:

- `bootstrap.servers`, `group.id`, `client.id`.
- `key.deserializer` and `value.deserializer`.
- `enable.auto.commit`, `auto.offset.reset`.
- `max.poll.records`, `max.poll.interval.ms`.
- `session.timeout.ms`, `heartbeat.interval.ms` if needed.
- `isolation.level=read_committed` when reading only committed transactional records.
- Security: `security.protocol`, SASL, SSL.

**A `ConsumerFactory` is not a single `KafkaConsumer` shared across threads.** A concurrent listener container creates child consumers; `KafkaConsumer` must not be accessed concurrently by arbitrary threads.

### 2.2. Listener Container Factory: Template for Creating Containers

`ConcurrentKafkaListenerContainerFactory` is a **factory bean**, not a running consumer thread. It provides a configuration template; when Spring processes `@KafkaListener`, each endpoint gets a corresponding container built from that factory.

Implications:

- Two listeners sharing one factory can still have **two independent listener containers**, each with multiple child consumers.
- `setConcurrency(3)` applies per container created by the factory, not as a cap of three consumers for the entire application.
- Mutating the factory object after containers are initialized should not be treated as a way to reconfigure running consumers at runtime; configure before endpoints are created or use proper runtime APIs.
- To tune just one listener, consider `@KafkaListener(concurrency=...)` or a dedicated factory rather than altering the global default.

### 2.3. `KafkaListenerEndpointRegistry`: Managing Created Listeners

Containers created from `@KafkaListener` are registered in `KafkaListenerEndpointRegistry`. The registry provides lookup by listener ID to inspect, start, stop, pause, and resume containers as supported.

The registry is not where initial consumer properties are configured. It primarily provides **lifecycle control** over existing listeners.

### 2.4. Listener: Where Business Logic Lives

`@KafkaListener` should focus on:

1. Decoding/validating the event against its schema.
2. Invoking a domain service with controlled transactions/idempotency.
3. Completing cleanly or throwing a classified exception.
4. Never swallowing exceptions when container retry/DLT handling is expected.

Do not embed `while(true)` loops or call `consumer.poll()` directly inside a listener. The container already manages polling, group membership, and offsets.

---

## 3. Decision: Spring Boot Auto-Configuration or Custom Factory?

Spring Boot provides Kafka auto-configuration under `spring.kafka.*`. If an application needs only one listener style, you typically **do not** need to declare `ConcurrentKafkaListenerContainerFactory` manually: Boot creates a default bean named `kafkaListenerContainerFactory` from config and related beans.

### 3.1. Default Configuration via `application.yml`

Example for a typical record listener:

```yaml
spring:
  kafka:
    bootstrap-servers: "localhost:9092"
    consumer:
      group-id: "orders-worker"
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
    listener:
      type: single
      ack-mode: record
      concurrency: 3
      poll-timeout: 2s
      auto-startup: true
      missing-topics-fatal: true
```

Meaning:

- `type: single` uses a record listener rather than passing the entire poll batch into the method.
- `ack-mode: record` commits offsets after the listener processes each record successfully per container policy, when consumer auto-commit is disabled.
- `concurrency: 3` creates up to three child consumers **per listener container**.
- `poll-timeout: 2s` bounds how long `poll()` waits for records, **not** how long the business method may run.
- `missing-topics-fatal: true` fails fast when required configured topics do not exist yet; detection and applicability are limited with subscription patterns.
- `auto-offset-reset: earliest` applies only when **no valid committed offset exists** for the group/partition (or when offsets go out of range), never forcing a group with existing offsets to replay from the start.
- `max-poll-records: 200` caps records returned per poll, not concurrency.
- `enable-auto-commit: false` delegates offset commits to the container, preventing Kafka from committing on a timer before business processing completes.

This is a sample policy, not a universal production preset for all workloads. `earliest` can cause a brand-new consumer group to read a huge backlog; verify scope and retention.

### 3.2. When Should You Declare a Custom Factory?

Custom factories are needed when:

- The same app has both **record listeners** and **batch listeners** with different thresholds.
- One topic group requires `AckMode.RECORD` while another requires `MANUAL_IMMEDIATE`.
- One group needs dedicated DLT/retries while another fails fast.
- One group needs concurrency 1 to conserve resources or preserve per-partition sequential processing.
- Separate message converters, record filters, or interceptors are needed.
- Different container-level metrics/observations/events are required.
- Startup must be controlled by feature flags or operational workflows.
- Consumer groups use different deserializers, credentials, or bootstrap clusters.

**One factory is not the sole place Kafka is configured.** If two groups use two brokers or two schemas/value deserializers, you generally need **two `ConsumerFactory` beans**, not just two listener container factories sharing one consumer factory.

### 3.3. Using the Boot Configurer to Preserve the Baseline

In Spring Boot 3.4.x, `ConcurrentKafkaListenerContainerFactoryConfigurer` is located at:

```java
import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
```

When building a custom factory, using the configurer inherits settings Boot already bound from `spring.kafka.*` and auto-wired beans. You then override **only** the differences for that listener group.

This is safer than constructing a factory from scratch and forgetting converters, transaction managers, error handlers, observations, or consumer configs that Boot previously wired.

**Version note:** in Spring Boot 4, the configurer class lives under a different Kafka auto-configuration package namespace. Do not copy Boot 4 imports into a Boot 3 project.

---

## 4. Complete Example: Record Listener with Retries and Dead Letter Topic

### 4.1. Hypothetical Business Requirements

Service `orders-service` reads topic `orders.events`:

- Key: order ID as a `String`.
- Value: JSON as a `String`, e.g. `{"eventId":"evt-201","orderId":201,"status":"PAID"}`.
- Main topic has **3 partitions**.
- Consumer group `orders-worker`, initially deployed as one instance with concurrency 3.
- Invalid business validation → no retries, route to DLT.
- Transient database failure → retry 2 times, 1 second apart.
- Retries exhausted → publish to DLT, and advance only if DLT publish succeeds.
- DLT named `orders.events.DLT`, with at least 3 partitions since the example preserves the source partition.
- Database side effects must be idempotent because Kafka offsets and DB commits do not share an atomic transaction by default.

### 4.2. Dependencies

Gradle example for Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

If business logic writes to a DB, add `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa` plus the appropriate JDBC driver. Never embed credentials in source code.

### 4.3. YAML Separating Infra Config and Business Names

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}"
    consumer:
      group-id: "orders-worker"
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
    listener:
      type: single
      ack-mode: record
      auto-startup: true
      poll-timeout: 2s

app:
  kafka:
    orders:
      topic: "orders.events"
      group-id: "orders-worker"
      concurrency: 3
```

With String deserializer/serializer, the example stays simple and invalid JSON is caught inside the listener. If using a typed `JsonDeserializer<OrderEvent>`, errors can occur **before entering the listener**; use `ErrorHandlingDeserializer` and a DLT producer capable of serializing failed raw payloads (see Section 10).

`acks: all` and an idempotent Kafka producer strengthen **publishing to Kafka**, but do not create exactly-once database side effects.

### 4.4. Classified Exceptions

Placed in `com.example.kafka.orders`:

```java
package com.example.kafka.orders;

public final class OrderExceptions {

    private OrderExceptions() {}

    public static class InvalidOrderEventException
            extends RuntimeException {
        public InvalidOrderEventException(String message) {
            super(message);
        }
        public InvalidOrderEventException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class TemporaryStorageException
            extends RuntimeException {
        public TemporaryStorageException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

In real applications, never catch arbitrary `RuntimeException`s and wrap them as `TemporaryStorageException`. Mapping bugs or security errors must not be retried just because they share a superclass; use an accurate classifier.

### 4.5. Configuring the Factory and Error Handler

```java
package com.example.kafka.orders;

import java.time.Duration;

import org.apache.kafka.common.TopicPartition;

import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;

import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;

import org.springframework.util.backoff.FixedBackOff;

import com.example.kafka.orders.OrderExceptions
        .InvalidOrderEventException;

@Configuration(proxyBeanMethods = false)
public class OrdersListenerConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, exception) ->
                                new TopicPartition(
                                        record.topic() + ".DLT",
                                        record.partition()));

        // Do not skip failed records when DLT publishing fails.
        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(
                Duration.ofSeconds(20));

        // 2 retries, up to 3 total delivery attempts.
        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1000L, 2L));

        handler.addNotRetryableExceptions(
                InvalidOrderEventException.class);

        return handler;
    }

    @Bean("ordersListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    ordersListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory,
            DefaultErrorHandler ordersErrorHandler,
            @Value("${app.kafka.orders.concurrency:3}")
                    int concurrency) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <Object, Object>();

        // Inherit baseline configuration from Spring Boot.
        configurer.configure(factory, consumerFactory);

        factory.setBatchListener(false);
        factory.setConcurrency(concurrency);
        factory.setCommonErrorHandler(ordersErrorHandler);

        ContainerProperties props =
                factory.getContainerProperties();

        props.setAckMode(ContainerProperties.AckMode.RECORD);
        props.setPollTimeout(2000L);
        props.setIdleEventInterval(60_000L);
        props.setObservationEnabled(true);
        props.setMissingTopicsFatal(true);
        props.setLogContainerConfig(true);

        return factory;
    }
}
```

**Points to read carefully:**

- The factory bean is named **`ordersListenerContainerFactory`**. The listener must explicitly set `containerFactory="ordersListenerContainerFactory"`.
- `configurer.configure(...)` applies Boot-configured defaults, and the code then overrides batch mode, concurrency, ack mode, and error handler.
- `ContainerProperties` is a **template for containers built by the factory**, not a shared object directly operating `KafkaConsumer` instances.
- `FixedBackOff(1000L, 2L)` means **two retries after the initial attempt**, normally up to three delivery attempts total. Do not mistake argument `2` for "two total calls."
- `InvalidOrderEventException` is marked non-retryable, so the recoverer runs immediately when that error occurs.
- If the DLT topic lacks partition `record.partition()`, publishing fails. Thus the DLT must have at least as many partitions as the source topic when using this resolver.
- `setFailIfSendResultIsError(true)` makes the recoverer verify the DLT publish result, reducing the risk of treating recovery as successful when the send actually failed.
- `setObservationEnabled(true)` requires a configured Micrometer Observation/registry to emit useful metrics/traces. It does not automatically create dashboards or alerts.
- `setMissingTopicsFatal(true)` suits pre-provisioned mandatory topics; environments with dynamic topic creation require careful evaluation.
- A single `DefaultErrorHandler` bean may also be picked up by Boot for another auto-configured factory. If multiple factories need different policies, configure each explicitly, verify auto-wiring, and avoid unintentionally sharing one error handler.

In the demo, the DLT Kafka producer uses `StringSerializer` because input uses `StringDeserializer`. For records failing deserialization whose raw value is `byte[]`, use a compatible producer serializer to send raw bytes to the DLT.

### 4.6. Record-by-Record Listener

```java
package com.example.kafka.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import com.example.kafka.orders.OrderExceptions
        .InvalidOrderEventException;

@Component
public class OrdersListener {

    private final ObjectMapper mapper;
    private final OrderProcessingService service;

    public OrdersListener(
            ObjectMapper mapper,
            OrderProcessingService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            id = "orders-v1",
            topics = "${app.kafka.orders.topic}",
            groupId = "${app.kafka.orders.group-id}",
            containerFactory = "ordersListenerContainerFactory")
    public void handle(ConsumerRecord<String, String> record) {

        JsonNode event;
        try {
            event = mapper.readTree(record.value());
        } catch (JsonProcessingException invalidJson) {
            throw new InvalidOrderEventException(
                    "INVALID_JSON", invalidJson);
        }

        if (event == null
                || !event.hasNonNull("eventId")
                || !event.hasNonNull("orderId")
                || !event.get("orderId").isIntegralNumber()
                || !event.hasNonNull("status")) {
            throw new InvalidOrderEventException(
                    "MISSING_OR_INVALID_FIELDS");
        }

        String eventId = event.get("eventId").asText();
        long orderId = event.get("orderId").asLong();
        String status = event.get("status").asText();

        if (eventId.isBlank()
                || orderId <= 0
                || status.isBlank()) {
            throw new InvalidOrderEventException(
                    "INVALID_VALUES");
        }

        // Service must handle idempotency where durable state resides.
        service.process(
                eventId,
                orderId,
                status,
                record.topic(),
                record.partition(),
                record.offset());

        // Return only after durable processing succeeds.
        // Container decides commit per AckMode.RECORD.
    }
}
```

Business interface:

```java
package com.example.kafka.orders;

public interface OrderProcessingService {

    void process(
            String eventId,
            long orderId,
            String status,
            String topic,
            int partition,
            long offset);
}
```

The example leaves `OrderProcessingService` unimplemented because persistence depends on your business DB; Section 12 illustrates idempotency. The essential rule for container config: **the listener must throw an error when processing did not succeed**. Catching exceptions, logging, and returning normally lets the container commit the offset and loses retry/DLT handling.

---

## 5. `AckMode`: Deciding When Offsets Are Committed

A Kafka consumer reads a record at an offset. After the application processes it, the container can commit the next offset to the Kafka consumer group. If processing succeeds but the process crashes **before the offset commits**, the record can be redelivered.

Kafka does not automatically guarantee "every business side effect happens once" when writing to databases, emails, or HTTP services.

### 5.1. Primary Modes

| AckMode | When the Container Commits | Notes |
|---|---|---|
| `RECORD` | After each record is processed successfully by the listener | Easy to reason about, more frequent commits, fits per-record processing |
| `BATCH` | After processing all records returned by one `poll()` | Default container ack mode; **does not require a batch listener method** |
| `TIME` | Once the time interval elapses and eligible records finish | Higher commit lag possible; must account for `pollTimeout` |
| `COUNT` | After at least the configured number of records | Larger replay window after a crash |
| `COUNT_TIME` | Whichever count or time threshold triggers first | Tunes commit overhead to traffic |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; committed per container rules | Must understand ack queuing and commit timing |
| `MANUAL_IMMEDIATE` | Ack on the consumer thread can commit immediately | Must stay consistent on thread/context; never mix irregular acks |

These modes assume `enable.auto.commit=false` and no transactional container altering how offsets are sent.

### 5.2. Do Not Confuse `AckMode.BATCH` with a Batch Listener

These are **two orthogonal axes**:

- `factory.setBatchListener(true)`: the method receives **a list of records per invocation**.
- `AckMode.BATCH`: **when offsets are committed** after processing the records from one `poll()`.

You can have **a record listener + `AckMode.BATCH`**: the container invokes the method once per record, then commits offsets after finishing the poll batch. That is common in many default setups.

Conversely, a batch listener can use supported ack modes as appropriate. However, error handling, partial batch commits, and transaction semantics must be verified against version docs rather than assuming flipping one flag is enough.

### 5.3. Manual Ack in a Dedicated Factory

When a listener group wants explicit acks after durable persistence:

```java
@Bean("manualAckListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
manualAckListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <Object, Object>();

    configurer.configure(factory, consumerFactory);

    factory.setConcurrency(1);
    factory.setBatchListener(false);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE);

    return factory;
}
```

Listener:

```java
@KafkaListener(
        id = "accounting-v1",
        topics = "accounting.events",
        groupId = "accounting-worker",
        containerFactory = "manualAckListenerContainerFactory")
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    accountingService.persistIdempotently(
            record.key(), record.value());

    acknowledgment.acknowledge();
}
```

Import:

```java
import org.springframework.kafka.support.Acknowledgment;
```

**Never call `acknowledge()` inside `finally`**: if the service throws and the offset is still acked, the message can be treated as processed and lost.

With `MANUAL_IMMEDIATE`, acking on the listener/consumer thread has different semantics than acking from another thread. Do not use async callbacks without understanding `asyncAcks`, offset gaps, pausing, and duplicate risks. Manual ack does not create DB/Kafka exactly-once.

### 5.4. When to Choose `RECORD` Over `MANUAL`?

- **`RECORD`:** synchronous method completing when side effects are durable; usually easier to maintain.
- **`MANUAL`:** the app genuinely needs ack control, such as synchronous handoff to a durable store followed by contractual acking.
- **`MANUAL_IMMEDIATE`:** immediate commit upon ack on the consumer thread, understanding the trade-offs.
- **`BATCH`/`COUNT`/`TIME`:** optimizing throughput and commit overhead while accepting a wider redelivery window.

Never pick `MANUAL` simply because it sounds "safer"; many production bugs stem from forgotten acks, premature acks, or acking from the wrong thread.

---

## 6. Concurrency and Partition Count

### 6.1. Capacity Formula

For a consumer group deployed across multiple pods:

```text
Total child consumers ≈
    replica count × concurrency of each listener container

Active consumers receiving data ≤ available partition count
    (for one topic in the same group, per assignment)
```

Example for a topic `orders.events` with 6 partitions:

| Replicas | Concurrency per replica | Total child consumers | Max active for 6-partition topic |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 1 | 3 | 3 | 3 |
| 2 | 3 | 6 | 6 |
| 3 | 3 | 9 | 6; remaining consumers may sit idle |
| 6 | 2 | 12 | 6; adding consumers does not increase throughput |

These idealized numbers assume one listener/group and one 6-partition topic. With multi-topic subscriptions and different partition assignors, active consumer distribution is more complex.

### 6.2. Ordering

Kafka guarantees order **within a single partition**, not across the whole topic. If order events for the same `orderId` must stay ordered, the producer should use a stable key so events for the same aggregate land in the same partition given stable partitioning config.

Increasing concurrency never causes two consumers in the same group to process the same partition concurrently. If business logic offloads records from the listener onto a thread pool without managing ordering/acks, you can break ordering yourself even while Kafka preserves log order.

### 6.3. Concurrency Does Not Change `group.id`

`group.id` determines which consumers share partitions and committed offsets. If two apps share a group ID, they divide the work; if they use distinct group IDs, each group receives its own stream.

`@KafkaListener(id="...")` can act as the group ID in certain cases when `groupId` is omitted (per annotation semantics). To avoid surprises when renaming a listener ID, declare `groupId` explicitly.

### 6.4. Multi-Topic Subscriptions and Assignors

When one group subscribes to multiple topics with differing partition counts, the default partition assignor may distribute assignments unexpectedly. Observe **actual partition assignments** before finalizing concurrency.

You can select an assignor via Kafka client config, for example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: >-
          org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Verify compatibility with your broker/client, existing consumer group, and rolling deployment workflow. Changing the assignor on a live group requires planning for rebalances; never switch it during peak traffic.

### 6.5. Do Not Raise Concurrency Just to "Fix Lag"

Consumer lag can also stem from:

- Slow DB/HTTP dependencies.
- Skewed record processing; one partition holds far more records.
- Continuous retry loops on one partition.
- GC pauses, CPU throttling, exhausted connection pools.
- `max.poll.records` set too high relative to processing time.
- Producer key skew overheating one partition.
- Blocked DLT publishing or transactions.

Adding consumer threads can slow the DB further or trigger rebalances when pods exhaust CPU. Identify the bottleneck before scaling.

---

## 7. Consumer Poll: `max.poll.records` and `max.poll.interval.ms`

### 7.1. A Poll Is Neither a Chunk Nor a Transaction

`KafkaConsumer.poll()` fetches a batch of records from the broker. For a record listener, the container invokes the listener repeatedly across that batch before the next poll.

Two key properties:

- `max.poll.records`: maximum records returned in one poll.
- `max.poll.interval.ms`: maximum elapsed time between valid polls before the consumer is considered stalled and removed from the group per client/broker rules.

If processing 500 records at 2 seconds each on one consumer thread takes ~1,000 seconds, it exceeds `max.poll.interval.ms=300000` (5 minutes). The consumer can lose its assignment and trigger a rebalance, causing duplicate deliveries and erratic lag.

### 7.2. Mental Formula

```text
Worst-case processing time per poll ≈
    max.poll.records × p99 processing time per record
  + retry/backoff overhead
  + scheduling/GC/I/O overhead
```

This is a conservative bound; actual returned records may be fewer, and processing times vary. In production, **measure p99 and outliers** rather than average latency alone.

Example:

```text
max.poll.records = 100
p99 business processing = 1.5 seconds
retry/outlier budget = 60 seconds
--------------------------------
estimated worst-case ≈ 210 seconds
max.poll.interval.ms = 300 seconds
```

That leaves roughly 90 seconds of headroom under these assumptions. If a processor occasionally blocks on a 10-minute HTTP call, synchronous processing does not fit; use tighter timeouts, circuit breakers, smaller poll batches, or durable async handoffs.

### 7.3. `pollTimeout` Does Not Cap Business Method Duration

`factory.getContainerProperties().setPollTimeout(2000L)` only limits how long a single `KafkaConsumer.poll` waits for data (~2 seconds). It **does not** abort `handle(...)` after 2 seconds.

To bound business execution, configure JDBC/HTTP, transaction, deadline, or worker-protocol timeouts. Never treat `pollTimeout` as an "overall listener timeout."

### 7.4. `max.poll.records` Is Not Concurrency

`max.poll.records=100` does not spawn 100 threads. `concurrency=3` spawns up to three child consumers, each capable of fetching up to 100 records per poll. Working set size and DB request volume scale with consumer count.

### 7.5. `idleBetweenPolls` and Backpressure

`ContainerProperties.setIdleBetweenPolls(...)` adds a pause between polls, provided total processing plus idle time stays within `max.poll.interval.ms`. This is a simple throttle, **not a substitute** for proper rate limiters and backpressure when downstream quotas are strict.

---

## 8. Error Handling: Retries, Recovery, and Dead Letter Topic

### 8.1. Error-Handling Flow

```text
Kafka record
     │
     ▼
@KafkaListener
     │
     ├── succeeds
     │      └── container commits per AckMode
     │
     └── throws exception
              │
              ▼
       DefaultErrorHandler
              │
              ├── non-retryable error
              │     └── recoverer → DLT
              │
              └── retryable error
                    ├── retry 1
                    ├── retry 2
                    └── still failing
                          └── recoverer → DLT
                                      │
                             DLT publish succeeded?
                                ├── Yes → recovery completes,
                                │         offset may advance
                                └── No → signal error/redeliver
```

The flow above depicts the non-transactional record listener demo. Seek/redelivery, commits, and error handlers behave differently with transactional containers or batch listeners.

### 8.2. `DefaultErrorHandler` and `FixedBackOff`

`DefaultErrorHandler` supersedes legacy error handlers, enabling retries and routing to a recoverer once retries are exhausted.

`FixedBackOff(1000L,2L)`:

- Initial business call fails.
- First retry after 1 second.
- Second retry after 1 second.
- If still failing, the recoverer receives the record.

In tests, expect **3 total listener invocations** for a consistently failing retryable case under this policy (barring environment/transaction or handler exceptions). Non-retryable exceptions bypass those retries.

### 8.3. A DLT Is Not "Drop Record Without Alerting"

`DeadLetterPublishingRecoverer` preserves failed records in a separate topic for investigation/replay. Yet if DLT publishing fails and the container still considers recovery done, records risk being lost per offset policy.

That is why the demo enables `setFailIfSendResultIsError(true)`. Monitor producer errors, DLT topic availability, broker acks, and timeouts. For critical data, define DLT retention, ACLs, and replay workflows.

**A record moved to the DLT has not yet been processed by business logic.** Maintain triage, quarantine, replay, and impact-reporting procedures.

### 8.4. DLT Partition Count Must Match the Resolver

Spring Kafka's default resolver typically sends failed records to a `-dlt` suffixed topic at the **original partition**. The demo uses `.DLT` while keeping the partition:

```java
(record, exception) ->
        new TopicPartition(
                record.topic() + ".DLT",
                record.partition())
```

If the main topic has 6 partitions and the DLT has only 3, failures from partitions 4/5 cannot publish to the same partition index. You can customize the resolver to let Kafka partition by key (returning a negative partition per supported API), though you must reassess ordering and traceability. The simplest option is provisioning the DLT with enough partitions and testing the mapping.

### 8.5. Poison Pills and Deserialization Errors

Failures occurring **before the listener**—such as `JsonDeserializer` failing to parse JSON—can prevent the listener method from ever being invoked. Using a deserializer directly without a wrapper can cause repeated poll failures or container stops with no DLT record produced.

`ErrorHandlingDeserializer` is a Spring Kafka adapter that attaches deserialization failure info in headers so the container/error handler can process it. For record listeners, Spring Kafka integrates deserialization error routing; for batch listeners, inspect and handle per-record failures explicitly.

With typed deserializers, the DLT producer must support serializing **raw `byte[]` values** when recovering undecodable records. A producer configured solely with `StringSerializer`/`JsonSerializer` may fail to send an undecoded `byte[]`. Use `DelegatingByTypeSerializer` or dedicated templates.

### 8.6. Choosing Retryable Error Categories

| Error | Typical Policy | Rationale |
|---|---|---|
| Transient DB connection timeout | Bounded retry | Dependency may recover |
| HTTP 503/429 | Retry/backoff/rate limit | Avoid retry storms |
| JSON missing required fields | Immediate DLT | Retrying the same payload will not fix it |
| Unsupported schema version | DLT/quarantine, upgrade consumer | Requires code/schema change |
| Kafka auth/authorization error | Infra/security handling, do not DLT per record | Consumer cannot access broker/topic |
| Permanent business validation error | Immediate DLT or reject per contract | Data is invalid |
| `NullPointerException` bug | Alert and investigate; very cautious policy | Retries may mask bugs or add load |
| Prolonged Redis/DB outage | Stop/pause or circuit breaker | Infinite retries stall the group |
| DLT publish failure | Do not mark recovery succeeded | Must preserve record to retry recovery |

Application policy should classify exceptions by domain. Never blindly add `IllegalArgumentException.class` as non-retryable if underlying libraries also throw it for unrelated conditions.

---

## 9. Record Listener vs. Batch Listener: Which Factory Fits?

### 9.1. Record Listener

Configuration:

```java
factory.setBatchListener(false);
```

Method:

```java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "ordersListenerContainerFactory")
public void onRecord(ConsumerRecord<String, String> record) {
    orderService.process(record.key(), record.value());
}
```

Best when each record needs independent validation, retries, and DLT routing with clear tracking by topic/partition/offset.

### 9.2. Batch Listener

Separate factory configuration:

```java
@Bean("auditBatchContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
auditBatchContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <Object, Object>();

    configurer.configure(factory, consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Listener receiving multiple records:

```java
@KafkaListener(
        id = "audit-batch-v1",
        topics = "audit.events",
        groupId = "audit-batch-worker",
        containerFactory = "auditBatchContainerFactory")
public void onBatch(
        List<ConsumerRecord<String, String>> records) {

    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, String> record = records.get(i);

        try {
            auditService.store(record.value());
        } catch (RuntimeException e) {
            throw new BatchListenerFailedException(
                    "Audit item failed", e, i);
        }
    }
}
```

Imports:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;
```

### 9.3. Why Is `BatchListenerFailedException` Important?

In a batch listener, if the third item fails and the method throws a generic `RuntimeException`, the handler may not know which index failed and fall back to retrying the **entire batch**.

`BatchListenerFailedException` tells the handler the failing record/index so it handles related offsets per Spring Kafka semantics. Even so, business side effects for earlier items **still require idempotency** on retry/rebalance.

Never assume `BatchListenerFailedException` rolls back partial DB writes already committed outside a transaction. Especially for HTTP/email calls, already-executed items cannot automatically roll back.

### 9.4. Non-Blocking Retry with `@RetryableTopic`

`@RetryableTopic` offers an alternative: routing failed records across retry topics using timed backoff and then a DLT instead of blocking consumer threads. It introduces its own topic topology, auto-creation, and tooling considerations.

Things to know:

- Non-blocking retries can **alter ordering** among records on the same partition when a failed record moves to a retry topic.
- Standard retry-topic mechanics do not apply to batch listeners.
- Never stack retry topics alongside long `DefaultErrorHandler` retries without calculating total attempts and backoff.
- Restrictions apply with transactional containers and certain consumer/record types; verify version-specific docs.
- The factory still creates listener containers for main/retry/DLT endpoints as configured by the annotation infrastructure.

When strict ordering is required, consider blocking retries, partition pausing, or stateful sequential processing rather than immediately moving failed records to retry topics.

---

## 10. Deserialization and Message Converters

### 10.1. Three Data Conversion Layers May Appear

```text
Kafka bytes
    │
    ▼
Kafka Deserializer<K,V>
    │ String / byte[] / JSON object
    ▼
Spring RecordMessageConverter / BatchMessageConverter
    │ optional adaptation to listener signature
    ▼
@KafkaListener arguments
```

**Deserializer** is a Kafka consumer config such as `StringDeserializer` or `JsonDeserializer<OrderEvent>`. **MessageConverter** sits in Spring Kafka's adapter layer, adapting payloads to listener method parameters.

If a `JsonDeserializer` produces `OrderEvent` while the listener expects `String`, or an incompatible converter is wired, conversion fails before business logic runs.

### 10.2. String + Jackson Inside the Listener

The demo uses `StringDeserializer` and `ObjectMapper.readTree`:

- JSON errors convert cleanly into `InvalidOrderEventException` inside the method.
- Application-level DLT logic is straightforward to express.
- Account for parsing overhead and schema validation.
- This does not automatically establish a broker-side "typed deserialization contract"; producer and consumer still need explicit schema/versioning.

### 10.3. Typed JSON Deserializer

When using `JsonDeserializer<OrderEvent>`, configure trusted packages/target type and typically wrap with `ErrorHandlingDeserializer` so parse failures do not cause infinite poll loops. Never casually set `trusted.packages=*` for untrusted event sources; prefer an explicit allowlist of packages/domains.

Illustrative YAML layout (adapt target type and DLT serializer to your project):

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.orders.OrderEvent
        spring.json.trusted.packages: com.example.kafka.orders
```

If event classes use polymorphic types, assess deserialization security and trusted type headers carefully. Never let an untrusted producer dictate arbitrary Java class names for the consumer to instantiate.

### 10.4. The DLT Must Preserve Failure Evidence

When recovering deserialization failures, raw payloads may need to be sent to the DLT as byte arrays so operators can inspect the malformed record. Establish policies ensuring:

- The DLT producer can serialize the actual key/value types.
- The DLT topic has ACLs, retention, and encryption matching source data sensitivity.
- Exception headers/stack traces do not leak secrets or PII.
- Replay tooling enforces attempt limits, schema versions, and business idempotency.
- If DLT publishing fails, offsets are never committed as recovered.

---

## 11. Multiple Listener Container Factories in One Service

### 11.1. When Are Multiple Factories Needed?

Consider a microservice consuming:

- `orders.events`: per-record order processing, concurrency 3, short retry and DLT.
- `payments.events`: critical side effects, concurrency 1 per instance, `MANUAL_IMMEDIATE`, and reconciliation.
- `audit.events`: batch listener, group processing, and idempotent writer.

You can separate:

```text
ConsumerFactory (common broker/credentials)
       │
       ├─ ordersListenerContainerFactory
       │     RECORD, concurrency=3, DefaultErrorHandler + DLT
       │
       ├─ paymentsListenerContainerFactory
       │     MANUAL_IMMEDIATE, concurrency=1,
       │     payment-specific policy
       │
       └─ auditBatchContainerFactory
             batchListener=true, concurrency=2,
             batch-specific handling
```

Each listener selects its bean:

```java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "ordersListenerContainerFactory")
void orders(String value) { ... }

@KafkaListener(
        topics = "payments.events",
        containerFactory = "paymentsListenerContainerFactory")
void payments(String value, Acknowledgment acknowledgment) { ... }

@KafkaListener(
        topics = "audit.events",
        containerFactory = "auditBatchContainerFactory")
void audit(List<String> values) { ... }
```

### 11.2. Factories Do Not Automatically Split Consumer Groups

Two differently named factories **do not create two group IDs**. Consumer groups come from consumer factory properties and may be overridden via `@KafkaListener(groupId=...)`.

If listeners share a group ID and subscribe to the same topic, they **split** partitions rather than each receiving all records. When two independent features both need every event, assign distinct group IDs by contract.

### 11.3. Multiple Clusters, Multiple Credentials

If the payments group uses a different Kafka cluster or requires dedicated credentials:

- Define a separate `ConsumerFactory` for payments with the right bootstrap/security configs.
- Define a DLT `ProducerFactory`/`KafkaTemplate` targeting that cluster.
- Wire the payments container factory to the payments consumer factory.
- Do not pass Boot's configurer with the default consumer factory and accidentally keep pointing to the main cluster.
- Test connectivity and topic ACLs independently per group.

Client factories can share bootstrap settings, but never share mutable, non-thread-safe deserializer instances. Use standard config maps and supplier/consumer factory mechanisms.

### 11.4. Default Bean Name

If `@KafkaListener` omits `containerFactory`, it looks by default for a bean named `kafkaListenerContainerFactory` (unless the endpoint registrar is configured otherwise). If you define only `ordersListenerContainerFactory` and another method forgets `containerFactory`, it may pick Boot's default or fail startup depending on auto-configuration.

In services with multiple reliability policies, **explicitly declare `containerFactory` on every listener** and verify via integration tests.

---

## 12. Offsets, Transactions, and Idempotency

### 12.1. Default At-Least-Once Across Many Pipelines

A common flow:

```text
Kafka consume record
        │
        ▼
Write business DB
        │
        ▼
DB commit succeeds
        │
        ▼
Container commit Kafka offset
```

If the process crashes between the two commits, the record is redelivered even though the DB write succeeded. This is **at-least-once delivery**, meaning the application must tolerate redelivery.

Exactly-once DB side effects cannot be guaranteed merely by setting:

```java
props.setAckMode(ContainerProperties.AckMode.RECORD);
```

### 12.2. Idempotency in the Database

A PostgreSQL pattern:

```sql
CREATE TABLE processed_kafka_events (
    consumer_group VARCHAR(100) NOT NULL,
    event_id       VARCHAR(120) NOT NULL,
    topic_name     VARCHAR(255) NOT NULL,
    partition_id   INTEGER NOT NULL,
    offset_id      BIGINT NOT NULL,
    PRIMARY KEY (consumer_group, event_id)
);
```

Concept inside one **database transaction**:

```java
@Transactional
public void process(
        String eventId,
        long orderId,
        String newStatus,
        String topic,
        int partition,
        long offset) {

    int inserted = jdbc.update("""
            INSERT INTO processed_kafka_events
                (consumer_group, event_id,
                 topic_name, partition_id, offset_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (consumer_group, event_id) DO NOTHING
            """,
            "orders-worker", eventId,
            topic, partition, offset);

    if (inserted == 0) {
        return; // Already processed this eventId successfully before.
    }

    jdbc.update("""
            INSERT INTO order_status (order_id, status)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET status = EXCLUDED.status
            """,
            orderId, newStatus);
}
```

This is **illustrative PostgreSQL code**, requiring the `order_status` schema and an appropriate `JdbcTemplate` bean. Crucial condition: both the deduplication insert and the business write must occur **within the same DB transaction**. If you commit the "processed" marker first and the business write fails, redelivery will skip the record even though business state never updated.

### 12.3. Deduplicate by Offset or Business ID?

- `(topic, partition, offset)` identifies a specific record when Kafka redelivers the same offset.
- A business-stable `eventId` identifies duplicate event copies published by producers at different offsets.
- `orderId` alone is rarely enough because one order receives multiple valid events over time.

Choose deduplication keys by semantics: event ID, aggregate version, business transaction ID, or a verified combination. For versioned state updates, enforce ordering/version checks so older events never overwrite newer state even with deduplication active.

### 12.4. Kafka Transactions

When using Kafka transactions with `KafkaTransactionManager`, the container can include consumer offsets in the Kafka transaction and pair with Kafka writes to achieve exactly-once semantics **within Kafka read-process-write boundaries** under proper configuration.

However:

- Kafka transactions **do not atomically commit external databases outside Kafka**.
- With JDBC side effects, you still need idempotency/outbox/reconciliation or carefully engineered transaction coordination.
- In transactional containers, exceptions normally trigger rollbacks; error handling uses `AfterRollbackProcessor` per policy, unlike the non-transactional `DefaultErrorHandler` demo.
- Configuring a `CommonErrorHandler` on a transactional container that swallows exceptions risks preventing expected rollbacks.
- Consumer `isolation.level=read_committed` is essential to skip records from aborted producer transactions.

Never enable Kafka transactions just to "reduce duplicates" without understanding transaction IDs, producer fencing, transactional broker settings, and the error-handling model.

### 12.5. DLT Publishing and Source Offsets

In the demo, DLT recovery counts as handled once the record reaches the DLT. The source record's offset may then be committed per handler/container rules. Yet this is not "business processed"; the record is awaiting triage.

Where business obligations must never be dropped, maintain a DLT consumer/replay workflow, reconciliation, and alerts. If the DLT fails or retention expires before handling, data correctness still suffers.

---

## 13. Listener Container Lifecycle: Startup, Pause, Resume, Stop

### 13.1. `autoStartup`

`spring.kafka.listener.auto-startup=true` (or the factory property) starts listeners automatically with the Spring application lifecycle.

Use `autoStartup=false` when:

- Database migrations must complete before receiving records.
- Caches or reference data must warm up first.
- A feature is disabled in the current deployment environment.
- Operators want manual confirmation before running rollback/replay.

Remember that consumer lag continues accumulating while containers are stopped; monitor carefully to distinguish intentional pauses from outages.

### 13.2. Controlling via Registry

```java
import org.springframework.kafka.config
        .KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

@Service
public class ListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c == null) {
            throw new IllegalStateException("Missing orders listener");
        }
        c.pause();
    }

    public void resumeOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c == null) {
            throw new IllegalStateException("Missing orders listener");
        }
        c.resume();
    }

    public void stopOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c != null) {
            c.stop();
        }
    }

    public void startOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c != null) {
            c.start();
        }
    }
}
```

This assumes `@KafkaListener(id="orders-v1")` is registered. Control APIs must only be exposed to authenticated, authorized, audited administrative workflows—never expose an unauthenticated public endpoint that can halt consumers.

### 13.3. `pause()` Is Not `stop()`

| Operation | Meaning |
|---|---|
| `pause()` | Asks the container to pause record delivery/partitions while keeping poll/group mechanics per policy |
| `resume()` | Resumes delivery from a paused state |
| `stop()` | Stops the listener container, which can alter group membership |
| `start()` | Starts a stopped container |
| `autoStartup=false` | Prevents automatic startup during context initialization |

`pause()` fits short-term backpressure or maintenance. `stop()` fits when the service must not keep an active consumer. Both take effect asynchronously at poll boundaries; never assume returning from the method means all in-flight records stopped immediately.

### 13.4. Graceful Shutdown

When Kubernetes sends `SIGTERM`:

1. The application initiates Spring context shutdown.
2. Listener containers stop fetching new records and finish in-flight processing per policy.
3. Offset commits/transactions complete if processing succeeds and time permits.
4. Consumers leave the group or lose assignments; remaining replicas take over partitions.

Account for timing:

- Pod `terminationGracePeriodSeconds`.
- Container `shutdownTimeout`.
- Kafka consumer poll/processing duration.
- DB/HTTP timeouts.
- Retry backoff and DLT publish timeouts.

If a pod receives `SIGKILL` before committing offsets, records can be redelivered; side effects must be idempotent. Never raise termination grace periods indefinitely to hide buggy code.

---

## 14. Rebalances and Multi-Replica Deployments

### 14.1. When Do Rebalances Happen?

- Pods/instances start or stop.
- A consumer misses heartbeats or exceeds the poll interval.
- Topic partition counts change.
- Group membership or partition assignor changes.
- Broker/coordinator issues occur.
- Rolling deployments cause consumers to join/leave the group.

Rebalances are not always errors, yet excessive rebalancing reduces processing time and increases redeliveries.

### 14.2. Coordinating Poll Interval and Retries

If a listener blocks for 10 minutes on an HTTP call while `max.poll.interval.ms=5 minutes`, the consumer group can revoke its assignment. When the worker later attempts to commit offsets, it can fail or find another consumer already processed the record.

Choose:

- HTTP/DB timeouts shorter than actual SLAs.
- `max.poll.records` aligned with p99 processing time.
- `max.poll.interval.ms` with adequate headroom.
- Circuit breakers or fail-fast behavior during dependency outages.
- Error handlers/backoff that do not hold the consumer too long.
- Retry topics or durable async handoffs for extended outages where ordering permits.

### 14.3. Static Membership

Kafka supports `group.instance.id` for static group membership in environments controlling instance identity. It can reduce churn across brief restarts, provided IDs are **unique per consumer instance** and match concurrency/replica lifecycles. Never assign the same static `group.instance.id` to all pods; it risks fencing and group-join failures.

With Kubernetes pods whose identities churn, static membership requires careful evaluation and testing rather than being a mandatory default.

### 14.4. Rolling Deployments

A deployment plan:

1. Verify schema compatibility between old and new producer/consumer versions.
2. Check topic topology, partitions, ACLs, group ID, DLT, and metrics.
3. Launch one canary/new replica with proper resource limits.
4. Observe assignments, lag, rebalances, error rates, and throughput.
5. Roll out remaining replicas once stable.
6. Retain binary rollback capability without leaving new event schemas unreadable by the old version.

If the new consumer uses a different DLT policy, rollback must account for records already routed to the DLT; rolling back the binary will not automatically move those records back to the main topic.

---

## 15. Container-Level Observability and Monitoring

### 15.1. Key Signals

| Signal | Source | Question Answered |
|---|---|---|
| Consumer lag (records/time) | Broker/consumer group metrics | Is consumption keeping pace with producers? |
| Records consumed rate | Kafka client metrics | Are records still being consumed? |
| Processing latency p95/p99 | App/Micrometer observation | Where is the business method slow? |
| Retry attempts | `DefaultErrorHandler` retry listener/custom metrics | Are errors repeating heavily? |
| DLT publish success/failure | Producer/Recoverer metrics | Are failed records being preserved? |
| Rebalance frequency | Client logs/events/metrics | Are assignments stable? |
| Active consumer count | Container metrics/JMX | Does actual concurrency match intent? |
| Non-responsive consumer events | Spring Kafka container monitor | Is a poll thread stuck? |
| Listener container idle | `ListenerContainerIdleEvent` | Is it quiet when traffic is expected? |
| Commit latency/errors | Kafka consumer metrics/logs | Are offsets committing on time? |
| Container alive/started | Registry/health | Did a listener stop unexpectedly? |
| Dependency errors | DB/HTTP clients/traces | Is the bottleneck in Kafka or downstream? |

A consumer with zero lag does not automatically mean business processing succeeded: if the listener catches exceptions and returns, offsets still advance while DB writes were skipped.

### 15.2. Observation

Spring Kafka 3.x supports Micrometer Observation on listener containers. Enable it via:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

Ensure a proper registry, Actuator, and tracing backend are configured. Never attach business IDs or sensitive payloads as per-message metric tags/attributes; high cardinality inflates metric costs and risks data leaks.

### 15.3. Idle vs. Non-Responsive Are Different

- **Idle listener event:** the container received no records within the configured interval. This can be normal when a topic has no traffic.
- **Non-responsive consumer event:** the thread failed to return to the poll loop within an abnormal threshold per the monitor. Causes include blocking calls, GC, deadlocks, or processing stalls.
- **High consumer lag:** backlog sits in the broker without necessarily meaning the consumer is hung; throughput may simply be insufficient.

Illustrative configuration:

```java
ContainerProperties props = factory.getContainerProperties();
props.setIdleEventInterval(60_000L);
props.setPollTimeout(2000L);
props.setMonitorInterval(30);
props.setNoPollThreshold(3.0f);
```

`monitorInterval` is in seconds, while `pollTimeout` is in milliseconds. Tune event intervals and alerts to your traffic profile rather than treating every quiet period as an incident.

### 15.4. Application Event Listener

```java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listenerId={}, idleMs={}",
                event.getListenerId(), event.getIdleTime());
    }

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {
        log.warn(
                "Kafka consumer non-responsive: listenerId={}",
                event.getListenerId());
    }
}
```

Imports:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

**Do not treat events as an automatic recovery mechanism:** a blocked container requires root-cause diagnosis. Putting `stop/start` logic inside every event callback can trigger infinite rebalance loops.

### 15.5. Consumer Lag and Alerting

Reference policy examples:

- Warning when lag grows continuously for 10 minutes and consumption throughput trails input rate.
- Critical when estimated catch-up time exceeds the SLA deadline.
- Critical when a container stops unexpectedly.
- Critical when DLT publishing fails.
- Warning when DLT rate exceeds baseline or pending replay counts grow.
- Investigate when continuous rebalances occur or zero records are consumed despite active topic traffic.

Thresholds depend on workload; 10,000 lagging records is minor for trivial events yet severe at 1 second/event. Prioritize **lag time/ETA and business SLAs**, not raw lag counts alone.

---

## 16. Security and Secret Configuration

The factory requires a properly secured consumer factory. Skeleton example:

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS}"
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: "${KAFKA_SASL_JAAS_CONFIG}"
```

Values are illustrative; secret delivery may use workload identity, mounted secrets, Vault, or managed service credentials. Never commit passwords, keytabs, or private keys to Git, and never log JAAS configurations.

Production controls must verify:

- ACLs for topic consumption, group joining, and DLT production.
- TLS truststores/keystores and certificate rotation.
- Dedicated DLT permissions when failed payloads or exception headers contain sensitive data.
- Client/network policies permitting connections only to approved Kafka clusters.
- Authentication exception timeout/retry policies: bad permissions usually warrant alerts rather than infinite retries.
- Config masking when `logContainerConfig` is enabled; avoid printing secret-bearing properties to logs.
- Environment-namespaced group IDs so dev never shares a group with prod.
- Schema Registry security if using Avro/Protobuf.

### 16.1. Auth Exception Retry Interval

When configured, `ContainerProperties.authExceptionRetryInterval` allows the container to retry periodically after authentication/authorization exceptions. Leaving it `null` (default) typically treats such errors as fatal and stops the container.

Enable it only when credential/ACL workflows can recover transiently and clear alerting exists. If a password is permanently wrong, infinite retries accomplish nothing and obscure misconfiguration signals.

### 16.2. Missing Topics

`missingTopicsFatal=true` suits mandatory pre-provisioned topics. If your app creates per-tenant topics on demand or subscribes by pattern, behavior differs; adjust the policy so delayed topic creation does not cause crash-loops.

---

## 17. Testing Listener Container Factories

### 17.1. Configuration Unit Tests

Verify every property you explicitly set:

- Bean named `ordersListenerContainerFactory` exists.
- `batchListener=false`.
- `concurrency=3`.
- `AckMode.RECORD`.
- `pollTimeout=2000ms`.
- `CommonErrorHandler` is the orders handler.
- `observationEnabled=true` if required.
- Consumer config has `enable.auto.commit=false` and `StringDeserializer`.
- Payments policies are not accidentally applied to orders.

When using Boot's configurer, test inside a real Spring application context rather than calling `new OrdersListenerConfiguration()`, because property binding and auto-wiring are essential to behavior.

### 17.2. Spring Kafka EmbeddedKafka Integration Tests

`spring-kafka-test` provides `@EmbeddedKafka`. Skeleton:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 3,
        topics = {
                "orders.events",
                "orders.events.DLT"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class OrdersListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void containerIsRegistered() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-v1");

        assertNotNull(container);
    }
}
```

Reference imports:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
```

This skeleton only verifies container registration in the context. To test delivery, send real records, await asynchronous processing with a latch/Awaitility/eventually assertion, and query durable state. Never rely on `Thread.sleep(100)` and assume the broker finished processing.

### 17.3. Mandatory Reliability Tests

| Scenario | Expected Verification |
|---|---|
| Valid record | Business service invoked; offset advances after success |
| Invalid JSON/domain | No repeated retries; record published to DLT |
| Transient DB failure twice, then succeeds | Attempt count matches policy; nothing sent to DLT |
| DB fails permanently | Retries exhausted, DLT published, no record lost |
| DLT topic unavailable | Recovery fails; record is not marked processed |
| Crash after DB commit before offset commit | Redelivery produces no duplicate side effects |
| Consumer group changed | Offset and replay behavior follow new group |
| Concurrency exceeds partitions | No linear throughput gain; idle consumers may increase |
| Listener exceeds `max.poll.interval.ms` | Rebalance/redelivery detected and handled idempotently |
| Ack before business commit (negative test) | Demonstrates data-loss anti-pattern |
| Manual ack after durable commit | No ack when service throws |
| Batch listener fails on third record | `BatchListenerFailedException` pinpoints index; rest handled per policy |
| Typed deserializer failure | `ErrorHandlingDeserializer` + DLT serializer handle raw payload |
| Container pause/resume | Lag may grow while paused and drain after resume |
| SIGTERM/redeploy | Graceful shutdown, safe redelivery |
| Wrong auth/ACL | Container errors/stops per policy with alerts |

### 17.4. Testcontainers

For higher fidelity, use Kafka Testcontainers to run against a real containerized broker, paired with Postgres Testcontainers for DB idempotency tests. This exercises topic partitions, networking, and broker behavior closer to production.

Testcontainers does not replace staging load/rebalance tests, yet it catches bootstrap misconfigurations, topic provisioning issues, serializers, and producer/consumer interaction bugs early.

### 17.5. Do Not Mock `KafkaConsumer` with Mockito to Prove Offset Semantics

Mockito unit tests are great for mappers, business logic, and bean wiring. However, offset commits, partition assignments, rebalances, DLT recoverers, and Kafka transactions require broker-backed integration tests. A mock invoking `handle()` successfully does not prove the listener container committed offsets at the right moment.

---

## 18. Production Deployment Plan

### 18.1. Pre-Deploy

- Provision main topic and DLT with proper partition counts and retention.
- Configure consume and DLT produce ACLs; verify security credentials.
- Finalize group IDs per application and environment.
- Lock down consumer deserializers, message schemas, and compatibility.
- Size concurrency against total partitions, replicas, and DB/CPU capacity.
- Set `enable.auto.commit=false` when using container-managed commits.
- Select `AckMode` matching side-effect types and replay requirements.
- Verify `max.poll.records × processing latency` against `max.poll.interval.ms`.
- Define retry/backoff, exception classification, and DLT publish verification.
- Prepare the idempotency store and DLT replay runbook.
- Enable monitoring for lag, rebalances, error rates, and container health.

### 18.2. During Deploy

- Start a single canary/replica and verify topic assignments.
- Inspect child consumer count, concurrency, and active partitions.
- Verify deserializer/schema behavior on live messages.
- Watch lag trends, processing latency, DLT counts, and exceptions.
- Verify graceful shutdown as old pods terminate.
- If a retry storm or DB overload appears, pause/throttle/adjust policy deliberately.

### 18.3. Post-Deploy

- Inspect committed offsets and consumer lag per group.
- Confirm no unintended new group IDs appeared.
- Reconcile business record counts/side effects by ID, not just lag dashboards.
- Verify DLT retention/ACLs and replay tooling.
- Record factory configuration versions per deployment for incident evidence.
- Periodically rehearse broker failover, DB outages, pod crashes, and rebalances.

---

## 19. Configuration Troubleshooting Runbook

### 19.1. Listener Receives No Messages

Check in order:

1. Was `@KafkaListener` scanned by Spring and did the container start?
2. Does `containerFactory` match an existing bean name?
3. Does the topic exist and match the environment name?
4. Is the consumer group ID correct?
5. What committed offsets exist, and which `auto.offset.reset` applies?
6. Do partition assignments reach this listener, or is concurrency excessive?
7. Are ACLs/TLS/SASL working?
8. Is a deserializer throwing before the listener is invoked?
9. Is the container paused/stopped or stuck in continuous error retries?

Never change the group ID immediately just to "see messages": a new group starts with fresh offsets and may replay millions of records or skip history depending on `auto.offset.reset`.

### 19.2. High Lag Despite Increasing Concurrency

- Compare total child consumers against partition counts.
- Check for a hot partition caused by producer key skew.
- Inspect DB/API latency and connection pools.
- Check `max.poll.interval.ms`, rebalances, and retries.
- Check CPU throttling, GC pauses, and network bottlenecks.
- Measure actual per-partition throughput and evaluate adding partitions carefully (accounting for key routing/ordering impacts).

If a topic has only three partitions, scaling from three to nine consumers in the same group will not triple throughput.

### 19.3. Duplicate Business Writes

- Identify topic/partition/offset and `eventId`.
- Compare DB commit timestamps with Kafka offset commits.
- Check for pod crashes, rebalances, or consumer group changes.
- Verify idempotency transactions/keys.
- If records have different offsets but identical `eventId`, investigate producer duplicates.
- Fix business deduplication/versioning rather than merely switching `AckMode`.

### 19.4. Poison Message Looping Infinitely

- Determine whether failure happens in the deserializer, converter, or listener.
- Check `ErrorHandlingDeserializer` for pre-listener errors.
- Review `DefaultErrorHandler`, non-retryable classification, and backoff.
- Verify the DLT topic has enough partitions and proper ACLs.
- Enable DLT send verification and inspect producer errors.
- Avoid infinite retries on permanent validation errors.
- Replay only after fixing the root cause to avoid DLT → main → DLT loops.

### 19.5. Consumer Rebalancing Continuously

- Compare processing duration against `max.poll.interval.ms`.
- Measure GC pauses, CPU throttling, and container restarts.
- Check rolling deploy replica churn.
- Review partition assignor and group membership.
- Confirm no unintended duplicate deployments share the same group ID.
- Inspect network/broker coordinator/heartbeat logs.

### 19.6. DLT Has No Messages Despite Listener Failures

- Not every error routes to DLT: the method may be swallowing exceptions.
- Another error handler may be attached to the actual factory.
- The listener may be transactional with a different after-rollback policy.
- DLT topic name, partition count, or ACLs may be wrong.
- The producer serializer may fail to serialize raw `byte[]` from deserialization errors.
- DLT sending may fail; without send verification, signals can mislead.
- Check logs, retry counts, and offset behavior before drawing conclusions.

---

## 20. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating a custom factory and forgetting `setConsumerFactory` | Listener fails to build consumers | Use Boot configurer or wire `ConsumerFactory` explicitly |
| Creating a new factory and discarding Boot configuration | Loses converters/error handlers/observation | Call `configurer.configure(...)` first, then override |
| Wrong bean name in `containerFactory` | Listener uses wrong default policy or fails startup | Specify and test bean names |
| Confusing `AckMode.BATCH` with `setBatchListener(true)` | Misunderstands listener invocation counts and retries | Separate ack timing from payload delivery mode |
| Setting `enable.auto.commit=true` and trusting `AckMode` to protect side effects | Offsets commit before business success | Let the container manage offset commits |
| Choosing `MANUAL` and forgetting to call ack | Unexpected redeliveries/lag | Ack after durable success and test |
| Acking inside `finally` | Failed records are lost because offsets advance | Never ack on business failure |
| `concurrency=12` on a 3-partition topic | Idle consumers wasting resources | Size to partitions × replicas |
| Sharing a group ID across two features wanting independent reads | Features split partitions and miss events | Use separate group IDs per feature |
| Raising `pollTimeout` to cap business method time | No effect on processing duration | Use separate HTTP/DB/transaction timeouts |
| `max.poll.records` too large for processing speed | Exceeds poll interval, triggers rebalances | Reduce poll batch and optimize processing |
| Retrying every exception | Poison pills never drain | Classify permanent vs. transient errors |
| Infinite retries during dependency outage | Lag balloons with no recovery strategy | Bounded retries, circuit breaker/DLT/pause |
| DLT missing required partitions | Recoverer fails to publish | Provision sufficient partitions or change resolver |
| Not verifying DLT publish results | Recovery looks successful while DLT failed | `setFailIfSendResultIsError(true)` |
| Wrong DLT producer serializer | Cannot send raw bytes of failed records | Use template/serializer matching payload types |
| Changing group ID to "reset offsets" | Unintended history replay or data skip | Manage offsets and backfills intentionally |
| Assuming `AckMode.RECORD` yields DB exactly-once | Crash after DB commit causes redelivery | Idempotent business transactions |
| Enabling transactions while swallowing errors | Transactions may fail to roll back | Transaction-aware error handling |
| Watching only `consumer lag=0` | Business writes may be silently skipped | Reconcile side effects and DLT |
| Missing DLT produce permissions | Poison messages fail recovery | Verify ACLs/retention/topic provisioning |
| Changing assignor mid-deploy without testing | Unexpected rebalances/assignments | Rolling plan and integration tests |
| Logging full error payloads/headers | Leaks PII/secrets, bloats logs | Structured metadata and masking |

---

## 21. Hands-On Exercises

### Exercise 1 — Auto-Configured Default Factory

Bootstrap a Spring Boot project with a three-partition topic `events.demo`. Use YAML alone to set group ID, `AckMode.RECORD`, concurrency 2, and `enable.auto.commit=false`. Verify Spring Boot creates the default factory and the listener runs without declaring `containerFactory`.

### Exercise 2 — Dedicated Factory

Create `criticalContainerFactory` with concurrency 1, `AckMode.MANUAL_IMMEDIATE`, and a custom error handler. Have another listener use `ordersListenerContainerFactory`. Swap the `containerFactory` annotation and observe behavioral and offset-commit differences.

### Exercise 3 — Concurrency and Partitions

With a four-partition topic, run one replica at concurrency 1, 2, 4, and 8. Then run two replicas at concurrency 2. Record actual partition assignments, idle consumers, and throughput. Explain why going from 4 to 8 threads does not automatically speed up processing.

### Exercise 4 — Blocking Retries

Create a listener that throws `TemporaryStorageException` twice before succeeding. Use `FixedBackOff(1000,2)`. Test invocation counts, delay between attempts, and confirm nothing enters the DLT.

### Exercise 5 — DLT

Send a JSON record missing `orderId`. Configure `addNotRetryableExceptions(InvalidOrderEventException.class)`; verify the record enters the DLT immediately with original topic/partition/offset metadata and is not treated as business success.

### Exercise 6 — DLT Failure

Delete the DLT topic or block produce ACLs in a test environment. Enable send result verification. Observe that the handler does not mark recovery succeeded and check how the record is redelivered. Never run destructive ACL tests in production.

### Exercise 7 — Ack Timing

Configure `MANUAL_IMMEDIATE` with a DB-writing callback. Intentionally ack **before** DB commit to observe the event-loss window. Fix it to ack after the durable transaction and add idempotency for redeliveries.

### Exercise 8 — `max.poll.interval.ms`

Simulate 2-second per-record processing with `max.poll.records=200` and `max.poll.interval.ms=300000`. Observe rebalances/lag. Lower `max.poll.records`, add timeouts, and re-measure.

### Exercise 9 — Batch Listener

Switch the audit listener to `setBatchListener(true)`, accept `List<ConsumerRecord<String,String>>`, and throw `BatchListenerFailedException` at index 2 (the third record). Verify the handler processes prior, failing, and subsequent records per policy.

### Exercise 10 — Deserialization Poison Pill

Switch to typed `JsonDeserializer<OrderEvent>` with `ErrorHandlingDeserializer`. Send malformed JSON, verify the DLT receives the raw payload in a supported serializer format, and ensure the consumer does not stall indefinitely.

### Exercise 11 — Multi-Replica and Graceful Shutdown

Run three pods with concurrency 2 on a six-partition topic. Rolling-restart one pod and measure group rebalances, lag, duplicate deliveries, and shutdown time. Verify business idempotency.

### Exercise 12 — Observability and Runbook

Enable Micrometer Observation and collect consumer lag, DLT rates, retries, rebalances, and idle/non-responsive events. Alert when a listener stops unexpectedly or DLT publishing fails. Write a runbook with commands to inspect topics, groups, and consumer assignments.

---

## 22. References

- [Spring Kafka — @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/listener-annotation.html): default factory, `containerFactory`, concurrency, batch listeners, and overrides.
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html): `ConcurrentMessageListenerContainer`, ack modes, concurrency, rebalances, and commits.
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/3.3/kafka/container-props.html): `ContainerProperties` reference and defaults.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html): `CommonErrorHandler`, `DefaultErrorHandler`, retries, DLT, and deserialization.
- [Spring Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/3.3/kafka/serdes.html): deserializers and decode failure handling.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/3.3/kafka/exactly-once.html): Kafka transactions and transactional offsets.
- [Spring Kafka — @RetryableTopic](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html): retry topics, DLT, and non-blocking retries.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/3.3/kafka/events.html): idle, non-responsive, and operational events.
- [Spring Boot 3.4 — Apache Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): `spring.kafka.*` and auto-configured factories.
- [Spring Boot 3.4 — ConcurrentKafkaListenerContainerFactoryConfigurer API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/kafka/ConcurrentKafkaListenerContainerFactoryConfigurer.html): preserving Boot's baseline in custom factories.
- [Spring Kafka 3.3 — DeadLetterPublishingRecoverer API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html): DLT routing and publish verification.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, groups, fetch, and offset settings.
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): producer acks, idempotence, and timeouts.

## 23. Summary

`ConcurrentKafkaListenerContainerFactory` is the bridge connecting **Kafka consumer configuration** with the **lifecycle, processing mode, ack/offset commits, retry/DLT handling, and observability** of `@KafkaListener`. A reliable configuration is more than `setConcurrency(3)`; it must align with partition and replica counts, downstream capacity, timeout/poll budgets, offset commit rules, error classification policies, and idempotent business side effects.

For straightforward applications, leverage the factory auto-configured by Spring Boot from `spring.kafka.*`. For multiple workloads with differing reliability guarantees, build clearly named factories using Boot's configurer with controlled overrides. Then verify with broker-backed integration tests, monitor consumer lag/rebalances/retries/DLT, and rehearse restarts and pod crashes. When these choices are designed cohesively, listeners gain **safe reprocessing, timely fault detection, and controlled recovery** across deployments and operations.
