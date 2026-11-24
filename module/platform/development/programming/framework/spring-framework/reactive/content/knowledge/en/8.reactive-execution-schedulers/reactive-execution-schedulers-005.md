# Scheduler Switching Placement and Thread-Hopping Cost in Project Reactor

> **Module:** Spring Framework – reactive. **Parent topic:** Execution threading. This lesson explains why and where to place `publishOn`/`subscribeOn` execution boundaries, how to choose a Scheduler, scheduling and queue costs, as well as applications in Spring WebFlux. Examples use Java 17+, Reactor Core 3.8.8, and Maven.

## 1. Learning Outcomes

1. Distinguish **subscription/request** flowing toward the source (upstream) from **onNext/onError/onComplete** flowing toward the subscriber (downstream).
2. Identify which operators run on the source thread, the `subscribeOn` thread, and the `publishOn` thread, including when both boundaries appear together.
3. Place `publishOn` right before the stage needing a context switch and `subscribeOn` near the synchronous/blocking source needing offloading.
4. Explain why a "Scheduler switch" does not mean an OS thread switch per element; understand queue, worker, prefetch, backpressure, RAM, and tail-latency costs.
5. Avoid locking the Reactor Netty event loop in WebFlux; choose appropriately among `boundedElastic`, `parallel`, `single`, `immediate`, and understand virtual threads.
6. Write and run a Java example verifying thread regions and JUnit/StepVerifier tests, and measure performance with a baseline-driven workflow.
7. Distinguish sequential thread switching from **processing multiple elements concurrently** via `flatMap` or `parallel().runOn(...)`.

**Rule:** Schedulers help **place work onto the right execution resource**, but do not speed up a pipeline by themselves. Each asynchronous boundary has a cost and needs a clear purpose plus real measurements.

## 2. Two Directions in Reactor: Subscription and Signals

A typical `Mono<T>` or `Flux<T>` is **lazy**. Building a pipeline with `map`, `filter`, and `publishOn` does not run the source yet. When a Subscriber subscribes, Reactor wires the subscriber chain backward from downstream to upstream, and then the source begins emitting when demand arrives. Elements and terminal signals flow forward downstream.

~~~text
subscribe / request(n):
Subscriber <── final operator <── publishOn <── map <── Source

onNext / onError / onComplete:
Source ──> map ──> publishOn ──> final operator ──> Subscriber
~~~

There are three distinct concepts here:

- **Thread:** where the JVM executes a callback; it may be the caller thread, an event loop, a worker pool, or a virtual thread.
- **Scheduler:** Reactor's abstraction that provides a `Worker` to schedule callbacks; a Scheduler may use one or multiple threads.
- **Backpressure/demand:** the Subscriber calls `request(n)` to regulate data volume; it is not synonymous with thread count.

**By default, Reactor does not create a new thread for each `map`.** With a synchronous `Flux.range(1, 3)`, a `map/filter` chain usually runs right on the thread performing the subscription. With `WebClient`, `Flux.interval`, an I/O source, or an async `Mono.fromFuture`, value-emitting callbacks can run on the source's own thread. Therefore, when reading execution flow, ask **who actually emits the signal**, rather than looking only at where a `subscribeOn` sits.

## 3. publishOn: Changing Where Downstream Signals Execute

**Syntax and how to read it:**

~~~java
Flux<Integer> result = Flux.range(1, 3)
    .map(i -> i + 10)                    // A: before boundary
    .publishOn(Schedulers.parallel())    // switches downstream emission
    .map(i -> i * 2);                    // B: after boundary
~~~

With a synchronous `Flux.range` and caller subscribing:
1. The `Flux.range` source and `map(+10)` typically run on the caller thread.
2. `publishOn` receives source signals and schedules forwarding onto a `Schedulers.parallel()` Worker.
3. `map(*2)` runs on that worker, along with subsequent operators until the next boundary or an async source/operator changes emission context.

**The position of `publishOn` has direct effect.** If a heavy CPU task sits **before** publishOn, publishOn does not reach back to move that task onto the new Scheduler. To relocate processing of a specific step, place the boundary **before** that step.

~~~text
Flux.range --- map(A) --- publishOn(cpu) --- map(B) --- publishOn(out) --- map(C)
    caller       caller              |        cpu             |          out
                                   boundary 1            boundary 2
~~~

Each `publishOn` selects a Worker and forwards `onNext`, `onError`, and `onComplete` of the stream downstream. **For a sequential subscription, `onNext` after publishOn remains serialized**, rather than pushing all elements simultaneously across multiple CPUs. `publishOn(Schedulers.parallel())` is not equivalent to `parallel().runOn(...)`.

### 3.1. Two publishOn Calls

~~~java
Flux<String> transformed = Flux.range(1, 3)
    .map(i -> "item-" + i)
    .publishOn(cpuScheduler)
    .map(this::compute)
    .publishOn(outputScheduler)
    .doOnNext(this::send);
~~~

This is a **fragment**, since `cpuScheduler`, `outputScheduler`, `compute`, and `send` must be defined by the application. With the synchronous source in the example, `compute` runs on the cpuScheduler region; `send` runs on the outputScheduler region. If `send` is blocking I/O, a dedicated strategy is needed; a `publishOn` by itself does not make a blocking call non-blocking.

### 3.2. Queue, Prefetch, and Backpressure

`publishOn` is an **asynchronous boundary**: items from upstream can be placed into a queue, and a downstream Worker reads and forwards them according to demand. Overloads accept `prefetch`:

~~~java
Flux<Integer> result = Flux.range(1, 1_000)
    .publishOn(Schedulers.parallel(), 32)
    .map(this::compute);
~~~

This is a fragment with an application-defined `compute` method. `32` is the configured prefetch: the operator can request a batch of elements ahead and replenish requests as progress occurs. It does **not** guarantee the queue always holds exactly 32 elements, nor does it cap every queue outside the boundary at 32 elements.

Pros/cons of prefetch:
- Higher values can reduce `request(n)` coordination frequency and improve throughput.
- Higher values can also increase **in-flight** elements, heap usage, GC pressure, and queueing time.
- Lower values can lower memory pressure but increase demand signaling round-trips, leaving the source busier or less fed than needed.
- The right value depends on load, payload size, downstream speed, and concurrent subscriptions; there is no universal "optimal prefetch" for every application.

`publishOn` still honors backpressure in a standard chain. **Hot sources emitting data regardless of demand** need an explicit overflow strategy (bounded `onBackpressureBuffer`, drop/latest/error, or a broker), because switching schedulers alone does not solve a producer persistently outpacing a consumer.

## 4. subscribeOn: Changing How Subscription Reaches the Source

**Typical syntax:**

~~~java
Mono<String> loaded = Mono.fromCallable(() -> legacyRead())
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim);
~~~

The above is a **fragment**, where `legacyRead()` is a real blocking method provided by the application. `subscribeOn` schedules subscription and request interactions with upstream onto a Worker of the chosen Scheduler. Because `fromCallable` runs the Callable upon subscription, the blocking call typically executes on `boundedElastic()` rather than holding the caller thread or Netty event loop.

With synchronous sources, `subscribeOn` placement is relatively more flexible than `publishOn`:

~~~java
Flux<Integer> a = Flux.range(1, 3)
    .subscribeOn(Schedulers.parallel())
    .map(i -> i + 1);

Flux<Integer> b = Flux.range(1, 3)
    .map(i -> i + 1)
    .subscribeOn(Schedulers.parallel());
~~~

In both pipelines, the synchronous source and `map` stay on the execution region selected by subscribeOn, unless another boundary exists. **Place subscribeOn near the source** so code is easy to inspect, especially when `doFirst`, `doOnRequest`, and other operators observe the subscription/request path.

### 4.1. Should You Add Multiple subscribeOn Calls?

~~~java
Flux<Integer> unnecessary = Flux.range(1, 3)
    .subscribeOn(schedulerA)
    .map(i -> i * 2)
    .subscribeOn(schedulerB);
~~~

The Schedulers in the fragment must be defined in the application. Multiple `subscribeOn` calls **do not make each element run in parallel**. Reactor documentation warns that only the subscribeOn closest to a given upstream path governs scheduling subscription/request to the source; adding more subscribeOn calls can cause **redundant hops**. Use **one subscribeOn per source that needs offloading**; use publishOn at downstream boundaries where a Worker switch is genuinely needed.

### 4.2. Do Not Force Asynchronous Sources Back Onto subscribeOn

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .subscribeOn(Schedulers.boundedElastic())
    .map(i -> i + 1);
~~~

`Flux.interval` uses a Scheduler to schedule **tick emissions**, defaulting typically to `Schedulers.parallel()`. `subscribeOn` may move registration time, yet **does not force every timer tick onto boundedElastic**. To change the Scheduler **emitting the timer**, use the `Flux.interval(period, scheduler)` overload; to change where processing runs **after** the timer, use publishOn.

The same applies to `WebClient`, network callbacks, `Mono.fromFuture`, or inner Publishers in `flatMap`: an asynchronous source can fire callbacks on a thread different from the subscribing thread. Do not assume every `onNext` must share the same thread just because subscribeOn is present.

## 5. Combining subscribeOn and Multiple publishOn Calls

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> 10)
    .map(n -> n + 1)
    .subscribeOn(sourceScheduler)
    .publishOn(cpuScheduler)
    .map(n -> n * 2)
    .publishOn(resultScheduler)
    .map(n -> n + 3);
~~~

This is a fragment with three application-supplied Schedulers. Starting from the synchronous `fromSupplier` source:
- `subscribeOn(sourceScheduler)` schedules upstream subscription; the supplier and `map(+1)` run in the source region.
- `publishOn(cpuScheduler)` switches downstream, so `map(*2)` runs on cpuScheduler.
- `publishOn(resultScheduler)` switches the final portion, so `map(+3)` runs on resultScheduler.

**The output value is always 25**: `(10 + 1) * 2 + 3 = 25`. Schedulers affect threads, scheduling, and latency, not the pure computation itself.

~~~text
                           subscribe from caller
                                    |
                       subscribeOn(sourceScheduler)
                                    |
                   Supplier -> map(+1) [sourceScheduler]
                                    |
                        publishOn(cpuScheduler)
                                    |
                         map(*2) [cpuScheduler]
                                    |
                       publishOn(resultScheduler)
                                    |
                        map(+3) [resultScheduler]
                                    |
                                Subscriber
~~~

Do not assume every callback is guaranteed to sit inside a `publishOn` region: `doFirst`, `doOnSubscribe`, `doOnRequest`, and `doFinally` can observe subscription/request/cancel at other points. When you need to know the thread at a point, observe that specific callback directly and check which boundaries signals cross.

## 6. Choosing the Right Scheduler for the Job

| Scheduler | Characteristics | Suitable for | Risks |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Executes on the calling thread, creates no separate thread | Keeping current context when no offload is needed | Cannot handle blocking/heavy CPU by switching workers. |
| `Schedulers.single()` | One shared worker/thread | Short, sequential work, simple affinity | Slow tasks block other tasks sharing the pool. |
| `Schedulers.newSingle("name")` | Dedicated scheduler, requires `dispose()` | Examples, components needing a thread with its own lifecycle | Avoid creating per request or disposing too early. |
| `Schedulers.parallel()` | Pool for CPU/timers, worker count tied to CPU count | Non-blocking computation, short scheduling | Do not put JDBC/`Thread.sleep` or sync network directly on this pool. |
| `Schedulers.boundedElastic()` | Bounded threads/task queues, tuned as a blocking bridge | Legacy/JDBC/blocking file libraries with no async API | Can saturate, queue up, and raise latency under high load. |
| Scheduler from ExecutorService | Custom execution infrastructure configuration | Integrating an already managed pool | Must have clear lifecycle, bounded queue, and shutdown. |

`boundedElastic()` has **finite** resources. On JDK 17, it typically uses platform threads. Reactor 3.6+ supports an option to run on **virtual threads** on JDK 21+ via the startup property `reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`; do not assume this feature is available on JDK 17. Virtual threads still do not give a DB backend/connection pool infinite capacity; a blocking API remains a blocking API.

Self-created schedulers like `newSingle`/`newParallel` must be `dispose()`d per lifecycle—not right when returning an unsubscribed `Mono`. Shared schedulers from `Schedulers.parallel()` and `Schedulers.boundedElastic()` are normally managed by Reactor; do not arbitrarily dispose them globally inside a request.

## 7. Context-Switching Cost: Why Not Add publishOn Everywhere?

### 7.1. Scheduling and Queue Coordination

A `publishOn` generally posts a task to a Worker, enqueues/dequeues signals, coordinates demand, and drains the queue. These operations consume CPU/atomics/heap; if the next operator is only `i + 1`, scheduling cost can exceed useful work. If the worker is busy, signals wait in the queue and increase **queueing latency**.

**Do not claim that one onNext always causes one OS thread context switch**: multiple signals can be drained consecutively on a Worker, and the scheduler can reuse threads. Yet an async boundary still adds measurable logic overhead, queueing, and resource pressure.

### 7.2. Prefetch, RAM, and Backpressure

Multiple boundaries can create multiple places holding pending elements. Approximate RAM pressure grows with active subscriptions, queues, prefetch, and payload sizes, though there is no fixed formula because upstream operators, codecs, network buffers, and external sources also participate. If downstream is slow, queues can increase p95/p99 even when initial throughput looks high.

Inspect actual backpressure sizing and shape. `publishOn(..., 32)` is a prefetch setting, not a guarantee that "the entire application only buffers 32 elements."

### 7.3. Pool/Thread Overhead and CPU Cache

Adding unnecessary boundaries can make multiple Workers contend for CPU, increase scheduling tasks, hurt locality/caches, and make logs harder to correlate. `publishOn(parallel)` picks a Worker to transfer signals for one subscription; it does not create `N` parallel item-processing tasks.

### 7.4. Context and Observability

Traditional `ThreadLocal` or MDC is bound to a **thread**, and does not automatically move to another Worker. `Thread.currentThread().getName()` is useful for debugging, but is **not** a request identifier. In Reactor, use **Reactor Context** (`contextWrite`, `deferContextual`) bound to the subscription, combined with official context-propagation/security/tracing if MDC must be restored for logging.

Do not assume adding `publishOn` preserves `ThreadLocal` or acts as a mechanism to pass JWTs, correlation IDs, and request data. Test trace and security context across every async boundary.

### 7.5. Why Is a Hop Sometimes Worth Paying?

When an event loop is serving many sockets, moving a moderate CPU chunk onto an appropriate pool can help the event loop stay responsive. When a legacy source blocks on I/O, `fromCallable(...).subscribeOn(boundedElastic())` avoids holding the event loop during the wait. Weigh the benefit against queue cost, pool saturation, and hop count—do not benchmark only a single isolated request.

## 8. Runnable Java 17+ Example Printing Deterministic Execution Regions

This example uses three `Schedulers.newSingle` instances with clear prefixes. Instead of printing full thread names (which may add varying indices), a helper checks the prefix and prints the **region name**. The `block()` calls here only make the CLI app wait for results before printing; **do not place `block()` on a WebFlux request path**.

### 8.1. Structure

~~~text
reactor-scheduler-demo/
├── pom.xml
├── src/main/java/com/example/scheduler/SchedulerDemo.java
└── src/test/java/com/example/scheduler/SchedulerDemoTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-scheduler-demo</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. src/main/java/com/example/scheduler/SchedulerDemo.java

~~~java
package com.example.scheduler;

import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class SchedulerDemo {
    private SchedulerDemo() {}

    static String region(String expected) {
        String threadName = Thread.currentThread().getName();
        if (!threadName.startsWith(expected + "-")) {
            throw new IllegalStateException(
                "Expected " + expected + ", got " + threadName);
        }
        return expected;
    }

    public static void main(String[] args) {
        Scheduler source = Schedulers.newSingle("source-zone");
        Scheduler compute = Schedulers.newSingle("compute-zone");
        Scheduler output = Schedulers.newSingle("output-zone");

        try {
            Mono<String> positions = Mono
                .fromSupplier(() -> region("source-zone"))
                .subscribeOn(source)
                .map(s -> s + " > " + region("source-zone"))
                .publishOn(compute)
                .map(s -> s + " > " + region("compute-zone"))
                .publishOn(output)
                .map(s -> s + " > " + region("output-zone"));

            System.out.println("positions=" + positions.block());

            List<Integer> values = Flux.range(1, 10)
                .publishOn(compute, 4)
                .map(i -> {
                    region("compute-zone");
                    return i * 2;
                })
                .take(4)
                .collectList()
                .block();
            System.out.println("values=" + values);

            // This simulates a legacy blocking library.
            Mono<String> legacy = Mono.fromCallable(() -> {
                Thread.sleep(20);
                return "OK";
            }).subscribeOn(Schedulers.boundedElastic());
            System.out.println("legacy=" + legacy.block());
        } finally {
            source.dispose();
            compute.dispose();
            output.dispose();
        }
    }
}
~~~

`Mono.fromSupplier` runs in `source-zone` thanks to subscribeOn. The first `map` stays in the source region; after publishOn(compute), the next `map` runs on `compute-zone`; after publishOn(output), the final step runs on `output-zone`. `Flux.range` only moves the doubling step onto the compute Worker; prefetch 4 does not create 4 threads. The sleep call simulates a blocking SDK and is offloaded to boundedElastic.

**Why is disposing at the end correct?** The CLI already called block at the terminal points, so subscriptions have completed. In WebFlux, returning a Mono does not mean the Mono has run yet; disposing a Scheduler as soon as a service method returns can make the pipeline fail later because the Scheduler is already shut down. Use a Scheduler bean with a sufficiently long lifecycle.

### 8.4. Run Commands and stdout

In the directory containing pom.xml, JDK 17+ and Maven are required:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.scheduler.SchedulerDemo
~~~

**Stdout lines printed by main** (excluding Maven logs):

~~~text
positions=source-zone > source-zone > compute-zone > output-zone
values=[2, 4, 6, 8]
legacy=OK
~~~

Values and order do not depend on OS scheduling timing. Thread name prefixes are used only to demonstrate regions in the demo; do not build business logic on thread names.

## 9. Testing Thread Boundaries with StepVerifier

`StepVerifier` verifies onNext/terminal signals without adding `Thread.sleep` to tests. The tests below use self-created Schedulers, call `dispose()` after verifying, and assert thread prefixes per region.

**src/test/java/com/example/scheduler/SchedulerDemoTest.java**

~~~java
package com.example.scheduler;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerDemoTest {

    @Test
    void publishOnChangesDownstreamThread() {
        Scheduler stage = Schedulers.newSingle("test-stage");
        String caller = Thread.currentThread().getName();
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        try {
            Flux<Integer> values = Flux.range(1, 3)
                .doOnNext(v -> before.set(
                    Thread.currentThread().getName()))
                .publishOn(stage)
                .doOnNext(v -> after.set(
                    Thread.currentThread().getName()));

            StepVerifier.create(values)
                .expectNext(1, 2, 3)
                .verifyComplete();

            assertEquals(caller, before.get());
            assertTrue(after.get().startsWith("test-stage-"));
        } finally {
            stage.dispose();
        }
    }

    @Test
    void subscribeOnSchedulesCallableSource() {
        Scheduler source = Schedulers.newSingle("test-source");
        AtomicReference<String> executedOn = new AtomicReference<>();
        try {
            Mono<Integer> sourceValue = Mono.fromCallable(() -> {
                executedOn.set(Thread.currentThread().getName());
                return 7;
            }).subscribeOn(source).map(i -> i + 1);

            StepVerifier.create(sourceValue)
                .expectNext(8)
                .verifyComplete();

            assertTrue(executedOn.get().startsWith("test-source-"));
        } finally {
            source.dispose();
        }
    }

    @Test
    void twoPublishOnBoundariesChooseTwoZones() {
        Scheduler one = Schedulers.newSingle("test-one");
        Scheduler two = Schedulers.newSingle("test-two");
        AtomicReference<String> first = new AtomicReference<>();
        AtomicReference<String> second = new AtomicReference<>();
        try {
            Flux<Integer> values = Flux.range(1, 3)
                .publishOn(one)
                .doOnNext(v ->
                    first.set(Thread.currentThread().getName()))
                .publishOn(two)
                .doOnNext(v ->
                    second.set(Thread.currentThread().getName()));

            StepVerifier.create(values)
                .expectNext(1, 2, 3)
                .verifyComplete();

            assertTrue(first.get().startsWith("test-one-"));
            assertTrue(second.get().startsWith("test-two-"));
        } finally {
            one.dispose();
            two.dispose();
        }
    }
}
~~~

The first test infers that before publishOn runs on caller only because **the `Flux.range` source is synchronous**. Do not apply that assumption to `WebClient`, `Mono.delay`, or inner async Publishers. The second test verifies where the Callable executes. The third test confirms two boundaries on two separate Schedulers.

**Not a benchmark:** checking thread names/signals verifies functional correctness, not hop latency. Real timing tests require a load environment and dedicated measurement methodology.

## 10. publishOn(parallel) Is Not Parallel Processing of Multiple Items

~~~java
Flux<Integer> serialOnWorker = Flux.range(1, 1_000)
    .publishOn(Schedulers.parallel())
    .map(this::heavyComputation);
~~~

This is a fragment using an application `heavyComputation` method. It moves the **downstream path** of one subscription onto a Worker, yet `map` still receives items sequentially. If the work is truly CPU-bound and each item is independent:

~~~java
Flux<Integer> multiRail = Flux.range(1, 1_000)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(this::heavyComputation)
    .sequential();
~~~

`parallel(4)` splits the source into four rails; `runOn` places the rails onto the Scheduler; `sequential` merges back into a normal Flux. This carries splitting/merging overhead and is not always faster; inspect ordering properties, CPU cores, and work per element. Tiny operations like `i + 1` can become slower due to overhead.

For multiple **non-blocking I/O** tasks (such as WebClient) over a list of IDs, use `flatMap` with bounded concurrency:

~~~java
Flux<Result> results = Flux.fromIterable(ids)
    .flatMap(id -> remoteClient.fetch(id), 8);
~~~

The fragment assumes `ids` is a list and `remoteClient.fetch(id)` returns `Mono<Result>`. `8` caps concurrent inner subscriptions in flatMap; result order may vary. When output order must be preserved, consider `flatMapSequential` or `concatMap`; do not scatter subscribeOn across every element of an already non-blocking source.

## 11. Isolating Blocking I/O from the Spring WebFlux Event Loop

The Reactor Netty event loop serves I/O for many sockets. A **synchronous JDBC call, blocking HTTP SDK, Thread.sleep, blocking file read, or Mono.block()** on the event loop can stall many requests at once. `publishOn(Schedulers.parallel())` is not a sound way to offload blocking I/O: parallel workers are designed for non-blocking/CPU work.

**Legacy blocking bridge pattern:**

~~~java
Mono<Customer> found = Mono.fromCallable(() ->
        legacyGateway.load(customerId))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::mapToCustomer);
~~~

This is a service fragment with `legacyGateway`, `customerId`, `Customer`, and `mapToCustomer`; it does not compile without those definitions. `fromCallable` defers the blocking call until subscription, while subscribeOn places it on the boundedElastic pool. `boundedElastic` still has thread/queue bounds; timeouts, connection pools, concurrency limits, and saturation monitoring remain necessary. An appropriate reactive driver may perform better under heavy I/O load.

### 11.1. Illustrative WebFlux Controller

~~~java
package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/customers")
public class CustomerController {
    private final BlockingCustomerGateway gateway;

    public CustomerController(BlockingCustomerGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/{id}")
    public Mono<CustomerDto> find(@PathVariable String id) {
        return Mono.fromCallable(() -> gateway.load(id))
            .subscribeOn(Schedulers.boundedElastic())
            .map(row -> new CustomerDto(row.id(), row.name()));
    }
}
~~~

**Integration fragment**, not a standalone program: requires a Spring Boot WebFlux application, a `BlockingCustomerGateway` bean, `CustomerDto`/row types, and real configuration. Add HTTP 404 handling, validation, error handling, and security per system requirements. The controller **returns a Mono** for WebFlux to subscribe to; do not call block/subscribe inside a request handler.

### 11.2. Blocking I/O Inside Each Inner Publisher

~~~java
Flux<Customer> customers = Flux.fromIterable(ids)
    .flatMap(id ->
        Mono.fromCallable(() -> gateway.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8);
~~~

This is a fragment with `ids`, gateway, and `Customer` type. `subscribeOn` inside each `Mono.fromCallable` offloads each individual call; `8` bounds concurrency. A single subscribeOn placed outside the entire Flux does not ensure all inner blocking work runs concurrently safely; placing it on the specific work source makes the intent clear.

### 11.3. When Already Using a Reactive Client

~~~java
Mono<CustomerDto> customer = webClient.get()
    .uri("/customers/{id}", id)
    .retrieve()
    .bodyToMono(CustomerDto.class);
~~~

This is a fragment with existing `webClient`, `id`, and `CustomerDto`. `WebClient` with a non-blocking connector already performs network I/O asynchronously; **there is no need to add subscribeOn(boundedElastic) just because an HTTP request is made**. Only add publishOn if a specific downstream step requires a different Scheduler, and understand the cost.

## 12. Typical Mistakes

| Mistake | Consequence | Proper fix |
| --- | --- | --- |
| Placing publishOn **after** the CPU/blocking step to relocate | That step still runs upstream | Place publishOn before the step to move; use boundedElastic if blocking. |
| Scattering subscribeOn everywhere | Redundant subscribe hops, no increase in per-item parallelism | One subscribeOn per source needing offload. |
| Treating publishOn(parallel) as parallel per item | Does not achieve expected concurrency | Use `parallel().runOn` for independent CPU work or flatMap for async I/O. |
| Moving every callback to boundedElastic | Queues/resources grow, losing async benefits | Use boundedElastic only for legacy blocking. |
| Using Thread.sleep or block on Netty event loop | Halts serving of many connections | Reactive driver or proper blocking source offload. |
| Creating a new Scheduler per request | Thread explosion and hard cleanup | Use shared Schedulers or lifecycle-managed beans. |
| Disposing Scheduler right when returning Mono | Mono is not subscribed yet so scheduler errors may occur | Keep Scheduler alive until subscriptions complete/app shutdown. |
| Increasing prefetch unboundedly to speed up | Heap/GC and p99 degrade when consumer is slow | Tune per workload and bound buffers. |
| Reading MDC/ThreadLocal after publishOn without propagating context | Trace/requestId lost | Reactor Context and proper context-propagation. |
| Assuming subscribeOn forces all network callbacks onto one thread | Misdiagnosing async source behavior | Check emitter/inner Publisher threads; use publishOn where needed. |
| Thinking more schedulers always means faster | Scheduling/queueing can cost more than useful work | Measure baseline, 1 hop, 2 hops under identical load. |

## 13. Measuring Thread-Switching Cost Methodically

There is no fixed number like "one publishOn costs X microseconds" applicable to all machines. Cost depends on Reactor/JDK, thread pools, CPU quotas, concurrent requests, payload sizes, GC, prefetch, and downstream saturation.

**Measurement workflow:**
1. **Baseline:** synchronous source and `map` on the same Worker; record throughput, p50/p95/p99, CPU/heap/GC.
2. **One publishOn:** switch right before the step to offload, keeping data and processing logic unchanged.
3. **Two publishOn calls:** add a second boundary if production topology requires it; compare p99, queues, and resource consumption.
4. **Prefetch tuning:** test bounded levels (e.g., 16, 32, 128), measuring in-flight counts, memory usage, and downstream speed.
5. **Realistic concurrent load:** inspect request latency, event-loop responsiveness, boundedElastic queues, connection pools, and cancellation under high load.
6. **Tools:** use JMH for microbenchmarks needing proper warmup/JIT, endpoint load tests for server behavior, and Micrometer/Actuator/tracing for in-app diagnostics.

**Data-driven conclusion:** one boundary may add slight overhead to a single pipeline while protecting the event loop and improving load capacity; conversely, adding two boundaries for a tiny operation can increase queueing/p99. Measure real SLOs, not just thread counts.

## 14. Quick Decision Table

| Goal | Placement / usage | Notes |
| --- | --- | --- |
| Offload blocking Callable source | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Place near source and limit load. |
| Relocate execution of a downstream CPU step | `source.map(light).publishOn(cpu).map(heavy)` | publishOn stands before the step to relocate. |
| Need two consecutive worker regions | `publishOn(s1).map(A).publishOn(s2).map(B)` | Two boundaries add extra overhead. |
| Light processing after non-blocking WebClient | `webClient...bodyToMono(...).map(...)` | No default scheduler hop needed. |
| Many independent CPU-bound items | `parallel(rails).runOn(parallel).map(...).sequential()` | Measure overhead and ordering requirements. |
| Many non-blocking I/O calls | `flatMap(id -> client.fetch(id), concurrency)` | Bound in-flight; note ordering. |
| Many blocking SDK calls | `flatMap(id -> fromCallable(...).subscribeOn(boundedElastic()), concurrency)` | Offload each inner piece of work. |
| Timer emitting on specified Scheduler | `Flux.interval(period, scheduler)` | Timer scheduler differs from subscribeOn. |
| Preserve trace/security across thread switches | Reactor Context and framework context propagation | Do not rely on ThreadLocal copying automatically. |
| Bound RAM at an async boundary | Choose `publishOn(scheduler, prefetch)` + monitor | Prefetch is not a system-wide memory cap. |

## 15. Practice Exercises

**Exercise 1.** Run `Flux.range(1,3).map(A).publishOn(cpu).map(B)`, print threads in A/B, then move publishOn before A. **Expected answer:** first A is in source region and B in cpu region; afterward both A and B are in cpu region, given a synchronous source and no other async boundary.

**Exercise 2.** Add `publishOn(s1).map(A).publishOn(s2).map(B)` and verify with a test that A/B run on two workers. Then measure whether the second hop helps for tiny work. **Answer:** correct placement does not equate to good performance.

**Exercise 3.** Call a blocking SDK in WebFlux via `Mono.fromCallable`, `subscribeOn(boundedElastic)`. Test concurrent requests and pool saturation. **Answer:** reduces blocking on the event loop, yet connections, timeouts, and saturation must still be managed.

**Exercise 4.** Compare `publishOn(parallel).map(cpu)` with `parallel(4).runOn(parallel).map(cpu).sequential()` for 10,000 items. **Answer:** the first switches context for one sequential stream; the second splits into rails, carries overhead, and can alter ordering characteristics.

**Exercise 5.** For a request passing requestId across multiple Schedulers, check whether `ThreadLocal`/MDC is lost, then use Reactor Context/context propagation. **Answer:** thread-bound data does not automatically become subscription-bound data.

## 16. Pre-Deployment Checklist

- [ ] I know whether the source is synchronous or asynchronous and who emits callbacks.
- [ ] I can explain subscription/request direction and onNext/error/complete direction.
- [ ] I place subscribeOn on sources needing offload and publishOn before downstream stages needing a context switch.
- [ ] I do not treat publishOn(parallel) as per-element parallel processing.
- [ ] I do not run blocking I/O or Thread.sleep on Netty or parallel Schedulers.
- [ ] I manage custom Scheduler lifecycles and do not dispose early.
- [ ] I understand prefetch/queues, backpressure, memory, p99, and boundedElastic limits.
- [ ] I have tests checking thread placement at each boundary without hardcoding immutable thread names.
- [ ] I verified Reactor Context, MDC, security, and tracing across worker switches.
- [ ] I have baselines and reliable performance measurements before adding hops.

## 17. Official References

1. Project Reactor Reference – Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
2. Reactor Flux Javadoc – `publishOn`, `subscribeOn`, prefetch: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor Mono Javadoc – `publishOn`, `subscribeOn`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
4. Reactor Schedulers API – `parallel`, `boundedElastic`, virtual-thread option: https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html
5. Reactor Test StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
6. Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Self-check:** Given `Mono.fromSupplier(...).subscribeOn(A).map(X).publishOn(B).map(Y).publishOn(C).map(Z)`, you should be able to identify where the source, X, Y, and Z execute when the source is synchronous; explain why WebClient/timers may differ; and state why each boundary helps or hurts under load. That is the foundation for using Schedulers properly.
