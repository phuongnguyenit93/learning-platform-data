# Choosing a web model based on workload characteristics and dependencies

In Spring Boot, deciding between **Spring MVC (Servlet)** and **Spring WebFlux (reactive)** must come from the type of work requests perform, how dependent libraries handle I/O, actual concurrency levels, and the team's operational maturity. Merely looking at request counts, seeing the word "async," or wanting "high performance" is not enough reason to pick WebFlux.

## 1. Learning outcomes

After this lesson, you will be able to:

- Distinguish the HTTP flow on Servlet/MVC from the non-blocking flow on WebFlux, including when MVC handles requests asynchronously.
- Inventory **blocking** and **non-blocking** calls across databases, HTTP clients, SDKs, and file I/O before selecting a web stack.
- Choose the appropriate model for CRUD with JPA, API gateways calling multiple services, streaming/SSE, CPU-heavy tasks, and mixed systems.
- Explain switching costs, intermediate approaches, and measurement-driven validation rather than relying on intuition.

## 2. Two models and their runtime characteristics

### 2.1. Spring MVC / Servlet

- HTTP input typically passes through a Servlet container (e.g., Tomcat/Jetty) and `DispatcherServlet`; controllers can return ordinary values such as `String`, DTOs, or `ResponseEntity<T>`.
- Imperative programming is convenient when using JPA/Hibernate, JDBC, synchronous HTTP clients, and SDKs with blocking methods. Processing threads can be held while waiting on I/O; thread pools and downstream connection pools must be appropriately bounded.
- MVC **does not mean "no async support"**: `Callable`, `DeferredResult`, `CompletableFuture`, `SseEmitter`, `StreamingResponseBody`, and certain reactive return types are supported. Servlet async can release the request thread while waiting, though Servlet response writing still differs from WebFlux's non-blocking I/O model.
- Java 21+ can combine **virtual threads** in supported Spring Boot configurations (`spring.threads.virtual.enabled=true`). This is worth evaluating when many tasks wait on synchronous I/O, though it does not turn JDBC/SDKs into non-blocking APIs and does not solve connection pool limits or CPU work.

### 2.2. Spring WebFlux / Reactive

- HTTP is handled by the reactive web layer (`DispatcherHandler`); controllers can return `Mono<T>` (0 or 1 result) or `Flux<T>` (multiple results). WebFlux builds on non-blocking I/O and Reactive Streams, providing demand regulation (**backpressure**) when participating components support it.
- The event-loop model typically uses few event-processing threads; to benefit, the execution chain must avoid blocking those threads. `WebClient`, compatible R2DBC drivers, and other reactive APIs can compose into a pipeline that does not block threads while waiting on the network.
- WebFlux defaults to Reactor Netty in Spring Boot apps using the WebFlux starter; it **is not forced to run on Netty**, as it can also run via adapters on compatible Servlet containers. The server name alone does not dictate whether application code is non-blocking.
- Reactor does not turn a blocking call into non-blocking simply by wrapping it in `Mono.just(...)`. Calling JDBC, `Thread.sleep`, `Future.get`, or `.block()` on the event loop still blocks the thread.

### 2.3. Illustrating the difference at the I/O wait point

```text
MVC (typical synchronous processing path):
HTTP → Servlet thread → Controller → blocking JDBC/SDK → wait on I/O → Response

WebFlux (truly non-blocking pipeline):
HTTP → Event loop → Controller → non-blocking WebClient/R2DBC
                         ↳ register callback, thread freed for other work
                         ↳ result arrives → resume pipeline → Response
```

This is a conceptual diagram. Do not infer that every MVC request always holds a single thread for its entire lifecycle, or that WebFlux never uses other threads: async MVC, executors, schedulers, virtual threads, and thread-hopping make actual behavior more varied.

## 3. Deciding factors: workload and the full dependency chain

| Workload / library characteristic | Initial recommendation | Rationale and conditions |
| --- | --- | --- |
| CRUD with Spring Data JPA/Hibernate or `JdbcTemplate` | **MVC** | JDBC/JPA perform blocking I/O; MVC fits the imperative transaction model and existing libraries. |
| Payment SDKs, LDAP libraries, synchronous HTTP clients, or third-party drivers with only blocking APIs | **MVC** or isolate via separate adapter | WebFlux cannot avoid the library's I/O wait. |
| Proxy/aggregation service calling many HTTP APIs via `WebClient`, with no blocking dependencies on the main path | **Consider WebFlux** | Many requests waiting on network concurrently can benefit from non-blocking execution once benchmarked. |
| App using R2DBC and reactive data sources/network clients end-to-end | **Consider WebFlux** | Non-blocking behavior can span from HTTP to database; verify drivers and actual transaction management. |
| Standard HTML/REST, moderate traffic, team experienced with imperative Java | **MVC** | Simpler to develop, debug, trace, and integrate with traditional libraries. |
| Long-lived SSE or streaming with huge connection counts, where all pipeline parts support non-blocking | **Consider WebFlux** | Reduces threads waiting on connections when the architecture stays genuinely non-blocking and controls load well. |
| SSE/streaming with modest connections or system already on MVC | **MVC remains viable** | `SseEmitter`/`StreamingResponseBody` may suffice; streaming alone does not force WebFlux. |
| Image encoding, report computation, CPU-heavy work | **Neither model solves this alone** | Use appropriate worker pools/queues, bound concurrency and CPU; never run heavy CPU tasks on the event loop. |
| System mixing blocking JPA with a few HTTP calls needing async | **Usually keep MVC + WebClient** | Adding the reactive client helps without changing the server stack or refactoring persistence. |

**Key principle:** Base your decision on the *actual request execution path*. Even a single critical blocking library on the hot path forces WebFlux into a blocking-isolation strategy, and the net benefit must be verified.

## 4. How to inventory dependencies before choosing

For a representative request, map the path from controller to response and tabulate every I/O point:

1. **Database:** Spring Data JPA/JDBC/`JdbcTemplate` are blocking; R2DBC offers reactive APIs, but the driver, business logic, and transactions must all align.
2. **Outbound HTTP:** `RestTemplate`/`RestClient` are typically synchronous; `WebClient` exposes a reactive API. Calling `WebClient(...).block()` still blocks the caller.
3. **Third-party SDKs:** check the SDK's API docs and actual behavior; do not treat `Async` in a method name as proof of non-blocking if it waits internally or uses a bounded pool.
4. **Files, object storage, message brokers, and caches:** inspect each driver and operation. "Has callbacks" and "does not block the event loop" must be verified concretely; do not label something non-blocking by technology name alone.
5. **Framework integrations:** check Servlet filters, `SecurityFilterChain`-style Spring Security, sessions, interceptors, exception handlers, and Servlet-only libraries. WebFlux uses corresponding reactive integrations, such as `SecurityWebFilterChain`.
6. **Infrastructure and pools:** check HTTP/database pools, timeouts, queues, rate limits, retry behavior, and CPU/memory caps. WebFlux does not increase how many database connections a pool can serve.

When a dependency's behavior is unverified, mark it **"unverified"** in your technical inventory rather than assuming non-blocking. An end-to-end reactive architecture only makes sense when critical dependencies genuinely support it.

## 5. Practical selection workflow

```text
Start from the most critical request
  |
  +-- Main dependency is blocking JPA/JDBC/SDK? -- Yes --> Prefer MVC
  |                                                   |
  |                                                   +--> Need async HTTP?
  |                                                        Use WebClient/Servlet async
  |
  +-- No --> Primarily high-concurrency network I/O waits?
                  |
                  +-- No --> MVC is an easy-to-maintain default
                  |
                  +-- Yes --> Are client, DB, cache, auth all reactive-ready?
                                |
                                +-- No --> Keep MVC or isolate blocking parts;
                                |          re-measure benefit before switching stacks
                                |
                                +-- Yes --> Prototype WebFlux under representative load,
                                            measure p95/p99, resources, complexity
```

A selection step can be captured in a short **ADR (Architecture Decision Record)**: primary workload, blocking libraries, load targets, chosen model, alternatives, and validating metrics. Without clear justification or measurements, MVC is a sound starting point for most imperative business apps; there is no need to migrate a well-performing MVC app solely because WebFlux is newer.

## 6. Declaring starters: do not let dependencies pick your runtime by accident

In Gradle, the following examples assume you generated a Spring Boot project via Spring Initializr. Add only the starter for the intended web stack *per project*, and manage versions via the Spring Boot plugin/BOM:

```groovy
// Spring Boot 3.x: MVC application
implementation 'org.springframework.boot:spring-boot-starter-web'

// Spring Boot 4.x: dedicated MVC starter
implementation 'org.springframework.boot:spring-boot-starter-webmvc'

// MVC or WebFlux when a reactive HTTP client is needed (depends on Boot version):
// check the specific Boot version's WebClient starter or webflux dependency.
```

```groovy
// Spring Boot 3.x/4.x: reactive WebFlux application
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

These lines are **alternatives by version and model**, not a list to add together into a single app. In Spring Boot 3.x, if both `spring-boot-starter-web` and `spring-boot-starter-webflux` appear together, Boot normally auto-configures **Spring MVC**. That allows using `WebClient` inside MVC; do not assume having `Mono` or the WebFlux starter in the dependency tree guarantees the server is WebFlux. If you deliberately want a reactive web application, configure it explicitly and verify compatibility across the whole application.

Note: starter and module names can change across major versions. Always cross-check starters against the **Boot version in use**; specifically, Spring Boot 4 introduces `spring-boot-starter-webmvc` and treats `spring-boot-starter-web` as the legacy path.

## 7. Two standalone runnable Java 17+ examples

The two examples below are **two separate Spring Boot projects**, both using the `/demo` path, run one at a time on port 8080. They only demonstrate how controllers express waiting operations; `sleep`/timers are simulations and do not represent real I/O benchmarks.

### 7.1. Project A: MVC and blocking call

Create a Spring Boot 3.x project with the **Spring Web** dependency (or Spring Boot 4.x with **Spring Web MVC**), and create `src/main/java/demo/MvcApplication.java`:

```java
package demo;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }

    @GetMapping("/demo")
    public String demo() throws InterruptedException {
        TimeUnit.MILLISECONDS.sleep(80); // Simulates synchronous waiting SDK/JDBC
        return "mvc-ok";
    }
}
```

Here the thread executing the method must wait about 80 ms. When replacing this with real JPA/JDBC or synchronous SDKs, configure connection pools, timeouts, and rate limits; do not use `sleep` in production.

### 7.2. Project B: WebFlux and asynchronous signal

Create another Spring Boot project with only the **Spring Reactive Web / WebFlux** starter, and create `src/main/java/demo/WebFluxApplication.java`:

```java
package demo;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class WebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }

    @GetMapping("/demo")
    public Mono<String> demo() {
        return Mono.delay(Duration.ofMillis(80))
                .map(ignored -> "webflux-ok");
    }
}
```

`Mono.delay` schedules a signal after about 80 ms; do not call `Thread.sleep` on the event loop. In real applications, replace the timer signal with `WebClient`, R2DBC, or suitable reactive APIs. Do not compare "80 ms" across these two tiny programs to conclude which model is faster.

In **each project's** directory, run:

```bash
./gradlew bootRun
curl -s http://localhost:8080/demo
```

On Windows PowerShell, use `./gradlew.bat bootRun` (or `.\gradlew.bat bootRun`) and `curl.exe -s http://localhost:8080/demo`. After the server starts, Project A's HTTP stdout body is `mvc-ok`, and Project B's is `webflux-ok`. Stop Project A before starting Project B if both use port 8080. With Boot 3.x, Java 17+ is suitable; check the Java requirements of your chosen major version and starters.

## 8. When an application mixes reactive and blocking

### 8.1. MVC can still use WebClient

An MVC controller can return a `Mono<String>` obtained from `WebClient`; Spring MVC adapts reactive return types for asynchronous response handling. Example **integration snippet**, assuming an injected `WebClient` pointing to a service with endpoint `/status`:

```java
@GetMapping("/remote-status")
public Mono<String> remoteStatus() {
    return webClient.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
}
```

The snippet above is a **controller snippet**, not a standalone Java program; it requires the `webClient` bean, target service, and corresponding dependencies. Avoid adding `.block()` if the goal is returning asynchronously. This approach does not convert the entire MVC server to WebFlux.

### 8.2. WebFlux forced to call a blocking library

If you are on WebFlux but must invoke a legacy blocking API, isolate the call on a scheduler meant for blocking—for example, a **snippet** inside a service:

```java
Mono<LegacyResult> result = Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

Import `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`; `LegacyResult`/`legacyClient` are hypothetical project types/objects. `boundedElastic` avoids tying up the event loop while waiting, yet **still consumes threads and resources**, and still needs timeouts/load limits; it does not make the legacy client non-blocking. Use `Mono.fromCallable(() -> legacyClient.fetch())` so execution occurs only upon subscription, rather than `Mono.just(legacyClient.fetch())` which blocks immediately when constructing the publisher.

If most business flows must be offloaded to `boundedElastic`, reconsider choosing WebFlux: MVC may be clearer and easier to maintain.

### 8.3. Virtual threads do not replace dependency inventory

With Java 21+ and a supporting Spring Boot version, configure:

```properties
spring.threads.virtual.enabled=true
```

Virtual threads can improve throughput while waiting on I/O in imperative code; they do not speed up CPU, lower database latency, increase connection counts, or turn blocking APIs reactive. Benchmark pinning/tracing, connection pools, and concurrency limits before adopting, and check where Boot actually uses virtual-thread executors in your version.

## 9. Four model-selection scenarios

**Scenario A — Order management.** Controller creates orders, calls JPA/Hibernate, uses synchronous transactions, and invokes a blocking payment SDK. Choose **MVC**. Optimize database queries, connection pools, timeouts, idempotency, and isolate high-latency network calls before considering a stack switch.

**Scenario B — Aggregation API gateway.** A single request concurrently calls 5 APIs using `WebClient`, performs no JDBC access, and all adapters are non-blocking; thousands of connections wait on the network simultaneously. **WebFlux is worth trying** if the team masters reactive error handling, timeouts, cancellation, backpressure, and observability. MVC with an async client also serves as a comparison baseline.

**Scenario C — Task notification SSE.** The app has only a few hundred connections and already runs steadily on MVC: try `SseEmitter` first. A system with huge numbers of streaming connections and reactive producers: consider WebFlux. Account for proxy timeouts, keep-alives, client disconnects, bounded buffering, and slow consumers.

**Scenario D — CPU-heavy report generation.** Exporting large reports, encrypting files, and reading data for minutes: do not adopt WebFlux expecting lower CPU usage. Offload work to a resource-bounded background job/queue with an API returning a task ID; MVC can serve as the HTTP frontend, or WebFlux if other reasons warrant it.

## 10. Measure to confirm your decision

Using the same business logic and dataset, test **warm-up**, normal load, bursts, and slow/failing dependency states. Record:

- **Responsiveness:** successful requests/s, p50/p95/p99 latency, timeouts, and error rates; compare under the same functional target.
- **Resources:** CPU, heap/GC, thread counts, event-loop utilization/blocking, active requests, and queue lengths.
- **Dependency bottlenecks:** active/waiting database pool connections, HTTP client pools, connection timeout rates, retry amplification, and rate limits.
- **Operability:** stack trace clarity, context propagation in logs/traces, transaction testing, cancellation behavior, learning curve, and library integration quality.

For example, if throughput is capped by at most 20 database connections or an SDK allowing only 50 requests/s, switching to WebFlux **will not automatically remove that bottleneck**. The goal is meeting SLAs with acceptable complexity, not minimizing thread counts at any cost.

## 11. Stack selection mistakes and how to avoid them

1. **"WebFlux is always faster than MVC."** False: gains depend on workload, I/O wait ratio, libraries, and configuration. Measure under representative load.
2. **"Returning `Mono` means it is already non-blocking."** False if blocking methods are still called inside `map`, `flatMap`, or during publisher creation.
3. **"You must use WebFlux for WebClient/async/SSE."** False: MVC supports async and streaming; `WebClient` also works with MVC.
4. **"JPA runs fine on the event loop because it has a reactive wrapper."** False: JPA/JDBC remain blocking; isolate blocking work or stay on MVC and account for transaction semantics.
5. **"Adding both starters makes Spring Boot pick WebFlux."** Usually false in Boot 3.x configurations: MVC takes precedence when both starters are present. Verify the actual started web application type.
6. **"Many concurrent requests mean heavy CPU work."** Not necessarily: distinguish I/O-waiting connections from CPU computation; measure separately.
7. **"With backpressure, memory can never overflow."** False: buffering, data sources, operators, clients, and external systems still require explicit bounds.
8. **"Virtual threads solve all blocking libraries."** False: they do not replace timeouts, connection pools, circuit breakers, or downstream capacity.
9. **"Migrating completely to reactive is always better."** Not necessarily: migration costs for transactions, security, testing, observability, and training can outweigh benefits.

## 12. Self-check exercises

**Question 1.** A CRUD API uses PostgreSQL + Spring Data JPA, up to a few hundred requests/s, with all synchronous SDKs. Which stack to choose? **Hint:** MVC, because the primary processing path is blocking and existing libraries suit imperative code.

**Question 2.** An API gateway uses WebClient for 8 upstreams, needs to hold tens of thousands of network-waiting connections, and has no blocking drivers. What should you do? **Hint:** prototype WebFlux, benchmark against async MVC; inspect tail latency, memory, HTTP pools, timeouts, and cancellation.

**Question 3.** A WebFlux controller calls JPA's `repository.findAll()` inside `Mono.just(...)`. Is it non-blocking? **No.** The JPA call executes immediately when creating the Mono; change strategy or isolate onto an appropriate scheduler, and re-evaluate choosing WebFlux.

## 13. Pre-decision checklist

- [ ] Described key requests and I/O wait time relative to CPU time.
- [ ] Marked blocking/non-blocking status for DB, HTTP clients, SDKs, caches, and other I/O.
- [ ] Checked servlet/reactive integrations, transactions, security, and starter versions.
- [ ] Considered MVC async, WebClient, and virtual threads as viable alternatives.
- [ ] Designed timeouts, pools, concurrency limits, retries/circuit breakers, and observability.
- [ ] Benchmarked under representative load; recorded the decision with evidence in an ADR.

## Official references

- [Spring Framework — WebFlux Overview and Applicability](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Task Execution, Scheduling and Virtual Threads](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)