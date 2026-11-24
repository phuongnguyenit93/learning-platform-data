# Limitations of Bridging Synchronous Code to Reactive Using Adapters

> **Context:** Spring Security for Spring WebFlux applications, Java 17+, Reactor. This lesson focuses on using adapters to reuse **synchronous authentication** components (such as `AuthenticationManager`, JDBC/LDAP clients, legacy credential verification libraries) inside a reactive processing chain. The goal is to understand the technical and security limits of this bridge before choosing a solution.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a method returning `Mono<Authentication>` does not necessarily perform *non-blocking* work.
- Choose where to place an adapter and scheduler for a legacy authentication component; recognize where threads and connections are still consumed.
- Distinguish thread-bound `SecurityContextHolder` from Reactor-Context-based `ReactiveSecurityContextHolder`.
- Accurately assess impacts on load, timeouts, cancellation, transactions, authentication errors, and WebFlux security flows.
- Write tests proving work is deferred until subscription and the system still returns valid authentication/authorization outcomes.

## 2. Why Do We Need an Adapter?

A legacy servlet system might authenticate like this:

~~~java
Authentication result = authenticationManager.authenticate(authentication);
~~~

This call returns a result or throws an exception synchronously. Internally it may query JDBC, make synchronous LDAP/HTTP calls, verify passwords with CPU-heavy algorithms, read caches, or use `ThreadLocal`. In WebFlux, the authentication pipeline normally consumes `Mono<Authentication>` via `ReactiveAuthenticationManager` and runs inside WebFilters.

An adapter builds an **interface-level bridge** between the two models:

~~~text
WebFlux request
  -> SecurityWebFilterChain / AuthenticationWebFilter
  -> ReactiveAuthenticationManager.authenticate(...) : Mono<Authentication>
  -> [adapter + scheduler]
  -> AuthenticationManager.authenticate(...) : Authentication
  -> onNext/onComplete or onError signal
~~~

Spring Security's `ReactiveAuthenticationManagerAdapter` accepts an existing `AuthenticationManager`. The adapter lets a reactive chain invoke legacy authentication logic; it **does not turn synchronous JDBC into R2DBC, does not make blocking LDAP/HTTP non-blocking, and does not convert an entire servlet system into WebFlux**.

**Three distinct concepts:**

| Concept | Reality | What must not be inferred |
| --- | --- | --- |
| Reactive API | Returns a publisher, e.g. `Mono<Authentication>`; begins work when subscribed | That every I/O operation is non-blocking |
| Offloading blocking work | Runs synchronous work on an appropriate thread instead of the event loop | That underlying work becomes faster or instantly cancellable |
| End-to-end reactive | I/O layers support asynchronous/non-blocking operations with demand and cancellation signals | Achievable merely by changing return types in controllers or services |

## 3. Limit #1: Keeping the Event Loop Free Does Not Eliminate Blocking

WebFlux typically uses a small number of event-loop threads to serve many connections. Calling JDBC, LDAP, or `Thread.sleep` directly on the event loop makes one request hold the thread while waiting, increasing latency for unrelated requests.

**Wrong: the work already ran before `Mono` was created.**

~~~java
Mono<Authentication> authenticate(Authentication input) {
    return Mono.just(legacyManager.authenticate(input));
}
~~~

Java evaluates `legacyManager.authenticate(input)` immediately when the method is called; it is a synchronous call even though the result sits inside `Mono.just`. If called on the event loop, the event loop is still blocked. Exceptions can also be thrown before the publisher is returned.

**Correct for isolating blocking work, yet still blocking underneath:**

~~~java
Mono<Authentication> authenticate(Authentication input) {
    return Mono.fromCallable(() -> legacyManager.authenticate(input))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` defers work until subscription, and `subscribeOn` schedules the synchronous source onto the chosen scheduler. This is an **illustrative pattern for custom code**; when using `ReactiveAuthenticationManagerAdapter`, prefer the adapter's own scheduler configuration rather than wrapping extra scheduler layers unnecessarily.

`Schedulers.boundedElastic()` fits short-to-medium blocking I/O tasks because it bounds worker threads and queues. It does not remove wait time, thread memory overhead, connection-pool contention, or the risk of queue saturation. Placing `publishOn` at the end of a chain cannot undo a call already executed during `Mono.just`; source creation, invocation timing, and scheduler placement must be evaluated together.

## 4. Limit #2: Throughput and Resources Still Depend on Legacy

Suppose a blocking account lookup takes 200 ms on average. At 200 authentications/second, by Little's Law, the average concurrent operations needed is approximately:

~~~text
concurrency = throughput × latency
            = 200 requests/s × 0.2 s
            = 40 blocking operations
~~~

This is an illustrative calculation, not a benchmark guarantee. If the LDAP pool has only 10 connections, the JDBC pool has 15 connections, or the scheduler saturates, adding `Mono` will not remove the bottleneck. Latency typically spikes sharply once queues hit load thresholds.

Metrics to monitor include: concurrent authentications; p50/p95/p99 authentication latency; scheduler queue depth and wait time; DB/LDAP connection pool utilization; timeout counts; 401/403/5xx rates; CPU spent on password verification; and event-loop stalls. Growing threads unboundedly to “cure” blocking can exhaust RAM, increase context switching, and overload the backend.

**Distinguish I/O from CPU:** BCrypt/Argon2 are intentionally expensive, so password verification must never occupy the event loop. However, they are primarily CPU-bound; putting hashing tasks onto an oversized pool will not make the CPU compute faster. Measure load and bound concurrency per workload type. `boundedElastic` is a useful boundary for blocking I/O, not a universal optimal configuration for every computation.

## 5. Limit #3: Timeouts and Cancellation Cannot Control Every Blocking Call

A publisher can be cancelled when a client disconnects, times out, or a downstream operator stops requesting items. Yet a synchronous JDBC/LDAP/HTTP call stuck inside a library method **may keep occupying its thread and connection** even after subscription cancellation.

~~~text
Client cancels request
  -> Reactor sends cancel
  -> pipeline no longer needs result
  -> legacy I/O may still wait for socket/driver timeout
~~~

Likewise, `.timeout(Duration.ofSeconds(2))` triggers a Reactor-level timeout error; it does not configure socket timeouts, query timeouts, or guarantee aborting every blocking call. Some libraries support interruption or request cancellation, while others do not; verify actual driver behavior.

Implementation rules:

1. Set timeouts **on the client/driver and each dependency** (connect, read, query) aligned with the request's latency budget.
2. Bound concurrent authentication tasks and queues; define load-shedding behavior upon saturation.
3. Never retry indefinitely on invalid credentials or failing LDAP/DB calls. Automatic auth retries can also overload services or trip account lockout policies.
4. Ensure connections/resources are released cleanly in synchronous code, even on error; monitor tasks still running after client cancellation.
5. Preserve existing rate limiting, lockout, auditing, and brute-force defenses; an adapter does not add these automatically.

## 6. Limit #4: SecurityContext and ThreadLocal Are Not Equivalent

In servlet apps, `SecurityContextHolder` binds `SecurityContext` to a thread (typically via `ThreadLocal`) for the scope of request handling. In WebFlux, work can switch threads and execution schedules; Spring Security uses `ReactiveSecurityContextHolder` to read/write `SecurityContext` via the **Reactor Context carried with the subscription**.

~~~java
Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
~~~

This snippet is a method used inside a security-configured WebFlux app, not a standalone Java program. In a normal filter chain, Spring Security populates the Reactor Context for resolved authentication.

Avoid the following in reactive code:

- Calling `SecurityContextHolder.getContext().getAuthentication()` and assuming it holds the current request's guaranteed identity: it may be empty or belong to a different context.
- Copying `SecurityContext` into a shared `ThreadLocal` without strict scoping and cleanup; this risks cross-request identity leaks when threads are reused.
- Assuming `subscribeOn`/`publishOn` automatically propagates every MDC, locale, transaction, or custom ThreadLocal to worker threads. Reactor Context and ThreadLocal are distinct mechanisms; any context bridging must be explicitly configured and tested.

If a legacy `AuthenticationManager` relies on reading user/request data via ThreadLocal, **prefer passing required data explicitly through `Authentication` or method arguments**, and audit providers, interceptors, and audit hooks. Be especially cautious when legacy code reads servlet HTTP request/session objects: WebFlux does not provide those servlet objects by default.

## 7. Limit #5: You Cannot Reuse the Servlet Security Filter Chain As-Is

The two security orchestration models differ:

| Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- |
| `SecurityFilterChain`, `HttpSecurity`, servlet `Filter` | `SecurityWebFilterChain`, `ServerHttpSecurity`, `WebFilter` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityContextHolder` commonly with thread-bound context | `ReactiveSecurityContextHolder` with Reactor Context |
| `@EnableMethodSecurity` for synchronous chains | `@EnableReactiveMethodSecurity` for reactive method security |

An adapter only helps **one authentication boundary** conform to the reactive interface. It does not convert `OncePerRequestFilter` into `WebFilter`, nor carry over servlet filter ordering, session handling, CSRF, exception handlers, or servlet semantics into WebFlux.

You must properly configure `SecurityWebFilterChain`, credential converters (such as HTTP Basic or bearer tokens), authentication success/failure handling, authorization rules, and session/context repositories as needed by the application. For reactive method security, protected business methods must return supported reactive types; you cannot keep thread-bound interceptors intact and expect an adapter to handle them.

## 8. Example of a Controlled Bridge Configuration

Suppose the system **already has a working synchronous `AuthenticationManager` bean** (including providers, password encoder, lockout/auditing). In a Spring Boot 3.x / Spring Security 6.x app using `spring-boot-starter-webflux` and `spring-boot-starter-security`, the configuration below illustrates wiring that bean into WebFlux:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerAdapter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.scheduler.Schedulers;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            AuthenticationManager legacyManager) {
        ReactiveAuthenticationManagerAdapter adapter =
                new ReactiveAuthenticationManagerAdapter(legacyManager);
        adapter.setScheduler(Schedulers.boundedElastic());
        return adapter;
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**How to read this example:**

1. The legacy `AuthenticationManager` still authenticates and returns `Authentication` or throws `AuthenticationException` as before. Such a bean must be provided by the legacy portion of the application; this snippet does not create providers or user data itself.
2. `ReactiveAuthenticationManagerAdapter` wraps the synchronous manager and returns a publisher for WebFlux. `setScheduler` determines where the legacy work runs; pick the scheduler after understanding the actual work and resource bounds.
3. `ServerHttpSecurity` accepts the reactive manager, sets public paths, and requires authentication elsewhere; HTTP Basic is a **demo mechanism** so requests carry credentials. For JWT/OAuth2, use the appropriate mechanism rather than assuming this Basic setup fits every system.
4. When CSRF, sessions, CORS, custom authentication entry points, or custom error handling are required, configure them per real security requirements. Never disable CSRF merely because you use reactive or an adapter.
5. This is a **Spring application configuration fragment**, not a standalone `main` file compiled with `javac`. It requires WebFlux/Spring Security dependencies and a real `AuthenticationManager` bean.

Do not wrap this adapter *from the outside* in `Mono.fromCallable(...).subscribeOn(...)` if the adapter already handles scheduling. Instead, audit all **other** blocking calls outside the adapter.

## 9. When You Must Wrap Another Synchronous API Yourself

Not every blocking component has a built-in adapter. The example below is a complete Java 17 class in a project with Reactor Core (provided by `spring-boot-starter-webflux`); it defers a legacy lookup through a synchronous function and schedules it onto `boundedElastic`.

~~~java
package demo.security;

import java.util.Objects;
import java.util.function.Function;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyLookupBridge {
    private final Function<String, String> blockingLookup;

    public LegacyLookupBridge(Function<String, String> blockingLookup) {
        this.blockingLookup = Objects.requireNonNull(blockingLookup);
    }

    public Mono<String> findRole(String username) {
        return Mono.fromCallable(() -> blockingLookup.apply(username))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

The snippet above **illustrates blocking wait offloading only**, not a production authorization service: role data and access rights must be verified per system policy. `Mono.fromCallable` emits a value when the callable returns non-`null`; if it returns `null`, it completes empty. Thus “empty” must never be interpreted as a successful authentication.

The following JUnit 5 test verifies laziness without relying on sleep durations or thread names; it requires `reactor-test` in test dependencies. Place it in the test source tree of the same package:

~~~java
package demo.security;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LegacyLookupBridgeTest {

    @Test
    void lookupStartsOnlyWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();
        LegacyLookupBridge bridge = new LegacyLookupBridge(username -> {
            calls.incrementAndGet();
            return "mai".equals(username) ? "ROLE_USER" : null;
        });

        Mono<String> result = bridge.findRole("mai");
        assertEquals(0, calls.get());

        StepVerifier.create(result)
                .expectNext("ROLE_USER")
                .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

In a Spring Boot Gradle project configured with JUnit 5, verify `io.projectreactor:reactor-test` is in test dependencies, then run `./gradlew test` (Windows: `.\gradlew.bat test`). Expectation: **test passes**, with no required application stdout. The test proves laziness and return values; it **does not** prove throughput, JDBC cancellation on cancel, or end-to-end security.

## 10. Authentication Outcomes and Errors Must Preserve Exact Meaning

For `ReactiveAuthenticationManager.authenticate`, the contract is commonly understood as:

| Publisher signal | Meaning to handle |
| --- | --- |
| `onNext(Authentication)` then complete | Authentication accepted; object must accurately reflect principal and authorities |
| Empty completion (`Mono.empty()`) | Manager could not determine / does not handle this auth method; must not be treated as “login succeeded” |
| `onError(AuthenticationException)` | Authentication rejected; WebFlux Security routes to configured failure handling |
| `onError` from infrastructure error | Must distinguish backend failures, timeouts, unavailable services; never swallow errors and return a fake principal |

If a legacy provider returns `null` to mean “not applicable”, inspect the specific adapter and manager contract; avoid turning it into an authenticated `Authentication`. Never use `onErrorResume(e -> Mono.just(adminAuth))`, never grant default access when LDAP/DB fails, and never log passwords, access tokens, or secrets for debugging. Distinguish 401 (unauthenticated/invalid credentials), 403 (identified yet lacking authority), and 5xx (system error) with integration tests, matching the configured HTTP entry point and failure handler.

## 11. Transactions, Context, and Side State Are Not Converted Automatically

A synchronous `@Transactional` method relying on a JDBC-style transaction manager and thread-bound resources can finish on an offloaded thread **if the entire synchronous call and transaction stay within that single execution boundary**. Even so, that does not turn it into a reactive transaction.

Do not open a JDBC transaction via an interceptor and scatter work across multiple publishers/worker threads expecting the transaction, connection, or `ThreadLocal` to follow the signals automatically. Reactive transaction management uses reactive context and compatible drivers; migrating fully to reactive requires redesigning transaction boundaries and the persistence stack, such as adopting R2DBC where suitable.

You must also audit legacy auditing, MDC/tracing, quotas, retries, caches, request attributes, and the lifecycle of password encoders/providers. They may rely on threads or contain mutable state unsafe under higher concurrency. Using an adapter does not solve thread safety automatically and does not replace functional testing and security review.

## 12. Common Anti-Patterns

| Practice | Why it is dangerous | Fix |
| --- | --- | --- |
| `Mono.just(blockingCall())` | Blocking happens when creating the publisher | `Mono.fromCallable` + appropriate scheduler |
| Calling `.block()` or `.blockOptional()` on a WebFlux request path | Blocks worker thread; may be rejected by Reactor on non-blocking schedulers | Use `flatMap`/`map` and return publisher to the end of the chain |
| Using `Mono.defer(() -> Mono.just(blockingCall()))` thinking it is non-blocking | `defer` only delays execution; does not move blocking off the event loop | Offload properly with `subscribeOn` or a scheduler-aware adapter |
| Placing `publishOn` after a blocking call has already run | Schedulers cannot turn back time | Check source creation and invocation timing |
| Treating every `AuthenticationException` as `Mono.empty()` | Drops failure signal and may cause unwanted fallbacks | Preserve error/empty contract |
| Copying servlet `Filter`/`SecurityFilterChain` into WebFlux | Wrong filter and context infrastructure | Use `WebFilter`/`SecurityWebFilterChain` |
| Reading current user via `SecurityContextHolder` across arbitrary threads | Context is not guaranteed to match the request | Use `ReactiveSecurityContextHolder` |
| Setting only Reactor `timeout` without driver timeouts | Legacy calls can keep holding threads/sockets | Multi-layer timeouts, bulkheads, and observability |
| Wrapping every layer in `Mono` while keeping blocking JDBC/LDAP underneath | System remains constrained by threads and connection pools | Isolate blocking boundaries or migrate to native reactive drivers |

## 13. Pre-Production Testing Checklist

**Functional and security correctness**

- Valid credentials: matching principal and authorities; wrong credentials: authentication fails; unsupported provider: never auto-permits.
- Verify 401/403 distinction, DB/LDAP timeout behavior, lockout, auditing, and behavior when clients cancel requests.
- Authorization rules in `SecurityWebFilterChain` and `@EnableReactiveMethodSecurity` methods still apply after scheduler switches.
- High user concurrency: no cross-request leakage of `SecurityContext`, session data, or logs; zero sensitive info logged.

**Operational characteristics**

- Use `StepVerifier` to verify lazy publishers, outputs, and error paths; use `WebTestClient` to verify HTTP requests actually traversing the filter chain.
- High concurrency load: measure event-loop stalls, scheduler saturation, connection-pool waits, CPU hashing, p95/p99, and downstream backpressure.
- Test real timeouts on JDBC/LDAP clients, not just `Mono.timeout`; observe cancelled requests whose blocking work continues running.
- Benchmark before and after under identical loads and configs; establish concurrency limits, timeout budgets, and an actionable rollback plan.

## 14. When to Use an Adapter vs. Re-Architecting

| Scenario | Practical decision |
| --- | --- |
| Mandatory legacy library, moderate traffic, incremental WebFlux integration | Adapter + scheduler + timeouts + concurrency caps + tests is a reasonable transitional solution |
| Single blocking JDBC/LDAP call site with an existing replacement plan | Isolate at one clear boundary, measure, and gradually replace with proper reactive clients/drivers |
| Very high auth rate, strict low p99, mostly blocking I/O wait time | Prioritize replacing backend/driver with non-blocking APIs if feasible; evaluate caching/security policy and infra capacity |
| Entire app is still mostly synchronous MVC/JDBC code | Consider keeping the synchronous servlet model if it fits the rest better; WebFlux is not mandatory |
| Need true I/O cancellation and multi-step reactive transactions | Design end-to-end reactive rather than relying on adapters as the final answer |
| Legacy manager depends implicitly on servlet requests or ThreadLocal | Analyze and decouple dependencies first; pass identity data via explicit parameters/authentication |

**Technical conclusion:** An adapter is a tool for **compatibility and isolating blocking code**, not an automatic upgrade to performance, security, or transaction semantics. Proper design keeps the event loop clear, bounds load on synchronous parts, keeps the authentication contract crisp, and proves it with tests. When legacy limits dominate product requirements, replace the dependency or pick the fitting runtime rather than wrapping more publishers around it.

## References

- [Spring Security — ReactiveAuthenticationManagerAdapter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html)
- [Spring Security — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Project Reactor — FAQ: Wrap a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
