# Payload codecs and data MIME types in RSocket Adapter

## 1. Why does RSocket need codecs?

In module **SPRING_INTEGRATION_ADAPTERS**, we connect external systems into Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; at the same time we manage message contracts, errors, and connection lifecycles. With **RSocket Adapter**, the sender may operate on Java objects like `CreateOrder`, yet RSocket transmits data as **bytes**. Both sides must agree on that byte format to encode and decode correctly.

For example, a client wants to send:

~~~java
new CreateOrder("ORD-102", 3)
~~~

Over RSocket, the object must be encoded, for example into JSON:

~~~json
{"orderId":"ORD-102","quantity":3}
~~~

RSocket does not inherently know what Java type `CreateOrder` is, nor does it automatically turn arbitrary byte sequences into JSON. A **codec** handles this conversion; the **data MIME type** indicates which format is used.

After this lesson, you can:

- Distinguish **data/payload**, **metadata**, **data MIME type**, and codec in an RSocket interaction.
- Explain the direction of `Encoder` and `Decoder` in Spring RSocket.
- Configure a client with `RSocketRequester` and use JSON DTOs in a handler connected to Spring Integration.
- Know when additional codecs are needed for non-JSON formats, how to verify compatibility, and how to diagnose conversion errors.

## 2. Four concepts not to confuse

| Concept | Content | Example |
| --- | --- | --- |
| **Data/payload** | Business data carried in the data section of an RSocket payload | Order JSON |
| **Data MIME type** | Format name used by both sides to interpret the data section | `application/json`, `text/plain` |
| **Codec** | Encoder/decoder between application values and bytes | Jackson JSON encoder/decoder |
| **Metadata** | Accompanying info for routing or context | Route `orders.create`, trace ID |

RSocket's term *payload* is sometimes used to mean the **data + metadata pair**. In this document, when we say **business payload**, we refer only to the **data** part containing request/response content.

Conceptually, a request looks like this:

~~~text
RSocket connection SETUP
  data MIME type:     application/json
  metadata MIME type: message/x.rsocket.composite-metadata.v0

REQUEST_RESPONSE:
  metadata:
    routing entry -> orders.create
  data:
    {"orderId":"ORD-102","quantity":3}
~~~

A MIME type is not synonymous with a Java class name. The same `application/json` can be decoded into `CreateOrder`, `OrderReceipt`, or another type depending on the **target type requested by the handler/client** and the actual JSON structure.

## 3. Where is the data MIME type set?

In RSocket, the client sends a **SETUP frame** when opening a connection. SETUP carries `dataMimeType` and `metadataMimeType` declarations. For example:

~~~text
Client                        Server
  |                             |
  |-- SETUP ------------------->|  dataMimeType = application/json
  |                             |  metadataMimeType = composite
  |-- REQUEST_RESPONSE -------->|  data is JSON bytes
  |<---------- RESPONSE --------|  data also follows JSON contract
  |                             |
~~~

Key points to remember:

1. This is a **format declaration in SETUP**, not an automatic negotiation step to discover a common codec. Client and server must be configured compatibly.
2. In the standard RSocket model, the **data MIME type belongs to the connection**, not an independent per-request HTTP `Content-Type` header. Multiple routes sharing one connection must have data formats compatible with that connection's MIME type.
3. **Metadata MIME type** governs how the metadata section is interpreted. Routes normally live in routing metadata or a composite metadata entry; **a route is not a JSON body and does not determine the data MIME type**.
4. Java types and payload schemas can differ across routes on the same connection: `orders.create` accepts `CreateOrder`, while `orders.status` accepts `OrderQuery`, provided both can use the agreed JSON codec.

If two different data formats are needed—for example JSON and Protobuf—the clearest approach is using **two requesters/connections** with their respective SETUP and codec strategies, or designing an explicit agreed envelope protocol. Never assume calling a different route automatically switches the existing connection's data MIME type.

### Common MIME types

| Data MIME type | Data form | Application requirements |
| --- | --- | --- |
| `application/json` | JSON objects, arrays, scalars | Jackson or compatible JSON codec must be present |
| `application/*+json` | JSON subtypes with `+json` suffix, e.g. `application/vnd.example.order+json` | Codec must support that specific MIME type |
| `text/plain` | Text, strings | Text encoder/decoder with compatible charset |
| `application/octet-stream` | Binary bytes without a MIME-level schema | Use byte/buffer types and appropriate binary codecs |
| `application/cbor` | Structured binary CBOR data | Requires a CBOR codec; not automatically available just by using Spring |
| `application/x-protobuf` | Schema-driven Protobuf messages | Requires matching Protobuf schemas/types and codecs on both sides |

The MIME types in this table are protocol design examples. **Actual support depends on classpath, library versions, and `RSocketStrategies`**; merely declaring `application/cbor` or `application/x-protobuf` does not make the corresponding codec appear.

## 4. Where do encoders and decoders operate?

A codec has two primary responsibilities:

- **Encoder:** takes an application value and produces bytes matching the selected MIME type, e.g. `CreateOrder` → JSON.
- **Decoder:** takes bytes and reconstructs a value of the type desired by the caller/handler, e.g. JSON → `CreateOrder`.

In Spring Framework, common codec contracts are `org.springframework.core.codec.Encoder` and `Decoder`. Spring RSocket uses encoders/decoders from **`RSocketStrategies`** to process data, combining the MIME type and target data type.

~~~mermaid
flowchart LR
    A["Client: CreateOrder"] --> B["JSON Encoder"]
    B --> C["RSocket data bytes"]
    C --> D["JSON Decoder on server"]
    D --> E["@MessageMapping: CreateOrder"]
    E --> F["Spring Integration Message"]
    F --> G["IntegrationFlow"]
    G --> H["OrderReceipt"]
    H --> I["JSON Encoder on server"]
    I --> J["RSocket response bytes"]
    J --> K["JSON Decoder on client"]
    K --> L["Client: OrderReceipt"]
~~~

For request-response, there are **two independent codec passes**:

| Leg | Encoder | Decoder |
| --- | --- | --- |
| Request client → server | Client encodes request | Server decodes into handler parameter type |
| Reply server → client | Server encodes result | Client decodes per `retrieveMono(...)` target type |

Failure scenarios to distinguish:

- **No matching encoder:** client cannot convert the value to bytes; usually fails immediately when preparing or sending the request.
- **No matching decoder:** server receives bytes yet cannot construct the handler parameter type, or client cannot decode the reply.
- **Codec exists yet content is invalid:** malformed JSON, wrong field type, or incompatible schemas between the two sides.
- **Codec succeeds yet business rules fail:** DTO is constructed, but quantity is negative or order ID is missing; this is a validation error, not a codec error.

## 5. How Spring selects a codec

When Spring needs to send `CreateOrder`, it considers the source data type, the connection's data MIME type, and the encoders registered in `RSocketStrategies`. On the receiving side, it similarly checks the MIME type, available decoders, and the **handler parameter type** or the client's requested result type.

Example:

~~~java
// Server: target type is CreateOrder.
@MessageMapping("orders.create")
Mono<OrderReceipt> create(@Payload CreateOrder request) {
    // ...
}

// Client: target type when decoding response is OrderReceipt.
Mono<OrderReceipt> reply = requester
    .route("orders.create")
    .data(new CreateOrder("ORD-102", 3))
    .retrieveMono(OrderReceipt.class);
~~~

Those two snippets do not define new codecs: they **use already configured codecs**. In a Spring Boot app with Jackson and default Spring RSocket codecs, JSON DTOs usually work without manually registering encoders/decoders. Avoid registering duplicate JSON codecs unless you actually need to customize serialization behavior.

### What does `RSocketStrategies` contain?

`RSocketStrategies` aggregates strategies needed by Spring Messaging RSocket, including encoders, decoders, metadata extractors, route matchers, and supporting components. In this lesson, the directly relevant parts are encoders/decoders:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;

@Configuration
class CodecConfiguration {

    // Only use when custom/extra codecs are truly needed.
    // For standard JSON, Spring Boot may already configure it.
    @Bean
    RSocketStrategiesCustomizer customizeCodec() {
        return strategies -> {
            strategies.encoder(new Jackson2JsonEncoder());
            strategies.decoder(new Jackson2JsonDecoder());
        };
    }
}
~~~

This illustrates where codecs are registered, **not a mandatory configuration to run the JSON example** in the next section. In real systems, you may want to pass a shared `ObjectMapper` to preserve consistent JSON conventions such as date/time formatting, enums, and naming strategies. When client and server are separate applications, review codec configuration **at both ends**.

### Limits of "having Jackson is enough"

Jackson converts objects ↔ JSON, yet it does not solve every problem automatically:

- DTOs with incompatible field types or constructors can still cause mapping errors.
- Field names and date/time formats must match between sides.
- You cannot treat `text/plain` or `application/x-protobuf` as JSON just because bytes look readable.
- Registering a codec does not replace input validation or business authorization.
- For large payloads, decoders may buffer data in memory; design size limits and streaming appropriately.

## 6. End-to-end example: JSON over RSocket to IntegrationFlow

This example uses **Spring Boot 3, Spring Framework 6, and Spring Integration 6** to demonstrate request-response: the client sends an order as JSON, the server decodes it into `CreateOrder`, forwards it to a `MessageChannel`, and returns `OrderReceipt`. These Java snippets are illustrative components in **the same package or scanned packages**; in practice, place public types in their own Java files.

### Step 1 — Dependencies and RSocket server

Example Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

When client and server are separate applications, each needs the dependencies for its role. For an RSocket TCP server:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

If no JSON codec is on the classpath or autoconfiguration was altered, add Jackson/`RSocketStrategies` configuration before using JSON DTOs. Never rely on a MIME type string to assume a dependency is present.

### Step 2 — Define the data contract

~~~java
public record CreateOrder(String orderId, int quantity) {}

public record OrderReceipt(String orderId, String state) {}
~~~

With Spring Boot 3 and compatible Jackson, Java records are a clean choice for DTOs:

~~~json
{
  "orderId": "ORD-102",
  "quantity": 3
}
~~~

The data bytes contain no metadata saying "this is class `CreateOrder`". The server decides to decode into `CreateOrder` from the handler's signature. JSON fields must match the agreed DTO contract.

### Step 3 — Create an IntegrationFlow processing the DTO

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "newOrderInput")
    OrderReceipt create(CreateOrder order);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow createOrderFlow() {
        return IntegrationFlow.from("newOrderInput")
            .handle(CreateOrder.class, (order, headers) -> {
                if (order.orderId() == null || order.orderId().isBlank()) {
                    throw new IllegalArgumentException("orderId is required");
                }
                if (order.quantity() <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }

                // Illustrative: in practice, call order creation service/repository.
                return new OrderReceipt(order.orderId(), "ACCEPTED");
            })
            .get();
    }
}
~~~

`OrderGateway` is an internal messaging gateway feeding data into `newOrderInput`. The flow's handler receives the **already decoded DTO**, so business code does not manually parse JSON. Spring Integration can continue routing, transforming, invoking other adapters, or returning replies. Note that the quantity check is **business-layer validation**, occurring after JSON decoding succeeded.

### Step 4 — RSocket responder as inbound boundary

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class OrderRSocketController {
    private final OrderGateway gateway;

    OrderRSocketController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("orders.create")
    Mono<OrderReceipt> create(@Payload CreateOrder order) {
        return Mono.fromCallable(() -> gateway.create(order))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Spring Messaging RSocket uses routing metadata to match `orders.create`; then the matching decoder turns **data bytes** into `CreateOrder`. Because this example's messaging gateway is **synchronous**, `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` avoids running potentially blocking work on the RSocket event loop. An end-to-end reactive flow should design non-blocking gateways/handlers rather than relying solely on scheduler switching.

### Step 5 — RSocketRequester sends JSON and decodes reply

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

class OrderClient {
    private final RSocketRequester requester;

    OrderClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .metadataMimeType(MimeTypeUtils.parseMimeType(
                "message/x.rsocket.composite-metadata.v0"))
            .tcp("localhost", 7000);
    }

    Mono<OrderReceipt> create(CreateOrder order) {
        return requester.route("orders.create")
            .data(order)
            .retrieveMono(OrderReceipt.class);
    }
}
~~~

In this example:

1. `dataMimeType(application/json)` declares the connection's **data** format when building the requester.
2. `metadataMimeType(composite)` specifies how **metadata**, including routing entries, is packed.
3. `route("orders.create")` sets the logical target for the request; it does **not** change the data MIME type.
4. `data(order)` instructs Spring to find a JSON encoder matching `CreateOrder`.
5. `retrieveMono(OrderReceipt.class)` instructs the client to decode the reply as `OrderReceipt`.

If both server and client use compatible JSON strategies, the expected response is:

~~~json
{"orderId":"ORD-102","state":"ACCEPTED"}
~~~

This is the **expected output**, not an executed test result in the repository.

## 7. Changing the data format: what must change?

Suppose one route accepts plain text strings instead of JSON DTOs. On a **dedicated `text/plain` connection**, the client can create a separate requester:

~~~java
RSocketRequester textRequester = builder
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .tcp("localhost", 7000);

Mono<String> result = textRequester
    .route("echo.text")
    .data("Hello RSocket")
    .retrieveMono(String.class);
~~~

And the server defines a matching handler:

~~~java
@MessageMapping("echo.text")
Mono<String> echo(String text) {
    return Mono.just("Received: " + text);
}
~~~

This example only works if the server accepts `text/plain` and has a matching String codec. It demonstrates **a separate connection**, not switching codecs per request on an existing JSON connection. If the application does not support `text/plain` on that endpoint, configure the codec or use a server-supported format.

### Custom codecs and vendor MIME types

When a system adopts `application/vnd.example.order+json`, share that MIME type agreement with all clients. If you need to register a codec explicitly for it:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Configuration
class OrderVendorJsonCodecConfiguration {

    private static final MimeType ORDER_JSON =
        MimeTypeUtils.parseMimeType("application/vnd.example.order+json");

    @Bean
    RSocketStrategiesCustomizer orderVendorJson(ObjectMapper mapper) {
        return builder -> {
            builder.encoder(new Jackson2JsonEncoder(mapper, ORDER_JSON));
            builder.decoder(new Jackson2JsonDecoder(mapper, ORDER_JSON));
        };
    }
}
~~~

The client must declare `dataMimeType(ORDER_JSON)` and both sides must have encoders/decoders capable of handling the data. Jackson may already support certain `+json` MIME types out of the box; **check existing codecs before adding more** to avoid overlapping registrations. For Protobuf, CBOR, or custom binary formats, register codecs built for those formats—never swap MIME names to reuse a JSON codec.

## 8. Codecs across RSocket interaction models

RSocket has four common interaction models:

| Interaction | How is data processed? | Example |
| --- | --- | --- |
| Request-response | Encode one request; decode one reply | `orders.create` |
| Fire-and-forget | Encode request; expect no business response payload | `inventory.changed` |
| Request-stream | Encode request; decode multiple reply elements | `orders.events` |
| Request-channel | Encode/decode bidirectional element streams | `orders.sync` |

With request-stream, you may see:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.events")
    .data(new OrderQuery("ORD-102"))
    .retrieveFlux(OrderEvent.class);
~~~

Each `OrderEvent` element is handled by the decoder per the stream's contract. **Backpressure** regulates element emission/consumption rates; it does not fix MIME mismatches or schema errors. You must bound element counts, payload sizes, and accumulated memory. Protocol framing/fragmentation also does not allow application parsers to accept arbitrarily huge payloads.

When placing Spring Integration behind RSocket, clarify whether the flow operates on **one DTO**, a set of DTOs, or a **Publisher**; never collect an infinite stream into a `List` just to cross a synchronous gateway. Align the interaction model, codecs, and message flow design in the contract upfront.

## 9. Codecs and IntegrationFlow message contracts

Three layers hold distinct responsibilities:

| Layer | Input/output | Key checks |
| --- | --- | --- |
| RSocket | Bytes and metadata per SETUP | Declared format, interaction model, routing |
| Spring Messaging + codec | Bytes ↔ Java DTO | Matching encoders/decoders and schemas |
| Spring Integration | `Message<?>` via channels and flows | Business contract, transforms, routing, reply/error |

Once the RSocket decoder creates a DTO, the Spring Integration message **payload** can be that decoded object. Headers for correlation, tracing, or tenant context can accompany it when metadata mapping is configured. Do not repeat JSON parsing code in every `ServiceActivator` when boundary codecs already deliver the right DTO.

A clear contract for route `orders.create` should document:

| Item | Example value |
| --- | --- |
| Route | `orders.create` |
| Interaction | Request-response |
| Data MIME type | `application/json` |
| Request DTO | `CreateOrder(orderId, quantity)` |
| Reply DTO | `OrderReceipt(orderId, state)` |
| Metadata MIME type | `message/x.rsocket.composite-metadata.v0` |
| Validation rules | `orderId` non-blank, `quantity > 0` |
| Contract errors | Codec failure, invalid JSON, invalid data |
| Compatibility | Rules for adding/renaming fields and DTO versioning |

Upgrading payloads from JSON to Protobuf changes the **codec, schema, and SETUP** contract—not just a route name. With independently deployed clients, maintain compatible endpoints/connections for older versions during migration.

## 10. Codec-focused testing

A useful test suite checks both bytes crossing RSocket and the values actually received by the `IntegrationFlow`:

1. **Valid JSON:** send `CreateOrder("ORD-102", 3)` and receive `OrderReceipt` with expected fields; verify the handler receives the DTO rather than a raw JSON string.
2. **Payload missing required field:** send JSON without `orderId`; define clearly whether validation/mapping allows null or rejects, and assert the expected outcome.
3. **JSON type mismatch:** send `quantity: "abc"`; verify decoding fails and confirm `IntegrationFlow` never runs order creation logic.
4. **Malformed JSON syntax:** send non-JSON bytes under `application/json`; verify the decoder error response.
5. **Unsupported MIME type:** use a requester declaring `text/plain` and send a JSON-only DTO; assert the expected encode or decode error.
6. **Reply schema mismatch:** have the client request `OrderReceipt` while the server returns an incompatible structure; verify client-side decode failure.
7. **Non-JSON formats:** when supporting vendor JSON or Protobuf, send real payloads over a connection with matching SETUP; verify both sides read them cleanly.
8. **Size limits:** test oversized payloads and verify behavior when exceeding configured codec/buffer limits.

With Reactor, `StepVerifier` checks `onNext`, `onComplete`, and `onError` signals. Tests calling Java handlers directly **cannot verify** encoding/decoding or data MIME declarations. At least one integration test group must go through `RSocketRequester` and a production-like responder.

## 11. Troubleshooting: common errors

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Client fails to encode `CreateOrder` | Missing JSON encoder or wrong data MIME type | Check `RSocketStrategies`, builder MIME, and Jackson on classpath |
| Server fails to decode request | Malformed JSON, wrong MIME, missing decoder, or incompatible DTO | Check wire bytes, schema, `@MessageMapping` signature, and codecs |
| Server succeeds yet client fails in `retrieveMono` | Reply mismatches `OrderReceipt` or client lacks decoder | Check response schema and target class |
| `orders.create` finds no handler | Wrong route/routing metadata | Check route and metadata MIME type; distinct from JSON errors |
| Flow receives `String` instead of `CreateOrder` | Handler expects `String` or an extra converter runs | Define exact parameter types and inspect DTO-to-channel handoff |
| One client succeeds with JSON, another fails | Mismatched SETUP MIME, codecs, schemas, or DTO versions | Compare both client configs against the server contract |
| Large payloads cause memory or buffer errors | Missing size limits or buffering design | Enforce codec/transport limits; use streaming/business chunking |
| Sending `application/x-protobuf` produces unreadable results | Protobuf codec/schema not installed | Register real Protobuf codecs and align schemas on both sides |

When isolating issues, trace in order: **SETUP MIME → sender encoder → wire bytes → receiver decoder → DTO type → IntegrationFlow → reply encoder → client decoder**. Separate payload issues from routing, metadata, and validation issues so you fix the right layer.

Do not log raw payload bytes in production when they contain PII, tokens, or sensitive business data. Log route, MIME type, correlation ID, payload length, and sanitized error codes instead.

## 12. Practice exercises

### Exercise A — Observing DTOs at the RSocket boundary

Complete the `orders.create` example and add a check confirming the payload received by `IntegrationFlow` is `CreateOrder` with `quantity == 3`. Compare with temporarily changing the handler parameter to `String`. Explain why the parameter type drives decoding.

### Exercise B — Adding a text route

Create `echo.text` with a requester using `text/plain` returning a `String`. Write separate tests for the JSON connection and the text connection. Explain why you cannot arbitrarily switch `dataMimeType` per route on the same existing RSocket connection under default SETUP semantics.

### Exercise C — Contract and compatibility errors

Write tests intentionally sending type-mismatched JSON, sending a DTO with an incompatible MIME type, and requesting a response class with a mismatched schema. For each test, identify whether the failure occurs **before sending**, **during server decoding**, **inside IntegrationFlow**, or **when the client decodes the reply**.

## 13. Key takeaways

- RSocket transmits bytes; **codecs** convert between bytes and application values.
- **Data MIME type** is declared in SETUP and governs how connection data is interpreted. **Metadata MIME type** governs how routes and other metadata are interpreted.
- JSON DTOs pass through an encoder on the sender and a decoder on the receiver; replies follow the reverse encode/decode path.
- Spring RSocket uses `RSocketStrategies` to manage codecs. Setting the right MIME type is not enough if either side lacks the codec or has an incompatible schema.
- Spring Integration should accept decoded payloads at the RSocket boundary and focus on business processing through `MessageChannel` and `IntegrationFlow`. Tests must traverse real RSocket connections to catch codec errors that pure-Java handler unit tests miss.
