# Reducing Coupling to Internal Java Classes and ObjectMessage Serialization

## 1. The Problem to Solve

A messaging system is truly decoupled only when both sides exchange a stable data contract without sharing each other's full internal implementation structure. If a producer sends domain model objects, ORM entities, or internal Java classes directly, consumers become coupled to the producer's class names, packages, field structures, libraries, and build versions.

This problem becomes especially acute with JMS `ObjectMessage`. This message type carries a `Serializable` Java object; the receiver must deserialize that object to use it. In Spring JMS, `SimpleMessageConverter` converts a `Serializable` object into an `ObjectMessage` by default when calling conversion methods such as `JmsTemplate.convertAndSend`.

Common consequences:

- Producer and consumer must have compatible classes on their runtime classpaths.
- Changing packages, class hierarchies, or object structures can break reading old messages.
- Consumers are locked into Java and JVM serialization rules.
- Integrating services written in other languages becomes difficult.
- Deserializing untrusted data can create severe security vulnerabilities.
- A seemingly small internal change can force multiple services to deploy simultaneously.

A sustainable design separates the **internal business model** from the **external message contract**, then serializes via a format with an explicit schema such as JSON, Avro, or Protocol Buffers. With JMS, `TextMessage` is commonly used for JSON/XML or `BytesMessage` for schema-defined binary data.

## 2. Distinguishing Internal Objects from Message Contracts

### 2.1. Do Not Send Domain Entities Directly

Suppose the Order Service has an internal entity:

~~~java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines;

    private BigDecimal total;
    private String internalRiskFlag;
    private int persistenceVersion;
}
~~~

This structure serves persistence and internal logic. It may contain lazy relationships, ORM proxies, internal fields, sensitive data, or details outside the integration contract.

If this entity is sent directly, consumers may accidentally depend on:

- The producer's class and package names.
- ORM relationships and how the framework represents proxies.
- Internal fields meaningless to consumers.
- How the domain model represents money, status, or timestamps.
- Library versions and the producer application's classpath.

Database changes or domain model refactorings then turn into breaking protocol changes across services.

### 2.2. Create Dedicated DTOs for Integration

Create a public, compact DTO containing only the data consumers need:

~~~java
import java.util.List;

public record OrderPlacedV1(
    String eventId,
    String orderId,
    String customerId,
    String occurredAt,
    List<OrderLineData> lines,
    String currency,
    long totalMinorUnits
) {
    public record OrderLineData(
        String productId,
        int quantity
    ) {}
}
~~~

`occurredAt` in this example is an ISO 8601 timestamp string, e.g., `2026-11-07T10:30:00Z`. The contract must clearly specify timezone and precision. Using a string here keeps the example independent of registering a Jackson module for `java.time`.

This DTO is a **message contract**. It does not need to mirror the producer's entire entity, aggregate, or object graph. An event may publish only IDs and essential facts; consumers can query additional data via an appropriate API if genuinely needed.

Perform the conversion at the boundary between domain and messaging:

~~~java
OrderPlacedV1 toContract(OrderEntity order, String eventId) {
    return new OrderPlacedV1(
        eventId,
        order.getId().toString(),
        order.getCustomer().getId().toString(),
        order.getPlacedAt().toString(),
        order.getLines().stream()
            .map(line -> new OrderPlacedV1.OrderLineData(
                line.getProductId(),
                line.getQuantity()))
            .toList(),
        order.getCurrency(),
        order.getTotalMinorUnits()
    );
}
~~~

The example assumes the domain already exposes `getTotalMinorUnits` returning the amount in the minor unit defined by the contract. Never assume every currency has two decimal places; the contract must specify the unit explicitly or use a decimal string representation paired with currency.

Explicit mapping brings an important benefit: when the domain model evolves, the producer only needs to keep the mapper producing a compatible contract. Consumers do not need to know how the producer refactored its entities.

### 2.3. Separate Contract Modules from Implementation Modules

| Sharing Approach | Coupling Level | When Appropriate |
|---|---|---|
| Sharing entity/domain classes | Very high | Avoid between independent services |
| Sharing a Java DTO JAR | Medium to high | Java-only systems with synchronized release processes and strict version management |
| Sharing neutral schemas; each side generates its own DTOs | Lower | Independent, polyglot services with separate deployments and upgrades |

A dedicated DTO library is better than sharing domain entities, yet still introduces coupling to a Java artifact and library release schedule. For distributed or polyglot systems, treat JSON Schema, Avro schemas, Protobuf schemas, or AsyncAPI contracts as the primary contract source. Each service can generate code or map to its own internal types.

Never let the producer's Java package become a protocol identifier that consumers are forced to know.

## 3. How Does ObjectMessage Work?

### 3.1. Characteristics of JMS ObjectMessage

`jakarta.jms.ObjectMessage` is a JMS message type whose body holds a serializable Java object. The passed object must implement `Serializable`. The API provides `Session.createObjectMessage(Serializable)` to construct the message and `getObject()` to read the object on the receiving side.

Plain JMS example:

~~~java
import jakarta.jms.ObjectMessage;
import jakarta.jms.Session;

ObjectMessage message = session.createObjectMessage(orderEvent);
~~~

`ObjectMessage` captures a snapshot of the object at the moment `setObject` is called; mutating the original object afterward does not alter the message body. Upon receipt, the message is read-only; the API allows calling `clearBody` before rewriting the body.

The issue with this message type is not merely that the class must implement `Serializable`. Its body uses Java Object Serialization, so the consumer must understand the serialized object layout and possess the necessary classes on its classpath to reconstruct the object graph.

### 3.2. Spring Can Create ObjectMessage Unobtrusively

`SimpleMessageConverter` is the default converter used by `JmsTemplate` for `convertAndSend` and `receiveAndConvert` when no other converter is configured.

Default mappings of this converter:

| Object Passed In | Resulting JMS Message |
|---|---|
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| Object implementing `Serializable` | `ObjectMessage` |

Consequently, the following code can produce an `ObjectMessage` if `PlaceOrder` implements `Serializable` and `JmsTemplate` still uses `SimpleMessageConverter`:

~~~java
jmsTemplate.convertAndSend("orders", command);
~~~

Calling a method named `convertAndSend` does not mean the payload is converted to JSON. The JMS message type depends on the configured converter.

If you want to construct a `TextMessage` manually, use `send` with a `MessageCreator`; if you want DTOs serialized to JSON, configure a JSON converter and verify the actual JMS message type produced.

### 3.3. Why Should ObjectMessage Not Be Used as a Long-Term Integration Contract?

**Class and classpath coupling.** Consumers must have compatible classes to read serialized objects. Moving packages or renaming classes can cause `ClassNotFoundException` on consumers.

**Serialization version coupling.** Adding, removing, or changing field types, altering class hierarchies, and `serialVersionUID` changes can break reading stored messages. Java serialization has its own compatibility rules, yet it is not an appropriate schema evolution contract for independent services.

**Java lock-in.** Consumers written in Go, Python, JavaScript, or .NET cannot directly consume Java object graphs as a standard data contract.

**Poor observability and inspection.** The payload is not human-readable JSON/XML text. Inspecting messages in broker consoles, logs, or integration tools becomes harder.

**Deserialization risk.** Java deserialization can instantiate objects and execute logic while reconstructing the object graph. Untrusted serialized data can exploit gadget classes on the classpath or cause excessive resource consumption.

**Hard to control data exposure.** Object graphs can pull in unintended fields and references, leaking internal data or producing oversized payloads.

Therefore, do not treat `ObjectMessage` as the default inter-service integration format, especially when producers and consumers have independent release lifecycles or the broker receives messages from less-than-fully-trusted sources.

## 4. Choosing a Java-Independent Message Format

### 4.1. Comparing JMS Body Types

| Message Type | Content | Advantages | Limitations |
|---|---|---|---|
| `TextMessage` | A text string | Readable, suited for JSON/XML, polyglot | Requires encoding and schema conventions |
| `BytesMessage` | Byte sequence | Suited for Avro, Protobuf, binary data | Requires schema/encoding and decoding tools |
| `MapMessage` | Named/typed fields supported by JMS | Simple contract, no Java classes needed | Restricted data types and limited nesting |
| `ObjectMessage` | Java Serializable object | Convenient in legacy Java apps | Class coupling, serialization fragility, deserialization risk |

No single format fits every case. JSON is generally easy to inspect and integrate; Avro/Protobuf offer explicit schemas and binary encoding when optimizing size or enforcing strict schema governance; `MapMessage` may suffice for very simple payloads.

### 4.2. JSON in TextMessage

Example JSON event body:

~~~json
{
  "eventId": "evt-01J8A2",
  "orderId": "ord-10042",
  "customerId": "cus-700",
  "occurredAt": "2026-11-07T10:30:00Z",
  "currency": "VND",
  "totalMinorUnits": 12500000
}
~~~

This body can be read by Java, Kotlin, Python, Go, or JavaScript consumers as long as all parties agree on the schema and value representations.

JSON does not automatically make messages safe or compatible. Producers and consumers must still agree on:

- Field names, data types, and required/optional fields.
- Timestamp formats, time zones, and precision.
- Currency and decimal representations.
- Enum values and how unknown values are handled.
- Nulls, missing fields, and defaults.
- Compatibility rules when adding or removing fields.

Never enable permissive polymorphic deserialization allowing JSON to instantiate arbitrary Java classes from metadata inside incoming messages. Prefer explicit target DTOs and allowlisted type mappings.

### 4.3. JSON in BytesMessage

Some converters write JSON as a `BytesMessage` instead of a `TextMessage`. Because the content is raw bytes, encoding must be agreed upon; for text-based JSON, UTF-8 is standard.

`BytesMessage` can also carry other binary formats. Never assume every `BytesMessage` is UTF-8 JSON; specify content type, schema ID, or corresponding metadata.

### 4.4. Avro and Protocol Buffers

When a system requires explicit schemas and binary payloads, you can use:

- **Avro:** schemas describe records and fields; useful for schema evolution and schema registry integration.
- **Protocol Buffers:** message schemas define field numbers and data types; supports code generation across many languages.
- **CBOR or other binary formats:** suitable when size, performance, or device constraints demand them.

With `BytesMessage`, the producer writes encoded bytes and the consumer reads bytes and decodes them using the matching schema. Both sides must agree on how to locate the schema: a schema ID in a message property, a registry, a routed version, or another mechanism.

Do not rely solely on field order or Java class names for decoding. In Protobuf, field numbers are part of the contract; never reuse removed field numbers. In Avro, adhere to writer/reader schema rules and registry compatibility settings.

## 5. Designing Stable Envelopes and Metadata

An integration message typically separates contract descriptors, operational metadata, and business payload.

Example envelope in JSON:

~~~json
{
  "messageType": "order.placed",
  "schemaVersion": 1,
  "messageId": "evt-01J8A2",
  "correlationId": "req-9F2",
  "occurredAt": "2026-11-07T10:30:00Z",
  "payload": {
    "orderId": "ord-10042",
    "customerId": "cus-700",
    "currency": "VND",
    "totalMinorUnits": 12500000
  }
}
~~~

Typical field meanings:

| Field | Meaning |
|---|---|
| `messageType` | Stable contract type name, e.g., `order.placed` |
| `schemaVersion` | Payload structure version |
| `messageId` | Unique identifier of the message |
| `correlationId` | Links the message to a request or workflow |
| `causationId` | Message that directly caused the current message |
| `occurredAt` | Timestamp when the business event occurred |
| `payload` | Business data conforming to the schema |

Some metadata can live in JMS properties/headers instead of being duplicated inside the JSON body. If using a converter with a type ID property such as `eventType`, standardize that property across sides and map it to stable type IDs.

Do not put Java class names like `com.company.order.internal.OrderEntity` in a type ID field. Use contract-level identifiers such as `order.placed.v1` or `order-placed-v1`. Each consumer maps that identifier to its own DTO.

### 5.1. Distinguishing JMS Headers, Properties, and Body

- **JMS headers** are standard JMS-defined metadata, such as `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, and delivery metadata.
- **JMS properties** are application metadata attached to messages, commonly used for selectors, type IDs, tenants, or tracing. Property values must use JMS-supported types.
- **Body** carries the business payload or envelope.

Do not place large payloads in JMS properties; properties suit simple metadata. Do not move all business data into headers, as the body holds the primary versioned contract.

## 6. Configuring Spring JMS to Avoid Creating ObjectMessage

### 6.1. Understanding the Active Converter

`JmsTemplate` uses an `org.springframework.jms.support.converter.MessageConverter` to convert objects into JMS messages when calling `convertAndSend` or `receiveAndConvert`.

If no converter is configured, `SimpleMessageConverter` is used. Therefore, merely turning a DTO into a record or moving packages is not enough to stop `ObjectMessage` creation; you must configure a converter and verify the output on the JMS side.

### 6.2. Spring Framework 7: JacksonJsonMessageConverter

With Spring Framework 7, use `JacksonJsonMessageConverter` (Jackson 3) to serialize DTOs to JSON. Set the target type to `MessageType.TEXT` if you want the body to be a `TextMessage`:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsMessagingConfiguration {

    @Bean
    JacksonJsonMessageConverter jmsMessageConverter() {
        JacksonJsonMessageConverter converter =
            new JacksonJsonMessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
            "order.placed.v1", OrderPlacedV1.class,
            "inventory.reserved.v1", InventoryReservedV1.class
        ));

        return converter;
    }
}
~~~

In this example:

- The body is JSON serialized from the DTO.
- The JMS property `eventType` holds the type ID.
- `order.placed.v1` maps to the `OrderPlacedV1` DTO.
- Consumers never need to receive the producer's Java package names.

Spring Framework 7 also provides `JmsClient` for a modern messaging API to send/receive messages. If an application already uses `JmsTemplate`, it can keep using it with an appropriately configured converter.

### 6.3. Spring Framework 6.2: MappingJackson2MessageConverter

With Spring Framework 6.2 and Jackson 2, use `MappingJackson2MessageConverter`. Type ID mapping configuration is analogous:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsMessagingConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
            "order.placed.v1", OrderPlacedV1.class,
            "inventory.reserved.v1", InventoryReservedV1.class
        ));

        return converter;
    }
}
~~~

`MappingJackson2MessageConverter` is the Jackson 2 converter; in Spring 7 it is deprecated in favor of `JacksonJsonMessageConverter`. Choose the converter matching your Spring/Jackson version and do not mix Jackson 2 and Jackson 3 classes in the same configuration example.

### 6.4. Attaching the Converter to JmsTemplate

Create `JmsTemplate` with the configured converter:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConverter;

@Bean
JmsTemplate jmsTemplate(
        ConnectionFactory connectionFactory,
        MessageConverter converter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(converter);
    return template;
}
~~~

This is a manual configuration example; in a Spring Boot application, ensure the converter bean is wired into the `JmsTemplate` the application actually uses. Simply declaring a converter bean does not guarantee every custom template uses it.

### 6.5. Attaching the Converter to Listener Containers

Consumers using `@JmsListener` also need a listener container configured with a matching converter to turn JMS messages into DTOs:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter converter) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);
    return factory;
}
~~~

Consumer receiving the DTO:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        destination = "orders.events",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void onOrderPlaced(OrderPlacedV1 event) {
        // Map the contract to the consumer's internal model.
    }
}
~~~

Producer sending the DTO:

~~~java
jmsTemplate.convertAndSend("orders.events", event);
~~~

If the converter uses a type ID property to select the target class, producer and consumer must share the same type ID mapping convention. Testing real messages catches cases where the converter was configured on only one side.

### 6.6. Using MessagePostProcessor for Metadata

You can attach a correlation ID or simple metadata after the converter builds the JMS message:

~~~java
jmsTemplate.convertAndSend(
    "orders.events",
    event,
    message -> {
        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("tenantId", tenantId);
        return message;
    }
);
~~~

`MessagePostProcessor` modifies the JMS message after payload conversion and before sending. Never treat client-asserted metadata as proof of tenant identity or authorization; the server must verify identity and permissions via trusted security mechanisms.

## 7. Managing Type IDs Without Exposing Java Packages

Some converters need to know the target DTO when reading a message. A type ID can be carried in a JMS property.

Avoid using fully qualified class names:

~~~text
com.example.orders.internal.OrderPlacedEntity
~~~

Use stable contract names instead:

~~~text
order.placed.v1
inventory.reserved.v1
~~~

Configure the converter with explicit mappings:

~~~java
converter.setTypeIdPropertyName("eventType");
converter.setTypeIdMappings(Map.of(
    "order.placed.v1", OrderPlacedV1.class,
    "inventory.reserved.v1", InventoryReservedV1.class
));
~~~

The type ID is the contract identifier; the Java class is merely the implementation each consumer chooses to map to. Another consumer can map that same ID to a different class or a structure in another language.

Do not enable broad polymorphic type resolution merely to avoid declaring mappings. Restrict which payload types may be decoded, use concrete DTOs, and validate schemas before processing.

## 8. Security and Limitations of Replacing ObjectMessage with JSON

### 8.1. Why Must Java Deserialization Be Restricted?

Java deserialization does more than read primitive values. It reconstructs object graphs and can invoke custom logic such as `readObject` during processing. If input data is untrusted and suitable gadgets exist on the classpath, deserialization can lead to unintended code execution or excessive resource consumption.

Oracle recommends avoiding deserializing untrusted data and using serialization filters to restrict classes and object graph size/complexity when unavoidable. Serialization filters are not enabled automatically just because an application runs on a newer JDK.

JEP 290 provides `ObjectInputFilter` to control classes, array sizes, graph depth, and reference counts. However, in JMS, filter configuration also depends on the JMS provider/client performing the deserialization stream. Check your provider's documentation and configuration support; do not assume the application can attach a filter directly to `ObjectMessage.getObject`.

If you must retain `ObjectMessage` in a legacy system:

- Accept messages only from authenticated, controlled producers and brokers.
- Apply class allowlists and serialization filters at the exact layer where the provider performs deserialization.
- Bound message size, object graph depth, reference counts, and processing time.
- Do not expand the classpath or allowlist casually.
- Establish a plan to remove `ObjectMessage` from integration contracts.

These measures are defense-in-depth. They do not turn Java native serialization into a Java-independent integration format.

### 8.2. JSON Also Requires Input Validation

Switching to JSON reduces class coupling and avoids Java native object deserialization, yet JSON is not automatically safe. Consumers still need to:

- Bound payload size and structural nesting depth.
- Validate schemas, data types, string lengths, and value ranges.
- Avoid enabling Jackson default typing or broad polymorphic class resolution on untrusted data.
- Map only allowlisted type IDs.
- Enforce access control and business validation after parsing.
- Avoid logging payloads containing secrets or unnecessary personal data.

In Spring 6.2.19+ `MappingJackson2MessageConverter`, `setTrustedPackages` is available to restrict trusted packages when the converter resolves type IDs by class. This is a control for Spring's JSON converter; it does not replace Java serialization filters and is not a reason to transmit internal class names in messages. Prefer explicit synthetic type ID mappings.

### 8.3. Protecting Metadata and Payloads

- Use TLS and authenticate producer/consumer connections.
- Enforce destination authorization at both the broker and application layers.
- Do not trust tenant IDs, user IDs, or roles merely because they appear in headers.
- Encrypt or strip sensitive fields per data policy.
- Configure appropriate retention, dead-letter queues, and message access permissions.
- Log message IDs, type IDs, correlation IDs, and conversion errors; limit logging full bodies.

## 9. Schema Evolution and Producer-Consumer Compatibility

### 9.1. Adding Fields

Adding optional fields is usually more compatible than renaming or changing field types. For example, a new schema adds `shippingMethod`:

~~~json
{
  "orderId": "ord-10042",
  "currency": "VND",
  "totalMinorUnits": 12500000,
  "shippingMethod": "EXPRESS"
}
~~~

Old consumers must have a clear policy for unknown fields: ignore them if the contract permits or reject if strict control is required. New consumers must handle old producers omitting the field by using a meaningful default or absent-value representation.

Spring's Jackson converters have their own defaults for unknown properties; do not treat those defaults as your schema policy. Configure and test according to your chosen contract.

### 9.2. Breaking Changes

The following changes commonly risk breaking consumers:

- Renaming fields or changing data types.
- Changing a field's meaning while keeping the old name.
- Turning an optional field into a required field.
- Removing enum values that old consumers might still receive.
- Changing units of measurement, time zones, or monetary representations.
- Reusing a schema version or type ID for a different payload.

For major changes, publish a new contract version such as `order.placed.v2`, or use an envelope version. Keep consumers able to read the old version during the transition window.

### 9.3. Rules for Enums and Unknown Values

Consumers should not assume producers emit only enum values known at compile time. When a schema allows extensible enums, consumers need an appropriate unknown-value branch: controlled skip, mapping to a generic state, or routing to a dead-letter queue for investigation. Never silently reinterpret a new value as a different business state.

### 9.4. Schema Registries and Code Generation

With Avro/Protobuf, schemas can live in a repository or schema registry. Pipelines should check compatibility before release. Code generation produces DTOs/serializers from schemas, though it does not eliminate the need to check versions, permissions, and business semantics.

With JSON, JSON Schema or AsyncAPI can describe payloads, message channels, operations, headers, and security schemes. Store schemas as versioned artifacts and test producers/consumers against the same contract.

## 10. Migrating Away from ObjectMessage

Do not switch producers first and hope old consumers magically read JSON. Producers and consumers require an ordered migration plan.

### Step 1: Inventory

Identify:

- Which producers send to each queue/topic.
- Which consumers read from each destination.
- Whether current messages are `ObjectMessage`, `TextMessage`, `BytesMessage`, or `MapMessage`.
- Which DTOs/entities are serialized and which classpaths are shared.
- Whether messages have long retention or remain queued in queues/dead-letter queues.
- Whether retries, replay, and message history require backward compatibility.

### Step 2: Finalize a Neutral Contract

Design a versioned payload with stable type IDs and required metadata. Define representations for time, money, enums, nulls, and IDs. Create JSON examples or binary schemas as test artifacts.

### Step 3: Upgrade Consumers First

Deploy consumers capable of reading the new format. If old messages must still be processed during transition, isolate the legacy reader branch, restrict trusted sources, and apply appropriate filters. Never loosen deserialization broadly just to support dual-reading.

A safer alternative is introducing a new versioned destination so new consumers receive only the new contract, then migrating producers and draining the legacy destination on schedule.

### Step 4: Configure Converters on Both Sides

Attach the JSON/bytes converter to `JmsTemplate` and the listener container. Verify producers actually emit the intended JMS message type; verify consumers read the DTO and type ID properly.

### Step 5: Switch Producers

Map domain objects to contract DTOs, publish through the converter, and preserve command/event semantics. Never put ORM entities or exception objects in payloads.

### Step 6: Monitor and Finish Migration

Monitor new/old message counts, conversion failures, dead letters, consumer lag, and retries. Wait for legacy destinations to drain or migrate them via a defined procedure. Afterward, remove legacy deserialization code and Java serialization dependencies from the messaging path.

## 11. Contract Testing and Inspecting JMS Message Types

A test confirming only that `convertAndSend` throws no exception is insufficient. You must verify the actual wire format matches the contract.

### 11.1. Verifying the Produced Message Type

In a test using a real JMS provider or compatible test broker, send a DTO and verify the received message is a `TextMessage` when `MessageType.TEXT` is configured:

~~~java
Message message = receiveRawMessage("orders.events");

assertThat(message).isInstanceOf(TextMessage.class);
assertThat(((TextMessage) message).getText()).contains("\"orderId\"");
assertThat(message.getStringProperty("eventType"))
    .isEqualTo("order.placed.v1");
~~~

`receiveRawMessage` represents a test helper for receiving the raw JMS message; implement it with your test infrastructure. The snippet above illustrates assertions, not a standalone compilable test without the helper and broker.

If the test receives an `ObjectMessage`, check that the converter is actually attached to the sending template—not just declared as a bean in the ApplicationContext.

### 11.2. Compatibility Testing

- New producers emit payloads matching the new schema.
- Old consumers can ignore new optional fields when specified by the contract.
- New consumers can read old payloads and apply proper defaults.
- Unregistered type IDs are rejected in a controlled manner.
- Malformed or oversized payloads do not exhaust consumer resources.
- Duplicate messages do not cause repeated side effects.
- Correlation IDs and metadata survive conversion intact.
- Contracts contain no unintended class names or internal fields.

### 11.3. Serialization Regression Testing

Add a regression test ensuring the sending path never produces `ObjectMessage`. This is especially valuable when there are multiple `JmsTemplate` instances, multiple listener factories, or custom configurations.

You do not need to ban `ObjectMessage` on every queue if a system still has a controlled internal use case with clear justification; however, each integration destination needs an explicit contract and allowlist of permitted message types.

## 12. Common Errors and Remedies

| Error | Cause | Remedy |
|---|---|---|
| DTO is still sent as ObjectMessage | Template is using SimpleMessageConverter | Configure JSON converter on the actual JmsTemplate |
| Consumer throws ClassNotFoundException | Message contains producer's class/package name | Use neutral type IDs mapped to consumer DTOs |
| Consumer fails to parse JSON | Sides disagree on schema or encoding | Standardize schema, content type, and UTF-8 |
| Type ID is unrecognized | Missing property or mismatched mapping | Align property name and type ID mappings |
| Consumer receives right body yet listener fails | Listener container uses a different converter | Configure converter on the listener factory |
| New field breaks old consumers | Incompatible unknown-field policy | Define forward/backward compatibility and test |
| Old ObjectMessage fails to deserialize | Incompatible class/version | Isolate legacy migration, drain messages, or use versioned destination |
| Deserialization poses security risk | Accepting untrusted object graphs | Avoid ObjectMessage; if unavoidable, filter/allowlist at provider |
| JSON leaks internal data | Mapping domain entities directly to payloads | Use contract DTOs and explicit mappers |
| Message too large | Sending entire aggregates or redundant data | Send only essential facts; use reference IDs where suitable |
| Changing converter has no effect | Another template/listener factory is active | Inspect wiring and test raw JMS messages |

## 13. Pre-Release Design Checklist

- [ ] Messages have DTOs/schemas independent of internal entities and classes.
- [ ] Producers map domain models to contracts at the messaging boundary.
- [ ] No ORM proxies, persistence entities, Spring objects, or exception objects are sent.
- [ ] Java native serialization is not used for integration destinations.
- [ ] Explicitly chose `TextMessage`, `BytesMessage`, or `MapMessage` per contract.
- [ ] JSON/Avro/Protobuf schemas and versions are managed.
- [ ] Type IDs are stable identifiers, not Java fully qualified class names.
- [ ] Converters are attached to the actual template and listener container in use.
- [ ] Metadata and correlation are clearly defined.
- [ ] Payloads undergo schema validation, size limits, and business validation.
- [ ] Strategies exist for duplicates, retries, dead-lettering, and replay.
- [ ] A migration plan exists for older messages still in the broker.
- [ ] Tests verify actual JMS message types and contract compatibility.

## 14. References

- [Spring Framework Reference — Sending a Message with JMS](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate`, `convertAndSend`, `MessageConverter`, `SimpleMessageConverter`, `JmsClient`, and sending messages.
- [Spring Framework Javadoc — JacksonJsonMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html): JSON converter using Jackson 3 in Spring Framework 7.
- [Spring Framework 6.2 Javadoc — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): Jackson 2 JSON converter and type ID mapping.
- [Spring Framework Javadoc — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): mapping between Java objects and JMS message types, including `Serializable` to `ObjectMessage`.
- [Jakarta Messaging API — ObjectMessage](https://jakarta.ee/specifications/messaging/3.0/apidocs/jakarta/jms/ObjectMessage.html): `Serializable` contract, `setObject`, and `getObject`.
- [Jakarta Messaging Specification — Message body](https://jakarta.ee/specifications/messaging/3.0/jakarta-messaging-spec-3.0.html): body types `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, and `ObjectMessage`.
- [Oracle Java Serialization Filters](https://docs.oracle.com/en/java/javase/22/core/java-serialization-filters.html): `ObjectInputFilter`, JEP 290/JEP 415, and deserialization restrictions.
- [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/technologies/javase/seccodeguide.html): guidelines for protecting against untrusted serialized data.
