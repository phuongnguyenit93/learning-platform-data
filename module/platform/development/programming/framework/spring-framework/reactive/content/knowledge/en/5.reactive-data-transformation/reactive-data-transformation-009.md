# `then`, `thenReturn`, and the Consequences of Discarding Input Values in Project Reactor

## 1. Goal and Context

In Spring WebFlux, `Mono<T>` and `Flux<T>` do not merely hold data: they represent an asynchronous process that can emit elements (`onNext`), complete successfully (`onComplete`), emit an error (`onError`), or be canceled (`cancel`). When chaining multiple operations, sometimes we **only care that the previous operation completed successfully**, without needing to keep the value it produced. Project Reactor provides the `then` and `thenReturn` operators for that case.

Two main ideas:

- `then()`: waits for the source to complete and returns `Mono<Void>`, **ignoring all input elements**; only success or error is propagated.
- `thenReturn(value)`: waits for a source **`Mono`** to complete successfully, discards the source value if any, and emits **a new pre-supplied value**.

In this lesson, “drop” or “discard” means **not forwarding that element to the downstream subscriber**. It does not mean the source task never executed, that objects were immediately freed from memory, or that resources were automatically closed.

### Practical Scenario

A service saving a record returns `Mono<SavedEntity>`. The endpoint only needs to know the save succeeded in order to return a fixed confirmation code; there is no need to send `SavedEntity` back to the caller:

~~~java
Mono<String> acknowledgement =
    repository.save(entity)
              .thenReturn("SAVED");
~~~

If saving succeeds, downstream receives `"SAVED"` followed by `onComplete`. If saving errors, downstream receives `onError`; the `"SAVED"` value **is not emitted**. If you need the ID or fields of `SavedEntity`, do not use `thenReturn` because that information is discarded; use `map(saved -> ...)` or `flatMap(saved -> ...)`.

## 2. Foundation: Completion Signals Differ from Data Values

Separate two questions:

1. **How did the source terminate?** Success (`onComplete`) or error (`onError`)?
2. **What data did the source produce?** No elements, one element, or multiple elements?

A `Mono.just("A")` emits `onNext("A")` then `onComplete`; `Mono.empty()` emits only `onComplete`; `Mono.error(...)` emits `onError`. After adding `then()`:

~~~text
Original source                       After then()
onNext("A") -> onComplete            onComplete
onComplete                            onComplete
onError(exception)                   onError(exception)
onNext("A") -> onNext("B") -> done    onComplete
~~~

All `onNext` signals from upstream are discarded, yet **errors are not swallowed**. The `then` operator is not equivalent to `onErrorComplete` or `onErrorResume`.

Another key point: `onComplete` can occur even when the source is empty. Therefore, `thenReturn("OK")` on `Mono.empty()` still produces `"OK"`. Do not interpret `thenReturn` as “if upstream has a value, convert it to OK”; it means “**if upstream completes successfully, emit OK**”.

## 3. `then()`: Keeping Only the Completion Outcome

### 3.1. `Mono<T>.then()`

Conceptual signature:

~~~java
Mono<Void> finished = sourceMono.then();
~~~

Example:

~~~java
Mono<Void> finished = Mono.just("payload")
    .doOnNext(value -> System.out.println("source=" + value))
    .then();

finished.subscribe(
    ignored -> System.out.println("No onNext here"),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Stdout:

~~~text
source=payload
complete
~~~

Explanation:

- Upstream emitted `"payload"`, so the `doOnNext` callback **placed before** `then` still sees the value.
- `then` intentionally discards `"payload"`, so downstream **sees no** `onNext`.
- `Mono<Void>` signals successful completion with `onComplete`; it **does not emit a `Void` object**.
- When the source signals an error, the `then()` result emits the error instead of completing successfully.

The `Void` type represents **success/error only without data**. It is not an `onNext(null)` signal; Reactive Streams forbids emitting `null`.

### 3.2. `Flux<T>.then()`

With a multi-element `Flux`, `then()` also produces `Mono<Void>` and discards every element emitted by the source:

~~~java
Mono<Void> completed = Flux.range(1, 3)
    .doOnNext(i -> System.out.println("processed=" + i))
    .then();
~~~

Upon subscription, elements 1, 2, and 3 still pass through `doOnNext`. Once the source completes, downstream receives only `onComplete`. `then()` **does not stop right after the first element** like `next()` or `take(1)`; it must wait for the entire source to complete successfully.

This has operational consequences: if upstream runs transformations, DB calls, or logging per item, upstream cost is still incurred. Do not use `then()` as an optimization to “avoid doing work” — it only changes **what data is forwarded downstream**.

### 3.3. Do Not Confuse `then()` with `map` or `filter`

~~~java
Mono<Integer> a = Mono.just(10).map(n -> n * 2); // emits 20
Mono<Integer> b = Mono.just(10).filter(n -> n > 5); // emits 10
Mono<Void> c = Mono.just(10).then(); // emits no number, only completes
~~~

`map` transforms *values* and requires an `onNext`. `filter` keeps or drops elements by condition. `then` discards all values and retains only *completion* semantics.

## 4. `thenReturn(value)`: Wait for Success, Then Return a Fixed Value

`Mono<T>.thenReturn(V value)` returns `Mono<V>` and has three properties:

1. The source value `T` no longer appears downstream.
2. If the source finishes successfully (even if empty), downstream receives **one** `value` followed by `onComplete`.
3. If the source errors, the error propagates and `value` **is not emitted**.

~~~java
Mono<String> response = Mono.just(42)
    .thenReturn("OK");
response.subscribe(System.out::println);
// Prints: OK (does not print 42)
~~~

Comparing three sources:

| Upstream | `thenReturn("ACK")` downstream signal | Reason |
| --- | --- | --- |
| `Mono.just(123)` | `onNext("ACK")`, `onComplete` | Discards 123 then emits ACK |
| `Mono.empty()` | `onNext("ACK")`, `onComplete` | Empty completion still counts as success |
| `Mono.error(new IllegalStateException("x"))` | `onError(error)` | Does not emit ACK on error |
| `Mono.never()` | Emits nothing and never finishes | Keeps waiting on upstream; unless canceled/timed out |
| Upstream `cancel()`ed before completing | Cannot be treated as success to emit ACK | Cancellation differs from completion |

### 4.1. `thenReturn` Cannot Access the Source Value

~~~java
Mono<User> saved = repository.save(user); // assumed to return Mono<User>
Mono<String> fixed = saved.thenReturn("SAVED");
~~~

`"SAVED"` is a pre-existing confirmation constant. If you need to build content from the saved record:

~~~java
Mono<String> dynamic = repository.save(user)
    .map(savedUser -> "SAVED:" + savedUser.getId());
~~~

The result of `map` depends on `savedUser`, whereas `thenReturn` discards `savedUser` completely. If the source is empty, `map` does not run and the final `Mono` is also empty; `thenReturn` still emits the confirmation, so clarify **“empty” semantics** before choosing.

### 4.2. The Argument to `thenReturn` Is Evaluated Immediately at Pipeline Assembly

Java evaluates method arguments before calling the method:

~~~java
Mono<Void> save = saveAsync();
Mono<String> result = save.thenReturn(calculateReceipt()); 
// calculateReceipt() runs immediately when building result,
// even though save has not completed or no one has subscribed yet.
~~~

If `calculateReceipt()` is expensive, has side effects, or must run **after saving succeeds, on each subscription**, use a Mono with deferred value creation:

~~~java
Mono<String> result = save.then(
    Mono.fromSupplier(() -> calculateReceipt())
);
~~~

`thenReturn(value)` is usually suited for constants or already-available objects. `then(Mono.fromSupplier(...))` is better when the next value must be **computed when the later stage is subscribed**. Note: even with `then(Mono<V>)`, *the Java expression producing the `Mono` argument* still runs at assembly; only logic inside `fromSupplier`/`defer` is deferred.

### 4.3. Do Not Use `null` as a Success Value

`thenReturn(null)` does not create a valid “Mono containing null”. If you want a result that only completes with no data, use `then()`; if you want a default element, choose a genuinely non-null object. If a value may be absent, consider `then(Mono.justOrEmpty(nullableValue))` or `then(Mono.fromSupplier(...))` with an explicit contract.

## 5. `then(Mono<V>)` and Related Variants

The natural reading of `first.then(second)` is: **complete `first` successfully, then subscribe to `second` and emit `second`'s data**. All values from `first` are discarded.

~~~java
Mono<String> workflow =
    Mono.just("ID-1")
        .doOnNext(id -> System.out.println("saved=" + id))
        .then(Mono.fromSupplier(() -> {
            System.out.println("creating receipt");
            return "receipt-ready";
        }));
~~~

Upon subscription, stdout is:

~~~text
saved=ID-1
creating receipt
~~~

Downstream receives `"receipt-ready"` (if subscribed with a consumer that prints it). If `first` errors, `second` is not subscribed; the upstream error propagates downstream. If `second` errors, downstream receives the error from `second`. If `first` is empty yet succeeds, `second` still runs.

| Operator | Upstream values | What downstream will emit | Return type |
| --- | --- | --- | --- |
| `mono.then()` | Discarded | Only complete/error | `Mono<Void>` |
| `flux.then()` | All discarded | Only complete/error | `Mono<Void>` |
| `mono.thenReturn(v)` | Discarded | One value `v` if successful | `Mono<V>` |
| `mono.then(otherMono)` | Discarded | Emits signals of `otherMono` if upstream succeeds | `Mono<V>` |
| `flux.then(otherMono)` | Discarded | Emits signals of `otherMono` after Flux succeeds | `Mono<V>` |
| `mono.thenMany(otherPublisher)` | Discarded | Emits elements of `otherPublisher` after upstream succeeds | `Flux<V>` |
| `mono.thenEmpty(otherVoidPublisher)` | Discarded | Waits for both sources to complete, emits no value | `Mono<Void>` |
| `flux.thenMany(otherPublisher)` | Discarded | Emits elements of `otherPublisher` after upstream succeeds | `Flux<V>` |

For `Flux`, there is no `Flux.thenReturn(v)` like on `Mono`. If the input is `Flux<T>` and you want to wait for all of it and then emit a fixed confirmation, use `flux.then(Mono.just(v))` or `flux.then().thenReturn(v)`.

Example returning a `Flux` after a setup operation:

~~~java
Flux<String> records = initializeAsync() // Mono<Void>
    .thenMany(Flux.just("A", "B", "C"));
~~~

`initializeAsync()` must complete successfully before `records` begins emitting data from the second source.

### How `then` Differs from `concatWith`

With `Flux.just("A").concatWith(Flux.just("B"))`, downstream can see both `"A"` and `"B"`. With `Flux.just("A").thenMany(Flux.just("B"))`, downstream sees only `"B"` — because `thenMany` **discards** elements from the first source. Both sequence stages in order, yet only one preserves data from the first stage.

## 6. Consequences of Discarding Input Values

### 6.1. Values Are Discarded at the Operator Boundary, Not “Uncomputed”

Consider:

~~~java
Mono<Void> finished = Flux.just("a", "b")
    .map(s -> s.toUpperCase())
    .doOnNext(s -> System.out.println("computed=" + s))
    .then();
~~~

`map` and `doOnNext` still process the values `"A"` and `"B"` before `then`. The final receiver only sees completion. Therefore:

- Work, logging, or side effects **already executed upstream** are not undone.
- `then` does not return a collection of values and does not retain references to all of them for later emission.
- Data is not forwarded downstream; if you need access to it after `then`, the pipeline has lost the channel carrying those values.
- Buffering operators before `then` can still consume memory; `then` does not solve every memory or I/O issue.

### 6.2. Cleaning Up Discarded Elements

Some elements are plain objects that can simply be garbage-collected by the JVM once unreferenced. However, if they hold resources requiring release (such as reference-counted buffers), actively discarding values may require cleanup.

Reactor provides `doOnDiscard(Class<R>, Consumer<? super R>)` to register a cleanup callback for **upstream operators that support discard**. The Javadoc for `then()` and `thenReturn(...)` confirms support for discarding source elements.

Illustrative example on `String` (observation only, not real resource release):

~~~java
Mono<Void> completion = Flux.just("A", "B")
    .then()
    .doOnDiscard(String.class, discarded ->
        System.out.println("discarded=" + discarded));

completion.subscribe(
    ignored -> System.out.println("unexpected value"),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Placing the hook **after the discarding operator** is intentional: `doOnDiscard` configures cleanup for supporting operators located upstream. For real resources, the callback must be **idempotent** and safe if invoked multiple times. Not every Reactor operator supports this mechanism; read the “Discard Support” section in the specific operator's Javadoc and test cancel/error paths.

For resources that own an entire lifecycle such as files, connections, or transactions, prefer scoped management with `using`/`usingWhen` or framework mechanisms; `doOnDiscard` is not a universal replacement for cleanup on completion, error, or cancellation. `doFinally` lets you observe `ON_COMPLETE`, `ON_ERROR`, and `CANCEL` for lifecycle instrumentation; it does **not** turn cancel into onComplete.

### 6.3. Cancellation, Errors, and Completion

~~~text
source --onNext(x)--> then --(does not forward x)-->
source --onComplete--> then -----------------------> downstream onComplete
source --onError(e)-> then -----------------------> downstream onError(e)

source canceled before succeeding:
  downstream cannot assume it will receive onComplete or thenReturn(value).
~~~

- With `then(Mono.just("NEXT"))`, if `source` errors, `"NEXT"` does not appear.
- If downstream cancels before source completes, cancellation can propagate upstream; already-started async tasks may require their own cancellation support. Do not infer that cancel always halts all I/O instantaneously.
- If `source` never completes, `then` will keep waiting (until canceled, timed out, or an external condition occurs).
- When upstream completes empty, `then()` still completes; `thenReturn(v)` still emits `v`; `then(other)` still subscribes to `other`.

### 6.4. `then()` Loses Information About “Whether the Previous Mono Had Data”

Both `Mono.empty().then()` and `Mono.just("X").then()` look identical downstream: a `Mono<Void>` that completes successfully. Once `then` is used, you cannot rely on a downstream `switchIfEmpty` to ask “did the original source emit an element or not”.

~~~java
Mono<String> source = findUser(); // assumed Mono<String>

// Wrong if the goal is to error when user is not found:
Mono<Void> wrong = source.then()
    .switchIfEmpty(Mono.error(
        new IllegalStateException("not found")));
// a succeeding then() is always an empty Mono, so switchIfEmpty triggers
// even when the preceding findUser() had a value.
~~~

The right way: check emptiness **before** discarding the payload:

~~~java
Mono<Void> right = source
    .switchIfEmpty(Mono.error(
        new IllegalStateException("not found")))
    .then();
~~~

Important note: `defaultIfEmpty` and `switchIfEmpty` on `Mono<Void>` after `then()` cannot recover information that was already discarded. Whenever you need to know *whether the original source emitted a value*, place the check upstream.

## 7. Complete Java 17+ Example: Observing 6 Cases in Turn

This example uses Project Reactor Core 3.8.8, Maven, and a scheduler-free program so stdout has an easily verifiable order. Project layout:

~~~text
reactor-then-demo/
├── pom.xml
└── src/main/java/example/ThenOperatorsDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-then-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ThenOperatorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/example/ThenOperatorsDemo.java`:**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ThenOperatorsDemo {

    private static <T> void observe(String name, Mono<T> source) {
        System.out.println("== " + name + " ==");
        source.subscribe(
            value -> System.out.println("next=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("complete")
        );
    }

    public static void main(String[] args) {
        observe("then", Mono.just("PAYLOAD")
            .doOnNext(value -> System.out.println("upstream=" + value))
            .then());

        observe("thenReturn", Mono.just(42)
            .doOnNext(value -> System.out.println("upstream=" + value))
            .thenReturn("ACK"));

        observe("empty thenReturn", Mono.<String>empty()
            .thenReturn("ACK_FROM_EMPTY"));

        observe("error thenReturn",
            Mono.<String>error(new IllegalStateException("FAILED"))
                .thenReturn("NEVER_EMITTED"));

        observe("then another Mono", Mono.just("FIRST")
            .doOnNext(value -> System.out.println("first=" + value))
            .then(Mono.fromSupplier(() -> {
                System.out.println("second subscribed");
                return "SECOND";
            })));

        observe("Flux then", Flux.range(1, 3)
            .doOnNext(number -> System.out.println("work=" + number))
            .then());
    }
}
~~~

Run from the `reactor-then-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
== then ==
upstream=PAYLOAD
complete
== thenReturn ==
upstream=42
next=ACK
complete
== empty thenReturn ==
next=ACK_FROM_EMPTY
complete
== error thenReturn ==
error=FAILED
== then another Mono ==
first=FIRST
second subscribed
next=SECOND
complete
== Flux then ==
work=1
work=2
work=3
complete
~~~

Analysis:

1. `then` still lets upstream `doOnNext` observe `PAYLOAD`, yet downstream receives no element.
2. `thenReturn("ACK")` does not convert 42 to a string; it **discards 42** and emits a new constant.
3. `Mono.empty()` completes successfully, so `thenReturn` still produces one output value.
4. The `FAILED` error goes straight downstream; `NEVER_EMITTED` does not appear and there is no `complete`.
5. The second stage starts after the first stage completes; the value `FIRST` does not pass through.
6. `Flux.then()` waits for all three elements to be processed by upstream before completing.

The example runs synchronously so stdout order can be verified directly. Adding `subscribeOn`, `publishOn`, or async sources can change execution threads and ordering across independent subscriptions.

## 8. Applying in Spring WebFlux

### 8.1. Chaining Sequential Tasks Without Needing the First Payload

In a service, suppose `validate(command)` returns `Mono<Void>` (completing only if valid) and `persist(command)` returns `Mono<SavedOrder>`. If the HTTP response only needs confirmation that processing succeeded, you can write:

~~~java
// Illustrative snippet inside a service/controller with Spring WebFlux dependencies.
// validate and persist are assumed to be defined business methods.
Mono<ResponseEntity<String>> submit(OrderCommand command) {
    return validate(command)
        .then(persist(command))
        .thenReturn(ResponseEntity.accepted().body("accepted"));
}
~~~

Lifecycle:

1. Once `validate` completes successfully, `persist` is subscribed.
2. Once `persist` completes successfully, `thenReturn` emits the response.
3. If either stage errors, downstream receives the error rather than the confirmation response in step 2 or 3.
4. The `SavedOrder` data produced by `persist` is discarded. That is only suitable if the response needs neither the ID nor fields of the record.

**Important boundary:** HTTP 202 Accepted is a business decision, not a status code generated by `thenReturn` itself. The controller must return `ResponseEntity` or configure the appropriate status.

### 8.2. If You Need the Saved Value, Use `flatMap` or `map`

~~~java
Mono<ResponseEntity<String>> submitWithId(OrderCommand command) {
    return validate(command)
        .then(persist(command))
        .map(saved -> ResponseEntity.ok("id=" + saved.getId()));
}
~~~

This example still uses `then` to ensure `validate` runs before `persist`, yet **retains** the result of `persist` because `map` operates on the Publisher returned by `then(persist(command))`.

If `persist` completes empty without saving anything, `map` does not run. If business logic requires a record, add `switchIfEmpty` on `persist` or right after `then(persist(...))` before `map` to convert absence into an explicit error.

### 8.3. Using `Mono<Void>` for Completion-Only Operations

~~~java
Mono<Void> deleteAndAudit(String id) {
    return repository.deleteById(id)
        .then(auditService.recordDeletion(id));
}
~~~

Here `deleteById` and `recordDeletion` must return publishers whose completion semantics match the contract. `then` ensures subscription order and error propagation; it does not create a transaction across two systems on its own. If atomic transactions or compensating actions on error are required, design them separately.

In WebFlux handlers, **return the publisher** so the framework manages subscription, errors, and cancellation. Do not call `subscribe()` manually inside a request handler just to “trigger” an operation, because doing so detaches the lifecycle from the response and breaks cancel/error coordination.

## 9. When to Choose `then`, `thenReturn`, or Another Operator?

| Need | Suitable approach | Notes |
| --- | --- | --- |
| Wait to finish, data not needed | `source.then()` | Type `Mono<Void>`; preserves errors |
| Wait for Mono success then return fixed confirmation | `source.thenReturn("OK")` | Even when source is empty |
| Wait for source then start another Mono | `source.then(otherMono)` | If source errors, next stage does not run |
| Wait for Flux then return one value | `flux.then(Mono.just(value))` | `Flux` has no `thenReturn` |
| Wait for source then emit multiple other elements | `source.thenMany(otherFlux)` | Discards data of first source |
| Transform the original value itself | `source.map(value -> ...)` | Requires upstream to actually emit an element |
| Create a new stage based on the original value | `source.flatMap(value -> service.call(value))` | Skipped for empty sources |
| Inspect while keeping elements | `doOnNext(...)` | Observation only, does not alter payload |
| Error if no record exists | `source.switchIfEmpty(Mono.error(...))` **before** `then` | Check before emptiness info is lost |
| Result value must be computed after success | `source.then(Mono.fromSupplier(...))` | Computed when the later stage is subscribed |
| Want to handle errors with a fallback | `onErrorResume(...)`, intentionally | `then` does not swallow errors |

Quick selection rule: **do you still need the payload?** If yes, continue with `map`/`flatMap`; if you only need successful completion, `then`; if after completion you want to emit an already-available fixed object, `thenReturn`.

## 10. Common Mistakes and How to Avoid Them

**Mistake 1 — Thinking `thenReturn` transforms data.** `Mono.just(7).thenReturn(99)` emits 99, not a result computed from 7. To compute from 7, use `map`.

**Mistake 2 — Assuming `then()` swallows errors.** `Mono.error(e).then()` still errors. Only intentional error-handling operators change the error path, and they must be chosen per business rules.

**Mistake 3 — Treating an empty source as a failure.** `Mono.empty().thenReturn("OK")` emits OK. If “no record” must be a 404 or domain error, use `switchIfEmpty` **before** `then`.

**Mistake 4 — Using `then` and then trying to read the upstream value.** The data was discarded at this boundary; redesign operator order so `map`/`flatMap` runs where the payload is still present.

**Mistake 5 — Calling `thenReturn(expensive())` intending `expensive` to run after source completes.** The Java expression runs at assembly. Use `then(Mono.fromSupplier(...))` or `Mono.defer` to defer it.

**Mistake 6 — Confusing `Mono<Void>` with `Mono.just(null)`.** `Mono<Void>` completes with `onComplete` without an element; it does not emit `null`.

**Mistake 7 — Assuming discard automatically releases every resource.** Objects with external resources may need cleanup hooks, `using/usingWhen`, or explicit ownership policies; dropping references alone does not guarantee closing resources.

**Mistake 8 — Using `then()` to optimize an expensive chain of work.** Upstream is still subscribed and typically still emits and processes elements. If the goal is to avoid unnecessary work, change the source structure or trigger condition.

**Mistake 9 — Calling `subscribe` in a controller and returning `Mono.just("OK")`.** This can return OK before the task actually finishes and breaks error/cancellation propagation. Use `return serviceCall().thenReturn("OK")` so the response properly depends on completion.

**Mistake 10 — Thinking cancel is successful completion.** `cancel()` does not emit `onComplete`; `thenReturn` must not be treated as having succeeded when the source did not complete.

## 11. Self-Check Exercises and Answers

1. What does `Mono.just("X").then()` send downstream? **Answer:** Only `onComplete`; no `onNext`.
2. Does `Mono.empty().thenReturn("A")` emit `"A"`? **Yes**, because the source completed successfully.
3. Does `Mono.error(new RuntimeException("E")).thenReturn("A")` emit `"A"`? **No**, downstream receives error `E`.
4. To call `charge(savedOrder)` using the object returned by `save(order)`, choose `then` or `flatMap`? **`flatMap(savedOrder -> charge(savedOrder))`**, because the source payload is needed.
5. Does `Flux.range(1, 3).then()` stop after number 1? **No**; the source keeps running until completion, error, or cancellation.
6. Can placing `switchIfEmpty` after `Mono<Void>.then()` tell whether the original source had no element? **No**. That check must happen before `then()`.
7. To call `generateReceipt()` after `save` succeeds **on every subscription**, use `thenReturn(generateReceipt())` or `then(Mono.fromSupplier(...))`? **`then(Mono.fromSupplier(() -> generateReceipt()))`** to defer computation.

## 12. Reference Material

- [Project Reactor API – Mono: then, thenReturn, thenMany, thenEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): signatures, error propagation, discarding source elements, and result Publisher types.
- [Project Reactor API – Flux: then and thenMany](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): discarding all `Flux` elements, waiting for completion, and emitting the next source.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onError` as a terminal signal, how to use error-handling operators.
- [Project Reactor Reference – Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): comparing transformations, chaining streams, and handling completion.
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): rules for `onNext`/`onComplete`/`onError`, backpressure, and cancellation.