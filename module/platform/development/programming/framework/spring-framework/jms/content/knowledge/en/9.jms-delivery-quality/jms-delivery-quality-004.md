# Time-to-Live (TTL) and Messages Expiring Before Delivery in Spring JMS

## 1. The Problem: Is an Expired Message Still Valuable?

Suppose an e-commerce application puts tasks onto a queue for asynchronous consumer processing:

- A newly created order needs a confirmation email; if backlog grows, a few minutes of delay may still be acceptable.
- A notification saying "promotional price valid for 30 seconds" should not be delivered an hour later.
- A cache refresh task is only useful for a few seconds.
- A payment command, by contrast, **must not be silently discarded** just because the queue is slow; it requires explicit business rules and reconciliation.

In Jakarta Messaging (JMS), **time-to-live (TTL)** is the maximum duration a message is considered valid for the provider to deliver to a consumer. Once the expiration timestamp passes, the provider **should discard** undelivered messages, and consumers normally should not receive them anymore. However, the specification does not absolutely guarantee that a client will never see an expired message; applications with strict requirements must still verify business deadlines themselves.

TTL is a **quality of service (QoS) delivery policy**. It is set on the **producer** side at send time, and is neither the consumer's receive timeout nor the maximum execution time for a job already delivered.

### 1.1. Distinguishing the Timestamps

~~~text
t = 0 ms     Producer sends "refresh cache", TTL = 5 000 ms
                 |
                 +--> JMS provider computes JMSExpiration ~= sendTime + 5 000
                 |
t = 1 000    Message is still waiting in queue        (still valid)
t = 4 000    Consumer receives it                     (valid)
t = 5 000    JMS delivery deadline
t = 8 000    If the message is still undelivered by now,
             the provider should discard it rather than deliver anew.
~~~

If the consumer receives at t=4 seconds and processes until t=9 seconds, TTL **does not abort the callback** at t=5 seconds. To stop a task past a business deadline, the consumer needs its own logic: checking timestamps/deadlines before applying side effects, execution time limits, transactions, and controlled cancellation mechanisms.

### 1.2. Why TTL Matters

TTL prevents queues from accumulating stale messages, lowers latency for fresh messages, and bounds certain classes of backlogged work. However, setting TTL too short can make **messages vanish without ever being processed by a consumer**, especially during deployments, network drops, broker overload, or consumer downtime. Therefore, you must weigh data semantics, SLAs, backlog, and recovery capabilities.

## 2. Exact Definition: TTL and JMSExpiration

Jakarta Messaging 3.1 specifies **TTL in milliseconds**. The default on `MessageProducer` is **0**, meaning **does not expire by TTL**. For a positive TTL, the JMS provider computes the absolute expiration timestamp:

\[
\text{JMSExpiration} = \text{send time} + \text{timeToLive}
\]

Here "send time" used in the calculation is when **the client sends the message**, not when a transaction commits. `JMSExpiration` is milliseconds since the Unix epoch (1970-01-01T00:00:00Z).

Hypothetical example:

| Property | Value | Meaning |
| --- | --- | --- |
| Send time | 2026-10-30T08:00:00Z | Sample timestamp |
| TTL | 30,000 ms | 30 seconds |
| JMSExpiration | 2026-10-30T08:00:30Z | Absolute expiration timestamp |
| Consumer available at 08:01:00Z | 30 seconds late | Undelivered message is generally no longer valid to deliver |

These timestamps only illustrate the calculation, not live environment clock times. If sending is delayed by a transaction or transport layer, TTL has already started counting from the client send timestamp.

**Three important notes:**

1. **TTL=0 does not mean immediate expiration.** In JMS, 0 means "does not expire." In some broker-specific expiry configurations, 0 may mean something else; do not project that meaning onto JMS `MessageProducer`.
2. **Do not call `message.setJMSExpiration(...)` yourself to set TTL.** That setter is reserved for the provider to populate the header upon sending. Application producers must use `MessageProducer.setTimeToLive(...)`, `send(..., timeToLive)`, or Spring's corresponding send API.
3. **`JMSExpiration` is distinct from `JMSTimestamp`.** `JMSTimestamp` records when the message was handed off for sending; `JMSExpiration` is the deadline. When a producer hints to disable timestamps, `JMSTimestamp` may be 0; do not use it as a substitute for the `JMSExpiration` contract.

### 2.1. When Is the Header Value Populated?

Before send, application code can create a `TextMessage`, while `JMSExpiration` is not yet set by the provider. Once send completes, the provider populates `JMSExpiration` on the sent message; when a consumer receives it, the header carries that value.

~~~java
TextMessage message =
        session.createTextMessage("refresh-cache");

// Do not call setJMSExpiration(...) from application code.
producer.send(
        message,
        DeliveryMode.PERSISTENT,
        4,
        5_000L);

long expiresAtEpochMs = message.getJMSExpiration();
System.out.println(expiresAtEpochMs > 0);
~~~

This is a **snippet** requiring an existing `Session`/producer, not a standalone program. When sent successfully with a 5-second TTL, the final condition is normally true; the exact epoch value depends on runtime clock so it is not fixed in stdout.

With TTL=0, `JMSExpiration` equals 0, meaning there is no TTL-based expiration timestamp.

### 2.2. Negative TTL and Overflow Values

TTL must be a valid **non-negative** duration; avoid passing negative numbers and do not assume all JMS providers handle them identically. When converting config from `Duration` to milliseconds, verify the value fits in `long`, has no unit mismatch, and is operationally meaningful. Do not arbitrarily set `Long.MAX_VALUE` to represent infinity; use `TTL=0` if the contract allows no expiration.

## 3. Lifecycle: Valid Messages, Expired Messages, and Delivery Time

~~~mermaid
stateDiagram-v2
    [*] --> Created: Create message
    Created --> Sent: producer.send
    Sent --> Waiting: Broker stores/queues
    Waiting --> Delivered: Consumer receives before expiry
    Waiting --> Expired: Past JMSExpiration
    Expired --> Discarded: Provider discards
    Expired --> ExpiryAddress: Broker configured expiry address
    Delivered --> Processed: App processes/acks or commits
    Delivered --> Redelivered: Processing error and broker redelivers if eligible
    Redelivered --> Delivered: Redelivered per policy
~~~

This diagram illustrates the common flow, not every internal state of every broker. The transition out of `Expired` may occur during periodic broker scans, before dispatch, or when a consumer polls; therefore, do not predict when queue depth drops strictly by wall clock.

### 3.1. If a Message Expires in the Queue

Basic scenario:

1. Producer sends a message at t0 with a 2-second TTL.
2. Broker accepts the message while the consumer is offline.
3. After 5 seconds, the consumer starts up.
4. The provider is responsible for honoring expiration and **should discard the expired message**; a normal `receive(timeout)` call will no longer fetch the old message.
5. If no other messages exist, `receive(timeout)` returns `null` when the wait expires.

Do not document this as "JMS 100% guarantees an expired message is never delivered": the specification says clients **should not** receive expired messages, yet **does not guarantee it absolutely**. If business impact is high, check deadlines in the consumer and design idempotent processing.

### 3.2. If a Message Was Delivered Before Expiring

Suppose TTL is 5 seconds, the consumer receives at second 4, and needs 8 seconds to process:

~~~text
t=0s             t=4s                 t=5s             t=12s
send              receive              JMSExpiry         processing completes
 |------------------|--------------------|-------------------|
                    ^ consumer already received before expiry
~~~

TTL is not an `onMessage` method timeout, does not kill a Java thread, and does not automatically roll back an in-flight transaction. If business rules forbid execution past the deadline, the consumer must enforce a deadline check before side effects or at suitable checkpoints, while still accounting for race conditions and transactions.

### 3.3. Does Retry/Redelivery Reset TTL?

**No, in standard JMS terms.** For the same un-acked/uncommitted message, the broker may redeliver due to rollback or consumer failure; the `JMSExpiration` deadline was stamped on the original send and does not reset just because another delivery occurs.

Conversely, if the application receives a message and **creates a new message** to re-send, that is a new send; the new message's TTL is calculated from the new send time unless the application carries a business deadline and applies a different policy.

Therefore, republish-style retries can unintentionally extend work past its deadline. If a business deadline must be preserved end-to-end, embed an absolute deadline in the payload/metadata and compute remaining TTL when republishing:

~~~text
remainingMs = max(0, deadlineEpochMillis - currentTimeMillis)
~~~

When `remainingMs <= 0`, **do not re-send**: setting JMS `TTL=0` would turn the message into non-expiring, the exact opposite of the goal.

## 4. Plain JMS API: Setting TTL on the Producer or Per Send

### 4.1. Setting Default TTL on MessageProducer

~~~java
MessageProducer producer = session.createProducer(queue);
producer.setTimeToLive(5_000L);  // 5 seconds, applied to subsequent sends.
producer.send(session.createTextMessage("update-1"));
producer.send(session.createTextMessage("update-2"));
~~~

This is a snippet: `Queue` and `Session` must already exist. When QoS is not specified in `send(...)`, the producer uses its current settings. The API default TTL on `MessageProducer` is 0: messages do not expire. Some providers allow administrative defaults; verify against the runtime environment.

Note: do not call `setTimeToLive(...)` on `Message`. QoS is controlled on the producer/send call, while `JMSExpiration` is written onto `Message` by the provider after sending.

### 4.2. Overriding TTL for a Single Send

~~~java
producer.send(
        session.createTextMessage("flash-sale-alert"),
        DeliveryMode.PERSISTENT,
        6,
        2_000L); // 2-second TTL

producer.send(
        session.createTextMessage("audit-event"),
        DeliveryMode.PERSISTENT,
        4,
        0L); // Does not auto-expire by JMS TTL
~~~

The `send(message, deliveryMode, priority, timeToLive)` overload lets each message have its own TTL. `DeliveryMode` and priority are orthogonal to TTL: a `PERSISTENT` message **still expires** if TTL is positive; a `NON_PERSISTENT` message with `TTL=0` **does not magically become persistent**.

When sharing producers across threads, adhere to the rule that a JMS `Session` must not be used concurrently without synchronization. Manage `Session`/`Producer` within an appropriate context and avoid mutating global TTL from competing threads.

### 4.3. Simplified API (JMSContext/JMSProducer)

In Jakarta Messaging 3.x, the simplified API provides:

~~~java
try (JMSContext context = factory.createContext()) {
    JMSProducer producer = context.createProducer()
            .setTimeToLive(5_000L);
    producer.send(destination, "hello");
}
~~~

This is a snippet; `factory` and `destination` are already provided. `JMSProducer.setTimeToLive(long)` returns `JMSProducer` for method chaining, unlike `MessageProducer.setTimeToLive(long)` in the classic API which returns `void`. Do not confuse the `jakarta.jms.*` namespace with `javax.jms.*` in Spring Boot 3/Spring Framework 6 applications.

## 5. Spring JmsTemplate: Tying TTL to Quality of Service

### 5.1. Why setTimeToLive Alone Might Not Suffice

`JmsTemplate` uses `MessageProducer`'s QoS mechanism. According to Spring documentation, when **explicit QoS is not enabled**, regular send calls can use the provider's default values instead of the values configured on `JmsTemplate`.

To instruct Spring to send with a specific TTL:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setTimeToLive(5_000L);
template.setExplicitQosEnabled(true);

template.convertAndSend("orders.notifications", "expires-in-5s");
~~~

This is a snippet inside an application that already has a `ConnectionFactory`. Calling **`setExplicitQosEnabled(true)`** is crucial to ensure the template passes `deliveryMode`, `priority`, and `timeToLive` into the QoS `send` overload instead of falling back to provider defaults.

Related settings:

| JmsTemplate API | Purpose |
| --- | --- |
| setTimeToLive(long) | TTL of sent messages, in milliseconds. |
| setExplicitQosEnabled(boolean) | Enables applying the directly configured QoS settings on send. |
| setDeliveryMode(int) | PERSISTENT or NON_PERSISTENT. |
| setPriority(int) | Priority 0–9; JMS default is 4. |
| setDeliveryDelay(long) | Delays the earliest time a message can be delivered; **distinct from TTL**. |
| setReceiveTimeout(long) | Wait timeout for a receive call; **does not expire messages**. |

When using `JmsTemplate` as a Spring bean shared across threads, configure its properties **before first use**. `JmsTemplate` is thread-safe once configured; do not continuously mutate TTL on a shared bean per request due to race conditions.

### 5.2. Explicit Configuration Bean

~~~java
@Configuration
class JmsQosConfig {

    @Bean
    JmsTemplate notificationTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(30_000L);
        return template;
    }
}
~~~

This is a configuration snippet requiring imports for `jakarta.jms.ConnectionFactory`, `DeliveryMode`, `org.springframework.context.annotation.Bean`/`Configuration`, and `org.springframework.jms.core.JmsTemplate`. When an application has multiple TTL policies, it is usually clearer to use **multiple statically configured templates/producers** by message class, rather than mutating TTL on one bean before every send.

### 5.3. Configuration via Spring Boot Properties

Spring Boot 3.3 supports configuring the template through properties:

~~~properties
spring.jms.template.time-to-live=30s
spring.jms.template.receive-timeout=2s
~~~

In Boot's auto-configuration, setting `time-to-live` (or `delivery-mode`/`priority`) **enables explicit QoS** via Spring Boot's mechanism. If you define a completely custom `JmsTemplate` bean and bypass Boot auto-configuration, these properties **will not necessarily be applied**; in that case explicitly call `setTimeToLive` and `setExplicitQosEnabled` as in Section 5.1.

To make it explicit:

~~~properties
spring.jms.template.qos-enabled=true
spring.jms.template.time-to-live=30s
~~~

Note that Spring Boot properties use duration syntax with suffixes like `30s`, `500ms`, etc., whereas `setTimeToLive(long)` takes **numeric milliseconds**. Do not confuse 30 with 30 seconds: `setTimeToLive(30L)` means 30 **milli**seconds.

### 5.4. One Message Needing a Different TTL from the Common Policy

`JmsTemplate.convertAndSend(...)` with a `MessagePostProcessor` is suitable for attaching business properties/headers, but a `MessagePostProcessor` cannot call `setJMSExpiration` to change TTL in a standard way.

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        "order-created",
        message -> {
            message.setJMSType("order.created.v1");
            message.setStringProperty("TenantId", "acme");
            return message;
        });
~~~

This is a snippet: it alters metadata, **not per-message TTL**. For per-message TTL, consider:

1. Separate `JmsTemplate` beans with distinct TTL policies.
2. Using **`ProducerCallback`** and calling `producer.send(message, deliveryMode, priority, ttl)` directly.
3. Creating an application-level send abstraction injected with TTL config to keep policies consistent and testable.

~~~java
jmsTemplate.execute("orders.events", (session, producer) -> {
    TextMessage message =
            session.createTextMessage("short-lived");
    producer.send(
            message,
            DeliveryMode.PERSISTENT,
            4,
            750L);
    return null;
});
~~~

This is a snippet inside a Spring bean; requires importing `TextMessage` and `DeliveryMode`. When calling `MessageProducer.send(...)` directly inside the callback, the QoS arguments in that overload govern that specific send; do not assume `JmsTemplate` automatically overrides the TTL of sends issued inside the callback.

## 6. Expiration Timeline Example: TTL, Receive Timeout, and Queue Backlog

Suppose a producer sends to queue Q at 10:00:00 with a 3-second TTL, and the consumer starts later.

| Time | Event | Expected Outcome |
| --- | --- | --- |
| 10:00:00 | Send m1, TTL=3s | Provider computes JMSExpiration 10:00:03 |
| 10:00:01 | Consumer not connected yet | m1 is still valid |
| 10:00:03 | m1 expires undelivered | Provider should discard/expire per policy |
| 10:00:06 | Consumer calls receive(2s) | Usually returns null if no other messages exist |
| 10:00:08 | receive timeout elapses | Thread stops waiting; **unrelated to m1's TTL** |

**Receive timeout does not make messages disappear.** If a consumer calls `receive(timeout=1000ms)` and gets nothing, that is the caller's wait limit; live messages can still wait for a later consumer. TTL is set at send time.

### 6.1. Do Not Confuse TTL with Infinite Storage Duration

A message with `TTL=0` means JMS does not request TTL-based expiration, but this **does not guarantee it exists forever**. Factors that can still remove a message:

- `DeliveryMode.NON_PERSISTENT` and a provider/broker restart.
- Queue deletion, capacity limits, eviction/retention policies, or administrative purges.
- Another consumer already received and acknowledged/committed it.
- Data loss or failure in the broker or underlying infrastructure.
- Server-side expiry/retention policies imposed by broker administration.

TTL is only **one factor** in a message's lifecycle, not a permanent storage agreement.

## 7. Runnable Project: Spring Boot 3.3, Java 17, Artemis

This hands-on example shows two message groups sent while no consumer is reading yet:

- Message A has a short TTL: 250ms, and will expire after the program waits 1.2 seconds.
- Message B has a long TTL: 60 seconds, and is still received normally.

To avoid interference from previous runs' backlogs, each run creates **two unique queue names** using a UUID. On the demo Artemis broker with auto-create enabled, queues do not need pre-provisioning. Stdout lines are designed not to depend on the UUID or absolute expiration timestamps.

### 7.1. Preparing the Broker

Requires JDK 17+, Maven, Docker, and port 61616 available. Start an Apache ActiveMQ Artemis container:

~~~bash
docker run --detach --rm --name ttl-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to finish starting; check `docker logs ttl-demo-broker` if connection fails. The demo image uses default username/password `artemis/artemis`; **never use demo credentials in production**. If your broker disallows auto-creating queues, create the destinations with appropriate permissions rather than trying to work around it by increasing TTL.

Structure:

~~~text
jms-ttl-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmsttl/TtlDemoApplication.java
    └── resources/application.properties
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-ttl-demo</artifactId>
    <version>1.0.0</version>
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

Spring Boot 3.x + Spring Framework 6.x uses **`jakarta.jms`**, not the `javax.jms` of older versions. The starter dependency provides Spring JMS and the Artemis client; application code does not manually open `Connection` or `Session` because `JmsTemplate` handles that.

### 7.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

The application is a `CommandLineRunner` and opens no HTTP server. TTL settings are applied on local `JmsTemplate` instances inside the runner to show the exact QoS API calls. Setting `spring.jms.template.time-to-live` is not needed for this demo.

### 7.4. TtlDemoApplication.java

~~~java
package example.jmsttl;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class TtlDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TtlDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ConnectionFactory connectionFactory) {
        return args -> {
            String runId = UUID.randomUUID().toString().replace("-", "");
            String shortQueue = "demo.ttl.short." + runId;
            String longQueue = "demo.ttl.long." + runId;

            JmsTemplate shortLived = new JmsTemplate(connectionFactory);
            shortLived.setExplicitQosEnabled(true);
            shortLived.setDeliveryMode(DeliveryMode.PERSISTENT);
            shortLived.setPriority(4);
            shortLived.setTimeToLive(250L);

            JmsTemplate longLived = new JmsTemplate(connectionFactory);
            longLived.setExplicitQosEnabled(true);
            longLived.setDeliveryMode(DeliveryMode.PERSISTENT);
            longLived.setPriority(4);
            longLived.setTimeToLive(60_000L);

            JmsTemplate reader = new JmsTemplate(connectionFactory);
            reader.setReceiveTimeout(1_000L);

            shortLived.convertAndSend(shortQueue, "too-late");
            longLived.convertAndSend(longQueue, "still-valid");

            // Consumer starts receiving only after the short TTL has elapsed.
            Thread.sleep(1_200L);

            Object expired = reader.receiveAndConvert(shortQueue);
            Message fresh = reader.receive(longQueue);

            if (!(fresh instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected unexpired TextMessage");
            }

            System.out.println("expired: " + expired);
            System.out.println("valid: " + text.getText());
            System.out.println(
                    "has-expiration: " + (text.getJMSExpiration() > 0));
        };
    }
}
~~~

Step-by-step explanation:

1. Each run uses two distinct UUID-suffixed queue names, avoiding accidentally reading leftover messages from earlier runs.
2. Both templates enable explicit QoS, so `setTimeToLive(250L)` and `setTimeToLive(60_000L)` take effect on send.
3. Both messages are sent before `reader` starts receiving. If the broker supports auto-created queues, messages wait in the queues.
4. `Thread.sleep(1_200L)` exceeds the 250ms TTL. When `receiveAndConvert(shortQueue)` runs, the expired message has normally been discarded by the broker, returning `null`.
5. The 60-second TTL on the second message lets `reader.receive(longQueue)` return a `TextMessage`; `getJMSExpiration()` has a positive value.
6. `reader.setReceiveTimeout(1_000L)` is the timeout of the **receive operation**, having no effect on the TTL sent by the two prior templates.
7. There are no competing consumers or background listeners in the demo; the test cleanly reflects the relationship between send time and receive start time.

### 7.5. Running the Project and Output

From the `jms-ttl-demo` directory:

~~~bash
mvn spring-boot:run
~~~

When the broker runs normally without major clock/resource anomalies and the second message is delivered within its TTL, the program's stdout is:

~~~text
expired: null
valid: still-valid
has-expiration: true
~~~

Additional Spring Boot/provider logs may appear. The JMS specification does not strictly guarantee every implementation discards expired messages before a caller reads them; this expectation is the **typical path on Artemis with expiry configured**. If `expired` is non-null, check clock sync, whether TTL is actually being applied, broker version, and expiry policy—do not simply assume the Java code is broken.

Stop the demo container:

~~~bash
docker stop ttl-demo-broker
~~~

### 7.6. Experiments After a Successful Run

- Change `shortLived.setTimeToLive(250L)` to `0L`. Without a provider-specific expiry override, `"too-late"` will **not expire by JMS TTL** and can still be received after 1.2 seconds.
- Change `250L` to `10_000L`: the 1.2-second wait has not exceeded TTL, so the message remains valid.
- Change `reader.setReceiveTimeout(1_000L)` to `2_000L`: the receive call duration may change, but **the expiration deadline does not change**.
- Change `shortLived.setExplicitQosEnabled(true)` to `false`: observe whether the configured TTL or provider default is applied. This is a key experiment to understand explicit QoS.
- Create a listener consuming earlier than 250ms and observe that the message can be delivered before expiring; TTL does not block delivery while valid.
- Send with varying `MessageProducer.send(..., ttl)` values and inspect `JMSExpiration` on received messages.

## 8. TTL and Delivery Delay Are Not the Same Concept

JMS 2.0+/Jakarta Messaging supports **delivery delay**: the number of milliseconds a message must wait before its earliest eligible delivery time. The provider computes **`JMSDeliveryTime`** as send time plus delivery delay.

| Property | Meaning | Related Header |
| --- | --- | --- |
| Time-to-live (TTL) | Maximum duration a message is considered valid | JMSExpiration |
| Delivery delay | Minimum wait time before a message may be delivered | JMSDeliveryTime |
| Receive timeout | Maximum time a client thread waits on a receive call | Does not alter expiry headers |
| Transaction timeout | Transaction limit enforced by the transaction manager | Does not directly set JMSExpiration |

Illustration:

~~~text
Send at t=0:
  deliveryDelay = 8 seconds
  TTL           = 5 seconds

  t=0:     message is sent
  t=5:     message expires (JMSExpiration)
  t=8:     earliest time eligible for delivery (JMSDeliveryTime)

  => No valid window exists to deliver before expiration.
~~~

A delay-compliant provider must not deliver before `JMSDeliveryTime`; a message that already expired prior to that timestamp is no longer eligible for delivery. Therefore, never combine `deliveryDelay > TTL` expecting the message to still arrive on time.

### 8.1. Spring Configuration

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDeliveryDelay(2_000L);
template.setTimeToLive(10_000L);
template.setExplicitQosEnabled(true);
~~~

This is a snippet; `ConnectionFactory` comes from outside. In this example, the message has a window from roughly 2 seconds after send to expiration around 10 seconds after send, though actual provider delivery timing also depends on queues, subscribers, broker, and transactions.

When using broker-specific scheduling features, check how they interact with standard JMS delivery delay and TTL; do not assume a scheduler automatically resets TTL.

## 9. TTL and JMS Transactions: Deadline Counts from Send, Not Commit

A subtle case in testing is a transacted `Session`:

~~~text
12:00:00  Transacted session: producer.send(m, TTL = 5s)
12:00:04  Business logic has not committed yet
12:00:07  session.commit()
12:00:07  Message has already expired counting from 12:00:00
~~~

According to the JMS specification, TTL counts from client send time **even inside a transaction**, and does not restart at commit. Thus a message can expire before commit and never be delivered after commit. Do not confuse:

- **commit**: confirming a JMS transaction.
- **JMSExpiration**: message lifetime limit measured from send time.
- **acknowledgement**: confirming receipt of a message.
- **business deadline**: application policy, which may need to span multiple transactions and retries.

For long transactions, choose a TTL with headroom for pre-commit time, backlog, and delivery, or design the producer to send the message at an appropriate stage. Do not pick an overly short TTL just to keep queues slim while ignoring transaction duration.

When Spring uses `JmsTransactionManager` or JTA, commit/rollback boundaries are managed by the transaction manager. `JmsTemplate` participates as configured; `setTimeToLive` neither creates a transaction nor replaces a transaction manager. Notably, DB and JMS operations are not automatically atomic when using separate local transactions.

## 10. TTL, Redelivery, and Consumer Errors

### 10.1. Message Still Valid, Consumer Fails Processing

If a consumer receives a message before expiration and then throws an exception causing transaction rollback or recovery, the provider may redeliver per policy. TTL is not a retry count; delivery attempts can be observed via `JMSXDeliveryCount` on the received message.

~~~java
int count = message.getIntProperty("JMSXDeliveryCount");
long expiration = message.getJMSExpiration();
boolean expiredByClock =
        expiration != 0 && System.currentTimeMillis() >= expiration;
~~~

This is a consumer snippet where `message` is a `jakarta.jms.Message`. The local process clock is advisory only and does not replace provider/business logic. If `expiredByClock=true` and side effects are forbidden past the deadline, the consumer must apply the appropriate policy rather than processing normally.

### 10.2. Received Before Expiry, but Slow Processing

There is no guarantee that TTL will stop side effects from running after expiration. To handle tasks with strict deadlines:

1. Carry an **absolute** business deadline or state version in the body/properties.
2. When starting processing, verify the job is still valid against domain state (e.g., order not cancelled).
3. Right before critical side effects, check validity conditions and use appropriate transactions/optimistic locking.
4. Design idempotency so redeliveries do not trigger duplicate actions.
5. Provide observability/post-check paths if an expired message requires notifying users.

If a payment or refund command must be cancelled, **do not rely on JMS TTL as the sole mechanism**: use an independent state machine and reconciliation workflow.

### 10.3. TTL vs. Retry Limits

Brokers typically have retry policies, redelivery delays, `max-delivery-attempts`, and dead-letter addresses/queues. These are distinct from TTL. A message with a short TTL can expire while waiting for retry; that is different from exceeding retry limits and being routed to a DLQ.

Track separately:

- Messages **expired** due to TTL/deadline.
- Messages **dead-lettered** due to processing failures or exceeding retry policy.
- Messages **acked/committed** after successful processing.
- Messages manually **purged** or deleted due to retention/broker policy.

Lumping all of these into a single "lost" metric makes diagnosis difficult.

## 11. How Do Brokers Handle Expiry? Apache ActiveMQ Artemis Example

Jakarta Messaging defines only TTL and `JMSExpiration` semantics, **not a standard expiry queue or expiration callback**. Brokers enforce their own policies:

- Deleting expired messages from the queue.
- Moving messages to an **expiry address/queue** for inspection if configured.
- Scanning for expiry periodically or checking right before dispatch; queue depth may drop after the deadline passes.
- Applying custom rules such as `expiry-delay`, `max-expiry-delay`, or `no-expiry` depending on administrative config.

### 11.1. Artemis Expiry Address

Apache ActiveMQ Artemis supports assigning an expiry address to collect expired messages. Example `broker.xml` excerpt:

~~~xml
<address-settings>
    <address-setting match="orders.notifications">
        <expiry-address>expiry.notifications</expiry-address>
    </address-setting>
</address-settings>
~~~

This is an illustrative **configuration excerpt**; the expiry address, its bound queue, permissions, routing type, and auto-create settings for expiry resources must match your environment. Do not copy this block verbatim into existing XML without checking the broker's `address-settings` structure.

When no appropriate expiry address is configured, Artemis may **drop** expired messages instead of moving them for retention. Therefore, "TTL expires messages" **does not mean** "messages are guaranteed to move to the DLQ." A DLQ handles errors/undelivered policies; an expiry address handles expiration. The two paths can use different names, retention settings, and permissions.

### 11.2. Expiry Scanning Can Lag

Artemis has an expiry reaper/scan period to check for expired messages. Scan intervals, prefetch/buffering, and provider dispatch behavior can leave a message appearing in queue stats briefly after `JMSExpiration` has elapsed.

Example:

~~~text
t=0s      send TTL 3s, queue depth +1
t=3s      deadline reached
t=6s      broker expiry scan removes message, queue depth -1
~~~

This is an illustrative timeline, not a fixed scan schedule across all Artemis versions. Do not mistake **unreduced queue depth metrics** for "the message is still valid to process." Observe expiry counts or the expiry address to verify.

### 11.3. Clock Synchronization

`JMSExpiration` is an epoch timestamp, and producers and brokers may run on hosts with different clocks. Drift/skew can cause messages to be judged expired too early or too late depending on the system. Operations should sync clocks with NTP/chrony, log timestamps with timezones, and monitor clock drift. Avoid computing business TTLs from timezone-less DateTimes or untrusted clocks.

## 12. Choosing TTL by Workload Type

There is no single "best" TTL for every queue. Derive it from the **business value of the message**:

| Message Type | Selection Guidance | Rationale |
| --- | --- | --- |
| Regenerable cache refresh / invalidation | Short TTL when older updates lose value | Avoids processing stale backlog; relies on source of truth to refresh later. |
| Time-bound marketing notifications | TTL matching campaign window, plus business deadline check | Prevents sending expired offers. |
| Mandatory audit events | TTL=0 or very long per retention rules, with durability and backlog planning | Must not vanish silently when consumers slow down. |
| Non-urgent emails | TTL aligned with practical SLA, with monitoring and expiry handling | Avoids sending very late if business dislikes stale delivery. |
| Payments/orders requiring integrity | Do not use short TTL as a way to cancel business commands | Requires state machine, reconciliation, idempotency, and compensation. |
| Request-reply with timeout | TTL matching useful lifetime of request/reply, yet **distinct** from caller wait time | Request or reply may become pointless once caller gives up. |

A guideline for estimating send TTL against a deadline:

~~~text
TTL large enough for:
  producer/transaction duration
+ broker/queue latency under acceptable load
+ brief consumer downtime if tolerated by business
+ clock/network buffer (if needed)

yet no longer than the period the message remains business-useful.
~~~

If these two requirements conflict, you cannot solve it by "arbitrarily raising TTL"; improve throughput, auto-scale consumers, separate priority queues, or adjust the business workflow.

## 13. Common Mistakes

| Symptom | Cause to Check | Fix |
| --- | --- | --- |
| Calling `setTimeToLive(30)` expires immediately | Assumed 30 meant seconds, actually 30ms | Use `30_000L` or Boot property `30s`. |
| `JmsTemplate` sends but messages never expire | Explicit QoS not enabled; provider uses default TTL | Call `setExplicitQosEnabled(true)` and verify `JMSExpiration`. |
| `TTL=0` keeps messages around unexpectedly | Mistook 0 for "expire immediately" | In JMS `0` = no expiration. |
| `JMSExpiration` is set yet consumer receives nothing | Message expired before delivery; queue backlog/offline consumer | Check deadline, broker metrics, and expiry address. |
| Expired messages missing from DLQ | Expiry and dead-letter are separate policies | Configure an expiry address/queue if retention is needed. |
| Expired already but queue depth does not drop immediately | Broker scans expiry periodically | Check scan period, expiry count, and metric refresh intervals. |
| Message processed past deadline | TTL does not interrupt callback after receive | Check deadlines inside the business handler. |
| Sending via `ProducerCallback` ignores template TTL | Code calls `producer.send` directly | Use the QoS `send` overload on that specific call. |
| Consumer times out yet message still exists | Receive timeout differs from TTL | Distinguish wait timeout from message expiration. |
| Message expires right after transaction commit | TTL counts from send before commit, long transaction | Adjust send timing or TTL accordingly. |
| TTL and `deliveryDelay` conflict | Delay > TTL, leaving no delivery window | Redesign the two policies together. |
| Message redelivered after error past business deadline | Broker retry does not check business state | Enforce idempotency, deadline validation, and state machine. |
| Host clocks out of sync | `JMSExpiration` uses epoch time; broker/client drift | Sync NTP, inspect logs/timezones. |
| Mutating TTL on a shared bean per request | `JmsTemplate` is already used by multiple threads | Use separate templates or `ProducerCallback` for per-send TTL. |

## 14. Expiration Incident Investigation Checklist

1. **Producer:** Where is TTL set? `MessageProducer`, `JMSProducer`, `JmsTemplate`, Boot properties, or broker default?
2. **Units:** Are `250`, `5_000`, `30s` milliseconds or durations? Is conversion to milliseconds safe?
3. **QoS:** Does `JmsTemplate` have `setExplicitQosEnabled(true)`? If using Boot auto-configuration, did a custom bean override the template?
4. **Header:** Inspect `JMSExpiration` after send or on the received message; `0` means no expiration.
5. **Send timestamp:** When did the producer send? Did a transaction commit much later than send?
6. **Delivery delay:** Is `JMSDeliveryTime` later than `JMSExpiration`?
7. **Broker:** Is an expiry address configured, are expired messages dropped or moved, and what is the scan period?
8. **Consumer:** Is the listener started, queue/topic correct, selector matching, and receive timeout/acknowledgement sensible?
9. **Redelivery:** Did rollbacks/recoveries extend wait time or did republishing a new message reset TTL?
10. **Clocks:** Are producer, broker, and consumer clocks synchronized?
11. **Business:** How should an expired task be recovered or recorded; are there audits/metrics and a compensating flow?

Diagnose layer by layer instead of staring solely at a `null` receive result: `null` can mean an empty queue, a non-matching selector, an unstarted consumer, an expired message, or too short a receive timeout.

## 15. Exercises and Self-Check Questions

**Q1. What does `TTL=0` mean?** No expiration under the JMS TTL mechanism. It does not guarantee a message survives broker restarts, purges, or other retention policies.

**Q2. With `TTL=5,000ms`, sent at `t=0`, committed at `t=7s`, from when is `JMSExpiration` calculated?** From the client send time, around `t=5s`; it does not restart at commit.

**Q3. After a consumer receives a valid message, if it expires 10 seconds later, is the running handler automatically aborted?** No. TTL governs expiration/delivery; a separate business timeout/deadline is required.

**Q4. If `JmsTemplate.setTimeToLive(10_000L)` is called without enabling explicit QoS, is 10 seconds guaranteed to apply?** Do not assume so. Enable `setExplicitQosEnabled(true)` when configuring `JmsTemplate` manually; Spring Boot automatically enables QoS when the template TTL property is set.

**Q5. Is calling `message.setJMSExpiration(...)` the standard way to set TTL?** No. That is a provider-reserved header setter, not an application TTL configuration API.

**Q6. With delivery delay=10s and TTL=2s, what happens?** The message expires before its earliest eligible delivery time; there is no valid delivery window.

**Q7. Does `Consumer.receive(timeout=1s)` returning `null` mean the message expired?** No. It only shows no message was received during that wait.

**Q8. Does a message's TTL automatically reset when the broker redelivers after a rollback?** No, not for the same message's expiration. If the application republishes a new message, it must actively carry over the business deadline if needed.

**Q9. Do expired messages automatically go to the DLQ?** Not necessarily. The broker may drop them or move them to an expiry address depending on configuration; DLQ is a separate policy concept.

**Q10. Is TTL suitable as the mechanism to cancel a payment command?** Not by itself. You need a state machine, idempotency, and reconciliation because the consumer might have already received the message before expiry while still processing it.

### Hands-On Exercises

1. Run Section 7 with a 250ms TTL, confirm the short-lived message is not received after 1.2s in the demo broker; inspect stdout and metrics.
2. Change the short TTL to `5_000ms`. Confirm `receive` retrieves the message with the same 1.2s delay.
3. Set `TTL=0` and explain how `JMSExpiration=0` differs from "expire now."
4. Use `MessageProducer.send(message, mode, priority, ttl)` to send two messages to the same queue with different TTLs; verify which one is delivered.
5. Create a JMS transaction and commit later than TTL; observe the outcome to understand the send-time anchor.
6. Enable delivery delay in Spring, set TTL shorter than delay; explain why no valid delivery window exists.
7. Configure an expiry address on a test Artemis broker and observe how expired messages move to the inspection queue.
8. Write a consumer that validates a business deadline inside the payload and deduplicates by `BusinessId`, even when the JMS message is still valid.
9. Track metrics: sent, consumed, expired, dead-lettered, timeout, and backlog; verify why receiving `null` has more than one possible cause.

## 16. Official References

- [Jakarta Messaging 3.1 Specification, Section 3.4.9 JMSExpiration](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): expiration anchor, TTL in transactions, guarantee limits.
- [Jakarta Messaging 3.1 API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): `JMSExpiration`, `JMSTimestamp`, `JMSDeliveryTime`, and defaults.
- [Jakarta Messaging 3.1 API — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): `setTimeToLive` and send with QoS.
- [Spring Framework 6.2 — JMS Using](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): configuring explicit QoS on `JmsTemplate`.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setTimeToLive`, `setExplicitQosEnabled`, `setReceiveTimeout`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/docs/3.3.0/reference/html/application-properties.html): `spring.jms.template.time-to-live` and `qos-enabled`.
- [Apache ActiveMQ Artemis — Message Expiry](https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html): `expiry-address`, drop policy, expiry scan.
