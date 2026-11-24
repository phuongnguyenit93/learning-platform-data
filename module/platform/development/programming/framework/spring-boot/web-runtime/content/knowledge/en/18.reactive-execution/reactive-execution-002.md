# Event Loop, Schedulers, and Distinguishing I/O-Bound vs. CPU-Bound Work

> **Context:** Spring Boot web-runtime, specifically Spring WebFlux running on Reactor Netty. This lesson explains the reactive execution model, where work runs, how to distinguish blocking/non-blocking I/O and CPU-bound tasks, how to choose an appropriate `Scheduler`, and practices with a runnable Java 17+ application.

## 1. Objectives

After this lesson, you will be able to:

1. Explain the role of the **event loop** in Netty and why a small number of threads can serve many HTTP connections when I/O operations are non-blocking.
2. Distinguish **I/O-bound** vs. **CPU-bound**; more importantly, distinguish **blocking I/O** vs. **non-blocking I/O**. Do not confuse "time-consuming I/O" with "must keep a thread waiting".
3. Understand the difference between the Netty event loop and a Reactor `Scheduler`; know how to use `Schedulers.parallel()`, `Schedulers.boundedElastic()`, `publishOn`, and `subscribeOn` for their intended purposes.
4. Understand why `map`, `flatMap`, `Mono`, and `Flux` do not automatically guarantee work switches to another thread.
5. Write and test a Spring WebFlux controller that does not block the event loop with synchronous code, while recognizing risks around throughput, latency, thread counts, queues, backpressure, and cancellation.

## 2. From the Thread-per-Request Model to the Event Loop

In a synchronous Servlet request-handling model, a request typically occupies a container worker thread while the handler runs. If the handler invokes synchronous JDBC or waits on synchronous HTTP for 500 ms, that worker thread usually must wait for the result. When many requests wait simultaneously, the container needs more workers or requests begin queuing. Servlets do support **asynchronous processing**, so one should not claim every Servlet application must hold a thread continuously until the response completes.

Spring WebFlux can run on Servlet containers, though it is commonly configured with **Reactor Netty** when a project uses `spring-boot-starter-webflux`. In that setup, Netty uses a group of **event-loop threads** to handle I/O events: connection ready to read, bytes received, socket writable again, connection closed, etc.

Visualizing the event loop:

```text
              many TCP / HTTP connections
                 /       |       \
              client A client B client C
                 \       |       /
             [Netty non-blocking sockets]
                        |
                  event-loop thread
                        |
       receive readiness / read / dispatch callback /
       run short processing / schedule write
                        |
               return to handle other events
```

**Core point:** the event loop does not dedicate a fixed thread per request. Instead, a thread runs a short task and returns to serve other connections. When data for a network operation **is not ready yet**, the thread does not wait with a blocking read; the reactor/network stack registers for an event and continues serving other connections.

Example: if an upstream responds after 800 ms, a non-blocking `WebClient` call can wait for the response **at the application-logic level** for 800 ms without occupying a Java thread sleeping for all 800 ms. The result is emitted when the corresponding network event arrives.

### Two Things Not to Confuse

- **Concurrent I/O:** many connections waiting simultaneously on I/O progress; a small number of event-loop threads can serve them. This does not mean Java callbacks for all connections are executing truly in parallel across multiple cores.
- **Parallel CPU:** multiple computational tasks executing simultaneously on multiple cores. To utilize multiple cores, CPU work must be distributed onto appropriate workers; merely creating a `Flux` does not make computations run in parallel.

Putting `Thread.sleep(500)`, synchronous JDBC, synchronous `RestTemplate`, or a long CPU loop onto the event loop prevents that thread from handling other sockets/callbacks during that interval. **One request blocking the event loop can slow down many unrelated requests**, because they may share the same event-loop thread.

## 3. I/O-Bound, CPU-Bound, and Two Types of I/O

**I/O-bound** means completion time depends primarily on the speed/latency of external systems: network, database, file system, or remote services. **CPU-bound** means time is spent primarily on CPU computation: encryption, decoding, compression, arithmetic, large data transformations, image processing.

However, you must also ask **whether the I/O API is blocking or non-blocking**:

| Work category | Examples in Java apps | While result is not ready | How to handle in WebFlux |
|---|---|---|---|
| Non-blocking network I/O | `WebClient` on Reactor Netty, compatible reactive drivers | Registers for events; no thread needed to wait for network response | Keep the pipeline reactive; normally **no need** to add `subscribeOn(boundedElastic())` just because network I/O exists |
| Blocking I/O | Synchronous JDBC, `RestTemplate`, synchronous SDKs, `Files.readAllBytes`, `InputStream.read` that may block | Calling thread is held while waiting | If the API cannot be replaced yet, wrap lazily (`fromCallable`) then `subscribeOn(Schedulers.boundedElastic())`; bound concurrency |
| Short CPU-bound | Condition checks, small DTO mapping, lightweight math | Brief CPU activity | Can run inline when cost is negligible; avoid pointless scheduler hops |
| Heavy CPU-bound | Hashing millions of records, compressing/transforming large payloads, long algorithms | Thread continuously runs computations | Move heavy CPU work off the event loop; consider `Schedulers.parallel()` or a dedicated CPU executor with concurrency limits |
| Both I/O and CPU needed | Receive network data then decompress, verify signature, process image | Alternates between I/O waiting and computation phases | Keep I/O reactive; isolate costly CPU sections to switch schedulers at appropriate boundaries |

Note: "file I/O" is not automatically non-blocking just because an app uses WebFlux. Many traditional file-reading APIs are still blocking. Likewise, **JDBC via `Mono.fromCallable` is still blocking JDBC**; only the waiting has been moved off the event loop. R2DBC aims at reactive non-blocking database connectivity when the driver and execution path support it.

**There is no rule saying "put all I/O on boundedElastic".** The right rule is that *blocking I/O* must be isolated from the event loop; *non-blocking I/O* thrives when kept on the asynchronous path.

## 4. What Is a Reactor `Scheduler` and How Does It Differ from the Event Loop?

A `Scheduler` in Project Reactor is an abstraction for **scheduling the execution** of pipeline tasks/callbacks. It determines which worker runs the work when operators request scheduling. The Netty event loop, by contrast, is part of the network runtime managing socket I/O events. The two interact, yet **are not identical**.

In a WebFlux request running on Reactor Netty, controllers and many operators typically start on an event-loop thread. If a pipeline has no asynchronous boundaries or scheduler switches, transformations like `map` usually continue on the thread emitting the signal. When `publishOn` or `subscribeOn` is added, the affected segments switch to threads managed by the Scheduler.

### Common Schedulers

| Scheduler | Characteristics | When to use | Avoid |
|---|---|---|---|
| `Schedulers.immediate()` | Runs immediately on the current thread, creates no new worker pool | Situations needing synchronous/no-op scheduling | Thinking it offloads heavy work off the event loop |
| `Schedulers.single()` | Scheduler using a single shared thread | Work that genuinely requires serialization on one worker | Submitting multiple blocking calls or long computations, blocking everyone sharing that worker |
| `Schedulers.parallel()` | Bounded pool geared toward CPU work, typically sized around processor count | Short-to-medium CPU computation, bounded CPU tasks | JDBC/`sleep`/blocking HTTP; unbounded or overly long CPU tasks |
| `Schedulers.boundedElastic()` | Pool with bounded resources and queue; suited to isolating blocking work | Synchronous APIs you must still call: blocking JDBC, synchronous SDKs, blocking file ops | Treating it as an "infinite thread pool"; unthrottled submissions cause queue and latency growth |
| `Schedulers.fromExecutorService(executor)` | Adapter for an application-configured executor | When needing dedicated thread pools, quotas, workload isolation, custom naming/monitoring | Creating an unbounded executor and forgetting shutdown |

Exact thread counts and implementation details also depend on Reactor version, runtime configuration, and hardware. For instance, `boundedElastic` may have strategies using platform threads or virtual threads on supported JDKs/configurations; **the semantics of "bounded for blocking work" remain unchanged**. Always measure in practice rather than relying on an immutable default thread number.

### Does a Scheduler "Make Code Non-Blocking"?

No. When `readLegacy()` is a synchronous thread-blocking method, running it on `boundedElastic` only **relocates where blocking occurs** to a thread managed for blocking work. This keeps the event loop more responsive, but still consumes threads and has an upper bound. End-to-end non-blocking requires non-blocking APIs/drivers and non-blocking processing throughout the pipeline.

## 5. Assembly, Subscription, and Where Operators Run

A publisher can be **assembled** (declared) without executing work yet. With cold publishers, data emission normally begins upon **subscription**. In WebFlux, the framework subscribes to the publisher returned by the controller to produce the HTTP response; you usually do not call `subscribe()` manually in a handler.

```java
// Illustrative snippet placed inside a method with Reactor imports.
Mono<String> source = Mono.fromCallable(() -> legacyCall());
Mono<String> result = source.map(String::toUpperCase);
// legacyCall() has NOT been invoked just by declaring source/result.
```

`Mono.just(legacyCall())` is different: Java evaluates the `legacyCall()` argument expression **eagerly when creating the Mono**, before `subscribeOn` has any chance to switch threads. This is a common bug:

```java
// WRONG if legacyCall() blocks: it runs immediately on the thread creating the Mono.
Mono.just(legacyCall()).subscribeOn(Schedulers.boundedElastic());

// RIGHT: defer the blocking call until subscription, then run on the right worker.
Mono.fromCallable(() -> legacyCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Both snippets show syntax assuming an existing synchronous `legacyCall()` method, not a standalone Java program.

### `subscribeOn` — Directing Subscribe / Upstream Execution

`subscribeOn(scheduler)` affects the subscription process and upstream emission source. It is the common way to push a **blocking source** off the event loop:

```java
Mono.fromCallable(() -> blockingJdbcQuery())
    .subscribeOn(Schedulers.boundedElastic())
    .map(result -> transform(result));
```

`blockingJdbcQuery()` executes on a boundedElastic worker upon subscription. Typically, `map` receives the signal on that emitting thread unless another operator/scheduler switches threads. No manual `subscribe()` is needed in the controller.

### `publishOn` — Switching Threads for Downstream Signals

`publishOn(scheduler)` shifts processing of signals after that point onto a worker belonging to the chosen scheduler, until another scheduling change occurs:

```java
Mono.fromCallable(() -> blockingJdbcQuery())
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(result -> expensiveCpuTransform(result));
```

The JDBC waiting region is blocking work on boundedElastic; the CPU `map` after `publishOn(parallel())` is switched to a CPU worker. This example illustrates the operators; running standalone requires defining `blockingJdbcQuery` and `expensiveCpuTransform`.

**Remember:** `publishOn` does not make computations non-blocking and **does not automatically split one large `map` across multiple cores**; it mainly changes which thread runs downstream steps. To process many elements across cores, you must partition work explicitly and bound concurrency.

### `map`, `flatMap`, and `parallel()`

- `map`: **synchronous** transformation on the current signal; `map(x -> slowBlockingCall(x))` still blocks whichever thread invokes it.
- `flatMap`: maps each element to another publisher and merges results; useful for composing non-blocking calls, though `flatMap` **does not automatically move** synchronous code inside its lambda to a separate pool.
- `parallel()`: splits a `Flux` into rails; to actually schedule rails onto CPU workers, pair it with `runOn(Schedulers.parallel())`, then `sequential()` if returning to a `Flux`. Watch thread-switching overhead, result ordering, and resources.
- Manual `subscribe()` inside a WebFlux controller creates a detached execution flow that the framework neither awaits, cancels, nor propagates errors from as the response publisher. Always **return the publisher** so the framework manages the request lifecycle.

```java
// Directional example; assumes cpuTransform(long) is defined.
Flux.range(1, 100)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(i -> cpuTransform(i))
    .sequential();
```

Never assume parallel processing is always faster: for small items, queuing, thread switching, and signal merging costs can outweigh the gains.

## 6. Hands-On: A Runnable Spring Boot WebFlux Application

Use a **dedicated Spring Boot WebFlux application** with Java 17+ and dependency `org.springframework.boot:spring-boot-starter-webflux`. In an existing Gradle Spring Boot project, the corresponding dependency line is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

This is a **dependency configuration snippet**; the project still needs standard Spring Boot/Gradle setup from your application. To observe Reactor Netty clearly, avoid also adding `spring-boot-starter-web`: if both MVC and WebFlux are present, Spring Boot typically prefers configuring MVC as the web application type unless configured otherwise.

Create the complete file `src/main/java/example/reactive/ReactiveExecutionApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveExecutionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveExecutionApplication.class, args);
    }

    @RestController
    static class WorkController {

        // Only for local testing on default port 8080.
        // Production: configure service URL via properties/injection.
        private final WebClient webClient =
                WebClient.create("http://localhost:8080");

        @GetMapping("/demo/echo")
        Mono<String> echo() {
            return Mono.just("pong");
        }

        @GetMapping("/demo/nonblocking-io")
        Mono<String> nonblockingIo() {
            // WebClient uses reactive network I/O; no block() needed.
            return webClient.get()
                    .uri("/demo/echo")
                    .retrieve()
                    .bodyToMono(String.class)
                    .map(body -> "webclient: " + body);
        }

        @GetMapping("/demo/blocking-io")
        Mono<String> blockingIo() {
            // Simulates a synchronous SDK or JDBC taking 150 ms.
            // Thread.sleep is for experimentation only, never for real I/O.
            return Mono.fromCallable(() -> {
                        Thread.sleep(150);
                        return "legacy: ok";
                    })
                    .subscribeOn(Schedulers.boundedElastic());
        }

        @GetMapping("/demo/cpu")
        Mono<Long> cpu() {
            // Pure CPU work; sums 0..1_999_999.
            return Mono.fromCallable(() -> {
                        long sum = 0;
                        for (long i = 0; i < 2_000_000; i++) {
                            sum += i;
                        }
                        return sum;
                    })
                    .subscribeOn(Schedulers.parallel());
        }

        @GetMapping("/demo/threads")
        Mono<String> threads() {
            return Mono.defer(() -> {
                        String sourceThread = Thread.currentThread().getName();
                        return Mono.just("source=" + sourceThread);
                    })
                    .publishOn(Schedulers.parallel())
                    .map(value -> value + ", mapped="
                            + Thread.currentThread().getName());
        }
    }
}
```

**Explanation of each endpoint:**

- `/demo/echo` is an auxiliary endpoint acting as a simulated upstream. It returns `pong`.
- `/demo/nonblocking-io` makes an HTTP call to `/demo/echo` via `WebClient`'s reactive API; it does not call `block()` or `sleep()`. Socket waiting is handled by the network runtime.
- `/demo/blocking-io` uses `Mono.fromCallable` to **defer** the synchronous call, then `subscribeOn(boundedElastic())` to avoid holding the Netty event loop for 150 ms. The `Thread.sleep` operation itself remains blocking.
- `/demo/cpu` performs computation on a `parallel` worker. CPU work is not "waiting I/O", so moving it to boundedElastic merely because the handler returns `Mono` lacks justification.
- `/demo/threads` records thread names when the source is subscribed and in `map` after `publishOn`. With Reactor Netty you typically see `source` named around `reactor-http-nio-...` and `mapped` around `parallel-...`, **but thread names/numbers are not an API contract**; they depend on configuration, runtime, and scheduler.

In the project terminal, run the application with `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). If the project has another main application class, use a separate test project or configure which main class to run so two main classes are not detected simultaneously.

Run the test commands (in PowerShell use `curl.exe` to avoid Windows PowerShell's `curl` alias):

```bash
curl -s http://localhost:8080/demo/echo
curl -s http://localhost:8080/demo/nonblocking-io
curl -s http://localhost:8080/demo/blocking-io
curl -s http://localhost:8080/demo/cpu
curl -s http://localhost:8080/demo/threads
```

Respective response bodies for the first four requests when running on port 8080:

```text
pong
webclient: pong
legacy: ok
1999999000000
```

For `/demo/threads`, **do not hardcode exact stdout/body thread names**; inspect the `source=` and `mapped=` values in the actual response. The `/demo/cpu` route computes the exact sum `0 + 1 + ... + 1_999_999 = 1_999_999_000_000`.

**Experiment limitations:** `Thread.sleep(150)` simulates blocking I/O and is not an example of real network/file APIs; `WebClient` calling loopback demonstrates non-blocking HTTP rather than measuring production performance. Latency/throughput from a single request does not prove a scheduler is optimal: you must run concurrent requests and monitor event-loop lag, CPU, thread pools, queues, and timeouts.

## 7. Where Should Each Type of Work Be Placed?

### 7.1. Non-Blocking I/O: Compose Publishers, Do Not Force Scheduler Switches

```java
// Example inside a service with an injected WebClient:
Mono<UserDto> findUser(String userId) {
    return webClient.get()
            .uri("/users/{id}", userId)
            .retrieve()
            .bodyToMono(UserDto.class);
}
```

This is **illustrative service code**, requiring a `WebClient webClient` field and `UserDto` type. `bodyToMono` returns a publisher; WebClient manages I/O through the async runtime. Calling `findUser(id).block()` in a controller on the event loop turns the whole chain into synchronous waiting on the current thread and risks Reactor rejecting it on a non-blocking thread.

For databases, prefer an appropriate reactive driver (e.g., R2DBC) if the entire execution path is truly intended to be non-blocking. Do not confuse `@Async`, returning `Mono`, or using `Flux` with the underlying driver actually being non-blocking.

### 7.2. Blocking I/O: Defer + boundedElastic + Limits

```java
// Example inside a service with an existing LegacyRepository:
Mono<Report> loadLegacyReport(long id) {
    return Mono.fromCallable(() -> legacyRepository.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

`LegacyRepository` and `Report` are hypothetical application types; this snippet illustrates the pattern and does not compile standalone. With JDBC, blocking SDKs, and blocking file APIs, similar wrapping keeps the event loop freer. Still, under 10,000 concurrent requests, boundedElastic has worker and queue limits; you need matching **database pools, timeouts, bulkheads, and concurrency limits**.

When mapping many elements to blocking tasks, you can bound active tasks:

```java
// Assumes blockingLoad(id) is defined; at most 8 inner publishers
// are concurrently subscribed by flatMap.
Flux.range(1, 100)
    .flatMap(id ->
            Mono.fromCallable(() -> blockingLoad(id))
                .subscribeOn(Schedulers.boundedElastic()), 8);
```

`flatMap(..., 8)` prevents unbounded inner calls within this pipeline, but does not globally limit total load across **all HTTP requests**. Application-wide bounds are needed if downstream shares a quota.

### 7.3. CPU-Bound: Move Off the Event Loop, Control Thread Count

For heavy computation per item:

```java
// Assumes CPU computation per item; non-standalone illustration.
Flux.range(1, 100)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(this::expensiveCpuWork)
    .sequential();
```

`parallel(4)` creates up to four rails and `runOn` schedules rail work on the Scheduler. This illustrates partitioning when CPU can process independent chunks. If computation consists of **one single large task**, `subscribeOn(parallel())` or `publishOn(parallel())` moves that task to a single worker; it does not split the algorithm across cores.

Long, costly CPU tasks easily saturate `parallel()` threads; consider a dedicated worker/executor, batch job, or queue architecture to avoid impacting other requests. Adding schedulers does not create CPU capacity; physical cores remain the limit.

### 7.4. Pipeline Combining Blocking I/O and CPU

```text
HTTP request (event loop)
  -> Mono.fromCallable(blockingLoad)
        subscribeOn(boundedElastic)  [waits on synchronous JDBC/SDK]
  -> publishOn(parallel)             [heavy CPU transformation]
  -> Mono/Flux result written to response by WebFlux
```

If `blockingLoad` is replaced with non-blocking `WebClient` or reactive R2DBC queries, remove the unnecessary blocking offload; keep only the heavy CPU switch where needed. **Do not place `publishOn(parallel())` before a blocking call expecting it to become non-blocking:** you are merely blocking a CPU pool thread.

## 8. Request Timeline and Impact on the HTTP Response

```text
T0: Netty event loop reads request, WebFlux invokes handler
T1: Handler returns Mono/Flux, framework subscribes to response publisher
T2: Non-blocking I/O: registers/reads events; waiting does not hold event loop
    or legacy blocking: callable runs on boundedElastic
    or heavy CPU: computation runs on parallel/custom pool
T3: Pipeline emits onNext / passes signals through operators
T4: Framework encodes + writes body; response may flush incrementally when streaming
T5: onComplete -> normal response completion
    onError -> error; cancel -> subscription cancelled (e.g., client disconnect)
```

This is a conceptual model. Header commit ordering, flushing, I/O callbacks, and `onNext` can differ across media types, codecs, HTTP versions, proxies, and containers. **An operator finishing or publisher emitting `onComplete` does not prove the browser has finished reading/rendering the body.**

For streaming responses (`text/event-stream`, NDJSON), an app may keep an HTTP response open for a long time to send multiple items. If each item passes through blocking/CPU code on the event loop, you can cause lag for other connections. If upstream is slow, consider timeouts and cancellation handling; if the client is slow, monitor buffering/backpressure to avoid unbounded RAM retention.

## 9. Common Mistakes and How to Fix Them

| Mistake | Why it is dangerous | How to fix |
|---|---|---|
| Calling `.block()`/`.blockFirst()` in a WebFlux handler on the event loop | Holds thread waiting, may throw errors for blocking on a `NonBlocking` thread | Return `Mono`/`Flux` directly and compose via `flatMap`, `map`, `zip`, `then` |
| `Mono.just(legacy.load())` followed by `subscribeOn(boundedElastic())` | `legacy.load()` executes synchronously at assembly time | Use `Mono.fromCallable(() -> legacy.load()).subscribeOn(boundedElastic())` |
| Calling blocking JDBC inside `map` | `map` runs on the signal-emitting thread; if that is the event loop, it stalls | Isolate blocking source into `fromCallable + subscribeOn(boundedElastic)` |
| Running `Thread.sleep` on the event loop or `parallel()` | Holds a thread idle without doing useful work | For pure reactive delays, use `Mono.delay`/`delayElement`; for real synchronous libraries, use a blocking pool |
| Moving every `WebClient` call onto `boundedElastic` | Adds scheduling/queue overhead to an already non-blocking source | Keep the non-blocking path; only offload genuinely CPU/blocking steps |
| Running heavy CPU work unbounded on `boundedElastic` | CPU contention, saturated pool/queue, erratic latency | `parallel`/dedicated CPU executor + concurrency bound/batching |
| Treating `flatMap` as "runs on another thread" | Synchronous lambdas still execute on the current thread | Inspect whether the inner source is non-blocking; assign scheduler to blocking parts |
| Adding arbitrary `publishOn` calls everywhere | Increases context switching, queuing, and tracing complexity | Switch threads at justified work boundaries; benchmark |
| Manually calling `subscribe()` in a controller and returning `Mono.empty()` | Detaches task from response, obscures errors/cancellation | Return a publisher tied to the response; let the framework manage subscription |
| Relying on `ThreadLocal` for security/trace context across scheduler hops | Thread-local data can be lost or leaked across requests | Use Reactor `Context`/framework context propagation and built-in security/tracing |
| Blocking the event loop with huge JSON encoding or synchronous logging | Reactive network I/O does not protect against CPU/blocking in callbacks | Measure CPU/serialization/logging; offload heavy parts, split/stream payloads appropriately |

### Why Isn't `Mono.delay` the Same as `Thread.sleep`?

`Thread.sleep(1000)` puts a thread to sleep for 1 second. `Mono.delay(Duration.ofSeconds(1))` sets up a timer and emits a signal after the delay when subscribed; it does not hold a sleeping thread for the entire wait. However, `Mono.delay` **cannot turn a blocking JDBC query into a non-blocking one**; it only describes a timer.

### Why Can Small Tests "Appear to Work Fine"?

With a single request, even `Thread.sleep` on the event loop can return a response in a few hundred milliseconds. The problem surfaces when multiple connections share an event loop: unrelated requests suffer increased latency. Therefore, apply concurrent load and inspect tail latency (p95/p99), not just single-request averages.

## 10. How to Observe and Verify

1. **Confirm the runtime:** check whether the app actually runs WebFlux + Reactor Netty or Spring MVC + Servlet container. Thread names like `reactor-http-nio-...` usually suggest Netty, though thread names alone are insufficient proof.
2. **Measure responsiveness:** send many concurrent requests to `/demo/blocking-io` and verify `/demo/echo` stays responsive; compare against a test-environment version that intentionally blocks the event loop to observe the impact. Never deploy an intentionally blocking version to production.
3. **Inspect thread dumps/metrics:** track event-loop threads, active `boundedElastic` workers, queues, CPU usage, connection pool size, timeouts, and throughput. Thread dumps show where threads are blocking, while CPU analysis requires profiling.
4. **Use thread-name logs selectively:** log at the source, before/after `publishOn`, and in error callbacks to see where code executes. Do not assume every `onNext` of a request stays on one single thread.
5. **Test cancellation/error:** close a client mid-stream and verify external sources are cancelled/cleaned up. `doFinally(signal -> ...)` can help clean up or observe terminal `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; never treat cancel as success.
6. **Verify via real HTTP integration tests:** controller mocks cannot reveal event-loop lag, network flushing, connection pools, or proxy behavior. Correct HTTP status/body does not prove the pipeline is free of blocking.
7. **Profile before optimizing:** measure I/O wait time, CPU time, pool pressure, and proxy latency. Only increase thread counts or change schedulers when measurements pinpoint the bottleneck.

Testing libraries can detect blocking calls on threads marked non-blocking (such as BlockHound in compatible environments), though they do not replace profiling/load testing and have JVM, instrumentation, and library compatibility constraints.

## 11. Design Decision Scenarios

**Scenario A — WebFlux calls a remote REST API with WebClient:** Keep the `Mono` returned by `WebClient` and compose the result; do not await with `.block()`. Add appropriate timeouts, conditional/idempotent retries, and request limits; do not offload to boundedElastic merely because HTTP has latency.

**Scenario B — WebFlux must call a legacy JDBC library:** Wrap the query in `fromCallable` and use `subscribeOn(boundedElastic())`; monitor JDBC pools, timeouts, and concurrency limits. If end-to-end non-blocking is required, evaluate migrating to a suitable reactive driver/data stack rather than simply wrapping with `Mono`.

**Scenario C — Heavy CPU image or report processing:** Do not compute on the Netty event loop. Move to an appropriate CPU scheduler/executor and bound concurrent tasks; consider background processing if duration exceeds HTTP request lifecycles.

**Scenario D — Long-lived SSE receiving data from a reactive upstream:** Keep the flow non-blocking and emit events with the right media type. If each event calls a blocking API, isolate that step and bound resources; handle cancel on client disconnect plus heartbeats/timeouts as needed.

**Scenario E — Using Spring MVC instead of WebFlux:** Servlet worker threads and async MVC have distinct properties; having a `Mono` somewhere in code **does not turn an MVC app into a Reactor Netty server**. Analyze the actual runtime before applying event-loop advice.

## 12. Self-Check Questions

**1. WebClient takes 500 ms to receive a response; does an event-loop thread have to sit idle for 500 ms?**  
No. With non-blocking network I/O, the runtime registers/receives events when data arrives; the request still experiences 500 ms latency, while the thread can handle other work during the wait.

**2. Does `Mono.just(jdbcRepository.load())` followed by `subscribeOn(boundedElastic())` protect the event loop?**  
No. `load()` executes immediately when constructing `Mono`; you must use a lazy source such as `Mono.fromCallable(() -> jdbcRepository.load()).subscribeOn(boundedElastic())`.

**3. Is `Schedulers.parallel()` suitable for `Thread.sleep` or blocking JDBC?**  
No. That pool is meant for CPU work; blocking holds CPU workers captive. Blocking APIs should be isolated on boundedElastic or a managed blocking executor.

**4. Does `publishOn(parallel())` turn a monolithic computation into multi-core computation?**  
No. It switches the downstream section to another worker; utilizing multiple cores requires splitting data/operations into independent tasks with appropriate concurrency.

**5. Does `flatMap(id -> legacyBlocking(id))` automatically run `legacyBlocking` on another thread?**  
No. If the lambda calls a blocking method to produce data, that call runs synchronously on the current thread. You must defer it into an appropriate publisher and assign a scheduler for the blocking section.

**6. If all blocking I/O is offloaded to `boundedElastic`, can the system handle infinite requests?**  
No. Scheduler threads and queues are bounded; database/HTTP pools, CPU, memory, downstream capacity, and timeouts still limit throughput.

**7. Should you guess the event loop from thread names and assume the thread never changes?**  
No. Thread names are useful only for debugging; `publishOn`, `subscribeOn`, drivers, and other callbacks can switch threads. Observe the actual runtime and never depend on implicit thread affinity.

## 13. Official References

- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): WebFlux execution model, concurrency, and non-blocking design.
- [Spring Framework Reference — Execution Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html#webflux-concurrency-model): comparing the WebFlux model with Servlet and handling blocking.
- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `Schedulers`, `publishOn`, `subscribeOn`, and thread boundary semantics.
- [Project Reactor Reference — Parallelizing Work](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-parallelizing-parralelflux.html): `parallel`, `runOn`, `sequential`.
- [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): Reactor Netty HTTP server, event-loop resources, and related configuration.