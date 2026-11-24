# JmsTemplate: Distinguishing send and convertAndSend

**Scope:** Spring Framework JMS, focusing on the two method groups `JmsTemplate.send(...)` and `JmsTemplate.convertAndSend(...)`. The goal is to read the API signatures, know who creates `jakarta.jms.Message`, understand payload conversion, set headers/properties at the right time, and choose the right API for each message type.

**Illustrative environment:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging (`jakarta.jms`), a compatible JMS broker (e.g., Apache ActiveMQ Artemis). The examples can be used directly in Spring Boot 3.x once `ConnectionFactory` and destinations are configured. Plain Spring Framework uses the same `JmsTemplate`, with the application registering the beans itself.

## 1. First answer: both send JMS, different Message creators

Both APIs send a **JMS Message** to a **Destination** via the `ConnectionFactory`, `Session`, and producer managed by `JmsTemplate`. The difference lies in the message-creation step:

- **`send(...)`:** the application provides a **`MessageCreator`**. The callback receives a `Session`, creates a `TextMessage`, `BytesMessage`, `MapMessage`, or whatever JMS message type is needed, sets application-owned properties/headers, and returns the `jakarta.jms.Message`. `JmsTemplate` then sends that message. **There is no automatic Java Object-to-JMS Message conversion via `MessageConverter`.**
- **`convertAndSend(...)`:** the application passes a **Java object/payload**. `JmsTemplate` invokes **`MessageConverter.toMessage(object, session)`** to create the JMS Message. If additional headers/properties are needed, the overload with **`MessagePostProcessor`** allows modifying the message **after conversion but before sending**.

~~~text
send(destination, MessageCreator)
    └─ callback: Session → manually creates jakarta.jms.Message
                           → JmsTemplate sends → provider/broker

convertAndSend(destination, Object)
    └─ MessageConverter: Object → jakarta.jms.Message
                                 → JmsTemplate sends → provider/broker

convertAndSend(destination, Object, MessagePostProcessor)
    └─ MessageConverter: Object → jakarta.jms.Message
                                 → postProcessMessage(Message)
                                 → JmsTemplate sends → provider/broker
~~~

Both method groups are **`JmsTemplate` send operations**: `convertAndSend` is not a different JMS protocol, does not mean “asynchronous”, and does not by itself guarantee that a listener has processed it. After a send succeeds, the message may still be waiting on the broker to be delivered to a consumer.

## 2. API signatures to remember

Typical overloads of `org.springframework.jms.core.JmsTemplate`:

| Group | Signature | What the application passes |
| --- | --- | --- |
| `send` | `send(String destinationName, MessageCreator creator)` | Destination name and callback to create the JMS Message |
| `send` | `send(Destination destination, MessageCreator creator)` | JMS Destination object and callback |
| `send` | `send(MessageCreator creator)` | Callback; requires a configured **default destination** |
| `convertAndSend` | `convertAndSend(String destinationName, Object message)` | Destination name and Java object |
| `convertAndSend` | `convertAndSend(String destinationName, Object message, MessagePostProcessor postProcessor)` | Java object, followed by a callback modifying the JMS Message |
| `convertAndSend` | `convertAndSend(Destination destination, Object message)` | Destination object and Java object |
| `convertAndSend` | `convertAndSend(Object message)` | Java object; requires a **default destination** |

The two callbacks have **different parameter types and timing**:

~~~java
// The snippets below assume JmsTemplate jmsTemplate is already injected.
// MessageCreator: Session -> JMS Message.
jmsTemplate.send("orders.queue", session ->
        session.createTextMessage("OrderCreated"));

// MessagePostProcessor: JMS Message -> JMS Message.
// It runs after MessageConverter, before send.
jmsTemplate.convertAndSend(
        "orders.queue",
        "OrderCreated",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            return message;
        }
);
~~~

In Spring JMS:

- `MessageCreator` is in `org.springframework.jms.core.MessageCreator`.
- `MessagePostProcessor` is in `org.springframework.jms.core.MessagePostProcessor`.
- `MessageConverter` for JMS is in `org.springframework.jms.support.converter.MessageConverter`.
- The `Message` operated on by creators/post-processors is **`jakarta.jms.Message`**; do not confuse it with **`org.springframework.messaging.Message<?>`** in Spring Messaging.

**Both APIs return `void`.** There is no default return value containing a broker-generated ID, business status, or listener processing result. `JmsTemplate` translates `JMSException`s that occur at the JMS layer into `org.springframework.jms.JmsException` (unchecked), while conversion errors can be `MessageConversionException`.

## 3. Similarities matter more than method names suggest

| Aspect | `send` | `convertAndSend` |
| --- | --- | --- |
| Broker connection | Uses `JmsTemplate`'s `ConnectionFactory` | Uses the same `ConnectionFactory` |
| Session/producer lifecycle | `JmsTemplate` creates/obtains, uses, and cleans up per Spring mechanism | Same |
| Destination | By parameter or default destination | Same |
| How body is built | Application builds Message with `Session` | `MessageConverter` builds Message from Object |
| Message type | Determined by `MessageCreator` code | Determined by converter |
| Client-set properties/headers | Inside `MessageCreator` | Inside `MessagePostProcessor` or custom converter |
| Provider headers | Assigned at send time per JMS | Same |
| JMS QoS | Configured on `JmsTemplate`/provider | Same |
| Transactions | Depends on Spring transaction/session/provider | Same |
| Error handling | `JmsException` and other runtime errors | Plus payload conversion errors |
| Consumer ACK | Not confirmed by sending | Same |
| Return value | `void` | `void` |

**It is untrue** that `send` is by default “raw and definitely faster” while `convertAndSend` is “guaranteed more reliable”. Reliability mainly relates to delivery mode, transactions, broker policies, consumer ACK/commit, retries, and idempotency. A converter has payload processing overhead, but performance decisions must be based on benchmarking with real data.

## 4. send: you control creating the JMS Message

### 4.1. Manually creating a TextMessage with metadata

~~~java
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public final class ManualTextPublisher {
    private final JmsTemplate jmsTemplate;

    public ManualTextPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String eventId, String correlationId) {
        jmsTemplate.send("orders.created", session -> {
            String json = """
                    {"type":"OrderCreated","orderId":"O-42","version":1}
                    """.strip();
            TextMessage message = session.createTextMessage(json);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("contentType", "application/json");
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }
}
~~~

This is a Java 17 class **that compiles in a project with Spring JMS**, without a standalone `main`. It requires a Spring-configured `JmsTemplate` and a valid broker/destination. The `Session` passed to the callback is the session the template uses for the operation; you **must not** create a separate session and return a message belonging to a different context.

Here:
1. A Java text block explicitly creates the JSON string.
2. `session.createTextMessage(json)` determines the **JMS type is `TextMessage`**.
3. `setStringProperty(...)` sets application properties, usable for selectors/tracing if supported by the broker.
4. `setJMSCorrelationID(...)` sets a client-controlled standard header; the provider sets provider-owned headers during send.
5. The callback returns the message, and Spring handles resources and sending.

**Advantage of `send`:** you have full control over the Message type, byte encoding, `MapMessage` structure, custom headers, property names, and elements that do not fit the default converter. When a message contract demands a specific format/attributes, this is the transparent choice.

### 4.2. Creating a BytesMessage without accidentally coercing to TextMessage

~~~java
byte[] payload = new byte[] {0x01, 0x02, 0x03};

jmsTemplate.send("binary.tasks", session -> {
    var bytesMessage = session.createBytesMessage();
    bytesMessage.writeBytes(payload);
    bytesMessage.setStringProperty("contentType",
            "application/octet-stream");
    return bytesMessage;
});
~~~

This snippet assumes `jmsTemplate` already exists. With `send`, the type and byte content are decided directly. You are responsible for the **version/schema** of the bytes and how the consumer decodes them; simply setting `contentType` does not make the consumer automatically understand the format.

### 4.3. What should you not do inside MessageCreator?

- Do not close Spring's `Session`, `Connection`, or `MessageProducer` inside the callback.
- Do not perform heavy I/O, HTTP calls, or DB transactions just to construct a message; the callback should focus on creating the message.
- Do not assume provider-assigned `JMSMessageID`, `JMSTimestamp`, or `JMSExpiration` already exist **before sending**. `MessageCreator` runs **before** the send operation.
- Do not set `JMSMessageID` manually hoping it serves as a business event ID; the provider manages the JMS ID upon sending. Use a business property such as `eventId`/`commandId`.
- Do not return a message created from a different `Session` or hold onto a message reference to mutate it asynchronously after the callback finishes.

## 5. convertAndSend: you pass an Object, MessageConverter creates the JMS Message

An equivalent example to the `TextMessage` above when using the **default `SimpleMessageConverter`**:

~~~java
jmsTemplate.convertAndSend(
        "orders.created",
        "{\"type\":\"OrderCreated\",\"orderId\":\"O-42\",\"version\":1}",
        message -> {
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("contentType", "application/json");
            message.setJMSCorrelationID(correlationId);
            return message;
        }
);
~~~

**With the default converter**, `String` becomes `TextMessage`. The body content and metadata can match the `send` example if the inputs are equivalent. **Difference in responsibility**: you do not write `session.createTextMessage(...)`; creating the Message is handled by the converter.

### 5.1. What happens beneath the abstraction?

One way to visualize the execution flow (not internal source code for any specific version):

~~~text
Application calls convertAndSend(destination, payload, postProcessor)
  ├─ JmsTemplate uses the configured MessageConverter
  ├─ converter.toMessage(payload, Session)
  │     └─ creates TextMessage / BytesMessage / MapMessage / ...
  ├─ postProcessor.postProcessMessage(jmsMessage)
  │     └─ adds client properties/headers or adjusts message
  ├─ provider sends JMS Message
  ├─ provider may generate ID/timestamp/QoS metadata
  └─ JmsTemplate releases or returns resources to cache/pool
~~~

If the converter fails, `postProcessor` **has not run yet**, and the provider **has not been asked to send that message**. If the callback throws an error, the message has also not been sent successfully. If the provider send fails at a network boundary, the broker's state can be **uncertain**; do not treat every exception as proof that it was “definitely not sent”.

### 5.2. Passing an Object does not automatically mean JSON

~~~java
jmsTemplate.convertAndSend("orders.created", "hello");
// With SimpleMessageConverter → TextMessage, body is "hello".

jmsTemplate.convertAndSend(
        "orders.created",
        new byte[] {1, 2, 3});
// With SimpleMessageConverter → BytesMessage.

jmsTemplate.convertAndSend(
        "orders.created",
        java.util.Map.of("orderId", "O-42", "status", "CREATED"));
// With SimpleMessageConverter → MapMessage.
~~~

**Common trap:** `convertAndSend("orders.created", new OrderCreated(...))` **does not automatically know to serialize a POJO to JSON**. With `SimpleMessageConverter`, a `Serializable` object may be converted to an `ObjectMessage` (depending on serializability); an incompatible object may throw `MessageConversionException`. `ObjectMessage` depends on the Java classpath, carries deserialization risks from untrusted data, and is usually unsuitable for cross-language communication.

If you want standard JSON between services, **configure a JMS `MessageConverter` for JSON** and align on schema/version/field names, rather than merely switching method names.

## 6. Mapping table of SimpleMessageConverter

This is the simple converter Spring uses by default when no other is configured:

| Java input | JMS Message typically created | Notes |
| --- | --- | --- |
| `String` | `TextMessage` | Does not parse/validate whether the string is valid JSON |
| `byte[]` | `BytesMessage` | Does not automatically encode a schema |
| `Map<String, ...>` | `MapMessage` | Values must be compatible with JMS MapMessage types; nested POJOs do not become JSON automatically |
| `Serializable` object not matching the above | `ObjectMessage` | Java serialization, class/schema coupling, and security risks |
| Unsupported object | Conversion exception | No default “JSON fallback” |

For **`MapMessage`**, JMS allows a set of primitive/basic types such as boolean, byte, short, char, int, long, float, double, String, and byte[]. Do not confuse it with nested JSON objects; a `Map<String, Object>` with nested `Map` or `List` will not automatically produce JSON via `SimpleMessageConverter`.

`receiveAndConvert(...)` is the reverse conversion on receive; it uses the template's converter. `@JmsListener` also depends on the **listener container factory's** message converter, so “the producer can convert” **does not prove** every listener can automatically deserialize the POJO. Both sides must share a compatible contract.

## 7. MessageCreator differs from MessagePostProcessor in timing

| | `MessageCreator` | `MessagePostProcessor` |
| --- | --- | --- |
| Primarily used in | `send(...)` | `convertAndSend(..., postProcessor)` |
| Callback parameter | `jakarta.jms.Session` | `jakarta.jms.Message` |
| Return value | Newly created `jakarta.jms.Message` | `jakarta.jms.Message` after modification (may be the same object) |
| Responsibility | Create body and JMS type, set headers/properties | Finalize headers/properties after converter creates the message |
| Does converter run beforehand? | **No**, because the application builds the JMS message | **Yes**, when using `convertAndSend` |
| Knows provider-assigned JMSMessageID? | **No**, because send has not happened yet | **No**, because post-processor still runs before send |

Equivalent examples by effect:

~~~java
// A. Manually create message in send callback.
jmsTemplate.send("orders.created", session -> {
    var m = session.createTextMessage("OrderCreated");
    m.setStringProperty("eventId", "evt-1001");
    return m;
});

// B. Let converter create message, then add property.
jmsTemplate.convertAndSend(
        "orders.created",
        "OrderCreated",
        m -> {
            m.setStringProperty("eventId", "evt-1001");
            return m;
        }
);
~~~

With the default converter, both A and B produce a `TextMessage` with body `OrderCreated` and property `eventId`. However, if you later switch the converter to JSON and pass a complex payload, **result B can change**, whereas A remains what your code manually constructs.

**Specifically:** the callback in `convertAndSend` has a `MessagePostProcessor` overload, not a lambda taking `Session`. Writing `session -> session.createTextMessage(...)` inside `convertAndSend` is the wrong model; it belongs in `send`.

## 8. Runnable Spring Boot 3.x example: comparing on the same broker

This lab creates **three messages** and sends them to **one queue** so you can observe the results directly:
- `send` creates a `TextMessage` manually.
- `convertAndSend` converts `String` to `TextMessage`.
- `convertAndSend` converts `Map` to `MapMessage`.

The example uses **Spring Boot 3.3.13** to demonstrate Spring 6.1's Jakarta JMS API; that version has reached end of open-source support, so new projects should choose a Boot branch currently supported under organizational policy. You need an external Artemis broker running, a user with send/consume permissions, and a queue `demo.send-modes` that exists or can be auto-created by the provider/broker.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'jms-send-modes'
~~~

### 8.2. application.yaml

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

**Provide the password via the `SPRING_ARTEMIS_PASSWORD` environment variable** of the startup process or a secret manager; do not commit it to Git. `user: demo` is only an example: use real credentials provisioned by the broker; if the broker does not enable authentication and has different connection conventions, adjust the configuration accordingly. Without a real broker, the application cannot prove send/receive worked.

### 8.3. Complete Java in a single file

Save to `src/main/java/example/jmsdemo/SendModesApplication.java`:

~~~java
package example.jmsdemo;

import java.util.Map;

import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class SendModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SendModesApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExamples(JmsTemplate template) {
        return args -> {
            String destination = "demo.send-modes";

            // 1. Manually construct a TextMessage using Session.
            template.send(destination, session -> {
                TextMessage message =
                        session.createTextMessage("hello from send");
                message.setStringProperty("source", "send");
                return message;
            });

            // 2. String is converted to TextMessage by SimpleMessageConverter.
            template.convertAndSend(
                    destination,
                    "hello from convertAndSend",
                    message -> {
                        message.setStringProperty(
                                "source", "convertAndSend");
                        return message;
                    }
            );

            // 3. Map is converted to MapMessage by SimpleMessageConverter.
            template.convertAndSend(
                    destination,
                    Map.of("orderId", "O-42", "status", "CREATED"),
                    message -> {
                        message.setStringProperty("source", "map");
                        return message;
                    }
            );
        };
    }
}

@Component
class RawMessageInspector {

    @JmsListener(destination = "demo.send-modes")
    public void inspect(Message message) throws JMSException {
        String source = message.getStringProperty("source");

        if (message instanceof TextMessage text) {
            System.out.printf("%s | TextMessage | %s%n",
                    source, text.getText());
        } else if (message instanceof MapMessage map) {
            System.out.printf("%s | MapMessage | orderId=%s%n",
                    source, map.getString("orderId"));
        } else {
            System.out.printf("%s | %s%n",
                    source, message.getClass().getSimpleName());
        }
    }
}
~~~

### 8.4. Running and reading the results

Once broker/credentials/queue are configured and a compatible Gradle wrapper is present:

~~~bash
./gradlew bootRun
~~~

The business lines that may appear:

~~~text
send | TextMessage | hello from send
convertAndSend | TextMessage | hello from convertAndSend
map | MapMessage | orderId=O-42
~~~

**This is an example of observable lines, not the complete stdout or a guaranteed order.** Listeners run asynchronously; an unready broker, credential errors, routing, multiple consumers, retries, or framework logs make timing and ordering vary. `ApplicationRunner` sends **every time the application starts**; this is demo behavior, not a pattern for emitting events from real business transactions.

**Verifiable conclusion:** the first two calls output the same JMS **`TextMessage` type** despite different creation paths; the third call produces a `MapMessage` chosen by the default converter. The queue and listener do not distinguish which send API created the message, because they only receive a **JMS Message**.

## 9. When you need to send POJOs as JSON

For events like `OrderCreated`, manually building JSON strings via `send` works, but easily duplicates serialization/schema logic. `convertAndSend` with a JSON converter is cleaner when many events share a common format.

### 9.1. Registering a JMS converter suitable for Spring 6.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConfiguration {

    @Bean
    MessageConverter jmsMessageConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        return converter;
    }
}
~~~

When using this class, the Jackson 2 dependency (`com.fasterxml.jackson.core:jackson-databind`) is needed at runtime; with Gradle, add:

~~~groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

In Spring Boot 3.x, a `MessageConverter` bean may be used by the **Boot auto-configured** `JmsTemplate` and listener factory, depending on version/conditions. If you **declare your own** `JmsTemplate` or a custom listener factory, you must inspect and attach the converter explicitly; do not assume every read path is configured identically.

### 9.2. Sending a domain object

~~~java
record OrderCreated(
        String eventId,
        String orderId,
        int schemaVersion
) {}

OrderCreated event =
        new OrderCreated("evt-1001", "O-42", 1);

jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("eventId", event.eventId());
            message.setStringProperty(
                    "contentType", "application/json");
            return message;
        }
);
~~~

This is a Java 17 snippet inside an application class/method that has `JmsTemplate` and a configured JSON converter. `MappingJackson2MessageConverter` turns the POJO into JSON inside a `TextMessage` when `MessageType.TEXT` is selected. `_type` is a JMS **property** helping the converter choose the Java type upon deserialization; the name, mapping, and trust boundary of type metadata must be agreed across applications before cross-service exchange.

**Interoperability limitation:** type IDs tied to internal Java class names are not an ideal cross-language contract. For broad exchange, standardize `eventType`, `schemaVersion`, and schema at the business layer, restrict allowed types, and configure the converter properly; never arbitrarily deserialize classes specified by external messages.

**No effect on `send`:** `jmsTemplate.send(..., session -> session.createTextMessage(json))` remains a `TextMessage` created by your code and **does not go through** the JSON converter bean. Changing the converter can affect `convertAndSend` and `receiveAndConvert`, but does not automatically rewrite manually built messages.

### 9.3. What should the consumer receive?

A producer creating a JSON `TextMessage` does not make every consumer automatically receive an `OrderCreated` record. The consumer must have a compatible converter/schema or parse JSON itself. In Spring:
- `@JmsListener` can receive raw `jakarta.jms.Message` to inspect directly.
- `@JmsListener` receiving `String`/POJO depends on Spring JMS listener argument resolution and the converter attached to the listener factory.
- Consumers in other languages need a schema/documentation and versioning policy; they do not understand Java class names.

**Keep the event envelope stable:** event ID, schema version, event type, business timestamp, and idempotency key belong in the contract, rather than relying on the provider-generated `JMSMessageID`.

## 10. Headers, properties, and JMS QoS: which API sets them?

### 10.1. Application metadata set before sending

Two valid ways:

~~~java
// send: set properties inside MessageCreator.
jmsTemplate.send("orders.events", session -> {
    TextMessage message = session.createTextMessage("OrderCreated");
    message.setStringProperty("eventId", "evt-1001");
    message.setJMSCorrelationID("checkout-42");
    return message;
});

// convertAndSend: set properties inside MessagePostProcessor.
jmsTemplate.convertAndSend(
        "orders.events", "OrderCreated",
        message -> {
            message.setStringProperty("eventId", "evt-1001");
            message.setJMSCorrelationID("checkout-42");
            return message;
        }
);
~~~

Applications should use `setStringProperty`, `setIntProperty`, and corresponding JMS property setters for client-owned metadata. `JMSCorrelationID` and `JMSReplyTo` are headers the application may set. `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSExpiration`, and provider-controlled headers are set by the provider on send; do not try setting them before send to alter policy.

**Key takeaway:** `MessageCreator` and `MessagePostProcessor` **both run before the provider send**. Therefore, neither **has a reliable `JMSMessageID` for the current send yet**. To trace upon receipt, log both the application-generated `eventId` and the provider-assigned `JMSMessageID` at the consumer or wherever post-send inspection is supported.

### 10.2. QoS belongs to JmsTemplate/provider, not the method name

~~~java
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(5);
jmsTemplate.setTimeToLive(60_000L);
~~~

This is a **bean configuration snippet**; a singleton `JmsTemplate` should not be continuously mutated per request/thread. To make `setDeliveryMode`, `setPriority`, and `setTimeToLive` on the template take explicit effect, you need `setExplicitQosEnabled(true)`. Otherwise, Spring may let the provider apply default/administered QoS. These setters affect **both `send` and `convertAndSend` paths** on that template.

- `PERSISTENT` is a request to protect messages across provider failures within standard and broker config limits; it **does not** mean the consumer has processed them.
- `priority` from 0 to 9 indicates priority, **without guaranteeing strict processing order**.
- `timeToLive` is in milliseconds; 0 typically means no TTL expiration, though messages remain subject to broker policies/resource limits.
- Choosing queue/topic and delivery mode is a **business/reliability decision**, not a special advantage exclusive to `send`.

**When different message groups need distinct QoS**, consider two clearly configured templates/factories or lower-level JMS provider policies under a unified standard; do not mutate a shared singleton template's state across concurrent threads just to prioritize one message.

## 11. Explicit destination vs. default destination

### 11.1. Destination names

~~~java
jmsTemplate.send("order.commands", session ->
        session.createTextMessage("CreateInvoice"));

jmsTemplate.convertAndSend("order.events", "OrderCreated");
~~~

These two calls send to **two different destinations** solely because of the parameter name. The string name is resolved by the template's `DestinationResolver`; by default it is usually a queue when `pubSubDomain=false`. Queue/topic names must match broker routing/authorization.

### 11.2. Default destination

~~~java
jmsTemplate.setDefaultDestinationName("orders.queue");

// No need to pass the target name on each call.
jmsTemplate.send(session ->
        session.createTextMessage("Created"));

jmsTemplate.convertAndSend("Created");
~~~

When no default destination is configured, overloads **that omit the destination** may throw an exception because they do not know where to send. Do not confuse `convertAndSend(String destinationName, Object payload)` with `convertAndSend(Object payload)`: parameter count/order determines whether a `String` is interpreted as destination or payload.

### 11.3. Multiple queues and topics

If an application sends to both queues and topics, do not expect a name ending in `...topic` to make `JmsTemplate` switch `pubSubDomain`. Create separate templates/resolvers or pass an explicit `Destination`, aligning policies with the broker. This applies to **both `send` and `convertAndSend`**.

## 12. Transactions, errors, and retries: neither API changes the JMS contract

### 12.1. Successful send is not successful processing

~~~text
send / convertAndSend
    → create JMS Message
    → provider receives/sends
    → broker stores/routes message
    → consumer receives
    → handler writes DB or calls another system
    → consumer ACK/JMS commit
~~~

When `JmsTemplate` returns, the application knows the **send operation under the provider's contract** completed (or enlisted in an active transaction); it **does not know** that downstream business side effects committed. In particular, inside a transaction, the send call can complete **before the actual commit**.

### 12.2. Sending in a local JMS transaction

If two send calls (from either group) must commit/roll back together at the broker, you need an intentional transaction scope, such as `JmsTransactionManager` and `@Transactional`. Spring illustrative snippet:

~~~java
@Bean
org.springframework.jms.connection.JmsTransactionManager
jmsTransactionManager(jakarta.jms.ConnectionFactory connectionFactory) {
    return new org.springframework.jms.connection.JmsTransactionManager(
            connectionFactory);
}
~~~

Then, in a Spring-managed service:

~~~java
@org.springframework.transaction.annotation.Transactional(
        transactionManager = "jmsTransactionManager")
public void publishTwo(JmsTemplate template) {
    template.send("orders.events", session ->
            session.createTextMessage("OrderCreated"));
    template.convertAndSend("orders.audit", "Created");
}
~~~

This is an **illustrative snippet inside a class with Spring bean lifecycle**, not a standalone `main` program. Ensure the same `ConnectionFactory`/transaction manager is used and the method is invoked properly through the Spring proxy; self-invocation bypassing the proxy will not trigger `@Transactional` as intended.

**Limitation:** a JMS local transaction only groups JMS resources belonging to that transaction; it **does not automatically include** DB, HTTP, email, or two different JMS providers. For the “write DB and emit event” use case, consider transactional outbox, retries with a stable event ID, and idempotent consumers; do not assume using `convertAndSend` brings the DB transaction along automatically.

### 12.3. Accurately classifying errors

| Scenario | `send` | `convertAndSend` | Handling approach |
| --- | --- | --- | --- |
| Cannot create JMS Message | Error in `MessageCreator` | Error in converter | Fix contract/types and test |
| Invalid custom metadata | Error in message-creating callback | Error in `MessagePostProcessor` | Validate properties/schema before send |
| Cannot resolve destination | May fail before send | Same | Fix name/resolver/routing |
| Provider/broker unreachable | `JmsException` | Same | Bounded retry/backoff, monitor network |
| Message received by broker but ack never returned | Result may be uncertain | Same | Do not generate a new business ID when retrying the same event |
| Consumer fails after send | Not immediately reported to publisher via send return | Same | DLQ, redelivery, idempotent consumer, and tracing |

`MessageConversionException` in `convertAndSend` is usually a **data/format incompatibility** error; retrying the exact same payload rarely fixes the converter. With network timeouts during send, the broker **may have received** the message while the producer cannot be certain; retrying can produce duplicate messages.

### 12.4. Once-only at the business layer

Suppose the producer must retry because no response was received:

~~~text
eventId=evt-1001
     send attempt A → broker stores message A → connection drops before response
     send attempt B → broker stores message B → producer sees success

consumer receives A and B
    → must not create two invoices for the same eventId
~~~

`JMSMessageID` can differ between the two sends; use an application-assigned `eventId` kept stable across retries, DB unique constraints/idempotency, and appropriate transactions. `send` and `convertAndSend` **have no magical difference** at this step.

## 13. Understanding what to log when debugging JMS

In a real request, log safe information:

| When | Useful data |
| --- | --- |
| Before send | `eventId`, destination, event type, schema version, payload size (do not log secrets) |
| During conversion | Java payload type, converter class, resulting JMS message type |
| After send | Success/failure, latency, transaction context; do not assume consumer ACK occurred |
| At consumer | `JMSMessageID`, `eventId`, `JMSCorrelationID`, delivery count, redelivered flag, processing success/failure |
| On retry/DLQ | Error category, attempts, first failure, destination, and replay policy |

**Note:** `MessagePostProcessor` runs before send; reading `message.getJMSMessageID()` there may yield `null` or an old ID, not the ID assigned by the provider for the ongoing send. If you need the ID after send, consider a JMS API path or callback observable after provider send, while understanding transactions/lifecycle and not breaking Spring resource management.

## 14. Distinguishing JmsTemplate from other “Message” APIs

Several names look very similar:

| API / class | Nature |
| --- | --- |
| `org.springframework.jms.core.JmsTemplate` | Works directly with `jakarta.jms.Message` and JMS converters |
| `org.springframework.jms.core.MessageCreator` | Creates a JMS Message from a JMS `Session` |
| `org.springframework.jms.core.MessagePostProcessor` | Modifies a JMS Message after conversion, before send |
| `org.springframework.jms.support.converter.MessageConverter` | Converts Java object ↔ JMS Message |
| `jakarta.jms.MessageProducer` | JMS API-level producer; distinct from `JmsTemplate` |
| `jakarta.jms.JMSProducer` | JMS simplified API used with `JMSContext` |
| `org.springframework.messaging.Message<?>` | Generic Spring Messaging message abstraction; **not a JMS Message** |
| `org.springframework.jms.core.JmsMessagingTemplate` | Spring Messaging bridge; its `send/convertAndSend` signatures differ |
| `org.springframework.jms.core.JmsClient` | Fluent API introduced in newer Spring Framework versions; does not replace the `JmsTemplate` signatures in this lesson |

If your IDE suggests `convertAndSend(String, Object, Map<String,Object>)`, check whether you are using **`JmsMessagingTemplate` / `org.springframework.messaging`** instead of `JmsTemplate`. On `JmsTemplate`, the post-processing overload takes **`MessagePostProcessor`**, not a `Map` of headers from the Spring Messaging API.

**Do not do this:**

~~~java
// WRONG in meaning: a JMS Message object is not a MessageCreator.
// jmsTemplate.send("orders.queue", existingJmsMessage);

// WRONG in expectation: convertAndSend is not guaranteed to pass through
// a pre-built JMS Message untouched while bypassing MessageConverter.
// jmsTemplate.convertAndSend("orders.queue", existingJmsMessage);
~~~

When you have a JMS Message to send, the natural `JmsTemplate` approach is to **create it from the `Session` provided by the callback**, or consider lower-level APIs within a controlled transaction scope. When starting with a Java object, use `convertAndSend` with a suitable converter.

## 15. When to choose send vs. convertAndSend?

| Need | Usually sensible choice | Reason |
| --- | --- | --- |
| Send a simple String | `convertAndSend` | Less code, default converter creates TextMessage |
| Send a Map with basic JMS types | `convertAndSend` | Converter creates MapMessage |
| Send a JSON POJO with a standardized converter | `convertAndSend` | Single place owning schema/serialization |
| Send a TextMessage with special properties/headers | Either | `send` builds manually; `convertAndSend` pairs with post-processor |
| Send a BytesMessage with custom byte layout | `send` | Exact control over body and message type |
| Need to set JMSReplyTo/correlation, selectors | Either | Set before send in creator or post-processor |
| Want to avoid depending on a changing converter | `send` | Body/type are decided inside the callback |
| Want consistent JSON across multiple publishers | `convertAndSend` + custom converter | Reduces duplication and eases versioning |
| Need retry/outbox/exactly-once business effect | **Additional design at business layer** | Both are only send operations |

**Pragmatic rule:** choose based on **who owns the message contract**. If the contract is defined as a **Java payload + standardized converter**, `convertAndSend` is more natural. If the contract demands exact control over every byte/JMS field, `send` is clearer. Both must follow a consistent policy for destination, QoS, transactions, idempotency, and observability.

## 16. Common mistakes

1. **“convertAndSend converts every object to JSON automatically.”** No; inspect the actual `MessageConverter`.
2. **“send and convertAndSend are two delivery modes.”** No; both create/send the same JMS message types, differing only in construction.
3. **“MessageCreator takes a Java Object.”** It takes a JMS `Session` and returns a JMS `Message`.
4. **“MessagePostProcessor runs after the broker send.”** It runs **before** provider send, after conversion.
5. **“A Map is JSON.”** `SimpleMessageConverter` typically creates a `MapMessage`, with JMS type restrictions.
6. **“Non-Serializable POJOs can still be sent automatically.”** The default converter may throw a conversion error.
7. **“Creating a separate Connection/Session inside MessageCreator is better.”** This violates the template-managed resource scope.
8. **“convertAndSend is definitely faster/slower than send.”** Measure serialization/caching/broker overhead; do not guess from the API name.
9. **“Installing a JSON converter only changes outbound.”** It may also change inbound conversion if listeners/templates share config; test compatibility.
10. **“QoS settings on JmsTemplate always take effect.”** For explicit QoS setters, verify `setExplicitQosEnabled` and admin overrides.
11. **“JMSMessageID is available in MessagePostProcessor.”** Not yet: the provider assigns it upon send.
12. **“Once convertAndSend returns, the listener has processed it.”** Sending does not replace consumer ACK or DB commit.
13. **“Having a DB transaction makes JMS roll back automatically.”** JMS transactions and DB transactions are separate unless coordinated by design.
14. **“Using `@JmsListener` with `String` decodes every bytes/map/JSON payload.”** Depends on converter, method signature, and container factory.
15. **“If the destination name has `.topic`, Spring treats it as a topic.”** String names do not automatically change `pubSubDomain`.
16. **“Mutating singleton JmsTemplate QoS per request.”** This can affect concurrent publishers; configure templates with stable policies.

## 17. Hands-on verification in sequence

**Exercise 1 — Two ways, one body:** send the string `"hello"` to a queue using `send` and `convertAndSend`; have the consumer verify both are `TextMessage` under the default converter.

**Exercise 2 — Post processor:** add `eventId` and `JMSCorrelationID` using both approaches and read them at the consumer. Try reading `JMSMessageID` inside creator/post-processor to see why it is not yet guaranteed.

**Exercise 3 — Conversion table:** pass `String`, `byte[]`, and `Map` through `convertAndSend`; have the consumer receive raw `Message` and log the actual type. Try a map containing a nested object and record the exception type.

**Exercise 4 — Swap converter:** register `MappingJackson2MessageConverter`, send an `OrderCreated` record, and observe the JSON `TextMessage`. Compare type metadata/schema before and after; test listener conversion.

**Exercise 5 — Missing default destination:** try `send(MessageCreator)` and `convertAndSend(Object)` without configuring a default destination; explain the failure, then fix it with an explicit destination name.

**Exercise 6 — QoS:** enable `setExplicitQosEnabled(true)`, configure persistent/priority/TTL, and test both send approaches. Inspect broker headers after send to prove the shared policy applies.

**Exercise 7 — Transaction:** under `JmsTransactionManager`, send two messages using the two APIs in one transaction and force an exception before commit; verify the broker has neither uncommitted message. Compare with two sends without a transaction scope.

**Exercise 8 — Fault injection:** make the broker unavailable while sending; distinguish a conversion error (before network) from a provider error (after send attempt), and see how retries can create duplicates.

**Exercise 9 — Consumer idempotency:** resend the same `eventId` twice via the two different APIs; prove a DB unique constraint protects against duplicate business processing.

**Exercise 10 — Separate queue/topic:** same payload but two different destinations; verify resolver/`pubSubDomain` and consumer/subscription counts before concluding delivery is right.

## 18. Comprehension self-check

Be able to answer these questions before moving to advanced JMS lessons:

- Can you state accurately that `send` takes `MessageCreator` to build a `jakarta.jms.Message`, whereas `convertAndSend` takes a Java object and uses `MessageConverter`?
- Why does `String` go through the default converter to become `TextMessage` and `Map` become `MapMessage`, while a POJO does not default to JSON?
- When you need to set `eventId` property and `JMSCorrelationID`, where do you set them in each approach?
- Why can neither creator nor post-processor guarantee reading the newly assigned `JMSMessageID`?
- When do destination-omitting overloads fail?
- How do you prove the listener and publisher are using compatible converters?
- Can you explain how the same TTL/delivery mode/transaction policy applies to both method groups?
- When the broker drops the response, why do both approaches risk duplicates and require a business event ID?
- Can you run the Boot 3.x example with a test broker and observe all three created message types?
- Do you know when to choose a manual callback instead of defining a shared converter?

**Desired outcome:** read any `JmsTemplate` call and clearly answer three questions: “**Who creates the JMS Message? What is the actual type/body? At what moment is metadata set?**”. Once these three are clear, choosing `send` or `convertAndSend` becomes a verifiable, explainable engineering decision rather than guessing by method name.

## 19. Primary references

1. [Spring Framework Reference — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate.send`, `convertAndSend`, `MessageCreator`, `MessagePostProcessor`, and Spring's examples.
2. [Spring Framework 6.1 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html): exact overloads and exceptions.
3. [Spring Framework 6.1 — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): mapping String/byte[]/Map/Serializable to JMS.
4. [Spring Framework 6.1 — JMS converter package](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/support/converter/package-summary.html): `MessageConverter`, `MappingJackson2MessageConverter`, `MessageConversionException`.
5. [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, connection/session management, destinations, transactions.
6. [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html): Artemis starter, auto-configuration, template/converter, and listener.
7. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): definition of JMS Message, producer, delivery mode, transactions, and metadata.