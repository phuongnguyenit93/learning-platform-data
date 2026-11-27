# WebFlux Outbound Gateway Calling a Reactive Service

## 1. Context: Calling an HTTP Service and Receiving Results in IntegrationFlow

An order management system needs to query a shipping service for the delivery fee before confirming an order. Data may arrive from an internal API, Kafka, JMS, AMQP, files, SFTP, or a database. After receiving `Message<Order>`, the integration flow must send an HTTP request to the quoting service, receive the result, and continue processing `shippingFee`.

The **WebFlux outbound gateway** meets this need. It receives a `Message<?>` from Spring Integration, builds an HTTP request using Spring WebFlux's `WebClient`, and brings the HTTP response back into the flow as a **reply message**. The HTTP target can be a reactive service returning `Mono<T>` for a single result or `Flux<T>` for a stream of results. The fact that the external service uses Reactor does not force every component in the calling application to also use Reactor.

This topic belongs to the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: a module that connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s; covering message contracts, error handling, and connection lifecycles across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases.

~~~mermaid
flowchart LR
    A["Service / Kafka / JMS / DB"] --> B["Message<QuoteRequest>"]
    B --> C["Request MessageChannel"]
    C --> D["WebFlux outbound gateway"]
    D -->|"HTTP POST JSON via WebClient"| E["Reactive HTTP service"]
    E -->|"HTTP response: JSON"| D
    D --> F["Reply Message<QuoteResponse>"]
    F --> G["Transformer / Router / Service Activator"]
~~~

A gateway is a **request-reply** bridge: the HTTP result becomes data for downstream integration steps to make decisions on. This is the fundamental difference from one-way notification sending where the response payload is ignored.

## 2. Distinguishing Types of WebFlux Endpoints

| Component | Starting point | Produces business result as reply message? | When to use |
|---|---|---|---|
| **WebFlux outbound gateway** | Message inside Spring Integration | **Yes**, receives response from external HTTP server | Price lookups, status checks, fetching tokens/metadata, calling compute services |
| **WebFlux outbound channel adapter** | Message inside Spring Integration | **No**, one-way HTTP send branch | Sending events, pushing webhooks, notifying partners |
| **WebFlux inbound gateway** | HTTP client calls into the application | **Yes**, returns flow reply as HTTP response | Exposing request-reply REST APIs |
| **WebFlux inbound channel adapter** | HTTP client calls into the application | **No**, turns request into a message | Ingesting webhooks and background jobs |
| **Direct WebClient** | Java call, controller, or service | Result is application `Mono`/`Flux` | No need for message channels, routers, transformers, or `IntegrationFlow` |

The two terms **outbound** and **gateway** address two orthogonal aspects: *outbound* is the direction calling out to an external system; *gateway* is the contract bringing response data back into the flow. An outbound gateway can sit in the middle of a long integration flow, such as `JMS inbound → filter → outbound HTTP gateway → enrich → JDBC outbound`.

Do not use an outbound gateway merely for "fire-and-forget" when the response body serves no downstream step. In that case, an outbound channel adapter is simpler. Conversely, if you need `trackingId`, a quote, or HTTP metadata to decide the next branch, an outbound gateway is the right choice.

## 3. Request-Reply Contract with a Reactive Service

Throughout the example, the `Shipping Quote Service` runs separately at `localhost:9090`. It uses WebFlux and returns a `Mono<QuoteResponse>`, yet to an HTTP client, it is still a standard JSON HTTP response.

| Property | Illustrative contract |
|---|---|
| URL | `POST http://localhost:9090/api/shipping/quote` |
| Request `Content-Type` | `application/json` |
| Request header | `X-Request-Id: req-001` |
| Request body | `{"orderId":"ORD-1001","weightKg":2}` |
| Success HTTP status | `200 OK` |
| Response `Content-Type` | `application/json` |
| Response body | `{"orderId":"ORD-1001","shippingFeeVnd":30000,"currency":"VND"}` |
| Reply in IntegrationFlow | `Message<QuoteResponse>` |

In Java DSL, `expectedResponseType(QuoteResponse.class)` specifies the object type to decode from the **response body**. On its own, `expectedResponseType` does not perform business validation, does not turn 4xx/5xx statuses into successful values, and does not guarantee the external service committed any transaction. These must be explicitly defined in the service contract.

~~~mermaid
sequenceDiagram
    participant Producer as Message source
    participant Gateway as WebFlux outbound gateway
    participant Client as WebClient
    participant Remote as Reactive Quote Service
    participant Next as Downstream handler
    Producer->>Gateway: Message<QuoteRequest>
    Gateway->>Client: Prepare URI, method, body, headers
    Client->>Remote: POST /api/shipping/quote
    Remote-->>Client: Mono completes -> HTTP 200 + JSON
    Client-->>Gateway: Decode body into QuoteResponse
    Gateway->>Next: Reply Message<QuoteResponse>
    Next->>Next: Compute total or persist result
~~~

Note: `Mono` is an **implementation type inside the reactive service**, not transmitted verbatim over the HTTP wire. The HTTP client sees bytes of status, headers, and body. The gateway decides whether to decode the body into a regular object or a publisher according to its configuration.

## 4. Setting Up the Project

The example uses Java 17+ and Spring Boot to manage Spring Framework/Spring Integration dependencies. The illustrated APIs follow Spring Integration 6.x/7.x; verify exact configuration details against your project's specific version.

~~~groovy
// build.gradle - dependencies section of the calling application
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` provides `WebFluxRequestExecutingMessageHandler` and the `WebFlux.outboundGateway(...)` Java DSL. `spring-boot-starter-webflux` provides `WebClient`, Reactor, and standard HTTP codecs. **An application that only makes outbound HTTP calls does not need to expose a WebFlux inbound endpoint.**

Keep HTTP client configuration in a shared bean: this is where TLS, authentication, proxies, connection pools, timeouts, and tracing live. Avoid instantiating a new `WebClient`/connection pool per message.

## 5. Complete Example: Sending QuoteRequest and Receiving QuoteResponse

### 5.1. Declaring DTOs

Two Java records describe the request/reply contract. Using records with JSON requires a compatible codec, normally included with the Spring Boot WebFlux starter.

~~~java
package com.example.shipping;

public record QuoteRequest(String orderId, int weightKg) {
}
~~~

~~~java
package com.example.shipping;

public record QuoteResponse(
        String orderId,
        long shippingFeeVnd,
        String currency) {
}
~~~

In a real project, `orderId` and `weightKg` require validation. For simplicity, this example only defines the data structure.

### 5.2. Configuring the Message Channel and Outbound Gateway

~~~java
package com.example.shipping;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.MessageChannel;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class ShippingQuoteIntegration {

    @Bean
    public MessageChannel shippingQuoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public WebClient shippingWebClient(WebClient.Builder builder) {
        return builder.build();
    }

    @Bean
    public IntegrationFlow requestShippingQuote(WebClient shippingWebClient) {
        return IntegrationFlow.from("shippingQuoteRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/shipping/quote",
                    shippingWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE,
                    "X-Request-Id"))
            .channel("shippingQuoteResults")
            .get();
    }

    @ServiceActivator(inputChannel = "shippingQuoteResults")
    public void receiveQuote(QuoteResponse response) {
        System.out.printf(
            "order=%s, fee=%d %s%n",
            response.orderId(),
            response.shippingFeeVnd(),
            response.currency());
    }
}
~~~

Each configuration item has a specific role:

1. `shippingQuoteRequests` receives request messages from sources within the application. `DirectChannel` illustrates sending and dispatching; it is not a durable queue.
2. `shippingWebClient` is a reusable HTTP client, built from Spring Boot's builder to inherit appropriate codec/connector settings.
3. `WebFlux.outboundGateway(url, webClient)` turns a message into an HTTP request and creates a reply message from the response. This call differs from `outboundChannelAdapter`.
4. `httpMethod(POST)` explicitly declares the method. With GET/DELETE, consider `extractPayload(false)` if you do not want to send a body.
5. `expectedResponseType(QuoteResponse.class)` instructs the codec to deserialize the JSON response into `QuoteResponse`.
6. `mappedRequestHeaders(...)` permits only necessary headers onto the outbound HTTP request. Internal headers like `replyChannel`, `errorChannel`, or unrelated metadata should not leak to external services.
7. `channel("shippingQuoteResults")` routes the **reply** to the downstream step. `receiveQuote` is invoked when a matching reply arrives, which may happen asynchronously relative to where the initial message was sent.

**Warning about timing expectations:** `shippingQuoteRequests.send(...)` returning successfully confirms that **the channel accepted/dispatched the message per the channel contract**, not that the remote service returned a response or that `receiveQuote` has run. With WebFlux, HTTP execution is typically asynchronous.

### 5.3. Feeding a Message into the Flow

~~~java
package com.example.shipping;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class QuotePublisher {

    private final MessageChannel requests;

    public QuotePublisher(
            @Qualifier("shippingQuoteRequests") MessageChannel requests) {
        this.requests = requests;
    }

    public boolean requestQuote(String orderId, int weightKg) {
        return requests.send(
            MessageBuilder.withPayload(new QuoteRequest(orderId, weightKg))
                .setHeader(HttpHeaders.CONTENT_TYPE,
                    MediaType.APPLICATION_JSON_VALUE)
                .setHeader("X-Request-Id", "req-" + orderId)
                .build());
    }
}
~~~

From a source service or listener, call:

~~~java
publisher.requestQuote("ORD-1001", 2);
~~~

The gateway sends the JSON, receives the HTTP response, decodes it into `QuoteResponse`, and routes it to `shippingQuoteResults`. If you need to call the same gateway for multiple event types, define routing, channel names, and contracts carefully to avoid turning messages into malformed requests.

## 6. Simulating a Reactive Service on the Partner Side

Create a **separate WebFlux application** running on port `9090`. Define DTOs compatible with the JSON contract in Section 5; you can use identical records or declare corresponding ones in the mock application.

~~~java
package com.example.mock;

import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ShippingQuoteController {

    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @PostMapping(
        path = "/api/shipping/quote",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QuoteResponse> quote(@RequestBody Mono<QuoteRequest> body) {
        return body
            .filter(request -> request.orderId() != null
                    && !request.orderId().isBlank()
                    && request.weightKg() > 0)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid quote request")))
            .delayElement(Duration.ofMillis(150))
            .map(request -> new QuoteResponse(
                request.orderId(),
                request.weightKg() * 15_000L,
                "VND"));
    }
}
~~~

~~~yaml
# application.yml of the mock application - run separately
server:
  port: 9090
~~~

`delayElement` simulates latency using Reactor, **without blocking a thread with `Thread.sleep`**. With `weightKg=2`, the API returns a fee of `30000 VND`. Test the external service directly first to distinguish client errors from gateway errors:

~~~bash
curl -i -X POST http://localhost:9090/api/shipping/quote \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-1001","weightKg":2}'
~~~

Expected HTTP response for a valid request:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"ORD-1001","shippingFeeVnd":30000,"currency":"VND"}
~~~

Next, run the Spring Integration application and call `publisher.requestQuote("ORD-1001", 2)`. Expected log in `receiveQuote`:

~~~text
order=ORD-1001, fee=30000 VND
~~~

Do not assume a fixed timing relationship between the return of `requestQuote` and the log in `receiveQuote`. Behavior depends on channel type, scheduler, and asynchronous execution.

## 7. Reactive Mechanism of the WebFlux Outbound Gateway

`WebFluxRequestExecutingMessageHandler` uses `WebClient` to perform the HTTP exchange. Its internal processing pipeline is built around `Mono<ClientResponse>` and converts the result into the corresponding reply message. When the **output channel is a `ReactiveChannel`**, publisher execution may be **deferred until downstream subscribes**. With a standard output channel, the handler uses the messaging endpoint's built-in asynchronous reply mechanism.

~~~mermaid
flowchart TD
    A["Inbound Message"] --> B["WebFlux outbound gateway"]
    B --> C{"Output channel type?"}
    C -->|"ReactiveChannel"| D["Hold publisher until subscription"]
    C -->|"Standard channel"| E["Endpoint async reply mechanism"]
    D --> F["Execute HTTP exchange"]
    E --> F
    F --> G["Decode HTTP response"]
    G --> H["Reply Message"]
~~~

This is an important distinction when debugging:

- Missing an appropriate subscriber on a reactive branch can prevent the request from executing even though the publisher was created; design an explicit consumption flow.
- A `Mono<T>` from the **external service** is not passed into the flow as `Mono<T>` by default. With a typical `expectedResponseType(QuoteResponse.class)` configuration, downstream receives a `QuoteResponse` payload after the body is decoded.
- Using `DirectChannel` on the input side does not prove the whole flow is synchronous or that the thread calling `send()` waits for the HTTP response. Never treat `send()` as a remote delivery receipt.
- Reactive I/O saves threads while waiting on the network, yet blocking `JDBC`, heavy CPU work, unbounded queues, or `block()` calls can still cause bottlenecks.

**Preserving message context:** the reply is constructed from the HTTP response. If subsequent steps need to correlate back to the original request, use correlation IDs/headers per Spring Integration's contract, while mapping only permitted HTTP headers. A reply missing context can make matching results back to the original order hard to manage.

## 8. Receiving a Single Object, a Flux, or the Full ResponseEntity?

### 8.1. Single-Object JSON Response

This is the main example's case:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/shipping/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class))
~~~

When the HTTP response contains a matching JSON object, the reply payload is `QuoteResponse`. `replyPayloadToFlux` defaults to `false`. This works well when processing a single value, such as a shipping fee.

### 8.2. Multi-Element Stream Response

If the reactive service emits a stream of status updates, batch check results, or `text/event-stream`, the gateway supports:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/quotes/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(QuoteUpdate.class)
    .replyPayloadToFlux(true))
~~~

**Exact meaning:** the reply message carries **`Flux<QuoteUpdate>` as its payload**; it does not automatically split into separate `Message<QuoteUpdate>` messages. To process individual elements, downstream must know how to consume a `Publisher` or use an appropriate splitter/reactive flow. For streaming responses, codecs and `Accept` must be compatible (e.g., `text/event-stream` or NDJSON); do not enable `replyPayloadToFlux(true)` on every single-JSON API and treat it as an infinite stream.

| Configuration | Typical reply payload | Scenario |
|---|---|---|
| `expectedResponseType(QuoteResponse.class)` | `QuoteResponse` | Single JSON object |
| `expectedResponseType(QuoteUpdate.class)` + `replyPayloadToFlux(true)` | `Flux<QuoteUpdate>` | Stream of updates |
| `extractResponseBody(false)` | `ResponseEntity<...>` | Status code and response headers needed |
| `bodyExtractor(...)` | Return value of `BodyExtractor` | Low-level custom response reading |

### 8.3. Reading Status and Headers from the Remote Service

Since Spring Integration 5.5, `extractResponseBody(false)` keeps the **`ResponseEntity`** as the reply payload, along with status and headers:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/shipping/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .extractResponseBody(false))
~~~

Downstream must then handle a `ResponseEntity<QuoteResponse>` payload (or the form matching the actual received body), **not** cast directly to `QuoteResponse` as in Section 5. If the response has no body, the handler may return the full `ResponseEntity` even when `extractResponseBody` is enabled; test `204 No Content` and empty-response scenarios.

Note that `extractResponseBody(false)` helps inspect metadata **on normally handled responses**; it does not implicitly disable the HTTP client's treatment of error statuses as exceptions. Handling policies for 4xx/5xx must be designed and tested separately.

### 8.4. Sending a Publisher Request Body

Since Spring Integration 5.2, the handler supports `Publisher`, `Resource`, and `MultiValueMap` as request payloads. With `Publisher<QuoteRequest>`, you can define the element type so the HTTP body inserter/codec knows how to encode it:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/bulk-quote")
    .httpMethod(HttpMethod.POST)
    .publisherElementType(QuoteRequest.class)
    .expectedResponseType(String.class))
~~~

The snippet above only illustrates configuration; to actually stream a request, the message sent to the gateway must carry a `Publisher<QuoteRequest>` payload, the target server must support the appropriate media type, and downstream must consume the reply. Avoid arbitrarily calling `block()` or `subscribe()` outside the `IntegrationFlow` lifecycle.

## 9. HTTP Method, URI, Header Mapping, and Authentication

**Method and body.** With `POST`, the DTO payload is normally serialized to JSON. With `GET`, place lookup parameters in path/query parameters and do not expect a request body; `extractPayload(false)` can be used when appropriate. `Content-Type` describes the outgoing body; `Accept` describes the desired response format.

**Dynamic URI.** The gateway provides URI function/expression overloads per message, such as using a partner ID to select a configured host. Never concatenate a URL directly from untrusted headers/JSON and pass it to `WebClient`: doing so can introduce SSRF vulnerabilities. Map IDs against an endpoint allowlist, pin scheme/host/port, or go through a trusted routing service.

**Header mapping.** Define the required set of outbound HTTP headers: `Content-Type`, `Accept`, `Authorization`, `X-Request-Id`, etc. `mappedResponseHeaders(...)` controls which HTTP response headers are copied into the message; do not assume all external headers are trustworthy or copied verbatim.

**Authentication.** Place Bearer tokens, OAuth2 clients, or mTLS in the `WebClient`/filter configuration using a secret manager and rotate tokens periodically. Never hardcode tokens in source files, and do not forward a user's `Authorization` header to another system without an explicit delegation contract.

~~~java
// Illustration only; accessToken loaded from secure secret configuration.
WebClient client = builder
    .defaultHeaders(headers -> headers.setBearerAuth(accessToken))
    .build();
~~~

## 10. Timeouts, HTTP Errors, Retries, and Load Limits

| Stage | Common failures | What to control |
|---|---|---|
| Request creation | Invalid URI, body cannot be encoded | Payload validation, codecs, URL, and method |
| Connection/TLS | DNS failure, handshake error, connection refused | Connect timeout, certificates, proxy, pool |
| Waiting for response | Slow server, client timeout | Response timeout and overall deadline |
| HTTP 4xx | Bad request, unauthorized, `429` | Do not retry all 4xx; handle rate limits specifically |
| HTTP 5xx | External service error, temporarily unavailable | Bounded retries + backoff/jitter |
| Response decoding | HTML returned instead of JSON, schema drift | Check `Content-Type`, codecs, and version contracts |
| Downstream | Reply has no consumer, full queue, handler errors | Error channel, channel bounds, and observability |

**Timeout hierarchy:** there may be connect timeouts, response timeouts, endpoint/gateway timeouts, workflow deadlines, message-source timeouts, and reverse proxy timeouts. A single `replyTimeout` on a Messaging Gateway or handler does not replace all network and business timeouts. Define an overall deadline and allocate budgets across steps.

Configure a response timeout via Reactor Netty when using that connector:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient http = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(http))
    .build();
~~~

This snippet sets the **response timeout**; it does not cover connection wait time, queuing, or retry attempts. In production, also configure connection pools, connect timeouts, metrics, and concurrency limits.

### 10.1. Retries Must Not Cause Business Duplicates

A `POST` request may already have been executed by the remote service even though the client observes a timeout waiting for the response. If resent blindly, the external service could charge or create a shipment twice.

Operational principles:

1. Attach a fixed **idempotency key** to each business operation; retries reuse the same key.
2. Retry only contractually permitted cases, such as network errors or certain `429`/`5xx` responses; cap attempts and use exponential backoff with jitter.
3. Persist incomplete requests, dead-letter failed items, alert, and allow manual remediation. If zero message loss across app restarts is required, use a persistent outbox or broker.
4. Do not conclude HTTP `200 OK` means every follow-on task in the remote service has committed; read the exact API contract.
5. When the source is a JMS/Kafka/DB poller, determine **when the source message is ACKed/committed** after recording send status. Early ACK can lose work; late retry can cause duplicate sends.

### 10.2. Error Channel and Handling Failed Responses

In reactive flows, errors occurring during publisher execution or response decoding can travel through the endpoint's asynchronous error path, depending on channel type, `errorChannel` configuration, and advice. Do not assume a `channel.send(...)` call throws every HTTP error. If business decisions depend on 4xx/5xx, configure an explicit error-handling path and test it; `extractResponseBody(false)` does not turn errors into successful replies.

For transient errors, `retry` can live at the client layer or Spring Integration layer depending on goals; avoid stacking multiple retry layers without knowing the total resend count. For permanent errors, route to a failure channel and store necessary reconciliation data.

## 11. Designing the End-to-End Flow

Treat the HTTP gateway as **one hop** among multiple systems, not a replacement for overall integration design.

Example quoting workflow sourced from Kafka:

~~~mermaid
flowchart TD
    A["Kafka inbound adapter"] --> B["Validate + map to QuoteRequest"]
    B --> C["WebFlux outbound gateway"]
    C -->|"HTTP response QuoteResponse"| D["Enrich order with shipping fee"]
    D --> E["Persist / emit next event"]
    C -.->|"HTTP/network/decode error"| F["Retry policy / error flow"]
    F --> G["DLQ / outbox / alerting"]
~~~

Decisions that must be explicit:

- **Routing:** when integrating with multiple partners, keep endpoints, credentials, and response schemas separate, or add an adapter layer translating to a shared contract.
- **Correlation:** a reply must be traceable back to the originating request via `requestId`/`orderId` and trusted metadata.
- **Dispatching:** `DirectChannel`, `ExecutorChannel`, and `FluxMessageChannel` differ in synchronicity, executors, subscription, and backpressure semantics.
- **Load limits:** configure pools, timeouts, rate limits, concurrency, and queue bounds rather than assuming WebFlux alone guarantees high throughput.
- **Observability:** measure success/error rates, HTTP latency, encode/decode failures, retries, queue backlog, and source-to-business-result duration.
- **Shutdown:** close connections and stop accepting new work gracefully; never assume an in-flight request without a response definitely failed on the remote server.

## 12. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| "External service returns `Mono<T>`, so the reply payload is always `Mono<T>`" | With `expectedResponseType(T.class)`, the gateway usually decodes to `T`; `Mono` is how the remote completes the HTTP response |
| "WebFlux outbound gateway is the same as outbound channel adapter" | The gateway produces a reply message; the adapter is for one-way branches |
| "`send() == true` proves the HTTP request finished processing" | `send` reflects the channel contract, not a remote receipt |
| "Adding `FluxMessageChannel` makes the request run immediately" | With reactive output, a downstream subscription may be needed to trigger the publisher |
| "`replyPayloadToFlux(true)` automatically creates multiple reply messages" | The reply payload is a single `Flux<T>`; you must design consumption or splitting |
| "`extractResponseBody(false)` never throws 4xx/5xx errors" | Depends on status handling; keeping `ResponseEntity` does not mean ignoring HTTP errors |
| "Non-blocking WebClient means the entire flow is non-blocking" | Handlers, databases, queues, schedulers, and application code dictate final behavior |
| "Retrying a POST after a timeout is always safe" | The remote may have already processed the request; idempotency and reconciliation are needed |

## 13. Exercises

1. Run the mock reactive service on `9090` and test HTTP `200` and JSON reply with `curl`. Next, send a message through `QuotePublisher` and verify `shippingQuoteResults` receives `QuoteResponse`.
2. Send `weightKg=0` to trigger a `400` client error; observe the error path and explain why downstream should not receive a `QuoteResponse` payload as if it succeeded.
3. Change the mock to return `204 No Content`; test `extractResponseBody(false)` and inspect the payload type in the reply.
4. Create a mock endpoint returning `Flux<QuoteUpdate>` as SSE or NDJSON; use `replyPayloadToFlux(true)` and design a subscriber/splitter to process each item. Compare with a single JSON response.
5. Add simulated latency exceeding the response timeout; compare exceptions, recovery time, retry counts, and API impact.
6. Send the same `X-Request-Id` twice after simulating a lost response; explain how the remote uses the idempotency key to prevent duplicate creation.
7. Replace the message source with Kafka/JMS or a DB poller; analyze ACK/commit placement and define what conditions permit marking the source message complete.

**Applied question:** A quoting service returns `HTTP 200` with body `{"orderId":"ORD-1001","shippingFeeVnd":30000}`. The next step must save the price and emit `quote.calculated` only after the database commits. If the connection drops after the remote returned the body but before the local commit, how would you place the retry, idempotency, and source ACK boundaries?

## 14. References

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): `WebFluxRequestExecutingMessageHandler`, Java DSL, reactive output channels, `expectedResponseType`, `replyPayloadToFlux`, and `extractResponseBody`.
- [Spring Integration API — WebFlux Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFlux.html): `outboundGateway` and `outboundChannelAdapter` overloads.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): `replyPayloadToFlux`, `publisherElementType`, `bodyExtractor`, and inherited options.
- [Spring Integration Reference — HTTP Outbound Components](https://docs.spring.io/spring-integration/reference/http/outbound.html): request mapping, response, URI, and header mapping.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): how WebClient calls reactive HTTP services, response handling, codecs, and timeouts.

> **Takeaway:** `WebFlux.outboundGateway(...)` is the point in Spring Integration that calls HTTP **outbound** and **returns the HTTP result to the flow** as a reply message. With reactive services, distinguish server-side `Mono`/`Flux`, the gateway's reply payload type, subscription timing, and business acknowledgment boundaries. Solid design pairs the right message contract with timeouts, idempotency, error handling, and end-to-end observability.
