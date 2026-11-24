# Impact of `empty` or `Mono<Void>` Sources in `zip` (Spring WebFlux / Reactor)

## 1. Core Rule: `zip` Needs **One Value from Each Source**

In Project Reactor, `Mono.zip(a, b)`, `a.zipWith(b)`, and `a.zipWhen(...)` are used to **combine results that carry values**. With `Mono`, each source emits at most one element via `onNext`; `zip` creates a tuple or invokes the combinator function only when **all involved sources have emitted an element**. A stream that completes successfully **without emitting `onNext`** is called `empty`.

That creates an easy point of confusion:

- `Mono.just("A")` emits `"A"` then completes: there is data for `zip` to combine.
- `Mono.<String>empty()` emits only `onComplete`: there is **no value** for `zip` to combine.
- `Mono<Void>` is a type used to signal **completion or failure of an operation**, carrying no ordinary data element; inside `zip`, it behaves as a source **with no value**.
- When any source ends empty, regular `zip` **completes empty**; it does not call the combinator and may **cancel other sources** that have started. This is not an error (it does not emit `onError` on its own).
- If a source signals an error, regular `zip` emits an error and may cancel the remaining sources. Error and empty are **two distinct signals**.

Keep **“completed successfully”** clearly separated from **“completed with a value”**: `zip` requires the second case from every source. This is the operator's contract, not a Spring WebFlux-specific quirk.

## 2. Signal-Level Illustration: Why Doesn't the Combinator Run?

### Both Monos have values

~~~text
Mono.just("An")  : onNext("An") ────── onComplete
Mono.just(20)    : onNext(20) ──────── onComplete
Mono.zip(...)    : onNext(("An", 20)) ─ onComplete
~~~

Both sources supply an element, so `zip` can construct `Tuple2<String, Integer>` or call a `BiFunction` to produce any desired result.

### One Mono completes empty

~~~text
Mono.empty()     : onComplete  (no onNext)
Mono.just(20)    : may be subscribed or skipped/cancelled depending on timing
Mono.zip(...)    : onComplete  (no onNext, no tuple created)
~~~

You cannot build a tuple containing `null` and `20`: Reactive Streams forbids `null` as an `onNext` element, and `zip` does not automatically replace an empty source with a default value.

### One `Mono<Void>` source

~~~text
save().then()    : runs save, signals only onComplete on success
getProfile()     : expected to return a Profile
Mono.zip(...)    : no tuple, because the first source emits no element
~~~

For example, `Mono<Void> save = repository.save(entity).then();` can still genuinely save data; **discarding the value** is the exact purpose of `then()`. However, if you combine `save` with another source via `zip`, `save` will never supply a value to combine.

**Note on source subscription:** after one source completes empty, some branches in `zip` — especially with synchronous empty sources or nested `zip` structures — may **never be subscribed to**. If already subscribed, they may be cancelled. Therefore, you must not rely on `zip` to guarantee that every side-effecting operation (saving, sending notifications, logging, calling APIs) runs to completion.

## 3. Related Operators and Causes of Missing Values

| Expression / operator | Data on successful completion | Impact when used as a `zip` source |
| --- | --- | --- |
| `Mono.just("A")` | One value `"A"` | Can be zipped with another value-emitting source |
| `Mono.empty()` | No value | `zip` completes empty |
| `Mono<Void>` | No value | `zip` completes empty |
| `mono.then()` | Drops prior `onNext`; keeps only completion/error | Supplies no value to `zip` |
| `mono.thenEmpty(other)` | Emits only completion/error | Supplies no value to `zip` |
| `mono.ignoreElement()` or `flux.ignoreElements()` | Drops elements; keeps only completion/error | Supplies no value to `zip` |
| `Mono.when(a, b)` | `Mono<Void>` waiting for publishers to complete | Still empty when used as a `zip` source |
| `mono.thenReturn("done")` | Emits `"done"` after the initial mono completes successfully | Can be zipped if a sentinel makes sense |
| `mono.defaultIfEmpty(fallback)` | Emits fallback if a source of type `T` is empty | Can be zipped with the fallback |
| `mono.singleOptional()` | Emits an `Optional<T>`, including `Optional.empty()` | Allows zipping even when the original source is empty |

`Mono<Void>` is a special case: **there is no valid `Void` value to emit as `onNext`**. Consequently, `Mono<Void>.defaultIfEmpty(...)` and `switchIfEmpty(...)` cannot produce a non-`null` value of type `Void` for `zip`; `null` is illegal. If you need an element representing completion, **change the type** using `thenReturn(sentinel)` or map to a value-carrying result type.

## 4. `zipWith` and `zipWhen` Have Empty Pitfalls Too

Suppose you write:

~~~java
// Illustrative only: process returns Mono<Void>.
Mono<Void> first = service.process("A");
Mono<Void> second = service.process("B");

first.zipWith(second, (a, b) -> "done")
     .subscribe(System.out::println);
~~~

The function `(a, b) -> "done"` **never runs**, because neither `a` nor `b` is emitted. Switching to `Mono.zip(first, second)` does not fix it either; to **wait for two tasks**, use `Mono.when(first, second)`.

With `zipWhen`, the second parameter is a **function building the next Mono** from the left-side element. If the left side is empty, that function **is not invoked**:

~~~java
Mono<String> id = Mono.empty();

Mono<?> result = id.zipWhen(value -> service.lookup(value));
~~~

`service.lookup` in the example is just an illustrative name; this snippet is not a standalone program. To invoke `rightGenerator`, `zipWhen` needs `value` from `id`. With no `onNext(value)`, there is no `lookup` call. Conversely, if the left side has a value yet the right-hand Mono completes empty, the entire `zipWhen` also completes empty.

**Important:** `zipWhen` does not mean “run a function after the left side completes”; it means “when the left side **emits a value**, use that value to build another Mono and zip both values”.

## 5. Runnable Java 17+ Example: Empty `zip` Results and Fixes

This example uses Reactor Core directly without Spring Boot. Create the structure:

~~~text
reactor-zip-empty/
├── pom.xml
└── src/main/java/ZipEmptyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-zip-empty</artifactId>
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

File `src/main/java/ZipEmptyDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class ZipEmptyDemo {
    public static void main(String[] args) {
        // 1) Two sources with values: produces a result.
        var both = Mono.zip(
            Mono.just("A"), Mono.just("B"),
            (left, right) -> left + "-" + right
        );
        System.out.println("zip values = " + both.blockOptional());

        // 2) One empty source: result remains empty, no tuple emitted.
        var oneEmpty = Mono.zip(
            Mono.<String>empty(), Mono.just("B"),
            (left, right) -> left + "-" + right
        );
        System.out.println("zip empty = " + oneEmpty.blockOptional());

        // 3) No left value: zipWhen does not call rightGenerator.
        AtomicInteger calls = new AtomicInteger();
        var dynamic = Mono.<String>empty().zipWhen(left -> {
            calls.incrementAndGet();
            return Mono.just(left.length());
        });
        System.out.println("zipWhen = " + dynamic.blockOptional());
        System.out.println("right factory calls = " + calls.get());

        // 4) Mono<Void> completes with no data to zip.
        Mono<Void> completedWithoutValue = Mono.empty();
        var withVoid = Mono.zip(completedWithoutValue, Mono.just(7));
        System.out.println("zip Mono<Void> = " + withVoid.blockOptional());

        // 5) Empty String source: use a meaningful fallback value.
        var withFallback = Mono.zip(
            Mono.<String>empty().defaultIfEmpty("guest"),
            Mono.just("viewer"),
            (name, role) -> name + ":" + role
        );
        System.out.println("defaultIfEmpty = " + withFallback.blockOptional());

        // 6) Void-typed completing source: produce a value AFTER completion.
        var withCompletionValue = Mono.zip(
            completedWithoutValue.thenReturn("saved"),
            Mono.just("viewer"),
            (status, role) -> status + ":" + role
        );
        System.out.println("thenReturn = " + withCompletionValue.blockOptional());

        // 7) Two completion-only tasks: use when instead of zip.
        AtomicInteger writes = new AtomicInteger();
        AtomicInteger audits = new AtomicInteger();
        Mono<Void> write = Mono.fromRunnable(() -> {
            writes.incrementAndGet();
        });
        Mono<Void> audit = Mono.fromRunnable(() -> {
            audits.incrementAndGet();
        });
        Mono.when(write, audit).block();
        System.out.println("when counts = " + writes.get() + "," + audits.get());
    }
}
~~~

From the `reactor-zip-empty` directory, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ZipEmptyDemo
~~~

**Output printed by the program** (additional Maven logs may appear depending on environment):

~~~text
zip values = Optional[A-B]
zip empty = Optional.empty
zipWhen = Optional.empty
right factory calls = 0
zip Mono<Void> = Optional.empty
defaultIfEmpty = Optional[guest:viewer]
thenReturn = Optional[saved:viewer]
when counts = 1,1
~~~

The `blockOptional()` calls in the example are solely so the console program clearly shows **“has a result”** (`Optional[value]`) or **“completed empty”** (`Optional.empty`). **Never use `block()`/`blockOptional()` on the WebFlux event-loop processing path**; in reactive controllers/services, return `Mono` and let the framework subscribe.

The `Mono.when(write, audit)` section ensures both `Mono<Void>` tasks complete successfully before the print statement reads the counters. Ordering the two callbacks in an asynchronous environment is not the goal of this example; if task B **must** start after A, use `A.then(B)`.

## 6. Choosing the Solution Based on Actual Intent

There is no single “fix for empty zip” that fits every business rule. Ask: **do we want to combine values, wait for completion, force every source to run, or execute sequentially?**

### Case A — A result may be absent, yet needs to be zipped with a default value

If the source has a useful data type, such as a `Mono<String>` that may be empty:

~~~java
Mono<String> displayName = findNameById(id);
Mono<String> locale = loadLocale();

Mono<String> label = Mono.zip(
    displayName.defaultIfEmpty("Guest"),
    locale,
    (name, region) -> name + "@" + region
);
~~~

This is an illustrative snippet inside a service where `findNameById` and `loadLocale` are implemented, not a standalone program. If `displayName` is empty, the fallback `"Guest"` is **emitted as a value** and `zip` can construct the label, provided `locale` also emits a value.

You can use `switchIfEmpty(Mono.just("Guest"))` when falling back to another publisher. Only configure a fallback when the business contract permits it; **never fabricate a fake name or valid-looking object** to hide missing data. If missing data is an error, choose `switchIfEmpty(Mono.error(new IllegalArgumentException("missing name")))` to surface an explicit error.

### Case B — Must distinguish “data present” from “data absent”

Use `singleOptional()` to represent both cases as **an `Optional<T>` value**. Each new source then always emits **one Optional**, including `Optional.empty()`.

~~~java
// Example requiring Reactor dependency, not a standalone runnable class.
Mono<String> first = Mono.empty();
Mono<Integer> second = Mono.just(42);

Mono<String> combined = Mono.zip(
    first.singleOptional(),
    second.singleOptional(),
    (a, b) -> "first=" + a + ", second=" + b
);
// combined emits: "first=Optional.empty, second=Optional[42]"
~~~

`singleOptional()` is especially helpful when **all sources must be subscribed to** while one source might be empty. Reactor's FAQ notes that with nested `zip`, an early empty source can prevent some other sources from being subscribed to. Wrapping each source into `Mono<Optional<T>>` before zipping lets each branch emit an Optional value, so `zip` subscribes to all branches needed to build the result.

**Be careful:** being subscribed to **does not mean** every task completed successfully: errors, active cancellation, timeouts, or external source failures can still alter the lifecycle. `Optional` represents absence; it does not turn errors into success.

### Case C — Have `Mono<Void>` and only need tasks to finish

Use `Mono.when` when you need to **wait for all sources to finish** without needing a data tuple:

~~~java
Mono<Void> saved = saveOrder(order);
Mono<Void> audited = recordAudit(order);

Mono<Void> completed = Mono.when(saved, audited);
~~~

This is an illustrative service structure. `when` subscribes to the publishers and returns a `Mono<Void>` that **completes when all complete successfully**; sources completing empty is the normal case. If one source errors, regular `when` fails fast and may cancel the remaining sources.

If business logic requires **waiting for sources to finish even when an error occurs**, look at `Mono.whenDelayError(...)` and establish an error-handling policy after all have stopped; do not treat it as an automatic way to ignore errors.

If operation B depends on A's completion, use:

~~~java
Mono<Void> sequence = saveOrder(order).then(recordAudit(order));
~~~

`then(other)` subscribes to `other` **only after** the first source completes successfully; if the first errors, the next step does not run. This expresses ordering far more clearly than `zip` or `when`.

### Case D — Need to wait for a `Mono<Void>` task then zip a “done” signal

When you truly want to combine task results and one task only signals completion:

~~~java
Mono<Void> save = saveOrder(order);
Mono<String> receipt = save.thenReturn("saved");

Mono<String> response = Mono.zip(
    receipt,
    loadCorrelationId(),
    (status, correlation) -> status + ":" + correlation
);
~~~

`thenReturn("saved")` emits its value only after `save` completes **successfully**; if `save` errors, the error propagates and `"saved"` is never emitted. `"saved"` is a **new programmer-defined value**, not a value emitted by `Mono<Void>`.

**Limitation:** you still have to mind `zip` semantics: if `loadCorrelationId()` completes empty before `save` finishes, `save` may be cancelled. If saving **must** succeed **before** fetching the ID, chain sequentially via `save.then(loadCorrelationId())`; if multiple side effects must all finish together, use `when` for the side effects followed by `then(...)` to produce the result. Do not use `thenReturn` as a way to guarantee an important branch is never cancelled when another branch is empty.

### Case E — Want to delay errors while still letting all sources finish

`Mono.zipDelayError(...)` differs from `Mono.zip(...)` in that it **delays errors** and, per Reactor's contract, if one source completes empty, the remaining sources are still allowed to finish before `zipDelayError` completes empty. It still **cannot form a tuple** when a value is missing. One or more errors can be reflected in the final error signal afterward, rather than silently turned into empty.

Choose `zipDelayError` only when you specifically need value zipping with error aggregation; for completion-only tasks, `when` or `whenDelayError` conveys the intent much more clearly.

## 7. Quick Selection Table

| Goal | Recommended | Misconception to avoid |
| --- | --- | --- |
| Combine **values** from multiple value-bearing `Mono<T>` sources | `Mono.zip`, `zipWith` | One empty source makes the result empty |
| Compute a second source from the first source's value | `zipWhen` or `flatMap` as needed | When the left side is empty, the factory for the second source does not run |
| Data Mono may be absent, fallback allowed | `defaultIfEmpty`, `switchIfEmpty` before `zip` | Do not invent a misleading sentinel value |
| Need to observe empty cases too | `singleOptional()` then `zip` | Result contains `Optional<T>`, not `T` |
| Wait for multiple `Mono<Void>` tasks to finish | `Mono.when` | Result is `Mono<Void>`, not a tuple |
| Run B after A finishes | `A.then(B)` | `when` does not express ordering dependencies |
| Convert completion-only to a meaningful value | `thenReturn(value)` | Does not stop another branch in `zip` from cancelling early |
| Wait for multiple sources on error; aggregate errors | `whenDelayError` or `zipDelayError` per goal | `zipDelayError` is still empty if a value is missing and no error occurred |

## 8. Common Cases in Spring WebFlux

Suppose an API performs two actions: **saving an order** returning `Mono<Void>`, and **recording an audit** returning `Mono<Void>`. The code below is an easy mistake:

~~~java
// Example is not a standalone Spring Boot app.
// Both methods return Mono<Void>.
Mono<Void> save = orderService.saveOrder(order);
Mono<Void> audit = auditService.record(order);

Mono<?> wrong = Mono.zip(save, audit);
~~~

Looking at `wrong`, one might assume `zip` will always run both tasks and emit a result. In practice, if one source completes empty early, `zip` can finish first and cancel or skip subscribing to the other branch. Moreover, **no tuple** is emitted because both are `Mono<Void>`.

Choose accurately according to business logic:

~~~java
// Want both operations launched and awaited for successful completion:
Mono<Void> bothDone = Mono.when(
    orderService.saveOrder(order),
    auditService.record(order)
);

// Want to record audit ONLY AFTER saving the order completes:
Mono<Void> inOrder = orderService.saveOrder(order)
    .then(auditService.record(order));

// Want to return a status after both complete:
Mono<String> response = Mono.when(
    orderService.saveOrder(order),
    auditService.record(order)
).thenReturn("OK");
~~~

These expressions fit reactive services or controller return values. In Spring WebFlux, **return the `Mono`** so the framework subscribes and manages cancellation with the request lifecycle; avoid calling `block()` or manually calling `subscribe()` in a controller just to force tasks to run. If processing must be guaranteed even if the client disconnects, the business design must use reliable mechanisms (transactions, outbox, queues, controlled retry/idempotency), rather than relying on a `zip` branch happening to be subscribed.

Another bug arises when trying to zip data after `then()`:

~~~java
Mono<User> user = userRepository.findById(id);
Mono<Void> logged = logAction(id);

Mono<?> bad = Mono.zip(user, logged); // logged emits no value

// If logging must complete before returning User:
Mono<User> good = logged.then(user);
~~~

This is an illustrative service example. If `user` is empty, `good` is still empty; the difference is that **the log operation is awaited to complete successfully** before querying the user. If you want to fetch data first and log only when a user exists, use `user.flatMap(u -> logAction(id).thenReturn(u))`; when `user` is empty, `flatMap` does not run, which fits if that is the business rule.

## 9. Debugging and Verifying Empty Behavior

When observing a `zip` pipeline whose combinator never runs, check step by step:

1. **Does each source actually emit `onNext`, or only `onComplete`?** Use `doOnNext`, `doOnSuccess` (note that `Mono`'s `doOnSuccess` receives `null` on empty completion), `doOnError`, and signal logging to distinguish.
2. **Did an operator strip data before `zip`?** Common culprits are `then()`, `ignoreElement(s)`, `thenEmpty(...)`, and `when(...)`.
3. **Is the actual type `Mono<Void>`?** If it only represents completion, do not expect it to emit a value.
4. **Is `zipWhen` receiving an empty left source?** In that case, the second-source builder function will not run.
5. **Was another branch unsubscribed or cancelled?** `doOnSubscribe`, `doOnCancel`, and `doFinally` help observe this; do not infer subscription merely from calling a publisher-factory method.
6. **Is empty handled in the right place?** Put `defaultIfEmpty`, `switchIfEmpty`, or `singleOptional` on the appropriate source **before `zip`**.
7. **Was empty confused with error?** `switchIfEmpty` reacts to an empty source; `onErrorResume` reacts to an error. The two operators solve different situations.
8. **Must all side effects complete successfully?** Use `Mono.when`/a `then` chain with appropriate reliability mechanisms; do not rely on unguaranteed subscription ordering in `zip`.

You can test directly (with `reactor-test` and `StepVerifier` in test scope):

~~~java
// Illustrative test snippet; requires reactor-test in test scope.
StepVerifier.create(Mono.zip(Mono.<String>empty(), Mono.just("B")))
    .verifyComplete(); // No expectNext, because zip is empty.

StepVerifier.create(
    Mono.zip(
        Mono.just("A"),
        Mono.just("B"),
        (a, b) -> a + b
    )
).expectNext("AB").verifyComplete();
~~~

If you need to prove **whether a branch was subscribed to**, check an `AtomicInteger` via `doOnSubscribe` in a dedicated test; however, do not assert that every `zip` structure, completion order, and Reactor version must subscribe to every source. Skipping a branch once it is already known no result can be formed is valid behavior.

## 10. Self-Check Questions

**1. What tuple does `Mono.zip(Mono.just(1), Mono.empty())` return?** No tuple is returned. The result completes empty; the second source provides no element to combine.

**2. Does a `Mono<Void>` completing successfully count as a value?** No. `onComplete` signals completion, not `onNext`.

**3. Why does `source.then().zipWith(other)` not invoke the combinator?** Because `then()` intentionally discards elements from `source`, leaving the left side with no value.

**4. If you need to wait for both saving data and sending an audit to finish, what should you use?** `Mono.when(save, audit)` for independent tasks that only need to complete, or `save.then(audit)` when the audit must wait for the save.

**5. If a `Mono<String>` can be empty yet you still want to zip it with a default value, what should you do?** Use `defaultIfEmpty("appropriate value")` on the source before zipping; do not apply this directly to `Mono<Void>`.

**6. How can you distinguish whether values exist or are absent while still zipping?** Use `singleOptional()` and zip the resulting `Mono<Optional<T>>` streams so `Optional.empty()` becomes a valid value.

**7. Does `zipDelayError` automatically generate a value when one branch is empty?** No. It can wait for other branches to finish, yet if there are no errors and one source emits no value, the result is still empty.

**Key takeaway:** `zip` combines **values**, not **completion notifications**. A `Mono.empty()` or `Mono<Void>` can cause `zip` to complete empty, prevent the combinator from running, and leave other tasks cancelled or unsubscribed. Choose `defaultIfEmpty`, `singleOptional`, `thenReturn`, `Mono.when`, or `then` according to the **business contract** you need to express, rather than forcing every workflow into `zip`.

**References:** [Project Reactor FAQ — My Mono zipWith or zipWhen is never called](https://projectreactor.io/docs/core/release/reference/faq.html#faq.zip.empty); [Reactor Mono JavaDoc — zip / zipDelayError / when](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).