# Lost Reactor Context or ThreadLocal Mismatch With Execution Model in Spring Security Authentication

## 1. Symptoms and First Diagnostic Question

A common bug when Java apps move from Spring MVC/Servlet to Spring WebFlux/Reactor is: the request authenticated cleanly, yet inside an async service or callback, calling `SecurityContextHolder.getContext().getAuthentication()` returns `null`, anonymous, or more rarely an unexpected identity. Sometimes the bug surfaces only in production under load, after `publishOn`/`subscribeOn`, inside `CompletableFuture`, or within an ad-hoc `subscribe()`.

**The topic "Lost Reactor Context or ThreadLocal Mismatch With Execution Model"** is not merely failing to see a username. It can cause three kinds of harm:

- **False denials:** the user logged in yet the service thinks they are anonymous, returning 401/403 or skipping tasks.
- **Wrong access:** custom code falls back to admin/default tenant or trusts a stale `ThreadLocal` from a thread pool, attaching privileges to the wrong user.
- **Broken observability:** request trace IDs, tenants, or MDC vanish across thread hops; logs show only part of the flow and mislead investigators into thinking authorization skipped.

**Foundational rules:**

- In **Spring Security Servlet/MVC**, `SecurityContextHolder` defaults to `ThreadLocal`: the security context follows the **current thread** for the request scope, cleaned up by Spring Security filters.
- In **Spring Security Reactive/WebFlux**, the security context lives in **each `Subscriber`'s Reactor `Context`**. The right way to read it is `ReactiveSecurityContextHolder.getContext()`, returning `Mono<SecurityContext>`. Context is not stored in a global variable and is not guaranteed to sit in the `ThreadLocal` of whichever thread runs a callback.
- **Reactor Context** and **`ThreadLocal`** are two distinct mechanisms; never "fix" reactive servers with `SecurityContextHolder.MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL`.
- When code hands work off to **`ExecutorService`, `CompletableFuture`, native callbacks, or non-Reactor systems**, context does not automatically follow; design explicit data passing or supported bridging.
- **A Context holding a principal does not auto-grant permissions to new tasks:** authority/tenant/object ownership must still be enforced against policy and trusted identity; never mix state across requests.

This lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.5 Servlet/WebFlux, and Reactor 3.x** as its reference frame. Verify exact APIs against your running BOM when upgrading to Spring Boot 4/Spring Security 7.

## 2. Comparing `ThreadLocal`, Reactor Context, and `SecurityContext`

| Aspect | Servlet `SecurityContextHolder` (default) | `ReactiveSecurityContextHolder` in WebFlux |
| --- | --- | --- |
| Logical storage | Thread's `ThreadLocal<SecurityContext>` | `Mono<SecurityContext>` bound in subscriber's Reactor `Context` |
| How to read | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Typical scope | Thread serving the HTTP request | Protected Publisher/Subscriber stream and subscription |
| On thread switch | `ThreadLocal` does **not** cross thread pools automatically | Reactor Context **propagates across compliant Reactor operators** |
| Standalone `CompletableFuture.supplyAsync` | Usually absent; needs deliberate propagation | Does not automatically cross non-Reactor callbacks |
| Standard `Mono`/`Flux` | Not where auth should be read | Context travels with subscription, including standard `publishOn`/`subscribeOn` |
| Nested `subscribe()` inside | Avoid mixing lifecycles | Can create a detached subscription, losing context and error handling |
| Cleanup | Security filter clears context on request thread | Subscriber lifecycle and Context scope; `ThreadLocal` bridges need cleanup |
| How to test | `MockMvc` + Spring Security Test | `WebTestClient` + Reactor `StepVerifier` |

**`SecurityContext`** holds `Authentication`, including principal, authorities, authenticated flag, and metadata. It is not a safe place to stash arbitrary raw passwords/access tokens; auth mechanisms typically erase credentials or retain only necessary fields. **Reactor Context** is likewise not a secret vault or database; it passes contextual metadata through a pipeline without encrypting or persisting across networks.

### Common Confusion Pattern

```java
// Wrong inside a reactive pipeline: reading auth from ThreadLocal
// instead of the subscriber's Reactor Context.
Mono<String> unsafe() {
    return Mono.just("ready")
            .publishOn(Schedulers.parallel())
            .map(x -> SecurityContextHolder.getContext()
                    .getAuthentication().getName());
}
```

This is a **bug illustration** (requires Spring Security/Reactor imports), not an API controller to copy into production. In WebFlux, `getAuthentication()` can be `null`; if a stale `ThreadLocal` happened to linger earlier, the code even risks reading the **wrong principal**. Succeeding occasionally on one thread **proves nothing** under concurrent subscribers.

The right approach reads `ReactiveSecurityContextHolder.getContext()` inside the reactive chain and enforces roles/ownership via Spring Security authorization.

## 3. Reactor Context Operates per **Subscription**, Not per Thread

Reactor Core defines `Context` as an **immutable** key/value structure attached to a subscriber. It flows at **subscription time from downstream to upstream**. To add data, use `contextWrite(...)`; to read inside logic running at subscribe time, use `Mono.deferContextual(...)` or `Flux.deferContextual(...)`.

### 3.1. Plain Context Example (Not Security Authentication)

```java
Mono<String> currentRequestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")));

Mono<String> first = currentRequestId
        .contextWrite(ctx -> ctx.put("requestId", "req-A"));

Mono<String> second = currentRequestId
        .contextWrite(ctx -> ctx.put("requestId", "req-B"));

// Two separate subscriptions:
String a = first.block();   // "req-A" in CLI/unit test
String b = second.block();  // "req-B" in CLI/unit test
```

This is an **illustrative Reactor snippet** using `reactor.core.publisher.Mono`; `block()` belongs only in CLIs/tests, **never** inside WebFlux handlers on the event loop. One source Publisher `currentRequestId` is reused while each subscription receives its own Context; there is no global "current requestId" variable.

### 3.2. `contextWrite` Affects Upstream, Not Thread State

```java
Mono<String> flow =
        Mono.deferContextual(ctx -> Mono.just(ctx.get("label")))
            .contextWrite(ctx -> ctx.put("label", "inner"))
            .flatMap(v -> Mono.deferContextual(ctx ->
                    Mono.just(v + "+" + ctx.get("label"))))
            .contextWrite(ctx -> ctx.put("label", "outer"));

// On subscribe: "inner+outer"
```

Above, the **upstream** `deferContextual` sees `inner`; the downstream `flatMap` sees `outer`. Seeing a key in Context at one point does not mean every operator or inner Publisher in the graph sees the same value. Context propagation follows scope, `contextWrite` ordering, and subscriber lineage.

**In Spring Security**, placing `ReactiveSecurityContextHolder.withAuthentication(...)` in the wrong position can make upstream see the context while another downstream/inner subscription does not. Prefer letting framework security filters establish context at the HTTP boundary; avoid injecting synthetic principals in production chains.

### 3.3. `publishOn` and `subscribeOn`

- `publishOn(Schedulers.parallel())` switches the thread running **downstream operators** after that point; those operators remain in the Reactor chain and can read Context cleanly via `deferContextual`.
- `subscribeOn(Schedulers.boundedElastic())` affects where subscription/source work is scheduled; it does not turn Context into `ThreadLocal`.
- Standard Reactor operators preserve propagation whenever the chain/subscription is intact. Bugs usually come from **reading `ThreadLocal`** or **starting a separate subscription**, not from `publishOn` dropping Reactor Context.
- `Schedulers.boundedElastic()` suits offloading properly wrapped **blocking** APIs; `Schedulers.parallel()` is for CPU-bound tasks and should never block on I/O or the Reactor Netty event loop.

### 3.4. Why Can `Mono.just(...)` and `Mono.defer(...)` Mislead?

`Mono.just(value)` captures a `value` **evaluated eagerly at assembly time**. Writing `Mono.just(SecurityContextHolder.getContext().getAuthentication())` reads auth **before subscription**, yielding null or the wrong user. Switching to `Mono.defer(() -> Mono.just(SecurityContextHolder...))` defers evaluation yet **still reads the wrong `ThreadLocal` source** in WebFlux. When you need Context, use `ReactiveSecurityContextHolder.getContext()` or Reactor's `deferContextual`.

**Never fix context bugs by adding `Thread.sleep(...)` or "forcing everything onto one thread"**; that hides races locally and stalls the event loop in production.

## 4. `ReactiveSecurityContextHolder`, WebFlux Filter Chains, and Authentication Scope

In Spring Security WebFlux, security filters create/restore `SecurityContext` from the auth scheme/repository and attach it to the Reactor subscription. Spring Security reactive method security docs emphasize using:

```java
Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
```

This snippet requires imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
```

**When no reactive `SecurityContext` exists**, `getContext()` emits `Mono.empty()`. `map(SecurityContext::getAuthentication)` should not blindly assume auth is always present; on a resource protected by `authenticated()` with a valid auth mechanism it is expected, whereas custom contexts and public endpoints may lack it. Use `switchIfEmpty` for public endpoints and fail closed/keep 401/403 on protected operations.

### 4.1. Inject Auth Into Context Only at Verified Test/Custom Boundaries

```java
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "N/A", List.of(
                        new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> result =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(alice));
```

Import `UsernamePasswordAuthenticationToken` from `org.springframework.security.authentication` and `SimpleGrantedAuthority` from `org.springframework.security.core.authority`. `withAuthentication(...)` creates a Reactor Context containing `SecurityContext` for **that subscription**; it writes neither to `HttpSession`/`WebSession` nor verifies passwords/tokens. In production, never read a username from a request parameter and construct an "authenticated token" manually like this: that is an **authentication bypass**.

### 4.2. Lifecycle Configured on the Right Stack

| Scenario | Mechanism |
| --- | --- |
| Spring MVC `HttpSecurity`, `SecurityFilterChain` | Servlet auth filters, `SecurityContextHolder`, and `SecurityContextRepository` |
| Spring WebFlux `ServerHttpSecurity`, `SecurityWebFilterChain` | Reactive WebFilter chain, `ReactiveSecurityContextHolder`, and `ServerSecurityContextRepository`/Reactor Context |
| HTTP Basic in WebFlux | `http.httpBasic(...)` creates reactive auth flow protecting the exchange |
| Spring Security reactive method rules | `@EnableReactiveMethodSecurity` on publisher-returning methods using Reactor Context |
| Reactive unit tests | `StepVerifier` and `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` |
| HTTP WebFlux tests | `WebTestClient`, Spring Security Test `springSecurity()`/`mockUser()`, or real Basic/JWT |

**Do not mix stacks:** `SecurityWebFilterChain` does not take `HttpSecurity`; Servlet `SecurityFilterChain` is not for `ServerHttpSecurity`. If a project pulls in both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot may pick the Servlet web application type; verify the actual runtime web stack rather than seeing `reactor-core` on the classpath and assuming WebFlux.

## 5. Common Failure Table by Where the Flow Breaks

| Symptom | Cause | Test to Distinguish |
| --- | --- | --- |
| `SecurityContextHolder.getContext().getAuthentication() == null` in WebFlux | Reading Servlet `ThreadLocal` instead of Reactor Context | Read `ReactiveSecurityContextHolder.getContext()` in pipeline |
| Auth present in controller yet lost in `CompletableFuture.supplyAsync` | Task runs on an Executor/pool outside the Reactor subscription | Pass immutable validated identity explicitly or use managed bridge |
| `MDC.get("traceId")` empty after `publishOn` | MDC uses `ThreadLocal` without Micrometer context bridge | Compare Reactor Context `deferContextual`; check registered accessors/hooks |
| Auth missing after `service.doWork().subscribe()` | Created a detached subscriber, losing parent context/error lifecycle | Return `Mono` and compose with `flatMap` |
| User A occasionally sees B's tenant | Mutable singleton/global variable or uncleaned `ThreadLocal` in pool | Run concurrent A/B tests; reset/remove context after tasks |
| `@WithMockUser` passes yet real HTTP Basic fails | Test injects principal directly, skipping provider | Send `WebTestClient` requests with real Basic/password |
| HTTP request through WebFlux stays unauthorized | Wrong `SecurityWebFilterChain` matcher, auth failure, missing principal | Check HTTP 401/403, filters, credentials, and masked logs |
| `ReactiveSecurityContextHolder.getContext()` test is empty | Test subscriber lacks context or `contextWrite` is in wrong scope | Unit test `withAuthentication` at right spot with `StepVerifier` |
| Async job runs after request ended | Request context is gone and job lacks service identity | Pass actor ID/audit metadata; re-authorize privileges before side effects |
| `block()` throws `UnsupportedOperationException`/`IllegalStateException` on blocking | Blocking on `reactor-http-nio` or parallel scheduler | Stay reactive end-to-end; offload blocking to right scheduler |
| Enabled automatic propagation yet auth still vanishes | Missing accessor/binding, split context, or version differences | Test for exact version; never treat hooks as auth mechanisms |
| Login succeeds yet next request loses user | Wrong repository/session/cookie/entry point, not Reactor Context | Inspect `ServerSecurityContextRepository` and `WebSession`/cookie lifecycle |
| Added `MODE_INHERITABLETHREADLOCAL` yet users get mixed | Child-thread semantics fail with reused executors | Revert; use reactive context / delegating wrappers for right stack |
| `WebClient` does not auto-send Bearer downstream | Reactor Context holding `Authentication` does not mean token relay | Configure OAuth client/token relay per policy; verify audience/scope |
| `Mono.empty()` treated as anonymous and given a public default role | Fail-open in custom fallback | Fail closed on protected endpoints; never auto-grant roles |

**Critical takeaway:** on seeing 403, do not rush to say "lost context". The user may be authenticated yet lack role/tenant, blocked by CSRF, matched to the wrong `WebFilterChain`, or denied downstream. Check **whether authentication was established**, **authorization policy**, and **where the status originated**.

## 6. Spring Boot 3 + WebFlux + Spring Security 6.5 Example Application

This example demonstrates the right path from HTTP request to `ReactiveSecurityContextHolder`, usable as a lab in a **Java 17+, Spring Boot 3.x project compatible with Spring Security 6.5**. Do not include Servlet/MVC starters in this project.

### 6.1. `build.gradle`

In a Gradle project with the Spring Boot plugin and Java toolchain configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

`spring-boot-starter-test` brings JUnit Jupiter/AssertJ/Mockito from the BOM. `reactor-test` provides `StepVerifier`. Use only the single `reactor-core` version managed by the Boot BOM; overriding it arbitrarily can change context propagation semantics.

### 6.2. `ReactiveContextApplication.java`

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
```

### 6.3. `ReactiveSecurityConfig.java`

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/public/**").permitAll()
                    .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(alice, admin);
    }
}
```

- `@EnableReactiveMethodSecurity` enables method security backed by Reactor Context. Protected methods must return a `Publisher` (e.g., `Mono`) so the reactive interceptor works properly. Never put method security on synchronous `void`/`String` methods assuming reactive context is present.
- `httpBasic()` in the example accepts test credentials; the server builds authentication from `MapReactiveUserDetailsService` and BCrypt. Passwords are **local fixtures** only; never use an in-memory user store or test passwords in production.
- `.anyExchange().authenticated()` protects all other routes. With pure HTTP GET, CSRF disabling is unnecessary; if adding cookie-backed web POSTs, test CSRF under the right scheme. Browsers can auto-resend Basic credentials, so do not claim Basic is always immune to CSRF.
- If Spring Boot actually starts **Servlet** due to another dependency, `ServerHttpSecurity` config will not protect MVC as expected. Check runtime logs and dependencies.

### 6.4. `IdentityService.java`: Correct Method Security Example

```java
package com.example.reactiveauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminView() {
        return currentName().map(name -> "admin=" + name);
    }
}
```

Subtle point: `currentName()` returns a **deferred `Mono`** rather than reading `ThreadLocal` when the service method is invoked. `adminView()` is a public method on a Spring bean so the interceptor enforces `@PreAuthorize`; admin policy requires both HTTP authentication and the role. Calling from **within the same class via `this.adminView()`** (self-invocation) can bypass Spring proxy method security; test calls from controllers/other beans, not just direct unit `new IdentityService()`.

### 6.5. `IdentityController.java`: Reading Context After Switching Schedulers

```java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class IdentityController {

    private final IdentityService service;

    public IdentityController(IdentityService service) {
        this.service = service;
    }

    @GetMapping("/api/whoami")
    public Mono<String> whoami() {
        return service.currentName().map(name -> "user=" + name);
    }

    @GetMapping("/api/whoami-hop")
    public Mono<String> whoamiAfterSchedulerSwitch() {
        return Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> service.currentName())
                .map(name -> "user=" + name);
    }

    @GetMapping("/api/public/context")
    public Mono<String> publicContext() {
        return service.currentName()
                .map(name -> "user=" + name)
                .defaultIfEmpty("anonymous");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return service.adminView();
    }
}
```

**Why is this a useful diagnostic example?**

- `/api/whoami` and `/api/whoami-hop` both access `ReactiveSecurityContextHolder`. In the second route, the read happens **inside `flatMap` after `publishOn`**; code using `ThreadLocal` instead would lose auth. With proper Reactor Context, the same authenticated subscriber still sees Alice.
- `/api/public/context` returns `anonymous` only when the context **genuinely lacks authentication**; it is a public demo route, not a model for sensitive rules. Never use `defaultIfEmpty("admin")` or a privileged principal as fallback.
- `/api/admin/report` calls another bean method with `@PreAuthorize("hasRole('ADMIN')")`; Alice is denied even though her identity context exists. **Lost context** differs from **missing authority**.
- There are no `.block()`, `.subscribe()`, or global `ThreadLocal`s in the controller/service. Spring WebFlux manages subscriptions and response lifecycles.

### 6.6. Running Locally

Assuming the project has the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Test via development terminal, **never using real passwords over HTTP**:

```bash
curl -i http://localhost:8080/api/public/context
curl -i -u alice:alice-pass http://localhost:8080/api/whoami
curl -i -u alice:alice-pass http://localhost:8080/api/whoami-hop
curl -i -u alice:alice-pass http://localhost:8080/api/admin/report
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report
```

Expectations:

| Request | Result |
| --- | --- |
| `GET /api/public/context` without credentials | 200, body `anonymous` |
| `GET /api/whoami` without credentials | 401 with HTTP Basic challenge |
| Alice `GET /api/whoami` | 200, body `user=alice` |
| Alice `GET /api/whoami-hop` | 200, body `user=alice` even after scheduler switch |
| Alice `GET /api/admin/report` | 403 due to missing role, **not lost Reactor Context** |
| Admin `GET /api/admin/report` | 200, body `admin=admin` |

This is the **expected behavior for the demo**. Test 401/403 codes through the real `SecurityWebFilterChain`; do not assume every custom error handler or proxy preserves the exact same body/headers.

## 7. `WebTestClient` Testing: Covering Anonymous, User, and Admin States

In the WebFlux Boot project above, use `spring-security-test` and Spring Boot Test:

File `src/test/java/com/example/reactiveauth/ReactiveIdentityHttpTest.java`:

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveIdentityHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotReadProtectedIdentity() {
        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void anonymousPublicEndpointHasNoIdentity() {
        client.get().uri("/api/public/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("anonymous");
    }

    @Test
    void aliceIdentitySurvivesReactorSchedulerHop() {
        client.get().uri("/api/whoami-hop")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=alice");
    }

    @Test
    void aliceLacksAdminAuthority() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminIsAuthorizedInReactiveMethod() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin=admin");
    }

    @Test
    void badPasswordIsAuthenticationFailure() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

**Why use real Basic?** `@WithMockUser` and `mockUser()` inject a test principal, which is useful for checking authorization and Context flow yet **does not prove real HTTP Basic password checking/`ReactiveAuthenticationManager` ran**. The suite above sends Basic headers to the real app on a random port.

**Never put production passwords in test fixtures or logs.** When diagnosing after `publishOn`, test with multiple distinct accounts to catch mixed identities rather than checking only "some username exists".

## 8. `StepVerifier`: Verifying Independent Context Across Two Subscribers

Reactor-level tests verify whether a `Mono` picks up the right security context at subscription time without bleeding context from a prior request.

File `src/test/java/com/example/reactiveauth/ReactivePrincipalTest.java`:

```java
package com.example.reactiveauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactivePrincipalTest {

    private Authentication principal(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void samePublisherUsesDifferentContextForEachSubscriber() {
        Mono<String> username = ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("missing");

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("alice"))))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("bob"))))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(username)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void threadSwitchDoesNotLoseReactivePrincipal() {
        Mono<String> username = Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("alice"))))
            .expectNext("alice")
            .verifyComplete();
    }
}
```

**This is a unit test with mock `Authentication`** and does not test databases/password hashing; it tests exact **Context propagation semantics** in Reactor/Spring. All imports belong to the WebFlux/Security/Reactor stack; `StepVerifier` is in `reactor-test`. When Context is absent, `missing` is expected; when Context has "bob", "alice" must not leak through.

**Test real concurrency:** fire hundreds of concurrent Alice/Bob requests with separate tokens/sessions through `WebTestClient` on real schedulers/Netty. Assert response names, tenants, roles, and business side effects never mix rather than merely asserting `Thread.currentThread().getName()` changed.

## 9. Detached Subscription: Calling `subscribe()` Directly Inside a Service

### 9.1. Anti-Example

```java
// Do NOT use in handlers:
// This creates a detached subscription outside the response lifecycle.
public Mono<String> wrongFireAndForget() {
    doSensitiveWork().subscribe(); // side effect runs independently
    return Mono.just("accepted");
}
```

What can go wrong:

- Subscription starts the moment the method is called, before the downstream request subscription/context exists.
- The HTTP request's security context **does not automatically transfer** into the detached subscription.
- Results/exceptions/cancellation are detached from the HTTP response; the endpoint can return 200 even if the real action fails.
- A task starting after the user logged out or the account was revoked can hold a stale auth snapshot if copied manually without re-checking.

**Right approach:** compose within the same graph:

```java
public Mono<String> correctComposition() {
    return doSensitiveWork()
            .thenReturn("accepted");
}

// When you need to pass outputs or decide based on the principal:
public Mono<String> identityBoundWork() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                performAuthorizedAction(authentication.getName()))
            .thenReturn("accepted");
}
```

This is a **fragment inside a service** where `doSensitiveWork()`/`performAuthorizedAction(...)` are defined and domain authorization is checked. `thenReturn("accepted")` emits only after the source Publisher completes; errors/cancellations stay in the pipeline. For HTTP 202/long-running async queues, design a **durable job** storing account ID/audit and **service credentials + policy checks when the worker executes**, rather than pretending request Context outlives the response.

### 9.2. Context Does Not Auto-Propagate Over `WebClient`/OAuth Services

Even when `ReactiveSecurityContextHolder` holds the user's inbound `Authentication`, `WebClient` does not automatically forward `Authorization: Bearer ...` downstream. When token relay is needed, use OAuth2 client/delegation mechanisms with the right permissions, audience, and scope; never blindly forward raw inbound tokens to arbitrary services. A 401 from downstream does not prove local Reactor Context was lost.

## 10. `CompletableFuture`, `@Async`, `ExecutorService`, and Thread Pools

**Not all async code is Reactor.** Anything crossing into `CompletableFuture.supplyAsync`, `ExecutorService.submit`, custom callbacks, scheduled jobs, or message listeners has a different lifecycle.

### 10.1. Why Does `ThreadLocal` Not Follow Automatically?

```java
ThreadLocal<String> currentUser = new ThreadLocal<>();
currentUser.set("alice");

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(currentUser::get);

// A task on commonPool usually does not see "alice".
// result may be null. Never use as an auth mechanism.
```

This is a **Java anti-example** inside a context importing `CompletableFuture`, not a deterministic test because executor/default thread behavior can vary. By default a parent thread's `ThreadLocal` is not global, so other threads lack the value. `InheritableThreadLocal` copies only when a thread **is created**, making its semantics broken with reused thread pools and prone to mixing identities/tenants; never turn it on as a "quick fix" for WebFlux.

### 10.2. Passing Verified Data as Explicit Arguments

A safer pattern for longer-lived work captures **immutable actor ID/tenant ID/correlation ID** at the authenticated boundary and re-checks privileges at execution time:

```java
record AuditActor(String accountId, String tenantId) {}

// Fragment inside a reactive service:
Mono<String> work() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> {
            // stable ID/tenant here must come from a trusted principal,
            // never read accountId from a query param and trust it.
            AuditActor actor = resolveTrustedActor(auth);
            return Mono.fromCallable(() -> blockingBusinessAction(actor))
                .subscribeOn(Schedulers.boundedElastic());
        });
}
```

**The snippet requires implementing `resolveTrustedActor` and `blockingBusinessAction`** and is not a runnable class. Passing an actor ID onto `boundedElastic` provides explicit business input, yet `blockingBusinessAction` must still enforce authorization/ownership if accessing sensitive resources. Never place raw passwords or Bearer tokens into logs or queues.

If you use **Servlet/MVC** `@Async` and genuinely need the authenticated request's `SecurityContextHolder`, Spring Security offers wrappers such as `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` and dedicated support. That is a controlled solution for **Servlet `ThreadLocal`**, not a direct substitute for WebFlux's `ReactiveSecurityContextHolder`. Wrappers must avoid reusing stale contexts, clean up properly, and not retain privileges after user revocation.

## 11. Micrometer Context Propagation, MDC, and Automatic Mode: Using at the Right Level

Reactor 3.5+ integrates with **Micrometer Context Propagation** to bridge selected values to/from `ThreadLocal` via registered `ThreadLocalAccessor`s. There are two distinct concepts:

- **Reactor Context** is the source of contextual data inside the reactive graph.
- **`ThreadLocal` restoration/capture** is a bridge supporting legacy `ThreadLocal`-based libraries such as logging MDC, observability, and specific integrations.

Reactor exposes `contextCapture()` and `Hooks.enableAutomaticContextPropagation()`:

```java
// Conceptual: enable at bootstrap before creating subscriptions,
// only if dependencies/accessors and performance characteristics fit.
Hooks.enableAutomaticContextPropagation();
```

Import `reactor.core.publisher.Hooks`. **Do not enable the hook and assume security is now fine**. Reactor documentation notes automatic mode affects **new subscriptions**, requires registered `ThreadLocalAccessor`s, carries performance overhead, and must restore/clear `ThreadLocal` when Context lacks a value so nothing leaks to other users. This mechanism helps MDC/tracing; it **does not verify tokens, create new `Authentication`, or carry logins from one WebFlux request to another HTTP request**.

**Never assert an absolute rule like "`ThreadLocal` is always null after `publishOn`":** with automatic mode, the right accessors, and subscription context, certain `ThreadLocal`s can be restored. The catch is that it **depends on bridge/config and scope**, not reliable semantics for custom auth code. In WebFlux, business code should use `ReactiveSecurityContextHolder` and context-aware APIs instead of relying on workarounds.

### 11.1. MDC and Log Correlation

Log fields like `traceId` and `requestId` can vanish after scheduler switches because MDC binds to `ThreadLocal` by default. Approach:

1. Use Micrometer Observation/Tracing in Spring Boot matching your supported version and config.
2. Verify `ThreadLocalAccessor`/context-propagation dependencies are present and hooks/configs are active.
3. Test log fields across scheduler switches, async boundaries, and concurrent requests.
4. Never log raw `Authorization`, session cookies, or JWTs when debugging context; log only correlation IDs and policy-redacted user IDs.
5. Bound cardinality, collect traces with proper access controls, and set accurate retention.

**Avoid reading MDC `"user=alice"` as an authorization basis.** MDC is strictly for observability; `SecurityContext` and authoritative policy decide access. If MDC is wrong while auth is right, fix observability; if auth is wrong while MDC is right, it is still a security bug.

## 12. Standalone Java 17: Seeing `ThreadLocal` Loss and Leakage on Worker Threads

To separate two risks — **losing context on thread switches** and **stale context leaking in a thread pool when uncleaned** — use plain Java with no Spring/Reactor dependencies.

Save as `ThreadLocalBoundaryLab.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class ThreadLocalBoundaryLab {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    record TrustedActor(String name) {}

    private static String visibleOnCurrentThread() {
        String name = CURRENT.get();
        return name == null ? "missing" : name;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor();
        try {
            // Request thread scenario after real authentication.
            CURRENT.set("alice");
            System.out.println("requestThread=" +
                    visibleOnCurrentThread());

            // New worker thread does not inherit ThreadLocal from request.
            String absent = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("workerWithoutCapture=" + absent);

            // Explicit input, avoiding reading global ThreadLocal on worker.
            TrustedActor actor = new TrustedActor(CURRENT.get());
            String explicit = single.submit(actor::name).get();
            System.out.println("workerWithExplicitActor=" + explicit);

            // Operational bug example: task sets ThreadLocal and forgets remove.
            single.submit(() -> {
                CURRENT.set("bob");
                return null;
            }).get();
            String stale = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("staleWorkerValue=" + stale);

            // Proper ThreadLocal code must clean up in finally.
            single.submit(() -> {
                try {
                    CURRENT.set("carol");
                    return visibleOnCurrentThread();
                } finally {
                    CURRENT.remove();
                }
            }).get();
            String cleaned = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("workerAfterCleanup=" + cleaned);
        } finally {
            CURRENT.remove();
            single.shutdown();
            single.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Compile and run on Java 17+:

```bash
javac ThreadLocalBoundaryLab.java
java ThreadLocalBoundaryLab
```

**Deterministic expected** stdout: `newSingleThreadExecutor()` reuses one worker thread across tasks, and `ThreadLocal` is not inherited by default.

```text
requestThread=alice
workerWithoutCapture=missing
workerWithExplicitActor=alice
staleWorkerValue=bob
workerAfterCleanup=missing
```

Line-by-line meaning:

- `requestThread=alice` shows `ThreadLocal` holds values only on the thread where set.
- `workerWithoutCapture=missing` explains why async code often "loses the user" if reading a thread pool's `ThreadLocal`.
- `workerWithExplicitActor=alice` illustrates passing an **explicit value**, independent of worker thread state. In production, the actor must be verified and privileges re-checked if work runs later.
- `staleWorkerValue=bob` illustrates a thread pool **retaining stale values** when a task forgets `remove()`, causing cross-request tenant/principal leakage if used for authorization.
- `workerAfterCleanup=missing` proves cleanup via `finally`. Spring Security handles cleanup in integrated flows; rolling your own `ThreadLocal` for authenticated identity is still best avoided.

**Lab nature:** the example deliberately sets "bob" without removing it in one task to demonstrate the bug; **never put that pattern into production**. It does not prove Reactor Context is lost, because Reactor Context differs from `ThreadLocal`. Use the earlier Reactor/Spring examples to test reactive context accurately.

## 13. Real-App Context Bug Test Matrix

| ID | Scenario | Action | Expectation |
| --- | --- | --- | --- |
| C01 | WebFlux anonymous request | GET authenticated-only route | 401/redirect per entry point, never enters protected logic |
| C02 | Alice valid Basic credentials | `GET /api/whoami` | 200 `user=alice` |
| C03 | Alice + `publishOn(Schedulers.parallel())` | `GET /api/whoami-hop` | 200 `user=alice` |
| C04 | Admin + `publishOn` | GET same route | 200 `user=admin` |
| C05 | Alice lacks `ROLE_ADMIN` | `GET /api/admin/report` | 403 due to authorization, not lost context |
| C06 | Admin has right role | GET admin route | 200 and right identity |
| C07 | Same `Mono` subscribed twice | Alice context then Bob | Alice and Bob isolated, no leakage |
| C08 | Subscribe without context | `ReactiveSecurityContextHolder.getContext()` | Empty `Mono` or safe fallback |
| C09 | `contextWrite` placed in wrong spot | Unit test operator scope | Fails clearly; fix `contextWrite` placement |
| C10 | Nested inner Publisher in `flatMap` | Propagate context to inner chain | Correct subscriber semantics |
| C11 | Service uses `SecurityContextHolder` on wrong stack | Test across scheduler switch | Null/wrong auth caught, no access granted |
| C12 | Detached `subscribe()` in service | Trigger protected side effect | Test rejects false success; refactored to `flatMap` |
| C13 | `CompletableFuture.supplyAsync` | Read `ThreadLocal` on worker | Do not expect auto propagation |
| C14 | Context from request A | Submit request B async job next | Does not inherit principal A |
| C15 | Thread pool reuses Bob → Alice task | Logs/request B | Does not pick up Bob's tenant from stale `ThreadLocal` |
| C16 | Reactor context + MDC bridge | `publishOn`, log `traceId` | MDC keeps trace ID per real config; no leakage |
| C17 | No bridge | Reactor Context still holds `requestId` | Prefer reading via `deferContextual` |
| C18 | `WebClient` token relay | Call downstream OAuth API | Token/scope obey policy; no blind Bearer forwarding |
| C19 | Invalid/expired authentication | Call protected route | 401, never fabricate fake context to bypass |
| C20 | Account disabled after queuing job | Worker executes later | Re-check privileges/epoch per policy, never trust snapshots forever |
| C21 | Login via `WebSession` | Subsequent request with same session | Repository saves/loads reactive authentication cleanly |
| C22 | Same account across two tenants | Concurrent requests | Trusted tenant IDs never mix |
| C23 | `block()` on Netty event loop | Exercise handler | Never block; fix API or offload blocking I/O to `boundedElastic` |
| C24 | HTTP POST missing CSRF | Blocked by CSRF filter | Do not blame "lost Reactor Context" when auth never reached service |
| C25 | Spring MVC app mistaken for WebFlux | Inspect runtime and dependencies | Pick the `SecurityFilterChain` matching the real stack |
| C26 | Reactive method security | Invoke through Spring bean proxy | `@PreAuthorize` enforces properly on `Mono`/`Flux` |

**One test passing on the same thread is insufficient.** Apply concurrent load with multiple accounts/tenants, switch schedulers, and verify business authorization; cross-principal bugs often emerge only on thread reuse. In HTTP tests, verify 401/403 originates from the right filter/handler rather than checking status codes alone.

## 14. Step-by-Step Diagnostics When Production Reports Lost Identity

### Step 1 — Confirm the Real Runtime

- Is the app running Servlet or Reactive? Check Boot web application type, dependencies, and startup logs. `WebFlux + Spring MVC starters` can make Boot pick Servlet even if services return `Mono`.
- Did the request pass **real HTTP authentication**? Check 401/403/302 and the corresponding filter chain. Merely sending an `Authorization` header does not guarantee a valid token.
- Which Spring Security version? `SecurityWebFilterChain`/`ReactiveSecurityContextHolder` APIs in 6.x differ from Servlet and 7.x in several places.

### Step 2 — Compare Identity at 3 Checkpoints

1. Right after the first authentication `WebFilterChain`/handler, using reactive context reads.
2. Inside service `flatMap`/after `publishOn`/`subscribeOn`; the same account should still appear if the chain is intact.
3. Inside non-Reactor callbacks or job queues. If identity disappears only at step 3, inspect the Executor/`CompletableFuture` boundary; do not alter Spring Security `WebFilterChain` arbitrarily.

Log **hashed/pseudonymous account IDs** and correlation IDs if policy allows; never log raw passwords/tokens. Never use `Thread.currentThread()` values as identity.

### Step 3 — Inspect the Operator Graph

- Are there manual `subscribe()`, `block()`, `toFuture()`, `CompletableFuture`, or nested new `Mono`s subscribed separately?
- Is `contextWrite` placed **after the operators that need the value** in subscription order? Does an inner `flatMap` override context scope?
- Does `Mono.just(...)` read `SecurityContextHolder` at assembly time?
- Does a custom reactive filter build a new publisher without chaining the response or alter `SecurityContext` itself?
- Is a context-propagation bridge active, and which `ThreadLocal`s does it cover?

### Step 4 — Verify Security Invariants

- Never use "if auth is null then account=admin" or trust client-supplied `X-User-ID` headers.
- Never reuse a mutable singleton `Authentication` across requests.
- Never use global/inheritable `ThreadLocal` to "share `currentUser`" across pool threads.
- When work outlives the request, use a proper service principal plus audited request actor and reauthorize per policy; never keep a bearer token alive indefinitely.
- Any empty `SecurityContext` on a protected route must fail closed, never silently skip ownership checks.
- Verify `@PreAuthorize`, security matchers, and domain roles/tenants independently of propagation.

### Step 5 — Write the Minimal Reproduction Test

- Reactor test with two `StepVerifier` subscriptions (Alice/Bob) plus no-context case.
- `WebTestClient` test with real Basic through the WebFlux security chain and method security.
- Insert `publishOn(Schedulers.parallel())` between the request and context read.
- Test tasks on a single-thread pool to catch stale `ThreadLocal` (like the lab).
- Compare behavior with and without automatic context bridging; never assume default behavior.
- Finally run concurrent multi-subscriber/multi-thread load tests verifying cross-tenant isolation and authorization side effects.

## 15. Wrong Fixes That Typically Make Systems Less Secure

| Workaround | Why Never to Use It | Right Direction |
| --- | --- | --- |
| `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` | Global context shared across requests/users — extremely dangerous | `ReactiveSecurityContextHolder` in WebFlux |
| `MODE_INHERITABLETHREADLOCAL` on web servers | Thread pool reuse breaks thread-creation propagation | Context-aware execution, never share `ThreadLocal` |
| `SecurityContextHolder.getContext().setAuthentication(...)` from query username | Caller picks principal, bypassing authentication | Use trusted `AuthenticationManager`/WebFilter |
| `onErrorResume(e -> Mono.just("admin"))` when context missing | Fail-open | Fail closed with proper 401/403 |
| `Mono.just(SecurityContextHolder.getContext()...)` | Evaluates identity at assembly time | Use `ReactiveSecurityContextHolder`/`deferContextual` |
| `doWork().subscribe()` in controller | Detached subscription loses lifecycle/context | Return composed `Mono`/`Flux` |
| `Thread.sleep`/`block()` to force sync | Blocks event loop, hides races, hurts throughput | Reactive end-to-end or `boundedElastic` |
| Enabling automatic context hook and stopping there | Does not authenticate; accessors/versions/configs may be missing | Test actual bridge; keep business auth in Reactor Context |
| Copying entire `SecurityContext` onto a queue | Stale principals, leaked tokens, overly long privilege lifetime | Immutable audit identity + worker reauthorization |
| Using MDC principal for access decisions | MDC is for logging and can be stale/forged | Official `Authentication` + authorization |
| Forwarding bearer tokens on every `WebClient` call | Leaks tokens to services outside audience | OAuth token relay scoped by audience/scope |
| Testing only `@WithMockUser` | Does not prove password/token providers ran | HTTP Basic/OAuth integration tests |
| Disabling WebFlux security over HTTP 403 | Removes protection to hide errors | Diagnose EntryPoint/AccessDenied/CSRF |
| Putting `subscribeOn(boundedElastic())` around whole app | Moving everything to thread pools does not fix scoping | Offload only explicit blocking boundaries |

**Performance note:** Context propagation incurs runtime cost; measure latency/throughput under load and watch for thread-pool exhaustion. However, never optimize by skipping security checks or stashing account IDs in static mutable variables.

## 16. Completion Checklist

- [ ] Confirmed accurately whether the app runs Servlet or WebFlux and which security chain is active.
- [ ] In WebFlux, auth is read via `ReactiveSecurityContextHolder.getContext()` **inside the Publisher chain**, not via `ThreadLocal` `SecurityContextHolder`.
- [ ] Relevant `contextWrite` calls sit in the right subscription scope; `deferContextual` reads values at subscription time.
- [ ] No detached `subscribe()` in controllers/services when logic belongs to the HTTP security lifecycle.
- [ ] No `block()` on the Netty event loop; blocking I/O is offloaded to `boundedElastic` or replaced with reactive drivers.
- [ ] `CompletableFuture`/Executor/queue boundaries pass verified actor data explicitly and re-authorize on delayed execution.
- [ ] No `MODE_GLOBAL`, `InheritableThreadLocal`, or stale `ThreadLocal` used for authorization in multi-user requests.
- [ ] Micrometer/MDC bridging is used only with matching dependencies/accessors/hooks and cleanup; logs never authorize.
- [ ] `WebTestClient` tests real HTTP Basic: Alice stays Alice after scheduler hops; Admin allowed, Alice denied 403; anonymous 401.
- [ ] `StepVerifier` tests the same publisher with two subscribers seeing distinct principals, and unauthenticated subscriptions inheriting nothing.
- [ ] Context does not blindly relay Bearer tokens downstream; OAuth token relay is configured and scoped explicitly.
- [ ] Concurrent multi-tenant/multi-user tests pinpoint exact 401/403 origins with zero side effects on failure.
- [ ] Sensitive data never appears in logs, static fields, queue payloads, or test snapshots.
- [ ] For custom login/sessions, `ServerSecurityContextRepository` and reactive auth filters save/restore context across requests.
- [ ] Post-fix load tests confirm zero identity leakage across reused worker threads and no throughput regressions.

**Summary:** Reactor Context follows the **Subscriber and subscription**, not the **Thread**. In Spring WebFlux, use `ReactiveSecurityContextHolder`; switching Schedulers in an intact Reactor chain does not drop identity by itself, whereas reading `SecurityContextHolder` or using detached subscriptions/non-Reactor Executors can lose or leak `ThreadLocal`. Verify boundaries, compose pipelines cleanly, pass verified actors across external executors, and enforce authorization at execution time.

### Official Documentation and References

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Reactive WebTestClient Authentication Tests](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security 6.5 — Servlet SecurityContextHolder / ThreadLocal](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
