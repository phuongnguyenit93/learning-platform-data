# Scope and propagation direction of Reactor Context in a Publisher chain

> **Topic:** Spring Security – reactive  
> **Knowledge group:** Security context  
> **Goal:** Properly understand that Project Reactor's `Context` belongs to the **Subscriber/Subscription**, how `contextWrite` scopes data visibility **from downstream toward upstream**, how `deferContextual` reads data, and why Spring Security WebFlux can preserve authenticated identity when a reactive pipeline switches threads.

## 1. The problem: whose identity is executing the pipeline?

In traditional synchronous applications, developers sometimes use `ThreadLocal` to store a request-scoped value such as `username`, `traceId`, or tenant. That approach is misleading in Spring WebFlux: a single request may be processed across multiple callbacks and multiple threads; conversely, a single thread may serve multiple requests at different times. Therefore, **a thread cannot be treated as the identifier of a request or a user**.

Project Reactor provides **`Context`**: a key–value set bound to a subscriber in a reactive sequence, propagated via the subscription mechanism. It allows components within a pipeline to access contextual metadata without having to add `userId` or `traceId` to every method parameter.

Spring Security reactive uses this mechanism to provide `SecurityContext` to `Mono`/`Flux` stages within the same protected processing flow. The key things to grasp are **where `contextWrite` is placed, where `ContextView`-reading operators are placed, and subscription boundaries**.

### Learning outcomes

1. Distinguish `Context` from `onNext` data, from `ThreadLocal`, and from `SecurityContext`.
2. Describe the two directions of flow: data signals **upstream → downstream**, subscription/`Context` **downstream → upstream**.
3. Accurately predict values in `deferContextual` when changing the position of `contextWrite`.
4. Explain the principle that **each subscription has its own context**, without leaking across requests.
5. Understand how `flatMap`, inner publishers, `publishOn`, `subscribeOn`, `cache`, and `share` affect scope.
6. Use `ReactiveSecurityContextHolder` correctly and avoid detaching pipelines in ways that lose security info.
7. Run and verify Java 17+ examples with clear expected outputs.

## 2. First separate four things that are easily confused

| Term | What is it? | Timing/scope | Example |
| --- | --- | --- | --- |
| **`onNext` data** | Values emitted by a `Publisher` | Flows with data signals to the subscriber | `Mono<User>`, `Flux<Order>` |
| **Reactor `Context`** | Immutable-API key–value structure attached to a subscriber | Determined per subscription and the pipeline portion visible to that context | `traceId`, `tenantId` |
| **`ThreadLocal`** | Variable bound to a Java thread | Bound to the current thread, not the entire reactive chain | Logger MDC or imperative-style security context |
| **Spring Security `SecurityContext`** | Object holding Spring Security's `Authentication` | Provided via Reactor `Context` in WebFlux | Principal's username and `GrantedAuthority` |

**Exact relationship:** Reactor `Context` is the **context carrier**; Spring Security `SecurityContext` is the **security data being carried**. They are not the same data type and should not be conflated.

A `Mono<String>` can emit `"OK"` in `onNext`, while the Reactor Context attached to the subscriber holds `traceId="r-42"`. Changing or adding `traceId` does not alter `"OK"` unless code explicitly reads the Context to produce a new value.

### 2.1. Capabilities of the two APIs

```java
import reactor.util.context.Context;
import reactor.util.context.ContextView;
```

- `Context`: interface with context-building operations such as `put(key, value)`, `delete(key)`, and `putAll(...)`. Operations **return a new Context**, rather than mutating the old object in place.
- `ContextView`: read-only interface with `get(key)`, `getOrDefault(key, defaultValue)`, `hasKey(key)`, `getOrEmpty(key)`. Reactive operators typically expose only `ContextView` to consuming code.
- Keys can be `Object`, but in large applications use well-defined keys to avoid collisions. Values are also `Object`; **an immutable Context itself does not make value objects immutable**.
- Values in Context cannot be `null` by contract; to represent absence, delete the key or use `getOrDefault`/`getOrEmpty`.

Short example:

```java
Context original = Context.of("tenant", "A");
Context changed = original.put("tenant", "B");

System.out.println(original.get("tenant")); // A
System.out.println(changed.get("tenant"));  // B
```

The lines above are a Java **in-method snippet** that can run when placed in a class with `main` or a test, importing `reactor.util.context.Context`. It shows that `put` returns a new instance.

## 3. Propagation direction: data flows down, Context flows up

When reading Java code, we usually read top to bottom:

```java
Mono.just("payload")
    .map(v -> v.toUpperCase())
    .flatMap(v -> callService(v))
    .contextWrite(ctx -> ctx.put("requestId", "r-42"));
```

However, **code writing order is not the order in which all events occur**. There are three phases:

1. **Assembly:** builds the operator chain by calling `just`, `map`, `flatMap`, `contextWrite`; business logic does not execute yet.
2. **Subscription:** the final subscriber calls `subscribe` or the framework subscribes for it. The subscription signal travels **from the end of the chain up to the source**. `contextWrite` takes the Context supplied by downstream and creates a new context for upstream.
3. **Execution/data:** the publisher emits `onNext`, `onError`, or `onComplete` from the source toward downstream. When subscribed, `deferContextual` can observe the Context belonging to its corresponding upstream portion.

```text
      SOURCE / UPSTREAM                        DOWNSTREAM / SUBSCRIBER

Mono.deferContextual(read) -- map -- flatMap -- contextWrite -- subscribe()
          |                                       |
          |<-------------  Context / subscribe --|
          |                                       |
          |--------------- onNext / onError ----->|

Data direction:    upstream  ----------------------> downstream
Context direction: upstream  <---------------------- downstream
```

**Rule for reading code:** `contextWrite` placed **below** a read point in the expression chain (downstream) allows the upstream read point to see the value. Placing `contextWrite` **above** a read point (upstream) does not push Context downward alongside data for a downstream read point to see.

### 3.1. What does `contextWrite` do?

There are two common forms:

```java
publisher.contextWrite(Context.of("traceId", "r-42"));

publisher.contextWrite(ctx -> ctx.put("traceId", "r-42"));
```

- `contextWrite(ContextView)`: merges the input key–value pairs with the Context from downstream, creating a new Context for upstream.
- `contextWrite(Function<Context, Context>)`: receives the Context supplied by downstream and returns a Context to apply upstream. The lambda form is especially useful for adding or replacing a key while preserving existing keys.
- Avoid returning `Context.empty()` arbitrarily from a lambda because it can wipe out framework metadata, including keys needed by Spring Security or tracing systems.
- `contextWrite` is not an API that mutates a "global Context variable", nor an operation that updates all running subscribers.

## 4. Where `contextWrite` is placed determines where it is visible

Below are examples with deterministic outputs, assembled into a project in section 9.

### 4.1. Write downstream, read upstream: **visible**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("user=" + view.getOrDefault("user", "missing")))
    .contextWrite(ctx -> ctx.put("user", "lan"));

System.out.println(sequence.block());
```

Output:

```text
user=lan
```

`deferContextual` sits above `contextWrite`; as subscription travels upward, the source `Mono` receives a Context containing the key `user`.

**`block()` in this code is only for runnable `main`/test examples** to illustrate behavior. In a WebFlux controller/service, do not call `block()` on the event loop; return `Mono`/`Flux` to the framework.

### 4.2. Write upstream, read downstream: **not visible**

```java
Mono<String> sequence = Mono.just("event")
    .contextWrite(ctx -> ctx.put("user", "lan"))
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just("user=" + view.getOrDefault("user", "missing"))));

System.out.println(sequence.block());
```

Output:

```text
user=missing
```

`flatMap` reads the Context at a position downstream of the declared `contextWrite`. The `onNext("event")` signal can pass through `contextWrite`, but **Context is not a field automatically carried with `onNext`**. This is the most common operator-ordering mistake.

### 4.3. Writing the same key multiple times: **the write closer to the source wins in upstream scope**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("who=" + view.get("who")))
    .contextWrite(ctx -> ctx.put("who", "near"))
    .contextWrite(ctx -> ctx.put("who", "far"));

System.out.println(sequence.block());
```

Output:

```text
who=near
```

Subscription starts at `far`, travels up through `near`, and then reaches `deferContextual`. At the read point above both writes, `near` is the latest value for **this upstream section**.

**Do not turn this into a rule that "the last write in source code always wins".** The position of the **read** point matters more than the relative positions of two writes viewed in isolation.

### 4.4. Two read points on either side of `contextWrite`: **each point has its own view**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("up=" + view.get("who")))
    .contextWrite(ctx -> ctx.put("who", "near"))
    .flatMap(previous -> Mono.deferContextual(view ->
        Mono.just(previous + ",down=" + view.get("who"))))
    .contextWrite(ctx -> ctx.put("who", "far"));

System.out.println(sequence.block());
```

Output:

```text
up=near,down=far
```

The `up` read point sits upstream of both `near` and `far`, so it sees `near`. The read point inside the second `flatMap` sits downstream of `near` but upstream of `far`, so it sees `far`. Thus **two different ContextViews can appear in the same chain** without data races or random loss.

## 5. Subscriber scope and subscription boundaries

**A Publisher does not own a global Context.** Reactor binds Context to `Subscriber`. The same `Mono` definition can be subscribed to twice with different Context values:

```java
Mono<String> common = Mono.deferContextual(view ->
    Mono.just("user=" + view.get("user")));

System.out.println(common
    .contextWrite(ctx -> ctx.put("user", "lan")).block());

System.out.println(common
    .contextWrite(ctx -> ctx.put("user", "minh")).block());
```

Output:

```text
user=lan
user=minh
```

There is no shared user assignment stored on the `common` object for the next request to read. Each subscription creates its own subscriber path. That is the foundation for preserving user boundaries in a reactive pipeline when the framework and application are designed properly.

### 5.1. `flatMap`: inner publishers have their own scope

`flatMap` receives an item and creates a nested inner publisher. The nested publisher is subscribed to as a sub-sequence; it can observe the Context at the point where the subscriber is created and can write additional Context **for that sub-sequence itself**.

```java
Mono<String> sequence = Mono.just("event")
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just(value + ":" + view.get("who"))))
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just(value + ":" + view.get("who")))
        .contextWrite(ctx -> ctx.put("who", "inner")))
    .contextWrite(ctx -> ctx.put("who", "outer"));

System.out.println(sequence.block());
```

Output:

```text
event:outer:inner
```

Explanation:

- `contextWrite("outer")` at the end of the chain sets the value used by the main branch and the inner publishers subscribed within that branch's `flatMap`.
- The inner publisher in the second `flatMap` adds `contextWrite("inner")`, causing its own read point to see `inner`.
- Writing `inner` **does not leak outward to the entire main branch** and does not alter the result already produced in the first `flatMap`. An inner Context does not become a global variable.

A `flatMap` can run multiple inner sequences concurrently. When processing per tenant/user, do not share mutable variables to pass tenant across inner sequences; use Context for subscriber-bound metadata or pass explicit business parameters.

### 5.2. What is wrong with calling `subscribe()` manually inside `map`/`flatMap`?

The following pattern **intentionally illustrates a bug**, not recommended code:

```java
// Anti-pattern: manual subscribe creates a flow detached from the returned flow.
public Mono<String> wrong() {
    return Mono.just("start")
        .doOnNext(value ->
            expensiveOperation().subscribe(result -> saveResult(result)));
}
```

This snippet omits `expensiveOperation`/`saveResult` definitions and is illustrative only. The flaw is not just ignoring the result: calling `subscribe()` inside creates an **independent subscription**, does not automatically preserve the outer subscriber's Context, and makes errors and cancellation hard to keep tied to the same flow.

Structurally sound pipeline composition pattern:

```java
// Illustrative snippet, assuming expensiveOperation and saveResult exist.
public Mono<String> better() {
    return Mono.just("start")
        .flatMap(value -> expensiveOperation()
            .doOnNext(this::saveResult)
            .thenReturn(value));
}
```

`flatMap` hands the inner publisher to Reactor to manage inside the pipeline, so Context propagation, error handling, and cancellation remain consistent. In a real application, if `saveResult` is also asynchronous, return a `Mono` from it and chain with `flatMap` or `then` rather than putting async work inside `doOnNext`.

## 6. Context across `publishOn` and `subscribeOn`: not bound to threads

`publishOn(scheduler)` switches the execution thread downstream; `subscribeOn(scheduler)` affects where subscription to the source occurs and upstream scheduling according to the chain structure. They are **execution scheduling operators**. While inside a valid reactive subscription, they neither turn Reactor Context into `ThreadLocal` nor erase Context by default.

```java
Mono<String> sequence = Mono.just("event")
    .publishOn(Schedulers.parallel())
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just("trace=" + view.get("trace"))))
    .contextWrite(ctx -> ctx.put("trace", "r-42"));

System.out.println(sequence.block());
```

Output:

```text
trace=r-42
```

This snippet shows that context remains accessible after `publishOn`. The exact thread name is not fixed, but the trace value is reliably as expected.

**Do not equate with MDC/`ThreadLocal`:** `MDC.get("trace")` on the new thread may no longer have data if no ThreadLocal propagation mechanism is present. Reactor offers context-propagation integration depending on configuration and libraries, but do not assume every `ThreadLocal` is copied to another thread just because `contextWrite` was used. For authentication logic, read `ReactiveSecurityContextHolder` inside the reactive pipeline instead of imperative `SecurityContextHolder.getContext()`.

### 6.1. When does `deferContextual` read?

`Mono.deferContextual(view -> ...)` creates a publisher **using the context at subscription time**. It is not code that "reads Context once when the JVM creates the Mono variable". That is why a single shared `Mono` definition can still yield different results for two subscribers (such as users `lan` and `minh` in section 5).

`transformDeferredContextual((publisher, view) -> ...)` is another option when you want to transform a publisher while observing `ContextView`. For introductory cases and reading a single key, `deferContextual` is usually clearer.

## 7. Places where Context can still be "lost" or misused

### 7.1. Shared results via `cache()` or `share()`: beware per-user data

Consider the following expression:

```java
Mono<String> cached = Mono.deferContextual(view ->
    Mono.just("user=" + view.get("user"))).cache();

String first = cached.contextWrite(ctx ->
    ctx.put("user", "lan")).block();

String second = cached.contextWrite(ctx ->
    ctx.put("user", "minh")).block();
```

Because `cache()` memoizes the successful result of the first subscription, when both run sequentially as above, `first` is `user=lan` and `second` is also `user=lan`. **Context is not being shared like a mutable variable.** Rather, the **result value** itself was cached and reused across subscribers.

In Spring Security, do not create a global cached `Mono` whose content is built from `Authentication` or tenant. Per-user data must be loaded per request or cached under keys that guarantee user/permission isolation, with dedicated authorization checks. `share()`/`publish().refCount()` can also cause multiple subscribers to share a source, so never assume one subscriber's metadata safely turns into another subscriber's identity.

### 7.2. Boundaries without Reactor mechanisms

If you hand off to a plain `CompletableFuture`, an external library callback, or spawn a thread carrying only the `Mono` as an object, you cannot assume the other library carries `ContextView` across every step. When integrating a non-Reactor API, check adapters, pass metadata explicitly, or use a supported context propagation solution. Never use `ThreadLocal` out of habit to "patch" identity.

### 7.3. Context does not replace business inputs

A function `approveInvoice(invoiceId, tenantId)` should usually accept `tenantId` as a parameter if it is an important business condition that should be independently testable. Reactor Context fits cross-cutting pipeline metadata (trace ID or security context) rather than becoming a hiding place for all parameters, which makes testing and reuse harder.

### 7.4. Avoid storing unnecessary sensitive data in Context

- Do not put passwords, raw bearer tokens, refresh tokens, or secrets into Context just for convenience.
- Do not log the entire `Context`, `Authentication`, or raw headers.
- Use well-scoped keys, such as a private class/enum or constant object, to avoid colliding with framework keys.
- The Context API is immutable, but values can be mutable: avoid storing a mutable `Map` shared across requests and mutating it concurrently.
- Do not replace the entire Context with `Context.empty()` inside a Spring Security pipeline, as that can drop critical framework keys.

## 8. Spring Security WebFlux integration: who sets and who reads SecurityContext?

In reactive security, `SecurityContext` holds `Authentication`. Spring Security configures components such as `ReactorContextWebFilter` and the corresponding authentication mechanisms so security information is available in the request's Reactor Context. Application code typically **reads via**:

```java
ReactiveSecurityContextHolder.getContext()
```

This method returns `Mono<SecurityContext>`, allowing non-blocking use inside a pipeline:

```java
Mono<String> currentUsername = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

This snippet can reside in a protected WebFlux controller/service method, with imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
```

When an authenticated HTTP Basic/JWT/session request is allowed through, Spring Security sets the proper SecurityContext for the request's publisher. **Never trust** self-declared usernames/roles from body/query/headers and attach them to Context to bypass authorization.

### 8.1. Non-HTTP testing: providing Authentication for a specific subscription

`ReactiveSecurityContextHolder.withAuthentication(authentication)` creates a `Context` that can be used with `contextWrite` **in tests**:

```java
Authentication auth =
    new TestingAuthenticationToken("lan", "unused", "ROLE_USER");

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(name)
    .expectNext("lan")
    .verifyComplete();
```

Import `TestingAuthenticationToken` from `org.springframework.security.authentication`, `StepVerifier` from `reactor.test`. This is **code placed in a test method**, using a fake token to simulate context; it does not prove that a password was verified over HTTP or JWT.

In the configuration above, `contextWrite` is placed **downstream** of `getContext()`, matching the propagation direction. If placed **upstream** of `getContext()`, the downstream read point will not automatically receive that identity.

### 8.2. Reading SecurityContext after an async boundary

A service can return:

```java
public Mono<String> currentUserAfterAsync() {
    return Mono.delay(Duration.ofMillis(1))
        .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This snippet is an illustrative method requiring `java.time.Duration` along with Reactor/Security classes. `Mono.delay` emits its signal on an asynchronous scheduler; the chain still accesses the security context via Reactor. There is no need to stay on the original thread, and no `block()`.

## 9. Complete Java 17+ example: Reactor Context + secure WebFlux API

The Maven project below uses **Spring Boot 3.5.16** with Java 17+, including pure Reactor Context read/write code, a WebFlux API using reactive Spring Security, and JUnit/`StepVerifier`/`WebTestClient` for verification. This is a pinned version for learning and reproducibility; for production projects, choose a supported Spring Boot branch and use consistent library versions via its BOM.

```text
reactor-context-security-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/
    │   ├── Application.java
    │   ├── ContextDirectionExamples.java
    │   ├── SecurityConfiguration.java
    │   └── ContextController.java
    └── test/java/demo/context/
        ├── ContextDirectionTests.java
        └── WebSecurityContextTests.java
```

### 9.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>reactor-context-security-demo</artifactId>
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

Spring Boot manages compatible Reactor and Spring Security versions. Do not arbitrarily add separate versions for `reactor-core`, `reactor-test`, or `spring-security-test` in a project using Spring Boot parent. `reactor-core` is brought in by the WebFlux starter; `reactor-test` is only needed in test scope.

### 9.2. `src/main/java/demo/context/Application.java`

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 9.3. `src/main/java/demo/context/ContextDirectionExamples.java`

This class contains only functions returning `Mono` for testing; do not call `block()` in reactive applications.

```java
package demo.context;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ContextDirectionExamples {

    private static final String KEY = "who";

    private ContextDirectionExamples() {
    }

    public static Mono<String> visibleUpstream() {
        return Mono.deferContextual(view ->
                Mono.just("user=" + view.getOrDefault(KEY, "missing")))
            .contextWrite(ctx -> ctx.put(KEY, "lan"));
    }

    public static Mono<String> invisibleDownstream() {
        return Mono.just("event")
            .contextWrite(ctx -> ctx.put(KEY, "lan"))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just("user=" + view.getOrDefault(KEY, "missing"))));
    }

    public static Mono<String> nearerWriteWins() {
        return Mono.deferContextual(view ->
                Mono.just("who=" + view.get(KEY)))
            .contextWrite(ctx -> ctx.put(KEY, "near"))
            .contextWrite(ctx -> ctx.put(KEY, "far"));
    }

    public static Mono<String> twoReadPositions() {
        return Mono.deferContextual(view ->
                Mono.just("up=" + view.get(KEY)))
            .contextWrite(ctx -> ctx.put(KEY, "near"))
            .flatMap(previous -> Mono.deferContextual(view ->
                Mono.just(previous + ",down=" + view.get(KEY))))
            .contextWrite(ctx -> ctx.put(KEY, "far"));
    }

    public static Mono<String> nestedScope() {
        return Mono.just("event")
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ":" + view.get(KEY))))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ":" + view.get(KEY)))
                .contextWrite(ctx -> ctx.put(KEY, "inner")))
            .contextWrite(ctx -> ctx.put(KEY, "outer"));
    }

    public static Mono<String> acrossScheduler() {
        return Mono.just("event")
            .publishOn(Schedulers.parallel())
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just("trace=" + view.get("trace"))))
            .contextWrite(ctx -> ctx.put("trace", "r-42"));
    }

    public static Mono<String> currentSubscriber() {
        return Mono.deferContextual(view ->
            Mono.just("user=" + view.get(KEY)));
    }
}
```

Placing these methods in a pure Java `final` class separates Reactor Context rules from Spring HTTP config. `Mono.deferContextual` is evaluated per subscription; `Mono.just` emits values, while the `contextWrite` calls scope the visibility of key values.

### 9.4. `src/main/java/demo/context/SecurityConfiguration.java`

```java
package demo.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public-context").permitAll()
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails lan = User.withUsername("lan")
            .password("{noop}learn123")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(lan);
    }
}
```

`SecurityWebFilterChain` is the configuration for WebFlux, distinct from `SecurityFilterChain` in Servlet. The in-memory user and `{noop}` are for local illustration only; production must have a strong password encoder, HTTPS, secret management, and proper identity mechanisms.

### 9.5. `src/main/java/demo/context/ContextController.java`

```java
package demo.context;

import java.time.Duration;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ContextController {

    @GetMapping("/api/public-context")
    public Mono<String> publicContext() {
        return Mono.deferContextual(view ->
                Mono.just("trace=" +
                    view.getOrDefault("traceId", "missing")))
            .contextWrite(ctx -> ctx.put("traceId", "r-42"));
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return Mono.delay(Duration.ofMillis(1))
            .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
            .map(SecurityContext::getAuthentication)
            .map(auth -> "user=" + auth.getName());
    }
}
```

Explanation of the two endpoints:

- `GET /api/public-context`: permitted without login. The method adds `traceId="r-42"` to **this publisher's local subscription** and reads it upstream, returning `trace=r-42`. This is an application key for illustration, **not security authentication**.
- `GET /api/me`: requires valid HTTP Basic; Spring Security puts the caller's `SecurityContext` into Reactor Context. `Mono.delay` creates an asynchronous boundary, yet `flatMap` still accesses `ReactiveSecurityContextHolder.getContext()`. The result for account `lan` is `user=lan`. We do not set identity ourselves using `contextWrite` in the controller.

### 9.6. `src/test/java/demo/context/ContextDirectionTests.java`

```java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ContextDirectionTests {

    @Test
    void downstreamWriteIsVisibleUpstream() {
        StepVerifier.create(ContextDirectionExamples.visibleUpstream())
            .expectNext("user=lan")
            .verifyComplete();
    }

    @Test
    void upstreamWriteIsInvisibleDownstream() {
        StepVerifier.create(ContextDirectionExamples.invisibleDownstream())
            .expectNext("user=missing")
            .verifyComplete();
    }

    @Test
    void nearestWriteWinsInUpstreamScope() {
        StepVerifier.create(ContextDirectionExamples.nearerWriteWins())
            .expectNext("who=near")
            .verifyComplete();
    }

    @Test
    void readingOnTwoSidesSeesDifferentValues() {
        StepVerifier.create(ContextDirectionExamples.twoReadPositions())
            .expectNext("up=near,down=far")
            .verifyComplete();
    }

    @Test
    void innerWriteIsLocalToInnerPublisher() {
        StepVerifier.create(ContextDirectionExamples.nestedScope())
            .expectNext("event:outer:inner")
            .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOn() {
        StepVerifier.create(ContextDirectionExamples.acrossScheduler())
            .expectNext("trace=r-42")
            .verifyComplete();
    }

    @Test
    void separateSubscribersCarrySeparateValues() {
        Mono<String> source = ContextDirectionExamples.currentSubscriber();

        StepVerifier.create(source.contextWrite(ctx ->
                ctx.put("who", "lan")))
            .expectNext("user=lan")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(ctx ->
                ctx.put("who", "minh")))
            .expectNext("user=minh")
            .verifyComplete();
    }

    @Test
    void reactiveSecurityContextCanBeProvidedForOneTest() {
        Authentication authentication =
            new TestingAuthenticationToken("lan", "unused", "ROLE_USER");

        Mono<String> username = ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));

        StepVerifier.create(username)
            .expectNext("lan")
            .verifyComplete();
    }
}
```

These tests verify **Context behavior using deterministically predicted values**. Do not test by "checking what gets printed" or guessing thread names. The last test only proves a security context can be attached to one subscription and read back; it does not verify HTTP credentials.

### 9.7. `src/test/java/demo/context/WebSecurityContextTests.java`

```java
package demo.context;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class WebSecurityContextTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicContextHasLocalTrace() {
        client.get().uri("/api/public-context")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("trace=r-42");
    }

    @Test
    void missingAuthenticationIsRejected() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicUserRemainsAvailableAfterAsyncBoundary() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("lan", "learn123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=lan");
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("lan", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

`WebTestClient` tests the WebFlux HTTP layer and Spring Security; `springSecurity()` comes from `spring-security-test`. The HTTP tests confirm a request's identity across an async boundary, while the `StepVerifier` tests check setting and reading Context at various operator positions.

### 9.8. Running the project and expected results

Requires Java 17+ and a compatible Maven. In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

The test suite has **12 `@Test` methods** (8 Context tests + 4 HTTP tests). With compatible configuration and dependencies, all are expected to PASS. Maven writes reports in `target/surefire-reports`. If tests fail to run, check `spring-boot-starter-test`, `reactor-test`, JDK version, and classpath.

Start the server:

```bash
mvn spring-boot:run
```

Call the API:

```bash
curl -i http://localhost:8080/api/public-context
curl -i http://localhost:8080/api/me
curl -i -u lan:learn123 http://localhost:8080/api/me
curl -i -u lan:wrong http://localhost:8080/api/me
```

| Request | Expected status | Successful response body |
| --- | --- | --- |
| GET `/api/public-context` | **200** | `trace=r-42` |
| GET `/api/me` without credentials | **401** | Depends on authentication entry point |
| GET `/api/me` with `lan:learn123` | **200** | `user=lan` |
| GET `/api/me` with `lan:wrong` | **401** | Depends on authentication failure handler |

On PowerShell, use `curl.exe` if `curl` aliases a PowerShell cmdlet. All HTTP examples use GET, so CSRF does not need to be disabled for this lesson. Do not hard-code 401 error headers/body as they can differ across configurations.

## 10. Proving the three rules yourself with `StepVerifier`

`StepVerifier` is a tool for observing a subscription. It can provide an initial Context **directly at the test subscriber**, which is very useful when testing an isolated function that does not call `contextWrite` internally:

```java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just("trace=" + view.get("trace")));

StepVerifier.create(source)
    .expectAccessibleContext()
    .then()
    .expectNext("trace=t-1")
    .verifyComplete();
```

**Note:** the snippet above is intentionally **incomplete** because the `trace` key has not been provided yet: if run as-is, `view.get("trace")` will fail. You must configure the Context for the subscriber via the `StepVerifierOptions` API:

```java
StepVerifierOptions options = StepVerifierOptions.create()
    .withInitialContext(Context.of("trace", "t-1"));

StepVerifier.create(source, options)
    .expectAccessibleContext()
    .contains("trace", "t-1")
    .then()
    .expectNext("trace=t-1")
    .verifyComplete();
```

This is an **addition inside a JUnit test method**, with imports:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;
import reactor.core.publisher.Mono;
```

If you prefer not to use `StepVerifierOptions`, the simpler alternative is `StepVerifier.create(source.contextWrite(Context.of("trace", "t-1")))`. Both test supplying Context from the subscriber side; the difference is that `withInitialContext` directly injects Context when creating StepVerifier.

### Check A: Move `contextWrite` by one step

Start with `deferContextual(...).contextWrite(...)` and observe the key. Then move `contextWrite` **above** the `flatMap` containing the read point. Predict `missing` before running the test. If you only remember "context travels with data", you will guess wrong.

### Check B: Add `contextWrite` to an inner publisher

Keep the outer Context as `outer`. Inside the second inner publisher, add `contextWrite(...inner...)`. Run StepVerifier on the nested chain and observe `event:outer:inner`, proving independent inner scope.

### Check C: Two subscribers sharing one Mono

Define `source = Mono.deferContextual(...)` once. Use `contextWrite` on each subscription with `lan` and `minh`. Two separate values are read, with no global "last user".

## 11. Common mistakes when using Reactor Context for security

| Mistake | Symptom/consequence | Fix |
| --- | --- | --- |
| Assuming `Context` travels with `onNext` | Downstream read gets `missing` even with `contextWrite` above | Place `contextWrite` **downstream** of the read point that needs to see it |
| Treating Context as a global variable of `Mono` | Worrying about overwrites between requests or mutating shared state | Remember Context is bound to the subscriber; use `deferContextual` |
| Using `ThreadLocal`/imperative `SecurityContextHolder` in WebFlux | Identity lost after `publishOn`/`delay`, caller confused | Use `ReactiveSecurityContextHolder` and Reactor chains |
| Calling `subscribe()` manually in controller/service | Task detaches from request, context/errors/cancellation leave parent flow | Return the publisher and compose with `flatMap`/`then` |
| Returning `Context.empty()` in `contextWrite` | Wipes existing security/tracing keys upstream | Use `ctx.put`/merge to preserve other keys |
| Writing Context in an inner `flatMap` and expecting outer to read it | Outer does not see the inner key | Move the write down to the scope enclosing the read point |
| Caching a publisher with per-user results | Second request may receive data computed for the first request | Do not cache per-user results globally; partition cache and check permissions |
| Basing access-control logic on an `X-User` header | Client can spoof identity if the system trusts self-declared headers | Rely on verified `Authentication` from Spring Security |
| Copying Context containing a shared mutable `Map` | Race conditions and uncontrolled value mutations | Use immutable values or explicitly design owner/lifetime |
| Using Context as a store for all business data | Functions hard to test, hidden context dependencies | Pass explicit arguments for business logic; Context for cross-cutting metadata |
| Confusing automatic Context propagation with ThreadLocal propagation | MDC can be empty even while Reactor Context still holds values | Configure a supported bridge if needed; test with schedulers |
| Testing only with `mockUser` and concluding real login works | Authorization passes while real authentication may be broken | Add real HTTP Basic/JWT/session tests via `WebTestClient` |

### When SecurityContext is missing, check in order

1. Is the publisher being subscribed **by the framework** in a protected WebFlux request, or did you call `subscribe()` manually elsewhere?
2. Did authentication succeed? Before reading context, confirm the flow ran through the security chain.
3. Is there a `contextWrite(ctx -> Context.empty())`, a `Context.of(...)` replacing old context, or a duplicate key overwrite?
4. Is there a `flatMap` creating an inner subscription where `contextWrite` was placed outside the read point's scope?
5. Is `cache()`, `share()`, or a `Mono` with user-bound results being shared?
6. Did you cross into callbacks/Futures outside Reactor and forget the context propagation boundary?
7. Did you accidentally use Servlet-style `SecurityContextHolder` instead of `ReactiveSecurityContextHolder`?

Do not log raw credentials, JWTs, or the entire `Authentication` to debug. Use status categorization, correlation IDs, and safe authority checks when needed.

## 12. Self-check questions

**Q1.** In `Mono.deferContextual(...).contextWrite(...)`, why does the read point **above** the write still see the key?  
**Answer:** Because `contextWrite` transforms the Context supplied by the downstream subscriber to the upstream portion as subscription travels from the end of the chain up to the source.

**Q2.** If `contextWrite` is placed above a `flatMap` containing `deferContextual`, why might `flatMap` read `missing`?  
**Answer:** Because `Context` does not travel along with `onNext`; a downstream read point does not inherit a write that only applies upstream.

**Q3.** Two requests share a `Mono` declared as a field. Request A has user `lan`; request B has user `minh`. Does Reactor Context turn into a shared user?  
**Answer:** No. Context is bound to the subscriber/subscription path, unless the code introduces unsafe shared state or results such as a cache holding per-user data.

**Q4.** Does `publishOn(Schedulers.parallel())` automatically erase Reactor Context?  
**Answer:** No. Switching threads does not lose Reactor Context in a valid Reactor pipeline. `ThreadLocal` has separate rules and requires a propagation mechanism if used.

**Q5.** An inner publisher inside `flatMap` writes `tenant="B"` with `contextWrite`. Will another inner publisher automatically see `B`?  
**Answer:** No. A write inside one inner subscription takes effect only in the upstream portion of that inner subscription.

**Q6.** Is using `ReactiveSecurityContextHolder.withAuthentication(auth)` in production to accept client-sent roles reasonable?  
**Answer:** No. It can be used in tests or controlled integration code, but production must rely on authentication verified by a trusted security mechanism.

**Q7.** Why can `cachedMono.contextWrite(user=lan)` and `cachedMono.contextWrite(user=minh)` both return Lan's value?  
**Answer:** If `cachedMono` cached **the result from the first subscription's Context**, subsequent subscriptions can receive that cached value. That is a sensitive-data caching design bug, not Reactor sharing a mutable Context.

**Q8.** If you want to test per-subscription context without writing an HTTP handler, what do you use?  
**Answer:** Combine `StepVerifier`, `Mono.deferContextual`, `contextWrite`, or `StepVerifierOptions.withInitialContext`, then assert concrete `onNext` values.

## 13. Summary and further reading

- **Reactor Context is bound to the subscriber**, not to a thread and not a field on each `onNext`.
- **Data signals flow upstream → downstream; Context can be supplied downstream → upstream** along the subscription path.
- **`contextWrite` affects only the portion upstream of where it is placed**. The read point's position and writes closest to it determine the observed value.
- **`flatMap` creates inner publishers with their own scope**; writing inside one inner publisher does not alter the Context of other branches.
- **`publishOn`/`subscribeOn` do not drop Reactor Context by default**; however, ThreadLocal bridges and non-Reactor systems require separate consideration.
- In Spring Security WebFlux, use **`ReactiveSecurityContextHolder`**; avoid detaching subscriptions, wiping the whole context, or caching user-bound data uncontrolledly.

**Official sources:**

- Project Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html
- Project Reactor – Reference Guide (Context, threading, and testing): https://projectreactor.io/docs/core/3.7.0/reference/
- Project Reactor – Reactor Test `StepVerifier`: https://projectreactor.io/docs/test/release/reference/
- Spring Security – Reactive Method Security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – Reactive Web Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
