# Envelope with Version, Identifier, Timestamp, and Data

> Scope: designing message contracts for Spring Framework Messaging applications. This lesson focuses on a stably structured envelope that carries information to identify and interpret a message, while containing a strongly typed business payload.

## 1. What Problem Does an Envelope Solve?

A message often passes through multiple components: producer, channel, adapter, broker or RSocket, and then consumer. Intermediary components may route, store, retry, log, or forward the message without needing to understand all of its business data.

If every producer chooses a different structure, consumers have to guess which field is the version, which identifier is used for deduplication, which timestamp represents when the event occurred, and which part is the payload. A unified envelope puts this shared information into a single structure:

- **Contract version** tells consumers which rules to use when interpreting the structure.
- **Message identifier** identifies a logical message for tracing, deduplication, and retry handling.
- **Timestamp** indicates when the occurrence happened.
- **Data (`data`)** holds the specific business content.

Example of an `OrderCreated` message:

~~~json
{
  "schemaVersion": 1,
  "messageId": "7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001",
  "occurredAt": "2026-11-07T14:00:00Z",
  "data": {
    "orderId": "ORD-1001",
    "total": 125000.00
  }
}
~~~

A consumer can check the version, identify the message, read the occurrence time, and then decode `data` into the `OrderCreated` type. The envelope does not need to know every property of each payload type; it only defines the shared contract portion.

## 2. Distinguishing Spring Message from a Business Envelope

In Spring Messaging, `Message<T>` is an abstraction with two parts:

- `payload`: the data object processed by handlers.
- `headers`: key-value metadata, such as ID, timestamp, content type, correlation, or transport information.

A Spring Message can be constructed with `MessageBuilder`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", new BigDecimal("125000.00")))
    .setHeader("eventType", "com.example.order.created")
    .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
    .build();
~~~

`MessageHeaders` is immutable after the message is created. Spring automatically generates `id` and `timestamp` headers for each message instance by default; this is metadata of the Spring Message object. When creating a new message during processing, the new instance's ID and timestamp may differ.

A business envelope serves a different purpose. `schemaVersion`, `messageId`, and `occurredAt` live inside the payload so they can be serialized, persisted, or transmitted to other systems. You should not use Spring's `MessageHeaders.ID` as a stable business identifier, or `MessageHeaders.TIMESTAMP` in place of when the event actually occurred.

| Information | Spring Message header | Business envelope |
|---|---|---|
| ID | ID of a Spring Message instance | Stable ID of the logical message across transmissions and retries |
| Timestamp | Creation time of the Spring Message instance | Time when the occurrence/event happened |
| Content type | Hint on how to interpret the payload on the transport | Can be described in the serialization contract if consumers need it |
| Correlation | Metadata supporting workflow correlation | Can be included in the envelope if it must survive across multiple transports |
| Data | Payload of the Spring Message | `data` field inside the envelope |

A header may be filtered, renamed, or not forwarded by an adapter or protocol binding. If a consumer in another process requires a value to interpret business logic, place that value in the serialized contract. If a value is only for routing or internal handling within a single hop, a header is usually more appropriate. Avoid storing the same value in both headers and the envelope without specifying which one is the authoritative source.

## 3. Designing the Four Core Fields

### 3.1. Version: `schemaVersion`

The version tells consumers which set of rules applies when interpreting the envelope structure or payload schema. Choose a descriptive name like `schemaVersion` rather than `version` if the system has multiple kinds of versions.

A simple convention is to use a positive integer:

- `1`: initial contract.
- `2`: new structural version for incompatible changes.
- Missing values, `0`, or values less than `0` must be rejected if the contract requires this field.

Three concepts must be distinguished:

1. **Envelope/schema version**: version of the message structure.
2. **Event type/version**: the event type and semantic version of that event type, e.g., `order.created.v2`.
3. **Aggregate/entity version**: state version of an order or business object, often used for optimistic locking and detecting stale updates.

These three values serve different purposes. Do not use `schemaVersion` in place of an order's sequence number, and do not increment the schema version merely because an order changed state.

When the schema changes, agree on a compatibility policy. Adding optional fields with default values is generally lower risk than changing types or changing the meaning of existing fields. However, consumers can ignore unknown fields only if the JSON decoder or schema validator is configured to allow it. For breaking changes, create a new schema version, deploy consumers supporting the new version first, and only then switch producers; during the transition period you may need to support reading both versions.

Never reuse an existing field name with a new meaning. For example, if `total` used to mean the pre-tax total, do not change it to the post-tax total while keeping the same schema version.

### 3.2. Identifier: `messageId`

`messageId` identifies a logical message. The producer should generate the ID when forming the message and preserve that same ID across retries or redeliveries of the same message.

UUID is a common choice:

~~~java
UUID messageId = UUID.randomUUID();
~~~

Important rules:

- Each new logical message receives a new ID.
- When resending the same message due to a timeout, lost ACK, or network error, keep the same ID.
- Do not regenerate the ID on every retry; doing so prevents consumers from recognizing redeliveries as the same message.
- The ID must be unique within the scope of the producer or source. If multiple producers share an ID space, ensure collision freedom or include a source identifier.
- The ID is not a secret, authentication token, or authorization key.

Consumers can use `messageId` as an idempotency key. Before applying side effects, the consumer checks whether the message has already been processed. Recording the ID and updating business data should happen within the same transaction or an appropriate atomic storage mechanism; recording the ID separately still leaves room for inconsistent state if a failure occurs between the two operations.

Deduplication does not by itself create a system-wide exactly-once guarantee. It only helps consumers safely detect and handle duplicate deliveries within the scope of storage and transactions controlled by the application.

### 3.3. Timestamp: `occurredAt`

`occurredAt` is the time when the event occurred in the business domain. For example, when an order was confirmed, or when a sensor recorded a temperature exceeding a threshold.

In Java, use `java.time.Instant` to represent a point on the UTC timeline:

~~~java
Instant occurredAt = Instant.now();
~~~

When serialized to JSON, use an ISO 8601/RFC 3339 representation with an explicit timezone, typically the `Z` suffix for UTC:

~~~text
2026-11-07T14:00:00Z
~~~

Do not conflate different kinds of timestamps:

- `occurredAt`: when the occurrence happened at the source.
- `publishedAt`: when the producer emitted the message to the transport, if publishing latency needs to be measured.
- `receivedAt`: when the consumer received the message.
- `processedAt`: when the consumer finished processing.

Do not write the consumer's receipt time into `occurredAt`, because when a message is delayed or replayed, that time no longer reflects the original occurrence. If latency measurement is needed, keep separate timestamp fields.

Machine clocks can skew relative to one another. Timestamps are useful for observability, time-range queries, and estimating latency, but should not be the sole mechanism for establishing absolute ordering of distributed events. If ordering within an aggregate is needed, use a sequence or aggregate version; if ordering within a broker is needed, use offsets or ordering mechanisms provided by the transport.

### 3.4. Data: `data`

`data` is the strongly typed business payload. For an order-created event, the payload may be `OrderCreated`; for a payment request, the payload may be `PaymentRequested`.

Use dedicated DTOs or records for contracts sent over the wire. Avoid sending JPA entities or internal objects directly because they can contain lazy relationships, proxies, sensitive fields, or structures tied to the persistence layer.

A good payload has these characteristics:

- Contains the data consumers need to understand and process the message.
- Has clear field names, data types, and units of measurement.
- Does not depend on the producer's internal implementation classes or packages.
- Does not contain passwords, access tokens, secrets, or unnecessary personal data.
- Has size bounds and is validated before processing.
- Explicitly specifies which fields are required, which may be omitted, and what `null` means.

If the payload evolves independently of the envelope, you can manage the payload schema separately or use `dataSchema`/a schema registry. This avoids changing the envelope structure just because a business field is added.

## 4. Defining the Envelope with a Java Record

Java 17 records are well suited for modeling an immutable data contract:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Envelope<T>(
    int schemaVersion,
    UUID messageId,
    Instant occurredAt,
    T data
) {
    public Envelope {
        if (schemaVersion < 1) {
            throw new IllegalArgumentException("schemaVersion must be positive");
        }
        Objects.requireNonNull(messageId, "messageId must not be null");
        Objects.requireNonNull(occurredAt, "occurredAt must not be null");
        Objects.requireNonNull(data, "data must not be null");
    }
}
~~~

The generic type `T` lets you reuse the envelope with many different payloads while preserving compile-time typing. The compact constructor enforces invariants upon object creation. These checks do not replace validating incoming JSON: data received from the network must be deserialized into a valid object before calling the business handler.

Payload example:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    BigDecimal total
) {
    public OrderCreated {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (total == null || total.signum() < 0) {
            throw new IllegalArgumentException("total must be non-negative");
        }
    }
}
~~~

When creating a message in the producer, generate the ID and timestamp once at the message creation boundary:

~~~java
Envelope<OrderCreated> envelope = new Envelope<>(
    1,
    UUID.randomUUID(),
    Instant.now(),
    new OrderCreated("ORD-1001", new BigDecimal("125000.00"))
);
~~~

If sending needs to be retried, keep the same envelope object or at least preserve its ID and timestamp fields. Do not invoke a factory again to create a new envelope for the same logical message.

## 5. Integrating the Envelope into Spring Messaging

You can place the envelope as the payload of a Spring Message and use headers for routing or transport metadata:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<Envelope<OrderCreated>> message = MessageBuilder
    .withPayload(envelope)
    .setHeader("eventType", "com.example.order.created")
    .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
    .build();
~~~

In this example:

- `envelope.messageId()` is the stable ID of the business message.
- `message.getHeaders().get(MessageHeaders.ID)` is the ID of the Spring Message instance.
- `envelope.occurredAt()` is when the event occurred.
- `message.getHeaders().get(MessageHeaders.TIMESTAMP)` is the timestamp attached by Spring to the message instance.
- `eventType` is a custom header for routing or classification at the messaging layer.
- `CONTENT_TYPE` describes the payload type for the appropriate processing layer.

When using an RSocket requester, you can send the envelope as the payload:

~~~java
Mono<Void> sendOrderCreated(
    RSocketRequester requester,
    Envelope<OrderCreated> envelope
) {
    return requester
        .route("events.order-created")
        .data(envelope)
        .send();
}
~~~

The RSocket route identifies the target handler; the envelope carries the data contract. The encoder/decoder configured for RSocket determines how the object is converted into bytes and reconstructed on the receiving side. Putting an object in `Message` or calling `data(envelope)` does not automatically guarantee that every internal Spring header will be serialized into the body. Clearly define what goes in the body and what is mapped to transport metadata.

## 6. Validating Messages Before Processing

Consumers should validate the envelope at the system boundary before applying side effects:

1. Check whether the JSON or payload can be deserialized.
2. Check whether `schemaVersion` is supported by the consumer.
3. Check whether `messageId`, `occurredAt`, and `data` are present and of the expected types.
4. Check business invariants of the payload: valid IDs, non-negative amounts, supported units of measurement.
5. Check message size and resource limits.
6. Authenticate the sender using transport or application security mechanisms; do not trust `source` or `messageId` merely because they appear in JSON.
7. Check idempotency before applying side effects.

Do not take an unsupported schema version and try to interpret it as the nearest known version. If a message cannot be processed safely, return a categorized error, route the message to a dead-letter queue or quarantine process per system policy, and retain enough information for investigation.

## 7. Correlation ID, Causation ID, and Trace ID

The four-field envelope is a compact foundation. Larger systems often need additional metadata to link multiple messages:

- **correlationId** links a group of messages belonging to the same workflow or originating request.
- **causationId** indicates which preceding message directly caused the current message to be created.
- **traceId** links logs, spans, and distributed traces of an execution.

These IDs do not replace `messageId`. A workflow may emit multiple different messages: each message has its own `messageId` but shares the same `correlationId`. A message created in response to another message can record `causationId` as the ID of the source message.

If these values only need to live for a single hop, Spring headers or tracing context may suffice. If they must survive across brokers, outboxes, storage, or replay, place them in a durable contract or a standardized metadata format.

## 8. Evolving Schemas Without Breaking Consumers

Message contracts typically outlive a single deployment. Producers and consumers may be upgraded at different times, so compatibility must be designed in.

A practical strategy:

- Prefer adding optional fields without changing the meaning of existing fields.
- Choose clear defaults for new fields when consumers read older messages.
- Require consumers to ignore unknown fields only when the decoder/schema validator actually supports that behavior.
- Do not change data types from number to string or vice versa within the same version.
- Do not change units of measurement while keeping the same field name; if a change is needed, introduce a new name and migrate intentionally.
- For incompatible changes, create a new schema version and support both in parallel during the transition window.
- Store schemas alongside example payloads so producers and consumers can run contract tests.

For example, adding `currency` to `OrderCreated` can be compatible if the new field is optional and older consumers ignore unknown fields. Changing `total` from tax-inclusive to tax-exclusive is a semantic change; it requires a new version or a new field.

Do not confuse the envelope version with the event type version. If there are many event types, a system can version schemas per type or manage schemas via a registry. Pick a consistent strategy and clearly document the authoritative source of version information.

## 9. Relationship to CloudEvents

If you need an event contract that interoperates across multiple platforms, consider the CloudEvents standard. CloudEvents 1.0 defines core context attributes:

- `specversion`: CloudEvents specification version, e.g., `1.0`.
- `id`: event identifier.
- `source`: event producer; the pair `source` + `id` uniquely identifies the event.
- `type`: type of occurrence being described.
- `time`: timestamp when the occurrence happened (optional field).
- `data`: business payload (optional field in the standard).

Key point: `specversion` is the CloudEvents specification version, not necessarily the business schema version of `data`. CloudEvents also provides `datacontenttype` and `dataschema` to describe the payload's format and schema.

An internal envelope with `schemaVersion`, `messageId`, `occurredAt`, and `data` is a valid application contract, though it does not automatically become a CloudEvent. If you claim CloudEvents compliance, you must satisfy all required attributes and encoding rules of the specification.

## 10. Runnable Java 17 Example with Spring Messaging

This example creates an envelope, wraps it in a Spring `Message`, and prints key fields. Business ID and timestamp values are fixed so the output can be matched deterministically.

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-envelope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**EnvelopeDemo.java**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public class EnvelopeDemo {

    record OrderCreated(String orderId, BigDecimal total) {}

    record Envelope<T>(
        int schemaVersion,
        UUID messageId,
        Instant occurredAt,
        T data
    ) {
        Envelope {
            if (schemaVersion < 1) {
                throw new IllegalArgumentException("schemaVersion must be positive");
            }
            Objects.requireNonNull(messageId, "messageId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(data, "data");
        }
    }

    public static void main(String[] args) {
        Envelope<OrderCreated> envelope = new Envelope<>(
            1,
            UUID.fromString("7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001"),
            Instant.parse("2026-11-07T14:00:00Z"),
            new OrderCreated("ORD-1001", new BigDecimal("125000.00"))
        );

        Message<Envelope<OrderCreated>> message = MessageBuilder
            .withPayload(envelope)
            .setHeader("eventType", "com.example.order.created")
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .build();

        System.out.println("schemaVersion = " + message.getPayload().schemaVersion());
        System.out.println("messageId = " + message.getPayload().messageId());
        System.out.println("occurredAt = " + message.getPayload().occurredAt());
        System.out.println("data = " + message.getPayload().data());
        System.out.println("springHeaderIdPresent = "
            + (message.getHeaders().get(MessageHeaders.ID) != null));
        System.out.println("eventType = " + message.getHeaders().get("eventType"));
        System.out.println("contentType = "
            + message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
    }
}
~~~

Run from the directory containing `pom.xml` and `EnvelopeDemo.java`.

Linux/macOS:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" EnvelopeDemo.java
java -cp ".:$(cat cp.txt)" EnvelopeDemo
~~~

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\EnvelopeDemo.java
java -cp ".;$cp" EnvelopeDemo
~~~

Output:

~~~text
schemaVersion = 1
messageId = 7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001
occurredAt = 2026-11-07T14:00:00Z
data = OrderCreated[orderId=ORD-1001, total=125000.00]
springHeaderIdPresent = true
eventType = com.example.order.created
contentType = application/json
~~~

This program demonstrates creating an envelope and wrapping it in an in-memory Spring Message. The JSON at the beginning is an illustrative wire representation; to actually send JSON, the application must configure the corresponding encoder/decoder or serializer. The `eventType` and `contentType` headers in the example are Spring Message metadata and are not automatically inserted into the JSON body.

## 11. Common Design Mistakes

1. **Using Spring's header ID as the business message ID.** Spring's ID identifies the message instance; creating a new message can generate a different ID. Keep the logical ID in the envelope.
2. **Using receipt time instead of occurrence time.** Delayed or replayed messages distort the timeline. Keep `occurredAt`, `receivedAt`, and `processedAt` separate.
3. **Generating a new ID on retry.** Consumers treat each resend as a new message and may repeat side effects. Preserve the logical message ID.
4. **Treating timestamps as absolute ordering.** Clocks across machines can drift. Use sequences, aggregate versions, or offsets when reliable ordering is needed.
5. **Using one version for multiple concepts.** Schema version, event type version, and entity version have different lifecycles.
6. **Changing a field's meaning without changing the contract.** Consumers may still deserialize successfully but process the data incorrectly.
7. **Putting persistence entities directly into `data`.** Proxies, lazy relationships, and database schema changes make the messaging contract fragile.
8. **Stuffing unnecessary metadata into the envelope.** Only add correlation, causation, source, or trace when there is a clear cross-system requirement.
9. **Trusting producer-supplied metadata without verification.** ID, timestamp, and source are controlled by the sender; they are not proof of authentication or authorization.
10. **Assuming `MessageBuilder` automatically serializes the entire message.** Spring Message is an in-application abstraction; transport encoders and header mappers determine what data actually goes over the wire.

## 12. Contract Design Checklist

Before publishing a message type, confirm:

- [ ] The name and meaning of `schemaVersion` are clearly defined.
- [ ] `messageId` is unique within the source's scope and preserved across retries.
- [ ] `occurredAt` is the occurrence time, using `Instant`/UTC and a consistent serialization format.
- [ ] `data` has a dedicated DTO/record with clear data types, units, and nullability rules.
- [ ] Consumers validate version, required fields, size, and business invariants.
- [ ] A deduplication/idempotency policy tied to the business transaction is in place.
- [ ] Compatibility rules and a transition plan exist when the schema changes.
- [ ] Spring Message metadata is clearly distinguished from contract fields that must survive across transports.
- [ ] If cross-platform interoperability is needed, evaluate adopting CloudEvents rather than inventing a half-baked standard.

## References

- [Spring Framework Javadoc — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): payload and headers abstraction.
- [Spring Framework Javadoc — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html): standard headers such as `ID`, `TIMESTAMP`, and `CONTENT_TYPE`.
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html): building messages and setting headers.
- [Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html): semantics of payload, headers, ID, and timestamp in messaging.
- [CloudEvents Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md): standardizing context attributes, `source` + `id` identification, occurrence time, and event data.
