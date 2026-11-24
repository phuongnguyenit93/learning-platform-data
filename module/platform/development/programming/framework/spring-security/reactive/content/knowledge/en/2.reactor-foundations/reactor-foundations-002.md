# Publisher Creation Time, Execution Subscription, and Access Evaluation

**Context:** Spring Security Reactive (WebFlux) on top of Project Reactor. This lesson explains precisely what happens when creating a `Mono`/`Flux`, when a `Subscriber` subscribes, and when Spring Security decides to allow or deny access. These are three related yet distinct events.

## 1. Three Milestones to Distinguish

| Milestone | Meaning | Key takeaway |
| --- | --- | --- |
| **Assembly (creating/composing the Publisher)** | Java code calls methods such as `Mono.just(...)`, `Mono.defer(...)`, `map`, and `flatMap` to build the processing flow description. | Simply having a `Mono` object **does not prove** data queries have run or permissions have been checked. However, Java expressions passed to operators can still execute immediately. |
| **Subscription** | A `Subscriber` registers to receive signals; for a *cold* source, subscribing triggers data generation and propagates `request` upstream toward the source. | Each new subscription typically re-triggers a cold source; `retry`/`repeat` can create additional subscriptions. |
| **Authorization (access evaluation)** | Security components use `Authentication`, access rules, and the protected target to decide allow/deny. | Evaluation timing depends on **where rules are applied**: WebFilter for HTTP, interceptor for methods, or checks composed into the Publisher by the application. |

**Foundational rule:** "Without a subscription, a cold pipeline has not emitted data yet" applies only to *cold pipeline* execution. It **does not** negate Java code executing immediately when calling a method, evaluating arguments, creating `Mono.just`, opening connections outside the pipeline, or *hot* source activity.

## 2. Assembly Does Not Mean Execution

Consider three ways of constructing a `Mono`:

- `Mono.just(load())`: Java must call `load()` to evaluate the argument **before** `Mono.just` is invoked. The result is captured at assembly time; a subsequent subscription emits the already computed value.
- `Mono.fromSupplier(this::load)` (similar to `fromCallable`): each time a cold Publisher is subscribed to, Reactor invokes the value-producing function. Without a subscription, this function does not run.
- `Mono.defer(() -> repository.findById(id))`: the function creating the **inner Publisher** is only called at subscription time. Suitable when queries/data sources must be built from state at subscription time, or to avoid calling Publisher-creating APIs too early.

`map(value -> ...)` and `flatMap(value -> ...)` create operators at assembly time; their callbacks execute when the stream emits the corresponding signal, usually after subscription. Code **outside** the callbacks still runs immediately:

```java
System.out.println("assembly: right now");
Mono<String> result = Mono.just("hello")
    .map(value -> {
        System.out.println("map: on receiving onNext");
        return value.toUpperCase();
    });
```

This snippet only **assembles** `result`, so only the line `assembly: right now` is printed. Once `result` is subscribed to and data is requested, the `map` callback runs. This is an illustrative snippet, not a standalone Java program.

### Runnable Java 17 Example: Demonstrating the Timings

Create a Maven project with the following two files. The example uses Reactor Core 3.7.0 so results are stably reproducible; no WebFlux startup is needed.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-timing</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/ReactorTimingDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class ReactorTimingDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> just =
            Mono.just(compute("just", counter));
        Mono<Integer> supplier =
            Mono.fromSupplier(() -> compute("supplier", counter));
        Mono<Integer> defer =
            Mono.defer(() -> Mono.just(compute("defer", counter)));

        System.out.println("created Publisher");
        just.subscribe(value -> System.out.println("just received " + value));
        supplier.subscribe(value -> System.out.println("supplier received " + value));
        supplier.subscribe(value -> System.out.println("supplier received " + value));
        defer.subscribe(value -> System.out.println("defer received " + value));
    }

    private static int compute(String source, AtomicInteger counter) {
        int number = counter.incrementAndGet();
        System.out.println(source + " computed #" + number);
        return number;
    }
}
```

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReactorTimingDemo
```

**Program stdout lines** (excluding Maven's own output if any):

```text
just computed #1
created Publisher
just received 1
supplier computed #2
supplier received 2
supplier computed #3
supplier received 3
defer computed #4
defer received 4
```

Explanation: `compute("just", ...)` runs immediately when creating the Publisher; `supplier` runs **twice** because there are two subscriptions; `defer` only creates the inner `Mono.just` when subscribed to. The example intentionally uses no scheduler so stdout order is deterministic. Calling `subscribe()` directly here is only for demonstration in a CLI program; **do not do this inside a WebFlux handler**.

## 3. Who Subscribes in WebFlux, and When Is Access Checked?

In a normal HTTP request, the WebFlux/Reactor Netty framework orchestrates subscribing to the stream serving the response; controller code should simply **return** `Mono`/`Flux`. You do not need to call `subscribe()` in a controller. There are two important security layers:

1. **HTTP Security** — `ServerHttpSecurity.authorizeExchange(...)` rules are configured at application startup; when handling each request, security filters (including `AuthorizationWebFilter` when applicable) inspect the request and `Authentication` in the processing chain. **Declaring** `pathMatchers(...).hasRole(...)` at startup is not a one-time permanent grant. The decision is made per request when the security chain runs, before allowing the request to proceed to the corresponding resource.
2. **Method Security** — `@EnableReactiveMethodSecurity` enables enforcement based on Spring AOP and Reactor Context. When calling a bean through its proxy, `@PreAuthorize` requires an authorization check before allowing the target method invocation; the reactive mechanism attaches the decision to Publisher processing and can be asynchronous. `@PostAuthorize` checks after the protected invocation/result portion, so it cannot replace an upfront gate for operations with side effects.

Conceptual path for a request configured with both layers:

```text
HTTP request
    |
    v
Spring Security WebFilter chain
    |-- authenticate / retrieve SecurityContext for the request
    |-- authorizeExchange: check authorization at the HTTP layer
    |-- DENY --> stop the protected path and handle the error
    |
   ALLOW
    v
WebFlux handler/controller
    |
    v
Invoke service bean through Spring AOP proxy
    |-- @PreAuthorize: authorization decision for the method
    |-- DENY --> do not execute the target method
    |
   ALLOW
    v
Execute source publishers (DB / HTTP / computation) upon subscription
    |
    v
Emit data or error -> WebFlux writes the response
```

The diagram depicts the **order of responsibilities**, not a guarantee that every step happens at one single moment or on one fixed thread. Some Publishers are assembled while the request is being processed; initializing security configuration at startup, invoking a controller, creating a Publisher, and subscribing are distinct events. In particular, Java code running during *assembly* can cause side effects before custom authorization-checking operators are subscribed to.

With HTTP Basic, an **unauthenticated** request is typically challenged with `401 Unauthorized`; an authenticated user lacking permissions typically receives `403 Forbidden`. The exact outcome also depends on the authentication entry point, access-denied handler, and whether the response has already been committed. Do not assume every security error in a stream that has already emitted data can be turned into HTTP 403.

## 4. Example Integrated into a Spring WebFlux + Spring Security Application

The following snippet is **integration code** in a Spring Boot WebFlux project that already has the `spring-boot-starter-webflux` and `spring-boot-starter-security` dependencies, along with appropriate authentication configuration. It is not a standalone Spring Boot application because it omits the `@SpringBootApplication` class and user source. Place the classes in a component-scanned package.

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/reports/**").hasRole("READER")
                .anyExchange().authenticated())
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
    }
}

@Service
class ReportService {
    @PreAuthorize("hasRole('READER')")
    public Mono<String> read(String id) {
        // Only compute data when subscribed and after passing the authorization layer.
        return Mono.fromSupplier(() -> "report-" + id);
    }
}

@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> read(@PathVariable String id) {
        return service.read(id); // Return Publisher; do not self-subscribe.
    }
}
```

In the example, an account with the `ROLE_READER` authority can pass both the HTTP check and `@PreAuthorize`. An account missing the role is denied at the HTTP layer (so the controller is normally not invoked); if the service is called through its proxy via another path, `@PreAuthorize` still protects the method. `hasRole("READER")` and `hasRole('READER')` evaluate the `ROLE_READER` authority using Spring Security's default prefix. `Mono.fromSupplier` models deferred work; in a real application, reactive database access should use a reactive repository/R2DBC returning a Publisher instead of placing blocking JDBC calls inside a supplier.

**Boundary to distinguish:** `@PreAuthorize` protects **method invocations going through the Spring AOP proxy**, not arbitrary code that already ran before hitting the proxy. Self-invocation `this.read(...)` within the same bean, unproxied methods, or causing side effects inside argument expressions can bypass the intended gate. Place checks at the actual boundary and keep sensitive operations inside the guarded portion.

## 5. Reactive SecurityContext Is Bound to the Subscription

Spring Security Reactive uses `ReactiveSecurityContextHolder` to retrieve the `SecurityContext` from the **Reactor Context**, bound to the subscriber stream. This is not the "always have the principal in the current ThreadLocal" assumption. When a pipeline executes across different schedulers/threads, Reactor Context can still travel properly along the reactive chain; splitting the flow with a manual `subscribe()` or relying on `ThreadLocal` can lose the required security context.

Example accessing the authenticated username in a pipeline:

```java
Mono<String> currentUser =
    org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(org.springframework.security.core.context.SecurityContext::getAuthentication)
        .map(org.springframework.security.core.Authentication::getName);
```

This snippet is a **fragment** in an application configured with Spring Security. It does not read the username when declared; at subscription time, the operator reads the context of the corresponding subscriber. In WebFlux, security filters typically establish the context per request. In tests or flows running outside a request, you can supply a context manually:

```java
Authentication alice =
    new TestingAuthenticationToken("alice", "unused", "ROLE_READER");

Mono<String> readAsAlice = currentUser
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
```

In the second fragment, `Authentication`, `TestingAuthenticationToken`, and `ReactiveSecurityContextHolder` are the Spring Security types to import; `readAsAlice` only emits `"alice"` when subscribed to. `contextWrite` applies *upstream* of the subscription. It is not a way to "log in" over HTTP system-wide; it is a technique for supplying context scoped to a pipeline/test.

When access policies vary by user, **read the context and make decisions along each subscription's execution path**. Do not capture an `Authentication` from an old request at bean initialization time, store it in a static field, or share a Publisher holding cached sensitive results across multiple users.

## 6. Placing Authorization Before Side Effects: Pitfalls and Fixes

If you implement access conditions yourself using `Mono<Boolean>`, chain **all sensitive operations** after the allow branch. A common mistake is thinking that simply placing a value inside `Mono.just` automatically defers the value-producing operation.

**Wrong — loads data eagerly at assembly, before the authorization result exists:**

```java
Mono<Report> result = Mono.just(loadSensitiveReport(id)); // Method runs immediately!
return accessPolicy.canRead(id)
    .flatMap(allowed -> allowed
        ? result
        : Mono.error(new AccessDeniedException("Forbidden")));
```

**Correct ordering — only creates the data-loading Publisher after an allow result:**

```java
return accessPolicy.canRead(id)
    .flatMap(allowed -> allowed
        ? Mono.defer(() -> reactiveReportRepository.findById(id))
        : Mono.error(new AccessDeniedException("Forbidden")));
```

Both snippets are **illustrative fragments** (`Report`, `accessPolicy`, `reactiveReportRepository`, and `loadSensitiveReport` are application-defined). `accessPolicy.canRead(id)` returns `Mono<Boolean>` and must be a trustworthy permission check for the current principal. If the data source returns a genuinely cold Publisher, creating it early typically does not run I/O yet; `defer` makes the boundary explicit and prevents source-creation logic from running prematurely. When you need protection against permission changes between the check and the operation, enforce checks/rules close to the data or use an appropriate transaction; "lazy" alone does not solve TOCTOU.

You must also guard **side effects** such as writing data, publishing events, processing payments, calling external services, or logging sensitive secrets. A Publisher rejected at subscription time cannot "undo" side effects that already ran earlier in Java code.

## 7. How Multiple Subscriptions, Retries, and Caching Affect Behavior

| Case | Impact |
| --- | --- |
| Subscribing twice to a cold `Mono.fromSupplier(...)` | The supplier typically runs twice, and security checks inside each subscription can also run twice. |
| `retry(n)` on error | Can **resubscribe** to the source and repeat permission checks, queries, or side effects. Design idempotency for write operations. |
| `repeat(n)` | Resubscribes after completion, potentially re-running work. |
| `cache()`, `share()`, hot source | Can reuse or share results across subscribers; "every subscribe = always calls a fresh source" no longer holds. |
| `subscribeOn`/`publishOn` | Changes where part of a pipeline runs; by themselves they do not grant authorization, do not self-subscribe, and do not replace Reactor Context. |

Dangerous example: caching a whole `Mono` returning user A's information and sharing that instance for user B's request. If the sensitive value is cached, later requests may receive A's value without re-running the inner logic. Even with `@PreAuthorize` at certain points, you must still verify **every access path** and key caches by principal/permissions, or only cache truly public data. Do not use a global `Mono.cache()` to store identity-dependent results.

## 8. Observing Real Timings with Logging and Tests

In Reactor, you can place the following hooks in a pipeline when investigating behavior:

```java
Mono<String> traced = Mono.defer(() -> {
        System.out.println("defer: created source on subscribe");
        return Mono.just("ok");
    })
    .doOnSubscribe(s -> System.out.println("subscribed"))
    .doOnNext(v -> System.out.println("onNext: " + v))
    .doOnError(e -> System.out.println("onError: " + e.getClass().getSimpleName()));
```

This is a fragment; the timing of each log depends on operator placement. `doOnSubscribe` proves a subscription at that position, **not** that a permission was granted. Also monitor *permit/deny* events at security boundaries or test with different identities/authorities. To test source execution timing, use `StepVerifier` (`reactor-test` dependency in test scope); to test WebFlux policies, use `WebTestClient` and security test support. Minimum test cases should prove: without subscribing, the supplier does not run; subscribing twice runs a cold source twice; lacking authority does not trigger the sensitive data stream; two principals' contexts do not mix; retry/cancel leave no unintended side effects.

## 9. Misconceptions to Eliminate

1. **"Creating a Mono means the DB already ran or authorization already happened."** False for most cold publishers; however, eager arguments/initialization logic still run, so inspect the **entire Java expression**.
2. **"Not seeing subscribe() in code means the endpoint does not run."** The WebFlux framework actively subscribes; controllers should return Publishers so the framework controls lifecycle, errors, and cancellation.
3. **"@PreAuthorize can protect code that runs before hitting the proxy."** No. Only calls passing through the proxy are protected; ensure there are no side effects outside the boundary.
4. **"Having @PostAuthorize makes all side effects safe."** No. A post-check cannot replace protecting before a sensitive operation.
5. **"ThreadLocal always holds the request's Authentication."** Do not rely on that in reactive code; use `ReactiveSecurityContextHolder`/Reactor Context along the same Publisher chain.
6. **"Every subscribe creates a fresh query."** Not true for hot/cached/shared Publishers; distinguish cold sources from retained results.
7. **"Calling subscribe() in a service guarantees it runs."** This detaches work from the HTTP flow, complicating error handling, cancellation, and security context; returning/chaining Publishers is the standard approach.
8. **"Handling onErrorResume with default data is always harmless."** Catching `AccessDeniedException` and returning sensitive data or HTTP success can break security policies. Classify errors explicitly.

## 10. Self-Check Comprehension

**Scenario A:** `Mono<String> p = Mono.just(load());` is created and nobody subscribes. Does `load()` run? **Yes** — Java evaluates `load()` immediately; no emission from the Publisher does not mean no side effect occurred.

**Scenario B:** `Mono<String> p = Mono.defer(() -> repository.findById(id));` is created and subscribed to twice. Is two DB accesses guaranteed? **If** the repository returns a cold Publisher and both subscriptions execute completely, two I/O rounds usually occur. `cache`/hot publishers/cancellation can alter the outcome, so do not state it as an absolute.

**Scenario C:** `authorizeExchange` config was initialized at startup. Has request X's authorization already been decided? **No**; rules are declared ahead of time, while the decision requires the request/Authentication context at processing time.

**Scenario D:** A user without `ROLE_READER` calls `/api/reports/1` in the Section 4 example. Does the report-producing supplier run? **Not on the normal processing path**, because HTTP authorization denies it first; if another path invokes the service via the proxy, method authorization denies it as well. This assumes no side effects exist outside those security gates.

**Scenario E:** Two users subscribe to the same cached Publisher already holding private data. Is it safe? **Not by default**; a shared cache can return the previous user's result. Design per-user isolation and policy enforcement before sharing.

### Official References

- Project Reactor, *Introduction to Reactive Programming* (assembly, subscription, cold/hot): https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, *EnableReactiveMethodSecurity*: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html

**Takeaway to apply:** Always ask three separate questions: **(1) Which expressions execute immediately when creating the Publisher? (2) Who subscribes, how many times, and with whose context? (3) At which boundary is the authorization decision made—before or after sensitive operations?** Only by answering all three can you accurately assess execution timing and access safety in Spring Security Reactive.