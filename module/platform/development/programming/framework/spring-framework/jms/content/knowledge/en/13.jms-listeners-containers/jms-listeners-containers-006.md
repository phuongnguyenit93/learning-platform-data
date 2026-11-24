# From Received Message to Invoking the Handler Method in Spring JMS

## 1. Which Layers Does a Message Pass Through?

Suppose a producer places a `TextMessage` containing `ORDER-1001` into the `orders.in` queue. In a Spring application, we only write:

```java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }
}
```

This is **a Spring-managed bean**, not a standalone Java program. The important question is: **who receives the message from the broker, who invokes `onOrder`, and why does the Java `String` parameter receive the contents of `TextMessage`?**

The answer is a pipeline made up of several components:

```text
                      APPLICATION STARTUP
@EnableJms / Spring Boot configuration
          |
          v
Find beans and methods with @JmsListener
          |
          v
JmsListenerEndpoint (bean, method, destination, id, selector...)
          |
          v
JmsListenerContainerFactory creates MessageListenerContainer
          |
          v
Container starts, manages Connection/Session/Consumer


                      WHEN A MESSAGE ARRIVES
Producer --> broker --> queue/topic --> JMS MessageConsumer
                                            |
                                            v
                                 MessageListenerContainer
                                            |
                                            v
                              MessagingMessageListenerAdapter
                                            |
                                            v
                    Convert JMS Message / map headers-payload
                                            |
                                            v
                 Resolve parameters via MessageHandlerMethodFactory
                                            |
                                            v
                      OrderListener.onOrder(String orderId)
                                            |
                                            v
                              Business service / database
                                            |
                                            v
                      ACK / commit or rollback per configuration
```

The two halves of the diagram do not run at the same time. **Startup** registers the listener and builds the infrastructure; **runtime** activates only when a consumer receives a message. The `@JmsListener` annotation is not a method call when Java reads the annotation.

> **Key takeaway:** Spring creates and manages the listener container, then uses an adapter and argument resolver to turn a **JMS Message** into a **Java method call**. Your method is only the business logic at the end of the pipeline, yet errors before or after the call still affect ACK, retries, and transactions.

## 2. Separating Roles So APIs Are Not Confused

| Component | Responsible for | Is not |
| --- | --- | --- |
| Broker (e.g., ActiveMQ Artemis) | Storing/delivering messages per queue/topic, permissions, selectors, and broker policies | What directly invokes a Spring bean's Java method |
| `jakarta.jms.ConnectionFactory` | Providing the ability to open JMS connections to the provider | A running message consumer |
| `jakarta.jms.Connection`/`Session`/`MessageConsumer` | JMS resources for receiving messages; managed depending on the container | Business objects |
| `MessageListenerContainer` | Managing consumers, threading, lifecycle, receiving, transactions/ack, and recovery | A payload converter or business service |
| `JmsListenerContainerFactory` | **Creating and configuring** listener containers for endpoints | A single consumer receiving all messages |
| `@JmsListener` | Declaring a Java method as an endpoint with destination/id/selector/factory | An active `receive()` command |
| `MessagingMessageListenerAdapter` | Adapting JMS callbacks into invocations of the annotated method | Spring `JmsTemplate` |
| `MessageConverter` and header mapper | Converting content/metadata between JMS messages and Spring representations | An ACK mechanism |
| `MessageHandlerMethodFactory` | Building the invoker and resolving method parameters (payload, headers, raw message, session, validation...) | A broker or listener container |
| Bean method | Executing business logic and throwing exceptions on failure | An automatic guarantee of atomic DB + JMS commit |
| `JmsTemplate` | Primarily **synchronous** sending and receiving when called explicitly by the application; usable in producers | A required mechanism for `@JmsListener` to be called |

There are two senses of "listener" to distinguish:

- `jakarta.jms.MessageListener` is the low-level Jakarta Messaging interface with the `onMessage(Message)` callback.
- `@JmsListener` is Spring's annotation for registering a **regular method** as a handler; the method does not need to implement `jakarta.jms.MessageListener`.

## 3. Phase A — Spring Discovers and Registers @JmsListener

### 3.1. Registering listener infrastructure

In Java configuration, use:

```java
@Configuration
@EnableJms
public class JmsConfiguration {
}
```

This is a **configuration snippet in a project that already has the Spring JMS dependency**; imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
```

`@EnableJms` enables annotation-driven infrastructure. In Spring Framework 6.x, `JmsBootstrapConfiguration` registers `JmsListenerAnnotationBeanPostProcessor`; this component detects methods annotated with `@JmsListener` on Spring-managed beans. Spring Boot provides matching JMS auto-configuration, though writing `@EnableJms` explicitly makes the infrastructure boundary visible.

If you instantiate via `new OrderListener()` without registering it as a Spring bean, Spring will not discover its method to create an endpoint. Additionally, the package containing the listener must be component-scanned or the bean must be registered with `@Bean`.

### 3.2. Turning the annotation into an endpoint

With an annotation:

```java
@JmsListener(
        id = "ordersListener",
        destination = "orders.in",
        containerFactory = "ordersListenerFactory")
public void onOrder(String orderId) {
    // business logic
}
```

Spring stores endpoint metadata (target bean, method, destination name, ID, and options) in a model such as `MethodJmsListenerEndpoint`. `JmsListenerEndpointRegistrar`/`JmsListenerEndpointRegistry` coordinate creating and registering the container via the appropriate factory.

Important attributes:

| `@JmsListener` attribute | Purpose |
| --- | --- |
| `destination` | Queue/topic name for the container to register a consumer on, resolved via `DestinationResolver` |
| `containerFactory` | Factory bean name used to create the container; if omitted, Spring looks for default `jmsListenerContainerFactory` unless another default is configured |
| `id` | Endpoint/container ID, supporting lookup via `JmsListenerEndpointRegistry` |
| `selector` | JMS selector expression filtering on headers/properties supported by the broker/provider |
| `concurrency` | Consumer count limits at the endpoint, depending on implementation support |
| `subscription` | Subscription name, mainly used in topic/durable subscription scenarios |

Multiple endpoints can share **one factory**, yet each annotated method is typically served by its own **separate listener container** created from the factory. The factory is a **blueprint**, not a single container taking turns invoking all methods.

### 3.3. Factory and registry manage lifecycle

`DefaultJmsListenerContainerFactory` usually creates `DefaultMessageListenerContainer`; Spring also supports `SimpleJmsListenerContainerFactory` and other registration styles. `JmsListenerEndpointRegistry` holds the containers created through the annotation infrastructure so you can manage them by ID.

Lifecycle check example, **a snippet inside a bean with an injected `JmsListenerEndpointRegistry registry`**:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    System.out.println("Listener running = " + container.isRunning());
}
```

Required imports:

```java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
```

This is not a standalone program. `getListenerContainer(...)` returns null when there is no matching endpoint ID. A container managed through the registry does not necessarily exist as an independent bean injectable directly by that name; the factory and registry are the infrastructure-managing beans.

## 4. Phase B — Listener Container Receives a JMS Message

When the container starts, it uses `ConnectionFactory` and the destination name to create the required JMS resources: `Connection`, `Session`, and `MessageConsumer` as dictated by implementation/caching/transaction settings.

With `DefaultMessageListenerContainer`, the container runs worker threads executing a receive loop via JMS `MessageConsumer.receive(...)` and hands messages off to the appropriate callback. Therefore:

- From the **business method's perspective**, receiving is asynchronous: the method is invoked when a message arrives without calling `receive` itself.
- From the **internal mechanism's perspective**, the implementation may still use blocking receive on container threads. Do not equate "annotation-driven" with "no thread blocks" or "the broker directly invokes Java methods".

`SimpleMessageListenerContainer` takes a different approach: it uses `MessageConsumer.setMessageListener(...)` so the provider actively pushes callbacks and keeps a fixed number of sessions/consumers. The two implementations have different scaling/transaction capabilities. This lesson uses `DefaultMessageListenerContainer` in its example.

### 4.1. Conditions for a message to reach the right consumer

The container receives only when the configuration is valid:

- Connected to the **right broker** (URL, credentials, permissions).
- `destination` resolves to the right queue/topic with corresponding resources per provider policy.
- If a `selector` is set, the message carries properties/headers matching the expression.
- If using a topic, `pubSubDomain` and subscription/durability/shared semantics are configured properly.
- The container is running and the consumer is validly registered.

Selector example:

```java
@JmsListener(
        destination = "orders.in",
        selector = "eventType = 'ORDER_CREATED'")
public void onCreated(String payload) {
    // Only messages with matching eventType property satisfy the selector.
}
```

A selector is a receive-time filter, **not a command to delete non-matching messages**. On a queue, messages that do not match a selector may wait for another consumer; on a topic, subscription semantics differ. Do not use selectors as a substitute for message validation inside business handlers.

### 4.2. Queues do not broadcast copies to all listeners

If two endpoints both listen to queue `orders.in`, they are **competing consumers**; the broker normally delivers each message to one eligible consumer. Two methods on the same queue do not both run for every message. For fan-out, design topics/subscriptions or publish separate messages rather than simply adding annotations.

## 5. Phase C — Adapter Turns the JMS Callback into a Java Method Call

Spring does not force you to implement `jakarta.jms.MessageListener` in every class containing `@JmsListener`. For annotated methods, Spring uses the `MethodJmsListenerEndpoint` model and `MessagingMessageListenerAdapter` to turn the message-receiving callback into an appropriate invocation.

Conceptual flow:

```text
Receive jakarta.jms.TextMessage
    body = "ORDER-1001"
    property eventType = "ORDER_CREATED"
    JMSMessageID, JMSCorrelationID, ...
                |
                v
DefaultMessageListenerContainer
                |
                v
MessagingMessageListenerAdapter.onMessage(jmsMessage, session)
                |
                v
JMS-to-Spring Message conversion + JMS header mapping
                |
                v
DefaultMessageHandlerMethodFactory / InvocableHandlerMethod
                |
                +--> @Payload String orderId
                +--> @Header("eventType") String eventType
                +--> jakarta.jms.Message raw / jakarta.jms.Session (if declared by method)
                |
                v
OrderEventListener.consume(orderId, eventType)
```

Key points to understand:

1. A **JMS message** is `jakarta.jms.Message` (`TextMessage`, `BytesMessage`, `MapMessage`...).
2. Spring adds the **`org.springframework.messaging.Message<?>`** abstraction consisting of payload and headers.
3. The adapter uses configured converters/header mappers to build data ready for the handler.
4. `DefaultMessageHandlerMethodFactory` and argument resolvers determine method parameters by type/annotation and may run additional conversion/validation.
5. Once arguments are ready, Spring invokes the registered method on the bean; if the handler throws an exception, the error returns to the container/transaction mechanism.

This is a **logical diagram**, not a guarantee that every Spring version/converter produces the exact same step count or internal classes. When custom converters/handler method factories are configured, conversion details may differ.

### 5.1. Parameters a method can receive

```java
@JmsListener(destination = "orders.in")
public void consume(
        @Payload String orderId,
        @Header("eventType") String eventType,
        jakarta.jms.Message raw,
        jakarta.jms.Session session) throws jakarta.jms.JMSException {

    System.out.println(orderId);
    System.out.println(eventType);
    System.out.println(raw.getJMSMessageID());
}
```

This is an **illustrative method snippet** inside a Spring bean, using imports:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
```

Explanation:

- `@Payload String orderId`: message body converted to `String`.
- `@Header("eventType") String eventType`: JMS property set by the producer, mapped to the corresponding header.
- `jakarta.jms.Message raw`: the raw JMS message object when the method needs low-level header/provider APIs.
- `jakarta.jms.Session session`: the receiving operation's session, usable if sending a reply via JMS APIs; **must not be cached or closed arbitrarily**.

You do not need to declare all four parameters in every method. When only the payload is needed, `public void consume(String orderId)` suffices.

With `org.springframework.messaging.Message<String>`, a method can receive an object containing **both payload and headers** in a single parameter. Watch out for the `Message` name collision: `jakarta.jms.Message` and `org.springframework.messaging.Message` are **two different interfaces**; use fully qualified names when reading both together.

### 5.2. Converter: TextMessage to String is not magic

With Spring JMS's standard `SimpleMessageConverter`:

| JMS input | Common Java payload type |
| --- | --- |
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `Map` |
| `ObjectMessage` | Deserialized object, requiring trust/compatibility control |

Actual results depend on the converter configured by the application. With JSON inside a `TextMessage`, mapping into `record OrderCreated(String id)` or a DTO is **not automatically guaranteed** by `SimpleMessageConverter`; you must configure a suitable JSON converter and agree on content type/type ID/schema.

If the method expects `OrderCreated` while the converter only returns `String` and no compatible conversion exists, failure can occur **before entering the handler body**. Seeing no log at the start of the method does not mean the broker failed to deliver: inspect conversion/argument resolution errors in the listener container.

### 5.3. Header mapper, validation, and parameter resolution rules

Useful annotations:

| Symbol | Role |
| --- | --- |
| `@Payload` | Marks the parameter receiving the converted body |
| `@Header("eventType")` | Extracts one mapped header/property by name |
| `@Headers Map<String, Object>` | Receives the map of mapped headers |
| `@Valid @Payload SomeDto` | Runs bean validation if a matching validator and conversion exist |
| `jakarta.jms.Message` | Accesses the raw JMS message |
| `jakarta.jms.Session` | Accesses the raw receiving session |
| `org.springframework.messaging.Message<T>` | Receives both payload and headers via Spring's abstraction |

Using bean validation requires the right dependency and validator configuration; `@Valid` alone does not create business validation rules or a JSON converter. Failing to resolve a required `@Header`, a header type mismatch, or an unconvertible payload can prevent the method **from ever being called**.

## 6. Complete Example with Spring Boot 3.x and Java 17+

The example sends a `TextMessage` to queue `orders.in`, the container receives it, the adapter converts the body and property, and then calls the processing service. Uses **Spring Boot 3.x / Spring Framework 6.x / Java 17+**, the `jakarta.jms` namespace, and an ActiveMQ Artemis broker.

Prerequisites: a Spring Boot Gradle project with plugins and dependency management; a running broker; queue `orders.in` provisioned or auto-creation permitted per policy; valid credentials and send/receive permissions. The files below belong to a **Spring Boot project**, not standalone classes compilable with `javac` without dependencies.

### 6.1. Dependencies

In the Groovy DSL `build.gradle` of a Spring Boot 3.x project, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot plugin and Java 17+ toolchain are required in the project. `spring-boot-starter-artemis` provides what Spring needs to use Jakarta JMS with Artemis; do not accidentally import `javax.jms`.

### 6.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    orders-queue: "${JMS_ORDERS_QUEUE:orders.in}"
```

Substitute the environment variables with your lab environment values. Never hardcode real passwords in the repository. The name `orders.in` must match the actual queue; having the string in YAML **does not mean the queue has been created on the broker**.

### 6.3. Boot application enabling listener annotations

File `src/main/java/demo/pipeline/PipelineApplication.java`:

```java
package demo.pipeline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class PipelineApplication {
    public static void main(String[] args) {
        SpringApplication.run(PipelineApplication.class, args);
    }
}
```

`@EnableJms` explicitly shows the listener infrastructure registration step. `PipelineApplication` sits in the parent package `demo.pipeline`, so default component scanning finds the demo beans in the same package.

### 6.4. Configuring the container factory

File `src/main/java/demo/pipeline/OrdersJmsConfiguration.java`:

```java
package demo.pipeline;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class OrdersJmsConfiguration {

    @Bean("ordersListenerFactory")
    public DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

Breakdown:

- `ConnectionFactory` connects to the broker and is supplied by Spring Boot once Artemis is configured.
- The factory creates `DefaultMessageListenerContainer` instances for endpoints using `containerFactory = "ordersListenerFactory"`.
- `sessionTransacted(true)` requests a **local JMS transaction**: if the handler finishes, JMS commits; if it fails and the exception propagates across the boundary, the container can roll back so the provider redelivers.
- `concurrency("1")` selects one concurrent consumer for **this endpoint's container**; it does **not** cap total consumers when running multiple application instances.
- This is a dedicated factory and requires no changes to the default producer `JmsTemplate`.

**Note:** a JMS transaction does not automatically cover another database's transaction. If the service updates the DB and then the JMS commit fails, redelivery can occur; real applications must be idempotent.

### 6.5. Business service invoked after conversion

File `src/main/java/demo/pipeline/OrderProcessingService.java`:

```java
package demo.pipeline;

import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {

    public void process(String orderId, String eventType) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        if (!"ORDER_CREATED".equals(eventType)) {
            throw new IllegalArgumentException(
                    "Unsupported eventType: " + eventType);
        }

        System.out.printf(
                "HANDLER_CALLED orderId=%s eventType=%s%n",
                orderId, eventType);
    }
}
```

The demo service only validates data and logs. It does not write to a database and does not represent exactly-once logic. Separating the service from the listener makes business logic testable independently of JMS infrastructure.

### 6.6. Listener receiving payload and header

File `src/main/java/demo/pipeline/OrderEventListener.java`:

```java
package demo.pipeline;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {
    private final OrderProcessingService service;

    public OrderEventListener(OrderProcessingService service) {
        this.service = service;
    }

    @JmsListener(
            id = "ordersListener",
            destination = "${app.jms.orders-queue}",
            containerFactory = "ordersListenerFactory")
    public void consume(
            @Payload String orderId,
            @Header("eventType") String eventType) {
        service.process(orderId, eventType);
    }
}
```

Upon receiving a `TextMessage` with body `ORDER-1001` and property `eventType = ORDER_CREATED`, the adapter/argument resolver turns the data into two `String`s and calls `consume("ORDER-1001", "ORDER_CREATED")`. The method then calls `OrderProcessingService.process(...)`.

`@JmsListener` does not spawn a Java thread per method; the listener container coordinates receiving threads. With a singleton `@Component`, multiple container threads (if concurrency is raised) **can invoke the method on the same bean simultaneously**. Never store mutable state in listener fields without thread-safety mechanisms.

### 6.7. Producer sending a message to test the path

File `src/main/java/demo/pipeline/DemoPublisher.java`:

```java
package demo.pipeline;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DemoPublisher {
    private final JmsTemplate jmsTemplate;
    private final String queue;

    public DemoPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders-queue}") String queue) {
        this.jmsTemplate = jmsTemplate;
        this.queue = queue;
    }

    public void publish(String orderId) {
        jmsTemplate.send(queue, session -> {
            TextMessage msg = session.createTextMessage(orderId);
            msg.setStringProperty("eventType", "ORDER_CREATED");
            return msg;
        });
    }
}
```

The producer's `MessageCreator` receives a `Session` **to build an outgoing message**, whereas the consumer's `MessagingMessageListenerAdapter` **processes an incoming message**. Do not conflate both callbacks.

### 6.8. Runner sending one message when demo profile is active

File `src/main/java/demo/pipeline/DemoRunner.java`:

```java
package demo.pipeline;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("demo-publish")
public class DemoRunner implements ApplicationRunner {
    private final DemoPublisher publisher;

    public DemoRunner(DemoPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publish("ORDER-1001");
        System.out.println("PUBLISH_REQUESTED ORDER-1001");
    }
}
```

Run once the broker is up and the queue has send/receive permissions:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo-publish'
```

If JMS sending and receiving succeed, **two lines printed by the application itself** may appear:

```text
PUBLISH_REQUESTED ORDER-1001
HANDLER_CALLED orderId=ORDER-1001 eventType=ORDER_CREATED
```

**The order of those two lines is not guaranteed.** The consumer can run before the producer prints `PUBLISH_REQUESTED`, and the console also contains other Spring Boot/broker logs. When the broker is unreachable, lacks permissions, lacks the queue, or conversion fails, do not expect both lines to appear.

Because the runner sends a message on every startup with the `demo-publish` profile, never enable this profile in production.

## 7. When Is the Handler Actually Called — and When Not?

There are many failure points **before** the first line of the handler:

| Step | Example failure | Symptom |
| --- | --- | --- |
| Spring context init | Listener is not a Spring bean or `@EnableJms` infrastructure missing | No endpoint registered |
| Create listener container | Wrong `containerFactory` bean name | Startup/configuration failure |
| Connect | Wrong broker URL/credentials, broker down | Container recovery/reconnect; handler not called |
| Resolve destination | Wrong queue name, queue/topic mismatch, missing ACL | Consumer receives no matching messages |
| Selector | `selector` does not match properties | Message is not dispatched to that endpoint |
| Convert | JMS message type/schema incompatible with converter | Method never called, conversion failure |
| Map headers | `@Header("eventType")` missing or wrong type | Argument resolution failure before body |
| Invoke method | Handler throws `IllegalArgumentException`/DB error | Error occurs **inside** handler |
| Commit/ACK | Transaction commit/connection fails | Handler may have run yet JMS outcome differs from expectations |

Therefore **"seeing no log in `onMessage`" does not mean the broker has no messages**. Check container logs, converter exceptions, destinations, selectors, and broker metrics before blaming the business service.

### 7.1. Why do converter errors also affect retries?

`@Payload` and `@Header` are resolved along the path before invoking the business method. If conversion fails, the adapter can throw an exception to the container even though the method was never called. With a transacted session and container rollback on exception, the message may be **redelivered** and fail repeatedly.

Do not wait until entering the service to catch "invalid schema" and conclude you handled all poison message cases. You need a DLQ policy, redelivery limits, and observability for conversion/validation errors.

### 7.2. Why can swallowing exceptions forfeit retries?

Anti-pattern:

```java
@JmsListener(destination = "orders.in")
public void broken(String body) {
    try {
        businessService.process(body);
    }
    catch (Exception ignored) {
        // Anti-pattern: does not report failure to the listener container.
    }
}
```

This is a **non-standalone illustrative snippet**, assuming `businessService` has the corresponding method. With a listener container using a local JMS transaction, when the handler returns normally, the container may **commit the JMS session**. If business logic fails yet the exception is swallowed, the message can be falsely marked complete.

Classify errors properly:

- Transient (DB temporarily unreachable): let the transaction roll back and retry/backoff per policy.
- Permanent (invalid payload/schema): avoid infinite loops; route to DLQ/quarantine in a controlled way.
- Duplicate: detect via eventId/business key to safely skip duplicate side effects.

Not every container creates a DLQ automatically. Redelivery, attempt limits, and DLQ destinations usually depend on **JMS provider/broker and application configuration**.

## 8. After the Handler: ACK, Commit, and Rollback Are Not the Annotation's Job

Once `consume(...)` completes, the container proceeds with transaction/acknowledgement handling per configuration. With the demo factory's `setSessionTransacted(true)`:

```text
Broker delivers message to consumer
    |
    v
Local JMS transaction for the receipt
    |
    v
Adapter -> convert -> resolve arguments -> handler
    |
    +-- success -------------> commit JMS session
    |                               |
    |                               v
    |                          complete ACK per provider
    |
    +-- exception -----------> roll back JMS session
                                    |
                                    v
                              possible redelivery
                              per broker policy
```

This behavior is **at the JMS transaction level**, not a guarantee that the business database committed atomically with JMS.

### 8.1. Acknowledgement modes are not identical

- With `sessionTransacted = true`, the JMS session's commit/rollback decides the outcome for the message and JMS operations within the transaction.
- With `AUTO_ACKNOWLEDGE` and a non-transacted `DefaultMessageListenerContainer`, acknowledgement may occur **before** the listener executes, so handler exceptions do not automatically trigger redelivery.
- With `CLIENT_ACKNOWLEDGE`, acknowledgement timing and its interaction with the entire session must be carefully designed; never assume each ACK call confirms only one message.
- `DUPS_OK_ACKNOWLEDGE` allows lazy acknowledgement; it does not solve exactly-once.
- When using an external transaction manager or provider-specific configuration, re-verify the listener container's actual boundaries.

**Do not rely on assumptions about "how Spring Boot defaults transactions" if the app defines a custom factory.** The example explicitly configures `setSessionTransacted(true)` so receiving behavior is clear.

### 8.2. Database transactions remain a separate boundary

What can happen:

1. Service processes and commits the database.
2. JMS commit fails due to a broker error.
3. Provider redelivers the message.
4. Service processes twice if idempotency is missing.

Therefore events need an `eventId` or stable business key, plus deduplication/inbox/version checks inside the DB transaction. When a stronger DB + JMS contract is required, consider outbox, proper XA/JTA, or reconciliation mechanisms; **`@JmsListener` and local JMS transactions do not automatically provide business-level exactly-once**.

### 8.3. Acknowledgement does not mean a result was returned to the producer

Consumer JMS ACK is part of the receiving protocol. It **does not automatically send "OrderProcessed" back to the producer**. If a business response is needed, design a reply destination, correlation ID, timeout, and retry/dedup model.

## 9. What Can a Java Method Receive Besides String?

### 9.1. Receiving raw TextMessage to access provider headers

```java
@JmsListener(destination = "orders.in")
public void receiveRaw(jakarta.jms.TextMessage raw)
        throws jakarta.jms.JMSException {
    String body = raw.getText();
    String id = raw.getJMSMessageID();
    boolean redelivered = raw.getJMSRedelivered();
    System.out.printf(
            "messageId=%s redelivered=%s body=%s%n",
            id, redelivered, body);
}
```

This snippet lives in a bean importing `org.springframework.jms.annotation.JmsListener`. The method only supports `TextMessage`; if another type arrives, binding fails. `JMSRedelivered` helps observe retries yet **does not replace `eventId` and deduplication**. Provider metadata can vary by configuration.

### 9.2. Spring Messaging Message

```java
@JmsListener(destination = "orders.in")
public void receiveSpringMessage(
        org.springframework.messaging.Message<String> message) {
    String body = message.getPayload();
    Object eventType = message.getHeaders().get("eventType");
    System.out.println(body + " / " + eventType);
}
```

The Spring Messaging wrapper carries payload and headers. It is **not** raw `jakarta.jms.Message`. If you want to call `getJMSCorrelationID()` directly, receive the raw JMS message as in 9.1 or read the standard mapped header.

### 9.3. Receiving DTOs from JSON with a matching converter

Concept:

```java
record OrderCreated(String orderId, String customerId) {}

@JmsListener(destination = "orders.json")
public void onJson(@Payload OrderCreated event) {
    orderService.create(event.orderId(), event.customerId());
}
```

This is a **conceptual snippet**, not a standalone compilable Java file; `orderService` is an injected dependency. You must configure an appropriate `MessageConverter` (e.g., converting JSON text to DTOs with Jackson) and matching type resolution, schema, and header rules. Do not simply put a JSON body in a `TextMessage` and expect `SimpleMessageConverter` to produce `OrderCreated` by default.

### 9.4. A method returning a value does not automatically mean the business reply completed

For handlers returning a value instead of `void`, Spring supports sending a reply to `JMSReplyTo` or a destination specified via `@SendTo`, depending on configuration. Conceptual example:

```java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String handleRequest(String orderId) {
    return "RECEIVED:" + orderId;
}
```

You must import `org.springframework.messaging.handler.annotation.SendTo` and set up the destinations properly. This behavior does not arise from a `void` method, nor is it proof the database committed. If reliable business responses are needed, explicitly design transactions and request/reply correlation.

## 10. Container Concurrency, Threading, and Ordering

`@JmsListener` does not create a separate handler object per message. A `@Component` bean is normally a singleton; multiple consumer threads can concurrently invoke **the same method on the same instance**.

Factory example:

```java
factory.setConcurrency("3-10");
```

This means `DefaultMessageListenerContainer` can maintain at least 3 concurrent consumers and scale up to 10 per conditions/policy. Valid values and dynamic scaling depend on the container implementation.

Consequences to handle proactively:

- Never use mutable fields such as `lastOrderId` in a singleton listener without synchronization.
- Multiple consumers can process different messages and **commit results out of producer send order**.
- Multiple application replicas create additional consumers, even if each endpoint on each replica has `concurrency = 1`.
- Connections/sessions belong to the container and are used within appropriate thread/transaction scopes; never cache `Session` in a field or pass it to another executor.
- If the handler offloads work to `CompletableFuture.runAsync(...)` and returns immediately, the container may ACK/commit **before the background business work completes**.

When per-entity ordering is needed, consider `aggregateId`/`sequence`, version checks in the DB, broker-supported message grouping, and appropriate concurrency limits. **JMS priority and a single listener thread do not replace a business ordering contract.**

## 11. Observing the Path on Failures: Troubleshooting Checklist

| Symptom | What to check first |
| --- | --- |
| Application boots yet no handler appears | `@EnableJms`, bean scanned, factory name, container running, queue, credentials |
| Messages exist on broker yet listener receives nothing | Wrong broker URL/namespace, queue/topic mismatch, selector, consumer permissions, subscription |
| No log at method entry yet broker dequeued message | Converter error, missing required header, argument resolver/validation error before invocation |
| Method invoked yet payload is wrong | JMS message type, `MessageConverter`, charset/schema, producer encoding |
| Header in method is null | Property not set by producer, wrong header name, custom mapper/converter |
| Handler throws exception and message keeps returning | Local JMS rollback, redelivery limit, poison message, DLQ/backoff |
| Handler throws exception yet message is lost | ACK happened before invocation, exception swallowed, broker/provider policy |
| Same event processed multiple times | JMS redelivery, duplicate publish, JMS commit failed after DB commit, missing idempotency |
| Raising concurrency overloads DB | Too many consumers/replicas, DB pool, handler latency, backpressure |
| One queue yet two listeners do not both receive each message | Competing consumers semantics, not broadcast |
| In-flight work lost on shutdown | Graceful stop/in-flight drain, JMS transaction outcome, redelivery |

Operational metrics to collect (application-defined names): `listener_container_running`, `consumer_count`, `queue_depth`, `oldest_message_age`, `received_total`, `handler_success_total`, `handler_failure_total`, `redelivery_total`, `dlq_depth`, `processing_latency`. Never rely solely on `System.out` logs as in examples.

## 12. Testing the Path from Message to Method

### 12.1. Unit test — verifying the method delegates to the right service

File `src/test/java/demo/pipeline/OrderEventListenerTest.java`:

```java
package demo.pipeline;

import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class OrderEventListenerTest {

    @Test
    void delegatesConvertedPayloadAndHeaderToService() {
        OrderProcessingService service =
                mock(OrderProcessingService.class);

        OrderEventListener listener = new OrderEventListener(service);
        listener.consume("ORDER-1001", "ORDER_CREATED");

        verify(service).process("ORDER-1001", "ORDER_CREATED");
    }
}
```

Run:

```bash
./gradlew test --tests demo.pipeline.OrderEventListenerTest
```

The test passes if the mock receives the expected invocation; Gradle may print `BUILD SUCCESSFUL`, though full stdout depends on Gradle/JUnit configuration. **Important limitation:** this test calls the Java method directly. It **does not** prove `@JmsListener` was registered, the broker delivered a `TextMessage`, the adapter mapped `@Header`, or the JMS transaction committed.

### 12.2. Integration test — requires a broker

To verify **the entire chain**, you need an environment with a real broker or a compatible embedded/Testcontainers setup:

1. Start the context with `@EnableJms` and the configured factory; verify `JmsListenerEndpointRegistry.getListenerContainer("ordersListener")` returns a running container.
2. Send a `TextMessage` with body `ORDER-1001` and string property `eventType = ORDER_CREATED`.
3. Use a latch/probe/mock service with a timeout to verify the listener method is actually called. Never use a fixed `Thread.sleep` as an oracle.
4. Send a message missing `eventType`; observe the **pre-handler** failure and rollback/redelivery or DLQ per policy.
5. Have the service throw an exception; verify JMS transaction policy and broker redelivery per configuration.
6. Run multiple consumers/replicas; verify handler thread safety and business idempotency while observing queue depth and retries.
7. Stop/start the broker to verify recovery, graceful shutdown, and no unexpected event loss.

**Separate test assertions:** "message sent", "listener container received", "method invoked", "business state committed", "JMS ACK/commit", and "producer received business reply". These are distinct milestones.

## 13. Summary Responsibility Matrix

| Stage | Primary component | What to verify |
| --- | --- | --- |
| Bean created | Spring IoC | `@Component`/`@Bean` and component scan |
| Endpoint registered | `@EnableJms` + annotation processor + registrar | Destination, factory, ID, selector |
| Container running | `JmsListenerContainerFactory`, registry, and container | `ConnectionFactory`, lifecycle, consumer count |
| JMS message received | Broker + JMS Session/Consumer | Queue/topic, permissions, selector, retries |
| Message adapted | `MessagingMessageListenerAdapter` | Converter, payload, header mapping |
| Method selected/invoked | `MessageHandlerMethodFactory`/invoker | `@Payload`, `@Header`, types, validation |
| Business processed | Application service | Correct logic, idempotency, DB transactions |
| Message ACKed/rolled back | Listener container/JMS transaction | ACK mode, rollback, redelivery, DLQ |

**Remember:** "From received message to invoking the handler method" is a pipeline with two lifecycles: **listener registration at startup**, and **receive → convert → invoke → ACK/commit/rollback at runtime**. When observing an error, identify which step it occurred in; in particular, converter errors can occur before the method runs, and a method finishing does not guarantee transactions or business work completed in every system.

### References

- Spring Framework 6.2 — Annotation-driven Listener Endpoints, `@JmsListener`, method signatures, and `@SendTo`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Receiving a Message, message listener container, `MessageListenerAdapter`, and transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework API — `MessagingMessageListenerAdapter`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html
- Spring Framework API — `JmsListenerAnnotationBeanPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerAnnotationBeanPostProcessor.html
- Spring Framework API — `JmsListenerEndpointRegistry`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS auto-configuration and listener factory: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
