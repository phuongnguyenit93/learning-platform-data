# Acting Before the Response Is Committed in Spring Cloud Gateway

In **SPRING_CLOUD_GATEWAY**, many filters need to modify the **HTTP response** before sending it to the client: adding trace headers, setting cache policies, stripping unwanted headers, attaching version metadata, or standardizing error responses. Timing matters greatly. Once a response is **committed**, status and headers are essentially finalized for transmission over the connection; attempting to edit them in a filter that runs too late may have no effect or throw an error.

This lesson belongs to the **Filter Chain** chapter and focuses on **`ServerHttpResponse.beforeCommit(...)`** in Spring WebFlux, its relationship to `GlobalFilter`/`GatewayFilter`, pre/post execution order (`pre`/`post`), streaming responses, and testing. It is foundational when building a microservices entry point using route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retry, TLS, and request observability.

> **Scope:** The Java sections use the reactive APIs of **Spring Cloud Gateway Server WebFlux** and **Spring Framework WebFlux**, illustrating versions that provide `GlobalFilter`, `GatewayFilterChain`, `ServerWebExchange`, and `ServerHttpResponse`. **Gateway Server MVC** uses the Servlet stack and has a different response API/lifecycle; do not copy a WebFlux `GlobalFilter` verbatim into an MVC app. Starter names and YAML namespaces must be verified against your Gateway line.

## 1. What Does "Response Committed" Mean?

An HTTP response has three distinct parts to separate:

| Part | Examples | When Must It Be Decided? |
|---|---|---|
| **Status** | `200 OK`, `401 Unauthorized`, `429 Too Many Requests` | Before the response commits |
| **Headers and cookies** | `Cache-Control`, `X-Request-Id`, `Set-Cookie` | Before the response commits |
| **Body** | JSON, HTML, byte stream, Server-Sent Events | Written per response mechanism; may initiate response commit |

**Commit** is the step where response state enters network transmission, during which the framework applies status/headers/cookies and starts or finishes sending data. Past the commit point, the initial response metadata can no longer be changed as if unsent.

Situations that transition a response into commit include:

- A handler or filter calls `response.setComplete()` to finish the response, even without a body.
- The framework calls `response.writeWith(...)` or `writeAndFlushWith(...)` to write the body.
- Gateway's routing/response filter forwards the downstream body back to the client.
- A component sends an error, redirect, or empty response and completes processing.

`isCommitted()` on `ServerHttpResponse` lets you observe current state, but it is **not a safe synchronization mechanism to read `false` and guarantee you can edit headers afterward**. When commit happens asynchronously, state can change between two operations. The right approach is to **register a pre-commit action early**, or complete modifications right before initiating response writing if you control that step directly.

### Three Distinct Moments

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as GlobalFilter / GatewayFilter
    participant D as Downstream
    participant R as ServerHttpResponse
    C->>G: Request
    G->>R: Register beforeCommit (before writing)
    G->>D: Forward request
    D-->>G: Status, headers, body
    G->>R: Send response via writeWith / setComplete
    Note over R: Commit starts
    R->>R: Run beforeCommit callbacks
    R-->>C: Status + headers + body
    Note over R: After commit: no longer safe to edit headers
~~~

This diagram is simplified: in practice Netty routing, Netty write response filter, Reactor, and other filters coordinate together. The key takeaway is that **`beforeCommit` runs during the commit process, before the framework applies response-head changes**.

## 2. Pre-Filter, Post-Filter, and beforeCommit Are Not Synonymous

In Gateway Server WebFlux, after a route matches, `FilteringWebHandler` combines `GlobalFilter`s with the route's `GatewayFilter`s and sorts them by order. Typically:

- **Pre**: code before `chain.filter(exchange)` executes when the request enters the filter chain.
- **Post**: reactive operations chained onto `chain.filter(exchange)` run when the downstream part of the chain emits the corresponding completion signal.
- **beforeCommit**: a callback registered on the **response**, invoked when the response actually enters commit, provided it was registered in time and commit occurs.

How to view a filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Pre: receive request; can register beforeCommit here.
    return chain.filter(exchange)
        .then(Mono.fromRunnable(() -> {
            // Post triggered on chain completion signal.
            // DO NOT assume the response is still uncommitted.
        }));
}
~~~

The `then(...)` block **does not guarantee** HTTP headers are still editable. In Gateway WebFlux, the response-writing filter itself may run during another filter's post stage. Depending on order, by the time your `then` Mono runs, the first bytes of the response may already be sent.

~~~mermaid
flowchart TD
    A["Pre-filter: register beforeCommit"] --> B["chain.filter(exchange)"]
    B --> C["Route to downstream"]
    C --> D["Prepare response write"]
    D --> E["ServerHttpResponse starts commit"]
    E --> F["Execute beforeCommit callbacks"]
    F --> G["Apply status, headers, cookies"]
    G --> H["Write response to client"]
    H --> I["Some post-filters may run after response committed"]
~~~

**Route order** (`Route.order`) affects only route selection. **Filter order** (`Ordered`/wrapped filter order) determines position in the chain; it does not replace `beforeCommit` when you need to act precisely at commit time.

## 3. The `ServerHttpResponse.beforeCommit` API

Spring WebFlux provides the API with this contract:

~~~java
void beforeCommit(Supplier<? extends Mono<Void>> action);
~~~

To use it, obtain the response from `ServerWebExchange`:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.defer(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
}));
~~~

**Three key points:**

1. **Register early:** call `beforeCommit(...)` in the pre part of the filter, before `chain.filter(exchange)`, so the callback is registered before any component commits the response.
2. **Defer side effects:** return a **deferred** `Mono<Void>` such as `Mono.defer(...)`. Modifying headers occurs when the Mono is actually subscribed to at commit time; do not mutate headers eagerly while building the callback if the goal is acting near commit.
3. **Complete asynchronously:** the callback can return a `Mono<Void>` that the framework awaits before writing status/headers. Avoid `block()`, blocking I/O, heavy computation, unnecessary remote calls, or callbacks that may never complete.

### Distinguishing Immediate Code from Commit-Time Code

**Example missing deferral:**

~~~java
// Do not use this structure if you need side effects guaranteed at commit time.
response.beforeCommit(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
});
~~~

Even though this lambda is invoked at commit, Reactor best practice is to return **a deferred publisher** for the asynchronous action, matching the `beforeCommit` contract and preventing subtle bugs as logic grows. Prefer the `Mono.defer` form shown as standard:

~~~java
response.beforeCommit(() -> Mono.defer(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
}));
~~~

A sharper difference appears if you create a `Mono` yet perform the side effect **before** subscription time:

~~~java
// Wrong expectation: modifies header immediately in pre-filter.
response.getHeaders().set("X-Edge-Processed", "true");
response.beforeCommit(() -> Mono.empty());
~~~

Setting a header early can be **completely valid** if you intentionally assign a fixed value upon receiving the request. However, that approach cannot inspect the final downstream response state or other filters and can easily be overwritten by a later filter. `beforeCommit` fits when decisions are needed near commit time.

### Does `beforeCommit` Promise to Run on Every Request?

No. The callback applies only to **the response on which it was registered** and **when that response enters commit**. Cases to watch out for:

- If a request matches no Gateway route, a Gateway `GlobalFilter` normally is not called; thus callbacks registered inside it never appear.
- If another component already committed the response **before you registered**, the callback cannot turn back time to edit sent headers.
- If a request is canceled, errors before reaching the commit path, or the connection drops, do not assume the callback always runs as a universal cleanup hook.
- The callback does not prove the full body reached the client; **committing the response head** differs from **finishing body transmission**.

To measure request completion, use metrics/tracing or operators observing terminal signals rather than treating `beforeCommit` as a "response sent successfully" event.

## 4. Complete Example: GlobalFilter Adding a Header Before Commit

Suppose Gateway must attach `X-Edge-Processed: true` to **responses passing through a Gateway route**, including when the backend returns HTTP 4xx/5xx, as long as the request traversed the filter and the response reaches commit.

~~~java
package example.gateway;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class EdgeResponseHeaderFilter implements GlobalFilter, Ordered {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        ServerHttpResponse response = exchange.getResponse();

        // Pre: register callback before letting the chain continue.
        response.beforeCommit(() -> Mono.defer(() -> {
            response.getHeaders().set("X-Edge-Processed", "true");
            return Mono.empty();
        }));

        return chain.filter(exchange);
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
~~~

Key details in this code:

- `GlobalFilter` enters the Gateway Server WebFlux pipeline **after route selection**. It is not a Spring Security `WebFilter`.
- `beforeCommit` is **registered in the pre branch**, independent of whether this class's post-filter runs before or after the response-writing filter.
- `Mono.defer` places the header mutation at the moment the publisher executes during commit.
- `getHeaders().set(...)` sets **a single value**; `add(...)` appends a value and can produce duplicate headers. Pick the semantics matching your business rule.
- `getOrder() = -100` is merely an example to invoke the filter early in many configurations; it is not a mandatory "magic number." Actual order and active filters must be verified in practice. **Registering before commit** is the decisive factor.
- Never add blocking work inside the callback, even to check service health, look up tokens, or call external APIs.

If Gateway has another filter **resetting** the same header in a pre-commit callback, the outcome depends on callback order and header behavior. Therefore, avoid letting multiple filters compete over ownership of the same header; establish conventions for who owns `X-Edge-Processed` or `Cache-Control`.

### Test Route for the GlobalFilter

An illustrative WebFlux route (common in Gateway 4.x lines):

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

Assume the Gateway application runs on `localhost:8080`, and an echo backend runs on `localhost:9090` serving `GET /orders/42`.

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

When the route matches and the request succeeds, the client response is expected to include:

~~~http
HTTP/1.1 200 OK
X-Edge-Processed: true
Content-Type: application/json
~~~

This is a **header illustration**, not a complete response. Status/body depend on the backend and other filters. If the request matches no route, this `GlobalFilter` may not execute and `X-Edge-Processed` may not appear.

## 5. When to Use a Built-In GatewayFilter Instead of Java Code?

Not every task needs custom `beforeCommit` code. When you just need to edit headers via simple configuration, consider the **built-in GatewayFilter factories** in your version.

Example:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
          filters:
            - SetResponseHeader=X-Edge-Service,catalog
            - AddResponseHeader=X-Processed-By,gateway
~~~

| Factory | Effect | Watch Out For |
|---|---|---|
| `AddResponseHeader` | Appends a value to a response header | Can produce multiple values under the same name |
| `SetResponseHeader` | Sets/replaces a response header value | Can overwrite values returned by downstream |
| `RemoveResponseHeader` | Removes a header by name | Depending on filter order, another component might add it back |
| `DedupeResponseHeader` | Removes duplicate headers using supported strategies | Useful when both Gateway and downstream add CORS headers |

Built-in filters have their own APIs and mechanisms for modifying responses in the pipeline. **Do not automatically assume all of them are implemented via `beforeCommit`**; what matters is picking the right factory for your version and verifying headers in real responses.

Write a custom `GlobalFilter` or `GatewayFilter` when you need contextual logic: choosing headers based on route ID, downstream status, test environment, metadata, or a policy unsupported by built-in factories.

## 6. Case Study: Adjusting Behavior Based on Downstream Status

Suppose you need to attach `Cache-Control: no-store` to error responses to avoid caching a backend error payload. You can read the status **near commit time** as long as the response has not yet been written:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Mono;

// Placed inside a filter, before chain.filter(exchange).
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.defer(() -> {
    HttpStatusCode status = response.getStatusCode();
    if (status != null && status.isError()) {
        response.getHeaders().set("Cache-Control", "no-store");
    }
    return Mono.empty();
}));

return chain.filter(exchange);
~~~

This example demonstrates the effect of **timing**: status may not yet be known during the pre-filter, yet it is usually populated before the response commits. Even so, statuses produced by Gateway, error filters, fallbacks, or downstream can vary by configuration; test real error paths too.

**Cache policy limitation:** `Cache-Control: no-store` is an HTTP directive whose behavior depends on caches/clients; it does not guarantee sensitive data is never persisted at every layer. When enforcing a mandatory security policy on all responses, ensure the callback is registered on **every relevant path**; a `GlobalFilter` that runs only after route matching is not enough to cover every application response.

### Avoid Muddying Status Determination

If you want to **reject a request right at the Gateway**, do not wait until `beforeCommit` to change `200` to `401`. Decide before routing and complete the response explicitly:

~~~java
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

// Example inside a filter, after an authorization check has produced a result.
// The denied condition is illustrative only; real auth should use Spring Security.
if (denied) {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
}

return chain.filter(exchange);
~~~

When calling `return setComplete()`, the downstream chain is no longer called on the denied branch. `beforeCommit` is suited for **finalizing response metadata**; it does not replace authentication/authorization.

## 7. Why Does Modifying the Response in a Post-Filter Often Fail?

Look at the example below:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    return chain.filter(exchange)
        .then(Mono.fromRunnable(() -> {
            // May already be too late depending on order and response writing.
            exchange.getResponse()
                .getHeaders()
                .set("X-Edge-Processed", "true");
        }));
}
~~~

This is not invalid Java syntax. The issue is **execution timing**: `then` waits for completion of the downstream chain; a response-writing filter inside that chain may have already committed before `then` executes. Consequences can include:

- The header never reaches the client.
- Exceptions because the header map is no longer mutable.
- Different behavior across responses with bodies, empty responses, and streaming responses.
- Tests against a fast local backend behaving differently from production, depending on filter order.

In Spring Cloud Gateway Server WebFlux, routing and response-writing components have distinct roles. For example, `NettyRoutingFilter` sends the request downstream via an HTTP client, while `NettyWriteResponseFilter` writes the returned body in the post-processing branch. `Ordered` determines whether your custom filter unwinds **before or after** the write step.

**Common fix:** register the `beforeCommit` callback right in the pre-filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();

    response.beforeCommit(() -> Mono.defer(() -> {
        response.getHeaders().set("X-Edge-Processed", "true");
        return Mono.empty();
    }));

    return chain.filter(exchange);
}
~~~

If errors persist, check whether the callback was registered **before the response already committed**, whether another filter is short-circuiting early, and whether another filter is editing the same header.

### `beforeCommit` Callback Order Can Be Part of Business Logic

If multiple components register callbacks that alter `Content-Type`, `Cache-Control`, or `Set-Cookie`, results can be hard to predict by reading route YAML alone. Assign one clear owner per critical header; if composition is needed, define explicit ordering and verify with integration tests.

Never use `beforeCommit` to rewrite the body or produce a second response. When body transformation is required, operate inside the body-writing pipeline using supported response decorators or body filters.

## 8. Streaming Responses and Bodies Advance Commit Timing

An HTTP response may contain:

- A small JSON body written in a single flush.
- Large files or multi-chunk downloads.
- **Server-Sent Events (SSE)** or long-lived streaming content.
- Bodyless responses like `204 No Content`, `304 Not Modified`, or some HEAD responses.

With streaming, status and headers must be finalized **before the first data chunk leaves**, while the body can keep streaming for minutes. By the time `doFinally` or the final post-filter runs, headers were committed long ago.

~~~mermaid
sequenceDiagram
    participant GW as Gateway filter
    participant R as Reactive response
    participant CL as Client
    GW->>R: beforeCommit(callback) registered in pre
    R->>R: Begin commit sequence
    R->>R: Execute pre-commit callback
    R-->>CL: HTTP status + headers
    loop Streaming
        R-->>CL: Next data chunk
    end
    Note over R,CL: Cannot change already-sent headers mid-stream
~~~

In this example, the callback runs **before** status/headers are applied; the diagram depicts commit at a high level without prescribing internal server event names.

### What If You Actually Need to Modify the Body?

You can use a `ServerHttpResponseDecorator` or a built-in body-transforming filter if supported by your version. When writing a decorator, handle properly:

- **Reactive backpressure** and the lifecycle of `Flux<DataBuffer>`.
- **DataBuffer release/pooling** per contract to avoid memory leaks.
- **Content-Length** when body size changes, or proper chunked transfer encoding.
- **Content-Encoding** such as gzip, and rules against blindly reading/editing binary payloads.
- Bodyless HTTP codes; SSE or streaming cannot arbitrarily buffer entire payloads in RAM.

`beforeCommit` **is not an API for reading the full body and editing it**. It is designed for actions executing right before the response commits. If JSON rewriting is required, use dedicated body-processing approaches and dedicated integration tests.

## 9. Route Configuration, Security, and Filter Scope

A Gateway application usually has multiple HTTP processing layers:

~~~mermaid
flowchart TD
    C["Client"] --> W["Spring WebFlux: WebFilter / Spring Security"]
    W --> H["RoutePredicateHandlerMapping"]
    H -->|"Route matched"| F["FilteringWebHandler"]
    F --> GF["GlobalFilter + GatewayFilter"]
    GF --> R["Routing / downstream"]
    R --> RESP["ServerHttpResponse beforeCommit + write response"]
    H -->|"No route matched"| NF["Error handler / web-layer response"]
    W -->|"Rejected early"| DENY["401/403 from security layer"]
~~~

From this it follows:

| Goal | Usually Suitable Place | Why? |
|---|---|---|
| Add a header to **every matched Gateway route** | `GlobalFilter` and `beforeCommit` | Easy access to route metadata without repeating route config |
| Add a header specific to **one route** | `GatewayFilter` or `SetResponseHeader` | Clear scope tied to route ID/URI/predicate |
| Enforce a mandatory header on **every HTTP response**, including unmatched 404s and security errors | `WebFilter` / appropriate outer web-layer response component | Gateway `GlobalFilter` may not run when no route is selected |
| Block unauthorized requests | Spring Security or policy filter running before routing | Prevents forwarding unauthorized requests to backends |
| Rate-limit per route | Filter with appropriate key resolver/backend limiter | Limits before forwarding; consider route fallbacks too |
| Collect metrics and request-end traces | Observability infrastructure / Reactor terminal signals | `beforeCommit` is not the body-transmission completion signal |

**Security:** never use client-supplied headers as proof that a request was authenticated. If adding an internal header like `X-Authenticated-User`, derive identity from a trusted security context, strip spoofed inbound headers, and avoid leaking sensitive details in responses.

**TLS:** `beforeCommit` operates only on HTTP response metadata. It does not replace listener TLS config, trust stores, certificate verification, or HTTPS connections to downstream services.

## 10. Tricky Bugs When a Callback Is Registered Yet the Header Is Missing

| Symptom | Causes Worth Checking | How to Verify |
|---|---|---|
| 200 response lacks the new header | Filter did not run, callback registered too late, header overwritten | Log route ID/filter, test a matching route; inspect all filters touching that header |
| Unmatched route request lacks header | Gateway `GlobalFilter` never ran | If policy must cover 404s too, inspect `WebFilter`/web-server layer |
| Header appears on 200 but not on 401/403 | Spring Security blocked before `FilteringWebHandler` | Check security filter chain; place logic at the right layer |
| Cannot edit header; exception thrown | Already committed or attempted to mutate headers too late in post-filter | Register `beforeCommit` in pre; check for early responses |
| Callback executes, yet status is unexpected | Error/fallback filter overwrote status or status decided late | Trace where status is set; test downstream and Gateway responses |
| Streaming response headers unchanged | Data already started flushing; callback registered post-commit | Register before the first stream chunk is written |
| Response contains multiple header values | `add` used across multiple filters or downstream also adds it | Define owner; use `set` or a dedupe filter |
| Client hangs or receives corrupt data after body edit | Wrong `DataBuffer`, `Content-Length`, compression, or backpressure handling | Use proper body filter/decorator; test streaming and large payloads |
| Behavior differs across Gateway instances | An instance runs older code/config or different route/order | Log instance ID; check rollout and caches |
| Header disappears behind reverse proxy or CDN | Downstream/edge proxy filters or overwrites headers | Compare direct Gateway response vs. client-facing response |

Enable targeted logging for the Gateway component under diagnosis and inspect traces/metrics when observability is configured. Avoid logging bodies, tokens, cookies, or private data merely to confirm `beforeCommit` ran.

### Use `isCommitted()` Only for Observation

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

This indicates whether a response **has already/is currently** passing commit at the instant observed, but it does not make subsequent header edits safe under an `if (!committed)` pattern. In particular, inside a `beforeCommit` callback itself, the framework has already begun committing; do not use `isCommitted()` to skip legitimate operations registered in the callback.

## 11. Hands-On Exercise: Proving Commit Timing

**Setup:** a Gateway Server WebFlux application of an appropriate version, an HTTP echo backend on `localhost:9090`, Gateway listening on `8080`, and the `/api/orders/**` route from section 4.

### Step 1 — Attach a Header via `beforeCommit`

Add the `EdgeResponseHeaderFilter` class from section 4 to your Gateway app sources, restart, and call:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Observe `X-Edge-Processed: true`, actual status, and the path received by the backend (`/orders/42` with `StripPrefix=1`). This confirms the callback ran on a routed response.

### Step 2 — Have the Backend Return an Error Status

Configure the backend to return an error response, e.g. HTTP 503 for `GET /orders/fail`, while still completing normally. Send:

~~~bash
curl -i http://localhost:8080/api/orders/fail
~~~

Verify `X-Edge-Processed` is attached if the request traversed the filter and committed, and that the downstream error code matches Gateway policy. If Gateway has `Retry` or `CircuitBreaker`, test results may differ due to retries/fallbacks; note that configuration.

### Step 3 — Try a Request Matching No Route

~~~bash
curl -i http://localhost:8080/not-configured
~~~

With no matching route or other handler, the app usually returns 404. With the current `GlobalFilter`, **do not expect** `X-Edge-Processed` in this response, as the filter's callback may never have been registered.

### Step 4 — Compare with a Post-Filter

In a test branch, replace `beforeCommit` with `.then(Mono.fromRunnable(...))` as in section 7 and measure outcomes across responses with a body, empty responses, and error responses. Never push that intentionally fragile test variant to production. Analyze via filter order and commit timing; **do not conclude post-filters are always wrong**, as valid orders and post-processing tasks do exist.

### Step 5 — Verify Streaming Responses

If your backend exposes an SSE or streaming endpoint, test with `curl -i -N`:

~~~bash
curl -i -N http://localhost:8080/api/orders/events
~~~

Ensure the route matches and the backend actually streams. The response must carry the header **before the first stream event**; while the stream stays open, another HTTP header block cannot be sent mid-stream. Do not call this hypothetical endpoint unless the backend implements it.

### Record Results

| Case | What to Record | Meaning |
|---|---|---|
| GET 200 with body | Status, new header, body | `beforeCommit` works on normal routes |
| GET returning 503 | Header present?, retry/fallback behavior | Behavior on error responses routed through Gateway |
| Path with no route | Header present or absent | Distinguishes Gateway `GlobalFilter` from outer web layer |
| 204/empty response | Are headers committed without a body? | Separates body writes from status/header commit |
| SSE/streaming | Header appears before first chunk | Commit happens early even while body keeps streaming |
| Post-filter version | Header present? Exception thrown? | Effect of filter order and mutation timing |

You do not need to artificially slow down a real backend or alter the system clock to test response commit behavior. Use an echo backend in a test environment, combined with logs/traces and inspecting bytes/headers received by the client.

## 12. Design Principles for Pre-Commit Filters

1. **Pick the right layer:** `GlobalFilter` for Gateway route responses, `GatewayFilter` for a single route, `WebFilter` or outer components to cover unmatched/security errors too.
2. **Register before calling the chain** when an action must land inside the commit window; avoid registering too late inside `doFinally` or `then`.
3. **Keep callbacks short, non-blocking, and deferred**, returning a completing `Mono<Void>`. Never put uncontrolled remote calls on the commit path of every request.
4. **Modify only valid response parts:** headers/status/cookies per lifecycle; for body edits, use a dedicated body pipeline.
5. **Assign header ownership:** avoid multiple filters calling `set`/`add` on the same name without an ordering contract; never leak internal info or tokens.
6. **Test all paths:** responses with bodies, empty responses, errors, security rejections, unmatched routes, retry/fallback, and streaming if used.
7. **Protect operability:** prevent failing/hanging callbacks from stalling all responses; record metrics, bounded logs, and actual client-observed output.

## 13. Self-Check Checklist

- [ ] I can distinguish **pre-filter**, **post-filter**, and **`beforeCommit`**.
- [ ] I understand status/headers/cookies must be decided before the HTTP response commits.
- [ ] I know how to obtain `ServerHttpResponse` from `ServerWebExchange`.
- [ ] I register `response.beforeCommit(...)` in the pre-filter using a deferred publisher such as `Mono.defer`.
- [ ] I do not treat `isCommitted() == false` as a lock guaranteeing absence of race conditions.
- [ ] I verified how `GlobalFilter` scope differs from `WebFilter` and route-specific `GatewayFilter`.
- [ ] I use `AddResponseHeader`/`SetResponseHeader` or built-in filters when custom Java logic is unnecessary.
- [ ] I do not use `beforeCommit` for authorization or rewriting the entire body.
- [ ] I have clear rules for sensitive headers, avoiding duplicate `add`s and uncontrolled overwrites.
- [ ] I tested normal, error, unmatched-route, bodyless, and streaming responses where applicable.
- [ ] I inspect filter order and response-writing components when debugging missing headers.
- [ ] I keep request observability, TLS, retry/circuit breaker, and rate limiting at the appropriate application layers.

## Official References

- [Spring Framework — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html) — `beforeCommit`, `setComplete`, `isCommitted`, and response management APIs.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — GlobalFilter, filter order, GatewayFilter factories, Netty routing/write response, and route lifecycle; select your exact version.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, `WebFilter`, and reactive response pipelines.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — `Mono.defer`, reactive signal sequences, cancellation, and non-blocking execution.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — observability, metrics, and management endpoints requiring protection.

**Remember:** To edit headers/cookies right before Gateway returns a response, **register `ServerHttpResponse.beforeCommit` early in the pre-filter and return a deferred `Mono<Void>`**. Code running inside `then` after `chain.filter(exchange)` may already be too late to change status/headers, especially when downstream responses have already been written or are long-lived streams. Choosing the right filter layer and verifying actual responses matters just as much as Java syntax.
