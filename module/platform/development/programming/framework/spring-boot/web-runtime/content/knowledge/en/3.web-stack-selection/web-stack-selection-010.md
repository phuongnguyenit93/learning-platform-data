# Evaluating Blocking Libraries Before Choosing the Reactive Model in Spring Boot

## 1. The problem to solve

When choosing between Spring MVC and Spring WebFlux for a Spring Boot application, you cannot look solely at controller return types. **A request-processing path only truly gains non-blocking benefits when the critical I/O calls along that path also do not hold threads while waiting.** An application that uses `Mono` and `Flux` while still calling JDBC/JPA, a synchronous HTTP client, or a sync SDK directly on the event loop can suffer higher tail latency, throttled throughput, and harder operations.

The goal of this lesson is to establish an actionable evaluation method: inventory libraries, pinpoint exact blocking calls, measure behavior under load, evaluate isolation or replacement options, and then choose between Spring MVC, Spring MVC with virtual threads, or Spring WebFlux based on evidence.

Technical context: Spring Boot 3.x, Spring Framework 6, Reactor, and Java 17+; the approach also applies to newer Spring versions when checked against their corresponding APIs.

## 2. Distinguishing synchronous, blocking, asynchronous, and reactive

| Concept | Meaning | Examples and notes |
|---|---|---|
| Synchronous | The caller follows control flow directly to obtain the result | A synchronous API may perform short CPU work; not every synchronous call waits on I/O |
| Blocking | The thread cannot proceed with other work because it is waiting on a condition, I/O, lock, or result | `InputStream.read`, JDBC query, `Thread.sleep`, `Future.get` |
| Asynchronous | The result is delivered later via callback, future, or signal | `CompletableFuture` may still execute a blocking call inside an executor |
| Reactive | Models work as a stream of data/error/completion signals, supporting asynchronous coordination and backpressure | `Mono`, `Flux`, `Publisher`; can still contain blocking operations inside |

Key points to remember:

- A method returning `Mono<T>` **does not guarantee** the code inside is non-blocking. For example, `Mono.just(jdbcRepository.findById(id))` already calls JDBC before creating the publisher.
- `Mono.fromCallable(() -> legacyCall())` defers execution lazily, yet the callable can still block the thread used to subscribe.
- `CompletableFuture.supplyAsync(() -> jdbcCall())` moves waiting onto a thread pool; JDBC has not become non-blocking I/O.
- Backpressure regulates data demand between reactive components; it does not make a synchronous SQL query return faster and does not replace connection pool limits.

## 3. Why can a blocking library bottleneck WebFlux?

Spring MVC typically uses Servlet worker threads to handle requests. That thread can wait on JDBC, sync HTTP, or file I/O. This model is straightforward and fits the synchronous library ecosystem well, provided thread pools, timeouts, connection pools, and concurrency limits are properly configured.

Spring WebFlux supports the reactive programming model and can run on Reactor Netty or a compatible servlet container. With Reactor Netty, a relatively small set of event-loop threads manages many connections. The event loop must yield control quickly to serve other connections. When a callback on the event loop waits on a JDBC query or a synchronous socket call, other connections sharing that thread are delayed.

~~~text
Path A: non-blocking HTTP call
Event-loop -> send async request -> yield control to event-loop
                                 -> response signal -> continue pipeline

Path B: blocking library on event-loop
Event-loop -> call sync JDBC/HTTP -> WAIT -> WAIT -> receive result
              (cannot process other work on this event-loop)

Path C: isolated blocking library
Event-loop -> schedule work on boundedElastic -> yield control to event-loop
boundedElastic worker -> call sync library -> WAIT -> return result
~~~

Path C protects the event loop, yet it still consumes worker threads, sockets, DB connections, and queue space. Wrapping a synchronous library in a reactive wrapper only changes **where blocking happens**; it does not magically scale capacity indefinitely.

## 4. Inventorying the entire request-processing path

Do not inspect only controller code. Trace each critical endpoint end to end:

~~~text
HTTP -> filter -> authentication/authorization -> validation
     -> controller/handler -> service -> repository/cache/HTTP/SDK/files
     -> mapping/serialization/logging -> HTTP response
~~~

Document the following for each I/O call:

1. Dependency name and version; exact method/overload actually invoked.
2. Is it blocking? If so, what resource does it wait on: socket, DB, file, lock, connection pool, or thread?
3. On which thread/scheduler is the method called? Could it run on the Reactor Netty event loop?
4. Is there a native async/reactive option? Does the underlying async API run on non-blocking transport, or is it merely an executor running blocking calls?
5. How are timeouts, retries, connection limits, and cancellation configured?
6. Does it rely on `ThreadLocal`, `@Transactional`, MDC, security context, locale, or request-scoped state?
7. Is the work CPU-bound or I/O-bound? Does it stream or accidentally read entire files/responses into RAM?
8. Is the operation on a hot path, high frequency, high fan-out, or high p99?

Also audit cache misses, token refreshes, signature verification, audit logging, DNS lookups, heavy serialization, custom `WebFilter`s, and `WebExceptionHandler`s. A single blocking call inside a filter can impact all requests before they even reach a controller.

## 5. Library categories commonly needing evaluation

| Category | Usage with blocking risk | Alternatives / mitigations |
|---|---|---|
| Relational persistence | JDBC, JPA/Hibernate, `JdbcTemplate`, JDBC-backed `JpaRepository` | Keep Spring MVC; or evaluate Spring Data R2DBC and an R2DBC driver matching your DB |
| Outbound HTTP | `RestTemplate`, synchronous `RestClient`, many Feign client setups, `HttpClient.send` | `WebClient` + non-blocking connector; SDK async HTTP client if truly non-blocking |
| Redis/cache | Synchronous commands on Redis client; cache loaders calling sync DB/HTTP | Driver's async/reactive API such as Lettuce, or isolate sync portions |
| NoSQL | Synchronous client/repository APIs | Official reactive drivers and repositories; inspect each method |
| Cloud SDK | Sync APIs for object upload/download, payment/secret/service calls | Async SDKs and streaming APIs; inspect thread model and timeouts |
| Filesystem | `Files.readAllBytes`, `InputStream.read`, reading/writing large files | Async NIO where appropriate or a bounded worker pool; avoid exhausting memory |
| Security | Synchronous user/token lookup, credential refresh over sync HTTP | Structure reactive authentication flows, non-blocking clients, analyze callbacks |
| Crypto/reporting | Password hashing, compression, PDF generation, image rendering | Offload CPU-bound work from the event loop; consider job queues and worker pools |
| Messaging | Producer/consumer APIs may be async while serialization/callbacks stay synchronous | Verify callback execution threads, queues, flow control, and backpressure |

**Pay attention to the exact API invoked.** Having both sync and reactive libraries on the classpath does not prove an endpoint uses the non-blocking version. A client named "async" may still use an executor wrapping a sync library. Connection pooling helps reuse connections, yet it does not turn a JDBC call into non-blocking I/O.

### 5.1. Blocking examples to spot

~~~java
// Code in a normal MVC service may be reasonable,
// but should not run directly on the WebFlux event loop.
Order order = orderRepository.findById(orderId).orElseThrow();

// Synchronous HTTP client: thread waits for server response.
Customer customer = restClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .body(Customer.class);

// Builds a reactive pipeline yet still waits synchronously at the end.
Customer customer2 = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .block();

// Synchronous file I/O.
byte[] bytes = Files.readAllBytes(path);
~~~

These snippets are illustrative, not a standalone Java class. Avoid calling `block()`, `blockFirst()`, `blockLast()`, `Future.get()`, or `Thread.sleep()` on the event loop. On threads marked non-blocking by Reactor, `block()` may throw `IllegalStateException`; not seeing an exception does not prove all I/O is safe.

### 5.2. Is R2DBC a drop-in replacement for JPA?

No. R2DBC provides a non-blocking API for relational databases when using a supported driver. It differs from the JDBC/JPA model in mapping, persistence context, lazy loading, transactions, query APIs, and ecosystem integrations. Before switching, audit business features, driver performance, connection pooling, transaction handling, and migration cost. If an application depends heavily on JPA, keeping MVC typically saves significant complexity.

## 6. Dependency and code audit workflow

### Step 1: Inspect runtime dependencies

In a Maven or Gradle project, run the corresponding command:

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for JDBC/JPA, HTTP, Redis, cloud SDK, reporting, messaging clients, and custom wrappers. The dependency tree only shows which libraries are present; inspecting actual call sites determines the blocking paths.

### Step 2: Audit risky calls

Use your IDE's Find Usages/Call Hierarchy or code search to trace `block`, `join`, `get`, `sleep`, synchronous repositories, `Files.readAllBytes`, `InputStream.read`, `RestClient`, `RestTemplate`, and sync SDK calls. Also inspect adapter layers used inside services.

Do not assume every keyword match is a bug. For example, `join` on an in-memory string sequence has different semantics, and a method named `get` does not necessarily block. Check the implementation and API documentation.

### Step 3: Focus on high-impact endpoints

Prioritize endpoints with high p95/p99, high concurrency, fan-out to multiple APIs, slow DB queries, or streaming/upload/download. For each endpoint, build a profile:

| Endpoint | Dependency | Behavior | Expected handling |
|---|---|---|---|
| GET /orders/{id} | JPA Repository | Sync blocking SQL | Prefer MVC or evaluate persistence change |
| GET /recommendations | WebClient | Non-blocking HTTP if not calling `block()` | Good candidate for WebFlux |
| POST /reports | Sync SDK + PDF generation | I/O wait and heavy CPU | Offload to worker/task queue; optionally return 202 |
| GET /profile | Sync Redis | Socket wait | Switch driver API or isolate on boundedElastic |

Wait times, call counts, and error rates must come from real tracing/metrics; do not use guessed numbers to select a stack.

### Step 4: Classify risk level

- **Very high risk:** blocking occurs on the event loop along a hot path, many requests wait a long time, with no timeout bounds or bulkhead.
- **High risk:** many blocking calls are offloaded to the same boundedElastic while DB pools, queues, and concurrency are uncontrolled.
- **Medium risk:** a few sync libraries on low-traffic paths, with timeouts and bounded schedulers, actively monitored.
- **Low risk:** primary I/O uses non-blocking drivers/transport, callbacks are short, and behavior is verified by load tests.

These are relative guidelines; actual thresholds must be measured on your system.

## 7. Verify at runtime instead of guessing

### 7.1. Profiling and thread dumps

Java Flight Recorder (JFR), async-profiler, Java thread dumps, and tracing reveal threads parked on socket reads, DB drivers, connection pool acquisition, file I/O, or locks. Thread names containing `reactor-http-nio` may suggest a Reactor Netty event-loop thread, though you must inspect the call stack and deployment environment because thread names can vary.

Inspect `map`, `flatMap`, `doOnNext` callbacks, filters, security logic, serialization/deserialization, and error handlers. If these steps invoke synchronous services on the event loop, identify the blocking source before applying fixes.

### 7.2. Blocking-detection tools

BlockHound can help detect certain blocking operations on threads marked non-blocking in test environments. Verify JDK, agent/instrumentation, and library compatibility; the tool does not cover every driver and code path. "No errors reported" does not prove a pipeline is completely non-blocking. Combine static review, thread dumps, tracing, and load testing.

### 7.3. Representative load testing

Compare under identical infrastructure, workload, and pool settings:

- Useful throughput (RPS), p50/p95/p99 latency, and error/timeout rates.
- CPU, RAM, garbage collection, thread counts, and context switching where measurable.
- Event-loop lag or event-loop wait times via actual instrumentation.
- Saturation of `boundedElastic`, scheduler queues, DB/HTTP connection pools, and remote API rate limits.
- In-flight request counts, DB wait times, outbound HTTP call durations, and response sizes.
- Behavior when downstreams slow down, pools exhaust, clients cancel requests, or the service shuts down.

A GET benchmark returning a static string is not enough. If all real endpoints call JDBC, JDBC must be included in the benchmark for stack comparisons to be meaningful.

## 8. Handling blocking libraries when WebFlux is already chosen

### 8.1. Isolating with boundedElastic

When a legacy SDK cannot yet be replaced, wrap the blocking work and schedule it on an appropriate scheduler:

~~~java
Mono<Profile> result = Mono.fromCallable(() -> legacyClient.loadProfile(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` defers execution until subscription. `subscribeOn` runs the source on the specified scheduler. `boundedElastic` is intended for blocking tasks, with bounded resources and queues; it **does not eliminate blocking** and can saturate under high request volume.

Conversely, the following example still blocks before the publisher is created:

~~~java
Profile profile = legacyClient.loadProfile(id);  // blocks immediately on the calling thread
return Mono.just(profile)
        .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` only switches downstream execution from the point where the operator is placed; it does not change the call that already ran before it. Do not use `Schedulers.parallel()` to run long-running blocking I/O calls, because that scheduler primarily serves short CPU tasks.

### 8.2. Bounds required for effective isolation

Align limits across layers: connect/read timeouts, DB pools, concurrent task limits, scheduler size/queue, retry counts, and circuit breakers. A scheduler many times larger than the DB pool may merely shift bottlenecks from the event loop to waiting in the connection acquisition queue.

Reactive cancellation can stop emitting signals in the pipeline, yet it does not guarantee cancelling an in-flight synchronous JDBC or SDK call; always verify driver semantics and timeout mechanisms.

### 8.3. Transactions, ThreadLocal, and context

JPA/JDBC typically uses transaction context bound to `ThreadLocal`. If you must call JPA in WebFlux, place **the entire blocking unit of work with its proper transaction boundary** inside a synchronous service, and call that service via `fromCallable` on boundedElastic. Do not open a transaction on one thread, let repositories hop across other threads, and expect the transaction to remain active. Watch out for Spring proxy behavior: self-invoking `this.someTransactionalMethod()` may bypass the `@Transactional` proxy.

Reactive transactions on R2DBC use `ReactiveTransactionManager` and Reactor Context; they do not behave identically to JDBC transaction managers. For MDC, Spring Security context, locale, and tracing, use proper context propagation mechanisms and test across every scheduler boundary.

## 9. Spring Boot 3.x, Java 17 example: WebFlux wrapping a blocking service

The following example belongs in `src/main/java/example/web/ReactiveAuditApplication.java` of a Spring Boot 3.x project with `spring-boot-starter-webflux`. It includes the main class, beans, and endpoint needed to start. `Thread.sleep(40)` only simulates a blocking API; do not use it for I/O in real applications.

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuditApplication.class, args);
    }

    public record Profile(long id, String name) {}
}

@Service
class LegacyProfileService {

    ReactiveAuditApplication.Profile load(long id) {
        try {
            Thread.sleep(40);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return new ReactiveAuditApplication.Profile(id, "demo");
    }
}

@RestController
class ProfileController {

    private final LegacyProfileService service;

    ProfileController(LegacyProfileService service) {
        this.service = service;
    }

    @GetMapping("/profiles/{id}")
    public Mono<ReactiveAuditApplication.Profile> find(@PathVariable long id) {
        return Mono.fromCallable(() -> service.load(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Start using the project's wrapper:

~~~bash
./mvnw spring-boot:run
# or:
./gradlew bootRun
~~~

Call the endpoint once the server is running:

~~~bash
curl -s http://localhost:8080/profiles/7
~~~

Expected JSON body:

~~~json
{"id":7,"name":"demo"}
~~~

The `load` call still blocks a boundedElastic worker for roughly 40 ms. Use this example to learn how to keep the event loop isolated from synchronous libraries, not as an end-to-end non-blocking application. For real tasks, bound concurrency and configure timeouts on clients or databases.

### 9.1. When a non-blocking HTTP client is available

The snippet below is a method inside a Spring component injected with a properly base-URL-configured `WebClient`; it is not a standalone Java program:

~~~java
Mono<ReactiveAuditApplication.Profile> loadRemote(
        WebClient webClient, long id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ReactiveAuditApplication.Profile.class);
}
~~~

With WebClient and a non-blocking connector, HTTP I/O can run without holding a worker thread while waiting on the network. Do not call `block()` inside a WebFlux handler. Define timeouts, error mapping, retry policies, and buffer allocation limits for real clients.

## 10. If most of the system remains blocking: Spring MVC is a sound choice

Spring MVC is the natural option when an application relies heavily on JPA/Hibernate, JDBC, synchronous SDKs, or imperative transactions. Choosing MVC does not mean lacking scalability; tuning connection pools, caching, timeouts, request concurrency, boundary backpressure, and offloading long jobs remain critical.

When running Java 21+ with a supporting Spring Boot version, **virtual threads** are an option worth evaluating for Servlet/MVC under high I/O-waiting workloads. Virtual threads can reduce the cost of threads tied to blocking requests, yet JDBC remains synchronous and databases/connection pools do not automatically gain higher throughput. Measure pinning, synchronized/lock contention, CPU-bound work, and other resource limits.

WebFlux fits better when most dependencies on the hot path support non-blocking operations: WebClient, reactive drivers, data streams, high concurrency waiting on I/O, or SSE. If many legacy libraries cannot be replaced, you can separate blocking business logic into a dedicated MVC service and communicate with the reactive part over HTTP/messaging boundaries, though weigh added deployment, tracing, and data consistency complexity.

## 11. Decision matrix

| Current state | Evaluate first | Rationale |
|---|---|---|
| Heavy JPA/JDBC, sync HTTP, and imperative transactions | Spring MVC | Matches existing libraries and transaction mechanics |
| Many requests waiting on sync I/O; Java 21+ with virtual threads support | Spring MVC + virtual threads | Can lower waiting thread overhead while keeping sync APIs |
| Outbound HTTP and DB both have reactive/non-blocking drivers; streaming needed | Spring WebFlux | Enables optimizing event loops and data pipelines |
| WebFlux with only a few sync SDKs on low-traffic paths | WebFlux + bounded boundedElastic | Isolates blocking parts while monitoring queues and pools |
| WebFlux where most endpoints call JPA/sync HTTP | Consider MVC or a dependency migration roadmap | Blanket reactive wrappers add complexity without changing I/O behavior |
| Report generation or long-running CPU-heavy tasks | Worker/task queue, 202 API where appropriate | Avoids holding request threads or event loops for the entire task |

Decisions should rest on **throughput, p99, stability, connection counts, migration complexity, team skills, and real operations**. No single model wins every workload.

## 12. Test scenarios before switching stacks

1. **Happy path:** endpoints return expected data, and traces show all dependencies and the thread model.
2. **Slow downstream:** introduce controlled DB/API latency; measure event-loop lag, p95/p99, queue times, and in-flight requests.
3. **Connection pool exhaustion:** temporarily shrink the pool for testing; verify timeouts, concurrency caps, and graceful error handling.
4. **Increasing concurrent load:** compare MVC/WebFlux with identical CPU/RAM, workload, and pool/timeout settings; observe threads, CPU, and memory.
5. **Mid-flight request cancellation:** client times out/disconnects; check whether sync work continues and whether resources are released properly.
6. **Upstream failures:** simulate 5xx, network drops, slow DNS, and retry storms; verify backoff, circuit breakers, bulkheads, and recovery.
7. **Transaction testing:** verify no transaction or security/tracing context is lost across scheduler transitions.

Do not extrapolate from a "hello world" benchmark. If a migration changes both the DB driver and pool settings at once, record the result as the combined effect of multiple changes.

## 13. Common design mistakes

- **Only adding Mono/Flux:** without inspecting underlying JPA or HTTP clients.
- **Calling `block()` on the event loop:** turns a reactive pipeline into a synchronous wait point.
- **Assuming an async API is non-blocking:** overlooking that the library uses an executor to run blocking calls.
- **Moving everything onto boundedElastic:** without monitoring queues, worker counts, and connection pools, creating new bottlenecks.
- **Using the parallel scheduler for long-blocking I/O:** degrades capacity of the CPU scheduler.
- **Losing transactions/context when switching threads:** business logic can fail silently even if endpoints return responses.
- **Relying on BlockHound as sole proof:** missing drivers, SDKs, or uninstrumented code paths.
- **Confusing CPU-bound with I/O-bound:** compression/hashing/reporting consumes CPU and must still avoid stalling the event loop.
- **Skipping load tests with slow dependencies:** missing failures that only appear when DB pools or outbound APIs approach limits.
- **Assuming virtual threads have no limits:** DBs, sockets, CPU, and remote rate limits remain bottlenecks.

## 14. Checklist before finalizing WebFlux vs. MVC

- [ ] Listed critical endpoints and all dependencies on the processing path.
- [ ] Categorized APIs into blocking, async wrappers, and truly non-blocking.
- [ ] Audited JDBC/JPA, sync HTTP clients, Redis, cloud SDKs, filesystem, security, and CPU-heavy work.
- [ ] Searched for blocking calls inside WebFlux filters, handlers, operators, and callbacks.
- [ ] Verified reactive drivers and APIs satisfy transaction/feature requirements.
- [ ] Defined a plan for sync libraries: keep MVC, replace APIs, or isolate with bounded schedulers.
- [ ] Verified ThreadLocal, MDC, security, tracing, and `@Transactional` across async boundaries.
- [ ] Configured timeouts, bounded concurrency, connection pools, retries, and error handling.
- [ ] Measured throughput, p95/p99, event-loop, scheduler/pool saturation, and errors with slow dependencies.
- [ ] Documented assumptions, technical decisions, test data, and review criteria.

## 15. Conclusion

**Choose the reactive model only after evaluating the real behavior of libraries across the entire I/O path.** Spring WebFlux can deliver major benefits when critical components are non-blocking and workloads involve many waiting connections; Spring MVC fits when persistence and SDKs are predominantly synchronous. You can use boundedElastic for a small number of blocking libraries that must remain, provided pools, timeouts, cancellation, context, and transactions are treated as finite resources. Measurements under representative load are the final basis for selecting a stack.
