# Metadata and routes in RSocket Adapter

## 1. Context and objectives

In Spring Integration, adapters and gateways connect internal processing flows with external systems. With **RSocket**, a single connection can serve multiple operations such as creating orders, checking status, or receiving event streams. To send a request to the right target, the client sends a **route**; to pass contextual information such as tenant, trace, or authentication details, the client uses **metadata**.

This lesson belongs to the **RSocket Adapter** chapter of module **SPRING_INTEGRATION_ADAPTERS**: connecting external systems with Spring Integration using inbound/outbound adapters, gateways, and `MessageChannel`; designing message contracts, error handling, and connection lifecycles. The scope of this lesson is how routes and metadata cross the RSocket boundary to reach a Spring Integration flow, without diving deep into TCP/WebSocket transport configuration or connection operations.

After this lesson, you can:

- Distinguish **route**, **metadata**, and **data/payload** in an RSocket request.
- Understand why routes usually reside in routing metadata, and when composite metadata is needed.
- Map decoded metadata into Spring Message headers before processing with `IntegrationFlow`.
- Design clear routes, validate contracts, detect route/metadata errors, and avoid trusting client-asserted metadata.

## 2. What is a route?

RSocket supports multiple interactions over the same connection. The client must specify the operation the server should perform. A **route** is a logical destination name, for example:

| Route | Meaning | Example interaction |
| --- | --- | --- |
| `orders.create` | Send order creation request | Request-response |
| `orders.status` | Fetch status of an order | Request-response |
| `orders.events` | Watch order events | Request-stream |
| `inventory.changed` | Notify inventory changed | Fire-and-forget |

A route is **not** an HTTP URL, filesystem path, or Java method name. It is a value agreed upon by client and server. With Spring Messaging RSocket, a route can match `@MessageMapping("orders.create")`; with Spring Integration, the RSocket inbound/outbound gateway moves requests into or out of the message flow per adapter configuration.

Conceptual example of a request:

~~~text
RSocket request-response
  route metadata: "orders.create"
  extra metadata: tenant = "shop-a"
  data (JSON):   {"orderId":"A-100","quantity":2}
~~~

The server selects the handler by route, then processes the payload and any required metadata. Do not force the server to inspect an `action` field inside JSON just to find the handler when RSocket already provides routing.

### How is a route carried?

RSocket has two data sections in a payload at the protocol level: **data** and **metadata**. When routing is used, the route is encoded inside **routing metadata** (standard MIME `message/x.rsocket.routing.v0`). This is an RSocket structured format, not an HTTP header and not an arbitrary JSON string.

In Spring, the call:

~~~java
requester.route("orders.create")
         .data(request)
         .retrieveMono(OrderAck.class);
~~~

sends the route in the format supported by the RSocket requester and configured metadata strategies. The `data(request)` part remains the business payload. A route does not determine the payload type or interaction style; both must be agreed upon in the endpoint's contract.

## 3. Metadata: information about the request, distinct from payload

Metadata tells the receiver **how** to process the request; the payload holds the **business data** to process. For example:

| Information | Where placed? | Reason |
| --- | --- | --- |
| `orders.create` | Routing metadata | Selects processing target |
| `orderId`, `quantity` | Data/payload | Business content |
| `tenantId` | Agreed custom metadata | Provides tenant context; must be verified on the server |
| Trace/correlation ID | Metadata or mapped header | Correlates logs/tracing across systems |
| Access token | Authentication metadata per security mechanism | Authentication, authorization; never log sensitive values |

During connection setup (**SETUP**), both sides negotiate the MIME types of data and metadata, such as JSON data and **composite metadata**. The data MIME type guides the codec encoding/decoding payloads; the metadata MIME type guides parsing the metadata section.

Values to distinguish:

| MIME type | Role |
| --- | --- |
| `application/json` | Common format for the data section |
| `message/x.rsocket.routing.v0` | Format for a routing metadata entry |
| `message/x.rsocket.composite-metadata.v0` | Container holding multiple metadata entries, each with its own MIME type |
| `text/plain` | Can be used for string metadata when both sides agree on interpretation |

**Composite metadata** is especially useful when a request needs a route alongside tenant ID, trace context, or authentication metadata:

~~~text
RSocket metadata (composite)
  ├─ entry MIME: message/x.rsocket.routing.v0 → "orders.create"
  └─ entry MIME: text/plain                 → "shop-a"

RSocket data (JSON)
  └─ {"orderId":"A-100","quantity":2}
~~~

Note: this diagram shows the **meaning** of entries, not actual wire bytes. RSocket metadata is binary-encoded per its MIME type and codec. Metadata sent with **SETUP** applies to the connection setup phase; metadata sent per **request** is bound to that specific interaction. If one connection serves multiple tenants, tenant context must be determined per request—never implicitly inferred from a previous request.

## 4. From route and metadata to Spring Integration

Sample flow:

~~~mermaid
flowchart LR
    A["Client RSocketRequester<br/>route + metadata + data"] --> B["RSocket responder"]
    B --> C["Decode route<br/>and metadata"]
    C --> D["@MessageMapping<br/>or RSocket inbound gateway"]
    D --> E["Spring Message<br/>payload + headers"]
    E --> F["MessageChannel"]
    F --> G["IntegrationFlow<br/>business processing"]
    G --> H["Reply / error"]
    H --> A
~~~

There are two common integration approaches:

1. **Spring Messaging at the RSocket boundary:** `@MessageMapping` selects the route; `@Header` reads extracted metadata; a Spring Integration messaging gateway accepts `Message<?>` and forwards it to a `MessageChannel`. The example in the next section uses this approach because the exact metadata mapping point is easy to observe.
2. **Spring Integration RSocket gateway/adapter:** an RSocket inbound gateway brings external requests into the flow; an outbound gateway sends requests from the flow to an RSocket peer. Routes and metadata propagation must be configured using the API of your **Spring Integration version**; business handlers still receive a Spring Message with payload and headers.

Crucially, **RSocket metadata does not automatically become every header in Spring Integration**. Spring must know how to extract each metadata entry. Only after extraction into a Spring Messaging header can the value pass into Spring Integration's `MessageHeaders`. Sharing a header name does not guarantee shared semantics unless sender and receiver agree on MIME type, data type, and validation.

## 5. End-to-end example: route `orders.create` and metadata `tenantId`

Suppose the client creates an order with a JSON request and passes the tenant ID separately in metadata. The server passes the request into an `IntegrationFlow` and returns `OrderAck`. This illustrative example targets **Spring Boot 3 / Spring Framework 6 and Spring Integration 6**, using Spring Messaging RSocket as the inbound boundary. Corresponding dependencies can be used:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

Declare the RSocket TCP server in `application.yml`:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

### Step 1: Define the data contract

~~~java
public record OrderRequest(String orderId, int quantity) {}

public record OrderAck(String orderId, String status) {}
~~~

These are two illustrative DTO types; place them in appropriate Java files. Client and server must agree on JSON structure and field meanings. Route `orders.create` corresponds to a request-response interaction returning a single `OrderAck`.

### Step 2: Register metadata extraction

Spring must know that a metadata entry with MIME `text/plain` should be decoded as a string and exposed as header `tenantId`:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.MimeTypeUtils;

@Configuration
class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategiesCustomizer tenantMetadataExtractor() {
        return strategies -> strategies.metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                MimeTypeUtils.TEXT_PLAIN,
                String.class,
                "tenantId"
            )
        );
    }
}
~~~

Here `text/plain` is used **only to keep the example simple**. When carrying multiple kinds of text metadata, define distinct MIME types for each, register matching codecs/extractors on both sides, and avoid ambiguity between entries. Without the extractor, the route may still match, yet `@Header("tenantId")` will have no value.

### Step 3: Send a Spring Message into IntegrationFlow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@MessagingGateway
interface OrderFlowGateway {
    @Gateway(requestChannel = "ordersInput")
    OrderAck submit(Message<OrderRequest> request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersInput")
            .handle(OrderRequest.class, (order, headers) -> {
                String tenantId = (String) headers.get("tenantId");

                if (tenantId == null || tenantId.isBlank()) {
                    throw new IllegalArgumentException("Missing tenantId");
                }
                if (order.quantity() <= 0) {
                    throw new IllegalArgumentException("quantity must be > 0");
                }

                // Demo: in a real system, check tenant access permissions
                // and call order creation service before returning ACK.
                return new OrderAck(order.orderId(), "ACCEPTED");
            })
            .get();
    }
}
~~~

The `submit(Message<OrderRequest>)` method carries **both payload and headers** into Spring Integration. The handler receives `OrderRequest` as payload while accessing `tenantId` from `MessageHeaders`. If you pass only the DTO instead of `Message<OrderRequest>` without forwarding headers, you lose the metadata just extracted at the RSocket boundary.

### Step 4: RSocket responder connects the route to the flow

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class OrderRSocketController {
    private final OrderFlowGateway gateway;

    OrderRSocketController(OrderFlowGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("orders.create")
    Mono<OrderAck> create(
            @Payload OrderRequest request,
            @Header("tenantId") String tenantId) {

        Message<OrderRequest> message = MessageBuilder
            .withPayload(request)
            .setHeader("tenantId", tenantId)
            .build();

        // The messaging gateway in this example is synchronous. Offload processing
        // to boundedElastic to avoid blocking the RSocket event loop.
        return Mono.fromCallable(() -> gateway.submit(message))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`@MessageMapping` selects the handler by route; `@Header("tenantId")` reads the value extracted from RSocket metadata; `MessageBuilder` passes that value into the Spring Integration message. Crucial rule: **do not treat a client-declared tenant ID as proof of authorization**. Pair it with an authenticated principal/token and server-side authorization policies before reading or writing tenant data.

### Step 5: Client sends the route and extra metadata

In the client application, once the server is running on port 7000:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

class OrderRSocketClient {
    private final RSocketRequester requester;

    OrderRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    Mono<OrderAck> create(OrderRequest request, String tenantId) {
        return requester.route("orders.create")
            .metadata(tenantId, MimeTypeUtils.TEXT_PLAIN)
            .data(request)
            .retrieveMono(OrderAck.class);
    }
}
~~~

Spring's `RSocketRequester` typically uses **composite metadata** to carry the route alongside other metadata entries. If configuring metadata MIME types/strategies manually, ensure client and server agree on the chosen format. Never assume every non-Spring RSocket peer automatically decodes routes or custom metadata the same way Spring does.

The expected output when sending `OrderRequest("A-100", 2)` with `tenantId = "shop-a"` is:

~~~json
{"orderId":"A-100","status":"ACCEPTED"}
~~~

This is the expected output of the example, not an actual execution log. If tenant metadata is omitted or sent with the wrong MIME type, the server may fail to populate the `tenantId` header and the request must be rejected per contract.

## 6. Distinguishing three layers of information in the flow

| Layer | Components | Examples | Responsibility |
| --- | --- | --- | --- |
| RSocket wire protocol | Data + metadata entries | JSON, routing, text metadata | Transport over TCP/WebSocket per RSocket interactions |
| Spring RSocket/Messaging | Route, decoded payload, extracted headers | `@MessageMapping`, `@Header` | Decoding, handler selection, message conversion |
| Spring Integration | `Message<?>` / `MessageHeaders` | `ordersInput`, `IntegrationFlow` | Internal routing, transformation, processing, reply/error |

Do not conflate these three concepts:

- **RSocket route**: operation name at the connection boundary, e.g., `orders.create`.
- **Spring Integration channel name**: internal flow address, e.g., `ordersInput`.
- **Metadata/header**: request context, e.g., `tenantId` or `traceId`.

Both routes and channels direct processing, yet belong to different layers. You can rename an internal channel while keeping the public route unchanged. Similarly, RSocket metadata needs an extractor/mapper to enter headers, and metadata sent outward over RSocket must be explicitly configured/serialized; not every internal header is emitted automatically.

## 7. Designing routes and metadata contracts

A maintainable naming convention is `<domain>.<action>`, such as `orders.create`, `orders.status`, and `inventory.reserve`. When supporting multiple contract versions, agree on routes like `v1.orders.create` or `orders.v2.create`. Never change the payload semantics of a route already used by clients without a compatibility plan.

Document each route with these fields:

| Contract field | Example for `orders.create` |
| --- | --- |
| Route | `orders.create` |
| Interaction | Request-response |
| Data MIME / request type | JSON / `OrderRequest` |
| Reply | `OrderAck` |
| Required metadata | Extracted `tenantId`; authentication details per chosen mechanism |
| Error rules | Missing metadata, invalid payload, unauthorized tenant, business failure |
| Repeatability | Clarify duplicate `orderId` handling and idempotency policy |

In practice, route names should stay stable over time; dynamic values like `orderId` or `tenantId` generally belong in payloads/metadata rather than spawning unbounded distinct routes. If using route templates or destination variables in `@MessageMapping`, verify how your framework version matches patterns and binds variables.

## 8. Routes do not dictate the interaction model

| RSocket model | What the client expects | Example route |
| --- | --- | --- |
| Request-response | One result or error | `orders.create` |
| Fire-and-forget | No business response | `inventory.changed` |
| Request-stream | Multiple streamed response elements | `orders.events` |
| Request-channel | Both sides exchange streams of elements | `orders.sync` |

Two routes may look similar in name while having completely different interaction contracts. For streams/channels, pay special attention to **backpressure**, cancellation, and bridging Reactor Publishers with Spring Integration channels/handlers. Do not use a blocking synchronous gateway to handle an infinite request-stream. The `orders.create` example above is intentionally limited to request-response.

## 9. Verifying routes and metadata

A meaningful test suite should traverse the real RSocket boundary or an equivalently configured test responder:

1. **Happy path:** send `orders.create`, valid payload, and valid tenant metadata; verify `ACCEPTED` response and prove the header reached the flow.
2. **Missing metadata:** omit `tenantId`; the handler must not silently assume a default tenant. Verify the error returned and client handling.
3. **Wrong MIME type:** send tenant under a MIME type with no registered extractor; verify the server does not guess a wrong header.
4. **Wrong route:** send `orders.unknown`; the server must report an appropriate routing error without falling back to another flow.
5. **Invalid payload:** send an invalid quantity or malformed JSON schema; conversion/validation errors must be clearly observed.
6. **Unauthorized tenant:** self-declared metadata must never grant access when the principal lacks permission.
7. **Multiple requests on the same connection:** interleave different tenants/traces, ensuring headers on each request remain strictly isolated.

With reactive test clients, Reactor's `StepVerifier` can verify values and `onError` signals. In operations, log the route, correlation ID, and sanitized error codes; mask tokens, passwords, and sensitive fields. Across multiple integration flows, explicitly retain only needed headers rather than dumping all external metadata into logs or outbound adapters.

## 10. Common errors and isolation steps

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| No handler found for request | Wrong client route or `@MessageMapping` mismatch | Compare exact route names and registered responder beans |
| Route matches yet `tenantId` is missing | Missing extractor; wrong MIME; client forgot extra metadata | Inspect composite metadata, entry MIME, and metadata extractor config |
| Payload does not decode to DTO | Incompatible codec/data MIME or JSON schema | Verify data format, DTO class, and codecs on both sides |
| Flow receives payload but loses context | Passed only DTO, dropped `MessageHeaders` | Use Spring `Message<?>` or explicit header mapping |
| Request-response never completes | Handler returns no reply, blocks, or flow hangs | Check reply path, timeouts, and appropriate schedulers |
| User accesses wrong tenant's data | Trusted client-sent `tenantId` as verified identity | Authorize on server via principal/token and allowed tenants |
| Metadata works with Spring client but fails with other peer | Peer does not share metadata MIME/codecs | Align composite metadata, routing entries, custom MIMEs, and protocol version |

To diagnose, check **layer by layer in order**: RSocket connection → MIME/setup → routing metadata → extractor/header → Spring Messaging handler → Spring Integration channel/flow → reply. Do not look only at the JSON payload, because routes and metadata do not necessarily appear inside JSON.

## 11. Practice exercises

**Exercise A — Add a trace ID:** Add `traceId` metadata to `orders.create`. Register an appropriate extractor, pass the value into a Spring Message header, and log the correlation ID without logging sensitive content. Verify two consecutive requests carry distinct trace IDs.

**Exercise B — New route:** Create route `orders.status` with request-response, payload containing `orderId` and reply containing `orderId`, `status`. You may share a `MessageChannel` or split channels by responsibility, but clearly document the route → flow mapping.

**Exercise C — Contract testing:** Write tests for a non-existent route, missing tenant metadata, negative quantity, and unauthorized tenant access. Passing criteria: invalid cases are visibly rejected without triggering unintended business processing.

### Key takeaways

An RSocket request typically carries **the route in metadata**, **the payload in data**, plus **additional metadata entries** when needed. At the Spring boundary, decode and validate metadata before turning it into headers; then use `MessageChannel` and `IntegrationFlow` for business processing. Routes are the client contract while channels are internal design; keeping the two layers separate makes systems easier to evolve and test.
