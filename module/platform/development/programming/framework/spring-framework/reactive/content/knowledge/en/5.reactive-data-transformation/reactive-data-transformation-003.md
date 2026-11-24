# concatMap for Sequential Processing and Order Preservation in Reactor

## 1. Problem and Desired Outcome

In **Spring WebFlux** and **Project Reactor**, we often have a **Flux<T>** with multiple elements and want to transform each element into a task that may produce additional data or run asynchronously. For example:

- Receiving order IDs in exact order and calling a service to fetch details for each order.
- Writing changes sequentially to the same resource, where the previous step must finish before moving to the next step.
- Transforming each input item into a **Mono<R>** or **Flux<R>**, without letting results from different items interleave.
- Processing a list of tasks where completion order affects business outcomes.

The **concatMap** operator solves this case: **it maps each upstream element to an inner Publisher, subscribes to and processes those inner Publishers in order, and waits for the current inner to finish before moving to the next inner**. Consequently, downstream results preserve the order corresponding to the order of upstream elements.

This is a **mapping + flattening** operator. It does not just turn a **T** value into an **R** like **map**; it turns **T** into a **Publisher<R>** (usually a **Mono<R>** or **Flux<R>**) and merges the elements of each Publisher into a single **Flux<R>**, sequentially in order.

Visualization:

~~~text
Upstream:      A  ─── B ─── C
                │      │     │
concatMap:      f(A)   f(B)  f(C)
                │      │     │
Inner:        [a1 a2] [b1] [c1 c2]
                │      │     │
Downstream:    a1 a2  b1    c1 c2
               └──── wait for each inner to complete ────┘
~~~

**Important point:** the order here is **the order of onNext signals actually emitted by upstream**, not an automatic sort by key, record creation time, or database order.

## 2. Syntax and How to Read the Pipeline

For **Flux<T>**, the basic form is:

~~~java
Flux<R> output = source.concatMap(item -> innerPublisher(item));
~~~

Where:

- **source** is the input **Flux<T>**.
- **item** is each upstream element.
- **innerPublisher(item)** returns a **Publisher<? extends R>**, such as **Mono<R>** or **Flux<R>**.
- **output** is a **Flux<R>** containing the values emitted by those inner Publishers, in the order of the input items.

Example turning each number into two numbers:

~~~java
Flux.range(1, 3)
    .concatMap(n -> Flux.just(n * 10 + 1, n * 10 + 2))
    .subscribe(System.out::println);
~~~

Result:

~~~text
11
12
21
22
31
32
~~~

The source emits **1, 2, 3** in turn. Each element creates a **Flux** of two values. **concatMap** emits all values from the Flux for **1** first, then the Flux for **2**, and finally the Flux for **3**. If an inner Publisher is empty (for example **Mono.empty()**), it contributes no elements, and concatMap moves on to the next item.

For a simple, synchronous **T → R** transformation, prefer **map**:

~~~java
Flux<Integer> doubled = Flux.range(1, 3)
    .map(n -> n * 2);
~~~

Only choose **concatMap** when the mapping function returns a **Publisher** or when you need to serialize the execution of reactive tasks.

## 3. Sequential Mechanism: One Inner Publisher at a Time

One way to visualize the event flow:

~~~text
Source emits:     item A          item B          item C
                      │               │               │
concatMap             ▼               │               │
                 subscribe A          │               │
                 onNext(a1)           │               │
                 onNext(a2)           │               │
                 onComplete A         │               │
                                      ▼               │
                                 subscribe B          │
                                 onNext(b1)           │
                                 onComplete B         │
                                                      ▼
                                                 subscribe C
                                                 onNext(c1)
                                                 onComplete C
                                                 onComplete whole stream
~~~

In practice, upstream may emit ahead or concatMap may pre-request and temporarily buffer some items in a queue. **What is guaranteed is that inner Publishers are not subscribed to and emitted downstream overlapping in a way that alters the order managed by concatMap**: the next inner starts only after the previous inner has terminated. Details of prefetching, queueing, and scalar optimization depend on the Reactor version and operator configuration.

For each input item, concatMap:

1. Receives the item and invokes the mapper function to obtain the corresponding inner Publisher.
2. Subscribes to the selected inner Publisher.
3. Forwards that inner's elements downstream in the exact order the inner emits them.
4. Once the inner completes, moves on to the next item.
5. Once upstream has terminated and no running inner or queued items remain, emits **onComplete** downstream.

If an inner **never completes** (for example **Flux.never()**), concatMap can wait forever on that inner; subsequent items get no chance to be processed. Therefore, with I/O or external sources, think about timeouts, error handling, and cancellation mechanisms.

### "Sequential" Does Not Mean "All Code Runs on One Thread"

An inner may work asynchronously on a scheduler or use an external network service. **concatMap** serializes **the subscription/completion lifecycle of the inner Publishers it manages**; it does not force every callback to run on the same thread and does not turn already-started independent tasks into sequential tasks. Do not use the reasoning "it's concatMap, so it must be thread-safe" to skip synchronization for resources shared across multiple threads.

## 4. Comparing map, flatMap, flatMapSequential, and concatMap

| Operator | Mapping function returns | Can multiple inners be active concurrently? | Output order | Use when |
| --- | --- | --- | --- | --- |
| **map** | Value **R** | No concept of inner Publisher | Follows upstream order | Synchronous per-element transformation |
| **flatMap** | **Publisher<R>** | **Yes**, depending on concurrency | Can interleave and reorder across inners | Independent tasks, prioritizing throughput |
| **flatMapSequential** | **Publisher<R>** | **Yes**, subscribes to inners eagerly | Preserves emission order by upstream item; may buffer results | Want concurrency while still preserving result order |
| **concatMap** | **Publisher<R>** | **No**, one inner at a time | Preserves order and values of each inner do not interleave | Need sequential execution/subscription, avoiding multiple concurrent inners |

Suppose item 1 takes 300 ms, item 2 takes 50 ms, and item 3 takes 100 ms:

~~~text
flatMap (tasks run nearly concurrently):
    start 1 ───────────────────── complete 1
    start 2 ──── complete 2
    start 3 ─────────── complete 3
    Result order can be: 2, 3, 1

flatMapSequential (can run concurrently, preserves emission order):
    start 1 ───────────────────── complete 1
    start 2 ──── complete 2 (result is buffered)
    start 3 ─────────── complete 3 (result is buffered)
    Downstream result: 1, 2, 3

concatMap (waits for the previous task to finish):
    start 1 ───────────────────── complete 1
                                  start 2 ──── complete 2
                                               start 3 ─────── complete 3
    Downstream result: 1, 2, 3
~~~

The timelines above are illustrative only, not benchmarks. **flatMap** is not required to reorder results; if inners finish in the original order, it can also produce 1, 2, 3. The difference is that order across inners is **not guaranteed**. **flatMapSequential** guarantees emission order, but does **not** guarantee that each subtask executes sequentially. If the business goal is “finish updating order 1 before starting order 2”, **concatMap** usually expresses it more accurately.

**concat** or **concatWith** concatenate Publishers that are already known; **concatMap** uses a mapper to create a Publisher based on each upstream item. They share the idea of sequential chaining, but have different API inputs.

## 5. Example with Asynchronous Tasks: Order Is Never Inverted

The following example uses **Mono.delay** to simulate work completing after a duration; even though the work runs via a scheduler, concatMap still waits for each inner to finish:

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        Mono.delay(Duration.ofMillis(id == 1 ? 200 : 40))
            .map(tick -> "result-" + id)
    )
    .subscribe(System.out::println);
~~~

The snippet above illustrates usage in an environment that already has Reactor, requiring imports for **Flux**, **Mono**, and **Duration**. **subscribe** does not keep a CLI program waiting for an async source; in the complete example in section 8 we will use **blockLast()** at the program boundary to observe the full output.

Even though item 1 takes longer than item 2, concatMap only begins subscribing to item 2's inner after item 1's inner finishes. Thus the output will be in order:

~~~text
result-1
result-2
result-3
~~~

This is especially useful when ordering is a business requirement. Changing it to **flatMap** allows inners to be subscribed together, and an element that finishes early can appear first.

## 6. What "Preserving Order" Actually Means

concatMap preserves the order of **the items it receives**. It does not automatically solve ordering issues outside the operator's scope.

**Sources with non-deterministic order:** if data comes from a SQL query without **ORDER BY**, a multi-partition streaming API, or parallel producers, the onNext order can differ between runs. concatMap preserves *that actual order*, rather than inferring an order by id.

**One item producing multiple values:** if item A returns **Flux(A1, A2)** and B returns **Flux(B1, B2)**, the output is **A1, A2, B1, B2**, without interleaving A1, B1, A2, B2.

**One item returning Mono.empty():** that item produces 0 values without blocking the next item. Thus, preserving order does not mean the output must have the same number of elements as the input.

**Mapper returning Mono.error/Flux.error:** by default, an error from an inner terminates the entire sequence via **onError**; subsequent items may not be processed. There must be an explicit recovery strategy if you want to continue.

**Work already started outside the chain:** if before calling concatMap you already created and started multiple **CompletableFuture**s, HTTP requests, or side effects, combining the results with concatMap does not make those tasks start sequentially. Create the work lazily inside the mapper/Mono.defer if start order matters.

Risk example:

~~~java
// Tasks are created and may have already started before concatMap.
List<CompletableFuture<Result>> started = startAllRequests();

Flux.fromIterable(started)
    .concatMap(future -> Mono.fromFuture(future));
~~~

This snippet is pseudocode with hypothetical type **Result** and function **startAllRequests**. It only serializes retrieving the results of already-existing Futures, not the process of sending requests. If you truly need each request to start only after the previous request finishes, build the **Flux** from the input items and **create the request Mono inside the mapper**.

## 7. Errors, Timeouts, and Cancellation

### 7.1. Default Behavior: Errors Stop the Pipeline

~~~java
Flux.just(1, 2, 3)
    .concatMap(id -> {
        if (id == 2) {
            return Mono.<String>error(
                new IllegalArgumentException("invalid id: 2")
            );
        }
        return Mono.just("ok-" + id);
    })
    .subscribe(
        System.out::println,
        error -> System.out.println("error: " + error.getMessage())
    );
~~~

Output:

~~~text
ok-1
error: invalid id: 2
~~~

There is no **ok-3**, because the error in id 2's inner is a **terminal signal** for the whole pipeline. Thus, concatMap **preserves the order of elements actually emitted**, which does not mean it always processes every input item after an error.

### 7.2. Continuing Per Item: Recover Inside the Mapper

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        callService(id)
            .onErrorResume(error -> {
                logFailure(id, error);
                return Mono.just(fallbackFor(id));
            })
    );
~~~

This snippet assumes **callService**, **logFailure**, and **fallbackFor** are already defined; **callService(id)** returns **Mono<Result>** and **fallbackFor(id)** returns **Result**. When the error is converted into a fallback **right inside the inner**, the inner still completes normally and concatMap proceeds to the next item. If you do not want to emit a replacement value, you can recover with **Mono.empty()** (in which case the failed item contributes no data).

Conversely:

~~~java
source.concatMap(this::callService)
    .onErrorResume(error -> Flux.just(fallbackValue));
~~~

The **onErrorResume** operator placed *after concatMap* only replaces the remainder of an errored pipeline; it **does not go back** to continue unprocessed upstream items. Where you handle errors determines the behavior.

Reactor also has variants such as **concatMapDelayError** to defer propagating errors downstream under a specific contract. This is a different choice from per-item recovery; do not assume that delaying errors will turn a failed inner into a success value or always continue unconditionally. Choose explicitly based on business error requirements.

### 7.3. Preventing an Inner from Hanging Indefinitely

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        callService(id)
            .timeout(Duration.ofSeconds(3))
            .onErrorResume(error -> fallbackMono(id, error))
    );
~~~

This snippet assumes **callService** and **fallbackMono** return **Mono<Result>**. If the inner times out, it switches to the error path to produce a fallback, preventing the next item from waiting forever. The 3-second limit here is only illustrative; base it on your SLA, source characteristics, and application retry policy.

A **Flux.never()** inner or an unresponsive I/O request will stall concatMap's progress unless there is a termination mechanism. Use **timeout**, resource limits, and deadlines where appropriate.

### 7.4. Cancellation Does Not Mean Completion

When downstream cancels the subscription (for example, a WebFlux client disconnects, or **Disposable.dispose()** is called), concatMap requests cancellation of the upstream subscription and the active inner. Items still sitting in the queue may be dropped, while external work already started may not be undone. **cancel** does not automatically emit **onComplete**.

To observe the termination reason and clean up resources:

~~~java
Flux<Result> flow = source
    .concatMap(this::callService)
    .doFinally(signalType -> log("terminated: " + signalType));
~~~

This snippet uses hypothetical application functions/types. **doFinally** observes cases such as **ON_COMPLETE**, **ON_ERROR**, or **CANCEL**. Do not call **subscribe()** yourself in a WebFlux controller just to log; return the pipeline so the framework manages the subscription.

## 8. Runnable Java 17+ Example with Maven and Reactor

For deterministic output, the program uses synchronous **Flux.just/Flux.range** sources and asynchronous **Mono.delay**, waiting for completion with **blockLast()** in the **main** method. **blockLast()** in a CLI example is intentional; do not use this pattern on the WebFlux event loop.

Project structure:

~~~text
concatmap-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ConcatMapDemo.java
~~~

File **pom.xml** (example using stable Reactor 3.6.6 APIs):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>concatmap-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

File **src/main/java/ConcatMapDemo.java**:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ConcatMapDemo {

    public static void main(String[] args) {
        System.out.println("=== 1. Flatten in order ===");

        Flux.range(1, 3)
            .concatMap(id -> Flux.just(id * 10 + 1, id * 10 + 2))
            .doOnNext(System.out::println)
            .blockLast();

        System.out.println("=== 2. Async, one inner at a time ===");

        Flux.just(1, 2, 3)
            .concatMap(id ->
                Mono.delay(Duration.ofMillis(id == 1 ? 120 : 20))
                    .doOnSubscribe(s ->
                        System.out.println("start " + id)
                    )
                    .map(tick -> "item-" + id)
                    .doOnNext(item ->
                        System.out.println("finish " + id)
                    )
            )
            .doOnNext(item -> System.out.println("receive " + item))
            .blockLast();

        System.out.println("=== 3. Recover each inner ===");

        Flux.just(1, 2, 3)
            .concatMap(id -> {
                if (id == 2) {
                    return Mono.<String>error(
                            new IllegalArgumentException("invalid")
                        )
                        .onErrorResume(error ->
                            Mono.just("fallback-" + id)
                        );
                }
                return Mono.just("ok-" + id);
            })
            .doOnNext(System.out::println)
            .blockLast();
    }
}
~~~

Inside the **concatmap-demo** directory, with JDK 17+ and Maven. Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ConcatMapDemo
~~~

Expected stdout:

~~~text
=== 1. Flatten in order ===
11
12
21
22
31
32
=== 2. Async, one inner at a time ===
start 1
finish 1
receive item-1
start 2
finish 2
receive item-2
start 3
finish 3
receive item-3
=== 3. Recover each inner ===
ok-1
fallback-2
ok-3
~~~

Explanation:

- **Part 1:** each number creates a two-element Flux; concatMap outputs all elements of inner 1, then inner 2, then inner 3.
- **Part 2:** item 1 takes about 120 ms, items 2 and 3 take about 20 ms. Each **start** line appears after the previous inner signals completion; the **finish/receive** callbacks show the data order. Actual durations depend on the scheduler, yet the order remains guaranteed.
- **Part 3:** the error for id 2 is recovered right inside the inner, producing **fallback-2**, and then execution continues to **ok-3**. Moving **onErrorResume** outside after concatMap does not behave equivalently.
- **blockLast()** is only to keep the CLI program waiting for subscription and completion. In a Spring WebFlux application, return Mono/Flux to the framework and avoid calling block on the event loop.

The example does not rely on completion order among tasks running in parallel: concatMap itself enforces processing only one inner at a time.

## 9. Spring WebFlux Application: Sequential Task Processing

Suppose an application receives a **Flux<OrderId>** already sorted in the desired order. Each ID needs a service call via **WebClient**:

~~~java
public Flux<OrderDetails> fetchInOrder(Flux<OrderId> orderedIds) {
    return orderedIds.concatMap(id ->
        webClient.get()
            .uri("/orders/{id}", id.value())
            .retrieve()
            .bodyToMono(OrderDetails.class)
    );
}
~~~

This is a snippet inside a Spring bean with a configured **webClient**, using hypothetical application types **OrderId** and **OrderDetails**. **WebClient** returns **Mono<OrderDetails>**. Once subscribed, the application starts the next request only after the previous inner request completes, and emits results in input order.

This is not necessarily always the fastest choice: if each request waits 200 ms on the network and there are 100 elements, total cumulative wait time can be large. If the requirement is only **results emitted in order** while independent requests can run concurrently, consider **flatMapSequential** with an appropriate concurrency limit; if order is not needed, **flatMap** can deliver better throughput.

### 9.1. Ordering Rules Must Start at the Source

If **orderedIds** comes from a database, the code must explicitly request ordering, such as a query with **ORDER BY position, id** when appropriate for business logic. Reactor does not automatically sort records from an unordered query. If upstream receives events from multiple producers, you must design sequence numbering, reordering, or partitioning appropriately before concatMap.

### 9.2. Do Not Nest Subscriptions

Wrong in terms of chain management intent:

~~~java
// Wrong: the inner is a side effect started independently.
return orderedIds.concatMap(id -> {
    callService(id).subscribe(result -> save(result).subscribe());
    return Mono.just(id);
});
~~~

This example illustrates an architectural mistake with hypothetical methods. The outer **concatMap** only waits on **Mono.just(id)**, **not waiting for the manually subscribed callService/save**. As a result, actual task order is not guaranteed, errors are detached from the chain, and canceling the outer subscription does not necessarily cancel the inner tasks.

Proper composition:

~~~java
return orderedIds.concatMap(id ->
    callService(id)
        .flatMap(result -> save(result).thenReturn(id))
);
~~~

This example assumes **callService** returns **Mono<Result>**, **save** returns a Publisher that completes when saving finishes, and the desired result is the id. **concatMap** moves to the next id only when both **callService** and **save** of the current inner have completed. **flatMap** is used *inside an inner* to link two stages, without violating concatMap's serialization across ids.

### 9.3. Ordering Does Not Replace Transactions, Idempotency, or Concurrency Control

If multiple different HTTP requests call the same service simultaneously, they have **independent subscriptions**. concatMap on one request only serializes the inners within that request; it does not impose a global queue across all requests or all application instances. When updating shared data concurrently, you still need transactions, optimistic locking, idempotency keys, or an appropriate queue design.

Similarly, when receiving events from a high-rate hot source, serialization can cause **growing latency**. Evaluate capacity, timeouts, backpressure policy, input rate, and scalability; do not treat concatMap as durable storage.

## 10. Backpressure, Buffering, and Performance

**Reactive Streams** uses **request(n)** so downstream controls data demand. concatMap participates in this mechanism and may pre-request/buffer upstream items depending on configuration, while still honoring downstream demand. Therefore:

- **One active inner at a time** does not imply **O(1) memory usage**: upstream, the inner, schedulers, and other operators may maintain queues/buffers.
- **The number of items received from upstream** may exceed the number of items forwarded downstream at a given moment. Do not infer pipeline-wide demand from the count of onNext logs at a single point.
- **Inner emitting multiple elements**: every element of the current inner must obey downstream demand and be processed before any content from the next inner appears.
- **A slow inner** forces later items to wait, even though those later items could finish quickly if run concurrently.
- **Retry** is a separate policy. Placing **retryWhen** inside the mapper makes concatMap wait for retries of the current inner; placing it outside can resubscribe part of the pipeline and repeat earlier side effects.

When optimizing, choose based on actual conditions:

| Requirement | Initial choice |
| --- | --- |
| Synchronous transformation, no Publisher created | **map** |
| Operations must truly wait for one another to avoid out-of-order updates | **concatMap** |
| Can run concurrently, but the interface must output results in order | **flatMapSequential** with bounded concurrency |
| Order does not matter, want I/O concurrency | **flatMap** with bounded concurrency |
| Directly concatenate a known set of Publishers | **concat**, **concatWith** |

To measure performance, observe **total latency**, **concurrent task count**, **queues**, **p95/p99 latency**, and **errors** under realistic load. Do not use a tiny example with a few **Mono.delay** items as a throughput benchmark for WebClient or a database.

## 11. Common Mental-Model Mistakes

| Misconception or symptom | Correct understanding and fix |
| --- | --- |
| "concatMap is always faster than flatMap because there is no contention" | Sequential execution generally **reduces concurrency**; efficiency depends on workload and ordering needs. |
| "concatMap automatically sorts by id" | It preserves **upstream onNext order**, not sorting by key. |
| "flatMapSequential also processes sequentially" | It can subscribe to multiple inners at once and **buffer results** to emit in order. |
| "concatMap guarantees side effects outside Mono run sequentially" | Only work modeled inside the inner Publishers and subscribed within the lifecycle is serialized by the operator. |
| "If one Mono errors, concatMap automatically continues to the next item" | By default, an error stops the sequence; use per-inner recovery or an appropriate delay-error variant. |
| "onErrorResume after concatMap lets remaining elements continue" | It replaces the tail of the errored sequence; place recovery **inside the mapper** to continue per item. |
| "concatMap does not need a timeout" | An inner that never terminates can block every inner behind it. |
| "Only one inner means no need to care about buffers" | Upstream/other operators may still prefetch, queue, or hold data. |
| "Use concatMap to fix race conditions across all users" | Separate subscriptions/requests can still run concurrently. Shared data requires dedicated concurrency control. |
| "You can nest subscribe and return Mono.just" | concatMap only waits on the Publisher **returned from the mapper**, not side effects subscribed outside the chain. |
| "Use blockLast in a controller to wait for results" | WebFlux should return the pipeline; blocking on the event loop stalls I/O processing. |

## 12. Practice Exercises and Self-Check

**Exercise 1 – Predict the order.** Given:

~~~java
Flux.just("A", "B")
    .concatMap(s -> Flux.just(s + "1", s + "2"))
    .subscribe(System.out::println);
~~~

The result is **A1, A2, B1, B2**. Explanation: each inner emits two elements, and concatMap finishes inner A before starting inner B.

**Exercise 2 – Empty source.** If the mapper returns **Mono.empty()** for B in source A, B, C, what will the output be?  
**Answer:** there are no elements for B, yet concatMap continues to C after Mono.empty completes.

**Exercise 3 – Error at B.** If B returns **Mono.error**, will C be processed?  
**Answer:** by default, no. To continue to C, use recovery inside inner B or an intentionally chosen error-handling mechanism.

**Exercise 4 – Order vs. speed.** When receiving a list of 100 independent GET requests where only **returning results in order** is required, is concatMap mandatory?  
**Answer:** no. **flatMapSequential** allows requests to run concurrently while emitting results in order, at the cost of potentially buffering results while waiting for a slow leading request.

**Exercise 5 – Hidden side effects.** A source has three CompletableFutures already started beforehand; passing them into concatMap—does that guarantee the tasks start sequentially?  
**Answer:** no. You must create the work lazily inside the mapper or Mono.defer to properly control start timing.

**Exercise 6 – Experiment.** Modify the Java example in section 8: replace **concatMap** with **flatMap** in part 2 and increase the delay difference; run it several times and observe. Next, replace it with **flatMapSequential**. Record two things separately: the **start/finish order** of the inners and the **receive order** downstream. From there, explain why "preserving output order" differs from "sequential execution".

## 13. Key Takeaways When Designing Pipelines

Practical selection question: **"Is the next item allowed to start working before the current item finishes?"** If **no**, **concatMap** is the right operator to represent a sequential chain of inner Publishers. If **yes**, consider **flatMapSequential** or **flatMap** depending on output ordering requirements.

When using concatMap, check all four points: **the upstream source has the desired order**, **every side effect that must be awaited lives inside the Publisher returned by the mapper**, **errors/timeouts/cancellations are handled per business rules**, and **latency/buffering are observed under load**. Following these points preserves both data order and task lifecycle boundaries.

## 14. References

- Project Reactor — Transforming Sequences, API operator choices: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor — Flux.concatMap API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor — Backpressure and subscribe: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Spring Framework — Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html