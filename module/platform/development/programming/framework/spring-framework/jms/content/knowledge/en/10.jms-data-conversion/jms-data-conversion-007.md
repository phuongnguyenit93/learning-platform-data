# Schema Versioning and Bidirectional Compatibility in Spring JMS

## 1. Context and Goal

In Spring JMS systems, producers and consumers are often **not deployed simultaneously**. For example, the order service emits `OrderCreated` using schema v1; the next week the producer is upgraded to send schema v2 with an added delivery note. During rollout, one consumer is still on the old version, another has been upgraded, and the Queue may still hold unprocessed old messages.

Without a **schema evolution** strategy, seemingly minor changes — adding a field, renaming a field, changing `int` to `String`, changing currency units — can cause listener deserialization to fail, send messages to the DLQ, or worse, **succeed syntactically while processing the wrong meaning**.

This lesson focuses on **versioning data structures transmitted over JMS and guaranteeing bidirectional compatibility** between writer/producer and reader/consumer:

- Understand `schema`, `writer schema`, `reader schema`, **backward**, **forward**, **full/bidirectional**, and **transitive** compatibility.
- Build the four-case matrix of producer v1/v2 × consumer v1/v2.
- Design a **non-breaking** change adding an optional field and handling unknown/missing fields.
- Put schema name/version into **JMS properties** and use `MessageConverter` or a JSON parser with clear responsibilities.
- Build a **Java 17 + Spring Boot 3.5 + embedded Artemis + Jackson** example proving both read directions.
- Recognize changes that appear valid at the data-type level yet **break the business contract**.
- Establish deployment strategies, contract tests, and handling for unconvertible messages.

**Starting point:** Jakarta Messaging/JMS is a **message transport channel**; it does not define JSON, Avro, or Protobuf schemas for domain objects on its own. There is no standard `JMSSchemaVersion` header. Applications must manage contracts and versions, optionally using serializer libraries or schema registries outside JMS.

## 2. Distinguishing Schema, Message Version, and Application Version

A **schema** describes the structure and rules of transmitted data: field names, field types, required constraints, default values, invariants (e.g. `amount >= 0`), event identifiers, and semantics. Distinguish three things:

| Concept | Example | What Does It Represent? |
| --- | --- | --- |
| **Schema version** | `orders.created` v2 | Version of the message format contract. |
| **Application version** | `order-service 5.8.0` | Service deployment version; can support multiple schemas. |
| **JMSMessageID** | `ID:...` | Provider-assigned identifier for one send attempt, **not** the schema version. |

A deployed service version 5.8 might **still write schema v1** during rollout while **reading both schema v1 and v2**. Never set `schemaVersion = 5` merely because the JAR artifact has major version 5.

The **writer schema** is the data structure the producer actually emits. The **reader schema** is the structure the consumer expects and knows how to read. The same message can be written by a new producer while an old consumer must still deserialize it if the system claims forward compatibility.

Example v1 payload:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50
}
~~~

v2 payload adds an **optional** field:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50,
  "note": "gift"
}
~~~

For both versions to coexist:

1. **Reader v1** must accept the unknown `note` field (or have the schema resolver ignore it).
2. **Reader v2** must accept a v1 message lacking `note` and assign an appropriate value (e.g. `null`, or an agreed default).
3. Both must preserve the meaning of `orderId` and `amount`.
4. Never assume a specific tool (Jackson/Avro/JSON Schema) applies identical rules; compatibility **depends on the format, validator, and reader configuration**.

## 3. Backward, Forward, and Full Compatibility: Read Direction Determines the Name

Saying `schema v2 is compatible with v1` without specifying direction easily causes confusion. Always ask **"Which reader version reads data written by which writer version?"**

| Compatibility Type | What Is Guaranteed | How to Remember |
| --- | --- | --- |
| **Backward** | **New reader (v2)** can read data from **old writer (v1)**. | New code reads old data. |
| **Forward** | **Old reader (v1)** can read data from **new writer (v2)**. | Old code reads new data. |
| **Full / two-way** | Holds in **both backward and forward** directions. | Both directions can read within the tested version scope. |
| **Transitive** | Checks compatibility against **all relevant prior versions**, not only the immediate predecessor. | Does not forget messages from multiple generations back. |

Minimum matrix for v1 and v2:

| Writer Sends | Reader Receives | Scenario | Condition |
| --- | --- | --- | --- |
| **v1** | **v1** | Baseline | v1 itself must work. |
| **v1** | **v2** | **Backward** | Reader v2 reads and processes v1 data. |
| **v2** | **v1** | **Forward** | Reader v1 reads and processes v2 data. |
| **v2** | **v2** | Baseline | v2 itself must work. |

When calling a v1–v2 pair **fully compatible**, all four cells must be verified, with the two diagonal cells serving as key proof.

### 3.1. Backward Does Not Mean Old Consumers Automatically Read New Producers

For example, reader v2 handles a default `note` when a v1 message lacks the field. That is **backward**, yet does not prove reader v1 accepts a v2 payload containing `note`. If reader v1 is configured strictly (rejecting unknown fields), **forward will fail**.

### 3.2. Forward Does Not Mean New Consumers Automatically Read Old Producers

Suppose producer v2 omits a field that reader v1 did not use, so reader v1 still reads it. However, reader v2 may require a new field that writer v1 did not supply; then **backward fails**.

### 3.3. FULL Does Not Mean "Every Version Understands Every Piece of Data"

The `BACKWARD`, `FORWARD`, and `FULL` modes in many schema registries only check a new schema against the **single immediately preceding schema**. Only `*_TRANSITIVE` modes check against all earlier versions within the registry scope. Never claim `FULL` equals `FULL_TRANSITIVE`, or that it automatically guarantees semantic conversion in business code.

## 4. Why Queues, Topics, and Independent Deployments Make This Critical

JMS sends and receives messages **independently of another service's Java version**:

~~~mermaid
flowchart LR
    P1["Producer v1"] --> Q[("orders.events")]
    P2["Producer v2"] --> Q
    Q --> C1["Consumer v1"]
    Q --> C2["Consumer v2"]
~~~

This diagram illustrates that **versions can coexist over time**; on the same Queue, each message delivery typically goes to **one** competing consumer, not broadcast to both C1 and C2. On a Topic, each subscription receives copies according to its JMS semantics.

Real-world situations:

- **Rolling deployment:** some v1 reader instances remain running while v2 readers start up.
- **Message backlog:** a v1 message stored yesterday may be read by a v2 reader today.
- **Redelivery/DLQ replay:** messages may be replayed days later, even after producer v1 has been retired.
- **Multi-service subscriptions:** multiple teams upgrade consumers on different schedules.
- **Blue/green deployment:** two consumer fleets on different versions may run concurrently during a cutover window.

With a Queue, if **a v1 consumer cannot read v2** while still running, it may receive v2 messages and fail/roll back continuously; you cannot rely on "a new consumer is also running" to keep v2 away from the old consumer.

With a Topic, an old subscriber can continue receiving new events. If a durable subscription holds a backlog, a new reader's ability to read **old** data becomes even more critical.

**Architectural conclusion:** compatibility is a contract between **writer and reader**, not just a property on a message; it must align with **co-deployment, backlog retention, and error handling**.

## 5. Safe Evolution Example: Adding an Optional Field

v1 definition:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50
}
~~~

v2 definition:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50,
  "note": "gift"
}
~~~

With an intentionally designed **permissive JSON reader**:

- Reader v1 reading v2: ignores the unknown `note`, while still accurately reading `orderId` and `amount`. This is **forward**.
- Reader v2 reading v1: missing `note` maps to `null` or a meaningful default. This is **backward**.
- Both together: **full compatibility at the reader implementation level** for the two payloads and stated assumptions.

**Important caveat:** if schema v1 uses JSON Schema `additionalProperties: false` and a validator enforces it strictly, v2 adding `note` can be **rejected by reader v1**, even though a Jackson DTO could ignore that field. Compatibility depends on both **schema validation** and **deserializer code/business logic**. Never conflate "Jackson can parse it" with "the schema contract is valid across all consumers".

### 5.1. Which Fields Are Truly "Optional"?

A new field is genuinely optional when:

1. Old writers omit the field and new readers still process accurately.
2. New readers have a **clearly specified** default value or fallback logic.
3. Business code does not assume the field is always present.
4. If sending `null` vs. omitting the field have different meanings, the contract documents them separately.
5. The default value makes business sense; never arbitrarily turn `null` into `0`.

For example, adding `discountPercent` with default `0` can be sensible **if everyone agrees an absent field means no discount**. However, adding `currency` with default `VND` can be wrong if old data used USD. **Semantic** compatibility matters more than whether a JSON parser avoids throwing an exception.

## 6. Changes That Easily Cause Breaking Changes

| Change from v1 to v2 | Risk | Recommendation |
| --- | --- | --- |
| **Add an optional field** | Old reader rejects unknown field; new reader mishandles missing. | Old reader ignores unknown when appropriate; new reader has default/nullable; test both directions. |
| **Add a required field** | Old payloads lack the field; new reader fails. | Introduce as optional first, backfill, or emit a new event. |
| **Remove a field** | Old readers still depend on the removed field. | Deprecate and measure usage, dual-write phase, remove only when no consumers depend on it. |
| **Rename a field** | Old or new reader does not recognize the other name. | Add alias/adapter or dual fields with an explicit migration. |
| **Change type `number` → `string`** | Converter may fail or perform risky coercion. | Keep old field, add new clearly named field, major version if needed. |
| **Change `amount` from VND to thousands of VND** | Data parses cleanly yet business results are wrong. | Never change meaning silently; add field/unit, new event version. |
| **Add an enum value** | Old reader switch without `default` fails or misbehaves. | Unknown-enum strategy, test, and plan expand/deploy. |
| **Change `null` ↔ missing** | Readers have differing semantics. | Specify nullability, omission, and defaults. |
| **Change schema while keeping same `schemaVersion`** | Cannot select the right decoder; replay breaks. | Immutable versions; never rewrite published contracts. |
| **Change format JSON → Avro/Protobuf** | Old consumers cannot parse new payloads. | Explicit content type/schema ID and rollout/routing/dual publication. |
| **Change routing/Queue/Topic** | Consumers may miss messages despite valid schema. | Change routing independently; test delivery and ACLs. |

There is no universal rule that "adding a field is always backward/forward/full" across **all** of JSON Schema, Avro, Protobuf, and Jackson. For example, Avro has writer/reader schema resolution; JSON Schema has `required` and `additionalProperties`; Protobuf relies on field numbers, reserved tags, and wire types. Registry/provider policies must be tested on the **actual format**.

## 7. Where Does Schema Version Live in JMS?

Standard JMS has headers such as `JMSType`, `JMSCorrelationID`, and custom properties. **There is no standard JMS header named `JMSSchemaVersion`**. You can set:

- `JMSType = "order.created"` to tag the business type.
- `schemaName = "orders.created"` as a `String` property.
- `schemaVersion = 2` as an `int` property.
- `contentType = "application/json"` as a `String` property by system convention.
- `eventId` as a `String` property to support idempotency.

Example in Spring JMS:

~~~java
// Fragment inside a Spring bean with JmsTemplate jmsTemplate.
jmsTemplate.convertAndSend("orders.events", jsonBody, msg -> {
    msg.setJMSType("order.created");
    msg.setStringProperty("schemaName", "orders.created");
    msg.setIntProperty("schemaVersion", 2);
    msg.setStringProperty("contentType", "application/json");
    msg.setStringProperty("eventId", "event-O-129");
    return msg;
});
~~~

`jsonBody` must be serialized according to the contract; metadata does not magically turn the body into schema v2. If `jsonBody` is still v1 while the property says v2, a version-driven consumer will **pick the wrong decoder**. Treat serialization and metadata as **one logical operation** and test them together.

With a raw JMS consumer:

~~~java
// Fragment: jakarta.jms.Message received has been received.
String schemaName = received.getStringProperty("schemaName");
int schemaVersion = received.getIntProperty("schemaVersion");
String contentType = received.getStringProperty("contentType");
~~~

**Validate:** does the property actually exist? How are wrong types handled? Do not silently default missing `schemaVersion=1` for every message lacking the field unless the contract explicitly mandates it. For legacy systems, you can explicitly define `missing version => v1` with a bounded support window; once migration ends, require the version strictly.

### 7.1. JMS Selectors by Version

~~~java
// Fragment: jakarta.jms.Session session and Queue queue are available.
jakarta.jms.MessageConsumer consumer = session.createConsumer(
        queue, "schemaName = 'orders.created' AND schemaVersion = 2");
~~~

Selectors operate on **headers/properties**, not by parsing the JSON body. If the version is sent as `String "2"` instead of `int 2`, a numeric selector condition may fail to match.

Use selectors during migration with caution: on a **Queue**, unmatched messages can accumulate if no other consumer picks them up; on a **Topic**, selectors belong to subscription filters and have different semantics. Selectors are **neither a security mechanism** nor schema validation.

### 7.2. Is a Schema Registry Part of JMS?

**No.** Jakarta Messaging/JMS does not provide a built-in schema registry or compatibility checker. You can adopt an independent **schema catalog/registry** to register versions, store schema IDs, run CI tooling, and carry schema IDs/versions in JMS properties or envelopes.

Confluent Schema Registry is a well-known ecosystem example from Kafka; **do not claim its integration is built into ActiveMQ Artemis or JMS by default**. To use one with JMS, you must choose the serializer, registry client, schema identifier, and decode/validation workflow yourself.

## 8. How Does Spring's MessageConverter Relate?

Spring JMS defines the `org.springframework.jms.support.converter.MessageConverter` abstraction:

- `toMessage(Object, Session)`: converts a Java object into a `jakarta.jms.Message` for sending.
- `fromMessage(Message)`: converts a received JMS Message into a Java object.

`JmsTemplate.convertAndSend(...)` uses the converter to build the JMS message. `JmsTemplate.receiveAndConvert(...)` uses the converter to read the payload. For listeners, the container can use a converter and map method arguments.

### 8.1. The Default Converter Does Not Provide Automatic Domain Versioning

`SimpleMessageConverter` handles common types such as:

| Java Input | JMS Message |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` with valid values | `MapMessage` |
| Certain `Serializable` objects | `ObjectMessage` per provider/settings |

**Never assume every POJO passed to `convertAndSend` is serialized to JSON.** For cross-service systems, JSON `TextMessage` or Avro/Protobuf `BytesMessage` with explicit contracts are usually far easier to manage for compatibility than relying on Java `ObjectMessage` (class names, `serialVersionUID`, serialization, and deserialization exploit risks).

### 8.2. Two JSON Strategies

**Approach A — send a JSON String and decode explicitly by version:** explicit code, easy to control when supporting v1/v2 simultaneously. The demo in Section 10 uses this approach, avoiding reliance on automatic type-header rules.

**Approach B — use a custom `MessageConverter`, such as `MappingJackson2MessageConverter`:** converts domain objects to JSON messages and messages back to domain types, optionally using a type-id property and explicit mappings. However, selecting a Java type from a JMS header **does not automatically mean** schema compatibility: you still need validators, migrations, multi-version readers, and controls on allowed deserialization types.

If the contract classifies messages by `schemaName` and `schemaVersion`, reader selection should **whitelist** supported combinations rather than loading arbitrary Java class names sent by a producer. Never turn an untrusted JMS header into permission to load arbitrary classes.

## 9. Sample JSON Contracts: v1 and v2

One way to document changes is to store two immutable versioned JSON Schema files. Below are **illustrative schemas**, not files automatically generated by JMS:

**`order-created-v1.schema.json`:**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderCreated v1",
  "type": "object",
  "required": ["orderId", "amount"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1},
    "amount": {"type": "number", "minimum": 0}
  },
  "additionalProperties": true
}
~~~

**`order-created-v2.schema.json`:**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderCreated v2",
  "type": "object",
  "required": ["orderId", "amount"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1},
    "amount": {"type": "number", "minimum": 0},
    "note": {"type": ["string", "null"]}
  },
  "additionalProperties": true
}
~~~

Meaning:

1. `orderId` and `amount` remain **required, keeping the same types and semantics**.
2. `note` is not in `required`, so a v1 message lacking the field remains valid under v2.
3. `additionalProperties: true` intentionally permits undescribed fields to illustrate an old reader accepting a payload with added `note`. For security-critical APIs, such an open policy may be unacceptable; design schemas/validators and rollouts accordingly.
4. `type: ["string", "null"]` allows sending `null`, though **missing** and **`null`** remain two distinct JSON states; the consumer decides the fallback.
5. Schemas validate structure/types, not whether `amount` matches the expected business currency unit. Changing units without changing the field is a **breaking semantic change**.

**Important practice:** run a schema validator against real payloads and run CI tests across multiple versions. The Java example below uses **Jackson DTOs** to illustrate read compatibility, without executing a JSON Schema validator from those two files.

## 10. Runnable Demo: Bidirectional JSON Reading via Spring JMS

This lab uses **Java 17+, Maven, Spring Boot 3.5.7, embedded ActiveMQ Artemis, Jackson**. We have **producer v1/v2** and **reader v1/v2**, testing the two hard cross-version directions directly:

- **Writer v2 → Reader v1**: reader v1 ignores the new `note`.
- **Writer v1 → Reader v2**: reader v2 treats missing `note` as `null`.

This demonstrates **full compatibility of the two specific DTOs in the demo**, not that every JSON Schema/consumer format accepts this change.

### 10.1. Project Structure

~~~text
jms-schema-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jmsschema/
        │   └── JmsSchemaDemoApplication.java
        └── resources/
            └── application.properties
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-schema-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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
~~~

In the example, `spring-boot-starter-json` provides Jackson `ObjectMapper` for JSON encoding/decoding; `spring-boot-starter-artemis` brings in the Spring JMS client; `artemis-jakarta-server` enables running the embedded broker. The parent manages compatible dependency versions.

### 10.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.schema
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

`demo.schema` is created when the embedded broker starts. Persistence is intentionally disabled **only for the demo**; never treat that as proof of replay capability across restarts. `receive-timeout=5s` prevents hanging indefinitely on failure.

### 10.4. JmsSchemaDemoApplication.java

~~~java
package com.example.jmsschema;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsSchemaDemoApplication {

    public record OrderV1(String orderId, BigDecimal amount) {}

    public record OrderV2(
            String orderId,
            BigDecimal amount,
            String note) {}

    public static void main(String[] args) {
        SpringApplication.run(JmsSchemaDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            ObjectMapper mapper = new ObjectMapper()
                    .configure(
                            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                            false);

            // 1) Writer v2 -> Reader v1 (FORWARD).
            String jsonV2 = mapper.writeValueAsString(
                    new OrderV2("O-NEW", new BigDecimal("125.50"), "gift"));

            template.convertAndSend("demo.schema", jsonV2, message -> {
                message.setStringProperty("schemaName", "orders.created");
                message.setIntProperty("schemaVersion", 2);
                return message;
            });

            TextMessage fromV2 = receiveText(template);
            int versionV2 = fromV2.getIntProperty("schemaVersion");
            OrderV1 oldReader = mapper.readValue(
                    fromV2.getText(), OrderV1.class);

            requireCore(oldReader.orderId(), oldReader.amount());
            System.out.println(
                    "V2->V1: " + oldReader.orderId() + " | "
                            + oldReader.amount());
            System.out.println("versionFromV2=" + versionV2);

            // 2) Writer v1 -> Reader v2 (BACKWARD).
            String jsonV1 = mapper.writeValueAsString(
                    new OrderV1("O-OLD", new BigDecimal("100.00")));

            template.convertAndSend("demo.schema", jsonV1, message -> {
                message.setStringProperty("schemaName", "orders.created");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            TextMessage fromV1 = receiveText(template);
            int versionV1 = fromV1.getIntProperty("schemaVersion");
            OrderV2 newReader = mapper.readValue(
                    fromV1.getText(), OrderV2.class);

            requireCore(newReader.orderId(), newReader.amount());
            System.out.println(
                    "V1->V2: " + newReader.orderId() + " | "
                            + newReader.amount() + " | note="
                            + newReader.note());
            System.out.println("versionFromV1=" + versionV1);
        };
    }

    private static TextMessage receiveText(JmsTemplate template)
            throws JMSException {

        Message message = template.receive("demo.schema");
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "Did not receive TextMessage within 5 seconds");
        }
        String name = text.getStringProperty("schemaName");
        if (!"orders.created".equals(name)) {
            throw new IllegalArgumentException(
                    "Unsupported schema: " + name);
        }
        return text;
    }

    private static void requireCore(String orderId, BigDecimal amount) {
        if (orderId == null || orderId.isBlank()
                || amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "Missing or invalid core order fields");
        }
    }
}
~~~

**Step-by-step in the demo:**

1. **DTO v1** has `orderId`, `amount`; **DTO v2** adds optional `note`.
2. An `ObjectMapper` is configured with **`FAIL_ON_UNKNOWN_PROPERTIES=false`**. This is an intentional decision: reader v1 ignores `note` when writer v2 sends it. In Jackson 2.x, do not assume the default configuration permits this.
3. `OrderV2` is serialized to a JSON String and passed to `JmsTemplate.convertAndSend`; `SimpleMessageConverter` creates a `TextMessage` without automatically serializing records.
4. `MessagePostProcessor` attaches `schemaName` and **`schemaVersion` of type `int`**. JMS does not automatically verify that the body actually conforms to that version.
5. `JmsTemplate.receive` returns a raw `Message` to inspect metadata, then extracts `TextMessage`.
6. **Reader v1** ignores the unknown `note`, keeping `orderId` and `amount` → **forward** example.
7. Sending v1 JSON, **Reader v2** deserializes it with `note` as `null` because the field is absent → **backward** example.
8. `requireCore` still checks required business fields; the deserializer parsing cleanly **does not prove** the data is valid.

Run from the `jms-schema-demo` directory:

~~~bash
mvn spring-boot:run
~~~

The lines printed by the **application code**, alongside Maven/Spring/Artemis logs, are expected to be:

~~~text
V2->V1: O-NEW | 125.50
versionFromV2=2
V1->V2: O-OLD | 100.00 | note=null
versionFromV1=1
~~~

The code intentionally receives each message immediately after sending on a fresh broker with a single consumer. If an environment shares a queue or has multiple consumers, receive order may vary and test isolation must be used. The result above is the **expected stdout** of the demo, independent of timestamps or message IDs assigned by the JMS provider.

### 10.5. Why Not "Just Ignore Unknown Fields to Be Compatible"?

Flipping `FAIL_ON_UNKNOWN_PROPERTIES` to `true` causes reader v1 to reject the unknown `note` field in v2 JSON (typically with `UnrecognizedPropertyException`). This proves **forward compatibility depends on reader configuration**.

However, enabling ignore-unknown is not enough if writer v2:

- Removes `orderId`: DTO v1 gets `orderId=null`; `requireCore` must block it.
- Changes `amount` to an object or unparseable data: the converter may throw an error.
- Changes the unit of `amount` while keeping a JSON number type: deserialization succeeds yet business logic is wrong.
- Adds a required field where consumer v2 lacks a default when reading v1.
- Puts untrusted content into sensitive fields: readers must validate thoroughly.

In systems with strict schema validators or high security requirements, explicit rules are needed and you must **not disable validation globally** just to get through a rollout. The demo is evidence at the Java deserialization layer, not a substitute for a schema registry and semantic contract tests.

## 11. How Does Compatibility Differ Across JSON, Avro, and Protobuf?

| Technology | How Schema Is Recognized | Evolution Details to Remember |
| --- | --- | --- |
| **JSON + Jackson** | Java DTO/converter and optional JSON Schema validator. | Unknown fields, missing fields, null/defaults, coercion, and mapper config decide. |
| **JSON Schema** | Independent schema describing types/required/additionalProperties. | Open/closed content model, `required`, `enum`, `oneOf` affect compatibility; not checked automatically by JMS. |
| **Apache Avro** | Writer schema + reader schema, via schema resolution. | When reader lacks a field from writer, an appropriate default is needed; extra writer fields can be ignored when unused by reader; aliases can help renames in certain cases. |
| **Protocol Buffers** | Message schema + field numbers/wire types. | Never reuse deleted field numbers; use `reserved`, account for unknown fields, enum evolution, and presence semantics. |

### 11.1. Avro: Defaults Belong to the Reader Schema

Example of an Avro v2 record adding an optional field:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.events",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "note", "type": ["null", "string"], "default": null}
  ]
}
~~~

When reading a message written with an older writer schema lacking `note`, the new Avro reader schema can apply the **new field's default**. An Avro default **does not mean the writer omits that field from binary encoding**; the default is applied when **decoding data missing the field during schema resolution**. For unions, pay attention to branch ordering, defaults, and Avro version.

**Do not assert** that an alias or type promotion guarantees all changes are valid; use the Avro/registry compatibility checker for your exact version and test with real data.

### 11.2. Protobuf: Field Numbers Matter More Than Field Names

Illustrative Protobuf schema:

~~~protobuf
syntax = "proto3";
package example.events;

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  optional string note = 3;
}
~~~

In Protobuf, **tag numbers** (1, 2, 3) are central to the wire format. When removing a field, consider marking used numbers/tags `reserved` to prevent reuse from misinterpreting old data. Changing types can make old data unreadable or alter its meaning. Default values, unknown fields, and presence semantics also differ from JSON/Jackson; never apply one rigid compatibility table to all formats.

### 11.3. Schema Registry Is Distinct from the Message Broker

When using Avro/Protobuf with a schema registry, a message may carry a `schemaId` or envelope so the reader can fetch the schema by ID and decode. That is an **application/ecosystem serializer convention**, not a built-in part of standard JMS headers. This mechanism works only when all parties agree on the format, schema registry, and access controls.

## 12. TRANSITIVE Modes and Multi-Version History

Suppose you have v1 → v2 → v3. If a registry checks **FULL without transitivity**, v3 may be compared against v2 without **requiring** direct compatibility with v1. If a Queue/DLQ still holds v1 messages, consumer v3 may encounter unreadable data.

| Mode | When Registering v3, Which Versions Is It Checked Against? |
| --- | --- |
| `BACKWARD` | v2: reader v3 must read writer v2. |
| `FORWARD` | v2: reader v2 must read writer v3. |
| `FULL` | v2: both directions v2 ↔ v3. |
| `BACKWARD_TRANSITIVE` | All registered versions in scope (v1, v2): reader v3 reads all older writers. |
| `FORWARD_TRANSITIVE` | Older versions (v1, v2): older readers read writer v3. |
| `FULL_TRANSITIVE` | Older versions (v1, v2): both directions for every new–old pair. |

These are **common Schema Registry mode names**, not JMS enums. Exact names and rules vary across registries and schema types. Confluent Schema Registry, for instance, distinguishes non-transitive modes from `*_TRANSITIVE`.

In JMS, retention/durable-subscription/DLQ decisions can create longer schema support windows than expected. If messages may be replayed after six months, you must keep a compatible reader or an upcast/migration mechanism for that historical data.

Some organizations choose not to maintain infinite backward compatibility, yet must establish an **explicit time-bounded policy**: retired versions, backlog purge/migration dates, replay permissions, deprecation notices, and rollback plans.

## 13. Asynchronous Rollout Strategies

### 13.1. With BACKWARD: Upgrade Readers First

If the **new reader reads the old writer**, the natural order is:

1. Deploy consumer v2 while the producer still sends v1.
2. Verify consumer v2 reads v1 without generating DLQ messages.
3. Once old consumer instances are retired or no longer consuming that queue/topic, let the producer emit v2.
4. Monitor decode errors, selectors, lag, and DLQ counts.

If producer v2 is enabled too early, still-running v1 consumers **are not guaranteed** to read v2 (since backward does not imply forward). On a Queue with competing consumers, an old instance can still pick up v2 and fail.

### 13.2. With FORWARD: New Writers Can Go First, With Conditions

If the **old reader reads the new writer**, producer v2 can emit messages while consumer v1 is still running. However, when upgrading consumers to v2 later, **forward compatibility does not guarantee reader v2 can read leftover v1 messages**. Before switching readers, ensure the v1 backlog is drained, or give reader v2 a dedicated compatibility/adapter path to read v1.

### 13.3. With FULL: Allows More Ordering Flexibility, Still Needs Guardrails

If both v1/v2 readers can read v1/v2 writers in a real environment, you can deploy more independently while the two versions coexist. Still, **structural FULL compatibility** alone does not prove business side effects, selectors, transactions, routing, or much older versions are safe.

A safe rollout can use **expand → migrate → contract**:

~~~mermaid
flowchart LR
    A["Expand: reader supports v1+v2"] --> B["Migrate: producer switches to v2 via feature flag"]
    B --> C["Observe: logs, DLQ, backlog, contract tests"]
    C --> D["Contract: retire v1 support when permitted"]
~~~

This sequence is especially useful for breaking schema changes. Avoid deploying new producers and consumers simultaneously and assuming there is no risk window.

### 13.4. Breaking Changes: Never Patch Silently

If v2 is truly incompatible with v1 (e.g., `amount` changes units or structure completely), options include:

- Emit a new event type like `OrderCreatedV2` or a separate destination with a clear contract, then migrate subscriptions cleanly.
- Dual-publish for a transition window **only if deduplication exists** and side effects are controlled.
- Use a reader adapter/upcaster converting v1 into an internal **canonical model**.
- Migrate/replay the backlog before removing the old reader.
- Coordinate with other consumer owners and publish deprecation deadlines.

Never reuse `schemaVersion=1` to carry an incompatible v2 payload; that makes retries, auditing, and replays nondeterministic.

## 14. Designing Multi-Version Readers and Unrecognized Version Handling

In real consumer code, separate the steps:

1. Read raw `jakarta.jms.Message` and verify allowed type (e.g. `TextMessage`).
2. Inspect `schemaName`, `schemaVersion`, `contentType`; **never trust headers blindly**.
3. Pick a **reader/decoder from a whitelist**; allow only supported versions.
4. Deserialize, validate structure and business semantics.
5. Normalize into the internal **domain model**.
6. Perform side effects only after data is valid; enforce ack/transactions, idempotency, and retry policies.

Example fragment:

~~~java
// Fragment: textMessage was obtained from a listener or JmsTemplate.receive.
// deserializeV1, deserializeV2, and toCanonical are application logic.
String name = textMessage.getStringProperty("schemaName");
if (!"orders.created".equals(name)
        || !textMessage.propertyExists("schemaVersion")) {
    throw new IllegalArgumentException("Unsupported event schema");
}
int version = textMessage.getIntProperty("schemaVersion");

OrderCanonical order = switch (version) {
    case 1 -> toCanonical(deserializeV1(textMessage.getText()));
    case 2 -> toCanonical(deserializeV2(textMessage.getText()));
    default -> throw new IllegalArgumentException(
            "Unsupported schema version " + version);
};
validateOrder(order);
~~~

This is a **pseudo-integrating fragment**: `OrderCanonical`, `deserializeV1`, `deserializeV2`, `toCanonical`, and `validateOrder` are application-defined; **not a standalone compilable file**. Its purpose is to clarify version dispatching.

Do not do this:

~~~java
// Anti-example: NEVER take an arbitrary class name from a producer-sent JMS property
// for reflection/class loading without a whitelist.
String arbitraryClass = message.getStringProperty("javaClassName");
// Class.forName(arbitraryClass) ... // avoid this design.
~~~

When an unknown schema arrives, **never silently coerce it to v1 and ack as processed**. Depending on policy, move the message to quarantine/DLQ, preserve the raw message with version/error metadata, alert contract owners, and allow controlled replay after adding a decoder.

## 15. Contract Testing: Not Just "Parsing Succeeded"

A solid CI suite must test **writer–reader pairs** as well as semantic validation:

| Test | Producer/Schema Generating Payload | Reader/Consumer | What Must Be Asserted |
| --- | --- | --- | --- |
| V1→V1 | v1 | v1 | Baseline with accurate body and business values. |
| V1→V2 | v1 | v2 | **Backward**; missing optional field/default is safe. |
| V2→V1 | v2 | v1 | **Forward**; extra field does not fail; old behavior holds. |
| V2→V2 | v2 | v2 | New baseline. |
| V1→V3 | v1 | v3 | Required if committing to backward transitivity/v1 replay. |
| V3→V1 | v3 | v1 | Required if committing to forward transitivity. |

### 15.1. Assertions to Include

- A JSON validator for the corresponding schema version accepts valid messages.
- Missing required fields cause the reader/business validator to reject.
- Unknown fields are handled per **policy**, without arbitrarily disabling all validation.
- Missing new fields receive proper defaults, distinguishing `null` when its meaning differs from omitting the field.
- Numeric type/precision/range: `BigDecimal` or integer minor units for currency; prevent silent precision loss.
- Old/new enums: an `UNKNOWN` strategy or explicit failure.
- JMS property `schemaVersion` has the right type and valid property name for selectors.
- Correlation ID/event ID remain invariant across retries of the same event.
- No unnecessary secrets or PII leak into headers/properties.
- No side effects commit when data is invalid.
- Replay from DLQ/backlog by newer readers works across the retention window.

**"Deserialization did not throw" is only one assertion**, insufficient to declare contract compatibility. For instance, if DTO v1 ignores `note`, yet v2 business rules use `note` to gate shipping eligibility, an old consumer might parse cleanly and **bypass a new rule**. That makes the schema full structurally yet unsafe semantically.

### 15.2. Golden Messages / Immutable Fixtures

Store sample **v1/v2/v3** payloads as test fixtures (never rewrite historical payloads when schemas change). Fixtures should cover:

- Minimal valid messages (required fields only).
- Messages with all optional fields populated.
- `null` vs. missing fields, empty strings, Unicode characters.
- Boundary values for numbers, timestamps, currencies, and enums.
- Messages with missing/duplicate fields, wrong types, unknown versions.
- Accompanying JMS metadata: `schemaName`, `schemaVersion`, `JMSType`/contentType.

Whenever schemas or converter code change, CI re-runs the entire **support matrix**. When using a registry, combine registry compatibility checks with **consumer-driven contract tests** and broker integration tests: the registry can pass while handler logic still fails.

## 16. When to Use an Upcaster, Schema Registry, or New Event Name?

| Scenario | Usually Suitable Solution | Reason |
| --- | --- | --- |
| Adding optional field, old readers ignore, new readers have default | **Full-compatible v2** | No need to migrate existing messages. |
| Multi-version JSON schemas, multiple independently deployed consumers | **Schema catalog/registry + contract CI** | Tracks versions and blocks breaking changes. |
| Need to read long-retained v1 messages into a new v3 domain model | **Upcaster / versioned decoder** | Normalizes old messages into a canonical model. |
| Fundamental change in business semantics | **New event type/destination** | Avoids pretending old data is new data. |
| Consumers cannot upgrade simultaneously | **Expand/migrate/contract, feature flag, dual reader** | Reduces rolling deploy risk. |
| Data carries embedded schema ID in Avro/Protobuf bytes | **Serializer/registry integration** | Reader identifies the exact writer schema. |

An **Upcaster** is a function transforming old data representations into a newer/canonical form, for example:

~~~java
// Fragment illustrating a pure Java adapter:
public record CanonicalOrder(
        String orderId,
        java.math.BigDecimal amount,
        String note) {}

public static CanonicalOrder fromV1(OrderV1 old) {
    return new CanonicalOrder(old.orderId(), old.amount(), null);
}

public static CanonicalOrder fromV2(OrderV2 current) {
    return new CanonicalOrder(
            current.orderId(), current.amount(), current.note());
}
~~~

`OrderV1`/`OrderV2` are the records from the demo; this snippet belongs inside an appropriate class, not a standalone file. If business rules shift `amount` from major to minor units, the **upcast must perform an explicit conversion with overflow/rounding checks**, not merely map fields by name.

## 17. Polyglot Messaging and Reducing Java Class Coupling

When a Spring Boot producer writes messages for Node.js, Go, or .NET consumers, **Java ObjectMessage** is generally unsuitable: it depends on Java serialization, classes, and `serialVersionUID`, plus untrusted object deserialization risks.

A polyglot contract typically uses:

- **JSON TextMessage** + JSON Schema + schema name/version, or
- **Avro/Protobuf BytesMessage** + schema ID/format and an agreed resolver.

For each type, agree on:

1. Encoding (UTF-8, JSON, binary).
2. Numeric types: money in `long` minor units/decimal strings or explicit schema decimals; avoid rounding floats.
3. Timestamps: UTC epoch millis or ISO 8601 with timezone; never switch implicitly.
4. Null/missing/empty and defaults.
5. Enums, ID formats, Unicode normalization if relevant.
6. Required vs. optional fields, unknown field strategy.
7. Max message size and payload security.
8. Schema registry access/version retention, when using a registry.

Keep **schema contracts** independent of Java classes named `com.example...`. Renaming an internal class should never force external consumers to update their schemas just because a Java package changed.

## 18. Conversion Error Handling and Safe DLQs

With Spring JMS listeners, parse errors can occur before the business method runs if the container converts the payload to a DTO automatically. Configure listener conversion/error handling, transactions, and broker redelivery properly.

Errors like payloads **permanently violating the schema** will not heal by retrying 100 times on identical data. Classify them:

| Error | Retry As-Is? | Suggested Handling |
| --- | --- | --- |
| Transient registry/network outage | Bounded retry allowed. | Backoff, metrics, timeout, alerting. |
| Unsupported version | Usually **do not** retry infinitely. | Quarantine/DLQ, upgrade reader or migrate. |
| Invalid JSON/malformed structure | No, unless data source is fixed or decoder changes. | DLQ, safely log ID/schema/error metadata. |
| Business invariant violation | Usually do not retry identical data. | Business error handling workflow. |
| Transient downstream DB/service error | Retryable. | Transactions, idempotency, backoff. |
| Message missing schema metadata | Depends on legacy policy. | Explicitly specified v1 adapter or quarantine. |

Never catch `JsonProcessingException` and **ack as success, dropping the message** just to keep throughput metrics green. Conversely, never roll back a poison message forever and stall the Queue. Bounded redelivery limits + DLQ + replay capability after fixing decoders keep the lifecycle under control.

**Security:** producer-supplied headers like `schemaName`/`schemaVersion` are **not authoritative trust anchors**. Consumers must enforce broker access controls, restrict decoder versions, and validate content; never use property values to reflectively load arbitrary classes. Manage schema registry credentials and sensitive payloads under organizational security policy.

## 19. Symptom-Based Troubleshooting

| Symptom | Typical Cause | Investigation Steps |
| --- | --- | --- |
| Old consumer fails when producer adds a field | Reader v1 rejects unknown JSON properties. | Check `FAIL_ON_UNKNOWN_PROPERTIES`, v1 validator, deploy readers first. |
| New consumer fails on old messages | New field treated as required without default. | Review v2 schema, null/missing semantics, v1 adapter. |
| JSON parses fine but monetary amounts are wrong | Unit/scale of field changed while keeping the same name. | Audit business contract; introduce new field or incompatible version. |
| Selector `schemaVersion = 2` does not match | Producer sent property as String instead of int, or wrong name. | Inspect raw JMS properties and selector expression. |
| Listener deserialization fails yet raw Message has valid body | Incompatible converter type-id, JSON schema/DTO. | Inspect raw `TextMessage`, select right decoder by version. |
| V1 messages remain in DLQ after removing reader v1 | Retention/replay outlived support window. | Keep upcaster, migrate backlog, or enforce clear purge policy. |
| Registry passes compatibility yet consumer fails | Semantic incompatibility or checker only compared immediate predecessor. | Test golden messages; evaluate transitive compatibility. |
| Rollout works in staging yet fails in production | Lingering old reader instances, different backlog, or older schemas. | Inventory consumers/versions, Queue depth, and retention. |
| Replacing `ObjectMessage` with JSON causes errors | Producers/consumers using mixed formats on one destination. | Align contentType/schemaName/version and transition plan. |
| Message redelivers repeatedly with the same ID | Poison message/unsupported schema, transaction rollback. | DLQ + alert instead of infinite retry; check eventId and delivery count. |

## 20. Knowledge Check Exercises

1. **What is reader v2 reading writer v1 called?** Backward compatibility.
2. **What is reader v1 reading writer v2 called?** Forward compatibility.
3. **What is both directions succeeding called?** Full/bidirectional compatibility **within the tested version scope**.
4. **Does FULL v3↔v2 alone guarantee v3↔v1?** No; transitivity or direct testing is required.
5. **V1 has `{"orderId":"O1"}`, v2 adds a required `note` field. What happens when v2 reads v1?** It can fail due to missing required field; requires a default/migration or contract change.
6. **V1 reader has `FAIL_ON_UNKNOWN_PROPERTIES=true`, v2 adds `note`. Can the old reader read v2?** Usually no, due to the unknown field; forward compatibility fails.
7. **JSON Schema v1 sets `additionalProperties: false`, v2 adds a new field. Is changing Jackson config alone enough to prove full compatibility?** No; a strict schema validator may reject it.
8. **Should `amount` change from VND to thousands of VND while keeping `schemaVersion=1`?** No; that is a semantic breaking change.
9. **Is `JMSSchemaVersion` a standard header?** No; a custom `schemaVersion` JMS property is an application convention.
10. **Can `JMSMessageID` replace a schema ID or eventId?** No; each ID serves a different purpose.
11. **Why do new consumers need to read old messages even after old producers are shut down?** Queue backlogs, redeliveries, durable subscriptions, and DLQ replays.
12. **When should an upcaster be used?** When historical messages must be transformed into a canonical domain model that newer readers cannot process directly.
13. **What does the demo code in Section 10 prove?** Reader v1 parses writer v2 when ignoring `note` and reader v2 parses writer v1 with `note=null`; it does not prove all schemas/validators are compatible.
14. **When producer v2 changes the schema while consumer v1 is still running, is backward compatibility alone safe?** No, because backward only guarantees reader v2 reads writer v1; upgrade readers first.
15. **Is passing a schema registry check enough to skip broker integration tests?** No; conversion, headers, selectors, transactions, business validation, and routing still need verification.

## 21. References

- [Confluent Schema Registry — Schema evolution and compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): defines backward/forward/full/transitive and notes adjacent vs. full-history checks. Example of **one registry**, not a JMS default.
- [Apache Avro — Specification, Schema Resolution](https://avro.apache.org/docs/current/specification/): writer/reader schemas, defaults, field aliases, and schema resolution.
- [JSON Schema — Understanding JSON Schema](https://json-schema.org/understanding-json-schema/): `required`, `additionalProperties`, nullability, validation.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field numbers, unknown fields, reserved field tags, and evolution.
- [Spring Framework — JMS using/message conversion](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `MessageConverter`, and listener integration.
- [Spring Framework 6.2 — SimpleMessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): convertible message types.
- [Spring Framework 6.2 — MappingJackson2MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON serialization/conversion in Spring JMS.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): auto-configuration, embedded broker, and `JmsTemplate`.
- [Jackson Databind — Deserialization features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features): `FAIL_ON_UNKNOWN_PROPERTIES` and unknown field handling.

**Summary:** Schema v2 is **backward** compatible when reader v2 reads writer v1; **forward** compatible when reader v1 reads writer v2; **full** when both directions hold. In Spring JMS, compatibility depends on the **contract, serializer/converter, JMS metadata, validation, and business code**, and does not arise automatically from `schemaVersion` alone. When evolving schemas, test the producer/consumer matrix, plan rollouts, and account for old messages still sitting in Queues/DLQs.
