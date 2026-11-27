# Streaming Responses with Flux in Spring Integration WebFlux

## 1. The Problem: Returning Results Incrementally Instead of Waiting for All Data

An HTTP API does not always return a single JSON object and close the response. For example, a shipment tracking service needs to emit statuses *RECEIVED → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED* in real time; a reporting service needs to return thousands of records without waiting to assemble a massive list in memory. **Streaming responses** allow the server to emit elements as data becomes available, and clients to read them as they arrive.

In the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. Flows can originate from files, SFTP, HTTP, JMS, AMQP, Kafka, or databases. Combining WebFlux with Project Reactor lets you represent result streams via **`Flux<T>`**, while still requiring explicit design of the HTTP contract, Spring Integration message wrapping, backpressure, errors, and connection lifecycles.

**Two distinct streaming directions:**

- **Inbound WebFlux gateway:** HTTP client calls **into the application**; a handler inside `IntegrationFlow` returns a `Flux<T>`, and the gateway writes elements as a streaming HTTP response.
- **Outbound WebFlux gateway:** `IntegrationFlow` calls **out to an external API** via `WebClient`; if the remote returns a stream, the gateway can place `Flux<T>` as the **reply message payload** for downstream consumption.

~~~mermaid
flowchart LR
    A["Browser / curl / client"] -->|"HTTP GET"| B["WebFlux inbound gateway"]
    B --> C["IntegrationFlow"]
    C -->|"Reply payload: Flux<ShipmentUpdate>"| B
    B -->|"SSE: events over time"| A
~~~

Streaming differs from returning `List<T>`: `List<T>` is normally only available after the entire result set is built and held in memory; `Flux<T>` can emit multiple items asynchronously and eventually complete, or continue indefinitely.

## 2. Three Layers to Distinguish: Reactor, Spring Integration, and HTTP

| Layer | Construct | Meaning |
|---|---|---|
| Project Reactor | `Mono<T>` | Publisher emitting at most one element |
| Project Reactor | `Flux<T>` | Publisher emitting zero to many elements; may complete or stay open |
| Spring Integration | `Message<Flux<T>>` | **One** integration message holding a publisher as its payload |
| Spring Integration | `Flux<Message<T>>` | Publisher emitting **multiple integration messages** |
| Spring Integration | `FluxMessageChannel` | Reactive Streams–integrated channel; not synonymous with HTTP response streaming |
| HTTP | `text/event-stream` | Server-Sent Events: event-framed text stream |
| HTTP | `application/x-ndjson` | Each text line is a JSON value, suited for consecutive JSON objects |
| HTTP | `application/json` | Typically a single JSON document; may require completing/collecting results to be valid |

These three layers do not automatically convert between one another. If an outbound gateway returns `Message<Flux<ShipmentUpdate>>`, a handler expecting `Message<ShipmentUpdate>` will **not** automatically receive individual updates. You need a consumer/splitter or reactive step that understands that payload.

~~~text
One message holding a stream:
Message<Flux<ShipmentUpdate>>
  └─ payload = Flux
     ├─ ShipmentUpdate(sequence=0)
     ├─ ShipmentUpdate(sequence=1)
     └─ ShipmentUpdate(sequence=2)

Stream of multiple messages:
Flux<Message<ShipmentUpdate>>
  ├─ Message(sequence=0)
  ├─ Message(sequence=1)
  └─ Message(sequence=2)
~~~

**Note:** *reactive* at the WebClient/WebFlux layer does not guarantee every handler, poller, JDBC call, or broker also obeys Reactive Streams. Backpressure propagates only through components with compatible contracts.

## 3. How Are Streaming Responses Actually Sent Over HTTP?

### 3.1. Server-Sent Events (SSE)

SSE uses an HTTP response with media type `text/event-stream`. Each event can contain `id`, `event`, `data`, and `retry` fields; events are typically separated by a blank line.

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 0
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}

id: 1
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}

~~~

In real responses, HTTP/1.1 may use chunked transfer encoding; HTTP/2 uses its corresponding frames. **A TCP packet boundary or HTTP chunk boundary is not an SSE event boundary.** Clients must parse the SSE format rather than relying on byte-read boundaries.

SSE is a **server → client** protocol after the client opens an HTTP request, suited for dashboards, notifications, or progress updates. It differs from WebSocket (bidirectional) and from issuing many separate HTTP requests.

### 3.2. NDJSON

With `application/x-ndjson`, each line is an independent JSON document:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}
{"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}
~~~

NDJSON fits record-oriented data processing systems. It lacks SSE's built-in `id/event/retry` structure. If the client is a browser using `EventSource`, pick SSE; if the client has a line-delimited JSON HTTP parser, NDJSON can be simpler.

### 3.3. Why `application/json` Is Not Necessarily Streaming

A valid JSON array requires `[`, comma-separated elements, and a closing `]`. Depending on codecs, encoding, and the client, a `Flux<T>` under `application/json` may be buffered, or only treated as a complete document after the server ends the stream. Never treat `Flux<T>` alone as proof that each object will render immediately for the client. **Choose a streaming-compatible media type and proper codec, and test the actual bytes received.**

## 4. From Standard Request-Reply to a Streaming Gateway

A WebFlux inbound **channel adapter** receives an HTTP request and sends a message to a channel; it does not use downstream results to construct a business response body. To stream **responses from a flow**, you need a **WebFlux inbound gateway**, because the gateway awaits a reply message and converts the reply payload into the HTTP body.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant Gateway as WebFlux inbound gateway
    participant Flow as IntegrationFlow
    participant Pub as Flux Publisher
    Client->>Gateway: GET /api/shipments/progress
    Gateway->>Flow: Request Message + reply context
    Flow-->>Gateway: Reply Message<Flux<ShipmentUpdate>>
    Gateway->>Pub: Subscribe/read payload publisher
    Pub-->>Gateway: onNext(update 0)
    Gateway-->>Client: SSE event 0
    Pub-->>Gateway: onNext(update 1)
    Gateway-->>Client: SSE event 1
    Pub-->>Gateway: onComplete()
    Gateway-->>Client: Complete HTTP response
~~~

The diagram depicts the **logical sequence**, not claiming each `onNext` produces exactly one TCP write. The gateway and WebFlux runtime coordinate reading the reply publisher according to the codec/media type. The gateway's reply timeout (if configured) governs **waiting for the reply message**, not automatically the total emission duration of a `Flux` that might run for several minutes.

## 5. Setting Up Spring Boot and Spring Integration

The example uses Java 17+, Spring Boot, and a BOM compatible with Spring Integration. With Spring Boot, let dependency management select compatible Spring Framework, Reactor, and Spring Integration versions.

~~~groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` provides WebFlux inbound/outbound gateways. `spring-boot-starter-webflux` provides the WebFlux runtime, WebClient, and standard HTTP codecs. In a Spring Boot app already auto-configured for WebFlux, manually adding `@EnableWebFlux` is unnecessary just to run the example.

In projects declaring both Spring MVC and WebFlux, verify which web application type is active; having `WebClient` on the classpath does not prove the server serves requests with WebFlux.

## 6. Complete Example: Inbound Gateway Returning SSE with Flux

Build an API publishing shipment processing progress. The app accepts `GET /api/shipments/progress`, produces a reply publisher of four statuses, and returns them as SSE. This is a simulated example—**no** external broker or database is needed.

~~~java
package com.example.integration;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Configuration
@EnableIntegration
public class ShipmentProgressFlow {

    public record ShipmentUpdate(
            String shipmentId, long sequence, String status) { }

    @Bean
    public IntegrationFlow shipmentProgressGateway() {
        String[] statuses = {
            "RECEIVED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"
        };

        return IntegrationFlow
            .from(WebFlux.inboundGateway("/api/shipments/progress")
                .requestMapping(mapping -> mapping
                    .methods(HttpMethod.GET)
                    .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
            .handle((payload, headers) ->
                Flux.interval(Duration.ofSeconds(1))
                    .take(statuses.length)
                    .map(index -> ServerSentEvent
                        .<ShipmentUpdate>builder()
                        .id(Long.toString(index))
                        .event("shipment-progress")
                        .data(new ShipmentUpdate(
                            "SHP-001", index, statuses[index.intValue()]))
                        .build()))
            .get();
    }
}
~~~

### 6.1. Reading Each Component

1. `WebFlux.inboundGateway(...)` creates a **request-reply** HTTP endpoint. The reply carries `Flux<ServerSentEvent<ShipmentUpdate>>` so the HTTP writer can serialize it incrementally.
2. `requestMapping(...).methods(GET)` defines the HTTP method, and `produces(TEXT_EVENT_STREAM_VALUE)` sets the response media type.
3. `handle((payload, headers) -> ...)` is an inline service activator. The example needs no body or query parameters, so it ignores the request payload.
4. `Flux.interval(Duration.ofSeconds(1))` emits indices on Reactor's scheduler without blocking threads via `Thread.sleep`.
5. `take(statuses.length)` limits emissions to four items; afterward, the publisher signals `onComplete` and the HTTP response can finish.
6. `ServerSentEvent.builder()` sets `id` and `event` explicitly; `data` holds the DTO serialized by the codec.
7. No large `List<ShipmentUpdate>` is prebuilt. Still, the small `statuses` array is for simulation only; in production, the source could be a reactive repository or event source.

**Limitations of the example:** each HTTP subscription starts a fresh interval sequence and the statuses are simulated. A real service must extract `shipmentId` safely from the request, authorize access to that shipment, connect to a real data source, and define a replay policy when clients reconnect.

## 7. Testing with curl and a Browser

Run the Spring Boot/WebFlux application on `localhost:8080` and send:

~~~bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/shipments/progress
~~~

`-N` or `--no-buffer` disables curl's output buffering so you can watch each event as the server emits it. In PowerShell, use `curl.exe` to avoid alias syntax differences.

Illustrative response (omitting minor transport headers):

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 0
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}

id: 1
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}

...
~~~

Actual behavior depends on codecs, serialization format, and intermediate proxies. If all items appear at once only when the request finishes, check **media types, codecs, proxy buffering, and the HTTP client** before concluding `Flux.interval` is not streaming.

A browser can consume SSE using the `EventSource` API:

~~~javascript
const stream = new EventSource("/api/shipments/progress");

stream.addEventListener("shipment-progress", event => {
  const update = JSON.parse(event.data);
  console.log(update.shipmentId, update.status);
});

stream.onerror = error => {
  console.error("SSE connection error", error);
};

// When updates are no longer needed:
// stream.close();
~~~

`EventSource` supports one-way SSE and automatically reconnects per browser behavior. **Automatic reconnect does not imply automatic replay**: the server must read `Last-Event-ID` and query an event store if clients should recover missed events. The `Flux.interval` example has no historical replay mechanism.

## 8. From Mock Data to Real Event Sources

In production, shipment updates may come from Kafka, JMS/AMQP, CDC, databases, or file/SFTP adapters. The biggest challenge is decoupling **long-lived message sources** from **short-lived HTTP subscriptions**.

~~~mermaid
flowchart TD
    A["Kafka / AMQP / DB event source"] --> B["Validation + enrichment"]
    B --> C["Event store / bounded fan-out service"]
    C --> D["Publisher<ShipmentUpdate>"]
    D --> E["WebFlux inbound gateway"]
    E --> F["SSE clients"]
    F -.->|"disconnect / reconnect / Last-Event-ID"| C
~~~

**Two source types to distinguish:**

- **Cold publisher:** each subscriber triggers an independent stream, like `Flux.interval` in this lesson. If 100 clients subscribe, 100 independent computations/queries may run. Control concurrency and bound subscriptions.
- **Hot publisher:** one source emits continuously and shares across subscribers, such as a publisher backed by an event bus. Late-joining clients miss prior events unless a replay mechanism exists.

Reactor offers `Sinks.Many<T>` to multicast/replay data to subscribers; pick a sink flavor based on buffer/overflow policies, acceptable data loss, and data retention lifecycles. `FluxMessageChannel` also uses reactive constructs for message integration, yet it is **not** a historical event store for all SSE users.

For critical events (payments, order confirmations), never rely on an **open SSE connection** as the sole durable store. Use an appropriate broker/outbox/event store and project publishable events onto the HTTP stream.

## 9. Outbound Gateway: Receiving Streaming HTTP Responses from a Remote Service

In the **outbound** direction, Spring Integration's WebFlux outbound gateway uses `WebClient` to call a remote HTTP API. Normally `expectedResponseType(ShipmentUpdate.class)` decodes **a single object** into the reply. When the remote genuinely returns a stream, `replyPayloadToFlux(true)` makes the reply message carry a `Flux<ShipmentUpdate>`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class RemoteProgressClientFlow {

    public record ShipmentUpdate(
            String shipmentId, long sequence, String status) { }

    @Bean
    public IntegrationFlow fetchRemoteProgress(WebClient.Builder builder) {
        WebClient client = builder.build();

        return IntegrationFlow.from("remoteProgressRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:8080/api/shipments/progress", client)
                .httpMethod(HttpMethod.GET)
                .extractPayload(false)
                .expectedResponseType(ShipmentUpdate.class)
                .replyPayloadToFlux(true)
                .mappedRequestHeaders(HttpHeaders.ACCEPT))
            .channel("remoteProgressReplies")
            .get();
    }
}
~~~

This is a **separate client flow illustration**: to connect two standalone applications, run the SSE service on `8080` and the HTTP-calling app on another port/process. Defining a channel named `remoteProgressRequests` alone does not initiate requests; a producer must send a message to the channel.

A producer can send a message with header `Accept: text/event-stream`:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.support.MessageBuilder;

remoteProgressRequests.send(
    MessageBuilder.withPayload("trigger")
        .setHeader(HttpHeaders.ACCEPT,
            MediaType.TEXT_EVENT_STREAM_VALUE)
        .build());
~~~

Here `extractPayload(false)` avoids sending the message payload as an HTTP GET body. The remote emits SSE events containing JSON data; with compatible codecs, the gateway decodes each event's data as `ShipmentUpdate.class`.

**Important:** `remoteProgressReplies` receives a single **reply message with payload `Flux<ShipmentUpdate>`**, not four separate `Message<ShipmentUpdate>` instances. Downstream must consume the publisher while managing subscription, backpressure, cancellation, and error signals.

In a large system, keep `WebClient` as an injected bean and configure connection pools/timeouts in one place rather than building a new client per call. The concise `builder.build()` inside the flow bean still creates **one client at context startup**, not per HTTP request.

## 10. Properly Consuming a Flux Reply Payload

Suppose the outbound gateway produces a `Flux<ShipmentUpdate>` message payload. Two common designs apply:

1. **Terminal reactive consumer:** the final endpoint in the pipeline subscribes to the `Flux`, processes each update, and owns stopping/bounding the source.
2. **Expanding a Flux into a stream of integration messages:** use a splitter or reactive-aware component so each update traverses its own pipeline. Make sure the splitter/consumer actually subscribes; changing channel names alone is not enough.

~~~mermaid
flowchart TD
    A["Reply: Message<Flux<Update>>"] --> B{"What does downstream need?"}
    B -->|"Record as stream"| C["Reactive subscriber / sink"]
    B -->|"Individual messages to route/transform"| D["Publisher-aware splitter"]
    D --> E["Flux<Message<Update>> or individual messages"]
    B -->|"Aggregate finite count"| F["Bounded collectList()"]
~~~

For an **unbounded stream**, `collectList()` never completes and accumulates infinitely. Only collect finite sets with explicit item/time bounds and memory analysis.

The Reactor snippet below illustrates handling a publisher at the **final consumption boundary**, not advice to call `subscribe()` arbitrarily inside every handler:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

void consumeAtBoundary(Flux<ShipmentUpdate> updates) {
    updates.subscribe(new BaseSubscriber<ShipmentUpdate>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1);
        }

        @Override
        protected void hookOnNext(ShipmentUpdate update) {
            System.out.println(update);
            request(1);
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.err.println("Streaming failed: " + error);
        }
    });
}
~~~

`ShipmentUpdate` in this snippet is the application DTO. `request(1)` expresses subscriber demand; **synchronous printing is not reliable business processing**. When writing to a DB or sending to a broker, tie requesting the next item to **when asynchronous processing finishes**, rather than calling `request(1)` prematurely and assuming downstream is protected.

When building Spring Integration reactive pipelines, study `FluxMessageChannel`, `ReactiveStreamsConsumer`, and `handleReactive(...)` to preserve composition and error/cancel signals. Never assume every `MessageHandler` automatically subscribes to a payload publisher.

## 11. Backpressure: Slow Clients and Real Boundaries

Reactive Streams uses `request(n)` so a subscriber expresses how many items it wants. When the HTTP writer consumes a `Flux` based on demand, it can regulate a reactive producer in the same chain. However, **TCP flow control**, codec/proxy buffers, and publishers running on independent schedulers each have their own behavior.

| Flow segment | How can backpressure operate? | Boundary limitation |
|---|---|---|
| `Flux.range/interval` → HTTP writer | Runtime subscribes to publisher; demand/cancellation propagates in the reactive chain | Does not guarantee each `request(n)` maps 1:1 to a TCP chunk |
| `FluxMessageChannel` → `ReactiveStreamsConsumer` | Compatible components link demand | Producers calling imperative `send()` must still throttle separately |
| Kafka/JMS/AMQP → service | Driver mechanisms: poll/prefetch/ACK/concurrency | Does not stop the broker just because a browser reads SSE slowly |
| Blocking JDBC → Flux | Blocking can be isolated on an executor/scheduler | Schedulers do not make JDBC non-blocking |
| HTTP stream via proxy | Flushes/buffers per infrastructure settings | Proxies can alter when clients observe individual events |

Avoid designing an *unbounded buffer* between a fast source and a slow client. If the source carries business data where no event can be missed, use an event store/replay plus connection limits instead of accumulating unsent data unboundedly in memory.

For real-time telemetry, you may consider a documented drop/latest policy with monitoring, **making it explicit that items may be dropped**. For payments or critical order updates, uncontrolled dropping is unacceptable.

### 11.1. Concurrency and Memory

Each SSE subscription can hold resources for a long time: connections, parsers/encoders, buffers, observers, correlation context, and upstream subscriptions. Cap concurrent clients, per-user subscriptions, event rates, payload sizes, and pending message counts.

A `Flux` can be non-blocking yet still exert severe memory pressure if upstream pushes thousands of events/second toward a slow-network client. Solutions include **throttling the source, bounded buffering, valid load shedding, or durable persistence letting clients read by offset/cursor**.

## 12. Cancellation, Reconnect, and Last-Event-ID

A client may close a tab, lose connectivity, or call `EventSource.close()`. WebFlux can then cancel the HTTP subscription, and the Reactor publisher receives the cancellation signal. Even so:

- A reactive query may cancel if the driver supports cancellation, whereas a blocking task already submitted to an executor may continue running.
- A message already sent to JMS/Kafka **is not automatically recalled** just because the SSE client disconnected.
- A committed database write does not roll back because the TCP connection closed afterward.
- A hot source can keep emitting to other clients even after one leaves.

Attach hooks to observe the publisher lifecycle:

~~~java
Flux<ShipmentUpdate> monitored = updates
    .doOnSubscribe(s -> log.info("Stream subscribed"))
    .doOnCancel(() -> log.info("Stream cancelled"))
    .doOnComplete(() -> log.info("Stream completed"))
    .doOnError(error -> log.warn("Stream failed", error))
    .doFinally(signal -> log.info("Stream terminated: {}", signal));
~~~

`updates` and `log` here represent components available in a real service; the snippet illustrates hooks, not a standalone runnable file.

SSE includes an `id` field and `Last-Event-ID` reconnect header, yet the framework does not automatically know how to query historical events. If **zero missed events** is required, the server must:

1. Persist events in a durable store or ordered/offset-based stream log.
2. Emit stable, queryable IDs corresponding to real events.
3. Re-verify resource authorization upon reconnect.
4. Read the `Last-Event-ID` header, resolve the resume cursor, and replay missed events before switching to live streaming.
5. Handle expired retention, invalid cursors, and ordering/partition changes.

The `Flux.interval` illustration in Section 6 does none of those steps.

## 13. Errors and Timeouts While Streaming Responses

### 13.1. Before and After HTTP Headers Are Sent

| Error timing | Handling capability | Examples |
|---|---|---|
| **Before** HTTP response commits | Can choose a different HTTP status and error body | Validation failure, unauthorized, shipment not found |
| **After** streaming has begun | Normally cannot change HTTP `200` to `500` mid-response | DB read error or publisher failure mid-stream |
| Client cancels connection | Stop emitting per cancellation mechanics | Browser closes tab, proxy timeout |
| Proxy timeout/idle close | May close response while app still holds publisher | Missing heartbeats or short proxy timeout |

Once the HTTP status and headers have been committed, the server cannot send a **new status code** mid-response. It can terminate the stream, emit a **business error event** if the contract permits and the socket is still writable, or let the client reconnect. Never treat a business error event as a complete substitute for HTTP 5xx.

### 13.2. Avoid Silently Swallowing Errors

~~~java
Flux<ShipmentUpdate> updates = loadUpdates(shipmentId)
    .doOnError(error -> log.error("Shipment stream error", error));
~~~

The snippet shows logging. If using `onErrorResume` to emit a final error-notification event, explicitly define that schema and expose only safe information. Never blindly write `onErrorResume(error -> Flux.empty())` for all errors, or clients will assume the stream ended normally and never realize data was lost.

### 13.3. Which Timeout Applies?

Distinguish the limits:

- Inbound gateway `replyTimeout` governs waiting for the flow's **reply message**. Receiving an early reply holding a `Flux` does not force the whole stream to finish within that window.
- Reactor Netty WebClient `responseTimeout` is the client transport response timeout; with sparse SSE emissions, setting it too short disconnects valid streams.
- Reactor `timeout(Duration)` is a publisher/operator bound; depending on placement, it applies between signals or over the chain per operator semantics.
- Proxies/load balancers have their own idle timeouts, absolute connection lifetimes, and buffering.
- Business contracts may require independent *first-event timeout*, *idle timeout*, *max stream lifetime*, and *reconnect backoff*.

Do not apply a single "5-second timeout" across every layer. Clearly document where each timeout starts, ends, and surfaces errors.

## 14. Security and Operating HTTP Streams

Streaming connections can outlive typical REST requests, requiring management of both user sessions and outgoing data:

1. **Authentication/authorization:** verify shipment access before opening a stream; for long-lived streams, account for token expiration/revocation and connection termination policies.
2. **CORS and credentials:** for browser `EventSource`, configure CORS/credentials for exact origins; CORS never replaces authentication.
3. **Data size and frequency:** bound payloads, event rates, subscriber counts, session lifetimes, and buffer capacities.
4. **Heartbeats:** when idle proxy timeouts exist, emit SSE heartbeats per contract to keep connections alive without wasting bandwidth.
5. **Observability:** track active streams, time-to-first-event, subscription durations, emitted events, cancellations, errors, reconnects, and data lag.
6. **Logging:** use secret-free correlation IDs; never log full sensitive payloads or `Authorization` headers.
7. **Graceful shutdown:** stop accepting new subscriptions, close active streams per policy, and clean up publishers/schedulers/resources.

**Headers and caching:** use `Content-Type: text/event-stream` and set `Cache-Control` per contract. Misconfigured proxies can cache or buffer streaming responses; test along the real deployment path (ingress, CDN, reverse proxy) rather than only on `localhost`.

## 15. Testing Streams, Not Just HTTP 200

A test asserting only `200 OK` is **insufficient** to prove a streaming API works. Verify media types, item counts, relative emission cadence, completion/cancellation, and error behavior.

### 15.1. WebTestClient Reading a Flux Response Body

With `spring-boot-starter-test` and appropriate test dependencies:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'io.projectreactor:reactor-test'
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ShipmentProgressStreamTest {

    @Autowired
    WebTestClient client;

    @Test
    void emitsShipmentUpdatesAsSse() {
        FluxExchangeResult<ShipmentProgressFlow.ShipmentUpdate> result =
            client.get()
                .uri("/api/shipments/progress")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(ShipmentProgressFlow.ShipmentUpdate.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(update ->
                update.sequence() == 0
                    && "RECEIVED".equals(update.status()))
            .expectNextCount(3)
            .verifyComplete();
    }
}
~~~

The test above focuses on the **`data` payload** decoded by WebFlux's SSE codec into a DTO. If you also need to verify `id` and `event` on the SSE frame, read the response body as `ServerSentEvent<ShipmentUpdate>` with an appropriate type reference or inspect the raw SSE stream; the test can then verify event names and IDs, not just JSON data.

With tests driven by `Flux.interval(1s)`, each request takes several seconds. In thorough test suites, control publishers using a test scheduler or controllable fixtures instead of wall-clock delays for every test. Tests/builds were not executed while authoring this guide.

### 15.2. Error Matrix to Practice

| Scenario | What to observe |
|---|---|
| Client sends `Accept: text/event-stream` | Matching HTTP media type and individual SSE events |
| Client reads very slowly | How buffers/concurrency/latency grow and whether limits protect the server |
| Client closes before final event | Whether upstream receives cancellation and resources clean up |
| Publisher throws before first element | Whether error handler returns an appropriate HTTP status |
| Publisher throws after two events | Committed HTTP status cannot change; how stream terminates/signals error |
| Remote SSE pauses emitting | Whether client/proxy timeouts and heartbeats behave properly |
| Client reconnects with `Last-Event-ID` | Whether replay exists; if not, document no guarantee |
| Multiple concurrent subscribers | Cold/hot publisher behavior, memory, and connection caps |

## 16. Applied Exercises

1. Run `ShipmentProgressFlow` and use `curl -N` to watch the four events. Change `take(4)` to `take(10)` and adjust the data source so array bounds are not exceeded.
2. Change `data` from `ShipmentUpdate` to a plain text string and compare the SSE frames; explain how the codec serializes data.
3. Add a `ServerSentEvent` heartbeat or a separate progress event, and check how proxies/browsers handle it.
4. Build a second endpoint streaming NDJSON with WebFlux; compare client NDJSON parsing with `EventSource` for SSE.
5. Run an outbound gateway with `replyPayloadToFlux(true)` calling the SSE endpoint. Inspect the reply payload type and build a consumer that actually consumes the `Flux`.
6. Use a `BaseSubscriber` requesting one item at a time, then hand off to a concurrency-bounded reactive DB writer; explain when requesting more via `request(n)` is safe.
7. Simulate a fast hot source and a slow client. Choose a bounded buffer/replay store or a documented drop policy depending on business rules.
8. Abort `curl` mid-stream and use `doOnCancel` and `doFinally` to observe the lifecycle. Verify that work already committed in a broker/DB is not mistaken for automatic rollback.
9. Make the publisher fail before the first item and after emitting two items; compare the ability to alter HTTP status/body.
10. Design a `Last-Event-ID` mechanism using an event store with stable cursors, authorization checks, and retries. Identify the impact when historical data expires beyond retention.

**Scenario question:** a system emits order-processing statuses over Kafka while multiple clients open SSE streams to track them. If a client goes offline for five minutes while the order transitions through three statuses, do `FluxMessageChannel` and `Flux.interval` alone satisfy the "no missed statuses" requirement? Describe the event store/cursor, replay mechanism, idempotency, connection limits, and where backpressure stops.

## 17. References

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound/outbound gateways, `Flux` replies, `replyPayloadToFlux(true)`, and `WebClient`.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): `expectedResponseType`, `replyPayloadToFlux`, and WebFlux outbound options.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer`, and publisher composition.
- [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HTTP body codecs, SSE, and reactive HTTP processing.
- [Spring Framework Reference — WebFlux Client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient receiving `Flux` and handling streaming responses.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): cold/hot publishers, `request(n)`, errors, cancellation, and testing with `StepVerifier`.
- [MDN — Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): SSE format, `EventSource`, event IDs, and browser reconnection behavior.

> **Takeaway:** `Flux` models a publisher capable of emitting multiple items; a **streaming response** is only achieved when the WebFlux HTTP writer, media type (SSE or NDJSON), subscription, and downstream are all designed properly. In Spring Integration, distinguish `Message<Flux<T>>` from `Flux<Message<T>>`, track backpressure/cancellation across every boundary, and never mistake an open HTTP connection for a reliable event store.
