# `using` and `usingWhen` for Resource Lifecycle in Project Reactor / Spring WebFlux

## 1. Why Does Resource Lifecycle Matter in Reactive?

A publisher might not be subscribed to immediately when a Java method returns; once subscribed to, it can **complete**, **emit an error**, or be **cancelled before finishing**. If code opens a file, creates a connection, acquires a lock, registers a listener, or holds a session and closes it only on the success branch, resources can leak when requests are cancelled, time out, or fail upstream.

In imperative programming, `try/finally` or `try-with-resources` wraps the execution duration of the work:

```java
try (SomeResource resource = openResource()) {
    return useResource(resource);
}
```

In reactive programming, returning a `Mono`/`Flux` **does not mean the work has finished running**. If you close the resource before subscribing, the reactive source may try to use an already-closed resource. Project Reactor provides dedicated factories to manage resources **per subscription**:

- **`Mono.using` / `Flux.using`**: acquires a resource via a `Callable`, uses it to create a publisher, and performs **synchronous cleanup** (a `Consumer<D>` callback or `AutoCloseable.close()`).
- **`Mono.usingWhen` / `Flux.usingWhen`**: acquires a resource from a **`Publisher<D>`**, creates a publisher using the resource, and performs **cleanup via an asynchronous Publisher**, optionally separating success, error, and cancel branches.

This topic belongs to the **Cancellation and resources** group. The focus is not merely “whether close is called or not”, but also **when close occurs**, **what signals downstream receives**, **whether cancelling the subscription runs cleanup**, **how cleanup errors are handled**, and **choosing the right API for connections/transactions**.

### Objectives

After this lesson, you can:

1. Accurately describe acquire → use → release across the three paths `onComplete`, `onError`, and `cancel`.
2. Distinguish synchronous cleanup of `using` from publisher-based cleanup of `usingWhen`.
3. Understand `eager` / non-eager when using `using`, especially the difference between a valued `Mono` and a multi-element `Flux`.
4. Understand why `Mono.usingWhen` must **wait for cleanup to finish before emitting its value**, whereas `Flux.usingWhen` can forward `onNext` during streaming and only wait for cleanup at terminal.
5. Write tests with `StepVerifier` for success, error, cancellation, and cleanup failure.
6. Apply these accurately in WebFlux and recognize when to use Spring's built-in transaction/resource management mechanisms.

## 2. Signal Model: Cleanup Is Part of the Subscription

Suppose a publisher uses a connection:

```text
subscribe
   |
   v
acquire resource
   |
   v
resourceClosure(resource) -> work publisher
   |
   +---- onNext ... -> onComplete ----> complete cleanup
   |
   +---- onNext ... -> onError(e) ----> error cleanup
   |
   +---- subscriber.cancel() --------> cancel cleanup
```

These three paths differ:

- **Completion (`onComplete`)**: the task finished normally, having emitted 0, 1, or more elements.
- **Error (`onError`)**: the task failed; cleanup must execute without losing the original error context.
- **Cancellation (`cancel`)**: the subscriber no longer requests data, for example an HTTP client disconnected, `take(n)` got enough elements, or a timeout cancelled upstream. **Cancel is neither `onComplete` nor `onError` sent to the subscriber.**

`using` and `usingWhen` manage the portion of resources that the **operator directly owns**. They cannot guarantee an immediate stop of external physical tasks if the driver/SDK does not honor cancellation. Therefore, proper timeouts and driver configuration are needed.

### Why Not Just Use `doFinally`?

`doFinally` observes when a sequence ends via `SignalType.ON_COMPLETE`, `ON_ERROR`, or `CANCEL`, which is very useful for recording metrics, but its callback is **synchronous**, not a mechanism that waits for an asynchronous cleanup publisher before publishing the terminal signal. If `close()` must return `Mono<Void>` or a transaction must commit/roll back via async I/O, `usingWhen` is more appropriate.

Moreover, a misplaced `doFinally` may fail to cover resource creation or isolate each subscription. `using`/`usingWhen` bind **acquire, use, and cleanup** into one explicit structure.

## 3. Comparison Table: `using` vs `usingWhen`

| Feature | `using` | `usingWhen` |
|---|---|---|
| How resource is supplied | `Callable<? extends D>` | `Publisher<D>` |
| How work is created | Function from resource → `Mono`/`Publisher` | Function from resource → `Mono`/`Publisher` |
| Cleanup | Synchronous `Consumer<D>` or `AutoCloseable.close()` | A `Publisher<?>` subscribed to for cleanup |
| Waits for async cleanup? | No; callback runs synchronously | Yes; terminal is typically delayed until cleanup finishes |
| Separate complete/error/cancel branches? | Shared cleanup callback | Has a 5-parameter overload separating the three branches |
| Best suited for | Synchronous `close()`, file handles, synchronously used buffers/locks | R2DBC connections, commit/rollback, `close` returning `Publisher` |
| Cleans up on cancel? | Yes, once the resource was acquired successfully | Yes, when the resource was acquired, via the cancel cleanup branch |
| One resource for multiple subscribers? | Created **fresh per subscription** via callable | Resource-supplying publisher is subscribed **per subscription** |
| Eager/non-eager | Has an `eager` flag on corresponding overloads | Does not use an `eager` flag; depends on cleanup publisher |

**Do not use `.block()` inside an async cleanup callback just to force `using`.** This turns an asynchronous I/O operation into a blocking one and can stall the WebFlux event loop. Choose `usingWhen` so Reactor subscribes and coordinates cleanup along with signals.

## 4. `using`: Synchronous Resource Source, Synchronous Cleanup

Typical signatures (types simplified for readability):

```java
Flux.using(
    Callable<D> resourceSupplier,
    Function<D, Publisher<T>> sourceSupplier,
    Consumer<D> resourceCleanup,
    boolean eager
);

Mono.using(
    Callable<D> resourceSupplier,
    Function<D, Mono<T>> sourceSupplier,
    Consumer<D> resourceCleanup,
    boolean eager
);
```

In the actual API, generics use wildcards to accept subtypes. Reactor also has overloads without `eager` and overloads for `AutoCloseable` resources to invoke `close()` automatically. When you want exact control over ordering, specify `eager` explicitly.

Example of a resource managing a synchronous cache snapshot:

```java
Mono<String> snapshot = Mono.using(
        () -> openSnapshot(),                  // acquire on subscribe
        resource -> Mono.fromSupplier(
                () -> resource.readValue()),   // use during execution
        resource -> resource.close(),          // synchronous release
        true                                   // eager cleanup
);
```

This is an **illustrative snippet**, requiring synchronous `openSnapshot()`, `readValue()`, and `close()` defined in the application. The produced publisher is **cold**: each subscription runs the supplier to obtain its own resource; merely creating the `snapshot` variable does not call `openSnapshot()`.

Corresponding lifecycle:

```text
Create Mono variable      : not acquired yet
Subscriber subscribes     : acquire
Inner source executes     : use
Source completes / errors : cleanup
Send terminal downstream  : depends on eager
```

### What Do `eager=true` and `eager=false` Mean?

With `eager=true`, cleanup runs **before forwarding the success/error terminal downstream**. With `eager=false`, cleanup usually happens **after the terminal**, and a cleanup error on the non-eager path cannot change an already-sent terminal; Reactor reports/drops the error per the corresponding policy.

Notable difference between `Mono` and `Flux`:

- `Mono.using(..., eager=true)` has **at most one value**. If the source has a value, eager cleanup occurs **even before `onNext(value)`** is sent downstream; if cleanup fails, that value may be discarded and downstream receives the cleanup error.
- `Flux.using(..., eager=true)` may **already have emitted multiple `onNext`** while the resource was still open; cleanup happens before the **terminal**, and already-emitted `onNext` items cannot be retracted.
- `eager=false` does not mean “no cleanup needed”. It still performs cleanup, just without synchronizing it with the terminal in the same eager way.

Example observing `Mono` ordering:

```java
Mono<String> one = Mono.using(
        () -> new Handle(),
        handle -> Mono.fromSupplier(handle::read),
        Handle::close,
        true
);
```

Here `Handle` is an **illustrative class**, not a Reactor API. If downstream receives `"abc"`, eager cleanup already succeeded before the value was passed down; this is useful when `close` can alter the final decision of success/failure.

### Use `AutoCloseable` When Appropriate

For types implementing `AutoCloseable`, you can use the overload:

```java
Mono<String> result = Mono.using(
        () -> new MyAutoCloseableResource(),
        resource -> Mono.just(resource.read()),
        true
);
```

This overload invokes `close()` from `AutoCloseable`. The snippet is illustrative only: `MyAutoCloseableResource` must be defined. Note that `resource.read()` in the mapper runs when the source supplier executes after acquire; if reading is blocking, ensure the whole subscription runs on an appropriate scheduler.

**Do not create a resource outside `using` and reuse it indiscriminately**:

```java
// Wrong if multiple subscriptions share one handle that is not allowed to be reused:
MyAutoCloseableResource handle = new MyAutoCloseableResource();
Mono<String> wrong = Mono.using(
        () -> handle,
        h -> Mono.just(h.read()),
        true
);
```

The first subscription can close `handle`; the second subscription receives an already-closed resource. If you want each subscriber to have its own resource, the factory **must create the resource inside the callable**.

## 5. `usingWhen`: Acquiring and Releasing Resources via Publisher

`usingWhen` is the choice when acquire or cleanup is performed by a Publisher that cannot safely be called synchronously. Two forms to remember:

```java
Flux.usingWhen(
    Publisher<D> resourceSupplier,
    Function<D, Publisher<T>> resourceClosure,
    Function<D, Publisher<?>> asyncCleanup
);
```

And the form distinguishing the three terminations:

```java
Flux.usingWhen(
    Publisher<D> resourceSupplier,
    Function<D, Publisher<T>> resourceClosure,
    Function<D, Publisher<?>> asyncComplete,
    BiFunction<D, Throwable, Publisher<?>> asyncError,
    Function<D, Publisher<?>> asyncCancel
);
```

`Mono.usingWhen` also has two corresponding forms, except `resourceClosure` returns `Mono<? extends T>`. The signatures above are **parameter-type outlines**; see the Javadoc at the end of the lesson for exact wildcards.

Simple example with a reactive connection:

```java
Mono<String> loaded = Mono.usingWhen(
        acquireConnection(),                  // Mono<Connection>
        connection -> connection.fetchName(), // Mono<String>
        connection -> connection.closeAsync() // Mono<Void>
);
```

This is a **hypothetical snippet**: `acquireConnection`, `Connection.fetchName`, and `closeAsync` represent project APIs, not generic R2DBC or Spring method names. The key point is that cleanup returns `Mono<Void>` and Reactor **subscribes to it**, without you calling `.subscribe()` or `.block()`.

### Why Must Cleanup Be a Publisher?

A connection pool or reactive transaction may need I/O to return a connection, flush, commit, or roll back. If you write:

```java
resource -> {
    resource.closeAsync();    // only creates Mono, not subscribed yet
}
```

then you **do not** complete cleanup merely by instantiating a publisher. `usingWhen` expects the callback to **return** the publisher so it can subscribe and await termination.

Syntactically right:

```java
resource -> resource.closeAsync()
```

If the callback has multiple steps, compose with `.then(...)`, `onErrorResume(...)`, or `Mono.defer(...)` per policy, but return a semantically valid publisher. Do not swallow cleanup errors inadvertently.

## 6. Branching `asyncComplete`, `asyncError`, `asyncCancel`

The 5-parameter overload is used when cleanup depends on the cause of termination:

```java
Flux<String> flow = Flux.usingWhen(
        openSession(),                       // Publisher<Session>
        session -> session.stream(),         // Publisher<String>
        session -> session.commit(),         // complete -> commit
        (session, error) -> session.rollback(), // error -> rollback
        session -> session.rollback()        // cancel -> rollback
);
```

This is a **design snippet** with a hypothetical `Session`. It only expresses the meaning of the three branches; in a real system, session release/closing must also be included per the API contract (for example inside the `commit/rollback` publishers or using `then(closeAsync())`). A plain commit/rollback command alone cannot be assumed to have returned the connection to the pool.

Scenarios:

| Event from `resourceClosure` | Selected cleanup callback | Result if cleanup completes successfully |
|---|---|---|
| `onComplete` (with or without elements) | `asyncComplete(resource)` | Downstream receives successful terminal |
| `onError(originalError)` | `asyncError(resource, originalError)` | Downstream receives the original error |
| Subscriber `cancel()` | `asyncCancel(resource)` | Cleanup is triggered; no new `onComplete`/`onError` is sent to the cancelled subscriber |

**Do not equate cancel with success.** A streaming transaction interrupted midway by the client generally cannot be treated automatically as a valid commit. For transactional APIs, cancel may need rollback. The exact decision belongs to business rules and driver contracts.

Reactor allows `asyncCancel` to be `null` in the corresponding overload to fall back to `asyncComplete` on cancel, but that is not a safe default for transactions: if cancellation requires rollback, provide a dedicated cancel callback.

### Is One Shared Cleanup Enough?

The 3-parameter form:

```java
Flux.usingWhen(
        acquire(),
        resource -> work(resource),
        resource -> release(resource)
);
```

uses the same cleanup callback for complete, error, and cancel. It fits when all paths simply need `close`/`release` in the exact same way. Use the 5-parameter form when success must commit while error/cancel must roll back or when paths differ in metrics/release behavior.

## 7. Downstream Signals During Asynchronous Cleanup

This is a difference that easily causes bugs if you compare the two APIs by name alone.

### `Mono.usingWhen`: Waits for Cleanup Before Emitting Result

If `resourceClosure` is a `Mono<String>` emitting `"OK"`, Reactor cannot send `"OK"` downstream and then report that cleanup failed while still honoring a successful Mono contract. Therefore, `Mono.usingWhen` **defers even the valued success signal** until cleanup finishes.

```text
t=0:    acquire resource
t=1:    use -> internal result "OK"
t=2:    start async cleanup
t=5:    async cleanup completes
t=5:    downstream receives onNext("OK"), onComplete()
```

If cleanup fails at `t=5`, downstream receives `onError(cleanupFailure)` instead of `"OK"`. The internally produced value may be discarded.

For `Mono.empty()`, downstream likewise waits for cleanup before receiving `onComplete`; for `Mono.error(original)`, cleanup runs and then downstream receives the original error if cleanup succeeds.

### `Flux.usingWhen`: Can Stream Elements Before Cleanup

A `Flux` can emit multiple elements while the resource is still open:

```text
acquire -> onNext(A) -> onNext(B) -> source onComplete
                                                |
                                                v
                                         async cleanup
                                                |
                                                v
                                      downstream onComplete
```

With `Flux.usingWhen`, elements `A` and `B` **may already have arrived downstream** before cleanup begins. If final cleanup fails, downstream receives `onError(cleanupFailure)` instead of a successful terminal; **already-received `A` and `B` are not retracted**.

Therefore, do not promise “the whole Flux will not reveal any data until commit finishes”. If business rules require **publishing data only after commit**, design an appropriate Mono/buffer/transaction boundary; streaming and atomic visibility guarantees are two different requirements.

### Observable Signals Table

| `resourceClosure` | Cleanup | `Mono.usingWhen` | `Flux.usingWhen` |
|---|---|---|---|
| Success with value | Completes | Value → complete, after cleanup | Possibly multiple values before cleanup; complete after cleanup |
| Empty completion | Completes | Complete after cleanup | Complete after cleanup |
| Success | Error | Cleanup error only, Mono value discarded | May have already received some `onNext`; terminal cleanup error |
| Original error | Completes | Original error after cleanup | Original error after cleanup |
| Original error | Cleanup error | Cleanup error replaces or wraps, original error preserved as suppressed/cause depending on implementation | Similarly, no successful terminal |
| Cancel | Cancel cleanup triggered | No new terminal sent to cancelled subscriber | No new terminal sent to cancelled subscriber |

Use `doOnDiscard`, metrics, or controlled logging when elements contain releasable resources and may be discarded due to cleanup failure.

## 8. Acquire Errors and Cleanup Errors: Do Not Miss Them

### Acquire Fails to Supply a Resource

`usingWhen` takes a resource publisher, so the acquire step itself can:

- **Complete empty** without supplying a resource: the flow completes empty; `resourceClosure` and cleanup do not run because there is no resource.
- **Emit an error before supplying a resource**: downstream receives the acquire error; cleanup is not called for a nonexistent resource.
- **Be cancelled before supplying a resource**: the acquire subscription is cancelled; internal cleanup inside the acquire publisher is that publisher's responsibility.

Thus, the acquire publisher should ideally emit **a single resource**. Avoid using a `Flux` emitting multiple connections as `resourceSupplier`: `usingWhen` only uses one resource; extra emitted resources may be dropped without going through normal resource-closure cleanup.

```java
Mono<Handle> acquisition = Mono.fromSupplier(Handle::new);
```

This is a snippet with an illustrative `Handle`. If acquire is genuinely reactive I/O, return the I/O publisher from the driver rather than forcing it with `.block()`.

### Cleanup Fails

Suppose the main processing succeeds, yet `asyncComplete` returns `Mono.error(closeError)`. `usingWhen` must not report success as if close finished; downstream will see the cleanup failure. Across overloads, Reactor may **wrap** the cleanup failure or attach the original error as suppressed; do not write tests relying on wrapper message strings without checking the exact Reactor version.

If the main work errors and cleanup also errors, the cleanup error usually becomes the final signal; to preserve diagnostics, log/attach the root cause and inspect `suppressed`/`cause` per the API.

**Do not write `onErrorResume(e -> Mono.empty())` after cleanup just to make the dashboard green.** Doing so can turn a failed connection return into an apparent success. If fallback/retry exists, define policies based on error type and idempotency of the cleanup operation.

### Should Cleanup Be Retried?

Retrying can make sense when cleanup is idempotent and the resource allows retries, yet it can also trigger repeated side effects (especially commit). Do not blindly add `.retry()` to every commit/rollback operation; understand that transaction state may be indeterminate after a network error and choose recovery accordingly.

## 9. Cancellation, `take(n)`, Timeout, and HTTP Client Disconnect

A WebFlux request may terminate not from the source's terminal signal, but by being cancelled from downstream. Example:

```java
Flux<String> limited = Flux.usingWhen(
        open(),
        resource -> resource.stream(),
        resource -> resource.closeAsync()
).take(3);
```

This is a snippet assuming `open()` and `stream()` return Publishers. If the source has more than three elements, `take(3)` typically **cancels the upstream subscription** after collecting three elements. `usingWhen` must enter the cancel cleanup path; **do not assume the `asyncComplete` branch is called** when using the overload with a dedicated cancel branch.

The same happens when:

- The client closes an SSE/WebSocket/HTTP streaming connection.
- A subscriber calls `Disposable.dispose()` or `Subscription.cancel()`.
- Another operator selects a different source (`switchMap`, `take`, timeout, etc.) and cancels the current source.

### Does Timeout Ensure Cleanup Completes?

```java
Mono<String> guarded = Mono.usingWhen(
        acquire(),
        resource -> useAsync(resource),
        resource -> releaseAsync(resource)
).timeout(Duration.ofSeconds(2));
```

Timeout can cancel upstream `usingWhen` upon expiration, triggering cancel cleanup. However, `timeout` **does not guarantee an I/O SDK without cancellation support will stop immediately**. If cleanup itself is also slow/broken, monitor it with metrics and configure timeouts at the driver/pool layer.

Placing `timeout` **inside or outside** `usingWhen` can change whether upstream sees `onError` or `cancel`:

- `usingWhen(...).timeout(...)`: timeout sits downstream; it can cancel `usingWhen`, selecting the cancel branch.
- `usingWhen(acquire, resource -> useAsync(resource).timeout(...), ...)`: timeout sits **inside `resourceClosure`**, typically emitting `onError(TimeoutException)` to `usingWhen`, selecting the error cleanup branch.

This difference is especially important when cleanup corresponds to commit/rollback. Do not move operator positions mechanically without testing all three paths.

### Asynchronous Cleanup After the Subscriber Has Cancelled

After cancel, the subscriber is no longer waiting for results; async cleanup still needs to run to return the resource. In real applications, do not rely on an external callback being able to `await` cleanup merely via `dispose()`. Verify via the cleanup publisher, traces, metrics, pool resource counts, and tests with latches/probes.

## 10. Runnable Java 17+ Program: Full Tests of All Three Lifecycle Paths

This example runs standalone with **Project Reactor Core 3.6.6**, JUnit Jupiter, and `reactor-test`. No Spring Boot or database startup is needed. A fake resource `Tracked` logs to a thread-safe list to verify when it is opened, used, and closed. `StepVerifier` verifies signals, and `CountDownLatch` helps verify cleanup after cancellation without depending on arbitrary thread scheduling.

### 10.1. File Structure

```text
reactor-resource-lifecycle/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── ResourceLifecycleTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
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
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/test/java/edu/demo/ResourceLifecycleTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ResourceLifecycleTest {

    static final class Tracked implements AutoCloseable {
        private final List<String> events;
        private boolean closed;

        Tracked(List<String> events) {
            this.events = events;
            events.add("acquire");
        }

        String read() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            events.add("use");
            return "VALUE";
        }

        @Override
        public void close() {
            closed = true;
            events.add("close");
        }
    }

    @Test
    void monoUsingEagerClosesBeforeDownstreamSeesValue() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.using(
                () -> new Tracked(events),
                handle -> Mono.fromSupplier(handle::read),
                Tracked::close,
                true
        ).doOnNext(value -> events.add("seen:" + value));

        StepVerifier.create(mono)
                .expectNext("VALUE")
                .verifyComplete();

        assertEquals(
                List.of("acquire", "use", "close", "seen:VALUE"),
                events
        );
    }

    @Test
    void fluxUsingClosesOnBusinessError() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> flux = Flux.using(
                () -> new Tracked(events),
                handle -> Flux.concat(
                        Flux.just(handle.read()),
                        Flux.<String>error(
                                new IllegalStateException("business"))
                ),
                Tracked::close,
                true
        );

        StepVerifier.create(flux)
                .expectNext("VALUE")
                .expectErrorMessage("business")
                .verify();

        assertEquals(List.of("acquire", "use", "close"), events);
    }

    @Test
    void fluxUsingClosesOnCancellation() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> never = Flux.using(
                () -> new Tracked(events),
                handle -> Flux.<String>never(),
                Tracked::close,
                true
        );

        StepVerifier.create(never)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(List.of("acquire", "close"), events);
    }

    @Test
    void monoUsingWhenDelaysValueUntilCleanupIsDone() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Mono.fromSupplier(handle::read),
                handle -> Mono.fromRunnable(handle::close)
        ).doOnNext(value -> events.add("seen:" + value));

        StepVerifier.create(mono)
                .expectNext("VALUE")
                .verifyComplete();

        assertEquals(
                List.of("acquire", "use", "close", "seen:VALUE"),
                events
        );
    }

    @Test
    void usingWhenRunsErrorCleanupAndPreservesOriginalError() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> flux = Flux.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Flux.<String>error(
                        new IllegalArgumentException("invalid")),
                handle -> Mono.fromRunnable(() -> {
                    events.add("complete-path");
                    handle.close();
                }),
                (handle, error) -> Mono.fromRunnable(() -> {
                    events.add("error-path:" + error.getMessage());
                    handle.close();
                }),
                handle -> Mono.fromRunnable(() -> {
                    events.add("cancel-path");
                    handle.close();
                })
        );

        StepVerifier.create(flux)
                .expectErrorMessage("invalid")
                .verify();

        assertEquals(
                List.of("acquire", "error-path:invalid", "close"),
                events
        );
    }

    @Test
    void usingWhenRunsCancelCleanup() throws InterruptedException {
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch closeDone = new CountDownLatch(1);

        Flux<String> flux = Flux.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Flux.<String>never(),
                handle -> Mono.fromRunnable(() -> {
                    events.add("complete-path");
                    handle.close();
                }),
                (handle, error) -> Mono.fromRunnable(() -> {
                    events.add("error-path");
                    handle.close();
                }),
                handle -> Mono.fromRunnable(() -> {
                    events.add("cancel-path");
                    handle.close();
                    closeDone.countDown();
                })
        );

        StepVerifier.create(flux)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertTrue(closeDone.await(2, TimeUnit.SECONDS));
        assertEquals(
                List.of("acquire", "cancel-path", "close"),
                events
        );
    }

    @Test
    void usingWhenCleanupErrorDiscardsMonoValue() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Mono.fromSupplier(handle::read),
                handle -> Mono.fromRunnable(() -> {
                    handle.close();
                    throw new IllegalStateException("cleanup-failed");
                })
        );

        StepVerifier.create(mono)
                .expectErrorMatches(error ->
                        "cleanup-failed".equals(error.getMessage())
                        || (error.getCause() != null
                            && "cleanup-failed".equals(
                                error.getCause().getMessage())))
                .verify();

        assertEquals(List.of("acquire", "use", "close"), events);
    }

    @Test
    void virtualTimeProvesAsyncCleanupDelaysMonoSuccess() {
        StepVerifier.withVirtualTime(() ->
                Mono.usingWhen(
                        Mono.just("resource"),
                        resource -> Mono.just("OK"),
                        resource -> Mono.delay(Duration.ofSeconds(5)).then()
                ))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("OK")
                .verifyComplete();
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected outcome when dependencies are downloaded and assertions hold: **8 tests pass with zero failures/errors**. This is a standalone Java 17+ test suite; there is no business output on stdout, because `StepVerifier` and `assertEquals` **report success via test status**. The Maven Surefire summary typically looks like:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
```

Other Maven lines (timings, versions, build logs) may vary by environment.

### Why Were the Tests Designed This Way?

1. `monoUsingEager...`: highlights that the resource is closed **before downstream observes `onNext`** of `Mono.using(..., true)`.
2. `fluxUsingClosesOnBusinessError`: verifies synchronous cleanup happens before the error terminal; already-emitted elements are not erased.
3. `fluxUsingClosesOnCancellation`: verifies cancel also releases the resource without needing the source to emit `onComplete`.
4. `monoUsingWhenDelaysValue...`: verifies `usingWhen` does not emit the Mono value before cleanup.
5. `usingWhenRunsErrorCleanup...`: ensures the error path goes through `asyncError` rather than being mistaken for complete.
6. `usingWhenRunsCancelCleanup`: ensures cancel selects `asyncCancel`; `CountDownLatch` avoids assuming async cleanup finished merely because the cancel test just ended.
7. `usingWhenCleanupError...`: verifies cleanup failure **replaces the success path** and discards the Mono value. The test accepts either the direct cleanup error or a wrapper with the matching cause.
8. `virtualTime...`: verifies waiting 5 seconds for async cleanup using virtual time without waiting 5 real seconds.

The tests use `Mono.fromRunnable` to simulate a cleanup Publisher completing synchronously. In real applications, `closeAsync` may signal later, fail, time out, or respond differently to cancellation. Add integration tests against the actual driver/pool for critical resources.

## 11. Blocking Resources: Placing the Scheduler Correctly

`using` does not automatically move blocking code to another thread. For example, reading a file with a synchronous API can block the event loop if subscribed in a WebFlux controller:

```java
Flux<String> fileLines(Path path) {
    return Flux.using(
            () -> new java.util.Scanner(
                    path, java.nio.charset.StandardCharsets.UTF_8),
            scanner -> Flux.<String>generate(sink -> {
                if (scanner.hasNextLine()) {
                    sink.next(scanner.nextLine());
                } else {
                    sink.complete();
                }
            }),
            java.util.Scanner::close,
            true
    ).subscribeOn(Schedulers.boundedElastic());
}
```

This is a **method snippet compilable inside a Java class** when importing `java.nio.file.Path`, `reactor.core.publisher.Flux`, and `reactor.core.scheduler.Schedulers`. `Scanner(Path, Charset)` exists in modern Java; `hasNextLine` / `nextLine` are blocking operations, so `subscribeOn(boundedElastic())` isolates reading from the WebFlux event loop.

`boundedElastic` also **does not create unlimited threads**: monitor worker limits, queues, and filesystem capacity. If file counts are large, choose appropriate concurrency and consider streaming buffers. For blocking tasks that can throw `IOException`, emit error signals and preserve cleanup; `Scanner` has an `ioException()` API worth checking if you need to detect I/O errors swallowed by `Scanner`.

Do not write:

```java
Mono.usingWhen(
        Mono.just(resource),
        r -> Mono.fromCallable(r::blockingRead),
        r -> Mono.fromRunnable(r::blockingClose)
);
```

assuming everything is non-blocking just because `Mono` appears. `Mono.fromCallable` and `Mono.fromRunnable` **only describe running a callback at subscription time**, not offloading threads. If callbacks block, an appropriate scheduler is still needed, though using a genuinely reactive driver is better whenever available.

## 12. R2DBC in Spring WebFlux: Closing Connections Asynchronously

An `io.r2dbc.spi.Connection` is created by `ConnectionFactory.create()` via a Publisher, and `close()` also returns `Publisher<Void>`. Hence **`usingWhen` fits semantically**.

The following is an **illustrative R2DBC integration method**; it requires the R2DBC SPI dependency and a real driver, plus imports for `Flux`, `Mono`, and `ConnectionFactory`. This is not a standalone Spring Boot application:

```java
record User(Long id, String name) {}

Flux<User> findUsers(ConnectionFactory factory) {
    return Flux.usingWhen(
            Mono.from(factory.create()),
            connection ->
                    Flux.from(
                        connection.createStatement(
                                "SELECT id, name FROM users")
                            .execute()
                    ).flatMap(result ->
                        Flux.from(result.map((row, meta) ->
                                new User(
                                    row.get("id", Long.class),
                                    row.get("name", String.class)
                                )
                        ))
                    ),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

Meaning:

- `Mono.from(factory.create())`: subscribes to connection acquisition when downstream subscribes.
- `resourceClosure`: executes SQL using the acquired connection and maps `Result` into data **while the connection is still open**.
- Complete/error/cancel cleanups all call `connection.close()` per the SPI; with a pool, closing may return the connection to the pool depending on the implementation.
- If the query fails, cleanup still runs and then forwards the error if cleanup succeeds; if the consumer cancels early, the cancel cleanup branch is triggered.

**Snippet conditions:** the `users` table must have matching columns and valid `id`/`name` values per schema; drivers may have rules on active statement/result counts, isolation, and row processing. The method does not include transaction commit/rollback: the example only illustrates acquiring/releasing a connection.

### Spring Already Has Connection Management Tools; Do Not Reinvent Them Unnecessarily

If you are using `DatabaseClient`, `R2dbcEntityTemplate`, Spring Data R2DBC, or `R2dbcTransactionManager`, **prefer Spring's connection/transaction management mechanisms**. These tools use Reactor Context to bind a connection to the active transaction. Calling `factory.create()` directly where transaction participation is needed can grab a different connection and **fail to participate in the current transaction**.

Spring provides `ConnectionFactoryUtils` for integrations that must manage connections themselves while still interacting with Reactor Context transactions. In particular, `ConnectionFactoryUtils.releaseConnection(connection, factory)` avoids closing a connection currently owned by a transaction manager; this logic differs from blindly calling `connection.close()`. Consult the Spring API documentation for your exact version when integrating.

Decision mindset:

- Managing an async resource not managed by Spring yourself: `usingWhen` can make sense.
- Standard queries in Spring Data R2DBC: use `DatabaseClient`/repository/template; let the framework handle acquisition and release.
- Multi-operation transactions: use `TransactionalOperator` or Spring's reactive transaction mechanism where suitable, rather than hand-rolling incomplete commit/rollback callbacks.

## 13. Reactive Transactions: Commit, Rollback, and Cancellation

In data-writing business flows, cleanup can be:

- **`asyncComplete` → commit** after all related operations succeed.
- **`asyncError` → rollback** if an error occurs.
- **`asyncCancel` → rollback** if the subscriber stops listening before the transaction completes.

`usingWhen` is a suitable foundation for modeling these paths. However, opening a transaction, committing, rolling back, and closing a connection according to driver/transaction manager contracts is a larger problem than a single `close()` call.

**Conceptual** example, not standalone code:

```java
Flux.usingWhen(
        acquireTransactionalSession(),
        session -> session.runBusinessFlow(),
        session -> session.commitAndRelease(),
        (session, failure) -> session.rollbackAndRelease(),
        session -> session.rollbackAndRelease()
);
```

Here `commitAndRelease`/`rollbackAndRelease` are **assumed** to include resource release, cleanup error handling, and transaction state per the system's contract. If commit fails, the state of the remote transaction may be indeterminate; blind retries can duplicate side effects.

### How to Use Spring's Transaction Manager

With Spring reactive transactions, applications usually work through `ReactiveTransactionManager` and `TransactionalOperator`:

```java
TransactionalOperator tx =
        TransactionalOperator.create(transactionManager);

Mono<Void> operation =
        databaseClient.sql(
                "UPDATE inventory SET reserved = reserved + 1 WHERE id = :id")
            .bind("id", itemId)
            .fetch()
            .rowsUpdated()
            .then();

Mono<Void> transactional = tx.transactional(operation);
```

This is an **integration snippet**: `transactionManager` must be a reactive transaction manager bean; `databaseClient` is configured to participate in the same transaction, and `itemId` has a value. `TransactionalOperator` belongs to `org.springframework.transaction.reactive.TransactionalOperator`.

`tx.transactional(operation)` binds the Publisher to a Spring-managed transaction instead of manually catching every error and cancellation to close the connection. Spring's APIs are built on Reactor Context, so do not replace them with a traditional `ThreadLocal`-based JDBC transaction in reactive code.

**Cancellation warning in transactions:** when a transactional publisher is cancelled midway, the rollback branch may be triggered per the transaction manager's mechanism. Do not use `.take(1)` inside a large streaming transaction and assume the entire business flow will still complete and commit; decide transaction boundaries explicitly and test the behavior.

## 14. Put All Steps Needing the Resource Inside `resourceClosure`

An easily overlooked rule from `usingWhen`'s Javadoc: operators that **need the resource to remain open and stable** must be described inside `resourceClosure`.

Not good:

```java
Flux<RowData> rows = Flux.usingWhen(
        acquireConnection(),
        connection -> streamRawRows(connection),
        connection -> closeConnection(connection)
);

// If the map operation below needs the connection still open, it may be too late.
Flux<String> mapped = rows.map(row -> row.readLobFromConnection());
```

This is an **illustrative diagram**, not existing APIs; `RowData.readLobFromConnection()` is assumed to require the connection. Downstream, `usingWhen` may complete cleanup before asynchronous work scheduled externally reuses the resource.

Move resource-dependent processing inside the scope:

```java
Flux<String> mapped = Flux.usingWhen(
        acquireConnection(),
        connection -> streamRawRows(connection)
                .concatMap(row -> readLobWhileOpen(connection, row)),
        connection -> closeConnection(connection)
);
```

The functions in the snippet are **hypothetical**; the idea is that the publisher using the resource must include reading LOBs, encoding, or flushing that genuinely needs the connection. If downstream receives objects holding references to the resource, it is best to convert them into standalone DTOs before cleanup.

Do not hold a `Connection`/cursor in a singleton field and share it across multiple subscriptions unless the driver explicitly allows it. Giving each subscription its own resource scope is the safer model.

## 15. Handling Cleanup Errors and Preserving Diagnostic Information

Distinguish three kinds of errors:

| Error kind | Timing | Handling principle |
|---|---|---|
| Acquire error | Before a resource exists | Forward error downstream; do not close a nonexistent resource |
| Business/use error | Inside `resourceClosure` | Run error cleanup; propagate original error if cleanup succeeds |
| Cleanup error | Inside close/commit/rollback callback | Do not silently claim success; preserve root cause for investigation |

For `using(eager=true)`, a synchronous cleanup error can **replace the terminal** and for a valued `Mono` can discard the value. With `using(eager=false)`, the terminal has already been sent downstream, so a cleanup error cannot turn the sequence into a new error for that subscriber; Reactor may drop/report it via hooks/logs. Therefore, if success is only valid when close succeeds, prefer eager or design with `usingWhen`.

For `usingWhen`, if the cleanup publisher emits `onError(t)`, the cleanup error becomes the observed terminal (possibly wrapped by Reactor in an exception indicating cleanup failure). If the use source also failed, the original cause is typically kept in `cause`/`suppressed`. When logging, do not just log `error.getMessage()` and lose `getCause()` and `getSuppressed()`.

If cleanup **never completes**, the terminal may never reach downstream, especially noticeable in `Mono.usingWhen`. Consider a timeout on the **cleanup publisher** when a driver might hang, along with an explicit error policy. However, do not add infinite retries to cleanup because that can hold connections forever without returning them to the pool.

### Do Not Manually `subscribe()` Inside Cleanup

Wrong:

```java
resource -> {
    closeAsync(resource).subscribe();
    return Mono.empty();
}
```

This is an illustrative callback, but wrong because returning `Mono.empty()` makes `usingWhen` think cleanup is done while `close` runs on a separate subscription. Close errors can be lost; the resource scope can end prematurely.

Right:

```java
resource -> closeAsync(resource)
```

Return the real publisher to `usingWhen`. If two cleanups are needed in sequence:

```java
resource -> flushAsync(resource)
        .then(closeAsync(resource))
```

If `flushAsync` fails, `.then(closeAsync(...))` will **not** automatically run `close`; to still close when flush fails, build a dedicated release policy and test it. Do not use `.then` carelessly assuming `close` always runs.

## 16. Comparing `using` / `usingWhen` with Other Approaches

| Technique | Fits when | Limitations |
|---|---|---|
| Java `try-with-resources` | Synchronous work finishes within lexical scope | If returning a lazy publisher outside scope, resource may close too early |
| `doFinally` | Observing terminal/cancel; metrics, simple synchronous cleanup | Does not wait for an async cleanup publisher |
| `doOnCancel` | Only need to react to cancellation | Does not replace cleanup on complete/error |
| `Flux.using` / `Mono.using` | Acquire and release have synchronous callbacks | Should not `.block()` async cleanup |
| `Flux.usingWhen` / `Mono.usingWhen` | Acquire/release via Publisher; async commit/rollback | Must account for cleanup errors, cancellation, and terminal delay |
| Reactive `@Transactional` / `TransactionalOperator` | Work participates in a Spring-managed transaction | Requires reactive transaction manager configuration and Reactor Context |
| `ConnectionFactoryUtils` | R2DBC integration needing to participate in Spring connection management | Must follow Spring/driver protocols |
| Dedicated Pool/SDK API | Driver already has a specialized lifecycle scope | Do not manually close framework-owned connections |

Not every temporary object needs `usingWhen`. Use it when you genuinely own a resource requiring release or a transaction requiring explicit cleanup.

## 17. Resource-Management API Design Checklist

Before writing production code:

1. **Who owns the resource?** The application, a pool, the Spring transaction manager, or an internal driver? Do not close resources managed by another scope.
2. **Is acquire blocking or reactive?** Blocking can use `using` plus an appropriate scheduler; reactive uses `usingWhen`.
3. **What does release return?** Synchronous `void`/`close()` or `Mono<Void>`/`Publisher<?>`? If async, avoid `.block()` or manual `.subscribe()`.
4. **Does each subscription get its own resource?** Avoid `Mono.just(precreatedHandle)` if the same handle cannot be shared.
5. **Are steps needing the open resource inside the closure?** Do not return cursors/LOBs/lazy views outside and release too early.
6. **Do complete/error/cancel behave identically?** For transactions, complete/commit usually differs from error/cancel/rollback.
7. **How will cleanup errors be handled?** Do not turn real failures into success; include logging/metrics and a recovery policy.
8. **Can it be cancelled/timed out?** Test disconnects, `take(n)`, timeouts, and cancellation during acquire/use.
9. **Does the resource have pool/quota limits?** Bound concurrency, queues, and timeouts at the client/driver; `usingWhen` does not create extra connections.
10. **Are there integration tests with the real driver?** Unit tests with mock resources verify lifecycle logic, but do not prove a real connection pool returns resources properly.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `try-with-resources` around a method returning a lazy `Flux` | Closes resource before the subscription uses it | Move acquire/use/cleanup into `using`/`usingWhen` |
| Creating a resource outside and reusing it for many subscribers | Later subscriptions use a closed handle | Create a new resource per subscription |
| Calling `.block()` in reactive cleanup | Blocks event loop, loses non-blocking | Return the cleanup publisher to `usingWhen` |
| Calling `closeAsync().subscribe()` and returning `Mono.empty()` | Operator does not wait for cleanup; errors may be lost | Return `closeAsync()` directly |
| Cleaning up only on `onComplete` | Resource leaks on error/cancel | Cover all three paths |
| Treating cancellation as transaction commit | Commits incomplete business writes | Design rollback on cancel per contract |
| Assuming `Mono.usingWhen` returns its value before cleanup | Misreads signals, misses that cleanup can turn success into error | Remember Mono holds its value until cleanup completes |
| Assuming `Flux.usingWhen` always holds all elements until after cleanup | Misunderstands streaming and side effects | Flux can emit `onNext` before cleanup runs |
| Swallowing cleanup errors with `onErrorComplete()` outside | Hides leaks/commit failures | Record and handle per error policy |
| Reading LOBs/cursors outside `resourceClosure` | Uses an already-closed resource | Complete resource-dependent processing inside closure |
| `Flux` `resourceSupplier` emitting multiple resources | Extra resources dropped, leak risk | Use a publisher supplying exactly one resource |
| Using `ThreadLocal` transactions in reactive flows | Loses context across scheduler hops | Use reactive transactions + Reactor Context |
| Assuming `dispose()` always waits for async cleanup to finish | Flaky tests, missed cleanup | Observe cleanup publisher/latch/metrics |
| Calling `connection.close()` manually while Spring manages the transaction | Breaks transaction/pool scope | Use `DatabaseClient`/`ConnectionFactoryUtils` properly |

## 19. Self-Check Exercises

**Exercise 1.** Why can the following snippet be wrong?

```java
try (FileHandle file = openFile()) {
    return file.toFlux();
}
```

**Answer:** If `toFlux()` is a lazy publisher, `try-with-resources` closes the file before the subscriber begins reading. Use `Flux.using` to open the file on subscribe and close on termination/cancel, or use a file publisher API that manages its own lifecycle.

**Exercise 2.** What is the most important difference between `Mono.using` and `Mono.usingWhen`?

**Answer:** `using` takes a synchronous resource and runs synchronous cleanup; `usingWhen` takes a resource-supplying publisher and waits for a cleanup publisher. With `Mono.usingWhen`, the success value is held until cleanup finishes.

**Exercise 3.** `Flux.usingWhen` already emitted `A`, `B` and then cleanup fails. What may downstream have received?

**Answer:** It may already have received `A`, `B` and then receive `onError(cleanupFailure)` instead of `onComplete`; already-observed elements are not retracted.

**Exercise 4.** A stream is cancelled upstream by `take(1)` after the first element. With the 5-parameter overload of `usingWhen`, which cleanup should run?

**Answer:** Normally **`asyncCancel`**, not the `asyncComplete` branch of the resource closure. Test the exact `take`/cancel boundary.

**Exercise 5.** A transaction is managed by Spring R2DBC. Should you call `factory.create()` and `close()` directly in the middle of the transaction?

**Answer:** By default, no. A manually created connection may not belong to the active transaction; use `DatabaseClient`, `R2dbcEntityTemplate`, `ConnectionFactoryUtils`, or `TransactionalOperator` per the transaction design.

**Exercise 6.** `asyncComplete` returns `Mono.delay(Duration.ofSeconds(5)).then()`; `Mono.usingWhen` has value `"OK"`. When does the subscriber receive `"OK"`?

**Answer:** After the cleanup publisher finishes, roughly 5 seconds according to the scheduler if there is no error or cancellation; before then, `onNext("OK")` is not yet received.

**Exercise 7.** If acquire completes empty, does `usingWhen` call close?

**Answer:** There is no acquired resource to close; the main publisher completes empty and the resource-handling callbacks are not invoked.

**Exercise 8.** Why does the following code not guarantee `close` occurs?

```java
resource -> flush(resource).then(close(resource))
```

**Answer:** If `flush` emits `onError`, the `.then` operator does not subscribe to `close`. Design cleanup to guarantee `close` even when `flush` fails, with a mechanism preserving both errors.

## 20. Summary

`using` and `usingWhen` create explicit **resource-ownership boundaries** in reactive programming:

- **`using`** is for synchronous acquire/release. The `eager` flag adjusts cleanup ordering relative to downstream signals; for a valued `Mono`, eager cleanup succeeds before emitting `onNext`.
- **`usingWhen`** is for Publisher-based acquire/release, optionally separating **complete, error, and cancel**. For `Mono`, cleanup finishes before downstream receives the value; for `Flux`, streamed elements can arrive before cleanup, while the terminal waits for cleanup.
- **Do not forget cancel**: client disconnects, timeouts, and operators like `take(n)` can cancel the source even when business code has not finished.
- **Do not lose cleanup errors**: if close/commit/rollback fails, that is an observable error, not success.
- **Prefer framework resource management when available**: use Spring reactive transactions / `DatabaseClient` / `ConnectionFactoryUtils` instead of reimplementing connection management.

Look at **who owns the resource, who subscribes to cleanup, and when the terminal is emitted**. Those three questions help prevent most resource leaks and transaction bugs in Spring WebFlux.

## Official Documentation

- Project Reactor Core 3.6.6, **`Mono` API – `using` and `usingWhen`**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html
- Project Reactor Core 3.6.6, **`Flux` API – `using` and `usingWhen`**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Resource handling in operator choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework, **R2DBC data access**: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Framework, **Programmatic transaction management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html