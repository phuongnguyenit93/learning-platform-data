# Accessing MessageProducer via ProducerCallback in Spring JMS

## 1. What Problem Does ProducerCallback Solve?

When sending messages with **Spring JMS**, the most common approach is calling `JmsTemplate.send(...)` or `convertAndSend(...)`. Spring acquires a `Connection`, `Session`, and `MessageProducer`, sends the message, and releases resources according to the framework lifecycle.

However, some sending code needs **direct control over a `jakarta.jms.MessageProducer`**: sending multiple messages in one operation, configuring Quality of Service (QoS) on the producer, building complex messages with a `Session`, or returning a processing result from inside the callback. In those situations, **`org.springframework.jms.core.ProducerCallback<T>`** is the right API.

```text
Service
  |
  | jmsTemplate.execute(destination, ProducerCallback<T>)
  v
JmsTemplate
  |-- obtain Connection via ConnectionFactory
  |-- create/obtain JMS Session
  |-- resolve destination (if given by name)
  |-- create JMS MessageProducer
  |-- invoke callback.doInJms(session, producer)
  |       |-- session.createTextMessage(...)
  |       |-- producer.setPriority(...), setTimeToLive(...)
  |       |-- producer.send(message), may repeat multiple times
  |       +-- return result T
  |-- close/release producer and session/connection per contract
  v
Service receives result T (or exception)
```

**`ProducerCallback` is not a JMS message type, not a listener, and not a class implementing `MessageProducer`.** It is simply a **Spring functional interface** that receives two prepared JMS objects and executes work within the callback scope.

Core distinctions:

- `MessageCreator`: Spring gives you a **`Session`** to build **one `Message`**; `JmsTemplate.send` sends it for you.
- `MessagePostProcessor`: modifies a message **after conversion** and before Spring sends it; typically used for headers/properties.
- `SessionCallback<T>`: directly accesses **`Session`** for low-level JMS operations.
- `ProducerCallback<T>`: accesses **both `Session` and `MessageProducer`**, especially convenient when sending multiple messages directly or configuring producer settings.

**Rule of thumb:** use `ProducerCallback` only when you genuinely need direct producer control; do not replace every `convertAndSend` call with a complex callback.

## 2. Exact API and How to Read the Signature

In **Spring Framework 6 / Jakarta Messaging 3.x**, the interface is defined as:

```java
package org.springframework.jms.core;

@FunctionalInterface
public interface ProducerCallback<T> {
    T doInJms(
        jakarta.jms.Session session,
        jakarta.jms.MessageProducer producer
    ) throws jakarta.jms.JMSException;
}
```

This is a **simplified signature for learning the API**, not a Spring source file for recompiling the framework. `T` is the **result type**, which can be `Integer`, `String`, an application record, or `Void` (returning `null`).

Three key overloads on `JmsTemplate`:

```java
<T> T execute(ProducerCallback<T> action);

<T> T execute(
    String destinationName,
    ProducerCallback<T> action
);

<T> T execute(
    jakarta.jms.Destination destination,
    ProducerCallback<T> action
);
```

These signatures describe the API; the actual methods carry nullable annotations and throw `org.springframework.jms.JmsException` on errors.

| Overload | Which destination is the producer created for? | When to use |
| --- | --- | --- |
| `execute(callback)` | Uses the template's **default destination name/object** if configured; **otherwise creates an unbound producer with no fixed destination**. | Have a default target, or want an unbound producer to target multiple destinations via `send(destination, message)`. |
| `execute("orders.out", callback)` | Resolves `"orders.out"` to a `Destination`, then creates a producer bound to it. | Sending to a Queue/Topic identified by name. |
| `execute(destination, callback)` | Uses the provided `Destination` object; if `null` is passed, the producer is unbound. | Destination already created, injected, or looked up via JNDI. |

### How Does a Lambda Work?

```java
Integer sent = jmsTemplate.execute(
    "orders.out",
    (session, producer) -> {
        producer.send(session.createTextMessage("Hello JMS"));
        return 1;
    }
);
```

This is a **snippet inside a method that already has a `JmsTemplate jmsTemplate` bean**. Java infers the lambda parameters as `Session` and `MessageProducer`; `return 1` becomes the return value of `execute`. This **does not mean** a consumer has received the message or the broker completed business processing.

### Equivalent Anonymous Class Form

```java
Integer sent = jmsTemplate.execute(
    "orders.out",
    new ProducerCallback<Integer>() {
        @Override
        public Integer doInJms(
                Session session,
                MessageProducer producer) throws JMSException {
            producer.send(session.createTextMessage("Hello JMS"));
            return 1;
        }
    }
);
```

This snippet requires imports for `jakarta.jms.Session`, `jakarta.jms.MessageProducer`, `jakarta.jms.JMSException`, `org.springframework.jms.core.ProducerCallback`, and a `jmsTemplate` variable. With Java 17+, the **lambda form is more concise** while preserving identical semantics.

## 3. Session and MessageProducer Have Different Roles

The callback receives two objects:

**`Session`**:

- Creates messages: `session.createTextMessage(String)`, `createBytesMessage()`, `createMapMessage()`, etc.
- Dynamically creates destination handles when needed: `session.createQueue("name")` or `session.createTopic("name")`.
- Carries the JMS context of a connection and **can** participate in local/JTA transactions depending on configuration.
- Should not be used concurrently from multiple threads; never store `Session` outside the callback for later use.

**`MessageProducer`**:

- Performs sends: `producer.send(message)` when bound to a destination, or `producer.send(destination, message)` when unbound.
- Provides producer QoS settings such as `setDeliveryMode`, `setPriority`, `setTimeToLive`, and `setDeliveryDelay` (per JMS/provider support).
- Has a lifecycle tied to `Session`; Spring creates and closes it within `JmsTemplate.execute(ProducerCallback)`.
- Must never be captured in a field, returned as a result for later use, or passed to another thread to work after the callback finishes.

Relationship between objects:

```text
ConnectionFactory -> Connection -> Session
                                    |
                                    +-> MessageProducer -> send Message
                                    |
                                    +-> createTextMessage(...)
```

**Never** call `new MessageProducer()` or `new TextMessage()`: both are provider-implemented interfaces. Spring creates the producer via `Session.createProducer(destination)`, and messages are created from the supplied session.

## 4. Destination-Bound vs. Unbound Producers

This is the single most important distinction when reading or debugging `ProducerCallback`.

### 4.1. Destination-Bound Producer

```java
jmsTemplate.execute("orders.out", (session, producer) -> {
    producer.send(session.createTextMessage("ORDER-1"));
    producer.send(session.createTextMessage("ORDER-2"));
    return null;
});
```

Spring resolves `"orders.out"` and creates a `producer` bound to that destination. Hence `producer.send(message)` uses **the bound destination** for both messages. With a String name, the default `pubSubDomain=false` and `DynamicDestinationResolver` typically resolve to a Queue; with `true`, to a Topic.

### 4.2. Producer Based on Default Destination

Suppose the configuration is:

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.out");
```

Then:

```java
template.execute((session, producer) -> {
    producer.send(session.createTextMessage("ORDER-3"));
    return null;
});
```

Spring uses the configured default destination to create a producer bound to `orders.out`. This snippet belongs inside a method with a valid `ConnectionFactory connectionFactory`, not a standalone program.

### 4.3. No Default Destination Configured: The Producer Can Be Unbound

Unlike `jmsTemplate.send(MessageCreator)`, which normally requires a default destination, `JmsTemplate.execute(ProducerCallback)` **can** run without a default destination. Spring creates the producer with destination `null` accordingly.

When the producer is **unbound**:

```java
jmsTemplate.execute((session, producer) -> {
    Queue audit = session.createQueue("orders.audit");
    Queue notifications = session.createQueue("orders.notifications");

    producer.send(audit, session.createTextMessage("AUDIT-1"));
    producer.send(notifications,
                  session.createTextMessage("NOTIFY-1"));
    return null;
});
```

This snippet assumes the template **has no default destination** and the resolver/provider permits these Queues. Import `jakarta.jms.Queue`; when the producer is unbound, use the **`send(Destination, Message)`** overload. Calling `producer.send(message)` on an unbound producer leaves no destination to send to, typically causing `InvalidDestinationException`.

**Do not confuse** `execute(callback)` with `send(messageCreator)`: they have different default handling. To send to **one specific destination**, `execute("name", callback)` is clearer and easier to maintain.

### 4.4. Passing a Destination Object

If the application already has a `jakarta.jms.Queue ordersQueue` bean compatible with the current factory:

```java
jmsTemplate.execute(ordersQueue, (session, producer) -> {
    producer.send(session.createTextMessage("ORDER-4"));
    return null;
});
```

Unlike a String name, a `Queue` object already carries provider-specific target identity. **Do not** take a `Queue` object from provider/broker A, pass it to a Session connected to broker B, and assume it will always work.

## 5. Simplest Send with ProducerCallback

When you need to set metadata directly and send a single message, typical code looks like:

```java
int submitted = jmsTemplate.execute("events.orders", (session, producer) -> {
    TextMessage message = session.createTextMessage(
            "{\"eventType\":\"ORDER_CREATED\",\"orderId\":42}"
    );
    message.setStringProperty("contentType", "application/json");
    message.setStringProperty("eventType", "ORDER_CREATED");
    message.setIntProperty("schemaVersion", 1);

    producer.send(message);
    return 1;
});
```

This snippet belongs **inside a method with `JmsTemplate` and `import jakarta.jms.TextMessage`**.

- `session.createTextMessage(...)` builds a `String` body; the JSON here **remains plain text**—JMS does not automatically parse it into a Java object.
- The `setXxxProperty` calls add custom metadata; `contentType` is not a mandatory JMS MIME header.
- `producer.send(message)` sends to the destination bound via `execute("events.orders", ...)`.
- `return 1` is a callback-chosen return value (number of send calls completed **up to that point without throwing an exception**). It is **not** an ACK count, consumer-processed count, or proof that messages survive failures.

In this single-message case, `jmsTemplate.send("events.orders", session -> {...})` works just as well. If you only want to send one message with properties, `convertAndSend(..., MessagePostProcessor)` may be even easier to read. `ProducerCallback`'s real strength shines when **sending multiple times on the same producer** or adjusting QoS directly.

## 6. Controlling QoS Directly on MessageProducer

A JMS producer offers two ways to configure QoS:

1. Set **producer defaults**: `setDeliveryMode(...)`, `setPriority(...)`, `setTimeToLive(...)`. Subsequent `producer.send(message)` calls use those settings.
2. Specify **per send call**: `producer.send(message, deliveryMode, priority, timeToLive)`.

Example setting defaults before sending two messages:

```java
jmsTemplate.execute("events.important", (session, producer) -> {
    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
    producer.setPriority(7);
    producer.setTimeToLive(120_000L); // 120 seconds

    producer.send(session.createTextMessage("ALERT-1"));
    producer.send(session.createTextMessage("ALERT-2"));
    return null;
});
```

This snippet requires importing `jakarta.jms.DeliveryMode`. In Java 17, `120_000L` is a `long` value in **milliseconds**. Typical properties:

| Attribute | API | Meaning / Notes |
| --- | --- | --- |
| Delivery mode | `producer.setDeliveryMode(DeliveryMode.PERSISTENT)` | Requests persistent delivery semantics; actual durability depends on the JMS provider/broker, transactions, and policy. |
| Priority | `producer.setPriority(7)` | JMS value from 0–9 (default typically 4); does not guarantee strict consumer ordering under concurrency, retries, or priority policies. |
| Time-to-live | `producer.setTimeToLive(120_000L)` | Lifetime in ms; `0` usually indicates no TTL expiration. |
| Delivery delay | `producer.setDeliveryDelay(5_000L)` | Per Jakarta Messaging 3.x / JMS 2.0+, requests a delay before the message becomes eligible for delivery; verify provider support and policies. |

**Spring note:** `JmsTemplate.setPriority(...)`, `setTimeToLive(...)`, and `setExplicitQosEnabled(true)` primarily govern the convenience **`JmsTemplate.send`/`convertAndSend`** send path. Once inside **`ProducerCallback` calling `producer.send` directly**, callback code controls QoS via setters or send parameters. Do not assume template QoS settings are copied onto the producer handed to your callback.

You can also assign different QoS per message:

```java
jmsTemplate.execute("events.important", (session, producer) -> {
    producer.send(
        session.createTextMessage("STANDARD"),
        DeliveryMode.PERSISTENT,
        4,
        60_000L
    );
    producer.send(
        session.createTextMessage("URGENT"),
        DeliveryMode.PERSISTENT,
        9,
        10_000L
    );
    return null;
});
```

Do not habitually raise every message to priority 9 or set huge TTLs: doing so can starve normal traffic and grow backlogs. Base QoS choices on business requirements, provider behavior, and operational capacity.

## 7. Sending Multiple Messages with the Same Session and MessageProducer

Suppose a batch has 3 events. Calling `convertAndSend` three times is valid, though each call goes through the template send path independently. With `ProducerCallback`, the entire batch shares **one callback scope with one session/producer**:

```java
List<String> events = List.of("ORDER-1", "ORDER-2", "ORDER-3");

int submitted = jmsTemplate.execute(
        "orders.batch",
        (session, producer) -> {
            int count = 0;
            for (String event : events) {
                TextMessage msg = session.createTextMessage(event);
                msg.setStringProperty("batchId", "batch-42");
                producer.send(msg);
                count++;
            }
            return count;
        }
);
```

This snippet lives **inside a method with `jmsTemplate`**, requiring imports for `java.util.List` and `jakarta.jms.TextMessage`. With a working broker and all `send` calls succeeding, `submitted == 3`.

**What "same producer" actually means:**

- Avoids creating/closing a `MessageProducer` on every loop iteration; Spring closes the producer when the callback finishes.
- Lets you configure producer QoS once before sending multiple messages.
- Groups multiple operations on one session; **does not automatically make them an atomic transaction**.
- If the third message fails inside a **non-transacted** session, the first two messages may already have been sent; throwing an exception from the callback does not undo previous sends.
- When an atomic batch is needed, configure transactions/commit/rollback explicitly with an appropriate transaction manager. See Section 10.

Do not save the producer in an external variable, launch async tasks, and keep using it after `execute` returns: the producer/session is managed by Spring and may be closed or returned to a pool.

## 8. Runnable Demo: Spring Boot 3 + Artemis + ProducerCallback

The following example uses **Java 17+**, **Spring Boot 3.3.13**, Spring JMS, Gradle 8.5+, and an **Apache ActiveMQ Artemis** broker running at `localhost:61616`. Goal: obtain a producer from `JmsTemplate.execute(ProducerCallback)`, configure QoS, send 3 `TextMessage`s, and return the send count; a listener reads them from the demo Queue.

### 8.1. Starting Artemis for Learning

If Docker is installed, start a test broker:

```bash
docker run --detach --rm --name artemis-producer-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Wait for the broker to become ready and inspect logs with `docker logs artemis-producer-demo`. This command uses the official image and credentials **for local learning environments only**. The broker must allow auto-creation or have Queue `demo.producer.orders` pre-provisioned; if auto-create is disabled, create the Queue first. Stop when finished: `docker stop artemis-producer-demo`.

### 8.2. Gradle Project

Create `settings.gradle`:

```groovy
rootProject.name = 'producer-callback-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Create `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      default-destination: demo.producer.orders
```

Because Boot sets `spring.jms.template.default-destination`, `JmsTemplate.execute(ProducerCallback)` in this example **uses a producer bound to Queue `demo.producer.orders`**. There is no need to pass the destination String on every call.

### 8.3. Complete Java File

Create `src/main/java/demo/jms/ProducerCallbackApplication.java`:

```java
package demo.jms;

import java.util.List;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class ProducerCallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProducerCallbackApplication.class, args);
    }

    @Bean
    ApplicationRunner sendAtStartup(BatchPublisher publisher) {
        return args -> {
            int sent = publisher.publish(
                    "batch-001",
                    List.of("ORDER-001", "ORDER-002", "ORDER-003")
            );
            System.out.println("Submitted via callback: " + sent);
        };
    }
}

@Component
class BatchPublisher {

    private final JmsTemplate jmsTemplate;

    BatchPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    int publish(String batchId, List<String> payloads) {
        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId is required");
        }
        if (payloads == null || payloads.isEmpty()) {
            throw new IllegalArgumentException("payloads are required");
        }

        // execute accepts ProducerCallback<Integer>; uses the default
        // destination from application.yml.
        return jmsTemplate.execute((session, producer) -> {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            producer.setPriority(6);
            producer.setTimeToLive(120_000L);

            int count = 0;
            for (String payload : payloads) {
                TextMessage message =
                        session.createTextMessage(payload);
                message.setStringProperty("batchId", batchId);

                producer.send(message);
                count++;
            }
            return count;
        });
    }
}

@Component
class OrderMessageListener {

    @JmsListener(destination = "demo.producer.orders")
    public void onMessage(TextMessage message) throws JMSException {
        System.out.printf(
                "Received: %s [batch=%s]%n",
                message.getText(),
                message.getStringProperty("batchId")
        );
    }
}
```

**Actual execution path:** `ApplicationRunner` calls `BatchPublisher.publish` → `JmsTemplate.execute(ProducerCallback)` → Spring creates a producer bound to the default Queue → the callback configures QoS and sends three messages → the callback returns the send count → the listener reads `TextMessage`.

`@JmsListener` uses the destination declared **independently** on its annotation; it does not read `JmsTemplate`'s default destination automatically. In this demo, both Queue names match intentionally.

### 8.4. Running and Observable Results

With Gradle installed, run from the project directory:

```bash
gradle bootRun
```

If using a generated Gradle Wrapper: `./gradlew bootRun` on Linux/macOS, `gradlew.bat bootRun` on Windows. Apart from Spring/Artemis logs, on a clean broker with a single listener and all sends succeeding, you should see **four content lines** (order is not guaranteed):

```text
Submitted via callback: 3
Received: ORDER-001 [batch=batch-001]
Received: ORDER-002 [batch=batch-001]
Received: ORDER-003 [batch=batch-001]
```

`Submitted via callback: 3` means the callback called `send` three times without error and returned `3`; it **does not confirm** the listener finished processing all three messages. `Received` lines can appear before `Submitted`, and if retries, backlogs, or competing consumers exist, the count or ordering can vary. Do not treat demo logs as proof of exactly-once delivery.

### 8.5. Switching to the Destination-Explicit Overload

If you prefer not to rely on `default-destination` in YAML, replace inside `BatchPublisher`:

```java
return jmsTemplate.execute(
        "demo.producer.orders",
        (session, producer) -> {
            int count = 0;
            for (String payload : payloads) {
                TextMessage msg = session.createTextMessage(payload);
                msg.setStringProperty("batchId", batchId);
                producer.send(msg);
                count++;
            }
            return count;
        }
);
```

This snippet replaces **the entire `return jmsTemplate.execute(...)` statement** inside `publish`; do not paste both at once. The QoS configuration from the main example is omitted in this shortened snippet; to retain QoS, keep the exact same setters inside the callback.

## 9. Sending to Multiple Destinations with One ProducerCallback

If you want to send two event types to different destinations **inside a single callback**, you need to understand bound vs. unbound producers.

Create a `JmsTemplate` **without configuring a default destination**, then call:

```java
jmsTemplate.execute((session, producer) -> {
    Queue orders = session.createQueue("events.orders");
    Queue audit = session.createQueue("events.audit");

    TextMessage order = session.createTextMessage("ORDER_CREATED");
    order.setStringProperty("eventId", "evt-001");
    producer.send(orders, order);

    TextMessage auditLog = session.createTextMessage("ORDER_CREATED");
    auditLog.setStringProperty("eventId", "evt-001");
    producer.send(audit, auditLog);

    return null;
});
```

This snippet requires `jakarta.jms.Queue` and a template without a default destination. Spring creates an **unbound** producer; the `send(Destination, Message)` overload specifies the target on each call. Depending on provider and permissions, `session.createQueue` creates a destination handle by name, **without guaranteeing the broker auto-provisions the Queue**.

**What not to do:** keep a default destination configured and try to use the bound producer to send elsewhere via the anonymous-producer overload; JMS providers may reject it. If you simply need to send to two Queues and do not need a shared session/producer, two `jmsTemplate.convertAndSend("...", payload)` calls are usually simpler.

**Transactions:** two `producer.send` calls in one callback **do not automatically mean** an atomic commit across both Queues. When atomicity is required, configure an appropriate transaction manager; for systems integrating databases or other brokers, evaluate JTA/XA, outbox, or idempotency.

## 10. Transactions, Commits, and Limits to Understand

### 10.1. The Callback Does Not Automatically Create a Batch Transaction

`JmsTemplate.execute(ProducerCallback)` supplies JMS resources to the callback and translates `JMSException` into Spring `JmsException`. It **does not** automatically initiate a distributed transaction across multiple messages or multiple systems.

On a default non-transacted session, three `send` calls are three operations that the provider may execute individually. If the third throws an exception, do not assume the first two are rolled back.

When you need **a local JMS transaction** or a transaction coordinated with a database, configure a transaction manager and verify resource participation. **Never** arbitrarily call `session.commit()` inside the callback when the session belongs to a container/JTA transaction.

### 10.2. Why Be Careful with `sessionTransacted=true`?

In Spring 6, the convenience path `JmsTemplate.send(...)` includes commit logic for a **locally transacted session** when appropriate. By contrast, `execute(ProducerCallback)` mainly creates the producer, invokes `doInJms`, and cleans up resources; **do not assume it runs through `doSend`'s auto-commit logic**.

Therefore, if you set `sessionTransacted=true` yourself without a suitable transaction manager/lifecycle setup, messages sent in the callback risk never being committed as expected. Make sure to:

1. Know whether the session is local or JTA-managed.
2. Identify which transaction manager starts, commits, and rolls back.
3. Write an integration test sending multiple messages, failing mid-way, and verifying rollback/redelivery.
4. Commit manually only when the application **truly owns** the local session and the design does not conflict with Spring/JTA.

Core lesson: **sharing a `Session` does not mean sharing a committed transaction**. If business-level exactly-once processing is needed, combine event IDs, deduplication/idempotency, and a sound transaction strategy.

### 10.3. Remember to Separate "Send", "Broker Persist", and "Consumer Process"

There are at least three milestones:

```text
producer.send(message) returns
            |
            v
broker/provider accepts per configured mode
            |
            v
consumer receives and processes/ACKs/commits
```

`execute` returning an `Integer` does not prove all three milestones succeeded. With retries, sending can create duplicate messages. Use business event IDs and idempotent handlers whenever safety against redelivery or client retries is required.

## 11. Resource Management and Exception Handling

`JmsTemplate.execute` is built for **resource management**:

- Acquires/opens a session from the connection factory, binding to any active transaction as appropriate.
- Creates a producer for the selected destination and passes it to the callback.
- Closes the `MessageProducer` in `finally`; closes/releases the session and connection per Spring lifecycle.
- Catches `jakarta.jms.JMSException` and converts it into unchecked Spring `org.springframework.jms.JmsException` so callers can handle it per application architecture.

Consequently, **do not close `producer` or `session` yourself** inside a normal callback. Closing them prematurely and continuing to send causes `IllegalStateException` or JMS errors. Nor should you return `MessageProducer`/`Session` for use after the callback; the return type `T` should be plain data or objects detached from the JMS lifecycle.

Example error boundary in a service:

```java
try {
    Integer count = jmsTemplate.execute(
            "orders.out",
            (session, producer) -> {
                producer.send(session.createTextMessage("ORDER-5"));
                return 1;
            }
    );
    System.out.println("Submitted: " + count);
} catch (org.springframework.jms.JmsException ex) {
    // Log eventId + error type, apply appropriate retry/backoff.
    // Do not assume every JMS error is safe to retry infinitely.
    throw ex;
}
```

This snippet belongs to a method with `JmsTemplate jmsTemplate`. `JMSException` inside the callback is translated by Spring; runtime exceptions thrown by business code may propagate as runtime exceptions rather than necessarily being wrapped as `JmsException`.

**Never** catch everything and return `0` when the callback fails mid-batch: the caller would think nothing was sent even though earlier messages may have reached the broker. Returned results need a clear contract: *how many send calls were issued inside the callback*, not *how many events were successfully processed*.

## 12. ProducerCallback vs. MessageCreator, MessagePostProcessor, SessionCallback?

| Need | Usually best API | Reason |
| --- | --- | --- |
| Send a single `String` or DTO via converter | `convertAndSend(destination, payload)` | Simple; uses `MessageConverter`. |
| Create a custom JMS `Message` | `send(destination, MessageCreator)` | Provides `Session`; Spring handles sending. |
| Set headers/properties after converter creates message | `convertAndSend(..., MessagePostProcessor)` | No need to manage producer yourself. |
| Send multiple messages with one `Session`/`MessageProducer` | `execute(destination, ProducerCallback<T>)` | Provides both session and producer. |
| Configure special QoS on producer in a scope | `ProducerCallback` | Direct access to `MessageProducer` API. |
| Diverse Session-level JMS operations, creating producers/consumers | `execute(SessionCallback<T>)` | Supplies Session only; app manages extra resources it creates. |
| Continuously receive messages asynchronously | `@JmsListener` | Listener container is far better suited than producer callbacks. |

**Common misconception:** `ProducerCallback` automatically uses `JmsTemplate`'s `MessageConverter` to convert DTOs into messages. False: the callback receives a **raw `Session`** and calls `createTextMessage`, `createObjectMessage`, etc., itself. If you need a converter, invoke the right `MessageConverter` explicitly and ensure type/schema compatibility, or choose `convertAndSend` so Spring handles it.

### Is the Callback Async?

No. It is **a callback invoked synchronously on the calling thread of `execute`**. While the JMS provider may optimize transport, invoking the callback is not dispatching work to a thread pool. A send can block due to broker flow control, network issues, or resource limits. Avoid unnecessary long CPU work or blocking HTTP loops inside the callback.

### Why Not Cache the Producer Forever?

`MessageProducer` is tied to `Session` and follows the JMS lifecycle. Spring can cache/reuse JMS sessions per connection factory settings, yet that **does not permit an application to hold onto a callback-provided producer after the callback exits**. To optimize throughput, tune `CachingConnectionFactory`/pooling settings and benchmark rather than breaking lifecycle contracts.

## 13. Common Errors

| Error/Symptom | Likely cause | Fix |
| --- | --- | --- |
| `InvalidDestinationException` on `producer.send(message)` | Producer is unbound because template lacks default destination. | Use `execute("queue", callback)`, set a default, or call `producer.send(destination, message)` on unbound producer. |
| Callback sends to an unexpected Queue | Wrong `defaultDestinationName`, `pubSubDomain`, or `DestinationResolver`. | Verify template instance, target name, and Queue/Topic domain. |
| `NullPointerException` or error using producer post-callback | Retained producer/session reference after Spring closed it. | Use only inside callback; return DTO/result, never resources. |
| Only some messages in a batch arrive | Mid-batch failure, transaction/rollback, broker policy, competing listeners, retries. | Inspect logs, actual sends/commits/ACKs; never assume atomic batches. |
| Priority/TTL ignores `JmsTemplate` config | Direct sends on raw `MessageProducer` bypass convenience `doSend`. | Set QoS on producer or per send call; test provider behavior. |
| Exception occurred yet count logged as success | Code caught and swallowed the exception. | Distinguish send attempts, broker ACKs, and downstream processing; never swallow errors. |
| Fails to compile due to `javax.jms` imports | Legacy JMS library mixed with Spring 6 / Boot 3. | Import `jakarta.jms.*`; keep `javax.naming` separate if using JNDI. |
| `JMSException` won't compile outside callback | Direct JMS calls throw checked exceptions. | Put code in callback (`doInJms throws JMSException`) or declare/catch properly. |
| Template runs yet no consumer receives | Destination missing, wrong domain, auth/broker error, listener not ready. | Check broker logs/console, destination, and listener config. |
| Producer sends multiple times then transaction doesn't commit | Misunderstood `execute` lifecycle and local transactions. | Verify transaction manager, `sessionTransacted`, and commit/rollback via integration tests. |

## 14. Testing the Design

### Unit Tests

The service's unit of responsibility should be: "when sending a batch, call `JmsTemplate.execute` with the expected destination and callback." You can mock `JmsTemplate` to verify which overload was invoked; to verify detailed message contents/QoS, mock `Session` and `MessageProducer` and **execute the captured callback** in the test. Never assume a mocked `JmsTemplate` runs callbacks on its own: without stubbing it, mock calls simply return default values.

### Integration Tests

Run a real broker or a test container close to production, verifying:

1. Factory connects to the right broker and Queue/Topic is provisioned.
2. Exact message count received when no competing consumer interferes.
3. Actual properties (`batchId`), priority, TTL, and delivery mode.
4. Mid-batch errors, rollback/retry behavior, and duplicate handling per transaction setup.
5. Behavior of `execute(callback)` **with** and **without** a default destination.
6. Resource lifecycle/caching under concurrent publishers.

Test **against your specific provider** because behavior around redelivery, expiration, priority scheduling, flow control, and pooling often differs in detail.

### Hands-On Exercises

**Exercise 1.** Use `ProducerCallback<Integer>` to send 5 `TextMessage`s to Queue `demo.orders`, returning the count of completed `send` calls. Attach a `batchId` property and verify it on the consumer.

**Hint:** use `jmsTemplate.execute("demo.orders", (session, producer) -> {...})`, create messages in a `for` loop, and `return count`.

**Exercise 2.** A template has no default destination. What happens if you call `execute((session, producer) -> { producer.send(session.createTextMessage("A")); return null; })`?

**Answer:** The producer may be unbound, so `send(message)` has no destination and can throw `InvalidDestinationException`. Use an overload with a destination or call `producer.send(explicitDestination, message)` on the unbound producer.

**Exercise 3.** Why might `execute` return `3` while the consumer dashboard shows only two processed events?

**Answer:** `3` is merely the callback's count of sends that did not throw errors; it does not prove consumption/ACK. Inspect backlog, consumer concurrency, filtering, expiration, errors, rollbacks, and transactions.

**Exercise 4.** Someone configures `jmsTemplate.setPriority(8)` and calls `producer.send(message)` inside the callback. Can you assume messages are sent with priority 8?

**Answer:** Never assume that. Direct producer calls inside the callback do not necessarily apply `JmsTemplate.doSend` QoS settings. Call `producer.setPriority(8)` or pass priority to `producer.send(message, mode, 8, ttl)`.

**Exercise 5.** Should you call `producer.close()` and `session.close()` inside the callback to prevent leaks?

**Answer:** No, not in normal `JmsTemplate.execute` usage; the template manages their lifecycle. Closing Spring-managed resources manually can break the rest of the callback or transaction.

## 15. Official Sources and Further Reading

- [Spring Framework – Sending a Message, SessionCallback, and ProducerCallback](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework 6.2 – ProducerCallback API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/ProducerCallback.html)
- [Spring Framework 6.2 – JmsTemplate.execute overloads](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Jakarta Messaging 3.1 – MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Jakarta Messaging 3.1 – Session](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session)
- [Spring Boot – ActiveMQ Artemis / JMS auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Apache ActiveMQ Artemis – Docker images and broker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Remember:** `ProducerCallback<T>` grants **direct access to `Session` and `MessageProducer` inside `JmsTemplate.execute`**, especially useful when sending multiple messages or controlling QoS. Know whether the producer is **bound or unbound**, let Spring manage lifecycles, and design **transactions/ACKs/idempotency separately** when business reliability is required.
