# Respecting the Reactive Contract and Avoiding Blocking Code in the Chain

> **Context:** Spring Security fundamentals, "Extension Points" group. This lesson focuses on **Spring WebFlux + reactive Spring Security** applications: when customizing authentication, authorization, account lookup, exception handling, or filters, you must preserve the `Mono`/`Flux` contract and avoid blocking the event loop. Examples use **Java 17, Spring Boot 3.3.x, Spring Security 6.x, and Reactor 3.6.x**. Servlet/Spring MVC applications use different interfaces and execution models; do not copy reactive examples to Servlet without adapting them.

## 1. What Truly Needs to Be Respected?

A reactive method does not become non-blocking merely because its return type is `Mono<T>` or `Flux<T>`. The logic **inside** the pipeline must itself avoid synchronous waiting calls: JDBC/JPA, `RestTemplate`, `Thread.sleep`, `Future.get`, blocking file I/O APIs, or `Mono.block()`.

In WebFlux, a small number of event-loop threads can serve many connections because work is expressed as **publishers**. When a request must wait on I/O, the publisher has not yet emitted a result; the event loop can serve other work. If custom security code holds an event-loop thread while waiting on a database, unrelated requests can also suffer increased latency.

Visual example:

```text
HTTP request
   |
   v
SecurityWebFilterChain (WebFlux)
   |
   +--> AuthenticationWebFilter / ReactiveAuthenticationManager
   |          |
   |          +--> Returns Mono<Authentication> (does not block to get Authentication)
   |
   +--> AuthorizationWebFilter / ReactiveAuthorizationManager
   |          |
   |          +--> Composes Mono<Authentication> with Mono<access decision>
   |
   +--> Handler/controller reacts to the result
              |
              v
        Mono/Flux completes, errors, or is cancelled
```

**The "reactive contract"** encompasses several interconnected properties:

1. **Lazy/deferred:** constructing a publisher does not mean performing all I/O immediately; most work starts upon subscription.
2. **Non-blocking:** do not occupy a thread solely waiting for network/database results in places that must remain non-blocking.
3. **Composition:** return the publisher so Spring Security and Reactor **compose** it into the pipeline; never call `subscribe()` yourself and return a dummy result.
4. **Clear signals:** value (`onNext`), completion without a value (`onComplete`), error (`onError`), and cancellation (`cancel`) carry distinct meanings.
5. **Per-subscriber context:** security data is propagated via **Reactor Context**; it does not live in a fixed `ThreadLocal` by default.
6. **Cancellation/timeout:** cancelled requests or timeouts should propagate to the data source if supported; work detached by a standalone `subscribe()` may keep running uncontrolled.
7. **Fail closed:** when permissions cannot be verified, never automatically grant access or return `true` to mask errors.

### Why Is "Wrapping with Mono.just" Not Enough?

```java
// WRONG — the JDBC call already ran and blocked the thread before Mono was created.
Mono<UserRecord> user = Mono.just(jdbcRepository.findUser(username));
```

```java
// WRONG — Mono is created upfront, yet the callback still runs blocking JDBC code
// on the thread executing the callback (which may be the event loop).
Mono<UserRecord> user = Mono.fromCallable(
    () -> jdbcRepository.findUser(username)
);
```

```java
// Temporary isolation if you must keep a synchronous JDBC adapter.
// Snippet is a fragment: jdbcRepository/UserRecord are project-defined.
Mono<UserRecord> user = Mono.fromCallable(
    () -> jdbcRepository.findUser(username)
).subscribeOn(Schedulers.boundedElastic());
```

The third example is only valid when you **actively isolate the synchronous source** onto a suitable scheduler. This is a transitional measure and **does not turn JDBC into reactive I/O**. JDBC connection pools and `boundedElastic` workers remain finite resources; production should prefer genuinely non-blocking APIs such as R2DBC or reactive HTTP clients where appropriate.

## 2. What Are Spring Security's Reactive Extension Points?

| Need | Reactive interface | Key contract |
| --- | --- | --- |
| Authenticate token/credential | `ReactiveAuthenticationManager` | `authenticate(Authentication)` returns `Mono<Authentication>`; emit result on success, may return `Mono.empty()` if unsupported, emit `onError` on auth failure |
| Extract credential from HTTP | `ServerAuthenticationConverter` | `convert(ServerWebExchange)` returns `Mono<Authentication>`; never invoke blocking data sources while parsing |
| Load account | `ReactiveUserDetailsService` | `findByUsername(String)` returns `Mono<UserDetails>`; empty when user is absent, `onError` on I/O errors |
| Make authorization decision | `ReactiveAuthorizationManager<T>` | `check(Mono<Authentication>, T)` returns `Mono<AuthorizationDecision>` in Spring Security 6.x; compose with `flatMap` |
| Save/load security context | `ServerSecurityContextRepository` | `load`/`save` and `SecurityContext` must honor the Mono contract, never touching blocking session stores on the event loop |
| Error requiring authentication | `ServerAuthenticationEntryPoint` | `commence(...)` returns `Mono<Void>` describing writing the response |
| Error authenticated but missing permission | `ServerAccessDeniedHandler` | `handle(...)` returns `Mono<Void>` |
| Authentication success/failure | `ServerAuthenticationSuccessHandler`, `ServerAuthenticationFailureHandler` | Return `Mono<Void>` tied to completing the response/chain |
| Additional web filter | `WebFilter` | `filter(exchange, chain)` returns `Mono<Void>` and uses `chain.filter(exchange)` properly |
| Reactive method security | `@EnableReactiveMethodSecurity`, `@PreAuthorize` | Relies on Reactor Context and methods returning an appropriate `Publisher` |

**Version note:** in Spring Security 6.x, the `ReactiveAuthorizationManager` interface defines `check` returning `Mono<AuthorizationDecision>`. When upgrading major versions, inspect the Java API of the exact version in use; do not blindly copy signatures from newer releases.

Important conventions:

- For **`ReactiveAuthenticationManager`**, `Mono.empty()` means the manager cannot decide/authenticate that token type; it **does not mean login succeeded**. Invalid credentials must emit an appropriate authentication error signal.
- For **`ReactiveUserDetailsService`**, a non-existent user may be represented by `Mono.empty()`; database/IdP errors must propagate `onError`, not be turned into an absent user.
- For **`ReactiveAuthorizationManager`**, a custom check should emit an **explicit true/false decision**. Never assume `Mono.empty()` means "deny" across all manager compositions.
- For `Mono<Void>`, no "void" value is emitted via `onNext`; what matters is that the publisher describes writing the response/error and completes at the right time.

## 3. Right and Wrong Ways to Implement an Authorization Decision

Suppose you must ask an entitlement service whether an account can read reports. A reactive service returns `Mono<Boolean>`:

```java
// Fragment: entitlementClient is a real reactive HTTP/database API.
Mono<Boolean> canRead(String username) {
    return entitlementClient.lookup(username)
        .map(record -> record.canReadReports())
        .switchIfEmpty(Mono.just(false));
}
```

The authorization check must **compose** the publisher, never pull the Boolean immediately with `block()`:

```java
// WRONG — can block the event loop or trigger a Reactor block() error.
// Assumes entitlementClient and authentication are already declared.
boolean allowed = entitlementClient.lookup(authentication.getName())
    .map(record -> record.canReadReports())
    .block();
return Mono.just(new AuthorizationDecision(allowed));
```

```java
// RIGHT — lambda illustrating ReactiveAuthorizationManager logic.
// authentication is Mono<Authentication>.
return authentication
    .flatMap(auth -> entitlementClient.lookup(auth.getName())
        .map(record -> new AuthorizationDecision(record.canReadReports())))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

When building a real manager, verify that `Authentication` is valid and do not rely solely on `isAuthenticated()`, because anonymous tokens can report an internal authenticated flag. The complete application sample in section 5 adds a check excluding `AnonymousAuthenticationToken`.

Common composition mistakes:

```java
// WRONG: map produces Mono<Mono<Boolean>> without unwrapping the inner async result.
// This is a fragment; authMono and entitlementClient must be defined.
Mono<Mono<Boolean>> nested = authMono.map(auth ->
    entitlementClient.canRead(auth.getName()));
```

```java
// RIGHT: flatMap flattens the child publisher's result into the shared chain.
Mono<Boolean> allowed = authMono.flatMap(auth ->
    entitlementClient.canRead(auth.getName()));
```

```java
// WRONG: subscribe() spawns a detached stream; returns true immediately,
// does not wait for permissions, and does not propagate errors/cancel to the request.
entitlementClient.canRead(username).subscribe(result -> audit(result));
return Mono.just(new AuthorizationDecision(true));
```

```java
// RIGHT: every step affecting the decision stays inside the publisher.
return entitlementClient.canRead(username)
    .map(AuthorizationDecision::new)
    .defaultIfEmpty(new AuthorizationDecision(false));
```

In the `subscribe()` fragment, `audit` is a hypothetical method; it is an **anti-pattern**, not a standalone runnable snippet. An auxiliary non-blocking logger/metric can use `doOnNext`, `doOnError`, or `doFinally`, yet **never use side effects to decide access grants**; the decision must come from the returned publisher.

### Choosing `map`, `flatMap`, `switchIfEmpty`, `onErrorResume`

| Operator | Use when | Security note |
| --- | --- | --- |
| `map(fn)` | Synchronous, fast transformation with no I/O wait | Never call blocking JDBC/HTTP inside `fn` |
| `flatMap(fn)` | `fn` returns `Mono<R>` such as permission lookup, token validation | Keeps async execution, errors, and cancellation inside the chain |
| `switchIfEmpty(other)` | Empty result needs a valid fallback | Never turn "no permission" into a default allow |
| `onErrorResume` | Classify/recover known errors | Never use `onErrorReturn(true)` or swallow all errors to grant access |
| `timeout(Duration)` | Bound wait duration | `TimeoutException` is not "user does not exist"; fail closed |
| `retryWhen` | Conditional retry for transient errors | Bound attempts/backoff; never blindly retry single-use authentication ops |
| `doOnError`/`doFinally` | Auxiliary metrics/logging, cleanup | Side effects must be lightweight and non-blocking |
| `subscribeOn` | Choose scheduler for subscription source, often to isolate blocking adapters | Place near `Mono.fromCallable` wrapping the blocking call |
| `publishOn` | Switch scheduler for downstream processing | Does not retroactively fix a blocking call that already ran upstream |

## 4. Why Are the Event Loop and Reactor Context Critical for Security?

### 4.1 Blocking degrades many requests

WebFlux on Reactor Netty typically uses an event loop with a bounded number of threads. When a handler/manager spends 200 ms waiting on JDBC, other tasks queued on that thread also slow down. Under heavy load, p95/p99 latency, timeouts, queues, and failed requests can spike. An API working "fine" in a low-traffic dev environment does not prove it is harmless under load.

Operations to audit on the authentication/authorization path:

- `Mono.block()`, `Flux.blockFirst()`, `Flux.blockLast()`, `blockOptional()`.
- `Thread.sleep`, `Object.wait`, `Future.get`, `CompletableFuture.join`.
- `RestTemplate`, `HttpURLConnection`, synchronous HTTP SDKs, blocking LDAP access.
- JDBC/JPA/`EntityManager`, JDBC session repositories, synchronous file I/O, long-held synchronized locks.
- Heavy password hashing/cryptography or heavy JSON mapping running directly on the event loop (CPU-intensive work, even without I/O waits).
- "Reactive" cache clients whose underlying implementation actually calls a synchronous SDK.

**Not every synchronous function is wrong.** Running `map` to compare an authority or read a field from an in-memory object is appropriate. The problem is blocking I/O, synchronous waiting, or prolonged computation that starves scheduler responsiveness.

### 4.2 SecurityContextHolder and ReactiveSecurityContextHolder

In Servlet apps, `SecurityContextHolder` typically relies on `ThreadLocal`. WebFlux can switch threads across `publishOn`, `flatMap`, or I/O callbacks; therefore reading the principal via `SecurityContextHolder.getContext()` inside a reactive callback easily yields an empty or wrong context.

Right in WebFlux:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

When a request passes through Spring Security WebFlux, the framework populates the proper context on Reactor Context. Never manually copy `SecurityContext` into `ThreadLocal` to "patch" a thread-switching bug.

To supply a context explicitly in a standalone unit test, you can write:

```java
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    "reader",
    "n/a",
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(username)
    .expectNext("reader")
    .verifyComplete();
```

This is a **unit test fragment**, requiring the matching Spring Security/Reactor Test/JUnit imports; it is not a standalone Java file. It demonstrates supplying context to a **subscription**. `contextWrite` serves Reactor Context; it does not make arbitrary `ThreadLocal` usage reliable across scheduler hops.

### 4.3 Do not manually subscribe inside filters/handlers

A `WebFilter` has the signature `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)`. Return `chain.filter(exchange)` or a publisher composed with it so the framework controls the lifecycle. Never call `chain.filter(exchange).subscribe()` and return `Mono.empty()`: writing the response can happen out-of-band, causing races, double commits, lost errors, or lost security context.

```java
// Fragment illustrating a valid filter without manual subscribe.
@Bean
WebFilter timingFilter() {
    return (exchange, chain) -> {
        long started = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signalType -> {
                long elapsedNanos = System.nanoTime() - started;
                // Only record lightweight metrics; never do blocking I/O here.
            });
    };
}
```

`doFinally` may execute on any Reactor thread; if a metric exporter is blocking, use a properly designed mechanism instead of letting the exporter block the event loop.

## 5. Runnable Spring Boot WebFlux Project: Mono-Based Authorization

The following example configures HTTP Basic, two demo accounts `reader` and `guest`, a `ReactiveAuthorizationManager<AuthorizationContext>`, and a simulated non-blocking entitlement service returning `Mono<Boolean>`. Using `Mono.delay` **only simulates an async result**; in real systems, replace it with WebClient/R2DBC/reactive SDKs. Access requires: real authentication, the READER role, and approval from the policy service. When no result is produced, the app denies by default.

### 5.1 Structure

```text
reactive-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/reactivesecurity/
    │   └── ReactiveSecurityDemoApplication.java
    └── test/java/com/example/reactivesecurity/
        └── ReactiveSecurityDemoApplicationTest.java
```

### 5.2 Maven — WebFlux only

Create `pom.xml`. Do not add `spring-boot-starter-web` to this example: when both Servlet MVC and WebFlux are on the classpath, Spring Boot may pick the Servlet stack depending on configuration, making you think you are testing reactive filters while the stack has changed.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-security-demo</artifactId>
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

### 5.3 Java source

Create `src/main/java/com/example/reactivesecurity/ReactiveSecurityDemoApplication.java`:

```java
package com.example.reactivesecurity;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();

        UserDetails guest = User.withUsername("guest")
            .password("{noop}demo123")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(List.of(reader, guest));
    }

    @Bean
    AsyncReportPolicy asyncReportPolicy() {
        return new AsyncReportPolicy();
    }

    @Bean
    ReactiveAuthorizationManager<AuthorizationContext> reportAuthorization(
            AsyncReportPolicy reportPolicy) {

        return (authentication, context) -> authentication
            .filter(auth -> auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken))
            .filter(auth -> auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())))
            .flatMap(auth -> reportPolicy.canReadReports(auth.getName()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    @Bean
    SecurityWebFilterChain filterChain(
            ServerHttpSecurity http,
            ReactiveAuthorizationManager<AuthorizationContext> reportAuthorization) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/me").authenticated()
                .pathMatchers("/secure/reports").access(reportAuthorization)
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Simulates an asynchronous dependency; never call Thread.sleep().
    static final class AsyncReportPolicy {
        Mono<Boolean> canReadReports(String username) {
            return Mono.delay(Duration.ofMillis(10))
                .map(tick -> "reader".equals(username));
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public ok");
        }

        @GetMapping("/secure/reports")
        Mono<String> reports() {
            return Mono.just("reports ok");
        }

        @GetMapping("/me")
        Mono<String> currentUser() {
            return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
        }
    }
}
```

### 5.4 Explaining Key Lines

1. **`MapReactiveUserDetailsService`** creates accounts in memory. `{noop}` is only for easy testing; plaintext passwords are unsafe in real products. Spring Security uses the reactive provider paired with `ReactiveUserDetailsService` to verify Basic credentials.
2. **`reportAuthorization`** receives a `Mono<Authentication>`. It filters out anonymous tokens, checks the configured authority, and uses **`flatMap`** into the policy call returning `Mono<Boolean>`. It never calls `block`, `subscribe`, JDBC, or synchronous HTTP.
3. **`new AuthorizationDecision(false)`** is the default when authentication or a result is absent. Granting rules are explicit; `Mono.empty()` is never treated as "allow".
4. **`Mono.delay`** does not block a thread for 10 ms; Reactor emits a signal after that duration. This is a **deliberate async simulation**, not to be mistaken for a real authorization system query.
5. **`/me`** reads the username from `ReactiveSecurityContextHolder`, demonstrating subscriber-bound context and preserving reactivity.
6. **HTTP Basic** handles missing credentials with a 401 challenge; authenticated users denied by policy normally receive 403. Failed permission lookups must never be turned into granted.
7. **CSRF is kept at its default**: the demo only has GET endpoints, so disabling it is unnecessary. When adding POST endpoints or session/cookie UIs, evaluate CSRF per the client model; never disable it by default just because a form POST returns 403.

### 5.5 Verifying Behavior over HTTP

From the project directory with `pom.xml`, requiring Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Open another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure/reports
curl -i -u guest:demo123 http://localhost:8080/secure/reports
curl -i -u reader:demo123 http://localhost:8080/secure/reports
curl -i -u reader:demo123 http://localhost:8080/me
```

| Request | Expected HTTP | Main body |
| --- | --- | --- |
| `GET /public` without credentials | 200 | `public ok` |
| `GET /secure/reports` without credentials | 401 | Basic challenge; not logged in |
| `GET /secure/reports` with `guest` | 403 | Logged in but lacking permission |
| `GET /secure/reports` with `reader` | 200 | `reports ok` |
| `GET /me` with `reader` | 200 | `reader` |

Headers like `Date` and framework-generated error bodies may vary; the table relies on the example's stable status codes and controller bodies. Observing the right status **does not by itself prove non-blocking execution**; you still need to inspect call paths and latency under load.

### 5.6 WebTestClient Testing 401/403/200 and Reactor Context

Create `src/test/java/com/example/reactivesecurity/ReactiveSecurityDemoApplicationTest.java`:

```java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousIsChallenged() {
        client.get().uri("/secure/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void guestIsDenied() {
        client.get().uri("/secure/reports")
            .headers(headers -> headers.setBasicAuth("guest", "demo123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerIsAllowed() {
        client.get().uri("/secure/reports")
            .headers(headers -> headers.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports ok");
    }

    @Test
    void reactiveContextContainsAuthenticatedUser() {
        client.get().uri("/me")
            .headers(headers -> headers.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }
}
```

These tests verify the HTTP route's security behavior. To confirm the custom async service behaves properly, add `StepVerifier` tests for `Mono<Boolean>`, error/timeout tests, and latency measurements under concurrent requests. The code examples above show how to run things yourself; they do not replace testing against your real project's environment and dependencies.

## 6. Replacing Simulation with Real I/O: Which APIs Should You Use?

| Security task | Reactive-friendly API | Avoid on the event loop |
| --- | --- | --- |
| Account lookup | `ReactiveUserDetailsService` + R2DBC/reactive driver | JPA/JDBC repository called directly inside `flatMap` |
| HTTP permission lookup | `WebClient` or non-blocking HTTP client | Synchronous `RestTemplate`, `HttpURLConnection` |
| Redis/session query | Reactive Redis client, `ReactiveRedisOperations` | Sync Redis client or blocking session store |
| Token verification with IdP | Matching reactive authentication manager/decoder/client | Calling a synchronous SDK inside a converter |
| Reading dynamic config/secrets | Async client or managed cached snapshot | Synchronous file/secrets read on every request |
| Password hashing/checking | Evaluate CPU cost and how Spring Security/providers schedule work | Running heavy hash loops arbitrarily on the event loop |

Example adapter calling a permission service with WebClient **(fragment; requires a `WebClient` bean and real API contract)**:

```java
record PermissionReply(boolean allowed) {}

Mono<Boolean> canReadReports(String username) {
    return webClient.get()
        .uri("/permissions/reports/{username}", username)
        .retrieve()
        .bodyToMono(PermissionReply.class)
        .map(PermissionReply::allowed)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Empty permission response")))
        .timeout(Duration.ofSeconds(2));
}
```

`WebClient` returns a publisher and requires no `block()`. By default `retrieve()` turns many 4xx/5xx responses into errors; **classify them** per the service contract—for instance, does 404 genuinely mean "no permission" or a wrong route? When the service times out, never grant access automatically. An "unable to check permissions" failure can be surfaced as a 5xx system error with safe logging, or denied as 403 if policy explicitly mandates deny-on-outage. Both approaches must **fail closed** and keep diagnostics internal.

If caching permissions, define TTL, tenant scope, invalidation, and revocation events. Stale caches can grant revoked permissions; "caching for speed" does not exempt revocation controls.

## 7. When Forced to Call a Blocking Library: How to Isolate Properly

Some systems have synchronous JDBC/LDAP/SDKs that cannot be replaced immediately. Transitional pattern with Reactor:

```java
// Fragment: legacyAccountStore is a synchronous project SDK/repository.
Mono<UserRecord> findUser(String username) {
    return Mono.fromCallable(() ->
            legacyAccountStore.findByUsername(username))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(2));
}
```

Using `fromCallable` defers executing the call until subscription; `subscribeOn(Schedulers.boundedElastic())` shifts blocking work onto a bounded worker pool instead of tying up the event loop. Never put the blocking call **outside** `fromCallable`, or it runs before the scheduler applies.

**Remaining limits and risks:**

- `boundedElastic` does not create "true non-blocking I/O"; each JDBC/LDAP call still occupies a worker thread while waiting.
- Workers/queues are bounded; if many requests wait on the database simultaneously, latency still rises or queues fill up.
- `timeout` on the publisher **does not guarantee interrupting an already-started JDBC call**; proper timeouts are needed at the driver, network, and pool levels.
- Bound concurrency and connection pools to realistic capacity, avoiding spawning extra requests merely because a dedicated scheduler is available.
- `publishOn(boundedElastic())` only switches **downstream**; if blocking happened upstream earlier, adding `publishOn` at the end does not save it.
- Never call `Schedulers.boundedElastic().schedule(...)` inside a manager and return allow immediately; that detaches work from the security flow.
- For heavy CPU-intensive work like hashing, review scheduler strategy and load limits; `boundedElastic` is mainly for blocking I/O, not a universal solution for every CPU workload.

The true long-term priority is migrating to R2DBC/reactive HTTP clients where supported. Never use a `Mono` wrapper to hide thread or pool design flaws.

## 8. Handling Errors, Timeouts, Retries, and Cancellation Without Weakening Security

A subtle part of reactive security is that **an asynchronous error is not the same as "no permission"**. For instance, if the entitlement service returns 503, the manager must still block the request from reaching the resource while alerting monitoring that the dependency is down.

### Distinguishing signals

| Signal in pipeline | Potential meaning | Safe handling |
| --- | --- | --- |
| `Mono.just(true)` from evidenced policy | Allowed per current rules | Return `AuthorizationDecision(true)` |
| `Mono.just(false)` | Policy disallows | Return `AuthorizationDecision(false)` |
| `Mono.empty()` from policy | No result / abstention | Define clearly and default to deny |
| `Mono.error(TimeoutException)` | Response not received in time | Fail closed, record outage metric |
| `Mono.error(WebClientResponseException)` | Service returned HTTP error | Classify 4xx/5xx per API contract; never grant |
| Request `cancel()` | Client aborted request or upstream timed out | Do not continue out-of-band granting side effects |

A dangerous anti-pattern:

```java
// WRONG — dependency failure automatically opens access.
return entitlementService.canRead(username)
    .onErrorReturn(true)
    .map(AuthorizationDecision::new);
```

A **fail-closed** option that still requires evaluating HTTP semantics:

```java
// Deny when the service errors; needs separate outage logging/metrics.
// Fragment: entitlementService/username are variables in scope.
return entitlementService.canRead(username)
    .onErrorResume(EntitlementUnavailableException.class, error ->
        Mono.just(false))
    .map(AuthorizationDecision::new);
```

Returning false during an outage can cause clients to receive 403 even though the root cause is a 5xx system failure. If the product requires clients to receive 503, let the exception reach a suitable server error handler and ensure it **does not** fall through to the resource handler. Do not turn every runtime error into a 403 deny by default and lose operational visibility.

### Bounding timeouts and retries

```java
// Illustrative fragment; retry only recognized transient failures.
// Client does non-blocking I/O; do not retry single-use operations
// like authorization-code exchange unless the protocol allows it.
return entitlementService.canRead(username)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(TransientEntitlementFailure.class::isInstance));
```

`Retry` requires importing `reactor.util.retry.Retry`; `TransientEntitlementFailure`/`EntitlementUnavailableException` in the fragments are **hypothetical application-defined domain types**, not built-in Spring Security classes. Retry only suitable operations, with bounds and backoff/jitter, without amplifying traffic when a dependency is failing.

**Cancellation:** never use a standalone `subscribe()` to dispatch permission checks; if the HTTP request is cancelled, the composed pipeline can propagate the cancel signal to `WebClient`/drivers. An already-started blocking call on `boundedElastic` may not stop immediately even if the subscriber cancels; manage this with timeouts at the source.

## 9. Common Mistakes in Reactive Extension Points

### Mistake 1 — Using Servlet interfaces in WebFlux

`HttpSecurity`, `SecurityFilterChain`, `OncePerRequestFilter`, `AuthenticationManager`, `UserDetailsService`, and `AccessDeniedHandler` are familiar Servlet-stack APIs. WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilter`, `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, and `ServerAccessDeniedHandler`. Concepts are similar, yet you cannot swap interfaces or cast them to make them work.

### Mistake 2 — Thinking `Mono.just(blockingCall())` is reactive

The argument to `Mono.just` is evaluated eagerly before the publisher is returned. If you must rescue a sync library, wrap it narrowly with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; best of all, replace it with a non-blocking client.

### Mistake 3 — Calling `block()` in `ReactiveAuthenticationManager` or `ReactiveAuthorizationManager`

`block()` waits immediately, destroying event-loop concurrency and potentially throwing `IllegalStateException` on threads marked non-blocking by Reactor. Return the authentication/authorization `Mono` so the framework subscribes in the proper context.

### Mistake 4 — Using `subscribe()` or a separate callback to grant permissions

Writing `permissionMono.subscribe(allowed -> allowedFlag.set(allowed))` and immediately returning an `AuthorizationDecision` from the flag introduces a race condition. The right way is `permissionMono.map(AuthorizationDecision::new)` directly in the authorization chain.

### Mistake 5 — Equating `Mono.empty()` with success

`Mono.empty()` emits no element; across extension points it can mean "token not supported", "user not found", or "no decision rendered". Interpret it per each contract, default to deny in authorization where appropriate, and never convert failed lookups into empty to hide backend outages.

### Mistake 6 — Abusing `onErrorResume`

`onErrorResume(error -> Mono.just(true))` is **fail-open**. `onErrorResume(error -> Mono.empty())` can also be wrong if downstream uses a permissive default or turns an outage into a missing user. Handle known exceptions selectively and preserve root cause/metrics to detect incidents.

### Mistake 7 — Accessing `SecurityContextHolder` from reactive callbacks

Thread changes are normal. Use `ReactiveSecurityContextHolder`/Reactor Context. With reactive method security, keep return types Reactor-compatible and enable `@EnableReactiveMethodSecurity` when needed; never put `.block()` inside SpEL or permission services.

### Mistake 8 — Assuming offloading is infinite

`boundedElastic` is a bounded scheduler and can still saturate. Offloading everything to a scheduler only masks architectural issues. Never use `parallel()` to run JDBC; `Schedulers.parallel()` is for short CPU tasks, not blocking I/O.

### Mistake 9 — Ignoring errors from the IdP or permission service

An HTTP 503 or token endpoint timeout is a dependency failure, not valid permission. Return an appropriate HTTP status without leaking tokens, users, stack traces, or tenant details. Do not let a custom filter commit a response early and let the chain write a second time.

### Mistake 10 — Testing only status codes, not latency or cancellation

A handler using `block()` can still return the right 200, 401, and 403 in single-request tests. Add tests simulating slow dependencies, timeout errors, concurrency, subscriber cancellation, and detection of event-loop stalls.

## 10. Testing and Observing the Reactive Contract

A high-value QA checklist for reactive Security extension points:

1. **Verify stack type:** the app genuinely runs Spring WebFlux; no Servlet starter accidentally caused Spring Boot to pick MVC.
2. **Functional behavior:** anonymous callers normally receive 401 when login is required, authorized accounts receive 200, and accounts lacking permissions receive 403.
3. **Context:** `ReactiveSecurityContextHolder` reads the right authentication after the pipeline switches schedulers.
4. **Dependency failures:** user service/entitlement/IdP timeouts or errors must not grant permissions; internal logs/metrics distinguish the cause.
5. **Non-blocking check:** grep directly for `block()`, `subscribe()`, JDBC/JPA, `RestTemplate`, `Thread.sleep`, `get()/join()` in security code and deeply invoked helpers.
6. **Concurrent load:** simulate concurrent requests; monitor event-loop threads, p95/p99 latency, Reactor Netty connection pools, `boundedElastic` queues, and latency to IdP/databases.
7. **Cancellation:** abort requests before completion and check whether cancellation propagates to supporting clients/drivers; no detached tasks continue granting access.
8. **Sensitive data:** never log raw passwords, Basic Authorization headers, access/refresh tokens, session cookies, signing keys, or stack traces sent to clients.
9. **API conformance:** review exact signatures of `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, `ServerAuthenticationConverter`, and handlers for your actual Spring Security version.

You can use **BlockHound** in test environments to detect many blocking operations on non-blocking threads, provided Java/Reactor/BlockHound versions are compatible. It is a **supplementary tool** and does not catch every blocking call or performance issue; combine static code review, integration tests, and load testing for high confidence.

With `StepVerifier`, verify success/error/empty/timeout publisher behavior. With `WebTestClient`, verify the full HTTP contract. The test examples in section 5 prove the 401/403/200 paths; adding tests when permission checks fail is the responsibility of real adapters to prevent fail-open bugs.

## 11. Checklist for Reviewing a Custom Security Extension

When adding a new authentication/authorization mechanism to WebFlux:

1. **Pick the right hook:** parse credentials with `ServerAuthenticationConverter`, authenticate with `ReactiveAuthenticationManager`, authorize with `ReactiveAuthorizationManager`; use reactive exception handlers. Do not dump all logic into a hand-written `WebFilter` when the framework already provides hooks.
2. **Map the I/O paths:** which libraries read accounts, tokens, roles, tenants, sessions, JWKs, or entitlements? Where could synchronous waiting or thread blocking occur?
3. **Switch to true reactive clients** whenever possible; otherwise isolate blocking sources with `fromCallable + boundedElastic`, bound resources, and record technical debt.
4. **Enforce fail-closed policies:** empty results, invalid tokens, timeouts, service errors, and cancellations must never default to allow.
5. **Compose the full pipeline:** return `Mono`/`Flux`, use `flatMap` for I/O, never manually `subscribe` or `block`. Read security context via Reactor Context.
6. **Separate responses and observability:** clients receive sensible HTTP statuses, the system captures root causes/metrics, and credentials are never leaked.
7. **Write tests:** at minimum anonymous, insufficient permissions, sufficient permissions, slow/broken dependencies, cancellation if side effects exist, and concurrent load if throughput is affected.

## 12. Conclusion

- **Returning `Mono` is not enough:** operations inside the security chain must also be non-blocking or isolated at proper boundaries.
- **`flatMap` composes asynchronous calls**, while `block()` breaks the chain; `subscribe()` in a filter/manager can detach permissions, errors, and cancellation from the request.
- **Spring Security WebFlux uses reactive hooks and Reactor Context**, not Servlet's `ThreadLocal SecurityContextHolder` by default.
- **Fail closed** when credentials/permissions cannot be verified; classify empty, false, error, and timeout strictly per contract.
- `boundedElastic` is a bounded bridge for blocking APIs; prefer R2DBC, `WebClient`, and reactive SDKs for new systems.
- Test **security semantics, error/timeout behavior, non-blocking execution, and behavior under high load**.

## Official Reference Documentation

- Spring Security — Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive Method Security and Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security 6.3 API — `ReactiveAuthorizationManager`: https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Project Reactor — Reactor 3 Reference Guide, FAQ "How Do I Wrap a Synchronous, Blocking Call?": https://projectreactor.io/docs/core/release/reference/
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html