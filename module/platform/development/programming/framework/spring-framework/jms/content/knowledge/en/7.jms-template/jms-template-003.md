# JmsOperations as a Contract for Application Components in Spring JMS

## 1. The problem: what should business components depend on?

In Spring JMS, the familiar way to send messages is to inject `JmsTemplate` directly and call `convertAndSend(...)`. That works well, but sometimes an application component only needs the **ability to send/receive messages** without knowing every configuration detail of a concrete template.

Spring provides the **`org.springframework.jms.core.JmsOperations`** interface to express this contract. `JmsTemplate` is the standard implementation of this interface. Instead of forcing every service to declare `JmsTemplate`, we can constructor-inject `JmsOperations`:

~~~java
private final JmsOperations jmsOperations;
~~~

And call operations on the contract:

~~~java
jmsOperations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
~~~

Practical benefits: the application layer focuses on the JMS operations it needs; connection configuration, converters, QoS, and resource lifecycle live on the Spring/implementation side; and in unit tests, you can mock a single interface without starting a broker.

**Exact scope:** `JmsOperations` is still a **Spring JMS contract**, not a pure business interface and not a standard `jakarta.jms` interface. It reduces coupling to the concrete `JmsTemplate` class, but the application layer still depends on Spring. If you want the domain to be completely independent of JMS, add a dedicated business port, such as `OrderEventPort`.

## 2. Position of JmsOperations in the architecture

~~~text
OrderEventPublisher (@Service)
  |
  | constructor dependency
  v
JmsOperations             <-- Spring JMS interface
  ^
  | implements
  |
JmsTemplate               <-- Spring implementation
  |
  +-- ConnectionFactory  <-- Artemis / broker provider
  +-- DestinationResolver
  +-- MessageConverter
  +-- QoS, transaction / timeout / resource management
  |
  v
Jakarta JMS Session / MessageProducer
  |
  v
Broker Queue / Topic
~~~

In an application component, responsibilities typically are:

1. Choosing the event or command to send based on business processing results.
2. Selecting the configured contract destination.
3. Creating the necessary payload and application metadata.
4. Calling a `JmsOperations` operation.
5. Handling errors or returning results according to business policy.

Tasks such as configuring broker host/port, username/password, pooling, caching, or setting `JmsTemplate#setReceiveTimeout(...)` belong to **infrastructure configuration**, not the responsibility of the event-publishing service.

Example layering:

| Component | Role |
| --- | --- |
| `OrderService` | Determines when an order is created |
| `OrderEventPublisher` | Translates business intent into payload/metadata and calls `JmsOperations` |
| `JmsOperations` | Declares the JMS operations the publisher is allowed to invoke |
| `JmsTemplate` | Executes operations, manages sessions/producers, and translates JMS exceptions into Spring exceptions |
| `ConnectionFactory` | Creates connections to the provider |
| Broker | Routes, stores, and distributes messages |

**Do not confuse:** the `JmsOperations` interface is not a listener container. `@JmsListener` is handled by Spring's listener mechanism; listeners still require a properly configured factory/container.

## 3. What is JmsOperations, and what is JmsTemplate?

`JmsOperations` resides in the package:

~~~java
import org.springframework.jms.core.JmsOperations;
~~~

It provides template-level JMS operations, including:

| Group | Representative API | Meaning |
| --- | --- | --- |
| Send a raw JMS message | `send(String, MessageCreator)` | Creates a `jakarta.jms.Message` via callback and sends it |
| Convert and send an object | `convertAndSend(String, Object)` | Uses `MessageConverter` to create a JMS message |
| Adjust message after conversion | `convertAndSend(String, Object, MessagePostProcessor)` | Adds headers/properties before sending |
| Synchronous receive | `receive(String)` | Receives a `jakarta.jms.Message` from the specified destination |
| Receive and convert | `receiveAndConvert(String)` | Receives and converts the JMS message into an object |
| Receive with selector | `receiveSelected(String, String)` | Filters messages using a JMS selector |
| Request/reply | `sendAndReceive(String, MessageCreator)` | Sends a request and waits for a reply via a temporary queue |
| Queue browsing | `browse(String, BrowserCallback<T>)` | Browses a queue without consuming messages |
| Session/producer-level callback | `execute(...)` | Lower-level operations when the methods above are not enough |

There are additional overloads accepting a `Destination`, using the default destination, or taking a selector, depending on the method. **Do not memorize this table as the complete signature list**; when you need an exact API, consult the Javadoc for your project's Spring Framework version.

`JmsTemplate` is the concrete class that implements these calls and provides configuration setters/getters such as `setDefaultDestinationName(...)`, `setReceiveTimeout(...)`, `setPubSubDomain(...)`, and `setExplicitQosEnabled(...)`. These setters are not operations promised by the `JmsOperations` interface.

~~~java
// The application class only asks for the contract:
public OrderEventPublisher(JmsOperations operations) {
    this.operations = operations;
}
~~~

Spring injects a bean implementing the interface, typically the `JmsTemplate` auto-configured by Spring Boot, provided there is **a single matching candidate** in the container. Java needs no extra adapter just to cast, because `JmsTemplate implements JmsOperations`.

### 3.1. Comparison with JmsMessagingTemplate / JmsMessageOperations

Similar names, but they belong to two different abstraction styles:

- `JmsOperations`: works with Jakarta JMS types such as `Message`, `Session`, `MessageCreator`.
- `JmsTemplate`: implementation of `JmsOperations`.
- `JmsMessageOperations`: a Spring Messaging-style interface using concepts such as `org.springframework.messaging.Message<?>`.
- `JmsMessagingTemplate`: a JMS-backed Spring Messaging implementation, not another name for `JmsTemplate`.

If a service needs direct access to JMS headers or `MessagePostProcessor` callbacks, `JmsOperations` fits well. If the rest of the application standardizes on Spring Messaging `Message<?>`, consider `JmsMessageOperations`. Base interface selection on the abstraction language the application layer needs, not on which name is shorter.

## 4. Why does injecting an interface improve testing?

Compare:

~~~java
// Depends on a concrete implementation:
private final JmsTemplate jmsTemplate;

// Depends on an operations contract:
private final JmsOperations jmsOperations;
~~~

Both are valid, and a `JmsTemplate` can still be mocked. The practical advantage of the interface is that unit tests can state explicitly **which capabilities this class requires**, create a mock/stub of the contract, and verify requests sent. You do not need to mock `ConnectionFactory`, `Session`, and `MessageProducer`, or start a real broker in unit tests.

Benefits to understand accurately:

- **Easy mocking**: verify the destination, body, and headers/properties requested by the service.
- **Reduced coupling to implementation setters**: application services cannot arbitrarily mutate a shared template.
- **Easier configuration changes**: adjust caching, timeouts, converters, and brokers without rewriting constructors/services as long as the contract holds.
- **Clear responsibility boundary**: the service builds the message; infrastructure executes JMS.

**No magic:** unit tests with a mocked `JmsOperations` **do not prove** that the JMS converter works, the broker exists, ACLs are right, messages are actually received, or ACKs succeed. Those require integration tests with a broker.

## 5. Sample project: Java 17 + Spring Boot 3.3 + Artemis

We will build a complete example: when the application starts, `OrderEventPublisher` receives `JmsOperations` via its constructor and sends an order event to a Queue; `OrderEventListener` reads and prints the result. Then we write **brokerless unit tests** to verify the contract.

Example scope: a single Queue `orders.events`, a text message, and illustrative metadata. No JPA or DB transactions are used so they do not get mixed up with the JMS contract.

### 5.1. Start a local broker

Docker is required. Example using the official Artemis image:

~~~bash
docker run --detach --rm --name artemis-ops-demo -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to finish starting:

~~~bash
docker logs artemis-ops-demo
~~~

The `demo/demo` credentials are for local use only. If the broker does not auto-create Queues, you must create `orders.events` and grant send/consume permissions beforehand. Using a sample container does not certify persistence or security policies for production.

### 5.2. Build scripts

File `settings.gradle`:

~~~groovy
rootProject.name = 'jms-operations-contract'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    useJUnitPlatform()
}
~~~

With Spring Boot 3, JMS code must import `jakarta.jms.*`. Do not mix in older `javax.jms.*` client libraries. Use compatible Gradle 8.x and JDK 17+. Versions here are pinned for example consistency and do not imply they are the latest releases.

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s
app.jms.orders-destination=orders.events
~~~

Spring resolves expressions `${KEY:default}` in this lesson using the standard `$` + `{KEY:default}` syntax. In the saved Markdown source, those lines carry the exact Spring property placeholder syntax. In production, remove the `demo` fallback credentials and pass values from a secret manager.

`spring.jms.pub-sub-domain=false` enables Queue mode. `spring.jms.template.receive-timeout=2s` applies to **synchronous receiving** via `JmsTemplate`; it does not turn publishing into a 2-second wait and is not a general listener timeout.

### 5.3. Entry point and execution scenario

File `src/main/java/demo/jms/JmsOperationsApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsOperationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsOperationsApplication.class, args);
    }

    @Bean
    CommandLineRunner publishDemo(OrderEventPublisher publisher) {
        return args -> publisher.publishOrderCreated("O-42");
    }
}
~~~

`CommandLineRunner` here is simply a way to trigger once on startup so learners can see the message move. A production application should invoke the publisher when the business event actually occurs rather than re-emitting an event on every restart.

### 5.4. Application component depending on JmsOperations

File `src/main/java/demo/jms/OrderEventPublisher.java`:

~~~java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsOperations operations;
    private final String destination;

    public OrderEventPublisher(
            JmsOperations operations,
            @Value("${app.jms.orders-destination}") String destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void publishOrderCreated(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        String body = "ORDER_CREATED:" + orderId;

        operations.convertAndSend(destination, body, message -> {
            message.setStringProperty("eventType", "order.created");
            message.setJMSCorrelationID("order-" + orderId);
            return message;
        });
    }
}
~~~

In this code, the key point is that the field and constructor **accept `JmsOperations`**, without requiring `JmsTemplate`. Spring Boot auto-configures `JmsTemplate` as the implementation when the Artemis starter and `ConnectionFactory` are available.

Line-by-line explanation:

1. `@Value(...)` reads the destination name from configuration; the service does not need to know the Queue host/port.
2. Validate `orderId` before touching the broker; invalid input throws an exception immediately at the application layer.
3. `convertAndSend(String, Object, MessagePostProcessor)` belongs to the `JmsOperations` interface. It uses the template's converter to turn the `String` into a JMS `TextMessage`.
4. The `MessagePostProcessor` callback attaches the `eventType` property and `JMSCorrelationID` header **after conversion, before sending**.
5. The provider generates broker-controlled headers such as `JMSMessageID`. Do not set them manually in the service.

Calling through the interface allows writing tests that verify the exact intent—“which order event body and metadata are sent”—without opening any network connection.

### 5.5. Receiving listener operating independently

File `src/main/java/demo/jms/OrderEventListener.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @JmsListener(destination = "${app.jms.orders-destination}")
    public void onOrderEvent(String body) {
        System.out.println("RECEIVED: " + body);
    }
}
~~~

The listener belongs to Spring's `@JmsListener` mechanism; you are **not** required to inject `JmsOperations` to consume messages via an asynchronous listener. Spring Boot + `@EnableJms` create the required receiving infrastructure, while `JmsOperations` serves active operations in sending/synchronous-receiving components.

### 5.6. Running and observing

~~~bash
gradle test
gradle bootRun
~~~

With the broker running, the Queue auto-created/existing, and the user authorized, the application console will print:

~~~text
RECEIVED: ORDER_CREATED:O-42
~~~

This is **the line printed by the sample's listener**; Spring and broker log ordering varies by environment. The publisher does not print an extra success line. Each startup triggers one publish via `CommandLineRunner`; if another consumer is competing on the Queue, this sample's listener is not guaranteed to be the consumer that receives the message.

When finished:

~~~bash
docker stop artemis-ops-demo
~~~

**What the check means:** the received log shows that connection, sending, routing, and the listener callback worked under test conditions. Having the listener print a log does not replace business transaction confirmation and idempotency policies.

## 6. Unit tests focused on the contract, without a broker

This is where `JmsOperations` shines. The tests only verify **how the service uses the contract**; they do not start a Spring `ApplicationContext`, inject a connection factory, or require Docker.

File `src/test/java/demo/jms/OrderEventPublisherTest.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jms.core.JmsOperations;
import org.springframework.jms.core.MessagePostProcessor;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderEventPublisherTest {

    @Test
    void publishesCorrectDestinationBodyAndMetadata()
            throws JMSException {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(
                operations, "orders.events");

        publisher.publishOrderCreated("O-42");

        ArgumentCaptor<MessagePostProcessor> captor =
                ArgumentCaptor.forClass(MessagePostProcessor.class);

        verify(operations).convertAndSend(
                eq("orders.events"),
                eq("ORDER_CREATED:O-42"),
                captor.capture());

        // Invoke the callback passed to JmsOperations:
        Message message = mock(Message.class);
        assertSame(message, captor.getValue()
                .postProcessMessage(message));

        verify(message).setStringProperty(
                "eventType", "order.created");
        verify(message).setJMSCorrelationID("order-O-42");
    }

    @Test
    void rejectsBlankOrderIdBeforeSending() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(
                operations, "orders.events");

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publishOrderCreated("  "));

        verifyNoInteractions(operations);
    }
}
~~~

Command:

~~~bash
gradle test
~~~

**These two tests do not start a broker.** The first test verifies the `MessagePostProcessor` overload, checks destination name and body, and invokes the callback with a mock JMS `Message` to verify headers/properties. The second test ensures invalid input is rejected before any JMS call occurs.

When passing, Gradle reports completion of the test task; log details depend on Gradle configuration. There is no need to fake a `JMSMessageID` or simulate an ACK, because those are not part of the contract the service is testing.

### 6.1. Why not mock JMS Session directly?

If a service directly called:

~~~java
// Illustrates raw API, excluding resource management:
Connection connection = connectionFactory.createConnection();
Session session = connection.createSession();
MessageProducer producer = session.createProducer(destination);
~~~

A unit test would have to set up multiple mocks and simulate the connection/session/producer lifecycle, shifting focus toward technical plumbing rather than business intent. `JmsOperations` hides that behind a send operation verifiable with Mockito.

However, if the application needs a specific JMS feature not exposed at the template level, `JmsOperations.execute(SessionCallback<T>)` still permits session-level callbacks. Use it only when needed, because lower-level operations increase infrastructure detail inside the service.

## 7. Distinguishing unit, integration, and end-to-end tests

| Test type | Real components | What it actually proves |
| --- | --- | --- |
| Unit test with mocked `JmsOperations` | Only publisher and test doubles | Service invokes the right destination, body, and metadata |
| Integration test with `JmsTemplate` and a real broker | Spring JMS + converter + broker | Messages can be sent/received and converters work |
| End-to-end with DB, consumer, and retry/ACK | Complete business workflow | End-to-end processing/commit/idempotency per contract |

If unit tests pass yet consumers do not receive messages, inspect broker configuration, Queue/Topic mode, permissions, selectors, converters, and the listener container. That is not a failure of unit tests; unit tests simply have a bounded scope.

When integration testing is needed, use an isolated broker in a test environment or appropriate Testcontainers. Avoid mocking an entire broker with Mockito and concluding that delivery semantics are correct.

## 8. When to use convertAndSend, send, receive, and sendAndReceive?

### 8.1. convertAndSend for simple data

~~~java
operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
~~~

Uses `JmsTemplate`'s `MessageConverter`. By default, `String` usually becomes `TextMessage`; if passing a DTO without an appropriate JSON converter, it may use Java serialization or fail depending on the object/provider. **Do not assume POJOs always become JSON.**

When a JSON schema is required, define a clear converter and verify content compatibility between producer and consumer. Converter configuration belongs in infrastructure, not setters on `JmsOperations`.

### 8.2. send when creating the JMS Message manually

~~~java
operations.send("orders.events", session -> {
    var message = session.createTextMessage("ORDER_CREATED:O-42");
    message.setStringProperty("eventType", "order.created");
    return message;
});
~~~

This is an **illustrative snippet inside a method that has an `operations` variable**; it is not a standalone Java file. `send` gives you control to create `TextMessage`, `BytesMessage`, or other message types via the JMS `Session`.

Consider `send` when exact control over message/body type is required. For plain `String` data, `convertAndSend` is shorter and expresses intent better.

### 8.3. receive / receiveAndConvert are synchronous

~~~java
Object payload = operations.receiveAndConvert("orders.events");
if (payload == null) {
    // No message received before timeout expired.
}
~~~

`receiveAndConvert` and `receive` can **block the thread**. If the timeout expires, the result can be `null`; this case must be handled. Avoid calling them on HTTP request threads without an SLA or appropriate timeout, as they can block threads for a long time.

Synchronous receive configuration, for example:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

For services that consume messages continuously, a listener container + `@JmsListener` is generally better than a hand-written `receive` loop. Do not use `receiveAndConvert` as a way to “peek” at a production Queue, because this operation **consumes the message**.

### 8.4. receiveSelected and selectors

~~~java
Object selected = operations.receiveSelectedAndConvert(
        "orders.events", "eventType = 'order.created'");
~~~

A JMS selector filters on **properties and certain supported standard headers**, not directly inside a JSON body. The `eventType` property in the producer example was set with the right `String` type so selectors can match it.

Like `receiveAndConvert`, this call **receives and consumes** the message and can block up to the timeout. When multiple consumers share a Queue, a consumer's selector determines which messages it can receive.

### 8.5. browse does not consume messages

~~~java
Integer count = operations.browse("orders.events",
        (session, browser) -> {
            int result = 0;
            var messages = browser.getEnumeration();
            while (messages.hasMoreElements()) {
                messages.nextElement();
                result++;
            }
            return result;
        });
~~~

This is an illustrative snippet. `browse` works with **Queues** and does not remove messages like `receive`. However, Queue contents can change while browsing; counts from `QueueBrowser` are not an exact snapshot/metric under concurrent load. For monitoring production backlogs, prefer broker metrics.

### 8.6. sendAndReceive for request/reply

~~~java
Message response = operations.sendAndReceive(
        "inventory.requests",
        session -> session.createTextMessage("CHECK:O-42"));
~~~

This is also a snippet inside a method with an `operations` variable. It sends a request and waits for a response via a temporary queue created by the template; the receiving side must have a listener that actually sends the reply to `JMSReplyTo`. The result can be `null` if no reply arrives before the timeout.

Do not use request/reply merely to verify that the broker “received the message” if the business case only needs to publish an event. `sendAndReceive` is a different exchange pattern that consumes waiting resources and requires timeout, error, and correlation management.

## 9. The contract does not include JmsTemplate configuration

A `JmsOperations` parameter **does not** expose these setters:

~~~java
// Only when configuring JmsTemplate itself:
jmsTemplate.setPubSubDomain(false);
jmsTemplate.setReceiveTimeout(2_000L);
jmsTemplate.setDefaultDestinationName("orders.events");
~~~

This is a **configuration snippet**, not for use inside `OrderEventPublisher`. These options can be set via Spring Boot application properties or a centrally managed `@Bean JmsTemplate`.

Having a service “downcast” to tweak configuration is a sign of a broken boundary:

~~~java
// Do not do this in business code:
((JmsTemplate) operations).setReceiveTimeout(2_000L);
~~~

It defeats the benefit of the interface and can mutate a shared singleton used concurrently by multiple threads. If a service genuinely needs an implementation-only operation or dedicated configuration, move that requirement into an appropriate infrastructure adapter/bean.

### 9.1. If Spring has multiple JmsOperations beans

In a single-broker application, the auto-configured `JmsTemplate` is usually a sufficient candidate. In systems with multiple brokers/destination groups, there may be multiple `JmsOperations` beans. Injection by type alone can then cause `NoUniqueBeanDefinitionException`.

Example **when a bean named `orderJmsTemplate` already exists**:

~~~java
public OrderEventPublisher(
        @org.springframework.beans.factory.annotation.Qualifier(
                "orderJmsTemplate") JmsOperations operations,
        @Value("${app.jms.orders-destination}") String destination) {
    this.operations = operations;
    this.destination = destination;
}
~~~

The snippet above illustrates bean selection. It replaces the **current constructor** if the real project has multiple factories; do not add both constructors to the same sample without adjusting wiring. `@Qualifier` only works if the bean name/qualifier is actually defined in the container; it does not create a bean on its own.

Manage `ConnectionFactory`, converters, and destination naming in one place so the application does not accidentally send messages to the wrong broker.

## 10. JmsOperations and cleaner business boundaries

Injecting `JmsOperations` is usually sensible when the application layer accepts a Spring dependency. If the goal is a domain/service layer **independent of messaging frameworks**, define an interface in **business language**:

~~~java
// Dedicated domain/application port, illustrative:
public interface OrderEventPort {
    void publishOrderCreated(String orderId);
}
~~~

JMS adapter:

~~~java
// Illustrates architectural relationship only; does not replace
// the sample project above unless OrderEventPort is created.
public final class JmsOrderEventAdapter implements OrderEventPort {
    private final JmsOperations operations;

    public JmsOrderEventAdapter(JmsOperations operations) {
        this.operations = operations;
    }

    @Override
    public void publishOrderCreated(String orderId) {
        operations.convertAndSend(
                "orders.events", "ORDER_CREATED:" + orderId);
    }
}
~~~

Now an `OrderService` can inject `OrderEventPort` without knowing about JMS. The adapter implements it using `JmsOperations`; if you later migrate to Kafka, swapping the adapter does not affect the business service as long as the business contract holds.

**Three coupling levels:**

| Level | Component depends on | Purpose |
| --- | --- | --- |
| Implementation | `JmsTemplate` | Needs concrete configuration/implementation APIs as well |
| Spring contract | `JmsOperations` | Wants a set of JMS operations, easy mocking, and no concrete class coupling |
| Domain port | `OrderEventPort` | Wants business code independent of framework/broker |

Not every application needs an extra domain port. For small projects, `JmsOperations` is a lightweight, clear boundary. When you need to swap messaging stacks or unit-test the domain in total isolation, a domain port offers clearer value.

## 11. Errors, transactions, retries: limits of the interface

Calls such as `convertAndSend` can throw `org.springframework.jms.JmsException` (unchecked), translated by `JmsTemplate` from provider/JMS errors. Services may catch errors when they genuinely have a response policy, but should never swallow an error and report business success.

~~~java
// Illustrative snippet inside a method:
try {
    operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
} catch (org.springframework.jms.JmsException failure) {
    // Log safely and apply appropriate retry/dead-letter/outbox policy.
    throw failure;
}
~~~

**Do not infer** that a normal method return means the consumer has processed or ACKed the message. It only indicates that the send operation completed per the template/provider contract at that moment.

Exercise special caution in these scenarios:

- **Network drops right during send**: the producer may not know whether the broker received the message; retrying can create duplicates.
- **Consumer throws an exception**: transaction/ACK mode determines whether the message is redelivered.
- **DB commits then JMS send fails**: without appropriate transactions/outbox, the DB state may have changed while no message was sent.
- **JMS send succeeds then DB rolls back**: this can also leave inconsistent state if the two operations are not in a coordinated transaction.
- **Thread safety**: `JmsTemplate` is a suitable shared singleton once configured; do not mutate setters dynamically per request.

For critical business events, consider **transactional outbox**, idempotency keys, retry/backoff, and dead-letter policies. The `JmsOperations` interface does not automatically guarantee system-wide exactly-once delivery.

## 12. Common misconceptions

| Misconception | Reality |
| --- | --- |
| “Injecting the interface removes the Spring dependency” | `JmsOperations` still lives in `org.springframework.jms.core` |
| “JmsOperations creates JMS connections itself” | `JmsTemplate` and `ConnectionFactory` execute and manage resources |
| “Each service must define its own JmsOperations bean” | A matching `JmsTemplate` bean already satisfies the interface; Boot can auto-configure it |
| “JmsOperations and JmsMessagingTemplate are the same” | Different abstractions: Jakarta JMS messages vs. Spring Messaging messages |
| “convertAndSend with a DTO always produces JSON” | Depends on the configured `MessageConverter` |
| “Passing a mock test means the broker received it” | Mocks only verify interactions with the contract |
| “receiveAndConvert peeks without removing the message” | It actually consumes from the destination |
| “receive cannot block because it belongs to an interface” | It is a synchronous receive operation and requires a timeout |
| “sendAndReceive only sends a request without needing a response listener” | It requires a receiver sending a reply and needs a timeout |
| “When JMS send returns, the receiver has committed” | Sending, receiving, and ACK/commit are separate steps |
| “Qualifier automatically picks a broker based on destination” | Qualifier selects a registered bean; it does not route messages by name |
| “Catching and ignoring JmsException prevents data loss” | It can silently drop events; an error-handling policy is required |

## 13. API selection suggestions by scenario

- **Application service only publishing notifications**: inject `JmsOperations`, call `convertAndSend` or `send`, and externalize destination config.
- **Need headers/properties**: use `convertAndSend(..., MessagePostProcessor)` or `send(..., MessageCreator)` overloads.
- **Continuously consuming worker**: use `@JmsListener` instead of a hand-rolled `receiveAndConvert` loop.
- **Task that occasionally polls a Queue**: use `JmsOperations.receiveAndConvert`, but set a timeout and handle `null`.
- **Explicit request/reply requirement**: consider `sendAndReceive`, configure timeout, and ensure a replying consumer.
- **Business code must be Spring-independent**: define a domain/application port and have a JMS adapter depend on `JmsOperations`.
- **Want to tune QoS/caching/transactions**: do it in factory, `JmsTemplate`, and listener configuration, not in the sending service.
- **Need to prove actual delivery**: write integration tests with a broker alongside unit tests mocking the interface.

## 14. Self-check questions

**Question 1.** Why can a constructor taking `JmsOperations` still be injected with a `JmsTemplate`?

Because `JmsTemplate` implements `JmsOperations`; Spring injects a bean of a compatible type.

**Question 2.** Does injecting `JmsOperations` make the application class independent of Spring Framework?

No. It is a Spring JMS interface. To keep the domain framework-independent, create a dedicated port.

**Question 3.** What does a unit test mocking `JmsOperations` verify?

It verifies that the service invokes the right method/destination/payload/metadata and error behavior at the application layer; it does not prove broker connectivity.

**Question 4.** Why must `receiveAndConvert` have a timeout?

It is a synchronous call that can block if the queue has no messages; it returns `null` when the wait expires.

**Question 5.** Is `@JmsListener` a method on the `JmsOperations` interface?

No. It is an endpoint managed separately by Spring's listener infrastructure.

**Question 6.** Should you cast `JmsOperations` to `JmsTemplate` to change timeouts per request?

No. Put timeouts in infrastructure/configuration; a shared template should not be dynamically mutated by business logic.

**Question 7.** Does `JmsOperations.sendAndReceive` need a responding consumer?

Yes. It creates a temporary queue for replies, but still requires the receiving side to actually send a response.

**Question 8.** If a publish call succeeds, can you omit duplicate-handling logic on the consumer?

No. Redelivery/retries, transactions, and network failures can cause duplicate processing; proper idempotency is required.

## 15. Official documentation

- Spring Framework 6.1 — Javadoc `JmsOperations` (full contract and signatures): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsOperations.html
- Spring Framework — Javadoc `JmsTemplate`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — Using Spring JMS, JmsTemplate, and listeners: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `@JmsListener`: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS support and auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Boot — Application properties (JMS template/listener): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/

**Remember:** `JmsOperations` is the **behavioral interface** that application services can depend on; `JmsTemplate` is the **implementation** managing actual JMS work; mocking the interface keeps unit tests focused on send/receive intent. If you want your application completely independent of JMS, add your system's own **domain port**.
