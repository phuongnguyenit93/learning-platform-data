# Limitations of `onErrorContinue` and When to Handle Errors Locally in Project Reactor

## 1. The Problem: Should One Bad Record Break the Entire Stream?

In Spring WebFlux and Project Reactor, errors are represented by the `onError` signal. Under the Reactive Streams contract, a Publisher **that has emitted `onError` is terminated**: it does not continue emitting further `onNext` or `onComplete` on that same subscription.

Suppose you receive a stream of strings and parse them into integers:

```java
Flux<Integer> values = Flux.just("10", "bad", "20")
        .map(Integer::parseInt);
```

When subscribed, `"10"` is converted into `10`, while `"bad"` causes `Integer.parseInt` to throw `NumberFormatException`. Without a recovery policy, the subscriber receives `onError`, and `"20"` **is not emitted as a result**.

If business rules say "drop only the invalid record and continue processing valid records", learners often try:

```java
Flux<Integer> values = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue((error, value) -> {
            System.out.println("Dropped: " + value);
        });
```

When the **`map` operator supports this mechanism**, the stream may emit `10`, skip `"bad"`, and then emit `20`. However, **you should not generalize** that `onErrorContinue` is a "try/catch for the entire pipeline".

**Main point of this lesson:** `onErrorContinue` is a special and relatively hard-to-predict mechanism that only works when upstream operators **support continuing after an error raised while processing a single element**. When you need to skip errors per record/task, you should normally **place error handling right inside that record/task's scope** using `handle`, `filter`, or an inner `Mono` with `onErrorResume`. This approach has a clearer scope and avoids unintentionally affecting upstream code.

## 2. Distinguishing Terminal Error Signals from Per-Element Processing Errors

In Reactive Streams, there are three key signals after `onSubscribe`:

```text
onNext(T)      : a data element
onComplete()   : successful completion, terminal
onError(error) : termination due to error, terminal
```

After `onComplete` or `onError`, there are no further values. `onErrorContinue` **does not alter that terminal rule**. It can only act at positions where an operator sees an error **while processing an `onNext`** and supports dropping the offending element before converting the failure into a final `onError`.

Two very different cases:

**Case A — synchronous error in a single element's mapper:**

```java
Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue(NumberFormatException.class,
                (error, badValue) -> logBadValue(badValue));
```

`map` is an example that can support dropping just the `"bad"` element to keep processing `"20"`. `logBadValue` is an illustrative method defined by the application. Continuation must be supported by the upstream operator; the result does not come from "restarting" a Publisher that already terminated.

**Case B — the source Publisher itself emits a terminal error:**

```java
Flux<Integer> source = Flux.concat(
        Flux.just(10),
        Flux.error(new IllegalStateException("source failed")),
        Flux.just(20)
);
```

When the subscription reaches `Flux.error(...)`, that is a **source error**, not a specific input element that a `map` operator can drop. Attaching `onErrorContinue` after the source **is not a reliable way to turn this terminal `onError` into `onNext(20)`**. If application policy requires continuing, you must design recovery at the appropriate source/branch boundary, such as using `onErrorResume` in the right place or representing each unit of work as a separate inner Publisher.

## 3. What Does `onErrorContinue` Actually Do?

Common API sketch:

```java
Flux<T> stream = someFlux.onErrorContinue(
        (Throwable error, Object value) -> {
            // Observe the error and the value dropped by the upstream operator.
        }
);
```

This is an **illustrative usage signature**, not a complete API definition. Reactor also provides overloads filtering by exception type or predicate:

```java
.onErrorContinue(NumberFormatException.class,
        (error, value) -> System.out.println("Invalid: " + value))
```

Key points you must understand:

1. **Direction of effect is upstream.** Although `.onErrorContinue(...)` is written downstream at the end of the chain, the continuation mechanism propagates backward into certain preceding operators. Not every operator can catch an error and know which element to drop.
2. **Requires operator support.** For example, `map` usually has clear semantics for dropping the failing element; a Publisher that already emitted `onError` itself has no "failing record" left to continue past.
3. **Not a conventional error-replacement operator.** `onErrorResume` sees an error signal and switches to a fallback Publisher; `onErrorContinue` alters how *upstream* operators handle errors while processing an element.
4. **Scope can leak.** Depending on placement, continuation configuration can affect earlier operators, including operators inside libraries/services whose authors never designed them to skip errors. This makes code hard to read and hard to be sure which parts have permission to drop errors.
5. **No guaranteed behavior with unsupported operators.** Across nested operators, async boundaries, resource handling, or errors emitted directly from a source, never assume the `onErrorContinue` callback will always be invoked.
6. **The callback receives the error and the dropped value.** `value` has type `Object`; for a mapper error, it is usually **the input value that caused the failure**, not necessarily the downstream result type. Avoid unsafe casting when a chain has multiple transformation steps.
7. **The callback itself can throw.** If the handler throws an exception, normal continuation breaks and a new error can be emitted. Keep error-recording logic short and safe; never call blocking services in the callback.

Important for data safety: "dropping an invalid record" is also a **business decision**. If the system must guarantee no events are lost, do not silently apply continuation. Define metrics, a dead-letter queue, auditing, and retry/redrive policies where appropriate.

## 4. Contrasting Example: `onErrorContinue` vs. `onErrorResume`

### 4.1. Dropping a failing element in a supporting `map`

```java
Flux<Integer> continued = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue(
                NumberFormatException.class,
                (error, rejected) ->
                        System.out.println("Dropped: " + rejected)
        );
```

When subscribing to this synchronous cold source, the successful values are `10` and `20`. The `map` call on `"bad"` fails and the value is dropped in the continuation-supporting operator. **This example illustrates conditional behavior**, not a guarantee for every pipeline implementation.

### 4.2. `onErrorResume` replaces the rest of the errored stream

```java
Flux<Integer> resumed = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class,
                error -> Flux.just(-1));
```

The result is `10`, then `-1`, then complete. **There is no `20`**: the mapper error terminated the original upstream; `onErrorResume` switched to the fallback Publisher rather than jumping back into `Flux.just` to process the next element.

This is a crucial distinction:

| Handling approach | Result for `"10","bad","20"` in the simple example | Scope of effect |
|---|---|---|
| No handling | `10`, then `onError` | Terminal error |
| `onErrorResume` outside `map` | `10`, then `-1`, then complete | Replaces **the rest of the whole chain** with a fallback Publisher |
| `onErrorContinue` after a supporting `map` | `10`, drops `"bad"`, `20`, complete | Continuation mechanism in compatible upstream operators |
| Recovery on **each inner Mono** | `10`, drops `"bad"`, `20`, complete | One isolated task/record, easy to scope |
| `handle` with `try/catch` | `10`, drops `"bad"`, `20`, complete | Validation and transformation at a specific synchronous step |

Having the same output values **does not mean identical semantics and error scope**.

## 5. Preferred Approach 1: Synchronous Handling in `handle`

When errors are predictable from **the input data of a synchronous transformation**, using `handle` expresses the "one in, zero or one out" rule and places `try/catch` right next to the parse operation:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "20")
        .<Integer>handle((text, sink) -> {
            try {
                sink.next(Integer.parseInt(text));
            } catch (NumberFormatException error) {
                System.out.println("Rejected: " + text);
            }
        });
```

Here:

- `sink.next(...)` is called only when `Integer.parseInt` succeeds.
- When `NumberFormatException` occurs, the handler **does not call `sink.next`**, so that record is not emitted.
- `handle` does not force turning every error into "skip". You can choose `sink.error(error)` for severe errors to stop the pipeline, or record invalid data to an approved monitoring mechanism.
- `handle` is only suited for **synchronous operations**; do not use it to emit results from an asynchronous callback after the `BiConsumer` has returned.

If you do not need to catch exceptions, express it even more directly:

```java
Flux<String> cleaned = Flux.just("10", "", "20")
        .filter(s -> !s.isBlank());
```

`filter` is much clearer than throwing exceptions just to use `onErrorContinue`. When you need a transformation that may produce no value without throwing, consider `mapNotNull` (where Reactor version and null conventions match) or `handle`.

### Strengths and limits of `handle`

Strengths: the decision point for dropping data sits right in the code; no silent continuation configured for distant operators; each exception can be handled per business rules. Limits: too much complex `try/catch` logic makes the handler hard to read; extract it into a dedicated parse/validate method and catch only genuinely expected error types.

## 6. Preferred Approach 2: Isolating Errors Per Inner `Mono`

When each element triggers its own task (parsing, validating, calling an API, writing to a service), you can turn each task into **an inner Publisher**, then put recovery **inside that inner Publisher**:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "20")
        .concatMap(text ->
                Mono.fromCallable(() -> Integer.parseInt(text))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty())
        );
```

`Mono.fromCallable` defers parsing until subscription of each inner Mono. If parsing fails, only **the corresponding inner Mono** completes empty; `concatMap` continues with the next element of the outer Flux.

- Input `"10"` → inner Mono emits `10`.
- Input `"bad"` → inner Mono errors, `onErrorResume` converts the expected error into `Mono.empty()`.
- Input `"20"` → inner Mono emits `20`.

The result is `10`, `20`, complete, with a very clear handling boundary: **errors are only recovered inside the task for the current record**. If the **outer Publisher itself errors**, inner recovery does not swallow the outer error; this is usually the desired behavior.

Why use `concatMap` in the example? It preserves processing/output order matching the source, which helps keep logs in sequence. `flatMap` can execute multiple inner Publishers concurrently, and in asynchronous tasks completion order does not always match input order. Choose based on ordering, throughput, and concurrency limits.

### Beware of eager evaluation when creating the inner

The pattern below does not provide the per-item boundary you might expect:

```java
// Anti-pattern: parseInt may throw BEFORE Mono.just is even created.
Flux<Integer> wrong = Flux.just("10", "bad", "20")
        .flatMap(text ->
                Mono.just(Integer.parseInt(text))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty())
        );
```

`Integer.parseInt(text)` is evaluated by Java before `Mono.just(...)`. If it throws an exception, **the inner Mono does not exist yet** for the trailing `onErrorResume` to catch that error. Use `Mono.fromCallable(() -> ...)` or `Mono.defer(...)` whenever you truly need to defer error-prone logic.

Example handling a **Publisher returned from an API** where the Publisher-creating method can also throw synchronously:

```java
// Illustrative code: client.lookup(id) returns Mono<Result>.
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> client.lookup(id))
                .onErrorResume(RecordNotFoundException.class,
                        error -> Mono.empty()),
        8
);
```

`Mono.defer` defers invoking the Publisher factory until inner subscription; recovery is placed **inside** each ID's scope. `ids`, `client`, `Result`, and `RecordNotFoundException` are hypothetical project components; this snippet is not a standalone compilable program. The number `8` is an illustrative concurrency level, and target API limits must be considered.

**Note:** do not confuse `Mono.empty()` with success. If every record must be processed or reported, return an explicit result type such as `ValidationOutcome.Success`/`Failure` and route errors to an error-handling queue rather than letting them vanish without a trace.

## 7. Complete Runnable Java 17+ Example

The example below intentionally keeps sources **cold, synchronous, and finite** so stdout order does not depend on network or scheduler timing. It compares four ways to handle the same data; the `onErrorContinue` case placed after `map` demonstrates an operator that supports continuation. Data and console logs use simple English for easy comparison.

File structure:

```text
reactor-local-error-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-local-error-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/Main.java`:

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class Main {
    public static void main(String[] args) {
        System.out.println("=== onErrorContinue ===");
        Flux.just("10", "bad", "20")
                .map(Integer::parseInt)
                .onErrorContinue(
                        NumberFormatException.class,
                        (error, value) ->
                                System.out.println("continue dropped: " + value)
                )
                .subscribe(
                        n -> System.out.println("continue next: " + n),
                        e -> System.out.println("continue error: " + e),
                        () -> System.out.println("continue complete")
                );

        System.out.println("=== onErrorResume on whole sequence ===");
        Flux.just("10", "bad", "20")
                .map(Integer::parseInt)
                .onErrorResume(NumberFormatException.class, error -> {
                    System.out.println(
                            "resume failure: " + error.getClass().getSimpleName()
                    );
                    return Flux.just(-1);
                })
                .subscribe(
                        n -> System.out.println("resume next: " + n),
                        e -> System.out.println("resume error: " + e),
                        () -> System.out.println("resume complete")
                );

        System.out.println("=== local per-item recovery ===");
        Flux.just("10", "bad", "20")
                .concatMap(raw -> {
                    Mono<Integer> item = Mono.fromCallable(
                            () -> Integer.parseInt(raw)
                    ).onErrorResume(NumberFormatException.class, error -> {
                        System.out.println("local dropped: " + raw);
                        return Mono.empty();
                    });
                    return item;
                })
                .subscribe(
                        n -> System.out.println("local next: " + n),
                        e -> System.out.println("local error: " + e),
                        () -> System.out.println("local complete")
                );

        System.out.println("=== handle for sync parsing ===");
        Flux.just("10", "bad", "20")
                .<Integer>handle((raw, sink) -> {
                    try {
                        sink.next(Integer.parseInt(raw));
                    } catch (NumberFormatException error) {
                        System.out.println("handle dropped: " + raw);
                    }
                })
                .subscribe(
                        n -> System.out.println("handle next: " + n),
                        e -> System.out.println("handle error: " + e),
                        () -> System.out.println("handle complete")
                );
    }
}
```

From `reactor-local-error-demo/`, with Maven and JDK 17+ installed, run:

```bash
mvn -q compile exec:java
```

Stdout printed by the program itself (excluding Maven logs if the environment is configured differently):

```text
=== onErrorContinue ===
continue next: 10
continue dropped: bad
continue next: 20
continue complete
=== onErrorResume on whole sequence ===
resume next: 10
resume failure: NumberFormatException
resume next: -1
resume complete
=== local per-item recovery ===
local next: 10
local dropped: bad
local next: 20
local complete
=== handle for sync parsing ===
handle next: 10
handle dropped: bad
handle next: 20
handle complete
```

Trace explanation:

- **`onErrorContinue`**: the error in `map(Integer::parseInt)` on `"bad"` is handled via continuation by the compatible operator; the callback receives the dropped value, and `"20"` still passes through the mapper.
- **`onErrorResume` outside**: `map` emitted a terminal error, so the fallback `-1` replaces the remainder. `"20"` from the original source **is not emitted**.
- **Local `concatMap`**: each raw string becomes a `Mono<Integer>`. The inner Mono failing on `"bad"` is converted to `Mono.empty()` right there; the outer Flux still processes `"20"`.
- **`handle`**: `try/catch` keeps the record-dropping decision right at the parse function, without propagating continuation backward across multiple operators.

The example does not use `.block()` in a controller, makes no network calls, and makes no thread-name assumptions. Because the sources are simple and synchronous, lines appear in the exact order shown above. Other code snippets in this article with hypothetical service names are marked separately as illustrative, not part of this standalone program.

## 8. Why Does `onErrorContinue` Easily Cause Unintended Side Effects?

### 8.1. Preceding operators do not share a uniform continuation contract

Suppose a chain passes through several operators:

```java
Flux<Result> output = source
        .map(this::parse)
        .flatMap(this::remoteLookup)
        .map(this::toDto)
        .onErrorContinue((error, value) -> log(error, value));
```

This is **application-dependent illustrative code**, not a standalone runnable file. Writing it this way does not allow a reader to reliably infer that **every error from every source** is dropped and the pipeline keeps running normally. `remoteLookup` may return a Mono failing from the network; the source may emit a terminal `onError`; some operators lack continuation support. Furthermore, `value` in the callback can have **multiple different data types** depending on where the error occurred.

Instead of placing one handler at the end of the whole pipeline, apply recovery at each semantically meaningful boundary:

```java
Flux<Result> output = source.concatMap(raw -> {
    Mono<Result> one = Mono.defer(() -> parseAndLookup(raw))
            .onErrorResume(ExpectedBadRecordException.class, error -> {
                reportRejected(raw, error);
                return Mono.empty();
            });
    return one;
});
```

`parseAndLookup`, `reportRejected`, `Result`, and `ExpectedBadRecordException` belong to the application. Recovery affects only **one inner Mono**, and exceptions outside the chosen type still propagate to `onError`. If higher throughput is needed, consider `flatMap` with appropriate concurrency limits and ordering requirements.

### 8.2. Unexpected outcomes after `flatMap` and async boundaries

Errors inside an **inner Publisher** have their own lifecycle. Placing `onErrorContinue` outside is not a guarantee that every `onError` from every inner can be converted into "drop one record". An inner Mono may signal an error directly without knowing which element to drop, and per the protocol `onError` remains terminal.

Isolate properly:

```java
// service.find(id) returns Mono<Entity>; a missing ID may signal an error.
Flux<Entity> entities = ids.flatMap(id ->
        service.find(id)
                .onErrorResume(EntityNotFoundException.class,
                        error -> Mono.empty()),
        4
);
```

Here outer `ids` continues processing other IDs after an error **recovered inside the inner**, provided outer itself does not error and other stages do not emit unhandled errors. `flatMap` can alter output ordering when async inners finish at different times; if ordering matters, use `concatMap` or an appropriate order-preserving operator.

### 8.3. Scope propagating backward through shared code

A library called by a service may contain internal `map` operators and assume an error there will terminate the Publisher. An `onErrorContinue` attached far downstream can reach backward into continuation-supporting operators in upstream regions **outside the caller's control**. Internal technical errors then risk being silently turned into dropped data.

When you need to shield a substream from continuation applied outside, Reactor provides `onErrorStop()` to restore **STOP** semantics for the corresponding upstream scope. Even so, that is a specialized scope-management tool; the primary policy should be **not extending `onErrorContinue` across libraries not designed for it**, rather than relying on patching scope afterward.

### 8.4. Errors in callbacks and side effects

The `(error, value) -> ...` callback should be treated as a place to record the dropped event, not a complex business workflow. If the callback itself throws an exception, you cannot assume the pipeline still continues. If the callback calls a blocking API on the event loop, it can also stall signal-processing threads.

Do not rely on an `onErrorContinue` callback to guarantee writing a record to an external dead-letter queue if that write can fail asynchronously. When you must **guarantee recording the error before accepting further processing**, move that step into a controlled **inner Publisher**, e.g. `onErrorResume(error -> deadLetterPublisher(...).then(Mono.empty()))`, and explicitly define what happens if writing to the dead-letter queue fails.

## 9. Local Error Handling for WebFlux Services

Scenario: a request receives a stream of IDs and needs to fetch each user from an external service. By business rules, only `CustomerNotFoundException` is allowed to be skipped; timeouts, authentication errors, and 5xx errors must surface so the client knows the system hit a failure.

Example **inside an existing application**, depending on types `Customer`, `CustomerView`, and `customerClient`:

```java
Flux<CustomerView> fetchCustomers(Flux<Long> ids) {
    return ids.flatMap(id -> {
        Mono<CustomerView> perId = Mono.defer(
                    () -> customerClient.fetch(id)
                )
                .map(customer -> new CustomerView(
                        customer.getId(), customer.getName()))
                .onErrorResume(CustomerNotFoundException.class,
                        error -> Mono.empty());

        return perId;
    }, 8);
}
```

Explanation:

1. Outer `ids` represents IDs arriving from the client or a reactive source.
2. `Mono.defer` defers calling the Publisher factory, so if the factory throws an expected exception, it is represented as an inner Mono error instead of throwing externally before the recovery chain is formed.
3. `map` converts customer data into an in-memory DTO.
4. `onErrorResume(CustomerNotFoundException.class, ...)` catches only one allowed error type for **a single ID** and converts it to `Mono.empty()`.
5. Other IDs can still be processed. Exceptions other than `CustomerNotFoundException` **are not swallowed** and normally terminate the result according to `flatMap`'s error policy.
6. `flatMap(..., 8)` caps concurrent active inner Publishers in this chain; it does not create a system-wide limit by itself. If results must preserve exact ID order, switch to a sequential/order-preserving strategy.

For HTTP APIs returning `Mono<...>`, the controller usually **returns the Publisher** for Spring WebFlux to subscribe to; do not manually call `.subscribe()` or `.block()` and assemble lists by hand.

### When should you report local errors instead of dropping data?

If the number of requested elements must match the number of output elements (such as generating a reconciliation report), skipping errors with `Mono.empty()` loses information. Instead of `Flux<CustomerView>`, return a type capable of carrying errors:

```java
// Illustrative API style: outcome records and functions belong to the application.
Flux<FetchOutcome> results = ids.concatMap(id ->
        Mono.defer(() -> customerClient.fetch(id))
                .map(customer -> FetchOutcome.success(id, customer))
                .onErrorResume(CustomerNotFoundException.class,
                        error -> Mono.just(FetchOutcome.notFound(id)))
);
```

This way, each ID has an auditable outcome. Unpermitted system errors remain terminal. **Recovering an error** does not necessarily mean dropping the element; sometimes you should convert the error into explicitly typed data.

## 10. Comparing Common Error-Handling Operators

| Operator/technique | Purpose | Does the original source continue after the failed element? |
|---|---|---|
| `doOnError` | Observes/logs errors | No; the error still propagates |
| `onErrorMap` | Maps a `Throwable` to another error | No; still a terminal error |
| `onErrorResume` | On upstream error, switches to a fallback Publisher | Does not continue the original upstream; runs fallback |
| `onErrorReturn` | Uses a fallback value for matching errors | No; replaces the failed tail with a value |
| `onErrorComplete` | Converts matching errors into complete | No; original upstream has terminated |
| `retry` / `retryWhen` | Re-subscribes to the source after an error per policy | Does not resume from the old position; typically **re-executes** the source |
| `onErrorContinue` | Only for supporting operators: drops one failing element during upstream processing | Possibly, **not guaranteed** across all sources/operators |
| `handle` + `try/catch` | Explicitly decides to emit or drop a value in a synchronous step | Yes, if the handler catches expected data errors |
| Inner `Mono` + `onErrorResume` | Scopes errors and fallbacks to a single task/record | Can continue the outer Publisher after inner recovery |

Why isn't `retry` a solution for a bad record? If a cold source emits `"10","bad","20"` and has `.retry(1)`, when parsing hits `"bad"` it can re-subscribe from the beginning: `"10"` is processed **again** and `"bad"` fails again. There is no magic that skips bad records; retries must be based on error type and operation idempotency, especially for DB writes, sending emails, or payments.

## 11. Discipline in Designing Recovery Without Hiding Bugs

Answer these questions before deciding to use any error-dropping approach:

1. **Expected error or system error?** A malformed CSV value might be a record error; a database timeout or programming bug should usually not be silently discarded.
2. **Can the failing record/ID be identified?** Putting `onErrorResume` inside an inner Publisher preserves the ID via closure. An `onErrorContinue` callback receives an `Object` that can be harder to correlate with business context.
3. **Is losing records acceptable?** If reconciliation is required, emit `Success`/`Failure` instead of `Mono.empty()`.
4. **Does order need to be preserved?** `concatMap` preserves order; `flatMap` increases concurrency, but API results may arrive out of order.
5. **Outer error or inner error?** Inner recovery does not cure outer source errors; this is often helpful to distinguish whole-stream failures from single-ID failures.
6. **Is retry present?** Retry can re-execute tasks and side effects; backoff, attempt limits, and idempotency are needed.
7. **Is dropped data recorded?** Error-record metrics, audit logs, error queues, or outcomes help detect pipelines silently losing data.
8. **Are concurrency and memory bounded?** Even with good local error handling, too many concurrent inner Publishers can still cause overload.
9. **Are timeouts and cancellation handled?** When downstream cancels or the client disconnects, some inners may be cancelled; error recovery does not mean every task is guaranteed to finish.

For external integrations, do not treat `.onErrorResume(e -> Mono.empty())` for **all Throwables** as a default convention. It can cause services to return incomplete responses without notifying users or monitoring systems.

## 12. Testing Key Scenarios

With `reactor-test`, `StepVerifier` can verify exact data and terminal signals. The snippets below are **examples in test code** importing `reactor.test.StepVerifier` and do not run standalone unless the `reactor-test` dependency is added to test scope:

```java
Flux<Integer> local = Flux.just("1", "bad", "2")
        .concatMap(raw -> Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(NumberFormatException.class,
                        error -> Mono.empty()));

StepVerifier.create(local)
        .expectNext(1, 2)
        .verifyComplete();
```

With `onErrorResume` on the whole chain:

```java
Flux<Integer> fallback = Flux.just("1", "bad", "2")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class,
                error -> Flux.just(-1));

StepVerifier.create(fallback)
        .expectNext(1, -1)
        .verifyComplete();
```

Beyond the happy path, include tests proving **different error types are not swallowed**, outer errors remain terminal, callbacks log the right ID, asynchronous sources preserve or do not preserve order as expected, and side effects are not executed twice unexpectedly when retries are present.

If you want to verify `onErrorContinue` on a specific operator, write tests directly against the **exact Reactor version and exact chain being deployed**, because it cannot be treated as a universal support contract across all operators.

## 13. Common Misconceptions

**"`onErrorContinue` is a general catch at the end of a pipeline."** False. It affects compatible upstream operators and lacks the clear recovery boundary of an inner `onErrorResume`.

**"If an HTTP Mono returns `onError`, attaching `onErrorContinue` drops that ID."** Not guaranteed. The Publisher may have already emitted a terminal `onError`; better to put `.onErrorResume(...)` directly on that ID's Mono.

**"`onErrorResume` will keep processing the remaining elements of the source."** False when placed outside an errored source. It switches to a fallback Publisher; to skip a single element's error, recover inside an inner Publisher.

**"Dropping a failed element is always safe."** False. For financial or data-sync workflows, dropping an element can cause wrong totals, missing records, or broken reconciliation. Define a data-quality policy.

**"`doOnError` handles the error."** False. It only observes and may log; recovery requires the right operator.

**"`retry` continues from the record after the error."** False in typical cases. Retry re-subscribes to the source, which can re-run already-processed elements.

**"Error handlers should catch `Throwable` and always complete."** Dangerous. It can mask programming bugs, infrastructure outages, and situations that must be reported to clients. Prefer catching expected business error types.

**"If using `flatMap` with inner recovery, output order always matches the source."** False for asynchronous inners. `flatMap` can interleave results; use `concatMap` or an order-preserving technique when needed.

## 14. Self-Check Exercises

**Question 1.** What does `Flux.just("1", "bad", "2").map(Integer::parseInt).onErrorResume(e -> Flux.just(0))` emit?

**Answer:** `1`, then `0`, and completes. `"2"` does not pass through the mapper because the original source already errored.

**Question 2.** Why might `onErrorContinue` fail to handle `Flux.error(new IllegalStateException(...))`?

**Answer:** That is a terminal `onError` signal emitted directly by the Publisher, not an element inside a compatible operator that can be skipped to continue.

**Question 3.** How can you avoid using `onErrorContinue` when parsing numbers in a `Flux<String>`?

**Answer:** Use `handle` with `try/catch` at the parse step to emit only valid numbers, or turn each value into an inner `Mono.fromCallable` and place `onErrorResume(NumberFormatException.class, ...)` inside that inner.

**Question 4.** Why is placing `.onErrorResume(...)` inside `flatMap` different from placing it at the end of the pipeline?

**Answer:** Placing it inside the inner recovers errors for **a single unit of work**; placing it at the end recovers errors of **the entire upstream** with a fallback after upstream terminates.

**Question 5.** If an inner API returns a "not found" error that is allowed to be skipped, while 500 errors must not be skipped, how should it be designed?

**Answer:** Use `onErrorResume(NotFoundException.class, error -> Mono.empty())` on the inner Mono. Other errors propagate for the system to handle; add logs/metrics/outcome types if dropped data must be audited.

**Question 6.** When a library operator uses `map` internally, what is the risk of placing `onErrorContinue` deep downstream?

**Answer:** The continuation mechanism can reach backward into the library's compatible upstream operator, causing internal errors to be skipped instead of terminating as the library expects.

**Question 7.** What is the output of `Flux.just("1","bad","2").concatMap(s -> Mono.fromCallable(() -> Integer.parseInt(s)).onErrorResume(NumberFormatException.class, e -> Mono.empty()))`?

**Answer:** `1`, `2`, complete; the outer Flux continues after the errored inner Mono is turned into empty.

## 15. Quick Selection Rules

- **Synchronous transformation/validation of a single element where data errors can be dropped:** prefer `filter`, `handle`, a parse function returning `Optional`, or error handling right at the transformation point.
- **Each element triggers its own Mono/Flux:** prefer placing `onErrorResume` **inside the inner Publisher**, filtering the exact exception type; choose `concatMap` or `flatMap` based on ordering/concurrency.
- **Whole source fails and needs a fallback:** use `onErrorResume` at the appropriate boundary, accepting that the original upstream does not "continue from the failure point".
- **System errors must be surfaced:** keep terminal `onError`, or `onErrorMap` to an appropriate business error; do not swallow all errors.
- **Only consider `onErrorContinue` when you truly understand which upstream operators support it, its impact scope, discard risks, and have tests verifying the exact pipeline.** Avoid treating it as the default recovery policy in a WebFlux application.

**Remember:** `onErrorContinue` is a specialized mechanism meant to drop failing elements **in supporting upstream operators**, not a way to recover arbitrary terminal `onError` signals. To handle per-record errors in a readable, testable, and auditable way, **scope recovery to the element or inner Publisher**, while letting serious system errors propagate per the Reactive Streams contract.
