# CloudEvents Integration and Version Support Comparison

## 1. Goals and Context

**Spring Cloud Function (SCF)** encourages building business logic with `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. Through `FunctionCatalog`, a function can be looked up, composed (*composition*), and invoked over HTTP, events, serverless, or an `IntegrationFlow` without direct protocol coupling.

**Spring Integration** provides Enterprise Integration Patterns (EIP) such as *Message Channel*, *Transformer*, *Router*, *Filter*, *Gateway*, *Poller*, and *Error Channel*. **CloudEvents** solves a problem at a different layer: a **standardized event description format** that lets event producers and consumers exchange core attributes—such as event ID, source, and event type—independently of the transport protocol.

When combining all three, an application needs to know:

- Which attributes CloudEvents 1.0 requires, and how `data` differs from metadata?
- How **binary content mode** and **structured content mode** affect HTTP headers/bodies, `Message<?>`, and converters?
- How to ingest events into Spring Integration, invoke business functions in `FunctionCatalog`, and emit a new CloudEvent?
- Which version milestones provide CloudEvents utilities in **Spring Cloud Function**, and which introduce the **`spring-integration-cloudevents`** module?
- Which checks are needed to prevent version skew, content-type mismatches, lost metadata, duplicate processing, or emitting invalid events?

This lesson belongs to the **Spring Integration** chapter of the **SPRING_CLOUD_FUNCTION** module. Model explanations and version details are clearly separated so you can apply them to both Spring Boot 3.x projects and newer release lines without assuming every API exists in every release.

## 2. What CloudEvents Is and Is Not

CloudEvents is a specification developed by the CNCF community to describe **an event that occurred** in a uniform structure. It defines context attributes, event data, and formats/protocol bindings for transport over HTTP, Kafka, AMQP, and other media.

A simple example: an order service emits an "order created" event:

~~~json
{
  "specversion": "1.0",
  "id": "evt-DH-101-v1",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "subject": "orders/DH-101",
  "time": "2026-11-24T09:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "DH-101",
    "totalVnd": 1500000
  }
}
~~~

**CloudEvents is not a message broker, queue, workflow engine, or Spring Integration flow.** It does not inherently provide retries, transactions, ordering, exactly-once delivery, or a DLQ. Nor does `FunctionCatalog` create event-sending adapters on its own; connectivity still requires the appropriate HTTP adapter, Spring Cloud Stream binder, Spring Integration adapter, or serverless event adapter.

~~~mermaid
flowchart LR
    P["Event-producing service"] --> A["CloudEvents<br/>context + data"]
    A --> B["HTTP / Kafka / AMQP / serverless"]
    B --> C["Adapter / header mapper"]
    C --> D["Spring Integration<br/>Message + EIP"]
    E["FunctionCatalog"] -. "lookup / composition" .-> F["Business function"]
    D --> F
    F --> G["Transformer / outbound adapter"]
    G --> H["Resulting CloudEvent if needed"]
~~~

## 3. The CloudEvents 1.0 Contract

### 3.1. Required Attributes

In CloudEvents **specversion 1.0**, every valid event must include four context attributes:

| Attribute | Type | Meaning | Example |
| --- | --- | --- | --- |
| `specversion` | String | Version of the specification the event conforms to. | `"1.0"` |
| `id` | String | Event identifier within the producer's scope. | `"evt-DH-101-v1"` |
| `source` | URI-reference | Identifies the context or origin of the event. | `"/sales/order-service"` |
| `type` | String | Classifies the event's meaning as agreed by producer and consumer. | `"com.example.order.created"` |

The producer must ensure **the `source + id` pair is unique for each distinct event**. When the same event is redelivered, consumers can treat that pair as a duplicate-event signal—a solid foundation for idempotency. `source` must be a non-empty URI-reference; an absolute URI is recommended though not required.

### 3.2. Optional Attributes and Data

| Attribute | Role |
| --- | --- |
| `subject` | Identifies a specific resource within the `source` context, e.g., `orders/DH-101`. |
| `time` | Timestamp of when the event occurred (valid timestamp format); distinct from broker delivery time. |
| `datacontenttype` | Media type of `data`, e.g., `application/json` or `text/plain`. |
| `dataschema` | URI pointing to a schema describing `data`; by itself it does not force consumers to fetch or automatically validate the schema. |
| `data` | The event payload, not one of the four required context attributes. |
| `Extension attributes` | Custom contract metadata such as `traceid` or `tenantid`; extension names must conform to spec rules. |

Do not confuse:

- `specversion` is the **CloudEvents specification version**, e.g., `1.0`.
- `dataschema` or a `schemaVersion` field inside `data` pertains to the **business data contract version**.
- `spring-cloud-function` `4.x/5.x` and Spring Integration `6.x/7.x` are **library versions**.
- `type` describes the **event type**, not a bean name in `FunctionCatalog`.

A system can simultaneously use CloudEvents 1.0, business schema v3, and Spring Cloud Function 5.1; those three numbers mean completely different things.

### 3.3. Event Compatibility

A consumer should not merely check `specversion == "1.0"` and trust everything else. Validate `source`, the allowed set of `type` values, business schema version, `data` format, payload size, and producer identity. For external events, metadata arriving in headers is still **untrusted input**, not proof of authentication.

## 4. Binary and Structured Content Modes

These are two ways of transmitting **the same CloudEvent** defined by the CloudEvents HTTP protocol binding.

### 4.1. Structured Mode

Context attributes and `data` sit together in **one JSON object**; the HTTP `Content-Type` header is `application/cloudevents+json`:

~~~http
POST /events HTTP/1.1
Host: localhost:8080
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-101",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "datacontenttype": "application/json",
  "data": {"orderId":"DH-101","totalVnd":1500000}
}
~~~

To read a structured CloudEvent, the receiver needs a parser for the appropriate **event format**; you cannot simply treat the raw body directly as an `OrderCreated`, because the body also contains the context envelope.

### 4.2. Binary Mode

CloudEvents attributes are placed in **HTTP binding headers**, while the body is the event `data` itself:

~~~http
POST /events HTTP/1.1
Host: localhost:8080
Content-Type: application/json
ce-specversion: 1.0
ce-id: evt-101
ce-source: /sales/order-service
ce-type: com.example.order.created

{"orderId":"DH-101","totalVnd":1500000}
~~~

The word "binary" here describes **how metadata is separated from the body**; `data` can still be JSON or plain text. Over HTTP, `ce-` is the prefix for CloudEvent context attributes in binary mode. For Kafka/AMQP, check the specific protocol binding and header mapper; **do not assume every transport uses the exact `ce-` prefix**.

### 4.3. Comparison Table

| Aspect | Structured | Binary |
| --- | --- | --- |
| Where context lives | Same object/event format alongside `data` in the body. | Transport headers or corresponding metadata. |
| HTTP Content-Type | `application/cloudevents+json` for JSON structured mode. | The `datacontenttype` of `data`, e.g., `application/json`. |
| How it is read | Deserialize the whole CloudEvent, then extract `data`. | Read CloudEvents headers and the data body. |
| Across a broker | Needs matching format/binding; broker may carry the entire event in the payload. | Needs broker-appropriate header mapping. |
| Common failures | Missing JSON EventFormat or wrong content type. | Context headers dropped by an adapter, or wrong header prefix. |

CloudEvents also defines a **batch mode** in the HTTP binding, but do not assume every Spring Integration transformer or adapter automatically supports sending/receiving multiple CloudEvents in a single call. Check batch support explicitly for your exact version.

## 5. Feature Comparison by Version

This section distinguishes **three separate layers**: Spring Cloud Function, Spring Integration, and the CloudEvents Java SDK. These details were verified against official documentation as of **24/11/2026**.

### 5.1. Feature Support Matrix

| Component / Version Line | CloudEvents and Related APIs | Applicability Notes |
| --- | --- | --- |
| **Spring Cloud Function 3.1+** | Includes `CloudEventMessageBuilder`, `CloudEventMessageUtils`, and support for representing CloudEvents in Spring Messages. | This is a **SCF context** utility; it does not imply a dedicated Spring Integration CloudEvents module. |
| **Spring Cloud Function 4.0.3+** | Includes `spring-cloud-function-integration` and `FunctionFlowBuilder` for catalog-name `fromSupplier`, `apply`, and `accept`. | Connects the function model to the Integration DSL; it is not a CloudEvents serializer by itself. |
| **Spring Integration 6.x and 7.0.x** | Still provides Messages, Transformers, Header Enrichers, and adapters to build CloudEvents flows with the SDK or header mappers. | **Does not yet include** the dedicated `spring-integration-cloudevents` module. |
| **Spring Integration 7.1.0+ (GA June 2026)** | Adds **`spring-integration-cloudevents`**, `ToCloudEventTransformer`, `FromCloudEventTransformer`, and the CloudEvents DSL. | Dedicated module documented to support **CloudEvents spec 1.0**. |
| **Spring Integration 7.2.0 (GA 19/11/2026)** | Continues providing the CloudEvents module and transformers. | You can consult 7.2 docs, but align with your active BOM/Boot version. |
| **CloudEvents Java SDK** | `CloudEvent`, `CloudEventBuilder.v1()`, `EventFormatProvider`, HTTP/Kafka bindings, and event formats. | **Java SDK** version is independent of `specversion: "1.0"`; JSON format requires the matching dependency. |

**Four easily confused milestones:**

1. SCF supported the **CloudEvents headers** model before Spring Integration had a dedicated CloudEvents module.
2. `spring-cloud-function-integration` appeared in **SCF 4.0.3** for invoking functions from Spring Integration; this module name is distinct from `spring-integration-cloudevents`.
3. `spring-integration-cloudevents` appeared in **Spring Integration 7.1**; **you cannot simply copy an import for `ToCloudEventTransformer` into an SI 6.5 project** and expect the class to exist.
4. `ToCloudEventTransformer` and `FromCloudEventTransformer` currently target **CloudEvents v1.0**. Do not treat an undocumented future `specversion` as compatible by default.

### 5.2. Alignment by Release Train

| Reference Project Line | Spring Boot / Spring Cloud | Sensible CloudEvents Approach |
| --- | --- | --- |
| Spring Boot 3.5.x project | Spring Cloud 2025.0.x, SCF 4.3.x per release train. | Leverage SCF `CloudEventMessageBuilder`, CloudEvents Java SDK, and existing Spring Integration DSL; do not assume SI 7.1's CloudEvents module is present. |
| Spring Boot 4.0.x/4.1.x project | Matching Spring Cloud 2025.1.x, SCF 5.0.x. | Check the **Spring Integration version managed by your actual patch/BOM**; 7.0 lacks the dedicated CloudEvents module, whereas 7.1+ provides it after verifying compatibility. |
| Spring Boot 4.2.x project | Spring Cloud 2026.0.x and SCF 5.1.x per train. | Can target Spring Integration 7.2.x and the CloudEvents module; check release notes, BOM, and starters before running. |

This table is a **guide for choosing APIs**, not permission to upgrade SI or SCF independently to a different major version. Versions of **Spring Boot**, **Spring Cloud release train**, **Spring Integration**, **CloudEvents SDK**, and **CloudEvents specversion** must be verified at their respective layers. The safest approach is picking a Spring Cloud BOM compatible with Boot, then inspecting the resolved dependency tree and documentation for the pinned version.

### 5.3. Checking Actual Dependencies

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,org.springframework.integration,io.cloudevents
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

In the output, verify `spring-cloud-function-context`, `spring-cloud-function-integration`, `spring-integration-core`, `spring-integration-cloudevents`, and `io.cloudevents` modules. A support matrix only applies when those artifacts are actually present in your build.

## 6. Choosing the Right Integration Approach

### 6.1. Approach A — Using Spring Cloud Function and Spring Message Metadata

If your project does not yet include `spring-integration-cloudevents`, you can still use SCF utilities:

~~~java
import org.springframework.cloud.function.cloudevent.CloudEventMessageBuilder;
import org.springframework.messaging.Message;

Message<String> eventMessage = CloudEventMessageBuilder
        .withData("DH-101")
        .setSource("/sales/order-service")
        .setType("com.example.order.created")
        .setId("evt-101")
        .build();
~~~

`CloudEventMessageBuilder` helps construct a `Message<T>` with context attributes. Header prefixes and content handling are applied by adapters per protocol; calling `build()` alone does not turn it into **structured CloudEvents JSON**.

When receiving `Message<OrderCreated>`, a business function can read both payload and metadata if needed:

~~~java
@Bean
Function<Message<String>, Message<String>> normalizeEvent() {
    return message -> MessageBuilder.fromMessage(message)
            .setPayload(message.getPayload().strip().toUpperCase())
            .build();
}
~~~

This approach uses **SCF context** and Spring Messaging. If a function needs no metadata, prefer `Function<String,String>` for simpler reuse. Adapter conversions must be verified separately.

### 6.2. Approach B — Using the Java SDK to Construct CloudEvents

Example using the CloudEvents Java SDK:

~~~java
import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;

import java.net.URI;
import java.nio.charset.StandardCharsets;

CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-101")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withSubject("orders/DH-101")
        .withData("text/plain",
                " dh-101 ".getBytes(StandardCharsets.UTF_8))
        .build();
~~~

The SDK gives explicit control over context attributes and serializes using a matching `EventFormat`. To transmit structured JSON, include an event format module such as `cloudevents-json-jackson` (or the Jackson 3 variant depending on your SDK version).

### 6.3. Approach C — Using the `spring-integration-cloudevents` Module

With Spring Integration **7.1+**, two transformers are available:

- **`FromCloudEventTransformer`:** from a `CloudEvent` payload or bytes representing a structured CloudEvent, creates a Spring Integration message whose payload is `data` and whose CloudEvents metadata becomes headers such as `ce-id`, `ce-type`, and `ce-source`.
- **`ToCloudEventTransformer`:** converts a Spring Integration message into CloudEvents. Without an `EventFormat`, it uses **binary mode**, keeping the payload and adding CloudEvents headers. With a format, it serializes the CloudEvent into the payload using **structured mode**.

This module is a tool for **normalizing message boundaries**; business logic afterward continues to use `Supplier`, `Function`, `Consumer`, or the catalog as usual.

## 7. Dependencies for the Spring Integration 7.1+ Example

The examples below target Spring Integration 7.1+ with a compatible Spring Cloud Function release, Java 17+, and Spring Boot with configured dependency management.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-cloudevents</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-integration-cloudevents` builds on the CloudEvents Java SDK; check your dependency tree and add `cloudevents-core` or an EventFormat module if your application uses the SDK directly or needs structured JSON. The next example uses `CloudEventBuilder.v1()` and a text payload, so no JSON EventFormat is needed to construct the `CloudEvent` object.

**Do not drop a random Spring Integration 7.1/7.2 version into a project locked to Spring Integration 6.x.** If your project's BOM does not yet manage the newer artifact, choose a compatible release train before adding it.

## 8. Inbound Example: CloudEvent → IntegrationFlow → FunctionCatalog

### 8.1. Problem Statement

The input is a CloudEvent of type `com.example.order.created` whose `data` is a UTF-8 text order ID. Flow:

1. Receive a `Message<CloudEvent>` on channel `events.input`.
2. `FromCloudEventTransformer` extracts `data` as a `byte[]` payload and puts `ce-id`, `ce-source`, and `ce-type` into headers.
3. Convert payload bytes into a `String`.
4. Look up and invoke `normalizeOrderId` from `FunctionCatalog`.
5. Send the normalized string to a `QueueChannel` for testing.

~~~mermaid
flowchart LR
    A["CloudEvent object"] --> B["events.input"]
    B --> C["FromCloudEventTransformer"]
    C --> D["Message<byte[]> + ce-* headers"]
    D --> E["UTF-8 byte[] → String"]
    E --> F["FunctionCatalog.lookup(normalizeOrderId)"]
    F --> G["events.output QueueChannel"]
~~~

### 8.2. CloudEvents-Independent Business Function

Create `src/main/java/example/events/OrderFunctions.java`:

~~~java
package example.events;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<String, String> normalizeOrderId() {
        return orderId ->
                orderId.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

This function can be invoked from HTTP, CloudEvents, Kafka messages, or serverless adapters given an appropriate payload conversion step. It has zero dependencies on `CloudEvent`, `Message<?>`, or channel names.

### 8.3. IntegrationFlow Using the Official Transformer

Create `src/main/java/example/events/EventFlows.java`:

~~~java
package example.events;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

// CloudEvents is the DSL factory from the spring-integration-cloudevents module.
// Your IDE should import the class matching your Spring Integration 7.1+ version.

@Configuration
class EventFlows {

    @Bean("events.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("events.output")
    PollableChannel output() {
        return new QueueChannel(16);
    }

    @Bean
    IntegrationFlow incomingEvents(FunctionCatalog catalog) {
        Function<String, String> normalize = Objects.requireNonNull(
                catalog.lookup("normalizeOrderId"),
                "normalizeOrderId not found");

        return IntegrationFlow.from("events.input")
                .transform(CloudEvents.fromCloudEventTransformer())
                .transform(byte[].class, data ->
                        new String(data, StandardCharsets.UTF_8))
                .filter(String.class, orderId -> !orderId.isBlank())
                .transform(String.class, normalize::apply)
                .channel("events.output")
                .get();
    }
}
~~~

`.transform(CloudEvents.fromCloudEventTransformer())` is the official Java DSL API from the CloudEvents module. `FromCloudEventTransformer` handles the envelope, while `normalizeOrderId` handles business logic. `QueueChannel` lets tests collect results without needing a poller if the test calls `receive(...)` directly.

**Policies worth adding in production:** validate `specversion`, `source`, and `type` before processing data, verify `datacontenttype` against the format you intend to parse, and enforce size and schema checks. In this minimal example, we assume the producer already sent valid `text/plain` and the expected event type.

### 8.4. Sending an Event into the Flow

Create a `CloudEvent` with the SDK and send it into the input channel:

~~~java
CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-101")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withData("text/plain",
                " dh-101 ".getBytes(StandardCharsets.UTF_8))
        .build();

MessageChannel input =
        context.getBean("events.input", MessageChannel.class);

input.send(MessageBuilder.withPayload(event).build());

PollableChannel output =
        context.getBean("events.output", PollableChannel.class);

Message<?> result = output.receive(1000);

assertNotNull(result);
assertEquals("DH-101", result.getPayload());
assertEquals("evt-101", result.getHeaders().get("ce-id"));
assertEquals("com.example.order.created",
        result.getHeaders().get("ce-type"));
~~~

This is part of a test or code snippet with an `ApplicationContext context` and matching SDK/JUnit/Spring Messaging imports. With `DirectChannel`, transformers run synchronously before `send(...)` returns; `receive(1000)` retrieves the message stored by `QueueChannel`.

`ce-id` is the CloudEvents event ID, **distinct** from the `id` header generated by Spring Messaging. In systems with redelivery, use `source + id` rather than the Spring Message ID as the basis for deduplication.

## 9. Structured JSON Input Example

Now suppose the producer sends bytes of a structured CloudEvent JSON instead of a `CloudEvent` object:

~~~json
{
  "specversion": "1.0",
  "id": "evt-102",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "datacontenttype": "text/plain",
  "data": "  dh-102  "
}
~~~

At Spring Integration ingress, the message might be constructed like this:

~~~java
byte[] jsonBytes = eventJson.getBytes(StandardCharsets.UTF_8);

Message<byte[]> incoming = MessageBuilder
        .withPayload(jsonBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE,
                "application/cloudevents+json")
        .build();
~~~

Here `eventJson` is the JSON string shown above. When the matching `cloudevents-json-jackson` or `cloudevents-json-jackson3` module is on the classpath, `FromCloudEventTransformer` can look up an `EventFormat` via `EventFormatProvider` and deserialize the event. Afterward, the payload becomes the `data` bytes, attributes become `ce-*` headers, and the flow from Section 8 can proceed.

Do not overlook selecting the right JSON module:

- **Jackson 2:** `io.cloudevents:cloudevents-json-jackson`.
- **Jackson 3:** `io.cloudevents:cloudevents-json-jackson3`, provided in SDK lines supporting Jackson 3.
- **Pin the SDK version** and format modules from the same release line; do not arbitrarily mix the two modules or assume Spring Boot 4 guarantees every format is already present.

If a matching format is missing or `contentType` does not match a registered format, the transformer may throw `MessageTransformationException`. Test structured and binary modes separately since they follow different decode paths.

## 10. Outbound: Function Produces Data, Transformer Produces CloudEvent

On the outbound path, the business function should return a **domain result** or payload bytes with a valid serializer. The `IntegrationFlow` layer adds CloudEvents context.

~~~text
Business function
    ↓
OrderDecision
    ↓ serialize to byte[] per datacontenttype
Message<byte[]> + eventId/source/type
    ↓
ToCloudEventTransformer
    ├─ without EventFormat → binary mode (ce-* headers)
    └─ with EventFormat → structured mode (serialized CloudEvent)
    ↓
Outbound adapter (HTTP / broker / serverless)
~~~

### 10.1. Binary Mode with ToCloudEventTransformer

Example DSL structure for a message with a `byte[]` payload and `contentType = "text/plain"`:

~~~java
return IntegrationFlow.from("events.outboundInput")
        .enrichHeaders(CloudEvents.headers()
                .idExpression("headers['businessEventId']")
                .sourceFunction(message ->
                        URI.create("/sales/order-service"))
                .type("com.example.order.normalized"))
        .transform(CloudEvents.toCloudEventTransformer())
        .channel("events.binaryOutput")
        .get();
~~~

This is a fragment: the input/output channels and `businessEventId` header must be declared, along with imports for `java.net.URI` and the `CloudEvents` DSL factory. According to Spring Integration 7.1+ documentation, **`ToCloudEventTransformer` requires a `byte[]` payload**. If you currently have an `OrderDecision` or `String`, serialize it explicitly before calling the transformer.

Without an `EventFormat` configured, the transformer uses binary mode: the data payload stays intact and context attributes are added as `ce-`-prefixed headers according to the module's mapping. The message's `contentType` reflects `datacontenttype`.

### 10.2. Structured Mode with EventFormat

If configured with a suitable `EventFormat` (or a content-type expression resolved via `EventFormatProvider`), `ToCloudEventTransformer` can serialize the entire CloudEvent into the payload. For JSON, the media type is typically `application/cloudevents+json` and requires the matching JSON EventFormat module.

Never change a binary message's `Content-Type` to `application/cloudevents+json` without actually serializing the event. That common bug tricks consumers into treating a `data`-only body as a structured CloudEvent, causing parse failures.

### 10.3. Deliberately Defining id, source, and type

The transformer has defaults such as message ID, internal source, and generic type per documentation. When emitting **business events**, explicitly set:

- `id`: a stable event ID, kept unchanged if the same event must be retried.
- `source`: the published producer identifier.
- `type`: the agreed event name, e.g., `com.example.order.normalized`.
- `datacontenttype`: matching the actual serializer used for `data`.
- `subject` and extensions: add only when required by the contract, avoiding sensitive data exposure.

When a function processes an input event and **emits a new event**, do not blindly copy all four required attributes from the input event onto the new event: a new event generally needs a new `id`/`type`; you can preserve `correlationId` to trace causality.

## 11. Header Mapping and Differences Between Spring Message and CloudEvent

After `FromCloudEventTransformer`, a Spring Integration message typically contains:

~~~text
payload = byte[] (" dh-101 ")
headers:
  ce-id              = evt-101
  ce-source          = /sales/order-service
  ce-type            = com.example.order.created
  ce-datacontenttype = text/plain
  contentType        = text/plain
  id                 = ... (Spring Message ID)
  timestamp          = ...
~~~

This is the **internal** representation after the transformer maps event attributes. `ce-id` is CloudEvent context; `id` is the Spring Message identifier. Neither should be overwritten unintentionally.

Things to verify:

1. **Transport bindings:** `ce-` in HTTP binary mode differs from Kafka/AMQP binding rules; use protocol-appropriate adapters or SDK bindings.
2. **Adapter header mappers:** some adapters only forward allowlisted headers; test `ce-id`, `ce-source`, and `ce-type` after passing through real infrastructure.
3. **Content type:** `application/cloudevents+json` describes the **structured envelope**; `application/json`/`text/plain` describes **`data`** in binary mode.
4. **Function signatures:** `Function<byte[],R>` takes raw data; `Function<OrderCreated,R>` requires a decoder/mapper; `Function<Message<T>,Message<R>>` can inspect headers when needed.
5. **Routing:** using `ce-type` to pick an EIP channel is an Integration-layer decision; calling a function directly from the catalog does not route messages through a router on its own.

If an external source is allowed to select a function name via a header or expression, maintain an allowlist of callable functions and avoid evaluating arbitrary expressions from untrusted data.

## 12. Common Failures in CloudEvents Support

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Event missing `specversion`, `id`, `source`, or `type` | Producer emitted an invalid event or header mapping dropped attributes. | Validate CloudEvents before business functions; inspect transport bindings. |
| Event has unsupported `specversion` | Consumer/transformer only declares support for spec v1.0. | Reject cleanly, upgrade components when official support arrives. |
| Structured JSON parsed as domain JSON | Wrong `contentType` or skipped envelope deserialization. | Set `application/cloudevents+json` and the matching EventFormat. |
| `FromCloudEventTransformer` fails to deserialize | Payload is not a `CloudEvent`/valid serialized bytes, or format is missing. | Check payload type, content type, and `EventFormatProvider`. |
| `ToCloudEventTransformer` rejects payload | Input is not `byte[]` as required by the transformer contract. | Serialize the domain object before transforming. |
| Consumer misses `ce-type` over Kafka | Header mapper or protocol binding differs from HTTP. | Inspect Kafka bindings and actual runtime headers. |
| `ClassNotFoundException` for transformer | Running Spring Integration older than 7.1 or missing artifact. | Check BOM and `spring-integration-cloudevents`. |
| Cannot inject `FunctionFlowBuilder` | Missing `spring-cloud-function-integration` or SCF version too old. | Verify SCF 4.0.3+ and auto-configuration. |
| Event processed twice | Broker retry/redelivery or caller retry. | Enforce idempotency by `source + id` and proper transactions. |
| Metadata lost when function returns result | Function only returns payload or adapter drops headers. | Use a message-aware contract where needed; test header propagation. |

A validation error does not necessarily warrant retries; infrastructure errors can use retry/backoff; format or schema mapping errors may belong in quarantine or a dead-letter queue for inspection. `FunctionCatalog`, CloudEvents, and Spring Integration do not provide exactly-once delivery without explicit delivery design.

## 13. Contract-Based and Version-Based Testing

### 13.1. Unit Testing Pure Functions

~~~java
OrderFunctions functions = new OrderFunctions();

assertEquals("DH-101",
        functions.normalizeOrderId().apply(" dh-101 "));
~~~

This tests business logic. It does not prove a serialized CloudEvent can travel over HTTP or a broker.

### 13.2. Testing the Transformer with a CloudEvent Object

~~~java
CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-201")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withData("text/plain",
                "dh-201".getBytes(StandardCharsets.UTF_8))
        .build();

Message<?> parsed = new FromCloudEventTransformer().transform(
        MessageBuilder.withPayload(event).build());

assertEquals("evt-201", parsed.getHeaders().get("ce-id"));
assertEquals("com.example.order.created",
        parsed.getHeaders().get("ce-type"));
assertEquals("dh-201",
        new String((byte[]) parsed.getPayload(),
                StandardCharsets.UTF_8));
~~~

This tests the **Spring Integration 7.1+** module; key classes are `io.cloudevents.CloudEvent`, `io.cloudevents.core.builder.CloudEventBuilder`, and `FromCloudEventTransformer` from `spring-integration-cloudevents`.

### 13.3. Integration Testing the Flow

In the Section 8 example, send `Message<CloudEvent>` to `events.input` and call `events.output.receive(timeout)`. Verify:

- The payload from text data `" dh-101 "` is normalized to `"DH-101"`.
- Headers `ce-id`, `ce-source`, and `ce-type` remain usable for correlation.
- Blank messages are dropped by the EIP Filter per flow policy.
- Messages with invalid `type`, invalid `specversion`, or unsupported formats are rejected at the proper validation layer.

### 13.4. Contract Tests at Real Boundaries

| Case | What to Verify |
| --- | --- |
| HTTP structured JSON | `Content-Type: application/cloudevents+json` and parser reads both context and data. |
| HTTP binary | `ce-*` headers are mapped; body remains domain data matching `datacontenttype`. |
| Kafka/AMQP | Header mapping follows protocol bindings without assuming HTTP prefixes. |
| Domain schema v1/v2 | Consumer accepts/rejects strictly per domain contract, independent of `specversion`. |
| Redelivery | `source + id` is stable; consumer is idempotent. |
| Missing EventFormat | Structured parsing fails cleanly rather than swallowing errors. |
| Release train upgrade | Build, imports, APIs, and wire formats verified under the pinned BOM. |

## 14. Upgrade Path from Older Projects

If a project is currently on SCF 4.x + Spring Integration 6.x:

1. **Keep business functions pure:** `Function<OrderCreated,OrderDecision>` handles only domain payloads.
2. **Wrap CloudEvents at the boundary:** use `CloudEventMessageBuilder` or the CloudEvents Java SDK; map context headers explicitly and safely if needed.
3. **Test structured/binary modes and header mapping:** especially across Kafka or AMQP.
4. **Pick a compatible release train before upgrading:** upgrade Spring Boot/Spring Cloud via published BOMs, then verify SI 7.1+ and `spring-integration-cloudevents`.
5. **Adopt official transformers when ready:** place `FromCloudEventTransformer` before business functions and `ToCloudEventTransformer` after output serialization.
6. **Preserve event ID/schema contracts:** avoid altering `source`, `id`, or `type` merely because you changed libraries or implementations; plan compatibility for business schema changes.

An application does not have to migrate to Spring Integration 7.1 just to support CloudEvents. SCF and the CloudEvents SDK already allow contract-compliant implementations on earlier versions. The advantage of the newer module is DSL-level transform/metadata integration and less manual boundary boilerplate.

## 15. Design Checklist

- [ ] Consumer validates `specversion`, `id`, `source`, and `type` before running business logic.
- [ ] Producer ensures `source + id` is unique for distinct events and stable across retries of the same event.
- [ ] `datacontenttype` matches the bytes in `data` and has appropriate mappers/schema validation.
- [ ] It is clear whether incoming messages are **`CloudEvent` objects**, **structured bytes**, or **binary data + metadata**.
- [ ] SCF, SI, SDK, and Spring Boot/Cloud BOM versions have been verified together.
- [ ] `spring-integration-cloudevents` is not added if the project is on SI below 7.1.
- [ ] SCF's `spring-cloud-function-integration` is not confused with SI's `spring-integration-cloudevents`.
- [ ] Business functions stay independent of HTTP/Kafka/serverless when metadata is not needed.
- [ ] `ce-*` headers are tested at actual adapter boundaries without assuming identical prefixes across transports.
- [ ] Retries, DLQs, idempotency, and tracing have explicit policies rather than relying on the CloudEvents format alone.

### Self-Check Questions

1. Why does `specversion: "1.0"` not tell you the version of Spring Cloud Function?
2. In HTTP binary mode, what does `Content-Type: application/json` describe?
3. Why can't a consumer receiving a structured CloudEvent directly parse the JSON body as `OrderCreated`?
4. How does `CloudEventMessageBuilder` in SCF differ from Spring Integration's `ToCloudEventTransformer`?
5. Why can't an SI 6.x project simply add an import for `FromCloudEventTransformer` without upgrading compatible dependencies?
6. Why is idempotency based on `source + id` more reliable than Spring Message's `id` header?
7. If an event arrives with type `com.example.order.created` but `data` violates the schema, which layer should report the error?

## 16. Official References

- [CloudEvents 1.0 — Core Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md): required/optional attributes, meaning of `source + id`, and extensions.
- [CloudEvents — HTTP Protocol Binding](https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/http-protocol-binding.md): structured, binary, and batch content modes.
- [CloudEvents — JSON Event Format](https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md): CloudEvent serialization in structured JSON.
- [Spring Integration — CloudEvents Support](https://docs.spring.io/spring-integration/reference/cloudevents.html): module, `ToCloudEventTransformer`, `FromCloudEventTransformer`, and DSL.
- [Spring Integration — Changes between 7.0 and 7.1](https://docs.spring.io/spring-integration/reference/changes-7.0-7.1.html): milestone introducing the `spring-integration-cloudevents` module.
- [Spring Integration 7.1.0 Released](https://spring.io/blog/2026/06/10/spring-integration-7-1-0-released/): announcement of the new module.
- [Spring Integration 7.2.0 Released](https://spring.io/blog/2026/11/19/spring-integration-7-2-0-available/): announcement of the 7.2.0 release.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `FunctionFlowBuilder` and milestones starting in SCF 4.0.3.
- [Spring Cloud Function — CloudEventMessageBuilder Javadoc](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-context/4.0.1/org/springframework/cloud/function/cloudevent/CloudEventMessageBuilder.html): SCF utility available since 3.1.
- [CloudEvents Java SDK — Core](https://cloudevents.github.io/sdk-java/core.html) and [JSON Event Format](https://cloudevents.github.io/sdk-java/json-jackson.html): building/deserializing and managing event formats.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/): Spring Boot compatibility with Spring Cloud release trains.

**Conclusion:** CloudEvents defines the **event contract**; `FunctionCatalog` holds **reusable business logic**; Spring Integration and its adapters handle **routing, message conversion, and error handling**. With Spring Integration 7.1+, `spring-integration-cloudevents` adds CloudEvents 1.0 transformers; in older projects, Spring Cloud Function's CloudEvents utilities or the Java SDK can still be used. Verify **specversion, schema, library versions, and release trains** separately, and test wire formats, content types, header mappings, and idempotency before going to production.
