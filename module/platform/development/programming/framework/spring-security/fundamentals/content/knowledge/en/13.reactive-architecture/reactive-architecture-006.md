# How Reactor Context Changes Identity Propagation Across Processing Steps

> **Topic:** Spring Security - fundamentals → Reactive architecture  
> **Focus:** User identity/`Authentication` travels through the WebFlux processing chain per *subscriber*, rather than assuming it always lives in a thread's `ThreadLocal`.

## 1. What Should You Understand After This Lesson?

- Why reading identity from the `ThreadLocal`-backed `SecurityContextHolder` familiar in Servlet applications is no longer a reliable mechanism for the entire reactive processing flow.
- How Reactor `Context` is attached to a *subscription/subscriber*, written via `contextWrite`, and read via `deferContextual`.
- How Spring Security WebFlux uses `ReactiveSecurityContextHolder` so handlers, services, and authorization checks see the `SecurityContext`/`Authentication` within the same reactive chain.
- How to spot points where context is easily lost: manually calling `subscribe()`, `block()`, building detached chains, or switching to non-Reactor async APIs.

## 2. The Problem: Identity Cannot Depend on a Thread

In traditional Servlets, an HTTP request is typically processed in a model where a thread stays bound to the request for much of its lifecycle. `SecurityContextHolder` uses `ThreadLocal` by default, so code running on that thread can read `Authentication`:

~~~java
// Common access pattern in Servlet code (illustrative, not a standalone program).
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, a request is modeled by `Mono`/`Flux`, executed upon subscription. A pipeline can switch threads at scheduler boundaries, await I/O without holding a thread, and combine multiple tasks with `flatMap`. The current thread is therefore **not a stable identifier of the request**. An empty `ThreadLocal` or one carrying an unexpected value cannot be used as proof of a user inside a reactive chain.

For example, Alice's request might flow through:

~~~text
HTTP request (Alice)
    |
    v
WebFilter authenticates / loads SecurityContext
    |
    v
Handler (event-loop thread A)
    |
    v
Service -- flatMap --> asynchronous query (thread may change)
    |
    v
Service continues (thread B or A)
    |
    v
HTTP response
~~~

The true requirement is: **every step belonging to Alice's processing chain reads Alice's `Authentication`, even if threads change; Bob's request must never see Alice's identity.**

## 3. What Is Reactor Context Actually?

`reactor.util.context.Context` is an *immutable* key–value map used to carry metadata along a subscription. It does not travel in `onNext` data payloads and is not a global variable. An operator can read the downstream subscriber's `ContextView`; `Context` is suited for correlation IDs, tracing, and security context.

| Mechanism | Bound to | Meaning for identity |
| --- | --- | --- |
| `ThreadLocal` | Executing thread | May not follow the request when execution scheduling shifts |
| Function parameter, e.g., `findByUser(userId)` | Specific invocation | Explicit and ideal for business data that should be passed directly |
| Reactor `Context` | Subscriber/subscription in a reactive chain | Propagates metadata implicitly across Reactor operators in the same chain |
| `ReactiveSecurityContextHolder` | `SecurityContext` stored in Reactor `Context` | Spring Security API to read/set the reactive authentication context |

Key properties:

1. **Written at subscribe time.** `contextWrite(...)` attaches/updates the context visible to *upstream* operators as the subscription travels from the tail of the chain back toward the source. Chain position matters more than left-to-right reading order in code.
2. **Read at execution time.** `Mono.deferContextual(view -> ...)` fetches `ContextView` only when subscribed. Reading context too early, outside a subscriber, does not establish a “default” identity for a request.
3. **Immutable and scoped.** `put` returns a new context; it does not mutate a shared instance. Two separate subscriptions can carry different users even while sharing the exact same pipeline definition.
4. **Generally flows across Reactor operators.** `map`, `flatMap`, and `publishOn` continue working with context when composed into a proper reactive chain. A `contextWrite` inside a child publisher of `flatMap` affects only that child publisher's scope and does not mutate outer branches.
5. **Does not automatically become `ThreadLocal`.** Optional *context-propagation* mechanisms can bridge with `ThreadLocal` for compatible libraries when properly configured. Reactor `Context` and reactive Spring Security remain distinct concepts; do not rely on that bridge by default.

### Read Bottom-Up When Seeing `contextWrite`

~~~java
Mono<String> name =
    Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("user", "guest")))
        .contextWrite(ctx -> ctx.put("user", "alice"));

// name.block() returns "alice" when run outside the event loop.
~~~

`contextWrite` appears at the bottom of the snippet, which is *downstream* of `deferContextual`, so the value `alice` is supplied to the *upstream* reader.

Conversely:

~~~java
Mono<String> name =
    Mono.just("ignored")
        .contextWrite(ctx -> ctx.put("user", "alice"))
        .flatMap(ignored ->
            Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("user", "guest"))));

// name.block() returns "guest": contextWrite sits above flatMap.
~~~

The two snippets above only illustrate Reactor semantics, **not user authentication**. `contextWrite` can store arbitrary metadata; Spring Security only trusts an `Authentication` created/verified by a valid security mechanism.

## 4. Runnable Practice: One Pipeline, Multiple Identities

This example uses Java 17+ and Reactor Core. Create a small Gradle project (or place it in an existing standalone Java/Gradle project). File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.7.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ContextIdentityDemo'
}
~~~

File `src/main/java/demo/ContextIdentityDemo.java`:

~~~java
package demo;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ContextIdentityDemo {
    private static final String USER_KEY = "user";

    private static Mono<String> readIdentity(String stage) {
        return Mono.deferContextual(view ->
            Mono.just(stage + "=" + view.getOrDefault(USER_KEY, "guest"))
        );
    }

    private static Mono<String> pipeline() {
        return readIdentity("handler")
            .publishOn(Schedulers.boundedElastic())
            .flatMap(first ->
                readIdentity("service")
                    .map(second -> first + " | " + second)
            );
    }

    public static void main(String[] args) {
        System.out.println(
            pipeline().contextWrite(Context.of(USER_KEY, "alice")).block()
        );
        System.out.println(
            pipeline().contextWrite(Context.of(USER_KEY, "bob")).block()
        );
        System.out.println(pipeline().block());
    }
}
~~~

Run with JDK 17+ and Gradle 8.x:

~~~bash
gradle run --quiet
~~~

Stdout (three lines printed by the program, ignoring Gradle output):

~~~text
handler=alice | service=alice
handler=bob | service=bob
handler=guest | service=guest
~~~

**Explanation:** `readIdentity` does not read the thread; it defers reading `ContextView` until subscription. `publishOn` switches the scheduler for downstream processing without losing the value for the respective subscription. Each `pipeline()`/`block()` call in the example creates one subscription; only subscriptions given `Context.of(USER_KEY, ...)` read `alice` or `bob`. The third line lacks that metadata, so it falls back to `guest`. `block()` is only in the test `main` program; **never call `block()` inside a WebFlux handler/service handling requests**.

> Contrast: the same `readIdentity` helper is reused, yet results differ per subscriber. This is the core mechanism that keeps identities from mixing across concurrent requests.

## 5. Where Does Spring Security WebFlux Put `Authentication`?

`Authentication` represents the principal and authentication/authority details. `SecurityContext` holds `Authentication`. In the reactive stack, `ReactiveSecurityContextHolder` is the API for accessing `SecurityContext` through Reactor `Context`; it does not require handlers to read `ThreadLocal`.

Conceptual flow:

~~~text
Request
  -> SecurityWebFilterChain
     -> validates token / HTTP Basic / session per configuration
     -> SecurityContext for the request
     -> Reactor Context of the processing chain
  -> Controller
     -> Service
        -> ReactiveSecurityContextHolder.getContext()
        -> SecurityContext.getAuthentication()
        -> Authentication.getName(), getAuthorities()...
  -> Authorization / response
~~~

`ReactorContextWebFilter` uses `ServerSecurityContextRepository` to supply `SecurityContext` to `ReactiveSecurityContextHolder`. Other authentication filters in `SecurityWebFilterChain` also participate in establishing the request context depending on the configured mechanism. **Do not assume every system uses sessions:** a JWT resource server can validate a token per request, while another application may persist context via a repository.

APIs to distinguish:

- `ReactiveSecurityContextHolder.getContext()` → `Mono<SecurityContext>`; may be empty if no context exists.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)` → a Reactor `Context` containing the corresponding `Mono<SecurityContext>`, useful in tests or intentionally constructed pipelines.
- `ReactiveSecurityContextHolder.withSecurityContext(monoContext)` → sets a `Mono<? extends SecurityContext>`.
- `ReactiveSecurityContextHolder.clearContext()` → a Reactor context transformer for the applied scope, not an operation that wipes authentication state across all requests.
- `SecurityContextHolder.getContext()` → imperative/thread-local API typical of Servlets; **do not use as the default principal source in reactive business logic**.

### Controller Example in a WebFlux App with Spring Security Enabled

The snippet below is a component meant for a Spring WebFlux application with appropriate Spring Security dependencies; it is **not** a standalone Java program:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class WhoAmIController {
    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication())
            )
            .map(Authentication::getName)
            .map(name -> "user=" + name);
    }
}
~~~

When the request is authenticated and passes through the right filter chain, the username is read **inside the publisher**. If no `SecurityContext`/`Authentication` exists, the snippet returns `Mono.empty()`; reading the principal by itself does not replace authorization.

Protect the endpoint with the security configuration itself, such as this configuration snippet inside a WebFlux application:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/me").authenticated()
            .anyExchange().permitAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Corresponding imports include `@Bean` from Spring Context, `SecurityWebFilterChain`, `ServerHttpSecurity`, and `org.springframework.security.config.Customizer`. This configuration only illustrates endpoint rules; a real application needs an appropriate mechanism to issue/verify credentials. If `@EnableReactiveMethodSecurity` is enabled, permission checks on reactive methods also rely on the security context in the Reactor chain.

### Example of Attaching an Identity in a Reactive Test

In tests with `reactor-test` and `spring-security-core` dependencies, you can use `StepVerifier` and a known `Authentication`:

~~~java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice",
    "unused",
    List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(username)
    .expectNext("alice")
    .verifyComplete();
~~~

Requires imports for `java.util.List`, `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `SecurityContext`, `ReactiveSecurityContextHolder`, `Mono`, and `StepVerifier`. The three-argument constructor of `UsernamePasswordAuthenticationToken` creates an authentication marked as authenticated for testing purposes. This test proves **context propagation within the pipeline**, not password/token validation correctness.

## 6. How Does Identity Flow Through Processing Steps?

Suppose the request has been authenticated by the security filters. The controller can directly return a `Mono` produced by a service; the service continues calling a reactive repository:

~~~java
// The method below is a composition example, not a standalone class.
Mono<String> loadMyProfile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(profileRepository::findDisplayNameByUsername);
}
~~~

Here `flatMap` chains the repository publisher into the same flow. Identity is resolved at execution time, rather than captured prematurely in a thread-local variable. For business logic requiring auditing or querying by resource owner, passing `username`/`userId` explicitly into the repository also makes authorization boundaries clearer. **Reactor Context is metadata-propagation infrastructure; it does not automatically append a `WHERE owner_id = ...` clause to your queries.**

Two concurrent requests can execute the same controller/service code while each subscription carries a different context. Conversely, if an independent background task is spawned using `subscribe()` inside a service, it becomes a new subscription and is not guaranteed to inherit the security context from the original request.

Another common misconception: `contextWrite` inside a child publisher changes only that child's scope. For example:

~~~java
Mono<String> inner = readCurrentUser()
    .contextWrite(ctx -> ctx.put("user", "inner"));

Mono<String> outer = Mono.just("start")
    .flatMap(ignored -> inner)
    .flatMap(ignored -> readCurrentUser())
    .contextWrite(ctx -> ctx.put("user", "outer"));
~~~

In this example, assuming `readCurrentUser()` reads the Reactor key `user` as in the pure Reactor example: the read inside `inner` sees `inner`, while the final read in `outer` sees `outer`. Do not infer that writing context in one branch updates all subscribers or a shared “session.”

## 7. Common Mistakes and How to Fix Them

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` is empty in a WebFlux service | Code depends on `ThreadLocal` | Read reactively with `ReactiveSecurityContextHolder.getContext()` inside the publisher |
| `deferContextual` does not see the written key | `contextWrite` was placed on the wrong side or applies only to another branch | Trace subscription flow bottom-up and check `flatMap` boundaries |
| Principal disappears after manual `subscribe()` | Created a detached subscription; request context is not propagated as expected | Return `Mono`/`Flux` for the framework to manage the subscription; chain via `flatMap`, `then`, etc. |
| `block()` slows down, errors, or loses context in a handler | Blocks the event loop and often spawns a secondary subscription | Keep the pipeline asynchronous; use reactive operators and avoid `block()` on the WebFlux request path |
| Metadata disappears when switching to `CompletableFuture`/another library callback | Left Reactor's context model | Pass required data explicitly as arguments; if needed, use compatible, explicitly configured context propagation |
| Two requests appear to share a user | Using static variables, mutable singletons, or uncleaned ThreadLocal | Never store `Authentication` in global state; keep scope per subscriber and test isolation |
| `SecurityContext` is present yet unauthorized access occurs | Confusing presence of context with authorization | Enforce `SecurityWebFilterChain`/method security and check permissions on business resources |

**Security note:** `Authentication` can contain sensitive credentials, claims, or tokens. Do not log the entire `SecurityContext` or serialize it to send to external systems. Use only the minimum data required for an authorized purpose, and let the framework enforce authentication/authorization.

## 8. How to Verify and Debug

1. Verify the request went through the right `SecurityWebFilterChain` and that the endpoint has the intended authentication requirement.
2. Add an observation point *inside the publisher*, such as `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication)`; verify the empty state separately from a populated principal.
3. Check for `subscribe()`, `block()`, `toFuture()`, or non-Reactor callbacks creating new boundaries; inspect `contextWrite` placement.
4. Write tests with `StepVerifier`: run the same pipeline definition with `alice`, `bob`, and unauthenticated contexts; verify results stay isolated without cross-user leakage.
5. Verify endpoint and resource access rules. Having the right principal does not guarantee having the right permission.

Three self-check questions:

- Why can `publishOn` switch threads while a `deferContextual` operator in the same chain still reads metadata from the subscriber?
- In `source.contextWrite(...).flatMap(...)`, is `flatMap` guaranteed to see the key just written? Explain using context propagation direction at subscribe time.
- Why is reading `username` from `ReactiveSecurityContextHolder` and passing it to a repository sensible, yet reading username alone without owner/role checks insufficient for security?

**Conclusion:** WebFlux shifts the practical unit of identity propagation from the assumption “one thread holds the request” to **a reactive subscription carrying context**. Spring Security uses `ReactiveSecurityContextHolder` on top of Reactor `Context` so the principal follows the pipeline; business code must still compose publishers properly, handle absent context, and enforce authorization at protected boundaries.

## References

- [Project Reactor — Adding a Context to a Reactive Sequence](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/advancedFeatures/context.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/site/docs/6.2.x/api/org/springframework/security/web/server/context/ReactorContextWebFilter.html)
