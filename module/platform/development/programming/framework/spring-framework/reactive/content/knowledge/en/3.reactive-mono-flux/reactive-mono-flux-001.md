# Mono<T>: Representing a Zero-to-One Element Result

**Topic:** Spring Framework Reactive — **Mono and Flux**.

In Project Reactor, `Mono<T>` is a `Publisher<T>` representing **at most one value** and the completion of a task. A `Mono` can emit exactly one value, complete without emitting any value, or terminate with an error. The key concept is **0..1 elements**, not "always returns an object".

`Mono` typically appears when an operation has only one valid outcome: finding a product by ID, making an HTTP call to retrieve a resource, validating a token, saving an object, or running a task where you only need to know that it completed.

## 1. Understanding "Zero to One Elements" Accurately

`Mono<T>` follows the Reactive Streams signal contract. `T` is the type of the **emitted element**; it does not describe execution duration, threads, or error state. A subscriber (`Subscriber`) can observe the following signals:

- `onSubscribe(Subscription)`: receives the subscription, allowing it to request data and cancel.
- `onNext(T)`: occurs **at most once**, carrying a **non-null** value.
- `onComplete()`: normal termination, either after one `onNext` or with no `onNext`.
- `onError(Throwable)`: termination due to an error, never accompanied by `onComplete`.

The three common outcomes are:

| Case | Data/Termination Signal Sequence | Meaning |
|---|---|---|
| **One element** | `onNext(value) → onComplete()` | Succeeded and produced one value |
| **No element** | `onComplete()` | Succeeded but has no value to emit |
| **Error** | `onError(error)` | Task failed; the error is the terminal signal |

Each sequence above is also preceded by `onSubscribe`. There is no fourth outcome "`onNext(null)`": according to Reactive Streams, `null` **is not allowed as emitted data**. A normal `Mono` also never emits two elements.

```text
One value:
subscribe → onNext("Java") → onComplete

Empty:
subscribe → onComplete

Error:
subscribe → onError(IllegalStateException)

Invalid:
subscribe → onNext("A") → onNext("B") → onComplete
subscribe → onNext(null) → onComplete
subscribe → onNext("A") → onError(...)
```

The last point is very easy to confuse: **a Mono that has already emitted a value cannot subsequently emit an error**; a failing `Mono` only terminates with `onError`. Some factories such as `Mono.never()` may emit no value and never terminate either; therefore, "0..1 elements" does not mean every subscription will finish immediately or always terminate in finite time. Real-world tasks should use timeouts when needed.

## 2. Mono<T> Is a Task Description, Not T

Comparing the types:

| Type | What Is Represented | Key Difference |
|---|---|---|
| `T` | A value already present in memory | Carries no reactive contract for completion/error |
| `Optional<T>` | A value that may not exist, **already determined** | Does not itself represent pending work or asynchronous error signals |
| `CompletableFuture<T>` | A result or error that will complete later | Usually represents already-started work; does not guarantee non-blocking I/O by itself |
| `Mono<T>` | A Publisher for **0 or 1** value, or completion/error | Has subscription, cancellation, composition, and the Reactive Streams demand model |
| `Flux<T>` | A Publisher for **0 to many** values | Can emit multiple `onNext` signals before termination |

Example of the same lookup operation:

```java
Product direct = findImmediately(id);       // may return null or throw an exception
Optional<Product> optional = cache.find(id);
Mono<Product> result = reactiveRepo.findById(id);
```

This is **illustrative code**; `Product` and the methods/objects are not declared. With `Mono<Product>`, you cannot obtain `Product` by regular assignment: you must **compose** the pipeline, or let WebFlux subscribe and convert the value into an HTTP response.

**Do not infer that having a Mono automatically means asynchronous or non-blocking execution.** For example, `Mono.just("OK")` may emit immediately on the subscribing thread; `Mono.fromCallable(() -> blockingIo())` still performs blocking I/O on the thread executing the source, unless an appropriate scheduler is arranged.

### Is Mono<List<T>> Multiple Elements?

No. A `Mono<List<Product>>` can emit **one List object** (even if the list has 100 elements inside), and then complete. Conversely, `Flux<Product>` can emit 100 `onNext(Product)` signals.

```java
Mono<List<Integer>> oneList = Mono.just(List.of(1, 2, 3));
Flux<Integer> threeItems = Flux.just(1, 2, 3);
```

This is an **illustrative snippet** in a project with Reactor and `java.util.List`. Choose `Mono<List<T>>` when you want a complete collection-typed result; choose `Flux<T>` when you need an item-by-item stream, streaming, and multi-element processing.

## 3. Creating Mono According to the Data's Meaning

| Factory | Result | When to Use |
|---|---|---|
| `Mono.just(value)` | Emits exactly one non-null `value` | The value is already available |
| `Mono.empty()` | Only `onComplete`, no `onNext` | No value found or task finished with no data |
| `Mono.error(error)` | Only `onError` | Signal an error under the reactive contract |
| `Mono.justOrEmpty(value)` | Has a value if `value != null`; otherwise empty | Convert a nullable result into a Mono |
| `Mono.justOrEmpty(optional)` | Emits the value if `Optional` is present | Convert an Optional into a Mono |
| `Mono.fromSupplier(supplier)` | Calls supplier on subscribe; emits value or empty if null is returned | Deferred computation/data reading |
| `Mono.fromCallable(callable)` | Calls callable on subscribe; thrown errors become `onError`; null becomes empty | Work that may throw checked exceptions |
| `Mono.defer(() -> source)` | Selects/creates a **new source Mono per subscription** | Reading updated state, creating context-dependent sources |
| `Mono.fromFuture(future)` | Bridges from a `CompletableFuture` | Integrating legacy asynchronous APIs |
| `Mono.delay(duration)` | Emits a `Long` value after a waiting period | Asynchronous timer without sleeping the request thread |

The snippets below **are snippets** and must be placed inside a class with the Reactor dependency:

```java
Mono<String> a = Mono.just("Spring");
Mono<String> b = Mono.empty();
Mono<String> c = Mono.error(new IllegalStateException("Unavailable"));

String maybeName = null;
Mono<String> d = Mono.justOrEmpty(maybeName); // empty, does not emit null

Optional<String> maybeEmail = Optional.of("a@example.org");
Mono<String> e = Mono.justOrEmpty(maybeEmail); // emits one email

Mono<String> f = Mono.fromSupplier(() -> "computed");
Mono<String> g = Mono.defer(() -> Mono.just("fresh source"));
```

**Do not use `Mono.just(null)`**: the factory requires a non-null object and throws a `NullPointerException` at creation time. `Mono.justOrEmpty(null)` is the way to convert a nullable value into empty. `Mono.fromCallable(() -> null)` also completes empty.

### When Is the Value Computed?

```java
String value = loadValue();
Mono<String> eager = Mono.just(value);

Mono<String> delayed = Mono.fromCallable(() -> loadValue());
```

- In the first line, `loadValue()` has already run **before `eager` is created**, regardless of whether anyone subscribes.
- In `delayed`, `loadValue()` runs **upon subscription**, and can run again for each new subscription.
- `Mono.defer(() -> createMono())` defers even **selecting/creating the source Mono** until subscription time. The factory can use the latest state.
- "Building a pipeline" usually differs from "triggering a pipeline", but **never claim that every Mono is cold/lazy**: `just` captures the value at assembly time; some hot sources, `Sinks`, or `CompletableFuture` instances may already be active before subscription.

If `loadValue()` performs blocking I/O, `fromCallable` **only defers it**; it does not turn I/O into non-blocking by itself. How to isolate blocking work is covered in section 8.

## 4. A Runnable Reactor Example on Java 17+

The following example runs standalone with Maven and Reactor Core; it does not require Spring Boot. The goal is to **observe the 0..1 signals accurately**, distinguishing one value, empty, error, and deferred work.

Create the structure:

```text
mono-cardinality-demo/
├── pom.xml
└── src/main/java/demo/MonoCardinalityDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mono-cardinality-demo</artifactId>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/MonoCardinalityDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class MonoCardinalityDemo {
    private static <T> void show(String label, Mono<T> mono) {
        mono.subscribe(
                value -> System.out.println(label + ":onNext=" + value),
                error -> System.out.println(label + ":onError=" + error.getMessage()),
                () -> System.out.println(label + ":onComplete")
        );
    }

    public static void main(String[] args) {
        show("one", Mono.just("Java"));
        show("empty", Mono.<String>empty());
        show("error", Mono.<String>error(
                new IllegalStateException("boom")));

        show("fallback", Mono.<String>empty().defaultIfEmpty("guest"));

        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> deferred = Mono.fromSupplier(calls::incrementAndGet);

        System.out.println("callsBefore=" + calls.get());
        show("deferred1", deferred);
        show("deferred2", deferred);
        System.out.println("callsAfter=" + calls.get());
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MonoCardinalityDemo
```

**Program output** (excluding messages from the Maven tool):

```text
one:onNext=Java
one:onComplete
empty:onComplete
error:onError=boom
fallback:onNext=guest
fallback:onComplete
callsBefore=0
deferred1:onNext=1
deferred1:onComplete
deferred2:onNext=2
deferred2:onComplete
callsAfter=2
```

Why is the print order deterministic here? All sources in the example emit **synchronously upon subscription**; there is no `delay`, scheduler, or network. `show` subscribes to one source at a time. The output illustrates:

1. `one` has one `onNext` and one `onComplete`.
2. `empty` has only `onComplete`; the `value` callback does not run.
3. `error` has only `onError`; there is no `onComplete` after an error.
4. `defaultIfEmpty("guest")` turns empty into **one value**, so `onNext` is emitted.
5. `Mono.fromSupplier` does not increment the counter at creation time. Two subscriptions cause the supplier to run twice, producing values 1 and 2 respectively.

**Note on `subscribe()`:** actively calling `subscribe()` in `main` is appropriate for a demonstration program. In a **Spring WebFlux controller**, you normally **return the Mono** so the framework manages subscription, response, errors, and cancellation. Do not call `subscribe()` separately to send an HTTP response.

## 5. Operations on a 0..1 Result

### 5.1. `map`: Transform the Element If It Exists

```java
Mono<String> title = Mono.just("java")
        .map(String::toUpperCase); // emits "JAVA"

Mono<String> missing = Mono.<String>empty()
        .map(String::toUpperCase); // remains empty
```

`map` only runs when there is an `onNext`. When the source is empty, there is nothing to map; the source still completes empty. When the source errors, the error is forwarded downstream. The mapping function **must not return null**; if the mapper itself returns null, Reactor treats it as an error. If you want to turn a value into a "no element" state, use an appropriate operator such as `filter` or `flatMap` returning `Mono.empty()`.

### 5.2. `filter`: Can Turn One into Zero

```java
Mono<Integer> positive = Mono.just(7)
        .filter(number -> number > 0); // emits 7

Mono<Integer> removed = Mono.just(-2)
        .filter(number -> number > 0); // empty
```

`filter` discards elements that fail the predicate. **Empty after `filter` is not an error**; it is a successful completion with no item.

### 5.3. `flatMap`: Chaining an Operation That Also Returns a Mono

```java
Mono<String> userId = Mono.just("u1");

Mono<String> displayName = userId
        .flatMap(id -> Mono.just("User " + id)); // "User u1"
```

Use `map` if the lambda returns a **regular value**, and `flatMap` if the lambda returns a **Mono**. If `userId` is empty, the lambda inside `flatMap` does not run; `displayName` is also empty.

Do not write:

```java
Mono<Mono<String>> nested = userId
        .map(id -> Mono.just("User " + id));
```

When you need `Mono<String>`, use `flatMap` to avoid `Mono<Mono<String>>`. These snippets are not standalone applications.

### 5.4. Empty Fallback: `defaultIfEmpty` and `switchIfEmpty`

```java
Mono<String> primary = Mono.<String>empty();

Mono<String> withValue = primary
        .defaultIfEmpty("anonymous");

Mono<String> withBackup = primary
        .switchIfEmpty(Mono.just("backup"));
```

- `defaultIfEmpty(value)`: if the source **completes empty**, substitute **a default value**.
- `switchIfEmpty(otherMono)`: if the source completes empty, **subscribe to a fallback publisher**. The fallback path can emit a value, complete empty, or error.
- Neither is **error handling**. `Mono.error(...)` does not trigger empty fallbacks.
- When the fallback option is expensive or has side effects when **creating the source**, use `Mono.defer` to defer its creation:

```java
Mono<String> found = primary.switchIfEmpty(
        Mono.defer(() -> fetchFallbackFromCache()));
```

`fetchFallbackFromCache()` here is a hypothetical function **returning `Mono<String>`**. Use `defer` so the fallback source is only created when actually needed; it does not change the blocking nature of the function if it is blocking.

### 5.5. Error Fallback Is Separate from Empty

```java
Mono<String> failed = Mono.<String>error(
        new IllegalStateException("unavailable"));

Mono<String> recovered = failed
        .onErrorResume(IllegalStateException.class,
                error -> Mono.just("temporary fallback"));
```

`onErrorResume` runs when a matching error occurs, turning the error into another publisher. It **does not run merely because the source is empty**. `onErrorReturn` can also supply a fixed fallback value on a matching error.

Do not use `onErrorComplete()` thoughtlessly: it can turn a real error into empty, causing downstream consumers to mistake "service is broken" for "not found". Choose handling based on business semantics.

### 5.6. Combining Multiple Monos Requires Attention to Empty

```java
Mono<String> first = Mono.just("A");
Mono<String> second = Mono.just("B");

Mono<String> combined = Mono.zip(first, second)
        .map(tuple -> tuple.getT1() + tuple.getT2()); // "AB"
```

`zip` requires **each source to provide one item** to form a tuple. If one source is empty, the combined result may complete empty without invoking the mapper; other sources may be cancelled depending on execution progress. `Mono<Void>` or a `then()` pipeline is an empty source with respect to data, so it is generally not used in `zip` to collect values.

If you want to **wait for tasks to finish** without needing data results, look at `Mono.when(...)`; if you want to **preserve a value after a side task finishes**, look at `thenReturn(...)` or an appropriate composition.

## 6. Empty, Null, Error, and Optional — Distinguishing by Business Meaning

Consider an operation that looks up a user by ID:

| Situation | Appropriate Representation | Meaning |
|---|---|---|
| User found | `Mono.just(user)` or a publisher emitting the user | Succeeded with data |
| No matching user | `Mono.empty()` | Succeeded with no data |
| Database connection lost | `Mono.error(cause)` | Infrastructure failure, not a missing user |
| Nullable value from a legacy API | `Mono.justOrEmpty(value)` | Convert `null` into empty |
| Legacy API returning Optional | `Mono.justOrEmpty(optional)` | Adapt Optional into the Mono contract |

**Do not equate `Mono.empty()` with `Mono.just(Optional.empty())`.** The first emits **0 items**; the second emits **1 item** of type `Optional<T>` containing an empty state inside. Depending on the design layer, `Mono<Optional<T>>` often adds an unnecessary extra layer of representing "absence".

**Never emit Java `null` via `onNext`.** At a synchronous boundary, `mono.block()` may return `null` if the Mono is empty; that is how the reactive contract is adapted to a synchronous waiting API, **not proof that the Mono emitted null**. If you need to work with `Optional` at this boundary, Reactor provides `blockOptional()`, though you must not use these blocking operations on event-loop request threads.

## 7. Mono in Spring WebFlux: One Resource or 404

WebFlux can use `Mono<ProductDto>` to return at most one product. However, **an empty Mono does not automatically mean HTTP 404** in every controller. For specific REST requirements, encode the HTTP status choice explicitly.

The controller example below is for an **existing Spring Boot WebFlux application** with `spring-boot-starter-webflux`. It is a valid Java 17 class with no database required: data lives in a `Map`; the Spring Boot application and server runtime configuration are part of the surrounding environment.

```java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final Map<String, ProductDto> products = Map.of(
            "p1", new ProductDto("p1", "Keyboard"),
            "p2", new ProductDto("p2", "Mouse")
    );

    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductDto>> getOne(@PathVariable String id) {
        return Mono.defer(() -> Mono.justOrEmpty(products.get(id)))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound()
                        .<ProductDto>build());
    }

    public record ProductDto(String id, String name) { }
}
```

HTTP observations when the WebFlux application is running:

```text
GET /products/p1
→ HTTP 200, JSON body: {"id":"p1","name":"Keyboard"}

GET /products/unknown
→ HTTP 404, no product body
```

Line-by-line explanation:

1. `Mono.defer` defers looking up the `Map` until subscription; in this small example, reading the `Map` is fast and not blocking I/O.
2. `Mono.justOrEmpty(products.get(id))` emits **one `ProductDto`** if present; otherwise, it emits **`onComplete` with no item**.
3. `map(ResponseEntity::ok)` only runs when a product is present, wrapping the item in a `ResponseEntity` with status 200.
4. `defaultIfEmpty(ResponseEntity.notFound().<ProductDto>build())` supplies **one 404 `ResponseEntity`** if the lookup is empty.
5. The controller returns `Mono<ResponseEntity<ProductDto>>`. WebFlux subscribes and handles the response; the application does not call `subscribe` or `block` itself.

Difference between the two signatures:

- `Mono<ProductDto>`: the product payload is provided as a publisher; customizing the HTTP status for empty/error cases requires additional handling.
- `Mono<ResponseEntity<ProductDto>>`: status, headers, and body can all be decided when the Mono emits an item; convenient when both 200 and 404 branches exist.

In a real application, replace the `Map` with a reactive repository (`Mono<Product> findById(...)`), but only call it "non-blocking end-to-end" when **the driver, HTTP client, and all operations inside the pipeline** are also non-blocking.

### Mono<Void> Example: Work Completes Without Returning an Item

```java
// repository is a reactive repository declared elsewhere.
public Mono<Void> delete(String id) {
    return repository.deleteById(id);
}
```

`Mono<Void>` typically represents **work to be completed with no data item**. It can still terminate successfully (`onComplete`) or fail (`onError`). `Void` **does not mean "emits null"**.

Example returning an HTTP status for a delete operation:

```java
@DeleteMapping("/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
    return repository.deleteById(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

This is a **snippet**, requiring a controller, `repository`, and appropriate imports for `DeleteMapping`, `ResponseEntity`, and `Mono`. `thenReturn` only emits 204 after the source completes successfully; if the source errors, the error is propagated. **Do not assume by default that "missing ID" causes an error**: `deleteById` behavior depends on the repository implementation/contract.

## 8. Mono Does Not Guarantee Automatic Asynchrony or Non-Blocking Execution

Two snippets that look similar can have different execution paths:

```java
Mono<String> immediate = Mono.just("OK");

Mono<String> blocking = Mono.fromCallable(
        () -> legacyClient.readFromDatabase());
```

`immediate` already has data; it can emit synchronously on the subscribing thread. `blocking` defers calling `legacyClient`, but **whichever worker executes the Callable still has to wait** if the underlying library uses blocking I/O.

When forced to integrate a blocking source in a WebFlux application, you can isolate it on a scheduler meant for blocking work:

```java
Mono<String> isolated = Mono
        .fromCallable(() -> legacyClient.readFromDatabase())
        .subscribeOn(Schedulers.boundedElastic());
```

This is a snippet requiring the `reactor.core.scheduler.Schedulers` import and a `legacyClient` object. `boundedElastic` **does not turn a blocking library into a non-blocking one**; it shifts where the blocking occurs and manages worker/queue limits. For an end-to-end reactive stack, prefer drivers/clients that truly support non-blocking I/O, such as R2DBC when appropriate.

### When Does a Mono Actually Run?

Some sources like `just` emit immediately upon subscription. Sources like `WebClient` require a subscription to trigger the HTTP exchange. Sources like `Mono.delay(Duration.ofMillis(100))` schedule emission after the specified duration without holding a request thread with `Thread.sleep`.

In particular, **never call `block()`/`blockOptional()`/`blockFirst()` inside a WebFlux request handler** to extract data and return a synchronous result. Those calls block the thread, and Reactor may reject blocking on threads marked as non-blocking. Keep `Mono` inside the pipeline and return it to the framework.

## 9. Lifecycle Management: Subscribe, Cancellation, and Errors

In application reactive code:

```java
Mono<String> result = webClient.get()
        .uri("/profile/{id}", id)
        .retrieve()
        .bodyToMono(String.class);

return result
        .filter(body -> !body.isBlank())
        .switchIfEmpty(Mono.just("{}"));
```

This is a snippet inside a service/controller with `webClient` and `id`. `WebClient` creates a publisher for the response body; `filter` can turn the result into empty, and `switchIfEmpty` falls back to a default string. In practice, returning fake JSON `"{}"` might not fit an API contract; the example is used to clarify the 0..1 pipeline.

Regarding the lifecycle:

1. **Assembly:** constructing the pipeline. Creating a publisher does not mean all side effects have executed or the HTTP request has been sent.
2. **Subscription:** the subscriber subscribes and signals demand; the source starts as appropriate. Each subscription may re-trigger the source if the source is cold.
3. **Signals:** may emit one `onNext` then `onComplete`; only `onComplete`; or `onError`.
4. **Cancellation:** the subscriber can cancel if it no longer needs the result. Cancellation does not guarantee an external operation already started can be rolled back; it depends on the API/source.
5. **Timeout:** a source that does not return a result can keep a subscription open for a long time; use timeouts and deliberate error/fallback handling when there is a business time limit.

Useful observation hooks:

- `doOnNext(value -> ...)` runs **only when an element is emitted**.
- `doOnSuccess(value -> ...)` runs when the Mono succeeds, **including empty**; the callback receives **null as an indicator of empty**. This is only a callback argument, **not `onNext(null)`**.
- `doOnError(error -> ...)` runs when an error occurs.
- `doOnSubscribe(subscription -> ...)` helps observe subscription.
- `doFinally(signalType -> ...)` helps observe termination/cancellation via `SignalType`.

Do not place mandatory business side effects inside observation hooks if you need retry/cancellation guarantees or transactional consistency; compose tasks as publishers to control the execution flow explicitly.

## 10. Common Mistakes Related to 0..1 Cardinality

1. **"A Mono always contains a result."** False: `Mono.empty()` succeeds without emitting an item.
2. **"Empty is an error."** False: `onComplete` without `onNext` is distinct from `onError`; business logic may decide whether to map empty to 404 or a specific error.
3. **"`Mono.just(null)` represents not found."** False: it throws `NullPointerException` at creation time. Use `justOrEmpty`.
4. **"`Mono.just(expensiveCall())` defers calling expensiveCall."** False: the argument must be evaluated before calling `just`. Use `fromCallable`/`fromSupplier`/`defer` as appropriate.
5. **"`map` still runs even when the source is empty."** False: without `onNext`, there is no data to map.
6. **"`switchIfEmpty` handles all errors."** False: it is only for **empty success**; errors use `onErrorResume`/other policies.
7. **"`Mono<Void>` emits a null value."** False: `Mono<Void>` represents completion/error and emits no `Void` object.
8. **"A Mono can emit two values by calling `subscribe()` twice."** Not within **a single subscription**. Two independent subscriptions can each receive at most one item.
9. **"`Mono<List<T>>` is a stream of many items."** False: it has one item of type `List<T>`.
10. **"`Mono.zip(a,b)` always runs the mapper even if a or b is empty."** False: `zip` requires an item from both.
11. **"Returning `Mono` always yields HTTP 200 or always yields 404 when empty."** False: HTTP status also depends on controller/operator/response handling; encode status codes according to the REST contract.
12. **"Mono creates its own thread and is non-blocking by default."** False: scheduling and blocking depend on the source/operator/client; `subscribeOn` only dispatches threads and does not change a blocking API.

## 11. Self-Check

| Expression | `onNext` Count in a Successful Subscription | Result |
|---|---:|---|
| `Mono.just("A")` | 1 | `"A"` then complete |
| `Mono.empty()` | 0 | Completes immediately |
| `Mono.error(new RuntimeException("x"))` | 0 | Terminates with error |
| `Mono.justOrEmpty((String) null)` | 0 | Completes, does not emit null |
| `Mono.just("A").filter(v -> false)` | 0 | Filter drops item, then completes |
| `Mono.<String>empty().defaultIfEmpty("B")` | 1 | `"B"` then complete |
| `Mono.<String>empty().switchIfEmpty(Mono.just("B"))` | 1 | `"B"` then complete |
| `Mono.just(List.of(1,2,3))` | 1 | One item, which is a three-element List |
| `Mono.just("A").then()` | 0 | Drops value, keeps only terminal signal |
| `Mono.<String>empty().map(String::toUpperCase)` | 0 | Mapper does not run |
| `Mono.never()` | 0 until cancelled/otherwise | No default terminal signal |

**Applied Questions:**

- Looking up a non-existent product: should you return `Mono.empty()` or `Mono.error(...)`? → Depends on the contract; "not found" is commonly empty at the repository layer, and the controller decides whether to convert it to HTTP 404.
- Database connection failure: should it be turned into `Mono.empty()`? → Normally **no**; doing so hides an infrastructure error as "no data".
- Want to check whether a Mono has an item while still returning a Boolean: `source.hasElement()` returns `Mono<Boolean>`, emitting `true` if there is an item or `false` if empty; source errors are still forwarded.
- Want to invoke a second operation **only if the first has data**: use `flatMap`. If you need to perform a follow-up task **after the source completes successfully, including empty**, use `then(otherMono)`/`thenReturn(value)` according to business logic.

**Key Takeaway:** `Mono<T>` represents **0 or 1 item of `T`** and a lifecycle of **success or error**. "No item" is a valid successful outcome, distinct from Java `null` and distinct from an exception. When designing with Spring WebFlux, this distinction determines how you compose pipelines, handle fallbacks, and map results to HTTP.

## References

- Project Reactor — [Mono: an Asynchronous 0–1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html).
- Project Reactor — [Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) (signal contract, factories, and operators).
- Project Reactor — [FAQ: Empty Mono and zip](https://projectreactor.io/docs/core/release/reference/faq.html).
- Spring Framework — [WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [ResponseEntity in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html).
