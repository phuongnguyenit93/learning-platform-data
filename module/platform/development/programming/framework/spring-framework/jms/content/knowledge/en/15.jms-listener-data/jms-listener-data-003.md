# Receiving org.springframework.messaging.Message to Read Payload and Headers in Spring JMS

## 1. Objectives and Practical Problem

In Spring JMS, a listener often only needs a `String` or DTO from the message body. However, important business workflows also need metadata: `eventType`, `sourceSystem`, `attempt`, `JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`, etc. If you only write `@JmsListener public void handle(String body)`, that information is not inside the `body` variable.

Spring allows receiving **`org.springframework.messaging.Message<T>`**, an abstraction consisting of two components:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

Usage:

```java
@JmsListener(destination = "orders.in")
public void onOrder(Message<String> message) {
    String body = message.getPayload();
    String eventType =
            message.getHeaders().get("eventType", String.class);
    System.out.println(body + " / " + eventType);
}
```

Imports:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
```

This is a method **inside a registered Spring bean**, not a standalone runnable program. This lesson explains how Spring creates the `Message<T>` wrapper, how to read payload/headers properly, how to distinguish `JmsHeaders` from `MessageHeaders`, how to handle missing/mistyped headers, and how to run a Java 17 + Spring Boot + Artemis example.

## 2. Do Not Confuse Spring Message with Jakarta JMS Message

There are **two interfaces sharing the name `Message`**:

| Characteristic | Spring Messaging | Jakarta Messaging |
| --- | --- | --- |
| Full name | `org.springframework.messaging.Message<T>` | `jakarta.jms.Message` |
| Primary API | `getPayload()`, `getHeaders()` | `getJMSMessageID()`, `getJMSCorrelationID()`, `getObjectProperty()`, etc. |
| Meaning | Generic payload + header wrapper | Native message managed by the JMS provider |
| Body type | Generic `T` after conversion | Native body depending on `TextMessage`, `BytesMessage`, `MapMessage`, etc. |
| Checked exceptions | No `JMSException` needed just to read the map | Many native getters throw `JMSException` |
| When to use | Wanting to process payload and mapped headers | Needing native header/body API or JMS-specific operations |

Spring Message:

```java
@JmsListener(destination = "orders.in")
public void handle(org.springframework.messaging.Message<String> msg) {
    String body = msg.getPayload();
    Object type = msg.getHeaders().get("eventType");
}
```

Native JMS Message:

```java
@JmsListener(destination = "orders.in")
public void handleNative(jakarta.jms.TextMessage msg)
        throws jakarta.jms.JMSException {
    String body = msg.getText();
    String type = msg.getStringProperty("eventType");
}
```

**Do not register both examples on the same Queue expecting a single message to be delivered to both.** With a Queue, consumers compete and one message may be received by one consumer before the other.

If your IDE suggests importing `jakarta.jms.Message` while the code needs `getPayload()`, change the import to `org.springframework.messaging.Message`. `org.springframework.messaging.support.GenericMessage<T>` is a Spring Message implementation used to construct an in-memory object; it is not itself a JMS message sitting on a broker.

## 3. How Spring Converts the Message When Invoking @JmsListener

Typical path:

```text
Producer:
  jakarta.jms.TextMessage("ORDER-101")
  JMS property: eventType="ORDER_CREATED"
  JMS header:   JMSCorrelationID="req-101"
                |
                v
          JMS Queue/broker
                |
                v
       Spring listener container
                |
                v
      JMS conversion + header mapping
                |
                v
  org.springframework.messaging.Message<String>
     getPayload() -> "ORDER-101"
     getHeaders() -> {
       eventType: ORDER_CREATED,
       jms_correlationId: req-101,
       jms_messageId: provider-generated ID,
       ...
     }
                |
                v
       @JmsListener method
```

Spring JMS annotated infrastructure directly supports `org.springframework.messaging.Message`, raw `jakarta.jms.Message`, `jakarta.jms.Session`, and `@Header`, `@Headers`, `@Payload` parameters. Payload converters and mappers such as `MessagingMessageConverter`, `SimpleMessageConverter`, and `SimpleJmsHeaderMapper` determine the actual values passed into the handler.

- The body is converted to type `T`; for a JMS `TextMessage`, the default configuration typically yields `String`.
- JMS API headers are mapped to `JmsHeaders` keys.
- JMS custom properties are mapped to application header names, such as `eventType`.
- The handler runs when the adapter can resolve/convert the required parameters.

Conversion errors may arise **before the method body begins executing**. Therefore, a `try/catch` inside the listener cannot catch every mapping error; container error handling and transactions must be configured.

## 4. Reading getPayload(): What Does the Generic Mean?

`Message<String>` carries a `String` payload; `Message<OrderEvent>` carries an `OrderEvent` payload **if the converter can produce that object**; `Message<?>` does not assume a specific payload type yet.

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> msg) {
    String body = msg.getPayload();  // no cast needed
    if (body.isBlank()) {
        throw new IllegalArgumentException("Empty order payload");
    }
}
```

If you need to receive multiple payload forms in an appropriately configured environment:

```java
@JmsListener(destination = "mixed.in")
public void handleMixed(Message<?> msg) {
    Object payload = msg.getPayload();
    if (payload instanceof String text) {
        System.out.println("TEXT " + text);
    } else if (payload instanceof byte[] bytes) {
        System.out.println("BYTES " + bytes.length);
    } else {
        System.out.println(payload.getClass().getName());
    }
}
```

These are snippets inside a Spring bean, not standalone classes. Java 17 supports pattern matching `instanceof`. **Generics are not a JSON decoder**: a `TextMessage` containing `{"orderId":"A"}` still normally has a `String` payload if no JSON converter/type mapping is configured. Do not blindly cast `(OrderEvent) msg.getPayload()` just because the body looks like JSON.

## 5. Reading getHeaders() and Header Lookup Methods

`MessageHeaders` holds key–value metadata. Read it like a Map:

```java
MessageHeaders h = incoming.getHeaders();

Object raw = h.get("eventType");
String type = h.get("eventType", String.class);
Integer attempt = h.get("attempt", Integer.class);

java.util.UUID springId = h.getId();
Long springTimestamp = h.getTimestamp();
```

This snippet runs in a method with `incoming: Message<?>`. `get(name, Class<T>)` enforces the expected type; it is **not** an arbitrary String-to-Integer converter. If the producer called `setStringProperty("attempt", "1")`, do not assume `h.get("attempt", Integer.class)` will automatically parse it to `1`.

Headers can be missing; before using an optional key:

```java
String correlationId = h.get(
        JmsHeaders.CORRELATION_ID, String.class);
if (correlationId == null || correlationId.isBlank()) {
    System.out.println("No JMS correlation ID");
}
```

`JmsHeaders` belongs to `org.springframework.jms.support.JmsHeaders` and defines the standard **key names** used by the mapper. Custom headers typically use the exact property name set by the producer. Custom property names are case-sensitive.

### Do Not Print the Entire Header Map in Production

Headers can contain customer identifiers, request IDs, tokens, or sensitive data depending on the application. Only log a safe metadata whitelist, masking or hashing identifiers when necessary. `h.keySet()` helps debug key names, though appropriate operational rules are still needed.

## 6. Important JmsHeaders Constants

```java
import org.springframework.jms.support.JmsHeaders;
```

| Key | Source from JMS | What to remember |
| --- | --- | --- |
| `JmsHeaders.MESSAGE_ID` | `getJMSMessageID()` | Native JMS ID, typically a provider-generated String. |
| `JmsHeaders.CORRELATION_ID` | `getJMSCorrelationID()` | String used in request–reply/correlation, may be null. |
| `JmsHeaders.REDELIVERED` | `getJMSRedelivered()` | Boolean reflecting the JMS redelivery flag. |
| `JmsHeaders.PRIORITY` | `getJMSPriority()` | Numeric, not an arbitrary business priority. |
| `JmsHeaders.DESTINATION` | `getJMSDestination()` | Destination determined by the provider. |
| `JmsHeaders.REPLY_TO` | `getJMSReplyTo()` | Response destination, may be absent. |
| `JmsHeaders.TYPE` | `getJMSType()` | JMS type label, may be absent. |
| `JmsHeaders.TIMESTAMP` | `getJMSTimestamp()` | Native timestamp, distinct from the Spring timestamp. |
| `JmsHeaders.EXPIRATION` | `getJMSExpiration()` | JMS expiration timestamp, if present. |
| `JmsHeaders.DELIVERY_MODE` | `getJMSDeliveryMode()` | Persistent/nonpersistent per the JMS API. |

Do not cast `DESTINATION` or `REPLY_TO` to String without checking: the mapped value may be a `jakarta.jms.Destination` object. Many standard headers are read-only on outbound and are assigned by the broker/provider upon sending; the header mapper can also be customized.

Example:

```java
String jmsId = h.get(JmsHeaders.MESSAGE_ID, String.class);
String correlation = h.get(
        JmsHeaders.CORRELATION_ID, String.class);
Boolean redelivered = h.get(
        JmsHeaders.REDELIVERED, Boolean.class);
```

If you want to read priority, use `Integer` when the mapper provides the corresponding numeric type; in custom mapper environments, inspect as `Object` before casting.

## 7. Do Not Confuse Spring IDs and Timestamps with JMS Ones

```java
java.util.UUID springId = incoming.getHeaders().getId();
String jmsMessageId = incoming.getHeaders().get(
        JmsHeaders.MESSAGE_ID, String.class);

Long springTimestamp = incoming.getHeaders().getTimestamp();
Object jmsTimestamp = incoming.getHeaders().get(
        JmsHeaders.TIMESTAMP);
```

The two IDs are not equivalent:

- `MessageHeaders.ID`: identifier of the Spring Message envelope (typically a UUID), which may change when creating a new wrapper.
- `JmsHeaders.MESSAGE_ID`: native `JMSMessageID` assigned by the provider for that JMS send.
- `JmsHeaders.CORRELATION_ID`: correlation ID chosen by the producer or request–reply contract, **not equal by default to either ID above**.

Similarly, `MessageHeaders.TIMESTAMP` typically records when the Spring Message was created, while `JmsHeaders.TIMESTAMP` is the native `JMSTimestamp`. When measuring latency, make sure you use the right reference timestamp.

A conceptual log:

```text
springId=<UUID of Spring wrapper>
jmsId=<ID assigned by JMS provider>
correlationId=req-101
```

The placeholders in this block describe **types of values**, not literal data to put into code. Do not use `MessageHeaders.ID` as proof that a JMS message was ACKed or as a unique business event ID during retries.

## 8. Custom JMS Properties: Data Outside the Body

A producer can attach properties to a native JMS message:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-101");
    msg.setStringProperty("eventType", "ORDER_CREATED");
    msg.setStringProperty("sourceSystem", "checkout");
    msg.setIntProperty("attempt", 1);
    msg.setBooleanProperty("urgent", false);
    msg.setJMSCorrelationID("req-101");
    return msg;
});
```

This is a snippet inside a method with an injected `JmsTemplate`, requiring `import jakarta.jms.TextMessage`. `setJMSCorrelationID` is how you set a **standard JMS header**; `setStringProperty("eventType", ...)` creates a **custom JMS property**.

Listener reading them:

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> incoming) {
    MessageHeaders h = incoming.getHeaders();
    String eventType = h.get("eventType", String.class);
    Integer attempt = h.get("attempt", Integer.class);
    Boolean urgent = h.get("urgent", Boolean.class);
    String correlation = h.get(
            JmsHeaders.CORRELATION_ID, String.class);
}
```

Names such as `eventType` must match exactly; `eventtype` is a different key. A JSON body having an `"eventType"` field **does not automatically create a JMS property** for Spring to map into headers.

### Properties Used in Selectors

```java
@JmsListener(
        destination = "orders.in",
        selector = "eventType = 'ORDER_CREATED' AND attempt >= 1")
public void onCreated(Message<String> incoming) {
    // ...
}
```

Selectors are evaluated by the JMS consumer against existing JMS metadata **before** Spring builds `Message<T>`. A JMS selector cannot access Spring's UUID and does not automatically parse a JSON body. The `attempt` property should be set via `setIntProperty` if the selector needs numeric comparison; `setStringProperty("attempt", "1")` is not equivalent.

## 9. Runnable Example: Java 17 + Spring Boot + Artemis

The following example sends a `TextMessage` with payload `"ORDER-101"`, custom properties `eventType`, `attempt`, `sourceSystem`, and `JMSCorrelationID`; then `@JmsListener(Message<String>)` reads those values back via the Spring Messaging API.

Environment: Java 17, Spring Boot 3.3.13, compatible Gradle 8.x, Apache ActiveMQ Artemis broker at `localhost:61616`. Queue name: `demo.spring.headers`. Assumes the broker allows auto-creating Queues or the Queue is pre-provisioned. Only one listener consumes from this Queue.

### 9.1. Starting Artemis

If Docker is available:

```bash
docker run --detach --rm --name artemis-spring-headers -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Wait for the broker to be ready and check `docker logs artemis-spring-headers`. Port `61616` is for JMS clients. The `demo` username/password is for local use only; real environments must have send/consume permissions and proper security/TLS configuration. When done learning: `docker stop artemis-spring-headers`.

### 9.2. Project Structure

```text
spring-headers-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/jms/
    │   ├── SpringHeadersApplication.java
    │   └── HeadersListener.java
    └── resources/application.yml
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-headers-demo'
```

File `build.gradle`:

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

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
```

### 9.3. Sending a Message with Full Metadata

`src/main/java/demo/jms/SpringHeadersApplication.java`:

```java
package demo.jms;

import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class SpringHeadersApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringHeadersApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.send("demo.spring.headers", session -> {
                TextMessage msg =
                        session.createTextMessage("ORDER-101");
                msg.setStringProperty(
                        "eventType", "ORDER_CREATED");
                msg.setStringProperty(
                        "sourceSystem", "checkout");
                msg.setIntProperty("attempt", 1);
                msg.setJMSCorrelationID("req-101");
                return msg;
            });
            System.out.println("SENT ORDER-101");
        };
    }
}
```

`ApplicationRunner` executes after Spring Boot starts; `JmsTemplate.send` uses `Session` to create a TextMessage and send it through the provider. `JMSMessageID` is assigned by the provider, not an application-generated ID in the Spring envelope.

### 9.4. Receiving Spring Message<String> in the Listener

`src/main/java/demo/jms/HeadersListener.java`:

```java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

@Component
public class HeadersListener {

    @JmsListener(destination = "demo.spring.headers")
    public void handle(Message<String> incoming) {
        String body = incoming.getPayload();
        MessageHeaders h = incoming.getHeaders();

        String type = h.get("eventType", String.class);
        String source = h.get("sourceSystem", String.class);
        Integer attempt = h.get("attempt", Integer.class);
        String correlation =
                h.get(JmsHeaders.CORRELATION_ID, String.class);
        String nativeId =
                h.get(JmsHeaders.MESSAGE_ID, String.class);

        if (!"ORDER_CREATED".equals(type) ||
                attempt == null || attempt < 1) {
            throw new IllegalArgumentException(
                    "Unexpected event metadata");
        }

        System.out.printf(
                "RECEIVED body=%s type=%s source=%s " +
                "attempt=%d correlation=%s idPresent=%s%n",
                body, type, source, attempt, correlation,
                nativeId != null && !nativeId.isBlank()
        );
    }
}
```

Point to remember: `HeadersListener` **does not import `jakarta.jms.Message`** because its input parameter is Spring `Message<String>`. Standard headers are read via `JmsHeaders`, while custom properties are read via `eventType`, `sourceSystem`, and `attempt`.

### 9.5. Running and Explaining Output

From the directory containing `build.gradle`:

```bash
gradle bootRun
```

If using the Gradle Wrapper: Linux/macOS `./gradlew bootRun`, Windows `gradlew.bat bootRun`.

With a clean broker, an existing/validly created Queue, a single consumer, and no conversion errors, you may see:

```text
SENT ORDER-101
RECEIVED body=ORDER-101 type=ORDER_CREATED source=checkout attempt=1 correlation=req-101 idPresent=true
```

These two lines **can swap order**, because the listener runs asynchronously. The broker may return different headers depending on policy; this is the **expected output under proper conditions**, not the transcript of an Artemis run executed during authoring. Avoid inferring from `idPresent=true` that a business transaction or ACK has completed.

If the broker holds messages from an older run, has competing consumers, has Queue auto-create disabled, or the user lacks permissions, output will differ or startup/sending may fail. Clean up test backlogs carefully with broker tools; never delete production Queues.

## 10. @Header, @Headers, and @Payload: When Do You Not Need All of Message<T>?

Spring offers alternative method signature forms.

### @Header for a Single Metadata Field

```java
@JmsListener(destination = "orders.in")
public void handle(
        @Payload String orderId,
        @Header("eventType") String eventType,
        @Header(name = JmsHeaders.CORRELATION_ID,
                required = false) String correlationId) {
    System.out.println(orderId + "/" + eventType);
}
```

Imports: `org.springframework.messaging.handler.annotation.Payload`, `org.springframework.messaging.handler.annotation.Header`, and `JmsHeaders`. A `@Header` parameter is required by default; if the header is absent, resolution may fail. With `required=false`, the handler must be prepared to receive `null`.

### @Headers for a Map

```java
@JmsListener(destination = "orders.in")
public void inspect(
        @Payload String body,
        @Headers java.util.Map<String, Object> headers) {
    Object type = headers.get("eventType");
    Object id = headers.get(JmsHeaders.MESSAGE_ID);
}
```

Requires importing `org.springframework.messaging.handler.annotation.Headers`. `@Headers` receives a Map of values provided by the mapper, not all internal broker metadata.

Comparison:

| Requirement | Signature |
| --- | --- |
| Only need content | `String body` |
| Payload and one property | `String body, @Header("eventType") String type` |
| Payload and multiple headers | `Message<String> incoming` |
| Unknown which headers are present | `@Headers Map<String,Object> headers` |
| Native JMS getters or Session | `jakarta.jms.TextMessage`, `jakarta.jms.Session` |

The snippets in this section are **alternative options**; do not register them on the same Queue in the demo to avoid competing consumers.

## 11. Receiving a DTO via Message<OrderEvent> and a Converter

The Spring reference allows a listener with signature `Message<OrderEvent>`:

```java
@JmsListener(destination = "orders.events")
public void onOrder(Message<OrderEvent> message) {
    OrderEvent order = message.getPayload();
    String eventType = message.getHeaders().get(
            "eventType", String.class);
}
```

However, the application must define `OrderEvent` and configure a converter to turn the JMS body into a DTO. If the producer only sends a JSON String in a TextMessage, the generic type **does not** cause JSON to deserialize automatically.

A JSON converter configuration you can use:

```java
@Bean
public MappingJackson2MessageConverter jmsMessageConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}
```

This is a method inside `@Configuration`, requiring imports for `@Bean`, `MappingJackson2MessageConverter`, and `MessageType` from `org.springframework.jms.support.converter`, along with the necessary Jackson dependency. The converter must be wired to the right `JmsTemplate` and listener factory (Boot-configured or custom), and producer–consumer must agree on the type id. With custom factories, do not assume merely declaring a bean is enough.

If conversion fails before method invocation, an appropriate error handler, transaction/rollback, and DLQ are needed. When first debugging type mapping, use `Message<String>` to inspect raw JSON before switching to a DTO.

## 12. Reading Mistyped or Missing Headers

Common cases:

- Producer did not set `JMSCorrelationID`: `JmsHeaders.CORRELATION_ID` may be null.
- Custom header `"attempt"` set by producer as String `"1"`: do not read with `Integer.class` without converting according to the contract.
- Data only exists in the JSON body: `headers.get("eventType")` may be null.
- Mapper has a customized inbound prefix or whitelist: a key may differ from defaults.
- Some native JMS headers have type `Destination` or provider-specific types: do not coerce everything to `String`.

Type-checking pattern:

```java
Object attemptValue = incoming.getHeaders().get("attempt");

if (attemptValue instanceof Number n && n.intValue() > 0) {
    int attempt = n.intValue();
    System.out.println(attempt);
} else {
    throw new IllegalArgumentException(
            "Missing or invalid numeric attempt");
}
```

This is a snippet inside a method with `incoming: Message<?>`. Java 17 supports `instanceof Number n`. If the schema genuinely allows String `"1"`, parse it explicitly and check errors rather than assuming the typed getter parses automatically.

## 13. Immutable MessageHeaders and MessageBuilder

Spring `MessageHeaders` exposes a Map API for **reading**, but you should not call:

```java
incoming.getHeaders().put("validated", true);
```

This is **not** a way to modify the received JMS message; a Spring Message's headers structure is treated as immutable. When you need a **new Spring Message** with added metadata, use:

```java
Message<String> enriched = MessageBuilder
        .fromMessage(incoming)
        .setHeader("validated", true)
        .build();
```

Requires importing `org.springframework.messaging.support.MessageBuilder`, inside a method with `incoming: Message<String>`. It creates a new wrapper at the application layer, **does not** modify the message on the broker, and **does not** ACK the message.

If returning `Message<R>` from `@JmsListener` with a configured response destination such as `@SendTo` or `JMSReplyTo`, Spring can send a reply. However, that is a separate outbound path; read-only headers like JMSMessageID, priority, or expiration are not guaranteed to be honored by the broker as native outbound values just by placing them in `MessageBuilder`. Configure JMS producer/template QoS when real priority/TTL is needed.

## 14. ACK Mechanism, Transactions, and Conversion Errors

The `@JmsListener(Message<String>)` signature does not change acknowledgment responsibilities:

- The container creates/obtains the JMS Session and MessageConsumer, then invokes the listener.
- The container and transaction manager decide ACK/commit/rollback.
- `getPayload()` and `getHeaders()` are **not** acknowledge commands.
- Spring `Message<T>` does not have `message.acknowledge()` like a native JMS Message.
- If conversion fails before the method, the exception is handled by the container according to its configuration, bypassing any `try/catch` inside the listener body.

With a locally transacted session, an exception from the handler can trigger rollback and broker redelivery; with non-transacted `AUTO_ACKNOWLEDGE`, **do not assume** redelivery will occur when the listener throws an exception. A handler that catches an error, logs it, and returns normally may cause the container to treat delivery as successful and commit.

```java
@JmsListener(destination = "orders.in")
public void handle(Message<String> message) {
    String type = message.getHeaders().get(
            "eventType", String.class);

    if (!"ORDER_CREATED".equals(type)) {
        throw new IllegalArgumentException(
                "Unexpected eventType: " + type);
    }

    processOrder(message.getPayload());
}
```

`processOrder` is an application-provided business method, not part of a standalone snippet. If DB updates occur, a local JMS transaction does not automatically create an XA transaction with the DB. An idempotent consumer, business event ID, retry/DLQ, and clear transaction boundaries are needed.

## 15. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `getPayload()` fails to compile | Wrongly imported `jakarta.jms.Message`. | Use `org.springframework.messaging.Message<T>`. |
| `getJMSMessageID()` fails to compile | Spring Message lacks native JMS getters. | Use `getHeaders().get(JmsHeaders.MESSAGE_ID)`. |
| `headers.get("eventType") == null` | Producer omitted property, or wrong key casing. | Set JMS property and check the mapper. |
| `JmsHeaders.CORRELATION_ID` is null | Producer did not set JMSCorrelationID. | Check contract, allow optional if appropriate. |
| Spring UUID differs from JMS ID | Two IDs serve different purposes. | Separate `MessageHeaders.ID` and `JmsHeaders.MESSAGE_ID`. |
| `Message<OrderEvent>` does not receive DTO | Missing converter/type mapping. | Set up JSON converter and schema. |
| `get("attempt", Integer.class)` fails | Producer used String property or different mapper. | Inspect `get("attempt")`, fix property type. |
| Adding header via `put` does not work | Spring Message headers are immutable. | Use `MessageBuilder` to create a new object. |
| Listener not called despite message on broker | Selector, competing consumer, conversion error, ACL, or wrong destination. | Check broker, selector, converter, logs. |
| Error handler invoked repeatedly | Poison message/transaction rollback and redelivery. | Retry policy, DLQ/quarantine, handle permanent errors. |
| Logs dump all headers and leak data | Unfiltered metadata map dump. | Log only safe headers, apply redaction. |
| `redelivered=false` yet duplicate business processing occurs | Producer retry or failure between DB/JMS commit. | Business event ID + idempotency. |

An effective debugging sequence: verify imports; safely print header key names; inspect producer setters `setJMSCorrelationID` and `setXxxProperty`; compare Spring UUID with JMS ID; check converters and Queue/Topic/selector; inspect transactions, redelivery, and DLQ on error.

## 16. Testing and Self-Practice Questions

### In-Memory Unit Test

```java
Message<String> message = MessageBuilder
        .withPayload("ORDER-101")
        .setHeader("eventType", "ORDER_CREATED")
        .setHeader("attempt", 1)
        .setHeader(JmsHeaders.CORRELATION_ID, "req-101")
        .build();

String body = message.getPayload();
String eventType = message.getHeaders().get(
        "eventType", String.class);
Integer attempt = message.getHeaders().get(
        "attempt", Integer.class);
```

This is a snippet using Spring Messaging and `MessageBuilder`, **not a broker integration test**. It helps test header-map handling logic, but does not prove the JMS header mapper works over the wire.

### Integration Test with Artemis

1. Send a TextMessage with payload `"ORDER-101"`, custom `eventType`/numeric `attempt`, and `JMSCorrelationID`.
2. Verify the `Message<String>` listener receives the exact body, custom properties, and `JmsHeaders.CORRELATION_ID`.
3. Verify `JmsHeaders.MESSAGE_ID` is present and distinct from Spring `headers.getId()`.
4. Test missing correlation ID to ensure the handler does not hit a NullPointerException.
5. Test String property `"attempt"="1"` and verify typed header access handles schema mismatches properly.
6. Test a JSON DTO with a separately configured converter and verify pre-method conversion failures.
7. Test rollback/redelivery when the handler throws an error in a transacted session, without using `JMSRedelivered` as an event ID.
8. Test on a clean Queue with a single consumer, without asserting log ordering between publisher and listener.

### Questions

**1.** Why does `org.springframework.messaging.Message<String>` have `getPayload()` while `jakarta.jms.Message` does not? — **Because they are two different interfaces**; Spring uses a payload/header abstraction, while Jakarta JMS uses a native message/body API.

**2.** Is `getHeaders().getId()` the `JMSMessageID`? — **No**. Read `JmsHeaders.MESSAGE_ID` to get the native JMS message ID.

**3.** Does an `eventType` field inside a JSON body automatically become a JMS header? — **No**. A JMS property or explicit custom mapping is needed.

**4.** Why doesn't `Message<OrderEvent>` automatically convert JSON into a DTO? — **A generic type does not replace a converter**. You must configure a payload converter/type/schema.

**5.** Does reading `getPayload()` ACK the message? — **No**. The container/Session/transaction policy manages acknowledgment and commits.

**6.** If only one header is needed, which API is cleaner? — `@Header("eventType")` combined with a payload argument; the header can specify `required=false` when optional.

**7.** Why shouldn't you use `incoming.getHeaders().put(...)`? — Headers are treated as immutable. Use `MessageBuilder.fromMessage(...).setHeader(...).build()` to construct a new Spring Message.

## 17. Official References and Conclusion

- [Spring Framework – Annotation-driven Listener Endpoints: Message<T> support](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework – JMS Message Listener](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 – Spring Message<T>](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework 6.2 – MessageHeaders](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.2 – JmsHeaders](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [Spring Framework 6.2 – SimpleJmsHeaderMapper](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html)
- [Spring Framework 6.2 – MessagingMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [Spring Boot – Messaging with JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Apache Artemis – Official Docker Images](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Conclusion:** When you need both content and metadata in `@JmsListener`, receive `org.springframework.messaging.Message<T>`; `getPayload()` gives the converted payload, and `getHeaders()` gives mapped headers and JMS properties. Use `JmsHeaders` for native JMS fields, distinguish `MessageHeaders.ID` from `JmsHeaders.MESSAGE_ID`, and configure converters/transactions according to the actual contract.
