# JSON Conversion by Library and Active Spring Version

In Spring Messaging, JSON is an exchange format for payloads. To convert a Java object to JSON when sending and restore JSON back into an object when receiving, an application needs a **MessageConverter** compatible with the JSON library and Spring version in use.

Do not choose a converter solely based on a library name present on the classpath. Three factors must be clearly identified:

1. The Spring Framework or Spring Boot version managing the application.
2. The JSON library and major version in use, such as Jackson 2, Gson, or JSON-B.
3. The conversion layer: Spring Messaging, JMS, Kafka, AMQP, or HTTP. Each layer may have its own converter interface.

This lesson focuses on **Spring Messaging** and using Jackson 2 with **MappingJackson2MessageConverter**, then highlights what needs adjusting when a project uses a different library or Spring release line.

## 1. MessageConverter in Spring Messaging

Spring Messaging represents messages with **Message<?>**, consisting of a payload and headers. The payload can be a Java object, a string, or a byte array. When a message crosses a process or network boundary, the payload usually has to be converted to a transmittable format, such as JSON bytes.

The **org.springframework.messaging.converter.MessageConverter** interface has two primary operations:

- **toMessage(payload, headers):** converts an application object into a Spring Message.
- **fromMessage(message, targetClass):** converts the payload inside a Spring Message into the Java type requested by the consumer.

Send and receive flow:

~~~text
Producer object
      |
      | toMessage(...)
      v
Spring Message
  payload: JSON String / byte[]
  headers: contentType, ...
      |
      | channel / adapter / transport
      v
Consumer Spring Message
      |
      | fromMessage(...)
      v
Target Java object
~~~

A converter is responsible for payload conversion and may inspect headers to determine the format. A converter does not send messages through a broker by itself, choose queues/topics, or replace every transport's serializer. Channels, adapters, and transports remain responsible for delivery.

### Basic converters and JSON

Spring Messaging provides converters for different payload types:

| Converter | Primary data | Purpose |
|---|---|---|
| **StringMessageConverter** | String | Converts text to messages and back. Does not parse JSON into DTOs by itself. |
| **ByteArrayMessageConverter** | byte[] | Keeps payloads as bytes, suited when another layer handles serialization/deserialization. |
| **SimpleMessageConverter** | Certain simple types | Converts supported simple payload types; not a JSON object mapper. |
| **MappingJackson2MessageConverter** | Java objects and JSON | Uses Jackson 2 to serialize objects and deserialize JSON into the target type. |

Class names and packages matter greatly. **org.springframework.messaging.converter.MappingJackson2MessageConverter** is the converter for Spring Messaging. Other Spring modules also have their own JSON converters, which do not necessarily implement the same interface.

## 2. Choosing a JSON Library for the Project

### Jackson 2

Jackson 2 is commonly used with Spring Messaging via:

- **com.fasterxml.jackson.databind.ObjectMapper**
- **org.springframework.messaging.converter.MappingJackson2MessageConverter**
- Additional modules such as **jackson-datatype-jsr310** for Java Time.

**ObjectMapper** governs how JSON is read and written: field names, naming strategies, date/time formats, enums, nulls, unknown properties, and other rules. Configure a shared mapper for the application instead of instantiating a new mapper per message.

Java Time configuration example:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

**JavaTimeModule** enables Jackson to handle types like **Instant**, **LocalDate**, and **LocalDateTime**. Disabling **WRITE_DATES_AS_TIMESTAMPS** represents dates and times as ISO strings rather than numbers or arrays per the default configuration.

### Gson or JSON-B

If the project uses Gson or JSON-B, check the converter provided by the corresponding Spring module or integration library. Do not assume that merely adding a Gson/JSON-B dependency makes **MappingJackson2MessageConverter** switch to that library automatically.

If core Spring Messaging does not include a suitable converter in your version, you can write an adapter implementing **MessageConverter** to delegate to Gson or JSON-B. The adapter should handle at least:

- Converting payload objects into JSON.
- Converting JSON into the target type.
- Reading and writing **contentType**.
- Handling String or byte[] payloads according to the chosen contract.
- Reporting conversion errors clearly when JSON is invalid or the target type is incompatible.

Do not mix object mappers from multiple libraries in the same flow without a specific reason. Differences in naming, date/time, enums, and unknown fields can cause producer and consumer to interpret the same JSON differently.

## 3. Spring Versions and Library Compatibility

Spring Framework and JSON libraries have separate version lifecycles. Version selection must follow the application's dependency management, not just the latest version of each individual library.

| Application release line | What to verify |
|---|---|
| Spring Framework 5.3.x | Use the right Spring 5.3 APIs and a compatible Jackson 2 version. Spring 5.3 supports older Java baselines than Spring 6; do not copy a Spring 6 Java 17 setup verbatim into an older Java application. |
| Spring Framework 6.x | Requires Java 17 or higher. The Spring Messaging converter using Jackson 2 is named **MappingJackson2MessageConverter**; Jackson 2 classes live in namespace **com.fasterxml.jackson.***. |
| Spring Boot | Prefer the BOM/dependency management of the matching Boot line to align Spring Framework and Jackson. Avoid pinning individual Spring modules to mismatched versions. |
| Projects using Jackson 3 or a newer Spring major | Check the converter and package supported in that exact release. Jackson 3 has different APIs/packages from Jackson 2; do not pass a Jackson 2 **ObjectMapper** into a converter requiring Jackson 3 or vice versa. |

For the example below, the pinned versions are specifically **Spring Messaging 6.1.8, Jackson 2.17.1, and Java 17**. This is an illustrative version set so the code is reproducible; real projects should use versions verified as compatible by their own BOM or build.

### Why shouldn't you upgrade individual dependencies piecemeal?

An application may encounter errors such as:

- **NoSuchMethodError** when a Spring module was compiled against a different API than the runtime version.
- **ClassNotFoundException** or **NoClassDefFoundError** when a required Jackson module is missing.
- **NoSuchMethodError** or linkage errors when mixing Jackson major versions.
- **MessageConversionException** when the converter cannot read the payload or target type.
- Dates/times serialize successfully but fail to deserialize due to a missing Java Time module or inconsistent formatting.

When upgrading, inspect the dependency tree and run serialization/deserialization tests on both producer and consumer.

## 4. Content Type and Serialized Payload Form

The **contentType** header indicates what format the payload uses. For JSON, the common value is **application/json**.

For example, a Spring Message may carry:

~~~text
payload:
  {"orderId":"ORD-1001","amount":125.50}

headers:
  contentType: application/json
  id: ...
  timestamp: ...
~~~

**MappingJackson2MessageConverter** uses content type and converter settings to decide whether a payload can be converted. Set content type explicitly when creating messages, especially if messages traverse multiple adapters or systems.

### String and byte[] are two ways to store JSON

After serialization, JSON can be held in a Spring Message as:

- **String:** convenient when inspecting content directly or working with APIs expecting text.
- **byte[]:** well-suited for many transports since the payload is already bytes.

**MappingJackson2MessageConverter** supports configuring the serialized payload class. In the example, **String.class** is chosen so JSON appears as a string and output is easy to observe. If keeping the default byte array, decode the bytes with the right charset (usually UTF-8) when debugging.

Do not confuse **StringMessageConverter** with a JSON converter. StringMessageConverter can turn a JSON string into a text message, but it does not build an **OrderCreated** instance from a JSON string. Parsing into a DTO requires Jackson or another JSON library.

## 5. Complete Example: Serializing and Deserializing with Jackson 2

This example uses **MappingJackson2MessageConverter** to convert a Java record into a JSON String and read it back into a record. It runs standalone in the JVM without requiring a broker, WebSocket, or Spring application context.

### Project structure

~~~text
json-message-demo/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            messaging/
              JsonMessageExample.java
~~~

### Maven dependencies

Create **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>json-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.1.8</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.1</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
            <version>2.17.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java source

Create **src/main/java/com/example/messaging/JsonMessageExample.java**:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

public class JsonMessageExample {

    public record OrderCreated(
            String orderId,
            BigDecimal amount,
            Instant occurredAt
    ) {
    }

    public static void main(String[] args) {
        ObjectMapper objectMapper = new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter(objectMapper);

        // Choose String so the JSON payload can be read directly in the example.
        converter.setSerializedPayloadClass(String.class);

        OrderCreated event = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z")
        );

        MessageHeaders headers = new MessageHeaders(Map.of(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        ));

        Message<?> jsonMessage = converter.toMessage(event, headers);
        if (jsonMessage == null) {
            throw new IllegalStateException("Converter rejected the payload");
        }

        String json = (String) jsonMessage.getPayload();

        OrderCreated restored = (OrderCreated) converter.fromMessage(
                jsonMessage,
                OrderCreated.class
        );
        if (restored == null) {
            throw new IllegalStateException("Converter could not read the JSON");
        }

        System.out.println("contentType="
                + jsonMessage.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("json=" + json);
        System.out.println("restored=" + restored);
    }
}
~~~

### Running the program

From the directory containing **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.JsonMessageExample
~~~

Output:

~~~text
contentType=application/json
json={"orderId":"ORD-1001","amount":125.50,"occurredAt":"2026-11-07T03:00:00Z"}
restored=OrderCreated[orderId=ORD-1001, amount=125.50, occurredAt=2026-11-07T03:00:00Z]
~~~

Explanation:

1. **ObjectMapper** is configured with **JavaTimeModule** to handle **Instant**.
2. **MappingJackson2MessageConverter** uses that ObjectMapper for serialization and deserialization.
3. **setSerializedPayloadClass(String.class)** instructs the converter to store JSON as a String in the payload.
4. **MessageHeaders** sets **contentType** to **application/json**.
5. **toMessage** creates a Spring Message from the record.
6. **fromMessage** reads the JSON payload and reconstructs **OrderCreated**.
7. Inspecting the output shows that the timestamp, order ID, and amount are preserved across the round-trip.

This example tests conversion in memory. It has not sent JSON through a broker; a real adapter or transport still needs its own serialization, destination, and delivery semantics configuration.

## 6. Customizing ObjectMapper to Match the JSON Contract

ObjectMapper configuration must be consistent between producer and consumer. If both sides apply different rules, JSON may be syntactically valid yet fail to deserialize properly.

### Field names

You can use Jackson annotations to keep field names in JSON stable:

~~~java
public record CustomerEvent(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("display_name") String displayName
) {
}
~~~

JSON then uses **customer_id** and **display_name** even though the Java component names are camelCase.

### Unknown fields and version compatibility

When a consumer receives JSON containing newly added fields, the **FAIL_ON_UNKNOWN_PROPERTIES** policy determines whether Jackson rejects or ignores unmapped fields. If you need producers to upgrade independently from consumers, choose an intentional compatibility policy and test it.

Do not disable all checks by default. Required fields, new enum values, numeric types, and date/time formats can still cause errors or produce wrong data if unvalidated.

### Dates and times

- Use **Instant** for an absolute point in time.
- Use **LocalDate** for a calendar date without a time component.
- Use **OffsetDateTime** when preserving the offset is required.
- Use **LocalDateTime** only when the contract is genuinely timezone-agnostic and both sides agree on its meaning.

Do not send a date-time string without a timezone and assume every service will interpret it the same way.

### Enums and numeric values

Define a stable enum representation. If ordinals are used, reordering enum constants can cause old data to be misinterpreted; usually stable names or codes are preferable. For monetary values, use **BigDecimal** instead of **double** to avoid floating-point precision errors.

### Security during deserialization

Do not enable Jackson broad default typing for data arriving from untrusted systems. Polymorphic deserialization can introduce risks if arbitrary types are allowed. If polymorphism is required, use a subtype allowlist and an explicit contract; validate payloads before passing them into business logic.

## 7. When Do You Need Another Converter or Custom Adapter?

### Using the Spring Messaging converter

Use **MappingJackson2MessageConverter** when:

- Messages use **org.springframework.messaging.Message<?>**.
- Payloads must be converted to JSON using Jackson 2.
- The application wants control over ObjectMapper, content type, and String/byte[] payload form.

### Using JMS, Kafka, or AMQP converters

Transport layers have their own conversion APIs. For example:

- Spring JMS has **org.springframework.jms.support.converter.MessageConverter** to convert application objects with **jakarta.jms.Message**.
- Spring Kafka has serializers/deserializers for Kafka record keys and values; these are not Spring Messaging **MessageConverter**s.
- Spring AMQP has **org.springframework.amqp.support.converter.MessageConverter** to convert payloads with AMQP messages.

Even though these converters may all use Jackson, they are not directly interchangeable because message models and lifecycles differ. Use the converter for the right layer, or build an explicit adapter between Spring Message and the transport message.

### Using another JSON library

If the application standardizes on Gson or JSON-B, implement a suitable **MessageConverter** or use an adapter supported by the integration module. When writing a custom converter, verify:

- Accept only supported MIME types, such as **application/json**.
- Convert accurately between String/byte[] and the target class.
- Specify charset explicitly, preferring UTF-8.
- Translate parse errors into exceptions preserving the root cause.
- Keep the **contentType** header consistent.
- Include tests for nulls, empty payloads, missing fields, extra fields, and malformed JSON.

## 8. Testing Conversion

Do not only test that **toMessage** does not throw an exception. A good test must prove that the JSON payload and the re-read object have equivalent meaning.

Cases to test:

| Case | What to verify |
|---|---|
| DTO round-trip | Serializing then deserializing preserves business values. |
| Content type | Message carries **application/json** as required by the contract. |
| Java Time | **Instant**, **LocalDate**, or temporal types are read/written accurately. |
| BigDecimal | Monetary scale and values are preserved as required. |
| New fields | Older consumers handle new fields per the chosen compatibility policy. |
| Missing required fields | Conversion or validation rejects with a clear message. |
| Invalid JSON | Parse errors are detected and routed into error handling. |
| Wrong payload type | Converter rejects or returns a clear error instead of blindly coercing types. |
| Charset | JSON bytes are encoded/decoded consistently, typically UTF-8. |

With Spring Integration or listener containers, add integration tests to confirm the converter is registered on the right endpoint and errors follow the expected error flow. Unit tests on ObjectMapper do not prove the adapter is configured properly.

## 9. Common Mistakes

1. **Adding Jackson dependencies while payloads remain Strings.** StringMessageConverter or another converter may be getting selected. Check the actual converter in the chain.
2. **Importing the wrong MappingJackson2MessageConverter package.** Spring Messaging, Spring JMS, and other modules have separate converters; wrong imports lead to incorrect method signatures or semantics.
3. **Omitting contentType.** The converter may fail to match the MIME type or messages passing through adapters may have their format misinterpreted.
4. **Missing JavaTimeModule.** Jackson does not know how to handle certain java.time types unless the module is registered on the mapper.
5. **Producer and consumer using different ObjectMappers.** Naming strategies, date formats, enums, and unknown-field policies may diverge.
6. **Confusing conversion with transport.** toMessage creates a Spring Message; it does not send messages to Kafka, JMS, or WebSocket.
7. **Mixing Jackson 2 and Jackson 3.** Packages, ObjectMapper, and converter must belong to the same major version supported by the Spring release.
8. **Sending JPA entities directly.** Entities can carry lazy relationships, proxies, and internal fields. Use dedicated DTO/event contracts.
9. **Not testing schema evolution.** Adding, renaming, or removing fields can break consumers running older versions.
10. **Enabling unrestricted polymorphic default typing.** Creates risks of deserializing unintended types from untrusted payloads.

## 10. Key Takeaways

- Spring Messaging's **MessageConverter** converts payloads into Messages and Messages into target objects.
- **MappingJackson2MessageConverter** uses Jackson 2; ObjectMapper governs JSON rules.
- Set **contentType=application/json** and align schemas between producer and consumer.
- **StringMessageConverter** handles text; it does not replace a JSON object mapper.
- Use **JavaTimeModule** when contracts include Java Time types and choose explicit timezone-aware date/time formats.
- Pick Spring/Jackson versions from the project BOM or dependency management; do not mix modules across major versions.
- JMS, Kafka, and AMQP have their own converters/serializers; use the right converter for each transport layer.
- Test round-trips, schema compatibility, parse errors, and converter configuration at the endpoint.

Whenever changing JSON libraries or upgrading Spring, re-check the registered converter, ObjectMapper, content type, schema, and round-trip tests. Doing so ensures producers and consumers continue sharing the same data contract.
