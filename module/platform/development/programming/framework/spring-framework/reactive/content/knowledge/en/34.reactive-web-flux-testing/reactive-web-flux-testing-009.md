# Limits of What Mock Tests Prove About Networking and Backpressure in Spring WebFlux

## 1. Goal

A WebFlux test can pass while the application still fails when running over sockets, TLS, proxies, load balancers, or slow-reading clients. The usual cause is that the test exercises logic at one layer and then draws overly broad conclusions about the entire data path.

This lesson clarifies the exact limits of each test type, especially when proving HTTP streaming and Reactive Streams backpressure:

- WebTestClient.bindToController(...), bindToRouterFunction(...), and bindToApplicationContext(...) use mock requests/responses and open no TCP sockets.
- StepVerifier tests signals and demand at a Publisher's subscription boundary; it does not simulate kernel TCP, HTTP codecs, TLS, or proxies.
- WebTestClient.bindToServer(...) and @SpringBootTest(webEnvironment = RANDOM_PORT) send HTTP over a running server, thus testing real connectors and sockets on loopback.
- MockWebServer or WireMock lets real WebClient send HTTP over sockets to a mock server, useful for transport errors and slow responses.
- Testing through ingress, TLS termination, network impairment, and concurrent load requires an environment with matching infrastructure.

**Core point:** Reactor backpressure, demand through WebFlux publishers, connector writability, OS buffers, and HTTP/TCP flow control are related layers, yet not the same mechanism. You cannot take a `request(1)` result in a StepVerifier and conclude that the production server produces only one element over the network.

The lesson uses Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Reactor, and JUnit 5. Examples distinguish standalone code, mock-bound tests, and live-server tests.

## 2. Four layers to distinguish when discussing backpressure

### 2.1. Demand in Reactive Streams

At the Publisher/Subscriber level, downstream sends `request(n)` to signal it can accept at most n more elements. The Publisher must honor demand and emit no more than requested.

Example:

```java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
```

Here the test subscriber initially requests zero elements, then requests two and then one. Flux.range emits only per demand. This is direct verification at the in-process Publisher/Subscriber boundary.

### 2.2. Backpressure between Reactor operators

A chain such as:

```java
source
    .map(this::transform)
    .filter(this::accept)
    .publishOn(Schedulers.parallel(), 16)
    .flatMap(this::saveAsync, 4);
```

can alter how demand propagates:
- publishOn has its own queue and prefetch.
- flatMap has its own concurrency and prefetch.
- limitRate splits upstream requests into smaller chunks.
- buffer, onBackpressureBuffer, onBackpressureDrop, and onBackpressureLatest change handling when the producer outpaces the consumer.

Therefore downstream demand does not necessarily translate into identical `request(n)` calls at every upstream operator. Operators may prefetch data to sustain throughput.

### 2.3. Backpressure in WebFlux and HTTP connectors

Spring WebFlux uses non-blocking HttpHandler and Reactive Streams backpressure. WebHandler, codecs, HttpMessageWriter, DataBuffer, and server adapters cooperate to read/write content.

With Reactor Netty, server/client connectors use Netty event loops and channel writability to manage I/O. When the outbound channel cannot accept more writes, the connector can throttle requesting more data from the publisher. However, multiple buffer layers sit between the publisher and the remote subscriber.

A Flux<T> serialized into bytes:
- One Java element may produce one or more byte buffers.
- One buffer may hold part of a message or multiple messages, depending on codec/framing.
- The HTTP writer may prefetch.
- The connector may hold buffers waiting for channel writability.
- The kernel has send/receive buffers.
- A proxy or load balancer may buffer responses.
- The client connector may prefetch bytes before the decoder emits objects.

Thus there is no general rule that one downstream `request(1)` equals one server-side `request(1)` or one TCP packet.

### 2.4. Flow control in TCP and HTTP/2

TCP regulates bytes via receive windows and congestion control. HTTP/2 has per-connection and per-stream flow control, also at the byte level. Reactive Streams `request(n)` regulates element counts at the Publisher level.

The three mechanisms coordinate through the connector, yet there is no one-to-one mapping between:
- one object T;
- one DataBuffer;
- one HTTP/2 DATA frame;
- one TCP segment;
- one `request(n)` call.

When a client reads slowly, buffers and flow-control windows can absorb data for some time before pressure propagates back to the Publisher. Tests must measure the exact layer the requirement targets.

## 3. Which modes does WebTestClient offer?

WebTestClient is a test client with a fluent API similar to WebClient, adding assertions on HTTP responses. It can run WebFlux with mock requests/responses or connect to a running server.

| How client is created | Real server/socket? | Primary scope |
| --- | --- | --- |
| bindToController(...) | No | Specific controller, handler mapping, and response via mock objects |
| bindToRouterFunction(...) | No | Functional endpoints via mock request/response |
| bindToApplicationContext(...) | No | WebFlux infrastructure and Spring application context via mock objects |
| @WebFluxTest | Usually no | Controller slice test with WebTestClient |
| Default @SpringBootTest (MOCK) | No | Spring Boot context in mock web environment |
| @SpringBootTest(RANDOM_PORT) | Yes | Embedded server on a random port |
| bindToServer() | Yes | HTTP connection to a running server |

### 3.1. bindToController

```java
WebTestClient client = WebTestClient
        .bindToController(new HelloController())
        .build();

client.get()
        .uri("/hello")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("hello");
```

This builds a WebFlux handler chain for the specified controller and uses mock request/response objects. It can verify:
- Path and HTTP method mappings.
- Argument resolution and binding.
- Validation and exception handling if configured.
- Response status/headers/body.
- Codec serialization inside the mock exchange.
- Controller logic and the publisher returned by the controller.

You cannot conclude from this test that:
- TCP socket bind/listen succeeds.
- Reactor Netty or Tomcat adapters work properly.
- TLS handshake, ALPN, or certificates are valid.
- HTTP/1.1 or HTTP/2 negotiation works.
- Firewalls, DNS, proxies, or ingress forward requests.
- Kernel buffers, network backpressure, or slow-client behavior work properly.

### 3.2. bindToRouterFunction

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello"));

WebTestClient client =
        WebTestClient.bindToRouterFunction(routes).build();
```

This mode works well for functional endpoints. It verifies route predicates and handler behavior via mock exchange. It opens no sockets and tests no server connectors.

### 3.3. bindToApplicationContext

```java
WebTestClient client =
        WebTestClient.bindToApplicationContext(applicationContext)
                .build();
```

This mode uses WebFlux configuration, controller beans, and the WebHandler chain from the Spring context, yet still handles requests/responses with mock objects. It fits testing filters, exception handlers, codec configuration, and WebFlux-integrated beans.

If Spring Security is needed in a mock-bound test, configure matching security test support, such as applying `springSecurity()` when binding the context. Testing filters in a mock chain does not prove production reverse proxies or TLS.

### 3.4. @WebFluxTest

`@WebFluxTest(HelloController.class)` is a slice test focused on the WebFlux controller layer. Spring Boot auto-configures WebTestClient for this test type; typically no embedded server starts.

It is great for fast controller contract checks, yet do not use its results to claim HTTP connectors, TCP, or proxies work.

### 3.5. bindToServer

```java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

This connects to a running HTTP server. If the server is your WebFlux application, requests travel through the client connector, socket, server connector, WebFlux handler chain, and response writer.

This is a fundamentally different verification step from bindToController. Still, if the server runs on localhost, the test covers only loopback on the test machine. It does not simulate WAN, proxies, TLS termination, production DNS, or real load.

## 4. Map: what can each test prove?

| What you want to prove | Suitable test | Insufficient evidence |
| --- | --- | --- |
| Controller returns right DTO | bindToController | Direct method unit test if mapping/codec still matter |
| Functional route maps properly | bindToRouterFunction | Isolated service test |
| WebFlux filters/configuration apply | bindToApplicationContext | bindToController without full app context |
| Validation/status/JSON contract | Mock-bound WebTestClient | Socket unnecessary if goal is purely contract |
| Reactive publisher honors request(n) | StepVerifier with initialRequest | expectBodyList already aggregates body |
| Operator cancels upstream properly | StepVerifier + doOnCancel/doFinally | Asserting only HTTP 200 |
| Real server accepts HTTP and serializes response | RANDOM_PORT or bindToServer | Mock-bound WebTestClient |
| HTTP connector and loopback socket | Live-server integration test | Controller test |
| WebClient sends real requests to mock endpoint | MockWebServer/WireMock | Mock ExchangeFunction |
| Slow-reading client cancels response body | Live server + bounded body subscriber | StepVerifier on Flux without HTTP |
| Proxy/ingress timeouts and buffering | Test through actual proxy/ingress | Localhost test |
| TLS certificate/ALPN/HTTP2 | Live TLS endpoint and real client | Mock request/response |
| Bounded memory under heavy load | Load/stress test + metrics/JFR | Single isolated test |
| Production network behavior | Staging/chaos/network impairment | Loopback server |

Rule: every conclusion is only as broad as the boundary actually tested.

## 5. Testing backpressure properly at the Publisher level with StepVerifier

This is where demand can be tested most precisely because the test controls the subscriber directly.

### 5.1. Recording request(n)

```java
@Test
void publisherHonorsExplicitDemand() {
    List<Long> requests = new ArrayList<>();

    Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(requests::add);

    StepVerifier.create(source, 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

    assertEquals(List.of(2L, 1L), requests);
}
```

This test proves:
- The subscriber starts with demand 0.
- The source emits nothing until requested.
- After `request(2)`, the subscriber receives two elements.
- After `request(1)`, the subscriber receives one more element.
- Cancellation terminates the subscription.

This result does not prove the HTTP connector sends one socket message per request, because there is no HTTP connector or socket in the test.

### 5.2. limitRate shapes upstream demand

```java
@Test
void limitRateShapesUpstreamRequests() {
    List<Long> requests = new ArrayList<>();

    Flux<Integer> source = Flux.range(1, 10)
            .doOnRequest(requests::add)
            .limitRate(3);

    StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(2)
            .expectNext(3, 4)
            .thenCancel()
            .verify();

    assertFalse(requests.isEmpty());
}
```

`limitRate(3)` splits requests into smaller upstream batches according to a replenishment strategy. Do not assert one fixed request sequence solely from the `limitRate` value: high-tide/low-tide thresholds, initial demand, operator fusion, and Reactor versions can affect replenishment. When exact verification is needed, record requests against the actual version and operator chain.

### 5.3. Testing prefetch and buffering

Several operators prefetch data to improve throughput:
- `publishOn(scheduler, prefetch)`.
- `flatMap(mapper, concurrency, prefetch)`.
- `buffer(n)`.
- `onBackpressureBuffer(...)`.

When testing, know where the buffer lives and whether limits count elements or bytes. A 256-object queue does not mean a 256 MB cap if object sizes vary.

Example verifying demand is not unbounded:

```java
AtomicLong upstreamRequested = new AtomicLong();

Flux<Integer> pipeline = Flux.range(1, 1000)
        .doOnRequest(upstreamRequested::addAndGet)
        .limitRate(8);

StepVerifier.create(pipeline, 0)
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify();

assertTrue(upstreamRequested.get() > 0);
```

The assertion above only confirms demand reached upstream; it does not establish a system-wide memory bound. To prove bounded buffering, inspect prefetch/concurrency configuration and measure queues/buffers under load.

## 6. What can mock-bound WebTestClient test about streams?

Mock-bound WebTestClient remains useful when a controller returns Flux. It can check:
- The publisher is subscribed to when writing the response.
- Status and content type.
- Serialization/encoding with configured codecs.
- Ordering and content of the response body.
- Publisher errors handled per response lifecycle inside the mock exchange.
- Certain in-memory publisher cancellation behaviors.

Controller example:

```java
@RestController
class NumberController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

Mock test:

```java
@Test
void mockClientVerifiesNdjsonBody() {
    WebTestClient client =
            WebTestClient.bindToController(
                    new NumberController()).build();

    client.get()
            .uri("/numbers")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
            .expectBody()
            .json("1\n2\n3\n");
}
```

Depending on codecs and how body matchers handle NDJSON, you can use `returnResult(Integer.class)` and inspect `getResponseBody()` with StepVerifier instead of the JSON matcher. The example's goal is verifying the response contract; it is still a mock exchange.

**Do not infer:** that because the mock test received three numbers in order, production sockets will maintain the exact same pace, buffer bounds, or cancellation. Those traits require live transport tests.

## 7. Live-server tests with RANDOM_PORT

### 7.1. Why is RANDOM_PORT needed?

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` starts an embedded server on a real randomly assigned port. When using `WebTestClient.bindToServer()`, the test sends HTTP requests over a loopback socket to the server.

This test can verify:
- The embedded server actually starts and binds a port.
- HTTP request/response flow through connectors.
- Codec serialization along the real path.
- Headers, status, streaming body, and connection behavior.
- Whether client response-body cancellation is observed by the server, depending on the connector.
- Real server/client configuration in the application.

It still does not prove:
- Production proxies, gateways, or service meshes work properly.
- External DNS and production routing.
- TLS if the test uses only `http://`.
- Packet loss or WAN jitter.
- Behavior under very high connection counts.
- Memory remains bounded under all workloads.

### 7.2. Example verifying body over real HTTP

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpTest {

    @LocalServerPort
    int port;

    @Test
    void receivesHttpResponseFromRunningServer() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/numbers")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .expectBody()
                .json("1\n2\n3\n");
    }
}
```

This is an integration test over a loopback socket. Mock ServerHttpRequest/ServerHttpResponse are no longer used.

### 7.3. Testing response streams with bounded demand

When checking that the client reads a response per demand, use `returnResult` to obtain the response body Flux rather than aggregating with `expectBodyList`:

```java
FluxExchangeResult<Long> result = client.get()
        .uri("/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .exchange()
        .expectStatus().isOk()
        .returnResult(Long.class);

StepVerifier.create(result.getResponseBody(), 0)
        .thenRequest(1)
        .expectNext(0L)
        .thenCancel()
        .verify(Duration.ofSeconds(10));
```

This tests over real HTTP when the client is built via `bindToServer()`. The subscriber controls demand on the client-side response body Flux. Cancellation propagates to the client connector and can close/cancel reading the response.

**Limitation to state explicitly:** the connector may have prefetched some bytes into buffers, the server may have written data to kernel buffers, and proxies may buffer. Therefore do not assert that the server publisher emitted only one element. This test proves the consumer's ability to cancel a body stream over HTTP; to confirm the server publisher receives cancellation, instrument server-side `doFinally(CANCEL)` and await the actual signal.

## 8. Complete example: server observing cancellation from a real client

The example below runs a Spring Boot WebFlux server and a WebTestClient connected over loopback. The server emits a long stream; the client receives just one item and cancels.

### 8.1. Project structure

```text
webflux-network-test/
  settings.gradle
  build.gradle
  src/main/java/demo/network/
    NetworkTestApplication.java
    StreamProbe.java
    StreamController.java
  src/test/java/demo/network/
    MockBoundTest.java
    LiveBackpressureTest.java
```

### 8.2. Dependencies

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'webflux-network-test'
```

### 8.3. Application class

File `NetworkTestApplication.java`:

```java
package demo.network;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NetworkTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                NetworkTestApplication.class, args);
    }
}
```

### 8.4. StreamProbe

File `StreamProbe.java`:

```java
package demo.network;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;

import reactor.core.publisher.SignalType;

@Component
public class StreamProbe {

    private final AtomicLong requestCalls = new AtomicLong();

    private volatile CountDownLatch cancelled =
            new CountDownLatch(1);

    public void reset() {
        requestCalls.set(0);
        cancelled = new CountDownLatch(1);
    }

    public void onRequest(long n) {
        requestCalls.incrementAndGet();
    }

    public void onFinally(SignalType signal) {
        if (signal == SignalType.CANCEL) {
            cancelled.countDown();
        }
    }

    public long requestCalls() {
        return requestCalls.get();
    }

    public boolean awaitCancellation(
            long timeout, TimeUnit unit)
            throws InterruptedException {
        return cancelled.await(timeout, unit);
    }
}
```

This probe records:
- The server-side publisher received at least one request signal.
- The server-side publisher received cancel, if transport closed/canceled properly.

It intentionally does not sum `n` values as "number of items sent over the network." A single request can carry a large value or be adjusted by operators/writers.

### 8.5. StreamController

File `StreamController.java`:

```java
package demo.network;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {

    private final StreamProbe probe;

    public StreamController(StreamProbe probe) {
        this.probe = probe;
    }

    @GetMapping(
            value = "/finite",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Integer> finite() {
        return Flux.range(1, 3);
    }

    @GetMapping(
            value = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Long> stream() {
        return Flux.interval(Duration.ofMillis(25))
                .take(10_000)
                .doOnRequest(probe::onRequest)
                .doFinally(probe::onFinally);
    }
}
```

`Flux.interval` is bounded by `take(10_000)` so the stream can complete if a client reads everything. If the client stops reading, cancellation can travel back through the response writer and connector to the publisher.

### 8.6. MockBoundTest

File `MockBoundTest.java`:

```java
package demo.network;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class MockBoundTest {

    @Test
    void controllerWorksWithoutOpeningSocket() {
        StreamController controller =
                new StreamController(new StreamProbe());

        WebTestClient client =
                WebTestClient.bindToController(controller)
                        .build();

        client.get()
                .uri("/finite")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        org.springframework.http.MediaType.APPLICATION_JSON)
                .expectBody()
                .json("[1,2,3]");
    }
}
```

This test verifies the controller and response contract via mock request/response. It does not start an embedded server.

### 8.7. LiveBackpressureTest

File `LiveBackpressureTest.java`:

```java
package demo.network;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveBackpressureTest {

    @LocalServerPort
    int port;

    @Autowired
    StreamProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.reset();
    }

    @Test
    void clientCanReadOneItemAndCancelLiveHttpStream()
            throws InterruptedException {

        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        FluxExchangeResult<Long> result = client.get()
                .uri("/stream")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Long.class);

        StepVerifier.create(result.getResponseBody(), 0)
                .thenRequest(1)
                .expectNext(0L)
                .thenCancel()
                .verify(java.time.Duration.ofSeconds(10));

        assertTrue(probe.requestCalls() > 0);
        assertTrue(probe.awaitCancellation(
                5, TimeUnit.SECONDS),
                "Server publisher did not observe cancellation");
    }
}
```

This test checks:
1. Spring Boot starts the embedded server on a real port.
2. WebTestClient connects over HTTP loopback.
3. The response is streamed as NDJSON.
4. The client subscriber initially requests 0, then requests 1.
5. The client receives the first element and cancels the response body.
6. The server publisher observes cancellation via `doFinally(CANCEL)`.

If a specific server adapter/client connector drains the response instead of closing the connection immediately, cancellation timing may differ. When porting tests to another connector, verify the actual lifecycle. Never replace the assertion with an exact count of items emitted by the server, because connectors and kernel buffers may have absorbed extra data.

### 8.8. Running the project

If the project already has the Gradle wrapper:

```bash
./gradlew test
```

If there is no Gradle wrapper yet but Gradle is installed:

```bash
gradle test
```

The test suite serves two distinct purposes:
- MockBoundTest: verifies the controller contract without sockets.
- LiveBackpressureTest: verifies real HTTP over loopback and cancellation to the server publisher.

Do not treat these two tests as substitutes for load tests through a proxy or production-like network.

## 9. Why does request(1) not mean the server emits only one item?

When a client subscriber requests one item, the response body may already traverse these layers:

```text
Server Flux<T>
   |
   v
HttpMessageWriter / Encoder
   |
   v
DataBuffer queue
   |
   v
Server connector / Netty channel
   |
   v
Kernel TCP send buffer
   |
   v
Network / proxy / load balancer
   |
   v
Client kernel receive buffer
   |
   v
Client connector / decoder
   |
   v
Response Flux<T>
   |
   v
StepVerifier request(1)
```

Several subsequent items may already:
- Be encoded into bytes.
- Sit in the DataBuffer queue.
- Have been written into the kernel send buffer.
- Sit in a proxy buffer.
- Have been read into memory by the client connector without yet being emitted as objects.

Therefore the test can prove the consumer requested only one next object at the response Flux boundary, yet cannot conclude zero subsequent bytes or items exist in any buffer.

Nor should you require transport to produce exactly one server `request(1)` for each object the client consumes. Those are different abstraction boundaries.

## 10. Testing outbound WebClient with MockWebServer or WireMock

Another scenario is a WebFlux service calling a downstream HTTP API via WebClient. If you mock `ExchangeFunction` directly, you test how the application handles responses/errors at the WebClient abstraction layer; you do not test the real HTTP client connector.

MockWebServer or WireMock accepts requests over an HTTP socket like a normal server. The same production WebClient connector can be used to test:
- Method, path, query, headers, and request body.
- Response status/body and codec decoding.
- Server returning slow responses.
- Connections closed/reset.
- Response bodies streamed in chunks.
- Retries, timeouts, and cancellation along the HTTP client path.

Conceptual example with MockWebServer (imports/packages depend on the OkHttp version used):

```java
MockWebServer server = new MockWebServer();
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,\"name\":\"keyboard\"}"));
server.start();

WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

Mono<Product> result = client.get()
        .uri("/products/42")
        .retrieve()
        .bodyToMono(Product.class);

StepVerifier.create(result)
        .assertNext(product -> {
            assertEquals(42L, product.id());
            assertEquals("keyboard", product.name());
        })
        .verifyComplete();

RecordedRequest request = server.takeRequest();
assertEquals("GET", request.getMethod());
assertEquals("/products/42", request.getPath());

server.shutdown();
```

This is an illustrative snippet: Product, imports, and the MockWebServer dependency must be declared. In real test code use try/finally or a JUnit extension to ensure `server.shutdown()` even if assertions fail.

MockWebServer creates real network I/O between client and mock server, yet does not test DNS, the Internet, or production downstream services. It is a great tool for reproducible scenarios such as delayed responses or socket disconnects.

Do not confuse:
- MockWebServer/WireMock: fake server receiving real HTTP over a socket.
- Mock ExchangeFunction: replaces the HTTP exchange layer with no socket.
- WebTestClient.bindToController: mocks WebFlux server request/response.
- WebTestClient.bindToServer: HTTP client connecting to a running server.

## 11. Testing slow consumers properly

A slow-consumer test should have clear goals:

1. Server emits data continuously or at a controlled rate.
2. Client reads slowly or pauses demand.
3. Track the volume of data produced/encoded/buffered.
4. Observe cancellation when the client stops reading.
5. Verify memory and queues stay bounded as designed.

### 11.1. Being slow in a downstream operator is not necessarily being slow on the socket

Example:

```java
clientResponseBody
        .delayElements(Duration.ofMillis(500))
        .subscribe(this::process);
```

`delayElements` slows down downstream processing, yet may prefetch/buffer several elements. It does not guarantee the client connector immediately stops reading from the socket.

When testing, use controlled subscriber demand or `limitRate`, record request signals, and measure actual buffers. Never just insert a delay and conclude transport applied backpressure.

### 11.2. Using body Flux and StepVerifier

With `WebTestClient.bindToServer()`, `returnResult(...).getResponseBody()` lets you consume the response body as a Publisher. Starting with demand 0 and requesting elements one by one is one way to test client-side demand and cancellation.

However, do not assert that the number of elements emitted by the server equals the number of client requests. Instead check:
- Client receives the exact data requested.
- Cancellation is sent when the subscriber cancels.
- Server observes cancel if the connector/transport actually propagates it.
- Memory/queues do not grow unbounded in a dedicated load test.

### 11.3. Testing inbound request bodies

For streaming uploads, use a `Flux<DataBuffer>` request body or a large body publisher sent slowly by the client. A mock test can verify decoding/binding at the application level, yet only a live server traverses the socket receive path.

In real tests, track:
- Bytes received over time.
- Server publisher request and consume rates.
- Buffer/temporary file usage.
- Client disconnect and cancellation.
- Multipart/codec max in-memory size.

## 12. HTTP streaming does not always preserve element-by-element boundaries

When `Flux<T>` is encoded into an HTTP response:
- JSON `application/json` may be represented as a JSON array and usually requires different framing from NDJSON.
- `application/x-ndjson` emits one JSON value per line.
- `text/event-stream` uses SSE framing, event/data/id fields, and flushes per event.
- Some codecs may aggregate bodies or buffer up to a limit.
- Compression can batch bytes and alter client-observed timing.

Thus backpressure tests must use the production media type and codec. An `expectBodyList` test usually aggregates the body before asserting; it suits verifying final content but is not the best choice to prove incremental streaming or consumer cancellation.

For streaming, prefer `returnResult(T.class)` and test `getResponseBody()` as a Flux; if byte-level framing must be observed, inspect raw DataBuffers/bytes with an appropriate client connector.

## 13. TLS, HTTP/2, and proxies: things mocks cannot prove

### 13.1. TLS

Mock requests/responses have no TLS handshake. A live test using `http://127.0.0.1` also does not test:
- Certificate chains.
- Hostname verification.
- Expiry and trust stores.
- TLS protocols/ciphers.
- ALPN negotiation.
- Mutual TLS client certificates.

To prove TLS, run a real HTTPS server with test certificates and a client validating certificates properly. Never use trust-all in tests and conclude the production trust store is valid.

### 13.2. HTTP/2

Mock WebTestClient does not verify HTTP/2 frames or ALPN. Live HTTP/2 tests require server/client connectors configured for HTTP/2, TLS/ALPN, or h2c per environment, then confirming the negotiated protocol.

A 200 status does not reveal whether a request ran over HTTP/1.1 or HTTP/2. Check client protocol, server access logs, or TLS ALPN evidence.

### 13.3. Reverse proxies and load balancers

Proxies can:
- Buffer responses instead of streaming immediately.
- Enforce lower idle timeouts than the application.
- Terminate TLS and connect to backends over HTTP/1.1.
- Enforce connection/stream limits.
- Compress or re-chunk responses.
- Close connections when clients read slowly.
- Maintain connection pools and alter load distribution.

Localhost tests bypass these components. If production requests pass through Nginx, Envoy, an ingress controller, API gateway, or service mesh, run an integration test through that exact layer or an equivalent staging environment.

### 13.4. Slow networks and packet loss

Mock servers can delay responses, yet do not fully simulate packet loss, retransmissions, congestion, route changes, or NAT idle timeouts. Use network emulation/chaos tooling or a controlled staging environment to test these conditions.

## 14. What mock tests can say about cancellation

Cancellation spans multiple layers:

| Layer | Example | How to test |
| --- | --- | --- |
| Reactor subscription | Subscriber calls cancel | StepVerifier.thenCancel, doFinally(CANCEL) |
| WebFlux handler | Client body canceled in mock exchange | Instrument publisher/handler, mock-bound test |
| HTTP client connector | Body consumer cancels | Live client + returnResult body Flux |
| HTTP server connector | Channel closes, writer cancels | Live server + doFinally(CANCEL) |
| TCP socket | FIN/RST and kernel state | Socket-level test/packet capture |
| Proxy | Upstream/downstream cancellation | Test through proxy and proxy logs/metrics |

A test can prove cancellation at one layer without proving it propagates through every layer underneath. For instance, `StepVerifier.thenCancel()` proves the subscriber canceled; to claim the server received cancellation, instrument the server publisher or transport.

Never set an `AtomicBoolean cancelled` in a unit test and claim the network peer closed its socket when the test has no network at all.

## 15. Measuring backpressure and buffering in live tests

### 15.1. Measuring Publisher demand

Use `doOnRequest` at different points in the pipeline:

```java
Flux<Data> pipeline = source
        .doOnRequest(n -> metrics.sourceDemand(n))
        .publishOn(scheduler, 32)
        .doOnRequest(n -> metrics.workerDemand(n))
        .map(this::encode);
```

The two points can observe different request patterns due to operator prefetch. Measure to understand flow; do not sum those numbers into messages sent over the socket.

### 15.2. Measuring cancellation

```java
Flux<Data> stream = source
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.streamCancelled();
            }
        });
```

This is a Publisher lifecycle signal. Placed before an operator with its own subscription or retry, observed cancellation can differ across upstream/downstream segments. Choose the right instrumentation point.

### 15.3. Measuring connectors and Netty

Reactor Netty provides Micrometer integration for HTTP servers/clients. Useful metrics include:
- Active connections and total connections.
- Active HTTP/2 streams.
- Data received/sent.
- Response times and errors.
- ByteBuf allocator heap/direct memory.
- Event loop saturation and pending tasks if exposed.

Metrics alone do not prove backpressure works correctly, yet help detect growing buffers, dropping throughput, or leaked connections. Enable metrics with templated URI tags and bounded cardinality; avoid creating a time series per user ID.

### 15.4. Measuring memory and queues

If the requirement is "memory does not grow unbounded when clients are slow," you must:
- Identify every queue/buffer and its cap.
- Measure heap/direct memory under load.
- Monitor pending writes, connection pools, and event loops.
- Test multiple clients at varying read speeds.
- Verify cancellation/timeouts release buffers.
- Run stress tests long enough to observe accumulation.

A single unit test with `request(1)` cannot prove bounded memory in production.

## 16. Test matrix for a streaming endpoint

Suppose endpoint `/events` returns NDJSON. The test suite should be layered:

| Test | Setup | Assertion | Conclusion limit |
| --- | --- | --- | --- |
| Publisher contract | StepVerifier | Values, order, demand, cancel | No HTTP |
| Controller contract | bindToController | Route, status, content type, body | No sockets |
| Application filter | bindToApplicationContext | Security/filter/codec config | Mock exchange |
| Live HTTP | RANDOM_PORT | Connector, socket, HTTP body | Loopback only |
| Slow reader | Live HTTP + bounded body subscriber | Client cancels and server observes cancel | Does not prove proxy/WAN |
| Outbound client | MockWebServer | WebClient network request/response, delayed body | Simulated downstream |
| TLS | Live HTTPS | Certificate/hostname/ALPN | Tests only that cert and TLS config |
| Proxy | Staging ingress | Buffering, timeouts, routing, cancellation | Environment-dependent |
| Load | Gatling/k6/Netty load tool | Throughput, p95/p99, memory, connections | Does not replace functional assertions |
| Chaos | Network impairment | Reconnect, retry, timeout, resource cleanup | Outcome depends on fault scenario |

Not every endpoint needs the entire matrix. Choose test layers according to the risk and technical commitments of the endpoint.

## 17. Common mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| bindToController test passes so production server works | Neither embedded server nor sockets started | Add RANDOM_PORT/bindToServer |
| Assuming WebTestClient is always a live server | Can use mock requests/responses | Identify exact bind mode |
| StepVerifier request(1) proves server emits one item | No connector/kernel/proxy in test | Use live network test and avoid 1:1 claims |
| expectBodyList proves incremental streaming | Body is usually aggregated before asserting | Use returnResult and response body Flux |
| Thinking MockWebServer is a socketless mock | It accepts HTTP over a real socket | Distinguish fake server from mock ExchangeFunction |
| Mock ExchangeFunction proves TLS/sockets | It replaces the exchange layer | Use mock web server or live server |
| delayElements creates a slow network | It only slows a downstream operator | Test slow-reading clients over real transport |
| Canceling StepVerifier proves TCP FIN was sent | Proves only subscription cancel | Instrument connector/socket when needed |
| Testing localhost proves production ingress | Bypasses proxies/LBs | Test through staging ingress |
| TCP flow control equals Reactor request(n) | One regulates bytes, the other elements | Measure each layer separately |
| Treating NDJSON and JSON arrays identically | Framing/flushing/aggregation differ | Test with exact Content-Type and codecs |
| Measuring only request count to infer memory | Misses buffer/byte sizes | Track heap/direct memory/queues |
| Not testing slow clients | Buffers may accumulate or streams drop | Add slow-reader/cancel tests |
| Mock tests suffice for TLS/HTTP2 | No handshake/frame negotiation | Use live TLS/HTTP2 endpoints |
| Timeout tests ignore cancellation | Error assertions do not prove resource cleanup | Assert doOnCancel/doFinally and connection lifecycle |
| Running stress tests and skipping functional tests | Throughput does not prove contracts | Combine unit, integration, and load tests |

## 18. Test selection checklist

Before writing assertions, answer:

1. Am I testing controller logic, publisher, codecs, connectors, or networking?
2. Is WebTestClient created via bindToController, bindToApplicationContext, or bindToServer?
3. Is a server actually running in this test?
4. Does the test run through the production server adapter (Reactor Netty/Tomcat/Jetty)?
5. At which boundary is publisher demand observed?
6. Are there prefetch/buffer/flatMap concurrency operators before the measurement point?
7. Does the test body aggregate the entire response?
8. If the client cancels, does the server publisher observe `doFinally(CANCEL)`?
9. Are bytes, DataBuffers, and domain objects clearly distinguished?
10. Does the test use the production media types/codecs?
11. If calling downstream via WebClient, is the mock an ExchangeFunction or a real mock HTTP server?
12. Are TLS, HTTP/2, proxies, and ingress in the test path?
13. Is a slow client simulated at the subscriber, socket, or proxy?
14. Are memory/queues and connection lifecycles measured?
15. Are test conclusions stretched beyond the setup's scope?

## 19. Official references

- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToController, bindToRouterFunction, bindToApplicationContext, and bindToServer modes.
- [Spring Framework – WebFlux Testing](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): mock ServerHttpRequest, ServerHttpResponse, ServerWebExchange, and WebTestClient.
- [Spring Boot – Testing Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): mock web environment, @WebFluxTest, @AutoConfigureWebTestClient, and live-server tests.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HttpHandler, non-blocking I/O, Reactive Streams backpressure, adapters, and codecs.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): MockWebServer/WireMock and why to test HTTP clients with a real mock server.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, TestPublisher, and PublisherProbe.
- [Project Reactor – StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): demand, cancellation, verify, and withVirtualTime.
- [Reactor Netty – HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): server I/O, Reactive Streams backpressure, and metrics.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): client connector, network I/O, and backpressure.

## 20. Takeaways

**Mock-bound WebTestClient tests WebFlux applications via mock requests/responses; StepVerifier tests publisher demand at subscription boundaries.** These two tools excel at proving logic, mappings, codecs, and Reactive Streams rules within the scope where they actually execute.

To test HTTP connectors and sockets, use `bindToServer()` or `RANDOM_PORT`. To test outbound WebClient over real HTTP, use MockWebServer/WireMock. To prove proxies, TLS, HTTP/2, slow-client behavior, or bounded memory, use matching environments and measurements.

Specifically, `request(1)` on the client does not mean the server emits only one element: codecs, connectors, kernels, TCP/HTTP2 flow control, and proxies can buffer data. Keep Reactor demand, byte flow control, and network buffering distinct, and draw conclusions strictly within the boundary the test actually ran.
