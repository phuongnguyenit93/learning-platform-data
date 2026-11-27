# Timeouts and Retries in Spring Integration WebFlux Reactive Flows

## 1. Why Must Timeouts and Retries Be Designed Together?

An order-processing system receives messages from Kafka, sends HTTP requests via WebFlux to a pricing API, receives the results, and writes to a database. When the API responds slowly or is temporarily unavailable, the integration flow must answer three questions:

1. **How long to wait?** TCP connection, pool waiting, HTTP response reception, and end-to-end business processing each have different deadlines.
2. **When to retry?** Transient errors should be retried, whereas requests with invalid data or insufficient permissions usually must stop.
3. **Is retrying safe?** An HTTP client timeout does not prove the server did not process the request. For side-effecting operations, retries can create duplicate data.

In the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we use inbound/outbound adapters, gateways, pollers, and `MessageChannel`s to connect HTTP, files, SFTP, JMS, AMQP, Kafka, and databases. Timeouts/retries sit at **multiple boundaries**: from receiving the source message, entering a channel, calling `WebClient`, receiving a reply, through ACKing/committing at the source system.

**Lesson objectives:** distinguish timeouts at each layer; construct `Mono`/`Flux` with retries placed properly; connect that policy with WebFlux outbound gateways, inbound request-reply, error channels, and idempotency; and test behavior with Reactor `StepVerifier`.

~~~mermaid
flowchart LR
    A["Kafka / JMS / DB / Service"] --> B["Spring Integration Message"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway / WebClient"]
    D -->|"HTTP request"| E["Partner API"]
    E -->|"HTTP response or timeout"| D
    D -->|"Reply / Error"| F["Business handler / error flow"]
    F --> G["ACK / persist / DLQ"]
    D -.->|"retry when safe"| E
~~~

**Foundational point:** *reactive* does not mean "never times out" or "free retries." Reactor models result/error/cancellation signals via publishers; Spring Integration and the source system govern message paths, transactions, and ACKs.

## 2. Timeout Map: There Is No Single Clock

| Timeout / limit type | Where it applies | What problem does it solve? | What it does not guarantee |
|---|---|---|---|
| `pendingAcquireTimeout` | Reactor Netty `ConnectionProvider` | Waiting for an available connection in the pool | TCP connection, HTTP response |
| `CONNECT_TIMEOUT_MILLIS` | Reactor Netty `HttpClient` | TCP connection establishment | Entire DNS/TLS, pool wait, server processing |
| TLS handshake timeout | SSL/TLS transport | Security handshake duration | Waiting for response body or business logic |
| `responseTimeout` | Reactor Netty HTTP client | Waiting for response data at the transport layer | Total deadline including queues + retries + downstream |
| `timeout(Duration)` | Reactor `Mono` / `Flux` | Bounding wait time for signals in a publisher | Automatic rollback of remote side effects |
| `requestTimeout` | Messaging gateway / channel | Waiting to send request message to the target channel | Remote HTTP processing time |
| `replyTimeout` | Spring Integration request-reply gateway | Waiting for the flow's reply message | TCP/HTTP timeout or total `Flux` stream duration |
| Business deadline | Entire workflow | Maximum acceptable total elapsed time | Existing automatically if not explicitly programmed |
| Consumer/poller timeout | Kafka/JMS/AMQP/DB and scheduler | Adapter/consumer-specific contract | Automatic alignment with WebClient timeouts |

A request may pass through **pool wait → DNS → TCP/TLS → send body → wait for response → decode → DB write → source message ACK**. Thus, setting `responseTimeout(5s)` does not mean the whole workflow is guaranteed to finish in 5 seconds.

~~~mermaid
sequenceDiagram
    participant Flow as IntegrationFlow
    participant Pool as Connection pool
    participant Net as HTTP transport
    participant Remote as Remote API
    Flow->>Pool: Acquire
    Note over Flow,Pool: pendingAcquireTimeout
    Pool->>Net: Connection
    Note over Net: connect/TLS timeout when opening new
    Net->>Remote: HTTP request
    Note over Net,Remote: responseTimeout + Reactor timeout
    alt Valid response
        Remote-->>Net: HTTP 200 JSON
        Net-->>Flow: Reply
    else Transient error
        Net-->>Flow: Error signal
        Note over Flow: Retry policy checks error & budget
    end
~~~

**Deadline budget:** if the user SLA is 8 seconds, do not allow three attempts each with `responseTimeout(8s)` plus unbounded backoff. Distinguish **per-attempt timeout** from **overall operation deadline**, including retries.

## 3. How `timeout` Works on Mono and Flux

### 3.1. Mono: Waiting for One Result or Completion

`Mono<T>` emits at most one value and completes, completes empty, or emits an error. The `timeout(Duration)` operator emits a `TimeoutException` if the publisher does not produce a matching signal before the deadline.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<String> lookup = remoteLookup()
    .timeout(Duration.ofSeconds(2));
~~~

`remoteLookup()` is an application-provided function returning a publisher. On timeout, Reactor **cancels the upstream subscription** and emits `onError` downstream. Cancellation does not prove the remote HTTP server or database aborted/rolled back work in progress.

If upstream returns `Mono.empty()` and completes before the timeout, that is an **empty completion**, not a timeout. Define the "not found" case explicitly:

~~~java
Mono<String> lookup = remoteLookup()
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No matching result")))
    .timeout(Duration.ofSeconds(2));
~~~

Do not turn every `Mono.empty()` into an error if an empty result is valid under the contract.

### 3.2. Flux: Deadline Between Emissions

`Flux<T>` can emit many elements. The simple `timeout(Duration)` form on `Flux` governs waiting for the **first element** and the **interval between subsequent elements**, not an overall deadline for a long-running stream by default:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<String> updates = remoteUpdates()
    .timeout(Duration.ofSeconds(10));
~~~

If each update arrives every 5 seconds, the stream can continue for minutes without timing out. If a stream must **live at most 60 seconds total**, add an explicit subscription/lifecycle deadline rather than relying solely on an inactivity timeout.

With SSE, quiet intervals may be normal; an overly short timeout can sever healthy connections. Treat heartbeats, time-to-first-event, inactivity timeouts, and max stream lifetime as four distinct concepts.

### 3.3. The Timeout Operator Is Not Time Travel

When a timeout fires, it stops waiting or cancels the subscription, yet it does not:

- Undo a `POST` already executed by the remote server.
- Recall a message already sent to Kafka/JMS.
- Roll back a committed database transaction.
- Guarantee interrupting a blocking task already running on an executor.

That is why retries must be paired with **idempotency, delivery state tracking, and error observability**, not just a Reactor operator.

## 4. Retries in Reactor: Resubscribing, Not "Resuming Where It Broke"

`retryWhen(...)` listens for errors and **resubscribes upstream** according to a `Retry` spec. For an HTTP request, this can trigger a fresh HTTP exchange. For a `Flux` mid-stream, items already emitted before the error may be re-emitted upon resubscription, depending on the publisher type.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> result = remoteLookup()
    .retryWhen(Retry
        .backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5));
~~~

Here `backoff(2, ...)` means at most **two retries after the initial attempt** (three attempts total), **not** two total attempts. `jitter` randomizes retry delays so multiple clients do not stampede the server simultaneously when it recovers.

### 4.1. Retry Only Appropriate Errors

| Scenario | Retry by default? | Reason |
|---|---|---|
| HTTP `400` (bad request) | **No** | Resending the same invalid data usually stays invalid |
| HTTP `401`/`403` | **No** | Fix authentication/authorization instead of looping endlessly |
| HTTP `404` | Usually **no** | May be a valid business outcome or wrong URL |
| HTTP `409` | Per contract | Could be a resolvable conflict or a permanent error |
| HTTP `429` | **Conditional** | Must respect rate limits, potentially honoring `Retry-After` |
| HTTP `502`/`503`/`504` | **Conditional** | Typically transient, yet still needs a budget and backoff |
| Connection reset / transient network | **Conditional** | Retry when idempotent; distinguish permanent TLS/certificate errors |
| Timeout after `POST` sent | **Only when safe** | Remote may have already executed side effects |
| JSON decode/schema error | Usually **no** | Retrying does not fix malformed data or schema drift |

`Retry.filter(...)` lets you specify which errors are retryable. Never use unbounded `retry()` in production, and do not retry every `Throwable`—configuration, validation, TLS trust, or decoding errors will not heal by repeating the request.

### 4.2. Retrying When a Flux Already Emitted Partial Data

Suppose a remote stream emitted `event-1`, `event-2`, and then dropped the connection. Applying `retryWhen` to the whole `Flux` can cause the new subscription to re-emit `event-1` and `event-2`. The subscriber sees duplicates:

~~~text
Attempt #1: event-1 → event-2 → network error
Retry #1:   event-1 → event-2 → event-3 → complete
Subscriber: event-1, event-2, event-1, event-2, event-3
~~~

For a business stream to resume cleanly, you need **event IDs/cursors, history retention, deduplication**, and a repositioning contract (such as `Last-Event-ID` for SSE). `retryWhen` only repeats subscription; it cannot infer a resume position on its own.

## 5. Placement of Timeout and Retry Determines the Outcome

This is one of the easiest mistakes to make when coding reactive resilience. **Operator order changes timeout scope.**

~~~java
// A: timeout PER ATTEMPT; each retry gets another 3 seconds to wait.
Mono<QuoteResponse> perAttempt = requestOnce()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));

// B: timeout for the ENTIRE chain, including attempts and backoff.
Mono<QuoteResponse> overall = requestOnce()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(8));

// C: two-tier timeout: 3 seconds per attempt and 8 seconds maximum total.
Mono<QuoteResponse> bounded = requestOnce()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(8));
~~~

`requestOnce()` illustrates a **cold/repeatable publisher** created from an HTTP call. The three snippets are **mutually exclusive alternatives**, not variables to declare together in the same scope. When reusing a publisher, verify that **a new subscription actually triggers a new request** and that the body is repeatable; single-read streaming request bodies may not be repeatable.

| Operator placement | Consequence |
|---|---|
| `timeout` **before** `retryWhen` | Timeout can trigger a retry; each attempt has its own timer |
| `timeout` **after** `retryWhen` | One overall deadline covers the entire retries/backoff chain; expiry emits error downstream |
| Combining both | Bounds both each attempt and total time; suitable for many outbound HTTP operations |
| `onErrorResume` placed before retry swallowing errors | Retry may never run because upstream already turned into completion/fallback |
| `onErrorResume` after retry | Falls back only after retry policy exhausts or hits a non-retryable error |

**Note on retries and overall deadlines:** when a trailing `timeout(8s)` emits an error, it cancels the preceding chain's subscription. That does not mean the partner server necessarily stops processing an in-flight HTTP request. For side-effecting APIs, still record idempotency keys and reconcile outcomes.

## 6. WebClient: Distinguishing HTTP Status Errors from Network Errors

With `WebClient.retrieve().bodyToMono(...)`, HTTP 4xx/5xx responses normally raise `WebClientResponseException`, exposing the status code. Connection/transport failures typically surface as `WebClientRequestException` with the root cause nested inside; Reactor `timeout` emits `TimeoutException`.

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import java.util.concurrent.TimeoutException;

boolean shouldRetry(Throwable error) {
    if (error instanceof TimeoutException) {
        return true; // Only safe if the operation is idempotent.
    }
    if (error instanceof WebClientResponseException ex) {
        int status = ex.getStatusCode().value();
        return status == 429 || status == 502
            || status == 503 || status == 504;
    }
    return false;
}
~~~

The policy above intentionally **does not** retry `WebClientRequestException` network errors yet. This is a deliberate choice for the example: in production, inspect the cause (`ConnectException`, reset, DNS, certificate, TLS, etc.) and decide per contract. Do not blindly add `error instanceof WebClientRequestException`, because truststore/TLS hostname errors are not fixed by retrying.

When special statuses need custom handling (e.g., `404` meaning "no data" rather than an error), use WebClient's `onStatus(...)` or `exchangeToMono(...)` to map statuses into domain results. **Never** return a fake success-like `QuoteResponse` for all 5xx errors, or downstream may persist bogus data.

## 7. Configuring HTTP Transport and Connection Pool

The Reactor Netty layer controls TCP connect, response wait, and pool acquisition. These timeouts complement Reactor's `timeout`, rather than replacing it.

~~~java
package com.example.integration;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class ResilientWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider quoteConnectionPool() {
        return ConnectionProvider.builder("quote-http-pool")
            .maxConnections(20)
            .pendingAcquireMaxCount(40)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(30))
            .build();
    }

    @Bean("quoteWebClient")
    WebClient quoteWebClient(
            WebClient.Builder builder,
            @Qualifier("quoteConnectionPool") ConnectionProvider pool) {
        HttpClient transport = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1500)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .build();
    }
}
~~~

Reading the configuration by layer:

1. `maxConnections` caps connections, **not requests/second**.
2. `pendingAcquireTimeout` limits waiting for the pool to grant a connection; requests can fail before any TCP connection is attempted.
3. `CONNECT_TIMEOUT_MILLIS` bounds TCP connect, excluding upstream queue wait times or post-exchange work.
4. `responseTimeout` governs waiting for an HTTP response at the transport layer; it is not the total deadline with retries.
5. The dedicated pool is closed when the Spring context shuts down via `destroyMethod = "dispose"`; shared event loops have their own lifecycle.

These parameters are **learning values**. If a partner API caps concurrency at 10 requests, merely raising `maxConnections` to 100 causes overload. Monitor active/pending connections, remote latency, response rates, and in-flight requests.

## 8. Complete Example: Reactive WebClient with Two-Tier Deadlines and Filtered Retries

This example calls a quoting API `POST /api/quotes`. It assumes **the partner supports `Idempotency-Key`** and returns the same result when receiving the same key again. If the API does not enforce that rule, retrying a `POST` as shown cannot be considered safe.

~~~java
package com.example.integration;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class PartnerQuoteClient {

    public record QuoteRequest(
        String eventId, String orderId, int weightKg) { }

    public record QuoteResponse(
        String orderId, long amountVnd, String currency) { }

    private final WebClient client;

    public PartnerQuoteClient(
            @Qualifier("quoteWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<QuoteResponse> quote(QuoteRequest request) {
        // Mono.defer ensures a fresh subscription can create a fresh HTTP exchange.
        return Mono.defer(() -> client.post()
                .uri("https://partner.example/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", request.eventId())
                .bodyValue(request)
                .retrieve()
                .bodyToMono(QuoteResponse.class))
            // Each attempt waits at most 3s at the publisher level.
            .timeout(Duration.ofSeconds(3))
            .retryWhen(Retry
                .backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(this::retryable)
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()))
            // Overall deadline covering attempts and backoff.
            .timeout(Duration.ofSeconds(8));
    }

    private boolean retryable(Throwable error) {
        if (error instanceof TimeoutException) {
            return true;
        }
        if (error instanceof WebClientResponseException ex) {
            int status = ex.getStatusCode().value();
            return status == 429 || status == 502
                || status == 503 || status == 504;
        }
        return false;
    }
}
~~~

**What to understand before using:**

- The URL `https://partner.example/api/quotes` is a **placeholder address** to be replaced via protected configuration; no real server backs this example URL.
- `eventId` must remain stable across attempts and restarts; do not generate a new UUID inside each retry.
- `Mono.defer` keeps request construction inside the subscription context. The immutable DTO request body here is repeatable; a single-read `Flux<DataBuffer>` may not be repeatable.
- `timeout(3s)` before retry bounds each attempt; the trailing `timeout(8s)` is the overall deadline. Transport `responseTimeout(3s)` is a separate limit, so avoid conflicting values relative to expected outcomes.
- `Retry.backoff(2, ...)` allows up to three total attempts. Once retries exhaust, `onRetryExhaustedThrow` re-emits the final underlying failure so downstream can classify it cleanly rather than turning errors into success.
- The filter does not retry `400`, `401`, `403`, or decoding errors; when the remote returns `429`, production code should inspect `Retry-After` and overall budgets rather than relying solely on fixed backoff.
- `.timeout(8s)` cancels the publisher on expiry but does not guarantee remote rollback. Reconcile using `eventId`.

**Two kinds of timeout can arise:** HTTP transport timeouts may carry a different exception/cause type than Reactor's `java.util.concurrent.TimeoutException`. The `retryable` filter above is illustrative only; in production, classify all transport errors via logs/tests on your exact Reactor Netty version.

## 9. Where Does the Policy Live in a Spring Integration Flow?

There are **two organizational patterns**; do not treat them as interchangeable defaults.

### 9.1. Using the WebFlux Outbound Gateway

When the flow needs a **reply message** carrying the HTTP result for further processing, use `WebFlux.outboundGateway(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class QuoteOutboundFlow {

    public record QuoteRequest(String eventId, String orderId) { }
    public record QuoteResponse(String orderId, long feeVnd) { }

    @Bean
    IntegrationFlow quoteGateway(WebClient quoteWebClient) {
        return IntegrationFlow.from("quoteRequests")
            .handle(WebFlux.outboundGateway(
                    "https://partner.example/api/quotes",
                    quoteWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class))
            .channel("quoteResults")
            .get();
    }
}
~~~

Here the configured WebClient **transport timeouts** apply. However, `Retry.backoff` inside `PartnerQuoteClient.quote(...)` from Section 8 **does not automatically apply** to this outbound gateway: the gateway invokes `WebClient` directly per endpoint configuration. If you want retries at the Spring Integration layer, design **advice/error flows/retries compatible with the endpoint's asynchronous behavior**, verify error types, and test in practice; never assume retry advice designed for synchronous handlers automatically catches errors emitted asynchronously later by a publisher.

When the API needs a reply for DB writes or routing, preserve the request-reply contract instead of turning it into fire-and-forget. If retries must survive application restarts, combine an outbox/broker and durable retry orchestration rather than keeping requests only in memory.

### 9.2. Using a Reactive Client as a Side-Effect Step Without Business Reply

For a branch that only issues commands, writes status, or performs error-managed side effects, you can wrap `PartnerQuoteClient` inside a `ReactiveMessageHandler`. Spring Integration 6.1+ Java DSL supports `handleReactive(...)` taking a handler returning `Mono<Void>`:

~~~java
@Bean
IntegrationFlow triggerRemoteQuotes(PartnerQuoteClient client) {
    return IntegrationFlow.from("quoteCommands")
        .handleReactive(message -> {
            PartnerQuoteClient.QuoteRequest request =
                (PartnerQuoteClient.QuoteRequest) message.getPayload();
            return client.quote(request)
                .doOnNext(response -> System.out.println(
                    "Quote received: " + response))
                .then();
        })
        .get();
}
~~~

This is a **one-way side-effect pattern** producing no `QuoteResponse` reply for downstream. The example illustrates **keeping the `Mono` inside the pipeline**, avoiding manual `block()` or `subscribe()`. In real applications, replace logging with reactive persist/publish operations with error handling; never conclude an operation is durable merely because a log printed.

If a handler must produce a **reply** so an inbound gateway returns an HTTP response, pick a request-reply endpoint/flow or build a publisher/reply-channel bridge with explicit correlation; never assume `handleReactive(...).then()` returns a business payload.

## 10. Error Channel, replyTimeout, and Asynchrony

Spring Integration can handle errors via `ErrorMessage`/`errorChannel`, advice, or flow error branches. Distinguish **errors during message dispatch** from **errors raised later while the HTTP publisher executes**.

| Case | What can happen | What to verify |
|---|---|---|
| Channel rejects message | `send` returns false or throws exception | Capacity, dispatcher, consumer, send timeout |
| WebClient builds HTTP request but connection refused | Reactive error after publisher subscription | Endpoint error flow, correlation to source message |
| Remote returns `503` | HTTP status becomes an error signal under default response reading | Retry policy, circuit breaker, dead-letter |
| Inbound gateway gets no reply | Gateway waits until `replyTimeout` | `errorOnTimeout`, error channel, HTTP response mapping |
| HTTP client closes connection | Cancellation may propagate into reactive pipeline | Which work already executed and may continue |

**`replyTimeout`** on an inbound request-reply gateway is the timeout for **waiting for the reply message**; it does not replace HTTP transport timeouts on an outbound WebClient. If downstream returns an early reply containing a `Flux<T>`, emitting the `Flux` can outlast `replyTimeout` without violating the initial reply wait deadline.

Do not assume every WebClient error is thrown right at `MessageChannel.send(...)`: asynchronous paths can signal errors after `send` has returned. Write **integration tests** covering network errors, HTTP statuses, and error channel routing on your actual Spring Integration version.

If clients calling an inbound gateway expect `504 Gateway Timeout`, `503 Service Unavailable`, or a custom error schema, design the corresponding **HTTP error mapping**. A `TimeoutException` inside a flow does not guarantee the framework returns the business's desired status automatically.

## 11. Retries, Idempotency, and Source Message ACK/Commit

When requests originate from Kafka/JMS/AMQP/file/SFTP/DB pollers, HTTP retries affect the delivery guarantees of the **source message**. For example:

~~~mermaid
sequenceDiagram
    participant Source as Kafka/JMS source
    participant App as IntegrationFlow
    participant API as Partner API
    Source->>App: order.created (eventId=e-101)
    App->>API: POST Idempotency-Key=e-101
    API->>API: Persist result
    API--xApp: Response lost / timeout
    Note over App: Unknown whether remote committed
    App->>API: Retry POST with same key e-101
    API-->>App: Return stored result for key e-101
    App->>Source: ACK per source contract
~~~

**Idempotency** is the ability to reprocess the same operation without duplicating side effects. It requires support from **the receiver or business layer**. Merely attaching an `Idempotency-Key` header provides no deduplication unless the partner server checks and stores the key.

Operational design should define:

1. **Stable key:** a unique `eventId`/`commandId` per operation, preserved across both HTTP retries and broker redeliveries.
2. **Outcome store:** persists requests, send status, responses, or reconciliation tokens; tracks whether tasks are `PENDING`, `SUCCEEDED`, `FAILED`, or `UNKNOWN`.
3. **Source ACK:** ACKing Kafka/JMS before sufficient confirmation can lose work on restart; ACKing late can duplicate processing after redelivery.
4. **Durable retries:** outbox/broker with backoff and dead-lettering to survive crashes. In-memory Reactor `retryWhen` does not survive restarts.
5. **Compounded retry counts:** if WebClient tries 3 times and the broker redelivers 5 times, one event can trigger far more HTTP requests than expected.
6. **Manual reconciliation:** for uncertain outcomes, query the receiver's status by idempotency key rather than blindly POSTing indefinitely.

Truly side-effect-free `GET` operations can retry more simply, though they still require rate limits, timeouts, request budgets, and overload protection.

## 12. Concurrency Limits, Backpressure, and Circuit Breakers

Retries increase traffic sent to an already degraded system. When 1,000 messages time out together, every message retrying independently can trigger a **retry storm** and prevent the partner service from recovering.

| Mechanism | What it solves | What it does not guarantee |
|---|---|---|
| `retryWhen` + backoff/jitter | Controlled retries after eligible failures | Durable delivery across restarts |
| `timeout` and deadlines | Bounds time per attempt or overall operation | Remote rollback of side effects |
| `flatMap(..., concurrency)` | Bounds concurrently subscribed inner publishers | Rate limiting / requests-per-second caps |
| `limitRate` / Reactive Streams demand | Regulates requests within a reactive chain | External brokers/JDBC understanding demand |
| Bounded queue | Caps backlog at a boundary | Increasing remote processing capacity |
| Connection pool | Caps sockets and acquire wait times | Per-second throughput limit |
| Circuit breaker | Temporarily stops calling when dependency fails repeatedly | Replacing reconciliation/idempotency |
| Rate limiter | Throttles requests by policy | Classifying retryable errors |

Reactor example bounding concurrent HTTP requests:

~~~java
import reactor.core.publisher.Flux;

Flux<PartnerQuoteClient.QuoteResponse> quotes =
    Flux.fromIterable(requests)
        .flatMap(client::quote, 8);
~~~

Here `requests` is an `Iterable<PartnerQuoteClient.QuoteRequest>` and `client` is `PartnerQuoteClient`. Parameter `8` caps concurrently active inner publishers; it does **not** mean 8 HTTP requests per second. When ordering must be preserved, use `concatMap` or an ordering-preserving boundary.

**Note:** per-flow concurrency limits do not enforce **application-wide** limits across multiple instances/partitions. You may need a shared rate limiter or partner quota management. Retry budgets and circuit breakers should also be coordinated across replicas.

## 13. Timeouts/Retries for Flux Streams and SSE

Streams can stay open for a long time; "success" and "completion" differ from a single JSON response:

- With `Mono<QuoteResponse>`, success typically means receiving one object and completing.
- With `Flux<ShipmentEvent>`, each event emits as it arrives; it may complete after N items, error mid-stream, or stay open indefinitely.
- With `text/event-stream`, HTTP connections stay open long; proxies and browsers have their own idle timeouts and reconnect behavior.
- With a `Flux` that emits two events then errors, `retryWhen` may replay events from the beginning. Event IDs, cursors, and deduplication are needed.
- If a client disconnects SSE, cancellation may reach upstream, yet messages already written to a broker/DB are not recalled automatically.

Example distinguishing a stream idle timeout:

~~~java
Flux<ShipmentEvent> liveUpdates = remoteEventStream()
    // Signal timeout if no event arrives within 15s.
    .timeout(Duration.ofSeconds(15))
    .doOnCancel(() -> log.info("Client no longer consumes stream"));
~~~

`remoteEventStream()`, `ShipmentEvent`, and `log` belong to the real application. `timeout(15s)` here is **not a 15-second maximum total stream lifetime**. If a stream can legitimately stay silent longer, add heartbeats or adjust the policy. Before retrying a stream, establish whether resuming from an offset/event ID is supported.

## 14. Observability, Security, and Lifecycle

Measure metrics **per attempt** and **per business task**, avoiding counting every retry attempt as a completed business transaction:

- **Latency:** acquire wait, TCP connect, TLS, response time, total duration including retries, p50/p95/p99.
- **Retries:** attempt counts, retry counts, retries exhausted, backoff time, final errors, `429/5xx` responses.
- **Pool:** active/idle/pending connections, acquire failures, and connection lifetimes.
- **Flow:** in-flight messages, queue depth, consumer lag, ACK/commit, dead-letters, messages in `UNKNOWN` outcome.
- **Stream:** active subscriptions, cancellations, idle timeouts, reconnects, duplicate events, and event lag.

Never attach `orderId`, tokens, or full URLs with sensitive query strings as high-cardinality metric tags. Use sanitized trace/correlation IDs in logs and ensure `Authorization` headers or personal data are never exposed.

For security, retries must never inadvertently send credentials to a different host: enforce endpoint allowlists, TLS hostname verification, redirect controls, and token refresh flows. Never disable certificate checks to turn TLS failures into "success," and never loop retries on `401` in place of a secure credential refresh process.

For lifecycle, reuse `WebClient`/connection pools and close them with the Spring context. On shutdown, stop accepting new work per policy and persist incomplete task states so brokers/outboxes can resume after restart. Never rely on an in-memory `Mono.retryWhen` to guarantee delivery across restarts.

## 15. Testing with StepVerifier and Virtual Time

Testing retries against wall-clock time is slow and flaky. `reactor-test` provides `StepVerifier.withVirtualTime(...)` to control time schedulers in reactive pipelines.

~~~groovy
// build.gradle - test dependencies
testImplementation 'io.projectreactor:reactor-test'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

### 15.1. Retrying Twice Then Succeeding

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryVirtualTimeTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> remote = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        });

        StepVerifier.withVirtualTime(() ->
                remote.retryWhen(Retry
                    .backoff(2, Duration.ofSeconds(1))
                    .jitter(0.0)
                    .filter(e -> e instanceof IllegalStateException)))
            .thenAwait(Duration.ofSeconds(4))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

With `jitter(0.0)`, illustrative backoffs are 1 second and 2 seconds. The test advances virtual time by 4 seconds to cover both delays. That `Retry.backoff(2, ...)` produces **two retries, three attempts** is verified by `attempts.get() == 3`.

### 15.2. Timeout Emits Error, Not Empty Completion

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutVirtualTimeTest {

    @Test
    void timesOutBeforeSlowResponse() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
~~~

This test verifies the Reactor operator on a simulated publisher; it does **not** verify WebClient's actual TCP connect/HTTP response handling. To test real transport timeouts and HTTP retries, use a mock HTTP server simulating `503`, `429`, response delays, connection resets, and invalid bodies.

### 15.3. Minimum Test Matrix with a Mock HTTP Server

| Simulated condition | Expectation |
|---|---|
| Remote `200` within deadline | One success result, no retry |
| Remote `400` | No retry, error classified properly |
| Remote `401`/`403` | No infinite retries or token leakage |
| Remote `429` then `200` | Retries per budget/rate limit; same idempotency key |
| Remote `503` twice then `200` | Three attempts total and one result |
| Remote continuously `503` | Retries exhaust, error routed to error flow |
| Remote processes `POST` then drops response | Retries with same key, remote creates no duplicate side effect |
| Pool full / acquire wait too long | Distinguish acquire failure from HTTP server timeout |
| Source message redelivered | No duplicate business outcome even after internal client retries |
| `Flux` fails after two events | Observe repeated items on resubscription |
| Client disconnects SSE | Subscription cleaned up; do not assume DB/broker rolled back |

## 16. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| "`timeout(3s)` means the remote definitely stopped processing" | Timeout only cancels/stops waiting on the subscription; remote side effects may have happened |
| "`retryWhen(Retry.backoff(2))` sends only two attempts total" | One initial attempt plus up to two retries |
| "Where `timeout` is placed does not matter" | Before retry bounds each attempt; after retry bounds the entire chain |
| "`Flux.timeout(10s)` cuts off the stream after exactly 10 seconds" | Normally limits wait time for the first/next element, not total stream age |
| "Retrying HTTP `429` immediately is faster" | Needs backoff, honoring `Retry-After` and rate limits |
| "`400` or JSON decode errors go away if retried" | Usually data/contract issues that must be fixed at the source |
| "`send() == true` means WebClient finished calling successfully" | Channel send result per contract, not completed HTTP exchange |
| "WebFlux outbound gateway automatically inherits retry policy from another WebClient service" | Only policies attached to the active request/publisher/endpoint apply |
| "Retrying a `POST` is always harmless if the request has a UUID" | The server must **enforce** idempotency by that key |
| "Reactor retries survive application restarts" | Requires outbox/broker/persistence and restart recovery logic |
| "Reactive backpressure automatically propagates back through every Kafka/JMS/DB" | Each adapter/broker has its own limits, prefetch, ACKs, and semantics |

## 17. Exercises

1. Use `StepVerifier.withVirtualTime` to test `timeout` on `Mono.delay`, change 2 seconds to 5 seconds, and explain the difference when the remote finishes after the deadline.
2. Make a publisher fail twice then succeed; verify `Retry.backoff(2, ...)` and `attempts == 3`. Change to `backoff(1, ...)` to observe retry exhaustion.
3. Move `timeout` before/after `retryWhen` and use virtual time to measure the difference between per-attempt deadlines and overall deadlines.
4. Build a mock API returning `503, 503, 200` sequentially; observe HTTP status mapping, actual call counts, and backoff delays.
5. Have the mock return `400`, `401`, and `429`, verifying only contractually allowed errors are retried.
6. Simulate an API accepting `POST` and persisting data successfully while dropping the response; implement idempotency by `eventId` in the mock and prove only one side effect is recorded.
7. Invoke `PartnerQuoteClient` inside a reactive handler for outbound calls; handle errors without swallowing details and without calling `block()` on the WebFlux event loop.
8. Compare configuring `WebFlux.outboundGateway` directly versus `PartnerQuoteClient.quote(...)`; identify where retry operators actually run and where only transport timeouts exist.
9. Add a Kafka/JMS source to the flow; intentionally restart the application mid-retry, and design a durable outbox/retry flow with proper ACKs.
10. Stream three events from SSE/Flux then fail, enable `retryWhen`, and observe duplicate data. Propose cursor/replay/deduplication so events are neither missed nor duplicated.
11. Saturate the mock client's connection pool and distinguish pending-acquire timeouts from response timeouts via logs/metrics.
12. Build an 8-second SLA budget table covering queues, remote HTTP, backoff, and downstream persistence; define when retries stop and what result returns to the inbound HTTP client.

**Synthesis scenario:** a `POST /api/orders` creates an order, writes to the DB, emits a Kafka event, and calls a shipping partner via `WebClient`. The partner creates the shipment, but the response is lost; the external HTTP client is still waiting and the Kafka message may be redelivered. Choose per-layer timeouts, overall deadline, retry policy, idempotency key, transaction boundaries, and criteria for returning `201 Created` vs. `202 Accepted`. Why is simply adding `retryWhen(3)` to a `Mono` insufficient?

## 18. References

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux outbound gateways/adapters and reactive HTTP mechanics.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request-reply contracts, request/reply timeouts, and error channels.
- [Spring Integration Reference — Reactive Streams](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer`, and reactive message handlers.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request/response handling and HTTP errors.
- [Spring Framework Reference — WebClient Retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): how `retrieve()` handles HTTP 4xx/5xx and custom status handling.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): transport/connect/response timeouts and connection pooling.
- [Project Reactor Reference — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, retry signals, backoff, and attempt limits.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and testing asynchronous publishers.

> **Takeaway:** Timeouts bound **how long a layer waits**, while retries **repeat a subscription or request** when permitted. In Spring Integration WebFlux, distinguish pool/TCP/response timeouts from `Mono.timeout`, `Flux.timeout`, `replyTimeout`, and business deadlines; order retry operators deliberately, enforce idempotency on side-effecting operations, and design ACK/outbox/error flows to maintain consistency across failures or restarts.
