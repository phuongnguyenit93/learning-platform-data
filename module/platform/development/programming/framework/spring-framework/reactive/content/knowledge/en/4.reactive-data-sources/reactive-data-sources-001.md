# Creating Pre-existing Data with `just`, `fromIterable`, and `range` in Project Reactor

## 1. Objectives and Context

In Spring Framework Reactive, especially Spring WebFlux, Project Reactor's `Mono<T>` and `Flux<T>` represent data sources that follow Reactive Streams. When **data is already available in memory**, three common factory methods to turn that data into a Publisher are `just`, `fromIterable`, and `range`.

After finishing this lesson, you need to choose the right method from the input data type, predict the order of emitted signals, understand the difference between Publisher creation time and subscription time, handle empty streams or `null` values, and avoid confusing the `count` parameter of `range` with an upper bound.

The following program creates a **source** without requesting to receive data yet:

~~~java
Flux<String> colors = Flux.just("red", "blue", "yellow");
~~~

Normally, when a subscriber subscribes (for example, by calling `subscribe`), the source starts sending `onNext` according to `request(n)` demand, then `onComplete` when finished emitting; if an error occurs, it sends `onError`. All three sources in this lesson are **finite** sources, typically processed **synchronously** when no scheduler-changing operator is attached. Simply converting a `List` to a `Flux` does not automatically make I/O asynchronous, does not automatically spawn threads, and does not make the program faster.

## 2. Quick Comparison of the Three Factory Methods

| Method | Input Data | Return Type | Number of Emitted Elements | Suitable Use Case |
| --- | --- | --- | --- | --- |
| `Mono.just(value)` | A non-null object | `Mono<T>` | Exactly 1 | An existing value, such as a configuration, an ID, an object |
| `Flux.just(a, b, c)` | Listed objects | `Flux<T>` | Equal to the number of passed objects | A few fixed values for demonstration or initialization |
| `Flux.fromIterable(iterable)` | `Iterable<? extends T>` such as `List`, `Set`, `Collection` | `Flux<T>` | Equal to the number of elements the iterator provides | Already have a dataset in memory |
| `Flux.range(start, count)` | Two `int` numbers | `Flux<Integer>` | `count` consecutive integers, if `count > 0` | Generating sequence numbers, testing, running a transformation N times |

Short examples:

~~~java
Mono<String> single = Mono.just("Spring");                 // Spring
Flux<String> fixed = Flux.just("A", "B", "C");              // A, B, C
Flux<String> fromList = Flux.fromIterable(List.of("X", "Y")); // X, Y
Flux<Integer> numbers = Flux.range(5, 3);                 // 5, 6, 7
~~~

The end-of-line comments represent the **values that will be emitted when there is a subscription and demand**, not the immediate return result of the Publisher creation statement.

## 3. `just`: Creating a Source from One or a Few Known Values

### 3.1. `Mono.just(T)` for Exactly One Value

`Mono.just("hello")` creates a `Mono<String>` that has one `onNext("hello")` then `onComplete()`. When you already have a concrete object, such as a record pre-read from cache or a configuration constant, this is the simple choice.

~~~java
Mono<String> greeting = Mono.just("Hello");

greeting.subscribe(
    value -> System.out.println("value=" + value),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Stdout:

~~~text
value=Hello
complete
~~~

`Mono.just` does not accept `null`. If the value may be absent, use `Mono.justOrEmpty(nullableValue)` or `Mono.empty()`; do not emit `null` via `onNext` because Reactive Streams forbids null data. The case of **no data** differs from the case of **having one element whose content is an empty string** (`Mono.just("")` still emits one element).

### 3.2. `Flux.just(T...)` for a Directly Listed Sequence of Values

~~~java
Flux<String> statuses = Flux.just("NEW", "PAID", "SHIPPED");
Flux<Integer> primes = Flux.just(2, 3, 5, 7);
~~~

`Flux.just` emits elements in the order they were passed and then completes. This choice is good for small, fixed sources; with an existing `List`, using `fromIterable` expresses the intent more clearly. Note:

- `Flux.just(list)` has type `Flux<List<T>>`: it emits **one element which is the entire list**. `Flux.fromIterable(list)` has type `Flux<T>`: it emits **each element** of the list. Do not confuse the two cases.
- Do not pass `null` as an element; for 0 elements, use `Flux.empty()`.
- With values that are mutable objects, `just` holds a reference to the object; it does not automatically deep-copy the object's state.
- Two independent subscribers can subscribe to the same `Flux.just` source and each subscriber receives the entire sequence from the beginning, unless a sharing/caching operator that changes semantics has been added.

### 3.3. "Pre-existing" Means the Input Expression Is Evaluated Immediately

Distinguish between **evaluating a Java expression** and **a Publisher emitting signals**:

~~~java
String title = loadTitleFromMemory();   // function runs immediately on this line
Mono<String> value = Mono.just(title);  // holds the already-computed value
// No subscriber yet, but loadTitleFromMemory() has already run.
~~~

Similarly, `Mono.just(loadTitleFromMemory())` **calls the function immediately when building the source**, before `subscribe`. If you need to execute the function *on each subscription*, use `Mono.fromSupplier(() -> loadTitleFromMemory())` or `Mono.defer(() -> Mono.just(loadTitleFromMemory()))`. These are other factory methods to solve the problem of deferred data creation; you should not force `just` to take on this behavior.

### 3.4. Should You Use `Mono.just` or `Flux.just` for One Object?

Both can emit one element, but the return type communicates the contract:

- One result or no result: prefer `Mono<T>` (e.g., lookup by ID).
- A 0..N result set: prefer `Flux<T>` (e.g., returning multiple statuses or multiple rows).
- `Mono<T>` is not a `Flux<T>`; you can convert with `mono.flux()` if an API needs to return a `Flux`.

## 4. `Flux.fromIterable`: Emitting Elements of an Existing Collection One by One

### 4.1. From `List` and `Set`

`Flux.fromIterable(Iterable<? extends T>)` retrieves elements through `Iterable` traversal, preserving the order provided by the iterator. With `List`, the emission order usually matches the order of elements in the list:

~~~java
List<String> cities = List.of("Hà Nội", "Đà Nẵng", "Cần Thơ");
Flux<String> cityFlux = Flux.fromIterable(cities);

cityFlux.subscribe(System.out::println);
~~~

Stdout:

~~~text
Hà Nội
Đà Nẵng
Cần Thơ
~~~

With `Set`, the order depends on the implementation: `HashSet` does not guarantee logical order, whereas `LinkedHashSet` preserves insertion order. If business logic requires a deterministic order, choose `List` or a collection with an appropriate ordering contract.

An empty `List.of()` yields a `Flux` that **emits no `onNext`** and only `onComplete`:

~~~java
Flux.fromIterable(List.<String>of())
    .subscribe(
        value -> System.out.println("onNext=" + value),
        error -> System.out.println("onError=" + error),
        () -> System.out.println("onComplete")
    );
// Prints only: onComplete
~~~

### 4.2. Each Subscription Re-iterates the Iterable

`fromIterable` holds the `Iterable` object and pulls data to emit when subscribed. Therefore, with a mutable `List`, the content seen on a later subscription can differ from an earlier subscription:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));
Flux<String> namesFlux = Flux.fromIterable(names);

namesFlux.subscribe(name -> System.out.println("Run 1: " + name));
names.add("Chi");
namesFlux.subscribe(name -> System.out.println("Run 2: " + name));
~~~

Stdout:

~~~text
Run 1: An
Run 1: Bình
Run 2: An
Run 2: Bình
Run 2: Chi
~~~

This does **not** mean `Flux` observes and pushes changes of the `List` over time: modifying the list **does not automatically emit an event** to an already-completed subscriber. The example above has **two separate subscriptions**. Modifying a collection **concurrently while iterating** can cause errors or undefined results depending on the implementation, so use a stable data source during emission.

If you want a snapshot independent of list-level changes, you can copy the data beforehand:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(source); // immutable copy at the list level
Flux<String> frozen = Flux.fromIterable(snapshot);

source.add("C"); // frozen still emits only A, B
~~~

`List.copyOf` rejects null elements; and for mutable inner objects, the snapshot only copies the list structure, not deep-copying the objects.

### 4.3. Requirements of a Re-subscribable Iterable

According to the Reactor Javadoc, `fromIterable` may call `Iterable.iterator()` **once or twice per subscriber**, because it needs to check finiteness characteristics for cancellation/discarding remaining elements. Therefore, a custom `Iterable` should return a valid iterator each time, and not assume the `iterator()` method is always called exactly once or that the same single iterator can be consumed forever.

Do not confuse `Iterable` with `Iterator`: an `Iterator` is a stateful traversal cursor, whereas `Iterable` is the capability to provide an iterator. If multiple subscriptions are needed, the source must be re-iterable. If the input is an array, the direct way is `Flux.fromArray(array)`; if it is a single-use `Stream`, consider `Flux.fromStream(() -> createStream())` to create a new stream for each subscription. These two APIs are just alternatives matching the input form; the focus of this lesson remains `fromIterable`.

### 4.4. Null, Exceptions, and Resources

- The `Iterable` and elements sent via `onNext` must not be `null`. A `null` element from a collection will lead to an error, rather than representing "skipping the element".
- If the iterator throws an exception during traversal, the sequence enters the `onError` path; you need to determine how downstream handles errors.
- `fromIterable` is for data that is already iterable. If the iterator performs thread-blocking I/O (reading DB, file, HTTP), using `Flux.fromIterable` **does not turn that I/O into non-blocking**; you need to integrate a reactive API or proper scheduling.

## 5. `Flux.range(start, count)`: Generating Consecutive Integers

Signature:

~~~java
static Flux<Integer> range(int start, int count)
~~~

`start` is the **first value** (inclusive), and `count` is the **number of elements to emit**. When `count > 0`, the sequence is:

~~~text
start, start + 1, ..., start + count - 1
~~~

Examples:

| Expression | Emitted Data | Explanation |
| --- | --- | --- |
| `Flux.range(5, 3)` | `5, 6, 7` | Starts at 5 and emits 3 numbers |
| `Flux.range(1, 5)` | `1, 2, 3, 4, 5` | Starts at 1 and emits 5 numbers |
| `Flux.range(0, 4)` | `0, 1, 2, 3` | Can start at 0 |
| `Flux.range(-2, 3)` | `-2, -1, 0` | Can start with a negative number |
| `Flux.range(9, 1)` | `9` | Only one element |
| `Flux.range(9, 0)` | No `onNext` | Empty stream, completes immediately |

**Common mistake:** `Flux.range(5, 10)` generates **ten** numbers from 5 to 14, not the numbers from 5 to 10. If you want numbers from `a` to `b`, with `a <= b` and arithmetic that does not overflow `int`, use `Flux.range(a, b - a + 1)`; validate bounds before computing for user input.

`count < 0` is an invalid argument; a range exceeding the `Integer` representation domain is also invalid. Do not try to represent sequences exceeding `Integer.MAX_VALUE` with `range`; use a different type and source creation approach if the problem requires large numbers.

`range` does not need to pre-create a `List<Integer>` containing all elements. When a subscriber requests data, it can compute the next element, respecting the requested amount (`request(n)`). This is especially useful for test data or generating sequence numbers without consuming memory linearly with the number of elements.

## 6. Emission Timing, Backpressure, and Source Characteristics

The three factory methods create a `Publisher`; the `subscribe` method attaches a `Subscriber` to the stream:

~~~text
Source creation (assembly):
Flux.range(3, 3)           -> Flux object, no onNext yet

Subscription:
subscribe(subscriber)      -> onSubscribe(subscription)
subscriber.request(2)      -> onNext(3), onNext(4)
subscriber.request(1)      -> onNext(5), onComplete()
~~~

This is the conceptual signal flow with a subscriber controlling demand. Overloads like `subscribe(Consumer)` usually request an unlimited amount of data, so all elements of a finite source are emitted immediately on the calling thread if no other scheduler is used. With a callback API that needs to control demand, you can use `BaseSubscriber` and `request(n)`.

Characteristics to keep in mind:

1. **Cold source by default:** Each subscription has its own emission cycle. `Flux.just` replays the held elements; `fromIterable` may see the updated state of the Iterable; `range` recomputes the same number sequence.
2. **Backpressure:** `just`, `fromIterable`, and `range` can respect `request(n)`. Demand is the maximum number of elements the receiver allows the source to send at that time, not a requirement that the source must emit that many if it has already run out of data.
3. **Finite termination:** After emitting all data, the source sends `onComplete`. An empty source can still complete without emitting any elements.
4. **Cancellation:** `Subscription.cancel()` asks upstream to stop. With a very short pre-existing source and `subscribe(Consumer)` running synchronously, the data may have already finished emitting before you have a chance to cancel from outside.
5. **Not automatically asynchronous:** No new thread is created just by calling `just`, `fromIterable`, or `range`. The `publishOn`/`subscribeOn` operators and the WebFlux runtime have their own roles; only add a scheduler when genuinely needed and when you understand thread limits.

## 7. Complete, Runnable Java 17+ Program

The example uses Project Reactor Core 3.8.8 (stable release) and Maven. Create two files with the exact structure:

~~~text
reactor-ready-data/
├── pom.xml
└── src/main/java/example/ReadyDataSources.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-ready-data</artifactId>
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
                    <mainClass>example.ReadyDataSources</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/ReadyDataSources.java`**

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReadyDataSources {
    public static void main(String[] args) {
        System.out.println("1. just");

        Mono.just("user-7").subscribe(
            value -> System.out.println("mono=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("mono complete")
        );

        Flux.just("red", "blue").subscribe(
            value -> System.out.println("fixed=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("fixed complete")
        );

        System.out.println("2. fromIterable");

        List<String> colors = new ArrayList<>(List.of("red", "blue"));
        Flux<String> fromList = Flux.fromIterable(colors);
        fromList.subscribe(value -> System.out.println("first=" + value));

        colors.add("green");
        fromList.subscribe(value -> System.out.println("second=" + value));

        System.out.println("3. range");

        Flux.range(5, 3).subscribe(
            value -> System.out.println("number=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("range complete")
        );

        System.out.println("4. backpressure");

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("subscribed");
                // No request yet: the source is not allowed to emit onNext.
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("done");
            }
        };

        Flux.range(10, 4).subscribe(subscriber);
        subscriber.request(2);
        subscriber.request(2);

        System.out.println("5. empty");

        Flux.fromIterable(List.<String>of()).subscribe(
            value -> System.out.println("unexpected=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("empty list complete")
        );

        Flux.range(42, 0).subscribe(
            value -> System.out.println("unexpected=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("zero range complete")
        );
    }
}
~~~

Run from the `reactor-ready-data` directory (with JDK 17+ and Maven installed):

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
1. just
mono=user-7
mono complete
fixed=red
fixed=blue
fixed complete
2. fromIterable
first=red
first=blue
second=red
second=blue
second=green
3. range
number=5
number=6
number=7
range complete
4. backpressure
subscribed
received=10
received=11
received=12
received=13
done
5. empty
empty list complete
zero range complete
~~~

Result meaning:

- `just` emits the exact listed values; `Mono` has one value, `Flux` has two values.
- `fromIterable` uses the same `List` object but re-iterates on the second subscription, so the later subscription sees the `green` element added beforehand.
- `range(5, 3)` emits three numbers 5–7.
- The subscriber controls `request(2)` twice, receiving four numbers sequentially before `onComplete`.
- An empty `List` and `range` with `count=0` emit only the completion signal.

## 8. Applying in Spring WebFlux

In a Spring WebFlux controller, you can **return a Publisher** for the framework to manage the subscription when handling HTTP. The following example illustrates a controller class in a project that **already has the Spring WebFlux dependency** (not part of the standalone Reactor Core Maven program in section 7):

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping("/version")
    public Mono<String> version() {
        return Mono.just("v1");
    }

    @GetMapping("/categories")
    public Flux<String> categories() {
        List<String> items = List.of("books", "games", "tools");
        return Flux.fromIterable(items);
    }

    @GetMapping("/positions")
    public Flux<Integer> positions() {
        return Flux.range(1, 4);
    }
}
~~~

The endpoints respectively represent a string, a collection of strings, and four integers. **Do not call `subscribe()` yourself in the handler** because the framework handles subscription, error propagation, and cancellation when processing the response. The sources in the example are useful for demos, configuration data, or small fixtures; for real data from a database, use a reactive repository/driver if available.

Returning `Flux<T>` **does not guarantee that each element is pushed immediately to the browser**. HTTP rendering also depends on `produces`, codecs, buffering, and media types. To require streaming elements one by one over time, you need an appropriate response contract such as SSE or NDJSON; that is separate from how `Flux` is created.

## 9. Choosing the Right Method in Real-World Scenarios

| Scenario | Recommended | Why |
| --- | --- | --- |
| Already have a non-null `Product` object | `Mono.just(product)` | Single-result contract |
| Three fixed statuses in code | `Flux.just("NEW", "PAID", "DONE")` | Readable, no need to create a collection |
| Already have `List<Order>` | `Flux.fromIterable(orders)` | Emits each `Order` and preserves List order |
| Want 100 sequence numbers starting from 1 | `Flux.range(1, 100)` | Does not create a 100-element List |
| Legacy API returns a possibly `null` object | `Mono.justOrEmpty(value)` | Represents an absent result per the rules |
| Empty collection | `Flux.fromIterable(List.of())` or `Flux.empty()` | Has `onComplete` without `onNext` |
| Data computed expensively on each subscribe | `Mono.fromSupplier` / `Mono.defer` | Does not evaluate the function at assembly time |
| Want 0..N results from a reactive DB | Publisher from driver/repository | Do not try to use a collection that has not been loaded |

## 10. Common Mistakes and How to Check

**Mistake 1 — Interpreting `count` as the ending value.** `Flux.range(4, 3)` emits `4, 5, 6`, not `4, 5, 6, 7` or `3, 4`. Always double-check with the rule `start + count - 1`.

**Mistake 2 — Wrapping an entire `List` with `Flux.just(list)`.** A subscriber receives exactly **one** `List` object. If you expect the elements of the List, use `fromIterable(list)`.

**Mistake 3 — Passing `null` to `just` or a collection containing `null`.** Reactive Streams forbids `onNext(null)`. Use `Mono.empty()`, `Mono.justOrEmpty`, `filter`/`handle`, or strip null values at the input boundary depending on business logic.

**Mistake 4 — Assuming every source runs in the background or spawns a new thread.** These pre-existing sources typically run synchronously on demand; putting blocking tasks directly inside `map` or an iterator can still block the event loop.

**Mistake 5 — Assuming `fromIterable` is a snapshot.** It holds a reference to the Iterable, so the List contents can change between subscriptions. If you need stable data, create a copy at the appropriate time.

**Mistake 6 — Creating a single-use custom Iterable.** `iterator()` may be called up to twice per subscriber. The source must obey Iterable semantics, especially if re-subscription is allowed.

**Mistake 7 — Using `Flux.range` for an overly large range or invalid arguments.** Check `count >= 0`, `int` limits, and the risk of overflow when computing count from two bounds.

**Mistake 8 — Evaluating an expensive function in `Mono.just(service.load())` and expecting it to run only on subscribe.** Java evaluates arguments first; for lazy processing, choose `fromSupplier`/`defer` with the right semantics.

**Mistake 9 — Ignoring errors when trying `subscribe`.** For learning examples, pass an error consumer and completion callback to observe all three signal types. In WebFlux, return the Publisher to the framework instead of subscribing yourself.

**Mistake 10 — Assuming all collections have the same emission order.** `fromIterable` respects iterator order; `HashSet` has no fixed order by contract, unlike `List`.

## 11. Self-Check Exercises

1. Given `Flux.range(8, 4)`, list the emitted values. **Answer:** 8, 9, 10, 11.
2. Given `List<String> fruits = List.of("orange", "apple");`. How many elements does `Flux.just(fruits)` emit? How many elements does `Flux.fromIterable(fruits)` emit? **Answer:** Respectively 1 element of type `List<String>` and 2 elements of type `String`.
3. Does `Flux.range(1, 0)` emit the number 1? **No**. The stream is empty and completes.
4. Create `Flux<String> p = Flux.fromIterable(list)` and then modify `list` before `subscribe`. Can the contents change? **Yes**, because the `Iterable` is traversed for the subscription; this does not create automatic push updates.
5. Why can `Mono.just(fetch())` execute `fetch()` even though no one has subscribed yet? **Because Java evaluates arguments when calling the method**; to defer, use `Mono.fromSupplier(fetch::call)` or `defer` with an appropriate function.
6. Does `Flux.range(1, 1_000_000)` need to create a `List` of one million numbers before emitting? **No**. The source generates the sequence per subscription/demand.

## 12. References

- [Project Reactor Reference – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).
- [Project Reactor API – Flux.just, Flux.fromIterable, Flux.range](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor API – Mono.just and Mono.justOrEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm#specification): concepts of Subscriber, Subscription, `request`, signals, and the requirement not to emit null.