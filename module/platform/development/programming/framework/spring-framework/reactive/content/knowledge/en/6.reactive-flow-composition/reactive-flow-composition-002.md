# `zip` for Combining Corresponding Values from Multiple Sources in Project Reactor

## 1. Problem and Core Idea

In Spring WebFlux, a single response may need information from **multiple independent sources**: a user profile and order count, a product code and inventory stock, or data from multiple APIs. Project Reactor provides the **`zip`** operator to **wait for each source to provide one value**, then combine the corresponding values into **a single result**.

With `Flux`, “corresponding” means **position of appearance within each stream**, not emission timestamp, business key, or clock time.

```text
Flux A:     A1 ------- A2 -------- A3
Flux B:          B1 -------- B2
                        |
zip(A, B): (A1, B1) -- (A2, B2) -- complete
```

The diagram above only illustrates **positional** pairing (1st with 1st, 2nd with 2nd), not an actual execution timeline. When one source finishes and it is no longer possible to form a complete group, `zip` completes. In the example, `A3` does not appear in the output.

`zip` is appropriate when:

- Each output item requires **simultaneously one value from every source**.
- The sources emit data in a **meaningfully corresponding order**, or each source is a `Mono` (at most one value).
- You want to build a `Tuple` or a new DTO from the available values.
- You need to combine independent reactive `Mono` calls without calling `block()` to fetch each value manually.

Key distinction: `zip` is **not** a key-based join (`join`), **not** list concatenation (`concat`), and does **not emit immediately whenever any source produces an element** (`merge` and `combineLatest` have different semantics).

## 2. Usage Forms

Reactor provides `Flux.zip(...)`, `Mono.zip(...)`, and the instance operator `zipWith(...)`. You can read the following calls as **illustrative snippets** inside a Java class that imports `Flux`, `Mono`, and the relevant types:

### `Flux.zip`: pairing multiple elements by index

```java
Flux<String> names = Flux.just("An", "Binh", "Chi");
Flux<Integer> ages = Flux.just(21, 25, 30);

Flux<reactor.util.function.Tuple2<String, Integer>> rows =
        Flux.zip(names, ages);
```

When subscribed, the resulting pairs are:

```text
(An, 21)
(Binh, 25)
(Chi, 30)
```

`Tuple2<String,Integer>` has two methods `getT1()` and `getT2()` to read the first and second elements. With three sources, the result is `Tuple3<T1,T2,T3>`, which adds `getT3()`; Reactor supports larger Tuple types, though positional names become harder to read when business logic grows complex.

### Passing a combinator function instead of keeping a Tuple

```java
Flux<String> labels = Flux.zip(
        Flux.just("Pen", "Book"),
        Flux.just(10, 5),
        (name, stock) -> name + ": " + stock
);
```

The output is `Pen: 10` and `Book: 5`. The BiFunction `(name, stock) -> ...` runs only when the operator has received one element from **both sources**. Using a combinator directly produces `Flux<R>` instead of `Flux<Tuple2<...>>`.

### `Mono.zip`: combining single results

```java
Mono<String> name = Mono.just("An");
Mono<Integer> score = Mono.just(95);

Mono<String> summary =
        Mono.zip(name, score, (n, s) -> n + " scored " + s);
```

If both `Mono` instances emit a value, `summary` emits **one** string `An scored 95` and completes. If **one source completes empty**, there are not enough values to combine, so `Mono.zip` also completes empty (emitting no `onNext`). If a source signals an error before the result is completed, the regular zip operator emits an error.

### `zipWith`: combining from an existing Publisher

```java
Flux<String> labels = Flux.just("A", "B")
        .zipWith(Flux.just(1, 2),
                (letter, number) -> letter + number);
// A1, B2
```

`zipWith` is convenient when writing a pipeline step by step; its positional pairing semantics are equivalent to calling two-source `Flux.zip`. `Mono` also supports `zipWith` in a similar pattern.

## 3. How It Works Through Reactive Streams Signals

**Suppose** two `Flux` sources emit:

```text
Publisher P -> p1, p2, p3
Publisher Q -> q1, q2

Downstream subscribe(zip(P, Q))
   |
   +-- zip subscribes to upstream sources
   +-- zip manages demand (request/demand) and internal buffers
   +-- when both p1 + q1 arrive -> onNext((p1, q1))
   +-- when both p2 + q2 arrive -> onNext((p2, q2))
   +-- Q has ended, cannot form a third pair -> onComplete()
```

Technical points to understand accurately:

1. **One output emission requires one element from each source.** A fast source may have to wait for a slow source; zip may buffer data awaiting pairing.
2. **Respects downstream backpressure.** If the subscriber has not requested results, zip must not emit `onNext` beyond demand. However, zip can request from upstream in batches (prefetch) and hold elements in an internal queue; do not assume one downstream `request(1)` always translates to exactly one `request(1)` on *each* source.
3. **Only emits a tuple when all values are present.** A value from P arriving first does not become a tuple on its own; it must wait for Q's value at the corresponding position.
4. **Completes when no further pair can be formed.** Once one source finishes and has no unpaired elements left, zip completes and cancels unnecessary upstreams. There is no policy that inserts `null`/default values to pad up to the longer source's length.
5. **Error propagation.** With standard `zip`, an upstream error terminates the result with `onError` and other sources are cancelled per error handling; there is no “half-filled” tuple. Some `zipDelayError` APIs have a different error-delay policy and should be chosen intentionally.
6. **Subscription and execution:** source Publishers can be subscribed to and execute asynchronously concurrently if they use an appropriate non-blocking foundation; `zip` itself does not create threads or guarantee parallel execution of every source.

Note that two streams with the same element count arriving at different times still pair **by exact position**, provided elements remain in each stream per its contract:

```text
Names:     N1 ------- N2 ------- N3
Balances:        B1 - B2 ---------------- B3
Result:    (N1,B1), (N2,B2), (N3,B3)
```

Do not use `zip` to “match records with the nearest timestamp” or automatically detect mismatched IDs. For data that must join on `userId` or `orderId`, design a key-based join/lookup, or transform the sources so order and keys are verified before zipping.

## 4. When Sources Have Different Lengths or Are Empty

### `Flux.zip` completes according to the shorter source

```java
Flux<String> products = Flux.just("Pen", "Book", "Bag");
Flux<Integer> prices = Flux.just(10, 20);

Flux<String> rows = Flux.zip(products, prices,
        (product, price) -> product + "=" + price);
```

When subscribed, downstream receives `Pen=10`, `Book=20`, then `onComplete`. There is no `Bag=...` line because no matching price exists. However, **you cannot conclude that the third element was definitely never read/buffered inside upstream**; prefetch policies may vary. The contract only guarantees correctly paired output.

### `Mono.zip` with an empty source

```java
Mono<String> profile = Mono.just("An");
Mono<Integer> count = Mono.empty();

Mono<String> result = Mono.zip(
        profile, count, (p, n) -> p + ": " + n);
```

`result` completes with **no `onNext`**. The function `(p, n) -> ...` is not called; zip does not automatically replace `count` with `0`.

If a default value of `0` is valid per business rules, you can apply it explicitly:

```java
Mono<String> result = Mono.zip(
        profile,
        count.defaultIfEmpty(0),
        (p, n) -> p + ": " + n
);
```

Then the result is `An: 0`. Do not overuse defaults to mask missing-data errors: distinguish “no count means 0” from “data not found and should return 404/error”.

**Important subscription detail:** if one `Mono` source completes empty synchronously, `Mono.zip` can terminate early and not subscribe to all remaining sources. Therefore, side effects attached to `doOnSubscribe` on other sources **are not guaranteed to all run**. If you truly need to observe every source's presence, consider a dedicated design such as `singleOptional()` on each Mono before zipping; the result then contains `Optional` and you must handle `Optional.empty()`:

```java
Mono<reactor.util.function.Tuple2<
        java.util.Optional<String>,
        java.util.Optional<Integer>>> pair =
        Mono.zip(
                Mono.just("An").singleOptional(),
                Mono.<Integer>empty().singleOptional()
        );
```

This **changes the result type to represent absence**; it does not turn missing data into an `onNext(null)`.

### `Flux.empty` and hot sources

If a `Flux` completes without emitting any elements, `Flux.zip` cannot form any group, so the result completes empty. With a **hot Publisher**, values may already have been emitted *before* zip subscribed; those values might not be replayed, depending on the source. Therefore, do not treat zip as a history mechanism that can recover missed events.

## 5. Hands-on Test with Java 17+ and Project Reactor

The example below uses **cold, synchronous, finite** sources so stdout is in a deterministic order. It covers combining two sources into a DTO, `Mono.zip`, three sources with `Tuple3`, and an empty `Mono` case. No Spring Boot application is needed to run the demo.

File structure:

```text
reactor-zip-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-zip-demo</artifactId>
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

public class Main {
    record Inventory(String name, int stock) {}

    public static void main(String[] args) {
        // 1) Two Fluxes: corresponding elements -> immutable DTO.
        Flux<Inventory> inventory = Flux.zip(
                Flux.just("Pen", "Book", "Eraser"),
                Flux.just(12, 5),
                Inventory::new
        );

        inventory.subscribe(
                item -> System.out.println(
                        "item: " + item.name() + "/" + item.stock()),
                error -> System.out.println("error: " + error.getMessage()),
                () -> System.out.println("inventory complete")
        );

        // 2) Two Monos: one aggregated result.
        Mono<String> summary = Mono.zip(
                Mono.just("An"),
                Mono.just(3),
                (name, orders) -> name + " has " + orders + " orders"
        );

        summary.subscribe(value -> System.out.println("mono: " + value));

        // 3) Three sources: Reactor returns Tuple3.
        Flux.zip(
                Flux.just("A", "B"),
                Flux.just(1, 2),
                Flux.just(true, false)
        ).subscribe(t -> System.out.println(
                "triple: " + t.getT1() + "/" + t.getT2()
                        + "/" + t.getT3()
        ));

        // 4) One empty Mono: zip completes with no onNext.
        Mono.zip(
                Mono.just("value"),
                Mono.<Integer>empty()
        ).subscribe(
                tuple -> System.out.println("unexpected tuple: " + tuple),
                error -> System.out.println("empty error: " + error),
                () -> System.out.println("empty zip complete")
        );
    }
}
```

From `reactor-zip-demo/`, with JDK 17+ and Maven installed, run:

```bash
mvn -q compile exec:java
```

Stdout printed by the **program** (excluding Maven logs if your environment has custom configuration):

```text
item: Pen/12
item: Book/5
inventory complete
mono: An has 3 orders
triple: A/1/true
triple: B/2/false
empty zip complete
```

**Reading the output:**

1. `Inventory::new` combines **one name** and **one stock quantity** into an `Inventory`. The name source has three values and the quantity source has two; zip emits only two records then completes.
2. `Mono.zip` emits exactly one summary string because both `Mono` sources have a value.
3. Three-source `Flux.zip` produces `Tuple3<String,Integer,Boolean>`; positions `T1`, `T2`, `T3` correspond to the argument order passed to zip.
4. `Mono.empty()` causes the final zip to emit no tuple; only the `onComplete` callback is invoked.
5. No `.block()` is called in the pipeline and there is no manual `subscribe` on each input source. `zip` is responsible for subscribing to and combining the source publishers when the result is subscribed to.

## 6. Using `Mono.zip` in a Spring WebFlux Service

Scenario: an endpoint needs a user profile and the total number of open tickets. Suppose two repositories already support a **reactive, non-blocking** API:

- `profileRepository.findById(id)` returns `Mono<Profile>`.
- `ticketRepository.countOpenByUserId(id)` returns `Mono<Long>`.

You can combine them into a DTO in an **illustrative method inside an existing service**:

```java
record UserDashboard(Profile profile, long openTickets) {}

Mono<UserDashboard> dashboard(long id) {
    Mono<Profile> profileMono = profileRepository.findById(id);
    Mono<Long> countMono = ticketRepository.countOpenByUserId(id);

    return Mono.zip(profileMono, countMono, UserDashboard::new);
}
```

The `Profile` type, the two repositories, and the enclosing method are **application-dependent**, so the snippet above is not a standalone runnable program. Idea:

1. The service creates two sources and returns a `Mono<UserDashboard>`.
2. When the framework subscribes to the result, zip subscribes to and coordinates both sources. Both queries can progress concurrently if the sources are implemented truly asynchronously and have no mutual dependencies.
3. Zip waits for `Profile` **and** `Long`, then calls the constructor `UserDashboard::new`.
4. If one source errors, the regular result errors; if one source is empty, the result is empty. Define explicit handling for both states according to business rules.
5. Spring WebFlux is normally the party subscribing to the Publisher when a controller returns `Mono<UserDashboard>`. Controllers/services do not need to call `.subscribe()` or `.block()` themselves to extract the value.

Additional example if **a missing profile must be 404**, while **a missing count validly defaults to 0**:

```java
Mono<Profile> profileMono = profileRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Profile not found"
                )
        ));

Mono<Long> countMono = ticketRepository.countOpenByUserId(id)
        .defaultIfEmpty(0L);

Mono<UserDashboard> result =
        Mono.zip(profileMono, countMono, UserDashboard::new);
```

This is illustrative code inside a WebFlux application with appropriate imports for `ResponseStatusException` (`org.springframework.web.server`) and `HttpStatus` (`org.springframework.http`). It expresses the missing-data policy **per source before zipping**, preventing the result from becoming empty unexpectedly.

**Note:** `zip` only coordinates the Publishers it receives. If `profileRepository.findById` has side effects immediately when **calling the method to construct the Mono**, those side effects do not become lazy merely because of `zip`; laziness depends on the source's implementation.

## 7. `zip` Does Not Solve Every Stream Combination Pattern

### `zip` and `merge`

```java
Flux<Integer> merged =
        Flux.merge(Flux.just(1, 2), Flux.just(10, 20));
```

`merge` emits **individual elements from the sources** into a shared stream; it does not produce `(1,10)` or `(2,20)`. When sources are asynchronous, interleaving order can differ across runs. `zip` emits only after receiving corresponding elements from **all sources**.

### `zip` and `concat`

`concat` completes the earlier source before appending the next source, preserving sequential order across sources. Use it when you want to **concatenate streams**, not build grouped tuples of values.

### `zip` and `combineLatest`

For sources that emit multiple times, once every source has emitted at least one element, `combineLatest` recomputes a result **every time any source emits a new value**, using the *latest* value from the remaining sources. By contrast, `zip` consumes one value from **each source per output**. For example, a “latest dashboard state” output may fit `combineLatest` better; data aligned pairwise by index fits `zip`.

### `zip` and `flatMap`

`flatMap` transforms **each value from one source** into an inner Publisher and merges the results; `zip` combines **independent Publishers** by position. For example, if each ID requires calling a details API:

```java
// Illustrative: findDetails(id) returns Mono<Details>.
Flux<Details> details = ids.flatMap(id -> service.findDetails(id));
```

If you mechanically use `zip(ids, details)` when `flatMap` can change completion order, IDs and details risk **getting mismatched**. Instead, keep the ID alongside the result inside each inner Publisher or use an approach that preserves keys/order properly.

### `zipWhen`: second source depends on the first source's value

On `Mono`, when you need to create a **second Mono after receiving the first result**, you can use `zipWhen`:

```java
// Illustrative: loadSettings(user.id()) returns Mono<Settings>.
Mono<UserView> view = userService.findById(id)
        .zipWhen(
                user -> settingsService.loadSettings(user.id()),
                (user, settings) -> new UserView(user, settings)
        );
```

`zipWhen` keeps the value from the initial `Mono` and calls the function to create the second source from that value. Contrast with `Mono.zip(a, b)`: both sources can already be prepared independently; `zipWhen` fits **data dependencies**. If the first Mono is empty, the function creating the second Mono is not called.

## 8. Common Errors and Limitations

| Error/confusion | Consequence | How to handle it |
|---|---|---|
| Zipping two business streams by index when records must match by ID | Mismatches people with orders if data is out of order or missing elements | Look up by key, intentionally sort/validate keys, or keep the key inside the same Publisher |
| One source is `Mono.empty()` while expecting zip to still emit a DTO | No `onNext`, so the DTO mapping branch never runs | Use `defaultIfEmpty`, `switchIfEmpty`, or an `Optional` model per business rules |
| One `Flux` source is shorter while expecting leftover elements to be emitted separately | Zip completes when no complete group remains | Choose another combination operator or add a missing-value policy before zip |
| Using `zip` to synchronize by timestamp | Pairs by position rather than by time | Design key-based or time-based windows/joins if needed |
| Performing `block()` inside a source or combinator | Blocks signal-processing threads; risk of stalling the WebFlux event loop | Use Publishers from non-blocking I/O, coordinate with `zip`, and offload blocking libraries onto an appropriate dedicated scheduler |
| Assuming `zip` automatically creates parallel threads | No such guarantee; depends on upstream, scheduler, and sources | Measure/design the specific execution context rather than inferring from the operator name |
| Assuming each downstream `request(1)` produces exactly one upstream `request(1)` | Ignores prefetch and internal queues | Rely on the output contract and demand configuration; monitor buffers under high load |
| Relying on `doOnSubscribe` to guarantee every source runs | A synchronous empty Mono can stop zip before subscribing to all sources | Avoid relying on subscribe-time side effects; consider `singleOptional` or a dedicated collection design |
| Not handling source errors | Standard zip terminates completely with `onError` | Decide which errors propagate, apply bounded retries, or add per-source fallbacks |

Another mistake is creating a **nested Publisher** by zipping with a combinator that returns a `Mono`:

```java
// Illustrative: service.enrich(a, b) returns Mono<Result>.
Mono<Mono<Result>> nested =
        Mono.zip(sourceA, sourceB,
                (a, b) -> service.enrich(a, b));
```

If downstream needs `Mono<Result>`, you can flatten it:

```java
Mono<Result> flat =
        Mono.zip(sourceA, sourceB)
                .flatMap(t -> service.enrich(t.getT1(), t.getT2()));
```

These snippets illustrate return types and require variables `sourceA`, `sourceB`, `service`, and `Result` in your project. `zip` **does not automatically subscribe** to a Mono returned from a combinator. Choose the right operator for the desired type at each step.

## 9. Self-Check Exercises

**Exercise 1.** How many results does `Flux.zip(Flux.just("A", "B", "C"), Flux.just(1, 2))` emit, and with what values?

**Answer:** Two tuples: `("A", 1)` and `("B", 2)`; `"C"` has no partner so it does not appear in the output. No null element is automatically inserted.

**Exercise 2.** Does `Mono.zip(Mono.just("ok"), Mono.empty())` call `onNext`?

**Answer:** No. There are not two elements; zip completes empty without emitting a tuple.

**Exercise 3.** One `Flux` emits 1 then 2 very quickly; another `Flux` emits `"X"` then `"Y"` more slowly. Which value does zip pair `1` with?

**Answer:** With `"X"` (the first element), regardless of the timing difference. The second result is `(2,"Y")` if both sources emit enough elements without errors or cancellation.

**Exercise 4.** Why can `zip(userIds, getDetailsViaFlatMap(userIds))` be dangerous?

**Answer:** `flatMap` results can arrive out of their original order; zip pairs by **received element index**, without checking `userId`. The solution is to keep the key and value together throughout the asynchronous operation, or join by key.

**Exercise 5.** When should you choose `Mono.zip` instead of `flatMap`?

**Answer:** When two or more independent sources already exist and you simply need to combine their results, `Mono.zip` expresses that intent clearly. If the later source **depends on the value** from the earlier source, `flatMap` or `zipWhen` is usually clearer.

**Remember:** `zip` pairs **one element from each Publisher in order**, emits when all values are ready, completes when no next group can be formed, and upholds the demand/error/cancellation contract of reactive streams. In Spring WebFlux, `Mono.zip` is very useful for aggregating independent reactive results into a DTO, provided you clearly understand **empty, error, independence, and positional pairing semantics**.
