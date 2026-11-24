# The Event-Loop Model and the Cost of Blocking Calls

In **Spring WebFlux**, especially when running on **Reactor Netty**, many HTTP connections can be served by a relatively small number of event-processing threads (*event-loop workers*). This works efficiently when the application **does not hold a thread while waiting for I/O**: the thread registers the work, continues handling other events, and receives a notification when the result is ready.

A **blocking** call such as `Thread.sleep`, waiting on `Future.get`, or making a synchronous JDBC call can tie up an event-loop worker while doing no useful work. During that time, other connections and callbacks assigned to that worker may have to wait. The biggest impact is usually **increased latency, reduced throughput, and cascading timeout failures under load**, even when CPU is not saturated.

This lesson explains how the event loop works, how to recognize different forms of blocking, how to coordinate Reactor `Scheduler`s, and how to handle remaining synchronous APIs inside a reactive application.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe how an event loop handles I/O events and distinguish **waiting asynchronously** from **holding a thread to wait**.
2. Explain why WebFlux typically requires fewer workers than a thread-per-request model, while recognizing the limits of that comparison.
3. Identify operations that can block a worker: `block()`, `Thread.sleep`, JDBC, synchronous HTTP clients, file I/O, lock contention, and overly heavy CPU work.
4. Distinguish `Schedulers.parallel()`, `Schedulers.boundedElastic()`, `subscribeOn`, and `publishOn`; choose the right execution-context switch.
5. Wrap a blocking API with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, bound concurrency, and preserve error/cancellation propagation.
6. Write WebFlux handlers that return `Mono` or `Flux` without arbitrarily calling `subscribe()` or `block()`.
7. Observe signs of event-loop stalls and test execution threads using Reactor Test.

## 2. How Does an Event Loop Work?

An event loop is a loop that processes events. In a non-blocking network system, it can:

- Monitor multiple connections/sockets and detect when read, write, or connection events are ready.
- Pick up an event, run a short piece of processing, update state/results, and register the next asynchronous work.
- Yield control quickly so the worker continues handling other connections, timers, and callbacks.

A simple mental diagram:

~~~text
                Multiple HTTP connections
                  /     |      \
                 A      B       C
                  \     |      /
                 Ready event queue
                          |
                   Event-loop worker
                          |
                Receive -> short processing
                          |
             +------------+-------------+
             |                          |
       Data available           Needs async I/O
             |                          |
       Emit signal              Register callback /
       or write socket          I/O wait state
             |                          |
       Return to event loop     Return to event loop
                                        |
                              I/O completes later
                                        |
                              New event is processed
~~~

This is a conceptual diagram and does not attempt to capture all Reactor Netty internals. An event loop does not mean **every connection shares a single thread**. The runtime typically has **multiple workers**; one worker can handle many connections via multiplexing. Nor does a request **necessarily stick to one thread forever**: a Reactor pipeline can switch contexts via a scheduler, and callbacks from external sources can run on other threads.

### What Exactly Does "Non-blocking" Mean?

For a network wait operation:

- **Blocking:** the calling thread invokes the operation and waits until data arrives or a timeout occurs; while waiting, it serves no other work.
- **Non-blocking/asynchronous:** the operation is initiated or registered; the thread can leave. When data is ready, the system schedules a callback/event to resume processing.

**Asynchronous does not automatically mean non-blocking.** You can run a blocking call on another worker pool and return the result via a `Mono`; to the caller it looks asynchronous, yet a worker in that other pool **is still held** waiting. That solution helps **isolate** blocking from the event loop, without turning a blocking API into true non-blocking I/O.

## 3. How Does WebFlux Differ from the Thread-per-Request Model?

Spring WebFlux supports a reactive programming flow with `Mono`, `Flux`, and Reactive Streams. When running on a non-blocking server like Reactor Netty, it assumes **non-blocking** request handling, enabling it to use a relatively small pool of event-loop workers.

In a traditional servlet application, a blocking request typically holds a thread from the request pool while waiting on I/O. The server can use a larger pool to absorb many waiting requests; in return, each thread, context switch, and queue consumes resources. Modern Spring MVC also has its own asynchronous mechanisms; one should not conclude that every Spring MVC request requires a thread locked until completion.

| Perspective | Non-blocking event-loop worker | Request using blocking calls |
| --- | --- | --- |
| While waiting on network/database | Can return the worker to the event processing loop | Calling thread typically waits |
| Primary load model | Events/callbacks across many connections | Many threads or a pool to absorb wait time |
| Long-running task | Stalls the shared worker | Stalls the thread/pool dedicated to the request |
| Costs to manage | Event-loop latency, schedulers, queues, demand | Pools, queues, thread stacks, context switching |
| When a synchronous API is unavoidable | Offload to an appropriate scheduler/adapter | Can execute in a controlled blocking thread pool |

**WebFlux does not run on "0 threads" and does not automatically make every library reactive.** WebFlux can also run on Servlet API-based servers that support non-blocking I/O. Actual configuration and worker counts depend on runtime, resources, and deployment; avoid assuming a fixed thread count for all machines.

## 4. Why Is Even One Blocking Call Dangerous?

Suppose event-loop worker W is handling multiple connections:

~~~text
Time  --->

Non-blocking:
W: [A: start I/O][B: process][C: process][A: I/O done][D: process]...

With blocking in A:
W: [A: Thread.sleep(500 ms)........................][B][C][D]...
                    B, C, D must wait for W to be free
~~~

If a handler blocks for 500 ms, other events needing that exact worker may wait up to hundreds of milliseconds even when they only require very fast processing. If **multiple** workers are blocked at once, wait times across the whole server can spike suddenly.

Commonly observed effects:

1. **Latency and tail latency:** p95/p99 increase; users see even short requests become slow while waiting for a worker.
2. **Throughput:** events processed per second drop; adding more connections does not resolve the worker bottleneck.
3. **Cascading timeouts:** clients time out, retries increase load, and queues/responses slow down further.
4. **Memory and backlog:** waiting callbacks, requests, or data are retained; queue limits may be hit.
5. **Hard-to-trace failures:** logs only show "service slow," while the root cause is a small synchronous section buried deep in the pipeline.

**Not all CPU work is blocking I/O**, yet a prolonged CPU computation also **occupies the worker and prevents the event loop from handling other connections**. Thus the practical rule is: **keep callbacks on the event loop short, non-blocking, and not overly compute-heavy**.

## 5. Identifying Types of Stalling Work

| Action inside handler/operator | Characteristics | What to watch out for |
| --- | --- | --- |
| `Thread.sleep(500)` | Blocks the current thread for the sleep duration | Do not use to wait for timers in reactive flows. |
| `mono.block()`, `flux.blockFirst()`, `blockLast()` | Synchronously waits for a publisher to emit/complete | On Reactor non-blocking threads, typically rejected with `IllegalStateException`. |
| `Future.get()`, `CompletableFuture.join()` | Can block when the result is not yet ready | Does not imply an end-to-end non-blocking API. |
| JDBC, synchronous HTTP client, synchronous file read | Blocks during I/O or waiting for resources | Use an appropriate reactive driver or a blocking isolation pattern. |
| Waiting on contended lock, semaphore, queue, `synchronized` | Can keep the worker held | Avoid long critical sections/lock waits on the event loop. |
| Heavy CPU loops, huge JSON, CPU-heavy compression/encryption | Continuously consumes CPU; may not call blocking APIs | Offload off the event loop, bound concurrency, and profile CPU. |
| `Mono.delay(Duration)` | Schedules a timer on a scheduler; does not hold a sleeping thread for the entire wait | Suitable for modeling delayed signals, not a substitute for real I/O. |
| `WebClient` with reactive API | Can use non-blocking network I/O | Only non-blocking if the entire callback/mapper chain contains no blocking operations. |

Some APIs already have a result ready so `Future.get` need not wait; an uncontended lock can be entered quickly. The problem is the **risk of holding a worker for a long time when data/resources are not ready**, especially under load.

### Do Not Misunderstand the Safeguards

Reactor marks threads of `Schedulers.parallel()` and `Schedulers.single()` as disallowing Reactor's own blocking wait operations. Calling `block()` on threads marked *non-blocking* typically throws `IllegalStateException`. Reactor Netty event-loop threads are usually marked the same way.

However, `Thread.sleep` or a JDBC call **is not automatically detected and stopped by Reactor** merely because it runs on the event loop. They can genuinely make the worker sit waiting. Test-time blocking-detection tools can help, but you should not rely on a runtime exception in place of design review.

## 6. Mono/Flux Do Not Automatically Create New Threads

A common misconception:

~~~java
Mono<String> value = Mono.just("hello")
    .map(text -> text.toUpperCase());
~~~

This is a Reactor pipeline. In most cases, without a separate scheduler or special asynchronous source, the operators execute on the thread emitting signals/subscribing, **not on a new thread just because `Mono` is used**.

Similarly:

~~~java
Mono<String> slow = Mono.fromCallable(() -> legacyClient.load());
~~~

`Mono.fromCallable` only defers calling `legacyClient.load()` until subscription. If the source is subscribed to on an event-loop worker, the blocking call can run **right on that worker**. Using `Mono.fromCallable` **is not enough** to handle blocking; you must control where the task runs.

Also avoid:

~~~java
Mono<String> wrong = Mono.just(legacyClient.load());
~~~

Here `legacyClient.load()` is invoked by Java **immediately when building the pipeline**, even before subscription, so it can block the thread calling the handler method right away. These two examples assume `legacyClient` is an existing synchronous API in the application; they illustrate the pattern and are not standalone programs.

## 7. Reactor Schedulers and How to Choose

Reactor provides `Scheduler` to control the execution context:

| Scheduler | Primary purpose | Should not be mistaken for |
| --- | --- | --- |
| `Schedulers.immediate()` | Executes immediately in the current thread context | A new thread pool |
| `Schedulers.single()` | One reusable worker for sequential execution | A suitable place for blocking I/O or long computations |
| `Schedulers.parallel()` | CPU-bounded pool for controlled CPU-bound work | A pool for blocking calls |
| `Schedulers.boundedElastic()` | Isolates synchronous/blocking I/O work that must still be used | Infinite resources or turning an API into non-blocking |
| `Schedulers.fromExecutorService(...)` | Integrates an application-managed pool | A pool with automatically tuned quota/concurrency if unconfigured |

`boundedElastic` has bounded thread counts and queues for waiting tasks. When load exceeds capacity, tasks can still **queue up and get delayed or rejected**. It does not cure an under-provisioned downstream service. Exact configuration depends on Reactor version, CPU, and runtime choices; measure and also bound connection pools/concurrency.

### How Do `subscribeOn` and `publishOn` Differ?

**`subscribeOn(scheduler)`** affects the subscription process and source execution that can be scheduled. Reactor generally recommends placing it **right after the blocking source** so the thread switch is explicit:

~~~java
Mono<String> safe = Mono.fromCallable(() -> legacyClient.load())
    .subscribeOn(Schedulers.boundedElastic());
~~~

**`publishOn(scheduler)`** switches signal emission **to a worker of that scheduler for operators after its position** (until another switch occurs):

~~~java
Flux<Integer> computed = Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform);
~~~

This is an integration snippet: `cpuIntensiveTransform` is an application method. `publishOn` fits when you want to move computation **after** it off the event loop. If heavy computation sits **before** `publishOn`, that computation is not protected by a scheduler switch placed afterward.

**Do not scatter `publishOn` or `subscribeOn` without reason.** Each asynchronous boundary carries scheduling, queuing, and thread-context switching cost; adding too many can raise latency or make debugging unpredictable. Nor do they replace load limiting and cancellation.

## 8. The Right Pattern When You Must Call a Blocking API

Reactor's recommended approach for a synchronous call:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyRepository.lookup(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is an integration snippet requiring `Result` and `legacyRepository` to be defined. Meaning:

1. `fromCallable` keeps the synchronous call inside a **lazy** publisher that runs only upon subscription.
2. `subscribeOn(boundedElastic)` specifies an appropriate worker to run the source, avoiding holding an event-loop worker while calling the synchronous API.
3. A successful result is emitted as `onNext` followed by `onComplete`. If the `Callable` returns `null`, `Mono.fromCallable` completes empty; if it throws an exception, Reactor emits `onError`.
4. The WebFlux subscriber can continue composing `map`, `flatMap`, `timeout`, and HTTP response handling without synchronously waiting via `block()`.

If the source has multiple items, you can use `Flux.defer` or `Flux.fromIterable` with an appropriate adapter, but control **the exact scope of the blocking call**. Moving an entire complex pipeline onto another pool can pile both blocking and CPU load onto one large queue.

### Why Not Simply Call `subscribe()` Manually?

~~~java
public Mono<String> incorrect() {
    legacyWork().subscribe();
    return Mono.just("done");
}
~~~

This example is only an integration snippet with an application-defined `legacyWork()`. The handler returning `"done"` can finish **before the task actually completes**; errors, cancellation, and timeouts are detached from the request lifecycle. In WebFlux, **return the composed publisher** so the framework subscribes and manages it:

~~~java
public Mono<String> correct() {
    return legacyWork().thenReturn("done");
}
~~~

If `legacyWork()` actually uses a blocking library, it still needs to be offloaded **inside** that service. `thenReturn` only chains the completion signal; it does not choose a scheduler by itself.

## 9. Runnable Java 17 Program: Non-Blocking Timer and Isolated Blocking

This example has two tasks:

- A "legacy" call simulated with `Thread.sleep`, running on `boundedElastic`.
- A timer using `Mono.delay`; during the delay, no worker needs to be held with `Thread.sleep`.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'EventLoopDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create `src/main/java/EventLoopDemo.java`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class EventLoopDemo {
    public static void main(String[] args) {
        Mono<String> legacy = Mono.fromCallable(() -> {
            Thread.sleep(40); // Simulate synchronous I/O; runs only on boundedElastic.
            return "legacy-ok";
        }).subscribeOn(Schedulers.boundedElastic());

        Mono<String> timer = Mono.delay(Duration.ofMillis(20))
            .thenReturn("timer-ok");

        Mono<String> combined = Mono.zip(legacy, timer)
            .map(pair -> pair.getT1() + " | " + pair.getT2());

        System.out.println("pipeline assembled");
        String result = combined.block(Duration.ofSeconds(5));
        System.out.println("result = " + result);
    }
}
~~~

Run inside the project directory with `gradle run`. If using Gradle Wrapper, use `./gradlew run` (on Windows use `gradlew.bat run`). **Program stdout**, excluding Gradle's own logs:

~~~text
pipeline assembled
result = legacy-ok | timer-ok
~~~

**Why is the output deterministic?**

- Creating the `Mono` instances and composing `Mono.zip` does not immediately execute the `Callable` or the timer.
- `block(Duration.ofSeconds(5))` in the **`main` method of a command-line application** subscribes and waits for the result so the program can print it; do not use this in a WebFlux handler.
- `Mono.zip` waits for **both Monos to emit a value**. Depending on the environment, the timer may finish before or after `legacy`, yet the tuple always holds `legacy` at position 1 and `timer` at position 2.
- `thenReturn("timer-ok")` discards the tick value from `Mono.delay`, emitting only the string once the timer finishes.
- Thread names or individual branch completion timestamps are not printed because those details depend on scheduling; one should not assert an unguaranteed stdout order.

This is an example simulating offloading, **not a benchmark**: `Thread.sleep(40)` does not represent all timeout, cancellation, and resource characteristics of real JDBC/HTTP clients. A real blocking API may not cooperate with cancellation or may keep running until I/O finishes.

## 10. WebFlux Example: Faulty Controller Snippet and How to Fix It

Assume a Spring Boot application with `spring-boot-starter-webflux` added and a `LegacyCustomerClient` that performs a synchronous query returning `CustomerDto`.

### Wrong way: callable can run on the event loop

~~~java
@GetMapping("/customers/bad/{id}")
public Mono<CustomerDto> bad(@PathVariable String id) {
    return Mono.fromCallable(() -> legacyClient.findById(id));
}
~~~

`fromCallable` is lazy, so when the framework subscribes to the result, executing the callable can happen on the request-serving thread, such as a Reactor Netty event loop. If `findById` waits on JDBC or synchronous HTTP, that worker is held for the duration of the wait.

### Proper way: offload right at the blocking API boundary

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class CustomerController {
    private final LegacyCustomerClient legacyClient;

    public CustomerController(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    @GetMapping("/customers/{id}")
    public Mono<CustomerDto> find(@PathVariable String id) {
        return Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

This is an **integration snippet**, requiring `LegacyCustomerClient`, `CustomerDto`, and the synchronous client bean to be defined; the code is not a standalone Java file. In a real application, if `findById` returns `null`, `Mono.fromCallable` completes empty; decide explicitly on the "not found" behavior (for instance HTTP 404 via `switchIfEmpty(Mono.error(new ResponseStatusException(...)))`), rather than assuming an empty response body is the desired business outcome.

### When fetching multiple IDs

~~~java
Flux<CustomerDto> customers = Flux.fromIterable(customerIds)
    .flatMap(id ->
        Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

This is an integration snippet with `customerIds`, `legacyClient`, and `CustomerDto` already available. The parameter `8` limits the number of **inner publishers subscribed concurrently** by `flatMap`, helping avoid launching too many blocking tasks at once. It does not replace connection pool limits, timeouts, queues, downstream quotas, or memory limits.

**Ordering note:** `flatMap` may emit results in a different order than the original IDs because completion times vary. If result order matters, consider `flatMapSequential`; if work must run sequentially per business rules, use `concatMap`.

## 11. Prefer End-to-End Non-Blocking Whenever Possible

`boundedElastic` is an integration approach **when a blocking API cannot yet be replaced**, not the ultimate goal of a reactive system. Common pairings:

| Task | Blocking integration | Reactive/non-blocking option |
| --- | --- | --- |
| HTTP call to another service | `RestTemplate` or synchronous HTTP client | Spring `WebClient` with a reactive processing path |
| SQL queries | Direct JDBC | R2DBC or an appropriate reactive driver/adapter |
| Redis | Synchronous client | Reactive Redis API/client when supported |
| Timer/time delay | `Thread.sleep` | `Mono.delay` or scheduler-based timer |
| Coordinating multiple requests | Calling `.block()` per request | `Mono.zip`, `Flux.flatMap`, `then` to compose publishers |
| File read/write | Blocking filesystem API | Asynchronous API suited to the backend or controlled offloading |

**Do not just change the return type to `Mono` and call a blocking API inside.** The data path genuinely avoids holding threads only when the participating components also cooperate with non-blocking I/O or blocking has been explicitly isolated.

### Difference Between `Mono.delay` and `Thread.sleep`

~~~java
Mono<String> delayed = Mono.delay(Duration.ofSeconds(1))
    .thenReturn("done");
~~~

This pipeline registers a timer and emits `"done"` after the appropriate interval, without requiring an application thread to sleep for an entire second waiting. That does **not** mean timers are free or callbacks after a timer can never stall a scheduler; heavy transforms/tasks placed after `delay` must still obey the rule of not blocking on an unsuitable worker.

## 12. When CPU-Bound Work Is the Cause

The following situation **does not wait on the network**, yet still causes stalls if run on the event loop:

~~~java
Mono<String> expensive = Mono.just(input)
    .map(value -> cpuHeavyTransform(value));
~~~

This is an integration snippet with application-defined `input` and `cpuHeavyTransform`. When a computation takes hundreds of milliseconds, the worker has no opportunity to handle other events during that window.

You can move CPU-bound computation onto a scheduler intended for this kind of work:

~~~java
Mono<String> offloaded = Mono.just(input)
    .publishOn(Schedulers.parallel())
    .map(value -> cpuHeavyTransform(value));
~~~

`publishOn` sits **before** the computation step so the `map` callback runs on the `parallel` scheduler per Reactor's mechanism. However, this pool is also bounded. A large volume of CPU work can saturate that pool itself; you need to bound concurrency, optimize the algorithm, separate dedicated jobs, or apply bulkheads according to load needs.

Do not assume `boundedElastic` is the best place for **every** heavy task: it primarily serves to isolate blocking work that spends time waiting. CPU-heavy tasks need separate measurement and scheduling.

## 13. Backpressure, Queues, and Concurrency Are Related but Not the Same as Blocking

Reactive Streams has `request(n)` so downstream can signal how many elements it is ready to receive. That mechanism helps a cooperating source **avoid emitting beyond demand**. But backpressure cannot free an event-loop worker held by `Thread.sleep` or a synchronous JDBC call.

Example:

~~~java
Flux<Result> pipeline = Flux.fromIterable(ids)
    .flatMap(id -> callReactiveService(id), 16);
~~~

This is an integration snippet. `flatMap(..., 16)` caps the number of active inner publishers; it is not a rate limit of 16 requests/second, and it does not guarantee the system has no internal buffers. The `callReactiveService` source still needs a non-blocking contract and proper cancellation/demand propagation.

When blocking must be offloaded, coordinate **at least** the following factors:

1. **Concurrency:** how many blocking operations are started and active at the same time?
2. **Queue:** how many tasks are held when the pool/scheduler/connection pool is busy?
3. **Timeout:** how long before the client/caller stops waiting; does the timeout actually cancel downstream work?
4. **Memory:** what is the total size of pending requests, payloads, and results?
5. **Retry:** do retries amplify load right when the dependency is overloaded?
6. **Backpressure:** how faithfully does the publisher honor `request(n)` and do any operators prefetch/buffer ahead?

Do not push all work into a huge queue "so no request is lost" while ignoring RAM limits and wait times. When a dependency lacks capacity, load-shedding policies, concurrency limits, circuit breakers/bulkheads, or a suitable durable queue may be required.

## 14. Errors, Timeouts, and Cancellation

When a `Callable` inside `fromCallable` throws an exception, Reactor turns that exception into an `onError` signal:

~~~java
Mono<Result> operation = Mono.fromCallable(
        () -> blockingService.read(id))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
~~~

This is an integration snippet requiring application `Result`, `blockingService`, and `id`; import `java.time.Duration` and `reactor.core.scheduler.Schedulers`. If the operation takes longer than the timeout, `timeout` signals an error and cancels the upstream subscription. However:

- **Canceling a subscription is not guaranteed to abort physical I/O immediately.** A synchronous driver may keep holding the thread until the driver itself or the socket times out.
- If the operation has side effects, a caller-side timeout does not prove the side effect did not occur. Retries can repeat operations unless idempotency keys/transactions exist.
- Configure timeouts at the **right layers**: HTTP client, driver, connection pool, Reactor operator, and overall request each have their own meaning.
- `doFinally(signalType -> ...)` can observe `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`, but measurement/logging inside the hook must also be brief and safe for whichever scheduler executes it.

To avoid swallowing errors:

~~~java
Mono<Result> logged = operation
    .doOnError(error -> logFailure(error));
~~~

`doOnError` only observes and forwards the error. Use `onErrorResume` to produce a fallback **when business policy allows**, rather than turning every database/network failure into an empty success by default.

## 15. Diagnosis: How to Spot Blocking in WebFlux?

A slow request **is not enough** to prove the event loop is blocked. Slow networks, slow databases, CPU load, GC pauses, connection pools, DNS, buffers, and queues can all produce the same symptom. Proper evidence must be gathered.

### System-Level Observation

| Signal | May suggest | Needs to be distinguished from |
| --- | --- | --- |
| p95/p99 HTTP latency rises across multiple endpoints | Shared worker/bottleneck is stalled | DB or network having elevated latency independently |
| Event-loop pending tasks/lag increases | Callbacks are not being served promptly | CPU saturation or excessive event volume |
| Thread dump shows `reactor-http-...` thread in `Thread.sleep` / socket read / JDBC | Likely blocking directly on the event loop | Single snapshot, unverified code path |
| `boundedElastic` workers busy / long queues | Blocking workload is backing up | External connection pool or slow dependency |
| Timeouts/retries spike together | Cascading failure may be forming | Initial remote service errors |
| High CPU and hot event loop | Long computation/processing loops | GC, heavy encode/decode, synchronous logging |

Specific thread names vary by runtime and version; **do not use thread prefixes as sole evidence**. Thread dumps/Java Flight Recorder, tracing, server/client/scheduler metrics, request-correlated logs, and controlled load tests help confirm bottlenecks.

### Logging Along Pipeline Stages

~~~java
Mono<String> result = reactiveCall()
    .doOnSubscribe(s -> logThread("subscribe"))
    .doOnNext(v -> logThread("onNext"))
    .doFinally(signal -> logThread("finally"));
~~~

This is an integration snippet with application-defined `reactiveCall()` and `logThread(...)`. Thread logging helps visualize where signals are processed, but **does not guarantee every callback always runs on the same thread**. Avoid excessive synchronous logging on the event loop, since a blocking log sink itself can introduce latency.

Reactor provides `Schedulers.isInNonBlockingThread()` to check whether the current thread is marked as disallowing blocking Reactor APIs; it does **not** replace measuring processing time and is not a scanner that catches all blocking I/O.

### Tools During Testing

- **Thread dump/JFR:** inspect worker stack frames under load to find blocking I/O, lock contention, or long CPU loops.
- **Micrometer/Actuator:** track latency, in-flight requests, HTTP client, connection pool, and scheduler metrics when corresponding instrumentation is enabled.
- **BlockHound:** can help detect certain blocking calls when running in supported environments. This tool requires proper setup and JVM compatibility; do not treat it as guaranteed to catch every library/type of blocking.
- **Scripted load tests:** compare adding/removing a blocking segment, measuring throughput, p99, queues, CPU, and timeouts; avoid drawing conclusions from a single browser test request.

## 16. Testing with Reactor Test

Create `src/test/java/EventLoopTest.java` in the Gradle project from section 9. The two test dependencies are already declared there.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;

class EventLoopTest {

    @Test
    void blockingCallableRunsOnAWorkerAfterSubscription() {
        AtomicReference<Thread> worker = new AtomicReference<>();
        Thread caller = Thread.currentThread();

        Mono<String> operation = Mono.fromCallable(() -> {
            worker.set(Thread.currentThread());
            return "loaded";
        }).subscribeOn(Schedulers.boundedElastic());

        assertNull(worker.get()); // Not subscribed yet, callable has not run.

        StepVerifier.create(operation)
            .expectNext("loaded")
            .verifyComplete();

        assertNotNull(worker.get());
        assertNotSame(caller, worker.get()); // Offloaded off the test thread.
    }

    @Test
    void timerCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofMinutes(2)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(2))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void callableErrorIsPropagated() {
        Mono<String> operation = Mono.<String>fromCallable(() -> {
            throw new IllegalStateException("legacy failed");
        }).subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(operation)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "legacy failed".equals(error.getMessage()))
            .verify();
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper. **All three tests are expected to PASS.**

- Test 1 verifies that the callable **has not run before subscription** and executes on a different thread when using `boundedElastic`. It does not check the thread name because prefixes are implementation details prone to change.
- Test 2 uses `StepVerifier.withVirtualTime` instead of sleeping for two minutes in a test; it verifies timer signals without waiting full wall-clock time.
- Test 3 confirms exceptions from the blocking source still travel through the `onError` path.

**Limitations of the tests:** testing thread switching does not prove the entire WebFlux system avoids blocking; concurrency/latency testing against real servers, drivers, and dependencies is still needed to validate behavior under load.

## 17. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix direction |
| --- | --- | --- |
| Treating `Mono.fromCallable` as creating a background thread | The callable can still run on the event loop upon subscription. | Add `subscribeOn(Schedulers.boundedElastic())` near the blocking source. |
| Writing `Mono.just(blockingCall())` | Blocking happens immediately while building the publisher. | Wrap the call in `fromCallable` or use a reactive API. |
| Calling `.block()` from a WebFlux handler | Blocks the worker or is rejected by Reactor on a non-blocking thread. | Return the publisher to WebFlux; use operators to compose results. |
| Using `Thread.sleep` to wait on a timer | Holds a thread doing no useful work. | Use `Mono.delay`/an appropriate asynchronous timer. |
| Using `Schedulers.parallel()` for JDBC | Small CPU pool gets blocked waiting on I/O. | Isolate blocking on `boundedElastic` or switch to a reactive driver. |
| Placing `publishOn` after a heavy CPU transform | The preceding computation still runs on the old thread. | Switch the scheduler **before** the part to separate. |
| Offloading everything to boundedElastic and assuming it's solved | Worker queues and connection pools can still overload. | Limit concurrency, pools, timeouts; monitor queues/p99. |
| Manual `subscribe()` inside a controller | Response may return before work finishes; errors and cancellation are detached. | Return the composed `Mono`/`Flux`. |
| Thinking backpressure can free a sleeping thread | Demand does not make `Thread.sleep` finish. | Remove blocking or move it properly, and limit load. |
| Measuring only overall CPU while ignoring event-loop lag | Low CPU can still coincide with request timeouts from workers waiting on I/O. | Track p99, worker stacks, queues, connection pools, and tracing. |
| Trusting Reactor timeout to always abort synchronous I/O | The driver may keep running, and side effects may have already occurred. | Configure underlying timeouts and design retries/idempotency. |

## 18. Workflow for Investigating a Slow WebFlux Endpoint

When investigating an endpoint with an unusual p99 spike, proceed in order:

1. **Identify the runtime:** Reactor Netty or another server? How are requests dispatched and which schedulers are involved?
2. **Measure the current state:** request rate, p95/p99, errors, timeouts, event-loop lag, CPU, memory, connection pools, and thread dumps.
3. **Find where threads are held:** inspect handlers/services/operators for `block()`, `Thread.sleep`, synchronous HTTP/JDBC, locks, and long CPU sections. Confirm with stacks/traces instead of guessing from method names.
4. **Fix at the source first:** use WebClient, R2DBC, or a non-blocking client where suitable. If it cannot be changed yet, place `fromCallable(...).subscribeOn(boundedElastic())` right at the blocking API boundary.
5. **Limit load:** set sensible concurrency, pool sizes, and queues; configure timeouts at the right layers and curb retry storms.
6. **Re-test:** compare metrics before/after under the same load profile, including slow downstream services, large payloads, cancellations, and errors. Check latency of other endpoints sharing the event-loop workers.
7. **Keep the reactive contract:** handlers return publishers; avoid hidden `subscribe()`/`block()` calls in application libraries and do not ignore error signals.

**Remember:** the event loop is effective because threads can quickly return to the processing loop after registering I/O work. Blocking forces threads to sit idle, affecting many connections sharing the worker. In Spring WebFlux, **use non-blocking APIs whenever possible**, isolate unavoidable synchronous calls with `boundedElastic` under load limits, and measure the real system to confirm results.

## References

- Spring Framework — WebFlux, overview and concurrency model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient and synchronous/reactive usage: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — FAQ on wrapping synchronous blocking calls: https://projectreactor.io/docs/core/release/reference/faq.html
- Project Reactor — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
