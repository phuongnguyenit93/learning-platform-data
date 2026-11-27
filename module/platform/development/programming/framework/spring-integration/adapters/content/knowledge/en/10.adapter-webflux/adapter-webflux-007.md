# Request-Response Mapping in Spring Integration WebFlux

## 1. What Does Request/Response Mapping Mean?

When connecting two systems over HTTP, data crosses between two different models: **HTTP request/response** and **Spring Integration `Message<?>`**. *Mapping* refers to the rules determining which parts of an HTTP request become message payload/headers and which parts of a reply message become the HTTP status, headers, and body. If mapped incorrectly, steps in the `IntegrationFlow` can receive the wrong data type, lose correlation IDs, return improper status codes, or accidentally leak internal information.

This lesson belongs to the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module covers using inbound/outbound adapters, gateways, pollers, and `MessageChannel`s to connect files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, while practicing message contracts, error handling, and connection lifecycles. Here we focus on **the HTTP boundary of Spring Integration WebFlux**: receiving HTTP from outside and calling HTTP to external systems.

Example: an API receives JSON order-check requests. A Spring Integration WebFlux inbound gateway reads the request, converts it into a `Message<OrderCheckRequest>`, invokes an internal handler, and sends `OrderCheckResponse` back to the client as JSON. When a flow needs to query a partner's API, a WebFlux outbound gateway handles the reverse direction.

~~~mermaid
flowchart LR
    A["HTTP client"] -->|"request: method, path, headers, body"| B["WebFlux inbound gateway"]
    B -->|"Message<OrderCheckRequest>"| C["MessageChannel"]
    C --> D["Business handler"]
    D -->|"Reply Message<OrderCheckResponse>"| B
    B -->|"response: status, headers, body"| A
~~~

**Distinguishing direction and contract:** *inbound* means HTTP calls **into** the application; *outbound* means the flow calls HTTP **outward**. A *channel adapter* transfers data primarily one-way, whereas a *gateway* implements a **request-reply** contract, returning a business result to the caller.

## 2. Four WebFlux Components in the Mapping Model

| Spring Integration component | What is the request mapped into? | What is the response used for? |
|---|---|---|
| **WebFlux inbound channel adapter** | HTTP request → Spring Integration message on input channel | Sends HTTP acceptance status code; does not fetch a business reply from the flow |
| **WebFlux inbound gateway** | HTTP request → request message with reply context | Reply message → HTTP status, response headers, and body |
| **WebFlux outbound channel adapter** | Internal message → HTTP request via `WebClient` | Response handled per HTTP contract and error handling; produces no business reply for the flow |
| **WebFlux outbound gateway** | Internal message → HTTP request via `WebClient` | HTTP response → reply message for downstream |

Both gateways perform request-reply mapping, differing in which side initiates the HTTP exchange:

~~~mermaid
flowchart TB
    subgraph IN["Inbound gateway"]
        X["External HTTP request"] --> Y["Request message"]
        Y --> Z["Reply message"]
        Z --> W["External HTTP response"]
    end
    subgraph OUT["Outbound gateway"]
        A["Request message"] --> B["Outbound HTTP request"]
        B --> C["HTTP response from partner"]
        C --> D["Reply message"]
    end
~~~

In practice, these adapters/gateways run on WebFlux infrastructure with HTTP readers/writers and codecs, yet a `DirectChannel`, `QueueChannel`, or synchronous JDBC service in the same flow does not automatically become non-blocking.

## 3. Mapping Map from HTTP Request to Message

An HTTP request has multiple parts: URL/path, query parameters, method, headers, body, and security context. Not every part automatically becomes a field in a business DTO.

| HTTP request | In Spring Integration | Notes |
|---|---|---|
| `POST /api/orders/check` | Endpoint selected by request mapping | Path/method must match before creating a message |
| `Content-Type: application/json` | Codec decides how to read the request body | Wrong media type may be rejected |
| JSON body `{"orderId":"ORD-1001"}` | `OrderCheckRequest` payload when `requestPayloadType` is configured | Decoder does not replace business data validation |
| `X-Correlation-Id` | Message header if permitted by header mapper | Never treat untrusted IDs as authentication proof |
| `?verbose=true` | Request parameters, mappable to metadata/payload depending on endpoint | Does not automatically appear as a JSON DTO field |
| Path variable `/orders/{orderId}` | Path variable info can be exposed via request metadata/mapper | Must explicitly map into payload when business logic needs it |
| `Authorization` header | Belongs to authentication layer; may exist in HTTP headers | Never forward sensitive tokens indiscriminately into every message/downstream |

For inbound WebFlux, the typical sequence includes:

1. **Route matching:** WebFlux locates the endpoint by path and method, `consumes`, `produces`, and params/headers constraints if specified.
2. **Decode:** HTTP message reader/codec reads the body; `requestPayloadType` specifies the target payload type for conversion.
3. **Create Message:** Spring Integration builds a message with the payload and mapped metadata.
4. **Dispatch:** The message is sent to `MessageChannel`; with a gateway, reply context is included.
5. **Reply:** downstream produces a reply; the gateway serializes the reply into an HTTP response per status/headers/body rules.

**Common pitfall:** `requestPayloadType(OrderCheckRequest.class)` only guides **body decoding**; it does not extract `orderId` from the URL to populate the DTO, nor guarantee the field is non-empty. Validation and data transformation steps must be explicitly designed.

## 4. Endpoint Mapping: Path, HTTP Method, Consumes, Produces

In Spring Integration Java DSL, `WebFlux.inboundGateway(...)` or `WebFlux.inboundChannelAdapter(...)` exposes an inbound HTTP endpoint; `requestMapping(...)` declares request selection criteria.

Inbound gateway configuration snippet:

~~~java
WebFlux.inboundGateway("/api/orders/check")
    .requestMapping(mapping -> mapping
        .methods(HttpMethod.POST)
        .consumes(MediaType.APPLICATION_JSON_VALUE)
        .produces(MediaType.APPLICATION_JSON_VALUE))
    .requestPayloadType(OrderCheckRequest.class)
~~~

Meaning:

- Fixed **path** `/api/orders/check` is the URL called by HTTP clients.
- **HTTP method** `POST` rejects other methods on this route per WebFlux mechanics.
- **Consumes** `application/json` requires the request's `Content-Type` to match the mapping.
- **Produces** `application/json` declares the response format the route can emit; it participates in content negotiation with the client's `Accept` header.
- **Request payload type** picks the Java type for the codec converting the HTTP body.

Typical routing/codec error outcomes when no custom exception handling is configured:

| Client request | Typical outcome | Cause |
|---|---|---|
| `GET /api/orders/check` | `405 Method Not Allowed` if path exists with another method | Does not match `POST` |
| `POST` with `Content-Type: text/plain` | `415 Unsupported Media Type` | Does not match `consumes` |
| `POST` with `Accept: text/plain` | `406 Not Acceptable` when requested media type cannot be produced | Does not match `produces`/codecs |
| `POST` with malformed JSON | Typically `400 Bad Request` | Codec failed reading body |
| Unmapped URL | `404 Not Found` | No matching route |

The status codes in the table reflect typical WebFlux behavior without custom error handling; actual behavior depends on version, security filters, exceptions, and application setup. Do not treat them as absolute rules for every project.

## 5. Payload: JSON, DTO, String, and Reactive Publisher

An HTTP body has no inherent Java type. For JSON objects, you can map to Java records:

~~~java
public record OrderCheckRequest(String orderId) { }
public record OrderCheckResponse(String orderId, String status) { }
~~~

With `requestPayloadType(OrderCheckRequest.class)`, the WebFlux codec reads JSON into an `OrderCheckRequest` payload. For plain text bodies, pick `String.class`. For binary, multipart, or streaming data, configure appropriate readers/types; never assume the JSON codec handles every format.

**Two distinct message shapes:**

~~~text
Message<OrderCheckRequest>
  payload: OrderCheckRequest(orderId="ORD-1001")

Message<Flux<OrderEvent>>
  payload: Flux<OrderEvent>    // one message holding a publisher
~~~

`Message<Flux<OrderEvent>>` is not equivalent to `Flux<Message<OrderEvent>>`. In the first case, downstream receives one message whose payload is a publisher; to handle each event as its own message, add an appropriate consumer/splitter. For streaming request bodies, you can declare `ResolvableType.forClassWithGenerics(Flux.class, OrderEvent.class)`, provided codecs and the client's HTTP media type support streaming.

Dedicated example for a streaming request:

~~~java
import org.springframework.core.ResolvableType;
import reactor.core.publisher.Flux;

// Configuration snippet for a WebFlux inbound endpoint:
.requestPayloadType(
    ResolvableType.forClassWithGenerics(
        Flux.class, OrderEvent.class))
~~~

This is a configuration snippet, not a complete Java flow. When using `Flux`, determine who subscribes and how errors and cancellations are handled; merely sending a `Flux` into a `QueueChannel` does not cause the queue to read individual items from the publisher.

## 6. Complete Inbound Gateway: JSON Request → JSON Reply

### 6.1. Dependencies

With Spring Boot, use Boot's BOM to manage compatible Spring Integration and Spring Framework versions.

~~~groovy
// build.gradle — dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
}
~~~

In Spring Boot using WebFlux auto-configuration, manually adding `@EnableWebFlux` is usually unnecessary. If both Spring MVC and WebFlux are present, verify which web application type is selected.

### 6.2. Java DSL: Explicit Request and Reply Mapping

The example below exposes `POST /api/orders/check`. The handler receives the decoded request and returns the corresponding DTO; the `X-Correlation-Id` header is preserved in the reply so it can be sent back in the HTTP response.

~~~java
package com.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderCheckHttpFlow {

    public record OrderCheckRequest(String orderId) { }
    public record OrderCheckResponse(String orderId, String status) { }

    @Bean
    public IntegrationFlow orderCheckInboundGateway() {
        return IntegrationFlow
            .from(WebFlux.inboundGateway("/api/orders/check")
                .requestMapping(mapping -> mapping
                    .methods(HttpMethod.POST)
                    .consumes(MediaType.APPLICATION_JSON_VALUE)
                    .produces(MediaType.APPLICATION_JSON_VALUE))
                .requestPayloadType(OrderCheckRequest.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id")
                .mappedResponseHeaders("X-Correlation-Id")
                .statusCodeFunction(message -> HttpStatus.OK)
                .replyTimeout(5_000))
            .handle((payload, headers) -> {
                OrderCheckRequest request = (OrderCheckRequest) payload;

                OrderCheckResponse response = new OrderCheckResponse(
                    request.orderId(), "PROCESSING");

                // Preserve gateway replyChannel/correlation context.
                return MessageBuilder.withPayload(response)
                    .copyHeaders(headers)
                    .build();
            })
            .get();
    }
}
~~~

**Reading the mapping stages:**

1. `inboundGateway` creates a request-reply endpoint, distinct from `inboundChannelAdapter` used for one-way ingestion.
2. `requestMapping` determines which HTTP requests can enter the flow.
3. `requestPayloadType` selects the codec and Java payload type.
4. `mappedRequestHeaders` maps only the required HTTP headers into the message. The example keeps `Content-Type` and `X-Correlation-Id`.
5. `statusCodeFunction` chooses `200 OK` for the example's **successful** response. It does not automatically turn every exception into `200`.
6. `mappedResponseHeaders` controls which reply headers may be written to the HTTP response.
7. `replyTimeout` caps how long the gateway waits for a reply under the messaging contract. It is not an outbound WebClient connection timeout.
8. `MessageBuilder.withPayload(...).copyHeaders(headers)` preserves reply/correlation context when constructing a new message manually. Never copy arbitrary headers from **untrusted** sources blindly into HTTP responses; outbound HTTP exposure must still be restricted via the header mapper.

**Why must reply context be preserved?** The gateway is waiting for a reply tied to the active HTTP request. If a handler constructs a new message and drops `replyChannel` and correlation info, the gateway may miss the result or wait until timeout. If a service activator simply returns a plain DTO, Spring Integration automatically builds the reply message and preserves needed headers; explicitly constructing a `Message` here makes that responsibility visible.

### 6.3. Testing with curl

~~~bash
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Correlation-Id: req-001' \
  -d '{"orderId":"ORD-1001"}'
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: req-001

{"orderId":"ORD-1001","status":"PROCESSING"}
~~~

The `X-Correlation-Id` header appears because the request mapper accepted it and the response mapper allowed emitting it. Actual byte-level HTTP responses depend on HTTP protocol, codecs, server, and custom filters; the example highlights the essential contract for learners.

## 7. Response Mapping: Status, Headers, Body, and Reply Channel

### 7.1. Status Code

The HTTP status must reflect the **outcome per the API contract**:

| Scenario | Common appropriate status | Meaning |
|---|---|---|
| Successful lookup with body | `200 OK` | Result returned |
| Resource created successfully | `201 Created` | Resource created, usually with `Location` |
| Request accepted for later processing | `202 Accepted` | Accepted for processing; not necessarily completed |
| Success with no body | `204 No Content` | No response body |
| Invalid request | `400 Bad Request` | Client-side format/data error |
| Resource not found | `404 Not Found` | Not found per contract |
| State conflict | `409 Conflict` | Conflicts with current resource state |
| Remote service unavailable | `502` / `503` / `504` depending on server role | Upstream/availability failure |

`statusCodeFunction(...)`/`statusCodeExpression(...)` on the inbound endpoint lets you configure the success status or derive it from the message context. When multiple outcomes exist, define explicit status mapping rules from replies/errors; do not assume `statusCodeFunction(m -> HttpStatus.OK)` works for errors too.

### 7.2. Response Body and Content-Type

With an inbound gateway, the reply payload is serialized by the HTTP writer/codec into a response body per `Content-Type`/`produces` and content negotiation. A DTO typically becomes JSON when Jackson codecs are configured. With a `Flux<T>` reply and `text/event-stream`, WebFlux streams elements over time. With `204 No Content`, the protocol specifies no response body.

Avoid serializing a DTO to a JSON string yourself and letting the JSON codec serialize it a second time: sending a `String` containing JSON under `application/json` improperly can deliver a double-escaped string rather than a JSON object. Prefer returning the DTO and letting the codec handle serialization; if sending raw bytes/text, declare the matching media type.

### 7.3. Response Headers

The header mapper governs metadata sent out over HTTP. Examples include `X-Correlation-Id` for log correlation, `Location` on resource creation, and `Cache-Control` for caching policies; emit only headers required by the contract. Never expose `replyChannel`, `errorChannel`, access tokens, or internal infrastructure details in responses.

If sitting behind a proxy/API gateway, some headers may be added or overwritten by upstream infrastructure. Tests should verify the **final HTTP response**, not just message headers inside the flow.

## 8. Mapping URI, Path Variables, and Query Parameters

WebFlux distinguishes three data regions:

~~~http
GET /api/orders/ORD-1001?includeHistory=true HTTP/1.1
Accept: application/json
X-Correlation-Id: req-002
~~~

- **Path variable** `ORD-1001` is part of the URI route; it can be bound from `{orderId}` in the request mapping.
- **Query parameter** `includeHistory=true` is a URL key/value pair, not a JSON body.
- **Header** `X-Correlation-Id` is metadata sent separately from the URI.

With plain REST controllers, `@PathVariable`, `@RequestParam`, and `@RequestHeader` bind directly to method parameters. **Spring Integration's WebFlux inbound gateway does not automatically run `@RestController` method-parameter binding**: it constructs a Spring Integration message per endpoint configuration. To use path/query data in the payload, extract request metadata supported by your version/header mapper and transform it into a DTO, or use an appropriate payload expression.

Some HTTP inbound endpoints fall back to request parameters as a `MultiValueMap<String, String>` when the payload expression yields no body. This behavior must be verified for your exact configuration; never assume every bodyless request automatically turns into `OrderCheckRequest`. For `GET` requests, explicitly define and test the data-extraction contract from path/query parameters.

Conceptual transformer flow:

~~~text
GET /api/orders/{orderId}?includeHistory=true
    -> request path/query metadata
    -> OrderLookupRequest(orderId, includeHistory)
    -> service activator
    -> OrderLookupReply
    -> HTTP JSON response
~~~

In exercises, identify **the exact header or payload source** emitted by the endpoint before writing SpEL/transformers. Never guess header names from URLs.

## 9. HeaderMapper: Keeping the Right Data and Protecting Trust Boundaries

Spring Integration provides an HTTP `HeaderMapper` mechanism to translate between HTTP headers and Spring Integration `MessageHeaders`. Common contract headers include:

| Header | Sender | Role in flow |
|---|---|---|
| `Content-Type` | Client → inbound / outbound → remote | Decode and encode HTTP body |
| `Accept` | Client → server | Select response media type |
| `Authorization` | Client or outbound HTTP client | Authentication; restrict copying across boundaries |
| `X-Correlation-Id` | Caller or trusted proxy | Logging/tracing, request/reply correlation |
| `Idempotency-Key` | Client per contract | Deduplicate create/update operations |
| `Location` | Resource-creating HTTP server | New resource URI, commonly with `201` |
| `Cache-Control` | Server → client | Response caching policy |

Do not treat every header as trustworthy: clients can forge `X-User-Id` or `X-Correlation-Id`. The header mapper restricts **which headers pass through**, while authentication/authorization and HMAC/mTLS verification must be handled separately.

### 9.1. Headers with Similar Names but Different Purposes

Distinguish:

1. **HTTP headers**: metadata of the HTTP exchange, e.g., `Content-Type`.
2. **Spring Integration message headers**: messaging metadata, e.g., `id`, `timestamp`, `replyChannel`, `errorChannel`.
3. **Business metadata**: e.g., `orderId`, `tenantId`, `eventId`; should have an explicit DTO or header contract.

Never copy all internal message headers onto an outbound HTTP request: you risk leaking infrastructure internals or colliding with proxy/security headers. Likewise, never let a remote HTTP response overwrite `replyChannel` or internal routing metadata unchecked.

## 10. Outbound Gateway: Message → HTTP Request → Reply Message

For an outbound gateway, the mapping direction flips: the flow supplies payload/headers to build an HTTP request; the remote service returns status/headers/body; the gateway turns the response into a message continuing downstream.

~~~mermaid
sequenceDiagram
    participant Source as Message producer
    participant Gateway as WebFlux outbound gateway
    participant Remote as Partner HTTP API
    participant Next as Downstream
    Source->>Gateway: Message<QuoteRequest> + headers
    Gateway->>Remote: POST JSON + mapped HTTP headers
    Remote-->>Gateway: HTTP 200 + JSON QuoteResponse
    Gateway->>Next: Message<QuoteResponse> + mapped response headers
~~~

### 10.1. Java DSL Example for Outbound Request/Response Mapping

~~~java
package com.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class PartnerQuoteOutboundFlow {

    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @Bean
    public WebClient partnerQuoteWebClient(WebClient.Builder builder) {
        return builder.build();
    }

    @Bean
    public IntegrationFlow partnerQuoteGateway(WebClient partnerQuoteWebClient) {
        return IntegrationFlow.from("quoteRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/quote",
                    partnerQuoteWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id")
                .mappedResponseHeaders("X-Partner-Request-Id"))
            .channel("quoteReplies")
            .get();
    }

    @ServiceActivator(inputChannel = "quoteReplies")
    public void handleQuote(QuoteResponse quote) {
        System.out.printf("Quote: %s -> %d %s%n",
            quote.orderId(), quote.shippingFeeVnd(), quote.currency());
    }
}
~~~

When sending a `Message<QuoteRequest>` with `Content-Type: application/json` to `quoteRequests`, the gateway issues an HTTP POST and uses `expectedResponseType(QuoteResponse.class)` to decode the JSON response. `mappedRequestHeaders`/`mappedResponseHeaders` govern which HTTP headers cross outbound/inbound at the boundary. `quoteReplies` receives a reply payload of type `QuoteResponse` when the exchange succeeds and codecs match.

In this example, `quoteRequests` is created implicitly by the DSL from the channel name; declare an explicit channel bean if you need custom executor, bounded capacity, or send policies.

**Limitation:** `MessageChannel.send(...)` returning `true` does not guarantee the HTTP exchange has completed, especially when the handler executes asynchronously. HTTP 4xx/5xx, network, timeout, or decoding errors can surface on the error path; do not assume downstream always receives `QuoteResponse`.

### 10.2. Capturing Both HTTP Status and Headers from the Remote

Normally, the reply payload is the decoded **response body**. When downstream needs `statusCode`, headers, and body together, the WebFlux outbound gateway supports `extractResponseBody(false)`:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .extractResponseBody(false))
~~~

This is a **DSL snippet**; when used, downstream must expect a `ResponseEntity<QuoteResponse>` payload (or a type matching the actual body), rather than casting directly to `QuoteResponse` as in the main example. On empty responses, reply creation depends on configuration and response type, so test `204 No Content`. Also, this option **does not turn HTTP 4xx/5xx into successful replies**: examine the handler's status/error handling behavior.

## 11. Mapping Reactive Responses: Mono, Flux, and SSE

A reactive HTTP service may return `Mono<T>`, yet the HTTP client only sees the HTTP response body after the `Mono` is subscribed and executed. An outbound gateway with `expectedResponseType(T.class)` typically creates a reply payload of type `T`, rather than putting `Mono<T>` onto the `MessageChannel`.

When the remote returns a stream (SSE or NDJSON) and downstream needs to consume items sequentially, the gateway can use `replyPayloadToFlux(true)`:

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/quote/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(QuoteUpdate.class)
    .replyPayloadToFlux(true))
~~~

The reply then carries payload `Flux<QuoteUpdate>`, meaning **a single message holding a publisher**. If each update must become a separate Spring Integration message, add an appropriate reactive consumer/splitter. A `Flux` does not split itself into thousands of messages merely because the flow uses a gateway.

On the inbound side, a WebFlux inbound gateway can accept a `Flux<T>` as the reply payload and write it out as an HTTP `text/event-stream` response:

~~~java
import java.time.Duration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow progressStream() {
    return IntegrationFlow
        .from(WebFlux.inboundGateway("/api/orders/progress")
            .requestMapping(m -> m.methods(HttpMethod.GET)
                .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
        .handle((payload, headers) -> Flux
            .just("RECEIVED", "PROCESSING", "COMPLETE")
            .delayElements(Duration.ofMillis(300)))
        .get();
}
~~~

This is a standalone alternative to the POST flow in Section 6. Test with `curl -N` to watch individual events; in production, plan for heartbeats, disconnects, proxy buffering, subscriber limits, and cancellation. Never assume a client closing SSE automatically rolls back work already dispatched to Kafka or a database.

## 12. Validation and Error Mapping

### 12.1. Decoding to a DTO Is Not Enough to Confirm Valid Data

For example, `OrderCheckRequest` can decode successfully from `{"orderId":null}` without proper validation. Separate:

- **Structural checks:** valid JSON, matching field types; typically handled by codecs.
- **Data validation:** `orderId` non-empty, proper length, no contract-violating characters.
- **Authorization:** caller is permitted to view that order.
- **Business rules:** order exists, state allows the action, no conflicts.

Spring Integration's WebFlux inbound endpoint supports integrating a `Validator`. Whether using Bean Validation or a custom validator, configure it so validation errors map to appropriate HTTP status/bodies. For publisher payloads, be clear on which elements validation runs on and at what stage.

### 12.2. Error Handling Matrix

| Error | Origin | Suggested handling |
|---|---|---|
| Wrong method/path/media type | WebFlux request mapping | HTTP 404/405/415/406 as applicable |
| Malformed JSON body | HTTP codec | HTTP 400 with safe message |
| Missing `orderId` | Validation | HTTP 400 or 422 per API contract |
| Order not found | Business handler | HTTP 404 if contract specifies |
| Insufficient permissions | Security/authorization | HTTP 401/403 depending on context |
| No reply produced | Gateway reply timeout | Timeout/error flow; HTTP status per configuration |
| Remote partner returns 5xx | Outbound gateway | Error flow, bounded retries, or appropriate error report |
| Codec cannot decode remote response | WebClient/codec | Record integration error, alert on schema drift |

Do not conflate HTTP errors **coming into the application** with errors when the application **calls outbound remotes**. Inbound gateways must return errors to their own callers; outbound gateways must classify partner errors and feed them into flow error handling.

`replyTimeout` on an inbound gateway limits waiting for a messaging reply; it is neither a TCP connect timeout nor an outbound WebClient `responseTimeout`. For flows crossing queues/pollers or brokers, examine message send times, reply reception, ACKs, and transaction boundaries.

### 12.3. A Testable Error Dispatching Flow

~~~text
HTTP POST /api/orders/check
  ├─ mapping/media type mismatch -> WebFlux route/codec error
  ├─ JSON decode failure -> HTTP 400
  ├─ validation failure -> contract-based error mapping
  ├─ service succeeds -> OrderCheckResponse reply -> HTTP 200 JSON
  ├─ not found -> business error -> HTTP 404 (when configured)
  └─ no reply -> timeout -> defined error flow/HTTP status
~~~

This is a **design model**; business error statuses do not appear automatically just by naming an exception. Configure error handlers, advice, or response mappers per your framework/version and test the full path.

## 13. Security and Preserving the Message Contract

When mapping HTTP into Spring Integration, enforce trust boundaries:

1. **Authenticate sources:** apply Spring Security, API keys, OAuth2/JWT, HMAC signatures, or mTLS per contract. Never treat a client-sent `X-User-Id` header as proof of identity.
2. **Choose header mappers carefully:** accept/emit only required headers. Never expose `replyChannel`, `errorChannel`, or internal details in HTTP responses or outbound requests.
3. **Prevent oversized data:** bound HTTP body size, codec buffers, concurrent requests, timeouts, queue capacities, and stream item counts.
4. **Correlation and idempotency:** propagate request IDs from trusted components for tracing; use idempotency keys when side-effecting operations may retry.
5. **Outbound URLs:** with dynamic URIs, pick remote hosts only from an allowlist; never turn arbitrary JSON payloads into URLs susceptible to SSRF.
6. **Sensitive data:** do not log raw `Authorization` headers, cookies, tokens, personal data, or full unnecessary request bodies.
7. **Content negotiation and CORS:** `produces/consumes` do not replace CORS or CSRF policies. CORS only matters to browsers; security must match the actual use case.

### 13.1. Reply Headers and HTTP Headers Are Not One-to-One

A business reply may consist of `Message<OrderCheckResponse>` plus Spring Integration metadata. When writing the HTTP response, only headers mapped and allowed by the server/runtime appear; transport headers such as `Content-Length`, `Transfer-Encoding`, and `Connection` are managed by the HTTP stack. Avoid trying to overwrite transport headers from business messages.

## 14. Testing the Request/Response Contract

### 14.1. Manual Testing with curl

After starting the application on `localhost:8080`:

~~~bash
# Valid: receives 200 and JSON response
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Correlation-Id: req-003' \
  -d '{"orderId":"ORD-1001"}'

# Wrong Content-Type: verify 415
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: text/plain' \
  -d 'ORD-1001'

# Invalid JSON: inspect how codec handles the error
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -d '{"orderId":'
~~~

On PowerShell, you can use `curl.exe` with the same command-line syntax. Actual error responses depend on mappings/security/error handlers, so always check both **status** and **body/content-type**.

### 14.2. Integration Testing with WebTestClient

With `spring-boot-starter-test` (test scope), a test can verify end-to-end success:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderCheckHttpFlowTest {
    @Autowired
    WebTestClient webTestClient;

    @Test
    void mapsJsonRequestToJsonReply() {
        webTestClient.post()
            .uri("/api/orders/check")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Correlation-Id", "req-004")
            .bodyValue(new OrderCheckHttpFlow.OrderCheckRequest("ORD-1001"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-1001")
            .jsonPath("$.status").isEqualTo("PROCESSING");
    }
}
~~~

This test assumes a Spring Boot application with full auto-configuration. It verifies the path request → gateway → handler → HTTP response. If security is enabled, configure appropriate test authentication. If the flow calls a real remote HTTP service, use a mock server to assert request method/headers/body and response mapping.

### 14.3. Minimum Test Matrix

| Test | What to verify |
|---|---|
| Valid POST JSON | Correct DTO body, HTTP 200, and JSON response |
| Wrong method, path, Content-Type, or Accept | Appropriate route/media-type error |
| Malformed JSON or missing field | Safe codec/validation error reporting |
| Valid correlation header | Mapped through message and emitted per policy |
| Header outside allowlist | Not leaked externally unintentionally |
| Business handler fails or returns no reply | Configured HTTP status/error flow/timeout |
| Remote 4xx/5xx, network timeout | Never treated as a success reply; conditional retries |
| SSE/Flux with slow client | No unbounded buffering, cancellation/timeout handled |

## 15. Applied Exercises

1. Run `OrderCheckHttpFlow`, sending requests with and without `X-Correlation-Id`. Inspect message headers and HTTP response headers, and explain why a header mapper matters.
2. Change `consumes` to `application/xml` while keeping a JSON body. Observe how route/codec rejects the request and distinguish `415` from `400`.
3. Add validation on `orderId`, testing `null`, empty string, and excessive length; design an error response with stable code, message, and correlation ID.
4. Change the API to `GET /api/orders/{orderId}` requiring query `includeHistory=true`. Identify the exact step converting path variable/query parameters into a DTO in the flow.
5. Change the handler to return a `Flux<OrderCheckResponse>` over SSE; use `curl -N` to observe events, disconnect mid-stream, and explain cancellation.
6. Add an outbound gateway calling a mock partner API, map `X-Correlation-Id` onto the request, receive `QuoteResponse`, then try `extractResponseBody(false)` to inspect the full `ResponseEntity`.
7. Have the mock partner return `404`, `429`, `503`, schema-mismatched JSON, and timeouts. Design error-handling, retry, and observability flows for each case.
8. Route the request into a `QueueChannel` ahead of a slow processing step with a short `replyTimeout`. Explain why the HTTP client can time out even while the message keeps processing.
9. Create an event with a fixed `Idempotency-Key` and resend it. Show how to prevent duplicate business results when an HTTP response is lost.
10. Inspect security filters and proxy-added headers; never trust unauthenticated client headers identifying users.

**Design question:** an application receives an HTTP POST to create a shipment, calls a remote shipping API, and writes to a DB. If the remote creates the shipment successfully but the response is lost, the client retries with the same request ID. Define how HTTP status/body are mapped across systems, where the idempotency key is stored, and what conditions permit returning `201 Created` instead of `202 Accepted`.

## 16. References

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound/outbound adapters, gateways, request mapping, payload types, and reactive replies.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP header mapper, URI variables, request/response semantics, and timeouts.
- [Spring Integration API — WebFluxInboundEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxInboundEndpointSpec.html): configuring inbound WebFlux endpoints, request mapping, and header mapping.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): outbound HTTP handlers, response types, and response body extraction.
- [Spring Framework Reference — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mapping, path/query/header binding, validation, and response handling.
- [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): reactive processing principles and HTTP bodies.

> **Takeaway:** Request/response mapping is the **HTTP ↔ Message** contract. Explicitly specify routes, media types, payload types, which headers are mapped, which channel carries replies, and how HTTP status/body are constructed. With WebFlux inbound/outbound gateways, proper mapping keeps integration flows returning accurate data while handling validation, timeouts, network errors, and security boundaries.
