# receiveAndConvert and Post-Conversion Data Types

**Topic:** Spring Framework - jms → Synchronous Receiving.

## 1. Why is receiveAndConvert needed?

JMS (Jakarta Messaging) transmits objects implementing `jakarta.jms.Message` such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. When only the business value inside the message is needed, a Spring application does not need to manually check each JMS class, call body getters, and manage `Session`/`MessageConsumer`.

`org.springframework.jms.core.JmsTemplate` provides:

~~~java
Object receiveAndConvert();
Object receiveAndConvert(String destinationName);
Object receiveAndConvert(jakarta.jms.Destination destination);
~~~

These are **abbreviated signatures for study**: in Spring, the return value may be `null`, and the methods can throw `org.springframework.jms.JmsException` (unchecked).

`receiveAndConvert(...)` performs two steps in sequence:

1. **Receive:** **synchronously** receives a JMS message from the chosen destination, within the configured wait limit.
2. **Convert:** invokes `MessageConverter.fromMessage(message)` to obtain the corresponding **Java object**.

For example, with a queue containing only a `TextMessage` whose body is `"hello"`:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof String text) {
    System.out.println(text);
}
~~~

If it retrieves that message, the program prints:

~~~text
hello
~~~

The snippet above is an **excerpt**, assuming `jmsTemplate` is configured with a valid `ConnectionFactory` and broker. If the queue is empty and times out, `value` may be `null`; in that case, no stdout is printed in this snippet.

**Core point:** the returned Java type is not determined by the queue name, the target variable, or the caller's desired type. It depends on the **actual JMS message type received** and the **configured MessageConverter**.

## 2. Synchronous receiving and conversion flow

~~~text
                      Caller / ApplicationRunner / Service
                                      |
                       JmsTemplate.receiveAndConvert(...)
                                      |
                           resolve actual destination
                                      |
                           ConnectionFactory / Session
                                      |
                             MessageConsumer.receive(...)
                                      |
                             JMS message or null
                                      |
                          +-----------+-----------+
                          |                       |
                       null                  JMS Message
                          |                       |
                 return null                 MessageConverter
                                           .fromMessage(message)
                                                  |
                                           Java Object
                                                  |
                                      return Object to caller
~~~

Because this is **synchronous receive**, the calling thread may **block** until a message arrives or the wait time expires. Unlike `@JmsListener`, this approach does not maintain an asynchronous listener handler method.

Outcomes:

- Message arrives and conversion succeeds → returns the Java value.
- No message received within the wait window → returns `null`.
- Connection setup, consumer creation, receive, or conversion fails → typically throws an exception per the Spring/JMS API.
- With converters that can return `null` for a valid empty body, **`null` alone is not always enough to prove a timeout**, especially with custom converters or a `TextMessage` whose body is `null`.

### 2.1. How do receive and receiveAndConvert differ?

| Call | Return type | Actual result | Best suited when |
| --- | --- | --- | --- |
| `jmsTemplate.receive("queue")` | `jakarta.jms.Message` or `null` | Raw JMS message including headers, properties, and body | Need to read `JMSCorrelationID`, `JMSReplyTo`, `JMSMessageID`, properties |
| `jmsTemplate.receiveAndConvert("queue")` | `Object` or `null` | Java value after converting the message body | Only business payload processing is needed |
| `jmsTemplate.receiveSelectedAndConvert("queue", selector)` | `Object` or `null` | Payload after receiving a message matching selector | Need broker-side metadata filtering |
| `@JmsListener(destination = "queue")` | Not a synchronous receive call | Spring listener container invokes handler when a message arrives | Continuous, asynchronous consumers |

`receiveAndConvert` does **not** automatically wrap all JMS headers into the resulting Java object. If correlation or properties such as `eventType` are needed, consider receiving the raw `Message`, reading metadata, and converting intentionally.

## 3. Java types produced by SimpleMessageConverter

By default, `JmsTemplate` uses `org.springframework.jms.support.converter.SimpleMessageConverter` unless the application configures another converter. It supports four common JMS message types. After receiving:

| Actual JMS message received | JMS contents | Java object returned by `receiveAndConvert` | Example |
| --- | --- | --- | --- |
| `TextMessage` | Text | `String` | `"order-42"` |
| `BytesMessage` | Byte sequence | `byte[]` | `new byte[]{1,2,3}` |
| `MapMessage` | Name–value entries using JMS types | `Map<String, Object>` | `{"quantity":3, "orderId":"A42"}` |
| `ObjectMessage` | Serialized Java object | Deserialized object of the sent Serializable type (if compatible) | `Integer.valueOf(42)` or Serializable DTO |
| Another JMS message type, e.g. `StreamMessage` | Not among the four above | **The JMS `Message` object itself** in SimpleMessageConverter 6.x | Must inspect actual type |

**Notably:** `SimpleMessageConverter.fromMessage` in Spring Framework 6.x returns the **plain JMS Message** if it does not recognize one of the four groups. Do not assume every other JMS type throws `MessageConversionException`. A custom converter may choose different behavior.

The Java type in column three is a **runtime type**, not a generic method return type: the signature still returns `Object`. The application must use `instanceof`, safe casting, or a verified contract before accessing it.

### 3.1. TextMessage → String

A producer:

~~~java
jmsTemplate.convertAndSend("demo.messages", "Hello JMS");
~~~

typically creates a `TextMessage` via the default converter. When the caller receives that message:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof String text) {
    System.out.println(text);
}
~~~

Result:

~~~text
Hello JMS
~~~

**Note:** A TextMessage containing a JSON string, such as `"{\"orderId\":\"A42\"}"`, still becomes a **String**, not automatically a `Map` or an `OrderEvent` class. `SimpleMessageConverter` **does not parse JSON automatically**. To receive a Java DTO from JSON, use Jackson/a dedicated converter or parse the String after receiving.

### 3.2. BytesMessage → byte[]

Producer sends bytes:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages", new byte[]{1, 2, 3});
~~~

Consumer receives:

~~~java
import java.util.Arrays;

Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value instanceof byte[] bytes) {
    System.out.println(Arrays.toString(bytes));
}
~~~

When that message is received, stdout:

~~~text
[1, 2, 3]
~~~

**There is no default charset decoding.** `byte[]` is just raw bytes; if it holds UTF-8, Avro, Protobuf, an image, or a file, the caller must decode it using the right schema/codec. Do not write `(String) value` when the runtime type is `byte[]`.

Example converting `byte[]` to text when the contract is genuinely UTF-8:

~~~java
import java.nio.charset.StandardCharsets;

if (value instanceof byte[] bytes) {
    String text = new String(bytes, StandardCharsets.UTF_8);
    System.out.println(text);
}
~~~

This is an **excerpt operating on an already received result**, not a standalone program. For non-text binary payloads, decoding as UTF-8 will produce meaningless data.

### 3.3. MapMessage → Map<String, Object>

A producer can send a valid Java Map:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> order = new LinkedHashMap<>();
order.put("orderId", "A42");
order.put("quantity", 3);
order.put("express", true);

jmsTemplate.convertAndSend("demo.messages", order);
~~~

SimpleMessageConverter builds a `MapMessage` with keys/values permitted by that JMS type. On receive:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");

if (value instanceof Map<?, ?> data) {
    System.out.println("orderId=" + data.get("orderId"));
    System.out.println("quantity=" + data.get("quantity"));
    System.out.println("express=" + data.get("express"));
}
~~~

Result for that message:

~~~text
orderId=A42
quantity=3
express=true
~~~

Do not cast to `LinkedHashMap` merely because the producer used `LinkedHashMap`; the converter only guarantees a suitable `Map`. Also do not rely on MapMessage iteration order. MapMessage body values only support JMS-allowed types such as primitives/wrappers, `String`, and `byte[]`; it does not automatically support nested DTOs, `BigDecimal`, or arbitrary `List`s.

### 3.4. ObjectMessage → deserialized Serializable object

A Serializable object outside the three groups above can be converted into an `ObjectMessage`. Example:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages", Integer.valueOf(42));
~~~

When the consumer receives the message as an `ObjectMessage` and the JMS provider permits Java deserialization:

~~~java
Object value = jmsTemplate.receiveAndConvert("demo.messages");

if (value instanceof Integer number) {
    System.out.println(number);
}
~~~

Output:

~~~text
42
~~~

For a DTO:

~~~java
import java.io.Serial;
import java.io.Serializable;

public record OrderNotice(String orderId)
        implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

This is a separate **`OrderNotice.java` file** if declared as a public record. Both sides must have compatible classes, matching serialization rules, and proper trust policies. A Java record **does not implement Serializable automatically**, so it must be declared if choosing the ObjectMessage route.

**Security warning:** Java deserialization from untrusted messages can be dangerous. Do not arbitrarily widen all trusted packages/classes on the JMS provider. For cross-service or polyglot communication, prefer JSON TextMessage or schema-based BytesMessage with controlled mapping instead of ObjectMessage.

### 3.5. Unfamiliar JMS types do not necessarily fail conversion

Spring Framework 6.x `SimpleMessageConverter.fromMessage` handles the four types above. When encountering an unsupported JMS Message type (such as `StreamMessage`), it may **return the raw JMS Message object itself**, rather than a decoded value. Thus:

~~~java
Object result = jmsTemplate.receiveAndConvert("demo.messages");

if (result instanceof jakarta.jms.Message rawMessage) {
    System.out.println("No specific conversion for JMS type");
}
~~~

This is an illustrative excerpt. It does not mean every `result instanceof jakarta.jms.Message` is an error; it may be because the default converter took its fallback path, or a custom converter intentionally returned the raw message.

## 4. What overloads does receiveAndConvert have?

In Spring Framework 6.x, there are three basic overloads:

~~~java
Object a = jmsTemplate.receiveAndConvert();
Object b = jmsTemplate.receiveAndConvert("demo.messages");
Object c = jmsTemplate.receiveAndConvert(destination);
~~~

- **No arguments:** reads from `defaultDestination` or `defaultDestinationName` configured on **that JmsTemplate**. Without a default, the method does not know where to receive from and throws a configuration error.
- **String destinationName:** uses `DestinationResolver` to resolve the name into a `Destination` object, then receives from it. `pubSubDomain=false` typically resolves as a Queue; `true` uses a Topic per resolver configuration.
- **Destination object:** receives directly from the supplied object, such as an administered destination from JNDI/provider.

The three statements above are **excerpts**; `destination` must be an actual `jakarta.jms.Destination` and the template must be connected.

A default example:

~~~java
jmsTemplate.setDefaultDestinationName("demo.messages");
jmsTemplate.setReceiveTimeout(2_000L);

Object value = jmsTemplate.receiveAndConvert();
~~~

This configuration is done **before using the template**; do not change defaults/timeouts on a singleton template per multi-threaded HTTP request. When handling multiple destinations, pass the destination explicitly or use multiple statically configured template beans.

### 4.1. receiveSelectedAndConvert and message selectors

When you want to fetch a message matching metadata conditions:

~~~java
Object value = jmsTemplate.receiveSelectedAndConvert(
        "demo.messages",
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5");
~~~

This is the **`receiveSelectedAndConvert(String destinationName, String messageSelector)`** overload. The selector uses JMS message properties and allowed standard headers; it **does not** read the body of a TextMessage/MapMessage.

For the selector above to work, the producer must set properties with matching types:

~~~java
jmsTemplate.convertAndSend(
        "demo.messages",
        "order-42",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("priorityLevel", 7);
            return message;
        });
~~~

When a matching message is received, the default converter still returns the **String** `"order-42"`. The selector determines **which message is picked**, not **which Java type it converts into**.

Note that `priorityLevel` must be a numeric type (such as int) for the `>= 5` comparison, not the String `"7"`; JMS selectors **do not apply** property getter coercion tables.

## 5. receiveTimeout and the meaning of null

Because this is **synchronous** receiving, you must understand `receiveTimeout` to avoid accidentally blocking threads for long periods.

### 5.1. JmsTemplate receive wait rules

| `receiveTimeout` setting | Meaning |
| --- | --- |
| `0` | **Wait indefinitely** until a message arrives or an error/resource close occurs |
| Positive number, e.g. `2_000` | Wait up to roughly 2 seconds |
| Negative number, e.g. `-1` | **No wait**: attempt to receive an immediately available message and return |

`JmsTemplate` defaults to **indefinite wait** (value 0). Do not confuse this with Spring listener containers or Spring Integration inbound adapters, which have their own timeout rules.

~~~java
// Configure once when creating the bean; do not mutate per request.
jmsTemplate.setReceiveTimeout(2_000L);

Object value = jmsTemplate.receiveAndConvert("demo.messages");
if (value == null) {
    System.out.println("NO_MESSAGE_OR_NULL_BODY");
}
~~~

If the queue has no message within the wait window, `receiveAndConvert` returns `null` per the API contract. However, a converter can also return `null` when a message has an empty body or the converter itself returns `null`. When you must distinguish **no message** from **message with null payload**, call `receive(...)` first to inspect the JMS Message itself and then convert manually.

Raw API example:

~~~java
import jakarta.jms.Message;
import org.springframework.jms.support.converter.MessageConverter;

Message raw = jmsTemplate.receive("demo.messages");
if (raw == null) {
    System.out.println("TIMEOUT");
} else {
    MessageConverter converter = jmsTemplate.getMessageConverter();
    if (converter == null) {
        throw new IllegalStateException("Converter not configured");
    }
    Object payload = converter.fromMessage(raw);
    System.out.println(payload == null ? "NULL_BODY" : "GOT_BODY");
}
~~~

This is an **excerpt** using `jakarta.jms.Message` and Spring JMS's converter; getters/`fromMessage` can throw `JMSException`, so the enclosing method must declare or catch it. Using the raw message also lets you read `JMSCorrelationID`, `JMSMessageID`, and application properties when needed.

### 5.2. Spring Boot property

With Spring Boot's auto-configured JmsTemplate:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

Boot translates this duration into the template's wait timeout setting. **This property does not alter broker retention, consumer acknowledgement, or transactions.** If you define your own `@Bean JmsTemplate`, ensure that bean receives the proper configuration or sets its timeout directly in Java Config.

### 5.3. Why should HTTP requests not wait indefinitely?

If an HTTP servlet thread calls `receiveAndConvert()` with no timeout, the request can hang until the broker gets a message. That can exhaust the server's thread pool when concurrent requests arrive. For services continuously consuming messages, Spring `@JmsListener` is usually the natural choice; for controlled polling, set explicit timeouts, concurrency limits, and backpressure.

## 6. Returned Object and safe handling

The signature of `receiveAndConvert` returns `Object`, not an auto-cast generic `T`:

~~~java
Object payload = jmsTemplate.receiveAndConvert("demo.messages");
~~~

**Do not** write this when a queue can hold multiple message types:

~~~java
// May throw ClassCastException if the actual message is BytesMessage/MapMessage.
String text = (String) jmsTemplate.receiveAndConvert("demo.messages");
~~~

A safer approach:

~~~java
Object payload = jmsTemplate.receiveAndConvert("demo.messages");

if (payload == null) {
    System.out.println("TIMEOUT_OR_NULL_PAYLOAD");
} else if (payload instanceof String text) {
    System.out.println("TEXT=" + text);
} else if (payload instanceof byte[] bytes) {
    System.out.println("BINARY_LENGTH=" + bytes.length);
} else if (payload instanceof java.util.Map<?, ?> map) {
    System.out.println("MAP_KEYS=" + map.keySet());
} else if (payload instanceof java.io.Serializable serializable) {
    System.out.println("SERIALIZABLE=" +
            serializable.getClass().getName());
} else {
    System.out.println("UNEXPECTED_TYPE=" +
            payload.getClass().getName());
}
~~~

This is a method body snippet with `jmsTemplate` already injected. Do not compare `Map.keySet()` against a fixed order; it depends on the Map implementation returned by the converter. Note that `String`, `byte[]`, and most Maps also implement `Serializable`, so check specific branches **before** the `Serializable` branch to avoid catching them prematurely.

### 6.1. When Java data still needs schema validation

Even when the runtime type is String or Map, business logic must still verify:

- Does a `String` contain valid JSON? Are the version/schema compatible?
- Does a Map contain required keys? Is `quantity` an Integer, or a String?
- Does a byte[] match the expected MIME type, codec, and size limits in the contract?
- Does an ObjectMessage have a compatible class, valid allowlist, and trusted origin?

The converter only provides the **initial Java value**, not full semantic validation of business data.

## 7. Runnable example: Spring Boot 3.x + Artemis, synchronous receive of four payload types

This Java 17+ example sends four messages via `convertAndSend` and then uses **the same ApplicationRunner** to call `receiveAndConvert` sequentially to receive them. **Do not put `@JmsListener` on the same queue**, to avoid a competing consumer altering the demonstration output.

### 7.1. Preparation

Create a Maven project from [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot 3.x, group `com.example`, artifact `receive-convert-demo`, and the **Spring for Apache ActiveMQ Artemis** dependency (`org.springframework.boot:spring-boot-starter-artemis`).

Infrastructure requirements:

- An external Apache ActiveMQ Artemis broker running at `tcp://localhost:61616`.
- Queue `demo.receive.convert` exists or the broker is configured for appropriate auto-creation.
- Account has connect/send/consume permissions on the queue.
- Broker/client permits deserializing `java.lang.Integer` in ObjectMessage. If the provider/trust policy forbids ObjectMessage, safely adjust the test scenario or omit that case rather than widening the allowlist recklessly.
- Queue starts empty and has no other competing consumers so the demo output stays deterministic.

Set environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD` according to your broker environment.

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=3s
~~~

`native` mode **does not automatically start a broker**. The 3-second timeout bounds wait time in the example; it does not govern message TTL.

File `src/main/java/com/example/ReceiveConvertDemoApplication.java`:

~~~java
package com.example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveConvertDemoApplication {

    private static final String QUEUE = "demo.receive.convert";

    public static void main(String[] args) {
        SpringApplication.run(ReceiveConvertDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            // Producer: four Java types -> four corresponding JMS messages.
            template.convertAndSend(QUEUE, "hello");
            template.convertAndSend(QUEUE, new byte[] {1, 2, 3});

            Map<String, Object> order = new LinkedHashMap<>();
            order.put("orderId", "A42");
            order.put("quantity", 3);
            template.convertAndSend(QUEUE, order);

            template.convertAndSend(QUEUE, Integer.valueOf(42));

            int received = 0;
            for (int i = 0; i < 4; i++) {
                Object value = template.receiveAndConvert(QUEUE);

                if (value == null) {
                    System.out.println("TIMEOUT");
                    break;
                }
                if (value instanceof String text) {
                    System.out.println("STRING=" + text);
                } else if (value instanceof byte[] bytes) {
                    System.out.println(
                            "BYTES=" + Arrays.toString(bytes));
                } else if (value instanceof Map<?, ?> map) {
                    System.out.println("MAP=orderId:"
                            + map.get("orderId") + ",quantity:"
                            + map.get("quantity"));
                } else if (value instanceof Integer number) {
                    System.out.println("OBJECT=" + number);
                } else {
                    throw new IllegalStateException(
                            "Unexpected Java type: "
                                    + value.getClass().getName());
                }
                received++;
            }
            System.out.println("RECEIVED=" + received);
        };
    }
}
~~~

The file has a single public class matching the filename. It uses Java 17 pattern matching `instanceof` and requires no custom converter. Spring Boot with the Artemis starter and valid configuration provides `ConnectionFactory` and `JmsTemplate`. Both sending and receiving go through the queue.

### 7.2. Run command and expected stdout

In the Maven project root directory:

~~~bash
mvn spring-boot:run
~~~

If the project has the Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With a clean queue, no competing consumers, and compatible broker/credentials/deserialization policy, you will see **four payload lines** and **one summary line**. One valid ordering of lines is:

~~~text
STRING=hello
BYTES=[1, 2, 3]
MAP=orderId:A42,quantity:3
OBJECT=42
RECEIVED=4
~~~

In the demo, `RECEIVED=4` is printed last because the loop finishes first; **payload line ordering is not a contract to depend on**, since JMS producer/consumer resources, the provider, and the environment can affect ordering when multiple producers/consumers or priority settings exist. Spring also prints startup logs.

If fewer than four messages arrive within 3 seconds per receive, the program may print `TIMEOUT` and `RECEIVED` less than 4. If the queue contains leftover messages with another schema, results will differ or a cast error may occur. If Artemis blocks ObjectMessage deserialization, the example may fail on the fourth message and trust class configuration must be checked.

### 7.3. Why is this a synchronous receiving example?

No `@JmsListener` exists in the example; `ApplicationRunner` actively calls `receiveAndConvert(QUEUE)`. The runner thread continues only after receive returns (or times out / errors). This pattern suits learning and short polling workers, **unlike a long-running listener container**.

Note that if the app starts when the broker is unavailable, sending may throw an exception before reaching receive; do not assume it will simply print `TIMEOUT`. The timeout here governs waiting once the consumer is active.

## 8. Does using a custom MessageConverter change the received type?

**Yes.** `receiveAndConvert` has no hardcoded rule that "TextMessage is always String" regardless of configuration. It calls the `JmsTemplate`'s active `MessageConverter`.

For instance, a system using JSON `TextMessage`s may want to receive a DTO directly instead of a String. Common approach:

1. Producer sends a JSON TextMessage with a well-defined schema.
2. Configure a JSON converter, such as `MappingJackson2MessageConverter` (in Spring Framework 6.x) with Jackson dependencies.
3. Receiver uses the same type-id convention or safely configured type mapping.
4. `receiveAndConvert` can return a domain object like `OrderEvent`, rather than a String.

An **illustrative** configuration, not a standalone project:

~~~java
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MessageConverter converter() {
    MappingJackson2MessageConverter c =
            new MappingJackson2MessageConverter();
    c.setTargetType(MessageType.TEXT);
    c.setTypeIdPropertyName("_type");
    return c;
}
~~~

You must **attach the converter to JmsTemplate**, for example:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setMessageConverter(converter());
template.setReceiveTimeout(2_000L);
~~~

These are **two excerpts**, assuming `ConnectionFactory`, Jackson, and a suitable `converter()` method exist. With JSON converters, type metadata, trusted mappings, and target object types on the receiver must all be configured properly. **Never** accept arbitrary class names from untrusted sources and deserialize them unchecked.

### 8.1. A JmsTemplate does not necessarily share the listener's converter

`JmsTemplate` and `@JmsListener` can be configured with different converters. The listener container/adapter has its own message conversion path. Seeing a DTO in a listener **does not prove** `jmsTemplate.receiveAndConvert` on another template returns a DTO too. Always inspect `jmsTemplate.getMessageConverter()` and container settings when comparing results.

### 8.2. What if no converter is used?

A `JmsTemplate` can be configured with a custom `MessageConverter`, or in certain low-level setups conversion may be bypassed/custom-handled. When the **raw JMS Message** is needed, the clearest approach is `receive(...)`; do not rely on `receiveAndConvert(...)` as an API that always returns a JMS Message.

## 9. Keeping headers/properties alongside the payload

When code needs `JMSCorrelationID`, `JMSReplyTo`, `eventType`, and the payload, there are two approaches:

**Approach 1 — Receive raw then convert explicitly**

~~~java
import jakarta.jms.Message;
import org.springframework.jms.support.converter.MessageConverter;

Message raw = jmsTemplate.receive("demo.messages");

if (raw == null) {
    System.out.println("NO_MESSAGE");
} else {
    String correlationId = raw.getJMSCorrelationID();
    String eventType = raw.getStringProperty("eventType");

    MessageConverter converter = jmsTemplate.getMessageConverter();
    if (converter == null) {
        throw new IllegalStateException("Missing MessageConverter");
    }
    Object body = converter.fromMessage(raw);
    System.out.println("correlation=" + correlationId);
    System.out.println("eventType=" + eventType);
    System.out.println("bodyType="
            + (body == null ? "null" : body.getClass().getName()));
}
~~~

This is an **excerpt** requiring `jakarta.jms.Message`, a Spring template, and `JMSException` declaration/handling in the enclosing method. It lets you separate **headers**, **properties**, and **body** instead of collapsing everything into one object.

**Approach 2 — Design the body contract**

If consumers only need business fields, encode them in a schema-validated DTO/JSON instead of coupling the application to JMS metadata. However, for request/reply, correlation, and routing, headers still play a distinct role; do not copy secrets or sensitive metadata into the body unnecessarily.

## 10. Queues, competing consumers, and why one receive takes one message

`receiveAndConvert` does **not** read the whole queue, has no broadcast semantics, and does not return a list of messages.

- A single call normally retrieves **at most one** message from the destination.
- Call it repeatedly to poll multiple messages, with timeouts, a shutdown signal, and an iteration cap.
- Multiple consumers on the same queue **compete** for messages; a single message is not automatically duplicated to both a `receiveAndConvert` caller and a `@JmsListener` on the same queue.
- If the destination is a Topic, whether a subscriber receives a message depends on subscription lifecycle, durable/shared subscriptions, and when the consumer was created; do not use queue examples to infer that topics buffer backlogs like queues.
- For batched synchronous receives, manage connection/session caching, concurrency, and rate to avoid resource exhaustion.

Example of a mistaken expectation:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42");

// Suppose a @JmsListener also listens on orders.queue.
// You cannot expect both to reliably receive the same message.
Object value = jmsTemplate.receiveAndConvert("orders.queue");
~~~

One of the consumers may grab the message first. When `receiveAndConvert` returns `null` even though a producer sent a message, check **competing consumers** and queue depth before concluding the converter failed on the type.

## 11. Acknowledgment, transactions, and conversion errors

Three events must be distinguished:

1. **The broker delivers the message to the consumer**.
2. **JmsTemplate receives the message** within the session's ack/transaction mode.
3. **The converter converts the body** and the application processes the data.

An application must not assume that throwing an exception after `receiveAndConvert` automatically returns the message to the queue. Depending on session acknowledgement, transactions, and commit/rollback boundaries, the message may already be acknowledged or committed. Under `AUTO_ACKNOWLEDGE`, receipt/ack and conversion/business processing are not one end-to-end transaction.

- `JmsTemplate` manages resources and translates JMS exceptions per Spring conventions.
- The converter can throw `org.springframework.jms.support.converter.MessageConversionException` or runtime errors from a custom converter.
- `ObjectMessage` can fail deserialization due to security allowlists, classpath, versioning, or untrusted data.
- Successful conversion does not guarantee business logic or database writes succeed.
- For transactional processing, configure the corresponding JMS session transaction/transaction manager and verify commit timing against business operations in real tests.
- When integrating a database and JMS, a local JMS transaction does not automatically provide atomic commit across both systems; consider outbox/inbox, JTA/XA, or idempotency as required.

When conversion fails repeatedly, do not retry a poison message indefinitely. Design retry/backoff, redelivery limits, and a dead-letter queue (DLQ) at the consumer/broker per explicit policy.

## 12. Common issues and diagnosis

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `receiveAndConvert` returns `null` | Empty queue, timeout, taken by another consumer, or body/converter returned null | Check queue depth, timeout, competing consumers; use raw receive to distinguish |
| Thread hangs in receive | `receiveTimeout=0` (indefinite wait) | Set a positive timeout or negative no-wait per intent |
| `ClassCastException` casting to String | Actual message is BytesMessage, MapMessage, or ObjectMessage | Use `instanceof`, log runtime type, verify producer contract |
| Received JSON String instead of DTO | SimpleMessageConverter only converts TextMessage → String | Parse JSON or configure a JSON converter and type metadata |
| Received `byte[]` instead of text | Producer sent BytesMessage | Decode codec/UTF-8 explicitly or update sender contract |
| Map has different order, or cast to LinkedHashMap fails | Converter returns a Map without promising implementation/order | Access solely via the `Map` interface and keys |
| ObjectMessage deserialization fails | Class version mismatch, missing class, security allowlist | Align class/schema and policy; avoid broad trusted packages |
| Received raw `jakarta.jms.Message` from `receiveAndConvert` | JMS Message type not specially handled by SimpleMessageConverter | Check actual message type (e.g., StreamMessage) or use a suitable converter |
| Missing `JMSCorrelationID` in received object | Converter returns body without carrying headers | Use `receive` and read headers before converting |
| No-arg `receiveAndConvert()` complains about missing default | Default destination not configured | Set `defaultDestinationName` or pass destination name |
| Wrong message type received on multi-type queue | Producer sends multiple schemas to same destination | Separate queues/schemas, use selectors/properties, or inspect at runtime |
| Both listener and polling on same queue | Competing consumers | Do not test both paths on one queue expecting both to see every message |
| Consumer reports conversion error after broker delivery | Valid JMS delivery, incompatible payload | Investigate converter, classpath, message schema, DLQ/retry |
| Connection/ACL/destination error | Broker down, wrong URL, credentials, unprovisioned queue | Check Artemis health, logs, permissions, endpoint |

### 12.1. Quick diagnostic flow

~~~text
What kind of JmsTemplate is injected?
   |
   v
Are receiveTimeout + destination correct?
   |
   v
Does the broker have messages? Are there competing consumers?
   |
   v
Which JMS Message type was received? (Text/Bytes/Map/Object/Stream...)
   |
   v
Which MessageConverter does the template use?
   |
   v
Result runtime type? Null due to timeout/body/converter?
   |
   v
Schema/deserialization/cast error or business error?
~~~

When detailed observability is needed, log the destination, JMS message class, Java payload class, and business/correlation ID, while avoiding logging personal data, tokens, and untrusted serialized objects directly.

## 13. Misconceptions to avoid

1. **"receiveAndConvert always returns String."** False: it returns an `Object` whose runtime type depends on the JMS Message and converter.
2. **"A JSON TextMessage is automatically converted to a Map."** False with SimpleMessageConverter: the result is a String.
3. **"BytesMessage is automatically decoded as UTF-8."** No: the result is `byte[]`.
4. **"MapMessage always becomes a LinkedHashMap."** No: rely only on the `Map` contract.
5. **"ObjectMessage can always be deserialized."** No: compatible classes and trust policies are required.
6. **"No message received means the converter failed."** No: it may be an empty queue, timeout, or competing consumer.
7. **"receiveAndConvert is a non-blocking API."** No: by default it can wait indefinitely unless an appropriate timeout is configured.
8. **"null always means timeout."** Not strictly: custom converters or null bodies can return null.
9. **"Throwing an exception after receiving makes the broker always redeliver."** No: depends on ack/transaction mode and commit boundary.
10. **"MapMessage body fields can be queried by a JMS selector."** No: selectors read properties and certain headers, not the body.
11. **"The converter changes the destination type."** No: the destination target is decided by template/resolver and broker.
12. **"@JmsListener and receiveAndConvert on the same queue both receive the same message."** No: queue consumers compete.
13. **"Declared return type Object means nothing can be known about the payload."** In practice you can inspect with `instanceof` and define explicit schema contracts.
14. **"Every unfamiliar Message type throws a conversion exception."** Not with SimpleMessageConverter 6.x: there is a fallback returning the raw JMS Message.

## 14. Self-check

**Q1.** A `TextMessage` with body `"42"` is received by default `receiveAndConvert`. What is the Java type?

**Answer:** `String`, not `Integer`. SimpleMessageConverter extracts text and does not auto-parse numbers.

**Q2.** Producer sends `byte[] {1, 2, 3}` via `convertAndSend`; what does the consumer receive?

**Answer:** `byte[]` if the actual message is a BytesMessage and the default converter is used.

**Q3.** A `MapMessage` has field `quantity=3`. What type does the consumer receive? Is it guaranteed to be LinkedHashMap?

**Answer:** A `Map` object. Neither a specific implementation nor iteration order is guaranteed.

**Q4.** Which queue does no-argument `receiveAndConvert()` use?

**Answer:** The default destination set on that JmsTemplate; without a default it reports a configuration error.

**Q5.** Is `setReceiveTimeout(0)` no-wait or indefinite wait?

**Answer:** Indefinite wait per JmsTemplate rules. Negative values mean no-wait.

**Q6.** If both `JMSCorrelationID` and the body are needed, which approach should you choose?

**Answer:** Use `receive(...)` to get the raw Message, read the header, then call `MessageConverter.fromMessage(raw)` or extract the body by type.

**Q7.** When the receiver sees a JSON String instead of a DTO, is the message corrupted?

**Answer:** No. SimpleMessageConverter simply returns a String; configure a JSON converter or parse explicitly.

**Q8.** Two consumers on the same queue: one `@JmsListener` and one `receiveAndConvert`. Will both definitely receive the same message?

**Answer:** No. Queues use competing consumers; a single message is not broadcast to both.

**Q9.** What does `SimpleMessageConverter.fromMessage` do when receiving a JMS message type outside the four common types?

**Answer:** Per Spring Framework 6.x Javadoc, it returns the plain JMS Message itself (fallback). Custom converters may behave differently.

**Q10.** Does `receiveAndConvert` guarantee the application's database transaction is atomic with the JMS receive?

**Answer:** No. Transaction/ack/retry/compensation must be designed for the context, and consistency and idempotency must be tested.

## Official references

- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, blocking and timeouts, comparison with asynchronous listeners.
- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, receive timeout, message converters, and destination configuration.
- [Spring Framework Javadoc 6.2 — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receiveAndConvert`, `receiveSelectedAndConvert`, `getMessageConverter`, and `setReceiveTimeout`.
- [Spring Framework Javadoc 6.2 — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): Text/Bytes/Map/Object mapping and fallback for unrecognized JMS types.
- [Spring Framework Javadoc 6.2 — MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): `toMessage`/`fromMessage` contract.
- [Spring Boot Reference — JMS/Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): Artemis starter, native broker, auto-configured ConnectionFactory/JmsTemplate.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS Message types, consumers, session acknowledgement, and selectors.
