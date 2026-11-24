# Mono, Flux, and the Meaning of Zero, One, or Many Values in Spring WebFlux

## 1. Lesson Objectives

When starting with Spring WebFlux, the two most common types you encounter are `Mono<T>` and `Flux<T>`. They might look like “one object” and “a List”, but that understanding is **incorrect**. Both are **Publishers** per Reactive Streams, describing signal emission over time. They represent **the capability of receiving a sequence of values**, rather than simply an object already residing in memory.

- `Mono<T>`: emits **0 or 1** value of type `T`, then completes successfully, **or** emits an error signal. A Mono may also never terminate if the publisher never sends a terminal signal.
- `Flux<T>`: emits **0 to N** values of type `T` (N can be very large or unbounded), then completes successfully, **or** emits an error. A long-lived publisher may continue until cancelled.
- **Zero values** in a reactive stream is a meaningful state: `onComplete` without `onNext`, not a Java `null` emitted as a value.
- **One value** is a single `onNext(value)` signal; when the sequence completes successfully, `onComplete` follows.
- **Multiple values** are multiple `onNext(value)` signals before a terminal signal; you must pay attention to demand, cancellation, and backpressure.

This is a foundational topic in WebFlux because controllers, WebClient, reactive repositories, and streaming APIs must all choose a type reflecting the true **cardinality** of the result.

### After this lesson you will be able to

1. Read the Reactive Streams signal sequence `onSubscribe → onNext* → (onComplete | onError)` and distinguish **empty**, **single**, **multiple**, **error**, and **never**.
2. Choose `Mono<T>`, `Mono<Void>`, `Flux<T>`, and `Mono<List<T>>` appropriately for HTTP business logic.
3. Understand factory methods: `Mono.just`, `justOrEmpty`, `empty`, `error`, `fromCallable`, `defer`; `Flux.just`, `fromIterable`, `range`, `empty`, `error`.
4. Use `map`, `flatMap`, `filter`, `switchIfEmpty`, `defaultIfEmpty`, `collectList`, `next`, `single`, `singleOrEmpty`, `then`, and `onErrorResume` without losing sight of result cardinality.
5. Distinguish **assembly** from **subscription**, cold/hot publishers, backpressure, cancellation, threading, and the impact of `block()`.
6. Build a practical Spring Boot WebFlux API with endpoints returning Mono and Flux, returning 404 on an empty Mono, JSON arrays, and SSE.
7. Use `StepVerifier` and `WebTestClient` to verify values, completion, errors, 404, and HTTP streaming.

**Context:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Reactor Core 3.x, and Spring WebFlux. The `reactor.core.publisher.Mono`/`Flux` APIs are not Java `Optional`, `Stream`, `Future`, or `java.util.concurrent.Flow.Publisher`, even though those abstractions share related ideas.

## 2. Reactive Streams: Not Just Data, Also Signals

Project Reactor's `Mono` and `Flux` implement `org.reactivestreams.Publisher<T>`. A downstream `Subscriber<T>` subscribes to the Publisher, receives a `Subscription`, and can request data in counts via `request(n)`.

Basic signal protocol:

```text
Publisher<T>
     │
     │ subscriber.subscribe(...)
     ▼
onSubscribe(subscription)
     │
     ├── subscription.request(n)  ← downstream requests data
     │
     ├── onNext(item #1)
     ├── onNext(item #2)
     ├── ...
     │
     └── one of two:
           onComplete()   ← succeeded with no more data
           onError(err)   ← terminal error
```

A Reactive Streams–compliant sequence must not emit further `onNext` signals after a terminal signal; `onComplete` and `onError` are mutually exclusive. The subscriber may also call `cancel()` to cancel; cancellation should not be interpreted as a successful business completion.

### 2.1. How Many onNext Signals Does a Mono Have?

**Empty Mono:**

```text
onSubscribe
onComplete
          → 0 onNext
```

**Single-value Mono:**

```text
onSubscribe
onNext("OK")
onComplete
          → 1 onNext
```

**Errored Mono:**

```text
onSubscribe
onError(IllegalStateException)
          → 0 onNext, terminated with failure
```

`Mono<T>` has at most one successful `onNext`. A `Mono.never()` emits neither onNext, onComplete, nor onError until cancelled — therefore “0..1” refers to **the number of elements that may be emitted**, without guaranteeing termination time.

### 2.2. How Many onNext Signals Does a Flux Have?

```text
Flux.empty()        onSubscribe → onComplete

Flux.just("A")      onSubscribe → onNext(A) → onComplete

Flux.just("A","B")  onSubscribe → onNext(A) → onNext(B) → onComplete

Flux.error(ex)      onSubscribe → onError(ex)

Flux.interval(...)  onSubscribe → onNext(0) → onNext(1) → ...
                    (can run indefinitely without take/cancel)
```

`Flux` does not automatically mean multiple elements. `Flux.empty()` is completely valid, and `Flux.just(1)` is also a Flux. The key distinction is the **contract**: this type allows multiple elements; in practice, not every subscription receives multiple values.

### 2.3. States Are Not Synonymous

| State | Has onNext? | Terminal signal? | Meaning |
| --- | ---: | --- | --- |
| `Mono.empty()` | 0 | `onComplete` | Success, no item |
| `Mono.just(value)` | 1 | `onComplete` | Success, one item |
| `Mono.error(ex)` | 0 | `onError` | Failure |
| `Mono.never()` | 0 | None yet | Pending indefinitely unless cancelled |
| `Flux.empty()` | 0 | `onComplete` | Empty sequence |
| `Flux.just(a,b)` | 2 | `onComplete` | Two elements |
| `Flux.error(ex)` | 0 | `onError` | Errored sequence |
| `Flux.just(a).concatWith(Mono.error(ex))` | 1 | `onError` | Emitted an item, then encountered an error |

**Note:** `Flux` can emit some items and then error. A contract-compliant `Mono` does not emit an item and then error on the same subscription: after one item, Mono succeeds and completes. In HTTP streaming, a mid-stream error can happen after headers/body have started sending; you cannot always switch to HTTP 500 anymore.

## 3. Mono.empty() Is Not Mono.just(null)

This is essential to grasp immediately because Reactor **forbids null as an `onNext` element**.

```java
Mono<String> present = Mono.just("hello");
Mono<String> absent  = Mono.empty();
Mono<String> nullable = Mono.justOrEmpty((String) null);
```

- `present` emits one string and completes.
- `absent` completes without emitting any string.
- `nullable` is also an empty Mono.
- `Mono.just(null)` **throws `NullPointerException` immediately upon calling the factory**; it cannot create a valid Mono holding null.

If a synchronous source returns null and you want to convert it into an empty Mono, use `Mono.justOrEmpty(possiblyNull)` or `Mono.fromCallable(() -> possiblyNull)` matching the API semantics. Do not attach `map(x -> null)` to filter out an item: Reactor will throw an error because the mapper must return non-null.

### 3.1. What Does Mono<Void> Mean?

`Mono<Void>` typically represents **an operation with no return value**, where you only care about success or failure:

```java
Mono<Void> saveOrDelete = repository.deleteById(42L);
```

Contract:

```text
success: onSubscribe → onComplete
failure: onSubscribe → onError(exception)
```

It does **not** carry a `Void` object for the subscriber to use. Therefore:

```java
Mono<Void> done = Mono.empty();

done.map(v -> "mapped"); // lambda will NOT run
```

If you want to perform a next step after completion, use `then(...)` or `thenReturn(value)`:

```java
Mono<String> result =
        repository.deleteById(42L)
                  .thenReturn("deleted");
```

In HTTP APIs, `Mono<Void>` is a common representation for completion without a payload; the controller must specify the appropriate status (often `204 No Content` for a successful DELETE). Do not assume `Mono<Void>` automatically implies HTTP 204; the status is determined by the Spring handler/ResponseEntity and configuration.

### 3.2. Mono.empty and Optional.empty

An `Optional.empty()` is an **immediately present Java value** indicating no object exists. `Mono.empty()` is a **Publisher**, which can be subscribed to and emit completion (potentially asynchronously). Converting Optional to Mono:

```java
Optional<String> maybeName = repository.findNameById(42L);
Mono<String> name = Mono.justOrEmpty(maybeName);
```

This illustrates a synchronous repository; if the repository executes a blocking query, **calling `findNameById` has already executed before** creating the Mono. Wrapping it in a Mono afterward does not make the DB call non-blocking. To defer the query, see `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` in the threading section.

## 4. Standalone Java 17 Program: Basic Cases

Use Maven Reactor Core if running inside a Spring Boot project with `spring-boot-starter-webflux`. The program can be placed in `src/main/java/example/ReactorCardinalityDemo.java`. It needs no HTTP server.

```java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactorCardinalityDemo {

    public static void main(String[] args) {
        System.out.println("Mono present:");
        Mono.just("A")
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));

        System.out.println("Mono empty:");
        Mono.<String>empty()
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));

        System.out.println("Flux several:");
        Flux.just(10, 20, 30)
                .subscribe(
                    value -> System.out.println("next=" + value),
                    err -> System.out.println("error=" + err),
                    () -> System.out.println("complete"));
    }
}
```

Because all three publishers are **synchronous cold factories**, with no `delayElement`, `publishOn`, or asynchronous source, stdout prints in order:

```text
Mono present:
next=A
complete
Mono empty:
complete
Flux several:
next=10
next=20
next=30
complete
```

**Be careful:** if replaced with `Flux.interval`, WebClient, or an async producer, `subscribe()` usually returns control quickly and output may arrive later; do not run a program that prints immediately and conclude the Publisher “emitted nothing”.

### 4.1. What Happens Without a Subscriber?

`Mono.just("x").map(...)` builds a pipeline/description; operators usually **do not process data** until a subscription occurs. `Mono.just(...)` itself accepts an already-computed object at assembly time, so **the value passed to `just` must be evaluated beforehand**; you must not claim that every side effect in every source always waits for subscription.

Example:

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> lazy =
    Mono.fromCallable(calls::incrementAndGet);

System.out.println(calls.get()); // 0
System.out.println(lazy.block()); // 1
System.out.println(lazy.block()); // 2
```

Here `Mono.fromCallable` defers invoking the function until subscription, while `block()` actively subscribes and waits for the result. **Only use `block()` in main/tests/appropriate imperative boundaries, never inside the WebFlux request event loop to invoke a reactive chain.**

## 5. Creating Mono and Flux: Choosing the Right Factory

### 5.1. Ways to Create a Mono

| Factory | Meaning | Example |
| --- | --- | --- |
| `Mono.just(value)` | Already holds a non-null value | `Mono.just("ok")` |
| `Mono.justOrEmpty(valueOrOptional)` | One value or none | `Mono.justOrEmpty(optional)` |
| `Mono.empty()` | Completes immediately, 0 items | `Mono.<String>empty()` |
| `Mono.error(ex)` | Terminal error | `Mono.error(new IllegalStateException("x"))` |
| `Mono.defer(supplierOfMono)` | Creates a fresh Mono on subscribe | `Mono.defer(() -> Mono.just(clockValue()))` |
| `Mono.fromCallable(callable)` | Invokes Callable on subscribe, null → empty | `Mono.fromCallable(() -> blockingRead())` |
| `Mono.fromSupplier(supplier)` | Invokes Supplier on subscribe | `Mono.fromSupplier(() -> "hello")` |
| `Mono.never()` | Never emits/completes/errors on its own | `Mono.<String>never()` |
| `Mono.delay(duration)` | Emits one `Long` after delay | `Mono.delay(Duration.ofSeconds(1))` |

**Do not use `Mono.just(expensiveCall())` to defer `expensiveCall()`**, because the argument expression is evaluated before the factory is invoked. Use `Mono.fromCallable(...)` or `Mono.defer(...)` when lazy semantics are needed.

### 5.2. Ways to Create a Flux

| Factory | Meaning | Example |
| --- | --- | --- |
| `Flux.just(a,b,c)` | A fixed sequence of existing values | `Flux.just(1,2,3)` |
| `Flux.fromIterable(iterable)` | Iterates a collection on subscribe | `Flux.fromIterable(List.of(1,2))` |
| `Flux.range(start,count)` | Finite sequence of integers | `Flux.range(5,3)` emits 5,6,7 |
| `Flux.empty()` | Completes with no items | `Flux.<String>empty()` |
| `Flux.error(ex)` | Terminal error | `Flux.error(new IllegalStateException())` |
| `Flux.defer(factory)` | Creates publisher upon subscription | `Flux.defer(() -> fetchCurrentItems())` |
| `Flux.interval(duration)` | Emits incrementing numbers on a scheduler tick | `Flux.interval(Duration.ofSeconds(1))` |
| `Flux.from(publisher)` | Adapts a Publisher | `Flux.from(otherPublisher)` |
| `Flux.generate(...)` | Stateful synchronous sink emitting 1 item per round | Needs clear state/termination |
| `Flux.create(...)` | Callback producer bridge | Needs demand/backpressure/cancellation handling |

**Do not default to `Flux.create` or `Sinks` for every collection.** For an existing list, `Flux.fromIterable` is far simpler and safer.

### 5.3. Flux.range: Count, Not endInclusive

`Flux.range(5, 3)` emits 5, 6, 7. The second parameter is the **element count**, not the ending value. With `Flux.range(1, 0)`, the Publisher completes without emitting any elements.

### 5.4. Creating Sources on Subscribe to Reflect Fresh Data

`Mono.just(service.readNow())` runs `readNow()` at assembly time. If that is a blocking DB query, you have already blocked at the Mono creation point.

`Mono.defer(() -> Mono.justOrEmpty(repository.findById(id)))` defers the call until subscription time, yet **is still blocking** if the repository is synchronous JDBC/JPA. To avoid blocking on the event loop, you must use a non-blocking driver (such as R2DBC) or temporarily offload via an appropriate scheduler. “Lazy” and “non-blocking” are not the same concept.

## 6. Key Operators by Value Cardinality

### 6.1. map: 1 → 1 per Item

```java
Flux<Integer> doubled = Flux.just(1, 2, 3)
        .map(n -> n * 2);
// onNext 2, 4, 6; onComplete
```

With Mono:

```java
Mono<String> upper =
        Mono.just("spring").map(String::toUpperCase);
// SPRING
```

If the source is `Mono.empty()`, the `map` lambda **does not execute**. `map` transforms items; it does not run when there is only `onComplete`.

### 6.2. filter: Items Can Disappear

```java
Mono<Integer> removed = Mono.just(3)
        .filter(n -> n % 2 == 0);
// Result: Mono.empty() because 3 fails the predicate.
```

`Flux.just(1,2,3).filter(n -> n > 2)` leaves only 3. An empty result after `filter` **is not an error**.

### 6.3. flatMap: Each Item Opens a Publisher

```java
Mono<String> name =
        Mono.just(42L)
            .flatMap(id -> reactiveRepository.findNameById(id));
```

When a service returns `Mono<String>`, use `flatMap` to avoid `Mono<Mono<String>>`. With Flux, `flatMap` can **interleave results and alter completion order** of inner publishers; use `concatMap` if you need to preserve order and serialize inner subscriptions.

Example:

```java
Flux<String> processed = Flux.just("A", "B")
        .flatMap(code -> webClient.get()
                .uri("/lookup/{code}", code)
                .retrieve()
                .bodyToMono(String.class));
```

This is an **illustrative snippet requiring a configured WebClient**, not a standalone class. Do not rely on A-then-B output order with `flatMap` when two HTTP calls have different latencies.

### 6.4. switchIfEmpty and defaultIfEmpty

```java
Mono<String> fallbackValue =
        Mono.<String>empty()
            .defaultIfEmpty("unknown");

Mono<String> fallbackPublisher =
        Mono.<String>empty()
            .switchIfEmpty(Mono.just("from-backup"));
```

Both can emit a fallback item and complete. Difference:

- `defaultIfEmpty(value)` takes **a non-null value**, suited for constants or pre-existing objects.
- `switchIfEmpty(otherMono)` switches to **another publisher** if upstream completes empty; the fallback publisher can be lazy, query another DB, or return empty or error.
- `onErrorResume` handles **errors**, not empty.
- `switchIfEmpty` handles **empty**, and does not catch upstream exceptions.

If the fallback reads an expensive resource, use `Mono.defer`:

```java
Mono<Item> source = repository.findById(id);

Mono<Item> selected = source.switchIfEmpty(
        Mono.defer(() -> backupRepository.findById(id)));
```

*Repositories are illustrative dependencies; code must be placed inside a method with a real Item type. Only calls backup when source is empty and the fallback is subscribed.*

### 6.5. collectList: Flux<T> → Mono<List<T>>

```java
Mono<List<Integer>> numbers =
        Flux.just(1, 2, 3).collectList();
```

When the subscription completes successfully, the Mono emits **one list** containing 3 elements, then completes.

Notably:

```java
Mono<List<Integer>> emptyList =
        Flux.<Integer>empty().collectList();
```

The result **is not Mono.empty()**. It emits **one empty List value** (`[]`) and then completes.

This is a very important cardinality distinction:

```text
Flux.empty():
  onComplete                  (0 items)

Flux.empty().collectList():
  onNext([]) → onComplete      (1 item: an empty List)
```

When using `collectList` on an infinite or non-completing Flux, it must accumulate until completion: **risking holding all data in heap forever**. Do not use `collectList()` on unbounded streams without `take`, `timeout`, or an explicit finite window.

### 6.6. next, single, singleOrEmpty

These convert a multi-value Flux to a Mono and carry distinct semantics.

| Operator | Empty Flux | 1-item Flux | 2+ item Flux |
| --- | --- | --- | --- |
| `next()` | Mono.empty | First item then complete | Only first item, cancels/ignores the rest |
| `single()` | Error (not exactly 1 item) | Mono with item | Error (more than 1 item) |
| `singleOrEmpty()` | Mono.empty | Mono with item | Error (more than 1 item) |
| `collectList()` | Mono emits `[]` | Mono emits `[x]` | Mono emits `[x,y,...]` |
| `count()` | Mono emits 0L | Mono emits 1L | Mono emits element count |

**Common bug:** using `next()` to verify there is only **one** DB result. `next()` only takes the first item and does not check if a second item exists. If business logic strictly requires uniqueness, use `single()` or a repository query backed by a unique constraint and appropriate reactive method.

### 6.7. then and thenReturn: Caring Only About Completion

```java
Mono<Void> saveCompleted =
        repository.save(entity).then();
```

`then()` ignores the previous value and produces a `Mono<Void>` representing completion/error.

```java
Mono<String> greetingAfterSave =
        repository.save(entity)
                  .thenReturn("saved");
```

When the source completes successfully, `thenReturn` emits the fixed value; when the source errors, the error propagates. Nothing is “saved” merely by constructing the Publisher — subscription is still required (in WebFlux, the framework subscribes to the handler's return value).

### 6.8. zip: Needs a Value from Every Source

```java
Mono<Tuple2<String, Integer>> combined =
        Mono.zip(Mono.just("A"), Mono.just(10));
```

The result is **one tuple**, followed by completion.

However:

```java
Mono<Tuple2<String, Integer>> noTuple =
        Mono.zip(Mono.just("A"), Mono.<Integer>empty());
```

The result completes **empty**: if one side emits no item, there are not enough values to pair. With complex zipped chains, short-circuiting can happen and not all sources may be subscribed; do not use zip as “a mechanism guaranteed to run side effects of all sources”. Choose `defaultIfEmpty` or redesign the pipeline if empty is an acceptable state.

## 7. Empty Does Not Mean HTTP 404 in WebFlux

A `@RestController` method:

```java
@GetMapping("/api/items/{id}")
Mono<Item> get(@PathVariable long id) {
    return repository.findById(id);
}
```

If `repository.findById(id)` returns `Mono.empty()`, the framework has no item to serialize. **404 is not guaranteed automatically** just because the Publisher is empty. If the HTTP API contract requires “not found → 404”, return `Mono<ResponseEntity<Item>>` and handle it explicitly:

```java
@GetMapping("/api/items/{id}")
Mono<ResponseEntity<Item>> get(@PathVariable long id) {
    return repository.findById(id)
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

*Illustrative snippet with injected repository/Item; complete code in section 12.*

Distinguishing the outcomes:

| Reactive value | Meaning at data layer | HTTP contract to decide |
| --- | --- | --- |
| `Mono.empty()` | No item | Could be empty body, 404, 204... depending on endpoint |
| `Mono.just(item)` | One item | Typically 200 + JSON item |
| `Flux.empty()` | Empty collection | Typically 200 + `[]` for JSON array |
| `Mono.just(List.of())` | **One empty list** | Typically 200 + `[]` |
| `Mono.error(ex)` | Retrieval failed | Error handling decides 4xx/5xx |
| `Mono<Void>` complete | Operation with no payload | Can be 204 when API defines no-content |

**Do not use empty to hide database errors.** “Record not found” can be empty; “cannot connect to DB” is an error and must be handled properly. Turning every error into empty makes clients think data does not exist while an infrastructure outage is happening.

### 7.1. Mono<ResponseEntity<T>> vs. ResponseEntity<Mono<T>>

WebFlux supports these types:

```java
Mono<ResponseEntity<Item>>
ResponseEntity<Mono<Item>>
ResponseEntity<Flux<Item>>
```

Key difference:

- `Mono<ResponseEntity<Item>>`: **status, headers, and body** can be decided **after** a Mono resolves. Suitable when returning `404` if empty.
- `ResponseEntity<Mono<Item>>`: status/headers are chosen immediately while the body arrives asynchronously; inconvenient if status must change based on whether the body has an item.
- `ResponseEntity<Flux<Item>>`: status/headers are chosen upfront, and multiple body items arrive over time. Once the response is committed and an error occurs, status cannot arbitrarily be changed.

Choose the type based on **when the status is known**, not simply whether a developer prefers wrapping Mono outside or inside.

## 8. Mono and Flux in Annotated WebFlux Controllers

Common examples:

### 8.1. Mono<Item> for Detail

```java
@GetMapping("/api/items/{id}")
Mono<ResponseEntity<Item>> item(@PathVariable long id) {
    return service.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

### 8.2. Flux<Item> for Lists

```java
@GetMapping("/api/items")
Flux<Item> items() {
    return service.all();
}
```

With `application/json`, a multi-value finite Flux is typically serialized as a JSON array; the client may receive it after encoding/buffering depending on the writer/streaming media type. Do not claim “Flux streams every item immediately” across all content types.

### 8.3. Flux<ServerSentEvent<Item>> for Streaming

```java
@GetMapping(
        value = "/api/items/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Item>> events() {
    return service.all()
            .map(item -> ServerSentEvent.<Item>builder()
                    .event("item")
                    .data(item)
                    .build());
}
```

With SSE (`text/event-stream`), each item can be sent/flushed as an event; avoid `collectList` if you want to preserve streaming semantics and backpressure. Client disconnects can emit cancellation; use `doFinally` to clean up resources rather than waiting indefinitely for `onComplete`.

### 8.4. Mono<Void> for Payloadless Operations

```java
@DeleteMapping("/api/items/{id}")
Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

*Illustrative snippet; requires `service.delete(id)` to have a clear contract (204 or 404 if ID doesn't exist?)*. If the delete method returns `Mono<Void>`, `thenReturn` emits the ResponseEntity upon completion. However, if you want 404 for a nonexistent ID, you must use an explicit business decision; `Mono<Void>` does not carry that information itself.

### 8.5. Request Body Publisher

With WebFlux:

```java
@PostMapping("/api/items")
Mono<ResponseEntity<Item>> create(
        @RequestBody Mono<CreateItem> requestBody) {

    return requestBody
            .flatMap(service::create)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/items/" + saved.id()))
                    .body(saved));
}
```

This is an illustrative snippet requiring classes/service/URI imports. If the request body is empty, `flatMap` does not run and the outer Mono is also empty unless `switchIfEmpty` is added to enforce 400. For complex input validation, use validation support and return errors with a stable schema; do not expect `flatMap` to handle null/empty automatically.

## 9. Assembly, Subscription, Cold, and Hot

### 9.1. Distinguishing Assembly Time from Execution Time

```java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> lazy = Mono.fromCallable(counter::incrementAndGet);

System.out.println(counter.get()); // 0
lazy.subscribe();
System.out.println(counter.get()); // 1
lazy.subscribe();
System.out.println(counter.get()); // 2
```

With synchronous `fromCallable`, two subscriptions result in two Callable invocations. In WebFlux, **do not manually call `subscribe()` inside a controller on a Publisher you intend to return**, if you want its result to become the HTTP response. Return the Publisher and let WebFlux subscribe; subscribing manually can cause extra parallel execution, double DB writes, and loss of error handling and cancellation.

### 9.2. Cold Publisher

Most factories like `Mono.just`, `Mono.defer`, and `Flux.fromIterable` represent sources that can replay for each subscriber; each subscription has its own lifecycle. `Mono.just(value)` already captured the value at assembly time, so it does not re-evaluate the expression that produced the value. Conversely, `Mono.defer` creates a new source upon subscription.

`Flux.range(1,3)` is cold:
 
```text
Subscriber A: 1 → 2 → 3 → complete
Subscriber B: 1 → 2 → 3 → complete
```

### 9.3. Hot Publisher

A hot source can emit while subscribers are present and does not necessarily replay history for latecomers. Examples include a message/event bus bridged into Reactor via `Sinks.Many<T>`. When using `Sinks.many().multicast()`, you must understand multi-subscriber behavior, buffering, and overflow; an external producer's backpressure might not naturally match consumer speed.

An illustrative snippet, not a complete service:

```java
Sinks.Many<String> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Flux<String> events = sink.asFlux();
// Publisher can share emissions across subscribers.
// EmitResult, buffer policy, and cancellation must be handled.
```

Use `tryEmitNext(value)` and check `Sinks.EmitResult` rather than assuming every emission will succeed. Hot streams risk missing events, overflowing buffers, or letting slow clients impact other subscribers. Designing replay/durability is separate from picking `Flux`.

### 9.4. cache, share, replay, and the Truth About DB Calls

Operators can change how subscriptions are shared:

- `Mono.cache()` caches the terminal result (value, empty, or error per API semantics) for subsequent subscriptions, with TTL overloads.
- `Flux.share()` creates sharing behavior suited for a hot subscription across multiple subscribers.
- `Flux.replay(n)`/`ConnectableFlux` supports replaying a count of elements (and variants).
- These options carry memory/TTL/error semantics that require careful control.

**Do not enable unbounded `cache()` for personalized responses or mutable data** without considering invalidation and privacy; a reactive cache does not replace authentication, transactions, or distributed cache design.

## 10. Backpressure: 0..N Flux Must Respect Consumption Speed

Reactive Streams provides a **demand** mechanism. The subscriber receives a `Subscription` and calls `request(n)` to ask for the next maximum number of items. If the producer respects demand, it does not flood the consumer without limit.

Example:

```java
Flux.range(1, 5)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
            request(1);
        }
    });
```

*Snippet requires `BaseSubscriber` and `org.reactivestreams.Subscription` imports. Its purpose is to demonstrate API demand; with this mechanism, eventual output is 1..5 then complete, unless cancelled.*

### 10.1. subscribe() Usually Requests Unbounded

Common overloads like `subscribe(value -> ...)` and `block()` usually request **unbounded** (`Long.MAX_VALUE`). Do not use “having called subscribe” as proof that a client consumes in a bounded manner.

In WebFlux, the reactive HTTP integration manages the subscription and flow control per WebFlux/Netty and each writer; the application must still control upstream DB/WebClient work and expensive consumers.

### 10.2. Backpressure Does Not Automatically Protect Every Producer

- Synchronous sources like `Flux.range` and `Flux.fromIterable` generally honor request demand.
- Callback-style push/hot event sources can emit faster, needing buffering/dropping/latest/error strategies or upstream flow control.
- `onBackpressureBuffer()` can exhaust heap if the producer outpaces the consumer for a long period.
- `limitRate(n)` adjusts downstream-to-upstream demand in batches, without making a database or remote broker zero-cost.
- `buffer(n)` turns multiple items into one `List<T>` per batch; it does not turn each batch into a complete stream.
- `take(n)` caps the item count and typically cancels upstream once enough items arrive.

### 10.3. Cancellation

In HTTP streaming, when a client disconnects, the subscription may be cancelled. Design cleanup:

```java
Flux<Item> stream = repository.streamItems()
    .doFinally(type -> {
        // lightweight cleanup/metrics on complete, error, or cancel;
        // do not block the event loop.
    });
```

*Illustrative example requiring a real repository. `doFinally` receives `SignalType`; avoid assuming every network disconnection is detected instantaneously across every proxy.*

Do not put resource-release logic only in `doOnComplete`: if the pipeline errors or cancels, that callback does not run. Use `usingWhen`/`doFinally` matching the lifecycle and nature of the resource.

## 11. Threading: Reactive Does Not Mean Multi-Threaded

`Mono.just(1).map(i -> i + 1)` typically runs synchronously on the subscribing thread. Using Mono/Flux **does not automatically run tasks in the background**. Thread switching only occurs if the source is already async, the framework/scheduler/driver chooses to switch, or you place `subscribeOn`/`publishOn`.

### 11.1. subscribeOn and publishOn

- `subscribeOn(scheduler)` affects where subscription/upstream execution occurs (relative position in the chain has specific semantics).
- `publishOn(scheduler)` switches the execution context for operators **after it**.
- Do not place `publishOn` indiscriminately to “fix blocking” if the event loop was already blocked earlier.

Example:

```java
Mono<String> value =
    Mono.fromCallable(() -> legacyJdbc.queryOne())
        .subscribeOn(Schedulers.boundedElastic());
```

This is a temporary bridge for **bounded** synchronous calls. `boundedElastic` is designed for blocking work much better than the event loop, yet it does not turn JDBC into non-blocking I/O and has limits/queues. You must set timeouts, configure connection pools, and avoid overload. If the whole data stack is reactive, prefer a non-blocking driver (e.g., R2DBC) and avoid unnecessary blocking wrappers.

### 11.2. Why Is .block() Dangerous in a WebFlux Handler?

Inside a request handled by a Reactor Netty event loop, `block()`/`blockFirst()`/`blockLast()` can stall the event loop or cause Reactor to throw `IllegalStateException` on non-blocking threads. Even a few blocking requests can degrade many concurrent connections.

**Wrong:**

```java
@GetMapping("/wrong")
String wrong() {
    return webClient.get().uri("/remote")
        .retrieve().bodyToMono(String.class).block();
}
```

**Better:**

```java
@GetMapping("/right")
Mono<String> right() {
    return webClient.get().uri("/remote")
        .retrieve().bodyToMono(String.class);
}
```

These are two illustrative snippets requiring an injected `WebClient` instance. Real production code also needs deadlines, status handling, circuit breakers/backoff, and connection pooling. In unit tests or command-line boundaries, `block()` can be acceptable when intentionally crossing back to the synchronous world.

### 11.3. Reactor Context Instead of Blindly Using ThreadLocal

A reactive chain can switch threads; `ThreadLocal`/MDC is not automatically guaranteed to keep the same value across every operator. Reactor provides a per-subscriber **Context**:

```java
Mono<String> trace =
    Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("traceId", "absent")))
        .contextWrite(Context.of("traceId", "req-123"));
```

In a real app, to keep MDC logs, tracing, and security context across threads, use appropriate Spring/Reactor context propagation integration. Do not pass unverified principals/secrets via arbitrary request headers and trust them as identity.

## 12. Runnable Spring Boot WebFlux + Java 17 Application

Create a Maven project using **Spring Boot 3.3.13**, JDK 17+, and the `spring-boot-starter-webflux` dependency. **Do not** add `spring-boot-starter-web` if you want Boot to default to a reactive web application; when both MVC and WebFlux starters are present, Boot typically prioritizes MVC auto-configuration unless configured otherwise.

The application demonstrates static data and a minimal in-memory reactive repository:

- `GET /api/items` returns `Flux<Item>` → JSON array with 2 items.
- `GET /api/items/1` returns `Mono<ResponseEntity<Item>>` → 200 + item.
- `GET /api/items/999` → empty source mapped to 404.
- `GET /api/items?contains=boot` → `Flux.filter`, potentially 0..N.
- `GET /api/items/first` → `Flux.next()`, converted to Mono.
- `GET /api/items/summary` → `collectList()`, creating one Summary object.
- `GET /api/items/events` → finite SSE Flux with two events.
- `GET /api/items/none` → `Mono<Void>`/204, illustrating completion without a body.

### 12.1. Structure

```text
mono-flux-cardinality/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ReactiveCardinalityApplication.java
    │   ├── Item.java
    │   ├── CatalogService.java
    │   └── ItemController.java
    └── test/java/example/
        ├── ReactorCardinalityTest.java
        └── ItemControllerTest.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mono-flux-cardinality</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-webflux` provides Spring WebFlux, Reactor Core, and the default Reactor Netty runtime; `reactor-test` provides `StepVerifier` for tests. You do not need to manually specify the Reactor version because Spring Boot dependency management selects compatible versions.

### 12.3. ReactiveCardinalityApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveCardinalityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveCardinalityApplication.class, args);
    }
}
```

### 12.4. Item.java

```java
package example;

public record Item(long id, String name) {}
```

Java record provides a constructor and accessors `id()`, `name()`; Jackson is configured by Boot to encode JSON objects.

### 12.5. CatalogService.java

```java
package example;

import java.util.List;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {
    private final List<Item> items = List.of(
        new Item(1L, "Spring WebFlux"),
        new Item(2L, "Spring Boot")
    );

    public Flux<Item> all() {
        // Cold source: each subscriber iterates the same snapshot.
        return Flux.defer(() -> Flux.fromIterable(items));
    }

    public Mono<Item> find(long id) {
        return Mono.defer(() ->
            Mono.justOrEmpty(
                items.stream()
                    .filter(item -> item.id() == id)
                    .findFirst()
            )
        );
    }
}
```

This is a fixed in-memory data store, **not a reactive DB driver**. Because the List is tiny, synchronous lookup suffices for demo purposes; in real systems, do not use this pattern to wrap a heavy blocking JPA query on the event loop. With R2DBC/reactive repositories, methods return Mono/Flux without holding threads while waiting for I/O like JDBC does.

Both methods use `defer` to create the Publisher/lookup at subscription time. `all()` emits two items then completes. `find(999)` completes empty without throwing an error.

### 12.6. ItemController.java

```java
package example;

import java.time.Duration;
import java.util.List;
import java.util.Locale;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ItemController {

    public record Summary(int count, List<String> names) {}

    private final CatalogService service;

    public ItemController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/api/items")
    public Flux<Item> list(
            @RequestParam(required = false) String contains) {

        Flux<Item> source = service.all();

        if (contains == null || contains.isBlank()) {
            return source;
        }

        String wanted = contains.trim().toLowerCase(Locale.ROOT);
        return source.filter(item ->
            item.name().toLowerCase(Locale.ROOT).contains(wanted));
    }

    @GetMapping("/api/items/first")
    public Mono<ResponseEntity<Item>> first() {
        return service.all()
            .next()
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping("/api/items/summary")
    public Mono<Summary> summary() {
        return service.all()
            .collectList()
            .map(items -> new Summary(
                items.size(),
                items.stream().map(Item::name).toList()
            ));
    }

    @GetMapping("/api/items/none")
    public Mono<ResponseEntity<Void>> none() {
        return Mono.<Void>empty()
            .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(
        value = "/api/items/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> events() {
        return service.all()
            .delayElements(Duration.ofMillis(20))
            .map(item -> ServerSentEvent.<Item>builder()
                .event("item")
                .data(item)
                .build());
    }

    @GetMapping("/api/items/{id}")
    public Mono<ResponseEntity<Item>> get(@PathVariable long id) {
        return service.find(id)
            .map(item -> ResponseEntity.ok(item))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

**Why were these return types chosen?**

- `list`: has 0..N items, returns `Flux<Item>` instead of `Mono<Item>`; with `application/json` on a finite result, the browser typically receives a JSON array.
- `first`: `Flux.next()` takes the first item; if the source has no items, the controller explicitly returns 404 rather than a default 200 empty body.
- `summary`: `collectList` creates a List and maps it to **one Summary**; if items are empty, summary can still be `{count:0,names:[]}` rather than 404.
- `none`: `Mono<Void>` completes successfully, and `thenReturn` supplies ResponseEntity 204 so the HTTP status is explicitly defined.
- `events`: `Flux<ServerSentEvent<Item>>` with the SSE media type represents multiple events sent over time; the demo emits only two events then completes to avoid an infinite stream in tests.
- `get`: `Mono.empty()` from the repository is transformed into `ResponseEntity.notFound()`. This is an API contract choice, not Mono's default behavior.
- Annotated routes `/api/items/first` and `/api/items/{id}` coexist: Spring path matching selects the more specific literal route; method declaration order in the class is not the deciding factor.

### 12.7. Run Commands and Sample Responses

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

GET the list:

```bash
curl -i http://localhost:8080/api/items
```

HTTP 200, JSON body:

```json
[
  {"id":1,"name":"Spring WebFlux"},
  {"id":2,"name":"Spring Boot"}
]
```

Actual whitespace is typically compact, but the JSON structure matches above.

GET one item:

```bash
curl -i http://localhost:8080/api/items/1
```

HTTP 200, body:

```json
{"id":1,"name":"Spring WebFlux"}
```

Nonexistent item:

```bash
curl -i http://localhost:8080/api/items/999
```

HTTP **404 Not Found**, because the controller maps `Mono.empty()` to `ResponseEntity.notFound()`. The exact error response body may be determined by Boot's default error handler; do not assert error JSON text not present in the controller.

Successful filter:

```bash
curl -i "http://localhost:8080/api/items?contains=boot"
```

HTTP 200:

```json
[{"id":2,"name":"Spring Boot"}]
```

Filter with no matches:

```bash
curl -i "http://localhost:8080/api/items?contains=unknown"
```

HTTP 200 with an empty JSON array:

```json
[]
```

Summary:

```bash
curl -i http://localhost:8080/api/items/summary
```

HTTP 200:

```json
{"count":2,"names":["Spring WebFlux","Spring Boot"]}
```

No body:

```bash
curl -i http://localhost:8080/api/items/none
```

HTTP **204 No Content**, with no JSON body.

SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/items/events
```

Illustrative body (exact encoding, whitespace, and headers may vary):

```text
event:item
data:{"id":1,"name":"Spring WebFlux"}

event:item
data:{"id":2,"name":"Spring Boot"}

```

`curl -N` disables curl-side output buffering so each event is easy to see. For long-running response streams, clients must handle reconnects, IDs, cancellation, timeouts, and backpressure; do not assume the presence of Flux guarantees durable delivery.

## 13. Reactor Unit Tests: StepVerifier Checks Signals, Not Just Data

`reactor-test` provides `StepVerifier` to verify what a Publisher emits:

- `expectNext(...)`: expects one or more onNext values.
- `expectNextCount(n)`: expects n elements regardless of value.
- `verifyComplete()`: asserts successful completion.
- `expectError(...)`/`expectErrorMatches(...)`: asserts a terminal error.
- `thenCancel()`: cancels a long-running stream.
- `withVirtualTime(...)`: tests delayed publishers without waiting long in real time, provided the publisher is created inside the Supplier after the virtual scheduler is set up.

### 13.1. ReactorCardinalityTest.java

```java
package example;

import java.util.List;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReactorCardinalityTest {

    @Test
    void monoJustEmitsOneItemThenCompletes() {
        StepVerifier.create(Mono.just("A"))
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void monoEmptyCompletesWithoutNext() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }

    @Test
    void monoJustNullIsNotAllowed() {
        assertThrows(NullPointerException.class,
            () -> Mono.just((String) null));
    }

    @Test
    void monoJustOrEmptyNullIsEmpty() {
        StepVerifier.create(Mono.justOrEmpty((String) null))
            .verifyComplete();
    }

    @Test
    void monoErrorIsNotSuccessfulCompletion() {
        StepVerifier.create(
                Mono.<String>error(
                    new IllegalStateException("boom")))
            .expectErrorMatches(ex ->
                ex instanceof IllegalStateException &&
                "boom".equals(ex.getMessage()))
            .verify();
    }

    @Test
    void fluxCanEmitMoreThanOneItem() {
        StepVerifier.create(Flux.just(1, 2, 3))
            .expectNext(1, 2, 3)
            .verifyComplete();
    }

    @Test
    void fluxCanBeEmpty() {
        StepVerifier.create(Flux.<Integer>empty())
            .verifyComplete();
    }

    @Test
    void collectListTurnsEmptyFluxIntoOneEmptyList() {
        StepVerifier.create(
                Flux.<Integer>empty().collectList())
            .expectNext(List.of())
            .verifyComplete();
    }

    @Test
    void nextTakesOnlyFirst() {
        StepVerifier.create(Flux.just(9, 8, 7).next())
            .expectNext(9)
            .verifyComplete();
    }

    @Test
    void singleRequiresExactlyOneValue() {
        StepVerifier.create(Flux.just(9).single())
            .expectNext(9)
            .verifyComplete();

        StepVerifier.create(Flux.<Integer>empty().single())
            .expectError(NoSuchElementException.class)
            .verify();

        StepVerifier.create(Flux.just(1, 2).single())
            .expectError(IndexOutOfBoundsException.class)
            .verify();
    }

    @Test
    void singleOrEmptyAllowsZeroButNotTwoValues() {
        StepVerifier.create(Flux.<Integer>empty().singleOrEmpty())
            .verifyComplete();

        StepVerifier.create(Flux.just(1, 2).singleOrEmpty())
            .expectError(IndexOutOfBoundsException.class)
            .verify();
    }

    @Test
    void fallbackForEmptyIsNotFallbackForError() {
        StepVerifier.create(
                Mono.<String>empty().defaultIfEmpty("fallback"))
            .expectNext("fallback")
            .verifyComplete();

        StepVerifier.create(
                Mono.<String>error(new IllegalStateException())
                    .defaultIfEmpty("fallback"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void collectListCountsAllFiniteItems() {
        StepVerifier.create(
                Flux.range(5, 3).collectList())
            .expectNext(List.of(5, 6, 7))
            .verifyComplete();
    }

    @Test
    void thenReturnWaitsForCompletion() {
        StepVerifier.create(
                Mono.just("ignored").thenReturn("done"))
            .expectNext("done")
            .verifyComplete();
    }

    @Test
    void monoZipWithEmptyCannotEmitTuple() {
        StepVerifier.create(Mono.zip(
                Mono.just("A"), Mono.<Integer>empty()))
            .verifyComplete();
    }
}
```

These tests are scoped to **signals/cardinality** and require no HTTP server. `single()` with too many items reports `IndexOutOfBoundsException` in Reactor 3.6; with an empty source, `single()` reports `NoSuchElementException`. Do not test merely by calling `block()` and comparing values, because `block()` on an empty Mono can return null and easily lead readers to confuse empty with null.

### 13.2. Virtual Time Test for Time-Based Streams

Additional example:

```java
@Test
void timedFluxCanBeTestedWithoutRealDelay() {
    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofHours(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
}
```

Add this method to the class above and add `import java.time.Duration;`. **The Publisher must be created inside the `withVirtualTime` Supplier**; if created beforehand, the timer may already be bound to the real scheduler and the test cannot control it. Virtual-time tests are useful for `delayElement`, `interval`, `timeout`, and retries; avoid `Thread.sleep` which makes tests slow/flaky.

## 14. WebTestClient: Testing Mono/Flux over HTTP

The test below boots the reactive Spring Boot context via `@SpringBootTest(webEnvironment = RANDOM_PORT)` and uses `WebTestClient`; it does not force Servlet MockMvc. `@AutoConfigureWebTestClient` configures the Spring WebFlux test client.

### 14.1. ItemControllerTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void listFluxBecomesJsonArray() {
        client.get().uri("/api/items")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$[0].name").isEqualTo("Spring WebFlux")
                .jsonPath("$[1].name").isEqualTo("Spring Boot");
    }

    @Test
    void existingItemMonoReturns200() {
        client.get().uri("/api/items/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.name").isEqualTo("Spring WebFlux");
    }

    @Test
    void emptyMonoIsExplicitlyMappedTo404() {
        client.get().uri("/api/items/999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void filterFluxCanReturnZeroItems() {
        client.get()
            .uri("/api/items?contains=missing")
            .exchange()
            .expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void firstConvertsFluxToMono() {
        client.get().uri("/api/items/first")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void summaryCollectsFiniteFluxIntoSingleObject() {
        client.get().uri("/api/items/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.count").isEqualTo(2)
                .jsonPath("$.names[0]")
                    .isEqualTo("Spring WebFlux");
    }

    @Test
    void completionWithoutBodyReturns204() {
        client.get().uri("/api/items/none")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void sseEndpointProducesEventStream() {
        client.get().uri("/api/items/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
    }
}
```

**Why does the test use RANDOM_PORT?** It tests the real WebFlux HTTP server stack (Reactor Netty by default), Spring Boot routing, and encoding more faithfully than unit-testing the controller alone. For strict streaming/cancellation testing, consume the body via `returnResult(...)` and use `StepVerifier`, rather than only asserting headers. This test does not replace load testing for network backpressure or reliability on client disconnect.

### 14.2. Testing Errors vs. Missing Items

If a service returns `Mono.error(new IllegalStateException("db unavailable"))`, that is an infrastructure failure; do not turn it into a 404. In Spring WebFlux you can configure `@RestControllerAdvice`, `ErrorWebExceptionHandler`, or `onErrorResume` per your contract. However, do not apply `onErrorResume(ex -> Mono.empty())` to every exception because it turns outages into “not found”, hiding alerts and debugging details.

## 15. Choosing Mono/Flux in WebClient, Repositories, and Business APIs

### 15.1. WebClient Returning One Object

```java
Mono<Item> item = webClient.get()
        .uri("/api/items/{id}", 42L)
        .retrieve()
        .bodyToMono(Item.class);
```

If the server responds with HTTP 404, `retrieve()` by default can throw `WebClientResponseException.NotFound`, and **does not automatically turn status 404 into Mono.empty()**. To distinguish 404 from other errors, write a status handler or use `exchangeToMono(...)`:

```java
Mono<Item> selected = webClient.get()
    .uri("/api/items/{id}", 42L)
    .exchangeToMono(response -> {
        if (response.statusCode().value() == 404) {
            return Mono.empty();
        }
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        return response.createError();
    });
```

*Illustrative snippet; requires WebClient/Item imports and handling for other business statuses if needed. Do not use the sample code to swallow all 5xx errors as empty.*

### 15.2. WebClient Returning Multiple Items

```java
Flux<Item> items = webClient.get()
        .uri("/api/items")
        .retrieve()
        .bodyToFlux(Item.class);
```

If the endpoint returns a JSON array, WebClient can decode it into multiple Item signals. However, a server emitting a finite JSON array and a server emitting an SSE/infinite stream have different lifecycles; the consumer must understand content types, buffering, and cancellation.

### 15.3. ReactiveCrudRepository

Common reactive repositories follow cardinalities such as:

| Operation | Common Type |
| --- | --- |
| `findById(id)` | `Mono<T>`: 0..1 |
| `findAll()` | `Flux<T>`: 0..N |
| `save(entity)` | `Mono<T>`: saved object or error |
| `deleteById(id)` | `Mono<Void>`: completion/error |
| `count()` | `Mono<Long>` |
| `existsById(id)` | `Mono<Boolean>` |

These are standard type contracts in Spring Data reactive repositories. An empty result from `findById` does not necessarily correspond to HTTP 404 in every use case; HTTP policy belongs to the service/controller.

### 15.4. Business Cardinality vs. Technical Cardinality

If an entity must be unique by email, `Mono<User>` is a good API signature, yet **does not enforce a DB unique constraint**. You still need database uniqueness/transactions. If a `findAll` endpoint returns `Flux<User>` while requiring a page size of 20, do not stream millions of users unboundedly; use pagination/limits and appropriate database queries.

## 16. Common Mistakes: 20 Pitfalls to Avoid

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| “Mono always has exactly 1 item” | Failing to handle empty | Mono emits 0 or 1 |
| “Flux always has multiple items” | Unaware of Flux.empty | Flux emits 0..N |
| “Mono.empty() is Mono.just(null)” | NPE or broken logic | Null is not a valid onNext |
| “Mono.error is Mono.empty” | Masks incidents | Terminal error differs from empty completion |
| “Mono<Void> contains a Void object” | map never runs | Only completion or error |
| “Mono<List<T>> is the same as Flux<T>” | Wrong cardinality and streaming | A List is a single item |
| “Flux.empty().collectList() is still an empty Mono” | Wrong response/test | It emits `[]` |
| “Flux.next verifies exactly one item” | Duplicate data ignored | next only takes the first item |
| “Flux.single ignores extra items” | Cardinality error | single requires exactly one item |
| “Flux.singleOrEmpty accepts any item count” | Error when >1 | It only allows 0 or 1 |
| “switchIfEmpty catches exceptions” | Errors go unhandled | Use onErrorResume when error fallback is truly intended |
| “onErrorResume is for not found” | Turns every DB error into 404 | Empty and error must remain separate |
| “zip with Mono.empty always runs side effects on the other side” | Side effects get short-circuited | Do not use zip to trigger mandatory tasks |
| “Mono.just(blockingCall()) is lazy” | Blocking runs at assembly | Use defer/fromCallable and an appropriate scheduler |
| “Mono.fromCallable makes JDBC non-blocking” | Event loop still blocks | Use a reactive driver or boundedElastic bridge |
| “Calling subscribe inside controller is faster” | Double execution, lost cancellation | Return the Publisher for WebFlux to subscribe |
| “block() in a WebFlux handler is harmless” | Event-loop starvation/error | Compose reactive operators |
| “Flux means streaming so browser sees items immediately” | Wrong expectations about media types | JSON array vs. SSE/NDJSON differ |
| “Hot Flux always replays data to newcomers” | Missed events | Choose explicit replay/buffer policy |
| “Backpressure exists automatically in every callback source” | Overflow/OOM | Design demand/backpressure explicitly |
| “collectList on infinite Flux yields a result” | Never completes, heap grows | Limit with take/window or stream |
| “Cancellation is onComplete” | Missing cleanup | Use doFinally/usingWhen with proper semantics |
| “Every operator creates a new thread” | Wrong performance model | Scheduler only changes when specified |
| “HTTP 404 happens automatically on empty Mono” | Broken API contract | Use explicit ResponseEntity.notFound |
| “WebClient retrieve on 404 returns Mono.empty” | 404 becomes an error | Use onStatus/exchangeToMono per policy |
| “An ETag/security token is reactive context” | Broken trust boundary | Use dedicated auth and context propagation |
| “Reactive means all libraries are non-blocking” | JDBC/file I/O still blocks | Audit the entire call chain |
| “map handles empty completion” | Side effect never runs | Use then/doOnSuccess/doFinally per semantics |
| “Flux flatMap always preserves order” | Unstable output order | Use concatMap/flatMapSequential if needed |
| “Producer cancel guarantees saved data rolls back” | Ambiguous side effects | Use explicit transactions/idempotency |

## 17. Mono vs. Flux Design Checklist

Before defining a method's return type, answer:

1. Does the operation return **zero**, **one**, or **many** objects?
2. Is “no object” a valid success, HTTP 404, or a business error?
3. Does “no body” mean a successful payloadless operation (`Mono<Void>`/204) or a missing entity?
4. If multiple objects, do you need a finite JSON array or SSE/NDJSON streaming?
5. Is the source finite or potentially infinite? Who cancels it and when?
6. Must item order be preserved? Could `flatMap` reorder items?
7. Do errors occur **before** or **after** the HTTP response is committed?
8. Are the repository/WebClient drivers truly non-blocking?
9. Is there upstream demand/backpressure when the producer is faster than the consumer?
10. Are you buffering everything with `collectList()`, and do memory limits apply?
11. Could accidental double subscription cause duplicate DB queries or writes?
12. Are retries applied to a non-idempotent operation?
13. Have you clearly separated `switchIfEmpty` from `onErrorResume`?
14. Are HTTP 404, 204, 400, and 500 explicitly mapped to the contract?
15. Do tests assert completion, error, empty, single value, and multiple values?
16. Do async tests use virtual time instead of `Thread.sleep` where appropriate?
17. Are cancellation, demand, latency, and retries logged/metered without leaking data?
18. Do context/security propagate properly across the reactive chain without relying blindly on ThreadLocal?
19. When mixing MVC and WebFlux starters, which stack is the application actually running?
20. Do you need pagination or rate limits instead of letting clients subscribe to an unbounded stream?

## 18. Self-Check Questions

**1.** Must `Mono<T>` always emit a value?  
**Answer:** No; it holds 0 or 1 item, terminates with success or error, and may never terminate if the source is never.

**2.** Can `Flux<T>` be empty?  
**Answer:** Yes; `Flux.empty()` completes without emitting any items.

**3.** Why is `Mono.just(null)` invalid?  
**Answer:** Reactive Streams forbids emitting null via `onNext`; the Reactor factory throws `NullPointerException`.

**4.** What does `Mono.justOrEmpty((String)null)` represent?  
**Answer:** An empty Mono, completing without `onNext`.

**5.** Does `Mono<Void>` emit `onNext(Void)`?  
**Answer:** No; it primarily represents completion/error with no payload.

**6.** How many items does `Flux.empty().collectList()` emit?  
**Answer:** One item: an empty List.

**7.** What does `Flux.just(1,2).next()` emit?  
**Answer:** Emits 1 and completes; does not check item 2.

**8.** What about `Flux.just(1,2).single()`?  
**Answer:** Errors because there is more than one item.

**9.** What about `Flux.empty().single()`?  
**Answer:** Errors because it requires exactly one item.

**10.** What about `Flux.empty().singleOrEmpty()`?  
**Answer:** Completes empty, valid.

**11.** Does `switchIfEmpty` handle error cases?  
**Answer:** No, separate error handling is required.

**12.** Does `Mono.error(ex).defaultIfEmpty(v)` emit `v`?  
**Answer:** No, the error propagates.

**13.** Does `Mono.zip` with one `Mono.empty` source emit a result?  
**Answer:** No, the tuple lacks all required components.

**14.** Why doesn't `Mono.just(expensive())` defer `expensive()`?  
**Answer:** Java evaluates arguments before calling `just`.

**15.** Is calling `subscribe()` directly inside a WebFlux controller generally recommended?  
**Answer:** No; return the Publisher so the framework manages subscription and lifecycle.

**16.** When a client disconnects from SSE, what can happen?  
**Answer:** The subscription is cancelled and needs cleanup; `onComplete` will not necessarily fire.

**17.** Does `flatMap` on a Flux preserve the order of async inner publishers?  
**Answer:** Not guaranteed; use `concatMap` or an order-preserving option.

**18.** Do `publishOn` and `subscribeOn` both affect execution context?  
**Answer:** Yes, but across different scopes: downstream vs. subscription/upstream.

**19.** Is using `.block()` inside the WebFlux request event loop dangerous?  
**Answer:** It can block or be rejected by Reactor, reducing concurrent connection capacity.

**20.** If an HTTP GET looks up a missing ID and the service returns `Mono.empty`, does it automatically return 404?  
**Answer:** Not guaranteed; use explicit `ResponseEntity.notFound` if the contract requires 404.

**21.** Does a Flux returning a JSON array always flush each item immediately?  
**Answer:** No; it depends on the writer/media type. SSE/NDJSON use clearer streaming semantics.

**22.** Does `WebClient.retrieve()` return `Mono.empty()` by default on 404?  
**Answer:** No; it typically produces the corresponding `WebClientResponseException`.

**23.** Is `Mono.zip` good for ensuring side effects of all sources run?  
**Answer:** No; an empty source can short-circuit subscriptions.

**24.** Is `Mono.cache()` suitable for storing every user's private data forever?  
**Answer:** No, not without evaluating keys, TTL, invalidation, and security.

**25.** What problem does backpressure solve?  
**Answer:** It lets downstream signal demand so upstream can match consumption speed when the source is able to honor demand.

## 19. Official References

- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/3.6.12/reference/index.html): Mono 0..1, Flux 0..N, backpressure, cold/hot, assembly/subscription, operators.
- [Reactor Core 3.6 — Mono Javadoc](https://projectreactor.io/docs/core/3.6.15/api/reactor/core/publisher/Mono.html): `justOrEmpty`, `defer`, `switchIfEmpty`, `defaultIfEmpty`, `thenReturn`, subscribe.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `fromIterable`, `next`, `single`, `singleOrEmpty`, `collectList`.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): testing onNext/onComplete/onError/virtual time.
- [Spring Framework 6.2 — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller.html): Mono/Flux return types in REST controllers.
- [Spring Framework 6.2 — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): HTTP encoding by media type, Flux streaming vs. response buffering.
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html): `Mono<ResponseEntity<T>>` vs. `ResponseEntity<Mono<T>>`/`ResponseEntity<Flux<T>>`.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): `bodyToMono`/`bodyToFlux`, error handling.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): WebFlux HTTP tests.
- [Reactive Streams specification](https://www.reactive-streams.org/): Publisher, Subscriber, Subscription, demand, terminal signals.

**Core takeaway:** `Mono<T>` is **0 or 1 item**; `Flux<T>` is **0 to many items**. Both also carry **completion/error/cancellation semantics** and are subject to subscription/backpressure. **Empty is not null, error is not empty, and `Flux.empty().collectList()` is not `Mono.empty()`.** Reading these distinctions accurately helps design WebFlux APIs with reliable HTTP statuses, memory footprints, streaming, and error handling.
