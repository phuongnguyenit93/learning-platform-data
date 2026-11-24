# Reactor Context and Request-Scoped Data Across Thread Switches in Spring Boot WebFlux

## 1. Problem: An HTTP Request Does Not Always Run on One Thread

In the synchronous Servlet model, developers typically picture one request handled by one worker thread, temporarily attaching data to `ThreadLocal`: trace ID (`requestId`), user info, locale, or MDC values for logging.

In **Spring WebFlux + Project Reactor**, an asynchronous processing chain consists of `Publisher`s (`Mono`/`Flux`) that are *subscribed* to; operators may run at different times and on different threads. Multiple requests share event loops; one request can hop from an event loop to another scheduler (e.g., via `publishOn`), and then onto yet another thread. Consequently, **a thread is not a stable identifier for a request**.

~~~text
HTTP request A                 HTTP request B
     |                              |
     v                              v
Reactor Netty event-loop-1  Reactor Netty event-loop-1
     |                              |
     +-- publishOn(...)             +-- async processing
             |                              |
             v                              v
       parallel-2                    parallel-1
             |                              |
      requestId = A                  requestId = B
       (Reactor Context)            (Reactor Context)
~~~

The diagram is illustrative; actual thread names and scheduling vary. **What must be preserved is the right data per subscription**, regardless of which thread executes an operator.

**Reactor `Context`** solves the problem of propagating *metadata along a reactive chain*: instead of stashing info in global variables or relying on `ThreadLocal`, data travels alongside the **`Subscriber` and subscription relationship**. Typical examples include correlation IDs, tracing metadata, verified tenant IDs, or auxiliary library metadata. It is not application-wide shared memory and does not replace primary business arguments.

## 2. Three Concepts Commonly Confused

| Mechanism | Bound to what? | Survives `publishOn`? | When to use? |
| --- | --- | --- | --- |
| `ThreadLocal<T>` | A Java thread | **Not by default**; requires configured bridges/restoration | Imperative libraries, traditional MDC |
| `ServerWebExchange.getAttributes()` | One WebFlux HTTP exchange | Data stays with the exchange wherever a reference to the **same exchange** exists | Sharing data between WebFilters/handlers that hold the exchange |
| Reactor `Context`/`ContextView` | **Subscriber** in a Reactor chain | **Yes**, across Reactor operators preserving the subscription link | Metadata crossing services, `flatMap`, `publishOn`, `subscribeOn`, reactive clients/filters |

A `ThreadLocal` variable can hold request A's value on the current thread; when B reuses that thread, A's value risks being read by mistake if cleanup fails. With Reactor Context, each subscription receives its own logical context, removing any need to pin all steps to one thread.

**Do not equate Reactor Context with an absolute "HTTP request scope"**: context is bound to a subscriber; one request normally creates an appropriate subscription chain, yet a request can spawn other publishers, and manual `subscribe()` calls or hopping into non-Reactor async mechanisms create new boundaries. Only data attached/propagated properly across those boundaries continues to appear.

## 3. Core Reactor Context API

`reactor.util.context.Context` is a map-like structure storing **key → value** pairs; keys and values are typed as `Object`. `Context` is **immutable**: write operations return a **new** Context without mutating the existing one.

- `Context.empty()`: creates an empty context.
- `Context.of(key, value)`: creates an initial context.
- `context.put(key, value)`: returns a new Context containing that key/value.
- `context.delete(key)`: returns a new Context without that key.
- `context.putAll(otherContextView)`: returns a Context after merging entries.
- `ContextView`: read-only view with `get(key)`, `getOrDefault(key, defaultValue)`, `getOrEmpty(key)`, `hasKey(key)`.

`ContextView` is what should be exposed to readers, preventing code from mistakenly believing it can mutate the current context in place.

Two Reactor operations matter most:

~~~java
// Write: applies Context to operators located UPSTREAM in the chain.
Mono<String> result = someMono
    .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// Read: defers until subscription time to inspect the effective Context.
Mono<String> requestId = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("requestId", "missing")));
~~~

**Calling `Context.of(...)` alone does not attach data to a request.** It merely creates an immutable object; you must apply `contextWrite(...)` at the right place to inject it into the subscription.

### 3.1. How Does `contextWrite` Write?

Two common forms:

~~~java
// A ContextView merged with context flowing from downstream.
source.contextWrite(Context.of("requestId", "req-101"));

// Function producing a new Context based on the current Context.
source.contextWrite(ctx -> ctx.put("requestId", "req-101"));
~~~

The function form has the advantage of preserving keys from other libraries, such as tracing/security data already added by the system. **Avoid** constructing and returning `Context.empty()` indiscriminately because it wipes downstream metadata; do not erase framework keys.

### 3.2. `deferContextual` Reads at the Right Moment

~~~java
Mono<String> readId = Mono.deferContextual(contextView ->
    Mono.just(contextView.getOrDefault("requestId", "missing")));
~~~

`deferContextual` receives the `ContextView` at **subscription time**, not when declaring the `readId` variable. Placing it inside chaining operators like `flatMap` lets you read context during asynchronous execution regardless of the active thread.

If a key might be absent, use `getOrDefault` or `getOrEmpty` and define explicit behavior; `get(key)` throws when missing, which fits contracts requiring a mandatory value. Keys lack compile-time type safety: avoid abusing unnamespaced string keys; define consistent constants/key objects and cast carefully.

## 4. Most Important Rule: **Context Flows Downstream to Upstream on Subscribe**

This runs counter to intuition about data flow:

- Data signals (`onNext`, `onError`, `onComplete`) flow **from source down to subscriber**.
- Context is supplied by the subscriber to operators during subscription, flowing **from downstream up to upstream**.
- Therefore, a `contextWrite` near the bottom of a chain supplies values to a `deferContextual` near the top, even though `contextWrite` appears on a lower line of source code.

**Correct** example:

~~~java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just("id=" + ctx.get("requestId")))
    .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// subscribe/block -> "id=req-101"
~~~

~~~text
On subscribe:
Subscriber --> contextWrite [put requestId=req-101] --> deferContextual
                 ^ enriches context for upstream operators

When emitting signals:
deferContextual --> contextWrite --> Subscriber
~~~

**Misplaced** example:

~~~java
Mono<String> wrong =
    Mono.just("begin")
        .contextWrite(ctx -> ctx.put("requestId", "req-101"))
        .flatMap(ignore -> Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("requestId", "missing"))));

// block -> "missing"
~~~

`flatMap` **below** `contextWrite` sits outside the scope affected by that write. Misunderstanding this rule often leads developers to blame `publishOn` for losing context when operator ordering is the real culprit.

### 4.1. Overriding Keys and Inner-Chain Scoping

~~~java
Mono<String> value =
    Mono.deferContextual(ctx -> Mono.just(ctx.get("requestId")))
        .contextWrite(ctx -> ctx.put("requestId", "inner"))
        .contextWrite(ctx -> ctx.put("requestId", "outer"));

// result: "inner"
~~~

`inner` is written in the `contextWrite` **closer downstream to the reader**, so the reader sees `inner`. Two `contextWrite` calls do not share a single mutable map.

With `flatMap`, a `contextWrite` on an **inner publisher** only changes the context visible to that inner publisher:

~~~java
Mono<String> example =
    Mono.just("item")
        .flatMap(item ->
            Mono.deferContextual(ctx ->
                Mono.just(item + ":" + ctx.get("requestId")))
                .contextWrite(ctx -> ctx.put("requestId", "local")))
        .flatMap(result ->
            Mono.deferContextual(ctx ->
                Mono.just(result + ":" + ctx.get("requestId"))))
        .contextWrite(ctx -> ctx.put("requestId", "request"));

// result: "item:local:request"
~~~

The `local` write applies only to the first inner publisher; the read in the subsequent `flatMap` still sees `request` from the outer chain. This is **scoping behavior**, not Reactor "dropping" data.

## 5. Does Switching Threads via `publishOn` and `subscribeOn` Lose Context?

**Usually no**, provided you preserve a properly composed Reactor chain and do not spawn detached subscriptions. Context follows the subscriber, not the current thread.

| Operator | Scheduling effect | Context effect |
| --- | --- | --- |
| `publishOn(scheduler)` | Shifts **downstream** signal emission/processing onto the chosen scheduler (until another boundary) | Context remains visible within the subscription scope |
| `subscribeOn(scheduler)` | Affects subscription timing/thread and upstream source execution; chain position affects threads less directly than `publishOn` | Context still propagates with the subscription |
| `flatMap` | May run asynchronous inner publishers interleaved | Inner publishers subscribed by Reactor in the chain receive the appropriate context; writes inside an inner publisher stay scoped to it |
| `delayElement` / `Mono.delay` | Uses a scheduler/timer to emit signals later | Does not drop Context just from switching threads |
| Manual `subscribe()` | Starts a **new** subscription with its own lifecycle | May lose the original request chain's context unless explicitly propagated |
| `CompletableFuture` / `ExecutorService` | Executes outside Reactor | Does not automatically carry Reactor Context simply by submitting a task |

Example:

~~~java
Mono<String> switched =
    Mono.just("work")
        .publishOn(Schedulers.parallel())
        .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(value + "@" + ctx.get("requestId"))))
        .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// block -> "work@req-101"
~~~

Here `flatMap` runs after `publishOn`; `deferContextual` still sees the ID. Adding another `publishOn(Schedulers.boundedElastic())` in the right chain likewise preserves the ID by default.

**Never call blocking I/O directly on the Netty event loop**, even when Context is intact. For unavoidable blocking integrations, use async APIs or wrap blocking parts with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with sensible resource caps. **Context does not make blocking code non-blocking**.

## 6. Standalone Reactor Example, Java 17+: Proving Subscription Isolation

File `src/main/java/demo/context/ReactorContextDemo.java` (in a project with `io.projectreactor:reactor-core`, such as a Spring Boot WebFlux project). Complete Java code:

~~~java
package demo.context;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    private static final String REQUEST_ID = "demo.requestId";

    public static void main(String[] args) {
        Mono<String> read = Mono.deferContextual(ctx ->
                Mono.just(ctx.get(REQUEST_ID)));

        // The same Publisher subscribed twice with two different contexts.
        String first = read
                .contextWrite(Context.of(REQUEST_ID, "req-A"))
                .block();
        String second = read
                .contextWrite(Context.of(REQUEST_ID, "req-B"))
                .block();

        Mono<String> switched = Mono.just("work")
                .publishOn(Schedulers.parallel())
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(value + "@" + ctx.get(REQUEST_ID))))
                .contextWrite(ctx -> ctx.put(REQUEST_ID, "req-C"));

        Mono<String> wrongScope = Mono.just("start")
                .contextWrite(ctx -> ctx.put(REQUEST_ID, "req-D"))
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.getOrDefault(REQUEST_ID, "missing"))));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("switched=" + switched.block());
        System.out.println("wrongScope=" + wrongScope.block());
    }
}
~~~

**Exact stdout of the `System.out.println` lines** (excluding any logging framework output):

~~~text
first=req-A
second=req-B
switched=work@req-C
wrongScope=missing
~~~

Explanation:

1. `read` does not hardcode an ID at declaration time. Each `block()` creates a new subscription with its own Context, so the two results are `req-A` and `req-B` without cross-talk.
2. `switched` reads the ID from Context **after a `publishOn` boundary** and still produces `req-C`.
3. `wrongScope` demonstrates ordering error: `contextWrite` sits too early in the chain so the following `flatMap` cannot see `req-D`.
4. `block()` is used solely in **`main`/demo runner** to wait for results and print to console. **Never copy `block()` into a WebFlux controller/handler**, as it risks blocking the event loop.

If your project uses Gradle with Reactor Core on the classpath, run this class via an `application`/JavaExec setup. In a Spring Boot project, the next HTTP example demonstrates the same principles without `block()`.

## 7. Attaching a Request ID from `WebFilter` into Spring Boot WebFlux Reactor Context

In WebFlux, the request originates at `ServerWebExchange`. A `WebFilter` can extract the `X-Request-Id` header, validate its format, generate an ID when absent, add a response header for correlation, and **attach the ID to Reactor Context for the entire chain**. Controllers/services read the ID via `deferContextual` even after scheduler hops.

**Example prerequisites:** Java 17+, Spring Boot 3.x, dependency `spring-boot-starter-webflux`; to use Reactor Netty by default, avoid also adding `spring-boot-starter-web` if you want Boot to auto-select `REACTIVE`. Standalone file:

`src/main/java/demo/context/ReactiveContextApplication.java`

~~~java
package demo.context;

import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveContextApplication {
    static final String REQUEST_ID_KEY = "demo.requestId";

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }

    @Bean
    WebFilter requestIdContextFilter() {
        return (exchange, chain) -> {
            String supplied = exchange.getRequest()
                    .getHeaders().getFirst("X-Request-Id");

            // Accept only safe-format IDs for the demo;
            // client-supplied headers are not trusted identities.
            String requestId = supplied != null
                    && supplied.matches("[A-Za-z0-9_-]{1,64}")
                    ? supplied
                    : UUID.randomUUID().toString();

            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);

            // Put contextWrite below chain so handlers upstream can read it.
            return chain.filter(exchange)
                    .contextWrite(ctx ->
                            ctx.put(REQUEST_ID_KEY, requestId));
        };
    }

    public record TraceResponse(String requestId, String stage) {}
}

@RestController
class TraceController {
    @GetMapping("/context")
    Mono<ReactiveContextApplication.TraceResponse> contextInfo() {
        return Mono.just("request")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> Mono.deferContextual(ctx -> {
                    String id = ctx.get(
                            ReactiveContextApplication.REQUEST_ID_KEY);

                    return Mono.just(
                            new ReactiveContextApplication.TraceResponse(
                                    id, "after-publishOn"));
                }));
    }
}
~~~

Steps of an HTTP request:

~~~text
GET /context
X-Request-Id: req-101
       |
       v
WebFilter reads/validates header, resolves requestId=req-101
       |
       v
chain.filter(exchange)
       |
       +-- .contextWrite(ctx -> ctx.put("demo.requestId", "req-101"))
                       |
                       | Context flows upstream on subscribe
                       v
          @GetMapping("/context")
                       |
                 Mono.just(...)
                       |
               publishOn(parallel)
                       |
               flatMap + deferContextual
                       |
         reads demo.requestId = req-101
                       |
                       v
                HTTP JSON response
~~~

**How to run:** in a Spring Boot 3.x project with Gradle wrapper configured, run `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`). On default port settings, invoke:

~~~bash
curl -i "http://localhost:8080/context" \
  -H "X-Request-Id: req-101"
~~~

Details to verify in the response:

~~~http
HTTP/1.1 200 OK
X-Request-Id: req-101
Content-Type: application/json

{"requestId":"req-101","stage":"after-publishOn"}
~~~

These are the **meaningful lines to inspect**, not a byte-for-byte full response: additional headers, header order, and framework body framing may vary. Seeing the ID appear after `publishOn` in `flatMap` proves Context follows the subscription. Actual worker thread names vary across runs, so output avoids asserting thread names.

Try sending another request with `X-Request-Id: req-202`. Its response must carry `req-202`; data is not an overwritten global static variable. If the header is omitted, the filter generates a UUID; both response header and JSON body must carry **that request's UUID**.

### 7.1. Why Does the Controller Receive Context Set in `WebFilter`?

`WebFilter` receives `ServerWebExchange` and returns `Mono<Void>` from `chain.filter(exchange)`. Attaching `contextWrite` **after** the entire filter chain's publisher makes the Context with the request ID visible to upstream operators inside handlers/controllers and services composed within that chain.

Never call:

~~~java
// WRONG: separate subscribe() inside filter instead of returning the chain to WebFlux.
// chain.filter(exchange).subscribe();
// return Mono.empty();
~~~

Manual subscription detaches processing from the HTTP lifecycle, loses error/completion/cancellation coordination, and breaks context boundaries. Always **return the publisher** to the framework.

### 7.2. Choosing Keys and Validating Input

Use clearly namespaced constants (`demo.requestId`) or dedicated key objects shared across layers. Reactor Context accepts any `Object` key; identical keys are scoped and overridden. The `X-Request-Id` header in the demo is restricted in length and character set for simplicity and basic log-injection safety; production apps should enforce trace ID generation/trust policies, proxy trust rules, and observability standards. **Never treat a client-supplied requestId as proof of authentication/authorization**.

Never put passwords, raw access tokens, payment data, or full request bodies into Context merely for "convenience" or logging. Context does not encrypt data, does not grant permissions, and is not a long-lived session store.

## 8. WebFlux: Services Reading Context Without Depending on HTTP Controllers

One advantage of Context is that services do not need an extra `requestId` parameter on every method just for logging/tracing. Illustrative **snippet**, reusing the key from Section 7:

~~~java
import reactor.core.publisher.Mono;

class AuditService {
    Mono<String> audit(String action) {
        return Mono.deferContextual(ctx -> {
            String requestId = ctx.getOrDefault(
                    ReactiveContextApplication.REQUEST_ID_KEY, "unknown");

            return Mono.just("action=" + action + ", requestId=" + requestId);
        });
    }
}
~~~

A controller can **compose** the service:

~~~java
// Inside a reactive chain whose Context was supplied by WebFilter:
return auditService.audit("read-book")
        .flatMap(logLine -> someReactiveOperation(logLine));
~~~

This is an illustrative snippet, not a standalone controller: `auditService` and `someReactiveOperation` must be defined/injected in an actual class. Context is read by the service at subscription time, even if the service lives in another module, provided the chain stays connected.

**Design consideration:** `requestId`, trace context, and locale for logging/observability are cross-cutting metadata; business inputs like `bookId`, purchase quantity, or monetary amounts belong in explicit parameters or domain models. Avoid turning Context into an untyped `Map<String,Object>` carrying everything: it obscures dependencies and invites missing-key failures.

## 9. Distinguishing From `ServerWebExchange`, Request Attributes, and `SecurityContext`

### 9.1. Use Exchange Attributes When You Have the Exchange

~~~java
// Inside a WebFilter or handler with ServerWebExchange:
exchange.getAttributes().put("auditMarker", "checked");
Object marker = exchange.getAttribute("auditMarker");
~~~

`ServerWebExchange` holds data tied to a specific HTTP exchange. Whenever every caller needing the data shares that exchange (passed as a parameter or reference), attributes are convenient. **Services that do not take an exchange do not automatically have it**, and you should avoid storing the entire exchange in Context just for small metadata, as holding large request objects can prolong object retention.

### 9.2. `WebClient` and Outbound HTTP Calls

A `WebClient` call **composed** inside a Reactor chain can read Reactor Context in a filter via `Mono.deferContextual`. However, **Reactor Context does not automatically turn into HTTP headers sent to other services**. To send correlation IDs over the network, explicitly set headers per your contract or tracing framework.

Illustrative outbound filter configuration snippet (requires imports `WebClient`, `ClientRequest`, `Mono` in a configuration class):

~~~java
WebClient client = WebClient.builder()
        .filter((request, next) ->
            Mono.deferContextual(ctx -> {
                String id = ctx.getOrDefault(
                        ReactiveContextApplication.REQUEST_ID_KEY,
                        "unknown");

                ClientRequest outbound = ClientRequest.from(request)
                        .headers(headers -> headers.set("X-Request-Id", id))
                        .build();

                return next.exchange(outbound);
            }))
        .build();
~~~

In production apps, standardize inter-service trace propagation and only forward headers to trusted destinations. Observability libraries may manage W3C Trace Context or other headers; avoid mixing conflicting propagation mechanisms manually.

### 9.3. Security: Do Not Reimplement Framework Mechanisms

Spring Security for WebFlux provides `ReactiveSecurityContextHolder`, using the security framework's own reactive context to retrieve `SecurityContext`. Example:

~~~java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(sc -> sc.getAuthentication().getName());
~~~

This snippet requires reactive Spring Security dependencies and an active authentication context; when unauthenticated, the publisher may be empty or authentication absent depending on configuration. Never manually stuff `"principal"` into Reactor Context and treat it as trusted identity; use official authentication/authorization mechanisms.

## 10. `ThreadLocal` / MDC Across Thread Switches: Why Data Vanishes and How to Handle It Properly

MDC in popular logging libraries typically relies on `ThreadLocal`. In a reactive request, early code may run on an event loop before signals switch to another scheduler's thread. **`ThreadLocal.get()` on the new thread does not automatically return values set on the previous thread**.

~~~java
// ERROR-PRONE PATTERN in a reactive app:
MDC.put("requestId", "req-101");

return Mono.just("x")
        .publishOn(Schedulers.parallel())
        .doOnNext(x -> log.info("processing {}", x));
// MDC on the publishOn thread may be empty or stale.
// Moreover, MDC set on the old thread risks leaking if not cleared properly.
~~~

This snippet illustrates a pitfall, not code to copy into handlers. Do not assume MDC is lost in every setup: libraries or frameworks may already enable **context propagation**. Understand the exact mechanism active in your project.

### 10.1. Two Distinct Layers

1. **Reactor Context propagation**: `contextWrite` and `deferContextual` operate natively inside Reactor; data travels with the subscription and normally survives `publishOn`/`subscribeOn` **without enabling any ThreadLocal bridge**.
2. **ThreadLocal ↔ Reactor Context propagation**: the Micrometer Context Propagation library can *capture* and *restore* selected ThreadLocals **registered via a `ThreadLocalAccessor`**. This is an extra integration layer bridging imperative code, MDC/observability, and reactive pipelines.

Modern Reactor supports **limited/default** mode (restoring at specific operators/points) and **automatic** mode (broader restoration). With Spring Boot 3.2/3.3 you can configure:

~~~properties
# Only when the app includes a compatible context-propagation library
spring.reactor.context-propagation=auto
~~~

This setting restores ThreadLocals that **have a registered accessor/bridge**; it does **not** mean any arbitrary `new ThreadLocal<>()` magically appears in Reactor Context. The feature carries runtime overhead; benchmark under load before enabling broadly. If enabling Reactor hooks directly (`Hooks.enableAutomaticContextPropagation()`), activate it at startup **before creating subscriptions**, while ensuring `io.micrometer:context-propagation` and suitable accessors are present.

**`contextCapture()`** snapshots registered ThreadLocal values at subscription time into Context when bridging from imperative code is genuinely needed. Crossing into an `ExecutorService`, `@Async`, `CompletableFuture`, or non-Reactor callbacks does not automatically carry Context across; use matching propagation/adapters or pass data explicitly. Never enable `auto` expecting it to cure every asynchronous boundary.

### 10.2. Logging Request IDs: Preferred Option

If you simply need an ID when logging inside a reactive operator, **read `ContextView` directly** and include the ID in the log message or structured logging fields. When restoring MDC is required for legacy log setups, rely on a **tracing/observability framework** or a bridge with registered accessors and proper ThreadLocal cleanup rather than calling `MDC.put` on the event loop and assuming threads never change.

An example logging directly from context without depending on MDC:

~~~java
Mono<Void> audited =
    Mono.deferContextual(ctx -> {
        String id = ctx.getOrDefault("demo.requestId", "unknown");
        System.out.println("received requestId=" + id);
        return Mono.empty();
    });
~~~

Production code should use a logger instead of `System.out`, yet the principle holds: **fetch the ID from Context at execution time**, avoiding thread-name dependence.

## 11. Scope and Lifecycle: Which Boundaries Lose Context?

### 11.1. Right: Compose Publishers, Let the Framework Subscribe

~~~java
Mono<String> response =
    repository.findById(id)
        .flatMap(entity -> service.enrich(entity))
        .flatMap(entity -> Mono.deferContextual(ctx ->
            Mono.just("requestId=" + ctx.get("demo.requestId"))));
~~~

This is an illustrative snippet; `repository`, `service`, `id`, and types are defined by the app. Inner publishers composed via `flatMap` belong to the reactive chain, so they read the right Context when subscription occurs.

### 11.2. Wrong: Manual Subscribe for "Fire and Forget"

~~~java
// WRONG in a request handler:
auditRepository.save(event).subscribe();
return Mono.just("ok");
~~~

`subscribe()` creates an independent subscription whose completion/error/cancellation the caller does not control; request metadata may fail to propagate, errors detach from the response, and work may outlive the response. If the work belongs in the request, compose and return the publisher:

~~~java
// Example when waiting for audit persistence before returning body:
return auditRepository.save(event)
        .thenReturn("ok");
~~~

For jobs that truly must run outside the request, push the event and required metadata onto a queue or dedicated worker system with an explicit contract for tracing, retries, and idempotency; never implicitly rely on HTTP request Context after the request ends.

### 11.3. Re-creating Publishers, `cache`, `share`, or External Boundaries

- **`Mono.defer` is not `Mono.deferContextual`**: the former defers publisher creation without supplying a `ContextView`.
- **`cache`/`share`/hot publishers** may share results or an already-running source across multiple subscribers. Context is per-subscriber metadata, yet cached/pushed values from a shared source do not magically become per-request values. Never cache tenant- or requestId-dependent results without including them in the cache key.
- **Non-Reactor API callbacks** cannot read Context automatically unless wrapped in a publisher with explicit data passing/bridging.
- **`CompletableFuture.supplyAsync(...)`** does not automatically receive subscriber context. Instead of reading `ThreadLocal` inside the async task, extract metadata from Context inside the reactive chain and pass it explicitly as arguments.
- **Modifying context in one branch** does not expose the new value to sibling branches or downstream operators. Trace `contextWrite` positions and publisher boundaries on a diagram.

## 12. Automated Testing: Context Must Hold Across Schedulers and Concurrent Requests

### 12.1. Pure Reactor Unit Tests with `StepVerifier`

File `src/test/java/demo/context/ReactorContextTest.java` (requires `io.projectreactor:reactor-test` and JUnit 5):

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    private static final String KEY = "demo.requestId";

    @Test
    void keepsRequestIdAfterPublishOn() {
        Mono<String> pipeline = Mono.just("event")
                .publishOn(Schedulers.parallel())
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(value + ":" + ctx.get(KEY))))
                .contextWrite(Context.of(KEY, "req-101"));

        StepVerifier.create(pipeline)
                .expectNext("event:req-101")
                .verifyComplete();
    }

    @Test
    void subscriptionsDoNotShareRequestIds() {
        Mono<String> lookup =
                Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        StepVerifier.create(lookup.contextWrite(Context.of(KEY, "A")))
                .expectNext("A")
                .verifyComplete();

        StepVerifier.create(lookup.contextWrite(Context.of(KEY, "B")))
                .expectNext("B")
                .verifyComplete();
    }

    @Test
    void contextWriteMustBeDownstreamFromReader() {
        Mono<String> misplaced = Mono.just("start")
                .contextWrite(ctx -> ctx.put(KEY, "A"))
                .flatMap(ignore -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.getOrDefault(KEY, "missing"))));

        StepVerifier.create(misplaced)
                .expectNext("missing")
                .verifyComplete();
    }
}
~~~

These three tests verify three separate properties: preservation across schedulers, isolation across subscriptions, and `contextWrite` scoping. Run with Gradle configured for JUnit Platform:

~~~bash
./gradlew test --tests demo.context.ReactorContextTest
~~~

These tests are designed **without relying on thread names** or timing sleeps, making them far more deterministic.

### 12.2. Spring WebFlux Integration Tests with `WebTestClient`

When running the Section 7 app, file `src/test/java/demo/context/ReactiveContextApplicationTest.java`:

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextApplicationTest {
    @Autowired
    WebTestClient client;

    @Test
    void readsSameRequestIdAfterSchedulerSwitch() {
        client.get().uri("/context")
                .header("X-Request-Id", "req-101")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Request-Id", "req-101")
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-101")
                .jsonPath("$.stage").isEqualTo("after-publishOn");
    }

    @Test
    void eachHttpRequestHasItsOwnId() {
        client.get().uri("/context")
                .header("X-Request-Id", "first")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("first");

        client.get().uri("/context")
                .header("X-Request-Id", "second")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("second");
    }
}
~~~

`RANDOM_PORT` starts an actual HTTP server on a dynamic port, while `WebTestClient` issues requests and asserts responses. This verifies that the filter populates Context in the HTTP lifecycle, the controller reads it after `publishOn`, and requests stay isolated. For parallel execution tests, add concurrency scenarios to verify isolation under load; two sequential requests here validate the happy path and **do not replace** load testing.

## 13. Common Pitfalls in Real Applications

| Symptom | Common cause | How to verify / fix |
| --- | --- | --- |
| `ctx.get("requestId")` reports missing key | Missing `contextWrite`, wrong key, or reader sits outside scope | Trace the chain from subscription point; move `contextWrite` downstream of readers |
| ID vanishes after `publishOn` | Actually caused by manual `subscribe()`, mistaking `ThreadLocal`/MDC for Reactor Context, or misplaced Context | Distinguish data sources clearly; use `deferContextual` within the same chain |
| Request A's ID appears in B | Mutable static field, uncleaned `ThreadLocal`, or caching request-dependent data | Remove globals; scope Context to subscription and fix cache keys |
| Logs lack correlation ID even though `deferContextual` reads it | MDC/ThreadLocal is not bridged/restored | Pass ID explicitly to logger or use configured observability/context-propagation |
| Service called via `WebClient` misses correlation header | Context exists only **inside the JVM/pipeline**, not automatically sent over HTTP | Set outbound headers in a WebClient filter/tracing integration |
| `Mono.block()` stalls server or errors on event loop | Blocking call in a reactive path | Return Mono/Flux, use async drivers, or offload blocking work onto the right scheduler |
| Same key has two values | A `contextWrite` closer to the reader overrides upstream values | Standardize key ownership, avoid overwriting framework context |
| Tests pass yet production breaks under concurrency | Shared mutable state, manual subscribe, broken ThreadLocal bridge | Test concurrently with distinct IDs, inspect trace/log context and external boundaries |

### Code Review Checklist

1. Is the data bound to a **thread**, an **exchange**, or a **subscription**? Can its lifecycle be explained clearly?
2. Is metadata written at a trusted `WebFilter`, subscriber, or boundary with consistent key names?
3. Do all services return `Mono`/`Flux` for framework composition, avoiding `subscribe()`/`block()` in handlers?
4. Is `contextWrite` placed properly **downstream** of reading operators? Do any sub-chains create detached subscribers?
5. Are `publishOn`, `subscribeOn`, `CompletableFuture`, `@Async`, `WebClient`, or message queues involved? Which boundaries need explicit bridging?
6. Are values stored in Context small, non-sensitive, safe from log leakage, and never misused as trusted authentication?
7. Do tests verify the ID survives scheduler switches and never leaks across concurrent requests?

## 14. Self-Check Exercises

**Exercise 1 — Reading order:** Why does the following produce `missing`?

~~~java
Mono<String> m = Mono.just("x")
    .contextWrite(c -> c.put("id", "A"))
    .flatMap(v -> Mono.deferContextual(c ->
        Mono.just(c.getOrDefault("id", "missing"))));
~~~

**Answer:** `flatMap` sits downstream of `contextWrite`, so it cannot see Context provided only to operators upstream of the write. Fix by moving `contextWrite(c -> c.put("id", "A"))` to the end of the chain after `flatMap`.

**Exercise 2 — Thread switch:** There is `publishOn(Schedulers.parallel())`, then `Mono.deferContextual(...)` in the same chain, with `contextWrite` at the end. Is the ID lost? → **No**, Context travels with the chain's subscriber. If the code relies on `ThreadLocal` or MDC instead, different rules apply.

**Exercise 3 — Two concurrent requests:** Should you store `currentRequestId` in a `static String` field for services to read? → **No**: mutable shared state will be overwritten by other requests. Attach metadata via Context/subscription or pass explicit parameters.

**Exercise 4 — Outbound WebClient:** Does placing `requestId` in Reactor Context cause external services to receive an `X-Request-Id` header? → **Not automatically**; you must use a filter/header or configured tracing library.

**Exercise 5 — MDC:** Does enabling `spring.reactor.context-propagation=auto` automatically propagate any arbitrary application-created `ThreadLocal`? → **No**; only values with matching accessors/bridges and within supported boundaries. Reactor Context read via `deferContextual` is a separate mechanism.

## 15. Official References

- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): definitions of Context, ContextView, `contextWrite`, `deferContextual`, and subscriber scoping.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, and schedulers.
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Reactor Context ↔ ThreadLocal bridge, `contextCapture`, and automatic mode.
- [Spring Framework — WebFlux WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): Context data in WebClient/filter chains.
- [Spring Framework — WebFlux Reactive Spring](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): request handling via `WebHandler`, `WebFilter`, and `ServerWebExchange`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.reactor.context-propagation`.
- [Spring Boot — Observability / Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): combining Micrometer observability and context propagation.

**Remember:** `ThreadLocal` follows the **thread**; Reactor `Context` follows the **subscriber**; `contextWrite` provides data to **upstream at subscription time**, and `deferContextual` reads it at runtime. Thus request data stays intact across `publishOn`/`subscribeOn` thread switches as long as you preserve composition and propagate explicitly across every external boundary.