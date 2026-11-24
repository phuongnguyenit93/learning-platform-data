# Avoiding `.block()`, Manual `.subscribe()`, and `ThreadLocal` When Propagating Identity in Spring Security Reactive

## 1. Goal and Scope

In a Spring WebFlux application using Spring Security, a request can traverse many Reactor operators, switch execution threads, call other services, and return without staying on the same Java `Thread`. Therefore you must simultaneously protect **non-blocking execution**, **publisher lifecycle**, and **the security context of the right request**.

After this lesson, you should be able to explain and practice:

- Never calling `block()`, `blockFirst()`, `blockLast()`, `toFuture().get()`, or synchronous I/O directly on a WebFlux processing thread.
- Never calling `subscribe()` in a controller, service, or authentication/authorization logic to "trigger" work and immediately return a response.
- Never reading/passing user identity via `ThreadLocal` or Servlet-style `SecurityContextHolder` inside a reactive chain; use `ReactiveSecurityContextHolder` and Reactor `Context` when accessing `Authentication`.
- Knowing when `Schedulers.boundedElastic()` is only a transitional bridge for blocking libraries, and when an independent execution boundary must be separated.
- Verifying two concurrent requests with different identities, handling errors/cancellations, and avoiding principal leakage.

Primary scope: **Spring Security on WebFlux + Project Reactor (`Mono`/`Flux`)**. Java snippets use Spring Security 6.x, Spring Framework 6.x, Reactor 3.x, and Java 17+ APIs. Short illustrative snippets using hypothetical repository/client names will be noted clearly; the complete application example in section 7 is runnable in a Spring Boot WebFlux project.

## 2. Execution Model: Subscription, Scheduler, and Security Context

In Reactor, `Mono<T>` or `Flux<T>` describes a processing sequence. Creating a publisher **does not mean** I/O work has executed. A `Subscriber` subscribes to start the sequence; along the path there are `onNext`, `onError`, and `onComplete` signals, as well as potential `cancel` signals.

For an HTTP request, WebFlux and the runtime are responsible for subscribing to the publisher returned by a handler/controller. Operators like `map`, `flatMap`, `then`, `zip`, etc. attach additional steps to that same sequence. A new `subscribe()` call manually invoked by a service typically opens **a separate subscription**, detaching results, errors, and cancellation control from the original request.

Spring Security Reactive uses `ReactiveSecurityContextHolder` to read `SecurityContext` from the **Reactor Context** bound to the subscriber. `SecurityContext` holds `Authentication` (principal, authorities, authentication state). Distinguish clearly:

| Concept | Bound to | Role | What must not be inferred |
| --- | --- | --- | --- |
| Java `ThreadLocal` | A single Java thread | Thread-local data | "Current thread = current user" in WebFlux |
| Reactor `Context` | Subscription and signal flow per Reactor rules | Propagates metadata across reactive operators | Does not automatically jump into arbitrary `Executor`s or detached subscriptions |
| Spring `SecurityContext` | Security state containing `Authentication` | Represents identity/authorities managed by Spring Security | Not equivalent to `reactor.util.context.Context` |
| `ReactiveSecurityContextHolder` | Bridge to Reactor Context | `Mono<SecurityContext>` for the reactive chain | Not a global variable shared across all requests |

Typical flow:

```text
HTTP request
    |
    v
Spring Security WebFilterChain
    |  authenticates, checks permissions, provides SecurityContext
    v
WebFlux handler -> Mono/Flux -> service -> WebClient / reactive repository
    |                  |                         |
    +----------- same subscription / Reactor Context ------------+
    |
    v
WebFlux subscribes, emits HTTP response or handles error/cancel
```

`publishOn` and `subscribeOn` change where steps in the sequence execute. **Switching schedulers does not automatically clear the Reactor Context** in a properly composed reactive chain. What easily breaks the association is creating a separate subscription, leaving for a non-Reactor async API without propagating context across a controlled boundary, or falling back to reading the principal via `ThreadLocal`.

## 3. Anti-pattern 1: Blocking with `block()` or Synchronous I/O

### 3.1. Why Is It Dangerous?

WebFlux typically handles many connections on a relatively small number of event-loop threads. `Mono.block()` waits synchronously for a result; if called on a thread marked non-blocking by Reactor/Netty, it can throw an `IllegalStateException` ("block()/blockFirst()/blockLast() are blocking..."). Even when a blocking call succeeds on another thread, it ties up that thread while waiting, reducing throughput under load.

**Wrong — controller blocks on WebClient:**

```java
@GetMapping("/profile")
public String profile() {
    return webClient.get()
            .uri("/profiles/current")
            .retrieve()
            .bodyToMono(String.class)
            .block(); // blocks the request processing thread
}
```

**Right — let WebFlux manage the subscription:**

```java
@GetMapping("/profile")
public Mono<String> profile() {
    return webClient.get()
            .uri("/profiles/current")
            .retrieve()
            .bodyToMono(String.class);
}
```

Both snippets above are **method excerpts** inside a controller with a configured `WebClient`, not standalone Java programs. In the right version, if downstream fails, the error travels through the `Mono` for the HTTP layer to handle; if the client cancels the request, cancellation can propagate down the chain as supported by each component.

A subtler mistake is wrapping blocking waits inside `map`:

```java
// Wrong: performing blocking I/O inside a reactive operator.
return userRepository.findById(id)
        .map(user -> blockingPaymentClient.lookup(user.id()));
```

If a method returns a publisher, chain it with `flatMap`:

```java
// Right when lookup returns Mono<Payment>.
return userRepository.findById(id)
        .flatMap(user -> reactivePaymentClient.lookup(user.id()));
```

`map` is meant for **short, synchronous, non-blocking** transformations; `flatMap` is used when the next step returns a `Publisher`. Do not confuse a method returning `Mono` with one that must wait for its result immediately.

### 3.2. What If the System Still Has Blocking Libraries?

Prefer truly non-blocking APIs (e.g., `WebClient` instead of a synchronous HTTP client, R2DBC drivers instead of running JDBC directly on the event loop). If a legacy library cannot yet be replaced, wrap each blocking section in `Mono.fromCallable` and offload **that section** to `Schedulers.boundedElastic()`:

```java
// legacyClient.findProfile(userId) is a synchronous call that may block.
Mono<String> legacyProfile(String userId) {
    return Mono.fromCallable(() -> legacyClient.findProfile(userId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a service excerpt assuming `legacyClient`, Reactor imports, and a method returning `String` already exist. When the operation returns `void`, you can use `Mono.fromRunnable(...).subscribeOn(Schedulers.boundedElastic()).then()`. `fromCallable` invokes the task only when subscribed to; `subscribeOn` **schedules execution rather than subscribing itself**.

Understand the exact limits:

- `boundedElastic` caps the number of threads/queued tasks per configuration; offloading blocking work there **does not make a blocking API non-blocking**. You must monitor pool saturation, timeouts, connection counts, and concurrency.
- Wrap the blocking source right at the boundary, then continue composing the `Mono` with operators; do not sprinkle `subscribeOn` arbitrarily around the whole pipeline assuming everything is solved.
- Never use `Schedulers.parallel()` to hide blocking I/O; that scheduler is intended for short, non-blocking, or CPU-bound work.
- Reactor-side timeout/cancellation does not guarantee immediately interrupting a waiting synchronous socket/JDBC call; configure timeouts on the legacy client/driver itself.
- Switching schedulers is not a reason to read thread-local `SecurityContextHolder` inside a blocking lambda; if a legacy API needs a user ID for **business logic**, extract the valid identity inside the reactive chain first and pass it as an explicit argument.

Example of composing identity properly with a legacy call, where `legacyClient` is a synchronous library and the method returns `String`:

```java
Mono<String> profileForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(username ->
                    Mono.fromCallable(() -> legacyClient.findProfile(username))
                            .subscribeOn(Schedulers.boundedElastic()));
}
```

Do not call `block()` to "grab the username" and then call the legacy client. Here username is business data read from the subscription's security context; resource access permissions must still be enforced by authorization policies rather than relying on username alone.

## 4. Anti-pattern 2: Calling `subscribe()` Manually in Controllers/Services/Filters

### 4.1. Why Is "Fire and Forget" Usually Wrong?

Consider a service updating data and then writing an audit log:

```java
// Wrong: the update runs on a detached subscription.
Mono<Void> changeEmail(ChangeEmail command) {
    repository.update(command).subscribe();
    return Mono.empty();
}
```

This is an excerpt; `ChangeEmail` and `repository` are hypothetical components. The handler can return success before the update completes; errors from the update never reach the request; cancellation and execution ordering are no longer part of the handler's contract. Many `Mono` sources are cold publishers, so re-subscribing could re-run I/O operations. A secondary subscription also does not automatically receive the `SecurityContext` attached to the request.

**Right — keep the business steps in a single pipeline:**

```java
// repository.update(command) -> Mono<SavedAccount>
// audit.record(id) -> Mono<Void>
Mono<Void> changeEmail(ChangeEmail command) {
    return repository.update(command)
            .flatMap(saved -> audit.record(saved.id()))
            .then();
}
```

`flatMap` waits for the audit operation to be subscribed to and complete before terminating the resulting publisher. If the update and audit are data-independent yet both must complete, consider `Mono.when(first, second)`; if the audit needs the ID produced by the update, use `flatMap` as above. Rollback/transaction decisions must rely on repository and transaction manager capabilities—do not assume `then()` creates a transaction.

A related mistake:

```java
// Wrong: the lambda creates a new Mono without chaining it into the sequence.
return repository.update(command)
        .doOnNext(saved -> audit.record(saved.id()).subscribe())
        .then();
```

`doOnNext` is suitable for **lightweight, synchronous** side effects such as incrementing a metric or non-blocking logging; you should not trigger a second reactive operation via `subscribe()` inside it. Switch to `flatMap` / `concatMap` / `then` depending on data dependencies and ordering.

### 4.2. Consequences for Errors and Cancellation

A properly composed pipeline has a clear path for `onError` and `cancel`. You can use `onErrorMap` to translate errors, `onErrorResume` for **intentional** fallbacks, and `doOnError` for logging; avoid blanket `onErrorResume(e -> Mono.empty())` that silently treats failed updates as successes. Note that `retry` re-subscribes to the source and re-runs side effects, so write operations must be designed with idempotency if retries are used.

**Where is `subscribe()` allowed?** At a boundary with a clear lifecycle owner: the WebFlux runtime when sending an HTTP response, a framework-managed message listener/consumer, or tests explicitly using `StepVerifier`. Background tasks independent of HTTP must have dedicated lifecycle, error, retry, security, shutdown, and observability management; decoupling async work does not make `service.subscribe()` the default choice.

## 5. Anti-pattern 3: Reading Identity with Servlet-Style `ThreadLocal`/`SecurityContextHolder`

### 5.1. Model Mismatch

In traditional Servlet flows, developers often write:

```java
// Do not use as the identity source in a reactive service.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

By default `SecurityContextHolder` binds context to a thread. In WebFlux, threads can be reused across different requests, and a single request can resume on a different thread. The result may be `null`, missing information, or wrong context if the application sets/clears `ThreadLocal` improperly. `InheritableThreadLocal`, changing the `SecurityContextHolder` mode, or manually copying principals across threads only creates hard-to-verify edge cases; they are no substitute for Reactor Context.

**Right — read from the subscription's context:**

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

This is a service method inside a region authenticated by Spring Security. `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`; if no context is present, the sequence can complete empty. Do not arbitrarily fall back to a default like "admin", a fake token, or a global variable when context is missing. Authentication/authorization requirements must be expressed in `SecurityWebFilterChain`, `ReactiveAuthorizationManager`, or method security. Checking `isAuthenticated()` in isolation also does not replace authorization checks because anonymous authentication has its own rules.

### 5.2. When to Read the Principal vs. When to Pass a User ID?

- At the **HTTP/security boundary**, Spring Security verifies credentials/tokens, loads authorities, and places `Authentication` into the Reactor Context. For normal requests, **never overwrite** authentication with data arriving from arbitrary headers or request bodies.
- In a service needing to decide "who is calling," use `ReactiveSecurityContextHolder.getContext()` inside the pipeline, or the principal supplied by the framework via handler parameters. Do not switch to `block()` just to extract a single field.
- After authorization checks, if pure business functions or blocking libraries only need `userId` for queries/auditing, pass **an explicit value via method parameters**. This keeps dependencies clear, easy to test, and avoids forcing legacy libraries to understand Spring Security.
- `Authentication.getName()` is not always the database user ID. With JWT/OIDC, the stable identifier may reside in `sub` or a claim mapped by system policy; do not equate username/email with an internal ID without proper mapping and access control over the target object.

Example of passing a verified identity into a service (excerpt; `accountService` returns `Mono<AccountView>`):

```java
Mono<AccountView> myAccount() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(accountService::findAuthorizedViewFor);
}
```

The method name `findAuthorizedViewFor` indicates **the service must still enforce data-level permission checks**. Never accept an arbitrary `userId` sent by the client and allow viewing someone else's account merely because a `SecurityContext` exists.

### 5.3. `contextWrite` and Subscription Boundaries

Reactor Context travels along subscriber relationships in the pipeline, not as thread-local data. `contextWrite` adds/modifies context for operators **upstream** of that call (along the subscription direction). In an authenticated WebFlux request, Spring Security is responsible for supplying the required context; controllers/services normally only **read**, rather than calling `contextWrite(withAuthentication(...))` to fabricate identity.

In a standalone test, you can construct a controlled `Authentication` and attach context to the publisher under test:

```java
Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice", "unused", AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
```

The snippet above uses `Authentication`, `UsernamePasswordAuthenticationToken`, `AuthorityUtils`, `ReactiveSecurityContextHolder`, `Mono`, and `Schedulers`; the complete test is in section 8. It demonstrates that the identity is still read properly after switching schedulers **within the same pipeline**. **Never** use this pattern to construct an `Authentication` from a client-supplied `username` string to bypass HTTP authentication; `withAuthentication` here is strictly for building trusted fixtures in tests or specially designed internal boundaries.

A `repository.find(...).subscribe()` call elsewhere does not automatically receive the request's context even if both subscriptions happen to run on the same thread. Likewise, `CompletableFuture.supplyAsync`, `@Async`, custom executors, external callbacks, and message queues are **separate async boundaries**; you must decide which data to pass explicitly and integrate appropriate context propagation if supported by the framework. Never conclude that a `ThreadLocal` that "works on a dev machine" will hold up under production concurrency.

### 5.4. Downstream Services and Logging

Having a user in `ReactiveSecurityContextHolder` **does not mean** `WebClient` automatically forwards an access token to every service. Propagating credentials downstream must go through proper client/security configuration (such as an OAuth2 authorized client when required by the design), verifying audiences/scopes and never copying bearer tokens arbitrarily to untrusted hosts.

Logging library MDC/correlation IDs typically rely on `ThreadLocal` and may require dedicated context-propagation/bridge integration. Trace IDs, user IDs for auditing, and `Authentication` objects for authorization have distinct responsibilities; **never** use MDC or trace headers to make authorization decisions. Avoid logging tokens, passwords, full principals, or sensitive data.

## 6. How to Compose an Authentication/Business Flow Properly

Example processing chain "read identity -> look up data -> write audit", assuming:

- `accountRepository.findByOwner(String)` returns `Mono<Account>` (reactive).
- `auditService.recordRead(String)` returns `Mono<Void>`.
- `Account.displayName()` returns `String`.

```java
Mono<String> readOwnDisplayName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(username ->
                    accountRepository.findByOwner(username)
                            .switchIfEmpty(Mono.error(
                                    new NoSuchElementException("Account not found")))
                            .flatMap(account ->
                                    auditService.recordRead(username)
                                            .thenReturn(account.displayName())));
}
```

This is a logic excerpt inside a class with injected dependencies, not standalone code. The structure ensures the audit work stays inside the returned publisher and relevant errors can propagate. `NoSuchElementException` only illustrates a domain error; the HTTP layer needs appropriate error mapping rules, and the service needs resource permission checks. If you want auditing even when reading fails, define explicit event semantics rather than invoking a detached `subscribe()` inside `doOnError`.

For lists of results, `flatMap` may run inner publishers concurrently; use `concatMap` when strict ordering and sequential execution are required, and bound concurrency when downstream capacity is limited. HTTP results, errors, timeouts, cancellation, and security state must all belong to the designed processing model.

## 7. Complete Spring Boot WebFlux Example: Reading the Logged-In User

The following is **a compilable/runnable Java file** in a Spring Boot 3.x, Java 17+ project with `spring-boot-starter-webflux` and `spring-boot-starter-security`. The example uses HTTP Basic with an in-memory user solely for learning; **`{noop}` passwords and non-TLS HTTP are not suitable for production**. Never use self-declared HTTP headers as the principal.

Place at `src/main/java/demo/ReactiveIdentityApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveIdentityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}dev-only-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "Hello, " + name);
        }
    }
}
```

In a Gradle Spring Boot project with plugins and Java 17+ already configured, the required dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) in the project containing the application. Test sequentially:

```bash
curl -sS http://localhost:8080/public
curl -i http://localhost:8080/me
curl -sS -u reader:dev-only-password http://localhost:8080/me
```

Expectations:

1. Request `/public` returns body `public` without credentials.
2. Request `/me` without credentials is rejected with HTTP **401 Unauthorized**.
3. Authenticated request `/me` returns exact body `Hello, reader`.

Here `SecurityWebFilterChain` handles authentication/authorization, `ReactiveSecurityContextHolder` only reads the principal supplied by Spring Security, and the controller returns `Mono<String>` for WebFlux to subscribe to. There is no `block()`, manual `subscribe()`, or `ThreadLocal`. Do not disable CSRF globally just to make GET examples work; when adding state-mutating requests, design CSRF/authorization suitable for the client type (cookie-based browsers, bearer tokens, etc.).

## 8. Regression Test: Ensuring Context Does Not Turn into a ThreadLocal

The small test below checks reading the principal after `publishOn`; it uses `contextWrite` **only to set up a test fixture**. Save at `src/test/java/demo/ReactiveContextTest.java` if the project has JUnit Jupiter, Spring Security Core, and `reactor-test` (listed in section 7).

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void currentUserSurvivesSchedulerSwitch() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        Mono<String> name = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .publishOn(Schedulers.parallel())
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(name)
                .expectNext("alice")
                .verifyComplete();
    }
}
```

Run `./gradlew test` or `gradlew.bat test`; the test **PASSes** when the publisher emits the single string `alice` and completes. This is a Reactor-level check and does not replace integration tests for the HTTP/security filter chain.

For real systems, add the following scenarios:

| Test scenario | What to assert |
| --- | --- |
| Two concurrent requests from Alice and Bob | Each response/audit carries its own identity; no principal mix-up |
| Unauthenticated / unauthorized request | Returns 401 / 403 per configured policy; does not fabricate permissions |
| Downstream returns an error or times out | Error flows through the publisher with unified handling; no orphaned tasks |
| Client cancels request mid-flight | No detached `subscribe()` task left running out of control |
| Moving across `publishOn` or `subscribeOn` | Reading `ReactiveSecurityContextHolder` remains accurate within the same subscription |
| Crossing to `CompletableFuture`/executor/broker | Identity/audit metadata is passed across boundaries by explicit policy; no ThreadLocal assumption |

To test concurrency, use `WebTestClient` with security test support (`spring-security-test`) or send real requests with two different credentials; assert both response values and audit records per request. Never write tests that depend on thread names or on the test machine using a single worker thread.

## 9. Failure Symptoms and How to Investigate

**Error "`block() ... is blocking`" or latency spikes under concurrent load.** Search for `.block(`, `.blockFirst(`, `.blockLast(`, `Thread.sleep`, and synchronous JDBC/HTTP clients in controllers, services, and even `map`/`doOnNext` callbacks. Replace with reactive APIs; for unavoidable legacy blocking, move the source segment into `fromCallable(...).subscribeOn(boundedElastic())`, set timeouts, and bound load.

**HTTP returns success yet the DB/audit is not updated or errors are never recorded.** Search for `.subscribe(` in business code. Check for publishers created and discarded, `doOnNext` subscribing on its own, or `Mono<Void>` returning `Mono.empty()` prematurely. Refactor to `flatMap`, `then`, or `when` inside a single publisher returned by the controller.

**Principal is occasionally `null`, context disappears after a callback, or user info is unstable.** Check for `SecurityContextHolder.getContext()`, `ThreadLocal`, `InheritableThreadLocal`, `@Async`, new subscriptions, custom executors, or message queues. Access `ReactiveSecurityContextHolder` within the authenticated request chain; when crossing boundaries, pass a business user ID or integrate controlled context propagation.

**Only fails when adding `publishOn` and legacy code reads the user from `ThreadLocal`.** Scheduler switches do not preserve threads; fix how context is read rather than trying to pin the entire request to one thread. Avoid wrapping Security logic in `Schedulers.boundedElastic` unnecessarily.

**Occasional duplicate writes after retry.** `retry` re-subscribes upstream so side effects can execute again. Verify idempotency keys, transaction boundaries, and retry conditions; do not work around it with a separate `subscribe()`.

## 10. Design Principles and Adoption Checklist

1. **Keep a single owned pipeline:** return `Mono`/`Flux` from controllers, services, and reactive filters. Let the runtime or managed subscriber perform the subscription.
2. **Never block the event loop:** external I/O must be non-blocking. Blocking legacy calls are isolated close to the source on `boundedElastic` with measured resources/timeouts.
3. **Do not detach mandatory work as fire-and-forget:** compose with `flatMap`, `then`, `when`, or `concatMap` based on ordering; handle `onError` and cancellation intentionally.
4. **Obtain identity from verified security:** use `ReactiveSecurityContextHolder` or Spring-supplied principals; configure authorization clearly in `SecurityWebFilterChain` and/or method security.
5. **Separate authorization from business data:** pass `userId` as an argument after permission checks when needed, but never use a client-supplied username to spoof `Authentication` or make authorization decisions in place of the security layer.
6. **Make boundaries explicit:** background tasks, brokers, executors, external callbacks, and downstream WebClients do not automatically own the request's security context; design identity/credential propagation per trust boundary.
7. **Test under load and scheduler switches:** concurrent principals, unauthenticated requests, downstream errors, timeouts, cancellations, and retries. Monitor event-loop latency, blocking operations, and unowned subscriptions.

Rule of thumb: **do not "pull" results out of a `Mono` with `block()`, do not "push" a side subscription with `subscribe()`, and do not "guess" identity from the thread.** Compose a single owned reactive chain and retrieve context properly from the subscriber.

## Official Documentation

- [Spring Framework — WebClient synchronous use and WebFlux recommendations](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html).
- [Spring Security — Reactive HTTP authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — Reactive Method Security and Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html).
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html).
- [Project Reactor — Schedulers API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html).
