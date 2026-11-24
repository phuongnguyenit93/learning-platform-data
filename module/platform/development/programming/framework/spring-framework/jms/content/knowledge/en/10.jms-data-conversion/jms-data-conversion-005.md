# Type Information, Type ID Mapping, and Type Allowlists in Spring JMS

> **Goal:** Understand how JMS messages convey data types, configure type ID-to-DTO mappings for JSON conversion, enforce a **type allowlist** before deserialization, protect consumers from spoofed metadata, and maintain cross-service contracts across versions.

**Technical scope:** Java 17+, Jakarta Messaging, Spring JMS **6.2.19+** with Jackson 2, with a Spring Boot 3.5.x hands-on example using patched dependencies. Spring Framework 7.x uses the corresponding Jackson 3 generation converters; consult its separate API docs. A key patch for this topic is **CVE-2026-41855**, published on 08/06/2026, affecting Jackson JMS converters when processing messages from untrusted sources. The illustrative example combines a **strict type-ID allowlist** and `setTrustedPackages(...)` on patched Spring.

## 1. Why Is Type Information Needed?

A producer might send the JSON string:

~~~json
{"invoiceId":"INV-0007","totalMinor":5500}
~~~

However, from those two fields alone, the consumer does not know whether to instantiate a Java `InvoiceCreated`, `InvoicePaid`, or another type. If a queue/topic carries multiple event types, the system must have a **data classification contract** independent of accidental field-name overlap.

Example contract:

~~~text
Destination: billing.events
JMS property: _type = "invoice-created-v1"
JMS body:     {"invoiceId":"INV-0007","totalMinor":5500}

Broker -> JMS TextMessage
           |
           +-- read _type property
           +-- verify alias belongs to ALLOWLIST
           +-- alias -> registered Java DTO
           +-- Jackson parses JSON -> DTO
           +-- validation -> business handler
~~~

Here `_type` is an **application-agreed JMS message property**, not a mandatory field of the JMS specification. It is **untrusted data** until verified. Sender and receiver must agree on the property name, alias values, body format, schema, and handling of unsupported versions.

### Goals of a Type ID

- **Dispatch:** pick a DTO/handler from a published set of message types.
- **Compatibility:** keep wire type names stable when refactoring packages or renaming Java classes.
- **Cross-language:** non-Java producers understand `invoice-created-v1` without needing to know `com.example.billing.InvoiceCreatedV1`.
- **Observability:** record type ID/version in metrics, routing, DLQ, and tracing.
- **Security:** instantiate only objects from a reviewed type set; prevent payloads from specifying arbitrary Java classes.
- **Versioning:** separate v1 and v2 schemas that have different semantics.

A type ID **does not** automatically validate that `totalMinor` is valid, does not guarantee exactly-once delivery, and does not replace transactions/ACK.

## 2. Distinguishing Common Metadata Layers

| Term | Where Is It? | Meaning |
| --- | --- | --- |
| `TextMessage` / `BytesMessage` / `ObjectMessage` | JMS body type | How data is transported; does not yet specify a business DTO |
| `JMSType` | JMS standard header | Message type label per producer/consumer contract |
| `_type` | Application-named JMS property | Property that `MappingJackson2MessageConverter` reads to select a Java type |
| `eventType` | Field in JSON envelope | Business event type, framework-independent |
| `schemaVersion` | Field in JSON envelope or metadata | Schema version and compatibility rules |
| `@JsonTypeInfo` / `@class` | Jackson polymorphic JSON mechanism | Selects subtypes at the JSON layer; can create its own attack surface |

**Do not equate them automatically.** `JMSType="InvoiceCreated"` does not make the converter read the `_type` property unless you write a corresponding adapter. `eventType` inside the JSON body cannot be read directly by a JMS selector. `TextMessage` is a string; turning JSON into a Java DTO is the job of the converter/parser. `ObjectMessage` uses Java native serialization, completely different from the JSON `TextMessage` in this lesson.

An organization might adopt `_type=invoice-created-v1` for the Java converter alongside `eventType=InvoiceCreated, schemaVersion=1` in the body. When both exist, **validate consistency** to avoid conflicting metadata and body values.

## 3. MessageConverter in Spring JMS

Spring defines the `org.springframework.jms.support.converter.MessageConverter` interface with two fundamental directions:

~~~java
Message toMessage(Object object, Session session) throws JMSException;
Object fromMessage(Message message) throws JMSException;
~~~

This is an illustrative API signature requiring imports `jakarta.jms.Message` and `Session`. `JmsTemplate.convertAndSend` uses `toMessage`; `JmsTemplate.receiveAndConvert` uses `fromMessage`. The `@JmsListener` listener adapter also converts payloads according to the configured converter/factory.

There are multiple converters/approaches:

| Converter / Approach | Received Data | How Type Is Selected |
| --- | --- | --- |
| `SimpleMessageConverter` | `String`, `byte[]`, `Map`, `Serializable`... by JMS body type | **Does not parse JSON into arbitrary DTOs** |
| `MappingJackson2MessageConverter` (Spring 6.x) | JSON `TextMessage` or `BytesMessage` | Uses type ID property and Jackson |
| Explicit JSON parser + fixed DTO | `String`/`TextMessage` then mapper | Class chosen by consumer code; no type ID class lookup needed |
| `ObjectMessage` / Java native serialization | Java object graph | Relies on Java serialization and classpath; do not use instead of a JSON contract |

If the producer sends a `TextMessage` containing JSON while the consumer uses `SimpleMessageConverter`, `receiveAndConvert` normally returns a **JSON `String`**. There is no magic that turns it into `InvoiceCreatedV1`.

### Two Conversion Directions

~~~text
Sender Java DTO
  -> MappingJackson2MessageConverter.toMessage
  -> JMS TextMessage/BytesMessage + _type
  -> Broker
  -> MappingJackson2MessageConverter.fromMessage
  -> Mapped Java DTO
  -> Business handler
~~~

If you want `TextMessage`, you must call `setTargetType(MessageType.TEXT)`; the Jackson 2 converter can default to `BytesMessage`. Do not confuse choosing the body type with the type ID used for the Java DTO.

## 4. Type ID Property and Bidirectional Mapping

Key configurations in Spring Framework 6.2.x:

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

// Configuration snippet inside a @Bean method, not a standalone program.
var converter = new MappingJackson2MessageConverter();
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(Map.of(
        "invoice-created-v1", InvoiceCreatedV1.class,
        "invoice-cancelled-v1", InvoiceCancelledV1.class));
~~~

`setTypeIdPropertyName("_type")` tells the converter **which property name to look up**. Per the Javadoc, if you want to automatically restore inbound messages back into Java objects via the default mechanism, this property name must be configured.

`setTypeIdMappings(...)` accepts a map with **wire type aliases as keys** and **Java classes as values**:

~~~text
"invoice-created-v1"   -> InvoiceCreatedV1.class
"invoice-cancelled-v1" -> InvoiceCancelledV1.class
~~~

**On the sending side**, the converter typically looks up the runtime class to obtain the alias and writes it into the `_type` JMS property. **On the receiving side**, the converter reads `_type` and looks up the alias to determine the Java type before invoking Jackson. Both sides must have compatible mappings for end-to-end typed conversion.

### Why Use Aliases Instead of Full Class Names?

If `com.shop.billing.InvoiceCreatedV1` moves to `com.shop.contract.events.InvoiceCreatedV1`, you can keep the alias `invoice-created-v1` unchanged. Receivers do not need to know about Java refactorings. Conversely, transmitting raw class names turns every rename/package/module move into a breaking wire contract change.

### Caveat About Map-Based Class Selection

The map only chooses the target type; JSON fields still require:
- Validating required fields and data integrity.
- Rules for enums, timestamps, monetary amounts, and encoding.
- Size, nesting depth, and resource limits.
- Handling supported/unsupported schema versions.
- Idempotency and transactions for side effects.

## 5. Major Trap: Type Mappings Are NOT an Allowlist

In Spring 6.2.x's `MappingJackson2MessageConverter`, if the type ID **is not in the map**, the converter may treat the ID as a **fully qualified class name** and attempt to resolve it. Specifying a mapping **does not automatically disable this fallback**.

~~~text
Configured:
  "invoice-created-v1" -> InvoiceCreatedV1.class

Receive _type="invoice-created-v1"
  -> map match -> InvoiceCreatedV1

Receive _type="java.lang.ProcessBuilder"
  -> no match -> class-name lookup fallback path (if not blocked)

Receive _type="com.example.other.SomeClass"
  -> no match -> class-name lookup fallback path (if not blocked)
~~~

This is a **data-driven type selection** issue. Having a class on the classpath does not make it safe for Jackson to instantiate. Certain Java classes/libraries risk being abused as deserialization gadgets, especially in environments where messages may come from untrusted sources.

**It is NOT secure to merely:**
- Call `setTypeIdMappings(Map.of(...))` assuming all other IDs will be rejected.
- Use `@JmsListener(InvoiceCreatedV1 event)` without realizing the converter runs before the handler.
- Run `instanceof`/cast after deserialization; by then, the object has already been constructed.
- Check `eventType` in the body after allowing the parser to load arbitrary class names.
- Disable `ObjectMessage` while allowing JSON metadata to select unrestricted Java classes.

Summary table:

| Mechanism | Effect | Does Not Guarantee |
| --- | --- | --- |
| `setTypeIdPropertyName` | Chooses the property carrying the ID | Does not restrict the ID value |
| `setTypeIdMappings` | Declares alias ↔ class | Does not block unknown IDs using class names |
| `setTrustedPackages` | Restricts packages for raw class-name fallback | Not an exact class/alias allowlist |
| **Checking alias against `Map/Set` before deserialization** | Rejects all unregistered IDs | Still needs schema/parser security |
| Broker ACL/TLS | Blocks unauthorized publishers | Does not block valid-looking malicious JSON |
| DTO validation | Validates business semantics | Does not replace safe type selection |

## 6. Spring Security Advisory CVE-2026-41855

On **08/06/2026**, Spring published **CVE-2026-41855**: Jackson JMS converters can allow unexpected class instantiation in **untrusted** JMS environments, potentially enabling unauthorized behavior via deserialization gadgets.

Affected versions per Spring's advisory include:
- Spring Framework **6.2.0 to 6.2.18**.
- Spring Framework **7.0.0 to 7.0.7**.
- Certain older branches per the advisory table.

Public fixes:
- **6.2.19** for the 6.2 branch.
- **7.0.8** for the 7.0 branch.

New package-restriction mechanism:

~~~java
// API available from Spring Framework 6.2.19 in the 6.2 branch:
converter.setTrustedPackages("com.example.jmstypes");
~~~

It restricts allowed packages **when taking the raw Java class name fallback path**. What must be understood accurately:

1. Aliases already present in the mapping are normally resolved directly to the registered class.
2. Unknown type IDs shaped like FQCNs can be blocked if the package is not trusted.
3. Another FQCN **within a trusted package** can still resolve through the fallback path; thus trusted packages are not an exact alias allowlist.
4. Omitting `setTrustedPackages` remains unsafe for untrusted environments.
5. Never configure wildcards allowing all packages or overly broad packages to "fix" deployment errors.

**Recommendation:** on patched Spring, use `setTrustedPackages` as defense in depth, while enforcing an **exact allowlist of wire aliases before the converter selects a class**. This prevents accidentally trusting another DTO that happens to share the same package.

### Checking Actual Dependencies

In a Maven project:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-jms
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
~~~

In Windows PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework:spring-jms
.\mvnw.cmd dependency:tree -Dincludes=org.springframework:spring-core
~~~

Do not rely on the Spring Boot starter name to assume you are patched. The lab below requires **spring-jms 6.2.19+**; if still on 6.2.18, update Spring Boot/Spring Framework per vendor guidance before compiling `setTrustedPackages`.

Original advisory: https://spring.io/security/cve-2026-41855/

## 7. Defense in Depth: IDs, Packages, DTOs, and Business Validation

Define the contract:

~~~text
Allowed wire aliases:
  invoice-created-v1
  invoice-cancelled-v1

Allowed mapped Java DTOs:
  InvoiceCreatedV1
  InvoiceCancelledV1

Trusted Java package (defense in depth):
  com.example.jmstypes
~~~

A consumer should execute in order:

1. Accept only the agreed JMS body type (e.g. `TextMessage`).
2. Read `message.getStringProperty("_type")`.
3. Verify the ID belongs to the **exact alias set** defined by the service. If missing or absent from the set, reject before Jackson parses.
4. Map the ID to the registered DTO. Never call `Class.forName(typeId)` in business code.
5. Parse JSON into the DTO and validate the schema.
6. Validate business invariants, IDs, versions, timestamps, enums, and required fields.
7. Execute idempotent business logic, committing/ACKing only at the proper transaction boundary.
8. For rejected messages, apply retry/DLQ/quarantine per policy; never retry infinitely.

**Fail closed** means unknown IDs are always rejected by policy, without guessing a nearby DTO or widening trusted packages.

### Three Distinct Control Layers

**Exact alias allowlist:** ensures senders cannot choose arbitrary classes via properties.  
**Trusted packages:** safeguard in case any code path still enters raw class-name fallback.  
**Jackson + DTO validation:** ensures data inside an allowed class has valid structure and values.

A valid `_type="invoice-created-v1"` can still carry a 500 MB payload, deeply nested JSON, or `totalMinor=-5`. Those require separate parser limits, broker size limits, and validation.

## 8. Building StrictJsonMessageConverter (Java 17+)

This example uses Spring 6.2.19+, Jackson 2, and Jakarta Messaging. Create **three separate files** in package `com.example.jmstypes`.

**File 1 — `src/main/java/com/example/jmstypes/InvoiceCreatedV1.java`**

~~~java
package com.example.jmstypes;

public record InvoiceCreatedV1(String invoiceId, long totalMinor) {
}
~~~

**File 2 — `src/main/java/com/example/jmstypes/InvoiceCancelledV1.java`**

~~~java
package com.example.jmstypes;

public record InvoiceCancelledV1(String invoiceId, String reason) {
}
~~~

**File 3 — `src/main/java/com/example/jmstypes/StrictJsonMessageConverter.java`**

~~~java
package com.example.jmstypes;

import java.util.Map;

import com.fasterxml.jackson.databind.JavaType;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageType;

public final class StrictJsonMessageConverter
        extends MappingJackson2MessageConverter {

    private static final Map<String, Class<?>> TYPES = Map.of(
            "invoice-created-v1", InvoiceCreatedV1.class,
            "invoice-cancelled-v1", InvoiceCancelledV1.class);

    public StrictJsonMessageConverter() {
        setTargetType(MessageType.TEXT);
        setTypeIdPropertyName("_type");
        setTypeIdMappings(TYPES);
        setTrustedPackages("com.example.jmstypes");
    }

    @Override
    protected JavaType getJavaTypeForMessage(Message message)
            throws JMSException {

        if (!(message instanceof TextMessage)) {
            throw new MessageConversionException(
                    "Only JSON TextMessage is supported");
        }

        String typeId = message.getStringProperty("_type");
        if (typeId == null || !TYPES.containsKey(typeId)) {
            throw new MessageConversionException(
                    "Unrecognized JMS type ID");
        }

        // Unknown ID already blocked: do not let Spring enter fallback.
        return super.getJavaTypeForMessage(message);
    }
}
~~~

**Key security point:** `getJavaTypeForMessage` executes during `fromMessage`, before the converter invokes Jackson parsing. Thus `_type="java.lang.ProcessBuilder"`, even though the class exists, is blocked because it is not in `TYPES`. Even with `setTrustedPackages`, the `TYPES.containsKey(typeId)` check is the exact allowlist.

**Pattern limitation:** this protects the **receiving path**. The parent converter can still emit a raw Java class name for an outbound object missing from the map. In production, restrict sent DTOs via typed publisher APIs or validate object types before `convertAndSend`; if customizing the converter to block outbound sends, cover all `toMessage` paths used by the app, including `SmartMessageConverter` overloads if applicable.

**DTO records do not validate business rules automatically.** Validate non-empty `invoiceId`, `totalMinor >= 0`, string lengths, and required fields in your handler/service validator after JSON parsing.

## 9. Runnable Lab: Spring Boot 3.5 + Embedded Artemis

This lab creates three queues and observes:
- JMS `_type` matches the alias on the sent message.
- `receiveAndConvert` returns the expected Java record type.
- An unknown alias carrying a raw class name is **rejected before deserialization**.

Stack: **Patched Spring Boot 3.5.x using Spring Framework 6.2.19+**, Java 17, Jackson 2, embedded Artemis. Use a local environment; never publish malformed messages to a production broker.

### 9.1. Create the Maven Project

Using https://start.spring.io/:

- Maven project, Java 17.
- Group `com.example`, artifact `jms-type-lab`, package `com.example.jmstypes`.
- Spring Boot 3.5.x with security patches applied.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).
- Ensure Jackson databind is included; you can add `spring-boot-starter-json`.

Add the embedded broker dependency to `<dependencies>` in the `pom.xml` generated by Spring Initializr:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-json</artifactId>
</dependency>
~~~

The Boot parent/BOM manages versions; do not mix arbitrary spring-jms/Jackson/Artemis versions. Verify `spring-jms` is at 6.2.19+ using Maven dependency tree.

### 9.2. Lab Configuration

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-type-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.raw,demo.converted,demo.unknown
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

The embedded broker is only for converter demos and does not prove production persistence/failover. Three queues are kept separate so raw reads do not consume the messages meant for conversion tests.

### 9.3. Complete Java Application

Add **File 4 — `src/main/java/com/example/jmstypes/JmsTypeLabApplication.java`**:

~~~java
package com.example.jmstypes;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConversionException;

@SpringBootApplication
public class JmsTypeLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTypeLabApplication.class, args);
    }

    @Bean
    ApplicationRunner runTypeIdDemo(ConnectionFactory factory) {
        return args -> {
            JmsTemplate template = new JmsTemplate(factory);
            template.setMessageConverter(
                    new StrictJsonMessageConverter());
            template.setReceiveTimeout(2_000L);

            template.convertAndSend(
                    "demo.raw",
                    new InvoiceCreatedV1("INV-7", 5500));

            Message raw = template.receive("demo.raw");
            if (!(raw instanceof TextMessage)) {
                throw new IllegalStateException(
                        "Expected a TextMessage");
            }

            System.out.println("TYPE_ID="
                    + raw.getStringProperty("_type"));
            System.out.println("RAW_TYPE=TextMessage");

            template.convertAndSend(
                    "demo.converted",
                    new InvoiceCreatedV1("INV-8", 7000));

            Object payload =
                    template.receiveAndConvert("demo.converted");
            if (!(payload instanceof InvoiceCreatedV1 event)) {
                throw new IllegalStateException(
                        "Expected InvoiceCreatedV1");
            }

            System.out.println("DTO="
                    + event.invoiceId() + ":" + event.totalMinor());

            // Test spoofed messages only in a local lab.
            template.send("demo.unknown", session -> {
                TextMessage message = session.createTextMessage(
                        "{\"invoiceId\":\"INV-X\",\"totalMinor\":1}");
                message.setStringProperty(
                        "_type", "java.lang.ProcessBuilder");
                return message;
            });

            try {
                template.receiveAndConvert("demo.unknown");
                throw new IllegalStateException(
                        "Expected type ID rejection");
            } catch (MessageConversionException expected) {
                System.out.println(
                        "REJECTED_UNKNOWN_TYPE=true");
            }
        };
    }
}
~~~

This is a **complete application when all four files** and proper dependencies/configs are combined. `JmsTemplate` is instantiated directly with the converter explicitly attached; the lab does not depend on Boot auto-configuring all listener factories.

### 9.4. How to Run

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Omitting Spring/Artemis startup logs, the lines printed by the application in order will be:

~~~text
TYPE_ID=invoice-created-v1
RAW_TYPE=TextMessage
DTO=INV-8:7000
REJECTED_UNKNOWN_TYPE=true
~~~

**Explanation:** the converter uses the alias map to attach the property and decode JSON into the `InvoiceCreatedV1` record. For the last message, the `getJavaTypeForMessage` override checks the alias first and throws `MessageConversionException` because `java.lang.ProcessBuilder` is not in the map, so Jackson is never asked to instantiate that class.

**Do not draw the wrong conclusion from the demo:** synchronous `JmsTemplate.receiveAndConvert` may complete its local ack/commit inside the `receive` step before the converter error occurs. A rejection in the demo **does not guarantee the message remains on the queue for retry**. For reliable processing, use proper transaction boundaries, listener containers, DLQ, and idempotency.

## 10. Configuring the Converter for JmsTemplate and @JmsListener

The lab instantiates a template directly to eliminate configuration ambiguity. In a real application, you can declare a converter bean:

~~~java
@Bean
StrictJsonMessageConverter strictJmsConverter() {
    return new StrictJsonMessageConverter();
}
~~~

This is a method fragment inside a Spring `@Configuration`. If the project creates multiple templates or containers manually, you must **attach the converter to each send/receive path** rather than assuming one bean covers everything.

Manual `JmsTemplate`:

~~~java
@Bean("invoiceTemplate")
JmsTemplate invoiceTemplate(
        ConnectionFactory factory,
        StrictJsonMessageConverter converter) {
    JmsTemplate template = new JmsTemplate(factory);
    template.setMessageConverter(converter);
    return template;
}
~~~

Listener factory:

~~~java
@Bean("invoiceListenerFactory")
DefaultJmsListenerContainerFactory invoiceListenerFactory(
        ConnectionFactory factory,
        StrictJsonMessageConverter converter) {
    var factoryBean = new DefaultJmsListenerContainerFactory();
    factoryBean.setConnectionFactory(factory);
    factoryBean.setMessageConverter(converter);
    factoryBean.setSessionTransacted(true);
    return factoryBean;
}
~~~

These are **configuration snippets**; they require imports for `jakarta.jms.ConnectionFactory`, `@Bean`, `JmsTemplate`, and `DefaultJmsListenerContainerFactory`, placed in an appropriate Spring class. With Boot, `DefaultJmsListenerContainerFactoryConfigurer` can preserve useful defaults before overriding the converter/transacted session per contract.

Illustrative listener:

~~~java
@Component
class InvoiceListener {

    @JmsListener(
        destination = "billing.events",
        containerFactory = "invoiceListenerFactory")
    public void onCreated(InvoiceCreatedV1 event) {
        // Validate the event then process idempotently.
        // Throw an exception when business processing fails.
    }
}
~~~

Requires `@Component`, `@JmsListener`, proper annotation-driven JMS configuration, and corresponding imports. **Never treat the annotated method signature as the sole security control**: conversion can run before the method is invoked. Test against a real broker with valid/unknown aliases and malformed JSON.

## 11. Distinguishing Allowlists from JSON Polymorphism

Having a type ID in a JMS property does not mean Jackson should trust class-selecting fields inside JSON:

~~~json
{
  "eventType": "InvoiceCreated",
  "schemaVersion": 1,
  "invoiceId": "INV-7",
  "totalMinor": 5500
}
~~~

**Common safe approach:** target DTOs are pure data records/classes with fixed field types. Avoid:
- Unrestricted `ObjectMapper.activateDefaultTyping(...)` on external inputs.
- `@JsonTypeInfo(use = JsonTypeInfo.Id.CLASS)` on untrusted payloads.
- Deserializing into `Object` / overly generic interfaces accompanied by class names from the body.
- Reading class names from JSON and calling `Class.forName(...)` manually.
- DTOs with unusual side-effecting code in constructors/custom deserializers.
- Outdated Jackson/library versions or missing parser limits.

**A proper allowlist at the `_type` layer cannot fix polymorphic deserialization vulnerabilities buried inside a DTO's fields.** Control `ObjectMapper`, type hierarchies, JSON limits, and validation independently.

### Note on ObjectMessage

`ObjectMessage` uses **Java native serialization**, which carries classpath-coupling and different deserialization security concerns. `MappingJackson2MessageConverter` normally converts JSON `TextMessage` or `BytesMessage`; do not treat `ObjectMessage` and JSON type IDs as identical mechanisms. In inter-service systems, JSON/Avro/Protobuf schemas generally provide cleaner contracts to govern than Java object serialization.

## 12. Versioning: Type IDs Must Be a Stable Wire Contract

Suppose v1 is:

~~~text
invoice-created-v1 -> com.shop.billing.InvoiceCreated
~~~

After a Java refactor:

~~~text
invoice-created-v1 -> com.shop.contract.events.InvoiceCreatedV1
~~~

If the v1 wire schema is unchanged, the alias can stay the same. Senders do not need to know consumer packages. However, the new class must still read old JSON properly and preserve old semantics; refactoring classes **does not replace compatibility testing**.

If a breaking schema change is required:

~~~text
invoice-created-v1 -> InvoiceCreatedV1.class
invoice-created-v2 -> InvoiceCreatedV2.class
~~~

Safe rollout process:
1. Define the v2 schema and mapping documentation.
2. Upgrade consumers to understand **both v1 and v2**.
3. Producers start emitting the v2 alias once consumers support it.
4. Monitor remaining v1 messages in the broker, DLQ, and retry backlog.
5. Remove v1 only when retention/replay contracts allow.
6. Test rolling deployments, backup restores, and broker failover.

If a new release registers only v2 and deletes v1, consumers may reject remaining v1 backlog; this is a communication contract change, not merely a Java package change.

### Schema Version and Aliases

Adding an optional field does not always require a new alias. You can keep v1 when a **backward-compatible** change is agreed upon by both sides. When changing field types, business meaning, required/optional semantics, or incompatible structures, introduce v2 and update validators.

## 13. JMS Properties, JMSType, and Selectors

A producer can set properties:

~~~java
// Code snippet inside a service with JmsTemplate:
jmsTemplate.send("billing.events", session -> {
    TextMessage message = session.createTextMessage(
            "{\"invoiceId\":\"INV-7\",\"totalMinor\":5500}");
    message.setStringProperty("_type", "invoice-created-v1");
    message.setStringProperty("contentType", "application/json");
    return message;
});
~~~

This is manual message construction. If replaced with `convertAndSend(dto)` using the configured converter, the converter generates the JSON body and type ID property automatically from the mapping. **Do not send the same event twice** just to test both approaches.

JMS property names follow the spec's identifier rules; `_type` is a valid name for the example. Avoid colliding with reserved names. `JMSType` is a **separate JMS header**, not automatically turned into `_type`.

JMS selectors can read JMS properties:

~~~sql
_type = 'invoice-created-v1'
~~~

Selectors help filter messages by metadata, **not authorization**. An untrusted producer can forge `_type` if broker ACLs allow publishing; consumers must still validate allowlists and schemas. Selectors do not parse `eventType` inside a JSON body unless the producer also sets a matching property.

## 14. Conversion Errors and Transactions/Acknowledgement

Stages:

~~~text
Broker
  -> receive JMS Message
  -> validate type ID, body type
  -> select Java DTO
  -> Jackson parse
  -> schema/business validation
  -> business handler
  -> JMS ACK/COMMIT per transaction boundary
~~~

**In practice, ACK/COMMIT timing depends on the receive path.** With `JmsTemplate.receiveAndConvert` managing a local session on its own, receiving the message may ACK/commit **before** the converter runs. Thus a converter exception does not necessarily cause the broker to redeliver the message. For critical work, wrap the entire operation in an external transaction or use `@JmsListener` with a transacted session and proper redelivery policy.

When using a transacted listener:
- An exception thrown by the converter/handler can roll back the session.
- The broker may redeliver the message per policy; max attempts, backoff, and DLQ are required.
- Permanently malformed JSON becomes a **poison message** if retried indefinitely.
- If a DB write succeeds before the JVM crashes prior to JMS commit, the message may be redelivered; **idempotency** keyed by event/business ID is mandatory for critical side effects.

Never write `catch(Exception e) { log(e); return; }` inside a handler when that error should trigger rollback: returning normally may be treated by the container as success.

### Operational Error Classification

| Error Type | Example | Policy to Consider |
| --- | --- | --- |
| `UNKNOWN_TYPE_ID` | `_type="invoice-created-v99"` | Quarantine/DLQ, verify release/version |
| `RAW_CLASS_NAME_REJECTED` | `_type="java.lang.ProcessBuilder"` | Security alert and block misbehaving/malicious publisher |
| `BODY_TYPE_MISMATCH` | `BytesMessage` under a TEXT-only policy | Block before Jackson; fix contract |
| `JSON_SYNTAX_ERROR` | Malformed JSON | DLQ after explicit retry policy |
| `SCHEMA_INVALID` | Missing `invoiceId`, negative total | Business validation, quarantine |
| `CLASS_VERSION_DRIFT` | Valid alias but incompatible consumer DTO | Contract tests/rolling deployment |
| `BROKER_UNAVAILABLE` | JMS connection/commit failure | Bounded retry and infrastructure recovery |
| `BUSINESS_FAILURE` | Transient DB/API failure | Transactions, retries, and idempotency |

## 15. What If the System Does Not Need Dynamic Type Selection?

If a destination carries only a single JSON message type, an explicit approach can be simpler and easier to audit:

~~~java
// Code snippet: objectMapper is a configured Jackson mapper.
Message message = jmsTemplate.receive("invoice-created.v1");
if (!(message instanceof TextMessage text)) {
    throw new IllegalStateException("Unexpected body type");
}
InvoiceCreatedV1 event = objectMapper.readValue(
        text.getText(), InvoiceCreatedV1.class);
~~~

Here the **consumer picks a fixed class** instead of reading a class name from a JMS property. Trade-off: if one queue carries multiple message types, you need a dispatch table or separate pre-defined destinations. This is not advice to use raw `receive` to solve ACK handling: `JmsTemplate` still manages resources/transactions; design reliability separately.

For polyglot systems, JSON Schema/Avro/Protobuf and an `eventType + schemaVersion` envelope can be a cleaner contract. A Java type ID should be adapter metadata, not an architecture forcing every consumer to know Java FQCNs.

## 16. Required Test Matrix

| Input | Expected Outcome |
| --- | --- |
| Alias `invoice-created-v1`, valid body | Produces `InvoiceCreatedV1` |
| Alias `invoice-cancelled-v1`, valid body | Produces `InvoiceCancelledV1` |
| Missing `_type` property | Rejected before JSON parsing |
| `_type=""` | Rejected |
| `_type="invoice-created-v99"` | Rejected or quarantined |
| `_type="java.lang.ProcessBuilder"` | Rejected **before** class fallback |
| FQCN inside a **trusted package** without an alias | Still rejected by exact ID allowlist |
| Valid type ID but `BytesMessage` when only Text is allowed | Body type rejected |
| Valid type ID but malformed JSON | Parse error; handler not invoked |
| Valid type ID but invalid data | Validation error |
| Oversized/deeply nested JSON | Blocked by broker/parser resource limits |
| Unmapped outbound class | Test catches converter emitting raw FQCN |
| New consumer reads old v1 message | Compatibility test passes or clear migration path |
| Listener throws after conversion | Transaction rollback/redelivery per policy |
| `receiveAndConvert` conversion failure | Do not assume message automatically returns to queue |
| JMS selector on `_type` | Valid routing, does not replace security |
| Spring dependency on CVE-affected version | CI dependency scan fails if patch is required |

### Why Test Against a Real Broker?

Unit tests with fake JMS `Session`/`TextMessage` objects verify mappings and rejections, yet cannot prove:
- How JMS producers/consumers preserve properties across the broker.
- JMS transaction commit/rollback.
- Redelivery/poison-message/DLQ policies.
- Concurrency/queue/topic subscriptions.
- Restarts/backlogs and multiple consumer versions running concurrently.

Use a test/staging broker configured close to production. Never send test payloads deemed malicious to a shared environment. Negative tests must prove **type rejection occurs before any DTO is instantiated**.

## 17. Operations When an Unknown Type ID Appears

A practical runbook:

1. Record JMS message ID, destination, publisher identity, sanitized type ID, timestamp, deployment version, and error category.
2. Check whether the unknown alias appears in the published schema registry/changelog.
3. If the alias is a valid new version, deploy consumers supporting that alias with DTO/validators and contract tests, normally **consumer before producer**.
4. If the alias contains a suspicious FQCN, treat it as a security incident; audit ACLs and publishers rather than opening trusted wildcards.
5. Route unprocessable messages to a DLQ/quarantine with appropriate retention instead of endless retry loops.
6. During replay, enforce authorization and idempotency so duplicate side effects do not occur.
7. Monitor unknown ID rates, parser errors, redelivery counts, DLQs, broker queue depth, and client library versions.
8. After upgrades, retain old mappings long enough to drain backlogs/retained messages per contract.

Never log entire payloads containing PII/secrets solely to diagnose a bad type ID; log safe metadata or create access-controlled investigation records.

## 18. Pre-Production Review Checklist

- Has the contract standardized the **JMS property name** used for type IDs?
- Which aliases are permitted, and which Java DTOs do they map to?
- Is `setTypeIdMappings` understood to be a **mapping, not an allowlist**?
- Are unknown aliases blocked **before** raw FQCN fallback and Jackson parsing?
- Is `setTrustedPackages` configured on Spring Framework **6.2.19+** or an equivalent patched version?
- Are wildcards or overly broad packages avoided when handling untrusted JMS inputs?
- Do DTOs have fixed structure with unrestricted Jackson polymorphic class lookup disabled?
- Are outbound producer type IDs tested to prevent unintentionally emitting raw Java class names?
- Is the JSON TEXT/BYTES body type explicitly chosen, with `schemaVersion` and data validation?
- Do broker auth/TLS/ACLs block unauthorized publishers?
- Is the converter bean actually wired into the running template and listener factories?
- Do transaction/ACK boundaries trigger properly, with idempotency and retry/DLQ?
- Can new consumer versions still process old alias backlogs?
- Are negative tests present for missing type IDs, malicious type IDs, malformed JSON, and unmapped new DTOs?
- Are payload size/depth limits, metrics, alerts, and runbooks in place?
- Is the patched Java 17+, Spring 6.2.x/Boot 3.5.x dependency tree documented?

## 19. Exercises

1. Send a JSON `TextMessage` without `_type`. Predict the outcome through the strict converter.
2. Add `InvoiceCancelledV1` to the lab, send it, and verify the received alias and DTO.
3. Why does simply adding `setTypeIdMappings(Map.of("safe", Safe.class))` not prevent raw FQCN fallback?
4. Type ID `com.example.jmstypes.NotMappedDto` is inside the trusted package; will the strict converter accept it? Why?
5. If Spring JMS is still on 6.2.18, what action is required before using `setTrustedPackages`?
6. Change a Java DTO's package while keeping the JSON schema/alias; identify what must change and what does not.
7. If the message body has `eventType="InvoiceCancelled"` while JMS `_type="invoice-created-v1"`, how should the consumer handle it?
8. Does using JMS selector `_type='invoice-created-v1'` make the consumer secure if the broker allows any publisher to send?
9. Why does catching `ClassCastException` after `receiveAndConvert` fail to prevent the converter from having already instantiated another class?
10. With a transacted `@JmsListener`, malformed JSON rolls back repeatedly; how do you design the retry budget and DLQ?
11. A queue carries only `InvoiceCreatedV1` JSON; compare a consumer using a fixed class against dynamic type ID mapping.
12. Write an integration test for a v2 publisher sending a new alias while a v1 consumer is still running.

## Official References

- Spring Framework 6.2.19 — `MappingJackson2MessageConverter` API (type ID property, mappings, trusted packages): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Framework Security Advisory, **CVE-2026-41855** (published 08/06/2026): https://spring.io/security/cve-2026-41855/
- Spring Framework 6.2 — `JmsTemplate` and message conversion: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — annotated listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.5 — JMS/Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — system requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Jakarta Messaging 3.1 — headers, properties, selectors, acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
