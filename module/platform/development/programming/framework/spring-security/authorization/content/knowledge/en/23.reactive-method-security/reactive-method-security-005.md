# Placing Identity into Reactor Context and Avoiding ThreadLocal Dependencies in Reactive Method Security

## 1. The Problem: One Pipeline, Multiple Threads, Multiple Users

In traditional Spring MVC/Servlet applications, code typically retrieves the current user like this:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
```

This feels familiar because each request is normally processed along a single thread-bound call chain; `SecurityContextHolder` defaults to a `ThreadLocal` context storage strategy. However, Spring WebFlux and Reactor do not guarantee an entire request runs on a single thread. A `Mono`/`Flux` can:

- be assembled (*assembly*) on thread A;
- begin executing when a subscriber subscribes (*subscribe*) on thread B;
- invoke an asynchronous I/O API and resume on thread C;
- switch schedulers via `publishOn` or `subscribeOn`;
- handle multiple distinct subscriptions from the same publisher.

If a reactive service calls `SecurityContextHolder.getContext()` inside a callback, it may encounter an **empty** context or a context **not belonging to the active subscriber**, depending on the pipeline and context propagation setup. An even severer risk arises when an application defines a custom `static ThreadLocal<String> CURRENT_USER`, forgets `remove()`, or runs on a thread pool; one request can accidentally inherit another request's user or tenant.

In Reactive Method Security, the standard approach uses **Reactor `Context`** and **`ReactiveSecurityContextHolder`**. The `Authentication` object is read from the **subscription's** context, rather than assuming identity stays pinned to the currently executing thread.

This Knowledge lesson belongs to the **Reactive Method Security** topic of the **Spring Security – Authorization** module. It focuses on **placing identity into the Reactor Context and avoiding ThreadLocal dependencies**: setting/reading identity, context propagation, its relationship to `@PreAuthorize`, testing, and practical pitfalls across async boundaries.

By the end of this lesson, you will know:

1. Why `ThreadLocal` is not a reliable identity source in a reactive chain.
2. How `Context`, `ContextView`, `contextWrite`, and `deferContextual` behave by subscription and direction.
3. How to read `SecurityContext` via `ReactiveSecurityContextHolder.getContext()`.
4. How to attach identity in **tests or trusted internal boundaries** using `withAuthentication`/`withSecurityContext`.
5. How WebFlux Security populates the Reactor security context after authenticating a request.
6. How to use `@EnableReactiveMethodSecurity` and `@PreAuthorize` with `Mono`/`Flux`.
7. How to protect tenant/owner/ACL boundaries with the principal and authoritative data.
8. How to avoid context loss across `publishOn`, `subscribeOn`, `@Async`, `CompletableFuture`, detached `subscribe()`, and background jobs.
9. How to write a runnable Java 17 + Spring Boot 3.5.8 project featuring a CLI demo, `StepVerifier`, and HTTP `WebTestClient` tests.
10. How to test **the same publisher under two identities**, preventing cross-tenant leaks and stopping source execution on denial.
11. Why `Mono.cache()`, hot publishers, retries, and permission revocation require dedicated design.
12. How to distinguish **identity** context from an **authorization** decision that may already be stale.

**Core principle:** Identity must be built from verified authentication and carried along the **correct subscription**, while data permissions must continue to be enforced at the repository/service/transaction layers. Reactor Context **does not** grant permissions by itself.

---

## 2. Comparing ThreadLocal and Reactor Context

| Criterion | `ThreadLocal` | Reactor `Context` |
| --- | --- | --- |
| Bound to | A Java thread | A subscriber/subscription and operator chain |
| Access | `threadLocal.get()` | `deferContextual`, `contextWrite`, and Context-aware APIs |
| Across `publishOn` / `subscribeOn` | Not guaranteed to carry over to the new thread | Reactor Context continues along the reactive chain |
| Multiple requests sharing a thread | Can bleed across requests if mismanaged | Context is isolated per subscription |
| Ownership / lifecycle | Must set/remove reliably on every path/thread | Tied to subscriber, immutable per update |
| Reading Spring Security auth | `SecurityContextHolder` (imperative default) | `ReactiveSecurityContextHolder` |
| When appropriate | Imperative Servlet or deliberately designed adapters | WebFlux/Reactor reactive chains |
| What it does NOT solve | Does not check tenant/ACL | Also does not automatically check tenant/ACL |

### 2.1. A Thread-Pool Callback Does Not Carry the Original ThreadLocal

Snippet illustrating the issue:

```java
ThreadLocal<String> current = new ThreadLocal<>();

current.set("alice");
CompletableFuture<String> result =
    CompletableFuture.supplyAsync(current::get);

// Never rely on the result being "alice".
System.out.println(result.join());
current.remove();
```

This snippet is **explanatory only** and not part of the runnable project below. With `CompletableFuture.supplyAsync`, the callback runs on another executor; ThreadLocal values are normally not copied there. Some propagation tools can alter observed behavior, so never treat any specific output of this snippet as a security contract.

**Nor should you try to fix this with `InheritableThreadLocal`** across all use cases: thread pools reuse worker threads, and thread creation time does not match request start time. Copying a principal from an older thread also fails to verify whether that user still holds permission at execution time.

### 2.2. In Reactor, the Subscription Is the Key Boundary

```text
Publisher definition / assembly
            |
            | not a fixed identity for every subscriber
            v
       Mono / Flux
        /       \
       /         \
Subscribe A    Subscribe B
Context A      Context B
alice / T1     bob / T2
       \         /
        v       v
  Operators read Context
  per subscription
```

The same **cold** publisher can be subscribed to by Alice and Bob with two different contexts. Each subscriber receives results matching its own identity if the publisher is built properly: no capturing users into singleton fields, no sharing cached authorized outputs, and no eager side effects outside the publisher.

### 2.3. Reactor Context Is Not a Shared Java `Map`

`reactor.util.context.Context` is an immutable key-value structure that produces a new instance on each write. An operator receiving a `ContextView` reads only the entries active for that subscription and pipeline branch.

This does **not** mean Context is a secret vault or an unforgeable security boundary. Code running inside the same application can write to the Context directly; therefore only **trusted boundaries** may construct an `Authentication` from verified identity. Never build an `Authentication` from arbitrary JSON, cookies, or self-asserted headers and attach it via `withAuthentication`.

---

## 3. Essential Reactor APIs to Know

### 3.1. `contextWrite(...)`: Putting Data into Context

A pure Reactor example without Spring:

```java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.getOrDefault(
            "requestUser", "anonymous"
        ))
    );

String result = greeting
    .contextWrite(ctx -> ctx.put("requestUser", "alice"))
    .block();

System.out.println(result);
```

Output in CLI/tests:

```text
Hello alice
```

Here:

- `Mono.deferContextual(...)` runs its lambda only on **subscription**, supplying a `ContextView`.
- `contextWrite(...)` creates a new Context containing `requestUser=alice`.
- `.block()` initiates a subscription, which is fine for CLI/tests; inside a WebFlux request pipeline, **never call `block()`** to wait for reactive work.

**`requestUser` is an illustrative domain key, not an internal Spring Security key.** Never invent a Context key `"username"` and assume Spring Security automatically treats it as the principal.

### 3.2. `contextWrite(ContextView)` and `contextWrite(Function)`

Two common forms:

```java
Mono<String> first = greeting.contextWrite(
    reactor.util.context.Context.of("requestUser", "alice")
);

Mono<String> second = greeting.contextWrite(
    ctx -> ctx.put("requestUser", "bob")
);
```

Both set context for their respective **upstream** operators upon subscription. The function form receives the downstream Context and returns a new Context; avoid deleting or overwriting framework-managed keys unless intentional and controlled.

### 3.3. Context Propagates Bottom-Up from Downstream to Upstream

Syntactically, developers often write:

```java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tag"))
    )
    .contextWrite(ctx -> ctx.put("tag", "NEAR"))
    .contextWrite(ctx -> ctx.put("tag", "FAR"));
```

At subscribe time, the trailing `contextWrite` sets `FAR`, then the operator closer to the source sets `NEAR`. `deferContextual` sees the value nearest to it:

```text
NEAR
```

**Rule of thumb:** `contextWrite` affects **upstream** operators in the chain, not code appearing *below* it in Java source order.

Example where context is not visible:

```java
Mono<String> result = Mono.just("value")
    .contextWrite(ctx -> ctx.put("tag", "INNER"))
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tag", "MISSING"))
    ));
```

`flatMap` sits **downstream** of `contextWrite("INNER")`, so the inner subscriber's context here does not inherit keys from the upstream operator above it. Written this way, the expected result is:

```text
MISSING
```

This is why `contextWrite` placement must be **tested on the final publisher**, not guessed by reading source top-to-bottom.

### 3.4. Using `deferContextual` When Sources Need Identity

When a repository/service needs Context data as soon as a subscriber starts:

```java
Mono<String> actorName = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("actorName", "anonymous"))
);
```

With **Spring Security**, however, the standard way to read identity is:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Do not duplicate security identity under a custom key without an explicit integration requirement; two identity sources easily drift out of sync.

---

## 4. How Does Spring Security Put `Authentication` into Reactor Context?

`ReactiveSecurityContextHolder` lives in package:

```java
org.springframework.security.core.context
```

Key APIs:

| API | Purpose |
| --- | --- |
| `getContext()` | Returns `Mono<SecurityContext>` from the current Reactor Context |
| `withAuthentication(Authentication)` | Creates a Reactor Context holding a `SecurityContext` with `Authentication` |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Inserts a `Mono<SecurityContext>` into Context |
| `clearContext()` | Function for `contextWrite` that clears the security context from Context |

### 4.1. Reading the Current User

```java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

This reads identity per **subscriber**, without requiring the executing thread to hold an imperative `SecurityContextHolder`.

When no context exists, `getContext()` completes empty. For secured endpoints, never fall back to a default like `"admin"` or tenant `"public"` to continue querying; **fail closed**:

```java
Mono<Authentication> requiredAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(
            new AccessDeniedException("Authentication required")
        ));
```

In production, also check `authentication.isAuthenticated()` and exclude anonymous tokens using `AuthenticationTrustResolver` or a proper Spring Security expression. An anonymous token can report `isAuthenticated() == true`; a raw boolean check alone is insufficient.

### 4.2. Attaching Authentication to a Pipeline in Tests/CLI

```java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice",
    "demo-only",
    List.of(new SimpleGrantedAuthority("memo:read"))
);

Mono<String> example =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );

String answer = example.block();
System.out.println(answer);
```

Expected output:

```text
alice
```

`withAuthentication(alice)` constructs a Reactor `Context` carrying the security context so upstream operators can read it. This is a **test/CLI simulation**. Never build a privileged `UsernamePasswordAuthenticationToken` from a username/role sent by an HTTP client and treat it as an authenticated user.

### 4.3. `withSecurityContext(Mono<SecurityContext>)`

If the application already holds a `Mono<SecurityContext>` constructed by a **trusted authentication boundary**, you can use:

```java
Mono<SecurityContext> securityContext = Mono.fromSupplier(() -> {
    SecurityContext ctx = new SecurityContextImpl();
    ctx.setAuthentication(alice);
    return ctx;
});

Mono<String> pipeline = username.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(
        securityContext
    )
);
```

This snippet requires importing `SecurityContextImpl` and having `alice` defined. `Mono.fromSupplier` makes context creation lazy; the authentication value must still be verified from a trusted source, never from arbitrary user input.

**Never share a single mutable `SecurityContext` across users.** If anything calls `setAuthentication` on a shared instance, other subscribers can be affected. Create a fresh context per request/actor.

### 4.4. Deliberate Use of `clearContext()`

```java
Mono<String> anonymousRead = username
    .contextWrite(ReactiveSecurityContextHolder.clearContext())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

`clearContext` sits **closer to the source**, so it clears the subscription's security context upstream. `username` receives no identity from the outer `withAuthentication`.

In sensitive operations, never let `switchIfEmpty(Mono.just("admin"))` turn a missing context into privilege. Authorization must deny by default.

### 4.5. What Does Spring WebFlux Do Automatically?

When an HTTP request passes through Spring Security WebFlux:

1. Security WebFilters apply authentication from HTTP Basic, session, JWT/Bearer, or another configured mechanism.
2. For authenticated requests, `ReactorContextWebFilter` helps place the `SecurityContext` into the Reactor Context according to the security context repository and pipeline.
3. Reactive controllers and services use `ReactiveSecurityContextHolder.getContext()` to retrieve identity per request subscription.
4. `@PreAuthorize` from **Reactive Method Security** can evaluate permissions using the Reactor Context's identity.

**Do not manually call `withAuthentication` in every controller** when requests already flow through Spring Security properly. Constructing authentication inside a controller from a request body can accidentally bypass provider authentication altogether.

---

## 5. `@PreAuthorize` and Reactive Method Security

### 5.1. Enabling the Right Configuration

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
```

With Spring Security 6.5, `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` selects the reactive `AuthorizationManager` engine. A typical protected method:

```java
@PreAuthorize("hasAuthority('memo:read')")
public Flux<MemoView> list() {
    return actorResolver.require()
        .flatMapMany(actor ->
            repository.findByTenantId(actor.tenantId())
        );
}
```

This snippet requires `MemoView`, `ActorResolver`, and repository. The full project example is in section 8.

**Do not confuse** `@EnableWebFluxSecurity` with `@EnableReactiveMethodSecurity`: the first secures the HTTP WebFilter chain, while the second enables authorization on Spring-managed method calls via proxies.

### 5.2. A Publisher Returned by a Method Is Not an Executed Decision

```java
Flux<MemoView> pending = memoService.list();
```

Holding `pending` does not prove the caller can read the data. The reactive method-security interceptor cooperates with the publisher/subscription. When `pending` is subscribed to, it uses that subscription's Reactor Context to evaluate `@PreAuthorize`.

Proper tests must subscribe:

```java
StepVerifier.create(
    pending.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    )
).expectNextCount(2).verifyComplete();
```

If you only call the method and assert no Java exception was thrown, you can miss authorization failures emitted as **reactive `onError` signals**.

### 5.3. Same Publisher, Two Subscribers

```text
memoService.list() -> Flux<MemoView> secured
    |
    +-- subscribe Alice / memo:read / T1
    |      -> @PreAuthorize allow
    |      -> ActorResolver sees Alice/T1
    |      -> queries only tenant T1
    |
    +-- subscribe Bob / memo:read / T2
           -> @PreAuthorize allow
           -> ActorResolver sees Bob/T2
           -> queries only tenant T2
```

When Reactor Context is used correctly, a cold publisher does not "remember" Alice just because Alice subscribed first. With a real policy, every subscription can re-evaluate permissions. Repository queries must also be **tenant-scoped to the actor verified in that subscription**.

### 5.4. Do Not Rely on Caller-Supplied Principals

Dangerous pattern:

```java
// FLAWED by design: client picks username and tenant.
@GetMapping("/api/memos")
Flux<MemoView> all(
        @RequestHeader("X-User") String username,
        @RequestHeader("X-Tenant") String tenant) {
    return repository.findByTenantId(tenant);
}
```

Even if the URL requires `.authenticated()`, this code still trusts an unverified tenant. Derive the tenant from a stable `issuer + subject`/server membership or verify the selected active tenant. The functional `memo:read` check and tenant isolation are **two independent constraints**.

### 5.5. Never Use `SecurityContextHolder` Inside Reactive Callbacks

```java
// WRONG in a reactive pipeline if assuming ThreadLocal is always valid.
return Mono.fromSupplier(() ->
    SecurityContextHolder.getContext()
        .getAuthentication().getName()
);
```

This may run on a thread without an imperative context, or one where context propagation behaves differently. Recommended approach:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
```

Even though Reactor/Micrometer context-propagation bridges can restore certain ThreadLocals in operator callbacks, that is **not** a reason to design Reactive Method Security around implicit ThreadLocals. When integrating imperative libraries, use a verified adapter and forbid silent fallbacks.

---

## 6. `publishOn`, `subscribeOn`, `flatMap`, and Context Lifecycle

### 6.1. Reactor Context Follows the Reactive Chain Across Scheduler Hops

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(name -> "Hello " + name)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)
        );
```

This is a snippet (requiring `Schedulers` import and `alice`). Despite `publishOn`, identity comes from the subscription's Context. Expected CLI/test output is `"Hello alice"`.

`subscribeOn` controls where subscription/source execution starts; `publishOn` affects where downstream signals are processed. **Neither automatically turns an ordinary ThreadLocal into safe context.**

### 6.2. `flatMap` and Inner Publishers

A pipeline:

```java
return actorResolver.require()
    .flatMap(actor -> remotePolicyClient.check(actor))
    .flatMap(result -> repository.findAllowed(result));
```

This is an illustrative snippet. `flatMap` subscribes to the inner publisher under Reactor's contract and propagates the subscriber context along the chain. If you **split away** with `remotePolicyClient.check(actor).subscribe()` inside a lambda, you spawn a detached subscription that loses request completion, error propagation, and identity tracking.

Compose and return child publishers instead. If you must send identity explicitly to a remote service, pass a **contract-verified stable user ID + tenant scope**, never serialize the entire `SecurityContext` or secret tokens into messages.

### 6.3. Why Is Context Not a Global Variable?

```text
HTTP request A -> Reactor Context A -> alice / T1
HTTP request B -> Reactor Context B -> bob / T2

Possible:
  A and B run on the same event loop worker at different times.
  A has an operator switching to a parallel scheduler.
  B creates its own inner publishers.

Must NOT happen:
  static CURRENT_USER = "alice"
  ThreadLocal holding tenant T1 then accidentally used on request B.
```

Subscriber-scoped context keeps identities isolated across these flows, provided you never capture a user into a singleton field or share cached authorized outputs across users.

### 6.4. Context Loss When Leaving Reactor

Error-prone boundaries:

- `CompletableFuture.supplyAsync(...)` created outside the reactive chain.
- Manually managed `new Thread(...)` or `ExecutorService.submit(...)`.
- Imperative `@Async` methods.
- `queue.publish(...)` followed by a job executing hours later.
- Fire-and-forget `.subscribe()` detached from the request lifecycle.
- External SDK callbacks running on SDK-owned threads.

Reactor Context **does not prove** identity crossed those boundaries safely. When handing off to queues or background jobs, include minimal verified facts, protect message integrity/origin, and **re-authorize at job execution time** within your revocation SLA.

---

## 7. Defining the Security Contract for the Example

We build a multi-tenant memo service with in-memory data to keep the focus on identity and Context.

| Memo ID | Tenant | Title |
| ---: | --- | --- |
| 11 | T1 | Alpha |
| 12 | T1 | Beta |
| 21 | T2 | Gamma |

Demo identities:

| Username | Tenant from server directory | Authority |
| --- | --- | --- |
| alice | T1 | `memo:read` |
| bob | T2 | `memo:read` |
| mallory | T1 | `memo:other` |

Rule:

```text
canListOrViewMemo(actor, memo) =
    validAuthenticated(actor)
    AND hasAuthority(actor, "memo:read")
    AND actor.tenant == memo.tenant
```

A user with read authority belonging to T1 **cannot** read T2's memo #21. A user in T1 lacking `memo:read` cannot read T1 memos either. The service code uses the server-side directory and never accepts a tenant from HTTP headers or bodies.

The full application provides:

- HTTP GET `/public` requiring no authentication.
- GET `/api/me` requiring an authenticated user, returning identity from Reactor Context and the directory.
- GET `/api/memos` requiring `memo:read` via **Reactive Method Security**, returning only the current tenant's memos.
- GET `/api/memos/{id}` requiring `memo:read`, returning 404 for IDs in other tenants.
- A CLI demo using `withAuthentication` to bind two identities to the same `Mono`.
- `StepVerifier` and `WebTestClient` tests verifying real policy through Spring proxies and WebFilters.

**Explicit limitation:** The in-memory directory and store are simulations, not a production authentication system. In a real DB, tenant filtering must live directly in SQL/R2DBC repository queries, e.g., `WHERE tenant_id = :trustedTenant` or `WHERE id=:id AND tenant_id=:trustedTenant`. Never fetch all tenants and filter afterward in Java.

---

## 8. Complete Java 17 + Spring Boot 3.5.8 Project

### 8.1. Directory Tree

```text
reactor-context-identity-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── IdentityApplication.java
    │       ├── ReactiveSecurityConfig.java
    │       ├── CurrentActor.java
    │       ├── Memo.java
    │       ├── MemoView.java
    │       ├── MemoStore.java
    │       ├── MemoService.java
    │       └── MemoController.java
    └── test/
        └── java/demo/
            ├── ReactorIdentityTest.java
            └── MemoHttpSecurityTest.java
```

All classes belong to package `demo`. This section is a runnable Gradle project, not pseudo-code; each snippet maps directly to its file.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'reactor-context-identity-demo'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages compatible Spring Security, Reactor, and Netty versions via its BOM. Do not add `spring-boot-starter-web` (Servlet) to this WebFlux learning project so auto-configuration does not alter the web application type.

### 8.4. Identity Application and CLI: `IdentityApplication.java`

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(
            MemoService memos,
            MemoStore store) {

        return args -> {
            Authentication alice = actor("alice", "memo:read");
            Authentication bob = actor("bob", "memo:read");

            // Same cold Mono, created before having
            // the subscriber's Reactor Security Context.
            Mono<String> identity = memos.whoAmI();

            System.out.println("READS_BEFORE: "
                + store.readSubscriptions());

            System.out.println("ALICE_IDENTITY: "
                + identity.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block());

            System.out.println("BOB_IDENTITY: "
                + identity.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)
                ).block());

            System.out.println("ALICE_MEMO_IDS: "
                + memos.list().map(MemoView::id)
                    .collectList()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(alice)
                    ).block());

            System.out.println("BOB_MEMO_IDS: "
                + memos.list().map(MemoView::id)
                    .collectList()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(bob)
                    ).block());

            System.out.println("READS_AFTER: "
                + store.readSubscriptions());
        };
    }

    static Authentication actor(
            String username, String authority) {
        return new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }
}
```

**Note:** `.block()` here runs inside `CommandLineRunner` on the CLI demo thread, not inside a WebFlux controller or event loop. When moving logic into a controller, **return `Mono`/`Flux`** instead of blocking.

`UsernamePasswordAuthenticationToken` is constructed manually **only for CLI/tests**. In real HTTP requests, Spring Security verifies credentials; clients must never select principals or authorities via JSON.

### 8.5. Reactive Web + Method Security: `ReactiveSecurityConfig.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo-pass")
            .authorities("memo:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo-pass")
            .authorities("memo:read")
            .build();

        UserDetails mallory = User.withUsername("mallory")
            .password("{noop}demo-pass")
            .authorities("memo:other")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, mallory
        );
    }
}
```

The HTTP rule for `/api/**` requires authentication and **does not require** `memo:read` by itself. Functional permission is checked by `@PreAuthorize` on the service. Deliberately splitting the two layers lets tests catch missing Method Security: Mallory can log in, yet must still receive 403 when calling `/api/memos`.

The password `"{noop}demo-pass"` is for learning/testing only. In production, use secure password hashing and an appropriate identity provider/OIDC/OAuth2 setup.

### 8.6. Trusted Actor Resolver: `CurrentActor.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

record Actor(String username, String tenantId) {
}

@Component
public class CurrentActor {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    private final Map<String, Actor> directory = Map.of(
        "alice", new Actor("alice", "T1"),
        "bob", new Actor("bob", "T2"),
        "mallory", new Actor("mallory", "T1")
    );

    public Mono<Actor> require() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(this::isTrusted)
            .flatMap(authentication ->
                Mono.justOrEmpty(
                    directory.get(authentication.getName())
                )
            )
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated tenant mapping required"
                )
            ));
    }

    private boolean isTrusted(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !trustResolver.isAnonymous(authentication);
    }
}
```

`CurrentActor.require()` returns `Mono<Actor>` to resolve **when the subscriber executes**, never writing the username into a singleton field. When the Reactor Security Context is missing, anonymous, or unmapped, the method **fails closed** with `AccessDeniedException`.

The server-side directory is the trusted tenant source in this **demo**. In production, map stable `issuer + subject` from your identity provider to memberships and the active tenant; if a user belongs to multiple tenants, **check membership** for the requested active tenant before using it. `getName()` is not always globally unique, so do not use it as a security key if usernames can collide.

**Never return raw `Authentication`, credentials, or tokens** in HTTP responses to "debug tenant". Return only explicitly approved identity fields.

### 8.7. Model: `Memo.java`

```java
package demo;

public record Memo(
        Long id,
        String tenantId,
        String title) {
}
```

`Memo` represents a server-side domain row including `tenantId`. In a real application, rows come from R2DBC/DB; never trust a user-supplied `tenantId`.

### 8.8. DTO: `MemoView.java`

```java
package demo;

public record MemoView(Long id, String title) {

    public static MemoView from(Memo memo) {
        return new MemoView(
            memo.id(), memo.title()
        );
    }
}
```

`MemoView` contains only ID/title; do not serialize internal tenant, owner, policy/ACL fields, or object graphs unless the endpoint requires them.

### 8.9. Lazy, Tenant-Scoped Store: `MemoStore.java`

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class MemoStore {

    private final List<Memo> rows = List.of(
        new Memo(11L, "T1", "Alpha"),
        new Memo(12L, "T1", "Beta"),
        new Memo(21L, "T2", "Gamma")
    );

    private final AtomicInteger reads = new AtomicInteger();

    public Flux<Memo> findAllInTenant(String trustedTenant) {
        return Flux.defer(() -> {
            reads.incrementAndGet();

            return Flux.fromIterable(rows)
                .filter(m -> m.tenantId().equals(trustedTenant))
                .sort(Comparator.comparing(Memo::id));
        });
    }

    public Mono<Memo> findInTenant(
            String trustedTenant, Long id) {

        return Flux.defer(() -> {
            reads.incrementAndGet();

            return Flux.fromIterable(rows)
                .filter(m ->
                    m.tenantId().equals(trustedTenant)
                    && m.id().equals(id)
                );
        }).next();
    }

    public int readSubscriptions() {
        return reads.get();
    }
}
```

Both data-access methods take a **trusted tenant** supplied by the service. `Flux.defer` ensures the counter increments only **when a subscription actually reaches the store**, proving denials do not silently read data first and block only at an outer layer.

**Never copy in-memory filtering into a multi-tenant production system.** In a real DB, the **tenant predicate must reside in the SQL/repository query** prior to fetching, pagination, counting, or `JOIN`s. The demo uses a small list strictly to demonstrate identity flow.

### 8.10. Service with `@PreAuthorize`: `MemoService.java`

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class MemoService {

    private final CurrentActor actors;
    private final MemoStore store;

    public MemoService(
            CurrentActor actors,
            MemoStore store) {
        this.actors = actors;
        this.store = store;
    }

    @PreAuthorize("isAuthenticated()")
    public Mono<String> whoAmI() {
        return actors.require().map(actor ->
            actor.username() + "@" + actor.tenantId()
        );
    }

    @PreAuthorize("hasAuthority('memo:read')")
    public Flux<MemoView> list() {
        return actors.require()
            .flatMapMany(actor ->
                store.findAllInTenant(actor.tenantId())
                    .map(MemoView::from)
            );
    }

    @PreAuthorize("hasAuthority('memo:read')")
    public Mono<MemoView> one(Long id) {
        return actors.require()
            .flatMap(actor ->
                store.findInTenant(actor.tenantId(), id)
            )
            .map(MemoView::from)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Memo unavailable"
                )
            ));
    }
}
```

Listing flow:

```text
HTTP authentication
    |
    v
MemoController.list()
    |
    v
Spring proxy + reactive @PreAuthorize memo:read
    |
    v
MemoService.list() publisher
    |
    v
CurrentActor.require()
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Trusted actor directory -> T1 or T2
    |
    v
MemoStore.findAllInTenant(trustedTenant)
    |
    v
Flux<MemoView> containing only the matching tenant
```

`@PreAuthorize` does not replace tenant scoping. In `one`, lookups always use `id + tenant`; if Alice guesses T2's ID 21, the service returns 404 without disclosing another tenant's data.

**`isAuthenticated()` is not data authorization.** `whoAmI` permits any authenticated user with a directory mapping; `list` and `one` require the additional `memo:read` authority enforced by Method Security.

### 8.11. WebFlux Controller: `MemoController.java`

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class MemoController {

    private final MemoService service;

    public MemoController(MemoService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public Mono<String> publicStatus() {
        return Mono.just("PUBLIC");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return service.whoAmI();
    }

    @GetMapping("/api/memos")
    public Flux<MemoView> list() {
        return service.list();
    }

    @GetMapping("/api/memos/{id}")
    public Mono<MemoView> one(
            @PathVariable Long id) {
        return service.one(id);
    }
}
```

The controller **returns publishers**; it never calls `.block()`, `.subscribe()`, or builds an `Authentication` from the request body. The WebFlux framework manages subscriptions and the Reactor security context.

If a controller must pass tenant/user to multiple services outside a single reactive chain, rather than copying a ThreadLocal, resolve `Actor` once from `CurrentActor.require()` and **pass explicit `Actor`/trusted IDs** as arguments to application services. Never accept a self-asserted `Actor` from an HTTP client.

---

## 9. Run Command and Expected CLI Stdout

With Gradle Wrapper:

```bash
./gradlew bootRun
```

In PowerShell:

```powershell
.\gradlew.bat bootRun
```

If there is no Gradle Wrapper, install a compatible Gradle version or generate a wrapper and re-run. In this project, Spring Boot startup logs still appear; the lines **printed by `CommandLineRunner`** are expected to be:

```text
READS_BEFORE: 0
ALICE_IDENTITY: alice@T1
BOB_IDENTITY: bob@T2
ALICE_MEMO_IDS: [11, 12]
BOB_MEMO_IDS: [21]
READS_AFTER: 2
```

**Exact breakdown:**

1. `MemoStore` starts fresh with `reads = 0`.
2. `Mono<String> identity = memos.whoAmI()` has not queried the store and has no subscriber yet.
3. `.contextWrite(withAuthentication(alice)).block()` subscribes as Alice; `CurrentActor.require()` sees Alice/T1.
4. Reusing **the same `identity` publisher** to subscribe as Bob yields Bob/T2, without retaining Alice's name.
5. The first `memos.list()` subscribes as Alice; the store runs once and returns `[11, 12]`.
6. The second `memos.list()` subscribes as Bob; the store runs a second time and returns `[21]`.
7. `READS_AFTER = 2`, because the two `whoAmI` calls never touch the memo store.

**These lines are expected output from the source code**, not a claim that it was compiled or run in the authoring environment. `block()` is used only in CLI/tests, never in reactive HTTP handlers.

### 9.1. Testing HTTP with the Basic Demo

```bash
curl -i http://localhost:8080/public
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/memos
curl -i -u bob:demo-pass http://localhost:8080/api/memos
```

Expected:

- `/public` returns `PUBLIC` anonymously.
- Alice `/api/me` returns `alice@T1`, and list contains only Alpha/Beta.
- Bob `/api/me` returns `bob@T2`, and list contains only Gamma.
- Unauthenticated callers to `/api/memos` are rejected.
- Mallory logs in successfully yet calling `/api/memos` is blocked by method authority.
- Alice calling `/api/memos/21` cannot read Bob/T2's memo.

Basic demo auth with `{noop}` is strictly for learning; production requires secret management, TLS, and proper credential verification.

---

## 10. Direct Integration Tests with `StepVerifier`

`StepVerifier` creates a **real subscription** to verify identity flow and authorization. It is essential: a test that merely calls `service.list()` without subscribing **never proves** reactive policies ran.

**`src/test/java/demo/ReactorIdentityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest
@ActiveProfiles("test")
class ReactorIdentityTest {

    @Autowired
    MemoService memos;

    @Autowired
    MemoStore store;

    private static Authentication alice() {
        return IdentityApplication.actor(
            "alice", "memo:read");
    }

    private static Authentication bob() {
        return IdentityApplication.actor(
            "bob", "memo:read");
    }

    private static Authentication mallory() {
        return IdentityApplication.actor(
            "mallory", "memo:other");
    }

    private static <T> Mono<T> as(
            Mono<T> publisher, Authentication actor) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(actor)
        );
    }

    private static <T> Flux<T> as(
            Flux<T> publisher, Authentication actor) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(actor)
        );
    }

    @Test
    void sameMonoUsesDifferentSubscriberIdentities() {
        Mono<String> identity = memos.whoAmI();

        StepVerifier.create(as(identity, alice()))
            .expectNext("alice@T1")
            .verifyComplete();

        StepVerifier.create(as(identity, bob()))
            .expectNext("bob@T2")
            .verifyComplete();
    }

    @Test
    void sameColdFluxUsesTrustedTenantOfEachSubscriber() {
        Flux<MemoView> publisher = memos.list();

        int readsBefore = store.readSubscriptions();

        StepVerifier.create(as(publisher, alice()))
            .expectNext(
                new MemoView(11L, "Alpha"),
                new MemoView(12L, "Beta")
            )
            .verifyComplete();

        StepVerifier.create(as(publisher, bob()))
            .expectNext(
                new MemoView(21L, "Gamma")
            )
            .verifyComplete();

        assertEquals(
            readsBefore + 2,
            store.readSubscriptions()
        );
    }

    @Test
    void missingReadAuthorityDoesNotReachStore() {
        int before = store.readSubscriptions();

        StepVerifier.create(as(memos.list(), mallory()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, store.readSubscriptions());
    }

    @Test
    void crossTenantLookupIsNotVisible() {
        StepVerifier.create(as(memos.one(21L), alice()))
            .expectError(
                org.springframework.web.server
                    .ResponseStatusException.class
            )
            .verify();

        StepVerifier.create(as(memos.one(21L), bob()))
            .expectNext(new MemoView(21L, "Gamma"))
            .verifyComplete();
    }

    @Test
    void identitySurvivesReactorSchedulerHop() {
        Mono<String> shifted = memos.whoAmI()
            .publishOn(Schedulers.parallel());

        StepVerifier.create(as(shifted, alice()))
            .expectNext("alice@T1")
            .verifyComplete();
    }

    @Test
    void missingReactorSecurityContextFailsClosed() {
        StepVerifier.create(memos.whoAmI())
            .expectError()
            .verify();
    }

    @Test
    void contextWriteClosestToSourceWins() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("tag"))
        );

        Mono<String> result = source
            .contextWrite(ctx -> ctx.put("tag", "NEAR"))
            .contextWrite(ctx -> ctx.put("tag", "FAR"));

        StepVerifier.create(result)
            .expectNext("NEAR")
            .verifyComplete();
    }
}
```

**Key verifications:**

- `sameMonoUsesDifferentSubscriberIdentities` uses the **same `Mono`** with two contexts; no user is captured at assembly.
- `sameColdFluxUsesTrustedTenantOfEachSubscriber` uses the **same `Flux`**, asserting T1/T2 isolation and that the store re-runs on each subscribe.
- `missingReadAuthorityDoesNotReachStore` proves denial does not merely turn the final output into an error after reading data.
- `crossTenantLookupIsNotVisible` confirms knowing another tenant's ID is insufficient to read the object.
- `identitySurvivesReactorSchedulerHop` proves Reactor Context lookup does not rely on thread-local request identity.
- `missingReactorSecurityContextFailsClosed` refuses to fall back to admin when identity is missing.
- `contextWriteClosestToSourceWins` clarifies Context scoping and propagation direction.

**Note:** Tests rely on Spring-managed beans, Method Security AOP, and real subscribers; never construct `new MemoService(...)` and expect annotations to apply. Because these tests do not mutate store state, they are independent of JUnit execution order (counters check relative increments).

### 10.1. Why Not Set `SecurityContextHolder` Directly in Tests?

Writing:

```java
SecurityContextHolder.getContext()
    .setAuthentication(alice);
```

does not ensure the publisher is subscribed to under the intended **Reactive Security Context**. In direct Reactor tests, use:

```java
publisher.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
);
```

This tests the exact API used by reactive method security rather than relying on the JUnit runner thread's ThreadLocal.

`@WithMockUser` remains useful with Spring Security Test, especially for WebFlux integration tests, yet when two users subscribe to **the same publisher**, explicit `contextWrite` distinguishes each subscription clearly.

---

## 11. HTTP Integration Tests with `WebTestClient`

The previous tests bypassed HTTP WebFilters. To prove **Spring Security actually puts `Authentication` into the Reactor Context** after handling an HTTP request, use `WebTestClient`.

**`src/test/java/demo/MemoHttpSecurityTest.java`:**

```java
package demo;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("test")
class MemoHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void configure() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient alice() {
        return client.mutateWith(
            mockUser("alice").authorities(
                new SimpleGrantedAuthority("memo:read")
            )
        );
    }

    private WebTestClient bob() {
        return client.mutateWith(
            mockUser("bob").authorities(
                new SimpleGrantedAuthority("memo:read")
            )
        );
    }

    private WebTestClient mallory() {
        return client.mutateWith(
            mockUser("mallory").authorities(
                new SimpleGrantedAuthority("memo:other")
            )
        );
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PUBLIC");
    }

    @Test
    void meReadsSubscriberIdentityFromWebFluxContext() {
        alice().get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice@T1");

        bob().get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("bob@T2");
    }

    @Test
    void listIsTenantScopedEvenWithSameAuthority() {
        alice().get().uri("/api/memos").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(11)
            .jsonPath("$[1].id").isEqualTo(12)
            .jsonPath("$[2]").doesNotExist();

        bob().get().uri("/api/memos").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(21)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void authenticatedButMissingAuthorityIsForbidden() {
        mallory().get().uri("/api/memos").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void knownOtherTenantIdDoesNotRevealMemo() {
        alice().get().uri("/api/memos/21").exchange()
            .expectStatus().isNotFound();

        bob().get().uri("/api/memos/21").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(21)
            .jsonPath("$.title").isEqualTo("Gamma");
    }

    @Test
    void anonymousCannotCallProtectedApi() {
        client.get().uri("/api/me").exchange()
            .expectStatus().isUnauthorized();
    }
}
```

`WebTestClient` invokes the WebFlux application context configured with `.apply(springSecurity())`; `mockUser(...)` supplies principal/authorities for **test requests**, and Spring Security inserts the context into the reactive pipeline. There is no need to set `SecurityContextHolder` manually or add `X-User` in the controller.

The assertions reflect **expected HTTP statuses for HTTP Basic configuration**. If a real application uses Bearer tokens, form login, or custom authentication entry points, error representations may differ while preserving allow/deny policies.

### 11.1. Running All Tests

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

This runs both direct Reactor Context tests and HTTP security tests. When debugging failures, separate three layers:

1. HTTP authorization: did the WebFilter require login?
2. Method authorization: did `@PreAuthorize` run via the Spring proxy?
3. Data authorization: was the trusted tenant included in the query/lookup?

If tests check only HTTP 401/403 without asserting returned payloads, they can miss cross-tenant leaks.

---

## 12. Avoiding Bad Identity Caching and Context Retention Beyond Request Lifetimes

### 12.1. Never Hold the Current User in a Singleton Field

Wrong:

```java
@Service
class UnsafeMemoService {
    private String currentUsername;

    Mono<String> read() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> {
                currentUsername =
                    ctx.getAuthentication().getName();
                return currentUsername;
            });
    }
}
```

This snippet is **intentionally flawed by design** and not part of the runnable project. `@Service` is singleton-scoped by default; concurrent Alice and Bob subscriptions overwrite each other's field. Use local lambda variables or pass `Actor` down to services/repositories instead of storing shared mutable state.

### 12.2. Never Capture Identity at Assembly to Emit Later

```java
// WRONG SNIPPET in a reactive app if capturedUsername
// is read from a ThreadLocal at assembly time.
String capturedUsername = currentThreadUser();
Mono<String> result = Mono.just(capturedUsername);
```

`Mono.just` evaluates its argument before creating the `Mono`; the user can change before subscription while the captured value remains frozen. The right pattern in Reactive Spring Security reads the user from context at subscription:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
```

### 12.3. `Mono.cache()` Can Replay an Authorized Decision or Response

Dangerous snippet:

```java
// Shared across multiple users: risky if response is cached.
Mono<String> shared = memoService.whoAmI().cache();
```

If Alice subscribes first, the cache may record `"alice@T1"`. Bob subscribing to **the same shared cached publisher** afterward can receive `"alice@T1"` without creating a fresh subscription to the underlying protected publisher. That leaks identity; with `MemoView`, it leaks data.

```text
Alice -> cached mono -> authorized source -> alice@T1
                              |
                              v
                            cache

Bob   -> cached mono -> replay alice@T1
                      (not necessarily rechecked)
```

Solution: never cache **personalized or pre-authorized publishers** and share them across users; if caching raw data, keys must be tenant/resource/version/visibility-aware and permissions must still be checked per subscriber. For long-lived hot streams or Server-Sent Events/WebSockets, enforce per-subscriber/session policies and proper revocation/cancellation mechanisms.

### 12.4. Retry/Repeat Create New Subscriptions

```java
Mono<MemoView> publisher = memoService.one(11L);
Mono<MemoView> retried = publisher.retry(1);
```

`retry` can re-subscribe and therefore repeat reads and policy checks; on writes, it can trigger duplicate side effects. Never retry authorization denials to "wait for permission"; denial is not a transient network error. For mutating operations, enforce idempotency keys, transactions, versions, and explicit retry policies.

### 12.5. Never Fire-and-Forget `.subscribe()`

Wrong in a controller:

```java
@GetMapping("/start")
public Mono<String> start() {
    memoService.one(11L).subscribe();
    return Mono.just("DONE");
}
```

This is **flawed** illustrative code, not part of the runnable project. It spawns a secondary subscription whose lifecycle, errors, and context are detached from the HTTP response, returning `"DONE"` even if the operation is denied or incomplete.

Compose instead:

```java
@GetMapping("/start")
public Mono<MemoView> start() {
    return memoService.one(11L);
}
```

For genuine background tasks, create a job with explicit ownership, identity/policy scope, correlation ID, and an authorization protocol **at job execution time**, rather than borrowing the originating request's security context indefinitely.

---

## 13. Context Propagation Bridges Do Not Replace Reactive Security Context

Systems may use Micrometer Context Propagation, Reactor `Hooks.enableAutomaticContextPropagation()`, `contextCapture()`, or adapters to carry select ThreadLocals across Reactor operators. Those tools address **interoperability** with tracing, logging, and legacy libraries.

Distinguish clearly:

- **Reactor `Context`:** the native subscriber-scoped model used for Spring Security reactive identity.
- **`SecurityContextHolder` ThreadLocal:** an imperative mechanism with a storage strategy, typically used in Servlets.
- **Micrometer/Reactor context-propagation bridge:** can capture/restore ThreadLocals **with registered accessors** within specific scopes and versions.
- **MDC logging:** typically a logging framework ThreadLocal requiring a bridge for trace IDs to cross schedulers.
- **`ReactiveSecurityContextHolder`:** the Spring Security API for storing and retrieving `SecurityContext` in Reactor pipelines.

Never claim that **every** ThreadLocal propagates automatically once a hook is enabled, or that security code reading ThreadLocals always works across schedulers. Behavior depends on Reactor version, context-propagation library, accessors, subscription lifecycle, and boundary placement.

### 13.1. When You Must Call an Imperative Library

Suppose the system relies on an SDK taking user ID as an argument:

```java
return currentActor.require()
    .flatMap(actor -> legacyAdapter.callFor(
        actor.username(),
        actor.tenantId()
    ));
```

This is a code snippet; `legacyAdapter` must return a suitable `Publisher` and manage blocking isolation. Passing **explicit trusted identity** is far easier to verify than hoping a library reads Spring's ThreadLocal.

If an SDK only reads a ThreadLocal, wrap it in a tightly scoped adapter that sets, restores, and clears state, runs on an appropriate scheduler, and is tested for concurrency, timeouts, cancellation, and errors. In reactive request handling, **never run blocking JDBC/SDK calls directly on the event loop**; `boundedElastic` provides bounded offloading, not automatic DB transactions or reactive authorization.

### 13.2. Logging Context and Identity Are Not the Same

You can place `traceId` and `requestId` into Context for observability, but never treat them as authentication proof. Clients can supply correlation IDs; they are useful for logs yet **must never determine roles or tenants**.

When recording stable user IDs/tenant IDs in audit logs, restrict PII, retention, and masking. Never log raw bearer tokens, passwords, or full `Authentication` objects.

---

## 14. Security Context Does Not Guarantee Permissions Remain Valid

Even when `Authentication` propagates accurately via Reactor Context, an authorization decision can still become stale:

```text
t1: Subscriber holds Authentication Alice / memo:write
t2: @PreAuthorize ALLOW
t3: Admin revokes grant or transfers ownership
t4: Service executes UPDATE using stale data
t5: DB COMMIT
```

Reactor Context answers **whose identity this is**; it does not synchronize **newly changed ACLs, owners, tenants, or roles**.

For write operations:

1. Use `@PreAuthorize` to check functional authorities.
2. Read trusted user/tenant from the subscriber security context.
3. Load resource/policy state from the authoritative source.
4. Guard `tenant_id`, `owner_id`, state, and `version` right inside the `UPDATE` or lock/recheck inside the transaction.
5. When permissions rely on grant tables or a remote PDP, define snapshot/revocation semantics and transaction protocols.
6. Never treat `Authentication` inside a long-lived stream as an immutable copy of permissions forever.

Conditional SQL example:

```sql
UPDATE memos
SET title = :newTitle,
    version = version + 1
WHERE id = :memoId
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedSubject
  AND version = :expectedVersion;
```

This is **illustrative SQL**, not run against the demo's in-memory store. Affected rows `0` means one or more conditions no longer matched; never strip tenant or version checks to retry. If update permission depends on another grant table, constraints/locks must cover that permission source as well.

### 14.1. Reactive Database Transactions

An R2DBC application can use `ReactiveTransactionManager`/`TransactionalOperator` within the reactive chain:

```java
// CODE SNIPPET: requires TransactionalOperator and real repository.
return transactionalOperator.transactional(
    repository.findByIdAndTenantId(memoId, trustedTenant)
        .flatMap(memo -> verifyAndUpdate(memo, trustedActor))
);
```

Reactive transaction context is not JDBC's thread-bound transaction. With R2DBC, transactions coordinate via Reactor Context; never call `@Transactional` and then `.block()` or manually `.subscribe()` to break work outside the boundary.

**Even a Reactor Context holding a valid `Authentication` does not make an unscoped `UPDATE` safe.** Identity propagation and data authorization are two distinct requirements.

### 14.2. Long-Lived Streams and Revocation

A `Flux` may emit items for hours. A single `@PreAuthorize` check at subscription start does not re-check every `onNext` or cancel the stream when a user loses permissions. For sensitive data:

- recheck authorization per item/batch or per policy freshness window;
- cancel active subscribers on revocation using appropriate signaling;
- use tenant-scoped queries at the source to avoid prefetching unauthorized data;
- track changes to tenant/role/ACL versions;
- ensure hot/multicast streams never broadcast tenant A data to tenant B subscribers;
- test revocation mid-stream and after cache warm-up.

All of these are policy requirements, not automatic features provided by `contextWrite`.

---

## 15. Test Checklist for Context Bugs and Security Bypasses

| Test Case | What to Verify |
| --- | --- |
| Build `Mono` without subscribing | Neither authorization nor data access has run yet |
| Subscribe same `Mono` as Alice and Bob | Identity resolves per subscription |
| `publishOn` switches scheduler | Identity still comes from `ReactiveSecurityContextHolder` |
| Missing Reactor Security Context | Fails closed; never falls back to default admin |
| Anonymous authentication | Not treated as a verified user based solely on `isAuthenticated()` |
| Unknown user/tenant mapping | Denied without querying the entire table |
| Authenticated user lacking authority | `@PreAuthorize` blocks before data access |
| T1 user knows T2 ID | Repository queries `id + tenant`, never returns T2 content |
| Shared `Mono.cache` across two users | Never replays another user's personalized response |
| Calling `this.securedMethod()` | Catches Spring AOP self-invocation bypass |
| Creating detached `.subscribe()` | Lifecycle, errors, and identity handled explicitly |
| `retry` on write action | No duplicate side effects |
| `flatMap` with inner publisher | Context is preserved without detached sub-subscriptions |
| `CompletableFuture`/`@Async` | Identity does not rely on implicit ThreadLocal |
| Owner/grant changes between check and write | Transaction/conditional mutation rechecks |
| Misplaced Reactor `contextWrite` | `contextWrite` affects the intended upstream |
| HTTP app with `mockUser` | Both Security WebFilters and method proxies engage |
| Upgrading Spring Security/Reactor | Re-test context-propagation behavior on the new version |

### 15.1. Common Mistakes

| Mistake | Impact | Remediation |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` inside callbacks | Context may be empty or stale | Use `ReactiveSecurityContextHolder.getContext()` |
| Singleton `ThreadLocal` for user/tenant | Requests bleed across threads | Per-subscriber Context or explicit trusted actor |
| `InheritableThreadLocal` with thread pools | Does not match request lifecycle | Never use as default auth propagation |
| `Mono.just(expensiveWrite())` | Side effects run at assembly | `Mono.defer`/`fromSupplier` and transactions |
| Trusting `X-User`, `X-Tenant` | Caller can impersonate or pick victim tenant | Verify auth + server-side membership |
| Setting `withAuthentication` from JSON input | Bypasses authentication provider | Trusted boundaries/tests only |
| Missing `@EnableReactiveMethodSecurity` | `@PreAuthorize` does not protect methods | Enable it and test the proxy |
| Calling `new MemoService(...)` | Bypasses AOP interceptor | Inject Spring-managed bean |
| Calling `this.secured()` within same bean | Self-invocation bypasses proxy | Extract bean, keep domain guards |
| Test never subscribes | Reactive authorization never observed | Use `StepVerifier` or `WebTestClient` |
| Caching authorized `Mono` across users | Replays another user's data | Scope caches and re-authorize per subscriber |
| Fire-and-forget `.subscribe()` | Lost lifecycle, unhandled errors | Return/compose publisher |
| Calling `.block()` on WebFlux event loop | Blocks threads, hurts throughput | Reactive composition |
| `publishOn` followed by raw ThreadLocal read | Value is not guaranteed | Reactor Context or controlled adapters |
| Storing `Authentication` in singleton field | Races and identity bleed | Lazy per-subscriber resolver |
| Confusing `traceId` with principal | No authentication guarantee | Authoritative `SecurityContext` |
| Relying on stale role for writes after revoke | TOCTOU | Rechecks / conditional DB updates |
| Another tenant's data still appears | Unscoped repository | `WHERE tenant_id = trustedTenant` |
| Catching `AccessDenied` and returning secrets | Fail-open | Deny and emit no sensitive data |
| `WebTestClient` missing `springSecurity()` | Tests omit security WebFilters | Apply test security setup |

---

## 16. Exercises and Self-Check Questions

### Question 1: Why is `ThreadLocal` insufficient?

In a WebFlux request, the source is subscribed on an event-loop thread, then `publishOn(Schedulers.parallel())` runs. Is ThreadLocal `SecurityContextHolder.getContext()` guaranteed to return the right identity on both threads?

**Answer:** No. You need `ReactiveSecurityContextHolder`/Reactor Context or a deliberately configured and tested propagation adapter.

### Question 2: Which direction does `contextWrite` affect?

```java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tag"))
)
.contextWrite(ctx -> ctx.put("tag", "ONE"))
.contextWrite(ctx -> ctx.put("tag", "TWO"));
```

**Answer:** The source sees `"ONE"` (the writer closer to the source), not `"TWO"`.

### Question 3: Why must `withAuthentication` never be populated directly from a request body?

**Answer:** Because it only puts `Authentication` into Context without verifying credentials or memberships. Reading username/roles from JSON and inserting them creates a forged principal.

### Question 4: One `Mono` subscribed twice under two users

`Mono<String> p = memoService.whoAmI()` is subscribed to by Alice (T1) and Bob (T2). With a cold publisher and proper Context, should both return the same username?

**Answer:** No. Each subscriber carries its own identity; `StepVerifier` tests confirm the two distinct results.

### Question 5: Missing authentication

`ReactiveSecurityContextHolder.getContext()` emits nothing. Should the service fall back to admin or read all tenants?

**Answer:** No. Fail closed; without a valid identity, never touch an unscoped repository.

### Question 6: Difference between HTTP auth and method auth

`@EnableWebFluxSecurity` protects URLs; what does `@PreAuthorize` on a reactive service require?

**Answer:** Enable `@EnableReactiveMethodSecurity`, invoke methods through the Spring proxy, and verify with real subscriptions.

### Question 7: Can `Mono.cache()` leak users?

**Answer:** Yes, if the cache wraps a publisher personalized/authorized for Alice and the same instance is shared with Bob. Scope caches properly and recheck per subscriber.

### Question 8: Is `Mono.just(performWrite())` lazy?

**Answer:** No, if Java invokes `performWrite()` eagerly while evaluating the argument. Use `Mono.defer`/`fromSupplier` for lazy sources and place mutations inside transaction/policy boundaries.

### Question 9: A long-lived `Flux` while the user is revoked

**Answer:** Context keeps carrying the identity; it does not automatically block subsequent items after revocation. Implement per-item/batch checks or cancellation per your security contract.

### Question 10: Moving to a background queue

Should you copy the request's entire Reactor Context, including tokens, and replay it days later?

**Answer:** No. Pass minimal integrity-protected identity/scope and re-authorize when the job executes; never persist raw access tokens long-term.

### Question 11: Why might `@PreAuthorize` not protect T2's objects?

**Answer:** Authority `memo:read` is a functional permission. Repositories still require tenant scoping and object policies, not just authentication.

### Question 12: How do you prove no side effects occurred after denial?

**Answer:** Place counters/logs at the lazy source or re-read the DB. After `StepVerifier.expectError(AccessDeniedException.class)`, assert the source never ran and data stayed unchanged.

### Question 13: Why use `AuthenticationTrustResolver`?

**Answer:** To avoid mistaking an anonymous token whose `isAuthenticated()==true` for a verified user; combine with directory and trust checks.

### Question 14: Is Reactor `Context` a security boundary against forged internal code?

**Answer:** No. Any trusted code able to construct publishers and `Authentication` instances can write to Context. Security boundaries live at authentication providers, principal validation, method/data authorization, and system configuration.

### Question 15: What should a test assert after a scheduler switch?

**Answer:** That `ReactiveSecurityContextHolder.getContext()` still returns the subscriber's identity despite `publishOn`/`subscribeOn` switching schedulers; never assert specific thread names or ThreadLocal values.

---

## 17. References and Official Documentation

1. [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, Reactor Context, `@PreAuthorize` on `Mono`/`Flux`.
2. [Spring Security 6.5 API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext`, `withAuthentication`, `withSecurityContext`, `clearContext`.
3. [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): authentication in WebFlux.
4. [Spring Security — Reactive WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, WebFilters, and authentication.
5. [Spring Security — Testing WebFlux Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html): `WebTestClient` and test support.
6. [Spring Security — WebFlux Test Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, `springSecurity()`.
7. [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber Context, `contextWrite`, `deferContextual`, propagation direction.
8. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, scheduler semantics.
9. [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): interoperability between Reactor Context and ThreadLocals.
10. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and subscriber-driven tests.
11. [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): transaction propagation with Reactor, `TransactionalOperator`.
12. [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP and self-invocation limitations.

**Conclusion:** In WebFlux, identity should be resolved **per subscriber via `ReactiveSecurityContextHolder`**, never by relying on a Java thread's `ThreadLocal`. `contextWrite` attaches context in tests and trusted boundaries; Spring Security WebFlux populates context automatically for authenticated HTTP requests. `@EnableReactiveMethodSecurity` + `@PreAuthorize` protect publishers when invoked through Spring proxies. However, Context alone does not validate inputs, isolate cross-tenant queries lacking predicates, stop shared caches from replaying another user's data, or solve revocations/TOCTOU after initial allowance. Test with `StepVerifier`/`WebTestClient` across multiple users and scheduler hops, and enforce tenant, ACL, and transaction guards at the data layer.