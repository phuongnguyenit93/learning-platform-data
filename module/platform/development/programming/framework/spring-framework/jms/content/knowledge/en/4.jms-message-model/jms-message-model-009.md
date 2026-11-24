# JMSDeliveryMode, JMSPriority, and JMSExpiration

> **Topic:** Message Model in Spring Framework – JMS (Jakarta Messaging). These three headers tell us what delivery assurance a message was sent with, what priority it carries, and until when it remains valid. Understanding them accurately helps design reliable queues, reduce stale messages, and avoid false expectations around "guaranteed delivery", "strict priority", or "self-canceling tasks".

## 1. Three Headers Answering Three Different Questions

Every JMS message has a **body**, spec-defined **headers**, and **properties** for supplementary data. When sending a message, the producer can specify Quality of Service (QoS) parameters: **delivery mode**, **priority**, and **time-to-live (TTL)**. The JMS provider/broker records the applied settings in the corresponding headers:

| Header on `jakarta.jms.Message` | Meaning | Producer default | Unit / range |
| --- | --- | --- | --- |
| `JMSDeliveryMode` | Delivery durability assurance across broker/provider failures | `DeliveryMode.PERSISTENT` (numeric value `2`) | `PERSISTENT` or `NON_PERSISTENT` |
| `JMSPriority` | Relative priority when dispatching messages | `4` | Integer from `0` (lowest) to `9` (highest) |
| `JMSExpiration` | Timestamp when the message expires | `0`, because default TTL is `0` | Epoch milliseconds; `0` means no expiration by TTL |

**Important relationship:** the sender does **not** configure these three fields directly via `message.setJMSDeliveryMode(...)`, `message.setJMSPriority(...)`, or `message.setJMSExpiration(...)`. Those setters exist for the provider to populate headers on send. Applications must set delivery mode, priority, and TTL on **`MessageProducer` / `JMSProducer` or as `send` method parameters**. After synchronous `send` returns, producers and consumers can read the headers to observe the actual applied values.

Beyond what code requests, the broker or administrative configuration can **override** delivery mode, priority, TTL, and delivery delay if supported by the provider. In that case, the received header must reflect the applied value, so what matters is inspecting the **message after send/receive**, not only Java-side configuration.

~~~text
Producer (chooses QoS)                 Broker / JMS provider               Consumer
---------------------                  ----------------------               --------
deliveryMode=PERSISTENT  -----+
priority=7                -----+-----> applies policy, writes headers ---> getJMSDeliveryMode()
timeToLive=30_000 ms      -----+        stores/routes/expires per config    getJMSPriority()
                                                                            getJMSExpiration()
~~~

## 2. `JMSDeliveryMode` – Transport Reliability

### 2.1. The Two Standardized Modes

`jakarta.jms.DeliveryMode` defines exactly two values:

- **`DeliveryMode.PERSISTENT` (2)**: the producer instructs the provider to use durable sending/storage so the message can survive provider failures per the JMS contract. This is the default. It typically incurs higher storage write, sync, and I/O overhead.
- **`DeliveryMode.NON_PERSISTENT` (1)**: prioritizes lower overhead; the provider is not required to persist the message to stable storage. Messages can be lost if the provider stops or crashes. Suits data that can be regenerated or tolerates occasional missed updates.

Per Jakarta Messaging's *delivery* contract, `NON_PERSISTENT` has **at-most-once** semantics; `PERSISTENT` requires **once-and-only-once** delivery under proper management and message retention conditions. Keep that guarantee within its exact scope: **it is a send/delivery guarantee of the JMS provider, not proof that application side effects will execute exactly once on a database or external service**.

For example: a consumer writes to a database successfully and then loses its connection before JMS ack/commit. After recovery, the message may be redelivered, causing business logic to run again unless deduplication controls exist. Likewise, a producer timing out after `send` may not know whether the broker received the message; blind retries can produce two messages with the same business meaning.

### 2.2. Persistent Still Has Conditions

Setting `PERSISTENT` does not automatically solve any of the following cases:
1. The message **expires by TTL** before being delivered to a consumer.
2. The queue is deleted/purged, or quotas/retention policies discard the message.
3. A topic uses a **non-durable subscription** and the subscriber is offline when the message is published.
4. The consumer receives the message but fails business/DB logic or acks at the wrong time.
5. Broker storage/HA is under-provisioned or its durability settings fall short of requirements.

For critical data (orders, payments, vital audit logs), combine `PERSISTENT` with durable queues/durable subscriptions, transactions/acknowledgments, idempotency, monitoring, and failed-message policies. For regenerable status updates (such as frequent metrics snapshots), `NON_PERSISTENT` can be sensible if losing a few updates is acceptable.

### 2.3. Setting Delivery Mode Properly

Classic API:

~~~java
// Snippet: producer and message have been created from a valid Session.
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(message); // Applies producer defaults.
~~~

Or specify per individual send:

~~~java
// Parameters in order: message, deliveryMode, priority, timeToLive (milliseconds).
producer.send(message, DeliveryMode.NON_PERSISTENT, 2, 5_000L);
~~~

Simplified `JMSProducer` API:

~~~java
// Snippet: context is a valid JMSContext, destination exists.
context.createProducer()
        .setDeliveryMode(DeliveryMode.PERSISTENT)
        .send(destination, "order-created");
~~~

In these snippets, import `jakarta.jms.DeliveryMode` and use an application- or framework-managed producer/context. Setting `NON_PERSISTENT` does not mean "always faster": throughput impact must be measured against your provider, disk, ACK mode, message size, and real load.

## 3. `JMSPriority` – Delivery Priority, Not an Absolute Execution Schedule

JMS defines **10 levels**, from `0` to `9`, default `4`:
- `0–4`: *normal priority* levels.
- `5–9`: *expedited priority* levels.

Providers are encouraged to try delivering higher-priority messages ahead of normal ones, **but the specification does not mandate strict priority ordering**. A priority `9` message is not guaranteed to reach a consumer before every priority `4` message sent earlier, especially with multiple consumers, prefetch/buffering, already-dispatched messages, transactions, or resource contention.

Example: a queue holds 10,000 report-generation requests at priority `4`, followed by an urgent alert at priority `9`. The broker may prioritize the alert still sitting in the queue; however, **it cannot "preempt" a long-running task a consumer has already received and started processing**. Raising priority also creates no extra CPU, threads, or database connections.

**Starvation risk:** if a high volume of high-priority messages arrives continuously, lower-priority groups may wait indefinitely. Therefore, when two workloads have very different SLAs, consider **separate queues**, concurrency caps, and capacity planning instead of relying solely on the number `9`.

### 3.1. Configuring and Observing

~~~java
// Snippet: set default for subsequent sends by this producer.
producer.setPriority(7);
producer.send(message);

// Or specify for a single send only.
producer.send(message, DeliveryMode.PERSISTENT, 7, 30_000L);
~~~

After sending or in the consumer:

~~~java
int appliedPriority = receivedMessage.getJMSPriority(); // 0..9
~~~

`message.setJMSPriority(9)` is **not** how to choose send priority: the provider resets the header from producer/send settings and administrative configuration. If you want to assign urgency levels by business logic, map them cleanly (e.g. `NORMAL=4`, `URGENT=7`) and make sure producers do not accidentally send all messages at priority `9`.

### 3.2. Priority Differs from Expiration

**Urgent** does not mean **valid for a long time**. A hot price-quote update might have high priority yet a very short TTL; an invoice creation message might have medium priority yet no expiration or a long business validity window. Make **independent** decisions for priority and TTL.

## 4. `JMSExpiration` – Expiration Timestamp Derived from Time-to-Live

### 4.1. Distinguishing TTL from Expiration

- **TTL (`timeToLive`)**: the duration the producer requests the message remain valid, in **milliseconds**. Set via `MessageProducer.setTimeToLive(long)`, `JMSProducer.setTimeToLive(long)`, or `send` parameters.
- **`JMSExpiration`**: the absolute timestamp computed and written into the header by the provider on send; unit is **milliseconds since 1970-01-01T00:00:00Z**.

When TTL is greater than `0` and not overridden administratively:

~~~text
JMSExpiration = send time + timeToLive (milliseconds)
~~~

When TTL is `0`, `JMSExpiration = 0`, meaning **does not expire due to JMS TTL**. A value of `0` **does not mean "expires immediately"**; nor does it guarantee eternal retention because brokers also enforce retention, quota, and operational policies.

Timeline illustration:

~~~text
Producer sends: 10:00:00.000 UTC
TTL:           30_000 ms (30 seconds)
JMSExpiration: 10:00:30.000 UTC

10:00:02  Broker receives, message is valid
10:00:15  Consumer can receive
10:00:30  Expiration timestamp for undelivered message
10:00:40  Consumer starts a new receive: expired message should not be delivered
~~~

When an undelivered message expires, the provider **should discard** it. JMS does not define a standard expiration notification sent back to the producer. Applications **should not receive** expired messages, yet the specification does not strictly guarantee it can never happen; providers also do not standardize millisecond-level timer precision.

### 4.2. TTL Starts at Send Time, Even Inside a Transaction

Suppose a producer sends in a JMS transacted session at `10:00:00` with a `5 s` TTL, but the transaction only commits at `10:00:08`. Per Jakarta Messaging, expiration is still calculated from **when the client called send**, not recalculated from commit time. Thus, the message may expire before the transaction even makes it visible to consumers.

This matters during large batching, long transactions, or network congestion. **Short TTL + slow transaction commit** is a common reason messages appear "sent successfully" yet are never seen by consumers.

### 4.3. Expiration Does Not Cancel an In-Flight Task

If a consumer already received a message before expiration and is calling a database or external service, **TTL does not kill the thread, roll back the transaction, or cancel outbound HTTP requests**. If business logic must abort past a deadline, the consumer must check a business deadline independently and define overdue behavior.

Conversely, `JMSExpiration = 0` does not replace poison-message handling, retry limits, or DLQs. Those are separate policies.

### 4.4. Setting and Reading TTL/Expiration

~~~java
// Snippet: TTL for subsequent sends using this producer.
producer.setTimeToLive(15_000L); // 15 seconds
producer.send(message);

// Specific TTL for one send, also specifying mode + priority.
producer.send(message, DeliveryMode.PERSISTENT, 7, 15_000L);

// On the message after synchronous send, or on a received message:
long expiresAtMillis = message.getJMSExpiration();
boolean neverExpiresByTtl = (expiresAtMillis == 0L);
~~~

Do not call `message.setJMSExpiration(System.currentTimeMillis() + 15_000)` to configure TTL: the provider can overwrite it completely. Never pass a negative TTL; use `0` when no TTL is desired. `JMSExpiration` is an absolute timestamp, **not remaining milliseconds**; if you need remaining time, compute `expiresAtMillis - System.currentTimeMillis()` and treat it only as an estimate at observation time.

## 5. How All Three Attributes Work Together on One Message

A `create-report` message might be configured as:

~~~text
deliveryMode = PERSISTENT
priority     = 7
timeToLive   = 60_000 ms
                    |
                    v
JMSDeliveryMode = 2 (PERSISTENT)
JMSPriority     = 7
JMSExpiration   = send time + 60 seconds
~~~

Meaning: request durable storage/transport, prioritize ahead of normal levels *when the broker can reorder*, yet consider it invalid for **new delivery** after the expiration timestamp. There is **no contradiction** between `PERSISTENT` and TTL: "surviving a broker crash" does not mean "never expires".

| Scenario | Suggested delivery mode | Suggested priority | Suggested TTL | Notes |
| --- | --- | --- | --- | --- |
| Mandatory order-created event | `PERSISTENT` | `4` | `0` or per explicit business SLA | Use durable queues/transactions/idempotency; avoid arbitrary short TTLs |
| Continuous repetitive sensor snapshots | `NON_PERSISTENT` if sample loss is tolerable | `2–4` | Very short, e.g. a few seconds | Stale readings are useless; verify sampling/replay requirements |
| Urgent status update command | `PERSISTENT` if critical | `7–9` | Per real deadline | Priority does not preempt running tasks |
| Low-importance broadcast notification | Depends on loss tolerance | `1–4` | Per usefulness window | Do not keep stale messages creating backlog |
| Long report-generation job | Usually `PERSISTENT` | `4` | Can be `0` | Track timeouts in job state; TTL does not cancel running jobs |

These numbers are **illustrative business decisions**, not mandatory defaults or Artemis/Spring SLAs. Start from the cost of losing a message, urgency, and how long data remains useful; then choose matching QoS settings.

## 6. API Comparison: Setting QoS vs. Reading Headers

| Send approach | Primary syntax | Effective scope |
| --- | --- | --- |
| Classic JMS API | `producer.setDeliveryMode(mode)`, `setPriority(n)`, `setTimeToLive(ms)` | Defaults for sends on that producer |
| Classic JMS API | `producer.send(message, mode, priority, ttl)` | Overrides producer defaults for that specific send |
| Simplified JMS API | `context.createProducer().setDeliveryMode(...).setPriority(...).setTimeToLive(...).send(destination, body)` | QoS on that `JMSProducer` |
| Spring `JmsTemplate` | `setDeliveryMode`, `setPriority`, `setTimeToLive` + `setExplicitQosEnabled(true)` | Sends through that template when explicit QoS is enabled |
| Receiver side | `getJMSDeliveryMode()`, `getJMSPriority()`, `getJMSExpiration()` | Reads headers set by provider |

These three headers are **JMS-defined headers**, not custom application properties. `message.setStringProperty("priority", "7")` only creates an arbitrary property named `priority` and does **not** alter `JMSPriority`. Conversely, JMS message selectors can evaluate `JMSPriority` numerically; when using `JMSDeliveryMode` in a selector, values are represented as string literals `'PERSISTENT'` or `'NON_PERSISTENT'`. Avoid relying on selectors to "compensate" for an undesigned priority/TTL policy.

## 7. Runnable Example: Jakarta JMS via Spring Boot and ActiveMQ Artemis

This is a Java 17 Gradle application using Spring Boot 3.3.x to create a `ConnectionFactory` and using the `jakarta.jms` API directly so you can observe the real headers **after send and after receive**.

**Prerequisites:** ActiveMQ Artemis broker at `tcp://localhost:61616`, credentials `demo/demo`, queue `demo.qos` (pre-created or auto-create enabled on the broker), and producer/consumer permissions. This is a local demo setup; production environments must use secrets and TLS per system policy. No Spring MVC or HTTP server is needed for this demo.

**Layout:**

~~~text
jms-qos-headers/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/QosHeadersApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-qos-headers'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    cache:
      enabled: false
~~~

Disabling caching in the demo is solely so connection allocation/closing reflects the JMS API directly; it is **not** a default recommendation for production applications.

`src/main/java/demo/QosHeadersApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QosHeadersApplication implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public QosHeadersApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(QosHeadersApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String traceKey = UUID.randomUUID().toString();

        try (Connection connection = connectionFactory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            Queue destination = session.createQueue("demo.qos");
            String selector = "traceKey = '" + traceKey + "'";

            try (MessageProducer producer = session.createProducer(destination);
                 MessageConsumer consumer =
                         session.createConsumer(destination, selector)) {

                TextMessage outgoing = session.createTextMessage("create-report");
                outgoing.setStringProperty("traceKey", traceKey);

                // QoS for this exact send: persistent, priority 7, TTL 60s.
                producer.send(
                        outgoing,
                        DeliveryMode.PERSISTENT,
                        7,
                        60_000L
                );

                printHeaders("sent", outgoing);

                // Classic JMS Connection only delivers messages once started.
                connection.start();
                Message incoming = consumer.receive(5_000L);

                if (!(incoming instanceof TextMessage textMessage)) {
                    throw new IllegalStateException(
                            "Did not receive expected TextMessage");
                }

                System.out.println("received.body=" + textMessage.getText());
                printHeaders("received", incoming);
            }
        }
    }

    private static void printHeaders(String prefix, Message message)
            throws Exception {
        int mode = message.getJMSDeliveryMode();
        String modeName = switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN";
        };

        System.out.println(prefix + ".mode=" + modeName);
        System.out.println(prefix + ".priority=" + message.getJMSPriority());
        System.out.println(prefix + ".hasExpiration="
                + (message.getJMSExpiration() > 0L));
    }
}
~~~

Run in the project directory with JDK 17+ and Gradle installed (or Gradle wrapper if generated):

~~~bash
gradle bootRun
~~~

With a running broker, available queue, no QoS override config, and message received within 5 seconds, the **application stdout** is:

~~~text
sent.mode=PERSISTENT
sent.priority=7
sent.hasExpiration=true
received.body=create-report
received.mode=PERSISTENT
received.priority=7
received.hasExpiration=true
~~~

Spring Boot and Artemis may print additional startup/connection logs. A random `traceKey` is used in the selector to receive only the message from the current run, avoiding stale messages from prior runs. This snippet **does not assert message delivery ordering by priority** since only one message is sent.

**Step-by-step explanation:**
1. Spring Boot configures an Artemis `ConnectionFactory` based on `application.yml`.
2. The program creates a connection, session, queue, producer, and consumer with a dedicated selector.
3. `outgoing.setStringProperty("traceKey", ...)` sets a property for filtering; it does **not** set QoS.
4. `producer.send(outgoing, DeliveryMode.PERSISTENT, 7, 60_000L)` requests the provider apply those three parameters for this send.
5. Once synchronous `send` completes, the producer reads `JMSDeliveryMode`, `JMSPriority`, and `JMSExpiration` from the provider-updated message.
6. `connection.start()` enables delivery; the consumer reads the same headers and body. On exit, `try-with-resources` closes resources.

If the broker is absent, credentials are wrong, the destination does not exist and auto-create is disabled, the message expires too early, or another consumer competes under the selector, the output may differ or throw an exception. Do not use the sample output to assert all providers apply QoS identically. In Spring-managed applications, prefer `JmsTemplate`/listener containers as shown next.

## 8. Configuring QoS in Spring `JmsTemplate`

Spring `JmsTemplate` takes a `ConnectionFactory`, executes send/receive operations, and cleans up resources per framework configuration. For QoS needs, one easily overlooked detail is:

**`setDeliveryMode`, `setPriority`, and `setTimeToLive` must be paired with `setExplicitQosEnabled(true)`** if you want `JmsTemplate` to pass those values into the send call. When `explicitQosEnabled=false` (the default), the template uses defaults determined by the producer/provider/administrative settings; the three template fields do not automatically override sends.

Bean configuration example (this is a **Spring code snippet**, using the same project/`ConnectionFactory`; not a standalone Java file):

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ReportMessagingConfig {

    @Bean
    JmsTemplate reportJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000L);
        return template;
    }
}
~~~

Using the bean in a Spring service (snippet requires importing `org.springframework.stereotype.Service`):

~~~java
@Service
public class ReportPublisher {

    private final JmsTemplate reportJmsTemplate;

    public ReportPublisher(JmsTemplate reportJmsTemplate) {
        this.reportJmsTemplate = reportJmsTemplate;
    }

    public void publish(String reportId) {
        reportJmsTemplate.convertAndSend("demo.qos", reportId);
    }
}
~~~

The two snippets `ReportMessagingConfig` and `ReportPublisher` are illustrative classes within an existing Spring context; if added to the **same** `QosHeadersApplication` from section 7, place the files under package `demo` and add `package demo;` so Spring component scanning discovers them. This is not code that can be run directly with `javac ReportPublisher.java` without Spring dependencies.

A `JmsTemplate` shared across threads should be **configured once at initialization**—do not flip `setPriority(...)` or `setTimeToLive(...)` right before each `convertAndSend`, because concurrent sends can overwrite each other's settings. If different message types require different QoS, consider **dedicated templates/producers** or classic JMS `send(message, mode, priority, ttl)` per send. Avoid relying on `MessagePostProcessor` to call `setJMSPriority`/`setJMSExpiration` directly: those headers are managed by the provider.

Spring also supports `QosSettings` to bundle delivery mode, priority, and TTL; fundamentally it is still QoS configuration on the template and does not alter the JMS contract.

## 9. Limitations to Understand Before Going to Production

### 9.1. TTL Differs from Delivery Delay

`JMSExpiration` answers **"until when may the message be delivered"**, whereas `JMSDeliveryTime` answers **"at earliest when may the message be delivered"** when delivery delay is used. The two timestamps are independent and computed from send time per their respective parameters.

For example, sent at `10:00:00`, delivery delay `20 s`, TTL `10 s`: the message expires at `10:00:10` before its earliest eligible delivery time at `10:00:20`. Never set delay longer than TTL unless intentional and with full understanding of the consequence. `JMSProducer.setDeliveryDelay(...)` or producer delay mechanisms are a separate feature and do not replace TTL.

### 9.2. Expiration Is Not a Business Deadline

Suppose a job must finish before 12:00. Sending a message at 11:59:59 with a `30 s` TTL allows a consumer to receive it after 12:00 before TTL expires. Business deadlines must be stored explicitly, e.g. `businessDeadline` in the payload/property, and checked by the consumer before executing actions.

Conversely, once a message has been delivered and a worker is running, JMS TTL does not roll back database changes or interrupt tasks. Implement cancellation/timeouts/idempotency separately as needed.

### 9.3. Priority Does Not Guarantee Hard SLAs

A shared queue carrying multiple message types can suffer head-of-line blocking, especially when consumers prefetch large batches into local buffers. Do not use priority as a substitute for isolating urgent traffic, load shedding, quotas, autoscaling, or designing cancellable work. Measure **queue age per priority level**, not only total queue depth.

### 9.4. Persistent Does Not Guarantee Database Exactly-Once

For critical messages, separate three layers:
1. **Producer → broker**: send succeeds, or encounters ambiguous outcomes on connection drops.
2. **Broker → consumer**: depends on retention, persistent/non-persistent, TTL, ack, and transactions.
3. **Consumer → side effect**: databases/external APIs lie outside the delivery mode contract; design idempotency or appropriate transactions.

To deduplicate retries/redeliveries, messages should carry a stable **`eventId`/`commandId`**. The consumer records processed IDs in the same database transaction as the side effect, using a unique constraint or equivalent atomic mechanism. Raising priority or setting persistent does not resolve duplicate state.

### 9.5. Brokers Can Override and Discard Messages

Operational factors can shape observed behavior: queue addresses, durable subscriptions, storage sync, expiry addresses, dead-letter addresses, limits, TTL overrides, max delivery attempts, and how the provider handles expired messages. The JMS API does not require expired messages to be moved to a DLQ or generate notifications to producers. Verify the actual configuration and metrics of your Artemis/broker instance.

## 10. Meaningful Testing and Monitoring

| Test case | Setup | What to verify |
| --- | --- | --- |
| Default headers | Send without configuring QoS | Default mode `PERSISTENT`, priority `4`, expiration `0` if broker does not override |
| Explicit QoS send | Send mode `PERSISTENT`, priority `7`, TTL `60_000` | Actual message headers after send and at consumer |
| Expired message | Set short TTL, delay consumer receive cleanly | Message is no longer delivered per provider policy; measure expired count rather than inferring only from `receive` timeout |
| High priority | Build priority `4` backlog then add priority `9` | Measure latency; do **not** write a test asserting priority `9` always arrives strictly before every other message |
| Broker restart | Send persistent and non-persistent, stop then restart under test conditions | Verify results per storage/retention config; do not assume all providers behave identically |
| Long transaction | Send with short TTL, delay commit | Verify expiration is calculated from send, not reset by commit |
| Spring QoS | Toggle `explicitQosEnabled` off/on | Verify template setters apply only under explicit mode |
| DLQ and expiry | Configure explicit broker policies | Verify where expired messages go and monitoring/cleanup procedures |

In production, monitor **persistent/non-persistent** message counts, priority distribution, queued message age, expiration rates, queue depth, send latency, redeliveries, DLQ/expiry queues, disk/broker errors, and business processing SLAs. These metrics expose overly short TTLs, priority starvation, or mismatched retention.

**Testing note:** use an isolated broker and dedicated queues for tests, because short TTLs or broker restarts can wipe test data. Never run destructive experiments against production business queues.

## 11. Common Mistakes and Fixes

| Wrong understanding / practice | Why it is wrong | Right approach |
| --- | --- | --- |
| `message.setJMSPriority(9)` to send urgently | Provider overwrites header on send | Use `producer.setPriority(9)` or `send` parameter |
| `message.setJMSExpiration(now + ttl)` to set TTL | Expiration is calculated by provider from time-to-live | Use `producer.setTimeToLive(ttl)`/`send(..., ttl)` |
| `JMSExpiration=0` means expires immediately | `0` means no expiration by TTL | Choose a positive TTL when expiration is desired |
| `PERSISTENT` guarantees database updates exactly once | JMS delivery and side effects are separate scopes | Transactions/acks, idempotency, and retry controls |
| Priority `9` always runs before priority `4` | Spec only asks providers to make best effort to prioritize | Benchmark; split queues/SLAs where needed |
| Calling `setPriority(7)` on `JmsTemplate` is enough | Explicit QoS is off by default | Pair with `setExplicitQosEnabled(true)` |
| TTL `5000` interpreted as 5000 seconds | TTL is in milliseconds | `5000 ms = 5 seconds` |
| TTL automatically aborts a received job | TTL governs message delivery eligibility, not side effects | Consumer checks deadline and handles cancellation separately |
| Expired messages always go to DLQ | Spec does not mandate how expiry is handled | Check broker expiry address/retention policy |
| Using `NON_PERSISTENT` on order events for throughput | Messages can be lost on broker failure | Weigh message loss cost and choose mode accordingly |

## 12. Self-Check Questions

1. Why does `JMSExpiration` store epoch milliseconds while producers configure relative TTL?
2. Does `JMSExpiration=0` guarantee the broker keeps a message forever? Why or why not?
3. Must a `PERSISTENT`, priority `9` message that has expired still be delivered to a consumer?
4. Once a consumer has received a message, does TTL expiring make Spring automatically roll back the database transaction?
5. Why might `JmsTemplate.setTimeToLive(10_000L)` not take effect if `setExplicitQosEnabled(true)` is missing?
6. When calling `producer.send(message, DeliveryMode.NON_PERSISTENT, 3, 5_000L)`, do prior default QoS setters on the producer still govern this send?
7. If a high-priority message is stuck behind several already-running tasks, is priority `9` enough to guarantee an SLA?
8. Why does "JMS once-and-only-once delivery" differ from "database side effect exactly-once"?

**Key takeaway:**
- `JMSDeliveryMode`: reliability policy for message **transport/delivery**.
- `JMSPriority`: **priority hint** from `0` to `9`, not strict ordering.
- `JMSExpiration`: **expiration timestamp** computed by provider from TTL; `0` means no expiration by TTL.
- Configure QoS on **producer/send/`JmsTemplate` with explicit QoS**; inspect actual headers to verify what the provider applied.
- Evaluate consumers, transactions, retention, and business deadlines holistically before picking production values.

## References

1. Jakarta Messaging 3.1 Specification, `3.4.2`, `3.4.9–3.4.12`, `7.4`, `7.7–7.9`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Jakarta Messaging 3.1 API – Message: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
3. Jakarta Messaging 3.1 API – MessageProducer: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
4. Jakarta Messaging 3.1 API – DeliveryMode: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/deliverymode
5. Spring Framework – JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
6. Spring Framework – JmsTemplate Javadoc: https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
7. Spring Boot – Messaging / JMS: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
