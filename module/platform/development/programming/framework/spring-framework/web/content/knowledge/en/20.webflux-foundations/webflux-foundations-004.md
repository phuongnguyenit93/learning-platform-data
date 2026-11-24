# Event Loop, Threading Model, and the Harm of Blocking Operations in Spring WebFlux

## 1. The Problem: Why Can One `sleep` Stall All of WebFlux?

Suppose a Reactor Netty–based WebFlux server receives many concurrent requests. Each request needs to wait 300 ms for an external service. When handled properly with asynchronous I/O, the event-loop thread **does not sit idle waiting** for the response; it can continue serving other connections and is woken up when an I/O event completes.

Conversely, if inside a handler you do:

~~~java
@GetMapping("/bad")
public Mono<String> bad() throws InterruptedException {
    Thread.sleep(300);              // BLOCKS the request/event-loop thread!
    return Mono.just("done");
}
~~~

then `Thread.sleep(300)` runs **immediately when Spring invokes the controller method**, before `Mono.just` is even created. In the typical Netty event-loop model, this can occupy an event-loop thread for 300 ms. Other connections assigned to that loop must wait; the result can be latency spikes, throughput drops, timeouts, and "cascading failures" under high load.

**`Mono<T>` does not automatically turn a blocking computation into a non-blocking one.** An API returning a reactive type that still calls `Thread.sleep`, `Future.get`, `RestTemplate`, synchronous JDBC, or `block()` in the wrong context can still stall the processing thread.

This lesson accurately explains:
1. How the event loop processes events and why each callback must stay short.
2. Conceptually how many thread groups Reactor Netty uses, without confusing one request with one thread.
3. How `Mono`/`Flux`, subscriptions, operators, and `Scheduler` relate to threads.
4. Distinguishing `publishOn`, `subscribeOn`, and rules for isolating blocking code.
5. Why `.block()`, `Thread.sleep`, blocking JDBC/HTTP/file I/O, and CPU-heavy work cause harm to varying degrees.
6. How to use `Schedulers.boundedElastic()` or a **dedicated bounded scheduler** for legacy libraries.
7. How to use WebClient/R2DBC for end-to-end non-blocking I/O.
8. Timeouts, cancellation, overload, backpressure, context propagation, monitoring, and testing.

The runnable example uses Java 17, Spring Boot **3.3.5**, Spring WebFlux, and Reactor Netty. Some implementation details (event-loop thread count, thread names, scheduler defaults) vary by CPU, container, Reactor release, and configuration: **do not hardcode them as API guarantees**.

## 2. Three Terms to Understand Before Reading Code

### 2.1. Concurrency vs. Parallelism

**Concurrency** is managing the progress of multiple overlapping tasks over time, potentially using just a single CPU/thread if tasks spend much of their time waiting on I/O.

**Parallelism** is executing multiple tasks **physically at the same time** across multiple CPU cores.

An event loop on a single thread can serve thousands of connections via event-driven operation, yet it cannot physically execute two pieces of CPU code simultaneously on that same thread.

Examples:
- 1,000 HTTP connections waiting on network responses do not imply needing 1,000 threads.
- 1,000 heavy CPU computations will not run faster merely because they are returned as a `Flux`.
- A blocking JDBC query still occupies a thread while waiting for the query if using a traditional JDBC driver.

### 2.2. Blocking vs. Non-Blocking I/O

**Blocking I/O** typically forces the calling thread to wait until data arrives or a timeout expires, for example:

~~~java
String body = legacyHttpClient.executeSynchronousRequest();
~~~

This is a hypothetical fragment with a `legacyHttpClient` variable, not a specific Java SDK class. When the network is slow, the calling thread stays occupied even though the CPU is mostly idle.

**Non-blocking I/O** registers interest in read/write or completion events. The thread can return to handle other work; when the socket is ready, the event loop receives a notification and continues the pipeline:

~~~java
Mono<String> body =
        webClient.get()
                .uri("/resource")
                .retrieve()
                .bodyToMono(String.class);
~~~

This is also a fragment; `webClient` must be configured with `WebClient` and a reactive connector. This snippet **does not send the request immediately when building the pipeline**; normally the HTTP exchange starts upon subscription. Do not call `body.block()` in a WebFlux handler to turn the code back into synchronous execution.

### 2.3. "Non-Blocking" Does Not Mean "Zero Time"

Non-blocking does not shrink a 300 ms network round-trip to 3 ms. It keeps threads from being held during waiting periods, so a small number of threads can serve many I/O-bound requests. Total request latency still includes network time, downstream server processing, data decoding, retries, and queueing.

## 3. How Does an Event Loop Work?

An event loop continuously waits for and processes events such as readable/writable sockets, accepted connections, scheduled timers, or task callbacks. Conceptually:

~~~text
while (serverIsRunning) {
    events = waitForReadyEvents();
    for (event : events) {
        handleSmallNonBlockingStep(event);
    }
}
~~~

This is **pseudocode**, not Netty's actual source code. The decisive point: `handleSmallNonBlockingStep` must be fast and avoid waiting on data or holding long locks. When work is not ready, register a callback/continuation and yield control back to the event loop to handle other events.

### 3.1. Diagram of Two Requests

~~~text
                     One event-loop thread
                           |
time -->  [read A] [read B] [schedule I/O A]
                           |
          [handle B] [write B] [read C]
                           |
             ...network response A arrives...
                           |
          [resume A] [serialize A] [write A]
~~~

This is a logical model, not a claim that the server has only a single loop. Reactor Netty typically manages a group of worker event loops; a connection can be bound to a given loop, and one loop serves many connections.

When A must wait on another service, the event loop should not sit idle on A; it moves on to B/C. If A runs `Thread.sleep(1000)` right on the loop, B/C on that same loop can be significantly delayed.

### 3.2. What the Event Loop Actually Does

- Accepts/reads/writes socket data and coordinates the Netty channel pipeline.
- Triggers downstream reactive callbacks/operators.
- Executes user code invoked by the framework **if no scheduler switch has occurred**.
- Handles timers/scheduled tasks and lifecycle callbacks.
- Coordinates backpressure and write readiness per implementation.

An event loop is **not** a dedicated thread per HTTP request. Nor is there a guarantee that one request stays on the same thread from start to finish if the pipeline uses `publishOn`, `subscribeOn`, async libraries, or other schedulers.

### 3.3. Reactor Netty and Client/Server Loops

In a Boot WebFlux application running Reactor Netty, you often see thread names prefixed like:

~~~text
reactor-http-nio-1
reactor-http-nio-2
...
~~~

These are **common example thread names**, not fixed constants, an API contract, or a basis for production authorization. Reactor Netty `WebClient` and HTTP server **can share event-loop resources by default** when both use Reactor Netty.

Consequence: a server handler that accidentally blocks the event loop can simultaneously delay I/O progress for outbound WebClient requests sharing those resources. In production you can configure separate `LoopResources`, connection pools, or client/server resources, yet **increasing loop count is not a cure for blocking code**.

Never claim "Netty always has exactly 4 threads" or "each core has 2 event loops": documentation, CPU counts, cgroup/container limits, and configuration alter defaults.

## 4. Threading Models: Spring MVC vs. Spring WebFlux

| Characteristic | Synchronous Servlet Spring MVC | Spring WebFlux on Reactor Netty |
| --- | --- | --- |
| Thread per request | Typically one servlet worker is held while the controller blocks | Small number of event-loop threads serving many connections |
| Default design assumption | Blocking APIs are acceptable within container thread pool limits | User code on the event loop must be non-blocking |
| Slow I/O handling | Thread normally waits | Registers completion and resumes when socket is ready |
| Return types | DTO/ResponseEntity or async types | `Mono<T>`, `Flux<T>`, publishers/adapters |
| Calling blocking JDBC | Typically directly on the worker pool | Never call on event loop; must isolate or change stack |
| Non-blocking HTTP client | Can use `WebClient` | `WebClient` is the natural choice |
| When overloaded | Queue/worker saturation | Event-loop starvation, scheduler/connection pool saturation |
| Best suited for | CRUD, JDBC, and broad blocking ecosystems | High concurrency I/O, end-to-end reactive stacks |

**Do not turn comparisons into a slogan like “WebFlux is always faster than MVC”.** Spring Framework explains the primary benefit of the reactive stack as **scalability/predictable resource usage** under I/O-waiting workloads, not lower latency for every operation. For applications relying mainly on JDBC and blocking libraries, MVC can be simpler and perform very well.

### 4.1. Spring WebFlux Does Not Run Only on Netty

Spring WebFlux can run on Reactor Netty or via adapters on non-blocking Servlet containers like Tomcat/Jetty. Thread names and scheduling details differ in those cases. This lesson uses Reactor Netty to explain a concrete event loop; **do not generalize** that all WebFlux deployments have the exact same thread count as Netty.

### 4.2. Does Boot Choose MVC or WebFlux When Both Starters Exist?

Spring Boot normally prefers the **Spring MVC application type** when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, unless the application type is explicitly configured. To run the WebFlux/Netty demo below properly, add only `spring-boot-starter-webflux` and **do not add `spring-boot-starter-web`**. An MVC application can still use reactive `WebClient` without switching its server to WebFlux.

## 5. Reactive Streams, `Mono`, `Flux`, and Subscription

Reactor provides:
- `Mono<T>`: publisher emitting **0 or 1** item, or terminating with an error.
- `Flux<T>`: publisher emitting **0 to N** items, or terminating with an error.

Both represent a **pipeline**: a chain of operators, signals, and side effects executed when subscribed and as data appears.

~~~java
Mono<String> pipeline = Mono.just("spring")
        .map(String::toUpperCase);
~~~

Here `"spring"` is created upfront; the `map` operator normally runs when subscribed. Merely creating the `pipeline` variable **does not mean an HTTP response was sent or a network request ran**.

### 5.1. Signals

A reactive stream has signals such as:
- `onSubscribe`: establishes the subscription.
- `onNext`: an item is emitted.
- `onComplete`: normal completion.
- `onError`: terminates with error.
- `request(n)`: subscriber requests item count, forming the backpressure mechanism.
- `cancel()`: subscriber cancels the subscription.

Backpressure describes consumption demand, **but does not guarantee every external producer can slow down indefinitely**. If upstream cannot slow down, the system needs bounded buffering, dropping, rejection, or ingress control. Reactive types do not make memory infinite.

### 5.2. Avoid Calling `subscribe()` Inside a Controller Just to "Kick Things Off"

Wrong example:

~~~java
@GetMapping("/bad-start")
public Mono<String> badStart() {
    remoteCall().subscribe();       // side effect detached from HTTP lifecycle
    return Mono.just("accepted");
}
~~~

`remoteCall()` is just an undefined fragment. By subscribing manually, you create an independent task that is hard to tie to request cancellation, errors, retries, tracing, and the HTTP response. If the goal is to return the result within the same request, **return the publisher** so WebFlux manages the subscription:

~~~java
@GetMapping("/good")
public Mono<String> good() {
    return remoteCall();
}
~~~

If the goal is genuinely a background job, design a job queue and `202 Accepted` with a job ID/status endpoint; do not merely call `subscribe()` and hope the background operation is durable.

## 6. Why Do Blocking Calls Harm the Entire System?

### 6.1. Event-Loop Starvation

Suppose each event-loop worker has many connections waiting on callbacks. One handler runs:

~~~java
Thread.sleep(1_000);
~~~

On the event loop, that thread cannot process read/write events or other callbacks during the sleep. If many requests make this same mistake, event loops get occupied one after another. In metrics/logs, CPU usage might not be high while p99 latency and timeouts spike; this is a symptom of **blocking waits**, not CPU shortage.

A cascade of failures can follow:
1. HTTP server receives requests.
2. Handler blocks the event loop.
3. Other sockets are not served in time.
4. Clients/gateways time out and auto-retry, sending even more requests.
5. Queues and open connection counts grow.
6. Retries continue worsening the situation even after downstream recovers.

This is a **failure pattern**, not a law that every `Thread.sleep` causes an outage; it depends on concurrency, loop count, blocking duration, retry policies, and load.

### 6.2. Common Blocking APIs

| API/Operation | Can Block? | How to Handle |
| --- | --- | --- |
| `Thread.sleep` | Yes | Never use on request event loops |
| `Mono.block()`, `Flux.blockLast()` | Yes | Never use inside a WebFlux reactive chain |
| `Future.get()`, `CompletableFuture.join()` | Yes if incomplete | Compose futures/publishers without blocking threads |
| `RestTemplate`, sync HTTP clients | Yes | Use non-blocking `WebClient` or isolate on `boundedElastic` |
| JDBC `DataSource`/`JdbcTemplate`/JPA | Yes | Use R2DBC or offload to a bounded pool |
| Synchronous File I/O | Can block | Streaming/async file APIs when appropriate or offload |
| `InputStream.read()` | Can block | Do not read long blocking streams on the event loop |
| `synchronized`/lock contention | Can block | Minimize locks/critical sections, avoid long holds |
| Large BCrypt/crypto/hashing/compression | CPU-heavy | Keep callbacks short, budget CPU explicitly; do not abuse event loops |
| Very large JSON serialization | CPU/memory heavy | Limit payloads, use streaming/codec strategies |
| `System.out.println` or excessive sync logging | Can block | Structured async logging, metrics, and sampling |
| `WebClient.retrieve().bodyToMono(...)` | Non-blocking with matching connector | Return/compose publisher, do not add `block()` |
| Reactive R2DBC driver | Non-blocking by design | Pick the right stack/driver, verify actual behavior |

**Distinguish I/O-blocking from CPU-bound:** Moving heavy CPU computation to `boundedElastic` can reduce direct impact on the event loop without making the CPU work cheaper; it can overload the scheduler and increase context switches. For CPU workloads, use `Schedulers.parallel()` or a measured/bounded compute worker pool depending on task length/nature. Reactor `parallel()` is not magic that increases throughput for tasks exceeding CPU cores.

### 6.3. `.block()` Can Fail Fast or Silently Slow Things Down

Project Reactor recognizes certain threads marked **NonBlocking**. Calling `block()`/`blockFirst()`/`blockLast()` on these threads can throw `IllegalStateException`, with a message such as:

~~~text
block()/blockFirst()/blockLast() are blocking, which is not supported in thread ...
~~~

Do not rely on the exact message text across versions. When running on a thread not marked NonBlocking, `block()` **may not throw** yet still occupies the thread and causes slowdowns. Thus “no IllegalStateException” **does not prove a pipeline is non-blocking**.

Inside a Spring WebFlux handler, never “fix” this by adding an exception handler for `IllegalStateException` and continuing to call `block()`. Fix the root cause: compose publishers properly or isolate legacy blocking calls on an appropriate worker.

## 7. Critical Counterexample: `Mono.just(blockingCall())` Still Blocks

Suppose `legacyService.find(id)` is a synchronous JDBC/HTTP call.

**Wrong:**

~~~java
@GetMapping("/bad/{id}")
public Mono<Product> bad(@PathVariable long id) {
    return Mono.just(legacyService.find(id));
}
~~~

`legacyService.find(id)` is invoked **before** `Mono.just(...)` executes, potentially right on the event-loop thread calling the controller. Even though the return type is Mono, blocking has already happened.

**Also wrong if you merely append `subscribeOn` afterward:**

~~~java
Mono.just(legacyService.find(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`legacyService.find(id)` still executes eagerly when the expression is evaluated; `subscribeOn` cannot turn back time to fix a call that already ran.

**Correct when forced to use a blocking library:**

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> legacyService.find(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` defers executing the lambda until subscription; `subscribeOn` schedules subscription/source execution on a bounded elastic worker. Thus the blocking call occupies an **appropriate worker**, not the event loop.

The snippets above are fragments with undefined `Product` and `legacyService`; the complete app is in section 12. Offloading does not eliminate the threads needed for blocking work; it merely **isolates** blocking work from I/O loops so the server does not choke prematurely.

### 7.1. `Mono.defer` and `Mono.fromCallable`

`Mono.defer(() -> legacyWrapper())` defers **building the publisher** per subscription. `Mono.fromCallable(() -> legacyService.find(id))` suits **a synchronous computation returning one result**, which may throw checked exceptions that become `onError`.

Using `defer` without scheduling can still run blocking code on the subscribing thread (which may be the event loop). To isolate it, you still need `subscribeOn(Schedulers.boundedElastic())` or an equivalent scheduler.

### 7.2. What If the Callable Returns `null`?

`Mono.fromCallable` completes **empty** when the callable returns null. Do not confuse that with JSON null or an automatic HTTP 404. If a resource is not found, throw a typed/domain exception or use `switchIfEmpty(Mono.error(...))` with an explicit fallback. The demo app throws `ProductNotFoundException` so the controller/advice turns it into 404.

## 8. Schedulers: Not Every Operator Spawns a Thread

Reactor `Scheduler` manages where scheduled work runs. Many operators like `map`, `filter`, `flatMap`, and `doOnNext` **do not automatically open a new thread**. They usually execute on whichever thread emitted the signal at that moment, unless there is an asynchronous boundary/scheduler switch.

### 8.1. Common Schedulers

| Scheduler | Primary Design | What to Avoid |
| --- | --- | --- |
| `Schedulers.immediate()` | Executes on the current thread | Do not use to offload blocking work |
| `Schedulers.single()` | One shared worker | One blocking task delays all others |
| `Schedulers.parallel()` | Fixed thread pool for short CPU-bound tasks | Never send JDBC/sleep to this pool |
| `Schedulers.boundedElastic()` | Bounded worker capacity for legacy blocking I/O | Do not treat as infinite; still has queues/rejections |
| `Schedulers.newBoundedElastic(...)` | Creates a dedicated bounded pool, easy dependency isolation | Must set sensible bounds and dispose on shutdown |
| Reactor Netty event-loop threads | Network I/O and callbacks | Never run blocking code or long computations |

The default `boundedElastic` in Reactor 3.6.x has thread/queue bounds, yet **do not copy a default number from another version as a contract**; system properties and environments customize it. Some Reactor releases/JDKs support a virtual-thread strategy for bounded elastic when configured. Java 17 in this demo uses traditional platform threads; **do not assume virtual threads are enabled**.

### 8.2. `subscribeOn`: Orchestrating Subscription/Source

~~~java
Mono<String> p = Mono.fromCallable(() -> {
            // Blocking operation needing its own worker.
            return legacyRead();
        })
        .subscribeOn(Schedulers.boundedElastic())
        .map(String::toUpperCase);
~~~

`legacyRead()` is an undefined hypothetical function. `subscribeOn` affects the upstream subscription/source execution. It is commonly placed **right after `fromCallable`** to make intent clear. That does not mean it self-subscribes; the publisher only runs when a client/WebFlux subscribes.

A pipeline can contain multiple `subscribeOn` calls, though stacking them is not an intuitive way to “bounce threads back and forth”: a `subscribeOn` closer to the source typically determines source scheduling depending on structure/operators. Avoid overlapping calls unnecessarily.

### 8.3. `publishOn`: Switching Threads for Subsequent Steps

~~~java
Mono<String> p = Mono.just("a")
        .publishOn(Schedulers.parallel())
        .map(value -> value.toUpperCase());
~~~

`publishOn` uses the scheduler for downstream stages after the operator until another scheduler boundary appears. It is suited for shifting a portion of the pipeline onto a compute worker.

**Be careful with blocking sources:**

~~~java
Mono.fromCallable(() -> legacyRead())
    .publishOn(Schedulers.boundedElastic())
    .map(String::toUpperCase);
~~~

Without other upstream scheduling, `fromCallable` can **still execute on the subscribing thread** before `publishOn` switches signals downstream. Hence the standard pattern for offloading a blocking source is **`Mono.fromCallable(...).subscribeOn(boundedElastic)`**.

### 8.4. Thread Switching Has a Cost, Not a Badge of Honor

Every scheduler boundary incurs queueing, context switching, context propagation, and latency overhead. Do not add `publishOn(Schedulers.parallel())` between every operator “to be safe”. Identify which step is genuinely blocking/CPU-heavy, place one intentional boundary, benchmark performance, and monitor queues.

## 9. Why Is `boundedElastic` Bounded, and Why Is That Good?

A bounded scheduler helps isolate calls that cannot be migrated to reactive immediately, yet those calls still consume workers:
- If a dependency normally responds in 50 ms, a few workers can serve many requests over time.
- If a dependency hangs for 30 seconds, workers stay blocked for a long time, and subsequent requests may queue up.
- When queues/pools hit their cap, scheduling can be rejected (e.g., Reactor `RejectedExecutionException`) instead of spawning infinite threads.

**Limits are a resource-protection mechanism**, not a design flaw. Under overload, return an appropriate status (often 503 per application policy), apply admission control, circuit breakers, rate limits, and retries with bounded backoff/jitter.

### 9.1. Dedicated Bounded Scheduler

Instead of all legacy libraries sharing global `boundedElastic`, an application can create a dedicated scheduler:

~~~java
@Bean(name = "legacyScheduler", destroyMethod = "dispose")
Scheduler legacyScheduler() {
    return Schedulers.newBoundedElastic(4, 32, "legacy-io");
}
~~~

This fragment belongs to a `@Configuration` class, with imports shown in the runnable example below. Meaning:
- At most 4 workers (per this helper setup).
- Queue bound is 32 **per backing thread** per Reactor's factory semantics; do not mistake this for 32 total requests app-wide.
- Thread name prefix `legacy-io` aids diagnostics; specific names are not a security or business contract.
- When the Spring context shuts down, `dispose` is called to clean up scheduler resources.

The numbers `4` and `32` are **for demo only**, not a production recommendation. In practice, size based on connection pools, service latency, concurrency, CPU, memory, expected load, and upstream timeouts.

### 9.2. Do Not Accidentally Exceed the Connection Pool

If a scheduler permits 100 blocking operations while the JDBC connection pool has only 10 connections, many workers will **sit waiting for connections** and fill the queue. Tune threads, connections, and request admission together. With R2DBC, connection pool limits and max in-flight operations still matter — non-blocking does not mean unlimited concurrency.

## 10. WebClient: Leverage Non-Blocking HTTP Instead of Offloading Every Call

If downstream supports HTTP, `WebClient` can perform reactive requests without blocking a worker:

~~~java
public Mono<Product> fetch(long id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

This is a fragment of a class with a preconfigured `WebClient webClient` and `Product` record/class; it is **not a complete project** as it provides no downstream server. With the Reactor Netty connector, HTTP I/O is handled non-blockingly, and the publisher is subscribed by WebFlux when the controller returns it.

**Do not do this:**

~~~java
Product product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .block();
~~~

`block()` makes the call synchronous, can throw on non-blocking threads, or causes starvation. When the caller is WebFlux, return `Mono<Product>` or compose via `flatMap`/`zipWhen`.

### 10.1. Running Multiple Independent HTTP I/O Requests

If two remote responses are needed:

~~~java
Mono<Product> a = productClient.fetch(1);
Mono<Product> b = productClient.fetch(2);

return Mono.zip(a, b)
        .map(tuple -> new ProductPair(tuple.getT1(), tuple.getT2()));
~~~

This is a fragment; `ProductPair` and `productClient` need separate declarations. Both publishers can have I/O in flight concurrently; there is no need to call `block()` to wait sequentially. However, `zip` completes empty if one source is empty per Reactor semantics; to handle missing cases, use `switchIfEmpty`/domain exceptions on each source before zipping.

### 10.2. Timeout Does Not Automatically Stop Every Legacy Task

`timeout(Duration.ofSeconds(2))` emits an error signal and cancels upstream when time expires. With non-blocking WebClient, cancellation can abort the request/free resources per connector behavior. With `fromCallable` executing blocking code that ignores interruption, timeout **does not guarantee** the task/SQL/network call stops immediately. Hence driver-level, HTTP client, and database timeouts remain essential.

### 10.3. Reactive Data Access: R2DBC vs. JDBC

R2DBC is designed for reactive database access; JDBC/JPA are traditionally synchronous APIs on the caller thread. If an entire system relies mostly on JDBC, you can:
- Keep synchronous Spring MVC, as it is a fitting architecture.
- Under mandatory WebFlux, offload blocking JDBC via bounded workers and enforce concurrency/connection limits.
- When required and driver-supported, consider migrating data access to R2DBC via a planned migration.

Do not attach imperative/JPA `@Transactional` and assume the transaction context automatically moves across every Scheduler: imperative transactions are typically thread-bound; reactive transactions use `Reactor Context` and `ReactiveTransactionManager` matching the stack.

## 11. Distinguishing `Thread.sleep`, Blocking I/O, and CPU-Heavy Work

### 11.1. Blocking Wait

~~~java
Thread.sleep(2_000);
~~~

Consumes very little CPU yet holds the thread. Putting it on the event loop is especially bad: the loop cannot return to serve sockets/callbacks. Putting it on a bounded worker still ties up a worker, causing queueing when many requests wait simultaneously.

If the goal is simply to **wait for a duration** in a pipeline, use a non-blocking timer:

~~~java
Mono<String> delayed = Mono.delay(Duration.ofSeconds(2))
        .map(ignored -> "done");
~~~

`Mono.delay` does not call `Thread.sleep` on the event loop; it uses the corresponding scheduler/timer. Still, this only simulates a delay and **does not replace** a real network/DB request with side effects.

### 11.2. CPU-Bound Work

~~~java
long value = expensiveHash(payload);
~~~

This is a fragment with two undeclared variables. Even without making any I/O calls, if `expensiveHash` takes 500 ms on the event loop, it still keeps the loop busy and delays socket processing. You can offload to a compute pool or send heavy work to a job queue; ensure hundreds of large operations do not contend for CPU. Use the right scheduler for the workload: `parallel`/dedicated bounded compute workers usually differ from `boundedElastic` aimed at blocking I/O.

### 11.3. Synchronous Locks

A callback acquiring a monitor/lock held long by other threads is also blocking. A very brief synchronized block is not automatically a bug, yet lock contention under high load and blocking calls inside locks can cause severe tail latency. Prefer immutable data, concurrent structures, and minimal critical sections; do not blindly move locks into Reactor context without proper thread-safety design.

### 11.4. Logging Can Also Block

Excessive debug logging, heavy formatters, synchronous file/network appenders, or stdout printing in large loops can slow down the event loop. In production, use structured logs, appropriately bounded asynchronous appenders, sampling, redaction, and metrics. Avoid logging raw Authorization/cookies/session IDs or private data just to trace threads.

## 12. Complete Application: Java 17 + Spring Boot 3.3.5 + Isolated Scheduler

The example provides:
- `GET /api/health`: returns a fast, non-blocking `Mono`.
- `GET /api/products/{id}`: simulates a legacy blocking library via `Thread.sleep(30)` in the service. The controller uses `Mono.fromCallable(...).subscribeOn(legacyScheduler)` to avoid blocking the Reactor Netty loop.
- If the product is missing: a typed exception is converted to 404 by `@RestControllerAdvice`.
- If timed out: `TimeoutException` is converted to 503 by advice.
- HTTP integration tests use `WebTestClient` with embedded Reactor Netty, verifying both success and 404.
- Scheduler test verifies work runs on a worker with a prefix distinct from the event loop.

`Thread.sleep(30)` is **only to simulate blocking code in the demo**; never put sleep in production and do not assume offloading solves all load problems.

~~~text
webflux-eventloop-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/loopdemo/
    │   ├── LoopDemoApplication.java
    │   ├── config/SchedulerConfig.java
    │   ├── domain/Product.java
    │   ├── domain/ProductNotFoundException.java
    │   ├── domain/LegacyProductGateway.java
    │   └── web/
    │       ├── ProductController.java
    │       └── ApiErrorHandler.java
    └── test/java/com/example/loopdemo/
        └── ProductControllerIntegrationTest.java
~~~

### 12.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-eventloop-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Do not add `spring-boot-starter-web`**. `starter-webflux` provides Reactor/Spring WebFlux/Reactor Netty, `starter-test` provides JUnit and Spring Boot testing, and `reactor-test` provides StepVerifier. The Boot BOM manages consistent Reactor versions. For real builds, use a Gradle wrapper compatible with Boot 3.3/Java 17.

### 12.2. Main Application

`src/main/java/com/example/loopdemo/LoopDemoApplication.java`:

~~~java
package com.example.loopdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoopDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoopDemoApplication.class, args);
    }
}
~~~

### 12.3. Dedicated Bounded Scheduler for Legacy Blocking

`src/main/java/com/example/loopdemo/config/SchedulerConfig.java`:

~~~java
package com.example.loopdemo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfig {

    @Bean(name = "legacyScheduler", destroyMethod = "dispose")
    public Scheduler legacyScheduler() {
        return Schedulers.newBoundedElastic(4, 32, "legacy-io");
    }
}
~~~

Spring manages the scheduler bean and invokes `dispose` on shutdown. Defining a dedicated scheduler clarifies boundaries and makes isolating legacy libraries easy to measure. Worker and queue numbers are illustrative; applications can use shared `Schedulers.boundedElastic()` if isolation is not required.

### 12.4. Domain Types

`src/main/java/com/example/loopdemo/domain/Product.java`:

~~~java
package com.example.loopdemo.domain;

public record Product(long id, String title) {}
~~~

`src/main/java/com/example/loopdemo/domain/ProductNotFoundException.java`:

~~~java
package com.example.loopdemo.domain;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product not found: " + id);
    }
}
~~~

### 12.5. Simulating a Legacy Blocking Library

`src/main/java/com/example/loopdemo/domain/LegacyProductGateway.java`:

~~~java
package com.example.loopdemo.domain;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class LegacyProductGateway {

    private final Map<Long, Product> products = Map.of(
            1L, new Product(1L, "Project Reactor"),
            2L, new Product(2L, "Spring WebFlux"));

    public Product find(long id) throws InterruptedException {
        // Demo: stands in for a synchronous JDBC/HTTP client call.
        Thread.sleep(30L);

        Product product = products.get(id);
        if (product == null) {
            throw new ProductNotFoundException(id);
        }
        return product;
    }
}
~~~

`find` is **blocking** due to sleep. Calling it straight from the Netty event loop holds the loop for at least ~30 ms plus lookup. Moving it to a dedicated scheduler only keeps it **off the Netty loop**, still consuming a worker. `Map.of` serves as a fixture; it holds no user data, depends on no external network, and yields deterministic test bodies.

### 12.6. Properly Structured WebFlux Controller

`src/main/java/com/example/loopdemo/web/ProductController.java`:

~~~java
package com.example.loopdemo.web;

import com.example.loopdemo.domain.LegacyProductGateway;
import com.example.loopdemo.domain.Product;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@RestController
@RequestMapping("/api")
public class ProductController {

    private final LegacyProductGateway legacy;
    private final Scheduler scheduler;

    public ProductController(
            LegacyProductGateway legacy,
            @Qualifier("legacyScheduler") Scheduler scheduler) {
        this.legacy = legacy;
        this.scheduler = scheduler;
    }

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }

    @GetMapping("/products/{id}")
    public Mono<Product> product(@PathVariable("id") long id) {
        return Mono.fromCallable(() -> legacy.find(id))
                .subscribeOn(scheduler)
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

**Step-by-step explanation:**
1. On a GET to `/api/products/{id}`, the controller returns **a Mono publisher** quickly without calling `legacy.find` inline.
2. `Mono.fromCallable` keeps the legacy work lazy until subscription.
3. `subscribeOn(scheduler)` picks a bounded worker for subscription/source; `Thread.sleep` runs on that worker, not the request event loop.
4. `timeout(2s)` caps how long the publisher waits; a blocking task that ignores interruption can still continue after timeout.
5. Once the worker returns `Product`, WebFlux serializes JSON as the HTTP response.
6. If `legacy.find` throws `ProductNotFoundException`, the error enters the reactive `onError` signal; WebFlux error handling selects the advice below.

No manual `subscribe()` is needed in the controller. There is no blocking in `health()`, so that route needs no dedicated scheduler. For CPU-heavy JSON serialization or complex response transforms, evaluate separately instead of putting the whole controller on `boundedElastic` by default.

### 12.7. API Error Handling

`src/main/java/com/example/loopdemo/web/ApiErrorHandler.java`:

~~~java
package com.example.loopdemo.web;

import com.example.loopdemo.domain.ProductNotFoundException;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> missing(
            ProductNotFoundException exception) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Product not found");
        problem.setDetail("No product has that id.");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(TimeoutException.class)
    public ResponseEntity<ProblemDetail> timeout(
            TimeoutException exception) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Product service timed out");
        problem.setDetail("The product could not be fetched in time.");
        problem.setProperty("code", "PRODUCT_TIMEOUT");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
~~~

`ProblemDetail` follows RFC 9457 semantics; Spring WebFlux + Jackson can serialize the `code` extension field. The advice does not return raw exception messages; that is a safe choice since real exceptions can leak SQL, internal URLs, or secrets.

**Limitations:** The demo maps only two error types; executor rejections, malformed path IDs, client disconnects, unexpected runtime errors, and HTTP gateway timeouts must be handled/tested per production policy. Never collapse all `Throwable` types into 200/503 and mask internal bugs. HTTP 504 only fits when the component acts semantically as a gateway/proxy; the demo application route intentionally chooses 503 on dependency timeout.

## 13. WebTestClient and StepVerifier: Testing the Real WebFlux Stack

In a WebFlux application, `WebTestClient` is the natural way to test reactive HTTP. The demo uses an embedded server on a random port to exercise network/Netty as well; it is not MockMvc for Servlet MVC.

`src/test/java/com/example/loopdemo/ProductControllerIntegrationTest.java`:

~~~java
package com.example.loopdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductControllerIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    @Qualifier("legacyScheduler")
    Scheduler scheduler;

    @Test
    void healthIsReactiveAndAvailable() {
        client.get().uri("/api/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void legacyProductStillReturnsJson() {
        client.get().uri("/api/products/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Project Reactor");
    }

    @Test
    void missingProductBecomes404ProblemDetail() {
        client.get().uri("/api/products/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
                .jsonPath("$.status").isEqualTo(404);
    }

    @Test
    void dedicatedSchedulerActuallyOffloadsItsSource() {
        Mono<String> workThread =
                Mono.fromCallable(() ->
                        Thread.currentThread().getName())
                    .subscribeOn(scheduler);

        StepVerifier.create(workThread)
                .expectNextMatches(name -> name.startsWith("legacy-io-"))
                .verifyComplete();
    }
}
~~~

**Distinguishing what the tests prove:**
- Three `WebTestClient` tests send HTTP requests to the application and verify status/body.
- The StepVerifier test proves **a Mono source with `subscribeOn` using the dedicated scheduler** runs on a worker with our configured prefix. It does not measure request concurrency under load, yet verifies the scheduler works.
- The demo intentionally avoids asserting Reactor Netty event-loop thread names because naming can change across runtimes.
- Tests do not rely on exact 30 ms timing since `Thread.sleep`/CI schedulers can jitter; response tests await the body instead of assuming fixed timing.
- Never claim four tests alone prove the system handles 10,000 concurrent requests. Load testing and scheduler/Netty metrics are needed for production.

Run in a project with Gradle wrapper and Java 17:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Do not run `bootRun` in the same terminal before `test` finishes. Against the running server, call:

~~~bash
curl -i 'http://localhost:8080/api/health'
curl -i 'http://localhost:8080/api/products/1'
curl -i 'http://localhost:8080/api/products/999'
~~~

Key outputs:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"title":"Project Reactor"}
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Product not found","status":404,"detail":"No product has that id.","code":"PRODUCT_NOT_FOUND"}
~~~

Additional headers, header order, JSON field order, and `instance` may differ by serializer/framework, yet status/essential fields should match. All three calls are independent HTTP requests; a single request does not automatically switch threads based on header count.

## 14. Anti-Patterns Directly Compared with Correct Examples

### 14.1. Wrong: Creating Mono After Blocking Has Already Executed

~~~java
return Mono.just(legacy.find(id));
~~~

The blocking call already ran before the Mono was constructed. Fix:

~~~java
return Mono.fromCallable(() -> legacy.find(id))
        .subscribeOn(legacyScheduler);
~~~

### 14.2. Wrong: Calling `block()` on WebClient Inside a Handler

~~~java
return Mono.just(
        webClient.get().uri("/x").retrieve()
                .bodyToMono(String.class).block());
~~~

If the API can be completely non-blocking:

~~~java
return webClient.get().uri("/x")
        .retrieve().bodyToMono(String.class);
~~~

### 14.3. Wrong: Placing `publishOn` in the Wrong Spot

~~~java
return Mono.fromCallable(() -> legacy.find(id))
        .publishOn(legacyScheduler);
~~~

The source can still run right on the subscriber/event-loop thread. Fix by placing `subscribeOn` immediately after the source, as in the runnable code.

### 14.4. Wrong: `flatMap` with a Slow Synchronous Lambda

~~~java
return ids.flatMap(id -> {
    Product p = legacy.find(id);  // runs synchronously inside lambda
    return Mono.just(p);
});
~~~

Here `ids` is a Flux/Publisher fragment. Even though the operator is named `flatMap`, the lambda blocks immediately when upstream emits. Fix:

~~~java
return ids.flatMap(
        id -> Mono.fromCallable(() -> legacy.find(id))
                .subscribeOn(legacyScheduler),
        8);
~~~

`8` caps concurrency at the `flatMap` layer in the example. When ordering is required, consider `flatMapSequential` or `concatMap` with their trade-offs. **Never let in-flight requests exceed database/legacy client capacity**; concurrency limits and scheduler queues must align.

### 14.5. Wrong: Using `doOnNext` for Blocking Side Effects

~~~java
return products.doOnNext(product ->
        legacyAuditRepository.save(product));
~~~

The `doOnNext` callback runs synchronously on the signal-emitting thread without offloading. If auditing must participate in the result:

~~~java
return products.concatMap(product ->
        Mono.fromCallable(() -> {
            legacyAuditRepository.save(product);
            return product;
        }).subscribeOn(legacyScheduler));
~~~

`products` and `legacyAuditRepository` are undeclared fragments. If auditing is a durable event separate from the HTTP response, use an outbox/queue with dedicated reliability design. Do not just call `subscribe()` inside `doOnNext` since retry/error ownership will be lost.

## 15. Backpressure and Overload Are Not Scheduling

### 15.1. `request(n)` Does Not Bound Every External Source

Reactive Streams allows a Subscriber to request a maximum number of items at a time. With a cold Flux emitting from a framework-controlled source, upstream can honor demand.

However, HTTP client connections, file watchers, Kafka brokers, GUI/events, or external services cannot always stop immediately when downstream lowers demand. If event rate exceeds processing speed, you need bounded buffers, concurrency limits, proper backpressure strategies, dropping/error policies, or admission control. Do not put an unbounded buffer in the pipeline to “keep all data”.

### 15.2. `flatMap` Has Concurrency and Prefetch

A pipeline:

~~~java
Flux.fromIterable(ids)
    .flatMap(id -> productClient.fetch(id), 8);
~~~

limits the number of inner publishers subscribed concurrently via the concurrency parameter. `ids` and `productClient` are fragments. This differs from `Schedulers.boundedElastic`: `flatMap` bounds **in-flight work count**, whereas the scheduler bounds **execution resources**. With legacy DBs, both may be needed.

### 15.3. Reactive Does Not Eliminate Connection Pools

Non-blocking WebClient still needs connection pools, DNS/TLS resources, limits, read/write timeouts, and memory budgets. R2DBC still has pools/concurrent transactions. If a downstream service allows only 20 concurrent calls, the application must enforce that limit even though the event loop can manage thousands of sockets.

### 15.4. Unbounded Retries Cause Snowballs

Never write unbounded `retry()` on an endpoint that is already slow due to saturation. Retries with exponential backoff/jitter, deadlines, idempotency, and circuit breakers should apply only to well-defined transient failures. Never blindly retry an HTTP POST with side effects. A good threading model cannot save a retry storm caused by bad architecture.

## 16. Timeouts and Cancellation in Reactive Pipelines

### 16.1. `timeout` Is a Publisher Deadline, Not Global Cleanup

~~~java
return legacyPublisher
        .timeout(Duration.ofSeconds(2));
~~~

When time expires, `timeout` can emit `TimeoutException` and cancel upstream. Yet if the source is blocked inside a native/JDBC driver that does not respond to interruption, the thread can still remain occupied. Driver-side timeouts, database statement timeouts, HTTP response timeouts, and per-layer cleanup are required.

### 16.2. Request Cancellation Does Not Mean Transaction Undo

A client closing a tab or cancelling a subscription can signal that the HTTP exchange no longer needs a response. However:
- A business side effect already committed in the DB does not automatically roll back because the subscriber cancelled.
- An already-running blocking call may continue until the driver returns or times out.
- Retries/cancellations can create an “uncertain whether the operation succeeded” state.
- For commands/transactions, you need idempotency keys, transaction boundaries, and auditing rather than relying solely on Reactor cancellation.

### 16.3. Error-Handling Operators

~~~java
return productClient.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                ex -> Mono.error(
                        new UpstreamUnavailableException()));
~~~

The fragment uses a custom `UpstreamUnavailableException`. `onErrorResume` determines fallback/error mapping in the reactive chain, while the actual HTTP 503/504/500 response depends on the global WebFlux exception handler, `@RestControllerAdvice`, or custom error mapping. Never catch all errors and return a default "empty product", as that can mask corrupt data and security errors.

## 17. WebFlux Threading, SecurityContext, and Reactor Context

### 17.1. ThreadLocal Is Unsafe as Logical Request Identity

In synchronous Servlet MVC, much code relies on `ThreadLocal` or MDC to hold user/trace state on the request thread. In a reactive pipeline, callbacks can run on the event loop, boundedElastic, parallel scheduler, or an async source's thread. A logical request **is not permanently pinned to one Java thread**.

Anti-pattern example:

~~~java
String user = currentUserThreadLocal.get();
return asyncCall.map(result -> useForUser(user, result));
~~~

Reading the variable during pipeline assembly may or may not work depending on security integration and timing; reading `ThreadLocal` inside an asynchronous callback is even less safe to assume as holding the old context. Never use raw `ThreadLocal` to enforce authorization in reactive callbacks.

### 17.2. Reactor `Context`

Reactor provides `Context` to attach metadata per subscription, independent of worker thread identity. Standalone runnable Java fragment example:

~~~java
Mono<String> greeting =
        Mono.deferContextual(ctx ->
                Mono.just("hello " + ctx.get("tenant")))
            .contextWrite(context ->
                context.put("tenant", "demo"));

greeting.subscribe(System.out::println);
~~~

This fragment assumes Reactor `Mono` imports; stdout upon subscribe:

~~~text
hello demo
~~~

In production, the tenant must come from **verified authentication/authorization**, not an arbitrary request header. Demo context keys/strings are not Spring Security's default schema; when using reactive Spring Security, `ReactiveSecurityContextHolder` leverages Reactor Context to access security identity.

### 17.3. MDC/Tracing Propagation

SLF4J's MDC is usually ThreadLocal-based, so when `publishOn` switches threads or an I/O callback runs on another thread, MDC fields can disappear or leak across connections if mismanaged. Use integration with Micrometer Context Propagation, Reactor context-propagation hooks, or version-appropriate tracing libraries; avoid copying raw ThreadLocal values into global static fields. Always clear state when executing on pooled threads.

### 17.4. Reactive Transaction Boundaries

With R2DBC, `ReactiveTransactionManager` and `TransactionalOperator` bind transactional state via Reactor Context properly. With JDBC/JPA `PlatformTransactionManager`, transactions are normally thread-bound; switching schedulers via `subscribeOn`/`publishOn` **does not preserve** an imperative controller/service method's transaction. Offloaded blocking repository calls need proper transactional boundaries inside the Spring-proxied worker.

## 18. Data-Driven Debugging of Event-Loop Starvation

### 18.1. Notable Symptoms

- p95/p99 latency rises while CPU usage does not necessarily rise proportionally.
- Many small requests and health checks also slow down even though a specific DB route is failing.
- Reactor Netty I/O loops show stack traces stuck in `Thread.sleep`, blocking socket reads, JDBC calls, or locks.
- WebClient timeouts appear concurrently with HTTP server latency.
- Bounded scheduler active workers/queues hit limits; task scheduling rejections occur.
- Client/gateway retries increase and connections remain open longer.
- Some requests are very fast while others wait long depending on callback/event-loop distribution.

Correlate these symptoms with tracing/profiling; never draw definitive conclusions from a single metric alone.

### 18.2. Thread Dumps

A thread dump during an incident can reveal:
- `reactor-http-nio-*` threads sitting in `Thread.sleep` or JDBC calls.
- `legacy-io-*` threads waiting on DB as designed by isolation.
- Threads contending on locks or in WAITING/BLOCKED states.
- Idle Netty event loops while connection pool bottlenecks lie elsewhere.

Inspect multiple dumps over an interval rather than one snapshot; note that stack traces can contain internal paths/identifiers and must be handled per security policy.

### 18.3. Reactor `Schedulers.isInNonBlockingThread()`

Reactor provides an API to check whether the current thread is marked NonBlocking:

~~~java
boolean markedNonBlocking =
        Schedulers.isInNonBlockingThread();
~~~

A callback running on a Reactor Netty event loop typically returns true; however, this API **does not detect all business-level blocking**. Returning false only means the thread lacks the marker, not that "blocking forever is allowed". Do not use this boolean in place of latency/throughput measurements.

### 18.4. BlockHound Where Appropriate

**BlockHound** is an external tool that instruments the JVM to detect certain blocking calls on threads where blocking is disallowed. It can be integrated in testing/diagnostics when the runtime and Java version are compatible. It does not catch every form of blocking or serve as free production diagnostics; certain JDKs/releases require specific JVM flags and integration. Do not add `BlockHound.install()` directly into the Boot 3 demo above without verifying compatibility and startup behavior.

BlockHound catching `Thread.sleep` on Reactor non-blocking threads is a useful illustration, yet **it does not replace load tests, source reviews, thread dumps, or observability**.

### 18.5. Micrometer / Actuator Metrics

With proper Spring Boot Actuator/Micrometer setup, you can observe:
- HTTP server request latency/status distributions.
- Reactor Netty connection pools and event-loop behaviors when metrics are enabled.
- Scheduler active/queued/rejected tasks when instrumented.
- WebClient latency, downstream timeouts, and pending connection acquires.
- CPU usage, heap, GC, and thread states.
- Business-specific deadlines/circuit breaker states.

Exact metric names depend on Boot/Micrometer/Reactor instrumentation versions and configured binders; never invent a metric name assuming it always exists. The goal is to **correlate event-loop stalls with specific code or dependencies**, not merely build a dashboard showing total QPS.

## 19. Capacity Estimation and Architecture Selection

### 19.1. When Is WebFlux Beneficial?

WebFlux is typically worth considering when:
- There are very high concurrent I/O requests with significant remote-service wait times.
- Critical dependencies have **non-blocking drivers/clients**.
- The team understands reactive operators, backpressure, cancellation, and context propagation.
- Streams, SSE/WebSocket, or reactive composition are needed.
- You have the capability to test/monitor scheduling, queues, and event-loop health.

### 19.2. When Is Spring MVC a Good Choice?

Spring MVC remains appropriate when:
- JPA/Hibernate/JDBC and synchronous integrations dominate.
- Most business logic is straightforward CRUD with throughput well within thread-pool capacity.
- The team is experienced in imperative programming and reactive debugging costs outweigh benefits.
- The true bottleneck lies in DB/indexes/network rather than request thread count.
- You do not want to build a half-reactive pipeline that offloads almost every blocking call.

A reactive wrapper around a large blocking core does not deliver the same benefits as end-to-end non-blocking I/O.

### 19.3. Estimating Blocking Worker Counts

In steady state, Little's Law for a stable system states that **requests in the system ≈ arrival rate × time spent in the system**. For example, a blocking workload of 100 requests/second where each operation holds a worker for 0.2 seconds on average requires ~20 concurrent operations on average assuming all succeed with no abnormal queueing.

This is a capacity estimate, **not a fixed recommended thread count**; p99, bursts, pool limits, memory, and retries require headroom and load testing. Do not configure a 20-worker scheduler merely because the average computes to 20 while ignoring tail latency.

### 19.4. Reactive Pipelines Also Need Security Policies

Returning `Mono` does not replace:
- Per-resource/tenant authentication and authorization.
- CSRF when using cookie-based browser credentials.
- CORS for cross-origin requests.
- Input validation, limits, and JSON deserialization safeguards.
- Timeouts, retries, and idempotency.
- Log redaction, SSRF protection on outbound requests, and dependency allowlists.

Never read raw `SecurityContextHolder` ThreadLocal from a scheduler callback to make authorization decisions; reactive Spring Security has appropriate context APIs.

## 20. Dangerous Misconceptions and How to Fix Them

| Misconception / Symptom | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| "Returning `Mono` is non-blocking" | `Mono.just(blockingCall())` still executes eagerly | Use `fromCallable` + `subscribeOn` or switch to a non-blocking client |
| "`Thread.sleep` only affects that one request" | An event loop serves many connections | Use a non-blocking timer or offload legacy calls |
| "`publishOn` after `fromCallable` offloads the source" | The source can run before `publishOn` | Place `subscribeOn` right after the source |
| "`block()` didn't throw so it's safe" | It might simply not be on a NonBlocking-marked thread | Never block in a reactive request chain |
| "Event loop = 1 thread/HTTP request" | One loop multiplexes many connections | Understand event-driven callback scheduling |
| "WebFlux = WebClient" | `WebClient` can be used in Spring MVC | Check Spring Boot application type/starters |
| "WebFlux is always faster than MVC" | Reactive does not automatically shrink DB/network latency | Benchmark workloads, choose based on dependencies |
| "`boundedElastic` is an infinite pool" | It has worker and queue bounds | Size capacity, monitor rejections |
| "Increasing Netty worker count fixes JDBC blocking" | Loops are still held while JDBC waits | Offload/change drivers, bound concurrency |
| "`parallel()` handles JDBC well" | CPU pool has few threads; blocking causes starvation | Use `boundedElastic`/dedicated blocking scheduler |
| "`timeout` stops any SQL call" | Blocking drivers may not cancel immediately | Use statement/socket timeouts and cancellation-aware drivers |
| "`flatMap` always runs each item in a new thread" | `flatMap` is composition, not a thread spawner | Configure explicit scheduler/concurrency as needed |
| "`Flux` prevents unbounded RAM" | Backpressure depends on producers/queues | Use bounded buffers, admission, drop/error policies |
| "`subscribe()` in controller is a reliable background job" | Detached from request lifecycle; errors hard to track | Return the publisher or use a durable queue |
| "ThreadLocal always holds the same request state" | Callbacks switch threads | Use Reactor Context, reactive security/tracing |
| "SecurityContext automatically crosses every worker" | Context propagation depends on integration | Use `ReactiveSecurityContextHolder`/validated context |
| "JDBC `@Transactional` crosses `publishOn`" | Imperative transactions are typically thread-bound | Use proper transactional boundaries or R2DBC |
| "Low CPU means WebFlux isn't bottlenecked" | Blocking waits stall loops with low CPU | Inspect thread dumps and latency/queue metrics |
| "One HTTP 200 test proves concurrency" | Does not measure starvation under load | Run load tests, inspect thread dumps and scheduler metrics |

## 21. Production Starvation Remediation Workflow

1. **Measure baseline**: p95/p99, error/timeout rates, connections, Netty event loops, scheduler queues, DB/HTTP client pools.
2. **Capture stack traces** during incidents; look for `sleep`, JDBC, blocking HTTP, `Future.get`, locks, excessive serialization.
3. **Identify where code runs**: event loop, `boundedElastic`, `parallel`, dedicated executor, or custom library worker.
4. **Classify workloads**: I/O needing non-blocking; unavoidable blocking; CPU-bound; streaming/buffering.
5. **Eliminate blocking directly in handlers** and `map`/`flatMap`/`doOnNext` callbacks; migrate HTTP to `WebClient` and DB to R2DBC where feasible.
6. **Isolate legacy calls** with `fromCallable().subscribeOn(dedicatedBoundedScheduler)`, keeping concurrency reasonable.
7. **Set dependency timeouts** and end-to-end deadlines; distinguish cancellation signals from drivers actually stopping.
8. **Limit load** via `flatMap` concurrency, semaphores/connection pools, rate limits, circuit breakers, and bounded queues.
9. **Prevent retry storms**; use retries with backoff, idempotency, and capped attempts.
10. **Preserve security/tracing context** via Reactor Context and approved propagation mechanisms.
11. **Test with `WebTestClient`/`StepVerifier`** for success, not found, timeout, and cancellation where deterministic.
12. **Load-test** in staging with realistic concurrency and payloads; monitor scheduler rejections and event-loop latency.
13. **Re-evaluate MVC vs. WebFlux** if most dependencies remain blocking and reactive maintenance costs are high.
14. **Monitor after changes**: ensure reducing p99 does not shift errors or queue delays to another layer.
15. **Maintain operational docs** covering scheduler ownership, dependency budgets, thread naming, and alert thresholds.

### Self-Check Questions

**1.** Why can WebFlux manage many connections with fewer threads?

**Answer:** Non-blocking/event-driven I/O lets a thread return to serve other sockets while waiting for I/O events, instead of one thread waiting per request.

**2.** Is `Mono.just(jdbc.find(id))` non-blocking?

**Answer:** No. `jdbc.find(id)` runs immediately when the expression is evaluated, potentially blocking the event loop before the Mono even exists.

**3.** What is the standard way to wrap a blocking method?

**Answer:** `Mono.fromCallable(() -> legacy.find(id)).subscribeOn(Schedulers.boundedElastic())` or an appropriate dedicated bounded scheduler.

**4.** Does `publishOn(boundedElastic)` after `fromCallable` guarantee the source is offloaded?

**Answer:** No. `publishOn` mainly switches downstream signals; the source may already execute on the subscribing thread. Use `subscribeOn` for blocking sources.

**5.** Why can `.block()` throw `IllegalStateException` on the event loop?

**Answer:** Reactor marks certain threads as non-blocking and disallows blocking APIs unsuitable for the event-loop model. Not throwing on other threads does not prove safety.

**6.** Does `timeout(2s)` guarantee cancelling a blocked SQL query?

**Answer:** No. It cancels the reactive subscription/emits a deadline error, while a blocking driver may keep running; driver/network statement timeouts are still required.

**7.** What must be considered when `WebClient` and the server both use Reactor Netty?

**Answer:** They can share event-loop resources by default, so blocking the server loop can affect outbound HTTP I/O callbacks.

**8.** Are `Schedulers.parallel()` and `boundedElastic()` used for the same things?

**Answer:** No. `parallel` fits CPU tasks; `boundedElastic` is for legacy blocking calls needing bounded worker capacity.

**9.** Does `Flux` with backpressure automatically prevent every unbounded queue?

**Answer:** No. You must evaluate whether the producer honors demand, plus buffering/retry/pool limits and overload policies at every layer.

**10.** What should be checked when migrating from blocking JDBC to WebFlux?

**Answer:** Choose a reactive database driver like R2DBC or offload to bounded workers, check transactions/context, connection pools, request concurrency, timeouts, and production observability.

## 22. Official Documentation and Further Reading

- [Spring Framework — WebFlux Overview / Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): why WebFlux uses non-blocking I/O and a small event-loop worker pool, differing from MVC.
- [Spring Framework — WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): annotated controllers, functional endpoints, Reactive Streams, and runtime.
- [Project Reactor — FAQ: Wrap a Synchronous Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): the `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` pattern.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `subscribeOn`, `publishOn`, `parallel`, `boundedElastic`, queues/bounds.
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): reactive context instead of relying on `ThreadLocal`.
- [Project Reactor — Reactor 3.6 Reference](https://projectreactor.io/docs/core/3.6.11/reference/index.html): APIs aligned with the Boot 3.3/Reactor 3.6 generation.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client and I/O connectors.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP-level tests for reactive servers.
- [Spring Framework — WebFlux Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux/ann-controller/ann-exceptions.html): `@ExceptionHandler`, `ProblemDetail`, and exception resolution.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): configuring WebFlux, servers, and tests in Boot 3.3.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, backpressure, publisher/subscriber protocols.
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `timeout`, `onErrorResume`, and error propagation.

**Conclusion:** WebFlux handles many connections well because event loops **do not wait on blocking I/O**. Merely slapping `Mono`/`Flux` return types onto synchronous code yields no reactive benefit. For non-blocking APIs, compose publishers; for blocking libraries that cannot be replaced immediately, use `Mono.fromCallable(...).subscribeOn(boundedElastic/dedicatedScheduler)` and limit load. Keep event-loop callbacks short, verify monitoring, timeouts, cancellation, context security, and audit every dependency to prevent one blocking call from bottlenecking the whole system.
