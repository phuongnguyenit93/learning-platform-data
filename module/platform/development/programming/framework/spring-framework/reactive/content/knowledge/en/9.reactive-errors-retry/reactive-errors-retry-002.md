# onErrorReturn and Fixed Fallback Values

**Module:** Spring Framework – reactive  
**Parent topic:** Errors and retry

## Learning Objectives

After this lesson, you will be able to:

1. Explain accurately how `onErrorReturn` turns a terminal error signal into **a fixed fallback value** and then completes successfully for `Mono` and `Flux`.
2. Use overloads taking a direct value, an exception class, or a `Predicate<Throwable>` to restrict which errors are allowed to be replaced.
3. Distinguish `onErrorReturn` from `defaultIfEmpty`, `switchIfEmpty`, `onErrorResume`, `onErrorComplete`, `onErrorMap`, and `retry`.
4. Predict what data is still emitted when a `Flux` emits some elements and then encounters an error; understand why subsequent elements after the error are not automatically processed.
5. Choose a business-appropriate fallback value, preserve error observability, and avoid turning serious incidents into misleading success responses in Spring WebFlux.
6. Write and run a Java 17+ example covering success, matching error, non-matching error, and empty publisher cases.

## 1. When Do You Need a Fallback Value?

Suppose an application displays temperature from a sensor. When sensor data cannot be retrieved due to a known error, the screen may need a fallback value or an explicit status like `"unavailable"`. However, if an error occurs while processing payments or authorization, silently turning it into a "successful" result can have serious consequences.

In Reactive Streams, a publisher has three basic signal types:

- `onNext(value)`: emits a data value.
- `onComplete()`: completes successfully, emitting no more values.
- `onError(error)`: terminates with an error, emitting no further `onNext` or `onComplete` from that subscription.

A `Mono<T>` emits at most one element; a `Flux<T>` can emit multiple elements. Both have Project Reactor's `onErrorReturn` operator.

**`onErrorReturn(fallback)`** is placed after a section of the pipeline to *intercept an error from upstream*, emit a `fallback` value in place of the error signal, and then emit `onComplete`. It **does not fix the root cause of the error**, does not re-run the source, and is not a promise that fallback data is equivalent to real data.

Diagram for a `Flux`:

```text
Upstream:
  onNext(10) -> onNext(20) -> onError(TimeoutException)
                                  |
                                  v
                     onErrorReturn(-1)
                                  |
Downstream:
  onNext(10) -> onNext(20) -> onNext(-1) -> onComplete()
```

If upstream emits `onComplete` normally, the operator simply forwards the completion and **does not add** `fallback`. If upstream emits `Mono.empty()`, the operator still completes empty. Only **a matching error** triggers the fallback value.

## 2. Contract of onErrorReturn

Basic form:

```java
Mono<T> recoveredMono = sourceMono.onErrorReturn(fallbackValue);
Flux<T> recoveredFlux = sourceFlux.onErrorReturn(fallbackValue);
```

This is **illustrative syntax**: `sourceMono`, `sourceFlux`, and `fallbackValue` must share the appropriate data type. There are three common forms:

| Form | When is the error replaced? | Example |
| --- | --- | --- |
| `onErrorReturn(T fallbackValue)` | Any upstream error | `mono.onErrorReturn("N/A")` |
| `onErrorReturn(Class<E> exceptionType, T fallbackValue)` | Error of the specified exception type | `mono.onErrorReturn(TimeoutException.class, cachedValue)` |
| `onErrorReturn(Predicate<? super Throwable> predicate, T fallbackValue)` | When the predicate returns `true` for the error | `mono.onErrorReturn(e -> isTemporary(e), fallback)` |

The `Class`-based overload checks the exception type, including subtypes of the specified class. A predicate allows more flexible error-selection policies, but must be short, reliable, and non-blocking. If the condition **does not match**, the original error continues downstream to `onError`; `onErrorReturn` is not an unconditional error converter when using conditional overloads.

### 2.1. Case with Mono

```java
Mono<Integer> parsed = Mono.just("invalid")
        .map(Integer::parseInt)
        .onErrorReturn(NumberFormatException.class, -1);
```

This is an **illustrative snippet**. `Integer.parseInt("invalid")` throws `NumberFormatException` inside `map`; Reactor turns the exception into `onError`, `onErrorReturn` catches the matching type and emits `-1`. Downstream sees a single `onNext(-1)` and `onComplete` instead of `onError`.

Conversely:

```java
Mono<Integer> ok = Mono.just("25")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
// The received value is 25; the fallback -1 is not emitted.
```

For a source that has already emitted a value successfully, there is no reason to use the fallback.

### 2.2. Case with Flux: only replaces the failed tail

```java
Flux<Integer> results = Flux.just(6, 3, 0, 2)
        .map(n -> 12 / n)
        .onErrorReturn(-1);
```

When a subscriber requests all data, the logical signal sequence is:

```text
6 -> 12 / 6 -> onNext(2)
3 -> 12 / 3 -> onNext(4)
0 -> 12 / 0 -> onError(ArithmeticException)
     onErrorReturn(-1) -> onNext(-1) -> onComplete()
2 -> not processed in this subscription
```

**Result: `[2, 4, -1]`**, not `[2, 4, -1, 6]`. Once the source has terminated due to an error, `onErrorReturn` does not go back to the old source to "skip the bad element and continue". It transitions from the error path to a final replacement value and then completes.

In applications returning lists, this behavior deserves careful thought: downstream may receive **part real data and one fallback element**. If the API requires an "all or nothing" result, convert with `collectList()` before handling errors; `Mono<List<T>>` only emits the list after the source completes normally.

## 3. Runnable Java 17+ Example

The example below demonstrates every important outcome of `onErrorReturn` without depending on the Spring WebFlux runtime. Uses **Java 17+**, **Maven**, and **Project Reactor Core 3.8.8**.

Create two files:

```text
on-error-return-demo/
├── pom.xml
└── src/main/java/demo/
    └── OnErrorReturnDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>on-error-return-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/OnErrorReturnDemo.java

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OnErrorReturnDemo {
    private static int buildFallback() {
        System.out.println("fallback created");
        return -9;
    }

    public static void main(String[] args) {
        // A. Already emitted values are kept; error is replaced with exactly one element.
        Flux<Integer> numbers = Flux.just(6, 3, 0, 2)
                .map(value -> 12 / value)
                .doOnError(error -> System.out.println(
                        "source error = " + error.getClass().getSimpleName()))
                .onErrorReturn(-1);
        System.out.println("flux = " + numbers.collectList().block());

        // B. Only NumberFormatException is replaced.
        Mono<Integer> valid = Mono.just("12")
                .map(Integer::parseInt)
                .onErrorReturn(NumberFormatException.class, -1);
        Mono<Integer> invalid = Mono.just("abc")
                .map(Integer::parseInt)
                .onErrorReturn(NumberFormatException.class, -1);
        System.out.println("mono valid = " + valid.block());
        System.out.println("mono invalid = " + invalid.block());

        // C. An empty source is not an error.
        Mono<Integer> empty = Mono.<Integer>empty().onErrorReturn(-1);
        System.out.println("empty has value = " + empty.hasElement().block());
        System.out.println("empty default = " +
                Mono.<Integer>empty().defaultIfEmpty(-1).block());

        // D. Non-matching Class error still propagates down to onError.
        Mono<Integer> unmatched = Mono.<Integer>error(
                        new IllegalStateException("service down"))
                .onErrorReturn(IllegalArgumentException.class, 99);
        try {
            unmatched.block();
        } catch (IllegalStateException error) {
            System.out.println("unmatched = " +
                    error.getClass().getSimpleName());
        }

        // E. Predicate selects the right error type.
        Mono<Integer> predicate = Mono.<Integer>error(
                        new IllegalStateException("temporary"))
                .onErrorReturn(
                        error -> error instanceof IllegalStateException,
                        0);
        System.out.println("predicate fallback = " + predicate.block());

        // F. Fallback argument is evaluated immediately at pipeline assembly time.
        Mono<Integer> alreadySuccessful =
                Mono.just(42).onErrorReturn(buildFallback());
        System.out.println("success = " + alreadySuccessful.block());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OnErrorReturnDemo
```

**Program stdout**, excluding Maven's own logs:

```text
source error = ArithmeticException
flux = [2, 4, -1]
mono valid = 12
mono invalid = -1
empty has value = false
empty default = -1
unmatched = IllegalStateException
predicate fallback = 0
fallback created
success = 42
```

Points to verify:

1. `doOnError` placed **before** `onErrorReturn` still observes the division-by-zero error. Then the operator replaces the error with `-1`, so `collectList().block()` succeeds and returns `[2, 4, -1]`.
2. `valid.block()` returns 12 because there is no error. `invalid.block()` returns -1 because `NumberFormatException` matches the specified overload.
3. `Mono.empty()` completes normally without a value, so `onErrorReturn` does not trigger; `hasElement().block()` is `false`. Meanwhile, `defaultIfEmpty(-1)` handles the missing-element case properly.
4. `IllegalStateException` **does not** match `IllegalArgumentException.class`, so it is thrown at `block()` in the CLI program and printed by the `catch` branch. It is not turned into 99.
5. The predicate receives the actual `Throwable` and returns `true` for `IllegalStateException`, so downstream receives 0.
6. `buildFallback()` is a normal Java call inside the expression `onErrorReturn(buildFallback())`. It runs when **building the pipeline**, printing `fallback created` even though `Mono.just(42)` will succeed. This shows that the "fixed fallback value" has already been evaluated in advance.

**Why is `block()` in the example?** This is `main` of a CLI application, so we intentionally wait for the result to inspect stdout. In a Spring WebFlux controller using nonblocking I/O, avoid `block()`; return `Mono`/`Flux` so the framework manages the subscription.

## 4. What Does "Fixed Fallback Value" Mean?

`onErrorReturn(fallbackValue)` takes an **already-existing `T` object**. This object or expression result is passed into the operator at assembly time. When a matching error occurs, Reactor uses that value as an `onNext` signal. It does not invoke a new supplier to compute the fallback value on each error.

Example:

```java
int fallback = expensiveComputation();  // runs immediately
Mono<Integer> result = source.onErrorReturn(fallback);
```

This is an **illustrative snippet**, where `source` and `expensiveComputation()` are defined by the application. Even if `source` never errors, computing the fallback has already happened. Similarly, passing `new ArrayList<>()` directly creates the list at assembly time; if subscriptions share the chain, that same fallback object could be shared. Therefore, with `onErrorReturn`, **prefer constants, immutable records/value objects, or values that are never mutated**.

### 4.1. When the fallback value must be computed at error time

Use `onErrorResume` to return a new publisher based on the error:

```java
Mono<String> result = source.onErrorResume(error ->
        Mono.fromSupplier(() -> createFallback(error)));
```

This is an **illustrative snippet**: `source` is a `Mono<String>`, and `createFallback(error)` returns a `String` and is defined by the application. The supplier is triggered when the fallback publisher is subscribed to after a matching error. If creating the fallback also fails, the new error can propagate downstream. For simple logic, you can use `onErrorResume(error -> Mono.just(createFallback(error)))`; the `createFallback(error)` expression only runs when the callback is invoked due to an error, though it is not deferred further inside the callback.

**Comparison:**

| Goal | How to write it |
| --- | --- |
| Use a pre-existing immutable value on error | `onErrorReturn(FALLBACK)` |
| Only replace timeout errors, keep other errors | `onErrorReturn(TimeoutException.class, FALLBACK)` |
| Choose different fallbacks based on exception or user | `onErrorResume(error -> ...)` |
| Need another reactive HTTP/database call on error | `onErrorResume(error -> backupService.fetch())` |
| Need to turn an empty completion into a value | `defaultIfEmpty(FALLBACK)` |
| Need to turn an empty completion into a new publisher | `switchIfEmpty(Mono.defer(() -> alternateSource()))` |

`onErrorReturn` is **not** a caching operator. Even if the fallback is a constant, the original source is still subscribed to separately according to its cold/hot semantics. If a cold request always fails, each subscription may still attempt that request before emitting the fallback.

### 4.2. Null cannot be used as a fallback

Reactive Streams does not allow `null` in an `onNext` signal. `onErrorReturn(null)` is not a way to express "on error, emit null" and may be rejected immediately at pipeline assembly. Use a valid value, a status-carrying DTO (such as `unavailable`), or keep the error for the HTTP layer to handle. If an optional value truly does not exist, `Mono.empty()` is a different representation from a fallback.

### 4.3. Fallback and data type must be meaningful

Suppose `Mono<Integer>` returns a valid temperature. Choosing `-1` as a fallback can be confusing if -1 is also a meaningful temperature. It is better to return a type representing status:

```java
record Reading(Integer value, boolean available) {}

Mono<Reading> reading = sensorService.read()
        .map(value -> new Reading(value, true))
        .onErrorReturn(new Reading(null, false));
```

This is an **illustrative snippet**, where `sensorService.read()` returns an application-defined `Mono<Integer>`. `Reading` is not a `null` value emitted through Reactor: the `Reading` object is non-null; the `value` field simply has no data when `available=false`. Real designs can use sealed types, `Optional` inside a DTO, or a dedicated error structure. Do not treat a fallback of 0 or false as "no data" if it can collide with valid business data.

## 5. Where to Place onErrorReturn in the Chain?

The operator only handles errors propagated from **its own upstream**. Placement determines which errors are intercepted, as well as whether values before the error are observed.

### 5.1. Placed after a step that can fail

```java
Flux<Integer> safe = Flux.just("1", "bad")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
```

The snippet above emits 1, then -1, and completes. The upstream `map` emits an error, so the handler sees the error.

### 5.2. Placed before a step that can fail: does not catch downstream errors

```java
Flux<Integer> notProtected = Flux.just(1, 0)
        .onErrorReturn(-1)
        .map(n -> 10 / n);
```

This is an **illustrative snippet**. `onErrorReturn` only protects `Flux.just` in front of it (which does not error); when `map` encounters 0 and throws `ArithmeticException` after the handler, the earlier handler has no chance to process it. To handle division by zero, you must place `onErrorReturn(-1)` **after** `map`.

### 5.3. Logging before replacing the error

```java
Mono<String> visible = remoteService.fetch()
        .doOnError(error -> metrics.record(error))
        .onErrorReturn("temporarily unavailable");
```

This is an **illustrative snippet**, requiring definitions for `remoteService` and `metrics`. `doOnError` observes errors from upstream without replacing or recovering from them. If you put `doOnError` **after** `onErrorReturn`, the callback will **not see the replaced error** because downstream only receives the fallback value and `onComplete`. Track errors before recovery, with informative logs/metrics while avoiding leaking sensitive data.

### 5.4. Position relative to retry: completely different behavior

```java
Mono<String> a = source.retry(2).onErrorReturn("offline");
Mono<String> b = source.onErrorReturn("offline").retry(2);
```

This is an **illustrative snippet**, where `source` is an application-defined `Mono<String>`.

- In `a`, `retry(2)` can re-subscribe to the source up to two times **in addition to the first attempt** after errors. If it still fails after the attempts, `onErrorReturn` emits `"offline"`.
- In `b`, if the error has already been replaced with a normal value by `onErrorReturn`, `retry(2)` downstream **no longer sees that error**, so it does not trigger a retry for that error.

`retry` can repeat network operations, data writes, or side effects. Only retry when the source, idempotency, timeouts, and business policy allow it. If an error is not suitable for retrying, do not add retry just because a fallback exists.

## 6. Comparing onErrorReturn with Easily Confused Operators

| Operator | Triggered by | Typical outcome |
| --- | --- | --- |
| `onErrorReturn(fallback)` | Matching `onError` | Emits **a single fixed value**, then completes. |
| `onErrorResume(error -> publisher)` | Matching `onError` | Switches to a fallback publisher (can emit 0, 1, or many values). |
| `onErrorComplete()` | Matching `onError` | Converts error into `onComplete` **emitting no extra value**. |
| `onErrorMap(error -> mapped)` | `onError` | Changes exception type/message; downstream still receives `onError`. |
| `defaultIfEmpty(defaultValue)` | `onComplete` with no value | Emits a value if the source is empty; **does not** recover from errors. |
| `switchIfEmpty(alternate)` | `onComplete` with no value | Switches to another publisher when empty; does not handle errors by default. |
| `retry(n)` | `onError` | Re-subscribes to the source when allowed; does not create a replacement value itself. |
| `doOnError(action)` | `onError` | Observes the error for logging/metrics; does not replace the error signal itself. |

A concise and accurate way to read it:

```text
source = Mono.just(5)
  .onErrorReturn(-1)     -> 5

source = Mono.empty()
  .onErrorReturn(-1)     -> empty
  .defaultIfEmpty(-1)    -> -1

source = Mono.error(E)
  .onErrorReturn(-1)     -> -1 then complete
  .onErrorComplete()     -> empty complete
  .onErrorResume(e -> Mono.just(10)) -> 10 then complete
```

The lines above are **behavioral diagrams for each individual case**, not standalone copy-paste Java. `onErrorReturn` does not fit every error; if you need to return an HTTP error code, record the failure reason, or preserve retry capability, choose the operator matching the handling contract.

## 7. Caution with a Flux That Already Emitted Partial Data

When a `Flux` emits two values and then errors, `onErrorReturn` appends the fallback **after** those two values (if downstream still has demand). This produces a stream that looks like it completed normally even though the tail may be missing many expected values.

Business data example:

```text
Expected data:     A, B, C, D
Already emitted:   A, B
Error occurs on:   C
onErrorReturn(?):  A, B, FALLBACK, onComplete
```

If a UI accepts a final line such as `"stream interrupted"`, the pattern above can be designed as a dedicated status event type. However, if the client assumes every element is a real `Order`, inserting a fake `Order` at the end of the list can lead to incorrect reporting.

### 7.1. All-or-nothing with collectList()

```java
Mono<List<Item>> all = sourceFlux
        .collectList()
        .onErrorReturn(List.of());
```

This is an **illustrative snippet**, assuming `java.util.List` is imported and the application defines `Item` and `sourceFlux`. `collectList()` only emits the list when the source completes successfully; if upstream emits some Items and then errors, the list has not been emitted yet, the Mono errors, and `onErrorReturn` supplies an empty list. This is **all-or-fallback** behavior, unlike `sourceFlux.onErrorReturn(fallbackItem)`, which emits the Items that arrived before the error.

However, `List.of()` is an **empty** fallback that can be interpreted as "there really are no orders". If connection errors and no-data situations must be distinguished, return a DTO containing `available=false` or keep the error for an appropriate HTTP status.

### 7.2. Backpressure and when fallback is emitted

`onErrorReturn` emits the fallback via `onNext`, so it must honor downstream **demand**. An upstream terminal error does not need demand to be signaled, but a fallback element can only be received by downstream when sufficient demand exists. If downstream has not requested yet or has cancelled, do not assume the fallback value will be observed immediately. Additionally, `onErrorReturn` does not provide backpressure for hot sources or automatically bound buffer sizes in other operators.

### 7.3. Do not turn per-item errors into "continue the old source"

```java
Flux<Integer> parsed = Flux.just("10", "oops", "30")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
```

The result is `10, -1` and then complete; `"30"` is no longer processed in this subscription.

If the contract allows **skipping a bad record individually and continuing**, move error handling into each parse operation:

```java
Flux<Integer> parsed = Flux.just("10", "oops", "30")
        .concatMap(raw ->
                Mono.fromCallable(() -> Integer.parseInt(raw))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty()));
// Result when consumed: 10, 30 then complete.
```

Both snippets above are **illustrative**, using Reactor and Java. `onErrorReturn` is suitable for **replacing the entire error signal** with a fallback value, not a mechanism for skipping individual records and continuing upstream. If you need to keep each error reason for auditing, return a `ParseResult` type containing success/failure status instead of discarding the information.

## 8. Applying in Spring WebFlux

In a WebFlux controller, typically **return `Mono` or `Flux`**. The WebFlux infrastructure and reactive HTTP server consume the publisher and determine the response, errors, and cancellation. Do not call `subscribe()` or `block()` in a handler just to trigger `onErrorReturn`.

### 8.1. Safe fallback values for optional data

Suppose an endpoint displays a secondary informational label; without the label, the UI can still render:

```java
@GetMapping("/display-label")
public Mono<String> displayLabel() {
    return labelService.fetchCurrentLabel()
            .doOnError(error -> logLabelFailure(error))
            .onErrorReturn("temporarily unavailable");
}
```

This is an **illustrative snippet in a Spring controller**, requiring importing `@GetMapping` and application definitions for `labelService`/`logLabelFailure`. If upstream fails, the HTTP handler still has a valid `String` value to encode. By default, the response can be HTTP **200 OK** because the error has been converted into a successful value. This is only reasonable when the endpoint and client **accept** displaying the fallback value.

If the endpoint is actually a payment API, access grant, financial report, or order decision, you should not return a fake "success value" to mask errors. For sensitive decisions, a Boolean fallback of `true` can become an unsafe **fail-open**. Only use fallbacks when semantics and safety policies are clearly defined.

### 8.2. Conditional error-to-value replacement

```java
@GetMapping("/availability")
public Mono<String> availability() {
    return stockService.check()
            .onErrorReturn(
                    java.util.concurrent.TimeoutException.class,
                    "unknown");
}
```

This is an **illustrative snippet**: `stockService.check()` returns `Mono<String>`. A timeout is treated as the `unknown` status, not `in-stock` or `out-of-stock`. Other errors are still reported through WebFlux's error path. You need to check the actual exception emitted by the service: an HTTP client error may be wrapped in another exception instead of `TimeoutException` directly; if the type does not match, the operator does not replace the error.

### 8.3. When an HTTP status other than 200 is needed

If failing to retrieve data is a service error, preserve response semantics using HTTP status:

```java
@GetMapping("/catalog")
public Mono<ResponseEntity<List<String>>> catalog() {
    return catalogService.streamNames()
            .collectList()
            .map(names -> ResponseEntity.ok(names))
            .onErrorResume(
                    java.util.concurrent.TimeoutException.class,
                    error -> Mono.just(
                            ResponseEntity
                                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                                    .body(java.util.Collections.<String>emptyList())));
}
```

This is an **illustrative snippet in a controller**, requiring importing Spring `ResponseEntity`, `HttpStatus`, `Mono`, `List`, and defining `catalogService`. We use `onErrorResume` instead of `onErrorReturn(List.of())` because the goal is to replace both **status and body** on timeout. HTTP 503 clearly signals a service error; the empty body is just an accompanying format, not the business result "there are no products".

Note for a streaming `Flux` with an already-committed response: if an error arrives after the server has sent headers/body, you cannot arbitrarily change the HTTP status to 503. Choosing a fallback, switching to a buffered full response, or defining an error-reporting event must account for streaming behavior and the client's contract.

### 8.4. Empty and not found in APIs

`repository.findById(id)` usually returns `Mono.empty()` when a record is not found; `onErrorReturn` **does not** turn that case into a fallback value or HTTP 404.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Item not found")));
```

This is an **illustrative snippet**, assuming `repository` and `id` exist. `switchIfEmpty` handles missing elements, while `onErrorReturn` handles upstream errors. Do not conflate "not found" with "server/database errored" if the API must distinguish them.

## 9. Choosing Which Errors to Replace: Safe and Maintainable Practices

### 9.1. Catching all errors can hide programming bugs

`source.onErrorReturn(FALLBACK)` will catch unexpected errors like `NullPointerException` or `IllegalStateException` from bugs in the pipeline. This can obscure logic bugs in production. For a business fallback, you should generally specify **which error types are allowed to recover**:

```java
Mono<String> response = service.fetch()
        .onErrorReturn(
                java.util.concurrent.TimeoutException.class,
                "unavailable");
```

This snippet is **illustrative**, requiring `service.fetch()` to return `Mono<String>`. Do not expand the whitelist to authentication errors, security errors, or integrity failures. For wrapped errors, inspect the exception structure and service mapping rather than blindly turning all errors into a fallback.

### 9.2. Retry then fallback, or fallback immediately?

If a transient network error can be retried:

```java
Mono<String> result = service.fetch()
        .retry(2)
        .onErrorReturn("temporarily unavailable");
```

This snippet is **illustrative**: valid when retrying is safe, bounded, and does not repeat dangerous side effects. Two retries plus the initial attempt can become **three subscriptions** to a cold source. For HTTP POST/database writes, evaluate idempotency first. When you need to restrict error types and use backoff, you can use `retryWhen(Retry.backoff(...).filter(...))` along with timeouts/circuit breakers per policy; the simple example above is only meant to illustrate operator ordering.

### 9.3. Observe incidents before recovering

Measure recovered errors instead of letting metrics only see downstream completion:

```java
return remoteService.fetch()
        .doOnError(error -> {
            logger.warn("Remote source failed", error);
            metrics.incrementFallbackCandidate();
        })
        .onErrorReturn("unavailable");
```

This is an **illustrative snippet**, with variables owned by the application. Place `doOnError` before the handler to track actual errors. If metrics need to count **only errors that were actually recovered**, use an appropriate filtering overload and a metric with the same condition, or an `onErrorResume` with a callback when recovery occurs; `doOnError` placed before the handler may also count non-matching errors.

### 9.4. Fallback values must be consistent with the domain

| Domain | Potentially reasonable fallback | Dangerous fallback |
| --- | --- | --- |
| Secondary UI label | `"temporarily unavailable"` | Empty string mistaken for a real label. |
| Non-essential content recommendations | Empty list **if the UI distinguishes error state** | Empty list implying there are definitely no results. |
| Sensors/measurements | DTO with `available=false` | Number 0 if 0 is a valid measurement. |
| Authorization decisions | Usually keep error or fail closed per explicit policy | `true` when the permission-check service fails. |
| Payments, inventory, transactions | Report a retryable error and preserve integrity | Fake "succeeded" value causing the client to ignore failure. |

## 10. Testing Behavior, Not Just Final Values

Use `reactor-test` to verify both data and terminal signals. Add the test dependency to `pom.xml` when writing unit tests:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

**Illustrative snippets inside test methods**, requiring importing `reactor.test.StepVerifier` and `reactor.core.publisher.*`:

```java
StepVerifier.create(
        Flux.just(6, 3, 0, 2)
            .map(n -> 12 / n)
            .onErrorReturn(-1))
    .expectNext(2, 4, -1)
    .verifyComplete();

StepVerifier.create(
        Mono.<Integer>empty().onErrorReturn(-1))
    .verifyComplete();

StepVerifier.create(
        Mono.<Integer>error(new IllegalArgumentException("bad"))
            .onErrorReturn(IllegalStateException.class, 99))
    .expectError(IllegalArgumentException.class)
    .verify();
```

The three tests make very clear distinctions:

1. After an error in Flux, one fallback is emitted and then it completes.
2. An empty Mono does not trigger the fallback at all.
3. A non-matching error type is preserved as `onError`.

If testing a publisher with retry, measure the subscription count with a counter or `StepVerifier` combined with a mock publisher. To test errors in Spring WebFlux, use `WebTestClient` to check **status and body**; having `block()` return the right fallback in a CLI is not enough to prove the HTTP endpoint has the desired semantics.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `onErrorReturn` to handle `Mono.empty()` | Fallback does not run, publisher stays empty | Use `defaultIfEmpty`/`switchIfEmpty`. |
| Thinking `Flux.onErrorReturn` continues elements after the error | Remaining upstream elements are never processed | Use per-item recovery if continuing is required; or intentional retry. |
| Using a fallback of an incompatible type | Code does not compile or semantics are wrong | Choose the same `T` or convert data to a valid DTO. |
| Passing `null` as the fallback | Reactor does not allow `null` in `onNext` | Use a valid value, empty publisher, or explicit status result. |
| Creating fallback via an expensive function directly in the argument | Function is called at assembly even if the source never errors | For dynamic fallbacks, use `onErrorResume`/`Mono.fromSupplier`. |
| Using a mutable object as fallback on a shared publisher | Subscriptions can share and mutate the same object | Prefer immutable fallbacks or create a new one on recovery. |
| Placing `onErrorReturn` before the operator that causes the error | Cannot catch downstream errors | Place it after the section needing protection. |
| Placing `retry` after `onErrorReturn` and expecting retries | Error already turned into complete so there is no error to retry | Decide ordering and safety of retry. |
| Catching all `Throwable` and returning "success" | Can mask programming, security, and data errors | Restrict error types, keep observability, choose valid status. |
| Placing `doOnError` after fallback and expecting to see the original error | Callback does not see the error already replaced with a value | Log/record metrics before recovery. |
| Treating fallback 0 or false as "no data" | Mixes valid values with error states | Return a status-bearing DTO or keep the error. |
| Using `block()` in a WebFlux controller to get the fallback | Can block the event loop, losing reactive benefits | Return the publisher for WebFlux to consume. |
| Returning HTTP 200 when a critical service is failing | Client may misinterpret the operation as successful | Keep the error or return a ResponseEntity with an appropriate HTTP status. |
| Using fallback in a partially emitted stream as if it were real data | Mixes real data with a fake element, causing wrong reports | Define a separate error event or handle all-or-nothing. |

## 12. Self-Check

**Question 1.** What does `Mono.just(5).onErrorReturn(0)` produce?  
**Answer:** Emits `5` and then completes. There is no error, so 0 is not used.

**Question 2.** Does `Mono.<Integer>empty().onErrorReturn(0)` emit 0?  
**Answer:** No. An empty publisher completes normally. Only `defaultIfEmpty(0)` emits 0.

**Question 3.** What does `Flux.just(4, 2, 0, 1).map(n -> 8 / n).onErrorReturn(-1)` emit?  
**Answer:** `2, 4, -1` and then completes. Element `1` after `0` is not processed because upstream errored at `0`.

**Question 4.** Does `Mono.error(new IllegalStateException()).onErrorReturn(IllegalArgumentException.class, "N/A")` emit `"N/A"`?  
**Answer:** No, assuming the chain's type is declared compatibly; because the exception is `IllegalStateException`, not `IllegalArgumentException`, the error still propagates down. In real Java, an explicit generic type is needed to match the fallback type, e.g., `Mono.<String>error(...)`.

**Question 5.** Why can `onErrorReturn(createFallback())` call `createFallback()` when the source has never errored?  
**Answer:** Java evaluates method arguments immediately when building the chain. `onErrorReturn` takes an already-created value, not a supplier. If conditional evaluation is needed, use `onErrorResume`.

**Question 6.** How does `source.retry(1).onErrorReturn("offline")` differ from `source.onErrorReturn("offline").retry(1)`?  
**Answer:** The first gives one retry before using the fallback if it still fails; the second already turned the error into success, so retry sees no matching error to trigger on.

**Question 7.** Why shouldn't `onErrorReturn(true)` be used when an authorization-check service fails?  
**Answer:** It can grant access without verification (fail-open). Access decisions must enforce safety per policy; a system error does not implicitly grant valid permission.

**Question 8.** For an endpoint returning `Flux<Order>`, an error happens after two orders have been sent. Does `onErrorReturn(fallbackOrder)` mean the client receives the "complete list"?  
**Answer:** No. It only replaces the error with one fallback element and completes; unemitted orders are still missing. The client must distinguish the error state, or the API must return the complete result only after all data is available.

## Remember

- **`onErrorReturn(fallback)` only triggers when upstream emits a matching `onError`.** It emits exactly **one fixed replacement value** and then completes successfully.
- **Empty is not Error:** for missing values, use `defaultIfEmpty`/`switchIfEmpty`; for errored sources, use the `onError...` operators or `retry` according to policy.
- For a `Flux` that already emitted some elements, `onErrorReturn` **does not go back to the source** to continue elements after the error.
- The fallback is created **before the error occurs** if the argument expression is evaluated eagerly; prefer immutable values with clear business semantics. If it must be computed dynamically per error, use `onErrorResume`.
- Limit the scope of replaced errors, log/record metrics before recovery, and never mask security or transaction errors. In WebFlux, return the publisher for the HTTP infrastructure to consume and choose appropriate status/body.

### References

1. [Project Reactor – Flux API: onErrorReturn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) – value, exception type, and predicate overloads.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) – error recovery for Mono.
3. [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) – onErrorReturn, onErrorResume, onErrorComplete, and terminal error characteristics.
4. [Project Reactor – Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand when emitting elements.
5. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – onNext/onError/onComplete and Subscription contracts.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – reactive HTTP pipeline, response consumption, and error handling.
