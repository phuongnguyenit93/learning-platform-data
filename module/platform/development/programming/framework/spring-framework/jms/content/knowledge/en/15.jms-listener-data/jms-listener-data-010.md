# Keeping Listener Methods Short and Delegating Business Logic in Spring JMS

## 1. Objectives and Practical Problem

In Spring JMS, a `@JmsListener`-annotated method is the **entry point for messages from the broker**, not the place to put an entire business workflow. A listener that simultaneously decodes JSON, checks contracts, queries databases, calculates charges, calls external APIs, updates state, sends emails, and decides retries manually quickly turns into a block of code that is hard to test, hard to reuse, and prone to transaction bugs.

The design principle should be a **thin listener / message adapter**: the listener receives data from JMS, gathers minimal metadata, converts it into application input, **delegates to a business service**, and **lets the transaction/acknowledgment mechanism handle the outcome**. Business logic belongs in services, decoupled from `jakarta.jms.Message` details, Queue names, or JMS Sessions.

After this lesson, you will be able to:

1. Separate responsibilities among **JMS listener adapter**, **message decoder/validator**, **application service**, and **domain layer**.
2. Write concise yet clear `@JmsListener` methods handling `@Payload`, `@Header`, schema versions, and correlation/event IDs properly.
3. Understand why you **must not swallow exceptions**, manually ack/roll back arbitrarily, or spawn threads / `@Async` fire-and-forget inside a listener.
4. Configure transacted JMS sessions, retries/redelivery/DLQs, and idempotency along proper boundaries.
5. Control concurrency, DB transactions, side effects, observability, and data security.
6. Run a **Java 17+, Spring Boot 3.5.7, embedded ActiveMQ Artemis, Jackson** example with a listener containing only two core statements.
7. Write separate unit/integration tests for the adapter, decoder, and business logic.

This lesson belongs to **Listener Data**, so the focus is how a listener **receives payloads and headers**, enforces data boundaries, and hands execution off to a service.

## 2. A Listener Is an Adapter, Not the Entire Application

Spring lets you declare a simple message-driven POJO:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.commands")
    public void onMessage(String payload) {
        // Call order processing logic.
    }
}
~~~

Spring creates a message listener container behind the annotation, receives from the configured Queue/Topic, converts/resolves parameters, and invokes the method on the bean. **The container** owns receiving, Session, MessageConsumer, threading, startup/shutdown, and JMS transactions; the listener method is an **application callback**.

Layered model:

~~~mermaid
flowchart LR
    A[("JMS Queue")] --> B["Spring listener container"]
    B --> C["@JmsListener: adapter"]
    C --> D["Decoder / contract validator"]
    D --> E["Application service"]
    E --> F["Domain + repository + ports"]
    F --> G["Database / external systems"]
~~~

Responsibilities to separate:

| Layer | Should be responsible for | Should not be forced to handle |
| --- | --- | --- |
| **JMS listener adapter** | Receiving payload and metadata, invoking decoder/delegate, letting exceptions propagate per policy. | Complex business calculations, SQL, piecemeal manual broker transaction control. |
| **Decoder / message contract validator** | Parsing JSON/Bytes/Map, checking schema version, required fields, and header/body coherence. | Directly writing DB records, sending emails, or mutating order state. |
| **Application service** | Orchestrating use cases, business transactions, idempotency, calling domain/repositories/ports. | Knowing JMS Queue names or depending on `jakarta.jms.Session`. |
| **Domain model/service** | Business invariants, calculation rules, and state transitions. | Depending on `@JmsListener`, Spring JMS, or selectors. |
| **Listener container / broker** | Receive/dispatch, session transactions, redelivery/recovery, DLQ per configuration. | Defining business success or deciding data validity. |

**"Short listener" is not a line-golf contest.** A 5-line method calling a 2,000-line "god service" does not magically become good design. What matters is **clear responsibility boundaries and independent testability**, not forcing every listener into a single expression.

### 2.1. Why Does This Matter for Listener Data?

JMS only delivers a `Message` with headers, properties, and a body. The application must understand:

- Is the body a JSON `TextMessage`, `BytesMessage`, or another format?
- Is `schemaVersion` still supported by the consumer?
- Do `eventId`/`JMSCorrelationID` match the contract?
- Does the payload hold enough data for business processing?
- Which information comes from the broker vs. set by the producer?
- If decoding/validation fails, should that exact message be retried?

If these checks are tangled inside DB update logic, a body error is easily mistaken for a transaction error or vice versa. A standalone decoder/validator creates a **clear boundary** between transport data and business data.

## 3. Anti-Pattern: Listener Taking On Every Responsibility

The counter-example below is **illustrative code only**, not a complete class; dependencies are undeclared:

~~~java
@JmsListener(destination = "orders.created")
public void onOrder(String json) {
    try {
        OrderDto dto = objectMapper.readValue(json, OrderDto.class);
        if (dto.orderId() == null) {
            return;
        }

        OrderEntity order = repository.findById(dto.orderId()).orElseThrow();
        order.setStatus("CONFIRMED");
        repository.save(order);

        paymentClient.capture(dto.orderId());
        mailClient.sendConfirmation(dto.orderId());
        jmsTemplate.convertAndSend("orders.audit", json);

    } catch (Exception ex) {
        log.error("Cannot process message", ex);
        // Logging and returning -> may cause container to treat as success.
    }
}
~~~

The issue is not just method length. It mixes **transport parsing**, **validation**, **DB transactions**, **external APIs**, **JMS publishing**, **error policy**, and **logging** into one callback.

Concrete risks:

1. Returning when `orderId` is missing can cause an invalid message to be **acked as successfully processed**, losing the chance to classify/quarantine it.
2. `catch(Exception)` followed by `return` hides the failure from the container; with a transacted session, the listener may commit JMS even though business processing failed.
3. The DB commit may succeed while payment/email/JMS audit fails; there is no automatic atomic transaction across all systems.
4. When a message is redelivered, payment/email risk **executing twice** if idempotency is absent.
5. Changing the JSON format forces modifying both the JMS method and business logic.
6. Unit tests must mock the database, HTTP client, JMS template, object mapper, and transactions — making failures hard to isolate.
7. Another entry point (REST API, batch, Kafka) cannot easily reuse the use case if it is tightly coupled to `@JmsListener`.

**The fix:** move parsing/validation into a decoder with its own contract; move use-case orchestration into an application service; keep the JMS callback as an adapter. Service failures must flow through proper transaction/error policies rather than being swallowed.

## 4. Pattern: Short Listener with Clear Boundaries

~~~java
@Component
public class OrderCreatedJmsListener {

    private final OrderMessageDecoder decoder;
    private final OrderApplicationService applicationService;

    public OrderCreatedJmsListener(
            OrderMessageDecoder decoder,
            OrderApplicationService applicationService) {
        this.decoder = decoder;
        this.applicationService = applicationService;
    }

    @JmsListener(destination = "orders.created")
    public void onMessage(
            @Payload String json,
            @Header("eventId") String eventId,
            @Header("schemaVersion") int schemaVersion) {

        OrderCreatedEvent event =
                decoder.decode(json, eventId, schemaVersion);

        applicationService.process(event);
    }
}
~~~

**This is a structural fragment**, without a package or definitions for `OrderMessageDecoder`, `OrderApplicationService`, and `OrderCreatedEvent`; the full version appears in the demo section.

Two meaningful statements in the listener:

1. `decoder.decode(...)` turns payload/headers into a **contract-valid event object**.
2. `applicationService.process(event)` executes the use case.

The listener **does not manually** call `message.acknowledge()`, commit JMS, open HTTP connections, or catch every exception. Those belong to the container, transaction configuration, and service/ports respectively.

You could organize it as **one** call `service.handleIncoming(json, metadata)` if the application service has an explicit inbound adapter, but avoid forcing the business service to know JMS header names whenever possible.

### 4.1. Use Constructor Injection

Prefer constructor injection with `final` fields. It makes required dependencies explicit, simplifies unit tests, and avoids partially initialized bean states. Never call `new OrderApplicationService()` inside the listener method: Spring loses control of transaction proxies/DI and you recreate the object per message.

### 4.2. Do Not Confuse Spring Bean Lifecycle with Message Lifecycle

Listener beans are normally singletons. One bean may be invoked thousands of times by the listener container. It is **not** newly instantiated by Spring for each JMS message. Adding `@PostConstruct` to the listener bean will not make that callback run before every message; `@PreDestroy` does not mean "ack the last message."

A container can start/stop/recover while the listener/application service beans remain alive. Therefore, never store **per-message** processing state in a mutable field on a singleton listener.

## 5. Receiving Payload and Headers with the Right API

Spring `@JmsListener` has flexible method signatures: accepting raw `jakarta.jms.Message`, `jakarta.jms.Session`, `org.springframework.messaging.Message<T>`, `@Payload`, `@Header`, `@Headers`, or an unannotated payload parameter. That is the **listener method's** API, not an automatic guarantee that payloads are business-valid.

### 5.1. String Body + Custom Headers

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(
        @Payload String json,
        @Header("eventId") String eventId,
        @Header("schemaVersion") int schemaVersion) {

    applicationService.process(
            decoder.decode(json, eventId, schemaVersion));
}
~~~

`@Header("eventId")` reads a **custom JMS property** mapped by Spring into message headers. `schemaVersion` must be set by the publisher with the right type (e.g., `setIntProperty`). If a required property is missing or conversion fails, an exception may occur during **argument resolution** before the method is invoked. Monitoring must cover **listener adapter/container errors**, not only logs inside the business service.

### 5.2. Raw Jakarta JMS Message When Truly Needed

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {

    String eventId = message.getStringProperty("eventId");
    int version = message.getIntProperty("schemaVersion");

    if (!(message instanceof jakarta.jms.TextMessage text)) {
        throw new IllegalArgumentException("Expected TextMessage");
    }

    applicationService.process(
            decoder.decode(text.getText(), eventId, version));
}
~~~

This fragment fits when you need explicit control over `TextMessage`/`BytesMessage`, or need to read `JMSCorrelationID` or `JMSXDeliveryCount`. However, if every listener manually parses dozens of raw JMS headers, extract a `JmsEnvelopeMapper` or dedicated adapter component instead of duplicating it across methods.

Do not rely on client-supplied headers (`tenantId`, `role`) as the sole proof of access rights. Broker ACLs and business authorization are separate layers. Never use raw `ObjectMessage` deserialization on untrusted data without configured trusted types.

### 5.3. Typed Payload

When an appropriate `MessageConverter` is configured, Spring can invoke:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(@Payload OrderCreatedEvent event) {
    applicationService.process(event);
}
~~~

However, **an important caveat**: default `SimpleMessageConverter` **does not automatically turn every JSON String into a domain record**. If using a typed DTO in the method, configure a converter/JSON type mapping and test schema evolution. Otherwise, receiving `String` and calling an explicit decoder is more transparent.

`@Valid @Payload` can trigger Bean Validation when Spring's method-argument infrastructure has a configured validator; do not assume adding the annotation alone enforces every payload constraint in every Spring setup.

### 5.4. Which Headers Should Be Passed to the Business Service?

| Metadata | Needed by adapter? | What to do? |
| --- | --- | --- |
| `eventId` (custom property) | Usually yes | Use for idempotency/auditing; cross-check against body. |
| `schemaVersion` | Yes if format evolves | Select decoder/contract; reject unsupported versions. |
| `JMSCorrelationID` | When tracing/request-reply needed | Can map to an application `CorrelationContext`; do not make it the default domain ID. |
| `JMSType` | When contract uses JMS type | Check event kind if needed; avoid conflicting names with other properties. |
| `JMSMessageID` | For diagnostics | Per-send ID; does not replace business `eventId`. |
| `JMSXDeliveryCount` | When observing redeliveries | Can include in logs/metrics; never edit or rely on it alone for business retry decisions. |
| `tenantId` | In multi-tenant setups | Validate against identity/ACLs; never blindly trust producer-supplied values. |
| All headers/properties | Should not be passed blindly | Keep only fields the service actually needs. |

**Do not force the business service to accept raw `jakarta.jms.Message` or `JmsHeaders` when it only needs `OrderCreatedEvent` and `eventId`.** If the service must know JMS types, it becomes transport-coupled and hard to reuse across other APIs.

## 6. Distinguishing Boundary Validation from Business Validation

Separate two layers:

**Contract/input validation** (decoder or adapter): is JSON valid? Is `schemaVersion` supported? Are required fields present? Does header `eventId` match body? Is `amountMinor` a valid integer? These are prerequisites for data to even be understood.

**Business validation** (application/domain): does the order exist? Is it already paid? Is the state transition permitted? Is the amount valid per domain invariants? Was the event already processed? These rules govern side effects.

| Example error | Where detected? | Suggested policy |
| --- | --- | --- |
| Truncated JSON | Decoder | Permanent-format error → controlled quarantine/DLQ. |
| Unsupported `schemaVersion=99` | Decoder | Do not retry identical payload forever; version upgrade/quarantine. |
| Header `eventId=A` vs. body `eventId=B` | Decoder | Reject; audit producer contract. |
| Empty `orderId` | Decoder/contract | Reject before side effects. |
| Order already completed | Domain/application | Handle idempotently or business-reject per contract. |
| Database temporarily unreachable | Repository/application | Can retry with rollback/backoff. |
| HTTP payment timeout | Outbound port | Can retry, but needs idempotency key and handling uncertain state. |

**Never let a schema-invalid message run halfway through a transaction before failing.** Validate inputs early and consistently. However, a "short" listener does not mean doing all validation inside the annotated method itself; the decoder/service are the right places.

## 7. Runnable Example: Spring Boot + Artemis + Two-Statement Listener

The demo uses **Java 17+**, **Spring Boot 3.5.7**, **Maven**, **embedded Apache ActiveMQ Artemis**, and Jackson. The application:

- Sends a JSON `TextMessage` to Queue `demo.order-events`.
- Attaches two JMS properties: `eventId` (String) and `schemaVersion` (int).
- Listener only calls the decoder and then the application service.
- Decoder parses/validates and cross-checks headers against the body.
- Business service prints one line and signals completion via `CountDownLatch`.
- `ApplicationRunner` verifies the handler ran, then closes the context.

**Note:** this is a single-message demo without a database and does not simulate exactly-once. Production idempotency and DB transactions are explained separately in later sections.

### 7.1. Structure

~~~text
jms-thin-listener-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsthin/
    │   ├── ThinListenerApplication.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderEventDecoder.java
    │   ├── OrderApplicationService.java
    │   └── OrderJmsListener.java
    └── resources/
        └── application.properties
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-thin-listener-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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

`spring-boot-starter-artemis` provides Spring JMS integration/client, `artemis-jakarta-server` provides the embedded broker, and `spring-boot-starter-json` provides Jackson `ObjectMapper`. The Boot parent manages compatible versions.

### 7.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.order-events
spring.artemis.embedded.persistent=false

spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=1

spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

- `spring.artemis.embedded.queues` provisions the test Queue when the embedded broker starts.
- `spring.jms.listener.session.transacted=true` instructs the container to use a **local JMS transacted session**; exceptions from the handler normally roll back the session, though broker redelivery/DLQ policies still must be configured for real deployments.
- Concurrency is set to one consumer for clear demo observation.
- `persistent=false` is for demo convenience only; it does **not** guarantee messages survive restarts.
- `web-application-type=none` avoids starting an unnecessary web server.

These properties are for **Spring Boot 3.5**; if you replace them with a custom `JmsListenerContainerFactory`, ensure the factory in use carries the same transaction/concurrency settings.

### 7.4. OrderCreatedEvent.java

~~~java
package com.example.jmsthin;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long amountMinor) {
}
~~~

The record is a simple **domain-facing input model**. `amountMinor` uses the smallest currency unit (e.g., cents), avoiding floating-point for money. The demo only checks `amountMinor > 0`; production needs currency, max values, rounding, and other invariants.

### 7.5. OrderEventDecoder.java

~~~java
package com.example.jmsthin;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.stereotype.Component;

@Component
public class OrderEventDecoder {

    private final ObjectMapper objectMapper;

    public OrderEventDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderCreatedEvent decode(
            String json,
            String headerEventId,
            int schemaVersion) {

        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schemaVersion: " + schemaVersion);
        }

        try {
            OrderCreatedEvent event =
                    objectMapper.readValue(json, OrderCreatedEvent.class);

            if (event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.amountMinor() <= 0
                    || !event.eventId().equals(headerEventId)) {
                throw new IllegalArgumentException(
                        "Invalid event contract or eventId mismatch");
            }

            return event;
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid OrderCreated JSON", ex);
        }
    }
}
~~~

The decoder only decodes and verifies the **contract**:

- `schemaVersion=1` is the only version supported by the demo.
- `ObjectMapper` from Spring Boot converts JSON to the Java record.
- `eventId` in the body must match the custom JMS property.
- `orderId` is non-blank, `amountMinor` is positive.

If the message violates the contract, the decoder throws an exception **before the application service performs side effects**. In a transacted environment, propagating the exception prevents the JMS transaction from committing normally; to prevent poison messages from retrying endlessly, configure max-delivery/DLQ/quarantine policies on the broker.

This is a simple decoder. For complex JSON contracts, consider a JSON Schema validator, message size/depth limits, data types, and policies for unknown fields/duplicate JSON keys. Never substitute "Jackson parsed it" for complete business validation.

### 7.6. OrderApplicationService.java

~~~java
package com.example.jmsthin;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final CountDownLatch processed =
            new CountDownLatch(1);

    public void process(OrderCreatedEvent event) {
        // Demo placeholder for a business operation.
        System.out.println(
                "BUSINESS_PROCESSED=" + event.orderId()
                        + " amountMinor=" + event.amountMinor());

        processed.countDown();
    }

    public boolean awaitProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return processed.await(timeout, unit);
    }
}
~~~

The service **has no JMS annotations**, does not know the Queue name, and does not accept `jakarta.jms.Message`. It can be unit-tested directly with an `OrderCreatedEvent`. The demo uses `CountDownLatch` to observe a single execution; it is **not an idempotency store** or a production service implementation.

Important: in reality `process` may include DB transactions, domain validation, and outbound ports, yet should never directly perform transport parsing or control JMS acknowledgment.

### 7.7. OrderJmsListener.java — Short Listener Method

~~~java
package com.example.jmsthin;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderJmsListener {

    private final OrderEventDecoder decoder;
    private final OrderApplicationService service;

    public OrderJmsListener(
            OrderEventDecoder decoder,
            OrderApplicationService service) {
        this.decoder = decoder;
        this.service = service;
    }

    @JmsListener(id = "ordersThinListener", destination = "demo.order-events")
    public void onMessage(
            @Payload String json,
            @Header("eventId") String eventId,
            @Header("schemaVersion") int schemaVersion) {

        OrderCreatedEvent event =
                decoder.decode(json, eventId, schemaVersion);

        service.process(event);
    }
}
~~~

**These are two meaningful statements in the listener**, not for line-count vanity: the method clearly expresses **transport data → validated event → business use case**.

There is no `catch (Exception)`, `new Thread`, `@Async`, `jmsTemplate.receive()`, or `message.acknowledge()` here. JMS/transaction runtime behavior is managed by the container; the service can be tested independently.

### 7.8. ThinListenerApplication.java

~~~java
package com.example.jmsthin;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ThinListenerApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ThinListenerApplication.class, args)) {
            // Once ApplicationRunner finishes, close the demo context.
        }
    }

    @Bean
    ApplicationRunner sendOneEvent(
            JmsTemplate template,
            OrderApplicationService service) {

        return args -> {
            String json =
                    "{\"eventId\":\"EV-188\","
                            + "\"orderId\":\"O-188\","
                            + "\"amountMinor\":12550}";

            template.convertAndSend("demo.order-events", json, message -> {
                message.setStringProperty("eventId", "EV-188");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            if (!service.awaitProcessed(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not process message in 10 seconds");
            }

            System.out.println("HANDLER_OBSERVED=true");
        };
    }
}
~~~

`@EnableJms` is written explicitly to make the annotation infrastructure easy to follow; Spring Boot JMS auto-configuration can also provide it. The producer is `JmsTemplate`, sending a String so `SimpleMessageConverter` creates a `TextMessage`; two custom properties are attached via `MessagePostProcessor`. The listener receives the String and mapped properties via the Spring listener adapter.

An `ApplicationRunner` sends the message after context initialization; the JMS listener container has already had a chance to auto-start during context refresh. Even if the consumer is not yet ready to receive, the demo Queue can retain the message until a consumer is ready per broker policy.

Using `try-with-resources` closes the context when the demo finishes, preventing a console app from staying alive due to listener threads.

### 7.9. Run Command and Output

From the `jms-thin-listener-demo` directory:

~~~bash
mvn spring-boot:run
~~~

The lines printed by application code, excluding Maven/Spring/Artemis logs, are expected to be:

~~~text
BUSINESS_PROCESSED=O-188 amountMinor=12550
HANDLER_OBSERVED=true
~~~

`BUSINESS_PROCESSED` is printed **before** the `CountDownLatch` counts down to 0, so it appears before the line from the runner. However, `HANDLER_OBSERVED=true` only proves the service reached the latch point, **not a certificate that a database or JMS transaction committed**. This example was not executed via Maven in this document; this is the expected output when dependencies/broker work as configured.

### 7.10. Experiments to Try

1. Change `eventId` in the JMS property from `EV-188` to `EV-DIFFERENT`, keeping the body: the decoder rejects it before calling the business service. With a transacted session, the broker may redeliver; never run this failure test unbounded in production.
2. Change `schemaVersion` from `1` to `2`: the current decoder rejects unsupported versions.
3. Change `amountMinor` in JSON to `0`: the decoder rejects it per contract.
4. Remove the custom property `eventId`: Spring `@Header` argument resolution may fail **before the listener method runs**.
5. Temporarily move decoding logic into the listener: responsibilities multiply and unit-testing the JMS method becomes harder despite identical output.
6. Increase listener concurrency to multiple consumers and send multiple messages: the same singleton service can be called concurrently, so state and DB transactions must be thread-safe.
7. Keep the listener unchanged while substituting a fake `OrderApplicationService` in a unit test: you can verify delegation without a broker.

## 8. Why Shouldn't You Catch, Log, and Return?

A common mistake:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String json) {
    try {
        service.process(decoder.decode(json));
    } catch (Exception ex) {
        log.error("Order failed", ex);
        // Wrong if rollback/redelivery is needed yet the method returns normally.
    }
}
~~~

This is a counter-example fragment; `service`, `decoder`, and `log` are undefined. When the method returns **normally**, the listener container may treat the call as successful, and with a local transacted JMS session it may **commit** the message receipt. The message can vanish from the Queue even though the order was never processed.

**The right approach is not "always throw every exception forever."** Classify errors instead:

- **Transient:** database unreachable, downstream temporarily failing, lock timeout. Usually let the exception propagate so the JMS transaction rolls back and the broker redelivers per backoff/max-delivery settings.
- **Permanent payload/contract error:** invalid JSON, unsupported version, missing required field. Do not retry the identical payload infinitely; use DLQ/quarantine and alerts per broker/application policy.
- **Already processed earlier (duplicate):** an idempotent consumer can treat it as **successful**, returning normally to commit/ack the message **after verifying** the event was already processed.
- **Valid business rejection:** define the business outcome, optionally record rejected status to DB/outbox and ack intentionally; never randomly "swallow errors."

If logging is needed:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String json) {
    try {
        service.process(decoder.decode(json));
    } catch (RuntimeException ex) {
        log.warn("Order message failed", ex);
        throw ex; // Let the container handle it per transaction/error policy.
    }
}
~~~

The fragment above **is not a recommendation to catch everywhere**; if your service/logging infrastructure already records enough detail, you do not need to catch in the listener. Avoid logging sensitive payloads and infinite repeated stack traces. Error classification belongs where enough context exists to distinguish transient/permanent errors and can be tested.

## 9. Session Transactions, Acknowledgment, and Retries

**A short listener does not make processing automatically reliable** if JMS transactions are misconfigured.

In `DefaultMessageListenerContainer`, when using non-transacted `AUTO_ACKNOWLEDGE`, Spring may acknowledge the message **before the listener business method finishes**, so an exception in the method does not guarantee redelivery. For workloads needing reliability, Spring recommends **transacted sessions** or an appropriately configured transaction manager.

Spring Boot 3.5 has the property:

~~~properties
spring.jms.listener.session.transacted=true
~~~

In the example, this means listener invocations run inside a **local JMS transaction**: on success, the container commits receipt; if an exception propagates normally, it rolls back and the broker may redeliver per policy. That is a **JMS Session transaction**, not a database transaction.

| Scenario | With local JMS transacted listener, in principle |
| --- | --- |
| Decoder + service return successfully | Container can commit JMS receipt. |
| Decoder/service throws exception out of listener | Container rolls back JMS receipt; message may redeliver. |
| Listener catches exception and returns | Container may commit, causing lost business processing. |
| Business DB committed yet JMS commit failed | Message may redeliver; requires idempotent service. |
| Exception caught and handled as valid duplicate | May return normally to ack/commit, once duplicate is verified. |
| Process killed mid-handling | Callback cleanup not guaranteed; broker may redeliver. |

**`sessionTransacted=true` does not guarantee an exactly-once business outcome.** For example, the DB commits successfully and then the JMS session rolls back due to a network drop; the same message will arrive again. The outcome depends on the service's idempotency/transaction design.

### 9.1. Retries Exist at Multiple Layers

Distinguish:

1. **Broker redelivery:** message is redelivered after rollback/session failure; configure delay, max attempts, and DLQ on the broker.
2. **Application retry:** service retries a temporarily failing call within the same delivery; use backoff/time budgets without stretching JMS transactions indefinitely.
3. **Producer retry:** producer may resend a new message, usually with a new `JMSMessageID` yet the same business `eventId`.
4. **Listener container recovery:** reconnecting to the broker, distinct from retrying a domain operation.
5. **Replay from DLQ:** controlled operational action after fixing the decoder/logic.

Do not mash everything into a `for` loop inside the listener. Specifically, never call `Thread.sleep(60_000)` inside a listener to delay retries per message; it ties up the consumer thread/session and crushes throughput. Broker redelivery delay/backoff is generally better suited for waiting between deliveries.

### 9.2. Dead-Letter / Quarantine

When a message has a bad schema or unrecoverable error, some brokers can route it to a DLQ after failed delivery attempts. Artemis supports `dead-letter-address` and `max-delivery-attempts` in address settings. Configure **real destinations and ACLs**, alerts, retention, and replay procedures.

A Queue with a toxic (poison) message must not spin in infinite rollbacks and stall the backlog. Yet it must not be silently acked and dropped from the system without a trace either. The solution must be explicit: **quarantine/DLQ + reason code + observability + controlled replay**.

## 10. @Async and Fire-and-Forget in Listeners: A Major Trap

Counter-example:

~~~java
@JmsListener(destination = "orders.commands")
public void onMessage(String payload) {
    asyncOrderService.processAsync(payload); // Returns immediately.
}
~~~

If `processAsync` runs via `@Async` or returns an incomplete `CompletableFuture` while the listener method has already returned, **the container may commit/ack JMS before the real task finishes**. When the background task fails, the broker may no longer have the message to retry naturally.

**Do not "fix" listener speed by adding `@Async`.** Short listener method ≠ short processing time. A listener making one **synchronous** `service.process(...)` call still occupies the container thread until the service finishes; that is normal when success/failure must tie to acknowledgment.

If long-running work must be decoupled from the JMS transaction, use an architecture ensuring a **durable handoff**:

- Transactional inbox: persist the event in a DB/idempotency store in `PENDING` state before committing receipt, then let background workers process it.
- Outbox/durable job queue: atomically record job/side-effect requests inside a designed DB transaction; manage retries and dedup separately.
- A second Queue: only treat handoff as complete when publish and ack share suitable semantics; do not assume two broker sends are atomic without transaction configuration.
- Preserve a stable `eventId`, visibility timeouts/retries, and monitoring at the new worker layer.

To prove correctness, identify **what is durable**, **when ack happens**, **who retries**, and **how double-processing is prevented**. Never just replace a synchronous call with a thread pool.

## 11. Idempotency Belongs to the Application Service

In typical JMS/DB setups, messages **can be redelivered**. A message `eventId=EV-188` can arrive twice even if the producer sent it once—for example, when a DB commit succeeds and the JMS commit fails.

Minimal DB table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

The schema above is an **SQL example**; timestamp/identity syntax varies by database. `event_id` needs a DB-enforced unique constraint; checking `existsById` before inserting **is not enough** against races across concurrent consumers.

The application service can execute **in the same DB transaction**:

~~~java
// Illustrative fragment, NOT a standalone class.
// processedEventRepository and orderRepository are application ports/repos.

@Transactional
public void process(OrderCreatedEvent event) {
    boolean firstTime = processedEventRepository.tryInsert(event.eventId());

    if (!firstTime) {
        return; // Duplicate already processed: success per policy.
    }

    orderRepository.applyOrderCreated(event.orderId(), event.amountMinor());
}
~~~

`tryInsert` is an **application-defined API** that must use a unique-constraint INSERT or equivalent strategy and handle transactions properly. A DB transaction rollback must revert both the inbox record and the business update on error. Never use an in-memory-only `ConcurrentHashMap` for production idempotency because data is lost on restart and not shared across replicas.

**Correct ordering:** check duplicates via database/unique key; if new, apply business updates in the transaction; once the service returns successfully, the JMS container has a sound basis to ack/commit the message. If the DB committed yet the JMS commit failed, redelivery hits `tryInsert`, detects the duplicate, and returns normally, preventing duplicate side effects.

If the business outcome requires calling external payment/email APIs outside the DB, SQL transactions do not cover those APIs; use outbox, provider idempotency keys, and appropriate patterns.

## 12. Do Not Drag the JMS API into the Domain Layer

A transport-coupled design:

~~~java
public void placeOrder(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    String eventId = message.getStringProperty("eventId");
    // Business logic remains coupled to JMS Session/headers/properties.
}
~~~

Weakness: the service is hard to invoke from REST, batch jobs, or plain unit tests; changing JMS providers/converters forces edits to business code.

Instead, map required information into an application object:

~~~java
// Java 17 record, snippet when business context is needed.
public record IncomingEventContext(
        String eventId,
        String correlationId,
        String tenantId) {
}
~~~

Example listener mapping transport details:

~~~java
// Snippet: decoder, service, and matching headers already exist.
OrderCreatedEvent event = decoder.decode(json, eventId, version);
IncomingEventContext ctx =
        new IncomingEventContext(eventId, correlationId, tenantId);

applicationService.process(event, ctx);
~~~

`IncomingEventContext` is an **application-layer** contract, not a native JMS message. Limit it to fields truly needed for business/observability. `tenantId` must be verified against identity/ACLs; do not pass it into the domain assuming it is safe by default.

Also avoid coupling the application service to `JmsTemplate` just to send emails/HTTP responses. If a use case must emit a domain event, define an `EventPublisher` port and implement the adapter via JMS/outbox. That keeps core logic testable without starting a broker.

## 13. @Transactional on Services and the JMS–DB Boundary

Using `@Transactional` on services is helpful for DB work, yet **it does not automatically combine DB and JMS into a distributed transaction**.

Example:

~~~java
@Service
public class OrderApplicationService {

    @Transactional
    public void apply(OrderCreatedEvent event) {
        // Write orders and processed_events tables in one DB transaction.
    }
}
~~~

This is a fragment requiring `@Transactional` imports, a configured `PlatformTransactionManager` for the datasource, and repository implementations. If multiple transaction managers exist (JMS/DB), select the right manager via qualifiers or a consistent policy.

**Two transaction layers:**

- `spring.jms.listener.session.transacted=true`: local JMS Session receive/commit/rollback.
- `@Transactional` with DB transaction manager: independent database transaction.

After the service DB commits and the listener method returns, the JMS commit occurs **afterward**; a crash in between causes redelivery. Design idempotency/outbox to handle this case. True atomicity across multiple resources may require JTA/XA, not just annotations.

**Proxy trap:** If a service invokes its **own** `@Transactional` method via `this.process(...)`, Spring's proxy-based transaction can be bypassed. Having the listener adapter call an injected Spring service bean cleanly separates the proxy boundary.

**Do not catch `DataAccessException` in the listener and return** unless the service achieved an intentional success outcome. Let the exception propagate or classify it under an explicit policy to control rollbacks.

## 14. Multi-Layer Error Handling

Not every error occurs inside the listener body. A pipeline:

~~~mermaid
flowchart TD
    Q[("Queue")] --> A["JMS receive / container"]
    A --> B["Message conversion + argument resolution"]
    B --> C["@JmsListener method"]
    C --> D["Decoder validation"]
    D --> E["Application service"]
    E --> F["DB / external ports"]
    B --> X["Conversion error"]
    D --> Y["Contract error"]
    F --> Z["Business / transient error"]
    X --> T["Container transaction / error policy"]
    Y --> T
    Z --> T
    T --> R["Commit / rollback / redelivery / DLQ"]
~~~

**Four error zones:**

1. **Before listener:** `MessageConverter` cannot read the body, or a required `@Header` is missing. `onMessage` may **not run**, so in-method logs miss these errors.
2. **Decoder:** invalid JSON, unsupported schema version, header-body mismatch; permanent classifications typically need quarantine.
3. **Service:** DB unavailable, optimistic lock, business constraint missing, duplicate; may be transient or permanent depending on cause.
4. **After service:** JMS commit/connection error despite completed business work; requires idempotency upon redelivery.

Depending on configuration, Spring offers `ErrorHandler` on `DefaultMessageListenerContainer` to log/observe errors; do not treat a logging-only handler as automatically routing messages to a DLQ. Rollback and acknowledgment boundaries still belong to the container/session/provider. Inspect the cause chain and test against a real broker.

Never add a `catch (Throwable)` in the listener to "keep the app alive": it can swallow fatal errors and miscommit messages. For permanent errors, choose an explicit policy: **reject/quarantine** or broker redelivery-limit/DLQ, never silent failure.

## 15. Concurrency: Even a Short Listener Needs a Thread-Safe Service

A singleton `@Component` listener can be called concurrently by multiple JMS consumer threads when increasing `spring.jms.listener.min-concurrency`/`max-concurrency` or `@JmsListener(concurrency="...")`.

**Note:** high container concurrency **does not create a new service bean per message**; multiple threads invoke the same singleton service/proxy simultaneously.

Counter-example:

~~~java
@Service
public class UnsafeOrderCounter {

    private int count;

    public void process(OrderCreatedEvent event) {
        count++; // Race condition when multiple messages process concurrently.
    }
}
~~~

This is a counter-example code fragment. Use thread-safe metric counters for statistics, DB transactions with unique keys for business data, and never store `currentEventId` or `currentTenant` in shared mutable fields.

When concurrency increases:

- DB connection pools/transaction latencies must be sized appropriately.
- Idempotency must guard against races across replicas and consumers.
- Never assume FIFO business completion across parallel workers, `JMSPriority`, or redeliveries.
- On a Queue, one message normally goes to one competing consumer at a time, though it may **redeliver** after failures.
- On a Topic, each subscription has distinct semantics; do not generalize from Queues.
- MDC/ThreadLocal context must be set and cleared properly to prevent leaking trace/tenant IDs across messages.

**Keeping the listener method short does not make processing time short.** If the service performs a 30-second synchronous task, the JMS consumer thread remains occupied for 30 seconds; throughput is solved by architecture, concurrency, bulkheads, and durable handoffs, not merely "fewer lines."

## 16. Observing What the System Is Processing

A thin listener still needs observability, applied at the **right layers**:

| Layer | Appropriate metrics/logs |
| --- | --- |
| JMS broker/container | Queue depth, message age, consumer count, redelivery, DLQ, recovery/connection errors. |
| Listener adapter | Endpoint ID, `JMSMessageID`, correlation ID, schema version, decode success/failure (never log sensitive bodies). |
| Decoder | Unsupported version, malformed JSON, invalid contract, header mismatch. |
| Application service | Use-case duration, idempotent duplicate count, business rejections, DB latency. |
| Outbound ports | HTTP errors, retry budgets, remote idempotency keys, timeout rates. |

Attach a contracted `eventId` to correlate producer–consumer–database logs; `JMSMessageID` is a provider-generated per-send ID and does not replace `eventId` for retries/idempotency.

### 16.1. Never Put Sensitive Data in Logs

Avoid:

~~~java
log.info("Received entire message: {}", json);
~~~

Payloads can contain customer names, addresses, accounts, or access tokens. Use approved metadata instead:

~~~java
log.info(
        "Processing eventId={} schemaVersion={}",
        eventId, schemaVersion);
~~~

Both fragments assume `org.slf4j.Logger log`, `json`, and metadata exist; they are not standalone classes. Define masking, retention, trace context, and audit policies before enabling production logs.

### 16.2. Listener Success Differs from Committed Transaction

Logging `"listener returned"` does not guarantee JMS commit or DB commit in all failure modes. A `CountDownLatch`/handler-invoked metric only confirms **execution reached that point**. For reliability integration tests, check DB side effects, JMS redelivery/queue metrics, and transaction boundaries separately.

## 17. Testing Layer by Layer

### 17.1. Decoder Unit Tests

Given `OrderEventDecoder` with an `ObjectMapper`:

- Valid JSON / version 1 / matching `eventId` → returns the exact `OrderCreatedEvent`.
- Malformed JSON → throws `IllegalArgumentException` with Jackson cause.
- Unsupported `schemaVersion=2` → rejects before business side effects.
- Mismatched header/body `eventId` → rejects.
- Empty `orderId`, `amountMinor=0` → rejects.
- Numeric boundary values, Unicode/escaped JSON, null vs. missing per contract.
- With schema evolution, test unknown fields and version mappings intentionally.

Decoder unit tests **do not need a broker** and should not mock JMS transactions.

### 17.2. Listener Adapter Unit Tests

Using a fake `OrderEventDecoder`/`OrderApplicationService` or Mockito:

1. Call `listener.onMessage(validJson, "EV-188", 1)` directly.
2. Assert decoder receives the exact payload, `eventId`, and `schemaVersion`.
3. Assert service is invoked **once** with the decoded event.
4. Make decoder throw an exception: verify service is not called.
5. Make service throw an exception: verify the listener **does not swallow the error**.
6. Do not expect this test to prove JMS rollback, since no container/broker is running.

When the goal is verifying `@JmsListener` annotations/queue/header mapping, add integration tests.

### 17.3. Application Service Unit Tests

Test with plain `OrderCreatedEvent`:

- Valid business rules (state transitions, invariants).
- DB transaction rolls back when repository fails.
- Duplicate `eventId` is handled idempotently.
- Payment/email actions use idempotency keys and timeout policies.
- No need to start Artemis to unit-test pricing rules.

A **JMS-free service test** is strong evidence that boundaries are clean, rather than hidden helpers accessing `JmsTemplate`.

### 17.4. Broker Integration Tests

On a dedicated test Queue with no competing consumers:

1. Boot Spring context with embedded/test Artemis broker.
2. Send a `TextMessage` with JSON body and JMS properties.
3. Use a latch or Awaitility with timeout to wait for service invocation.
4. Verify body/headers map properly; version mismatch is rejected.
5. With `session.transacted=true`, make the service throw an exception and observe redelivery per broker policy.
6. Test broker DLQ/quarantine with bounded attempts; never test poison messages on production.
7. If using a database, inject a controlled failure between DB commit and JMS commit to prove idempotency.
8. Increase concurrency and test duplicate races, transaction isolation, and session-thread usage.
9. Test shutdown during in-flight work; do not assume `@PreDestroy` always runs if the process is killed.
10. Verify sensitive data does not leak into headers/logs/DLQ.

### 17.5. Failure Test Matrix

| Input / condition | Does listener call service? | Expected outcome |
| --- | --- | --- |
| Valid JSON, version 1, matching `eventId` | Yes | Service processes. |
| Invalid JSON | No | Decoder throws; transaction/error policy handles. |
| Unsupported `schemaVersion` | No | Contract error; quarantine/DLQ policy. |
| Missing `eventId` in JMS property | Method may not be called | Pre-method argument resolution error; check container logs. |
| DB timeout | Yes, then fails | Exception propagates; rollback/retry policy. |
| Duplicate already-committed event | Possibly | Service detects duplicate and returns success. |
| Service returns incomplete `CompletableFuture` and listener returns | Listener finishes early | **Risk of premature ack**; avoid fire-and-forget without durable handoff. |
| Broker disconnects on commit | Service may have run | Redelivery may occur; requires idempotency. |

## 18. Incrementally Refactoring an Overgrown Listener

You do not have to rewrite everything at once:

1. **Map scope:** list every responsibility in the method (decode, validate, SQL, HTTP, publish, logging, retry).
2. **Lock behavior with tests:** golden payloads and success/failure, ack/redelivery cases.
3. **Extract decoder:** move JSON/schema/header parsing into a pure component; verify contract parity.
4. **Extract application service:** place use case and transactions in a Spring-injected service; avoid self-invocation proxy traps.
5. **Define ports** for repositories/outbound APIs; test business logic without a broker.
6. **Remove catch-and-swallow** after confirming JMS transaction/error policies; test poison messages separately.
7. **Add idempotency** using event IDs and unique constraints/outbox as needed.
8. **Measure latency and concurrency:** avoid a "short-looking listener" masking uncontrolled slow side effects.
9. **Keep the adapter thin and clear:** receive payload/headers, decode, delegate, add no extra side effects.
10. **Monitored rollout:** track DLQ, redelivery, backlog, success/error rates, and maintain rollback readiness.

Before–after:

~~~text
BEFORE
  @JmsListener
    -> parse JSON
    -> validate
    -> SQL + domain logic
    -> HTTP payment + email
    -> send JMS audit
    -> catch all + log + return

AFTER
  @JmsListener / inbound adapter
    -> decoder.decode(payload, headers)
    -> applicationService.process(event)
         -> domain policy
         -> repository / transaction / idempotency
         -> durable outbox / integration ports
  container + broker
    -> receive / session transaction / redelivery / DLQ
~~~

The "AFTER" design does not automatically merge DB and JMS into a single unified transaction. It **clarifies where transactions, idempotency, and outbox live so each piece can be tested**.

## 19. Common Mistakes When Applying Thin Listeners

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| One-line listener yet service takes raw `jakarta.jms.Message` | Merely shifted coupling into the service. | Map payload/metadata into application-level DTOs. |
| Catching `Exception`, logging, and returning | Can commit an unprocessed message. | Propagate or classify outcomes intentionally. |
| Putting `@Async` on service and returning immediately | JMS ack may happen before business completion. | Synchronous handling or durable inbox/handoff. |
| Using mutable Java singleton fields for `currentEventId` | Races across listener threads. | Local variables/immutable DTOs, storage transactions. |
| Failing on every duplicate | Infinite redelivery even though side effects succeeded. | Idempotency key/unique constraint treating duplicates as success. |
| Calling `message.acknowledge()` arbitrarily in transacted container | Breaks ownership/transaction semantics. | Let container manage per factory/session. |
| Trusting `schemaVersion` header as already validated data | Header and body may conflict. | Decoder validates both header and payload. |
| Using `@Payload OrderCreatedEvent` without a JSON converter | Default converter does not build arbitrary domain records. | Configure converter or receive String + decoder. |
| Missing `@Header` fails without in-method log | Failed in argument resolution before method ran. | Monitor container-level errors. |
| Treating DB `@Transactional` as JMS XA | The two local transactions remain independent. | Idempotency/outbox, or real XA when justified. |
| Cranking concurrency to fix slow HTTP latency | Exhausts DB/HTTP pools and increases duplicates/races. | Timeouts, bulkheads, backpressure, worker design. |
| Over-slicing listener into a dozen empty wrappers | Obscures control flow. | Split along real responsibilities with clear contracts. |
| Logging full payload with PII/secrets | Sensitive data leaks into logs and DLQ. | Structured metadata logs, redaction, ACLs. |

## 20. Self-Practice Questions

1. **Primary role of `@JmsListener`?** Receive payload/metadata from the adapter and delegate processing.
2. **Does the business service need to know the Queue name?** No, when boundaries are cleanly separated.
3. **What are the two statements in the example listener?** `decoder.decode(...)` followed by `service.process(...)`.
4. **Why not catch and return after a DB failure?** The container may treat processing as successful and commit the JMS receipt.
5. **Should `@Async` fire-and-forget be used to make a listener "fast"?** No, without a durable handoff, acknowledgment may occur too early.
6. **Does `spring.jms.listener.session.transacted=true` guarantee atomic DB + JMS commits?** No; only local JMS Session unless another transaction coordinator is used.
7. **Why do you need `eventId` in addition to `JMSMessageID`?** Idempotency and retries of the same event may receive different JMS IDs.
8. **What should happen on malformed JSON?** Reject before business side effects, classify as a permanent error, bound retries, and quarantine/DLQ.
9. **Why should the decoder verify header/body `eventId`?** Prevents metadata–payload mismatches from corrupting processing/tracing.
10. **Does default `SimpleMessageConverter` convert every JSON String into a domain record?** No; a converter or decoder must be configured.
11. **Where do missing `@Header` failures occur?** Potentially during argument resolution before the listener method runs.
12. **Can a singleton service be invoked by multiple listener threads concurrently?** Yes; it must be thread-safe.
13. **What happens if the service finishes yet the JMS commit fails?** The message may redeliver; use idempotency.
14. **With DB `@Transactional`, should the listener catch errors and ack manually?** No; preserve proper transaction boundaries and error policies.
15. **When should a duplicate event be treated as successful?** When the idempotency store confirms effects were already committed per contract.
16. **Does `@PostConstruct` on a listener run per message?** No, it runs once during bean initialization.
17. **Must listener tests always start a broker?** Unit tests for delegation do not; integration tests for mapping/retries need a broker.
18. **Ultimate goal of a thin listener?** Isolate transport, make use cases easy to test, and keep error/transaction behavior predictable.

## 21. Official References

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@Payload`/`@Header` method signatures, `@EnableJms`, listener factories, and registries.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): message-driven POJOs, listener containers, local JMS transactions, and redelivery.
- [Spring Framework 6.2 — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): acknowledgment, recovery, threading, transaction managers.
- [Spring Framework 6.2 — @JmsListener](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `destination`, `containerFactory`, `concurrency`, listener ID.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): embedded Artemis and `JmsTemplate` auto-configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.listener.session.transacted`, listener concurrency, and embedded Queues.
- [Spring Boot 3.5 — Disable Transacted JMS Session](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): notes on default transactions and custom listener factories.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message headers/properties, acknowledgment, transactions, and redelivery.
- [Apache ActiveMQ Artemis — Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages.html): delivery attempts, redelivery delays, and dead-letter handling.

**Takeaway:** An ideal listener is an **inbound adapter with clear responsibilities**: receive a message, turn it into valid input, delegate to an application service, and let exception/transaction policies handle the outcome. "Short" is not a cosmetic goal: the real goal is **separating transport from business logic, testing each layer independently, never acking too early, never losing errors, and staying safe under retries and concurrency**.
