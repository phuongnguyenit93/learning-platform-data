# Cleanup on Completion, Error, or Cancellation in Spring Reactive

## 1. Why Is Resource Management Part of Reactive Programming?

In **Project Reactor** and **Spring WebFlux**, a `Mono<T>` or `Flux<T>` typically represents work that only executes when someone **subscribes**. That work may hold a connection, transaction session, file stream, listener, timer, HTTP request, or an external SDK handle. When downstream no longer needs data, or when the source has terminated, these must be released.

Reactive programming has **three critical termination paths**:

1. **Successful completion — `onComplete`**: the source has finished emitting data, including the case where zero elements were emitted.
2. **Failure — `onError`**: the source encountered an error; `onError` ends the subscription, with no further `onNext` or `onComplete` afterward.
3. **Cancellation — `cancel`**: the subscriber or a downstream operator requests upstream to stop before it finishes naturally; cancel is a command on the `Subscription`, **not** an `onComplete` or `onError` signal sent to the subscriber.

**Proper cleanup means resources must be reclaimed on all three paths**, not only on the “finished successfully” branch. If you close resources only in the success callback, a disconnected SSE stream or a failed database query can leave listeners and sockets behind. Conversely, if you use only `doOnCancel`, natural completion and failure paths may go uncleaned.

Distinguish three terms:

| Concept | Role | What must not be confused |
| --- | --- | --- |
| **Termination** (`onComplete` or `onError`) | Source sends a terminal signal | Not every stopped operation is an error |
| **Cancellation** (`cancel`) | Downstream asks upstream to stop sending/processing further | Does not guarantee the subscriber receives a new terminal signal |
| **Resource cleanup** (cleanup/dispose/close) | Unregister listeners, close streams, release handles, finalize sessions | Does not happen automatically for external APIs unless logic is attached |

A `Flux.never()` publisher may emit neither values nor terminal signals; it still needs **cleanup when the subscriber cancels** if it holds resources. Hence, lifecycle management cannot rely solely on `onComplete` and `onError`.

## 2. Lifecycle of a Subscription

Simple model:

~~~text
Subscriber.subscribe()
       |
       v
onSubscribe(subscription)
       |
       +-- onNext(value) ... onNext(value)
       |
       +-- onComplete() ---> COMPLETE ---> cleanup
       |
       +-- onError(error) -> ERROR ------> cleanup
       |
       +-- subscription.cancel() -------> CANCEL ---> cleanup
~~~

`onComplete` and `onError` are **mutually exclusive** terminal signals for the same subscription. Cancel can race in timing with completion or error: for instance, a client closes the connection right as the source finishes. Adapters and external resources must tolerate **races**, never assuming only one thread exists or only one callback can arrive.

Real-world scenarios:

- An HTTP client receives the full response successfully → completion.
- An R2DBC driver returns a query error → error.
- A user closes a browser tab listening to SSE → the server may detect the disconnect and cancel upstream.
- `take(3)` receives three values → the operator may **cancel upstream** and send completion **downstream**.
- `timeout(...)` may cancel an upstream that exceeded the deadline, then report a timeout error downstream or switch to a fallback.

**Observation position affects the observed signal.** If `doFinally` sits before `take(3)`, it may see `CANCEL` from `take`; a hook after `take(3)` typically sees `ON_COMPLETE`. There is no contradiction: those are two segments of the same pipeline—one cancels upstream, the other completes downstream.

## 3. `doFinally`: The Conceptual Equivalent of `finally`

`doFinally(Consumer<SignalType>)` lets you run side effects when the sequence ends via **complete, error, or cancel**. It receives the termination type through `reactor.core.publisher.SignalType`:

- `SignalType.ON_COMPLETE`: the observed source/sequence completed successfully.
- `SignalType.ON_ERROR`: the observed source/sequence ended with an error.
- `SignalType.CANCEL`: upstream of the hook position was cancelled.

Example:

~~~java
// Illustrative snippet; requestCounter and timer are application objects.
Flux<Event> events = eventSource()
    .doOnSubscribe(subscription -> timer.start())
    .doFinally(signal -> {
        timer.stopAndRecord();
        if (signal == SignalType.CANCEL) {
            requestCounter.incrementCancelled();
        }
    });
~~~

This is an **in-project illustrative snippet**, not a standalone runnable class because `Event`, `eventSource`, `timer`, and `requestCounter` are application-defined. The timing logic will run on complete, error, or cancel.

Two easily missed details:

1. **`doFinally` is invoked after the terminal/cancel signal is propagated to the corresponding side.** Thus, the subscriber may have already received `onComplete` before the `doFinally` callback executes. If a pipeline chains multiple `doFinally` operators, callbacks may run in **reverse** declaration order due to how terminal signals propagate.
2. **`doFinally` is only a side effect, not a mechanism that automatically opens/closes scoped resources.** It works well for recording metrics or cleaning up an already properly managed handle, but when a dedicated resource must be allocated per subscriber, using `using` or `usingWhen` usually expresses the lifecycle more tightly.

For testing, do not rely on every `doFinally` side effect already being visible immediately after `block()`/completion signal in an asynchronous source. Use a synchronization condition or an appropriate `StepVerifier`/test hook when cleanup must be verified.

## 4. Hooks That Look Similar but Differ in Scope

| Operator/hook | When it runs | When it does **not** run | Used for |
| --- | --- | --- | --- |
| `doOnComplete` on `Flux` | Right before the complete signal flows downstream | Error or cancel | Observing successful completion |
| `doOnError` | When an error passes the pipeline at the hook's position | Complete or cancel | Error logging, metrics |
| `doOnTerminate` | Before `onComplete` or `onError` | **Pure cancel** | Tracking the two terminal signals |
| `doAfterTerminate` | After `onComplete` or `onError` has been passed downstream | **Pure cancel** | Post-terminal side effects |
| `doOnCancel` | When downstream cancels; before cancel propagates upstream past that point | Natural complete or error | Reacting specifically to cancel |
| `doFinally` | After complete, error, **or cancel** | Does not run if the sequence stays active forever and is never cancelled | Cleanup/metrics for all three branches |
| `FluxSink.onCancel` | When the subscription of a callback bridge is cancelled | Natural complete or error | Commanding an SDK to stop work |
| `FluxSink.onDispose` | When the sink is disposed due to complete, error, or cancel | Not a per-`onNext` hook | Detaching listeners/handles shared across all termination paths |

`doOnError` and `doFinally` do not turn an error into success; `onErrorResume` is the operator that creates a fallback. And `doOnTerminate` is **not** a “finally” for all three paths.

Error-prone example:

~~~java
// Wrong if you want to release the resource even when the client leaves:
source.doOnTerminate(resource::close);

// Better if the resource is already managed per single subscription:
source.doFinally(signal -> resource.close());
~~~

This example is **only about the difference between hooks**, not yet a safe resource-creation pattern. If `resource` is created once outside and `source` is shared by multiple subscribers, multiple callbacks might try to close the same object; instead, create and manage resources **within a subscription scope** using `using`/`usingWhen`.

## 5. `Flux.using` and `Mono.using`: Synchronous Resource Allocation and Closing

`using(resourceSupplier, sourceSupplier, resourceCleanup)` is the reactive equivalent of `try-with-resources`: **create the resource when a subscriber arrives**, use it to build a publisher, and invoke cleanup when the publisher completes, errors, or is cancelled.

Pattern:

~~~java
// Illustrative structural code; openReader and readAsFlux are provided by the application.
Flux<String> lines = Flux.using(
    () -> openReader(),
    reader -> readAsFlux(reader),
    reader -> reader.close(),
    true // eager cleanup
);
~~~

Here `openReader()` must supply a reader **dedicated to this subscription**, avoiding improper resource sharing between clients. `readAsFlux(reader)` must emit data **while the reader is still open**. Upon termination/cancellation, cleanup closes the reader.

The `eager` parameter in the 4-argument overload means:

- `eager = true`: cleanup is executed **before the terminal signal is sent downstream**. If cleanup throws an exception, it can **replace** the original terminal signal. This is useful when success should only be acknowledged after the resource closes cleanly.
- `eager = false`: cleanup runs **after the terminal has been passed down**; an exception in cleanup generally cannot alter the already-sent result and may be reported as dropped via application hooks. You should not silently ignore resource-cleanup errors by default.
- For **cancel**, there is no downstream terminal left to send, yet the resource still needs to be closed.

In real applications, some resources are owned by a database connection pool, HTTP client, or framework. **Close only resources you own**, not the application-wide pool when one request ends. Know whether a resource is per-subscription, per-request, or a shared singleton.

`using` is suitable when cleanup is **synchronous** (for example `AutoCloseable.close()`). If cleanup is an asynchronous publisher, such as `session.rollback()` returning `Mono<Void>`, do not call `block()` inside the hook to wait. Use `usingWhen`.

## 6. Runnable Java 17+ Example: Demonstrating Cleanup Across All Three Branches

This example uses **Reactor Core** (no Spring Boot startup required) and simulates a resource with a `close()` method. Three independent flows respectively: complete naturally, error after one element, and wait indefinitely until the subscriber cancels. The program collects milestones into a list and prints **after the operation finishes/cancels**, avoiding dependence on thread names.

Structure:

~~~text
reactor-resource-lifecycle/
├── pom.xml
└── src/main/java/ResourceLifecycleDemo.java
~~~

File `pom.xml`:

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

File `src/main/java/ResourceLifecycleDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public class ResourceLifecycleDemo {
    private static final class Resource implements AutoCloseable {
        private final List<String> events;
        private final AtomicBoolean closed = new AtomicBoolean();

        Resource(List<String> events) {
            this.events = events;
            events.add("open");
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                events.add("close");
            }
        }
    }

    private static void run(String name, Flux<Integer> body, boolean cancel) {
        List<String> events = new ArrayList<>();

        Flux<Integer> stream = Flux.using(
            () -> new Resource(events),
            resource -> body,
            Resource::close,
            true // Invoke cleanup before downstream terminal.
        ).doFinally(signal -> events.add("finally:" + signal.name()));

        Disposable subscription = stream.subscribe(
            value -> events.add("next:" + value),
            error -> events.add("error:" + error.getMessage()),
            () -> events.add("complete")
        );

        if (cancel) {
            subscription.dispose();
        }

        System.out.println(name + " => " + String.join(" | ", events));
    }

    public static void main(String[] args) {
        run("success", Flux.just(1, 2), false);

        run("error",
            Flux.concat(
                Flux.just(7),
                Flux.<Integer>error(
                    new IllegalArgumentException("bad"))),
            false);

        run("cancel", Flux.<Integer>never(), true);
    }
}
~~~

In the `reactor-resource-lifecycle` directory, with **JDK 17+** and **Maven**, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ResourceLifecycleDemo
~~~

**Stdout printed by the program** (excluding Maven messages):

~~~text
success => open | next:1 | next:2 | close | complete | finally:ON_COMPLETE
error => open | next:7 | close | error:bad | finally:ON_ERROR
cancel => open | close | finally:CANCEL
~~~

Explanation:

1. **Success:** `Flux.just(1, 2)` emits two values then completes. Because `using(..., true)` configures eager cleanup, `close` is recorded **before** the `complete` callback. `doFinally` runs after the terminal with type `ON_COMPLETE`.
2. **Error:** the `Flux.concat` source emits 7 and then emits an error. The resource is still closed, the subscriber receives `error:bad`, and `doFinally` observes `ON_ERROR`. There is no `complete` after an error.
3. **Cancel:** `Flux.never()` emits neither elements nor a terminal. `subscribe()` returns a `Disposable`; calling `dispose()` cancels the subscription, closes the resource, and `doFinally` observes `CANCEL`. There is no `complete` or `error` entry in this branch.
4. `AtomicBoolean` guards `close()` against repeated invocations. With async SDKs, cleanup additionally needs thread-safety, registration/cancellation synchronization, and bounding late callbacks.

This example has no scheduler or async I/O, so the synchronous sources and `dispose` all execute on the calling thread; the output lines have deterministic order. In real networked applications, do not assume cleanup callbacks run on a single thread or appear the instant an HTTP client closes a tab.

## 7. `usingWhen`: Asynchronous Cleanup per Termination Path

With reactive drivers, “closing” or “rolling back” can be **an asynchronous publisher**, such as a `Mono<Void>` from a database operation. If you call a method returning `Mono<Void>` **without subscribing or composing it into the pipeline**, cleanup may never execute; conversely, calling `block()` on the WebFlux event loop causes blocking.

`Mono.usingWhen` / `Flux.usingWhen` are designed for this case. The full signature has separate branches:

~~~java
// Conceptual sample code: resourcePublisher, work, and cleanup functions
// must be implemented using publishers from reactive libraries.
Mono<Result> result = Mono.usingWhen(
    resourcePublisher,         // Publisher<Session>: supplies resource
    session -> work(session),  // Mono<Result>: uses resource
    session -> close(session), // On successful completion
    (session, error) -> rollbackAndClose(session, error), // On error
    session -> cancelAndClose(session)   // On cancellation
);
~~~

This is an **API skeleton example**, not a standalone Java file; `Session`, `Result`, and the corresponding methods are application-defined. Each cleanup function must return a `Publisher<?>` that actually performs the cleanup work when subscribed to.

Key characteristics:

- **Complete** branch: the resource closure completes successfully → Reactor subscribes to the `asyncComplete` cleanup publisher.
- **Error** branch: the resource closure errors → Reactor invokes `asyncError` with both the resource and the exception, to roll back/release per error semantics.
- **Cancel** branch: downstream cancels → Reactor runs the `asyncCancel` cleanup publisher if the resource has already been acquired. If cancelled before the resource is acquired, the resource-acquisition subscription must also be cancelled properly.
- **`Mono.usingWhen` defers emitting the `Mono` result signal until the appropriate cleanup finishes.** If cleanup fails, the final result can become `onError` instead of the initial value.
- **`Flux.usingWhen` can forward multiple `onNext` values before cleanup finishes, yet defers the terminal signal** until cleanup completes. If cleanup fails, it can change the terminal outcome, though it cannot “retract” elements already sent to the client.
- When acquiring the resource fails or completes empty **before a resource exists**, there is no resource to clean up; the main publisher is handled according to the corresponding signal.

**Business note on transactions:** for a transaction, “complete” may mean **commit** rather than just close; “error/cancel” may require rollback. Rely on the real driver and transaction manager contracts. Do not call close and rollback multiple times across overlapping hooks without knowing idempotency. Spring reactive transactions have their own mechanisms; do not manually open transactions when the framework already manages them.

## 8. `Flux.create`, Callback SDKs, and Handling Cancellation

External listener/callback APIs typically hold a registration or handle until `unregister` is called. When bridging callbacks to `Flux` with `Flux.create`, manage **both directions**: the SDK pushes data into `sink.next`, and downstream cancellation sends a stop command back to the SDK.

~~~java
// Illustrative example; does not compile standalone because SensorSdk
// and Registration depend on an external SDK.
Flux<String> updates = Flux.<String>create(sink -> {
    Registration registration = sdk.register(
        value -> sink.next(value),
        error -> sink.error(error),
        () -> sink.complete()
    );

    sink.onCancel(registration::cancel);
    sink.onDispose(registration::unregister);
});
~~~

In this snippet:

- `sink.onCancel` triggers only when **the subscription is cancelled**; use it to command the SDK to stop work for that subscription if the API supports it.
- `sink.onDispose` runs on **complete, error, or cancel**, making it suitable for detaching callbacks/listeners.
- On cancel, `onCancel` runs **before** `onDispose`.
- Neither hook means `sink.next` accepts `null` or callbacks after terminal; the adapter must guard against those cases.
- If the `register` API can invoke callbacks synchronously or throw before returning a handle, handle incomplete initialization/races; cleanup hooks registered late may execute immediately if the sink is already disposed.

Use a **separate registration per subscription**, unless intentionally implementing a shared hot source with independent lifecycle management. If two HTTP clients share one handle and one client cancels and closes the entire source, the other client can be disrupted.

With real APIs, pair cancellation with **backpressure**, rather than letting overly fast callbacks accumulate unbounded buffers. `Flux.create` offers `FluxSink.OverflowStrategy`, but choosing `BUFFER`, `DROP`, `LATEST`, or `ERROR` must match the business's tolerance for data loss. Proper listener cleanup alone does not solve overload.

## 9. Cancellation in Spring WebFlux

In Spring WebFlux running on Reactor Netty, many requests are served on a shared pool of **event-loop threads**. A controller typically returns `Mono` or `Flux` directly so the framework holds the subscription and manages the lifecycle while the response is being sent.

Example SSE endpoint **depending on a real SDK**:

~~~java
// Illustrative controller snippet in a Spring Boot WebFlux project;
// sensorService.stream() returns a Flux<Event> with managed listener.
@GetMapping(value = "/sensors", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Event> events() {
    return sensorService.stream()
        .doFinally(signal -> metrics.record(signal));
}
~~~

This is not a standalone Java class because `sensorService`, `metrics`, `Event`, and the annotations belong to a Spring project. The point is to **return the publisher** to the framework and attach lifecycle metrics. `sensorService.stream()` must manage its own resources, for instance via `usingWhen`, `using`, or cleanup callbacks.

When a browser closes SSE, the server **may** detect the closed connection and cancel the subscription, leading to cleanup. However, detection timing depends on the OS, network, container, and when the server attempts to write data; never promise cleanup happens in the exact millisecond a user closes the tab.

Avoid two anti-patterns:

~~~java
// Wrong: detaches the task from the HTTP request lifecycle:
Flux<Event> events() {
    sensorService.stream().subscribe(event -> save(event));
    return Flux.empty();
}

// Wrong: blocking call directly on the event-loop thinking Mono/Flux is enough:
Mono<Result> result = Mono.just(blockingClient.fetch());
~~~

These two snippets illustrate design mistakes only, not standalone code. For blocking APIs that must be used, consider `Mono.fromCallable(() -> blockingClient.fetch()).subscribeOn(Schedulers.boundedElastic())` and control concurrency, instead of blocking the event-loop. Still, resource **cleanup** must be managed properly—it does not appear automatically just by using a scheduler.

If a business task **must continue even if the client disconnects** (such as payments or transaction recording), you cannot rely on an HTTP subscription's lifecycle to guarantee completion. Design appropriate transactions, outbox/queues, and idempotency. Response cancellation should not accidentally cancel a critical, independently managed background task.

## 10. Boundary Between Cleanup and Error Handling

Cleanup can also **fail**: closing a file fails, rollback errors, the database connection drops, or an SDK refuses to unregister a listener. Avoid two false assumptions: “the pipeline completed so cleanup certainly succeeded” and “cleanup failed so we can always still change the HTTP response”.

With `using(..., eager=true)`, an exception from cleanup can replace the terminal before downstream receives it. With `usingWhen`, a failing cleanup publisher can cause downstream to receive the corresponding error; in `Mono.usingWhen`, a value still waiting on cleanup can be discarded if cleanup fails. With `Flux.usingWhen`, elements already sent before cleanup **cannot be retracted**.

`doFinally`, meanwhile, is mainly for side effects **after terminal/cancel has been propagated**. If logging/metrics inside the hook throw an exception, do not expect it to alter an already-returned HTTP status. Design cleanup with dedicated error handling and recording, avoiding throwing exceptions from side-effect hooks that cannot reliably recover.

**Practical rule:** if a resource step is an essential condition for declaring success (committing a transaction, sending a final acknowledgment), place cleanup/commit in the **main reactive flow** via `usingWhen` or appropriate composition operators so the result is only acknowledged after that operation finishes, rather than using `doFinally` as “fire-and-forget”.

Additionally, `cancel` is a situation where downstream is no longer listening; there is not always a subscriber left to receive a cleanup error. Therefore, log/metric resource-cleanup errors and provide reclamation/reconciliation mechanisms at the resource layer if the business requires it.

## 11. Quick Comparison of Approaches

| Need | Recommended approach | Why |
| --- | --- | --- |
| Measure duration, count completion/error/cancel | `doFinally` | One hook observes all three branches |
| Log errors while keeping the error intact | `doOnError` | Does not alter the terminal signal |
| Send a dedicated notification when a subscriber cancels | `doOnCancel` | Runs on the cancellation branch |
| Supply a synchronous resource per subscriber, then close | `Flux.using` / `Mono.using` | Clear resource scope from acquisition to cleanup |
| Supply resources and async commit/rollback/close | `Flux.usingWhen` / `Mono.usingWhen` | Cleanup is a publisher with its own lifecycle |
| Integrate multi-event listener/callback APIs | `Flux.create` with `sink.onCancel` and `sink.onDispose` | Bridges events, forwards cancel, and detaches listeners |
| Log only after complete/error, without cancel | `doAfterTerminate` | Does not replace cleanup on cancel |
| Handle SSE/HTTP cancellation | Return publisher to WebFlux + source with cleanup | Framework controls subscription, source releases handles |
| Manage resources shared across multiple subscribers | Application-defined shared lifecycle/ref counting | Cancelling one subscriber must not arbitrarily close shared resources |

A single `onComplete` callback is insufficient to manage everything; a single `onCancel` callback is equally insufficient if the source can complete or error.

## 12. Common Mistakes and How to Prevent Them

1. **Cleaning up only on complete:** misses error/cancel and easily leaks listeners, sockets, or readers. Use `doFinally`, `using`, or `usingWhen` as needed.
2. **Using `doOnTerminate` as a finally:** this operator does not handle pure cancel paths. Use `doFinally` when all three branches must be covered.
3. **Using only `FluxSink.onCancel` to unregister listeners:** complete/error does not invoke the cancel hook; unregister listeners in `onDispose`.
4. **Closing resources when building the publisher:** the resource may close before the subscription even finishes reading. Acquire and close within the same reactive scope.
5. **`try-with-resources` outside a lazy publisher:** the `try` block can finish before the subscriber uses the resource. Use `using`/`usingWhen` rather than returning a Flux tied to an already-closed resource.
6. **Calling `block()` to wait for async cleanup on the event-loop:** easily stalls other requests. Use `usingWhen` with a cleanup publisher.
7. **Ignoring cleanup errors:** results get reported as successful even though a transaction didn't commit or a resource didn't close. Define eager/delayed semantics and error reporting.
8. **Closing a shared resource when one consumer cancels:** can break other subscribers' streams. Separate per-subscription resources from singletons/pools.
9. **Not handling races between cancel and callbacks:** double cleanup or late callbacks accessing closed resources. Make cleanup idempotent and thread-safe; verify SDK contracts.
10. **Treating cancel as HTTP 500 error:** cancel is not automatically an `onError`; record distinct metrics.
11. **Manually calling `subscribe()` in a controller:** detaches processing lifecycle from HTTP, so client cancellation can no longer control upstream properly. Return the publisher to WebFlux.
12. **Believing `dispose()` always waits for external tasks to stop completely:** cancel is a request; blocking SDKs or external systems may need separate stop mechanisms, timeouts, and confirmations.
13. **Relying on global ordering across multiple hooks:** `doFinally` runs after downstream terminal, and multiple hooks can run in reverse order. Test with realistic sync/async flows.
14. **Not measuring resource leaks:** failing to track active listeners/connections/handles hides leaks until high load. Use metric counters incremented on acquire and decremented on cleanup, verifying balance across all three branches.

## 13. Resource Lifecycle Testing Checklist

For every resource-backed publisher, test:

- **Empty completion (`Mono.empty`/`Flux.empty`)**: resource is closed even with zero `onNext` values.
- **Completion with multiple elements**: emits the right data, closes exactly once, callback sees `ON_COMPLETE`.
- **Error immediately upon subscribe**: still cleans up the resource properly; downstream receives the error per contract.
- **Error after several elements**: resource is closed, no further `onNext` after terminal.
- **Cancel immediately upon subscribe**: subscription stops, acquired resource is cleaned up, no fake `onComplete`.
- **`take(n)` cancels upstream**: upstream cleanup sees cancel, downstream can complete normally.
- **HTTP client disconnects mid-SSE**: once the server detects it, active registrations return to baseline.
- **Cleanup itself throws an exception**: verify whether the cleanup error replaces the terminal or is reported as dropped/logged per operator.
- **Two concurrent subscribers**: do not mistakenly close shared resources; each per-subscription resource has a clear owner.
- **Cancel and error occur concurrently**: resource release is idempotent, no late callbacks accessing a released handle.
- **Slow async cleanup**: verify `usingWhen` terminal is considered complete only according to the chosen semantics.
- **Infinite sources (`Flux.never`, SSE)**: can trigger active cancellation and confirm cleanup without waiting for completion.

With `reactor-test`, use `StepVerifier` to verify `expectNext`, `verifyComplete`, `expectError`, or `thenCancel`. To confirm cleanup, use `AtomicBoolean`/counters or appropriate await conditions instead of relying on random timing.

Verification idea example (illustrative test code; requires `reactor-test` in test scope):

~~~java
AtomicBoolean closed = new AtomicBoolean();
Flux<Integer> stream = Flux.using(
    () -> "resource",
    ignored -> Flux.just(1, 2),
    ignored -> closed.set(true),
    true
);

StepVerifier.create(stream)
    .expectNext(1, 2)
    .verifyComplete();

assertTrue(closed.get()); // JUnit assertion: eager cleanup has run.
~~~

Here `assertTrue` belongs to JUnit, and imports are needed in a test project. With `doFinally`, because callbacks may run after the terminal, synchronize appropriately before checking side effects. Do not turn this test snippet into a `main` method calling `assertTrue` without JUnit.

**Key takeaway:** Reliable resource management must account for **complete, error, and cancel**. `doFinally` fits observing all three; `using` manages resources with synchronous cleanup; `usingWhen` manages asynchronous cleanup; `FluxSink.onCancel` and `onDispose` are essential when bridging callback APIs. In Spring WebFlux, **return the publisher to the framework**, keep cleanup bound to the right subscription, and do not treat HTTP termination as a guarantee that all external tasks/resources stopped immediately.

**Official sources:** [Reactor Reference — Handling Errors: Using Resources and the Finally Block](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html); [Reactor Flux Javadoc — using, usingWhen, doFinally](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html); [Reactor Mono Javadoc — usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).