# Reactor Context, Propagating Correlation IDs, and Cancelling In-Flight Requests in WebClient

## 1. Problem Statement and Execution Model

A Spring WebFlux application often receives an HTTP request and then uses `WebClient` to call one or more downstream services. When diagnosing failures, we need to link logs and HTTP calls belonging to the same original request via a **correlation ID**. If the caller no longer needs the result, we also want to stop ongoing work to avoid wasting resources.

Two mechanisms solve two different problems:

- **Reactor Context:** carries small, thread-independent data attached to a `Mono`/`Flux` subscription.
- **Cancellation:** a subscriber sends a `cancel` signal upstream; the HTTP client may stop receiving/sending the in-progress exchange depending on the connector and timing.
- **HTTP headers:** if remote services must see the correlation ID, you must explicitly copy the ID from Context into an outbound request header. Reactor Context does not cross the network by itself.

Architectural example:

```text
HTTP client
   |
   v
WebFlux server A: WebFilter reads/creates correlation ID
   |
   +-- chain.filter(exchange).contextWrite(c -> c.put(KEY, id))
   |
   v
A: service -> business Mono/Flux
   |                         |
   +--> WebClient -> B       +--> flatMap -> WebClient -> C
         |                                 |
         v                                 v
   filter reads Context               filter reads Context
         |                                 |
         v                                 v
   Header X-Correlation-ID           Header X-Correlation-ID
   |
   v
Result / error / cancellation returns to A's subscriber
```

**Distinguish carefully:** a correlation ID groups events belonging to one unit of work; a trace ID/span ID from a distributed tracing system also models parent-child relationships between steps. A correlation ID does not authenticate identity, does not make operations atomic, and does not itself control request lifecycles on remote servers.

Lesson goals: understand Context propagation direction, how to read/write Context in WebClient, propagation across `flatMap`, creating headers safely, understanding cancellation and timeout semantics, and testing behavior without a real network.

## 2. What Is Reactor Context?

Project Reactor's `Context` is an immutable key/value map by API semantics: `put` produces a new Context without mutating the old one. `ContextView` is the read-only interface. Data is bound to the **subscriber** and flows across reactive operators that support Context; it is not tied by default to any particular thread.

| Mechanism | Where data lives | Scope |
| --- | --- | --- |
| `Reactor Context` | Context of a `Mono`/`Flux` subscription | Operators/publishers in the same reactive chain, including properly composed nested publishers |
| `ClientRequest.attribute(...)` | Internal attribute of one WebClient request | Filters of **that request only**; does not carry over to another request |
| HTTP header | Data sent over the network | Readable by the receiving service |
| `ThreadLocal` | Variable bound to the current thread | Unreliable for representing a reactive request that may hop threads |
| Logger MDC | Typically thread-bound state | Propagating with Reactor Context requires version-matched propagation integration |

Each subscription can receive its own Context. For instance, the same `Mono` reads two different values when subscribed to twice:

**File `ContextBasics.java` (runs with Java 17+ and Reactor on the classpath):**

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextBasics {
    static final String KEY = "correlationId";

    public static void main(String[] args) {
        Mono<String> work = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just("id=" + id);
        });

        System.out.println(work
                .contextWrite(Context.of(KEY, "request-A"))
                .block());

        System.out.println(work
                .contextWrite(Context.of(KEY, "request-B"))
                .block());
    }
}
```

**Stdout:**

```text
id=request-A
id=request-B
```

`Mono.deferContextual` reads Context **at subscription time**, rather than reading a global mutable variable during pipeline assembly. `Context.of(KEY, value)` supplies Context for a subscription; `contextWrite(c -> c.put(KEY, value))` updates an existing Context.

### 2.1 Why Is contextWrite Placed Toward the End?

Normal data flows from source to subscriber; Context flows from the subscriber **upward to upstream** during subscription.

```java
Mono<String> example =
        Mono.deferContextual(view ->
                Mono.just(view.getOrDefault("label", "absent")))
            .map(String::toUpperCase)
            .contextWrite(ctx -> ctx.put("label", "visible"));

System.out.println(example.block()); // VISIBLE
```

Although `contextWrite` appears after `deferContextual`, upstream still sees `label`. A `contextWrite` placed mid-chain affects only the upstream segment within that scope; it does not create a "new global variable" for all publishers and does not send HTTP by itself.

Distinguish three phases:

1. **Assembly:** constructing objects describing operations, e.g., `client.get().retrieve().bodyToMono(...)`.
2. **Subscription:** the WebFlux runtime, `subscribe()`, or `block()` subscribes to the publisher; here Context flows, filters can run, and HTTP executes.
3. **Signals:** data, errors, completion, or `cancel` travel through the pipeline.

`block()` in the `main` example is only for synchronous demonstration. Never call `block()` on a WebFlux event loop.

### 2.2 Context Keys, Types, and Values

You can use a fixed string key (`"correlationId"`) or a class/module-scoped key to avoid collisions. A filter can call `view.get(KEY)` if the key is guaranteed present, or `view.getOrDefault(KEY, fallback)` to operate safely when missing. The return type must match the stored value type.

Store short ID strings, immutable objects, or small metadata; avoid putting bodies, streams, passwords, mutable request/session objects, or large payloads into Context. Never use a correlation ID as proof of login or authorization.

## 3. Passing Context to WebClient with ExchangeFilterFunction

To send the ID externally, a `WebClient` filter must read Context and **build a new request** carrying the HTTP header.

**File `CorrelationFilter.java`:**

```java
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public final class CorrelationFilter {
    public static final String KEY = "correlationId";
    public static final String HEADER = "X-Correlation-ID";

    private CorrelationFilter() {}

    public static ExchangeFilterFunction create() {
        return (request, next) -> Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "");

            if (id.isBlank()) {
                return next.exchange(request);
            }

            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> headers.set(HEADER, id))
                    .build();

            return next.exchange(updated);
        });
    }
}
```

The filter returns `Mono<ClientResponse>`; `next.exchange(request)` forwards to the next filter or HTTP transport. `ClientRequest.from(request)` preserves other properties and lets you edit headers on the new request. `headers.set` replaces any existing value of that header. In this example, **the ID from Context takes precedence** over any header set earlier on the request; if per-request headers should win instead, alter that policy explicitly.

**Do not read Context once when building the client:** `WebClient` is typically reused across many concurrent requests. Placing `Mono.deferContextual` inside the filter ensures each subscription reads its own data.

### 3.1 Registering the Filter on the Builder

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    WebClient inventoryClient(WebClient.Builder sharedBuilder) {
        return sharedBuilder.clone()
                .baseUrl("https://inventory.example")
                .filter(CorrelationFilter.create())
                .build();
    }
}
```

This is a sample configuration in Spring Boot with a provided `WebClient.Builder`; plain Spring Framework can create `WebClient.builder()` or declare a builder bean itself. The illustrative URL must be replaced with your real service config. `clone()` prevents adding filters or changing `baseUrl` from accidentally affecting other clients sharing that builder.

In a service, simply return `Mono`/`Flux` to the caller:

```java
Mono<String> response = inventoryClient.get()
        .uri("/stock/{sku}", "SKU-7")
        .retrieve()
        .bodyToMono(String.class)
        .contextWrite(ctx ->
                ctx.put(CorrelationFilter.KEY, "request-A"));
```

This snippet assumes `inventoryClient` is injected and the API returns a String body; it is not a complete Java program. Upon subscription, the filter adds `X-Correlation-ID: request-A` to the outbound HTTP request.

### 3.2 Why Do Nested Requests Still Receive the Same ID?

```java
Mono<String> workflow =
        inventoryClient.get()
                .uri("/items/{sku}", "SKU-7")
                .retrieve().bodyToMono(String.class)
                .flatMap(item ->
                        inventoryClient.get()
                                .uri("/stock/{sku}", "SKU-7")
                                .retrieve().bodyToMono(String.class))
                .contextWrite(ctx ->
                        ctx.put(CorrelationFilter.KEY, "request-A"));
```

Both HTTP requests in the chain see `request-A`, because `flatMap` subscribes to the inner publisher using the outer reactive chain's context. This is the classic case where Reactor Context beats request attributes. `ClientRequest.attribute` belongs only to a single request and never carries forward to the next request.

Do not do the following in a controller/service:

```java
// Illustrative anti-pattern inside a method:
inventoryClient.get().uri("/items/SKU-7")
        .retrieve().bodyToMono(String.class)
        .subscribe(); // Starts a subscription detached from the caller's pipeline.
return Mono.just("started");
```

Manual `subscribe()` loses caller control over errors, Context, deadlines, and cancellation. Generally **return the publisher** or compose with `flatMap`/`then` instead of launching detached tasks.

### 3.3 Safe ID Propagation

A correlation ID is operational metadata, not an authentication token. Accept only characters safe for HTTP headers, bound length (for example allowing letters, digits, dots, underscores, and hyphens, up to 64 characters), and disallow CR/LF.

An externally supplied ID can be spoofed. In systems with trust boundaries, always mint a new ID at the ingress edge or trust only authenticated gateways; **regex only checks format**. Never forward headers carrying IDs or credentials to untrusted hosts without an explicit policy. For projects already using OpenTelemetry or Micrometer Tracing, prefer standard trace propagation such as `traceparent` for full span relationships; a custom correlation ID is merely a supplementary layer.

## 4. Putting Inbound IDs into the WebFlux Server Context

`WebFilter` runs on the **server inbound** side; `ExchangeFilterFunction` runs on the **client outbound** side. A `WebFilter` can read or generate an ID and place it into Reactor Context for downstream WebClient calls to use:

**File `IncomingCorrelationWebFilter.java`:**

```java
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class IncomingCorrelationWebFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String KEY = "correlationId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String incoming = exchange.getRequest()
                .getHeaders().getFirst(HEADER);

        String id = incoming != null && SAFE.matcher(incoming).matches()
                ? incoming : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(KEY, id));
    }
}
```

The application needs Spring WebFlux enabled and component scanning for this class. `contextWrite` wraps the chain returned by `chain.filter(exchange)` so components upstream in the chain can read `id`. The response header here is set before the response commits; callers see the ID for the current execution if the response passes back through the filter.

If inbound IDs are untrusted, **replace the incoming-acceptance branch with always generating a fresh ID** per system policy. Standardize creation, forwarding, and replacement points across multi-service architectures so logs for the same work stay connected.

Example reading context in the business layer:

```java
Mono<Void> auditedWork = Mono.deferContextual(view -> {
    String id = view.getOrDefault("correlationId", "missing");
    System.out.println("processing id=" + id);
    return Mono.empty();
});
```

This is an illustrative snippet; in production use a configured logger, logging only sanitized ID/method/status/paths. SLF4J `MDC` is normally thread-bound and does not automatically stay in sync with Reactor Context across every operator/scheduler. To populate MDC, use context propagation/observability integration matched to your Spring, Reactor, and Micrometer versions, and verify behavior across thread switches.

## 5. Complete Example: Two WebClient Calls Sharing Context

The program below uses a fake `ExchangeFunction` to generate HTTP responses in memory; **it makes no network connections**. A `flatMap` chain sends two simulated requests reading the same ID; at the end it cancels an incomplete `Mono`.

**File `ContextCancelDemo.java` (Java 17+, Spring WebFlux and Reactor):**

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextCancelDemo {
    private static final String KEY = "correlationId";
    private static final String HEADER = "X-Correlation-ID";

    public static void main(String[] args) {
        ExchangeFunction fakeTransport = request -> {
            System.out.println("fake HTTP " + request.method()
                    + " " + request.url().getPath()
                    + " id=" + request.headers().getFirst(HEADER));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("ok")
                    .build());
        };

        ExchangeFilterFunction correlation =
                (request, next) -> Mono.deferContextual(view -> {
                    String id = view.getOrDefault(KEY, "missing");
                    ClientRequest newRequest = ClientRequest.from(request)
                            .headers(h -> h.set(HEADER, id))
                            .build();
                    return next.exchange(newRequest);
                });

        WebClient client = WebClient.builder()
                .baseUrl("https://example.invalid")
                .exchangeFunction(fakeTransport)
                .filter(correlation)
                .build();

        String result = client.get()
                .uri("/first")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("/second")
                        .retrieve()
                        .bodyToMono(String.class))
                .contextWrite(Context.of(KEY, "request-42"))
                .block();

        System.out.println("response=" + result);

        AtomicBoolean cancelled = new AtomicBoolean();
        Disposable subscription = Mono.<String>never()
                .doOnCancel(() -> {
                    cancelled.set(true);
                    System.out.println("upstream cancel observed");
                })
                .subscribe();

        subscription.dispose();
        System.out.println("cancelled=" + cancelled.get());
    }
}
```

**Stdout:**

```text
fake HTTP GET /first id=request-42
fake HTTP GET /second id=request-42
response=ok
upstream cancel observed
cancelled=true
```

Each simulated request simply prints the header and returns an `ok` body. Once `block()` subscribes to the chain, the filter reads `request-42` from the subscription; `flatMap` preserves context for the second call. `Mono.never()` neither emits nor completes; `dispose()` signals cancellation, triggering `doOnCancel`. That demonstrates **Reactor cancellation signals**, not a remote HTTP server stopping execution.

To run it, place the class in a Spring Boot 3.x project with Java 17+ and dependencies (e.g., Gradle):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Run `main` from an IDE using the Gradle classpath, or supply all Spring/Reactor JARs on the classpath to `javac`/`java`. You cannot run `javac ContextCancelDemo.java` in an empty folder because `org.springframework.*` and `reactor.*` are not part of the JDK. `block()` in `main` is for synchronous experimentation; never place it inside request-handling code on the WebFlux event loop.

## 6. What Does Cancelling an In-Flight Request Actually Mean?

Reactive Streams allows subscribers to send `cancel` via `Subscription.cancel()`. In Reactor, `subscribe()` typically returns a `Disposable`; calling `dispose()` requests stopping the subscription.

```text
Caller / WebFlux runtime
         |
         | cancel
         v
bodyToMono() or bodyToFlux()
         |
         v
retrieve() / WebClient exchange
         |
         v
Client HTTP connector / network
         |
         v
Remote server (may already have received and processed request)
```

Example where a component owns a subscription and cancels it:

```java
Disposable running = client.get()
        .uri("/long-running")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(kind -> System.out.println("finished=" + kind))
        .subscribe(
                body -> System.out.println("body=" + body),
                error -> System.err.println(error.getMessage())
        );

// When the caller cancels the task:
running.dispose();
```

This is an illustrative snippet in a component authorized to hold `running`. In a WebFlux controller, normally **return `Mono` to the framework** so the runtime owns and manages the subscription; do not manually subscribe and detach work from the request.

Important limitations:

1. A cancel signal is only a **reactive-protocol cancellation request**. If the HTTP request has already left the client, the remote server may still be running or may have already written data.
2. The HTTP connector may stop reading the body, abort the exchange/close the connection, or free resources depending on timing, yet it cannot guarantee rolling back server-side side effects.
3. Payment, order-creation, or write APIs require idempotency keys/status queries to resolve ambiguous outcomes, especially when callers time out and retry.
4. Blocking calls or external libraries that do not support cancellation may keep running after the reactive subscriber cancels.
5. A hot/shared publisher (`cache()`, `share()`, or an independently managed source) has its own lifecycle; cancelling one subscriber does not necessarily stop the shared source.

### 6.1 Observing Complete, Error, and Cancel

| Situation | Signal | Observation API |
| --- | --- | --- |
| Source finishes normally | `onComplete` | `doOnSuccess` (Mono), `doOnComplete` (Flux), `doFinally(ON_COMPLETE)` |
| Source emits an error | `onError` | `doOnError`, `doFinally(ON_ERROR)` |
| Subscriber requests stop | `cancel` | `doOnCancel`, `doFinally(CANCEL)` |

`doFinally` is invoked when the sequence terminates in any of the three ways. `doOnTerminate` reacts to complete/error, not fully covering cancellation.

```java
Mono<String> operation = client.get()
        .uri("/report")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(signalType -> {
            switch (signalType) {
                case CANCEL -> System.out.println("cancelled");
                case ON_ERROR -> System.out.println("failed");
                case ON_COMPLETE -> System.out.println("completed");
                default -> { }
            }
        });
```

Creating `operation` does not trigger HTTP yet; a subscription is needed. These callbacks are for observation/cleanup, not replacements for `onErrorResume`, `flatMap`, or stream data transformations.

### 6.2 Cancel vs. Timeout and 4xx/5xx Statuses

- **Cancel:** a downstream subscriber or operator requests stopping. A cancelled subscriber normally does not receive an extra `onError` just to report "cancelled."
- **Reactor timeout:** `timeout(Duration)` expires waiting for a signal, **cancels upstream**, and emits `TimeoutException` downstream when no fallback is present.
- **HTTP 404/500:** these are HTTP response statuses; `retrieve()` has logic converting certain statuses into errors. This is not equivalent to cancellation.
- **Connector timeouts:** connect timeout, response timeout, or read timeout control individual transport phases; they do not replace an overall business deadline.

```java
Mono<String> timed = client.get()
        .uri("/slow")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(kind -> System.out.println("beforeTimeout=" + kind))
        .timeout(java.time.Duration.ofSeconds(2))
        .doFinally(kind -> System.out.println("afterTimeout=" + kind));
```

When expiring before a result arrives, the **upstream** `doFinally` can observe `CANCEL`, while the `doFinally` downstream of `timeout` observes `ON_ERROR`. Those are two perspectives on the same timeout event, not conflicting results. Log printing order can depend on schedulers; do not write tests relying on callback ordering unless guaranteed by the API.

`Flux.take(1)` can cancel upstream after receiving the first item; `switchMap` can cancel the previous inner task when a new value arrives. For HTTP streaming, understand closing/releasing the body after early termination so connections are not held unintentionally.

## 7. Lifecycle Management in Controllers and Services

A WebFlux controller should describe work as a publisher, for example:

```java
@GetMapping("/product/{sku}")
public Mono<String> product(@PathVariable String sku) {
    return inventoryClient.get()
            .uri("/products/{sku}", sku)
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(3));
}
```

This snippet belongs inside a `@RestController` with `inventoryClient` injected; import `@GetMapping`, `@PathVariable`, `Mono`, and `Duration`. The WebFlux runtime subscribes to the publisher and can signal cancellation when the caller's connection closes, depending on processing stage. Hence a service does not need manual `subscribe()` to "start" the request immediately.

For work that truly must outlive the HTTP lifecycle (such as long-running jobs), build a dedicated job mechanism with clear identity, state, deadlines, and cancellation controls. Never assume a detached `subscribe()` is a reliable background task system.

### 7.1 How Do Cancellation and Correlation IDs Relate?

Correlation IDs explain **which request** completed, failed, or was cancelled. A filter can safely log metadata and record termination type via `doFinally`, though it should not read response bodies just to log or trigger extra requests just for logging.

If using `doFinally` in a filter, pay attention to operator placement: timing a single HTTP attempt differs from timing the entire pipeline with `retry`, `timeout`, and body decoding. When cross-layer observability is needed, use Micrometer Observation/Tracing or appropriate instrumentation for consistent measurements, attaching the correlation ID as an extra attribute.

Never log tokens, cookies, authorization headers, payment data, or raw query strings containing secrets. Do not treat cancellation as a business error if the user genuinely lost interest in the result.

## 8. Testing Without a Network Connection

Use a fake `ExchangeFunction`, as in section 5, to capture outbound headers. With JUnit 5 + `reactor-test`, a test can verify the ID belongs to the right subscription:

```java
AtomicReference<String> seen = new AtomicReference<>();

ExchangeFunction fake = request -> {
    seen.set(request.headers().getFirst("X-Correlation-ID"));
    return Mono.just(ClientResponse.create(HttpStatus.OK)
            .body("done")
            .build());
};

WebClient client = WebClient.builder()
        .baseUrl("https://example.invalid")
        .exchangeFunction(fake)
        .filter(CorrelationFilter.create())
        .build();

StepVerifier.create(client.get()
                .uri("/test")
                .retrieve()
                .bodyToMono(String.class)
                .contextWrite(Context.of("correlationId", "test-123")))
        .expectNext("done")
        .verifyComplete();

assertEquals("test-123", seen.get());
```

This is a **snippet inside a `@Test` method** requiring imports for `AtomicReference`, `ExchangeFunction`, `ClientResponse`, `HttpStatus`, `WebClient`, `Mono`, `Context`, `StepVerifier`, and `assertEquals`. The test uses `CorrelationFilter` from section 3. With Gradle, declare `testImplementation 'io.projectreactor:reactor-test'` and a compatible JUnit 5.

Testing pure Reactor cancellation:

```java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.create(Mono.<String>never()
                .doOnCancel(() -> cancelled.set(true)))
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

This test verifies the Reactor protocol, **not that a real HTTP server stopped processing**. To test transport behavior, use a mock server with controllable response/connection timing and monitor connection closing, body release, and actual requests.

Test cases to cover: missing Context, two subscriptions with different IDs, two nested requests, invalid inbound headers, cancellation before and after response starts, timeout with downstream error, retry after a side-effecting action, and shared/hot tasks that do not stop like ordinary cold sources.

## 9. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "Reactor Context is the new ThreadLocal" | Mixes IDs across requests when schedulers switch threads | Use `deferContextual`, `contextWrite`; integrate MDC explicitly |
| Calling `ctx.put(KEY, id)` and discarding the returned Context | Active Context remains unchanged | Return the Context created by `put`, e.g., `contextWrite(c -> c.put(...))` |
| Placing `contextWrite` on the wrong side of the reader | Filter may fail to see the value | Check upstream/downstream placement and subscription boundaries |
| Building a filter that reads ID at client construction time | User/request ID gets pinned or lost | Read Context inside `Mono.deferContextual` when the request is subscribed |
| Using `ClientRequest.attribute` and expecting it on the next API call | Second request lacks the ID | Use Context and a filter that sets HTTP headers |
| Calling `subscribe()` manually in a controller | Loses caller cancellation/error/context ties | Compose publishers via `flatMap`/`then` and return to runtime |
| Treating correlation IDs as trusted tokens | Easy to spoof, causing flawed authorization decisions | Authenticate independently; use IDs strictly for log correlation |
| Assuming cancel stops server transactions | Can duplicate payments/writes on retry | Idempotency keys, deadlines, final status checks |
| Using only `doOnError` to count cancellations | Misses many cancellations that emit no error | Observe `doOnCancel` / `doFinally(CANCEL)` |
| Confusing Reactor `timeout` with all network timeouts | Connect/read delays lack clear policies | Combine business deadlines with connector timeouts |
| Returning `ClientResponse` after a filter reads its body | Downstream loses the body or leaks resources | Do not consume body just to log; manage body lifecycle properly if intercepting |
| Logging all headers/bodies | Exposes secrets/PII | Log only allowlisted fields; use standard tracing |

## 10. Check Your Understanding

1. A single `Mono` reads `Context`, and two subscribers supply different IDs: which ID does the filter see? **The ID belonging to the current subscriber.**
2. Why is `contextWrite` typically placed near the end of the pipeline? **Context flows from the subscriber upward to upstream, where `deferContextual` and filters read it.**
3. Once an ID is placed in Reactor Context, does a downstream service automatically receive it? **No; it must be written into a header or propagated via a configured tracing mechanism.**
4. Does a `flatMap` calling another WebClient preserve Context? **Yes, when the inner publisher is properly composed in the same reactive chain; detached manual `subscribe()` breaks that link.**
5. What signals does `timeout` normally produce? **Cancels upstream and emits a `TimeoutException` error downstream if no fallback exists.**
6. Does cancelling WebClient reverse work the server already processed? **No; business rules are needed for side-effecting requests with ambiguous outcomes.**
7. Is using `ThreadLocal` instead of Context safe for all async requests? **No; a single request can switch threads, and a thread can serve many different requests.**
8. Is one correlation ID enough to replace distributed tracing? **No; tracing also requires spans, relationships, and standard propagation context.**

In real deployments, standardize where IDs are minted, how inbound IDs are validated, how IDs travel in Reactor Context, the outbound-header filter, logging/tracing conventions, deadlines, and idempotency preconditions before enabling automatic retries.

## 11. References

- [Spring Framework — WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): guide to `Mono.deferContextual` and `contextWrite` in filters.
- [Spring Framework — WebClient Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html): scope of per-request attributes.
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): `ExchangeFilterFunction` and filter configuration.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context propagation direction, ContextView, immutability.
- [Project Reactor — Error Handling / doFinally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): distinguishing completion and cancellation.
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `doOnCancel`, `doFinally`, and `timeout`.
