# Converting CompletableFuture to Mono and Examining Launch Timing

## 1. Why Distinguish CompletableFuture Creation Time from Mono Subscription Time?

In a Spring WebFlux application, you may need to integrate a Java library returning **CompletableFuture<T>**: an asynchronous HTTP client, cloud SDK, external service query API, or background task. Meanwhile, WebFlux services and controllers normally return **Mono<T>** to continue using Reactor operators and let the framework manage the request lifecycle.

Reactor provides **Mono.fromFuture(...)** to convert a CompletableFuture's completion signal into a Mono: completing successfully with a value causes the Mono to emit at most one element; completing with no value (null) causes the Mono to complete empty; completing with an error causes the Mono to emit onError.

The hardest question is not the conversion syntax, but **when the asynchronous task is actually launched**.

- **CompletableFuture represents work/a result that may already have been launched.** If you call an asynchronous API or CompletableFuture.supplyAsync(...) when declaring the variable, the work has usually already been submitted, even if nobody has subscribed to the Mono yet.
- **Mono describes a Publisher with a subscription lifecycle.** In many Reactor pipelines, computation is triggered upon subscribe. However, a Mono created from **an already-existing Future** cannot turn back time to delay a task that has already started.
- **Mono.fromFuture(Supplier)** lets you defer **calling the function that creates the CompletableFuture** until subscription time. If the Supplier returns a new Future each time, each subscription creates a new task; if the Supplier just returns an already-existing Future, that task is still shared.

Therefore, **Mono's laziness** and **the laziness of the work inside CompletableFuture** are two properties that must be examined separately. Seeing only the Mono return type is not enough to confirm that a network request or task has been deferred.

## 2. CompletableFuture and Mono: Two Different Contracts

| Aspect | CompletableFuture<T> | Mono<T> |
| --- | --- | --- |
| What it represents | A result completing in the future: success, error, or cancellation. | A Publisher emitting at most one value then completing or erroring. |
| Starting work | Determined by the API creating the Future; many APIs start immediately when called. | Determined by the Publisher source/operator; with Supplier it can be deferred until subscribe. |
| Receiver | Registers callbacks like thenApply, thenCompose, whenComplete. | Subscriber receives onNext, onComplete, or onError; has Subscription and demand. |
| Subscribing multiple times | Multiple callbacks can observe **the same** Future. | Multiple subscriptions can re-trigger the source **if** Mono creates a new source each time. |
| Null values | CompletableFuture can complete successfully with null. | Reactive Streams does not emit onNext(null); Mono.fromFuture turns that case into empty completion. |
| Cancellation | CompletableFuture.cancel(...) has cancellation semantics at the Future; does not guarantee the background task is physically stopped. | Subscription cancellation can be forwarded to the Future depending on the fromFuture option. |
| Errors | CompleteExceptionally or failed callback result. | Errors become onError signals in the pipeline. |

A pipeline like **map**, **flatMap**, **timeout**, **onErrorResume** can be placed after Mono.fromFuture to process results according to Reactor rules. However, you should not conclude that all APIs using CompletableFuture are non-blocking: for instance, a function that uses Thread.sleep, blocking JDBC, or heavy CPU work inside an Executor can still occupy threads.

## 3. Three Common Conversion Approaches and Launch Differences

### 3.1. Passing an Existing CompletableFuture: Work May Have Already Started

Suppose **client.fetchAsync(id)** calls an API and immediately starts asynchronous processing when the method is invoked:

~~~java
CompletableFuture<User> future = client.fetchAsync(id); // Calls the API right here
Mono<User> mono = Mono.fromFuture(future);               // Wraps the existing Future

// Only when subscribed does Reactor observe/push signals to the Subscriber.
~~~

The line calling the client runs **before** the Mono is created. If the API truly starts I/O immediately on call, the request may already be running or even completed before the Mono has a Subscriber.

Writing it more concisely still has the same property:

~~~java
Mono<User> mono = Mono.fromFuture(client.fetchAsync(id));
~~~

Java must evaluate the argument **client.fetchAsync(id)** before calling **Mono.fromFuture(...)**. Thus, this is **not** a way to defer the client call until subscription.

### 3.2. Passing a Supplier: Creating the Future at Subscription

~~~java
Mono<User> mono = Mono.fromFuture(() -> client.fetchAsync(id));
~~~

At the time Mono is declared, the lambda expression has not run yet. On subscription, Reactor calls the Supplier to obtain a CompletableFuture, and then monitors that Future's result.

Points to remember:

- **No subscribe:** does not call client.fetchAsync(id) through this Supplier.
- **Subscribe once:** calls the Supplier once for that subscription.
- **Subscribe twice:** the Supplier is called for each subscription; if the client creates a new Future, there can be **two real requests**.
- **Retry:** retry performs a new subscription; a Supplier creating a new Future can re-launch the task. Consider idempotency if the task has side effects.

Supplier only defers **evaluating the expression returning the Future**. If you created a Future beforehand and wrote **() -> existingFuture**, the task can still be running from earlier; only retrieving the reference was deferred.

### 3.3. Using Mono.defer: Expressing the Deferred Assembly Boundary Clearly

~~~java
Mono<User> mono = Mono.defer(
        () -> Mono.fromFuture(client.fetchAsync(id))
);
~~~

**Mono.defer** calls the Supplier to create a new source Mono on each subscribe. In the case of simply converting a Future, this has equivalent effect regarding when **client.fetchAsync(id)** is called compared to **Mono.fromFuture(() -> client.fetchAsync(id))**.

Use **Mono.defer** if you need to decide *the entire way the publisher is constructed* at subscription time, such as choosing a source conditionally, reading current config, or composing multiple operations. If only deferring a single Future call, the Supplier overload of **Mono.fromFuture** is usually shorter and clearer.

**Important distinction:** None of these three approaches makes a Future that is already running become “not started yet”. To be truly lazy, you must defer **the API call itself that starts the task**.

## 4. Chronological Order: Assembly, Subscription, Completion

Consider two cases:

~~~text
A. Mono.fromFuture(client.fetchAsync(id))

t0  Call fetchAsync → Future is created, I/O may start
t1  Build Mono from that Future
t2  subscribe Mono → register to receive result
t3  Future completes → Mono emits value / completes / errors

If the Future completes before t2, Mono still emits the appropriate result on subscribe.


B. Mono.fromFuture(() -> client.fetchAsync(id))

t0  Build Mono, holding only Supplier; fetchAsync not called yet
t1  Not subscribed → no operation launched by Supplier
t2  subscribe → Supplier calls fetchAsync, Future is created
t3  Future completes → Mono emits value / completes / errors

Each subscription is a fresh evaluation of the Supplier.
~~~

The moment the **Future completes** can happen before or after subscribe for a pre-existing Future. That does not change the nature of a Mono: each subscription receives at most one value, a completion signal, or an error depending on the source's outcome.

In Java semantics, **CompletableFuture.supplyAsync(...)** normally schedules work immediately when invoked. Placing that statement outside a Supplier can make the work run before subscribe, regardless of how many Reactor operators follow.

## 5. Runnable Java 17+ Example: Seeing Exactly When the Future Is Created

The example uses **CompletableFuture.completedFuture(...)** so results and stdout are completely deterministic. Each time a Future is created, the helper prints a line and increments a counter. The goal is to prove **when the Future-creation call is evaluated**, not to simulate real I/O latency.

Create the project:

~~~text
future-mono-timing/
├── pom.xml
└── src/main/java/FutureMonoTiming.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>future-mono-timing</artifactId>
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
                    <mainClass>FutureMonoTiming</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/FutureMonoTiming.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

public class FutureMonoTiming {
    private static int created = 0;

    private static CompletableFuture<String> newFuture(String label) {
        created++;
        System.out.println("Create future " + label + " #" + created);
        return CompletableFuture.completedFuture(label + "-" + created);
    }

    public static void main(String[] args) {
        Mono<String> eager = Mono.fromFuture(newFuture("eager"));

        Mono<String> lazy = Mono.fromFuture(() -> newFuture("lazy"));

        Mono<String> deferred = Mono.defer(
                () -> Mono.fromFuture(newFuture("defer"))
        );

        System.out.println("--- before subscribe ---");

        eager.subscribe(v -> System.out.println("eager run 1 = " + v));
        eager.subscribe(v -> System.out.println("eager run 2 = " + v));

        lazy.subscribe(v -> System.out.println("lazy run 1 = " + v));
        lazy.subscribe(v -> System.out.println("lazy run 2 = " + v));

        deferred.subscribe(v -> System.out.println("defer run 1 = " + v));
        deferred.subscribe(v -> System.out.println("defer run 2 = " + v));
    }
}
~~~

Requires JDK 17+ and Maven. Run in the project directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program:

~~~text
Create future eager #1
--- before subscribe ---
eager run 1 = eager-1
eager run 2 = eager-1
Create future lazy #2
lazy run 1 = lazy-2
Create future lazy #3
lazy run 2 = lazy-3
Create future defer #4
defer run 1 = defer-4
Create future defer #5
defer run 2 = defer-5
~~~

**Explanation of output:**

1. In **Mono.fromFuture(newFuture("eager"))**, Java calls newFuture before subscribe, so “Create future eager #1” appears first.
2. Both Subscribers of **eager** observe **the single created CompletableFuture**. No new Future is created for the second subscription.
3. With **Mono.fromFuture(() -> newFuture("lazy"))**, the code inside Supplier runs for each subscription, creating Future #2 then Future #3.
4. With **Mono.defer(...)**, a new Publisher is created for each subscription, leading to Future #4 then #5.
5. Because each Future is a synchronously completed **completedFuture**, the subscribe callbacks in this example print results immediately and in order. If using asynchronous work on an Executor, **the completion order among multiple tasks may differ**.

The example intentionally **does not** use Thread.sleep to “wait” or assume thread ordering across multiple threads. It is a deterministic way to verify instantiation timing.

## 6. When the Future Actually Performs Asynchronous Work

To see the difference on a source that can run in the background, compare:

~~~java
// EAGER: supplyAsync is called immediately when this expression runs.
Mono<String> eager = Mono.fromFuture(
        CompletableFuture.supplyAsync(() -> fetchFromRemoteSystem())
);

// LAZY: supplyAsync is only called when the Mono has a subscription.
Mono<String> lazy = Mono.fromFuture(
        () -> CompletableFuture.supplyAsync(() -> fetchFromRemoteSystem())
);
~~~

These are **two illustrative snippets**, with fetchFromRemoteSystem() being an application-provided method; they are not a standalone Java program.

**Key point:** In the eager case, the work can be submitted to the Executor and run immediately. In the lazy case, supplyAsync is called and queued onto the Executor only upon subscribe. Once started, both are still asynchronous tasks; Mono does not automatically “re-run” a Future after it completes.

Additionally, **supplyAsync does not turn blocking logic into non-blocking I/O**. If fetchFromRemoteSystem uses blocking JDBC or synchronous network calls, it still holds an Executor thread while waiting. This approach may fit when needing compatibility with legacy APIs, but you must manage the Executor and avoid casually using commonPool for long-running blocking tasks. If you already have a true non-blocking client, prefer the client's asynchronous API and just bridge the result.

### Subscribing After the Future Has Completed

~~~java
CompletableFuture<String> alreadyDone =
        CompletableFuture.completedFuture("OK");

Mono<String> mono = Mono.fromFuture(alreadyDone);
mono.subscribe(System.out::println); // Prints: OK
~~~

No need to re-launch the Future: Reactor observes the existing completion state and emits the corresponding signals to the Subscriber.

### Subscribing Before the Future Completes

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
Mono<String> mono = Mono.fromFuture(pending);

mono.subscribe(v -> System.out.println("Received: " + v));
pending.complete("READY"); // Prints: Received: READY
~~~

Upon subscribe, the Future is not complete yet so there is no onNext. Once **complete("READY")** is called, the Mono emits the value. With a Future that actually completes on another thread, the callback may run on the thread completing the Future or be affected by Reactor scheduling operators; you should not rely on a fixed thread name.

## 7. One Shared Future Differs from Many New Futures

The two snippets below differ even though both have a Supplier.

~~~java
// An existing Future, which may have already started.
CompletableFuture<String> shared = client.fetchAsync("42");

// Supplier only returns the shared object; does not create a new request.
Mono<String> sharedMono = Mono.fromFuture(() -> shared);

// Supplier calls the API to create a new Future for each subscription.
Mono<String> newPerSubscription =
        Mono.fromFuture(() -> client.fetchAsync("42"));
~~~

If **sharedMono** has two Subscribers, both observe the same result, error, and cancellation state of one Future. If **newPerSubscription** has two Subscribers, it can create two independent requests/units of work.

This is a critical distinction for APIs with side effects such as creating orders, recording payments, sending emails, or updating data. If a controller or operator subscribes multiple times, a lazy source can re-send the real operation. **Lazy does not implicitly mean executing exactly once application-wide.**

In cases where you want to create the Future on the first subscription and share the result for subsequent ones, you can use **cache** at the Mono layer:

~~~java
Mono<String> cached = Mono.fromFuture(
        () -> client.fetchAsync("42")
).cache();
~~~

**cache()** stores and replays terminal signals for subsequent Subscribers, while coordinating concurrent Subscribers of the cached source. However, that also means results or errors may be retained: consider cache TTL, memory limits, data freshness, and operations with side effects. Cache does not automatically turn a write operation into an exactly-once transaction.

## 8. Values, Empty, Errors, and Differences Between Complete and Subscribe

### Future Completes Successfully with a Value

~~~java
Mono<Integer> value =
        Mono.fromFuture(CompletableFuture.completedFuture(42));
// On subscribe: onNext(42), then onComplete.
~~~

### Future Completes with null

~~~java
CompletableFuture<String> emptyFuture =
        CompletableFuture.completedFuture(null);

Mono<String> empty = Mono.fromFuture(emptyFuture);
// On subscribe: onComplete without onNext.
~~~

Reactive Streams does not allow onNext(null). If **null** genuinely needs to be distinguished from “not found”, design an appropriate result type (such as Optional or a status-bearing result) at the API boundary; Mono does not carry null values via onNext.

### Future Completes Exceptionally

~~~java
CompletableFuture<String> failed = new CompletableFuture<>();
Mono<String> result = Mono.fromFuture(failed);

result.subscribe(
        value -> System.out.println("OK: " + value),
        error -> System.out.println("Error: " + error.getMessage())
);

failed.completeExceptionally(
        new IllegalStateException("Service unavailable")
);
~~~

When a Future completes exceptionally, Mono emits **onError** instead of a normal value. Along the conversion path there may be exception wrapping from CompletionStage; when classifying errors, inspect the cause and the original API's contract. The example above only illustrates catching errors and assumes no automatic retry or recovery.

If the Supplier **throws an exception immediately when called**, creating the Future fails and the deferred pipeline must also be handled as an error. Place **onErrorResume**, **retryWhen**, or an appropriate error policy on the pipeline, avoiding hiding errors during task creation.

## 9. Cancelling Subscription Can Cancel the Future: Watch Out When Sharing

Per the Reactor API, by default **Mono.fromFuture(future)** has a mechanism to propagate cancel signals from the subscription to the CompletableFuture. Beyond the standard overload, there is **Mono.fromFuture(future, suppressCancel)**:

~~~java
CompletableFuture<String> future = client.fetchAsync("42");

Mono<String> defaultCancellation =
        Mono.fromFuture(future); // Default: may cancel the Future.

Mono<String> keepFutureRunning =
        Mono.fromFuture(future, true); // suppressCancel = true.
~~~

This is an illustrative snippet using a client provided by the application.

- **suppressCancel = false** (default): when the subscription is cancelled, the adapter may call cancel on the CompletableFuture object.
- **suppressCancel = true**: avoids propagating subscription cancellation to that Future; useful when the Future is managed elsewhere or needs to be observed by multiple Subscribers.
- The Supplier overload also has the variant **Mono.fromFuture(() -> client.fetchAsync(id), true)** when similar configuration is needed.

An easily overlooked point: **CompletableFuture.cancel(...) does not guarantee that work on the Executor/at the external system has stopped**. With standard CompletableFuture, the **mayInterruptIfRunning** parameter has no thread-interrupting effect as in some other Futures. Whether a real HTTP request, RPC, or I/O is actually cancelled depends on the client/SDK and its integration.

In particular, if **two subscriptions share the same Future** and one subscription is cancelled, cancelling the Future can affect the remaining observer as well. Thus you must clearly decide **who owns the Future**, whether it can be shared, and whether to propagate cancel or suppress it.

In WebFlux, a client request cancellation, timeout, or disconnect can lead to cancelling the upstream subscription depending on the pipeline. If the external source must still complete to persist state, design ownership and cancellation intentionally, and do not assume client cancellation has the right to abort business side effects.

## 10. Retry, Timeout, and Transformations: Which Future Is Actually Re-run?

### Retry with an Existing Future

~~~java
CompletableFuture<String> once = client.fetchAsync("42");

Mono<String> onceMono =
        Mono.fromFuture(once).retry(1);
~~~

If the **once** Future completes with an error, retry only **re-subscribes to the same failed Future**; it does not call client.fetchAsync again. If you want to create a new request, the source must be declared via Supplier/defer.

### Retry with a Per-Subscription Future Source

~~~java
Mono<String> retried = Mono.fromFuture(
        () -> client.fetchAsync("42")
).retry(1);
~~~

If the first attempt emits onError, retry re-subscribes and the Supplier is invoked to create a new Future. **retry(1)** allows one extra attempt after the first failure, but does not guarantee the error will resolve. With side effects, retry only when the API has safety mechanisms to avoid unintended duplicate effects; you may need idempotency keys, backoff, and rate limits.

### Timeout

~~~java
Mono<String> bounded = Mono.fromFuture(
        () -> client.fetchAsync("42")
).timeout(java.time.Duration.ofSeconds(3));
~~~

When time expires, the Mono signals a timeout error and cancels the upstream subscription per the operator mechanism. **A timeout at the Reactor layer is not a guarantee that the external system stopped I/O or rolled back the task**; distinguish cancelling the Publisher/Future from cancelling the task at the target service.

### Keeping the Pipeline Purely Reactor

~~~java
Mono<String> decorated = Mono.fromFuture(
        () -> client.fetchAsync("42")
)
.map(String::trim)
.filter(s -> !s.isEmpty())
.onErrorResume(error -> Mono.just("fallback"));
~~~

This snippet illustrates composing operators. With real records, fallback policies must depend on error type and business rules; do not swallow every error just because onErrorResume is available.

## 11. subscribeOn, publishOn, and Misconceptions About Threads

**Mono.fromFuture** does not mean results must arrive on a dedicated Reactor thread. Calling the Supplier and completing the Future callback can occur on different threads; that difference depends on the original API, Executor, completing thread, and scheduling operators.

- **subscribeOn(scheduler)** affects where upstream subscription takes place. If using **Mono.fromFuture(() -> client.fetchAsync(id))**, calling the Supplier typically occurs on the subscribe thread switched by subscribeOn.
- **publishOn(scheduler)** affects the thread processing signals in downstream operators from the publishOn position onward.
- **subscribeOn cannot turn back time.** If you already created **CompletableFuture.supplyAsync(...)** before adding subscribeOn, the work was already scheduled on CompletableFuture's Executor.
- **publishOn does not make a blocking library non-blocking.** Switching threads only changes where execution happens, not the nature of I/O or thread pool limits.

If you only have a **synchronous blocking** function rather than a true client-supported Future, a simpler bridge is:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id)
).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This is an illustrative snippet in an application that already has Result and blockingClient; boundedElastic isolates blocking work from the event loop within the scheduler's capacity. It **does not turn blocking operations into non-blocking I/O**, and still requires load limits.

## 12. Applying in Spring WebFlux

Suppose an SDK has a method **CompletableFuture<Profile> fetchAsync(String id)**. A WebFlux controller can return a Publisher created with a Supplier:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record Profile(String id, String displayName) {}

interface ProfileAsyncClient {
    CompletableFuture<Profile> fetchAsync(String id);
}

@RestController
class ProfileController {
    private final ProfileAsyncClient client;

    ProfileController(ProfileAsyncClient client) {
        this.client = client;
    }

    @GetMapping("/profiles/{id}")
    public Mono<Profile> get(@PathVariable String id) {
        return Mono.fromFuture(() -> client.fetchAsync(id));
    }
}
~~~

These are illustrative classes to place inside **a Spring Boot WebFlux project with configured dependencies and a ProfileAsyncClient bean**; not yet a self-launching app since client implementation and bootstrap are not defined.

**Why choose Supplier here?** The controller method is called to create the return value, while the framework performs the subscription according to the HTTP processing lifecycle. The Supplier places the fetchAsync call at the time the pipeline is subscribed. This creates a clear deferral boundary while allowing integration of cancellation and timeouts per policy.

In Spring, let **the framework subscribe** to the returned Mono; avoid calling **subscribe()** manually in the controller “just to trigger it for sure”, because doing so can detach the task from error signal management and response lifecycle. Do not call **block()**, **join()**, or **get()** on WebFlux request-handling threads just to extract a synchronous value.

If the SDK already returns a running Future before the controller calls it, bridging cannot make that task lazy. In that case you must examine the SDK's design or contract, or intentionally accept the eager model.

## 13. Common Mistakes and How to Check

| Common Mistake | Consequence | Fix |
| --- | --- | --- |
| **Mono.fromFuture(client.fetchAsync(id))** when wanting deferred | Client may be called right when assembling the pipeline, before subscribe. | Use **Mono.fromFuture(() -> client.fetchAsync(id))**. |
| **Mono.fromFuture(() -> existingFuture)** thinking it creates a new request | Only returns an old already-running Future; subscriptions share state. | Put the Future-creating call itself inside the Supplier if a new Future is needed. |
| **Subscribing twice to debug** | Supplier source may send two business requests. | Understand subscription counts; observe doOnSubscribe, API call counts, and consider intentional caching/sharing. |
| **Retrying on an old Future** | Retry does not launch a new request and may receive the exact same failure again. | Use a deferred source; design idempotency and retry limits. |
| **Assuming cancel is harmless** | One Subscriber can cancel a shared Future; real work may still run or affect another observer. | Define ownership, choose suppressCancel when appropriate, test with the real client. |
| **Using Future yet calling block/join in WebFlux** | Blocks the event loop or causes thread congestion. | Return Mono and use asynchronous operators. |
| **Calling supplyAsync then believing the task is non-blocking** | Blocking work still occupies the Executor; easily exhausts pools under high load. | Prefer non-blocking clients; isolate to a bounded pool if forced to use blocking. |
| **Not handling null and errors** | Confuses an empty Mono with no result, ignores onError. | Define the API contract, convert empty/error according to business rules. |
| **Requiring ordered stdout from multiple concurrent Futures** | Tests become flaky because completions can race. | Verify invocation counts/signals with counters, latches, StepVerifier, or controlled mocks; avoid measuring with sleep. |

### Test Cases You Should Have

1. **Before subscribe:** verify the supplier source has not been called; contrast with a pre-created Future.
2. **Single and multiple subscriptions:** count API invocations to confirm eager, per-subscription, or shared behavior.
3. **Future already completed before subscribe:** verify receiving the corresponding value/error.
4. **Future completing after subscribe:** verify Mono emits only once the Future completes.
5. **Future succeeding with null:** verify Mono completes empty, with no onNext(null).
6. **Future failing:** verify onError and retry/fallback policy.
7. **Cancel and timeout:** verify CompletableFuture state, behavior of the underlying client, and that real resources are released.
8. **Retry on a source with side effects:** verify idempotency and the actual number of times the task is invoked.

You can use **reactor-test / StepVerifier** to verify Mono signals; for Future creation timing, add invocation counters or a fake client that can complete Futures manually. Do not use sleep to infer ordering when scheduling is uncontrolled.

## 14. Checklist for Choosing a Conversion Approach

| Real-World Need | Appropriate Approach |
| --- | --- |
| Already have a CompletableFuture and just need to observe its result | **Mono.fromFuture(existingFuture)**. |
| Want an asynchronous API to be called only after subscribe | **Mono.fromFuture(() -> api.callAsync())**. |
| Want to rebuild a complex source Mono per subscription | **Mono.defer(() -> ...)**. |
| Shared Future, one Subscriber cancelling must not cancel the Future | **Mono.fromFuture(sharedFuture, true)** when fitting the ownership contract. |
| Multiple Subscribers need to share the result of one call | Design controlled sharing/caching instead of accidentally launching multiple times. |
| Have a synchronous blocking operation, no real Future API | **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())**, with resource limits. |
| Want to convert a general CompletionStage, not necessarily CompletableFuture | Consider **Mono.fromCompletionStage(...)** and its Supplier variant. |

## 15. Key Takeaways

**Mono.fromFuture(future)** turns **an existing Future** into a Publisher; that Future may have already started or completed before subscribe. **Mono.fromFuture(() -> createFuture())** defers calling the Future-creating function until **each subscription**, while **Mono.defer(() -> Mono.fromFuture(createFuture()))** generalizes the deferred boundary.

Because **each subscription can lead to another API call**, always check launch counts, retries, and side effects. At the same time, decide **whether cancellation propagates to the Future**, handle null/errors/timeouts per contract, and avoid blocking the event loop. Converting CompletableFuture to Mono is a bridge between two asynchronous models; it does not by itself alter blocking behavior or the real lifecycle of a task already launched by an SDK.

**API References:**
- [Project Reactor Mono API – fromFuture and fromCompletionStage](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
