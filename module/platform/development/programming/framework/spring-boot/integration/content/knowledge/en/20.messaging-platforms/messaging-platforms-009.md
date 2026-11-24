# Failing Messages, Retries, Dead-Lettering, and Replay

## 1. Context and Objectives

In the **Spring Boot Integration** module, applications commonly consume events from Kafka, RabbitMQ, Apache Pulsar, or a Spring Integration adapter, and then read/write databases, query caches, or call partner HTTP APIs. A single failing message can stall a batch of records, trigger a retry storm, lose data, or execute the same transaction multiple times. Error handling is therefore **part of the integration contract**, not merely a `catch (Exception)`.

Consider a consumer receiving `OrderCreated` and calling a credit-limit service. There are three possibilities:

1. Payload fails schema validation, missing `orderId`: the data **cannot be processed under the current contract**.
2. Credit-limit service returns `503` or times out: this may be a **transient** error; whether the partner executed the call remains uncertain.
3. Consumer committed to its DB yet died before acknowledging the broker: the broker may **redeliver** even though the side effect already completed.

A complete design defines: **error detection → classification → bounded retries → dead-lettering when needed → root-cause fix → controlled replay**, while protecting idempotency and observability.

### General Processing Pipeline

~~~mermaid
flowchart TD
    A[Producer sends event] --> B[Broker: source topic / queue]
    B --> C[Spring Boot consumer]
    C --> D{Validate contract and process}
    D -->|Succeeded| E[Write result / outbox]
    E --> F[Ack or commit offset]
    D -->|Transient error| G{Retry budget left?}
    G -->|Yes| H[Backoff / retry queue or topic]
    H --> C
    G -->|No| I[DLQ / DLT + error metadata]
    D -->|Permanent error| I
    I --> J[Incident, alert, triage, and fix]
    J --> K{Eligible for replay?}
    K -->|Yes| L[Replay with idempotency, throttle, audit]
    L --> B
    K -->|Not yet| M[Retain / quarantine / close per policy]
~~~

The diagram depicts **processing intent**, not an atomic transaction across producer, broker, database, and partner HTTP APIs. Choose delivery guarantees suited to each platform and verify acknowledgment boundaries.

## 2. Definitions: Errors, Retries, Dead-Lettering, and Replay

| Concept | Meaning | Crucial Distinction |
| --- | --- | --- |
| **Error message** | A message describing a failure, such as Spring Integration's `ErrorMessage` or a system error event | Not necessarily a copy of the original business event |
| **Retry** | Re-attempting **the same logical request** in hopes a transient fault cleared | Retries may occur in the consumer, inside the broker, or via a scheduler |
| **Backoff** | Wait interval before the next attempt, often with exponential growth and jitter | Not the retry count; requires both time limits and concurrency caps |
| **DLQ** | *Dead-letter queue*: queue isolating unprocessable messages or exhausted retries | Common in RabbitMQ/AMQP; needs proper exchange/binding and retention |
| **DLT** | *Dead-letter topic*: topic holding failed records | Common in Kafka; a new topic is **not created automatically** just because a listener throws |
| **Replay / redrive** | Reintroducing retained messages into processing through a controlled task | A fresh operation that can generate new offsets/acks and side effects |
| **Poison message** | A message that always fails at the same point, usually due to bad schema or data | Must not retry infinitely; risks stalling an entire partition/queue |
| **Redelivery** | Broker re-delivering an unacknowledged or unhandled message per broker mechanics | Can happen **outside** application-level retry policies |

### What Should Be Preserved in the Message Contract?

Example JSON event:

~~~json
{
  "eventId": "evt-8f2a",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "sourceSystem": "checkout",
  "aggregateId": "order-5042",
  "occurredAt": "2026-11-21T05:00:00Z",
  "data": {
    "orderId": "order-5042",
    "amount": 125000,
    "currency": "VND"
  }
}
~~~

| Field | Purpose During Failures and Replays |
| --- | --- |
| `eventId` | Idempotency key for the **logical event**; stays stable across retries/replays |
| `eventType` + `schemaVersion` | Selects matching deserializer/validator; enables deliberate migrations |
| `sourceSystem` | Identifies data owner, error grouping, and replay authority |
| `aggregateId` | Partition/routing key to preserve per-entity order when required |
| `occurredAt` | Event occurrence timestamp; never overwrite with retry time |
| `correlationId` / trace context in headers | Links logs, traces, and operations across DB/HTTP/broker |
| `attempt`, `firstFailureAt`, `failureCategory` | Broker/consumer-managed infrastructure metadata for routing and alerting |

Systems are not required to use this exact JSON. Formats may be Avro, Protobuf, or JSON Schema; what matters is publishing business keys, contract versions, and field semantics. If payloads carry personal data, DLQ/DLT storage must still comply with encryption, access control, retention, and deletion policies.

### Delivery Guarantee ≠ Business Guarantee

- **At-most-once:** avoids redelivery, yet risks losing messages if consumers die before finishing.
- **At-least-once:** broker can redeliver; applications must tolerate duplicates. This is the standard foundation for reliable integrations.
- **Exactly-once** in certain broker/transaction mechanisms has a **specific scope**, e.g., consuming and producing back to Kafka within a Kafka transaction; it does not automatically span HTTP APIs or independent databases.

Example: DB commits, then consumer crashes before acking. The broker redelivers and a worker could write again. Hence use `eventId`/`sourceSystem` as a unique key in a **consumer inbox/idempotency table**, and require external HTTP APIs to support idempotency keys or reconciliation.

## 3. Classify Errors Before Retrying

Not every error is “retryable.” Classify failures with testable logic driven by data contracts, response codes, and infrastructure causes.

| Error Category | Example | Initial Action | When Budget Exhausted |
| --- | --- | --- | --- |
| **Permanent / contract** | Missing required field, unsupported schemaVersion, unknown enum | Do not retry repeatedly; record structured reason | DLT/DLQ or business quarantine |
| **Intentional business rejection** | Order legitimately rejected per policy | Business outcome, not an infra fault | Record `REJECTED` status per contract; may not need DLQ |
| **Transient dependency** | HTTP `503`, DB temporarily unavailable, pool timeout | Bounded retry, backoff, and circuit breaker | DLT/DLQ + alert; eligible for replay once resolved |
| **Rate limit / overload** | HTTP `429`, overloaded downstream broker | Respect valid `Retry-After`; reduce concurrency | Delayed retry topic/queue or planned quarantine |
| **Ambiguous outcome** | Timeout after POST, disconnect after DB commit | Query outcome or retry with **same idempotency key** | Dedicated incident; never assume “definitely not executed” |
| **Serialization / deserialization** | Malformed JSON, incompatible Avro schema | Error-handling deserializer / adapter error channel | DLT storing safe raw payload and schema info |
| **Configuration / security** | Wrong TLS truststore, invalid credentials | Alert and fix configuration; never retry unbounded | Pause/shed load, hold messages safely |
| **Broker publish/ack failure** | Failed to publish to DLT, lost confirm | Never ack as if dead-lettering succeeded | Separate retry/recovery for DLT transfer per platform |

A practical rule: **business success**, **valid rejection**, **retryable error**, and **unprocessable error** are four distinct outcomes. Never collapse everything into a boolean `success` or log every exception as “not found.”

### Structured Error Model

~~~java
public enum FailureKind {
    INVALID_CONTRACT,
    BUSINESS_REJECTED,
    TRANSIENT_DEPENDENCY,
    RATE_LIMITED,
    UNKNOWN_OUTCOME,
    CONFIGURATION,
    UNEXPECTED
}

public record FailureDescription(
        FailureKind kind,
        String safeCode,
        boolean retryable,
        String eventId) {
}
~~~

`safeCode` is a stable code like `PARTNER_TIMEOUT` or `SCHEMA_VERSION_UNSUPPORTED`, excluding bodies, tokens, passwords, or stack traces. `retryable` should come from each operation's policy: a `POST` without idempotency/reconciliation differs from a read-only `GET`.

## 4. Designing Retry Budgets and Backoff

### 4.1. Retry in the Consumer or Through the Broker?

| Retry Approach | Characteristics | When to Choose | Limitations |
| --- | --- | --- | --- |
| **Blocking/local retry** | Holds the record in the consumer while waiting and retrying | Brief glitches from hundreds of ms to seconds; ordering must stay intact | Blocks partition/thread; increases consumer lag |
| **Kafka retry topic** | Sends record to a retry topic for later consumption | Long backoffs; avoid stalling the main stream | Can alter per-key processing order; adds topics/consumers |
| **RabbitMQ retry queue / TTL / delayed delivery** | Broker holds message until retry timestamp | Long delays; avoids tight immediate requeue loops | Needs DLX/TTL/limits and forwarding reliability checks |
| **DB/outbox scheduler retry** | Persists retry state and polls via background job | Workflows needing downstream checks or hour-long waits | Must implement leases, concurrency, idempotency, and cleanup |
| **Immediate requeue** | Puts message right back on the queue | Rarely appropriate if the fault persists | Can trigger hot loops and CPU/connection storms |

### 4.2. Attempt Counts, Wait Intervals, and Total Time

Policy example:

~~~text
Attempt 1: at t = 0
Attempt 2: after 1 second
Attempt 3: after 2 seconds
Attempt 4: after 4 seconds
=> 4 executions (1 initial + 3 retries), minimum wait 7 seconds,
   EXCLUDING per-attempt execution time, jitter, and topic/queue hops.
~~~

Specify `maxAttempts` alongside `initialDelay`, `multiplier`, `maxDelay`, a **total deadline**, and concurrency limits on retrying requests. Add **jitter** so thousands of consumers do not wake simultaneously after a partner outage. On `429`, honor `Retry-After` within overall service budgets and caps. Configuration errors will not heal themselves through backoff.

Avoid “stacked retries across layers”: 3 HTTP client retries × 3 service retries × 4 Kafka retries can trigger **36 HTTP calls** for a single event. Policy must declare which layer owns retries and which layers simply fail fast to escalate.

### 4.3. Retries and Processing Order

In Kafka, each partition maintains offset order. Blocking retries keep the failing record in that partition's processing lane; **non-blocking retry topics** let subsequent records proceed on the main topic before the failed record returns. If `OrderCreated` then `OrderCancelled` depend on order for the same `aggregateId`, carelessly using retry topics can corrupt final state.

In RabbitMQ, a message `nack(requeue=true)`d can return to the queue and be picked up by another consumer ahead of or behind other messages depending on prefetch, consumer count, and queue state. FIFO alone does not preserve order across multiple consumers, requeues, and retry delays.

The choice is a business decision: preserve order via one lane/partition per aggregate key, use versions and conditional DB updates, or accept out-of-order delivery and reconcile. Never promise exactly-once or total order purely from broker selection.

## 5. Kafka: `DefaultErrorHandler`, DLT, and Retry Topics

Kafka stores records by **topic/partition/offset**. Offsets mark how far a consumer has read; records are not deleted from the log just because a listener succeeds or throws. A Kafka DLT is normally **a separate topic published to by the consumer/framework**, not a queue Kafka creates automatically after a `throw`.

### 5.1. Typical Dependencies and Configuration (Spring Boot 3.x)

~~~xml
<dependency>
  <groupId>org.springframework.kafka</groupId>
  <artifactId>spring-kafka</artifactId>
</dependency>
~~~

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: order-integration
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    listener:
      ack-mode: record
~~~

This example consumes JSON strings and parses explicitly, avoiding pre-listener deserializer failures. With Avro/Protobuf or Spring's `JsonDeserializer`, add mechanisms to catch **deserialization failures before the listener** such as `ErrorHandlingDeserializer`, plus a DLT producer serializer handling raw bytes when needed; otherwise the handler may never receive a valid payload to forward to the DLT.

### 5.2. Listener Errors and Exception Classification

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderKafkaListener {

    private final ObjectMapper objectMapper;
    private final OrderProcessor processor;

    public OrderKafkaListener(
            ObjectMapper objectMapper, OrderProcessor processor) {
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    @KafkaListener(topics = "orders.events")
    public void consume(String json) {
        OrderCreated event;
        try {
            event = objectMapper.readValue(json, OrderCreated.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException("Invalid order JSON", ex);
        }

        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new InvalidOrderEventException("Missing eventId/orderId");
        }

        processor.process(event); // Enforces idempotency/inbox in business layer.
    }
}

record OrderCreated(String eventId, String orderId, long amount) {}

interface OrderProcessor {
    void process(OrderCreated event);
}

class InvalidOrderEventException extends RuntimeException {
    InvalidOrderEventException(String message) {
        super(message);
    }
    InvalidOrderEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

In real Java codebases, put each `public` top-level type in its own matching file or keep illustrative types package-private as above. `processor.process` is the contract to implement: e.g., insert `eventId` into an inbox table guarded by a unique constraint before applying side effects. If the service calls a partner over HTTP and times out, throw a distinct exception like `TransientPartnerException` rather than turning it into `InvalidOrderEventException`.

### 5.3. Blocking Retries Followed by Publishing to DLT

With **Spring Kafka 3.x**, `DefaultErrorHandler` can retry records with backoff and then use `DeadLetterPublishingRecoverer` to send failing records to a dead-letter topic:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration(proxyBeanMethods = false)
public class OrderKafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler orderKafkaErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, error) -> new TopicPartition(
                                "orders.events.DLT", record.partition()));

        recoverer.setFailIfSendResultIsError(true);

        // 2 retries after initial delivery: up to 3 total attempts.
        DefaultErrorHandler handler = new DefaultErrorHandler(
                recoverer, new FixedBackOff(1_000L, 2L));
        handler.addNotRetryableExceptions(InvalidOrderEventException.class);
        return handler;
    }
}
~~~

When using Spring Boot's auto-configured Kafka listener factory, a `CommonErrorHandler`/`DefaultErrorHandler` bean is picked up by Boot to configure listener containers. If your application declares a custom `ConcurrentKafkaListenerContainerFactory`, you must **wire that handler explicitly** via `factory.setCommonErrorHandler(handler)`; never assume a bean automatically applies to custom factories.

One cycle:

~~~text
orders.events, partition=2, offset=91
  -> listener attempt 1: 503 (retryable)
  -> FixedBackOff 1,000 ms -> attempt 2: 503
  -> FixedBackOff 1,000 ms -> attempt 3: 503
  -> recoverer publishes to orders.events.DLT, partition=2
  -> advances / commits original record per container policy
     only when recovery succeeds
~~~

`FixedBackOff(1_000L, 2L)` means **two retries**, not two total attempts. `InvalidOrderEventException` is marked non-retryable, so it goes straight to the DLT. Depending on version, Spring Kafka also treats certain `DeserializationException` and `MessageConversionException` errors as fatal by default. Never mix policy tweaks across multiple error handlers without test verification.

**Deployment prerequisites:**

- Topic `orders.events.DLT` must exist and have **at least as many partitions as the source topic** if the recoverer targets `record.partition()`. To let the producer choose the partition, the resolver can return `TopicPartition(name, -1)` under compatible settings.
- Configure DLT producer serializers, broker authorization, and message size limits compatibly. If DLT publishing fails yet the consumer treats the record as recovered, data can drop out of the main processing path.
- Ensure publish succeeds per policy (e.g., `setFailIfSendResultIsError(true)`, producer acks, and broker-failure tests) before considering the record quarantined.
- DLT metadata includes original topic/partition/offset, exception class, and headers; sanitize sensitive info. Retain DLT records long enough for investigation, not infinitely.
- Post-handling/post-recovery offset commits also depend on `AckMode`, `commitRecovered`, and container/transaction configuration. Never guess from listener code without testing against the broker and consumer group.

### 5.4. Observing Records in the DLT

A dedicated consumer can record incidents without **auto-replaying**:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderDltInspector {
    private final FailureIncidentStore incidents;

    public OrderDltInspector(FailureIncidentStore incidents) {
        this.incidents = incidents;
    }

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector")
    public void inspect(ConsumerRecord<String, String> record) {
        incidents.record(
                record.key(), record.topic(), record.partition(),
                record.offset(), record.value(), record.headers());
    }
}

interface FailureIncidentStore {
    void record(String key, String topic, int partition, long offset,
                String rawValue, org.apache.kafka.common.header.Headers headers);
}
~~~

The incident store needs a unique key per DLT observation because this audit listener itself can experience redelivery. In production, do not store raw payloads unvetted for permissions/PII; retain minimal data or encrypted payloads with retention limits. If the incident DB fails, let the listener fail per policy so the broker redelivers, rather than ACKing and losing track of the failure.

### 5.5. Non-Blocking Retry Topics

Instead of blocking retries from section 5.3, Spring Kafka supports **non-blocking retry topics** via `@RetryableTopic`. This is an **alternative approach**—do not layer both onto the same listener without explicit design:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class RetryTopicOrderConsumer {
    private final ObjectMapper objectMapper;
    private final OrderProcessor processor;
    private final FailureIncidentStore incidents;

    RetryTopicOrderConsumer(
            ObjectMapper objectMapper,
            OrderProcessor processor, FailureIncidentStore incidents) {
        this.objectMapper = objectMapper;
        this.processor = processor;
        this.incidents = incidents;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0,
                               maxDelay = 5_000),
            exclude = InvalidOrderEventException.class,
            autoCreateTopics = "false")
    @KafkaListener(
            topics = "orders.retry-demo",
            groupId = "orders-retry-demo")
    public void consume(String rawJson) {
        processor.process(parseOrder(rawJson));
    }

    @DltHandler
    public void inspectDeadLetter(ConsumerRecord<String, String> record) {
        // Record incident; do not auto-replay immediately.
        incidents.record(
                record.key(), record.topic(), record.partition(),
                record.offset(), record.value(), record.headers());
    }

    private OrderCreated parseOrder(String rawJson) {
        try {
            OrderCreated event =
                    objectMapper.readValue(rawJson, OrderCreated.class);
            if (event.eventId() == null || event.eventId().isBlank()
                    || event.orderId() == null || event.orderId().isBlank()) {
                throw new InvalidOrderEventException("Missing eventId/orderId");
            }
            return event;
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException("Invalid order JSON", ex);
        }
    }
}
~~~

`@RetryableTopic` builds on Spring Retry (`org.springframework.retry.annotation.Backoff`); `attempts="4"` means **1 original attempt + 3 retries**. `exclude = InvalidOrderEventException.class` bypasses retries for contract errors and routes straight to the DLT. `autoCreateTopics="false"` requires pre-provisioning the retry topics and DLT with the exact names and partition counts your Spring Kafka version expects; otherwise the listener fails to operate as intended. The snippet uses `OrderCreated`, `OrderProcessor`, `InvalidOrderEventException`, and `FailureIncidentStore` defined earlier.

Known limitations: non-blocking retries **cannot be combined with Kafka container transactions** and **do not support batch listeners**; they can also reorder records with the same key when a newer record overtakes one sitting in a retry topic. For flows needing sequential processing, prefer blocking retries, version gating, or per-key queues. If using Spring Kafka 4.x, double-check retry topic naming, default attempt counts, and topic-reuse modes rather than assuming fixed suffixes across versions.

## 6. RabbitMQ: Reject/Nack, DLX, and DLQ

RabbitMQ uses **exchange → routing key → queue**. The broker delivers messages to consumers; consumers or listener containers acknowledge (`basic.ack`), reject (`basic.reject`), or `basic.nack`. When `requeue=false` and the queue configures a dead-letter exchange (**DLX**), the broker can route the message to an error queue. Other dead-lettering triggers include expired TTL, exceeded queue length limits, or exceeded quorum-queue delivery limits.

### 6.1. Configuring RabbitMQ Topology

With **Spring Boot 3.x and Spring AMQP 3.x**:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitDeadLetterTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.exchange", true, false);
    }

    @Bean
    DirectExchange ordersDeadExchange() {
        return new DirectExchange("orders.dlx", true, false);
    }

    @Bean
    Queue ordersWorkQueue() {
        return QueueBuilder.durable("orders.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.dead")
                .build();
    }

    @Bean
    Queue ordersDeadQueue() {
        return QueueBuilder.durable("orders.dlq").build();
    }

    @Bean
    Binding ordersBinding(Queue ordersWorkQueue,
                          DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersWorkQueue)
                .to(ordersExchange).with("orders.created");
    }

    @Bean
    Binding deadBinding(Queue ordersDeadQueue,
                        DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersDeadQueue)
                .to(ordersDeadExchange).with("orders.dead");
    }
}
~~~

Path:

~~~text
publish exchange=orders.exchange, routingKey=orders.created
         -> queue orders.work
         -> consumer fails
         -> reject/nack(requeue=false)
         -> DLX orders.dlx, routingKey=orders.dead
         -> queue orders.dlq
~~~

Spring AMQP can declare `Queue`, `Exchange`, and `Binding` through `RabbitAdmin` when configured. In production, RabbitMQ recommends managing DLX via **policies** so changes do not require deleting/recreating queues; the code above makes the practice topology explicit. Queue arguments `x-dead-letter-exchange` and `x-dead-letter-routing-key` match the builder calls.

**A DLQ is not created automatically simply by setting `default-requeue-rejected=false`.** The broker must have a valid DLX and target binding; otherwise rejected messages may be discarded from the source queue without landing in quarantine. When long-term retention is required, verify durability, persistence, publish/routing permissions, disk alarms, and capacity limits.

### 6.2. Listener and Container-Level Retries

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitListener {
    private final OrderMessageService service;

    public OrderRabbitListener(OrderMessageService service) {
        this.service = service;
    }

    @RabbitListener(queues = "orders.work")
    public void receive(String rawJson) {
        service.handle(rawJson);
    }
}

interface OrderMessageService {
    void handle(String rawJson);
}
~~~

If the service throws an exception, the listener container acts per configured acknowledgment/requeue/retry settings. Example:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        prefetch: 20
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1s
          multiplier: 2
          max-interval: 8s
~~~

When the listener container enables Boot's retry interceptor, `max-attempts: 4` means **1 initial attempt and up to 3 retries** during message handling. Once retries exhaust and the final failure is rejected without requeue, RabbitMQ dead-letters the message per declared topology. `acknowledge-mode: auto` means the container acks automatically after the listener finishes cleanly; it does **not** mean the broker guarantees DB/HTTP side effects occurred exactly once.

**Classifying permanent errors:** the default retry interceptor may retry schema/validation errors before rejecting. To route those straight to the DLQ, configure a `RetryPolicy`/`RetryOperationsInterceptor` with a suitable exception classifier or validate before the handler. `AmqpRejectAndDontRequeueException` forces the container to reject with `requeue=false` when the exception reaches the container layer; if an outer retry advice wraps it, check whether that advice catches the exception first.

### 6.3. Why Must You Never Requeue Infinitely?

If you always `nack(requeue=true)` while a DB is down, the same message immediately returns, multiple consumers loop on the error, and CPU/connections across the cluster spike. Remedies:

- Keep consumer-local retry counts small for brief glitches.
- For prolonged outages, move to a **delayed retry queue** or scheduler/retry mechanism rather than tight loops.
- Enforce quorum-queue delivery limits and explicit policies for unrecoverable errors.
- Monitor ready/unacked counts, consumer utilization, redelivery rates, and DLQ depth.
- When failures leave side effects uncertain, preserve idempotency keys and check downstream state before retrying.

A TTL-based retry architecture can look like:

~~~text
orders.work -> on transient error -> retry.exchange
                                  -> orders.retry.5s (5-second TTL)
                                  -> on TTL expiry, DLX returns to orders.exchange
                                  -> orders.work
orders.work -> on exhausted budget/poison -> orders.dlx -> orders.dlq
~~~

This is a **logical** diagram; configure exchanges, queues, routing keys, TTLs, retry counts, and final branching completely. RabbitMQ supports dead-lettering on TTL expiration, though mixing different TTLs in one shared queue can cause head-of-line blocking; consider separate retry queues per delay tier or delayed-delivery mechanisms supported by your broker version.

### 6.4. Dead-Lettering Can Fail

In RabbitMQ, dead-lettering is **a fresh publish inside the broker**. By default, DLX forwarding has durability limits and should not be assumed at-least-once in every situation. For **quorum queues**, RabbitMQ supports an `at-least-once` dead-letter strategy using internal publisher confirms when properly configured, trading extra resources and holding the source message until the target confirms. Check `overflow=reject-publish`, policies, queue types, permissions, and target health. Test behavior when the DLX or target queue is unavailable.

RabbitMQ attaches the broker-managed `x-death` header recording dead-letter events by queue/reason. Do not trust a producer-supplied `x-death.count` as a reliable retry counter; RabbitMQ 4.x ignores client-set `x-*` headers on certain publish paths. When the application republishes messages to retry, manage your own `retry_count`/metadata per contract and avoid infinite dead-letter cycles.

### 6.5. Differences Between Reject, Republish, and Recover

| Spring AMQP Mechanism | Source Message After Recoverer | Key Notes |
| --- | --- | --- |
| `AmqpRejectAndDontRequeueException` | Rejected with `requeue=false` at container | Broker DLX receives it if configured and routed properly |
| `RejectAndDontRequeueRecoverer` | Ends retries with matching reject | Useful when delegating DLX routing to the broker |
| `RepublishMessageRecoverer` | Recoverer actively publishes a new message to chosen exchange/routing key | Source message is normally treated as recovered and acked; **does not automatically traverse broker DLX** |
| `RepublishMessageRecovererWithConfirms` | Publishes and awaits publisher confirms per config | Reduces risk of acking source when target publish fails; still test failure modes |
| `ImmediateRequeueAmqpException` | Tells container to requeue immediately | Risks hot loops; use only when genuinely warranted |

If a recoverer only logs and returns normally, the container can ack the message and leave zero copies in the DLQ. When **preserving investigability** matters, test DLT/DLQ publish failure paths too—not only happy paths.

## 7. Spring Integration: `ErrorMessage` and `errorChannel`

Spring Integration revolves around `Message<?>`, channels, and endpoints. When an **asynchronous** step fails or a poller throws an exception, the framework can wrap the `Throwable` in `org.springframework.messaging.support.ErrorMessage` and send it to the message's **error channel** or the global channel named `errorChannel`.

~~~text
Message<OrderCreated> -> IntegrationFlow
    |       \
    |        \-- synchronous DirectChannel: exception may throw back to sender
    |
    +-- async ExecutorChannel / poller:
              exception -> ErrorMessage(Throwable)
                                  |
                             errorChannel
                                  |
                        log/incident/route/recovery
~~~

Monitoring listener example:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationFailureObserver {
    private final IntegrationIncidentService incidents;

    public IntegrationFailureObserver(IntegrationIncidentService incidents) {
        this.incidents = incidents;
    }

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();
        Message<?> failed = null;
        if (failure instanceof MessagingException messagingFailure) {
            failed = messagingFailure.getFailedMessage();
        }
        incidents.record(failure, failed);
    }
}

interface IntegrationIncidentService {
    void record(Throwable error, Message<?> failedMessage);
}
~~~

`errorChannel` is **an in-application error flow**, not automatically equivalent to a durable Kafka DLT or RabbitMQ DLQ. To retain failed messages for replay across restarts, explicitly publish them to a broker/incident store with confirm and retention policies. Note that `failedMessage` can sometimes be `null` or carry a transformed payload, so capture correlation/eventId at the intake boundary.

**The acknowledgment boundary is especially critical:** if a broker consumer forwards a message to an `ExecutorChannel` and returns immediately, the broker listener may treat processing as complete before the async task throws. Logging an `ErrorMessage` does not make the broker redeliver. Conversely, if a handler on a `DirectChannel` throws synchronously, it can propagate back to the listener container for Kafka/RabbitMQ error handling. For true broker retries, align ack ownership, transactions, channels, and completion checkpoints.

With a poller configured with an `errorChannel`, exceptions route to that channel within the scheduled task. To route by exception type, use `ErrorMessageExceptionTypeRouter` or a classifying service activator, ensuring messages are not silently dropped by a handler that merely logs and returns.

### 7.1. Placing Error Handlers at the Right Layer

| Layer | Primary Error Handler | Characteristics |
| --- | --- | --- |
| HTTP client | Status handlers, exception mapping, retry/circuit breaker | Sees 4xx/5xx or response-less timeouts |
| Spring Integration async endpoint | `ErrorMessage` via `errorChannel` | Decides in-app routing/logging/recovery |
| Kafka listener container | `CommonErrorHandler`, retry topics/DLT | Controls record retries and offset commits |
| Rabbit listener container | Retry interceptor, reject/nack, recoverers | Controls ack/requeue/DLX |
| DB/outbox | Transactions and unique keys | Blocks duplicate side effects, coordinates publishing |
| Replay job | Audit, authorization, rate limits, idempotency | Reintroduces failed messages after investigation |

Avoid configuring both `IntegrationFlow` and the listener container to retry the same call without accounting for combined attempts and timeouts. Each exception class needs one clear **policy owner**.

## 8. Controlled Replay / Redrive

Dead-letter storage is an **investigation staging area**, not proof that messages can be automatically re-injected immediately. Replay only after fixing the root cause or repairing data under an auditable workflow.

### 8.1. Three Distinct Forms of Replay

| Form | Effect on Broker | When to Use |
| --- | --- | --- |
| **Read DLT/DLQ and republish** | Creates a new message in target topic/queue; must confirm publish before marking moved | Replaying a specific investigated batch of messages |
| **Kafka offset reset/seek** | Consumer group re-reads retained history without appending new records | Recovering a time/offset range after fixing consumer logic |
| **Rebuild from source-of-truth/outbox** | Re-emits events from durable source state | When DLT expired, schemas require conversion, or state must reconcile |

A Kafka offset is **not a business message ID**. If a DLT consumer republishes a record back to `orders.events`, it receives a **new offset** and potentially a new partition if partitioning changed. Resetting a consumer group to an older offset replays all records in that window, including already-succeeded ones; enforce idempotency before resetting.

In RabbitMQ, consuming from a DLQ and republishing removes the message from the DLQ per the **replay consumer's** acknowledgment; there is no built-in atomic “move” spanning two separate queues and external HTTP/DB state. Use publisher confirms/returns, acking the DLQ only after target publication is confirmed per policy, and accept that duplicates can still arise after crashes.

### 8.2. Pre-Replay Checklist

1. **Scope tightly:** specify topic/queue, partition/offset range, or explicit incident IDs; never blindly “replay everything.”
2. **Confirm root cause:** schema mismatch, app bug, broker, or downstream? Was the fix deployed?
3. **Verify contract:** is the payload still valid under the newer consumer schema, or does it need transformation while preserving the original trace?
4. **Enforce idempotency:** unchanged `eventId`; inbox/DB unique constraints; HTTP calls using the same idempotency key or reconciliation; reprocessing must not overwrite newer state.
5. **Check ordering:** older records may follow newer ones; apply version checks or conditional updates where needed.
6. **Throttle load:** cap concurrency, batch size, throughput, backoff, and max messages so redrive does not overload production.
7. **Record audit trail:** requester/automation, approvals (if required), timestamp, scope, code commit/version, reason, and success/failure counts.
8. **Define stop criteria:** halt if error rates spike, DLQs refill, downstream saturates, or duplicate ratios exceed thresholds.

Replay should not be run by a DLT consumer that **automatically** republishes every message immediately: if the underlying bug remains unfixed, messages ping-pong between the DLT and source infinitely while masking the outage.

### 8.3. State Machine for a Replay Job

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED: Message enters DLT/DLQ
    QUARANTINED --> READY: Investigated and policy approved
    READY --> CLAIMED: Replay worker acquires lease
    CLAIMED --> PUBLISHING: Begins republish
    PUBLISHING --> SUBMITTED: Broker confirm succeeds
    PUBLISHING --> RETRY_PENDING: Publish error/timeout
    RETRY_PENDING --> CLAIMED: Backoff + valid lease
    SUBMITTED --> VERIFIED: Consumer reprocessed cleanly
    SUBMITTED --> QUARANTINED: Failed again, new incident opened
    VERIFIED --> [*]
~~~

`SUBMITTED` only indicates the broker accepted the replayed message; it does **not** mean the target consumer completed business processing. Transitioning to `VERIFIED` requires evidence from business state, outbox/inbox, or result messages. Persist every state durably so another worker can recover if the process crashes.

### 8.4. Example: Republishing to Kafka with the Original Key

Once an incident is approved for replay, a service can re-emit the raw JSON using the same aggregate key:

~~~java
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

record ReplayCandidate(
        String incidentId,
        String eventId,
        String aggregateId,
        String rawJson) {
}

@Service
public class KafkaReplayPublisher {
    private final KafkaTemplate<String, String> template;

    public KafkaReplayPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<RecordMetadata> publish(
            ReplayCandidate candidate) {
        // Caller must validate replay scope, throttle rate,
        // and persist PUBLISHING/SUBMITTED state in the incident store.
        return template
                .send("orders.events",
                      candidate.aggregateId(), candidate.rawJson())
                .thenApply(SendResult::getRecordMetadata);
    }
}
~~~

The caller marks `SUBMITTED` **only** when the future succeeds; if it fails, leave state retryable. If the broker appended the record before the client disconnected, the next attempt can produce a duplicate record: consumers must deduplicate by `eventId`. If serializers, schemas, or partitioning rules changed, validate compatibility before replaying instead of injecting incompatible payloads into live topics.

To trace a replay without altering `eventId`, attach a **separate header** such as `replayRunId`/`originalIncidentId` (allowlisted and free of PII). Never replace `eventId` with a new UUID merely to bypass consumer duplicate detection, as that corrupts business semantics.

### 8.5. RabbitMQ Redrive from DLQ

A replay worker can consume `orders.dlq` in **manual ack** mode and execute:

~~~text
1. Receive DLQ delivery, hold deliveryTag.
2. Check replay policy, schema, and requestId/eventId.
3. Publish to original exchange with target routing key,
   add replayRunId header, keep business key, and use persistent delivery.
4. Await publisher confirm; check unroutable return (mandatory) if enabled.
5. Only after target publish confirms, basic.ack the DLQ delivery.
6. On publish error / connection loss: do not ack; let broker redeliver,
   relying on inbox/idempotency if publish actually succeeded.
7. Write audit record, update incident, and monitor end-to-end processing.
~~~

This is an **algorithm**—`RabbitTemplate.convertAndSend(...)` does not by itself provide an atomic queue-move transaction. With Spring AMQP publisher confirms, verify both publication and routing when `mandatory` returns are active. When the source is a quorum queue, account for delivery limits so replay workers do not turn temporary faults into toxic loops.

### 8.6. When to Halt Replay

Do not replay when the root cause is unknown, when schemas changed incompatibly without a converter, when downstream remains broadly degraded, when strict ordering is required yet no ordering plan exists, or when replaying would corrupt current business state. Choose **longer quarantine or business compensation** rather than blindly re-injecting stale messages.

## 9. Testing: Verify Effects, Not Just Exceptions

In Spring Boot, organize policy tests across layers: unit tests for classifiers/processors; integration tests against real Kafka/RabbitMQ via Testcontainers or equivalent; failure tests simulating consumer crashes, DLT publish failures, and downstream timeouts. Never mock `KafkaTemplate`/`RabbitTemplate` alone and conclude broker dead-lettering works.

### 9.1. Minimum Test Matrix

| Test Case | Trigger | Expected Observation |
| --- | --- | --- |
| Valid event | Has `eventId`, supported schemaVersion | Processed once normally; ack/committed per policy |
| Invalid contract | Bad JSON, missing `orderId` | Downstream untouched; routed to DLT/DLQ with clear reason |
| Transient HTTP failure | 503 on first 2 attempts, then 200 | Exact retry/backoff count; succeeds without DLT |
| Retries exhausted | Downstream always 503 | Single logical record parked in DLT/DLQ with metadata; no infinite loop |
| Ambiguous timeout | POST received, response timed out | Retried with same idempotency key; only one order created |
| DB commit then crash | Kill consumer before ack/commit | Broker redelivers; unique key/inbox blocks second side effect |
| DLT topic lacks partition | Recoverer targets missing partition | Recovery fails rather than marking succeeded; alerts and retains retryability |
| Rabbit DLX lacks binding | Reject with `requeue=false` | Test catches missing DLQ entry; deployment pipeline blocks release |
| Continuous Rabbit requeue | Prolonged downstream failure | Delivery limit/backoff enforced; no hot loop |
| Kafka non-blocking order | Record A fails, record B same key follows | Out-of-order behavior measured; business version/conditional update guards result |
| Consumer restart/rebalance | Stop pod mid-processing | No committed-delivery loss; accurate side-effect count |
| Replay same event | Pick DLT record and republish | `eventId` kept; `replayRunId` & audit written; no duplicate results |
| DLT/DLQ retention | Approach expiry or quota limit | Alert fires before investigative data disappears |
| Message with PII | DLT stores failure and payload | Tokens/passwords/sensitive stack traces scrubbed; retention/access enforced |

### 9.2. Counting Actual Attempts

Tests must distinguish the **initial execution** from **retries**. For example, `FixedBackOff(1000L, 2L)` runs 3 total attempts, whereas `@RetryableTopic(attempts="4")` runs 4 attempts. Count attempts via a stubbed downstream adapter rather than counting logged exception lines, which frameworks may emit at multiple layers.

Use bounded waits in tests since brokers involve backoffs and polling; rely on Awaitility or deadline-based polling. On test failure, inspect source/DLT records, consumer offsets, ready/unacked counts, incident stores, retry-topic configs, and broker logs. Test **DLT publish failures** too; otherwise the most dangerous silent-loss path goes untested.

### 9.3. Testing Ordering and Duplicates

Inject an ordered sequence sharing `aggregateId`: `OrderCreated(v1)`, `OrderPaid(v2)`, `OrderCancelled(v3)`; fail `v1` temporarily while letting `v2` and `v3` proceed in retry-topic mode. Verify whether consumers enforce versions or corrupt state. Where order is mandatory, detect version gaps and defer/reconcile instead of assuming Kafka partition order holds across separate retry topics.

Duplicate tests must inspect **DB rows, HTTP side effects, and broker outputs**, because invoking a listener twice is normal under at-least-once. Success means **no extra logical side effects**, not “the listener ran only once.”

## 10. Observability and Operational Runbooks

### 10.1. Recommended Metrics and Logs

| Signal | Meaning | Alerting Hint |
| --- | --- | --- |
| `messages_processed_total{topic,result}` | Successes, valid rejections, transient errors | Rapid jump in error rate |
| `message_processing_duration_seconds{consumer}` | Business processing latency | P95/P99 exceeds budget |
| `message_retry_attempts_total{reason}` | Retry pressure | Sudden spike or retry storm |
| `message_dead_letter_total{reason}` | Records entering DLT/DLQ | Steady growth, especially schema errors |
| `dlt_publish_failures_total` | Unable to quarantine failing records | Urgent alert for data-loss or stall risk |
| `dead_letter_backlog` and `oldest_age_seconds` | Size and age of unresolved messages | Approaching retention or recovery SLA |
| Kafka consumer lag | Gap between log end and processed offset | Sustained lag or stalled partition |
| Rabbit ready/unacked | Queued vs. in-flight messages | Queue backup; poor prefetch/concurrency tuning |
| `replay_submitted_total` / `replay_verified_total` | Separates resubmissions from business completion | High submitted vs. low verified |
| `duplicate_suppressed_total` | Idempotency catching duplicates | Unexpected spike may indicate ack/retry failures |

These metric names are **application-level suggestions**, not automatic built-ins across all Spring Boot/broker setups. Use low-cardinality tags such as topic, consumer group, operation, and failure kind; avoid putting `eventId`, raw payloads, request IDs, or exception messages into metric labels. Logs/traces can include correlation IDs under proper access/retention controls, while excluding credentials, tokens, or personal data from DLT headers.

### 10.2. Runbook When DLT/DLQ Grows

1. Identify which topic/queue is growing, the dominant error, start time, and active producer/consumer versions.
2. Check lag, retry counts, HTTP/DB/broker health, disk/quotas, and DLQ/DLT publish success.
3. Separate **contract errors** from **infrastructure errors**; stop any retry storm before fixing schemas.
4. Assess whether data was lost or side effects already ran; reconcile using business idempotency keys/outboxes.
5. Fix the cause, deploy, and run a canary replay on a few selected failed events; verify clean handling before scaling up replay.
6. Replay in rate-limited batches, monitoring submitted/verified/failures; halt if new errors, overload, or ordering drift appear.
7. Close the incident with evidence; reconcile source vs. target to catch any missing records.

### 10.3. Design Mistakes to Avoid

**1. Infinite retries:** never terminates on schema errors, wedging partitions/queues and exhausting threads. Enforce attempt limits, time budgets, and dead-letter policies.

**2. Treating DLQ like a delete bucket:** setting `requeue=false` without a valid DLX/binding or DLT topic and assuming messages are saved. Verify publish/route/confirm in deployment tests.

**3. Swallowing exceptions before broker ack:** a `try/catch` that only logs lets the listener return normally, committing offsets or acking queue messages and vanishing errors from recovery. When intentionally quarantining, verify the incident/failed message persisted before returning cleanly.

**4. Regenerating business IDs on replay:** assigning a fresh UUID per attempt breaks idempotency and causes double charges or duplicate shipments. Replays must keep logical IDs and only add replay metadata.

**5. Assuming ordering survives retry topics:** records moved to another topic can return after newer events. Add version gating or pick another retry strategy.

**6. Retrying at every layer:** HTTP client, Spring service, consumer, and broker all retrying multiplies traffic exponentially. Assign one retry owner and enforce an end-to-end attempt budget.

**7. Assuming dead-lettering is always durable:** DLX, DLT publishing, and acks each have failure modes. Verify partitions, bindings, permissions, publisher confirms, serializers, and retention.

**8. Letting DLTs retain PII indefinitely:** error stores remain subject to authorization, encryption, privacy, and retention rules; strip stack traces and sensitive fields from headers.

## 11. Takeaways and Self-Check Questions

A reliable messaging system preserves three distinct boundaries:

- **Broker delivery:** was a record acked/committed, requeued, or routed to DLT/DLQ per policy?
- **Business effect:** can messages be delivered multiple times without duplicating effects in DBs, HTTP APIs, or downstream brokers?
- **Operational recovery:** do we know why it failed, store enough context to fix it, and replay within a controlled scope?

Self-check:

1. Why does `DefaultErrorHandler(new FixedBackOff(1000, 2))` not mean two total executions?
2. Why can Kafka non-blocking retries break ordering for the same aggregate key?
3. In RabbitMQ, what happens if you reject with `requeue=false` when no DLX exists?
4. Why is Spring Integration's `errorChannel` not automatically equivalent to a DLT/DLQ?
5. Why must a POST timeout be treated as an “uncertain outcome”?
6. Why does publishing from a DLT back to the source topic create a new offset while `eventId` must remain unchanged?
7. What proves a replay is **verified** rather than merely **submitted**?

## References

- [Spring Kafka — Handling Exceptions / DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka — Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)
- [Spring Kafka — Retry Features and Backoff](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring AMQP — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Quorum Queues and At-Least-Once Dead Lettering](https://www.rabbitmq.com/docs/quorum-queues)
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
