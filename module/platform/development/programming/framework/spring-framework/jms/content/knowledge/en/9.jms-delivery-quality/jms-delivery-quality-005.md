# Delivery Delay and Earliest Delivery Time in Spring JMS

## 1. What Problem Does Delivery Delay Solve?

In asynchronous systems, a producer sometimes needs to **send a message right now while preventing consumers from receiving it immediately**. For example: after sending a confirmation email, the application wants to wait 10 seconds before checking status; after creating an order, the system wants to emit a payment reminder several minutes later; or a job can be queued before a processing window opens.

**Delivery delay** is the minimum duration (in milliseconds) from when a message is sent until the provider is **allowed** to make the message available to a consumer. This feature was introduced in JMS 2.0 and continues in Jakarta Messaging 3.x. It supports relative scheduling without forcing the producer to hold a connection open, call `Thread.sleep(...)`, and then send.

The single most important point to remember:

> **The earliest delivery time is not an exact execution timestamp.** Past that point, the message is merely *eligible* for delivery; a consumer may receive it later due to broker load, priority ordering, backlog, transactions, network, scheduler behavior, throttling, or consumer downtime.

This lesson belongs to the **Delivery Quality** group in Spring Framework – JMS. After this lesson you will understand:
- How delivery delay differs from time-to-live (TTL), expiration, priority, redelivery delay, and a job scheduler.
- The meaning of the `JMSDeliveryTime` header; how the earliest delivery timestamp is computed at send time, including inside transactions.
- How to use `MessageProducer.setDeliveryDelay(...)`, `JMSProducer.setDeliveryDelay(...)`, and `JmsTemplate.setDeliveryDelay(...)`.
- How to configure fixed delays and per-message delays without corrupting a singleton `JmsTemplate`.
- How to verify with Java 17, Spring Boot, and Artemis examples, along with common failure scenarios.

## 2. Distinguishing Four Timestamps

Suppose a message is **sent** at 10:00:00.000 and the producer sets:

~~~text
deliveryDelay = 5_000 ms
timeToLive    = 12_000 ms

10:00:00.000            10:00:05.000             10:00:12.000
     |                        |                         |
  SEND MESSAGE         ELIGIBLE FOR DELIVERY         EXPIRES
     |------------------------|-------------------------|
       not yet deliverable       may be delivered
       to consumer               (if still present)

Provider may deliver at 10:00:05.100 or 10:00:07.000...
but must not deliver before 10:00:05.000.
~~~

| Concept | Value/Meaning | Header Relation |
|---|---|---|
| **Send time** | When the provider/client sends the message per JMS rules. | `JMSTimestamp` usually records send time, though it can be disabled. |
| **Delivery delay** | Minimum delay, e.g. 5,000 ms. | Configured on `MessageProducer` or `JMSProducer`, not an arbitrary payload field. |
| **Earliest delivery time** | Send time + delay, e.g. 10:00:05.000. | `JMSDeliveryTime` holds this timestamp in epoch milliseconds. |
| **Expiration time** | Send time + TTL, e.g. 10:00:12.000; TTL=0 indicates no TTL expiration. | `JMSExpiration` in epoch milliseconds, or 0 if TTL=0. |

**Formula with positive TTL:**

~~~text
earliestDeliveryTime = sendTime + deliveryDelay
expirationTime       = sendTime + timeToLive
availableWindow      = [earliestDeliveryTime, expirationTime)
~~~

The interval notation here denotes only the *eligible delivery window*, not a broker guarantee to deliver within that window. With TTL=0, `JMSExpiration=0`; there is no TTL-based expiration, though other administrative policies such as quotas, retention, DLQ, or message deletion still apply.

**Critical hazard:** if `timeToLive <= deliveryDelay` with a positive TTL, the message may **expire before or at the exact moment it becomes eligible for delivery**. For example, delay=10 seconds, TTL=3 seconds: the message can expire at second 3 while having to wait until second 10. That is not a scheduler bug; it is a contradictory configuration.

### Delivery Delay Uses Relative Offsets

`setDeliveryDelay(5_000L)` means wait at least 5 seconds from *send time*, **not** "schedule delivery for 5:00 PM." When a requirement calls for a fixed wall-clock schedule by timezone (such as the next business day at 08:00 Asia/Ho_Chi_Minh), compute the delay offset from a reliable system clock, verify DST/timezones and broker max delay limits; for complex schedules, use a dedicated scheduler/outbox/workflow engine instead of treating JMS as a business calendar service.

## 3. Standard Jakarta Messaging Contract

### 3.1. Classic API: MessageProducer.setDeliveryDelay

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

// Snippet: requires a real Session and MessageProducer from the provider.
producer.setDeliveryDelay(5_000L);
TextMessage message = session.createTextMessage("generate-invoice");
producer.send(message);
~~~

`MessageProducer` can configure a default delivery delay for subsequent messages sent through that producer. According to Jakarta Messaging:
- Unit is **milliseconds**; default is `Message.DEFAULT_DELIVERY_DELAY=0L`.
- `setDeliveryDelay(long)` has existed since JMS 2.0.
- `send(message, deliveryMode, priority, timeToLive)` takes only **three** extra QoS parameters; it has **no separate delivery delay parameter**. Therefore delay is configured on the producer.
- A provider is permitted administrative policies that override send options; always read the actual `JMSDeliveryTime` and test broker behavior.

In multithreaded applications, do not share `Session`/`MessageProducer` casually. With `JmsTemplate`, let Spring manage resources and keep template configuration immutable after initialization.

### 3.2. Simplified API: JMSContext and JMSProducer

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;

public final class SimplifiedApiExample {
    public static void schedule(ConnectionFactory factory) {
        try (JMSContext context = factory.createContext()) {
            context.createProducer()
                    .setDeliveryDelay(5_000L)
                    .send(context.createQueue("billing.invoice.jobs"),
                            "generate-invoice");
        }
    }
}
~~~

This is a **class compilable against the Jakarta Messaging API**, requiring a `ConnectionFactory` and a supporting broker to run. `JMSProducer#setDeliveryDelay(...)` returns the producer for method chaining, unlike `MessageProducer#setDeliveryDelay(...)` which returns `void`. `JMSContext`/`JMSProducer` throw `JMSRuntimeException`, whereas the classic API throws checked `JMSException`; do not confuse either with Spring's `JmsException`.

### 3.3. The JMSDeliveryTime Header Is an Output, Not a Scheduling API

Read the earliest delivery time via:

~~~java
long earliestEpochMillis = receivedMessage.getJMSDeliveryTime();
~~~

The value is milliseconds since 1970-01-01T00:00:00Z; you can convert it to `java.time.Instant` or a display timezone. By specification, the provider sets the `JMSDeliveryTime` header on send; clients **do not call** `message.setJMSDeliveryTime(...)` to schedule delivery. Provider-managed header setters can be overwritten during send.

Do not use:
- `message.setJMSTimestamp(...)` to fake a delay.
- `message.setJMSExpiration(...)` to schedule a receive time.
- A custom application property named `deliveryTime` expecting the provider to understand it, unless you implemented custom handling.
- `Thread.sleep(5_000)` inside an HTTP request to "wait before sending": this ties up threads, fails badly on process crashes, and is no longer send-now-deliver-later.

## 4. How Spring JmsTemplate Supports Delivery Delay

Spring Framework 6.x provides:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDeliveryDelay(5_000L);
template.convertAndSend("billing.invoice.jobs", "generate-invoice");
~~~

This is an illustrative snippet in an application with a real `jakarta.jms.ConnectionFactory`. `JmsTemplate` manages sessions/connections and invokes `MessageProducer.setDeliveryDelay(...)` before sending the message. The setting serves as policy **for sends using that template**.

Commonly misunderstood details:
- `JmsTemplate#setDeliveryDelay(...)` defaults to **-1**: Spring **does not pass a delivery delay** down to the producer. When the provider uses the standard default, delay is 0.
- `setDeliveryDelay(0L)` **explicitly sends with no delay**, distinct from Spring's `-1` sentinel which leaves the provider to apply its default/administrative config.
- `setExplicitQosEnabled(true)` governs the template's `deliveryMode`, `priority`, and `timeToLive`. **Delivery delay is configured separately**; you do not need to enable that flag just to call `setDeliveryDelay`.
- Because a configured template is shared across multiple threads, **do not mutate `setDeliveryDelay(...)` per request**. Mutating it concurrently can delay another service's messages as well.

### One-Time Configuration Beans

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DelayedMessagingConfiguration {
    @Bean("delayedJobsTemplate")
    JmsTemplate delayedJobsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("billing.invoice.jobs");
        template.setDeliveryDelay(5_000L);
        return template;
    }

    @Bean("immediateJobsTemplate")
    JmsTemplate immediateJobsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("billing.invoice.jobs");
        template.setDeliveryDelay(0L);
        return template;
    }
}
~~~

Both beans share the same `ConnectionFactory` and Queue, yet enforce **two stable, distinct send policies**. Services inject `@Qualifier("delayedJobsTemplate")` or `@Qualifier("immediateJobsTemplate")`. Without qualifiers when multiple `JmsTemplate` beans exist, dependency injection becomes ambiguous.

Note: `setDefaultDestinationName` refers to a Queue under the default `pubSubDomain=false` setting. For a Topic, declare `pubSubDomain=true` or use the matching destination. Destination names do not automatically determine Queue vs. Topic.

## 5. Spring Boot + Embedded Artemis Demo: Send Now, Receive Later

This example is meant to **verify delivery delay functionality**, not simulate a production system. It uses:
- Java 17.
- Spring Boot 3.5.16 (Spring Framework 6 line, pinned version for lab reproducibility).
- Embedded Apache ActiveMQ Artemis, requiring no separate broker installation.
- One `JmsTemplate` sending with delay and one `JmsTemplate` receiving synchronously with timeout.

Spring Boot 3.5.16 is the final OSS-supported release of the 3.5 line; use a supported branch and follow advisories for production deployments. This demo pins a specific version so it can be read, compiled, and rerun in a consistent environment.

### 5.1. Project Structure

~~~text
jms-delivery-delay-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/DeliveryDelayDemo.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-delivery-delay-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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

    // Embedded Artemis server needed only for the local example.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.delivery.delay
      persistent: false
~~~

`src/main/java/example/jms/DeliveryDelayDemo.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class DeliveryDelayDemo {

    private static final long DELAY_MS = 2_000L;

    public static void main(String[] args) {
        SpringApplication.run(DeliveryDelayDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(ConnectionFactory connectionFactory) {
        return args -> {
            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.setDefaultDestinationName("demo.delivery.delay");
            sender.setDeliveryDelay(DELAY_MS);

            // TTL > delay to avoid expiring before becoming eligible for delivery.
            sender.setExplicitQosEnabled(true);
            sender.setTimeToLive(15_000L);

            JmsTemplate receiver = new JmsTemplate(connectionFactory);
            receiver.setReceiveTimeout(8_000L);

            long beforeSend = System.currentTimeMillis();
            sender.convertAndSend("delayed-message");

            Message received = receiver.receive("demo.delivery.delay");
            if (!(received instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "No TextMessage received within 8 seconds");
            }

            long eligibleAt = text.getJMSDeliveryTime();
            long receivedAt = System.currentTimeMillis();

            if (eligibleAt < beforeSend + DELAY_MS) {
                throw new IllegalStateException(
                        "Broker did not respect requested delivery delay");
            }
            if (receivedAt < eligibleAt) {
                throw new IllegalStateException(
                        "Message delivered before JMSDeliveryTime");
            }

            System.out.println("BODY=" + text.getText());
            System.out.println("NOT_BEFORE_DELIVERY_TIME=true");
        };
    }
}
~~~

Because `ApplicationRunner.run` declares `throws Exception`, calling `TextMessage.getText()` and `getJMSDeliveryTime()` with checked `JMSException` works cleanly here. Only one runner consumes the queue with no competing listeners, making the experiment reproducible. `persistent: false` is a lab choice and does not demonstrate message survival across broker restarts.

### 5.2. How to Run

From the project directory with JDK 17+ and a Gradle version compatible with the selected Spring Boot plugin. If you have the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Without a Wrapper, using a pre-installed Gradle:

~~~bash
gradle bootRun
~~~

In PowerShell, with the Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

After Spring Boot/Artemis logs, the two lines printed by the application upon passing checks are:

~~~text
BODY=delayed-message
NOT_BEFORE_DELIVERY_TIME=true
~~~

The application does not print raw millisecond counts because those vary per run. Checking `receivedAt >= JMSDeliveryTime` verifies that the measurement does not violate the provider-reported timestamp; `eligibleAt >= beforeSend + DELAY_MS` checks that the header matches the requested delay in a single-host lab clock. **Do not interpret this result as a guarantee that consumers execute at millisecond 2,000**. Across multi-host networks, clock skew can make client/server timestamp comparisons inaccurate; prefer provider-returned headers and clock-synced metrics.

### 5.3. Experimenting with Variants to Understand the Mechanics

- Change `DELAY_MS` to `0L`: the provider may deliver right after send/commit, though delays can still occur.
- Change `sender.setTimeToLive(15_000L)` to `sender.setTimeToLive(1_000L)` while keeping the 2-second delay: the message may expire before being received; the runner throws that no `TextMessage` arrived within timeout. That is an **intentional misconfiguration experiment**, not a Gradle error.
- Change `setDeliveryDelay` to a value greater than the 8-second receive timeout: `receive` may return `null` after timeout because the message is not eligible yet; receiving later requires another `receive` call.
- If swapping Artemis for another broker, verify JMS 2.0 delivery delay support and provider policies first; **having the API method compile does not guarantee runtime implementation support**.

## 6. Standalone Java 17 Exercise: Checking the Delivery Window

You can verify the exact relationship between delivery delay and TTL **without a broker**. Create `DeliveryWindow.java`:

~~~java
public final class DeliveryWindow {
    private DeliveryWindow() {}

    static long earliest(long sentAt, long delayMillis) {
        if (delayMillis < 0) {
            throw new IllegalArgumentException("negative delay");
        }
        return Math.addExact(sentAt, delayMillis);
    }

    static long expiration(long sentAt, long ttlMillis) {
        if (ttlMillis < 0) {
            throw new IllegalArgumentException("negative ttl");
        }
        return ttlMillis == 0L ? 0L
                : Math.addExact(sentAt, ttlMillis);
    }

    public static void main(String[] args) {
        long sentAt = 100_000L;
        long delay = 5_000L;
        long ttl = 12_000L;

        long ready = earliest(sentAt, delay);
        long expires = expiration(sentAt, ttl);

        System.out.println("earliest=" + ready);
        System.out.println("expiration=" + expires);
        System.out.println("windowMillis=" + (expires - ready));

        long tooShort = expiration(sentAt, 3_000L);
        System.out.println("shortTtlCanDeliver="
                + (tooShort > ready));

        System.out.println("noExpiration="
                + (expiration(sentAt, 0L) == 0L));
    }
}
~~~

Compile/run from the file's directory:

~~~bash
javac -encoding UTF-8 DeliveryWindow.java
java DeliveryWindow
~~~

**Deterministic standard output**:

~~~text
earliest=105000
expiration=112000
windowMillis=7000
shortTtlCanDeliver=false
noExpiration=true
~~~

This exercise verifies the **formula**; it does not measure network/broker behavior, solve queue backlogs, or prove provider expiration policies. `Math.addExact` detects `long` addition overflow; in production, TTL/delay values received from APIs should be bounded by business rules before passing them to JMS.

## 7. How Does Delivery Delay Differ from TTL, Priority, and Schedulers?

| Feature | Question It Answers | Outcome |
|---|---|---|
| **Delivery delay** | "When is the earliest the message may be delivered?" | Blocks delivery prior to `JMSDeliveryTime`; does not guarantee exact delivery time. |
| **TTL / expiration** | "Until when is the message considered valid to keep?" | Expires per `JMSExpiration`; may never reach a consumer if TTL is too short. |
| **Priority** | "Which eligible message should be favored first?" | Values 0–9 are provider/policy scheduling hints; cannot override an unmet delivery time. |
| **Persistent delivery** | "How hard must the provider try to store the message?" | Durability is independent of earliest delivery time; does not replace transactions/idempotency. |
| **Redelivery delay** | "After a failed attempt, how long to wait before redelivering?" | Controlled by listener transactions/broker retry policies; distinct from **initial** delay. |
| **Cron/job scheduler** | "At what exact business schedule should work trigger?" | Supports calendars, timezones, rescheduling/cancelling; usually better for long or complex workflows. |

### Examples Where Delivery Delay Should Not Be Used

If a job must run at **08:00 every business day**, adjust for public holidays, and allow users to cancel scheduled jobs, Spring Scheduler, Quartz, or a workflow engine paired with messaging/outbox is usually better suited. JMS delivery delay itself provides no cron contract, timezone calendar, schedule management, or post-send rescheduling.

If you want to wait 10 seconds before **retrying a failed message**, do not manually re-enqueue endlessly onto another Queue just because `setDeliveryDelay` exists. First evaluate broker redelivery delay, max delivery attempts, DLQ, and idempotency; if intentionally using delayed requeueing, prevent infinite loops and preserve delivery count/correlation IDs.

## 8. Transactions: The Clock Does Not Start at Commit

A common design mistake is overlooking that **delivery delay and TTL count from client send time, not transaction commit time** under Jakarta Messaging.

Suppose a JMS transaction runs:

~~~text
10:00:00  producer.send(message); deliveryDelay=5s, TTL=12s
10:00:05  earliest delivery time reached
10:00:07  JMS transaction commits
10:00:07+ message only now becomes visible after commit
10:00:12  TTL expiration
~~~

Here **committing at 10:00:07 does not create a new 10:00:12 delivery time**. The message can reach consumers only after both conditions hold: the delivery time has passed **and** the transaction has committed. If commit happens too late, TTL can expire before consumption.

If the transaction rolls back, messages sent inside it are never committed for delivery; delivery delay does not "rescue" messages from a rolled-back transaction.

A Spring/DB transaction and a JMS transaction are normally **two separate resources**. Do not treat a shared `@Transactional` as guaranteeing DB-broker atomicity without a properly configured transaction manager. For publishes that must follow a DB commit, consider outbox/transaction boundaries instead of using delivery delay as a trick to dodge race conditions.

## 9. Queue and Topic: Same Delay, Different Distribution

### Queue

Messages enter the Queue but become eligible for delivery only after earliest delivery time. Thereafter, the provider selects an eligible consumer per Queue semantics, priority, and policy; consumer count, backlog, and concurrency may still delay processing.

For example, a report-generation command sent at 09:00 with a 30-second delay should not be received before 09:00:30. If workers are busy until 09:05, receiving at 09:05 still satisfies "earliest."

### Topic

Messages published to a Topic fan out to multiple subscriptions. Delivery delay governs **when delivery to consumers occurs**, not turning an event into "an event that only comes into existence when due." Under Jakarta Messaging, a message published to a Topic is added to durable/non-durable subscriptions **only if the subscription exists at send time**.

Consequently, you cannot publish a Topic message delayed by 1 hour, create a subscription 30 minutes later, and expect that new subscription to automatically receive the message. To capture events while consumers are offline, create durable subscriptions ahead of time and verify broker persistence/retention, even for long delays.

### Ordering

Delay can invert the order observed by consumers. For instance, if a producer sends A before B, with A delayed 10 seconds and B delayed 0, B can arrive before A; JMS ordering has explicit exceptions and conditions for delayed messages. Do not rely on absolute send order for data-dependent workflows whenever delays, priorities, or competing consumers are involved. Use business sequences, correlation IDs, idempotency, and domain state when required.

## 10. Fixed Delay vs. Per-Operation Delay

### Fixed Delay: Many Sends Under One Policy

A `JmsTemplate` bean with `setDeliveryDelay(5_000L)` makes sense when an entire "payment reminder after 5 seconds" Queue shares one policy. When you need to send an undelayed command, use a second template with `deliveryDelay=0` or unconfigured delay, avoiding setter calls that mutate a multithreaded singleton.

### Dynamic Delay: Using Scoped ProducerCallback

`JmsTemplate` has no `convertAndSend(payload, delayMillis)` overload. When delay must vary per request, you can use `ProducerCallback` to access `MessageProducer`:

~~~java
// Snippet: jmsTemplate is an injected bean, and the provider supports JMS 2.0.
jmsTemplate.execute("billing.invoice.jobs", (session, producer) -> {
    long oldDelay = producer.getDeliveryDelay();
    try {
        producer.setDeliveryDelay(8_000L);
        producer.send(session.createTextMessage("send-once-later"));
        return null;
    } finally {
        producer.setDeliveryDelay(oldDelay);
    }
});
~~~

Important details:
- `execute(String, ProducerCallback)` provides a template-managed `Session` and `MessageProducer` scoped to the callback.
- Setting delay on the producer inside the callback **does not mutate the singleton `JmsTemplate.getDeliveryDelay()`**; restoring in `finally` prevents leaving stale state if connections/sessions/producers are cached for reuse.
- Some providers do not fully support `getDeliveryDelay`/`setDeliveryDelay`. Test this against your chosen provider/client; unsupported providers may throw an exception.
- Never store the producer/session into a field for use outside the callback; avoid caching a mutable producer and sharing it across threads.
- If delay requirements vary widely, carry high volume, or require cancellation/rescheduling, consider a dedicated scheduling service rather than building core architecture around mutating producers.

Where possible, multiple templates with static policies are easier to test than per-call producer mutation. You can also write an adapter that owns a producer inside a **single** `SessionCallback` and closes the producer at the end; which pattern fits best depends on provider resource management and connection pooling.

### Why MessagePostProcessor Does Not Replace setDeliveryDelay

`MessagePostProcessor` mainly modifies a `Message` created by a converter (correlation ID, application properties, etc.). `JMSDeliveryTime` is set by the provider upon send, so do not write:

~~~java
// Semantically wrong: not the standard way to request delay.
jmsTemplate.convertAndSend("billing.invoice.jobs", "job", m -> {
    m.setJMSDeliveryTime(System.currentTimeMillis() + 8_000L);
    return m;
});
~~~

The header setter exists because providers need an API to populate the field; **applications must not use it as a standard scheduling tool**. The right way is configuring delay on the producer/template, or using a broker's vendor scheduling extension when vendor lock-in is accepted.

## 11. Spec Gaps and Feature Differences Across Providers

A Java class implementing `jakarta.jms.MessageProducer` is not proof that every JMS 2.0 feature works completely on every broker/client/version.

| Provider / Send Method | Notes |
|---|---|
| **Apache ActiveMQ Artemis** | Supports scheduled delivery; Java JMS client implements `setDeliveryDelay`. For Artemis-specific setups, the broker also supports the `_AMQ_SCHED_DELIVERY` property for a target **epoch millisecond**; this is an extension, not a standard JMS property name. |
| **Apache ActiveMQ Classic** | Some branches/versions implement only part of JMS 2.0; per ActiveMQ Classic's feature matrix, `MessageProducer.setDeliveryDelay` has limitations and may throw `UnsupportedOperationException`. Verify the **exact version**, never assume it works just because it compiles. |
| **Qpid JMS / AMQP 1.0 / managed brokers** | Mapping `setDeliveryDelay` to schedulers/AMQP annotations depends on client and broker capabilities; test end-to-end over the real protocol. |
| **Other JMS providers** | Check compatibility matrices/JMS versions, scheduler configs, quotas, and permissions; verify TTL, timestamp, and delivery time in test sends. |

Artemis extension example (non-portable):

~~~java
// Snippet specific to Artemis when intentionally using its vendor property.
long deliverAtEpochMillis = System.currentTimeMillis() + 5_000L;
jmsTemplate.convertAndSend("billing.invoice.jobs", "artemis-job", m -> {
    m.setLongProperty("_AMQ_SCHED_DELIVERY", deliverAtEpochMillis);
    return m;
});
~~~

This sets Artemis's proprietary scheduling property, **not `setJMSDeliveryTime`**. Use only one tested mechanism—either standard or provider-specific; avoid setting both `JmsTemplate.deliveryDelay` and `_AMQ_SCHED_DELIVERY` on the same message because precedence can vary by version and protocol mapping.

When migrating brokers, prefer standard `MessageProducer.setDeliveryDelay` on providers with true support, and remove vendor extensions when no longer appropriate. Do not confuse broker scheduled delivery with broker delayed retry: configuration and observability can differ completely.

## 12. Slow Systems, Offline Consumers, and the No-Exact-Time Principle

The `5_000` in `setDeliveryDelay(5_000L)` is only a **lower bound**. Reasons a message can arrive later:
- Broker backlog or scheduler lacking high-precision deadlines.
- Uncommitted message, paused/locked destination, or no matching consumer/subscription.
- Queue priorities, selectors, load balancing, throttling, TTL/expiration, or connection limits.
- Network delays, client/broker clock skew, broker maintenance, failover, or disconnects.
- Busy consumers or exhausted thread pools/handlers.

Designs should track both `JMSDeliveryTime` and **when the consumer actually starts processing**. If SLAs demand jobs start within a tight upper bound, invest in capacity planning, monitoring/alerting, overload strategies, and sometimes a dedicated scheduler. JMS delivery delay offers no hard real-time contract.

### Message Loss and Duplicate Processing

A delayed message with `DeliveryMode.NON_PERSISTENT` can be lost if the broker fails; a persistent message can survive failures subject to broker persistence and policies. A producer timeout on send does not prove the broker never received it; retries can create duplicates. Attach event/job IDs, verify domain state, and design idempotent consumers.

Delay is not a system-wide "execute exactly once" solution. Consumers still need transactions, proper acknowledgement/redelivery, dead-letter policies, and deduplication.

## 13. Real-World Observability and Testing

For production systems, test against **real broker/client/transport versions**, beyond the embedded demo:

| Test Case | Evidence to Record |
|---|---|
| Delay = 0 | Receivable right after send/commit with no configured delay blocking it. |
| Delay = 3,000 ms | `JMSDeliveryTime` matches target; consumer does not receive **before** that time. |
| Delay > receive timeout | Short receive returns `null`; a subsequent receive retrieves it once eligible. |
| TTL < delay | Message may expire undelivered; check expiry queue/metrics. |
| TTL > delay | Valid delivery window exists; verify expiration as well. |
| Late transaction commit | Delivery time does not add delay **a second time** from commit; no delivery before commit. |
| Transaction rollback | Uncommitted messages are never delivered. |
| Late topic subscription | Do not expect a subscription created after send to receive historical messages. |
| Failover/restart | Verify persistence of scheduled messages and timestamps after recovery. |
| Unsupported provider | Ensure the app fails clearly or uses a designed fallback rather than silently dropping delay. |

Log/record metrics across these fields:
- `JMSMessageID`/business event ID/correlation ID.
- `JMSDeliveryTime` and `JMSExpiration` (epoch millis).
- Broker accept time, consumer receive time, processing duration, and backlog/scheduled counts.
- Requested delay, Queue/Topic type, transaction commit latency, and redelivery counts.

Never log payloads containing sensitive data, tokens, or passwords. To correlate timestamps between clients and brokers, synchronize clocks via NTP and log in UTC; convert timezones only in presentation layers.

## 14. Common Mistakes

| Mistake | Why It Is Wrong | Right Approach |
|---|---|---|
| "A 5-second delay means execute at exactly 5 seconds." | JMS only guarantees **not delivering earlier** than the time. | Write SLAs with tolerances; measure drift from earliest to actual consumption. |
| "`setDeliveryDelay` delays the `send` call itself." | Producer sends to the broker immediately; delivery to consumers is deferred by contract. | Distinguish send acceptance from consumer delivery. |
| "TTL 3s and delay 10s means receive at second 10." | The message may expire at second 3. | Choose TTL longer than delay + backlog processing headroom, or TTL 0 when appropriate. |
| "`JmsTemplate.setDeliveryDelay` defaults to 0." | Spring defaults to **-1** so no setting is passed to the provider. | Check `getDeliveryDelay()`; distinguish `-1` sentinel from explicit `0`. |
| "Must enable `explicitQosEnabled` for delivery delay." | That flag governs the template's delivery mode/priority/TTL. | Configure delay separately; test the API on your real provider. |
| "Setting `JMSDeliveryTime` on `Message` schedules it." | That header is set by the provider at send time. | Use `setDeliveryDelay` on producer/template. |
| "JMS `send` has a per-message delay overload." | The classic API has mode/priority/TTL overloads, **not** a delay argument. | `MessageProducer.setDeliveryDelay` or an appropriate callback adapter. |
| "Delay restarts counting on transaction commit." | The spec counts from send time. | Account for delay, TTL, and commit duration together. |
| "Topic message published today reaches a subscriber created 1 hour later." | Subscriptions must exist when the message is published per spec rules. | Design durable subscriptions/retention and provision before sending. |
| "If it says JMS 2.0, the provider surely supports it." | Implementations may be partial. | Test the feature on the actual broker/client version. |
| "Mutating a singleton's setter before each send is safe." | Thread race conditions occur. | Use per-policy templates or properly scoped callbacks. |
| "Delivery delay replaces retry/backoff." | Delay applies to initial send, not retry/redelivery/DLQ handling. | Design retries with max attempts, DLQ, and idempotency. |

## 15. Self-Check Questions

**Q1.** A message is sent at 14:00:00.000 with an 8-second delay and 30-second TTL. What is the earliest time the provider may deliver it, and when does it expire?

**Answer:** Earliest 14:00:08.000; expiration 14:00:30.000. This is the eligible delivery window, not a promise to finish processing before 14:00:30.

**Q2.** If TTL = 2 seconds and delivery delay = 5 seconds, can we guarantee a consumer receives it after 5 seconds?

**Answer:** No. The message may already expire before its earliest delivery time. Fix TTL/expiry policies or choose another scheduling approach.

**Q3.** After sending at 10:00:00 with a 10-second delay, the transaction commits at 10:00:12. Must the message wait until 10:00:22?

**Answer:** No. Per spec, earliest is 10:00:10; after the 10:00:12 commit the message becomes eligible immediately if unexpired and broker/consumers are ready.

**Q4.** Why not use `message.setJMSDeliveryTime(now + delay)`?

**Answer:** `JMSDeliveryTime` is populated by the provider on send; clients do not use that setter as a scheduling API. Use `MessageProducer#setDeliveryDelay`, `JMSProducer#setDeliveryDelay`, or `JmsTemplate#setDeliveryDelay`.

**Q5.** Suppose `JmsTemplate.setDeliveryDelay(5000)` is set with `setExplicitQosEnabled(false)`. Does Spring necessarily ignore the delay?

**Answer:** No. Delivery delay is managed independently of the template's three explicit QoS properties; you still must ensure the provider implements `MessageProducer#setDeliveryDelay`.

**Q6.** A producer publishes a Topic event, and a new subscriber is created before the delay expires. Will that subscriber definitely receive the event?

**Answer:** No. Under Jakarta Messaging, durable/non-durable subscription membership applies when the message is published/sent, not when the delivery delay elapses.

**Q7.** When the broker redelivers a message after a listener failure, does `setDeliveryDelay` on the producer re-apply a delay to each retry?

**Answer:** There is no such guarantee. Redelivery delay/rollback/retry is a separate broker/consumer container policy that must be checked and configured specifically.

## 16. Implementation Checklist

- [ ] Clearly understood that "earliest delivery time" does not mean an exact execution timestamp.
- [ ] Verified that the producer/client/broker genuinely support JMS 2.0 delivery delay.
- [ ] Used `setDeliveryDelay` on producer/template rather than editing `JMSDeliveryTime` directly.
- [ ] Configured a sensible TTL policy that does not expire before earliest delivery time.
- [ ] Verified transaction send/commit/rollback and publisher/consumer behavior.
- [ ] When using Topics, provisioned required subscriptions before publishing.
- [ ] Avoided mutating setters on a singleton `JmsTemplate` across concurrent requests.
- [ ] Tested with real Queues/Topics, TLS, broker restarts, backlogs, and unsupported-provider behavior.
- [ ] Kept retry/DLQ and idempotency separate from initial delivery delay.
- [ ] Added metrics/logs for `JMSDeliveryTime`, actual receive time, and delay drift.

## 17. Official References

- [Jakarta Messaging 3.1 Specification — JMSDeliveryTime, TTL, and delivery delay](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Jakarta Messaging 3.1 — MessageProducer#setDeliveryDelay](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer).
- [Jakarta Messaging 3.1 — Message#getJMSDeliveryTime](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message).
- [Spring Framework 6.2.14 — JmsTemplate#setDeliveryDelay](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework 6.2 — Using JmsTemplate and QoS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Boot 3.5 — Artemis and JMS configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Apache ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages).
- [Apache ActiveMQ Classic — JMS 2.0 and Jakarta Messaging feature support](https://activemq.apache.org/components/classic/documentation/jms2).
