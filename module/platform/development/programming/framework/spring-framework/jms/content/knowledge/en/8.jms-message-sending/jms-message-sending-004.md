# Setting Typed Properties on a Message (Spring Framework JMS)

**Context:** Spring Framework - jms → Message Sending.

## 1. What Are Typed Properties and What Are They For?

In **JMS (Java Message Service, now part of Jakarta Messaging)**, a message has three sections of information: **standard headers**, **properties**, and **body**. The body carries business data; properties hold metadata as **typed name-value pairs**. For example, an ordering application sends the body `"order-42"` with attached properties:

~~~text
Message
├── Headers: JMSMessageID, JMSDestination, JMSCorrelationID, ...
├── Properties:
│   ├── eventType      (String)  = "ORDER_CREATED"
│   ├── priorityLevel  (int)     = 7
│   ├── express        (boolean) = true
│   ├── amountMinor    (long)    = 125000
│   └── attempt        (int)     = 1
└── Body: TextMessage("order-42")
~~~

Properties let consumers inspect metadata without parsing the body and specifically support **JMS message selectors**. For example, a consumer that only wants high-priority, express order-created events:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5 AND express = TRUE
~~~

The **written type** determines whether a selector can compare values properly: an `int` `priorityLevel = 7` differs from a `String` `priorityLevel = "7"`, even if they look identical when logged.

Key facts to remember:

- Properties live on the **JMS Message**, not as methods on `JmsTemplate` or broker settings.
- The producer sets properties **before sending**; the consumer reads them from the received message.
- A business property like `priorityLevel` **does not automatically set** the JMS standard header `JMSPriority`.
- Properties help the broker filter messages; they **do not** create queues, trigger retries automatically, or guarantee business success.

Examples in this lesson use **Java 17+**, **Spring Framework 6.x / Spring Boot 3.x**, and the `jakarta.jms.*` API. Legacy JMS applications may use `javax.jms.*`; choose consistent API libraries and provider clients and never mix the two incompatible namespaces.

## 2. The Eight Standard JMS Property Types

The `jakarta.jms.Message` interface supports property values of exactly **eight types**:

| Type | Setter | Getter | Illustrative value |
| --- | --- | --- | --- |
| `boolean` | `setBooleanProperty` | `getBooleanProperty` | `true` |
| `byte` | `setByteProperty` | `getByteProperty` | `(byte) 3` |
| `short` | `setShortProperty` | `getShortProperty` | `(short) 84` |
| `int` | `setIntProperty` | `getIntProperty` | `7` |
| `long` | `setLongProperty` | `getLongProperty` | `125_000L` |
| `float` | `setFloatProperty` | `getFloatProperty` | `0.75f` |
| `double` | `setDoubleProperty` | `getDoubleProperty` | `0.125d` |
| `String` | `setStringProperty` | `getStringProperty` | `"ORDER_CREATED"` |

Every setter/getter above takes the **property name** as its first parameter. On a newly created, writable `Message message`:

~~~java
message.setStringProperty("eventType", "ORDER_CREATED");
message.setIntProperty("priorityLevel", 7);
message.setBooleanProperty("express", true);
message.setLongProperty("amountMinor", 125_000L);
message.setByteProperty("shard", (byte) 3);
message.setShortProperty("regionCode", (short) 84);
message.setFloatProperty("score", 0.75f);
message.setDoubleProperty("ratio", 0.125d);
~~~

This is an **excerpt**; you must create `message` from a `jakarta.jms.Session` beforehand. Literals like `125_000L`, `0.75f`, and `0.125d` follow Java syntax; the message itself stores only the corresponding value and type.

There is no `setCharProperty`, `setBytesProperty`, `setDateProperty`, or `setBigDecimalProperty`. Do not confuse these with `MapMessage` or `StreamMessage`, which set fields **inside the body**, distinct from message properties.

### 2.1. Which Objects Does setObjectProperty Accept?

Two additional methods:

~~~java
message.setObjectProperty("attempt", Integer.valueOf(1));
Object attempt = message.getObjectProperty("attempt");
~~~

By standard JMS rules, `setObjectProperty(String, Object)` only permits storing **Boolean, Byte, Short, Integer, Long, Float, Double, and String**—namely the primitive wrappers and String. `getObjectProperty` returns an object of the stored type, such as an `Integer` if the producer passed `Integer.valueOf(1)` or called `setIntProperty`.

~~~java
Object attempt = message.getObjectProperty("attempt");
if (attempt instanceof Integer value) {
    System.out.println("attempt=" + value);
}
~~~

Once the `attempt` property is set to 1 as an int/Integer, the illustrative line prints:

~~~text
attempt=1
~~~

It is **invalid** to store arbitrary objects directly—such as `UUID`, `BigDecimal`, `Instant`, `LocalDate`, DTOs/POJOs, enums, or `byte[]`—using `setObjectProperty`. The JMS provider must reject types outside the allowed list; there is no automatic serialization of arbitrary objects at the property level.

To store a UUID or timestamp as metadata, convert it intentionally:

~~~java
import java.time.Instant;
import java.util.UUID;

// Explicit schema-defined value conversions:
message.setStringProperty("eventId", UUID.randomUUID().toString());
message.setLongProperty("occurredAtMs", Instant.now().toEpochMilli());
~~~

In real systems, generate `eventId` and `occurredAtMs` **once per event** before sending; avoid generating a new ID on every retry if the business contract needs duplicate detection.

For monetary amounts, prefer a `long` representing **minor units** (such as the smallest currency unit defined by the system) or convert decimals to a standardized String format; never use `float/double` for exact monetary calculations.

## 3. Distinguishing Properties from JMS Headers and Body

Names like `JMSCorrelationID`, `JMSMessageID`, and `JMSPriority` are **standard headers**. Even though they live on the Message, they are not regular application properties.

| Want to set | Which API to use? | Meaning |
| --- | --- | --- |
| `eventType` | `message.setStringProperty("eventType", "...")` | Event type for selectors |
| `priorityLevel` | `message.setIntProperty("priorityLevel", 7)` | **Business** priority |
| `JMSCorrelationID` | `message.setJMSCorrelationID("corr-42")` | Request/reply correlation |
| `JMSReplyTo` | `message.setJMSReplyTo(destination)` | Where replies are expected |
| `JMSPriority` | Producer QoS / Spring explicit QoS | JMS message delivery priority |
| `TextMessage` body | `session.createTextMessage("order-42")` | Business payload |

Do not replace a standard header by manually setting a property with the same name:

~~~java
// Misguided intent: using property API for a standard header name.
message.setStringProperty("JMSCorrelationID", "corr-42");

// Correct: use the dedicated header API.
message.setJMSCorrelationID("corr-42");
~~~

The first line is an **anti-pattern** and may be rejected by providers because of the reserved namespace; never use it to set correlation IDs.

A `MapMessage` also has setters like `mapMessage.setInt("quantity", 3)`, but those are **fields inside the body**. Selectors cannot access them. If the broker needs to filter on `quantity`, promote the corresponding metadata into a property:

~~~java
message.setIntProperty("quantity", 3); // property usable in selectors
~~~

Setting properties is a **contract design decision**, not an automatic step that mirrors an entire JSON or MapMessage body into dozens of properties.

## 4. Property Names: Syntax, Case Sensitivity, and Namespaces

Property names must follow **message selector identifier** rules (similar to Java identifiers, with reserved keywords). Avoid `null`, empty names, names starting with digits, spaces, or hyphens. Avoid colliding with keywords `NULL`, `TRUE`, `FALSE`, `NOT`, `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`, `IS`, and `ESCAPE`.

Good names:

~~~text
eventType
priorityLevel
express
amountMinor
attempt
tenantId
traceId
occurredAtMs
~~~

These names work cleanly in selectors. Property names are **case-sensitive**: `eventType` differs from `EventType`. Never rename a property on only one side (producer or consumer).

Mind the namespaces:

- `JMSX...` is reserved by **Jakarta Messaging** for standard properties such as `JMSXGroupID` and `JMSXGroupSeq`; do not invent new application names with this prefix.
- `JMS_...` is reserved for **provider-specific properties**. Do not use it for ordinary business metadata.
- Standard JMS headers like `JMSCorrelationID` have dedicated getters/setters and do not appear as ordinary application properties.

Some `JMSX` properties (e.g., `JMSXDeliveryCount`) are assigned/managed by the provider per contract. Do not spoof delivery counts with arbitrary setters. To track business retry attempts, use a dedicated name like `attempt` with clear semantics, distinct from broker redelivery.

## 5. Type Conversion Rules When Reading

JMS defines a conversion table **when calling getters**. If a property was written with a type in the left column, it can be read using the same-type getter or specific widening/conversion getters as follows:

| Written as | Aside from same-type getter, readable via |
| --- | --- |
| `boolean` | `getStringProperty` |
| `byte` | `getShortProperty`, `getIntProperty`, `getLongProperty`, `getStringProperty` |
| `short` | `getIntProperty`, `getLongProperty`, `getStringProperty` |
| `int` | `getLongProperty`, `getStringProperty` |
| `long` | `getStringProperty` |
| `float` | `getDoubleProperty`, `getStringProperty` |
| `double` | `getStringProperty` |
| `String` | Primitive getters if the String is parseable |

Valid example:

~~~java
message.setIntProperty("attempt", 2);

int exact = message.getIntProperty("attempt");      // 2
long widened = message.getLongProperty("attempt");  // 2L
String text = message.getStringProperty("attempt"); // "2"
~~~

Invalid example:

~~~java
message.setLongProperty("amountMinor", 125_000L);
int amount = message.getIntProperty("amountMinor");
~~~

Narrowing from `long` to `int` is **not** allowed in the JMS conversion table. An incompatible getter may throw `MessageFormatException`, even if the runtime value happens to fit within `int` bounds.

For Strings, JMS allows parsing into primitives when the text is valid:

~~~java
message.setStringProperty("attempt", "2");
int parsed = message.getIntProperty("attempt"); // 2

message.setStringProperty("attempt", "two");
int broken = message.getIntProperty("attempt"); // parse failure
~~~

The last line is **intentionally an error example**. When the String is not a valid numeric representation, numeric getters may throw `NumberFormatException`. Therefore, if data is logically numeric, send it with `setIntProperty`/`setLongProperty` from the start.

### 5.1. Selectors Do Not Use the Getter Conversion Table

This is an essential rule to remember. With:

~~~java
message.setStringProperty("priorityLevel", "7");
~~~

the selector:

~~~sql
priorityLevel >= 5
~~~

**does not automatically parse `"7"` into an int**. JMS selectors compare using the **stored type**, unlike Java's `getIntProperty("priorityLevel")`.

For numeric comparisons in selectors:

~~~java
message.setIntProperty("priorityLevel", 7);
~~~

And for boolean filtering:

~~~java
message.setBooleanProperty("express", true);
~~~

the selector uses:

~~~sql
priorityLevel >= 5 AND express = TRUE
~~~

Setting `express` via `setStringProperty("express", "true")` stores a String, which does not carry boolean semantics in selectors. Selector string literals use **single quotes**, such as `eventType = 'ORDER_CREATED'`.

## 6. Sending Messages with Typed Properties Using Plain JMS API

In the Jakarta Messaging classic API, a producer creates a `Message` from a `Session`, sets properties, and sends it:

~~~java
package com.example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicTypedPropertySender {

    private ClassicTypedPropertySender() {}

    public static void send(ConnectionFactory factory) throws JMSException {
        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            Queue queue = session.createQueue("demo.orders.typed");

            try (MessageProducer producer = session.createProducer(queue)) {
                TextMessage message =
                        session.createTextMessage("order-42");
                message.setStringProperty("eventType", "ORDER_CREATED");
                message.setIntProperty("priorityLevel", 7);
                message.setBooleanProperty("express", true);
                message.setLongProperty("amountMinor", 125_000L);
                message.setObjectProperty(
                        "attempt", Integer.valueOf(1));
                producer.send(message);
            }
        }
    }
}
~~~

This is a **class without a `main` method**; it compiles against the JMS API, though actually sending requires a real provider-specific `ConnectionFactory`, broker, credentials, and a valid queue. `Connection.start()` is required for message delivery in a classic API consumer, not for a producer sending messages.

The simplified `JMSContext` API works similarly:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

// factory is a configured ConnectionFactory.
try (JMSContext context = factory.createContext()) {
    Queue queue = context.createQueue("demo.orders.typed");
    TextMessage message = context.createTextMessage("order-42");
    message.setIntProperty("priorityLevel", 7);
    message.setStringProperty("eventType", "ORDER_CREATED");

    context.createProducer().send(queue, message);
}
~~~

This is an excerpt inside a method, not a standalone file. Calling `createQueue` only creates a logical destination handle; provisioning the queue on the broker may require separate setup.

## 7. The Spring JMS Way: MessagePostProcessor

Spring applications commonly use `JmsTemplate.convertAndSend(...)`. The template invokes a `MessageConverter` to turn the payload into a JMS Message, then optionally lets you customize the message before sending via **`org.springframework.jms.core.MessagePostProcessor`**:

~~~java
import org.springframework.jms.core.JmsTemplate;

// jmsTemplate is an injected Spring bean.
jmsTemplate.convertAndSend(
        "demo.orders.typed",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("priorityLevel", 7);
            message.setBooleanProperty("express", true);
            message.setLongProperty("amountMinor", 125_000L);
            message.setObjectProperty("attempt", Integer.valueOf(1));
            return message;
        });
~~~

Sequence:

1. `"demo.orders.typed"` is the explicitly passed destination; `"order-42"` is the payload.
2. The default converter turns the `String` into a `TextMessage`.
3. `MessagePostProcessor` receives a `jakarta.jms.Message` **already created and still writable**.
4. The callback sets properties and returns the message.
5. `JmsTemplate` sends the message via the JMS provider.

Do not confuse `org.springframework.jms.core.MessagePostProcessor` with an interface handling `org.springframework.messaging.Message<?>`. Those belong to two different abstraction layers. The snippet above sets **native JMS properties** on the JMS Message object.

### 7.1. Using MessageCreator When You Want to Construct the Message Yourself

~~~java
jmsTemplate.send("demo.orders.typed", session -> {
    var text = session.createTextMessage("order-42");
    text.setStringProperty("eventType", "ORDER_CREATED");
    text.setIntProperty("priorityLevel", 7);
    text.setBooleanProperty("express", true);
    return text;
});
~~~

This snippet uses a `MessageCreator` callback, where you build the JMS Message directly with `Session`. This is useful when you want a `BytesMessage`, `MapMessage`, or custom message-building logic.

| Need | Choice |
| --- | --- |
| String/byte[]/converter-supported payload, just attach properties | `convertAndSend(..., MessagePostProcessor)` |
| Build message manually, choose exact message type | `send(..., MessageCreator)` |
| Not using Spring | JMS `Session` or `JMSContext` and producer |
| Need consumer-side filtering | Contract-compliant typed properties paired with a selector |

**Note:** typed properties do not determine the `Destination`, ack mode, or transactions. Those settings still reside on `JmsTemplate`, the container, `ConnectionFactory`, and the broker.

## 8. Runnable Example: Java 17+, Spring Boot 3.x, Apache ActiveMQ Artemis

A complete example with a producer setting multiple typed properties and a consumer filtering with a selector and reading them back.

### 8.1. Setup

Generate a Maven project from [Spring Initializr](https://start.spring.io/) with Java 17+, group `com.example`, artifact `jms-typed-properties`, and dependency **Spring for Apache ActiveMQ Artemis** (`org.springframework.boot:spring-boot-starter-artemis`). Start an external Artemis broker on `tcp://localhost:61616` with send/consume permissions for queue `demo.orders.typed`. The queue must be provisioned or the broker configured for appropriate auto-creation.

Set environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD`. Create `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`native` connects to an already-running broker; it does **not** start an embedded broker.

Create `src/main/java/com/example/JmsTypedPropertiesApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
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
public class JmsTypedPropertiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTypedPropertiesApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            template.convertAndSend(
                    "demo.orders.typed",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        message.setIntProperty("priorityLevel", 7);
                        message.setBooleanProperty("express", true);
                        message.setLongProperty(
                                "amountMinor", 125_000L);
                        message.setObjectProperty(
                                "attempt", Integer.valueOf(1));
                        return message;
                    });
            System.out.println("SENT order-42");
        };
    }
}

@Component
class TypedOrderConsumer {

    @JmsListener(
            destination = "demo.orders.typed",
            selector = "eventType = 'ORDER_CREATED' "
                    + "AND priorityLevel >= 5 AND express = TRUE")
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("BODY=" + textMessage.getText());
        System.out.println("eventType="
                + message.getStringProperty("eventType"));
        System.out.println("priorityLevel="
                + message.getIntProperty("priorityLevel"));
        System.out.println("priorityAsLong="
                + message.getLongProperty("priorityLevel"));
        System.out.println("express="
                + message.getBooleanProperty("express"));
        System.out.println("amountMinor="
                + message.getLongProperty("amountMinor"));
        System.out.println("attemptIsInteger="
                + (message.getObjectProperty("attempt")
                        instanceof Integer));
        System.out.println("hasUnknownProperty="
                + message.propertyExists("unknownProperty"));
    }
}
~~~

Each Java file has one public class matching the filename; the package-private listener class is still picked up by Spring component scanning. Spring Boot with the Artemis starter and proper configuration sets up the JMS infrastructure and `JmsTemplate`. The consumer receives a **raw `jakarta.jms.Message`**, so it reads properties with standard JMS getters rather than through a JSON converter.

### 8.2. Run Command and Output

In the project directory:

~~~bash
mvn spring-boot:run
~~~

On Windows, if using the Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

In a clean run with working broker/destination/credentials, no leftover messages, and no competing consumers, the expected business lines are:

~~~text
SENT order-42
BODY=order-42
eventType=ORDER_CREATED
priorityLevel=7
priorityAsLong=7
express=true
amountMinor=125000
attemptIsInteger=true
hasUnknownProperty=false
~~~

Other startup logs will also appear. Because the listener runs asynchronously, `SENT order-42` may appear before or after the consumer log block; the lines within a single `receive()` invocation follow the code order. This is **conditionally expected output**, not proof that a broker/Maven was run during authoring.

Explanation:

- The default message converter turns `"order-42"` into a `TextMessage`.
- The callback sets `eventType` as String, `priorityLevel` as int, and `express` as boolean, allowing the selector to match.
- `getLongProperty("priorityLevel")` returns 7 because `int → long` widening is permitted by JMS.
- `attempt` was stored as an `Integer`, so `instanceof Integer` is true.
- `propertyExists("unknownProperty")` returns false because the producer never set that property.

## 9. Safely Reading and Inspecting Properties on the Consumer

The `Message` API also provides:

~~~java
boolean propertyExists(String name) throws JMSException;
Object getObjectProperty(String name) throws JMSException;
java.util.Enumeration<?> getPropertyNames() throws JMSException;
~~~

Example snippet on a received message:

~~~java
if (message.propertyExists("attempt")) {
    Object value = message.getObjectProperty("attempt");
    if (value instanceof Integer attempt) {
        System.out.println("attempt=" + attempt);
    }
}

var propertyNames = message.getPropertyNames();
while (propertyNames.hasMoreElements()) {
    String name = (String) propertyNames.nextElement();
    System.out.println(
            name + "=" + message.getObjectProperty(name));
}
~~~

The iteration order of names returned by `getPropertyNames()` is **not guaranteed by the JMS standard**. Do not assert fixed stdout ordering from that loop. This API enumerates properties; it does **not** include standard headers like `JMSMessageID`.

When a property does not exist:

~~~java
boolean exists = message.propertyExists("traceId"); // false
Object value = message.getObjectProperty("traceId"); // null
String text = message.getStringProperty("traceId");  // null
~~~

These results assume the message truly lacks the `traceId` property. **Do not assume** every primitive getter returns 0 or false for missing properties: check `propertyExists` before reading required properties. For untrusted messages, also validate names, types, value ranges, and the business schema.

### 9.1. Received Properties Are Read-Only

A newly created message on the producer has writable properties. Once a consumer receives the message, its properties become **read-only**. Therefore:

~~~java
// incoming is a message just received by the consumer.
incoming.setIntProperty("attempt", 2);
~~~

can throw `MessageNotWriteableException`. The `clearProperties()` method clears **all properties** and makes the property section writable again; it does **not** clear the body or standard headers.

However, you should not call `clearProperties` on a received message just to edit one field, because doing so wipes out all other metadata. When forwarding or replying, it is usually cleaner to **create a new message** and copy the required fields with explicit types/contracts. Mutating a received Java object also does not update the original message on the broker or re-send it automatically.

## 10. Selectors Operate on the Written Property Types

A JMS selector is a restricted SQL92-like expression evaluated over **properties and a few permitted standard headers**. It **cannot** read fields inside JSON, a `MapMessage`, or a String body.

| Written property | Selector | Interpretation |
| --- | --- | --- |
| `setIntProperty("priorityLevel", 7)` | `priorityLevel >= 5` | Correct numeric comparison |
| `setStringProperty("priorityLevel", "7")` | `priorityLevel >= 5` | Does not auto-parse String to number |
| `setBooleanProperty("express", true)` | `express = TRUE` | Boolean comparison |
| `setStringProperty("express", "true")` | `express = TRUE` | Type mismatch; does not match as Boolean |
| `setStringProperty("eventType", "ORDER_CREATED")` | `eventType = 'ORDER_CREATED'` | Correct String comparison |
| Missing `tenantId` | `tenantId IS NULL` | Missing property evaluates to NULL |
| Missing `tenantId` | `tenantId = 'A'` | Evaluates to UNKNOWN, does not match |

Selector string literals use **single quotes**. Identifiers are case-sensitive. If a literal contains a single quote, escape it per selector rules using doubled single quotes. Never concatenate unvalidated user input directly into a selector.

With `@JmsListener`:

~~~java
@JmsListener(
    destination = "demo.orders.typed",
    selector = "eventType = 'ORDER_CREATED' AND priorityLevel >= 5")
public void consume(Message message) {
    // Only messages matching the selector are delivered to this listener.
}
~~~

This is an excerpt; compiling requires imports and an enclosing class. The selector lives on the **consumer side**, yet the producer is responsible for setting the **right metadata types**. A mismatch between producer and selector can prevent the consumer from receiving messages without necessarily throwing an exception in the listener method.

Only a restricted set of standard headers may be referenced in selectors (e.g., `JMSCorrelationID`, `JMSPriority`); do not use `JMSDestination` or `JMSReplyTo` as standard selector headers.

## 11. Implementation Mistakes and Fixes

| Error/Symptom | Cause | Fix |
| --- | --- | --- |
| Selector `attempt > 1` misses `"2"` | Producer wrote String instead of int | Write with `setIntProperty` |
| `MessageFormatException` on getter | Invalid type conversion | Use matching typed getter or standard conversion |
| `NumberFormatException` | String cannot be parsed as a number | Validate data; write typed numbers from producer |
| `setObjectProperty` fails on DTO/UUID/Instant | Not in allowed JMS object set | Convert to String/epoch long or move to body |
| `propertyExists` returns false | Typo, wrong case, or never set | Check schema and producer |
| Cannot set property on received message | Properties are read-only | Create a new message or understand `clearProperties` |
| Selector cannot read metadata | Metadata placed only in body | Set properties for broker-side filtering |
| `JMSCorrelationID` treated as application property | Used wrong property API | Use `setJMSCorrelationID` |
| Set `priorityLevel` yet broker does not prioritize delivery | Application property is not `JMSPriority` | Use producer QoS if delivery priority is truly needed |
| Messages pile up after changing selector | Property name/type drift between producer and listener | Align contract, version properly, monitor queue depth |
| Send succeeds but listener receives nothing | Wrong queue, ACL, selector, or container error | Inspect broker metrics, logs, and destination |
| Forwarding a received message loses properties | `clearProperties` or new message omitted copying | Explicitly list required metadata when forwarding |

### 11.1. Do Not Overuse Metadata

Properties may be stored and evaluated by the provider for selectors, carrying their own processing overhead. Do not stuff large JSON blobs or sensitive data into properties unnecessarily. Use the body for business payloads; use properties for metadata needed for **selection, routing, or observability**. Avoid putting passwords, tokens, or unnecessary personal data into properties because broker admin consoles and logs can expose them.

### 11.2. Standardizing the Message Contract

Producer and consumer should agree on:

~~~yaml
destination: demo.orders.typed
body:
  type: TextMessage
  description: orderId
properties:
  eventType: {type: String, example: ORDER_CREATED}
  priorityLevel: {type: int, example: 7}
  express: {type: boolean, example: true}
  amountMinor: {type: long, example: 125000}
  attempt: {type: int, example: 1}
selector: "eventType = 'ORDER_CREATED' AND priorityLevel >= 5 AND express = TRUE"
~~~

This is a **contract documentation example**, not an executable `application.yml` configuration file. When changing property names, types, or units, check compatibility with **older messages still in the broker** and un-upgraded consumers. Use an explicit version field if two schema versions must coexist during a transition.

## 12. Quick Verification Guide

1. Start the Artemis broker and the Spring Boot demo from Section 8.
2. Observe the listener receiving the message with `priorityLevel=7` and `express=true`.
3. In a test environment, switch the producer to `setStringProperty("priorityLevel", "7")` while keeping the numeric selector `priorityLevel >= 5`. The new message fails the numeric JMS selector comparison.
4. Observe queue depth when messages do not match; do not assume messages vanished just because the listener prints no logs.
5. Switch back to `setIntProperty` and re-run against a clean destination/queue so old messages do not interfere.
6. Inspect properties with `getObjectProperty`/`propertyExists` and confirm boxed types match the contract.

Separate verifying **send completion** from **successful consumer processing**. Typed properties convey metadata and support message filtering; they do not guarantee transactional processing, idempotency, retries, or business-level exactly-once delivery.

## 13. Self-Check

**Question 1.** Why does `setIntProperty("attempt", 2)` differ from `setStringProperty("attempt", "2")`?

**Answer:** One stores an `int` and the other stores a `String`. Getters may parse Strings into numbers, whereas selectors do not perform getter-style implicit casting.

**Question 2.** Is `getLongProperty("attempt")` valid if the property was set with `setIntProperty("attempt", 2)`?

**Answer:** Yes. Widening `int` to `long` is among the conversions mandated by the JMS standard.

**Question 3.** What about `getIntProperty("amountMinor")` when the producer called `setLongProperty("amountMinor", 125000L)`?

**Answer:** Invalid under the JMS conversion table because `long → int` is a narrowing conversion.

**Question 4.** Can you call `setObjectProperty("eventTime", Instant.now())`?

**Answer:** No. `Instant` is not in the permitted set of JMS property objects. Convert it to a String/epoch milliseconds or place it in the body.

**Question 5.** Why does `getPropertyNames()` not list `JMSCorrelationID`?

**Answer:** Because it is a JMS standard header, not a property.

**Question 6.** Does Spring's `MessagePostProcessor` set properties before or after the JMS provider receives the message?

**Answer:** Before: after the converter creates the JMS Message and before the send call.

**Question 7.** How does `setBooleanProperty("express", true)` vs. `setStringProperty("express", "true")` affect the selector `express = TRUE`?

**Answer:** Only the Boolean property matches with the right type; a String is not automatically parsed into a boolean by the selector.

**Question 8.** Should you call `clearProperties()` on a received message solely to increment an `attempt` counter?

**Answer:** Usually no, because it erases all other properties. Create a new message and copy metadata per contract when forwarding or doing a business retry.

## Official References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — section 3.5 on message properties, conversion table 3.5.4, and section 3.8 on selectors.
- [Jakarta Messaging API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — typed setters/getters, `setObjectProperty`, `getPropertyNames`, `propertyExists`, `clearProperties`, and read-only semantics.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, `MessageCreator`, `MessagePostProcessor`.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` and message selectors.
- [Spring Boot — ActiveMQ Artemis and JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — JMS starter, auto-configuration, `native` broker mode.
