# Differences Between Spring Events and Broker Messages in Spring Systems

## 1. Both mechanisms are called “events”, but they do not share the same contract

In a Spring application, we can publish an object:

```java
applicationEventPublisher.publishEvent(
        new OrderCreated("evt-101", "ORD-101"));
```

In a system using RabbitMQ, we can also send a message expressing that exact same occurrence:

```java
rabbitTemplate.convertAndSend(
        "orders.events", "order.created.v1", jsonBody);
```

These two lines of code easily create the impression that they only differ in their API. In reality, a **Spring application event** is primarily a communication mechanism between components within an application; a **broker message** is a message passing through an independent exchange infrastructure with its own protocol, routing, storage, and acknowledgment rules.

A business event such as “an order has been created” can exist in both forms, but **you should not equate the transport mechanism with the business fact**.

- **Domain event**: a fact in the model, for example `OrderCreated`.
- **Spring application event**: a Java object passed by `ApplicationEventPublisher` to listeners in the Spring ApplicationContext (which can propagate across a context hierarchy).
- **Integration event**: a data contract published to other applications/bounded contexts, for example `order.created.v1`.
- **Broker message**: a protocol/transport-level message carrying an integration event and metadata, passing through a RabbitMQ exchange/queue or a Kafka topic/partition.

A domain event can be used to produce an integration event, but it **does not automatically** provide durable data guarantees, retries, or exactly-once delivery.

## 2. Fundamental comparison table

| Criterion | Spring Application Events | Message broker (e.g., RabbitMQ/Kafka) |
| --- | --- | --- |
| Scope | Between beans/listeners in the same application/context; context hierarchy can forward events | Across different processes, services, machines, or languages |
| Transmission unit | Java object; `ApplicationEvent` or POJO/record | Bytes/message/record with headers, payload, routing metadata |
| Network protocol | No network protocol needed just for dispatching | Has client-broker protocol, connections, and a separately operated broker |
| Receiver registration | `ApplicationListener<E>`, `@EventListener` | Queue subscription, `@RabbitListener`, consumer group, `@KafkaListener` |
| Default dispatch | Usually synchronous on the publisher thread | Sending and consumer processing are usually decoupled in time/thread/process |
| Durability | Does not persist events by default | Depends on broker, queue/topic, persistence, replication, and configuration |
| Acknowledgment | Java call returns or throws an exception; no broker ACK | Producer confirm/ack, consumer ACK/offset depending on the broker |
| Retry | Must be designed; `@Async` does not automatically provide durable retries | Has redelivery, retry/DLQ, or application-level retry based on configuration |
| Transaction | Synchronous listeners can share a thread-bound transaction | DB transaction and broker publish are usually **not** atomic |
| Ordering | Synchronous usually follows call order; async may differ | Depends on queue/partition/consumer/concurrency and redelivery policy |
| Contract | Usually an internal Java class | Schema/version, serializer, and compatibility across services |
| Monitoring | Logs/tracing at publisher, listener, and executor | Also includes queue depth, consumer lag, unacked, DLQ, producer confirms |
| Event loss on crash | Unprocessed events can be lost, especially async ones | Can persist/recover if configured properly, **not automatically lossless** |
| Operational cost | Low, uses existing Spring context | Broker, connections, topology, quotas, retention, monitoring, security |

**There is no conclusion that “a broker is always better than Spring events”.** For cache updates or notifying an internal module, `@EventListener` can be simpler, more accurate, and easier to maintain. For information that must reach multiple services even after the producer restarts, a broker paired with a durable way to persist the intent to send is usually more appropriate.

## 3. How do Spring events work?

An example:

```text
HTTP request / scheduled job
          |
          v
OrderService.createOrder()
          |
          v
ApplicationEventPublisher.publishEvent(OrderCreated)
          |
          v
ApplicationEventMulticaster in the Spring context
          |
        +-+-+
        |   |
        v   v
 @EventListener   ApplicationListener<OrderCreatedEvent>
        |                  |
        +-------+----------+
                |
                v
     Returns to publisher (when synchronous callbacks complete)
```

Spring typically uses `SimpleApplicationEventMulticaster`. Under the default configuration, listeners are invoked on the **publishing thread**, with no durable queue sitting in between.

An example method:

```java
@EventListener
public void on(OrderCreated event) {
    projectionService.update(event.orderId());
}
```

This is an **illustrative code snippet**, assuming `OrderCreated` and `projectionService` exist. With a synchronous listener, if this method is slow, `publishEvent(...)` can be blocked. If an unhandled exception is thrown, the exception typically propagates back to the caller; the impact on the transaction depends on where the event is published and the error configuration.

### Spring events do not have to extend ApplicationEvent

An object `record OrderCreated(String orderId)` can be published directly; Spring supports receiving it with `@EventListener`. Internally, Spring can use `PayloadApplicationEvent` for payloads that are not an `ApplicationEvent`.

Meanwhile, if a class implements `ApplicationListener<E>`, the generic `E` must extend `ApplicationEvent`. Therefore, you should not take an example of a POJO record and force `ApplicationListener<OrderCreatedRecord>` if the record does not inherit from `ApplicationEvent`.

### Can run asynchronously while remaining inside the application

```java
@Async("eventTaskExecutor")
@EventListener
public void on(OrderCreated event) {
    emailService.send(event.orderId());
}
```

This is an **illustrative code snippet**, requiring `@EnableAsync`, an executor bean, and a Spring-managed listener bean. When processed asynchronously, the callback typically runs on a different thread. However:

- Errors in an async method do not automatically propagate back to the caller.
- An in-memory task executor does not automatically guarantee events survive a restart.
- Transaction, MDC, security context, and request context do not automatically transfer to the worker.
- The executor queue can fill up, reject tasks, or execute under a different rejection policy.
- A thread pool can hold tasks, but it has no broker message or offset to replay.

**Async Spring events are not equivalent to broker messages.**

## 4. How do broker messages work?

RabbitMQ example:

```text
Producer service
      |
      | Basic.Publish(exchange, routingKey, message)
      v
RabbitMQ broker
      |
      v
Topic exchange: orders.events
      |
      | routing key: order.created.v1
      +---------------------+
      |                     |
      v                     v
billing.order-created   analytics.order-created
      |                     |
      v                     v
Billing consumers       Analytics consumers
      |                     |
      v                     v
ACK/reject              ACK/reject
```

The producer sends to an **exchange**; the exchange uses bindings/routing keys to determine the target queues. Each queue is an independent delivery stream. If two services each need to receive every event, each service typically has **its own queue**. Two instances reading from the same RabbitMQ queue will act as competing consumers, rather than both receiving every message.

With Kafka, the producer sends records to a **topic**, typically by key; consumer groups and partitions determine how work is distributed and re-read by offset. Do not apply RabbitMQ’s queue/ACK model directly to Kafka: Kafka has its own commit offset, retention, and consumer group semantics.

A broker can store messages until consumers are ready (depending on configuration), so producer and consumer do not need to be running at the same time. This is the **benefit of temporal decoupling**. However, the producer must still handle connection errors, the broker must still have sufficient resources, and the consumer must know what to do when a payload is invalid.

## 5. “Sent successfully” can have three different meanings

When diagnosing issues, do not use a single boolean `sent=true` to represent the entire pipeline.

### Level 1 — The producer called the API

```java
publisher.publishEvent(event);
rabbitTemplate.convertAndSend(exchange, routingKey, json);
```

The first line only proves that producer code requested an in-application dispatch. The second line only proves that the send call was invoked and may have returned normally; it is **not enough** to know whether the message was routed, persisted, received by a consumer, or processed by business logic.

### Level 2 — The broker accepted and routed the message

With RabbitMQ, you can configure:

- **Publisher confirms**: the broker sends an ACK/NACK for a publish operation under the confirm mechanism.
- **Publisher returns + mandatory**: messages with no matching queue to route to are returned to the producer.

A publisher ACK **does not mean the consumer has finished processing**. If you only enable publisher confirms and omit returns, a message can be accepted by the broker at the exchange yet reach no queue at all.

Example Spring Boot configuration:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

When certainty is required, the application must **check the result** from `CorrelationData`/confirm callbacks and returned messages; merely enabling properties does not turn every `convertAndSend` call into a blocking wait for confirmation.

### Level 3 — The consumer completed the side effect

A `@RabbitListener` may receive a message, yet updating the DB or calling another API can still fail. In a listener container with `AcknowledgeMode.AUTO`, when the callback completes normally, the container typically ACKs; on error, retry/requeue/reject policies decide what happens next.

You should not ACK/commit offsets too early before starting an important side effect. If the process dies after ACK but before persisting the business state, the broker may not redeliver that message.

## 6. Failure windows: why are Spring events and brokers different?

### 6.1. Failures in a synchronous listener

```text
Service transaction opens
   -> save Order
   -> publishEvent(OrderCreated)
       -> synchronous listener sends email
   -> DB commit / rollback
```

If the listener sends the email successfully and then the DB transaction rolls back, the email has already gone out: **a local transaction does not roll back the email service**. If the listener throws an unchecked exception before commit, the outer transaction may roll back depending on configuration.

A listener that only updates data within the same transaction can make sense; a listener calling a remote API before commit requires careful evaluation.

### 6.2. Failures when sending directly to the broker

```text
DB transaction
  UPDATE orders
  RabbitTemplate.send(order.created)
  COMMIT DB
```

If RabbitMQ has already received the message but the DB rolls back, the consumer observes an “OrderCreated” that is no longer true. If the DB commits and the broker send fails, the business data exists but the event never reaches other systems.

This is the **dual-write problem**: two independent write systems (database and broker) do not automatically form a single atomic transaction just because a Java method is annotated with `@Transactional`.

### 6.3. Sending after commit

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void publishToBroker(OrderCreated event) {
    bridge.send(event);
}
```

This snippet is **illustrative only** and assumes an active Spring transaction, a listener bean, `OrderCreated`, and `bridge`. It helps avoid sending events when the DB transaction rolls back. However, **the process can crash right after commit before the send callback succeeds**. If sending fails, the DB has already committed, so an exception cannot reverse the previous transaction.

By default, `@TransactionalEventListener` only runs when there is an active transaction at publish time; outside a transaction, the callback is skipped if `fallbackExecution=false`. It does not durably store events.

### 6.4. Transactional outbox

When you cannot afford to lose the intent to send, write the business change and the outbox record in the same database transaction:

```text
@Transaction:
  save order
  INSERT outbox(id, type, payload, status=NEW)
  COMMIT
         |
         v
Outbox relay / CDC
   read NEW
   publish to broker
   wait confirm
   mark SENT
         |
         v
Idempotent consumer
```

If the transaction rolls back, both the order and the outbox roll back together. If it commits, the worker can read the outbox again after a process restart. However, the worker may send successfully and crash before marking `SENT`. In that case the message is sent again, so **at-least-once delivery and idempotency** are the standard design.

Outbox solves the problem of **losing the intent to send after commit** better than sending inside `@EventListener`, but it does not mean downstream side effects happen only once without deduplication logic.

## 7. Durability and delivery semantics: do not use absolute labels

Three commonly seen terms:

| Semantics | Idea | Risk |
| --- | --- | --- |
| At-most-once | Does not actively redeliver once considered sent/processed | Messages may be lost |
| At-least-once | When unconfirmed, retries/redelivery may occur | Messages may be duplicated |
| Exactly-once | A guarantee within a **specifically defined scope** | Does not by default span DB, HTTP, and broker together |

Default Spring application events are **not a durable delivery system**, so even labeling them “at-most-once” requires care: a publisher might publish the same event again, or an application might have multiple listeners. It is simply object dispatch within the current code/context.

Brokers do not automatically provide the same guarantee under every configuration. For example, RabbitMQ:

- A durable queue preserves the **queue definition** across broker restarts under the proper configuration.
- Persistent delivery mode helps eligible messages be durably stored in the corresponding queue.
- Publisher confirms tell you the broker accepted the publish, **not** that the business effect occurred.
- Quorum/replication/storage, broker outages, TTL, dead-lettering, and policies also affect whether messages are lost or retained.
- If a Docker container is deleted along with its data volume, declaring a durable queue **will not make the data reappear**.

With Kafka, retention, replication, acks, producer idempotence/transactions, and offset commits affect recoverability. Kafka transactions have guarantees within Kafka’s scope, **not meaning a JDBC transaction and an external API become atomic**.

## 8. Hands-on example: one internal event and one broker message

The example uses **Spring Boot 3.3.13, Java 17+, RabbitMQ, and Maven**. The goal is to observe the differences when an application both publishes a Spring event and sends a broker message. The Boot version is pinned for reproducible lesson execution; for real production systems, choose a currently supported branch and check dependency/security updates.

In the demo:
1. `CommandLineRunner` publishes `LocalOrderCreated` in the context.
2. `@EventListener` handles it immediately, without needing the network.
3. The runner transforms the data into `OrderCreatedWire` and sends JSON to a RabbitMQ exchange.
4. The broker routes the message to a queue.
5. `@RabbitListener` receives the message on a separate listener container.
6. The runner uses a `CountDownLatch` to wait for the broker-side callback, preventing the app from exiting before seeing the output.

**Important:** This is a demo of **two parallel dispatch channels for comparison**, not a transactional outbox or a pattern for publishing twice to serve two production systems.

### 8.1. Project structure

```text
spring-event-vs-broker/
├── pom.xml
├── compose.yaml
└── src/
    ├── main/
    │   ├── java/example/events/EventComparisonDemo.java
    │   └── resources/application.properties
    └── test/java/example/events/EventContractTest.java
```

### 8.2. compose.yaml

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

Run RabbitMQ with Docker Compose:

```bash
docker compose up -d
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

The default account of the demo image is usually `guest/guest` for local access; the management UI is at `http://localhost:15672`. **Only use this configuration on a learning machine**, and do not expose demo ports/credentials to a public network.

### 8.3. pom.xml

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
    <artifactId>spring-event-vs-broker</artifactId>
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

### 8.4. application.properties

```properties
spring.main.web-application-type=none

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=guest
spring.rabbitmq.password=guest

# Demo has no DLQ; do not let poison messages requeue infinitely.
spring.rabbitmq.listener.simple.default-requeue-rejected=false

logging.level.root=WARN
```

The configuration above uses a local RabbitMQ instance; it does not set up publisher confirms, bounded retries, DLX/DLQ, or an outbox. If the consumer fails, the message may be rejected and **discarded** because there is no DLQ, so do not use this policy as-is in production.

### 8.5. EventComparisonDemo.java

```java
package example.events;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;

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
public class EventComparisonDemo {

    private static final String EXCHANGE = "demo.orders.events";
    private static final String ROUTING_KEY = "order.created.v1";
    private static final String QUEUE = "demo.billing.order-created.v1";

    // Internal Spring event: plain Java record.
    public record LocalOrderCreated(
            String eventId,
            String orderId,
            long amountMinorUnits,
            Instant occurredAt) {
    }

    // Message payload used on the wire: has an explicit schema version.
    public record OrderCreatedWire(
            String eventId,
            String eventType,
            int schemaVersion,
            String orderId,
            long amountMinorUnits,
            String occurredAt) {
    }

    // Pure Java mapper: no broker dependency.
    public static OrderCreatedWire toWire(LocalOrderCreated event) {
        return new OrderCreatedWire(
                event.eventId(),
                "order.created",
                1,
                event.orderId(),
                event.amountMinorUnits(),
                event.occurredAt().toString());
    }

    public static final class InternalListener {
        @EventListener
        public void on(LocalOrderCreated event) {
            System.out.println(
                    "LOCAL_LISTENER id=" + event.eventId());
        }
    }

    public static final class BrokerListener {
        private final ObjectMapper mapper;
        private final CountDownLatch observed;

        public BrokerListener(ObjectMapper mapper,
                              CountDownLatch observed) {
            this.mapper = mapper;
            this.observed = observed;
        }

        @RabbitListener(queues = QUEUE)
        public void on(String json) throws Exception {
            OrderCreatedWire message =
                    mapper.readValue(json, OrderCreatedWire.class);

            if (!"order.created".equals(message.eventType())
                    || message.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                        "Unexpected event type or version");
            }

            System.out.printf(
                    "BROKER_LISTENER id=%s order=%s%n",
                    message.eventId(),
                    message.orderId());

            // Only to synchronize stdout in the demo, does not replace broker ACK.
            observed.countDown();
        }
    }

    @Bean
    InternalListener internalListener() {
        return new InternalListener();
    }

    @Bean
    CountDownLatch brokerObserved() {
        return new CountDownLatch(1);
    }

    @Bean
    BrokerListener brokerListener(
            ObjectMapper mapper, CountDownLatch brokerObserved) {
        return new BrokerListener(mapper, brokerObserved);
    }

    @Bean
    TopicExchange orderExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue orderQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding orderBinding(
            Queue orderQueue, TopicExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
                .to(orderExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    CommandLineRunner compare(
            ApplicationEventPublisher publisher,
            RabbitTemplate rabbitTemplate,
            ObjectMapper mapper,
            CountDownLatch brokerObserved) {

        return args -> {
            LocalOrderCreated local = new LocalOrderCreated(
                    "evt-42",
                    "ORD-42",
                    12500L,
                    Instant.parse("2026-11-11T06:00:00Z"));

            System.out.println("LOCAL_PUBLISH id=evt-42");
            publisher.publishEvent(local);
            System.out.println("LOCAL_RETURN id=evt-42");

            OrderCreatedWire wire = toWire(local);
            String json = mapper.writeValueAsString(wire);

            System.out.println("BROKER_SEND_START id=evt-42");
            rabbitTemplate.convertAndSend(
                    EXCHANGE,
                    ROUTING_KEY,
                    json,
                    amqpMessage -> {
                        amqpMessage.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return amqpMessage;
                    });

            System.out.println("BROKER_SEND_RETURN id=evt-42");

            if (!brokerObserved.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Broker consumer did not receive message");
            }

            System.out.println("BROKER_OBSERVED id=evt-42");
        };
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             EventComparisonDemo.class, args)) {
            // Runner runs during startup; context closes when finished.
        }
    }
}
```

**Annotation explanation:**
- `@EventListener` receives the `LocalOrderCreated` record through the Spring context without needing a broker.
- `@RabbitListener` does not receive that Java record; it receives a **JSON String from RabbitMQ** via the listener container and then deserializes it into `OrderCreatedWire`.
- `TopicExchange`, durable `Queue`, and `Binding` are registered as beans; Spring AMQP can declare the topology on the broker when the application connects.
- `MessageDeliveryMode.PERSISTENT` asks the broker to treat the message as persistent, but **it is not an absolute guarantee of durability**.
- `CountDownLatch` only helps the demo wait for the consumer before the application exits.

### 8.6. Running and reading the output

Once the broker is ready:

```bash
mvn -q package
java -jar target/spring-event-vs-broker-1.0.0.jar
```

The **internal Spring event** part produces three lines in exact order:

```text
LOCAL_PUBLISH id=evt-42
LOCAL_LISTENER id=evt-42
LOCAL_RETURN id=evt-42
```

Then the broker path produces additional lines:

```text
BROKER_SEND_START id=evt-42
BROKER_SEND_RETURN id=evt-42
BROKER_LISTENER id=evt-42 order=ORD-42
BROKER_OBSERVED id=evt-42
```

**Note on ordering:** The first three lines of the internal event have a stable order due to the synchronous listener. In the broker part, **`BROKER_LISTENER` may appear before or after `BROKER_SEND_RETURN`**, because the consumer is an independent worker. It is only guaranteed that `BROKER_OBSERVED` appears after the listener calls `countDown()`; `BROKER_SEND_START` occurs before the send call is made.

The `BROKER_SEND_RETURN` line is not a broker confirm and `BROKER_OBSERVED` is not an ACK-reporting API; these are trace lines printed by the application itself. The demo does not open a database transaction and does not automatically provide exactly-once delivery, durable retries, or publisher confirms.

Clean up:

```bash
docker compose down
```

If you want to keep messages after removing the container, add a persistent volume. A durable queue **will not** recover data if the broker’s entire storage is deleted.

## 9. Testing: distinguishing internal logic from broker integration

### 9.1. Simple mapping tests without RabbitMQ

File `src/test/java/example/events/EventContractTest.java`:

```java
package example.events;

import java.time.Instant;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EventContractTest {

    @Test
    void internalEventMapsToVersionedWireContract() {
        var local = new EventComparisonDemo.LocalOrderCreated(
                "evt-test",
                "ORD-TEST",
                2500L,
                Instant.parse("2026-11-11T06:00:00Z"));

        var wire = EventComparisonDemo.toWire(local);

        assertEquals("evt-test", wire.eventId());
        assertEquals("order.created", wire.eventType());
        assertEquals(1, wire.schemaVersion());
        assertEquals("ORD-TEST", wire.orderId());
        assertEquals(2500L, wire.amountMinorUnits());
        assertEquals("2026-11-11T06:00:00Z",
                wire.occurredAt());
    }
}
```

Run:

```bash
mvn -Dtest=EventContractTest test
```

This test verifies mapping from the internal Java record to the wire schema. It **does not start RabbitMQ**, does not prove that the exchange/queue exists, and does not test consumer ACKs. To verify the broker path, run the demo with a real RabbitMQ instance or use Testcontainers + an integration test with timeouts.

### 9.2. Necessary test layers

| Test level | Verifies | Cannot replace |
| --- | --- | --- |
| Spring listener unit test | Callback logic, exceptions, parameters | Spring listener registration/matching |
| Spring context integration | `publishEvent` actually invokes the matching listener | Broker routing and persistence |
| Serialization/contract | JSON/`schemaVersion` and field semantics | Broker ACK and consumer business effect |
| Broker integration | Exchange, queue, routing, consumer receives the message | Dual-write/transaction failures |
| Transaction integration | Rollback/`AFTER_COMMIT` and atomic outbox | Real broker/worker crashes |
| Failure/recovery test | Consumer crash before ACK, producer retry, DLQ, idempotency | Other business logic and permissions |

**Do not use a test checking that “`convertAndSend` does not throw an exception” to conclude that the message reached the consumer.** When delivery guarantees are required, check publisher confirms/returns and downstream processing status.

## 10. Data contracts: internal classes vs. integration schemas

An internal Java class can have its name refactored, package changed, fields added, or representation altered to serve the same module. Those changes may not affect anything else if the code is built and deployed together.

Over a broker, the consumer may be an independently deployed service or even written in a different language. Therefore:

- Use a stable `eventType`, such as `order.created`.
- Have a `schemaVersion` or an appropriate schema registry system.
- Specify required/optional/default fields, monetary units, currency, timezone, and null semantics.
- Include an `eventId`/correlation ID sufficient for tracing/deduplication.
- Do not serialize JPA entities or Spring `ApplicationEvent` directly if consumers do not need Java classes/source.
- Maintain contract tests with real payloads from previous versions, especially when outboxes/brokers retain older messages.
- A change in business meaning may require a **new event type**, not just incrementing the version.

Example of a simple envelope:

```json
{
  "eventId": "evt-42",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T06:00:00Z",
  "orderId": "ORD-42",
  "amountMinorUnits": 12500
}
```

This record is an **illustrative contract**, not a structure mandated by RabbitMQ or Spring Framework. RabbitMQ has its own message properties/headers; Kafka has headers and record keys. Transport metadata and business payload should be clearly separated.

## 11. Retry, redelivery, and idempotency

With synchronous Spring events, when a listener fails, continuing or rolling back depends on the exception, transaction, `ErrorHandler`, and application. Spring does not by default persist failed events for replay after a restart. You can use Spring Retry or a job store, but that is an **additional design**.

With a broker, a consumer can receive the same message multiple times:

```text
Broker delivers evt-42
       |
       v
Consumer updates DB successfully
       |
       v
Consumer crashes before ACK
       |
       v
Broker redelivers evt-42
```

If the redelivery writes to the DB again, it can cause duplicate side effects. A common approach is an **inbox/dedup table**:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

When a consumer only modifies **the same database**, record the processing marker and perform the business update in **one transaction**. The unique constraint protects against two workers processing concurrently. If it is a duplicate, decide to ignore it and ACK according to the contract.

For external side effects such as payments or emails, you need an **idempotency key understood by the downstream service**, or a workflow that can verify the outcome after a timeout. Saving a dedup flag in the DB and then making an HTTP call after commit without a recovery mechanism still leaves a window for lost work.

### Retries are not just enabling a single property

- Transient errors such as connection drops or rate limits can be retried with limits/backoff.
- Schema/validation errors usually do not resolve themselves when retrying the same payload.
- Poison messages should be sent to a dead-letter queue/quarantine for investigation.
- RabbitMQ can requeue based on container policy; without limits, the same failing message can be redelivered repeatedly very quickly.
- Kafka consumers have their own offset/retry-topic/dead-letter models, which are not identical to RabbitMQ’s reject/requeue.

**A reasonable guarantee is typically “at-least-once delivery + idempotent business effects”**, rather than claiming end-to-end exactly-once merely because a broker is present.

## 12. Ordering and processing timing

In synchronous Spring listeners, when the application publishes A and then B from the same thread, the synchronous callbacks for A typically run before the publish call for A returns. However, if there are multiple listeners, async tasks, or multiple threads publishing concurrently, business ordering may no longer be simple.

In a broker:

- A single RabbitMQ queue with one consumer makes ordering easier to control than multiple concurrent consumers; requeues, priorities, and retries can still affect it.
- Kafka provides ordering guarantees per partition under certain configuration conditions; events for the same aggregate can use a partition key to support ordered processing.
- The order in which a consumer receives events does not always equate to DB state order, especially when there are multiple producer/outbox workers.
- If the business logic needs to check ordering, add an `aggregateVersion`/sequence and build logic to reject stale events or detect missing events.

Example:

```text
OrderCreated(orderId=ORD-42, aggregateVersion=1)
OrderPaid(orderId=ORD-42, aggregateVersion=2)
OrderCancelled(orderId=ORD-42, aggregateVersion=3)
```

`aggregateVersion` expresses the order of state changes of an aggregate, whereas `schemaVersion` expresses the payload contract. **Do not use schemaVersion to infer the order of business events.**

## 13. Security, context, and tracing

### In-process Spring events

Synchronous listeners can see `ThreadLocal`, MDC, or the imperative transaction context bound to the publisher’s thread at the time of the call. That does not mean every listener uses the right principal, or that the transaction is guaranteed to commit.

Async listeners typically run on a different worker thread, so context is not propagated automatically. If needed, use a `TaskDecorator`/appropriate context propagation, or put a correlation ID into the event; **do not blindly copy JDBC transaction ThreadLocals** to another thread.

### Broker messages over the network

The consumer resides in another process and does not have the producer’s Java `ThreadLocal` or Spring `SecurityContextHolder`. If correlation is needed, pass IDs through headers/payload according to the contract and start a **consumer trace span** using your tracing system. Do not stuff access tokens or request cookies into messages to “preserve context”.

A basic observability design:

```text
producer log:
  eventId=evt-42 traceId=t-91 stage=publish_started

broker relay log:
  eventId=evt-42 traceId=t-91 stage=broker_confirmed

consumer log:
  eventId=evt-42 traceId=t-91 stage=processed
```

The lines above are a **suggested log format**, not logs generated automatically by Spring. Do not use `eventId`/`orderId` as metric tags because of very high cardinality; keep them in logs/traces subject to access controls.

### Authorization and data

With a broker, each service should have its own credentials and publish/subscribe permissions scoped by vhost/topic/queue. Enable TLS when data traverses untrusted infrastructure, define retention/DLQ policies, and omit sensitive data from payloads when unnecessary. Because a broker carries data further, the security boundary is **wider** than in-JVM callbacks.

## 14. Observability and operations: which metrics should you watch?

| Spring event | Broker message |
| --- | --- |
| Number of events published by type | Producer publish attempts / confirm ACK-NACK |
| Number of callbacks started, finished, failed | Broker queue depth/topic lag |
| Listener latency | Consumer end-to-end processing latency |
| Executor active threads, queue, rejections | Consumer count, unacked, rebalances, offsets |
| Transaction phase/rollbacks | Retries/redeliveries, DLQ/quarantine |
| Exception propagation and ErrorHandler | Publisher returns, unroutable messages |
| MDC/trace propagation | Cross-service tracing/correlation |
| Startup/lifecycle registration | Broker availability, retention, replication, quotas |

Specific metric names depend on Micrometer/Spring Boot/broker exporters; do not assume the system already exposes every metric just because you added a listener annotation.

With a broker, you also have to manage connection pools, channels, topology migrations, schema compatibility, partition/queue scaling, dead-letter replay, and access permissions. This cost can be worthwhile for multiple independent services, but too heavy if you only need two beans exchanging data within a single context.

## 15. Choosing an option for each need

### When to prefer Spring Application Events

- Modules live within the same application and deployment lifecycle.
- Events do not need to survive process termination, or side effects can be recomputed.
- You want to decouple internal notifications, cache/projection updates, or best-effort UI/metrics handling.
- No network connection is needed, and you do not want to operate messaging infrastructure.
- You can take responsibility for controlling exceptions and callback latency.

For example, a monolith application updates an auxiliary in-memory cache when a domain object changes. If the cache misses an event, it can refresh by reading from the durable data source.

### When to prefer a broker

- Other services must receive events independently of the producer’s lifetime.
- There are multiple independently deployed subscribers, each needing its own queue/group and retry pace.
- You need to absorb traffic bursts, apply backpressure, or decouple slow processing from requests.
- You want to retain/replay messages according to broker retention.
- There are cross-service requirements for logging, auditing, and error retry/triage.
- You accept the investment in operations, schema versioning, and idempotency.

For example, Billing, Shipping, and Analytics all need to know that an order was created. Each bounded context has its own responsibilities and may deploy on a different schedule.

### When to combine both

A sensible architecture:

```text
Order aggregate
    |
    v
Domain event OrderCreated
    |
    v
Application service / internal handlers
    |
    +--> internal cache/projection event listener
    |
    +--> same DB transaction:
           UPDATE orders
           INSERT outbox(eventId, payload)
                 |
                 v
           Outbox relay
                 |
                 v
              Broker
                 |
            +----+----+
            |         |
            v         v
          Billing   Shipping
```

**You do not have to publish a Spring event first and then write to the outbox by default.** When invariants require never losing an integration event, the application service can write the outbox directly in the transaction after the aggregate creates the domain event; or the corresponding infrastructure must ensure the outbox is written in the right phase. What needs to be proven is the **atomicity of the business change and the outbox record**, not the number of annotation invocations.

## 16. Common misconceptions

**1. “@Async turns a Spring event into a queue.”** False: an in-RAM executor is not a durable message broker.

**2. “A broker guarantees messages are never lost.”** False: it depends on confirms, persistence, replication, retention, topology, consumer ACKs, and infrastructure failures.

**3. “publishEvent returning means all listeners succeeded.”** Only on a matching synchronous path can you infer that callbacks returned; async/conditions/transaction phases change this.

**4. “convertAndSend returning means the consumer has processed it.”** False: producer send, broker confirm, and consumer side effect are distinct milestones.

**5. “@Transactional makes the DB and RabbitMQ commit together.”** False: a regular JDBC transaction does not automatically fold a broker into an atomic transaction.

**6. “@TransactionalEventListener(AFTER_COMMIT) is an outbox.”** False: AFTER_COMMIT still has a window where the process crashes after DB commit and before sending.

**7. “Just add retry on failure and the system becomes exactly-once.”** Retries aid recovery but easily cause duplicate side effects; idempotency is required.

**8. “One queue for all services, and everyone receives it.”** In RabbitMQ, multiple consumers on the same queue typically split messages among themselves. If each service must receive every event, design separate queues/groups.

**9. “Use the Java ApplicationEvent as the JSON contract for all services.”** This creates class/package coupling and risks lazy-loading/PII leaks. Use integration DTOs and schemas.

**10. “Every event has global system-wide ordering.”** Ordering is affected by concurrency, partitioning, retries, and broker semantics. Use aggregate sequences when needed.

**11. “MDC flows across RabbitMQ like a method call.”** False: thread-bound context does not automatically cross process boundaries; pass correlation/trace metadata explicitly.

**12. “Having a DLQ means error handling is done.”** A DLQ is a holding area for failed messages; it requires alerts, investigation, fixes, and controlled replay.

**13. “Adding more consumers always increases throughput.”** It can create DB contention, exceed downstream quotas, break ordering requirements, or increase retries.

**14. “A broker is needed for every micro-interaction.”** Adding a broker when there is no requirement for cross-service communication or persistence adds unnecessary latency, topology, and complexity.

## 17. Failure matrix and how to verify

| Scenario | Plain Spring event | Broker message |
| --- | --- | --- |
| Temporary listener/consumer error | Exception on sync/async thread; needs application policy | Retry/requeue/replay/DLQ per consumer/broker |
| Publisher process dies right after publish | Unexecuted async tasks may be lost | Message can remain on the broker if properly confirmed and persisted |
| Consumer is not running | No durable default queue waiting | Message can stay in queue/topic until consumer comes back, per retention |
| DB rollback after emitting | Pre-commit callbacks may have already run | Direct broker send before commit can create phantom events |
| Crash after DB commit before send | Events not yet received by broker may be lost | Outbox can preserve send intent if in the same DB transaction |
| Lost broker connection | Irrelevant to pure internal dispatch | Producer send errors/times out; confirm and retry per contract |
| Duplicate message sent | Publisher/listener logic must manage it | Producer retries/redelivery can cause duplicates; needs dedup |
| Payload schema changes | Usually same codebase/Java types, still needs compatibility | Independent consumers need schema versions/contract tests |
| Downstream only partially processes | No automatic system-wide outcome | Needs consumer state, idempotency, saga/additional outbox |
| Sudden traffic spike | Internal thread pool can saturate | Broker buffers/applies backpressure per resources and retention |

### Testing failures at the right scope

1. Spring context test: publish a real event, assert the listener is called the expected number of times/types.
2. Spring async test: tasks complete with a latch/timeout; assert exception handler or error state.
3. Broker integration test: run RabbitMQ/Testcontainers, assert bindings/routing and payload.
4. Confirm/return test: send to a routing key with no queue, distinguish broker ACK from returned message.
5. Transaction integration: DB rollback produces no “committed” integration event; commit has an outbox record.
6. Crash/retry test: relay sends successfully then dies before mark-SENT; consumer ignores duplicate.
7. Consumer test: malformed/wrong-version data is quarantined, not requeued infinitely.
8. Ordering test: multiple workers, messages for the same aggregate, handling stale/missing events.

When testing async/broker paths, use latches or polling with timeouts; do not use `Thread.sleep(100)` and assume the system has definitely finished. Avoid relying on stdout order when two threads/processes run concurrently.

## 18. Design checklist before choosing

1. Is the event only for beans in the same application, or must it reach other services?
2. If the producer restarts, must the message still reach the consumer?
3. Are multiple independent subscribers needed, each retrying at its own pace?
4. Is processing time allowed to block the original request/transaction?
5. Are **business commit**, **broker confirm**, and **consumer success** milestones clearly understood?
6. If both DB and broker are written, has dual-write been solved with an outbox or an equivalent proven mechanism?
7. Are `eventId`, `schemaVersion`, and a payload contract independent of internal Java classes present?
8. Under at-least-once delivery, does the consumer have an appropriate idempotency key and unique constraint?
9. Are retry/backoff, DLQ, monitoring, and a replay procedure in place?
10. To what extent must ordering per aggregate/partition/queue be guaranteed?
11. Are credentials, PII, retention, and broker access permissions protected?
12. Have tests reproduced crashes, rollbacks, connection losses, and duplicates before going to production?

**Conclusion:** Spring Application Events and broker messages are **two mechanisms at different layers**. Spring events suit internal communication within a single process, are synchronous by default, and have no durable event storage. Brokers support connecting independent services across messaging infrastructure, but delivery and business effects are only reliable when properly combined with **publisher confirms, persistence, retries, transactions/outbox, and idempotent consumers**. Choose the mechanism based on system boundaries and tolerable loss/duplication levels, not merely by the name “event”.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): synchronous dispatch, `@EventListener`, `ApplicationEventPublisher`, `@Async`.
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): thread model, executor, and error handler.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): transaction phases and `fallbackExecution`.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `RabbitTemplate`, `@RabbitListener`, retry, and queues.
- [Spring AMQP — RabbitTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): send semantics, confirms/returns.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): two distinct acknowledgment layers.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): delivery scope and producer/consumer settings.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): dual-write, relay, and duplicates.
