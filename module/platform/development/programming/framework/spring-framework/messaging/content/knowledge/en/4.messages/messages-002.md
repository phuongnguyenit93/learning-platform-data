# Message Contracts and Payload Data Types

## 1. Message Is an Envelope

In Spring Messaging, `Message<T>` represents a message consisting of two parts: **payload** and **headers**. The payload is the main content that the consumer needs to process; headers are accompanying metadata used for identification, correlation, routing, or describing how to interpret the content.

- `Message<T>`: the message abstraction; `T` is the payload type at the Java level.
- `MessageHeaders`: a named collection of metadata accessed by key; header values have the general type `Object`.
- `MessageBuilder`: a way to create a new message or create a message based on an existing message.

For example, an `OrderPlaced` event can carry a payload containing the order ID, customer, total amount, and creation timestamp. Headers can carry `eventId`, `correlationId`, and `schemaVersion`. This allows the consumer to process the business data while still tracking the message within a larger processing flow.

Message is an application-layer abstraction. A `Message` created successfully in memory does not prove that it has been sent to a broker, durably stored, or processed by a consumer. Delivery guarantees depend on the channel, adapter, broker, and configuration.

## 2. Structure and Role of the Payload

The payload is the primary data of the message. `Message<T>` helps Java code express the expected data type, such as `Message<OrderPlaced>` or `Message<String>`. This type helps both the compiler and readers understand the contract between producer and handler.

Common payload forms:

| Payload type | When appropriate | Notes |
| --- | --- | --- |
| DTO or Java `record` | Structured events/commands with a clear contract | Should have specific fields, stable names, and versioning rules |
| `String` | Simple text, short commands, or text content | Specify encoding and the meaning of the string |
| `byte[]` or `ByteBuffer` | Binary data, files, or encoded payloads | Need to define format, maximum size, and memory management |
| Numeric, boolean, or single value types | Small messages with a single meaning | Avoid overly vague types if the contract may need to expand later |
| Collection or map structures | Lists or flexible data with a clear schema | Check elements, runtime types, and compatibility when changing |

For business messages exchanged across multiple components, a DTO or record is usually easier to manage than sending an ORM entity directly. Entities can contain lazy proxies, circular relationships, persistence state, or internal database details. Those details make serialization unpredictable and couple producer/consumer to the storage model.

Do not use `Object` as a generic payload type for all messages if the consumer needs to know the actual structure. `Object` weakens the contract and forces the consumer to cast or infer types at runtime. Similarly, `Map<String, Object>` is flexible but requires a clear schema, field naming rules, and validation if used across service boundaries.

### 2.1. Generic types and runtime types

`Message<OrderPlaced>` helps the compiler check most operations in Java source code, but generic types undergo type erasure at runtime. When a message is received from a broker or deserialized from JSON, the generic declaration at the producer does not by itself guarantee the payload has returned as the exact type.

The consumer must know the target type and use an appropriate converter/serializer. After conversion, the actual data still needs to be validated: required fields, value ranges, schema version, and business invariants. Do not cast a payload of unknown origin based solely on a header sent by the producer.

## 3. Role of Headers

Headers are metadata attached to the envelope. They should describe the message or the transport process rather than becoming a place to store all business data.

Commonly useful headers:

| Header | Purpose | Usage rules |
| --- | --- | --- |
| Business `eventId` or `messageId` | Stable identifier of the event/message | Keep unchanged on retries or replays of the same event for consumer deduplication |
| `correlationId` | Link messages/requests belonging to the same business flow | Propagate across downstream steps; do not use as a deduplication key if one flow has multiple messages |
| `causationId` | Indicate which message/event caused this message to be created | Useful when building causal relationships in tracing/auditing |
| `schemaVersion` | Version of the payload contract | Must have compatibility and consumer upgrade policies |
| `contentType` | Describe the content format such as JSON or text | Must reflect the actual representation and be understood by the converter |
| Routing headers | Select destination, channel, or handler type by configuration | Control allowed values; do not treat external headers as trusted commands |

`MessageHeaders` also has framework-managed headers such as ID and timestamp. They are useful for identifying the message object and creation time according to the framework mechanism. Do not assume the framework-generated ID is a stable business ID across retries, serialization, or republishing. If deduplication is needed, generate an `eventId`/idempotency key with a clearly defined lifecycle.

Header values have the general type `Object`, but that does not mean every Java type can be transferred across every transport. An adapter/broker may only support a specific set of header types, convert them to protocol metadata, or drop unsupported headers. Prefer simple, serializable values and agree on types between producer/consumer.

Do not put passwords, access tokens, unnecessary personal data, or large payloads in headers. Metadata frequently appears in logs, tracing, broker management UIs, and operational tools. Only pass the minimum required information and apply appropriate protection policies.

## 4. Creating Messages with MessageBuilder

`MessageBuilder` helps create a message with a payload and add metadata before building. After building, the message and `MessageHeaders` are designed to be immutable: do not modify the headers map of an already created message directly. If you need to change metadata, create a new message from the old message using a builder.

Example of creating a message:

~~~java
Message<OrderPlaced> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", "evt-1001")
        .setHeader("correlationId", "corr-77")
        .setHeader("schemaVersion", 1)
        .build();
~~~

To create a message based on an existing message, you can use `MessageBuilder.fromMessage(existing)` and then replace or add headers before calling `build()`. Only copy the metadata that needs to be retained; when creating a new business event, consider generating a new ID rather than accidentally reusing the ID of the old message.

An immutable message envelope does not mean the payload is always immutable. If the payload is a mutable object, other code can still change the fields of that object after the message is built. Prefer records, immutable DTOs, unmodifiable collections, or copying data at send/receive boundaries when a consistent snapshot must be guaranteed.

## 5. Payload Contracts Should Be Designed Like APIs

The payload is the contract between producer and consumer. When both sides are deployed independently, changing a field can break old consumers just like changing a REST API.

A good contract should define:

1. **Names and meanings:** what each field describes, what units are used, and whether null is distinguished from an absent field.
2. **Data types:** string, integer, decimal, boolean, timestamp, enum, object, or list; specify formats and limits.
3. **Required/optional:** which fields are always present, which may be missing, and what the default values are.
4. **Identifiers:** event ID, aggregate ID, correlation/causation ID, and uniqueness rules.
5. **Time:** timezone, format, precision, and the meaning of occurrence time versus send time.
6. **Versioning:** how consumers recognize the schema and how producer/consumer rollouts work.
7. **Validation:** value ranges, business invariants, size limits, and how to respond when data is invalid.
8. **Security:** which fields are sensitive, who is allowed to read them, and whether encryption or log masking is required.

Name events after what happened, such as `OrderPlaced`, and describe the data needed for the consumer to understand the event independently. Do not force the consumer to directly access the producer's internal objects or database to interpret the payload.

### 5.1. Compatible schema changes

Changes that are generally easier to keep compatible:

- Adding an optional field that old consumers can ignore.
- Consumers ignoring unknown fields and using explicit defaults for missing new fields.
- Adding an enum value only when consumers have a strategy for handling unknown values.

Changes that typically break compatibility:

- Renaming or removing a field currently used by consumers.
- Changing the data type or meaning/unit of a field while keeping the old name.
- Turning an optional field into a required one before old producers are updated to send it.
- Changing the representation of timestamps, decimals, or enums without conversion rules.

For incompatible changes, release a new schema/version or have a transition period: consumers support both versions, producers roll out later, monitor the proportion of old messages, and only then drop support. Do not just change `schemaVersion` in the header without changing or checking the actual content.

## 6. Type Conversion and Serialization

Three steps should be distinguished:

- **Creating the payload in the application:** the producer creates a Java object or raw data.
- **Message conversion:** converting the payload to the type required by the target handler or creating a message from other data.
- **Transport serialization:** turning data into a byte representation to send over the network/store in a broker; the receiving side deserializes it back.

Spring Messaging provides the `MessageConverter` abstraction for converting message payloads. A converter can use metadata such as `contentType` to choose how to interpret the data. JSON converters typically require the corresponding JSON library; the specific converter choice and configuration depend on the Spring version and adapter.

`contentType` should reflect the actual representation. For example, if the payload has already been serialized to JSON bytes, `application/json` is appropriate metadata. If the payload is still a Java object in memory, attaching `application/json` does not automatically serialize the object to JSON. Do not confuse declaring a content type with performing a conversion.

Serialization is a boundary that needs clear design:

- JSON is easy to inspect and widely compatible, but requires conventions for numbers, timestamps, enums, nulls, and unknown fields.
- Avro/Protocol Buffers or schema-based formats can provide better schemas and compatibility controls, but require managing a registry/tooling and versions.
- Java native serialization often tightly couples both sides to classes/versions and carries security risks; it should not be used as the default contract between services that do not share a lifecycle.
- For binary payloads, document encoding, compression, checksums if needed, and size limits.

Do not send a raw Java object through a broker assuming consumers in other languages will understand it. Agree on the wire format, schema, and version handling before integrating.

## 7. Validation at Producer and Consumer

Validation needs to happen on both sides because producers can have bugs, and messages can be old, resent, or originate from another system.

**Before publishing:** check required fields, value ranges, authorization to emit the event, and invariants verifiable within the current transaction. Do not emit an `OrderPlaced` event if the order has not yet been committed in a valid state according to business rules.

**Upon receiving:** check that the payload converted to the right type, the schema version is supported, IDs are valid, required fields are present, and the message is allowed to be processed in the current state. Do not blindly trust routing headers or tenant IDs sent externally; authenticate and validate at the system's security boundary.

Data validation and business validation are two different things. An `amount` may be a valid number yet not allowed to be negative by business rules; an `orderId` may match the format yet not exist or not belong to the current tenant.

When a message is invalid, classify the error:

- Transient errors such as unavailable database/network: retry with limits and backoff.
- Schema errors or invalid data: quarantine/DLQ for inspection, do not retry indefinitely.
- Permanent business rule violations: record the rejection outcome according to the contract, avoid letting the message loop.
- Unexpected programming errors: log sufficient safe context, raise alerts, and apply retry/DLQ policies.

## 8. Payload and Headers in Multi-Component Systems

### 8.1. Putting data in the right place

The payload should contain the business data needed to process the message. Headers should contain coordination and observability metadata. For example, `orderId`, `items`, and `totalAmount` are event data; `eventId`, `correlationId`, `schemaVersion`, and `contentType` are metadata.

Do not put `totalAmount` only in a header because it is business data. Nor is it necessary to duplicate the entire payload in headers. If a value is needed both for business logic and for routing, clearly define the canonical source of truth and how payload/header stay synchronized to avoid divergence.

### 8.2. Correlation and tracing

`correlationId` helps link multiple messages of a business flow; `causationId` helps identify the message that directly caused the current message. Trace ID/span ID serve distributed tracing and have their own lifecycle. They may relate to correlation ID, but should not be conflated into a single concept.

When a consumer creates a new message, decide which metadata to propagate and which to generate anew. For example, correlation ID can be preserved throughout a workflow; event ID must be new for a new event; causation ID can reference the event just processed. Do not blindly copy all headers because that may carry reply channel, error channel, routing, or internal data inappropriate for the new destination.

### 8.3. Payload size

Large payloads increase serialization time, network transfer, storage, memory pressure, and retry costs. If a message contains a large file or blob, consider storing the content in object storage and sending a controlled reference such as object key, checksum, media type, and size. The reference must have appropriate access permissions, expiration, and cleanup rules; do not use unrestricted public URLs for private data.

Set size limits on both producer and broker/consumer. Avoid sending entire large object graphs merely for convenience. Keep only the fields needed for the consumer to complete its task.

## 9. Java 17 + Spring Messaging 6.2 Example

The following example creates a message with an `OrderPlaced` payload and some metadata. This is an in-memory message object to illustrate the contract; the example does not connect to a broker, does not serialize JSON, and does not demonstrate delivery guarantees.

Create a Maven project with the structure:

~~~text
message-contract-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageContractDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/MessageContractDemo.java`:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageContractDemo {
    private MessageContractDemo() {
    }

    public record OrderPlaced(
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            Instant occurredAt) {
    }

    public static void main(String[] args) {
        OrderPlaced event = new OrderPlaced(
                "ORD-1001",
                "CUS-42",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z"));

        Message<OrderPlaced> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", "evt-1001")
                .setHeader("correlationId", "corr-77")
                .setHeader("schemaVersion", 1)
                .build();

        OrderPlaced payload = message.getPayload();
        MessageHeaders headers = message.getHeaders();

        System.out.println("orderId=" + payload.orderId());
        System.out.println("totalAmount=" + payload.totalAmount().toPlainString());
        System.out.println("eventId=" + headers.get("eventId"));
        System.out.println("schemaVersion=" + headers.get("schemaVersion"));
        System.out.println("correlationId=" + headers.get("correlationId"));
    }
}
~~~

Compile and run from the directory containing `pom.xml` using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageContractDemo
~~~

Stdout:

~~~text
orderId=ORD-1001
totalAmount=125.50
eventId=evt-1001
schemaVersion=1
correlationId=corr-77
~~~

Points to observe:

- `Message<OrderPlaced>` expresses the expected payload type in source code.
- The `OrderPlaced` record groups business data into a structured contract.
- `eventId` and `correlationId` are in headers because they serve identification and flow tracking.
- `schemaVersion` helps the consumer know which contract version to interpret.
- `MessageHeaders` is read as metadata; there is no need to—and you should not—modify the headers map directly after building.

In real integrations, the adapter/converter determines how this object is turned into JSON, a byte array, or another wire format. The consumer must deserialize and validate before applying business logic.

## 10. Common Mistakes

- **Putting all data into headers:** headers are metadata, not a replacement for a schema-backed payload.
- **Using `Object` or uncontracted maps:** consumers must guess types and fields, easily causing runtime errors.
- **Assuming generic types protect data on receipt:** type erasure and deserialization can produce payloads of a different type than expected; runtime checking is required.
- **Using the framework message ID as an idempotency key:** the message object's ID can change when creating a new message; use a stable business ID.
- **Changing fields or data types without versioning:** old consumers may fail or misinterpret data.
- **Setting `contentType=application/json` when the payload is not serialized:** metadata does not automatically convert a Java object to JSON.
- **Sending JPA entities or large object graphs:** serialization can pull in lazy loading, circular references, and persistence coupling.
- **Trusting external headers:** headers can be spoofed or not preserved by adapters; validate data at the consumer.
- **Keeping a mutable payload and modifying it after publishing:** other handlers may observe unexpected state changes.
- **Copying all headers to a new message:** may carry over inappropriate IDs, reply/error channels, or routing metadata.
- **Not setting size limits:** large messages put pressure on memory, network, broker, and retry duration.

## 11. Message Contract Review Checklist

1. Does the payload have a specific type, clear field names, and clear meanings?
2. Can the consumer understand the payload without accessing the producer's internals?
3. Are required fields, nullability, units, timestamps, and enums defined?
4. Is the `eventId`/idempotency key stable across retries and replays?
5. Are `correlationId` and `causationId` propagated according to the proper lifecycle?
6. Does `schemaVersion` have compatibility and rollout rules?
7. Does `contentType` match the actual representation?
8. Are converter/serializer configurations consistent across producer and consumer?
9. Does the consumer validate schema, access permissions, and business invariants?
10. Does the payload/header contain secrets, sensitive data, or overly large content?
11. Do the adapter/broker support the chosen header and payload types?
12. Should a new message keep metadata from the old message or generate a new ID/causation?

## 12. Key Takeaways

Spring `Message<T>` is an envelope consisting of payload and headers. The payload carries business data with its type expressed in Java code; headers carry metadata for identification, correlation, routing, and content description. `MessageBuilder` creates new messages, while `MessageHeaders` is designed to be immutable; however, a mutable payload can still be altered if the object is shared. Generic types do not replace deserialization and validation at the consumer. When a message passes through a broker, you need to agree on wire format, content type, schema version, size limits, and compatibility. Design payloads like an API with a lifecycle, use stable business IDs for deduplication, and put only necessary metadata in headers.