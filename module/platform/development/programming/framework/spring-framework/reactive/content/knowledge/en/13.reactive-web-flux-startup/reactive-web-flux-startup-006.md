# Observing Requests, Responses, and the First Signal in Spring WebFlux

## 1. Goal: observing the HTTP and Reactor lifecycles accurately

A request in Spring WebFlux passes through multiple layers: the HTTP server receives the request, WebFilters and handlers process it, the controller creates a `Mono`/`Flux`, the service may call `WebClient`, and then the response is written back to the client. Meanwhile, Reactor emits the signals `onSubscribe`, `onNext`, `onComplete`, and `onError`; the subscriber can also send `request(n)` and `cancel()`.

To diagnose properly, three perspectives must be distinguished:

1. **HTTP lifecycle**: the request arrives, a route is selected, the response status/headers are created, the body is written, and the connection ends or is disconnected.
2. **Reactor lifecycle**: the publisher is subscribed to, demand is requested, elements are emitted, and the sequence completes/errors or is cancelled.
3. **Race between multiple sources**: if multiple publishers compete to provide a result, `firstWithSignal` picks the source that emits the first signal; `firstWithValue` picks the source that emits the first value.

A log line saying "request started" does not prove the response completed. A `Mono<ClientResponse>` emitting response headers does not mean the body has been fully read either. A cancelled publisher is also not a publisher that completed successfully.

This lesson focuses on how to observe requests/responses on the server and client, how to read Reactor signals, what "first signal" means, and how to write tests to verify the behavior accurately.

## 2. Request and response path in WebFlux

The server path usually looks like this:

```text
HTTP client
    |
    v
Reactor Netty / HTTP server adapter
    |
    v
WebFilter chain
    |
    v
DispatcherHandler -> HandlerMapping -> HandlerAdapter
    |
    v
Controller -> Service -> WebClient / repository
    |
    v
Mono<T> / Flux<T>
    |
    v
HttpMessageWriter / codecs
    |
    v
HTTP response status + headers + body
    |
    v
HTTP client
```

Different observation points have different meanings:

| Observation point | What you can know | What you cannot conclude yet |
|---|---|---|
| Start of `WebFilter` | The request has entered the filter chain | Which handler will process it, final response status |
| After `chain.filter(exchange)` completes | The filter/handler pipeline has finished | Not every client is guaranteed to have received all bytes if the connection dropped at the transport layer |
| `doOnError` on the chain | An error propagated past that operator's position | The error might already have been handled by `@ExceptionHandler` before escaping |
| `doFinally` | The sequence ended with complete, error, or cancel | Cancel does not tell you that an external upstream stopped physical work immediately |
| `ExchangeFilterFunction` receiving `ClientResponse` | The client has received response metadata/status | The body may not have been read or decoded yet |
| `doFinally` after `bodyToMono` / `bodyToFlux` | The body consumption pipeline ended or was cancelled | Does not by itself prove downstream business work committed successfully |

A WebFlux request can switch across multiple threads. Thread ID is not a reliable correlation ID. Use a request log ID, trace/span ID, or correlation ID propagated through context instead of piecing logs together by thread name alone.

## 3. Reactive Streams signals and observation operators

The lifecycle of a subscription:

```text
Publisher.subscribe(subscriber)
       |
       v
onSubscribe(subscription)
       |
       +---- request(n) --------------------+
       |                                    |
       v                                    |
onNext(value) <-----------------------------+
       |
       +---- onNext(value) ... (Flux)
       |
       +---- onComplete()   success terminal
       |
       +---- onError(error) error terminal

Subscriber can cancel() before terminal.
```

Important observation operators:

| Operator | Observes | Note |
|---|---|---|
| `doFirst` | Action before upstream is subscribed | Does not mean the HTTP request has already been sent |
| `doOnSubscribe` | Subscriber receives `Subscription` | Can record the start of a subscription |
| `doOnRequest` | Demand passing the operator's position | `request(n)` is neither an HTTP request nor requests/second |
| `doOnNext` | Each element emitted | With Flux this can run multiple times |
| `doOnSuccess` | Mono completes successfully | The callback value is `null` if the Mono is empty |
| `doOnComplete` | Flux completes successfully | Mono typically uses `doOnSuccess` or `doOnEach` |
| `doOnError` | An error passing through the pipeline | Does not run on cancel alone |
| `doOnCancel` | Receives a cancel request | Not a terminal signal from the publisher |
| `doOnEach` | Receives `Signal` for onNext/onError/onComplete | Useful when one callback should observe multiple signal types |
| `doFinally` | Complete, error, or cancel | Callback runs after the terminal/cancel signal is propagated downstream |

### `doOnSuccess` differs from `doOnNext`

```java
Mono<String> value = Mono.just("OK")
        .doOnNext(v -> log.info("onNext={}", v))
        .doOnSuccess(v -> log.info("mono success={}", v));

Mono<String> empty = Mono.<String>empty()
        .doOnNext(v -> log.info("empty next={}", v))
        .doOnSuccess(v -> log.info("empty success={}", v));
```

- With `Mono.just("OK")`, both `doOnNext` and `doOnSuccess` are called with `"OK"`.
- With `Mono.empty()`, `doOnNext` does not run; `doOnSuccess` runs with `null`.
- `null` in the `doOnSuccess` callback does not mean Reactor emitted `onNext(null)`. Reactive Streams does not allow `null` as an element.

This is an illustrative snippet; `log` must be a declared logger.

### `doOnEach` to observe both values and terminal signals

```java
Mono<String> observed = remoteCall
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                log.debug("value received");
            } else if (signal.isOnComplete()) {
                log.debug("publisher completed");
            } else if (signal.isOnError()) {
                log.warn("publisher failed", signal.getThrowable());
            }
        });
```

`remoteCall` is an existing `Mono<String>`. Do not log the full value if it may contain tokens, personal data, or sensitive business content. `doOnEach` receives a `Signal` carrying Reactor's context, which is useful for instrumentation; if you only need one simple event, using a specialized operator is easier to read.

### `doFinally` to distinguish complete, error, and cancel

```java
Mono<String> observed = remoteCall
        .doFinally(signal -> log.info("exchange finished: {}", signal));
```

Common values:

- `ON_COMPLETE`: the publisher completed successfully.
- `ON_ERROR`: the publisher ended with an error.
- `CANCEL`: the subscriber requested cancellation.

`doFinally` runs after the ending signal has been propagated downstream. Therefore, when testing the callback, wait for cancellation/terminal to complete; do not assume the side effect of `doFinally` has already run before downstream sees the terminal signal.

## 4. Observing server HTTP requests with `WebFilter`

`WebFilter` is the right place to record request metadata at the WebFlux layer: method, route/path, request ID, final status, ending signal, and processing duration.

The following example is a **snippet in a Spring Boot WebFlux application**, requiring imports of `Mono`, `WebFilter`, `WebFilterChain`, `ServerWebExchange`, `HandlerMapping`, `HttpStatusCode`, `Logger`, and `LoggerFactory`:

```java
@Component
public class HttpLifecycleFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(HttpLifecycleFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();

        String method = exchange.getRequest()
                .getMethod()
                .name();

        String requestId = exchange.getLogPrefix();

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn("{} request failed: {}",
                                requestId, error.toString()))
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();

                    Object pattern = exchange.getAttribute(
                            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                    String route = pattern != null
                            ? pattern.toString()
                            : exchange.getRequest().getPath()
                                    .pathWithinApplication().value();

                    String statusText = status == null
                            ? "not-set"
                            : Integer.toString(status.value());

                    log.info(
                            "{} method={} route={} status={} signal={} durationMs={}",
                            requestId, method, route,
                            statusText, signal, elapsedMs);
                });
    }
}
```

To compile the snippet, add the imports:

```java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.reactive.HandlerMapping;
import reactor.core.publisher.Mono;
```

How to read it:

- `exchange.getLogPrefix()` provides a log prefix attached to the WebFlux request; use it to correlate log lines of the same request.
- `BEST_MATCHING_PATTERN_ATTRIBUTE` can hold a route template such as `/orders/{id}` after handler mapping runs. If absent, the example uses the actual path; in a real system consider masking IDs in the path.
- `getStatusCode()` can return `null` if the response has not had an explicit status set yet. Do not automatically conclude `null` means HTTP 200.
- `doOnError` records an error escaping the filter chain. If an exception was already handled by WebFlux via `@ExceptionHandler`, the error may not escape here; the response can still be 4xx/5xx.
- `doFinally` records `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`, distinguishing a normally finished request from a client disconnect/pipeline cancellation.
- `System.nanoTime()` is suitable for measuring durations; do not use `currentTimeMillis()` to calculate elapsed time.

The chain's `doFinally` is the point when reactive processing ends at the filter's position. For streaming responses, test on the real server/transport to confirm when the pipeline finishes relative to body writing and disconnects under the adapter in use.

## 5. Observing outbound requests/responses with a `WebClient` filter

`ExchangeFilterFunction` lets you intercept request and response metadata on the client. This is a good place to log the method, host, status, and the time to receive response headers without reading the body.

```java
ExchangeFilterFunction exchangeLogger =
        (request, next) -> {
            long startedAt = System.nanoTime();

            log.info("outbound start method={} host={}",
                    request.method(),
                    request.url().getHost());

            return next.exchange(request)
                    .doOnNext(response ->
                            log.info("outbound response status={}",
                                    response.statusCode().value()))
                    .doOnError(error ->
                            log.warn("outbound exchange failed",
                                    error))
                    .doFinally(signal -> {
                        long elapsedMs =
                                TimeUnit.NANOSECONDS.toMillis(
                                        System.nanoTime() - startedAt);

                        log.info(
                                "outbound exchange signal={} headerLatencyMs={}",
                                signal, elapsedMs);
                    });
        };

WebClient client = WebClient.builder()
        .filter(exchangeLogger)
        .build();
```

This is a snippet needing imports of `ExchangeFilterFunction`, `WebClient`, `ClientResponse`, `ClientRequest`, `Mono`, `TimeUnit`, and an appropriate logger; `ClientResponse`/`ClientRequest` do not need to be imported if their types are not declared directly.

**Important about measured time:** `next.exchange(request)` returns `Mono<ClientResponse>`. The filter receives the response when the status/headers are ready; `doFinally` in this filter usually ends after `ClientResponse` is passed downstream to the caller, **before the caller finishes consuming the response body**. Therefore name the metric clearly, such as `headerLatency`, rather than labeling it full body latency.

If you want to measure the time to read and decode the body, instrument the publisher after `bodyToMono`, `bodyToFlux`, or `toEntity`:

```java
Mono<ResponseEntity<String>> result = client.get()
        .uri("/status")
        .retrieve()
        .toEntity(String.class)
        .doOnNext(entity ->
                log.info("body received status={}",
                        entity.getStatusCode().value()))
        .doOnError(error ->
                log.warn("body processing failed", error))
        .doFinally(signal ->
                log.info("body pipeline ended: {}", signal));
```

This snippet consumes the entire body into a `String`; do not use that approach for large streaming responses or SSE unless intentionally buffering the whole body.

### Do not read the body arbitrarily inside a filter

`ClientResponse` body is a single-consumption stream. If a filter calls `bodyToMono(String.class)` itself just to log and then passes the original response downstream, downstream may have no body left to read. If a filter processes the response body, it must consume, release, or recreate the body properly. Buffering the entire body also increases heap usage and can cause errors with large payloads.

Prefer logging status, method, host, route template, request ID, elapsed time, and body size if a safe metric exists. Implement body logging only with bounded decorators/buffering, verify `DataBuffer` release, mask secrets, and have a separate policy for streaming.

## 6. Observing response status and HTTP errors

`WebClient.retrieve()` by default converts 4xx/5xx statuses into a `WebClientResponseException` error unless handled with `onStatus`. Therefore there are two kinds of situations:

1. **An HTTP response arrived** with a 4xx/5xx status: the filter can see the response status; afterward `retrieve()` may turn it into an error in the body pipeline.
2. **No HTTP response**: DNS/connect/timeout/TLS/network failure; the filter may receive `onError` before there is a `ClientResponse`, so there is no HTTP status to log.

Example of handling status explicitly:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException())
        .bodyToMono(Order.class)
        .doOnError(WebClientResponseException.class,
                error -> log.warn("HTTP status={} request failed",
                        error.getStatusCode().value()));
```

This is a snippet needing `id`, `Order`, `client`, and a logger. `createException()` creates an exception containing response information; avoid logging the entire response body if it contains sensitive data.

If you need different decoding decisions depending on status, use `exchangeToMono`/`exchangeToFlux`:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Order.class);
            }
            return response.createError();
        });
```

When using `exchangeToMono`, the callback must decide how to consume the body. Spring checks and releases the body if it is not consumed; you cannot decode the body again after leaving the callback. This is why you should not write a filter that observes status and ignores body management.

## 7. "First signal": `firstWithSignal` and `firstWithValue`

When two or more publishers compete to provide a result, Reactor has two easily confused operators:

- **`Mono.firstWithSignal(a, b)`**: picks the source that emits **any first signal**: `onNext`, empty `onComplete`, or `onError`.
- **`Mono.firstWithValue(a, b)`**: picks the source that emits the **first `onNext` value**. A source that completes empty or errors does not win if another source can still emit a value.

Both operators subscribe to the competing sources and cancel the remaining sources once a winner is chosen. Cancellation happens at the Reactor layer; the HTTP client/driver may try to cancel I/O, but the remote server may already have received and continued processing the request.

### Example timeline

```text
Time:            0 ms       10 ms          20 ms           80 ms
Primary:         subscribe  empty/error ------------------->
Backup:          subscribe  ---------------- value -------->
firstWithSignal:             empty/error wins immediately
firstWithValue:                           backup value wins
```

For example: primary returns `Mono.empty()` after 10 ms, backup returns `"backup"` after 20 ms:

- `firstWithSignal` finishes empty at 10 ms; backup is cancelled.
- `firstWithValue` keeps waiting because primary had no value; backup emits `"backup"` at 20 ms and wins.

This is an important distinction for fallback APIs: **a fast empty/error is not necessarily a useful result**.

### Example of picking the first response

```java
Mono<Quote> fastestSignal = Mono.firstWithSignal(
        primaryClient.getQuote(symbol),
        backupClient.getQuote(symbol)
);

Mono<Quote> fastestValue = Mono.firstWithValue(
        primaryClient.getQuote(symbol),
        backupClient.getQuote(symbol)
);
```

`primaryClient` and `backupClient` are already-configured clients/services. Use this race only when both sources can run concurrently and the operation is safe if one branch is cancelled. Do not race POST requests that create payments/orders without an idempotency key and mechanisms against duplicate side effects.

### Error handling when no source has a value

With `firstWithValue`, if no publisher emits `onNext` (all are empty/error), the operator emits `NoSuchElementException` with aggregated error details in the cause. If you need detailed error classification, look at `Exceptions.unwrapMultiple(...)` according to the Reactor API of the version in use.

Another policy is normalizing each source before racing:

```java
Mono<Quote> primaryValue = primaryClient.getQuote(symbol)
        .onErrorResume(error -> Mono.empty());

Mono<Quote> backupValue = backupClient.getQuote(symbol)
        .onErrorResume(error -> Mono.empty());

Mono<Quote> quote = Mono.firstWithValue(
        primaryValue,
        backupValue);
```

This is only an example when business rules allow treating each source's error as "no value" to try another source. Do not turn every error into empty if you need to distinguish authentication errors, data errors, quota, or system incidents.

### `Flux.firstWithSignal`

For `Flux`, `Flux.firstWithSignal(...)` picks the publisher that emits any first signal and then forwards the sequence from the winning publisher. It **does not merge** elements from the sources and does not sort by global time. If the goal is to combine all events, use `merge`; if you only pick one winning source, use `firstWithSignal`.

## 8. Observing signals in a race

You can attach `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnCancel`, and `doFinally` to each branch to see which branch wins and which branch is cancelled:

```java
Mono<String> primary = primaryCall()
        .doOnSubscribe(s -> log.debug("primary subscribed"))
        .doOnNext(v -> log.debug("primary produced value"))
        .doOnError(e -> log.warn("primary failed", e))
        .doOnCancel(() -> log.debug("primary cancelled"))
        .doFinally(s -> log.debug("primary final={}", s));

Mono<String> backup = backupCall()
        .doOnSubscribe(s -> log.debug("backup subscribed"))
        .doOnNext(v -> log.debug("backup produced value"))
        .doOnError(e -> log.warn("backup failed", e))
        .doOnCancel(() -> log.debug("backup cancelled"))
        .doFinally(s -> log.debug("backup final={}", s));

Mono<String> winner = Mono.firstWithValue(primary, backup);
```

This is a snippet needing `primaryCall()`/`backupCall()` returning `Mono<String>`. When one branch wins, the other branch typically observes `CANCEL`; if the other branch already terminated earlier, it cannot be cancelled again. Do not log data contents unless necessary.

Use branch-level logs along with a correlation ID to answer:

- Were both requests actually subscribed?
- Which branch emitted a value first?
- Which branch returned empty/error first?
- Did the losing branch receive cancellation?
- How much does the time from subscribe to response headers differ from the body reading time?

## 9. Observation, metrics, and tracing

Manual logs help investigate individual requests but do not replace metrics/tracing. In a Spring application, prefer **Micrometer Observation** and tracing to have unified telemetry across the HTTP server, WebClient, and services.

### Enabling Observation for WebClient

`WebClient.Builder` supports `observationRegistry(...)`:

```java
@Bean
WebClient webClient(
        WebClient.Builder builder,
        ObservationRegistry observationRegistry) {

    return builder
            .observationRegistry(observationRegistry)
            .build();
}
```

This is a Spring configuration snippet requiring the import of `ObservationRegistry` from Micrometer. In Spring Boot, the auto-configured builder may already have the registry attached when appropriate Actuator/observability dependencies are present; check the actual configuration before attaching it again.

Client observation can measure the entire HTTP exchange from connection setup to body reading/deserialization, unlike a simple `ExchangeFilterFunction` that only measures up to when response metadata is emitted downstream. Specific observation/metric names and tags may vary by Spring/Micrometer convention version.

### Server-side metrics

Spring Boot Actuator can auto-configure HTTP server observations/metrics for WebFlux applications when suitable dependencies and registries are present. Use metrics to view latency distributions, request counts, status/outcome, and errors; use tracing to link one request across multiple outbound calls.

Do not hard-code unverified metric names or tags. Spring Boot version, Micrometer conventions, OpenTelemetry bridges, and exporters can affect names and tag sets. Avoid high-cardinality tags such as user ID, email, full URL with query string, order ID, or correlation ID; those values belong in logs/traces rather than metric labels.

### Correlation ID and Reactor Context

A request can switch threads; `ThreadLocal` is not a safe way to propagate context manually across an entire reactive pipeline. Use Observation/Tracing propagation mechanisms or Reactor Context suitable for your Spring/Micrometer version.

Do not put tokens, secret session IDs, or PII into baggage/tags/logs. If accepting a correlation ID from the client, validate length/characters and prevent clients from crafting values that can cause log injection.

## 10. Security and reliability when observing HTTP

Observing requests/responses can accidentally become a data leak path. Apply minimum principles:

- Log method, route template, status, elapsed time, request ID, and error category before considering the body.
- Do not log `Authorization`, `Cookie`, access tokens, API keys, passwords, or all headers.
- Avoid logging query strings containing email, phone, search text, or identifying information.
- Do not log request/response bodies by default. If debugging requires it, enable it only temporarily, limit size, mask sensitive fields, and control log access permissions.
- Do not buffer streaming bodies unboundedly for logging.
- When wrapping `DataBuffer`, manage retain/release properly; if you read the body in a filter without re-emitting it, downstream may get an empty body or connection leaks.
- Avoid logging the same stack trace at multiple layers for the same error; pick one place for full logging and attach correlation ID and error category at other layers.
- Distinguish errors handled into a 4xx/5xx response from errors escaping the pipeline. Do not rely solely on `doOnError` to count all HTTP error statuses.

### Distinguishing HTTP status and Reactor terminal signals

| HTTP response | Observable Reactor signal | Meaning |
|---|---|---|
| 200 with body | `onNext`, then `onComplete` | Body emitted, then sequence completed |
| 204/no content | `onComplete` with no value in body publisher | Success without a body |
| 404 from `retrieve()` | `onError(WebClientResponseException)` | HTTP response had status 404, but WebClient turned it into an error |
| 500 handled by `onStatus`/`onErrorResume` | Possibly `onError`, then converted into fallback `onNext`/complete | Original error was transformed |
| Client disconnect | `cancel` on some publisher/response pipeline | Subscriber no longer receives; server/remote cancellation depends on transport |
| DNS/connect timeout | `onError` with no HTTP status | No HTTP response from upstream |

An HTTP 404 is not `SignalType.ON_ERROR` at every layer. If you use `exchangeToMono` and handle the status into a value yourself, the pipeline can complete successfully. Conversely, `retrieve()` by default turns error statuses into exceptions. You must observe the exact layer being instrumented.

## 11. Runnable Java 17+ program: testing `firstWithSignal` and `firstWithValue`

The example below uses Reactor Core 3.6.6, JUnit Jupiter, and `reactor-test`. This is a standalone Java project for testing signals; it does not need to start Spring Boot or make real network calls.

Structure:

```text
reactor-first-signal-demo/
├── pom.xml
└── src/test/java/edu/demo/FirstSignalTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-first-signal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/test/java/edu/demo/FirstSignalTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FirstSignalTest {

    @Test
    void firstWithSignalAllowsEmptyToWin() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithSignal(
                        Mono.<String>empty()
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(50))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(60))
                .verifyComplete();
    }

    @Test
    void firstWithValueWaitsForAnActualValue() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithValue(
                        Mono.<String>empty()
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(20))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(30))
                .expectNext("backup")
                .verifyComplete();
    }

    @Test
    void firstWithValueCanIgnoreAnEarlyErrorIfAnotherSourceProducesValue() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithValue(
                        Mono.<String>error(
                                new IllegalStateException("primary failed"))
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(20))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(30))
                .expectNext("backup")
                .verifyComplete();
    }

    @Test
    void firstWithSignalPropagatesTheFirstError() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithSignal(
                        Mono.<String>error(
                                new IllegalArgumentException("bad primary"))
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(50))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(20))
                .expectErrorMessage("bad primary")
                .verify();
    }

    @Test
    void doFinallyDistinguishesCancellation() {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        StepVerifier.create(
                        Mono.<String>never()
                                .doFinally(finalSignal::set))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected result when dependencies download successfully and assertions pass: **5 tests PASS** (`Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`). The tests do not need to wait on real clock time; `withVirtualTime` creates a virtual scheduler before the supplier builds the timed pipeline.

Meaning of each test:

1. `firstWithSignalAllowsEmptyToWin`: empty `onComplete` at 10 ms is the first signal; backup is cancelled and the result completes with no value.
2. `firstWithValueWaitsForAnActualValue`: empty does not win; backup emits a value at 20 ms.
3. `firstWithValueCanIgnoreAnEarlyErrorIfAnotherSourceProducesValue`: primary's error does not win if backup later produces a value.
4. `firstWithSignalPropagatesTheFirstError`: the first `onError` wins and is propagated downstream.
5. `doFinallyDistinguishesCancellation`: the subscriber cancels `Mono.never()`, and the callback sees `SignalType.CANCEL`.

These are operator semantic tests with Reactor Core; they are not integration tests measuring real HTTP timing, TLS, connection pooling, body decoding, or server behavior when a request is cancelled.

## 12. Checklist for adding observability to an application

Before enabling instrumentation in production, check:

1. Is there a consistent request ID/trace ID across the server and outbound clients?
2. Do server logs include method, route template, status, signal, and latency?
3. Do client logs distinguish time to response headers from time to read/decode the body?
4. Does `doFinally` distinguish `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`?
5. Are HTTP 4xx/5xx recorded even when WebClient converts them into errors/fallbacks?
6. Are connect/DNS/timeout errors distinguished from HTTP response statuses?
7. Are sensitive bodies and headers masked?
8. Does any filter accidentally consume the body, buffer unboundedly, or lose a `DataBuffer`?
9. Does a publisher race cancel the losing branch? Do upstream tasks support cancellation?
10. Can `firstWithSignal` let a fast empty/error win unintentionally? Is `firstWithValue` needed instead?
11. Are metric tags low-cardinality? Are user ID, request ID, full URL, and query string avoided as labels?
12. Are there tests for complete, error, cancel, empty, response status, and body consumption?
13. Are errors already handled by a handler distinguished from exceptions actually escaping `WebFilter`?
14. Are there sampling/log-volume limits to avoid a log firehose when a stream emits many elements?

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating `doFinally(ON_COMPLETE)` as proof the client received the full response | Overestimating delivery state | Distinguish pipeline terminal from client/transport-layer confirmation |
| Using only `doOnError` to count HTTP 500s | Missing response statuses already handled into fallbacks | Record status in a response filter/Observation and record error signals separately |
| Measuring latency inside `ExchangeFilterFunction` and calling it body latency | Metrics underreport body consumption time | Instrument the publisher after `bodyToMono`/`bodyToFlux` or use Observation |
| Calling `bodyToMono` in a filter to log then returning the old response | Downstream loses the body or buffers are not released | Do not read the body in a filter unless there is a proper consume/rebuild mechanism |
| Logging full URL/query/headers/body | Leaking tokens, PII, and business data | Mask, use route templates, log minimal metadata |
| Using thread ID as correlation ID | Logs lose correlation when the pipeline switches threads | Use request ID, trace/span, and Reactor Context |
| Mistaking `doOnSuccess(null)` for `onNext(null)` | Misunderstanding empty Mono | Remember empty Mono calls the success callback with null without emitting an element |
| Using `firstWithSignal` for a fallback that needs a value | Fast empty/error can win | Use `firstWithValue` or normalize errors/empty per business rules |
| Using `firstWithValue` without handling the case where all sources error/empty | Getting an aggregated `NoSuchElementException` | Define an error policy when no source emits a value |
| Racing non-idempotent POSTs | Multiple requests create duplicate side effects | Do not race or use real idempotency/deduplication |
| Assuming cancel guarantees the remote server stops processing | Remote work may continue | Design timeouts/idempotency and verify driver/server cancellation |
| Putting request ID or user ID as metric labels | Cardinality explosion | Keep IDs in logs/traces; use bounded tags for metrics |

## 14. Self-check exercises

**Exercise 1.** A WebFilter sees `chain.filter(exchange)` emit `onError`. Can you conclude no HTTP response exists?

**Answer:** No. Depending on where errors are handled, the exception may already have been converted into a response at another layer; observe status and error propagation at the right layer.

**Exercise 2.** `ExchangeFilterFunction` logged status 200. Can you conclude the body decoded successfully?

**Answer:** No. The filter receives `ClientResponse` when response metadata is ready; decoding/body consumption can fail afterward.

**Exercise 3.** What does `Mono.firstWithSignal(Mono.empty(), slowValue)` return if empty emits first?

**Answer:** Empty completion. `firstWithSignal` picks any first signal, including `onComplete` with no value.

**Exercise 4.** What does `Mono.firstWithValue(Mono.error(e), slowValue)` return if `slowValue` later emits a value?

**Answer:** The value from `slowValue`. An early error does not win if another source can still emit a value; if no source emits a value, the operator ends with an aggregated error.

**Exercise 5.** Why shouldn't you log the body by calling `response.bodyToMono(String.class)` in a filter and still returning the response to the controller?

**Answer:** The body is a single-consumption stream. The filter already consumed the body; downstream cannot read it again without buffering/rebuilding and proper buffer management.

**Exercise 6.** Does `doFinally` receiving `CANCEL` mean the server definitely stopped all remote work?

**Answer:** No. That is cancellation at the observed subscription; physical work on the driver/server side depends on cancellation support.

**Exercise 7.** If you want to pick the API that returns a value fastest, but the primary API can complete empty very quickly, which operator should you use?

**Answer:** `Mono.firstWithValue`, if business semantics allow waiting for another source; `firstWithSignal` would let empty win.

**Exercise 8.** Should correlation ID be put into a Micrometer metric tag?

**Answer:** No, if the ID has a nearly unique value per request. Use the ID in logs/traces; metric tags should have low cardinality.

## 15. Key takeaways

- **HTTP request/response** and **Reactor signals** are two related but non-identical observation layers.
- `WebFilter` suits observing server requests; `ExchangeFilterFunction` suits observing outbound request/response metadata.
- Measuring response headers differs from measuring body consumption time. Place instrumentation at the right point.
- `doOnEach` observes value/error/complete; `doFinally` distinguishes complete/error/cancel.
- **`firstWithSignal`** picks any first signal; **`firstWithValue`** picks the first value. Empty/error can win in the first operator, but not in the second if another source emits a value.
- Cancellation is a request to cancel, not proof that physical work has stopped.
- Prefer Micrometer Observation/tracing for overall observability; manual logging only supplements information that is truly needed.
- Do not read bodies arbitrarily, do not log sensitive data, and do not create high-cardinality metric tags.

When investigating a request, trace in order: **request enters server → handler creates publisher → outbound response metadata → body is consumed → terminal signal or cancellation**. With multiple competing sources, clearly determine whether the system wants to pick the first signal or the first value.

## Official documentation

- Spring Framework, **WebFlux – Reactive Core and Logging**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework, **WebClient Filters (`ExchangeFilterFunction`)**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
- Spring Framework, **WebClient Configuration and ObservationRegistry**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework, **WebClient Exchange and Response Body Handling**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework, **Observability Support**: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Project Reactor 3.6.6, **Mono API (`firstWithSignal`, `firstWithValue`, `doOnEach`, `doFinally`)**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html
- Project Reactor 3.6.6, **Flux API (`firstWithSignal`, `firstWithValue`)**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor 3.6.6, **Testing with StepVerifier and virtual time**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html