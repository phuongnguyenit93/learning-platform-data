# Operators Return a New Publisher and Require Proper Chaining in Mono/Flux

## 1. Core Idea

In Project Reactor, every time you call an operator such as `map`, `filter`, `flatMap`, `doOnNext`, `onErrorResume`, `timeout`, or `publishOn` on a `Mono`/`Flux`, you normally receive **a new Publisher describing the pipeline with that additional step**. Operators **do not mutate** the existing source object in place.

Therefore, for a processing step to take effect, you must **chain the operator onto the active pipeline**, **assign the result to a variable**, or **return that result**. Calling an operator and discarding its return value creates an intermediate Publisher that is never placed on the intended execution path.

```java
Flux<Integer> source = Flux.just(1, 2, 3);

// Creates a new Publisher, then discards the result: does not modify source.
source.map(n -> n * 10);

// Still receives 1, 2, 3:
source.subscribe(System.out::println);
```

The right way:

```java
Flux<Integer> source = Flux.just(1, 2, 3);
Flux<Integer> transformed = source.map(n -> n * 10);

// Receives 10, 20, 30 from transformed:
transformed.subscribe(System.out::println);
```

These are two **illustrative code snippets in a Java context with Reactor**, not two standalone compilable files. A complete runnable example is in section 5.

**Key takeaway:** `source.map(...)` creates a *new result*; `source` remains the original pipeline. This also holds when the method is named `doOn...` or `onError...`: if the returned Publisher is not used, the new step is not part of the subscribed pipeline.

## 2. How Is a New Publisher Formed?

Think of a Publisher as a **description of how data will be emitted**. Each operator attaches another stage to that description:

```text
source = Flux.range(1, 5)
    |
    | .filter(n -> n % 2 == 0)
    v
filtered (new Publisher)
    |
    | .map(n -> n * 10)
    v
mapped (new Publisher)
    |
    | .doOnNext(System.out::println)
    v
observed (new Publisher)
    |
    | subscribe() by consumer
    v
20, 40
```

You can write this as a single fluent chain:

```java
Flux<Integer> result = Flux.range(1, 5)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .doOnNext(n -> System.out.println("observed: " + n));
```

Or split across lines while still chaining properly:

```java
Flux<Integer> source = Flux.range(1, 5);
Flux<Integer> even = source.filter(n -> n % 2 == 0);
Flux<Integer> tens = even.map(n -> n * 10);
Flux<Integer> result = tens.doOnNext(System.out::println);
```

Both styles describe the exact same output data. If you need to update a variable with the same name, you can reassign it:

```java
Flux<Integer> result = Flux.range(1, 5);
result = result.filter(n -> n % 2 == 0);
result = result.map(n -> n * 10);
```

What matters is **keeping and using the final Publisher**, not what the variable is named or how many lines of code are used.

### Assembly and Subscription Are Two Different Moments

Most operations like `map`, `filter`, and `flatMap` configure behavior during **assembly** (building the chain); data-processing callbacks are normally invoked only when a subscription exists and signals pass through the operator. With a **cold** Publisher like `Flux.range`, each subscription usually re-executes the source's emission process.

```text
ASSEMBLY:     Flux.range -> filter -> map -> result
SUBSCRIPTION: Subscriber -> result -> map -> filter -> source
SIGNALS:      source -> filter -> map -> Subscriber
```

- Subscription/demand flows backward from downstream to upstream.
- Data and completion/error signals flow from upstream to downstream.
- Only operators **on the path from the subscribed Publisher back to the source** participate in this flow.
- `subscribe()` begins a consumption pass; in Spring WebFlux, the framework normally performs the subscription after the controller returns the Publisher.
- Not all Publishers are cold or lazy in every respect: hot sources, caching, initialization logic, and expressions passed to `just(...)` have their own semantics (see section 8).

"New Publisher" is a concept about **objects and pipelines**; it does not mean Reactor always copies data, spawns a new thread, or immediately computes the entire result.

## 3. The Most Important Bug: Calling an Operator Without Using Its Return Value

Wrong example:

```java
Flux<Integer> numbers = Flux.range(1, 4);

numbers.filter(n -> n % 2 == 0);  // Result discarded.
numbers.map(n -> n * 10);          // Result discarded.
numbers.doOnNext(n -> log.info("value={}", n)); // Result discarded.

// This is still the original Publisher, receiving 1, 2, 3, 4:
return numbers;
```

The snippet above illustrates a method body returning `Flux<Integer>` with an existing logger `log`. Because none of the three new Publishers are chained or saved, `return numbers` still returns the original stream. The `log.info` line inside the discarded operator **will not run in this subscription**.

Fix:

```java
return numbers
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .doOnNext(n -> log.info("value={}", n));
```

Given `numbers = Flux.range(1, 4)`, the output data is now `20, 40`; the logger records those elements as they pass through the pipeline.

**Another common bug at the service layer:**

```java
public Mono<UserDto> loadUser(String id) {
    Mono<User> user = repository.findById(id);

    user.map(this::toDto); // Publisher<Dto> discarded.
    // return user;     // Wrong type: Mono<User> is not Mono<UserDto>.
    // ...
}
```

The right way:

```java
public Mono<UserDto> loadUser(String id) {
    return repository.findById(id).map(this::toDto);
}
```

These are **snippets inside an existing service** with `repository`, `User`, `UserDto`, and `toDto`; they illustrate preserving types and Publisher chains, and do not run standalone. Across multiple processing steps, return the final Publisher itself.

## 4. Every Operator Must Be Chained Into a Valid Pipeline

| Operator | Returned Publisher (Typical) | Purpose | Common Mistake |
|---|---|---|---|
| `Flux.map(f)` / `Mono.map(f)` | `Flux<R>` / `Mono<R>` | Synchronously transform values | Discarding the result and subscribing to the old source. |
| `Flux.filter(p)` / `Mono.filter(p)` | `Flux<T>` / `Mono<T>` | Keep only data matching the predicate | Assuming the original source was filtered. |
| `Mono.flatMap(f)` | `Mono<R>` | Compose a step returning `Mono<R>` | Using `map`, producing `Mono<Mono<R>>`. |
| `Flux.flatMap(f)` | `Flux<R>` | Map each element to a Publisher, merging inner streams | Assuming output order always matches input order. |
| `Flux.concatMap(f)` | `Flux<R>` | Concatenate inner Publishers in input sequence order | Using `flatMap` when strict ordering is required. |
| `Mono.flatMapMany(f)` | `Flux<R>` | One Mono input leading to multiple values | Using Mono's `flatMap` when a Flux is needed. |
| `doOnNext`, `doOnError`, `doFinally` | Same-type Publisher (typical) | Attach observation/lifecycle hooks | Assuming just calling it makes the hook run. |
| `onErrorResume`, `onErrorMap` | Same-family Publisher | Turn errors into fallbacks or another error | Calling and discarding the result, leaving no error handling. |
| `defaultIfEmpty`, `switchIfEmpty` | New Publisher | Define fallback value/branch when empty | Assuming the original object was modified. |
| `timeout`, `retry`, `publishOn`, `subscribeOn` | New Publisher | Add timeout, retry, or execution scheduling policies | Calling standalone and subscribing to the old Publisher. |
| `then()`, `thenReturn(v)`, `then(other)` | `Mono<Void>` / `Mono<V>` / Publisher per overload | Wait for completion and move to the next step | Not realizing `onNext` elements before `then` are dropped. |

This list covers common cases, not a guarantee that "every overload always returns the exact same type"; always check the specific signature. For example, `Flux.next()` returns `Mono<T>`, `Mono.flux()` returns `Flux<T>`, and `Flux.collectList()` returns `Mono<List<T>>`. The universal rule is to **use the actual return value** so no processing step is lost.

### `map` and `flatMap` Differ in the Callback's Return Type

When the transformation function returns a **regular value**, use `map`:

```java
Mono<String> result = Mono.just("java")
        .map(String::toUpperCase);  // Mono<String>, value "JAVA"
```

When the transformation function returns a **Publisher**, use `flatMap` to avoid nesting `Mono`:

```java
Mono<String> nested = Mono.just("java")
        .map(value -> Mono.just(value.toUpperCase()))
        .map(inner -> "inner publisher=" + inner.getClass().getSimpleName());
```

The `nested` snippet above intentionally demonstrates that `map` treats the inner `Mono` as a **plain value**, rather than subscribing to it and extracting its inner result. For real business logic:

```java
Mono<String> result = Mono.just("java")
        .flatMap(value -> Mono.just(value.toUpperCase()));
```

`flatMap` receives the Publisher returned by the callback and coordinates subscribing to it. Never call `.subscribe()` inside `map` to "extract a value"; that creates a subscription detached from the parent stream, making result awaiting, error propagation, and cancellation hard to control.

### Operator Order Changes the Result

```java
Flux<Integer> first = Flux.range(1, 4)
        .filter(n -> n > 2)
        .map(n -> n * 10); // 30, 40

Flux<Integer> second = Flux.range(1, 4)
        .map(n -> n * 10)
        .filter(n -> n > 2); // 10, 20, 30, 40
```

Operators are chained **in the exact order written** and process data according to each step's semantics. Thus proper chaining is a necessary condition; you must also choose the right operator ordering for the desired business behavior.

## 5. Runnable Java 17+ Example: Wrong, Right, and Execution Timing

This example runs standalone with **JDK 17+ and Maven**, without Spring Boot. It uses synchronous `Flux.range` so stdout is exact and easy to compare.

Project structure:

```text
reactor-chain/
├── pom.xml
└── src/main/java/example/ChainDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-chain</artifactId>
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
                    <mainClass>example.ChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/ChainDemo.java`:

```java
package example;

import reactor.core.publisher.Flux;

public class ChainDemo {
    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 4);

        System.out.println("A - discard new publisher:");
        source.map(n -> n * 10);         // Wrong: discards result.
        source.filter(n -> n % 2 == 0);  // Wrong: discards result.
        source.subscribe(n -> System.out.println("raw=" + n));

        System.out.println("B - chain operators properly:");
        Flux<Integer> result = source
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .doOnNext(n -> System.out.println("peek=" + n));

        result.subscribe(n -> System.out.println("out=" + n));

        System.out.println("C - assembly and subscription:");
        Flux<Integer> lazy = source.map(n -> {
            System.out.println("map=" + n);
            return n + 100;
        });

        System.out.println("pipeline created");
        lazy.take(2).subscribe(n -> System.out.println("got=" + n));
    }
}
```

Run in the `reactor-chain` directory:

```bash
mvn -q compile exec:java
```

Stdout from **the program** (ignoring any extra messages printed by Maven/plugins):

```text
A - discard new publisher:
raw=1
raw=2
raw=3
raw=4
B - chain operators properly:
peek=20
out=20
peek=40
out=40
C - assembly and subscription:
pipeline created
map=1
got=101
map=2
got=102
```

**Exact explanation:**

1. **A:** `map` and `filter` both create new Publishers that are discarded, so `source.subscribe(...)` still receives `1, 2, 3, 4`.
2. **B:** `result` holds the chain `filter → map → doOnNext`; even elements are transformed into `20`, `40`. `peek` prints right before each element reaches the `subscribe` callback, so each `peek=` appears before its corresponding `out=`.
3. **C:** Calling `source.map(...)` only constructs the pipeline; it does not print `map=` at that time. After printing `pipeline created`, subscribing to `lazy.take(2)` triggers two invocations of the map callback, and then `take(2)` ends the consumption pass. Because this example uses a synchronous cold source, only the first two elements are processed.

If B were changed to `source.filter(...); source.map(...); result = source;`, the output would revert to `1, 2, 3, 4`. If there were no `subscribe` in C, neither `map=` nor `got=` would print; only `pipeline created` would appear.

## 6. Chaining Properly When Code Is Split Across Methods

### Approach 1: Return the Final Publisher

Example method body in a service where `repository.findById` returns `Mono<User>` and `saveAudit` returns `Mono<Void>`:

```java
Mono<UserDto> findUser(String id) {
    return repository.findById(id)
            .filter(User::isActive)
            .flatMap(user ->
                    saveAudit(user)
                            .thenReturn(toDto(user))
            );
}
```

The snippet above **requires real types/services from the application** and is not a standalone program. `thenReturn(toDto(user))` emits the DTO only when saving the audit completes successfully; if `saveAudit` signals an error, the error follows the same pipeline. `toDto(user)` is a Java expression evaluated when building the inner Publisher of the `flatMap` branch; if computing the DTO has noticeable side effects, consider putting it in an appropriate lazy callback, such as `.then(Mono.fromSupplier(() -> toDto(user)))`.

### Approach 2: Use an Intermediate Variable and Reassign Properly

```java
Flux<String> names = Flux.just("An", "Binh", "Chi");
names = names.filter(name -> name.length() >= 3);
names = names.map(String::toUpperCase);

return names;
```

`names` is a **Java reference** that can be pointed to the new Publisher. Reassigning the variable is not an operation that mutates the contents of the original `Flux`.

### Approach 3: Avoid Nested Subscribes Inside a Service

Wrong approach, assuming `auditService.write(user)` returns `Mono<Void>`:

```java
return userRepository.findById(id)
        .map(user -> {
            auditService.write(user).subscribe(); // Detached subscription.
            return user;
        });
```

Bug: the audit step runs under a separate subscription. The outer pipeline can complete before the audit finishes; audit errors do not automatically propagate to the outer subscriber; cancelling the outer pipeline does not guarantee cancelling this audit task.

Right approach when the result must **wait for the audit**:

```java
return userRepository.findById(id)
        .flatMap(user ->
                auditService.write(user)
                        .thenReturn(user)
        );
```

This way the audit task is part of the returned stream, and the framework/caller can observe the shared lifecycle.

## 7. At the Spring WebFlux Application Boundary

In a Spring WebFlux controller, **return the final Publisher** so the framework can subscribe and control the HTTP lifecycle:

```java
@RestController
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    Mono<ProductDto> find(@PathVariable String id) {
        return service.findById(id)
                .filter(Product::isEnabled)
                .map(ProductDto::from)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
```

This controller snippet illustrates the API and **must be placed in a Spring WebFlux project** with matching `ProductService`, `Product`, and `ProductDto` types, along with `@RestController`, `@GetMapping`, `@PathVariable`, `Mono`, `ResponseStatusException`, and `HttpStatus` imports. `filter` can make the Mono empty, and `switchIfEmpty` turns a missing result into a 404 error. All three operators are chained onto the returned Publisher, so they are applied when the framework subscribes.

Wrong approach:

```java
Mono<Product> product = service.findById(id);
product.filter(Product::isEnabled); // New Publisher discarded.
return product;                      // Returns the original, unfiltered.
```

Do not call `subscribe()` inside a controller just to "start" work and then return a different Publisher or `void`. At the HTTP boundary, WebFlux normally subscribes to the Publisher returned by the controller; subscribing manually can cause a second subscription, duplicate requests, or broken error handling and client-disconnect cancellation. For service integration, you normally just **return** the fully composed Publisher chain.

## 8. Three Important Nuances to Avoid Misinterpretation

### 8.1. A New Operator Does Not Mean the Entire Expression Is Lazy

`map` accepts a function and normally invokes it only when data arrives, yet **Java arguments are evaluated before calling a method**:

```java
Mono<String> eager = Mono.just(loadValue());
```

In the snippet above, `loadValue()` is called right when constructing the `Mono.just(...)` expression, before any subscription. To defer invoking the data source until each subscription:

```java
Mono<String> deferred = Mono.fromSupplier(() -> loadValue());
```

These two snippets are illustrations where `loadValue()` returns a non-null `String`. If `loadValue()` can return null, explicitly design how emptiness is represented, such as `Mono.fromCallable(...)` completing empty on a null return, or using `Optional`/explicit checks. Never claim that every Publisher-building operation executes nothing at all.

### 8.2. Hot Publishers, Caching, and Sharing Emit Differently

A cold pipeline like `Flux.range` typically re-executes for each subscriber. Hot sources may already be emitting before a subscriber appears. Operators such as `cache()`, `share()`, or `publish()` change how the source is consumed and how signals are shared. Even so, **the syntax remains the same**: each operator returns a Publisher, and you must keep that Publisher if you want the new sharing behavior.

```java
Flux<Integer> shared = source.share(); // Must subscribe to "shared".
```

Calling `source.share();` and then continuing to subscribe to `source` will not turn `source` into a shared stream.

### 8.3. Chaining Is Distinct from Guaranteeing Order, Threading, and Backpressure

In Reactive Streams, the subscribed Publisher must honor the data-request mechanism; only operators present in the chain have a chance to coordinate demand and cancellation. However, you cannot infer that merely chaining properly gives you a dedicated thread, preserves order, or avoids buffering.

- `map` transforms each element, typically preserving received order.
- `flatMap` merges multiple inner Publishers and can interleave results; `concatMap` is better suited when order must be preserved.
- `publishOn` or `subscribeOn` changes the scheduling context according to Reactor rules; calling the operator and discarding the returned Publisher will not apply that policy to the active subscription.
- `doOnNext` observes signals; it is not an operator for changing types or values. To transform values, use `map`.
- `doOnError` observes errors rather than handling them; `onErrorResume` sets up a fallback branch. Both must still be chained onto the Publisher that gets consumed.

## 9. Spotting and Fixing Bugs in Code Review

| Symptom | How to Check / Fix |
|---|---|
| A line ends at `.map(...)`, `.filter(...)`, or `.doOnNext(...)` and the result is not assigned/returned/passed as an argument | Trace where the returned Publisher goes. If discarded, chain it into the final pipeline. |
| After `.onErrorResume(...)`, errors still occur as if no fallback were added | Verify you are subscribing to/returning the Publisher that has `onErrorResume`, and that the fallback handles the right error type. |
| A debug `doOnNext` does not run even though the original Publisher has data | Check that `doOnNext` is on the subscribed Publisher, has demand, and wasn't filtered out by `filter`. |
| Calling `.subscribe()` inside a `.map(...)` or a WebFlux service | Check whether the task can be moved into `.flatMap(...)` or `.then(...)` and return the unified Publisher. |
| Unintended `Mono<Mono<T>>` or `Flux<Mono<T>>` appears | Callback returns a Publisher: consider `flatMap` or `concatMap` as appropriate. |
| `.then()` loses data | This is its intentional semantics to drop upstream values; use `thenReturn`, `flatMap`, or another operator if data must be kept. |
| Operators are right yet there is no output | Verify the Publisher is subscribed to at the proper boundary; without a subscriber, cold pipelines generally do not emit. |
| Unintended duplicate requests/API calls | Check for multiple subscriptions to a cold source, nested `subscribe()`, or manual subscriptions; consider restructuring the chain and adding caching/sharing where justified. |

### Short Mental Checklist When Reading a Pipeline

1. **Identify the source:** where does the `Mono`/`Flux` originate?
2. **Track the returned Publisher:** which variable/expression does each new operator attach to, and is any discarded?
3. **Check the types:** `map` for regular values; `flatMap`/`concatMap` for callbacks returning Publishers; do any operators convert `Flux` to `Mono`?
4. **Check the order:** are filtering, transformation, error replacement, and empty handling in the right positions?
5. **Identify the boundary:** who performs the subscription? WebFlux usually does so after the controller returns; CLI apps may call `subscribe()` or `block()` at the outer boundary.
6. **Check error/cancellation behavior:** are related asynchronous tasks part of the same pipeline?

## 10. Self-Check Exercises

Given the code snippet:

```java
Flux<Integer> p = Flux.just(2, 3, 4);
p.map(n -> n + 1);
p.filter(n -> n % 2 == 0);
p.subscribe(System.out::println);
```

**Question 1:** What data is printed? Why?

**Answer:** `2`, `3`, `4` (one per line), because the Publishers returned by `map` and `filter` were both discarded.

**Question 2:** Rewrite it to add 1 and then keep only even numbers.

```java
Flux<Integer> p = Flux.just(2, 3, 4)
        .map(n -> n + 1)
        .filter(n -> n % 2 == 0);
p.subscribe(System.out::println);
```

**Expected stdout:** Only `4`, because `2,3,4` becomes `3,4,5` first, and then filtering keeps `4`.

**Question 3:** If `filter` is replaced with `doOnNext(System.out::println)`, does it still create a new Publisher? Do you need to chain the result?

**Answer:** Yes. `doOnNext` also returns a new Publisher; if the new Publisher is discarded, the observation callback does not participate in the subscribed chain. `doOnNext` only observes values without transforming them.

**Learning Summary:** Every Mono/Flux operator creates a new Publisher link. Always **chain, assign, or return** that result and **subscribe at the appropriate boundary**. Knowing exactly which Publisher is actually consumed prevents most "called an operator but it had no effect" bugs in Reactor and Spring WebFlux applications.
