# Distinguishing Empty, Error, and Non-Terminating Sequences in Mono and Flux

In Project Reactor and Spring WebFlux, **"no data right now" does not mean "completed", and "completed with no data" does not mean "failed"**. A `Mono<T>` or `Flux<T>` can terminate normally without emitting an element, terminate with an error, or never terminate. These three states lead to very different behaviors for fallbacks, timeouts, HTTP responses, testing, and resource cleanup.

This lesson focuses on **signal semantics and how to handle the three sequence kinds**, within the parent context **Mono and Flux** of the Spring Framework - reactive module.

## 1. Learning Objectives

After this lesson, you will be able to:

- Recognize `Mono.empty()`, `Flux.empty()`, `Mono.error(...)`, `Flux.error(...)`, `Mono.never()`, and `Flux.never()`.
- Distinguish **empty completion**, **error termination**, and **indefinite waiting** based on `onNext`, `onError`, and `onComplete`.
- Understand why `defaultIfEmpty`/`switchIfEmpty` only handle streams that **complete empty**, whereas `onErrorResume` handles **errors**, and `timeout` handles **no signal arriving in time**.
- Distinguish a silent non-terminating source from a source that emits multiple elements without terminating.
- Write and test pipelines with time limits, handle unsubscription, and map results appropriately to HTTP in Spring WebFlux.

## 2. The Signal Protocol as the Foundation

Reactor is built on Reactive Streams. A `Publisher` is subscribed to by a `Subscriber`, sends `onSubscribe(subscription)`, and can then send data via `onNext(value)` and a single terminal signal via **`onComplete()`** or **`onError(error)`**. The two terminal signals are mutually exclusive: after `onComplete` or `onError`, that stream can no longer emit any valid elements.

`Subscription.request(n)` expresses demand for data from downstream; `Subscription.cancel()` expresses a cancellation request. **Cancel is not an `onComplete` or `onError` call sent to the subscriber.** A compliant publisher never emits `null` in `onNext`; missing values are represented by empty completion or another valid data model, depending on the problem.

`Mono<T>` emits at most one `onNext`; `Flux<T>` emits zero to many `onNext`. Both can be empty, error, or wait forever.

```text
Empty:               onSubscribe  ──────────────────→ onComplete
Error:               onSubscribe  ──────────────────→ onError(E)
Non-terminating:     onSubscribe  ────────────────→  (no terminal signal)
With data:           onSubscribe → onNext(A) → onNext(B) → onComplete
Data then error:     onSubscribe → onNext(A) ────────→ onError(E)
Infinite data:       onSubscribe → onNext(A) → onNext(B) → ... (not terminal yet)
```

The diagram shows logical ordering; in real applications, signals can arrive over time on different schedulers. With an empty or error source, the terminal signal may appear right after subscription without waiting for any data element. However, **declaring** a pipeline with operators usually does not execute the work yet: common cold sources only start upon `subscribe`.

## 3. Three Sequence Kinds: Comparison Table

| Property | Empty sequence (`empty`) | Error sequence (`error`) | Non-terminating sequence (`never`) |
| --- | --- | --- | --- |
| Reactor factory | `Mono.empty()`, `Flux.empty()` | `Mono.error(ex)`, `Flux.error(ex)` | `Mono.never()`, `Flux.never()` |
| `onNext` | None | None for a directly created `error` source; other streams may emit data before failing | None for a directly created `never` source |
| `onComplete` | **Yes** | No | No |
| `onError` | No | **Yes** | No |
| Has terminal signal? | Yes, successful completion | Yes, failure | No |
| `defaultIfEmpty` / `switchIfEmpty` | Triggered | No | No |
| `onErrorResume` | No | Triggered | No |
| `timeout` | Usually unnecessary since it already completed | Does not "cure" an error that already occurred | Can produce a timeout error when the deadline expires |
| `block()` in demos | Returns `null` if it completes empty | Throws the corresponding exception/wrapped by Reactor when needed | Waits indefinitely if there is no timeout/cancel |

**Important:** "empty" is **successful completion with 0 elements**. "error" is **a failure outcome**, not a normal element. "never" describes **the absence of both data signals and any final signal**; a subscription will not complete on its own unless acted upon by cancellation or an operator like `timeout`.

## 4. Empty Sequences: Successful Completion Without a Value

`Mono.empty()` represents an operation that finishes successfully without returning data; `Flux.empty()` represents a 0-element sequence that completes. Some valid empty sources:

- Key lookup finds no result: the repository returns `Mono.empty()`.
- Filtering drops every element: `Flux.just(1, 3).filter(n -> n % 2 == 0)` completes empty.
- Empty input collection: `Flux.fromIterable(List.of())` completes empty.
- A task that only signals "done": `Mono<Void>`, for example `Mono.fromRunnable(task)` or the result after `then()`.

A quick reading example:

```java
Mono<String> emptyMono = Mono.empty();
Flux<Integer> emptyFlux = Flux.empty();

emptyMono.subscribe(
    value -> System.out.println("next " + value),
    error -> System.out.println("error"),
    () -> System.out.println("complete")
);
// Prints: complete
```

Even without `onNext`, the `onComplete` callback is still invoked. The word "empty" does **not** mean the publisher has not run yet; it may have finished checking and confirmed there are no results.

### Producing an Empty Mono from a Potentially Missing Value

`Mono.just(value)` requires `value` to be non-`null` and fails immediately if `null` is passed. If the input can be `null`, use `Mono.justOrEmpty(value)` or `Mono.justOrEmpty(optional)`. `Mono.fromCallable(() -> null)` also represents empty completion when the `Callable` returns `null`; this is a mechanism of the source adapter, not permission for `onNext(null)`.

An easily confused detail:

- `doOnNext(value -> ...)` does **not** run when a `Mono` is empty.
- `Mono`'s `doOnSuccess(value -> ...)` **can be called with `value == null`** when the Mono completes empty. Do not use this callback as proof that data was emitted.
- `switchIfEmpty` accepts a fallback publisher; for fallback logic that is costly or has side effects, wrap it with `Mono.defer(() -> lookupFallback())` to defer creating the source.

### Choosing a Fallback for an Empty Sequence

```java
Mono<String> a = Mono.<String>empty()
    .defaultIfEmpty("no-data");

Mono<String> b = Mono.<String>empty()
    .switchIfEmpty(Mono.just("fallback-source"));
```

`defaultIfEmpty` provides a replacement **value**. `switchIfEmpty` switches to a replacement **publisher**, making it suitable for an asynchronous fallback query. If upstream produces a value, the fallback is not used; if upstream emits an error, these two operators are not used for error handling.

You cannot apply `defaultIfEmpty(null)` to represent "nothing", because Reactor does not accept `null` as an element. With `Mono<Void>`, use `then`/`thenReturn` or an appropriate publisher composition to chain work, rather than expecting an `onNext` of type `Void`.

## 5. Error Sequences: Abnormal Termination with onError

`Mono.error(new IllegalStateException("bad state"))` and `Flux.error(...)` emit an error signal upon subscription. A pipeline can also emit some data **before** encountering an error:

```java
Flux<Integer> result = Flux.just(2, 1, 0, 5)
    .map(n -> 10 / n);
```

The consumer can receive `5`, then `10`, and then `onError(ArithmeticException)`. The value from the trailing source element `5` **is not processed**, because `onError` is a terminal signal. There is no `onComplete` afterward.

Proper handling depends on what the error means:

- `doOnError(log::error)` for observation; it does **not** recover the stream.
- `onErrorReturn(fallback)` replaces the error with a single value.
- `onErrorResume(ex -> anotherPublisher)` switches to a fallback publisher when an error occurs.
- `onErrorMap(ex -> new DomainException(...))` transforms the error type for upper layers to handle.
- `onErrorComplete()` intentionally turns an error into **empty completion**; use it carefully so real errors are not hidden.
- `retry(n)` re-subscribes to the source on error; it can repeat side effects, so consider idempotency, error types, and retry limits.

Example:

```java
Mono<String> recovered =
    Mono.<String>error(new IllegalArgumentException("invalid"))
        .onErrorResume(error -> Mono.just("recovered"));
```

The failed source has already **terminated**; `onErrorResume` does not "continue at the next element" in the old source, but instead uses the replacement publisher. Do not confuse re-subscribing in `retry` with fixing the error and resuming at the exact previous position.

A Reactor error signal is different from a business event like `PaymentDeclined` sent via `onNext`. If a system needs to carry both failure and success outcomes within the same stream, design a stateful result type (such as a sealed interface or record), rather than abusing terminal errors for every ordinary business decision.

## 6. Non-Terminating Sequences: No Final Signal Yet

`Mono.never()` and `Flux.never()` **emit no `onNext`, `onComplete`, or `onError`**. The subscriber still receives `onSubscribe`, but without cancellation or a lifecycle-changing operator, the subscription can wait forever. Because there is no terminal signal:

- `defaultIfEmpty` does not run: this operator needs confirmation that the source **completed empty**.
- `switchIfEmpty` does not run because upstream has not completed.
- `onErrorResume` does not run because upstream has not reported an error.
- `doFinally` is not triggered merely because time has passed; it requires complete, error, or cancellation.
- `block()` without a timeout waits forever. Avoid it on the WebFlux event loop and avoid writing tests that can hang.

**Non-terminating does not necessarily mean silent.** `Flux.interval(Duration.ofSeconds(1))` emits `0, 1, 2, ...` steadily and can continue indefinitely; this is a sequence **with data but no terminal signal**. Similarly, `Flux.just(1).concatWith(Flux.never())` emits 1 and then waits forever. Conversely, `Flux.interval(...).take(3)` completes after three elements because `take` actively caps the amount of data.

```text
Flux.never():           ───────────────────────────── (silent, does not complete)
Flux.interval(...):     ──0──1──2──3──4──...         (emits items, does not complete on its own)
Flux.just(1) + never:   ──1────────────────────────── (one item then silent)
Flux.empty():           ──[onComplete]               (completes immediately)
```

In a continuous streaming system (SSE, WebSocket, monitoring), a long-lived stream can be an **intentional design**. What matters is managing connection lifecycles, cancellation, backpressure, heartbeats, and timeouts. `Flux.never()` is an extreme example for testing semantics; it should not be treated as the way to build a real event-listening system.

## 7. Runnable Java 17+ Example: Observing Every Signal

You can run Reactor independently of Spring to see signals clearly. Create a Maven project:

```text
reactor-signals/
├── pom.xml
├── src/main/java/SignalKindsDemo.java
└── src/test/java/SignalKindsTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-signals</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
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
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

This is a consistent set of illustrative versions for a standalone example. In a real Spring Boot application, prefer letting the Spring Boot BOM manage compatible Reactor dependencies.

Contents of `src/main/java/SignalKindsDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SignalKindsDemo {

    public static void main(String[] args) {
        show("EMPTY", Flux.<Integer>empty(), false);
        show("ERROR", Flux.<Integer>error(
            new IllegalStateException("boom")), false);
        show("NEVER", Flux.<Integer>never(), true);

        String emptyFallback = Mono.<String>empty()
            .defaultIfEmpty("empty-fallback")
            .block();

        String errorFallback = Mono.<String>error(
                new IllegalArgumentException("invalid"))
            .onErrorResume(e -> Mono.just("error-fallback"))
            .block();

        String timeoutFallback = Mono.<String>never()
            .timeout(Duration.ofMillis(50))
            .onErrorResume(TimeoutException.class,
                e -> Mono.just("timeout-fallback"))
            .block();

        System.out.println("empty fallback: " + emptyFallback);
        System.out.println("error fallback: " + errorFallback);
        System.out.println("never timeout: " + timeoutFallback);
    }

    private static void show(
            String label, Flux<Integer> source, boolean cancel) {

        System.out.println("== " + label + " ==");

        Disposable subscription = source
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .doOnNext(value ->
                System.out.println("onNext " + value))
            .doOnComplete(() -> System.out.println("onComplete"))
            .doOnError(error ->
                System.out.println("onError "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage()))
            .doOnCancel(() -> System.out.println("onCancel"))
            .subscribe(
                value -> { },
                error -> { },
                () -> { }
            );

        if (cancel) {
            subscription.dispose();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=SignalKindsDemo
```

Expected stdout from the program itself:

```text
== EMPTY ==
onSubscribe
onComplete
== ERROR ==
onSubscribe
onError IllegalStateException: boom
== NEVER ==
onSubscribe
onCancel
empty fallback: empty-fallback
error fallback: error-fallback
never timeout: timeout-fallback
```

How to read the results:

1. **EMPTY:** subscribed successfully and completed immediately. Without `onNext`, the empty fallback activates.
2. **ERROR:** received `onError` right after subscribing. `onComplete` is not called; the error recovery branch produces the replacement value.
3. **NEVER:** only `onSubscribe` occurs. `show` proactively calls `dispose()` so `doOnCancel` runs; without cancellation, this source does not emit a termination on its own.
4. With `Mono.never().timeout(...)`, the timeout operator emits a `TimeoutException` when the deadline expires, and `onErrorResume` turns that error into the value `timeout-fallback`. The fallback does not come from the raw `Mono.never()`.
5. `block()` is only used in the demonstration `main` method, outside any reactive server path. Never use `block()`/`blockLast()` inside a controller or code running on the Spring WebFlux event loop.

Code using `Flux.never()` **does not create a waiting scheduler by itself**; the example itself proactively cancels right after subscribing. For a publisher holding a socket, subscription, or timer, cancelling is also an important step to release resources.

## 8. Rules for Choosing Operators by Signal

Different operators react to **different conditions**:

| Upstream Situation | Suitable Operator | Trigger Condition | Desired Outcome |
| --- | --- | --- | --- |
| No records, completes normally | `defaultIfEmpty(value)` | `onComplete` with 0 elements | Emit default value |
| No records, need to query another source | `switchIfEmpty(otherPublisher)` | `onComplete` with 0 elements | Subscribe to fallback source |
| Recoverable error occurs | `onErrorResume(handler)` | `onError` | Switch to fallback publisher |
| Want to replace error with fixed value | `onErrorReturn(value)` | `onError` | Emit value and complete |
| No new signal in time | `timeout(duration)` | Operator deadline exceeded | Emit `TimeoutException` |
| Timed out, want to switch to fallback data | `timeout(duration, fallback)` | Deadline exceeded | Switch to fallback publisher |
| Need to bound an infinite stream | `take(n)` | `n` elements emitted | Downstream completes, cancels upstream |
| Client no longer interested | `cancel()` / `dispose()` | Action from subscriber | Stop subscription; no terminal signal sent to subscriber |

Comparing three easily confused statements:

```java
Mono<String> a = Mono.<String>empty()
    .switchIfEmpty(Mono.just("A")); // "A"

Mono<String> b = Mono.<String>error(
        new IllegalStateException("failure"))
    .onErrorResume(e -> Mono.just("B")); // "B"

Mono<String> c = Mono.<String>never()
    .timeout(Duration.ofMillis(100),
             Mono.just("C")); // "C" after timeout
```

The result comments here describe the values received by a subscriber; the statements only **create publishers** until subscribed to.

Do not write `Mono.never().switchIfEmpty(...)` expecting the fallback to run, because there is no completion to confirm emptiness. Also do not write `Mono.never().onErrorResume(...)` expecting an error to arise by itself. To bound wait time, add `timeout` or a cancellation mechanism from the subscriber/transport side. The timeout duration must match the stream's characteristics; for long-lived SSE, valid silent intervals can be long and require heartbeats.

### Note on Request and Backpressure

A subscriber may have called `request(n)` and still **receive no elements**: upstream is empty, waiting on I/O, has no data yet, or is `never`. Conversely, upstream may have data but has to wait for demand if downstream has not requested yet. **Merely observing a silent period is not enough to infer whether a stream is empty, error, or never**; you must wait for a terminal signal, error, timeout, or inspect the source's design itself.

## 9. Distinguishing "No Data Yet" from "Completed Empty" in an Operator Chain

Operator ordering affects the meaning of the result.

### Filtering Out All Elements

```java
Mono<Integer> result = Mono.just(3)
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(0);
// Upon subscribe, the result is 0.
```

The value 3 fails the filter, so downstream of `filter` receives an empty completion; `defaultIfEmpty` is then triggered. No error occurs.

### Data Before an Error

```java
Flux<Integer> result = Flux.just(10, 0, 5)
    .map(n -> 100 / n)
    .onErrorResume(error -> Flux.just(-1));
// Upon subscribe: onNext(10), onNext(-1), onComplete.
```

Dividing by 0 causes upstream to error; `onErrorResume` replaces the remainder with a publisher emitting -1. The last source element 5 never passes through `map`.

### Emitting One Element Then Waiting Forever

```java
Flux<Integer> result = Flux.just(7)
    .concatWith(Flux.<Integer>never())
    .defaultIfEmpty(0);
// Upon subscribe: onNext(7), then waits; no onComplete.
```

The empty fallback does not trigger because the stream already emitted a value **and** has not terminated. `timeout` can cut off the wait, though in that case it emits an error rather than automatically turning the wait into empty completion.

### Chaining Tasks with then

`Mono<Void>` is very useful for signaling "task completed" without carrying data. For instance, `repository.save(...).then()` (depending on return type) discards the value and completes with no data when upstream succeeds; if upstream errors, the error propagates; if upstream does not complete, `then()` cannot complete on its own either. With `thenReturn(value)`, `value` is emitted only when upstream **completes successfully**.

One thing to remember when using `zip`/`zipWith`: combining data requires a value from each source. If one source completes empty before emitting a value, the zipped result may complete empty without producing a tuple; an empty source cannot be treated as a `null` value for zipping.

## 10. Application in Spring WebFlux: HTTP Requires Proper Status Mapping

Consider an account lookup API. A reactive repository may return:

- `Mono.just(account)` if found;
- `Mono.empty()` if not found;
- `Mono.error(ex)` if the query fails;
- a publisher with no terminal signal if the operation hangs or a mock is written with `Mono.never()`.

Those are four **distinct** states. A typical HTTP API needs to turn "not found" into **404 Not Found**, infrastructure errors into appropriate error responses, and excessive waiting into a policy-driven timeout. **Returning `Mono.empty()` from a controller does not implicitly mean 404.**

The controller example below is a snippet inside a Spring WebFlux application that already defines `AccountService` and `AccountDto`; this is **not a standalone Java program**, as the service/DTO types must be declared by the application:

```java
import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<AccountDto>> find(
            @PathVariable String id) {

        return service.findById(id)
            .timeout(Duration.ofSeconds(3))
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

If the service completes empty, `defaultIfEmpty` returns a **404** response. If the service emits an error, the error propagates to WebFlux's exception handling mechanism (specific HTTP error policy configured by the application). If three seconds pass without an appropriate signal, `timeout` produces a timeout error, **not an automatic 404**. The application can map that timeout error to 504 Gateway Timeout or an appropriate status per API role and policy; it should not be treated as "account does not exist".

To be truly non-blocking, `service.findById` must use a non-blocking I/O source, or isolate any blocking code in a controlled manner. Merely returning `Mono` does not automatically make synchronous JDBC or `Thread.sleep` calls non-blocking.

With SSE/WebSocket, a long-lived stream without a terminal signal can be valid for the entire duration of the client subscription. The server must manage client disconnect → cancellation, stream errors → retry/reconnect policy, and silent gaps → sensible heartbeats/timeouts. A connection that has not sent an event yet does not mean "empty"; only when a stream completes with no data is it called "empty" under Reactor semantics.

## 11. Testing All Three Outcomes Properly with StepVerifier

Reactive tests need to verify the **final signal**, not just printed values. With `reactor-test` and JUnit in `pom.xml` above, create `src/test/java/SignalKindsTest.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SignalKindsTest {

    @Test
    void emptyCompletesWithoutValue() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }

    @Test
    void errorTerminatesInsteadOfCompleting() {
        StepVerifier.create(Flux.<Integer>error(
                new IllegalStateException("boom")))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void neverEmitsNothingUntilCancelled() {
        StepVerifier.create(Flux.<Integer>never())
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(50))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void timeoutCanRecoverFromNever() {
        Mono<String> source = Mono.<String>never()
            .timeout(Duration.ofMillis(30))
            .onErrorResume(TimeoutException.class,
                e -> Mono.just("fallback"));

        StepVerifier.create(source)
            .expectNext("fallback")
            .verifyComplete();
    }
}
```

Run:

```bash
mvn -q test
```

Maven exits with code **0** when all four tests pass; using `-q` means no separate application stdout is normally needed. The `neverEmitsNothingUntilCancelled` test uses `expectNoEvent` to verify the silent interval and `thenCancel` to end in a controlled manner. Simply calling `verifyComplete()` on `Flux.never()` would make the test wait forever unless an external timeout exists. The timeout test shows that the error signal is **generated by the timeout operator**, and the fallback then handles that error.

In real-world tests, when verifying time-based streams such as `Flux.interval` or multiple timers, consider `StepVerifier.withVirtualTime(...)` to control virtual time and reduce wait duration. When using virtual time, construct the publisher lazily inside the supplier so the virtual scheduler is applied properly.

## 12. Common Mistakes

1. **"No `onNext` means empty."** False: `error` and `never` can also have no `onNext`. You must inspect the terminal signal.
2. **"After `onError`, `onComplete` can still happen."** False: each subscription ends with one kind of terminal signal. You can handle the error with a fallback publisher, but that is a new execution path.
3. **"`defaultIfEmpty` rescues a hanging operation."** False: it only handles cases where upstream completes without data.
4. **"`onErrorResume` runs automatically when no value arrives for too long."** False: an error signal is required, such as from `timeout`.
5. **"`Flux.never()` is the same as `Flux.interval(...)`."** False: one is completely silent; the other keeps emitting elements over time.
6. **"Record not found and database timeout are both 404."** False: a missing record is an empty result that can map to 404; a timeout is a timing/service-quality error that must be handled separately.
7. **"Cancel is the same as complete."** False: `cancel()` is subscriber control; upstream can be cancelled, while downstream does not receive an extra `onComplete` simply from cancelling.
8. **"`block()` can be used anywhere to check whether a publisher has data."** False: on a never source it can hang; on a reactive server it can block the event loop. In non-server demos, if blocking is unavoidable, set an appropriate timeout.
9. **"`onErrorComplete()` is always harmless."** False: it turns errors into empty success and can mask infrastructure failures.
10. **"A `Mono<Void>` with no elements means it did no work."** False: a successfully completed operation can intentionally emit only completion, such as writing data followed by `then()`.
11. **"Non-terminating sources need no management."** False: real streams must handle cancellation, closed connections, timeouts, backpressure, and resources.

## 13. Practice Scenarios and Answers

**Exercise 1.** What does `Mono.<String>empty().defaultIfEmpty("guest")` emit?  
**Answer:** Upon subscription, it emits `guest` and then completes. Because the empty source **sent `onComplete`**, the fallback runs.

**Exercise 2.** What does `Mono.<String>error(new RuntimeException()).defaultIfEmpty("guest")` emit?  
**Answer:** `onError`, without emitting `guest`. To recover from errors, use `onErrorResume`/`onErrorReturn` per policy.

**Exercise 3.** Does `Mono.<String>never().switchIfEmpty(Mono.just("guest"))` complete?  
**Answer:** No, unless there is a timeout/cancel or other intervention. Upstream never sends `onComplete`, so the fallback is never triggered.

**Exercise 4.** What does `Flux.just("A").concatWith(Flux.never())` receive?  
**Answer:** It receives `A` and then waits with no terminal signal. It is **different** from `Flux.empty()` and different from `Flux.just("A")` completing normally.

**Exercise 5.** A repository returns `Mono.empty()` because the ID does not exist; another time it returns `Mono.error(new TimeoutException())` because the database is slow. Do the two cases carry the same HTTP meaning?  
**Answer:** No. The first case can map to 404; the second is an access/timing error that needs timeout and error-mapping policies.

**Exercise 6.** After `Flux.interval(Duration.ofMillis(100)).take(3)`, does downstream receive `onComplete`?  
**Answer:** Yes, after three elements. `take(3)` bounds the stream and typically cancels upstream to stop further emissions.

**Exercise 7.** Why is `StepVerifier.create(Flux.never()).verifyComplete()` not a good test?  
**Answer:** Because the publisher has no terminal signal; verification may wait forever. Use `expectNoEvent`, `thenCancel`, and/or a verification timeout.

## 14. Pipeline Design Checklist

When reviewing a `Mono` or `Flux`, ask yourself four questions:

1. **Can it be empty?** If yes, is empty a valid business success case, or should it return 404, a default value, or a fallback source?
2. **Can it error?** Which errors should be handled, which should propagate to HTTP, and which are safe to retry?
3. **Can it run long or hang?** Where are timeouts, heartbeats, cancellation, and resource limits placed?
4. **Who subscribes and who cancels?** In a Spring WebFlux handler, normally return the publisher for the framework to manage subscription; do not call `subscribe()` arbitrarily and discard the request lifecycle.

The three sources `empty`, `error`, and `never` are minimal tools for testing signal-handling logic. In practice, a pipeline can emit data before failing or stay silent indefinitely; to determine the state accurately, you must look at the **entire signal sequence**, not just the number of elements received.

### References

- Project Reactor, [Reactor Core Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Javadoc: Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) and [Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
