# Simulating Slow Connections, Disconnects, and Timeouts in Spring WebFlux Testing

**Module:** Spring Framework – reactive  
**Parent topic:** WebFlux Testing  
**Lesson:** Simulating slow connections, disconnects, and timeouts

## Learning objectives

After this lesson, you will be able to:

1. Classify "slowness" across DNS, TCP connect, TLS handshake, waiting for response headers, reading response chunks, sending request bodies, and waiting for the next item in a stream.
2. Choose the right testing layer: `StepVerifier`, `WebTestClient.bindToController`, a real HTTP server with `RANDOM_PORT`, or a fake upstream HTTP server capable of socket-level control.
3. Use `Mono.delay`, `Flux.interval`, and `StepVerifier.withVirtualTime` to simulate **logical delays** without turning unit tests into network measurements.
4. Use `MockWebServer` to delay headers/bodies, throttle transfer rates, and force-close connections mid-response.
5. Distinguish `WebTestClient.responseTimeout`, `Mono.timeout`, Reactor Netty `responseTimeout`, TCP connect timeout, pool acquire timeout, and test harness time limits.
6. Test reactions to timeouts or subscription cancellation: error mapping, fallbacks, upstream cancellation, and resource cleanup.
7. Test HTTP streaming (SSE) and slow uploads with `WebClient`/`Flux` without buffering the whole stream in RAM.
8. Write complete examples with Java 17+, Spring Boot 3.3.5, Reactor Test, WebTestClient, and MockWebServer on a random port.
9. Design CI-resilient tests: bounded durations, no external IPs, no `Thread.sleep` for logic synchronization, asserting error contracts rather than stack traces.
10. Understand what **cannot** be concluded from a single test: cancel does not guarantee database rollback, closing a socket does not automatically prove every resource was freed, and mock tests do not verify TCP behavior.

## 1. Where can slowness happen in a WebFlux request?

An HTTP request can be slow at multiple points:

```text
WebClient                  Network / Proxy             WebFlux server
   |                             |                            |
   |-- DNS resolve --------------|                            |
   |-- TCP connect --------------|--------------------------->|
   |-- TLS handshake ------------|--------------------------->|
   |-- send headers/body --------|--------------------------->| decode request
   |                             |                            | handler
   |                             |                            | Mono.delay?
   |<-- response status/headers -|----------------------------|
   |<-- response chunk 1 --------|----------------------------|
   |           [wait]            |                            |
   |<-- response chunk 2 --------|----------------------------|
   |<-- end of body -------------|----------------------------|
   |                             |                            |
```

The term "slow connection" is misleading. A server using `Mono.delay(Duration)` only simulates **a server slow to return a result**; it does not simulate slow TCP connect, TLS congestion, packet loss, or a real low-bandwidth network.

Forms to distinguish:

| Delay/fault type | Where it sits | Suitable simulation | Observable symptom |
| --- | --- | --- | --- |
| Slow/failing DNS resolve | Before TCP connection | Fake DNS/controlled resolver, proxy, or dedicated integration test | UnknownHost/resolver timeout; not HTTP 500 |
| TCP connect timeout | No connection yet | Network fault proxy, controlled firewall/blackhole | Connect timeout, no HTTP status received |
| Slow/failing TLS handshake | After TCP, before HTTP | Fake TLS endpoint, cert/ALPN mismatch, fault proxy | Handshake/SSL exception |
| Waiting for response headers | Server received request but has not sent headers | `MockResponse.setHeadersDelay` or handler returning `Mono.delay` | High time to first byte |
| Slow response body | Headers arrived, large gaps between chunks | `setBodyDelay`, `throttleBody` | Read/response timeout between chunks |
| Slow body upload | Client sends chunks slowly | `Flux.delayElements` or `Flux.interval` in request body | Server waits for request body to finish |
| Idle streaming | SSE/NDJSON with no new events | `Flux.never`, heartbeat with intervals | Idle timeout or stream stays open |
| Remote socket closes abruptly | TCP connection reset/closed | `SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY` | Premature close/I/O error, typically no 5xx status |
| Client disconnects actively | Subscriber cancels, browser closes tab | `take(n)`, `dispose`, closing client socket | `doFinally(CANCEL)` may appear upstream |

A trustworthy test must state **which layer** it is simulating; if you merely add a delay in a service and call it a "slow network," conclusions become overstated.

## 2. Three testing layers and the value of each

### 2.1. Unit tests with StepVerifier and VirtualTime

`StepVerifier` verifies Mono/Flux signals. With `withVirtualTime`, you can verify a multi-hour logical delay in a few real milliseconds.

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2))
                .thenReturn("ready"))
        .expectSubscription()
        .expectNoEvent(Duration.ofHours(1))
        .thenAwait(Duration.ofHours(1))
        .expectNext("ready")
        .verifyComplete();
```

Pros: fast, accurately checks pipelines and business timeouts. Cons: does not test TCP sockets, TLS, pooling, client disconnects, or network adapter backpressure.

### 2.2. WebTestClient bindToController / bindToApplicationContext

```java
WebTestClient client = WebTestClient
        .bindToController(new DemoController())
        .configureClient()
        .responseTimeout(Duration.ofSeconds(2))
        .build();
```

This tests WebFlux request mapping, codecs, HTTP status/headers/body **without opening a TCP server**. It is useful for validation, error handlers, and serialization, yet does not prove behavior on lost sockets or connect timeouts.

If controller dependencies need mocking, use `@WebFluxTest` with appropriate mock services; do not treat that as a full network integration test either.

### 2.3. @SpringBootTest(RANDOM_PORT) and real WebClient

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HttpIntegrationTest {
    @Autowired
    WebTestClient client;
}
```

Spring Boot starts an embedded HTTP server on a random port; `WebTestClient` can connect to the real server. `@LocalServerPort` can be paired with `WebClient` when testing subscription-level cancellation or streaming.

This tests loopback network transport on the test machine, yet **does not reproduce** WAN latency, real packet loss, NAT, or production proxies without adding network fault simulation.

### 2.4. Fake upstream server with transport control

When the WebFlux application acts as an **HTTP client** calling an external service, use `MockWebServer` (OkHttp 4.x) to simulate upstream. You can force it to:

- Wait before sending response headers.
- Wait before the response body.
- Stream the body at a throttled rate.
- Cut the socket mid-body.
- Return status 429, 503, Retry-After headers, or malformed bodies.

This tests **outbound WebClient** over real HTTP without requiring the Internet or remote dependencies. Combined with `RANDOM_PORT`, both the WebFlux server and outbound WebClient can be tested.

### 2.5. When is Toxiproxy or a network fault environment needed?

`MockWebServer` handles scripted delayed responses and disconnects well. To simulate blackholed connections, packet loss, jitter, bidirectional bandwidth limits, half-open TCP, or proxy tunnels, use a network fault proxy such as Toxiproxy/`tc netem` in a controlled test environment.

Never use an arbitrary Internet IP as an "unresponsive host" in CI: routing may differ, firewalls may fail fast, or external behavior may change. Tests need resources controlled by the test suite and finite timeouts.

## 3. Distinguishing timeouts

A request may wait for a pooled connection, a TCP connection, headers, or subsequent chunks. Each layer has its own timeout mechanism.

| Timeout | Common API | Scope | On expiration |
| --- | --- | --- | --- |
| Connection pool acquire | `ConnectionProvider.pendingAcquireTimeout` | Waiting for a channel from the pool | Acquire error; may not have opened a new TCP connection |
| TCP connect | Reactor Netty `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Establishing TCP connection | Connect exception, no HTTP response yet |
| SSL handshake | Reactor Netty `secure(spec -> ...)` | TLS negotiation | SSL/handshake exception |
| Response/read | Reactor Netty `HttpClient.responseTimeout` | Timeout on response reading per Netty semantics | Read/response timeout, possibly wrapped |
| Publisher timeout | `Mono.timeout(Duration)` or `Flux.timeout(Duration)` | Waiting for next signal in reactive pipeline | Cancels source and emits TimeoutException if no fallback |
| WebTestClient deadline | `WebTestClient.Builder.responseTimeout(Duration)` | Time test client waits for response per test API | Test fails if exchange/response waits too long |
| StepVerifier deadline | `verify(Duration)` | Real time to finish **the assertion script** | AssertionError; does not automatically produce HTTP 504 |
| Server/gateway timeout | Reverse proxy, load balancer, or application | Server/infrastructure policy | May return 504/408 or close connection; varies by layer |

Do not confuse them:

- `Mono.timeout` sets a deadline on the caller's body publisher, yet does not configure TCP connect, TLS, or pooling separately.
- `Flux.timeout(Duration)` on an ordinary stream governs **the wait until the next signal** (including the first); it is not necessarily the total stream duration.
- Reactor Netty's `HttpClient.responseTimeout` should not be called an absolute end-to-end deadline. It bounds response-read waits; a total business-layer timeout is still needed if required by the contract.
- `verify(Duration)` only protects the JUnit test. On expiration, the test throws AssertionError; it does not turn a Mono into onError(TimeoutException).
- `WebTestClient.responseTimeout` governs the test client's behavior, without altering timeouts used by production WebClient.

### 3.1. Reactor Netty client configuration example

```java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Requires importing `io.netty.channel.ChannelOption`, `reactor.netty.http.client.HttpClient`, and `org.springframework.http.client.reactive.ReactorClientHttpConnector`. This is an outbound client and does not change the embedded server receiving HTTP.

If using a custom pool, configure `maxConnections`, `pendingAcquireMaxCount`, `pendingAcquireTimeout`, and `dispose()` lifecycle; never create a new pool per request.

### 3.2. Timeouts are errors, not necessarily HTTP 504

If WebClient inside a service encounters `TimeoutException`, the service must decide error mapping: it may return 504, 503, fallback, or retry per API contract. Reactor does not automatically turn all timeouts into 504 Gateway Timeout.

Client disconnects are not server-authored 4xx/5xx responses either. A socket closed mid-body can cause the client to receive `PrematureCloseException` or `WebClientRequestException` depending on failure point and connector. Therefore transport tests should assert appropriate I/O/timeout error categories rather than forcing one stack-trace message string.

## 4. Simulating slow responses in a controller

Controller example:

```java
@RestController
class DelayController {

    @GetMapping("/delay")
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(400))
                .thenReturn("slow-ok");
    }
}
```

`Mono.delay` schedules a signal after 400 ms without blocking the event loop. `thenReturn` discards the tick value (0) and emits the string. **This is a slow application response**, not a simulation of TCP handshake or DNS.

Testing at the publisher layer:

```java
StepVerifier.withVirtualTime(
        () -> new DelayController().delayed())
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(399))
        .thenAwait(Duration.ofMillis(1))
        .expectNext("slow-ok")
        .verifyComplete();
```

Using `withVirtualTime` requires **creating the publisher inside the Supplier** so the scheduler receives virtual time. Creating Mono.delay before activating virtual time can cause real waiting or failure.

Real HTTP test:

```java
client.get().uri("/delay")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("slow-ok");
```

The HTTP test runs slowly for about 400 real ms. It tests the endpoint over HTTP without measuring WAN connection latency.

## 5. Simulating slow upstream with MockWebServer

### 5.1. Header delay: server has not returned status line/headers

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeadersDelay(700, TimeUnit.MILLISECONDS)
        .setBody("delayed"));

Mono<String> response = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build()
        .get()
        .uri("/work")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(150));
```

Because the mock server deliberately waits 700 ms before sending headers while the publisher times out after 150 ms, the caller typically receives `TimeoutException` from Reactor `timeout`. This scenario verifies publisher-layer timeout; it does not prove engine connect timeout.

### 5.2. Body delay: headers received but content arrives late

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("body-is-late")
        .setBodyDelay(500, TimeUnit.MILLISECONDS));
```

Here the server sends headers first, waits, and then sends the body. You can test Reactor Netty's response timeout or total duration with Mono.timeout. If using `retrieve().toBodilessEntity()`, the test may succeed as soon as headers arrive and **does not prove the body was read**; to verify the body, use `bodyToMono(String.class)`.

### 5.3. Chunk throttling: low bandwidth or stalling mid-body

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("abcdefgh")
        .throttleBody(1, 300, TimeUnit.MILLISECONDS));
```

Sends one byte every 300 ms. If Reactor Netty `responseTimeout` is smaller than the gap between reads, the caller may receive a read timeout. Do not conclude the whole body must finish within 300 ms: `responseTimeout` is not a total response deadline.

### 5.4. Socket closed mid-stream

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("x".repeat(8192))
        .setSocketPolicy(
                SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));
```

MockWebServer closes the connection before the body finishes. When the response carries a `Content-Length` for the full body, the client receives a truncated body and normally emits an I/O error rather than returning a successful string.

The exact error class can be `PrematureCloseException`, `WebClientRequestException`, or a Netty-wrapped exception depending on version and failure point. Tests should expect a terminal error and, if classification is needed, inspect the cause chain rather than depending on version-specific messages.

### 5.5. Socket closed right at the start

`SocketPolicy.DISCONNECT_AT_START` simulates the remote closing before handling the request. It differs from mid-body disconnect. Some HTTP clients may retry when a connection closes early if the request is safe; tests must control retry policies and enqueued response counts to avoid wrong conclusions from a single close.

Do not assume a TCP reset equals HTTP status 503. When TCP is reset, the server may not have sent any status at all.

## 6. Slow uploads and incremental request bodies

WebFlux can accept a request body publisher; clients can supply data piece by piece. With NDJSON, each object is encoded and flushed per streaming media type.

```java
record SensorLine(long seq) {}

Flux<SensorLine> slowLines =
        Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(i -> new SensorLine(i));

Mono<Long> count = webClient.post()
        .uri("/lab/upload")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(BodyInserters.fromPublisher(
                slowLines, SensorLine.class))
        .retrieve()
        .bodyToMono(Long.class);
```

The snippet above requires WebClient, MediaType, and BodyInserters imports; `webClient` is a client already pointed at a real HTTP server. The server can receive:

```java
@PostMapping(
        value = "/lab/upload",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Long> upload(@RequestBody Flux<SensorLine> lines) {
    return lines.count();
}
```

The response emits when the request publisher completes because `count()` must count all items. With three items and a 200 ms interval each, the response cannot finish instantaneously like a pre-buffered body. However, elapsed time on CI machines also depends on schedulers and network overhead, so **do not assert an exact 600 ms**.

For large uploads, bound individual item sizes and total element count/memory. If the client closes the connection mid-upload, the server may receive cancel or error; ensure temporary resources (files, streams, DB sessions) are released. To test very low upload bandwidth, use `MockWebServer`/proxy or a pace-controlled client stream rather than `Thread.sleep` inside the controller.

## 7. SSE, client disconnects, and cancellation

### 7.1. Non-terminating response stream

Example server emitting an SSE every 120 ms:

```java
@GetMapping(
        value = "/lab/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(120))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .data("tick-" + i)
                    .build())
            .doFinally(signal ->
                    System.out.println("events ended: " + signal));
}
```

`ServerSentEvent` lets clients receive multiple records on a single HTTP response. This response has no `onComplete` if upstream uses an infinite `Flux.interval`.

Client takes only two events and stops:

```java
Flux<String> firstTwo = webClient.get()
        .uri("/lab/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(new ParameterizedTypeReference<
                ServerSentEvent<String>>() {})
        .map(ServerSentEvent::data)
        .take(2);

StepVerifier.create(firstTwo)
        .expectNext("tick-0", "tick-1")
        .verifyComplete();
```

On the **client** side, `take(2)` completes after two events. Upstream, it sends `cancel` and the network adapter normally closes/cleans up the response body. The server may observe `SignalType.CANCEL` once the disconnect is detected. Never assert that the server callback always executes in the exact same millisecond as the client-side assertion.

### 7.2. Difference between active cancellation and unexpected disconnect

- `take(2)` or `dispose()`: caller actively stops consuming. This is the **deterministic** way to test Reactive Streams cancellation.
- User closes browser tab or proxy cuts socket: the system learns via transport when I/O detects the disconnect; timing varies, especially if the server has not written new data yet.
- `MockWebServer` forces socket drop: tests WebClient's ability to detect broken responses.
- `Mono.timeout`: on expiration, it cancels the upstream subscription and emits TimeoutException downstream; this still is not proof the server finished cleanup immediately.

For long-lived SSE, periodic events/heartbeats can be sent to increase the chance of detecting departed clients. Avoid overly frequent heartbeats that waste bandwidth or CPU. Clients must handle reconnection and `Last-Event-ID` if the contract requires resume; do not assume the server stores every event automatically.

### 7.3. Testing doFinally(CANCEL)

Cancellation can be tested **at the Flux layer**, isolated from socket timing:

```java
AtomicReference<SignalType> observed = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 100)
        .doFinally(observed::set);

StepVerifier.create(source, 2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();

assertEquals(SignalType.CANCEL, observed.get());
```

`StepVerifier.thenCancel()` actively cancels. `doFinally` is placed **on the source**, before the point where downstream cancels; if placed after `take(2)`, the downstream callback could see COMPLETE while upstream actually received cancel.

`doFinally` makes sense for metrics/logging or releasing **synchronous** resources managed there. If cleanup is an async publisher, use `usingWhen` or a suitable lifecycle API; do not call unmanaged `connection.close().subscribe()` and claim leaks are fixed.

## 8. Testing errors and timeouts without swallowing errors

A service can map timeouts to business errors:

```java
public Mono<String> fetchWithDeadline(WebClient webClient) {
    return webClient.get()
            .uri("/remote/data")
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(2))
            .onErrorMap(
                    TimeoutException.class,
                    ex -> new UpstreamTimeoutException(ex));
}
```

`UpstreamTimeoutException` is an application-defined business exception; this code is illustrative and needs `TimeoutException` imported. Never write `onErrorResume(e -> Mono.just("OK"))` for all errors because it can mask connection failures or return fake data as real.

For an HTTP proxy/service gateway, return 504 only when that is the right contract; `@RestControllerAdvice` or `onErrorResume` in functional endpoints can map errors to `ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)`.

```java
return webClient.get()
        .uri("/remote/data")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .map(ResponseEntity::ok)
        .onErrorResume(TimeoutException.class, ex ->
                Mono.just(ResponseEntity
                        .status(HttpStatus.GATEWAY_TIMEOUT)
                        .body("upstream timed out")));
```

This snippet specifically illustrates error mapping; ensure the return type and status/body stay consistent with the real controller. Do not map every `IOException` to 504; a connection refused or TLS handshake failure may warrant 502/503 per the API contract.

### 8.1. Retries require caution

Retrying on timeout can resend a request while the remote already finished the initial work. For read-only GETs, bounded retries with backoff are usually reasonable. For side-effecting POST/PUT, retry only if the operation is idempotent or uses a server-enforced idempotency key.

Never configure unbounded `retry()`, especially around an overly tight timeout; tests may look "fine" while production suffers a request storm.

### 8.2. Transport errors can surface at different stages

- Cannot connect: error happens before any HTTP response status.
- Headers arrive then body drops: client may see status 200 before the body publisher emits an error.
- Final chunk lost: body parser may wait for full Content-Length or receive premature-close.
- Client times out after server commits: server already executed the side effect, even though caller sees TimeoutException.

Thus tests must verify the right layer and stage. An assertion checking only HTTP status 200 does not prove the full body was read cleanly.

## 9. Runnable Java 17 + Spring Boot 3.3.5 project

The project below runs Spring WebFlux on a random port during integration tests. It contains three test groups:

1. **WebTestClient + RANDOM_PORT:** fast/slow endpoints and response status/body over real HTTP.
2. **StepVerifier:** driving virtual time, timeouts, and cancellation independently of sockets.
3. **MockWebServer + WebClient:** header delays, body throttling, and forced socket disconnects.

No Internet is required when running tests apart from Maven's initial dependency download.

### 9.1. Structure

```text
webflux-fault-simulation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── FaultSimulationApplication.java
    │   └── LabController.java
    └── test/java/demo/
        ├── WebFluxHttpIntegrationTest.java
        ├── ReactorTimingTest.java
        └── MockUpstreamFailureTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-fault-simulation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent provides dependency management for Spring WebFlux, Reactor Netty, and JUnit 5; MockWebServer is pinned to version 4.12.0 to use the `okhttp3.mockwebserver.MockResponse` API. OkHttp 5 uses a different API, so do not bump the version automatically while keeping 4.x test code.

### 9.3. FaultSimulationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FaultSimulationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FaultSimulationApplication.class, args);
    }
}
```

### 9.4. LabController.java

```java
package demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/lab")
public class LabController {

    public record SensorLine(long seq) {
    }

    @GetMapping("/fast")
    public Mono<String> fast() {
        return Mono.just("fast-ok");
    }

    // Simulates a slow handler, not a slow TCP connect.
    @GetMapping("/delayed")
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(400))
                .thenReturn("slow-ok");
    }

    // Emits no headers/body, no terminal signal.
    @GetMapping("/never")
    public Mono<String> never() {
        return Mono.never();
    }

    // Long-lived SSE; client can cancel after n events.
    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(120))
                .map(index -> ServerSentEvent.<String>builder()
                        .id(Long.toString(index))
                        .data("tick-" + index)
                        .build());
    }

    // Request body arrives incrementally as NDJSON objects.
    @PostMapping(
            value = "/upload",
            consumes = MediaType.APPLICATION_NDJSON_VALUE)
    public Mono<Long> upload(
            @RequestBody Flux<SensorLine> lines) {
        return lines.count();
    }
}
```

Both `Mono.delay` and `Flux.interval` use schedulers without blocking the Reactor Netty event loop. `never()` deliberately never completes and sends no response; in production, such an endpoint needs deadlines and cleanup mechanisms.

### 9.5. WebFluxHttpIntegrationTest.java

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxHttpIntegrationTest {

    @Autowired
    WebTestClient testClient;

    @LocalServerPort
    int port;

    private WebClient webClient() {
        return WebClient.builder()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    @Timeout(10)
    void fastEndpointReturnsImmediately() {
        testClient.get()
                .uri("/lab/fast")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("fast-ok");
    }

    @Test
    @Timeout(10)
    void delayedHandlerEventuallyReturnsHttp200() {
        testClient.get()
                .uri("/lab/delayed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("slow-ok");
    }

    @Test
    @Timeout(10)
    void publisherTimeoutCancelsNeverEndingRequest() {
        StepVerifier.create(
                webClient().get()
                        .uri("/lab/never")
                        .retrieve()
                        .bodyToMono(String.class)
                        .timeout(Duration.ofMillis(200)))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }

    @Test
    @Timeout(10)
    void clientCanStopReadingSseAfterTwoEvents() {
        Flux<String> firstTwo = webClient().get()
                .uri("/lab/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {})
                .map(ServerSentEvent::data)
                .take(2);

        StepVerifier.create(firstTwo)
                .expectNext("tick-0", "tick-1")
                .verifyComplete();
    }

    @Test
    @Timeout(10)
    void slowNdjsonUploadIsConsumedAsFlux() {
        Flux<LabController.SensorLine> lines =
                Flux.interval(Duration.ofMillis(150))
                        .take(3)
                        .map(LabController.SensorLine::new);

        StepVerifier.create(
                webClient().post()
                        .uri("/lab/upload")
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(BodyInserters.fromPublisher(
                                lines, LabController.SensorLine.class))
                        .retrieve()
                        .bodyToMono(Long.class))
                .expectNext(3L)
                .verifyComplete();
    }
}
```

Explanation:

- The first two tests use `WebTestClient` configured with the real server port, rather than calling the controller directly.
- The `/lab/never` test puts the timeout on **the client-side publisher**. It emits `TimeoutException` even though the server never returned an HTTP status; do not assert 504.
- The SSE test uses `take(2)`: the client receives two events and cancels the subscription. Do not assert the exact moment the server-side socket closes because network cancellation is observed asynchronously.
- The upload test schedules three objects 150 ms apart as NDJSON; the server uses `Flux.count()` so it replies 3 once the body stream completes.
- `@Timeout(10)` is JUnit's per-test watchdog and does not replace business timeouts or `StepVerifier.verify(Duration)`.

### 9.6. ReactorTimingTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactorTimingTest {

    private final LabController controller = new LabController();

    @Test
    void delayedMonoUsesVirtualTime() {
        StepVerifier.withVirtualTime(controller::delayed)
                .expectSubscription()
                .expectNoEvent(Duration.ofMillis(399))
                .thenAwait(Duration.ofMillis(1))
                .expectNext("slow-ok")
                .verifyComplete();
    }

    @Test
    void timeoutOperatorEmitsTimeoutException() {
        StepVerifier.withVirtualTime(
                        () -> Mono.delay(Duration.ofSeconds(10))
                                .timeout(Duration.ofSeconds(3)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void cancellationIsObservableOnUpstreamFlux() {
        AtomicReference<SignalType> signal =
                new AtomicReference<>();

        Flux<Integer> source = Flux.range(1, 100)
                .doFinally(signal::set);

        StepVerifier.create(source, 2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, signal.get());
    }
}
```

These three tests verify reactive semantics **without networking**. They do not replace the integration tests in the previous section.

### 9.7. MockUpstreamFailureTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.test.StepVerifier;

class MockUpstreamFailureTest {

    private WebClient webClient(
            MockWebServer server, Duration responseTimeout) {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(responseTimeout);

        return WebClient.builder()
                .baseUrl(server.url("/").toString())
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }

    @Test
    @Timeout(10)
    void healthyResponseIsFullyRead() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("upstream-ok"));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(2))
                            .get().uri("/health")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectNext("upstream-ok")
                    .verifyComplete();
        }
    }

    @Test
    @Timeout(10)
    void delayedHeadersTriggerPublisherTimeout() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .setHeadersDelay(700, TimeUnit.MILLISECONDS)
                    .setBody("eventually"));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(3))
                            .get().uri("/delayed-headers")
                            .retrieve()
                            .bodyToMono(String.class)
                            .timeout(Duration.ofMillis(150)))
                    .expectError(TimeoutException.class)
                    .verify(Duration.ofSeconds(4));
        }
    }

    @Test
    @Timeout(10)
    void throttledBodyTriggersResponseReadTimeout() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("abcdefgh")
                    .throttleBody(1, 300, TimeUnit.MILLISECONDS));

            StepVerifier.create(
                    webClient(server, Duration.ofMillis(120))
                            .get().uri("/throttled")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectError()
                    .verify(Duration.ofSeconds(4));
        }
    }

    @Test
    @Timeout(10)
    void disconnectMidBodyFailsBodyConsumption() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("x".repeat(8192))
                    .setSocketPolicy(
                            SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(3))
                            .get().uri("/broken-body")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectError()
                    .verify(Duration.ofSeconds(4));
        }
    }
}
```

These tests intentionally avoid forcing all transport errors into one Java exception class. For delayed headers, the timeout is emitted by `Mono.timeout`, so `TimeoutException` can be asserted directly. For read timeouts or broken sockets, exception classes vary by Netty version, so the minimal scenario checks that an **error** occurs rather than completing with a full response body.

`throttledBodyTriggersResponseReadTimeout` can be extended by inspecting the `ReadTimeoutException` cause chain if the system requires a detailed contract. Also assert the actual request received by MockWebServer using `takeRequest` when verifying paths/methods; the examples here focus on failure injection and response handling.

### 9.8. Running and expected results

In the directory containing `pom.xml`:

```bash
mvn test
```

With Java 17+, Maven, and downloaded dependencies, JUnit is expected to run **12 test cases**: 5 HTTP integration, 3 Reactor timing/cancellation, and 4 upstream fault injection. All tests should pass when the loopback/CI environment meets the time limits and socket policies work as designed.

There is no fixed stdout to copy verbatim because Boot/Netty log lines and Maven timings depend on the environment. What matters is the test count and zero failures/errors.

They can also be run individually:

```bash
mvn -Dtest=ReactorTimingTest test
mvn -Dtest=WebFluxHttpIntegrationTest test
mvn -Dtest=MockUpstreamFailureTest test
```

Run the application serving the sample endpoints:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/lab/fast
curl -i http://localhost:8080/lab/delayed
curl -N http://localhost:8080/lab/events
```

`curl -N` disables curl's output buffering so SSE events are visible as they arrive. Stop the stream with Ctrl+C. The server may observe the disconnect signal at varying times, especially while the connection is idle.

## 10. Observing cancellation and resources

### 10.1. Placing doFinally in the right spot

Pipeline example:

```java
Flux<Long> source = Flux.interval(Duration.ofMillis(100))
        .doFinally(signal -> logSignal(signal));

return source.take(2);
```

`logSignal` is an illustrative method, not part of the runnable project in section 9. Once downstream receives two items, the source typically sees `SignalType.CANCEL`, whereas the pipeline after `take(2)` completes normally. Place `doFinally` at the right position when distinguishing the two sides.

### 10.2. Do not infer rollback solely from CANCEL

If a response stream is canceled, an *active Spring-managed reactive transaction* can roll back on cancel per Spring 5.3+ policy. However, if commit already completed before the client disconnected, cancel cannot undo the commit.

With R2DBC, closing connections/rolling back must finish within the transaction manager's lifecycle. For self-managed reactive resources, use `Mono.usingWhen`/`Flux.usingWhen` for async cleanup instead of calling `close().subscribe()` inside `doFinally` and losing errors.

### 10.3. DataBuffer and memory leaks

`DataBuffer` can hold Netty pooled memory. When reading raw bytes or manually handling streaming with `DataBuffer`, every buffer must be consumed/released per contract. Low-level work may need `DataBufferUtils.release` or `DataBufferUtils.releaseConsumer`; when using standard codecs like `bodyToMono(String.class)` or `bodyToFlux(DTO.class)`, the framework typically manages release.

Never use `collectList` on infinite or unbounded streams, and never buffer large uploads/responses entirely in memory. Low-load tests may pass while production runs out of memory.

### 10.4. Connection pool after cancellation

With a pooled HTTP client, canceling a response often closes the connection or handles it based on reusability. **Do not** assume every canceled connection returns to the pool in a reusable state; for an incomplete response body, the engine may discard the channel.

Monitor active/idle/pending acquires, acquire times, and disposed connections. Testing pool exhaustion with a low maxConnections, a canceled stream, and verifying subsequent requests complete within a deadline is more valuable than only asserting a doFinally log.

## 11. Distinguishing four commonly confused timeouts

### 11.1. Connect timeout

If the destination never completes the TCP handshake, the engine can emit a connect timeout. To test accurately, use a controlled network fault (proxy/drop), not `Mono.delay` in a controller. The controller runs **after** the connection has been accepted and the HTTP request routed.

### 11.2. Response timeout

If the server is slow sending headers or between chunks, Reactor Netty's response timeout can trigger. Use MockWebServer to reproduce both scenarios separately: `setHeadersDelay` and `throttleBody`. The test must actually consume the body, not just fetch status.

### 11.3. Business timeout

`Mono.timeout(Duration)` measures from subscription to the matching signal. If the response exceeds the limit, the caller cancels upstream and emits `TimeoutException`. When combining retries/fallbacks, place operators carefully so you do not accidentally alter the deadline's scope.

Example:

```java
Mono<String> result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

When the body is aggregated into a Mono, this timeout limits the wait for a single result; for a multi-event Flux, a default timeout can reset after each item. Do not equate that with "the whole stream must finish within two seconds."

### 11.4. Test timeout

`StepVerifier.verify(Duration)`, JUnit `@Timeout`, and WebTestClient responseTimeout are test harness tools. Test limits should have headroom over valid latency to reduce flakiness, yet remain short enough to catch hangs.

For example, a unit test using virtual time does not need to wait two real seconds just to require a two-second logical delay.

## 12. Designing a test matrix for a real API

| Scenario | Setup | Expectation | Should not assert |
| --- | --- | --- | --- |
| Healthy | Mock upstream replies immediately | Right status/body | Exact elapsed milliseconds |
| Delayed headers | `setHeadersDelay` larger than client timeout | Timeout error, request does not hang | Pretending it is TCP connect timeout |
| Delayed body | Fast headers, slow body | Caller times out or completes per config | Checking only status 200 |
| Throttled chunks | `throttleBody`, large gap | Read timeout at right logic layer | One fixed exception message across versions |
| Disconnect mid-body | `DISCONNECT_DURING_RESPONSE_BODY` | Body publisher emits error | Server must return 500 after socket close |
| Server never completes | `Mono.never()` | Publisher timeout and cancel | Automatic HTTP 504 without error handler |
| SSE taking two events | Long-lived stream and `take(2)` | Two events, client complete/upstream cancel | Server doFinally runs at exact same instant as test |
| Slow upload | `Flux.interval` request body | Server consumes all items, returns count | Asserting exact absolute elapsed ms |
| Retry after timeout | Server records event then stalls connection | No duplicate side effects when idempotent | Automatic retry safe for all POSTs |
| Pool exhausted | Small pool, many open streams | Requests wait to acquire or fail with deadline | Adding threads fixes pool exhaustion |
| TLS handshake fail | Invalid cert in fake TLS endpoint | Handshake exception | Disabling certificate verification |
| DNS/connection fail | Controlled resolver/network fault | No HTTP status; transport error | Relying on an arbitrary Internet IP |

This matrix makes tests readable when a case fails: whether the failure lies in logic, HTTP protocol, transport, or test harness.

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `Mono.delay` "slow TCP" | Tests miss connect/TLS/packet loss | Clearly separate delayed handlers from network faults |
| Using only `bindToController` to test disconnects | No real socket to drop | Use RANDOM_PORT, WebClient, and MockWebServer/proxy |
| Not subscribing to `Mono`/`Flux` in tests | Request never runs | Use WebTestClient.exchange or StepVerifier.verify |
| Asserting only HTTP status | Misses truncated bodies or mid-response drops | Consume body and verify terminal signal |
| Using `verify()` on non-completing sources | CI may hang | `verify(Duration)` and cancel script |
| Using `Thread.sleep` to sync callbacks | Flaky, slow tests | StepVerifier virtual time or bounded awaits |
| Setting all timeouts equal | Unclear failure root cause | Set layered connect, response, operation, and test deadlines |
| Assuming `Flux.timeout` is total stream deadline | Multi-event streams can still run longer | Use a separate total-deadline policy if needed |
| Matching exact Netty exception message | Brittle across versions | Assert error contract / cause chain |
| Expecting browser disconnect to return 504 | Client already left; no valid response remains | Observe cancel, cleanup, and logs |
| Logging PII in wiretap | Leaks request/response data | Enable selectively and redact |
| Enabling unbounded retries | Request storms or duplicate side effects | Bound retries, backoff, idempotency |
| Wrapping `block()` in controller | Blocks event loop, triggers cascading timeouts | Compose reactive operators |
| Not releasing raw DataBuffers | Leaks pooled direct memory | Release per contract or use standard codecs |
| Holding DB transaction across infinite SSE | Exhausts DB connection pool | Short transaction for snapshot, stream outside transaction |
| Test asserting server sees CANCEL immediately | Depends on adapter/socket timing | Assert cancel logic in unit tests; use bounded await in integration |
| Testing unresponsive public IP | Routing/firewall changes | Use deterministic local fake/proxy |
| Using fixed port for all tests | Port collisions in CI | RANDOM_PORT / MockWebServer ephemeral ports |

## 14. Self-check questions

**Question 1.** Can `Mono.delay` in a controller simulate slow TCP connect?  
**Answer:** No. It simulates processing/response delay after the HTTP request has reached the handler.

**Question 2.** When should `WebTestClient.bindToController` be used?  
**Answer:** When testing routing, codecs, status, body, and validation without sockets; do not use it to prove disconnect/TLS behavior.

**Question 3.** How do you test real HTTP on a random port?  
**Answer:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` and WebTestClient/WebClient connecting to `@LocalServerPort`.

**Question 4.** How do you make upstream slow to send headers with MockWebServer?  
**Answer:** `MockResponse.setHeadersDelay(...)`. Do not confuse it with TCP connect timeout.

**Question 5.** How do you simulate a socket dropping mid-response body?  
**Answer:** `SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY` and require the client to consume the body.

**Question 6.** How does `Mono.timeout` differ from `WebTestClient.responseTimeout`?  
**Answer:** Mono.timeout belongs to the application pipeline and emits TimeoutException; WebTestClient responseTimeout is the test client's limit.

**Question 7.** When an SSE client uses `take(2)`, what happens?  
**Answer:** The client receives two items and completes downstream; upstream is canceled. The server may see cancel after transport detects the disconnect.

**Question 8.** Why avoid asserting exact elapsed=400 ms for `Mono.delay(400 ms)`?  
**Answer:** Schedulers, GC, and CI load add overhead; verify the value and use buffered timeouts or virtual time.

**Question 9.** If status 200 was received, is the body guaranteed complete?  
**Answer:** No. The socket can drop while transmitting the body; consume the body to terminal.

**Question 10.** Does a client timeout guarantee the server did not write to the database?  
**Answer:** No. Side effects can finish before the caller times out; idempotency and state checks are needed.

**Question 11.** What is `MockWebServer.throttleBody` useful for?  
**Answer:** Simulating a response body arriving slowly in chunks to test read/response timeouts.

**Question 12.** Why not use `Thread.sleep` to prove cancellation?  
**Answer:** It lacks clear synchronization guarantees and is flaky; use StepVerifier/CountDownLatch/bounded awaits at the layer under test.

## 15. Takeaways

- "Slow connection" is not one single state: distinguish DNS, TCP, TLS, header waits, slow body/streams, and slow uploads.
- **StepVerifier + virtual time** tests timing logic quickly; **WebTestClient mock** tests WebFlux HTTP abstractions; **RANDOM_PORT** and **MockWebServer** test real HTTP transport.
- `Mono.timeout` and `Flux.timeout` govern business signals; Reactor Netty `responseTimeout` governs networking; `verify(Duration)` and `WebTestClient.responseTimeout` guard tests.
- Always consume the response body to terminal if detecting mid-body disconnects matters.
- When a client cancels SSE, upstream can receive `CANCEL`; server detection and cleanup may lag due to transport.
- MockWebServer 4.x provides `setHeadersDelay`, `setBodyDelay`, `throttleBody`, and `SocketPolicy` for reproducible scenarios.
- Every fault-injection test needs an explicit deadline, zero Internet dependence, and assertions free of absolute timing assumptions.
- Timeout/disconnect does not mean business side effects rolled back; combine cancellation cleanup, idempotency, metrics, and resource management.

## 16. References

1. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind to controller/application context/server, HTTP assertions, streaming.
2. [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): RANDOM_PORT, WebTestClient, @WebFluxTest.
3. [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): response timeout, connect timeout, pooling, and lifecycle.
4. [Spring Framework – Reactive Core and Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): streaming, SSE heartbeats, DataBuffer, and codecs.
5. [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): HTTP client fluent API, outbound connectors.
6. [Project Reactor – Testing and Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, and cancellation.
7. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): delay/timeout/usingWhen.
8. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): interval/take/timeout and backpressure.
9. [OkHttp MockWebServer 4.x API](https://square.github.io/okhttp/): scripted responses, MockResponse delay/throttle, and SocketPolicy.
10. [Reactive Streams Specification](https://www.reactive-streams.org/): cancellation and Publisher/Subscriber semantics.
