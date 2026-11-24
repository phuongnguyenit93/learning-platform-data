# `single`, `parallel`, and `boundedElastic`: Choosing Execution Threads in Project Reactor

## 1. Goal and Context

In Spring Framework Reactive and Spring WebFlux, `Flux<T>`/`Mono<T>` describe data and signal streams, yet **simply using reactive types does not spawn new threads automatically**. By default, most operators keep running on whatever thread emitted the previous signal. When you want to move execution elsewhere, you can use Project Reactor's `Scheduler` abstraction.

This lesson focuses on three common Schedulers:

- `Schedulers.single()` — a shared single thread, suited for short tasks that need sequential ordering.
- `Schedulers.parallel()` — a bounded group of workers aimed at fast, **non-blocking** computational work that can handle multiple independent tasks across different threads.
- `Schedulers.boundedElastic()` — a boundedly elastic group of workers suited when you must integrate **synchronous APIs that can block threads**, such as traditional JDBC libraries, blocking file operations, or legacy SDKs.

You need to distinguish **Scheduler**, `publishOn`, `subscribeOn`, `Flux.parallel()`, and practical questions: which thread does a pipeline run on, where do threads switch, does it actually run concurrently, and when to avoid blocking.

## 2. What Is a Scheduler and Why Does Reactor Need It?

A `Scheduler` is responsible for scheduling task execution. Its role is close to `ExecutorService`, but it is Reactor's own abstraction, also used for time-based operations, scheduling, and virtual-time testing. `Schedulers` is the factory class providing common options.

With the following code, creating a Publisher does not immediately move work to the background:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .map(i -> i * 2);

// Only runs upon subscription; by default usually uses
// the signal-emitting thread or the thread calling subscribe().
numbers.subscribe(System.out::println);
~~~

Without an operator specifying a Scheduler and when the source does not manage threads itself, calling `subscribe` on the `main` thread usually makes `map` and `onNext` run on `main` as well. However, one should not state that **every** `Flux` always runs on the thread calling `subscribe`: some asynchronous sources or operators (for example `Flux.interval`) use a Scheduler of their own.

Key concepts:

| Concept | Meaning |
| --- | --- |
| **Assembly** | When building `Flux`/`Mono` and chaining operators; most data has not been emitted yet |
| **Subscription** | When a Subscriber registers; the signal stream can begin |
| **Worker** | Object provided by a Scheduler to execute scheduled tasks |
| **Scheduler** | Mechanism for selecting and scheduling workers/threads for work |
| **Thread** | JVM/OS execution unit (or virtual thread on supported Java versions) |
| **Non-blocking** | Work that does not hold a thread solely waiting for I/O to finish |
| **Blocking** | Work that holds a thread while waiting, such as `Thread.sleep`, synchronous I/O, and many JDBC libraries |

**A Scheduler is not a performance guarantee.** Moving thread-blocking work to a separate pool can protect the event loop, yet it still consumes threads, connections, memory, and can increase waiting time.

## 3. `Schedulers.single()`: One Shared Thread

### 3.1. Characteristics

`Schedulers.single()` returns a **shared Scheduler** with one reusable thread for callers. Tasks submitted by different subscribers to the same Scheduler contend on that thread and execute sequentially according to scheduling. `single` is suited for:

- Light, short work where centralized execution on one thread is desired.
- Callback chains where concurrent execution across multiple workers at the scheduled stage must be avoided.
- Simple state-recording steps already designed to be sequential with short duration.

~~~java
Mono<String> report = Mono.fromSupplier(() ->
    "thread=" + Thread.currentThread().getName()
).subscribeOn(Schedulers.single());
~~~

On subscription, `fromSupplier` runs on the `single` worker; default thread names typically carry the `single-` prefix (e.g., `single-1`). **Numeric suffixes are not an application contract** and must not be used for business decisions.

Because this Scheduler shares **one** thread, if one task blocks the thread for a long time, other tasks using `single` must wait. Therefore **do not** place blocking JDBC, long `Thread.sleep`, `block()`, or very heavy CPU work onto `Schedulers.single()`.

### 3.2. Shared `single()` vs. `newSingle(...)`

~~~java
Scheduler shared = Schedulers.single();
Scheduler dedicated = Schedulers.newSingle("audit");
~~~

- `Schedulers.single()` is a shared instance managed by Reactor, not creating a separate thread per factory call.
- `Schedulers.newSingle("audit")` creates an independent Scheduler for a specific application scope. The creator **must manage its lifecycle** and call `dedicated.dispose()` when no longer needed; do not create a new one per request and forget to dispose.
- Sharing `single()` does not guarantee all application state updates are thread-safe. Threads outside the Scheduler can still access state; shared state still requires proper synchronization/ownership conventions.

## 4. `Schedulers.parallel()`: Bounded Pool for Fast, Non-Blocking Work

### 4.1. Characteristics

`Schedulers.parallel()` is a shared Scheduler with a fixed group of workers, defaulting to a worker count based on processors reported by the JVM (usually `Runtime.getRuntime().availableProcessors()`; configurable via Reactor properties). It is optimized for fast, computational work that **does not block threads**.

~~~java
Mono<Integer> result = Mono.fromSupplier(() -> 12 * 12)
    .subscribeOn(Schedulers.parallel());
~~~

Upon subscription, the computation is scheduled on a `parallel` worker. Multiple independent subscriptions or rails **can** use different workers, depending on processor count and the actual Scheduler.

### 4.2. `publishOn(parallel())` Does Not Automatically Parallelize Every Item

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::calculate)
    .subscribe();
~~~

This is an **illustrative snippet inside an instance with a `calculate` method**, not a standalone Java program. A single `publishOn` typically selects **one worker per subscription** and sequentially passes downstream signals through that worker. Consequently, a `map` chain after `publishOn(parallel())` **does not automatically distribute 100 elements across multiple CPU cores**.

To split data into rails capable of concurrent processing:

~~~java
Flux<Integer> squared = Flux.range(1, 100)
    .parallel(4)                      // Split into 4 rails
    .runOn(Schedulers.parallel())     // Schedule a worker for each rail
    .map(i -> i * i)
    .sequential();                    // Merge rails back into a Flux
~~~

`parallel(4)` by itself only creates a `ParallelFlux`, which is **not enough** to ensure multiple threads; `runOn` attaches a Scheduler to the rails. And even when 4 rails are declared, actual threads used still depend on the worker pool, CPU resources, and current load. Results merged via `sequential()` **should not be assumed to preserve input order in every concurrent case** if the application depends on ordering; review and verify ordering requirements.

Do not place long synchronous I/O tasks on `Schedulers.parallel()`: blocking occupies CPU workers and affects other streams.

### 4.3. `parallel()` vs. `newParallel(...)`

`Schedulers.parallel()` is a shared pool. `Schedulers.newParallel("compute", 4)` creates a dedicated pool of up to 4 workers for a subsystem when resource separation is truly needed; you must `dispose()` self-created pools at the end of their lifecycle. Adding threads arbitrarily does not give the machine more CPU cores; if pure CPU work already saturates cores, raising concurrency may only add context switching.

## 5. `Schedulers.boundedElastic()`: Handling Blocking Work Within Bounds

### 5.1. When to Use It?

`boundedElastic` serves relatively long-running tasks, especially **APIs without a reactive/non-blocking option**:

- Traditional JDBC libraries or synchronous legacy SDKs.
- Reading files with blocking APIs when no suitable asynchronous solution exists.
- Calling synchronous code provided by an external library.
- Performing I/O-waiting work that cannot yet be replaced with a reactive driver/client.

The standard pattern is to **wrap the blocking call so it truly executes only on subscribe**, then apply `subscribeOn(Schedulers.boundedElastic())`:

~~~java
Mono<Customer> customerMono = Mono
    .fromCallable(() -> legacyJdbcRepository.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is an **illustrative snippet in an application with `Customer`, `legacyJdbcRepository`, and `customerId`**, not a standalone program. `fromCallable` defers calling the repository until subscription; `subscribeOn` shifts **source work** onto the boundedElastic pool.

**Common anti-pattern**:

~~~java
Mono<Customer> wrong = Mono
    .just(legacyJdbcRepository.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Here Java calls `findById` **right when constructing the Publisher**, before the Scheduler has any chance to relocate the work. If this line runs on an event loop, it can still block the event loop. Use `fromCallable` or `defer` at the right moment.

### 5.2. Why Is It Called Bounded + Elastic?

With the standard platform-thread implementation, `boundedElastic` expands and reuses worker threads flexibly within **bounds**. By default in current Reactor 3.x:

- The backing-thread cap is typically `10 × available processors`; changeable via `reactor.schedulers.defaultBoundedElasticSize`.
- When threads are busy, work is queued; the default queue limit is roughly **100,000 tasks per backing thread**, not an infinite queue guarantee. Configurable via `reactor.schedulers.defaultBoundedElasticQueueSize`.
- Idle worker threads in the platform-thread implementation can be evicted after roughly 60 seconds.
- If scheduling limits are exceeded, Reactor may reject additional tasks (`RejectedExecutionException` or the corresponding scheduling error).

These defaults are **configuration and implementation details**, and should not be hardcoded into business expectations. In real deployments, check the Reactor version, JVM, processor count, and configured properties.

Important note: `boundedElastic` **does not turn JDBC into non-blocking communication**. A thread is still blocked during the query; the Scheduler only isolates that blocking from threads that must remain responsive. Connection pools and database limits remain independent constraints. If you already use R2DBC or non-blocking `WebClient`, do not wrap them in boundedElastic merely because they return `Mono`.

### 5.3. Java 21 Virtual Threads Are an **Optional** Mode

Since Reactor 3.6.0, applications running **Java 21+** can enable a shared `boundedElastic` implementation that uses a **new virtual thread per task**, via the JVM system property:

~~~text
-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
~~~

This mode only takes effect when the environment and configuration support it, and is disabled by default; it does not apply to the Java 17 program in the hands-on section. Virtual threads reduce the cost of holding platform threads for many blocking tasks, yet **do not remove concurrency, queue, I/O, connection-count, or deadline limits**. In virtual-thread mode, there is no traditional boundedElastic idle platform-thread pool; each task runs on a new virtual thread according to the implementation's bounding mechanism.

### 5.4. `boundedElastic()` Is Also a Shared Scheduler

`Schedulers.boundedElastic()` returns a shared Scheduler managed by Reactor. You can create a dedicated Scheduler if resource isolation and custom caps are required:

~~~java
Scheduler legacyPool = Schedulers.newBoundedElastic(
    8,       // Maximum backing threads
    100,     // Maximum waiting tasks per backing thread
    "legacy" // Thread name prefix
);
// Use legacyPool for sources needing isolation.
// When the application stops: legacyPool.dispose().
~~~

Create a dedicated pool only with a clear operational reason; creating many large pools can defeat the goal of controlling total thread count.

## 6. Decision Table: Which Scheduler to Choose?

| Question | `single()` | `parallel()` | `boundedElastic()` |
| --- | --- | --- | --- |
| Thread count | One **shared** thread | Fixed pool, roughly CPU core count by default | Elastic with thread and queue caps |
| Suitable work | Short, needing centralized/sequential execution | Fast computation, non-blocking | Integrating blocking I/O / legacy code |
| Should you call `Thread.sleep`, `block()`, blocking JDBC? | **No** | **No** | Can be used when needed, yet still consumes resources |
| Can multiple subscriptions share threads? | No, same single thread | Yes | Yes, up to limits |
| Does it guarantee Flux items automatically run concurrently? | No | No, requires proper rail/flatMap design | No |
| Overload risk | One slow task makes all others wait | CPU workers occupied; latency rises | Thread/queue caps, delays or task rejections |
| How to create a custom one | `newSingle(name)` | `newParallel(name, n)` | `newBoundedElastic(cap, queueCap, name)` |

**Practical rule:** prefer genuinely non-blocking pipelines; switch threads only with good reason. If forced to use a blocking API, isolate that call on boundedElastic; do not try to "fix" it with single/parallel.

## 7. `subscribeOn` and `publishOn`: Where Does the Scheduler Apply?

The three Schedulers above are **where work runs**. Two key operators determine how those execution locations attach to the pipeline.

### 7.1. `subscribeOn(scheduler)`: Shifts Subscription and Source Execution

~~~java
Mono<String> source = Mono.fromCallable(() -> {
    return "source thread=" + Thread.currentThread().getName();
}).subscribeOn(Schedulers.boundedElastic());
~~~

For a `fromCallable`-style source, the source invocation runs on the chosen Scheduler, making it suitable for offloading blocking APIs. `subscribeOn` is usually placed close to the source so readers clearly see where the source runs. It affects the backward subscription flow to the source and the source's signal-emission work, unlike `publishOn`.

Having `subscribeOn` **does not cause multiple subscriptions** and does not turn a source into a hot Publisher. Adding multiple `subscribeOn` calls in the same chain leaves only one effective position directly governing subscription to the source and can introduce redundant thread hops; avoid stacking unnecessary `subscribeOn` calls.

### 7.2. `publishOn(scheduler)`: Changes Where Downstream Signals Are Processed

~~~java
Flux.range(1, 3)
    .doOnNext(i -> logThread("before", i))
    .publishOn(Schedulers.parallel())
    .doOnNext(i -> logThread("after", i));
~~~

`logThread` is an application-defined illustration helper. Before `publishOn`, hooks run in the previous context; afterward, downstream hooks are switched onto a `parallel()` worker until another boundary is encountered.

One `publishOn` delivers `onNext` signals to **a single Subscriber** sequentially as required by Reactive Streams. `publishOn(parallel())` does not mean "one thread per `onNext`." It typically uses an internal queue/prefetch, so examine both backpressure and memory when a pipeline has mismatched production/consumption rates.

### 7.3. Combining Both Boundaries

~~~text
subscribe() on caller thread
        |
        v
Mono.fromCallable(...) -- subscribeOn(boundedElastic)
        |                   (source runs on boundedElastic)
        v
map(...)                 -- runs on boundedElastic
        |
        v
publishOn(parallel)
        |                   (switches signals to parallel worker)
        v
map(...)                 -- runs on parallel
        |
        v
subscriber               -- receives downstream signals
~~~

Example:

~~~java
Mono<String> pipeline = Mono.fromCallable(() -> {
        String raw = blockingLegacyCall(); // On boundedElastic
        return raw;
    })
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim)
    .publishOn(Schedulers.parallel())
    .map(String::toUpperCase);
~~~

`blockingLegacyCall` is an illustrative method, absent in a standalone program. `publishOn(parallel)` does not move a blocking source onto parallel; it only changes where *operators after it* execute. **Placing `publishOn(parallel())` and letting a subsequent `map` perform blocking I/O defeats the purpose.**

### 7.4. `publishOn` vs. `flatMap` with `subscribeOn` on Each Inner Source

~~~java
Flux<Integer> results = Flux.range(1, 5)
    .flatMap(i ->
        Mono.fromCallable(() -> blockingService(i))
            .subscribeOn(Schedulers.boundedElastic()),
        3 // Maximum inner sources that can be subscribed concurrently
    );
~~~

This is an illustrative snippet with an application-supplied `blockingService`. This structure allows up to 3 independent blocking operations to be handled concurrently (per `flatMap` concurrency semantics and source behavior), instead of merely changing one worker for the whole chain. `flatMap` results may **not preserve input order**; if order is required, consider `flatMapSequential` or `concatMap` depending on requirements and throughput.

Even with `concurrency=3`, how much truly runs concurrently remains bounded by workers, connection pools, resources, and the scheduler. Do not pick a huge concurrency number merely hoping to raise throughput.

## 8. Standalone Java 17+ Example with Deterministic stdout

This example uses **Reactor Core 3.8.8** and Java 17. We observe **thread kind via prefix** instead of printing thread sequence numbers. Reactor's default shared Schedulers use prefixes such as `single-`, `parallel-`, and `boundedElastic-`; checking prefixes keeps output independent of per-machine worker indices. Tests use `block()` **only from the `main` calling thread** to wait for completion, without calling blocking Reactor APIs inside `single`/`parallel` workers.

Structure:

~~~text
reactor-schedulers-demo/
├── pom.xml
└── src/main/java/example/SchedulerChoicesDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-schedulers-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SchedulerChoicesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/SchedulerChoicesDemo.java`**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class SchedulerChoicesDemo {

    private static boolean onThreadPrefix(String prefix) {
        return Thread.currentThread().getName().startsWith(prefix);
    }

    public static void main(String[] args) {
        // Only a shared single thread is needed to run the supplier.
        Boolean single = Mono
            .fromSupplier(() -> onThreadPrefix("single-"))
            .subscribeOn(Schedulers.single())
            .block();
        System.out.println("single worker=" + single);

        // Short compute task on the parallel pool.
        Boolean parallel = Mono
            .fromSupplier(() -> onThreadPrefix("parallel-"))
            .subscribeOn(Schedulers.parallel())
            .block();
        System.out.println("parallel worker=" + parallel);

        // Simulate a synchronous I/O wait call with Thread.sleep.
        // Callable is scheduled on boundedElastic.
        Boolean elastic = Mono
            .fromCallable(() -> {
                Thread.sleep(20);
                return onThreadPrefix("boundedElastic-");
            })
            .subscribeOn(Schedulers.boundedElastic())
            .block();
        System.out.println("boundedElastic worker=" + elastic);

        // subscribeOn affects source; publishOn switches downstream.
        String boundary = Mono
            .fromSupplier(() ->
                "source single=" + onThreadPrefix("single-"))
            .subscribeOn(Schedulers.single())
            .publishOn(Schedulers.parallel())
            .map(value ->
                value + ", downstream parallel=" + onThreadPrefix("parallel-"))
            .block();
        System.out.println(boundary);

        // Split into rails for independent compute processing.
        // Print only count because scheduling/ordering may vary.
        Long count = Flux.range(1, 6)
            .parallel(2)
            .runOn(Schedulers.parallel())
            .map(i -> i * i)
            .sequential()
            .count()
            .block();
        System.out.println("computed count=" + count);
    }
}
~~~

From the `reactor-schedulers-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout with default shared Schedulers, without custom thread naming or Scheduler factory overrides:**

~~~text
single worker=true
parallel worker=true
boundedElastic worker=true
source single=true, downstream parallel=true
computed count=6
~~~

Explanation:

1. `Mono.fromSupplier` in case 1 executes only when subscribed, and `subscribeOn(single)` puts it on the `single` worker.
2. `Mono.fromSupplier` in case 2 is placed on a `parallel` worker. This does not prove multiple items run in parallel; it only demonstrates where the work executes.
3. Case 3 uses `Mono.fromCallable`, which can throw checked exceptions, so writing `Thread.sleep` is valid without manual `try/catch`. In real applications, `Thread.sleep` only simulates blocking work, not how to do non-blocking I/O.
4. `subscribeOn(single)` controls where the source emits, while `publishOn(parallel)` changes the thread executing the trailing `map`.
5. `parallel(2).runOn(parallel).sequential()` processes 6 items across two rails. We print only the output count to avoid depending on timing and scheduling order. A machine allocated only one processor may not show concurrent speedup despite requesting two rails.

**Limitations of the example:** Thread prefixes are observable hints under default configuration, not a stable API for controlling business logic. `block()` is used in `main` for the demo; do not bring this waiting style onto a WebFlux event-loop thread.

## 9. Blocking Errors on `single` and `parallel`

Reactor marks default threads of `Schedulers.single()` and `Schedulers.parallel()` as **non-blocking only**. Calling blocking Reactor APIs such as `block()`, `blockFirst()`, `blockLast()`, or blocking iterators `toIterable()/toStream()` on those threads can throw `IllegalStateException` with a message related to "blocking is not supported."

The following is an **anti-example**; do not run it as a valid pattern:

~~~java
Mono.just("outer")
    .publishOn(Schedulers.parallel())
    .map(value -> Mono.just("inner").block()) // WRONG
    .subscribe();
~~~

`map` runs on a `parallel` worker and tries to call `block()` inside. That violates the non-blocking thread policy. To combine two `Mono` values, use `flatMap`/`zip`:

~~~java
Mono<String> correct = Mono.just("outer")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.just("inner").map(inner -> value + "-" + inner));
~~~

Distinguish **blocking actively detected by Reactor** (`block()` on a NonBlocking thread) from **blocking in external APIs** (JDBC, `Thread.sleep`). External APIs may not throw immediately even while stalling the worker. Thus "seeing no exception" is not proof that code is non-blocking.

## 10. Integrating with Spring WebFlux

### 10.1. Protecting the Event Loop When Forced to Use a Legacy Library

In a WebFlux application running on Reactor Netty, many HTTP callbacks execute on event-loop threads. Never perform long blocking I/O on them. When reactive drivers are unavailable, wrap synchronous calls in `fromCallable` and `subscribeOn(boundedElastic)`:

~~~java
@Service
public class CustomerService {
    private final LegacyCustomerClient legacyClient;

    public CustomerService(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    public Mono<Customer> load(String id) {
        return Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

This is an **illustrative snippet in a Spring application**: `LegacyCustomerClient` and `Customer` are hypothetical business classes requiring implementations. If `findById` returns `null`, `Mono.fromCallable` completes empty; downstream must decide whether to return 404 via `switchIfEmpty`.

A WebFlux controller should **return a Publisher** so the framework subscribes and manages the lifecycle:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> getCustomer(@PathVariable String id) {
    return service.load(id);
}
~~~

Do not call `subscribe()` manually inside a handler to "trigger" work and return an independent response, as that detaches error handling, cancellation, and completion timing from HTTP. Nor is this a reason to put `Schedulers.boundedElastic()` on every endpoint.

### 10.2. When You Already Have a Non-Blocking API, Keep It Non-Blocking

~~~java
Mono<Customer> customer =
    reactiveRepository.findById(id)
        .map(this::enrich);
~~~

If the repository and `enrich` are non-blocking, adding `subscribeOn(boundedElastic)` generally yields no benefit and only adds scheduling/queue/context-switch overhead. `WebClient`, R2DBC, and non-blocking drivers have their own scheduling models; you do not make them "more reactive" by switching threads indiscriminately.

For independent CPU processing, you can consider `Schedulers.parallel()` or splitting rails, yet throughput, CPU, data ordering, and concurrency bounds must be determined via real measurement.

### 10.3. ThreadLocal, Transactions, and Context Are Not the Same Thing

Switching threads with `subscribeOn`/`publishOn` can cause traditional `ThreadLocal`, MDC logging, security context, or synchronous transactions to disappear where you expect them. Reactor provides `Context` attached to the subscription and context-propagation mechanisms (depending on integration) to pass context. Do not assume a transaction/thread-bound resource is shared across multiple workers merely because Publishers were built in the same method.

In reactive Spring, reactive transaction management uses the subscription context; synchronous JDBC/transactions using ThreadLocal require separate design. If a use case requires transactions spanning operations, a Scheduler cannot replace a transaction policy.

## 11. Overload, Cancellation, and Resources

A Scheduler can accept many queued tasks; that **does not exempt you from backpressure** or concurrency-limiting policies. Some rules:

1. **Bound concurrency**: `flatMap(..., concurrency)`, connection pools, thread caps, and queue caps should be sized to actual resources; do not raise them all at once.
2. **Monitor latency/queues**: boundedElastic has caps, so tasks may wait a long time; if queues fill up, the scheduler can reject. Observe corresponding metrics with Micrometer/Reactor when integrated.
3. **Timeouts/cancellation**: downstream `timeout` or cancellation is not guaranteed to interrupt every running blocking API. Legacy calls need timeout/interrupt support or proper cancellation hooks. `doFinally` can observe `CANCEL`, `ON_ERROR`, and `ON_COMPLETE`.
4. **Avoid nested blocking**: using one worker to wait for results of work that requires that same worker to run can cause deadlock/starvation, even when the Scheduler permits blocking.
5. **Manage lifecycle**: shared Schedulers `single()/parallel()/boundedElastic()` are managed by Reactor; for `newSingle`/`newParallel`/`newBoundedElastic`, the owner must `dispose()` at application shutdown. Never create a new pool per HTTP request.
6. **Do not rely on thread names** to store state, measure concurrency, or generate correlation IDs. Threads can be reused and tasks can switch workers across async boundaries.

## 12. Quick Check Exercises

1. Does `Flux.range(1, 10).publishOn(Schedulers.parallel()).map(...)` guarantee 10 elements run on 10 threads? **No**. One `publishOn` typically uses one worker for that subscriber's signal stream. To split into rails, use `parallel().runOn(...)` or controlled fan-out.
2. You must call synchronous JDBC without blocking the HTTP event loop; which scheduler do you use? **`boundedElastic()`**, with `Mono.fromCallable(() -> jdbcCall()).subscribeOn(...)`.
3. Does `Mono.just(blockingCall()).subscribeOn(Schedulers.boundedElastic())` move `blockingCall` to boundedElastic? **No**: Java evaluates the call immediately at assembly.
4. Does `Schedulers.single()` create a new thread on every invocation? **No**, it is a shared Scheduler. For an independent scheduler, create `newSingle(...)` and manage its lifecycle.
5. Is `Schedulers.parallel()` optimal for holding threads waiting on JDBC or `Thread.sleep`? **No**, it is meant for fast, non-blocking tasks.
6. Why can calling `block()` inside a `map` running on `parallel()` cause `IllegalStateException`? Because that thread is marked `NonBlocking`, and Reactor forbids calling blocking APIs on it.
7. Is `boundedElastic` allowed to run unlimited threads and queued tasks? **No**, thread/queue limits can lead to queuing and errors under overload.
8. If already using non-blocking WebClient, must you wrap every call in `boundedElastic()`? **No**. Offload only when genuine blocking work exists.
9. To process 4 items across multiple rails, is `parallel(4)` alone enough? **No**, you must attach `runOn(Schedulers.parallel())` or a suitable scheduling source, and it still depends on real resources.
10. Can `ThreadLocal` issues after `publishOn` be fixed simply by keeping application state on one exact thread? **No**. Use context propagation/`Reactor Context` and an explicit data-management policy.
11. If you want downstream to run on parallel while a legacy JDBC call stays on boundedElastic, where do you place the Schedulers? **`subscribeOn(boundedElastic)` near `fromCallable(jdbcCall)` and `publishOn(parallel)` after the blocking part**.
12. Can you replace timeout/connection-pool design by raising the boundedElastic thread cap? **No**; thread blocking and infrastructure limits must be addressed at each layer.

## 13. Selection Summary and Official Documentation

- `Schedulers.single()`: one shared thread for short, centralized work; do not place long blocking tasks here.
- `Schedulers.parallel()`: bounded pool optimized for fast/non-blocking computation; **does not parallelize items automatically** via `publishOn` alone.
- `Schedulers.boundedElastic()`: capped environment to isolate unavoidable blocking work; does not turn legacy I/O into non-blocking.
- `subscribeOn` shifts subscription and source; `publishOn` shifts downstream processing; both establish context in different ways.
- Use `Flux.parallel().runOn(...)` or `flatMap` with concurrency when truly needing concurrent independent work; measure performance and preserve ordering if business logic requires it.

Reference documentation:

1. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): Schedulers, `publishOn`, `subscribeOn`, Java 21 virtual-thread boundedElastic.
2. [Project Reactor API — Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): factories, default settings, and rules for creating shared/dedicated Schedulers.
3. [Project Reactor Reference — Parallelizing Work with ParallelFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-parallelizing-parralelflux.html): `parallel`, `runOn`, `sequential`.
4. [Project Reactor Reference — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): `fromCallable` and `subscribeOn(boundedElastic)`.
5. [Project Reactor API — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) and [Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): Publisher semantics and operator effects on threads.