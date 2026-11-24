# MessagePostProcessor for Data Before Sending

> **Topic:** `JmsTemplate` in Spring Framework JMS. `MessagePostProcessor` is an interception point **after `MessageConverter` converts Java data into a JMS `Message`, but before `MessageProducer` sends the message to the broker**. This mechanism is especially useful for adding correlation IDs, event types, schema versions, and per-send JMS properties.

## 1. Lesson objectives

After this lesson, you can:

1. Accurately describe the `convertAndSend → MessageConverter → MessagePostProcessor → send` sequence and when a JMS message can be modified.
2. Use the `JmsTemplate.convertAndSend(destination, payload, postProcessor)` overload to add headers/properties while keeping the converter-created payload intact.
3. Distinguish **JMS headers**, **message properties**, and **body**, especially headers managed by the JMS provider at send time.
4. Write a runnable Java 17 / Spring Boot 3.3 / ActiveMQ Artemis program that sends a `TextMessage`, receives that exact message via selector, and inspects headers and properties.
5. Design a reusable post-processor without losing per-request data, creating duplicate side effects on retry, or accidentally mutating QoS settings of a shared template.
6. Diagnose when a callback does not run, the body has the wrong type, headers are overwritten by the provider, or the message is not selected by a consumer.

This is a **mechanism for modifying a message right before send**. It is not a consumer, a filter running after broker acceptance, or a component processing a message after it has been successfully sent.

## 2. Where does MessagePostProcessor sit in the send flow?

With Spring Framework 6.x, `JmsTemplate` can send data in two common ways:

- `send(destination, MessageCreator)`: application code manually creates a `jakarta.jms.Message` using `Session`.
- `convertAndSend(destination, object)`: a `MessageConverter` converts a Java object into a JMS `Message`; the template sends it.

To **intervene after conversion**, use the overload taking an additional `org.springframework.jms.core.MessagePostProcessor`.

~~~text
Application calls:
    jmsTemplate.convertAndSend("orders.events", payload, processor)
                           |
                           v
            MessageConverter.toMessage(...)
                           |
                           v
              jakarta.jms.Message
                           |
                           v
       MessagePostProcessor.postProcessMessage(...)
       - setJMSCorrelationID(...)
       - setStringProperty(...)
       - setIntProperty(...)
       - returns Message (must not be null)
                           |
                           v
           JMS MessageProducer.send(...)
                           |
                           v
                      JMS broker
                           |
                           v
                     JMS consumer
~~~

**Key ordering:** the callback receives the **JMS message already created by the converter**. Here you can add request-dependent metadata, without having to manually create the `TextMessage`/`BytesMessage` body if the converter already handled it properly.

Suppose an application sends the string `"order-created"`. By default, Spring's `SimpleMessageConverter` converts `String` to a JMS `TextMessage`. `MessagePostProcessor` can attach:

~~~text
Body: TextMessage("order-created")
Header: JMSCorrelationID = "trace-abc-001"
Properties:
    eventType     = "order.created" (String)
    schemaVersion = 1               (int)
    sourceService = "order-service" (String)
~~~

The body remains unchanged. Consumers can read the metadata for routing, correlated logging, or schema version validation before processing.

## 3. Core API: a functional interface

In Spring Framework 6.x:

~~~java
package org.springframework.jms.core;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

@FunctionalInterface
public interface MessagePostProcessor {
    Message postProcessMessage(Message message) throws JMSException;
}
~~~

This is an API signature shown for learning, **not a file to create in your project** (the actual interface already comes with the Spring JMS dependency).

- **Input:** a `jakarta.jms.Message`, typically just created by `MessageConverter`.
- **Output:** the modified message itself, or a valid replacement message; **must not return `null`**.
- **Exceptions:** the method permits `JMSException` when JMS API operations fail. `JmsTemplate` translates eligible JMS checked exceptions into runtime Spring `JmsException`.
- **Implementation:** use a lambda or a class implementing the interface since it has a single abstract method.

Concise usage:

~~~java
// Snippet: jmsTemplate is a configured Spring bean.
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSCorrelationID("trace-abc-001");
    message.setStringProperty("eventType", "order.created");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

You do not need to instantiate `MessagePostProcessor` upfront if the logic is single-use. For shared logic, you can create a parameterized processor object or a helper method returning a lambda.

Note: the example above uses **`org.springframework.jms.core.MessagePostProcessor`**, which operates on `jakarta.jms.Message`. Spring also has **`org.springframework.messaging.core.MessagePostProcessor`**, which operates on `org.springframework.messaging.Message<?>` in other messaging APIs. The two interfaces are in different packages and take different message types; do not pick the wrong import when compiling.

## 4. Headers, properties, and body: which layer sets what?

| Element | Example | Proper way to set | Key point to remember |
| --- | --- | --- | --- |
| Body (payload) | JSON/string `"order-created"` | `MessageConverter` | The converter owns data representation, encoding, and content type |
| Application-settable JMS headers | `JMSCorrelationID`, `JMSType`, `JMSReplyTo` | `MessagePostProcessor` once a valid `Message` exists | Use the proper setter/getter APIs on `jakarta.jms.Message` |
| Custom application properties | `eventType`, `schemaVersion`, `sourceService`, `runId` | `setStringProperty`/`setIntProperty`/... in processor | Property type matters when consumers read or use selectors |
| Provider-managed headers | `JMSMessageID`, `JMSTimestamp`, `JMSDestination` | Set by the JMS provider during send | Do not set/overwrite them expecting them to stick |
| Send-time QoS | delivery mode, priority, time-to-live | `MessageProducer` or `JmsTemplate` config with explicit QoS | Do not set via modifying headers owned or overwritten by the provider |

Example distinguishing headers from properties:

~~~java
message.setJMSCorrelationID("req-001");             // JMS header
message.setStringProperty("eventType", "created");   // Custom String property
message.setIntProperty("schemaVersion", 2);         // Custom int property
~~~

Corresponding consumer reads:

~~~java
String correlationId = message.getJMSCorrelationID();
String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
~~~

**Do not** use `setStringProperty("JMSCorrelationID", "...")` instead of `setJMSCorrelationID(...)`; the former only creates a property named like the header and is not guaranteed to populate the actual JMS header field.

### 4.1. Correlation ID and trace ID

`JMSCorrelationID` is commonly used by applications to link request–reply pairs or steps within the same business flow. The value is typically chosen by the emitting service, such as a command ID or a correlation ID generated at API ingress.

When using distributed tracing (OpenTelemetry), do not assume `JMSCorrelationID` is identical to `traceparent`; each system may follow a different convention. You can keep correlation ID as the header while placing `traceparent`/`tracestate` in separate properties per your instrumentation standard. **Do not arbitrarily generate a new ID on every retry** if you need to identify the same logical operation.

### 4.2. Properties and selectors

JMS supports primitive and String properties: `setStringProperty`, `setIntProperty`, `setBooleanProperty`, etc. When sending properties:

~~~java
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
~~~

A consumer can construct a matching JMS selector:

~~~text
eventType = 'order.created' AND schemaVersion = 1
~~~

Selectors only inspect **headers/properties**, not JSON body contents. Property names must follow JMS selector identifier rules; avoid reserved namespaces defined by the spec/broker. Metadata strings supplied by clients must be validated; never concatenate untrusted input into a selector.

### 4.3. Can you replace the body inside a processor?

A JMS `TextMessage` is mutable during construction; at the API level, you can cast to the right type and call `setText(...)` before sending. However, if your goal is serializing DTOs to JSON, renaming fields, enforcing encoding, or managing schemas, put that in a **`MessageConverter`/serializer**, where responsibilities are clean and easy to unit-test. Processors fit metadata that arises **after the payload has been converted**. Do not cast every `Message` to `TextMessage`, because a converter may create a `BytesMessage`, `MapMessage`, or `ObjectMessage`.

## 5. Overloads that use MessagePostProcessor

Typical `JmsTemplate` calls:

~~~java
// Snippet: jmsTemplate is injected; processor is a MessagePostProcessor.
jmsTemplate.convertAndSend("orders.events", payload, processor);

// With defaultDestination configured:
jmsTemplate.convertAndSend(payload, processor);

// With a jakarta.jms.Destination provided:
jmsTemplate.convertAndSend(destination, payload, processor);
~~~

`convertAndSend` converts the object to a JMS `Message`, invokes the post-processor, and then sends. Calling `jmsTemplate.send(destination, session -> ...)` is the **`MessageCreator`** API: the lambda there receives a `Session` to create the message, so do not confuse it with the `MessagePostProcessor` callback that receives an already-converted `Message`.

| Scenario | API to use | Why |
| --- | --- | --- |
| Send a `String`/`byte[]`/`Map` with current converter | `convertAndSend` | No need to build the JMS message manually |
| Add per-request correlation ID/properties | `convertAndSend(..., MessagePostProcessor)` | Intervenes right after conversion and before send |
| Manually create `BytesMessage` or special message from `Session` | `send(..., MessageCreator)` | Full access to `Session` to construct the message |
| Convert DTO to JSON/Text/Bytes per schema | `MessageConverter` | Separates serialization from metadata |
| Adjust delivery mode/priority/TTL template-wide | `JmsTemplate` + `explicitQosEnabled` | QoS applied by producer/provider on send |
| Transform results on the consumer | Receiving listener/converter | Producer's post-processor is not invoked on receive |

Do not expect a `convertAndSend` callback to run automatically for every send path through the template. **It applies only to calls invoking an overload that accepts the processor**, not as a global interceptor attached automatically to every `send`.

## 6. Complete example: Spring Boot 3.3 + ActiveMQ Artemis + Java 17

We will send a `TextMessage` using `JmsTemplate.convertAndSend`, set metadata in the lambda, and then use `JmsTemplate.receiveSelected` to **read the exact message sent by this run**. The experiment lets you observe the content before send and verify that the broker preserves metadata on receive.

### 6.1. Prepare the broker

You need an **ActiveMQ Artemis broker** running at `tcp://localhost:61616`, credentials `artemis/artemis` for an **isolated local demo environment**, and a queue `demo.postprocess`. Create an anycast/point-to-point queue beforehand; if your demo broker allows auto-creation you may rely on that, though real brokers require respecting destination-creation permissions.

For example, if you have Docker and want to test locally, the official image can be started as follows:

~~~bash
docker run --detach --rm --name artemis-postprocess-demo -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Check the logs before running Java:

~~~bash
docker logs artemis-postprocess-demo
~~~

If a broker is already running on the same port, do **not** start another container sharing that port. When finished, run `docker stop artemis-postprocess-demo` to clean up the test environment. The demo command does not configure persistent volumes; do not treat it as a production deployment setup.

### 6.2. Project structure

~~~text
jms-message-postprocessor/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/PostProcessorApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-message-postprocessor'
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
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
~~~

`spring.artemis.mode: native` ensures the project targets an out-of-process Artemis broker. The `artemis/artemis` credentials are defaults for the **local demo** environment only; in real environments, use managed secrets overridden via `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` or centralized configuration, and never commit real passwords.

### 6.3. Runnable Java: verifying payload and metadata

`src/main/java/demo/PostProcessorApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PostProcessorApplication {

    private static final String QUEUE = "demo.postprocess";
    private static final String PAYLOAD = "order-created";

    public static void main(String[] args) {
        SpringApplication.run(PostProcessorApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            // Distinguish the exact test message of this run.
            String runId = UUID.randomUUID().toString();

            // Demo runs single-threaded; set timeout to avoid waiting forever.
            template.setReceiveTimeout(5_000L);

            template.convertAndSend(QUEUE, PAYLOAD, message -> {
                // Converter already created the JMS Message before the lambda runs.
                if (!(message instanceof TextMessage)) {
                    throw new IllegalStateException(
                            "Expected TextMessage for String payload");
                }

                // JMS header to correlate steps of a single request.
                message.setJMSCorrelationID(runId);

                // Application properties for selectors/metadata processing.
                message.setStringProperty("runId", runId);
                message.setStringProperty("eventType", "order.created");
                message.setIntProperty("schemaVersion", 1);

                System.out.println("POSTPROCESSOR_OK");
                return message; // Must return a non-null Message.
            });

            // This line only prints after the send call returns normally.
            System.out.println("SEND_OK");

            String selector = "runId = '" + runId + "'";
            Message received = template.receiveSelected(QUEUE, selector);

            if (!(received instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "No matching TextMessage within 5000 ms");
            }
            if (!PAYLOAD.equals(text.getText())) {
                throw new IllegalStateException("Payload mismatch");
            }

            System.out.println("RECEIVE_OK body=" + text.getText());

            boolean metadataMatches =
                    runId.equals(text.getJMSCorrelationID())
                    && runId.equals(text.getStringProperty("runId"))
                    && "order.created".equals(
                            text.getStringProperty("eventType"))
                    && text.getIntProperty("schemaVersion") == 1;

            if (!metadataMatches) {
                throw new IllegalStateException("Metadata mismatch");
            }

            System.out.println("METADATA_OK");
        };
    }
}
~~~

**What each step means:**

1. Spring Boot configures `ConnectionFactory` and `JmsTemplate` from the Artemis starter. You do not need to create `Session` or `MessageProducer` manually.
2. `String PAYLOAD` is converted by the default `SimpleMessageConverter` into a `TextMessage`.
3. The `MessagePostProcessor` lambda receives this message, checks its type, sets the correlation ID, and sets three application properties. In this example, the converted data is the body; the callback only adds metadata.
4. `POSTPROCESSOR_OK` is printed **inside the callback**, so it appears **before** `SEND_OK`. This proves the callback ran, **not that the broker already received the message** when the first line appeared.
5. After `convertAndSend` returns without error, the program prints `SEND_OK`. Business-wise, you must still separate “producer sent” from “consumer processed”.
6. `receiveSelected` creates a consumer with a selector accepting only this run's `runId`. `setReceiveTimeout(5000)` bounds the receive wait time.
7. `RECEIVE_OK` is only printed when the body matches. `METADATA_OK` is only printed after verifying correlation ID, `eventType`, `schemaVersion`, and `runId`.
8. `ApplicationRunner` runs the experiment once and exits; the demo app does not start an HTTP server. This is a synchronous verification example, not a long-lived production listener model.

The filename `PostProcessorApplication.java` matches the public class; the source uses Java 17 pattern matching for `instanceof`. Because the code depends on Spring/JMS, run it via Gradle (with the proper classpath), not standalone `javac PostProcessorApplication.java`.

### 6.4. Running and checking stdout

In the project directory containing the files above, with JDK 17+ and Gradle installed:

~~~bash
gradle bootRun
~~~

When the broker, queue, and credentials work properly, the **lines printed by the application itself** are:

~~~text
POSTPROCESSOR_OK
SEND_OK
RECEIVE_OK body=order-created
METADATA_OK
~~~

Spring and Artemis startup/shutdown logs may appear interleaved. `runId` is a random UUID and is **not printed** in the sample output. Selecting by `runId` ensures the newly sent message is received even if the queue holds older messages from prior runs.

If the broker is unreachable, the queue does not exist with auto-create disabled, send/receive permissions are insufficient, or the wait times out, the program throws an exception; the sample output above applies only when test preconditions are met. If `POSTPROCESSOR_OK` appears but `SEND_OK` does not, the failure likely occurred in the producer/broker step **after the callback**.

To avoid consuming messages belonging to other applications, run only against a **dedicated demo queue**. In production, do not use `JmsTemplate.receiveSelected` on a business queue just to “inspect metadata”; it can alter message delivery and acknowledgement outcomes.

## 7. Real-world application pattern: per-request metadata

In an order-publishing application, the correlation ID and tenant/context typically differ per request. Creating a dedicated processor per call preserves thread safety:

~~~java
// Snippet in a Spring service; JmsTemplate is already injected.
public void publishOrderEvent(
        String orderId,
        String correlationId,
        String sourceService) {

    String payload = "order-created:" + orderId;

    jmsTemplate.convertAndSend(
            "orders.events",
            payload,
            message -> {
                message.setJMSCorrelationID(correlationId);
                message.setStringProperty("eventType", "order.created");
                message.setStringProperty("sourceService", sourceService);
                message.setIntProperty("schemaVersion", 1);
                return message;
            });
}
~~~

This is a **snippet**, not a standalone runnable class. A real service must validate `orderId`, `correlationId`, and `sourceService` before publishing. Property names and meanings form a **contract between producer and consumer**; changing them arbitrarily can prevent listeners/selectors from reading them.

### 7.1. Extracting shared post-processing logic

If multiple sends apply the same logic, create a factory returning a processor:

~~~java
// Java 17 snippet; import org.springframework.jms.core.MessagePostProcessor.
static MessagePostProcessor eventMetadata(
        String correlationId, String eventType, int version) {

    return message -> {
        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("eventType", eventType);
        message.setIntProperty("schemaVersion", version);
        return message;
    };
}

// Usage call:
jmsTemplate.convertAndSend(
        "orders.events",
        "order-created",
        eventMetadata("request-001", "order.created", 1));
~~~

Capture **immutable** local variables/parameters so the processor stays stable for a given send. `JmsTemplate` is usually a singleton used across many requests; never put “current correlationId” into a mutable singleton field and mutate it across threads.

### 7.2. When multiple metadata operations are needed

You can combine multiple rules inside **a single callback** rather than sending two messages:

~~~java
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSCorrelationID("request-001");
    message.setStringProperty("eventType", "order.created");
    message.setStringProperty("sourceService", "order-api");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

Two calls to `convertAndSend` are **two separate sends**, not two metadata-enrichment stages on one message. If you want to split into small helper functions, invoke them sequentially on the same `Message` inside the lambda and return only once.

## 8. Headers you should not set with a post-processor

A common point of confusion: since the callback receives a JMS `Message`, it looks like you can call any setter on it. However, **final control over several headers belongs to the JMS producer/provider**.

| Header or option | Can it be read/set in processor? | Reliable way to configure |
| --- | --- | --- |
| `JMSCorrelationID` | Can be set in processor | `message.setJMSCorrelationID(id)` |
| `JMSType` | Can be set if app uses this field | `message.setJMSType(type)` |
| Custom property `eventType` | Can be set | `message.setStringProperty("eventType", type)` |
| `JMSReplyTo` | Can be set when a valid destination exists | `message.setJMSReplyTo(replyDestination)` |
| `JMSMessageID` | Assigned by provider on send | Read message after send / at consumer; do not assign manually to replace ID |
| `JMSTimestamp` | Set by provider per send configuration | Do not set manually to fake send time |
| `JMSDestination` | Set by producer/provider | Pass destination to `convertAndSend` |
| `JMSDeliveryMode` | Decided by producer/provider at send | Set delivery mode on producer/template |
| `JMSPriority` | Decided by producer/provider at send | Configure priority on producer/template |
| `JMSExpiration` | Computed by provider from TTL | Set time-to-live instead of writing a timestamp manually |

**Example to avoid:**

~~~java
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSPriority(9); // Not a reliable way to set QoS.
    message.setJMSExpiration(System.currentTimeMillis() + 30_000L);
    return message;
});
~~~

These values may be overwritten by the provider on send. If all messages sent through a template need a specific TTL/priority/mode, configure the template when creating the bean:

~~~java
// Spring @Configuration snippet; do not copy into demo without adjusting beans.
@Bean
JmsTemplate shortLivedTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setExplicitQosEnabled(true);
    template.setPriority(7);
    template.setTimeToLive(30_000L);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    return template;
}
~~~

This snippet requires imports for `jakarta.jms.ConnectionFactory`, `jakarta.jms.DeliveryMode`, `org.springframework.jms.core.JmsTemplate`, and `org.springframework.context.annotation.Bean`. The QoS setters on the template are only actively applied on send when **`setExplicitQosEnabled(true)`** is enabled. Configure this **once at bean creation**; never call `template.setPriority(9)` before each request on a shared singleton because threads can overwrite each other's settings.

If individual messages require different QoS, consider separate templates per policy group, or use JMS API-level producer operations/`JmsTemplate.execute` with explicit send parameters. Keep `MessagePostProcessor` for metadata, and distinguish TTL from business deadlines inside the body.

## 9. Role of converter, processor, and consumer in a real system

~~~text
Order Service
  |
  | orderId, business event
  v
MessageConverter                  -> serializes Java object into JMS message
  |
  v
MessagePostProcessor             -> adds correlationId, eventType, version
  |
  v
JmsTemplate / MessageProducer    -> selects destination, delivery mode, priority, TTL
  |
  v
JMS Broker                       -> accepts, stores, routes per configuration
  |
  v
@JmsListener / Consumer          -> receives, deserializes, validates metadata, processes
  |
  v
Database / External Service      -> separate side effects, with transactions/idempotency
~~~

### 9.1. What is MessageConverter?

Spring's `org.springframework.jms.support.converter.MessageConverter` converts between Java objects and JMS `Message`s. By default, `SimpleMessageConverter` supports `String ↔ TextMessage`, `byte[] ↔ BytesMessage`, and `Map ↔ MapMessage`. For JSON DTOs, you typically must configure a dedicated converter/serializer; **calling `convertAndSend` with an arbitrary DTO does not guarantee it becomes a JSON `TextMessage`**.

Example DTO:

~~~java
public record OrderCreated(String orderId, int amount) {}
~~~

This is only a data definition (place in `OrderCreated.java` if public), not a standalone runnable send example. If you want to publish this record as JSON, choose an appropriate `MessageConverter` and configure content/type mappings transparently. Afterward, `MessagePostProcessor` can still add metadata without needing to know internal serialization details.

### 9.2. How do consumers rely on metadata?

A listener can filter by the `eventType` property:

~~~java
// Snippet: runs in another Spring bean with JMS listener infrastructure.
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created'")
public void handleOrderCreated(String body) {
    System.out.println("Received: " + body);
}
~~~

Requires importing `org.springframework.jms.annotation.JmsListener`, configuring the application's JMS listener infrastructure, and applying proper idempotency rules. **Do not add this listener to the `receiveSelected` demo in section 6**, because another listener on the same queue can compete and consume the message before the synchronous test runs.

For complex metadata handling, you can receive raw `jakarta.jms.Message` via the corresponding API or use Spring Messaging headers after mapping. Inspect the converter and header mapper, as not all properties/data types map identically automatically.

## 10. Common issues and diagnosis

| Symptom | Possible cause | Troubleshooting step |
| --- | --- | --- |
| `MessagePostProcessor` does not run | Called `convertAndSend` overload without processor or used `send(MessageCreator)` | Check exact `convertAndSend(..., processor)` signature |
| Callback throws error before `SEND_OK` | Wrong JMS message type, invalid property setter, or converter error | Check converter, property names/types, and exception stack |
| `POSTPROCESSOR_OK` prints then send fails | Post-processing finished, but broker/network/permission send failed | Separate the two phases; inspect producer-send exception and broker logs |
| Consumer does not receive message | Wrong destination, selector mismatch, expired TTL, another consumer took it | Check queue depth, selector, TTL, correlation ID, competing consumers |
| Metadata at receiver differs from expected | Broker policy overwrote it or a different converter/mapper processed it | Inspect raw JMS headers/properties and both sides' configs |
| `ClassCastException` casting to `TextMessage` | Converter produced `BytesMessage`, `MapMessage`, or another provider message | Use `instanceof` and check which converter is active |
| `JMSPriority` does not match manually set value | Header set by provider/producer on send | Set QoS on template/producer and enable explicit QoS if needed |
| Listener cannot find `schemaVersion` | Property name/case mismatch or not post-processed | Align contract, check producer and raw received message |
| Erratic request latency | Callback calls database/network or generates heavy payloads | Keep callback lean, avoid blocking I/O |
| Same event generated multiple times | Send retries or unclear transactions; processor invoked again | Use stable `eventId`/idempotency key; design outbox when needed |
| Private data appears in broker/logs | Placed sensitive info into properties for debugging convenience | Limit metadata, control logs, retention, ACLs, encryption |

**Recommended debugging sequence:** verify which overload is called → verify callback invocation → inspect the created message → confirm send completed → read raw message at a test-queue consumer → compare selector and provider policies. Do not assume a selector mismatch is a `MessagePostProcessor` bug.

### 10.1. Exceptions and retries

If a `JMSException` occurs inside `postProcessMessage`, `convertAndSend` can fail **before the producer sends**. If a network error occurs after the callback, you still face the situation of **not knowing for sure whether the broker accepted the message**. Retrying can emit duplicate messages even when the metadata callback is completely valid.

Therefore:
- Producers should have a stable **`eventId`/`commandId`** per logical operation, especially across retries.
- Consumers must be idempotent if side effects must not execute repeatedly.
- When emitting messages alongside database commits, consider **transactional outbox**.
- Never perform non-rollbackable side effects (e.g., charging money, sending real emails) **inside the post-processor**; the callback can run and the send can still fail.

### 10.2. Thread-safety

`JmsTemplate` is typically used as a singleton across multiple threads. Capturing per-request immutable/local variables in the lambda is good practice:

~~~java
String correlationId = requestCorrelationId;
jmsTemplate.convertAndSend("orders.events", payload, message -> {
    message.setJMSCorrelationID(correlationId);
    return message;
});
~~~

This is an illustrative snippet; `requestCorrelationId` and `payload` must exist in application context. Never store `correlationId` in a mutable singleton field like “currentCorrelationId” and update it before each send; concurrent requests can mix metadata. Avoid mutating shared `JmsTemplate` configuration on the request path.

## 11. When should you NOT use MessagePostProcessor?

- Need to **serialize domain objects** to JSON/XML/Bytes: build a `MessageConverter`.
- Need to **create special messages** using `Session` or work directly with the JMS producer: use `MessageCreator`/`JmsTemplate.execute`.
- Need to **read and process messages**: use `@JmsListener`, a listener container, or a consumer.
- Need to **guarantee broker acceptance/consumer processing**: design transactions, acknowledgement, retries, and observability; a post-processor alone does not guarantee reliability.
- Need to **vary QoS per send**: use appropriate producer/send policies; do not manually mutate provider-managed headers.
- Need **slow I/O or database calls**: perform them in the business layer before sending or in a separate transactional flow, avoiding synchronous pre-send callbacks.

## 12. Adoption checklist and self-check questions

Checklist before introducing a `MessagePostProcessor` into an application:
- [ ] Selected the right Spring JMS interface `org.springframework.jms.core.MessagePostProcessor`.
- [ ] Used the right `convertAndSend` overload accepting the processor.
- [ ] Converter builds the expected JMS `Message` type before the callback; no blind casts.
- [ ] Processor returns a valid `jakarta.jms.Message`, never `null`.
- [ ] Sets only appropriate headers/properties; leaves body intact unless an explicit contract dictates otherwise.
- [ ] Does not set `JMSPriority`/`JMSExpiration` as a way to configure QoS.
- [ ] Correlation ID and `eventId` follow a stable strategy across retries.
- [ ] Property names/types match selectors and consumer contracts.
- [ ] No unnecessary secrets or PII are placed in messages/logs.
- [ ] Tested receiving the raw message on a dedicated queue with a dedicated selector/ID.
- [ ] Evaluated transactions/outbox/idempotency if the message relates to critical data.

**Self-check:**

1. Does `MessagePostProcessor` run before or after `MessageConverter`? Why is this beneficial for setting JMS properties?
2. What is the difference between `message.setJMSCorrelationID("x")` and `message.setStringProperty("JMSCorrelationID", "x")`?
3. Why does `message.setJMSPriority(9)` inside a processor not guarantee the message is sent with priority `9`?
4. If `POSTPROCESSOR_OK` appears but `SEND_OK` does not, can you conclude the broker received the message?
5. With a Java DTO and no JSON converter registered, can you assume `convertAndSend` sends a JSON `TextMessage`?
6. Why should a singleton `JmsTemplate` not have a mutable “currentCorrelationId” field shared across requests?
7. If a consumer needs to filter on `eventType = 'order.created'`, where must you set that metadata?
8. After the callback finishes, the message is sent repeatedly due to retries; where does responsibility for preventing duplicate side effects lie?

**Remember:** `MessageConverter` builds a **JMS message from a Java object**; `MessagePostProcessor` adds **headers/properties to that JMS message before sending**; `JmsTemplate` performs the **send**; and the broker/consumer govern acceptance, routing, and subsequent processing. Each component has its own contract—avoid mixing responsibilities so testing, maintenance, and operations stay clean.

## References

- Spring Framework 6.1 – `MessagePostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html
- Spring Framework – Sending a Message / JMS converters and post-processing: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.1 – `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Boot 3.3 – JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Jakarta Messaging 3.1 Specification, JMS Headers and Message Properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
