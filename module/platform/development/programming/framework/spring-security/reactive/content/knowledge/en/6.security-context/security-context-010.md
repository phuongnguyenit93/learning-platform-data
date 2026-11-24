# Preventing identity leakage across concurrent requests

**Module:** Spring Security – Reactive · **Section:** Security context.

In Spring WebFlux, many HTTP requests from different users can be processed interleaved on a small number of event-loop threads; a single pipeline can also resume on another thread after `delay`, `publishOn`, or an async I/O call. Storing user identity in a singleton field, `static` variable, manually managed `ThreadLocal`, or an improperly shared Publisher can cause **Alice's** request to read **Bob's** details. This is a **cross-request identity leak**, which can lead to data exposure or broken authorization.

The core solution is to let Spring Security bind `SecurityContext` to the **corresponding subscription's Reactor Context**, read identity via `ReactiveSecurityContextHolder` inside the reactive chain, and never turn that information into shared state unpartitioned by user.

This lesson explains the mechanism, contrasts wrong and right code patterns, provides a runnable Java 17+ application, and builds a `WebTestClient` test suite that fires concurrent requests to detect identity mixing.

## 1. Stating the problem accurately

Suppose two clients send requests nearly concurrently:

```text
Client A (Authorization: Basic alice:...)       Client B (Authorization: Basic bob:...)
                  |                                                |
                  v                                                v
           Request A /api/delayed                         Request B /api/delayed
                  |                                                |
          authenticated = Alice                          authenticated = Bob
                  |                                                |
                 [async wait, multiple signals interleaved on event-loop]
                  |                                                |
                  v                                                v
            response "Alice"                               response "Bob"
```

**Invariant to maintain:** Every step using identity in request A must reference **A's valid Authentication**; every step in request B must reference **B's Authentication**, regardless of execution order, executing thread, delay, request count, or subscription count. A must never return B's result, and vice versa.

Separate three questions:

1. **Who authenticates?** Spring Security authenticates each request using HTTP Basic, Bearer token, session, or the configured mechanism; success produces an `Authentication`.
2. **Where is identity held?** In reactive programming, the security context is provided via `ReactiveSecurityContextHolder` and the subscriber-bound Reactor `Context`; a request does not own a fixed dedicated thread.
3. **When does business code read identity?** It must read inside **the pipeline of the request being subscribed**, after security filters prepare the context, rather than reading a value written earlier to shared memory.

Leaks can occur even when the application returns `200` normally: Alice's request receiving Bob's data is a far more severe violation than returning an error status. Therefore, testing only `200/401/403` is **insufficient**; you must assert the **exact principal, exact resource, and exact tenant**.

## 2. Why is ThreadLocal not a reliable identity source in WebFlux?

In traditional Servlet applications, a request typically occupies one thread while being processed. Servlet Spring Security can use `SecurityContextHolder` with a `ThreadLocal` strategy. In WebFlux, however:

- One event-loop thread serves many requests at interleaved times.
- `Mono.delay` or many operators reschedule execution onto another scheduler.
- `flatMap` can interleave multiple inner Publishers; order and threads do not necessarily follow sequential Java flow.
- Async tasks, retries, cancellation, and scheduling can make the running thread differ from the thread where the request entered.

`ThreadLocal` binds data to a **thread**, whereas security must bind to a **request/subscription**. An uncleaned `ThreadLocal` can leak an earlier request's info to a later task on the same thread; a `ThreadLocal` without propagation can return `null` on thread switches. Switching to `InheritableThreadLocal` does not properly handle thread pools or arbitrary async tasks.

For Spring Security Reactive, use:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

This is a **fragment** (requiring imports and Spring Security Reactive context) returning `Mono<String>`; it **does not** read a global variable when creating the Publisher. When subscribed in a proper pipeline, it receives the corresponding subscriber's context. Never replace it with Servlet-style `SecurityContextHolder.getContext().getAuthentication()` to make access decisions in WebFlux.

**Distinction:** Some Reactor versions/configs support converting Reactor Context ↔ `ThreadLocal` for tracing/MDC via Micrometer Context Propagation; that does not turn arbitrary `ThreadLocal` variables into a safe security identity source. If integrating a legacy library using `ThreadLocal`, configure explicit accessors, clear restore/cleanup scopes, test, and assess impact separately.

## 3. How does Reactor Context isolate per subscriber?

Reactor `Context` is an **immutable** key/value set from the caller's perspective: `put` yields a new context without mutating the old object in place. Each `Subscriber` has its own context; subscription signals travel from downstream to upstream so operators can read the required context.

- `contextWrite(...)` attaches/adjusts context for **operators upstream** of it in the current subscription.
- `Mono.deferContextual(ctx -> ...)` reads `ContextView` when subscription occurs, not immediately at assembly time.
- `ReactiveSecurityContextHolder.getContext()` reads `SecurityContext` from the Reactor Context provided by Spring Security Reactive.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)` creates a context containing `Authentication`, useful for **tests or already-trusted pipelines**. Never use it to let clients pick users via a self-declared header.

Pure Reactor example to understand isolation (fragment):

```java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("user=" + ctx.get("user")));

Mono<String> alice = message.contextWrite(ctx -> ctx.put("user", "alice"));
Mono<String> bob   = message.contextWrite(ctx -> ctx.put("user", "bob"));
```

Subscribing to `alice` emits `user=alice`; subscribing to `bob` emits `user=bob`. Deriving both from **the same `message` object** does not mix contexts because each subscription has its own context. Conversely, if `message` is `cache()`d after attaching user-specific data and shared across everyone, the cached result can break isolation.

### 3.1. Position of contextWrite matters greatly

```java
// Reads "alice": contextWrite is downstream of the read segment.
Mono<String> good = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("user")))
    .contextWrite(ctx -> ctx.put("user", "alice"));

// Misplaced fragment: trailing flatMap does not see the new key.
Mono<String> misplaced = Mono.just(1)
    .contextWrite(ctx -> ctx.put("user", "alice"))
    .flatMap(i -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("user", "missing"))));
```

`good` emits `alice`; `misplaced` emits `missing` upon subscription (assuming no prior `user` key exists). Context travels along the **subscription** path, not as a global variable carried with every `onNext` signal. Operators creating inner Publishers have their own context rules; when bridging context into a detached flow, design an explicit connection.

## 4. Anti-patterns that leak identity

### 4.1. Mutable field in a singleton Spring bean

**Wrong:**

```java
@Service
class UnsafeGreetingService {
    private volatile String lastUser;

    Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .doOnNext(name -> lastUser = name)
            .then(Mono.delay(Duration.ofMillis(40)))
            .map(ignored -> "hello " + lastUser);
    }
}
```

This is an **intentionally unsafe illustrative snippet**; import Spring/Reactor types if trying it separately. `@Service` is a singleton by default. Alice's request sets `lastUser="alice"`, then waits; Bob's request sets `lastUser="bob"`; when Alice resumes, Alice can return `hello bob`. `volatile` only makes writes visible across threads—it **does not** isolate users. `synchronized` or `static` variables are also wrong models for storing a request's principal.

**Right: keep each subscription's name in local data flow.**

```java
@Service
class SafeGreetingService {
    Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .flatMap(name -> Mono.delay(Duration.ofMillis(40))
                .map(ignored -> "hello " + name));
    }
}
```

Each subscriber has its own `name` variable inside its lambda. After reading context, `flatMap` keeps the corresponding value for the async branch. Nothing is written to bean fields, static variables, or shared mutable objects. Both snippets above are **contrasting examples**, not the two required classes of the runnable app in section 5.

### 4.2. Caching a Publisher holding principal or user-specific data

**Wrong:**

```java
@Service
class UnsafeIdentityCache {
    private final Mono<String> cachedUser =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .cache();

    Mono<String> currentUser() {
        return cachedUser;
    }
}
```

`cache()` stores the signals from the first subscription and replays them to subsequent subscribers. If a singleton holds `cachedUser`, Alice can populate the cache first, and then Bob reads Alice's name. Protecting the endpoint with `authenticated()` does not prevent **content mixing after authentication**.

**Right for identity data:** create a context-reading source per subscription without shared caching:

```java
Mono<String> currentUser() {
    return Mono.defer(() -> ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName));
}
```

The snippets here are illustrated inside a bean with imports present. When caching business data, design keys by verified identity **and corresponding data/permission/tenant scope**, with TTL and invalidation rules; never cache sensitive `Authentication` app-wide just for performance optimization. Beware of `share()`, `publish().refCount()`, hot `Sinks.Many`, and singleton-scoped publishers: they can emit data to multiple different subscribers.

### 4.3. Manual subscribe() creating a flow detached from the request

**Wrong:**

```java
@GetMapping("/notify")
Mono<String> notifyUser() {
    service.notifyCurrentUser().subscribe(); // detached from request
    return Mono.just("accepted");
}
```

This is an intentionally wrong fragment (the app would define `service`). Calling `subscribe()` manually creates a new subscription that can lose the HTTP request's security context; exceptions and cancellation no longer travel with the response. If the job reads ThreadLocal inside, it can pick up the wrong identity, or `ReactiveSecurityContextHolder.getContext()` can return empty.

**Right:** compose the task into a chain returned to WebFlux:

```java
@GetMapping("/notify")
Mono<String> notifyUser() {
    return service.notifyCurrentUser()
        .thenReturn("accepted");
}
```

This is also a fragment; this outcome only fits if the API needs to **wait for the task to complete** before returning the response. If a true background job is needed, model a job/queue, explicitly pass **verified identity and minimal authorization info**, re-verify permissions where the job executes, and enforce idempotency/monitoring. Never rely on a completed request's Reactor Context to grant permissions forever afterward.

### 4.4. Reading username from client-sent headers

`X-User: alice`, `X-Role: ADMIN`, or query parameter `?user=alice` does not prove the caller is Alice. Only a **trusted, verified, and properly configured** reverse proxy/API gateway can forward identity with guarantees; at the application boundary, prevent client header spoofing. In normal WebFlux apps, use the `Authentication` constructed by Spring Security from valid credentials.

### 4.5. Using request A's data to authorize request B

Avoid storing Alice's `SecurityContext` or `Authentication` in a singleton/map without a clear lifecycle; avoid storing a `ServerWebExchange` or mutable request object for work shared across requests. Never keep references to bearer tokens, passwords, or cookies in caches/service fields for reuse.

## 5. Runnable Java 17+ application to observe identity isolation

The example creates a Spring Boot WebFlux app with two test users `alice` and `bob`. Both endpoints require Basic auth:

- `GET /api/identity` returns `now:alice` or `now:bob` from the current security context.
- `GET /api/delayed` uses `Mono.delay` to switch scheduling before reading context, returning `later:alice` or `later:bob`. Concurrent clients must still receive their own identity.

The example uses Spring Boot `3.5.16` and JDK 17+. The version is a specific compilation pin; in production deployments, pick a supported version with the latest security patches per project policy.

### 5.1. Project structure

```text
reactive-context-isolation/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/isolation/
    │   │   ├── IsolationApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── IdentityService.java
    │   │   └── IdentityController.java
    │   └── resources/application.properties
    └── test/java/demo/isolation/
        └── IdentityIsolationTests.java
```

`pom.xml`:

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
    <artifactId>reactive-context-isolation</artifactId>
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

Use only the WebFlux starter; `spring-boot-starter-web` (Spring MVC) is not needed. `reactor-test` is used to verify per-subscriber context with `StepVerifier`. No database is needed.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-context-isolation
server.port=8080
```

### 5.2. Entry point

`src/main/java/demo/isolation/IsolationApplication.java`:

```java
package demo.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

### 5.3. Two accounts and one security chain

`src/main/java/demo/isolation/SecurityConfig.java`:

```java
package demo.isolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob123")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/identity", "/api/delayed")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

- Both users share the `USER` role to remove role differences from the experiment: what is being tested is **the exact identity** in the response.
- HTTP Basic lets each test client send its own credentials for direct observation. `{noop}` is plaintext password encoding, **only for local practice**; production must use password hashing/secret storage, HTTPS, and proper authentication configuration.
- `authenticated()` blocks unauthenticated requests; `anyExchange().denyAll()` avoids accidentally exposing other endpoints. Never let clients pick identities via self-declared headers.
- `.formLogin(login -> login.disable())` avoids login-page redirects when testing HTTP Basic. If a real project uses sessions/form login, test session security context persistence and per-client cookie isolation.

### 5.4. Service storing no user state

`src/main/java/demo/isolation/IdentityService.java`:

```java
package demo.isolation;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> current(String stage) {
        return Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Missing reactive security context")))
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> stage + ":" + name)
        );
    }
}
```

`@Service` is a singleton, yet **has no mutable field holding the principal**. On each subscription to `current(...)`, `Mono.defer` requests reading `SecurityContext` from that subscription's active context. If context is missing, the pattern fails explicitly with an error instead of silently falling back to a default identity or leaking a prior user. The service class never caches a `Mono` holding a username.

### 5.5. Controller switching schedulers while preserving identity

`src/main/java/demo/isolation/IdentityController.java`:

```java
package demo.isolation;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class IdentityController {

    private final IdentityService identities;

    public IdentityController(IdentityService identities) {
        this.identities = identities;
    }

    @GetMapping(value = "/identity", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> identity() {
        return identities.current("now");
    }

    @GetMapping(value = "/delayed", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(40))
            .then(identities.current("later"));
    }
}
```

`Mono.delay` uses Reactor's scheduler to emit a signal after the delay. `then(...)` continues in **the same reactive subscription tree**, so reading `ReactiveSecurityContextHolder.getContext()` still sees the right security context. There is no need to know or pin thread names; correctness rests on the subscriber's context, not on an "Alice thread".

You can also use `publishOn(Schedulers.parallel())` or a reactive repository returning `Mono` to demonstrate thread switches. They do not drop Reactor Context when composed normally in the same pipeline. However, jumping out of Reactor with `CompletableFuture.supplyAsync(...)` or spawning tasks in an `ExecutorService` and reading `ThreadLocal` is **a different boundary**, requiring explicit passing of verified data or an appropriate propagation mechanism.

## 6. Testing per user with curl

Requires JDK 17+, Maven, and port 8080 free. From the project directory:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Open another terminal:

```bash
curl -i http://localhost:8080/api/identity
curl -i --user alice:alice123 http://localhost:8080/api/identity
curl -i --user bob:bob123 http://localhost:8080/api/identity
curl -i --user alice:alice123 http://localhost:8080/api/delayed
curl -i --user bob:bob123 http://localhost:8080/api/delayed
curl -i --user alice:wrong http://localhost:8080/api/identity
```

Under the example configuration, the corresponding statuses/bodies:

| Request | Expected |
| --- | --- |
| Anonymous `/api/identity` | `401 Unauthorized` (Basic challenge) |
| Alice `/api/identity` | `200`, exact body `now:alice` |
| Bob `/api/identity` | `200`, exact body `now:bob` |
| Alice `/api/delayed` | `200`, exact body `later:alice` |
| Bob `/api/delayed` | `200`, exact body `later:bob` |
| Wrong password | `401 Unauthorized` |

Note the difference between **authentication** and **no leakage**: both Alice and Bob pass `authenticated()` and get `200`. You must compare the body against the authenticated principal to catch a bug where "Alice receives Bob's name". On older PowerShell, you may need `curl.exe` to invoke the real curl binary.

Try spoofing a header while still using Alice's Basic auth:

```bash
curl -i --user alice:alice123 \
  -H "X-Authenticated-User: bob" \
  http://localhost:8080/api/delayed
```

The result must be `later:alice`, because the controller reads identity from Spring Security, not from an untrusted header. Never put real passwords/tokens into shell history or logs; outside localhost, use HTTPS because Basic does not encrypt credentials itself.

## 7. WebTestClient testing concurrency, bad credentials, and per-subscriber Context

This is the most important part for turning "no leaks" into a measurable requirement. Using `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot runs a real WebFlux server on a random port; `WebTestClient` sends HTTP requests with Basic auth to that server. There is no need to run `mvn spring-boot:run` separately before running the tests.

`src/test/java/demo/isolation/IdentityIsolationTests.java`:

```java
package demo.isolation;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IdentityIsolationTests {

    @Autowired
    WebTestClient client;

    private void expectIdentity(
        String username, String password, String path, String prefix
    ) {
        client.get()
            .uri(path)
            .headers(headers -> headers.setBasicAuth(username, password))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo(prefix + ":" + username);
    }

    @Test
    void rejectsAnonymous() {
        client.get().uri("/api/identity")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongPassword() {
        client.get().uri("/api/identity")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void keepsEachUserInSequentialRequests() {
        expectIdentity("alice", "alice123", "/api/identity", "now");
        expectIdentity("bob", "bob123", "/api/identity", "now");
        expectIdentity("alice", "alice123", "/api/identity", "now");
    }

    @Test
    void retainsIdentityAfterAsyncDelay() {
        expectIdentity("alice", "alice123", "/api/delayed", "later");
        expectIdentity("bob", "bob123", "/api/delayed", "later");
    }

    @Test
    void ignoresSpoofedIdentityHeader() {
        client.get().uri("/api/delayed")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .header("X-Authenticated-User", "bob")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("later:alice");
    }

    @Test
    void parallelRequestsDoNotExchangeIdentity() {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<CompletableFuture<Void>> tasks =
                IntStream.range(0, 40)
                    .mapToObj(index -> CompletableFuture.runAsync(() -> {
                        boolean even = index % 2 == 0;
                        String username = even ? "alice" : "bob";
                        String password = even ? "alice123" : "bob123";
                        expectIdentity(
                            username, password, "/api/delayed", "later");
                    }, pool))
                    .toList();

            CompletableFuture.allOf(
                tasks.toArray(new CompletableFuture[0])
            ).join();
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void onePublisherSupportsDifferentSubscriberContexts() {
        Mono<String> current = ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);

        Authentication alice = new TestingAuthenticationToken(
            "alice", "unused", "ROLE_USER");
        Authentication bob = new TestingAuthenticationToken(
            "bob", "unused", "ROLE_USER");

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();
    }
}
```

Run:

```bash
mvn test
```

If the project contains only this test class, **7 passing tests** are expected; runtime, test order, and Maven logs depend on the machine. When tests fail, inspect the expected/actual assertions alongside security filters and request headers rather than guessing from unordered Reactor log lines.

### 7.1. What the tests prove

- `rejectsAnonymous` and `rejectsWrongPassword`: protected endpoints enforce credentials properly rather than picking principals from arbitrary request headers.
- `keepsEachUserInSequentialRequests`: a single `WebTestClient` switching credentials Alice → Bob → Alice still receives the right response for each request.
- `retainsIdentityAfterAsyncDelay`: Reactor rescheduling does not lose identity or switch it to another user.
- `ignoresSpoofedIdentityHeader`: a forged `X-Authenticated-User` header does not change `Authentication`.
- `parallelRequestsDoNotExchangeIdentity`: 40 requests from 8 client threads with interleaved credentials; each assertion checks **both 200 and the body matching the user's name**. `CompletableFuture.allOf(...).join()` turns assertion failures on worker threads into test failures instead of swallowing errors.
- `onePublisherSupportsDifferentSubscriberContexts`: the same `Mono<String>` object can read two separate contexts when subscribed on two independent branches. `withAuthentication(...)` is used **only in controlled tests**, never giving HTTP clients the ability to specify identity.

**Practical limits of concurrency tests:** 40 requests cannot prove a race condition is impossible under every execution schedule; the test is a valuable regression check, so vary delays/request counts appropriately in CI, monitor intermittent failures, and review code for mutable shared state. Avoid abusing sleep to "force" bugs to reproduce. With HTTP client/server, requests run concurrently even though each inner assertion is synchronous on its client thread.

### 7.2. Why StepVerifier cannot replace HTTP integration tests

`StepVerifier` accurately tests Reactor Context semantics for standalone Publishers; it does not prove Spring Security authenticated the HTTP request, loaded the right security filters, or mapped endpoints properly. `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` exercises the real HTTP path. Use both for two distinct layers of evidence.

Using `WebTestClient.bindToController(...)` directly may omit security filters from the test. Using `@WebFluxTest` requires verifying that security configurations/beans are properly imported. Avoid tests where every request passes a mocked `Authentication` outside the network and then concluding real HTTP authentication is safe. With `RANDOM_PORT`, send credentials over HTTP as above.

## 8. Preserving identity across async boundaries and thread switches

| Case | What to do | What to avoid |
| --- | --- | --- |
| `map`, `flatMap`, `then`, `delay` in the same Reactor chain | Read `ReactiveSecurityContextHolder` or carry username as a branch value | Writing user into a singleton field and reading after delay |
| `publishOn`, `subscribeOn` with standard Reactor operators | Subscriber's Reactor Context stays on the chain | Relying on thread names to identify users |
| `retry`, `repeat` | Verify identity/permissions per subscription and design idempotency | Assuming single execution or single context read |
| `Flux.share()` / `Mono.cache()` / `Sinks.Many` | Share only identity-independent data or partition keys properly | Caching/sharing results carrying the first user's principal |
| `CompletableFuture` / `ExecutorService` outside the chain | Pass verified identity/tenant explicitly if needed | Expecting `ReactiveSecurityContextHolder` or ThreadLocal to appear in new threads |
| HTTP client calling another service (`WebClient`) | Use trusted, scoped token/claim forwarding | Reusing a prior request's Authorization header or a global mutable token |
| Correlation ID logs / tracing | Use Reactor Context and proper MDC integration if needed | Storing tokens/PII in ThreadLocal without cleanup |

**Data-safe example** when calling an async service that does not support Reactor Context natively:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .flatMap(username -> otherClient.fetchForUser(username));
```

This fragment assumes `otherClient.fetchForUser(String)` is an **already safely designed API** and the remote server does not trust arbitrary client-sent usernames. In real systems, never treat a passed username string as authentication proof. The target service must verify signed/authorized tokens (or use a secured internal channel) and enforce resource permissions; avoid "client declares itself admin" designs.

### 8.1. ThreadLocal and MDC for logging

Many logging libraries use MDC, which relies on `ThreadLocal`. Logging before/after `publishOn` without an appropriate context propagation mechanism can lose the correlation ID or leak it to another signal. You can use Micrometer Context Propagation integration with `tap`/`handle` operators or automatic propagation depending on your Reactor version; test the exact configuration and clean up ThreadLocals within the proper scope. Remember **MDC is solely for observability**, never an authority to access data. Avoid putting passwords, tokens, full PII, or raw `SecurityContext` into logs.

### 8.2. Distinguishing a request's security context from longer-lived tasks

Once a request returns a response or is canceled, you cannot rely on that request's context for an unbounded background job. A job tagged "created by Alice" does not mean Alice still holds permissions when the job runs. Pass verified identity ID, request ID, and minimal metadata; when the job executes, perform fresh authorization per policy and avoid expired tokens or sharing tokens across jobs.

## 9. Never confuse right identity with right data authorization

A service can read `alice` accurately yet still return Bob's resource if queries fail to filter by owner. Leak protection therefore has two layers:

1. **Preserve principal:** every subscription reads its request's true `Authentication`.
2. **Enforce resource permissions:** queries/business layers restrict resources by principal and tenant, rather than relying solely on `authenticated()` at the endpoint.

Example fragment in a service with a repository designed for owner-scoped access:

```java
Mono<Report> myReport(String reportId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            repository.findByIdAndOwnerUsername(reportId, username))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
```

Import `Report`, `repository`, `HttpStatus`, and `ResponseStatusException` in a concrete application; this is not a standalone Java file. The method assumes the repository filters ownership **at the data source**. With multi-tenancy, also enforce tenant ID and contextual admin rights; never just call `findById(reportId)` assuming an authenticated endpoint suffices. `@EnableReactiveMethodSecurity`/`@PreAuthorize` can serve as an auxiliary layer when invoked through a Spring proxy, yet does not replace record-level authorization checks.

### 9.1. Avoid placing the whole SecurityContext in a cache

`Authentication` can hold authorities, credentials, and details. Storing or logging the whole object increases exposure risk; auth state can also change when permissions are revoked. Cached data should have explicit keys, TTLs, invalidation, and ownership, retaining only truly needed fields. Never use a global `Mono<Authentication>` to "optimize principal lookup".

### 9.2. Client sessions/cookies and tokens

Two browser tabs sharing one valid session cookie are **the same user** by design; that is not proof Spring mixed Reactor Contexts. Conversely, a test reusing a session cookie across two accounts can yield a false positive. When measuring isolation, create independent clients/sessions or use separate HTTP Basic/tokens per request, documenting the auth scheme and credential lifetimes.

For shared accounts (service accounts), differing principals may not reflect the end user's identity. Explicitly define what identity needs protection: user, tenant, service principal, delegated authorization, or the full delegation chain. Never accept an arbitrary `X-User` as proof.

## 10. Symptoms and troubleshooting workflow

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Alice gets a body with Bob's name; both `200` | Mutable field, `static`, cached Publisher, broken context bridge | Add concurrent tests per principal; search for `Authentication`/username stored in singletons |
| Principal becomes `null` on thread switch | Relying on `ThreadLocal` instead of Reactor Context | Read via `ReactiveSecurityContextHolder` in pipeline; inspect async split points |
| Fails only when requests run in parallel | Race condition in shared state | Repeat Alice/Bob test with controlled delays; audit bean scopes and caches |
| After user A, user B always sees A | `Mono.cache()` or cache key missing user/tenant | Inspect cached Publisher lifetime and data partitioning |
| Request with `X-User` header controls data | Trusting client-sent headers | Drop header trust or lock behind verified gateway and token validation |
| API returns `401` on async pipeline | Detached subscription without context or wrong credentials | Check security filters, Reactor chain wiring, request credentials, and actual error |
| Right username, wrong record accessed | Query missing owner/tenant condition | Test cross-resource access; add owner filter in repository |
| Trace/MDC occasionally shows another request's username | Broken ThreadLocal context propagation/cleanup | Never use MDC for permissions; check accessors, cleanup scopes, log redaction |

Effective investigation steps:

1. Reproduce with **two distinct identities** and an endpoint returning the identity supplied by Spring Security; start with sequential requests.
2. Add delays or scheduler switches inside the Reactor pipeline and run interleaved requests. Log an independent **request ID** (never the token) to correlate logs per request.
3. Expand into a concurrency test asserting both exact principal and exact data. Use `WebTestClient` through security filters rather than calling controller methods directly.
4. Audit singleton fields, `static` state, `ThreadLocal`, `Mono.cache`, shared/hot Publishers, async callbacks, event sinks, request/session scopes, and identity-reading interceptors.
5. Trace the auth path: credentials → Spring Security authentication → Reactor Context → controller/service → data query → response. Check authorization gates at every boundary.
6. When forwarding identity to another API/queue, define a new trust and authorization contract; never arbitrarily pass raw mutable `SecurityContext`.
7. Ensure negative tests always exist: anonymous rejected from protected resources, bad credentials rejected, user A never receives B's response/data, spoofed headers never change principal.

## 11. Common misconceptions

**"Each WebFlux request has its own thread."** False. Event-loop threads are shared and signals can be processed interleaved.

**"Using volatile String currentUser is thread-safe enough."** False. `volatile` does not provide per-request isolation.

**"Reactor Context is a global HashMap."** False. Context is immutable and bound to the subscriber; `contextWrite` affects the upstream operator scope of that subscription.

**"@PreAuthorize alone prevents leaking other users' data."** False. Method security also depends on proxy invocation and policy. Data queries need owner/tenant protection; a wrong username variable or shared cache remains dangerous.

**"Switching schedulers definitely loses security context."** False for standard Reactor operators in the same chain. The bigger risk is **detaching from the chain**, reading `ThreadLocal`, or using libraries needing an unconfigured context bridge.

**"WebTestClient returning 200 means there is no leak."** False. You must match the response body against the actual identity/tenant of **each request**.

**"Caching the result of Mono.getContext() optimizes performance."** Very dangerous if shared: the first subscriber can lock in the value replayed to all later subscribers.

**"Two browser tabs showing the same user is a concurrency bug."** It may just be two tabs sharing one cookie/session or cached credentials. Verify the actual credentials sent by the browser before concluding.

**"Requests can choose Authentication via contextWrite(withAuthentication(...))."** False. This API is only appropriate where the server/test already **trusts** the identity. Accepting a client-declared principal is an identity-spoofing vulnerability.

## 12. Self-check questions

**Q1:** Alice and Bob send concurrent requests on the same event-loop thread. Does storing the username in `ThreadLocal` guarantee isolation?  
**No.** One thread can serve both requests; use subscriber-bound Reactor Context and avoid shared state.

**Q2:** Why does `Mono.delay(...).then(identityService.current("later"))` in the example still read the right principal?  
Because the operators remain in the same subscription and `ReactiveSecurityContextHolder` reads the corresponding context; `Mono.defer` ensures the read happens at subscription time.

**Q3:** In the singleton example with `Mono<String> cached = getContext().map(...).cache()`, why can Bob see Alice?  
Because `cache` replays the result of the first subscription to later subscribers without partitioning by principal.

**Q4:** Is a concurrent test suite asserting only `isOk()` enough?  
**No.** You must assert that the body/resource matches **each** request's credentials, and also test unauthorized cases.

**Q5:** If user A reads the right `Authentication` yet still views B's report, where is the bug?  
Likely in resource authorization policy/query logic, such as a repository missing an owner/tenant filter; protect the data layer in addition to isolating security context.

**Q6:** A background job needs to record its initiator. Should you keep the request's `ReactiveSecurityContextHolder` indefinitely?  
**No.** Pass the verified identity and minimal metadata in the job contract, and check authorization at execution time per policy.

### Official references

- Spring Security, *Reactive Method Security* (Reactor Context and `ReactiveSecurityContextHolder`): https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Reactor, *Adding a Context to a Reactive Sequence*: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor, *Context-Propagation Support*: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Framework, *Testing with WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Most important rule:** Keep `SecurityContext` in **the subscription's Reactor Context**, read via `ReactiveSecurityContextHolder` in the right pipeline, never store principals in shared state, never share caches containing per-user data, and test concurrently with multiple identities asserting on **the exact returned data**. That way, thread interleaving never turns into a cross-request identity leak.