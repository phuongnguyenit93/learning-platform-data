# Detecting Thread Blocking with BlockHound in Spring Security Reactive

## Learning Objectives

In a **Spring Security – reactive** application, a prolonged synchronous operation during authentication/authorization processing can pin a Reactor Netty **event-loop thread**, slowing down many other requests sharing that thread. This lesson shows how to use **BlockHound** to detect blocking calls on threads designated as non-blocking, write repeatable tests with Reactor `StepVerifier`, analyze failures, and fix the boundary between blocking and reactive tasks.

After this lesson, you will be able to:

1. Explain why blocking in `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, custom `WebFilter`s, or controller-side publishers degrades WebFlux responsiveness.
2. Distinguish **blocking** operations (waiting on I/O or sleeping a thread), CPU-heavy work, **backpressure** signals, and improper `block()` usage; understand BlockHound's detection boundaries.
3. Install BlockHound in JVM tests, and write a test that is **red for application behavior yet green for detection**: intentionally execute `Thread.sleep` on `Schedulers.parallel()` and expect `BlockingOperationError`.
4. Move a synchronous API that must be retained onto `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; verify pipeline behavior after the fix.
5. Know when a test can yield false negatives, why you must not “fix” issues by allowlisting everything, and how to observe real impact via latency/throughput under load.

**Scope:** runtime blocking detection on Reactor/WebFlux, with examples specific to **Spring Security Reactive**. BlockHound is a performance/threading-correctness diagnostic tool; it does not replace authentication, authorization, or HTTP 401/403 testing.

## 1. The Problem: Where Is Blocking on the Event Loop Dangerous?

In the WebFlux model using Reactor Netty, a small number of event-loop threads handle I/O and non-blocking callbacks for a large number of connections. Unlike a “one thread per request” mental model, code for one request can temporarily run on a thread simultaneously serving other requests.

Conceptual diagram:

~~~text
Client request
     |
     v
Reactor Netty event loop (non-blocking)
     |
     v
SecurityWebFilterChain
     |
     +--> AuthenticationWebFilter / ReactiveAuthenticationManager
     |             |
     |             +--> ReactiveUserDetailsService / token verifier
     |
     +--> authorization checks / custom WebFilter
     |
     v
Handler -> Mono/Flux -> HTTP response
~~~

Suppose an authenticator calls a synchronous JDBC repository and waits 300 ms on the event loop. During that wait, **the entire event-loop thread** cannot continue other callbacks queued on that same thread. The number of affected requests can be far larger than the number of requests querying the database. This defect typically causes elevated tail latency (p95/p99), connection queueing, and degraded throughput under load, even though a single isolated request still returns the right result.

Common places where blocking creeps into the security chain:

- `ReactiveUserDetailsService.findByUsername` calling a synchronous JDBC/JPA repository, synchronous LDAP query, synchronous API, or local file read.
- `ReactiveAuthenticationManager.authenticate` using a synchronous HTTP client, `Thread.sleep` for retries, waiting on `Future.get`, or building a publisher and calling `block()` inside.
- A `WebFilter` writing audits/logs to a synchronous sink, calling a synchronous driver, or acquiring locks that can contend for long periods.
- A branch in `@PreAuthorize` method security or a custom authorization bean querying a synchronous data source before returning or inside a publisher assembly.
- A controller-side service calling the same blocking dependency after security lets the request through; the impact is identical because it still runs on the event loop.

**Key point:** a `Mono<T>` / `Flux<T>` return type does not guarantee the inner logic is non-blocking. Wrapping a blocking query in `Mono.just(repository.find(...))` only changes the return type; the synchronous call still executes eagerly when constructing the publisher.

## 2. What Does BlockHound Do and Not Do?

**BlockHound** is a **Java instrumentation agent**: when installed into the JVM, it intercepts known blocking methods and throws `reactor.blockhound.BlockingOperationError` if they are invoked from threads marked **non-blocking**. Threads created by `Schedulers.parallel()` or `Schedulers.single()` belong to Reactor's default non-blocking group; Reactor Netty event-loop threads must also remain non-blocking. Conversely, `Schedulers.boundedElastic()` is designed to host synchronous blocking tasks that must wait, so BlockHound normally **does not throw merely for blocking on boundedElastic**.

Comparison table:

| Scenario | Can BlockHound Catch It? | Explanation |
| --- | --- | --- |
| `Thread.sleep(20)` on `Schedulers.parallel()` | **Yes**, this is the standard canary test | `BlockingOperationError` upon subscription |
| Reading files/sockets via instrumented synchronous APIs on the event loop | **Possibly**, depends on method/JDK/version | Must test actual execution paths |
| Synchronous JDBC/JPA on the event loop | **Possibly**, if passing through monitored blocking methods | Does not automatically cover every call in every driver |
| `Mono.block()` on a Reactor non-blocking thread | **Forbidden by Reactor**; error may be `IllegalStateException` | Does not necessarily surface as `BlockingOperationError` |
| `Thread.sleep(20)` inside `boundedElastic` | **Normally no** | Blocking has been offloaded to a dedicated pool; still consumes a thread and time |
| CPU-heavy code (bcrypt, huge loops, massive JSON) | **Not guaranteed** | Does not necessarily call an instrumented blocking primitive |
| Synchronous API call on a normal JUnit thread | **Usually no** | Test threads are not automatically classified as non-blocking |
| Slowdowns from GC, network congestion, queues, or uninstrumented locks | **Incomplete** | Requires metrics, profiling, and load testing as well |

BlockHound **does not detect every cause of system slowness**. It does not measure execution time, does not compute p99, and does not prove that moving work to `boundedElastic` is enough to scale. Conversely, some internal software or libraries calling uninstrumented blocking methods can slip past. Therefore, tests must include a **smoke test** that intentionally triggers a known blocking call to prove the agent is actually active.

## 3. Installing BlockHound in a Spring Boot/WebFlux Project

The example below assumes a **Spring Boot 3.x / Spring Security 6.x** project using Java 17+ and Gradle Groovy DSL, with Spring dependency versions managed by the Spring Boot plugin/BOM. Add to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'io.projectreactor.tools:blockhound:1.0.18.RELEASE'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    // Required for BlockHound's instrumentation/redefinition of native methods
    // on compatible JDK 13+ versions, e.g. JDK 17/21.
    jvmArgs '-XX:+AllowRedefinitionToAddDeleteMethods'
}
~~~

`1.0.18.RELEASE` is a stable release published in October 2026; in real use, verify compatibility with the exact JDK and Reactor versions pinned in your project. `io.projectreactor.tools:blockhound` is distinct from `io.projectreactor:reactor-test`: you need both if you want `StepVerifier` to assert errors from the agent.

**About JVM configuration:** BlockHound performs runtime instrumentation/retransformation. For JDK 13 and newer, the BlockHound project instructs adding `-XX:+AllowRedefinitionToAddDeleteMethods`. Some JDKs emit warnings about dynamic agent loading or enforce policies forbidding attach; inspect **real errors from the test JVM** and verify agent/JDK versions instead of ignoring installation failures. Depending on your environment, you can load the agent via `-javaagent:...` at process startup, but do not mix both approaches carelessly or hardcode a JAR path across incompatible environments.

**Install early and once:** call `BlockHound.install()` before tests run the reactive code under inspection, ideally in test/JVM bootstrap or `@BeforeAll` of a dedicated test setup. BlockHound applies JVM-wide; subsequent `install()` calls do not automatically reset a different configuration. For large test suites, use a single unified installation strategy plus a test confirming instrumentation is active. Never quietly disable BlockHound when a test turns red.

## 4. Complete Java Test: Catching Blocking and Verifying Isolation

Place the file at `src/test/java/demo/security/reactive/BlockHoundDetectionTest.java`. This example runs in **a Gradle project configured with the dependencies from section 3**; no web server or database is needed. The test code uses Java 17+, JUnit Jupiter, and Reactor:

~~~java
package demo.security.reactive;

import java.time.Duration;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockHoundDetectionTest {

    @BeforeAll
    static void installAgent() {
        BlockHound.install();
    }

    // Synchronous API that intentionally blocks the thread: used solely as a test fixture.
    private static Mono<String> legacyBlockingCall() {
        return Mono.fromCallable(() -> {
            Thread.sleep(20);
            return "ok";
        });
    }

    @Test
    void detectsBlockingOnNonBlockingScheduler() {
        StepVerifier.create(
                legacyBlockingCall()
                    .subscribeOn(Schedulers.parallel()))
            .expectError(BlockingOperationError.class)
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void canRunLegacyBlockingCallOnBoundedElastic() {
        StepVerifier.create(
                legacyBlockingCall()
                    .subscribeOn(Schedulers.boundedElastic()))
            .expectNext("ok")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void pureNonBlockingPipelineCompletesNormally() {
        StepVerifier.create(
                Mono.just("ok")
                    .map(String::toUpperCase)
                    .subscribeOn(Schedulers.parallel()))
            .expectNext("OK")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Run the test from the Gradle root directory of the module/project containing that class:

~~~bash
./gradlew test --tests demo.security.reactive.BlockHoundDetectionTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests demo.security.reactive.BlockHoundDetectionTest
~~~

There is no fixed stdout to match: Gradle prints reports depending on configuration. The **expectation** when instrumentation is properly configured is that all three tests PASS.

### First test: the test must see an error, so why does it PASS?

`legacyBlockingCall()` uses `Mono.fromCallable`, so `Thread.sleep(20)` executes only when a subscriber actually subscribes. `subscribeOn(Schedulers.parallel())` shifts subscription and callable execution onto a Reactor thread marked non-blocking. When `Thread.sleep` is invoked, BlockHound throws `BlockingOperationError`. `StepVerifier.expectError(BlockingOperationError.class)` matches the `onError` signal; that is the **desired outcome** of a detection test.

Illustrative stack trace (line numbers and JDK details may vary):

~~~text
reactor.blockhound.BlockingOperationError:
  Blocking call! java.lang.Thread.sleep
  at ...Thread.sleep(...)
  at ...BlockHoundDetectionTest.lambda$legacyBlockingCall$0(...)
~~~

If you remove `BlockHound.install()` and nothing else installs the agent, `Thread.sleep` completes normally, the publisher emits `"ok"`, and the first test **FAILS** because no `BlockingOperationError` arrives. This turns the test into a **canary/smoke test** guarding against a “green” CI pipeline where BlockHound is silently inactive.

### Second test: why is there no longer a `BlockingOperationError`?

`Schedulers.boundedElastic()` is meant for **synchronous blocking tasks that must be kept temporarily**. `Mono.fromCallable` defers the call until subscription; `subscribeOn(boundedElastic)` runs the callable on an appropriate worker. Receiving `"ok"` and `onComplete` proves the task completed on a thread pool intended for blocking. This is **blocking isolation**, not turning a synchronous JDBC/HTTP API into non-blocking code or guaranteeing infinite scalability.

`boundedElastic` has bounded workers and queues: heavy blocking, long wait times, or an undersized external pool can still saturate it. When a true non-blocking client exists (R2DBC, reactive driver, WebClient), prefer that client in WebFlux flows. Bounded elastic serves as a bridge while synchronous adapters cannot yet be replaced.

### Third test: the control test

`Mono.just("ok").map(String::toUpperCase)` uses no known blocking primitives. The test verifies it emits `"OK"` and completes on a non-blocking scheduler. Having both a **positive failure-detection test** and a **valid negative control test** distinguishes a “false positive from the agent” from a normal non-blocking pipeline.

**Why include `verify(Duration...)`?** Asynchronous tests should have timeouts to prevent hanging when a scheduler or setup fails. `StepVerifier` must subscribe; calling `legacyBlockingCall()` and just asserting `assertNotNull(...)` does not trigger code inside the publisher.

## 5. Applying Directly to Spring Security Reactive

### 5.1. Anti-pattern: using a blocking store inside `ReactiveUserDetailsService`

The example below shows **code you should not use**:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    UserDetails user = legacyStore.findByUsername(username);
    return Mono.justOrEmpty(user);
}
~~~

Suppose `legacyStore.findByUsername` is a synchronous JDBC query—it runs **immediately when the method is called**, before the `Mono` is even returned. If invoked by `ReactiveAuthenticationManager` during a request on the event loop, the thread can be blocked. Changing it to `Mono.just(legacyStore.findByUsername(username))` does not help either because the argument is evaluated before `Mono.just` runs.

Even:

~~~java
return Mono.fromCallable(() -> legacyStore.findByUsername(username));
~~~

although **lazy**, will still block on the event loop if subscribed on the event loop. You must fix both **execution timing** and **execution scheduler**.

### 5.2. Proper adapter when a legacy store is unavoidable

The illustrative code below is a class-standalone Java adapter that compiles in a module with Spring Security and Reactor. `LegacyStore` is an interface you implement against an existing datasource, so this snippet **does not connect to a database itself**:

~~~java
package demo.security.reactive;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyUserDetailsAdapter
        implements ReactiveUserDetailsService {

    public interface LegacyStore {
        // Synchronous query, may wait on I/O.
        UserDetails findByUsername(String username);
    }

    private final LegacyStore store;

    public LegacyUserDetailsAdapter(LegacyStore store) {
        this.store = store;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return Mono.fromCallable(
                    () -> store.findByUsername(username))
                .subscribeOn(Schedulers.boundedElastic())
                .switchIfEmpty(Mono.error(
                    new UsernameNotFoundException(username)));
    }
}
~~~

Step-by-step mechanism:

1. Calling `findByUsername` creates a cold `Mono` **without querying** the store yet.
2. When the authentication pipeline subscribes, `subscribeOn` requests a `boundedElastic` worker to execute the `fromCallable` source.
3. The `UserDetails` result flows downstream; `null` from the callable produces an empty publisher, and `switchIfEmpty` turns it into `UsernameNotFoundException`.
4. Reactor Context propagates via operator mechanics across scheduler switches; do not spawn custom threads and rely on Servlet's `SecurityContextHolder` ThreadLocal to guess identity.

In production, the adapter should also enforce **appropriate client/driver timeouts**, connection limits, concurrency limits, and queue/latency monitoring. `Mono.timeout` limits wait time from the subscriber's perspective, but **does not automatically cancel** a synchronous JDBC operation stuck inside a driver; driver/network timeouts remain vital. Never spin up a new thread per request.

### 5.3. Relation to `SecurityWebFilterChain` and method security

An application may have authorization in both `SecurityWebFilterChain` and `@EnableReactiveMethodSecurity`. BlockHound does not know “which request is login” or “which annotation is `@PreAuthorize`”; it watches for **blocking calls on threads disallowed from blocking**. If an expression, custom authorization service, or logic invoked behind `@PreAuthorize` runs a synchronous API on the event loop, BlockHound can point near the blocking method, without judging whether the security rule itself is right or wrong.

Example paths to inspect proactively:

~~~text
POST /login or GET /private
   -> reactive authentication (user lookup / token validation)
   -> authorization
   -> secured service
   -> data source
~~~

A `StepVerifier` test directly on the service can force `Schedulers.parallel()` to **prove the old adapter fails**. After fixing, the service test must complete as expected. For the full HTTP path, use Spring Boot/WebFlux tests or `WebTestClient` configured with the real security chain and run requests through the server; do not replace the real service with a Mockito mock if your goal is to find blocking inside that service itself. Plain `WebTestClient.bindToController` or tests subscribing publishers on a JUnit thread **do not automatically recreate production event-loop scenarios**.

To ensure an integration test is meaningful, verify:

- The request actually traverses the relevant authentication/authorization path.
- BlockHound is installed in **the same JVM** executing the inspected code.
- At least one canary test confirms the agent is instrumenting; absence of BlockHound errors in one HTTP test **does not automatically prove** every branch is non-blocking.
- Deny or unauthenticated cases may short-circuit early: to test an inner lookup, use fixtures/requests that actually reach that lookup.

## 6. Placement of `subscribeOn`, `publishOn`, and Common Pitfalls

### WRONG case: blocking happens before creating the `Mono`

~~~java
String value = legacyClient.fetchSync();  // blocking happens IMMEDIATELY
return Mono.just(value)
           .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` affects **publisher subscription**, and cannot turn back time to relocate a `fetchSync()` that already ran. Moreover, placing `publishOn(boundedElastic)` after this synchronous call does not help either because the source has already executed.

### RIGHT case: wrap the blocking call inside a lazy source

~~~java
return Mono.fromCallable(() -> legacyClient.fetchSync())
           .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` ensures the call is deferred until subscription; `subscribeOn` specifies the scheduler for subscription/source execution. A suitable `publishOn` can move **subsequent** operators, but cannot substitute for isolating a synchronous blocking source that runs before the switch. When composing multiple publishers, trace the execution thread of each source/`flatMap` rather than looking only at the outermost publisher's scheduler.

### Dangerous case: calling `block()` inside a pipeline

~~~java
return reactiveHttpClient.get()
    .retrieve()
    .bodyToMono(String.class)
    .map(body -> anotherMono().block()); // Never use on the event loop.
~~~

Reactor actively rejects many `block()` calls when executed on threads marked non-blocking. The error is typically an `IllegalStateException` stating that `block()/blockFirst()/blockLast()` are unsupported on that thread. This differs from primitives like `Thread.sleep` that BlockHound reports as `BlockingOperationError`. Fix it by **composing publishers** with `flatMap`/`zipWhen` instead of waiting synchronously:

~~~java
return reactiveHttpClient.get()
    .retrieve()
    .bodyToMono(String.class)
    .flatMap(body -> anotherMono()
        .map(other -> body + ":" + other));
~~~

Both snippets use `reactiveHttpClient` and `anotherMono()` as hypothetical dependencies to illustrate **operator structure**, not standalone Java programs. In real code, declare/import them from your project's clients/services.

## 7. Integrating BlockHound into Controlled Testing Workflows

**At the unit/reactor test level:** test blocking tasks via lazy sources running on `Schedulers.parallel()` and expect `BlockingOperationError`. Add a test for the fixed version running on `boundedElastic`; the result must be accurate and the full pipeline must complete. This level is fast, stable, and requires no HTTP port.

**At the Spring integration test level:** run real beans/security chains; for services touching data sources, use controlled fakes/stubs at the service's **dependency** to simulate known blocking calls, rather than mocking out the code under test. When testing real requests, confirm execution reaches login/token lookup or protected handlers before drawing conclusions. Install BlockHound at JVM bootstrap rather than having each test configure different allowlists.

**At the CI level:** always run the canary test suite; if instrumentation fails due to JDK/agent issues, fail the build and investigate. Maintain an integration job for supported JDK/Spring Boot combinations. Add benchmarks/load tests measuring p50/p95/p99, throughput, queue/connection saturation, and thread utilization to confirm fixes work under real load.

**Separating application errors from instrumentation errors:**

| Symptom | Possibility | Action |
| --- | --- | --- |
| `BlockHound.install()` fails before tests run | JVM forbids attach/redefinition or incompatible agent | Read setup stack trace, verify JDK, dependency, and JVM flags; do not interpret as “no blocking” |
| Canary `Thread.sleep` on `parallel()` does **not** throw `BlockingOperationError` | Agent inactive or call did not run on a non-blocking thread | Check installer execution, `parallel` scheduler, and actual subscription |
| Stack trace reports `Blocking call! ...Thread.sleep` | Monitored blocking call on a non-blocking thread | Find the nearest application frame in the trace; swap API or isolate lazy source on `boundedElastic` |
| `IllegalStateException` about `block()` | Violated Reactor rule against blocking on non-blocking threads | Remove `block()`, compose chain with reactive operators |
| Direct JUnit-thread test “passes silently” yet requests are slow | Did not simulate non-blocking threads or missed the buggy branch | Force the right scheduler in unit tests; use server integration and load testing |
| Canary PASSES yet p99 remains high | CPU-heavy work, uninstrumented I/O, contention, `boundedElastic` saturation, or other causes | Profiler/JFR, Reactor/Netty metrics, driver metrics, and load tests |

## 8. Customizing BlockHound: Keep Narrow and Justified

BlockHound allows customizing some behaviors via `BlockHoundIntegration`/`BlockHound.Builder`. An API example is:

~~~java
BlockHound.install(builder ->
    builder.allowBlockingCallsInside(
        "com.example.legacy.LibraryInternals",
        "initializeCache"));
~~~

This is a **configuration example**, used only when you have verified that specific blocking region is genuinely acceptable in its exact context. It is **not** a blanket solution to silence errors. The class/method names above are hypothetical and do not exist in the framework. And because `install` executes once per JVM, customizations must be registered when installing the agent; a late `install` may not apply as you expect.

When might an allowlist be considered? For instance, a library performing brief synchronous initialization proven to run only before the server accepts requests, yet flagged by a special test setup. Before permitting it, gather evidence on call timing, impact scope, and cost, plus a dedicated test confirming real request paths do not depend on that exception. Never allowlist arbitrary calls inside `ReactiveAuthenticationManager`, the event loop, controllers, or schedulers just to make CI green.

If there is a custom native/blocking method that BlockHound does not recognize, the Builder also offers `markAsBlocking` taking the exact class/method name and JVM method descriptor. Pair this with a dedicated canary test because a wrong descriptor or JDK update can silently let regressions slip through.

Limitations to always keep in mind:

- BlockHound only detects instrumented primitives/methods on threads matching the non-blocking predicate. `boundedElastic` is not marked non-blocking by default; a “clean” test on that pool does not prove code is non-blocking.
- Installing instrumentation can depend on JDK version, agent attach permissions, and library initialization order. Tests must never silently ignore installation failures.
- BlockHound cannot replace resource exhaustion protection. Use `boundedElastic` with bounds; high concurrency workloads need non-blocking drivers or load-shedding designs.
- ThreadLocal and Reactor Context are not identical; manually spawning `Thread`/`CompletableFuture` does not preserve authentication context automatically. Keep pipelines in Reactor operators and test context propagation when integrating Spring Security.
- Middleware error handling for `BlockingOperationError` should not turn serious performance defects into “successful” responses; let tests catch them and fix the root cause at the source.

## 9. Lab Evaluation Checklist

The lab can be considered complete when:

1. The `detectsBlockingOnNonBlockingScheduler` test PASSES **because it received** `BlockingOperationError` from a known `Thread.sleep` call on `Schedulers.parallel()`.
2. If BlockHound installation is temporarily disabled (in an isolated test run), the canary flips to FAIL; this proves the test genuinely depends on the agent.
3. The test moving the blocking task to `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` returns the exact value and completes within the timeout.
4. You can explain why `Mono.just(legacyStore.find(...))` and `Mono.fromCallable(...)` without a scheduler can still block on the event loop.
5. You can pinpoint places in the Spring Security Reactive flow prone to blocking (user lookup, token/introspection, audit, authorization service), and distinguish testing a service in isolation from testing requests through the security filter chain.
6. When a test turns red, you diagnose whether it is an **agent setup failure**, **non-blocking thread violation**, **application logic bug**, or **tool limitation** instead of bumping timeouts or allowlisting broadly.
7. You evaluate performance with separate metrics/profiling/load tests rather than concluding “zero blocking” solely from a green BlockHound suite.

## References

- BlockHound README (instrumentation mechanics, installation, JVM requirements): https://github.com/reactor/BlockHound
- BlockHound Quick start (canary test and agent setup): https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md
- BlockHound Customization (allow/disallow and customization capabilities): https://github.com/reactor/BlockHound/blob/master/docs/customization.md
- BlockHound releases (verify stable/JDK compatibility): https://github.com/reactor/BlockHound/releases
- Reactor Core Reference, FAQ “How Do I Wrap a Synchronous, Blocking Call?”: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Security Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
