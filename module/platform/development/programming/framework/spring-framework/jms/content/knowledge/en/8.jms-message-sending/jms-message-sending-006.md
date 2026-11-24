# Adding Metadata with MessagePostProcessor in Spring JMS

## 1. Why Do We Need MessagePostProcessor?

When sending a message over JMS, a service often needs to transmit **two groups of information**: (1) the **body/payload** holding business data; (2) **metadata** for identification, tracking, classification, filtering, request–reply correlation, or version management. For example, an order-created event has a JSON body containing the order ID and total amount, while the consumer also needs `eventType=OrderCreated`, `schemaVersion=2`, `tenantId=tenant-demo`, `traceId`, and `JMSCorrelationID`.

In Spring Framework, the **`org.springframework.jms.core.MessagePostProcessor`** interface lets you hook into the **`jakarta.jms.Message` after payload conversion but before sending to the broker**. It is the natural place to add **producer-settable JMS headers** and **custom message properties** without manually managing `Session`/`MessageProducer` for every send call.

This lesson belongs to the **Message Sending** section of Spring JMS. After completing it, you will be able to:

- State the exact order `convertAndSend` → `MessageConverter` → `MessagePostProcessor` → producer send.
- Invoke `JmsTemplate.convertAndSend(..., MessagePostProcessor)` overloads with a lambda or a dedicated class.
- Distinguish **body, JMS headers, and JMS properties**, and when each value is assigned.
- Add `JMSCorrelationID`, `JMSType`, `JMSReplyTo`, and properly typed properties (`String`, `int`, `boolean`, `long`, ...).
- Avoid manually editing JMS-provider-managed headers such as `JMSMessageID`, `JMSTimestamp`, `JMSExpiration`, and `JMSPriority` in an attempt to replace QoS.
- Run a **Java 17+, Spring Boot 3.5.x, embedded Artemis** demo, read the message back to verify metadata, and apply a message selector.

## 2. Processing Flow: After Conversion, Before Send

Commonly used method:

~~~java
void convertAndSend(String destinationName,
                    Object payload,
                    org.springframework.jms.core.MessagePostProcessor processor);
~~~

Similar overloads accept `jakarta.jms.Destination` or use the default destination if configured. This signature is shown for explanation; it is **not** a method you need to implement yourself in a project.

~~~mermaid
flowchart LR
    A["Java payload"] --> B["MessageConverter.toMessage"]
    B --> C["JMS Message"]
    C --> D["MessagePostProcessor.postProcessMessage"]
    D --> E["MessageProducer.send"]
    E --> F["Broker"]
    F --> G["JMS Consumer"]
~~~

Short example:

~~~java
// Fragment inside a Spring bean with an injected JmsTemplate template.
template.convertAndSend("orders.events", "ORDER-105", message -> {
    message.setJMSCorrelationID("corr-O-105");
    message.setStringProperty("eventType", "OrderCreated");
    message.setIntProperty("schemaVersion", 2);
    return message;
});
~~~

With the default `SimpleMessageConverter`, the input `String` is converted into a `TextMessage`. The lambda receives the **converted JMS Message**, attaches metadata, and returns the Message for `JmsTemplate` to send. There is no `Thread.sleep` and no manual creation of `Connection`/`Session`.

Separate three distinct moments clearly:

1. **Payload conversion:** `MessageConverter.toMessage(..., session)` creates the body and JMS message type.
2. **Post-process:** the callback can modify the message **before sending**. Fields assigned by the provider upon sending may not exist yet or may not hold their final values.
3. **Send:** the provider populates JMS-managed headers, applies QoS and transactions, and delivers the message to the broker.

Therefore, **finishing the post-processor does not mean the broker has stored or delivered the message successfully**. Send errors, rollbacks, or connection failures can still occur after the callback returns.

## 3. Right Interface, Right Package

Spring JMS's `MessagePostProcessor` is a functional interface with the core contract:

~~~java
// API shape for reference; do not create this file/interface in your application.
jakarta.jms.Message postProcessMessage(
        jakarta.jms.Message message) throws jakarta.jms.JMSException;
~~~

- The argument is the `jakarta.jms.Message` **created by the converter**.
- The return value is a **non-null** JMS Message; typically you modify and return **the same message you received**.
- The callback is allowed to throw `JMSException`. `JmsTemplate` normally translates checked JMS exceptions into unchecked `org.springframework.jms.JmsException`.
- Because it has a single abstract method, you can use a lambda, method reference, or dedicated class.

**Name collision warning:** Spring also has `org.springframework.messaging.core.MessagePostProcessor`. It operates on `org.springframework.messaging.Message<?>`, which **differs** from `jakarta.jms.Message`. When using `JmsTemplate.convertAndSend`, import:

~~~java
import org.springframework.jms.core.MessagePostProcessor;
import jakarta.jms.Message;
import jakarta.jms.JMSException;
~~~

With **Spring Boot 3.x / Spring Framework 6.x**, use `jakarta.jms.*` and **never** mix it with `javax.jms.*` from legacy Java EE/JMS. Letting an IDE pick the wrong import is a common cause of compiler errors or a callback lacking `setJMSCorrelationID`.

## 4. Distinguishing Body, Standard JMS Headers, and Custom Properties

| Component | Role | Examples | API |
| --- | --- | --- | --- |
| **Body** | Business data. | Order JSON, byte[], MapMessage. | `TextMessage.getText()`, converters... |
| **Client-settable standard JMS headers** | Logical correlation and identification. | `JMSCorrelationID`, `JMSType`, `JMSReplyTo`. | `setJMSCorrelationID`, `setJMSType`, `setJMSReplyTo`. |
| **Provider-managed headers** | Actual send/delivery metadata. | `JMSMessageID`, `JMSTimestamp`, `JMSExpiration`, `JMSDeliveryTime`, `JMSPriority`. | Mostly read after send / on consumer; configure QoS via producer/template. |
| **Custom properties** | Application metadata for filtering, classification, tracing. | `eventType`, `schemaVersion`, `traceId`, `tenantId`. | `setStringProperty`, `setIntProperty`, ... |

Visualizing a message:

~~~text
Headers:
    JMSMessageID     = ID:...             (assigned by provider)
    JMSCorrelationID = corr-O-105        (set by client)
    JMSType          = order.created
    JMSTimestamp     = ...               (assigned by provider)
Properties:
    eventType        = "OrderCreated"    (String)
    schemaVersion    = 2                 (int)
    tenantId         = "tenant-demo"     (String)
    auditRequired    = true              (boolean)
Body:
    {"orderId":"O-105","status":"CREATED"}
~~~

This is a **logical representation**, not a mandatory on-the-wire serialization format. A custom property is **independent metadata**, not a field that JMS automatically extracts from a JSON body. For instance, the selector `eventType = 'OrderCreated'` reads the JMS property; it does **not parse** `eventType` from the body.

### 4.1. JMSCorrelationID

~~~java
message.setJMSCorrelationID("corr-O-105");
~~~

Consumers read it via `message.getJMSCorrelationID()`. The value links messages belonging to a request/reply or logical transaction; the application defines the convention. **Do not conflate**:

- `eventId`: identifies **a business event**; it should stay stable across retries/republishes of the same event to support idempotency.
- `JMSCorrelationID`: identifier linking an exchange flow; a single correlation may span multiple events.
- `JMSMessageID`: ID assigned by the provider **for a send attempt**; if a producer retries with a new message, it generally receives a different ID.

**Do not expect `getJMSMessageID()` inside the post-processor**: the provider usually assigns the ID only during send. Do not fabricate a fake string starting with `ID:` and treat it as a provider ID; use your own application ID such as `corr-O-105` or a UUID when needed.

### 4.2. JMSType

~~~java
message.setJMSType("order.created");
~~~

`JMSType` describes the message type according to business convention. `JMSType="order.created"` is **distinct** from the message being a `TextMessage`: a `TextMessage` can carry many kinds of events. This value can also be used in message selectors, so keep naming conventions consistent between producer and consumer.

### 4.3. JMSReplyTo

`JMSReplyTo` specifies the destination where the sender expects to receive a reply:

~~~java
// Fragment: replyDestination is an existing jakarta.jms.Destination.
message.setJMSReplyTo(replyDestination);
~~~

It expects a **`Destination` object**, not simply a String. Because `MessagePostProcessor` has no `Session` parameter, if you only know the queue name and want to create the destination object on the same session, use `MessageCreator`:

~~~java
// Fragment: requires JmsTemplate template.
template.send("orders.requests", session -> {
    jakarta.jms.TextMessage req =
            session.createTextMessage("STATUS? O-105");
    req.setJMSCorrelationID("req-O-105");
    req.setJMSReplyTo(session.createQueue("orders.replies"));
    return req;
});
~~~

`createQueue("orders.replies")` creates a **reference handle** to the Queue; whether the physical queue exists or is auto-created depends on the broker. When using `JmsTemplate.sendAndReceive` or built-in request–reply abstractions, do not manually overwrite `JMSReplyTo` in ways that conflict with the template's correlation/reply destination mechanism.

## 5. Custom Properties: Names, Data Types, and Selectors

JMS supports property value types: `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `String`. Set the right type on the producer:

~~~java
// Fragment inside a MessagePostProcessor callback:
msg.setStringProperty("eventType", "OrderCreated");
msg.setIntProperty("schemaVersion", 2);
msg.setBooleanProperty("auditRequired", true);
msg.setLongProperty("createdAtMillis", 1793328000000L);
msg.setDoubleProperty("riskScore", 0.35);
~~~

Consumer reads with matching getters:

~~~java
String eventType = msg.getStringProperty("eventType");
int schemaVersion = msg.getIntProperty("schemaVersion");
boolean auditRequired = msg.getBooleanProperty("auditRequired");
long createdAt = msg.getLongProperty("createdAtMillis");
double riskScore = msg.getDoubleProperty("riskScore");
~~~

This is a **code fragment** assuming an existing `jakarta.jms.Message msg`. Property methods can throw `JMSException`; handle exceptions according to your API/context.

**Property names obey JMS selector identifier rules:** the first character must be a Java identifier start, subsequent characters Java identifier parts, and names are case-sensitive. Avoid spaces, hyphens, and keywords like `AND`, `OR`, `TRUE`, `NULL`. Use `traceId` instead of `trace-id`. `schemaVersion` differs from `schemaversion`.

**Do not set arbitrary POJOs/Maps/Lists as a property**: JMS properties support only the primitive/String set above. To send objects, use the body/converter. If complex metadata is needed, model it in a JSON body or break it into a small number of purposeful properties.

### 5.1. Filtering by Property at the Broker

~~~java
// Fragment: session and queue already created.
jakarta.jms.MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2");
~~~

The selector evaluates `eventType` as a String and `schemaVersion` as a numeric property. If the producer called `setStringProperty("schemaVersion", "2")`, numeric comparison may not match as intended. Selectors **do not read JSON bodies** and are no substitute for security authorization.

### 5.2. JMSX Properties

The `JMSX` prefix is reserved by Jakarta Messaging for standard properties. Relevant fields include:

- `JMSXGroupID` and `JMSXGroupSeq`: producers can use these to describe message groups when the application/broker uses message grouping.
- `JMSXDeliveryCount`: set by the provider upon receipt to report delivery count (1 on first delivery, 2+ on redelivery).
- Other `JMSX` properties may be optional or provider-managed.

Message group example:

~~~java
template.convertAndSend("orders.events", "ORDER-105", msg -> {
    msg.setStringProperty("JMSXGroupID", "customer-42");
    msg.setIntProperty("JMSXGroupSeq", 1);
    return msg;
});
~~~

Use group IDs/sequences only when you understand your provider's message grouping rules; they do not by themselves guarantee exactly-once processing or completion order of independent DB transactions. **Never set `JMSXDeliveryCount` yourself** to simulate retries.

**Security:** `tenantId`, `role`, and `userId` are publisher-supplied data, so consumers must never rely solely on them for access control. Combine broker ACLs, producer authentication, and business validation. Avoid putting access tokens, passwords, or unnecessary customer data into properties/logs.

## 6. Lambdas, Dedicated Classes, and Reusable Processors

A lambda is the cleanest option for a single send call:

~~~java
template.convertAndSend("orders.events", "ORDER-105", msg -> {
    msg.setJMSType("order.created");
    msg.setStringProperty("eventType", "OrderCreated");
    return msg;
});
~~~

When metadata logic is reused in multiple places, write a class with immutable parameters:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.core.MessagePostProcessor;

public final class OrderMetadataProcessor implements MessagePostProcessor {

    private final String correlationId;
    private final int schemaVersion;

    public OrderMetadataProcessor(String correlationId, int schemaVersion) {
        this.correlationId = correlationId;
        this.schemaVersion = schemaVersion;
    }

    @Override
    public Message postProcessMessage(Message message) throws JMSException {
        message.setJMSCorrelationID(correlationId);
        message.setJMSType("order.created");
        message.setIntProperty("schemaVersion", schemaVersion);
        return message;
    }
}
~~~

This is the **content of `OrderMetadataProcessor.java`** (add a package matching your project). Invocation:

~~~java
template.convertAndSend(
        "orders.events",
        "ORDER-105",
        new OrderMetadataProcessor("corr-O-105", 2));
~~~

Any metadata that varies per request must be passed via constructor/method arguments or captured by a lambda from an **immutable** local variable. Never create a singleton processor with a mutable `currentCorrelationId` field set before each `convertAndSend`: concurrent requests can overwrite one another, attaching another request's ID to a message.

The callback must **return a non-null Message**. Typically use `return message;`. If you need to change body serialization globally, prefer configuring a `MessageConverter` rather than manually building a different Message inside the callback without clarity on its type and session.

## 7. Runnable Example: Java 17+, Spring Boot, Embedded Artemis

This demo requires no separate broker installation. Spring Boot creates `ConnectionFactory` and `JmsTemplate`, and ActiveMQ Artemis runs embedded. We send a JSON string, attach metadata, and then **receive the raw JMS Message** from the Queue to verify it.

Requirements: **JDK 17+** and **Maven 3.6.3+**. Structure:

~~~text
jms-postprocessor-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmspost/
    │   └── JmsPostProcessorDemoApplication.java
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
    <artifactId>jms-postprocessor-demo</artifactId>
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

Spring Boot parent manages compatible library versions. `spring-boot-starter-artemis` brings in the JMS client; `artemis-jakarta-server` enables the embedded broker.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.metadata
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

- Queue `demo.metadata` is provisioned by the embedded broker at startup.
- `receive-timeout=5s` keeps the demo from hanging indefinitely.
- `persistent=false` is for testing only; it does not prove messages survive restarts.
- `pub-sub-domain=false` uses Queue semantics instead of Topic.

### 7.3. Complete Java Source

Create `src/main/java/com/example/jmspost/JmsPostProcessorDemoApplication.java`:

~~~java
package com.example.jmspost;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsPostProcessorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsPostProcessorDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate jmsTemplate) {
        return args -> {
            String body =
                    "{\"orderId\":\"O-105\",\"status\":\"CREATED\"}";

            jmsTemplate.convertAndSend("demo.metadata", body, message -> {
                message.setJMSCorrelationID("corr-O-105");
                message.setJMSType("order.created");
                message.setStringProperty("eventType", "OrderCreated");
                message.setIntProperty("schemaVersion", 2);
                message.setBooleanProperty("auditRequired", true);
                message.setStringProperty("tenantId", "tenant-demo");
                return message;
            });

            Message incoming = jmsTemplate.receive("demo.metadata");
            if (!(incoming instanceof TextMessage received)) {
                throw new IllegalStateException(
                        "Did not receive TextMessage within 5 seconds");
            }

            System.out.println("BODY=" + received.getText());
            System.out.println(
                    "CORRELATION=" + received.getJMSCorrelationID());
            System.out.println("TYPE=" + received.getJMSType());
            System.out.println(
                    "EVENT_TYPE=" + received.getStringProperty("eventType"));
            System.out.println(
                    "SCHEMA_VERSION="
                            + received.getIntProperty("schemaVersion"));
            System.out.println(
                    "AUDIT_REQUIRED="
                            + received.getBooleanProperty("auditRequired"));
            System.out.println(
                    "TENANT=" + received.getStringProperty("tenantId"));
        };
    }
}
~~~

**Exact breakdown of the send/receive flow:**

1. `ApplicationRunner` runs once Spring starts the context; Boot has created `JmsTemplate` and the embedded broker.
2. The body is a `String` containing JSON, so the default converter turns it into a **TextMessage**. No extra JSON converter is needed to send an already-serialized string.
3. `MessagePostProcessor` sets `JMSCorrelationID`, `JMSType`, and four custom properties with proper types.
4. The callback returns `message`; `JmsTemplate` executes the JMS send to `demo.metadata`.
5. `JmsTemplate.receive` retrieves the **raw `jakarta.jms.Message`**, preserving metadata that would be stripped if reading only the body via `receiveAndConvert`.
6. Pattern matching `instanceof TextMessage` confirms the message type before calling `getText`.
7. Because there is only one producer and one synchronous consumer in this demo, it does not deal with multi-consumer contention. Production systems must handle transactions, idempotency, and retries as required.

Run from the `jms-postprocessor-demo` directory:

~~~bash
mvn spring-boot:run
~~~

The lines printed by the application code (ignoring Maven/Spring/Artemis logs) should read:

~~~text
BODY={"orderId":"O-105","status":"CREATED"}
CORRELATION=corr-O-105
TYPE=order.created
EVENT_TYPE=OrderCreated
SCHEMA_VERSION=2
AUDIT_REQUIRED=true
TENANT=tenant-demo
~~~

Timestamp/`JMSMessageID` lines are omitted because they **depend on each send**, while payload and custom metadata are fixed in the example and easy to verify. This is the expected output from the presented program, not a claim that Maven was executed in every environment.

## 8. When Are Headers Assigned by the Provider?

Inside `MessagePostProcessor`, client-settable headers such as `JMSCorrelationID`, `JMSType`, and `JMSReplyTo` may be modified. However, **several other headers are computed by the provider at send or receive time**:

| Header | Who determines it on send/receive? | Practical API |
| --- | --- | --- |
| `JMSMessageID` | Assigned by provider on send. | Read `getJMSMessageID()` after send or at consumer. |
| `JMSTimestamp` | Assigned by provider on send; may be disabled by configuration. | Read `getJMSTimestamp()`. |
| `JMSDestination` | Provider records actual target destination. | Choose destination via `convertAndSend(destination,...)`. |
| `JMSDeliveryMode` | Delivery mode policy on send. | Set via `JmsTemplate`/producer QoS. |
| `JMSPriority` | Effective priority value on send. | Set via QoS; do not rely on `setJMSPriority` in callback. |
| `JMSExpiration` | Provider calculates from time-to-live. | Set TTL on producer/`JmsTemplate`. |
| `JMSDeliveryTime` | Provider calculates from send time + delivery delay. | Set delivery delay on producer/`JmsTemplate`. |
| `JMSRedelivered` | Provider determines redelivery flag. | Consumer reads; do not use to spoof retries. |

You can add the following **on the receiving side** of the demo:

~~~java
System.out.println("MESSAGE_ID=" + received.getJMSMessageID());
System.out.println("TIMESTAMP=" + received.getJMSTimestamp());
System.out.println("DESTINATION=" + received.getJMSDestination());
System.out.println("PRIORITY=" + received.getJMSPriority());
~~~

Exact values are broker-determined; do not hardcode assertions against them. `JmsTemplate.convertAndSend` returns `void`, so it does not directly return `JMSMessageID` after sending; therefore, for business reconciliation, generate a dedicated `eventId` before sending.

**Mistake to avoid:** writing inside the callback:

~~~java
// Do not use the callback to override send QoS:
message.setJMSPriority(9);
message.setJMSExpiration(System.currentTimeMillis() + 60_000L);
message.setJMSDeliveryTime(System.currentTimeMillis() + 5_000L);
~~~

Providers can overwrite these fields on send; this is not a portable API to configure priority, TTL, or delay.

## 9. Configuring QoS Properly Instead of Editing JMS Headers

Set QoS on the producer or a configured `JmsTemplate`:

~~~java
// Fragment: requires an existing ConnectionFactory connectionFactory.
org.springframework.jms.core.JmsTemplate highPriority =
        new org.springframework.jms.core.JmsTemplate(connectionFactory);

highPriority.setExplicitQosEnabled(true);
highPriority.setPriority(8);
highPriority.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
highPriority.setTimeToLive(120_000L);

highPriority.convertAndSend("orders.urgent", "ORDER-105", msg -> {
    msg.setStringProperty("eventType", "UrgentOrder");
    return msg;
});
~~~

In Spring Boot 3.5, you can configure this in `application.properties`:

~~~properties
spring.jms.template.qos-enabled=true
spring.jms.template.priority=8
spring.jms.template.delivery-mode=persistent
spring.jms.template.time-to-live=2m
~~~

This is **template configuration**, not per-message metadata added automatically by a callback. With `JmsTemplate`, priority/delivery mode/TTL are applied on send when **explicit QoS** is enabled (Spring Boot may enable it automatically when certain QoS values are customized). Delivery delay has its own settings: `spring.jms.template.delivery-delay` or `template.setDeliveryDelay(...)`.

**Crucial rule:** `JmsTemplate` can be shared across multiple threads once stably configured. Do not repeatedly call `setPriority`/`setTimeToLive` on a shared singleton before each `convertAndSend`, because concurrent requests can "borrow" each other's policy. If different message types need different QoS settings, use separate templates/producers or explicit per-message send APIs.

## 10. MessageConverter vs. MessagePostProcessor

`MessageConverter` defines **how the body is transformed** into a JMS Message. `MessagePostProcessor` adjusts fields on the JMS Message **after conversion**.

| Task | Appropriate API |
| --- | --- |
| `String` → `TextMessage`; `byte[]` → `BytesMessage`; `Map` → `MapMessage`. | `MessageConverter` |
| POJO → JSON text, controlling serializer/schema. | Custom `MessageConverter` and JSON library. |
| Set `JMSCorrelationID`, `JMSType`. | `MessagePostProcessor`. |
| Set `eventId`, `schemaVersion`, `tenantId`. | `MessagePostProcessor`. |
| Set target destination. | `convertAndSend(destinationName,...)` or resolver. |
| Set priority/TTL/delivery mode. | QoS on `JmsTemplate` or JMS producer. |
| Manage transactions/commits. | `Session`, transaction manager, container. |

The default `SimpleMessageConverter` supports `String`, `byte[]`, and `Map`. It **does not mean every arbitrary Java POJO automatically becomes a JSON `TextMessage`**.

Example `Map` body with properties:

~~~java
java.util.Map<String, Object> body = java.util.Map.of(
        "orderId", "O-105",
        "total", 420000);

template.convertAndSend("orders.events", body, msg -> {
    msg.setStringProperty("eventType", "OrderCreated");
    msg.setJMSCorrelationID("corr-O-105");
    return msg;
});
~~~

This is a fragment; `body` becomes a `MapMessage` under the corresponding converter, **not** automatically a JSON string. The custom property `eventType` is not a `MapMessage` field. If you need POJO JSON, configure the converter and test both conversion and metadata.

## 11. Metadata and Message Selectors in Spring JMS

One benefit of custom properties is that the broker can filter messages without parsing the body. Producer:

~~~java
template.convertAndSend("orders.events", "ORDER-105 created", msg -> {
    msg.setStringProperty("eventType", "OrderCreated");
    msg.setIntProperty("schemaVersion", 2);
    return msg;
});

template.convertAndSend("orders.events", "ORDER-105 cancelled", msg -> {
    msg.setStringProperty("eventType", "OrderCancelled");
    msg.setIntProperty("schemaVersion", 2);
    return msg;
});
~~~

Consumer selects only the type it needs:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'OrderCreated' AND schemaVersion >= 2")
    public void onCreated(String body) {
        System.out.println("Created: " + body);
    }
}
~~~

This is a **Spring-managed class** requiring running listener infrastructure, a broker, and an existing Queue. On a Queue, `OrderCancelled` messages with no matching consumer can accumulate; on a Topic, subscription semantics differ. **Selectors only filter messages; they do not replace authentication/authorization.**

### 11.1. Reading Metadata via @Header

Spring listeners can receive custom JMS properties as headers when the listener adapter supports the corresponding mapping:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class VersionedOrderListener {

    @JmsListener(destination = "orders.events")
    public void handle(
            String body,
            @Header("eventType") String eventType,
            @Header("schemaVersion") int schemaVersion) {

        System.out.println(
                eventType + " v" + schemaVersion + ": " + body);
    }
}
~~~

This example assumes delivered messages contain both properties with matching types. For optional properties, handle missing cases—for example using nullable types with `@Header(required=false)` or accepting raw `jakarta.jms.Message` and checking `propertyExists`. When using custom converters/adapters, verify how JMS properties map to messaging headers.

## 12. Designing Stable Metadata for Production

A minimal contract for the `OrderCreated` event:

| Name | Type | Purpose |
| --- | --- | --- |
| `eventId` | String property | Idempotency and matching republishes of the same event. |
| `JMSCorrelationID` | JMS header | Links request–reply or logical transactions. |
| `JMSType` | JMS header | System-wide `order.created` designation. |
| `eventType` | String property | Selector filtering and classification. |
| `schemaVersion` | int property | Branches body parsing by version. |
| `sourceService` | String property | Records the emitting service. |
| `tenantId` | String property | Tenant identifier; must be verified by consumer. |
| `traceId` | String property | Log correlation; when using standard tracing, prefer library context propagation. |

Example publisher keeping metadata fixed per invocation:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsTemplate template;

    public OrderEventPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(
            String eventId,
            String correlationId,
            String jsonBody) {

        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId required");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("correlationId required");
        }

        template.convertAndSend("orders.events", jsonBody, msg -> {
            msg.setJMSCorrelationID(correlationId);
            msg.setJMSType("order.created");
            msg.setStringProperty("eventId", eventId);
            msg.setStringProperty("eventType", "OrderCreated");
            msg.setIntProperty("schemaVersion", 2);
            msg.setStringProperty("sourceService", "order-service");
            return msg;
        });
    }
}
~~~

This is a Spring class to place inside a project package with configured JMS connectivity. `eventId` is generated by the business layer **before sending**, so it stays stable if the producer retries the same event. Never generate a fresh event ID inside the lambda on every send attempt when the goal is idempotency.

**Do not blindly trust producer-supplied metadata:** roles/tenant IDs must be tied to an authenticated identity and validated; JMS properties can enter logs, DLQs, or admin tools, so avoid secrets. If using OpenTelemetry/Micrometer, use the library's native context propagation rather than treating a standalone `traceId` property as full distributed tracing.

## 13. Errors, Retries, and Transaction Boundaries

`postProcessMessage` can throw `JMSException` when calling JMS setters. An `IllegalArgumentException` while validating `eventId` can also abort sending.

~~~java
// Fragment inside a Spring service:
try {
    template.convertAndSend("orders.events", payload, msg -> {
        msg.setStringProperty("eventType", "OrderCreated");
        return msg;
    });
} catch (org.springframework.jms.JmsException ex) {
    // Log structured details without exposing sensitive payloads.
    // Determine retry according to business policy.
    throw ex;
}
~~~

`template` and `payload` must be supplied by the service; this snippet is not a standalone program.

Key takeaways:

- If the callback throws an error, the send normally does not succeed.
- If the callback completes but the broker rejects the send or a transaction rolls back, the message may not be published.
- If the DB committed yet the JMS send did not complete (or vice versa), metadata **does not coordinate** the two transactions automatically. Consider transactional outbox if consistency is required.
- If the consumer processes successfully yet JMS ack/commit fails, the message may be redelivered; `eventId` supports idempotent handling.
- Never `catch` mandatory failures inside the callback and `return message` as if everything succeeded; that can send a message missing critical metadata into the broker.

`MessagePostProcessor` is **not** a retry, DLQ, backoff, or consumer-completion mechanism. Its sole responsibility is adjusting the JMS Message before sending.

## 14. Testing and Diagnostics

### 14.1. Unit Testing

For `OrderMetadataProcessor`, you can mock `jakarta.jms.Message` with Mockito and verify:

1. `setJMSCorrelationID` is called with the expected value.
2. `setIntProperty("schemaVersion", 2)` is called with the right type.
3. `postProcessMessage` returns **the exact input Message**, non-null.
4. The constructor accepts per-send metadata without mutable global state.
5. Setter/validation errors propagate to the caller.

Mocks only test the callback; they do **not** prove the broker stores or reads headers properly. Use integration tests with Artemis for that.

### 14.2. Integration Testing

Following the Section 7 demo:

1. Create a dedicated test queue and send a message with `JMSCorrelationID`, `JMSType`, and properties.
2. Receive the **raw** `Message` via `JmsTemplate.receive` with a finite timeout.
3. Assert getters return the expected values and property types.
4. Send another message and verify metadata does not "stick" from the previous send.
5. If selectors are used, assert matching messages arrive and understand the behavior of non-matching messages.
6. For `JMSMessageID`/`JMSTimestamp`, verify provider-valid values rather than **hardcoding**.
7. For QoS, test template/producer configuration and broker behavior rather than merely mocking `setJMSPriority`.
8. Clean up queues and isolate the test environment; other consumers must not compete for test messages and cause flakiness.

### 14.3. Common Errors Table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Lambda fails to compile | Wrong `MessagePostProcessor` imported or `javax.jms`/`jakarta.jms` mixed | Use `org.springframework.jms.core.MessagePostProcessor` and `jakarta.jms.*`. |
| Callback never runs | Called `convertAndSend` overload without processor or used `send(MessageCreator)` | Call the overload accepting a processor. |
| `JMSMessageID` missing inside callback | Message has not been sent yet | Read after send via appropriate API or on consumer. |
| Custom property missing | Read wrong message, wrong casing, different converter/adapter, broker rejected send | Receive raw JMS Message and inspect getters/queue. |
| Selector misses message | `schemaVersion` sent as String while comparing numerically; malformed expression | Use `setIntProperty` and exact property name. |
| Priority/TTL has no effect | Set headers inside callback instead of QoS config | Use `setExplicitQosEnabled(true)`, `setPriority`, `setTimeToLive`. |
| Callback returns `null` | Violates `postProcessMessage` contract | Return a valid message. |
| POJO fails to convert | `SimpleMessageConverter` cannot convert domain objects | Configure a custom `MessageConverter`. |
| Multiple requests share wrong correlation ID | Singleton processor holds mutable per-request field | Use an immutable lambda/processor per send. |
| Metadata contains sensitive data | Put tokens, session keys, or PII into properties | Minimize data; control logs/ACLs/DLQs and masking. |
| Post-processor logs "OK" yet consumer receives nothing | Send failed, uncommitted, wrong destination, selector mismatch, TTL expired | Inspect broker metrics, transactions, and exception chain. |

### 14.4. Negative Tests to Write

- Force the callback to throw `JMSException` and verify no valid message is sent.
- Send `schemaVersion` with the wrong type and observe the numeric selector failing to match as expected.
- Pass an empty `eventId` and confirm the service fails fast before sending.
- Perform two sends with different correlation IDs and verify each message keeps its own ID.
- Omit a required metadata field: verify the consumer reports it clearly or routes to error handling instead of assuming metadata is always present.

## 15. Practice Questions

1. **Does MessagePostProcessor run before or after MessageConverter?** After conversion, before producer send.
2. **Does it operate on `jakarta.jms.Message` or `org.springframework.messaging.Message`?** With `JmsTemplate`, it is `jakarta.jms.Message` from `org.springframework.jms.core.MessagePostProcessor`.
3. **What must you do to add `eventType` for use in selectors?** Call `setStringProperty("eventType", "...")` before sending.
4. **Should you set `JMSMessageID` to a client UUID inside the callback?** No; that ID is assigned by the provider. Use a separate `eventId`.
5. **Why doesn't `setJMSPriority(9)` replace `setPriority(9)` on the producer/template?** The provider determines priority on send based on QoS settings.
6. **Must `JMSCorrelationID` and `eventId` always be identical?** No. Correlation links a flow; `eventId` identifies an event for deduplication.
7. **Why avoid setting `schemaVersion="2"` as a String when the selector compares numbers?** JMS selectors distinguish types; use a numeric property.
8. **If you want to set a reply queue by name, does the post-processor have direct access to `Session`?** No; pass an existing `Destination` or use `MessageCreator`, which receives `Session`.
9. **Is returning `null` from `postProcessMessage` valid?** No.
10. **Does callback completion confirm that the DB and consumer have committed?** No; the callback only prepares metadata prior to sending.

## 16. Official Documentation

- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html): `MessageConverter`, `MessagePostProcessor` examples, and setting headers/properties.
- [Spring Framework 6.2 — MessagePostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html): signature, `JMSException`, non-null return contract.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `convertAndSend` overloads, QoS, `receive`, transactions.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message headers/properties, selector identifiers, `JMSXGroupID`, and `JMSXDeliveryCount`.
- [Jakarta Messaging 3.1 Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): getters/setters and property types.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): embedded broker and auto-configuration.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.template.receive-timeout`, QoS, and Artemis.

**Summary:** `MessagePostProcessor` is the step that **modifies a JMS Message after conversion but before sending**. Use it to attach `JMSCorrelationID`, `JMSType`, and consistent **typed properties**; never use it to spoof provider headers or substitute for QoS/transactions. A solid metadata contract enables event filtering, tracing, and idempotency, while security, retries, and consumer-side validation remain essential.
