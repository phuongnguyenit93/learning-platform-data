# Converting DTOs to JSON and Choosing a Converter by Spring Version

> **Topic:** Data conversion in Spring Framework JMS. This lesson walks through converting a **Java DTO** into JSON inside a JMS `TextMessage`, decoding JSON back into a DTO, and choosing the right `MessageConverter` across **Spring Framework 5/6/7, Spring Boot 2/3/4, and Jackson 2/3**. The focus is not only on "getting JSON sent", but also on stable type aliases, producer–consumer compatibility, deserialization security, testing, and upgrade planning.

## 1. The Big Picture

In a JMS application, the **Java payload** and the **wire message** are not the same thing. A DTO such as:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountCents) {
}
~~~

is a Java object. The broker does not understand this record structure on its own. We need **serialization** to JSON, then wrapping that JSON in a JMS message:

~~~text
Producer (Java/Spring)                             Broker/Consumer
-----------------------                            ---------------
OrderCreated DTO
   |
   v
JMS MessageConverter.toMessage(dto, session)
   |
   +--> JSON: {"eventId":"e-1","orderId":"O-42","amountCents":12500}
   +--> JMS TextMessage or BytesMessage
   +--> type property: _type = "order-created.v1"
   |
   v
JmsTemplate.convertAndSend(...) -------> JMS queue
                                              |
                                              v
                                  JMS MessageConverter.fromMessage(...)
                                              |
                                              v
                                  OrderCreated DTO at consumer
~~~

**Three independent decisions to clarify:**

1. **Choose the body format**: JSON in a `TextMessage` (easy to inspect, easy to interoperate) or a `BytesMessage` (byte form).
2. **Choose the converter/library**: Jackson 2 + `MappingJackson2MessageConverter` in Spring 6, or Jackson 3 + `JacksonJsonMessageConverter` in Spring 7.
3. **Choose the type/schema contract**: JSON field names, versioning, aliases, consumer DTO, allowlist, and upgrade strategy.

By default, `JmsTemplate` uses `SimpleMessageConverter` for basic JMS types. It **does not automatically know how to turn every custom record/POJO into JSON** simply because Jackson is on the classpath. For JSON DTOs, register a dedicated converter or serialize manually using a JSON mapper in the application layer and send the string (then decode it manually on the consumer).

## 2. What Does `MessageConverter` in Spring JMS Do?

The primary interface is:

~~~java
// Illustrative API signature; DO NOT recreate this interface in your application.
package org.springframework.jms.support.converter;

public interface MessageConverter {
    jakarta.jms.Message toMessage(
            Object object, jakarta.jms.Session session)
            throws jakarta.jms.JMSException,
                   MessageConversionException;

    Object fromMessage(jakarta.jms.Message message)
            throws jakarta.jms.JMSException,
                   MessageConversionException;
}
~~~

**Two directions:**

- `toMessage`: Java object → `jakarta.jms.Message`, using the `Session` provided by the JMS runtime to create a `TextMessage`/`BytesMessage`.
- `fromMessage`: JMS `Message` → Java object, reading the body and necessary metadata to determine which Java type to instantiate.

`JmsTemplate.convertAndSend(queue, dto)` calls `toMessage` before sending. `JmsTemplate.receiveAndConvert(queue)` or `receiveSelectedAndConvert` calls `fromMessage` on receive. `@JmsListener` can also use a converter configured on the listener container, though **not every listener automatically shares the same converter as every JmsTemplate** if there are multiple factories or beans.

### 2.1. Distinguishing Spring's Two `MessageConverter` Types

| API | Package | Works With | Where Used? |
| --- | --- | --- | --- |
| Spring **JMS** `MessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | `jakarta.jms.Message` (Spring 6/7) | `JmsTemplate`, JMS listener containers |
| Spring **Messaging** `MessageConverter` | `org.springframework.messaging.converter.MessageConverter` | `org.springframework.messaging.Message<?>` | `JmsMessagingTemplate`, `JmsClient` (Spring 7), other abstractions |
| Jackson JSON mapper | Jackson `ObjectMapper`/`JsonMapper` | Java objects ↔ JSON | Serialization engine invoked underneath by the converter |

**Do not mix up imports:** two classes may share the name `MappingJackson2MessageConverter` or `JacksonJsonMessageConverter` yet reside in **two different packages**. Throughout this lesson, all `JmsTemplate` configurations use the package **`org.springframework.jms.support.converter`**.

### 2.2. `SimpleMessageConverter` Does Not Solve JSON DTOs

`SimpleMessageConverter` commonly supports:
- `String` ↔ JMS `TextMessage`;
- `byte[]` ↔ `BytesMessage`;
- `Map` ↔ `MapMessage`;
- `Serializable` ↔ `ObjectMessage` (depending on usage).

With a custom DTO, you may hit a "cannot convert" error or accidentally fall back to Java native serialization if the DTO implements `Serializable`. **`ObjectMessage` is not JSON**; decoding Java objects from unknown messages also introduces deserialization and class-compatibility risks. Do not switch to `ObjectMessage` just to avoid configuring a JSON converter.

## 3. Converter Selection Matrix by Version

This is the most error-prone part when copying code from the internet:

| Stack in Use | JMS Namespace | Jackson Generation | JSON Converter in Spring JMS | Selection Guidance |
| --- | --- | --- | --- | --- |
| Spring Framework **5.3.x** / Spring Boot **2.7.x** | `javax.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` | Legacy; do not mix `jakarta.jms` code; plan an upgrade |
| Spring Framework **6.0–6.2** / Spring Boot **3.x** | `jakarta.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` | Right choice for Boot 3 projects; Spring 6.2 must include security patches |
| Spring Framework **7.0+** / Spring Boot **4.x** | `jakarta.jms.*` | Jackson **3.x** (preferred) | `JacksonJsonMessageConverter` | Primary choice for new Boot 4 applications |
| Spring Framework **7.0** still keeping Jackson 2 | `jakarta.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` **deprecated** | Temporary compatibility bridge for migration only; do not start new projects with this API |

**Version points to remember:**

- Spring Framework **6.x** does not have Spring Framework 7's `JacksonJsonMessageConverter`; use `MappingJackson2MessageConverter` for Jackson 2.
- Spring Framework **7.x** introduces `org.springframework.jms.support.converter.JacksonJsonMessageConverter` for Jackson 3. Jackson 2's `MappingJackson2MessageConverter` is marked deprecated starting in Spring 7.
- Jackson 3 moves core packages from `com.fasterxml.jackson.*` to `tools.jackson.*`; Jackson annotations such as `com.fasterxml.jackson.annotation.JsonProperty` remain under `com.fasterxml.jackson.annotation`.
- Spring Boot **4** defaults to Jackson 3 and uses modular starters; when using Artemis + JSON, ensure you include both the JMS/Artemis starter and the JSON/Jackson 3 starter/dependency.
- Spring Boot **3** normally manages Jackson 2; do not copy `tools.jackson.databind.*` code into a Boot 3 project expecting Spring to map it automatically.
- In **Spring 5**, the JMS API is still `javax.jms`, unlike the Spring 6/7 namespace. This is a class/bytecode-level change and cannot be fixed by merely changing one import if the JMS library/provider is incompatible.

### 3.1. Version Security: 2026 Advisory

Spring published **CVE-2026-41855** regarding untrusted deserialization in Jackson JMS converters. The minimum fixed releases published include **Spring Framework 6.2.19** and **7.0.8** (along with corresponding commercial support branches). Starting from these fixes, the `setTrustedPackages(String...)` API lets you restrict which Java packages may be used to decode types named in a message.

**Design implications:**

1. Do not expose an unpatched Jackson JMS converter on a queue with untrusted producers.
2. Prefer a **finite set of type aliases** (e.g. `order-created.v1`) mapped to application-defined DTOs rather than accepting arbitrary class names from headers.
3. In environments processing untrusted messages, restrict `trustedPackages` alongside broker role controls, payload validation, and patching. `trustedPackages` does not replace authorization/broker ACLs.
4. Do not use `"* "` or an arbitrary wildcard/broad package allowlist; accepted types should be explicitly declared in the message contract.
5. If your project runs older Spring 6.1 or 5.3 branches, check available patches and official support lifecycles; do not assume older Boot releases are safe by default.

The hands-on example below uses **Spring Boot 4.0.9** (aligned with Spring Framework 7.0.10 via the BOM), which is past the `7.0.8` patch milestone. The version numbers here describe **a verified compatible set**, not a recommendation to blindly upgrade all projects to a new major release without testing.

## 4. Goals of a Good JSON Message Contract

Before writing Java code, define the wire contract rather than accidentally depending on internal class names.

Example event JSON body:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500
}
~~~

Expected JMS metadata:

~~~text
_type = "order-created.v1"    (String property set by the converter)
eventId = "e-001"            (String property set by the application)
schemaVersion = 1            (int/String property per contract)
JMSCorrelationID = "e-001"   (JMS header)
~~~

**Guidelines:**
- `eventId` in the body helps consumers stay idempotent; `eventId` as a JMS property supports selectors/broker tooling.
- `_type` is an **application property** read/written by the converter to select the Java DTO, not the automatic `JMSType` header.
- `schemaVersion` is the business data version, not tied to Spring/Jackson versions.
- Avoid sending `demo.OrderCreated` as a type ID because Java package names can change during refactoring; an alias like `order-created.v1` is more stable.
- Represent monetary fields with `long amountCents` or an explicit decimal convention; avoid `double` for currency calculations.
- Specify encoding explicitly (JSON `TextMessage` is a string; `BytesMessage` needs agreed UTF-8) and payload size limits to prevent memory pressure.

**Important:** valid JSON does not guarantee schema compatibility. When a v1 consumer encounters a v2 event with a new field, you need a policy: ignore unknown fields, reject unsupported versions, or route via a schema registry. Never change the meaning of a field while keeping the old version.

## 5. Configuring the Jackson 2 JSON Converter for Spring Boot 3.x / Spring Framework 6.x

While still on Spring Boot 3 (e.g. Spring 3.5.x paired with Framework 6.2.x), use:

~~~java
// Snippet for Spring Framework 6.2.19+ / Jackson 2.
// Place inside @Configuration; imports are listed below.
@Bean
MappingJackson2MessageConverter jmsJsonConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created.v1", OrderCreated.class));

    // Available since Spring Framework 6.2.19 (absent in older 6.2).
    converter.setTrustedPackages("demo");
    return converter;
}
~~~

Corresponding imports:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
~~~

With this code, `OrderCreated` is a DTO in the project's `demo` package. Add Jackson 2 to the build if the project only pulls JMS/Artemis without a JSON library:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

The two snippets above are **configuration snippets**, not a complete runnable Boot 3 project; Spring Boot/Gradle versions and the DTO must be supplied by the project. For Spring 6.1 or 6.2 prior to 6.2.19, `setTrustedPackages` may not exist yet; **apply the patch first** rather than removing this restriction just to make code compile on a vulnerable release.

**Key steps:**
- `setTargetType(MessageType.TEXT)` creates a `TextMessage`; **by default, the Jackson JMS converter creates a `BytesMessage`**, not a TextMessage.
- `setTypeIdPropertyName("_type")` sets the property used for decoding on the receiving side. If unconfigured, `fromMessage` may not know which DTO type to instantiate.
- `setTypeIdMappings` maps fixed aliases to Java classes; the consumer does not depend on serialized class names on the wire.
- `setTrustedPackages` adds an extra layer of restriction for dynamic class names not found in the map; the alias map should be curated separately.
- The converter configuration should be an **immutable singleton bean after startup**. Never mutate mappings/trustedPackages per request.

If you need to inject a custom Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper` to handle dates/times or special modules, use the mapper constructor in Spring 6.1+ or `setObjectMapper` depending on version. Avoid creating a hidden mapper that differs from the service's data configuration and produces inconsistent JSON.

## 6. Configuring the Jackson 3 Converter for Spring Boot 4.x / Spring Framework 7.x

In Spring Boot 4, use the new class:

~~~java
// Spring Framework 7.0.8+ / Jackson 3 snippet.
@Bean
JacksonJsonMessageConverter jmsJsonConverter() {
    JacksonJsonMessageConverter converter =
            new JacksonJsonMessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created.v1", OrderCreated.class));
    converter.setTrustedPackages("demo");
    return converter;
}
~~~

Imports differ from Jackson 2 in the **converter class name**:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;
~~~

If constructing a Jackson 3 JSON mapper manually, import from `tools.jackson.databind.*` / `tools.jackson.databind.json.JsonMapper` per the Jackson 3 API and consider using `JsonMapper.builder()`. **Do not** pass `com.fasterxml.jackson.databind.ObjectMapper` (Jackson 2) into the Jackson 3 converter constructor; the two generations do not share Java types. Only use a mapper with the modules you actually need, and avoid implicitly trusting arbitrary class names declared by messages.

With Spring Boot 4, a **Spring JMS** `MessageConverter` bean is wired into the auto-configured `JmsTemplate` and the default listener factory when auto-configuration conditions are met. If any template/factory is created manually, you must call `setMessageConverter(converter)` explicitly. Do not infer that every custom listener factory received the bean just because it exists.

## 7. Complete Hands-On Example: DTO → JSON TextMessage → DTO

The following example uses **Spring Boot 4.0.9 + Spring Framework 7.0.10 + Jackson 3 + Java 17**, with an external ActiveMQ Artemis broker. The goal is to verify both the **actual JSON body** and **DTO decoding**. Because there is only one test thread/task, the code receives synchronously on a dedicated queue and does not run a competing parallel listener.

### 7.1. Environment Setup

Requirements:
- JDK `17+`, Gradle `8.14+` or `9.x`, and Maven Central access to download dependencies.
- Artemis broker at `tcp://localhost:61616`, account `demo/demo` **for an isolated learning environment only** or valid credentials for an existing test broker.
- An **anycast** queue named `demo.json.dto` pre-provisioned, or a broker permitting queue auto-creation. In real environments, pre-create queues to control permissions.
- No other consumer occupying the test queue, or only consumers using a matching selector.

Never use a production queue for demos because `receive` can acknowledge/consume messages. When using Docker, you can run an Artemis broker in a container exposing port 61616; consult the image/broker version docs for credentials and persistence rather than assuming all images share the same account.

### 7.2. Project Structure

~~~text
jms-dto-json/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JsonJmsApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-dto-json'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-jackson'
}
~~~

The Artemis starter provides JMS and the broker client; the Jackson starter provides Jackson 3 and JSON infrastructure. `io.spring.dependency-management` imports the Spring Boot managed BOM. Keep versions compatible within one dependency set, and avoid accidentally adding both Jackson 2 and Jackson 3 and injecting the wrong `ObjectMapper`.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

**Security:** the username/password here are dummy credentials for a learning broker. In real systems, supply credentials via `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` or a secret store; never commit real passwords. `mode: native` ensures the app connects to the specified broker instead of unexpectedly starting an embedded broker.

### 7.3. Runnable Java Code

`src/main/java/demo/JsonJmsApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.UUID;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@SpringBootApplication
public class JsonJmsApplication {

    private static final String QUEUE = "demo.json.dto";

    public record OrderCreated(
            String eventId,
            String orderId,
            long amountCents) {
    }

    public static void main(String[] args) {
        SpringApplication.run(JsonJmsApplication.class, args);
    }

    @Bean
    JacksonJsonMessageConverter jsonJmsConverter() {
        JacksonJsonMessageConverter converter =
                new JacksonJsonMessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(
                "order-created.v1", OrderCreated.class));
        converter.setTrustedPackages("demo");
        return converter;
    }

    @Bean
    ApplicationRunner run(
            JmsTemplate jmsTemplate,
            JacksonJsonMessageConverter converter) {

        return args -> {
            String eventId = UUID.randomUUID().toString();

            OrderCreated outgoing =
                    new OrderCreated(eventId, "O-42", 12_500L);

            jmsTemplate.setReceiveTimeout(5_000L);

            // Converter runs before MessagePostProcessor.
            jmsTemplate.convertAndSend(QUEUE, outgoing, message -> {
                message.setJMSCorrelationID(eventId);
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            System.out.println("SEND_OK");

            String selector = "eventId = '" + eventId + "'";
            Message raw = jmsTemplate.receiveSelected(QUEUE, selector);

            if (!(raw instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected TextMessage within 5000 ms");
            }
            System.out.println("WIRE_TEXT_MESSAGE=true");

            // Do not assert property order in JSON.
            String json = text.getText();
            if (!json.contains("\"eventId\"")
                    || !json.contains("\"orderId\"")
                    || !json.contains("\"amountCents\"")) {
                throw new IllegalStateException("JSON fields missing");
            }
            System.out.println("JSON_FIELDS_PRESENT=true");

            String typeAlias = raw.getStringProperty("_type");
            if (!"order-created.v1".equals(typeAlias)
                    || raw.getIntProperty("schemaVersion") != 1) {
                throw new IllegalStateException(
                        "Type alias or schema version mismatch");
            }
            System.out.println("TYPE_ALIAS_OK=order-created.v1");

            Object restored = converter.fromMessage(raw);
            if (!(restored instanceof OrderCreated incoming)
                    || !outgoing.equals(incoming)) {
                throw new IllegalStateException("DTO mismatch");
            }

            System.out.println("DTO_ROUNDTRIP_OK=true");
        };
    }
}
~~~

**Points to note when reading the program:**

1. `@SpringBootApplication` includes component scan and auto-configuration, creating a `JmsTemplate` from the Artemis `ConnectionFactory`.
2. The `JacksonJsonMessageConverter` bean belongs to the **Spring JMS converter package**, so Spring Boot can wire it into the auto-configured JmsTemplate.
3. `MessageType.TEXT` forces the converter to produce a JMS `TextMessage` containing JSON; omitting this line defaults to `BytesMessage`.
4. `_type` is the property written by the converter according to the alias mapping `order-created.v1` → `OrderCreated.class`. Aliases avoid sending raw Java FQCNs and limit the handled type set.
5. `setTrustedPackages("demo")` uses the patched allowlist API; the demo only accepts the defined domain package for dynamic type lookup. Mappings explicitly define the event types used in the lesson.
6. `MessagePostProcessor` sets `eventId`, `schemaVersion`, and the correlation ID **after the DTO has already been converted**, right before sending. It does not serialize the body itself.
7. `receiveSelected` receives the raw message with a matching `eventId` property; using UUID isolates data from other test runs.
8. Upon seeing `TextMessage`, the program reads the raw wire JSON and checks the three fields by name, **without depending on JSON property ordering**.
9. `converter.fromMessage(raw)` uses the type alias to choose `OrderCreated`, decodes the JSON, and compares against the original record.
10. If the broker is unreachable, queue/ACL is wrong, selector mismatches, or timeout expires, the program throws an exception; it never reports a false PASS.

The structure above is **a standalone Spring Boot program** within a project containing the accompanying files. `OrderCreated` is a nested public record inside `JsonJmsApplication`; Java records provide value-based `equals`, making them ideal for round-trip comparison.

### 7.4. Running and Reading Output

In the project directory, with Gradle, JDK, and the broker ready:

~~~bash
gradle bootRun
~~~

If sending/receiving succeeds, the program prints these lines (Spring Boot and Artemis may also print additional logs):

~~~text
SEND_OK
WIRE_TEXT_MESSAGE=true
JSON_FIELDS_PRESENT=true
TYPE_ALIAS_OK=order-created.v1
DTO_ROUNDTRIP_OK=true
~~~

The example omits printing the UUID so sample output stays stable. Actual JSON content may vary in field ordering, character escaping, or whitespace depending on the mapper; validate JSON using parsing/schema snapshots rather than byte-for-byte string comparison unless canonical JSON is required.

**When no broker is available:** do not misclassify a `connect refused` error as a converter error. First check `spring.artemis.broker-url`, credentials, queue existence, and send/consume permissions. On a machine without Gradle or a broker, the code is designed to run, but this sample output cannot be claimed as an observed execution result on the reader's machine.

### 7.5. Why Not Use `receiveAndConvert` Immediately in the Demo?

It could be shortened to:

~~~java
// Snippet: uses a selector like the program above.
Object received =
        jmsTemplate.receiveSelectedAndConvert(
                "demo.json.dto", "eventId = 'e-001'");
~~~

This is a snippet (only works if the matching message is still on the queue), not a drop-in replacement when the program uses a random UUID. That method receives and converts in one step; in our experiment, we deliberately receive the `raw Message` to **inspect the JSON body, type alias, and version before calling `fromMessage`**. Both approaches are valid.

### 7.6. Automated Testing Without a Real Broker

**Unit** tests should focus on the converter:
1. Mock or create a fake `Session` returning an appropriate `TextMessage`.
2. Call `converter.toMessage(dto, session)`, asserting message type, JSON, and alias.
3. Call `converter.fromMessage(message)`, comparing field values.
4. Test invalid type aliases, malformed JSON, missing required fields, missing metadata, or unsupported versions.

This is a **testing procedure**, not standalone runnable unit test code because it requires a concrete JMS Session implementation/mock framework. Integration tests use an isolated broker or real container to verify that actual producers and consumers share the same converter; do not confuse converter unit tests with connectivity/ACL/broker tests.

## 8. When Using `@JmsListener`: Producer and Consumer Must Share the Contract

In real projects, the producer may be one app and the consumer another app or written in another language. When using Spring Boot auto-configuration and a valid `MessageConverter` bean, the default JMS listener factory can also use that bean. However, **if there is a custom container factory** or another app, the corresponding converter must be configured.

Example in a Spring consumer bean (snippet, do not run on the same queue as the synchronous receive in Section 7):

~~~java
// Placed inside a @Component of an application with @EnableJms enabled.
@JmsListener(destination = "orders.events")
public void handle(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

When the metadata has type alias `order-created.v1` and the receiving converter resolves the DTO, the listener can accept `OrderCreated`. If the annotation/method signature or listener factory uses a different converter, an error will occur before or when invoking the handler.

**Special notes:**
- `@JmsListener` on a real queue can compete for messages with other consumers. Do not attach it to the same queue as the demo's `receiveSelected`.
- If the consumer is written in Node.js, Go, or another stack, it **cannot use a Java class name** in `_type`. Provide schema version and event type as language-independent aliases.
- If the producer uses a JSON `TextMessage` while the consumer expects `BytesMessage`/`ObjectMessage`, the body types will not match; align the format before deployment.
- For request–reply, `JMSCorrelationID` links the flow, but does not solve schema/DTO mapping on its own.

### 8.1. Should You Use `JmsMessagingTemplate` or `JmsClient`?

- `JmsTemplate` is the core API where the Spring JMS `MessageConverter` is directly visible.
- `JmsMessagingTemplate` operates at the Spring Messaging layer and has its own converter/header-mapping mechanism.
- Spring Framework **7.0** adds the fluent `JmsClient`; it builds on `JmsTemplate` but leans toward `org.springframework.messaging.Message`.
- You cannot take an `org.springframework.jms.support.converter.JacksonJsonMessageConverter` bean and assume it is an `org.springframework.messaging.converter.MessageConverter`. When switching abstractions, verify the conversion chain and configure accordingly.

This lesson uses `JmsTemplate` to avoid mixing the two SPIs. For a new Boot 4 project with `JmsClient`, the choice of client API is separate from choosing the JSON wire format.

## 9. Operating Type IDs Safely for the Long Term

### 9.1. Why Is `setTypeIdPropertyName` Important?

The JSON converter needs to know the **target Java type** during `fromMessage`. With `MappingJackson2MessageConverter`/`JacksonJsonMessageConverter`, setting `setTypeIdPropertyName("_type")` makes the producer write the data type into a JMS property and the consumer read it to find the matching class.

If unset, `toMessage` can still produce JSON, yet `fromMessage` on receive may report a missing type ID because the converter **lacks enough information to pick a DTO**. This is a common bug when testing send without testing receive.

### 9.2. Why Are Aliases Better Than FQCNs?

**Fragile:**

~~~text
_type = "com.example.internal.dto.OrderCreated"
~~~

**More durable:**

~~~text
_type = "order-created.v1"
~~~

Package renames, module splits, moving classes, or non-Java consumers are much less disruptive with a stable alias. When a new incompatible version arrives, introduce a new alias `order-created.v2` and maintain the corresponding type mapping during migration.

The alias does not strictly have to live inside the body; it can be a JMS application property. However, you must agree on which consumers may read and filter on this property.

### 9.3. Trusted Packages, Alias Maps, and Producer Controls

`setTrustedPackages("demo")` restricts resolving **class names stated directly** in a message when they do not match a defined alias. Therefore:
- **The alias map must be finite and reviewed**; never auto-scan the classpath to expose every DTO.
- **Never feed user-supplied message types into a dynamic map**.
- With shared brokers or untrusted producers, enforce JMS `send` ACLs on queues, payload size, versions, and formats; do not trust all content simply because it carries a valid `_type`.
- Avoid uncontrolled Jackson polymorphic default typing and native Java object deserialization on untrusted payloads.
- Apply Spring/Jackson patches, scan dependencies, and verify the actual `spring-jms` version in the dependency tree.

These mechanisms address different risks: the **alias map** defines the contract, **trusted packages** limit dynamic resolution, **broker ACLs** control who can send/receive, and **validation** checks business content. None of them completely replaces the others.

## 10. Versioning: What Happens When the DTO Changes?

Suppose version v1 is:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500
}
~~~

v2 adds a field:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500,
  "currency": "VND"
}
~~~

If a v1 consumer does not know `currency`, there are three strategies:
1. **Tolerant reader:** ignore unknown fields, while checking mapper configuration and whether the new field is genuinely optional.
2. **Separate alias:** send `order-created.v2`, and upgrade consumer mappings to accept both v1 and v2 during the transition period.
3. **Versioned envelope:** separate an event envelope with `schemaVersion`/`eventType` from the payload to explicitly pick a decoder and validate.

Do not confuse **Spring Framework 7** with **business schema version 7**. Converter/Jackson versions are internal choices; a Boot 3 producer and a Boot 4 consumer can exchange messages **as long as they share the JSON/JMS property contract**. Sharing the same Java class is not required; using Java on both sides is not even required.

### 10.1. Compatibility/Breaking Changes Are Not Always Obvious

| Change | Risk | Strategy |
| --- | --- | --- |
| Adding an optional field | Older consumers might reject unknown properties | Policy to ignore unknown fields + tests |
| Renaming `orderId` to `id` | Older consumers fail to read it | Support alias, dual-write/dual-read phase |
| Changing `amountCents` from `long` to `double` | Amount/precision drift | Keep currency units and numeric types stable |
| Changing currency unit from cents to VND/dong | Same field, different meaning | New field/new schema version, explicit migration |
| Removing a field needed by consumers | Missing data/validation failure | Deprecation period, monitoring |
| Adding a subtype selected by `_type` | Deserialization risk and new contract | Allowlist mapping + trusted packages |
| Replacing Jackson 2 with Jackson 3 | JSON/naming/date/config defaults may differ | Golden messages + cross-version tests |

Build realistic JSON fixtures and verify wire content and consumer decoding across every supported version pair. Never compile each app independently and assume the two apps are compatible.

## 11. Migrating from Spring Boot 3 to Boot 4

A safe migration plan:

1. **Inventory dependencies**: Boot version, Spring Framework/`spring-jms`, Jakarta Messaging, Jackson modules, Artemis JMS client, custom converters, and listener factories.
2. **Lock down the contract first**: wire JSON, `MessageType.TEXT`, `_type` aliases, `schemaVersion`, message selectors, naming/timezone/null handling.
3. **Patch current branches**: especially Spring 6.2.19+ if any queue has untrusted producers.
4. **Add integration tests for Boot 3 producer ↔ Boot 4 consumer** and vice versa on a test queue; check both payload and properties.
5. **Switch the converter Java API**: `MappingJackson2MessageConverter` → `JacksonJsonMessageConverter`, and replace Jackson 2 mapper APIs with their Jackson 3 equivalents.
6. **Update Jackson imports** where needed: Jackson 3 core moves to `tools.jackson.*`; Jackson annotations remain in `com.fasterxml.jackson.annotation`.
7. **Keep aliases unchanged** if the schema is unchanged so older consumers still receive messages.
8. **Deploy in compatibility order**: consumers support old/new formats first, then enable the new producer format; ensure a rollback plan exists.
9. **Monitor conversion errors**: number of rejected messages, missing `_type`, unknown type aliases, invalid JSON, schema mismatches, DLQ, and replays.
10. **Clean up legacy dependencies** once all services have migrated to avoid inadvertently keeping two Jackson generations on the classpath.

**Do not mix converter beans in the same application context without specifying which one to use.** If multiple `MessageConverter` beans implement the same interface, auto-configuration may lack a single candidate to pick; Spring may require `@Primary`/`@Qualifier` or explicit configuration on each template/factory.

## 12. Common Errors When DTOs Fail to Convert to JSON

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `convertAndSend(dto)` creates `ObjectMessage`, not JSON | Using `SimpleMessageConverter` | Register a Jackson JMS converter |
| `NoClassDefFoundError: javax.jms...` | Legacy Spring 5/JMS library using `javax.jms` in a Boot 3/4 app | Align `jakarta.jms` client and dependencies |
| `ClassNotFoundException: JacksonJsonMessageConverter` | App uses Spring Framework 6 or `spring-jms` without the 7.0 class | Use `MappingJackson2MessageConverter` in Spring 6; do not copy 7 APIs |
| `NoClassDefFoundError: com.fasterxml.jackson.databind...` | Using Jackson 2 classes in a Jackson 3-only environment | Switch to the Jackson 3 converter/mapper or add the appropriate dependency |
| `NoClassDefFoundError: tools.jackson...` | Using the Jackson 3 converter without Jackson 3 runtime | Add `spring-boot-starter-jackson` or Jackson 3 libraries |
| Producer sends successfully, consumer fails to decode | Missing `_type` configuration or missing matching mapping | Align `setTypeIdPropertyName` and `setTypeIdMappings` on both sides |
| `MessageConversionException` about untrusted package | Dynamic type ID is outside the allowlist | Do not remove the allowlist; fix the alias/mapping or configure permitted packages |
| Consumer expects `TextMessage` but sees `BytesMessage` | Converter defaults to BYTES | Set `setTargetType(MessageType.TEXT)` on producer; align wire contract |
| `@JmsListener` receives `String` instead of DTO | Container uses a different converter, or method signature mismatch | Configure the listener factory and pick the right converter |
| Wrong JSON date/time fields | Mapper has different modules/format/timezone | Align Jackson modules and schema; test sample timestamps |
| Error serializing record/DTO | Incompatible constructor, field visibility, module, or builder | Unit test mapper and DTO independently; check Jackson generation |
| `_type` value changes after package refactor | Type ID coupled to Java FQCN | Use stable aliases instead of class names |
| JSON payload is valid but rejected by business logic | Missing required field/null/number/schemaVersion mismatch | Validation + contract/schema tests |

### 12.1. Why Not "Fix" It by Dropping the Converter?

If you replace `convertAndSend(dto)` with `convertAndSend(objectMapper.writeValueAsString(dto))`, the body may be JSON, yet on the consumer side `SimpleMessageConverter` normally returns a **String** rather than `OrderCreated`. This approach **can be valid** when services intentionally manage serialization/deserialization outside the Spring JMS converter. However, never assume a listener will magically map a `String JSON` into a DTO.

If choosing manual JSON, document the method explicitly:
- Producer uses Jackson to serialize DTO → String, sending a `TextMessage`.
- Consumer receives String → Jackson deserializes to a **fixed schema/type**, never trusting a raw class name from the message.
- Manage encoding/mapper/date/timezone, versioning, and security.
- Never mix a manual-parse consumer with a consumer expecting automatic JMS conversion on the same queue without testing.

### 12.2. Do Not Touch QoS Improperly

`MessageConverter` determines **the body and certain type-id metadata**; it is not the place to control delivery mode, priority, or expiration. `JMSDeliveryMode`/`JMSPriority`/`JMSExpiration` are applied by the producer/provider on send. If QoS is needed, configure the producer/template/send operation separately. Do not call `message.setJMSExpiration(...)` inside a converter and expect TTL to be honored.

### 12.3. Be Careful with Retries and Dead-Letter Queues

Conversion errors on receive can cause the listener to roll back and the broker to redeliver repeatedly. Limit retries, route invalid messages to a DLQ per broker policy, track retry counts, and establish safe remediation. For messages with permanent schema errors, infinite retries will never make the message valid. **Do not delete production messages or mutate payloads directly** just because a new converter cannot parse them without a reconciliation/replay plan.

## 13. QA Checklist Before Production

- [ ] Exact **Boot/Framework/Jackson/JMS provider** versions and `javax.jms`/`jakarta.jms` namespace verified.
- [ ] Correct **Spring JMS converter package** selected, not confused with Spring Messaging converter.
- [ ] For Boot 3: Jackson 2 + `MappingJackson2MessageConverter`; for Boot 4: Jackson 3 + `JacksonJsonMessageConverter`.
- [ ] Appropriate security patches applied; no JMS converter accepting untrusted types on an unpatched Spring version.
- [ ] `setTargetType(MessageType.TEXT)` configured if the wire contract requires JSON TextMessage.
- [ ] `setTypeIdPropertyName` and fixed alias mappings configured for consumer deserialization.
- [ ] Type aliases, `trustedPackages`, broker ACLs, and payload validation enforced.
- [ ] Converter properly wired into the actual JmsTemplate and listener containers.
- [ ] `schemaVersion`, `eventType`/`eventId`, JSON naming, timezone, and null handling documented in the contract.
- [ ] Bidirectional converter tests covering valid DTOs, malformed JSON, missing fields, unknown aliases, and new fields.
- [ ] Integration tests with a real broker/isolated container; cross-version producer/consumer tests during migration.
- [ ] DLQ/backoff/idempotency in place when consumers fail to read JSON or hit processing errors.
- [ ] Dependencies audited to ensure both Jackson 2 and 3 or both JMS namespaces are not pulled unintentionally.

### Self-Check Questions

1. Why is having `jackson-databind` on the classpath not enough for `JmsTemplate.convertAndSend(OrderCreated)` to automatically produce JSON?
2. When using Spring Boot 3.5.x, which JMS JSON converter class is appropriate, and why cannot a Spring 7 example be copied verbatim?
3. What is the difference between `org.springframework.jms.support.converter.MessageConverter` and `org.springframework.messaging.converter.MessageConverter`?
4. Why do `MappingJackson2MessageConverter`/`JacksonJsonMessageConverter` send `BytesMessage` by default, and when is `MessageType.TEXT` needed?
5. What happens if the producer sends JSON but the consumer lacks `_type` or an alias mapping?
6. Why is a type alias like `order-created.v1` better on the wire than the Java class name `demo.OrderCreated`?
7. Why is `setTrustedPackages` needed on JMS converters in Spring 7.0.8+ or Spring 6.2.19+ when receiving messages from untrusted sources?
8. Can a Boot 3 producer and a Boot 4 consumer communicate over JMS without sharing the same Jackson major version?
9. If a schema adds a `currency` field, what tests are needed before publishing v2 events to a shared queue?
10. If a listener receives invalid JSON and rolls back continuously, will persistent delivery mode fix the conversion error on its own?

**Remember:** DTO → JSON in JMS is a **converter + wire format + type/schema contract + version alignment + trust boundary** problem, not a single line of `convertAndSend`. With **Spring Framework 6 / Boot 3**, use Jackson 2 and `MappingJackson2MessageConverter`; with **Framework 7 / Boot 4**, prefer Jackson 3 and `JacksonJsonMessageConverter`. Maintain stable aliases, restrict trusted packages, and test across versions so upgrades do not disrupt producers or consumers.

## References

1. Spring Framework 7 – Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
2. Spring Framework 6.2 – `MappingJackson2MessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
3. Spring Framework 7.0 – `JacksonJsonMessageConverter` API: https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html
4. Spring Boot 4 – JMS and Artemis: https://docs.spring.io/spring-boot/4.0/reference/messaging/jms.html
5. Spring Boot 4 – JSON/Jackson 3: https://docs.spring.io/spring-boot/4.0/reference/features/json.html
6. Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
7. Spring Framework Security Advisory, CVE-2026-41855: https://spring.io/security/cve-2026-41855/
8. Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
