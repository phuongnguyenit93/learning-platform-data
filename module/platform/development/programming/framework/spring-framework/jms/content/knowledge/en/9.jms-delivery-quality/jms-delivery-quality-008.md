# Disabling Message ID or Timestamp: Purpose and Trade-Offs in Spring JMS

## Learning Objectives

In Jakarta Messaging (JMS), when a producer sends a message, the provider usually populates two header fields: **`JMSMessageID`** and **`JMSTimestamp`**. Generating IDs and timestamps can introduce some processing overhead, especially at very high volumes of small messages. The JMS specification lets applications **hint to the provider not to generate** one or both of these fields for potential optimization.

This lesson covers in full:

1. The roles of `JMSMessageID` and `JMSTimestamp`, and when they are populated.
2. The two options `MessageProducer.setDisableMessageID` and `setDisableMessageTimestamp`, and their nature as a **hint** rather than a mandatory command.
3. The corresponding setters in Spring `JmsTemplate`: `setMessageIdEnabled` and `setMessageTimestampEnabled`, noting the inverted boolean logic.
4. What can and cannot be optimized, and what remains unchanged regarding persistence, QoS, TTL, expiration, transactions, and redelivery.
5. The cost of losing metadata when using request-reply, correlation IDs, tracing, monitoring, DLQs, auditing, and latency measurement.
6. A Java 17 example with Spring Boot and ActiveMQ Artemis, plus an experiment comparing standard settings against hint-disabled settings.
7. A decision checklist and performance benchmark plan before enabling optimizations in production.

> **Key point:** Disabling JMS message ID/timestamp is an **optimization hint** to the provider. If the provider honors it, message ID becomes `null` and/or timestamp becomes `0`. If the provider ignores it, both headers still receive normal values. Never write business logic assuming the provider is required to honor the hint.

## 1. What Are the Two Standard Headers For?

### 1.1. `JMSMessageID`

`JMSMessageID` is a header field **assigned by the JMS provider at send time**. Read it via:

~~~java
String id = message.getJMSMessageID();
~~~

When enabled, the ID typically carries an `ID:` prefix and identifies the sent message. According to the Jakarta Messaging 3.1 specification, uniqueness scope is provider-defined—at minimum unique within a provider installation; **it is not guaranteed globally unique across all brokers and vendors**.

Common use cases for this header:

- Correlating producer, broker, and consumer logs.
- Searching for a specific message in admin tools.
- Tracking broker redeliveries of the same JMS message.
- Recording trails for DLQs, re-drives, and duplicate investigations.
- Request-reply correlation, where responses set `JMSCorrelationID` to the request's ID.

**Do not equate `JMSMessageID` with a business ID.** An `OrderCreated` event may be published twice as two distinct JMS messages, each with its own ID; therefore business deduplication requires an independent `eventId` or business key.

### 1.2. `JMSTimestamp`

`JMSTimestamp` is a `long` in epoch milliseconds indicating **when the message was handed off to the provider to be sent**, read via:

~~~java
long timestamp = message.getJMSTimestamp();
~~~

For synchronous sends, the specification states that when the send call finishes, the provider-set timestamp lies between when send was called and when it returned. That does **not** guarantee it represents:

- When the business event actually occurred.
- When the sending transaction committed.
- When the broker finished writing to disk or sending over the network.
- When the consumer actually received or processed the message.

For example, an event is saved to an outbox at `10:00`, sent to JMS by a relay at `10:15`, and received by a consumer at `10:15:02`. In that case `eventCreatedAt`, `JMSTimestamp`, and `receivedAt` are **three distinct timestamps**.

A commonly seen approximation formula:

~~~java
long timestamp = message.getJMSTimestamp();
if (timestamp > 0L) {
    long ageMillis = System.currentTimeMillis() - timestamp;
    // This is an approximate age, not an exact end-to-end measurement.
}
~~~

Across different machines, clock skew also affects results. If timestamp is `0` because the hint was honored, this formula **is no longer valid**.

### 1.3. Fields That Must Not Be Confused

| Field | Who Sets It | Meaning |
|---|---|---|
| `JMSMessageID` | Provider at send time | JMS message identifier |
| `JMSTimestamp` | Provider at send time | Handoff timestamp to the provider |
| `JMSCorrelationID` | Usually set by application | Links request-response or a workflow |
| `JMSExpiration` | Provider computed from time-to-live | Message expiration timestamp |
| `JMSDeliveryTime` | Provider computed from delivery delay | Earliest eligible delivery time |
| `JMSRedelivered` | Provider prior to delivery | Indicator that the message may be redelivered |
| `JMSXDeliveryCount` | Provider, property on receive | Number of provider delivery attempts |
| `eventId` | Application property | Stable logical ID for idempotency |
| `createdAt` | Business payload/property | Business event creation timestamp |
| `traceparent` | Tracing propagation | Links spans across services |

The two options in this lesson relate directly **only to `JMSMessageID` and `JMSTimestamp`**. There is no basis to infer "disable all headers," "disable TTL," or "disable redelivery."

## 2. Why Do These Two Optimization Options Exist?

Generating a `JMSMessageID` may require allocating sequence numbers, building provider-specific ID structures, and writing/transmitting extra bytes. Generating a timestamp requires reading the clock and transmitting time metadata. Under heavy load, some providers can reduce overhead if the application declares it does not use those two pieces of metadata.

JMS offers two **producer hints**:

~~~java
producer.setDisableMessageID(true);
producer.setDisableMessageTimestamp(true);
~~~

Meaning: "The application does not depend on those two headers; the provider **may** omit generating them."

~~~text
                 MessageProducer
                       |
              disable ID = true?
              disable time = true?
                       |
                       v
                    Provider
                   /        \
           Honors hint    Ignores hint
                 |              |
          ID = null         ID = "ID:..."
          Time = 0          Time = epoch millis
                   \        /
                    Consumer
~~~

**The two hints are independent.** A provider may honor disabling ID while ignoring disabling timestamp, or vice versa. The JMS spec promises no specific speedup; CPU, latency, message size, and throughput impact depend on the implementation.

### 2.1. Default Values

Without further configuration:

- `setDisableMessageID(false)`: ID generation is enabled.
- `setDisableMessageTimestamp(false)`: timestamp generation is enabled.
- Spring `JmsTemplate` defaults to `messageIdEnabled=true` and `messageTimestampEnabled=true`.

Thus, in most standard applications, both headers remain populated, aiding tracing and inspection.

### 2.2. Rules When Provider Honors vs. Ignores

| Hint | If Provider Honors | If Provider Ignores |
|---|---|---|
| Disable message ID | `getJMSMessageID() == null` | A normal ID is assigned |
| Disable timestamp | `getJMSTimestamp() == 0L` | A normal timestamp is assigned |

Outcomes from either branch in this table are compliant with the JMS standard. Therefore, assertions like the following are **not portable**:

~~~java
producer.setDisableMessageID(true);
producer.setDisableMessageTimestamp(true);
producer.send(message);

// Must not assume every provider guarantees:
assert message.getJMSMessageID() == null;
assert message.getJMSTimestamp() == 0L;
~~~

Reading **the producer's own getters** also does not prove the provider performed the optimization:

~~~java
boolean requestedIdDisabled = producer.getDisableMessageID();
boolean requestedTimeDisabled =
        producer.getDisableMessageTimestamp();
~~~

They reflect the producer's setting/hint. To check the actual effect, read the headers on a sent message or when received by a consumer.

## 3. Using Plain Jakarta Messaging API

### 3.1. Classic API with `MessageProducer`

~~~java
// Snippet inside a method with a valid ConnectionFactory.
// The Queue must exist or the broker must allow auto-create.
try (Connection connection = connectionFactory.createConnection();
     Session session =
             connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

    Queue queue = session.createQueue("lesson.headers.hinted");

    try (MessageProducer producer = session.createProducer(queue)) {
        producer.setDisableMessageID(true);
        producer.setDisableMessageTimestamp(true);

        TextMessage message =
                session.createTextMessage("hello-jms");
        message.setStringProperty("eventId", "evt-100");

        producer.send(message); // synchronous send
        System.out.println(
                "id=" + message.getJMSMessageID());
        System.out.println(
                "timestamp=" + message.getJMSTimestamp());
    }
}
~~~

Corresponding imports from `jakarta.jms`: `Connection`, `ConnectionFactory`, `Session`, `Queue`, `MessageProducer`, and `TextMessage`. This is a **snippet**, not a standalone runnable class; it needs a broker and `ConnectionFactory`.

With a provider honoring both hints, the output *might* be:

~~~text
id=null
timestamp=0
~~~

With a provider ignoring hints, ID will look like `ID:...` and timestamp will typically be positive. Both outcomes conform to the spec. Calling `connection.start()` is unnecessary just to **send**; `start()` is primarily required to enable receiving messages.

### 3.2. Scope of Effect

Both `setDisable...` methods are settings on a **`MessageProducer` instance** and affect messages sent by that producer. They do not alter policies for the entire broker, entire queue, or every producer on the same connection.

~~~text
Producer A [disable ID=false] ─┐
                               ├──► Queue orders
Producer B [disable ID=true] ──┘
                               |
                Consumer may see both message shapes:
                  normal ID and null ID
~~~

One producer on one session can send multiple messages sequentially. However, a `Session` is a **single-thread-at-a-time** unit; never share the same session/producer concurrently across threads.

### 3.3. Simplified API with `JMSContext` and `JMSProducer`

~~~java
// Snippet inside a method with a ConnectionFactory.
try (JMSContext ctx =
        connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue queue = ctx.createQueue("lesson.headers.hinted");

    ctx.createProducer()
       .setDisableMessageID(true)
       .setDisableMessageTimestamp(true)
       .send(queue, "hello-context");
}
~~~

`JMSProducer` exposes getters for the corresponding hints and supports method chaining. Semantically it is still a **hint**, not a mandate forcing header removal. `JMSContext` encapsulates an underlying session and must not be stored in a singleton field shared across request threads.

### 3.4. Do Not Set Both Headers Directly Before Send

~~~java
// Do not use these setters to force disabling ID/timestamp:
message.setJMSMessageID(null);
message.setJMSTimestamp(0L);
producer.send(message);
~~~

`setJMSMessageID` and `setJMSTimestamp` exist so the **provider** can populate headers at send time, not as application APIs to control QoS. Values assigned prior to send may be ignored/overwritten by the provider per specification.

## 4. Corresponding Settings on Spring `JmsTemplate`

Spring provides two setters named with **Enabled**:

~~~java
template.setMessageIdEnabled(false);
template.setMessageTimestampEnabled(false);
~~~

This is the easiest place to make a mistake because the boolean direction is **inverted** compared to the Java JMS producer:

| Intent | Jakarta `MessageProducer` | Spring `JmsTemplate` |
|---|---|---|
| Keep message ID | `setDisableMessageID(false)` | `setMessageIdEnabled(true)` |
| Hint to disable ID | `setDisableMessageID(true)` | `setMessageIdEnabled(false)` |
| Keep timestamp | `setDisableMessageTimestamp(false)` | `setMessageTimestampEnabled(true)` |
| Hint to disable timestamp | `setDisableMessageTimestamp(true)` | `setMessageTimestampEnabled(false)` |

### 4.1. Declaring Once in Configuration

~~~java
@Configuration
public class JmsConfig {
    @Bean
    JmsTemplate compactJmsTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate t = new JmsTemplate(connectionFactory);
        t.setPubSubDomain(false); // Queue
        t.setMessageIdEnabled(false);
        t.setMessageTimestampEnabled(false);
        return t;
    }
}
~~~

This is a configuration class requiring imports for `jakarta.jms.ConnectionFactory`, `JmsTemplate`, `@Bean`, and `@Configuration`. In Spring Boot apps, you can rely on auto-configuration for default cases and declare manual beans when specialized policies are needed.

Spring documents `JmsTemplate` as **thread-safe after configuration**. Therefore, set these hints **before multiple services use the template**, never mutating setters per request.

### 4.2. Anti-Pattern: Mutating Shared Configuration While Sending

~~~java
// WRONG: sharedTemplate is called by multiple threads.
void sendForEvent(boolean needId, String payload) {
    sharedTemplate.setMessageIdEnabled(needId);
    sharedTemplate.convertAndSend("events", payload);
}
~~~

Thread A sets `false`, Thread B sets `true`, and then Thread A's send may pick up B's setting. Never treat a setter + send pair as atomic. Configure **two template beans** for two fixed policies.

### 4.3. Two Beans for Two Policies

~~~java
@Bean("fullHeadersTemplate")
JmsTemplate fullHeadersTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setMessageIdEnabled(true);
    t.setMessageTimestampEnabled(true);
    return t;
}

@Bean("leanHeadersTemplate")
JmsTemplate leanHeadersTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setMessageIdEnabled(false);
    t.setMessageTimestampEnabled(false);
    return t;
}
~~~

These methods are snippets inside a `@Configuration` class. Both templates can share the same `ConnectionFactory` because hints live at the **producer/send policy** level, not broker identity.

When multiple beans of type `JmsTemplate` exist, inject using `@Qualifier("leanHeadersTemplate")` or configure `@Primary` clearly to avoid ambiguity.

### 4.4. Is `setExplicitQosEnabled(true)` Needed?

You do not need to enable explicit QoS **just to use these two hints**. `setExplicitQosEnabled(true)` controls **`deliveryMode`**, **`priority`**, and **`timeToLive`** in `JmsTemplate`'s send call. Message ID/timestamp are independent producer hint settings.

If you simultaneously change persistence mode, TTL, priority, pooling, or transactions while measuring throughput, you will not know where any gain came from. Benchmark one variable at a time.

## 5. Potential Performance Benefits

### 5.1. Overhead That May Be Reduced

The provider might:

- Skip generating message IDs (e.g., managing implementation-specific sequences/metadata).
- Skip fetching timestamps to populate headers.
- Reduce header bytes serialized and sent over the network or written in provider format.
- Reduce some header-processing CPU under very high small-message rates.

These savings can matter in telemetry/metrics/event systems with **small payloads and high throughput**. However, if the real bottleneck is broker disk I/O, network, transaction latency, TLS, DB, or message conversion, toggling these two headers may yield **no measurable gain**.

The JMS standard does not require providers to optimize and promises no minimum throughput percentage. A provider may keep maintaining internal metadata and ignore the hints. "Optimization configured" does not equal "optimization actually happened."

### 5.2. Things You Must Never Infer

| Statement | True or False? |
|---|---|
| Disabling `JMSMessageID` means the broker does not know which message is acked | **False.** The broker can maintain its own internal identifiers. |
| Disabling `JMSTimestamp` means messages never expire | **False.** TTL/`JMSExpiration` is a separate mechanism. |
| Both hints switch delivery mode from `PERSISTENT` to `NON_PERSISTENT` | **False.** They never change delivery mode. |
| Disabling ID disables duplicates or redeliveries | **False.** Acks/transactions/retries work independently. |
| Headers can be absent if the provider honors the hints | **True.** ID `null`, timestamp `0`. |
| Successful send proves the consumer processed the message | **False.** Requires acks/transactions, broker metrics, or business confirmation. |
| Hints may be ignored by the provider | **True.** That is standard semantics. |

### 5.3. Hint Optimization Does Not Replace Tuning

Optimizations that often yield much larger gains include: shrinking payloads, using efficient message converters, proper caching/pooling, avoiding excessive connection/session creation, tuning persistent stores, adjusting send/consumer concurrency, provider-supported batching, and reducing network hops. Each has its own trade-offs and must be measured on real workloads.

## 6. Trade-Offs of Disabling `JMSMessageID`

### 6.1. Observability and Incident Investigation

When ID is `null`, log tools and broker consoles cannot use `JMSMessageID` to join producer logs with consumer logs. Tracking a specific message across queues, DLQs, retries, and re-drives becomes harder.

Example across two delivery attempts:

~~~text
Normal:
  messageId=ID:abc, deliveryCount=1
  messageId=ID:abc, deliveryCount=2

ID disabled and provider honors hint:
  messageId=null, deliveryCount=1
  messageId=null, deliveryCount=2
~~~

`JMSRedelivered` and `JMSXDeliveryCount` remain useful, yet missing IDs make correlating **one physical message** across delivery attempts harder.

### 6.2. Request-Reply Relying on JMSMessageID Can Break

A common request-reply pattern:

~~~text
Requester sends message R
  Request.JMSMessageID = "ID:R100"

Responder receives R, builds reply:
  Reply.JMSCorrelationID = Request.JMSMessageID

Requester receives reply and matches:
  Reply.JMSCorrelationID == "ID:R100"
~~~

If the request has `JMSMessageID=null`, the responder has no ID to copy into the correlation field, and the requester loses its traditional match key. **Do not disable ID** if your request-reply protocol uses `JMSMessageID`. To use application-controlled correlation, design both sides:

~~~java
// Inside a request's MessageCreator.
String requestId = java.util.UUID.randomUUID().toString();
message.setJMSCorrelationID(requestId);
~~~

Responder and requester must agree on using the same correlationId. `JMSCorrelationID` is distinct from `JMSMessageID` and typically set explicitly by the application; disabling ID **does not disable the correlation header**.

### 6.3. Business Idempotency Differs from Broker ID

`JMSMessageID` helps identify redeliveries of **the same JMS message**, but is insufficient against duplicate publishes by the producer:

~~~text
Producer sends eventId=evt-900 attempt 1:
   JMSMessageID=ID:111

Producer sends same eventId=evt-900 attempt 2:
   JMSMessageID=ID:222
~~~

Consumers can receive both and execute business logic twice. The durable solution is a stable `eventId`/business key, database unique constraints, idempotency records, and proper transactions. When disabling ID, make sure `eventId` is present and preserved across retries/forwards if infrastructure supports it.

### 6.4. No JMS ID Does Not Mean No Broker Internal ID

The broker may still manage queue sequences, journal records, delivery tags, or internal identities for acks/retries. JMS does not dictate internal structures. You may assert only that **the `JMSMessageID` header can be `null`**, not that every ID on the broker disappears.

## 7. Trade-Offs of Disabling `JMSTimestamp`

### 7.1. Do Not Interpret `0` as "Sent in 1970"

If the provider honors the hint and `getJMSTimestamp()==0L`, treat it as **no timestamp available**. Age-calculation code must check:

~~~java
long sentAt = message.getJMSTimestamp();

if (sentAt > 0L) {
    long approximateAge = System.currentTimeMillis() - sentAt;
    System.out.println("approxAgeMs=" + approximateAge);
} else {
    System.out.println("JMSTimestamp unavailable");
}
~~~

If you blindly pass `0` to `Instant.ofEpochMilli(0)`, dashboards can display `1970-01-01`, misleading operators into thinking messages are 56 years old.

### 7.2. Time Tracing Needs to Distinguish Milestones

~~~text
10:00:00  business event occurs (eventCreatedAt)
10:15:00  outbox relay sends JMS (JMSTimestamp if enabled)
10:15:02  consumer receives (receivedAt)
10:15:03  consumer finishes processing (processedAt)
~~~

Each milestone means something different. Keeping timestamp enabled aids correlating send time, though it does not replace business timestamps. If disabled, the application can supply `createdAt`, `publishedAt`, or suitable trace spans along with clock-sync policies.

Drawback: setting a custom `publishedAtEpochMs` property via `System.currentTimeMillis()` still reads the clock and adds bytes to the message; that **can negate the expected savings** from disabling the standard header. Add custom timestamps only when genuinely required.

### 7.3. TTL/Expiration Is Not Disabled

The JMS standard computes expiration from **time-to-live** and send time:

~~~text
JMSExpiration = sendTime + timeToLive
~~~

If TTL is `0`, `JMSExpiration=0` means no expiration. If TTL is non-zero, the provider must still enforce expiry per spec/policy **even when `JMSTimestamp` is disabled**.

Example:

~~~java
producer.setDisableMessageTimestamp(true);
producer.setTimeToLive(5_000L);
producer.send(message);
~~~

If the provider honors the hint, `getJMSTimestamp()` may be `0`, yet `JMSExpiration` still reflects the deadline computed from TTL. **Disabling timestamp is not a way to disable TTL.** In transactions, TTL counts from send time, not commit time.

### 7.4. Delivery Delay Is Also Independent

`JMSDeliveryTime` represents the earliest time a message may be delivered based on delivery delay. This header is separate from `JMSTimestamp`; disabling timestamp does not disable scheduled delivery. Test against your specific broker/provider if your app combines delay and expiry.

### 7.5. Without Timestamp: Observe Differently

- Log producer send-call start/end to measure call cost.
- Log consumer received/processed timestamps using local clocks.
- Propagate trace context `traceparent` if using distributed tracing.
- For end-to-end SLAs from business creation, use a well-defined `eventCreatedAt`.
- For multi-host latency, account for clock skew and measurement methods.
- Never treat an absent or `0` timestamp as an actual send time.

## 8. Four Configurations to Distinguish

| Case | `messageIdEnabled` | `messageTimestampEnabled` | Main Trade-Off |
|---|---|---|---|
| A: default | `true` | `true` | Retains identity and send timing. |
| B: hint disable ID | `false` | `true` | May cut ID overhead; complicates ID-based correlation. |
| C: hint disable timestamp | `true` | `false` | May cut time overhead; complicates message age checks. |
| D: hint disable both | `false` | `false` | Largest potential optimization; loses both traces. |

**Only judge effectiveness by benchmarking.** Sharing a queue name does not force all producers to enable/disable identically; consumers must handle both present and absent headers during gradual rollouts.

## 9. Runnable Demo: Java 17, Spring Boot, Artemis

This demo has two statically configured templates: one keeping ID/timestamp, one hinting to disable them. Each template sends a `TextMessage` to its own Queue, and two listeners inspect raw headers. The provider is not forced to honor the hints; output is interpreted under both valid branches.

### 9.1. Preparing a Local Broker

Requires JDK 17+, Maven 3.9+, and Docker. Start a test Artemis broker on `localhost:61616`:

~~~bash
docker run --detach --rm --name jms-header-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Verify the broker started:

~~~bash
docker logs jms-header-lab
~~~

This Artemis image is for demo use; default broker policy typically allows auto-creating queues. In environments where auto-create is disabled, provision queues beforehand. Never use demo credentials in production.

Structure:

~~~text
jms-header-lab/
├── pom.xml
└── src/main/
    ├── java/example/JmsHeaderLabApplication.java
    └── resources/application.properties
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-header-lab</artifactId>
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

### 9.3. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 9.4. `JmsHeaderLabApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsHeaderLabApplication {

    private static final String FULL_QUEUE = "lesson.header.full";
    private static final String HINT_QUEUE = "lesson.header.hinted";

    public static void main(String[] args) {
        SpringApplication.run(JmsHeaderLabApplication.class, args);
    }

    @Bean("fullHeadersTemplate")
    JmsTemplate fullTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        template.setMessageIdEnabled(true);
        template.setMessageTimestampEnabled(true);
        return template;
    }

    @Bean("leanHeadersTemplate")
    JmsTemplate leanTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        template.setMessageIdEnabled(false);
        template.setMessageTimestampEnabled(false);
        return template;
    }

    @Bean("demoListenerFactory")
    DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner publish(
            @Qualifier("fullHeadersTemplate") JmsTemplate full,
            @Qualifier("leanHeadersTemplate") JmsTemplate hinted,
            HeaderProbe probe) {
        return args -> {
            full.send(FULL_QUEUE, session ->
                    sample(session, "evt-full", "req-full"));
            hinted.send(HINT_QUEUE, session ->
                    sample(session, "evt-hinted", "req-hinted"));

            System.out.println("sentTwoMessages=true");
            System.out.println("receivedBoth=" + probe.awaitBoth());
        };
    }

    private static TextMessage sample(
            Session session, String eventId, String requestId)
            throws JMSException {
        TextMessage m = session.createTextMessage("payload:" + eventId);
        m.setStringProperty("eventId", eventId);
        m.setJMSCorrelationID(requestId);
        return m;
    }

    @Component
    public static class HeaderProbe {
        private final CountDownLatch received = new CountDownLatch(2);

        @JmsListener(destination = FULL_QUEUE,
                     containerFactory = "demoListenerFactory")
        public void onFull(TextMessage message) throws JMSException {
            print("full", message);
        }

        @JmsListener(destination = HINT_QUEUE,
                     containerFactory = "demoListenerFactory")
        public void onHinted(TextMessage message) throws JMSException {
            print("hinted", message);
        }

        private void print(String source, TextMessage message)
                throws JMSException {
            boolean idPresent = message.getJMSMessageID() != null;
            boolean timestampPresent = message.getJMSTimestamp() > 0L;

            System.out.printf(
                    "%s idPresent=%b timestampPresent=%b "
                  + "eventId=%s correlationId=%s%n",
                    source, idPresent, timestampPresent,
                    message.getStringProperty("eventId"),
                    message.getJMSCorrelationID());

            received.countDown();
        }

        boolean awaitBoth() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }
}
~~~

**Explanation:**

- One `public` class matching the filename and one nested `@Component` listener.
- Both `@Bean JmsTemplate` instances are configured at startup; no setters are called from sending threads.
- `MessageCreator` creates messages with application-chosen `eventId` and `JMSCorrelationID`; those fields can exist even when `JMSMessageID` is null.
- The listener receives raw `jakarta.jms.TextMessage` to check actual headers after broker delivery.
- `CountDownLatch` is for demo observation only, never as a production ACK/dedup mechanism.
- `setSessionTransacted(true)` controls listener transactions independently of the two producer hints.
- Queues must exist or the broker must allow auto-creation; calling `send` alone does not guarantee physical queue resources exist.

### 9.5. Running and Interpreting Results

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If both hints are honored by the provider, an **example** of the lines printed by the application is:

~~~text
full idPresent=true timestampPresent=true eventId=evt-full correlationId=req-full
hinted idPresent=false timestampPresent=false eventId=evt-hinted correlationId=req-hinted
sentTwoMessages=true
receivedBoth=true
~~~

**No stdout order is guaranteed:** listeners run asynchronously; `full/hinted` lines can appear before or after `sentTwoMessages` and swap positions. The console also shows Spring Boot/Artemis logs. If the provider ignores one or both hints, `hinted idPresent` and `timestampPresent` can still be `true`. That remains spec-compliant behavior, not proof of wrong setter code.

To inspect exact numbers, `HeaderProbe.print` can print:

~~~java
System.out.printf("id=%s timestamp=%d%n",
        message.getJMSMessageID(),
        message.getJMSTimestamp());
~~~

Inspection must happen **after the message is received** or after synchronous send. Do not read ID inside `MessageCreator` to draw conclusions, because that callback builds the message **before sending**.

When finished:

~~~bash
docker stop jms-header-lab
~~~

The lab container uses `--rm` with no mounted volume; stopping it discards broker data. Never use this test config where durability is required.

## 10. Should You Use Custom Timestamps or IDs Instead?

### 10.1. Business Event ID

For systems requiring idempotency, a producer-assigned `eventId` is better than a provider ID for **logical event uniqueness**:

~~~java
message.setStringProperty("eventId", eventId);
~~~

The producer must preserve the same `eventId` when retrying the same event. Consumers use unique constraints or an idempotency store to prevent duplicate side effects. Never rely on `JMSMessageID` as a unique business key merely because it is enabled.

### 10.2. Correlation ID

An application-defined `JMSCorrelationID` can match responses if both sides agree:

~~~java
message.setJMSCorrelationID(requestId);
~~~

Be clear on uniqueness scope; a `correlationId` may group multiple events within one workflow. Do not automatically assume per-message uniqueness.

### 10.3. Business Timestamp

If you need when the **business event was born**, place a domain-generated `eventCreatedAt` in the payload. If you need publish time for reporting, you can set `publishedAtEpochMs` from the producer clock, yet this **also incurs overhead**; disabling `JMSTimestamp` only to add an equivalent timestamp may save nothing.

Distinguish `eventCreatedAt`, `publishedAt`, broker ingest time, consumer `receivedAt`, `committedAt`, and `processedAt`. No single timestamp tells the whole story.

## 11. Benchmark Plan: How to Prove Real Gains

Never write "boosts throughput by 20%" without measuring. Use the four variants A/B/C/D from Section 8 on the same provider and payload:

1. **Setup:** pin broker version, client version, queue/topic, persistent mode, transaction/ack, TLS, pooling, and message size.
2. **Warm-up:** run long enough for JIT and broker caches to stabilize; never compare cold runs against warm runs.
3. **Isolate variables:** change only the two hints; do not simultaneously alter durability, TTL, batching, producer count, or consumer load.
4. **Measure throughput:** producer and consumer messages/sec; make sure you are not merely building up broker backlog.
5. **Measure latency:** p50/p95/p99 send calls, producer/broker CPU, network bytes/message, and error rates.
6. **Verify headers:** proportion of `JMSMessageID == null` and `JMSTimestamp == 0` at the consumer for each variant.
7. **Assess operations:** do log traces, DLQs, request-reply, audits, and incident triage still have enough data?
8. **Repeat:** run multiple rounds, swapping variant order to reduce cache/background load bias.
9. **Decide:** enable hints only when savings are significant and no header dependencies exist.
10. **Prepare rollback:** configuration must revert cleanly to `Enabled=true` via tested deployment/config changes.

### Interpreting Confusing Results

- **Hints set yet ID/timestamp still present:** provider ignored hints or adapter lacks support; spec-compliant.
- **ID null, timestamp still present:** provider honored one hint; spec-compliant.
- **Throughput unchanged:** header overhead is negligible or provider does not optimize; no reason to force it.
- **Latency increased:** workload/GC/caching variance or another provider code path added overhead; re-analyze.
- **Tracing broken:** consumers/tooling depended on the disabled header; restore or redesign.
- **Queue backlog grows despite faster sends:** producer throughput exceeded consumer capacity; do not call that an end-to-end improvement.

## 12. Common Mistakes to Avoid

| Anti-Pattern | Why Is It Wrong? | How to Fix |
|---|---|---|
| `setMessageIdEnabled(true)` to "disable ID" | Spring names it **Enabled**, so `true` keeps it on | Use `false` when hinting to disable |
| `setDisableMessageID(false)` to "disable ID" | JMS names it **Disable**, so `false` keeps it on | Use `true` when hinting to disable |
| Checking for null ID before `send` inside `MessageCreator` | Header has not been set by the provider yet | Check after send or at the consumer |
| Asserting ID must be null / time 0 on all brokers | Hints may be ignored | Assert according to provider semantics |
| Using `JMSTimestamp=0` to compute message age | Produces a huge fake age | Treat `0` as timestamp unavailable |
| Disabling ID in request-reply using `JMSMessageID` | Loses correlation key | Keep ID or design explicit `correlationId` |
| Using provider ID for business deduplication | Two duplicate publishes get different IDs | Use `eventId` and durable idempotency |
| Assuming disabling timestamp disables TTL | TTL/expiration is independent | Inspect `JMSExpiration` and policies |
| Mutating template setters per request | Race conditions on shared config | Use immutable template profiles |
| Optimizing alongside changing delivery mode/pool/batching | Cannot tell where any gain came from | Benchmark each variable independently |
| Ignoring DLQ, traces, and audits | Makes real incident debugging painful | Design observability before rollout |
| Assuming disabling ID leaves the broker with no internal ID | JMS specifies headers only | Do not infer internal implementation details |

## 13. Pre-Production Checklist

- [ ] Consumers and adapters do not strictly rely on `getJMSMessageID()` or `getJMSTimestamp()` for this message group.
- [ ] Request-reply does not require request `JMSMessageID` for correlation, or has migrated to an independent correlation protocol.
- [ ] A stable business `eventId` exists across producer resends to support idempotency.
- [ ] Required business/tracing timestamps exist; message age is never computed from timestamp zero.
- [ ] TTL, priority, delivery delay, persistence, transactions, and ack rules do not change unintentionally.
- [ ] Spring `JmsTemplate` is configured once; setters are never mutated from request/worker threads.
- [ ] Verified whether the provider **actually** honors or ignores each hint.
- [ ] Benchmarked real throughput/latency/CPU and consumer impact, not just send duration.
- [ ] Monitoring, DLQs, retries, broker tools, and audits still retain enough trail for investigation.
- [ ] Rollback plan to both default hints in tested configuration is ready.
- [ ] Tested against matching provider/client versions and staging/prod environments, not just mocks.
- [ ] Broker permissions and queue/topic configs were not altered during header experiments.

## 14. Self-Check Questions

**1. Does calling `MessageProducer.setDisableMessageID(true)` guarantee a null message ID?** No. If the provider honors it, ID is null; if ignored, a normal ID appears.

**2. What does calling `JmsTemplate.setMessageIdEnabled(false)` mean?** Spring suggests to the provider not to generate a message ID for messages sent via that template.

**3. Does `getDisableMessageTimestamp()==true` prove message timestamps are 0?** No. The getter reports the producer setting, not whether the provider honors the hint.

**4. Does disabling timestamp automatically disable TTL/expiration?** No. `JMSExpiration` is a separate field computed from time-to-live.

**5. Should `JMSTimestamp=0` be converted to a 1970 Instant?** No. When the hint is honored, `0` indicates no timestamp is present.

**6. Why can request-reply break if ID is disabled?** Because some protocols copy the request's `JMSMessageID` into the reply's `JMSCorrelationID`, leaving the requester without a match key.

**7. Should `JMSMessageID` be used as a unique business event key?** No. Producers can send two different JMS messages for the same business event.

**8. If both hints are disabled and throughput does not rise, is the code definitely wrong?** No. The provider may ignore the hints, or ID/time overhead may be tiny compared to other bottlenecks.

**9. Can messages in the same queue have both present IDs and missing IDs?** Yes, if sent by producers with different policies and the provider honors the hint on the corresponding producer.

**10. Do you need `setExplicitQosEnabled(true)` just to disable `JMSMessageID`?** No. Explicit QoS governs `deliveryMode`, `priority`, and `timeToLive` separately.

**11. Why not toggle `setMessageTimestampEnabled` repeatedly on a singleton template?** Because concurrent sending threads will observe non-atomic changes to shared configuration.

**12. To measure when an event was created, which field should be used?** A business `eventCreatedAt` with clear semantics, rather than equating it with `JMSTimestamp` when the provider accepted the send.

**13. When ID is disabled, does `JMSXDeliveryCount` disappear too?** No such rule exists. Delivery count is an independent provider property; correlating multiple deliveries may just be harder without `JMSMessageID`.

**14. Which demo outcomes are spec-compliant?** The provider may honor both hints, only one, or neither; software must handle all those possibilities.

## 15. Official References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — sections **3.4.3 JMSMessageID**, **3.4.4 JMSTimestamp**, **3.4.5 JMSCorrelationID**, **3.4.9 JMSExpiration**, **3.4.13 JMSDeliveryTime**, and **7.8 Message time-to-live**.
- [Jakarta Messaging — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer) — `setDisableMessageID`, `setDisableMessageTimestamp`, and getters.
- [Jakarta Messaging — JMSProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer) — fluent variant via `JMSContext`.
- [Jakarta Messaging — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — header semantics and value origins.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — `setMessageIdEnabled`, `setMessageTimestampEnabled`, QoS.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — template lifecycle and QoS.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html) — Spring Boot configuration.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html) — demo broker.

**Summary:** These two optimization APIs let the provider **skip generating `JMSMessageID`/`JMSTimestamp` when the application does not depend on those headers**. Spring uses `messageIdEnabled=false` and `messageTimestampEnabled=false` to pass the hints. Decide based on tracing, request-reply, and audit needs plus benchmarks on a real broker, never on an assumption that dropping headers always improves performance.
