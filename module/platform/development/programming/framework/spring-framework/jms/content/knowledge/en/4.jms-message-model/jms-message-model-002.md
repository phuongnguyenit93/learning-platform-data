# TextMessage and Text Content in Spring JMS

## 1. What Is TextMessage?

In **Jakarta Messaging (JMS)**, `TextMessage` is a `jakarta.jms.Message` type whose **body is a `java.lang.String`**. When a producer needs to transfer a notification sentence, text snippet, XML, or text-based JSON through a JMS broker, `TextMessage` is the most direct and straightforward message type to use.

Example body:

```text
Order #42 has been confirmed.
```

Or JSON content is still a *text string*:

```json
{
  "eventId": "evt-42",
  "eventType": "ORDER_CONFIRMED",
  "orderId": 42,
  "customerName": "Nguyễn An"
}
```

JSON here **has not automatically turned into a Java object**. To JMS, the body is still a `String`; the receiving application must parse it manually or configure an appropriate `MessageConverter`.

Visualizing a message:

```text
JMS Message
├── Header: JMSMessageID, JMSTimestamp, JMSCorrelationID, ...
├── Properties: contentType="application/json", schemaVersion=1, ...
└── Body (TextMessage): "{\"eventId\":\"evt-42\", ...}"
```

**Distinguish three layers:** `TextMessage` describes the **body data type**; `Queue` or `Topic` describes the **destination/routing**; a custom `Content-Type` property describes the **text interpretation convention** between applications. A `TextMessage` can be sent to either a Queue or a Topic. It does not by itself decide whether one or multiple consumers receive the message.

## 2. Core API and Body Lifecycle

This is the `jakarta.jms.TextMessage` interface, not `javax.jms.TextMessage` from legacy JMS libraries. Spring Boot 3 / Spring Framework 6 uses the `jakarta.jms` namespace.

| API | Role | Things to remember |
| --- | --- | --- |
| `session.createTextMessage()` | Creates a `TextMessage` with an initial `null` body. | `getText()` returns `null` at this point. |
| `session.createTextMessage(String)` | Creates the message and immediately sets the body. | The string can be plain text, XML, or JSON. |
| `message.setText(String)` | Writes or replaces the body content when the message is writable. | Received messages typically have a read-only body. |
| `message.getText()` | Reads the raw body string (can be `null`). | No implicit JSON/XML parsing step occurs. |
| `message.getBody(String.class)` | Reads the body via the generic `Message` API. | For a valid `TextMessage`, returns `String` or `null`. |
| `message.isBodyAssignableTo(String.class)` | Checks whether the body can be read as `String`. | Useful when receiving a `Message` of unknown type. |
| `message.clearBody()` | Clears the body and puts it into writable mode. | Not a way to update a message already stored in the broker. |

Both `TextMessage#getText()` and `setText()` can throw `JMSException`. If the body is in read-only mode, `setText()` can throw `MessageNotWriteableException`.

### `null`, Empty String, and Whitespace Are Three Distinct Cases

| Created body | `getText()` value | Suggested meaning |
| --- | --- | --- |
| `createTextMessage()` | `null` | Body has not been set |
| `createTextMessage("")` | `""` (length 0) | String is present but empty |
| `createTextMessage("   ")` | `"   "` (length 3) | Contains three spaces |
| `createTextMessage("Hello")` | `"Hello"` | Normal string |

If business logic does not accept empty data, check both `null` and `isBlank()`; do **not** automatically `trim()` every message because leading/trailing spaces or newlines may be meaningful data. JMS does not enforce a content validation policy for applications.

### Creating and Reading with Pure JMS

The following snippet illustrates the API **inside a method that already has a valid `jakarta.jms.Session session`**; it is not a standalone Java program:

```java
TextMessage outgoing = session.createTextMessage("Hello, JMS!");
outgoing.setStringProperty("contentType", "text/plain");
outgoing.setIntProperty("schemaVersion", 1);

String text = outgoing.getText();              // "Hello, JMS!"
String type = outgoing.getStringProperty("contentType"); // "text/plain"
int version = outgoing.getIntProperty("schemaVersion");  // 1
```

The sender must obtain a `Session` from a JMS connection/provider or let `JmsTemplate` supply one to a callback. Do **not** instantiate an arbitrary `TextMessage` implementation with `new TextMessage()`: it is an interface, and the provider creates the actual object.

Once a generic `Message` object is received, you can check its type before reading:

```java
if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    // Validate and process body.
} else {
    // Handle other body types separately, or reject per contract.
}
```

With the JMS 2.0+/Jakarta Messaging 3.x API, `message.getBody(String.class)` is a cleaner choice **when the contract already guarantees a compatible body type**. If the actual body is not assignable to `String`, calling with the wrong type can throw `MessageFormatException`. Check `isBodyAssignableTo(String.class)` when handling generic messages.

## 3. Text Body, Headers, and Properties Serve Different Purposes

Suppose you send an order-created notification:

```text
Header:
  JMSMessageID: assigned by broker/provider
  JMSTimestamp: managed by provider
  JMSCorrelationID: request-734 (if set by application)

Properties:
  eventType: ORDER_CREATED
  contentType: application/json
  schemaVersion: 1

Body:
  {"eventId":"evt-734","orderId":734,"total":199000}
```

- **Body** holds the primary data; it can be large and structured.
- **Standard JMS Headers** hold metadata about identification, routing, priority, correlation, redelivery, etc. Fields do not always carry application-set values.
- **Properties** are customizable metadata with primitive/basic types such as `String`, `int`, `boolean`; suited for classification, routing, or selectors. Properties are not the place to stuff entire large Java/JSON objects.
- `contentType` in the example is an **application-defined property convention**, not a mandatory JMS `Content-Type` header. JMS does not automatically recognize `application/json` and parse the content.
- `JMSType` is a separate JMS header; it is **not implicitly synonymous with MIME Content-Type**.
- `JMSMessageID` is a provider-assigned message identifier. If you need a stable event identifier across producer retries/deduplication, add a separate business `eventId`.

Properties can be used with **JMS selectors**; selectors inspect valid headers/properties and **do not search inside the text body**. For instance, a consumer that only cares about `eventType = 'ORDER_CREATED'` should place `eventType` in a property. If `"eventType"` only exists inside the JSON body, a JMS selector cannot filter on that JSON field automatically.

## 4. TextMessage Supports Unicode, But Still Needs a Format Contract

In Java, `String` represents Unicode content (UTF-16 storage units); JMS code works with `String`, not a `byte[]` that you encode manually. Strings such as `"Tiếng Việt có dấu"`, `"こんにちは"`, or `"🌿"` can all be valid `TextMessage` bodies. The JMS provider/protocol handles transmitting data between client and broker.

Do not confuse three concepts:

1. **Characters in `String`**: the text data the application sees.
2. **UTF-16 code unit count `String.length()`**: not the number of human-perceived characters; emojis often occupy two code units.
3. **Bytes on the wire/broker**: depends on the provider/protocol/encoding and metadata; cannot be inferred from `String.length()`.

If a program manually converts text into bytes (`text.getBytes(charset)`) and writes them into a `BytesMessage`, then it **must agree on the charset** with the consumer, usually UTF-8. With `TextMessage`, do not manually call `getBytes()` and mistakenly treat the body as still being a `String`.

Sensible formats for `TextMessage`:

| Content | Example | Proper handling |
| --- | --- | --- |
| Plain text | `Order delivered` | Display, validate, store as text |
| JSON | `{"status":"DONE"}` | Parse JSON into a validated schema/DTO |
| XML | `<status>DONE</status>` | Parse with a securely configured XML parser |
| Small CSV | `id,status\n1,DONE` | Use a CSV parser, specify delimiter and quoting |
| Base64-encoded string | `SGVsbG8=` | Use only when required by protocol; raw binary usually fits `BytesMessage` |

**There is no JMS rule stating all JSON must be `TextMessage`**; however, it is a common choice when human-readable content, cross-language interoperability, and clear schemas are needed. Plain text alone does not provide security, integrity, or versioning.

## 5. How Spring JMS Works with TextMessage

Spring provides `JmsTemplate` and `@JmsListener` so applications rarely have to manage `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` manually.

There are two common sending styles:

**Creating `TextMessage` manually:** when you need explicit control over the body type and specific properties/headers.

```java
jmsTemplate.send("orders.text", session -> {
    TextMessage msg = session.createTextMessage("Order #42 confirmed");
    msg.setStringProperty("contentType", "text/plain");
    msg.setStringProperty("eventType", "ORDER_CONFIRMED");
    return msg;
});
```

**Converting `String` automatically:** when using the default `SimpleMessageConverter`, Spring turns a `String` into a `TextMessage`:

```java
jmsTemplate.convertAndSend("orders.text", "Order #42 confirmed");
```

`send(..., MessageCreator)` lets a callback create the `TextMessage` directly. `convertAndSend(..., Object)` delegates to the configured **`MessageConverter`**, so actual output can differ if the application replaces the converter. When only a `String` body is needed, `convertAndSend` makes the code shorter; when properties are needed, use a `MessagePostProcessor`:

```java
jmsTemplate.convertAndSend(
    "orders.text",
    "Order #42 confirmed",
    message -> {
        message.setStringProperty("eventType", "ORDER_CONFIRMED");
        return message;
    }
);
```

With default Spring Boot configuration, a listener can receive:

```java
@JmsListener(destination = "orders.text")
public void onText(String text) {
    System.out.println(text);
}
```

Or receive the **native JMS object** to access metadata/body directly:

```java
@JmsListener(destination = "orders.text")
public void onRaw(TextMessage message) throws JMSException {
    System.out.println(message.getText());
    System.out.println(message.getJMSMessageID());
}
```

**Choose one receiving style based on your needs.** If you declare **both** listeners as above on the same Queue running simultaneously, they act as two **competing** consumers, rather than delivering every message to both callbacks. The full runnable example below uses **two different Queues** to avoid confusing delivery mechanics.

## 6. Complete Example: Spring Boot + Artemis, Sending and Receiving Two Text Forms

Goal: observe (1) a producer explicitly creating a `TextMessage` and a consumer receiving the raw `TextMessage`; and (2) a `String` automatically converted into a `TextMessage` via `SimpleMessageConverter` and a consumer receiving the `String` body. Uses **Java 17+, Spring Boot 3.3.13, Gradle, and Apache ActiveMQ Artemis**.

### 6.1. Run the Test Broker

With Docker running, execute this single command (port 61616 is for JMS connections):

```bash
docker run --detach --rm --name artemis-text-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Wait until Artemis is ready before starting the application. These are demo credentials for local testing; do not use them as-is in production environments. The official image can auto-create addresses/queues by default when permitted by the broker; if your broker has `auto-create` disabled, an administrator must create the two Queues `demo.text.raw` and `demo.text.converted` beforehand. To stop the broker: `docker stop artemis-text-demo`.

### 6.2. Gradle Configuration

Create `settings.gradle`:

```groovy
rootProject.name = 'jms-text-demo'
```

Create `build.gradle`:

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

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Create `src/main/resources/application.yml`:

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

`pub-sub-domain: false` explicitly specifies that the demo uses **Queues**, not Topics. Spring Boot creates the `ConnectionFactory`, `JmsTemplate`, and listener infrastructure when the corresponding starter is present.

### 6.3. Complete Java Application

Create the exact file `src/main/java/demo/jms/TextMessageDemoApplication.java`:

```java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class TextMessageDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TextMessageDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExamples(JmsTemplate jmsTemplate) {
        return args -> {
            // Example A: explicitly create a TextMessage.
            jmsTemplate.send("demo.text.raw", session -> {
                TextMessage message =
                        session.createTextMessage("Xin chào JMS 🌿");
                message.setStringProperty("contentType", "text/plain");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            // Example B: SimpleMessageConverter converts String -> TextMessage.
            jmsTemplate.convertAndSend(
                    "demo.text.converted",
                    "Dòng một\nDòng hai"
            );
        };
    }
}

@Component
class TextMessageListeners {

    @JmsListener(destination = "demo.text.raw")
    public void onRaw(TextMessage message) throws JMSException {
        System.out.printf(
                "RAW text=%s | type=%s%n",
                message.getText(),
                message.getStringProperty("contentType")
        );
    }

    @JmsListener(destination = "demo.text.converted")
    public void onConverted(String text) {
        System.out.printf(
                "CONVERTED body=%s%n",
                text.replace("\n", "\\n")
        );
    }
}
```

**Explanation:** `@EnableJms` activates the annotation-driven listener mechanism (Spring Boot also auto-configures the corresponding support when JMS is on the classpath). Once the application context is ready, `ApplicationRunner` sends two messages to the two Queues. The broker dispatches each message to its respective listener.

`TextMessageListeners.onRaw` receives **`jakarta.jms.TextMessage`** directly, using `getText()` and `getStringProperty()`. `onConverted` receives **`String`**, thanks to Spring extracting the payload from the `TextMessage`. These are two method signatures for two use cases, both reading text bodies.

### 6.4. Run and Verify

With Gradle 8.5+ installed, run from the project directory:

```bash
gradle bootRun
```

If you generated the Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Ensure the broker at `localhost:61616` is running and the username/password match.

Apart from Spring/Artemis startup logs, when each message is processed once, the application prints **these two lines (the order between the two lines is not guaranteed)**:

```text
RAW text=Xin chào JMS 🌿 | type=text/plain
CONVERTED body=Dòng một\nDòng hai
```

In the output, `\\n` is the two characters backslash and `n` printed to represent a newline, caused by `replace("\n", "\\n")`; the actual sent body contains **one newline character** between “Dòng một” and “Dòng hai”. Vietnamese diacritics and the symbol retain their content because `TextMessage` operates on `String`; the source file is UTF-8 encoded so the compiler reads the literal characters properly.

If no output appears, check broker connection and listener startup logs, queue names, access permissions, and whether another consumer already took the messages. A Queue may contain unprocessed messages from previous runs; do not infer strict exactly-once guarantees from log line counts under error/retry conditions.

## 7. JSON in TextMessage: Raw Text Format or Converted Object?

The same JSON message can be handled at two levels:

**Level A – raw text:** the producer puts JSON into a `String` (typically serialized with Jackson) and sends a `TextMessage`; the consumer receives `String`, validates, and parses it. When a system involves non-Java languages, this keeps the contract easy to exchange, though you still need agreement on schema, version, required fields, size limits, and parse-error handling.

```java
// Illustration inside a producer with JmsTemplate and ObjectMapper.
String json = objectMapper.writeValueAsString(
        new OrderCreated("evt-42", 42L)
);
jmsTemplate.send("order.events", session -> {
    TextMessage m = session.createTextMessage(json);
    m.setStringProperty("contentType", "application/json");
    m.setIntProperty("schemaVersion", 1);
    return m;
});
```

In this snippet, `OrderCreated` is an application DTO/record and `objectMapper` is a configured Jackson `ObjectMapper`; the snippet **does not compile standalone** without those two components declared. Do not concatenate strings like `"{\"name\":\"" + input + "\"}"` to build JSON: quotation marks, backslashes, or newlines in input will corrupt the data or introduce injection bugs downstream. Use a standard serializer.

**Level B – automatic converter:** Spring provides `MappingJackson2MessageConverter`. When you want the **JMS body to be JSON text**, configure target `MessageType.TEXT`, because this converter can default to producing `BytesMessage` if no target type is set. Here is a **separate configuration example replacing the default converter in the demo above**:

```java
@Bean
public org.springframework.jms.support.converter.MessageConverter jsonConverter() {
    var converter =
            new org.springframework.jms.support.converter.MappingJackson2MessageConverter();
    converter.setTargetType(
            org.springframework.jms.support.converter.MessageType.TEXT
    );
    converter.setTypeIdPropertyName("_type");
    return converter;
}
```

This configuration requires Jackson (`com.fasterxml.jackson.core:jackson-databind`, usually brought in by `spring-boot-starter-json`). Converting back to an object also requires a valid type-id property and appropriate mapping/trust policies; both applications must agree on the converter and schema. **Do not drop this bean into the previous demo and blindly expect `convertAndSend(String)` and all listeners to behave identically to the old converter.** For cross-service JSON contracts, consider using stable type names and explicit type-id mappings rather than coupling the wire format to internal class names.

### When to Prefer TextMessage JSON vs. BytesMessage?

- **TextMessage JSON:** when receivers need human-readable content, selective safe logging, text-based schemas, and easy polyglot integration; usually well suited for small-to-medium business events.
- **BytesMessage:** when the payload is inherently binary (images, protobuf, compressed payloads), or when the wire format specifies agreed-upon raw bytes/charsets.
- **ObjectMessage:** holds a Java `Serializable`, is tied to the Java object model, and carries deserialization risks if receiving from untrusted sources; not a good default choice for multi-system integration.

Do not rely on data merely looking like JSON to guess the converter. Both sides must explicitly agree on the exact JMS message type and content schema.

## 8. Error Cases and Runtime Behavior to Understand

### 8.1. Receiving the Wrong Message Type

If a listener declares `String` but the producer sends a `BytesMessage` or complex object that the converter does not know how to convert, conversion can fail; Spring does not automatically know whether those bytes represent UTF-8 or another business payload. When the contract requires `TextMessage`, the consumer can accept a `TextMessage` parameter and fail explicitly when another type arrives.

In pure JMS, `Message#getBody(String.class)` is not a command to "force any body into a string": it only works for compatible body types. Do not catch the exception and treat missing/invalid data as an empty string.

### 8.2. Empty Body, `null`, Malformed JSON, or Incompatible Version

`TextMessage` accepts `null`. Consumers should validate the payload before parsing:

```java
String body = message.getText();
if (body == null || body.isBlank()) {
    throw new IllegalArgumentException("Text body is missing or blank");
}
```

This is processing logic **inside a listener that received `TextMessage message`**, not a standalone Java class. With JSON, handle parse errors, missing schema fields, unsupported versions, and oversized payloads separately; do not treat syntactically valid JSON as automatically business-valid.

### 8.3. Transactions, Acknowledgment, and Redelivery

`TextMessage` only specifies the **body type**. Messages are acknowledged/committed/rolled back like any other JMS message. If a listener fails and the session rolls back or has not properly ACKed, the broker may redeliver the same message; `JMSRedelivered` can signal a redelivery attempt.

If processing writes to a database or makes HTTP calls, do not infer "exactly once" merely from using `TextMessage`. To prevent duplicate business side effects, include a stable `eventId` in the body/property and implement idempotency (unique key, inbox table, etc.). Configure transactions, retries, and DLQs according to the broker and reliability requirements. Do not ACK before processing finishes if your architecture needs to avoid message loss.

### 8.4. Body Length and Operations

JMS **does not define a universal maximum character limit** for `TextMessage`; practical limits depend on the broker, memory, quotas, protocol, timeouts, and policies. Do not send large files or unbounded text through a queue without an agreed size limit. For very large payloads, consider storing the object in object storage and sending an appropriate reference (along with access permissions and expiration).

Keep logs bounded: avoid printing raw bodies containing PII, tokens, account numbers, or sensitive data. Include `correlationId`/`eventId` for tracing; selectively log message type, contentType, schemaVersion, expected size, and processing status.

### 8.5. Do Not Edit a Received Message to "Update It in the Broker"

Messages arriving at a consumer typically have read-only body/properties; `setText()` is disallowed until the body state is appropriately changed (`clearBody()`). Even if you mutate the object in the JVM, that operation **does not modify the copy already sent in the broker**. To produce a new event/response, create **a new message** and send it to the appropriate destination.

## 9. Common Misconceptions

1. **"TextMessage is a Queue dedicated to text."** False: `TextMessage` is a body type; Queue/Topic is a destination.
2. **"TextMessage is always text/plain."** False: it can hold JSON, XML, CSV, logs, etc.; the content is interpreted per the application contract.
3. **"JSON in a TextMessage is automatically turned into a POJO."** False unless the application configures an appropriate converter/parser.
4. **"`convertAndSend` always produces a TextMessage."** False: the outcome depends on the payload type and `MessageConverter`; `String` with the default `SimpleMessageConverter` is simply the typical case.
5. **"`getText()` is never `null`."** False: the body of a newly created message with no text assigned yet defaults to `null`.
6. **"An empty body and a `null` body are the same."** False: they are two distinct values, even if business validators often reject both.
7. **"A JMS selector can filter JSON fields inside the body."** False: selectors evaluate supported headers/properties and do not parse JSON bodies.
8. **"`String.length()` is the number of bytes the broker sends."** False: `String.length()` counts UTF-16 code units, which differs from wire byte count.
9. **"Once received, you can edit a TextMessage so the broker updates it."** False: received bodies are normally read-only; to publish new content you must send a new message.
10. **"Using TextMessage means processing happens only once."** False: transactions, ACK, retries, and idempotency are delivery concerns independent of body type.

## 10. Practice Questions

**Question 1:** How do the following two lines differ?

```java
TextMessage a = session.createTextMessage();
TextMessage b = session.createTextMessage("");
```

**Answer:** `a.getText() == null`; `b.getText().equals("")` and `b`'s length is 0. The code snippet assumes a valid `Session session` is already available.

**Question 2:** A producer calls `jmsTemplate.convertAndSend("q", "hello")` with the default `SimpleMessageConverter`. What is the message/body type?

**Answer:** `TextMessage` with body `"hello"`. If the converter is replaced, the mapping must be checked again.

**Question 3:** A `TextMessage` contains JSON `{"priority":"HIGH"}`. The consumer sets JMS selector `priority = 'HIGH'`, but the producer did not set a `priority` property. Can it be filtered via the body?

**Answer:** No. Selectors do not read JSON bodies; a valid `priority` property must be added when sending (or filtering must be performed in the handler after receiving).

**Question 4:** Can a `TextMessage` hold Vietnamese characters with diacritics, emojis, and newlines? Do you need to manually create a UTF-8 `byte[]`?

**Answer:** It can hold all of those characters in a `String`. You do not need to manually convert them to `byte[]` to use `TextMessage`; ensure proper source code/file/compiler charset and provider/client compatibility.

**Question 5:** A listener processes a message, writes to the DB successfully, and then fails before JMS commit/ACK; the broker redelivers it. Is this a `TextMessage` bug?

**Answer:** No. This is a transaction/redelivery and side-effect scenario; you need idempotent processing keyed by event ID and proper transaction/ack design.

## 11. Source References

- [Jakarta Messaging 3.1 – `TextMessage` API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/textmessage)
- [Jakarta Messaging 3.1 – `Message` (headers, properties, body)](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Spring Framework – Sending a Message and Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Boot – Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Apache ActiveMQ Artemis – Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Key takeaway:** `TextMessage` transports a **`String`** over JMS. To ensure applications interpret that string correctly, agree on **format, schema, metadata, conversion, and error handling**; to achieve reliable delivery, design transactions, acknowledgments, and idempotency separately.
