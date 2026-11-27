# Passing Data via Exchange Attributes and Reactor Context

## 1. Why Do Custom Filters Need to Pass Data Across Multiple Steps?

In **Spring Cloud Gateway**, a request traverses route predicates, the filter chain, header/path transformations, service discovery, load balancing, and HTTP(S) routing to reach a microservice. Gateway also commonly applies authentication, rate limiting, circuit breakers, retries, TLS, and observability.

When writing your own `GlobalFilter` or `GatewayFilter`, you may need to share information across steps:

- Filter A generates a `requestId` correlation identifier; Filter B uses it for logging.
- Filter A determines a **verified** tenant label; Filter B selects a rate-limit key or policy.
- An early filter reads route metadata; a later filter attaches an observability header to the upstream request.
- A Reactor operator needs trace information after the pipeline switches schedulers/threads.

**Two distinct mechanisms** commonly appear in designs:

1. `ServerWebExchange.getAttributes()`: a property map **attached to the HTTP exchange**, letting filters/handlers on the same request share data by key.
2. **Reactor `Context`**: a data store **attached to a reactive subscriber/subscription**, propagated across the Reactor chain within the scope of `contextWrite`.

These two mechanisms do not automatically synchronize with each other. Choosing the wrong store or placing `contextWrite` at the wrong spot can leave downstream filters reading `null`, drop correlation IDs, misattribute logs, or cause `ThreadLocal`-dependent code to break on thread switches.

This lesson belongs to the **Custom Filters** chapter of the **SPRING_CLOUD_GATEWAY** module. It focuses on using `exchange attributes` and `Reactor Context` with proper lifecycles and filter ordering, avoiding security leaks, and writing repeatable tests.

> **Scope:** examples use **Spring Cloud Gateway Server WebFlux** and Project Reactor. APIs such as `GlobalFilter`, `GatewayFilterChain`, `ServerWebExchange`, `Mono.deferContextual`, and `contextWrite` are shown in Java. Gateway Server MVC has a different architecture; never transplant Reactor Context directly into MVC/Servlet.

## 2. Overview of Data Storage Mechanisms

| Mechanism | Attached to | Read/write via | Used for | Do not use instead of |
| --- | --- | --- | --- | --- |
| Exchange attributes | A `ServerWebExchange` | `exchange.getAttributes().put(...)`, `getAttribute(...)` | Sharing data across WebFlux/Gateway filters and routing steps | HTTP headers, DB/session, security tokens |
| Reactor Context | A reactive subscription within operator scope | `contextWrite(...)`, `Mono.deferContextual(...)` | Propagating data across async operators, even across scheduler hops | Exchange attributes or automatic `ThreadLocal` |
| HTTP request headers | Message sent over the network | `ServerHttpRequest.mutate()` | Passing info to an **upstream service** per contract | Private internal storage |
| Security principal | Authentication in reactive Spring Security | `exchange.getPrincipal()`, Security context APIs | Identifying the verified authenticated caller | Self-asserted client headers |
| Session/data store | Multi-call requests or sessions | Spring Session/Redis/database | State that must outlive a single request | Short-lived Attributes or Context |
| `ThreadLocal` / MDC | One thread at a time | `MDC.put(...)`, `MDC.get(...)` | Certain synchronous logging libraries | Reactive context when execution switches threads |

**Question for choosing a mechanism:** does the data need to live **for the same HTTP request**, **within the current Reactor chain**, **in another microservice**, or **across multiple requests**? Each goal has its own channel.

~~~mermaid
flowchart LR
    C["HTTP client"] --> W["Spring WebFlux WebFilter"]
    W --> G["Gateway filter chain"]
    G --> A["GlobalFilter A<br/>exchange attributes"]
    A --> B["GlobalFilter B<br/>Reactor Context"]
    B --> N["Netty routing"]
    N --> S["Upstream service"]
    A -. "Attributes map on same exchange" .-> B
    B -. "Reactor Context along subscription" .-> N
    N -. "HTTP headers over the wire" .-> S
~~~

The diagram illustrates logical flows only. **Reactor Context is not sent over the network as HTTP headers**; for upstream to receive a request ID, you must explicitly write the appropriate header/metadata. **Attributes are not serialized automatically** to backends either.

## 3. Filter Chain Lifecycle and the Role of `Ordered`

In Gateway Server WebFlux:

- **`GlobalFilter`** applies to requests that have matched a Gateway route.
- **`GatewayFilter`** is attached to a specific route or produced by a `GatewayFilterFactory`.
- Filters are combined into a single chain and sorted by `Ordered`.
- **Pre-phase** runs in ascending order; **post-phase** of nested publishers usually unwinds in reverse order.
- Spring WebFlux/Security **`WebFilter`**s sit in an outer layer; they are not `GlobalFilter`s and do not share Gateway's filter ordering.

Example with two filters:

~~~text
Filter A: order = -100
Filter B: order = -90

Pre:
  A -> B -> routing

Post:
  routing -> B -> A
~~~

If A writes an attribute **before** calling `chain.filter(exchange)`, B can read it. If A writes the attribute only **after** `chain.filter(...)` completes, B's pre-phase has already run and could not see the value then.

This also matters when choosing where to place `contextWrite`. Reactor Context propagates through operators at **subscription time**, not as a global map editable arbitrarily from any thread.

### 3.1. Filters May Not Run on Every Response

A `401` or `403` blocked by `SecurityWebFilterChain` **before Gateway selects a route** may never invoke GlobalFilters A or B. A request matching no route may be handled elsewhere, bypassing declared route filters as well.

If correlation IDs are mandatory even on **responses rejected before routing**, place that logic in a properly positioned **`WebFilter`** and pass data down to Gateway via exchange/Context. Never expect `GlobalFilter` to observe every 401/404.

## 4. `ServerWebExchange` Attributes: Data for One HTTP Exchange

`ServerWebExchange` represents the request, response, and auxiliary processing data in WebFlux. `getAttributes()` returns a map keyed typically by `String`. Gateway also stores internal routing attributes there.

Writing and reading example:

~~~java
String key = "example.gateway.requestId";

// Early filter in the pipeline:
exchange.getAttributes().put(key, "req-abc-123");

// Later filter on the same exchange:
String requestId = exchange.getAttribute(key);
if (requestId != null) {
    // Use requestId safely within this request.
}
~~~

Characteristics:

- **Lifecycle:** scoped to one HTTP exchange; not long-term storage.
- **Visibility:** filters/handlers sharing the exchange (or decorators delegating attributes to the base exchange) can access the data.
- **Mutability:** the map allows replacing values by key; define **write ownership** to prevent accidental overwrites.
- **Does not cross the network:** upstream never sees attributes unless a filter maps them into headers/body/messages per contract.
- **Does not enter Reactor Context automatically:** calling `put` does not make `Mono.deferContextual` see that key.

### 4.1. Namespace Your Keys

Avoid overly generic keys:

~~~java
exchange.getAttributes().put("id", "123");
~~~

Another custom filter or the framework could use the same name. Use namespaced keys:

~~~java
public static final String REQUEST_ID_ATTRIBUTE =
        "example.gateway.request-context.requestId";
~~~

If a filter reads a required attribute, retrieve it in a typed/validated manner; never blindly cast an attribute of unknown origin. Type mismatches throw `ClassCastException` inside reactive pipelines, sometimes surfacing only in production.

### 4.2. Gateway's Internal Attributes

Spring Cloud Gateway defines constants in `ServerWebExchangeUtils`, for example:

| Constant | General meaning | When it may exist |
| --- | --- | --- |
| `GATEWAY_ROUTE_ATTR` | Selected route | After Gateway matches a route |
| `GATEWAY_REQUEST_URL_ATTR` | Target URI for routing | After building the upstream URL |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | Original URIs before transformations | When routing/path-rewrite filters record them |
| `GATEWAY_SCHEME_PREFIX_ATTR` | Scheme prefix like `lb` on special routes | After Gateway parses the URL |
| `CACHED_REQUEST_BODY_ATTR` | Cached request body in specific flows | Only when a filter intentionally caches the body |

Never assume `GATEWAY_REQUEST_URL_ATTR` **always** exists in a GlobalFilter with negative order; it may be populated only after `RouteToRequestUrlFilter`. Also never overwrite these internal constants to "reroute" unless you fully understand the routing contract: corrupting them can forward requests to unintended URLs.

### 4.3. Write Before Calling the Chain, Read After Calling the Chain

A filter can store metadata for later filters in pre-phase or for itself in post-phase:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    exchange.getAttributes().put("example.gateway.startNanos", System.nanoTime());

    return chain.filter(exchange)
        .doFinally(signal -> {
            Long start = exchange.getAttribute("example.gateway.startNanos");
            if (start != null) {
                long elapsedNanos = System.nanoTime() - start;
                // Record sanitized metric; never log raw tokens.
            }
        });
}
~~~

`doFinally` runs on complete, error, or cancel. This illustrates **using an attribute for per-request timing**; do not rely solely on `doOnSuccess` if you need to cover errors and cancellation.

**Concurrency note:** never have concurrent threads racing to mutate the same mutable object stored in attributes without proper synchronization. The attribute map is not a transaction, lock, or event bus.

## 5. Reactor Context: Per-Subscriber Data, Not `ThreadLocal`

Project Reactor provides an effectively immutable `Context` (each `put` yields a new context instance) and a read-only `ContextView`. Data flows **from the subscriber upstream to upstream operators at subscription time**, not like a global variable mutated at runtime.

Common APIs:

- `contextWrite(ctx -> ctx.put(KEY, value))`: creates a new context visible to its **upstream** segment.
- `Mono.deferContextual(contextView -> ...)`: defers reading the context until subscription time.
- `Flux.deferContextual(...)`: same for multi-element publishers.
- `ContextView.hasKey(KEY)`, `get(KEY)`, `getOrDefault(KEY, defaultValue)`: read values with appropriate safety.

### 5.1. Minimal Runnable Reactor Example

~~~java
import reactor.core.publisher.Mono;

public class ReactorContextDemo {
    static final String KEY = "example.requestId";

    static Mono<String> readRequestId() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));
    }

    public static void main(String[] args) {
        String result = readRequestId()
                .contextWrite(context -> context.put(KEY, "req-123"))
                .block();

        System.out.println(result); // req-123
    }
}
~~~

`block()` here is **strictly for a standalone `main` demo**. **Never call `block()` inside a `GlobalFilter`/`GatewayFilter` running on the Reactor Netty event loop**, as it blocks async threads, spikes latency, or throws errors.

### 5.2. Why Does `contextWrite` Placement Matter?

A mental model:

~~~text
Subscriber
  |
  v
contextWrite(put requestId)
  |
  v
deferContextual(read requestId)    <-- upstream can read it
~~~

In Reactor, `contextWrite` affects operators **upstream of itself** in the reactive chain. Never assume operators chained downstream after `contextWrite` automatically see the updated context.

Example:

~~~java
Mono<String> observed = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .contextWrite(ctx -> ctx.put("requestId", "req-123"));

// The Mono above reads req-123.
~~~

Distinguish **operator assembly** from **subscription time**. Synchronous Java code reading a `ThreadLocal`-style variable while constructing a `Mono` will not get this propagation behavior.

### 5.3. Context vs. MDC in Logging

`org.slf4j.MDC` typically relies on `ThreadLocal`. Reactive pipelines can use `publishOn`, `subscribeOn`, or libraries that switch threads; `MDC.put("requestId", ...)` on thread A is not guaranteed to be visible in logs on thread B.

`Reactor Context` propagates cleanly across the Reactor chain, **yet it does not automatically copy everything into MDC**. For automatic MDC/log correlation, use Micrometer Context Propagation, Reactor integrations, framework tracing, or a configured bridge, and test it on your version. Never enable context-propagation hooks without checking overhead and registered `ThreadLocal` scope.

## 6. When to Use Exchange Attributes vs. Reactor Context?

| Scenario | First choice | Why |
| --- | --- | --- |
| Filter A selects a route tag; Filter B in Gateway reads it | Exchange attribute | Available directly on `ServerWebExchange` |
| Custom operator needs request ID after `publishOn` | Reactor Context | Matches reactive subscriber lifecycle |
| Pass request ID to an external microservice | HTTP header / trace propagation | Neither Attributes nor Context crosses HTTP automatically |
| Persist login outcome for tomorrow's requests | Session / data store | Both mechanisms above are short-lived |
| Backend must verify user/tenant | Verified Security principal / token / identity assertion | Never trust an attribute populated from a raw client header |
| Per-route metrics | Exchange attributes or observation APIs | Track route ID and latency with bounded cardinality |
| Reactive library accepts `Mono`, not exchange | Reactor Context | Avoids threading `ServerWebExchange` through every layer |
| Unit-testing pure reactive logic without HTTP | `Context` or explicit parameters | No need to mock the entire Gateway |

**Do not force "both everywhere".** If filters simply share data via the exchange, attributes suffice. If propagating through reactive operators, Context avoids polluting method signatures. If a value is a core business parameter, **passing it explicitly as a method argument** can be clearer than either.

## 7. Complete Example: Bridging a Request ID Across Both Mechanisms

Goals of the example:

1. Gateway generates an unpredictable `requestId` for each route-matched request.
2. The first filter stores it in an **exchange attribute**.
3. The first filter writes `X-Request-Id` to the **outbound HTTP request**.
4. The first filter puts it into **Reactor Context** for inner filters.
5. A second filter reads and compares both sources inside the **reactive subscription**.
6. Gateway returns `X-Request-Id` in the response for client log correlation without exposing private info.

This is a practical exercise pattern, not a replacement for standard distributed tracing like Micrometer Tracing/OpenTelemetry.

### 7.1. Shared Keys Declaration

~~~java
package example.gateway.filter;

public final class GatewayContextKeys {
    public static final String REQUEST_ID_ATTRIBUTE =
            GatewayContextKeys.class.getName() + ".requestId";

    // Unique Object key helps avoid collisions among Reactor Context keys.
    public static final Object REQUEST_ID_REACTOR_CONTEXT = new Object();

    private GatewayContextKeys() {
    }
}
~~~

Use a namespaced `String` for the exchange map and a dedicated `Object` key for Reactor Context. The key must be the **exact same object reference** between writer and reader filters, so keep it in a shared constants class.

### 7.2. GlobalFilter Writing Exchange Attribute and Reactor Context

~~~java
package example.gateway.filter;

import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class RequestContextBridgeFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        // Intentionally generate a fresh ID; never trust client-supplied headers.
        String requestId = UUID.randomUUID().toString();

        // (1) Attach per-exchange metadata for downstream filters.
        exchange.getAttributes().put(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE, requestId);

        // (2) Pass via HTTP header when upstream needs it.
        ServerHttpRequest outboundRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set("X-Request-Id", requestId))
                .build();

        ServerWebExchange forwardedExchange = exchange
                .mutate()
                .request(outboundRequest)
                .build();

        // (3) Emit correlation header right before response commits.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);
            return Mono.empty();
        });

        // (4) contextWrite sits downstream of the chain.filter publisher;
        // operators inside the inner chain can read Context at subscribe time.
        return chain.filter(forwardedExchange)
                .contextWrite(ctx -> ctx.put(
                        GatewayContextKeys.REQUEST_ID_REACTOR_CONTEXT,
                        requestId));
    }
}
~~~

**Step-by-step explanation:**

- `UUID.randomUUID()` serves as a demo correlation ID; never use it as an access token, password-reset token, or security credential.
- `exchange.getAttributes().put(...)` runs before invoking the chain; later filters can read the attribute.
- `mutate().headers(...)` creates a request decorator with the updated header instead of mutating the immutable original request directly.
- `exchange.mutate().request(...).build()` builds an exchange decorator; in standard WebFlux it delegates attributes and response to the underlying exchange. If using custom decorators, verify delegation behavior.
- `beforeCommit` sets the response header **before commit**. If an earlier `WebFilter` already handled the response before Gateway, this filter may not run.
- `contextWrite` adds the ID to Context **scoped to the publisher returned by `chain.filter`**. It does not magically expose the ID to unrelated publishers or other HTTP requests.
- `getOrder()=-100` ensures the observer filter below (order `-90`) runs after metadata is populated. Do not treat these two numbers as a mandatory convention across all projects.

### 7.3. GlobalFilter Reading from Both Mechanisms

~~~java
package example.gateway.filter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class RequestContextAuditFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestContextAuditFilter.class);

    @Override
    public int getOrder() {
        return -90;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        return Mono.deferContextual(contextView -> {
            String fromContext = contextView.getOrDefault(
                    GatewayContextKeys.REQUEST_ID_REACTOR_CONTEXT, "missing");

            String fromAttribute = exchange.getAttribute(
                    GatewayContextKeys.REQUEST_ID_ATTRIBUTE);

            // Sufficient metadata for correlation; never log tokens or bodies.
            log.debug("Gateway requestId: exchange={}, reactor={}",
                    fromAttribute, fromContext);

            return chain.filter(exchange)
                    .doFinally(signal -> log.debug(
                            "Gateway requestId={} signal={}",
                            fromAttribute, signal));
        });
    }
}
~~~

`Mono.deferContextual(...)` is essential: it reads Context **when subscribed** inside the chain wrapped by the previous filter's `contextWrite`. Synchronous code running outside the reactive chain has no guarantee of seeing that context.

The audit filter still processes the request even if Context lacks the key, logging `missing` so discrepancies are easy to verify. In production, policies may alert on propagation failures. Never let **authorization** logic treat a `"missing"` value carelessly or default to granting access.

### 7.4. Minimal Route Configuration to Run the Example

Server WebFlux 5.x typically uses:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
~~~

On common Gateway WebFlux 4.x releases, the equivalent route sits under `spring.cloud.gateway.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
~~~

**These two YAML snippets are version-specific alternatives**—do not declare both simultaneously. Because both Java filters are `@Component` beans implementing `GlobalFilter`, they join matched route chains automatically without listing `name: RequestContextBridge` in `filters`.

Ensure the upstream actually runs and accepts `GET /catalog/products/42`. `localhost` works for local demos when processes share a host; in containers, use proper DNS/service names.

## 8. Where Can `contextWrite` Be Misplaced?

### 8.1. Placing `contextWrite` Around the Right Publisher

Pattern to internalize:

~~~java
return chain.filter(exchange)
        .contextWrite(ctx -> ctx.put(KEY, requestId));
~~~

Here, `chain.filter(exchange)` is the **upstream publisher** of `contextWrite`; operators invoked inside that publisher see the key upon subscription.

Counter-example:

~~~java
return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault(KEY, "missing")))
    .contextWrite(ctx -> ctx.put(KEY, requestId))
    .flatMap(value -> {
        // The flatMap downstream of contextWrite in operator order
        // does NOT receive the Context written earlier by default.
        return Mono.deferContextual(ctx -> Mono.just(
                ctx.getOrDefault(KEY, "missing")));
    })
    .then();
~~~

This demonstrates that **operator position** determines context scope. Do not generalize a simple `contextWrite` example into thinking every operator in the same method always sees that value.

### 8.2. `contextWrite` Does Not Mutate a Global Variable

~~~java
Context updated = Context.empty().put("requestId", "req-123");
~~~

`updated` is a new context instance; it does not make `requestId` visible to every `Mono` in the JVM. Unless attached to the **target subscription**, other publishers never see it.

### 8.3. Never Use a Separate `subscribe()` to "Pass Data"

Anti-pattern in a filter:

~~~java
// WRONG reactive filter design:
Mono.deferContextual(ctx -> {
    // Side work reading Context.
    return Mono.empty();
}).subscribe();

return chain.filter(exchange);
~~~

Calling `subscribe()` manually creates **a separate subscription**, breaking context, cancellation, errors, backpressure, and response lifecycle management. **Compose** publishers with `then`, `flatMap`, `deferContextual`, or suitable operators so everything stays inside the request chain.

Never call `block()` on the Reactor Netty event loop or stash `ServerWebExchange` in a static/global variable to "pass" it to another thread.

## 9. Can a Per-Route Custom `GatewayFilterFactory` Use Both Mechanisms?

Yes. When data is needed only for a single route, a `GatewayFilterFactory` can store metadata in an exchange attribute or enrich Reactor Context. Example:

~~~java
package example.gateway.filter;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.stereotype.Component;

@Component
public class RouteLabelGatewayFilterFactory
        extends AbstractGatewayFilterFactory<RouteLabelGatewayFilterFactory.Config> {

    public RouteLabelGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        return (exchange, chain) -> {
            String label = config.getLabel();
            exchange.getAttributes().put("example.gateway.routeLabel", label);

            return chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put("example.gateway.routeLabel", label));
        };
    }

    public static class Config {
        private String label;

        public String getLabel() {
            return label;
        }

        public void setLabel(String label) {
            this.label = label;
        }
    }
}
~~~

Route using the factory:

~~~yaml
filters:
  - name: RouteLabel
    args:
      label: catalog-read
~~~

`catalog-read` is **route configuration metadata** for demo purposes, not user identity or permissions.

**Note:** the default factory name derives from the class name ending in `GatewayFilterFactory`, so `RouteLabelGatewayFilterFactory` is configured as `name: RouteLabel`. This route-specific filter runs only when attached to a matching route.

If another filter reads the label, align on key names and ordering. Never reuse the same key for a `String` in route A and a different object type in route B; downstream readers may hit cast errors.

### 9.1. When to Use `GlobalFilter` Instead of a Factory?

| Need | Suitable approach |
| --- | --- |
| Request ID/trace generated for every Gateway route | `GlobalFilter` |
| Policy dedicated only to an upload route | Route `GatewayFilterFactory` |
| Per-route configurable label or behavior | Factory with `Config` |
| Intercepting 401 responses before route matching | `WebFilter` at the WebFlux layer |
| Logging verified authenticated principal across routes | `GlobalFilter` reading principal reactively |

A factory enables per-route configuration, yet **does not create a global Reactor Context on its own**. Context must still be written via the right publisher scope.

## 10. Security of Data in Exchange and Context

### 10.1. Never Treat an Attribute as Verified Data

Unsafe example:

~~~java
String tenantId = exchange.getRequest()
        .getHeaders()
        .getFirst("X-Tenant-Id");

exchange.getAttributes().put("tenantId", tenantId);
~~~

If clients can send `X-Tenant-Id`, the value inside the attribute **remains untrusted**. Copying a header into a map does not turn it into an authenticated principal.

For quotas or authorization, tenant IDs must originate from:

- Verified Spring Security principals / JWT claims with checked audience/issuer.
- A trusted identity service or policy engine.
- Internal metadata protected by mTLS, signatures, or an enforced trust boundary.

Likewise, `Reactor Context` is strictly a **data-propagation mechanism**; it does not authenticate its contents. Never grant admin access because `contextView.get("role") == "admin"` without knowing who wrote it and what verified it.

### 10.2. Never Put Secrets in Logs or Response Headers

Never log or echo:

- `Authorization: Bearer ...`, session cookies, refresh tokens.
- Passwords, API secrets, private keys, PII-bearing payloads.
- OTP codes, password-reset links, or payment details.
- Unvalidated identity metadata.

Random request IDs are generally fine for correlation, though they can still act as **tracking identifiers** if retained long-term or linked to users. Enforce appropriate retention, access control, and redaction. Never use a request ID as a credential.

### 10.3. Scope and Data Disposal

Attributes and Context normally live only for the request/subscription lifetime, yet storing references to them in static maps, unbounded caches without TTLs, or unmanaged background tasks keeps data alive longer than intended—causing memory leaks or user-data exposure.

When state must persist across requests, use a **session store, policy-governed cache, or database**—never "temporarily stash" `ServerWebExchange` or `ContextView` in singletons.

## 11. Thread Switching, Cancellation, and Backpressure

### 11.1. Switching Schedulers Does Not Erase Context

A pipeline may use `publishOn(Schedulers.boundedElastic())` for suitable tasks. Reactor Context stays attached to the subscriber chain when operators are composed properly, whereas custom `ThreadLocal`s do not automatically survive every hop.

~~~java
Mono<String> work = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .publishOn(reactor.core.scheduler.Schedulers.boundedElastic())
    .map(id -> id + "-processed")
    .contextWrite(ctx -> ctx.put("requestId", "req-123"));
~~~

This publisher still returns `req-123-processed` across the scheduler hop. Never use `boundedElastic` as a Band-Aid for blocking filter code without evaluating throughput, and never call `block()` on the event loop.

### 11.2. Cancellation and `doFinally`

Clients can close connections, time out, or cancel subscriptions. When recording metrics, `doFinally` can observe `SignalType.CANCEL` alongside `ON_COMPLETE` and `ON_ERROR`.

~~~java
return chain.filter(exchange)
        .doFinally(signal -> {
            // Count complete/error/cancel per policy.
        });
~~~

Do not infer that `doFinally` runs after **all backend business work** succeeded or the client received the full HTTP response: cancellation can strike mid-flight while backend side effects continue.

**Warning:** never write response headers inside `doFinally`; the response may already be committed. For response metadata, use `beforeCommit` or an appropriate pre-write phase.

### 11.3. When a `Retry` GatewayFilter Is Present

With `Retry`, the chain segment behind Retry can be **resubscribed/re-executed**. This affects:

- Attributes rewritten on each attempt, especially counters or timestamps.
- Context re-initialized per subscription via `contextWrite`; never treat it as a mutable cache shared across attempts.
- Logs and metrics potentially counting **upstream attempts** rather than client requests.
- Filters sitting before Retry running only once per client request.
- Request bodies potentially buffered for write retries, creating memory pressure.

If a request ID must remain **invariant across all attempts**, generate it in a filter **outside Retry** without regenerating per attempt. If you need a per-attempt ID, place it inside the retry-aware pipeline and label it distinctly.

## 12. Boundaries That Do Not Propagate Automatically

| Boundary | Exchange attributes | Reactor Context | How to pass when needed |
| --- | --- | --- | --- |
| Same Gateway filter chain | Readable on same exchange | Readable within `Context` scope | Set key before chain; place `contextWrite` properly |
| `publishOn` / scheduler switch | Exchange stays explicitly passed | Reactor propagates along chain | Never use `ThreadLocal` directly |
| Independent manual `subscribe()` | Not shared unless exchange passed | Context may differ or be empty | Compose in same publisher; avoid detached subscriptions |
| HTTP request Gateway → upstream | **No** | **No** | `X-Request-Id`, W3C Trace Context per contract |
| Multiple HTTP requests from one client | **No** | **No** | Session / token / data store |
| Different JVM / microservice | **No** | **No** | Protocol headers, messaging metadata, tracing |
| Spring Security `WebFilter` before routing | Post-route attributes don't exist yet | `GlobalFilter` Context doesn't exist yet | Place bridge in an outer `WebFilter` if needed |

This table helps prevent a classic mistake: a `GlobalFilter` adding `contextWrite` cannot reach backward in time to let an earlier Spring Security filter read that value.

## 13. Unit Testing Reactor Context

### 13.1. `StepVerifier` Verifying Propagation

Gateway-independent test example:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {
    private static final String KEY = "example.requestId";

    @Test
    void readsContextFromSubscription() {
        Mono<String> publisher = Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));

        StepVerifier.create(
                publisher.contextWrite(ctx -> ctx.put(KEY, "req-test-42")))
            .expectNext("req-test-42")
            .verifyComplete();
    }

    @Test
    void showsMissingWithoutContextWrite() {
        Mono<String> publisher = Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));

        StepVerifier.create(publisher)
            .expectNext("missing")
            .verifyComplete();
    }
}
~~~

This test requires `reactor-test` and matching JUnit dependencies and shows **expected assertions, not executed output**. It demonstrates that `Context` belongs to a subscription and defaults to missing without `contextWrite`.

### 13.2. Testing Exchange Attributes

For Gateway unit tests, use `MockServerWebExchange` and `MockServerHttpRequest`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class ExchangeAttributesTest {
    @Test
    void attributesBelongToExchange() {
        var request = MockServerHttpRequest.get("/api/catalog/items").build();
        var exchange = MockServerWebExchange.from(request);

        exchange.getAttributes().put(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE, "req-test-42");

        assertThat(exchange.getAttribute(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE))
            .isEqualTo("req-test-42");
    }
}
~~~

Requires `spring-test` and AssertJ/JUnit on the classpath. Testing `get`/`put` verifies attribute behavior only; it **does not prove Context propagation**, filter ordering, or outbound request headers.

## 14. Integration Testing Both GlobalFilters

To verify the filters run together properly, set up a test environment:

- Gateway at `http://localhost:8080`.
- Mock upstream at `http://localhost:8081`.
- Route `GET /api/catalog/**` with `StripPrefix=1`.
- `RequestContextBridgeFilter` at order `-100`.
- `RequestContextAuditFilter` at order `-90`.

Send:

~~~bash
curl -i http://localhost:8080/api/catalog/products/42
~~~

Expected flow when the mock upstream receives the request:

~~~text
Client -> Gateway:
  GET /api/catalog/products/42

Gateway filter:
  Fresh X-Request-Id generated
  requestId attribute written
  requestId Context added for inner chain

Gateway -> mock upstream:
  GET /catalog/products/42
  X-Request-Id: <new-uuid>

Upstream -> Gateway -> Client:
  Mock response status/body
  X-Request-Id: <same-uuid>
~~~

This describes **expected results**, not captured live output. For strict assertions, have the mock upstream record received headers and paths; capture the response `X-Request-Id` and assert it matches what upstream received, while verifying via logs/test hooks that `fromContext` equals `fromAttribute`.

### 14.1. Test Matrix

| Case | Variation | Expected behavior |
| --- | --- | --- |
| A1 | Normal matched route call | Request ID matches across attributes, Context, response, and upstream header |
| A2 | Second call to same route | Fresh ID generated; no stale state reused across requests |
| A3 | Change reader order to `-110` | Reader misses attr/Context; test catches ordering bug |
| A4 | Remove `contextWrite` in first filter | Attribute still present; `deferContextual` returns `missing` |
| A5 | Remove `exchange.getAttributes().put` | Context still present; attribute missing |
| A6 | Client sends `X-Request-Id: attacker` | Filter overwrites with Gateway-issued ID, never trusting client |
| A7 | Upstream returns 503 | ID still present along chain; status reflects upstream |
| A8 | Client closes connection mid-flight | `doFinally` sees `CANCEL`; no writes after commit |
| A9 | Add `Retry` for GET | Request ID stays invariant across attempts; attempt counters increment properly |
| A10 | Spring Security rejects 401 before route | GlobalFilters may not run; evaluate if `WebFilter` is needed |
| A11 | No route matches | Do not expect an ID from `GlobalFilter` |
| A12 | Switch scheduler via `publishOn` | Context still works within the reactive chain |
| A13 | Invoke a publisher via separate `subscribe()` | Context missing; test exposes the anti-pattern |

### 14.2. Be Careful Counting Filter Invocations

With `Retry`, a single client request can generate multiple upstream attempts. Seeing one request ID logged alongside an upstream counter incrementing by 3 can be completely expected retry behavior.

In metrics, separate **client request count** from **upstream attempt count**. Never put request IDs in **metric labels**, because every request mints a unique value and causes unbounded cardinality. Use trace/log correlation for request IDs; group metrics by route ID, status, and error category.

## 15. Common Issues and How to Diagnose Them

| Symptom | Common cause | Where to look |
| --- | --- | --- |
| Filter B reads `null` attribute | A wrote after `chain`, wrong order, or different exchange | Check pre-phase, `Ordered`, write timing |
| `deferContextual` returns `missing` | `contextWrite` misplaced or different subscription | Inspect operator graph and key reference identity |
| Reading Context via `ThreadLocal` gives `null` after `publishOn` | Reactor Context does not auto-sync to `ThreadLocal` | Use `deferContextual` or tracing bridge |
| Upstream lacks `X-Request-Id` | Only set attribute/Context without mutating HTTP request | Check `ServerHttpRequest.mutate().headers` |
| Client lacks `X-Request-Id` on 401 | Spring Security rejected before Gateway `GlobalFilter` | Move required logic to a `WebFilter` |
| Client lacks response header after error | Added header too late after commit | Use `beforeCommit` early enough |
| Request ID from another request appears | Stored per-request state in singleton/static field | Keep state strictly per request/subscription |
| Tokens leaked via Context logs | Context held secrets and got dumped/logged | Store only safe metadata; redact |
| Retry triples counters | Filter sits after Retry and re-executes | Check ordering; separate attempt metrics |
| `GATEWAY_REQUEST_URL_ATTR` is null | Read before `RouteToRequestUrl` ran | Check phase/order; do not assume early presence |
| Excessive body caching | Custom filter/Retry buffers bodies unboundedly | Cap sizes, concurrency, memory/backpressure |
| Context exists in filter yet absent in next service | Reactor Context does not cross the network | Send HTTP trace headers/metadata per contract |
| CORS/`Forwarded` headers confused with context | HTTP headers carry their own network semantics | Never treat `X-Forwarded-*` as secure Context |
| Standalone test passes, Gateway fails | Filter ordering, route matching, or security layer | Full integration test and log route IDs |

### Short Debugging Checklist

1. Did the request match a **route**, or did Security reject it beforehand?
2. Which filter **writes** the key—in pre-phase or post-phase, and at what order?
3. Which filter **reads** the key? Is it using the same exchange/decorator and key reference?
4. Is the Reactor Context reader **upstream of `contextWrite`** in the subscription?
5. Are there detached `subscribe()` calls, manual threads, or `ThreadLocal`s?
6. Was the outbound header set via a request decorator? Did the backend receive it?
7. Had the response already committed before the filter tried setting headers?
8. Are `Retry`, timeouts, cancellation, or multiple subscriptions changing execution counts?
9. Did data in attributes/Context originate from a verified principal or an untrusted header?
10. Do any logs or metric labels contain tokens, cookies, or high-cardinality request IDs?

## 16. Practice Exercise: Adding Correlation and Tenant Policy

**Scenario:** Gateway has two routes, `/api/catalog/**` and `/api/orders/**`, both protected by Spring Security and `RequestRateLimiter` per user/tenant.

Requirements:

1. Create an early-order `GlobalFilter` generating a **correlation ID** and storing it in an exchange attribute and Reactor Context.
2. Add `X-Request-Id` to upstream requests and client responses without trusting unverified client IDs.
3. Create another `GlobalFilter` using `Mono.deferContextual` to read the ID and cross-check it against the attribute.
4. If tenant ID is needed, obtain it from the **authenticated principal**, never from a client-sent `X-Tenant-Id` header.
5. Decide whether the rate limiter receives the tenant policy via exchange attribute, Context, or explicit parameter; document your rationale.
6. Use `RouteLabelGatewayFilterFactory` if you want to tag routes for metrics.
7. Write `StepVerifier` unit tests for Reactor Context and `MockServerWebExchange` tests for attributes.
8. Write an integration test with a mock upstream asserting `X-Request-Id` traverses Gateway as a single consistent value.
9. Enable `Retry` **for GET only**, verifying the request ID stays constant across attempts while attempt counters increment properly.
10. Send a request rejected with 401 before routing; explain why `GlobalFilter` did not add the header and how a `WebFilter` can address it.
11. Test client disconnect or timeout; verify nothing writes to the response after commit.
12. Monitor p95/p99 latency, route ID, status, and retry count; **never** put request IDs in metric labels.

### Production Checklist

- [ ] Clearly distinguished whether data belongs to the **exchange**, **reactive subscription**, or **HTTP protocol**.
- [ ] Exchange attribute keys are namespaced and never overwrite Gateway internal constants.
- [ ] `contextWrite` sits on the right side of the publisher and is read via `deferContextual`.
- [ ] `ThreadLocal`/MDC is never used directly in place of Reactor Context without a proper bridge.
- [ ] No `block()` or detached `subscribe()` calls inside Gateway filters.
- [ ] Ordering of writer/reader filters is tested across pre/post phases.
- [ ] `ServerWebExchange`/`ContextView` references are never retained in singletons/static maps past the request.
- [ ] Security principals/tenants are verified; self-asserted client headers are never trusted.
- [ ] Outbound upstream headers are mutated explicitly rather than expecting attributes to cross the network.
- [ ] Response headers are set before commit, including eligible error branches.
- [ ] Cancellation/error handling and latency hooks are in place.
- [ ] Tested alongside `Retry`, circuit breakers, rate limiters, and service discovery.
- [ ] Avoided caching large bodies, races on shared mutable objects, and `DataBuffer` leaks.
- [ ] Logs/traces redact credentials; metric labels have bounded cardinality.
- [ ] Tested 401/403/404 responses originating outside Gateway routes.
- [ ] Using only APIs and namespaces matching your Spring Cloud Gateway WebFlux version.

## 17. Summary and References

**`ServerWebExchange.getAttributes()`** lets filters sharing one HTTP exchange exchange short-lived metadata, while **Reactor `Context`** lets reactive operators carry data along a subscription, even across scheduler switches. They **do not sync automatically**, do not cross the HTTP network, and do not replace Spring Security principals or session stores.

A custom `GlobalFilter` can populate both: write the attribute before calling `chain.filter`, then attach `contextWrite` so inner filters/operators read it with `Mono.deferContextual`. When downstream services need the request ID, explicitly mutate **HTTP headers**; when clients need it, set response headers before commit.

To operate Gateway safely, combine filter ordering, route predicates, authentication/authorization, rate limiting, retries, circuit breakers, TLS, and observability while keeping crisp boundaries between request state, reactive subscriber state, and network metadata.

### References

- [Spring Cloud Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — Custom GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
- [Spring Framework — ServerWebExchange API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html).
- [Project Reactor — Context, Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
