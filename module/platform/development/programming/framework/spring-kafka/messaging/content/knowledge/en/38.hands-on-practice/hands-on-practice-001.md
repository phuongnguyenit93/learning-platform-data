# Building a Producer to Publish OrderEvent

In this hands-on lab, we build a Spring Boot service that receives requests to create order events via a REST API and publishes `OrderEvent` messages to Kafka. The producer uses `KafkaTemplate`, serializes the payload to JSON, sets `orderId` as the record key, and adds `event-id`/`correlation-id` to the Kafka headers. The API only returns a published status after the broker confirms that the send succeeded.

This lab focuses on the producer in the `SPRING_KAFKA_MESSAGING` module: understanding the flow from a request to a Kafka record, configuring serializers and reliability, observing metadata returned by the broker, and then testing actual send/receive behavior using Embedded Kafka.

## 1. Expected Outcomes

After completing this lab, you will be able to:

- Create a Spring Boot application with the Spring Kafka dependency.
- Model `OrderEvent` and serialize the event to JSON.
- Configure `KafkaTemplate<String, OrderEvent>` and `ProducerFactory`.
- Choose an appropriate topic, record key, and Kafka headers.
- Send records asynchronously and handle results from `CompletableFuture`.
- Understand `acks`, producer idempotence, retries, and their limitations.
- Provision topics for local/test environments and distinguish that from production provisioning.
- Verify that records actually reach the Kafka broker.

## 2. Problem Statement and Data Flow

The service receives requests to confirm order status. Each request creates an independent event containing `eventId`, `orderId`, status, total amount, timestamp, and correlation ID.

~~~mermaid
flowchart LR
    A[HTTP client] -->|POST /api/orders/{id}/events| B[OrderEventController]
    B --> C[OrderEventPublisher]
    C -->|KafkaTemplate.send| D[(orders.events)]
    D --> E[Broker ACK]
    E --> F[HTTP 202 + topic/partition/offset]
    D -.-> G[Consumer in the next lesson]
~~~

A Kafka record has the following key components:

| Component | Value in this lab | Role |
|---|---|---|
| Topic | orders.events | Stream storing events |
| Key | orderId | Selects the partition and preserves relative order for the same order |
| Value | JSON OrderEvent | Business payload |
| Headers | event-id, correlation-id | Tracing and correlating logs across services |

The producer sends the event and receives a broker acknowledgment. That confirms Kafka accepted the record according to the `acks` configuration; it does not prove that a downstream consumer has processed the event.

## 3. Preparing the Project

The example uses Java 17, Spring Boot 3.4.x, and Spring Kafka 3.x. If your existing project already has a Spring Boot parent/BOM, keep the version managed by the project and only add the required dependencies. Do not mix Spring Kafka 2.x with the `CompletableFuture` API examples in this lesson.

Suggested package structure:

~~~text
src/main/java/com/acme/orders/
  OrdersProducerApplication.java
  config/
    KafkaTopicProperties.java
    KafkaTopicConfiguration.java
  messaging/
    OrderEvent.java
    OrderStatus.java
    OrderEventPublisher.java
  web/
    OrderEventController.java
    PublishOrderRequest.java
    PublishOrderResponse.java
src/main/resources/
  application.yml
src/test/java/com/acme/orders/messaging/
  OrderEventPublisherIntegrationTest.java
~~~

With Maven, the minimum dependencies are:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

Version 3.4.5 in the parent is an illustrative baseline so the project can run standalone. For a repository using a different version, prefer the existing Spring Boot dependency management so Spring Kafka and the Kafka client stay aligned.

## 4. Creating the Application Entry Point

~~~java
package com.acme.orders;

import com.acme.orders.config.KafkaTopicProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class OrdersProducerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersProducerApplication.class, args);
    }
}
~~~

EnableConfigurationProperties registers the topic configuration bound from `application.yml`. SpringBootApplication is placed in the root package so component scan discovers the controller, publisher, and configuration below.

## 5. Declaring the Producer Configuration

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

app:
  kafka:
    topics:
      orders: orders.events

spring:
  application:
    name: orders-producer
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: snappy
~~~

Explanation of the properties:

| Property | Meaning |
|---|---|
| bootstrap-servers | Broker addresses for the client to discover the cluster |
| StringSerializer | Serializes the record key |
| JsonSerializer | Serializes the `OrderEvent` object to JSON |
| acks: all | Waits for acknowledgment according to the partition's current ISR |
| enable.idempotence: true | Prevents duplicates caused by producer retries within a single producer session |
| retries | Allows the producer to retry retryable errors |
| max.in.flight.requests.per.connection: 5 | Keeps the limit compatible with an idempotent producer |
| delivery.timeout.ms | Bounds the total time the producer tries to deliver a record |
| linger.ms and batch.size | Provides opportunities to batch records together |
| compression.type | Compresses batches before sending them to the broker |

`acks=all` does not mean data is replicated to every broker in the cluster; the broker waits for the replicas currently in the ISR. In production, coordinate an appropriate replication factor and `min.insync.replicas`. For example, a topic with RF=3 is usually better protected with `min.insync.replicas=2`; a single local broker may only use RF=1/ISR=1 for practice.

An idempotent producer makes producer retries safer within the scope of a session and producer ID. It does not guarantee that a business event is only created once across multiple API calls, multiple instances, or after an application restart. Use a stable `eventId` and consumer-side idempotency if the business domain needs duplicate processing protection.

## 6. Binding the Topic Name from Configuration

Create `KafkaTopicProperties.java`:

~~~java
package com.acme.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka.topics")
public record KafkaTopicProperties(String orders) {
}
~~~

Do not scatter the string `orders.events` across the controller and publisher. A single configuration source lets you change the topic per environment without modifying code.

## 7. Provisioning Topics for the Practice Environment

For local/test environments, you can declare a `NewTopic` so Spring Kafka's `KafkaAdmin` creates the topic when the application context starts:

~~~java
package com.acme.orders.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersEventsTopic(KafkaTopicProperties topics) {
        return TopicBuilder.name(topics.orders())
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

If the broker does not allow the runtime identity to create topics, provision the topic using the Kafka CLI or IaC before running the service. In production, topics usually need to be managed centrally to control partitions, replication factor, retention, cleanup policy, and ACLs.

Manual topic creation commands:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --create \
  --topic orders.events \
  --partitions 3 \
  --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 --describe \
  --topic orders.events
~~~

On Windows you can use `kafka-topics.bat`. Make sure the CLI and the application connect to the same cluster. If a topic already exists with fewer partitions than declared, `KafkaAdmin` can increase the partition count; Kafka does not support decreasing the partition count. Do not assume `NewTopic` automatically reconciles every topic config such as retention or cleanup policy. Manage those changes with controlled `AdminClient`/IaC operations.

## 8. Defining the Event Contract

Create the `OrderStatus.java` enum:

~~~java
package com.acme.orders.messaging;

public enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED
}
~~~

Create `OrderEvent.java`:

~~~java
package com.acme.orders.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderEvent(
        UUID eventId,
        String orderId,
        OrderStatus status,
        BigDecimal total,
        String currency,
        Instant occurredAt,
        String correlationId
) {
}
~~~

Each field has a specific purpose:

- eventId: unique identifier of the event for logging, deduplication, and tracing.
- orderId: aggregate/business key; used as the Kafka record key.
- status, total, currency: business data needed by the consumer.
- occurredAt: timestamp when the event occurred in the application.
- correlationId: correlates logs/traces across multiple services.

An event is a contract between producer and consumer. After publishing, avoid arbitrarily renaming fields or changing field types. When adding fields, apply the schema evolution rules you learned: defaults/optional fields, testing old consumers, and rolling out in a compatible order.

## 9. Writing OrderEventPublisher with KafkaTemplate

Create `OrderEventPublisher.java`:

~~~java
package com.acme.orders.messaging;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import com.acme.orders.config.KafkaTopicProperties;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final KafkaTopicProperties topics;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            KafkaTopicProperties topics) {
        this.kafkaTemplate = kafkaTemplate;
        this.topics = topics;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        ProducerRecord<String, OrderEvent> record =
                new ProducerRecord<>(
                        topics.orders(),
                        event.orderId(),
                        event
                );

        record.headers().add(
                "event-id",
                event.eventId().toString().getBytes(StandardCharsets.UTF_8)
        );
        record.headers().add(
                "correlation-id",
                event.correlationId().getBytes(StandardCharsets.UTF_8)
        );

        return kafkaTemplate.send(record);
    }
}
~~~

`ProducerRecord` lets you control the topic, key, value, and headers before sending. This lab sets `orderId` as the key so events for the same order are routed to the same partition by the default partitioner.

If you only call `kafkaTemplate.send(topic, value)`, the key will not be set by order. In that case, the partition may be chosen by other logic and events for the same order are no longer guaranteed to go to the same partition.

## 10. Why Use orderId as the Key?

Kafka only guarantees record ordering within a single partition. If all events for `order-1001` use the same key and the partition count/partitioner does not change, they will go to the same partition and be read in append order.

Example:

| Event | Key | Meaning |
|---|---|---|
| evt-1 | order-1001 | CREATED |
| evt-2 | order-1001 | CONFIRMED |
| evt-3 | order-2002 | CREATED |

`evt-1` and `evt-2` are routed to the same partition; `evt-3` may go to a different partition. There is no global ordering across partitions.

Note: increasing the partition count can change the key-to-partition mapping with the default partitioner. If the business domain requires strict ordering for a key across topology changes, you must have an appropriate partitioning/migration plan.

## 11. Creating Request and Response for the REST API

Create `PublishOrderRequest.java`:

~~~java
package com.acme.orders.web;

import java.math.BigDecimal;

import com.acme.orders.messaging.OrderStatus;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record PublishOrderRequest(
        @NotNull
        @DecimalMin("0.01")
        BigDecimal total,

        @NotNull
        @Pattern(regexp = "[A-Z]{3}")
        String currency,

        @NotNull
        OrderStatus status
) {
}
~~~

Create `PublishOrderResponse.java`:

~~~java
package com.acme.orders.web;

import java.util.UUID;

public record PublishOrderResponse(
        UUID eventId,
        String result,
        String topic,
        Integer partition,
        Long offset
) {
}
~~~

The response returns metadata from `RecordMetadata`. Partition and offset are useful when investigating events, but you should not use offset as a business identifier because an offset is only meaningful within a single topic-partition.

## 12. Creating the REST Controller to Publish Events

Create `OrderEventController.java`:

~~~java
package com.acme.orders.web;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import com.acme.orders.messaging.OrderEvent;
import com.acme.orders.messaging.OrderEventPublisher;
import jakarta.validation.Valid;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderEventController {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventController.class);

    private final OrderEventPublisher publisher;

    public OrderEventController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/{orderId}/events")
    public CompletableFuture<ResponseEntity<PublishOrderResponse>> publish(
            @PathVariable String orderId,
            @Valid @RequestBody PublishOrderRequest request,
            @RequestHeader(name = "X-Correlation-Id", required = false)
                    String correlationId) {

        UUID eventId = UUID.randomUUID();
        String effectiveCorrelationId =
                correlationId == null || correlationId.isBlank()
                        ? eventId.toString()
                        : correlationId;

        OrderEvent event = new OrderEvent(
                eventId,
                orderId,
                request.status(),
                request.total(),
                request.currency(),
                Instant.now(),
                effectiveCorrelationId
        );

        return publisher.publish(event).handle((sendResult, exception) -> {
            if (exception != null) {
                log.error("Failed to publish OrderEvent: eventId={}, orderId={}",
                        eventId, orderId, exception);

                return ResponseEntity
                        .<PublishOrderResponse>status(
                                HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new PublishOrderResponse(
                                eventId, "FAILED", null, null, null));
            }

            RecordMetadata metadata = sendResult.getRecordMetadata();
            log.info("Published OrderEvent: eventId={}, orderId={}, topic={}, partition={}, offset={}",
                    eventId,
                    orderId,
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());

            return ResponseEntity.accepted().body(
                    new PublishOrderResponse(
                            eventId,
                            "PUBLISHED",
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset()
                    )
            );
        });
    }
}
~~~

The controller waits for the future result before returning the HTTP response. When the broker confirms the send succeeded, the API returns 202 Accepted along with metadata. If the send fails, the API returns 503 Service Unavailable and logs the exception for operations to investigate.

In high-traffic systems, consider HTTP timeouts and `delivery.timeout.ms`: the request may wait until the producer times out delivering the record. If the API needs to respond immediately before broker acknowledgment, design an accepted/pending state and a separate result-tracking mechanism; never return `PUBLISHED` when you do not yet know whether the send succeeded.

## 13. Running the Application and Publishing OrderEvent

Ensure a Kafka broker is running at `localhost:9092` or set the `KAFKA_BOOTSTRAP_SERVERS` environment variable to the right broker address.

Run the application:

~~~bash
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders/order-1001/events \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: checkout-req-9001" \
  -d '{
    "total": 1250000,
    "currency": "VND",
    "status": "CREATED"
  }'
~~~

A successful response looks like:

~~~json
{
  "eventId": "7d7a4a0e-4db7-44b8-9120-30f9a54a8c10",
  "result": "PUBLISHED",
  "topic": "orders.events",
  "partition": 1,
  "offset": 0
}
~~~

`eventId`, `partition`, and `offset` in the example are illustrative data; the actual values are generated by the application and broker.

## 14. Observing Records in Kafka

Use the console consumer to read records:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic orders.events \
  --from-beginning \
  --property print.key=true \
  --property print.headers=true
~~~

You should observe:

- Key equals `order-1001`.
- Value is JSON containing `eventId`, `orderId`, `status`, `total`, `currency`, `occurredAt`, and `correlationId`.
- The `event-id` and `correlation-id` headers are present.
- Topic/partition/offset match the metadata in the API response.

Spring Kafka's `JsonSerializer` may add a type information header by default. When multiple services use different languages or packages, avoid making the consumer depend on the producer's Java class name; agree on a schema/contract and configure explicit type mapping or deserializer target types.

## 15. Testing the Producer with Embedded Kafka

Unit tests that mock `KafkaTemplate` can verify the `send` call, but do not prove the serializer and broker work properly. The following integration test sends an event through the publisher and reads it back from the embedded broker.

~~~java
package com.acme.orders.messaging;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(properties = {
        "spring.kafka.bootstrap-servers=${spring.embedded.kafka.brokers}",
        "app.kafka.topics.orders=orders.events"
})
@EmbeddedKafka(partitions = 3, topics = "orders.events")
class OrderEventPublisherIntegrationTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    private OrderEventPublisher publisher;

    @Test
    void publishesJsonEventWithKeyAndHeaders() throws Exception {
        Map<String, Object> consumerProperties =
                KafkaTestUtils.consumerProps(
                        "orders-producer-integration-test",
                        "false",
                        embeddedKafka
                );
        consumerProperties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest"
        );

        JsonDeserializer<OrderEvent> valueDeserializer =
                new JsonDeserializer<>(OrderEvent.class, false)
                        .trustedPackages("com.acme.orders.messaging");

        try (Consumer<String, OrderEvent> consumer =
                     new DefaultKafkaConsumerFactory<>(
                             consumerProperties,
                             new StringDeserializer(),
                             valueDeserializer
                     ).createConsumer()) {

            embeddedKafka.consumeFromAnEmbeddedTopic(
                    consumer,
                    "orders.events"
            );

            OrderEvent event = new OrderEvent(
                    UUID.randomUUID(),
                    "order-1001",
                    OrderStatus.CREATED,
                    new BigDecimal("1250000"),
                    "VND",
                    Instant.now(),
                    "checkout-req-9001"
            );

            var sendResult = publisher.publish(event)
                    .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, OrderEvent> received =
                    KafkaTestUtils.getSingleRecord(
                            consumer,
                            "orders.events",
                            Duration.ofSeconds(10)
                    );

            assertThat(received.key()).isEqualTo("order-1001");
            assertThat(received.value()).isEqualTo(event);
            assertThat(new String(
                    received.headers().lastHeader("event-id").value(),
                    java.nio.charset.StandardCharsets.UTF_8
            )).isEqualTo(event.eventId().toString());
            assertThat(new String(
                    received.headers().lastHeader("correlation-id").value(),
                    java.nio.charset.StandardCharsets.UTF_8
            )).isEqualTo(event.correlationId());
            assertThat(sendResult.getRecordMetadata().topic())
                    .isEqualTo("orders.events");
            assertThat(sendResult.getRecordMetadata().offset())
                    .isEqualTo(received.offset());
        }
    }
}
~~~

The test creates a three-partition topic to match the application's `NewTopic` bean, but does not hard-code the partition index because the partitioner selects the partition based on the key. `KafkaTestUtils.getSingleRecord` waits for the record with a timeout; avoid using `Thread.sleep` to guess when the record arrives.

Keep the partition count of Embedded Kafka and the `NewTopic` bean consistent so the test does not trigger unintended partition increase operations while the Spring context starts up.

## 16. What Producer Acknowledgment Guarantees

When the `KafkaTemplate.send()` future completes successfully, the producer receives metadata for a record that the broker accepted according to the producer configuration. The level of durability also depends on:

- Whether `acks` is set to 0, 1, or all.
- Replication factor and `min.insync.replicas`.
- The ISR state when the record is written.
- Broker/cluster storage and replication policy.

`enable.idempotence=true` reduces the risk of duplicates from producer client retries. It does not replace:

- Business-level idempotency keys when clients call the REST API repeatedly.
- Transactional outbox if database commit and event publish need to be synchronized.
- Consumer deduplication if an event can be redelivered.
- Kafka transactions if atomic consume-process-produce within Kafka is required.

## 17. Common Pitfalls During Practice

| Symptom | Possible cause | How to check |
|---|---|---|
| TimeoutException on send | Broker unreachable, slow metadata or network | Check bootstrap server, broker logs, and network |
| UnknownTopicOrPartitionException | Wrong topic name or topic not created yet | Run `kafka-topics --list`/`--describe` |
| SerializationException | DTO cannot be serialized or wrong serializer | Check `JsonSerializer`, fields, and stack trace |
| API returns 503 | Future completed with an exception | Read the root exception log and producer metrics |
| Record has null key | Publisher used an overload without a key | Send a `ProducerRecord` with `orderId` |
| Another consumer fails to deserialize | Type header or schema incompatible | Check `JsonDeserializer`/type mapping/schema |
| Event appears multiple times | REST retry, producer retry outside session, or repeated business publish | Use event ID/idempotency and check producer semantics |

## 18. Extension Exercises

1. Send three consecutive events for the same `orderId`; verify they land in the same partition with increasing offsets.
2. Send events for multiple `orderId` values; observe how keys are distributed across partitions.
3. Change `linger.ms` and `batch.size`; measure throughput, request rate, and p95 latency with a repeated workload.
4. Try `compression.type` set to `none`, `gzip`, and `snappy`; compare bytes sent and CPU usage.
5. Stop the broker during a send; observe the failed future and the API logs.
6. Add an idempotency key from the HTTP request so two calls with the same request do not publish two business events.
7. Write a small consumer to inspect the received JSON, key, and headers.
8. Separate topic provisioning from application runtime using Kafka CLI or IaC.

When comparing tuning parameters, change only one group of parameters at a time and use the same workload. Do not evaluate configuration using only a single send because batching requires sufficient traffic to show its effect.

## 19. Completion Checklist

- [ ] Project starts with compatible Java/Spring Boot versions.
- [ ] Broker address is configured via environment variables.
- [ ] Topic `orders.events` exists with appropriate partitions/replication.
- [ ] `KafkaTemplate<String, OrderEvent>` is injected successfully.
- [ ] JSON serializer works with `OrderEvent`.
- [ ] `orderId` is used as the Kafka key.
- [ ] Event ID and correlation ID are present in headers.
- [ ] Send future handles both success and failure.
- [ ] API only reports `PUBLISHED` after broker acknowledgment.
- [ ] Console consumer reads the key, JSON payload, and headers.
- [ ] Embedded Kafka integration test verifies the round-trip.
- [ ] Limitations of `acks` and idempotent producer are understood.

After this lab, you have a complete producer publishing `OrderEvent` from a REST API to a Kafka broker. The key parts are a clear contract, a stable aggregate key, metadata for tracing, and asynchronous send result handling. This lays the groundwork for the next lab to build a consumer that receives and processes the same event.
