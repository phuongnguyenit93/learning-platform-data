# JMSDeliveryTime and Eligible Delivery Time in Spring JMS

## 1. Goal and Context

In asynchronous systems, not every message needs to be processed the instant the producer sends it. For example, when a new order is created, the application may want to **wait 5 minutes** before reminding the customer to complete payment. The producer can send a message to the broker right now, while requiring that **no consumer receive it before the eligible time**.

Jakarta Messaging (JMS) supports this with two concepts:

- **Delivery delay**: minimum delay duration, in milliseconds, configured on the producer before sending.
- **`JMSDeliveryTime`**: standard header assigned by the JMS provider, representing the **earliest time** the message may be delivered to a consumer.

After this lesson, you should be able to explain how `JMSDeliveryTime` is calculated, use `MessageProducer`/`JMSProducer`/`JmsTemplate` to configure delay, distinguish `JMSTimestamp`, `JMSExpiration`, and actual receive time, understand effects of transactions, TTL, Queue/Topic, and retries, and write Java 17+ examples.

**Scope:** this lesson covers **when a message becomes eligible for delivery** per Jakarta Messaging and how to use it from Spring JMS. It does not replace multi-day schedulers, business deadline management, or broker-specific retry mechanisms.

## 2. Exact Definition of JMSDeliveryTime

`JMSDeliveryTime` is a `long` header (milliseconds since 00:00:00 UTC on January 1, 1970, i.e., Unix epoch), introduced in JMS 2.0 and carried forward in Jakarta Messaging 3.x.

Per the specification, the provider computes:

~~~text
JMSDeliveryTime = sendTime + deliveryDelay
~~~

Where:

- `sendTime` is the time the client performs the send according to the JMS provider, **not transaction commit time**.
- `deliveryDelay` is the minimum delay in milliseconds set on the producer; **default is 0**.
- `JMSDeliveryTime` is the **earliest** time the broker is allowed to make the message deliverable to a consumer.
- A consumer **must not receive it before** that time. Delivery at that exact millisecond **is not guaranteed**.

Illustrative diagram:

~~~mermaid
flowchart LR
    A["10:00:00 Producer sends"] --> B["Broker receives message"]
    B --> C["10:00:00–10:04:59 Not yet delivered"]
    C --> D["10:05:00 Delivery becomes eligible"]
    D --> E["Consumer actually receives at >= 10:05:00"]
~~~

For example, `deliveryDelay = 300_000L` means **5 minutes**, not 300,000 seconds. If the producer sends at 10:00, the message will have `JMSDeliveryTime` around 10:05. It might be received at 10:05:00 or 10:05:07, or even later if the broker/consumer is busy. Do not interpret delay as a promise to execute at an exact minute/second.

**Never use `Thread.sleep` on the producer or consumer.** The broker/provider is responsible for holding ineligible messages. Sleeping on the consumer happens **after the message has already been delivered**, tying up threads and prolonging transactions/acknowledgments.

## 3. Distinguishing Related Timestamps

| Field or timestamp | Meaning | Source of value |
| --- | --- | --- |
| `JMSTimestamp` | Time the message was handed to the JMS provider for sending, not necessarily physical arrival at the broker. | Set by provider after send; can be 0 if client requests disabling timestamps and provider honors it. |
| `JMSDeliveryTime` | **Earliest time** the message is permitted to be delivered. | Computed by provider from send time + delivery delay. |
| `JMSExpiration` | Timestamp when the message expires when TTL is set; 0 means no JMS TTL expiration. | Computed by provider from send time + time-to-live. |
| `receivedAt` | Time the consumer actually receives the message or the listener begins processing. | Recorded by the application; not a standard JMS header. |
| Business `scheduledAt` | Business target time/deadline. | Stored or sent by the application in the message to manage schedules independently of the broker. |

Example:

~~~text
sendTime         = 10:00:00
deliveryDelay    = 5 minutes
timeToLive       = 30 minutes

JMSTimestamp     ≈ 10:00:00
JMSDeliveryTime  = 10:05:00
JMSExpiration    = 10:30:00
receivedAt       = 10:05:08   (an example run)
~~~

If `JMSExpiration != 0`, the message is unexpired and time-eligible for delivery when:

~~~text
receivedAt >= JMSDeliveryTime
and
receivedAt < JMSExpiration
~~~

That is solely the **timing condition**; the broker also requires the message to be committed, a valid destination/subscription, an available consumer, and other delivery conditions. If `JMSExpiration == 0`, there is no standard TTL expiry constraint, though broker memory/disk policies can still apply.

Reading headers in a consumer via Jakarta Messaging API:

~~~java
// Fragment: jakarta.jms.Message message is already available.
long earliestEpochMillis = message.getJMSDeliveryTime();
long sentEpochMillis = message.getJMSTimestamp();
long expirationEpochMillis = message.getJMSExpiration();

System.out.println(
        "earliest=" + java.time.Instant.ofEpochMilli(earliestEpochMillis));
System.out.println("sent=" + sentEpochMillis);
System.out.println("expires=" + expirationEpochMillis);
~~~

This is a **fragment**, not a standalone program. `JMSExpiration == 0` means no TTL expiration timestamp; do not format 0 as a "real 1970 expiration time". `JMSTimestamp` is sometimes 0 under disable-timestamp policies; do not rely on `JMSDeliveryTime - JMSTimestamp` as a universally valid formula across all configurations.

`JMSDeliveryTime` is stored as UTC epoch milliseconds. To display in Vietnam time:

~~~java
// Fragment with long earliestEpochMillis read from message.
java.time.ZonedDateTime local =
        java.time.Instant.ofEpochMilli(earliestEpochMillis)
                .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"));
System.out.println(local);
~~~

Time zone only affects display formatting; **it never changes delivery eligibility time**.

## 4. Who Sets the Header? Configuring It Properly

`Message.getJMSDeliveryTime()` is for **reading** the header. This header is **populated by the JMS provider**, not something the client arbitrarily writes for the broker to obey.

| API | Role | Usage |
| --- | --- | --- |
| `MessageProducer.setDeliveryDelay(long)` | Sets delay for subsequent sends on classic JMS producer. | **Use** |
| `JMSProducer.setDeliveryDelay(long)` | Sets delay when using simplified `JMSContext` API. | **Use** |
| `Message.getJMSDeliveryTime()` | Reads the provider-assigned timestamp. | **Use** |
| `Message.setJMSDeliveryTime(long)` | Setter for the provider to populate header on send. | **Do not use for client-side scheduling** |
| `Message.DEFAULT_DELIVERY_DELAY` | Default constant `0L`. | Use when explicit clarity is helpful |

**Misuse** example:

~~~java
// Do not use this to create a delayed message:
message.setJMSDeliveryTime(System.currentTimeMillis() + 60_000L);
producer.send(message);
~~~

Per the specification, a header value set by the client before send **does not control scheduling**, and may be ignored/overwritten by the provider on send. The proper way with `MessageProducer` is:

~~~java
// Fragment: producer and message already created.
producer.setDeliveryDelay(60_000L);
producer.send(message);
~~~

One `MessageProducer` can send many messages. If you set a 60-second delay, subsequent sends on that producer **keep using that delay** unless reconfigured. If different job types need different policies, manage producer lifecycle and state explicitly.

When a **synchronous send** succeeds, once the send call returns, `JMSDeliveryTime` has been populated on the sent message object; the consumer receives the same value. When calling **asynchronous send** with a `CompletionListener`, read provider-assigned headers only **after the successful completion callback**, because the send may not be complete yet.

Note: broker administrators can configure **overrides** for delivery delay per provider policy. In that case, the returned header must reflect the effective value applied by the provider; do not assume every broker strictly honors 100% of the application's requested value when administrative overrides exist.

## 5. Using the Classic Jakarta JMS API

`MessageProducer.setDeliveryDelay(long)` was added in JMS 2.0. `ConnectionFactory`, `Connection`, `Session`, and `MessageConsumer` remain part of the core JMS model.

~~~java
// Fragment inside a method that received jakarta.jms.ConnectionFactory factory.
try (jakarta.jms.Connection connection = factory.createConnection();
     jakarta.jms.Session session =
             connection.createSession(false,
                     jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {

    jakarta.jms.Queue queue = session.createQueue("orders.delayed");

    try (jakarta.jms.MessageProducer producer =
                 session.createProducer(queue);
         jakarta.jms.MessageConsumer consumer =
                 session.createConsumer(queue)) {

        producer.setDeliveryDelay(3_000L);
        jakarta.jms.TextMessage outbound =
                session.createTextMessage("ORDER-123");

        producer.send(outbound);

        long permittedAt = outbound.getJMSDeliveryTime();
        System.out.println("Eligible at: " +
                java.time.Instant.ofEpochMilli(permittedAt));

        connection.start();

        jakarta.jms.Message inbound = consumer.receive(10_000L);
        if (inbound == null) {
            throw new IllegalStateException("Did not receive message");
        }
        System.out.println("Received: " + inbound.getBody(String.class));
    }
}
~~~

**How it works:**

1. `createQueue("orders.delayed")` creates a destination handle, not necessarily the physical queue. Configure/provision the queue on the broker.
2. Producer sets a 3-second delay and sends a `TextMessage`.
3. After synchronous send succeeds, `JMSDeliveryTime` is readable.
4. `connection.start()` enables message delivery to the consumer, yet **does not bypass delivery delay**.
5. `receive(10_000)` waits up to 10 seconds from the call; it **does not make the broker change `JMSDeliveryTime`**.
6. This code requires a real `ConnectionFactory` and a broker with the queue; hence it is a **fragment**, not a standalone `main` file.

**Do not confuse `receive(timeout)` with delay:** receive timeout is how long the consumer **is willing to wait**, while delivery delay is how long the broker **must not deliver early**.

## 6. Using the Simplified Jakarta JMS API

Since JMS 2.0, `JMSContext`/`JMSProducer` provides a more concise style. `JMSProducer.setDeliveryDelay` returns the producer to support chaining:

~~~java
// Fragment with jakarta.jms.ConnectionFactory factory.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.delayed");

    jakarta.jms.JMSProducer producer = context.createProducer()
            .setDeliveryDelay(3_000L);

    jakarta.jms.TextMessage outbound =
            context.createTextMessage("ORDER-123");
    producer.send(queue, outbound);

    System.out.println(
            java.time.Instant.ofEpochMilli(outbound.getJMSDeliveryTime()));
}
~~~

`JMSProducer` is lightweight and needs no separate `close()`; `JMSContext` is a closeable resource. A `JMSContext` auto-starts delivery by default; if an application calls `setAutoStart(false)`, it must start it at the proper time before receiving.

**Thread safety warning:** `JMSContext` and `Session` must not be shared arbitrarily across multiple threads for concurrent sends/receives. With Spring, let templates/listener containers manage resources or create dedicated contexts per processing thread.

## 7. Runnable Example with Java 17+ and Spring Boot

The following project uses **Spring Boot 3.5.7** to configure `ConnectionFactory` and **embedded ActiveMQ Artemis** for experimentation. Java code uses `JMSProducer` and `JMSConsumer` directly to inspect native headers. The embedded broker is for learning only; the example intentionally disables persistence.

Project layout:

~~~text
delivery-time-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/deliverytime/
    │   └── DeliveryTimeDemoApplication.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>delivery-time-demo</artifactId>
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

Spring Boot manages the required dependency versions; there is no need to hardcode an Artemis server version in the example.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.delayed
spring.artemis.embedded.persistent=false
spring.main.banner-mode=off
~~~

- `mode=embedded` starts an embedded broker alongside the application.
- `queues=orders.delayed` creates the test queue when the broker starts.
- `persistent=false` means the demo **does not demonstrate message survival across restarts**. Production needs a dedicated broker or proper persistence and capacity configuration.

### 7.3. DeliveryTimeDemoApplication.java

~~~java
package com.example.deliverytime;

import java.time.Instant;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DeliveryTimeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryTimeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrateDelay(ConnectionFactory factory) {
        return args -> {
            try (JMSContext context = factory.createContext()) {
                Queue queue = context.createQueue("orders.delayed");

                try (JMSConsumer consumer = context.createConsumer(queue)) {
                    JMSProducer producer = context.createProducer()
                            .setDeliveryDelay(2_000L);

                    TextMessage outbound =
                            context.createTextMessage("ORDER-123");

                    producer.send(queue, outbound);

                    long earliest = outbound.getJMSDeliveryTime();
                    System.out.println(
                            "Earliest: " + Instant.ofEpochMilli(earliest));

                    Message incoming = consumer.receive(10_000L);
                    if (!(incoming instanceof TextMessage received)) {
                        throw new IllegalStateException(
                                "Did not receive TextMessage in time");
                    }

                    long receivedAt = System.currentTimeMillis();

                    System.out.println("Payload: " + received.getText());
                    System.out.println("Same delivery time: "
                            + (received.getJMSDeliveryTime() == earliest));
                    System.out.println("Received no earlier than allowed: "
                            + (receivedAt >= received.getJMSDeliveryTime()));
                }
            }
        };
    }
}
~~~

Step-by-step explanation:

1. Spring Boot injects a `ConnectionFactory` connected to embedded Artemis into `ApplicationRunner`.
2. `JMSContext` and `JMSConsumer` are created once in `try-with-resources` blocks and closed when the runner finishes.
3. Producer calls `setDeliveryDelay(2_000L)`, then sends the `TextMessage`. No `Thread.sleep`.
4. Once synchronous send completes, `outbound.getJMSDeliveryTime()` holds the earliest eligible delivery timestamp.
5. Consumer calls `receive(10_000)`; the broker cannot deliver before delivery time. If nothing arrives within 10 seconds, the example throws an error.
6. The header on the received message **must equal** the header assigned on send.
7. `receivedAt >= JMSDeliveryTime` verifies the timing invariant. The comparison uses the JVM system clock; environments with erratic clock adjustments can skew the observed check even though the JMS broker follows its own rules.

Run from the `delivery-time-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Printed output looks like (ignoring Spring/Artemis startup logs):

~~~text
Earliest: 2026-10-30T03:15:20Z
Payload: ORDER-123
Same delivery time: true
Received no earlier than allowed: true
~~~

**`Earliest` here is only an illustrative value; each run prints a different timestamp.** The two `true` lines are the expected outcome with a healthy broker and no backward clock jumps. Do not write a test asserting elapsed time equals exactly 2,000 ms: the broker may deliver later.

### 7.4. Further Experiments

- Change `setDeliveryDelay(2_000L)` to `setDeliveryDelay(0L)` to see the message become eligible immediately on send.
- Change to an 8-second delay while calling `receive(1_000L)`: an early receive before eligibility returns `null`; to actually receive afterward, call `receive(12_000L)` on the same consumer.
- Keep the 8-second delay and call `receiveNoWait()` right after send: it normally returns `null`; that is just an instantaneous snapshot. If the send unexpectedly took over 8 seconds, the message could already be eligible when polled.
- Increase backlog with many messages and slow consumer processing: eligibility timestamp does not guarantee immediate completion.

## 8. Spring JmsTemplate and @JmsListener

In Spring Framework, `JmsTemplate` manages most JMS sending and exposes `setDeliveryDelay(long)`.

### 8.1. Delayed Message Sending Bean

Create `DelayedJmsConfig.java`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DelayedJmsConfig {

    @Bean("delayedOrdersTemplate")
    public JmsTemplate delayedOrdersTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDeliveryDelay(5_000L);
        return template;
    }
}
~~~

Then invoke the template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DelayedOrderPublisher {

    private final JmsTemplate delayed;

    public DelayedOrderPublisher(
            @Qualifier("delayedOrdersTemplate") JmsTemplate delayed) {
        this.delayed = delayed;
    }

    public void publish(String orderId) {
        delayed.convertAndSend("orders.delayed", orderId);
    }
}
~~~

These are **two separate classes** inside a Spring application that already has a JMS `ConnectionFactory`; declare an appropriate `package` when adding them to a project. Spring applies the delivery delay on the underlying producer used for sends through that template.

**Defaults to remember:**

- A standard JMS producer has delivery delay **0L**.
- `JmsTemplate` defaults its property to `deliveryDelay = -1`, meaning **do not pass an override** to the broker. `-1` is Spring's internal sentinel, **not a valid negative delay sent to the JMS producer**.
- `JmsTemplate.setExplicitQosEnabled(true)` is the switch that applies template-configured delivery mode, priority, and TTL; delivery delay has its own setter and **does not depend on enabling that switch**.

`JmsTemplate` is normally shared across threads once configured. **Do not mutate `setDeliveryDelay` repeatedly right before each `convertAndSend` on a shared bean**: concurrent requests can accidentally pick up each other's delay values. If you need multiple delay intervals, configure multiple templates per policy or use a dedicated producer scoped solely to the send operation.

### 8.2. Spring Consumers Do Not Have to Watch the Clock

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class DelayedOrderListener {

    @JmsListener(destination = "orders.delayed")
    public void onMessage(String orderId) {
        System.out.println("Order ready: " + orderId);
    }
}
~~~

This listener requires `@JmsListener` infrastructure enabled and an active `ConnectionFactory`. The Spring container creates the consumer and the broker delivers messages once eligible; the listener **does not compare clocks or `sleep`** to enforce the initial delay.

The examples in section 8 show how to integrate into an existing Spring application; the full standalone runnable example is in section 7. When processing critical business work, configure transactions/acknowledgment, idempotency, retries, and DLQs separately.

## 9. Delivery Delay and Time-to-Live (TTL)

**Delivery delay** answers "at earliest **when may it be delivered**?". **TTL** answers "**when does the message expire**?". Both are measured from send time, not from when a consumer starts listening.

| Sent at | Delay | TTL | Meaning |
| --- | --- | --- | --- |
| 10:00 | 5 minutes | 30 minutes | Eligible for delivery from 10:05; expires at 10:30. |
| 10:00 | 5 minutes | 2 minutes | Expires at 10:02 before becoming eligible at 10:05; consumers should never receive expired messages. |
| 10:00 | 0 | 0 | Eligible immediately; no JMS TTL expiration. |
| 10:00 | 10 minutes | 0 | Eligible for delivery from 10:10; no JMS TTL expiration. |

Configuring directly via `MessageProducer`:

~~~java
// Fragment with MessageProducer producer and Message message already created.
producer.setDeliveryDelay(5 * 60_000L);
producer.setTimeToLive(30 * 60_000L);
producer.send(message);
~~~

Configuring via `JMSProducer`:

~~~java
// Fragment with JMSProducer producer and Queue queue already created.
producer.setDeliveryDelay(5 * 60_000L)
        .setTimeToLive(30 * 60_000L)
        .send(queue, "ORDER-456");
~~~

`setTimeToLive(0L)` means **does not expire by TTL**, not "expires immediately". The provider computes `JMSExpiration` on send; expired messages are not delivered further. Some brokers have an **expiry address/expiry queue** or discard expired messages per rule; configure them clearly so expiration is not mistaken for successful processing.

**Proper design:** TTL must be long enough to cover **delay + potential broker/consumer wait time + slow-processing buffer**. If TTL is shorter than delay, the message expires before ever getting a chance to be delivered. If TTL equals delay, the message can expire right at eligibility time, making it unreliable for required work.

## 10. Transactions: Measured from Send, Not from Commit

The Jakarta Messaging specification is explicit: for sends inside a transaction, **delivery time is calculated from when the client sends the message**, not from when the JMS transaction commits.

Example A:

~~~text
10:00  send M1, delay 5 minutes => JMSDeliveryTime = 10:05
10:02  commit transaction
10:05  M1 becomes eligible for delivery
~~~

Example B:

~~~text
10:00  send M2, delay 5 minutes => JMSDeliveryTime = 10:05
10:05  eligible time has already passed
10:07  transaction finally commits
10:07+ M2 can be delivered; no need to wait another 5 minutes
~~~

Think of actual earliest visibility as **after both conditions are satisfied**: the message has committed and `JMSDeliveryTime` has been reached. If the transaction rolls back, messages sent inside it are never published regardless of what header timestamp was initially calculated.

Fragment inside a method with `jakarta.jms.Connection connection` and `jakarta.jms.Queue queue`:

~~~java
jakarta.jms.Session session = connection.createSession(
        true, jakarta.jms.Session.SESSION_TRANSACTED);

try {
    try (jakarta.jms.MessageProducer producer =
                 session.createProducer(queue)) {

        producer.setDeliveryDelay(60_000L);
        jakarta.jms.TextMessage message =
                session.createTextMessage("ORDER-789");

        producer.send(message);

        long eligibleAt = message.getJMSDeliveryTime();
        session.commit();

        System.out.println("Eligible: " +
                java.time.Instant.ofEpochMilli(eligibleAt));
    }
} finally {
    session.close();
}
~~~

**Note:** a local JMS transaction differs from a DB transaction. Annotating `@Transactional` with a JDBC transaction manager does not automatically enlist a JMS send. If the requirement is "delay exactly 5 minutes after DB commit", use an explicit coordination pattern (such as transactional outbox publishing after commit, or a deadline-managing scheduler) instead of assuming delivery delay handles it automatically.

## 11. Queue, Topic, Ordering, and Consumers

### 11.1. With a Queue

A message sent to a queue can be persisted by the broker immediately yet only becomes **eligible for delivery** at `JMSDeliveryTime`. With competing consumers, the broker picks an eligible consumer at delivery time; delay **does not pin a specific consumer**.

M1 sent before M2 can be delivered later:

~~~text
10:00:00  send M1, delay 60 seconds => eligible 10:01:00
10:00:01  send M2, delay 0        => eligible 10:00:01

M2 may be delivered before M1.
~~~

Therefore, do not assume a delayed queue preserves completion order matching producer send order. Priority, multiple sessions/consumers, transactions, and redeliveries affect order further.

### 11.2. With a Topic

For a message published to a Topic with delivery delay, the subscription **must exist at publish/send time** to be eligible for that message; creating a subscriber **after send yet before delivery time** does not mean it receives the already-published message.

~~~text
10:00  E1 published to topic, delay 5 minutes
10:02  subscriber B subscribes
10:05  E1 reaches eligible delivery time

Subscriber B does not automatically receive E1 merely because it existed before 10:05.
~~~

Durable/shared subscriptions, selectors, and connection state govern how the broker stores and delivers messages, yet delivery delay **does not turn a Topic into a historical replay log**.

## 12. Retries and Redelivery Delay Are Different Matters

`JMSDeliveryTime` is computed for the **initial send**. If a consumer receives a message and then rolls back or disconnects, the message may be redelivered; that **does not mean** JMS automatically recomputes `JMSDeliveryTime = retry time + initial delay`.

A broker may be configured with **redelivery delay/backoff**, e.g. retrying after 30 seconds, 1 minute, 5 minutes. That is a **post-failure retry policy**, independent of producer delivery delay. The `JMSDeliveryTime` header still reflects the provider-assigned timestamp from send; do not use that header as a retry schedule.

Example timeline:

~~~text
10:00  producer sends M, delay 2 minutes
10:02  JMSDeliveryTime arrives; consumer receives M
10:03  consumer processing fails => rollback
10:05  broker redelivers per 2-minute retry policy
~~~

`JMSRedelivered` and, if supported by the provider, `JMSXDeliveryCount` help observe redeliveries; they **do not replace** an idempotent consumer keyed by business `eventId`. Delivery delay does not guarantee exactly-once processing.

## 13. Scheduling by Absolute Timestamp

JMS APIs accept a **relative delay**, not a business `Instant` directly. To send a message "not before 20:00 tomorrow", the application calculates remaining milliseconds:

~~~java
// Fragment: with java.time.Instant target,
// jakarta.jms.JMSProducer producer, and Queue queue.
long delayMillis = Math.max(
        0L,
        target.toEpochMilli() - System.currentTimeMillis());

producer.setDeliveryDelay(delayMillis).send(queue, "REMINDER-123");
~~~

Points to understand:

1. `Math.max(0, ...)` ensures no negative delay is passed; if the deadline has already passed, the message becomes immediately eligible with delay 0.
2. Computing the delay and executing the send **do not happen at the exact same instant**; application latency sits between them, so `JMSDeliveryTime` may drift slightly from the business target.
3. Broker/producer/consumer clocks must be properly synchronized, especially when calculating deadlines across multiple machines.
4. For multi-day schedules requiring cancellation/modification and auditing, usually store `scheduledAt` and state in a DB/scheduler. Standard JMS **provides no generic API to modify an in-flight delayed message by ID**.
5. If a business deadline changes, you need a schedule-update, versioning, and idempotency strategy rather than assuming `JMSDeliveryTime` on an already-sent message can be edited.

**Distinguish broker timing eligibility from business action completion:** a message delivered at 20:00+ does not prove an email/payment/DB update succeeded. The task can start late, retry, or fail.

## 14. Observability and Testing

### 14.1. Information Worth Logging

For practical diagnostics, log `eventId`/business job ID, `JMSMessageID`, queue/topic, `JMSTimestamp`, `JMSDeliveryTime`, `JMSExpiration`, `receivedAt`, transaction status, configured delay, redelivery count, and processing duration.

**Late delivery** can be estimated by:

~~~text
lateByMillis = receivedAtEpochMillis - JMSDeliveryTime
~~~

If the result is negative, investigate **clock skew/system clocks** or timestamp logging bugs before concluding the JMS provider delivered early. To measure **elapsed durations** on the same JVM, prefer a monotonic clock (`System.nanoTime()` or a metrics library). To compare **absolute timestamps**, use Unix epoch millis with synchronized host clocks.

Do not log sensitive payloads merely to debug scheduling.

### 14.2. Meaningful Integration Tests

An integration test against a real broker should:

1. Send a message with a delay large enough to observe (e.g. 2–3 seconds).
2. Read `JMSDeliveryTime` **after send**, verifying it sits ahead of send time by the configured offset.
3. While the clock is still **before** the timestamp, ensure the consumer does not receive the message; avoid flaky assertions based on `Thread.sleep(100)`.
4. Wait past the timestamp with generous timeout headroom for broker processing, verifying payload and unchanged `JMSDeliveryTime` header.
5. Separately test TTL shorter than delay: confirm the message expires before becoming eligible for delivery.
6. For transacted sends, confirm the message is not delivered before commit, even after delivery time has passed.

Never assert that the broker invokes the consumer at an exact millisecond. That is not a Jakarta Messaging guarantee.

### 14.3. Diagnostic Table

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `JMSDeliveryTime` near `JMSTimestamp` despite expected delay | Producer/template unconfigured or overridden by broker. | Print header after send; check producer and broker config. |
| Message arrives "earlier" than business deadline | Wrong units, treating local time as UTC, wrong producer/template. | Convert all times to epoch millis; compare `scheduledAt` and `JMSDeliveryTime`. |
| Consumer receives much later than header | Broker backlog, listener not running, selector, slow consumer, late transaction commit. | Check queue depth, consumer count, transactions, and broker metrics. |
| `receive(1000)` returns `null` | Message not yet eligible, uncommitted, already expired, or no matching message. | Check delay, TTL, queue/selector, and listener status. |
| Message never processed | TTL shorter than delay, expiry policy, topic subscription absent at send time. | Inspect `JMSExpiration`, expiry/DLQ metrics, subscription rules. |
| Retries arrive slower than expected | Broker has its own redelivery delay/backoff. | Check retry policy separately from send delivery delay. |
| Per-message delay randomly wrong | Shared `JmsTemplate` mutated dynamically across threads. | Configure fixed templates per policy; never mutate setters during concurrent sends. |
| M1 sent first yet M2 processed first | M1 delayed, different priorities/transactions, or multiple consumers. | Review business ordering constraints; never assume global FIFO. |

## 15. Common Misconceptions

**"Setting a 5-minute delay makes the producer wait 5 minutes before sending?"** No. The producer sends immediately; the broker defers delivery to consumers.

**"`JMSDeliveryTime` is the exact time `@JmsListener` is guaranteed to run?"** No. It is only the **earliest eligible time**; the consumer may receive it later.

**"Can I use `message.setJMSDeliveryTime(...)`?"** Not for scheduling. Clients must use `setDeliveryDelay` on the producer.

**"If I want zero wait, should I set delay = -1?"** For a JMS producer, the default is **0**. `-1` is **`JmsTemplate`**'s sentinel meaning do not override the option, not a negative JMS delivery delay.

**"TTL starts after the delay ends?"** No. Both TTL and delay start from send time, so `JMSExpiration < JMSDeliveryTime` can happen.

**"Committing after 5 minutes starts another 5-minute delay?"** No. In transacted sends, delay still starts from send; however, uncommitted messages are not delivered.

**"I called `receiveNoWait()` and got `null`, so the message is lost?"** No. At that polling instant no message was available to that consumer, possibly because the message is still waiting for its delivery time.

**"With a delayed message, any subscriber created before delivery time receives it?"** No. On a Topic, the subscription must meet existence requirements at **publish/send** time.

## 16. Practice Questions and Answers

1. Producer sends at 08:00, delivery delay 10 minutes, TTL 30 minutes. Earliest delivery time and expiration time? **08:10 and 08:30**.
2. Sent at 08:00, delay 10 minutes, TTL 3 minutes. Can it be delivered at 08:10? **No; the message already expired at 08:03**.
3. Sent in a transaction at 08:00 with a 5-minute delay, committed at 08:08. When is the earliest it can be delivered? **After commit at 08:08**, since the 08:05 header timestamp already passed.
4. Producer calls `message.setJMSDeliveryTime(now + 60000)` and sends. Must the broker wait one minute? **No; that setter is for the provider**.
5. Message is delivered at 08:12 with `JMSDeliveryTime = 08:10`. Does this violate the spec? **No; brokers may deliver later**.
6. What is the JMS default `deliveryDelay`? **0L**. What is `JmsTemplate`'s default `deliveryDelay`? **-1**, meaning do not override.
7. Producer sends M1 before M2, where M1 has a 30-second delay and M2 has delay 0. Can M2 be received before M1? **Yes**.
8. Broker retry configuration waits 2 minutes after rollback; does `JMSDeliveryTime` get 2 minutes added to it? **No; retry delay is a separate rule**.
9. If you need cancellable/editable schedules spanning days, is JMS delivery delay alone enough? **Usually no; you need business schedule management and cancellation/edit mechanisms**.
10. To get headers after an async send, is reading immediately after calling `send(..., CompletionListener)` reliable? **No; wait for the successful completion callback**.

## 17. Authoritative Sources

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): section 3.4.13 on `JMSDeliveryTime`, section 7.9 on delivery delay, and TTL/transaction rules.
- [Jakarta Messaging Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): `getJMSDeliveryTime()`, `setJMSDeliveryTime()`, `getJMSExpiration()`.
- [Jakarta Messaging MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): `setDeliveryDelay(long)`, `setTimeToLive(long)`.
- [Jakarta Messaging JMSProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer): simplified API producer.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setDeliveryDelay` setter.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): embedded broker and connections.
- [Apache ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages): broker-specific scheduled messages mechanism.

**Long-term takeaway:** `JMSDeliveryTime = sendTime + deliveryDelay` is the **earliest time the JMS provider is allowed to deliver a message**, neither an expiration time nor an exact processing time. Set delay on the producer; the provider writes the header; transactions, TTL, and broker/consumer state determine when the message is actually delivered.
