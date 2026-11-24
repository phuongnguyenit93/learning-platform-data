# Managing Schedulers, Subscriptions, and Custom Resources in Reactor / Spring WebFlux

## 1. Goal: Managing Ownership and Lifecycles Properly

In a reactive application, besides data there are **Scheduler threads/queues**, **active Subscriptions**, **connections**, **sessions**, **files**, **listener callbacks**, **buffers**, and resources allocated by the application or external libraries. A `Flux` or `Mono` can terminate along three paths:

- **onComplete:** normal completion.
- **onError:** encountered an error.
- **cancel:** the Subscriber stopped caring about results, for instance an HTTP client disconnected, `take(n)` got enough data, or a timeout cancelled upstream.

**Never release resources only on success.** If cleanup sits only inside `doOnComplete`, a failed or cancelled request can leak connections, threads, registrations, or memory resources.

Distinguish three ownership scopes:

| Type | Lifecycle owner | When to release |
| --- | --- | --- |
| **Dedicated Scheduler** created by a service/app | Component or Spring context owning the Scheduler | When the component/app stops and no tasks still need the Scheduler |
| **Subscription explicitly created via `subscribe()`** | The code that called `subscribe` or a container holding the handle | When the stream no longer needs to continue; on shutdown or business cancellation |
| **Resource opened for one subscription** | Pipeline managed via `using`/`usingWhen` or equivalent logic | After complete/error/cancel, following sync/async contracts |

If a Scheduler, client, or pool **is managed by the framework/shared runtime**, do not manually dispose it when one request ends. Conversely, if the application opens a resource itself, do not expect a Java variable going out of scope to automatically call `close` or `dispose`.

Central rule: **create at the right scope, assign clear ownership, guarantee cleanup on every termination path, and test all different termination paths**.

## 2. Core Concepts

**Scheduler** is Project Reactor's task-scheduling abstraction. A Scheduler may use dedicated threads, a pool, an event loop, or execute directly on the current thread. APIs like `publishOn` and `subscribeOn` work with it.

**Subscription** is the Reactive Streams contract between Publisher and Subscriber, allowing the Subscriber to call **request(n)** and **cancel()**. It is neither the same object as a Scheduler nor all external resources outside the pipeline.

**Disposable** is a handle on which **dispose()** can be called. Many **subscribe()** calls in Reactor return a `Disposable` for the application to cancel the subscription. A task scheduled via `Scheduler.schedule` returns its own `Disposable`. A Scheduler also has a dispose mechanism, yet **disposing a subscription does not mean disposing the whole Scheduler**.

**AutoCloseable/Closeable** is a Java resource type with a close operation. Other APIs may only support closing via a Publisher (for example `Mono<Void>` or `Publisher<Void>`).

**Resource ownership** answers three questions: who creates/allocates it, who may use it, and who has the right to close it. When ownership is unclear, common risks are **forgetting to close**, **closing twice**, or **closing too early while another party still uses it**.

### Lifecycle Diagram

~~~text
Application startup
   |
   +--> create shared Scheduler/connection pool (owner: app)
   |
   +--> HTTP request 1
   |       |
   |       +--> framework subscribes to response Publisher
   |       +--> open per-request resource (if needed)
   |       +--> complete/error/cancel -> close per-request resource
   |
   +--> independent background task
   |       |
   |       +--> app subscribes manually -> hold Disposable
   |       +--> shutdown -> dispose Subscription
   |
Application shutdown
   |
   +--> stop accepting new work
   +--> handle/cancel background subscriptions and await proper cleanup
   +--> dispose app-owned Scheduler/pool
~~~

This is a mental model, not a rigid sequence for every framework. If a cleanup Publisher still needs a Scheduler to run, **do not dispose the Scheduler before cleanup has been properly coordinated**.

## 3. Built-in Schedulers vs Custom Schedulers

### 3.1. Reactor-Managed Schedulers

~~~java
Schedulers.parallel();
Schedulers.boundedElastic();
Schedulers.single();
Schedulers.immediate();
~~~

These calls select an appropriate execution environment:

- **parallel():** for non-blocking CPU work; has a bounded number of workers. A single `publishOn(parallel())` does not automatically split every element onto a different thread.
- **boundedElastic():** useful for isolating unavoidable blocking work; has bounded thread/queue counts and does not make blocking APIs non-blocking.
- **single():** shared single-threaded Scheduler; heavy tasks can stall other work.
- **immediate():** does not switch to a dedicated pool.

Do not write code like this per request:

~~~java
return service.load()
        .publishOn(Schedulers.parallel())
        .doFinally(signal -> Schedulers.parallel().dispose());
~~~

This is a **wrong ownership example**: the Scheduler is shared at runtime level; one request has no right to shut it down on behalf of other requests.

### 3.2. Creating a Custom Scheduler

~~~java
Scheduler worker = Schedulers.newSingle("custom-stage");
try {
    String result = Mono.just("hello")
            .publishOn(worker)
            .map(String::toUpperCase)
            .block(); // Only in console programs.
    System.out.println(result);
} finally {
    worker.dispose();
}
~~~

This is an illustrative Java snippet with Reactor imports. A Scheduler created by **newSingle** is a custom resource and needs to be disposed. **try/finally** fits here because the console program uses `block()` to wait for the finished result.

However, **do not** apply that `finally` pattern to a method returning a lazy `Mono`:

~~~java
Mono<String> wrong() {
    Scheduler worker = Schedulers.newSingle("temporary");
    try {
        return Mono.just("hello")
                .publishOn(worker)
                .map(String::toUpperCase);
    } finally {
        worker.dispose(); // Closed before the caller subscribes.
    }
}
~~~

This is an **intentionally wrong example**. The `Mono` has not executed when the method returns; `finally` has already closed the Scheduler. When the framework subscribes later, scheduling work can be rejected.

Solution: keep the Scheduler at a **sufficiently long-lived** component/bean scope, or if a dedicated Scheduler per subscription is genuinely needed, open and close it with **using/usingWhen** bound to the subscription.

### 3.3. Spring-Managed Schedulers

In a Spring Boot application configured with Spring and Reactor dependencies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class SchedulerConfiguration {
    @Bean(destroyMethod = "dispose")
    Scheduler legacyScheduler() {
        return Schedulers.newBoundedElastic(
                8,       // max backing threads
                1000,    // max queued tasks per backing thread
                "legacy-io"
        );
    }
}
~~~

This is an **illustrative configuration**, not a standalone Spring Boot app. The Spring context owns the bean and invokes `dispose` when the bean is destroyed per lifecycle. Multiple services can inject the same Scheduler; **no service disposes the bean after each request**.

When forced to integrate a blocking library:

~~~java
Mono<Result> load(String id) {
    return Mono.fromCallable(() -> blockingClient.load(id))
            .subscribeOn(legacyScheduler);
}
~~~

This snippet assumes `Result`, `blockingClient`, and the Scheduler bean exist. The blocking source sits inside **fromCallable** and is scheduled onto the appropriate Scheduler via `subscribeOn`. Even so, the blocking function still occupies a thread while executing; concurrency, timeouts, CPU, and queues must be bounded.

**Warning:** Creating a separate **newBoundedElastic** on every service call can explode thread/queue counts; managing it as a bean or component resource is usually the better choice.

### 3.4. Scheduler.Worker and Individual Tasks

When the application uses low-level scheduling APIs:

~~~java
Scheduler own = Schedulers.newSingle("task-runner");
Scheduler.Worker worker = own.createWorker();
Disposable task = worker.schedule(() -> performTask());

task.dispose();   // Cancel task if still possible.
worker.dispose(); // No longer using Worker.
own.dispose();    // No longer using self-created Scheduler.
~~~

This is an illustrative snippet where `performTask` is application-defined. There can be three ownership levels: task, worker, and scheduler. Cancelling a task does not mean cancelling a shared Scheduler. **If the task is already running, `dispose` does not promise to halt an already-started operation immediately or roll back side effects**.

## 4. Who Owns a Subscription?

### 4.1. Manual subscribe() Must Retain the Disposable

~~~java
Disposable sub = Flux.interval(java.time.Duration.ofSeconds(1))
        .subscribe(
                tick -> log.info("tick={}", tick),
                error -> log.error("poll failed", error)
        );

// When the component no longer wants to receive events:
sub.dispose();
~~~

This is an illustrative service snippet assuming a logger. **Flux.interval** can emit infinitely; if you call `subscribe()` and discard the handle, the background stream can keep running and hold unwanted references.

Whoever subscribes manually must answer: who calls `dispose`? If an error terminates it, who records it? Does it need restarting? If the component shuts down while callbacks are running, some signals may still be in flight externally.

Some `Disposable` implementations have **isDisposed()**, yet `true`/`false` on any implementation must not be treated as proof that a network request or remote transaction stopped completely. Subscription cancellation state and external business state differ.

### 4.2. Spring WebFlux Controllers Normally Do Not Subscribe Manually

Right way:

~~~java
@GetMapping("/events")
public Flux<EventDto> events() {
    return eventService.stream().map(EventDto::from);
}
~~~

The controller **returns a Publisher**, and the framework subscribes and coordinates response/cancellation.

Wrong way:

~~~java
@GetMapping("/events")
public Flux<EventDto> events() {
    eventService.stream().subscribe(this::sendElsewhere);
    return Flux.empty();
}
~~~

The code above creates a task detached from the HTTP response lifecycle; the client cancelling the response does not necessarily cancel the controller's self-created subscription. Errors and resources are not managed through the same response path. If a background worker is required, use a service with its own **lifecycle, `Disposable`, and shutdown policy**.

### 4.3. A Subscription Can Terminate for Multiple Reasons

Example:

~~~java
Flux<Integer> source = Flux.range(1, 100)
        .doFinally(signal -> logger.info("source ended: {}", signal))
        .take(2);
~~~

This is an illustrative snippet. **take(2)** receives two values then cancels upstream; `doFinally` **before `take`** may observe **SignalType.CANCEL**. Meanwhile, the Subscriber after `take` receives a successful **onComplete** after two elements. Those are two different boundaries, not a contradiction.

## 5. doFinally, doOnCancel, and Lifecycle Callbacks

| Operator | Triggers when | Scope |
| --- | --- | --- |
| **doOnSubscribe** | A new subscription arrives | Start timers, tracing |
| **doOnNext** | An element passes | Observe data, not final cleanup |
| **doOnComplete** | Flux completes | Completion only, not error/cancel |
| **doOnError** | `onError` occurs | Error branch only |
| **doOnCancel** | Subscription is cancelled | Cancel branch only |
| **doOnTerminate** | `onComplete` or `onError` | Does not include cancel |
| **doFinally** | `onComplete`, `onError`, or `cancel` | Receives **SignalType.ON_COMPLETE/ON_ERROR/CANCEL** |

**doFinally** is useful for counting and classifying final outcomes:

~~~java
return client.fetch(id)
        .doFinally(signal -> {
            activeRequests.decrementAndGet();
            metrics.record(signal);
        });
~~~

However, distinguish **observation** from **mandatory cleanup**:

- `doFinally` is invoked per Reactor's position/signal rules; on complete/error, the callback may run **after downstream has already seen the terminal**. Checking a variable right after `block()` may not always see the callback's side effect under different execution schedules.
- `doFinally` **does not automatically subscribe to and await a cleanup Publisher**. Do not write `doFinally(signal -> closeAsync().subscribe())` and assume cleanup will finish before the response.
- Errors from cleanup actions inside callbacks can be awkward to coordinate with the original error. Use **using/usingWhen** if the resource must be managed as part of the Publisher's contract.
- Placing callbacks before/after `take`, `timeout`, or `retry` can change the observed signal type.

If you need synchronous per-subscription cleanup, use **using**. If close/commit/rollback returns a Publisher, use **usingWhen**.

## 6. Flux.using and Mono.using: Synchronous Per-Subscription Resources

A resource is created specifically upon subscribe, used in the pipeline, and released on complete/error/cancel:

~~~text
Subscription
   |
   +--> resourceSupplier() creates resource
   +--> resourceClosure(resource) creates Publisher using resource
   |
   +--> complete -----+
   +--> error --------+--> resourceCleanup(resource)
   +--> cancel -------+
~~~

Syntax:

~~~java
Flux<String> lines = Flux.using(
        () -> openResource(),
        resource -> readResource(resource),
        resource -> closeResource(resource)
);
~~~

This is an illustrative snippet with learner-defined application APIs. **Flux.using** is for resources with synchronous cleanup; the overload with an **eager** parameter lets you tune disposer timing relative to the terminal signal. If the disposer throws an error, understand the impact of `eager` and handle exceptions per contract.

**Do not open a resource eagerly and return it across every subscribe**:

~~~java
Connection shared = openConnection();
Flux<Row> bad = Flux.using(
        () -> shared,
        conn -> query(conn),
        conn -> close(conn)
);
~~~

This is a wrong example if multiple subscriptions can arrive or if the publisher is declared and never subscribed to. The resource opens immediately, may never be used/closed, and gets shared across multiple Subscribers.

If the resource opens synchronously, put the open call inside the Supplier:

~~~java
Flux<Row> good = Flux.using(
        () -> openConnection(),
        conn -> query(conn),
        conn -> close(conn)
);
~~~

These two snippets illustrate synchronous APIs with `Row`, `Connection`, and application methods. For reactive DBs where open/close return Publishers, use **usingWhen**, or Spring's corresponding transaction/resource management mechanisms.

## 7. Mono.usingWhen and Flux.usingWhen: Asynchronous Resources

Many resources expose async APIs like **openSession(): Mono<Session>** and **closeSession(Session): Mono<Void>**. Use **usingWhen** so Reactor manages the cleanup Publisher:

~~~java
Mono<Result> result = Mono.usingWhen(
        client.openSession(),               // Publisher<Session>
        session -> client.execute(session), // Mono<Result>
        session -> client.close(session)    // Publisher<?> cleanup
);
~~~

This is an illustrative snippet with application-defined `client`, `Session`, and `Result`. Operations needing an active resource must reside inside **resourceClosure**. If the resource is used downstream **after `usingWhen`**, it may already be closed by then.

### Three Separate Cleanup Branches

~~~java
Mono<Result> operation = Mono.usingWhen(
        client.openSession(),
        session -> client.execute(session),
        session -> client.commitAndClose(session),
        (session, error) -> client.rollbackAndClose(session),
        session -> client.cancelAndClose(session)
);
~~~

This is illustrative architectural code with hypothetical client methods returning Publishers:

- **asyncComplete** runs when `resourceClosure` completes successfully.
- **asyncError** receives the resource and `resourceClosure` error to roll back/close per contract.
- **asyncCancel** is invoked when the subscription is cancelled.

Do not manually commit/roll back a connection already managed by **Spring `TransactionalOperator` or a transaction manager**; pick one owner for the transaction.

### Mono.usingWhen Waits for Cleanup Before Emitting Final Result

With `Mono.usingWhen`, **the success result is coordinated with the cleanup Publisher**. When cleanup errors, the `Mono` may emit **onError** instead of an expected value, and that result can be discarded. This matters for operations that should only be declared successful after commit/close.

With `Flux.usingWhen`, multiple **onNext** values may already have been delivered while the resource was open; a cleanup error cannot retract `onNext` items the Subscriber already saw. **usingWhen is not automatically exactly-once or a distributed transaction.**

Cases to account for:

- Resource Supplier completes empty or errors before supplying a resource: no resource was supplied to clean up via that mechanism.
- Operation errors: error-branch cleanup must run without hiding the original error.
- Subscriber cancels: cancel-branch cleanup must be initiated, though it may still execute **after the `dispose()` call returns** if asynchronous.
- Cleanup Publisher errors: record cleanup failures rather than assuming a successful outcome.
- Resource shared outside `usingWhen`: may get closed while another consumer still needs it.

## 8. Runnable Java 17+ Example: Managing All Three Resource Kinds

This program uses Reactor Core to demonstrate:

1. A dedicated Scheduler handling `map` after `publishOn` and disposed at the end.
2. A `Flux.never` subscription being disposed, with `doFinally` receiving `CANCEL`.
3. `Flux.using` automatically closing a resource when `take(2)` cancels upstream.
4. `Mono.usingWhen` coordinating a cleanup Publisher before returning the result.

Structure:

~~~text
reactor-resource-lifecycle/
├── pom.xml
└── src/main/java/ResourceLifecycleDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-resource-lifecycle</artifactId>
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
                    <mainClass>ResourceLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/ResourceLifecycleDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ResourceLifecycleDemo {
    static final class CounterResource implements AutoCloseable {
        private final AtomicInteger closed;

        CounterResource(AtomicInteger closed) {
            this.closed = closed;
        }

        int twice(int number) {
            return number * 2;
        }

        @Override
        public void close() {
            closed.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        Scheduler worker = Schedulers.newSingle("lesson-worker");
        try {
            String stage = Mono.just("A")
                    .publishOn(worker)
                    .map(value -> Thread.currentThread()
                            .getName()
                            .startsWith("lesson-worker-")
                            ? "on-worker" : "unexpected-thread")
                    .block();
            System.out.println("scheduler stage = " + stage);

            List<String> cancellation = new CopyOnWriteArrayList<>();
            Disposable subscription = Flux.<Integer>never()
                    .doFinally(signal -> cancellation.add(signal.name()))
                    .subscribe();
            subscription.dispose();
            System.out.println("cancel signal = " + cancellation);

            AtomicInteger closeCount = new AtomicInteger();
            List<Integer> values = Flux.using(
                    () -> new CounterResource(closeCount),
                    resource -> Flux.range(1, 3)
                            .map(resource::twice),
                    CounterResource::close
            )
            .take(2)
            .collectList()
            .block();

            System.out.println("using values = " + values
                    + ", closed = " + closeCount.get());

            AtomicInteger asyncCloseCount = new AtomicInteger();
            String outcome = Mono.usingWhen(
                    Mono.fromSupplier(
                            () -> new CounterResource(asyncCloseCount)),
                    resource -> Mono.just("DONE"),
                    resource -> Mono.fromRunnable(resource::close)
            ).block();

            System.out.println("usingWhen = " + outcome
                    + ", closed = " + asyncCloseCount.get());
        } finally {
            worker.dispose();
        }

        System.out.println("scheduler disposed = " + worker.isDisposed());
    }
}
~~~

Requires **JDK 17+** and Maven. Run from the project directory:

~~~bash
mvn -q compile exec:java
~~~

**Stdout printed by the program:**

~~~text
scheduler stage = on-worker
cancel signal = [CANCEL]
using values = [2, 4], closed = 1
usingWhen = DONE, closed = 1
scheduler disposed = true
~~~

Explanation:

- **publishOn(worker)** runs `map` on a worker of the custom-named Scheduler; prefix checking produces `on-worker`.
- **Flux.never()** has no natural terminal. Calling **dispose()** on the subscription makes `doFinally` receive **CANCEL**; the demo's synchronization is simple because `Flux.never` does not schedule emissions on another thread.
- **take(2)** receives numbers 1, 2 (doubled to 2, 4) and cancels upstream. **Flux.using** closes `CounterResource` **once**.
- **Mono.usingWhen** executes **Mono.fromRunnable(resource::close)** as the cleanup Publisher. With `Mono.usingWhen`, `DONE` is delivered after cleanup; by the time `block()` returns, the counter has already incremented.
- **finally** disposes the custom Scheduler. Calling `isDisposed()` on this scheduler returns `true`.

**Why does the example use `block()`?** It is used only at the console application boundary to print results of finite sources. **Never use `block()` on the event loop in a WebFlux controller**. Do not rely on `Thread.sleep` or interleaved print ordering across threads to test resources.

## 9. Grouping Background Subscriptions with Disposables.composite()

If a component proactively subscribes to multiple sources **not tied to an HTTP response**, it can hold a **Disposable.Composite**:

~~~java
import reactor.core.Disposable;
import reactor.core.Disposables;

Disposable.Composite active = Disposables.composite();

active.add(sensorFlux.subscribe(
        event -> process(event),
        error -> log.error("sensor failed", error)
));

active.add(refreshFlux.subscribe(
        event -> refresh(event),
        error -> log.error("refresh failed", error)
));

// When the component stops:
active.dispose();
~~~

This is an illustrative snippet with application-provided `sensorFlux`, `refreshFlux`, `process`, `refresh`, and `log`. The composite owns the added `Disposable` handles; disposing the container cancels them. If you **add** after the container is already disposed, the new handle is disposed instead of “reviving” the container. To start a fresh run after restart, create a new composite.

**remove(d)** takes the handle out of the composite without cancelling it; the caller then assumes ownership and must dispose it at the right time. Do not remove from the composite and drop the reference.

You do not need `Disposables.composite()` for Publishers subscribed to by the Spring WebFlux framework when handling responses. This tool is for streams **the application proactively launches**.

## 10. Unregistering External Callbacks

A system outside Reactor may return a handle after registering a listener. When bridging callbacks to a `Flux`:

~~~java
Flux<Event> events = Flux.create(sink -> {
    ListenerRegistration registration =
            externalSource.registerListener(
                    value -> sink.next(value),
                    error -> sink.error(error)
            );

    sink.onDispose(() -> registration.unregister());
});
~~~

This is an illustrative architectural snippet: `Event`, `ListenerRegistration`, and `externalSource` are hypothetical APIs. **FluxSink.onDispose** registers cleanup for the sink lifecycle, including termination and cancellation; **onCancel** targets only the cancel branch.

Points to watch:

- Each subscription usually needs its own listener/registration, unless you intentionally design a hot/shared source.
- An `unregister` API might not block an already in-flight callback, so verify thread safety.
- If unregistration is **async**, an `onDispose` `Runnable` will not automatically await its completion; coordinate cleanup per the proper contract.
- If the push source does not support `request(n)`, define a dedicated buffer/drop/error/backpressure policy at the adapter boundary.
- Avoid holding references to destroyed controllers/services inside unregistered listeners.

## 11. Cancellation Does Not Mean Stopping Remote Operations

~~~text
Client cancels Subscription
    |
    +--> Reactor tells downstream/upstream to stop signals
    |
    +--> Client adapter may cancel future or HTTP request
    |
    +--> Server/SDK work may still be running
    |
    +--> Committed side effects do not auto-rollback
~~~

**Cancellation is part of the reactive protocol**, yet its effect on connections, RPCs, database transactions, or SDKs depends on the real integration.

- **CompletableFuture.cancel()** may mark the Future cancelled without guaranteeing a task already started on an Executor stops.
- **WebClient/Netty** may stop receiving/close the request when the subscription is cancelled, yet cannot prove the server has not executed the operation.
- **Timeout** usually cancels upstream without guaranteeing rollback.
- **Idempotency keys**, status-check APIs, and transaction managers solve delivery/recovery needs that Reactor cancellation does not.

For resources shared across multiple subscriptions, one subscriber cancelling must not automatically close the shared source. Use `refCount`/sharing, clear ownership, and explicit close contracts.

## 12. Buffers, Discard, and Releasable Resources

If a `Flux` contains objects like **DataBuffer/ByteBuf** genuinely owned by the application, filtering, taking, cancelling, or queue overflow can cause some elements to be dropped before reaching the Subscriber. **GC does not necessarily replace explicit release for pooled/reference-counted resources**.

Reactor provides **doOnDiscard** for discard-supporting operators:

~~~java
Flux<MyBuffer> result = source
        .filter(MyBuffer::shouldKeep)
        .doOnDiscard(MyBuffer.class, MyBuffer::release);
~~~

This is an illustrative snippet with application-defined `MyBuffer`/`source`. Not every operator supports discard. Read the operator's **Discard Support** note and verify who owns the buffer:

- Release only objects that **the application is responsible for releasing**.
- Do not **double-release** objects already managed by the framework/codec.
- If Spring WebFlux handles `DataBuffer` manually, consult the **DataBufferUtils.release(...)** API and data-buffer implementation rules.
- When prefetching occurs in `publishOn` or async operators, cancellation can leave items in queues; identify the corresponding discard path.
- Do not misuse `doOnDiscard` as a cleanup tool for Schedulers or primary connections: those are two different concerns.

## 13. Resources and Transactions in Spring WebFlux

### Request/Subscription-Owned Resources

~~~java
@GetMapping("/reports/{id}")
public Mono<Report> report(@PathVariable String id) {
    return Mono.usingWhen(
            sessionClient.openSession(),
            session -> sessionClient.readReport(session, id),
            session -> sessionClient.closeSession(session)
    );
}
~~~

This is an example controller in a project with `Report`/`sessionClient`. The resource opens for the subscription serving the request and closes per the `usingWhen` contract. Note that **client disconnect** can cancel the HTTP subscription; provide a cleanup branch on cancel.

When using Spring's **R2DBC transaction manager**, normally let **TransactionalOperator** or the corresponding reactive transaction mechanism own commit/rollback; do not add a parallel `usingWhen` with commit when the framework already manages the same transaction.

### Application-Owned Resources

Connection pools, WebClients with custom resources, dedicated Schedulers, and background subscriptions can outlive a single request. Manage them via Spring beans/lifecycles:

- **@Bean(destroyMethod = "dispose")** if the resource has an appropriate `dispose()`.
- **@PreDestroy**, **DisposableBean**, or **SmartLifecycle** when multi-step shutdown is needed.
- Stop accepting new work, stop background subscriptions, coordinate cleanup, and then close Schedulers/connection pools in dependency order.
- For cleanup Publishers, **merely instantiating a `Mono` and ignoring it does not mean cleanup ran**: it must be subscribed/coordinated in a designed shutdown mechanism, with deadlines and error recording.
- Do not dispose shared Reactor Netty components simply because one HTTP request ended.

### Resource Cleanup Errors

A cleanup operation can throw an exception or emit `onError`. Handling policy depends on resource type and business rules:

- With **Mono.usingWhen**, a cleanup failure can turn the main result into `onError` instead of emitting success.
- With **Flux.usingWhen**, previous `onNext` items cannot be retracted.
- If both the operation and cleanup error, preserve root-cause/cleanup-cause details for diagnostics.
- Do not silently swallow all critical cleanup failures with **onErrorResume(Mono.empty())**; that can hide commit/close failures.

## 14. Testing Complete, Error, and Cancel

Testing only the happy path is insufficient to prove resource lifecycles. With **reactor-test / StepVerifier** and a fake resource holding an **AtomicInteger closeCount**, check:

1. **onComplete:** resource opens once per subscription and closes once.
2. **onError:** cleanup still runs; downstream sees the error per contract.
3. **cancel:** `take(1)`, `thenCancel()`, or `dispose()` causes cleanup to run.
4. **No subscribe:** `resourceSupplier` has not been invoked on deferred sources.
5. **Subscribe twice:** each subscription receives its own resource, without reusing a closed object.
6. **Acquire errors/empty:** do not clean up a resource that was never created.
7. **Slow/failing async cleanup:** response waits or receives error per `usingWhen` semantics.
8. **Early shutdown:** do not dispose a Scheduler before a cleanup Publisher needing that worker runs.
9. **Callback resources:** listeners are unregistered and retain no references after cancel.
10. **Threads/pools:** no accumulation of Schedulers or tasks across repeated component start/stop cycles.

Illustrative test snippet (requires `reactor-test` and `CounterResource` defined in the program):

~~~java
AtomicInteger closeCount = new AtomicInteger();

Flux<Integer> values = Flux.using(
        () -> new CounterResource(closeCount),
        r -> Flux.just(1, 2, 3),
        CounterResource::close
);

StepVerifier.create(values)
        .expectNext(1, 2, 3)
        .verifyComplete();

if (closeCount.get() != 1) {
    throw new AssertionError("Resource must close once");
}
~~~

For cancellation, you can use **StepVerifier.thenCancel()**, though with asynchronous cleanup you must observe an additional completion signal rather than reading a counter immediately. Avoid tests relying on arbitrary `Thread.sleep` and interleaved logs across threads.

### Production Monitoring

Monitor **active background subscription counts**, open/unclosed resource counts, terminations by `ON_COMPLETE`/`ON_ERROR`/`CANCEL`, **Scheduler queued/rejected tasks**, connection/session counts, cleanup duration, cleanup errors, and lingering resources after shutdown. For metrics, avoid unbounded labels like resource IDs or request IDs, which cause high cardinality.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `newSingle`/`newBoundedElastic` on every request | Thread/queue waste, easy leaks | Reuse Scheduler per component/app, dispose on shutdown |
| Disposing a shared Scheduler in `doFinally` | Breaks other subscriptions | Only the Scheduler's owner may dispose it |
| Closing Scheduler in `finally` before a lazy `Mono` is subscribed | Rejected scheduling, pipeline failure | Bean lifecycle or subscription-bound `using` |
| Calling `subscribe()` in a controller and discarding `Disposable` | Work detached from HTTP, not cancelled on time | Return `Mono`/`Flux` to the framework |
| Cleaning up only in `doOnComplete` | Leaks on error/cancel | `using`/`usingWhen` or callbacks covering all paths |
| `doFinally(signal -> closeAsync().subscribe())` | Fire-and-forget cleanup, errors uncoordinated | `usingWhen` with a cleanup Publisher |
| Sharing a mutable resource across multiple subscriptions | Using a closed resource, races | Create a fresh resource per subscription |
| Assuming `dispose()` rolls back remote tasks | Retries can duplicate side effects | Idempotency, transactions, and status checks |
| Dropping handles to background listeners/Subscriptions | Callbacks or intervals run forever | `onDispose`, `Composite`, and lifecycle management |
| Forgetting to release buffers on discard | Pooled memory leaks | Clear ownership, `DataBufferUtils`/`doOnDiscard` per contract |
| Closing Scheduler before async cleanup during shutdown | Cleanup scheduling may be rejected | Coordinate cleanup before shutting down related Schedulers |
| Checking only `isDisposed()` to confirm a remote task finished | Wrong conclusions about execution state | Use metrics, remote outcomes, and business contracts |

## 16. Choosing Tools by Need

| Need | Tool |
| --- | --- |
| Shared Scheduler for CPU/legacy blocking | Reactor-managed Scheduler or Spring bean |
| Application-created custom Scheduler | `dispose()` in lifecycle owner, not per request |
| Manually scheduled task | Retain `Disposable` from `schedule()` |
| Background subscription manually subscribed by app | Retain `Disposable`; use `Disposables.composite()` if needed |
| HTTP controller returning Publisher | **Do not subscribe manually**; framework manages it |
| Metrics for every termination type | **doFinally(SignalType)** |
| Callback only on cancel | **doOnCancel** |
| Synchronous resource, one instance per subscription | **Flux.using / Mono.using** |
| Resource needing async close/commit/rollback | **Flux.usingWhen / Mono.usingWhen** |
| Different cleanup on complete/error/cancel | 3-branch `usingWhen` overload |
| Listener needing unregister when stream stops | `Flux.create` + `sink.onDispose` or `using` |
| Pooled buffer needing release on discard | `doOnDiscard` + type-appropriate ownership/release API |
| Shutting down multiple interdependent resources | Spring lifecycle with ordered stop/await/dispose |

## 17. Conclusion

Resource management in Reactor requires clearly separating **Schedulers**, **Subscriptions**, and **per-subscription resources**. Custom Schedulers are component/application-scoped resources; never shut down a shared Scheduler after each request. A `Disposable` returned from `subscribe()` needs an owner and a cancellation point if the application subscribes proactively, while in Spring WebFlux you should let the framework manage response subscriptions.

**doFinally** observes complete/error/cancel, yet does not await asynchronous cleanup automatically. **using** manages synchronously closed resources and **usingWhen** coordinates resources with cleanup Publishers; both prevent missed cleanup on error/cancel. **Cancellation does not mean all remote tasks stopped or rolled back**: consult SDK, connection, and business contracts.

A sound design answers: **Who opens the resource? Who has the right to close it? How does it close on complete, error, and cancel? Must a cleanup Publisher be awaited? On shutdown, are there still tasks needing the Scheduler?** Then verify reality using `StepVerifier`/fake resources and metrics.

**Official Documentation:**
- [Reactor Reference — doFinally and using](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Mono API — usingWhen, cancellation and cleanup](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Flux API — using, usingWhen, doOnDiscard](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Scheduler API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html)
- [Disposable.Composite API](https://projectreactor.io/docs/core/release/api/reactor/core/Disposable.Composite.html)
