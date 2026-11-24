# Timeouts, Cancellation, and Streaming Response Handling

## 1. Context and Objectives

In the **SPRING_BOOT_INTEGRATION** module, a Spring Boot application integrates with external systems via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. **WebClient** is a Reactive Streams-based HTTP client well suited for composing multiple asynchronous I/O calls, receiving streaming data, or forwarding payloads without buffering entire responses in memory. When using `WebClient`, configuration management, data contracts, transactions, error handling, deduplication, testing, and observability remain the application's design responsibilities.

This lesson in the **WebClient** chapter covers **timeouts, cancellation, and streaming response handling**. These three concepts are related yet non-interchangeable:

- **Timeout**: bounds a network phase, signal wait interval, or total operation duration; expiration can trigger an error signal and cancellation.
- **Cancellation**: downstream signals that it no longer needs data from a subscription; upstream may stop reading and release resources as feasible.
- **Streaming**: receiving multiple consecutive chunks from a response and processing each decoded piece immediately instead of waiting for the full body.

After this lesson, you should be able to:

1. Distinguish **connect timeout**, **response timeout**, **pool acquire timeout**, **Mono.timeout**, and **Flux.timeout**.
2. Explain why `WebClient` sends requests only when subscribed and how cancellation propagates.
3. Handle standard JSON, NDJSON, Server-Sent Events (SSE), and large file downloads.
4. Set memory limits, element bounds, backpressure, and deadlines matching upstream contracts.
5. Explain why cancelling a request does not guarantee cancelling server-side transactions; design retries/idempotency where needed.
6. Test timeouts, stream cancellation, mid-stream errors, and resource cleanup.

## 2. WebClient Execution Model

A call such as **client.get().retrieve().bodyToMono(...)** constructs an asynchronous processing description. With typical cold `WebClient` publishers, the actual HTTP request starts only when subscribed. **Mono** emits 0 or 1 item and terminates; **Flux** emits 0 to many items.

~~~mermaid
flowchart TD
    A["Application service / HTTP controller"] --> B["WebClient request specification"]
    B --> C["Unsubscribed Mono or Flux"]
    C -->|"Subscriber subscribes"| D["Client connector / HTTP transport"]
    D --> E["DNS, pool, TCP, TLS, send request"]
    E --> F["Receive status, headers, and body"]
    F --> G{"Decoding mode"}
    G -->|"bodyToMono"| H["Single object or aggregated result"]
    G -->|"bodyToFlux"| I["Multiple objects / chunks"]
    H --> J["onNext? → onComplete"]
    I --> J
    F -->|"Error"| K["onError"]
    J --> L["Release resources"]
    K --> L
    C -->|"cancel / timeout / take"| M["Cancel subscription"]
    M --> L
~~~

Key Reactive Streams signals:

| Signal | Meaning |
| --- | --- |
| **onSubscribe** | Downstream receives the subscription and can request items |
| **request(n)** | Downstream expresses demand for at most `n` items under Reactive Streams |
| **onNext(value)** | Upstream emits one data item |
| **onComplete** | Upstream finishes successfully |
| **onError(error)** | Upstream terminates with an error |
| **cancel()** | Downstream wants no more data; a subscription control signal, not an upstream terminal signal |

**onComplete, onError, and cancel have different semantics.** When a consumer cancels a stream early, never record a "download succeeded" metric simply because no exception occurred. In a WebFlux controller, generally **return `Mono`/`Flux`** so the framework manages the subscription instead of calling **subscribe()** manually inside services/controllers.

Example:

~~~java
public record StockSnapshot(String sku, int available) {}

public Mono<StockSnapshot> findStock(String sku) {
    return stockWebClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(StockSnapshot.class);
}
~~~

If you call **findStock("SKU-01")** and discard the return value, the request may never execute. Using **.block()** inside a reactive pipeline switches the thread to synchronous waiting, which can block the event loop and trigger runtime errors in WebFlux. Only block at explicitly designed synchronous boundaries, never indiscriminately inside reactive handlers.

## 3. Transport Configuration: Where Network Timeouts Live

`WebClient` is a high-level API; TCP, TLS, pooling, and socket reads belong to **ClientHttpConnector**. Examples below use **Reactor Netty**, a common choice with Spring Boot and WebFlux.

### 3.1. Dependencies and Bean

For a Maven project managing versions via Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring MVC can still use `WebClient` as an HTTP client; adding the WebFlux starter **does not automatically turn all MVC controllers into reactive endpoints**. If the project does not need the entire starter, you can select the appropriate `WebClient` and transport dependencies. Always check dependency management for your exact Spring Boot version.

Example client configuration for inventory queries (Java/Spring imports omitted in the snippet to highlight the API):

~~~java
@Configuration(proxyBeanMethods = false)
public class StockClientConfiguration {

    @Bean
    WebClient stockWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory reactorResources) {

        HttpClient nettyClient = HttpClient
                .create(reactorResources.getConnectionProvider())
                .runOn(reactorResources.getLoopResources())
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                .responseTimeout(Duration.ofSeconds(4));

        return builder
                .baseUrl("https://inventory.example.internal")
                .clientConnector(new ReactorClientHttpConnector(nettyClient))
                .codecs(codecs -> codecs.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
                .build();
    }
}
~~~

Key imports include **reactor.netty.http.client.HttpClient**, **io.netty.channel.ChannelOption**, **org.springframework.http.client.ReactorResourceFactory**, **org.springframework.http.client.reactive.ReactorClientHttpConnector**, **org.springframework.web.reactive.function.client.WebClient**, and **java.time.Duration**.

Meaning:

- **CONNECT_TIMEOUT_MILLIS = 800**: bounds the TCP connection establishment phase in Netty.
- **responseTimeout(4 seconds)**: configures response timeout at the Reactor Netty layer; understand this as **an interval without network read progress** while receiving a response, not an end-to-end business deadline.
- **maxInMemorySize(512 KiB)**: sets the codec decoding buffer cap; not a total network transfer cap.
- Boot-provided **WebClient.Builder** preserves Boot and application customizations such as observations, connector customizers, or filters. When overriding the connector, verify those customizations remain intact.
- **ReactorResourceFactory** reuses Spring-managed pools and event loops when Boot configures Reactor Netty. If the application manages its own **ConnectionProvider/LoopResources**, it must handle their lifecycle and disposal properly.

These numbers are purely illustrative. Choose them based on SLOs, latency percentiles, downstream capacity, and resource limits. Specifically for **long-lived SSE connections**, applying a multi-second response timeout to all requests can break valid streams between events.

### 3.2. Categories of Timeouts

~~~text
Wait to borrow a connection from the pool
   → DNS
   → TCP connect
   → TLS handshake
   → send headers/body
   → wait for response headers
   → read response chunks
   → decode / business processing
~~~

| Timeout / Limit | Scope | Typical Configuration |
| --- | --- | --- |
| **Pending acquire timeout** | Time spent waiting for an available pooled connection | Reactor Netty `ConnectionProvider` |
| **DNS resolve timeout** | Time spent resolving the hostname | DNS resolver/transport |
| **Connect timeout** | Opening TCP to upstream | `ChannelOption.CONNECT_TIMEOUT_MILLIS` |
| **TLS handshake timeout** | Security handshake | Client TLS/SSL configuration |
| **Read/write idle timeout** | No read/write progress within an interval | Netty `ReadTimeoutHandler`/`WriteTimeoutHandler` where suitable |
| **Response timeout** | Transport-level wait policy for response | Reactor Netty `HttpClient.responseTimeout` |
| **Pipeline timeout** | Wait interval for `Mono`/`Flux` signals | Reactor `timeout(Duration)` |
| **End-to-end deadline** | Total budget for an operation across calls, retries, backoff | Service/orchestration and deadline propagation |

For example, Netty's **responseTimeout** differs from **Mono.timeout**: a response may stream chunks over a long period without breaching idle read intervals, whereas **Mono<Void>.timeout(30 seconds)** fails if the entire task exceeds 30 seconds.

**Never treat a simple sum of timeouts as a latency SLA.** If a service retries three times with a 2-second response timeout each, plus pool waits and backoff, total elapsed time can exceed six seconds. Enforce an overall budget at the orchestration layer.

### 3.3. Per-Request Timeout Override

When only one endpoint is permitted a longer response (such as a report), you can configure transport settings per request on Reactor Netty:

~~~java
Mono<ReportStatus> status = stockWebClient.get()
        .uri("/reports/{id}/status", reportId)
        .httpRequest(request -> {
            HttpClientRequest nativeRequest = request.getNativeRequest();
            nativeRequest.responseTimeout(Duration.ofSeconds(12));
        })
        .retrieve()
        .bodyToMono(ReportStatus.class);
~~~

**HttpClientRequest** comes from **reactor.netty.http.client**. This snippet depends on the Reactor Netty connector and is not transport-agnostic across all `WebClient` connectors; for JDK/Jetty/Apache connectors, use their respective configuration APIs. Do not infer system-wide connection timeouts from this request-level timeout.

## 4. Mono.timeout vs. Flux.timeout

### 4.1. Mono: Waiting for a Single Result

Example calling inventory with a call-level deadline:

~~~java
public Mono<StockSnapshot> fetchSnapshot(String sku) {
    return stockWebClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(StockSnapshot.class)
            .timeout(Duration.ofSeconds(3))
            .onErrorMap(
                    TimeoutException.class,
                    ex -> new InventoryCallTimedOutException(
                            "inventory request exceeded 3 seconds", ex));
}

public final class InventoryCallTimedOutException
        extends RuntimeException {
    public InventoryCallTimedOutException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Mono.timeout(3 seconds)** starts counting upon subscription. If no **onNext**, **onComplete**, or valid completion signal arrives in time, Reactor emits a timeout error and cancels the upstream subscription. For `WebClient` reading a JSON object, this typically includes request setup, network round-trip, and object decoding.

However:

- For large responses or downstream work outside this `Mono`, the deadline does not cover subsequent steps.
- Errors from **Reactor Netty `responseTimeout`** can carry a different exception class than Reactor's **`java.util.concurrent.TimeoutException`**; **`onErrorMap(TimeoutException.class, ...)`** does not catch every transport timeout exception.
- Placing **timeout** before **retryWhen** gives each retry attempt its own timeout; placing it outside the **retryWhen** chain bounds the total duration of that chain. Position operators according to the intended business semantics.

### 4.2. Flux: Waiting for the First Element and Gaps Between Elements

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/updates")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .timeout(Duration.ofSeconds(15));
~~~

With **Flux.timeout(Duration)**, the timer applies while waiting for the first item and **between consecutive `onNext` signals**. Every time a new item arrives, the timer resets. Thus, a stream running for hours that emits a message every 10 seconds will never hit a 15-second timeout.

If the goal is to **cap the total time to receive a finite stream**, wait for **onComplete**:

~~~java
Mono<Long> totalItems = priceWebClient.get()
        .uri("/prices/export")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .count()
        .timeout(Duration.ofSeconds(30));
~~~

**count()** completes only when the stream completes, so the outer **Mono.timeout** covers the full completion wait. This suits finite streams; on an infinite SSE stream, it only terminates via timeout without ever producing a natural total.

To actively cap **subscription duration** on a long-lived stream, **take(Duration.ofMinutes(2))** can complete the stream after that window with **onComplete** and cancel upstream. Make explicit that this is a **policy-driven stop**, avoiding confusing `take` completion with receiving all upstream data.

### 4.3. Timeout Failure Modes and Observable Outcomes

| Scenario | Observable Signal | What Is Certain? |
| --- | --- | --- |
| Failed to connect in time | Transport/Netty error | No valid HTTP response; no status code can be inferred |
| TCP established, response silent too long | Response/read timeout error | Server processing outcome cannot be confirmed |
| `Mono.timeout` expires | Reactor `TimeoutException`, upstream cancelled | Caller stopped waiting; server may still be processing |
| `Flux.timeout` expires between events | Reactor `TimeoutException`, stream cancelled | Stream failed to emit events within the expected cadence |
| Consumer calls `dispose()` | Cancel signal on cancellation-observing operators | Does not automatically emit `onError` or guarantee server rollback |
| Upstream closes stream normally | `onComplete` | Stream ended per protocol; completeness depends on contract |

## 5. Cancellation: What Happens When Nobody Wants the Response Anymore?

In Reactive Streams, a subscriber can call **cancel()** to stop demand. Reactor propagates cancellation upstream; `WebClient` and its connector attempt to stop reading data and release associated resources. Cancellation can originate from:

- A browser/client closing a WebFlux connection before a proxied response finishes.
- **take(n)** receiving `n` items and discarding the rest.
- **timeout(...)** emitting `onError` and cancelling upstream.
- **switchMap** cancelling an older stream when a newer selection arrives.
- Calling **Disposable.dispose()** on an application-managed subscription.

Illustration of explicit subscription in a standalone task:

~~~java
Disposable subscription = priceWebClient.get()
        .uri("/prices/updates")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .subscribe(
                price -> processPrice(price),
                error -> recordFailure(error));

// When the application no longer needs this stream:
subscription.dispose();
~~~

**This illustrates cancellation ownership when an application manages its own subscription.** Inside a WebFlux controller or pipeline-called service method, **return `Flux`/`Mono`** rather than subscribing manually and letting a subscription outlive the request lifecycle.

### 5.1. Observing Cancellation Separately from Errors

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/updates")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.recordStreamCancellation("prices");
            } else if (signal == SignalType.ON_ERROR) {
                metrics.recordStreamFailure("prices");
            } else if (signal == SignalType.ON_COMPLETE) {
                metrics.recordStreamCompleted("prices");
            }
        });
~~~

**SignalType** comes from **reactor.core.publisher.SignalType**. **metrics** is an illustrative application-defined component, not a built-in Spring API. **doFinally** runs whenever the pipeline ends via completion, error, or cancellation; **doOnError** only sees errors, and **doOnTerminate** cannot observe cancellations.

For a Reactor-triggered timeout, an operator **above `timeout`** may observe **CANCEL**, while a subscriber **below `timeout`** observes **onError(TimeoutException)**. To avoid double-counting one incident as both "user cancel" and "timeout," align metric placement and labels for cancel vs. timeout sources.

### 5.2. Cancellation Is a Stop Signal, Not a Transaction Rollback

Consider calling:

~~~java
Mono<PaymentResult> paid = paymentWebClient.post()
        .uri("/payments")
        .bodyValue(command)
        .retrieve()
        .bodyToMono(PaymentResult.class)
        .timeout(Duration.ofSeconds(3));
~~~

If the client times out, the POST request may already have arrived in full and the payment service may have committed before the response returned. Cancelling the subscription **does not guarantee the remote server stops processing, deletes data, or rolls back its transaction**.

Therefore:

1. For operations creating/charging/writing orders, use an **idempotency key**, request ID, or status reconciliation.
2. On timeout, never auto-retry a POST unless the API provides an explicit deduplication contract.
3. True business cancellation requires a **dedicated cancellation protocol** on the server, not merely aborting the client HTTP stream.
4. When a message broker retries after timeout, idempotency must hold across redeliveries.

## 6. Consuming Streaming Responses: bodyToMono and bodyToFlux

### 6.1. Choosing the Result Type by Data Format

| Upstream HTTP Contract | Appropriate Read API | Notes |
| --- | --- | --- |
| Small single JSON object | **bodyToMono(MyDto.class)** | Single result, fully decoded |
| Finite JSON array | **bodyToFlux(MyDto.class)** or **bodyToMono(List<MyDto>)** per codec/contract | For large arrays, check actual codec streaming support and item size |
| **application/x-ndjson** | **bodyToFlux(MyDto.class)** | Each JSON object is line-delimited and server must flush |
| **text/event-stream (SSE)** | **bodyToFlux(ServerSentEvent<T>)** | Long-lived connection; supports event IDs and resume if API supports it |
| Large file/binary | **bodyToFlux(DataBuffer.class)** or **DataBufferUtils.write** | Requires policy for byte buffers, partial files, and cancellation |
| No body needed | **toBodilessEntity()** or **bodyToMono(Void.class)** as needed | Never leave bodies unconsumed when handling `ClientResponse` directly |

**`Flux` does not automatically guarantee instant streaming** if the upstream buffers the entire response before flushing or an intermediate proxy buffers bytes. Verify content type, codec behavior, flushing, and proxy configuration in real tests.

### 6.2. NDJSON: Processing Record by Record

Suppose downstream returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"sku":"A-1","price":100}
{"sku":"B-2","price":250}
{"sku":"C-3","price":180}
~~~

DTO:

~~~java
public record PriceChanged(String sku, int price) {}
~~~

Client:

~~~java
public Flux<PriceChanged> streamPriceChanges() {
    return priceWebClient.get()
            .uri("/prices/changes")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(PriceChanged.class)
            .limitRate(64)
            .doOnNext(change -> metrics.recordReceived("price-change"))
            .doFinally(signal -> metrics.recordTerminal(
                    "price-change", signal.name()));
}
~~~

**limitRate(64)** regulates item demand sent upstream within Reactor. It **does not guarantee** the network server or every HTTP proxy immediately throttles sending: OS, connector, codec, or upstream buffers still exist. Monitor memory, producer speed, and concurrent consumers.

**Never call `collectList()` unconditionally** on an unknown-length stream. It buffers every item in memory and forfeits incremental processing. When batching is required, use **buffer(100)**, bounded batches, pagination, or explicit backpressure strategies.

### 6.3. SSE: Long-Lived Streams and Events with IDs

SSE normally uses **text/event-stream**; upstream may emit:

~~~text
id: 91
event: order-progress
data: {"orderId":"O-10","state":"PACKING"}

id: 92
event: order-progress
data: {"orderId":"O-10","state":"SHIPPED"}

~~~

Client:

~~~java
public record OrderProgress(String orderId, String state) {}

public Flux<ServerSentEvent<OrderProgress>> followOrder(String orderId) {
    return orderWebClient.get()
            .uri("/orders/{id}/events", orderId)
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(
                    new ParameterizedTypeReference<
                            ServerSentEvent<OrderProgress>>() {})
            .timeout(Duration.ofSeconds(45));
}
~~~

**ServerSentEvent** is in **org.springframework.http.codec**; **ParameterizedTypeReference** is in **org.springframework.core**. Reading the generic wrapper preserves SSE metadata such as **id**, **event**, and **data**.

For valid streams that can go quiet for longer than 45 seconds, the configuration above will cancel healthy subscriptions unnecessarily. Agree on heartbeat intervals and idle limits with upstream; to resume from a prior offset on reconnect, the API must support event IDs/`Last-Event-ID` or cursors. **Retrying an SSE stream does not automatically resume at the exact offset**, and events before reconnect may be replayed.

Special note: byte-level SSE comment-only heartbeats **do not necessarily emit an `onNext`** in **Flux<ServerSentEvent<T>>**. Thus, `Flux` timeout measures the gap between decoded events, not raw socket activity. Align transport timeouts with real heartbeat behavior.

## 7. Status-Driven Responses with exchangeToFlux

**retrieve()** uses default behavior: HTTP 4xx/5xx creates **WebClientResponseException**, customizable via **onStatus**. When decoding strategy depends on status, use **exchangeToMono** or **exchangeToFlux**.

~~~java
public Flux<PriceChanged> fetchChanges() {
    return priceWebClient.get()
            .uri("/prices/changes")
            .exchangeToFlux(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(PriceChanged.class);
                }
                return response.createException()
                        .flatMapMany(ex -> Flux.error(ex));
            });
}
~~~

**createException()** reads error details to build a `WebClientResponseException` per Spring rules. In other custom branches, explicitly consume or release the response body. With **exchangeToMono/Flux**, Spring checks and releases unconsumed bodies once the returned publisher completes; **never retain `ClientResponse` to decode outside the callback boundary**.

For handling a specific error status:

~~~java
Mono<StockSnapshot> result = stockWebClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 429,
                response -> response.createException())
        .bodyToMono(StockSnapshot.class);
~~~

This remains an HTTP status error, **distinct from network timeouts and JSON decode errors**. Never catch all exceptions and return **Mono.empty()**: doing so conflates "SKU absent" with "upstream broken" and corrupts business decisions.

## 8. Streaming Large Files and DataBuffer

For large files, **bodyToMono(byte[].class)** buffers the entire payload in memory and hits codec limits. Consume **DataBuffer** chunks and write them to a target file instead.

Example downloading to a temporary file for processing after completion:

~~~java
public Mono<Path> downloadExport(String exportId, Path temporaryFile) {
    return exportWebClient.get()
            .uri("/exports/{id}", exportId)
            .exchangeToMono(response -> {
                if (!response.statusCode().is2xxSuccessful()) {
                    return response.createException()
                            .flatMap(ex -> Mono.<Path>error(ex));
                }

                Flux<DataBuffer> body =
                        response.bodyToFlux(DataBuffer.class);

                return DataBufferUtils.write(
                                body,
                                temporaryFile,
                                StandardOpenOption.CREATE,
                                StandardOpenOption.TRUNCATE_EXISTING,
                                StandardOpenOption.WRITE)
                        .thenReturn(temporaryFile);
            })
            .timeout(Duration.ofSeconds(40));
}
~~~

This snippet requires importing **Path**, **StandardOpenOption**, **DataBuffer**, and **DataBufferUtils**; it assumes the parent directory already exists and is writable. **DataBufferUtils.write(Publisher<DataBuffer>, Path, ...)** streams chunks to disk and returns **Mono<Void>** upon completion, avoiding buffering the entire body into a byte array.

In production systems:

1. Write to a request-specific **temporaryFile**, enforcing permissions and disk quotas.
2. Mark the file **COMPLETED** and move/rename it to the final path **only after the full download succeeds**; cancellation, timeout, or mid-stream error leaves partial data.
3. Schedule cleanup/reconciliation of temp files after failures or cancellation without running blocking file I/O on the event loop; do not assume **doOnError** fires on user cancellation.
4. When using **DataBufferUtils.write** overloads returning **Flux<DataBuffer>** or handling raw pooled `DataBuffer` instances manually, track ownership and **release** them after use—especially across thread hops, filters, cancellations, or errors. Call **DataBufferUtils.release** once at the right time; double-releasing is also a bug.
5. Verify **Content-Length**, checksums, or expected item counts if provided by contract, since a truncated stream might still appear to complete depending on upstream/protocol.
6. Enforce **total byte caps**, **time caps**, and **file quotas** in application code if a source can stream indefinitely; **maxInMemorySize** does not replace those caps.

### Pooled DataBuffer Considerations

With Reactor Netty, a **DataBuffer** can wrap reference-counted native memory. When reading or copying buffers directly, release them along the lifecycle:

~~~java
// Small example: process each chunk and always release the buffer.
Flux<Integer> sizes = response.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                return buffer.readableByteCount();
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

The **sizes** example merely counts bytes per chunk to illustrate ownership without persisting content. If operators before **map** can discard buffers, ensure discard/cancellation release handling per Reactor and Spring `DataBuffer` documentation. When using codecs to decode directly into DTOs, `DataBuffer` lifecycles are normally managed by the codec.

## 9. Backpressure, Concurrency, and Memory

Streaming avoids buffering an entire response upfront, yet it does not prevent resource exhaustion. If upstream produces faster than downstream consumes, applications can accumulate thousands of objects or buffers in internal queues.

| Mechanism | Effect | Limitation |
| --- | --- | --- |
| **limitRate(n)** | Regulates item requests sent upstream | Not an HTTP rate limiter and cannot force servers to stop sending immediately |
| **concatMap(...)** | Preserves order and runs one inner sequence at a time per operator semantics | Reduces throughput if downstream is slow |
| **flatMap(fn, concurrency)** | Caps concurrent inner publishers | Must account for ordering, prefetch, and upstream request load |
| **onBackpressureBuffer(maxSize)** | Bounded buffer for sources outpacing demand | Throws error or applies overflow policy when full |
| **buffer(n)** | Collects batches of size `n` | Consumes memory per batch; cap in-flight batches too |
| **take(n)** | Takes at most `n` items and cancels upstream afterward | Intentional stop; does not prove upstream had no more data |
| **maxInMemorySize** | Caps codec buffer per decoded object/unit | Not a total stream byte limit or connection limit |

Example processing price updates while capping concurrent database writes:

~~~java
public Mono<Void> synchronizePrices() {
    return streamPriceChanges()
            .flatMap(
                    change -> priceRepository.upsertIdempotently(change),
                    8)
            .then();
}
~~~

Here **priceRepository.upsertIdempotently(change)** is assumed to return **Mono<?>** and be genuinely non-blocking. If the repository uses blocking JDBC/JPA, never execute it directly on a Netty event loop; offload to a blocking-appropriate executor/scheduler with concurrency limits, or use a reactive data driver.

**flatMap** can process items out of order. If events for the same SKU carry increasing versions, protect correctness with version checks/conditional updates or per-key serialization rather than relying on callback timing. When strict arrival ordering is required, consider **concatMap** or key-based partitioning.

### Avoid Unbounded onBackpressureBuffer

**onBackpressureBuffer()** with no arguments can accumulate vast amounts of data if a consumer stays slow. Prefer bounded variants with explicit overflow strategies and threshold alerts. For payment or ledger events, **dropping** an event is unacceptable; instead, signal an error, pause upstream, or rely on a durable broker.

## 10. Mid-Stream Errors and the Risk of Replaying Data on Retry

A stream may emit 500 events before dropping the connection. If you write:

~~~java
Flux<PriceChanged> updates = priceWebClient.get()
        .uri("/prices/export")
        .retrieve()
        .bodyToFlux(PriceChanged.class)
        .retry(2);
~~~

**retry(2)** resubscribes to **the entire source pipeline** up to two times on error; it does not resume at record 501. If the upstream resends the first 500 records, the application service receives them twice.

Safe stream retries require:

1. **Checkpoints/cursors/`Last-Event-ID`** supported by the upstream.
2. **Idempotency keys** or versions per record to block duplicate side effects.
3. Policies separating transient from permanent errors (never blindly retry 401, malformed JSON, or 422).
4. Explicit retry counts, backoff, jitter, time budgets, and resume capability.
5. Verification that stopping and resuming does not corrupt record ordering.

For a GET returning a **single `Mono` result**, retries are simpler:

~~~java
Mono<StockSnapshot> snapshot = stockWebClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(StockSnapshot.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(error ->
                                error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503))
        .timeout(Duration.ofSeconds(3));
~~~

This retries HTTP 503 at most **twice**, bounded by the outer **timeout**. It does not retry DNS, TLS, or transport timeouts because the filter excludes them. For POST/PUT with side effects, design idempotency before enabling any comparable policy.

### Errors After the HTTP Response Has Started Streaming

If a WebFlux controller streams a **Flux** to a browser, an exception after several events occurs **after the server already flushed HTTP 200 and headers**. At that point, you cannot retroactively change the status code to 503 for already-sent chunks.

The application must define a streaming error contract: closing the connection with an error signal, emitting an **error** SSE event, checkpoint/resume, or status metadata inside payloads. Never silently turn `onError` into `onComplete`, or clients will assume they received complete data.

## 11. Observing Timeouts, Cancellation, and Outcomes Properly

A reliable integration flow separates these metrics:

| Proposed Metric | When Incremented | Distinct From |
| --- | --- | --- |
| **http.client.request.started** | Actual subscription/request start | Number of Java method invocations |
| **http.client.request.timeout** | Timeout at a defined boundary | User cancellation, 4xx/5xx errors |
| **http.client.stream.cancelled** | Cancel signal observed at instrumentation point | `onComplete` |
| **http.client.stream.completed** | Upstream finishes normally | Downstream business processing completion |
| **http.client.stream.failed** | Terminal stream failure | Retries that may still follow |
| **http.client.stream.items** | One decoded item received | Raw network bytes / unique event count |
| **http.client.stream.bytes** | Bytes read/written when reliably measurable | Number of DTOs |
| **http.client.retry.started** | Retry attempt actually starts | Scheduled retry intent |
| **http.client.connection.pending** | Waiting in pool per transport metrics | Business processing duration |

These table names are **proposed metric contracts**, not all automatically emitted by Spring Boot. Use Spring Boot Actuator/Micrometer Observation and Reactor Netty metrics for transport-level latency, status, and pools; add custom business outcome metrics yourself.

**Do not increment a generic "error count" at multiple layers** if the same exception is wrapped across client, service, and handler. Classify using low-cardinality tags such as **downstream**, **operation**, and **error_kind**; never use SKUs, ID-bearing URLs, emails, or `requestId` as metric tags.

When debugging timeouts, trace across stages:

~~~text
WebFlux inbound
  → inventory service
    → WebClient subscribe
      → pool acquire 15 ms
      → connect 80 ms
      → wait for response 1.8 s
      → body decode 40 ms
    → mapping / transaction
  → HTTP response
~~~

**Service-level deadline expiration** and **Netty read idle timeouts** can produce different exception types. Record a normalized **kind** and sanitized root cause in logs/metrics to avoid misdiagnosis.

## 12. Testing Edge Behaviors Missed by HTTP 200 Tests

**StepVerifier** tests reactive signals; **MockWebServer/WireMock** or a real local HTTP test server verifies timeouts and streaming over transport.

### 12.1. Testing Mono.timeout with Virtual Time

~~~java
@Test
void failsWhenMonoHasNoSignalForTwoSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.<StockSnapshot>never()
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

This test verifies Reactor timeout semantics **without networking**. When using virtual time, construct the publisher inside the **withVirtualTime** supplier so the virtual scheduler attaches properly.

### 12.2. Testing Cancellation

~~~java
@Test
void takeCancelsUpstreamAfterTwoElements() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Long> infinite = Flux.interval(Duration.ofMillis(10))
            .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(infinite.take(2))
            .expectNext(0L, 1L)
            .verifyComplete();

    assertTrue(cancelled.get());
}
~~~

This proves **take(2)** propagates cancellation upstream; it **does not** prove an HTTP server stopped writing. Testing network cancellation requires a test endpoint that tracks disconnects alongside the real connector; exact socket close timing varies by OS and transport.

### 12.3. Testing Flux Timeout Between Elements

~~~java
@Test
void streamTimesOutWhileWaitingForNextElement() {
    StepVerifier.withVirtualTime(() ->
            Flux.just("A", "B")
                    .concatWith(Flux.never())
                    .timeout(Duration.ofSeconds(5)))
            .expectNext("A", "B")
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

**Flux.just("A","B")** emits two elements and then **Flux.never()** emits nothing further, so the timeout fires **after the last element** rather than at an absolute stream duration deadline.

### 12.4. Integrating WebClient with a Mock Server

Use MockWebServer/WireMock to simulate realistic scenarios:

| Scenario | Expectation |
| --- | --- |
| Server delays headers | `Mono` timeout or response timeout fires per policy |
| Headers arrive, body stalls or drops mid-stream | Distinguish read idle timeout from end-to-end deadline |
| NDJSON emits many small chunks | Handler processes item by item without full aggregation |
| SSE has long quiet intervals | Healthy stream is not severed when heartbeats/timeouts are properly configured |
| Consumer cancels after `n` events | Upstream subscription cancelled, cancellation metric increments |
| HTTP 503 or 429 | Status mapped and retried strictly per contract |
| HTTP 200 with invalid JSON mid-stream | First items arrive, then stream terminates with `onError` |
| Response exceeds codec limit | `DataBufferLimitException` classified, not fixed by raising limits infinitely |
| File download truncated mid-stream | Partial temp file never published as completed result |
| Stream retried after mid-stream failure | No duplicate side effects; resumes cleanly via cursor/version |

To test **connector timeouts**, use the actual **ClientHttpConnector** and production-equivalent transport settings. Mocking a service method to throw `TimeoutException` tests only business error handling, not whether connections or body streaming are configured properly.

## 13. Common Design Pitfalls

**"Calling the WebClient method already sent the request."** For cold pipelines, requests execute on subscription. Without a subscriber, no network I/O occurs.

**"Mono.timeout and Flux.timeout both cap total duration."** `Mono` waits for one result/completion; `Flux.timeout(Duration)` checks initial wait and gaps between `onNext` items. A continuously emitting stream can run indefinitely.

**"Reactor Netty response timeout is always the full workflow deadline."** It is a transport timeout. You still need a business deadline covering pooling, retries, and backoff.

**"Cancel means the server rolled back."** Cancellation never proves a remote write failed to commit. Operations with side effects need idempotency and status lookup/reconciliation.

**"bodyToFlux always uses constant memory."** Memory still depends on codecs, element sizes, buffers, concurrency, downstream processing, and whether `collectList` is called.

**"No SSE event for 2 seconds means a network failure."** Streams can legitimately pause; configure matching heartbeats and timeouts.

**"retry(3) resumes the stream where it broke."** Retries restart from the beginning unless server and client support cursors/resume. Never assume exact ordering or once-only delivery.

**"onErrorResume should always turn timeouts into empty data."** When an API must distinguish an unavailable upstream from an absent record, empty fallbacks corrupt business behavior.

**"Writing a few chunks to a temp file is enough."** A file is valid only after stream completion and verification; cancellation or errors can leave truncated files behind.

**"No exception means all data arrived."** **take(n)**, **take(Duration)**, or disconnects can stop a stream early while downstream still observes a clean completion signal per operator semantics.

## 14. Checklist for Resilient, High-Load WebClient Integrations

1. Determine whether endpoints return a JSON object, JSON array, NDJSON, SSE, or binary; match `Mono`/`Flux` to the contract.
2. Use the real transport to configure pools, connect timeouts, response/read timeouts, and resource limits.
3. Enforce business-operation deadlines; distinguish total stream deadlines from **inter-event timeouts**.
4. Return `Mono`/`Flux` from services/controllers; subscribe explicitly only at clear lifecycle boundaries.
5. Track **onComplete**, **onError**, and **CANCEL** separately; understand which signals appear above vs. below `timeout`.
6. For write requests, provide idempotency keys and post-timeout/cancel reconciliation procedures.
7. For long streams, cap buffers, concurrency, page sizes, byte counts, and durations; never buffer everything in memory.
8. When using raw `DataBuffer`, manage ownership, release, discard hooks, and temp-file cleanup.
9. Use bounded retries and cursors/checkpoints for streams; enforce deduplication and ordering at the business layer.
10. Test over real transport for delays, cancellations, partial bodies, JSON errors, retries, and server disconnects.
11. Instrument metrics/tracing with bounded tags; distinguish network errors, timeouts, missing data, normal completion, and active cancellations.

**Key mindset:** `WebClient` expresses an **HTTP pipeline executed upon subscription**. Timeouts bound waiting at each layer; cancellation terminates subscriber demand; streaming governs incremental body consumption. Reliable integrations align all three with data contracts, idempotency, and error-recovery strategies.

## References

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive model, streaming, and connectors.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): Reactor Netty, connection/response timeouts, and codec limits.
- [Spring Framework — retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): `bodyToMono`, `bodyToFlux`, and `onStatus`.
- [Spring Framework — exchangeToMono / exchangeToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): status-based handling and response body release.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled `DataBuffer` and memory management.
- [Spring Framework — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): streaming to files and releasing buffers.
- [Reactor Core — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onError`, timeouts, retries, `doFinally`, and cancellation.
- [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/index.html): transport timeouts, connection pools, and resource management.
- [Spring Boot — HTTP Clients](https://docs.spring.io/spring-boot/how-to/http-clients.html): configuring `WebClient`/`ClientHttpConnector` and sharing Reactor Netty resources.
