# publishOn Changes Where Subsequent Operators Execute

## 1. What Problem Does publishOn Solve?

In Project Reactor, a **Flux** or **Mono** chain consists of multiple operators: generating data, filtering, transforming, logging, calling services, aggregating results, and returning a response. Those steps **do not automatically run on different threads**. By default, many synchronous sources and operators run on the exact thread emitting signals from the preceding operator.

**publishOn(Scheduler)** is the operator used to establish an **execution-context switching boundary** inside a pipeline. It receives signals from upstream and re-emits them downstream on a worker of the passed Scheduler. Consequently, **operators after publishOn** typically handle onNext/onError/onComplete on the thread chosen by that Scheduler, until another execution scheduling boundary appears, especially a subsequent publishOn.

Example:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
        .map(n -> n * 2)                  // Step A
        .publishOn(Schedulers.parallel()) // Thread-switching boundary
        .map(n -> n + 10)                 // Step B
        .filter(n -> n % 2 == 0);        // Step C
~~~

This is an **illustrative snippet** for use in a project with Reactor Core; it is not a standalone Java program.

- **Step A** is before publishOn: it belongs to the upstream processing path and **is not retroactively moved to another thread by this publishOn**.
- **Steps B and C** are after publishOn: they generally run on a worker selected from Schedulers.parallel() when receiving signals for that subscription.
- Steps do not automatically run in parallel per element: publishOn **moves where signals are processed**, without automatically splitting 1, 2, 3 across three threads.
- The pipeline only describes the work. With a cold source like Flux.range, processing typically begins when there is a **subscription**.

This is an important reading habit: the position of **publishOn** in a chain has both business and performance significance. Placing it **before or after** an operator can make that operator run on a different thread.

## 2. What Are Upstream and Downstream?

In the chain:

~~~text
Flux.range(1, 3)
      |
      v
  map(A)
      |
      v
  doOnNext(B)           <- upstream of publishOn
      |
      v
  publishOn(S1)         <- Scheduler boundary
      |
      v
  map(C)
      |
      v
  filter(D)             <- downstream of publishOn
      |
      v
  subscribe()
~~~

**Upstream** is the side toward the data source; **downstream** is the side toward the Subscriber. Reading Java code top-to-bottom, steps before publishOn are upstream, and steps after publishOn are downstream.

Regarding signals in Reactive Streams:

- **onNext, onError, and onComplete** typically flow from **upstream to downstream**.
- **subscribe**, **request(n)**, and **cancel** have scheduling paths flowing in the opposite direction or involving both directions. Therefore, one should not say publishOn forces *every callback in the pipeline* onto the same thread.
- publishOn primarily changes the **execution context when forwarding signals to subsequent operators**.
- With sources that have their own scheduling mechanism, an event loop, or other asynchronous operators, thread placement can depend more on the **entire pipeline** rather than just a single publishOn.

The **Scheduler** concept in Reactor is an abstraction over where and how work is executed: it may use a dedicated thread, a thread pool, an event loop, or immediate execution depending on the Scheduler type. Do not equate a Scheduler with "creating a new thread for every element."

## 3. Which Part of the Pipeline Does publishOn Affect?

### 3.1. Operators Before publishOn Do Not Move With It

~~~java
Flux.range(1, 3)
    .map(this::stepBefore)
    .publishOn(Schedulers.parallel())
    .map(this::stepAfter);
~~~

Here **stepBefore** is not moved to parallel by the subsequent publishOn. **stepAfter** receives signals on a parallel worker, unless it or related components have special scheduling rules.

If you place **publishOn after a blocking call**, that blocking operation may have already blocked the upstream thread before publishOn even runs. This is a common placement mistake:

~~~java
Mono.fromCallable(() -> blockingClient.load())
    .map(this::slowBlockingOperation)  // Blocks the upstream thread.
    .publishOn(Schedulers.boundedElastic())
    .map(this::format);
~~~

This illustrative code uses blockingClient and application-defined methods. **Placing publishOn after slowBlockingOperation does not protect the thread that already executed the preceding blocking step.**

### 3.2. Operators After publishOn Use the New Context

~~~java
Flux.range(1, 3)
    .publishOn(Schedulers.parallel())
    .map(this::calculate)
    .doOnNext(this::logResult);
~~~

With a simple synchronous source, both **calculate** and **logResult** typically execute on a parallel worker for that subscription. This is useful when you want to move a processing segment off the thread where data is received.

### 3.3. A Second publishOn Switches Context Again

~~~java
Flux.range(1, 3)
    .map(this::prepare)                    // Upstream
    .publishOn(firstScheduler)
    .map(this::transform)                  // On firstScheduler
    .publishOn(secondScheduler)
    .doOnNext(this::saveAudit);            // On secondScheduler
~~~

**firstScheduler** and **secondScheduler** here are Schedulers created/configured by the application. In normal signal flow, transform is governed by the first publishOn; saveAudit is governed by the second publishOn. If another operator is added after saveAudit with no new boundary, it continues in the downstream context of the second publishOn.

Each publishOn typically introduces a thread switch and an intermediate queue; placing multiple boundaries in a row can increase **context switches, latency, and memory usage**. Add them only when there is a clear reason for work isolation or operational control.

### 3.4. publishOn Preserves Signal Sequentiality Within a Subscription

Even though a Scheduler may be a multi-threaded pool, publishOn picks one **worker per subscription** to forward onNext in order. For a typical subscription, downstream signals are processed sequentially under the Reactive Streams contract.

Therefore:

- **publishOn(Schedulers.parallel()) does not mean each element is processed on a different CPU core.**
- If a map() function after publishOn takes 500 ms of CPU, elements of *that subscription* may still wait in turn.
- If work truly needs to be split across multiple elements, look at other mechanisms such as **flatMap** with asynchronous sources, or **parallel().runOn(...).sequential()** when appropriate.
- Multiple independent subscriptions may be distributed across different workers/threads and run concurrently, depending on the Scheduler and actual processing capacity.

## 4. publishOn and subscribeOn: Two Different Purposes

Both operators accept a Scheduler, yet **act on different stages**:

| Criterion | publishOn(scheduler) | subscribeOn(scheduler) |
| --- | --- | --- |
| Primary intent | Switches context for **downstream signal processing** from the operator's position | Switches context for **subscription/source initialization** and related upstream interactions |
| Position in chain | **Matters**: steps after publishOn are affected | Generally affects upstream/source regardless of position, noting operators with special rules |
| When used multiple times | Each publishOn can set a new boundary | Adding multiple subscribeOn calls usually yields no benefit; the subscribeOn closest to the source in the downstream chain is the primary factor scheduling upstream subscription |
| Effect on per-element processing | Switches where operators after it run | Shifts where the source and operators without their own scheduler boundary start/execute |
| Does it run elements in parallel? | **Not automatically** | **Not automatically** |
| Does it turn blocking I/O into non-blocking? | No | No |

Example combining both:

~~~java
Flux.range(1, 3)
    .map(this::prepare)
    .subscribeOn(sourceScheduler)
    .map(this::processBeforeBoundary)
    .publishOn(processingScheduler)
    .map(this::processAfterBoundary);
~~~

This is an illustrative snippet with Scheduler variables and application methods.

With a synchronous source such as Flux.range:

1. **subscribeOn(sourceScheduler)** places subscription/source on sourceScheduler; prepare and processBeforeBoundary typically run in that context when no other switch exists.
2. **publishOn(processingScheduler)** switches onNext to processAfterBoundary on a processingScheduler worker.
3. Placing **subscribeOn below publishOn** does not mean it erases the effect of publishOn. Every downstream boundary must still be read according to its position.
4. If the source already uses an event loop or its own schedule (for instance Flux.interval or a network source), examine the source's mechanism rather than assuming every emission always stays on the thread chosen by subscribeOn.

Practical selection rules:

- To **launch a blocking source where blocking is permitted**: typically use **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())**.
- To **move a subsequent processing segment** to an appropriate scheduler: use **publishOn(scheduler)** right before that segment.
- To run multiple asynchronous I/O calls concurrently: typically combine those Monos using suitable async composition operators; adding publishOn does not create concurrency by itself if the work itself remains sequential.

## 5. Runnable Java 17+ Example: Observing Three Thread Regions

This example creates a finite Flux and two dedicated Schedulers. It records where each operator executes, yet **only prints the lists after the whole pipeline completes**. This ensures deterministic stdout order, even though the source thread and workers can interleave in practice.

Project structure:

~~~text
reactor-publishon/
├── pom.xml
└── src/main/java/PublishOnDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-publishon</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>PublishOnDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/PublishOnDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class PublishOnDemo {
    public static void main(String[] args) {
        Thread callingThread = Thread.currentThread();

        Scheduler transform = Schedulers.newSingle("transform-stage");
        Scheduler audit = Schedulers.newSingle("audit-stage");

        List<String> upstreamSeen = new CopyOnWriteArrayList<>();
        List<String> transformSeen = new CopyOnWriteArrayList<>();
        List<String> auditSeen = new CopyOnWriteArrayList<>();

        try {
            List<Integer> result = Flux.range(1, 3)
                    .hide()
                    .doOnNext(n -> upstreamSeen.add(
                            n + ":caller="
                                    + (Thread.currentThread() == callingThread)
                    ))
                    .publishOn(transform)
                    .map(n -> {
                        transformSeen.add(
                                n + ":transform="
                                        + Thread.currentThread()
                                                .getName()
                                                .startsWith("transform-stage-")
                        );
                        return n * 10;
                    })
                    .publishOn(audit)
                    .doOnNext(n -> auditSeen.add(
                            n + ":audit="
                                    + Thread.currentThread()
                                            .getName()
                                            .startsWith("audit-stage-")
                    ))
                    .collectList()
                    .block();

            System.out.println("upstream = " + upstreamSeen);
            System.out.println("transform = " + transformSeen);
            System.out.println("audit = " + auditSeen);
            System.out.println("result = " + result);
        } finally {
            transform.dispose();
            audit.dispose();
        }
    }
}
~~~

With **JDK 17+**, Maven, and dependency download access for the first run, execute in the project directory:

~~~bash
mvn -q compile exec:java
~~~

**Lines printed by the program:**

~~~text
upstream = [1:caller=true, 2:caller=true, 3:caller=true]
transform = [1:transform=true, 2:transform=true, 3:transform=true]
audit = [10:audit=true, 20:audit=true, 30:audit=true]
result = [10, 20, 30]
~~~

Explanation:

1. **Flux.range(1,3)** is a synchronous source. When block() performs subscription on callingThread, the source emits 1, 2, 3 on the calling thread.
2. **hide()** here intentionally prevents **operator fusion** optimization at the source boundary. That makes the upstream signal-emitting thread clearly observable in the example; you do not need to add hide() in every real application.
3. **doOnNext before publishOn(transform)** records caller=true.
4. **map after publishOn(transform)** observes a thread name starting with transform-stage-, so transform=true, then multiplies the number by 10.
5. **doOnNext after publishOn(audit)** runs on a thread starting with audit-stage-, so audit=true.
6. **collectList().block()** lets the console program wait for the pipeline to complete before printing the lists. Thus stdout lines do not depend on interleaved thread logging order.
7. **CopyOnWriteArrayList** keeps recording safe across threads. For a small example it is simple and clear; do not default to it for very large data or high-frequency updates.
8. **dispose()** releases the two Schedulers created by the program. For shared Reactor Schedulers, do not arbitrarily dispose global schedulers belonging to the rest of the application.

### Why Not Print Directly Inside Each map?

If you place **System.out.println** directly across three stages running on different threads, lines can interleave according to OS scheduling. You should not document an "exact" stdout relying on unguaranteed print ordering. The example above **stores three separate lists** and prints them after block() finishes, confirming contents and order within each stage.

**Note on block():** Use it only at the boundary of an illustrative console program. In a Spring WebFlux request handler, return **Mono/Flux** and let the framework subscribe; do not use block() or blockLast() to fetch data synchronously on the event loop.

## 6. Placing publishOn Before vs. After map: A Crucial Difference

Placing publishOn **before** the computation:

~~~java
Flux<Integer> moved = Flux.range(1, 3)
        .publishOn(Schedulers.parallel())
        .map(this::expensiveCalculation);
~~~

With a normal source, **expensiveCalculation** runs on a parallel worker. If this computation is pure CPU work and significant enough, moving it off the event loop can be useful, though all elements of a single subscription are still processed sequentially on that worker.

Placing publishOn **after** the computation:

~~~java
Flux<Integer> notMoved = Flux.range(1, 3)
        .map(this::expensiveCalculation)
        .publishOn(Schedulers.parallel());
~~~

Now expensiveCalculation remains upstream. With a synchronous source like Flux.range, the computation can run right on the thread executing the source/subscription; the trailing publishOn only moves signals/results that have already been computed downstream.

An easy rule to remember:

**Place publishOn right before the region whose execution location you want to change**, not after a processing region that has already finished.

However, concluding "where it runs" requires checking preceding special operators as well. A source emitting signals on its own thread, Flux.interval, or a publisher dispatched via a network event loop may already introduce its own thread into the pipeline.

## 7. Which Scheduler to Choose for the Downstream Region?

Project Reactor provides multiple Schedulers with different goals:

| Scheduler | Target model | Appropriate usage |
| --- | --- | --- |
| **Schedulers.immediate()** | Executes on the current thread without switching to a separate pool | When no real scheduling boundary is wanted; not for isolating blocking |
| **Schedulers.single()** | One shared thread for tasks of the common single scheduler | Light sequential work, understanding contention risk with other subscriptions |
| **Schedulers.newSingle("name")** | Dedicated single-thread scheduler with application-managed lifecycle | Experiments, processing regions needing thread affinity or clear separation |
| **Schedulers.parallel()** | Pool with bounded workers, suited to fast non-blocking CPU work | Offloading CPU transform segments, not for prolonged blocking I/O |
| **Schedulers.boundedElastic()** | Boundedly elastic capacity for tasks that may block | Isolating unavoidable blocking APIs in a reactive system |
| **Schedulers.fromExecutorService(...)** | Uses an application-supplied ExecutorService | Integrating a custom pool with managed limits and lifecycle |

**parallel() does not turn a map into multi-threaded parallel processing** simply because multiple cores exist. It is a scheduling target. Processing multiple elements in parallel requires explicit concurrency design.

**boundedElastic() does not turn blocking JDBC or Thread.sleep() into non-blocking I/O.** It dedicates a more suitable execution environment for blocking segments, with bounded threads and queues; under overload, waiting and bottlenecks can still occur.

**single()** can become a bottleneck if multiple subscriptions push heavy tasks onto one thread; newSingle is not a default for every request. In real services, prefer shared Schedulers or lifecycle-managed Schedulers rather than creating newSingle on every HTTP request.

## 8. publishOn and Blocking Work: Placing the Boundary Correctly

### When You Must Call a Synchronous Library

With a method **blockingClient.fetch(id)**:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

This is an **illustrative snippet** in a project with Result and blockingClient types. **subscribeOn(boundedElastic)** fits because the fromCallable **source** itself invokes the blocking function on subscribe; source startup needs to be placed on a scheduler able to tolerate blocking.

If you have an already non-blocking source, yet a **subsequent step** must perform blocking processing:

~~~java
Mono<RemoteData> response = remoteClient.fetchReactive(id);

Mono<FinalData> result = response
        .publishOn(Schedulers.boundedElastic())
        .map(data -> legacyBlockingFormatter.format(data));
~~~

This is an illustrative snippet with application-defined remoteClient/legacyBlockingFormatter. publishOn sits **before** legacyBlockingFormatter, so that step is scheduled onto boundedElastic. Yet blocking still occurs on a boundedElastic thread; this is an API compatibility workaround, not a conversion into non-blocking I/O.

### Two Mistakes to Avoid

~~~java
// WRONG PLACEMENT: blocking work runs before publishOn.
Mono<Result> wrong = Mono.fromCallable(() -> blockingClient.fetch(id))
        .publishOn(Schedulers.boundedElastic());
~~~

A trailing publishOn does not retroactively move source creation before it. For fromCallable without subscribeOn, the blockingClient call can execute on the subscribing thread, including the event loop if used inside a reactive request.

~~~java
// Also insufficient: the source blocks right when creating the value!
Result value = blockingClient.fetch(id);
Mono<Result> tooLate = Mono.just(value)
        .publishOn(Schedulers.boundedElastic());
~~~

In the second example, Java already called blockingClient.fetch(id) **before creating the Mono**. No Reactor operator added afterward can undo a blocking operation that already happened.

## 9. publishOn Has Prefetch and a Queue: Impact on Backpressure

**publishOn** typically uses an internal queue to transfer signals from the upstream thread to the downstream worker. It may **request elements ahead of time (prefetch)** and replenish as items are consumed. Therefore, request counts at operator boundaries do not necessarily match 1:1 with requests from the final Subscriber.

A simple model:

~~~text
Upstream Publisher
       |
       | onNext per demand managed by publishOn
       v
  [publishOn queue]
       |
       | Scheduler worker receives signals
       v
  map / filter / downstream Subscriber
       |
       +--- downstream may process slower than upstream
~~~

Key points to understand:

- **publishOn must still honor the Reactive Streams contract**, managing demand and never emitting onNext to the Subscriber beyond requested items.
- **Prefetch** allows upstream to prepare more data to reduce per-element request overhead, but can hold some elements in the queue before downstream processes them.
- Overloads such as **publishOn(scheduler, prefetch)** exist to tune prefetch depth; specific values must match source behavior, latency, element size, and resources.
- **Prefetch is not a system-wide memory cap guarantee**: other operators, clients/brokers, and external sources still have their own queues or buffers.
- If an external source does not support slowing down, publishOn cannot force the external protocol to perform request(n). Explicit buffer/drop/error policies are needed at the adapter boundary.
- Adding more publishOn stages can add more queues, increasing latency, in-flight item count, and scheduling work.

Do not set prefetch to a single universal "optimal" number across all applications. Measure throughput, latency, queue depth, CPU, GC, and behavior when downstream slows down.

## 10. Interaction with Concurrency-Creating Operators

### flatMap with Asynchronous Sources

~~~java
Flux<Result> results = ids
        .flatMap(id -> remoteClient.fetchReactive(id), 8)
        .publishOn(Schedulers.parallel())
        .map(this::enrich);
~~~

This is an illustrative snippet: ids is a Flux of IDs, remoteClient.fetchReactive(id) returns a Publisher, and enrich is an application method.

**flatMap(..., 8)** can keep up to eight inner Publishers active concurrently according to the concurrency parameter; the trailing **publishOn(parallel)** only switches where enrich executes. Do not claim that publishOn creates eight asynchronous calls: concurrency comes from how **flatMap** coordinates Publishers and the client API.

### parallel().runOn(...)

~~~java
Flux<Integer> values = Flux.range(1, 100)
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(this::cpuBoundTransform)
        .sequential();
~~~

An illustrative snippet for CPU-bound cases divisible into independent tasks. **parallel(4)** splits data into four rails; **runOn** distributes rail processing onto a scheduler; **sequential()** merges back into a Flux. This is a different mechanism from publishOn. Check ordering, distribution, overhead, and whether the processing is genuinely heavy enough to benefit.

### A Single Subscription with One publishOn

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuBoundTransform);
~~~

This pipeline still has one sequential signal stream for that subscription. Having multiple threads in the parallel pool **does not mean 100 elements are automatically split into 100 tasks**.

## 11. Spring WebFlux, Reactor Netty, and the Event-Loop Boundary

In a Spring WebFlux application running on Reactor Netty, network I/O is typically dispatched via an **event loop**. The event loop is precious when operations are non-blocking; therefore, avoid blocking JDBC, Thread.sleep, or synchronous wait calls on those threads.

Example service holding a Publisher from a reactive HTTP client:

~~~java
public Mono<Report> buildReport(String id) {
    return webClient.get()
            .uri("/reports/{id}", id)
            .retrieve()
            .bodyToMono(ReportData.class)
            .publishOn(Schedulers.parallel())
            .map(this::computeReport);
}
~~~

This is an **illustrative service snippet** in a project that already has webClient, ReportData, and Report; not a standalone application. If computeReport is a relatively heavy yet non-blocking CPU computation, publishOn before map can help avoid tying up the network callback thread for that calculation.

**publishOn does not move the Netty socket to another Java thread to perform network I/O.** It switches *downstream signals* to a Scheduler worker. HTTP connection lifecycle, transport backpressure, and how the framework sends the response remain managed by their respective layers.

If computeReport is very heavy, a shared CPU Scheduler can stall; measure load and bound concurrency. If computeReport actually blocks on I/O, **parallel() is unsuitable**—choose a non-blocking API or boundedElastic for segments that must block.

### Controllers Should Return a Publisher

~~~java
@GetMapping("/reports/{id}")
public Mono<Report> getReport(@PathVariable String id) {
    return reportService.buildReport(id);
}
~~~

The framework manages subscription, errors, and cancellation along the request lifecycle. Avoid calling **subscribe()** manually or **block()** inside a controller to "make sure publishOn runs": that can detach the task from HTTP handling and defeat non-blocking benefits.

## 12. ThreadLocal, Reactor Context, and Logging Across publishOn Boundaries

When signals move from thread A to thread B, values stored in A's **ThreadLocal** **do not automatically appear** in B's ThreadLocal. Consequently, logging with MDC, trace IDs, request metadata, or security context can lose correlation if the application relies solely on traditional ThreadLocal.

Reactor provides **Context** attached to the subscriber to pass immutable information along the pipeline. Conceptual example:

~~~java
Mono<String> message =
        Mono.deferContextual(ctx -> Mono.just(
                "trace=" + ctx.getOrDefault("traceId", "unknown")
        ))
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(ctx -> ctx.put("traceId", "demo-123"));
~~~

This snippet returns a Mono carrying trace data after subscription without relying on ThreadLocal. **contextWrite** contributes context that upstream can read via **deferContextual**; Context propagation semantics are a separate topic to design alongside Spring Security/observability. **Do not confuse Reactor Context with automatically copying every ThreadLocal**.

If your application uses a tracing/MDC framework with context-propagation features, configure and test it for your exact stack; never assume publishOn always preserves or always drops every log field.

## 13. Errors, Cancellation, and Timeouts Crossing publishOn

A pipeline with publishOn still follows Reactor's **onNext, onError, onComplete** signals:

~~~java
Flux<Integer> source = Flux.just(1, 2, 3)
        .publishOn(Schedulers.parallel())
        .map(n -> {
            if (n == 2) {
                throw new IllegalArgumentException("invalid");
            }
            return n * 10;
        })
        .onErrorResume(error -> Flux.just(-1));
~~~

This is an illustrative snippet. When map hits n=2, the chain fails and **onErrorResume** switches to the fallback Publisher per the policy here. publishOn **does not swallow errors** and does not retry automatically.

Regarding cancel:

- If the Subscriber cancels, operators along the path must stop receiving/emitting per contract and release appropriate resources.
- Elements already requested/prefetched or scheduled work may still sit in a queue or be mid-flight. **Cancel is not a command that stops all external activity instantaneously.**
- If downstream work performs side effects, define retry/cancellation/idempotency policies; switching threads does not make an operation transactional.
- If a timeout is needed, apply **timeout(...)** per business requirements; publishOn does not set a request deadline by itself.

A very common mistake is assuming "once publishOn is used, block() can be called anywhere." **publishOn does not make block() safe on every thread**. If an operator runs on a non-blocking scheduler such as parallel/single, invoking Reactor blocking operations can be rejected or cause stalls. Use non-blocking APIs or isolate blocking segments properly.

## 14. Testing publishOn According to What Can Be Guaranteed

### Testing Pipeline Values

With the **reactor-test** dependency, StepVerifier can be used:

~~~java
StepVerifier.create(
        Flux.range(1, 3)
            .publishOn(Schedulers.parallel())
            .map(n -> n * 10)
)
.expectNext(10, 20, 30)
.verifyComplete();
~~~

This is a **snippet placed in a test with Reactor and reactor-test imports**, not a standalone Java program. It verifies **values/order/onComplete**, not exact thread names.

### Testing Execution Location

If the goal is to prove operators after publishOn switch to the specified Scheduler:

1. Use a **named Scheduler** managed by the test.
2. Record the thread or thread flag in **operators before and after** publishOn.
3. Synchronize until source completion with StepVerifier or a suitable mechanism.
4. Assert **the region before vs. the region after**, rather than comparing interleaved log lines from multiple threads.
5. Dispose of the test-created Scheduler.

The Java 17+ example above accomplishes this using two named schedulers and deterministically ordered recording lists. **Do not treat thread names like "parallel-1" as a public guarantee of the application**: names and allocation can change with configuration, version, or runtime. Check the Scheduler/worker at the signal emission point rather than relying on an arbitrary thread name.

### Load and Performance Cases to Test

- **CPU-bound**: measure map processing time before/after publishOn, throughput, and P95/P99 latency.
- **Blocking tasks**: verify they do not run on event loop/parallel and do not exhaust boundedElastic.
- **Slow downstream**: observe prefetch/queues, memory, backpressure, and cancellation.
- **Multiple subscriptions**: check whether the Scheduler suffers contention or worker starvation.
- **Multiple publishOn calls**: measure whether thread-switching overhead outweighs task-isolation benefits.
- **MDC/Context**: verify trace/request metadata stays accurate across boundaries.
- **Errors and cancellation**: ensure signals propagate properly without unintended duplicate subscriptions or side effects.

## 15. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "All operators in a Flux run on publishOn's thread." | **Only the downstream portion** is affected by that publishOn, up to another scheduling boundary. |
| "Placing publishOn after a blocking function moves that function." | Functions **before** publishOn may already have run; place the boundary before the step to move, or use subscribeOn for a blocking source. |
| "Schedulers.parallel() makes each onNext run in parallel with the others." | One publishOn typically uses **one worker per subscription**, keeping onNext sequential. |
| "publishOn and subscribeOn are interchangeable." | subscribeOn relates to subscription/source; publishOn switches downstream processing by position. |
| "Every publishOn always creates a new thread." | It picks a worker from the Scheduler; this may be a shared or dedicated thread depending on the Scheduler. |
| "publishOn makes I/O non-blocking." | Changing where work runs does not alter the nature of a blocking API. |
| "publishOn moves the WebClient/Netty network socket." | It switches downstream signal processing, without changing the network I/O event-loop mechanism. |
| "Adding more publishOn is always faster." | Queuing, scheduling, and context-switch overhead exist; measure performance. |
| "With publishOn, data cannot be lost and memory cannot fill up." | Backpressure/prefetch and external sources must be examined independently; large queues or overflow can still happen. |
| "ThreadLocal propagates automatically to every thread." | Reactor Context or a configured context-propagation mechanism is required. |
| "block() becomes safe because the scheduler was switched." | Blocking can still be disallowed/cause stalls on an unsuitable scheduler. |

## 16. Practical Checklist for Placing publishOn

When planning to add publishOn to a Spring WebFlux service, answer:

1. **Which operator truly needs to change execution location?** Place publishOn **before** that operator.
2. **Which thread is upstream emitting on?** Synchronous sources, event loops, fromCallable, Flux.interval, or sources with dedicated schedulers can differ.
3. **What kind of task follows?** Pure CPU, asynchronous I/O, or blocking I/O? Choose parallel, boundedElastic, or no switch accordingly.
4. **Is per-element parallelism needed?** If so, a single publishOn is not enough; design concurrency with appropriate operators.
5. **How many thread-switching boundaries exist?** Each publishOn can add a queue and overhead.
6. **Does context/trace follow the request?** Test MDC, tracing, and Reactor Context.
7. **Could the source be unbounded or downstream very slow?** Control prefetch, buffering, load limits, and cancellation.
8. **Do results/tests depend on thread names or log order?** Use named schedulers and synchronized observation rather than guessing from interleaved logs.

## 17. Key Takeaways

**publishOn(scheduler)** sets a **boundary that switches the thread processing downstream signals** in Reactor. Operators **before** publishOn are not retroactively moved; operators **after** typically receive signals on a worker of the chosen Scheduler **until the next publishOn**. **subscribeOn**, by contrast, targets the subscription stage and upstream startup.

**A single publishOn does not parallelize elements automatically, does not turn blocking I/O into non-blocking, and does not guarantee memory safety.** Match the Scheduler to the workload, place the boundary at the right spot, check prefetch, and measure real performance. In Spring WebFlux, protect the event loop with non-blocking APIs or proper blocking isolation, and return Mono/Flux for the framework to manage.

**References:**
- [Project Reactor Reference — Threading and Schedulers: publishOn and subscribeOn](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor Reference — How do I ensure thread affinity using publishOn?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Project Reactor API — Flux.publishOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
