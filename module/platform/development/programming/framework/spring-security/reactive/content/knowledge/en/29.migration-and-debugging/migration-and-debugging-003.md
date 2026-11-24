# Replacing SecurityContextHolder and ThreadLocal with ReactiveSecurityContextHolder in Spring Security WebFlux

## 1. Migration Goals and Context

When migrating a Spring Security application from Servlet/Spring MVC to WebFlux (Reactive), reading the logged-in user via `SecurityContextHolder.getContext().getAuthentication()` inside a service is generally no longer reliable. The reason: the reactive model does not pin the entire handling of a request to a fixed thread. Steps in a `Mono`/`Flux` chain can execute on different threads; the same event-loop thread can also serve many requests.

This lesson explains how to switch to **`ReactiveSecurityContextHolder`**, understand how `Authentication` lives inside the **per-subscriber Reactor Context**, update APIs/services to return `Mono`/`Flux`, preserve context across reactive operators, verify behavior with `StepVerifier`, and handle boundaries where context can be lost.

After studying this, you will be able to:
- Distinguish between `SecurityContextHolder` (typically ThreadLocal-based in imperative flows) and `ReactiveSecurityContextHolder` (Reactor Context-based).
- Read `SecurityContext`/`Authentication` properly at subscription time, rather than eagerly during chain assembly.
- Use `getContext()`, `withAuthentication()`, `withSecurityContext()`, and `clearContext()` for their intended purposes.
- Migrate services, WebFlux handlers, and security-annotated methods without arbitrary `block()`/`subscribe()` calls.
- Diagnose `principal=null`, unexpected `401/403` responses, cross-request context leakage, or context loss when calling non-Reactor async libraries.

**Scope:** Spring Security for WebFlux/reactive, Java 17+, Project Reactor. Snippets belong to a Maven/Gradle application with `spring-boot-starter-webflux` and `spring-boot-starter-security` (plus `reactor-test` and JUnit Jupiter for testing). Code examples are classes or snippets meant for an appropriate Spring project, not standalone programs compiled solely with `javac` on the JDK.

## 2. Core Difference: Data Tied to a Thread or to a Subscriber?

### The Previous Imperative Style

In Servlet applications, Spring Security typically prepares `SecurityContextHolder` on the thread processing the request. Familiar code:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
~~~

Inside synchronous execution belonging to a standard Servlet Security chain, this read is usually valid. When moving that code as-is to WebFlux, however, typical failure modes appear:
- While assembling the `Mono`, the request's security context does not exist yet or has not been populated on the current thread.
- A processing step executes on another thread after `subscribeOn`/`publishOn` or an I/O event.
- Event-loop threads are continuously reused across independent requests.
- A callback, `CompletableFuture`, or `@Async` call spawns execution outside the current subscription.

ThreadLocal stores data per thread and does not automatically follow a reactive subscription. Manually calling `SecurityContextHolder.setContext(...)` at the start of a request can also leak data between users if lifecycle and clearing are wrong or threads are reused.

### The Correct Reactive Style

`ReactiveSecurityContextHolder` stores a `Mono<SecurityContext>` in the Reactor Context, a context structure attached to a **Subscriber**. Spring Security WebFlux places the security context onto the subscriber when processing through the appropriate filter chain. Reading code:

~~~java
Mono<Authentication> currentAuthentication =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()));
~~~

The `Authentication` value is read only when the `Mono` is subscribed under the current request's context. If no context or authentication is present, the publisher may complete empty. Never assume every request has an authenticated user.

| Criterion | Servlet/imperative | WebFlux/reactive |
| --- | --- | --- |
| Security context source | `SecurityContextHolder`, typically ThreadLocal strategy | `ReactiveSecurityContextHolder` via Reactor Context |
| Primary scope | Executing thread | Subscriber and operator chain |
| Reading info | Synchronous: `Authentication` or `null` | Asynchronous: `Mono<SecurityContext>`, `Mono<Authentication>` |
| Scheduler switches | ThreadLocal is not guaranteed to carry values | Context propagates through standard Reactor operators in the same subscription |
| Integration point | Servlet `FilterChain` | `SecurityWebFilterChain` and Spring Security WebFlux context handling |
| Common mistake | Forgetting to clear ThreadLocal when managing manually | Mid-chain `block()`/`subscribe()`, caching principal, losing context at non-Reactor APIs |

**Key takeaway:** Reactor Context is a per-subscription mechanism, not a ThreadLocal clone and not a global variable. Having an authentication in the context also does not mean an operation is **authorized**; authorization must still be enforced by `SecurityWebFilterChain`, method security, or explicitly designed checks.

## 3. Identifying Exact Bugs in Legacy Code

### Bug 1: Returning a Synchronous String from a Service

~~~java
// Imperative pattern unsuitable when called from WebFlux:
public String currentUsername() {
    return SecurityContextHolder.getContext()
            .getAuthentication().getName();
}
~~~

In WebFlux, `getAuthentication()` may be null, or the code may accidentally observe a context not belonging to the current subscription. The fix is not merely adding a null check; the contract must change to `Mono<String>`.

### Bug 2: Reading SecurityContextHolder Before Creating a Mono

~~~java
// Wrong-scoped code: invoked immediately when the method runs.
public Mono<String> username() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    return Mono.just(auth.getName());
}
~~~

`Mono.just(...)` evaluates its argument at publisher assembly time, unlike reading Reactive Context at subscription time. Replacing `Mono.just(...)` with `Mono.defer(...)` while **still reading ThreadLocal** does not fix the root cause either: execution may run on a thread lacking the right `SecurityContextHolder`.

### Bug 3: Storing Authentication in an Instance/Singleton Field

~~~java
// Never store a request's principal in a field of a singleton @Service.
private Authentication currentAuthentication;
~~~

Requests can execute concurrently; a shared field lets request A read request B's data. Never use a static field or global `Map` as a vehicle for holding the "current user" either.

### Bug 4: Subscribing Manually and Returning Something Else

~~~java
// Detached subscription: never do this in a handler to read the principal.
ReactiveSecurityContextHolder.getContext()
        .subscribe(context -> doSomething(context.getAuthentication()));
return Mono.empty();
~~~

`subscribe()` creates a separate subscription, typically detached from the request's security context and lifecycle; errors are no longer propagated through the handler. Replace it with `flatMap`/`map` inside the chain returned to WebFlux.

## 4. Four Key APIs of ReactiveSecurityContextHolder

The class `org.springframework.security.core.context.ReactiveSecurityContextHolder` provides:

| API | Return type | Purpose |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Reads the context from Reactor Context at subscription time; may complete empty. |
| `withAuthentication(authentication)` | `reactor.util.context.Context` | Creates a Reactor Context entry from a properly authenticated/established `Authentication`. |
| `withSecurityContext(monoSecurityContext)` | `reactor.util.context.Context` | Places a `Mono<? extends SecurityContext>` publisher into Reactor Context. |
| `clearContext()` | `Function<Context,Context>` | Removes the reactive security context entry within the **chain scope** using `contextWrite`. |

Example setting authentication for **a controlled subscription**, commonly used in tests:

~~~java
Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice", null, AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");

Mono<String> testFlow = username.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

When subscribing to `testFlow`, the result is `"alice"`. When subscribing directly to `username` in an environment with no security context, the result is `"anonymous"`. This example assumes Spring Security/Reactor classes are already imported in the project. **Never** use `withAuthentication()` to mark a client-supplied username as "logged in"; `Authentication` must originate from a valid authentication step.

For a publisher that already holds an established `SecurityContext` from an authentication mechanism:

~~~java
Mono<SecurityContext> verifiedContext = obtainVerifiedSecurityContext();

return securedWork().contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(verifiedContext));
~~~

This is illustrative structural code, not a standalone snippet: `obtainVerifiedSecurityContext()` must perform real authentication, `securedWork()` must return a `Publisher`, and error/cancellation handling must be designed properly. In normal applications, **Spring Security automatically populates the context in the pipeline**; do not manually inject context in every service.

When intentionally clearing access within a specific segment:

~~~java
Mono<String> withoutSecurityContext = currentUserService.currentUsername()
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

That segment does not see the upstream security context. `clearContext()` only affects that reactive chain scope; it is **not equivalent to logout**, does not revoke a JWT, does not invalidate a session, and does not clear a `SecurityContextRepository`. Logout must use proper logout mechanisms, session/token invalidation, and storage policies.

## 5. Complete Service Example: Reading Username per Subscriber

Here is a Java 17+ class placed in `src/main/java/example/security/CurrentUserService.java` of a Spring Boot WebFlux application:

~~~java
package example.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentUserService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx ->
                        Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(this::isRealAuthenticatedUser)
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AuthenticationCredentialsNotFoundException(
                                "Authentication required")));
    }

    private boolean isRealAuthenticatedUser(Authentication authentication) {
        return authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Key points to understand:
1. **Return type `Mono<String>`**: controllers/services calling from a reactive pipeline receive the result at subscription time without demanding an immediate `String`.
2. **`Mono.justOrEmpty(ctx.getAuthentication())`**: a `SecurityContext` may exist while `getAuthentication()` returns `null`; calling `map(SecurityContext::getAuthentication)` directly on a `null` value violates the Reactive Streams contract. `justOrEmpty` handles `null` cleanly as empty.
3. **Do not check `isAuthenticated()` alone**: Spring Security's `AnonymousAuthenticationToken` can return `true`, so anonymous users must be filtered out according to policy. Depending on custom configurations, evaluate other `Authentication` subtypes as well.
4. **`switchIfEmpty`**: do not turn an unauthenticated user into an empty string or `"guest"` inside a service that requires authentication. The exception can be translated by the security/web layer into an appropriate HTTP status; confirm how exceptions map to responses with your application's integration tests.
5. **`getName()` is identification, not authorization**: an endpoint reading or modifying data must enforce proper security rules and ownership checks, never granting access solely because a username is present.

If business logic only needs a stable account ID, define a typed principal or application identity after authentication rather than relying indefinitely on the `Authentication.getName()` string. Avoid casting the principal to a custom user or `Jwt` if the application supports multiple authentication mechanisms; check types or use an appropriate adapter.

## 6. Calling the Service from a WebFlux Controller

Example class `src/main/java/example/security/MeController.java`:

~~~java
package example.security;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class MeController {
    private final CurrentUserService currentUserService;

    public MeController(CurrentUserService currentUserService) {
        this.currentUserService = currentUserService;
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return currentUserService.currentUsername()
                .map(name -> Map.of("username", name));
    }
}
~~~

When a request passes through `SecurityWebFilterChain` and succeeds authentication, Spring WebFlux subscribes to the returned publisher; `currentUsername()` reads that request's context.

The route-protection configuration below is a **class snippet you can place in an application configured with an appropriate authentication mechanism**:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

`httpBasic()` is only an illustrative authentication mechanism; production must use an appropriate mechanism (OAuth2 Resource Server/JWT, OAuth2 login, sessions, mTLS, etc.) with HTTPS, proper credential storage, and an appropriate CSRF policy. Do not disable CSRF mechanically if the system serves browsers and uses cookies/sessions or HTTP Basic. Do not implement a custom `WebFilter` to inject `Authentication` on every request when Spring Security already provides `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `ServerSecurityContextRepository`.

The logical outcome for an authenticated account named `alice` is JSON containing username `"alice"`. Unauthenticated requests must be rejected per configuration (typically `401` with HTTP Basic); authenticated requests lacking permission for another endpoint may receive `403`. Exact response codes depend on the application's entry point and `SecurityWebFilterChain`.

## 7. Why contextWrite Placed Downstream Affects Upstream Operators

In Reactor, Context flows **from the Subscriber (bottom of the pipeline) upward to upstream operators** at subscription time. `contextWrite` establishes context for operators located **above** it, rather than mutating a global thread-local.

Example:

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .flatMap(c -> Mono.justOrEmpty(c.getAuthentication()))
        .map(Authentication::getName)
        .defaultIfEmpty("guest");

Mono<String> scoped = who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

If `alice` is an authenticated `Authentication`, `scoped` emits `"alice"`. However, a context read placed **after** a `contextWrite` in an outer pipeline will not necessarily receive that entry:

~~~java
Mono<String> onlyUpstream = who
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))
        .then(who);
~~~

In this example, the first `who` is subscribed with `alice`'s context, whereas the `who` passed as the argument to `then` is subscribed in the downstream context of `then`, where `withAuthentication` was not applied. Without another context, the final result will be `"guest"`. What matters is not "top-to-bottom line order" in Java source code, but the operator's position in the **subscription graph**.

How to fix it when the entire pipeline needs the same context:

~~~java
Mono<String> entireFlow = firstStep()
        .then(who)
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

`firstStep()` is an application publisher (hypothetical); only an authentication from a valid authentication result should be propagated. In normal requests, `SecurityWebFilterChain` handles setting up the context; business code only reads it.

One more important detail: `contextWrite` on one `Mono` branch does not by default spread to an independent branch subscribed separately. Reusing the same `Mono` variable is safe as long as it remains **cold** and does not cache per-user results; each subscriber sees its own context.

## 8. Preserving Reactor Context Across Scheduler Thread Switches

Reactor allows switching threads via `publishOn` and `subscribeOn`. Because Context follows the subscription, standard Reactor operators see the context after a thread switch:

~~~java
Mono<String> result = Mono.delay(Duration.ofMillis(10))
        .publishOn(Schedulers.boundedElastic())
        .then(currentUserService.currentUsername());
~~~

For a request already authenticated by Spring Security with the subscription preserved, `currentUsername()` still retrieves the right `Authentication`. Relevant packages are `java.time.Duration`, `reactor.core.publisher.Mono`, and `reactor.core.scheduler.Schedulers`.

Crucially: Context is per-subscriber data; **not every ThreadLocal is automatically propagated across schedulers**. The following example is unreliable in WebFlux:

~~~java
Mono<String> unsafe = Mono.fromCallable(() ->
        SecurityContextHolder.getContext().getAuthentication().getName())
        .subscribeOn(Schedulers.boundedElastic());
~~~

The `Callable` runs on a worker thread; `SecurityContextHolder` may be empty or reflect stale/unrelated data. Adding `publishOn`, `subscribeOn`, or `defer` does not turn `SecurityContextHolder` into a reactive API.

When forced to invoke a blocking library, run the blocking I/O on `boundedElastic` (or a designed isolation pool) and **explicitly pass the permitted business data**:

~~~java
public Mono<String> auditCurrentUser() {
    return currentUserService.currentUsername()
            .flatMap(username ->
                    Mono.fromCallable(() ->
                            blockingAuditClient.recordUserAction(username))
                        .subscribeOn(Schedulers.boundedElastic()));
}
~~~

This method snippet depends on an application `blockingAuditClient`; the return type assumes `recordUserAction` returns a `String`. The code does not pass `SecurityContextHolder` across threads; `username` is read from context inside the pipeline before invoking the blocking system. Avoid forwarding raw credentials, JWTs, or the full `SecurityContext` where only an actor identifier is needed. Permission to write audit records must still be enforced at the appropriate layer.

## 9. Boundaries That Lose Context: subscribe, Future, @Async, and Message Queues

### Calling subscribe() Inside a Service

~~~java
// Avoid detaching work from the request:
someMono.subscribe();
return Mono.just("accepted");
~~~

The new subscription may lack Context and is not awaited or authorized by WebFlux, and errors are handled separately. Replace with:

~~~java
return someMono.thenReturn("accepted");
~~~

In the returned chain, WebFlux subscribes once with the proper lifecycle.

### CompletableFuture and Manual Threads

Reactor Context does not automatically cross a new `Thread`, `CompletableFuture.supplyAsync`, callbacks of non-Reactor SDKs, or `@Async` methods. When crossing to a non-Reactor API, pick one of two deliberate approaches:
- **Prefer** extracting the minimal permitted data and passing it explicitly into the external call (such as validated `actorId` or `tenantId`). Enforce authorization checks where required.
- If propagation is needed for observability or legacy frameworks via Micrometer Context Propagation, use library-supported adapters and configuration; never rely on ThreadLocal or `SecurityContextHolder` magically holding the principal.

Never sneak `SecurityContextHolder.setContext(...)` onto a shared executor and forget to clear it. If a library strictly requires ThreadLocal, bridging to it needs `try`/`finally` scoping, isolation, concurrent-request testing, and official framework support. That is a controlled compatibility measure, not a default pattern for new code.

### Message Queues and Background Jobs

A message processed after an HTTP request has ended is an independent unit of work and does not inherit the old request's `Authentication`. When actor auditing is required, include a verified actor identifier, minimal permissions, or a business command in the message per an approved contract. The worker must authenticate/authorize according to its own policy—never put an entire `SecurityContext` or bearer token onto a queue just to "restore" thread context.

### Special Publisher Sources

Hot publishers, `share`/`cache`, global sinks, or callbacks emitting signals from outside Reactor can alter subscription sites and value sharing. Never store or cache a publisher that already resolved `Authentication` across multiple requests. **Each caller needs its identity inside its own subscriber context**, and authorization must be checked per request.

## 10. Dangers of Caching or Sharing User Data

`Mono.cache()` turns a publisher into one that replays its result to subsequent subscribers. If caching is applied to the username or per-user permissions in a singleton service, subscriber B can receive subscriber A's result:

~~~java
// Wrong: singleton field stores the value of the first subscriber.
private final Mono<String> cachedUser =
        currentUserService.currentUsername().cache();
~~~

Even though the original `currentUsername()` reads the context properly at subscription time, once cached it returns the stored result. No amount of context propagation fixes **data cached at the wrong scope**.

Replace with:

~~~java
// Each request invokes a cold publisher under its own context.
public Mono<String> handle() {
    return currentUserService.currentUsername()
            .flatMap(this::processForCurrentUser);
}
~~~

`processForCurrentUser(String)` is an application business method returning `Mono<String>`. When business data genuinely needs caching, key-partition it by authenticated tenant/user and enforce authorization, cache TTL, and invalidation—never cache the current principal as a singleton.

Avoid mutating a `SecurityContext` or `Authentication` and reusing the same instance across concurrent subscriptions. `withAuthentication()` does not make an object immutable or guarantee isolation if the same instance is shared and mutated.

## 11. Role of SecurityWebFilterChain and ReactiveSecurityContextHolder

In WebFlux, Spring Security uses `SecurityWebFilterChain` and `WebFilter` instances to handle authentication, authorization, and context. When a `SecurityContextRepository` or bearer authentication mechanism validates credentials, the framework supplies the context downstream via Reactor.

Typical cases:
- **HTTP Basic:** credentials are verified by the appropriate authentication manager/provider; controllers/services read via `ReactiveSecurityContextHolder`.
- **OAuth2 Resource Server with JWT:** the bearer filter verifies signature, `exp`/`nbf`, and issuer/audience (per configuration), then sets the authenticated `Authentication`. Services simply read the context rather than decoding the token a second time to guess the caller.
- **Session/form login:** the repository saves or loads context per session; within reactive requests, still read via `ReactiveSecurityContextHolder`.
- **`permitAll` requests:** authorization requires no identity; `getContext()` may have no `Authentication` or hold an anonymous token. Never assume `permitAll` implies "logged in".

Never call `ReactiveSecurityContextHolder.withAuthentication(new UsernamePasswordAuthenticationToken(...))` based on an unverified header or query-string ID. That skips authentication and enables privilege escalation. When migrating a custom authentication filter from Servlet:
1. Separate **reading credentials** from **verifying credentials** (`ReactiveAuthenticationManager` or supported mechanism).
2. Use `AuthenticationWebFilter` and `ServerSecurityContextRepository` where appropriate instead of manually managing context in arbitrary callbacks.
3. Place the filter at the proper order in `SecurityWebFilterChain`, defining entry points and error responses.
4. Test valid, invalid, missing, and expired credential cases; do not test reading `ReactiveSecurityContextHolder` alone.
5. Never log credentials or raw `Authorization` headers while debugging propagation.

## 12. Migrating SecurityContextHolder Across Application Layers

### Controller/Handler

**Before:** Calling a service that synchronously returns a `String` username.

**After:** Return `Mono`/`Flux` or use WebFlux-supported principal parameters. The example in Section 6 returns `Mono<Map<String,String>>`. In WebFlux handlers, `ServerWebExchange.getPrincipal()` also returns `Mono<Principal>` and can be used when the principal is only needed at the HTTP layer. When logic is shared across layers, `ReactiveSecurityContextHolder` and a domain identity model are usually preferable.

### Services Using Authentication

**Before:**

~~~java
String owner = SecurityContextHolder.getContext()
        .getAuthentication().getName();
return repository.findByOwner(owner);
~~~

**After:** Assuming `repository.findByOwner(String)` returns `Mono<Order>`:

~~~java
return currentUserService.currentUsername()
        .flatMap(repository::findByOwner);
~~~

This illustrates a method returning `Mono<Order>`. Avoid reading `owner` from the request body instead of the auth context when data must be restricted to the logged-in user. Ownership/authorization checks are still required when looking up by a request-supplied ID.

### Multi-Step Services

~~~java
return currentUserService.currentUsername()
        .flatMap(user -> accountRepository.findByOwner(user))
        .flatMap(account -> paymentService.readStatus(account.id()));
~~~

`accountRepository.findByOwner(...)` and `paymentService.readStatus(...)` are hypothetical reactive domain APIs; return types and error handling must stay consistent in the implementation. Passing an explicit actor or ID between layers often makes code easier to test and audit for authorization than having every helper implicitly read the security context.

### Library Code Unaware of Spring Security

Do not force domain/DAO libraries to depend directly on `ReactiveSecurityContextHolder` just to discover the current user. At the application/service boundary, extract the verified identity and pass a typed `Actor`, `TenantId`, or explicit parameter into domain logic. This reduces framework coupling and simplifies tests.

## 13. Reactive Authorization with Method Security

If using authorization annotations at the service layer, enable **reactive method security** rather than copying Servlet `@EnableMethodSecurity` verbatim while ignoring the Publisher model.

~~~java
package example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Example inside a Spring-managed service returning `Mono<String>`:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<String> readOrderStatus(String orderId) {
    return orderRepository.findStatus(orderId);
}
~~~

This is an illustrative method snippet; `orderRepository` must be declared and return `Mono<String>`, and compiling requires importing `org.springframework.security.access.prepost.PreAuthorize`. Reactor-Context method security is applied via proxies/interceptors on Spring-managed bean calls; self-invocation within the same instance normally bypasses the proxy. `hasAuthority` rules must match the exact authorities produced by the real JWT/role setup, such as `SCOPE_orders.read` in Resource Server with the appropriate default converter. Other mechanisms may use different policies and prefixes.

Spring Security expects reactive publishers so the framework can attach authorization checks with Reactor Context. Do not change return types to `String` via `block()` just to keep imperative annotations. Nor should checking `Authentication.isAuthenticated()` inside a service be treated as sufficient authorization for reading or modifying a resource.

## 14. Unit Testing with Reactor Test: Missing, Present, and Isolated Contexts

Create `src/test/java/example/security/CurrentUserServiceTest.java`; compatible versions of JUnit Jupiter and `reactor-test` are required. These tests exercise `CurrentUserService` logic directly without starting a web server:

~~~java
package example.security;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class CurrentUserServiceTest {
    private final CurrentUserService service = new CurrentUserService();

    private static Authentication auth(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, null, AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    @Test
    void missingContextIsRejected() {
        StepVerifier.create(service.currentUsername())
                .expectError(AuthenticationCredentialsNotFoundException.class)
                .verify();
    }

    @Test
    void readsAuthenticationFromSubscriber() {
        StepVerifier.create(service.currentUsername()
                        .contextWrite(ReactiveSecurityContextHolder
                                .withAuthentication(auth("alice"))))
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void keepsContextAcrossSchedulerChange() {
        Mono<String> flow = Mono.delay(Duration.ofMillis(10))
                .publishOn(Schedulers.boundedElastic())
                .then(service.currentUsername())
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("alice")));

        StepVerifier.create(flow)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void concurrentSubscribersDoNotShareAuthentication() {
        Mono<String> sharedColdSource = service.currentUsername();

        Mono<String> alice = Mono.delay(Duration.ofMillis(20))
                .then(sharedColdSource)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("alice")));

        Mono<String> bob = Mono.delay(Duration.ofMillis(5))
                .then(sharedColdSource)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("bob")));

        StepVerifier.create(Flux.merge(alice, bob).collectSortedList())
                .expectNext(List.of("alice", "bob"))
                .verifyComplete();
    }
}
~~~

**Test expectations:**
- Missing context: publisher terminates with `AuthenticationCredentialsNotFoundException`.
- Context `alice`: emits `"alice"`.
- After scheduler switch: still emits `"alice"`, not `null`.
- Two overlapping subscriptions: returns sorted list `["alice", "bob"]` with no context leakage.

Run commands in a project with the matching wrapper and dependencies:

~~~bash
./mvnw -Dtest=CurrentUserServiceTest test
~~~

Or with Gradle (a fully qualified name may be needed if multiple classes share the name):

~~~bash
./gradlew test --tests example.security.CurrentUserServiceTest
~~~

On Windows, use `mvnw.cmd` or `gradlew.bat`. Tests do not assert exact Maven/Gradle stdout text because console output varies by runner, version, plugins, and other tests; the pass criterion is all four tests succeeding. These are logic regression tests and **do not yet prove** that `SecurityWebFilterChain` works properly over HTTP.

### WebFlux Integration Testing

With `spring-security-test` and `WebTestClient`, you can simulate a user at the filter chain without manually mutating ThreadLocal. Snippet for a test class already configured with Spring Security-integrated `WebTestClient`:

~~~java
webTestClient
        .mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.username").isEqualTo("alice");
~~~

Requires `import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser`. When writing real tests, wire the proper context, client, and controller; add tests verifying unauthenticated requests get `401`, insufficient roles get `403` on protected endpoints, and two concurrent requests with different identities never mix principals. Never use `@WithMockUser` or `mockUser` as a production authentication mechanism.

## 15. Debugging Procedure When getContext() Is Empty

If new code still sees no `Authentication`, walk through this sequence:

1. **Did the request hit the right `SecurityWebFilterChain`?** Verify URL, matchers, chain order, and the actual running web application type. Do not infer this merely from `spring-security-web` being on the classpath.
2. **Was the request actually authenticated?** Check `401`/`403` on protected endpoints, `AuthenticationWebFilter`/Resource Server config, issuer, audience, session, and entry point. Under `permitAll`, having no user is expected.
3. **Is context read at subscription time or assembly time?** Never read it in static initializers, singleton constructors, `@PostConstruct`, or before WebFlux subscribes.
4. **Is there a `subscribe()`/`block()` or separate `Future` in a helper?** Trace the chain where the subscription detaches, not only at the `getContext()` call site.
5. **Is a `cache`/`share`/hot publisher holding a principal?** Check singleton fields, `.cache()`, `.share()`, shared `Sinks`/Subjects, and per-user memoization.
6. **Is there a `contextWrite(clearContext())` or broken Context replacement?** Check upstream/downstream scope and whether code uses `contextWrite(ctx -> Context.empty())`, wiping all entries.
7. **Are there non-Reactor gateways/SDKs/services?** Inspect reactive adapters, callbacks, `@Async`, and message handlers. Independent flows need explicit actor contracts or fresh authentication.
8. **Are you checking anonymous properly?** `isAuthenticated()` alone does not exclude `AnonymousAuthenticationToken`.
9. **Did a legacy helper confuse `SecurityContextHolder` with `ReactiveSecurityContextHolder`?** Search for `getContext()`, `setContext()`, `clearContext()`, `ThreadLocal`, and `MDC` across the migrated codebase.
10. **Authenticated yet still `403`?** Check authorities, `ROLE_` / `SCOPE_` prefixes, method security, claim mapping, and tenancy/ownership; context existence does not prove authorization.

When logging to debug, log only events, safe correlation IDs, route templates, authenticated/anonymous status, and normalized exception types. **Never print `Authentication.toString()`, principal objects, credentials, `Authorization` headers, cookies, JWTs, or `SecurityContext`**; logging full objects can expose personal data and tokens.

## 16. Why Micrometer Context Propagation Does Not Replace Reactive APIs

Reactor supports `io.micrometer:context-propagation` to capture and restore selected ThreadLocal states across Context. There is a default mode and an automatic mode via `Hooks.enableAutomaticContextPropagation()` (depending on Reactor version and configuration). This is useful for trace IDs/MDC or legacy libraries requiring ThreadLocal.

However:
- **The canonical source of security context in WebFlux remains Reactor Context** via `ReactiveSecurityContextHolder`. Do not design new code assuming `SecurityContextHolder` happens to be synchronized into ThreadLocal.
- Automatic mode has scope limits, `ThreadLocalAccessor` registration requirements, and performance overhead. Enabling it after subscriptions already exist does not guarantee fixing older flows.
- A callback outside a reactive chain does not automatically inherit context just because Micrometer is enabled; proper capture/adapters per documentation are required.
- Never put full `Authentication`/JWTs into MDC, tracing baggage, or logs. When audit requires an identity, prefer minimal verified identifiers.
- Avoid patching framework ThreadLocals inside scattered `try`/`catch` blocks; if bridging a library is mandatory, enforce reset/cleanup so shared threads never leak data.

Reactor Context is the mechanism for per-subscription data; Micrometer can partially bridge it to ThreadLocal when explicitly needed. The two tools serve different purposes.

## 17. Migration Strategy for Multi-Service Codebases

**Step 1 — Locate ThreadLocal dependencies.** Search for calls to `SecurityContextHolder.getContext()`, `setContext()`, `clearContext()`, `MODE_INHERITABLETHREADLOCAL`, custom `ThreadLocal`, MDC containing `userId`, `RestTemplate` interceptors, `@Async`, and `CompletableFuture`. Pay special attention to services called from reactive controllers that still synchronously return data derived from the current user.

**Step 2 — Categorize changes.** HTTP-boundary logic can use the WebFlux-provided principal; reactive services need a current-user abstraction returning `Mono<Actor>`; domain/repositories are better served receiving explicit `Actor` or `ownerId` parameters. Background tasks need their own identity/authorization contract instead of trying to inherit a user thread context.

**Step 3 — Convert synchronous contracts to Publishers.** For example, `String currentUsername()` → `Mono<String> currentUsername()`. Refactor callers using `map`/`flatMap`; never call `block()` on the event loop to "keep the old signature". If using blocking APIs, wrap them via a `boundedElastic` adapter or migrate to reactive APIs.

**Step 4 — Place authentication in the right framework layer.** Use `SecurityWebFilterChain`, WebFlux Security, `AuthenticationWebFilter`/`ReactiveAuthenticationManager`, or OAuth2 Resource Server. Never write ad-hoc filters that inject `Authentication` from unverified input.

**Step 5 — Define policy when context is absent.** Public endpoints may have no user. Private endpoints should require authentication with consistent error semantics; `"guest"` fallbacks belong only to logic intentionally allowing anonymous access. Never swallow exceptions and fall back to a privileged default account.

**Step 6 — Protect authorization paths.** Add reactive method security where needed and check `hasRole`/`hasAuthority`, ownership, and tenant matching. Ensure every path accessing sensitive data enforces authorization.

**Step 7 — Test concurrency and error paths.** Run concurrent requests across schedulers, valid/expired tokens, missing context, cancelled subscriptions, retries, timeouts, and non-Reactor calls. Confirm identity never bleeds from request A to request B.

**Step 8 — Remove legacy paths and monitor for regressions.** Once all callers are migrated, remove `SecurityContextHolder`/`ThreadLocal` helpers used for WebFlux principal lookup. Watch for spikes in `401`/`403`, missing-principal errors, `5xx` responses, and latency shifts.

Avoid rewriting an entire application in one huge commit before authentication/authorization tests exist; migrate controller by controller or service by service, keep HTTP outputs stable, and run regression tests at every step.

## 18. Subtle Traps

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `getAuthentication()` is null in a reactive handler | Reading `SecurityContextHolder` on a thread not bound to the request | Use `ReactiveSecurityContextHolder.getContext()` inside `Mono`/`Flux`; verify chain |
| App works locally on dev machine, fails under load | Reused threads, race conditions, singleton field holding principal | Remove ThreadLocal/global state and test concurrent subscribers |
| "User disappears" after `publishOn` | Helper still reads ThreadLocal or detached subscription | Read Reactor Context; keep publishers chained together |
| Test has auth, yet HTTP returns `401` | Test only used `withAuthentication` on a `Mono`, bypassing WebFlux filter chain | Add `WebTestClient` integration tests with `spring-security-test` |
| `@PreAuthorize` does not work as expected | Reactive method security not enabled, self-invocation, or wrong return type | Enable `@EnableReactiveMethodSecurity` and test calls through the Spring proxy |
| Service sees `"anonymous"` yet `isAuthenticated()=true` | `AnonymousAuthenticationToken` is marked authenticated | Check token type and apply appropriate rules |
| User A's data appears for user B | `Mono.cache`/`share` or singleton field storing identity | Remove context-dependent caching and isolate per subscriber |
| Creating a new Context wipes tracing/security | `contextWrite(ctx -> Context.empty())` or mis-scoped `clearContext` | Preserve existing entries and modify only intended keys |
| Token still works after logout | Confusing `clearContext` with logout/session invalidation | Implement session/token invalidation per your authentication model |
| `WebClient` callback loses context | External library call / `Future` / detached `subscribe` | Use Reactor operators or pass actor explicitly, re-authenticating where needed |

## 19. Pre-Production Checklist

- [ ] In WebFlux flows, there are no remaining dependencies on `SecurityContextHolder`/ThreadLocal to read the current user.
- [ ] `SecurityContext`/`Authentication` is retrieved lazily via `ReactiveSecurityContextHolder`, handling missing auth cases.
- [ ] No singleton/static fields or `Mono.cache()`/`share()` hold per-request `Authentication`.
- [ ] No `block()`/`subscribe()` is used in controllers/services to force principal values to be synchronous.
- [ ] `SecurityWebFilterChain` and framework authentication mechanisms are wired properly; `Authentication` is never populated from unverified client input.
- [ ] Method security uses `@EnableReactiveMethodSecurity` and appropriate reactive `Publisher` return types.
- [ ] Publishers preserve context across `publishOn`/`subscribeOn`; non-Reactor boundaries are handled explicitly.
- [ ] `StepVerifier` tests cover absent context, authenticated context, scheduler switches, and concurrent subscribers.
- [ ] `WebTestClient` tests verify `401`, `403`, and correct per-user/per-role data for real requests.
- [ ] Logs/tracing/MDC contain no credentials, tokens, full `SecurityContext`, or out-of-policy personal data.
- [ ] Background tasks/queues have their own auth model; `clearContext` is never treated as logout.
- [ ] Security tests run in CI after Spring Security, Reactor, and context-propagation upgrades.

## 20. Official Documentation for API Reference

1. [ReactiveSecurityContextHolder Java API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html) — `getContext`, `withAuthentication`, `withSecurityContext`, and `clearContext`.
2. [Spring Security Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — reactive method authorization backed by Reactor Context; `StepVerifier` examples.
3. [Spring Security Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain` and WebFlux configuration.
4. [Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — `contextWrite`, `ContextView`, and per-subscriber propagation direction.
5. [Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html) — Micrometer bridge with ThreadLocal, default/automatic modes.
6. [Spring Security Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html) — Spring Security Test and `WebTestClient`.

**Remember:** In WebFlux, the current user belongs to the **subscription**, not the thread. Read via `ReactiveSecurityContextHolder.getContext()`, continue processing through `Mono`/`Flux`, let `SecurityWebFilterChain` populate the context, and enforce proper authorization. Keep identities isolated across subscribers, never cache a shared principal, and never assume a ThreadLocal will follow reactive execution steps.
