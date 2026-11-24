# JmsHeaders and JMS Metadata Mapping

> **Context:** Listener data in Spring Framework JMS. When `@JmsListener` receives a message, the handler method can obtain not only the **payload** but also **standard JMS headers** and **application properties**. `org.springframework.jms.support.JmsHeaders` defines unified header names at the `org.springframework.messaging.MessageHeaders` layer; `SimpleJmsHeaderMapper` helps convert metadata between `jakarta.jms.Message` and Spring Message. Understanding these two layers enables using correlation IDs, message IDs, priority, type, redelivery, and business properties properly without confusing them with a JSON body.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **JMS API header**, **JMS application property**, **Spring Messaging header**, and **payload**.
2. Use the constants `JmsHeaders.CORRELATION_ID`, `MESSAGE_ID`, `PRIORITY`, `TYPE`, `REDELIVERED`, `TIMESTAMP`, `DESTINATION`, `REPLY_TO`, `DELIVERY_MODE`, and `EXPIRATION` accurately without hard-coding wrong names.
3. Use `@Header` and `@Headers` in a `@JmsListener` to extract individual metadata entries or all mapped metadata.
4. Use `JmsMessageHeaderAccessor` or `org.springframework.messaging.Message<T>` to read metadata in a way less coupled to the JMS provider; compare with reading `jakarta.jms.Message` directly.
5. Understand **inbound** (JMS → Spring) and **outbound** (Spring → JMS) mapping directions, as well as read-only standard headers and QoS headers determined by the JMS producer/provider.
6. Build a runnable Java 17/Spring Boot 3.3.5/Artemis example that sends a String `TextMessage` with a correlation ID + properties and verifies the metadata in an annotated listener.
7. Distinguish Spring Framework's `JmsHeaders` from **Spring Integration**'s `DefaultJmsHeaderMapper`, avoiding imposing one component's defaults onto the other.
8. Test cases of missing metadata, wrong types, provider-overwritten headers, multiple consumers, redelivery, and the risks of putting secrets into message headers.

**Principle:** Metadata helps **classify, correlate, route, observe, and reply to messages**. Metadata does not automatically prove a message was processed exactly once, does not replace transactions/acknowledgment, and a similarly named header does not necessarily share the same meaning across abstractions.

## 2. Four Data Layers to Distinguish

The same `order.created` event can be represented as:

~~~text
                         jakarta.jms.TextMessage
                      +----------------------------+
                      | BODY:                      |
                      |   {"orderId":"O-42"}       |
                      |                            |
                      | JMS STANDARD HEADERS:      |
                      |   JMSMessageID              |
                      |   JMSCorrelationID          |
                      |   JMSPriority               |
                      |   JMSType                   |
                      |   JMSRedelivered            |
                      |   JMSTimestamp ...          |
                      |                            |
                      | JMS APPLICATION PROPERTIES: |
                      |   eventType                 |
                      |   schemaVersion             |
                      |   tenantCode                |
                      +----------------------------+
                                      |
                                      | Spring JMS listener adapter
                                      | + SimpleJmsHeaderMapper
                                      v
                  org.springframework.messaging.Message<String>
                      +------------------------------------+
                      | payload: JSON String               |
                      | headers["jms_messageId"]           |
                      | headers["jms_correlationId"]       |
                      | headers["jms_priority"]            |
                      | headers["jms_type"]                |
                      | headers["eventType"]               |
                      | headers["schemaVersion"]           |
                      | headers["tenantCode"]              |
                      +------------------------------------+
                                      |
                      +---------------+---------------+
                      |                               |
                @Header("eventType")             @Headers Map
                @Header(JmsHeaders.TYPE)         or MessageHeaders
~~~

| Concept | Belongs to | Typical reading method | Example |
| --- | --- | --- | --- |
| JMS standard header | `jakarta.jms.Message` | `getJMSCorrelationID()`, `getJMSMessageID()`, `getJMSPriority()` | `JMSCorrelationID` |
| JMS application property | `jakarta.jms.Message` | `getStringProperty("eventType")`, `getIntProperty("schemaVersion")` | `eventType` |
| Spring Messaging header | `org.springframework.messaging.MessageHeaders` | `get(JmsHeaders.CORRELATION_ID)`, `@Header(...)` | `jms_correlationId` |
| Payload/body | JMS `TextMessage`/`BytesMessage` or Spring `Message<T>` | `getText()` or `getPayload()` | JSON order body |
| Spring envelope ID/time | `MessageHeaders.ID`/`TIMESTAMP` | `headers.getId()` / `headers.getTimestamp()` | Spring Message ID/timestamp |

**Important:** Spring Messaging's `MessageHeaders.ID` is not equivalent to the broker's `JMSMessageID`. `MessageHeaders.TIMESTAMP` is not by default equal to `JMSTimestamp`. To read the JMS message ID/timestamp, use `JmsHeaders.MESSAGE_ID`/`JmsHeaders.TIMESTAMP`.

## 3. What Is `JmsHeaders`?

`org.springframework.jms.support.JmsHeaders` is an interface containing `static final String` constants for JMS metadata names inside **Spring Messaging headers**. This interface is **not** a JMS provider, does not hold a message's state, is not a class to `new`, and does not automatically add metadata if the producer did not set it.

### 3.1. Table of Important Constants

The string values below correspond to Spring Framework 6.x/7.x:

| Spring Constant | String value | Original JMS API | Meaning / type when read |
| --- | --- | --- | --- |
| `JmsHeaders.PREFIX` | `"jms_"` | No corresponding getter | Prefix distinguishing JMS API headers from custom properties |
| `CORRELATION_ID` | `"jms_correlationId"` | `getJMSCorrelationID()` | `String` — correlates messages/request–reply |
| `MESSAGE_ID` | `"jms_messageId"` | `getJMSMessageID()` | `String` — ID assigned by provider upon sending |
| `DESTINATION` | `"jms_destination"` | `getJMSDestination()` | `jakarta.jms.Destination` — actual destination |
| `REPLY_TO` | `"jms_replyTo"` | `getJMSReplyTo()` | `jakarta.jms.Destination` — destination expecting replies |
| `DELIVERY_MODE` | `"jms_deliveryMode"` | `getJMSDeliveryMode()` | `Integer` — `DeliveryMode.PERSISTENT` or `NON_PERSISTENT` |
| `EXPIRATION` | `"jms_expiration"` | `getJMSExpiration()` | `Long` — expiration epoch millis; `0` means no TTL expiration |
| `PRIORITY` | `"jms_priority"` | `getJMSPriority()` | `Integer` — 0..9 |
| `REDELIVERED` | `"jms_redelivered"` | `getJMSRedelivered()` | `Boolean` — redelivery flag |
| `TYPE` | `"jms_type"` | `getJMSType()` | `String` — classification label set by producer/application |
| `TIMESTAMP` | `"jms_timestamp"` | `getJMSTimestamp()` | `Long` — send timestamp established by JMS provider |

**Standard import:**

~~~java
import org.springframework.jms.support.JmsHeaders;
~~~

Use `@Header(JmsHeaders.CORRELATION_ID)` instead of repeating the literal `"jms_correlationId"` everywhere. Values from older JMS 1/2 code sometimes appear as a `JMSCorrelationID` header; in **Spring Messaging headers**, the key name is normally **`jms_correlationId`**. Those are two representations at different layers, not two independent correlation IDs.

### 3.2. Not Every JMS-Like Name Is in `JmsHeaders`

`JMSXDeliveryCount` is a JMS-defined property that is very useful during redelivery, yet there is no `JmsHeaders.DELIVERY_COUNT` constant in the table above. Read via:

~~~java
// Snippet when raw jakarta.jms.Message is already available:
int deliveryCount = raw.getIntProperty("JMSXDeliveryCount");
~~~

Per provider/JMS specifications, availability and semantics are conditional; you can check `raw.propertyExists("JMSXDeliveryCount")` before reading in multi-provider code. In addition, brokers may attach `JMS_*`/vendor-specific properties. **Do not arbitrarily use standard prefixes or provider-reserved names** as custom property names.

## 4. Mapping Mechanism: Native JMS → Spring Message

A Spring `@JmsListener` can receive:

~~~java
// Snippet: @Component containing this method, with JMS listener infrastructure enabled.
@JmsListener(destination = "orders.events")
public void onEvent(org.springframework.messaging.Message<String> event) {
    String body = event.getPayload();
    String correlationId = (String) event.getHeaders()
            .get(JmsHeaders.CORRELATION_ID);
}
~~~

At the adapter boundary, Spring JMS converts the native JMS message into a Spring Messaging message (payload + headers). `SimpleJmsHeaderMapper` is Spring Framework's basic mapper for translating JMS API headers and custom properties into `MessageHeaders`. Thus, the handler does not have to invoke every JMS getter directly to obtain mapped headers.

### 4.1. Inbound Direction

~~~text
jakarta.jms.Message                         Spring MessageHeaders
--------------------------------------------------------------------
getJMSCorrelationID()                -->    jms_correlationId
getJMSMessageID()                    -->    jms_messageId
getJMSPriority()                     -->    jms_priority
getJMSType()                         -->    jms_type
getJMSRedelivered()                  -->    jms_redelivered
getJMSDestination()                  -->    jms_destination
getJMSReplyTo()                      -->    jms_replyTo
getStringProperty("eventType")       -->    eventType
getIntProperty("schemaVersion")      -->    schemaVersion
...                                  -->    ...
~~~

A mapping may skip metadata when it has no value, cannot be type-converted, or is excluded by a custom mapper policy. Therefore, in business APIs with optional headers, use `@Header(name = "...", required = false)` with a wrapper/reference type or read the raw `Message` and check for null, instead of forcing every message to carry every header.

### 4.2. Outbound Direction

If an integration sends a Spring Messaging `Message<T>` out to JMS via an abstraction with header mapping, supported headers are translated to native JMS:
- `JmsHeaders.CORRELATION_ID` → `setJMSCorrelationID(...)`;
- `JmsHeaders.REPLY_TO` → `setJMSReplyTo(...)` with a valid `Destination`;
- `JmsHeaders.TYPE` → `setJMSType(...)`;
- valid application headers such as `eventType` and `schemaVersion` → JMS properties.

**However**, provider-managed headers are only reflected on read and should not be "copied back" from a Spring Message expecting them to remain unchanged. Fields such as `JMSMessageID`, `JMSDestination`, `JMSTimestamp`, `JMSExpiration`, `JMSPriority`, and `JMSDeliveryMode` follow JMS producer/provider rules.

### 4.3. Distinguishing Spring Framework from Spring Integration

In Spring Framework JMS:
- `org.springframework.jms.support.JmsHeaderMapper` — JMS ↔ Spring mapping interface.
- `org.springframework.jms.support.SimpleJmsHeaderMapper` — basic mapper implementation.
- `org.springframework.jms.support.JmsHeaders` — shared constant list.

In **Spring Integration JMS** (a separate module):
- `org.springframework.integration.jms.DefaultJmsHeaderMapper` — mapper class for Spring Integration gateways/adapters.
- This mapper has its own options such as `setMapInboundDeliveryMode(true)`, `setMapInboundExpiration(true)`, and priority mapping policies.

Do not impose Spring Integration's `DefaultJmsHeaderMapper` defaults onto every Spring Framework `@JmsListener`. To customize Spring Integration mapping, configure the appropriate **integration inbound/outbound endpoint**; a mapper bean does not automatically change the adapter of every ordinary listener.

Example Spring Integration configuration (snippet, only used with the Spring Integration JMS dependency):

~~~java
@Bean
DefaultJmsHeaderMapper integrationJmsHeaderMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setMapInboundDeliveryMode(true);
    mapper.setMapInboundExpiration(true);
    return mapper;
}
~~~

In Spring Integration code, import `org.springframework.integration.jms.DefaultJmsHeaderMapper`. This snippet is **not** the `SimpleJmsHeaderMapper` API and is **not** required configuration for the Spring Boot JMS example later.

## 5. Accessing Metadata with `@Header` and `@Headers`

In a listener, you can declare the payload and individual metadata parameters:

~~~java
// Snippet placed inside a Spring-managed @Component.
@JmsListener(destination = "orders.events")
public void process(
        @Payload String payload,
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(name = JmsHeaders.MESSAGE_ID, required = false)
                String messageId,
        @Header(name = "eventType", required = false)
                String eventType,
        @Headers Map<String, Object> headers) {

    System.out.println("correlation=" + correlationId);
    System.out.println("messageId=" + messageId);
    System.out.println("type=" + eventType);
}
~~~

Imports:
~~~java
import java.util.Map;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
~~~

**Meaning of annotations:**
- `@Payload`: retrieves the converted payload; may be String/DTO depending on converter.
- `@Header("eventType")`: retrieves a single metadata key mapped from JMS property `eventType`; does not read fields inside a JSON body.
- `@Header(JmsHeaders.CORRELATION_ID)`: retrieves standard `JMSCorrelationID` via the Spring key.
- `@Headers Map<String,Object>`: receives the metadata map containing standard JMS headers and custom properties added by the mapper.
- `required=false`: if the key does not exist, a reference type like `String` can receive null; avoids forcing every message to include tracing-only metadata.
- `MessageHeaders` can also be injected to access all headers via the Spring API; `JmsMessageHeaderAccessor` provides typed getters.

**Do not arbitrarily use `jakarta.jms.Message` as the type of `@Payload`.** Spring supports raw `jakarta.jms.Message` as a direct parameter, whereas `@Payload` represents converted data. Do not confuse the two `Message` types sharing a name in different packages.

### 5.1. Using `org.springframework.messaging.Message<T>`

~~~java
// Snippet: use the fully qualified Message name to avoid confusion with jakarta.jms.Message.
@JmsListener(destination = "orders.events")
public void process(org.springframework.messaging.Message<String> event) {
    String payload = event.getPayload();
    String cid = (String) event.getHeaders()
            .get(JmsHeaders.CORRELATION_ID);
    Integer priority = (Integer) event.getHeaders()
            .get(JmsHeaders.PRIORITY);
    // validate and run business logic.
}
~~~

Benefit: the handler can easily reuse logic around the Spring abstraction, with all headers in one object. Drawback: if native provider/JMS methods are needed (such as `getJMSXDeliveryCount` or raw `BytesMessage` handling), receive `jakarta.jms.Message` directly or design a dedicated adapter.

### 5.2. `JmsMessageHeaderAccessor`

~~~java
// Snippet: event has type org.springframework.messaging.Message<String>.
JmsMessageHeaderAccessor accessor =
        JmsMessageHeaderAccessor.wrap(event);

String cid = accessor.getCorrelationId();
String id = accessor.getMessageId();
Integer priority = accessor.getPriority();
Boolean redelivered = accessor.getRedelivered();
Long expiration = accessor.getExpiration();
~~~

Import `org.springframework.jms.support.JmsMessageHeaderAccessor`. Getters return wrappers/references and may return null depending on metadata/mapping; do not auto-unbox `Integer`/`Long` without checking. `wrap(event)` only provides typed reads over existing Spring headers; it **does not call the broker** to fetch missing headers.

### 5.3. Receiving Raw `jakarta.jms.Message`

~~~java
// Alternate snippet: raw JMS message directly in the listener.
@JmsListener(destination = "orders.events")
public void processRaw(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {

    String cid = message.getJMSCorrelationID();
    String id = message.getJMSMessageID();
    int priority = message.getJMSPriority();
    boolean redelivered = message.getJMSRedelivered();
    String eventType = message.getStringProperty("eventType");
    int schemaVersion = message.getIntProperty("schemaVersion");
}
~~~

When you need to verify whether a **header truly exists on the wire**, reading raw JMS lets you inspect directly, especially when a custom header mapper or converter is in place and metadata mapping is suspected. If using a DTO in the handler, raw `Message` is still a supported parameter alongside it; verify the appropriate handler method signature. **Do not run both listener snippets on the same production queue just to debug**, as each consumer competes to receive and ACK messages.

## 6. Headers Whose Meanings Are Easily Confused

### 6.1. `JMSCorrelationID` vs. `JMSMessageID`

**`JMSMessageID`:** assigned by the provider (typically upon send) to identify a JMS message. Some providers/configurations can disable message IDs when the producer calls `setDisableMessageID(true)`; thus this header is not guaranteed to exist in every setup. Do not use `JMSMessageID` as a business idempotency key if a producer can retry sending the same event, as each send may receive a new ID.

**`JMSCorrelationID`:** set by the producer/application to link messages within a logical request or request–reply flow. Its value can be a request ID, command ID, an ingress correlation ID, or a client/broker-coordinated ID. It is not automatically equal to `JMSMessageID`.

~~~java
// Snippet when sending a JMS Message before producer.send(...).
message.setJMSCorrelationID("request-2026-001");
~~~

Consumer:
~~~java
@Header(JmsHeaders.CORRELATION_ID) String correlationId
~~~

**Do not** replace this with `message.setStringProperty("JMSCorrelationID", "...")`; that only creates a property with a similar name to the standard header and does not guarantee `getJMSCorrelationID()` changes.

If using Spring Integration, the generic Spring Integration `correlationId` header differs from the `jms_correlationId` header. A generic `MessageHeaders.ID` UUID also differs from the JMS message ID. Three concepts may serve similar observability purposes, but must not be treated as identical.

### 6.2. `JMSType` and Application `eventType`

`JMSType` is a standard JMS header that can describe the message type at the application level. `JmsHeaders.TYPE` maps to it. Many systems also carry custom properties like `eventType` or `schemaVersion` for selectors, versioning, and cross-platform interoperability.

~~~java
message.setJMSType("order.created");
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
~~~

These are **two distinct fields** for event type (standard `JMSType` and a custom property). If both are used, establish a contract keeping them consistent; otherwise consumers can easily read stale metadata.

Important: a JSON converter may use a separate JMS property, such as `_type`, to carry a Java DTO alias. **`_type` is not `JMSType` by default** and is not synonymous with `JmsHeaders.TYPE`. Producer and consumer must agree on how DTOs are resolved.

### 6.3. `JMSReplyTo` Is Not an Arbitrary String Destination

`JMSReplyTo` on raw JMS is a `jakarta.jms.Destination`. If you set it on the JMS message:

~~~java
// Snippet: replyQueue is a valid jakarta.jms.Destination.
message.setJMSReplyTo(replyQueue);
~~~

the corresponding inbound mapping is `JmsHeaders.REPLY_TO` of type `Destination`. Do not assume `@Header(JmsHeaders.REPLY_TO) String queueName` will always resolve every provider-specific `Destination`; when working with raw JMS destinations, declare `Destination` or use `JmsMessageHeaderAccessor.getReplyTo()`.

In a request–reply model, handle:
- a suitable and unique correlation key to avoid mismatched replies;
- proper send/consume permissions on the reply destination;
- TTL and late replies after the caller times out;
- idempotency of the business operation if the client retries.

### 6.4. `JMSPriority`, `JMSDeliveryMode`, `JMSExpiration`

These headers relate to QoS and are typically **established by the provider during the send**:

| Header | Reading in listener | How to set when sending |
| --- | --- | --- |
| `JMSPriority` | `JmsHeaders.PRIORITY` or `getJMSPriority()` | `MessageProducer.send(..., priority, ...)`; or template QoS |
| `JMSDeliveryMode` | `JmsHeaders.DELIVERY_MODE` or `getJMSDeliveryMode()` | `DeliveryMode.PERSISTENT/NON_PERSISTENT` on producer |
| `JMSExpiration` | `JmsHeaders.EXPIRATION` or `getJMSExpiration()` | Set TTL; provider computes expiration |
| `JMSTimestamp` | `JmsHeaders.TIMESTAMP` or `getJMSTimestamp()` | Determined by provider at send; do not manually fake timestamp |
| `JMSMessageID` | `JmsHeaders.MESSAGE_ID` or `getJMSMessageID()` | Assigned by provider unless disabled |

**Do not** do:

~~~java
// Illustration of how NOT to set QoS.
message.setJMSPriority(9);
message.setJMSExpiration(System.currentTimeMillis() + 60_000L);
~~~

The provider may overwrite these upon send. With Spring `JmsTemplate`:
~~~java
// Snippet: configure the template at bean creation time, do not mutate a singleton per request.
template.setExplicitQosEnabled(true);
template.setPriority(7);
template.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
template.setTimeToLive(60_000L);
~~~

Set `explicitQosEnabled=true` so `JmsTemplate` actively applies configured QoS through the producer. Do not take a `JmsHeaders.PRIORITY` value in a Spring header map as proof that a subsequent producer `send` will retain that priority: it still depends on the API and QoS policy in use.

### 6.5. `JMSRedelivered` and `JMSXDeliveryCount`

When a consumer rolls back, recovers a session, or fails to ACK, the broker may redeliver the message:
- `JMSRedelivered` → Boolean indicating this is a redelivery within the JMS provider's scope.
- `JMSXDeliveryCount` → delivery count property per specification/provider; useful for tracking redeliveries.
- Do not use `JMSRedelivered=false` to assert that a business side effect never occurred.
- Do not use delivery count as an **idempotency key**. If a producer sends a duplicate event again, it can arrive as a new message with count = 1.

Use a stable application `eventId`/`commandId` in the body or property to prevent duplicate business processing.

## 7. Runnable Project: Verifying Metadata Mapping in `@JmsListener`

This lab sends a String via `JmsTemplate`, setting **JMSCorrelationID**, **JMSType**, and custom properties, then the listener receives and verifies the corresponding Spring headers. The example favors assertion checks so it will not print PASS if metadata is mapped incorrectly.

### 7.1. Prerequisites

- Java 17+, Gradle (or Gradle wrapper), Spring Boot 3.3.5, and an ActiveMQ Artemis broker.
- Broker running at `tcp://localhost:61616`; `artemis/artemis` credentials are for an isolated local Docker demo only.
- Anycast queue `demo.jms.metadata` with send/consume permissions; a test broker may allow auto-create, though pre-creating it is recommended in shared environments.
- No other listeners running on the same test queue, and never use a queue carrying real business messages.
- If the broker is unavailable or credentials are wrong, the demo may fail before checking headers; that is a connection/config error, not header mapping.

You can run Artemis via Docker in an isolated learning environment:

~~~bash
docker run --detach --rm --name artemis-metadata-test -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Wait for the broker to be ready via `docker logs artemis-metadata-test`. When finished, run `docker stop artemis-metadata-test`. Do not run this command if another broker on your machine already uses port 61616. Never use default passwords in production.

### 7.2. Project Structure

~~~text
jms-header-mapping/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── MetadataApplication.java
    │   └── MetadataListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-header-mapping'
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

These credentials are **only for a local Docker demo on a personal machine**. If using an organization's test broker, grant role-based permissions and supply secrets via environment variables/a secret manager, such as `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD`; never commit real passwords to Git. `mode: native` prevents accidentally falling back to an embedded broker when testing real connectivity.

### 7.3. Listener Receiving Both Payload and Headers

`src/main/java/demo/MetadataListener.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class MetadataListener {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Observed> observed =
            new AtomicReference<>();
    private volatile String expectedBody;

    public record Observed(
            String correlationId,
            String messageId,
            String messageType,
            String eventType,
            Integer schemaVersion,
            Map<String, Object> headers) {
    }

    public void expect(String runId) {
        expectedBody = "event:" + runId;
    }

    @JmsListener(destination = "demo.jms.metadata")
    public void handle(
            @Payload String body,
            @Header(name = JmsHeaders.CORRELATION_ID, required = false)
                    String correlationId,
            @Header(name = JmsHeaders.MESSAGE_ID, required = false)
                    String messageId,
            @Header(name = JmsHeaders.TYPE, required = false)
                    String messageType,
            @Header(name = "eventType", required = false)
                    String eventType,
            @Header(name = "schemaVersion", required = false)
                    Integer schemaVersion,
            @Headers Map<String, Object> headers) {

        String expected = expectedBody;
        if (expected == null || !expected.equals(body)) {
            return; // Only record the message belonging to this demo run.
        }

        observed.set(new Observed(
                correlationId,
                messageId,
                messageType,
                eventType,
                schemaVersion,
                new HashMap<>(headers)));
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public Observed observed() {
        return observed.get();
    }
}
~~~

**Details to note:**
- `@Header` and `@Headers` belong to `org.springframework.messaging.handler.annotation`, not annotations defined in `jakarta.jms`.
- `JmsHeaders.*` keys map standard JMS headers. `eventType` and `schemaVersion` are **custom JMS properties**, so they use the contract names directly.
- `required=false` avoids binding errors if a provider/config omits an optional header; expected headers are verified in the assertion block.
- `@Headers Map<String,Object>` holds current Spring Messaging metadata, not verbatim every provider implementation-specific field.
- `CountDownLatch` provides a synchronization point between the listener thread and `ApplicationRunner`, avoiding arbitrary sleeps hoping a message arrived.
- `AtomicReference` with `latch` allows reading a metadata snapshot after the callback; the callback does not retain a reference to a native JMS Message whose session the container may reuse/close.
- The code intentionally supports one run per instance; handling multiple concurrent requests requires a correlation table/registry keyed by runId, not a single shared latch for all messages.
- If the test queue contains stale messages, the listener could consume them before `expect` is called. Therefore, only use a clean dedicated queue or appropriate filter/isolated consumer for serious integration tests.

### 7.4. Application Sending the Message and Verifying

`src/main/java/demo/MetadataApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.JmsHeaders;

@SpringBootApplication
@EnableJms
public class MetadataApplication {

    private static final String QUEUE = "demo.jms.metadata";

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            MetadataListener listener) {

        return args -> {
            String runId = UUID.randomUUID().toString();
            listener.expect(runId);

            template.convertAndSend(
                    QUEUE, "event:" + runId, message -> {
                        message.setJMSCorrelationID(runId);
                        message.setJMSType("order.created");
                        message.setStringProperty(
                                "eventType", "order.created");
                        message.setIntProperty("schemaVersion", 1);
                        message.setStringProperty("runId", runId);
                        return message;
                    });

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive matching message");
            }

            MetadataListener.Observed data = listener.observed();
            if (data == null
                    || !runId.equals(data.correlationId())) {
                throw new IllegalStateException(
                        "JMSCorrelationID mapping mismatch");
            }
            if (data.messageId() == null
                    || data.messageId().isBlank()) {
                throw new IllegalStateException(
                        "JMSMessageID was not supplied");
            }
            if (!"order.created".equals(data.messageType())
                    || !"order.created".equals(data.eventType())
                    || !Integer.valueOf(1).equals(
                            data.schemaVersion())) {
                throw new IllegalStateException(
                        "Type or custom property mismatch");
            }

            Map<String, Object> headers = data.headers();
            if (!Objects.equals(
                    headers.get(JmsHeaders.CORRELATION_ID), runId)
                    || !Objects.equals(
                    headers.get(JmsHeaders.MESSAGE_ID),
                    data.messageId())
                    || !Objects.equals(headers.get("runId"), runId)) {
                throw new IllegalStateException(
                        "Mapped headers map mismatch");
            }

            Object priority = headers.get(JmsHeaders.PRIORITY);
            if (!(priority instanceof Integer level)
                    || level < 0 || level > 9) {
                throw new IllegalStateException(
                        "Missing/invalid JMS priority header");
            }

            System.out.println("CORRELATION_ID_MAPPED=true");
            System.out.println("MESSAGE_ID_PRESENT=true");
            System.out.println("JMS_TYPE_MAPPED=true");
            System.out.println("CUSTOM_PROPERTIES_MAPPED=true");
            System.out.println("PRIORITY_MAPPED=true");
            System.out.println("ALL_ASSERTIONS_PASSED");
        };
    }
}
~~~

**Why these assertions are meaningful:**

1. `JmsTemplate.convertAndSend` with a String body creates a `TextMessage` via the default `SimpleMessageConverter`.
2. `MessagePostProcessor` runs after payload conversion; `setJMSCorrelationID` and `setJMSType` set **standard JMS headers**, while `setStringProperty`/`setIntProperty` add **application properties**.
3. The listener does not use synchronous `receiveAndConvert`; the Spring container receives the message on a background consumer thread and binds parameters.
4. A fresh `UUID` is used per run; the callback only signals success when the body matches the expected ID, preventing false PASSes from leftover messages of another run.
5. `JMSMessageID` is assigned by the broker/provider upon sending. The demo assumes normal message ID mode; if the producer configures disabled message IDs, the corresponding assertion no longer applies.
6. `JmsHeaders.PRIORITY` is read from **inbound headers** to prove the mapper populates priority in Spring metadata; the code only checks range 0..9 without forcing a specific priority when QoS is not configured.
7. A custom property `runId` is checked in `@Headers Map` to demonstrate that the application can read properties alongside standard headers.
8. `CountDownLatch` ensures that when main prints `ALL_ASSERTIONS_PASSED`, the listener has observed the message and metadata. It does **not** prove that a database transaction or JMS ACK/commit has completed.
9. The example does not add a second `@JmsListener` on the same queue, avoiding competing consumers that make tests nondeterministic.
10. If the broker is not running, permissions are wrong, or the message fails to arrive, the program throws an exception/timeout and does not print PASS.

### 7.5. Running and Expected Output

Create the files accurately, ensure JDK/Gradle and the broker are ready, then:

~~~bash
gradle bootRun
~~~

When the test succeeds, the lines printed by the **application** are:

~~~text
CORRELATION_ID_MAPPED=true
MESSAGE_ID_PRESENT=true
JMS_TYPE_MAPPED=true
CUSTOM_PROPERTIES_MAPPED=true
PRIORITY_MAPPED=true
ALL_ASSERTIONS_PASSED
~~~

Spring Boot and Artemis may log additional lines. `runId` is a random UUID and is not printed; the verification output above is deterministic. If the program throws an error, do not treat earlier printed lines as an overall PASS.

**No JSON converter needed on the broker:** the demo only sends a String `TextMessage`. It specifically tests **header/metadata mapping** without mixing JSON DTO serialization errors into the conclusions.

This is an example of logic that compiles when dependencies are satisfied; actual execution depends on the broker, credentials, and test queue. Never run it against a production queue or let the demo consume real business messages.

## 8. Metadata Mapping When Forwarding Messages

A common mistake: a consumer receives a message from queue A and wants to forward it to queue B using Spring Messaging `Message<T>`. If you copy the entire inbound `MessageHeaders` to outbound, you can carry along metadata that should be read-only.

**Example:**

~~~text
Inbound:
  jms_messageId = "ID:provider-123"
  jms_timestamp = 1700000000000
  jms_priority = 4
  jms_correlationId = "request-42"
  eventType = "order.created"

Desired outbound:
  JMSMessageID = reassigned by provider
  JMSTimestamp = time provider resends
  JMSDestination = queue B
  JMSPriority = per outbound QoS
  JMSCorrelationID = can preserve request-42
  eventType = preserved if contract allows
~~~

**Approach:** classify metadata into:
- **Safe to propagate:** business eventId, correlation ID per contract, schemaVersion/eventType if semantics stay unchanged.
- **Must be reassigned by provider:** message ID, send timestamp, destination, TTL-based expiration, priority/delivery mode from the send operation.
- **Should not be blindly forwarded:** trace/baggage with secrets, internal tenant metadata, retry counters with local semantics, provider-specific headers.
- **Needs recomputing or tagging:** hop count, routing history, processing state, redelivery/attempt info. Do not copy `JMSRedelivered` expecting the broker to treat it as a redelivery on queue B.

**Tip:** when writing a bridge, construct a **new outbound message** with the payload and an allowlisted set of properties, configure producer QoS explicitly, and let the provider assign new IDs/headers. Verify with a broker integration test rather than copying raw objects as the source of truth.

## 9. Metadata and JMS Selectors

A JMS selector filters messages using **standard JMS headers and message properties**, not by parsing a JSON body. Therefore, producers must agree on **property names and types**:

~~~java
// Snippet: inside producer's MessagePostProcessor.
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
message.setBooleanProperty("urgent", true);
~~~

Consumer can use:

~~~java
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created' AND schemaVersion >= 1")
public void onOrder(String body) {
    // Listener only receives messages whose selector evaluates to TRUE.
}
~~~

A selector does not read an `eventType` field inside a JSON body if the producer failed to set the `eventType` JMS property. If the producer sets `schemaVersion` as a String `"1"`, a numeric comparison `schemaVersion >= 1` does not auto-parse it to a number — it may **fail to match**. If a property is missing, the expression evaluates under SQL NULL/UNKNOWN logic; only TRUE is delivered.

**JMS header names and Spring keys differ in selectors:**
- On the Spring Messaging side: `@Header(JmsHeaders.PRIORITY)`, whose key is `jms_priority`.
- In JMS selector syntax: use **`JMSPriority >= 7`**, **not** `jms_priority >= 7` (unless the producer explicitly created a custom property of that name and the provider permits it).
- In Spring `MessageHeaders`: `JmsHeaders.CORRELATION_ID` → `"jms_correlationId"`.
- In a JMS selector: `JMSCorrelationID = 'request-42'`.

**Do not** use Spring's internal header key names directly inside a JMS selector expecting the provider to understand Spring's Java mapping. Selectors execute at the JMS/broker layer, not through Spring's method parameter resolver.

### 9.1. Types and Case Sensitivity

| Producer sets | Spring receives | Matching selector |
| --- | --- | --- |
| `setStringProperty("eventType", "order.created")` | `@Header("eventType") String` | `eventType = 'order.created'` |
| `setIntProperty("schemaVersion", 2)` | `@Header("schemaVersion") Integer` | `schemaVersion >= 2` |
| `setBooleanProperty("urgent", true)` | `@Header("urgent") Boolean` | `urgent = TRUE` |
| `setJMSCorrelationID("req-42")` | `@Header(JmsHeaders.CORRELATION_ID) String` | `JMSCorrelationID = 'req-42'` |
| `setJMSType("order.created")` | `@Header(JmsHeaders.TYPE) String` | `JMSType = 'order.created'` |

Property names are case-sensitive (`eventType` differs from `EventType`); String literals are also case-sensitive. In selectors, check for missing values using `IS NULL`, not `= NULL`. If interpolating input into a selector, validate/escape it to avoid syntax errors and misfiltering.

## 10. Request–Reply and Correlation Metadata

A request–reply flow can use:
- `JMSCorrelationID` to match responses to requests;
- `JMSReplyTo` to specify where to reply;
- `JMSMessageID` for correlation under a defined convention (e.g., reply correlation ID equals the request's message ID);
- a separate `eventId`/`requestId` for business correlation across retries.

~~~text
Requester                  Worker                  Reply queue
    |                        |                          |
    |-- request ------------>|                          |
    | JMSCorrelationID=R123  |                          |
    | JMSReplyTo=replyQueue  |                          |
    |                        |-- reply ----------------->|
    |                        |   JMSCorrelationID=R123   |
    |<----------------------- reply matched by R123 ----|
~~~

This is **a convention**, not something the provider chooses for every correlation ID automatically. All parties must agree whether to echo `JMSCorrelationID` or use the request's `JMSMessageID` as the key. A JMS selector waiting on the wrong correlation ID can cause the caller to time out even when the message arrived.

With a Spring `@JmsListener` returning a non-void value/`@SendTo`, Spring can use `JMSReplyTo` or a default reply destination to send the response. When returning a Spring Messaging `Message<?>`, certain headers may be mapped outbound; check the adapter configuration. Avoid setting `jms_replyTo` to an arbitrary String if the mapper expects a JMS `Destination`.

**Reliability:** request–reply needs deadlines/TTL, handling late replies, duplicate requests, idempotency, and avoiding a shared reply queue where any consumer can accidentally steal another's message.

## 11. Common Errors and Fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `@Header("JMSCorrelationID")` fails to retrieve value | That is the JMS API header name, not the standard Spring Messaging key | Use `@Header(JmsHeaders.CORRELATION_ID)` or raw `getJMSCorrelationID()` |
| `@Header("jms_messageId")` is null | Provider may disable IDs or custom mapper omits it | Use `required=false`, check raw JMS/provider config |
| `@Header("eventType")` is null even though JSON body has field | Selector/header mapper does not parse JSON fields into properties | Have producer set JMS property `eventType` explicitly |
| `@Header("schemaVersion") Integer` fails | Producer sent property as String or wrong name/type | Standardize producer `setIntProperty`, validate contract |
| `JmsHeaders.TYPE` differs from `_type` | `JMSType` and converter type-id property are two different fields | Specify event type/schema clearly, do not conflate them |
| `@Header(JmsHeaders.REPLY_TO) String` fails to bind | Native value is `Destination`, not a portable String queue name | Read `Destination` or use accessor |
| Taking `MessageHeaders.ID` as JMS message ID | Spring envelope ID and provider JMS ID are different | Use `JmsHeaders.MESSAGE_ID` |
| Reading `JmsHeaders.PRIORITY` then forwarding with same priority | Outbound QoS is governed by producer/provider | Configure explicit QoS on sender |
| Copying `jms_redelivered=true` onto a new send | Redelivery flag is provider state, not arbitrary business metadata | Let provider manage it; use a separate eventId |
| Using `DefaultJmsHeaderMapper` in Spring JMS code and class is missing | That class belongs to Spring Integration, not core Spring Framework JMS | Use `SimpleJmsHeaderMapper` or add Spring Integration if truly needed |
| Header type lost after bridge | Mapper only transfers valid JMS property types or uses prefix/allowlist | Check mapper, types, contracts, integration tests |
| Consumer receives right headers yet processes duplicates | Message may be redelivered or producer retried | Deduplicate by eventId, proper transaction/ACK |
| Headers contain tokens/user PII | Logs/monitoring/broker browsing can leak data | Minimize data, mask secrets, manage ACLs and retention |
| Listener does not run | Wrong destination/ACL, factory, transaction, or selector, not necessarily mapping | Check broker URL, registry, listener container, and logs |
| Header has value yet selector fails to match | Used Spring key `jms_priority` instead of JMS selector `JMSPriority`, or wrong type | Write selector per JMS syntax and property types |
| `JmsHeaders.EXPIRATION` missing in Spring Integration map | Spring Integration mapper has an option to map inbound expiration | Enable the right mapper option on the integration endpoint if needed |

## 12. Testing Metadata: What Should Be Checked?

### 12.1. Deterministic Test Suite

| Case | Input message | What to verify |
| --- | --- | --- |
| T01 | Has `JMSCorrelationID` and String `eventType` | `@Header(JmsHeaders.CORRELATION_ID)`, `@Header("eventType")` match |
| T02 | Has `JMSType` | `@Header(JmsHeaders.TYPE)` matches, not confused with converter `_type` |
| T03 | Missing `JMSCorrelationID` | Optional header is null; listener does not fail due to required |
| T04 | Has custom int `schemaVersion` | `@Header("schemaVersion") Integer` receives matching type |
| T05 | String `schemaVersion` `"1"` | Test converter/binder and numeric selector; do not assume automatic compatibility |
| T06 | Has `JMSReplyTo` | `Destination` is mapped properly, not coerced to String |
| T07 | Producer does not set `JMSMessageID` manually | Provider assigns `JMSMessageID` per policy; assert present if ID enabled |
| T08 | Priority 7 on send via explicit QoS | Received header reflects actual `JMSPriority` confirmed by provider |
| T09 | TTL > 0 | `JMSExpiration` has a sensible value, without setting header directly |
| T10 | Redelivery after rollback | `JMSRedelivered`, `JMSXDeliveryCount` change per contract/provider |
| T11 | Producer retries sending two messages with same eventId | JMS IDs may differ, eventId remains identical; consumer idempotency |
| T12 | Spring Message forwarded to JMS | Read-only standard headers are reassigned by provider; business metadata is selectively kept |

**Note:** T06/T08/T09/T10/T12 require separate broker setups or experiments. The runnable demo focuses only on inbound mapping of correlation/type/custom props/priority to keep scope clear.

### 12.2. Do Not Test by Calling the Java Method Directly

Calling:

~~~java
listener.handle(...);
~~~

bypasses the JMS container, `JmsHeaderMapper`, and provider, so it **cannot** prove `@Header` binding works. Integration tests must send a real JMS message through a broker or properly exercise the listener adapter/message conversion layer in a suitable test framework.

### 12.3. Assertions to Include

- Producer sets native headers using standard setters.
- Producer sets custom properties with the exact **JMS types**.
- Listener receives the expected payload and headers under `JmsHeaders.*` keys.
- Missing optional headers do not fail the handler.
- Each test suite uses unique IDs so it does not pick up messages from previous runs.
- Use a latch/future with finite timeout rather than fixed `Thread.sleep`.
- Test error paths: broker unavailable, missing consume permissions, bad converter, transaction rollback, or unmatched selector.
- When multiple producers exist, contract tests verify they emit identical JMS property names/types regardless of Java/Node/Go.
- In negative mapping tests, receive the raw JMS message to compare native headers and determine whether the bug is in the producer or the mapper.

## 13. Operations: Logging and Tracing Metadata Properly

A log event might include:

~~~text
broker=artemis-test
queue=orders.events
eventId=e-123
jmsCorrelationId=req-456
jmsMessageId=ID:...
jmsRedelivered=false
eventType=order.created
schemaVersion=1
handlerResult=success
~~~

This is an **illustrative log format**, not output printed automatically by Spring. Do not log the entire `@Headers Map` without controlling its contents: it may include tenant IDs, tokens, custom PII, or vendor-specific headers.

**Observability recommendations:**
- Use stable `eventId`/`correlationId` values to correlate producer→broker→consumer logs.
- If using OpenTelemetry, follow W3C trace context conventions (`traceparent`/`tracestate`) per active instrumentation; **do not** assume `JMSCorrelationID` is a standard trace ID.
- When the broker redelivers, log `JMSRedelivered` and `JMSXDeliveryCount` alongside `eventId` for retry analysis.
- Do not treat `JMSMessageID` as business-unique across producer retries.
- Track metrics for queue depth, oldest message age, retries/DLQ, and processing latency.
- When forwarding across a bridge, maintain an explicit allowlist of headers to preserve instead of copying all standard JMS headers/provider internals.

## 14. Adoption Checklist

- [ ] Can distinguish `jakarta.jms.Message` from `org.springframework.messaging.Message<?>`.
- [ ] Use `org.springframework.jms.support.JmsHeaders` for mapped standard JMS headers.
- [ ] Do not confuse `MessageHeaders.ID` with `JmsHeaders.MESSAGE_ID`.
- [ ] Use `@Header` for a single field and `@Headers Map` for the metadata map.
- [ ] Optional headers use `required=false`/nullable types or proper null checks.
- [ ] Custom JMS properties have contracted names/types; do not rely on JSON body fields.
- [ ] Metadata needed for selectors is set as properly typed JMS properties.
- [ ] `JMSReplyTo` is typed as `Destination` when accessed natively.
- [ ] QoS is managed by the producer/template; do not set priority/expiration via custom mapping expecting the provider to honor them.
- [ ] `JmsHeaderMapper`/`SimpleJmsHeaderMapper` and Spring Integration's `DefaultJmsHeaderMapper` are distinguished by module.
- [ ] When using integration gateways/adapters, inbound/outbound mapping policies are reviewed and tested.
- [ ] No unnecessary PII/secrets are placed in JMS properties/logs.
- [ ] Integration tests exist on a dedicated queue with a real broker, never ACKing production messages.
- [ ] ACK/transaction/idempotency strategies are independent of metadata headers.

### Self-Check Questions

1. What string value does `JmsHeaders.CORRELATION_ID` hold, and which JMS getter does it map from?
2. Why should `JMSCorrelationID`, `JMSMessageID`, and Spring `MessageHeaders.ID` not be used interchangeably?
3. Does `@Header(JmsHeaders.TYPE)` correspond to `JMSType` or the converter property `_type`?
4. How do you retrieve all Spring-mapped metadata in `@JmsListener`?
5. Is `@Header(JmsHeaders.REPLY_TO) String` always valid? Why or why not?
6. Why might `message.setJMSPriority(9)` before sending fail to guarantee priority 9 is used?
7. How does Spring Framework's `SimpleJmsHeaderMapper` differ from Spring Integration's `DefaultJmsHeaderMapper`?
8. If `eventType` only exists inside a JSON body, can `@Header("eventType")` read it automatically?
9. If you want a selector by priority, do you write `JMSPriority >= 7` or `jms_priority >= 7`?
10. For a message redelivered after rollback, which metadata do you inspect and why doesn't it replace business deduplication?
11. When forwarding a message to another queue, what should you do with `JMSMessageID` and `JMSTimestamp`?
12. Does a test invoking the annotated method directly prove Spring header mapping works?

**Remember:** `JmsHeaders` defines **JMS metadata names inside Spring Messaging headers**. `@Header`/`@Headers` help listeners extract standard headers and custom properties; `SimpleJmsHeaderMapper` translates between native JMS and Spring Message. Read the right keys, types, and mapping directions; let the JMS provider manage read-only/QoS headers; use `eventId`/correlation IDs with stable contracts; and verify with a real listener on a test broker.

## References

1. Spring Framework 6.2 — Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
2. Spring Framework 6.2 — `JmsHeaders` constants and package: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/jms/support/JmsHeaders.html
3. Spring Framework 6.1 — `SimpleJmsHeaderMapper`: https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html
4. Spring Framework 6.2 — `JmsMessageHeaderAccessor`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/support/JmsMessageHeaderAccessor.html
5. Spring Integration 6.x — JMS Header Mapping / `DefaultJmsHeaderMapper`: https://docs.spring.io/spring-integration/reference/jms.html
6. Spring Boot 3.x — JMS / Artemis support: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
7. Jakarta Messaging 3.1 Specification — Message headers and properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
