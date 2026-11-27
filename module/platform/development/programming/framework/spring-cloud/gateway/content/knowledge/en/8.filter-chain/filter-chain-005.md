# Continuing the Chain with chain.filter(exchange)

## 1. Why Is Understanding chain.filter(exchange) Essential?

In **Spring Cloud Gateway Server WebFlux**, a request typically passes through several filters before being forwarded to a microservice: attaching tracing info, modifying paths/headers, authenticating or enforcing policies, rate limiting, circuit breaking, retrying, and collecting observability metrics. These filters must coordinate so that each request is handled in the right order.

The most critical call inside a custom filter is:

~~~java
return chain.filter(exchange);
~~~

It expresses: **pass `ServerWebExchange` to the remainder of the filter chain and return a `Mono<Void>` representing that asynchronous execution**. If a filter fails to continue the chain, downstream filters and upstream routing may not execute; that behavior is valid when a filter intentionally rejects a request, but it is a bug if the author simply forgot to return `chain.filter(exchange)`.

In this lesson from the **Filter Chain** chapter, we focus on the lifecycle of `chain.filter(exchange)`, how to write pre/post processing, how to pass a modified exchange, and when to stop the chain. The examples sit in the context of building an **API Gateway** with route predicates, filter chains, header/path transformations, service discovery, and security/reliability controls.

**After this lesson, you will be able to:**

1. Describe the roles of `ServerWebExchange`, `GatewayFilterChain`, and the `Mono<Void>` return type.
2. Write a `GlobalFilter` or `GatewayFilter` that continues the chain properly without calling `subscribe()` or `block()`.
3. Distinguish **pre**, **post**, **error**, and **cancel** handling in Reactor.
4. Modify requests/responses at the right moment and know when a response has already been committed.
5. Recognize **short-circuiting**, filter ordering, error handling, streaming request bodies, and common mistakes.
6. Verify that the chain actually runs using unit tests and requests sent through the gateway.

> This article focuses on **Spring Cloud Gateway Server WebFlux** and Reactor. Spring Cloud Gateway Server Web MVC has a different filter model; do not copy WebFlux `GatewayFilterChain` examples directly into the MVC variant.

## 2. Where Does the Filter Chain Sit in Request Processing?

When a request arrives at Gateway, `RoutePredicateHandlerMapping` finds a matching route based on predicates such as `Path`, `Host`, `Method`, or `Header`. Once a route is selected, `FilteringWebHandler` builds a chain combining `GlobalFilter`s and the route's `GatewayFilter`s. The chain is sorted by order and processes the request reactively.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[RoutePredicateHandlerMapping]
    B -->|Route selected| C[FilteringWebHandler]
    C --> D[Filter A: pre]
    D --> E[Filter B: pre]
    E --> F[Routing filter / upstream handler]
    F --> G[Filter B: post]
    G --> H[Filter A: post]
    H --> I[HTTP response]
~~~

The diagram depicts the **wrapping pre/post order** during normal request processing. In practice, a filter might run only pre, only observe terminal signals, return a response itself, or delegate handling to another mechanism. Not every filter has a post section.

Three key concepts:

| Concept | Role | What to Remember |
| --- | --- | --- |
| `ServerWebExchange` | HTTP request/response context for the current exchange | Holds request, response, attributes, and related metadata |
| `GatewayFilterChain` | Abstraction for invoking the remainder of the chain | Primary method is `Mono<Void> filter(ServerWebExchange exchange)` |
| `Mono<Void>` | Signal indicating asynchronous processing completed, errored, or was canceled | Emits no `Void` data item for `map` or `doOnNext` to process |

Subtle point: **returning `Mono<Void>` does not mean the response has no body**. The body can be written by downstream components via `response.writeWith(...)` or WebFlux codecs; `Mono<Void>` simply indicates that reactive processing/response writing has finished.

## 3. The Exact Meaning of chain.filter(exchange)

In the signature of `GlobalFilter` and `GatewayFilter`:

~~~java
Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
~~~

`chain.filter(exchange)` builds the next portion of the processing pipeline for the given exchange. When the pipeline has a subscriber managed by WebFlux, actual work executes per Reactor semantics; completion, error, or cancellation signals propagate back up through outer wrapping filters.

~~~mermaid
sequenceDiagram
    participant Framework as WebFlux runtime
    participant A as Filter A
    participant B as Filter B
    participant R as Routing/handler

    Framework->>A: filter(exchange, chain)
    A->>A: pre A
    A->>B: chain.filter(exchange)
    B->>B: pre B
    B->>R: chain.filter(exchange)
    R-->>B: Publisher completes
    B->>B: post B
    B-->>A: Mono<Void> completes
    A->>A: post A
    A-->>Framework: Completion signal
~~~

Distinguish **calling a method to build/compose a publisher** from **subscribing to the publisher**. In much Reactor code, performing I/O or asynchronous calls is deferred until subscription. However, Java statements placed **directly before** `return chain.filter(exchange)` execute immediately when `filter` is called. When you need to defer even task creation until subscription time, use `Mono.defer(...)` deliberately.

The simplest, cleanest, and most idiomatic pattern:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Pre: validate/prepare whatever the request needs.
    return chain.filter(exchange);
}
~~~

**Never call `chain.filter(exchange)` just for side effects and discard the result.** If the `Mono` is not properly subscribed to, downstream work may never run. The framework must receive the publisher back to coordinate the request lifecycle, errors, and cancellation.

## 4. Writing a GlobalFilter with Pre and Post Handling

Suppose we want to measure elapsed time from when a filter starts until the chain finishes. A simple `GlobalFilter`:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class GatewayTimingFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(GatewayTimingFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        long startedAt = System.nanoTime(); // Pre

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn("Gateway processing failed: {}",
                                error.getClass().getSimpleName()))
                .doFinally(signal -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);
                    log.info("Gateway finished: signal={}, durationMs={}",
                            signal, durationMs);
                });
    }
}
~~~

**Code execution path:**

1. `startedAt` captures the start time when the filter is called.
2. `chain.filter(exchange)` continues the chain and returns `Mono<Void>`.
3. `doOnError` observes error signals passing through the publisher without **swallowing the error**.
4. `doFinally` runs when the chain emits completion, error, or cancellation. It is suitable for recording timing or cleaning up locally managed resources.

In Reactor, the `doFinally` signal can be `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. When a client disconnects mid-stream during a long response, the stream may receive a cancel signal; **do not log only successful completions**. The duration measured here is how long the publisher was active at this filter's position, which is not necessarily equal to the time until the client has consumed every byte from the OS socket.

If Micrometer/Actuator and gateway metrics are already enabled, prefer built-in observability for latency, route ID, status, and tracing; the example above is meant to clarify the lifecycle of `chain.filter(exchange)`.

## 5. Post Is Not a Statement Placed Right After chain.filter

The following code **misses its intent** if the author wants to log after downstream completes:

~~~java
Mono<Void> downstream = chain.filter(exchange);
log.info("Downstream finished"); // Can run before downstream actually finishes!
return downstream;
~~~

The `log.info` statement executes right after obtaining the publisher, while downstream processing may still be pending. Instead, attach actions to Reactor signals:

~~~java
return chain.filter(exchange)
        .doOnSuccess(ignored -> log.info("Completed successfully"))
        .doOnError(error -> log.warn("Processing failed", error))
        .doFinally(signal -> log.debug("Final signal: {}", signal));
~~~

`Mono<Void>` emits no value for `doOnNext`. On success, `doOnSuccess` still runs, receiving `null` because the `Mono` completes empty. If you only want to run reactive work **after downstream finishes successfully**, you can use:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                log.info("Run only after successful downstream completion")));
~~~

With `then(...)`, the next step runs only when the downstream publisher completes successfully; if upstream errors, the error propagates, and if canceled, the continuation does not run. `doFinally` differs in that it also observes cancellation. **Do not place long blocking work inside these callbacks**, as they may execute on Reactor Netty's event loop.

### Why Should You Not Use switchIfEmpty for Post?

`Mono<Void>` completes **without emitting any items** on success, so:

~~~java
// Misleading example:
return chain.filter(exchange)
        .switchIfEmpty(someAlternativeMono);
~~~

`switchIfEmpty` treats normal completion of `Mono<Void>` as an empty result and executes the alternative on **every successful call**, not just when "no route matched." This is not how to build an HTTP fallback for Gateway. Use error semantics or CircuitBreaker/fallback mechanisms instead.

## 6. Passing a Modified ServerWebExchange

A filter may need to normalize request headers or inject trusted information before forwarding. Rather than attempting to mutate the current request in place, use Spring WebFlux's **mutate/decorator** mechanism and pass the **newly wrapped exchange** down the chain:

~~~java
import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class GatewayRequestIdFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -200;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String requestId = UUID.randomUUID().toString();

        ServerHttpRequest request = exchange.getRequest().mutate()
                .headers(headers -> {
                    headers.remove("X-Gateway-Request-Id");
                    headers.set("X-Gateway-Request-Id", requestId);
                })
                .build();

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .build();

        return chain.filter(updated);
    }
}
~~~

This generates a new ID and replaces any `X-Gateway-Request-Id` header the client may have sent beforehand. This is only an example of **passing a mutated exchange**, not a complete distributed tracing solution. Standard tracing should use built-in context propagation/instrumentation, with clear policies for trace IDs, trusted headers, and logs.

The crucial line is:

~~~java
return chain.filter(updated);
~~~

If you build `updated` yet still call `chain.filter(exchange)`, downstream filters and handlers receive the **old exchange** and will not see the new request header. Both exchange objects may share the underlying response/attributes depending on decorator behavior, but the mutated request view is only passed downstream when you pass the updated variable.

### What About Modifying the Path?

You can mutate the request path if you understand the exact requirements, but for standard routes prefer built-in filters such as `StripPrefix` or `RewritePath`, because Gateway also tracks target URLs in **exchange attributes** used by routing filters. Arbitrarily editing the path on `ServerHttpRequest` while assuming the proxy URL updates automatically can cause mismatches. Verify the client path, post-filter path, and URL received by the backend.

## 7. Setting Response Headers at the Right Moment

Once downstream writes the response, headers may already be **committed** and cannot be safely modified. Therefore, this code is unreliable:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true")));
~~~

By the time `then` runs, downstream may have already sent headers and body. If your goal is to attach a response header **before writing**, register a `beforeCommit` callback before continuing:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    exchange.getResponse().beforeCommit(() -> {
        exchange.getResponse().getHeaders()
                .set("X-Gateway-Processed", "true");
        return Mono.empty();
    });

    return chain.filter(exchange);
}
~~~

The `beforeCommit` callback runs right before the response is committed. Do not put thread-blocking I/O or expensive operations inside it. If downstream has already committed the response by the time you try to register the callback, adding headers will have no effect; always register **before** forwarding.

Within the same application, multiple filters may edit the same header. Define clear ownership and update order so two filters do not overwrite each other. Security headers such as `Strict-Transport-Security`, `Access-Control-Allow-Origin`, or identity headers must be configured by appropriate policies, never copied blindly from the client.

## 8. When Should You Intentionally Not Call chain.filter(exchange)?

**Short-circuiting** occurs when a filter decides to terminate a request immediately—for example, when a request violates a policy, exceeds a rate limit, or misses a required precondition. In that case, the filter can write a response directly and **not call the remainder of the chain**.

Minimal example rejecting HTTP TRACE in a filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    if (HttpMethod.TRACE.equals(exchange.getRequest().getMethod())) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

Two distinct branches:

- If the method is `TRACE`, the filter returns a publisher that completes a `403` response without routing upstream.
- If it is not `TRACE`, the filter calls `chain.filter(exchange)` normally.

This snippet assumes `HttpMethod` and `HttpStatus` imports from Spring HTTP inside an appropriate filter and only illustrates short-circuiting. In real applications, authentication/authorization policies should rely on Spring Security, and rate limiting should use dedicated components where appropriate.

~~~mermaid
flowchart TD
    R[Request enters filter] --> Q{Violates rule?}
    Q -->|Yes| S[Set status / body]
    S --> T[return response.setComplete]
    Q -->|No| N[return chain.filter(exchange)]
    N --> U[Next filter and routing]
~~~

**Stopping the chain means not calling downstream**; it does not make earlier filters "disappear." Outer wrapping filters still receive the completion/error/cancel signal from the publisher returned by the short-circuiting filter. Thus metrics or `doFinally` in an outer filter can still record the rejected request.

If you want to return JSON instead of an empty response, set status/content type and **write the body** using the reactive response API, then return the body-writing publisher itself; never return `Mono.empty()` right after starting a write without chaining the write task into the pipeline.

## 9. Mistakes That Break Proper Chain Continuation

| Code Pattern or Behavior | Consequence | How to Fix |
| --- | --- | --- |
| `chain.filter(exchange); return Mono.empty();` | Discards downstream publisher; request may go unhandled | `return chain.filter(exchange);` |
| `chain.filter(exchange).subscribe(); return Mono.empty();` | Creates a detached subscription outside the HTTP lifecycle, causing races/missed errors | Return the publisher to the framework |
| `chain.filter(exchange).block();` | Blocks the event loop; risks deadlocks or blocking exceptions | Compose the pipeline with Reactor operators |
| Calling `chain.filter(exchange)` twice | Can re-run filters/routing, send duplicate upstream requests, or corrupt responses | Call once per intentional execution path |
| Creating `updated` but calling `chain.filter(exchange)` | Downstream does not receive the mutated request | `chain.filter(updated)` |
| Logging "done" immediately after getting `Mono` | Logs before I/O actually finishes | Use `doOnSuccess`, `doOnError`, `doFinally` |
| Using `doOnNext` on `Mono<Void>` | Never observes completion | Use `doOnSuccess` or `doFinally` |
| Editing response headers in post after commit | Header is not sent or throws an error | Register `beforeCommit` in the pre-phase |
| Catching error and returning `Mono.empty()` without a response | Can turn an error into completion with unintended HTTP semantics | Return an error/status matching the contract |
| Reading the entire body just to inspect a header | Wastes memory and can break streaming | Read headers directly; avoid consuming the body unnecessarily |

A particularly subtle bug is:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> Mono.empty());
~~~

This **swallows all errors** from downstream and replaces them with completion, even though the response may lack a valid status or body. If part of the body was already sent, swallowing the error also hides mid-stream failures. Only use `onErrorResume` when you have an explicit fallback policy, produce a valid response, and account for whether the response is already committed.

## 10. Error, Cancel, and Response Commit Events

Filters can observe three main outcomes of the downstream publisher:

| Outcome | Reactor Signal | Common Meaning |
| --- | --- | --- |
| Completion | `onComplete` | Chain ended along the success path, possibly via short-circuit |
| Error | `onError` | A downstream step emitted an error; error handlers may set a status or close the connection |
| Cancellation | `cancel` | Subscriber no longer needs the stream, e.g. client closed the connection |

**There is no guarantee every downstream error can produce an arbitrary fresh response.** In HTTP, once headers and the first bytes are sent, the response is committed; Gateway cannot rewind and change the overall status to `500` or `503`. This is especially important when proxying SSE, NDJSON, file downloads, or large uploads.

Example error branch checking response state, for illustration only:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse()
                    .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        });
~~~

**Do not use this pattern as a generic production error handler.** It turns **every error** into 503—including programming bugs, auth failures, and invalid requests—which is semantically wrong. A real implementation must classify errors, preserve appropriate status codes, record metrics, avoid leaking internals, and leverage Gateway's built-in error-handling mechanisms.

**Retry and CircuitBreaker** also work by wrapping the downstream publisher. Retry configuration must consider idempotency: retrying a POST that creates an order or payment can cause duplicate side effects without safeguards. For partially sent streaming responses, re-running the pipeline cannot guarantee the client receives a deduplicated event stream; application-level resume/idempotency is required.

## 11. Filter Order Determines Pre and Post

Spring Cloud Gateway combines `GlobalFilter`s and the route's `GatewayFilter`s into one chain and sorts them by `Ordered` or the applicable ordering mechanism. **Smaller order values typically have higher priority on entry**.

Suppose:

| Filter | Order | Pre | Post |
| --- | ---: | ---: | ---: |
| A | -100 | 1 | 3 |
| B | 0 | 2 | 2 |
| C | 100 | 3 | 1 |

~~~mermaid
flowchart LR
    A1[A pre] --> B1[B pre]
    B1 --> C1[C pre]
    C1 --> R[Routing / response work]
    R --> C2[C post]
    C2 --> B2[B post]
    B2 --> A2[A post]
~~~

Filter A has the smallest order, so it can run **earliest in pre** and **last in post** when post is attached to the downstream publisher. Never pick an order purely based on wanting to run "early" or "late" while ignoring both phases.

**Distinguish types of order:**

- **Route order** decides which route is evaluated first when multiple routes match predicates.
- **Filter order** decides a filter's position inside the chain **after a route has been selected**.
- Built-in filters for routing, metrics, response writing, or load balancing have their own orders. If a custom filter depends on them, verify the exact order and attributes required in your running Gateway version.

A `GlobalFilter` runs in the pipeline of **requests routed by Gateway**, which does not mean it automatically applies to **every** Spring WebFlux request in the application. If you need policies for local WebFlux endpoints outside Gateway, consider `WebFilter` or Spring Security WebFlux with an appropriate scope. Do not confuse `GatewayFilterChain` with `WebFilterChain`.

## 12. Route-Specific GatewayFilters Must Also Continue the Chain

Not only `GlobalFilter`s—a `GatewayFilter` attached to a specific route also receives the same parameters. Example using the Java Route DSL:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.ServerHttpRequest;

@Configuration
class RouteConfiguration {

    @Bean
    RouteLocator catalogRoutes(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("catalog", r -> r.path("/api/catalog/**")
                        .filters(f -> f.filter((exchange, chain) -> {
                            ServerHttpRequest request = exchange.getRequest()
                                    .mutate()
                                    .header("X-Gateway-Section", "catalog")
                                    .build();
                            return chain.filter(
                                    exchange.mutate().request(request).build());
                        }))
                        .uri("lb://catalog-service"))
                .build();
    }
}
~~~

This route uses the `Path=/api/catalog/**` predicate, a filter that adds a request header, and the `lb://catalog-service` URI. This filter runs **when the catalog route is selected**, rather than globally across all routes.

`lb://` requires load-balancing/service-discovery infrastructure (e.g. Spring Cloud LoadBalancer and configured service discovery). For quick local testing, you can use `http://localhost:9001` if a backend is running on that port. The snippet illustrates chaining `chain.filter(exchange)` and omits full dependencies, project setup, and backend code.

If you only need to add or remove simple headers, prefer **built-in GatewayFilterFactories** such as `AddRequestHeader`, `SetRequestHeader`, and `RemoveResponseHeader` rather than writing a custom Java filter. Custom filters are useful for conditional logic, request-context state, or specialized integrations.

### Why Not Attach Arbitrary Headers for Identity Information?

If downstream trusts `X-User-Id` or `X-Role`, never forward client-controlled headers and treat them as authenticated. The gateway must obtain identity from a trusted source, restrict what gets propagated, and establish protective network boundaries. The header filter shown above uses the fixed value **catalog** and does not grant permissions.

## 13. Do Not Accidentally Consume the Request Body Before Calling the Chain

`ServerWebExchange` holds the request body as a publisher, at a low level typically `Flux<DataBuffer>`. For streaming data, reading the body inside a filter can leave downstream with no data or force buffering the entire payload in RAM.

An **anti-pattern** for logging the body:

~~~java
// Do not use: subscribing manually can consume the body stream before downstream.
exchange.getRequest().getBody()
        .subscribe(buffer -> log.debug("Received body chunk"));
return chain.filter(exchange);
~~~

This creates an independent subscription, fails to manage `DataBuffer` ownership, and does not propagate error/cancellation signals into the Gateway chain. If a request body can only be consumed once, downstream may receive incomplete data or fail.

Another dangerous pattern:

~~~java
// Do not use for large/unbounded bodies just to log.
Mono<DataBuffer> combined =
        DataBufferUtils.join(exchange.getRequest().getBody());
~~~

`DataBufferUtils.join(...)` aggregates the body into a single buffer; using it safely requires understanding size limits and `DataBuffer` retain/release rules. For large uploads, SSE, NDJSON, or streaming bodies, full buffering defeats streaming benefits. If content transformation is needed, use built-in body filters, codecs, decorators, and size limits, and test end-to-end.

When you only need to inspect headers, path, method, or attributes, **do not touch the body**. Simply let:

~~~java
return chain.filter(exchange);
~~~

pass the body to the proxy/handler component designed to consume and forward data asynchronously.

## 14. Testing That the Chain Is Called and the Mono Completes

A small filter unit test can construct a `MockServerWebExchange`, define a mock `GatewayFilterChain`, and use Reactor `StepVerifier`. Example for `GatewayRequestIdFilter` from section 6:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayRequestIdFilterTest {

    @Test
    void forwardsMutatedExchangeToNextFilter() {
        GatewayRequestIdFilter filter = new GatewayRequestIdFilter();
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/items")
                        .header("X-Gateway-Request-Id", "untrusted")
                        .build());

        AtomicReference<String> observedId = new AtomicReference<>();

        GatewayFilterChain next = forwardedExchange -> {
            observedId.set(forwardedExchange.getRequest()
                    .getHeaders().getFirst("X-Gateway-Request-Id"));
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
                .verifyComplete();

        assertThat(observedId.get())
                .isNotBlank()
                .isNotEqualTo("untrusted");
    }
}
~~~

This is an **illustrative test** that belongs in the test source set with compatible `spring-test`, `reactor-test`, JUnit 5, and AssertJ dependencies. It verifies that the filter actually forwards the mutated request to the next link and completes the publisher. It **does not yet prove** HTTP routing, security, timeouts, or backend behavior.

### Additional Tests for Short-Circuiting

Write two test cases for the `TRACE`-rejecting filter in section 8:

1. `TRACE` request: use an `AtomicBoolean` to record if `next.filter` was invoked; expect the flag to be **false**, the response completed, and status 403.
2. `GET` request: expect `next.filter` to be called **exactly once** and the publisher to complete.

For filters with post-processing, use a downstream publisher that emits completion or error on demand to verify callbacks run **at the right time**; do not merely assert the returned object is non-null. To test real Gateway behavior, write integration tests with real routes and a stub backend verifying response, route ID, forwarded headers/paths, and error cases.

## 15. Hands-On Scenario: Tracing Requests Then Intentionally Blocking

Suppose a gateway for Catalog and Orders microservices needs two capabilities: attaching a trusted request ID to requests passing through the gateway and recording processing time, while an admin endpoint can be rejected early per Spring Security policy.

### Part A — Build Chain-Continuing Filters

1. Use `GatewayRequestIdFilter` from section 6; verify that when a client sends `X-Gateway-Request-Id: untrusted`, the upstream receives a newly generated ID.
2. Use `GatewayTimingFilter` from section 4; send both a successful request and a failing request, observing `doFinally` and latency.
3. Define a route to the service using `lb://` or a fixed HTTP URI. Ensure the route predicate matches and requests are forwarded.

### Part B — Observe a Short-Circuit

1. Add a test filter that rejects `TRACE` with status 403 without calling `chain.filter(exchange)` on the rejection branch.
2. Send a normal request and verify the backend is called.
3. Send a blocked request and verify the backend **does not receive the request**.
4. Verify the outer timing filter still receives the completion signal; distinguish blocked requests from upstream-error requests.

### Part C — Spot Reactor Lifecycle Bugs

Try these in a test environment, then **restore the correct implementation**:

| Experiment | Phenomenon to Observe |
| --- | --- |
| Forget `return chain.filter(exchange)` | Downstream does not execute as expected |
| Call `subscribe()` manually | Pipeline detaches from HTTP lifecycle; errors/responses become hard to control |
| Log immediately after obtaining `Mono` | Log timestamp differs from when response actually completes |
| Edit headers in post after response commit | Header may fail to appear in the response |
| Mutate request but pass old exchange | Backend does not receive the added header |
| Use `doOnNext` to count completions | Does not fire on empty-completing `Mono<Void>` |
| Client cancels streaming response mid-way | `doFinally` may receive `CANCEL` |

### Part D — Acceptance Criteria

Verify using logs/metrics and a test backend that:

- The right route is matched; route-level and global filters apply within their intended scopes.
- `chain.filter(updatedExchange)` delivers changes downstream.
- Every normal path continues the chain **once**; short-circuit paths do not continue.
- Pre/post/error/cancel logic is measured at the proper points without blocking the event loop.
- Tokens, cookies, and full bodies are not logged; backends still receive complete request bodies when needed.
- Response headers are attached before commit without raising errors after streaming begins.

## 16. Summary

- **`return chain.filter(exchange);`** is the fundamental operation for a Gateway filter to **forward the request to the rest of the chain** while returning the publisher for WebFlux to coordinate.
- `Mono<Void>` represents **asynchronous completion** of the pipeline; use `doOnSuccess`, `doOnError`, `doFinally`, or `then` to build proper post logic. Avoid misusing `doOnNext` or `switchIfEmpty`.
- When modifying a request, pass the **mutated exchange** into `chain.filter(updated)`. To edit response headers, prepare them **before commit**, e.g. with `beforeCommit`.
- **Short-circuiting** means intentionally skipping downstream and completing the response directly; enforce proper policies and status/body semantics, and never use it to hide errors.
- **Filter order** determines pre and post execution sequence; `GlobalFilter` differs from `WebFilter` and from route-bound `GatewayFilter`s.
- Never call `subscribe()`, `block()`, invoke the chain twice, or arbitrarily consume the body inside a filter. These fundamentals ensure a Spring Cloud Gateway API Gateway stays correct, performant, secure, and observable for microservices.
