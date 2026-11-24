# Mono<Void> Represents Completion Without Carrying Data

In **Project Reactor** and **Spring WebFlux**, `Mono<Void>` is a `Mono` used to signal that **an operation has completed successfully or failed**, while **providing no result value to the subscriber**. This type is especially useful for write commands, deletions, resource cleanup, HTTP completion signals, or executing a chain of operations where the caller only needs to know when everything has finished.

Key point: **"no data" does not mean "no work is performed".** A `Mono<Void>` can still represent asynchronous I/O, coordinated tasks, errors, and subscription cancellation.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `Mono<Void>`, `Mono.empty()`, `Mono<T>`, `Mono.never()`, and Java's `void`.
- Explain the signals `onSubscribe`, `onComplete`, `onError`, and `cancel`; understand why a successful `Mono<Void>` has no `onNext`.
- Create `Mono<Void>` using `Mono.empty()`, `Mono.fromRunnable(...)`, or `then()` and understand when the task actually executes.
- Combine sequential work with `then`, `thenEmpty`, and `thenReturn`; combine multiple sources when only completion matters using `Mono.when`.
- Use `Mono<Void>` properly in Spring WebFlux, handle errors, observe streams, and test completion with `StepVerifier`.

## 2. Signal Protocol: Completion Without Carrying a Value

`Mono<T>` can emit **at most one** element of type `T`, then complete; it can also complete without emitting an element or terminate with an error. The two basic success paths are:

~~~text
Mono<T> with data:
onSubscribe -> onNext(value) -> onComplete

Empty Mono<T>, or successful Mono<Void>:
onSubscribe -> onComplete

Failure path:
onSubscribe -> onError(error)
~~~

By convention, `Mono<Void>` represents the success path **without `onNext`**, meaning no `Void` instance is delivered downstream. Java has `java.lang.Void` but does not let applications instantiate it normally; Reactor also **does not accept `null` as an `onNext` signal**. Therefore:

~~~java
Mono<Void> done = Mono.empty(); // Valid: completes empty.
Mono<Void> invalid = Mono.just(null); // Invalid: throws NullPointerException.
~~~

The line `Mono.just(null)` here **intentionally demonstrates an error** and should not be put into a runnable program. If a Java API returns `null` and you want to treat that as having no element, `Mono.justOrEmpty(nullableValue)` can create an empty Mono; however, `null` **never becomes an emitted element**.

Each signal has a specific meaning:

| Signal | Meaning for `Mono<Void>` |
| --- | --- |
| `onSubscribe(subscription)` | Subscription is established; work may begin depending on the source and scheduler. |
| `onNext(value)` | Absent in a normal successful `Mono<Void>`. |
| `onComplete()` | Work finished successfully, with no data to return. |
| `onError(error)` | Work failed; not followed by `onComplete`. |
| `cancel()` | Subscriber requested to stop; cancellation may release work/resources if the source cooperates, and is not a success signal. |

**Do not infer that every `Mono<Void>` completes.** For example, `Mono.never()` can emit neither data, completion, nor error; an I/O operation can also hang if a timeout is missing. `Mono<Void>` describes the **output type**, not a guarantee of timing or success.

## 3. How Does `Mono<Void>` Differ from `void` and an Empty `Mono<T>`?

| Expression | Type | What the Caller Receives |
| --- | --- | --- |
| `void delete()` | Java `void` | Method finishes the call; no publisher to wait on or compose, unless another API provides a separate mechanism. |
| `Mono<Void> delete()` | Reactor Publisher | Completion or error signal once the publisher is subscribed to; composable with other pipelines. |
| `Mono<String> find()` emitting `"ok"` | `Mono<String>` | One `String` value, then completes. |
| `Mono<String> find()` returning `Mono.empty()` | `Mono<String>` | No value found/no result, then completes (specific meaning defined by the API). |
| `Mono<Void> save()` completes | `Mono<Void>` | Operation completed, with no data value. |
| `Mono<Void> save()` errors | `Mono<Void>` | Receives `onError`, receives no success signal. |

**Subtle point:** Both an empty `Mono<String>` and a successful `Mono<Void>` produce the exact same signal flow: `onComplete` with no `onNext`. The difference lies in the **API contract and business meaning**: `Mono<String>` usually implies a result may exist; `Mono<Void>` tells the caller not to expect a result value.

Do not use `Mono<Void>` to represent "whether saving succeeded or not" via a `true/false` value: when a checkable business status is needed, use `Mono<Boolean>`, `Mono<Result>`, or an explicitly typed response. A successful `Mono<Void>` only confirms that the operation **completed according to the publisher's contract**; it does not by itself guarantee that a transaction committed, data is durable, or a third party acknowledged it, unless those guarantees belong to the source API.

## 4. Runnable Example with Java 17 and Reactor

Create a small Gradle project consisting of the following two files. **`Mono.fromRunnable`** wraps a `Runnable` that returns no value into a `Mono<Void>`; the action executes upon subscription. **`then`** chains the next task after the previous task completes successfully.

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'MonoVoidDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/main/java/MonoVoidDemo.java`:

~~~java
import reactor.core.publisher.Mono;

public class MonoVoidDemo {
    public static void main(String[] args) {
        Mono<Void> save = Mono.fromRunnable(
            () -> System.out.println("Saved")
        );
        Mono<Void> audit = Mono.fromRunnable(
            () -> System.out.println("Audit recorded")
        );

        Mono<Void> process = save
            .then(audit)
            .doOnNext(value -> System.out.println("onNext: " + value))
            .doOnSuccess(value -> System.out.println("doOnSuccess: " + value));

        System.out.println("Pipeline created");

        process.subscribe(
            value -> System.out.println("Subscriber onNext: " + value),
            error -> System.out.println("Subscriber onError: " + error),
            () -> System.out.println("Subscriber onComplete")
        );
    }
}
~~~

Run `gradle run` (or `./gradlew run` if the project has a Gradle Wrapper; on Windows use `gradlew.bat run`). Stdout from **the program itself**, excluding Gradle logs:

~~~text
Pipeline created
Saved
Audit recorded
doOnSuccess: null
Subscriber onComplete
~~~

**Why do these exact lines appear?**

1. When constructing `save`, `audit`, and `process`, `Mono.fromRunnable` has not executed yet; therefore the first log line is "Pipeline created".
2. `subscribe` triggers the synchronous pipeline in the example. `save` completes, and only then does `audit` execute.
3. `doOnNext` and the `onNext` callback inside `subscribe` **are not invoked**, because no value is emitted.
4. Reactor's `doOnSuccess` is invoked when the `Mono` succeeds. For an empty `Mono`, this callback's argument is **`null` to indicate no value**, even though there is no `onNext(null)` event.
5. Finally, the subscriber receives `onComplete`. In this example the synchronous actions execute directly on the thread calling `subscribe`; using `Mono<Void>` by itself does not create a new thread.

**Note on dependencies:** the example specifies a Reactor version explicitly to run standalone. In Spring Boot, let the Spring Boot BOM manage compatible Reactor versions instead of pinning a separate version as shown here.

## 5. Ways to Create `Mono<Void>`

### 5.1. Complete Immediately Without Doing Anything: `Mono.empty()`

~~~java
Mono<Void> ready = Mono.empty();
~~~

This is a prebuilt empty success signal. Do not confuse it with "the save task has finished": if the required operation has not actually been performed, returning `Mono.empty()` can mislead the caller into believing the work is done.

### 5.2. Wrapping Synchronous Work: `Mono.fromRunnable`

~~~java
Mono<Void> cleanup = Mono.fromRunnable(
    () -> System.out.println("Closing temporary resources")
);
~~~

The action starts upon subscription. If the `Runnable` throws an exception, the exception becomes an `onError` signal. Do not put long blocking I/O directly onto the WebFlux event loop; choose reactive integrations or an appropriate scheduler with resource limits.

### 5.3. Converting a Data-Bearing Publisher to Completion-Only: `then()`

~~~java
Mono<Void> done = Mono.just("payload")
    .doOnNext(text -> System.out.println("Processing " + text))
    .then();
~~~

`then()` **ignores downstream `onNext` results**, waits for upstream to complete successfully, and then emits `onComplete`; if upstream errors, downstream receives the error. `then()` **does not cancel upstream execution**. With `Flux<T>`, `then()` also waits for the entire source to complete, so applying it to an infinite stream will not produce completion on its own.

### 5.4. Converting an Asynchronous Task's Signal to `Mono<Void>`

~~~java
Mono<Void> doneLater = Mono.delay(
    java.time.Duration.ofMillis(100)
).then();
~~~

`Mono.delay(...)` emits a `Long` value after a specified duration; `then()` discards this value and keeps only completion. This illustrates signal control, **not a way to wait for real I/O**.

## 6. Chaining Multiple Tasks Properly

When task A must finish before task B, use `then`:

~~~java
Mono<Void> stepA = Mono.fromRunnable(
    () -> System.out.println("A done")
);
Mono<Void> stepB = Mono.fromRunnable(
    () -> System.out.println("B done")
);

Mono<Void> sequential = stepA.then(stepB);
~~~

`stepB` is subscribed to only after `stepA` completes **successfully**. If `stepA` errors, `stepB` is not executed along this path.

To switch to a publisher **with a value** after completion:

~~~java
Mono<String> result = stepA.thenReturn("OK");
// "OK" is emitted only after stepA completes successfully.
~~~

Or switch to a pre-created/dynamically determined publisher:

~~~java
Mono<String> result = stepA.then(Mono.just("OK"));
~~~

With a completion-only publisher:

~~~java
Mono<Void> full = stepA.thenEmpty(stepB);
~~~

`thenEmpty(Publisher<Void>)` waits for upstream to complete and then waits for the next publisher to complete, still emitting no value. When both are typed as `Mono<Void>`, `stepA.then(stepB)` is also easy to read.

If two tasks are **order-independent** and you only need to know when both finish:

~~~java
Mono<Void> both = Mono.when(stepA, stepB);
~~~

`Mono.when` subscribes to the participating sources, completes when **all** sources complete successfully, and by default signals an error when one source fails (potentially cancelling the remaining sources). It **does not guarantee that two synchronous Runnables run on two threads**; true parallelism depends on the asynchronous nature/scheduler of each source. If you need to wait for all sources to finish before aggregating errors, look into `Mono.whenDelayError`.

**Do not use `Mono.zip(stepA, stepB)` to wait for two `Mono<Void>` instances.** `zip` requires each source to emit **one value** to combine; when a source completes empty, zip has no pair of values to produce a result and may complete early/cancel the other sources. To wait for completion, use `when`, or establish explicit ordering with `then`.

## 7. Common Traps When Using Data-Dependent Operators

Because a successful `Mono<Void>` emits no elements, operators that only execute on `onNext` will not run their callbacks:

~~~java
Mono<Void> task = Mono.fromRunnable(
    () -> System.out.println("Task runs")
);

// The action inside flatMap does NOT run when task succeeds empty:
Mono<String> wrong = task.flatMap(ignored -> Mono.just("next"));

// Execute after task completes:
Mono<String> correct = task.thenReturn("next");
~~~

Similarly:

- `map(...)`, `filter(...)`, `flatMap(...)`, and `doOnNext(...)` wait for an element; if upstream is empty, the corresponding callback does not run.
- `doOnSuccess(value -> ...)` **does run** when the `Mono` completes successfully; `value == null` for the empty case. Do not use this callback to pretend a `Void` value was emitted.
- `doOnTerminate(...)` can observe successful completion or error; `doFinally(signalType -> ...)` also observes cancellation. These are observation hooks and do not replace pipeline propagation.
- `switchIfEmpty(fallback)` is triggered when upstream **emits no value**. Because a successful `Mono<Void>` is inherently empty, using `switchIfEmpty` after a `Mono<Void>` typically triggers the fallback **even when the first task succeeded**. If you want to run the next task after completion, use `then` or `thenEmpty`.
- `defaultIfEmpty(value)` requires a valid value to emit. You cannot use `null` as a "default value" in Reactor, and `Mono<Void>` is not meant to carry default data. Use `thenReturn(result)` when you need to return a value after success.

Example illustrating the `switchIfEmpty` trap:

~~~java
Mono<Void> saved = Mono.fromRunnable(
    () -> System.out.println("Saved")
);

Mono<Void> surprising = saved.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("Fallback also runs")
    )
);
~~~

If you subscribe to `surprising`, **both** lines can be printed in the order above, because `saved` completes without `onNext`. Do not confuse empty completion with a failed result. To handle errors, use `onErrorResume` or a clearly defined error policy.

## 8. Error Handling, Cancellation, and Timeouts

`Mono<Void>` still has full error propagation capabilities:

~~~java
Mono<Void> task = Mono.fromRunnable(() -> {
    throw new IllegalStateException("Unable to save");
});

Mono<Void> logged = task.doOnError(error ->
    System.err.println("Error: " + error.getMessage())
);
~~~

`doOnError` only observes; it **does not swallow the error**. Downstream still receives `onError`. If a valid fallback exists:

~~~java
Mono<Void> recovered = task.onErrorResume(error -> {
    System.err.println("Applying recovery policy: " + error);
    return Mono.empty();
});
~~~

After recovery, the pipeline completes successfully. This approach **intentionally converts an error into success**, so it is only appropriate when business rules allow it; do not overuse it for errors that must be reported to the client. If you want to preserve the error after logging, only use `doOnError` or return `Mono.error(error)` in the recovery branch.

For tasks that may not terminate:

~~~java
Mono<Void> bounded = someOperation
    .timeout(java.time.Duration.ofSeconds(5));
~~~

In the example above, `someOperation` is an existing `Mono<Void>` variable from the system (an integration snippet, not a standalone program). `timeout` converts exceeding the deadline into an error and cancels upstream according to the operator's contract; whether physical I/O can be interrupted depends on the source/driver. `cancel()` is also a cooperative signal: you cannot assume by default that external side effects already executed will be rolled back.

An action can complete successfully, error, or be cancelled; **cancellation is not equivalent to `onComplete`**. When cleanup is needed, consider `doFinally`, `usingWhen`, or an appropriate resource-management API, and test success/error/cancel paths in your tests.

## 9. `Mono<Void>` in Spring WebFlux

### 9.1. Endpoint Returning 204 No Content After Deletion

Many Spring Data Reactive interfaces, such as `ReactiveCrudRepository.deleteById(...)`, return `Mono<Void>`: the caller cares that the deletion finished, without needing an object as the response body.

This is an **integration snippet inside an existing Spring Boot WebFlux application**, where `accountRepository` is a declared and injected reactive repository:

~~~java
@DeleteMapping("/accounts/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> deleteAccount(@PathVariable String id) {
    return accountRepository.deleteById(id);
}
~~~

Corresponding imports:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;
import reactor.core.publisher.Mono;
~~~

When the controller **returns the publisher to WebFlux**, the framework is responsible for subscribing, waiting for completion, and finalizing the HTTP response; if the publisher errors, the error flows through WebFlux's exception handling mechanism. `@ResponseStatus(HttpStatus.NO_CONTENT)` sets status **204**; **`Mono<Void>` by itself does not mean status 204**. The example code does not check whether the record exists first; if business logic needs to distinguish "not found" from "deleted", add a lookup step and map to an HTTP 404 error per API convention.

**Do not call `.subscribe()` inside a controller and return `Mono.empty()` immediately.** Doing so detaches the work from the HTTP lifecycle, allowing the response to finish before the write/delete completes; errors, timeouts, and cancellation also become difficult to propagate properly.

### 9.2. Filter Chains and Response Completion

In WebFlux, `WebFilterChain.filter(exchange)` returns `Mono<Void>`, representing that request processing through the chain has finished. `ServerHttpResponse.setComplete()` also returns `Mono<Void>`, letting the framework know when response completion finishes. Here, the **completion signal** matters more than a returned object.

*Conceptual* example inside a `WebFilter`:

~~~java
@Override
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    return chain.filter(exchange)
        .doFinally(signal -> recordCompletion(signal));
}
~~~

The snippet above requires the class and `recordCompletion` method to be defined by the application; it is not a standalone runnable Java file. `doFinally` observes completion, error, and cancellation alike. Instrumentation hooks should be fast and safe; do not perform blocking I/O directly inside an event-loop callback.

### 9.3. WebClient When You Only Need to Know the Request Completed

With a configured `WebClient`, you can write:

~~~java
Mono<Void> finished = webClient.post()
    .uri("/notifications")
    .bodyValue(new Notification("hello"))
    .retrieve()
    .toBodilessEntity()
    .then();
~~~

This is an integration snippet requiring `Notification` and `webClient` to be declared in the application. `toBodilessEntity()` produces `Mono<ResponseEntity<Void>>` (allowing status/headers to be read), and `then()` intentionally discards the response entity value to keep only the completion/error signal. If you need to inspect success status codes under business rules, **keep `ResponseEntity<Void>` to handle it before calling `then()`**. With `retrieve()`, HTTP 4xx/5xx error responses are converted to Reactor errors by default unless reconfigured.

## 10. Testing Completion, Errors, and Side-Effect Timing

The `reactor-test` library provides `StepVerifier` to verify exact signals rather than guessing from sleep durations or logs. The test dependency is already in `build.gradle` in section 4.

Create `src/test/java/MonoVoidTest.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MonoVoidTest {
    @Test
    void runsOnSubscriptionAndCompletesWithoutItem() {
        AtomicInteger counter = new AtomicInteger();
        Mono<Void> operation = Mono.fromRunnable(
            counter::incrementAndGet
        );

        assertEquals(0, counter.get()); // Not subscribed yet.

        StepVerifier.create(operation)
            .verifyComplete();          // No expectNext.

        assertEquals(1, counter.get()); // Executed exactly once.
    }

    @Test
    void failureDoesNotCompleteSuccessfully() {
        Mono<Void> operation = Mono.fromRunnable(() -> {
            throw new IllegalStateException("failed");
        });

        StepVerifier.create(operation)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "failed".equals(error.getMessage()))
            .verify();
    }

    @Test
    void thenReturnEmitsValueAfterCompletion() {
        Mono<String> operation = Mono.<Void>empty()
            .thenReturn("OK");

        StepVerifier.create(operation)
            .expectNext("OK")
            .verifyComplete();
    }
}
~~~

Run `gradle test` (or the corresponding Gradle Wrapper command). All three tests are expected to **PASS**:

- `Mono<Void>` completes without `expectNext`, and the side effect only runs after subscription.
- An exception inside `Runnable` is converted into `onError`.
- `thenReturn` lets you transition from completion-only to a value-emitting publisher.

You can verify completion independent of the number of requested elements with `StepVerifier.create(Mono.<Void>empty(), 0).verifyComplete()`: `onComplete` is not an `onNext`, so it consumes no demand. However, an arbitrary publisher's work may still require demand to make progress; for example, `Flux.range(...).then()` must consume the source before completing.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `Mono.just(null)` to "return Void" | `NullPointerException`; Reactor forbids emitting `null`. | Use `Mono.empty()`, `Mono.fromRunnable(...)`, or `then()`. |
| Using `flatMap` after `Mono<Void>` to run the next task | Callback does not run because there is no `onNext`. | Use `then(nextMono)` or `thenEmpty(nextPublisher)`. |
| Using `Mono.zip` to wait on multiple `Mono<Void>` | No values to combine; may complete early. | Use `Mono.when` for multiple completion-only sources. |
| Treating `doOnSuccess(null)` as emitting a null element | Misunderstands the protocol, causing broken check logic. | Recognize this as the success callback on an empty Mono. |
| Using `switchIfEmpty` to "run when the operation fails" | Fallback is called even after `Mono<Void>` completes successfully. | Use `onErrorResume` for errors; `then` for follow-up work. |
| Calling `subscribe` manually in service/controller and returning `Mono.empty()` | Loses error handling, completion waiting, and cancellation chain. | Return the `Mono<Void>` pipeline so WebFlux subscribes and manages it. |
| Assuming `Mono<Void>` always means HTTP 204 | HTTP status is decided by the controller/response. | Set `@ResponseStatus(NO_CONTENT)` or an appropriate `ResponseEntity`. |
| Calling `block()` on a WebFlux processing thread | Can block the event loop and break reactivity. | Return the publisher from the handler; use composable reactive APIs. |
| Testing only "does not throw an exception" | Misses subscription, completion, error, and cleanup behavior. | Use `StepVerifier.verifyComplete()`, `expectError...`, and verify side effects. |

## 12. API Design Principles with `Mono<Void>`

Choose `Mono<Void>` when the question the caller needs answered is: **"When does this finish, or why did it fail?"** Examples include deletes, writes, command dispatches, or closing a response without needing to return data. When the caller also needs the affected row count, a business confirmation code, a new ID, or an updated version, choose `Mono<Long>`, `Mono<Id>`, `Mono<UpdateResult>`, or an appropriate result type.

When building a pipeline, check in order:

1. **Is there a real side effect?** Construct the proper publisher describing the work; do not return `Mono.empty()` before the work is composed into the pipeline.
2. **Who subscribes?** In WebFlux, the framework is typically the final subscriber; in tests, use `StepVerifier`. Avoid subscribing internally and losing errors/completion.
3. **Need a value or only completion?** Use `map/flatMap` for value-producing sources; use `then/when` for completion-only flows.
4. **Where do errors go?** Preserve `onError` if the caller needs to know about failures; recover only when business rules permit.
5. **Can the task be cancelled or hang too long?** Configure timeouts, cleanup, and test cancel/error paths with appropriate sources.

**Key Takeaway:** `Mono<Void>` is a **publisher of a completion signal**, not "a `Mono` that emits a `Void` object". Empty success is expressed with `onComplete`; failure with `onError`. To chain work after completion, use `then`; to wait on multiple completion-only tasks, use `when`.

## References

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor `Mono` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
