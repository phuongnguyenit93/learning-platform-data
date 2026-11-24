# Distinguishing JMS from Kafka, AMQP, and Spring Messaging

## Learning Objectives

After this lesson, you can: (1) identify which architectural layer JMS, Kafka, AMQP, and Spring Messaging belong to; (2) explain the differences among a work queue, event broadcasting, and a replayable event log; (3) choose the right technology for distribution, retention, replay, and Spring integration requirements; and (4) avoid confusing JMS Topic, Kafka Topic, the AMQP protocol, and Spring APIs.

**Key takeaway:** these four names are not four equivalent brokers. JMS/Jakarta Messaging is a **Java API standard**; Kafka is an **event streaming storage and processing platform**; AMQP is a **network message-exchange protocol**; Spring Messaging is a **programming abstraction set** in the Spring ecosystem.

## 1. Placing Each at the Right Architectural Layer

| Component | What It Actually Is | What It Defines/Provides | Related Examples |
|---|---|---|---|
| **JMS (Jakarta Messaging)** | Message send/receive API standard for Java applications | `ConnectionFactory`, `Session`/`JMSContext`, `Message`, `Queue`, `Topic`, acknowledgment mechanism, selectors, transactions | Jakarta Messaging API with providers like ActiveMQ Artemis, IBM MQ; Spring JMS calls this API |
| **Apache Kafka** | Event streaming platform with brokers, partitioned logs, and its own protocol/clients | `topic`, `partition`, `offset`, retention, consumer groups, ability to re-read still-retained data | Kafka brokers, Kafka clients, Spring for Apache Kafka |
| **AMQP** | Protocol family standardizing message transmission between client and broker | Frame format, wire interactions; routing model depends on protocol version | AMQP 0-9-1 commonly used with RabbitMQ; AMQP 1.0 used by various clients/brokers |
| **Spring Messaging** | Spring Framework abstraction inside application code | `org.springframework.messaging.Message<T>`, headers, `MessageChannel`, `MessageHandler`, payload conversion | Spring Integration, STOMP/WebSocket, transport integration adapters |

The difference lies in **the question each technology answers**:

- JMS: "Which API contract does Java code use to talk to a messaging provider?"
- Kafka: "Which log is an event written to, how is it partitioned, what offset has each consumer group reached, and can it be re-read?"
- AMQP: "Which network standard do client and broker use to transmit frames/messages?"
- Spring Messaging: "Inside a Spring application, which interfaces represent payloads, headers, and message-processing flows?"

**Do not equate API, protocol, broker, and framework.** A Spring application can use Spring JMS to call the JMS API; a JMS provider can communicate over AMQP 1.0. Meanwhile, `@KafkaListener` and `@RabbitListener` integrate different models and clients.

~~~text
Java + Spring Application
  ├─ Spring JMS    → Jakarta Messaging API → JMS provider/broker
  ├─ Spring Kafka  → Kafka client          → Kafka cluster
  ├─ Spring AMQP   → AMQP/RabbitMQ client  → Compatible RabbitMQ/broker
  └─ Spring Messaging: Message, headers, channel, handler
       (internal abstraction or connected to transports via adapters)
~~~

The diagram only shows conceptual relationships. A broker may support multiple protocols, and a transport may integrate with multiple Spring modules.

## 2. JMS: API for Message Queues and Publish/Subscribe in Java

### 2.1. Basic Mechanism

JMS is the familiar name for **Java Message Service**. With modern Jakarta Messaging versions, the API package is `jakarta.jms`; older documentation and libraries commonly use `javax.jms`. When learning Spring Framework 6/7 or Spring Boot 3/4, check compatibility between these two namespaces.

A typical flow:

1. The application obtains a `ConnectionFactory` supplied by the JMS provider.
2. The producer creates or converts a `Message` and sends it to a `Destination`.
3. The broker/provider distributes the message according to destination semantics, persistence settings, TTL, selectors, and specific policies.
4. The consumer receives the message, processes it, and then acknowledges or commits the transaction. On failure, redelivery may occur depending on configuration.

JMS defines the Java contract and core semantics; it **does not mandate a single universal wire protocol** that every provider must use. Nor does the JMS API start a broker itself or ensure all providers share the same operational policies.

### 2.2. Queue and Topic Are Not the Same

**Queue — point-to-point/competing consumers:**

~~~text
Producer ──► [Queue: payment.requests]
                  ├─► Worker A
                  ├─► Worker B
                  └─► Worker C
Each message is delivered to one eligible consumer on the queue.
~~~

If three workers listen on the same queue, the message is not automatically multiplied into three copies for all three. Queues fit "one job needing one worker to process it", such as generating an invoice or sending an email.

**Topic — publish/subscribe:**

~~~text
Producer ──► [Topic: order.events]
                  ├─► Subscription A → Billing
                  └─► Subscription B → Analytics
Each eligible subscription receives its own message copy.
~~~

Topics broadcast to different **subscriptions**. With a **non-durable subscription**, messages published when no active subscriber is present are typically not retained for that subscriber to read later. With a **durable subscription**, the provider maintains the subscription and accumulates eligible messages while the consumer is disconnected, until received/acknowledged or expired per policy. A shared subscription can distribute work across multiple consumers; do not assume every instance receives every message.

### 2.3. Reliability and Limitations

- **Acknowledgment/transaction:** a message not yet recorded as complete may be redelivered. Do not assume the handler executes strictly once.
- **Persistence:** `PERSISTENT` mode increases durability guarantees on broker failure; it does not bypass resource limits, retention config, or failures outside the broker.
- **Selector:** consumers can filter based on message properties (e.g., `region = 'VN'`); this is not an arbitrary content query over an event log.
- **TTL, priority, redelivery, dead-letter queue (DLQ):** partly standard concepts/APIs, while redelivery schedules and DLQ setup typically depend on the broker.
- **Ordering:** JMS specifies delivery ordering under certain conditions, yet competition among multiple consumers, selectors, retries, and parallel processing can make **business completion** order differ from send order.
- **Replay:** JMS does not define resetting an offset to replay the entire consumed history like Kafka. Browsing, DLQ, archiving, or redrive—if available—are provider-specific features/policies.

**Choose JMS when** a Java system already uses a JMS provider, needs enterprise messaging queues or topics, transactions/acknowledgments, and Spring integration; especially when there is no need to treat the message stream as an independent historical log for multiple groups to replay.

## 3. Kafka: Retained, Partitioned Event Log with Offsets

Kafka uses a `topic` to hold records appended to a **log**. Each topic is split into one or more `partitions`; records have an offset within **that specific partition**, with no "global offset" across the entire topic. Producers can choose a key so records with the same key are typically routed consistently to the same partition within a given configuration era.

~~~text
Topic: orders.events
  partition 0: [offset 0][offset 1][offset 2]...
  partition 1: [offset 0][offset 1][offset 2]...
  partition 2: [offset 0][offset 1][offset 2]...

Consumer group "billing":   stores its own read position
Consumer group "analytics": stores its own read position
~~~

Key differences:

1. **Reading does not mean deleting records.** Records typically remain in the log after a consumer reads and commits offsets, until removed by time/size retention, compaction policy, or other configuration.
2. **Multiple consumer groups read independently.** Billing and Analytics can track different offsets without competing for the same "message instance" like a queue.
3. **Conditional replay.** Consumers can seek/reset offsets to re-read data **that still exists**; Kafka does not inherently retain history forever.
4. **Scoped ordering.** Kafka preserves ordering per partition. If a business rule requires ordering by `orderId`, design keys/partitions accordingly; do not claim strict ordering across an entire topic.
5. **Parallelism depends on partitions.** In the standard consumer group model, a partition is assigned to at most one active consumer in the group at a time. Scaling instances beyond the partition count does not add useful parallelism for that topic.
6. **Delivery and business processing are two separate layers.** Kafka has transactional/exactly-once mechanisms for certain processing flows and Kafka writes, but that **does not automatically make** emails, payment APIs, or external database updates outside Kafka exactly-once.

Kafka typically fits when you need event history with explicit retention, multiple independent consumer groups, replay to fix logic or rebuild materialized views, high-volume ingestion, and stream processing. Do not pick Kafka merely because it is "faster than a queue": evaluate throughput, latency, ordering, operational complexity, and retained data in real context.

### 3.1. How Is a "JMS Topic" Different from a "Kafka Topic"?

Both share the word *topic*, yet their models differ:

- A JMS Topic distributes messages to subscriptions; a durable subscription can hold backlog for a subscriber, but the JMS API does not expose a log offset for any consumer to actively rewind acknowledged history.
- A Kafka Topic is a partitioned log with retention; consumer groups manage read positions and can re-read still-retained records.
- Both support fan-out to multiple parties in different ways. Clarify whether "each party" means a **subscription**, a **consumer instance**, or a **consumer group**.

Example: a system starts with an `OrderCreated` event; a month later the analytics team needs to rebuild a report for the past 14 days of data. Kafka handles this smoothly if topic retention still holds enough data and read permissions are granted. A JMS Topic does not by default provide rewinding all previously processed messages.

## 4. AMQP: A Messaging Protocol, Not the Name of a Broker

AMQP stands for **Advanced Message Queuing Protocol**. Always specify the version:

- **AMQP 0-9-1:** the model widely known through RabbitMQ. Producers publish to an **exchange**, and the exchange routes to **queues** via **bindings** (e.g., direct, topic, fanout, headers exchanges), then consumers receive from queues.
- **AMQP 1.0:** a substantially different wire standard using connections, sessions, links, and transfers. Do not infer that all exchange/binding operations from 0-9-1 exist identically in 1.0. Specific features must be checked against the broker/client.

~~~text
AMQP 0-9-1 (e.g., RabbitMQ):
Publisher ─► Exchange("orders") ──binding/routing key──► Queue("billing")
                                              └────────► Queue("analytics")
                                                           │
                                                        Consumer
~~~

A RabbitMQ broker can provide AMQP 0-9-1, AMQP 1.0, and other protocols; **RabbitMQ is the broker product**, whereas **AMQP is the protocol**. Names like Kafka, RabbitMQ, and ActiveMQ Artemis sit closer to the deployment platform layer, even though their architectures still differ.

### 4.1. Can JMS and AMQP Be Used Together?

**Yes, with an appropriate provider/client.** For example, **Apache Qpid JMS** implements the Jakarta Messaging API for Java applications while transmitting data over **AMQP 1.0**. Hence "using JMS" and "using AMQP 1.0" are not mutually exclusive: one describes the API source code calls, while the other describes the protocol on the wire.

Conversely, using Spring AMQP's `RabbitTemplate` to talk to RabbitMQ over AMQP 0-9-1 **does not mean** you are using the JMS API. Do not treat `JmsTemplate` and `RabbitTemplate` as two names for the same API.

### 4.2. Semantics Must Be Verified with the Broker

Delivery confirmation, consumer acknowledgment, persistent messages, DLQ, retries, routing, queue types, ordering, and transactions vary in support by **AMQP version + broker + client + configuration**. The word "AMQP" alone does not guarantee identical features to JMS or Kafka.

## 5. Where Does Spring Messaging Fit in the Ecosystem?

`spring-messaging` provides universal programming contracts, for example:

- `org.springframework.messaging.Message<T>`: a payload accompanied by headers.
- `MessageChannel`: contract for sending messages to a channel.
- `MessageHandler`: processes messages; other modules can implement routing/asynchronous execution.
- `MessageConverter` and annotation support infrastructure: transform and bind payloads/headers at the application layer.

It **is not a broker itself**, and does not itself provide Kafka partitions, JMS durable subscriptions, or AMQP exchanges. An in-JVM `MessageChannel` must not be treated as a durable cross-process queue unless connected to an appropriate transport/persistent store.

Distinguish other common modules:

| Spring Module | Commonly Seen APIs | Backing / Meaning |
|---|---|---|
| **Spring JMS** (`spring-jms`) | `JmsTemplate`, `@JmsListener`, `DefaultJmsListenerContainerFactory` | Integrates Jakarta Messaging/JMS providers |
| **Spring for Apache Kafka** (`spring-kafka`) | `KafkaTemplate`, `@KafkaListener`, listener container | Kafka producer/consumer/offsets |
| **Spring AMQP / Spring Rabbit** | `RabbitTemplate`, `@RabbitListener`, `RabbitAdmin` | Integrates AMQP, especially RabbitMQ |
| **Spring Messaging** (`spring-messaging`) | `Message<T>`, `MessageChannel`, `MessageHandler` | Internal abstractions leveraged by other integrations |
| **Spring Integration** | flows, channels, gateways, adapters | Connects endpoints and applies Enterprise Integration Patterns |
| **Spring Cloud Stream** | functions/binders | Another event-driven programming layer; binders connect to brokers like Kafka/RabbitMQ |

`org.springframework.messaging.Message<?>` is a **different type** from `jakarta.jms.Message`. Both types can appear in the same application; Spring JMS has converters/adapters to translate at the integration boundary. Spring Framework 7 also introduces `JmsClient` as a fluent API complementing `JmsTemplate`; code targeting older Framework versions must check available APIs.

## 6. Comparison by Operational Behavior

| Question to Answer | JMS / JMS Broker | Kafka | AMQP / AMQP Broker | Spring Messaging |
|---|---|---|---|---|
| Primary abstraction units? | Queue, Topic, Message, subscription | Topic, partition, record, offset, group | Frames/protocol; queue/exchange/binding per version | Message, headers, channel, handler |
| One job handled by one worker? | Queue and competing consumers | Consumer group handling partitions; task model must be designed explicitly | Appropriate broker queue (e.g., RabbitMQ) | Depends on concrete channel/transport |
| Broadcast to multiple systems? | Multiple Topic subscriptions | Multiple consumer groups | Multiple queues/bindings or broker mechanism | Only with an appropriate implementation |
| Replayable history? | No standard JMS replay-offset; depends on broker and archiving | Yes while records remain within retention | Cannot be inferred from protocol; depends on broker | Not provided by itself |
| Ordering? | Has JMS rules, altered by concurrency/selectors/redelivery | Ordering guaranteed within each partition | Depends on broker, queue, retries, concurrency | Depends on implementation |
| Recording processed status? | Session ack/transactions | Commit offset; transactions for supported scopes | Ack/settlement per protocol/broker | No shared cross-broker semantics |
| Spring integration focus? | `JmsTemplate`, `@JmsListener` | `KafkaTemplate`, `@KafkaListener` | `RabbitTemplate`, `@RabbitListener` with Spring Rabbit | `Message<?>` and channels/handlers |
| Data remaining after consumer reads? | Usually processed and acked off queue; topic depends on subscription | Retention independent of whether consumers read | Depends on queue/broker | Undefined |

**Note:** the "AMQP" column only states what the protocol standard defines; to compare storage or distribution guarantees, you must name RabbitMQ/Artemis specifically along with its configuration. Table cells represent default/typical models and do not replace testing in the target deployment environment.

## 7. A Common Scenario: E-Commerce Order

Suppose Order Service emits an event when an order is created, Payment Service executes a payment command, and Analytics Service updates reports.

### Option A — JMS Queue for Processing Commands

Order Service sends `ChargePayment(orderId)` to `payment.commands`. Multiple payment workers compete to read from the same queue; each command is distributed to one worker. Upon success, the worker commits/acks. For transient errors, retry/redelivery policies and DLQ must be configured on the consumer and broker.

Suitable when the primary goal is **distributing work to be done**, not retaining an event log for new groups to replay days later.

### Option B — JMS Topic for Events Broadcast to Subscriptions

Order Service publishes `OrderCreated` to a JMS Topic. Billing and Analytics each have separate subscriptions. If consumers must receive backlog while offline, durable subscriptions must be designed properly alongside retention/delivery policies. Durable subscriptions are not equivalent to Kafka log replay.

Suitable when a JMS provider is already in place and reliable subscription-based pub/sub is needed.

### Option C — Kafka Topic for Event History

Order Service appends `OrderCreated` to `orders.events` keyed by `orderId`. The Billing group and Analytics group read independently. When reporting logic changes, Analytics can use a new group or manage offset resets/seeks to reprocess **the portion of the log still in retention**.

Suitable when history is valuable, there are multiple independent pipelines, and real replay needs exist. Do not emit "payment commands" without duplicate controls as if they were harmless events: consumers must ensure idempotency and enforce business invariants.

### Option D — RabbitMQ and AMQP 0-9-1

Order Service publishes to exchange `orders.exchange` with routing key `order.created`. Bindings deliver one copy to `billing.queue` and one copy to `analytics.queue`; each queue can have multiple competing consumers. Flexible routing is a common strength.

This is a **specific broker + protocol implementation**, which does not imply every AMQP broker behaves like RabbitMQ.

### Spring Messaging in the Options Above

Teams can represent messages with `Message<T>`, process via channels/handlers, or use adapters. However, you still must choose and operate a **JMS broker, Kafka cluster, or RabbitMQ** separately for storage, delivery, and inter-service connectivity. Adding only the `spring-messaging` dependency will not create a message broker.

## 8. Java 17 Implementation Sample: Seeing the Spring JMS API Clearly

The example below uses **Spring Boot 3.4.5, Java 17, ActiveMQ Artemis**. It can run when the machine already has an **Artemis broker at localhost:61616**, credentials and permissions are properly configured, and queue `orders.queue` exists or the broker allows auto-creating queues. This is an end-to-end illustrative project, not a simulation of Kafka/AMQP.

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>jms-compare-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-artemis</artifactId>
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
~~~

`src/main/resources/application.properties` (adjust security settings for your broker):

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
~~~

`src/main/java/example/JmsCompareDemoApplication.java`:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsCompareDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsCompareDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner produce(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend("orders.queue", "order-123");
    }

    @Component
    public static class OrderConsumer {
        @JmsListener(destination = "orders.queue")
        public void receive(String orderId) {
            System.out.println("Handled: " + orderId);
        }
    }
}
~~~

Run from the directory containing `pom.xml` with:

~~~bash
mvn spring-boot:run
~~~

If the broker is reachable, the destination is available, and no other consumer picks up the message first, the output printed by business code is:

~~~text
Handled: order-123
~~~

Spring Boot also prints startup logs. The output above assumes one successful processing run; redelivery or running multiple instances may produce different output. In a plain Spring Framework project, you must configure `ConnectionFactory`, the listener container, and usually enable `@EnableJms` manually; Spring Boot has JMS auto-configuration that can set this up when dependencies are present.

**Explanation:** `JmsTemplate.convertAndSend` sends the `String` as a JMS `TextMessage` using the default converter; `@JmsListener` invokes the method when the JMS provider delivers a message to the queue. Even though the source code does not reference `jakarta.jms.Message` directly, Spring JMS still uses the JMS API underneath. A broker connection is a real requirement; there is no "automatic in-JVM message delivery" just from using the annotation.

### 8.1. Corresponding APIs When Changing Transports

The snippets below are **code placed inside a Spring bean with the respective transport properly configured**, not standalone Java programs. They help compare APIs, without implying equivalent semantics.

**Kafka** (requires Spring Kafka, Kafka broker, topic, and serializer/deserializer):

~~~java
// In a bean with KafkaTemplate<String, String> kafkaTemplate:
kafkaTemplate.send("orders.events", "order-123", "{\"type\":\"OrderCreated\"}");

// In a consumer bean:
@KafkaListener(topics = "orders.events", groupId = "analytics")
public void consumeEvent(String json) {
    System.out.println(json);
}
~~~

With Kafka, `"order-123"` is the key used for partitioning, and `"analytics"` is the consumer group. To ensure business processing can retry without duplicate side effects, an explicit commit, retry, and idempotency strategy is still required.

**RabbitMQ/AMQP 0-9-1** (requires Spring Rabbit, RabbitMQ broker, and exchange→queue binding):

~~~java
// In a bean with RabbitTemplate rabbitTemplate:
rabbitTemplate.convertAndSend("orders.exchange",
        "order.created", "{\"type\":\"OrderCreated\"}");

// In a listener bean:
@RabbitListener(queues = "analytics.queue")
public void consumeEvent(String json) {
    System.out.println(json);
}
~~~

Here `"orders.exchange"` and `"order.created"` belong to the AMQP 0-9-1 routing model; they are neither JMS destinations nor Kafka offsets.

**Spring Messaging** (Java snippet inside a method importing `Message` and `MessageBuilder`):

~~~java
Message<String> event = MessageBuilder.withPayload("order-123")
        .setHeader("eventType", "OrderCreated")
        .build();
~~~

The `event` object holds a payload and headers at the application layer. This snippet **has not sent it to any broker yet**; you must invoke an adapter/template/channel with a concrete implementation.

## 9. Choose Technology by Requirements, Not by Name

Answer these questions in order:

1. **Is the data a command/job or an event history?** Jobs needing only one worker to complete usually fit queues. Event histories with multiple consumers and replay usually fit Kafka.
2. **Must data be re-read after being processed?** If yes, define retention, offset/seek, and replay windows; Kafka provides this model directly. JMS/RabbitMQ require a separate archive/replay strategy if similar history is desired.
3. **Who needs to receive each message?** One worker, each subscription, each bound queue, or each consumer group? Explicitly write down copy counts and competition scope.
4. **What existing systems constrain you?** Enterprise apps already running a JMS provider and transactions; RabbitMQ with existing exchange/queue topology; Kafka already serving as the event backbone? The cost of changing semantics usually exceeds changing API names.
5. **What are ordering, latency, data volume, and multi-language requirements?** Verify against partitions, concurrency, protocols, and brokers. JMS is a Java API; AMQP and Kafka have multi-language clients.
6. **How are failures handled?** Define retry policies, DLQ, idempotency keys, correlation IDs, consumer lag/backlog observability, storage limits, and operational alerts.

| Scenario | Typically Reasonable Choice | Conditions to Verify |
|---|---|---|
| Multiple workers execute a task once at the business level | JMS Queue or RabbitMQ queue | Ack/transactions, retries, DLQ, idempotency |
| Broadcast events to multiple Java systems already using JMS | JMS Topic with matching subscriptions | Durable/shared subscriptions, TTL, and backlog storage |
| Audit, analytics, stream processing, rebuilding views | Kafka | Retention, partition key, offsets, schema evolution |
| Routing by exchange and routing key | RabbitMQ over AMQP 0-9-1 | Exchanges/bindings, publisher confirms, queue types |
| JMS API interoperability over AMQP 1.0 | JMS provider/client such as Apache Qpid JMS | Broker supports AMQP 1.0 and matching `jakarta.jms` version |
| Uniform payload/header model within Spring | Spring Messaging plus required adapters | Actual underlying transport and adapter semantics |

These are architectural criteria, not absolute performance claims. Two technologies may both solve a problem, yet their incident-handling cost, operations, and data fit will differ.

## 10. Common Pitfalls and Risks

**Pitfall 1 — "Both JMS and Kafka have topics, so swapping dependencies is all it takes."** False: JMS uses subscriptions, while Kafka uses logs/offsets/consumer groups. Migration requires redesigning replay, ordering, retries, storage, and event contracts.

**Pitfall 2 — "AMQP is RabbitMQ."** False: RabbitMQ is a broker supporting multiple protocols; AMQP also has wire-incompatible versions. Always state both the broker and the protocol version.

**Pitfall 3 — "Using Spring Messaging gives you a durable queue."** False: `MessageChannel` and `Message<T>` are contracts/objects. Persistence and inter-service delivery must come from implementations and a broker.

**Pitfall 4 — "Once acked or committed, the entire business flow is guaranteed exactly-once."** False: failures can happen between database writes, external API calls, sending messages, and commit/ack. Design **idempotent consumers**, business keys/unique constraints, and deduplication; when emitting events tied to database transactions, consider a **transactional outbox**.

**Pitfall 5 — "Adding consumers always improves both ordering and speed."** Not by default: multiple JMS workers can finish out of order, Kafka parallelism is capped by partition count per group, and RabbitMQ is affected by prefetch/ack/queue type.

**Pitfall 6 — "Persistent means stored forever."** JMS `PERSISTENT` targets transport durability; Kafka retention follows configured policies; RabbitMQ persistence and queue retention depend on configuration. Define concrete data SLAs.

**Pitfall 7 — "Every transport can pass arbitrary Java objects."** Prefer versioned wire formats (JSON/Avro/Protobuf...), validate schemas, and avoid relying by default on Java serialization. In Spring JMS, the default converter supports String/byte[]/Map; custom business objects need an appropriate converter.

**Pitfall 8 — "Infinite retries will fix the problem on their own."** Some errors are unrecoverable (malformed schema payload, data violating invariants). Separate transient errors from permanent errors; cap retries, use DLQ/quarantine, add correlation IDs, and monitor backlog/consumer lag.

## 11. Self-Check for Accurate Understanding

1. **An invoice-printing job must be handled by one worker:** JMS Queue or RabbitMQ queue is the direct model; you must still handle redelivery and prevent duplicate printing in business logic.
2. **Three teams want to read the same price-change history, and a new team needs to rerun last week:** Kafka fits if retention still holds last week's data. A durable JMS Topic does not automatically allow rewinding all acknowledged history.
3. **Is Java calling the JMS API over AMQP 1.0 contradictory?** No. JMS describes the API; Qpid JMS is an example client using AMQP 1.0.
4. **Given `org.springframework.messaging.Message<String>`, where is the broker?** There is no broker yet. You need a concrete channel/adapter implementation and actual transport configuration.
5. **A Kafka topic has 4 partitions, and 10 consumers are started in the same consumer group:** typically at most 4 consumers get partitions assigned to read this topic concurrently; the remaining instances do not increase parallelism for that topic alone.
6. **A JMS Topic has 2 durable subscriptions, each with 3 shared consumers:** each subscription gets a matching copy, and the shared consumers within that subscription divide the messages among themselves; not all 6 instances receive every message.

## 12. Official Reference Documentation

- [Jakarta Messaging 3.1 specification](https://jakarta.ee/specifications/messaging/3.1/) — Queue, Topic, acknowledgment, durable subscription, and message selector semantics.
- [Spring Framework — JMS integration](https://docs.spring.io/spring-framework/reference/integration/jms.html) — `JmsTemplate`, `@JmsListener`, listener containers, and transactions.
- [Spring Boot — JMS and Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — auto-configuration and broker configuration for examples.
- [Apache Kafka — Design](https://kafka.apache.org/40/design/design/) — partitions, consumers, and offset/replay.
- [RabbitMQ — AMQP 0-9-1 concepts](https://www.rabbitmq.com/tutorials/amqp-concepts) and [protocols](https://www.rabbitmq.com/docs/protocols) — exchanges, bindings, and differences between AMQP 0-9-1 and 1.0.
- [Apache Qpid JMS](https://qpid.apache.org/components/jms/index.html) — JMS API running over AMQP 1.0.
- [Spring for Apache Kafka](https://spring.io/projects/spring-kafka/) and [Spring AMQP](https://spring.io/projects/spring-amqp) — identifying the right templates/listeners per transport.

**Key takeaway:** When comparing messaging solutions, always write out all four layers **application API → protocol/client → broker/storage → processing semantics**. Only then does the question "JMS vs. Kafka vs. AMQP vs. Spring Messaging?" turn into a verifiable engineering decision.
