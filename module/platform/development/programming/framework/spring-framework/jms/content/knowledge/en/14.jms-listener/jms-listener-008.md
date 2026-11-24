# Multiple @JmsListener Annotations on One Method in Spring JMS

## 1. Goal and Short Answer

In Spring Framework JMS, **`@JmsListener` is a repeatable annotation (`@Repeatable`)**. A Java method can declare **two or more `@JmsListener` annotations**, each describing **a separate listener endpoint**: with its own destination, ID, container configuration, selector, and concurrency. When a message arrives at any of those endpoints, Spring calls **the same Java method** to process it.

Example:

```java
@Component
class UnifiedEventHandler {

    @JmsListener(id = "orders-endpoint", destination = "orders.inbox")
    @JmsListener(id = "audit-endpoint", destination = "audit.inbox")
    public void handle(String body) {
        System.out.println("Handled: " + body);
    }
}
```

Result at the infrastructure layer:

```text
                 Spring-managed UnifiedEventHandler bean
                               │
                      handle(String body)
                       ▲               ▲
                       │               │
           listener endpoint 1   listener endpoint 2
             id=orders-endpoint    id=audit-endpoint
                       ▲               ▲
                container A       container B
                       ▲               ▲
               orders.inbox        audit.inbox
                       ▲               ▲
                    JMS Broker / provider
```

**Do not misunderstand:** multiple annotations on one method **do not** create a single consumer subscribed to multiple queues, nor do they automatically invoke the method N times for one message. Spring registers **N endpoints** and typically creates **N listener containers**, one per annotation. Each container manages its consumer/session, converts payloads, and calls the shared method.

### After This Lesson, You Will:

1. Know the syntax for repeating `@JmsListener` and how to use `@JmsListeners` when needed.
2. Understand why Spring creates multiple endpoints/containers while having only one business method.
3. Distinguish **two different queues**, **two listeners on the same queue**, and **two subscriptions on a topic**.
4. Know how to use `id`, `destination`, `selector`, `concurrency`, and `containerFactory` per annotation.
5. See a Spring Boot 3.x + Artemis + Java 17+ example with run commands and registry checks.
6. Avoid duplicate IDs, duplicate processing, shared mutable state, mismatched message schemas, and wrong transaction assumptions.

## 2. Mechanism of Repeatable Annotations

Java has supported repeatable annotations since Java 8. In Spring JMS, `@JmsListener` carries metadata equivalent to:

```java
@Repeatable(JmsListeners.class)
public @interface JmsListener {
    // Attributes such as destination(), id(), containerFactory(), ...
}
```

This is only a **structural summary** to explain the idea, **not the complete Spring Framework source**. `@JmsListeners` is the **container annotation** holding multiple `@JmsListener` declarations.

Two semantically equivalent ways to write it:

**Approach A — recommended on Java 17+: repeat directly**

```java
@JmsListener(id = "listener-a", destination = "queue.a")
@JmsListener(id = "listener-b", destination = "queue.b")
public void consume(String payload) {
    process(payload);
}
```

**Approach B — using `@JmsListeners` explicitly**

```java
@JmsListeners({
    @JmsListener(id = "listener-a", destination = "queue.a"),
    @JmsListener(id = "listener-b", destination = "queue.b")
})
public void consume(String payload) {
    process(payload);
}
```

Both snippets are **method fragments** that must sit inside a Spring-managed bean with imports:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.annotation.JmsListeners;
```

`@JmsListeners` is not a special annotation creating a "multi-queue" listener: it is simply wrapper syntax grouping `@JmsListener` annotations. Java reflection `getAnnotationsByType(JmsListener.class)` can read repeated annotations; Spring's annotation processor also detects each declaration.

**Version scope:** Repeatable `@JmsListener` exists in Spring Framework lines supporting modern Jakarta/Java; the hands-on example uses Spring Framework 6.x via Spring Boot 3.5.7. With Spring Boot 3+, JMS imports are `jakarta.jms.*` instead of `javax.jms.*`.

## 3. How Does Spring Register the Endpoints?

When a bean has methods annotated with `@JmsListener`, the annotation-driven infrastructure enabled by `@EnableJms` scans them, registers `MethodJmsListenerEndpoint` instances, and creates listener containers via `JmsListenerContainerFactory`.

Conceptually:

```text
Spring Boot / ApplicationContext
   │
   ├─ @EnableJms / JMS annotation infrastructure
   │     │
   │     ▼
   │  JmsListenerAnnotationBeanPostProcessor
   │     │
   │     ├─ finds first @JmsListener on handle()
   │     │     └─ MethodJmsListenerEndpoint("listener-a", "queue.a")
   │     │
   │     └─ finds second @JmsListener on handle()
   │           └─ MethodJmsListenerEndpoint("listener-b", "queue.b")
   │
   ▼
 JmsListenerEndpointRegistry
   ├─ listener-a → MessageListenerContainer A
   └─ listener-b → MessageListenerContainer B
                          │
           same target bean, same handle(...)
```

Each annotation typically corresponds to **one endpoint** and **one listener container**. A container creates or manages JMS consumers/sessions depending on the container type and `concurrency`; the physical consumer count does not always equal the annotation count. For example, two endpoints each with concurrency 3 can yield **six consumers**, not just two.

### 3.1. Shared Method, Separate Endpoint Context

Each message passes through a specific endpoint's container; the container determines:

- Which `Destination` to consume from.
- Consumer selector, and whether to receive as queue or topic.
- Concurrency and session/ack/transaction behavior.
- `MessageConverter` or handler method adapter provided by the factory.
- Error handling, recovery, lifecycle, and provider policies.

Only the **final processing target** is the shared Java method. A `@JmsListener` is not "called" in a `for` loop inside Spring; instead, independent containers await messages from the broker and invoke the method upon arrival.

### 3.2. `JmsListenerEndpointRegistry` for Management

Containers created via annotations are managed by `org.springframework.jms.config.JmsListenerEndpointRegistry` and **are not necessarily standalone beans** to autowire by container name.

```java
// Code snippet inside a Spring-managed component.
JmsListenerEndpointRegistry registry = ...;

boolean hasA = registry.getListenerContainer("listener-a") != null;
boolean hasB = registry.getListenerContainer("listener-b") != null;

System.out.println("A registered: " + hasA);
System.out.println("B registered: " + hasB);
```

`registry.getListenerContainer("listener-a")` returns the container for that ID or `null` if absent; it can be used to inspect/control lifecycle per operational policy. Checking non-null does not mean the broker is definitely connected or has already consumed messages successfully. To verify delivery, use integration tests or broker health/metrics.

Assigning stable IDs to critical endpoints makes monitoring/troubleshooting much clearer than letting Spring auto-generate IDs.

## 4. When to Use: Two Different Queues

The most common case: two queues carry **payloads sharing the same contract** and processed by the same logic, e.g., `orders.created` and `orders.replayed` both carry `OrderCreatedV1` under a shared convention.

```java
@Component
class OrderCreatedHandler {

    @JmsListener(id = "orders-live", destination = "orders.created")
    @JmsListener(id = "orders-replay", destination = "orders.replayed")
    public void onOrder(String orderId) {
        // Same processing code, two separate queue sources.
        System.out.println("Order: " + orderId);
    }
}
```

Advantages:

- Avoids duplicating a block of business logic across two methods.
- Provides **one place** to validate, map DTOs, and call business services.
- Allows configuring concurrency or container factories per endpoint.
- When logic changes, both endpoints immediately use the updated code.

Disadvantages:

- If the two queues have different schemas/security rules/ack policies, one method can accumulate too many branches.
- If both queues contain **the same event** at once, the handler can process the event **twice**—sharing a method provides no deduplication.
- When a replay queue holds older events, care must be taken with idempotency and controlling business side effects.
- Operations may struggle to tell which queue an error came from if logs omit destination/source headers.

**Practical rule:** multiple `@JmsListener` annotations on the same method make sense when **message contracts and processing policies are compatible**. If business logic differs, use separate listener methods calling **a shared service** instead of forcing all messages through one method.

### 4.1. What If Schemas Differ?

For instance, `orders.queue` receives JSON `OrderCreatedV1`, while `audit.queue` receives JSON `AuditRecordV2`. Putting both on `consume(OrderCreatedV1 order)` can make the converter fail when an audit message arrives.

A cleaner approach:

```java
@Component
class DedicatedHandlers {
    private final BusinessProcessor processor;

    DedicatedHandlers(BusinessProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "orders.queue")
    public void handleOrder(OrderCreatedV1 event) {
        processor.processOrder(event);
    }

    @JmsListener(destination = "audit.queue")
    public void handleAudit(AuditRecordV2 event) {
        processor.processAudit(event);
    }
}
```

The names `BusinessProcessor`, `OrderCreatedV1`, and `AuditRecordV2` in this example are **illustrative application types**, not built-in Spring classes. This is an architectural snippet, not a standalone project. With JSON DTOs, you also need a `MessageConverter` configured for the corresponding schemas.

## 5. Two Annotations on the Same Destination: Does Not Auto-Duplicate Messages

Placing two `@JmsListener` annotations reading the same **queue**:

```java
@JmsListener(id = "worker-a", destination = "jobs.queue")
@JmsListener(id = "worker-b", destination = "jobs.queue")
public void process(String body) {
    System.out.println(body);
}
```

registers **two endpoints/consumers** on `jobs.queue`. Under JMS queue point-to-point semantics, **a message is normally delivered to one consumer**, not broadcast to both just because there are two annotations. They act as **competing consumers**.

```text
Queue jobs.queue:  message-1, message-2, message-3
        │
        ├── Consumer A (endpoint worker-a) ──► process(...)
        └── Consumer B (endpoint worker-b) ──► process(...)

Each message is processed by one consumer in a normal delivery.
On error/retry/redelivery, the same message may be delivered again.
```

Consequences:

- Putting the same destination twice is **not** a way to "run two handlers for every message".
- To increase throughput, configure `concurrency` on **one endpoint** rather than duplicating identical annotations. That is usually cleaner.
- Two endpoints compete, and processing completion order is not guaranteed to match global queue order as concurrency rises.
- On broker redelivery after a transaction rollback, a message can reach the other consumer on retry; **do not infer "exactly once per message"** from queue semantics alone.

### 5.1. Wanting Fan-Out to Every Subscriber: Use a Topic or Publish Multiple Copies

With JMS topics and proper subscriptions, each subscriber can receive a copy of a message, unlike competing consumers on a queue. However, you must explicitly configure **pub-sub domain**, subscriptions, durability/shared subscriptions, and broker routing.

Do not simply rename `destination="jobs.queue"` to a topic-like name assuming Spring knows it is a topic: the container factory may default to queue mode. Configure the factory/topic appropriately and test against the provider. Two listeners on the same topic can form **two subscriptions**, though shared/durable subscription modes have distinct delivery semantics; do not generalize that every configuration always yields exactly two copies.

**If the goal is merely sending the same event to two different systems**, consider a publish–subscribe design or two queues routed from an address/topic; that is a topology decision, not a side effect of repeatable annotations.

## 6. Using `selector` to Route Traffic on the Same Queue

Two endpoints can receive different message types on one queue using JMS message selectors:

```java
@Component
class ClassifiedConsumer {

    @JmsListener(
        id = "orders-selector",
        destination = "events.queue",
        selector = "eventType = 'ORDER'"
    )
    @JmsListener(
        id = "audit-selector",
        destination = "events.queue",
        selector = "eventType = 'AUDIT'"
    )
    public void onEvent(String payload) {
        // Same method, different selector.
    }
}
```

The producer must set a **JMS property**, not just a JSON field:

```java
jmsTemplate.convertAndSend("events.queue", "order-42", message -> {
    message.setStringProperty("eventType", "ORDER");
    return message;
});
```

JMS selectors filter by standard headers/properties supported by the provider; they **do not parse arbitrary JSON bodies**. With two non-overlapping selectors like `ORDER` and `AUDIT`, each valid message normally matches only one consumer. If selectors overlap, two consumers on the same queue **still compete**, without turning the queue into a topic.

### 6.1. What If a Message Matches No Selector?

The message may sit in the queue until a matching consumer appears, its TTL expires, or it moves per broker policy. Do not assume Spring automatically routes it to a DLQ just because no listener matches the selector. Define rules for unknown event types and monitor queue backlog.

### 6.2. Why Selectors Do Not Replace Validation

A producer could set property `eventType=ORDER` while placing an audit schema in the JSON body. Selectors only decide **which consumer receives**; the handler must still validate content type, schema version, required fields, and business constraints. When multiple queues share a handler, this is even more important.

## 7. `@JmsListener` Attributes Configure Independently per Annotation

| Attribute | Role | Notes for a multi-annotation method |
| --- | --- | --- |
| `destination` | JMS destination name the endpoint receives from | Each annotation has its own value; do not pass `q1,q2` expecting two queues |
| `id` | Endpoint container ID | **Must be unique** across endpoints in the same registry |
| `containerFactory` | Bean name of `JmsListenerContainerFactory` creating the container | Each annotation can use a different factory if policies differ |
| `selector` | JMS selector expression filtering headers/properties | Applied independently on each endpoint's consumer |
| `concurrency` | Limit on consumers/container threads per factory | Counted **separately** per annotation; total resources add up |
| `subscription` | Subscription name for matching durable/shared topics | Do not reuse arbitrarily with incompatible configurations |

Example of two endpoints with separate concurrency bounds:

```java
@JmsListener(
    id = "fast-orders",
    destination = "orders.fast",
    concurrency = "2-4"
)
@JmsListener(
    id = "slow-orders",
    destination = "orders.slow",
    concurrency = "1"
)
public void handle(String payload) {
    process(payload);
}
```

Here `process(payload)` is an **illustrative business method** not declared in the snippet. Depending on the actual container factory, `concurrency="2-4"` can run at least two and at most four consumers; it does not call the method four times per message. If the factory does not support dynamic scaling, interpretation may differ—check the specific API.

### 7.1. What Problem Does a Duplicate `id` Cause?

```java
// DO NOT: two endpoints using the same ID.
@JmsListener(id = "same-id", destination = "queue.a")
@JmsListener(id = "same-id", destination = "queue.b")
public void handle(String body) {
    // ...
}
```

The registry needs an ID to manage each container. Registering an ID twice can fail startup with a message similar to "Another endpoint is already registered with id ...". Use distinct values such as `inbound-a-v1`, `inbound-b-v1`.

If `id` is omitted, Spring auto-generates IDs. That avoids collisions under normal conditions, but is inconvenient for monitoring, alerts, and lifecycle control by meaningful names.

### 7.2. `containerFactory` Can Differ

Sometimes one method is invoked by an endpoint handling a critical queue and another handling a batch/test workload. You can choose:

```java
@JmsListener(
    id = "critical-events",
    destination = "events.critical",
    containerFactory = "strictQueueFactory"
)
@JmsListener(
    id = "background-events",
    destination = "events.background",
    containerFactory = "batchQueueFactory"
)
public void onEvent(String body) {
    process(body);
}
```

Both factory names must exist as Spring beans of type `JmsListenerContainerFactory`, properly configured with `ConnectionFactory`, transactions, acknowledgement, concurrency/recovery, converter, and broker security. If an annotation omits `containerFactory`, Spring uses the default bean usually named `jmsListenerContainerFactory`, or a default configured via `JmsListenerConfigurer`.

**Warning:** different factories can lead to different **transaction semantics** and message conversions even for the same method. Do not share a handler across incompatible payloads/schemas or assume the annotation selects the type converter by itself.

### 7.3. Different Destinations When You Need to Know the Source

You can pass trusted broker/transport metadata into the handler, such as the JMS destination header, or check a `sourceSystem` property set by the producer per contract. With Spring method signatures:

```java
import jakarta.jms.Message;
import jakarta.jms.JMSException;
import jakarta.jms.Queue;

@JmsListener(id = "from-a", destination = "queue.a")
@JmsListener(id = "from-b", destination = "queue.b")
public void onMessage(Message raw) throws JMSException {
    if (raw.getJMSDestination() instanceof Queue queue) {
        String name = queue.getQueueName();
        System.out.println("Received on: " + name);
    }
}
```

This is a method snippet using raw JMS `Message`; there is no automatic conversion to `String`. Queue names can be provider-specific and should not be used to enforce business security rules without verification; a clearer solution when logic diverges is two separate methods calling one shared service.

You can use `@Header` with `JmsHeaders.DESTINATION` in Spring's messaging abstraction, though runtime types/header mappings must be verified per converter/provider; the example above intentionally uses native `Message.getJMSDestination()` to avoid assumptions about header string names.

## 8. Complete Hands-On Example: Two @JmsListener Annotations on One Method

The following demo uses **Java 17+**, **Maven**, **Spring Boot 3.5.7**, and **Apache ActiveMQ Artemis** running locally via Docker. It sends two String messages to **two different queues**, and the same `handle` method receives from both. A component counts **two distinct payloads** using `CountDownLatch` and prints sorted results so stdout stays deterministic despite asynchronous execution.

### 8.1. Starting a Local Artemis Broker

Requires Docker and free localhost port `61616`:

```bash
docker run --rm -d --name jms-repeatable-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-repeatable-broker
```

Wait until the broker is ready before running the application. These are **local demo** credentials—never reuse the same credentials in production. The Artemis demo image may allow auto-creating queues under default policy; production brokers may require pre-provisioning and explicit permissions.

### 8.2. Project Structure

```text
repeatable-jms-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/
    │   │   └── application.properties
    │   └── java/com/example/jms/
    │       └── RepeatableJmsApplication.java
    └── test/
        └── java/com/example/jms/
            └── RepeatableAnnotationTest.java
```

### 8.3. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repeatable-jms-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

`spring-boot-starter-artemis` provides the client and Spring JMS infrastructure. Because the payload is just a String, the default converter can use `TextMessage`; the example needs no custom JSON converter.

### 8.4. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

This configuration is **for local lab use only**. In production, never commit real passwords to Git or `application.properties`; supply them via environment variables/secret managers, and configure TLS and ACLs.

### 8.5. `RepeatableJmsApplication.java` — Complete Runnable Code

```java
package com.example.jms;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class RepeatableJmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RepeatableJmsApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            ReceivedTracker tracker) {
        return args -> {
            boolean bothRegistered =
                    registry.getListenerContainer("orders-endpoint") != null
                    && registry.getListenerContainer("audit-endpoint") != null;
            if (!bothRegistered) {
                throw new IllegalStateException("Expected two JMS endpoints");
            }

            template.convertAndSend(
                    "demo.multi.orders", "order-42",
                    msg -> {
                        msg.setStringProperty("eventType", "ORDER");
                        return msg;
                    });

            template.convertAndSend(
                    "demo.multi.audit", "audit-9",
                    msg -> {
                        msg.setStringProperty("eventType", "AUDIT");
                        return msg;
                    });

            if (!tracker.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for both messages");
            }

            System.out.println("Endpoints registered: true");
            System.out.println("Messages: " + tracker.snapshot());
        };
    }
}

@Component
class MultiQueueHandler {

    private final ReceivedTracker tracker;

    MultiQueueHandler(ReceivedTracker tracker) {
        this.tracker = tracker;
    }

    @JmsListener(
            id = "orders-endpoint",
            destination = "demo.multi.orders",
            concurrency = "1"
    )
    @JmsListener(
            id = "audit-endpoint",
            destination = "demo.multi.audit",
            concurrency = "1"
    )
    public void handle(String payload,
                       @Header("eventType") String eventType) {
        if (!"ORDER".equals(eventType) && !"AUDIT".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported eventType");
        }

        tracker.record(eventType + ":" + payload);
    }
}

@Component
class ReceivedTracker {

    private final Set<String> received = ConcurrentHashMap.newKeySet();
    private final CountDownLatch latch = new CountDownLatch(2);

    void record(String value) {
        // Count once per distinct value, avoiding latch decrement on duplicates.
        if (received.add(value)) {
            latch.countDown();
        }
    }

    boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    List<String> snapshot() {
        return received.stream().sorted().toList();
    }
}
```

**Key points explained:**

1. `@EnableJms` explicitly enables annotation-driven endpoints. In Spring Boot with a JMS starter, Boot also configures the appropriate infrastructure; declaring it here makes the mechanism explicit.
2. `MultiQueueHandler` is **one bean** with **one method** `handle(...)`, yet **two `@JmsListener` annotations**.
3. Spring registers `orders-endpoint` consuming from `demo.multi.orders` and `audit-endpoint` consuming from `demo.multi.audit`. `JmsListenerEndpointRegistry` lets you inspect each endpoint by ID.
4. `JmsTemplate.convertAndSend` sends two String payloads as JMS `TextMessage`s; the post-processor sets the `eventType` JMS property so `@Header("eventType") String eventType` can read it in the listener.
5. Both endpoints invoke the same `handle(String, String)`; the method validates a simple schema and records `eventType:payload` in the thread-safe tracker.
6. Listener containers normally process on separate threads without guaranteeing order. `ConcurrentHashMap.newKeySet()` handles concurrent access; `CountDownLatch(2)` waits for two distinct values; `sorted()` keeps output deterministic.
7. The example uses two empty demo queues with only one consumer application. If the queues contain older messages or other competing consumers exist, results may differ; use a clean broker and dedicated queue names.
8. For critical business guarantees, you need transactions, retries/DLQ, and idempotency—not just an in-memory concurrent set. The tracker is solely for the hands-on exercise.

### 8.6. Run Command and Expected Stdout

From the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

If the broker is ready and both messages are received within 10 seconds, the application prints:

```text
Endpoints registered: true
Messages: [AUDIT:audit-9, ORDER:order-42]
```

Spring/Artemis also emit startup and connection logs; the two lines above are **the output printed by the demo code**, not the entire stdout. Arrival order may vary, while the sorted list keeps the `Messages` line in the order shown above.

Stop the broker:

```bash
docker stop jms-repeatable-broker
```

**Limitations:** Does not simulate TLS, secret managers, outbox, database transactions, broker failover, or duplicate redeliveries. Never use lab configuration in production.

## 9. Unit Test Checking Repeatable Annotations

No broker is required to verify that a method actually carries two `@JmsListener` annotations with the declared IDs/destinations. Java reflection supports `getAnnotationsByType()` for `@Repeatable` annotations.

### 9.1. `RepeatableAnnotationTest.java`

```java
package com.example.jms;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.jms.annotation.JmsListener;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RepeatableAnnotationTest {

    @Test
    void oneMethodDeclaresTwoDifferentListenerEndpoints()
            throws Exception {
        Method method = MultiQueueHandler.class.getDeclaredMethod(
                "handle", String.class, String.class);

        JmsListener[] listeners =
                method.getAnnotationsByType(JmsListener.class);

        assertEquals(2, listeners.length);

        Set<String> ids = Arrays.stream(listeners)
                .map(JmsListener::id)
                .collect(Collectors.toSet());
        Set<String> destinations = Arrays.stream(listeners)
                .map(JmsListener::destination)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("orders-endpoint", "audit-endpoint"), ids);
        assertEquals(
                Set.of("demo.multi.orders", "demo.multi.audit"),
                destinations);
    }
}
```

Run:

```bash
mvn test
```

Expected result: **test passes** when code/dependencies are valid. It verifies **annotation metadata**, not that Spring created two containers or that the broker delivered two messages. To verify lifecycle and delivery, you need an integration test booting a Spring context with a real broker—for instance, running the section 8 demo or using Testcontainers and asserting registry + message flow.

### 9.2. Two Test Categories to Distinguish

| Test Type | Real broker? | What it verifies |
| --- | --- | --- |
| Reflection/JUnit test | No | Two annotations exist with distinct IDs/destinations |
| Spring context test + registry | May need broker depending on config | Bean post-processing registers endpoints/containers |
| Artemis integration test | Yes | Real messages arrive from each queue, conversion, ack/retry |
| Failure/redelivery test | Yes | Transaction rollback, duplicates, DLQ, retry policy |
| Load/concurrency test | Yes | Backpressure, throughput, thread safety, ordering |

Never use **only** an annotation unit test to conclude the entire messaging system operates reliably.

## 10. `@JmsListeners` Wrapper and Custom Composed Annotations

Java allows writing directly:

```java
@JmsListeners({
    @JmsListener(id = "orders-a", destination = "orders.a"),
    @JmsListener(id = "orders-b", destination = "orders.b")
})
public void onOrder(String body) {
    // Process...
}
```

**Purpose:** expresses a list of annotations inside a container annotation; it has no shared `destination` attribute and does not change the number of endpoints registered. Because Spring's `@JmsListener` is repeatable, direct repetition in Java 17+ is usually shorter and easier to read.

Spring also supports using `@JmsListener` as a **meta-annotation** in cases where you want to define domain-specific annotations. For example, `@OrdersListener` could preconfigure destination/converter/factory, though you must handle Spring annotation scanning, attribute aliasing, naming conventions, and endpoint IDs carefully. If you simply want to listen to two queues, there is **no need** to create a custom composed annotation; repeating directly suffices.

### 10.1. When the Queue List Changes at Runtime

Repeatable annotations are fixed at **compile time** and endpoints are registered by Spring when the context starts. If you need to read a queue list at runtime from config/service discovery and add/remove endpoints, you need **programmatic endpoint registration** or controlled registry/lifecycle management; do not expect Spring to dynamically "add annotations" to a running Java method.

Spring provides `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `SimpleJmsListenerEndpoint`, and `JmsListenerEndpointRegistry`. That is a different architectural option; avoid dynamic complexity when the requirement is merely two static destinations.

## 11. Transactions, Acknowledge, and Retries: Multiple Endpoints Do Not Share One Transaction

Each annotation has its own container with its own session/transaction. When the broker delivers one message to `orders.queue` and another to `audit.queue`, two invocations of the same method **do not automatically share the same JMS transaction** just by sharing a Java function.

```text
orders.queue  → endpoint orders → Session/transaction A ─┐
                                                         ├─ shared Java method
audit.queue   → endpoint audit  → Session/transaction B ─┘
```

This means:

- If `orders` succeeds and `audit` fails, both queues do not automatically roll back together.
- If the two endpoints use different `containerFactory` beans, acknowledgement and redelivery policies can differ.
- With `AUTO_ACKNOWLEDGE`, do not assume a business exception always forces broker redelivery; check listener container/provider types and ack timing.
- With `sessionTransacted=true` or an appropriate transaction manager, the container can roll back the receive when the handler throws and the broker redelivers per policy.
- Do not put `@Transactional` for a database and assume DB and JMS share one distributed atomic transaction. For dual-writes, consider properly configured outbox/JTA-XA, idempotency, and DLQs.

### 11.1. Configuring a Transacted Factory

This is an optional **configuration snippet**, not part of the runnable demo file in section 8:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean("transactedQueueFactory")
DefaultJmsListenerContainerFactory transactedQueueFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
```

You can then assign `containerFactory="transactedQueueFactory"` on the desired annotations. With Spring Boot, consider using `DefaultJmsListenerContainerFactoryConfigurer` and Boot's factory configuration so you do not accidentally lose existing settings, while also checking `ConnectionFactory` wrappers/pooling/`CachingConnectionFactory`. The example above only illustrates local JMS transactions and concurrency, not all production aspects (recovery, timeouts, DLQ, metrics).

### 11.2. Do Not Swallow Errors and Return Success

If the handler catches an exception and does not rethrow it, the container may treat the message as processed and commit/ack:

```java
// Anti-pattern, illustrative only:
try {
    doBusinessWork(payload);
} catch (RuntimeException ex) {
    logger.warn("failed", ex);
    // Not rethrowing/marking rollback: container may ack.
}
```

Not every error should be retried forever: invalid JSON schemas or authorization failures need classification, alerting, and a DLQ/quarantine. Repeatable annotations do not solve retries or poison messages automatically.

## 12. Concurrency and Thread Safety of a Shared Method

**One bean method does not imply sequential execution.** Both endpoints can be invoked **at the same time** on two threads, and a single endpoint can have multiple consumers under concurrency. Common pitfalls:

```java
@Component
class UnsafeHandler {

    private int processedCount = 0; // Not thread-safe.

    @JmsListener(destination = "queue.a")
    @JmsListener(destination = "queue.b")
    public void onMessage(String payload) {
        processedCount++; // Race when two containers invoke concurrently.
    }
}
```

Prefer stateless handlers, or update state via thread-safe/transactional mechanisms:

```java
@Component
class SafeHandler {
    private final AtomicLong processed = new AtomicLong();

    @JmsListener(id = "a", destination = "queue.a")
    @JmsListener(id = "b", destination = "queue.b")
    public void onMessage(String payload) {
        process(payload);  // business service must be thread-safe.
        processed.incrementAndGet();
    }
}
```

This is an **architectural snippet**: `AtomicLong` requires `java.util.concurrent.atomic.AtomicLong`, and `process` is an undeclared business method. An atomic counter **only** fixes races on the counter; it does not replace DB transactions or idempotency on redelivery.

**Total consumers** can grow larger than expected: three annotations with concurrency `"2-5"` can create up to **15 consumer instances**, depending on factory scaling and provider capacity. Never look only at the method name and forget to count each endpoint when budgeting connections/sessions/threads and broker load.

### 12.1. Ordering Across Multiple Queues

Even if messages within each queue are delivered in order by the broker, processing across two endpoints **has no global order**. If business ordering per orderId/aggregateId is required, use appropriate partitioning/grouping/serialization and deliberate concurrency. Adding consumers typically increases throughput at the expense of reasoning about processing order.

### 12.2. Idempotency When Two Queues Deliver the Same Event

If `orders.created` and `orders.replayed` both carry eventId `evt-42`, the shared handler may receive it twice. That is not a framework bug. The handler must deduplicate by eventId/business key if side effects must happen only once, or distinguish message types if replays have different semantics.

## 13. Monitoring, Configuration, Lifecycle, and Troubleshooting

### 13.1. Inspecting Endpoint IDs

You can display IDs using the registry:

```java
Set<String> ids = registry.getListenerContainerIds();
System.out.println(ids);
```

This snippet belongs in a bean with `JmsListenerEndpointRegistry` injected and requires importing `java.util.Set`. **Set order is not guaranteed**; do not use unsorted output as a rigid assertion. Use `getListenerContainer("orders-endpoint")` to fetch a specific container; `start()`/`stop()` can be invoked in controlled operational tooling, and stopping one endpoint does not stop the remaining endpoints.

### 13.2. Metrics Should Be Separated by Endpoint/Destination

Track:

- Endpoint/container ID, destination, runtime state.
- Active consumer count, concurrency, session/connection count, worker thread pool.
- Queue depth, consumer lag, redeliveries, DLQ, timeouts/recovery.
- Decode/schema/version errors, business exceptions, retry counts.
- Processing latency and throughput per endpoint.

If logs record only the method name `handle`, errors from two different queues get mixed together; include sanitized source/destination metadata in logs. Never use full payloads or secret tokens as metric labels due to cardinality and privacy risks.

### 13.3. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Method is not invoked | Missing `@EnableJms`/auto-config, bean not scanned | Check bean, annotation infrastructure, and registry |
| Only queue A works | Wrong destination B name, broker routing missing, missing permissions | Check ID/container, destination, ACLs, and broker queue depth |
| Two annotations yet only one message processed | Both read the same **queue** | These are competing consumers; use topic/fan-out if needed |
| Two messages arrive yet handler fails decoding on one queue | Two queues have different schemas | Split handlers or unify conversion/schemas |
| Startup fails with duplicate endpoint ID | Two annotations use the same `id` | Assign distinct IDs |
| Missing listener container factory | No default or `containerFactory` points to wrong bean | Declare factory with the right name |
| `@JmsListener(destination="a,b")` does not listen to two queues | Destination string is one name, not a list | Write two annotations |
| One annotation uses selector yet no messages arrive | Producer did not set matching JMS property | Check selector and properties, not just JSON body |
| Assuming `concurrency=5` processes each message 5 times | Concurrency is consumer count, not fan-out | Review queue/topic semantics |
| Count/sum in listener is wrong | Shared mutable field and concurrent callbacks | Stateless handler/atomic/transaction-safe state |
| One queue redelivers heavily while the other is fine | Different factory/ack/transaction or message validity | Compare per-endpoint configurations |
| Cannot tell source in logs | Shared method omits metadata | Log sanitized destination/source/correlation |
| Producer sends successfully yet handler never runs | Broker has no consumer or topic subscription unready | Check readiness and delivery; do not confuse send with processing |
| Infinite retries on poison message | Bad schema/logic, no DLQ policy | DLQ/quarantine, bounded retries, alerts |
| Endpoint IDs differ across environments | Letting Spring auto-generate IDs | Assign explicit meaningful `id` |
| Listener stops receiving after broker password rotation | Cached connections/credentials not rotated properly | Check security, recreate connections per runbook |

### 13.4. When Should You NOT Use Repeatable `@JmsListener`?

Split into separate methods if:

- Queues have different message contracts/validation rules.
- Each queue has very different transaction, retry, DLQ, or response semantics.
- Separate source-specific logging and business auditing are needed and easily confused when merged.
- Different authorization/multi-tenant contexts cannot be distinguished safely from the payload.
- Different business owners exist: a shared method becomes a coupling point.

You can still reuse code via two adapter methods calling the same `BusinessService.process(...)`, instead of stacking multiple annotations directly on one method.

## 14. Deployment and Code Review Checklist

- [ ] Every `@JmsListener` on the same method genuinely needs the same payload contract/handler.
- [ ] Explicitly verified whether each destination is a **queue or topic**.
- [ ] Each annotation has a distinct `id` (or auto-generated IDs are intentionally accepted).
- [ ] Each endpoint's `containerFactory` exists with the right provider/ack/transaction/recovery settings.
- [ ] `concurrency` is budgeted **per endpoint**; total consumers/threads have been summed.
- [ ] If selectors are used, producers set the exact JMS headers/properties.
- [ ] Never expect two consumers on the same queue to receive two copies of one message.
- [ ] Never use `destination="q1,q2"` as a queue list.
- [ ] Handler is thread-safe and does not hold JMS Sessions, producers, or improperly scoped mutable state.
- [ ] Business schema validation, versioning, and unknown event type handling are in place.
- [ ] Idempotency, redelivery/retry bounds, and DLQ/quarantine exist.
- [ ] Monitoring breaks down by endpoint ID and destination, not just method name.
- [ ] Tests cover registry IDs, receiving from **all destinations**, and failure handling.
- [ ] For production, secrets, TLS, ACLs, and broker provisioning are configured.

## 15. Review Questions

**1. Can two `@JmsListener` annotations be placed on one method?**  
Yes. `@JmsListener` is a repeatable annotation and Spring creates a separate listener endpoint/container for each declaration.

**2. Is `@JmsListeners` required?**  
No on Java 17+. Two directly repeated `@JmsListener` annotations suffice; `@JmsListeners({...})` is merely the equivalent container annotation.

**3. Are two annotations on one method a single consumer reading two queues?**  
No. The two endpoints have separate containers/consumers, while invoking the same shared method.

**4. Do two listeners on one queue cause every message to run twice?**  
No under standard queue semantics; they compete to receive. Redeliveries/duplicates can still occur on errors/transactions, not from repeating annotations.

**5. If two independent systems must both receive an event, what should you do?**  
Design topic/subscriptions or appropriate broker routing/fan-out; do not duplicate annotations on a queue expecting broadcast.

**6. Must `id` values differ?**  
Yes, when specified; container IDs in a registry must be unique. Spring can auto-generate them if omitted.

**7. Can different `containerFactory` beans be used for two annotations?**  
Yes. However, different converters, ack/transaction modes, and recovery policies can affect the shared method.

**8. What does `concurrency="2-4"` mean?**  
It is the consumer limit for **the corresponding endpoint** per factory capabilities, not the number of times each message is processed.

**9. Does `selector` read `eventType` inside a JSON body?**  
Not arbitrarily. JMS selectors filter headers/properties; producers must set the appropriate properties.

**10. Why must a shared method be thread-safe?**  
Both containers can invoke the same bean concurrently on different threads; never use unprotected mutable fields.

**11. Can messages with different schemas be received by the same method?**  
Technically yes if adapters/converters and validation handle them, though it is error-prone. If business logic differs, split methods calling a shared service.

**12. When should dynamic endpoint registration be used?**  
When the destination list genuinely needs to change at runtime; repeatable annotations declare static endpoints in code.

## 16. Official References

1. [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
2. [Spring Framework — JmsListener annotation API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
3. [Spring Framework — JmsListeners container annotation API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListeners.html)
4. [Spring Framework — JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
5. [Spring Framework — JMS Overview](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
6. [Spring Framework — JMS Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
7. [Spring Boot 3.5 — JMS with Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Spring — Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
9. [Jakarta Messaging 3.1 Specification: Queue and Topic semantics, message selectors](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
10. [Apache ActiveMQ Artemis — Docker guide](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)