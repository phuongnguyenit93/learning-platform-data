# Cancellation Does Not Mean Stopping External Work Immediately

> **Module:** Spring Framework – reactive · **Parent topic:** Cancellation and resources. This lesson presents the `cancel()` signal in Reactive Streams, the limits of cancelling a Publisher, and why external work (HTTP requests, databases, executors, queues, job servers, payment gateways) can still complete. Includes runnable Java 17+, Reactor tests, Spring WebFlux examples, and a deployment checklist.

## 1. Understanding the Problem Properly

After this lesson you can:
1. Explain `Subscription.cancel()`, `Disposable.dispose()`, and distinguish cancellation from `onComplete`/`onError`.
2. Recognize where cancellation originates via `take`, `timeout`, `switchMap`, racing operators, subscriber disposal, and client disconnects.
3. Distinguish three layers: **stopping delivery of results downstream**, **signaling the upstream source to stop producing data**, and **actually stopping/undoing external work**.
4. Use `doOnCancel`, `doFinally`, `MonoSink/FluxSink.onCancel/onDispose`, `using`, and `usingWhen` to manage resources with the proper lifecycle.
5. Test cancellation, cleanup, late callbacks, and independent tasks that still complete without relying on vague timing assumptions.
6. Design idempotency, status lookup, deadlines, retries, and business cancellation when database transactions or remote write commands are involved.
7. Apply these concepts in Spring WebFlux when users close tabs, SSE disconnects, or HTTP requests time out.

**Most important principle:** `cancel()` is a **request to stop a subscription**, not a command to undo all side effects that have already begun. Only when the source/driver/remote system supports an appropriate cancellation mechanism can part of the work stop, and even when supported, **you cannot assume that all work stops immediately**.

## 2. Which Direction Does the Cancellation Signal Travel?

Under the Reactive Streams model, a Subscriber subscribes to a Publisher, receives a `Subscription`, uses `request(n)` to signal demand, and calls `cancel()` when it no longer needs data. The Publisher delivers `onNext`, `onError`, or `onComplete` to the Subscriber. Cancellation is a control signal **traveling upstream**, distinct from terminal signals **traveling downstream**.

~~~text
Data and results:
Publisher / upstream ── onNext, onError, onComplete ──> Subscriber / downstream

Control:
Subscriber ── request(n), cancel() ──> operators ──> Source subscription

What can happen:
client cancel → Reactor cancels upstream → HTTP client attempts to disconnect
                                         |
                                         +→ remote server has still received the request
                                         +→ DB has committed or is committing
                                         +→ external thread is still running
                                         +→ cleanup may continue asynchronously
~~~

`Mono<T>` holds 0 or 1 value; `Flux<T>` holds 0 to many values. **onComplete** is a successful termination; **onError** is an error; while **cancel** expresses that the consumer no longer wants to wait. Do not write an API expecting `onComplete` after cancellation as proof of successful cancellation. In particular, `doOnComplete` does not replace `doOnCancel` or resource cleanup triggered across all termination paths.

Races can happen: a callback or signal may already be queued when `cancel()` occurs. After cancellation, Reactor may drop late signals or record dropped signals depending on the operator/hook. Do not use the log ordering of two threads to conclude for certain that “the source has not executed yet”.

### 2.1. `dispose()` Is Local Subscription Cancellation

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
Disposable subscription = ticks.subscribe(System.out::println);

// When you no longer want to keep receiving ticks:
subscription.dispose();
~~~

This is a fragment requiring imports for `Flux`, `Disposable`, and `Duration`. `subscribe()` returns a `Disposable` representing the subscription, and calling `dispose()` corresponds to a cancellation request. It does not return proof that a remote server has stopped. The example uses a manually managed subscriber in a CLI app; **in a Spring WebFlux controller, typically return a Mono/Flux to the framework instead of subscribing manually**. If a controller both subscribes to trigger side effects and returns another Publisher, the work can lose its binding to the HTTP lifecycle, errors get ignored, and retries can create duplicates.

### 2.2. Three Layers of Cancellation

| Layer | What cancel can do | What cannot be assumed automatically |
| --- | --- | --- |
| Downstream | Stop waiting for/receiving further data from the cancelled subscription | Does not prove every callback has finished running. |
| Upstream/reactive client | Forward request to stop source; cancel timers, free queues, close or abort requests if the driver supports it | Does not guarantee a blocking call or already-sent I/O stops immediately. |
| External side effects | API may support request cancellation, rolling back uncommitted transactions, unregistering listeners | Cannot automatically undo a commit, payment, email, or completed job. |

**Example:** a browser sends a POST, and the server calls a payment system. The browser times out and closes the connection at second two; the gateway may commit the charge at second three. If the user retries the POST with a new id, there is a risk of double charging. This is a problem of **idempotency and verifying transaction status**, which cannot be solved by Reactor cancel alone.

## 3. Which Operators Can Trigger Cancellation?

| Source of cancellation | Why it happens | Notes on external work |
| --- | --- | --- |
| `take(n)` | Received `n` elements | Downstream may complete; upstream is cancelled to stop emitting the rest. |
| `Flux.next()` | Takes only the first element | Does not wait for the entire Flux to finish. |
| `timeout(Duration)` | Wait budget expired | May cancel upstream even while remote is still processing. |
| `switchMap` | A new inner Publisher replaces the old inner | Cancelling the old inner does not guarantee the old request hasn't executed. |
| `firstWithSignal` / `firstWithValue` | A winner is selected, already-subscribed losers may be cancelled | Both systems may have already received requests. |
| `flatMap` terminating with error | Other inners may be cancelled per error policy | Inner side effects already started are not necessarily undone. |
| `Disposable.dispose()` | Subscriber stops caring on its own | Only cancels the held subscription. |
| Client disconnect in WebFlux | Framework may abort the response Publisher | Whether remote stops depends on connector, proxy, timing. |

Do not assert that all cases above produce strictly one `doOnCancel` callback for every source under every race or optimization. Observe operator placement, subscription state, and how well the source honors cancellation.

### 3.1. `take(1)`: Complete Below, Cancel Above

~~~java
Flux<Integer> stream = Flux.range(1, 100)
    .doFinally(type -> System.out.println("upstream: " + type))
    .take(1)
    .doFinally(type -> System.out.println("downstream: " + type));
~~~

This fragment illustrates the difference in termination paths: downstream after `take(1)` can see **ON_COMPLETE** because enough elements were obtained, while the upstream source can receive **CANCEL** because the remaining 99 elements are no longer needed. **Do not rely on the exact order of `doFinally` log lines** for business synchronization. `doFinally` runs after the terminal signal has been forwarded downstream and may execute on another thread.

### 3.2. Timeout Is Not Rollback

~~~java
Mono<Response> result = remoteWrite()
    .timeout(Duration.ofSeconds(2));
~~~

This is a fragment with an application-defined `remoteWrite()`. After 2 seconds, downstream receives a timeout error and Reactor cancels upstream. If the external party already received the write command, it can still commit afterward. When a POST times out, **do not automatically retry without limits** or send a new command with a different key; first know the idempotency protocol and remote state.

## 4. A Cancel Signal Is Not Successful Completion

### 4.1. `doOnCancel`

~~~java
Mono<String> result = callRemote()
    .doOnCancel(() -> metrics.incrementCancellation());
~~~

`doOnCancel` is a **cancel-only** hook. Per Javadoc, the hook runs before the cancel signal is propagated upstream of that operator. It can record a metric or request a resource to stop; however, saying “the hook ran” **does not mean** the remote task stopped. The callback should be fast, idempotent, thread-safe, and avoid blocking or launching a Mono and leaving it unmanaged.

### 4.2. `doFinally` and `SignalType`

~~~java
Flux<String> events = eventSource()
    .doFinally(type -> {
        if (type == SignalType.CANCEL) {
            metrics.cancelled();
        } else if (type == SignalType.ON_ERROR) {
            metrics.failed();
        } else if (type == SignalType.ON_COMPLETE) {
            metrics.completed();
        }
    });
~~~

This fragment assumes `eventSource()` and `metrics` exist. `doFinally` is well suited to recording metrics for **every** termination (completion, error, cancellation). For complete/error, the callback executes **after the terminal signal has been passed downstream**. If tests need to assert side effects inside `doFinally`, design proper synchronization; do not automatically assume that as soon as `block()` returns, all hooks have finished.

**Comparison:**
- `Flux`'s `doOnComplete` is only for successful completion, not full cleanup on error/cancel.
- `doOnError` is only for errors.
- `doOnCancel` is only for cancellation.
- `doFinally` covers complete/error/cancel, suitable for counting and observation.
- `doOnDiscard` is for certain operators that drop elements from queues/buffers; discard hooks should be idempotent and do not mean the external task was cancelled.
- `MonoSink.onCancel`/`FluxSink.onCancel` is suitable for integrating the cancellation handle of an external SDK.
- A sink's `onDispose` covers both cancel and terminal signals to close resources.

If cleanup must run asynchronously, for example `connection.close()` returning a Publisher, calling `connection.close()` inside `doFinally` and ignoring the Publisher will **not guarantee cleanup runs**. Use `usingWhen` or a resource manager with an explicit lifecycle instead of unmanaged `.subscribe()` in a callback.

## 5. Callback SDKs: Attaching Resources to MonoSink/FluxSink

Many legacy SDKs return results via a callback and a handle to cancel/unregister. Reactor provides `Mono.create`/`Flux.create` to bridge those APIs into a pipeline.

### 5.1. Single Callback Returning One Result

~~~java
Mono<Result> result = Mono.create(sink -> {
    CancelHandle handle = client.fetchAsync(
        value -> sink.success(value),
        error -> sink.error(error)
    );

    sink.onCancel(handle::cancel);
    sink.onDispose(handle::close);
});
~~~

**This is a fragment**; `Result`, `CancelHandle`, `client`, and the corresponding methods are application-defined. `onCancel` forwards the cancellation request to the handle; `onDispose` cleans up resources on completion, error, or cancellation. Ensure `cancel`/`close` are idempotent and tolerant of races where a callback arrives right at cancellation time. **Each callback type on a sink should only be registered once**; if there are multiple resources, combine cleanup in order.

**Important:** `handle.cancel()` might only cancel waiting for the callback, might close the connection, or might not actually prevent the server from processing. You must read the library's contract and test with a mock server or integration tests.

### 5.2. Multi-Event Sources: Unregistering Listeners

~~~java
Flux<Event> events = Flux.create(sink -> {
    ListenerHandle registration = externalClient.register(
        event -> sink.next(event),
        error -> sink.error(error)
    );

    sink.onDispose(registration::unregister);
}, FluxSink.OverflowStrategy.ERROR);
~~~

This is also a fragment, requiring types `Event`, `ListenerHandle`, and `externalClient`. Upon complete/error/cancel, the callback registration is removed. **A callback already in the SDK's queue may still run** after unregistering; therefore handle concurrency and make cleanup idempotent. `OverflowStrategy.ERROR` represents one policy when upstream does not respect backpressure; it is not a mandatory choice for every event source. For hot sources with slow subscribers, choose an appropriate bounded buffer/drop/latest/broker policy and avoid unbounded buffers.

### 5.3. `sink.success` After Cancel

If an external callback calls `sink.success("done")` after downstream cancels, the result will not necessarily be delivered to the cancelled subscriber; Reactor may discard late signals. However, the external callback **already ran** and the external task may have already committed. Thus, do not use “no onNext observed” as proof of “no transaction occurred”.

## 6. Runnable Java 17+: Subscription Cancelled While External Job Still Finishes

This example uses an `ExecutorService` to simulate an **independent remote job**. A `CountDownLatch` holds the worker until `Disposable.dispose()` has been called, so the result does not depend on random timing between two threads. **We intentionally do not wire cancel to the external task**, in order to observe the limits of Reactor cancellation.

### 6.1. Project Structure

~~~text
reactor-cancellation/
├── pom.xml
├── src/main/java/com/example/cancel/CancellationDemo.java
└── src/test/java/com/example/cancel/CancellationTest.java
~~~

**pom.xml** — Java 17, Reactor Core 3.8.8, Reactor Test, and JUnit Jupiter:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-cancellation</artifactId>
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

### 6.2. `CancellationDemo.java`

**src/main/java/com/example/cancel/CancellationDemo.java**

~~~java
package com.example.cancel;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.Disposable;
import reactor.core.publisher.Mono;

public final class CancellationDemo {
    private CancellationDemo() {}

    public static void main(String[] args) throws Exception {
        ExecutorService remoteJob = Executors.newSingleThreadExecutor();
        CountDownLatch releaseJob = new CountDownLatch(1);
        CountDownLatch finishedJob = new CountDownLatch(1);

        AtomicInteger started = new AtomicInteger();
        AtomicInteger cancelHooks = new AtomicInteger();
        AtomicInteger remoteCompleted = new AtomicInteger();
        AtomicInteger delivered = new AtomicInteger();

        try {
            Mono<String> operation = Mono.create(sink -> {
                started.incrementAndGet();

                // External work runs independently of the Subscription.
                remoteJob.execute(() -> {
                    try {
                        releaseJob.await();
                        remoteCompleted.incrementAndGet();
                        sink.success("done");
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        sink.error(ex);
                    } finally {
                        finishedJob.countDown();
                    }
                });

                sink.onCancel(() -> cancelHooks.incrementAndGet());
            });

            Disposable subscription = operation.subscribe(
                value -> delivered.incrementAndGet());

            // Cancel first, then allow the external job to finish.
            subscription.dispose();
            releaseJob.countDown();

            if (!finishedJob.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("job did not finish");
            }

            System.out.println("started=" + started.get());
            System.out.println("cancelHooks=" + cancelHooks.get());
            System.out.println("remoteCompleted=" + remoteCompleted.get());
            System.out.println("delivered=" + delivered.get());
        } finally {
            releaseJob.countDown();
            remoteJob.shutdownNow();
        }
    }
}
~~~

**Explanation:** `Mono.create` runs its callback upon subscription, increments `started`, and schedules a separate worker. `Disposable.dispose()` cancels the subscription and triggers `sink.onCancel`; only then does the latch let the worker proceed. The worker still increments `remoteCompleted` and calls `sink.success`, but the subscriber has already cancelled so it does not receive the result. Calling `remoteJob.shutdownNow()` in `finally` is only cleanup for the CLI example, and does not prove subscription cancellation can stop an external job.

### 6.3. Run Commands

In the project directory:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.cancel.CancellationDemo
~~~

**Stdout from the `System.out.println` lines in `main`**:

~~~text
started=1
cancelHooks=1
remoteCompleted=1
delivered=0
~~~

The code uses latches to guarantee ordering, rather than relying on `Thread.sleep` or hoping a scheduler runs within exact milliseconds. **The result clearly proves:** not delivering a result to the subscriber is different from the external work having ended. In a WebFlux application, do not create a separate executor per request; you need a bounded resource manager/job service and durable state.

## 7. What If the External API Supports Cancel?

When an SDK returns a cancellation handle, `Future`, `ScheduledFuture`, or `AutoCloseable`, bind it to the subscription. This example illustrates a timer whose scheduled task **can be prevented if it has not run yet**:

~~~java
Mono<String> timerResult = Mono.create(sink -> {
    ScheduledFuture<?> future = timer.schedule(
        () -> sink.success("ready"),
        10, TimeUnit.SECONDS
    );
    sink.onCancel(() -> future.cancel(false));
});
~~~

This is a fragment requiring a `ScheduledExecutorService timer` and imports. `cancel(false)` attempts to cancel work **not yet started** and does not interrupt running work. `cancel(true)` can send an interrupt request to the thread, but **there is no guarantee the task will stop immediately**: code may ignore interrupts, be stuck in a non-interruptible API, or the operation may have already been sent to another machine.

**Cooperative cancellation:** if you own the long-running task code, pass a cancellation flag/token and check it at safe points, while closing resources in `finally`. The token must be scoped to the subscription/job, not a global flag where cancelling request A stops request B.

~~~java
AtomicBoolean stop = new AtomicBoolean();

Mono<Result> computation = Mono.fromCallable(() -> {
    for (int i = 0; i < 100; i++) {
        if (stop.get() || Thread.currentThread().isInterrupted()) {
            throw new CancellationException("stopped cooperatively");
        }
        processChunk(i);
    }
    return assembleResult();
})
.subscribeOn(Schedulers.boundedElastic())
.doOnCancel(() -> stop.set(true));
~~~

**Fragment**, requiring `Result`, the business methods, and Java/Reactor imports. The goal is for code to *cooperate* by checking flags/interrupts; it does not prove an external system rolled back. For blocking sources, `boundedElastic` helps avoid holding the event-loop, yet still has thread/queue limits and does not turn blocking I/O into non-blocking.

## 8. Resource Management: `using` and `usingWhen`

### 8.1. Synchronous Cleanup with `Flux.using`

~~~java
Flux<Integer> values = Flux.using(
    () -> openHandle(),
    handle -> readValues(handle),
    handle -> handle.close()
);
~~~

This fragment assumes `openHandle()` returns a resource with a `close()` that does not throw checked exceptions, and `readValues` returns a Publisher. `using` creates the resource **per subscription**, scopes its usage, and cleans up on complete/error/cancel. Unlike `try-with-resources` around the call that **creates** the Mono: if you close the resource right when the method returns, the Mono may not have been subscribed to yet and later reads will use a closed resource.

If `close()` throws checked exceptions, handle them inside the cleanup callback per the system's contract. Synchronous cleanup can also block: avoid placing slow I/O closing onto the event-loop.

### 8.2. Asynchronous Cleanup with `usingWhen`

~~~java
Mono<Result> result = Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> doQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

**Fragment** for an R2DBC-like driver: `connectionFactory.create()` and `connection.close()` return Publishers, and `doQuery(connection)` returns `Mono<Result>`. `usingWhen` binds the resource to the processing chain and **separate cleanup Publishers** for complete, error, or cancel. In production, the error/cancel branches might need to roll back an uncommitted transaction before closing; the example only closes because transaction details cannot be assumed.

**Important point:** asynchronous cleanup on cancel may still run after the subscriber stops waiting; metrics/logs are needed for cleanup failures. `usingWhen` helps manage resource lifecycles, but **it is not a distributed transaction**: once a commit has completed, there is no magical rollback. If business guarantees across multiple services are required, use durable state, idempotency, outbox, inbox/dedup, or compensation.

### 8.3. Choosing the Right Mechanism

| Mechanism | Suitable for | Limitations |
| --- | --- | --- |
| `doOnCancel` | Recording cancel metrics, triggering cancellation handles | Hook execution does not prove external work stopped. |
| `doFinally` | Classifying complete/error/cancel, telemetry | Does not run a cleanup Publisher automatically if you only instantiate it. |
| `MonoSink/FluxSink.onCancel` | Linking a `CancelHandle` from a callback API | Cancellation effectiveness depends on the external API. |
| `MonoSink/FluxSink.onDispose` | Unregistering/closing resources on any termination | An in-flight callback may still run. |
| `Flux.using` / `Mono.using` | Resources with synchronous cleanup | Does not solve asynchronous I/O cleanup on its own. |
| `Flux.usingWhen` / `Mono.usingWhen` | Resources with asynchronous cleanup including cancel | Cannot undo an external commit that already occurred. |
| Business cancellation API | Cancelling jobs and receiving verified status | Requires protocol, persistent state, and race checks. |

## 9. Testing Cancellation Behavior with Reactor Test

`StepVerifier` helps verify whether Reactor forwards cancel and runs cleanup at the right boundaries. These tests **do not replace integration tests against a remote server** when you want to know whether external work actually stopped.

**src/test/java/com/example/cancel/CancellationTest.java**

~~~java
package com.example.cancel;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CancellationTest {

    @Test
    void cancelIsDifferentFromCompletion() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.create(
                Flux.<Long>never().doFinally(type -> {
                    if (type == SignalType.CANCEL) {
                        cancelled.set(true);
                    }
                }))
            .expectSubscription()
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void takeOneReleasesUsingResource() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> source = Flux.using(
            () -> "handle",
            handle -> Flux.concat(
                Flux.just(1), Flux.<Integer>never()),
            handle -> closed.incrementAndGet()
        );

        StepVerifier.create(source.take(1))
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, closed.get());
    }

    @Test
    void timeoutCancelsUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofHours(2))
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofHours(1)))
            .expectSubscription()
            .thenAwait(Duration.ofHours(1))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void cancelDoesNotInvokeOnComplete() {
        AtomicInteger cancels = new AtomicInteger();
        AtomicInteger completions = new AtomicInteger();

        Flux<Integer> never = Flux.<Integer>never()
            .doOnCancel(cancels::incrementAndGet)
            .doOnComplete(completions::incrementAndGet);

        StepVerifier.create(never)
            .expectSubscription()
            .thenCancel()
            .verify();

        assertEquals(1, cancels.get());
        assertEquals(0, completions.get());
    }
}
~~~

**Test explanation:**
- Test 1 verifies `SignalType.CANCEL` is observed when the subscriber itself cancels.
- Test 2 verifies `Flux.using` closes the resource when `take(1)` stops the rest even though downstream completed.
- Test 3 uses **virtual time**, creating `Mono.delay` **inside the `withVirtualTime` supplier**, cancelling upstream after one virtual hour instead of waiting in real time.
- Test 4 proves cancel does not invoke `doOnComplete`.

If you must test **asynchronous** cleanup of `usingWhen`, wait on the cleanup Publisher or use a controlled latch rather than asserting immediately after cancel and hitting flaky timing. For real HTTP tests, use a mock server with a barrier confirming the **request was received** before you cancel so you can verify outcomes more accurately than with `Thread.sleep`.

## 10. Spring WebFlux Integration When a Client Disconnects

In WebFlux, controllers **return a Mono/Flux** so the framework manages the subscription and writes the HTTP response. When the client leaves or the network drops, the framework/connector **may** forward cancellation to the response Publisher. What happens at a remote endpoint depends on the network, HTTP client, driver, and whether the request had already reached the server.

**Controller fragment** (requires Spring Boot WebFlux, a `JobStatusService` bean, and DTO `JobStatus`):

~~~java
package com.example.web;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@RestController
@RequestMapping("/api/jobs")
public class JobStatusController {
    private final JobStatusService jobs;

    public JobStatusController(JobStatusService jobs) {
        this.jobs = jobs;
    }

    @GetMapping("/{id}/status")
    public Mono<JobStatus> status(@PathVariable String id) {
        return jobs.readStatus(id)
            .timeout(Duration.ofSeconds(2))
            .doFinally(type -> {
                if (type == SignalType.CANCEL) {
                    jobs.recordSubscriberCancellation(id);
                }
            });
    }
}
~~~

`recordSubscriberCancellation` here should be fast metric recording, non-blocking, and independent of whether the client is still connected. If you must write to a DB asynchronously, use a telemetry/job mechanism with its own lifecycle instead of calling `.subscribe()` casually inside a callback. The CANCEL hook **only speaks about the subscription to the response status**; it does not mean the job was cancelled.

### 10.1. Distinguish Between Discardable Tasks and Work That Must Continue

- **Temporary GET/search/SSE/streams:** when the reader leaves, it is usually good to cancel queries/timers/listeners to save resources, set timeouts, and release connections. Test how well the driver supports cancellation.
- **Received business commands:** creating invoices, payments, issuing vouchers, sending notifications, or running background reports. A user closing a tab does not mean the business action may stop arbitrarily; the task may need to finish or record its outcome for lookup.

For long jobs, design an API that **submits → stores job in storage/queue → returns 202 Accepted + jobId → GET status**. If job cancellation is supported, add a cancellation-request endpoint and return states **cancellation requested** and then **cancelled/finished/failed** after worker confirmation. Do not treat closing an HTTP connection as a business cancellation API. Return 202 only after the job has been durably recorded, not merely after creating a Publisher and leaving it hanging.

### 10.2. Retrying After Timeout Requires Idempotency

~~~text
POST /payments with Idempotency-Key = k
   |
   v
Backend → Payment gateway
   |
   +-- Client timeout / closes connection
   |
   +-- Gateway still commits the charge successfully
           |
           +-- Client retries POST with the same k
                   |
                   +-- Return recorded outcome, do not charge a second time
~~~

For correctness, the system must store the result/idempotency key or query the transaction ID with the gateway. `timeout`, `cancel`, `doFinally`, or `onErrorResume` **do not guarantee exactly-once**. If you do not know whether the remote committed, do not assume the request failed; a “verifying” status and a reconciliation workflow may be needed.

## 11. Transactions, Rollback, and External Tasks

With a reactive database, a transaction may support rollback when the chain fails or is cancelled **before commit** depending on the transaction manager and driver; however, actual timing and behavior must be verified:
1. Command **not yet sent**: cancel can prevent execution.
2. Command sent and processing: the driver/backend may accept the cancel request, or may have already executed an irreversible step.
3. Transaction **already committed**: a late cancel cannot roll it back automatically.
4. External service **already received the command**: rolling back the local DB does not undo emails, charges, or published messages in other systems.

Use `ReactiveTransactionManager`/`TransactionalOperator` or the appropriate R2DBC transaction API when needed, and design clear transaction boundaries. Do not mix blocking JDBC and R2DBC and assume they share one atomic reactive transaction. For cross-service side effects, use outbox, inbox/deduplication, idempotent consumers, saga/compensation, or durable state depending on the domain.

**Note on cancellation tokens:** if a CPU or blocking task is owned by you, you can check a cancellation flag/interrupt at safe points. However, a JVM flag cannot stop a remote server without a protocol to transmit the cancellation request. With `Future.cancel(true)`, interruption is only a **request** and the code must cooperate to stop; with `cancel(false)`, already-started work can keep running.

## 12. Scenarios and How to Handle Them

### 12.1. Client Closes SSE

A `Flux.interval` emits SSE events continuously. The client closes the connection, the Publisher is cancelled, and the source timer can be stopped. If the SSE connects to a broker with an external registration, `onDispose`/`usingWhen` is needed to unsubscribe and release resources. **An event already queued before cancel can still run** on the producer thread; callbacks must check lifecycle state and support idempotent cleanup.

### 12.2. WebClient Call Times Out

A WebClient calls an auxiliary API, and `.timeout(2s)` emits an error. The local HTTP request may be cancelled/connection closed depending on the connector; however, the auxiliary server **may continue processing**. For read/idempotent GETs, bounded retries are sometimes acceptable; for write POSTs, idempotency is required. Measure `clientCancelled`, `remoteCompleted`, and `remoteFailed` wherever measurable rather than lumping them all into “failed”.

### 12.3. `firstWithValue` Races Two Replicas

Two sources are subscribed simultaneously; one emits data first as the winner, and the loser is cancelled. The request to the loser may **already have left the machine**; racing fits read/idempotent operations, not two money-transfer commands. If you need data from both, choose `zip`/`merge` instead of racing.

### 12.4. Large File Processing Job

A file-processing task using a blocking SDK can run on `boundedElastic`. When the client cancels, a cancellation token should be passed into the processing loop and checked between chunks; clean up temporary files and streams in `finally` or a resource manager. If the SDK does not support interruption, it may continue until finishing on its own. Use concurrency and queue limits; `boundedElastic` does not make blocking I/O non-blocking.

### 12.5. User Clicks “Cancel job”

This is a business action **with its own state**, distinct from closing a connection. The system must record the cancellation request, forward it to the worker/job service, check whether it has started/committed, and confirm `cancelled`, `tooLate`, `finished`, or `failed` per domain rules. You cannot promise “cancelled” before the worker reports having stopped at a safe point.

## 13. Common Mistakes

| Misunderstanding / implementation mistake | Consequence | Remedy |
| --- | --- | --- |
| Treating `dispose()` like a DB rollback | DB/remote can still commit | Distinguish Subscription from transaction outcome. |
| Assuming `doOnCancel` running means the server stopped | Only proves the hook fired | Test SDK cancellation and server state. |
| Retrying POST after timeout without idempotency | Data/charge can be duplicated | Idempotency key, status lookup, dedup. |
| Closing resources only in `doOnComplete` | Leaks on error/cancel | `using`, `usingWhen`, `onDispose`, or cleanup for all branches. |
| Calling `.subscribe()` to run async cleanup right inside a hook | Errors and lifecycle are hard to observe | `usingWhen` or a dedicated resource manager. |
| Using `Future.cancel(true)` as a guaranteed kill command | Task ignores interrupt and continues | Cooperative cancellation, deadlines, empirical testing. |
| Believing no `onNext` seen means remote hasn't run | Misinterpreting business state | Measure remote state, transaction IDs. |
| Labeling `onComplete` as “cancel” | Wrong completion/cancel metrics | Use `doFinally` and `SignalType`. |
| Creating a worker/executor per HTTP request | Thread, queue, and heap exhaustion | Bounded pools, job service, backpressure. |
| `Flux.create` emitting too fast without listener cleanup | Growing RAM and dangling callbacks | Backpressure strategy, `onDispose`. |
| Closing HTTP and assuming background job was cancelled | Unconfirmed behavior | Separate job-cancellation request API and state. |
| Sharing a cancellation token across multiple subscribers | One cancel affects another request | Scope token per subscription/job. |

## 14. Pre-Production Checklist

- [ ] Know who owns the **subscription, remote operation, and resources** at each layer.
- [ ] Do not treat `cancel` as `onComplete`, `onError`, transaction rollback, or business cancellation.
- [ ] Verify `onCancel`/`onDispose` and cleanup on complete/error/cancel with explicit tests.
- [ ] For external SDKs, provide a cancellation handle or document limits when unsupported.
- [ ] For callback/hot sources, ensure idempotent unsubscription and a backpressure policy.
- [ ] Async resources use `usingWhen`/resource managers; cleanup errors are monitored.
- [ ] Remote data writes have idempotency keys, transaction IDs, status lookup, or dedup.
- [ ] Client disconnects and retries are tested **before/after remote receive** and **before/after commit**.
- [ ] Timeouts and deadlines exist at each hop, and timeouts are never used as proof of rollback.
- [ ] Do not block the Reactor Netty event-loop; `boundedElastic` is load-bounded and monitored.
- [ ] Track metrics for `cancelled`, `timedOut`, `completed`, external job results, cleanup failures, and leaks.
- [ ] If the product requires real job cancellation, provide a dedicated API and verified states: requested, cancelled, too late, finished.

## 15. References

1. Reactor Core 3.8.8 — `Mono`, `doOnCancel`, `doFinally`, `usingWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
2. Reactor Core 3.8.8 — `Flux`, `using`, `usingWhen`, `doOnDiscard`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor `MonoSink` — `onCancel`, `onDispose`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/MonoSink.html
4. Reactor `FluxSink` — lifecycle and callbacks: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.html
5. Reactor Test — `StepVerifier`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
6. Reactive Streams Specification: https://www.reactive-streams.org/
7. Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
8. Spring Data R2DBC: https://docs.spring.io/spring-data/relational/reference/r2dbc.html

**Self-check:** If a client placing an order times out after the server sends a payment command and `doFinally(CANCEL)` runs, can you assert that money was not charged? **No.** You only know the local subscription is no longer waiting. You must check the gateway outcome, idempotency key, transaction status, and a confirmed business cancellation mechanism. That is the decisive difference when building safe reactive systems.
