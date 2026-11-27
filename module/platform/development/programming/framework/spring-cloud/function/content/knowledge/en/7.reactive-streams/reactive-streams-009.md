# Avoiding Thread Blocking and Choosing a Scheduler for Blocking Operations

## 1. The Problem: One Blocking Call Can Stall the Entire Stream

Suppose an order-status checking service is written with **Spring Cloud Function**. Business logic is packaged as a `Function<Flux<OrderEvent>, Flux<Decision>>` so the same logic can be invoked via HTTP, events, or serverless environments. A developer writes:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> decide = orders ->
    orders.map(order ->
        legacyClient.check(order) // Synchronous HTTP call, may block for 500 ms.
    );
~~~

`map` does not spawn a new thread. If the source `Flux` emits signals on an event-loop thread, `legacyClient.check(order)` may also execute **right on that event loop**. A call waiting on the network, JDBC, or `Thread.sleep` keeps that thread busy, forcing many other requests or messages sharing the thread to wait.

The keyword **reactive** does not automatically convert a synchronous library into an asynchronous one. To keep a system responsive, distinguish four concerns:

- **Non-blocking asynchronous logic:** use clients returning publishers like `Mono<Decision>` and compose them with Reactor operators.
- **Unavoidable blocking logic:** isolate it off threads that must not be blocked, typically with `Schedulers.boundedElastic()` and `Mono.fromCallable(...)`.
- **CPU-bound logic:** run heavy calculations on appropriate resources, avoiding both stalling the event loop and spawning excessive threads.
- **Load regulation:** bound concurrent tasks, queues, timeouts, and connections; changing the Scheduler does not replace capacity design.

This lesson focuses on **avoiding thread blocking and choosing a Scheduler for blocking operations** in the *Reactive Streams* chapter. The target is pure-business Spring Cloud Function beans, reusable via `FunctionCatalog`, composition, message conversion, and various adapters.

### Learning Objectives

After this lesson, you will be able to:

1. Identify blocking calls and understand why they are dangerous on event loops or non-blocking Schedulers.
2. Compare `Schedulers.immediate()`, `single()`, `parallel()`, and `boundedElastic()`.
3. Distinguish `subscribeOn` from `publishOn` and understand how they affect execution threads.
4. Wrap synchronous JDBC, SDKs, or REST clients lazily so they do not block the subscribing thread.
5. Compose blocking tasks into a `Flux` using `flatMap` or `concatMap` while controlling errors, order, and concurrency.
6. Recognize when to prefer a true reactive client over offloading blocking work.
7. Write unit tests verifying execution timing, execution threads, and error/completion signals.
8. Identify responsibility boundaries among functions, Schedulers, HTTP adapters, event binders, and serverless runtimes.

## 2. What Is “Non-Blocking,” and Where Does Blocking Happen?

A **blocking** piece of code forces the executing thread to wait on an external event or an unready resource. Typical examples:

~~~java
// Waiting for JDBC to return a result:
OrderRow row = jdbcRepository.findById(id);

// Waiting for an HTTP response via a synchronous API:
Decision decision = restTemplate.getForObject(url, Decision.class);

// Fixed wait:
Thread.sleep(500);

// Forcing an asynchronous publisher into a synchronous value:
Decision result = reactiveClient.check(order).block();
~~~

These operations prevent the thread from doing other work while waiting. By contrast, a proper reactive client represents “waiting for a result” as a publisher without occupying a thread for the duration of the I/O wait.

**Key point:** A reactive program still performs synchronous calculations. `map(String::trim)` is small, normal work. The problem is not “anything synchronous is wrong,” but rather **work that can block for a long time, consume excessive CPU, or behave unpredictably** on a thread meant to multiplex many streams.

### 2.1. How Does an Event Loop Work?

Runtimes like Reactor Netty typically use a bounded number of event-loop threads to handle many connections. Ideally, an event loop only runs short tasks: reading/writing when I/O is ready, dispatching callbacks, and forwarding signals.

~~~mermaid
flowchart LR
    R1["HTTP request A"] --> EL["Event-loop thread"]
    R2["HTTP request B"] --> EL
    R3["HTTP request C"] --> EL
    EL --> BAD["Blocking JDBC call 500 ms"]
    BAD --> WAIT["Other callbacks must wait"]
~~~

If one callback holds the thread for 500 ms, responsiveness for other requests on that thread can drop sharply. In practice, load tolerance also depends on event-loop thread count, workload profile, CPU, network, and application configuration.

### 2.2. Reactive Streams Does Not Solve Blocking Automatically

`Flux` and `Mono` represent publishers emitting `onNext`, `onError`, and `onComplete` signals. They do not dictate which thread each operation runs on.

~~~java
Flux<Integer> source = Flux.range(1, 3);

Flux<Integer> transformed = source.map(value -> {
    System.out.println(Thread.currentThread().getName());
    return value * 2;
});
~~~

When subscribed, callbacks inside `map` normally run on whichever thread emits the upstream signal, unless a Scheduler, asynchronous source, or operator switches execution context. `map`, `filter`, and `doOnNext` do not offload work automatically.

In Spring Cloud Function, `Function.apply(flux)` usually only builds the pipeline. Callback execution starts when the caller/adapter subscribes to the returned publisher. If the framework processes the `Flux` source on a sensitive thread, blocking inside callbacks can impact that very thread.

## 3. Distinguishing Pipeline Construction Time from Execution Time

An example with `Mono.fromCallable`:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<String> lazyLookup = Mono.fromCallable(() -> {
    calls.incrementAndGet();
    return blockingClient.fetch();
});

// Here calls is still 0.
Mono<String> configured = lazyLookup
    .subscribeOn(Schedulers.boundedElastic());

// Only upon subscription is the Callable executed.
// After a successful subscription, calls increases to 1.
~~~

`Mono.fromCallable` creates a *cold* publisher wrapping the call to make, instead of running `blockingClient.fetch()` immediately when `lazyLookup` is initialized. `subscribeOn` schedules upstream subscription onto the specified Scheduler, allowing the blocking call inside `Callable` to run on a thread meant for blocking.

**Conversely, the following snippet still blocks eagerly:**

~~~java
// Wrong: blockingClient.fetch() executes immediately when the expression is evaluated.
Mono<String> eager = Mono.just(blockingClient.fetch())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.just(...)` takes an **already-computed value**. By the time the Scheduler gets involved, the blocking call has already happened. This is the single most important bug to eliminate when migrating from imperative to reactive code.

### 3.1. defer and fromCallable

| Source factory | When does logic run? | When is it suitable? |
| --- | --- | --- |
| `Mono.just(value)` | Expression producing `value` runs before `just` is called | Value is already in memory, non-blocking |
| `Mono.fromCallable(() -> call())` | Calls `call()` upon subscription | Synchronous task returning a single value or possibly `null` |
| `Mono.fromRunnable(() -> action())` | Calls `action()` upon subscription | Synchronous `void` action turned into `Mono<Void>` |
| `Mono.defer(() -> monoFactory())` | Creates a fresh publisher per subscription | Source depends on current state or publisher selection logic |
| `Flux.defer(() -> fluxFactory())` | Creates a fresh `Flux` per subscription | Selecting or building a data source at subscription time |

`Mono.fromCallable` completes empty when the `Callable` returns `null`; if business logic treats “not found” as an error, handle `switchIfEmpty(...)` or use an explicit result type.

### 3.2. Re-Subscribing Can Invoke the Blocking Task Again

~~~java
Mono<String> source = Mono.fromCallable(blockingClient::fetch)
    .subscribeOn(Schedulers.boundedElastic());
~~~

With this cold publisher, every subscription can execute `fetch()` again. Therefore:

- Never assume a side-effecting call runs only once.
- When retrying or re-subscribing, evaluate idempotency.
- For database updates or money transfers, use proper business keys and transactional contracts.
- `cache()` changes replay behavior, but never treat it as a transaction mechanism or durable deduplication.

## 4. Common Schedulers in Project Reactor

`Scheduler` is an abstraction for executing and scheduling work. Common Schedulers include:

| Scheduler | Key characteristics | Use cases | Avoid using for |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Executes on the current thread, no thread switch | No scheduling needed, testing, or simple cases | Offloading blocking work |
| `Schedulers.single()` | Uses a single shared worker thread for sequential work | Short tasks needing serialization within an appropriate scope | Long-waiting blocking I/O |
| `Schedulers.parallel()` | Fixed CPU-sized thread pool for non-blocking computation | Short CPU-bound work, controlled parallel processing | JDBC, synchronous REST, `Thread.sleep`, or `block()` |
| `Schedulers.boundedElastic()` | Bounded elastic scheduler for blocking work | Bridging to legacy blocking libraries | Spawning work beyond target capacity, or treating it as true non-blocking I/O |
| Custom Scheduler | From `Schedulers.newBoundedElastic(...)` or a managed executor | Isolating resources of distinct legacy systems | Creating a new pool per event |

There is no single “best Scheduler for everything.” Selection depends on **blocking behavior**, **workload type**, **parallelism**, **lifecycle**, and **waiting tolerance**.

### 4.1. immediate: Never Leaves the Current Thread

~~~java
Mono.fromCallable(blockingClient::fetch)
    .subscribeOn(Schedulers.immediate());
~~~

This snippet **does not move blocking work off the caller thread**. `immediate` is not a fix for blocking; it executes work in the existing thread context.

### 4.2. single: Sequential Does Not Mean Fit for Slow I/O

~~~java
flux.publishOn(Schedulers.single())
    .map(this::quickTransform);
~~~

`single` helps when dispatching signals to a single worker thread for short tasks. However, a 2-second JDBC query on this worker blocks other unrelated tasks sharing that Scheduler. Having “just one thread” also does not guarantee business ordering across multiple subscriptions or instances; ordering still depends on the source and operators.

### 4.3. parallel: For CPU-Bound Work, Not Network Waits

~~~java
Flux<Integer> result = Flux.range(1, 100)
    .parallel()
    .runOn(Schedulers.parallel())
    .map(this::expensivePureComputation)
    .sequential();
~~~

`parallel()` creates a `ParallelFlux`, `runOn` assigns a Scheduler to its rails, and `sequential()` converts back to `Flux`. This fits pure computation that benefits from multiple CPU cores while tolerating ordering, overhead, and shared-state considerations.

**Warning:** This is not a solution for blocking I/O. A blocked `parallel` thread degrades CPU processing capacity and hurts other publishers sharing that Scheduler. Reactor also marks certain non-blocking threads to reject calls like `block()`.

### 4.4. boundedElastic: Default Choice for Isolating Legacy Blocking Calls

~~~java
Mono<Decision> decision = Mono
    .fromCallable(() -> legacyHttpClient.check(order))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Reactor designed `boundedElastic` for resource-bounded blocking tasks. Instead of spawning unbounded threads, it caps worker threads and queued tasks; exceeding capacity leads to deep queues or rejected scheduling errors.

Keep in mind:

- It **does not turn** a synchronous HTTP/JDBC call into non-blocking I/O.
- A thread remains occupied while the synchronous API waits for a response.
- If arrival rate exceeds processing rate over time, queues or latency still grow.
- You still need timeouts, I/O resource management, concurrency bounds, and monitoring.
- `Schedulers.boundedElastic()` is Reactor's shared Scheduler; do not create and dispose of a new default scheduler per element.

### 4.5. Virtual Threads Are a Conditional Configuration

On supporting Reactor/JDK versions, the bounded elastic implementation can use **virtual threads** when configured appropriately (e.g., Java 21+ and Reactor's bounded-elastic properties). However:

- Do not assume every Spring Boot/Reactor version enables or supports the same configuration.
- Virtual threads **do not turn blocking libraries into reactive I/O** and cannot raise throughput beyond database/API limits.
- Connection pools, timeouts, transactions, and admission policies remain necessary.
- With native methods, `synchronized`/pinning, or custom SDKs, real-world impact must be benchmarked.

For portable lessons and examples, start with standard `Schedulers.boundedElastic()`; switch implementations only after verifying versions and running benchmarks.

## 5. subscribeOn and publishOn: Two Placement Points Affecting Threads Differently

### 5.1. subscribeOn Governs Upstream Subscription

~~~java
Mono<String> result = Mono.fromCallable(() -> {
    log.info("fetch on {}", Thread.currentThread().getName());
    return blockingClient.fetch();
}).subscribeOn(Schedulers.boundedElastic());
~~~

Here the `Mono.fromCallable` source is subscribed on the chosen Scheduler, so the blocking call inside `Callable` runs on a bounded elastic worker.

When wrapping a blocking source, **placing `subscribeOn` directly after `fromCallable`** keeps the code readable and makes responsibility boundaries clear.

`subscribeOn` affects subscription/requests toward upstream in the pipeline. With multiple `subscribeOn` calls in one chain, do not expect every call to keep switching threads for the same source; the one closest to the source/upstream typically wins for that subscription phase. Design one clear boundary rather than stacking `subscribeOn` calls blindly.

### 5.2. publishOn Governs Downstream Signals

~~~java
Flux<Integer> output = Flux.range(1, 3)
    .map(n -> n * 2)
    .publishOn(Schedulers.parallel())
    .map(n -> heavyCpuTransform(n));
~~~

`publishOn` switches emission of `onNext`, `onComplete`, and `onError` to operators **after** it onto the chosen Scheduler within the pipeline's scope.

With multiple `publishOn` calls at different positions, each can trigger an execution context switch:

~~~java
Flux<String> output = source
    .publishOn(Schedulers.parallel())
    .map(this::cpuStep)
    .publishOn(Schedulers.boundedElastic())
    .map(this::blockingLegacyStep);
~~~

This illustrates thread boundaries. In production, however, it is usually better to **extract `blockingLegacyStep` into an independent lazy publisher using `fromCallable(...).subscribeOn(boundedElastic)`**, rather than shifting the entire downstream onto one Scheduler across every callback.

### 5.3. Quick Comparison Table

| Question | `subscribeOn(scheduler)` | `publishOn(scheduler)` |
| --- | --- | --- |
| Primary effect | On upstream subscription | On downstream signals from placement onward |
| Best suited when | `fromCallable` or `defer` source contains blocking work | Need to switch execution context for subsequent operators |
| Turns an eager source into lazy? | **No** | **No** |
| Automatically creates non-blocking network I/O? | **No** | **No** |
| Solves business ordering guarantees in brokers? | **No** | **No** |
| Can add overhead? | Yes, from scheduling | Yes, adds queue/thread switch/prefetch |

**Practical rule:** Prefer `Mono.fromCallable(blockingCall).subscribeOn(Schedulers.boundedElastic())` for **each blocking unit of work**; use `publishOn` when you genuinely need to switch execution context for a segment of a pipeline.

### 5.4. There Is No Promise That “Every Operator After subscribeOn Always Runs on boundedElastic”

Many sources have internal schedulers, are hot sources, or deliver callbacks from external SDKs. Even if subscribing to the source used `subscribeOn`, subsequent `onNext` signals may arrive on a thread managed by the source or driver itself.

Hence, placing `subscribeOn(boundedElastic)` at the end of a `Flux` composed of asynchronous sources **does not ensure every `map` above it runs on boundedElastic**. Whenever you need to offload a specific blocking call, wrap that call directly in a lazy publisher and apply the scheduler to that inner publisher.

## 6. Standard Pattern: Integrating a Synchronous REST/JDBC API into a Pipeline

Suppose we have a legacy client:

~~~java
public interface LegacyFraudClient {
    Decision check(OrderEvent event); // Synchronous, may block.
}
~~~

Wrong approach:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> bad =
    orders -> orders.map(legacyFraudClient::check);
~~~

Better approach:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> better =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyFraudClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

Explanation:

1. Each `OrderEvent` produces a lazy `Mono<Decision>`.
2. `fromCallable` defers the blocking call until subscription of the inner publisher.
3. `subscribeOn(boundedElastic)` shifts the blocking call onto the appropriate Scheduler.
4. `flatMap(..., 8)` bounds concurrent active inner publishers within a single subscription.
5. `flatMap` does **not** guarantee output order matches input `OrderEvent` order.
6. If the blocking call throws, the exception inside `Callable` becomes an `onError` signal on the inner publisher.

### 6.1. Complete Spring Cloud Function Example

The following examples use Java 17+ for `record`. They define a self-contained configuration class; `LegacyFraudClient` is an application interface backed by your synchronous library.

~~~java
package demo.scheduler;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Configuration
public class FraudFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public record Decision(String orderId, boolean approved) {}

    public interface LegacyFraudClient {
        Decision check(OrderEvent order); // Blocking I/O
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> checkFraud(
            LegacyFraudClient legacyClient) {

        return orders -> orders.flatMap(
            order -> Mono.fromCallable(
                    () -> legacyClient.check(order)
                )
                .subscribeOn(Schedulers.boundedElastic()),
            8
        );
    }
}
~~~

Spring injects `LegacyFraudClient` when a matching implementation bean exists. `@Bean` registers a `Function<Flux<OrderEvent>, Flux<Decision>>`; via `FunctionCatalog`, adapters can look up `checkFraud` and reuse the same logic across HTTP, message binders, or serverless.

Configuration selecting the function might be:

~~~properties
spring.cloud.function.definition=checkFraud
~~~

This only specifies which function is selected. It does not itself provision an HTTP server, broker, credentials, or retry policies; each adapter must be configured accordingly.

### 6.2. What If Results Must Follow Input Order?

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> ordered =
    orders -> orders.concatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
    );
~~~

`concatMap` waits for each inner publisher to complete before processing the next. Output preserves order within that subscription, and client calls are serialized at the publisher boundary. However, if the source spans multiple subscriptions or parallel instances, you cannot infer global external ordering from `concatMap`.

If only output emission needs ordering while business operations may run concurrently, `flatMapSequential` can serve as a middle ground; it does **not** guarantee side effects finish in order, and may buffer items while waiting for leading elements.

### 6.3. Wrapping a Query Returning a List

A blocking repository might return a list:

~~~java
public interface LegacyOrderRepository {
    java.util.List<OrderEvent> findPending();
}
~~~

Do not invoke it eagerly when constructing the publisher:

~~~java
// Wrong: findPending() executes before subscribeOn takes effect.
Flux<OrderEvent> wrong = Flux.fromIterable(
    repository.findPending()
).subscribeOn(Schedulers.boundedElastic());
~~~

Move list retrieval inside `Callable`:

~~~java
Flux<OrderEvent> pending = Mono
    .fromCallable(repository::findPending)
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
~~~

The entire list fetch executes upon subscription on the blocking Scheduler. Then the list is expanded into a `Flux` for downstream processing. Keep in mind:

- `findPending()` might return too many records, inflating heap usage even though offloaded.
- With streaming JDBC or lazy iterators, iterating can continue blocking after the initial query returns. Never treat the `fromIterable` pattern as sufficient for managing streaming `ResultSet`s.
- Pagination, batch limits, resource closing, and transactions remain necessary.
- A single query reading millions of rows does not become efficient just because it is wrapped in a `Flux`.

## 7. Prefer Reactive Clients Over Offloading Whenever Possible

If a true non-blocking library already exists, prefer it:

~~~java
public interface ReactiveFraudClient {
    Mono<Decision> check(OrderEvent order);
}

Function<Flux<OrderEvent>, Flux<Decision>> check =
    orders -> orders.flatMap(
        reactiveFraudClient::check,
        8
    );
~~~

`ReactiveFraudClient` can be implemented with `WebClient` or a reactive driver. In this case, requests are modeled natively as publishers; there is no reason to wrap a genuinely non-blocking client in `Mono.fromCallable` or route every call through `boundedElastic`.

| Scenario | Usually appropriate choice |
| --- | --- |
| Synchronous HTTP client like `RestTemplate` or blocking SDK | Wrap lazily with `Mono.fromCallable` + `boundedElastic`, or migrate to a non-blocking client |
| Reactive HTTP client like `WebClient` | Return/compose `Mono` directly, bounding concurrency and timeouts |
| Synchronous JDBC | Isolate on bounded elastic, consider pagination and transactions |
| R2DBC/reactive repository | Use driver publishers directly, avoid `block()` |
| Short pure CPU computation | Normal `map`, no offloading needed |
| Heavy independent CPU work | `parallel`/appropriate Scheduler, measure CPU and ordering |
| `Thread.sleep` to simulate delay | Use `Mono.delay` for time simulation instead of tying up threads |

### 7.1. WebClient Example

~~~java
public Mono<Decision> check(OrderEvent order) {
    return webClient.post()
        .uri("/risk/check")
        .bodyValue(order)
        .retrieve()
        .bodyToMono(Decision.class);
}
~~~

This is a sample method inside a class with `WebClient webClient`, `OrderEvent`, and `Decision` already declared. `bodyToMono` returns a publisher describing the request/response; HTTP status error handling, timeouts, retries, and connection limits must be designed appropriately.

Never call:

~~~java
Decision decision = check(order).block(); // Defeats non-blocking execution.
~~~

inside `map` or a reactive function subscribed to by an adapter. Compose publishers with `flatMap` or `concatMap` instead.

## 8. Concurrency Limits, Backpressure, and Queues

Offloading keeps the application from blocking the event loop, yet **does not solve a source producing faster than downstream can process**.

Suppose a database handles at most 20 concurrent queries efficiently. If input has 100,000 events, immediately scheduling 100,000 `boundedElastic` tasks causes long waits, exhausts the connection pool, and saturates queues.

### 8.1. flatMap with Bounded Concurrency

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> limited =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

`8` limits concurrent inner publishers for **one subscription at this operator**. With 10 independent streams or 10 instances, total active tasks can be far higher. You must also manage connection pools, consumer counts, API quotas, and instance counts.

### 8.2. Backpressure Differs from Concurrency

- **Backpressure:** downstream uses `request(n)` to express element demand.
- **Concurrency limit:** maximum number of inner publishers running concurrently.
- **Scheduler queue:** tasks already scheduled but awaiting a worker.
- **Rate limit:** how many new invocations may start within a time window.
- **Database connection pool:** limit on concurrent active connections.

These five aspects are related yet non-interchangeable. Setting `flatMap(..., 8)` does not guarantee at most eight requests cluster-wide or eight requests/second. Nor does it guarantee a broker slows down when Reactor lowers demand if the binder cannot propagate backpressure to the broker.

### 8.3. Never Use Unbounded Buffers to Hide Overload

~~~java
Flux<OrderEvent> queued = source.onBackpressureBuffer();
~~~

An unbounded queue on a high-rate stream risks out-of-memory failure. Especially for orders or payments, `onBackpressureDrop` and `onBackpressureLatest` can lose data, so never apply them just to “silence overflow errors.”

When complete processing is mandatory, prioritize durable sources (brokers/outboxes), configure binder read/pause/ack controls, use bounded buffers, and process with checkpoints/idempotency.

### 8.4. Real Load Limits of boundedElastic

`Schedulers.boundedElastic()` isolates I/O waits from the event loop, yet it still has worker and queue limits. When limits are exceeded, scheduling may be rejected or latency will climb. Never assume the scheduler scales infinitely with event volume.

Monitor concurrently:

- End-to-end event latency.
- Database/HTTP connection wait times.
- Active in-flight queries/requests.
- Pending jobs and queue dwell times.
- CPU, memory, and thread/virtual-thread counts per configuration.
- Timeout errors, queue saturation, and retry rates.

## 9. Managing a Custom Scheduler Instead of Sharing One for All Blocking Work

In large applications, a very slow blocking SDK can consume much of the default `Schedulers.boundedElastic()` capacity and starve other workloads. You can dedicate a custom Scheduler with explicit bounds:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    public Scheduler legacyDatabaseScheduler() {
        // At most 8 backing threads; bounded task queue.
        return Schedulers.newBoundedElastic(
            8, 1000, "legacy-db"
        );
    }
}
~~~

Injecting the scheduler:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkUsingLegacyDb(
        LegacyFraudClient client,
        Scheduler legacyDatabaseScheduler) {

    return incoming -> incoming.flatMap(
        order -> Mono.fromCallable(() -> client.check(order))
            .subscribeOn(legacyDatabaseScheduler),
        8
    );
}
~~~

The second snippet is a `@Bean` method inside a configuration class with `Function`, `Flux`, `Mono`, `Scheduler`, `OrderEvent`, `Decision`, and `LegacyFraudClient` imported. These patterns can be integrated into the `FraudFunctions` class from Section 6.

**Never call `Schedulers.newBoundedElastic(...)` per element.** Doing so creates excessive schedulers/threads, leaks lifecycles, and breaks resource bounds. A custom scheduler should be an application-scoped bean or lifecycle-managed component, disposed of on shutdown.

### 9.1. Bounded Elastic Does Not Replace Target-Service Bulkheads

An eight-thread limit does not guarantee only eight queries hit the database if the same client is used elsewhere or a single request triggers extra work outside that scheduler. Across multiple instances, total demand still multiplies. Coordinate:

1. Connection pool size and connection-acquisition timeouts.
2. Function-level concurrency limits.
3. Quotas at the destination service.
4. Queues, circuit breakers, or bulkheads where needed.
5. Partitioning/coordination across instances.

## 10. JDBC Transactions and Thread-Switching Limits

Traditional synchronous transaction APIs typically bind context to a thread, such as `ThreadLocal` in many transaction managers. Reactive execution can hop threads across operators, so never assume “adding `subscribeOn` keeps every transactional step on the same thread.”

### 10.1. Grouping Blocking Work Belonging to One Transaction

If you must keep synchronous JDBC transactions, wrap **the entire blocking block sharing one transaction** inside a single synchronous unit and offload that unit as a whole:

~~~java
Mono<Receipt> saveAtomically(OrderEvent order) {
    return Mono.fromCallable(() ->
        transactionTemplate.execute(status -> {
            legacyOrderRepository.insert(order);
            return legacyAuditRepository.appendAndCreateReceipt(order);
        })
    ).subscribeOn(Schedulers.boundedElastic());
}
~~~

`transactionTemplate`, both repositories, and `Receipt` are application dependencies/DTOs. The point is keeping synchronous steps sharing one transaction inside the `Callable` callback. If the transaction callback returns `null`, `Mono.fromCallable` completes empty; define the result contract explicitly.

Reactive transactions using R2DBC propagate context differently from thread-bound JDBC transactions. Never mix models arbitrarily; verify the transaction manager and driver in use.

### 10.2. Do Not “Split a Transaction” Across Multiple publishOn Calls

~~~java
// Dubious design with thread-bound synchronous transactions:
source.publishOn(Schedulers.boundedElastic())
    .map(order -> jdbcRepository.insert(order))
    .publishOn(Schedulers.parallel())
    .map(order -> jdbcRepository.updateAudit(order));
~~~

The two operations can run on different threads; if relying on a thread-bound transaction, data integrity can break. If both operations require one transaction, group them into a single unit of work or migrate cleanly to a compatible reactive transaction solution.

### 10.3. Cancellation Does Not Guarantee External Rollback

When a subscriber cancels `Mono.fromCallable(...)`, Reactor stops emitting downstream results, yet an already-started blocking JDBC or SDK call **may continue running** until the driver returns. Never assume `cancel` aborted the query or rolled back the transaction.

Therefore:

- Configure timeouts on the database/HTTP client itself, not only on the publisher.
- Distinguish “the caller stopped listening” from “the operation never happened.”
- Use idempotency keys if retries can duplicate writes.
- For critical events, verify state after errors/cancellations according to business rules.

## 11. Timeouts, Errors, and Retries in Offloaded Pipelines

### 11.1. Per-Operation Timeouts

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> checked =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(2)),
        8
    );
~~~

`timeout` emits an error if the publisher fails to produce a value/terminal signal within the limit per operator semantics. However, if the blocking SDK ignores interruption/cancellation, the background call **may still hold the thread** after timeout. Configure timeouts on the HTTP client/JDBC driver as well as connection management.

### 11.2. Per-Element Recovery vs. Whole-Stream Recovery

If each event may be marked “indeterminate,” handle errors inside the inner publisher:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> resilient =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(order.orderId(), false))
            ),
        8
    );
~~~

Assume `false` here is a business-approved *fail closed* rule. If you must distinguish legitimate business rejections from check failures, use a DTO with `status = UNAVAILABLE` rather than collapsing all errors into rejection.

If `onErrorResume` sits outside the entire `flatMap`, an error may have already terminated the source subscription; an outer fallback **does not automatically resume from the next element**.

### 11.3. Retries Require Bounds and Idempotency

~~~java
Mono<Decision> oneOrder = Mono.fromCallable(
        () -> legacyClient.check(order)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, Duration.ofMillis(200)
        )
    );
~~~

`retryWhen` re-subscribes to upstream after failure per policy. With `fromCallable`, it can **re-invoke the blocking client**. If the call has side effects and the first response was lost, retries can cause duplicate execution. Design idempotency and only retry appropriate error types.

Beware of “retry storms”: many concurrent failures all retrying together can overwhelm an already-struggling dependency. Bound concurrency, apply backoff with jitter, and consider circuit breakers/bulkheads.

## 12. Finite Streams, Continuous Streams, and Scheduler Lifecycle

A finite source such as `Flux.just(...)` processes a few orders and emits `onComplete`. By contrast, `Supplier<Flux<T>>` can return a continuous source like `Flux.interval(...)` or a broker stream, keeping a subscription alive long-term.

### 12.1. Never Let Blocking Tasks Pin Threads Indefinitely

A hung callback inside `Mono.fromCallable` can occupy a bounded elastic worker far longer than intended. On continuous streams, as new events keep arriving, stuck tasks pile up until queues fill or timeouts fire.

Solutions span multiple layers:

- SDK/driver timeouts.
- Task and connection limits.
- Error classification and isolation for stalled services.
- Queue dwell-time and active-task monitoring.
- A graceful shutdown strategy to stop accepting new events and await/cancel in-flight tasks.

### 12.2. Do Not Call subscribe() Inside Function When You Can Return a Publisher

~~~java
// Wrong design direction: work runs outside the caller's management.
Function<Flux<OrderEvent>, Flux<Decision>> hiddenWork = orders -> {
    orders.flatMap(order ->
        Mono.fromCallable(() -> legacyClient.check(order))
            .subscribeOn(Schedulers.boundedElastic())
    ).subscribe();

    return Flux.empty();
};
~~~

Calling `subscribe()` separately creates a subscription detached from the returned publisher. The caller sees the output finish immediately while work continues in the background; errors and cancellation become hard to coordinate cleanly.

Instead:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> visibleWork =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            ).subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

By returning the publisher, the caller/adapter can manage the subscription and observe signals.

### 12.3. Consumer<Flux<T>> Requires Separate Consideration

Because `Consumer<Flux<T>>` returns `void`, the framework has no resulting publisher to subscribe to. In some Spring Cloud Function/Stream integrations, an explicit reactive consumer must subscribe itself and manage `Disposable`, errors, and lifecycle.

If the goal is asynchronous processing that **signals completion/failure without returning a payload**, `Function<Flux<T>, Mono<Void>>` with `then()` expresses the contract more clearly:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> audit =
    events -> events
        .concatMap(event ->
            Mono.fromRunnable(
                () -> legacyAuditStore.persist(event)
            )
            .subscribeOn(Schedulers.boundedElastic())
        )
        .then();
~~~

`legacyAuditStore.persist(event)` is a blocking `void` method. `then()` completes only once a finite source and all inner tasks finish; with an infinite source, `Mono<Void>` emits no end-of-stream completion signal while the source remains active.

## 13. ThreadLocal, MDC, Tracing, and Context Across Scheduler Switches

Switching threads changes how thread-bound data behaves. Example:

~~~java
requestContext.set("trace-123"); // ThreadLocal on the current thread.

Mono<Decision> result = Mono.fromCallable(() -> {
    // Does not automatically see the caller's ThreadLocal value.
    return legacyClient.check(order);
}).subscribeOn(Schedulers.boundedElastic());
~~~

Never assume `ThreadLocal`, MDC logging, or security context from the caller thread automatically appears on a bounded elastic thread. In Reactor apps, **Reactor Context** carries metadata along a subscription; bridging to ThreadLocal/MDC requires a context propagation mechanism compatible with your Spring/Reactor version and tracing library.

### 13.1. Reactor Context for Subscription Metadata

~~~java
Mono<String> task = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "unknown");

    return Mono.fromCallable(() ->
        legacyClient.fetchWithTrace(traceId)
    ).subscribeOn(Schedulers.boundedElastic());
}).contextWrite(ctx -> ctx.put("traceId", "trace-123"));
~~~

This pattern reads `traceId` from Reactor Context and passes it **explicitly** to the blocking method. It does not require `ThreadLocal` to migrate across threads automatically.

Across message brokers, headers like `correlationId` or `traceId` may need to be mapped via `Message<T>` metadata and written into Reactor Context at the adapter boundary. That depends on your active stack; never mistake a single subscription's context for per-message context automatically.

### 13.2. SecurityContext and Transaction Context

Do not rely on custom `ThreadLocal` values as a source of truth for security or transactions after multiple `publishOn` switches. Use your framework's official context propagation APIs and appropriate (reactive or imperative) transaction managers.

For example, synchronous JDBC writes inside a `Callable` with synchronous transactions can stay bound to that callback's thread; switching threads mid-transaction can corrupt behavior.

## 14. Testing Lazy Execution and Execution Threads with StepVerifier

`StepVerifier` triggers a subscription and observes completion/error signals. You can use it to prove a blocking operation is **deferred until subscribe** and **executed on a different thread**.

### 14.1. A Task Running on a Scheduler Instead of the Test Thread

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingSchedulerTest {

    @Test
    void callableIsLazyAndRunsOnBoundedElastic() {
        Thread testThread = Thread.currentThread();
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Thread> executedOn = new AtomicReference<>();

        Mono<String> source = Mono.fromCallable(() -> {
            calls.incrementAndGet();
            executedOn.set(Thread.currentThread());
            return "ORD-101";
        }).subscribeOn(Schedulers.boundedElastic());

        assertEquals(0, calls.get());

        StepVerifier.create(source)
            .expectNext("ORD-101")
            .verifyComplete();

        assertEquals(1, calls.get());
        assertNotSame(testThread, executedOn.get());
    }
}
~~~

This test verifies only the specific Reactor behavior in the snippet. It **does not** test peak load, JDBC timeouts, context propagation, or end-to-end adapter behavior.

### 14.2. Exceptions Inside Callable Become onError

~~~java
@Test
void checkedExceptionIsAnErrorSignal() {
    Mono<String> source = Mono.<String>fromCallable(() -> {
        throw new java.io.IOException("legacy service unavailable");
    }).subscribeOn(Schedulers.boundedElastic());

    StepVerifier.create(source)
        .expectErrorMatches(error ->
            error instanceof java.io.IOException
                && error.getMessage().contains("unavailable"))
        .verify();
}
~~~

You do not need `try/catch` around `source` just to capture errors; if an exception occurs **upon subscription**, it enters the `onError` signal.

### 14.3. Testing Bounded Concurrency

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@Test
void innerBlockingCallsHaveBoundedConcurrency() {
    AtomicInteger active = new AtomicInteger();
    AtomicInteger peak = new AtomicInteger();

    Flux<Integer> pipeline = Flux.range(1, 12)
        .flatMap(item ->
            Mono.fromCallable(() -> {
                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                try {
                    // Simulating blocking in a unit test only;
                    // work is offloaded onto boundedElastic.
                    Thread.sleep(15);
                    return item;
                } finally {
                    active.decrementAndGet();
                }
            }).subscribeOn(Schedulers.boundedElastic()),
            3
        );

    StepVerifier.create(pipeline.collectList())
        .assertNext(values -> assertEquals(12, values.size()))
        .verifyComplete();

    assertTrue(peak.get() <= 3);
}
~~~

This tests **concurrency limits within one subscription**, not total threads across the entire JVM or cluster. The test uses `Thread.sleep` to simulate a blocking SDK and properly offloads it onto the Scheduler; in production applications, prefer non-blocking clients.

### 14.4. Testing with BlockHound Is Optional

In supported environments, **BlockHound** can help detect blocking APIs invoked on threads marked as non-blocking. However:

- It requires dependencies and test integration compatible with your active JVM and Reactor versions.
- Additional configuration may be needed, especially for agents/instrumentation.
- Not every blocking behavior in third-party libraries is detected.
- It does not replace load testing, profiling, or transaction/driver verification.

Do not scatter `BlockHound.install()` into arbitrary tests if your project lacks proper configuration and version support; integrate it deliberately in a suitable test suite.

## 15. Signs of Thread Contention in Production

Common symptoms:

| Symptom | Likely cause | How to investigate |
| --- | --- | --- |
| HTTP p99 spikes despite low CPU | Event loop stalled by blocking I/O | Thread dumps, profilers, stack traces |
| Many pending requests yet flat throughput | Connection pool or target resource saturated | Pool metrics, timeouts, pending acquisition times |
| Still slow after moving to boundedElastic | Blocking work saturates workers/queues | Task execution duration, queued tasks, capacity |
| Random request timeouts | Retry storms or deep queues | Timing milestones across pipeline and clients |
| `IllegalStateException` on `block()` | Blocking API called on a thread marked non-blocking | Search for `block()`, `blockFirst()`, `blockLast()` on call paths |
| Logs lose `traceId` across Scheduler switches | Metadata relies on `ThreadLocal` | Reactor Context / context propagation |
| DB queries keep running after cancellation | Blocking driver cannot abort immediately | Client query timeouts, transaction/connection cleanup |
| Duplicate order processing after error | Retries/resubscriptions on cold sources or broker redelivery | Idempotency keys, offsets, transactions |
| Appears only under high production load | Connection/instance counts exceed test setups | Load tests, capacity planning, per-instance limits |

A thread dump may reveal stacks waiting on sockets, `LockSupport.park`, JDBC, or sleep. Yet `WAITING` is not always a bug: idle workers also wait for tasks. Correlate stack traces with latency and throughput context.

### 15.1. Metrics Worth Monitoring

- **Latency:** p50/p95/p99 of APIs, queries, I/O tasks, and end-to-end event processing time.
- **Resources:** CPU, heap, thread counts, active/pending connection pool stats.
- **Scheduler/queues:** pending task counts, queue length, and queue wait times where instrumented.
- **Publishers:** active subscriptions, processed event counts, completions/errors/cancellations.
- **Reliability:** timeouts, retries, dead-letters, redeliveries, and duplicate counts.
- **Brokers:** lag, prefetch, partition/consumer counts, and binder acknowledgment milestones.

Avoid logging details of every element at high throughput just to observe performance; synchronous logging I/O itself can choke the pipeline.

## 16. When the Same Function Runs via HTTP, Events, or Serverless

A key benefit of Spring Cloud Function is **keeping business logic intact** while swapping adapters. However, thread and completion responsibilities vary across environments.

~~~mermaid
flowchart TD
    CALL["HTTP / Event binder / Serverless"] --> CAT["FunctionCatalog"]
    CAT --> FUNC["Function<Flux<T>, Flux<R>>"]
    FUNC --> ASYNC["Mono.fromCallable(blockingCall)"]
    ASYNC --> SCH["subscribeOn(boundedElastic)"]
    SCH --> OUT["Result publisher"]
    OUT --> ADAPTER["Adapter subscribes, serializes/sends"]
    ADAPTER --> DEST["Client / broker / runtime"]
~~~

### 16.1. Calling Over HTTP

With an HTTP adapter on a reactive stack, the function may receive a publisher from the request body and return a publisher as the response. Never place blocking calls directly inside `map` on the event loop; offload each blocking call or use a reactive client instead.

A client-aborted request can trigger subscription cancellation, yet an external blocking operation may already have committed data. Define HTTP statuses, timeouts, and client retry policies explicitly—never rely on request cancellation to prove side effects never occurred.

### 16.2. Consuming Events via Spring Cloud Stream

When wired to an event binder, the framework may feed messages per element or establish a long-lived reactive pipeline. `Function<Flux<T>, Flux<R>>` may be applied once to a `Flux` carrying many events; callbacks inside operators run as items arrive.

**Never infer that Reactor backpressure propagates to Kafka/RabbitMQ or that broker dispatch waits for every `Mono.fromCallable` to finish.** Binders, consumer prefetch/polling, acknowledgments, and error handling must be verified on your exact version.

If the function returns `Flux<R>`, the adapter owns a resulting publisher to manage the subscription. If you call `subscribe()` inside the function and return an empty publisher, the adapter can misread when processing finished.

### 16.3. Serverless

Serverless runtimes enforce invocation time and resource limits. Pushing a 30-second JDBC call onto boundedElastic does not extend the invocation timeout. Configure timeouts and element bounds so the publisher completes before the runtime terminates the invocation.

Never trust a fire-and-forget `subscribe()` to keep running safely after a serverless function returns; the runtime may freeze or tear down the execution environment.

### 16.4. Composition Does Not “Fix” Blocking

Suppose we have two beans:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validate() {
    return events -> events.filter(e -> e.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkFraud(
        LegacyFraudClient client) {
    return events -> events.flatMap(
        e -> Mono.fromCallable(() -> client.check(e))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

You can select the composition:

~~~properties
spring.cloud.function.definition=validate|checkFraud
~~~

`FunctionCatalog` supports name lookup and composition when signatures match. Even so, **composition does not automatically detect blocking calls and switch threads**. Each function must place proper scheduling boundaries inside its own pipeline.

## 17. Solution Selection Workflow

~~~mermaid
flowchart TD
    START["Need to run an operation inside Flux/Mono"] --> Q{"Can the operation block?"}
    Q -->|No, small computation| MAP["Direct map/filter"]
    Q -->|I/O with reactive API| REACTIVE["flatMap/concatMap non-blocking publisher"]
    Q -->|Yes, only blocking SDK/JDBC exists| WRAP["Mono.fromCallable/fromRunnable"]
    WRAP --> SCHED["subscribeOn(boundedElastic)"]
    SCHED --> LIMIT["Bound concurrency,\ntimeouts, pools, and queues"]
    MAP --> TEST["Test subscription,\nerrors, load, and adapter"]
    REACTIVE --> TEST
    LIMIT --> TEST
~~~

To choose correctly, ask yourself:

1. **Where does blocking actually occur?** Database reads, HTTP waits, sleep, lock waits, or pure CPU?
2. **Is a non-blocking API available?** If yes, compose its publishers directly.
3. **Which thread is currently executing?** Event loop, parallel, bounded elastic, or an external source thread?
4. **Is the call truly lazy?** `Mono.just(blockingCall())` still blocks immediately.
5. **Who subscribes?** Spring Cloud Function adapter, test, or code subscribing out-of-band?
6. **What is the concurrency?** One `flatMap` opens many tasks; cluster-wide load is even larger.
7. **What do errors, timeouts, and cancellations mean?** External work may finish even if the subscriber never gets the response.
8. **Where do transactions live?** For thread-bound JDBC, ensure transactions are scoped within a coherent unit.
9. **Which context must propagate?** Do tracing, security, or tenant IDs rely on `ThreadLocal`?
10. **Have load and adapters been tested?** Reactor unit tests do not replace real DB/broker tests.

## 18. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “Using `Flux` makes all code non-blocking.” | `Flux` does not alter the blocking nature of code inside callbacks. |
| “Adding `subscribeOn` after `Mono.just(blockingCall())` is enough.” | The call already ran before `just` received the value; use a lazy source. |
| “`Schedulers.parallel()` is the best pool for JDBC.” | `parallel` is for CPU/non-blocking work; bounded elastic fits legacy blocking calls better. |
| “`Schedulers.immediate()` leaves the event loop.” | `immediate` executes on the current thread. |
| “`publishOn` and `subscribeOn` do the same thing.” | One switches downstream signals; the other mainly affects upstream subscription. |
| “boundedElastic creates infinite threads whenever needed.” | It is a bounded scheduler; queues and load can still saturate. |
| “Setting `flatMap(..., 8)` limits the whole cluster to eight requests.” | The limit is per operator/subscription; multiple instances multiply total load. |
| “`timeout` definitely aborts running JDBC queries.” | Publisher timeouts do not guarantee blocking drivers cancel I/O or roll back. |
| “`retry` never affects data integrity.” | Resubscription can re-run side effects; idempotency is required. |
| “Passing a transaction across multiple Schedulers keeps the same thread.” | Thread-bound transactions can break across thread boundaries. |
| “Using virtual threads eliminates the need for connection pools.” | Target resources, transactions, and rate limits still have bounds. |
| “A passing `StepVerifier` unit test proves broker acks work.” | Integration tests at the adapter/transport boundary are required. |

## 19. Self-Assessment Questions

1. Why can `map(order -> jdbcRepository.save(order))` stall an event loop?
2. What is the difference between `Mono.just(blockingClient.fetch())` and `Mono.fromCallable(blockingClient::fetch)`?
3. When is `Schedulers.parallel()` more suitable than `Schedulers.boundedElastic()`?
4. Why is `Schedulers.immediate()` not a solution for offloading a blocking API?
5. Which parts of a pipeline are affected by `subscribeOn` vs. `publishOn`?
6. Does placing `subscribeOn(boundedElastic)` at the end of a hot source guarantee every `map` callback runs on bounded elastic?
7. Given 100,000 events and a database handling at most 20 concurrent queries well, what limits beyond `boundedElastic` are required?
8. Why can `flatMap(..., 8)` still overload a shared API when running across multiple instances?
9. With `Mono.fromCallable(...)`, how can retries and resubscriptions cause side effects to run multiple times?
10. Why does a publisher timeout not guarantee a JDBC transaction rolled back?
11. When using thread-bound synchronous transactions, why should blocking operations be grouped into a single unit of work rather than separated by `publishOn`?
12. If a tracing ID is stored in `ThreadLocal`, what must be handled when switching Schedulers?
13. Why can a function that calls `subscribe()` itself and returns `Flux.empty()` cause the adapter to think processing finished prematurely?
14. How do you test that a blocking `Callable` has not executed prior to subscription?
15. What is the difference among a Scheduler's thread limit, `flatMap`'s concurrency limit, and a database connection pool limit?
16. For a continuous event stream and an SDK that can hang for a long time, at which layers would you place timeouts and recovery policies?

## 20. References

- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): the `Scheduler` model and using `subscribeOn`/`publishOn`.
- [Project Reactor — FAQ: Wrapping a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): the `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` pattern.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Reactor operators, subscriptions, backpressure, context, and errors.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier` and verifying signals.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, and reactive signatures.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): binder responsibilities, reactive functions, and limits at message boundaries.

Examples are written for Java 17+ and modern Project Reactor. Exact Scheduler settings, virtual threads, transaction managers, and binders depend on your deployed library versions; check dependencies/BOMs and run integration tests before production deployment.

**Key takeaway:** Avoid blocking by **preferring reactive clients**. When still dependent on synchronous JDBC, REST clients, or SDKs, wrap the operation in a lazy publisher such as `Mono.fromCallable(...)` or `Mono.fromRunnable(...)` and place `subscribeOn(Schedulers.boundedElastic())` **right at the blocking boundary**. `publishOn` only switches context for downstream signals and cannot fix an already-eager call. A Scheduler never replaces concurrency bounds, timeouts, connection pools, transactions, idempotency, or verifying actual behavior across Spring Cloud Function adapters.
