# filter, filterWhen, and Handling Invalid Values

**Module:** Spring Framework – reactive  
**Parent topic:** Data Transformation

## Lesson Objectives

After this lesson, you will be able to:

1. Use `Mono`/`Flux` `filter` to retain elements based on a **synchronous** condition, and understand what signal a filtered-out value becomes.
2. Use `filterWhen` when the condition requires a **reactive** operation returning `Publisher<Boolean>`, such as checking permissions or looking up configuration from another service.
3. Distinguish four situations: **not matching a condition**, **no data**, **invalid input value**, and **error during checking**. Each situation has a different business meaning and handling path.
4. Choose the appropriate behavior: drop the element, convert to an error with a message, return a fallback value, or retain the rejection reason.
5. Build pipelines following Reactor semantics without blocking the event loop or swallowing errors; know how to apply these in Spring WebFlux.

## 1. Where Does Filtering Sit in a Reactive Pipeline?

In Reactor, `Flux<T>` is a publisher that can emit multiple values, and `Mono<T>` emits at most one value. Operators such as `map`, `filter`, and `filterWhen` create a **new publisher**. They do not mutate the dataset in place; upon subscription, data and signals flow through the operators.

```text
                  onNext(v1) ─┐
Source Flux<T> → onNext(v2) ──┼─→ filter / filterWhen ─→ retained values
                  onNext(v3) ─┘                       └→ discarded values: no onNext emitted
                    onComplete ──────────────────────→ onComplete
                         onError ────────────────────→ onError (unless error is explicitly handled)
```

Example:

```java
Flux<Integer> values = Flux.just(1, 2, 3, 4, 5);
Flux<Integer> even = values.filter(number -> number % 2 == 0);
// When a subscriber requests enough data: even emits 2, 4 then onComplete.
```

This is an **illustrative snippet**, assuming `reactor.core.publisher.Flux` is imported. Odd numbers are dropped—they do not turn into `null`, empty strings, or errors. The resulting sequence is a `Flux<Integer>`, not an eagerly computed Java list. To collect at a synchronous boundary for experimentation, you can use `collectList().block()`; in a WebFlux handler, you normally **return the publisher** and do not call `block()`.

Filtering also affects demand (backpressure). If downstream requests two **accepted** elements while many initial elements are discarded, the operator may need to request more data from upstream to satisfy demand. Do not infer that a single downstream `request(2)` corresponds to exactly two elements pulled from the source. In a larger pipeline, `prefetch` and other operators also affect request counts.

## 2. `filter`: Synchronous Conditions

Common signatures:

```java
Flux<T> filter(Predicate<? super T> predicate)
Mono<T> filter(Predicate<? super T> predicate)
```

`Predicate<T>` is a function that takes a `T` and returns a `boolean`. For each `onNext(value)`:

- Returns `true` → keeps `value` and emits it downstream.
- Returns `false` → drops `value` and emits no `onNext` signal for that element.
- Predicate throws an exception → normally the error signal travels downstream, rather than being treated as a normal `false` result. Do not use exceptions as a “filter condition” when you can return `false` or handle errors at the right scope.

### 2.1. Filtering After Data Normalization

```java
Flux<String> names = Flux.just("  An  ", " ", " Binh ", "Linh");
Flux<String> validNames = names
        .map(String::trim)
        .filter(name -> !name.isBlank())
        .filter(name -> name.length() >= 3);
// When consumed: "Binh", "Linh"
```

This is an **illustrative snippet**; `map(String::trim)` produces new data before applying conditions. Dropping empty/blank strings and short lengths is an example business rule. Note the ordering: if leading/trailing whitespace must be stripped, `trim` must run before checking length.

### 2.2. `Mono.filter` Can Turn a Valued Mono into an Empty Mono

```java
Mono<Integer> quantity = Mono.just(-5)
        .filter(value -> value > 0);
// quantity completes successfully with no onNext (Mono.empty).
```

`Mono.empty()` is not `Mono.error(...)`. For an input failing the condition, `filter` only **drops the element**; it does not automatically send an “invalid quantity” message to the client. You must distinguish an invalid value from data that does not exist.

### 2.3. Predicates Should Be Short, Pure, and Non-Blocking

`filter(item -> item.isActive())` is good filtering when all required data is already in memory. Conversely, do not call HTTP, blocking JDBC, `Thread.sleep(...)`, or `block()` inside a predicate on a WebFlux request. Such calls run on the pipeline execution thread, can block the event loop, reduce throughput, or throw errors because blocking is disallowed. If the condition needs async I/O, consider `filterWhen`; if only a blocking API exists, you need a dedicated scheduler/resource isolation strategy—do not pretend work is non-blocking simply by calling `subscribe()`.

## 3. `filterWhen`: Reactive/Asynchronous Conditions

`Flux` signatures:

```java
Flux<T> filterWhen(Function<? super T, ? extends Publisher<Boolean>> asyncPredicate)
Flux<T> filterWhen(Function<? super T, ? extends Publisher<Boolean>> asyncPredicate,
                   int bufferSize)
```

`Mono` also provides `filterWhen(Function<? super T, ? extends Publisher<Boolean>>)`. The lambda **returns a publisher of Boolean**, typically a `Mono<Boolean>` from a reactive service. Do not pass a raw `boolean` directly to `filterWhen`:

```java
Flux<User> permitted = users.filterWhen(user ->
        permissionService.canView(user.id())); // assumed to return Mono<Boolean>
```

This is an **integration illustrative snippet**: the application needs to define `User`, `users`, and `permissionService`. `filterWhen` creates and subscribes to the check publisher for each element as the pipeline is consumed.

### Exactly When Does It Keep an Element?

For a source element `item`, the outcome from the test publisher decides:

| Test publisher emits | Result of `filterWhen` |
| --- | --- |
| First Boolean value is `true` | Keeps `item`. |
| First Boolean value is `false` | Drops `item`. |
| Completes empty, emits no Boolean | Drops `item` (treated as no allow decision). |
| Emits multiple Booleans | Only the **first** Boolean is considered; for a non-`Mono` test publisher, it may be canceled after the first value. |
| Emits `onError` | The error normally travels down the pipeline; it is **not** automatically converted to `false`. Choose an explicit error-handling policy. |

This is an important contract: `Mono.empty()` from a check service does not mean “wait longer for an answer”; it is an **empty completion**, so the element is filtered out. If a decision is mandatory, convert empty results into an error or an intentional default decision inside the service.

### 3.1. Checking Permissions Using a Reactive Source

```java
Flux<Document> visible = documentRepository.findAll()
        .filterWhen(document ->
                accessService.canRead(currentUserId, document.id()));
```

This is an **illustrative snippet**, assuming the repository returns `Flux<Document>`, `canRead` returns `Mono<Boolean>`, and the components are defined by the application. If permission for document A returns `true`, A is kept; if document B returns `false`, B is dropped; an error calling the authorization service must be handled per an explicit policy rather than silently becoming “no permission” without recording it.

Using `filterWhen` makes particular sense when the business meaning is **selecting a result set**: for instance, showing only viewable documents in a list. For an endpoint accessing **one specific document**, excluding data may need to become HTTP 403 or 404 per security policy, instead of silently returning an empty response.

### 3.2. Execution, Ordering, and Buffering

According to the Reactor API, with `Flux.filterWhen`, test publishers are created and subscribed **sequentially in order**; this is **not** a fan-out operator that automatically runs hundreds of checks in parallel. `bufferSize` tunes how many elements can be held awaiting check results and the initial request size from upstream (rounding/bounding details depend on the version); it does **not** mean the number of check tasks running concurrently. Choose buffer size based on real measurements to avoid holding too many objects in memory.

If you need to check multiple elements **concurrently** while still preserving output order, you can design it with bounded-concurrency `flatMapSequential`:

```java
Flux<Item> kept = items.flatMapSequential(item ->
        asynchronousTest(item)
                .filter(Boolean::booleanValue)
                .map(allowed -> item),
        8); // at most eight inner publishers subscribed concurrently
```

This is an **illustrative snippet**, assuming `asynchronousTest(item)` returns `Mono<Boolean>`. When the Boolean result is `false` or the publisher is empty, the inner publisher emits no `Item`; when `true`, it emits `item`. `flatMapSequential` can process inner publishers concurrently while emitting results in input order; resource costs differ from `filterWhen` and require evaluating concurrency limits, timeouts, ordering, and per-task errors.

## 4. Runnable Java 17+ Example: All Three Decision Types

This CLI example runs standalone without Spring WebFlux, using **Project Reactor Core 3.8.8** and **Java 17+**. `block()` appears only in `main` to demonstrate ordered output; do not copy `block()` into a WebFlux controller.

Create the layout:

```text
reactive-filter-demo/
├── pom.xml
└── src/main/java/demo/
    └── FilterWhenDemo.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>reactive-filter-demo</artifactId>
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

### `src/main/java/demo/FilterWhenDemo.java`

```java
package demo;

import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class FilterWhenDemo {
    public static void main(String[] args) {
        // 1. Synchronous predicate: normalize and filter strings.
        List<String> names = Flux.just(" An ", " ", " Binh ", "Linh")
                .map(String::trim)
                .filter(name -> !name.isBlank())
                .filter(name -> name.length() >= 3)
                .collectList()
                .block();
        System.out.println("filter = " + names);

        // 2. Reactive predicate: each decision comes from a Mono.
        List<Integer> even = Flux.range(1, 5)
                .filterWhen(number ->
                        Mono.delay(Duration.ofMillis(10))
                                .map(tick -> number % 2 == 0))
                .collectList()
                .block();
        System.out.println("filterWhen = " + even);

        // 3. An empty test Publisher also drops the element.
        List<Integer> selected = Flux.range(1, 4)
                .filterWhen(number ->
                        number == 3
                                ? Mono.<Boolean>empty()
                                : Mono.just(number % 2 == 1))
                .collectList()
                .block();
        System.out.println("empty decision = " + selected);

        // 4. Batch processing requirement: skip records that fail to parse,
        // while continuing to read the remaining records.
        List<Integer> parsed = Flux.just("12", "oops", "-2", "7")
                .concatMap(raw ->
                        Mono.fromCallable(() -> Integer.parseInt(raw))
                                .onErrorResume(NumberFormatException.class,
                                        error -> Mono.empty()))
                .filter(value -> value >= 0)
                .collectList()
                .block();
        System.out.println("skip invalid = " + parsed);

        // 5. Strict requirement: one invalid value is an error.
        Mono<Integer> strictlyValid = Mono.just(-2)
                .filter(value -> value >= 0)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException(
                                "quantity must be >= 0")));
        try {
            strictlyValid.block();
        } catch (IllegalArgumentException error) {
            System.out.println("reject invalid = " + error.getMessage());
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FilterWhenDemo
```

**Stdout of the program itself** (excluding Maven tool logs; `Mono.delay` slows execution time without altering the order of collected results):

```text
filter = [Binh, Linh]
filterWhen = [2, 4]
empty decision = [1]
skip invalid = [12, 7]
reject invalid = quantity must be >= 0
```

**Explanation:**

- In example (1), `" An "` becomes `"An"` but has length 2 so it is dropped; the whitespace-only string becomes `""` so it is dropped; `"Binh"` and `"Linh"` are kept.
- In example (2), `Mono.delay` simulates a delayed decision and creates a Boolean publisher. Each even number is kept, and odd numbers are dropped. `filterWhen` does not return the Booleans; it returns **the source elements themselves** that pass the condition.
- In example (3), `1` yields `true` so it is kept, `2` and `4` yield `false` so they are dropped, and `3` yields `Mono.empty()` so it is also dropped.
- In example (4), parsing each string happens inside an **inner Mono**. The `"oops"` error is handled right inside the inner publisher with `Mono.empty()`, so `concatMap` continues with `"-2"` and `"7"`. `filter(value -> value >= 0)` then drops `-2`. `concatMap` is used to preserve data order in the example.
- In example (5), the failed filter condition produces `Mono.empty()`. `switchIfEmpty` turns that case into `Mono.error`, because business rules require a valid quantity. `block()` in the CLI rethrows `IllegalArgumentException` and the `catch` branch prints the message.

For automated testing needs, use `reactor-test`'s `StepVerifier` to assert value sequences, completion, and errors instead of relying on `System.out`. That is especially helpful when delays or subscription/cancellation are involved.

## 5. “Invalid Value” Must Be Clearly Defined

The phrase “invalid” can refer to very different situations. Choose handling based on the **business contract**, not on which operator is shortest to write.

| Situation | Common representation | Example |
| --- | --- | --- |
| Element does not belong in the returned result set | `filter` / `filterWhen` | A list showing only published products or documents the user is allowed to view. |
| A mandatory parameter violates format/rules | `Mono.error` or `switchIfEmpty(Mono.error(...))` | Creating an order with a negative quantity should return an input error, not silently create an empty order. |
| A resource is not found | `Mono.empty()` from repository then `switchIfEmpty` to 404 at the HTTP boundary | Lookup by ID yields no result. |
| An asynchronous check from a service fails | `onError`, possibly `timeout` + policy-compliant handling | Authorization service outage: system error or deny per approved policy. |
| Batch-ingested data has corrupt records and the contract allows skipping | Handle errors **per element**, keeping audit/logs/metrics | Skip malformed CSV lines, continue to subsequent lines, and record rejection reasons. |
| Input has multiple invalid fields that must be reported together | `ValidationResult`, `Either`, or DTO holding a list of errors | A form has both an invalid email and phone number; both must be reported for the user to fix. |

### 5.1. `filter` Cannot Explain Why an Element Was Dropped

When `filter(x -> isValid(x))` returns `false`, the element disappears from the output. Downstream receives no accompanying `ValidationError` for that element. For filtering a product catalog, this may be fine behavior. For form input, error reporting, or security auditing, silently dropping values can make the API confusing or lose data.

If you need to **keep the rejection reason**, use an explicit result type:

```java
record ValidationResult<T>(
        T value, boolean valid, String reason) {}

Flux<ValidationResult<String>> results = Flux.just("A", "AB")
        .map(text -> text.length() >= 2
                ? new ValidationResult<>(text, true, "")
                : new ValidationResult<>(text, false, "too short"));
```

This **illustrative** snippet uses Java 17 records; it preserves both valid results and reasons. When generating a report, you can branch valid outputs and error outputs. Avoid calling `filter` first and then expecting to recover information that was already discarded.

### 5.2. Empty Is Not Error; Error Is Not False

Remember the three distinct signals:

```text
Mono.just(value).filter(predicateFalse)  → onComplete (no onNext)
Mono.empty()                             → onComplete (no onNext)
Mono.error(exception)                    → onError(exception)
```

If `filterWhen` receives a `Mono.empty()` inner publisher, it drops the element being tested. If the inner publisher emits `onError`, the pipeline errors. A failing filter condition does not trigger `onErrorResume`, because it completed successfully while **emitting no value**. To handle the empty case, use `switchIfEmpty` or `defaultIfEmpty` depending on the contract.

For example: `Mono.just("abc").filter(String::isBlank).defaultIfEmpty("none")` emits `"none"`; `onErrorResume` does not run because there was no error.

## 6. Handling Errors at the Right Scope: Whole Sequence or Per Element?

This is an especially common mistake when cleaning data.

### 6.1. External Error Handling Can Terminate the Source Early

```java
Flux<Integer> numbers = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class, ex -> Flux.empty());
```

This is an **illustrative snippet**. When `"bad"` causes `map` to throw `NumberFormatException`, the upstream source enters the error signal; `onErrorResume` switches the rest of the pipeline to `Flux.empty()`. You **do not get `"3"` back** from the original source; the emitted output is `1` followed by completion. External `onErrorResume` cannot be treated as “skip just one element and keep running”.

### 6.2. Inner Publisher Scope Allows Skipping Individual Bad Values

```java
Flux<Integer> numbers = Flux.just("1", "bad", "3")
        .concatMap(raw ->
                Mono.fromCallable(() -> Integer.parseInt(raw))
                    .onErrorResume(NumberFormatException.class,
                            ex -> Mono.empty()));
// When a subscriber requests enough: 1, 3 then onComplete.
```

The error is handled at **each parse attempt**, before leaving `concatMap`. The outer source continues receiving subsequent elements. This works well when the ingest contract permits skipping corrupt records. For critical data, persist a traceable error record rather than silently dropping it.

### 6.3. `onErrorContinue` Is Not the Default Validation Solution

`onErrorContinue` has operator-specific semantics that can affect upstream and make code hard to predict. For per-record parsing/validation, isolate the work in an inner `Mono` and handle `onErrorResume` there, or use a result type carrying validation state. Avoid “turning on `onErrorContinue` across the whole chain” and assuming every error is safely skipped.

### 6.4. If a Failure Is a System Error, Do Not Hide It

Especially when `filterWhen` is used for authorization, an error calling the service does not necessarily mean the user lacks permission. There are three common options, each requiring an architectural decision:

- **Propagate the error** so the endpoint returns 5xx/503 if verification fails, avoiding serving unverified data.
- **Fail closed**: treat errors as denied, with logs/metrics, when policy requires it; note this can make the response look like a denial even though the root cause was infrastructure.
- **Conditional recovery** for a specific error type, such as a secondary service timeout that does not affect public data; never fail-open to grant access to sensitive data.

Fail-closed example for an optional check **when policy is explicitly defined**:

```java
Flux<Item> accepted = items.filterWhen(item ->
        remoteCheck(item)
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(java.util.concurrent.TimeoutException.class,
                        ex -> Mono.just(false)));
```

This is an **illustrative snippet**, requiring definitions of `Item`, `items`, and `remoteCheck`. Only timeouts are converted to `false`; other errors still travel via `onError`. `Mono.just(false)` is a *deny* decision, not equivalent to fixing the remote service error. Track timeouts via metrics/logs if investigation is needed.

## 7. `null` Values, Empty Strings, and Malformed Data Structures

**Reactor does not allow `null` values in `onNext` signals.** Expressions like `Mono.just(null)` are not a way to represent “a value that exists but is invalid”; they can throw `NullPointerException` right at assembly time. A `map` operator returning `null` leads to an error, not an empty element for `filter` to process next.

When a Java input value can be `null`, convert it to an empty publisher at the boundary:

```java
String supplied = null;
Mono<String> possible = Mono.justOrEmpty(supplied);
// possible is Mono.empty(), does not emit null.
```

This is an **illustrative snippet**. If a missing value is a request error, chain `switchIfEmpty(Mono.error(...))` immediately afterward for a clear error signal. For `String` inputs, `isBlank()` handles whitespace-only strings, yet cannot be called on `null`. Normalize or check for nullability **before** building the Reactor chain.

For complex objects, “validity” may depend on multiple fields and rules. `filter(user -> user != null)` is not the place to patch an upstream emitting nulls; fix it at the source, use validated objects, or use a dedicated result type. Do not use `filter` to quietly discard exceptions from bad JSON mapping/deserialization.

## 8. Applying in Spring WebFlux

### 8.1. List Filtering: Exclusion Semantics Are Normal

```java
@GetMapping("/products")
public Flux<ProductDto> products() {
    return productRepository.findAll()
            .filter(Product::isPublished)
            .map(productMapper::toDto);
}
```

This is an **illustrative snippet inside a controller**. `Product`, `ProductDto`, `productRepository`, and `productMapper` must be defined. In a public listing, excluding unpublished products is normal semantics. Because the controller returns `Flux`, WebFlux owns the subscription for the HTTP response. Do not add `.subscribe()` inside the handler to drive the chain.

### 8.2. Checking a Single Resource: Distinguish Not Found from Forbidden

Suppose the repository returns `Mono<Document>`, and the permission service returns `Mono<Boolean>`:

```java
@GetMapping("/documents/{id}")
public Mono<Document> readDocument(@PathVariable String id) {
    return documentRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Document not found")))
            .filterWhen(document ->
                    accessService.canRead(document.id()))
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.FORBIDDEN, "Access denied")));
}
```

This is an **illustrative snippet in a WebFlux controller**, requiring Spring imports and definitions for `Document`, `documentRepository`, and `accessService`. The ordering is deliberate:

1. Repository returns empty → the first `switchIfEmpty` turns it into HTTP 404.
2. Document exists, yet the permission service returns `false` or empty → `filterWhen` drops the document, and the second `switchIfEmpty` turns it into HTTP 403.
3. Document exists and permission is `true` → the controller returns the document.
4. Permission service emits `onError` → the error propagates to WebFlux; it does not automatically become 403. You can map that error type to 503 per policy.

In real applications, some systems intentionally return 404 instead of 403 to avoid leaking the existence of a document. That is a **security policy** that must be chosen explicitly, not an automatic behavior of `filterWhen`. Also guard against IDOR: every endpoint accessing sensitive data must check permissions properly, whether the API returns a single record or a list.

### 8.3. Invalid Input Should Become HTTP 400, Not Ambiguous Empty

```java
@PostMapping("/quantity")
public Mono<Integer> acceptQuantity(@RequestBody Mono<Integer> input) {
    return input
            .filter(quantity -> quantity > 0)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "quantity must be positive")));
}
```

This is an **illustrative snippet inside a controller**, requiring Spring imports; it checks a single number to clarify the idea. `filter` alone would produce `Mono.empty()` when the quantity fails; `switchIfEmpty` turns that into an input contract error. JSON decoding, body parsing, or binding errors may be handled by WebFlux on a separate path before reaching this predicate.

For multi-field DTOs, typically use Bean Validation (`@Valid`/`@Validated`), constraint annotations, custom validators, or a validation result carrying an error list. Do not chain a series of `filter` calls that lose per-field error details.

### 8.4. Asynchronous Checks Must Have Timeouts and Resource Management

If a predicate calls a database or remote HTTP service:

- Use reactive APIs such as `WebClient` or reactive repositories instead of placing blocking HTTP/JDBC calls inside `filter`.
- Choose a sensible timeout because `filterWhen` waits for check results; a non-completing Mono can hold items waiting indefinitely.
- Clearly define what empty/false/error mean for the business contract.
- Monitor latency, error rates, rejection rates, buffer sizes, and cancellation; do not call `subscribe()` manually to “let filterWhen run”.
- When element counts are large and each predicate incurs I/O, evaluate batch queries, database-side filtering, or bounded concurrency; calling a separate service per record easily causes an N+1 problem.

One performance point is often more important than operator choice: if the repository supports filtering in the query, push **safe and permission-compliant** conditions down to the query source to avoid loading excessive data only to filter it in memory. For authorization checks, still ensure conditions are enforced thoroughly in the proper place.

## 9. Backpressure, Cancellation, and Discard

Both `filter` and `filterWhen` can **discard** elements that fail the condition. For simple objects like `String`/`Integer`, this is usually unnoticeable. If values carry resources that may need releasing (buffers, pooled objects), consult Reactor's **discard support** guide and where `doOnDiscard` or library resource-release mechanisms are needed. Do not assume Java GC is sufficient for all native resources.

`filterWhen` can also retain elements in a queue while awaiting decisions. When upstream errors, downstream cancels, or checks take long, understand how the system handles unfinished values. Buffer/prefetch tuning balances throughput and memory; it does not mean “automatically capping maximum parallel outbound HTTP requests”.

Because rejected items are not emitted downstream, downstream receives fewer elements than upstream emits. When tracking metrics, distinguish **items seen**, **accepted**, **rejected**, and **predicate error**. If rejection reasons must be reported, measure directly at the decision point or preserve result objects rather than using `filter` alone.

## 10. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `filter` to call a remote service and `block()` | Blocks processing threads, reduces scalability, can error on event loop | Use `filterWhen` with a reactive publisher; or design an isolated boundary for blocking work. |
| Using `filterWhen(x -> Mono.empty())` thinking it means “undecided” | Element is dropped | Return a `Mono<Boolean>` with an explicit decision, or turn empty into an error if a missing decision is abnormal. |
| Assuming `onError` from an async predicate equals `false` | Pipeline may fail unexpectedly | Define an error policy and apply recovery at the right scope. |
| Using `filter` on mandatory request data and returning empty unconditionally | Client struggles to tell input was invalid | Use `switchIfEmpty` to produce a 400 error or a validation model with messages. |
| Using `map(parse)` + outer `onErrorResume` to “skip one bad line” | Upstream stops at the first erroring element, dropping later elements | Handle parsing inside each inner publisher. |
| Calling `filter` before recording rejection reasons | Cannot summarize per-element reasons for dropped items | Use `ValidationResult` or emit audit/metrics at the decision point. |
| Passing `null` into `Flux.just`/`Mono.just` to filter later | Reactor forbids `null` in `onNext` | Use `Mono.justOrEmpty` and handle the missing-data contract. |
| Treating `filterWhen(..., bufferSize)` as a concurrency limit | Wrong optimization; may still be slow due to sequential checks | Understand buffering/requests; when concurrency is needed, design explicitly with bounds. |
| Calling `subscribe()` manually inside a WebFlux controller | Creates a branch detached from the response; errors and cancellation are hard to control | Return the composed publisher to WebFlux. |
| Automatically “failing open” when the permission service errors | Risk of data exposure | Enforce an explicit authorization policy, typically denying access when unverified. |

## 11. Practice Scenarios and Self-Check Questions

**Scenario A.** Does `Flux.just("1", "bad", "3").map(Integer::parseInt).onErrorResume(e -> Flux.empty())` emit `3`?  
**Answer:** No. The source errors on `"bad"`; the outer `onErrorResume` switches to another publisher without going back to resume the old source. To skip only the failing record, use an inner publisher per item like `concatMap` in the example.

**Scenario B.** Does `Mono.just(0).filter(n -> n > 0)` emit `onError`?  
**Answer:** No. It completes empty. Use `switchIfEmpty(Mono.error(...))` if 0 is an input error.

**Scenario C.** What does `Flux.just("a", "b").filterWhen(value -> Mono.empty())` emit?  
**Answer:** It emits no elements, then completes (assuming the source does not error). An empty test publisher means the element did not pass the filter.

**Scenario D.** A permission service returns `Mono.error(new RuntimeException("unavailable"))`. Does `filterWhen` keep or drop the element?  
**Answer:** By default, the error travels down the pipeline and can terminate the whole sequence with `onError`. Converting errors into false, 503, or retries is a handling decision that must be written explicitly.

**Scenario E.** Why is `filterWhen` not automatically faster than `filter`?  
**Answer:** `filterWhen` involves subscribing to check publishers and may wait on I/O; checks in `Flux.filterWhen` are created/subscribed in order. For conditions already available in memory, synchronous `filter` is simpler. Only use reactive checks when truly needed.

**Scenario F.** A document list shows only viewable documents, while a single-document endpoint must return a specific status on denial. Can both reuse the same `filterWhen`?  
**Answer:** Both can use the same permission check mechanism, yet **response semantics differ**. In a list, excluding denied items is normal; for a single document, `switchIfEmpty`/policy is needed to return 403 or 404, while also handling the non-existent document case.

## Remember

- `filter` takes `Predicate<T>` returning `boolean` immediately: right for filtering on in-memory conditions.
- `filterWhen` takes a function returning `Publisher<Boolean>`: right when the decision comes from a reactive sequence. **The first Boolean** is the decision; empty drops the element; error takes the error path.
- **Filtered out does not mean errored.** For mandatory input data, turn “condition not met” into an error or appropriate validation object rather than letting the value vanish.
- Handle errors **at per-element scope** when business rules allow continuing after a bad record; handle errors at whole-sequence scope when failures must halt processing.
- In WebFlux, compose and **return the publisher**; the framework manages subscribing at the HTTP boundary. Do not use `block()` or manual `subscribe()` to drive operators in controllers.

### References

1. [Project Reactor Core – Flux API: filter and filterWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) – predicate contract, empty/false outcomes, check ordering, and buffering.
2. [Project Reactor Core – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) – `Mono.filter`, `Mono.filterWhen`, and `switchIfEmpty`.
3. [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) – filtering, error handling, backpressure, and testing.
4. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – reactive controller contract and HTTP request/response handling.
5. [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html) – input validation at the WebFlux boundary.
