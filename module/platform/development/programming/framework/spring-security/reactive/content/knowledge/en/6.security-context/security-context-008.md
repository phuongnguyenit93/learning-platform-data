# Propagating security context across publishOn, subscribeOn, and asynchronous calls

## 1. Learning objectives

In Spring Security Reactive, user identity is not permanently pinned to a Java thread. When a WebFlux pipeline uses `publishOn`, `subscribeOn`, `flatMap`, timers, reactive I/O, or calls to another async API, a request can traverse multiple threads. What must stay intact is **the security context belonging to the same Reactor subscription**, not the running thread's name.

After this lesson, you will be able to:

1. Explain `Reactor Context`, `ContextView`, `contextWrite`, and `ReactiveSecurityContextHolder`.
2. Distinguish switching schedulers with `publishOn`/`subscribeOn` from losing security context.
3. Read `Authentication` before and after `flatMap`, `Mono.delay`, and `Mono.fromCallable` boundaries properly.
4. Integrate `CompletableFuture`, `@Async`, or non-Reactor callbacks without assuming `ThreadLocal` and Reactor Context appear automatically inside callbacks.
5. Identify detached subscriptions caused by calling `subscribe()`, as well as misplaced `contextWrite` bugs.
6. Build a Java 17+ Spring WebFlux application and test HTTP 401, identity consistency across schedulers, and isolation between users.

The scope is **Spring Security's security context in WebFlux**. Examples use Spring Boot 3.x, Spring Security 6.x, Project Reactor 3.x, and Java 17+. Tracing/MDC/ThreadLocal propagation mechanisms are clearly distinguished from security context, as they have different lifecycles and purposes.

## 2. Why is ThreadLocal no longer a valid assumption?

In traditional Servlet applications, Spring Security commonly accesses the security context via `SecurityContextHolder`; its default strategy relies on `ThreadLocal`. In many synchronous blocks, the request-serving thread holds the context while the code runs. When handing off to an `Executor`, `@Async`, or another thread, copying context cannot be taken for granted.

In Spring WebFlux, a handler may start on one thread and continue after `publishOn`, `delayElement`, network callbacks, or another scheduler. A single thread in the event loop serves many requests over time, so storing a principal in a manual `ThreadLocal` variable can yield `null` or the wrong identity when threads switch, and risks identity leakage if lifecycle cleanup fails.

Spring Security Reactive uses **`ReactiveSecurityContextHolder` and Reactor Context**:

```java
// Snippet inside a WebFlux bean; not a standalone Java class.
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

Imports: `reactor.core.publisher.Mono` and `org.springframework.security.core.context.ReactiveSecurityContextHolder`. When no context exists, the publisher normally completes empty; the example does not decide who the user is on its own. On an HTTP endpoint requiring authentication, let `SecurityWebFilterChain` authenticate and authorize before the controller reads context.

**Principle:** Reactor Context follows the subscription and is propagated by supporting Reactor operators. It is not identical to Java `ThreadLocal`, nor does it automatically become HTTP headers, Kafka event metadata, or data inside an arbitrary `CompletableFuture`.

## 3. Reactor Context belongs to the subscriber, not the Thread

`Context` is a key/value mapping structure that is immutable in usage (each `put` creates a new context). `ContextView` is the read-only interface. Each subscription has its own context, which Reactor operators can access via `Mono.deferContextual` or `Flux.deferContextual`.

Pure Reactor example:

```java
Mono<String> query = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "missing"))
);

Mono<String> request = query
    .contextWrite(ctx -> ctx.put("traceId", "REQ-42"));

// If block() is used in a demo running outside the event loop:
// request.block() returns "REQ-42".
```

This snippet imports `reactor.core.publisher.Mono` and uses `block()` **only in demo programs or tests**, never in a WebFlux handler.

### 3.1. Propagation direction of `contextWrite`

Reactor Context is attached at subscription time and logically **propagates from the subscriber at the end of the chain up to earlier operators**. Therefore, `contextWrite` placement matters:

```java
Mono<String> present = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing")))
    .contextWrite(ctx -> ctx.put("key", "value"));
// present.block() -> "value"
```

Compare with placing it outside the scope of the operator that wants to read:

```java
Mono<String> absent = Mono.just(1)
    .contextWrite(ctx -> ctx.put("key", "value"))
    .flatMap(n -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing"))));
// absent.block() -> "missing"
```

In the `absent` example, `contextWrite` alters the context **only upstream of itself**; the trailing `flatMap` does not inherit the `key` entry. Do not think of context as a global variable set once for the entire application.

### 3.2. How does Spring Security store context?

Spring Security uses internal keys and mechanisms via `ReactiveSecurityContextHolder`. Applications should not guess the security context key or substitute `Context.of("user", name)` expecting authorization to understand it. Use the official API:

```java
Authentication authentication =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "not-an-http-password",
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    );

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

Imports: `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `List`, and `Mono`. This is a **snippet for unit tests or internal simulation with an already-trusted identity**. On a real HTTP server, never build an `Authentication` from self-declared inputs/headers and call `withAuthentication` to bypass authentication; Spring Security WebFlux must authenticate the request and establish the context.

`ReactiveSecurityContextHolder.withAuthentication(authentication)` supplies a `Context` containing the authentication wrapped in a security context per Spring Security's API. `.contextWrite(...)` attaches it to the publisher's upstream scope; it **does not** mutate global static state or future requests.

## 4. `publishOn`: switches downstream execution, does not copy identity to ThreadLocal

`publishOn(Scheduler)` affects the thread handling **downstream signals after the operator**, until another `publishOn` appears; it typically switches the thread executing subsequent callbacks. It is not a login API, does not attach security context to `ThreadLocal`, and does not pin the request to one thread.

Example:

```java
Mono<String> display = username()
    .publishOn(Schedulers.parallel())
    .flatMap(before -> username()
        .map(after -> before + "|" + after));
```

Here `username()` is a method returning `ReactiveSecurityContextHolder.getContext().map(...)` inside the same reactive service, not a built-in Java API; full code is in section 8.

If security context exists in the publisher's **subscription**, both reads before and after `publishOn` receive the same principal, even though the two blocks may run on different threads. They might happen to share a thread in small environments; therefore **never use thread-name comparison as proof of correct/broken context propagation**.

`Schedulers.parallel()` is suited for short CPU work, not blocking JDBC, long synchronous file I/O, or `Thread.sleep`. Reactor Context may still be intact while the system stalls if blocking code runs on `parallel` or the Netty event loop.

## 5. `subscribeOn`: changes subscription scheduling, does not create a new context

`subscribeOn(Scheduler)` affects where **subscribing/requesting from the source** is scheduled. Its semantics differ from `publishOn`:

| Criterion | `publishOn` | `subscribeOn` |
|---|---|---|
| Primary effect | Switches signal delivery from that point downstream | Schedules subscription/source request |
| Typical placement | Before operators whose execution thread you want to switch | Near blocking sources/sources needing specific scheduling |
| Security context impact | Does not erase Reactor Context by itself | Does not erase Reactor Context by itself |
| Creates new identity? | No | No |
| Copies ordinary `ThreadLocal`? | Not guaranteed | Not guaranteed |
| Turns blocking I/O into non-blocking? | No | No; only moves work to another scheduler |

Example of a `Mono.fromCallable` source carrying synchronous work:

```java
Mono<Integer> value = Mono.fromCallable(() -> 7)
    .subscribeOn(Schedulers.boundedElastic());

Mono<String> result = value
    .flatMap(n -> username()
        .map(name -> name + ":" + n));
```

`boundedElastic` bounds thread/queue counts by Reactor design and is a way to **isolate a legacy blocking step**. It still consumes threads and does not make synchronous database drivers reactive. When genuine non-blocking APIs like `WebClient` or R2DBC exist, prefer composing their publishers.

Distinguish two layers: **Reactor Context propagates across publishers**, yet synchronous Java code running inside a callable is not guaranteed to see the same identity via `SecurityContextHolder`. If the callable needs the username, extract it with `ReactiveSecurityContextHolder` **before creating the callable**, and pass it as an allowed parameter or captured immutable value:

```java
return username().flatMap(name ->
    Mono.fromCallable(() -> legacyService.loadFor(name))
        .subscribeOn(Schedulers.boundedElastic())
);
```

This is an illustrative snippet inside a method returning `Mono<...>`, where `legacyService` is injected and enforces proper permission controls. If `loadFor` handles sensitive data, passing only the username is not enough to guarantee authorization; the service and data layers must still enforce verified permissions.

### 5.1. Does adding multiple `subscribeOn` calls propagate context better?

No. Placement and scheduling effects of multiple `subscribeOn` calls can be unintuitive; call it only near the source requiring scheduling to keep code clear. Never sprinkle `subscribeOn(Schedulers.parallel())` everywhere to "preserve security context". Context is preserved by publishers within the same subscription; switching schedulers does not magically give non-Reactor code a context.

## 6. `flatMap`, timers, and reactive I/O: what is preserved?

`flatMap` subscribes to an inner publisher and Reactor propagates the subscriber's context per operator semantics. `Mono.delay` emits signals via a scheduler, and `WebClient`/reactive I/O can complete after another thread handles work. While staying composed in **one request pipeline**, `ReactiveSecurityContextHolder.getContext()` can read the identity at appropriate stages.

Example:

```java
return username()
    .flatMap(before ->
        Mono.delay(Duration.ofMillis(10))
            .then(username())
            .map(after -> before + "|" + after)
    )
    .publishOn(Schedulers.parallel());
```

This snippet uses `java.time.Duration`, `reactor.core.scheduler.Schedulers`, and a `username()` method; it returns `Mono<String>`. With authenticated principal `alice` and an unbroken context, the result is `alice|alice`. Test **identity values** rather than thread names or unstable log ordering.

**Note on calling other services:** When `WebClient` sends HTTP to a downstream service, **Reactor Context does not travel over the network automatically**. The remote service receives a new request with a new security boundary; it knows the user only if valid credentials/tokens and verification policies are sent, or via a designed trusted delegation mechanism. Never treat `contextWrite` in a caller as an automatic "login" on a remote service.

## 7. Boundaries outside Reactor: CompletableFuture, @Async, callbacks, and detached subscribe

This is where the most subtle bugs arise. Reactor Context is not data automatically present in every callback running on an executor outside Reactor.

### 7.1. `CompletableFuture.supplyAsync` does not inherit context like a Reactor operator

Look at the two separate phases:

```text
HTTP Request (authenticated)
    |
    v
Reactor pipeline: ReactiveSecurityContextHolder.getContext()
    | -> resolve user authenticated by Spring Security
    v
CompletableFuture.supplyAsync(() -> externalWork(user))
    | -> Java callback runs on its own executor
    | -> DO NOT assume Reactor Context or SecurityContextHolder here
    v
Mono.fromFuture(...) rejoins completion to the pipeline
    |
    v
flatMap/ReactiveSecurityContextHolder.getContext()
    -> reads context on the continuation belonging to the Reactor subscription
```

Safe integration pattern for a simple case:

```java
return username().flatMap(caller ->
    Mono.fromFuture(() ->
            CompletableFuture.supplyAsync(
                () -> "loaded-for-" + caller))
        .flatMap(result ->
            username().map(inContext ->
                result + "|" + inContext))
);
```

This is a snippet in a service/controller requiring `java.util.concurrent.CompletableFuture`. `"loaded-for-" + caller` merely represents a lightweight non-blocking computation for illustration. `Mono.fromFuture(Supplier)` creates the future **at subscription time**, avoiding eager side effects at assembly time; by default, canceling the `Mono` can cancel the future per Reactor's contract. For real blocking tasks, use a dedicated bounded executor/backpressure mechanism or suitable blocking adapter. `CompletableFuture.supplyAsync` is not a good default for arbitrary WebFlux I/O.

In the example above, the callback inside `supplyAsync` **receives `caller` explicitly** rather than trying to read principal from ThreadLocal. After `Mono.fromFuture(...)`, the `flatMap` is once again a Reactor operator, so `username()` can read the subscription's context again. That does not mean code **inside** the future saw the context.

### 7.2. `@Async` and Executors

A Spring `@Async` method or a task submitted via `Executor.submit` usually runs in a thread pool outside the reactive subscription. Do not write:

```java
@Async
public CompletableFuture<String> load() {
    String user =
        SecurityContextHolder.getContext()
            .getAuthentication().getName(); // NOT reliable in WebFlux
    return CompletableFuture.completedFuture(user);
}
```

This is an illustrative buggy snippet; do not use it. Replace it with an API accepting verified identity as an **explicit input**:

```java
@Async
public CompletableFuture<String> load(String authenticatedUser) {
    return CompletableFuture.completedFuture(
        "loaded-for-" + authenticatedUser);
}
```

This is a method in a suitable `@Async` bean, not a standalone Java class. The caller reads identity from `ReactiveSecurityContextHolder` inside the pipeline, verifies authorization, and passes needed arguments. When passing multiple permissions/metadata, design an appropriate immutable object with clear trust boundaries; never log full tokens/passwords or pass arbitrary security contexts to workers outliving the request.

### 7.3. Why does calling `subscribe()` manually "lose context"?

Wrong in a WebFlux handler:

```java
public Mono<String> broken() {
    username().subscribe(name -> audit(name));
    return Mono.just("queued");
}
```

*This is an illustrative snippet assuming `audit` exists.* Calling `subscribe()` creates a separate subscription; it is not managed by WebFlux like the returned chain and **is not guaranteed to receive the outer request subscription's context**. It also detaches error/cancellation lifecycles, potentially letting work continue after the client closes the connection or the request finishes.

Correct when the work belongs in the request:

```java
public Mono<String> connected() {
    return username()
        .flatMap(name -> auditReactive(name).thenReturn("queued"));
}
```

Here `auditReactive(String)` is a service returning `Mono<Void>` (e.g., non-blocking audit). If auditing must run independently as a durable job, enqueue a verified request with explicit identity and permissions, proper idempotency/expiry, and re-verify permissions on the worker. Never expect Reactor Context to survive for the entire lifetime of a background job.

### 7.4. Never edit Context to spoof authentication

In unit tests, you can call `contextWrite(ReactiveSecurityContextHolder.withAuthentication(testAuthentication))`. In production, however, a username from `X-User`, query parameters, or a JSON body **must never** be turned into a trusted `Authentication` and attached to Reactor Context. Security filters must verify credentials, token signatures/issuer/audience, sessions, or trusted mechanisms, and authorization must still run. Propagation is **carrying verified identity**, not minting new permissions.

## 8. Runnable Spring Boot WebFlux lab

We will build a WebFlux app with HTTP Basic and two demo users. It exposes `GET /chain`, using `publishOn`, `subscribeOn`, a timer, and `boundedElastic` before re-reading the username; `GET /future` illustrates a `CompletableFuture` call rejoining the Reactor pipeline. Both require authentication.

### 8.1. Project setup and dependencies

From [Spring Initializr](https://start.spring.io/), create a Spring Boot 3.x Gradle project with Java 17+ and dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, and **Spring Security Test**. In the `build.gradle` generated by Initializr, the dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is a **dependencies snippet**; keep the Spring Boot plugins, dependency management, repositories, Java toolchain, and Gradle wrapper provided by Initializr. Do not add `spring-boot-starter-web` to the demo if you want WebFlux as the inbound server; when both MVC and WebFlux starters are present, Spring Boot 3.x defaults to MVC.

File layout:

```text
src/main/java/demo/contextpropagation/
  ContextPropagationApplication.java
  SecurityConfig.java
  ContextController.java
src/test/java/demo/contextpropagation/
  ContextControllerTests.java
  StandaloneContextTests.java
```

### 8.2. Entry point

Create `src/main/java/demo/contextpropagation/ContextPropagationApplication.java`:

```java
package demo.contextpropagation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextPropagationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextPropagationApplication.class, args);
    }
}
```

`@SpringBootApplication` scans beans in package `demo.contextpropagation` and subpackages; the three main classes share this package.

### 8.3. Security filter chain and user store

Create `src/main/java/demo/contextpropagation/SecurityConfig.java`:

```java
package demo.contextpropagation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/chain", "/future").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

Spring Security WebFlux authenticates HTTP Basic and places `SecurityContext` into the request's Reactor Context; the controller **does not manually create** a user via `contextWrite`. `alice-pass` and `bob-pass` are dummy credentials solely for this lesson. In real products, use HTTPS, a real identity source, and credential protection; HTTP Basic only Base64-encodes credentials in the header without encrypting the transport.

### 8.4. Controller observing context after schedulers and Future

Create `src/main/java/demo/contextpropagation/ContextController.java`:

```java
package demo.contextpropagation;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ContextController {

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/chain")
    public Mono<String> chain() {
        return username()
            .publishOn(Schedulers.parallel())
            .flatMap(first ->
                Mono.delay(Duration.ofMillis(10))
                    .then(username())
                    .map(second -> first + "|" + second))
            .flatMap(prefix ->
                Mono.fromCallable(() -> 7)
                    .subscribeOn(Schedulers.boundedElastic())
                    .flatMap(value -> username()
                        .map(third -> prefix + "|" + third + "|" + value)))
            .subscribeOn(Schedulers.parallel());
    }

    @GetMapping("/future")
    public Mono<String> future() {
        return username()
            .flatMap(caller ->
                Mono.fromFuture(() -> CompletableFuture.supplyAsync(
                        () -> "loaded-for-" + caller))
                    .flatMap(result -> username()
                        .map(inContext -> result + "|" + inContext)));
    }
}
```

This is a **runnable class** inside the project declaring the dependencies above. Explaining each stage of `/chain`:

1. `username()` reads the authenticated principal from Reactor Context.
2. `publishOn(Schedulers.parallel())` moves downstream signals onto the `parallel` scheduler without changing the user.
3. `Mono.delay(10ms)` introduces a scheduler-backed async step. After `then(username())`, context is still read within the same subscription.
4. `Mono.fromCallable(() -> 7).subscribeOn(Schedulers.boundedElastic())` represents a small synchronous task on the bounded elastic scheduler. The fixed number 7 makes testing easy; it does not prove blocking I/O "turns into" reactive I/O.
5. `flatMap(value -> username()...)` reads context again after the scheduled task.
6. `subscribeOn(Schedulers.parallel())` on the outer pipeline affects source subscription scheduling; it does not "turn on" context propagation, since context was already supplied by Spring Security.

With HTTP Basic username `alice`, the `/chain` response is expected to be exactly:

```text
alice|alice|alice|7
```

With `bob`:

```text
bob|bob|bob|7
```

Do not claim the two reads ran on the same thread, nor require identical thread names in logs. The proof to verify is **consistent principal** and **no cross-request mixing**.

In `/future`, `CompletableFuture.supplyAsync` produces a result using the `caller` value extracted earlier from context. Code **inside the future does not access the security context**. After the future completes and `Mono.fromFuture` emits the value, `flatMap` returns to the reactive publisher and can read context within the same subscription. For Alice, the response is:

```text
loaded-for-alice|alice
```

`Mono.fromFuture(() -> ...)` defers future creation until subscription. It is suitable for illustrating the bridge; for production tasks, consider bounded executors, timeouts, cancellation, idempotency, and permission checks in the backend doing the work. Never let futures freely use the common pool for large-scale blocking I/O.

### 8.5. Running HTTP

From the root directory of the created Gradle project:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Send requests once the server is listening on `localhost:8080`:

```bash
curl -i http://localhost:8080/chain
curl -i -u alice:alice-pass http://localhost:8080/chain
curl -i -u bob:bob-pass http://localhost:8080/chain
curl -i -u alice:alice-pass http://localhost:8080/future
```

On Windows PowerShell, use `curl.exe` instead of `curl` if the shell maps another alias. Verification table:

| Request | Expected HTTP | Expected body on success |
|---|---:|---|
| `GET /chain` without Authorization | `401` | Not fixed |
| `GET /chain` as Alice | `200` | `alice|alice|alice|7` |
| `GET /chain` as Bob | `200` | `bob|bob|bob|7` |
| `GET /future` as Alice | `200` | `loaded-for-alice|alice` |

`WWW-Authenticate` headers, error response bodies, and request logs vary by server/version. The mandatory security outcomes are that unauthenticated clients cannot access the endpoints and identity never morphs into someone else across scheduler/future bridges.

## 9. Automated tests independent of thread names

### 9.1. HTTP integration tests with WebTestClient

Create `src/test/java/demo/contextpropagation/ContextControllerTests.java`:

```java
package demo.contextpropagation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ContextControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/chain")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceKeepsIdentityAcrossSchedulers() {
        client.get().uri("/chain")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("alice|alice|alice|7");
    }

    @Test
    void bobDoesNotInheritAliceIdentity() {
        client.get().uri("/chain")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("bob|bob|bob|7");
    }

    @Test
    void futureBridgeRejoinsReactorContext() {
        client.get().uri("/future")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("loaded-for-alice|alice");
    }
}
```

This is a JUnit 5 class using a random-port server to test **real HTTP through the Spring Security chain**. Usernames are authenticated against the demo user store and pass through the scheduler-using controller itself. The tests do not guess thread names, making them more stable than asserting specific scheduler threads.

### 9.2. Standalone unit test with `contextWrite` and StepVerifier

Spring Security itself supplies context inside a WebFlux server. When testing a **standalone publisher/service**, you can attach a **simulated trusted authentication** within subscription scope using `withAuthentication`.

Create `src/test/java/demo/contextpropagation/StandaloneContextTests.java`:

```java
package demo.contextpropagation;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class StandaloneContextTests {

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @Test
    void testContextSurvivesSchedulerBoundaries() {
        Authentication alice =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

        Mono<String> pipeline = username()
            .publishOn(Schedulers.parallel())
            .flatMap(first -> Mono.delay(Duration.ofMillis(5))
                .then(username())
                .map(second -> first + "|" + second))
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice|alice")
            .verifyComplete();
    }

    @Test
    void withoutContextThereIsNoImplicitPrincipal() {
        StepVerifier.create(username())
            .verifyComplete();
    }
}
```

In the first test, `withAuthentication(alice)` takes effect for **upstream** publishers in the subscription. The second test attaches no context, so `ReactiveSecurityContextHolder.getContext()` completes empty; the identity from the first test is not stored in any global variable. Neither case proves the framework verifies passwords; that is the security chain's job in the HTTP tests.

Run in the Gradle project:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Expect 6 passing tests: 4 integration tests and 2 unit tests. Do not assume exact Gradle/JUnit stdout because task names, timings, and log configuration may differ. If tests fail to run, verify the Java toolchain, Spring Boot plugin, `reactor-test` dependency, and matching package/classpath.

## 10. How does context flow across multiple service layers?

Suppose a controller calls `OrderService`, then `PermissionService`, then a reactive repository:

```text
SecurityWebFilterChain authenticates request
  -> Reactor Context holds Authentication
  -> Controller returns Mono
       -> OrderService.readOrders()
           -> flatMap(...)
           -> PermissionService.check()
               -> ReactiveSecurityContextHolder.getContext()
           -> R2DBC/WebClient (reactive publisher)
       -> Reactor pipeline completes
  -> WebFlux writes HTTP response
```

When services **return Publishers** for WebFlux/the framework to compose and subscribe, context remains in the subscription as long as operators and adapters propagate properly. Therefore, reactive service APIs should favor `Mono<T>`/`Flux<T>` and avoid `void` methods that call `subscribe()` internally, since callers lose the ability to await results, errors, and cancellation.

A business method can read Authentication:

```java
public Mono<String> readForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .flatMap(auth -> repository.findByOwner(auth.getName()))
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No permitted data")));
}
```

This is **illustrative design code**, assuming `repository.findByOwner` returns `Mono<String>` and is called only after HTTP authentication/authorization. For real data requests, check resource access rights in the service/repository rather than assuming an arbitrary `auth.getName()` permits viewing any record. Returning an exception from `switchIfEmpty` merely illustrates an empty-stream handler, not a suggestion to return 500 for every missing-data case. In production, separate "unauthenticated", "forbidden", and "not found" via explicit policies.

### 10.1. Method security also relies on Reactor Context

Spring Security Reactive method security can use `@EnableReactiveMethodSecurity` and `@PreAuthorize` on publisher-returning methods:

```java
// Service snippet; requires @EnableReactiveMethodSecurity in configuration.
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<String> readReport() {
    return repository.findReport();
}
```

Do not use Servlet-style `@EnableMethodSecurity` and assume it automatically works identically for WebFlux reactive methods. `@EnableReactiveMethodSecurity` reads the security context from Reactor Context to evaluate permissions during subscription. In the HTTP Basic test example in section 8, only `ROLE_USER` exists, not `SCOPE_orders.read`; running this snippet requires configuring matching real authorities.

## 11. Distinguishing tracing/MDC from security context

These are two distinct questions:

- **Security context:** "Who is authenticated, what authorities do they hold, and which request/subscription do they belong to?" Accessed via `ReactiveSecurityContextHolder` inside the reactive pipeline.
- **Observability context:** "Which traceId/spanId/requestId should appear in logs, metrics, and tracing across operations?" Can integrate Reactor Context with Micrometer Context Propagation, OpenTelemetry, or MDC per configuration.

Reactor supports integrating `io.micrometer:context-propagation` and provides **automatic context propagation** modes such as `Hooks.enableAutomaticContextPropagation()`. In supporting Reactor 3.x versions, this mechanism can restore `ThreadLocal` values **with registered accessors** from Reactor Context at appropriate points; it requires the dependency and activation before subscriptions you want covered. That does **not** mean:

- Arbitrary `ThreadLocal` variables suddenly propagate across every thread and every `Executor`.
- An independent `CompletableFuture.supplyAsync` gains permission to read Reactive Security Context inside its callback.
- Detached `subscribe()` calls carry the HTTP request's context.
- Authentication/authorization can be skipped when sending requests to other services.
- A global hook should be enabled merely to "patch" code that is wrongly reading `SecurityContextHolder`.

When security context is needed inside Reactor, the standard approach remains `ReactiveSecurityContextHolder.getContext()`. ThreadLocal bridges for frameworks or legacy libraries must be tested explicitly with the specific configuration, ensuring cleanup and preventing identity leakage between requests sharing a pool.

## 12. Diagnosing context loss in real systems

When encountering an empty `ReactiveSecurityContextHolder.getContext()` or an unexpected principal:

1. **Check the inbound stack and authentication.** Is the real server WebFlux or MVC? Are `SecurityWebFilterChain` and `ReactorContextWebFilter` properly configured? Does the endpoint require authentication or is it `permitAll`? Without a valid identity, having no context is expected.
2. **Search for manual `subscribe()`.** A fire-and-forget task often creates a detached subscription unmanaged by WebFlux.
3. **Inspect bridges to `CompletableFuture`/`@Async`/callbacks.** Is code reading `SecurityContextHolder` inside a non-Reactor callback? If identity is needed, read it in the pipeline and pass it explicitly.
4. **Check `contextWrite` scope.** `Context` is supplied upstream; downstream reading operators will not see an entry placed above them.
5. **Check custom publishers/adapters.** When using non-Reactor libraries or creating custom publishers in ways that drop subscriber context, inspect adapters and make sure calls are composed.
6. **Check for event-loop blocking.** Correct context does not guarantee performance; `block()` or improper synchronous I/O can cause timeouts that look like "lost context".
7. **Test two users concurrently or interleaved.** Alice/Bob identity assertions should verify each request's principal without relying on thread names. Strictly avoid storing `Authentication` in a static field or shared cache as a "current user".
8. **Check security policy after obtaining principal.** Having a context does not mean access to every endpoint; authentication and authorization are two steps. JWT scope/role rules must still be enforced and audited.
9. **Distinguish local context from remote boundaries.** Reactor Context does not cross TCP/HTTP/Kafka automatically. If a downstream service needs identity, design delegation tokens/trust and verify on the receiving side.
10. **Watch cancellation and errors.** If a request is canceled, a background job should not continue indefinitely with stale context; design proper timeouts/cancellation and independent authorization for background tasks.

### Typical bugs

| Symptom | Common cause | Resolution |
|---|---|---|
| `username()` empty in GET handler | Missing authentication or publisher runs outside request subscription | Check security chain, invocation path, and subscription |
| `SecurityContextHolder` returns `null` after `publishOn` | Using ThreadLocal in a reactive pipeline | Use `ReactiveSecurityContextHolder` |
| `username()` works before/after `flatMap` but empty inside Future callback | Future callback is outside Reactor | Pass verified identity as a parameter |
| Test with `withAuthentication` passes while real endpoint returns 401 | Test only mocks context without testing HTTP Basic/token | Write a `WebTestClient` integration test through the security chain |
| Two requests mix up usernames | Identity stored in static/mutable singleton field or mismanaged ThreadLocal | Keep data per subscription; never store in global state |
| `contextWrite` has no effect at a trailing `flatMap` | Entry applies upstream only | Place `contextWrite` in the right scope and test with `deferContextual` |
| Need to log traceId but MDC is empty | No bridge/accessor for ThreadLocal | Check Micrometer context propagation and lifecycle |
| An `@Async` task still uses an old request's user | Long-running task, arbitrary identity passing, or TL leak | Design dedicated job context/expiry/authorization |
| `Mono.fromCallable` uses `boundedElastic` yet threads stay occupied long | Blocking adapter is not truly non-blocking | Limit concurrency; move to genuine reactive APIs where appropriate |

## 13. Exercises and answers

**Exercise 1 — Does `publishOn` lose the user?** A pipeline calls `ReactiveSecurityContextHolder.getContext()` before and after `publishOn(Schedulers.parallel())`, with all steps inside an authenticated WebFlux subscription. Do we need to copy `SecurityContext` into `ThreadLocal` ourselves?

**Answer:** No. Within a properly composed Reactor chain, context follows the subscriber across schedulers. If code after `publishOn` uses ThreadLocal `SecurityContextHolder`, fix how it reads context rather than unconditionally copying identity.

**Exercise 2 — Does `subscribeOn` create a new authentication?** Add `subscribeOn(Schedulers.boundedElastic())` to a publisher that has no context.

**Answer:** No. `subscribeOn` selects the scheduler for subscription/source work; it does not log in or create an `Authentication`. To have context, the request must be authenticated by Spring Security or a test must supply a trusted context for that subscription.

**Exercise 3 — Inside `CompletableFuture.supplyAsync`, can you call `ReactiveSecurityContextHolder.getContext().block()` to get the user?**

**Answer:** You should not. The HTTP request's Reactor Context does not appear automatically in an external callback, and calling `block()` will not recover what is missing. Read the user in the Reactor pipeline before creating the Future, pass a controlled parameter, and rejoin the pipeline via `Mono.fromFuture`.

**Exercise 4 — Why is a `contextWrite(ctx -> ctx.put("id", "R1"))` not always visible to a subsequent operator?**

**Answer:** `contextWrite` applies upstream as subscription travels backward up the chain; operators placed downstream may lie outside the scope of that change. Use `Mono.deferContextual` at the right position to verify.

**Exercise 5 — A controller calls `auditMono.subscribe()` and immediately returns `Mono.just("ok")`. What is the risk?**

**Answer:** It creates an independent subscription; errors, context, cancellation, and HTTP lifecycle may diverge. Compose with `flatMap`/`then`. If a durable job is needed, enqueue an authenticated event with explicit permissions rather than relying on request context.

**Exercise 6 — Should you enable `Hooks.enableAutomaticContextPropagation()` to fix all security bugs?**

**Answer:** No. It is a tool for bridging Reactor Context with registered ThreadLocals via context-propagation, mainly for library integration; it does not change authentication contracts or automatically carry context into arbitrary futures/callbacks or remote services. Using `ReactiveSecurityContextHolder` for Reactor Security code is the proper foundation.

**Exercise 7 — Why are Alice and Bob tests more valuable than testing thread names?**

**Answer:** Thread names/IDs vary as schedulers dispatch work; what must be protected is that the principal is not lost and never leaks between user subscriptions. Asserting exact responses per user provides direct evidence.

## 14. Technical summary

```text
HTTP authentication (Spring Security WebFlux)
  -> SecurityContext in the request subscription's Reactor Context
       |
       +-- publishOn(scheduler) ----- context still follows subscriber
       |
       +-- subscribeOn(scheduler) --- context still follows subscriber
       |
       +-- flatMap / delay / WebClient (Reactor publisher)
       |      -> read via ReactiveSecurityContextHolder
       |
       +-- fromCallable().subscribeOn(boundedElastic)
       |      -> Reactor operator keeps context
       |      -> Java callable must not assume ThreadLocal auth
       |
       +-- CompletableFuture / @Async / external Executor
       |      -> non-Reactor callback has no automatic context
       |      -> pass verified identity explicitly
       |      -> Mono.fromFuture(...) to rejoin the pipeline
       |
       +-- new subscribe(), detached from request
              -> separate subscription; do not assume inherited context

contextWrite(...) -> sets Context upstream within the subscription
ReactiveSecurityContextHolder -> WebFlux API to read SecurityContext
SecurityContextHolder -> default ThreadLocal, not a substitute for Reactor Context
```

**The right debugging question:** "Is this code part of the same Reactor subscription and reading via the proper context API?" rather than "Which thread is it running on?". When crossing boundaries into other technologies, design explicit, testable identity propagation, authentication, and authorization.

## Official documentation

- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Reactor Mono API — fromFuture](https://projectreactor.io/docs/core/3.6.1/api/reactor/core/publisher/Mono.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
