# Designing Message Schemas Independent of Internal Java Classes in Spring JMS

## 1. Problem and Goal

In an event-driven system, producers and consumers must agree on a **message contract / wire schema**: event name, meaning, data fields, data types, units of measure, required constraints, versioning, and change rules. This contract **should not depend** on a service's Java class names, packages, ORM entities, or domain model structure.

Suppose service A publishes order events. Initially A uses `com.company.sales.OrderEntity`, then refactors it to `com.company.orders.PurchaseAggregate` and renames an internal field from `amountCents` to `grossMinorUnits`. Services B (Spring), C (Python), and D (Go) only need `orderId`, `totalMinor`, and `currency` to do their work. If the message payload is a Java serialized object, refactoring A can break consumers. If A maps its domain to a stable JSON contract, internal changes do not affect the wire.

```text
Producer:
 Domain entity / business aggregate (free to refactor)
        |
        v explicit mapper
 Transport DTO OrderPlacedV1 (Java adapter for the contract)
        |
        v JSON serializer / schema validation
 JMS TextMessage + headers / properties
        |
        v
       Broker
        |
        v
 Consumer reads JSON contract v1
        |
        v validate, map to consumer's own domain model
```

**Core principle:** Java classes are implementation details; the schema published between systems is an API. You can use a Java `record` to represent the schema in code, but you must never assume that a Java class name or how Jackson automatically serializes an entity constitutes the public contract.

Learning outcomes: design event envelopes/payloads, define language-independent schemas, explicitly map domain ↔ transport DTOs, understand Spring JMS conversion, manage versioning/compatibility, write a Java 17+ demo, and test older consumers when messages evolve.

## 2. Distinguishing Data Layers

| Component | Responsibility | Example |
| --- | --- | --- |
| Domain model / entity | Business rules, internal state, and persistence | `OrderAggregate`, `@Entity Order` |
| Transport DTO | Communication structure at the producer/consumer boundary | `OrderPlacedV1` record |
| Message schema | Defines names, types, required/optional, semantics, and **language-independent** version | JSON Schema, Avro, Protobuf |
| Serializer / converter | Turns DTO into text/bytes and vice versa | Jackson `ObjectMapper`, `MessageConverter` |
| JMS Message | Jakarta Messaging headers, properties, and body | `TextMessage`, `BytesMessage`, `MapMessage` |
| Broker / destination | Routing, storage, delivery, ack per configuration | ActiveMQ Artemis queue |

JMS does not define the schema of `OrderPlaced`. `TextMessage` only states that the body is a string; the broker does not know what the JSON field `totalMinor` means. `MapMessage` carries JMS-typed name–value pairs, yet does not replace a multi-version contract. `ObjectMessage` uses Java serialization and is not a class-independent cross-language format.

### 2.1. Why Sending Java Entities Directly Is an Anti-Pattern

```java
// Illustrates what NOT to use as a public contract:
jmsTemplate.convertAndSend("orders.events", orderEntity);
```

There are at least six risks:

1. Spring JMS's default `SimpleMessageConverter` **does not automatically convert arbitrary POJOs to JSON**. If the object is `Serializable`, it may create an `ObjectMessage` with Java serialization.
2. Changing class/package names or `serialVersionUID` can prevent consumers from deserializing.
3. JPA entities have Hibernate proxies, lazy associations, and circular references; serializing the whole graph does not reflect an event contract.
4. You may accidentally leak passwords, emails, fraud/risk data, admin fields, or unauthorized data to the broker.
5. Python/Go consumers cannot depend on a Java class on the producer's classpath.
6. Domain classes have a different release lifecycle from the public message contract version.

Instead, create a **dedicated wire DTO**, pick only fields authorized for publication, and serialize using the defined format. Producer and consumer can use differently named classes that both satisfy the contract.

## 3. OrderPlaced v1 Event Schema Example

Example JSON payload with a fixed structure:

```json
{
  "schemaVersion": 1,
  "eventType": "order.placed",
  "eventId": "123e4567-e89b-42d3-a456-426614174000",
  "occurredAt": "2026-10-30T02:00:00Z",
  "payload": {
    "orderId": "order-42",
    "totalMinor": 1999,
    "currency": "VND"
  }
}
```

| Field | Wire Type | Contract Meaning | Required |
| --- | --- | --- | --- |
| `schemaVersion` | integer | Major version of the schema, here `1` | Yes |
| `eventType` | string | Stable event name `order.placed` | Yes |
| `eventId` | UUID string | Unique **event** identifier for tracing/dedup | Yes |
| `occurredAt` | date-time string with offset | Timestamp when the event occurred, preferring UTC `Z` | Yes |
| `payload` | object | Event-specific business body | Yes |
| `payload.orderId` | string | Public order identifier | Yes |
| `payload.totalMinor` | integer | Monetary amount in **defined minor units** | Yes |
| `payload.currency` | ISO 4217 string | E.g. `VND` | Yes |

**Why have an envelope?** The four fields `schemaVersion`, `eventType`, `eventId`, and `occurredAt` are shared metadata, helping consumers select a decoder, log, and detect duplicates. `payload` holds data specific to `order.placed`. Never name the envelope after a class like `com.company.OrderEntity`.

**Why use integer money?** `double` often cannot represent decimal values accurately, easily causing rounding errors. `totalMinor` is the count of agreed minor units: for `VND`, 1999 is 1999 dong; for currencies with fractional units, the system must define the corresponding scale/rounding. If using a decimal string instead, you must also specify sign, precision, and rounding.

**Why include an offset in timestamps?** `2026-10-30T02:00:00Z` can be interpreted unambiguously across every timezone. A Java `LocalDateTime` without a timezone is not clear enough for cross-system event exchange. `occurredAt` is the event time, distinct from consumer processing time.

### 3.1. Event ID Is Not JMS ID

- `eventId`: application-level identifier for an event used for tracing/dedup; requires a policy keeping it constant when the same event is retried.
- `JMSMessageID`: assigned by the provider to a JMS message upon send; may differ on each attempt.
- `JMSCorrelationID`: header for correlating request–reply or related messages.
- `schemaId`: contract identifier in a registry, not a message ID.
- `traceId`: distributed trace identifier, which can be passed via a separate property.

Do not reuse one ID for everything just because their names sound similar. Share them only when the architecture defines an intentional convention.

### 3.2. Null, Absent, Empty, and Defaults

JSON distinguishes several states: field completely absent, field `null`, empty string `""`, number `0`. If `orderId` is required, absent/null/empty are all invalid. If `promotionCode` is optional, the contract must specify what absent means, whether `null` is allowed, and what default applies.

In Java, a missing `int` in JSON can silently become `0`, masking a missing field. You can use `Integer`/`Long` on wire DTOs and validate non-null, or use a JSON Schema validator. **Java type checking does not replace full schema validation**.

## 4. JSON Schema: A Contract Free of Java Package Names

A definition written in JSON Schema Draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-placed/v1.schema.json",
  "title": "OrderPlacedV1",
  "type": "object",
  "required": [
    "schemaVersion", "eventType", "eventId", "occurredAt", "payload"
  ],
  "properties": {
    "schemaVersion": { "type": "integer", "const": 1 },
    "eventType": { "type": "string", "const": "order.placed" },
    "eventId": { "type": "string", "format": "uuid" },
    "occurredAt": { "type": "string", "format": "date-time" },
    "payload": {
      "type": "object",
      "required": ["orderId", "totalMinor", "currency"],
      "properties": {
        "orderId": { "type": "string", "minLength": 1 },
        "totalMinor": { "type": "integer", "minimum": 0 },
        "currency": {
          "type": "string",
          "pattern": "^[A-Z]{3}$"
        }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

Explanation and limitations:

- `required` mandates field presence; `type`/`minimum` constrain types and ranges.
- `const` pins version 1 and the event type.
- `additionalProperties: true` lets a v1 reader ignore new fields *published as optional*, though it can also hide a typo. Thus contract governance must review fields rather than casually exposing sensitive data.
- `format: uuid`/`date-time` requires a validator with **format assertion** enabled; not every engine rejects invalid formats automatically.
- Pattern `^[A-Z]{3}$` does not verify that the currency code actually exists in ISO 4217; add an extra check if business rules require it.
- `$id` is an illustrative URI only, not a pre-existing server/schema registry.
- A schema describes structure, not full semantics like "totalMinor includes tax" or "occurredAt is when the order was accepted". Those rules need documentation and semantic tests.

**Do not put metadata like** `javaClass=com.company.internal.OrderEntity` or `_type=com.company.persistence.OrderAggregate` into the wire contract. Instead use `eventType`, `schemaVersion`, or a stable alias/schema ID.

## 5. Separating Domain Models from Wire DTOs via Mappers

An internal model might look like:

```java
record InternalOrder(
    String internalDbId,
    String publicOrderId,
    long grossInMinorUnits,
    String settlementCurrency
) {}
```

Transport DTO:

```java
public record OrderPlacedV1(
    Integer schemaVersion,
    String eventType,
    String eventId,
    String occurredAt,
    Payload payload
) {
    public record Payload(
        String orderId,
        Long totalMinor,
        String currency
    ) {}
}
```

An **intentionally selective** mapper:

```java
// Illustrative code placed in a class with access to both types:
OrderPlacedV1 toWire(InternalOrder domain, String eventId, String time) {
    return new OrderPlacedV1(
        1,
        "order.placed",
        eventId,
        time,
        new OrderPlacedV1.Payload(
            domain.publicOrderId(),
            domain.grossInMinorUnits(),
            domain.settlementCurrency()
        )
    );
}
```

Field `internalDbId` is never published. The name `grossInMinorUnits` can change in Java without altering `payload.totalMinor` on the wire. Consumers read the contract DTO and map it into the **consumer's own model/command**, without importing JPA entity classes from the producer.

### 5.1. Do Not Let Dynamic Maps Flow Through Every Layer

`Map<String,Object>`/`JsonNode` is useful when inspecting an envelope to read `eventType/schemaVersion`, yet if every business layer uses maps, wrong field names/missing data surface late at runtime. After schema classification, parse into a **versioned wire DTO**, validate, and then map to the domain model.

```text
TextMessage JSON
 → inspect eventType/schemaVersion properties
 → select parser/schema
 → parse + validate payload
 → OrderPlacedV1 DTO
 → explicit mapper
 → consumer-local domain object
 → business handler
```

## 6. MessageConverter in Spring JMS Does Not Create a Contract by Itself

`JmsTemplate.convertAndSend` and `receiveAndConvert` use `org.springframework.jms.support.converter.MessageConverter`.

| Java Value | `SimpleMessageConverter` Typically Creates |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` with valid types | `MapMessage` |
| `Serializable` | `ObjectMessage` |

Therefore **never assume** `convertAndSend(myDto)` produces JSON. Reasonable options include:

1. Use `ObjectMapper` to serialize the **wire DTO**, then `JmsTemplate.send(destination, session -> session.createTextMessage(json))`.
2. Build a custom `MessageConverter` converting the exact DTO version ↔ `TextMessage` or `BytesMessage`.
3. Use `MappingJackson2MessageConverter` with `MessageType.TEXT`, stable type ID aliases, and `setTypeIdMappings(...)`. If mappings are omitted when using a type property, the converter may emit the **raw Java class name** — coupling that should be avoided. Configure safe types/trusted packages.
4. With Avro/Protobuf, encode bytes in a `BytesMessage` and pass the appropriate schema identifier.

### 6.1. Synchronizing Body Metadata and JMS Properties

For example, a message has:

```text
JMS Properties:
  eventType     = "order.placed"
  schemaVersion = 1
  contentType   = "application/json"

TextMessage body:
  {"schemaVersion":1,"eventType":"order.placed", ...}
```

Properties allow JMS selectors/consumers to route without parsing the body. However, **body and JMS properties can drift out of sync**. Consumers must reject/quarantine when type/version in the two places disagree. `schemaId`, if present, must be a contract ID, not a Java class name.

JMS selectors filter headers/properties per standard semantics and **cannot automatically read nested JSON fields**. Keep business payloads and routing metadata distinct.

## 7. Runnable Project: Java 17+, Spring Boot 3.5.7, Artemis, Jackson JSON

This demo sends an `order.placed` event where the producer's domain field names differ from wire names. The consumer receives the raw JMS `TextMessage`, validates version/type, deserializes into a DTO, and maps to a local model. It also includes a unit test proving a v1 consumer reads a payload containing a new optional field.

### 7.1. Structure

```text
jms-contract-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/contract/
    │       ├── ContractApplication.java
    │       ├── InternalOrder.java
    │       ├── OrderPlacedV1.java
    │       └── OrderPlacedConsumer.java
    └── test/
        └── java/com/example/contract/
            └── ContractCompatibilityTest.java
```

### 7.2. Local Artemis Broker

```bash
docker run --rm -d --name jms-contract-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-contract-broker
```

Wait for the broker to become ready. These demo credentials are **for local use only**; production requires a secret manager, TLS, and ACLs. The lab broker may auto-create queues per policy; production queues should be pre-provisioned.

### 7.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jms-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-artemis` provides the JMS client/infrastructure; the JSON starter brings Jackson onto the classpath and Boot creates an `ObjectMapper` bean.

### 7.4. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

Use lab credentials only. Never commit real passwords into production YAML/properties; supply them via environment variables or secrets, TLS, and least-privilege permissions.

### 7.5. `InternalOrder.java`

```java
package com.example.contract;

// Internal model of the publishing service.
record InternalOrder(
        String internalDbId,
        String publicOrderId,
        long grossInMinorUnits,
        String settlementCurrency
) {}
```

### 7.6. `OrderPlacedV1.java`

```java
package com.example.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlacedV1(
        Integer schemaVersion,
        String eventType,
        String eventId,
        String occurredAt,
        Payload payload
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Payload(
            String orderId,
            Long totalMinor,
            String currency
    ) {}
}
```

`Integer`/`Long` distinguishes missing fields from numeric `0`. The ignore-unknown-fields annotation supports **one form of compatibility** when producers add optional fields, but does not replace schema validation and security checks.

### 7.7. `ContractApplication.java` — Producer Mapping Domain → Wire

```java
package com.example.contract;

import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractApplication.class, args);
    }

    @Bean
    CommandLineRunner publish(JmsTemplate template, ObjectMapper mapper) {
        return args -> {
            InternalOrder domain = new InternalOrder(
                    "internal-db-482", "order-42", 1999L, "VND");

            OrderPlacedV1 event = new OrderPlacedV1(
                    1,
                    "order.placed",
                    UUID.randomUUID().toString(),
                    Instant.now().toString(),
                    new OrderPlacedV1.Payload(
                            domain.publicOrderId(),
                            domain.grossInMinorUnits(),
                            domain.settlementCurrency()
                    )
            );

            // Serialize outside the callback so Jackson exceptions are not
            // coerced into JMSException inside MessageCreator.
            String json = mapper.writeValueAsString(event);

            template.send("demo.contract.order-placed.v1", session -> {
                TextMessage message = session.createTextMessage(json);
                message.setStringProperty("eventType", event.eventType());
                message.setIntProperty("schemaVersion", event.schemaVersion());
                message.setStringProperty("contentType", "application/json");
                return message;
            });
            System.out.println("Published contract: order.placed v1");
        };
    }
}
```

Here `internalDbId` never goes on the wire. `schemaVersion` and `eventType` are present in both the body and JMS properties. `JmsTemplate` manages the connection/session/producer for the operation; the mapper defines the business contract.

### 7.8. `OrderPlacedConsumer.java` — Parse, Validate, Map DTO

```java
package com.example.contract;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedConsumer {

    private final ObjectMapper mapper;

    OrderPlacedConsumer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @JmsListener(destination = "demo.contract.order-placed.v1")
    public void consume(TextMessage raw) throws Exception {
        if (!"application/json".equals(
                raw.getStringProperty("contentType"))) {
            throw new IllegalArgumentException("Unsupported content type");
        }
        if (!raw.propertyExists("schemaVersion")
                || raw.getIntProperty("schemaVersion") != 1
                || !"order.placed".equals(
                        raw.getStringProperty("eventType"))) {
            throw new IllegalArgumentException("Unsupported contract");
        }

        OrderPlacedV1 event = mapper.readValue(
                raw.getText(), OrderPlacedV1.class);

        if (!Objects.equals(event.schemaVersion(), 1)
                || !"order.placed".equals(event.eventType())) {
            throw new IllegalArgumentException(
                    "Body and JMS properties mismatch");
        }

        if (event.eventId() == null || event.occurredAt() == null) {
            throw new IllegalArgumentException("Missing envelope field");
        }
        UUID.fromString(event.eventId());
        Instant.parse(event.occurredAt());

        OrderPlacedV1.Payload p = event.payload();
        if (p == null || p.orderId() == null || p.orderId().isBlank()
                || p.totalMinor() == null || p.totalMinor() < 0
                || p.currency() == null
                || !p.currency().matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid payload");
        }

        // Consumer-owned model; never imports producer's internal class.
        ConsumerOrderView local = new ConsumerOrderView(
                p.orderId(), p.totalMinor(), p.currency());

        System.out.println("Consumed contract: "
                + local.orderId() + " "
                + local.amountMinor() + " "
                + local.currencyCode());
    }
}

record ConsumerOrderView(
        String orderId,
        long amountMinor,
        String currencyCode
) {}
```

This is **illustrative validation**: production requires a real JSON Schema validator, business checks, payload size limits, idempotency, and DLQ handling. `@JmsListener` runs on a thread independent of the producer; do not use console line order to infer delivery ordering.

### 7.9. Running the Demo

```bash
mvn spring-boot:run
```

With the broker ready and no other consumer on the demo queue, the lines printed by the code include:

```text
Published contract: order.placed v1
Consumed contract: order-42 1999 VND
```

**The order of the two lines may be reversed**, since the listener is asynchronous. Spring and Artemis logs also appear alongside them. Stop the broker:

```bash
docker stop jms-contract-broker
```

The example does not guarantee exactly-once processing, failover, or atomicity with a database; design those separately for production.

## 8. Compatibility Testing When Adding Optional Fields

Suppose producer v1.1 adds `payload.deliveryChannel` and `sourceSystem`. That can be a **forward-compatible** change for a v1 reader if the reader is permitted to ignore unknown fields; the meaning of existing fields must not change.

### 8.1. `ContractCompatibilityTest.java`

```java
package com.example.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContractCompatibilityTest {

    @Test
    void oldReaderAcceptsNewOptionalFields() throws Exception {
        String json = """
                {
                  "schemaVersion": 1,
                  "eventType": "order.placed",
                  "eventId": "123e4567-e89b-42d3-a456-426614174000",
                  "occurredAt": "2026-10-30T02:00:00Z",
                  "payload": {
                    "orderId": "order-42",
                    "totalMinor": 1999,
                    "currency": "VND",
                    "deliveryChannel": "pickup"
                  },
                  "sourceSystem": "web"
                }
                """;

        OrderPlacedV1 event = new ObjectMapper()
                .readValue(json, OrderPlacedV1.class);

        assertEquals(1, event.schemaVersion());
        assertEquals("order-42", event.payload().orderId());
        assertEquals(1999L, event.payload().totalMinor());
        assertEquals("VND", event.payload().currency());
    }
}
```

Run with `mvn test`. The test is designed to **pass** and demonstrates **one specific compatibility direction**, not that all producer/consumer versions are compatible. If a producer renames `totalMinor` to `grossMinorUnits` on the wire and removes the old field, the v1 reader gets `totalMinor=null` and rejects it during validation. Java refactoring is not a valid reason to break a public schema.

## 9. Versioning and Compatibility

**Contract versions differ from JAR versions.** You can emit `schemaVersion=1` across many application releases as long as the payload schema/semantics stay unchanged.

| Change | Common Impact | Handling Strategy |
| --- | --- | --- |
| Adding an optional field, reader ignores unknown | Potentially forward compatible | Test old readers |
| Adding a field required by new readers | Old messages lack it | Default value or breaking version |
| Renaming `orderId` to `id` | Old readers lose the field | Breaking |
| Removing required `currency` | Consumers lose context | Breaking |
| `totalMinor` integer → `total` double | Wrong type, precision drift | Breaking |
| Changing currency unit while keeping field name | Silent data corruption | Semantically breaking |
| Adding an enum value | Old readers may not recognize it | Unknown-value policy |
| Replacing offset timestamp with local datetime | Loses timezone | Breaking |
| Changing Java class/package, keeping JSON wire | No consumer impact | Not breaking |
| Adding permitted metadata property | Usually non-breaking | Test routing |

**Backward compatibility:** newer readers can read data produced by older writers. **Forward compatibility:** older readers can read data from newer writers. **Full:** both directions under a defined policy. Never ask "is it compatible?" without specifying which writer and reader versions.

### 9.1. Breaking Migration Strategy

```text
1. Publish schema v2 and migration guide
2. Deploy readers supporting v1 + v2
3. Begin emitting v2 per agreed rollout
4. Monitor queue backlog, consumer lag, DLQ, and decode errors
5. Remove v1 after retention ends and no old consumers remain
```

You can keep `eventType=order.placed` and bump `schemaVersion=2`, or use a versioned event name `order.placed.v2`. Choose one consistent convention across body, JMS properties, and registry. If dual-publishing v1/v2, design deduplication so the same business event is not processed twice.

**Semantic changes can also break contracts** even when JSON parses cleanly: changing `totalMinor` from **post-tax** to **pre-tax** while keeping the same name/type/version causes consumers to miscalculate, which is often more dangerous than a parsing exception.

## 10. Schema-First and Contract Governance

Recommended workflow:

1. Designate a **schema owner**, producers, and consumers.
2. Document fields, types, required/optional, nullability, units, timezones, enum values, PII, retention, and version.
3. Store schemas in a contract repository or registry with history, reviews, and access controls.
4. Use code generation for DTOs if helpful, **without** forcing every service to share a Java entity/JPA library.
5. Maintain golden JSON fixtures, producer tests, and consumer compatibility tests.
6. Enforce schema compatibility checks in CI; require reviews for breaking changes.
7. Monitor `eventType`, `schemaVersion`, invalid schemas, DLQ, and consumer lag during deployment.
8. Announce deprecation and retention windows before retiring old schemas.

Tests should cover both positive and negative cases: missing/null required fields, wrong types, malformed JSON, unknown enums, oversize payloads, timezones, wrong unit mapping, body/property version mismatches, and schema migrations.

## 11. JSON, Avro, or Protobuf?

| Criterion | JSON + JSON Schema | Avro | Protobuf |
| --- | --- | --- | --- |
| Readability when debugging | High | Binary, hard to read directly | Binary, hard to read directly |
| Contract decoupled from Java classes | Yes | Yes | Yes |
| Common JMS body | `TextMessage` | `BytesMessage` | `BytesMessage` |
| Size | Usually larger than binary | Usually compact | Usually compact |
| Evolution mechanism | Schema policy/CI | Writer–reader resolution/defaults | Field numbers and presence |
| Multi-language support | Broad | Broad | Broad |
| Main pitfalls | Precision, unknown fields, defaults | Schema ID and union/default rules | Never reusing field numbers |

Small, easy-to-debug events usually suit JSON. High-throughput systems or those wanting strong code generation can consider Avro/Protobuf. **A binary format does not make a contract safe by itself** without version governance and semantic validation.

## 12. Delivery, Security, and Idempotency

A stable schema **does not** guarantee exactly-once message processing. JMS can redeliver on disconnects or transaction rollbacks; consumers should use `eventId`/business idempotency keys and track processed state to avoid duplicate side effects. If a producer both writes to a DB and sends to JMS, **dual-write** risks arise; `@Transactional` on the database does not automatically form an atomic transaction with JMS. Transactional outbox is one way to mitigate this: write the business change + outbox row in the same DB transaction, then publish with retries.

Security:

- Publish only necessary fields; never serialize entities containing passwords/PII/admin fields.
- Enforce broker authentication, send/consume ACLs, TLS, retention, and size/nesting limits.
- Never deserialize Java `ObjectMessage` from untrusted sources.
- With type ID converters, use stable aliases and allowed classes/trusted packages rather than instantiating arbitrary Java FQCNs from messages.
- Log `eventId`, `eventType`, version, and outcome metadata; avoid logging full JSON containing private data.
- For invalid-schema messages, route to DLQ/quarantine instead of infinitely retrying permanent errors.

## 13. Common Errors

| Error | Consequence | Fix |
| --- | --- | --- |
| Serializing JPA entities directly | Coupling and leaking internal fields | Separate contract DTO |
| Using raw Java FQCN in type property | Class refactoring breaks consumers | Stable alias/schemaId |
| Assuming `convertAndSend` produces JSON | May create `ObjectMessage` | JSON converter or explicit TextMessage |
| Java refactor changes JSON field names | Unintended breaking change | Explicit mapper and golden tests |
| Using `double` for money | Precision/rounding errors | Integer minor units or decimal string |
| Timestamps without offsets | Timezone ambiguity | ISO 8601/RFC 3339 offset |
| Enum ordinals on the wire | Adding enum values shifts meanings | Stable strings and unknown policy |
| Adding required field without migration | Old/new readers fail | Optional/default or v2 |
| Ignoring unknown fields without validating | Masks typos/unexpected payloads | Schema validation + security checks |
| JMS properties disagree with body | Wrong decoder selected | Enforce consistency check |
| Changing field semantics while keeping version | Parses fine but business logic breaks | Semantic review and new version |
| Missing contract tests | Incompatible version deployments | Fixtures + compatibility matrix |
| Infinite retries on poison messages | Queue blockage/CPU spike | DLQ, alerting, quarantine |
| Confusing schema ID with JMS correlation | Wrong decoding/routing | Separate each identifier clearly |

## 14. Code Review Checklist

- [ ] Event name and version carry business meaning, independent of Java classes.
- [ ] Schema has an owner, changelog, fields, types, required/optional rules, and units.
- [ ] Producer maps domain → wire DTO, never publishing entities/JPA proxies.
- [ ] Consumer maps wire DTO → local model; validates schema before business logic.
- [ ] No Java FQCN/`serialVersionUID` acts as public identity.
- [ ] Converter/serializer is configured and tested, never assuming POJOs turn into JSON automatically.
- [ ] Body `eventType/schemaVersion` and JMS properties match.
- [ ] Compatible golden fixtures exist for old/new readers and writers.
- [ ] Schema changes are reviewed for both structure **and semantics**.
- [ ] Policies exist for malformed/unknown versions, retries, DLQ, and idempotency.
- [ ] No secrets/PII exposed; auth/ACL/TLS and payload size limits are in place.

## 15. Self-Check Questions

**1. Why should you not send `OrderEntity` directly?**  
Because entities are implementation details, tied to Java serialization/JPA, and may contain fields not permitted for publication.

**2. Is the Java record `OrderPlacedV1` the sole contract?**  
No. It is a Java adapter; the published JSON Schema and business rules form the language-independent contract.

**3. Why does `JmsTemplate.convertAndSend(dto)` not produce JSON by default?**  
Because the default converter picks the JMS body type from the Java value; it may use `ObjectMessage` for `Serializable`.

**4. Is adding an optional `deliveryChannel` field always compatible?**  
Not always. It is only compatible when older readers ignore unknown fields or have rules handling it; tests are required.

**5. Does renaming an internal Java field require bumping the schema version?**  
No, as long as the wire JSON field names, types, and meanings remain unchanged.

**6. Is changing `totalMinor` from integer to decimal breaking?**  
Yes, it changes type/precision and often semantics, requiring migration/versioning.

**7. How do a schema ID and `JMSCorrelationID` differ?**  
Schema ID selects the decoder; `JMSCorrelationID` links messages such as in request–reply.

**8. Does JSON Schema guarantee exactly-once delivery on its own?**  
No. Delivery, transactions, and idempotency must be designed separately.

**9. Why should timestamps include UTC or an offset?**  
So consumers in different timezones interpret the exact same instant in time.

**10. When should you choose Avro/Protobuf?**  
When compact binary payloads, code generation, and strong schema tooling are needed; governance is still required.

## 16. Official References

1. [Spring Framework — JMS Sending and Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
2. [Spring Framework 6.2 — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
3. [Spring Framework — JMS Reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)
4. [Spring Boot 3.5 — JMS with ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
5. [Spring Boot 3.5 — JSON / Jackson](https://docs.spring.io/spring-boot/3.5/reference/features/json.html)
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
7. [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
8. [Apache Avro Schema Specification](https://avro.apache.org/docs/current/specification/)
9. [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)