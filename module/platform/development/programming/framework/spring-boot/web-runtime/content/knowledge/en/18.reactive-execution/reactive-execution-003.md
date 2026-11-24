# Backpressure and Applicability Conditions Across HTTP Boundaries

**Module:** Spring Boot - web-runtime  
**Parent topic:** Reactive execution

## 1. Lesson Objectives and the Problem to Solve

A reactive HTTP system typically traverses multiple layers: client, proxy, network socket, HTTP codec, handler, service, database, or external services. When one side produces data faster than the receiving side can process it, queues can grow, memory gets consumed, and latency degrades. **Backpressure** is the mechanism by which a receiver signals its consumption capacity to a producer and limits the amount of in-flight data in the system.

After this lesson, you should be able to:

1. Understand **demand** in Reactive Streams and how **Flux/Mono** propagates **request(n)** signals opposite the direction of data flow.
2. Identify the **HTTP boundaries** where demand can influence read/write speed, and where it is **no longer** a Reactive Streams signal.
3. Distinguish between **element-based backpressure**, **byte-based TCP flow control**, **HTTP/2 flow control**, **buffering**, and **rate limiting**.
4. Apply these principles with Spring WebFlux/Reactor Netty, WebClient, streaming requests/responses, and suitable data sources.
5. Recognize points that break the mechanism: switching to blocking APIs, collecting entire payloads, producers ignoring demand, buffering proxies, unbounded queues, or non-streaming consumers.

**Core thesis:** Returning a **Flux** or enabling Spring WebFlux only creates the conditions for demand-driven processing. It **does not automatically guarantee end-to-end backpressure from browser to database**. Each real connection segment must be examined individually.

## 2. The Reactive Streams Mechanism: Data Flows Forward, Demand Flows Backward

Reactive Streams defines four core roles:

- **Publisher<T>**: the source publishing elements of type T.
- **Subscriber<T>**: the receiving side consuming elements.
- **Subscription**: the registration link, providing **request(long n)** and **cancel()**.
- **Processor<T,R>**: both receiver and publisher (protocol concept; in Reactor, operators typically fulfill the corresponding intermediate role).

A basic chain:

~~~text
DATA:           source --- onNext(T) ----> operator ----> consumer
DEMAND:         source <-- request(n) ---- operator <---- consumer
CANCEL:         source <-- cancel() ------ operator <---- consumer
~~~

Typical sequence: the receiver **subscribes**, receives **onSubscribe(subscription)**, calls **request(3)**, and upstream is then permitted to emit **at most three onNext elements** corresponding to that demand. After consuming them, the receiver may request more or cancel the subscription. The Publisher emits **onComplete** when data finishes, or **onError** on failure; terminal signals are not data elements counted against request(n).

Important rules:

- **n must be positive** when calling request(n); zero or negative values violate the Reactive Streams contract and trigger an error signal.
- Demand accumulates by the number of elements permitted to be received, not bytes or milliseconds. **request(10)** does not mean "10 KB" or "10 HTTP requests/second".
- **Long.MAX_VALUE** represents unbounded demand. Convenience subscription methods such as **subscribe()** typically issue unbounded demand; in that case you cannot infer the consumer is throttling emission element-by-element.
- Some operators **reshape demand**: **buffer(10)** receiving demand for 2 buffers may request 20 elements upstream; **flatMap** and **publishOn** use prefetching; **limitRate** splits large requests into smaller batches.
- **cancel()** stops a subscriber's interest in a source, but cannot "recall" data already sent over the network, written to a queue, already processed, or committed in another system.

**Backpressure differs from throughput rate:** demand is permission to emit a number of elements. If a subscriber requests 1,000 elements and then processes very slowly, the source may already have pushed many elements into valid buffers. Achieving stable load also requires bounding concurrency, memory, timeouts, and downstream capacity.

## 3. Three Throttling Layers Commonly Confused

| Layer | Unit | Typical mechanism | What that layer guarantees / does not guarantee |
| --- | --- | --- | --- |
| **Reactive Streams** | Element count T | Subscription.request(n), cancel() | Throttles onNext between contract-compliant Publishers/Subscribers; does not send request(n) verbatim over HTTP. |
| **TCP Transport** | Bytes and send/receive windows | Receive window, send buffer, socket writability | Limits bytes transmitted when a peer cannot read fast enough; has no awareness of JSON objects, business events, or Flux element counts. |
| **HTTP/2** | Bytes in DATA frames per connection/stream | WINDOW_UPDATE, flow-control window | Throttles DATA body bytes between two HTTP/2 peers; does not replace Reactive Streams or application quotas. |

**HTTP/1.1** has no per-stream flow control like HTTP/2; it can stream bodies via **Transfer-Encoding: chunked** or other framing, though transmission remains governed by TCP. **HTTP/2** multiplexes multiple streams over one connection and features DATA frame flow control. Both can back a reactive WebFlux pipeline if the HTTP stack, sources, and sinks are suitable.

**TLS/HTTPS** encrypts the transport; TLS does not turn request(n) into a new application-layer rate-control signal. **Rate limiting** (e.g., max 100 requests/sec) caps traffic over time, usually at an API Gateway; it is not equivalent to backpressure on an open streaming body.

## 4. Identifying Exact HTTP Boundaries

Consider two common paths.

**A. Server sending a streaming response:**

~~~text
Database/reactive source
          |
          v   Flux<Item>
Business operators / WebFlux HTTP encoder
          |
          v   Byte buffers / HTTP DATA or chunked body
HTTP server connector (e.g., Reactor Netty)
          |
          v   Socket, TCP, TLS
Load balancer / reverse proxy (may buffer or switch protocols)
          |
          v
Client HTTP decoder -> browser/app consumes data

request(n) can propagate backward within each process's reactive pipeline;
socket writability, TCP window, and HTTP/2 window throttle at the network boundary.
There is no single shared Subscription.request(n) spanning across hosts.
~~~

**B. Server receiving a streaming request body:**

~~~text
Client sends request body
          |
          v
Socket / HTTP server / decoder
          |
          v   Flux<DataBuffer> or Flux<Item>
Controller -> service -> storage/processor
          |
          v
Subscriber completes work
~~~

When the application processes the body incrementally and the upstream connector links demand to socket reads, backpressure can help slow down further reading/decoding. Still, clients and proxies may already have sent or buffered data ahead of time. You cannot count **request(n)** calls on the server and assume a one-to-one mapping to TCP packets or JSON lines the client just sent.

**An HTTP boundary can only be considered capable of useful throttling when all of these conditions hold simultaneously:**

1. Data can be **emitted/received incrementally**, rather than needing to aggregate the entire payload before decoding or processing.
2. The connector and codec **link demand with non-blocking I/O read/write readiness**, or at minimum apply bounded queues instead of silently growing memory without limit.
3. The Publisher **honors demand**, or when a source cannot slow down, applies an **explicit overflow policy** (bounded buffer, drop, latest, or error/cancel).
4. Operators and downstream code do not break incremental flow with **collectList**, **block**, unbounded queues, excessive prefetch/concurrency, or blocking adapters.
5. Outside the process, **proxies/clients** must be verified for buffering and consumption behavior; an HTTP path may split into multiple connections with different policies.

These conditions form a capability-assessment framework. Each library/adapter has specific details; do not infer infinite memory safety or overload immunity merely from the word "reactive".

## 5. How Spring WebFlux and Reactor Netty Connect Demand to HTTP

In Spring WebFlux, controllers can return **Flux<T>**, **Mono<T>**, or accept **Flux<T>** from a request body. Spring provides **HttpHandler** and non-blocking HTTP adapters. With **spring-boot-starter-webflux**, the common default Spring Boot configuration is Reactor Netty; WebFlux also has adapters for other compatible containers.

On responses, Spring uses **HttpMessageWriter/Encoder** to turn logical elements into byte buffers. The server connector sends those bytes to the socket. Downstream demand can limit how much data the publisher needs to generate; when transport slows down, the write layer can throttle consumption depending on the connector, buffer sizes, and writability.

On requests, **HttpMessageReader/Decoder** turns the byte stream into elements of **Flux<T>**. With **application/x-ndjson**, multiple JSON objects on separate lines can be decoded as individual elements. With a JSON array or body aggregated into a single object, the application may have to consume/buffer a large amount before producing the resulting element; distinguish **streaming framing** from an aggregated request body.

**Key takeaway:** Spring Framework provides a backpressure-capable model, yet there is no fixed ratio like **1 request(n) = 1 TCP read = 1 socket write**. A network chunk can hold multiple objects or one object can span multiple chunks; TLS, codecs, flush policies, and Netty buffers further reshape byte boundaries.

### Server Sending Data

- **Flux<Item> with NDJSON**: suitable for lists of events/objects that can be read incrementally; clients must parse line-by-line rather than using an API that buffers the whole body.
- **Flux<ServerSentEvent<T>> with text/event-stream (SSE)**: suitable for server-to-client notification feeds; slow receivers, proxy buffering, disconnects, and heartbeats still need management. Browser EventSource has no Reactive Streams request(n) API.
- **Flux<DataBuffer>**: suitable for large byte/file streams requiring close I/O control, though it demands manual buffer lifecycle management if handled directly.
- **Mono<T>**: a single value/response; may still be non-blocking, but is not a multi-element example for observing sequential demand.

### Server Receiving Data

- **@RequestBody Flux<Item>**: processes a body as multiple records if codec/content type supports it. Do not call collectList() unless business requirements demand having all records upfront.
- **Flux<DataBuffer>**: processes uploads buffer-by-buffer, streaming to storage if storage supports it; watch body limits, decode errors, cancellation, and buffer release when handling buffers directly.
- For bodies that must be read completely before processing (e.g., whole-payload signatures, large single JSON objects), per-record streaming may not hold. Enforce size and memory limits rather than assuming effective backpressure exists.

## 6. Spring Boot 3.x, Java 17+ Demo: One Stream Response and One Stream Request

**Prerequisites:** Create a Spring Boot 3.x project with Java 17+ and dependency **org.springframework.boot:spring-boot-starter-webflux** (along with Jackson provided by the starter). Use only the WebFlux starter for the Reactor Netty demo; adding **spring-boot-starter-web** as well causes Spring Boot to typically prefer Servlet/MVC, changing the actual stack.

Create file **src/main/java/com/example/boundary/BoundaryDemoApplication.java**:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class BoundaryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }

    @GetMapping(value = "/feed", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Event> feed() {
        return Flux.range(1, 100)
                .map(i -> new Event(i, "event-" + i))
                .doOnRequest(n ->
                        System.out.println("source requested " + n))
                .limitRate(8);
    }

    @PostMapping(
            value = "/ingest",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ingest(@RequestBody Flux<Event> input) {
        return input.limitRate(8)
                .count()
                .map(count -> "received=" + count);
    }

    public record Event(int id, String label) {}
}
~~~

**Why is this code meaningful?**

- **Flux.range(1, 100)** is a finite, Reactive Streams-compliant source allowing observation of upstream demand in a stable environment; **Event** is a Java record that Jackson can serialize/deserialize.
- **application/x-ndjson** represents each JSON object on its own line, suitable for streaming responses and streaming requests. This is a **sequence of objects**, not one JSON array wrapping everything.
- **limitRate(8)** splits upstream demand into smaller batches, replenishing when a batch is nearly consumed. It **does not** mean 8 items/sec or a hard cap of 8 items across all system buffers.
- **doOnRequest** sits **before** limitRate, so it observes demand sent by the operator to the source. That log shows operator behavior, **not TCP packets or HTTP/2 windows**.
- **count()** in the ingest endpoint counts elements before returning a result. It aggregates to a number without needing to retain all Events; however, the response still only appears once the input body finishes.

Run the application from a project with a matching Gradle wrapper and Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

Test pulling the response stream:

~~~bash
curl -sS -N -H "Accept: application/x-ndjson" http://localhost:8080/feed
~~~

The **initial** JSON content output corresponds to:

~~~json
{"id":1,"label":"event-1"}
{"id":2,"label":"event-2"}
{"id":3,"label":"event-3"}
~~~

Remaining records up to id 100 follow; flush timing and demand log output vary by server/transport. **-N** tells curl not to buffer terminal output; it **does not** force the server to send one packet per record or prove that slow TCP caused backpressure.

Test sending two records in a request body:

~~~bash
printf '{"id":1,"label":"a"}\n{"id":2,"label":"b"}\n' |
  curl -sS -H "Content-Type: application/x-ndjson" \
       --data-binary @- http://localhost:8080/ingest
~~~

Expected response output:

~~~text
received=2
~~~

**@-** instructs curl to read the body from standard input. In Windows PowerShell, replace **printf/pipe** with a UTF-8 file containing the two NDJSON lines and pass **--data-binary @items.ndjson**; the Java application and HTTP contract remain identical.

**Demo limitations:** Flux.range emits far too quickly to simulate a genuinely slow consumer. It demonstrates that demand can be shaped in Reactor and that endpoints can stream-encode/decode bodies. Proving backpressure propagates to the transport requires additionally measuring queue sizes, buffers, memory usage, socket writes, slow-reading clients, and proxy settings under controlled load.

## 7. Testing Element-Based Demand with reactor-test

To verify the Publisher contract precisely, add the test dependency with the version managed by Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

This is a **dependencies** snippet for Gradle Groovy DSL in a project already configured with appropriate plugins/repositories, not a complete build.gradle file.

Create **src/test/java/com/example/boundary/DemandTest.java**:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {

    @Test
    void honorsRequestedElementCount() {
        StepVerifier.create(Flux.range(1, 5), 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.boundary.DemandTest
~~~

The test starts with demand **0**, requests 2 elements, asserts 1 and 2, and only then requests the remaining three. A passing test confirms **the Publisher under test** honors the demand contract. This test **does not** prove an HTTP connector, proxy, browser, or database shares one unified demand; verifying an end-to-end path requires measuring each boundary directly.

## 8. WebClient and Client-Side HTTP Boundaries

Spring WebFlux's WebClient also supports non-blocking Reactive Streams processing. A receiving snippet:

~~~java
WebClient client = WebClient.create("http://localhost:8080");

Flux<BoundaryDemoApplication.Event> events = client.get()
        .uri("/feed")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(BoundaryDemoApplication.Event.class);
~~~

This is an **illustrative code snippet**, requiring imports for **org.springframework.web.reactive.function.client.WebClient** and **org.springframework.http.MediaType**, placed inside a class/method of a WebFlux app; it is not a standalone Java program. **bodyToFlux** lets downstream consume items incrementally and generate demand in the WebClient pipeline. Conversely, **bodyToMono(List<...>)**, **collectList()**, or processing the whole response upfront intentionally buffers elements.

A Spring WebFlux application acting as **A calling B** can maintain reasonable demand-driven pipelines when A does not block the event loop, B streams results, and both use demand-respecting sources/sinks. Over the network, however, A and B still communicate via HTTP/TCP buffers rather than passing a Subscription object from one JVM to another. If an API Gateway or cache sits in between, verify its streaming/buffering behavior separately.

Note that **subscribe()** and **blockLast()** from external code can request unbounded data; inside a Spring WebFlux handler, never call **block()** to wait on WebClient, JDBC, or futures on the event loop. Return **Mono/Flux** so the framework manages the asynchronous chain, or establish a proper boundary for blocking tasks.

## 9. Operators That Easily Break Backpressure Capability

| Component | Actual behavior | Risks / usage notes |
| --- | --- | --- |
| **limitRate(32)** | Splits upstream demand into batches and replenishes at a threshold. | Not a time rate limit or total memory cap; only acts where the operator sits. |
| **flatMap(mapper, concurrency, prefetch)** | Runs multiple inner sources concurrently; concurrency/prefetch set design limits. | Excessive concurrency/prefetch increases in-flight work and buffers; tune to real resources. |
| **publishOn(scheduler, prefetch)** | Moves signal processing onto a scheduler with a queue/prefetch. | Introduces a queue at the scheduler boundary; downstream demand does not equal upstream demand at all times. |
| **buffer(n), window(n)** | Groups or splits data into logical batches. | Group demand differs from element demand; may request n elements per buffer. |
| **collectList(), sort()** | Requires all elements before emitting the final result or sorting completely. | Can hold nearly the entire input in memory, losing output streaming benefits. |
| **onBackpressureBuffer(...)** | Provides a buffer when producer outpaces consumer. | Unbounded variants can blow up memory; use bounded buffers with an explicit overflow policy if required. |
| **onBackpressureDrop / onBackpressureLatest** | Selectively discards elements when demand is insufficient. | Suitable only when dropping/latest-only data is acceptable (e.g., live telemetry), unsuitable for transactions requiring every event. |
| **retry / repeat / cache / replay** | Re-executes or retains results. | Can amplify request/source load or retain data; enforce limits and check idempotency. |
| **subscribe() in a service** | Starts an independent subscription. | Breaks caller control over cancellation, errors, and demand; normally return the Publisher instead of subscribing manually. |

Pay special attention to **Flux.create**, callback APIs, push sources from message brokers, or third-party client SDKs: not every source can naturally pause. If a producer cannot slow down, you must choose between **bounding queues, rejecting/cancelling, durable persistence, or intentional dropping**. Wrapping a push source in a reactive operator does not make it truly pull-based.

## 10. Applicability Conditions by Boundary Type

### 10.1 HTTP/1.1 and HTTP/2

**HTTP/1.1:** responses can stream via chunked encoding, and TCP slows the sender if the receiver cannot read fast enough. Suitable for NDJSON/SSE, though middleboxes along the path may buffer. There is no **request(n)** mechanism in the HTTP/1.1 protocol.

**HTTP/2:** DATA frames have flow-control windows per **stream** and **connection**. Peers update byte capacity via **WINDOW_UPDATE**. This provides operational benefits for multiplexing, yet window bytes are not processed Java Events. A proxy terminating HTTP/2 on the client side and forwarding HTTP/1.1 to the backend creates **two independent segments**.

Enabling **server.http2.enabled=true** in Spring Boot does not prove the pipeline has end-to-end backpressure; protocol version and demand are separate concerns.

### 10.2 SSE (Server-Sent Events)

SSE suits long-lived, unidirectional server-to-client notification streams, though browser **EventSource** does not emit **request(n)**. JavaScript clients may process events slowly while libraries/proxies/browsers still buffer. Use heartbeats on long connections to detect disconnects; cap subscribers, memory, pending events, and slow-subscriber policies. If every event is critical, use bounded resume/replay with event IDs rather than arbitrary dropping.

### 10.3 WebSocket

WebSocket enables bidirectional messaging over long-lived connections; a reactive API can expose **Flux** for incoming/outgoing messages, yet the WebSocket protocol does not carry Reactive Streams **request(n)** directly between peers. TCP and buffers still have limits; fast producers must manage outbound queues, downstream subscriptions, and client message capacity.

### 10.4 Reverse Proxy / CDN / API Gateway

Proxies may buffer an entire response in RAM or on disk before forwarding—**response buffering**, **request buffering**, protocol translation, compression/decompression, or blocking specific stream styles. When a proxy buffers, the backend may see the proxy as a fast consumer even while the browser reads very slowly. Inspect settings and measure both **browser↔edge** and **edge↔Spring Boot**. Adjusting buffering must weigh security, resources, observability, and real costs.

### 10.5 Database, Filesystem, and Outbound Services

Backpressure only slows producers if the **upstream source** supports it or is throttled at a queue. Reactive database drivers supporting cursors/fetching to some extent behave very differently from blocking JDBC returning a large list. Files, object storage, and message brokers also have distinct read-ahead, batching, and acknowledgement mechanics. Use suitable drivers/clients, handle cancellation, bound in-flight data, and preserve transaction semantics.

### 10.6 Blocking Boundaries and Servlet MVC

A **JDBC** call, **RestTemplate**, blocking file I/O, or heavy CPU work on the Netty event loop can stall **every connection** sharing that thread. If the library cannot be replaced yet, isolate blocking work on an appropriate scheduler like **Schedulers.boundedElastic()**, while capping concurrent tasks and queues within capacity. **boundedElastic** does not make JDBC reactive; it only moves waiting to another thread under a finite budget.

Spring MVC supports several async/streaming patterns, yet Servlet write mechanics and adapter behavior differ from WebFlux on Reactor Netty. Do not assume that merely returning Flux or DeferredResult from an MVC controller creates a unified Reactive Streams contract across the HTTP stack, codecs, and backend.

## 11. Memory, Errors, and Cancellation: Backpressure Cannot Replace Resource Protection

**Payload aggregation:** **bodyToMono(byte[])**, **collectList()**, or decoding JSON into one huge object can all demand massive memory. Spring codecs support **maxInMemorySize** to cap corresponding decoding/buffering scenarios, though that is not a whole-app quota; any custom buffering or queuing must impose its own limits.

**DataBuffer:** With Reactor Netty, byte buffers can be pooled/reference-counted. When directly manipulating **Flux<DataBuffer>**, filtering, dropping, or cancelling in custom branches, follow **DataBufferUtils.release** and buffer ownership rules to avoid direct memory leaks. When using standard codecs to decode POJOs, the framework handles most buffer management.

**Errors and cancellation:** When a consumer cancels a stream or a client disconnects, observe **doOnCancel**, **doFinally**, close cursors/files/subscriptions, and clean up resources properly. Never rely solely on immediate cancellation delivery: the OS/proxy may still hold buffers, and already executed side effects may be irreversible.

**Load limits:** Combine connection caps, timeouts, concurrent-request caps, body size limits, queue limits, batch sizes, retry budgets, memory/CPU headroom, and source throttling. If events cannot be lost, prefer durable queues and acknowledgement/replay mechanisms instead of **onBackpressureDrop**.

**Observability:** Track p95/p99 latency, active connections/streams, pending writes, queue depth, subscription counts, cancellations/errors, throughput, heap/direct memory, CPU, proxy latency, pending elements, and database latency. Logging **doOnRequest** only shows one pipeline segment; pair it with network metrics to understand real limits.

## 12. Designing Tests to Avoid False Conclusions

A solid test plan separates at least three questions:

1. **Does the Publisher honor the demand contract?** Use **StepVerifier.create(flux, 0)**, request in batches, verify nothing emits without demand, and verify terminal/cancel handling. This is unit-level (Section 7).
2. **Does the HTTP adapter stream data?** Use **WebTestClient** or an HTTP client able to read bodies incrementally, pick the right **Content-Type**, observe when elements arrive, and test early client cancellation. If a test helper buffers the whole response, the helper masks streaming behavior.
3. **Does a slow-reading client cause unbounded buffer/queue growth?** Run controlled load through proxies/ingress, throttle the client, and inspect memory, sockets, connectors, queues, cancellations, and throughput. Never conclude anything from a single localhost curl because OS/codecs easily buffer small payloads.

Measure **HTTP/1.1** and **HTTP/2** separately while holding payload, client count, concurrency, TLS/proxy, network latency, and item size constant. If the source is a tiny in-memory Flux.range, it may complete before network backpressure becomes a bottleneck. Use a dataset large enough yet **safely bounded** with an explicit cancellation policy.

## 13. Deployment Diagnostic Table

| Symptom | Hypothesis to check | Practical action |
| --- | --- | --- |
| Heap grows rapidly when using Flux | collectList, cache, unbounded buffer, high concurrency/prefetch | Profile allocations and queues, switch to streaming/bounded collections where appropriate. |
| Direct memory increases | Unreleased DataBuffers, outbound network queues | Audit pooled buffer ownership, leak detector, Netty metrics, and cancel paths. |
| doOnRequest always shows Long.MAX_VALUE | Terminal subscriber/operator requested unbounded demand | Check log placement and operators, use StepVerifier to test demand control; do not equate with unbounded memory usage. |
| curl receives the entire response at the end | Codec content type aggregates, proxy buffering, or client buffering | Use appropriate NDJSON/SSE; verify headers, flushing, proxy config, and client. |
| One slow client overloads the server | Unpausable push source, large queues, many concurrent streams | Bound connections/queues, set overflow policies, timeouts, and resource budgets. |
| Backend sees HTTP/1.1 despite browser using HTTP/2 | Proxy translates protocols across two hops | Measure both hops separately; HTTP/2 does not dictate Reactive Streams support inside a service. |
| Blocking timeouts under load | JDBC or blocking HTTP calls running on the event loop | Measure blocked event loops; switch to non-blocking drivers or bounded isolation. |
| Subscriber cancels yet upstream keeps working | Source does not support cancel, side effects already started, or pre-filled buffers | Inspect cancellation hooks, cleanup, rate/concurrency, and source cancellability. |
| Adding onBackpressureBuffer initially hides errors then causes OOM | Buffering converted pressure into RAM growth | Set bounded buffers, explicit overflow policies, and fix the overload source. |

## 14. Scenario Exercises and Self-Check

**Scenario A:** An API returns 500,000 database records as a Flux, yet the service calls collectList() before serializing a single JSON array. Why does the response stop streaming effectively? Because **collectList** retains every record until the source completes and builds a list, spiking memory; consider serializing per-record with NDJSON or streaming at an appropriate boundary, and verify driver demand support.

**Scenario B:** A browser connects via SSE through a proxy; server logs show few requests and stable memory, yet users see events arrive in bursts. What is the likely cause? **Proxy/client buffering or flush policy**. Measure both segments before tweaking Flux backpressure.

**Scenario C:** A Flux processes file uploads per DataBuffer, and over time direct memory rises. Where should you look? Inspect **consume/drop/cancel paths for pooled DataBuffers**, buffer releases, and connector queues; proper demand does not preclude leaks.

**Scenario D:** A client only processes 10 items/sec while the server emits 1,000 items/sec. Is adding limitRate(10) enough? **No.** limitRate limits **the number of elements requested per batch**, not 10 items/sec. You need demand-driven consumption, bounded in-flight work, queue protection, and measurement across transport/proxy boundaries.

End-of-lesson questions:

1. Is demand **request(5)** measured in bytes or elements?
2. Why doesn't **request(n)** automatically cross between two hosts over HTTP/2?
3. Is TCP flow control aware of business messages/events?
4. Why can an endpoint returning **Flux** still cause an OOM?
5. When is **drop/latest** allowed, and when is durable storage mandatory?
6. To verify backpressure when a browser reads slowly, which segments must you measure?

**Suggested answers:** (1) elements; (2) Reactive Streams is an in-pipeline contract, whereas HTTP/2 only performs byte-level flow control; (3) no; (4) sources/codecs/operators/proxies/queues can buffer or break streaming; (5) drop only when business rules tolerate data loss, whereas critical data needs durable storage/acks/controlled retries; (6) publisher/operators/HTTP connector, sockets/proxies and client, plus memory/queues.

## 15. Authoritative References

- **Reactive Streams Specification:** https://www.reactive-streams.org/ and https://github.com/reactive-streams/reactive-streams-jvm (Publisher, Subscriber, request, and cancel contracts).
- **Project Reactor Reference – Backpressure:** https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html (how requests propagate upstream, unbounded demand, limitRate, prefetch).
- **Spring Framework – WebFlux Reactive Core:** https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html (non-blocking I/O, HttpHandler, adapters, codecs/buffering).
- **Spring Framework – WebClient:** https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html (reactive HTTP client, body streams).
- **Spring Framework – Data Buffers and Codecs:** https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html (DataBuffer ownership and release).
- **RFC 9113 – HTTP/2:** https://www.rfc-editor.org/rfc/rfc9113 (frames, streams, and byte-level flow control).