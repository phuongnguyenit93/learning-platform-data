# Point-to-Point and the Queue Model in Spring JMS

## 1. Objectives and Context

**Point-to-point (PTP)** is a model for sending messages to a **Queue** so that one of the eligible consumers processes each message delivery. This is one of the two destination models (*messaging domains*) of Jakarta Messaging (JMS); the other model is **publish/subscribe** with Topic.

After this lesson, you should be able to explain the path of a message from producer to broker and consumer, distinguish Queue from Topic, implement a producer and multiple consumers with Spring JMS, understand acknowledgment/transaction/redelivery, and recognize limitations regarding ordering, duplication, and recoverability.

Running example: an ordering service sends request `ORDER-001` to `orders.queue`; one worker processes the order. If the number of workers is increased, they **compete to pull work from the same queue**, rather than every worker receiving a copy.

## 2. Components and Processing Flow

- **Producer (sender):** creates and sends messages, typically via `JmsTemplate` or `JmsClient` (Spring Framework 7+).
- **Queue:** a JMS destination holding messages awaiting delivery/processing according to broker mechanisms.
- **Broker / JMS provider:** the system implementing JMS (for example, ActiveMQ Artemis) that manages storage, dispatching, acknowledgment, redelivery, and error policies. A Queue is not simply a `java.util.Queue` residing in application memory.
- **Consumer (receiver/worker):** receives messages using `MessageConsumer`, `JMSConsumer`, or a Spring listener.
- **ConnectionFactory and Session:** provide the connection and JMS processing context; Spring typically manages their lifecycle on behalf of business code.
- **Acknowledgment / commit:** signals that help the broker decide whether a message has been successfully processed or must remain pending / be redelivered.

~~~mermaid
flowchart LR
    P1["Producer A"] --> Q[("orders.queue")]
    P2["Producer B"] --> Q
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
~~~

**How to read the diagram:** the three arrows from the queue to the consumers represent *options for receiving work*. They do not mean that the same message is broadcast simultaneously to all three consumers. A single message delivery goes to one consumer; in case of failure, **the same message may be redelivered**.

Typical lifecycle:

1. The producer creates a payload and optional headers/properties such as order ID, priority, and time-to-live.
2. The producer sends to destination `orders.queue`; once sending succeeds according to the provider's protocol, the broker accepts the message. If sent within a transaction, the message only becomes available to consumers after commit.
3. The broker selects an eligible consumer (which may be based on readiness to receive, selector, prefetch, and provider policies).
4. The consumer receives and executes the business logic. The message may be in an *in-flight* state, not yet confirmed as complete.
5. When acknowledgment or JMS transaction commit succeeds, the broker considers that delivery complete. If rolled back, the session loses its connection, or an error matching the redelivery policy occurs, the message may return to the queue for further delivery.

There can be **multiple producers and multiple consumers** on the same queue. A queue decouples send time from processing time: when workers are busy or paused, messages can build up (backlog), depending on the broker's capacity, persistence, and expiry configuration.

## 3. Important Queue Rules

### 3.1. One delivery to one consumer: competing consumers

When there are three messages M1, M2, M3 and two consumers C1, C2, one *possible* distribution is C1 receiving M1 and M3, and C2 receiving M2. The actual distribution is not required by the JMS specification to be round-robin or strictly fair.

| Characteristic | Queue (point-to-point) | Topic (publish/subscribe) |
| --- | --- | --- |
| Purpose | Distribute work to one consumer per delivery | Broadcast events to multiple subscriptions |
| Multiple consumers/subscribers | Compete to receive messages on the same queue | Each matching subscription can receive a copy |
| When receivers are not running | Messages can wait on the queue per broker policy | Depends on subscription type (durable/non-durable) |
| Typical use cases | Order processing, background jobs, sending emails | Event notifications to multiple systems |

**Do not confuse "one consumer per delivery" with "processed exactly once forever".** Before commit/ack succeeds, the provider may redeliver the same message, even to a different consumer.

### 3.2. Queues do not automatically guarantee global processing order

JMS defines ordering rules under specific conditions, but it does not guarantee that multiple workers finish processing in the exact order producers sent messages. For example, C1 receives M1 and runs for 5 seconds, while C2 receives M2 and finishes after 100 ms: as a result, M2 completes before M1. There are also priority, TTL, delivery delay, multiple producers/sessions, and redelivery.

If **strict ordering** is required, consider limiting concurrency for the corresponding flow to 1, or using an entity-key grouping/routing mechanism supported by the provider (for example, message groups). Throughput must be traded off, and the behavior of the specific broker must be verified.

### 3.3. Do not equate a queue with a work database

The broker manages message delivery, but typically does not replace a business-state database on its own. For orders, the payload should carry `orderId` or `eventId`; the "paid/completed" status needs to be confirmed in the business storage system. A message may expire, be moved to a dead-letter queue, or be deleted according to administrative policies.

## 4. Spring JMS Architecture

In Spring Framework, application code typically works at a high level:

- **`JmsTemplate`:** sends using `convertAndSend`, sends customized messages using `send`, and receives synchronously using `receive`/`receiveAndConvert`. A configured bean can be shared across threads.
- **`@JmsListener`:** declares an asynchronous receiving method; Spring creates a listener container and passes the payload, headers, or raw `jakarta.jms.Message` into the parameters.
- **`DefaultJmsListenerContainerFactory`:** configures the container for listeners, including connection factory, session transaction, concurrency, and message converter.
- **`ConnectionFactory`:** creates connections to the JMS provider; Spring Boot provides auto-configuration for Artemis when the appropriate starter is present.
- **`MessageConverter`:** converts Java data into JMS messages and vice versa. For strings, the default converter typically creates a `TextMessage`.

Starting from Spring Framework 6 / Spring Boot 3, the JMS API uses the **`jakarta.jms.*`** namespace instead of the legacy `javax.jms.*`; do not mix the two library families in the same example. The examples below use Java 17 and Spring Boot 3.5.x.

## 5. Runnable Example: One Queue, Two Competing Consumers

The application runs **embedded ActiveMQ Artemis** for local learning. The embedded broker here is configured *not to persist to disk*, solely for practice; production systems should configure a dedicated broker, persistence, security, and appropriate monitoring.

Requirements: **JDK 17+** and **Maven 3.6.3+**. Directory structure:

~~~text
queue-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/queuedemo/
    │   ├── QueueDemoApplication.java
    │   └── OrderConsumer.java
    └── resources/application.properties
~~~

### 5.1. Maven Declaration

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>queue-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
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

The Artemis starter provides the components needed to connect and integrate JMS; the `artemis-jakarta-server` dependency enables using the embedded broker. The Artemis dependency version is managed by the Spring Boot BOM.

### 5.2. Configuring the Broker and Queue Destination

**`src/main/resources/application.properties`**:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
~~~

- `orders.queue` is the queue created when the embedded broker starts.
- `pub-sub-domain=false` determines that destination names are resolved by default as **Queue**, not Topic.
- `session.transacted=true` instructs the listener to use a local JMS transaction: successful execution commits; an exception propagating out of the listener triggers a rollback and enables redelivery according to the broker.
- Persistence is disabled, so do not use this example to infer survival guarantees across broker restarts.

### 5.3. Producer Sending Five Messages

**`src/main/java/com/example/queuedemo/QueueDemoApplication.java`**:

~~~java
package com.example.queuedemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class QueueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExample(JmsTemplate jmsTemplate) {
        return args -> {
            for (int i = 1; i <= 5; i++) {
                String orderId = "ORDER-%03d".formatted(i);
                jmsTemplate.convertAndSend("orders.queue", orderId);
                System.out.println("sent " + orderId);
            }
        };
    }
}
~~~

`ApplicationRunner` sends messages after the application initializes. `convertAndSend` converts a Java string into a JMS `TextMessage` and sends it to the queue. The producer does not need to hold connections or manage `Session` manually: `JmsTemplate` handles most of that work.

### 5.4. Listener with Two Consumers

**`src/main/java/com/example/queuedemo/OrderConsumer.java`**:

~~~java
package com.example.queuedemo;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.queue", concurrency = "2")
    public void handle(String orderId, Message message) throws JMSException {
        System.out.printf(
                "processed %s by %s, redelivered=%s%n",
                orderId,
                Thread.currentThread().getName(),
                message.getJMSRedelivered()
        );
    }
}
~~~

`concurrency="2"` creates two concurrent consumers/sessions for this listener; **each message is received by one of the two consumers in a single delivery**. The `String` parameter is the payload converted by Spring; `Message` is the raw JMS object for reading metadata. `JMSRedelivered` helps observe redelivery, but it is not a deduplication key.

### 5.5. Running and Observing

In the `queue-demo` directory:

~~~bash
mvn spring-boot:run
~~~

The log will contain **five lines from `sent ORDER-001` to `sent ORDER-005`** and, if all processing succeeds, **five `processed ORDER-...` lines**. The send and receive lines may interleave; thread names, which consumer receives each order, and the order of `processed` lines vary between runs. There is no fixed stdout order for line-by-line comparison. Press Ctrl+C to stop the application.

Try changing `concurrency = "1"` and running again: a single consumer receives all the work. Change it back to `"2"` or `"3"` and observe thread names and concurrent processing capability. Do not use a single run with too few messages to conclude that the broker always distributes work evenly.

## 6. Acknowledgment, Transaction, and Redelivery

Queue reliability depends on **when the message is acknowledged**, not merely on whether the Java method was invoked.

| Mechanism | What to understand | Notes |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | The JMS provider/container acknowledges according to the message reception rules of auto mode | With Spring listener containers, errors from business code may not produce the desired recovery mechanism; do not assume it is safe for critical work by default |
| `CLIENT_ACKNOWLEDGE` | The client explicitly calls `Message.acknowledge()` | Must understand the acknowledgment scope of the entire session, which is not always just a single message |
| `DUPS_OK_ACKNOWLEDGE` | Acknowledgment may be delayed | Accepts duplicate delivery in exchange for performance in certain cases |
| **Transacted JMS session** | Commit confirms the receive (and JMS operations in the same transaction); rollback allows the message to be redelivered | Suitable for listeners requiring reliable processing; does not automatically span other database transactions |

With Spring, `DefaultMessageListenerContainer` can be configured with `sessionTransacted=true`; when the listener throws an uncaught exception, the container rolls back the JMS transaction. The broker then applies its redelivery policy, wait interval, attempt count, and dead-letter queue (if configured). **Retry/DLQ details belong to the broker and deployment configuration**, not a fixed JMS constant.

Example of temporarily modifying the listener method body to test an error:

~~~java
// Illustrative snippet REPLACING the handle method body in section 5.4;
// also requires importing java.util.concurrent.atomic.AtomicBoolean.
private final AtomicBoolean failOnce = new AtomicBoolean(true);

@JmsListener(destination = "orders.queue", concurrency = "2")
public void handle(String orderId, Message message) throws JMSException {
    if ("ORDER-003".equals(orderId) && failOnce.compareAndSet(true, false)) {
        throw new IllegalStateException("Simulated error before commit");
    }
    System.out.printf("processed %s, redelivered=%s%n",
            orderId, message.getJMSRedelivered());
}
~~~

**This is a replacement snippet inside `OrderConsumer`, not a standalone Java file.** When the error is thrown, the JMS transaction rolls back; if the broker is still running and allows redelivery, `ORDER-003` may be received again and print `redelivered=true`. Timing and attempt counts are decided by the broker. Avoid writing code that catches an exception and ignores it if rollback is desired:

~~~java
// Not suitable when broker retry is needed:
try {
    processOrder(orderId);
} catch (RuntimeException error) {
    log.warn("Processing failed", error);
    // Returning normally: the container may commit the current delivery.
}
~~~

The second snippet only illustrates a common mistake; `processOrder` and `log` are hypothetical components, not a self-contained runnable program. If you need to catch an error to add information, rethrow the exception or use a clearly designed error strategy.

### 6.1. At-most-once, at-least-once, and "exactly once"

- **At-most-once:** processes at most once by design, accepting message loss on certain failures.
- **At-least-once:** strives not to lose incomplete messages; this allows **duplicates** upon connection errors, rollbacks, or crashes.
- **Exactly-once *business effect*:** only achievable at the business layer by combining transaction boundaries, duplicate detection, and/or proven specialized mechanisms. **A Queue + JMS transaction alone does not guarantee that DB writes, email sending, or HTTP calls happen strictly once.**

Classic scenario:

1. The consumer receives message `ORDER-003`.
2. The consumer writes the order status to the DB and the DB commits.
3. The process crashes **before the JMS session commits**.
4. The broker does not receive acknowledgment/commit and may redeliver the message.
5. If reprocessing does not check for duplicates, the business action is executed a second time.

A common solution is an **idempotent consumer**: each message has a stable business `messageId` (created by the producer), and a processed marker is stored with a unique key in the same transaction as the DB change. If the record already exists, skip the duplicate business effect while still completing the listener normally to acknowledge the message. `orderId` can be used as the key if the business truly allows only one processing per order; if multiple distinct events exist for the same order, a separate `eventId` is needed.

Conceptual example of a tracking table in PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(100) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

-- In the SAME DB transaction as the business change:
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('billing-worker', 'event-123')
ON CONFLICT DO NOTHING;
~~~

Only when `INSERT` actually creates a new row should the corresponding business effect be executed; if a DB rollback occurs, both the marker and the effect must roll back together. The SQL above is a design example for PostgreSQL, **not complete transaction code**. Do not treat `JMSMessageID` as a substitute for a stable `eventId` across all producer retry mechanisms.

### 6.2. A JMS transaction does not automatically merge with a DB transaction

`JmsTransactionManager` manages local JMS resources. `DataSourceTransactionManager` manages JDBC resources. Without proper transaction coordination, **DB commit and JMS commit are two separate operations**; do not assume you have a distributed transaction merely by adding `@Transactional` without knowing which transaction manager is active.

If consistency between DB and message sending is needed, consider the **transactional outbox** pattern (writing the DB change and outbox record in the same DB transaction, with a separate relay moving outbox records to JMS). For consumers, use idempotency/inbox; only consider XA/JTA when there are special requirements and supporting infrastructure. Outbox does not eliminate duplicates completely, because the relay may resend after a crash; consumers still need to be idempotent.

## 7. Tuning Delivery and Reception

### 7.1. Conditionally Increasing Concurrency

Increase `concurrency` to process multiple messages in parallel when tasks are independent, but check:

- Connection/session counts, thread limits, and broker quotas.
- Downstream DB/HTTP capacity; adding consumers does not help if the bottleneck is in the DB.
- Business ordering; two messages with the same `orderId` may run concurrently without a key/group.
- Backlog, processing time, in-flight message count, retry rate, and DLQ; measure instead of merely adding workers.

`concurrency="2-5"` (when supported by the listener container configuration) can allow the consumer count to scale within this range. The broker may prefetch messages for each consumer; distribution is not necessarily balanced instantaneously.

### 7.2. Selectors for Filtering Messages on the Same Queue

JMS message selectors use expressions over **headers/properties**, not arbitrary fields inside a JSON payload. Example of a producer sending a message with property `region`:

~~~java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("ORDER-101");
    message.setStringProperty("region", "VN");
    return message;
});
~~~

The consumer receives only messages with a matching property:

~~~java
@JmsListener(destination = "orders.queue", selector = "region = 'VN'")
public void handleVn(String orderId) {
    System.out.println("VN order: " + orderId);
}
~~~

The two snippets above **illustrate separate usage**; when combined into an application, they must be placed in appropriate beans and ensure no unintended overlapping listeners are created. Messages not matching the selector will not be received by that listener; if no matching consumer exists, messages may pile up. Do not use selectors as a substitute for authorization or data protection.

### 7.3. TTL, Persistence, Priority, and DLQ

- **Persistent delivery** requires the provider to retain messages according to JMS durability rules, though this also depends on broker, disk, and transaction configuration. The embedded `persistent=false` example above intentionally does not demonstrate survival across restarts.
- **Time-to-live (TTL)** can cause messages to expire before processing; managing expired messages is a broker policy.
- **Priority** can cause higher-priority messages to be delivered first, weakening simple FIFO assumptions.
- **DLQ** holds messages that cannot be processed after the configured retry/redelivery policy. You must monitor it and have a process for triaging, fixing errors, and controlled reprocessing; do not assume failed messages vanish safely on their own.
- **Delivery count:** for providers supporting the Jakarta Messaging specification, `JMSXDeliveryCount` indicates the number of deliveries; `JMSRedelivered` signals redelivery. These two fields serve diagnostics and do not replace idempotency.

Name queues clearly by function (`orders.commands`, `payments.requests`) and maintain message contracts: schema versioning, data types, stable IDs, maximum size, serialization errors, protection of sensitive data, and processing time limits.

### 7.4. Synchronous Receive vs. Asynchronous Listener

Synchronous reception is possible:

~~~java
// Illustrative snippet running inside a Spring bean with JmsTemplate injected.
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

This call may block until a message is received or a timeout occurs. When polling periodically, set an appropriate `receiveTimeout` and consider transactions. Most long-lived workers prefer `@JmsListener` because Spring manages consumer lifecycle, threads, and connection recovery.

## 8. Diagnosing Common Issues

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Producer sends but consumer does not receive | Wrong destination name, Topic/Queue confusion, unmatched selector, listener not started, or misconfigured connection | Check the queue on the broker, `destination`, `pubSubDomain`, selector, and connection logs |
| A message is processed twice | Rollback, crash before commit, connection drop, duplicate producer send | Use a stable event ID, idempotency, and inspect delivery count |
| Messages stuck in queue | Consumer stopped, high send rate, unmatched selector, slow downstream | Inspect queue depth, in-flight count, receive rate, listener errors, and resource limits |
| Uneven reception across consumers on the same queue | Prefetch, differing worker speeds, consumer contention, broker dispatch | Measure throughput and latency, check provider configuration; do not assume round-robin |
| Processing order differs from send order | Concurrency, multiple producers/sessions, retries, priority | Design ordering keys, limit concurrency, or apply appropriate message groups |
| Failing message retried endlessly | No retry limit/DLQ or uncontrolled rollback configuration | Distinguish transient errors from data errors; configure redelivery delay/max attempts/DLQ per broker |
| Messages lost after restart in demo | Embedded Artemis has `persistent=false` | Enable persistence and configure a production-grade broker properly when durability is needed |

**Minimum operational observability:** queue depth, age of oldest message, number of connected consumers, enqueue/dequeue rate, retry count, DLQ depth, processing duration, parse errors, and downstream system health. A continuously growing backlog is a symptom that requires finding the root cause, not automatically just adding more consumers.

## 9. Knowledge Self-Check

1. There are 100 messages and 4 consumers listening on the same queue. Does each consumer receive all 100 messages? **No.** They split the deliveries; equal distribution is not guaranteed.
2. A consumer updated the DB but crashed before JMS commit. What can happen? **The message is redelivered**, creating a risk of duplicate DB effects if the consumer is not idempotent.
3. Does scaling from 1 to 8 consumers preserve completion order of M1 before M2? **No.** Parallelism and redelivery break the global completion-order assumption.
4. Can `@JmsListener` be used with both queues and topics? **Yes.** The corresponding destination type and subscription semantics must be configured; this lesson only implements Queue.
5. When nobody is listening, do messages always persist forever? **No.** It also depends on persistence, TTL, capacity, broker policy, and administration.

## 10. Official Reference Documentation

- [Jakarta Messaging 3.1 — point-to-point model and Queue semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), section 4.1.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html), `JmsTemplate`, transactions, and listener containers.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html), `@JmsListener` and concurrency.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html), synchronous, asynchronous, and transacted listeners.
- [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html), embedded Artemis and auto-configuration.

**Key takeaway:** Queue solves the problem of *assigning each message delivery to one worker*, whereas business correctness depends on acknowledgment/transaction, redelivery policies, and idempotent application design.
