# Mocking Producers, Consumers, or Adapters at Business Boundaries

In **Spring Boot Messaging**, if every business check had to connect to Kafka/RabbitMQ, create topics, wait for a consumer group, send messages, and wait for processing, the suite would easily become slow and flaky. However, if you mock everything and only verify a Mockito call, tests also fail to prove that payloads, serialization, consumer subscriptions, retries, or broker acknowledgments are correct. A valuable approach is to **define clear business boundaries, mock the right dependencies at those boundaries, and test real transport in a separate integration layer**.

This lesson focuses on **mocking producers, consumers, or adapters at business boundaries** in the Messaging group. The example uses **Java 17, Spring Boot 3.4.5, Spring Kafka, Jackson, Mockito, and JUnit Jupiter**. A small payment flow is divided into:

~~~text
Kafka payments.received
    |
    v
PaymentKafkaConsumer        [inbound adapter]
  - receives JSON String
  - deserializes into PaymentAccepted
  - calls PaymentHandler port
    |
    v
PaymentApplicationService   [business core]
  - validates event
  - calculates reward points
  - creates ReceiptIssued
  - calls ReceiptPublisher port
    |
    v
KafkaReceiptPublisher       [outbound adapter]
  - serializes JSON
  - KafkaTemplate.send(topic, key, payload)
  - returns CompletableFuture
    |
    v
Kafka receipts.issued
~~~

**Unit tests do not start a Kafka broker and do not run a Spring ApplicationContext.** They verify logic and each adapter using mocked dependencies. To know whether the broker actually delivers messages, offsets are committed, or the DLT receives failures, add **EmbeddedKafka/Testcontainers integration tests**. The described outcomes are expectations based on the code, not Gradle logs run during authoring.

## 1. Mock at the boundary, not the subject under test

| Subject under test | Keep real | Mock / fake | Evidence |
| --- | --- | --- | --- |
| PaymentApplicationService | Validation rules and rewardPoints calculation | ReceiptPublisher | Accurate business data, called once, not called if invalid |
| PaymentKafkaConsumer | JSON deserialization + method dispatch | PaymentHandler | Raw JSON becomes the right command; bad input and handler errors are handled properly |
| KafkaReceiptPublisher | JSON serialization + topic/key + future handling | KafkaTemplate | Right topic, key, payload, and propagation when send fails |
| Kafka producer client | Records built against Kafka API | MockProducer | In-memory ProducerRecord history |
| Kafka consumer client | Polling Kafka client API | MockConsumer | Manually supplied records polled properly |
| Spring Kafka listener container | Real container, deserializer, group, retry, ack | Do not replace with plain Mockito | Requires EmbeddedKafka or Testcontainers Kafka |
| Deduplication logic | DB unique constraint/outbox/transaction | Fakes can help in unit tests | Requires integration/concurrency tests to prove safety |

**Do not mock PaymentApplicationService itself** if testing rewardPoints. **Do not mock PaymentKafkaConsumer** if testing JSON mapping. **Do not mock KafkaReceiptPublisher** if testing topic/key. Only mock dependencies outside the subject under test.

Mocks are tools for splitting a system into contracts, not tools for proving the entire stack ran.

### Mock, stub, fake, and spy

- **Mock**: an object created by Mockito that supports `when/thenReturn`, `doThrow`, `verify`, and `ArgumentCaptor`. Useful for verifying interactions.
- **Stub**: supplies canned outcomes, e.g. `ReceiptPublisher.publish` returning `CompletableFuture.completedFuture(null)`.
- **Fake**: a lightweight implementation with real state, like `InMemoryReceiptPublisher` storing a list of receipts; no broker network or offsets.
- **Spy**: wraps a real object and can override part of its behavior. Easy to accidentally trigger real side effects; use only with good reason.
- **Kafka MockProducer/MockConsumer**: fake implementations in `kafka-clients`, closer to the client API than Mockito, yet **not a Kafka cluster**.
- **EmbeddedKafka/Testcontainers Kafka**: broker infrastructure for integration tests, with startup cost and a need to clean up topics/groups.

**Pick the tool for the bug you want to catch:** business rules → mock port; JSON mapping → real ObjectMapper; topic/key/future → mock KafkaTemplate; broker subscription/retry/offset → broker integration.

## 2. Design ports and adapters before testing

An application service becomes coupled when it imports `KafkaTemplate` and hardcodes a topic name in the middle of business logic:

~~~java
@Service
class CoupledService {
    private final KafkaTemplate<String, String> template;

    void onPayment(PaymentAccepted message) {
        // validation ...
        template.send("receipts.issued", message.orderId(), "{...}");
    }
}
~~~

This is an **anti-example snippet**, missing constructor/imports and not part of the runnable project. When switching from Kafka to RabbitMQ/outbox, the service must change. Business unit tests also get dragged into serialization, futures, and broker APIs.

A better design uses two interfaces:

~~~java
public interface PaymentHandler {
    void handle(PaymentAccepted payment);
}

public interface ReceiptPublisher {
    CompletableFuture<Void> publish(ReceiptIssued receipt);
}
~~~

**PaymentHandler** is the inbound application port; the Kafka consumer adapter only parses and delegates. **ReceiptPublisher** is the outbound port; the business core produces receipts without knowing `KafkaTemplate`, topics, or serializers.

`CompletableFuture<Void>` on the outbound port is a **demo choice** so callers can observe asynchronous send success/failure. Production systems may use an outbox/command queue, return a receipt ID, or use another transaction acknowledgment; do not treat futures as mandatory for every system.

### Event contract

Input event:

~~~json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "amountMinor": 12345,
  "schemaVersion": 1
}
~~~

Output receipt:

~~~json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "amountMinor": 12345,
  "rewardPoints": 12,
  "schemaVersion": 1
}
~~~

**amountMinor** is the smallest currency unit defined by the contract; do not assume every currency has two decimal places. Demo rule: **1 point per 1,000 minor units**, integer division. Use `long` to avoid binary floating-point issues when handling integer currency amounts. **eventId** stays stable for correlation and potential future deduplication; merely storing it in the payload **does not create idempotency automatically**.

## 3. KafkaTemplate.send returns CompletableFuture, not a broker-delivery assertion

Spring Kafka 3.x provides:

~~~java
CompletableFuture<SendResult<String, String>> result =
        template.send("receipts.issued",
                      "order-9",
                      "{\"eventId\":\"evt-101\"}");
~~~

This is a snippet assuming a template is present. Levels of evidence to distinguish:

1. **send() was called**: `Mockito.verify` confirms the adapter invoked it.
2. **send future completed successfully**: the producer received a result per `acks` config, not necessarily downstream processing.
3. **send future completed exceptionally**: network/timeout/broker/serializer or other errors must reach the caller.
4. **Consumer receives record**: requires listener/broker integration.
5. **Business state updated properly**: requires handler/persistence tests.
6. **Exactly-once business effect**: requires idempotency, transactions/outbox, and retry tests.

Do not treat `verify(template).send(...)` as proof that the message entered Kafka or was acked by the consumer.

The business handler example below uses `future.join()` to **propagate send errors** across the listener boundary. This is an intentional simplification for testing, but it **blocks the listener thread** and can reduce throughput. Production systems should consider async listeners, outbox, retry policies, and backpressure.

## 4. Runnable Java 17 / Spring Boot 3.4.5 project

### 4.1. File structure

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/messagingqa/MessagingQaApplication.java
src/main/java/com/example/messagingqa/PaymentAccepted.java
src/main/java/com/example/messagingqa/ReceiptIssued.java
src/main/java/com/example/messagingqa/PaymentHandler.java
src/main/java/com/example/messagingqa/ReceiptPublisher.java
src/main/java/com/example/messagingqa/PaymentApplicationService.java
src/main/java/com/example/messagingqa/PaymentKafkaConsumer.java
src/main/java/com/example/messagingqa/KafkaReceiptPublisher.java
src/test/java/com/example/messagingqa/PaymentApplicationServiceTest.java
src/test/java/com/example/messagingqa/PaymentKafkaConsumerTest.java
src/test/java/com/example/messagingqa/KafkaReceiptPublisherTest.java
src/test/java/com/example/messagingqa/KafkaClientFakesTest.java
~~~

### 4.2. Gradle and Kafka String serialization

**settings.gradle**

~~~groovy
rootProject.name = 'messaging-boundary-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-kafka** brings in the Kafka client types in the example; **spring-boot-starter-json** provides Jackson `ObjectMapper`; **spring-boot-starter-test** provides Mockito and JUnit Jupiter. The Spring Boot BOM manages compatible versions. Do not force an independent `spring-kafka`/client version without testing compatibility.

**src/main/resources/application.yml**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: payments-demo
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

The Kafka boundary uses **String** for values; `ObjectMapper` parses/serializes JSON in the adapter. **localhost:9092** is a placeholder for the real app environment running against a local broker; **unit tests do not open Kafka** because they do not start a Spring context. In Testcontainers, bootstrap servers must come from the runtime mapped host/port.

### 4.3. Spring application class

**src/main/java/com/example/messagingqa/MessagingQaApplication.java**

~~~java
package com.example.messagingqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class MessagingQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingQaApplication.class, args);
    }
}
~~~

**@EnableKafka** makes `@KafkaListener` registration intent explicit. Do not start a Spring context just to test integer division or a simple mapper; plain `MockitoExtension` tests run faster and with better isolation.

### 4.4. Message DTO records

**src/main/java/com/example/messagingqa/PaymentAccepted.java**

~~~java
package com.example.messagingqa;

public record PaymentAccepted(
        String eventId,
        String orderId,
        long amountMinor,
        int schemaVersion) {
}
~~~

**src/main/java/com/example/messagingqa/ReceiptIssued.java**

~~~java
package com.example.messagingqa;

public record ReceiptIssued(
        String eventId,
        String orderId,
        long amountMinor,
        long rewardPoints,
        int schemaVersion) {
}
~~~

Do not let DTOs know about `KafkaTemplate` or `@KafkaListener`. Event `schemaVersion` helps reject unsupported formats; production must design backward/forward compatibility and contract evolution. `eventId` must remain stable across retries so downstream consumers can deduplicate.

### 4.5. Inbound and outbound application ports

**src/main/java/com/example/messagingqa/PaymentHandler.java**

~~~java
package com.example.messagingqa;

public interface PaymentHandler {
    void handle(PaymentAccepted payment);
}
~~~

**src/main/java/com/example/messagingqa/ReceiptPublisher.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;

public interface ReceiptPublisher {
    CompletableFuture<Void> publish(ReceiptIssued receipt);
}
~~~

### 4.6. Business service as the subject under test, not mocked

**src/main/java/com/example/messagingqa/PaymentApplicationService.java**

~~~java
package com.example.messagingqa;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class PaymentApplicationService implements PaymentHandler {
    private final ReceiptPublisher publisher;

    public PaymentApplicationService(ReceiptPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void handle(PaymentAccepted payment) {
        Objects.requireNonNull(payment, "payment");

        if (payment.eventId() == null
                || payment.eventId().isBlank()) {
            throw new IllegalArgumentException(
                    "eventId must not be blank");
        }
        if (payment.orderId() == null
                || payment.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (payment.amountMinor() <= 0) {
            throw new IllegalArgumentException(
                    "amountMinor must be positive");
        }
        if (payment.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "unsupported schema version");
        }

        long points = payment.amountMinor() / 1000L;
        ReceiptIssued receipt = new ReceiptIssued(
                payment.eventId(),
                payment.orderId(),
                payment.amountMinor(),
                points,
                1);

        CompletableFuture<Void> send = Objects.requireNonNull(
                publisher.publish(receipt),
                "publisher returned null future");

        // Synchronous demo: send errors will propagate out of the handler.
        // When production needs throughput, consider async/outbox.
        send.join();
    }
}
~~~

**Rules to test:** `amountMinor=12345` yields `rewardPoints=12`. Invalid input must not call the publisher. A failed future must throw an exception; a completed future lets the method return. With this code, a duplicate `eventId` arriving twice produces **two publishes**: the lesson intentionally documents that limitation rather than pretending idempotency already exists.

### 4.7. Inbound Kafka consumer adapter

**src/main/java/com/example/messagingqa/PaymentKafkaConsumer.java**

~~~java
package com.example.messagingqa;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentKafkaConsumer {
    private final ObjectMapper mapper;
    private final PaymentHandler handler;

    public PaymentKafkaConsumer(
            ObjectMapper mapper, PaymentHandler handler) {
        this.mapper = mapper;
        this.handler = handler;
    }

    @KafkaListener(
        topics = "payments.received",
        groupId = "payments-demo")
    public void onMessage(String rawJson) {
        final PaymentAccepted payment;
        try {
            payment = mapper.readValue(
                    rawJson, PaymentAccepted.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "invalid payment JSON", ex);
        }
        handler.handle(payment);
    }
}
~~~

The adapter only parses JSON and calls the port. It contains no reward rules and does not define retry/DLT itself. A test calling `onMessage` directly **does not pass through the Kafka listener container**, and thus does not test subscription, offsets, acknowledgments, or consumer group rebalances.

Valid JSON can contain invalid values; the business service validates `eventId`/`orderId`/`amount`/`version`. If the application requires message schema validation right inside the adapter, add an explicit validator and test that branch separately.

### 4.8. Outbound Kafka producer adapter

**src/main/java/com/example/messagingqa/KafkaReceiptPublisher.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaReceiptPublisher implements ReceiptPublisher {
    public static final String TOPIC = "receipts.issued";

    private final KafkaTemplate<String, String> template;
    private final ObjectMapper mapper;

    public KafkaReceiptPublisher(
            KafkaTemplate<String, String> template,
            ObjectMapper mapper) {
        this.template = template;
        this.mapper = mapper;
    }

    @Override
    public CompletableFuture<Void> publish(ReceiptIssued receipt) {
        final String json;
        try {
            json = mapper.writeValueAsString(receipt);
        } catch (JsonProcessingException ex) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException(
                        "cannot serialize receipt", ex));
        }

        return template.send(
                TOPIC,
                receipt.orderId(),
                json).thenApply(result -> null);
    }
}
~~~

The **topic** lives in the adapter, not the service. **orderId is the record key**, so events with the same key go to the same partition under the typical producer partitioner; ordering is scoped to **a single partition**, not the whole topic. **thenApply(result -> null)** preserves propagation: if the `KafkaTemplate` future fails, the returned future still fails. Do not log the error and return `completedFuture(null)` faking success.

When headers are needed (`correlation ID`, `traceparent`, `event type`), use `ProducerRecord` or Spring `Message<?>` and verify headers in the adapter test. The example puts `eventId` inside JSON rather than assuming `KafkaTemplate.send(topic,key,value)` adds extra business headers.

## 5. JUnit business test: mock outbound ReceiptPublisher

**src/test/java/com/example/messagingqa/PaymentApplicationServiceTest.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PaymentApplicationServiceTest {

    @Mock
    private ReceiptPublisher publisher;

    private PaymentApplicationService service;

    @BeforeEach
    void setUp() {
        service = new PaymentApplicationService(publisher);
    }

    @Test
    void validPaymentCreatesExactReceipt() {
        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.completedFuture(null));

        service.handle(new PaymentAccepted(
                "evt-101", "order-9", 12345L, 1));

        ArgumentCaptor<ReceiptIssued> captor =
                ArgumentCaptor.forClass(ReceiptIssued.class);
        verify(publisher, times(1)).publish(captor.capture());

        ReceiptIssued receipt = captor.getValue();
        assertEquals("evt-101", receipt.eventId());
        assertEquals("order-9", receipt.orderId());
        assertEquals(12345L, receipt.amountMinor());
        assertEquals(12L, receipt.rewardPoints());
        assertEquals(1, receipt.schemaVersion());
    }

    @Test
    void invalidFieldsCannotTriggerPublication() {
        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "", "order-9", 12345L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", " ", 12345L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", "order-9", 0L, 1)));

        assertThrows(IllegalArgumentException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-101", "order-9", 12345L, 99)));

        verifyNoInteractions(publisher);
    }

    @Test
    void publisherFailurePropagatesInsteadOfBeingSwallowed() {
        RuntimeException cause =
                new IllegalStateException("broker unavailable");

        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.failedFuture(cause));

        CompletionException thrown = assertThrows(
                CompletionException.class,
                () -> service.handle(new PaymentAccepted(
                    "evt-102", "order-10", 3000L, 1)));

        assertSame(cause, thrown.getCause());
        verify(publisher).publish(any(ReceiptIssued.class));
    }

    @Test
    void duplicateEventCurrentlyPublishesTwice() {
        when(publisher.publish(any(ReceiptIssued.class)))
                .thenReturn(CompletableFuture.completedFuture(null));

        PaymentAccepted payment =
                new PaymentAccepted("evt-dup", "order-11", 5000L, 1);
        service.handle(payment);
        service.handle(payment);

        verify(publisher, times(2))
                .publish(any(ReceiptIssued.class));
    }
}
~~~

**Why use ArgumentCaptor?** `verify(publisher).publish(any())` stays green even when `rewardPoints` is wrong or the receipt has the wrong `orderId`. A captor turns the payload into meaningful business assertions.

**Why use completedFuture/failedFuture?** This is an asynchronous boundary, so outcomes must be simulated according to the contract. An unstubbed Mockito mock for a future-returning method returns `null`, causing a useless `NullPointerException` when the subject calls `.join()` or `.thenApply()`. A **real failed future** must be `failedFuture(exception)`, not `null`.

**Intentional duplicate test:** it explicitly highlights that the current implementation is not yet idempotent. Once a `processedEventRepository`/outbox is added, update the assertion to prove the same `eventId` produces only **one business effect**. Do not treat `verify(times(1))` on a single invocation as proof of exactly-once when Kafka has redelivery.

## 6. JUnit consumer adapter test: real JSON, mocked handler

**src/test/java/com/example/messagingqa/PaymentKafkaConsumerTest.java**

~~~java
package com.example.messagingqa;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class PaymentKafkaConsumerTest {

    @Mock
    private PaymentHandler handler;

    private PaymentKafkaConsumer consumer;

    @BeforeEach
    void setUp() {
        consumer = new PaymentKafkaConsumer(
                new ObjectMapper(), handler);
    }

    @Test
    void validJsonDispatchesExactCommand() {
        consumer.onMessage("""
                {
                  "eventId":"evt-101",
                  "orderId":"order-9",
                  "amountMinor":12345,
                  "schemaVersion":1
                }
                """);

        ArgumentCaptor<PaymentAccepted> captor =
                ArgumentCaptor.forClass(PaymentAccepted.class);
        verify(handler).handle(captor.capture());

        PaymentAccepted payment = captor.getValue();
        assertEquals("evt-101", payment.eventId());
        assertEquals("order-9", payment.orderId());
        assertEquals(12345L, payment.amountMinor());
        assertEquals(1, payment.schemaVersion());
    }

    @Test
    void malformedJsonNeverCallsHandler() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> consumer.onMessage("{broken-json"));

        assertEquals("invalid payment JSON", error.getMessage());
        verifyNoInteractions(handler);
    }

    @Test
    void handlerErrorPropagatesOutOfAdapter() {
        IllegalStateException cause =
                new IllegalStateException("processing failed");

        doThrow(cause).when(handler)
                .handle(any(PaymentAccepted.class));

        IllegalStateException thrown = assertThrows(
                IllegalStateException.class,
                () -> consumer.onMessage("""
                    {"eventId":"evt-2","orderId":"o-2",
                     "amountMinor":1000,"schemaVersion":1}
                    """));

        assertSame(cause, thrown);
        verify(handler).handle(any(PaymentAccepted.class));
    }
}
~~~

A **real ObjectMapper** in the consumer adapter test protects field names, data types, and Jackson record binding. Mocking the mapper on the success path skips the adapter's primary parsing logic.

A **mocked handler** keeps the adapter test independent of business logic and the Kafka producer. The test only proves JSON converts into `PaymentAccepted` and calls the port, malformed JSON does not call the port, and business errors propagate. It **does not** prove how the `@KafkaListener` container retries or commits offsets.

### Error classification

- **Malformed JSON**: the message itself cannot be parsed; retrying verbatim usually will not fix it, so production often classifies it as non-retryable and routes it to a DLT.
- **Business validation error**: JSON parses, but `amountMinor=0`/unknown `schemaVersion`; needs a clear error policy rather than retrying forever.
- **Temporary infra error**: DB/broker unavailable or timeout; can be retried with backoff.
- **Duplicate**: same `eventId` already processed; an idempotent handler should have a clear no-op/ack policy.

The demo adapter only propagates exceptions. **DefaultErrorHandler/retry-topic/DLT are the responsibility of the Spring Kafka listener container/configuration**, which cannot be asserted via a unit test calling a Java method directly.

## 7. JUnit producer adapter test: mock KafkaTemplate, parse real JSON

**src/test/java/com/example/messagingqa/KafkaReceiptPublisherTest.java**

~~~java
package com.example.messagingqa;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class KafkaReceiptPublisherTest {

    @Mock
    private KafkaTemplate<String, String> template;

    private ObjectMapper mapper;
    private KafkaReceiptPublisher publisher;

    @BeforeEach
    void setUp() {
        mapper = new ObjectMapper();
        publisher = new KafkaReceiptPublisher(template, mapper);
    }

    @Test
    void sendsExactTopicKeyAndJsonFields() throws Exception {
        CompletableFuture<SendResult<String, String>> ack =
                CompletableFuture.completedFuture(null);

        when(template.send(
                eq("receipts.issued"),
                eq("order-9"),
                anyString()))
                .thenReturn(ack);

        publisher.publish(new ReceiptIssued(
                "evt-101", "order-9", 12345L, 12L, 1)).join();

        ArgumentCaptor<String> payload =
                ArgumentCaptor.forClass(String.class);

        verify(template).send(
                eq("receipts.issued"),
                eq("order-9"),
                payload.capture());

        JsonNode data = mapper.readTree(payload.getValue());
        assertEquals("evt-101", data.path("eventId").asText());
        assertEquals("order-9", data.path("orderId").asText());
        assertEquals(12345L, data.path("amountMinor").asLong());
        assertEquals(12L, data.path("rewardPoints").asLong());
        assertEquals(1, data.path("schemaVersion").asInt());
    }

    @Test
    void futureFailureIsPropagatedToCaller() {
        RuntimeException cause =
                new IllegalStateException("send failed");

        when(template.send(
                eq("receipts.issued"),
                eq("order-9"),
                anyString()))
                .thenReturn(CompletableFuture.failedFuture(cause));

        ReceiptIssued event = new ReceiptIssued(
                "evt-102", "order-9", 1000L, 1L, 1);

        CompletionException thrown = assertThrows(
                CompletionException.class,
                () -> publisher.publish(event).join());

        assertSame(cause, thrown.getCause());
    }
}
~~~

**The subject is the real KafkaReceiptPublisher**, and the only mocked dependency is `KafkaTemplate`. A real `ObjectMapper` is used to test serialization. Parsing the payload into a `JsonNode` allows asserting **the important fields** without coupling to whitespace or property ordering in JSON. The `completedFuture(null)` future simulates a successful send result but **carries no real broker RecordMetadata**; do not infer real offset/partition/ack behavior from it.

### Testing serializer failure as a separate branch

The adapter returns a failed future when `ObjectMapper.writeValueAsString` throws `JsonProcessingException`. If coverage of this rare branch is needed, mock the mapper separately:

~~~java
ObjectMapper broken = mock(ObjectMapper.class);
when(broken.writeValueAsString(any()))
        .thenThrow(new JsonProcessingException("bad JSON") {});

KafkaReceiptPublisher adapter =
        new KafkaReceiptPublisher(template, broken);

CompletionException thrown = assertThrows(
        CompletionException.class,
        () -> adapter.publish(receipt).join());

assertInstanceOf(IllegalStateException.class, thrown.getCause());
verifyNoInteractions(template);
~~~

This is a **supplementary snippet**, not part of the runnable files; it needs Mockito/JUnit/Jackson imports and `template`/`receipt` variables from a test fixture. On the success path, **do not mock the mapper**: mocking serialization hides schema drift.

## 8. Built-in MockProducer and MockConsumer in kafka-clients

Mockito `KafkaTemplate` mocks fit when the adapter uses the Spring Kafka API. If testing the Kafka clients API directly and wanting to inspect record history or polling, you can use the fakes provided by `kafka-clients`.

**src/test/java/com/example/messagingqa/KafkaClientFakesTest.java**

~~~java
package com.example.messagingqa;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.MockConsumer;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class KafkaClientFakesTest {

    @Test
    void producerRecordsMessageInMemory() {
        MockProducer<String, String> producer =
                new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

        try {
            producer.send(new ProducerRecord<>(
                    "receipts.issued",
                    "order-9",
                    "{\"eventId\":\"evt-101\"}"));

            assertEquals(1, producer.history().size());
            ProducerRecord<String, String> record =
                    producer.history().get(0);
            assertEquals("receipts.issued", record.topic());
            assertEquals("order-9", record.key());
            assertEquals(
                    "{\"eventId\":\"evt-101\"}",
                    record.value());
        } finally {
            producer.close();
        }
    }

    @Test
    void consumerPollsPreparedRecordsInMemory() {
        MockConsumer<String, String> consumer =
                new MockConsumer<>(OffsetResetStrategy.EARLIEST);

        try {
            TopicPartition partition =
                    new TopicPartition("payments.received", 0);
            consumer.assign(List.of(partition));
            consumer.updateBeginningOffsets(
                    Map.of(partition, 0L));

            consumer.addRecord(new ConsumerRecord<>(
                    "payments.received", 0, 0L,
                    "order-9", "{\"eventId\":\"evt-101\"}"));

            ConsumerRecords<String, String> batch =
                    consumer.poll(Duration.ofMillis(1));

            assertEquals(1, batch.count());
            ConsumerRecord<String, String> record =
                    batch.iterator().next();
            assertEquals("payments.received", record.topic());
            assertEquals("order-9", record.key());
            assertEquals(0L, record.offset());
        } finally {
            consumer.close();
        }
    }
}
~~~

**MockProducer** records `ProducerRecord` entries into history; `true` in the constructor auto-completes sends. **MockConsumer** is assigned a partition and given beginning offsets, then fed records to poll. Neither mock involves a real Kafka cluster or consumer coordinator. A `MockConsumer.poll` test **does not start PaymentKafkaConsumer** and does not prove `@KafkaListener` annotations work.

Spring Kafka also provides **MockProducerFactory/MockConsumerFactory** for tests wiring fake clients into `KafkaTemplate`/listener containers. That is a test level between Mockito adapter unit tests and EmbeddedKafka/Testcontainers integration tests; it still does not simulate all broker semantics.

## 9. An in-memory fake for the outbound port

For multi-step business flow tests, a fake can be more readable than Mockito interaction matching:

~~~java
final class InMemoryReceiptPublisher implements ReceiptPublisher {
    final java.util.List<ReceiptIssued> sent =
            new java.util.ArrayList<>();

    @Override
    public CompletableFuture<Void> publish(ReceiptIssued receipt) {
        sent.add(receipt);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

This snippet can live in the test package with a `CompletableFuture` import. An illustrative test:

~~~java
InMemoryReceiptPublisher fake = new InMemoryReceiptPublisher();
PaymentApplicationService service =
        new PaymentApplicationService(fake);

service.handle(new PaymentAccepted(
        "evt-1", "order-7", 5000L, 1));

assertEquals(1, fake.sent.size());
assertEquals(5L, fake.sent.get(0).rewardPoints());
~~~

A fake needs no broker and can replace the mock publisher in business tests. However, a `List` is normally **not thread-safe** and has no partitions, acks, offsets, retries, or transactions. Create a **fresh fake per test**, never leaving a static mutable `List` that makes tests order-dependent. For concurrent tests, use proper synchronization/dedicated fakes or test against real infrastructure.

## 10. When to use @MockitoBean?

The runnable tests above use **@ExtendWith(MockitoExtension.class)** and instantiate classes via constructors. They do not start a Spring ApplicationContext, so they are fast and easy to follow.

If you want to prove Spring DI/wiring, use **@MockitoBean** (Spring Framework 6.2 and Boot 3.4). Spring Boot's **@MockBean** was deprecated in 3.4 in favor of `@MockitoBean`. Illustrative example:

~~~java
@SpringBootTest(properties = {
    "spring.kafka.listener.auto-startup=false",
    "spring.kafka.admin.auto-create=false"
})
class ConsumerWiringExample {
    @Autowired
    PaymentKafkaConsumer consumer;

    @MockitoBean
    PaymentHandler handler;

    @Test
    void usesInjectedMockPort() {
        consumer.onMessage(
            "{\"eventId\":\"evt-1\",\"orderId\":\"o-1\","
            + "\"amountMinor\":1000,\"schemaVersion\":1}");

        verify(handler).handle(any(PaymentAccepted.class));
    }
}
~~~

This is a **snippet** needing the corresponding imports, not part of the runnable tree. `@MockitoBean` replaces the `PaymentHandler` bean in the test `ApplicationContext`, while `PaymentKafkaConsumer` is the real bean. **listener.auto-startup=false** prevents the Kafka listener container from auto-polling during the wiring test; this **does not prove** Kafka broker delivery.

If you only want to test mappers or business logic, use contextless unit tests. Too many `@SpringBootTest`/`@MockitoBean` variants create many `TestContext` cache keys, slowing down the suite and complicating state management.

## 11. Producer errors, futures, and the true meaning of acknowledge

**KafkaTemplate.send** returns `CompletableFuture<SendResult>`. A successful send invocation does not guarantee broker ack; future completion depends on `acks`/producer config. Even when the broker has acknowledged, the downstream consumer may not have processed the record yet.

In mock adapter tests:
- **Success**: `CompletableFuture.completedFuture(null)` tests adapter result propagation, **not** broker metadata.
- **Failure**: `CompletableFuture.failedFuture(exception)` proves the adapter does not swallow errors.
- **Missing stub**: a mock returning `null` for a future causes a `NullPointerException`, which is not a valid broker failure simulation.
- **Serialization failure**: `ObjectMapper` throws before `KafkaTemplate.send`, so no message must be published.
- **Callback**: when using `whenComplete/handle`, note that callbacks may run on a different thread; assertions must await completion properly.

Do not write:

~~~java
template.send(topic, key, payload)
        .whenComplete((result, ex) -> logger.error("{}", ex));
return CompletableFuture.completedFuture(null);
~~~

This is an **anti-example snippet**, missing variable and return context; it makes the caller see success even when the send failed. The main adapter in this lesson returns the template's future via `thenApply` to **preserve exceptional completion state**.

### Unit test futures vs. integration test delivery

| Evidence | Mockito | Broker integration |
| --- | --- | --- |
| Right topic/key/payload called | Yes | Yes |
| Adapter serializes JSON properly | Yes, with real ObjectMapper | Yes |
| Future success/failure propagation | Yes, via stubbed future | Yes, per broker behavior |
| Broker receives/stores record | No | Yes |
| Consumer group subscribes/polls | No | Yes |
| Deserializer/headers/offset/ack | Not comprehensive | Yes |
| Retry attempts and DLT publishing | Not comprehensive | Yes |
| Duplicates under crash/rebalance | No | Needs dedicated test scenario |
| Exactly-once business effect with DB | No | Needs persistence + concurrency/end-to-end tests |

## 12. Consumer listener errors do not automatically prove retry

When a `@KafkaListener` method throws an exception, the Spring Kafka listener container and **DefaultErrorHandler** decide retry/backoff/recovery per configuration. Depending on error types and handlers, poison JSON may be retried, skipped, or sent to a DLT. **`assertThrows` when calling `onMessage` directly only proves the exception crosses the Java method boundary**, not that offsets were committed or the message moved to a DLT.

Separate error types:
- **Malformed JSON**: unparseable; usually needs non-retryable classification/DLT.
- **Unsupported schemaVersion**: unsupported business contract, usually cannot be fixed by retrying verbatim.
- **Temporary infrastructure failure**: database/broker unavailable, can be retried with backoff.
- **Duplicate business event**: same `eventId` already processed; idempotent handler should safely ignore duplicate impact.
- **Permanent business rejection**: per policy goes to DLT/audit/alert, avoiding infinite retries.

A real retry integration test typically:
1. Configures a specific error handler with bounded attempts/backoff.
2. Sends valid and poison records to an isolated topic.
3. Awaits observable outcomes with a timeout (no guessing `Thread.sleep`).
4. Asserts processing count/DLT/offsets per policy.
5. Cleans up isolated topics/consumer groups/state, avoiding test order dependency.

## 13. Idempotency, outbox, and the limits of exactly-once

Kafka can redeliver records when a consumer crashes after processing and before offset commit, during rebalances, or on retries. Producers can also send duplicate business events. Therefore, **a single `verify(times(1))` in a unit test does not prove the system is truly exactly-once**.

An idempotent consumer typically writes **eventId** into a `processed_events` table with a unique constraint inside the **same DB transaction** as the business mutation. Doing a check-if-exists followed by an insert in two steps without a unique constraint can race when multiple consumers run concurrently.

~~~text
BEGIN DB TRANSACTION
  INSERT processed_events(event_id) UNIQUE
  IF duplicate -> do not apply business mutation again
  ELSE
    UPDATE order/payment state
    INSERT outbox event in same transaction
COMMIT

Separate relay:
  load unsent outbox rows
  publish to Kafka, retry when needed
  mark delivery progress with safe concurrency/idempotency rules
~~~

This is **pseudocode**, not complete SQL. If a service saves `processed_events` first and publishes directly outside the transaction and the send fails, a retry sees `eventId` already processed and skips → **lost outbound message**. Hence an **outbox** is usually suitable for synchronizing database changes and the intent to emit an event, while downstream consumers still need idempotency when the relay resends.

**Kafka exactly-once producer transactions** do not automatically make external SQL/HTTP side effects exactly-once. When a problem involves DB + messaging, design explicit atomicity/compensation/outbox mechanics and test with a real database + broker.

The runnable example has no DB and intentionally publishes a duplicate event twice. This is a limitation that must be addressed before calling an implementation production-ready for finance/payments.

## 14. Topic, key, schema, and header contracts

**Topic:** the adapter receives `payments.received` and emits `receipts.issued`. Unit tests assert exact topics; sending to the wrong topic means consumers never see the message.

**Key:** the example uses `orderId`. With Kafka's default partitioner, records with the same key typically land on the same partition in a stable topology. **Ordering is guaranteed only within a single partition**, not across the entire topic and not across partition count/partitioner changes.

**eventId:** must remain consistent across retries for duplicate detection to be meaningful. Consumers should not use a single offset as the business idempotency key because an event may appear at multiple offsets across resends.

**schemaVersion:** input field `1` passes validation; `version=99` fails. Production needs backward/forward compatibility, a schema registry, and rollout discipline when consumers are not updated simultaneously.

**amountMinor:** uses integer minor units instead of `double` to avoid binary rounding errors. For very large numbers, check multiplication/addition for overflow; the demo only divides by 1000.

**Headers:** the example puts `eventId` only in JSON, not in business Kafka headers. If the contract requires correlation ID, traceparent, tenant ID, or content type in headers, the adapter must construct `ProducerRecord`/`Message<?>` and test exact headers. Do not assume headers appear automatically from `KafkaTemplate.send(topic,key,value)`.

**Serializer:** YAML specifies `StringSerializer` and `StringDeserializer`. JSON is handled by Jackson in the adapter. If a project switches to `JsonSerializer`/`JsonDeserializer` or Avro/Protobuf, tests must be updated for schemas, type headers, trusted packages, and compatibility.

## 15. When to test with a real broker?

### @EmbeddedKafka

Add `testImplementation 'org.springframework.kafka:spring-kafka-test'`, then use Spring Kafka `@EmbeddedKafka` with JUnit 5/`@SpringBootTest` to run an in-process broker. An annotation sketch:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"payments.received", "receipts.issued"},
    bootstrapServersProperty =
        "spring.kafka.bootstrap-servers")
class BrokerContractExample {
    // Send record with real KafkaTemplate.
    // Use test consumer to receive receipts.issued.
    // Assert key, JSON, retry/DLT/side effect per contract.
}
~~~

This is a **sketch**, not part of the runnable tree; it needs imports, test consumer wiring, timeouts/cleanup, and assertions to become a complete integration test. Do not treat this illustrative snippet as evidence that tests connected to a broker.

### Testcontainers Kafka

With a Docker runner, Testcontainers can spin up a real Kafka broker closer to production. Spring Boot 3.4 supports service connections for recognized containers, or `@DynamicPropertySource` can pass bootstrap servers. Only enable the integration class when the job has a Docker daemon and can pull images. A Testcontainers broker class is typically slower than unit tests; split CI jobs into `fast-tests` and `integration-tests`.

### Do not choose a broker test if you only want to compute rewardPoints

If the requirement is "12,345 minor units → 12 reward points", a plain Mockito business test is the right level. If the requirement is "poison messages go to DLT after N attempts and consumer group offsets stay safe", test with a real broker/container. **Separating levels keeps diagnostics clear**, avoiding abusing `@SpringBootTest` to run simple rules.

## 16. Running unit tests and expected results

With a JDK 17-compatible Gradle Wrapper and the dependencies above:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.messagingqa.PaymentApplicationServiceTest
./gradlew test --tests com.example.messagingqa.PaymentKafkaConsumerTest
./gradlew test --tests com.example.messagingqa.KafkaReceiptPublisherTest
./gradlew test --tests com.example.messagingqa.KafkaClientFakesTest
~~~

On Windows use **gradlew.bat** with the same arguments. Because the tests use `MockitoExtension` or in-memory Kafka `MockProducer`/`MockConsumer` and **have no `@SpringBootTest`**, they **do not require Kafka running at localhost:9092**. Expected outcomes per assertions:

| Test group | Expected outcome |
| --- | --- |
| Business valid | Captured `ReceiptIssued` `rewardPoints=12`, complete `eventId`/`orderId`/`schemaVersion` |
| Business invalid | `IllegalArgumentException`, publisher receives no invocations |
| Business future failed | `CompletionException` wrapping original cause |
| Business duplicate | Two publishes, exposing lack of idempotency |
| Consumer JSON valid | Accurate `PaymentAccepted` fields, handler invoked |
| Consumer malformed JSON | `IllegalArgumentException` and handler not invoked |
| Consumer handler failed | Exception propagates out of the adapter boundary |
| Producer send success | Exact topic `receipts.issued`, key `order-9`, accurate JSON fields |
| Producer send failed | Exceptional future propagation |
| MockProducer | One `ProducerRecord` appears in history |
| MockConsumer | Polls exact single record at partition 0, offset 0 |

**Do not fabricate stdout, broker Kafka offsets, or Gradle BUILD SUCCESSFUL when not actually run.** Kafka `MockConsumer` offset 0 is a **test-supplied value**, not a broker-assigned offset.

## 17. Common mistakes and how to fix them

| Design/test mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Mocking the business service itself | Business rules never run | Keep service real; mock ports |
| Mocking mapper on consumer success path | Hides JSON field type bugs | Use real `ObjectMapper` |
| `verify(publisher).publish(any())` | Misses wrong payloads | `ArgumentCaptor` + field assertions |
| `verify(template).send(any...)` | Misses wrong topic/key | `eq` topic/key + JSON assertions |
| Mock future returns `null` | Meaningless NPE, does not simulate broker | `completedFuture`/`failedFuture` |
| Adapter returns success when future failed | Swallows send errors | Return future chained to send |
| Unit test calls `onMessage` and claims offset commit | No listener container involved | Broker integration |
| Using `MockConsumer` to verify group rebalance | Fake has no coordinator | EmbeddedKafka/Testcontainers |
| Using `Thread.sleep` to await messages | Flaky across machines/load | Await observable condition with timeout |
| Assuming producer ack means downstream processed | Two separate stages | Consumer/DB integration assertions |
| No `eventId`/idempotency | Redelivery causes duplicate side effects | Unique processed-event ID + transaction |
| Recording processed ID before publishing and send fails | Risk of lost event | Outbox + relay |
| Business code uses `KafkaTemplate` directly | Couples framework and rules | `ReceiptPublisher` port |
| Using `@MockBean` in new Boot 3.4 code | Deprecated | `@MockitoBean` when Spring context is needed |
| `@SpringBootTest` on every test | Slow suite and config flakiness | `MockitoExtension` for unit boundaries |
| Asserting hard-coded Kafka partition/offset without a broker | Wrong model | Assert fake offsets only when using `MockConsumer` |
| Fake stores static `List` across test classes | Order- and concurrency-dependent | Fresh fake per test |
| Not testing poison messages | Infinite retries or wrong DLT policy | Broker integration error tests |
| Not testing async future failures | False success | `failedFuture` and assert cause |
| Deleting another test's topics/data | Flaky parallel CI | Isolated namespaces/topics/groups |

## 18. Process for reviewing a messaging feature

**Step 1.** Write out the message contract clearly: `eventId`, `schemaVersion`, topic, key, value schema, headers, authorization, and privacy constraints.

**Step 2.** Separate `PaymentHandler`/`ReceiptPublisher` or similar ports; business core must not depend on Spring Kafka types.

**Step 3.** Unit-test business logic using a mocked/faked outbound port, verifying arguments and exact side-effect count per invocation.

**Step 4.** Unit-test the inbound adapter with real JSON, mocked handler, malformed JSON, and exception propagation.

**Step 5.** Unit-test the outbound adapter with mocked `KafkaTemplate`, real `ObjectMapper`, topic/key/payload checks, and exceptional futures.

**Step 6.** If code directly uses the Kafka clients API, use `MockProducer`/`MockConsumer` to test record/poll paths, without mistaking them for a broker.

**Step 7.** Integration-test with EmbeddedKafka/Testcontainers when real serialization, listener containers, offsets, retry/DLT, partition handling, and transactions are needed.

**Step 8.** Test idempotency and state with DB unique constraints/outbox, including duplicate delivery and concurrency.

**Step 9.** Run separate performance/operational tests for lag, throughput, partitions, startup/readiness, and error recovery.

A test should fail at the exact layer it protects: wrong reward rule → business test fails; wrong topic/key/JSON → adapter test fails; wrong listener/container config → broker integration fails.

## 19. Self-check questions

**1.** What should you mock to test `rewardPoints`? **ReceiptPublisher**, keeping `PaymentApplicationService` real.

**2.** `KafkaReceiptPublisher` sends to the wrong topic with the right payload. Is `verify(send(any...))` enough? **No**; assert the exact topic.

**3.** What does `KafkaTemplate.send` return in Spring Kafka 3.x? **CompletableFuture<SendResult<K,V>>**.

**4.** Does a successful `send` call mean the downstream consumer processed the event? **No**; future/broker/consumer/business state are distinct levels.

**5.** Does calling a `@KafkaListener` method directly test consumer groups? **No**.

**6.** Why not mock `ObjectMapper` in consumer success tests? Because we want to test real JSON mapping.

**7.** Should malformed JSON be retried infinitely? **No by default**; it needs a non-retryable/DLT policy per contract.

**8.** Does `MockProducer` actually send records to a Kafka cluster? **No**, it only keeps history in memory.

**9.** Does `MockConsumer` get partitions assigned by a group coordinator? **No**, the test assigns them manually.

**10.** Does a Kafka key guarantee topic-wide ordering? **No**, ordering is within a partition.

**11.** Does having `eventId` in JSON automatically make a handler idempotent? **No**, you must store/enforce unique `eventId` and transaction state.

**12.** What is it called when a producer future fails yet the adapter returns `completedFuture(null)`? **Swallowing errors**, which can falsely report processing success.

**13.** When is `@MockitoBean` used? When overriding a Spring bean inside an `ApplicationContext`; pure unit tests usually use `MockitoExtension`.

**14.** Which module does Kafka `@EmbeddedKafka` require? **spring-kafka-test**.

**15.** What does Testcontainers Kafka require? A **Docker-compatible runtime/daemon** and matching dependencies/container config.

**16.** What is the trade-off of joining a future inside a listener? Easy exception propagation, but it **blocks the listener thread**, impacting throughput.

**17.** Why can updating the DB and then failing `Kafka.send` lose an event? DB commit and Kafka send are not atomic; an outbox or suitable pattern is needed.

**18.** Can you replace a mocked `ReceiptPublisher` with a fake `List`? **Yes**, provided the test owns its state and does not treat the fake as a broker.

**19.** Does `Verify(times(1))` after one call prove exactly-once under redelivery? **No**.

**20.** When is broker integration needed? When the contract involves **real transport, serializers, consumer groups, offsets/acks, retries, DLT, or concurrency**.

### QA Checklist

- Does the business service use interface ports instead of importing `KafkaTemplate`?
- Is the consumer adapter the real subject when testing parsing/dispatch?
- Is the producer adapter the real subject when testing topic/key/JSON?
- Do unit tests use a real `ObjectMapper` on the success path?
- Do Mockito stubs return valid futures, including a `failedFuture` path?
- Do business tests assert exact message fields, validation, and no interactions when invalid?
- Do consumer tests assert malformed JSON does not dispatch and handler exceptions propagate?
- Do producer tests assert topic, key, and JSON content, not just invocation count?
- Are mock/fake clients clearly distinguished from broker integration?
- Is it clearly noted that offsets/retries/DLT **are not proved** by calling a listener directly?
- Are Kafka key, `eventId`, `schemaVersion`, and ordering semantics accurate?
- Is duplicate behavior acknowledged rather than pretending exactly-once?
- Do DB + event atomicity requirements have an idempotency/outbox strategy?
- Are `Thread.sleep` and leaked state from prior tests avoided?
- Do Boot 3.4 context tests prefer `@MockitoBean` over deprecated `@MockBean`?
- Are EmbeddedKafka/Testcontainers added when requirements actually lie at the broker boundary?
- Are Gradle/broker execution results never reported without actual evidence?

**Conclusion:** To test Messaging effectively, **mock at dependency boundaries, never mock the subject under test**. A real business service with a mocked `ReceiptPublisher` proves business rules; a real consumer adapter with a real `ObjectMapper` and mocked handler proves mapping; a real producer adapter with a mocked `KafkaTemplate` proves topic/key/payload/future handling. These tests do not replace broker integration: offsets, retries, DLT, duplicate delivery, and DB-message consistency still require testing on appropriate infrastructure.

## Official Documentation

- Spring Kafka — Sending Messages and KafkaTemplate CompletableFuture: https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html
- Spring Kafka 3.3 — Testing Applications, EmbeddedKafka, MockProducerFactory/MockConsumerFactory: https://docs.spring.io/spring-kafka/reference/3.3/testing.html
- Spring Kafka — Receiving Messages with @KafkaListener: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka — Error Handling, DefaultErrorHandler: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring Framework 6.2 — @MockitoBean: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Apache Kafka Client API — MockProducer and MockConsumer: https://kafka.apache.org/documentation/
