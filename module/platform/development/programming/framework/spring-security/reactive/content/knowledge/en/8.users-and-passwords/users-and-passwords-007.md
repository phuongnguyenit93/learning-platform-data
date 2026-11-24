# Scheduling CPU-Intensive Password Verification and Assessing Event-Loop Impact

## Objectives and Scope

In **Spring Security - reactive**, HTTP requests are normally handled by Spring WebFlux on event-loop threads. However, matching a password with BCrypt, PBKDF2, scrypt, or Argon2 is an operation that is **intentionally CPU-intensive (and potentially memory-intensive)**. If this computation runs on the event loop, other requests can be forced to wait even though the application uses `Mono` and `Flux`.

After this lesson in the **Users and Passwords** group, you can:

1. Explain why `PasswordEncoder.matches(...)` is a resource-intensive synchronous operation and distinguish it from blocking I/O.
2. Predict the consequences when hashing/verification runs on Netty event-loop threads.
3. Use `Mono.fromCallable(...)`, `subscribeOn(...)`, and an appropriate scheduler when writing custom pipelines.
4. Understand how Spring Security's `UserDetailsRepositoryReactiveAuthenticationManager` **already schedules password verification separately**, and know when to use `setScheduler(...)`.
5. Configure a dedicated scheduler for CPU hashing, size it to available CPU, and control queued load.
6. Build a Java 17+ example verifying the BCrypt execution thread, authentication outcomes, and latency of an unauthenticated endpoint.
7. Measure **throughput, p95/p99, event-loop delay, CPU saturation, and queueing** under load and propose mitigations without weakening password security.

**Core idea:** Reactive frees threads while *waiting on I/O*; it does not make BCrypt compute faster. Switching schedulers only moves where CPU is consumed. If total compute demand exceeds machine capacity, queues and latency still grow.

## 1. Why Must Password Verification Be Intentionally Slow?

Spring Security's `PasswordEncoder` has a synchronous API:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

`encode` creates a one-way hash for storage; `matches` checks a supplied password against a stored hash. Raw passwords must never appear in databases or logs.

Modern password hashing algorithms use a **work factor** and salt to raise brute-force costs if hashes leak:

| Mechanism | Primary Resource | What to Measure |
| --- | --- | --- |
| BCrypt | CPU; exponential cost | Time per `matches` call as strength/cost increases |
| PBKDF2 | CPU by iteration count | Timing and cryptographic policy compatibility |
| scrypt | CPU and memory | Timing and RAM under multiple concurrent verifications |
| Argon2 | Memory and CPU | Time cost, memory cost, parallelism, container RAM/GC |

In its password storage guide, Spring Security recommends tuning the work factor so a check takes around **one second on deployment hardware** as a reference point, then measuring and balancing latency/resources for the actual system. **Do not treat 1 second as a fixed SLA** or optimal level for every product. Hardware, CPU quotas, algorithm choice, memory, and login demand all shape the decision. The default `BCryptPasswordEncoder()` uses strength 10, which does not guarantee your system will take any exact duration.

Slow hashing is a security feature. "Optimizations" such as storing plaintext passwords, using `NoOpPasswordEncoder`, using plain SHA-256, or lowering the work factor without verification **are not** valid fixes for event-loop stalls.

A user should normally use a password for the **login step**, then continue via an appropriate session or short-lived credential; do not run BCrypt on **every request** merely to keep an application stateless. If an API uses HTTP Basic on every request, size verification volume according to total request traffic, not just login session count.

## 2. What Does WebFlux's Event Loop Do?

With Spring Boot WebFlux running on Reactor Netty, `reactor-http-nio-*` threads typically accept HTTP traffic, transfer data, execute non-blocking pipelines, and write responses. They must return promptly to serve many connections.

```text
                         Spring WebFlux / Reactor Netty
Request A -----\
Request B ------> event-loop thread -- parse, route, schedule, write response
Request C -----/                |
                                +--> if BCrypt runs directly here:
                                     CPU spins for hundreds of ms or more
                                     thread cannot serve B/C meanwhile
```

To stay responsive, long-running work must leave the event loop or be designed asynchronously. **Do not conflate CPU-bound work with blocking I/O:**

- **CPU-bound:** `BCryptPasswordEncoder.matches` occupies the CPU to compute; the synchronous method only returns once computation finishes. It does not wait on the network, yet it **holds the thread** for its entire runtime.
- **Blocking I/O:** synchronous JDBC, synchronous file reads, or blocking HTTP clients typically make threads **wait** on external resources.
- **Nonblocking I/O:** reactive drivers return a publisher while waiting on DB/network; the event loop can serve other work.
- **Memory-hard hashes:** scrypt/Argon2 also consume RAM, creating memory pressure when many jobs run concurrently.

Reactor `Mono` only defines how signals are emitted; writing `Mono.just(encoder.matches(raw, hash))` **does not** make the computation asynchronous: Java evaluates the argument before constructing `Mono.just`.

### Two Illustrative Timelines

```text
Wrong: synchronous verify on the event loop

event-loop: [read A][BCrypt A .....................][respond A][read B]...
password CPU:    same event-loop thread is occupied

Right direction: offload verify to a bounded CPU worker

event-loop: [read A][schedule BCrypt A][read B][route B][respond B]...
pwd-worker:             [BCrypt A .............]
event-loop:                                            [respond A]

High load: more BCrypts than workers/CPU -> jobs still wait in queue.
```

Dots only illustrate duration and do not represent actual measured milliseconds.

## 3. Choosing a Scheduler: parallel, boundedElastic, and immediate

Reactor provides several `Scheduler`s:

| Scheduler | Typical Purpose | Should It Be Used for Password Verification? |
| --- | --- | --- |
| `Schedulers.parallel()` | Short or bounded CPU tasks; default pool tied to CPU count | Suitable workload type, but using the **shared pool** can contend with timers/other operators |
| `Schedulers.newParallel("password-work", n)` | Dedicated CPU pool with configurable worker count and thread names | Useful choice to **isolate hashing** from the shared `parallel` scheduler |
| `Schedulers.boundedElastic()` | Wrapping **blocking I/O** sources; bounded threads and queue | Not an optimal default for pure CPU consumption; too many active workers can saturate CPU |
| `Schedulers.single()` | One sequential worker | Easily becomes a bottleneck under multiple hashes |
| `Schedulers.immediate()` | Runs immediately on the current thread | Risky if the current thread is a Netty event loop |
| Custom `newBoundedElastic(...)` | Blocking/synchronous pool with configured thread/queue caps | Fits tasks that must **wait on I/O**; does not make password computation faster |

An easily missed detail: **Reactor's `parallel` is a shared scheduler used across many operators**. If all hashing runs on this pool and keeps CPUs busy continuously, other tasks using `Schedulers.parallel()` can be delayed. A named `newParallel` isolates **queues and threads**, but **does not isolate physical CPU**: pools still compete for the same CPU quota. Therefore, measure CPU and active job counts rather than concluding "a dedicated pool eliminates bottlenecks".

**Virtual threads** also do not shorten pure CPU computations. They help blocking-wait patterns under certain conditions, not multiply a container's CPU capacity.

### About Spring Security's Default

`UserDetailsRepositoryReactiveAuthenticationManager` extends `AbstractUserDetailsReactiveAuthenticationManager`; the Spring Security API documents `setScheduler(Scheduler)` and defaults to a `Schedulers.newParallel(String)`-style scheduler for password verification because password hashing is CPU-intensive. Therefore:

- If you use the **standard manager** for username/password authentication, **check it first**: verification already has appropriate scheduling, so do not wrap the entire `authenticate` call in another `subscribeOn` just because it returns `Mono`.
- If you want to **isolate**, set thread count, thread names, and pool lifecycle per application, call `setScheduler(...)` on the **exact manager instance actually used by HTTP Basic/form login**.
- If you invoke `PasswordEncoder.matches` yourself outside the manager, you must decide where it executes, e.g., `Mono.fromCallable(...).subscribeOn(dedicatedScheduler)`.
- Never use `Schedulers.immediate()` for BCrypt just to bypass scheduling; that can push the computation back onto the event loop.

API docs can differ in class/Javadoc details across versions; always verify the Spring Security version selected by your Spring Boot BOM.

## 4. Wrapping a PasswordEncoder Call Properly

Suppose `encoder` is `BCryptPasswordEncoder` and `storedHash` has been loaded from the user store.

### 4.1. Wrong: Computing Before Creating the Mono

```java
// Wrong if running on the event loop:
Mono<Boolean> verified =
        Mono.just(encoder.matches(rawPassword, storedHash));
```

`matches` is called **right when building the expression**, on the calling thread; no scheduling happens before CPU is consumed. Nor does writing this help:

```java
Mono<Boolean> verified =
        Mono.just(encoder.matches(rawPassword, storedHash))
                .subscribeOn(passwordScheduler);
```

`subscribeOn` only affects subscription **after** `Mono.just` has already been created. The computation has already finished on the original thread.

### 4.2. Right: Lazy Evaluation and Scheduling at the Source

```java
// Code fragment used in a custom authentication service:
Mono<Boolean> verified =
        Mono.fromCallable(
                () -> encoder.matches(rawPassword, storedHash))
            .subscribeOn(passwordScheduler);
```

`Mono.fromCallable` defers invoking `matches` until a subscriber subscribes. `subscribeOn` directs the source to run on the specified scheduler. On each subscription, the hash is checked and emits a Boolean or `onError` if an exception occurs.

**Still return the result through the pipeline—never `block()` or call `subscribe()` standalone**:

```java
// Illustrative code fragment, not a complete controller.
// Never return true before verification completes.
return Mono.fromCallable(
            () -> encoder.matches(rawPassword, storedHash))
        .subscribeOn(passwordScheduler)
        .flatMap(matches ->
            matches ? Mono.just(authentication)
                    : Mono.error(new BadCredentialsException(
                            "Bad credentials")));
```

Here `authentication` is an authentication result built by the application per contract, while `BadCredentialsException` comes from Spring Security. Never allow access simply because a repository or scheduler errored. Do not leak overly specific "user does not exist" or "wrong password" details in responses.

### 4.3. publishOn vs. subscribeOn

`publishOn(scheduler)` switches **downstream operators** onto that scheduler. If you already hashed **upstream**, placing `publishOn` after the call cannot "move CPU work back in time".

```java
// Effective if the upstream pipeline has not called matches yet:
Mono<Boolean> example =
        Mono.just(storedHash)
            .publishOn(passwordScheduler)
            .map(hash -> encoder.matches(rawPassword, hash));
```

This form can work in simple cases, but when **wrapping an independent synchronous method**, the `fromCallable(...).subscribeOn(passwordScheduler)` pattern is usually clearer and less error-prone. Avoid unnecessary `publishOn` calls because each scheduler hop adds overhead and shifts where downstream operators run.

### 4.4. Do Not Create a Scheduler per Request

```java
// Wrong: each request creates a new thread pool, hard to manage resources.
Mono.fromCallable(() -> encoder.matches(raw, hash))
    .subscribeOn(Schedulers.newParallel("one-request", 4));
```

Create **one shared application-managed scheduler**, and dispose of it on shutdown. Thread names, worker counts, and load bounds must align with your CPU budget.

## 5. Runnable Java 17+ Spring Security Reactive Example

The application uses Spring Boot **3.3.13**, WebFlux, HTTP Basic, and BCrypt. So learners can see actual scheduling, the example creates `UserDetailsRepositoryReactiveAuthenticationManager`, attaches a `newParallel("pwd-verify", n)` scheduler, and wraps `PasswordEncoder` to record **thread name + verification duration**; it never prints raw passwords, hashes, or Authorization headers.

### 5.1. Files and Dependencies

Structure:

```text
password-scheduling-demo/
  settings.gradle
  build.gradle
  src/main/java/example/PasswordSchedulingApplication.java
  src/test/java/example/PasswordSchedulingApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'password-scheduling-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add Servlet's `spring-boot-starter-web` to the WebFlux sample project. The plugin and dependency management select compatible Spring Security and Reactor versions. In production apps, update to supported releases per organization policy; the pinned version above keeps the example reproducible.

### 5.2. Complete Application

Create `src/main/java/example/PasswordSchedulingApplication.java`:

```java
package example;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class PasswordSchedulingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordSchedulingApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/private")
    public String privateData() {
        return "PRIVATE_OK";
    }

    @Bean(destroyMethod = "dispose")
    Scheduler passwordScheduler() {
        int cpus = Runtime.getRuntime().availableProcessors();
        int threads = Math.max(1, Math.min(cpus, 4));
        return Schedulers.newParallel("pwd-verify", threads);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

        return new PasswordEncoder() {
            @Override
            public String encode(CharSequence rawPassword) {
                return bcrypt.encode(rawPassword);
            }

            @Override
            public boolean matches(CharSequence raw, String encoded) {
                long started = System.nanoTime();
                try {
                    return bcrypt.matches(raw, encoded);
                }
                finally {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);
                    System.out.println("password-verify thread="
                            + Thread.currentThread().getName()
                            + " elapsedMs=" + elapsedMs);
                }
            }

            @Override
            public boolean upgradeEncoding(String encodedPassword) {
                return bcrypt.upgradeEncoding(encodedPassword);
            }
        };
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("alice")
                .password(encoder.encode("learn"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder,
            Scheduler passwordScheduler) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setScheduler(passwordScheduler);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
                .authenticationManager(manager)
                .authorizeExchange(ex -> ex
                        .pathMatchers("/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Key points to read accurately in the example:**

1. `PasswordEncoder.matches` is still **synchronous** BCrypt. It is wrapped with encoder instrumentation to see which thread executes it and how long it takes. `encode("learn")` runs **once when creating the demo user**, not as a benchmark measurement.
2. `UserDetailsRepositoryReactiveAuthenticationManager` performs username/password authentication. It already has a default parallel-style scheduler, but here `setScheduler(passwordScheduler)` **explicitly swaps in** a dedicated pool for observation/bounding.
3. `Schedulers.newParallel("pwd-verify", threads)` creates a dedicated pool capped at 4 workers in the demo and no more than visible logical CPUs. The number 4 is purely illustrative, **not a universal recommendation**; size according to CPU quotas and instance counts.
4. `@Bean(destroyMethod = "dispose")` ensures the application-owned scheduler is disposed when the ApplicationContext closes.
5. `.authenticationManager(manager)` wires that exact manager into `ServerHttpSecurity`, rather than defining a bean while the Basic pipeline uses another manager.
6. `/ping` is a public endpoint requiring **no BCrypt**. `/private` requires HTTP Basic, so requests carrying username/password can trigger verification.
7. Never print passwords, hashes, or Basic headers. `System.out.println` is solely for observing threads on a learning machine; production should use lightweight metrics/timers and avoid blocking logging on hot paths.
8. `BCryptPasswordEncoder(10)` is only sample config. Evaluate cost against your real system and password policy before deploying.

### 5.3. Running and Verifying

Requires JDK 17+ and Gradle 7.5+/8.x compatible with Spring Boot 3.3.13. From the project directory:

```bash
gradle bootRun
```

If a Gradle Wrapper exists, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Open another terminal:

```bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/private
curl -i -u alice:learn http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
```

Expected functional outcomes:

| Request | HTTP Result | Body / Meaning |
| --- | --- | --- |
| `GET /ping` without credentials | `200` | `PONG` |
| `GET /private` without credentials | `401` | Basic challenge; protected handler not invoked |
| `GET /private` Basic `alice:learn` | `200` | `PRIVATE_OK` |
| `GET /private` Basic `alice:wrong` | `401` | Wrong password, access denied |

Each request with a valid user and password should emit a log line like:

```text
password-verify thread=pwd-verify-1 elapsedMs=...
```

The `...` placeholder represents an actual number varying by hardware and load. The trailing thread name may be `pwd-verify-2`, etc. **Do not write tests asserting exact millisecond counts.** What matters is the `pwd-verify-` prefix: the computation ran on the dedicated scheduler, **not on `reactor-http-nio-*`**.

While `GET /ping` runs, no `matches` calls are made by that endpoint. That lets `/ping` serve as a responsiveness probe while `/private` requests run concurrently.

## 6. Unit Testing Scheduler Behavior and HTTP Behavior

Create `src/test/java/example/PasswordSchedulingApplicationTests.java`:

```java
package example;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class PasswordSchedulingApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequirePassword() {
        client.get().uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void privateEndpointRequiresAuthentication() {
        client.get().uri("/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctPasswordSucceeds() {
        client.get().uri("/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PRIVATE_OK");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/private")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void callableRunsOnDedicatedScheduler() {
        Scheduler scheduler = Schedulers.newParallel("pwd-test", 1);
        try {
            BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(10);
            String hash = encoder.encode("learn");
            AtomicReference<String> thread = new AtomicReference<>();

            Mono<Boolean> verify = Mono.fromCallable(() -> {
                thread.set(Thread.currentThread().getName());
                return encoder.matches("learn", hash);
            }).subscribeOn(scheduler);

            StepVerifier.create(verify)
                    .expectNext(true)
                    .verifyComplete();

            assertTrue(thread.get().startsWith("pwd-test-"));
        }
        finally {
            scheduler.dispose();
        }
    }
}
```

Run:

```bash
gradle test
```

The HTTP tests verify the security chain; the `StepVerifier` test verifies `fromCallable.subscribeOn` uses a worker from the named pool. **Never treat a thread-name test as proof that performance meets SLAs.** Performance must be measured under steady load on real infrastructure, whereas scheduler tests verify the scheduling mechanism works.

If you replace the custom scheduler with the manager's default, you still need to check which scheduler it uses in your **specific Spring Security version**. Do not wrap the manager in another scheduler and assume BCrypt was offloaded properly without observing the actual execution thread.

## 7. Capacity and Queue Math: Why Adding Threads Alone Is Not Enough

Suppose each BCrypt check takes an average of `S` CPU/worker seconds and a machine can effectively execute `C` checks concurrently. Ideal capacity is roughly:

```text
ideal_throughput ≈ C / S   (verifications/sec)
approx_utilization ≈ λ × S / C
```

Where `λ` is the rate of **actual verification requests arriving per second on that instance**. This is a rough estimate for CPU-heavy workloads; it is not an exact forecast formula when I/O, GC, contention, cgroup throttling, startup costs, or work-factor changes are involved.

Hypothetical example (**not measured application numbers**):

- CPU capacity supports roughly 4 active hash workers.
- Each verification takes 250 ms = 0.25 seconds on average.
- Ideal maximum capacity: `4 / 0.25 = 16 verifications/sec`.
- If average load hits `20 verifications/sec`, incoming work **exceeds** processing capacity; queues tend to grow even with the event loop free.
- Increasing workers to 16 on a 4-CPU machine **does not create** 16 cores of CPU capacity; context-switching overhead can even make things worse.

| Condition | What Metrics Show | Diagnostic Action |
| --- | --- | --- |
| Spare CPU, minimal queue | Hash time near baseline | No need to add threads |
| Password workers saturated, queue growing | Login p95/p99 rises | Bound concurrency, rate-limit, or add capacity |
| 100% CPU / cgroup throttling | Even `/ping` slows down | Check CPU quotas, pod count, workers, load distribution |
| Rising RAM/GC with Argon2 | Pauses or OOM risk | Lower concurrent jobs, measure memory cost |
| Event loop sluggish while password workers idle | Likely other blocking/CPU work on event loop | Thread/stack profiling, BlockHound in appropriate tests |
| Low throughput despite low CPU | Likely DB/user lookup, locks, queues, or network | Separate lookup time, scheduler wait, and hash time |

Separate **queue wait time** from **`matches` execution time**. A timer placed inside `PasswordEncoder.matches` measures hash runtime on the worker but **excludes how long the request waited for a worker**. To explain login p99, measure total request duration and admission/scheduler wait times where applicable.

### What Happens When Queues Grow?

A `newParallel` pool has a finite worker count, **which does not mean queued tasks are automatically bounded to an API-safe level**. If clients keep sending requests and each enqueues another pending task, memory usage and latency can climb. Apply:

- An instance-wide cap on concurrent login attempts aligned with CPU/memory budgets.
- IP/account rate limiting and credential-stuffing defenses to prevent attackers from using hashing as CPU DoS.
- Bounded queues and explicit overload policies returning 429/503 appropriately after reviewing security semantics.
- Request timeouts—but **do not assume `timeout` immediately aborts a synchronous hash already in progress**; cancellation may not interrupt CPU work instantaneously.
- Autoscaling driven by CPU, latency, and queue depth together, accounting for warmup and pod limits.

Never use `onErrorReturn(true)`, `onErrorComplete()` followed by granting access, or return successful authentication if the scheduler rejects execution under overload. Infrastructure errors must remain "unable to authenticate" until policy handles them safely.

## 8. Controlling Concurrency in Reactive Code

For a **bounded internal batch** of offline checks (not an external client login endpoint), you can cap fan-out via `flatMap`'s `concurrency` parameter:

```java
// Illustrative code fragment: requests is an internal Flux<VerifyRequest>,
// passwordScheduler is a shared scheduler, verifyRequest returns Mono<Boolean>.
int concurrency = 4;

Flux<Boolean> checked = requests.flatMap(
        request -> verifyRequest(request, passwordScheduler),
        concurrency);
```

`flatMap(..., concurrency)` limits concurrently subscribed inner publishers **within this batch pipeline**. However, each HTTP login request typically has **its own pipeline**; putting `flatMap(..., 4)` inside a single request **does not enforce a service-wide cap of 4 logins**. For an instance-wide limit, use a **shared** bulkhead/semaphore/admission controller with non-blocking queuing or rejection and safe permit release across success/error/cancellation.

Never call synchronous `Semaphore.acquire()` on the event loop to "throttle" because that call itself can block the event loop. When queuing is needed, use an async scheduler/admission mechanism or fail fast with overload status when permits are exhausted. Every termination path must release permits via `doFinally` or an equivalent resource guard.

### Checking Operation Order

If you must both query the user database and hash:

```text
HTTP request
    |
    +-- ReactiveUserDetailsService lookup (nonblocking I/O)
    |
    +-- once stored hash is available:
    |      -> schedule CPU-only matches on dedicated scheduler
    |
    +-- receive Boolean -> authentication result
    |
    +-- authorization -> handler / security response
```

Do not put `subscribeOn(passwordScheduler)` at the **start of the entire stream** if you can offload only the CPU computation itself; doing so runs unrelated steps on pricey workers and increases contention. With the standard manager, the framework normally isolates verification already so no extra wrapper is needed.

## 9. Designing an Experiment to Measure Event-Loop Impact

The goal is not to prove "a thread named `pwd-verify` exists", but to evaluate **responsiveness under concurrent password checks**.

### 9.1. Experiment Setup

Run scenarios in an **isolated test environment**, holding constant:

- JDK, Spring Boot/Security/Reactor versions, algorithm, and BCrypt cost.
- Container CPU/memory limits, instance count, cgroup throttling, Netty and worker configs.
- User/password-hash dataset; do not include hash creation time in every request.
- Connection count, arrival rate (RPS), concurrency, warmup duration, and measurement window.
- Right/wrong password scenarios, account counts, and actual hashes compared.
- Load-generator client with sufficient capacity, ideally on a separate machine from the server to avoid CPU contention.

Never run stress tests against production or use real passwords. Never write raw Authorization headers into load-test logs.

### 9.2. Four Comparison Scenarios

| Scenario | What It Tests | Signals to Watch |
| --- | --- | --- |
| A — no login load | `GET /ping` baseline | P50/p95/p99 latency and throughput of lightweight endpoint |
| B — low login load, proper scheduler | Expected BCrypt overhead | `/ping` stays near baseline; login takes hash time |
| C — login load near CPU limit | CPU contention and queueing effects | Login p95/p99 rises first; `/ping` can slow when host saturates CPU |
| D — misconfigured, `matches` on event loop (test-only) | Proves why offloading matters | Event-loop threads stay busy long; `/ping` lags sharply under equal load |

Scenario D can use a **benchmark-environment-only** test endpoint, never shipped in a public app. Never expose an unsafe password-checking route to real users; the sole goal is comparing event-loop occupancy.

### 9.3. Metrics to Record

**Login:** request rate, success/failure rate, `latency_p50`, `latency_p95`, `latency_p99`, completed throughput, timeout and rejection counts.

**Password check:** isolated `matches` duration, active check count, estimated queue wait, queued job count, password worker utilization.

**WebFlux/Netty:** `/ping` latency, event-loop task delay (via appropriate instrumentation or sampling), thread states, latency of non-password endpoints, socket backlog.

**Host/container:** total CPU / CPU quota throttling, per-core saturation, thread counts, heap/RSS, GC pauses, memory allocation, instance count.

**Security:** failed logins by account/IP (appropriately anonymized), rate-limit rejections, credential-stuffing patterns, with no passwords/tokens logged. A sudden failure spike may indicate a CPU-exhaustion attack.

### 9.4. Sample Results Table (Not a Real Benchmark)

| Scenario | Login RPS | Login p95 (ms) | Ping p95 (ms) | CPU % | In-flight verify | Conclusion |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A — baseline | Measure | Measure | Measure | Measure | Measure | Baseline speed |
| B — light load | Measure | Measure | Measure | Measure | Measure | Compare vs. A |
| C — near saturation | Measure | Measure | Measure | Measure | Measure | Queueing and contention |
| D — event-loop bug | Measure | Measure | Measure | Measure | Measure | Impact of mis-scheduling |

The "Measure" cells must be populated with real measurements; **never invent throughput/latency numbers**. If `/ping` p95 spikes while BCrypt stays on dedicated workers, check CPU saturation/GC and other tasks; offloading does not magically eliminate all system latency.

Measure each load level repeatedly after warmup; report percentiles rather than averages alone; rule out load-generator saturation. Keep cost/password hashes and connection counts identical when comparing two configurations.

## 10. Analyzing Common Scenarios

### Scenario A: Handler Calls BCrypt Directly on the Event Loop

```java
// WRONG example in a WebFlux controller if the current thread is the event loop:
boolean allowed = encoder.matches(passwordFromRequest, storedHash);
return Mono.just(allowed);
```

Calling `matches` directly before returning the Mono stalls the event loop. **Fix:** use the standard manager with its scheduler, or wrap custom checks with `fromCallable(...).subscribeOn(...)`.

### Scenario B: Using the Standard Password Manager While Offloading All of authenticate

```java
// Not needed by default if the manager already has its own scheduler:
return manager.authenticate(authentication)
        .subscribeOn(Schedulers.boundedElastic());
```

This can add overhead and shift upstream steps onto boundedElastic, yet **does not replace the manager's internal scheduler**. Inspect the exact manager instance and use `setScheduler(...)` to manage password workers.

### Scenario C: Every Request Uses HTTP Basic and Re-Verifies

If clients send username/password on **every API request**, BCrypt cost scales with request rate; even with proper protection and working schedulers, verification volume can be high. The architectural fix is using sessions or short-lived tokens after initial authentication, with TTLs, revocation/rotation, transport protection, and a CSRF policy fitting the credential model. Never cache `matches` Booleans indefinitely keyed by raw password as a hasty optimization.

### Scenario D: Adding Threads "to Go Faster"

Once CPU is exhausted, adding threads can increase context switching and memory pressure, especially with Argon2. Worker thread counts for hashing should be sized after measuring CPU quotas, concurrency, target latency, and memory budgets. A dedicated `newParallel` pool only isolates scheduling; it does not grant extra total compute resources.

### Scenario E: Overload and Timeouts

`timeout(Duration.ofSeconds(...))` on `Mono<Boolean>` can cancel the Reactor subscription, but a synchronous hashing call already underway is not guaranteed to abort immediately in every implementation. If requests time out while CPUs keep spinning, load can still climb. Thus **admission control/rate limiting** matters more than merely adding timeouts.

### Scenario F: Nonexistent Users

A path returning immediately when a username is missing vs. a path running BCrypt when a username exists can expose timing differences; authentication design should produce uniform failure responses and weigh timing and workload per framework/policy. Never return "username exists" in a login API, never skip hashing for unknown users without evaluating enumeration risk, and never add dummy hashing without measuring load impact.

### Scenario G: Memory-Hard Hashes

With Argon2/scrypt, concurrency limits must also consider RAM: if each verification uses significant memory, too many concurrent jobs can trigger OOM before CPU reaches 100%. Measure heap and native memory/RSS and container memory limits; do not size solely by `Runtime.availableProcessors()`.

## 11. Implementation Checklist

1. **Authentication mechanism:** Which `ReactiveAuthenticationManager` does HTTP Basic/form login use? Is the exact instance verified on the security chain?
2. **Where hashing runs:** Which thread actually runs `matches`? Is it off `reactor-http-nio-*`?
3. **Scheduler:** Does the standard manager offload already? If custom, are worker count, naming, and disposal configured properly?
4. **Resources:** Have CPU quotas, memory, and BCrypt cost/Argon2 memory cost been benchmarked?
5. **Concurrency:** Is there an instance-wide cap on concurrent login attempts and a bounded queue?
6. **Overload:** Do overload responses preserve rejection policies rather than turning into successful authentications?
7. **Measurement:** Are hash execution time, queue wait, end-to-end login p95/p99, and `/ping` p95 tracked separately?
8. **Security:** Are rate limiting, anti-enumeration, log redaction, and safe work-factor governance in place?
9. **Testing:** Are valid passwords, wrong passwords, missing users, scheduler execution, timeouts, repository errors, and burst load tested?
10. **Lifecycle:** Are custom pools disposed; do you avoid per-request thread pools and avoid `block()` inside WebFlux?

## 12. Self-Check Questions

**1. Does `Mono.just(encoder.matches(...)).subscribeOn(scheduler)` move BCrypt off the event loop?**  
No. Java evaluates `matches` immediately before creating `Mono.just`. `subscribeOn` takes effect too late.

**2. Why does `Mono.fromCallable(...).subscribeOn(passwordScheduler)` make sense?**  
It defers computation until subscription and picks the worker for the source. You must compose the publisher into a real pipeline and handle results/errors.

**3. What default does Spring Security reactive have for username/password?**  
Per Javadoc, `UserDetailsRepositoryReactiveAuthenticationManager` uses a dedicated parallel scheduler for password verification. `setScheduler(...)` lets you replace the scheduler on the active manager.

**4. Is `boundedElastic` always the best choice for BCrypt?**  
No. `boundedElastic` is mainly intended for blocking I/O. BCrypt is CPU-bound; extra workers do not create extra CPU. A dedicated `newParallel` pool with bounded concurrent verifications is usually easier to control.

**5. After moving hashing to workers, why can `/ping` still slow down under heavy logins?**  
Because workers and the event loop still share the same physical CPU, memory, GC, and CPU quotas. When the host saturates, a scheduler cannot increase total processing capacity.

**6. Can `flatMap(..., 4)` inside each request cap the whole server to 4 concurrent hashes?**  
No. Each request has its own pipeline. You need an instance-wide shared admission controller/bulkhead or gateway-level limits.

**7. Why is measuring only time inside `matches` insufficient?**  
It excludes time spent waiting for a worker, looking up the user, authorizing, and network overhead. Measure end-to-end login latency and scheduler queue wait.

**8. If a request times out, is BCrypt guaranteed to stop immediately?**  
No general guarantee exists. Pipeline cancellation does not necessarily interrupt synchronous CPU work already running.

**9. Should you drop BCrypt strength very low just to improve p95?**  
Do not make that call unilaterally. Work factor is a security requirement and must follow benchmarks, threat models, and policy. Optimize admission control, architecture, and resources first.

**10. What is the fastest way to verify password checks run on the right thread?**  
Temporarily instrument `PasswordEncoder.matches` to log the worker thread name and duration (without logging passwords/hashes), then call the endpoint with valid credentials. Check the dedicated scheduler's prefix alongside CPU/event-loop metrics.

**Key takeaway:** Password verification uses intentionally CPU-expensive algorithms. In WebFlux, **keep that computation off the event loop**, use a properly scheduled manager or `fromCallable(...).subscribeOn(...)` in custom code, bound concurrent work, and measure real latency. "Non-blocking I/O" **does not mean** "zero thread/CPU cost".

## Reference Documentation

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): adaptive one-way functions, work factors, BCrypt/PBKDF2/scrypt/Argon2, and why not to verify passwords on every request.
- [Spring Security — AbstractUserDetailsReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html): `setScheduler(Scheduler)` and the default scheduler for password hashing.
- [Spring Security — UserDetailsRepositoryReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): manager using `ReactiveUserDetailsService` and `PasswordEncoder`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): distinguishing `parallel`, `boundedElastic`, `single`, and thread switching.
- [Project Reactor — FAQ: Wrap a Synchronous Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html): `Mono.fromCallable`, `subscribeOn`, and lazy execution principles.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` and configuring authentication/authorization in WebFlux.
