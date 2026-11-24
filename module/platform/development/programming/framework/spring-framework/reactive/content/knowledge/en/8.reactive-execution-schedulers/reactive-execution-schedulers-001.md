# Reactor Does Not Automatically Create a New Thread for Every Mono or Flux

## 1. Core Concept to Grasp

In **Spring WebFlux**, `Mono<T>` represents a result with **0 or 1 element**, while `Flux<T>` represents **0 to many elements**. These two types describe **signal streams and asynchronous processing**, but **they do not mean Reactor creates a new Java thread for each `Mono`, each `Flux`, or each request**.

A simple operator chain can execute **completely synchronously on the very thread that calls `subscribe()`**. The thread only changes when there is an asynchronous source, an operator that uses a scheduler, or when the developer explicitly specifies a context switch using mechanisms such as `subscribeOn` and `publishOn`.

This matters because confusing *publisher*, *subscription*, *thread*, and *scheduler* leads to common mistakes: assuming `Mono.fromCallable` automatically runs on a worker, blocking the event loop with `Thread.sleep` or JDBC, creating a scheduler per request, or assuming every part of a pipeline runs on the same thread.

**Four concepts to distinguish:**

| Concept | Meaning | Does it imply a new thread? |
| --- | --- | --- |
| `Mono<T>`, `Flux<T>` | Publisher describing a source and a signal processing chain | **No** |
| Subscription | A single registration of a subscriber to a publisher; starts processing flow when demand exists | **No** |
| Java thread | Thread of execution for Java code at a given moment | A publisher may run on an existing thread or move across multiple threads |
| Reactor `Scheduler` | Mechanism for scheduling work onto an execution context (current thread, thread pool, etc.) | Does not necessarily create a dedicated thread per publisher |

A `Flux` can emit a million elements **sequentially on a single thread**, whereas a single `Mono` can pass through **multiple threads** due to I/O steps or `publishOn`. The number of elements and the number of threads are two different quantities.

## 2. Pipelines Are Declared First, Executed on Subscription

Most Reactor operators are **lazy**: they describe a transformation chain, and data processing begins when there is a subscriber. However, not **every expression when building a publisher** is lazy; an argument passed to `Mono.just(...)` is evaluated according to Java rules at the time the method is called.

Example:

~~~java
// Illustrative snippet; requires reactor-core and Mono import.
Mono<Integer> numbers = Mono.just(3)
    .map(n -> n * 2)
    .filter(n -> n > 0);

// No onNext has been processed by the operators above yet.
// On subscribe, the just source emits 3, map produces 6, and filter keeps 6:
numbers.subscribe(System.out::println);
~~~

If `subscribe()` is called from the `main` thread, with `Mono.just` and these synchronous operators, `map`, `filter`, and the consumer usually execute **on the `main` thread itself**. Reactor does not launch `new Thread(...)` for each step.

The following statements are easily misunderstood:

~~~java
Mono<String> a = Mono.fromCallable(() -> blockingRead());
Mono<String> b = Mono.just(blockingRead());
~~~

This is an illustrative snippet with a hypothetical `blockingRead()` method:

- For `a`, the call to `blockingRead()` is **deferred until subscription**; however, without `subscribeOn` or another scheduler, it can still **block the subscribing thread directly**.
- For `b`, Java calls `blockingRead()` **right when constructing `Mono.just(...)`**, even before there is a subscriber.
- Neither **automatically creates a new thread** just because the result is wrapped in a `Mono`.

To isolate a blocking operation, an explicit scheduling decision is required; later sections use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

## 3. Default Rule: Synchronous Sources Run on the Subscribing Thread

With synchronous sources such as `Flux.just`, `Flux.range`, `Mono.just`, or `Mono.fromSupplier`, and operators that do not switch schedulers (`map`, `filter`, `doOnNext`), signals are typically emitted and processed **on the thread calling `subscribe`**.

~~~text
thread calling subscribe()
    │
    ▼
Flux.range(1, 3)
    │   onNext(1), onNext(2), onNext(3)
    ▼
map(n -> n * 10)
    │   10, 20, 30
    ▼
filter(n -> n >= 20)
    │   20, 30
    ▼
Subscriber.onNext(20), onNext(30), onComplete
    └── Same thread if there is no async/scheduler boundary
~~~

`Flux.range(1, 3)` does not create three threads; it only emits **three elements**. Nor does the `map` operator automatically turn each element into an independent task.

However, one cannot state that "**every** chain without `publishOn` runs on the subscribing thread": an **already asynchronous source** can emit callbacks on a thread owned by an external library, Reactor Netty, or a default scheduler. For example, `Flux.interval`, `Mono.delay`, a `WebClient` source, or a `Mono.fromFuture` signal may complete on another thread. Therefore, the accurate conclusion is: **Reactor does not automatically allocate a new thread per Mono/Flux; the execution context depends on the source, operators, and schedulers**.

## 4. `publishOn`: Changing the Thread Processing Downstream Signals

`publishOn(scheduler)` places a boundary to **re-emit downstream signals** on a worker of the specified scheduler. Operators before it continue running in the current upstream context; operators after it typically run on the chosen worker **until another source/operator switches context again**.

~~~java
// Illustrative example; requires importing Flux and Schedulers.
Flux.range(1, 3)
    .map(n -> n * 10)                 // Upstream: subscribing thread
    .publishOn(Schedulers.parallel()) // Scheduling boundary
    .map(n -> n + 1)                  // Downstream: parallel scheduler worker
    .subscribe(System.out::println); // Callback runs on the downstream context
~~~

`publishOn` **does not create one thread per element**. For a single subscription under the Reactive Streams contract, `onNext` signals are delivered sequentially to the subscriber; `publishOn` selects a worker to serialize the downstream signals. Nor does the name `Schedulers.parallel()` **mean** that the three elements above automatically run concurrently across three cores.

Multiple `publishOn` calls can be used when multiple scheduling stages are needed:

~~~java
// Structural illustration; stageA/stageB need to be implemented.
flux
    .publishOn(Schedulers.parallel())
    .map(this::stageA)
    .publishOn(Schedulers.boundedElastic())
    .map(this::stageB);
~~~

Each `publishOn` incurs scheduling and signal-buffering overhead; do not add it arbitrarily for every `map`. For a blocking task, it is usually preferable to place that work directly in a `fromCallable` source and schedule it with `subscribeOn(boundedElastic)`, rather than letting it accidentally block the event loop before reaching `publishOn`.

## 5. `subscribeOn`: Scheduling Subscription and Source Work

`subscribeOn(scheduler)` changes the **subscription context going upstream toward the source**. For cold synchronous sources such as `Mono.fromCallable`, `Mono.fromSupplier`, and `Flux.range`, this usually determines the thread that executes the source work and many synchronous operators that follow.

~~~java
// Illustrative snippet; fetchBlocking() is a hypothetical blocking API.
Mono<String> response = Mono.fromCallable(() -> fetchBlocking())
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim);
~~~

When downstream subscribes, the blocking fetch call runs on a `boundedElastic` worker instead of occupying the event loop through which the initial request arrived. Without an additional async boundary or `publishOn`, `map(String::trim)` also typically runs on that worker.

**Two placement rules to distinguish:**

- `publishOn`: **its position in the pipeline determines** which operators lie past the thread-switching boundary.
- `subscribeOn`: affects the subscription flow toward the source **regardless of where it appears in the chain**, though it should be placed right after the source for clarity. With multiple `subscribeOn` calls, the call **closest to the source** generally takes primary effect for scheduling subscription to the source; adding more can cause unnecessary thread hops.
- A `publishOn` placed after `subscribeOn` can still change the thread of operators downstream from it. A `subscribeOn` **does not permanently lock** the entire pipeline to one thread.

Symbolic comparison:

~~~text
Synchronous source Flux ── map(A) ── publishOn(S1) ── map(B) ── Subscriber
       source thread         |          worker S1           worker S1

Synchronous source Flux ── subscribeOn(S1) ── map(A) ── Subscriber
          worker S1                    worker S1             worker S1
~~~

The diagram shows the typical path of a synchronous source. For a source with its own scheduler/multiple callbacks, base reasoning on how that source actually behaves rather than assuming `subscribeOn` will "pull" every asynchronous callback onto a single worker.

## 6. Commonly Used Schedulers

Reactor uses the `Scheduler` abstraction to organize execution contexts. Many schedulers can **share or reuse threads**, and are not equivalent to calling `new Thread` for every subscription.

| Scheduler | Characteristics | When suitable |
| --- | --- | --- |
| `Schedulers.immediate()` | Runs work **directly on the current thread** | When no thread switch is needed |
| `Schedulers.single()` | Shared scheduler with a single worker/thread | Work needing a single sequential execution stream; with awareness of shared impact |
| `Schedulers.newSingle("name")` | Creates a single-thread scheduler managed by you | When dedicated resources with a clear lifecycle are needed; **dispose** when finished |
| `Schedulers.parallel()` | Bounded worker pool, mainly sized by CPU count | **Short CPU-bound**, non-blocking processing steps |
| `Schedulers.boundedElastic()` | Bounded worker pool designed to isolate **blocking** tasks | Blocking JDBC/SDKs, file operations, or synchronous legacy APIs when no non-blocking option exists |
| `Schedulers.fromExecutorService(executor)` | Uses an application-managed executor | When integrating an existing thread pool mechanism with managed lifecycle |

`boundedElastic` has bounded thread counts and queues, not infinite resources. If the blocking workload is too large, it can still fill up, increase latency, or cause resource exhaustion. Choosing `parallel` for a long blocking operation occupies the scarce workers intended for CPU work and easily slows down other pipelines.

**Do not create `Schedulers.newSingle(...)` or `newParallel(...)` per HTTP request**. Arbitrary scheduler creation wastes threads/resources. Shared schedulers via `Schedulers.parallel()` and `Schedulers.boundedElastic()` are usually sensible defaults; self-created schedulers must have an application-level lifecycle and corresponding cleanup.

Some operators/sources choose a default scheduler themselves: for example, `Flux.interval(Duration)` and `Mono.delay(Duration)` use Reactor's timing scheduler (defaulting to `Schedulers.parallel()` in common APIs). This is an **asynchronous source**, not proof that every `Flux` gets a new thread automatically.

## 7. Runnable Java 17+ Example with Deterministic Output

The example below clarifies three cases: default synchronous pipeline, `publishOn` switching downstream, and `subscribeOn` switching source work. To avoid depending on the thread name Maven assigns to `main`, the program prints **`caller`** if on the initial thread, and **`worker`** otherwise. It uses only one dedicated `newSingle` scheduler for the demo, so it does not create a new thread for every `Mono`.

Directory structure:

~~~text
reactor-thread-demo/
├── pom.xml
└── src/main/java/ReactorThreadDemo.java
~~~

File `pom.xml` (Reactor Core 3.8.8, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-thread-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/ReactorThreadDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ReactorThreadDemo {
    private static Thread callerThread;

    private static void where(String stage) {
        String kind = Thread.currentThread() == callerThread
                ? "caller"
                : "worker";
        System.out.println(stage + " @ " + kind);
    }

    public static void main(String[] args) {
        callerThread = Thread.currentThread();

        // A. No scheduler: map and consumer run on caller.
        Mono.just(2)
            .map(n -> {
                where("sync map");
                return n * 3;
            })
            .doOnNext(n -> where("sync onNext"))
            .block();

        Scheduler worker = Schedulers.newSingle("lesson");
        try {
            // B. Synchronous source on caller; downstream after publishOn on worker.
            Mono.fromSupplier(() -> {
                    where("source before publishOn");
                    return 10;
                })
                .publishOn(worker)
                .doOnNext(n -> where("after publishOn"))
                .block();

            // C. subscribeOn moves subscription and source to worker.
            Mono.fromSupplier(() -> {
                    where("source with subscribeOn");
                    return 20;
                })
                .subscribeOn(worker)
                .doOnNext(n -> where("after subscribeOn"))
                .block();
        } finally {
            worker.dispose();
        }
    }
}
~~~

Run from the `reactor-thread-demo` directory with Maven and JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ReactorThreadDemo
~~~

**Program output** (additional Maven lines may appear depending on environment configuration):

~~~text
sync map @ caller
sync onNext @ caller
source before publishOn @ caller
after publishOn @ worker
source with subscribeOn @ worker
after subscribeOn @ worker
~~~

Explanation:

1. In branch A, `Mono.just` + `map` + `doOnNext` has no scheduler: **the thread calling `block()`/subscribe** processes all data synchronously.
2. In branch B, `Mono.fromSupplier` emits the value on **caller**, after which `publishOn(worker)` switches the downstream portion to a worker. The source **is not moved to the worker** just because `publishOn` appears downstream.
3. In branch C, `subscribeOn(worker)` places subscription and execution of the synchronous source onto the worker. `doOnNext` encounters no other boundary, so it also runs on the worker.
4. `block()` here is only used in a **console application** to wait for the demo to finish and keep output ordered. In a Spring WebFlux application, do not call `block()` on the event loop.

The actual thread is managed by Reactor and has an internal name; the `caller/worker` labels help demonstrate relative placement. The line `worker.dispose()` releases the dedicated scheduler created by the demo.

## 8. Distinguishing Asynchronous, Non-Blocking, and Parallel Execution

These terms are easily conflated:

- **Asynchronous:** results may arrive later, from another callback/event loop/scheduler; the caller does not necessarily wait directly.
- **Non-blocking:** work can temporarily yield the thread while waiting for I/O and resume when signaled, avoiding holding a thread just to sleep/wait.
- **Concurrent:** multiple tasks can exist and make interleaved progress, not necessarily at the exact same instant across multiple CPUs.
- **Parallel:** multiple pieces of work genuinely execute simultaneously across multiple processing units.
- **Reactive:** the Publisher/Subscriber model with signals and `request(n)` demand management; **it does not by default guarantee** the other three properties for every piece of code.

For example, `Flux.range(1, 100)` is reactive but typically runs synchronously. `Flux.interval(...)` involves time-based events and a scheduler. `WebClient` typically uses asynchronous I/O; while waiting on the network, the event loop can manage many more connections. `map(this::expensiveCpuWork)` still consumes CPU on the thread handling the signal; merely changing the type to `Flux` does not make an algorithm faster.

Even the following snippet:

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuWork);
~~~

does **not automatically spread 100 elements across multiple cores**. For a single subscription, `publishOn` switches downstream to a single worker and delivers `onNext` sequentially. If you have an independent CPU workload genuinely worth distributing, Reactor offers `parallel().runOn(Schedulers.parallel()).map(...).sequential()` or combining `flatMap` with scheduled inner publishers; each approach has overhead and affects result ordering, so choose only after measuring.

Nor does `flatMap` mean "automatically spawn threads": it allows **multiple active inner publishers concurrently**, while which execution threads are used depends on the inner sources and the schedulers they use. `concatMap` maintains sequential processing order, whereas `flatMap` may emit results in an order different from the source order.

## 9. Where Does the Event Loop Come From in Spring WebFlux?

When running on the **Spring WebFlux + Reactor Netty** stack, the server has a group of **event-loop threads** to accept connections and handle I/O. One event loop can serve many requests/connections when requests spend most of their time **waiting on non-blocking I/O**. Receiving a WebFlux request does not mean the server creates a separate thread to run all `Mono` or `Flux` instances of that request.

High-level flow:

~~~text
HTTP client
    │
    ▼
Reactor Netty event loop
    │
    ▼
WebFlux handler / controller returns Mono or Flux
    │
    ├── Synchronous operators run on the signal-emitting thread
    │   (possibly the current event loop)
    │
    ├── Non-blocking WebClient / R2DBC waits for I/O
    │       └── Result signals arrive from the event loop / driver
    │
    └── subscribeOn / publishOn (if configured)
            └── Moves part of the work to a Scheduler worker
    │
    ▼
WebFlux writes the HTTP response when data arrives
~~~

An important consequence: **do not block the event loop** with `Thread.sleep`, long lock waits, blocking JDBC, large synchronous file reads, synchronous HTTP calls, or `Mono.block()` on the request-handling path. Even a few blocking operations can slow down many other requests because event-loop threads are shared.

Nor should you assume that every operator in a request sees the same `Thread.currentThread()` or can access `ThreadLocal` as in synchronous servlet processing. When switching threads, thread-bound context may not follow. For business context across a reactive chain, use **Reactor Context** and the framework's propagation mechanisms rather than relying solely on `ThreadLocal`.

## 10. Integrating Blocking APIs Properly

If you must use a synchronous library inside a reactive service, wrap the call with `fromCallable` to defer it until subscription, then use `subscribeOn(Schedulers.boundedElastic())` to isolate the event-loop thread:

~~~java
// Illustrative service snippet; legacyClient and Result are implemented in the project.
Mono<Result> loadLegacy(String id) {
    return Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

This **isolates blocking I/O onto an appropriate pool**; it does not "turn a blocking library into a non-blocking API." The `boundedElastic` worker is still occupied while waiting on the call; threads and queues are bounded. You still need concurrency limits, timeouts, connection pools, and metrics observation to avoid saturation.

Compare with the anti-patterns:

~~~java
// Wrong: fetch runs immediately when Mono.just is created, possibly on the event-loop.
Mono<Result> wrong = Mono.just(legacyClient.fetch(id));

// Wrong when called on the event-loop: Mono.fromCallable does not switch threads by itself.
Mono<Result> alsoWrong = Mono.fromCallable(() -> legacyClient.fetch(id));

// More appropriate if no reactive client is available:
Mono<Result> adapted = Mono.fromCallable(() -> legacyClient.fetch(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

These snippets illustrate concepts, not standalone runnable Java files. `Mono.fromCallable` is lazy, but **lazy ≠ running on another thread**. Attaching `subscribeOn` ensures the cold synchronous source is scheduled on the chosen scheduler upon subscription.

With a genuinely non-blocking API such as `WebClient` or an R2DBC repository, there is no need to wrap it in `boundedElastic` by default. Let the asynchronous API emit signals via its own mechanism; switch schedulers only when there is a real technical reason (blocking adapter, separating a CPU stage, etc.).

## 11. Cases to Observe in Practice

| Phenomenon | Correct conclusion | How to check / fix |
| --- | --- | --- |
| `Mono.just(1).map(...)` runs on `main` | Normal: synchronous source and operators use the subscribing thread | Add `doOnNext` to log the thread |
| `Mono.fromCallable(blockingCall)` slows WebFlux requests | `fromCallable` does not automatically provide a worker | Use `subscribeOn(boundedElastic)`, limit load |
| After `publishOn(parallel)`, multiple `map` calls still use one worker | `publishOn` switches downstream but does not dispatch each item to a different thread | Use parallelization only when truly needed |
| `Flux.interval` emits on another thread without `publishOn` | The source has its own timing scheduler | Check the source's documentation and scheduler configuration |
| `subscribe()` returns before `onNext` occurs | Source/callback is asynchronous so work continues | Return the publisher to WebFlux; in console demos wait via test/latch/`block` |
| Many requests, fewer threads than requests | Non-blocking event loop uses shared threads | Monitor event-loop latency, I/O, CPU, and pools |
| Creating a scheduler per request | Thread/resource bloat, hard to clean up | Use shared schedulers or manage a dedicated lifecycle |
| `ThreadLocal` is lost across async boundaries | Operators do not necessarily run on the same thread | Use Reactor Context or appropriate context propagation |

To observe behavior, you can temporarily add `doOnSubscribe(s -> ...)`, `doOnNext(v -> ...)`, `doOnError`, `doFinally`, or `log()`. Remember that `doOnSubscribe` shows where subscription is observed, not necessarily the same thread as **every** subsequent `onNext`. Multiple async boundaries can exist within the same pipeline.

## 12. Common Misconceptions

1. **"Every `Mono` is a thread."** False. `Mono` is a 0..1 publisher; threads depend on the source and scheduling.
2. **"Every `Flux` has a thread; every Flux element adds a thread."** False. A large `Flux.range` can emit all values synchronously on the caller.
3. **"`subscribe()` always creates a background task."** False. With a synchronous source, `subscribe()` can run the consumer and complete right before returning. With an async source, signals may arrive later.
4. **"`fromCallable` is non-blocking."** False. It defers execution; the call can still block and needs an appropriate scheduler if inside WebFlux.
5. **"`publishOn` always changes the source's thread."** False. It switches **downstream signals** starting from where the operator is placed.
6. **"`subscribeOn` only affects everything written below it."** False. It primarily affects the subscription flow going toward the source; its syntactic placement is not like `publishOn`.
7. **"Simply using `Schedulers.parallel()` splits all computations across multiple cores."** False. A single `publishOn(parallel())` on one subscription does not parallelize elements automatically.
8. **"Non-blocking Reactor can call sync JDBC/HTTP inside the event loop."** False from a performance standpoint: that code still blocks the shared thread and reduces throughput.
9. **"Switching threads does not affect state."** False when using mutable shared state or `ThreadLocal`. You must identify thread boundaries and how state/context is shared or propagated.
10. **"All thread pools are infinite."** False. `boundedElastic` and `parallel` are bounded; high load can cause queuing, increased latency, or rejections.
11. **"The more scheduler switches, the faster it gets."** False. Scheduling also has overhead and can make a pipeline slower and more complex.
12. **"A request must always run on one thread from start to finish."** False in WebFlux: the event loop, reactive client callbacks, and `publishOn/subscribeOn` can validly produce multiple execution contexts.

## 13. Self-Check

**Question 1.** Does `Mono.just(5).map(n -> n + 1).subscribe(...)` create a new worker by default? **No.** If the source and operators are synchronous, they usually run on the thread calling subscribe.

**Question 2.** Is `Mono.fromCallable(() -> jdbcQuery())` safe to place directly on the event loop? **No.** `jdbcQuery()` still blocks when the subscription executes. Use `subscribeOn(Schedulers.boundedElastic())`, or switch to an appropriate non-blocking driver.

**Question 3.** What does `publishOn(Schedulers.parallel())` in the middle of a pipeline affect? **Mainly the downstream segment after `publishOn`** up to any subsequent scheduling boundary.

**Question 4.** What does `subscribeOn(Schedulers.boundedElastic())` mean for a `fromCallable` source? **It schedules subscription and the synchronous source work on a scheduler worker**, avoiding holding the caller while the callable waits.

**Question 5.** Can `Flux.interval(Duration.ofSeconds(1))` emit from another thread without `publishOn`? **Yes.** It is a source with its own timing scheduler, defaulting to the mechanism specified by Reactor.

**Question 6.** Is the number of WebFlux requests equal to the number of Netty threads? **No.** Event-loop threads serve many connections/requests in a non-blocking model, though blocking must be avoided and bottlenecks monitored.

**Question 7.** Should you create `Schedulers.newSingle` inside a controller on every request? **No.** Use shared schedulers or a lifecycle-managed instance that is properly disposed.

**Final takeaway:** Reactive describes **how signals are processed and work is scheduled**, without allocating a dedicated thread per `Mono`/`Flux`. Synchronous sources typically use the **subscribing thread**; `publishOn` switches **downstream processing**, `subscribeOn` switches **subscription/source**, and some I/O or timer sources are already asynchronous. In Spring WebFlux, keep the **event loop non-blocking** and use a Scheduler only when there is a specific technical reason.

**Official documentation:** [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html), [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/index.html).