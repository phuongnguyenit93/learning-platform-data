# Building an Idempotent Producer in Spring Kafka

In event-driven systems, a producer may send a record to Kafka without receiving a response due to network slowness, a broker leader change, or a lost response. The Kafka client typically retries to increase delivery success. If every retry became a new record, the consumer could process the same business event multiple times.

An **idempotent producer** is an Apache Kafka mechanism designed to prevent certain duplicate writes caused when **the producer client itself retries the same batch**. Spring Kafka uses the Kafka Java client underneath, so you can enable this mechanism via producer configuration without writing a custom deduplication algorithm around `KafkaTemplate`.

However, a producer configured with `enable.idempotence=true` **does not guarantee end-to-end exactly-once semantics for the whole application**. It does not merge two separate application `send()` calls, does not participate in transactions with PostgreSQL or REST APIs, and does not prevent duplicates if an event is replayed after a process crash and restart.

The lab **Building an Idempotent Producer** belongs to the **Operations Practice** chapter of **Spring Kafka Reliability Operations**. We will configure the producer, write publishing code with stable identity, test with real/Embedded Kafka, inject faults, and establish operational rules.

**Example context:** Java 17, Spring Boot 3.x, Spring Kafka 3.x, and Apache Kafka brokers supporting idempotent producers. For Spring Kafka 4.x or other Kafka client generations, check the APIs, JDK requirements, and documentation corresponding to your actual dependencies.

## 1. Learning Objectives

After completing this lab, you will be able to:

1. Explain why producer retries can create duplicates when idempotence is not enabled.
2. Understand the conceptual roles of producer ID, epoch, and sequence number.
3. Configure `enable.idempotence`, `acks`, `retries`, and `max.in.flight.requests.per.connection` with compatible settings.
4. Implement a `KafkaTemplate` publisher with a stable key and business event ID.
5. Distinguish a Kafka broker acknowledgment from consumer-side business processing completion.
6. Recognize when resending a record via application-level retries risks creating duplicates.
7. Combine the transactional outbox pattern and consumer idempotency when publishing events from a database.
8. Test the happy path, network/broker failures, producer restarts, and business duplicates.
9. Monitor retries, send latency, failures, buffer pressure, and record integrity.
10. Design rollout, rollback, and handling procedures when the producer does not know whether a record was written.

## 2. Why Can Retries Create Duplicate Records?

Suppose a service sends `OrderCreated`:

```text
orders-service                          Kafka broker
      |                                      |
      |------ Produce: event E ------------>|
      |                                      | stores record E
      |<--------- ACK lost ------------------X
      |
      |------ Retry event E --------------->|
      |                                      | may store E again
      |<--------------- ACK -----------------|
```

Without a matching deduplication mechanism on the broker, a retry can turn one event into multiple records in the log. When a consumer performs side effects such as awarding loyalty points or sending emails, duplicates can trigger repeated actions.

In Kafka clients that support idempotence, the producer and broker coordinate using producer identity and sequence numbers so the broker can recognize **duplicate batch retries from that producer**. The goal is to allow retries on transient errors without duplicating records merely because a response was lost.

### Levels That Must Be Separated

| Level | Problem | Common Mechanism |
| --- | --- | --- |
| Kafka client → broker | Same batch retried by Kafka client due to send failure | **Idempotent producer**. |
| Application → KafkaTemplate | Business event passed to `send()` twice by the application | Business ID + publish control / unique key / outbox. |
| Database → Kafka | DB transaction commits, but process dies before recording publish success | Transactional outbox, idempotent consumer, and reconciliation. |
| Kafka → consumer | Offset not yet committed so record is redelivered | Consumer idempotency or Kafka transactions within supported scope. |
| Consumer → external system | HTTP call succeeds, then consumer crashes | Remote idempotency key, business deduplication, or orchestration. |

**Do not confuse "records with the same key" with "the broker will deduplicate records."** A Kafka partition key such as `orderId` is generally used for partition selection and relative ordering, not as a unique constraint that causes Kafka to drop records sharing a key.

## 3. How Idempotence Works in Kafka

Conceptually, an idempotent producer uses:

- **Producer ID (PID):** a Kafka-managed identifier for the producer session.
- **Producer epoch:** helps distinguish producer generations/sessions in relevant scenarios.
- **Sequence number:** an ordering number attached to batches per topic-partition in the protocol mechanism.
- **Broker-side sequence tracking:** the broker detects already-written batches or out-of-order sequences.

```text
Producer session P
    |
    +-- Partition orders.events-0
    |       batch seq=0 --> broker stores
    |       batch seq=1 --> broker stores
    |       batch seq=1 --> duplicate retry detected
    |
    +-- Partition orders.events-1
            batch seq=0 --> broker stores
            batch seq=1 --> broker stores
```

This is a simplified explanatory diagram. Idempotence does not require developers to compute sequence numbers manually; the Kafka producer client and broker handle this protocol metadata.

### Primary Protection Scope

**A Kafka client retrying the same batch within a producer session** is the exact case idempotence is designed to handle. If the client sends a new record via another `send()` call, that is a brand-new record even if its payload, key, and event ID are identical to an earlier one.

Example:

```java
template.send("orders.events", "order-42", "{\"eventId\":\"evt-7\"}");
template.send("orders.events", "order-42", "{\"eventId\":\"evt-7\"}");
```

Those two calls are **two separate send requests**. `enable.idempotence=true` does not deduplicate them. Kafka's mechanism manages retries for each request individually, but it has no knowledge of a business rule saying "each `eventId` must be emitted only once."

### Producer Restarts Are Another Boundary

When an application sends a record, Kafka receives it, and the process dies before the application records the `SENT` state, a new instance may resend the same business event over a new producer session. Client-side idempotence **does not maintain a durable business record across process restarts**.

Therefore, you still need a stable event key and deduplication at the business layer or an appropriate outbox/transaction design.

## 4. Configuration Conditions for an Idempotent Producer

Related Kafka producer properties:

| Configuration | Value for Idempotence | Role |
| --- | --- | --- |
| `enable.idempotence` | `true` | Enables the idempotent producer mechanism. |
| `acks` | `all` (equivalent to `-1`) | Producer requires appropriate acknowledgment from in-sync replicas. |
| `retries` | Greater than `0` | Allows the Kafka client to retry recoverable send errors. |
| `max.in.flight.requests.per.connection` | Less than or equal to `5` | Satisfies the sequence/ordering constraint of an idempotent producer. |
| `delivery.timeout.ms` | Budget sufficient for requests/retries | Limits total time the producer spends trying to send a record. |
| `request.timeout.ms` | Request wait limit | Controls request-level timeout. |
| `linger.ms` | Optional for batching records | Affects batching/latency; not a prerequisite for enabling idempotence. |

In modern Kafka clients, idempotence may be **enabled by default unless conflicting settings are present**. However, setting `enable.idempotence=true` explicitly makes the reliability contract clear and verifiable.

If you set `enable.idempotence=true` alongside `acks=1`, `retries=0`, or `max.in.flight.requests.per.connection` outside the allowed bound, the client can fail with a configuration error. With implicit idempotence, certain conflicting combinations can silently disable idempotence unexpectedly. That is why you should verify **effective runtime values**.

### Do You Need `max.in.flight.requests.per.connection=1`?

Not required for modern idempotent producers: **`<= 5`** is the key Kafka client limit for this feature. Setting it to `1` can reduce pipelining and throughput, though it may occasionally fit a specific control requirement.

If idempotence is disabled, multiple in-flight requests combined with retries can cause records to be written out of order. When idempotence is properly enabled, the Kafka client provides ordering guarantees per topic-partition consistent with the producer protocol.

### Why Does `delivery.timeout.ms` Matter?

A record can fail at the **delivery timeout** even if configured retry attempts remain. For example:

```text
delivery.timeout.ms = 120000
request.timeout.ms  = 30000
linger.ms           = 5
retries             = large number
```

The producer does not retry forever; it is also bounded by the delivery budget. With modern clients, `delivery.timeout.ms` must be configured sufficiently higher than `request.timeout.ms + linger.ms` and matched to application conditions.

**A timeout outcome may be indeterminate:** when the application receives an error after sending, do not assume the record is definitely absent from the broker. Do not rush to re-emit a business event from a new producer session without a deduplication or reconciliation plan.

## 5. Kafka Durability: `acks=all` Is Not the Whole Story

Idempotence and durability solve different problems.

- **Idempotence:** reduces duplicates caused by client retries of the same batch.
- **`acks=all`:** defines the broker/ISR acknowledgment requirement.
- **Replication factor:** number of partition replicas.
- **`min.insync.replicas`:** minimum number of in-sync replicas required to accept writes under the acknowledgment policy.
- **Unclean leader election:** option governing the trade-off between availability and potential data loss.
- **Producer delivery timeout:** determines how long the producer keeps attempting delivery.

Illustrative **production configuration** example for a topic:

```text
topic: orders.events
replication.factor = 3
min.insync.replicas = 2

producer:
  acks = all
  enable.idempotence = true
```

With three replicas and at least two in-sync replicas enforced by policy, the system maintains stronger acknowledgment guarantees than a single broker. Still, you must inspect actual ISR health, failure modes, broker durability, and cluster configuration.

If ISR drops below `min.insync.replicas`, produce requests may be rejected or fail accordingly; do not "fix" this by lowering `acks` to `0` or `1` without evaluating data-loss requirements.

**An Embedded Kafka broker in tests does not prove the fault tolerance of a topic with replication factor 3.** It is suitable for checking APIs, configuration, and record delivery, while durability must be verified on a multi-broker cluster.

## 6. Creating the Practice Project

Suppose an `orders-service` application needs to publish `OrderCreated` events to the `orders.events` topic.

Pipeline:

```text
Order command
    |
    v
Application validates / records business event
    |
    v
OrderEventPublisher
    |
    +-- eventId: stable per business event
    +-- key: orderId
    +-- value: JSON
    |
    v
KafkaTemplate<String, String>
    |
    v
Idempotent KafkaProducer
    |
    v
Kafka brokers: orders.events
```

### Gradle Dependencies

With Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

You can add `spring-boot-starter-web` if an HTTP API is needed, though the publisher does not depend on a controller. Spring Boot dependency management should align `spring-kafka` and `kafka-clients`; do not force arbitrary Kafka client versions just to enable idempotence.

In a project using a Spring Boot starter that already includes Jackson, the direct dependency may not need explicit declaration; the example lists it explicitly to identify the application-level JSON serializer.

### Topic

Example topic:

```text
orders.events
  partition 0
  partition 1
  partition 2
```

Use `orderId` as the Kafka record key so events for the **same order** are typically routed to the same partition given a stable partition count and partitioner configuration. This is a key-based ordering mechanism, **not deduplication**.

If you increase the partition count or change the partitioner, the same key may route differently than historically. Never assume global ordering across partitions or across separate producers just because keys match.

## 7. Configuring an Idempotent Spring Boot Producer

Illustrative `application.yml` file:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        compression.type: snappy
```

These values are only a **practice baseline**, not optimal tuning for every system. `retries` is set high so `delivery.timeout.ms` acts as the practical bound; retries are not guaranteed to continue forever.

In production:

- Point `bootstrap-servers` to environment-managed endpoints.
- Enable TLS/SASL and appropriate ACLs; never store secrets in source code.
- Measure latency and throughput before increasing `linger.ms`, `batch.size`, or compression.
- Set maximum delivery deadlines based on SLAs and broker capacity.
- Configure topic replication and ISR according to durability requirements.

### Why Not Wrap `KafkaTemplate.send()` with `@Retryable` Right Away?

The Kafka client already retries at the producer layer. Putting `@Retryable` on a publish method can initiate **a brand-new `send()` call** after a previous call times out. That new call is not a retry of the same batch under the producer sequence; it can create business duplicates.

If application-level retries are truly needed, you must design:

1. A stable event ID.
2. Durable send state / an outbox or deduplication rule.
3. Error classification distinguishing known vs. unknown outcomes.
4. Bounded attempts and backoff.
5. Consumer idempotency.
6. Reconciliation when the event may already exist on the topic.

Never treat `enable.idempotence=true` as making unbounded `send()` calls safe.

## 8. Creating an Event with Stable Business Identity

An `OrderCreated` event should carry an ID for the **event itself**, not only the order ID:

```java
package example.kafka.orders;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long totalCents,
        String currency,
        long aggregateVersion) {
}
```

Example:

```json
{
  "eventId": "evt-order-42-v1-created",
  "orderId": "order-42",
  "totalCents": 12500,
  "currency": "USD",
  "aggregateVersion": 1
}
```

Distinguish:

- **`orderId`:** entity/aggregate key, used for Kafka partition routing and grouping events for the same order.
- **`eventId`:** logical event identifier, used to detect duplicate events within applications.
- **`aggregateVersion`:** business state version, supporting ordering checks and optimistic concurrency.
- **Payload fields:** business contract data, versioned by schema if evolution is needed.

Do not generate `UUID.randomUUID()` on **every publish retry** of an existing business event. The event ID should be created when the application records the event and **preserved unchanged** across all retries and restarts.

If the producer process crashes, the system must still have durable storage holding the `eventId` and stable payload so it can resend the exact same business event. A Java variable in memory cannot satisfy this requirement.

## 9. Writing `OrderEventPublisher` with `KafkaTemplate`

Spring Kafka 3.x lets `KafkaTemplate.send(...)` return a `CompletableFuture<SendResult<K,V>>`. We will send a `ProducerRecord` with `orderId` as the key and an `eventId` header for easier reconciliation.

```java
package example.kafka.orders;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public final class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper) {

        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
    }

    public CompletableFuture<PublishAck> publish(
            OrderCreatedEvent event) {

        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {

            return CompletableFuture.failedFuture(
                    new IllegalArgumentException(
                            "Stable eventId and orderId are required"));
        }

        final String json;
        try {
            json = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            return CompletableFuture.failedFuture(ex);
        }

        var record = new ProducerRecord<String, String>(
                TOPIC,
                event.orderId(),
                json);

        record.headers().add(
                "eventId",
                event.eventId().getBytes(StandardCharsets.UTF_8));

        return kafkaTemplate.send(record)
                .thenApply(result -> {
                    var metadata = result.getRecordMetadata();

                    return new PublishAck(
                            event.eventId(),
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset());
                });
    }

    public record PublishAck(
            String eventId,
            String topic,
            int partition,
            long offset) {
    }
}
```

### Design Explanation

- `OrderCreatedEvent` already carries `eventId` from the business layer; the publisher does not invent a new ID.
- `orderId` acts as the Kafka key to keep events of the same aggregate in the same partition per routing policy.
- `eventId` is present in both the payload and headers; the header gives logs and consumers quick access, though it is not a broker deduplication key.
- `ObjectMapper` serializes JSON once per send call.
- `KafkaTemplate.send(...)` uses the underlying Kafka producer; Kafka client retries run according to producer settings.
- `CompletableFuture` lets you observe success or failure **asynchronously**, without blocking the calling thread just to wait for an ACK.
- `PublishAck` holds the topic, partition, and offset of the record acknowledged by the broker under the producer policy.

In a real project, the topic name should be injected via managed configuration properties rather than hardcoded in the publisher. The example uses the constant `TOPIC` so the lab stays focused on idempotence.

**Warning:** Receiving a `PublishAck` **does not mean the consumer has processed the event**. It only confirms delivery to Kafka according to the producer's acknowledgment settings.

## 10. Calling the Publisher and Handling Outcomes

Example:

```java
OrderCreatedEvent event = new OrderCreatedEvent(
        "evt-order-42-v1-created",
        "order-42",
        12500,
        "USD",
        1L);

publisher.publish(event)
        .whenComplete((ack, error) -> {
            if (error != null) {
                // Record that the send status is unconfirmed.
                // Do not automatically generate a new eventId and resend.
                log.error(
                        "kafka.publish.failed eventId={} orderId={}",
                        event.eventId(),
                        event.orderId(),
                        error);
                return;
            }

            log.info(
                    "kafka.publish.acked eventId={} "
                        + "topic={} partition={} offset={}",
                    ack.eventId(),
                    ack.topic(),
                    ack.partition(),
                    ack.offset());
        });
```

This snippet illustrates callbacks and assumes `publisher` and `log` variables exist in the calling service. With `CompletableFuture`, completion may execute on a thread different from the HTTP or caller thread. Avoid long blocking operations inside completion callbacks; offload heavy post-processing to a suitable executor.

### Success and Failure Callbacks

| Outcome | Meaning | Next Step |
| --- | --- | --- |
| Send future completed successfully | Kafka broker ACKed per producer settings. | Record offset/metadata; update publish state if using an outbox. |
| Send future completed exceptionally | Kafka client did not complete the send per API contract. | Classify error; remote state may be unknown; consider reconciliation. |
| Process dies before future completes | Application may lose local completion state. | Recover from durable event/outbox; do not rely on memory. |
| Callback fails while updating database | Kafka ACK may have succeeded while the DB is unaware. | Outbox / idempotent consumer handles potential re-emission. |

If an HTTP endpoint calls `publish()` and returns 200 before the future completes, the HTTP response only proves **the request was accepted internally**. Define the contract explicitly: is the API "accepted for publication" or "Kafka acknowledged"? If you need publishing durable across restarts, use an outbox instead of treating an in-memory `CompletableFuture` as a durable queue.

## 11. Kafka ACK and Message Durability

There are several distinct milestones:

```text
Application
  |
  | publish(event)
  v
KafkaTemplate
  |
  | enqueue record
  v
KafkaProducer
  |
  | serialize / batch / retry
  v
Kafka broker leader + ISR
  |
  | acks=all satisfied
  v
Send future completed successfully
  |
  +-- Consumer later reads event
          |
          +-- Business processing succeeds
                  |
                  +-- offset committed
```

Do not conflate these milestones into a single "processed exactly once" signal.

### What If the Broker Reports ACK, but the Consumer Has Not Seen the Record?

The consumer may not have polled yet, the partition may be lagging, the consumer group may not be assigned yet, deserialization may be failing, or the consumer may be configured with `read_committed` while the record belongs to an uncommitted transaction (for transactional producers). With the **non-transactional** publisher in this baseline lab, ACK reflects send completion, not consumer progress.

### What If the Future Times Out?

Never assume the broker definitely lacks the record. For instance, the broker may have appended it while the response was lost, or the client hit the delivery deadline before receiving final confirmation. Transition the event to an investigation / controlled-replay state rather than creating a new event with a fresh identity.

## 12. Testing with `@EmbeddedKafka`: The Happy Path

Integration tests need an actual test Kafka broker rather than only mocking `KafkaTemplate`. With `spring-kafka-test`, you can use `@EmbeddedKafka`.

```java
package example.kafka.orders;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.acks=all",
    "spring.kafka.producer.properties[enable.idempotence]=true",
    "spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5"
})
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class IdempotentProducerIT {

    @Autowired
    private OrderEventPublisher publisher;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Test
    void publishesEventWithStableKeyAndId() throws Exception {
        String eventId = "evt-" + UUID.randomUUID();

        var event = new OrderCreatedEvent(
                eventId, "order-42", 12500, "USD", 1L);

        var properties = KafkaTestUtils.consumerProps(
                "publisher-it-" + UUID.randomUUID(),
                "false",
                broker);

        properties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<String, String>(
                        properties,
                        new StringDeserializer(),
                        new StringDeserializer())
                        .createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    consumer, "orders.events");

            OrderEventPublisher.PublishAck ack =
                    publisher.publish(event)
                            .get(10, TimeUnit.SECONDS);

            var received = KafkaTestUtils.getSingleRecord(
                    consumer,
                    "orders.events",
                    Duration.ofSeconds(10));

            assertThat(ack.eventId()).isEqualTo(eventId);
            assertThat(ack.topic()).isEqualTo("orders.events");
            assertThat(received.key()).isEqualTo("order-42");
            assertThat(received.value()).contains(eventId);
            assertThat(received.partition())
                    .isEqualTo(ack.partition());
            assertThat(received.offset())
                    .isEqualTo(ack.offset());
        }
    }
}
```

### Test Assumptions

- `OrderEventPublisher` and `OrderCreatedEvent` are registered and compiled in the Spring Boot context.
- An `ObjectMapper` bean and `KafkaTemplate<String,String>` are provided by Spring Boot auto-configuration or equivalent setup.
- `spring-kafka-test` is compatible with the runtime version.
- The test does not share topics or groups with parallel tests or stale data; in large suites, isolate brokers, contexts, or topics as needed.
- Embedded Kafka runs a single broker, so it does not verify cluster fault tolerance during leader changes or ISR shrinkage.
- The test consumes one message and checks metadata; it only proves **basic send/receive**, not retry deduplication when an ACK is lost.

Do not name a test `exactlyOnceUnderAllFailures` if it only sends a single successful record. This test is a baseline before performing fault injection.

## 13. Testing Effective Producer Configuration

An easy oversight is declaring `enable.idempotence=true` in YAML while the actual producer bean uses a custom `ProducerFactory` with different properties.

Verify the **effective producer configuration** of the factory used by `KafkaTemplate` under test, rather than just reading the YAML file.

Example using `DefaultKafkaProducerFactory` in Spring Kafka 3.x:

```java
import org.apache.kafka.clients.producer.ProducerConfig;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;

import static org.assertj.core.api.Assertions.assertThat;

void verifyProducerSettings(
        DefaultKafkaProducerFactory<String, String> producerFactory) {

    var configs = producerFactory.getConfigurationProperties();

    assertThat(configs.get(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG))
            .isEqualTo(true);

    assertThat(configs.get(
            ProducerConfig.ACKS_CONFIG))
            .isEqualTo("all");
}
```

This is an illustrative configuration check. Inspect the application's actual producer factory and note that property values may be `String` or converted types depending on the configuration source. For properties defaulted internally by the Kafka client, they may not appear in the input map even though the effective runtime value is applied.

For deeper verification, check startup logs/metrics or instantiate a real producer and confirm no configuration conflicts occur. Never dump the entire configuration map to production logs because SASL JAAS strings, passwords, and sensitive values may reside in it.

### Distinguishing Build Dependencies and Runtime Kafka Client

Spring Kafka is a wrapper. If an application accidentally pulls in an unsupported `kafka-clients` version, startup may fail with `NoSuchMethodError`, `ConfigException`, or unexpected behavior. When changing Kafka client versions, inspect the artifact dependency graph:

```bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

In Maven, use `mvn dependency:tree` with the corresponding filter. Never override the Kafka client version arbitrarily just to access a property without checking the support matrix.

## 14. An Important Test: Calling `send()` Twice Is Not Deduplicated

Suppose the application sends the same business event twice:

```java
OrderCreatedEvent event = new OrderCreatedEvent(
        "evt-order-42-v1-created",
        "order-42",
        12500,
        "USD",
        1L);

publisher.publish(event).get(10, TimeUnit.SECONDS);
publisher.publish(event).get(10, TimeUnit.SECONDS);
```

An idempotent Kafka producer **does not** treat two application calls as one request. Normally, the topic will receive **two records** with the same key and `eventId` (two valid sequence numbers).

Why is this test important?

- It disproves the misconception that `enable.idempotence=true` acts as a unique constraint on `eventId`.
- It reminds developers not to place `@Retryable` around the publisher carelessly.
- It motivates designing event identity, outbox tables, and consumer deduplication.
- It separates Kafka protocol idempotence from business idempotency.

If you write a dedicated integration test, run it on a clean test topic, send twice, poll both records, and assert that the same `eventId` can appear twice. Do not misinterpret seeing two records as "Kafka idempotence is broken"; those are two independent **application sends**.

## 15. Testing Retries When Broker Responses Are Lost

Actually testing idempotent retry deduplication is harder than sending a normal message. You must induce a failure at the moment **the broker may have already written the request, but the client never received the ACK**.

Conceptual scenario:

```text
Producer A (idempotence=true)           Test broker
         |                                  |
         |---- batch E -------------------->|
         |                                  | append E
         X<--------- ACK response ---------|
         |
         |---- Kafka internal retry ------->|
         |                                  | detect duplicate sequence
         |<----------------- ACK ------------|
         |
         v
Topic contains one record for that
internal retry scenario.
```

To test this scenario, you can use:

- A Kafka cluster in Testcontainers.
- A programmable network proxy such as Toxiproxy.
- A broker or test harness capable of dropping responses at a targeted point.
- Producer metrics/logs confirming that the request actually retried.

**Randomly blocking the network does not necessarily reproduce "ACK lost after append."** If the request never reached the broker, the retry has nothing to deduplicate; if the client reconnects and initiates a new application-level send, the semantics differ. The test must demonstrate that the fault affected the ACK path after broker append if you intend to use it as strong evidence of broker-side deduplication.

### Practice Testing Steps

1. Create an isolated topic and a consumer in an isolated test group.
2. Enable idempotence, `acks=all`, retries, and appropriate timeouts.
3. Configure the proxy for **every broker endpoint the producer connects to**, not only the bootstrap address.
4. Use the fault tool to drop/sever responses during the test window.
5. Issue **a single `send()` call** carrying a stable event ID; let the Kafka client retry internally.
6. Observe the send future, producer retry metrics, broker logs, and topic contents.
7. When an actual retry occurs after the initial append, verify that the physical record count did not increase due to duplicate internal retries.
8. Capture logs/metrics before concluding; if the fault did not reproduce the target condition, record the test as inconclusive.

When running Kafka through a proxy, broker metadata returns `advertised.listeners`, so clients may connect directly to brokers after bootstrapping. If you only intercept the bootstrap address and not the advertised endpoints, fault injection may miss actual traffic altogether.

### Testing with Broker Leader Failover

A multi-broker cluster lets you test leader failover and ISR changes. Define replication factor, min ISR, quorum health, and failover timing. Do not assume every leader failure causes duplicates or lost records; the goal is to evaluate outcomes against the Kafka client protocol and durability policy.

## 16. Testing Producer Restarts and "Unknown Outcome"

A more dangerous scenario:

```text
orders-service                          Kafka
     |                                    |
     |--- send event E ------------------>|
     |                                    | stores E
     X process dies before saving ACK
     |
Restart application
     |
     |--- send E again with new session ->| stores another valid record
```

Producer idempotence does not know that two `send()` calls across two sessions represent the same business operation.

A test can:

1. Store event E in a durable source.
2. Use producer instance A to send E; Kafka receives it.
3. Simulate process A dying before the application records publish success.
4. Start producer instance B.
5. Read E from the durable source and resend it with **the same event ID**.
6. Verify the topic may contain a duplicate business event.
7. Verify the idempotent consumer applies the side effect only once.

The key takeaway for the test report is that **Kafka producer idempotence and consumer idempotency protect two different boundaries**.

Never design a test expecting "producer B will be automatically deduplicated against producer A by the Kafka broker because both records have the same JSON."

## 17. Consumer Idempotency to Protect Business Outcomes

When a consumer processes `OrderCreated`, do not treat `eventId` as a string to log and forget. If a business event can reappear, the consumer needs durable deduplication.

PostgreSQL example:

```sql
CREATE TABLE processed_kafka_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Processing strategy within **the same database transaction**:

```text
BEGIN DB TRANSACTION

INSERT INTO processed_kafka_event(consumer_name, event_id)
  ON CONFLICT DO NOTHING;

If insert creates a new row:
  -> apply business update
If key already exists:
  -> skip business update

COMMIT
After DB commits successfully:
  -> acknowledge/commit Kafka offset per policy
```

**Both the deduplication marker and the business update must execute inside the same transaction**; otherwise you risk recording the marker without applying the business update.

Example JDBC service:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class IdempotentOrderConsumerService {

    private final JdbcTemplate jdbc;

    public IdempotentOrderConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderCreatedEvent event) {

        int inserted = jdbc.update(
                """
                INSERT INTO processed_kafka_event(
                    consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                "order-projection",
                event.eventId());

        if (inserted == 0) {
            return false; // Already processed by this consumer.
        }

        jdbc.update(
                """
                INSERT INTO order_projection(
                    order_id, total_cents, currency)
                VALUES (?, ?, ?)
                ON CONFLICT (order_id) DO UPDATE SET
                    total_cents = EXCLUDED.total_cents,
                    currency = EXCLUDED.currency
                """,
                event.orderId(),
                event.totalCents(),
                event.currency());

        return true;
    }
}
```

This is a **conditional example**: you must create the `order_projection` table, configure a transaction manager for the same datasource, and add an event parser and Kafka listener. The SQL targets PostgreSQL. For versioned updates, add optimistic concurrency / version checks so an older redelivered event cannot overwrite newer state.

Kafka offset commits are still not atomic with PostgreSQL in this design. However, when the DB commits and the consumer crashes before committing the Kafka offset, the redelivered record hits the existing marker, preventing **duplicate DB side effects**.

### Do Not Share One Global `event_id` Across All Consumers

If multiple independent consumers or services must process the same event, the marker table must distinguish **logical consumer name** or business scope. An `eventId` already processed by service A must not cause service B to skip its first delivery.

### External HTTP / Side Effects

If a consumer calls a remote payment API, a database deduplication marker does not automatically cover the HTTP call. Use remote idempotency keys or consumer-side orchestration/outbox patterns to ensure correct outcomes across crashes and retries.

## 18. Transactional Outbox: Idempotent Producers Do Not Replace It

A typical application saves an order to the database and then publishes `OrderCreated`.

An unsafe approach:

```text
BEGIN DB TX
  INSERT orders
COMMIT DB TX
  |
  X process crashes
  |
No Kafka event
```

Reversing the order is also unsafe:

```text
Kafka send acked
  |
  X database transaction fails
  |
Kafka has OrderCreated, database has no order
```

The **transactional outbox** solves this by recording **business state and the intent to publish an event in the same DB transaction**:

```text
API / command
     |
     v
BEGIN DB TX
   INSERT/UPDATE orders
   INSERT outbox(event_id, order_id, payload, status=NEW)
COMMIT DB TX
     |
     v
Outbox dispatcher
   claim NEW rows (short DB TX)
   KafkaTemplate.send(...) outside DB TX
   wait for ACK with bounded deadline
   mark SENT (short DB TX)
```

### Illustrative Schema

```sql
CREATE TABLE order_event_outbox (
    event_id      VARCHAR(160) PRIMARY KEY,
    aggregate_id  VARCHAR(160) NOT NULL,
    event_type    VARCHAR(80) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload_json  JSONB NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'NEW',
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    lease_until   TIMESTAMPTZ,
    claim_token   VARCHAR(100),
    last_error    VARCHAR(120),
    created_at    TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_order_event_business
        UNIQUE (aggregate_id, event_type, aggregate_version)
);
```

The outbox is an application table, **not something the Kafka broker creates automatically**.

Design highlights:

- `event_id` remains stable across retries and restarts.
- A unique business constraint prevents creating two events for the same logical obligation when that matches business rules.
- `claim_token` and leases support multi-worker dispatching, preventing a stale worker from updating rows after its lease expires.
- `next_attempt_at` enables backoff.
- `payload_json` preserves the exact event snapshot created; do not regenerate payloads from mutated database state unintentionally.
- `status` reflects publish status, not processing completion across all consumers.

### Crash After Kafka ACK Before DB Ack

```text
Dispatcher A
  |
  +-- KafkaTemplate.send(event E) ACKED
  |
  X crashes before outbox.status=SENT
  |
Dispatcher B claims E
  |
  +-- KafkaTemplate.send(event E) again
```

An outbox ensures events are not forgotten after DB commit, yet because of this crash window, the system can still publish **more than once**. With a different producer instance B, the idempotent producer does not merge the new send. You still need consumer idempotency via `eventId` or appropriate transactional/streaming semantics within your solution boundary.

**Conclusion:** Idempotent producer + transactional outbox + idempotent consumer are **complementary layers**, not three names for the same feature.

## 19. Distinguishing Idempotent Producers and Kafka Transactions

Idempotence is an important foundation, and Kafka also offers **transactional producers** to commit or abort a group of records atomically within Kafka's scope.

| Mechanism | Solves | Does Not Automatically Solve |
| --- | --- | --- |
| `enable.idempotence=true` | Prevents Kafka client batch retries from duplicating records within a producer session per protocol. | Two independent application `send()` calls, DB/HTTP transactions, consumer-side duplicates. |
| Kafka transactions | Atomic commit/abort across multiple Kafka records and offsets in supported workflows. | Atomic transactions with external databases or remote APIs. |
| `read_committed` consumer | Filters out records from aborted Kafka transactions per isolation semantics. | Deduplicating business events from two committed application sends. |
| Transactional outbox | Records publish intent alongside DB changes in a local transaction. | Exactly-once Kafka publishing after crashes without coordination / consumer dedup. |
| Consumer idempotency | Prevents duplicate side effects by business event ID. | Broker-side duplicate removal for internal producer retries. |

### When Are Kafka Transactions Needed?

For example, a Kafka Streams or consume-process-produce workflow that needs:

```text
Consume Kafka input
    |
    +-- Process
    |
    +-- Produce Kafka output
    |
    +-- Commit consumed offsets
             |
             v
      Same Kafka transaction
```

When using a Spring Kafka transactional producer, configure the producer transaction ID prefix and transaction manager/operations according to your exact version's documentation. Each active instance needs appropriate identity to avoid unintended producer fencing.

Conceptual example:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.validated", "order-42", "validated");
    operations.send("orders.audit", "order-42", "recorded");
    return null;
});
```

This snippet illustrates Kafka transaction scope; it requires a transaction-enabled producer factory, existing topics, and suitable broker configuration. If **consumer offsets** must also participate, do not merely call two `send()` methods in a transaction and assume offsets are automatically included.

**Kafka transactions do not roll back PostgreSQL or HTTP side effects.** If events must stay consistent with a database, an outbox or another state synchronization mechanism remains essential.

## 20. Ordering, Partition Keys, and Concurrent Producers

Kafka guarantees log order **per partition**, not global order across a multi-partition topic. Within a single idempotent producer, sequence handling supports retry and ordering guarantees for requests to the same partition.

However, distinguish carefully:

- **One producer sending multiple records:** the Kafka producer manages sequences; `max.in.flight`/idempotence settings affect ordering during retries.
- **Multiple producers sending for the same key:** logical order across separate producers is not automatically sorted by Kafka according to business version.
- **Changing partition counts:** the same key may route to a different partition than historically depending on the partitioner.
- **Producer restarts:** idempotence does not preserve business order across sessions when competing outbox workers exist.

Example:

```text
Order #42
  version 1: CREATED
  version 2: PAID
  version 3: SHIPPED
```

If publisher A sends `v3` before publisher B sends `v2`, the broker cannot infer that `v2` "must happen first." To preserve business ordering, you can:

1. Keep the `orderId` key consistent.
2. Read events from an outbox ordered by `aggregateVersion`.
3. Hold back publishing the next version before the prior version if the contract requires strict ordering.
4. Use per-aggregate sequencing/locking in the dispatcher when needed.
5. Have consumers validate versions or safely ignore stale events.

Do not set `max.in.flight=1` and assume it enforces ordering across independent producer processes.

## 21. Producer Retry Policy: Recoverable vs. Terminal Errors

The Kafka client classifies certain errors as retryable internally. The application still needs to know whether a send succeeded or failed.

| Scenario Type | Example | Handling Approach |
| --- | --- | --- |
| Temporary network glitch | Connection reset, leader election in progress | Kafka client retries per configuration while the producer session remains valid. |
| Broker temporarily short on ISR | `NotEnoughReplicasException` or related error | Keep `acks=all`, monitor the cluster, do not recklessly lower durability. |
| Delivery deadline expired | `TimeoutException` | Outcome may be unknown; classify and reconcile. |
| Serialization failure | Payload cannot be serialized | Fix data or code; do not retry indefinitely over the network. |
| Authorization failure | Insufficient topic ACLs | Investigate ACLs/credentials; do not treat as transient network error. |
| Severe producer state error | `OutOfOrderSequenceException` or fatal producer error | Per client contract, may require recreating the producer; account for unknown outcomes. |
| Transactional producer fenced | `ProducerFencedException` | Handle lifecycle/identity; stop using the fenced producer. |

Exceptions can surface at multiple layers and differ across Kafka client versions. Inspect the **root cause**, record topic/key, attempt/failure telemetry, and broker state.

### Do Not Blindly Resend Whenever a Future Fails

Anti-pattern example:

```java
publisher.publish(event).exceptionally(error -> {
    publisher.publish(event); // Starts a new send while the previous outcome is unknown.
    return null;
});
```

This code can create duplicates and mask errors. When a failure occurs, follow a disciplined process:

1. Identify the stable event ID and source/outbox record.
2. Classify whether the error is retryable, a configuration bug, or an unknown outcome.
3. Enforce a retry budget and backoff.
4. If the application retries, use **the same event ID** and do not mutate the payload arbitrarily.
5. Ensure consumer-side deduplication is in place.
6. Record the final outcome and attempt count.

Without deduplication and reconciliation, "just resend until it succeeds" is not a reliable strategy.

## 22. Backpressure and Producer Resources

Even an idempotent producer has finite resources. If the application generates records faster than the broker acknowledges them, client-side queues and buffers can fill up.

Relevant configurations:

| Configuration | Impact |
| --- | --- |
| `buffer.memory` | Memory used by the Kafka producer to buffer records before sending. |
| `batch.size` | Target batch size for batching and throughput. |
| `linger.ms` | Wait window to accumulate larger batches under certain conditions. |
| `max.block.ms` | How long producer operations wait for metadata/buffer space before failing. |
| `compression.type` | Reduces network bytes at the expense of CPU. |
| `max.request.size` | Maximum producer request size. |
| `delivery.timeout.ms` | Deadline for delivering a record. |
| `acks` / `min.insync.replicas` | Trade-off between acknowledgment guarantees and durability. |

Do not raise `buffer.memory` unboundedly to hide backlogs. If the broker or network slows down for an extended period, larger buffers only delay failure and consume RAM. Apply application-level backpressure, bounded in-flight sends, and overload policies.

For example, a service should not create a million `CompletableFuture` instances and hold all of them in an in-memory list to await:

```java
for (OrderCreatedEvent event : events) {
    futures.add(publisher.publish(event)); // Can grow unboundedly.
}
```

A better approach is bounding concurrency using a worker pool with a bounded queue or an outbox dispatcher with capped in-flight sends. Only acknowledge or delete source work once durable state is assured.

### Throughput Numbers Do Not Replace Correctness

An `acks=1` configuration may run faster than `acks=all` on certain workloads, but if the system requires high durability, do not choose settings based purely on rows/second. Track producer error rates, retries, P95/P99 latency, broker ISR health, and lost/duplicate business events together.

## 23. Observing Idempotent Producers in Production

Kafka producer metrics typically cover record send/retry/error rates, request latency, buffer pressure, and batch behavior. Exact metric names depend on the Kafka client, JMX/Micrometer bridge, and version.

Examples of signals to collect:

| Group | Signal | What to Watch |
| --- | --- | --- |
| Send | Record send rate, send total | Whether producer throughput matches input volume. |
| Retry | Record retry rate/total | Whether broker/network issues are forcing heavy client retries. |
| Error | Record error rate/total | Whether failures spike after a deployment. |
| Latency | Request latency, record queue time | Whether the broker is slow or the producer buffer is congested. |
| Buffer | Buffer available bytes, bufferpool wait time | Whether the application produces faster than Kafka can accept. |
| Batching | Average batch size, compression rate | Throughput vs. bandwidth trade-offs. |
| Broker | Under-replicated partitions, ISR shrink | Ability to satisfy `acks=all` and durability. |
| Business | Outbox backlog, oldest pending event age | Whether events are stuck unpublished. |
| Consumer | Duplicate event IDs handled, lag, DLT | Whether outputs are reprocessed or failing deserialization. |

Do not automatically treat `retry-rate > 0` as data corruption: retries can be normal behavior during transient blips. What matters is sustained spikes in retries/errors, latency breaching SLAs, non-draining backlogs, or wrong business outcomes.

### Structured Logging

Example:

```text
INFO kafka.publish.requested
  topic=orders.events
  eventId=evt-order-42-v1-created
  aggregateId=order-42

INFO kafka.publish.acked
  topic=orders.events
  eventId=evt-order-42-v1-created
  partition=2
  offset=71054
  durationMs=35

WARN kafka.publish.unknown
  topic=orders.events
  eventId=evt-order-42-v1-created
  errorType=TimeoutException
  nextAction=RECONCILE
```

These values are illustrative logs only, not real execution output. Never log tokens, secrets, sensitive financial data, or full unapproved payloads.

For metrics, **do not attach `eventId`, `orderId`, or offsets as metric tags** because of high cardinality. Keep those IDs in detailed logs and traces; use low-cardinality tags such as `topic`, `service`, and `result` for metrics.

## 24. Reliability Testing Checklist

A test suite for an idempotent producer should cover everything from configuration to realistic failure modes:

| Test | Setup | What to Prove |
| --- | --- | --- |
| Valid configuration | Idempotence, acks, retries, max in-flight | Producer initializes and sends successfully. |
| Conflicting configuration | `enable.idempotence=true` + `acks=1` | Client rejects invalid combinations per config contract. |
| Normal send | Embedded Kafka | One application send is ACKed and read by consumer. |
| Two identical application sends | Same `eventId`, call `send()` twice | Business duplicates **can still occur**; prevents misunderstanding idempotence. |
| Internal retry | Confirmed ACK loss / leader fault | Kafka client retry does not duplicate the same batch within the same session. |
| Producer restart | Event resent by new instance | Duplicates may occur; consumer idempotency must protect side effects. |
| Broker short on ISR | Multi-broker cluster, degraded ISR | `acks=all` may fail; do not silently weaken durability. |
| Broker recovery | Temporary network/leader loss | Producer resumes valid sending once fault clears without retry storms. |
| Outbox crash window | Broker ACK before DB marks sent | Event ID stays stable; replay does not duplicate business effects. |
| Consumer restart | Uncommitted offset | Redelivery does not trigger duplicate business updates. |
| Serialization failure | Schema-invalid payload | Explicit error logged/handled; no infinite network retries. |
| Load test | Bounded queue/in-flight | No OOM; throughput and latency meet SLA. |

Do not mark "passed Kafka dedup under retry" unless the test actually triggered an internal retry of the same batch **after the broker had appended it**. Test names and reports must reflect the conditions actually verified.

## 25. Practicing Intentional Configuration Errors

A clear way to verify constraints is attempting to build producers with invalid configurations **in a test environment**, for example:

```properties
enable.idempotence=true
acks=1
retries=10
max.in.flight.requests.per.connection=5
```

Or:

```properties
enable.idempotence=true
acks=all
retries=0
max.in.flight.requests.per.connection=5
```

With Kafka clients enforcing matching idempotence rules, these combinations must be rejected rather than allowing the producer to run silently with weaker semantics than intended. Never introduce intentional misconfigurations in production to "test" with live traffic.

### Why Are Negative Configuration Tests Valuable?

- Proves configuration is applied to the **actual producer factory**.
- Catches library defaults or environment overrides altering `acks` or `retries`.
- Prevents deploying a system where developers believe idempotence is active while requirements are unmet.
- Makes constraints explicit when another team tunes for throughput.

Note that validation APIs and exceptions can vary between Kafka client versions; tests should not assert exact full error message strings.

## 26. Security and Deployment Operations

Idempotence does not replace Kafka authentication, authorization, or transport security.

In production:

- Connect to brokers over `SASL_SSL`/TLS with proper truststores and identities.
- Grant least-privilege ACLs allowing producers to write only to intended topics.
- Manage credentials via a secret manager; never commit passwords in `application.yml`.
- Control topic auto-creation; applications must not auto-create production topics lacking proper replication or retention.
- Ensure event schemas, sizes, and headers do not expose unnecessary sensitive data.
- Protect idempotency/business IDs against unauthorized event spoofing.
- Audit producer deployments, topics, versions, and reliability configuration changes.
- Correlate ISR/leader failures with retry backlogs to pinpoint whether incidents stem from Kafka or the application.

### Rolling Deployments

When deploying multiple replicas:

```text
orders-service v1 (producer A)
orders-service v2 (producer B)
         |
         v
      Kafka topic
```

Each producer instance can be individually idempotent, yet **two replicas can still emit the same business event** if two workers pick up the same command or scan the same outbox row without atomic claiming.

You must:

1. Claim outbox jobs atomically using leases and fencing.
2. Keep event IDs fixed rather than generating them per pod.
3. Have a single authoritative business rule deciding which events to publish.
4. Deduplicate at consumers whenever an event may be re-emitted.
5. Drain or bound in-flight work on shutdown to avoid losing local state.
6. Verify crash windows before considering a rollout complete.

**Do not rely on Kafka's producer ID as a business event identifier.** PID belongs to the Kafka client protocol/session, not as a substitute for `eventId`.

## 27. Difference Between Producer Idempotence and HTTP Idempotency Keys

An HTTP service may receive:

```http
POST /orders
Idempotency-Key: req-123
Content-Type: application/json

{"orderId":"order-42","totalCents":12500}
```

That is an **HTTP API** mechanism: the server stores `Idempotency-Key` / request fingerprints to return consistent responses when a client retries. Kafka producer idempotence is a distinct mechanism at the **Kafka protocol** layer.

An end-to-end reliable flow might look like:

```text
HTTP client (request idempotency key)
    |
    v
orders-service
  validate command
  DB TX: insert order + outbox eventId
    |
    v
Outbox dispatcher
  idempotent Kafka producer
    |
    v
Kafka topic
    |
    v
Consumer dedup by eventId
  DB TX: marker + business update
```

Each layer has its own "key" and scope that must be designed explicitly. If a client retries an HTTP command after a timeout, the request ID prevents creating two orders; if Kafka retries internally, producer idempotence prevents appending a batch twice; if a service restarts, outbox/consumer IDs handle re-emitted events.

Do not collapse all three layers into an imaginary `exactlyOnce=true` flag.

## 28. Incident Scenarios and Responses

### Scenario A: Broker Changes Leader During Publish

The producer may hit temporary errors and retry using refreshed metadata. Monitor request retries, send latency, and leader/ISR changes. If the send future ultimately succeeds, record ACK metadata. If it times out, keep an unknown state for reconciliation.

### Scenario B: ISR Drops Below Threshold

With `acks=all` and proper `min.insync.replicas`, the broker may reject writes. Do not switch to `acks=1` just to silence errors without an explicit durability decision. Investigate broker replication and ISR health.

### Scenario C: Producer Process Dies After ACK

The outbox row has not been marked `SENT`. A new dispatcher may resend the same business event. The new producer's Kafka idempotence does not prevent application-level duplicates. Consumers must deduplicate by event ID, or reconciliation must resolve duplicates.

### Scenario D: Serialization Error

The publisher fails to produce valid JSON or the serializer throws an exception. This is not a transient network error. Inspect data and schemas instead of retrying indefinitely.

### Scenario E: Producer Buffer Full

Publishing faster than the broker drains leads to `max.block.ms` and buffer pressure timeouts or backpressure. Cap concurrency/queues and measure broker throughput instead of accumulating unbounded in-memory futures.

### Scenario F: Same Key, Wrong Business Order

Two producers publish `OrderPaid v2` and `OrderCreated v1` out of order. An idempotent producer does not coordinate ordering between them. Use aggregate versions, outbox ordering, and consumer version checks.

## 29. Practice Exercises

Suppose a `payment-service` emits `PaymentCaptured` events to `payments.captured`. Each payment has `paymentId` and `captureVersion`. The system must survive transient broker faults, never lose events committed to the database, and never double-count revenue on redelivery.

### Exercise 1: Idempotent Producer

1. Create a `KafkaTemplate<String,String>` with `StringSerializer`.
2. Configure `enable.idempotence=true`, `acks=all`, `retries>0`, and `max.in.flight.requests.per.connection<=5`.
3. Create records with a stable `eventId` and `paymentId` as key.
4. Publish asynchronously and record ACK metadata.
5. Ensure timeouts/failures are not misinterpreted as "record definitely never sent."

### Exercise 2: Proving the Limits

1. Send an event normally and read it with a test consumer.
2. Resend it **via a second `send()` call** with the same payload and `eventId`.
3. Observe that two records can coexist on the topic.
4. Explain why this is **not a bug in the idempotent producer**.
5. Implement consumer deduplication by `eventId` and confirm the business update runs only once.

### Exercise 3: Adding an Outbox to the Architecture

1. In a database transaction, persist payment state and the `PaymentCaptured` outbox event.
2. Add a unique constraint on `(paymentId, captureVersion, eventType)`.
3. Have a dispatcher claim rows and publish through the idempotent Kafka producer.
4. After ACK, mark `SENT` in a short database transaction.
5. Kill the dispatcher after broker ACK but before the DB update commits.
6. Restart the dispatcher, verify `eventId` stays unchanged, and confirm the consumer does not apply side effects twice.

### Exercise 4: Verifying Broker Durability

1. Spin up a multi-broker Kafka test cluster.
2. Create a topic with suitable replication factor and min ISR.
3. Intentionally terminate one broker or leader according to your test procedure.
4. Observe retries, future completion, ISR, offsets, and messages received at the consumer.
5. Do not lower `acks` just to make the test pass if system policy requires strong durability.

### Exercise 5: Metrics and Deployment

1. Collect producer send/retry/error rates and P95 latency.
2. Collect outbox pending count and oldest event age.
3. Collect duplicate event IDs at the consumer.
4. Configure alerts for sustained retries, growing backlogs, or under-replicated ISR.
5. Perform a rolling deployment of two producer instances sharing an outbox; verify claiming, fencing, and deduplication.
6. Document the Kafka client / Spring Kafka versions and configurations used.

### Self-Assessment Questions

- Which category of duplicates does `enable.idempotence=true` protect against?
- Why do `acks=all` and `min.insync.replicas` solve a different problem than idempotence?
- When do two `KafkaTemplate.send()` calls produce two records even with identical keys and payloads?
- Why is `max.in.flight.requests.per.connection=1` unnecessary when an idempotent producer is properly configured?
- Does a future timeout prove the broker did not store the record?
- Why does a new producer after restart not automatically deduplicate events sent by the previous producer?
- How does a transactional outbox prevent "DB committed, publish forgotten"?
- Which crash window still allows an outbox to publish duplicates?
- Should a consumer deduplication marker share a transaction with the business update? Why?
- Do Kafka transactions roll back external database or HTTP side effects?
- During leader failover, why is counting client/HTTP retries alone insufficient to prove Kafka deduplicated properly?
- When multiple replicas publish for one aggregate, how do you preserve business version order?

## 30. Summary

A producer can be called **Kafka-idempotent** when the Kafka Java client and broker use producer identity and sequence mechanisms to handle retries of the same batch safely within supported boundaries. In Spring Kafka, this is primarily **producer configuration**: enable `enable.idempotence` and keep `acks`, `retries`, and `max.in.flight.requests.per.connection` compatible.

Business-level reliability, however, requires additional layers:

- **Stable event IDs** to recognize the same event across process restarts.
- **Outbox or transaction design** so publish intent is never lost when the database commits.
- **Consumer idempotency** to prevent duplicate business side effects after redeliveries or application resends.
- **Kafka transactions** when atomicity is needed strictly within supported Kafka boundaries.
- **Realistic fault tests** and metrics to distinguish client retries, broker ACKs, unknown outcomes, and business completion.

The goal of this lab is not "flip one flag and assume all duplicates vanish," but to understand **exactly what that flag guarantees** and build an event publishing system that recovers accurately when failures occur.

## References

- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `enable.idempotence`, `acks`, `retries`, `max.in.flight.requests.per.connection`, and timeouts.
- [Apache Kafka – KafkaProducer API](https://kafka.apache.org/documentation/#producerapi): asynchronous sending and producer behavior.
- [Apache Kafka – Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once, and exactly-once within Kafka.
- [Spring for Apache Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate`, send results, and producer configuration.
- [Spring for Apache Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): transactional producers and offset handling in Kafka transactions.
- [Spring for Apache Kafka – Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` and test utilities.
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): configuring Kafka producers and consumers in Spring Boot.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable event publishing after business data writes.
- [Testcontainers – Kafka Module](https://java.testcontainers.org/modules/kafka/): testing real Kafka in containers and controlled fault injection.

