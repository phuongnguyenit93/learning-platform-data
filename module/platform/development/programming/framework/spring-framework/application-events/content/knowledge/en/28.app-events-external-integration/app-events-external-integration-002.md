# When to Use Kafka, RabbitMQ, or JMS to Integrate Spring Application Events Outside the Application

## 1. The problem and architectural boundaries

In the **External Integration** group of the **Spring Framework Application Events** topic, the question is not “which annotation replaces `@EventListener`?”, but **when an event must cross the JVM boundary, be durably stored, and be consumed by another system**.

Spring Framework has `ApplicationEventPublisher` and `@EventListener` for communication between beans/modules **within the same `ApplicationContext`**, or propagation from a child context to a parent according to hierarchy rules. For example:

```java
publisher.publishEvent(new OrderPaid("O-42", 125_000));
```

This is illustrative code; `OrderPaid` is defined by the application. The call above does not automatically send a record to a Kafka topic, RabbitMQ exchange, or JMS destination. Nor does it automatically persist the event for replay after a restart.

With two microservices in two different processes:

```text
Spring Application A                              Spring Application B
--------------------                              --------------------
OrderService
    |
    +-- ApplicationEventPublisher
              |
              +-- @EventListener in A
              |
              +-- Bridge / Externalizer
                      |
                      +-- Message broker --------> Broker consumer of B
                          (Kafka/RabbitMQ/JMS)      |
                                                    +-- Business processing in B
```

The bridge layer must perform additional tasks that `ApplicationEventPublisher` does not do on its own: **converting the event to an external contract, serializing, choosing a routing target/key, sending to the broker, observing confirmations, retrying, and handling potential duplicate sends**.

### Initial selection rules

- Only components within the same JVM need short-lived notifications, and losing events when the process dies is acceptable: **Application Events** are usually sufficient.
- Multiple independent services must receive messages, with queues/retries and consumer lifecycle management: consider **RabbitMQ or a JMS provider**, depending on topology and infrastructure.
- Need a log stream, re-reading within retention, multiple consumer groups, and partition-based processing: consider **Kafka**.
- Updating the DB and **must** publish messages without losing them: choose a **durable transactional outbox/event publication registry** or a proven transaction solution; merely switching to a broker does not solve the consistency problem by itself.

## 2. Comparing the three options

| Aspect | Kafka | RabbitMQ | JMS |
| --- | --- | --- | --- |
| Nature | Distributed event log with topics/partitions | Message broker with exchanges, bindings, and queues | Jakarta Messaging specification/API; uses a JMS provider |
| Spring integration | Spring for Apache Kafka | Spring AMQP | Spring JMS |
| Common producer | `KafkaTemplate<K,V>` | `RabbitTemplate` | `JmsTemplate` |
| Common consumer | `@KafkaListener` | `@RabbitListener` | `@JmsListener` |
| Distribution to multiple systems | Consumer groups reading independent streams | Each system has a queue bound to an exchange | Topics/durable subscriptions |
| One worker handles one task | Consumer group/partitions, requires design | Work queues/competing consumers are very natural | Queues/competing consumers |
| Replay | Yes, if the log is still within retention | Queues usually delete/ack messages; need a separate event store for history replay | Determined by the provider and durable subscriptions |
| Ordering | Guarantees log order **within a partition** | Depends on queue, consumer concurrency, prefetch, requeue | Depends on provider, session, destination, concurrency |
| Producer confirmation | Future result/record metadata | Publisher confirm, return, mandatory routing | Provider’s send/session/transaction contract |
| Delivery acknowledgment | Consumer offsets/commit | Consumer ACK/NACK/requeue | Session acknowledgment/transaction |
| Retry, dead letter | Error handlers, retry topics, DLT | Requeue, retry, dead-letter exchange/queue | Provider redelivery and DLQ policy |

**JMS is not a single broker product.** It is an API/specification layer; for example, a system might use ActiveMQ Artemis as the provider and Spring JMS as the integration layer. You cannot assume every provider has identical retention, ack timing, and DLQ behavior.

**Having a broker does not mean exactly-once business processing.** When a crash or timeout occurs, the system must usually tolerate messages **being sent or received multiple times**.

## 3. Kafka: when you need an event stream, consumer groups, and replay

Kafka organizes records by topics and partitions. Producers can set a key so that events for one aggregate (`orderId`) are consistently routed to the same partition, provided the partitioning configuration is stable. A single partition has its own log order; you should not assume global ordering across multiple partitions.

### 3.1. Sending via `KafkaTemplate`

```java
@Component
public class KafkaOrderPublisher {

    private final KafkaTemplate<String, String> kafka;

    public KafkaOrderPublisher(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public void send(ExternalEvent event) {
        String json = serialize(event);

        kafka.send("orders.events.v1",
                   event.aggregateId(), json)
                .whenComplete((result, failure) -> {
                    if (failure != null) {
                        recordFailure(event.eventId(), failure);
                    } else {
                        recordAck(event.eventId(),
                                result.getRecordMetadata().partition(),
                                result.getRecordMetadata().offset());
                    }
                });
    }
}
```

**This is an illustrative snippet**, not a standalone program. `ExternalEvent`, `serialize`, `recordFailure`, `recordAck`, imports, Kafka producer properties, and credentials are provided by the project.

In modern Spring Kafka versions, `KafkaTemplate.send(...)` returns a `CompletableFuture<SendResult<K,V>>`. **The moment `send()` is called is not when the broker confirms the record is stored.** You need to observe the future/callback and asynchronous errors. A producer ACK only proves the outcome of the send step per the Kafka protocol; **it does not prove that the billing service has successfully processed the business logic**.

Choose the key by aggregate when ordering is needed:

```text
topic=orders.events.v1
key=O-42
value={eventId, aggregateId=O-42, sequence=7, ...}
```

However, a key cannot rescue ordering if the producer/relay **sends events for O-42 out of sequence**, or if the consumer dispatches records with the same key to multiple concurrent workers and commits offsets carelessly.

### 3.2. Receiving via `@KafkaListener`

```java
@Component
public class BillingKafkaListener {

    @KafkaListener(
            topics = "orders.events.v1",
            groupId = "billing-service")
    public void handle(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

This is an illustrative snippet; it requires `@EnableKafka`/Spring Boot Kafka configuration, a listener container factory, converters, and a business processor.

- Each consumer group has **its own reading progress/offsets**; an analytics group and a billing group can both read the same topic.
- Instances in the same group split partitions according to assignment.
- `@KafkaListener` is a listener for **messages from Kafka**, not an `@EventListener` from `ApplicationEventPublisher`.
- Error handlers, retry topics/DLT, offset commits, and consumer transactions must be explicitly configured.
- Retention allows replay while records are still stored; do not treat a Kafka topic as infinite storage.

### 3.3. Do Kafka transactions replace the outbox?

Kafka supports idempotent producers and transactions within the scope of supported Kafka records/offsets. However, enabling Kafka transactions **does not automatically create an atomic transaction between Kafka and any business database**, nor does it cover email, HTTP, or payment gateways outside Kafka.

If a `@Transactional` method uses only a JDBC transaction manager while calling `KafkaTemplate.send(...)`, do not infer that both will commit/roll back atomically. There are ways to coordinate transactions, but each approach requires verifying commit order and failure windows; do not equate transaction synchronization with distributed XA.

## 4. RabbitMQ: when you need exchange routing, multiple queues, and work queues

RabbitMQ uses an **exchange** to receive messages from producers and then routes them via **bindings** to one or more queues.

```text
Producer
   |
   +-- exchange: domain.events
          |
          +-- routing key: order.paid
                 |
                 +-- queue: billing.paid
                 |
                 +-- queue: analytics.paid
```

Each queue can have one or more competing consumers. If two services must **both receive their own copy**, normally each service uses its own queue bound to the exchange; do not put both services on a single queue and expect both to receive every message.

### 4.1. Sending via `RabbitTemplate`

```java
@Component
public class RabbitOrderPublisher {
    private final RabbitTemplate rabbit;

    public RabbitOrderPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public void send(ExternalEvent event) {
        rabbit.convertAndSend(
                "domain.events",
                "order.paid",
                serialize(event));
    }
}
```

This is **illustrative code**, requiring exchanges, bindings, message converters, a Rabbit connection, and defined business types.

Do not treat `convertAndSend(...)` returning as proof that the message reached the queue. With RabbitMQ, you must distinguish:

- **Publisher confirm:** the broker confirms the publish according to the publisher confirms configuration.
- **Publisher return:** indicates that a message could not be routed when mandatory/returns are properly enabled.
- **Consumer ACK:** the container/consumer acknowledges that the delivery was processed per policy.
- **Business completion:** for example, the billing DB has been updated; this is a separate milestone from producer confirm and consumer ACK.

Durable queues go together with persistent message policies and appropriate broker durability; declaring a durable queue alone does not automatically guarantee every message survives a broker restart under all configurations.

### 4.2. Receiving via `@RabbitListener`

```java
@Component
public class BillingRabbitListener {

    @RabbitListener(queues = "billing.paid")
    public void handle(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

This is illustrative code; it requires Spring AMQP listener infrastructure, `@EnableRabbit`/Boot auto-configuration, queue declarations, and converters.

Common pitfalls:

- Consumer throws an exception, container immediately `requeue`s repeatedly -> **requeue storm**.
- Multiple consumers and high prefetch -> completion does not follow strict FIFO.
- No dead-letter exchange/queue -> poison messages cause congestion.
- Publisher confirms/returns not configured -> routing failures go unnoticed.

You can use retry/backoff, `AmqpRejectAndDontRequeueException`, DLX, and consumer ACK policies. Check the exact Spring AMQP/container version: default requeue behavior, exception handling, and retries should not be based on generic assumptions.

## 5. JMS: when the system uses a JMS provider and standard destinations

JMS provides concepts of **queue/topic**, connection/session, acknowledgment, and transactions. Spring JMS helps you use the API without manually managing the entire resource lifecycle.

### 5.1. `JmsTemplate` producer

```java
@Component
public class JmsOrderPublisher {
    private final JmsTemplate jms;

    public JmsOrderPublisher(JmsTemplate jms) {
        this.jms = jms;
    }

    public void send(ExternalEvent event) {
        jms.convertAndSend(
                "billing.paid",
                serialize(event));
    }
}
```

This is an illustrative snippet. `JmsTemplate` requires a `jakarta.jms.ConnectionFactory`, provider, converter, and appropriate destination. By default, `pubSubDomain=false` typically targets a **queue**; to use topics/pub-sub, you need to configure the mode and durable subscriptions as required.

### 5.2. `@JmsListener` consumer

```java
@Component
public class BillingJmsListener {

    @JmsListener(destination = "billing.paid")
    public void onMessage(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

Requires `@EnableJms`, `DefaultJmsListenerContainerFactory`, and a provider connection. Example configuration (illustrative snippet, requiring corresponding imports):

```java
@Configuration
@EnableJms
public class JmsListenersConfig {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory factory) {

        DefaultJmsListenerContainerFactory result =
                new DefaultJmsListenerContainerFactory();
        result.setConnectionFactory(factory);
        result.setSessionTransacted(true);
        result.setConcurrency("2-6");
        return result;
    }
}
```

`ConnectionFactory` here is `jakarta.jms.ConnectionFactory`. `sessionTransacted(true)` enables rollback/commit within the JMS session scope; if the listener fails, redelivery is typically controlled by the provider/container.

**Reliability note:** `JmsTransactionManager` only manages a local JMS transaction for a single `ConnectionFactory`. It does not automatically combine a separate JDBC DB transaction into an atomic commit. If you truly need a distributed transaction, you need JTA/XA and provider support; that is more complex than a standard outbox, and you should not assume enabling `@Transactional` is enough.

## 6. Internal events and external messages have different contracts

An internal record:

```java
public record OrderPaid(String orderId, int amountCents) {}
```

is not necessarily a public contract for sending over a broker. An external envelope might look like:

```java
public record ExternalEvent<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateSequence,
        String correlationId,
        Instant occurredAt,
        T payload) {}
```

This is an **illustrative definition**, requiring `java.time.Instant`. Purpose:

| Field | Why it is needed |
| --- | --- |
| `eventId` | Deduplication on retries/redelivery, producer ACK correlation |
| `eventType` | Describes the business fact, e.g., `OrderPaid` |
| `schemaVersion` | Payload/serialization version, not the entity version |
| `aggregateId` | Ordering key/partition key and business identifier |
| `aggregateSequence` | Event order for an aggregate when the contract requires it |
| `correlationId` | Tracking a workflow/request across services |
| `occurredAt` | Timestamp when the producer recorded the event; does not establish cross-machine total ordering |
| `payload` | Immutable snapshot or controlled delta of the data |

An illustrative external JSON event:

```json
{
  "eventId": "evt-42-7",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "aggregateId": "O-42",
  "aggregateSequence": 7,
  "correlationId": "checkout-19",
  "occurredAt": "2026-11-11T00:00:00Z",
  "payload": {
    "orderId": "O-42",
    "amountCents": 125000,
    "currency": "VND"
  }
}
```

Do not pass raw JPA/Hibernate lazy-proxy entities, `HttpServletRequest`, sessions, or mutable objects attached to a transaction/thread as payloads. DTOs should be immutable, defensively copy nested collections, and contain only the data external consumers actually need. Use Jackson/Avro/Protobuf or an appropriate serializer; do not use Java `toString()` as a wire format.

**Distinction to keep in mind:** a message’s `schemaVersion` differs from `aggregateSequence` used for ordering. A JPA entity’s `@Version` is not necessarily a contiguous event sequence.

## 7. Transaction trap: DB commit does not mean broker send succeeded

Contraindicated example if atomic reliability is required:

```java
@Transactional
public void pay(OrderCommand command) {
    repository.markPaid(command.id());
    kafka.send(
            "orders.events.v1",
            command.id(),
            serializePaid(command));
}
```

This is an illustrative snippet with repository, Kafka, and serializer provided by the application.

Possible failures:

1. Broker receives the message, DB later rolls back -> consumer thinks the order is paid.
2. DB commits successfully, broker is unreachable -> event is lost.
3. Producer times out even though the broker actually persisted it -> retries can cause duplicate sends.
4. JVM dies between DB commit and publish -> missing message.
5. `send()` only submits the task, yet the service returns normally -> mistakenly called “sent successfully”.

### 7.1. Is `@TransactionalEventListener(AFTER_COMMIT)` enough?

Simple bridge:

```java
@Component
public class BestEffortBridge {
    private final KafkaTemplate<String, String> kafka;

    public BestEffortBridge(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        kafka.send("orders.events.v1",
                   event.orderId(), serialize(event));
    }
}
```

This is an illustrative snippet. The listener runs after the transaction containing the event commits successfully, provided the event was published **within that transaction**. It avoids sending the event to the broker **before DB commit**, but there is still a window where the process dies right after commit, or the broker send fails.

Furthermore, `KafkaTemplate.send` is asynchronous: `onPaid` may return before the broker acknowledges. An exception in a post-commit callback does not roll back the already-committed transaction. If the application requires zero lost messages, this is **not a sufficient guarantee**.

If the event is published **outside a transaction**, `@TransactionalEventListener` does not run by default (`fallbackExecution=false`). Do not set `fallbackExecution=true` just to “make the listener run” if the business logic genuinely requires a commit to have happened.

### 7.2. Transactional outbox

A more reliable pattern:

```text
BEGIN T1 (database)
  +-- UPDATE business state: OrderPaid
  +-- INSERT outbox(eventId, type, payload, status=NEW)
COMMIT T1
  |
  +-- relay/CDC worker reads committed outbox
        |
        +-- sends message to Kafka/RabbitMQ/JMS
        +-- observes broker confirmation per protocol
        +-- marks SENT or persists retry state
             |
             +-- consumer receives, checks idempotency
```

The outbox row is written **in the same transaction** as the business state; if T1 rolls back, both roll back together. If a crash occurs after commit, the relay can recover from the DB.

Also remember: if the broker has received the message but the relay has not yet marked `SENT`, the relay may send it again. Thus, an outbox supports **at-least-once delivery with possible duplicates**, not automatic exactly-once business effects. Preventing duplicate side effects is handled at the consumer.

## 8. Runnable Java 17+ example: outbox and fake broker before wiring Kafka/RabbitMQ/JMS

To demonstrate transaction semantics without **requiring a real broker installation**, this console example uses Spring Framework **6.2.12**, Spring JDBC, H2, and a `FakeBroker` implementing `BrokerPort`.

It verifies:

1. Creating order A and outbox event A in the **same transaction**, committing successfully.
2. Creating order B then throwing an unchecked exception, causing **both order and outbox** to roll back.
3. The `@TransactionalEventListener(AFTER_COMMIT)` listener runs only for A.
4. Relay sends A when the fake broker fails the first time -> outbox A stays `NEW`.
5. Retry send succeeds -> outbox A becomes `SENT`.
6. Consumer receives the same event twice -> the in-memory side effect is applied only once.

**A fake broker is not real Kafka/RabbitMQ/JMS.** The program demonstrates business transactions, outbox, retries, and deduplication at a simulated level. When wiring a real broker, you must swap in the adapter, add producer confirms, serialization/deserialization, connection settings, and separate broker integration tests.

### 8.1. Structure

```text
external-event-outbox-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ExternalEventsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'external-event-outbox-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ExternalEventsDemo'
}
```

### 8.2. `src/main/java/demo/ExternalEventsDemo.java`

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class ExternalEventsDemo {

    public record OrderPaid(String orderId, int amountCents) {}

    public record ExternalMessage(
            String eventId,
            String aggregateId,
            String eventType,
            int schemaVersion,
            String payloadJson) {}

    public interface BrokerPort {
        void send(ExternalMessage event);
    }

    public static class FakeBroker implements BrokerPort {
        private final AtomicBoolean failNext = new AtomicBoolean();
        private final CopyOnWriteArrayList<ExternalMessage> sent =
                new CopyOnWriteArrayList<>();

        public void failNextSend() {
            failNext.set(true);
        }

        @Override
        public void send(ExternalMessage event) {
            if (failNext.getAndSet(false)) {
                throw new IllegalStateException("broker unavailable");
            }
            sent.add(event);
        }

        public List<ExternalMessage> sentMessages() {
            return List.copyOf(sent);
        }
    }

    public static class AfterCommitProbe {
        private final AtomicInteger callbacks = new AtomicInteger();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onPaid(OrderPaid event) {
            callbacks.incrementAndGet();
        }

        public int count() {
            return callbacks.get();
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void pay(String id, int cents, boolean rollback) {
            jdbc.update(
                    "insert into purchase_orders "
                    + "(order_id, amount_cents) values (?, ?)",
                    id, cents);

            // Demo A/B IDs only; manual JSON is NOT for real input.
            String json = "{\"orderId\":\"" + id
                    + "\",\"amountCents\":" + cents + "}";

            jdbc.update(
                    "insert into outbox_events "
                    + "(event_id, aggregate_id, event_type, "
                    + "schema_version, payload_json, status) "
                    + "values (?, ?, ?, ?, ?, ?)",
                    "evt-" + id, id, "OrderPaid", 1, json, "NEW");

            events.publishEvent(new OrderPaid(id, cents));

            if (rollback) {
                throw new IllegalStateException("rollback requested");
            }
        }
    }

    public static class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final BrokerPort broker;

        public OutboxRelay(JdbcTemplate jdbc, BrokerPort broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        @Transactional
        public void deliverPending() {
            List<ExternalMessage> pending = jdbc.query(
                    "select event_id, aggregate_id, event_type, "
                    + "schema_version, payload_json "
                    + "from outbox_events where status = 'NEW' "
                    + "order by event_id",
                    (rs, rowNum) -> new ExternalMessage(
                            rs.getString("event_id"),
                            rs.getString("aggregate_id"),
                            rs.getString("event_type"),
                            rs.getInt("schema_version"),
                            rs.getString("payload_json")));

            for (ExternalMessage event : pending) {
                // Fake broker confirms synchronously; real brokers differ.
                broker.send(event);
                jdbc.update(
                        "update outbox_events set status = 'SENT' "
                        + "where event_id = ?",
                        event.eventId());
            }
        }
    }

    public static class DeduplicatingConsumer {
        // RAM-only demo. Production: unique key in a persistent DB.
        private final Set<String> handled =
                ConcurrentHashMap.newKeySet();
        private final AtomicInteger effects = new AtomicInteger();

        public void consume(ExternalMessage event) {
            if (handled.add(event.eventId())) {
                effects.incrementAndGet();
            }
        }

        public int effects() {
            return effects.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:external_events;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        FakeBroker fakeBroker() {
            return new FakeBroker();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OutboxRelay outboxRelay(
                JdbcTemplate jdbc, BrokerPort broker) {
            return new OutboxRelay(jdbc, broker);
        }

        @Bean
        AfterCommitProbe afterCommitProbe() {
            return new AfterCommitProbe();
        }
    }

    private static int count(JdbcTemplate jdbc, String sql) {
        return jdbc.queryForObject(sql, Integer.class);
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            OutboxRelay relay = context.getBean(OutboxRelay.class);
            FakeBroker broker = context.getBean(FakeBroker.class);
            AfterCommitProbe afterCommit =
                    context.getBean(AfterCommitProbe.class);

            jdbc.execute(
                    "create table purchase_orders ("
                    + "order_id varchar(40) primary key, "
                    + "amount_cents int not null)");
            jdbc.execute(
                    "create table outbox_events ("
                    + "event_id varchar(80) primary key, "
                    + "aggregate_id varchar(40) not null, "
                    + "event_type varchar(80) not null, "
                    + "schema_version int not null, "
                    + "payload_json varchar(1000) not null, "
                    + "status varchar(20) not null)");

            String orderSql =
                    "select count(*) from purchase_orders";
            String pendingSql =
                    "select count(*) from outbox_events "
                    + "where status = 'NEW'";

            orders.pay("A", 1200, false);
            System.out.println("after commit: orders="
                    + count(jdbc, orderSql)
                    + ", pending=" + count(jdbc, pendingSql)
                    + ", callbacks=" + afterCommit.count());

            boolean rolledBack = false;
            try {
                orders.pay("B", 2500, true);
            } catch (IllegalStateException ex) {
                rolledBack = true;
            }
            System.out.println(
                    "transaction B rolled back=" + rolledBack);
            System.out.println("after rollback: orders="
                    + count(jdbc, orderSql)
                    + ", pending=" + count(jdbc, pendingSql)
                    + ", callbacks=" + afterCommit.count());

            broker.failNextSend();
            boolean sendFailed = false;
            try {
                relay.deliverPending();
            } catch (IllegalStateException ex) {
                sendFailed = true;
            }
            System.out.println("first send failed=" + sendFailed
                    + ", pending=" + count(jdbc, pendingSql));

            relay.deliverPending();
            System.out.println("after retry: sent="
                    + broker.sentMessages().size()
                    + ", pending=" + count(jdbc, pendingSql));

            DeduplicatingConsumer consumer =
                    new DeduplicatingConsumer();
            ExternalMessage message =
                    broker.sentMessages().get(0);
            consumer.consume(message);
            consumer.consume(message);

            System.out.println(
                    "consumer side effects after duplicate="
                    + consumer.effects());
        }
    }
}
```

### 8.3. Running and observing

With JDK 17+ and Gradle installed:

```bash
gradle -q run
```

The lines explicitly printed by the program:

```text
after commit: orders=1, pending=1, callbacks=1
transaction B rolled back=true
after rollback: orders=1, pending=1, callbacks=1
first send failed=true, pending=1
after retry: sent=1, pending=0
consumer side effects after duplicate=1
```

**Explanation by transaction:**

- `OrderService.pay` is invoked through a Spring transaction proxy. For A, `purchase_orders` and `outbox_events` are INSERTed in T1; the commit succeeds, so `AfterCommitProbe` receives the callback.
- For B, the unchecked exception causes T2 to roll back; there is no order/outbox B and no post-commit callback for B.
- `OutboxRelay` is also invoked through a proxy, using a separate transaction. On the first call, `FakeBroker` throws an exception, so the relay transaction rolls back and row A remains `NEW`.
- On the second call, the simulated broker accepts the event and the relay updates it to `SENT`; the simulated consumer receives the same `eventId` twice and increments the effect only once.

**This is not proof of a successful connection to a real broker**: the Java console app has no Kafka, RabbitMQ, or JMS provider. The adapters illustrated in the next section need integration tests with a real broker. `FakeBroker` sends synchronously, whereas real producer APIs have different ACK/future/confirm semantics.

## 9. Why is the demo relay not enough for production?

### 9.1. DB transaction stays open while calling the broker

`OutboxRelay.deliverPending()` in the demo uses one transaction spanning read/send/update. If the network is slow, DB connections or locks can be held for a long time. Production usually requires **claim/lease/batch + timeout**, short transactions, and a recovery mechanism.

### 9.2. Send succeeds then crash before `SENT`

If the broker has already received the message, but the DB update to `SENT` has not committed yet, the next relay run sees `NEW` and sends it again. This is why **consumer idempotency is mandatory** with an at-least-once outbox.

### 9.3. `sent` is different from `processed`

Outbox `SENT` should only mean **the broker confirmed message handoff per the adapter’s contract**, not that the consumer completed its side effects. To know whether an invoice was issued, you need a consumer status/reply event.

### 9.4. Fake dedupe does not survive restarts

`DeduplicatingConsumer` uses a `Set` in RAM. Production should store `processed_events(consumer_name,event_id)` with a unique constraint in the same transaction as the business DB update, or apply an idempotency key on the external system.

### 9.5. Ordering and concurrency

The demo’s `ORDER BY event_id` is only enough for a small example; **it does not establish business ordering**. If multiple events of the same aggregate must be applied sequentially, assign an `aggregateSequence` within the transaction and process relay/consumer by key; do not rely on timestamps or random ID ordering as a guarantee.

## 10. Adapting `BrokerPort` to each technology

In the demo project:

```java
public interface BrokerPort {
    void send(ExternalMessage message);
}
```

can be replaced with one of the following adapters. **The snippets below only illustrate the API**, and are not part of the runnable project shown earlier.

### 10.1. Kafka adapter awaiting send result

```java
@Component
public class KafkaBrokerPort implements BrokerPort {
    private final KafkaTemplate<String, String> kafka;

    public KafkaBrokerPort(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    @Override
    public void send(ExternalMessage event) {
        try {
            kafka.send("orders.events.v1",
                    event.aggregateId(),
                    event.payloadJson())
                    .get(10, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Kafka send interrupted", ex);
        } catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException("Kafka send failed", ex);
        }
    }
}
```

Requires imports for `KafkaTemplate`, `TimeUnit`, `ExecutionException`, `TimeoutException`, producer configuration, and serializers. Waiting on the future with a timeout tells you the send result per the producer API, **but does not handle every ambiguous timeout case**: the broker may have persisted it while the client did not receive the ACK in time. In practice, the relay can use async callbacks and a state machine instead of blocking threads; recovery semantics must be preserved.

### 10.2. RabbitMQ adapter

```java
@Component
public class RabbitBrokerPort implements BrokerPort {
    private final RabbitTemplate rabbit;

    public RabbitBrokerPort(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    @Override
    public void send(ExternalMessage event) {
        rabbit.convertAndSend(
                "domain.events",
                "order.paid",
                event.payloadJson());
    }
}
```

This snippet is **not enough to reliably mark `SENT`**. Production needs to observe publisher confirms and returned/unroutable messages according to topology and settings; you can attach `CorrelationData` with `eventId`.

### 10.3. JMS adapter

```java
@Component
public class JmsBrokerPort implements BrokerPort {
    private final JmsTemplate jms;

    public JmsBrokerPort(JmsTemplate jms) {
        this.jms = jms;
    }

    @Override
    public void send(ExternalMessage event) {
        jms.convertAndSend(
                "billing.paid",
                event.payloadJson());
    }
}
```

JMS `ConnectionFactory`, destination, QoS, and transaction policies must be explicitly configured. Do not equate a `void` send with confirmation that the consumer has completed.

**Register only a single `BrokerPort`** or use `@Qualifier` when multiple adapter beans coexist. If you create Fake, Kafka, Rabbit, and JMS beans simultaneously without qualifiers/conditional config, dependency injection will be ambiguous.

## 11. Ordering by `aggregateId`, not timestamp

Example event stream:

```text
Order O-42
  seq=1 OrderCreated
  seq=2 OrderPaid
  seq=3 OrderShipped
```

- Kafka: set `aggregateId` as the key; all records with the same key should go to the same partition and be sent by the producer in sequence. The consumer must not blindly apply seq=3 before seq=2.
- RabbitMQ: a queue can have multiple consumers, prefetch, and requeues; per-key serialization/version checks are needed if strict ordering is required.
- JMS: check session/provider semantics, consumer concurrency, and redelivery; do not assume total order across all consumers by default.
- Outbox relay: two parallel workers reading the outbox can send E2 before E1 if using `SKIP LOCKED` without constraining per-key ordering.

A consumer requiring contiguous ordering can store `lastAppliedSequence` in the DB:

```text
If incoming == last + 1: apply and update progress atomically
If incoming <= last: duplicate/stale, handle per idempotency contract
If incoming > last + 1: gap; defer/retry/alert
```

This is pseudocode, **and only valid if the sequence contract is contiguous**. If entity versions have gaps due to changes that do not emit events, you need a dedicated event sequence or a gap-tolerant policy.

## 12. Retries, ACK, and dead-letter handling per broker

### Kafka

Has producer futures/record metadata, consumer offsets, error handlers, backoff, and DLT/retry topics. **Offset commit** does not prove all external side effects succeeded without corresponding transaction/idempotency rules. Retries can alter completion order; test per-partition/per-key.

### RabbitMQ

Has publisher confirms/returns, consumer ACK/NACK, requeue, and DLX/DLQ. Avoid infinite retries creating a requeue storm. An empty queue after ACK does not prove another system processed it if the consumer itself ACKed too early.

### JMS

Has session acknowledgment modes and transacted sessions; `DefaultMessageListenerContainer` along with the provider manages delivery/redelivery. Auto-ack may be insufficient for critical workloads. DLQ, redelivery delay, and max attempts depend on the provider, so test against real infrastructure.

**Separate the three success layers:**

```text
Message submitted by producer
    -> Broker confirmed storage/routing per contract
        -> Consumer applied side effects and ACKed/committed
```

These three milestones are not equivalent. Add a `COMPLETED` status or result event if the business logic requires confirmation from the consumer.

## 13. Durable idempotent consumer pattern

A commonly used mechanism:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Within a consumer DB transaction:

```text
BEGIN
  +-- INSERT (consumer_name, event_id) with unique constraint
  +-- If already exists: identify as duplicate, avoid duplicate side effects
  +-- If new: update business state
COMMIT
  +-- ACK/commit offset per consumer protocol
```

**Do not** do a non-atomic check-then-act:

```java
if (!alreadyProcessed(eventId)) {
    chargeCustomer();
    markProcessed(eventId);
}
```

This is an **anti-pattern**. Two workers can both read `false`, or the process can die after `chargeCustomer()` before `markProcessed()`. For HTTP side effects, an internal DB unique key cannot by itself prevent a second charge if the remote service lacks an idempotency key. Use a stable operation ID and remote API idempotency when available.

## 14. Security and schema evolution

A message broker expands the blast radius of data propagation. A DTO sent through Kafka/RabbitMQ/JMS may be retained for days or reach multiple teams/systems.

- Publish only necessary fields; do not include passwords, bearer tokens, cookies, sessions, or full request objects.
- Use validated `eventId`, correlation ID, and aggregate ID; tenant/user IDs must be authenticated/authorized at ingress.
- Use TLS, credential rotation, topic/queue ACLs, and a secrets manager appropriate for the broker.
- Establish retention and appropriate personal data deletion/redaction rights.
- Schema versions, backward compatibility, and staged rollouts must be tested; changing an `amount` field from cents to decimal while keeping the same name/schema is a severe risk.
- Do not serialize Hibernate entities with lazy associations; map to immutable external DTOs.
- For large data (images/files), consider object storage + object key/checksum instead of putting the entire blob into the message.

## 15. When to use Spring Modulith event externalization?

If your architecture is a modular monolith running with Spring Boot, **Spring Modulith** has an Event Publication Registry and event externalization to forward selected application events to Kafka/AMQP/JMS, depending on modules, dependencies, and configuration.

However, Spring Modulith is **not a built-in feature of Spring Framework**. The registry and externalization require appropriate storage/configuration; retry/republish policies and ordering may vary by version. Some externalization modes based on async transactional listeners do not provide all the guarantees of an outbox, so read the documentation for your specific version and test crash windows.

What to verify when using it:

- Which events are selected for externalization, and what routing target/key is used?
- Is the publication registry persisted within the original transaction?
- What do restarts and republishing of outstanding events do?
- If the broker ACKs but the registry has not marked complete yet, how does the consumer prevent duplicates?
- Is per-aggregate ordering guaranteed, especially when replaying multiple rows?

You can choose Spring Modulith to reduce boilerplate, but event contract design and idempotency remain the application’s responsibility.

## 16. Testing with real Kafka, RabbitMQ, or JMS

**Unit tests** mocking `KafkaTemplate`, `RabbitTemplate`, or `JmsTemplate` only prove a method was called. **Integration tests** with `@RecordApplicationEvents` prove an event was published inside the Spring context, not broker delivery.

For reliability requirements, test across these boundaries:

| Scenario | What to verify |
| --- | --- |
| Business transaction rollback | No committed outbox row exists |
| Commit, broker unavailable | Pending outbox row remains for retry |
| Broker recovers | Relay sends the message and marks per ACK contract |
| Broker receives but relay dies before marking SENT | Duplicate occurs safely; consumer is idempotent |
| Consumer processes then dies before ACK/offset commit | Redelivery causes no duplicate side effects |
| Wrong routing key/queue | Rabbit publisher return/monitoring reports unroutable |
| Bad schema/poison message | Bounded retries, DLQ/quarantine/alert |
| Kafka multiple consumer groups | Each group consumes per its own offset policy |
| Rabbit multiple queues bound to one exchange | Each queue receives a copy; consumers on the same queue share work |
| JMS transaction rollback | Redelivery behaves per provider/container configuration |
| Two events for the same aggregate across workers | Sequence/gap checking and per-key ordering |
| Restart while outbox still has NEW | Work is recovered from DB instead of lost in RAM |

You can use Testcontainers to run Kafka, RabbitMQ, or ActiveMQ Artemis in integration tests, along with a persistent test database and network failure injection. Avoid measuring only that `publishEvent` returned; observe producer confirmations, broker storage/delivery, and consumer side effects.

## 17. Quick troubleshooting table

| Symptom | Cause worth checking | Solution |
| --- | --- | --- |
| `@EventListener` in B does not receive A’s event in another JVM | `ApplicationEventPublisher` is not a remote bus | Bridge to a broker |
| Kafka `send()` called but consumer does not receive | Future failed, topic/ACL/serializer/group offset | Observe the send future and consumer configuration |
| Rabbit sent but nothing in queue | Wrong routing/binding, missing mandatory returns | Publisher confirms/returns + topology checks |
| JMS listener does not run | Missing `@EnableJms`, container factory, destination/provider | Check provider connection and listener |
| DB committed yet broker has no message | In-memory after-commit bridge lost task | Durable transactional outbox/publication registry |
| Duplicate messages sent | Timeout, crash after broker ACK, or redelivery | `eventId` and consumer idempotency |
| Kafka has EOS yet emails still send twice | Kafka transactions do not cover external HTTP side effects | External idempotency key |
| Messages for the same order arrive out of order | Parallel relay/consumer, retries, wrong partition | Per-key ordering, sequence checking |
| Rabbit requeue storm | Poison message with unlimited retries | Backoff, max attempts, DLQ |
| JMS rollback does not roll back JDBC DB | JMS session transaction is separate from DB | Outbox or properly configured JTA/XA |
| Outbox status SENT yet downstream not finished | `SENT` only reflects producer/broker milestone | Separate consumer result/status |
| Service crash loses internal events | Spring Application Events do not auto-persist | Outbox or durable queue |
| Schema change causes deserialization failure | Lack of backward compatibility | Schema versioning and compatibility tests |

## 18. Production checklist

**Boundaries**

- [ ] Have internal events and external messages been clearly separated?
- [ ] Were Kafka for streams/replay, RabbitMQ for routing/work queues, or JMS for provider/enterprise needs chosen with concrete reasons?
- [ ] No expectation that an `@EventListener` in another process automatically receives an Application Event?

**Reliability**

- [ ] Business DB + outbox written in the same transaction when messages cannot be lost?
- [ ] Relay waits for proper broker confirmation before marking `SENT`?
- [ ] Duplicates from crashes/timeouts handled idempotently by the consumer?
- [ ] Replay/recovery, backoff, DLQ, and poison-message policies in place?
- [ ] Producer ACK, consumer ACK, and business completion distinguished?

**Contract & operations**

- [ ] Are event ID, aggregate ID, sequence, schema version, and correlation ID clearly defined?
- [ ] Have ordering, keys/partitions, consumer concurrency, and gaps been verified?
- [ ] Does payload contain only necessary data, without leaking secrets/PII?
- [ ] Are metrics for outbox backlog/age, broker lag, queue depth, failures/retries, and oldest event present?
- [ ] Are there integration tests with a real broker, commit/rollback, crashes, and duplicates?

**Summary:** `ApplicationEventPublisher` is an **in-application** event publishing mechanism. **Kafka, RabbitMQ, and JMS** are messaging options when data must leave the JVM with dedicated retention/routing/ack/retry semantics. Choose the technology based on required system behavior, map domain events to stable external contracts, and use **outbox + idempotent consumers** when reliability across transactions, networks, and crashes is needed. Do not treat `publishEvent`, `send`, broker confirmation, and consumer completion as a single milestone.

## References

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Kafka — Sending Messages with `KafkaTemplate`](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka — `@KafkaListener`](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring AMQP — Sending, Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages.html)
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — `@JmsListener` endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Modulith — Event Publication Registry and Externalization](https://docs.spring.io/spring-modulith/reference/events.html)
