# Non-Blocking Error Handling in Spring Integration WebFlux

## 1. The Problem: Keeping the Flow Stable When External Services Fail

An application receives events from Kafka or JMS, checks inventory over HTTP, and updates orders in a database. If the HTTP server returns `503 Service Unavailable`, the network drops, or a JSON payload fails to decode, the flow must detect, classify, record, and decide how to handle the error. The anti-pattern is calling `block()` to wait on WebClient, catching exceptions with `try/catch`, and calling `Thread.sleep` to retry. That ties up threads (especially dangerous on the Reactor Netty event loop) and masks the asynchronous error contract.

**Non-blocking error handling** uses Reactive Streams error signals and Reactor operators such as `doOnError`, `onErrorMap`, `onErrorResume`, `retryWhen`, and `timeout`, coordinated with Spring Integration error flows. The goal is not to "swallow every error so the program keeps running," but to ensure **errors propagate, recover, or translate into controlled business outcomes** without locking threads waiting on I/O.

This topic belongs to the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, where inbound/outbound adapters, gateways, pollers, and `MessageChannel`s connect HTTP, files, SFTP, JMS, AMQP, Kafka, and databases. Crossing those boundaries requires clearly distinguishing HTTP request errors, Reactor pipeline errors, message dispatch errors, poller/broker errors, and business errors.

~~~mermaid
flowchart LR
    A["Kafka / JMS / File / HTTP"] --> B["Spring Integration Message"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway / WebClient"]
    D -->|"HTTP request"| E["Inventory API"]
    E -->|"HTTP response / network error"| D
    D --> F{"Outcome"}
    F -->|"Success"| G["Reply Message<InventoryReply>"]
    F -->|"Retryable error"| H["Bounded retry"]
    F -->|"Business error"| I["Structured error outcome"]
    F -->|"Unrecovered error"| J["Error flow / DLQ / alert"]
    H --> D
~~~

In the diagram, the retry edge represents logic when policy permits, not that Spring Integration automatically retries every error. For source messages requiring guaranteed processing, ACK/commit steps, outbox persistence, and idempotency must be designed separately.

## 2. Error Contract of Mono and Flux

Reactive Streams defines three core terminal/data signals: `onNext(T)` emits data, `onComplete()` signals completion, and `onError(Throwable)` signals failure. `Mono<T>` emits at most one item; `Flux<T>` can emit many items. Once `onError` or `onComplete` is emitted, that subscription **terminates** and emits no further valid `onNext` signals.

~~~mermaid
sequenceDiagram
    participant Source as Publisher
    participant Op as Reactive operators
    participant Sub as Subscriber
    Sub->>Source: subscribe + request(n)
    Source-->>Op: onNext(item 1)
    Op-->>Sub: onNext(item 1)
    Source-->>Op: onError(timeout)
    alt With onErrorResume
        Op->>Op: Select fallback publisher
        Op-->>Sub: onNext(fallback) or empty
        Op-->>Sub: onComplete
    else No error handler
        Op-->>Sub: onError(timeout)
    end
~~~

| Scenario | Meaning | Appropriate handling |
|---|---|---|
| `Mono.just(value)` | One value then complete | Turn result into reply or persist data |
| `Mono.empty()` | Completes with no item | Express "not found" or "no body needed" |
| `Mono.error(ex)` | Failure terminating the chain | Classify, map, retry, or route to error flow |
| `Flux` fails after 3 items | First 3 items already emitted; subscription ends in error | Track cursor, avoid duplicate emissions on retry |
| `cancel()` | Consumer wants no more items | Clean up resources; does not roll back completed work |

**Important:** `Mono.empty()` is not `Mono.error(...)`. An inventory lookup returning "no record" should map to 404 or an appropriate domain outcome rather than being lumped together with network errors. Reactive Streams also forbids `onNext(null)`; when no data exists, use `Mono.empty()` or an explicit result object.

## 3. Error-Handling Operators: Observe, Transform, Recover

| Reactor operator | Purpose | Pitfalls to avoid |
|---|---|---|
| `doOnError(consumer)` | Record logs, metrics, or tracing when an error passes | Does not replace the error or perform recovery |
| `onErrorMap(mapper)` | Translate low-level exceptions into domain exceptions | Do not discard useful causes/context |
| `onErrorResume(ex -> publisher)` | Switch to a fallback publisher based on error | Do not swallow unexpected errors |
| `onErrorReturn(value)` | Return a pre-built fallback value | Never return a "fake success" for critical transactions |
| `onErrorComplete(...)` | Complete without error under a condition | Never use to hide payment, DB save, or broker send failures |
| `retryWhen(Retry...)` | Resubscribe upstream on matching errors | Never retry infinitely or non-idempotent POSTs |
| `timeout(Duration)` | Emit error when waiting exceeds deadline | Does not prove remote aborted/rolled back |
| `doFinally(signal)` | Cleanup/metrics on complete, error, or cancel | Do not assume it runs only on success |

Minimal example illustrating the layers:

~~~java
Mono<InventoryReply> guarded = inventoryApi.find("SKU-001")
    .doOnError(error -> log.warn("Inventory lookup failed", error))
    .onErrorMap(
        java.util.concurrent.TimeoutException.class,
        error -> new InventoryDependencyException(
            "Inventory timeout", error))
    .onErrorResume(
        InventoryDependencyException.class,
        error -> Mono.just(InventoryReply.unknown("SKU-001")));
~~~

The snippet above is **illustrative code**; `inventoryApi`, `log`, `InventoryDependencyException`, and `InventoryReply` are application types. Falling back to `unknown` is only valid if business rules **permit an unknown state**. If the system must prevent overselling inventory, never implicitly treat a dependency failure as "in stock."

## 4. Where Can Errors Arise in Spring Integration WebFlux?

| Boundary | Example failure | Commonly observed signal | Required response |
|---|---|---|---|
| Inbound WebFlux route | Invalid path, HTTP method, `Content-Type` | HTTP 404/405/415 per case | Return safe client error before message enters flow |
| Inbound decode/validation | Malformed JSON, invalid field, unauthorized | WebFlux exception or validation result | HTTP 400/401/403/422 per contract |
| `MessageChannel` | No consumer, full executor/queue | Send failure, dispatch exception | Load limits, messaging error handling |
| Reactive handler | `Mono.error`/`Flux.error` | `onError` inside publisher | Recovery, retry, or error flow |
| WebClient HTTP | Remote returns 404/429/503 | HTTP status mapped to error/value | Classify status before retrying |
| Reactor Netty | DNS, TLS, TCP, response timeout | Transport exception/cause | Network policy, timeouts, conditional retries |
| Gateway reply | No reply within deadline | `replyTimeout` / timeout error | Return proper error; do not hold HTTP request forever |
| Kafka/JMS/DB poller adapter | Redelivery, transaction, ACK/commit failure | Adapter/broker/DB error | DLQ, outbox, handle duplicate processing |
| HTTP SSE streaming | Error after emitting several events | `onError`/connection close | Committed status cannot be changed |

**Do not conflate the two error layers:** `onErrorResume` operates **inside the publisher it is attached to**; Spring Integration's `errorChannel` handles `ErrorMessage`s when the framework/endpoint routes failures into messaging. An error emitted by a publisher does not necessarily become an `ErrorMessage` unless the consuming endpoint subscribes to errors and is configured accordingly. Likewise, `send()` returning successfully does not prove asynchronous HTTP work finished.

## 5. WebClient Example: Classifying HTTP Statuses Before Returning Domain Errors

To keep the flow decoupled from `WebClientResponseException` details, map status/transport failures into meaningful domain errors. Suppose an HTTP inventory service returns `200` with JSON, `404` when a SKU does not exist, and `503` when a dependency is temporarily down.

### 5.1. DTO and Exceptions

~~~java
package com.example.integration;

public record InventoryReply(String sku, int available) {
    public static InventoryReply unknown(String sku) {
        return new InventoryReply(sku, -1); // -1 represents UNKNOWN in this example.
    }
}
~~~

~~~java
package com.example.integration;

public class InventoryNotFoundException extends RuntimeException {
    public InventoryNotFoundException(String sku) {
        super("Inventory not found for " + sku);
    }
}
~~~

~~~java
package com.example.integration;

public class InventoryDependencyException extends RuntimeException {
    public InventoryDependencyException(String message) {
        super(message);
    }
    public InventoryDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Using `-1` for `available` is solely an example representation of UNKNOWN; in production, prefer a domain model distinguishing `FOUND`, `NOT_FOUND`, and `UNKNOWN` so negative stock is never misread as actual stock.

### 5.2. Using WebClient with onStatus, Timeout, and Filtered Retry

~~~java
package com.example.integration;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class InventoryClient {

    private final WebClient client;

    public InventoryClient(@Qualifier("inventoryWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<InventoryReply> find(String sku) {
        // defer ensures each subscription/attempt creates a fresh HTTP request.
        return Mono.defer(() -> client.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .onStatus(status -> status.value() == 404,
                    response -> Mono.just(
                        new InventoryNotFoundException(sku)))
                .onStatus(HttpStatusCode::is5xxServerError,
                    response -> Mono.just(
                        new InventoryDependencyException(
                            "Inventory HTTP " + response.statusCode().value())))
                .bodyToMono(InventoryReply.class))
            .timeout(Duration.ofSeconds(2))
            .retryWhen(Retry
                .backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(this::retryable))
            .timeout(Duration.ofSeconds(6));
    }

    private boolean retryable(Throwable error) {
        return error instanceof InventoryDependencyException
            || error instanceof TimeoutException
            || error instanceof WebClientRequestException;
    }
}
~~~

With Spring Boot, configure a shared client bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryClientConfiguration {
    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:9090").build();
    }
}
~~~

**Reading the example accurately:**

1. `retrieve()` with `onStatus(...)` turns HTTP statuses into **error signals**: `404` becomes a domain not-found error, and `5xx` becomes a dependency error.
2. For `429 Too Many Requests` or other 4xx codes, `retrieve()`'s default behavior emits `WebClientResponseException`; this example does not retry those codes. To retry `429`, map/filter it explicitly and inspect `Retry-After`.
3. `bodyToMono(InventoryReply.class)` decodes the JSON body when the response is treated as successful. There is **no** validation of `sku`, authorization, or business schema yet; implement those separately.
4. `timeout(2s)` before `retryWhen` applies to **each attempt**. `timeout(6s)` after retry bounds the **entire chain** including backoff.
5. `Retry.backoff(2, ...)` allows at most two retries after the initial attempt. It runs only for errors matching `retryable`.
6. Retrying `WebClientRequestException` here assumes **read-only GET**. In production, inspect the cause: certificate/TLS trust failures or bad hostnames should not be retried repeatedly.
7. There is no `block()` or `Thread.sleep`. Errors emit asynchronously to subscribers/endpoints; this still does not guarantee downstream contains no other blocking operations.

This is intentionally illustrative code; production deployments must add transport connect/response timeouts, circuit breakers, concurrency caps, and business-appropriate fallback rules.

## 6. Fallbacks: When Is Returning a Value Better Than Emitting an Error?

A fallback adds value when the system can proceed **without falsifying results**. For instance, a dashboard may display `UNKNOWN` when the inventory API is down, whereas a payment capture flow must never assume an error means success.

~~~java
Mono<InventoryReply> displayInventory(String sku) {
    return inventoryClient.find(sku)
        .onErrorResume(
            InventoryNotFoundException.class,
            error -> Mono.just(new InventoryReply(sku, 0)))
        .onErrorResume(
            InventoryDependencyException.class,
            error -> Mono.just(InventoryReply.unknown(sku)));
}
~~~

This is a **display-only policy**: missing SKUs show `"0"`, while dependency failures show `"UNKNOWN"`. You must **clearly distinguish** both cases in UI and logs. Other errors—such as authentication, serialization, or broken configuration—continue propagating downstream.

When a workflow needs exact inventory counts to authorize funds or confirm orders, **fail closed** or transition to a `PENDING` state for later reconciliation; never write `onErrorReturn(new InventoryReply(sku, 9999))`.

### 6.1. Do Not Accidentally Swallow Errors with onErrorComplete

~~~java
// DANGEROUS for critical order persistence:
Mono<Void> ignored = saveOrder(order)
    .onErrorComplete();

// Better: let errors propagate or map to an explicit business outcome.
Mono<OrderOutcome> handled = saveOrder(order)
    .thenReturn(OrderOutcome.saved(order.id()))
    .onErrorResume(TemporaryDatabaseException.class,
        error -> Mono.just(OrderOutcome.pending(order.id())));
~~~

`saveOrder`, `OrderOutcome`, and `TemporaryDatabaseException` are application components in this snippet. `pending` is only valid if durable storage and a reprocessing mechanism actually exist, not just an in-memory status flip.

## 7. Preventing One Failed Element from Stopping an Entire Flux Unnecessarily

A stream receives multiple inventory lookup requests. Calling `flatMap(inventoryClient::find)` directly lets a failure on one SKU terminate the **entire** `Flux`. In some business flows, each SKU's result should remain independent, turning failed SKUs into explicit error outcomes.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public record LookupOutcome(
    String sku, InventoryReply reply, String errorCode) {

    public static LookupOutcome success(String sku, InventoryReply reply) {
        return new LookupOutcome(sku, reply, null);
    }

    public static LookupOutcome unavailable(String sku) {
        return new LookupOutcome(sku, null, "DEPENDENCY_UNAVAILABLE");
    }
}

Flux<LookupOutcome> results = Flux.fromIterable(skus)
    .flatMap(sku ->
        inventoryClient.find(sku)
            .map(reply -> LookupOutcome.success(sku, reply))
            .onErrorResume(
                InventoryDependencyException.class,
                error -> Mono.just(LookupOutcome.unavailable(sku))),
        8);
~~~

Here `skus` is an input `List`/`Iterable<String>`. Each inner `Mono` handles dependency failures for **that SKU alone**, preventing an anticipated transient error from aborting the whole stream. **Other** error types still terminate the outer `Flux`, by design.

If `InventoryNotFoundException` should map to `LookupOutcome.notFound`, add a separate branch; never disguise "not found" as dependency unavailable. `flatMap(..., 8)` bounds active inner publishers, yet does not preserve input order; use `concatMap` or an ordering mechanism when order matters.

**Note on nulls:** `LookupOutcome` itself is non-null (valid for Reactive Streams). Its `reply` field is nullable to represent failure in this example, though production code should prefer sealed result types or explicit status DTOs so callers never invoke `reply.available()` on `null`.

### 7.1. Why onErrorContinue Is Usually Not a Good Choice

`onErrorContinue` has operator-dependent semantics that can affect upstreams and drop errors unpredictably. For business integration flows, it is far easier to reason about **wrapping each item in `flatMap`/`concatMap` and handling errors inside the inner publisher**, as shown above. Never use `onErrorContinue` as a blanket "keep the stream running forever" switch.

## 8. Retries Do Not Block Threads, Yet Can Still Overload Systems

`retryWhen(Retry.backoff(...))` schedules retries inside Reactor instead of calling `Thread.sleep`. Nevertheless, many message sources retrying concurrently increase request volume against an already struggling dependency.

~~~java
Mono<InventoryReply> retried = inventoryClient.find("SKU-001")
    .doOnError(error -> log.warn("Final inventory error", error));
~~~

`InventoryClient.find(...)` already includes its own retry policy. Do **not** mechanically wrap another outer `retryWhen`: stacked retry layers multiply attempt counts. If the service, `IntegrationFlow`, and Kafka listener all retry, a single event can trigger far too many HTTP calls.

| Error type | Retry? | Reason |
|---|---|---|
| HTTP 400/401/403 | Usually no | Invalid data or permissions cannot be fixed by retrying |
| HTTP 404 | Per contract | May be a valid business result |
| HTTP 429 | Conditional | Backoff, honor `Retry-After`, shed load |
| HTTP 502/503/504 | Conditional | Typically transient; requires deadline and bounds |
| Timeout on order-creating POST | Only if idempotent | Remote may have executed side effects |
| JSON decode/schema error | Usually no | Data contract issue requiring a fix |
| Network reset | Per operation contract | Request may have been sent; requires idempotency |

A shipment-creation `POST` that timed out may already have been recorded by the server. Retries must reuse the exact same **idempotency key**, and the partner must **enforce** deduplication. Attaching a UUID header that the remote ignores provides zero protection.

### 8.1. Timeouts and Retries Are Two Clocks

~~~java
// Per-attempt timeout, which can trigger a retry.
Mono<InventoryReply> perAttempt = callOnce()
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));

// Overall operation timeout, covering attempts and backoff.
Mono<InventoryReply> overall = callOnce()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(6));
~~~

`callOnce()` is an application-provided **cold/repeatable** publisher. These snippets are mutually exclusive alternatives. Placing `timeout` **before** retry bounds each attempt; placing it **after** retry bounds the entire chain. When both limits are needed, place two `timeout` operators accordingly while avoiding conflicts with Reactor Netty's transport timeouts.

## 9. Error Mapping with Spring Integration WebFlux Outbound Gateway

In Spring Integration, `WebFlux.outboundGateway(...)` calls a remote service via `WebClient` and emits a **reply message** on success. Simple example:

~~~java
package com.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class InventoryGatewayFlow {

    public record InventoryRequest(String sku) {}

    @Bean
    IntegrationFlow outboundInventory(WebClient inventoryWebClient) {
        return IntegrationFlow.from("inventoryRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/inventory/query",
                    inventoryWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(InventoryReply.class))
            .channel("inventoryReplies")
            .get();
    }
}
~~~

**Important distinction:** `InventoryClient.find(...)` in Section 5 is a Java service with `onStatus`, `timeout`, and `retryWhen` policies. `WebFlux.outboundGateway(...)` here uses `WebClient` directly and **does not automatically run policies inside `InventoryClient.find(...)`**. If errors must be classified and retried via Spring Integration endpoint mechanics, design advice/error flows compatible with your running version's asynchronous handling and test them.

At an outbound gateway, when a remote returns 4xx/5xx, HTTP/network/decoding errors may surface **after** `MessageChannel.send(...)` has returned. Never equate `send() == true` with HTTP request success. Define where outcomes are observed and where error outcomes are recorded alongside the source message's correlation ID.

If only one-way HTTP sending is needed, use `WebFlux.outboundChannelAdapter(...)`; it produces no business reply message. Even so, HTTP statuses and network errors still must be managed.

## 10. ReactiveMessageHandler and Keeping Errors in the Pipeline

Spring Integration supports `ReactiveMessageHandler`, whose handle method returns `Mono<Void>`. Since Spring Integration 6.1, Java DSL provides `handleReactive(...)` to integrate asynchronous side effects without calling `block()`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import reactor.core.publisher.Mono;

@Bean
IntegrationFlow checkInventoryCommands(InventoryClient client) {
    return IntegrationFlow.from("inventoryCommands")
        .handleReactive(message -> {
            String sku = (String) message.getPayload();
            return client.find(sku)
                .doOnNext(reply -> System.out.println(
                    "Received inventory: " + reply))
                .then();
        })
        .get();
}
~~~

This example is a **one-way side-effect** branch producing no `InventoryReply` for downstream. `then()` emits only completion or error for the work, allowing the endpoint/reactive consumer to track outcome. Logging is illustrative only: production code should persist/publish via async/reactive APIs, never treating a log line as a commit receipt.

In a reactive handler, a `try/catch` wrapping `Mono` creation catches only errors **while constructing the publisher**. HTTP errors occurring **when the subscription runs** must be handled by reactive operators or endpoint error handling:

~~~java
// Wrong expectation model: catch misses errors emitted after subscription.
try {
    Mono<InventoryReply> publisher = client.find("SKU-001");
    // Does not mean the HTTP request has completed.
} catch (Exception error) {
    // Not the path for reactive onError signals.
}

// Right direction: attach error policy onto the publisher.
Mono<InventoryReply> publisher = client.find("SKU-001")
    .doOnError(error -> log.warn("Reactive operation failed", error));
~~~

When a `MessageHandler` has no reply path while an inbound gateway awaits an HTTP result, the gateway may time out; do not confuse `Mono<Void>` completion with an automatic DTO reply. For request-reply contracts, choose a gateway/handler returning a reply with clear correlation.

## 11. Spring Integration errorChannel and Errors Outside Reactor

Spring Integration provides `ErrorMessage` and `errorChannel` for messaging error handling. Depending on the endpoint and channel, errors may be thrown synchronously, routed to an error channel, or remain as `onError` signals on a publisher. Thus, **there is no single rule that "all errors go to `errorChannel`."**

| Path | Example | How to handle |
|---|---|---|
| Synchronous dispatch | `DirectChannel` consumer throws inside `send` | Caller or flow/advice handles the exception |
| Executor/poller | Worker thread runs handler and fails | Endpoint's error handler/error channel |
| Reactive pipeline | WebClient `Mono` emits `onError` after subscription | Reactor operators or reactive endpoint error handling |
| Inbound gateway | Handler produces no reply before deadline | `replyTimeout`, timeout/error mapping |
| Broker source | Kafka/JMS listener throws or redelivers | ACK/retry/DLQ per adapter and broker |

Example of an **error flow recording `ErrorMessage`s** (ensure errors from your endpoint actually route to that channel):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessagingException;

@Bean
IntegrationFlow integrationErrors() {
    return IntegrationFlow.from("errorChannel")
        .handle(message -> {
            Throwable error = (Throwable) message.getPayload();
            System.err.println("Integration error: " + error.getClass());
            if (error instanceof MessagingException me
                    && me.getFailedMessage() != null) {
                System.err.println("Failed message available for correlation");
            }
        })
        .get();
}
~~~

This configuration **illustrates an error-receiving path**, not proof that every publisher error automatically arrives here. A default `errorChannel` may already be registered by Spring Integration; verify your endpoint setup, error headers, advice, and routing. Never dump raw failed payloads or credentials into logs. For failures that cannot recover in place, persist failure state and route to dead-letter/reconciliation workflows.

**Preserving correlation:** error messages need message IDs, business event IDs, and source info for reconciliation. An HTTP failure occurring after `send` may lack a stack trace on the caller thread; design observability and context propagation deliberately.

## 12. Inbound WebFlux Gateway: Returning HTTP Errors Without Blocking Threads

An inbound gateway accepts an HTTP request, builds a Spring Integration message, and waits for a reply. For request-reply, distinguish:

- **Pre-flow errors:** invalid method, path, media type, malformed JSON, or authentication failure handled by WebFlux.
- **In-flow errors:** validation, business authorization failures, database failures, downstream `Mono.error`, or gateway `replyTimeout`.
- **Response-write errors:** client disconnected, body serialization failure, or stream failure after response headers committed.

If business rules require `404` for a missing SKU and `503` when a dependency is unavailable, define **exception/domain-outcome-to-HTTP-status mapping rules**. `onErrorResume` can turn an error into an appropriate DTO, yet **does not automatically set the HTTP status** per business semantics unless the endpoint is configured to do so.

~~~mermaid
flowchart TD
    A["HTTP request to inbound gateway"] --> B{"Valid request/codec?"}
    B -->|"No"| C["HTTP 4xx from route/validation mapping"]
    B -->|"Yes"| D["Spring Integration request message"]
    D --> E{"Downstream result"}
    E -->|"Success reply"| F["HTTP 200 + DTO"]
    E -->|"Domain not found"| G["HTTP 404 per contract"]
    E -->|"Dependency unavailable"| H["HTTP 503 per contract"]
    E -->|"No reply"| I["Configured timeout/error flow"]
~~~

`replyTimeout` limits **waiting for the reply message** per Spring Integration's contract. It is not synonymous with an outbound WebClient `responseTimeout`, nor does it necessarily bound the entire streaming duration of an SSE `Flux` already returned as the reply payload. Never assume downstream errors automatically return HTTP `503` to callers; verify with integration tests.

### 12.1. Before and After the HTTP Response Commits

| When the error occurs | What can the HTTP server do? |
|---|---|
| Before status/headers are sent | Choose a `4xx/5xx` status and sanitized error body |
| After SSE already emitted several events | Cannot change `200 OK` to `500` in the same response |
| When browser disconnects | Cancel HTTP subscription, clean up resources |
| When hot source keeps emitting after cancel | Other subscribers may continue; bound source and buffers |

If an error arises mid-SSE stream, you can close the stream or emit a contract-defined **`error` SSE event** if the socket is still writable. An `error` event does not replace HTTP status codes and is not guaranteed to reach the client if the connection already dropped.

## 13. Handling Errors per Element of an HTTP Stream

For a `Flux` from SSE or NDJSON, decide whether an error belongs to the **entire connection** or **one record**. If a single record fails validation, convert it into a status-bearing data outcome; if the source drops the connection, handle reconnect/resume at the subscription level.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<LookupOutcome> stream = incomingSkus
    .flatMap(sku ->
        inventoryClient.find(sku)
            .map(reply -> LookupOutcome.success(sku, reply))
            .onErrorResume(InventoryDependencyException.class,
                error -> Mono.just(LookupOutcome.unavailable(sku))),
        4);
~~~

`incomingSkus` is a `Flux<String>` or compatible publisher, and `LookupOutcome` is defined in Section 7. This handles errors **inside each inner publisher** so one dependency failure maps to an error outcome for that SKU without halting the rest of the stream.

Conversely, if the HTTP source itself emits `onError`, the outer stream may still terminate. Putting `retryWhen` on the outer `Flux` can resubscribe from the start and duplicate already-received events; use cursors/event IDs, deduplication, or an explicit resume protocol when completeness is required.

Never call `collectList()` on an unbounded stream just to "wait until processing finishes": it will never complete or will exhaust memory. For large streams, manage concurrency, size bounds, backpressure, and cancellation.

## 14. Logging, Metrics, Tracing, and Avoiding Event-Loop Slowdowns

`doOnError` is well suited for logging/metrics, yet its callback executes in the publisher's execution context; heavy blocking work inside `doOnError` can still stall the event loop.

~~~java
Mono<InventoryReply> observed = inventoryClient.find("SKU-001")
    .doOnError(error -> metrics.counter(
        "inventory.lookup.failed",
        "exception", error.getClass().getSimpleName()).increment())
    .doFinally(signal -> metrics.counter(
        "inventory.lookup.terminated",
        "signal", signal.name()).increment());
~~~

`metrics` is a `MeterRegistry` in a real application. Use only low-cardinality tags such as dependency name, error category, and status group; never use tokens, per-request IDs, or full query URLs as metric tags.

Metrics worth tracking:

1. **Error rates by type:** 4xx/5xx, network, TLS, codec, timeouts, validation, and internal processing.
2. **Per-stage latency:** connection pool wait, TCP/TLS, HTTP response, retry/backoff, and end-to-end processing time.
3. **Retry outcomes:** attempt counts, retries exhausted, fallbacks triggered, and `UNKNOWN` outcomes.
4. **Channel/adapter health:** queue depth, in-flight messages, poller lag, broker consumer lag, and dead-letter counts.
5. **Streaming:** active subscriptions, cancellations, event lag, dropped events, and post-commit stream errors.

With Reactor Context, trace/correlation data must propagate properly across reactive schedulers and message boundaries. Do not rely solely on a single-thread `ThreadLocal`/MDC when chains hop schedulers. If telemetry touches external async logging/metrics sinks, add queue bounds and overload rules.

## 15. Testing Non-Blocking Error Handling

### 15.1. Testing onErrorResume: Falling Back Only on Known Errors

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorFallbackTest {

    @Test
    void knownErrorUsesFallback() {
        Mono<String> result =
            Mono.<String>error(new InventoryDependencyException("down"))
                .onErrorResume(InventoryDependencyException.class,
                    error -> Mono.just("UNKNOWN"));

        StepVerifier.create(result)
            .expectNext("UNKNOWN")
            .verifyComplete();
    }

    @Test
    void unexpectedErrorStillPropagates() {
        Mono<String> result =
            Mono.<String>error(new IllegalArgumentException("bad input"))
                .onErrorResume(InventoryDependencyException.class,
                    error -> Mono.just("UNKNOWN"));

        StepVerifier.create(result)
            .expectError(IllegalArgumentException.class)
            .verify();
    }
}
~~~

The second test proves an error outside the policy **is not swallowed**. Explicitly specify expected errors per branch so dependency outages never silently return wrong data.

### 15.2. Testing Timeouts with Virtual Time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorTimeoutTest {

    @Test
    void slowPublisherFailsWithoutBlockingThread() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
~~~

`StepVerifier.withVirtualTime` tests **Reactor operator deadlines**; it does not prove Reactor Netty connect timeouts or Spring Integration's `errorChannel` routing work. To verify transport/gateways, write integration tests with a mock HTTP server controlling response statuses, delays, broken connections, and invalid bodies.

### 15.3. End-to-End Test Matrix

| Scenario | What to verify |
|---|---|
| Remote 200 valid JSON | Correct reply DTO, no error emitted |
| Remote 404 | Domain not found, no out-of-policy retry |
| Remote 429 or 503 | Bounded backoff, observe attempts; no retry storm |
| Remote continuously fails | Error propagated / routed to error flow after retries exhaust |
| Schema-invalid response JSON | Codec/decoding failure never turned into success |
| Network refused/TLS error | Cause classified, never retry trust errors endlessly |
| One SKU fails inside multi-SKU `Flux` | Only that SKU maps to error outcome; other items succeed |
| HTTP caller cancels SSE mid-stream | Subscription/cleanup and backlog handled |
| Inbound gateway receives no reply | Configured timeout, HTTP error mapping, and error channel |
| Kafka/JMS redelivery after HTTP timeout | Idempotency prevents duplicate side effects |
| Handler calls `Thread.sleep` on event loop | Blocking detected via BlockHound/tests or metrics in appropriate environments |

When using `BlockHound` in tests, integrate a Reactor/JDK-compatible version and watch for false positives; it detects blocking calls, rather than replacing code reviews, load tests, or metrics.

## 16. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| "Having `onErrorResume` means all errors are handled safely" | Errors must be classified and fallbacks must not break business contracts |
| "`doOnError` catches and suppresses the exception" | It only observes; `onError` continues propagating |
| "`try/catch` around `Mono` catches all HTTP errors" | HTTP errors can occur later upon subscription |
| "`onErrorContinue` always preserves remaining records" | Semantics depend on operators; isolate errors inside each inner publisher |
| "`retryWhen` is non-blocking so any retry count is fine" | Still consumes network, pool, and memory, risking retry storms |
| "`send() == true` proves the remote succeeded" | Confirms only channel send behavior per contract |
| "Errors inside publishers always go to Spring Integration `errorChannel`" | Depends on endpoint/subscription/error handling and configuration |
| "`Mono.empty()` is the same as `Mono.error()`" | Empty completion differs from an error signal |
| "If it timed out, the remote did not commit" | Remote may have processed it; idempotency/reconciliation are needed |
| "SSE error after two events changes status to 500" | Committed statuses cannot change mid-response |
| "`block()` simplifies error handling in WebFlux" | Can block the event loop; use reactive operators and async boundaries |

## 17. Exercises

1. Create `Mono.error(new InventoryDependencyException(...))`, chain `doOnError` and `onErrorResume`. Observe log order and downstream results.
2. Write `StepVerifier` tests for `Mono.empty()` and `Mono.error()` to distinguish empty completions from exceptions.
3. Add `onStatus` to a mock WebClient mapping `404` to `InventoryNotFoundException` and `503` to `InventoryDependencyException`. Verify `404` is not confused with a timeout.
4. Have the mock return `503` twice then `200`. Cap retries with `Retry.backoff`; measure attempt counts, latency, and error outcomes.
5. Pass multiple SKUs through `Flux.flatMap`; simulate one SKU failing. Handle the error in the inner `Mono` and verify the remaining SKUs still produce results.
6. Intentionally use `onErrorComplete()` after an order save; explain why the flow reports completion despite database failure, then replace it with a durably persisted `PENDING` outcome.
7. Connect `WebFlux.outboundGateway` to a mock API returning `503` and inspect the error flow. Demonstrate that a retry policy defined on another service does not automatically apply to the gateway.
8. Write `handleReactive(...)` calling `InventoryClient`; ensure there are no manual `block()`/`subscribe()` calls in the handler.
9. Create an inbound HTTP request-reply gateway where downstream returns no reply; observe `replyTimeout` and configure explicit `503` or `504` responses.
10. Build an SSE endpoint emitting two events then failing. Compare failures before and after headers commit; do not expect HTTP status changes mid-response.
11. Attach a correlation ID to messages and logs, trace a WebClient error across schedulers, and confirm tokens and sensitive payloads are never exposed.
12. Add a Kafka/JMS source to the flow and simulate an HTTP timeout after the remote already processed the request. Design the idempotency key, outbox/DLQ, ACK/commit, and reconciliation.

**Scenario question:** a system receives a payment command via an HTTP inbound gateway, notifies a partner via `WebClient`, writes status to a database, and publishes to Kafka. The partner recorded the notification, but the response was lost; WebClient times out, and the message may be redelivered. How do you handle the error non-blockingly without turning the payment into a false success, without creating duplicate transactions, and while still reporting a consistent `PENDING`/`UNKNOWN` status to the client?

## 18. References

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux inbound/outbound adapters, gateways, WebClient, and reply/error semantics.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer`, and `handleReactive`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, message endpoint error handling, and advice.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply timeouts, error channels, and correlation.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient, error handling, `retrieve`, and `onStatus`.
- [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `doOnError`, `onErrorResume`, `onErrorMap`, `onErrorContinue`, and retries.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and testing error signals.
- [Reactive Streams Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, `Subscription`, `onError`, and cancellation.

> **Takeaway:** **Non-blocking** error handling does not mean hiding errors. Let `Mono`/`Flux` propagate `onError` cleanly, classify HTTP/transport/domain errors, choose bounded retries/fallbacks, isolate per-element failures where appropriate, and integrate with `errorChannel` per endpoint semantics. With Spring Integration WebFlux, reliable outcomes also depend on message correlation, timeouts, idempotency, ACK/commit, and end-to-end observability.
