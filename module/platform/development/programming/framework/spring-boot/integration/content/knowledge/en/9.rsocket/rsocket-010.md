# Testing interactions, disconnects, and error handling

## 1. How should RSocket integration be tested?

In a **Spring Boot Integration** system, an RSocket client may query inventory, receive continuous update streams, send transaction streams, or emit logging messages. Results connect to HTTP clients, databases, caches, and brokers like Kafka/RabbitMQ. Testing only “the request returns the expected DTO” is insufficient:

- TCP/WebSocket connections can drop while the client is receiving a stream.
- Backpressure and subscription cancellation must cross network boundaries.
- Responders can emit business errors, codec errors, or transport errors; retry behavior must differ accordingly.
- A timeout after sending a write command does not prove the server **did not execute it**.
- With **fire-and-forget**, `send()` completing is not a business processing acknowledgment.
- Retries can re-issue requests, causing duplicates in databases or downstream APIs.

This lesson builds tests from unit-level Reactor up to integration tests with a real RSocket server, then examines disconnect, recovery, and error testing. The goal is knowing **which operations completed, which failed, and which have uncertain outcomes**, rather than merely counting exceptions.

### RSocket in the Spring Boot Integration picture

~~~mermaid
flowchart LR
    A[HTTP / scheduler / broker consumer] --> B[Business Service]
    B --> C[RSocketRequester]
    C <-->|TCP or WebSocket| D[RSocket @MessageMapping]
    D --> E[(DB / cache)]
    D --> F[Partner HTTP]
    D --> G[(outbox / broker)]
    C -. metrics, trace, retry .-> H[Observability]
    D -. error/close/cancel .-> H
~~~

No automatic transaction spans RSocket, databases, and brokers. Idempotency must be verified at side-effecting write points even when using Reactive Streams.

## 2. Four interaction models and testing expectations

RSocket is a bidirectional application protocol with **Reactive Streams semantics** for streaming interactions. Choosing the right model helps write accurate tests.

| Model | Requester sends | Responder returns | Common Spring API | What to test |
| --- | --- | --- | --- | --- |
| **Request-Response** | One request | At most one response | `.retrieveMono(Result.class)` | Value/empty/error, timeout, safe retry |
| **Request-Stream** | One request | Stream of responses | `.retrieveFlux(Result.class)` | Ordering, demand, cancellation, error termination |
| **Request-Channel** | Stream of requests | Stream of responses | `.data(flux, Type.class).retrieveFlux(...)` | Bidirectional flow, backpressure, cleanup on either side closing |
| **Fire-and-Forget** | One message | No application response | `.send()` | Sends cleanly, but does not by itself prove server processed |

RSocket also supports **metadata-push** and protocol features such as keepalive, leasing, resume, and fragmentation. Do not confuse these with the four primary message interaction models.

### Connection state differs from business state

~~~text
Client       TCP/RSocket             Server               DB/HTTP downstream
  | CONNECT     |                       |                         |
  |-----------> | SETUP                 |                         |
  |             |---------------------->|                         |
  | REQUEST     |                       |                         |
  |-----------> |---------------------->| call downstream         |
  |             |                       |------------------------>|
  |             |<-- DISCONNECT ------->|       commit?           |
  | TIMEOUT     |                       |                         |
  |             |      UNKNOWN WHETHER SERVER ALREADY COMMITTED   |
~~~

A client timeout/connection error can occur before the request leaves, while the server is processing, or after the server committed yet before the response arrived. Never apply a single “always safe to retry” branch to all three.

## 3. Sample project configuration

Examples target **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. With Boot 4.x, check artifacts, packages, and APIs against the active BOM/version; do not mix APIs across major versions.

### 3.1. Dependencies

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
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
</dependencies>
~~~

`reactor-test` provides `StepVerifier` and `TestPublisher`. Spring Boot's RSocket starter provides server/client support when required dependencies are present; `spring-boot-starter-webflux` is unnecessary solely for a standalone TCP server. For RSocket-over-WebSocket embedded in a WebFlux server, configure the web server/Reactor Netty accordingly.

### 3.2. RSocket TCP server

~~~yaml
# application.yml — standalone server on TCP port 7000
spring:
  rsocket:
    server:
      port: 7000
      transport: tcp
~~~

The standalone TCP server is distinct from HTTP `server.port`. An app serving REST on 8080 and RSocket TCP on 7000 exposes **two transport endpoints** whose health/ingress/TLS policies must be reviewed separately.

When using RSocket-over-WebSocket with a WebFlux web server:

~~~yaml
# Alternative option; do not combine with the TCP config above
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

WebSocket requires a reactive server and matching deployment; test clients must use `builder.websocket(URI)` instead of `tcp(host,port)`. Never send standard HTTP JSON requests to `/rsocket` expecting RSocket replies.

## 4. Building a testable responder

Consider an inventory service supporting three interaction styles; fire-and-forget receives non-critical log events carrying unique event IDs. So the code can be placed in real Java files, each `public` record/class below belongs in a file matching its name.

~~~java
// InventoryQuery.java
public record InventoryQuery(String sku) {}

// Availability.java
public record Availability(String sku, int available) {}

// InventoryTick.java
public record InventoryTick(String sku, long sequence, int available) {}

// AuditEvent.java
public record AuditEvent(String eventId, String message) {}
~~~

### 4.1. Responder

~~~java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class InventoryRSocketController {

    private final AuditRegistry auditRegistry;

    public InventoryRSocketController(AuditRegistry auditRegistry) {
        this.auditRegistry = auditRegistry;
    }

    @MessageMapping("inventory.check")
    public Mono<Availability> check(InventoryQuery query) {
        return Mono.defer(() -> {
            validate(query);
            return Mono.just(new Availability(query.sku(), 12));
        });
    }

    @MessageMapping("inventory.watch")
    public Flux<InventoryTick> watch(InventoryQuery query) {
        return Flux.defer(() -> {
            validate(query);
            return Flux.range(1, 1_000)
                    .map(sequence ->
                            new InventoryTick(query.sku(), sequence, 12));
        });
    }

    @MessageMapping("inventory.bulk")
    public Flux<Availability> bulk(Flux<InventoryQuery> incoming) {
        return incoming.concatMap(this::check);
    }

    @MessageMapping("inventory.slow")
    public Mono<Availability> slow(InventoryQuery query) {
        return Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> new Availability(query.sku(), 12));
    }

    @MessageMapping("inventory.fail")
    public Mono<Availability> fail(InventoryQuery query) {
        return Mono.error(new IllegalStateException("Dependency unavailable"));
    }

    @MessageMapping("audit.accept")
    public Mono<Void> accept(AuditEvent event) {
        return Mono.fromRunnable(() -> auditRegistry.record(event));
    }

    private static void validate(InventoryQuery query) {
        if (query == null || query.sku() == null
                || query.sku().isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
    }
}
~~~

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class AuditRegistry {
    private final ConcurrentMap<String, AuditEvent> events =
            new ConcurrentHashMap<>();

    public void record(AuditEvent event) {
        if (event == null || event.eventId() == null
                || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        events.putIfAbsent(event.eventId(), event);
    }

    public boolean contains(String eventId) {
        return events.containsKey(eventId);
    }
}
~~~

`AuditRegistry` illustrates `eventId` deduplication in **single-process memory**, which is insufficient across multiple pods or restarts. For business-critical operations, replace it with a DB unique index/inbox or durable idempotency and proper transactions. `Flux.range` illustrates a finite stream with clear backpressure; when reading from MongoDB, Redis, or HTTP clients, those upstreams must also support cancellation and resource bounds.

### 4.2. Spring Boot-configured requester

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InventoryRSocketClient {
    private final RSocketRequester requester;

    public InventoryRSocketClient(RSocketRequester.Builder builder) {
        // Configured by Boot with codecs and connector customizers.
        // Actual connection is established when a request runs.
        this.requester = builder.tcp("inventory.example.internal", 7000);
    }

    public Mono<Availability> check(String sku) {
        return requester.route("inventory.check")
                .data(new InventoryQuery(sku))
                .retrieveMono(Availability.class);
    }

    public Flux<InventoryTick> watch(String sku) {
        return requester.route("inventory.watch")
                .data(new InventoryQuery(sku))
                .retrieveFlux(InventoryTick.class);
    }

    public Flux<Availability> bulk(Flux<InventoryQuery> queries) {
        return requester.route("inventory.bulk")
                .data(queries, InventoryQuery.class)
                .retrieveFlux(Availability.class);
    }

    public Mono<Void> sendAudit(AuditEvent event) {
        return requester.route("audit.accept")
                .data(event)
                .send();
    }
}
~~~

**API distinctions across generations:** in Spring Framework 6.x, `RSocketRequester.Builder.tcp(host, port)` returns **`RSocketRequester`** with a shared connection established lazily on request; **do not** treat it as a `Mono<RSocketRequester>` from older `connectTcp(...)` APIs. The Spring Boot-provided builder is normally prototype-scoped and stateful, so avoid reusing the same mutated builder across endpoints with differing setup metadata.

Never call `block()` inside a Netty event-loop/WebFlux handler. Integration tests use `StepVerifier` to subscribe, assert completion/errors, and enforce deadlines.

## 5. Testing pyramid for RSocket

| Layer | Subject | Tools | What it proves | What it does not prove |
| --- | --- | --- | --- | --- |
| **Reactive unit** | Mapping, validation, retry operators, cancellation | JUnit 5, `StepVerifier`, `TestPublisher`, virtual time | `Mono`/`Flux` semantics | SETUP, route metadata, wire codecs, TLS, real sockets |
| **Spring context** | `@Controller`, `@MessageMapping`, beans, codecs | `@SpringBootTest` | Bean wiring/validation/serialization inside context | Incomplete without opening a real transport |
| **RSocket integration** | Client connecting to TCP/WebSocket server | `@SpringBootTest`, random port, `RSocketRequester` | Routing, 4 interaction models, remote errors, real backpressure | Network drops, server restarts, external brokers/DBs |
| **Fault integration** | TCP cuts, latency, packet loss, restarts | Toxiproxy, container/netem, network fault tests | Timeouts, disconnects, reconnects, resource cleanup | Correct business side effects without checking DB/outbox |
| **System/contract** | RSocket + DB + HTTP + brokers | Testcontainers, mock APIs, contract fixtures | At-least-once/idempotency, replay, and duplicate handling | Production guarantees under every condition |

Never replace the whole suite with a test that only mocks `RSocketRequester`: such tests miss SETUP metadata bugs, wrong routes, and codec mismatches.

## 6. TCP integration tests on a random port

Spring Boot 3.5 provides `@LocalRSocketServerPort` in `org.springframework.boot.test.rsocket.server` to inject the OS-assigned port when `spring.rsocket.server.port=0`. Do not use `@LocalServerPort`: that annotation targets the HTTP web port and can differ from the RSocket TCP port.

### 6.1. Testing Request-Response and remote errors

~~~java
import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "spring.rsocket.server.port=0",
        "spring.rsocket.server.transport=tcp"
})
class InventoryRSocketIT {

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Autowired
    AuditRegistry auditRegistry;

    private RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = requesterBuilder.tcp("127.0.0.1", port);
    }

    @AfterEach
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsExpectedDto() {
        StepVerifier.create(requester
                .route("inventory.check")
                .data(new InventoryQuery("SKU-101"))
                .retrieveMono(Availability.class))
            .assertNext(value -> {
                assertEquals("SKU-101", value.sku());
                assertEquals(12, value.available());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void invalidBusinessInputIsNotSuccess() {
        StepVerifier.create(requester
                .route("inventory.check")
                .data(new InventoryQuery(""))
                .retrieveMono(Availability.class))
            .expectErrorMatches(error -> error != null)
            .verify(Duration.ofSeconds(5));
    }
}
~~~

`@SpringBootTest` must scan `InventoryRSocketController` and `AuditRegistry` in the sample app. If your project uses different packages, specify explicit test configuration instead of relying on uncontrolled component scanning. RSocket tests run over real sockets; avoiding fixed port 7000 prevents conflicts during parallel CI runs.

`invalidBusinessInputIsNotSuccess` only confirms the server does not return success. In real apps, define a **structured error contract** (code `INVALID_SKU`, correlation, and safe messages) and assert the appropriate payload/error type rather than coupling to raw Spring RSocket exception strings across versions.

### 6.2. Stream: testing ordering, demand, and cancellation

Add the following test to the **same class** `InventoryRSocketIT`:

~~~java
@Test
void requestStreamRespectsDownstreamDemand() {
    var updates = requester
            .route("inventory.watch")
            .data(new InventoryQuery("SKU-101"))
            .retrieveFlux(InventoryTick.class);

    StepVerifier.create(updates, 0)
            .thenRequest(2)
            .assertNext(tick -> {
                assertEquals("SKU-101", tick.sku());
                assertEquals(1L, tick.sequence());
            })
            .assertNext(tick ->
                    assertEquals(2L, tick.sequence()))
            .thenRequest(1)
            .assertNext(tick ->
                    assertEquals(3L, tick.sequence()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
}
~~~

`StepVerifier.create(flux, 0)` starts with **zero demand**, then requests exactly three items. `thenCancel()` sends cancellation from the subscriber; the responder must not retain stream-producing resources indefinitely once the client stops consuming. However, this test **does not measure exact wire `REQUEST_N` frame counts**, since frameworks/transports may prefetch or buffer. If your contract requires verifying wire `REQUEST_N`/cancellation frames, instrument the transport or use low-level RSocket protocol tests.

To ensure no excess items are produced beyond demand, use a controllable source and reasonable timing bounds rather than asserting only the first three item values. `Flux.range` emits on Reactive Streams demand, making it easy to test. When data comes from HTTP polling or a hot source that ignores backpressure, add bounded buffering/drop/fail rules per contract and run dedicated overload tests.

### 6.3. Request-Channel: many requests, many responses

Add test:

~~~java
@Test
void requestChannelReturnsResponsesInOrder() {
    var queries = reactor.core.publisher.Flux.just(
            new InventoryQuery("SKU-A"),
            new InventoryQuery("SKU-B"));

    StepVerifier.create(requester
            .route("inventory.bulk")
            .data(queries, InventoryQuery.class)
            .retrieveFlux(Availability.class))
        .assertNext(value -> assertEquals("SKU-A", value.sku()))
        .assertNext(value -> assertEquals("SKU-B", value.sku()))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

In the responder, `bulk(...)` uses `concatMap(this::check)` to keep ordering simple in the example. If replaced with concurrent `flatMap`, responses can reorder by completion time; tests then need correlation IDs rather than assuming the Nth reply matches the Nth request. For real request-channels, also test **mid-stream input `Flux` errors/cancellations** and **server stopping responses** when downstream cancellation propagates.

### 6.4. Fire-and-Forget: test side effects separately, never mistake for ACK

~~~java
@Test
void fireAndForgetMustCheckServerSideEffectSeparately() {
    String eventId = "audit-" + java.util.UUID.randomUUID();

    StepVerifier.create(requester
            .route("audit.accept")
            .data(new AuditEvent(eventId, "stock checked"))
            .send())
        .expectComplete()
        .verify(Duration.ofSeconds(5));

    // Separate assertion on server state; do not infer from send().
    org.awaitility.Awaitility.await()
            .atMost(Duration.ofSeconds(3))
            .until(() -> auditRegistry.contains(eventId));
}
~~~

`.send()` issues **fire-and-forget**, and `Mono<Void>` completion only reflects protocol-level sending; it **does not guarantee the handler committed DB or finished work**. Within the same test app, checking `AuditRegistry` observes handler execution; across services, inspect persisted storage or explicit business acknowledgments.

When you need confirmation of “durably saved” before replying to a caller, **do not use fire-and-forget**—use request-response with an explicit `ACCEPTED`/`COMMITTED` response, or an outbox for durable, retryable broker publishing.

### 6.5. Client timeout when the responder is slow

~~~java
@Test
void requestResponseTimesOutWhenServerIsTooSlow() {
    StepVerifier.create(requester
            .route("inventory.slow")
            .data(new InventoryQuery("SKU-101"))
            .retrieveMono(Availability.class)
            .timeout(Duration.ofMillis(300)))
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify(Duration.ofSeconds(5));
}
~~~

Here the server intentionally delays about **two seconds**, while the client enforces **300 ms**. `timeout` is a client-side Reactor operator and does not prove the server halted all side effects; it may cancel the reactive subscription, yet cannot roll back an already-dispatched transaction or HTTP call. If slow CI makes initial handshakes jittery, warm up the connection with `inventory.check` beforehand and leave enough margin below the server's 2-second delay.

### 6.6. Route, MIME type, and serialization errors

Alongside valid DTOs, verify:

| Input / setup | Expected outcome |
| --- | --- |
| Route `inventory.check` with valid request | Single `Availability` |
| Non-existent route | No success response; error may be encoded by the RSocket framework as an application error |
| Content type matching no registered codecs | Classified decode/encode failure, never turned into an empty result |
| Wrong payload types / missing fields | Contract error or business rejection per policy |
| Oversized response exceeding frame/reassembly limits | Bounded and alerted/metered; no unbounded memory allocation |
| Invalid setup metadata/authentication | Connection or request rejected per security contract |
| Server returns `Mono.empty()` on request-response route | Client observes empty completion, distinct from both values and errors |

For paths subject to schema evolution, test both version N and N+1 DTOs: new clients read old payloads, and old clients safely handle new fields/enums. RSocket route metadata is part of the contract; renaming routes or encodings breaks compatibility just like changing HTTP endpoints without backward support.

## 7. Disconnects: failure modes that must be simulated

RSocket multiplexes many requests over one long-lived transport connection. A single socket failure can therefore impact **many in-flight requests**, unlike an isolated HTTP request.

| Failure mode | Where it happens | What client may observe | What to verify |
| --- | --- | --- | --- |
| Unreachable host/port | Before TCP connect | Connect refused/timeout | Does not hang forever; bounded retries |
| `SETUP` failure (codec, auth, metadata) | At session start | Setup rejected/application error | Never blindly retry misconfigurations or bad credentials |
| Network reset mid Request-Response | After sending request | Connection error / cancel / timeout | Server execution state may be unknown |
| Network drop mid Request-Stream | After several items | Flux errors/cancels, or times out | How many items arrived; cursor resume/replay support |
| Network drop mid Request-Channel | Bidirectional data flowing | Partial loss in either direction | Correlation, app acks, offsets/cursors, duplicates |
| Client cancels stream | After receiving enough items | `CANCEL` signal and subscription cleanup | DB cursors/HTTP streams are not held open unnecessarily |
| Server restart/rolling update | Old connection closed | Multiple requests fail simultaneously | Client re-establishes connection and reconciles in-flight work |
| Half-open/blackhole network | TCP appears open but zero frames pass | Hangs indefinitely without timeouts/keepalive | Deadlines, heartbeats, dead-peer detection |
| Invalid/expired TLS certificate | Handshake | SSL error before application handlers | Never disable TLS validation to “make tests pass” |
| Rate/concurrency limit | Server/lease/rejection | Rejected request or timeout | Concurrency reduction, backoff, and load shedding |

**Never equate socket state with business state.** When a response is lost, the server may still have written an order, sent an email, or published a Kafka event. Always support looking up outcomes by business key before re-executing side-effecting operations.

### 7.1. Testing with client `dispose()`

`RSocketRequester` implements `Disposable`, exposing `dispose()` and `isDisposed()`. In tests, calling `dispose()` closes the client side so you can verify active subscriptions terminate per policy and resources are released.

~~~java
// Outline for testing intentional client disposal:
RSocketRequester requester = builder.tcp("127.0.0.1", port);

// Execute at least one request so the lazy connection establishes.
StepVerifier.create(requester.route("inventory.check")
        .data(new InventoryQuery("SKU-101"))
        .retrieveMono(Availability.class))
    .expectNextCount(1)
    .expectComplete()
    .verify(Duration.ofSeconds(5));

requester.dispose();
org.junit.jupiter.api.Assertions.assertTrue(requester.isDisposed());
~~~

This is a **local lifecycle test**: it confirms the application closed its requester, **not equivalent** to a remote network cut or server kill. Terminal signals of an active `Flux` during disposal depend on transport/timing; tests should assert the errors, completions, or cancellations expected by the application's mapping rather than hardcoding one universal exception across all cases.

### 7.2. Fault injection with Toxiproxy or a network proxy

To reproduce network faults deterministically, place a proxy between client and server in the test environment:

~~~text
RSocketRequester:127.0.0.1:8666
          |
       [Proxy]
       | latency / timeout / reset / cut connection
          |
Inventory RSocket server:127.0.0.1:<test-port>
~~~

Testing workflow:

1. Start the RSocket server on a random port and point the proxy at that port.
2. Connect a requester through the proxy and verify a healthy request/stream succeeds.
3. Start a long request-stream or a request-response with noticeable processing time.
4. Cut the connection or inject a blackhole after observing partial data.
5. Verify subscribers **do not wait forever**: timeouts and disconnect detection fire as designed.
6. Re-enable the proxy/server. Following the app's recovery policy, open a new connection or configured session resume, and retry operations using the same business key.
7. Inspect DB, HTTP side effects, and broker outputs to catch duplicates or dropped data.

Depending on Toxiproxy/netem, disabling a proxy may close sockets immediately, whereas timeout toxics make sockets go silent. Both produce distinct failure paths and should be tested. Never inject network faults on production clusters just to verify this lesson.

### 7.3. Testing restarts/rolling updates

Simulate the server dying mid-call and a new instance starting:

~~~text
T0  client creates requester, sends eventId=E100
T1  server begins updating DB
T2  server process killed, connection drops
T3  client sees error or timeout
T4  new server receives the same eventId=E100
T5  inspect DB/outbox: logical side effect occurred only once
~~~

If DB committed before T2, the retry hits an existing record; that is normal **at-least-once delivery**. Idempotency logic must detect the repeated `eventId`/request ID and return an appropriate result without creating a second order. If DB had not committed, atomic retry executes safely.

Tests should distinguish **controlled rolling stops** (graceful shutdown/drain) from **abrupt kills**. Graceful shutdown reduces interrupted requests but does not replace recovery strategies for crashes or network partitions.

### 7.4. Keepalive and resume do not solve everything

RSocket supports keepalive frames to detect unresponsive peers. Some transports/libraries support **session resumption** if both sides configure it completely and retain session state. Keep in mind:

- Keepalive detects unresponsive peers; it **does not** confirm business completion.
- Resume is a protocol mechanism bounded by time/state/buffers; it cannot recover across a pod replacement that lost session state.
- Resumption is not a DB transaction or HTTP/Kafka exactly-once guarantee. After connectivity returns, still check event IDs/cursors and business side effects.
- If a connector auto-reconnects, know when it starts a new session vs. resumes, and the status of previously failed requests.
- An intentionally disposed requester should not be used as if its connection stayed alive; manage factory and connection lifecycles cleanly.

Using `resume()`/keepalive must follow your active RSocket Java version's APIs and support across server, client, and ingress/proxies; never ship speculative resume settings to production.

## 8. Classifying errors at the RSocket boundary

RSocket uses protocol frames and error codes rather than HTTP `404/409/503` statuses over TCP. Spring handlers emit errors via `ERROR` frames; Java clients receive RSocket exceptions or exceptions wrapped by Reactor/transports.

| Error group | Examples | Retry? | Action |
| --- | --- | --- | --- |
| **Data/contract** | Invalid SKU, bad type/codec, unknown route | Usually no | Return business validation error or quarantine; fix schema/route |
| **RSocket SETUP/security** | Bad auth metadata, MIME mismatch, `SETUP` rejected | Never retry with identical config | Fix credentials, trust, codecs, and setup metadata |
| **Remote application error** | Responder throws while accessing DB/HTTP | Cause-dependent, not by default | Separate business rejection from transient dependency failure |
| **Transport unavailable** | Connection refused/reset, peer restart | Bounded for safe operations | Backoff, reconnect/new requester, circuit breaker |
| **Timeout/unknown outcome** | Response missing after sending command | Idempotency-dependent | Lookup by business key, safe retry, or reconcile |
| **Overload/backpressure** | Fast producer, full queues/pools | Shed/reduce load first | Bound concurrency, flow control, explicit buffer policies |
| **Cancellation** | Subscriber cancels deliberately | Not a server error by default | Clean up upstream resources; do not auto-retry canceled streams |
| **Serialization failure** | Decoder cannot parse payload | Never blindly retry | Schema versioning, codec config, DLQ if from broker |

For instance, `io.rsocket.exceptions.ApplicationErrorException` may appear when a responder emits an application error. However, **never hard-couple to one exception class** to parse business error codes, as exceptions may be wrapped or details may vary across versions. For critical operations, define a **structured error contract** in published payloads/metadata or a unified error-mapping rule.

### 8.1. Never treat remote errors as `Mono.empty()`

The following is **wrong** for order reservations:

~~~java
return requester.route("orders.reserve")
        .data(command)
        .retrieveMono(ReservationResult.class)
        .onErrorResume(error -> Mono.empty());
~~~

It turns a connection/DB outage into “no result”; callers may proceed unaware whether the reservation succeeded. Safer is mapping transport failures to a domain error representing an **uncertain** state so orchestration decides retry/reconciliation:

~~~java
public class RemoteInventoryUnavailable extends RuntimeException {
    public RemoteInventoryUnavailable(Throwable cause) {
        super("Inventory RSocket is temporarily unavailable", cause);
    }
}
~~~

The calling layer can return HTTP `503` or defer the broker message (per retry/dead-letter policy) without falsely assuming “the order was never processed.”

### 8.2. Error contracts in request-response

One way to avoid parsing `ApplicationErrorException` strings is returning a data envelope for **predictable business outcomes**:

~~~java
public record StockCheckResult(
        boolean accepted,
        String code,
        String sku,
        Integer available) {
}
~~~

For example, `code=OUT_OF_STOCK` is a controlled business rejection needing no transport exception. Conversely, when the database disconnects or RSocket drops, still emit a proper **error signal** so callers classify it as dependency unavailability rather than fabricating `accepted=false` as a valid business outcome.

For N/N+1 compatibility across deployments, keep `code` catalogs stable with unknown-value handling. Schema upgrades may add optional/defaulted fields, but must never change the semantics of `accepted`/`available` without a contract migration.

## 9. Retries, reconnects, and idempotency

Some RSocket libraries manage connections, yet you must never infer “RSocket reconnects and replays every request safely automatically.” Make explicit decisions across **three layers**:

1. **Transport reconnect:** re-establishing connectivity when the server returns, distinct from resuming an old session.
2. **Application retry:** re-running an operation when the failure is recoverable and retry budget remains.
3. **Business deduplication:** ensuring replays never duplicate side effects when prior outcomes are uncertain.

### 9.1. Policy by interaction type

| Operation | Safe to retry on disconnect? | Mandatory conditions |
| --- | --- | --- |
| Read-only `inventory.check` | Usually yes | Bounded retries, timeouts, circuit breakers; no side effects |
| Streaming `inventory.watch` | Can re-subscribe | Sequence/cursor or tolerated loss/duplicates; never resume blindly from break |
| Request-channel `inventory.bulk` | Harder | Per-item correlation, app acks, per-item checkpoints/idempotency |
| Fire-and-forget `audit.accept` | Cannot know from `send()` | If important, needs durable `eventId`/inbox or switching to request-response |
| State-mutating `orders.reserve` | Only if idempotent | Stable `requestId`, unique constraints, status check after timeout |
| Payment/shipping operations | Needs explicit contract | Downstream idempotency, outbox/inbox, and reconciliation |

**Principle:** a retry only **re-subscribes to a Publisher**, and never undoes side effects. For a cold read source, it typically re-issues the request; for a hot stream, it may behave differently. With an `RSocketRequester` tied to a broken connection, adding `retryWhen(...)` alone may not establish a fresh session as hoped. Test connection lifecycles and reconnect behavior in your actual client version.

### 9.2. Retry example for idempotent reads

Separating retry policy from transport simplifies unit testing. `Supplier<Mono<Availability>>` runs on each attempt, letting callers supply a fresh request or a new requester after disconnects.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;
import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class InventoryReadRetryPolicy {

    public Mono<Availability> run(
            Supplier<Mono<Availability>> requestFactory) {

        return Mono.defer(requestFactory)
                .timeout(Duration.ofSeconds(2))
                .retryWhen(Retry.backoff(
                        2, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.3)
                        .filter(InventoryReadRetryPolicy::isTransient)
                        .onRetryExhaustedThrow(
                                (config, signal) -> signal.failure()));
    }

    private static boolean isTransient(Throwable error) {
        for (Throwable current = error;
                current != null; current = current.getCause()) {

            if (current instanceof TimeoutException
                    || current instanceof ConnectionErrorException
                    || current instanceof java.io.IOException) {
                return true;
            }
        }
        return false;
    }
}
~~~

`Retry.backoff(2, ...)` allows **up to 2 retries after the initial attempt**, not 2 total executions. The classifier above is just a starting example; network errors can have other subtypes or be wrapped by frameworks. Tailor classifiers to observed exceptions rather than retrying all `RuntimeException`s. Specifically, never repeatedly retry `RejectedSetupException`, authentication errors, bad routes, or malformed payloads with unchanged inputs.

Client usage:

~~~java
// Inside a service using RestClient/RSocketRequester at the integration boundary:
InventoryReadRetryPolicy policy = new InventoryReadRetryPolicy();
Mono<Availability> result = policy.run(
        () -> requester.route("inventory.check")
                .data(new InventoryQuery("SKU-101"))
                .retrieveMono(Availability.class));
~~~

This illustrates application-layer retries using an existing requester. If that requester has been disposed or lacks reconnect support, callers need a **requester factory/reconnect strategy** rather than retrying against a dead connection. In production, avoid opening a new TCP connection for **every** healthy request; manage reuse and controlled reconnection, disposing unused requesters.

### 9.3. Testing retries with virtual time, without real sockets

Testing the Reactor pipeline directly measures attempt counts and backoffs without waiting real seconds:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryPolicyTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                    int n = attempts.incrementAndGet();
                    if (n < 3) {
                        return Mono.<String>error(
                                new TimeoutException("transient"));
                    }
                    return Mono.just("ok");
                }).retryWhen(Retry.backoff(
                        2, Duration.ofSeconds(1)).jitter(0)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(4))
            .expectNext("ok")
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals(3, attempts.get());
    }
}
~~~

`StepVerifier.withVirtualTime` controls only **Reactor schedulers** inside the pipeline (such as `delay`, `timeout`, `Retry.backoff`). It **does not fast-forward real TCP, TLS, OS, or broker clocks**. Separate integration/fault tests remain necessary for network disconnects.

### 9.4. From retries to duplicate suppression

Example `ReserveInventory` command:

~~~json
{
  "requestId": "checkout:req-0031",
  "orderId": "ord-901",
  "sku": "SKU-101",
  "quantity": 2
}
~~~

Server boundary:

~~~text
requestId == idempotency key of one logical command
  |
  +-- INSERT inbox/processed_requests (UNIQUE requestId) in transaction
  |     if already present, look up prior outcome
  |
  +-- Check available stock, conditional update
  |
  +-- Write status and outbox in same transaction
  |
  +-- Commit -> return response per contract
~~~

If the socket drops after commit, the client retries using the **same `requestId`**; the server recognizes it and returns the prior result or `PROCESSING/COMPLETED` status per contract without decrementing stock twice. If emitting a Kafka event after DB commit, use an outbox or recoverable publisher; never claim DB transactions span RSocket and Kafka.

**Fire-and-forget is unsuitable for confirming critical transactions** without an alternative business acknowledgment channel. Client-side `Mono<Void>.then()` does not prove the remote inbox/DB committed.

## 10. Testing stream cancellation and excessive backpressure

### 10.1. Cancellation must clean up upstream resources

In unit tests, `TestPublisher` can verify how pipelines handle errors and cancellation:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class StreamLifecycleTest {

    @Test
    void propagatesErrorFromUpstream() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().map(String::toUpperCase))
                .then(() -> source.next("one"))
                .expectNext("ONE")
                .then(() -> source.error(
                        new IllegalStateException("upstream closed")))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void cancelStopsSubscription() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
                .thenRequest(1)
                .then(() -> source.next("one"))
                .expectNext("one")
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
~~~

These are unit tests of a **Reactor Publisher**, not proof that RSocket transport sent a `CANCEL` frame. Integration tests should attach a `doFinally(signal -> ...)` handler and verify the server receives cancellation when the client closes its subscription or requester. Use Awaitility to wait for counters/metrics to update, avoiding flaky immediate assertions over the network.

When upstream is a DB cursor, Kafka consumer, or HTTP stream, releasing the subscription must close/cancel resources per driver version. Check connection, thread, socket, and buffer counts across repeated subscribe/cancel cycles to catch leaks.

### 10.2. Backpressure over the network does not prevent all OOMs

RSocket uses Reactive Streams `REQUEST_N` to represent demand on Request-Stream/Channel; yet an application can still overload when:

- Data arrives from a hot publisher lacking backpressure support.
- Code uses unbounded `buffer()` or `onBackpressureBuffer()` without a capacity cap.
- Producers load huge datasets into memory before wrapping them as a `Flux`.
- Codecs/fragmentation and network buffers exceed monitored thresholds.
- Handlers run blocking code on the Netty event loop, stalling other streams.

Pick an explicit policy: **bounded buffers**, metered drops, fail-fast with `OVERLOADED`, or staging into a durable queue for later processing. For financial/transactional events, never silently drop items just to keep latency low.

Example bounding items before processing:

~~~java
Flux<InventoryQuery> incoming = Flux.just(
        new InventoryQuery("A"),
        new InventoryQuery("B"));

Flux<Availability> bounded = incoming
        .limitRate(16)
        .concatMap(query -> Mono.just(
                new Availability(query.sku(), 12)));
~~~

`limitRate(16)` shapes how Reactor requests upstream items—it does not mean “cap concurrent HTTP calls at 16” or “buffer at most 16 items”; bound concurrency using `flatMap(mapper, concurrency)`, semaphores/bulkheads, or appropriate adapters. With `flatMap`, replies can arrive out of order; rely on correlation keys rather than assuming output order matches input order.

## 11. Security, TLS, and metadata contracts must also be tested

RSocket runs directly over TCP or via WebSocket; **plain `builder.tcp(...)` does not enable TLS automatically**, nor does web server HTTPS automatically protect standalone RSocket TCP. For RSocket-over-WebSocket, use `wss://` with TLS. For TCP/TLS, configure Reactor Netty/client transports and matching trust/key material on both server and client.

### 11.1. Security cases to verify

| Case | Expectation |
| --- | --- |
| Client has valid CA | TLS handshake succeeds and hostname verifies |
| Expired server cert or hostname mismatch | Connection rejected; never enable trust-all to bypass errors |
| mTLS client missing cert/key | Handshake fails per policy |
| Invalid/expired RSocket setup token | `SETUP` or request rejected per authentication policy |
| Request lacks route permissions | Rejected cleanly without leaking sensitive data |
| Metadata wrong MIME/codec | Setup/codec error classified, not mislabeled as generic server outage |
| Payloads containing PII | Bodies and token-bearing metadata excluded from frame debug logs |
| Client rotates certificates | Refresh/reconnect/rolling update mechanism works smoothly |

For RSocket authentication and authorization, use Spring Security RSocket or configured/tested metadata authentication interceptors; never stuff tokens into business payloads and check them in only one handler. Long-lived RSocket connections can retain authentication context from `SETUP`, so evaluate token expiration/rotation and per-request authorization policies as needed.

### 11.2. When WebSocket and gateways are enabled

RSocket-over-WebSocket behind an HTTP reverse proxy requires **Upgrade** support, idle timeouts suited to long-lived streams, frame/request size settings, and TLS forwarding. A gateway tested only with REST `200 OK` may block WebSocket handshakes or reap idle connections after one minute. Testing `wss://` through real ingress differs completely from testing TCP loopback.

Never treat HTTP `101 Switching Protocols` as an acknowledgment of an RSocket request. It confirms only the WebSocket upgrade; `SETUP`, route metadata, payload codecs, keepalives, and flow control follow afterward.

## 12. Observability: visibility into connections, requests, and business effects

RSocket does not follow a 1:1 HTTP request/response model. One TCP connection can hold many bidirectional streams, so TCP connection counts alone explain very little. Attach **business correlation IDs**, routes, and processing outcomes at the application layer.

### 12.1. Recommended metric groups

| Application metric | Meaning | What to alert on |
| --- | --- | --- |
| `rsocket_connections_active` | Active connections per endpoint | Unusual spikes/drops, connection leaks |
| `rsocket_connect_failures_total{reason}` | Transport/`SETUP` establishment errors | DNS/TLS/auth issues or unavailable backends |
| `rsocket_requests_total{route,result}` | Request count by route and outcome | Route error rates, remote application errors |
| `rsocket_request_duration_seconds{route,result}` | Request-response and deadlined operation latency | p95/p99 exceeding SLO |
| `rsocket_streams_active{route}` | Active stream/channel subscriptions | Stream leaks or sudden mass drops |
| `rsocket_cancellations_total{route}` | Subscriber-initiated cancellations | High cancel rates from client timeouts or page navigation |
| `rsocket_retry_attempts_total{reason}` | Retry count by cause category | Retry storms, persistent infrastructure errors |
| `rsocket_timeouts_total{route}` | Application timeouts | Timeouts breaching budget or slow partners |
| `rsocket_decode_failures_total{schema}` | Codec/contract failures | Incompatible producer/consumer versions |
| `business_duplicates_suppressed_total` | Idempotency preventing duplicate writes | Retries/disconnects generating duplicates |
| `outbox_oldest_unpublished_seconds` | Unpublished business events | Detects integration backlogs after connection drops |

These are **illustrative metric names to implement with Micrometer** or your chosen instrumentation—not all appear automatically merely from adding `spring-boot-starter-actuator`. Avoid putting `sku`, `eventId`, user IDs, raw route parameters, tokens, or exception messages into low-cardinality labels. Use route templates, bounded error codes, and service/instance versions.

### 12.2. Tracing across RSocket, HTTP, and brokers

Desired trace:

~~~text
HTTP POST /inventory/reserve (trace T, business requestId R)
  |
  +-- OrderService
        |
        +-- RSocket request inventory.reserve (route, correlation R)
              |
              +-- InventoryService DB transaction
              +-- Write outbox eventId E
                    |
                    +-- Kafka publisher / downstream consumer
~~~

RSocket routes/metadata are not HTTP headers; **do not assume `traceparent` automatically crosses every RSocket client, broker adapter, and custom scheduler**. Verify Micrometer Tracing/Observation, metadata propagation, Reactor Context, and transport/framework instrumentation for your exact version. In tests, verify parent–child span relationships and shared business `requestId` rather than inferring from logs on the same thread.

Never use `traceId` as an idempotency key: across retries or replays, one business operation can span multiple traces/spans while `requestId` must remain constant. Never put bearer tokens, credentials, or PII into debug metadata or trace attributes.

### 12.3. Structured logging at the right layer

On errors, log at minimum:

~~~json
{
  "component": "inventory-rsocket-client",
  "route": "inventory.check",
  "result": "CONNECTION_LOST",
  "retryAttempt": 2,
  "elapsedMs": 1840,
  "correlationId": "corr-58b",
  "requestId": "checkout:req-0031"
}
~~~

Log `requestId` only if data policies allow, and never use it as a metric label. Logs must distinguish **subscriber error signals**, reconnect counts, and DB/outbox business outcomes. Identical exception stack traces for every message are insufficient to decide safe replay.

## 13. Mandatory pre-release test matrix

| Test case | Layer | Test action | Pass criteria |
| --- | --- | --- | --- |
| Request-response succeeds | RSocket integration | Call `inventory.check` | Correct DTO and completion |
| Validation error | RSocket integration | Blank SKU | Contract error emitted; no success data returned |
| Non-existent route | Integration | Call unknown route | Controlled error received |
| Request-stream | Integration | Request 3 items then cancel | Ordered items; no further items sent after cancel |
| Request-channel | Integration | Send 2 SKUs, read 2 responses | Accurate mapping per correlation/order contract |
| Fire-and-forget | Integration | `send()` then inspect storage | Does not infer business success from send completion |
| Slow responder | Integration | Server delays 2 s, short client timeout | Bounded timeout and explicit error type |
| Remote application error | Integration | Handler emits `Mono.error` | Never disguised as `Mono.empty()`/not-found |
| Codec mismatch | Integration | Wrong setup/payload format | Decode failure; no infinite retry |
| Connection refused | Fault integration | Server down or wrong port | Errors within deadline; finite retry budget |
| Cut in-flight request | Fault integration | Reset socket after sending request | Business outcome reconciled; zero double effects |
| TCP half-open | Fault integration | Proxy blackhole | Timeout/keepalive detects within budget |
| Disconnect stream | Fault integration | Cut after 5 items | Receives error/termination; cursor saved or loss reported |
| Recovery/reconnect | Fault integration | Restore server after restart | Client establishes new session per policy |
| Unsupported resume | Fault integration | Resume state lost/expired | Explicit fallback; no silently skipped items |
| Backpressure overload | Load/integration | Slow subscriber, fast producer | Bounded buffers; no OOM or blocked event loop |
| Subscriber cancellation | Unit + integration | Cancel active stream | Upstream frees resources; active stream count drops |
| TLS handshake failure | Security integration | Wrong CA/hostname/mTLS | Connection rejected; verification never disabled |
| Auth setup rejected | Security integration | Bad token | No infinite loops; no payload/secret leaks |
| Read-only retry | Virtual-time unit | Fail twice then succeed | Total 3 attempts with proper backoff |
| Side-effect retry | System test | DB commits then response drops | Same `requestId`; single logical side effect |
| Rolling deployment | System test | Stop one pod with active streams | Clean client recovery and cancellation/cleanup |
| Historical event replay | Contract/system test | N-1 payload, older schema | Compatible decoder and business logic |

### 13.1. Do not test connections with a single assertion

To prove safe failover for `ReserveInventory`, collect evidence that:

1. The client sees the error/timeout at the fault window.
2. Server/DB state shows whether it committed.
3. The retry reuses the same business `requestId`.
4. Inbox/unique constraints prevent double reservation.
5. Outbox/downstream brokers have zero duplicate logical effects.
6. Incidents/metrics record both the failure and recovery state.

Asserting only `StepVerifier.expectError()` tells you the client saw an error, **without testing correctness of the full integration flow**.

### 13.2. Reducing flaky tests

- Use random ports; connect only after the application context/RSocket server is ready.
- Set deadlines on every `StepVerifier.verify(Duration)`, Awaitility call, and fault test; never wait indefinitely.
- In timeout tests, leave enough gap between server delay and client timeout to tolerate CI jitter.
- Separate unit virtual time from real network time; never mix virtual clocks with real sockets.
- Never rely on `Thread.sleep(...)` to observe cancellation; await signals/counters with bounded timeouts.
- Assign unique request/event IDs per test and clean up DB/topics/queues and requesters/connections afterward.
- Assert attempt counts via counters and business outcomes rather than stack-trace line counts.
- Run network-disrupting fault tests inside isolated containers or test processes; never interfere with shared service ports.

## 14. Operational troubleshooting runbook

### Symptoms and triage direction

| Symptom | First question | Action |
| --- | --- | --- |
| Fails to connect initially | DNS/port/transport, TCP vs. WebSocket, `SETUP` MIME/auth? | Check routing/TLS/config and setup errors |
| Requests slow while TCP stays open | Slow upstream DB/HTTP or subscriber not requesting demand? | Inspect latencies, threads, active streams, deadlines |
| Streams stop after exactly 60 seconds | Gateway/proxy idle timeout or misconfigured keepalive? | Test through real ingress; tune timeouts with data |
| Mass stream drops after deploy | Pod stop/rolling drain and reconnect designed? | Verify graceful shutdown, retries, and cursors |
| Retry spikes | Flapping connections, circuit breakers, duplicate callbacks? | Cap retries, add backoff/jitter, eliminate hot loops |
| Reserve command deducts stock twice | Missing server idempotency or client generating new `requestId`? | Inspect inbox/transactions/outbox; fix deduplication |
| Client loses tokens or TLS certs expire | Trust stores, keys/certs, auth setup, rotation policies | Fix secrets/certs; never disable verification |
| Memory grows with many request-streams | Unbounded buffers, missing cancel cleanup, stream leaks? | Check demand, heap, connection/buffer metrics |
| Passes locally, fails in CI | Port races, timing, unready server, tight timers? | Random ports, readiness checks, Testcontainers/Awaitility |
| DTO decodes yet data is wrong | Schema version or semantic mismatch? | Contract tests and compatible decoders; never retry bad data |

### Incident response workflow

1. **Isolate the error layer:** transport, setup/security, application logic, codecs, backpressure, or dependency.
2. **Contain impact:** if retries/reconnects spike, throttle concurrency / trip circuit breakers and hold messages in durable brokers/outboxes.
3. **Determine business outcome:** look up by `requestId`/`eventId`; never guess from timeouts.
4. **Fix root cause:** DNS/ingress/TLS, resource policies, validation code, codecs/schemas, or downstream dependencies.
5. **Recover safely:** restore traffic, re-establish RSocket sessions as appropriate, and redrive backlog using idempotency keys.
6. **Reconcile and observe:** verify DB state, HTTP side effects, outbox/broker state, stream cursors, and duplicate rates.
7. **Postmortem:** add regression test fixtures for the exact scenario and tune timeouts/keepalives/retry budgets to real SLOs.

## 15. Takeaways

- RSocket has **four primary interaction models**, each with distinct completion/error/demand contracts.
- `StepVerifier` verifies Reactive Streams behavior; only integration tests over real transports validate `SETUP`, routes, codecs, and network backpressure/cancellation.
- **Timeouts or disconnects do not prove requests were not processed**; side-effecting operations require idempotency, inbox/outbox, and reconciliation.
- Fire-and-forget `send()` is **not** a business acknowledgment.
- Retries must be bounded, error-classified, and paired with **reconnect/stream-state recovery**; re-subscribing alone does not guarantee a fresh session or exactly-once delivery.
- Failure tests must verify **final state** in databases, HTTP/brokers, and backlogs—not just client exceptions.

### Self-check questions

1. Why does `send()`'s `Mono<Void>` not prove the server committed work?
2. What is the difference between `StepVerifier.thenCancel()` and a TCP reset through a fault proxy?
3. If a client receives 5 items before a stream breaks, what metadata is needed to recover without loss or duplicates?
4. Why can `retryWhen` keep retrying on a closed requester instead of truly recovering?
5. When a reserve command times out after DB commit, why must retries preserve the same `requestId`?
6. Can virtual time test network keepalives and TLS handshakes?
7. Which four scenarios must be classified separately: invalid SKU, rejected SETUP, connection lost, and downstream HTTP 503?
8. Why does `limitRate(16)` not mean every buffer or concurrency pool is bounded at 16?

## References

- [Spring Framework — RSocket Overview, RSocketRequester, Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 3.5 — RSocket Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Boot 3.5 API — LocalRSocketServerPort](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/)
- [RSocket Java — Reactor Netty Transport](https://github.com/rsocket/rsocket-java)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html)
- [RSocket Java API — Protocol Error Exceptions](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/package-summary.html)
- [Spring Integration — RSocket Support](https://docs.spring.io/spring-integration/reference/rsocket.html)
- [Spring Security — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
