# Handling Pre, Post, Error, and Cancel in a Reactor Chain

## 1. Why Must You Understand the Reactive Lifecycle When Writing Custom Filters?

In **Spring Cloud Gateway**, an incoming request is matched to a route using route predicates (such as `Path`, `Method`, `Header`), then passes through a filter chain for authentication, rate limiting, path/header transformation, instance selection via `lb://`, HTTP(S) connection, retry, circuit breaking, and response delivery. Developers can add a **`GatewayFilter`** or **`GlobalFilter`** to measure duration, attach headers, enforce custom rules, or record events.

However, Gateway Server WebFlux is built on **Reactor**: a filter method returns `Mono<Void>` instead of executing the entire request synchronously at the moment it is called. Confusing **creating a Publisher** with **subscribing to and executing that Publisher** can cause a custom filter to:

- Log "success" before downstream has even started.
- Miss canceled requests when a client disconnects.
- Overwrite 401/403 errors or turn a 503 into a 200 in violation of the contract.
- Attempt to modify the response after headers have already been sent.
- Call `subscribe()` or `block()`, losing lifecycle control and stalling the event loop.
- Retain `DataBuffer` or other resources after cancellation, causing memory leaks.
- Misreport latency when retries, circuit breakers, or streaming are involved.

The lesson **"Handling Pre, Post, Error, and Cancel in a Reactor Chain"**, in the **Custom Filters** chapter, explains how to design filters that respect the asynchronous lifecycle of **Spring Cloud Gateway Server WebFlux**. Examples focus on `GlobalFilter`, `GatewayFilter`, `GatewayFilterChain`, `ServerWebExchange`, and `Mono<Void>`.

After this lesson, you will be able to:

1. Distinguish **pre** and **post** processing, including when multiple filters have different orders.
2. Explain Reactor signals **onSubscribe**, **onComplete**, **onError**, and **cancel** inside a `Mono<Void>`.
3. Use `Mono.defer`, `doOnSubscribe`, `doOnSuccess`, `doOnError`, `doOnCancel`, and `doFinally` appropriately.
4. Use `onErrorResume` conditionally without masking security errors or writing responses after commit.
5. Register `ServerHttpResponse.beforeCommit` to adjust response headers before commit time.
6. Test ordering, success, error, and cancellation using **StepVerifier** or HTTP integration tests.
7. Apply non-blocking principles, protect sensitive data, propagate context, and clean up resources on termination.

> **Scope:** This lesson applies to **Spring Cloud Gateway Server WebFlux** (Reactor Netty), not the Server Web MVC variant. APIs and packages may vary across Spring Boot/Spring Cloud versions. Snippets are learning examples and should be integrated with your real project's dependencies, security, and tests.

## 2. A Filter Has Two Logical Phases: Before and After Downstream

Basic interface:

~~~java
public interface GatewayFilter {
    Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
}
~~~

A `GlobalFilter` follows the same idea, applying across eligible Gateway routes:

~~~java
public interface GlobalFilter {
    Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
}
~~~

In a typical implementation, `chain.filter(exchange)` returns a Publisher representing the work of the **remaining filter chain**. A filter can perform work before calling it (**pre**), attach operators to run after it finishes (**post**), or observe errors and cancellation.

~~~mermaid
flowchart TD
    Client["Client HTTP request"] --> Security["WebFlux / Spring Security filters"]
    Security --> Route["Select Gateway route"]
    Route --> F1pre["GlobalFilter A: pre"]
    F1pre --> F2pre["GatewayFilter B: pre"]
    F2pre --> F3pre["GlobalFilter C: pre"]
    F3pre --> Routing["Load balancer + HTTP routing"]
    Routing --> F3post["GlobalFilter C: post"]
    F3post --> F2post["GatewayFilter B: post"]
    F2post --> F1post["GlobalFilter A: post"]
    F1post --> Client
~~~

This is a **nested** model. If A runs pre before B, A's post section typically triggers after B's post section, like opening and closing nested wrappers.

### Execution Order Is Determined by `order`

Gateway merges GlobalFilters and GatewayFilters into a single ordered chain. Components with higher precedence (lower order values) usually execute **earlier in the pre phase** and **later in the post phase**. However, **Reactor operators also determine when signals are observed**, so you must not infer everything solely from YAML declaration order.

| Filter | Example order | Pre phase | Post phase when downstream completes |
| --- | ---: | ---: | ---: |
| A | -100 | 1 | 3 |
| B | 0 | 2 | 2 |
| C | 100 | 3 | 1 |

Note: This table illustrates **order**; not every callback always runs when downstream errors or cancels. `then(...)` only proceeds when the upstream chain completes successfully; `doFinally` receives complete, error, and cancel.

### Short Example: Pre and Post for the Success Case

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Preparation phase; executed when filter(...) is invoked.
    long startNanos = System.nanoTime();

    return chain.filter(exchange)
            .then(Mono.fromRunnable(() -> {
                long elapsedNanos = System.nanoTime() - startNanos;
                // Non-blocking work after downstream completes successfully.
                recordSuccessDuration(elapsedNanos);
            }));
}
~~~

The snippet above is only a **sketch**, with `recordSuccessDuration` as a placeholder method. `then(Mono.fromRunnable(...))` **does not run when downstream emits an error or is canceled**. Furthermore, capturing `startNanos` before the Publisher is subscribed can include any delay between **chain assembly** and **execution**. When per-subscription data is needed, use `Mono.defer`.

## 3. Reactor Is a Publisher with a Lifecycle, Not a Synchronous Call

`Mono<Void>` represents an asynchronous process emitting at most one item, though with `Void` there is normally **no `onNext` payload** to consume. It can:

- Be subscribed and **complete successfully** (`onComplete`).
- Be subscribed and **fail** (`onError(Throwable)`).
- Be **canceled** via `Subscription.cancel()` before a terminal signal.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Create Publisher
    Created --> Subscribed: subscribe
    Subscribed --> Completed: onComplete
    Subscribed --> Failed: onError
    Subscribed --> Cancelled: cancel
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

These states model the lifecycle of **a single subscription**. Cancellation is a request from downstream to upstream asking it to stop emitting signals; it is not a new `onError` delivered to the subscriber, and it does not guarantee that already-started I/O or side effects are reversed immediately.

### Assembly vs. Subscription

When code builds:

~~~java
Mono<Void> work = chain.filter(exchange)
        .doOnSuccess(ignored -> log.debug("completed"));
~~~

all you are guaranteed is that you are **constructing a Publisher chain** and returning it to WebFlux. The reactive work inside the Publisher generally proceeds **only upon subscription**, yet plain Java statements executed while *building the Publisher* can still trigger side effects **at assembly time**. That is why writing `log.info("request complete")` right after `chain.filter(exchange)` is wrong:

~~~java
// ANTI-PATTERN: logging success too early.
Mono<Void> result = chain.filter(exchange);
log.info("Downstream finished"); // No such guarantee exists yet.
return result;
~~~

To defer both capturing the start timestamp and building the Publisher until subscription time, use:

~~~java
return Mono.defer(() -> {
    long startNanos = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedNanos = System.nanoTime() - startNanos;
                recordTerminalSignal(signal, elapsedNanos);
            });
});
~~~

In the example above, `recordTerminalSignal` is an illustrative instrumentation helper. **Every subscription** re-runs the `Mono.defer` supplier, creating fresh local state. To know whether each subscription corresponds to a retry attempt or a whole HTTP request, you must know whether the **retry operator sits outside or inside the filter**.

### Why Never Call `subscribe()` Inside a Filter?

~~~java
// WRONG: creates a detached subscription outside the Gateway lifecycle.
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

This code can signal completion to callers **before routing finishes**, detach cancellation/errors from the original request, cause requests to fire twice, or leak resources. Likewise, `block()` blocks threads (dangerous on the Reactor Netty event loop) and destroys non-blocking scalability.

**Rule:** Always **return the Publisher** to the framework; compose with operators instead of manually subscribing or blocking.

## 4. Operator Selection Table for Pre, Post, Error, and Cancel

| Operator | When does it run? | Does it alter signals? | Used for |
| --- | --- | --- | --- |
| `Mono.defer(supplier)` | Every time the Publisher is subscribed | Produces a fresh Publisher per subscription | Starting timers, local state, lazy pre logic |
| `doOnSubscribe(consumer)` | When subscription is established | Does not actively change outcome | Tracking start/subscription |
| `doOnSuccess(consumer)` | When `Mono` completes normally | No | Recording success; receives `null` for `Mono<Void>` |
| `doOnError(consumer)` | When `onError` occurs | No, unless the callback itself throws | Safely logging exception type, error metrics |
| `doOnCancel(runnable)` | When downstream requests cancellation | Does not turn into an HTTP error | Tracking cancellation |
| `doFinally(consumer)` | After complete, error **or cancel** | No | Stopping timers, lightweight cleanup, telemetry |
| `then(other)` | After upstream completes **normally** | Switches to another Publisher | Composing reactive post-success work |
| `onErrorResume(mapper)` | When upstream emits an error | **Yes**, replaces error with a fallback Publisher | Narrow, controlled fallback |
| `onErrorMap(mapper)` | When upstream emits an error | **Yes**, transforms the exception | Normalizing exception types where needed |
| `doOnEach(consumer)` | On supported signal emissions | No | Observing signals alongside Reactor Context |
| `contextWrite(function)` | Attaches/modifies Reactor Context upstream along subscription | Affects context | Passing immutable metadata; never store raw tokens |

Common misconceptions:

- `doOnSuccess` on `Mono<Void>` **does not receive the HTTP response body**; its argument is normally `null`. Never call `ignored.toString()`.
- `doOnError` **only observes**. It does not "catch" the error to make the response 200. Handling errors requires an explicit operator like `onErrorResume` with a clear policy.
- `doFinally` covers **CANCEL**, yet its callback runs **after the terminal/cancel signal propagates along the chain**; do not rely on it to modify responses before commit.
- `then(...)` does not run on error or cancel. `doOnTerminate` also does not replace cancellation handling.
- `doOnNext` is unsuitable for observing completion of `Mono<Void>` because it normally emits no `onNext`.

### Quick Comparison of the Three Terminal Branches

~~~text
Downstream -> onComplete:
    doOnSuccess -> then(post work) -> downstream complete -> doFinally(ON_COMPLETE)

Downstream -> onError:
    doOnError -> (onErrorResume if present) -> error or fallback -> doFinally(...)

Downstream <- cancel:
    doOnCancel -> upstream cancel/cleanup -> doFinally(CANCEL)
    No onComplete/onError occurs for a canceled subscription.
~~~

Exact callback order **also depends on operator placement in the chain**. If `doFinally` sits before `onErrorResume`, it can observe an upstream error termination even though the overall Publisher recovers via fallback. If placed outside `onErrorResume`, it can observe `ON_COMPLETE` after fallback. Choose placement based on **what you intend to measure**.

## 5. GlobalFilter Example Tracking All Four Branches

A practical need is measuring route processing duration and recording **success**, **error**, or **cancellation** without logging sensitive data. Example:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class SafeLifecycleGlobalFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(SafeLifecycleGlobalFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();
            Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
            String routeId = route == null ? "unknown" : route.getId();

            return chain.filter(exchange)
                    .doOnSubscribe(subscription ->
                            log.debug("route={} lifecycle=subscribed", routeId))
                    .doOnSuccess(ignored ->
                            log.debug("route={} lifecycle=success", routeId))
                    .doOnError(error ->
                            log.warn("route={} lifecycle=error errorType={}",
                                    routeId, error.getClass().getSimpleName()))
                    .doOnCancel(() ->
                            log.debug("route={} lifecycle=cancel-requested", routeId))
                    .doFinally(signal -> {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);
                        HttpStatusCode status =
                                exchange.getResponse().getStatusCode();
                        String statusCode = status == null
                                ? "unknown"
                                : Integer.toString(status.value());

                        log.info(
                                "route={} method={} status={} terminal={} elapsedMs={}",
                                routeId,
                                exchange.getRequest().getMethod(),
                                statusCode,
                                signal,
                                elapsedMs
                        );
                    });
        });
    }
}
~~~

**Layer-by-layer explanation:**

1. `Mono.defer` initializes the timestamp and `routeId` **when subscription happens**. If an outer retry re-subscribes the Publisher, each attempt gets independent state.
2. `chain.filter(exchange)` represents downstream work. The filter **never calls `subscribe()` itself**.
3. `doOnSubscribe` observes subscription start, useful for counting attempts.
4. `doOnSuccess` runs when `Mono<Void>` completes normally; `ignored` will be `null`, not a response body.
5. `doOnError` logs only the **exception class**, avoiding messages that could contain tokens, query strings, or internal URLs. The error still propagates.
6. `doOnCancel` tracks downstream cancel requests; it does not turn them into HTTP 499/503 automatically.
7. `doFinally` runs for complete, error, **or cancel**, letting you emit one summary line per subscription. `signal` is a `SignalType` such as `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`.
8. `getStatusCode()` can return `null` when the response does not yet have a status. A `200` status on the response **does not prove every byte reached the client**.

This snippet emits minimal events. In production, use Micrometer/tracing and apply appropriate log sampling rather than emitting multiple DEBUG/INFO lines per request at high traffic. For dynamically generated routes, govern route IDs so client-controlled data never leaks into logs or metric labels.

### Does `doFinally` Always Mean the Request Succeeded?

**No.** `doFinally` answers "with which signal did this subscription terminate?". For example:

- `ON_COMPLETE`: The Publisher finished normally, **yet the backend may have returned HTTP 503 as a normal response**.
- `ON_ERROR`: The Publisher emitted an exception; the response may be uncommitted or partially sent.
- `CANCEL`: downstream canceled; possibly due to client disconnect, a timeout operator, a race, or another cause. You cannot always infer **client disconnect** from CANCEL alone.

With `Retry` or `CircuitBreaker`, **multiple subscriptions can occur for one operation**, each producing its own terminal signal. Never equate total `doFinally` calls with end-user HTTP requests without accounting for filter placement.

## 6. Proper Pre-Phase: When to Use `Mono.defer`?

A custom filter can perform a non-blocking check and decide:

~~~java
return Mono.defer(() -> {
    if (!featurePolicyAllows(exchange)) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }
    return chain.filter(exchange);
});
~~~

This is a **conceptual pattern**: `featurePolicyAllows` is a pre-designed helper, and you need to import `HttpStatus`. Any policy check requiring asynchronous data must compose Publishers rather than issuing blocking queries. In particular, **never replace Spring Security with a check on a client-supplied header** for admin access.

### Why Does `Mono.defer` Make Sense?

It guarantees:

- Pre logic runs **per subscription**, not when merely assembling the Publisher.
- Per-attempt state is recreated if the publisher is resubscribed.
- Exceptions thrown in the supplier are turned into `onError` by Reactor rather than escaping synchronously at assembly time, within Reactor's supplier handling.
- No side effects occur before a request is actually executed.

However, `Mono.defer` **does not make a blocking method non-blocking**. If `featurePolicyAllows` performs blocking JDBC, synchronous REST calls, or `Thread.sleep()`, the event loop can still stall. Use reactive APIs or intentionally isolate blocking work at an appropriate layer.

### Pre Logic Performing Asynchronous I/O

If policy evaluation requires data from an asynchronous reactive source, compose it:

~~~java
return policyService.check(exchange)
        .flatMap(allowed -> {
            if (!allowed) {
                exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        });
~~~

The snippet above is a **design pattern**, where `policyService.check(exchange)` is a hypothetical method returning `Mono<Boolean>`. Production systems must enforce **timeouts, caching, error policies, and authorization** for the policy service. If the policy source fails, never default to granting access to sensitive resources; **fail closed** is usually appropriate.

Do not use `flatMap` on `Mono<Void>` to run post logic because it **emits no `onNext` value**. To chain reactive work after downstream succeeds, use `then(...)`.

## 7. Post-Phase: After Success, Before Commit, and After Commit

The word "after" can refer to **three distinct moments**:

1. After the **downstream Publisher completes normally**.
2. **Right before the response commits**, before status/headers are sent.
3. After the **response has committed or started writing the body**, when many HTTP mutations are no longer valid.

**These three moments are not interchangeable.**

### 7.1. Post-Success with `then`

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                auditSuccessWithoutSensitiveData(exchange)));
~~~

`auditSuccessWithoutSensitiveData` is a hypothetical helper that must be fast and non-blocking. `then` waits for the preceding Publisher's **`onComplete`** before subscribing to the next step; it does not run on `onError` or cancellation.

Note: at the HTTP layer, **`onComplete` does not mean HTTP 2xx**. A backend returning 500 can produce a normally completed response. To measure "HTTP success", inspect the status code per your policy.

### 7.2. Registering `beforeCommit` Before Running Downstream

If Gateway policy needs to attach a response header, register the callback **before the response is written**:

~~~java
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class ResponseMarkerFilter implements GlobalFilter, Ordered {
    @Override
    public int getOrder() {
        return -200;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true");
                return Mono.empty();
            });

            return chain.filter(exchange);
        });
    }
}
~~~

`beforeCommit` registers a `Supplier<Mono<Void>>` invoked before the response commits. The callback must return a proper Publisher, never subscribe manually, and never block. `X-Gateway-Processed` is only illustrative; for security headers such as HSTS, CORS, or CSP, use official components and verify **which layer owns the header** rather than overwriting arbitrarily.

**Limitation:** `beforeCommit` runs only if the response actually reaches the commit step and the callback was registered in time. It is not guaranteed to run if the request is canceled before commit. If another filter already committed before you registered, it is too late to alter headers.

### 7.3. Why Is `doFinally` Not the Place to Modify Responses?

~~~java
// ANTI-PATTERN: may be too late to add headers or change status.
return chain.filter(exchange)
        .doFinally(signal ->
                exchange.getResponse().getHeaders()
                        .set("X-Finished", "true"));
~~~

By the time `doFinally` runs, status and headers may **already be committed**. Even if the Java mutation throws no exception, there is no guarantee the client receives that header. Use `beforeCommit` or dedicated response filters; keep `doFinally` for lightweight instrumentation and cleanup.

### Callback Ordering When Combining `beforeCommit` and `then`

~~~mermaid
sequenceDiagram
    participant G as Custom GlobalFilter
    participant D as Downstream routing
    participant R as ServerHttpResponse
    participant C as Client
    G->>R: Register beforeCommit callback
    G->>D: chain.filter(exchange)
    D->>R: Write status/headers/body
    R->>R: Invoke beforeCommit callback
    R-->>C: Response data
    D-->>G: Publisher completes
    G->>G: then(post-success) / doFinally
~~~

The diagram simplifies multi-flush response writes. **Post-success is not guaranteed to be the exact moment all bytes have been delivered over the underlying network to the client.** For deeper I/O timing, use version-appropriate HTTP server/Netty instrumentation.

## 8. Distinguishing Error Observation from Error Handling

Reactor provides several error-related operators with very different effects:

~~~java
// Observe only; the error keeps propagating.
return chain.filter(exchange)
        .doOnError(error -> recordErrorType(error.getClass()));
~~~

~~~java
// Replace errors of a specific type with another Publisher.
return chain.filter(exchange)
        .onErrorResume(SelectedUpstreamException.class,
                error -> safeFallback(exchange, error));
~~~

In the second snippet, `SelectedUpstreamException` and `safeFallback` are **placeholder** names. Do not copy them as built-in classes/APIs. For a handleable exception, `onErrorResume` can turn `onError` into `onComplete` if the fallback Publisher completes normally.

**Never use `onErrorResume(error -> Mono.empty())` as a blanket catch-all.** It can terminate the filter chain without writing a valid response/status, hide security errors, and trick observability into thinking requests succeeded.

### 8.1. Example: Narrow Connection Error Handling While Response Is Uncommitted

The snippet below translates only **direct `java.net.ConnectException`** into HTTP 503 with an empty body; all other errors continue propagating to the framework's error handler:

~~~java
import java.net.ConnectException;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class NarrowConnectionFallback {

    private NarrowConnectionFallback() {}

    public static GatewayFilter create() {
        return (exchange, chain) -> chain.filter(exchange)
                .onErrorResume(
                        ConnectException.class,
                        error -> respondUnavailable(exchange, error)
                );
    }

    private static Mono<Void> respondUnavailable(
            ServerWebExchange exchange,
            ConnectException originalError
    ) {
        ServerHttpResponse response = exchange.getResponse();

        // Do not overwrite status if headers/body have already been sent.
        if (response.isCommitted()
                || !response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE)) {
            return Mono.error(originalError);
        }

        response.getHeaders().setCacheControl("no-store");
        return response.setComplete();
    }
}
~~~

**This is a constrained technical example, not a full production fallback.** In Reactor Netty, connection failures may be wrapped or surfaced as other exception types. This code catches exact `ConnectException` only and may miss timeouts, TLS handshake failures, or `PrematureCloseException`. Real systems need clear exception policies based on route contracts and fault-injection tests.

More importantly:

1. **Auth errors (401/403)** belong to Spring Security and backend policies; never turn every exception into 503.
2. If the response **has already committed**, you cannot emit a new HTTP 503 on the same response. The example re-emits the original error so outer layers can handle/abort the connection realistically.
3. HTTP 500/503 **returned by the backend as normal HTTP responses** usually do not emit `onError`; custom filters must distinguish HTTP status codes from reactive errors.
4. If you want Resilience4j/circuit-breaker fallback, use the **CircuitBreaker GatewayFilter** and a proper `forward:` handler instead of writing a custom catch-all.
5. Never echo full exception messages in responses; messages can expose upstream URLs, hosts, queries, or credentials.

### 8.2. Errors Inside Filter Callbacks Themselves

A callback like:

~~~java
.doOnError(error -> {
    // If recordFailure() throws, it can mask the original exception.
    recordFailure(error);
})
~~~

must be designed **never to throw**. A failing logger, metric exporter, or formatter must not replace the root cause. Use tested instrumentation, bound its cost, and never perform blocking I/O inside `doOn...` callbacks.

### 8.3. Operator Ordering Changes What You Observe

Compare:

~~~java
// A: observe upstream error, then fall back.
return chain.filter(exchange)
        .doOnError(error -> recordUpstreamFailure())
        .onErrorResume(ConnectException.class,
                error -> respondUnavailable(exchange, error));
~~~

~~~java
// B: fall back first; outer doOnError only sees unrecovered errors.
return chain.filter(exchange)
        .onErrorResume(ConnectException.class,
                error -> respondUnavailable(exchange, error))
        .doOnError(error -> recordUnrecoveredFailure());
~~~

In A, telemetry records an upstream failure even when the fallback cleanly serves 503. In B, exceptions handled by fallback never reach the outer `doOnError`. Either way, you still need a **dedicated metric for fallback invocations**; neither `HTTP status` nor `doOnError` alone tells the whole story.

## 9. Cancellation: A Stop Request, Not an Exception

Cancellation is a normal part of Reactive Streams. For example:

- A client closes the browser tab or navigates away, dropping the HTTP connection mid-response.
- A `timeout` or `takeUntilOther` operator stops the upstream subscription.
- A `flatMap` branch or composite publisher no longer needs the result.
- Server shutdown or an orchestrator cancels running work.

**Never assume a one-to-one mapping** where every `CANCEL` means "client disconnect", nor that a client disconnect always surfaces as exactly one `CANCEL` at your filter's position. Depending on protocol, buffering, Netty layers, and timing, you may see `onError`, cancel, or another termination.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Gateway Reactor chain
    participant Filter as Custom GlobalFilter
    participant Upstream as Backend HTTP client
    Client->>Gateway: GET /api/reports/stream
    Gateway->>Filter: Subscribe
    Filter->>Upstream: Subscribe / start request
    Upstream-->>Client: HTTP response bytes (via Gateway)
    Client--xGateway: Connection closed / request abandoned
    Gateway->>Filter: cancel (possible outcome)
    Filter->>Upstream: cancel propagates upstream
    Note over Filter,Upstream: Cleanup / socket handling depend on state
~~~

### 9.1. How Do `doOnCancel` and `doFinally(CANCEL)` Differ?

~~~java
return chain.filter(exchange)
        .doOnCancel(() -> recordCancelRequested())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                recordSubscriptionCancelled();
            }
        });
~~~

This requires importing `reactor.core.publisher.SignalType`; the `record...` helpers illustrate instrumentation. `doOnCancel` fires when cancellation is requested. `doFinally` gives you the **subscription termination signal type**, making it suitable for unified accounting across `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`.

Do not increment the same "cancel" counter in both `doOnCancel` and `doFinally(CANCEL)` unless you intend to **double-count**. You can use `doOnCancel` for detailed logs and `doFinally` for terminal counts by signal type.

### 9.2. Why Cleanup Should Not Rely Solely on `doOnError`

If you open a per-subscription resource (e.g., a handle to an external subsystem) and only clean up on error, successful or canceled requests will leak that resource.

~~~java
// ANTI-PATTERN: misses success and cancellation.
return chain.filter(exchange)
        .doOnError(error -> releaseResource());
~~~

For **synchronous, ultra-fast, non-blocking** cleanup, consider `doFinally`:

~~~java
return chain.filter(exchange)
        .doFinally(signal -> releaseFastLocalResource());
~~~

However, if releasing the resource requires **asynchronous reactive I/O**, never kick it off with `releaseMono.subscribe()` inside `doFinally`. Manage it with the appropriate operator, such as `Mono.usingWhen`, when the lifecycle truly owns that resource:

~~~java
// Pseudocode illustrating ownership scope; resourceFactory is a custom API.
return Mono.usingWhen(
        resourceFactory.acquire(),
        resource -> chain.filter(exchange),
        resource -> resourceFactory.release(resource),
        (resource, error) -> resourceFactory.release(resource),
        resource -> resourceFactory.release(resource)
);
~~~

**Do not use this snippet to manually close connection pools, `ServerWebExchange`, or `DataBuffer`s owned by Gateway/Netty.** It only illustrates a **custom resource explicitly acquired by your component** with Publisher-returning lifecycle methods. `usingWhen` lets you define cleanup branches for completion, error, and cancellation.

### 9.3. Cancellation Does Not Equal Rollback

If Gateway already sent `POST /orders` and Orders committed to its database before the client disconnected, canceling at the Gateway **does not roll back** the service transaction. Never automatically retry a write operation just because you observed `CANCEL`. You need **idempotency keys, transaction state, and an explicit retry policy**.

With SSE, WebSockets, or NDJSON, cancellation also does not guarantee which events were flushed; design reconnect/resume support so clients handle partial receipts without duplicating events.

## 10. Error Paths When the Response Has Already Committed

In HTTP, status and headers can only change **before the response commits**. If Gateway begins streaming:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

~~~

and upstream then fails, you **cannot go back and send**:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error":"UPSTREAM_UNAVAILABLE"}
~~~

on the same HTTP response that already sent status 200 and data. A custom `onErrorResume` returning JSON at that point can cause protocol errors or append malformed content into the stream.

### Safe Handling Principles

1. **Before commit:** Choose an appropriate fallback status/body if the exception is properly classified and no response content has been written.
2. **After commit:** Do not alter status; let the stream error/close per HTTP semantics, and define client reconnect/resume when business logic needs it.
3. **On cancel:** Avoid trying to write a new response to a departed client; only clean up owned resources.
4. **On retry:** Never arbitrarily resubscribe to an HTTP exchange that has already written a response or whose request body is non-replayable.

`exchange.getResponse().isCommitted()` indicates state at the instant checked, though **races** between async steps are still possible. Therefore commit/status logic must use the proper response APIs rather than attempting late mutations in `doFinally`.

## 11. DataBuffer, Request/Response Bodies, and Backpressure

A custom filter occasionally needs to inspect or transform request/response bodies. In WebFlux, bodies are typically represented as `Flux<DataBuffer>`, arriving incrementally under backpressure. This area is error-prone if written like synchronous Servlet "read everything and write back" code.

### Why Is a Body Not Like a String You Can Read Infinitely Many Times?

| Action | Risk |
| --- | --- |
| Read body first and let downstream read again | Publisher/body may already be consumed, leaving downstream with an empty body |
| Cache body without limits | Heap/off-heap memory spikes, risking OOM |
| Retain pooled `DataBuffer` without proper release | Reference-count leaks or memory corruption |
| Manually call `subscribe()` to log body | Two consumers race, breaking backpressure/cancellation |
| Dump login/JSON bodies into logs | Leaks passwords, access tokens, or personal data |
| Attempt body replay after response commit | Violates HTTP contract, causes duplicate side effects |

**Do not treat `doFinally` as sufficient to release every touched `DataBuffer`.** With reference-counted buffers, you must know exactly who holds ownership, who retains, who releases, and how discard/cancel behave. Use `DataBufferUtils.release(...)`, `doOnDiscard`, and request/response decorators **following framework-supported patterns**; never release a buffer downstream still needs.

### Correct Architecture When Transforming Bodies

~~~mermaid
flowchart LR
    I["Body Flux<DataBuffer>"] --> D["Decorator / supported body filter"]
    D --> T["Transform / validate, bounded"]
    T --> B["Body forwarded with backpressure"]
    B --> U["Upstream HTTP client"]
    T -. "cancel/error" .-> C["Release owned buffers"]
~~~

If you only need to add headers, measure latency, or track status codes, **do not touch the body**. Use `AddRequestHeader`, `SetResponseHeader`, or appropriate callbacks. When JSON body transformation is needed, prefer supported GatewayFilter factories like `ModifyRequestBody`/`ModifyResponseBody` for your release line, while setting size limits and testing streaming.

### Where Is the Response Body in `Mono<Void>`?

The `Mono<Void>` returned by `GatewayFilter` is a **completion signal**, not the body content. JSON/SSE streams flow through `ServerHttpResponse.writeWith(Publisher<? extends DataBuffer>)` and HTTP response decorators. Therefore:

~~~java
return chain.filter(exchange)
        .doOnSuccess(body -> {
            // body is null in Mono<Void>, not the JSON response.
        });
~~~

Do not use this to parse responses. Intercepting bodies requires decorator APIs, buffer management, and dedicated security policies.

## 12. Distinguishing `GlobalFilter` and `GatewayFilterFactory`

Not every requirement needs a **`GlobalFilter`**. For policies targeting only selected routes, build a **`GatewayFilterFactory`** to manage per-route configuration. Your choice determines execution scope:

| Choice | Typical scope | When to use |
| --- | --- | --- |
| `GlobalFilter` | Requests matched to a Gateway route and entering the Gateway filter chain | Shared route telemetry, common header normalization, consistent technical policies |
| `GatewayFilter` | A single route or routes configured with the filter | Route-specific policy, response marker, or transformation |
| `AbstractGatewayFilterFactory<Config>` | Defines how to construct parameterized `GatewayFilter`s from YAML/DSL | Reusing logic with per-route configuration and validation |
| `WebFilter` | WebFlux layer; can cover HTTP requests that bypass Gateway routes | Authentication/authorization or cross-cutting logic outside route lifecycles |

**Point to remember:** `GlobalFilter` does **not** run on **every request arriving at the HTTP port**. If a request matches no route, it may skip `FilteringWebHandler` and never hit custom GlobalFilters. Internal WebFlux controllers, actuators, or other handlers may also follow separate lifecycles. For authentication/authorization, prefer **Spring Security WebFlux WebFilters** over building security solely with GlobalFilters.

### Factory Example Measuring Signals by Group Tag

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class LifecycleTagGatewayFilterFactory
        extends AbstractGatewayFilterFactory<LifecycleTagGatewayFilterFactory.Config> {

    private static final Logger log =
            LoggerFactory.getLogger(LifecycleTagGatewayFilterFactory.class);

    public LifecycleTagGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        String tag = config.getTag();

        // Only accept bounded tags supplied by trusted configuration.
        if (tag == null || !tag.matches("[a-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid lifecycle tag");
        }

        return (exchange, chain) -> Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);
                        log.debug("tag={} signal={} elapsedMs={}",
                                tag, signal, elapsedMs);
                    });
        });
    }

    public static class Config {
        private String tag;

        public String getTag() {
            return tag;
        }

        public void setTag(String tag) {
            this.tag = tag;
        }
    }
}
~~~

You can use that factory in a route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - name: LifecycleTag
                  args:
                    tag: catalog
~~~

The `LifecycleTagGatewayFilterFactory` naming convention enables the filter name `LifecycleTag` in Gateway releases supporting this factory pattern. Route `lb://catalog-service` needs a load balancer and `ServiceInstance` source; for local experiments, you can swap in a valid backend URI.

**Note:** Factories can be instantiated/configured when route definitions load, while `apply` builds the route filter. Per-request Publishers must only be created inside the `(exchange, chain) -> ...` lambda. Never store `ServerWebExchange` or request-specific state inside `Config` or singleton factory fields, as that leaks data across users and concurrent requests.

### Factory-Specific Ordering

If a route requires a filter to run before/after another filter, use Gateway's ordering mechanism or `OrderedGatewayFilter` per your version's API, and test it at runtime. **Do not assume YAML list order alone suffices** when GlobalFilters and factory-created GatewayFilters are combined.

## 13. Reactor Context, `ServerWebExchange`, and Per-Request Data

A request can cross multiple asynchronous boundaries. Reactor provides **Context** attached to a subscription, while `ServerWebExchange` holds HTTP data and request attributes. They serve different roles.

| Storage location | Characteristics | Suitable example |
| --- | --- | --- |
| Local variables inside `Mono.defer` | One state per subscription | Timestamps, per-attempt counters |
| `ServerWebExchange.getAttributes()` | Data attached to the HTTP exchange | Selected route, target URL, shared filter metadata |
| Reactor `Context` | Metadata along the subscriber chain | Standardized trace context / technical correlation |
| Raw `ThreadLocal` / MDC | Data tied to the current thread | **Unreliable** across async scheduling without context propagation |
| Singleton `GlobalFilter` fields | State shared across all requests | Immutable clients/metric registries, **never per-request variables** |

Example reading Reactor Context inside a Publisher:

~~~java
return Mono.deferContextual(contextView -> {
    String traceGroup = contextView.getOrDefault("trace.group", "unknown");
    return chain.filter(exchange)
            .doFinally(signal ->
                    recordTraceGroup(traceGroup, signal));
});
~~~

`recordTraceGroup` is an example helper. The snippet only reads an existing key from context; if not populated by upstream instrumentation, it defaults to `unknown`. For real tracing, use context propagation from **Micrometer Tracing, OpenTelemetry, or Spring** rather than inventing a custom trace header format.

### Never Copy Tokens into Reactor Context Just for Easier Logging

Reactor Context propagates across many operators and libraries. Placing raw `Authorization` headers, session cookies, refresh tokens, request bodies, or secret-bearing URLs into Context only widens exposure. When a filter needs identity to make decisions, read it from the **verified Spring Security context** or an approved contract; never trust a client-supplied `X-User-Id` header as identity.

### Why Can `ThreadLocal`/MDC Break?

In WebFlux, multiple requests share Reactor Netty event-loop threads and can hop schedulers during execution. A `ThreadLocal` populated in the pre phase is not guaranteed to hold the same value when `doFinally` runs unless proper context propagation is enabled. Never retain `ServerWebExchange` in a long-lived `ThreadLocal` either, as that causes **cross-user log mixing** or data leaks.

## 14. Retry, Circuit Breaker, and Resubscription Change Callback Counts

In Spring Cloud Gateway, routes can use `Retry` or `CircuitBreaker`. A lifecycle-measuring filter must know whether it **wraps the whole HTTP operation or each upstream attempt**.

~~~mermaid
flowchart TD
    Req["One inbound HTTP request"] --> Retry["Retry filter"]
    Retry --> Attempt1["Attempt #1: subscribe downstream"]
    Attempt1 --> Err["onError or retry-matched status"]
    Err --> Wait["Backoff"]
    Wait --> Attempt2["Attempt #2: resubscribe downstream"]
    Attempt2 --> Done["Success or budget exhausted"]
    Done --> Resp["Final HTTP response"]
~~~

If `SafeLifecycleGlobalFilter` or a `GatewayFilter` sits **inside** the Publisher segment resubscribed by Retry, you may observe:

~~~text
Attempt 1 -> doFinally(ON_ERROR)
Attempt 2 -> doFinally(ON_COMPLETE)

One inbound request can produce two doFinally callbacks.
~~~

Conversely, if instrumentation wraps the **outer retry loop**, it sees one final `ON_COMPLETE` without tracking each attempt separately. **Both measurements are useful**, but they measure different units:

- **request latency / result**: total time and final status seen by the client.
- **attempt latency / error**: each upstream call, including retries or circuit-breaker-rejected calls.

An OPEN `CircuitBreaker` can prevent downstream subscription altogether. If custom instrumentation sits **after the circuit breaker**, it will not run on rejected requests. If placed outside, it observes fallbacks/short-circuits. Always analyze **filter order** and test under both CLOSED and OPEN states.

### Caution with `Mono.defer` and Resubscription

`Mono.defer` re-executes its supplier on every new subscription. If the pre phase performs **DB writes, email sends, charges, or order creation**, an outer retry can **repeat side effects**. Never put side-effecting business logic inside a custom GatewayFilter just because it "runs before routing".

When retry logic is needed, prefer the **`Retry` GatewayFilter Factory** with explicit method/status/exception rules, backoff, deadlines, and idempotency. Never wrap `chain.filter(exchange)` in manual `repeat()` or `retryWhen()` without verifying body replay, response commits, cancellation, and business contracts.

## 15. Security When Handling Errors and Cancellations

Errors and cancellations often prompt operators to raise debug logging. That is precisely when tokens and user data leak into logs and traces.

**Avoid:**

~~~java
return chain.filter(exchange)
        .doOnError(error -> {
            log.error("Failed exchange={} exception={}", exchange, error);
        });
~~~

Aside from dumping full stack traces, string representations of `exchange` or exception messages can contain raw URLs/queries, tokens, or internal addresses depending on version/logger. A fallback response must also never echo `Authorization` headers or stack traces back to clients.

**Prefer** logging controlled metadata:

~~~text
route=catalog-api method=GET status=503
terminal=ON_ERROR errorType=ConnectException
elapsedMs=148
~~~

For `CANCEL`, never log "client maliciously disconnected" from the cancel signal alone; log `terminal=CANCEL` and combine server/network instrumentation when diagnosing causes.

### Boundaries a GlobalFilter Cannot Protect on Its Own

1. **Spring Security WebFilter** must enforce authentication/authorization at the proper layer; GlobalFilter cannot cover all HTTP endpoints.
2. **TLS/mTLS** governs trust and confidentiality of upstream connections, not `doOnSuccess`.
3. **Service discovery** can dynamically change `lb://service-id` targets; never log or forward tokens to unauthorized instances.
4. **Rate limiting / circuit breaker / retry** can short-circuit the chain; telemetry must reflect which branch actually ran.
5. **Gateway fallback** using `forward:` must never expose internal endpoints or bypass backend authorization.

If mandatory security auditing is required before allowing an action, **never entrust critical auditing to a best-effort `doFinally` callback** without delivery guarantees. Use a transaction/outbox or a reliable audit service with an explicit failure policy.

## 16. Testing Pre and Post with `StepVerifier`

Reactor callbacks run asynchronously, making visual log inspection insufficient to prove ordering. **`reactor-test`** provides `StepVerifier` to subscribe to Publishers and assert `onComplete`, `onError`, or cancellation.

### 16.1. Verifying `pre → downstream → post`

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PrePostGatewayFilterTest {

    @Test
    void preRunsBeforeDownstreamAndPostRunsAfterSuccess() {
        List<String> events = new ArrayList<>();

        GatewayFilter filter = (exchange, chain) ->
                Mono.defer(() -> {
                    events.add("pre");
                    return chain.filter(exchange)
                            .then(Mono.fromRunnable(() -> events.add("post")));
                });

        GatewayFilterChain downstream = exchange ->
                Mono.fromRunnable(() -> events.add("downstream"));

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, downstream))
                .verifyComplete();

        assertThat(events)
                .containsExactly("pre", "downstream", "post");
    }
}
~~~

**Why is this test valuable?**

1. When building the filter, `Mono.defer` has not yet run `events.add("pre")`.
2. `StepVerifier` subscribes, triggering the pre logic.
3. Downstream `Mono.fromRunnable` appends `downstream`.
4. Because downstream completes normally, `then` appends `post`.
5. The assertion verifies exact ordering. If downstream errors, `post` will not be added; test that case separately.

In this small test, `ArrayList` suffices because execution stays single-threaded without scheduler hops. If tests cross threads, use thread-safe collections or explicit synchronization.

### 16.2. Verifying Errors Are Not Swallowed by `doOnError`

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ErrorSignalGatewayFilterTest {

    @Test
    void doOnErrorObservesButDoesNotRecoverTheError() {
        AtomicInteger errorsSeen = new AtomicInteger();

        GatewayFilter filter = (exchange, chain) ->
                chain.filter(exchange)
                        .doOnError(error -> errorsSeen.incrementAndGet());

        GatewayFilterChain failingDownstream = exchange ->
                Mono.error(new IllegalStateException("test-only"));

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, failingDownstream))
                .expectError(IllegalStateException.class)
                .verify();

        assertThat(errorsSeen.get()).isEqualTo(1);
    }
}
~~~

This test proves `doOnError` observed the error while the final subscriber still received `onError`. If replaced with an `onErrorResume` returning a completing Publisher, the `StepVerifier` expectation would change accordingly.

### 16.3. Verifying Cancellation Yields `SignalType.CANCEL`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CancelSignalGatewayFilterTest {

    @Test
    void finallyObservesCancelWithoutTurningItIntoError() throws Exception {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();
        CountDownLatch finished = new CountDownLatch(1);

        GatewayFilter filter = (exchange, chain) ->
                chain.filter(exchange)
                        .doFinally(signal -> {
                            finalSignal.set(signal);
                            finished.countDown();
                        });

        GatewayFilterChain neverCompletes = exchange -> Mono.never();

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/stream").build());

        StepVerifier.create(filter.filter(exchange, neverCompletes))
                .thenCancel()
                .verify();

        assertThat(finished.await(1, TimeUnit.SECONDS)).isTrue();
        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }
}
~~~

`Mono.never()` never completes or errors on its own, so `StepVerifier.thenCancel()` exercises the cancellation branch. `CountDownLatch` in the **test thread** avoids racing the assertion before `doFinally` finishes; **never use blocking awaits like this on the Reactor Netty event loop in production**.

This is a Reactor signal test, **not a full simulation of a TCP client disconnect**. To verify real lifecycle behavior when clients drop SSE/WebSocket connections, run integration tests with Gateway and a controlled backend/proxy or stub.

## 17. Testing `beforeCommit` and Committed Responses

A frequent requirement: "Add an audit header to every response proxied by Gateway." You must verify the header is added **before the response commits**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class BeforeCommitGatewayFilterTest {

    @Test
    void headerIsAddedBeforeResponseCompletes() {
        GatewayFilter filter = (exchange, chain) -> {
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true");
                return Mono.empty();
            });
            return chain.filter(exchange);
        };

        GatewayFilterChain downstream = exchange ->
                exchange.getResponse().setComplete();

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, downstream))
                .verifyComplete();

        assertThat(
                exchange.getResponse().getHeaders()
                        .getFirst("X-Gateway-Processed")
        ).isEqualTo("true");
    }
}
~~~

This test uses `MockServerWebExchange` and inspects the mock response; it does not prove every reverse proxy or CDN preserves that header out to the Internet. Add HTTP integration tests verifying the full path across ingress, response filters, and backends.

**Do not use this test to claim `doFinally` can validly modify headers**: downstream `setComplete()` is the commit point. Once committed, post or finally callbacks may have no chance to alter status/headers.

## 18. Comprehensive Lifecycle Test Matrix

| Scenario | Downstream Publisher | Callbacks expected | What not to expect |
| --- | --- | --- | --- |
| Normal success | `Mono.empty()` | `doOnSuccess`, `doFinally(ON_COMPLETE)` | `doOnError`, `doOnCancel` |
| Error in route/filter | `Mono.error(ex)` | `doOnError`, `doFinally(ON_ERROR)` | `doOnSuccess` |
| Explicit cancel | `Mono.never()` then cancel | `doOnCancel`, `doFinally(CANCEL)` | `doOnError`, `doOnSuccess` |
| Error recovered by fallback | `onErrorResume` returning `Mono.empty()` | Observer before fallback sees error; observer after fallback may see complete | All observers seeing the same terminal signal |
| Backend returns HTTP 503 normally | HTTP 503 response + Publisher completes | `doOnSuccess`, `doFinally(ON_COMPLETE)` can run | Automatic `doOnError` solely from status 503 |
| Error after commit | Partial HTTP 200 sent + Publisher errors | `doOnError`, `doFinally(ON_ERROR)` depending on position | Turning status 200 into 503 |
| Retry with 2 attempts | Downstream Publisher resubscribes | Two pre/finally pairs if filter sits inside retry scope | Only one callback per user operation |
| Circuit breaker OPEN | Downstream not subscribed on blocked branch | Outer observer sees fallback/short-circuit outcome | Inner downstream filter always running |
| No Gateway route matched | No Gateway `FilteringWebHandler` for that route | Appropriate WebFlux/`WebFilter` if present | Custom `GlobalFilter` guaranteed to run |
| Client closes HTTP stream | Depends on Netty/transport and timing | May see cancel or error in chain | Every disconnect always producing exactly one `CANCEL` |

### Evidence from Integration Tests

Configure a backend stub capable of returning 200/503, delays, connection resets, or partial streams:

1. Send requests through the route carrying your custom filter.
2. Verify the **route ID** and how many times the backend received the request.
3. Verify success/error/cancel callbacks under the created conditions.
4. Check status, headers, and body at the **client**, not only on a mock exchange.
5. With retry or circuit breakers, measure subscriptions/attempts separately.
6. On cancel, verify filter-owned resources are cleaned up; do not assume TCP sockets close within the same millisecond.
7. Ensure callbacks never record tokens, cookies, sensitive queries, or full bodies in telemetry.

**Run fault-injection tests strictly in controlled test environments.** You do not need a production outage to verify `doFinally`.

## 19. Diagnosing Common Custom Filter Bugs

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| "request complete" logs before backend replies | Logged at assembly right after `chain.filter` | Use `then`, `doOnSuccess`, or `doFinally` per signal |
| `doOnNext` never runs despite JSON body | Filter returns `Mono<Void>`, emitting no `onNext` | Observe completion/status; bodies require proper decorators |
| `doOnSuccess` throws `NullPointerException` | Callback tries to read a value from `Mono<Void>` | Never treat the `null` argument as a response body |
| Error occurs yet post-success doesn't run | `then` only executes when upstream completes | Use `doFinally` to observe all terminal outcomes |
| Client disconnects yet `doOnError` doesn't fire | Cancellation is not `onError` | Observe `doOnCancel`/`doFinally(CANCEL)` and test real transport |
| Filter counts latency twice for one request | Retry resubscribes downstream, or both success and finally log | Separate operations vs. attempts; use distinct counters |
| Response header set yet client doesn't see it | Set in `doFinally` after commit or overwritten by another filter | Use `beforeCommit`; inspect order and response filters |
| Fallback 503 not sent | Response already committed or wrong exception class | Check `isCommitted()`, exception chain, and HTTP contract |
| HTTP 500 fails to trigger `doOnError` | Backend returned a normal response with status 500 | Observe status separately; use CircuitBreaker `statusCodes` where appropriate |
| Spring Security 401/403 missing from GlobalFilter telemetry | Security WebFilter rejected before Gateway routing | Instrument WebFlux/Spring Security or HTTP server at that layer |
| Filter skips `/unknown` | No Gateway route matched | Check route predicates or use `WebFilter` if covering all HTTP |
| `NullPointerException` on `getStatusCode().value()` | Response status not yet set | Check for `null` first |
| Request A data appears in Request B logs | Per-request state stored in singleton field or bad `ThreadLocal` | Use `Mono.defer`, exchange/context, and proper propagation |
| Memory grows on large bodies or cancels | Unbounded `DataBuffer` caching/joining, bad retain/release | Bound body sizes, use standard factories/decorators, test for leaks |
| Gateway hangs under load despite fast backend | `block()`, JDBC, sleep, or blocking I/O in callback | Use reactive APIs or isolate blocking work by design |
| Error counter spikes while client success rate is fine | Observer sits before `onErrorResume` or fallback returns 200 | Separate raw upstream errors, fallback counts, and final status |
| Circuit OPEN yet custom metric stays zero | Custom filter sits inside the unsubscribed downstream branch | Adjust measurement point/order; track breaker rejections separately |
| One request proxied twice | Manual `subscribe()` or unguarded second `chain.filter` call | Return one composed Publisher; never manage subscriptions manually |

### Layer-by-Layer Investigation Checklist

1. **Route selection:** Which route did `RoutePredicateHandlerMapping` pick? With no route, GatewayFilters do not run.
2. **Filter order:** Does the custom filter sit before or after `Retry`, `CircuitBreaker`, `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter`, and routing filters?
3. **Assembly vs. subscription:** Is pre logic outside or inside `Mono.defer`? Do retries trigger resubscription?
4. **Reactive signal:** Did the publisher complete, error, or cancel? Was an error handled by another operator's `onErrorResume`?
5. **HTTP response state:** Has it committed yet? What is the real final status? Was a partial response already sent?
6. **Transport:** Did the backend return a normal response, drop TCP, time out, fail TLS, or did the client disconnect?
7. **Ownership:** Who owns `DataBuffer`s, connections, sessions, and filter resources? Are there leaks or missed cancellations?
8. **Instrumentation:** Are metrics counting HTTP requests, upstream attempts, or subscriptions? Is sensitive data leaking into logs?

Following this sequence prevents knee-jerk mistakes like **adding retries** when a filter is actually subscribing twice, or **raising timeouts** when the event loop is blocked.

## 20. Callback Performance and Reliability in Production

Custom filters sit on the hot request path, so even a tiny callback can create heavy pressure when Gateway handles thousands of requests per second.

### Never Block Inside Callbacks

The following **must never run** directly on the Reactor Netty event loop:

~~~java
// ANTI-PATTERN:
return chain.filter(exchange)
        .doFinally(signal -> {
            Thread.sleep(100);             // Example; wouldn't even compile due to checked exception.
            jdbcRepository.save(...);       // Blocking I/O.
        });
~~~

This is **anti-pattern pseudocode**, intentionally non-compiling. In reality, any sleep, blocking JDBC call, synchronous network client, or `fsync` in a callback can stall the event loop and slow down unrelated requests. Never run critical auditing, billing, or DB updates via ad-hoc `doFinally` hooks.

When you must compose reactive work after downstream completes:

~~~java
return chain.filter(exchange)
        .then(nonBlockingAuditPublisher(exchange));
~~~

`nonBlockingAuditPublisher(exchange)` is an application-defined helper returning a Publisher **without logging secrets**. Remember the HTTP response may already be committed by then; if the audit fails, the overall filter signal can become `onError` even though a success response was already sent. For mandatory audits, enforce/persist the decision **before** allowing the action or use an outbox/transaction; for best-effort telemetry, use instrumentation designed never to break the request.

### Avoid Excessive Logging and Unbounded Metric Labels

| Signal | Do | Avoid |
| --- | --- | --- |
| Route ID | Use IDs from governed routes | Arbitrary route IDs from client input |
| Outcome | `ON_COMPLETE`, `ON_ERROR`, `CANCEL` | Putting full exception messages in labels |
| HTTP status | Numeric status when available | Attaching raw bodies to metrics |
| Latency | Properly configured histograms/timers | Logging full payloads per request |
| Errors | Normalized exception class | Tokens, JWT payloads, query strings, or headers |
| Trace | Valid trace ID with bounded retention | Session IDs or `Authorization` as correlation ID |

Once sensitive data enters logs or exporters, stripping `Authorization` from the outbound HTTP request **does not erase the logged copy**. Enforce a log allowlist at collection time and protect logs, traces, and APM storage.

### Never Treat `SignalType` as an HTTP Status

`ON_COMPLETE` does not mean HTTP 200, `ON_ERROR` does not mandate HTTP 500, and `CANCEL` is not a universal HTTP 499 across all layers. Some servers/proxies use internal log codes for client disconnects, yet **never call `response.setStatusCode(499)` from `doFinally`**.

To measure reliability, track **two dimensions**:

- **Reactive lifecycle:** terminal signal, resubscriptions, cleanup.
- **HTTP outcome:** sent status, bytes/streams, upstream/fallback, connections/cancellations.

Combining both explains why a route can report HTTP 200 while a user reports an incomplete download, or why HTTP 503 is cleanly returned without the Reactor chain emitting an exception.

## 21. Hands-On Lab: Building a Lifecycle-Observing Filter

**Scenario:** You are building a Gateway for Catalog and Reports. Catalog returns fast JSON, while Reports exposes a long-lived SSE endpoint. Goal: accurately track pre/post/error/cancel without blocking, leaking tokens, or altering HTTP status after commit.

### Part A — Build the Filter

1. Use **Gateway Server WebFlux** with a BOM-compatible dependency and a `/api/catalog/**` route pointing to a backend stub.
2. Add `SafeLifecycleGlobalFilter` from section 5 with an intentional order.
3. On one specific route, try `LifecycleTagGatewayFilterFactory` from section 12 to compare scopes.
4. Emit log metadata containing route ID, method, status, `SignalType`, and elapsed time; **never log `Authorization`, `Cookie`, or raw query strings**.
5. Register a response marker via `beforeCommit` and verify the header using an HTTP client.

### Part B — Verify Signals

| Case | Backend stub or test publisher | What to prove |
| --- | --- | --- |
| Returns JSON 200 | `Mono.empty()` or HTTP 200 | pre before downstream; post-success and finally complete |
| Throws exception | `Mono.error(...)` | `doOnError` invoked; error is not swallowed |
| HTTP 503 with body | Backend returns HTTP 503 response | `doOnError` does not necessarily run; status tracked separately |
| Mid-flight cancel | `Mono.never()` with `StepVerifier.thenCancel()` | `doFinally(CANCEL)`, not `onError` |
| SSE client disconnect | Slow stub stream, client closes connection | Observe real Netty cancel/error behavior |
| Error after commit | Stub sends partial body then resets | No attempt to change status to 503 or write JSON fallback |
| `beforeCommit` | Downstream `setComplete()` | Header set before commit |
| Retry two attempts | Stub fails first, succeeds second | Callbacks counted by filter position/request/attempt |
| Circuit breaker OPEN | Breaker blocks upstream | Filter on the unsubscribed branch does not run |

### Part C — Audit Code and Lifecycle

1. Confirm there is no `.subscribe()`, `.block()`, `Thread.sleep()`, or blocking JDBC in the filter.
2. Confirm `doOnNext` is not used on `Mono<Void>` and `doOnSuccess`'s `null` value is never dereferenced.
3. For self-acquired resources, test all of success/error/cancel; never dispose framework-owned resources.
4. If using a body decorator, verify backpressure, size limits, and reference-count lifecycles with appropriate tooling.
5. Never store `ServerWebExchange` in singleton fields or global mutable maps lacking lifecycle cleanup.
6. Keep `StepVerifier` tests and HTTP integration tests distinct so reactive terminal signals are not confused with real HTTP responses.

### Part D — Try an Anti-Pattern and Fix It in the Lab

In a test environment **containing no real data**:

1. Place a "success" log immediately after `chain.filter(exchange)` and compare it against logging when subscription completes.
2. Move it into `doOnSuccess` or `then` and compare timestamps.
3. Switch downstream to `Mono.error(...)` to verify `then` does not run while `doFinally(ON_ERROR)` does.
4. Use `Mono.never()` and `StepVerifier.thenCancel()` to observe that cancellation does not become `onError`.
5. Try adding a header inside `doFinally` after downstream commits, confirm it is unreliable, and switch to `beforeCommit`.
6. If Retry is enabled in the lab, observe whether callbacks fire once per subscription and adjust measurement targets accordingly.

### Passing Criteria

You can explain and demonstrate:

- **Pre** executes at subscription time, not assembly time.
- **Post-success** runs only after downstream completes normally, whereas **`doFinally`** receives complete/error/cancel.
- **`doOnError`** observes and forwards errors; **`onErrorResume`** substitutes an outcome when permitted, without hiding 401/403 or modifying committed responses.
- **Cancel** is a stop-request signal, not synonymous with an exception or side-effect rollback.
- **`beforeCommit`** updates response headers at the right moment; bodies are handled separately with safe buffer lifecycles.
- Metrics/logs separate **HTTP requests, retry attempts, and Reactor subscriptions**, never leak sensitive data, and never block the event loop.

## 22. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Calling `chain.filter(exchange)` means the backend has already replied." | It returns a Publisher; you must observe when that Publisher is subscribed and terminates. |
| "Logging right after `chain.filter` is the post phase." | That is assembly-time Java code, before downstream has necessarily finished. |
| "`Mono<Void>` holds the body for `doOnNext` to read." | `Mono<Void>` normally emits no item; bodies flow through separate HTTP response publishers. |
| "`doOnError` handles and swallows errors." | It only observes; fallback requires composing a controlled `onErrorResume`. |
| "Client cancellation emits `onError`." | Cancel differs from `onError`; use `doOnCancel`/`doFinally` and test real transport. |
| "Inside `doFinally` you can always edit status/headers." | When it runs, the response may already be committed; use `beforeCommit` when needed. |
| "`doFinally(ON_COMPLETE)` means the client received HTTP 200." | 4xx/5xx responses also complete normally; network delivery is separate as well. |
| "`GlobalFilter` runs on every HTTP request." | It belongs to Gateway's `FilteringWebHandler` for matched routes, not app-wide `WebFilter`s. |
| "YAML order alone dictates every callback." | Filter ordering, operator placement, and resubscriptions all matter. |
| "One `doFinally` equals one user request." | Retry can trigger multiple subscriptions and callbacks. |
| "With `onErrorResume`, falling back on every error is safe." | Classify errors, check commit state, preserve auth, idempotency, and budgets. |
| "Cleanup is only needed on `onError`." | Success and cancellation also require cleanup according to ownership. |
| "`Mono.defer` automatically makes blocking code safe." | It only defers execution; it does not turn blocking calls into non-blocking ones. |
| "Putting tokens in MDC/Reactor Context for debugging is harmless." | It widens secret propagation/logging exposure; use safe metadata and Security context. |

## 23. Summary

- In **Spring Cloud Gateway Server WebFlux**, custom `GlobalFilter` and `GatewayFilter` implementations return **`Mono<Void>`**, representing the asynchronous processing lifecycle rather than a response body.
- **Pre** runs before downstream; **post** usually unwinds in reverse order as nested filters wrap one another. Use `Mono.defer` to attach per-subscription state and start times instead of running prematurely at assembly.
- `doOnSuccess` observes normal completion; `doOnError` observes errors; `doOnCancel` observes cancel requests; **`doFinally` covers complete, error, and cancel**.
- **`onErrorResume` replaces error signals with another Publisher**, so keep it narrow, check response commit state, and honor HTTP contracts. A backend returning HTTP 503 normally does not become a Reactor `onError`.
- **Response headers/status must be handled before commit**; `beforeCommit` fits headers, whereas `doFinally` fits lightweight instrumentation/cleanup rather than modifying responses.
- **Cancellation does not prove the backend rolled back**; never automatically retry side-effecting requests or partially streamed responses.
- Respect `DataBuffer`, backpressure, memory limits, non-blocking I/O, Reactor Context, and resource lifecycles when handling bodies or async cleanup.
- With `Retry` and `CircuitBreaker`, subscription counts and executed downstream branches change; measure requests and attempts separately, verify filter ordering, and keep tokens/PII out of telemetry.
- Use **`StepVerifier`**, mock exchanges, and backend stubs to prove pre/post/error/cancel, response commits, and attempt counts—never rely solely on logs or a final HTTP 200.

A solid custom filter does not merely "work when requests succeed" — it **preserves correctness across the entire Reactor chain during errors, cancellations, retries, and committed responses**, without blocking the event loop or exposing sensitive data.
