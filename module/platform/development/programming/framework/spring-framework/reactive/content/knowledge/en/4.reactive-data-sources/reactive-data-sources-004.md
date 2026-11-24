# Creating Completion, Error, and `never` Signals in Project Reactor (Spring WebFlux)

## 1. Lesson Objectives

When creating a reactive data source, we do not always have a value to emit. An operation may **complete successfully without producing data**, **fail**, or **keep waiting without emitting a terminal signal**. Project Reactor provides three corresponding factory groups for both `Mono` and `Flux`:

- `Mono.empty()` / `Flux.empty()`: completes successfully without emitting elements.
- `Mono.error(Throwable)` / `Flux.error(Throwable)`: terminates with an error.
- `Mono.never()` / `Flux.never()`: emits no elements, no completion signal, and no error.

This lesson focuses on **signal semantics**, how to create each source, effects on downstream operators, how to test them, time limits, subscription cancellation, and how to apply them in Spring WebFlux. These three sources represent three very different states; you should not swap them merely because they all “have no data”.

## 2. Understand the Signal Contract Before Writing Code

`Mono<T>` represents at most one element; `Flux<T>` represents zero to many elements. A Publisher interacts with a subscriber through signals defined by the Reactive Streams protocol.

```text
Subscription:           onSubscribe(subscription)

Empty completion:       onSubscribe -> onComplete
Completion with data (Mono):
                        onSubscribe -> onNext(value) -> onComplete
Completion with data (Flux):
                        onSubscribe -> onNext(a) -> onNext(b) -> ... -> onComplete
Error termination:      onSubscribe -> [possibly prior onNext] -> onError(error)
Not terminated:         onSubscribe -> ... no onNext/onComplete/onError
```

Principles to remember:

1. `onSubscribe` is the step that establishes the subscription; `request(n)` from the subscriber expresses demand to receive data. With `never()`, subscription still occurs, but there are no subsequent data or terminal signals.
2. `onComplete` and `onError` are two **terminal** signals, mutually exclusive within a subscription. After either signal, the source must not emit any further `onNext`.
3. `Mono.empty()` **has** an `onComplete` terminal signal; `Mono.never()` **does not**.
4. An error is a **signal in the pipeline**, not synonymous with a Java method having to `throw` immediately at publisher creation time.
5. `cancel()` is an action from the subscriber side to stop observing/receiving data. It differs from `onComplete` and `onError`: cancelling does not mean a success or failure outcome has been emitted.

### Exact Comparison of the Three Sources

| Source | `onNext` | `onComplete` | `onError` | Terminates by Itself by Default? |
|---|---|---|---|---|
| `Mono.empty()` | No | Yes, as soon as the subscription is processed | No | Yes |
| `Mono.error(e)` | No | No | Yes, with `e` | Yes |
| `Mono.never()` | No | No | No | No |
| `Flux.empty()` | No | Yes | No | Yes |
| `Flux.error(e)` | No | No | Yes | Yes |
| `Flux.never()` | No | No | No | No |

With these direct factories, **no new thread is created just by calling `empty()`, `error()`, or `never()`**. A reactive source describes a stream of signals; schedulers and asynchronous execution come from other operators or sources if present.

## 3. Creating an Empty-Completing Source: `empty()`

A successful outcome sometimes carries no value: an optional item is not found, no elements remain in a stream, or a command only needs to notify that it has finished.

```java
Mono<String> noUser = Mono.empty();
Flux<Integer> noNumbers = Flux.empty();

Mono<Void> completedCommand = Mono.empty();
```

`noUser` **does not emit `null`**. It completes with `onComplete` without emitting any `onNext`. Because Reactor forbids `null` elements in publishers, `Mono.just(null)` is not the way to represent “no data”.

Case with a potentially absent value:

```java
String optionalName = null;
Mono<String> userName = Mono.justOrEmpty(optionalName);
```

`Mono.justOrEmpty(null)` creates a source that completes empty; if the input is non-`null`, it creates a source that emits one value and completes. For `Optional<T>`, you can also use `Mono.justOrEmpty(optional)`.

### What Does `Mono<Void>` Mean?

`Mono<Void>` is commonly used for actions where the client **only needs to know whether execution succeeded or failed**, without needing a return value:

```java
Mono<Void> auditAction = Mono.fromRunnable(
        () -> System.out.println("Audit finished")
);
```

When subscribed, the `Runnable` runs; if it returns normally, `Mono<Void>` completes empty. If the `Runnable` throws an exception, Reactor turns it into `onError`. This is an **illustrative snippet**, requiring `import reactor.core.publisher.Mono` and running in a program with Reactor Core; do not call `.subscribe()` yourself inside a WebFlux service/controller just to trigger it.

Distinguish two questions:

- `Mono<Void>`: a **type** contract stating that the publisher carries no meaningful payload.
- `Mono.empty()` or a `Mono<T>` ending empty: the **behavior** of completing without emitting `onNext`. A `Mono<String>` completing empty is completely valid.

A value-emitting source can also be turned into a completion-only signal:

```java
Mono<Void> finished = Mono.just("temporary-result").then();
```

`.then()` ignores the upstream success value, waits for upstream to complete, and then completes empty; if upstream errors, the error continues downstream; if upstream never terminates, `.then()` cannot terminate either.

### Handling Empty Streams

```java
Mono<String> value = Mono.<String>empty()
        .defaultIfEmpty("anonymous");
```

When upstream completes empty, `defaultIfEmpty` emits `"anonymous"` and completes. If an alternate pipeline is needed, use `switchIfEmpty`:

```java
Mono<String> value = Mono.<String>empty()
        .switchIfEmpty(Mono.just("from-fallback"));
```

`defaultIfEmpty` requires a **non-null** default value; `switchIfEmpty` allows a fallback source that has asynchronous logic or emits an error. Both trigger only when upstream **completes empty**; they do not rescue an `error()` source or a `never()` source.

## 4. Creating an Error-Terminating Source: `error()`

Use `Mono.error` or `Flux.error` when the system **cannot provide a successful result**: invalid input data, rejected operation, or a failed dependency.

```java
Mono<String> failedLookup =
        Mono.error(new IllegalArgumentException("invalid id"));

Flux<String> failedStream =
        Flux.error(new IllegalStateException("source unavailable"));
```

The subscriber receives `onError`. For the `error()` source itself above, **there is no `onNext` and no `onComplete`**.

### Distinguish Creating an Error from Emitting an Error Signal

```java
Mono<String> eager = Mono.error(
        new IllegalArgumentException("invalid id")
);

Mono<String> lazy = Mono.error(
        () -> new IllegalArgumentException("invalid id")
);
```

- In `eager`, the exception object is created immediately when evaluating `new IllegalArgumentException(...)`; the error **signal** is only emitted when there is a subscriber.
- In `lazy`, the `Supplier` creates the exception **on each subscription**. This is useful when you need a fresh error with context determined at subscription time or do not want to instantiate the exception upfront.
- Neither is **equivalent** to `throw new IllegalArgumentException(...)` directly outside the pipeline: `throw` would terminate the Java method before returning the publisher.

Example of a rejection branch in a reactive service:

```java
Mono<String> findUsername(boolean permitted) {
    if (!permitted) {
        return Mono.error(
                new SecurityException("access denied")
        );
    }
    return Mono.just("alice");
}
```

The snippet above is an **illustrative method in a class with Reactor**, not a standalone Java file. The caller receives a `Mono<String>` and decides how to observe or handle the error.

### An Error Can Appear After Several `Flux` Elements

```java
Flux<String> stream = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("failed")),
        Flux.just("C")
);
```

When subscribed normally, the stream emits `"A"`, `"B"`, then `onError`; `"C"` **is not emitted**, because the error terminated the sequence. `Flux.empty()` at the same position simply completes successfully, allowing `concat` to proceed to the next source.

```text
concat(just(A,B), empty(), just(C))   -> A, B, C, complete
concat(just(A,B), error(e), just(C))  -> A, B, error(e)
concat(just(A,B), never(), just(C))   -> A, B, then wait forever if not cancelled/timed out
```

`concat` subscribes to the sources sequentially in order and requires the preceding source to **complete successfully** to move on.

### Handling Errors Is a Different Branch from Handling Empty

```java
Mono<String> recovered = failedLookup
        .onErrorResume(IllegalArgumentException.class,
                error -> Mono.just("guest"));
```

`onErrorResume` runs when upstream emits a matching `onError`. You can use `onErrorReturn` to return a fallback value, or `onErrorMap` to transform an exception into a more suitable error type.

```java
Mono<String> ignoredError = failedLookup.onErrorComplete();
```

`onErrorComplete` turns an error into empty completion; this **loses error information downstream**, so only use it when business logic intentionally treats that error as having no data. Do not replace every error with empty, as that hides system failures.

To *convert empty into an error*:

```java
Mono<String> requiredUser = Mono.<String>empty()
        .switchIfEmpty(Mono.error(
                new java.util.NoSuchElementException("user not found")
        ));
```

This differs from `onErrorResume`: the `switchIfEmpty` operator reacts only to `onComplete` without `onNext`, whereas `onErrorResume` reacts to `onError`.

## 5. Creating a Source That Never Emits or Terminates: `never()`

```java
Mono<String> waitingOne = Mono.never();
Flux<String> waitingMany = Flux.never();
```

After subscribing, a `never()` source emits no `onNext`, `onComplete`, or `onError`. It merely sits as a waiting subscription until **cancelled**, **replaced by time-limiting logic**, or no longer observed externally. `never()` does not perform background work or spawn a waiting thread on its own.

`never()` is useful mainly in **control-flow testing**, exercising cancel behavior, timeouts, or source composition. In real business logic, an accidental never source can cause an HTTP request or task to wait endlessly.

### Distinguishing `never()` from Infinite Sequences

| Expression | What Happens? |
|---|---|
| `Flux.never()` | Emits no elements; neither completes nor errors |
| `Flux.interval(Duration.ofSeconds(1))` | Emits numbers `0`, `1`, `2`, ... at a regular interval; does not self-complete unless bounded |
| `Mono.delay(Duration.ofSeconds(1))` | After the delay, emits one `Long` value, then completes |
| `Mono.empty()` | Completes immediately, no waiting |
| `Mono.never().take(Duration.ofSeconds(2))` | Can complete empty because the **`take` operator** enforces a deadline; `never()` itself still never self-completes |
| `Mono.never().timeout(Duration.ofSeconds(2))` | Emits a **timeout error** if no appropriate signal arrives before the deadline |

Do not call “emitting no data” and “completing empty” the same state. With `never()`, operators requiring `onComplete` like `then`, `collectList`, or `switchIfEmpty` will never get a chance to complete without external intervention.

### Cancelling a Subscription with `dispose()`

When using the `.subscribe(...)` overload, Reactor returns a `Disposable`. The subscription owner can call `dispose()` to cancel:

```java
Disposable subscription = Mono.never()
        .doFinally(signal ->
                System.out.println(signal.name()))
        .subscribe();

subscription.dispose();
```

When cancelled successfully in the example, `doFinally` observes `CANCEL`. This signal **is not** `onComplete` sent to the subscriber. Calling `dispose()` on an already-completed subscription produces no new terminal signal.

In WebFlux applications, the framework usually owns the response subscription: controllers should **return `Mono`/`Flux`**, letting the framework manage subscription, termination, and disconnection. Do not subscribe manually in a controller just to “make the code run”.

### Preventing Infinite Waiting with Timeout

```java
Mono<String> guarded = Mono.<String>never()
        .timeout(
                Duration.ofSeconds(2),
                Mono.just("fallback")
        );
```

With the fallback overload, when the deadline expires without a result, Reactor switches to the fallback publisher instead of emitting a `TimeoutException` error. With `timeout(Duration)` **without a fallback**, the stream terminates with a timeout error; in that case you can use `onErrorResume` to decide how to handle it.

The effect at the time boundary is added by the operator: `never()` does not change its nature. Timeout does not guarantee that tasks outside Reactor stop immediately if they do not support cancellation.

**Warning:** do not call an unbounded `.block()` on `Mono.never()`; the calling thread can wait indefinitely. On the WebFlux event loop, in general you should not call `.block()` even on sources that will complete.

## 6. Runnable Java 17+ Program: Observing `empty`, `error`, `never`

This example uses **standalone Reactor Core**, without booting Spring Boot. Java 17+, Maven, and the ability to download Maven dependencies are sufficient. Reactor `3.6.6` is pinned so the example has a fixed version; real Spring Boot projects should use the Reactor version managed by Spring Boot to avoid conflicts.

Create the structure:

```text
reactor-signal-demo/
├── pom.xml
└── src/main/java/edu/demo/SignalDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-signal-demo</artifactId>
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
```

Contents of `src/main/java/edu/demo/SignalDemo.java`:

```java
package edu.demo;

import java.time.Duration;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

public final class SignalDemo {
    public static void main(String[] args) {
        trace("empty", Mono.<String>empty(), false);
        trace("error", Mono.<String>error(
                new IllegalArgumentException("bad-id")), false);
        trace("never", Mono.<String>never(), true);

        String emptyFallback = Mono.<String>empty()
                .defaultIfEmpty("anonymous")
                .block();
        System.out.println("emptyFallback=" + emptyFallback);

        String errorFallback = Mono.<String>error(
                        new IllegalStateException("down"))
                .onErrorReturn("cached")
                .block();
        System.out.println("errorFallback=" + errorFallback);

        String timeoutFallback = Mono.<String>never()
                .timeout(
                        Duration.ofMillis(150),
                        Mono.just("timed-out"))
                .block(Duration.ofSeconds(2));
        System.out.println("timeoutFallback=" + timeoutFallback);
    }

    private static void trace(
            String label, Mono<String> publisher, boolean cancel) {
        System.out.println("[" + label + "]");

        Disposable subscription = publisher
                .doOnSubscribe(ignored ->
                        System.out.println("subscribe"))
                .doFinally(signal ->
                        System.out.println("finally=" + signal.name()))
                .subscribe(
                        value -> System.out.println("next=" + value),
                        error -> System.out.println(
                                "error=" + error.getClass().getSimpleName()
                                + ":" + error.getMessage()),
                        () -> System.out.println("complete")
                );

        if (cancel) {
            subscription.dispose();
        }
    }
}
```

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.demo.SignalDemo
```

Expected `System.out` lines in order (Maven may print its own info depending on configuration):

```text
[empty]
subscribe
complete
finally=ON_COMPLETE
[error]
subscribe
error=IllegalArgumentException:bad-id
finally=ON_ERROR
[never]
subscribe
finally=CANCEL
emptyFallback=anonymous
errorFallback=cached
timeoutFallback=timed-out
```

Explanation:

1. `empty`: subscriber was subscribed, received `onComplete` without `onNext`; `doFinally` saw `ON_COMPLETE`.
2. `error`: subscriber received `onError` and did not receive `onComplete`; `doFinally` saw `ON_ERROR`.
3. `never`: no `next`, `complete`, or `error` callback; `dispose()` ended the subscription lifecycle via the `CANCEL` path, and `doFinally` saw `CANCEL`.
4. `defaultIfEmpty` handles only empty; `onErrorReturn` handles only error; `timeout` adds a time-limit mechanism for never. `.block(Duration.ofSeconds(2))` in the example is a way to wait **in a console program**; do not use that technique on an event-loop thread in a WebFlux controller.

Do not call `.block()` to observe `Mono.never()` directly. In this example, `never` is cancelled or has an explicit timeout so the program can finish.

## 7. `Flux.empty`, `Flux.error`, `Flux.never` Also Follow the Same Rules

`Flux` can emit multiple `onNext` signals before termination, but the empty/error/never factories still use the same semantics:

```java
Flux<Integer> emptyNumbers = Flux.empty();
Flux<Integer> failedNumbers =
        Flux.error(new IllegalStateException("bad source"));
Flux<Integer> waitingNumbers = Flux.never();
```

These snippets require `import reactor.core.publisher.Flux`. To see the effect when combining sources:

```java
Flux<String> continues = Flux.concat(
        Flux.just("one"),
        Flux.empty(),
        Flux.just("two")
);

Flux<String> stops = Flux.concat(
        Flux.just("one"),
        Flux.error(new IllegalStateException("stop")),
        Flux.just("two")
);

Flux<String> waits = Flux.concat(
        Flux.just("one"),
        Flux.never(),
        Flux.just("two")
);
```

`continues` emits `one`, `two`, then completes. `stops` emits `one`, then errors. `waits` emits `one`, then does not complete without an external limit/cancellation, so the `two` part will not be emitted. These snippets are **code fragments**, not standalone runnable programs; the `Flux<String>` type is inferred from the `just` sources and the `concat` operator.

With `Flux.error(...)` following a data source, elements already emitted **are not retracted**. An error is terminal from the moment it is emitted, not a rollback operation of `onNext` events that the subscriber has already received.

## 8. Testing Signal Reactions with `StepVerifier`

Testing reactive sources should verify the **exact signals**, rather than just calling `.block()` and comparing values. `reactor-test` provides `StepVerifier` to assert the order of events. In particular, with `never`, the test needs to **cancel or apply timeout/virtual time**, otherwise it can hang.

To add tests to the Maven project in section 6, add dependencies to `<dependencies>`:

```xml
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
```

Add `maven-surefire-plugin` to `<plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
</plugin>
```

Create `src/test/java/edu/demo/SignalDemoTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SignalDemoTest {
    @Test
    void emptyCompletesWithoutAValue() {
        StepVerifier.create(Mono.<String>empty())
                .verifyComplete();

        StepVerifier.create(Flux.<Integer>empty())
                .verifyComplete();
    }

    @Test
    void errorTerminatesTheSequence() {
        Flux<String> source = Flux.concat(
                Flux.just("A"),
                Flux.<String>error(
                        new IllegalArgumentException("invalid")),
                Flux.just("B")
        );

        StepVerifier.create(source)
                .expectNext("A")
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "invalid".equals(error.getMessage()))
                .verify();
    }

    @Test
    void neverCanBeCancelledOrTimedOut() {
        StepVerifier.create(Mono.<String>never())
                .expectSubscription()
                .thenCancel()
                .verify();

        StepVerifier.withVirtualTime(() ->
                        Mono.<String>never()
                                .timeout(Duration.ofSeconds(5)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectError(TimeoutException.class)
                .verify();
    }
}
```

Run:

```bash
mvn test
```

When the assertions are correct, all three test methods will pass; `StepVerifier.withVirtualTime` simulates 5 seconds elapsing on a virtual scheduler without having to wait 5 real seconds. Always construct pipelines with time operators **inside the supplier** of `withVirtualTime`, as in the example, so the virtual scheduler is set up beforehand.

The third test intentionally includes two ways to exit `never`:

- `.thenCancel()` sends a cancel signal and verifies closing the subscription.
- `.timeout(Duration.ofSeconds(5))` produces `TimeoutException` after the virtual deadline; here the **timeout operator** is the source of `onError`, rather than `Mono.never()` emitting an error itself.

If you test `never()` with `StepVerifier.create(Mono.never()).verifyComplete()`, the test has no termination mechanism and can get stuck.

## 9. Applying in Spring WebFlux

In a WebFlux controller, `Mono`/`Flux` is the description of work for Spring to monitor and turn into an HTTP response. The three signal types do not automatically correspond to three specific HTTP statuses.

Example **integration snippet** inside a `@RestController` class that has imported `Mono`, `ResponseEntity`, `ResponseStatusException`, `HttpStatus`, `Duration`, `@GetMapping`, and `@PathVariable`:

```java
@GetMapping("/items/{id}")
public Mono<ResponseEntity<String>> item(@PathVariable String id) {
    Mono<String> found = "42".equals(id)
            ? Mono.just("item-42")
            : Mono.empty();

    return found
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}

@GetMapping("/reject")
public Mono<String> reject() {
    return Mono.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "invalid request"));
}

@GetMapping("/guarded")
public Mono<String> guarded() {
    return Mono.<String>never()
            .timeout(Duration.ofSeconds(2), Mono.just("fallback"));
}
```

This is an illustrative snippet **that must be placed in a real WebFlux controller**, not yet a standalone Spring Boot application; the `/guarded` endpoint uses `never` solely to demonstrate timeout handling. In a real system, apply timeouts to publishers from actual HTTP clients, databases, or services.

- `/items/42`: emits a `ResponseEntity` containing `"item-42"` and HTTP 200.
- `/items/other`: the empty branch triggers `defaultIfEmpty`, creating a `ResponseEntity` with HTTP 404.
- `/reject`: Reactor emits a `ResponseStatusException` error signal, letting Spring WebFlux's HTTP error-handling mechanism turn it into the appropriate error response (HTTP 400 in standard configuration).
- `/guarded`: after about 2 seconds, returns the body `"fallback"` due to the timeout operator, without keeping the request waiting indefinitely.

**Do not assume `Mono.empty()` defaults to HTTP 404.** It is a completion signal without payload; to decide the HTTP status code, return `Mono<ResponseEntity<T>>`, throw/map an appropriate error, or handle it in a controller/advice per the API contract.

### Using empty, error, never According to Purpose

| Business Case | Suitable Representation | Condition |
|---|---|---|
| Search where not-found is allowed | `Mono.empty()` | Caller actively decides replacement value or 404 |
| Update operation succeeds, no payload needed | `Mono<Void>` completes | Errors still propagate via `onError` |
| Bad ID, access denied, dependency failed | `Mono.error(...)` | Use clear exception type / HTTP mapping |
| Testing cancellation or timeout behavior | `Mono.never()` in tests | Test must cancel/timeout |
| Real network operation that may hang | Publisher from real client + `.timeout(...)` | Configure timeout, retry, and fallback per business rules |

Avoid creating `Mono.never()` as a stand-in for “no result yet”. For results that are not ready yet, a reactive source must **actually emit data, complete, or error when the condition changes**; `never()` by itself does not monitor any event.

## 10. Observing and Diagnosing Signals

Observation operators help determine what state a source is in:

- `doOnSubscribe`: a subscriber subscribed.
- `doOnNext`: a value was emitted; does not run for the three direct factories `empty`, `error`, `never`.
- `doOnComplete`: for `Flux`, runs when `Flux` completes successfully.
- `doOnSuccess`: for `Mono`, runs on successful completion; if the Mono is empty, the parameter may be **`null`**. This is an observation callback, **it does not mean Mono emitted `onNext(null)`**.
- `doOnError`: observes errors.
- `doOnCancel`: observes cancellation requests.
- `doFinally`: observes the lifecycle termination type (`ON_COMPLETE`, `ON_ERROR`, or `CANCEL`), so it is useful for distinguishing scenarios.

Example:

```java
Mono.<String>empty()
    .doOnSuccess(value ->
            System.out.println(value == null ? "empty" : value))
    .subscribe();
```

This snippet prints `empty` because `doOnSuccess` receives `null` when `Mono` completes without a value; it **cannot** be used to prove that `onNext` occurred.

Do not log and accidentally swallow errors. When calling `.subscribe(...)` manually on a publisher that may emit errors, pass an `errorConsumer`; if missing, an unhandled error may be reported by Reactor as an error lacking an error callback. In Spring WebFlux, most controllers return the publisher directly so the framework manages subscription and errors through the HTTP layer.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `Mono.just(null)` to represent no data | Reactor forbids `null` elements | Use `Mono.empty()` or `Mono.justOrEmpty(...)` |
| Using `Mono.never()` instead of `Mono.empty()` | `switchIfEmpty`, `then`, `collectList` cannot complete | If there are no elements and the task has ended, use `empty()` |
| Using `Mono.empty()` instead of `Mono.error()` when a dependency fails | Real failure is interpreted as an absent result | Return an error signal and map errors per business logic |
| Thinking `error()` runs `throw` immediately when creating the publisher | Confuses creation time with subscribe time | Distinguish instantiating a Throwable from emitting `onError` |
| Calling `.block()` on `never()` | Thread waits indefinitely | Use timeout/cancel; avoid `.block()` on the WebFlux event loop |
| Forgetting the error callback in manual `.subscribe(...)` | Errors are not handled properly | Pass an error consumer or let the framework own the subscription |
| Using `defaultIfEmpty` to recover from errors | Operator does not run when receiving `onError` | Use `onErrorResume`/`onErrorReturn` per policy |
| Using `onErrorResume` for an `empty()` source | No `onError` to trigger it | Use `switchIfEmpty` or `defaultIfEmpty` |
| Expecting `never()` to `timeout` by itself without adding an operator | Publisher has no built-in timeout mechanism | Add `.timeout(...)` or I/O-layer timeout |
| Treating `cancel()` as `onComplete` | Incorrect lifecycle semantics | Observe `doFinally(CANCEL)` and clean up resources appropriately |

## 12. Self-Check Exercises

**Exercise 1.** Predict the signals from:

```java
Mono.<String>empty()
    .switchIfEmpty(Mono.just("guest"));
```

Result: emits `"guest"` then completes, because upstream ended empty.

**Exercise 2.** Predict the signals from:

```java
Mono.<String>error(new IllegalStateException("failure"))
    .defaultIfEmpty("guest");
```

Result: `onError(IllegalStateException)`. `defaultIfEmpty` does not run because upstream **errored**, not completed empty.

**Exercise 3.** Predict the signals from:

```java
Mono.<String>never()
    .switchIfEmpty(Mono.just("guest"));
```

Result: does not emit `"guest"`, does not complete, and does not error without external cancellation/timeout. `switchIfEmpty` needs to see an empty `onComplete` which it never receives.

**Exercise 4.** Why does `Flux.concat(Flux.just("A"), Flux.error(e), Flux.just("B"))` not emit `"B"`?

Result: `concat` must wait for the second source to complete successfully before subscribing to the third source. The second source emits `onError`, causing the entire concat to terminate with an error.

**Exercise 5.** To test a publisher that never emits data without hanging the test, which approach should you use?

Result: `StepVerifier` with `.thenCancel()` or wrapping `.timeout(...)` and asserting `TimeoutException` (prefer virtual time for time-based tests).

## 13. Knowledge Summary

The three factories differ in their **terminal signal**, not only in the number of values:

- `empty()` means *no data and completed successfully*.
- `error(e)` means *failed; propagate error to the subscriber*.
- `never()` means *no data and no notification of completion or failure*.

When building a pipeline, determine whether downstream needs to handle **empty** (`defaultIfEmpty`, `switchIfEmpty`), **error** (`onErrorResume`, `onErrorReturn`), or **waiting with no signals** (`timeout`, cancellation). Observe `doFinally` and write `StepVerifier` tests to verify all three branches accurately.

## Official Documentation

- Project Reactor, **Mono API** (`empty`, `error`, `never`, `doFinally`, `timeout`): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Project Reactor, **Flux API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor, **Simple Ways to Create a Flux or Mono and Subscribe to It**: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor, **Handling Errors**: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor, **Testing**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework, **WebFlux `ResponseEntity`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html