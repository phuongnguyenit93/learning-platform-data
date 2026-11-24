# Debugging Lost Security Context Across Thread Switches or Reactive Misuse

## 1. Symptom: Logged In, Yet Another Task Cannot See the User

In a Spring Security application, a hard-to-diagnose bug occurs when **the initial HTTP request authenticated successfully**, yet an asynchronous processing step sees `Authentication == null`, username `anonymousUser`, missing roles, or returns 401/403 even though the same request previously had an identity.

Common scenarios:

- A Servlet controller reads `SecurityContextHolder.getContext().getAuthentication()` and sees Alice; inside `CompletableFuture.supplyAsync(...)` or `@Async`, it sees null.
- A worker running on an `ExecutorService` occasionally sees the context of a **previous request**, not the current one. That can be a **cross-user identity leak**, worse than losing context.
- A Spring WebFlux app reads Servlet's `SecurityContextHolder` inside `Mono.map(...)`, `Flux.flatMap(...)`, or after `publishOn(...)` and gets null or inconsistent values.
- A reactive branch is invoked via a standalone `subscribe()` or bridged to a `Future`/callback outside the pipeline, causing that work to lose the subscriber context.
- Tests using `mockUser()` succeed at the HTTP layer while background work never receives the same identity, or tests run on a single thread and hide the real bug.
- Logs show a different thread, without telling you whether that itself is a bug.

**Crucial distinction: switching threads does not automatically lose context in Reactor.** Here is how the two models differ:

| Model | Where Spring Security Normally Stores Context | What Must Be Guaranteed |
| --- | --- | --- |
| Servlet/MVC, synchronous | `SecurityContextHolder`, usually `ThreadLocal`-based | Propagate context intentionally when handing work to a new thread/executor |
| Servlet/MVC, asynchronous | Built-in integration exists for **some** Servlet/MVC async paths; custom tasks still need verification | Never assume every `CompletableFuture`, `new Thread`, `@Async`, or callback library propagates automatically |
| Spring WebFlux/Reactor | `ReactiveSecurityContextHolder` uses **Reactor Context** bound to the subscriber | Keep work inside the pipeline; do not rely on Servlet `ThreadLocal` |
| Background job detached from a request | May **have no current HTTP identity** | Pass explicit actor/delegation metadata, and re-authenticate per business workflow when needed |

The goal of this guide is to **read symptoms accurately, reproduce bugs reproducibly, distinguish Servlet from reactive stacks, and fix the exact break in context**—not to patch around it by granting default permissions or faking identities.

## 2. Three Things Often Lumped Together as "Context"

Separate these three clearly to read logs and fix the right layer:

1. **SecurityContext**: holds `Authentication` (principal, authorities, and authenticated state). In Servlet, `SecurityContextHolder` uses a `ThreadLocal`-based strategy by default.
2. **Reactor Context**: a data structure bound to the **subscriber** and propagated through the `Mono`/`Flux` subscription protocol. Reactive Spring Security uses it to carry `SecurityContext` through the rest of the pipeline.
3. **Logging/trace context**: such as SLF4J MDC, request ID, or trace ID. This is **observability context**, not proof of authentication or authorization. A request with the right trace ID yet wrong `Authentication` is still a security bug.

`ThreadLocal` is bound to a **thread**; Reactor Context is bound to a **subscription**. Reactor can run across many threads, and one thread can serve many different subscribers. Hence measuring "the current thread differs from the initial thread" **does not prove** Reactor Context was lost.

Comparison diagram:

```text
Servlet request:
  thread-http-1
    SecurityContextHolder --> alice
       |
       +--> rawExecutor.submit(task)
                worker-2
                SecurityContextHolder --> usually empty
                (or worse: context leak if code sets it and forgets to clear)
       |
       +--> DelegatingSecurityContextExecutor.submit(task)
                worker-3
                context is populated while the task runs
                then cleaned up afterward

WebFlux request:
  subscriber of request A
    Reactor Context --> Authentication(alice)
       |
       +--> Mono.publishOn(otherScheduler)
                different thread, same subscription
                ReactiveSecurityContextHolder --> alice
       |
       +--> spawning an independent subscription/job/callback
                DOES NOT share the same Context by default
```

Neither model should read a client-supplied `userId` from a header, query param, or body and treat it as a substitute identity.

## 3. Identifying Failures via Logs and Status Codes

A single root symptom can surface in several ways:

| Symptom | Reasonable Initial Diagnosis | Do Not Jump to Conclusions |
| --- | --- | --- |
| Before `supplyAsync` sees Alice, inside task sees null | `ThreadLocal` does not transfer automatically to workers | Do not conclude the user failed to log in or gave a bad password |
| Inside task sees a different user | Possible context leak from improper `ThreadLocal`/`Authentication` retention | Never dismiss it as harmless "random" data |
| WebFlux after `publishOn` reads `SecurityContextHolder` and sees null | Reading the **wrong API for reactive** | Do not conclude `publishOn` drops Reactor Context |
| `ReactiveSecurityContextHolder.getContext()` is empty | No subscriber context, detached branch, or unauthenticated request | Do not immediately blame thread switching for losing context |
| `@PreAuthorize` in service denies after `@Async` | Check task executor, proxy invocation, and capture timing | Never disable method security to "fix" it |
| Valid login, HTTP 403 on POST | Could be CSRF or authorization, not necessarily lost context | Separate filter rejection from propagation failure |
| Unit tests pass, production fails under load | Tests lack concurrency or code retains context too long | Do not use `Thread.sleep(...)` as a fix |

A sound debugging workflow **never logs tokens, passwords, or serialized `Authentication` objects**. Record only non-sensitive markers: request ID, normalized endpoint, phase (`before-submit` / `inside-task` / `after-completion`), thread name, "authenticated present?", and a pseudonymized actor code when appropriate.

Example safe log format:

```text
trace=req-42 phase=before-submit thread=http-nio-8080-exec-2 authPresent=true
trace=req-42 phase=inside-raw-task thread=pool-1-thread-1 authPresent=false
trace=req-42 phase=inside-delegated-task thread=pool-1-thread-2 authPresent=true
```

This is an **illustrative format**, not fixed output printed by Spring Security. Logs should clarify checked values and task locations without exposing credentials or personal data.

## 4. Context in Servlet: Why Does ThreadLocal Not Follow an Executor?

In Servlet Spring Security, `SecurityContextHolder` typically uses `MODE_THREADLOCAL`. When a request enters the security pipeline, Spring Security loads/initializes the context for **the thread handling the request**. When the pipeline ends, the framework performs cleanup accordingly.

A new thread or a worker from a thread pool **does not automatically inherit** the submitting thread's `ThreadLocal`.

Conceptual example:

```java
Authentication before =
    SecurityContextHolder.getContext().getAuthentication();
// In an authenticated request: before may hold Alice's Authentication.

executor.execute(() -> {
    Authentication inside =
        SecurityContextHolder.getContext().getAuthentication();
    // With a raw executor, inside is usually null.
});
```

This is an illustrative snippet requiring `executor` and imports in a Spring Security project. Do not "fix" it by inserting:

```java
// DO NOT DO THIS: shares permissions across all users in the entire JVM.
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_GLOBAL
);
```

`MODE_GLOBAL` turns the security context into process-wide shared state, unsuitable for multi-request/multi-user applications. `MODE_INHERITABLETHREADLOCAL` is also **not a general cure for thread pools**: values inherited when creating a thread do not reflect whoever submits work later, and reused threads can retain stale state. Changing the global strategy also affects everything in the JVM.

### 4.1. Standard Approach: DelegatingSecurityContextRunnable/Executor

Spring Security provides wrappers:

- `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextCallable`;
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`;
- `DelegatingSecurityContextAsyncTaskExecutor` or matching Spring Task adapters.

The wrapper establishes the context while the task runs and cleans up afterward. With `DelegatingSecurityContextExecutor(delegate)` **without passing a fixed SecurityContext to the constructor**, context is captured at **submission time** from the caller. This fits independent requests when a task must run **on behalf of the request's caller at the time of submission**.

Conversely, passing **a fixed SecurityContext** to the constructor uses that exact context for every task. Accidentally passing Alice's context into a singleton executor at startup would run every task under Alice's identity—a severe authorization flaw. Use a fixed context only when intentionally designing a dedicated, tightly controlled service identity.

### 4.2. Runnable Java 17+ Spring Boot MVC Example Reproducing and Fixing the Bug

Create a **Servlet/MVC** Spring Boot 3.x / Spring Security 6.x project with dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`

Save the full code in:

```text
src/main/java/demo/context/ServletContextLabApplication.java
```

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextLabApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    // Real executor for running tasks. For demo use only.
    @Bean(destroyMethod = "shutdown")
    ExecutorService rawWorkers() {
        return Executors.newFixedThreadPool(2);
    }

    // Wrapper without fixed identity: captures context
    // at task submission time from the caller thread.
    @Bean
    Executor securedExecutor(
            @Qualifier("rawWorkers") ExecutorService workers) {

        return new DelegatingSecurityContextExecutor(workers);
    }

    static String callerFromSecurityContext() {
        Authentication auth = SecurityContextHolder
            .getContext()
            .getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return "missing-context";
        }
        return "actor=" + auth.getName();
    }

    @RestController
    static class DemoController {
        private final ExecutorService rawWorkers;
        private final Executor securedExecutor;

        DemoController(
                @Qualifier("rawWorkers") ExecutorService rawWorkers,
                @Qualifier("securedExecutor") Executor securedExecutor) {

            this.rawWorkers = rawWorkers;
            this.securedExecutor = securedExecutor;
        }

        @GetMapping("/api/current")
        String current() {
            return callerFromSecurityContext();
        }

        // Intentionally DEMONSTRATES THE BUG in a local environment.
        @GetMapping("/api/raw")
        CompletableFuture<String> raw() {
            return CompletableFuture.supplyAsync(
                ServletContextLabApplication
                    ::callerFromSecurityContext,
                rawWorkers
            );
        }

        @GetMapping("/api/delegated")
        CompletableFuture<String> delegated() {
            return CompletableFuture.supplyAsync(
                ServletContextLabApplication
                    ::callerFromSecurityContext,
                securedExecutor
            );
        }
    }
}
```

**This is a complete program inside a Spring Boot project with the dependencies listed above**; it cannot be compiled/run with bare `javac` without the Spring classpath. Both `/api/raw` and `/api/delegated` return `CompletableFuture`, letting Spring MVC handle the async response once the task completes.

Key points to verify:

1. `/api/current` runs on the authenticated request thread, so it reads Alice from `SecurityContextHolder`.
2. `/api/raw` submits the lambda directly to `ExecutorService` via `CompletableFuture.supplyAsync(...)`; the raw pool does not copy `ThreadLocal`, so the worker usually sees `missing-context` in the demo.
3. `/api/delegated` uses `DelegatingSecurityContextExecutor`. The wrapper captures context when submitting from the request thread, sets it for the worker during execution, and cleans up afterward.
4. `rawWorkers` has lifecycle management via `destroyMethod="shutdown"` so threads do not linger after shutdown.
5. One request's `Authentication` is never reused for another request; the wrapper does not share a global `SecurityContext`.
6. This example **is not an identity propagation solution for multi-hour jobs** or queued jobs executing on another machine. Those require a dedicated identity/delegation design.

### 4.3. Running and Observing

From the root of the Spring Initializr Gradle project:

```bash
./gradlew bootRun

# On Windows PowerShell:
# .\gradlew.bat bootRun
```

In another terminal:

```bash
curl -s -u alice:alice123 http://localhost:8080/api/current
curl -s -u alice:alice123 http://localhost:8080/api/raw
curl -s -u alice:alice123 http://localhost:8080/api/delegated

curl -s -u bob:bob123 http://localhost:8080/api/delegated
```

Text bodies **expected under demo conditions with no other code touching the raw pool**:

```text
actor=alice
missing-context
actor=alice
actor=bob
```

The four lines correspond to the four commands above, with no prompts, headers, or timestamps. Using `curl -i` to inspect statuses adds HTTP headers. Never use these sample passwords in real environments; HTTP Basic must go over HTTPS on real networks.

**Reminder:** this program is designed to demonstrate thread-local loss and wrapper usage; having the raw worker return `missing-context` does not prove every context-loss case shares the same cause. If other code attaches a security context to a thread and forgets to clean up, a worker could see **the wrong identity of another request**—never mistake that for correct behavior.

### 4.4. How to Verify in Async MVC Tests

When testing a controller returning `CompletableFuture` with `MockMvc`, you cannot simply assert the body immediately after `mvc.perform(...)` once the request switches to async mode. Capture `MvcResult`, assert `asyncStarted()`, then call `asyncDispatch(...)`:

```java
// Snippet inside a @SpringBootTest + @AutoConfigureMockMvc class
// with @Autowired MockMvc mvc; requires spring-security-test.
MvcResult pending = mvc.perform(
        get("/api/delegated")
            .with(httpBasic("alice", "alice123"))
    )
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(pending))
    .andExpect(status().isOk())
    .andExpect(content().string("actor=alice"));
```

Illustrative static imports needed:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
```

This is a **test snippet inside an already-configured test class**, not a standalone compilable file. Test dependencies are typically `spring-boot-starter-test` and `spring-security-test`. `MockMvc` must also be configured to run through the Spring Security filter chain.

Note: Spring Security includes **built-in integration with Servlet `AsyncContext.start(Runnable)` and Spring MVC async**. Do not conclude "every async Servlet loses context." The example specifically tests **tasks explicitly submitted by application code to a raw `ExecutorService`**, which must be verified independently of MVC's async response handling.

## 5. Common Mistakes with @Async and CompletableFuture

### 5.1. @Async Using a Thread Pool Without a Security-Aware Executor

This is a common bug pattern:

```java
// Illustrates a method in a @Service using @EnableAsync.
// If the executor does not propagate SecurityContext, principal may be missing.
@Async
public CompletableFuture<String> process() {
    Authentication authentication = SecurityContextHolder
        .getContext()
        .getAuthentication();

    String name = authentication == null
        ? "missing-context"
        : authentication.getName();

    return CompletableFuture.completedFuture(name);
}
```

To use Spring `@Async` safely when running **on behalf of the caller**, configure the task executor with `DelegatingSecurityContextAsyncTaskExecutor` or an equivalent wrapper, and verify Spring `@Async` picks that executor rather than a different raw executor bean. **Partial illustrative configuration**:

```java
@Bean
AsyncTaskExecutor securityAwareTaskExecutor(
        ThreadPoolTaskExecutor delegate) {

    return new DelegatingSecurityContextAsyncTaskExecutor(
        delegate
    );
}
```

The types here belong to Spring Task and Spring Security task integration; a `ThreadPoolTaskExecutor` must be created, initialized, and properly shut down, and you must specify `@Async("securityAwareTaskExecutor")` or set it as the default executor. Do not register a wrapper bean without confirming the method actually uses it.

Another mistake: calling an `@Async` method from another method **on the same object (`this.asyncMethod()`)** can bypass the Spring proxy, preventing async execution altogether. When debugging, separate "did the task switch threads?" from "was context propagated properly?"—they are two distinct issues.

### 5.2. Future Chains With a Second Thread Handoff

Suppose an initial stage ran in a security-aware executor:

```java
CompletableFuture<String> result = CompletableFuture
    .supplyAsync(this::loadData, securedExecutor)
    .thenApplyAsync(this::enrichData);
```

Here `thenApplyAsync(...)` takes no `Executor` argument, so by default it can run on the common pool and **does not automatically inherit SecurityContext** from the prior step. If `enrichData` needs the principal, pass the appropriate executor for that stage—or better yet, resolve and authorize identity before building the task chain and pass the minimal required business values explicitly.

Do not assume `thenApply(...)` is "always safe" just because it lacks the `Async` suffix: it can run on whichever thread completed the previous stage, not necessarily the original submitting thread.

### 5.3. Never Retain Request-Scoped Authentication Indefinitely

A task queued and executed hours later may run after the session expired or the user's permissions were revoked. Passing the entire `SecurityContext` object long-term is poor authorization policy for background jobs.

When designing long-lived jobs:

- Record the **verified actor ID**, requested action, resource ID, and authorization scope/reason.
- Decide whether the job runs under a **service identity** or a valid delegated authorization mechanism.
- Re-check authorization state at execution time for sensitive actions per business requirements.
- Never serialize access tokens or session cookies into a queue merely to restore `SecurityContext`.
- Clearly audit "who initiated" and "which principal actually executed," avoiding over-privileged defaults.

## 6. WebFlux: ReactiveSecurityContextHolder, Not Servlet ThreadLocal

Reactive Spring Security places security information into the **Reactor Context** attached to the subscriber, via components such as `ReactorContextWebFilter` and reactive authentication mechanisms.

Use the right API:

```java
Mono<String> principalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

This is an **illustrative Java method** inside a reactive application with Reactor/Spring Security. The publisher emits a value when a valid `SecurityContext` exists on the current subscriber; otherwise it can complete empty. Never convert a missing context into a self-asserted user via `X-User-Id`.

Do not use:

```java
// Wrong for identifying a WebFlux request
// if code relies on Servlet-style ThreadLocal.
String user = SecurityContextHolder
    .getContext()
    .getAuthentication()
    .getName();
```

In a reactive pipeline, code can execute on multiple schedulers. Reading `ThreadLocal`-backed `SecurityContextHolder` can return null, throw a NullPointerException, or return unrelated data (if another environment leaked a `ThreadLocal`). Reactive `SecurityContext` must be read from the subscriber context via `ReactiveSecurityContextHolder` or the framework-provided reactive principal parameter.

### 6.1. What Happens with publishOn()/subscribeOn()?

A very common misconception:

- `publishOn(scheduler)` changes where **downstream signals** are processed.
- `subscribeOn(scheduler)` affects where subscription and upstream work execute.
- **Neither of them erases Reactor Context** from a subscription properly created and propagated via Reactor APIs.

Reactor Context **does not follow threads**; it flows along subscription signals. If a WebFlux request has a security context and the pipeline composes `Mono`/`Flux` properly, code after a scheduler switch can still read `ReactiveSecurityContextHolder`.

Thus, claiming "the request lost the user after `publishOn`, so `publishOn` drops security context" usually skips a diagnostic step: is that code reading `ThreadLocal`, did it spawn a new subscription, leave the Reactor chain, or use a library that does not propagate context?

### 6.2. Separate Runnable Java 17+ WebFlux Example

Create a **separate Spring Boot project** so Spring MVC and Spring WebFlux are not mixed unintentionally. Dependencies:

- `spring-boot-starter-webflux`
- `spring-boot-starter-security`

File:

```text
src/main/java/demo/reactivecontext/ReactiveContextLabApplication.java
```

```java
package demo.reactivecontext;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextLabApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/actor").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build()
        );
    }

    @RestController
    static class ReactiveController {

        @GetMapping("/api/actor")
        Mono<String> actor() {
            // Intentionally switch scheduler while staying in the same Reactor chain.
            return Mono.delay(Duration.ofMillis(10))
                .publishOn(Schedulers.boundedElastic())
                .then(
                    ReactiveSecurityContextHolder.getContext()
                        .map(context ->
                            context.getAuthentication().getName()
                        )
                        .map(name -> "actor=" + name)
                        .defaultIfEmpty("missing-context")
                );
        }
    }
}
```

This is a **complete Spring Boot WebFlux program when placed in a project with the two dependencies above**. `Mono.delay(...)` merely introduces an explicit asynchronous boundary. `publishOn(Schedulers.boundedElastic())` switches schedulers, while `ReactiveSecurityContextHolder.getContext()` executes inside the chained pipeline under the same subscription.

Run:

```bash
./gradlew bootRun

# In another terminal
curl -i http://localhost:8080/api/actor
curl -i -u alice:alice123 http://localhost:8080/api/actor
```

Expectations:

| Request | HTTP status | Body |
| --- | --- | --- |
| No credentials | **401** | Basic challenge from Spring Security; never reaches controller |
| Valid Basic credentials for Alice | **200** | `actor=alice` |

Getting `"actor=alice"` across an asynchronous boundary illustrates that Reactor context persists when the pipeline is composed properly. Never infer security state from seeing an old or new thread name in logs.

Note that this demo does not show how to call a blocking database: `boundedElastic` is typically used for bounded blocking operations, yet **switching to `boundedElastic` does not make a JDBC query non-blocking**. If an app has blocking work, design scheduling, timeouts, and pool sizing appropriately.

## 7. A Small Test Proving Reactor Context Follows the Subscription

If you have a project with `spring-security-test` and `reactor-test`, you can write a unit test for a publisher outside HTTP. Test file in the Spring Boot WebFlux project created above:

```text
src/test/java/demo/reactivecontext/ReactorSecurityContextTest.java
```

```java
package demo.reactivecontext;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication
    .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context
    .ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactorSecurityContextTest {

    @Test
    void identitySurvivesPublishOn() {
        Authentication alice =
            new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

        Mono<String> pipeline = Mono.just("work")
            .publishOn(Schedulers.boundedElastic())
            .flatMap(ignored ->
                ReactiveSecurityContextHolder.getContext()
                    .map(context ->
                        context.getAuthentication().getName()
                    )
            )
            .map(name -> "actor=" + name)
            .contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(alice)
            );

        StepVerifier.create(pipeline)
            .expectNext("actor=alice")
            .verifyComplete();
    }
}
```

**Technical note on imports:** Java allows line breaks before a dot in import statements, though for clean copying you can put wrapped imports on single lines:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Use **those two full lines instead of the wrapped imports**, without keeping both forms. With Gradle, add:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **dependency addition for a `build.gradle` that already applies the Spring Boot plugin**, not a complete Gradle file. Run:

```bash
./gradlew test --tests "demo.reactivecontext.ReactorSecurityContextTest"
```

The test constructs `Authentication` **only to test internal context propagation in a unit test**; it does not prove real username/password or JWT verification. Fake values must never be injected into production requests to impersonate Alice.

Key detail in the test: `flatMap(...)` calls `ReactiveSecurityContextHolder.getContext()` **after** `publishOn`, so the test does not merely read context before switching schedulers and capture the name in a `String` variable. `contextWrite(...)` places the authentication into **the test subscription's Reactor Context**, not into a fixed thread's `ThreadLocal`.

## 8. Reactive Antipatterns That Break Context Scope

### 8.1. Calling subscribe() Manually in a Controller or Service

Broken orchestration design:

```java
// Illustrates the bug; do not paste directly into the sample app.
public Mono<String> process() {
    somePublisher()
        .flatMap(this::saveEvent)
        .subscribe(); // Work splits off into a separate subscription.

    return Mono.just("accepted");
}
```

Calling `subscribe()` creates an independent subscription. The caller loses control over completion, error handling, backpressure, and context propagation as a single request branch. If `somePublisher()` needs security context, the new subscription **does not share the request's context by default**.

Proper composition within the same pipeline:

```java
public Mono<String> process() {
    return somePublisher()
        .flatMap(this::saveEvent)
        .thenReturn("accepted");
}
```

These two snippets **illustrate method structure only** and assume `somePublisher()` and `saveEvent(...)` are defined in an appropriate service. They are not standalone compilable programs. If work genuinely must be detached from the HTTP request (fire-and-forget, queue, scheduled job), design a dedicated event/job and decide the job's identity explicitly rather than hoping subscriber context tags along implicitly.

### 8.2. Bridging from Reactive to CompletableFuture or Callbacks

Example:

```java
// Illustrates a boundary to evaluate:
CompletableFuture<Data> future = thirdPartyClient.loadAsync();
return Mono.fromFuture(future);
```

`Mono.fromFuture(...)` brings the Future's **result** into a reactive pipeline, yet code already executing inside the Future **does not automatically receive the subscriber's Reactor Context**. If `thirdPartyClient.loadAsync()` needs the actor, pass verified actor metadata into the call via an explicit contract or use an appropriate bridge/context propagation mechanism.

Do not assume `Mono.fromFuture` itself always "loses SecurityContext." Failure occurs when identity-dependent code executes **outside the contextual subscription**, or when code relies on an unbridged `ThreadLocal`.

### 8.3. Calling block() in the Wrong Place

`block()`/`blockOptional()` creates a **subscription** to retrieve a value synchronously. On WebFlux non-blocking threads, `block()` can fail or starve threads while spawning an independent execution path that makes context and scheduling hard to reason about. Never call `block()` inside a handler or reactive chain to read the username.

Wrong:

```java
// Avoid inside a reactive handler:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
```

Prefer staying reactive:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
```

These snippets show part of a service/controller; returning `Mono<String>` assumes a matching return type. In tests or blocking integration points outside the reactive stack, controlled `block()` calls can make sense, but **never use it as a security-context management strategy inside reactive requests**.

### 8.4. Placing contextWrite in the Wrong Spot / Misreading Propagation Direction

`contextWrite(...)` writes context for the **upstream** portion along the subscription flow. You cannot deduce where it takes effect from top-to-bottom Java line order like a mutable variable. For example, the unit test in section 7 places `contextWrite` at the end of the pipeline before `StepVerifier` so upstream operators can read it.

`Mono.deferContextual(...)` inspects Reactor Context directly; `ReactiveSecurityContextHolder.getContext()` is Spring Security's API for retrieving the corresponding `SecurityContext`. Writing `contextWrite(context -> Context.empty())` or deleting keys expected by the security library can inadvertently wipe data the pipeline needs.

Never inject a `SecurityContext` from an unverified request header using `contextWrite(...)` to "fix 403": that is impersonation. In tests, `ReactiveSecurityContextHolder.withAuthentication(testAuthentication)` can **simulate** context; production must rely on a genuinely verified authentication flow.

### 8.5. Confusing Reactor Context with MDC/ThreadLocal Observability

A log line missing `traceId` or MDC **does not mean** Spring Security `Authentication` was lost. Conversely, having the right MDC does not prove security context is present. Bridges like `io.micrometer:context-propagation` and Reactor's automatic context propagation mode help supported `ThreadLocal` values participate in propagation under supported conditions, yet **they do not turn arbitrary ThreadLocals into valid security contexts**.

When diagnosing, measure **both separately**: is authentication present via the stack's official API, and are tracing/diagnostic fields propagated via the right observability mechanism? Enable automatic context propagation only once you understand library versions, accessors, lifecycles, and performance impact; never treat it as a universal cure for authorization errors.

## 9. Verifying at the Reactive HTTP Layer with WebTestClient

In a WebFlux project, you can bind `WebTestClient` to `ApplicationContext` so requests flow through `SecurityWebFilterChain` without opening an HTTP port:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();

client.mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/actor")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("actor=alice");
```

This snippet assumes the test class injects `ApplicationContext applicationContext`, uses Spring Test's `WebTestClient`, statically imports `springSecurity` and `mockUser` from `SecurityMockServerConfigurers`, and includes `spring-security-test`. **This is an integration test snippet**, not a standalone program.

Separate two test layers:

- `mockUser()` injects a simulated `Authentication` in tests to check **context reaching the controller** and role-based authorization. It **does not** verify passwords, JWT signatures, issuers, audiences, or OAuth2 introspection.
- Sending HTTP Basic credentials via `WebTestClient` or `curl` against a real `MapReactiveUserDetailsService` verifies **inbound authentication** and context delivery to the handler.

For the sample WebFlux app, add a test crossing another scheduler to prove `ReactiveSecurityContextHolder` still has data. For anonymous requests, `/api/actor` must be blocked (typically 401 by HTTP Basic) **before** the controller reads context. Never turn `missing-context` into an HTTP 200 success to mask bugs in a real product; that string is purely for bug visibility in the demo.

### Concurrency Tests to Catch Identity Leaks

In the Servlet demo, run consecutive or concurrent requests to `/api/delegated` as Alice and Bob. Verify every response body matches the request's own actor. If Bob's request ever returns `actor=alice`, the bug is no longer lost context—it is a **cross-request context leak**. Use synthetic identities in tests, never real personal data.

Minimum test matrix:

| Stack | Scenario | Correct Result |
| --- | --- | --- |
| Servlet | Alice request reads context synchronously | Alice |
| Servlet | Alice submits task to raw non-propagating executor | Usually empty context in demo |
| Servlet | Alice submits task to delegated executor | Alice |
| Servlet | Bob submits task to the same delegated executor | Bob, never receiving Alice's identity |
| Servlet | Anonymous calls protected endpoint | Blocked at security filter |
| WebFlux | Alice crosses `publishOn` then reads `ReactiveSecurityContextHolder` | Alice |
| WebFlux | Mock user in tests | Alice reaches handler and method security per rules |
| WebFlux | Request without credentials | 401/challenge when using HTTP Basic |
| WebFlux | Task detached from subscription without identity handoff | Must not implicitly receive request context |
| Both | Code builds user from `X-User-Id` | Must not be treated as an authenticated caller |

## 10. Ordered Debugging to Avoid Misattributing 401/403

### Step 1 — Identify Which Stack Is Actually Running

Check whether the application uses `spring-boot-starter-web` (Servlet) or `spring-boot-starter-webflux` (reactive). When both are on the classpath, Spring Boot 3.x normally defaults to Servlet mode unless reactive mode is explicitly configured. Do not look at one method returning `Mono` and conclude the whole app is WebFlux.

- Servlet: inspect `HttpSecurity`, `SecurityFilterChain`, `SecurityContextHolder`.
- WebFlux: inspect `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`.

### Step 2 — Verify HTTP Authentication and Authorization First

Send a request with **valid test-environment credentials**. If a filter immediately returns 401/403 before async execution begins, the root cause is not lost context in a worker. For POST, check CSRF as well. Inspect initial status, route matchers, roles, and entry point.

### Step 3 — Measure Context at Both Ends of the Boundary

In Servlet, record whether `SecurityContextHolder.getContext().getAuthentication()` exists right before task submission and **inside the task**, along with request ID and executor type. In WebFlux, measure with `ReactiveSecurityContextHolder.getContext()` **at the signal consumer**, rather than reading ThreadLocal `SecurityContextHolder` and drawing conclusions.

Never log full `Authentication` objects, credentials, JWTs, session cookies, or personal data. If you need to compare actors across phases, use a properly issued and protected internal/pseudonymous identifier.

### Step 4 — Pinpoint the Broken Boundary

Look for `new Thread`, `ExecutorService`, `CompletableFuture.supplyAsync/thenApplyAsync`, `@Async`, SDK callbacks, message queues, schedulers, manual `subscribe()`, or `block()`. Determine whether the task belongs to the request or has become an independent job. Inspect which executor is actually invoked; configuring a security-aware bean **has no effect** if the method still falls back to the common pool.

### Step 5 — Fix According to the Right Model

- **Servlet same request:** use `DelegatingSecurityContextExecutor`/`Runnable`/`Callable` or an appropriate task adapter to transfer context intentionally. Verify cleanup and avoid wrong fixed contexts.
- **WebFlux same subscription:** compose `Mono`/`Flux`, read via `ReactiveSecurityContextHolder`, avoid ad-hoc child subscriptions, and never use Servlet ThreadLocal to look up principals.
- **True background tasks:** pass actor/job identity per business contract, enforce authorization at execution time, and audit the initiator.
- **Reactive ↔ blocking bridges:** identify the boundary, pass **minimal verified data** or use a well-tested context propagation mechanism; never copy tokens arbitrarily.

### Step 6 — Stress-Test Concurrent Requests

A single test cannot catch every flaw. Interleave two different test accounts across the same thread pool and verify identities never mix. Test timeouts, task exceptions, cancellations, retries, and shutdown. After an error, the next task **must not inherit** the previous task's security context.

## 11. Dangerous "Fixes" to Avoid

1. **`MODE_GLOBAL`**: turns the principal into process-wide state that can mix users.
2. **Applying `MODE_INHERITABLETHREADLOCAL` indiscriminately**: can retain stale context in thread pools; does not guarantee the current request's identity.
3. **Failing to clear ThreadLocal after a task**: leaks identity across requests; standard library wrappers handle cleanup/restoration.
4. **Creating a principal from an `X-User-Id` header or `userId` query param**: turns a lost-context bug into an impersonation vulnerability.
5. **Pinning an admin `SecurityContext` onto a shared executor**: every task can end up running with admin privileges.
6. **Disabling `@PreAuthorize` / `authorizeHttpRequests`** just because of 403: strips a protection layer instead of fixing identity propagation.
7. **Calling `block()` inside a WebFlux request** to read the username: can block the event loop and create an out-of-scope subscription.
8. **Calling `subscribe()` inside a service without lifecycle management**: detaches context, errors, and completion from the request.
9. **Assuming `publishOn` itself drops Reactor Context**: leads to the wrong fix; inspect context APIs and the real boundary.
10. **Logging the entire security context**: risks exposing credentials and personal data, especially with broad TRACE enabled.
11. **Running every background task under the caller's HTTP identity after the request ended**: does not guarantee authorization remains valid.
12. **Treating context propagation as authorization**: propagating Alice accurately only answers "who is executing"; you must still verify whether Alice is authorized for the specific **resource/action**.

## 12. Checklist When Investigating a Real Incident

- [ ] Identify Servlet vs WebFlux and the exact Spring Security/Boot version.
- [ ] Confirm the initial request authenticated successfully and 401/403/CSRF rules are understood.
- [ ] Measure actor **before and after the execution boundary** using the stack's proper API.
- [ ] Check which executor/scheduler is actually invoked; never guess by bean name.
- [ ] For Servlet, confirm capture/restore/cleanup of `SecurityContext` on custom tasks.
- [ ] For WebFlux, stay in the same Reactor subscription and read context via `ReactiveSecurityContextHolder`.
- [ ] Inspect every `Future`, `@Async`, callback, nested `subscribe`, queue, and scheduled job branch.
- [ ] Verify method security/authorization **was not disabled** to mask errors.
- [ ] Check timeout/cancel/error paths for proper cleanup and zero identity leakage.
- [ ] Run interleaved Alice/Bob tests on the same pool to detect cross-user context.
- [ ] Never log tokens, passwords, serialized principals, or raw personal data.
- [ ] Distinguish "having the right Authentication" from "having permission on the resource."

**Conclusion:** in Servlet, a `ThreadLocal` does not automatically follow tasks onto an executor—use Spring Security's delegation utilities when needed. In WebFlux, context travels with the **Reactor subscriber Context**; switching schedulers does not erase it, whereas spawning detached subscriptions, leaving the pipeline, or reading the wrong API hides the true identity. Every fix must protect **both directions**: never lose the caller's valid identity, and never leak another user's identity.

### Official Documentation

- [Spring Security 6.5 — Concurrency Support (Servlet)](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security — Servlet Concurrency Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Servlet AsyncContext integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html)
- [Spring Security 6.5 — Reactive Method Security and Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Project Reactor — Adding Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Security — Reactive Web Test Support](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
