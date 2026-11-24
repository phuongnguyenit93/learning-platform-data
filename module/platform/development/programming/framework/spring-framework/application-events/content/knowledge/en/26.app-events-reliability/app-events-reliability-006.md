# Forwarding Internal Events to a Message Broker in Spring Application Events

## 1. Why Forward Events Outside the Application?

Spring Framework provides `ApplicationEventPublisher` so one component can emit an event and other components within the **same ApplicationContext/process** can react. For example, upon creating an order successfully, the application emits `OrderCreated`; one listener updates read data, and another prepares an email.

This mechanism helps reduce direct coupling between modules, but **is not a durable message broker**:

- Events are normally dispatched in memory; process death can lose unprocessed work.
- By default `@EventListener` is invoked synchronously; a failing listener can affect the publisher.
- An `@Async` listener can run on another pool, but tasks in an executor do not automatically survive a restart.
- Other systems do not automatically receive an event merely because the application called `publishEvent(...)`.
- Spring events do not provide broker acknowledgements, dead-letter queues, replays, or consumer offsets out of the box.

When the business needs to notify **another service**, such as Billing, Shipping, or Analytics, we typically add an **integration adapter** to translate the internal domain/application event into an **integration event** following a data contract and send it to RabbitMQ, Kafka, or an equivalent broker.

This lesson explains how to structure the adapter, presents a **runnable Spring Boot + RabbitMQ** demo, and then analyzes the reliability levels of three sending approaches: direct, post-commit, and **transactional outbox**.

## 2. Distinguishing Internal Events, Integration Events, and Broker Messages

| Component | Role | Example |
| --- | --- | --- |
| Internal/domain event | A fact that happened inside the domain model | `OrderCreated(orderId, amount)` |
| Application event mechanism | Distributes objects across beans in one Spring context | `publisher.publishEvent(event)` |
| Integration adapter/bridge | Converts, versions, serializes, and sends data externally | `OrderEventBridge` |
| Integration event | Stable exchange contract across services | `order.created.v1` with `eventId` |
| Message broker | Receives, routes, stores/retains, and delivers messages per config | RabbitMQ exchange/queue, Kafka topic |
| Consumer | Reads messages and performs work with error/duplicate controls | `@RabbitListener` or `@KafkaListener` |

**Do not send raw JPA entities or Spring `ApplicationEvent` objects over a broker** and force other services to deserialize internal domain classes. That creates tight coupling to Java packages, lazy-loading, entity structures, and serializers, and may accidentally expose sensitive fields.

An adapter should map from the in-application event to **wire-stable** data:

```text
Aggregate/Application Service
  |
  v
publishEvent(OrderCreated)
  |
  v
Spring @EventListener / adapter
  |
  +--> map internal -> integration event v1
  +--> JSON/Avro/Protobuf serialization
  +--> broker routing/partition key
  |
  v
RabbitMQ exchange / Kafka topic
  |
  v
Billing/Shipping service consumer
```

This is a **message flow architecture**; it does not imply the source transaction and the broker send belong to one atomic transaction.

## 3. Three Options and Their Reliability Levels

### Option A — Sending Directly Inside @EventListener

```text
@Transactional service
  UPDATE orders
  publishEvent(OrderCreated)
    -> @EventListener
       -> rabbitTemplate.convertAndSend(...)
  COMMIT
```

Pros: minimal code, easy to test. Key drawback: the message can be sent externally **before the DB transaction commits**. If the DB rolls back, consumers may receive an event stating an order was created even though no record exists.

If there is no transaction and only best-effort notification is wanted, a simple bridge can be acceptable **when the business agrees to the risk of event loss**. Never use it as the default for payments, inventory reservations, or state changes that require guarantees.

### Option B — Sending After Commit with @TransactionalEventListener

```text
@Transactional service
  UPDATE orders
  publishEvent(OrderCreated)
  COMMIT
    -> @TransactionalEventListener(AFTER_COMMIT)
       -> rabbitTemplate.convertAndSend(...)
```

Pros: avoids sending events for rolled-back transactions. Drawback: a **gap for event loss** remains if the process dies after the DB commits but before sending to the broker. Successfully publishing to the broker also does not automatically guarantee the consumer finished processing.

Note: by default `@TransactionalEventListener` **is not invoked when an event is published outside an active transaction**, unless `fallbackExecution=true` is enabled. You cannot swap `@EventListener` for this annotation in an in-memory demo and still expect it to run without opening a transaction.

### Option C — Transactional Outbox

```text
DB transaction:
   UPDATE orders ...
   INSERT INTO outbox_events ...
   COMMIT
                  |
                  v
Outbox worker / CDC (after commit)
                  |
                  v
Broker -> Consumers
```

Pros: the business change and the **intent to send the event** are persisted in the **same DB transaction**. When the broker is temporarily unavailable or the process restarts, the worker can re-read unsent events and continue.

In return, an outbox requires a relay worker/CDC, retry state, idempotency, monitoring, and cleanup. It is typically chosen for critical business events where losing a notification is unacceptable.

**Decision rule:** `AFTER_COMMIT` solves *not sending on rollback*; an **outbox** additionally solves *durably recording the intent to send*. Both still require safeguards against duplicate processing and consumer failures.

## 4. Designing the Integration Event Contract

Example JSON message published to RabbitMQ:

```json
{
  "eventId": "evt-001",
  "eventType": "order.created",
  "schemaVersion": 1,
  "orderId": "ORD-101",
  "amountMinorUnits": 12500,
  "occurredAt": "2026-11-11T06:00:00Z"
}
```

Each field serves a distinct role:

- **`eventId`:** ID of a single occurrence, used for tracking and deduplication. Retries of the **same event** must preserve the same ID.
- **`eventType`:** name of the business fact, independent of Java class names.
- **`schemaVersion`:** version of the payload structure and semantics, not the application or aggregate version.
- **`orderId`:** object identifier so consumers can correlate and potentially use it as a routing/partition key.
- **`amountMinorUnits`:** monetary amount in the defined minor units. In multi-currency systems, add `currency` or define the contract explicitly.
- **`occurredAt`:** UTC/ISO-8601 timestamp when the event occurred; not when the consumer received it.

An event may carry `correlationId`, tenant ID, aggregate version, or trace metadata when needed, but **do not turn an integration event into a dump of every domain entity field**. Send only data that consumers are authorized and need to use.

The contract should specify required fields, `null` handling, units, enums, versioning, and compatibility policies. When multiple services deploy independently, prefer stable event types/schemas and contract tests rather than relying on Java class names from the producer.

### Organizing Names and Routing

In RabbitMQ, producers typically send to an **exchange** with a **routing key**; queues are owned by consumers and bound to the exchange.

```text
                    exchange: shop.events
                              |
           routing key: order.created.v1
                       /                \
                      v                  v
      shop.billing.order-created    shop.analytics.order-created
                      |                  |
               Billing consumer     Analytics consumer
```

Two independent queues for two consumer groups let each group process/retry at its own pace. If multiple Billing instances consume **one queue**, RabbitMQ distributes messages across competing consumers on that queue rather than broadcasting each message to every instance.

Kafka has a topic/partition/consumer-group model that differs from RabbitMQ exchanges/queues; **do not transfer routing and acknowledgement concepts verbatim** between the two brokers without redesigning.

## 5. Runnable Project: Spring Boot Sending Internal Events to RabbitMQ

The example uses **Java 17+, Spring Boot 3.3.13, RabbitMQ, and Jackson JSON**. Versions are pinned for reproducibility; for production, choose currently supported Spring Boot and RabbitMQ branches and verify compatibility.

The demo puts both producer and consumer in one application for ease of learning. In real deployments, the two sides typically live in **two independent services**, sharing an integration schema rather than domain objects.

### 5.1. Expected Behavior to Observe

1. `CommandLineRunner` publishes the internal record `OrderCreated` via `ApplicationEventPublisher`.
2. An `@EventListener` converts that record into version 1 of `OrderCreatedMessage`.
3. `RabbitTemplate` serializes the message into a JSON string and sends it to exchange `shop.events` with routing key `order.created.v1`.
4. The durable queue `shop.billing.order-created.v1` is bound to the exchange.
5. `@RabbitListener` receives the message, deserializes the JSON, and prints the data.
6. `CountDownLatch` lets the runner wait for the consumer in the demo; no fixed sleep is used.

### 5.2. Directory Structure

```text
internal-event-to-rabbitmq/
├── compose.yaml
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/EventToRabbitDemo.java
    │   └── resources/application.properties
    └── test/
        └── java/example/events/BridgeMappingTest.java
```

### 5.3. compose.yaml

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

Run Docker Compose in the project directory:

```bash
docker compose up -d
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

Wait until the broker is ready before running the app. The local management UI can be opened at `http://localhost:15672`, with default demo credentials `guest/guest` when the broker uses its default configuration. **Use these credentials only on a local machine**; never expose management/broker ports to the Internet or use demo settings in production.

### 5.4. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>internal-event-to-rabbitmq</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-amqp` provides Spring AMQP/RabbitMQ and auto-configuration for `RabbitTemplate`, listener containers, and `RabbitAdmin`. `spring-boot-starter-json` provides Jackson for writing and reading JSON; the example intentionally keeps the wire contract in a dedicated integration record.

### 5.5. application.properties

```properties
spring.main.web-application-type=none

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=guest
spring.rabbitmq.password=guest

# Demo only. On error, do not requeue infinitely.
# No DLX yet, so rejected messages may be discarded.
spring.rabbitmq.listener.simple.default-requeue-rejected=false

logging.level.root=WARN
```

Setting `default-requeue-rejected=false` here makes failures easy to observe instead of falling into an infinite redelivery loop. **It does not turn a failed message into a safely parked pending message**: because the demo has not configured a dead-letter exchange, a message rejected without requeue may be discarded. For production, design a DLX/DLQ/quarantine and explicit retry policies.

### 5.6. EventToRabbitDemo.java

```java
package example.events;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
@EnableRabbit
public class EventToRabbitDemo {

    public static final String EXCHANGE = "shop.events";
    public static final String ROUTING_KEY = "order.created.v1";
    public static final String QUEUE =
            "shop.billing.order-created.v1";

    // Internal event: plain Java POJO/record, NOT an AMQP message.
    public record OrderCreated(
            String eventId,
            String orderId,
            long amountMinorUnits,
            Instant occurredAt) {
    }

    // JSON contract sent to other services.
    public record OrderCreatedMessage(
            String eventId,
            String eventType,
            int schemaVersion,
            String orderId,
            long amountMinorUnits,
            String occurredAt) {
    }

    public static final class EventBridge {
        private final RabbitTemplate template;
        private final ObjectMapper mapper;

        public EventBridge(
                RabbitTemplate template, ObjectMapper mapper) {
            this.template = template;
            this.mapper = mapper;
        }

        // Pure mapping: easy to test without needing RabbitMQ.
        public static OrderCreatedMessage map(OrderCreated domain) {
            Objects.requireNonNull(domain, "domain");
            return new OrderCreatedMessage(
                    domain.eventId(),
                    "order.created",
                    1,
                    domain.orderId(),
                    domain.amountMinorUnits(),
                    domain.occurredAt().toString());
        }

        @EventListener
        public void on(OrderCreated domain) {
            OrderCreatedMessage message = map(domain);
            String json;

            try {
                json = mapper.writeValueAsString(message);
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException(
                        "Cannot serialize OrderCreated", ex);
            }

            System.out.println(
                    "BRIDGE_SEND eventId=" + message.eventId());

            // Keep wire message as String so SimpleMessageConverter
            // on the consumer side receives it as text.
            template.convertAndSend(
                    EXCHANGE,
                    ROUTING_KEY,
                    json,
                    amqpMessage -> {
                        amqpMessage.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return amqpMessage;
                    });
        }
    }

    public static final class BillingConsumer {
        private final ObjectMapper mapper;
        private final CountDownLatch consumed;

        public BillingConsumer(
                ObjectMapper mapper, CountDownLatch consumed) {
            this.mapper = mapper;
            this.consumed = consumed;
        }

        @RabbitListener(queues = QUEUE)
        public void onMessage(String body) {
            final OrderCreatedMessage message;

            try {
                message = mapper.readValue(
                        body, OrderCreatedMessage.class);

                if (message.schemaVersion() != 1
                        || !"order.created".equals(
                                message.eventType())) {
                    throw new IllegalArgumentException(
                            "Unsupported event schema/type");
                }
            } catch (JsonProcessingException
                    | IllegalArgumentException ex) {
                throw new AmqpRejectAndDontRequeueException(
                        "Invalid integration message", ex);
            }

            // Demo logs only; production needs transactions/idempotency
            // for real side effects before letting the container ACK.
            System.out.printf(
                    "BROKER_CONSUMED eventId=%s orderId=%s"
                            + " amount=%d version=%d%n",
                    message.eventId(),
                    message.orderId(),
                    message.amountMinorUnits(),
                    message.schemaVersion());

            consumed.countDown();
        }
    }

    // Broker topology: durable exchange, queue, and binding.
    @Bean
    TopicExchange shopExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding billingBinding(
            Queue billingQueue, TopicExchange shopExchange) {
        return BindingBuilder.bind(billingQueue)
                .to(shopExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    CountDownLatch receivedLatch() {
        return new CountDownLatch(1);
    }

    @Bean
    EventBridge eventBridge(
            RabbitTemplate template, ObjectMapper mapper) {
        return new EventBridge(template, mapper);
    }

    @Bean
    BillingConsumer billingConsumer(
            ObjectMapper mapper, CountDownLatch receivedLatch) {
        return new BillingConsumer(mapper, receivedLatch);
    }

    @Bean
    CommandLineRunner demo(
            ApplicationEventPublisher publisher,
            CountDownLatch receivedLatch) {
        return args -> {
            System.out.println("APP_PUBLISH orderId=ORD-101");

            publisher.publishEvent(new OrderCreated(
                    "evt-001",
                    "ORD-101",
                    12500,
                    Instant.parse("2026-11-11T06:00:00Z")));

            if (!receivedLatch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Consumer did not receive event in time");
            }

            System.out.println("APP_CONSUMED=true");
        };
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             EventToRabbitDemo.class, args)) {
            // Demo runs and waits for consumer, then closes context.
        }
    }
}
```

### 5.7. Building and Running

Start the broker first with `docker compose up -d`, verify RabbitMQ is ready, and then run:

```bash
mvn -q package
java -jar target/internal-event-to-rabbitmq-1.0.0.jar
```

Lines **printed by the demo code itself** when the broker is running and the message is processed successfully:

```text
APP_PUBLISH orderId=ORD-101
BRIDGE_SEND eventId=evt-001
BROKER_CONSUMED eventId=evt-001 orderId=ORD-101 amount=12500 version=1
APP_CONSUMED=true
```

Spring/RabbitMQ may print additional logs of their own. In the example:

- `APP_PUBLISH` happens before calling the Spring publisher.
- `BRIDGE_SEND` prints before the bridge calls `RabbitTemplate.convertAndSend(...)`.
- `BROKER_CONSUMED` appears on the Rabbit listener container thread after the broker actually routes the message into the queue.
- `APP_CONSUMED=true` only appears after the consumer calls `CountDownLatch.countDown()`. The latch preserves output order in the demo; it **does not replace ACKs or business confirmation in a real system**.

If the broker is not started, misconfigured, or the message does not arrive, the program may report connection/timeout errors instead of printing the output above. The `BRIDGE_SEND` line **does not prove RabbitMQ accepted the message**, since it is printed before the send call; confirming broker acceptance requires publisher confirms/returns, covered below.

Stop the demo:

```bash
docker compose down
```

If you want to keep messages/queues after the container is removed, configure a durable Docker volume for RabbitMQ data; merely marking a queue durable does not preserve data when the container's entire storage is deleted.

### 5.8. Why Is This Only a Basic Bridge Example?

The demo intentionally omits database transactions/outbox, publisher confirms, consumer idempotency, and a real DLQ. It only proves **an internal event is converted and sent through RabbitMQ**, and then a consumer receives the message. Do not treat this demo as a pattern guaranteeing exactly-once or end-to-end reliability.

## 6. Unit Testing the Mapping Without a Broker

File `src/test/java/example/events/BridgeMappingTest.java`:

```java
package example.events;

import java.time.Instant;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BridgeMappingTest {

    @Test
    void internalEventMapsToStableIntegrationContract() {
        var domain = new EventToRabbitDemo.OrderCreated(
                "evt-123", "ORD-123", 7350L,
                Instant.parse("2026-11-11T06:00:00Z"));

        var message = EventToRabbitDemo.EventBridge.map(domain);

        assertEquals("evt-123", message.eventId());
        assertEquals("order.created", message.eventType());
        assertEquals(1, message.schemaVersion());
        assertEquals("ORD-123", message.orderId());
        assertEquals(7350L, message.amountMinorUnits());
        assertEquals(
                "2026-11-11T06:00:00Z",
                message.occurredAt());
    }
}
```

Run:

```bash
mvn -Dtest=BridgeMappingTest test
```

This test only operates on Java records and pure mapping, so **it does not require RabbitMQ to be running**. When successful, Maven Surefire passes one JUnit test method. It verifies the v1 JSON contract is constructed accurately from the domain event, yet **does not prove the exchange/binding/consumer work**. That part must be verified by running the demo with RabbitMQ or integration testing with a real broker (for example, using Testcontainers).

For production, add tests ensuring the mapper:
- Does not change `eventId` when an event is republished.
- Preserves currency minor units and UTC timestamps.
- Does not leak sensitive fields from the aggregate into the integration event.
- Does not break the v1 schema when an internal field is renamed.
- Handles unsupported event types/schema versions with deliberate error flows.

## 7. @TransactionalEventListener(AFTER_COMMIT) and Its Limitations

In a database-backed application, when you want to send to the broker **only after DB commit**, you can replace the bridge listener with this pattern:

```java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    rabbitPublisher.send(mapToIntegrationMessage(event));
}
```

**This is an illustrative snippet**, not code to drop directly into section 5's demo: the method assumes `OrderCreated`, `rabbitPublisher`, and `mapToIntegrationMessage(...)` exist, and must reside in a Spring bean. The event must be published while **a transaction is active**.

Example application service:

```java
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        repository.save(order);
        publisher.publishEvent(
                new OrderCreated(order.getEventId(),
                        order.getId(), order.getAmount(),
                        Instant.now()));
    }
}
```

This is also an **illustrative skeleton**, not part of section 5's project: `OrderRepository`, `Order`, `CreateOrderCommand`, and imports must be defined in a real DB application. The goal is to visualize the transaction boundary, not to paste pseudocode into the demo build.

One important point: **AFTER_COMMIT does not alter the already-committed DB transaction if sending fails**. When the post-commit callback runs, if the broker is disconnected, the order remains saved while the event may not yet have reached the broker. If the process dies right after commit before the callback completes, there is no durable queue to continue.

If `@TransactionalEventListener` is used to write new DB state after commit, some transaction resources still bound to the thread can cause confusion. For new DB writes, use a service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` via a Spring proxy or `TransactionTemplate`; do not assume the old transaction can still commit.

**Avoid setting `fallbackExecution=true` casually:** it causes the callback to run even without a transaction, altering the "send only after commit" contract.

## 8. Transactional Outbox: How to Reduce Event Loss Risk

Persist the **business change** and the **outbox record** in one transaction on the **same database**:

```sql
BEGIN;

INSERT INTO orders (id, status, amount_minor)
VALUES ('ORD-101', 'CREATED', 12500);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type,
    schema_version, payload_json, status)
VALUES (
    'evt-001', 'ORD-101', 'order.created',
    1, '{"eventId":"evt-001","eventType":"order.created"}',
    'NEW');

COMMIT;
```

This is **SQL pseudocode illustrating the write sequence**: simplified table/column names and JSON are not a ready-made schema from the demo. In practice, the payload needs all fields required by the integration contract, and the transaction must be managed consistently by the database/JDBC/JPA.

Relay flow:

```text
OrderService: @Transactional
    |
    +--> save Order
    +--> save OutboxEvent
    |
    v
DB COMMIT (atomic for both records)
    |
    v
Outbox relay / CDC reads NEW events
    |
    +--> serialize/send to broker
    +--> wait for broker confirm
    +--> mark SENT / ACK per policy
    |
    v
RabbitMQ / Kafka -> consumers
```

### Why Is an Outbox More Reliable?

If the DB transaction rolls back, **neither the order nor the outbox exists**. If the transaction commits, the outbox can be re-read by a worker after a restart. When the broker is temporarily unavailable, the worker preserves state and retries on schedule. That fixes the gap where "the order committed, yet the application event vanished in RAM".

### What Should an Outbox Record Contain?

Commonly useful fields:

| Field | Purpose |
| --- | --- |
| `event_id` (unique) | Identifies the event and prevents duplicate inserts |
| `aggregate_id` | Routing/ordering key per aggregate |
| `event_type`, `schema_version` | Consumer contract |
| `payload_json` | Message to send, semantically immutable |
| `created_at` | Time outbox row was written |
| `status` | NEW/IN_PROGRESS/SENT/FAILED... |
| `attempt_count` | Retry tracking |
| `next_attempt_at` | Retry schedule |
| `last_error` (truncated, no secrets) | Diagnostics |
| `locked_until`/lease (if needed) | Prevents multiple workers from claiming the same row |
| `published_at` | Audits when delivery was confirmed |

The relay can be implemented with polling SQL using safe claim/lease semantics or with change data capture (CDC). Which option fits depends on throughput, infrastructure, DB logs, and operational capabilities.

### A Crash Window Still Exists in the Relay

Suppose the relay sends a message successfully and the broker receives it, yet the process dies **before updating the outbox status to SENT**. On the next run it will resend the same message. Thus an outbox normally provides **at-least-once publication**, not end-to-end exactly-once. Consumers **must be idempotent**.

Do not mark the outbox SENT merely because `convertAndSend(...)` returned if you require assurance that the broker actually accepted the message. Combine publisher confirms/returns with policies for timeouts and indeterminate states.

## 9. Publisher Confirms and Publisher Returns in RabbitMQ

**Do not confuse send-API success with broker or consumer success.**

In Spring AMQP, `RabbitTemplate.convertAndSend(...)` can return after sending the request without knowing for sure that the broker accepted and routed it to the right queue. Two mechanisms help:

1. **Publisher confirm:** the broker sends an ACK/NACK for the publish; confirms at the broker level. It does **not** confirm the business consumer finished processing.
2. **Publisher return:** when a message is published with `mandatory` enabled and no matching queue exists to route to, the broker returns the message instead of silently dropping it as unroutable.

In Spring Boot, common configuration:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

When correlated confirms are enabled, use `CorrelationData` to link each publish with a callback or future. When returns and mandatory are enabled, register `RabbitTemplate.ReturnsCallback` or inspect returned messages attached to the correlation. Relay design must handle **NACKs, unroutable messages, timeouts, and indeterminate results**.

**API-orientation example (not a standalone program):**

```java
CorrelationData correlation = new CorrelationData(eventId);
rabbitTemplate.convertAndSend(
        exchangeName, routingKey, jsonBody, correlation);

var confirm = correlation.getFuture()
        .get(5, TimeUnit.SECONDS);

if (!confirm.isAck()) {
    throw new IllegalStateException(
            "Broker did not ACK publication");
}
```

The snippet above assumes the template has publisher confirms enabled, plus imports, variables, and handling for `InterruptedException`, `ExecutionException`, and `TimeoutException`. Checking ACK alone **is not enough** to detect unroutable messages without checking publisher returns under mandatory configuration. On timeout, the message **may have already been accepted by the broker**; retry using the same `eventId` and prepare for duplicates.

You should also avoid keeping a database transaction open waiting too long for a broker confirm. With an outbox relay, the worker typically operates **outside** the source business transaction and uses short transactions to claim/update status.

### Durable Is Not an Absolute Guarantee

- Durable exchanges and durable queues allow the broker to restore topology after a restart according to the broker's storage mechanism.
- Persistent delivery mode makes messages eligible for durable storage in an appropriate queue.
- Publisher confirms indicate the broker accepted the publish under its implemented mechanism.
- Factors like queue type (classic/quorum), replication, storage failures, HA, and shutdown behavior still affect real durability.

Never use the words `durable` or `persistent` alone to promise "messages can never be lost". Set SLOs for latency, durability, retention, and recovery tailored to the specific broker.

## 10. Consumer Acknowledgement, Redelivery, and DLQ

In RabbitMQ, messages flow through a queue and are received by consumers. With Spring AMQP, `@RabbitListener` typically runs inside a listener container with an acknowledgement mode. In `AcknowledgeMode.AUTO`, the container ACKs based on the callback outcome (unless configured otherwise), not because the method merely started.

Common outcomes:

- Handler finishes normally → container can ACK the message.
- Handler throws an exception → depending on retry/error handlers and requeue policy, the message may be redelivered, rejected, or dead-lettered.
- Consumer dies before ACK → broker may redeliver the unacked message to another consumer.
- Handler already executed the side effect but crashes before ACK → redelivery can create a duplicate side effect.

Therefore, **acknowledgement does not replace idempotency**, and broker at-least-once delivery does not automatically turn business logic into exactly-once.

### Poison Messages

A message with malformed JSON or an unsupported `schemaVersion` can fail every time. If infinite requeue is configured, it can create a sustained failure loop:

```text
consume -> deserialize fail -> requeue -> consume
        -> deserialize fail -> requeue -> ...
```

Classify errors:

| Error type | Suggested action |
| --- | --- |
| Downstream timeout/connectivity | Finite retries with backoff |
| HTTP 429/rate limit | Respect quotas and `Retry-After` |
| Unparseable JSON | Reject/quarantine and alert; do not requeue infinitely |
| Unsupported schema version | DLQ/quarantine; support migration or upgrade consumer |
| Violated business invariant | Do not infinitely retry the same payload |
| Duplicate already-processed eventId | Return success/idempotent skip; avoid second side effect |

Production should configure a **dead-letter exchange/queue** with retention, redelivery limits, alerts, and controlled replay paths. A DLQ does not solve the failure by itself; it holds the failure evidence for fixing/replaying.

The demo in section 5 sets `default-requeue-rejected=false` to prevent infinite failure loops, yet **has no DLQ**, so it is only suited for learning the mechanics.

## 11. Consumer Idempotency: Avoiding Double Writes or Double Sends

An integration event can be reprocessed due to broker redelivery, producer retries, or duplicate outbox relay sends. If a listener generates invoices, sends notifications, or deducts inventory, duplication can have severe consequences.

Common **inbox/dedup table** model:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

For a consumer updating the **same database**, recording the processed marker and applying the DB side effect can share the **same transaction**:

```text
BEGIN DB TRANSACTION
    INSERT processed_messages(consumer, event_id)
        -- unique key: already exists => duplicate
    UPDATE billing_projection ...
COMMIT

After DB processing commits successfully:
    allow listener container to ACK per configuration
```

On a duplicate key, the consumer can confirm the event was handled previously and skip safely **provided** the dedup record only commits after the DB side effect succeeds. Never commit a `processed` marker first and perform the side effect in a different transaction; crashing between the two steps causes retries to skip and loses work.

For side effects **outside the database** (payment APIs, email, shipping providers), you need downstream-supported idempotency keys, or another workflow/saga/secondary outbox to manage "sent but response lost" outcomes. A local DB transaction **cannot roll back an already-executed HTTP request**.

### Choosing an Idempotency Key

- Use `eventId` when a single business occurrence is redelivered; every retry keeps the same ID.
- Define an additional business key when a producer might emit a new event ID for the same state transition.
- Never use `threadName`, approximate timestamps, or a new random value per attempt as a deduplication key.
- When multiple independent consumers exist, the key can be **(consumerName, eventId)** so Billing and Analytics handle the same event with separate state.

Idempotency prevents duplicate side effects, but must be paired with unique constraints/atomic operations to avoid races when multiple workers process concurrently.

## 12. Ordering and Multiple Consumers

A message broker does not necessarily guarantee strict business ordering across multiple producers, partitions/queues, consumers, or retries.

Example events for one order:

```text
OrderCreated(orderId=ORD-7, aggregateVersion=1)
OrderPaid(orderId=ORD-7, aggregateVersion=2)
OrderCancelled(orderId=ORD-7, aggregateVersion=3)
```

Consumers may receive late events or reprocess earlier versions. If ordering is a strict requirement:

- With Kafka, consider partition key = `orderId` so events for the same aggregate generally land in the same partition; ordering still depends on producer/consumer settings and replays.
- With RabbitMQ, watch consumer concurrency on the queue, prefetch, requeue/redelivery, and concurrency limits.
- Add `aggregateVersion` or sequence numbers; consumers can detect stale events, missing events, or handle out-of-order delivery.
- In multi-service workflows, do not rely solely on "which message arrived first" to assert a valid state transition.

**SchemaVersion differs from aggregateVersion.** Two events can both have `schemaVersion=1` while having different `aggregateVersion` values; never use the payload schema version to order state transitions.

## 13. Comparing RabbitMQ and Kafka at the Integration Point

The mindset **internal event → integration event → broker** is shared, yet the APIs and delivery models differ:

| Aspect | RabbitMQ/Spring AMQP | Kafka/Spring Kafka |
| --- | --- | --- |
| Where producer sends | Exchange + routing key | Topic + optional key |
| Subscriber | Queue + `@RabbitListener` | Consumer group + `@KafkaListener` |
| Routing | Exchange bindings, routing key | Partitions, topic subscriptions |
| Deduplication | Consumer idempotency/inbox | Consumer idempotency; Kafka transactions cover only certain Kafka-to-Kafka flows |
| Send confirmation | Publisher confirms/returns | Producer futures/callbacks, broker acknowledgements |
| Replay | Depends on storage, DLQ, and application | Topic retention/offsets/replay |
| Ordering | Depends on queue/consumers/requeue | Per partition under proper conditions |

When using Spring Kafka, the adapter typically calls:

```java
// Schematic: requires KafkaTemplate, topic, and serializer.
kafkaTemplate.send(
        "order.created.v1", event.orderId(), payload);
```

This is **not part of the RabbitMQ demo code**. Spring Kafka sends are usually asynchronous; you must handle completion/failure instead of ignoring the future. If you must avoid losing events between a DB transaction and Kafka, transactional outbox/CDC remains an appropriate solution rather than assuming JDBC `@Transactional` turns into a safe distributed transaction with Kafka.

## 14. Testing Each Layer of the Pipeline

For accurate diagnostics, separate unit, integration, and failure testing:

### Mapping Unit Tests

- `OrderCreated` maps accurately to `OrderCreatedMessage`.
- `eventId`, `orderId`, and `amountMinorUnits` are preserved.
- Schema version, event type, and timestamp are correct.
- Sensitive fields are not leaked.
- If mapping fails, the callback emits the contractually expected exception or error state.

The `BridgeMappingTest` in section 6 illustrates this group.

### Integration Tests with a Real Broker or Testcontainers

Use an ephemeral RabbitMQ container in tests or an isolated test broker:

1. Start the broker, declare exchange, queue, and binding.
2. Publish a domain event via Spring's publisher; assert the consumer receives the right JSON.
3. Test an invalid routing key and returns/mandatory behavior.
4. Test consumer schema errors → reject/DLQ per configuration.
5. Ensure the listener is not accidentally registered twice.
6. Test consumer restarts, queue durability, and retained messages when the broker preserves storage.
7. Use timeout/latch assertions to avoid flaky tests; never just `Thread.sleep(100)` and assert "no message arrived".

### Transaction/Outbox Tests

With a real database:

| Scenario | Expected outcome |
| --- | --- |
| Business transaction commits | Order and outbox record both exist |
| Business transaction rolls back | Neither order nor outbox event exists |
| Broker temporarily unavailable | Outbox keeps unsent event; relay retries |
| Broker ACKs but relay crashes before updating SENT | Event may republish; consumer deduplicates |
| Consumer updates DB then crashes before broker ACK | Redelivery does not update DB twice |
| Unparseable event | Sent to DLQ/quarantine, no infinite loop |
| Schema v1 and v2 coexist | Consumer handles versions properly without guessing |
| Duplicate eventId | Only one side effect per transaction/idempotency |
| Scaling up consumers | Does not break per-aggregate ordering requirements |
| DLQ replay | Audited and idempotent when reprocessed |

**Important:** You cannot use a test asserting only that `rabbitTemplate.convertAndSend(...)` threw no exception to prove end-to-end delivery. That tests only a tiny piece of the send path.

## 15. Operations and Security

A reliable message-broker pipeline requires observability across **every stage**:

- **Producer:** internal events created, mapping errors, publish attempts, confirm ACK/NACKs, returns.
- **Outbox:** pending records, age of oldest event, next retry time, attempt counts, failed/stuck leases.
- **Broker:** queue depth/lag, unacked messages, throughput, dead-letter count, connection/channel health.
- **Consumer:** received, processed, failed, retry count, DLQ count, duplicates skipped, and end-to-end latency.

Tag metrics only with event type, consumer, outcome, and service; **never** attach `eventId` or `orderId` as tags because they cause massive cardinality. Detailed IDs belong in access-controlled logs/tracing.

For security: use TLS and dedicated credentials per service/vhost following least privilege, manage secrets with a proper system, restrict publish/consume permissions, and govern schemas and payload PII. Do not stuff entire entities or tokens into messages. Define retention, data deletion, encryption at rest, and handling of sensitive data inside DLQs.

For scalability: tune concurrency, prefetch, backpressure, retry delays, and broker resource limits based on actual load rather than just adding consumers. A persistently failing consumer can trigger retry storms, inflate lag, and overload the broker.

## 16. Common Design Mistakes

**1. Treating @EventListener as a durable message queue.** Normal Spring events live in the context's memory. They do not auto-replay after a restart.

**2. Sending to the broker before DB commit saying "OrderCreated".** On rollback, the integration event spreads false information. Separate transaction boundaries and choose `AFTER_COMMIT`/outbox.

**3. Thinking AFTER_COMMIT is enough to prevent event loss.** The process can die right after DB commit. Use an outbox when delivery truly matters.

**4. Sending whole JPA entities over the broker.** Tightly couples schemas to implementations, lazy-loading, and PII; use versioned immutable integration event DTOs.

**5. Lacking publisher confirms/returns when certainty is needed.** A send method returning does not prove the message routed into a queue, let alone that a consumer processed it.

**6. Ignoring consumer duplicates.** Redelivery and outbox relays can send the same event multiple times; design idempotency with stable keys.

**7. Retrying data errors forever.** Bad JSON or unknown versions do not heal themselves. Route to DLQ/quarantine and alert.

**8. Using one shared queue for every service needing the event.** When each service needs every event, use separate queues/groups per broker semantics; multiple consumers on one RabbitMQ queue are competing consumers.

**9. Marking outbox SENT before sending/confirming.** Crashes can lose notifications. Require clear status transitions and confirmation/retry rules.

**10. Treating a broker ACK as consumer success.** Publisher confirms only mean the broker accepted the publish; consumer outcomes are a separate step.

**11. Enabling @Async on a bridge and assuming it is reliable.** Executors still live in memory; there is no durable retry across crashes.

**12. Lacking pipeline observability.** You cannot tell whether an event was lost at producer, outbox, routing, consumer, or side effect. Add correlation IDs and per-stage metrics.

## 17. Production Readiness Checklist

1. Does the business truly need cross-service events, or are internal listeners enough?
2. Have **internal events and separate integration events** been chosen with explicit DTOs/`schemaVersion`?
3. Is **when the event is published** relative to transaction commit clearly defined?
4. If event loss is unacceptable, is there a transactional outbox or equivalent durable mechanism?
5. Does the outbox relay have claiming, retry/backoff, confirms, lease/cleanup, and crash recovery?
6. Does broker topology have the right exchanges/topics, routing/partition keys, and queues/consumer groups?
7. Does the producer distinguish ACK/NACK, unroutable messages, timeouts, and indeterminate states?
8. Do consumers have idempotency/deduplication to tolerate at-least-once delivery?
9. Are retryable errors separated from validation/schema errors with DLQ/quarantine configured?
10. Are schema compatibility, versioning, and retention/replay guaranteed?
11. Has per-aggregate ordering been tested under real concurrency?
12. Are there integration/failure tests for rollbacks, broker outages, crashes, duplicates, and DLQs?
13. Is there monitoring for pending outbox rows, consumer lag, DLQs, retries, and side-effect outcomes?
14. Are payloads and broker credentials protected under product security policies?
15. Are the limitations of an in-process demo understood when splitting producer and consumer into independent services?

**Conclusion:** Forwarding internal events to a message broker is not just replacing `publishEvent(...)` with `rabbitTemplate.convertAndSend(...)`. You must define the **integration event contract**, determine transaction boundaries, choose a sending strategy matching the reliability bar, handle ACKs/returns/retries, and ensure consumers are idempotent. For critical business workflows, **DB transaction + outbox + broker + idempotent consumer** is usually a much sounder foundation than direct-sending listeners.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, synchronous/asynchronous listeners.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, AFTER_COMMIT, and fallback behavior.
- [Spring Boot — AMQP/RabbitMQ](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): AMQP starter, `RabbitTemplate`, `@RabbitListener`, queue declarations, and retries.
- [Spring AMQP — AmqpTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): confirms, mandatory returns, and unroutable message risks.
- [Spring AMQP — @RabbitListener Annotation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): listener containers and `@EnableRabbit`.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): consumer threads, prefetch, and throughput.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): dual-write problem, relays, and duplicate publications.
