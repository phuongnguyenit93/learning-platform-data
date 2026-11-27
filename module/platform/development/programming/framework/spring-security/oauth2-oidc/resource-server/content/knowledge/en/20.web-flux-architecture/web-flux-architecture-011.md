# Subscription Timing, Cancellation, and Context Propagation in the Processing Chain

In a **Spring Security OAuth 2.0 / OIDC Resource Server** written with **Spring WebFlux**, an HTTP request is not processed strictly under the “one fixed thread per request from start to finish” model. Instead, the application builds reactive processing chains (**reactive pipelines**) consisting of `Mono`, `Flux`, `WebFilter`s, Bearer Access Token authentication, authorization, data queries, and response writing.

Three concepts determine whether the design is sound:

1. **Subscription — when execution starts:** When is a Publisher actually subscribed to execute? What is merely *described* when Java calls a method without executing yet?
2. **Cancellation — unsubscribing:** What happens if a browser disconnects, a request times out, or an operator no longer needs data? How do you clean up resources, preserve transaction state, and avoid unintended side effects?
3. **Context propagation:** How is the `SecurityContext` containing the request's principal and authorities carried across operators, schedulers, reactive databases, or `WebClient` when a single thread cannot be assumed?

These concepts directly impact security: an `Authentication` read at the wrong time can become `null`, work spawned outside the subscription can bypass permission checks, and a canceled request does not guarantee prior writes were rolled back.

This lesson uses **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x, Reactor 3.x**, and a **WebFlux Resource Server accepting JWT Bearer Access Tokens**. Examples use an illustrative orders domain; if your project uses different versions, verify the exact APIs. The focus is on **subscription, cancellation, and Reactor Context in the security pipeline**, not configuring an OAuth 2.0 Authorization Server.

## 1. Picture of Processing a WebFlux HTTP Request

Suppose a client calls:

~~~http
GET /api/orders/8a4f...
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

In WebFlux, the request may flow through:

~~~text
Client / browser
       |
       | HTTP request + Bearer Access Token
       v
Reactive HTTP server (e.g., Reactor Netty)
       |
       v
WebFilter chain
       |
       +-- Reactor/WebFlux context setup
       +-- Bearer authentication
       |      +-- JWT decoder / validators
       |      +-- Authentication: JwtAuthenticationToken
       |
       +-- HTTP authorization
       |      +-- SCOPE_orders.read?
       |
       v
Handler / Controller returning Mono<OrderDto>
       |
       v
Service / reactive repository / WebClient
       |
       +-- Domain authorization: owner / tenant?
       +-- Data access: Mono / Flux
       |
       v
Encode response -> HTTP client
~~~

The diagram above depicts **responsibilities**—it does not mean every step runs on one thread or executes immediately when Java constructs a `Mono`.

| Component | Responsibility | Boundary to Watch |
| --- | --- | --- |
| `SecurityWebFilterChain` | Configures WebFlux security filters, Bearer auth, and rules. | Protects only exchanges matching the chain. |
| Reactive authentication | Verifies the Access Token and builds `Authentication`. | Invalid tokens must never become valid principals. |
| Reactor `Publisher` | Describes `onNext`, `onComplete`, and `onError` signals. | Work typically starts upon **subscribe**. |
| `Subscriber` / subscription | Consumes data and manages demand/cancellation. | Can cancel when the request no longer needs data. |
| `Reactor Context` | Carries subscription-level metadata. | Not equivalent to `ThreadLocal` or HTTP headers. |
| `ReactiveSecurityContextHolder` | Reads/writes SecurityContext via Reactor Context. | Depends on the current chain's subscriber context. |
| Reactive I/O | R2DBC/`WebClient`/streaming responses. | Cancel propagation and transactions must be designed explicitly. |

## 2. From Assembly to Subscription: Two Different Moments

In Reactor, many `Mono` and `Flux` instances are **cold publishers**: calling a method only **builds a description of a processing chain**; the work inside usually runs when a subscriber subscribes.

### 2.1. Assembly: Building the Processing Chain

~~~java
Mono<String> pipeline = Mono.just("order-42")
    .map(id -> {
        System.out.println("Processing " + id);
        return id.toUpperCase();
    });

System.out.println("Pipeline created");
~~~

At the moment `pipeline` is created, the lambda inside `map` has not necessarily executed. For this cold publisher example, the console output before subscription is only:

~~~text
Pipeline created
~~~

Because **no subscriber has requested data**, the `map` operator has no reason to emit `onNext`.

### 2.2. Subscription: Starting Chain Execution

~~~java
pipeline.subscribe(value ->
    System.out.println("Received result: " + value));
~~~

Upon subscription, the publisher begins emitting signals:

~~~text
Processing order-42
Received result: ORDER-42
~~~

If you subscribe a **second time** to the same cold pipeline, the lambdas execute **again**:

~~~java
pipeline.subscribe(System.out::println);
pipeline.subscribe(System.out::println);
~~~

This is crucial for business logic. A Publisher performing a database write or HTTP call **cannot be assumed to execute “exactly once”** if multiple subscriptions or retries occur. **Idempotency** and side-effect design must be handled explicitly.

### 2.3. Not Everything Is Lazy

Distinguish carefully:

~~~java
// value is computed before Mono.just is called.
Mono<String> eager =
    Mono.just(expensiveSynchronousCalculation());

// The function is called at subscription time.
Mono<String> lazy =
    Mono.fromCallable(() -> expensiveSynchronousCalculation());

// The Publisher is created at subscription time.
Mono<String> deferred =
    Mono.defer(() -> service.fetchName());
~~~

In this example:

- `Mono.just(value)` holds an **already-computed value**; the expression creating `value` runs eagerly at assembly time.
- `Mono.fromCallable(...)` defers a synchronous operation until subscription.
- `Mono.defer(...)` defers **creating the Publisher** until subscription, letting each subscriber observe fresh state.

If `expensiveSynchronousCalculation()` is blocking, `Mono.fromCallable` **does not magically make it non-blocking**; it only changes *when* it is called. When an unavoidable blocking library must be used, isolate it on a scheduler like `Schedulers.boundedElastic()` with timeouts and concurrency bounds. Better yet, use reactive drivers/APIs whenever possible.

### 2.4. Hot Publishers and Shared Publishers Differ from Cold Publishers

Never claim **every Publisher starts fresh on subscribe**. Hot publishers, `Sinks.Many`, `share()`, certain `cache()` patterns, or external event sources may emit ahead of time or share data across subscribers.

In an API with JWT user-specific context, **never share a Publisher holding a principal or personal data across multiple HTTP requests** without explicitly designing key boundaries, caching, expiry, and authorization. Reusing one hot/shared `Mono` improperly can **leak request A's data to request B**.

## 3. Who Calls Subscribe in WebFlux?

With Spring WebFlux annotated controllers or functional routers, the framework is responsible for **subscribing to the Publisher returned by the handler** to produce the HTTP response.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/api/demo")
    Mono<String> demo() {
        return Mono.defer(() -> {
            System.out.println("Executing reactive response");
            return Mono.just("ok");
        });
    }
}
~~~

The controller returns **`Mono<String>`**. WebFlux manages subscription, demand, errors, and cancellation in sync with the HTTP lifecycle.

### 3.1. Never Call subscribe() Manually in Controllers or Services

The following is a common architectural mistake:

~~~java
// DO NOT DO THIS.
@PostMapping("/api/orders")
Mono<Void> createOrder(@RequestBody OrderCommand command) {
    orderService.save(command).subscribe();
    return Mono.empty();
}
~~~

Problems:

1. `save(...).subscribe()` starts an **independent subscription** detached from the request chain managed by WebFlux.
2. The controller can return a success response **before the save finishes**.
3. Save errors bypass the request's error handling.
4. Client disconnects will not necessarily cancel that detached side effect.
5. The request's Reactor Context / SecurityContext **is not guaranteed to propagate intact** to the manually subscribed chain.
6. Transactions, tracing, and quotas/rate limits can be applied inconsistently.

The right way is **returning a Publisher representing the entire workflow**:

~~~java
@PostMapping("/api/orders")
Mono<Void> createOrder(@RequestBody OrderCommand command) {
    return orderService.save(command).then();
}
~~~

WebFlux subscribes to and manages that Publisher's subscription. If a true background job is needed, build an **independent job/queue system** with its own identity/service authorization, auditing, retries, and lifecycle rather than dropping `subscribe()` into a handler.

### 3.2. Use flatMap to Compose Asynchronous Operations

Wrong:

~~~java
// DO NOT DO THIS: Mono<Mono<OrderDto>> does not express
// the intended data pipeline.
Mono<Mono<OrderDto>> nested =
    Mono.just(orderService.findById(orderId));
~~~

Right:

~~~java
Mono<OrderDto> result =
    Mono.just(orderId)
        .flatMap(orderService::findById);
~~~

Or return directly:

~~~java
return orderService.findById(orderId);
~~~

`map` is for **synchronous** value transformations; `flatMap` chains **asynchronous Publishers**. Composing Publishers inside a single pipeline preserves cancellation, error propagation, and Reactor Context by design.

## 4. Subscription and Backpressure

Reactive Streams defines the protocol between Publisher and Subscriber:

~~~text
Subscriber
    |
    | onSubscribe(Subscription)
    | request(n)  -> requests n elements
    | cancel()    -> wants no more items
    v
Publisher
    |
    | onNext(value)
    | onError(error)  or  onComplete()
    v
Subscriber
~~~

A `Mono` typically emits at most one value; a `Flux` can emit many values. **Backpressure** lets subscribers express demand instead of letting producers push unbounded data.

Example streaming a large list:

~~~java
@GetMapping(
    value = "/api/events",
    produces = "text/event-stream")
Flux<EventDto> events() {
    return eventService.streamAuthorizedEvents();
}
~~~

An event stream can stay open for a long time; **cancellation and cleanup** become critical when a browser closes a tab or drops the connection. However, pausing or requesting items still depends on drivers and upstream sources. Never assume an arbitrary external API supports full backpressure merely because it is wrapped in a `Flux`.

## 5. Three Terminal Signals: Complete, Error, and Cancel

In Reactor, a sequence can end via:

| Outcome | Meaning | Example |
| --- | --- | --- |
| **Complete** | Publisher finished normally. | Found a record and completed. |
| **Error** | Publisher terminated with an error. | Database error, invalid JWT, or access denied emitted as an error. |
| **Cancel** | Subscriber signaled it needs no more items. | Browser aborted request, `take(1)`, or `timeout` canceled upstream. |

**Cancellation is not an `onError`.** On cancel, a publisher generally does not receive an error signal or run `onErrorResume` the way normal exceptions do.

### 5.1. doOnSubscribe and doFinally

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<String> operation = Mono.defer(() -> {
        System.out.println("Starting work on subscription");
        return Mono.just("done");
    })
    .doOnSubscribe(subscription ->
        System.out.println("Subscribed"))
    .doFinally(signalType ->
        System.out.println("Terminated with " + signalType));
~~~

`doOnSubscribe` runs when subscription reaches that operator position. `doFinally` observes termination for:

- `SignalType.ON_COMPLETE`
- `SignalType.ON_ERROR`
- `SignalType.CANCEL`

Never use `doOnComplete` for universal cleanup because it never runs on cancellation. `doOnError` also does not run simply because a subscriber canceled.

### 5.2. doOnCancel and doFinally Differ

~~~java
Flux<EventDto> stream = eventService.stream()
    .doOnCancel(() -> metrics.incrementCancellation())
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.recordClientOrOperatorCancellation();
        }
    });
~~~

`doOnCancel` is a hook specific to cancellation at that operator position. `doFinally` observes all termination types and receives the cause; `doFinally` callbacks execute after termination paths per operator semantics. Never rely on hooks to **guarantee a business transaction has not produced side effects**, because the action may already have happened before the cancel signal arrived.

### 5.3. timeout Can Turn Upstream Cancel into Downstream Error

~~~java
Mono<OrderDto> result =
    orderService.load(orderId)
        .doFinally(signal ->
            metrics.recordUpstreamSignal(signal))
        .timeout(Duration.ofSeconds(2))
        .doOnError(TimeoutException.class,
            error -> metrics.recordTimeout());
~~~

When a timeout fires, `timeout` **cancels upstream** and emits `TimeoutException` downstream:

~~~text
Upstream: CANCEL
Downstream: onError(TimeoutException)
~~~

So when recording logs or metrics, know whether a hook sits **before or after `timeout`**. An API timeout does not mean an external database, remote HTTP, or payment operation was canceled remotely.

## 6. When Is an HTTP Request Canceled?

In WebFlux, cancellation can occur when:

1. A browser closes a tab, navigates away, or calls `AbortController.abort()`.
2. A client closes the TCP/HTTP stream and the server detects the connection has no receiver.
3. Operators like `take(1)`, `firstWithSignal`, or `switchMap` no longer need the previous source.
4. `timeout(...)` stops waiting on the upstream source.
5. A downstream caller cancels its subscription or limits item counts.
6. The server shuts down or the application stops streams under shutdown conditions.

Frontend example:

~~~javascript
const controller = new AbortController();

const promise = fetch("https://api.example.test/api/orders", {
  headers: {
    Authorization: "Bearer " + accessToken
  },
  signal: controller.signal
});

// When the user navigates away:
controller.abort();
~~~

The browser stops waiting for the response; once the server detects the disconnect, WebFlux propagates cancellation to the reactive publisher. **How fast and how far propagation travels depends on the HTTP server, I/O type, drivers, and timing.** Never assume cancel always occurs instantaneously or reaches every remote component.

### 6.1. Cancel Does Not Roll Back Every Side Effect

Suppose a request creates an order:

~~~text
T0: API begins INSERT order
T1: Database commits successfully
T2: Browser closes connection
T3: WebFlux sees cancel, cannot send response
T4: Client thinks the operation failed
~~~

The order may still **have been created** at T1. Therefore:

- Use **idempotency keys** or deduplication mechanisms for critical write transactions.
- Provide a status-lookup endpoint so clients can verify actual outcomes after timeouts or cancels.
- Never automatically retry non-idempotent writes without explicit rules.
- For distributed workflows, use appropriate business patterns such as outbox, saga, or compensation.

Cancellation is a **subscription demand/lifecycle signal**, not a promise that “no data changed”.

### 6.2. Cancellation with WebClient

~~~java
Mono<InventoryDto> remote = webClient.get()
    .uri("/inventory/{sku}", sku)
    .retrieve()
    .bodyToMono(InventoryDto.class)
    .timeout(Duration.ofSeconds(3));
~~~

When downstream cancels, Reactor Netty/`WebClient` stops waiting for the response and closes/cancels local activity. **However, the inventory service may already have received and processed the request**; client cancellation does not guarantee a business rollback on the remote server.

For HTTP GETs that are side-effect-free by contract, the impact is only local resources and I/O cost. For POSTs to external services, design **idempotency, timeouts, retries, and transaction boundaries**.

## 7. Cleaning Up Resources Properly on Cancel

A pipeline may open:

- Database connections/transactions.
- Streaming subscriptions to a message broker.
- File handles or data streams.
- Remote HTTP calls.
- Locks, leases, or resource pool slots.

If cleanup only runs in `doOnComplete`, canceled requests can hold resources longer than intended.

### 7.1. usingWhen for Asynchronous Resources

Reactor provides `usingWhen` to manage a resource with **asynchronous cleanup** across complete, error, and cancel branches:

~~~java
import reactor.core.publisher.Mono;

// Assuming methods returning asynchronous Publishers:
// Mono<Lease> acquireLease()
// Mono<OrderDto> readOrder(Lease lease, UUID orderId)
// Mono<Void> releaseLease(Lease lease)

Mono<OrderDto> loadWithLease(UUID orderId) {
    return Mono.usingWhen(
        acquireLease(),
        lease -> readOrder(lease, orderId),
        lease -> releaseLease(lease),             // complete
        (lease, error) -> releaseLease(lease),    // error
        lease -> releaseLease(lease)              // cancel
    );
}
~~~

`acquireLease`, `readOrder`, `releaseLease`, and `Lease` are **illustrative types to implement**, not built-in Reactor APIs. The core point is that cleanup is expressed as a **Publisher**, never a blocking operation inside an event-loop callback.

If cleanup fails, define clear error observability and state recovery policies. Never swallow cleanup failures just to return a misleading HTTP 200. Ensure release operations are not invoked **twice** if the resource lifecycle is non-idempotent; design all termination paths safely.

### 7.2. doFinally Does Not Replace usingWhen

~~~java
return source
    .doFinally(signal -> {
        logger.debug("Order stream finished: {}", signal);
    });
~~~

`doFinally` is suited for metrics, logging, and brief side effects—**not for calling `block()` while waiting to close a resource**. For lifecycle-coordinated asynchronous cleanup, use `usingWhen`, reactive transaction management, or equivalent resource APIs.

### 7.3. R2DBC Transactions and Cancellation

For reactive databases, Spring manages transactions via **Reactor Context**, not by pinning execution to one thread. Example:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

class OrderApplicationService {

    private final OrderRepository orders;
    private final TransactionalOperator tx;

    OrderApplicationService(
            OrderRepository orders, TransactionalOperator tx) {
        this.orders = orders;
        this.tx = tx;
    }

    Mono<OrderEntity> updateNote(UUID id, String newNote) {
        return orders.findById(id)
            .switchIfEmpty(
                Mono.error(new IllegalArgumentException("Not found")))
            .flatMap(order -> {
                order.setNote(newNote);
                return orders.save(order);
            })
            .as(tx::transactional);
    }
}
~~~

In this example, `OrderRepository` and `OrderEntity` are illustrative components. `TransactionalOperator` wraps the transaction lifecycle around the subscribed Publisher. Spring reactive transactions **roll back on errors and handle cancellation according to transaction manager/driver semantics**; however, never assume cancellation **always** undoes changes that already committed.

A completed `commit` cannot be reversed merely because a subscriber canceled. For critical operations, add **transactional constraints, optimistic locking, idempotency keys, and auditing**.

## 8. What Is Reactor Context?

`Reactor Context` is **data bound to the subscriber/subscription**, **immutable** by API design. It carries contextual metadata along a Reactor chain without relying on a fixed thread.

Examples of data suitable for Context:

- Request correlation ID.
- Appropriate tracing metadata.
- Verified locale or tenant selection.
- Spring Security's SecurityContext.
- Reactive transaction context.

Never treat Context as a dumping ground for arbitrary request inputs or credentials. Operators in the chain can inspect Context; restrict sensitive data to its intended purpose and never log or serialize the entire context verbatim.

### 8.1. contextWrite to Supply Context

~~~java
import reactor.core.publisher.Mono;

Mono<String> publisher =
    Mono.deferContextual(contextView -> {
        String requestId =
            contextView.getOrDefault("requestId", "unknown");
        return Mono.just(requestId);
    })
    .contextWrite(context ->
        context.put("requestId", "req-42"));
~~~

Upon subscription, `Mono.deferContextual` reads `requestId` from Context.

~~~java
publisher.subscribe(System.out::println);
// req-42
~~~

Important:

- `contextWrite` creates a new context rather than mutating a global `Map`.
- In Reactor, context **propagates from the downstream subscriber upward to upstream operators**. Where you place `contextWrite` determines which operators see the value.
- `deferContextual` reads context **at subscription time**, not prematurely at assembly time.
- Context keys can be overridden by outer/inner `contextWrite` calls; define clear precedence if sharing keys.

### 8.2. Context Is Not a Global Request Variable

Example:

~~~java
Mono<String> base = Mono.deferContextual(
    ctx -> Mono.just(ctx.get("requestId")));

Mono<String> one = base.contextWrite(
    ctx -> ctx.put("requestId", "request-A"));

Mono<String> two = base.contextWrite(
    ctx -> ctx.put("requestId", "request-B"));
~~~

Two different subscribers receive **different contexts** without mutating any static variable:

~~~text
Subscriber A -> request-A
Subscriber B -> request-B
~~~

This is an essential property of the reactive model: many HTTP requests can multiplex onto a small pool of threads without ever mixing principals or correlation IDs.

## 9. Reactor Context Differs from ThreadLocal and SecurityContextHolder

In traditional Spring MVC Servlet applications, developers commonly write:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, a single request may switch across multiple schedulers and threads. **Traditional thread-bound `SecurityContextHolder`** is not the right way to retrieve the security context inside a reactive pipeline.

Instead, Spring Security provides:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

to obtain **`Mono<SecurityContext>`** from **Reactor Context**.

### 9.1. Why Is ThreadLocal Error-Prone?

~~~text
Request A starts on thread-1
    |
    +-- publishOn(scheduler-X)
    |      -> next operator runs on thread-7
    |
    +-- WebClient -> async callback / another thread

Concurrent Request B uses thread-1 or thread-7
~~~

If you keep `currentUser` in a self-managed `ThreadLocal`:

- Operators may **fail to see** the user after a thread switch.
- A ThreadLocal lacking proper cleanup risks retaining a **previous request's data**.
- Callbacks on other threads may miss tracing or security context.

Reactor Context travels with the **subscription**, fitting reactive chains naturally. Do not manually “copy ThreadLocal into Reactor Context” in every service, as that can feed untrusted sources into authorization.

### 9.2. Switching Threads Keeps Reactor Context in the Pipeline

~~~java
Mono<String> result =
    Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId")))
        .publishOn(Schedulers.parallel())
        .map(id -> "processed:" + id)
        .contextWrite(ctx ->
            ctx.put("requestId", "req-100"));
~~~

`publishOn` changes the scheduler executing subsequent operators, yet **Reactor Context remains the subscription's context** along that chain. This differs from ThreadLocal, which is not automatically inherited across threads.

If an application integrates libraries that only support ThreadLocal (such as MDC logging), configure an explicit **context propagation** bridge such as Micrometer context-propagation with Reactor rather than assuming MDC copies automatically.

### 9.3. Never Equate Context with HTTP Headers

The Bearer token arrives in an HTTP header and is processed by the Spring Security authentication filter. **SecurityContext** is the verified result Spring Security places into the reactive context.

Never write:

~~~java
String user = request.getHeaders().getFirst("X-User");
~~~

in place of SecurityContext, because caller-controlled headers are not proof of authentication. When a tenant ID is needed, verify trusted tenant claims from the Access Token and membership/domain policies—never trust `X-Tenant-ID` by default.

## 10. Where Does Spring Security WebFlux Store Authentication?

With **WebFlux Security**, SecurityContext is maintained via Reactor Context by reactive security infrastructure. In a Bearer JWT Resource Server, a successful Authentication may be `JwtAuthenticationToken`; authorities are typically `SCOPE_...` mapped from token claims.

~~~text
HTTP Authorization: Bearer JWT
              |
              v
Reactive authentication web filter
              |
              v
ReactiveJwtDecoder
  - signature, issuer, audience, exp, nbf...
              |
              v
JwtAuthenticationToken
  - principal Jwt
  - authorities SCOPE_orders.read
              |
              v
SecurityContext
              |
              v
Subscription's Reactor Context
              |
              v
ReactiveSecurityContextHolder.getContext()
              |
              v
Controller / Service / method authorization
~~~

A token with an invalid signature or wrong audience must be rejected **before** becoming a valid `Authentication`. Being able to read a `SecurityContext` does not prove the caller has permissions for a specific order or tenant; enforce downstream authorization too.

### 10.1. Configuring SecurityWebFilterChain for JWT

In Spring WebFlux use **`SecurityWebFilterChain`** and **`ServerHttpSecurity`**, not Servlet MVC's `SecurityFilterChain` and `HttpSecurity`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Suitable for pure Bearer-header APIs without session cookies
            // as credentials. Do not copy to web OIDC Login.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/public/ping").permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

On Spring Boot versions supporting `audiences`, that property requires Access Tokens intended for `orders-api`; otherwise, configure a corresponding reactive JWT decoder/audience validator. **Verify signature, issuer, audience, and timestamps** before trusting the principal.

The `csrf.disable()` example applies solely to **stateless APIs using Bearer tokens in headers** with no cookies/sessions used for automatic authentication. Web session / OIDC Login flows require an appropriate CSRF strategy.

### 10.2. Security Filter Order and Reactive Lifecycle

`SecurityWebFilterChain` comprises multiple `WebFilter`s performing authentication, authorization, exception translation, and related policies. They coordinate via **Publishers**; never insert blocking code or `subscribe()` inside a WebFilter to “wait for the token”.

When a custom `WebFilter` needs user information, **compose** reactive operations and use `ReactiveSecurityContextHolder`. Depending on **filter order** in the chain, Authentication may not yet be populated; never read `null` early and cache it for the rest of the request.

## 11. Reading SecurityContext at the Right Moment in Mono/Flux

Example service retrieving the subject from a verified JWT:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentSubjectService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .map(auth -> auth.getToken().getSubject())
            .filter(subject ->
                subject != null && !subject.isBlank())
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated JWT principal required")));
    }
}
~~~

Key points:

- **Never call `block()`** trying to fetch SecurityContext in non-blocking request processing.
- `ReactiveSecurityContextHolder.getContext()` returns a **Mono**, letting Spring Security read from the subscriber context upon subscription.
- `JwtAuthenticationToken` is the right Authentication type **when configured for JWT**. An opaque Resource Server may use a different Authentication type.
- Never fabricate a fake `Authentication` when context is missing.
- `switchIfEmpty` in this example denies when no valid principal exists; exact HTTP status depends on exception handling.

### 11.1. Controller Returning a Publisher Using SecurityContext

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record MyProfile(String subject) {}

@RestController
class MeController {

    private final CurrentSubjectService currentSubjectService;

    MeController(CurrentSubjectService currentSubjectService) {
        this.currentSubjectService = currentSubjectService;
    }

    @GetMapping("/api/me")
    Mono<MyProfile> me() {
        return currentSubjectService.currentSubject()
            .map(MyProfile::new);
    }
}
~~~

To expose `/api/me`, add the HTTP rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/me").authenticated()
~~~

before `anyExchange().denyAll()`. The controller and service illustrate **consuming SecurityContext without manually subscribing**. Production endpoints must decide which data may be returned and whether local user mapping is required.

### 11.2. Never Read SecurityContext Once in a Constructor

Wrong:

~~~java
// DO NOT DO THIS.
@Service
class UnsafeIdentityService {

    private final Authentication current =
        SecurityContextHolder.getContext()
            .getAuthentication();

    // Singleton service would hold a null/stale Authentication
    // unrelated to the current request.
}
~~~

Spring `@Service` beans are usually singletons, while Authentication is **per request/subscription**. Never cache a request principal in a singleton or static field. In WebFlux, retrieve it **inside the chain** at use time—never store it in global fields.

### 11.3. defer and deferContextual for Request Data

~~~java
Mono<String> requestId =
    Mono.deferContextual(contextView -> {
        String id =
            contextView.getOrDefault("requestId", "unknown");
        return Mono.just(id);
    });
~~~

`deferContextual` is suited for **custom Reactor Context keys**. For authenticated principals and authorities, **prefer `ReactiveSecurityContextHolder`** rather than building a custom `currentUser` map outside security infrastructure to replace Spring Security.

## 12. contextWrite and Operator Placement

Reactor Context propagates **from the downstream subscriber upstream**. Example:

~~~java
Mono<String> source =
    Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "missing")));

Mono<String> result =
    source.contextWrite(context ->
        context.put("requestId", "abc-123"));
~~~

When subscribing to `result`, `source` sees `requestId=abc-123`.

### 12.1. Context Is Immutable, Not Shared Mutable State

~~~java
Mono<String> resultA = source.contextWrite(
    context -> context.put("requestId", "A"));

Mono<String> resultB = source.contextWrite(
    context -> context.put("requestId", "B"));
~~~

No global `Map` is mutated; each subscription has its own context. To replace a value in a pipeline, apply `contextWrite` and pass the resulting publisher—never write to shared singleton fields.

### 12.2. contextWrite Cannot Rescue a Manually Subscribed Chain

Wrong:

~~~java
Mono<String> result = Mono.deferContextual(
    ctx -> Mono.just(ctx.get("requestId")));

result.subscribe(value -> audit(value)); // Separate subscription

return Mono.empty()
    .contextWrite(ctx -> ctx.put("requestId", "req-42"));
~~~

The subscription created by `result.subscribe()` **is not a subscriber** of the Publisher returned on the last line; `contextWrite` on the returned Publisher **does not apply** to the earlier subscription.

The right approach keeps **one Publisher chain**:

~~~java
return result
    .flatMap(value -> auditReactive(value))
    .contextWrite(ctx -> ctx.put("requestId", "req-42"))
    .then();
~~~

In this example, `auditReactive(value)` must return a `Publisher` and be non-blocking. For security context, rely on the context established by Spring Security rather than injecting client-supplied user values.

## 13. Why Thread Switches Preserve Reactor Context, While CompletableFuture May Lose It

When using:

~~~java
return reactiveRepository.findById(id)
    .publishOn(Schedulers.parallel())
    .flatMap(this::transformAsync);
~~~

Reactor Context stays with the Publisher chain as long as operations continue using Reactor operators properly. **Not** because `SecurityContextHolder` ThreadLocal is copied automatically, but because context belongs to the subscriber.

### 13.1. subscribeOn vs. publishOn

| Operator | Common Purpose | Context Behavior |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Controls which scheduler runs subscription/upstream work per Reactor semantics. | Reactor Context continues along the subscriber chain. |
| `publishOn(scheduler)` | Switches execution context for downstream operators. | Reactor Context continues along the chain; ThreadLocal is not guaranteed. |
| `flatMap(publisherFunction)` | Chains asynchronous Publishers. | Reactor propagates subscriber context into inner subscriptions. |
| Manual `subscribe()` | Creates a new subscription. | **Not guaranteed** to receive the running request's context. |
| `CompletableFuture.supplyAsync(...)` | Runs work outside Reactor. | Does not automatically see Reactor Context inside callbacks. |

If you must use `CompletableFuture`-based libraries, wrap them with `Mono.fromFuture` or appropriate adapters and **pass needed context explicitly as immutable data** when crossing boundaries unaware of Reactor Context. Never expect `ReactiveSecurityContextHolder.getContext()` to magically work inside every non-subscription Java callback.

### 13.2. Passing the Principal as Controlled Data

A clean pattern:

~~~java
record VerifiedUser(String subject, String tenantId) {}

Mono<OrderDto> loadForCurrentUser(UUID orderId) {
    return currentUserService.verifiedUser()
        .flatMap(user ->
            orderRepository.findForUser(
                orderId, user.subject(), user.tenantId()));
}
~~~

Here `verifiedUser()` must retrieve the principal from Spring Security and validate the token/domain contract. `findForUser` must enforce owner/tenant constraints via database predicates. This is **explicit post-authentication data passing**, not forging a security context or trusting a client-sent `userId`.

## 14. Reactive Method Security and When Permissions Are Checked

Spring Security supports method authorization for WebFlux:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Example:

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReader {

    private final OrderRepository orders;

    public OrderReader(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> read(UUID orderId) {
        return orders.findById(orderId)
            .map(OrderDto::fromEntity);
    }
}
~~~

Spring Security evaluates reactive method authorization using the **subscription's SecurityContext**. For methods returning `Mono`/`Flux`, permissions are checked **inside the subscribed chain**, rather than relying on ThreadLocal at assembly time. Furthermore, annotations/proxies only take effect when invoked **through the Spring-managed proxy**.

### 14.1. Why Avoid Eager Side Effects in Protected Methods?

Do not write:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public Mono<OrderDto> create(OrderCommand command) {
    externalSystem.sendSynchronously(command); // Do not do this!
    return reactiveOrders.save(command);
}
~~~

`sendSynchronously` executes as a side effect **the moment the Java method body is called**, instead of being deferred inside the Publisher. In reactive architecture, never place side effects outside authorization, transaction, and cancellation controls.

A cleaner design:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public Mono<OrderDto> create(OrderCommand command) {
    return validateReactive(command)
        .then(reactiveOrders.save(command));
}
~~~

`validateReactive` and `reactiveOrders.save` are illustrative Publisher-returning methods. When external side effects cannot be rolled back, add idempotency and workflow safeguards. Never put unguarded payment/mutation calls inside `doOnNext`, since `retry` or multiple subscriptions can replay side effects.

### 14.2. Self-Invocation Remains an Issue

If a `@PreAuthorize` method lives on a Spring bean and another method on the **same instance** calls it via `this`, the proxy is bypassed. Example:

~~~java
@Service
class UnsafeService {

    Mono<Void> process(UUID id) {
        return delete(id); // Self-invocation may bypass the proxy
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.delete')")
    public Mono<Void> delete(UUID id) {
        return Mono.empty();
    }
}
~~~

Never rely solely on an annotation if internal calls bypass the proxy. Extract protected methods into separate beans, guard entry points, and keep domain checks close to writes. Test both WebFlux controller paths and cross-service invocation paths.

### 14.3. Method Arguments Are Still Untrusted Data

`@PreAuthorize("hasAuthority('SCOPE_orders.read')")` only checks general read authority. When a method takes `orderId`, domain logic must verify the record belongs to the current user/tenant. Never use path, query, or body `ownerId` as proof of permission; rely on principals from verified tokens and database state.

## 15. WebFlux Service Example Using Security Context in the Pipeline

Suppose `GET /api/orders/{orderId}` must verify:

1. The JWT Access Token was authenticated by the Resource Server.
2. The caller holds `SCOPE_orders.read`.
3. The user has an ACTIVE local account and the order belongs to that tenant and user.

The HTTP rule blocks missing scopes first:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

The service enforces data-level constraints:

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuthorizedOrderService {

    private final LocalIdentityService identities;
    private final OrderRepository orders;

    public AuthorizedOrderService(
            LocalIdentityService identities,
            OrderRepository orders) {
        this.identities = identities;
        this.orders = orders;
    }

    public Mono<OrderDto> findAuthorized(UUID orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .ofType(JwtAuthenticationToken.class)
            .flatMap(auth -> {
                URI issuer = auth.getToken().getIssuer();
                String subject = auth.getToken().getSubject();
                Object rawTenant =
                    auth.getToken().getClaims().get("tenant_id");

                if (issuer == null
                        || subject == null
                        || subject.isBlank()
                        || !(rawTenant instanceof String tenant)
                        || tenant.isBlank()) {
                    return Mono.error(new AccessDeniedException(
                        "Account context unavailable"));
                }

                return identities.findActiveUserId(
                        issuer.toString(), subject)
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                            "Account context unavailable")))
                    .flatMap(userId ->
                        orders.findByIdAndTenantIdAndOwnerUserId(
                            orderId, tenant, userId))
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                            "Order access not permitted")))
                    .map(OrderDto::fromEntity);
            })
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated JWT principal required")));
    }
}
~~~

Here:

- `LocalIdentityService.findActiveUserId(issuer, subject)` is an **illustrative business interface** returning `Mono<UUID>`, looking up mappings by the **(issuer, subject) pair** and returning only ACTIVE accounts.
- `OrderRepository.findByIdAndTenantIdAndOwnerUserId` is an illustrative reactive repository method returning `Mono<OrderEntity>`; real queries must enforce owner/tenant predicates in the database.
- `OrderDto.fromEntity` is the application mapper.
- Denied responses emit `AccessDeniedException`; map and test HTTP statuses through WebFlux exception handling.
- Never use `block()`, `subscribe()`, static user fields, or self-declared request headers to resolve principals.

### 15.1. Why Does This Pipeline Preserve the Right Subscription Context?

When WebFlux subscribes to `findAuthorized(...)`, it uses the subscriber context established by the security filters. `ReactiveSecurityContextHolder.getContext()` reads Authentication from that context, and `flatMap` passes verified identity into the database-query Publishers. If the client cancels the request, cancellation can propagate into those publishers per driver support.

Calling `findAuthorized(...)` in Java **does not re-validate tokens** or run queries eagerly at assembly time. Tokens are already verified in the WebFlux security filter chain; the method simply retrieves the principal from the subscription context while processing the request.

### 15.2. Never Build a Shared Publisher Holding Request A's User

Wrong:

~~~java
// DO NOT DO THIS: singleton cache easily retains user data across contexts.
private Mono<String> cachedCurrentSubject;

public Mono<String> subject() {
    if (cachedCurrentSubject == null) {
        cachedCurrentSubject =
            currentSubjectService.currentSubject().cache();
    }
    return cachedCurrentSubject;
}
~~~

If `cache()` on a publisher reading SecurityContext is shared in a singleton, **the first subscriber's value** can be replayed to later requests, causing cross-user data leakage.

Never cache `Authentication` or the current user directly on a singleton. When caching resources, key by identity/tenant/resource and policy version, enforce TTL and invalidation, and still check permissions per request.

## 16. Context and WebClient: Same Process vs. Calling a Remote Service

When a WebFlux service invokes `WebClient`:

~~~java
Mono<InventoryDto> inventory =
    webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryDto.class);
~~~

A `WebClient` Publisher composed into the same Reactor pipeline can access the caller's Reactor Context **within the current process**. However, **Reactor Context does not travel across the HTTP network to service B**.

### 16.1. Never Automatically Relay Every Bearer Token

Suppose an Access Token is issued with:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "person-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

`orders-api` receives that token and calls `inventory-api`. Do not blindly attach:

~~~text
Authorization: Bearer <original orders-api token>
~~~

to every downstream service. The token has `aud=orders-api` and **is not necessarily authorized for inventory-api**. If passed verbatim, downstream must verify audience/token profile and reject mismatches.

When delegated access / on-behalf-of is required:

- Use **OAuth 2.0 Token Exchange** or an Authorization Server-supported flow to obtain a token scoped for the downstream audience, if that fits the product model.
- For service-to-service calls not acting on behalf of a user, use client credentials / appropriate service identities.
- Pass minimal internal identity/context payloads only across an explicit trust boundary with service authentication/signatures; never trust client-supplied `X-User-Id`.
- Never log Access Tokens in `WebClient` filters, tracing, or HTTP diagnostics.

### 16.2. WebClient Calls Must Still Stay Inside the Pipeline

Wrong:

~~~java
// DO NOT DO THIS.
webClient.post()
    .uri("/audit")
    .retrieve()
    .bodyToMono(Void.class)
    .subscribe();

return orderRepository.save(order);
~~~

The audit call is a detached subscription: there is no ordering, transaction, cancellation, or context coordination with `save`. Intentional Publisher composition:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        auditClient.recordCreated(saved)
            .thenReturn(saved));
~~~

`auditClient.recordCreated` must return `Mono<Void>` or a compatible Publisher. Even then, **a database save and an HTTP audit POST do not automatically form a distributed transaction**. When audit records cannot be lost, consider a transactional outbox or event-driven pattern, and handle cancellations between steps with idempotency and recovery.

## 17. ThreadLocal MDC and Trace Context: Do Not Confuse with SecurityContext

In traditional logging, many libraries use ThreadLocal-backed **MDC (Mapped Diagnostic Context)**:

~~~java
MDC.put("requestId", requestId);
~~~

Because WebFlux requests can switch threads, MDC may:

- Lose `requestId` in operators after `publishOn`.
- Retain stale values if callbacks miss cleanup.
- Mix up users or requests when threads are reused.

### 17.1. Use Reactor Context for Request Metadata

~~~java
Mono<String> work = Mono.deferContextual(context -> {
    String requestId =
        context.getOrDefault("requestId", "unknown");
    logger.info("requestId={}", requestId);
    return Mono.just("ok");
});
~~~

`requestId` is read from the subscription context without requiring every operator to stay on the same thread.

### 17.2. Integrating Libraries That Require ThreadLocal

Depending on your Reactor/Micrometer versions, a **context-propagation** integration can capture and restore selected ThreadLocal values across appropriate scopes. That is an operational configuration concern, **not proof that all ThreadLocals automatically work in WebFlux**.

Never turn on global automatic propagation just to “patch” misused `SecurityContextHolder` calls without evaluating performance, scheduling, and cleanup impacts. For authorization, prefer **`ReactiveSecurityContextHolder`** and pass verified data explicitly when leaving the Reactor chain.

## 18. Passing Context Across a Custom WebFilter Boundary

A custom reactive `WebFilter` can supply a correlation ID downstream:

~~~java
import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            org.springframework.web.server.ServerWebExchange exchange,
            org.springframework.web.server.WebFilterChain chain) {

        // Server-generated ID; never use arbitrary headers as identity.
        String requestId = UUID.randomUUID().toString();
        exchange.getResponse().getHeaders()
            .set("X-Request-ID", requestId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put("requestId", requestId));
    }
}
~~~

**Distinction to keep clear:** `requestId` is purely tracing/correlation metadata; it is **not Authentication**. Never write `contextWrite(ctx -> ctx.put("user", request.getHeader("X-User")))` to authorize requests. Authentication must come from **Spring Security verifying tokens** and populating the Reactive SecurityContext.

When writing custom WebFilters:

- Return `chain.filter(exchange)`; **never call `subscribe()`**.
- Place filters in the right order relative to security infrastructure.
- Never try to read authentication **before authentication filters run** and treat empty as “permanently anonymous”.
- Never call `block()` inside a WebFilter.
- For client-supplied request IDs, trust only after validation/normalization per infrastructure policy; request IDs grant zero permissions.

## 19. Cancellation and HTTP Status: Never Mix with Authentication Errors

When Spring Security detects:

- Missing Bearer token on a protected endpoint → typically **401 Unauthorized**.
- JWT bad signature/issuer/audience/expired → typically **401 invalid_token**.
- Valid JWT missing scope → typically **403 insufficient_scope**.
- Valid JWT with scope, wrong owner/tenant → typically **403/404** per policy.

These outcomes are **security decisions** expressed in the error/response pipeline.

**Cancellation is different:** the client canceled the subscription or closed the connection. The server may no longer even be able to send an HTTP status or body. Never map `SignalType.CANCEL` to **401**, **403**, or an invalid-token conclusion.

### 19.1. doFinally for Observability, Never for Granting Access

~~~java
return orderService.load(orderId)
    .doFinally(signal -> {
        switch (signal) {
            case CANCEL -> metrics.recordCancelledRequest();
            case ON_ERROR -> metrics.recordErrorTermination();
            case ON_COMPLETE -> metrics.recordCompletedRequest();
            default -> { }
        }
    });
~~~

This hook records pipeline metrics; it **must never** turn a cancellation into a 401 response or a mock principal. When the browser has disconnected, do not expect to send a JSON error body back to the client.

### 19.2. Never “Recover” All Security Errors with Default Data

Wrong:

~~~java
// DO NOT DO THIS.
return orderService.load(orderId)
    .onErrorResume(error ->
        Mono.just(OrderDto.publicFallback()));
~~~

If `orderService.load` throws `AccessDeniedException`, an `onErrorResume` catching **all errors** turns a denied request into HTTP 200 with fallback data or masks security failures. Only recover from **explicitly allowed errors**—such as a designed remote-lookup fallback policy—and never swallow authentication or authorization exceptions.

### 19.3. Retries Can Trigger Multiple Subscriptions

~~~java
Mono<OrderDto> result = orderService.createOrder(command)
    .retry(2);
~~~

With a cold Publisher, `retry(2)` **resubscribes** and re-executes the order-creation operation. If the first attempt committed to the DB before a response error occurred, retrying can create **duplicate records**.

Therefore, for write operations:

- Never retry arbitrarily simply because a `Mono` emitted an error.
- Use **idempotency keys**, unique constraints, or deduplication.
- Never retry **401/403** errors as transient network errors.
- Preserve transaction boundaries and domain invariants.
- When retrying downstream HTTP calls, know whether the operation is idempotent.

## 20. Reactive Transaction Context Differs from Reactive Security Context

Both Spring Security and Spring Reactive Transactions can use Reactor Context, yet each manages **distinct data types and lifecycles**.

| Context | Managed By | Purpose | Must Not Be Confused With |
| --- | --- | --- | --- |
| **SecurityContext** | Spring Security WebFlux. | Principal, authorities, request authentication. | Does not automatically prove owner/tenant. |
| **Transaction context** | ReactiveTransactionManager / TransactionalOperator. | Binds transaction/resource to subscription. | Not user identity. |
| **Tracing/correlation context** | Observability filters/instrumentation. | Request and log tracing. | Grants no permissions. |
| **Custom application context** | Explicitly set by app. | Short-lived metadata like request ID or locale. | Does not replace JWT validation. |

In a `Mono`-returning method called through a Spring-managed service, these contexts can coexist in the chain yet **are never interchangeable**. Writing `authenticated=true` into Reactor Context does not turn a request into a valid Spring Security Authentication.

### 20.1. Transaction Boundaries Must Enclose All Synchronized Work

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        itemRepository.saveItems(saved.getId(), items)
            .thenReturn(saved))
    .as(transactionalOperator::transactional);
~~~

Here, the transaction covers both database operations under a matching reactive transaction manager. If the application subsequently calls an external HTTP service, the database transaction **does not automatically span the HTTP call**.

On cancellation, the transaction manager can request rollback when the Publisher is canceled, though races with commit and driver limitations still exist. **Never build business logic assuming subscription cancellation rolls back an entire distributed system.**

## 21. Testing Subscription and Cancellation with StepVerifier

**Reactor Test** provides `StepVerifier` to test Publishers, completion/error/cancel signals, and Reactor Context contents. Add dependency:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

### 21.1. Testing Lazy Execution on Subscription

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionTest {

    @Test
    void deferRunsOnSubscription() {
        AtomicInteger invoked = new AtomicInteger();

        Mono<String> pipeline = Mono.defer(() -> {
            invoked.incrementAndGet();
            return Mono.just("ok");
        });

        // No subscription yet: defer body has not run.
        assertEquals(0, invoked.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, invoked.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        // Cold pipeline executes again on the second subscription.
        assertEquals(2, invoked.get());
    }
}
~~~

This test verifies **subscription semantics** only, not JWT signatures or SecurityContext.

### 21.2. Testing Cancellation with doFinally

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationTest {

    @Test
    void cancellationIsNotOnError() {
        AtomicReference<SignalType> terminal =
            new AtomicReference<>();

        Flux<Long> infinite = Flux.interval(
                java.time.Duration.ofMillis(10))
            .doFinally(terminal::set);

        StepVerifier.create(infinite)
            .expectNext(0L)
            .thenCancel()
            .verify();

        assertEquals(SignalType.CANCEL, terminal.get());
    }
}
~~~

This demonstrates testing cancellation on a periodic stream. For scheduler/timing-dependent tests, use `StepVerifier.withVirtualTime` to avoid wall-clock waits and flakiness. What this proves is that **cancellation triggers cleanup/metrics branches** without emitting an `onError` to the subscriber.

### 21.3. Testing Reactor Context with StepVerifier

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {

    @Test
    void subscriberContextIsVisible() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("requestId")));

        StepVerifier.create(
                source.contextWrite(ctx ->
                    ctx.put("requestId", "req-test-1")))
            .expectNext("req-test-1")
            .verifyComplete();
    }
}
~~~

Without `contextWrite`, `ctx.get("requestId")` has no value; depending on how it is read, the Publisher fails due to the missing key. Production code can use `getOrDefault` or enforce required keys per contract.

## 22. Testing SecurityContext in a Reactive Service

You do not need a real signed JWT just to verify **a service reads `ReactiveSecurityContextHolder` properly**. You can supply a mock Authentication in the test's Reactor Context.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void serviceReadsAuthenticationFromSubscriberContext() {
        Instant now = Instant.now();

        Jwt jwt = new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", "https://identity.example.test/realms/demo",
                "sub", "person-A",
                "aud", List.of("orders-api")));

        JwtAuthenticationToken auth =
            new JwtAuthenticationToken(jwt, List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")));

        CurrentSubjectService service =
            new CurrentSubjectService();

        StepVerifier.create(
                service.currentSubject()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(auth)))
            .expectNext("person-A")
            .verifyComplete();
    }
}
~~~

`ReactiveSecurityContextHolder.withAuthentication(auth)` is used **in tests** to place a mock Authentication into the subscriber context. **Never use it on production APIs to build Authentications from unverified HTTP headers.**

This is a **context-propagation** test—it **does not** prove JWT signatures, issuer, audience, or scopes were verified by `ReactiveJwtDecoder`. Concluding that the Resource Server validates tokens securely requires separate integration tests.

### 22.1. Two Subscribers Must Never Mix Principals

Write a test creating:

~~~text
Subscriber A -> JWT subject person-A
Subscriber B -> JWT subject person-B
~~~

Then subscribe both to the same Publisher-returning service method and assert each subscriber receives its own subject. If code uses static fields, singleton fields, or misuses `cache()`, this test exposes cross-request principal leakage.

### 22.2. Using WebTestClient for WebFlux HTTP Security

With `spring-security-test`, WebFlux can use test configurers to inject mock JWT Authentications:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This illustrates an authorization test **assuming a handler/test fixture for order 42 exists and permits the principal**. `mockJwt()` creates a mock authentication in tests and **does not verify real JWS signatures**.

Comprehensive HTTP testing covers:

| Scenario | Expected Outcome |
| --- | --- |
| No Bearer token to protected endpoint | **401**. |
| Bad-signature, expired, wrong-issuer/audience JWT | **401** from real decoder. |
| Valid JWT missing `SCOPE_orders.read` | **403** at HTTP authorization. |
| Valid JWT with scope, order belongs to another user | **403/404** per domain policy. |
| Valid JWT with right permissions, user's order | Succeeds per handler. |
| Client cancels streaming request | Clean subscription cleanup; no resource leaks. |
| `publishOn`/scheduler switch in service | `ReactiveSecurityContextHolder` still reads right principal. |
| Two concurrent requests with distinct principals | No Authentication/context mixing. |
| `retry` on order creation | No duplicates when idempotency policy is in place. |

For end-to-end JWT testing, generate a test key pair, sign JWTs, configure a real `ReactiveJwtDecoder` with validators, and send Bearer tokens via `WebTestClient`. That differs from `mockJwt()`.

## 23. Testing HTTP Request and Downstream Cancellation

`StepVerifier` tests Publishers, while **WebTestClient**, Reactor Netty test servers, or test clients let you observe the HTTP lifecycle.

Example strategy:

1. Build a `Flux` endpoint emitting multiple items with an `AtomicInteger` or metric recording **`doFinally(CANCEL)`**.
2. Have the client subscribe to the response stream.
3. Have the client consume the first item and cancel the subscription.
4. Verify the server receives cancellation when supported by the transport and test setup.
5. Verify upstream resources are released and no detached `subscribe()` tasks keep running.

Distinguish:

- **Publisher unit tests:** you control cancellation precisely via `StepVerifier`.
- **HTTP integration tests:** disconnect timing, buffering, and server transport affect when cancellation reaches the application.
- **Business behavior:** canceling a subscription does not prove a remote transaction rolled back.

For write requests, also test **successful commit followed by client disconnect before receiving the response**. Confirm clients can safely retry with an idempotency key or query status without causing duplicates.

## 24. Common Real-World Pitfalls

| Mistake | Consequence | Proper Approach |
| --- | --- | --- |
| Calling `subscribe()` inside a controller. | Detached work; errors/cancels/context decouple from the request. | Return a complete Publisher to WebFlux. |
| Calling `block()` on the event loop. | Stalls non-blocking processing, causing timeouts. | Use `flatMap` and reactive drivers; isolate blocking only when unavoidable. |
| Using ThreadLocal `SecurityContextHolder` like Spring MVC. | Missing or wrong Authentication across thread switches. | Use `ReactiveSecurityContextHolder`. |
| Reading current user in a singleton constructor. | Null or stale value retained across requests. | Read principal inside each subscription's Publisher. |
| Caching a `Mono` containing current user across all requests. | Leaks subjects/tenants across users. | Never share principal publishers; scope caches by request/resource permissions. |
| Using `Mono.just(blockingCall())`. | Executes eagerly at assembly time. | Use `fromCallable` + `boundedElastic` when needed, or true reactive APIs. |
| Using `doOnComplete` for all cleanup. | Skips cleanup on cancel/error. | `usingWhen`, reactive transaction lifecycle, `doFinally` for observation. |
| Treating cancellation as a normal exception. | Wrong metrics, cleanup, and error handling. | Distinguish `CANCEL`, `ON_ERROR`, and `ON_COMPLETE`. |
| Assuming cancel always rolls back remote POSTs. | Causes duplicate retries or state drift. | Idempotency, transactional constraints, auditing/reconciliation. |
| Calling `retry` on non-idempotent writes. | Can execute multiple times upon resubscription. | Policy-driven retries, deduplication, and idempotency keys. |
| Trusting `X-User-Id` instead of SecurityContext. | Clients can spoof identity. | Use verified tokens and domain identity mapping. |
| Putting `@PreAuthorize` on self-invoked methods without domain guards. | Can bypass proxy. | Invoke via Spring bean/proxy and guard real operations. |
| Assuming Reactor Context travels to HTTP service B. | Downstream lacks proper credentials. | Use OAuth client/service credentials or right-audience token exchange. |
| Forwarding `orders-api` JWT to `inventory-api`. | Wrong audience and unnecessary credential exposure. | Use tokens scoped for the downstream resource. |
| Reading MDC assuming it always follows subscriptions. | Wrong request logs or lost correlation IDs. | Use Reactor Context / integrated context propagation. |
| Turning every `onError` into a fallback success. | Can swallow `AccessDeniedException`. | Recover selectively; fail closed on security errors. |
| Testing only with `mockJwt()` and assuming JWT verification is safe. | Tests skip signature/issuer/audience checks. | Maintain separate signed `ReactiveJwtDecoder` tests. |

## 25. Roadmap for Implementing a WebFlux Resource Server

1. **Pick the right stack:** Use `spring-boot-starter-webflux`, `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveJwtDecoder`; never confuse with Servlet `HttpSecurity`.
2. **Verify tokens at the security boundary:** Validate JWT signature, issuer, audience, timestamps, and scope authorities. Never mint Authentication from unverified headers.
3. **Keep a single Publisher chain from controller to I/O:** Never call `subscribe()` or `block()` manually in the WebFlux request path.
4. **Understand execution timing:** Assembly creates a description; subscription typically triggers cold Publisher work; `Mono.just` does not defer value creation.
5. **Use ReactiveSecurityContextHolder:** Read principals/authorities inside the reactive chain; never cache context in singletons.
6. **Propagate context intentionally:** Use `contextWrite`/`deferContextual` for metadata, let Spring Security manage authentication context, and control boundaries with ThreadLocal/`CompletableFuture`.
7. **Separate broad scopes from data permissions:** HTTP scopes and method security are only one layer; domain services must still verify local accounts, tenants, owners, and state.
8. **Design for cancellation and cleanup:** Use `usingWhen`, reactive transactions, `doFinally`, and resource timeouts; remember cancel does not automatically roll back remote side effects.
9. **Design retries and idempotency:** For POSTs or critical transactions, use idempotency keys and status-query endpoints after client disconnects.
10. **Never relay tokens arbitrarily:** Reactor Context only stays in-process; downstream tokens need the right audience, scopes, and approved OAuth flows.
11. **Test subscription, cancellation, and context:** Use `StepVerifier` for lazy/defer/cancel/context; `WebTestClient` for security and HTTP; real signed decoders for JWT validation.
12. **Observe without leaking credentials:** Log request IDs, signal types, and error categories; never log Bearer Access Tokens, full SecurityContexts, or sensitive JWT claims.

**Key takeaway:** In WebFlux, **building a Publisher does not mean the work has run**; **subscription** is normally when a cold pipeline executes. **Cancel** is a lifecycle signal distinct from complete/error and does not guarantee rolling back committed side effects. **Spring Security's SecurityContext is propagated via per-subscription Reactor Context**, so use `ReactiveSecurityContextHolder`, keep operations inside a unified reactive chain, and never rely on `ThreadLocal` or manual `subscribe()` to preserve identity.

## References

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html).
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Spring Framework — Programmatic Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
