# Why ThreadLocal Must Not Be Used to Infer Identity Across a Reactive Chain

> **Key Focus:** In traditional Servlet applications, `SecurityContextHolder` typically relies on `ThreadLocal` so code running on a request thread can access the current `Authentication`. In **WebFlux/Reactor**, a request is represented as an **asynchronous Publisher/Subscriber chain**: signals can execute across multiple threads, a single thread can serve multiple subscriptions, and the chain itself may be assembled at a different time from when it is processed. Therefore, **the current thread is not the identity of a request/subscription**. Using `ThreadLocal` or `SecurityContextHolder.getContext()` as the source for inferring the user across an entire reactive pipeline can return null, observe an out-of-scope value, or cause code to bypass authorization. Spring Security reactive uses **Reactor Context** and `ReactiveSecurityContextHolder` to carry `SecurityContext` along with the **subscriber**, independent of which thread runs a continuation.

This lesson belongs to the **Security Context** group of the **Spring Security – fundamentals** module. The hands-on section uses Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x**, and Spring WebFlux/Project Reactor. The lesson compares with Servlet to explain the underlying nature, while the sample application **uses only WebFlux**, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`, and `WebTestClient`. Sample passwords are for localhost environments only.

## 1. What will you be able to do after this lesson?

1. Clearly distinguish **thread**, **request**, **publisher**, **subscriber**, **subscription**, **signal**, and **Reactor Context**.
2. Explain why `ThreadLocal.get()` does not represent the identity of an entire reactive chain.
3. Know that `Mono.just(...)` can compute data at chain assembly time, whereas `Mono.defer(...)` creates a value at subscription time but **still does not fix determining identity by thread**.
4. Understand `Mono.deferContextual(...)`, `ContextView`, and `contextWrite(...)`; know the scope of `contextWrite` affecting **upstream** operators.
5. Use `ReactiveSecurityContextHolder.getContext()` to obtain trustworthy authentication from a reactive pipeline.
6. Recognize that Spring Security WebFlux uses `WebFilter`/`SecurityWebFilterChain`, `ReactiveAuthenticationManager`, and `ServerSecurityContextRepository`, rather than the Servlet `ThreadLocal`/`HttpSecurity` mechanism.
7. Distinguish the impact of `publishOn`, `subscribeOn`, `delayElement`, and asynchronous boundaries on the **scheduler** versus their impact on the **Reactor Context**.
8. Avoid creating nested `subscribe()` calls, calling `block()` on the event-loop, storing principals in mutable/static fields, or using raw thread pools to infer the user manually.
9. Run a WebFlux application with real authentication via HTTP Basic + BCrypt, verify that identity stays correct after switching schedulers, distinguish Alice/Bob, and test role/method security.
10. Write `StepVerifier` unit tests for two independent subscribers and `WebTestClient` integration tests to prove context is not leaked across requests.

## 2. Getting the fundamentals right: ThreadLocal belongs to a thread, whereas Reactor Context belongs to a subscriber

### 2.1. Classic Servlet

A simple synchronous flow:

```text
Alice's HTTP request
       |
       v
Tomcat/Servlet worker thread T1
       |
       v
Spring Security Servlet filter chain
       |
       v
SecurityContextHolder (default MODE_THREADLOCAL)
       |
       v
Controller -> Service -> Repository on T1
       |
       v
Filter clears SecurityContext from ThreadLocal
       |
       v
T1 is reused for another request
```

In this model, `SecurityContextHolder.getContext()` helps code running on the **same request thread** know the current authentication. The Spring Security Servlet filter chain must clear the ThreadLocal at the end so that a thread that processed Alice does not retain her identity when serving Bob.

This is a convenience with a well-defined lifecycle. It **does not mean** a thread belongs to Alice forever or that an authentication automatically follows every `@Async`, `CompletableFuture`, or HTTP callback.

### 2.2. WebFlux/Reactor

A reactive request is not necessarily processed by a single fixed thread:

```text
Alice's HTTP request
       |
       v
WebFlux WebFilter chain sets up reactive security context
       |
       v
Subscriber/Subscription of Alice's pipeline
       |
       +-- At one moment: event-loop thread E1
       |      map/filter/flatMap...
       |
       +-- Upon delay or publishOn: worker thread W3
       |      continues operator...
       |
       +-- Async I/O callback: event-loop E2 or another thread
       |      completes Mono/Flux...
       |
       v
Response for Alice

Simultaneously:
Bob's HTTP request -> separate subscriber -> may use E1, W3, E2
```

The same thread can run signals belonging to multiple subscriptions **at different times**. One chain for Alice can switch threads between operators. Conversely, a thread serving Bob after Alice tells you nothing about who the current principal is by thread ID alone.

**The logical unit for attaching metadata to a reactive operation is the subscriber/subscription context**, not the worker thread.

### 2.3. Comparison table

| Criterion | Synchronous Servlet | WebFlux/Reactor |
| --- | --- | --- |
| Execution model | Typically thread-per-request in synchronous segments | Asynchronous signals, thread switching, shared event-loop |
| Standard security holder | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| How context is carried | `ThreadLocal` per default Servlet strategy | `Reactor Context` attached to subscriber |
| Security filter | `SecurityFilterChain`/Servlet `Filter` | `SecurityWebFilterChain`/`WebFilter` |
| Web configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Context repository | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| HTTP testing | `MockMvc` | `WebTestClient` |
| Async testing | Executor/thread tests | `StepVerifier` + subscription/scheduler tests |
| Typical mistakes | Forgetting to clear ThreadLocal on thread reuse | Reading ThreadLocal instead of Reactor Context, nested subscribe, or losing context at a bridge |

**Note:** In real systems, Servlet also supports async dispatch and Reactor can integrate restoration for certain ThreadLocals. The table describes **defaults and the source mechanism of identity**, not a claim that every Servlet request runs on exactly one thread or that every reactive operator always switches threads.

## 3. Fundamental mistake: reading ThreadLocal as if it were the logical request's identity

### 3.1. Why can reading it go wrong?

```java
// ANTI-PATTERN in a WebFlux reactive service.
Mono<String> currentUserWrong() {
    return Mono.fromSupplier(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "unknown" : auth.getName();
    });
}
```

This is a snippet; imports/classes are intentionally omitted. `Mono.fromSupplier(...)` defers execution until subscription — which is better than reading immediately when creating the publisher — but inside it still reads the **ThreadLocal**-based `SecurityContextHolder`. There is no Spring Security WebFlux contract guaranteeing that ThreadLocal always holds the current subscriber's authentication.

You may encounter:

- A null/empty value even though the HTTP request was properly authenticated in WebFlux.
- A value assigned by some component to the worker thread in a different scope.
- Results changing when adding `publishOn` or changing schedulers.
- Tests passing on a single thread but failing in production under concurrent load.
- Logs/audits identifying the wrong actor or custom authorization code granting wrong permissions.

**Do not predict absolutely that the result will always be null.** Some systems using Micrometer Context Propagation can restore `ThreadLocal` across certain operator segments. The existence of that bridge mechanism still **does not make ThreadLocal the primary source of identity in WebFlux**; the true source is the subscription's security context.

### 3.2. Reading too early at assembly time

```java
// Also an ANTI-PATTERN:
Authentication a =
    SecurityContextHolder.getContext().getAuthentication();

Mono<String> user =
    Mono.just(a == null ? "unknown" : a.getName());
```

Here the value is read **when creating the Mono**, not upon subscription. If `user` is created once inside a singleton bean, it may capture the identity from startup time or a previous request and reuse it for every subscriber. Even when creating a Mono inside a controller, assembly and subscription are still two distinct moments: relying on thread timing is a fragile assumption.

### 3.3. defer does not equate to the right identity

`Mono.defer(...)` delays invoking the supplier until a subscriber arrives. This is useful when lazy evaluation is needed. However, if the supplier still calls `ThreadLocal.get()`, the result still depends on the thread at supplier execution time and bridge configuration. To know the **subscriber's own** context, use `Mono.deferContextual(...)` or `ReactiveSecurityContextHolder.getContext()`.

### 3.4. The most severe failure is not just NullPointerException

If `auth` is null, code may throw or reject the request — that is a functional bug. If code falls back to a high-privilege system principal, skips checks because it "sees no user", or uses a stale ThreadLocal value from another thread, the consequences can include **IDOR/BOLA, data exposure, inaccurate audit records, and cross-tenant access**.

Do not fix this with `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL` in WebFlux. `MODE_GLOBAL` makes multiple users share a single context; inherited thread locals do not carry the right identity per subscription scheduled onto a thread pool.

## 4. Reactor Context: the right way to pass metadata per subscription

### 4.1. Context is not a global Map

A Reactor `Context` is a key/value structure provided within a **Reactive Streams subscriber chain**. When a context is updated via `put`, Reactor creates a new context with immutable semantics rather than mutating a static Map shared across all requests.

```text
Mono<String> source
    |
    v
map/filter/flatMap...
    |
    v
Subscriber S_A with Context_A (actor=alice)
    
The same source publisher can have:
Subscriber S_B with Context_B (actor=bob)

Context_A and Context_B do not need the same thread;
the two subscribers do not automatically see each other's keys/values.
```

You should not think of Context as "another way to write ThreadLocal". It travels with the **subscription**, allowing a downstream subscriber to supply data for upstream operators to read during execution. It is also not a database/session: when a subscription ends, data is not persisted to an independent HTTP request.

### 4.2. Pure Reactor example: contextWrite and deferContextual

A publisher:

```java
Mono<String> source =
    Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("actorId", "missing"))
    );

Mono<String> alice =
    source.contextWrite(ctx -> ctx.put("actorId", "alice"));

Mono<String> bob =
    source.contextWrite(ctx -> ctx.put("actorId", "bob"));
```

**Meaning:** Two different subscriptions can run the same `source` yet receive different `actorId` values depending on context. If the key is absent, the code returns `missing`. These `alice`/`bob` strings are demo data, **not proof of a logged-in user**. In real products, do not let clients supply `actorId` themselves and treat it as authority; the security context must be established by a trusted authentication mechanism.

### 4.3. Why does contextWrite placed "below" take effect "above"?

Reactor rule: `contextWrite` receives the context from the **downstream subscriber** and adds keys for **upstream** operators to see. For example:

```java
Mono<String> visible =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "missing"))
    )
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
```

Upon subscription, `deferContextual` returns `request-42`.

However:

```java
Mono<String> notAutomaticallyVisibleDownstream =
    Mono.just("start")
        .contextWrite(ctx -> ctx.put("traceId", "request-42"))
        .flatMap(ignored ->
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))
            )
        );
```

`flatMap` placed **downstream** of `contextWrite` does not necessarily see a key added by an upstream operator. With the layout above, the lower `deferContextual` is designed to return `missing` because keys do not propagate forward in the data flow direction. This differs from the imperative mindset of "call set() and all subsequent code can read it".

### 4.4. Each subscribe is a new subscription

A `Mono` or `Flux` can be **subscribed** multiple times. With a cold publisher, each subscription re-executes the source per its semantics and has its own context. A shared hot `Flux` source can still have multiple subscribers with distinct metadata; propagation must be verified against specific operator/share boundaries.

**Do not store a mutable `SecurityContext` and mutate it across two subscribers**. Reactor Context isolates key/value scope, while object references attached to Context **can still be mutable**. Spring Security manages context per request; application code should not mutate recognized `Authentication`/authorities inside a singleton.

## 5. SecurityContext in Spring WebFlux

### 5.1. Components

```text
HTTP request
    |
    v
Spring WebFlux WebFilter chain
    |
    v
Spring Security SecurityWebFilterChain
    |
    +-- AuthenticationWebFilter (depends on mechanism)
    |       |
    |       v
    |   ReactiveAuthenticationManager
    |       |
    |       v
    |   Verified Authentication
    |
    +-- ReactorContextWebFilter / reactive context integration
    |       |
    |       v
    |   Mono<SecurityContext> in Reactor Context
    |
    +-- Reactive authorization (URL/method)
    |
    v
Controller -> Service returning Mono/Flux
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Mono<SecurityContext> -> Authentication -> principal/authorities
```

This is a component diagram, not a fixed ordering of every WebFilter for every mechanism. `ReactorContextWebFilter` integrates `ServerSecurityContextRepository` to set up the reactive security context; authentication filters also interact with context by design. `SecurityWebFilterChain` is not simply a Servlet `SecurityFilterChain` with a different name.

### 5.2. Proper API for reading identity

In WebFlux, use:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
```

This is a snippet. `getContext()` returns `Mono<SecurityContext>`; it does not require current code to know the thread name. When no context exists, it can be an empty Mono. `defaultIfEmpty(...)` here is only for **illustrative messaging**; never turn anonymous into a privileged actor. In protected APIs, if a trusted user is missing, return the appropriate authentication/authorization error rather than granting access.

### 5.3. Two valid patterns for reading current principal

1. In a reactive service, retrieve it via `ReactiveSecurityContextHolder.getContext()` and compose with `map`/`flatMap`.
2. In a WebFlux controller, Spring can resolve `Principal` or `Mono<Principal>` from the request via method arguments per the API; if you need a business service independent of the HTTP framework, pass the verified actor ID or read the reactive context where needed.

If object-level authorization is needed, do not rely solely on `auth.getName()` to grant access. A route like `GET /orders/{id}` must verify owner/tenant/permission in the service/repository. `Authentication` tells you "who", not automatically "whether they may act on this record".

### 5.4. API for writing context in unit tests or trusted flows

Spring Security allows setting context on **a single subscription** in tests:

```java
Authentication testAlice =
    new TestingAuthenticationToken("alice", "unused", "ROLE_USER");

Mono<String> forAlice =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(testAlice)
        );
```

This snippet uses a **mocked** authentication in tests and does not perform real password authentication. `withAuthentication(authentication)` creates a Reactor `Context` to pass the supplied authentication; this method does not verify credentials itself. In a real application, the authentication context must come from **WebFlux security filters/providers/verified tokens**; do not take a role from the request body and call `withAuthentication(...)` directly.

The `ReactiveSecurityContextHolder.withSecurityContext(Mono<SecurityContext>)` API can be used when a trusted context is already available, and `ReactiveSecurityContextHolder.clearContext()` supports clearing context using Reactor mechanics; do not apply `ThreadLocal.remove()` to these APIs.

### 5.5. Session and Reactor Context are two separate concerns

`Reactor Context` holds metadata accessible to operators in the **current subscription**; `ServerSecurityContextRepository` (for example `WebSessionServerSecurityContextRepository` or `NoOpServerSecurityContextRepository`) decides whether to store/restore authentication **across different HTTP requests**.

With stateless HTTP Basic in the hands-on demo, each request sends credentials itself. If using WebSession/OIDC login, the security filter can restore the authenticated identity from the session into a new reactive context on the next request.

Do not conflate:
- Reactor Context with HTTP Session.
- `contextWrite(...)` with persisting to a database.
- Reactive `clearContext()` with logout/revoking a refresh token.
- Servlet `SecurityContextHolder.clearContext()` with clearing the security context of a WebFlux subscription.

## 6. publishOn, subscribeOn, delay, and context

### 6.1. A Scheduler controls execution, not where identity lives

`publishOn(scheduler)` shifts the execution of **downstream signals** from that operator onward to the specified worker scheduler. `subscribeOn(scheduler)` affects **subscribing upstream** and part of the execution pipeline. Both can change the thread used, yet **they do not cause Reactor Context to change ownership to another user** when the pipeline uses native operators and context is propagated properly.

```text
Alice's request, subscription S_A, Context_A
       |
       v
map(...) on event-loop E1
       |
       v
publishOn(boundedElastic)
       |
       v
flatMap(...) on worker W2
       |
       v
ReactiveSecurityContextHolder.getContext()
       |
       v
Authentication(Alice) of subscription S_A
```

There is no need to force all of Alice's operators to stay on E1. Doing so goes against the reactive model and reduces scalability.

### 6.2. Proper example after scheduler switching

```java
Mono<String> afterSchedulerHop() {
    return Mono.delay(Duration.ofMillis(10))
        .publishOn(Schedulers.boundedElastic())
        .then(ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
        .map(name -> "after-hop:" + name);
}
```

This snippet assumes the corresponding Reactor/Spring Security imports. `Mono.delay` emits an asynchronous signal; `publishOn` switches downstream execution to another scheduler; the identity source is read from **Reactor Context** when the `Mono` is subscribed. A test can prove the chain still receives Alice even though the thread changed. **Do not assert the exact thread name** in tests because runtimes/schedulers/pools can vary.

### 6.3. Why not use Thread.currentThread().getName() for authentication?

`Thread.currentThread().getName()` is only useful for observing concurrency and debugging. Names like `reactor-http-nio-3`, `parallel-2`, or `boundedElastic-1` do not tell you who the actor is. The same thread name can run signals for multiple users; one user can appear on multiple threads. Never map thread name → user/tenant/role.

### 6.4. Do not use a thread-local request variable to pass tenant

If a WebFlux service creates `private static final ThreadLocal<String> TENANT`, calls `TENANT.set(...)` in a filter, and calls `TENANT.get()` inside a deep `map(...)`, it risks seeing the wrong tenant or null after a scheduler switch.

To stay safe:
- Verify the tenant belongs to the authenticated principal.
- Pass the tenant ID explicitly via method arguments to domain/repository layers, or place metadata with clear provenance into Reactor Context.
- Do not treat a `tenantId` key in Reactor Context as authority if an untrusted filter can write to it.
- Database queries must use owner/tenant predicates and domain authorization, not rely solely on the HTTP path.

## 7. When can context be "lost" from a chain?

### 7.1. Creating nested subscribe() calls

```java
// ANTI-PATTERN: fire-and-forget inside a reactive operator.
Mono<String> broken() {
    return reactiveIdentity.currentName()
        .map(actor -> {
            sendNotification(actor).subscribe();
            return "accepted";
        });
}
```

This snippet intentionally omits classes/fields to highlight the bug. `subscribe()` creates a **new subscription**, detached from the caller's HTTP subscription; context, errors, cancellation, tracing, and lifecycle are no longer composed naturally. Capturing `actor` in a closure may let the notification know a name string, but it does not mean it has the correct security context/permissions. Errors in the notification may be handled unexpectedly; the request may return success before the notification finishes.

**Better:** compose within the same chain:

```java
Mono<String> composed() {
    return reactiveIdentity.currentName()
        .flatMap(actor ->
            sendNotification(actor).thenReturn("accepted")
        );
}
```

If a notification truly must run outside the request, use a queue/outbox with a trusted message, actor/tenant/action metadata, transactions, retries, and reauthorization per policy; do not spawn an anonymous nested subscription in a controller.

### 7.2. Calling block() on the event-loop

```java
// ANTI-PATTERN in a WebFlux controller:
String actor = reactiveIdentity.currentName().block();
return Mono.just("hello:" + actor);
```

`block()` is a subscription/blocking boundary; on a non-blocking Reactor event-loop it can be rejected or cause thread starvation, timeouts, and break the reactive model. It also creates a spot where context is hard to reason about because you have exited the chain managed by WebFlux.

**Right:** keep returning `Mono`:

```java
Mono<String> hello() {
    return reactiveIdentity.currentName()
        .map(actor -> "hello:" + actor);
}
```

### 7.3. Raw ExecutorService, CompletableFuture, SDK callbacks

Reactor Context is scoped to the Reactor subscriber; a `Runnable` running on an `ExecutorService` or an SDK callback spawning its own thread **does not automatically become a reactive operator with the same context**.

If you need to invoke legacy blocking code:

```java
Mono<Order> loadOwnedOrder(String orderId) {
    return reactiveIdentity.currentName()
        .flatMap(actorId ->
            Mono.fromCallable(() ->
                    legacyOrderDao.findOwnedOrder(actorId, orderId))
                .subscribeOn(Schedulers.boundedElastic())
        );
}
```

This snippet is illustrative; `Order`/`legacyOrderDao` and policies must be implemented by the project. What matters is **reading the verified actor at the reactive boundary**, then passing the **explicit actor ID value** to the blocking DAO. Inside the DAO you must still check owner/tenant and perform real authorization; passing a string alone does not prove permission. Run the blocking call on `boundedElastic` so it does not block the Netty event-loop.

### 7.4. Nested requests or messaging

An HTTP client such as `WebClient` has its own publisher; the chain's context is propagated through appropriate Reactor operators, but **security identity is not automatically shared to another service as a valid credential**. If downstream needs authentication, there must be a verified OAuth2 token relay/propagation policy, rather than grabbing the username, setting an `X-User` header, and treating that header as trusted authentication.

With Kafka/RabbitMQ/SQS messages, the consumer is a new scope: actor metadata must be appropriately signed/controlled and tokens/authorization rechecked rather than inferring the user from a listener ThreadLocal.

### 7.5. cache, share, hot publishers, and context

`Mono.cache()` can cache a value and share it across other subscribers. If the cached value is **user-specific data** or a principal, putting the cache in a singleton without an actor/tenant key can cause Alice to receive Bob's result (or vice versa), even when Reactor Context on every subscription is correct. Do not cache a publisher/result under a single shared key when the response depends on identity; cache keys and scopes must include security-relevant dimensions and expiry.

Similarly, `share()`/`publish().refCount(...)` and hot publishers have their own upstream subscription mechanics; do not assume each downstream subscriber's context recreates identity for a shared upstream source. Test these boundaries against actual operator behavior.

## 8. Micrometer Context Propagation: an exception to understand accurately

### 8.1. Why does ThreadLocal sometimes still "seem to work" in reactive code?

Reactor supports the `io.micrometer:context-propagation` SPI. When an application configures a `ThreadLocalAccessor` and an appropriate restoration mode, certain values from Reactor Context can be **temporarily populated into ThreadLocal** around callbacks:

- Default/limited mode: certain operators such as `handle`/`tap` support restoration when the library is present.
- Automatic mode: can be enabled via `Hooks.enableAutomaticContextPropagation()` prior to the subscriptions it should apply to.
- `contextCapture()` can capture registered ThreadLocals at subscription time into Reactor Context.
- These mechanisms have specific scopes, overhead, activation timing, and cleanup rules; not every ThreadLocal is automatically propagated.

Therefore, stating "ThreadLocal is always null in WebFlux" is **inaccurate**. However, stating "any reactive operator can use ThreadLocal as its security source" is also **wrong**.

### 8.2. The source of truth remains the subscription's context

When the bridge is enabled, Reactor Context is the **context source** that registered ThreadLocal accessors use to restore state within supported scopes. This is helpful when integrating logging/MDC libraries or imperative code needing compatibility, but you should not write new authorization logic based on `SecurityContextHolder.getContext()` in WebFlux.

For Spring Security WebFlux:
- Use `ReactiveSecurityContextHolder.getContext()` to read authentication in the pipeline.
- Use `@EnableReactiveMethodSecurity`/`@PreAuthorize`/`SecurityWebFilterChain` to protect access points.
- For blocking bridges, pass trusted actor ID/permissions into the service or design controlled, tested propagation.
- If enabling automatic ThreadLocal propagation, also test the **missing-context** case to ensure accessors clear state properly and avoid cross-subscriber leaks.
- Benchmark overhead and contention; propagation is not free.

### 8.3. Do not enable a global hook just to "fix auth.getName()"

`Hooks.enableAutomaticContextPropagation()` affects Reactor behavior process-wide for new subscriptions. It does not validate credentials or turn an arbitrary `ThreadLocal` into valid authentication. In a multi-user web system, changing a global hook requires evaluating timing, performance, library integration, and cleanup; do not enable it blindly just so legacy code can read the current user.

## 9. Runnable example: Spring Boot WebFlux + Reactor Context + HTTP Basic

The demo illustrates three things:

1. `ReactiveSecurityContextHolder` reads the correct identity on an HTTP request that passed through WebFlux security.
2. Identity can still be read accurately **after an async delay and publishOn**, without relying on thread names.
3. Alice/Bob in **two different subscriptions** do not share identity; reactive method security evaluates roles in context.

This is a **Spring WebFlux** application; do not mix `spring-boot-starter-web` (MVC) into the project. In-memory users exist only for learning. A real application may authenticate via OIDC/JWT/IdP; retrieving `Authentication` from the reactive context follows the same principle, though principal types and token validation differ.

### 9.1. Versions and layout

- Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x** from the Boot BOM, Project Reactor per BOM.
- Maven 3.9+ or compatible Maven wrapper.
- Runs on localhost; sample HTTP Basic credentials must not be used on real networks; production requires HTTPS.
- Boot 3.5.16 was released on **2026-06-25** and is the final OSS release in the 3.5 line; for new deployments, choose a supported Boot line (4.x) and migrate APIs/tests accordingly.

```text
reactive-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveContextApplication.java
    └── test/java/demo/reactive/
        ├── ReactiveContextHttpTests.java
        └── ReactiveContextUnitTests.java
```

### 9.2. Complete pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-security-context-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Complete Java application

Create `src/main/java/demo/reactive/ReactiveContextApplication.java`:

```java
package demo.reactive;

import java.time.Duration;
import java.util.Objects;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder passwordEncoder) {

        UserDetails alice = User.withUsername("alice")
            .password(passwordEncoder.encode("lab-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("lab-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            // Stateless API demo: do not restore authentication from WebSession.
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET,
                    "/me", "/after-hop", "/role-user")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // Keep default CSRF configuration. Demo only uses GET.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@Service
class ReactiveIdentityService {

    Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Objects::nonNull)
            .map(Authentication::getName)
            // Illustrative value when NO context is present in unit tests.
            // Never turns anonymous into authenticated.
            .defaultIfEmpty("anonymous");
    }

    Mono<String> afterSchedulerHop() {
        return Mono.delay(Duration.ofMillis(10))
            .publishOn(Schedulers.boundedElastic())
            // Subscribe to publisher reading security context AFTER the boundary.
            .then(Mono.defer(this::currentUsername))
            .map(name -> "after-hop:" + name);
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> onlyUserRole() {
        // Reactive method security reads Authentication from Reactor Context.
        return currentUsername().map(name -> "user-only:" + name);
    }
}

@RestController
class ReactiveIdentityController {

    private final ReactiveIdentityService identity;

    ReactiveIdentityController(ReactiveIdentityService identity) {
        this.identity = identity;
    }

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> currentUser() {
        return identity.currentUsername()
            .map(name -> "me:" + name);
    }

    @GetMapping("/after-hop")
    Mono<String> afterHop() {
        return identity.afterSchedulerHop();
    }

    @GetMapping("/role-user")
    Mono<String> onlyUserRole() {
        // Go through service bean proxy so @PreAuthorize is applied.
        return identity.onlyUserRole();
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

**Reading the code accurately:**

1. `spring-boot-starter-webflux` and `SecurityWebFilterChain` establish the app as a **reactive web stack**. Do not use `HttpSecurity`, `OncePerRequestFilter`, or Servlet `SecurityContextHolder` to determine the actor in controllers.
2. `MapReactiveUserDetailsService` is only a learning user store without a database; `BCryptPasswordEncoder` verifies passwords. HTTP Basic on localhost uses valid credentials checked by the provider; the demo has no endpoint to create admins.
3. `NoOpServerSecurityContextRepository.getInstance()` clarifies the stateless intent: do not use WebSession to save authentication across requests. It is **unrelated** to `NoOpPasswordEncoder`; one is a repository that does not persist context, while the other is a dangerous plaintext encoder.
4. `ReactiveIdentityService.currentUsername()` returns a **Mono**, using `ReactiveSecurityContextHolder.getContext()` to fetch the subscriber's authentication. It reads neither a static field nor `ThreadLocal`.
5. `afterSchedulerHop()` introduces a delay and uses `publishOn(Schedulers.boundedElastic())` to switch execution before reading context. Because context propagates along the subscription, identity remains accurate.
6. `@EnableReactiveMethodSecurity` and `@PreAuthorize("hasRole('USER')")` work on methods returning `Mono<String>`. Tests distinguish Alice (ROLE_USER) and admin (only ROLE_ADMIN). A role does not imply all permissions.
7. `.formLogin(form -> form.disable())` keeps this app focused on HTTP Basic without form login redirects. `csrf` remains enabled by default; because all demo endpoints use **GET**, tests do not need a CSRF token. Write endpoints in real products must evaluate their own CSRF threat model.
8. `.anyExchange().denyAll()` blocks undeclared routes. If there are multiple SecurityWebFilterChains, proper matchers/order are required so requests do not fall into a public chain.
9. `Mono<String>` is returned directly; WebFlux subscribes and manages lifecycle. Do not call `subscribe()`/`block()` inside controllers.
10. The `lab-pass` password is hard-coded for learning and is **non-secret** data. Do not use this code as production configuration: use a managed IdP/user store, rate limits, TLS, auditing, and proper token/session management.

### 9.4. Integration tests: WebTestClient verifying identity over HTTP

Create `src/test/java/demo/reactive/ReactiveContextHttpTests.java`:

```java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextHttpTests {

    @Autowired
    WebTestClient client;

    @Test
    void basicAuthenticationUsesRealReactiveUserStore() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:alice");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void identitySurvivesReactorSchedulerSwitch() {
        client.get().uri("/after-hop")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("after-hop:alice");

        client.get().uri("/after-hop")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("after-hop:admin");
    }

    @Test
    void twoUsersAndAnonymousDoNotShareIdentity() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:alice");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("me:admin");

        // Stateless request without Basic header does not receive previous user.
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void webAndReactiveMethodAuthorizationAreSeparate() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");

        client.get().uri("/role-user")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user-only:alice");

        client.get().uri("/role-user")
            .headers(h -> h.setBasicAuth("admin", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unlistedEndpointIsNotOpenedByAnAuthenticatedUser() {
        client.get().uri("/unlisted")
            .headers(h -> h.setBasicAuth("alice", "lab-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**What the tests mean:**

- `WebTestClient` replaces Servlet `MockMvc`, testing the real WebFlux SecurityWebFilterChain on a random HTTP port.
- `setBasicAuth` sends credentials like a real client. The 200/401 tests show the authentication manager/user store/BCrypt working; unlike `mockUser()`/`@WithMockUser` which only simulate a principal.
- `/after-hop` verifies **Reactor Context remains accessible after a scheduler hop**. Tests do not depend on any thread name.
- Alice and admin have distinct authentications; a new request without a Basic header gets 401 in the stateless demo. No global "current user" variable is ever retained.
- Tests verify role permissions at two layers: URL `/admin` requires ROLE_ADMIN, service `onlyUserRole` requires ROLE_USER via `@PreAuthorize`.
- These are lab integration tests with sample usernames/passwords. Production also needs negative tests (token validation, tenant/object authorization, login rate limits, log redaction, TLS, cancellation).

### 9.5. Unit tests with StepVerifier: two subscribers sharing the same source with different identities

Create `src/test/java/demo/reactive/ReactiveContextUnitTests.java`:

```java
package demo.reactive;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextUnitTests {

    private final ReactiveIdentityService identity =
        new ReactiveIdentityService();

    private static Authentication user(String name) {
        // Unit test use only. Not real password authentication.
        return new TestingAuthenticationToken(
            name, "unused-test-credential", "ROLE_USER");
    }

    @Test
    void contextIsChosenPerSubscriptionNotPerSourceMono() {
        Mono<String> source = identity.currentUsername();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice"))))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("bob"))))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void schedulerSwitchDoesNotChangeReactivePrincipal() {
        StepVerifier.create(identity.afterSchedulerHop()
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(
                        user("alice"))))
            .expectNext("after-hop:alice")
            .verifyComplete();
    }

    @Test
    void concurrentSubscriptionsHaveIndependentSecurityContexts() {
        Mono<String> alice = identity.afterSchedulerHop()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice")));

        Mono<String> bob = identity.afterSchedulerHop()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("bob")));

        StepVerifier.create(Mono.zip(alice, bob))
            .expectNextMatches(pair ->
                pair.getT1().equals("after-hop:alice")
                && pair.getT2().equals("after-hop:bob"))
            .verifyComplete();
    }

    @Test
    void deferContextualReadsContextAtSubscription() {
        Mono<String> source =
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("lesson.actor", "missing"))
            );

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.actor", "alice")))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.actor", "bob")))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void contextWriteOnlyAffectsItsUpstreamPart() {
        Mono<String> source =
            Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("lesson.trace", "missing"))
            );

        StepVerifier.create(source
                .contextWrite(ctx -> ctx.put("lesson.trace", "T1")))
            .expectNext("T1")
            .verifyComplete();

        Mono<String> downstream =
            Mono.just("start")
                .contextWrite(ctx -> ctx.put("lesson.trace", "T1"))
                .flatMap(x -> source);

        StepVerifier.create(downstream)
            .expectNext("missing")
            .verifyComplete();
    }
}
```

Note: The `Duration` and `Schedulers` imports listed may be flagged as unused by IDEs in the test file since scheduler switching lives in `ReactiveIdentityService.afterSchedulerHop()`; remove unused imports if the project enforces strict linting. The JUnit methods remain model-valid.

**What the unit tests prove:**

1. **The same Mono source** can be subscribed three times with Alice/Bob/empty contexts; it does not store "current user" in a singleton field.
2. `ReactiveSecurityContextHolder.withAuthentication(...)` puts a **test authentication** onto the subscription; this tests identity propagation, not real password proof.
3. `StepVerifier` asserts Mono completion cleanly; there is no need to call `block()` inside controller code.
4. Two subscriptions using `Mono.zip` run concurrently per the source's scheduler design; they can share a worker pool while keeping identity accurate **per subscription**, not per thread.
5. `contextWrite` adds keys for **upstream**; the downstream test sees `missing` to prevent misunderstanding the ordering.
6. There is no need to rely on `Thread.currentThread().getName()` or arbitrary sleeps to conclude identity.

### 9.6. Running Maven and testing with curl

From the project directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Expected behavior when dependencies/JDK match:

- `mvn test` runs WebTestClient HTTP tests and StepVerifier unit tests.
- `GET /public` without Basic authentication → HTTP 200, body `public`.
- `GET /me` without credentials → 401.
- `GET /me` as Alice → 200, `me:alice`.
- `GET /after-hop` as Alice → 200, `after-hop:alice`.
- `GET /after-hop` as admin → 200, `after-hop:admin`.
- `GET /admin` as Alice → 403; as admin → 200.
- `GET /role-user` as Alice → 200; as admin (only ROLE_ADMIN) → 403.
- `GET /me` immediately after an authenticated request, without a Basic header → 401.

These are **expected code outcomes**, not a claim that Maven was executed in the authoring environment.

In a second terminal, on localhost only:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/after-hop
curl -i -u admin http://localhost:8080/after-hop
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

`curl -u alice`/`-u admin` will prompt for a password; enter `lab-pass` on your learning machine. Never put passwords on the command line, share them in logs, or send HTTP Basic outside localhost without HTTPS. On older PowerShell versions you may need `curl.exe`.

## 10. Why do WebTestClient and StepVerifier complement each other?

| Question to prove | WebTestClient | StepVerifier |
| --- | --- | --- |
| Valid/invalid HTTP Basic password verified by provider | **Yes** | No if using test token |
| URL role policy returns proper 200/401/403 | **Yes** | Can test method security separately |
| WebFlux security filter sets up context properly | **Yes** | Only tests source/context supplied by test |
| Context per subscription | Indirectly via requests | **Directly** via contextWrite |
| Switching scheduler does not change identity | **Yes** with async endpoint | **Yes** with Mono in unit test |
| Two subscribers have independent contexts | Test multiple requests | **Yes** with Mono.zip/contextWrite |
| Missing context must not grant permissions | **Yes** via 401/403 | Tests empty/default behavior |
| CSRF/session/OIDC/JWT production policies | Needs separate tests | Insufficient |
| No leakage of another user's tenant/object | Needs app/domain tests | Can test reactive service/repository |

`@WithMockUser`/`mockUser()` in Spring Security reactive testing are also useful for testing role policies, but they **do not prove** real password authentication. In this lesson, HTTP tests intentionally send Basic credentials to test the full authentication path.

## 11. Common design mistakes

### 11.1. Storing Authentication in a singleton service field

```java
// DANGEROUS ANTI-PATTERN.
@Service
class WrongIdentityService {
    private Authentication lastAuthentication;
}
```

`@Service` beans are singletons by default; fields can be read/written concurrently across many requests/subscriptions. Never store "current user" as mutable global state. Use reactive context or pass verified actor IDs into methods.

### 11.2. Relying on ThreadLocal inside every map()

```java
// ANTI-PATTERN:
flux.map(item -> {
    String actor = THREAD_LOCAL_CURRENT_USER.get();
    return loadFor(actor, item);
});
```

If `THREAD_LOCAL_CURRENT_USER` is a custom context not propagated properly, `actor` can be null or wrong. Even when the Micrometer bridge is present, clear contracts/registration/cleanup are required. For Spring Security WebFlux identity, read `ReactiveSecurityContextHolder.getContext()` first and then use `flatMapMany`/`flatMap` with the trusted actor.

### 11.3. Using a client-supplied Context key as a role

```java
// ANTI-PATTERN: roles from request body are not trusted authentication.
return service.run()
    .contextWrite(ctx -> ctx.put("role", request.getRole()));
```

Reactor Context does not verify signatures on a role string. Only put metadata authenticated by a filter/identity mechanism; authorization must still use a trusted `Authentication` and domain policies.

### 11.4. Context disappearing after nested subscribe()

Fix with `flatMap`/`then`/`concatMap` composition instead of nested `subscribe()`. If fire-and-forget is genuinely necessary, establish a clear job boundary, message envelope, and separate authorization/retry handling.

### 11.5. Context appearing to work in tests but failing in production

A unit test may execute every operator on the same thread, accidentally relying on `ThreadLocal`. Add tests with `delayElement`/`publishOn`, two different subscribers, and interleaved HTTP requests. Do not assert thread names; assert **identity and authority**.

### 11.6. Switching to MODE_INHERITABLETHREADLOCAL

A worker thread created while Alice is authenticated may inherit Alice's context and later be reused for Bob; this is not per-subscription propagation. Never set a JVM-wide strategy just to avoid using `ReactiveSecurityContextHolder`.

### 11.7. Running blocking JDBC on the event-loop

`JdbcTemplate` is blocking; using it directly inside `map` on the Netty event-loop easily causes starvation. Use R2DBC or wrap blocking operations in `Schedulers.boundedElastic()` with resource limits; pass actor/tenant IDs explicitly and enforce domain authorization at query time.

### 11.8. Assuming Context persists sessions

`ReactiveSecurityContextHolder` returns identity for the current chain. Keeping logins across HTTP requests requires an appropriate repository/session/token mechanism, not just `contextWrite`. In the stateless Basic demo, each request requires an Authorization header.

### 11.9. Assuming authenticated always means authorized

A successful login only tells you who; role/method policies and object authorization must still be enforced. With anonymous authentication, an `Authentication` object can exist; do not write `auth.isAuthenticated()` as the sole condition for granting sensitive actions.

### 11.10. Logging the entire SecurityContext for debugging

`Authentication`/principals can contain sensitive claims/metadata; never log raw credentials, Basic headers, bearer tokens, cookies, or tenant secrets. Audits should record stable actor ID, action, outcome, and correlation ID; never use thread name as actor.

### 11.11. Caching a publisher under a global key

If a publisher produces a response based on the current principal and calls `cache()` inside a singleton, the first user's result can be returned to subsequent users. Never cache cross-user responses under a key lacking actor/tenant/permission/expiry. A correct reactive context cannot cure a flawed cache scope.

### 11.12. Assuming Reactor Context grants authority to remote services

A downstream HTTP request must itself be authenticated (e.g., via policy-governed OAuth2 token relay) and authorized per resource. An upstream Reactor Context does not cross network boundaries as an identity trusted by a remote service.

## 12. Reactive method security and identity in services

Spring Security reactive supports `@EnableReactiveMethodSecurity` and `@PreAuthorize` on methods returning a reactive publisher:

```java
@Service
class PurchaseService {
    @PreAuthorize("hasAuthority('PURCHASE_READ')")
    public Mono<Purchase> getPurchase(String purchaseId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                repository.findOwnedPurchase(
                    purchaseId,
                    stableActorId(authentication)
                )
            );
    }
}
```

This is a **design snippet**, not a standalone program: `Purchase`, `repository`, and `stableActorId` are application-specific components. Meaning:

- Method security obtains trusted authentication from the reactive context rather than a static ThreadLocal.
- Authority `PURCHASE_READ` is checked.
- Repository/Service verifies purchase ownership by actor ID/tenant to prevent BOLA.
- Returning `Mono` lets Spring Security attach policy to the reactive pipeline.
- Do not call `block()` to return `Purchase` synchronously from the event-loop.
- Stable actor ID should be derived from **verified** principal/claims, not from a query param allowing callers to impersonate someone else.

If an annotated method is called via **self-invocation** inside the same object rather than through the Spring proxy, interception may not run. Therefore separate security-sensitive services and write integration tests for proxies/methods rather than trusting annotations simply by reading source code.

## 13. When does ThreadLocal still have a place in reactive systems?

ThreadLocal is not strictly "banned". It remains sensibly used by many imperative libraries such as logging MDC, metrics, JDBC transaction management, or legacy SDKs. Still, you must clearly establish:

1. Which context belongs to the subscriber, and which belongs to the thread?
2. If bridging is required, are `ThreadLocalAccessor` and Reactor Context Propagation modes configured/tested?
3. Is there proper **cleanup/reset** when a scheduler worker is reused?
4. Does any logic treat ThreadLocal as proof of authority even though it was only set by a logging framework?
5. Do any scopes switch to raw threads/CompletableFutures/SDK callbacks outside Reactor?
6. If propagation is lost, does the application **fail closed** instead of falling back to a privileged default identity?
7. Have overhead, errors, cancellations, and concurrent subscriptions been benchmarked?

**Selection rule:** Observability-only metadata may be bridged to MDC under control; decisions on who may act on data must still rest on trusted identity from the authentication mechanism, Reactor Context/authorization policy, and domain checks.

## 14. Essential testing matrix

| Scenario | What to verify |
| --- | --- |
| Anonymous GET protected | 401 or redirect per authentication entry point |
| Alice correct password | HTTP 200, name Alice |
| Alice wrong password | HTTP 401 |
| Admin accesses admin-only URL | 200 |
| Alice accesses admin URL | 403 |
| Alice calls method requiring ROLE_USER | 200 |
| Admin without ROLE_USER calls that method | 403 |
| Alice across Mono.delay + publishOn | Still reads Alice via ReactiveSecurityContextHolder |
| Bob across same endpoint/scheduler | Still reads Bob, never sees Alice |
| Subsequent request without Basic header | Does not receive prior request's identity |
| Same Mono source, subscribed under Alice then Bob context | Each subscription sees the right user |
| Same Mono source, subscribed without context | Does not see another subscription's user |
| Concurrent Mono.zip Alice/Bob | Two independent authentications |
| deferContextual and contextWrite | Correct key upstream, evaluated at subscribe time |
| contextWrite placed before downstream flatMap | Downstream does not receive upstream key by default |
| Nested subscribe() | Not treated as HTTP request propagation; test refactor |
| Blocking bridge to JDBC | Runs on boundedElastic or uses R2DBC; ownership still checked |
| User-scoped cache | Never returns data from another actor |
| Micrometer automatic mode | No value leakage on empty context or other callbacks |
| Downstream WebClient | Does not trust caller headers directly; uses proper token relay protocol |
| JWT/OIDC principal | Does not mistakenly cast to UserDetails; validates issuer/audience/signature |
| Cancellation/exception | Does not leak context or resources between subscriptions |

**Do not test only "works on the same thread".** Test **subscription A then B**, two concurrent subscribers, and scheduler switching. When bugs are hard to reproduce, increase coverage with stress/integration tests and measure redacted security audit signals; do not add random `Thread.sleep` calls to "force" races.

## 15. Self-assessment questions

**Question 1.** Does `ThreadLocal` belong to the thread or the HTTP request?

**Answer:** It belongs to the **thread**. Servlet filters can manage a scope roughly matching a synchronous request, whereas reactive pipelines do not bind a single thread to one subscription.

**Question 2.** In WebFlux, why is `SecurityContextHolder.getContext()` not the default choice for reading the user?

**Answer:** Spring Security WebFlux stores/passes the security context via **Reactor Context** and `ReactiveSecurityContextHolder`. ThreadLocal has no contract binding it to a subscriber when schedulers switch or threads are reused.

**Question 3.** Does `Mono.defer(...)` solve the mistake of reading the user from ThreadLocal?

**Answer:** No. It only delays evaluating the value until subscription time; it does not change the data source from thread to subscriber. You must use `deferContextual`/`ReactiveSecurityContextHolder`.

**Question 4.** In which direction does `contextWrite` take effect?

**Answer:** It enriches context for operators **upstream** of where it is placed; context flows along the subscription rather than simply flowing forward with `map` outputs.

**Question 5.** If Alice switches from event-loop to boundedElastic after `publishOn`, do we need a global `currentUser` variable?

**Answer:** No. Properly composed Mono/Flux chains preserve Reactor Context across the subscription; `ReactiveSecurityContextHolder.getContext()` retrieves Alice accurately.

**Question 6.** If a ThreadLocalAccessor/Micrometer automatically restores values, can ThreadLocal be used as the sole source for authorization?

**Answer:** No. Bridges depend on registration, scope, and cleanup conditions. Reactor Context/verified authentication remains the authoritative source in WebFlux, and authorization must still follow policy.

**Question 7.** Why is calling `subscribe()` inside `flatMap`/`map` suspect?

**Answer:** It creates an independent subscription, breaking composition of context, errors, cancellation, and lifecycle. You should return/compose publishers; if a true background job is needed, use a dedicated task boundary.

**Question 8.** When the same `Mono` is subscribed by two subscribers Alice and Bob, do we need a singleton Mono holding a `currentUser` field?

**Answer:** No. Context lives per subscription, so the same source can serve multiple actors without mutable global fields.

**Question 9.** If `ReactiveSecurityContextHolder.getContext()` returns empty, should we create a default admin principal so the service doesn't fail?

**Answer:** Absolutely not. For protected endpoints, missing authentication must be rejected or routed into the proper authentication flow; fail closed.

**Question 10.** Does using Reactor Context correctly automatically check invoice/order ownership?

**Answer:** No. It provides identity, while services/repositories must still check actor + action + resource/tenant and business state.

**Question 11.** Does `NoOpServerSecurityContextRepository` in the WebFlux demo mean passwords are compared in plaintext?

**Answer:** No. That is a repository that **does not persist security context across requests**, completely different from `NoOpPasswordEncoder`; passwords in the demo are still hashed with BCrypt.

**Question 12.** If a backend calls another service via WebClient, does that service automatically receive the upstream Reactor Context as credentials?

**Answer:** No. Each service has its own trust boundary; use OAuth2 token relay or an appropriate machine-to-machine authentication mechanism instead of sending a raw username and treating it as authenticated.

## 16. WebFlux code review checklist

- [ ] Does the project actually use WebFlux (`spring-boot-starter-webflux`) without confusing MVC and reactive adapters?
- [ ] Are `SecurityWebFilterChain`/`ServerHttpSecurity` used for WebFlux rather than Servlet `SecurityFilterChain`?
- [ ] Does the authentication mechanism properly verify credentials/JWT/OIDC via providers/decoders?
- [ ] Do reactive services read identity from `ReactiveSecurityContextHolder` or receive a verified actor ID?
- [ ] Is ThreadLocal `SecurityContextHolder.getContext()` avoided as the default "current user" inside `map`/`flatMap`?
- [ ] Are `Authentication`/tenant/role values never stored in static fields or mutable singleton fields?
- [ ] Is `Mono.just(ThreadLocal.get())` avoided so identity is not cached at assembly time?
- [ ] Are nested `subscribe()` calls and `block()` on the event-loop avoided?
- [ ] Do developers understand `contextWrite` affects upstream while `Mono.deferContextual` reads at subscription?
- [ ] Are scheduler hops (`publishOn`/delay) and at least two distinct-identity subscribers tested?
- [ ] Do HTTP tests use `WebTestClient` with real passwords and 401/403/200 in addition to mock auth tests?
- [ ] Is `@EnableReactiveMethodSecurity` enabled and do protected methods return `Mono`/`Flux` appropriately?
- [ ] Are domain ownership/tenant checks enforced on actual resources rather than only `authenticated()`?
- [ ] When calling blocking SDKs/DAOs, are `boundedElastic`/resource limits or reactive drivers used?
- [ ] When dispatching jobs to queues, are trusted actor metadata + reauthorization included instead of stale sessions?
- [ ] If using Micrometer context-propagation, have registered accessors, cleanup, and overhead been tested?
- [ ] Is Reactor Context never treated as a session repository, nor `contextWrite` as token relay?
- [ ] Are user-specific cached Mono/Flux publishers never shared across accounts without keys/scoping?
- [ ] Are raw Authentication objects, passwords, JWTs, session cookies, or sensitive headers excluded from logs?
- [ ] Are Boot/Security/Reactor versions kept on supported releases and tested after migration?

## 17. Short summary to remember

1. **ThreadLocal attaches to a thread; Reactor Context attaches to a subscriber/subscription.** Because reactive chains can switch threads and reuse pools, ThreadLocal cannot be used to infer identity across a chain.
2. **ReactiveSecurityContextHolder.getContext()** is the primary API to read the Spring Security context in WebFlux services, not Servlet `SecurityContextHolder.getContext()`.
3. **contextWrite adds context for upstream**, while `deferContextual` reads context at subscription time. Do not think of it as setting a global variable.
4. **publishOn/subscribeOn change scheduling, not the actor**, provided the pipeline preserves Reactor Context. Test identity, not thread names.
5. **Nested subscribe(), block(), raw Executors, and global caches** can break lifecycle/context or leak data; compose reactive operators and pass actor explicitly across bridges.
6. **Micrometer context propagation can temporarily restore ThreadLocal**, but this is a configurable compatibility mechanism, not a reason to change the trust model.
7. **Reactive method security and domain authorization remain mandatory**; valid authentication does not imply permission on every record.
8. **WebTestClient + StepVerifier** verify both real HTTP security and two subscribers with different identities, rather than just a single successful request.

## Official references

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Reactive Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Spring Security 6.5 — Security Context in Reactive Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Reactive Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Servlet Authentication Architecture (for ThreadLocal comparison)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Project Reactor 3 — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor 3 — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Reactor Mono Javadoc — contextWrite](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Spring Boot 3.5.16 release, 2026-06-25](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
