# TextMessage vs. BytesMessage for JSON in Spring JMS

## 1. Core Question: Should JSON Be Sent as Text or Bytes?

**JSON is a data format**, whereas **TextMessage** and **BytesMessage** are two Jakarta Messaging (JMS) *body* types. The same business object, such as an order-created event, can be represented as a JSON string placed inside a `TextMessage`, or encoded as a UTF-8 byte sequence placed inside a `BytesMessage`. Both approaches are valid; the consumer must have the corresponding **data contract** to read it properly.

Example business data:

~~~json
{
  "eventId": "evt-42",
  "orderId": "O-42",
  "customer": "Hà",
  "amountVnd": 125000
}
~~~

Two ways to send:

~~~text
Approach A — TextMessage
  Message body = JSON String
  Session.createTextMessage(json)
  Consumer: ((TextMessage) message).getText()

Approach B — BytesMessage
  Message body = byte[] carrying UTF-8 JSON
  Session.createBytesMessage() + writeBytes(json.getBytes(UTF_8))
  Consumer: message.getBody(byte[].class) + decode UTF-8

Both have:
  JMS headers: JMSMessageID, JMSDestination, ...
  JMS properties: eventId, schemaVersion, contentType, ...
~~~

Common misconception: **TextMessage is not a "JSON message" capable of parsing JSON**, and **BytesMessage is not inherently a non-JSON binary format**. JMS only holds/transports the body; responsibility for JSON serialization/deserialization belongs to the producer, consumer, or Spring `MessageConverter`.

### Learning Outcomes

After this lesson, you will understand:

1. The difference between a JMS String body and a byte body.
2. When you need to care about UTF-8, BOM, byte length, and charset mismatch.
3. How to use the JMS API and `JmsTemplate` to send both forms.
4. How `SimpleMessageConverter` and `MappingJackson2MessageConverter` choose the message type.
5. How to design a type/encoding/schema contract so Java services and services in other languages understand each other.
6. Common conversion errors and how to write practical tests.

## 2. Direct Comparison

| Aspect | TextMessage | BytesMessage Used for JSON |
| --- | --- | --- |
| JMS body type | `java.lang.String` | Sequence of bytes |
| Creation API | `session.createTextMessage(json)` | `session.createBytesMessage()` then `writeBytes(...)` |
| Reading API | `getText()` or `getBody(String.class)` | `getBody(byte[].class)` or `readBytes(...)` |
| JSON format | JSON string created by the application | Bytes of the JSON string in the agreed encoding |
| Who handles encoding? | The JMS provider abstracts string transport | The application/converter must agree on how to turn bytes into text |
| Inspectability in admin tools | Usually easier | Depends on whether the tool auto-decodes bytes |
| Language independence | Yes if the consumer supports text types and JSON | Yes if the byte protocol/charset is agreed upon |
| Suitable for truly binary data | Not a natural fit | Better suited |
| JSON validity | Not validated automatically | Not validated automatically |
| JMS selector | Only accesses supported headers/properties; cannot read JSON body automatically | Same |
| Performance | Depends on provider, payload, converter, and network | Depends on provider, payload, converter, and network |

**No standard JMS rule guarantees that BytesMessage is always faster or smaller than TextMessage.** For JSON text, both forms usually carry the same logical content. *On-wire* size, memory copies, caching, and compression depend on the provider, client, and how Jackson produces the data. To choose for performance, benchmark against the actual broker and workload.

## 3. TextMessage: JSON as a String

Jakarta JMS API:

~~~java
// Snippet inside a callback with jakarta.jms.Session session:
String json = "{\"orderId\":\"O-42\",\"customer\":\"Hà\"}";
jakarta.jms.TextMessage message = session.createTextMessage(json);
~~~

Receiving:

~~~java
// Snippet inside a consumer with jakarta.jms.Message message:
if (message instanceof jakarta.jms.TextMessage textMessage) {
    String json = textMessage.getText();
    // Pass json to Jackson ObjectMapper or another JSON decoder.
}
~~~

You can use the generic JMS 2.0+ API:

~~~java
String json = message.getBody(String.class);
~~~

Only use this when you know the body is assignable to `String`, such as from a `TextMessage`. For a `BytesMessage`, do not call `getBody(String.class)` expecting the provider to automatically decode bytes as UTF-8.

**TextMessage is modeled by JMS as a character string**, not a byte sequence in an application-chosen encoding. The provider may choose its own on-wire encoding; the spec does not require you to call `getBytes` before creating a `TextMessage`. Therefore, do not guess network size solely from `json.length()` or assume the provider always sends UTF-8 verbatim.

Suitable when:

- The payload is JSON/XML/text naturally representable as a `String`.
- You want an easily inspectable contract that is simple to debug via the JMS console.
- Producer and consumer primarily exchange JSON strings without needing exact control over raw byte payloads.
- You want quick pairing with `SimpleMessageConverter` using `String`.

Points to handle: `getText()` can return `null` if the TextMessage has no body; validate JSON before parsing. TextMessage also does not allow automatically querying an `orderId` field via a JMS selector; to use selectors, move filterable metadata into properties.

## 4. BytesMessage: JSON Encoded into byte[]

Example sending UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.jms.BytesMessage;

// Snippet inside a callback with Session session:
String json = "{\"orderId\":\"O-42\",\"customer\":\"Hà\"}";
byte[] body = json.getBytes(StandardCharsets.UTF_8);

BytesMessage message = session.createBytesMessage();
message.writeBytes(body);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("charset", "UTF-8");
~~~

Receiving via the `getBody` API:

~~~java
// Snippet inside a consumer with Message message:
byte[] data = message.getBody(byte[].class);
String json = new String(data, StandardCharsets.UTF_8);
~~~

For a typical received `BytesMessage`, `getBody(byte[].class)` retrieves the byte body as an array. This is straightforward when the body is small/medium in size and does not require chunked streaming.

**Essential contract:** if the producer uses UTF-8, the consumer must use UTF-8, or use a JSON decoder that accepts UTF-8 bytes directly. `BytesMessage` has no standard JMS charset attribute that forces the provider to apply an encoding to every byte body. If you choose a `charset` property, that is an **application convention**; both ends must understand and verify it.

### 4.1. Careful with Vietnamese Characters

Example:

~~~java
String json = "{\"name\":\"Hà\"}";
System.out.println(json.length());
System.out.println(json.getBytes(StandardCharsets.UTF_8).length);
~~~

Output:

~~~text
13
14
~~~

`String.length()` counts UTF-16 code units; byte length is the number of bytes after UTF-8 encoding. The character `à` is one UTF-16 unit but encodes into two UTF-8 bytes. For emojis, a single Unicode character can be two UTF-16 units and four UTF-8 bytes.

Never use `String.length()` as a byte buffer length or assume every Java `char` is one byte. That mistake truncates content mid-character inside a UTF-8 sequence.

### 4.2. When You Need to Reject Invalid UTF-8 Bytes

The `new String(bytes, StandardCharsets.UTF_8)` constructor can replace invalid byte sequences with a replacement character, causing the application to **miss corrupted data**. When payloads require exact preservation or carry digitally signed data, decode strictly:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

This snippet is a utility method; place it in an appropriate Java class. If the decoder reports an error, do not silently accept content with replacement characters as valid JSON. Decide whether to retry, dead-letter, or raise a schema error per application policy.

### 4.3. Reading BytesMessage in Chunks

`BytesMessage` is a byte stream with a read cursor. When a message is received, the body is in read-only mode and can be read using:

~~~java
// Snippet inside a consumer when message is known to be a BytesMessage:
BytesMessage bytesMessage = (BytesMessage) message;
long length = bytesMessage.getBodyLength();
byte[] buffer = new byte[4096];
int n;
while ((n = bytesMessage.readBytes(buffer)) != -1) {
    // Process exactly the first n bytes in buffer.
}
~~~

`getBodyLength()` returns a **long**; do not cast it to `int` or allocate an array of an unchecked size. When reading in chunks, a UTF-8 character can be split across two chunks. Do not decode each chunk independently with `new String(buffer, 0, n, UTF_8)`; use a stateful decoder or feed bytes into an appropriate streaming parser.

When a `BytesMessage` is freshly created in a producer, the body starts in **write-only mode**; if you need to read it before sending, call `reset()` to switch to read-only mode and rewind the cursor to the start. For a received message, the provider already puts the body in read-only mode. `clearBody()` clears the body and switches it to writeable mode; do not call it just to "re-read".

### 4.4. Why Not Use `writeUTF` to Send Raw JSON?

~~~java
// Not equivalent to writeBytes(json.getBytes(UTF_8)):
bytesMessage.writeUTF(json);
~~~

`writeUTF` writes the string using **modified UTF-8 with length metadata in the JMS stream format**, not pure UTF-8 JSON bytes. A non-Java consumer reading the entire body and parsing JSON may fail due to the prefix bytes. When the contract states "the body is raw UTF-8 JSON", use `writeBytes(json.getBytes(StandardCharsets.UTF_8))`.

## 5. Headers/Properties Remain Separate from the JSON Body

Both TextMessage and BytesMessage have JMS headers (such as `JMSMessageID`, `JMSCorrelationID`) and JMS properties (typed name–value pairs). This metadata **does not reside inside the JSON body**, even when it sometimes duplicates information for broker filtering or observability.

Suggested contract example:

| Field | Type/Location | Example |
| --- | --- | --- |
| `eventId` | JMS String property | `evt-42` |
| `schemaVersion` | JMS int property | `1` |
| `contentType` | Application String property | `application/json` |
| `charset` | String property (if using bytes) | `UTF-8` |
| `payloadKind` | String property | `text` or `bytes` |
| JSON `orderId` | Field in body | `O-42` |
| JSON `amountVnd` | Field in body | `125000` |

`contentType`, `charset`, and `payloadKind` **are not standard JMS header names with universal automatic behavior**. These properties are only useful when both producer and consumer define the same convention.

Example selector:

~~~sql
schemaVersion = 1 AND payloadKind = 'bytes'
~~~

Selectors only evaluate JMS properties/headers permitted by the spec and **cannot query** `body.orderId` inside plain JSON. If a consumer needs to receive only events of one type, consider an `eventType` property instead of parsing the entire JSON on the broker.

Warning: avoid placing sensitive data or API keys in properties just for easy filtering; metadata may be visible in monitoring tools and broker logs.

## 6. Spring JmsTemplate and SimpleMessageConverter

`JmsTemplate.convertAndSend(...)` uses a `MessageConverter` to convert a Java object into a Jakarta JMS message. According to the Spring documentation, `SimpleMessageConverter` supports by default:

| Java Value Passed to `convertAndSend` | Created Message Type |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| `Serializable` | Can create an `ObjectMessage` depending on converter and type |

With pre-serialized JSON:

~~~java
String json = "{\"orderId\":\"O-42\"}";

// With default SimpleMessageConverter:
jmsTemplate.convertAndSend("orders.json.demo", json);
// -> TextMessage

jmsTemplate.convertAndSend(
        "orders.json.demo", json.getBytes(StandardCharsets.UTF_8));
// -> BytesMessage
~~~

This is an **illustrative snippet** inside a class with an injected `JmsTemplate` and `StandardCharsets` imported, not a standalone Java file. The result above depends on the **currently configured converter**: if the application registers a custom `MessageConverter`, behavior may differ.

More importantly:

- `convertAndSend(destination, someDto)` **does not automatically guarantee JSON**. Using the simple converter, a `Serializable` object can be placed into an `ObjectMessage` via Java serialization; this is unsuitable for cross-language exchange and carries deserialization risks.
- `convertAndSend(destination, jsonString)` creates a TextMessage because the Java value is already a `String`, not because Spring parsed JSON.
- `convertAndSend(destination, jsonBytes)` creates a BytesMessage because the Java value is `byte[]`; Spring does not know whether those bytes are JSON or an image unless you specify a convention.
- `receiveAndConvert(...)` returns an object according to the converter, yet with the default converter a TextMessage usually becomes a String and a BytesMessage usually becomes a `byte[]`, **not automatically an OrderCreated DTO**.

If you want DTOs to convert to JSON automatically, configure the corresponding JSON converter or serialize/deserialize explicitly with Jackson.

## 7. MappingJackson2MessageConverter: Default Is BYTES, Configurable to TEXT

Spring Framework provides `MappingJackson2MessageConverter`, which uses Jackson to convert objects to JSON and back.

Two important details from the Spring Javadoc:

1. **Default `targetType = MessageType.BYTES`**. That means if you use this JSON converter without changing the target, a DTO becomes a **BytesMessage JSON**.
2. Set `converter.setTargetType(MessageType.TEXT)` if you want a DTO to become a **TextMessage JSON**.
3. When receiving messages and converting them back into DTOs based on a type ID, you must set `typeIdPropertyName` and align type ID mappings. Otherwise, inferring the Java class on receive has no clear contract.

Example configuration as an **alternative** to the manual serialization strategy in the hands-on project below:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JsonJmsConverterConfiguration {

    @Bean
    MessageConverter jsonJmsMessageConverter() {
        var converter = new MappingJackson2MessageConverter();

        // Want TextMessage; omitting this line uses default BYTES.
        converter.setTargetType(MessageType.TEXT);

        // Needed for converting messages back into Java objects:
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order.created.v1", OrderCreated.class));

        return converter;
    }
}
~~~

This is an **alternative configuration**; do not add it to the sample project below without changing the send/receive approach: the sample project deliberately creates `TextMessage` and `BytesMessage` via `JmsTemplate.send(...)` to make the difference obvious. If switching to `convertAndSend(dto)` and `@JmsListener(OrderCreated)`, ensure both producer and consumer use compatible converters, valid type IDs, and the Jackson dependency.

**Why map stable type IDs?** You should not expose a full Java class name like `com.example.OrderCreated` as a public contract between services when a logical event name like `order.created.v1` suffices. Spring may fall back to the class name as the type ID if no mapping exists; this increases coupling between producer and consumer. In distributed systems, standardize type IDs/versions in documentation independent of Java packages.

**Converter encoding:** `MappingJackson2MessageConverter` has `setEncoding(...)` and `setEncodingPropertyName(...)`; the default encoding is UTF-8 when converting via BytesMessage. If a producer uses a different encoding, configure it and pass the metadata for the reading side. Choosing TEXT makes the JMS object carry a String; choosing BYTES requires the consumer to know the byte encoding/JSON converter.

## 8. Runnable Project: Same JSON Sent via Both JMS Message Types

This hands-on project uses:

- Java 17.
- Spring Boot 3.3.x, Spring JMS, Jakarta Messaging.
- Apache ActiveMQ Artemis as the local broker.
- Jackson `ObjectMapper` to turn DTOs into JSON, **without** relying on hidden converter choices.
- `JmsTemplate.send(...)` creating TextMessage and BytesMessage explicitly.
- A `@JmsListener` receiving raw `jakarta.jms.Message`, branching by type, decoding JSON, and parsing into the same record.

### 8.1. Running the Artemis Broker

Requires Docker running. A command using the official Artemis image:

~~~bash
docker run --detach --rm --name artemis-json-types -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to be ready and check logs:

~~~bash
docker logs artemis-json-types
~~~

The example binds ports on the loopback host and uses demo credentials **for lab use only**. Depending on broker settings, Queue `orders.json.demo` may be auto-created or must be pre-created by an administrator. Do not use demo settings as production security/persistence policies.

### 8.2. Project Structure

~~~text
jms-json-types/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/json/
    JsonTypesApplication.java
    OrderCreated.java
    OrderPublisher.java
    OrderReceiver.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'jms-json-types'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

Jackson is declared directly and its version is managed by Spring Boot dependency management. Use a compatible Gradle 8.x and JDK 17+. Spring Boot 3 uses `jakarta.jms`, not `javax.jms`.

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
~~~

In the final text, `${...}` expressions in the example must be understood and saved as **standard Spring placeholders** starting with a dollar sign and curly braces. The `demo` defaults are only valid in a local lab; production must use secret injection, never hardcoded passwords.

### 8.3. Shared DTO for Both Sending Approaches

File `src/main/java/demo/json/OrderCreated.java`:

~~~java
package demo.json;

public record OrderCreated(
        String eventId,
        String orderId,
        String customer,
        long amountVnd) {
}
~~~

The Java 17 record defines the business data; Jackson reads/writes JSON for the corresponding record. Both JMS messages will have the **exact same JSON structure**, differing in body type and event ID to distinguish the two demo sends.

### 8.4. Entry Point

File `src/main/java/demo/json/JsonTypesApplication.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JsonTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonTypesApplication.class, args);
    }

    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }

    @Bean
    CommandLineRunner publishTwoFormats(OrderPublisher publisher) {
        return args -> {
            publisher.publishText(new OrderCreated(
                    "evt-text-42", "O-42", "Hà", 125000));
            publisher.publishBytes(new OrderCreated(
                    "evt-bytes-43", "O-43", "Hà", 125000));
        };
    }
}
~~~

Use one consistent `ObjectMapper` bean across producer and consumer. `CommandLineRunner` only produces demo data at startup; in practice, publish when business events happen rather than re-sending events on every deploy.

### 8.5. Producer: Explicitly Creating TextMessage and BytesMessage

File `src/main/java/demo/json/OrderPublisher.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.BytesMessage;
import jakarta.jms.TextMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private static final String DESTINATION = "orders.json.demo";

    private final JmsTemplate template;
    private final ObjectMapper mapper;

    public OrderPublisher(JmsTemplate template, ObjectMapper mapper) {
        this.template = template;
        this.mapper = mapper;
    }

    public void publishText(OrderCreated event)
            throws JsonProcessingException {
        String json = mapper.writeValueAsString(event);

        template.send(DESTINATION, session -> {
            TextMessage message = session.createTextMessage(json);
            message.setStringProperty("payloadKind", "text");
            message.setStringProperty("contentType", "application/json");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }

    public void publishBytes(OrderCreated event)
            throws JsonProcessingException {
        byte[] utf8 = mapper.writeValueAsBytes(event);

        template.send(DESTINATION, session -> {
            BytesMessage message = session.createBytesMessage();
            message.writeBytes(utf8);
            message.setStringProperty("payloadKind", "bytes");
            message.setStringProperty("contentType", "application/json");
            message.setStringProperty("charset", "UTF-8");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }
}
~~~

Key takeaways:

- `ObjectMapper.writeValueAsString(event)` produces a JSON String for TextMessage.
- `ObjectMapper.writeValueAsBytes(event)` produces a JSON `byte[]`; Jackson creates UTF-8 JSON by default in this branch.
- `Session.createTextMessage(json)` and `Session.createBytesMessage()` determine the **JMS message type**.
- `template.send(..., MessageCreator)` does not invoke a converter for the body; the callback builds `jakarta.jms.Message` directly.
- Metadata lives in JMS properties, not in the JSON body even when the same `eventId` appears in both places.
- `charset= UTF-8` is an application-agreed property; the provider does not automatically parse bytes into JSON.

### 8.6. Consumer: Receiving the Raw JMS Message

File `src/main/java/demo/json/OrderReceiver.java`:

~~~java
package demo.json;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.BytesMessage;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderReceiver {

    private final ObjectMapper mapper;

    public OrderReceiver(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @JmsListener(destination = "orders.json.demo", concurrency = "1")
    public void receive(Message message) throws Exception {
        if (!"application/json".equals(
                message.getStringProperty("contentType"))) {
            throw new IllegalArgumentException("Expected JSON contentType");
        }
        if (message.getIntProperty("schemaVersion") != 1) {
            throw new IllegalArgumentException("Unsupported schemaVersion");
        }

        String json;
        String representation;

        if (message instanceof TextMessage text) {
            json = text.getText();
            representation = "text";
        } else if (message instanceof BytesMessage bytes) {
            if (!"UTF-8".equalsIgnoreCase(
                    message.getStringProperty("charset"))) {
                throw new IllegalArgumentException("Expected UTF-8 bytes");
            }
            byte[] raw = bytes.getBody(byte[].class);
            json = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(raw))
                    .toString();
            representation = "bytes";
        } else {
            throw new IllegalArgumentException(
                    "Unsupported JMS message type: " + message.getClass());
        }

        OrderCreated event = mapper.readValue(json, OrderCreated.class);
        System.out.printf(
                "RECEIVED=%s orderId=%s customer=%s amountVnd=%d%n",
                representation, event.orderId(),
                event.customer(), event.amountVnd());
    }
}
~~~

Important details:

1. The listener receives `jakarta.jms.Message`, **not** forcing the parameter to always be String. Thus it can inspect the original body type.
2. For TextMessage, `getText()` returns the JSON String.
3. For BytesMessage, `getBody(byte[].class)` retrieves raw bytes, and the UTF-8 decoder uses `REPORT` on invalid encoding instead of silently substituting characters.
4. Once a JSON String is obtained, both branches use `mapper.readValue(json, OrderCreated.class)`, so business logic does not have to care how the body was transported.
5. If parsing/schema is invalid, the listener throws an error. ACK/redelivery/DLQ depends on the listener/broker transaction and error-handling configuration; production applications must establish an appropriate policy.

`payloadKind` can be used as observability metadata, yet the example trusts the **actual JMS message type** rather than blindly trusting the client-sent property string. If the property says `"text"` while the actual message is a BytesMessage, the system should raise a contract error.

### 8.7. Running and Explaining the Output

With the broker ready:

~~~bash
gradle bootRun
~~~

Two lines printed by the consumer under normal conditions:

~~~text
RECEIVED=text orderId=O-42 customer=Hà amountVnd=125000
RECEIVED=bytes orderId=O-43 customer=Hà amountVnd=125000
~~~

Spring and Artemis may interleave other logs. In a Queue with a single listener at `concurrency=1`, messages are normally consumed in the example's publish order, yet never design business logic to depend strictly on log ordering under different concurrency, retries, or multiple consumers. If the broker is not ready, credentials are wrong, or permissions are missing, the example cannot guarantee those two lines appear.

Stop the broker when finished:

~~~bash
docker stop artemis-json-types
~~~

## 9. Standalone Java 17 Demo: Char Length Differs from UTF-8 Byte Length

This program does not depend on Spring/JMS and compiles immediately with JDK 17; use it to verify the charset behavior yourself before introducing a broker.

File `EncodingProof.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class EncodingProof {
    public static void main(String[] args) {
        String json = "{\"name\":\"Hà\"}";
        byte[] utf8 = json.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        System.out.println("utf16Units=" + json.length());
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("roundTrip=" + json.equals(decoded));
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac EncodingProof.java
java EncodingProof
~~~

Output:

~~~text
utf16Units=13
utf8Bytes=14
roundTrip=true
~~~

This is an example **with valid UTF-8 bytes**. If bytes are already corrupted, `new String(...)` may substitute invalid characters; when strict data validation is needed, use `CharsetDecoder` from the earlier section.

## 10. Which Approach to Choose in a Real System?

### 10.1. Prefer TextMessage When the Data Is Fundamentally JSON Text

TextMessage is usually the clearer choice when:

- Services send/receive JSON primarily for API/business event integration.
- The team needs to inspect payloads via broker administration tools.
- There is no requirement to preserve the exact **byte sequence** sent by an external system.
- Both sides agree to serialize/parse JSON as a String.
- Using Spring's `MessageType.TEXT` converter or `SimpleMessageConverter` with String.

In return, Java Strings and JSON parsers still allocate memory/resources, and internal wire encoding depends on the broker; "readable TextMessage" does not guarantee a smaller message.

### 10.2. Prefer BytesMessage When a Byte-Level Contract Matters

BytesMessage fits well when:

- Non-Java consumers require **raw UTF-8 bytes** in an exact agreed format.
- Payloads are already serialized into `byte[]` by a JSON library, schema registry, or existing pipeline.
- There is a binary transport standard (Avro/Protobuf) or a payload with a signature/hash over the byte sequence; for JSON, a dedicated canonicalization policy is needed if signatures require exact bytes.
- You want to combine compression, encryption, or checksums at the application layer with a clear contract (at that point the body is no longer raw JSON text, and content encoding must be documented).
- You need to synchronize byte-level encoding between producer and consumer without relying on how the provider represents Strings.

In return, you must declare the charset and test invalid bytes; admin tools may display hex/base64 instead of JSON, and code must distinguish `BytesMessage` from TextMessage.

### 10.3. Do Not Choose Solely Because "BytesMessage Is Faster"

Benchmarking requires identical payload, schema, broker, network, delivery mode, consumer concurrency, and ACK/transaction settings. Measure:

- Message throughput and p50/p95/p99 latency.
- CPU and allocation/GC volume on Java producers/consumers.
- Message size on the wire or in the journal (if observable).
- Number of serialization/deserialization passes and byte copies in the converter.
- Ease of observability, debugging, and error handling in operations.

Jackson `writeValueAsBytes` may avoid one String allocation in certain pipelines, yet the JMS provider and network serialization can still introduce other copies. There is no "absolute speed win" solely from the JMS message type name.

## 11. Data Contract: More Important Than Text vs. Bytes

A versioned message contract should clearly specify:

~~~yaml
destination: orders.json.demo
eventType: order.created
schemaVersion: 1
bodyFormat: application/json
messageTypesAccepted:
  - TextMessage
  - BytesMessage
bytesCharset: UTF-8
requiredProperties:
  eventId: string
  schemaVersion: integer
  contentType: string
businessFields:
  eventId: string
  orderId: string
  customer: string
  amountVnd: integer
~~~

This is an **illustrative YAML contract document**, not a Spring Boot `application.yml` file. Properties like `contentType`, `charset`, and `schemaVersion` must be defined and validated consistently; no generic JMS mechanism turns them into an automatic schema validator.

Especially important:

1. **Body type**: use only one type (simpler), or allow both types during a migration phase? If allowing both, the decoder must handle both explicitly.
2. **Charset**: for BytesMessage JSON, standardize on UTF-8 and do not use `writeUTF`; if bytes in another encoding arrive, reject per policy.
3. **Schema version**: consumers must know which versions they can accept; do not blindly coerce into a new DTO if an incompatible field change occurred.
4. **Required/nullable fields**: Jackson parsing valid JSON does not mean the business contract is valid. Validate `eventId`/`orderId`/`amountVnd` after deserialization.
5. **Business identifier**: `eventId` in properties/body remains stable across retries for idempotent consumers; do not rely solely on `JMSMessageID`.
6. **Security**: payloads containing PII need transport encryption, destination ACLs, and avoiding full-body logging; readable JSON text is also easier to leak during uncontrolled debugging.
7. **Maximum size**: enforce payload limits before allocating large arrays, parsing deeply, or deserializing untrusted data. Large messages need broker-specific mechanisms or storing objects externally and sending a reference.

## 12. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cast to `TextMessage` fails | Producer sent `byte[]`/BytesMessage | Check original type; handle BytesMessage branch or standardize contract |
| `getBody(String.class)` fails | Body is actually a BytesMessage | Read `byte[].class` then decode with charset |
| JSON becomes `H` or corrupted Vietnamese accents | Charset mismatch or invalid UTF-8 replaced | Standardize on UTF-8, use strict decoder, inspect raw bytes |
| Parser hits strange characters at body start | BOM/prefix from `writeUTF` or another encoding | Send raw UTF-8 via `writeBytes`; do not use stream `writeUTF` for JSON |
| `MessageNotReadableException` | Reading a BytesMessage still in write-only mode | Call `reset()` before reading a newly created body; received messages start in read mode |
| `MessageNotWriteableException` | Modifying body of a received message in read-only mode | Create a new message or understand `clearBody()` |
| `receiveAndConvert` returns `byte[]` instead of DTO | Using SimpleMessageConverter | Use a Jackson converter with type ID or parse JSON explicitly |
| DTO sent as `ObjectMessage` | Default converter chose Java serialization | Register JSON converter and verify `targetType` |
| Jackson converter registered but fails to deserialize DTO | Missing type ID or incompatible mapping | Call `setTypeIdPropertyName` and align mappings |
| JSON parses fine but fields are wrong | Schema/version drift | Check version, nullable/required rules, and validation |
| Selector cannot filter `orderId` inside JSON | Selectors do not read JSON body | Promote required filter keys to JMS properties |
| Large byte bodies cause memory pressure | Reading whole body into unbounded arrays | Enforce size limits, streaming/broker large-message policy |
| Consumer receives duplicates | Retry/redelivery | Use business `eventId` + idempotent consumer |
| Handler fails repeatedly on malformed JSON | Poison message/invalid payload | Bounded retries, DLQ, observability, and schema validation |

A conversion error should not be retried infinitely if the payload cannot be parsed by the deployed schema. Separate permanent data errors from transient broker/network errors; configure retry/DLQ appropriately to avoid blocking the Queue.

## 13. Testing Strategy from Bottom to Top

### 13.1. Serialize/Deserialize Unit Tests

No broker needed:

- Serialize `OrderCreated` to String and `byte[]`.
- Read both back with Jackson.
- Test Vietnamese characters, special characters, numbers, and null/empty cases.
- Verify malformed UTF-8 is rejected when the contract requires strict decoding.
- Test unsupported `schemaVersion`, missing required fields, and invalid JSON syntax.

Never assume byte length equals String length; use `StandardCharsets.UTF_8` and assert only properties the code actually guarantees.

### 13.2. JMS MessageConverter Unit Tests

For `SimpleMessageConverter`, verify `String -> TextMessage` and `byte[] -> BytesMessage` using an accurate JMS `Session` mock/provider fixture. For `MappingJackson2MessageConverter`, test both `MessageType.TEXT` and `MessageType.BYTES`, type ID mappings, and encoding properties. Do not test only the sending side; the receiving side is usually where type ID issues show up.

### 13.3. Integration Tests with a Broker

A reliable integration test needs:

1. A real Artemis broker in the test environment (e.g., Docker/Testcontainers).
2. `ConnectionFactory` and `JmsTemplate` configured as in real deployment.
3. Sending one TextMessage and one BytesMessage with contract-compliant JSON.
4. Consumer receiving, distinguishing the original type, decoding Unicode properly, and deserializing the DTO.
5. Verifying metadata `schemaVersion`, `contentType`, and `eventId`.
6. Testing negative cases (wrong charset, invalid JSON, newer schema) alongside DLQ/retry mechanisms.
7. Checking timeouts, ACK, and rollback if the system requires delivery guarantees.

**Do not confuse converter unit tests with broker verification.** Mockito can verify `JmsTemplate.send` was called, but it does not prove two messages reached the Queue, persistence worked, or the consumer ACKed.

### 13.4. Multi-Language Integration Tests

If a Java producer talks to Python, Node.js, or another stack, run an **actual consumer in that language**. Test payloads with Vietnamese text, emojis, newlines, unknown fields, and changing `schemaVersion`. A JMS TextMessage does not mean every non-Java client infers the same contract automatically; use the right protocol/client and verify results end-to-end.

## 14. Self-Assessment Questions

**1.** Is JSON a JMS message type or a data format?

JSON is a data format. `TextMessage` and `BytesMessage` are JMS body types; JSON can reside in either.

**2.** What does `convertAndSend(queue, jsonString)` create with SimpleMessageConverter?

Normally a `TextMessage` because the Java value is a `String`.

**3.** What does `convertAndSend(queue, jsonBytes)` create with SimpleMessageConverter?

`BytesMessage` because the Java value is `byte[]`.

**4.** Does `MappingJackson2MessageConverter` send JSON DTOs as TextMessage by default?

No. According to Spring, this converter's default target is `MessageType.BYTES`; to use text, call `setTargetType(MessageType.TEXT)`.

**5.** Why is `bytesMessage.writeUTF(json)` not equivalent to `writeBytes(json.getBytes(UTF_8))`?

`writeUTF` uses a length-prefixed modified UTF-8 encoding designed for JMS streams; it is not a raw UTF-8 JSON body.

**6.** Why can `String.length()` differ from the number of UTF-8 bytes?

Java `String.length()` counts UTF-16 code units; Unicode characters can require multiple UTF-8 bytes.

**7.** Can `getBody(String.class)` be used on any UTF-8 JSON BytesMessage?

No. For a BytesMessage, read `byte[]` and then decode according to the contract.

**8.** Does the `contentType=application/json` property cause the JMS broker to parse JSON automatically?

No. That is application metadata; the broker does not automatically turn the body into a JSON AST.

**9.** Once a Jackson converter is registered, what must you pay attention to in order to receive a DTO back?

Type ID property/mappings, body type, encoding, and ensuring producer and consumer use compatible converters.

**10.** Is BytesMessage always faster than TextMessage?

No; you must benchmark the full path with the same provider, workload, conversion, and broker.

## 15. Official Documentation

- Jakarta Messaging 3.1 — Message Types, TextMessage, BytesMessage, `getBody`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API — `TextMessage`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/textmessage
- Jakarta Messaging API — `BytesMessage`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/bytesmessage
- Jakarta Messaging API — `Message#getBody`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Spring Framework — Sending a Message, SimpleMessageConverter: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — `MappingJackson2MessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Guide — Messaging with JMS (Jackson converter target TEXT): https://spring.io/guides/gs/messaging-jms/
- Spring Boot — JMS/Artemis support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Remember:** For JSON, choose **TextMessage** when you want clear, easily inspectable String exchange; choose **BytesMessage** when the contract requires raw bytes/UTF-8 or byte-level processing. Both require a schema, a charset/version contract, the right MessageConverter, and end-to-end testing; never treat a JMS message type as a JSON parser or a delivery guarantee.
