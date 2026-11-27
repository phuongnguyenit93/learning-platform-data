# Backpressure and HTTP Content Streaming

## 1. The Problem: Data Arriving Faster Than Processing Speed

An API Gateway must receive requests from clients, apply route predicates and the filter chain, and forward them to the appropriate microservice. For small JSON responses, all data can be generated and sent very quickly. However, if a client downloads a multi-gigabyte file, subscribes to real-time events, or receives results from a long query, the approach of **buffering the entire payload into memory before sending** creates three problems:

- **Memory:** a single large request or many concurrent requests can consume RAM beyond the gateway's capacity.
- **Latency:** the client must wait until the entire payload is produced before receiving the first byte.
- **Speed mismatch:** the backend may produce data faster than the network or client consumption rate, causing queues to grow continuously.

**Streaming** allows data to be generated, processed, and transmitted incrementally in parts. **Backpressure** is the mechanism by which the receiving side in an asynchronous pipeline expresses how much data it is ready to accept, thereby pacing the producer. In **Spring WebFlux**, this model is built on Reactor and the Reactive Streams specification. In **Spring Cloud Gateway Server WebFlux**, request/response bodies can be represented as a **Flux<DataBuffer>** stream and forwarded through reactive infrastructure.

The two concepts are related but **not synonymous**: an HTTP response can be streamed while an intermediate layer still buffers too much data; conversely, a Reactor chain with backpressure can still have a **collectList()** operator gather all data before writing the HTTP response.

### Learning Objectives

After this lesson, you will be able to:

1. Explain **request(n)**, **cancel**, and the limits of backpressure in Reactive Streams.
2. Distinguish streaming at the application, HTTP, and transport layers; identify where buffering can occur.
3. Read and design the flow of **Flux<DataBuffer>** through Spring WebFlux and Spring Cloud Gateway.
4. Implement SSE, NDJSON, and streaming upload/download examples and configure routes to proxy them.
5. Avoid accidentally buffering the entire body when writing filters; handle **DataBuffer** lifecycles, timeouts, mid-stream errors, and performance observability.

## 2. The Reactive Streams Backpressure Mechanism

Reactive Streams defines four fundamental roles:

| Component | Role |
| --- | --- |
| **Publisher&lt;T&gt;** | Asynchronous source emitting data |
| **Subscriber&lt;T&gt;** | Receiver of data, errors, and completion signals |
| **Subscription** | Link between publisher and subscriber; allows requesting more data or cancelling |
| **Processor&lt;T, R&gt;** | Combines receiver and producer roles, capable of transforming data |

When a subscriber subscribes, it receives a **Subscription** via **onSubscribe**. The subscriber calls **request(n)** with a positive count to signal demand. The publisher must not emit more elements via **onNext** than requested for that subscription. When no more data is needed, the subscriber can call **cancel()**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe()
    P->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>P: request(1)
    P-->>S: onNext(item 3)
    P-->>S: onComplete()
~~~

In Reactor, **Flux&lt;T&gt;** represents 0..N elements and **Mono&lt;T&gt;** represents 0..1 elements. Many operators such as **map**, **filter**, **flatMap**, **limitRate**, or **publishOn** propagate or adjust demand across stages. When using **flatMap**, remember that the operator can subscribe to multiple inner sources concurrently and maintain internal buffers; the number of elements requested downstream does not necessarily match 1:1 with the total elements requested from every upstream source at any given moment.

### Example Regulating Element Count

~~~java
Flux<Integer> numbers = Flux.range(1, 1000);

numbers.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Received: " + value);
        request(1);
    }
});
~~~

This snippet illustrates how a subscriber initially requests two elements and then requests one more at a time. A few details to remember:

- **request(n)** counts **elements in the stream**, not bytes, TCP packets, or HTTP requests.
- Do not use **Thread.sleep()** inside a reactive callback running on an event loop to simulate a slow client; that blocking call stalls the processing thread.
- The specification defines backpressure at the publisher/subscriber boundary; it **does not guarantee** that every external event producer, socket, or proxy follows the same mechanism.
- **cancel()** can stop publishers that cooperate with cancellation, but an already-dispatched task or external system does not necessarily halt instantaneously.

## 3. Backpressure and HTTP Streaming: Two Different Layers of Mechanisms

At least three layers should be distinguished:

1. **Application/reactive layer:** Reactor propagates demand signals, processes elements one by one, and cancels subscriptions when needed.
2. **HTTP layer:** bodies are transmitted as byte sequences over one or more writes; HTTP/1.1 can use **chunked transfer encoding** when the length is unknown beforehand, while HTTP/2 transmits data via **DATA frames** with its own flow control mechanism.
3. **Transport layer:** TCP has flow control and socket buffers. Socket read/write speeds affect the HTTP infrastructure, but it is not the same API as **Subscription.request(n)**.

~~~mermaid
flowchart LR
    S[Service Publisher] -->|Flux of DataBuffer| G[Gateway]
    G -->|HTTP response bytes| C[Client]
    C -.->|Network flow control / readiness| G
    G -.->|Reactive demand / cancellation| S
~~~

WebFlux and Reactor Netty can coordinate asynchronous reads/writes with demand to avoid storing excessive data. However, **there is no general guarantee that one Flux element corresponds to one HTTP chunk, one TCP packet, or one client read call**. Codecs, HTTP framing, proxies, TLS, compression, buffering, and client speed can all alter how data arrives.

**Example:** A backend emits 1 KB records one by one, the gateway processes asynchronously, and the client reads slowly. If intermediate layers do not buffer the full body, the memory held at each layer can remain much better bounded than loading the whole response into RAM. If a filter calls **DataBufferUtils.join(...)** across the entire body, that advantage is lost at that filter.

### What Does Streaming Improve?

| Aspect | Buffer entire payload before returning | Stream incrementally |
| --- | --- | --- |
| Time to first data | After the full result is ready | Potentially right after the first part is ready |
| Body memory | Can scale with the entire body size | Can stay close to in-flight/buffered data if the path truly streams |
| Client-side handling | Waits for a complete payload | Receives, decodes, and processes incrementally |
| Error mid-response | Usually still able to choose HTTP status before sending | Once headers are sent, the committed status cannot be changed |
| Complexity | Easy to validate payload once | Must handle framing, disconnects, timeouts, and partial results |

Streaming does not automatically make a slow query produce its first element early: the data source itself must support incremental emission for latency benefits to show.

## 4. Types of HTTP Content Streaming

Not all streaming types share the same contract:

| Type | Typical Content-Type | Characteristics | Use cases |
| --- | --- | --- | --- |
| **Raw bytes** | application/octet-stream | Continuous byte stream; application interprets format | File downloads, binary data transfer |
| **NDJSON** | application/x-ndjson | Each line is an independent JSON value; newline-delimited | Query results, large record lists |
| **Server-Sent Events (SSE)** | text/event-stream | Server pushes text/event formatted events over a long-lived HTTP connection | Notifications, progress updates, real-time status |
| **Multipart upload** | multipart/form-data | Multiple parts with separate headers; framework may use buffers or temp files | Uploading files with metadata |
| **WebSocket** | WebSocket protocol upgrade/handoff | Bidirectional communication with its own framing and mechanics | Chat, bidirectional real-time control |

**NDJSON** and **SSE** keep an HTTP response open, allowing consumption of logical units without waiting for the entire list. **SSE** only streams events from server to client over an HTTP connection; the reverse direction uses separate HTTP requests. **WebSocket** has a different bidirectional model and should not be equated with standard HTTP body streaming.

In HTTP/1.1, when a response is sent incrementally without a known upfront length, the server typically uses **Transfer-Encoding: chunked**. For HTTP/2, the **Transfer-Encoding: chunked** header is not used; data is packaged into HTTP/2 frames. **Chunk/frame boundaries are not record boundaries**. With NDJSON, clients rely on newlines; with SSE, clients rely on event formatting, not on the size of a single socket read.

### NDJSON Data Illustration

~~~text
{"id":1,"name":"A"}
{"id":2,"name":"B"}
{"id":3,"name":"C"}
~~~

Each line must be a valid, standalone JSON value. Do not add commas or square brackets like a normal JSON array. Clients can parse each line as soon as a newline character arrives.

### SSE Illustration

~~~text
id: 101
event: order-status
data: {"orderId":"O-42","status":"PAID"}

id: 102
event: order-status
data: {"orderId":"O-42","status":"PACKING"}

~~~

Each SSE event ends with a blank line. Browsers can use **EventSource** to receive events. If recovery after disconnection is required, the backend design must support **event IDs**, store appropriate history, and interpret **Last-Event-ID**; merely adding an **id** field does not automatically provide reliable replay.

## 5. How Is the Body Handled in Spring WebFlux?

In **Spring WebFlux**, the most important low-level API for understanding HTTP streaming is **ServerHttpRequest.getBody()**, which returns **Flux&lt;DataBuffer&gt;**. **ServerHttpResponse.writeWith(Publisher&lt;? extends DataBuffer&gt;)** allows writing buffers incrementally to the response. Spring uses codecs to decode/encode higher-level types such as JSON DTOs, SSE, or strings.

~~~mermaid
flowchart LR
    IN[Request network bytes] --> R[Reactor Netty HTTP server]
    R --> F[Flux of DataBuffer]
    F --> C[WebFlux Handler / Filter]
    C --> B[Service or upstream call]
    B --> O[Publisher of response DataBuffer]
    O --> W[HTTP response writer]
    W --> OUT[Client]
~~~

**DataBuffer** represents a memory region holding bytes. In configurations using Reactor Netty, buffers are often backed by memory managed with Netty **reference counting**. Therefore:

- When you only **forward** a DataBuffer through the chain without holding onto it, let the framework manage its normal lifecycle.
- If you manually retain, transform, drop, or consume a DataBuffer, you must follow the corresponding **retain/release** rules; avoid reading and discarding a buffer without releasing it.
- Do not call **subscribe()** manually inside a filter to "peek" at the body. That subscription can consume the single-use stream, causing races, duplicate processing, or leaving downstream with no body.
- Do not assume the body can be read multiple times; if you must read and modify the body, use a properly designed cache/decorator while accounting for memory cost and maximum size limits.
- Never keep a DataBuffer reference after the publisher has transferred ownership or the buffer has been released.

A helpful rule of thumb: **choose codec/controller-level solutions whenever possible; manipulate DataBuffer directly only when byte-level access is genuinely required**.

## 6. Spring Cloud Gateway Proxying HTTP Streaming

In **Spring Cloud Gateway Server WebFlux**, routes are selected via predicates; gateway filters and global filters participate in request/response processing. In Reactor Netty-based deployments, components such as **NettyRoutingFilter** make HTTP requests to the upstream and **NettyWriteResponseFilter** participates in writing the response back to the client. A forwarding path **does not have to aggregate the entire body** to proxy data.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Spring Cloud Gateway
    participant Upstream as Streaming service
    Client->>Gateway: GET /api/stream/events
    Gateway->>Gateway: Path predicate / filter chain
    Gateway->>Upstream: GET /stream/events
    Upstream-->>Gateway: Headers + event 1
    Gateway-->>Client: Headers + event 1
    Upstream-->>Gateway: event 2
    Gateway-->>Client: event 2
    Note over Client,Upstream: Can continue many events over the same response
    Client-xGateway: Client disconnects
    Gateway-xUpstream: Cancel/close upstream when cancellation propagates
~~~

An illustrative route in Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: streaming-service
              uri: lb://notification-service
              predicates:
                - Path=/api/stream/**
              filters:
                - StripPrefix=1
~~~

Under this example, a **GET /api/stream/events** request is forwarded as **GET /stream/events** to the service. **lb://notification-service** uses the configured instance-lookup/load-balancing mechanism, such as Spring Cloud LoadBalancer and a service discovery source. For quick testing without discovery, you can replace **uri** with a concrete service address like **http://localhost:8081**.

**Version note:** Configuration property structure for Spring Cloud Gateway Server WebFlux varies across generations; some versions use **spring.cloud.gateway.routes** instead of **spring.cloud.gateway.server.webflux.routes**. Check the documentation for the **exact Spring Cloud Gateway version** you are running. Spring Cloud Gateway Server Web MVC also has its own APIs/properties; this lesson focuses on **Server WebFlux**.

### Which Filters Easily Break Streaming?

A simple route with **Path** and **StripPrefix** normally does not need to read the entire body. However, requirements such as **re-signing the entire payload**, **decoding full JSON to rewrite it**, **caching the entire response**, or **reading the body into a String for logging** may require aggregating data and breaking incremental delivery.

Example of an operation to weigh carefully:

~~~java
// Illustrating a risk point: aggregating all buffers into one combined body.
Mono<DataBuffer> aggregated = DataBufferUtils.join(request.getBody());
~~~

**DataBufferUtils.join(...)** produces a result only after the stream completes, or after hitting a limit/error condition. A very large or infinite body is unsuitable for this approach. Overloads exist with a **maxByteCount** limit, but setting a limit only prevents excessive consumption; it **does not turn aggregation into streaming**. When working directly with DataBuffer, manage releases according to the API contract and actual execution path.

Body-transforming filters such as **ModifyRequestBody** / **ModifyResponseBody** should be evaluated individually: depending on data type, codec, and implementation, they may decode the body into objects/chunks before re-writing it. **Do not assume every filter streams simply because the Gateway runs on WebFlux.**

## 7. Hands-on: SSE and NDJSON Through the Gateway

The example below simulates a service emitting events and record lists. The controller uses Spring WebFlux with Reactor:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/stream")
class StreamingDemoController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .event("tick")
                        .data("event-" + i)
                        .build());
    }

    @GetMapping(value = "/records", produces = "application/x-ndjson")
    Flux<Map<String, Object>> records() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(400))
                .map(i -> Map.of("id", i, "name", "item-" + i));
    }
}
~~~

Endpoint **/stream/events** emits five SSE events at one-second intervals; endpoint **/stream/records** emits five JSON objects over time. Each NDJSON object is newline-separated by the encoder matching the response media type. This is a mock data source for observing when each part arrives; in a real system, replace these with event streams or queries **capable of incremental emission**. Clock-driven sources like **Flux.interval** also have specific behavior when downstream is too slow; do not use them as a lossless event queue.

With the route from the previous section, test:

~~~bash
curl -i -N http://localhost:8080/api/stream/events
curl -i -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/stream/records
~~~

The **-N** (or **--no-buffer**) flag tells curl not to buffer output on display; it does not change any buffers that may exist in the server/gateway/proxy. Compare when each line/event appears. If all data appears in one burst at the end, inspect the source, codec, filters, gateway, and upstream proxies one layer at a time.

### Notes When Accessing from a Browser

JavaScript can use **EventSource** for SSE:

~~~javascript
const events = new EventSource("/api/stream/events");

events.addEventListener("tick", (event) => {
  console.log("Event:", event.data, "ID:", event.lastEventId);
});

events.onerror = () => {
  console.warn("SSE disconnected or reconnecting");
};
~~~

Because the example endpoint sends five events and closes the connection, **EventSource** may attempt to reconnect according to browser behavior. In production, explicitly decide whether reconnects are allowed, retry delays, replay strategy, and authentication policy. Since SSE runs over HTTP, concerns like **CORS**, sessions/cookies, tokens, and timeouts still apply.

## 8. Streaming Request Bodies and Uploads

Streaming is not just for responses. Requests can also be byte streams, such as a client uploading a video file to a backend through the gateway.

~~~mermaid
flowchart LR
    U[Uploader] -->|Request body: multiple parts| G[Gateway]
    G -->|Forwards DataBuffers| F[File service]
    F --> D[(Storage)]
~~~

In WebFlux, the low-level request body is **Flux&lt;DataBuffer&gt;**. If upload-handling code calls **collectList()**, unbounded **join()**, or **bodyToMono(byte[].class)**, it risks holding the entire payload in RAM. Likewise, logging the entire request body at the gateway can cause substantial memory spikes when many uploads run concurrently.

For multipart uploads, WebFlux provides **FilePart** to transfer files to a destination without requiring the application to allocate a single byte array holding the whole file:

~~~java
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class UploadController {
    private final Path uploadDirectory = Path.of("uploads");

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<Void>> upload(@RequestPart("file") FilePart part) {
        Path destination = uploadDirectory.resolve(UUID.randomUUID() + ".bin");
        return part.transferTo(destination)
                .thenReturn(ResponseEntity.accepted().build());
    }
}
~~~

This is a stripped-down example: the **uploads** directory must be created, secured with proper permissions, and disk capacity managed; authentication, size limits, and storage error handling are also required. Client-supplied filenames **must never be trusted** to build storage paths directly. With multipart, the framework may buffer part of the content or spill to temporary files depending on configuration, so "not buffering everything on the application heap" does not mean "using zero buffers or disk."

### Two Separate Categories of Limits to Configure

1. **Ingress safety limits:** request/part size, part count, header/form field size, upload duration, disk quota, and concurrent upload count.
2. **In-memory decoding limits:** when WebFlux must decode/aggregate part of a body, settings such as **spring.codec.max-in-memory-size** can cap how much data certain codecs buffer; this **does not replace overall upload size limits**.

If the gateway rejects an oversized request or the backend rejects early, the client should receive an appropriate error. Backpressure does not replace a policy for rejecting over-quota files.

## 9. Writing a Gateway Filter That Observes the Body Without Aggregating Data

The following example illustrates a **GlobalFilter** measuring the number of request-body bytes flowing through consumption. The filter **does not manually subscribe**, **does not store DataBuffers**, and **does not call join**:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class RequestBodyBytesFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(RequestBodyBytesFilter.class);

    @Override
    public int getOrder() {
        return -10;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        AtomicLong bytesSeen = new AtomicLong();

        ServerHttpRequestDecorator request =
                new ServerHttpRequestDecorator(exchange.getRequest()) {
                    @Override
                    public Flux<DataBuffer> getBody() {
                        return super.getBody()
                                .doOnNext(buffer ->
                                        bytesSeen.addAndGet(buffer.readableByteCount()));
                    }
                };

        return chain.filter(exchange.mutate().request(request).build())
                .doFinally(signal ->
                        log.debug("Consumed request-body bytes={}, signal={}",
                                bytesSeen.get(), signal));
    }
}
~~~

**What this example does:** Counts the size of buffers actually consumed through the decorator. This measures **bytes that passed through the publisher**, not proof that the entire body uploaded successfully or that the backend received the exact same byte count. If the request cancels/fails mid-stream, the count may be less than Content-Length. If nothing consumes the body, the count may be 0.

**Checks when applying in practice:**

- Filter ordering must install the decorator before any component consumes the body. A filter may run across different paths; count only requests as needed.
- **doOnNext** only reads **readableByteCount()**, holds no DataBuffer references, and performs no blocking work.
- **doFinally** runs on completion, error, or cancellation. Avoid logging sensitive details and overly high-cardinality metric tags.
- A decorator may be subscribed/read multiple times under special cache/retry configurations; if exact wire byte counts are needed, measure at the appropriate layer and redefine metric semantics.
- Some APIs or packages change across Spring Cloud Gateway versions; verify compatibility with your active stack.

If the goal is merely tracking request counts, latency, and status per route, **prefer built-in metrics/tracing** rather than reading bodies. Only write custom body filters when byte-level signals are genuinely required with clear operational justification.

## 10. Reactor Operators Affecting Backpressure

A reactive pipeline can work functionally yet still buffer heavily. These operators have distinct effects:

| Operator | Effect | Risks or limitations |
| --- | --- | --- |
| **limitRate(n)** | Shapes upstream demand requests into batches | Does not limit HTTP requests/second |
| **flatMap(fn, concurrency)** | Limits how many inner publishers are subscribed concurrently | Still prefetches and buffers; output order can interleave |
| **concatMap(fn)** | Processes inner publishers sequentially | Can reduce throughput if downstream is slow |
| **onBackpressureBuffer(capacity)** | Bounded buffer when receiver cannot keep up | Full buffers require a clearly designed overflow strategy |
| **onBackpressureDrop()** | Drops elements when downstream cannot keep up | Data loss; unsuitable for payments, orders, or audit |
| **onBackpressureLatest()** | Keeps only the latest value when falling behind | Skips intermediate states |
| **collectList() / reduce()** | Aggregates elements into a final result | Waits for stream completion; can consume high memory or never complete |
| **buffer(n) / window(n)** | Groups elements into batches or windows | Introduces extra state/buffering; requires sizing and rate tuning |

Example limiting concurrency of an asynchronous processing step:

~~~java
Flux<Result> results = source
        .limitRate(64)
        .flatMap(item -> processAsync(item), 8);
~~~

Here, **processAsync(item)** is a hypothetical function returning **Mono&lt;Result&gt;**. **limitRate(64)** regulates how the pipeline requests data from upstream; **flatMap(..., 8)** bounds how many inner publishers execute concurrently. Neither is equivalent to Spring Cloud Gateway's **RequestRateLimiter**, which enforces **HTTP request** rate limits.

Never apply **onBackpressureDrop** to data requiring complete processing hoping backpressure will magically fix everything: dropped elements cannot recover themselves. For events that must not be lost, design durable queues, replay mechanisms, and delivery acknowledgments at the proper layer.

### Note on Blocking Operations

Reactor Netty's default path runs on event loops, so calling synchronous JDBC, blocking file reads, or **Thread.sleep()** inside **map**, **doOnNext**, or gateway filters can slow down many other requests. If blocking work cannot yet be replaced, isolate it in a controlled manner, for example:

~~~java
Mono<Result> result = Mono.fromCallable(() -> legacyBlockingCall())
        .subscribeOn(Schedulers.boundedElastic());
~~~

The snippet above only isolates the blocking task; it still consumes finite threads/resources. For streaming proxies, prefer asynchronous I/O APIs or suitable reactive libraries.

## 11. Conditions for True End-to-End Streaming

**End-to-end streaming** requires every critical layer to permit incremental emission:

~~~mermaid
flowchart LR
    A[Data source] --> B[Service / codec]
    B --> C[Gateway filters]
    C --> D[Proxy / TLS / compression]
    D --> E[Client / decoder]
~~~

A single layer can break incremental delivery even if every other layer is reactive. When deploying, check:

1. **Source:** does the database/client library emit results incrementally, or has it already loaded the whole list?
2. **Service:** does the endpoint return **Flux** with the appropriate media type, or did the controller call **collectList()** before returning?
3. **Codec:** does the serializer flush per record/event, or wait for the full body before outputting?
4. **Gateway:** does any route/filter read, rewrite, cache, or log the entire body?
5. **Upstream proxies:** do NGINX, ingress, CDN, WAF, or compression layers buffer responses; are timeouts suitable for long-lived connections?
6. **Client:** does the tool or library buffer output until connection close; is it parsing NDJSON/SSE record by record?

A **Flux** in a method signature is merely a favorable condition, **not sufficient proof** that bytes reach the client incrementally over time.

### Timeouts, Keepalive, and Long-Lived Connections

SSE can keep a response open for a long time. Distinguish:

- **Connection timeout:** time allowed to establish the TCP/TLS connection to upstream.
- **Response/idle timeout:** time waiting for the first response or subsequent data, depending on client/proxy and configuration version.
- **Overall deadline:** maximum duration for an operation to finish; may be inappropriate to apply mechanically to an intentionally continuous stream.

Periodic heartbeats, such as a **: ping** comment line in SSE, help some proxies know the connection is still active, but **do not replace timeout configuration and end-to-end connection testing**. Some gateways/proxies enforce maximum connection lifetimes even when streams send heartbeats.

### Retries and Circuit Breakers

Retrying a streaming request requires special care. If the response has already sent several events to the client, **automatically retrying the entire request** can produce duplicate events or hard-to-merge results. If an upload request breaks mid-way, restarting from byte 0 does not mean it can seamlessly resume from the last received byte. Use application-protocol resume/range, offset, and idempotency mechanisms when needed.

A circuit breaker can prevent new requests from hitting a failing upstream. However, if a stream has already sent headers/bytes before failing, the gateway **cannot rewind and return HTTP 503 for the entire response**. The client must detect the interrupted stream and decide to reconnect, resume, or report partial failure per contract.

## 12. Security and Observability for Data Streams

Spring Cloud Gateway is often the central point for authentication, rate limiting, path/header rewriting, TLS, and tracing. With streaming, pay additional attention to connection lifecycles and in-flight data.

**Authentication/authorization:**

- Authenticate before opening the stream; business services must still enforce authorization on emitted data.
- For long-lived streams, define policies when tokens expire or user permissions are revoked; do not assume an open connection re-authenticates on every event automatically.
- Avoid placing sensitive tokens in query strings since URLs frequently appear in logs, traces, or access histories.

**Resource limits:**

- **Rate limiting** caps HTTP requests, whereas **backpressure** regulates pipeline elements. A single SSE connection is only one request yet can live a very long time, so enforce quotas on **concurrent connections**, max lifetime, and data transfer budgets.
- Bound upload sizes, frame/record sizes, codec buffers, connections, and storage based on endpoint characteristics.
- SSE/NDJSON needs per-event or per-line size limits so an anomalous record cannot force the client/decoder to hold excessive data.

**Observability:**

| Signal | Question answered |
| --- | --- |
| Active streaming connections | How many long-lived connections are currently open? |
| Bytes sent/received | How much data is flowing and in which direction? |
| Time to first byte/event | How long before the client starts receiving data? |
| Event/record rate | How many records are produced and consumed over time? |
| Cancellation/disconnect | How many streams terminate due to client disconnects? |
| Retry/fallback/error midstream | Did errors happen after the response already started? |
| Heap/direct memory, event-loop latency | Is the system buffering excessively or stalling I/O? |

Propagate **trace context** across the Gateway and backends to pinpoint where latency arises. For long streams, looking only at total request completion time does not reflect user experience; also record time to first event and inter-event intervals. Never attach tokens, personal data from bodies, or unbounded-cardinality IDs as metric tags.

## 13. Diagnosing Common Failures

| Symptom | Possible cause | How to check and resolve |
| --- | --- | --- |
| SSE only appears when the request finishes | Codec/filter/proxy/client is buffering | Call the service directly with **curl -N**, then test layer by layer |
| Gateway RAM climbs when proxying large files | Filter reads full body, codec aggregates data, high concurrency | Search for **join**, **collectList**, body logging/caching; enforce size limits |
| Stream cuts off after a fixed interval | Proxy idle timeout, response timeout, or deadline | Check per-hop timeouts; add heartbeats if using SSE |
| Client receives duplicate events after reconnect | Server replays without IDs; retries duplicate content | Design idempotency, event IDs, and replay mechanics |
| Endpoint errors when client is slow | Fast producer, full buffers, source lacks backpressure support | Reduce concurrency, measure demand/buffers, define explicit overflow policies |
| Gateway returns 200 but stream is missing data | Error occurred after headers committed | Log mid-stream errors, inspect server/client logs and resume contracts |
| SSE works locally in dev but fails behind ingress | Proxy buffering, compression, timeouts, different HTTP version | Inspect production infrastructure, headers, and per-event arrival times |
| Slow uploads stall the whole gateway | Blocking I/O on event loop or missing quotas | Use async APIs, bound concurrency, monitor event loops |

Do not rely solely on seeing **Transfer-Encoding: chunked** in a response header to conclude streaming is optimal. Measure **when data reaches the client**, **memory usage**, **connection counts**, **latency**, and **behavior when either side slows down or disconnects**.

## 14. Capstone Lab Exercise

**Scenario:** An ordering system has a Notification service emitting order statuses over SSE, a Report service returning NDJSON with thousands of rows, and a File service accepting uploads—all behind Spring Cloud Gateway.

### Part A — Setup and Routing

1. Create a Notification endpoint returning **Flux&lt;ServerSentEvent&lt;...&gt;&gt;** and a Report endpoint returning **Flux&lt;ReportRow&gt;** with **application/x-ndjson**.
2. On the Gateway, declare routes for **/api/stream/\*\*** and **/api/reports/\*\***; use **StripPrefix** or **RewritePath** so forwarded paths match the backends.
3. Run **curl -N** both through the gateway and directly against the service to compare time to first event/record.

### Part B — Testing Backpressure and Memory

1. Build a client that reads responses slowly in a controlled manner; test multiple concurrent connections in a test environment.
2. Observe heap/direct memory, queue depths, error/cancel events, CPU, and per-route latency.
3. Try adding a **collectList()** in a test endpoint with finite data, then compare time to first byte and memory usage. Never apply such aggregation to an infinite stream.
4. Experiment with **limitRate** and concurrency caps when processing individual records; explain why these are not HTTP rate limiters.

### Part C — Testing Cancellation and Mid-stream Errors

1. Close an SSE client mid-stream and observe whether the subscription/connection cancels.
2. Intentionally trigger an upstream error after a few events have been emitted and observe whether an already-committed response can still change its status code.
3. Route through a real ingress/reverse proxy to verify buffering, timeouts, and reconnects.
4. For uploads, configure explicit size limits and test clients exceeding quota or disconnecting mid-upload.

**Passing criteria:** Evidence that data arrives incrementally; memory does not grow linearly with total stream size along the intended path; resource limits and cancellation/error behaviors are clearly observed; no filter accidentally aggregates the entire body. Never rely solely on a **Flux** method signature or a snapshot of HTTP **200** as proof.

## 15. Key Takeaways

- **Backpressure** in Reactive Streams is the mechanism by which a subscriber communicates demand via **Subscription.request(n)**; this signal applies to **reactive elements**, not network speed or HTTP request counts.
- **HTTP streaming** transmits bodies incrementally; SSE, NDJSON, and raw bytes use different framing. HTTP chunks, TCP packets, and application records do not share one-to-one boundaries.
- **Spring WebFlux** uses **Flux&lt;DataBuffer&gt;** for low-level bodies. Spring Cloud Gateway Server WebFlux can proxy streams without holding the entire payload in memory, provided intermediate components do not actively aggregate them.
- **join**, **collectList**, certain codecs/body filters, proxy buffering, and client buffering can negate streaming benefits; always verify end-to-end.
- **DataBuffer** requires respecting memory lifecycles; avoid manual subscribing, retaining buffers improperly, or performing blocking I/O on the event loop.
- For long streams or large uploads, also design **timeouts, quotas, connection controls, cancellation handling, semantically safe retries, authentication, tracing, and metrics**. Backpressure helps pace data flow, but does not replace resource management and reliability engineering.
