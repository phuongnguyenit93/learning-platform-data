# Building a Data Source with `Stream.Builder`

> **Chapter:** Streams from Existing Data  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API, from lazy pipelines and `filter`, `map`, `reduce`, `collect` to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers.

When elements are already in a `List` or array, you can call `list.stream()` or `Arrays.stream(array)`. Sometimes, however, **the data source must be assembled element by element**, such as response messages built from conditional branches, a sequence of business events, or a set of values produced during processing.

`Stream.Builder<T>` lets you construct a finite Stream in this way: **add elements first, call `build()` once, and then process the resulting Stream with a familiar pipeline**.

## 1. What Is `Stream.Builder<T>`?

`Stream.Builder<T>` is a nested interface in `java.util.stream.Stream`, provided since Java 8. It describes a builder that can accept elements of type `T` one by one to create a `Stream<T>`. You obtain a builder via the static method `Stream.builder()`.

```java
import java.util.List;
import java.util.stream.Stream;

public class BuilderQuickStart {
    public static void main(String[] args) {
        Stream.Builder<String> builder = Stream.builder();

        builder.add("Java");
        builder.add("Stream");
        builder.accept("API");

        Stream<String> stream = builder.build();
        List<String> words = stream
                .map(String::toUpperCase)
                .toList(); // Java 16+

        System.out.println(words); // [JAVA, STREAM, API]
    }
}
```

The example demonstrates three important operations:

- `add(T value)`: puts an element into the Builder and **returns the Builder itself**, suitable for chained calls.
- `accept(T value)`: puts an element into the Builder but **returns `void`**. Builder implements `Consumer<T>`, so it provides this method.
- `build()`: finishes building and **returns a `Stream<T>` whose encounter order matches the order in which elements were added**.

`Builder` is the object for **creating the source**; the returned `Stream` is the object for calling `filter`, `map`, `limit`, `collect`, and so on.

## 2. Lifecycle: From Adding Elements to Consuming the Stream

```text
Stream.builder()
      │
      ▼
  Building ── add / accept ── add / accept ── ...
      │
      └────────────────── build() ────────────────┐
                                                 ▼
                                          Created Stream<T>
                                                 │
                                           filter / map / ...
                                                 │
                                            terminal operation
                                                 │
                                                 ▼
                                         Result / side effect
```

There are **two single-use lifecycles** to remember:

1. **A Builder can only call `build()` once.** After this call, the Builder transitions to the built state. Calling `add()`, `accept()`, or `build()` again on the same Builder throws `IllegalStateException`.
2. **The created Stream can also only be consumed once.** After a terminal operation such as `toList()`, `count()`, or `forEach()`, the pipeline cannot be reopened on the same Stream; you must build a new Stream if you want to process again.

Example illustrating **invalid** operations:

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("first");

Stream<String> stream = builder.build();

// Wrong: Builder is already in the built state.
// builder.add("second"); // IllegalStateException
// builder.build();       // IllegalStateException

System.out.println(stream.count()); // 1

// Wrong: Stream has already been consumed.
// stream.toList(); // IllegalStateException
```

You do not need to manually create an intermediate list just to convert to a Stream: the Builder stores the added elements and `build()` places them into a Stream. However, the Builder **still has to hold the received data**; it should not be understood as providing an infinite source or an on-demand generator.

## 3. Concise Chaining with `add()` and Declaring Type `T`

Because `add()` returns `Builder<T>`, you can chain multiple steps:

```java
Stream<String> languages = Stream.<String>builder()
        .add("Java")
        .add("Kotlin")
        .add("Scala")
        .build();

System.out.println(languages.toList());
// [Java, Kotlin, Scala]
```

Here, `Stream.<String>builder()` explicitly specifies the element type. This syntax is useful in long chains because the compiler might infer too broad a type if relying solely on the `add()` calls:

```java
// Clear form when using a variable declaration:
Stream.Builder<Integer> builder = Stream.builder();
builder.add(10).add(20);
Stream<Integer> numbers = builder.build();
```

If you need to insert values across `if` branches, placing the Builder in a variable is usually more readable than chained calls.

## 4. Practical Example: Assembling an Event Stream Conditionally

Suppose you need to construct a status log for an order. Some events are always present; others are only included when the corresponding business condition is true:

```java
import java.util.List;
import java.util.stream.Stream;

public class OrderEvents {
    static Stream<String> createEvents(
            boolean paymentConfirmed,
            boolean delivered) {

        Stream.Builder<String> builder = Stream.builder();

        builder.add("ORDER_CREATED");
        if (paymentConfirmed) {
            builder.add("PAYMENT_CONFIRMED");
        }
        if (delivered) {
            builder.add("DELIVERED");
        }
        builder.add("EVENTS_ASSEMBLED");

        return builder.build();
    }

    public static void main(String[] args) {
        List<String> events = createEvents(true, false)
                .filter(e -> !e.equals("EVENTS_ASSEMBLED"))
                .map(String::toLowerCase)
                .toList();

        System.out.println(events);
        // [order_created, payment_confirmed]
    }
}
```

Key points to note:

- The `add()` statements clearly reflect the **conditions for adding elements** and the **order of occurrence**.
- `createEvents` returns `Stream<String>`, so the caller can continue applying intermediate and terminal operations.
- Each call to `createEvents(...)` creates a **new Builder and Stream**, avoiding reuse of a completed Builder.
- `build()` does not create a `List` result by itself: `toList()` on the caller side is the terminal operation that collects the data.

When business conditions require accessing a database or other resource, clearly determine when data must be read and manage resources properly. Builder is suited for assembling **already-determined values**, not replacing on-demand resource access.

## 5. Builder Does Not Eliminate Pipeline Laziness

A common misconception is thinking `Stream.Builder` also defers evaluating the values passed to `add()`. In reality:

- Expressions used to compute arguments to `add(...)` or `accept(...)` are evaluated **at the moment of the call**.
- `build()` finishes assembling the source and returns the Stream; **it is not a terminal operation** of the Stream.
- Intermediate steps such as `map()` and `filter()` still obey the Stream's **lazy** mechanism: they usually execute only when a terminal operation is called, unless optimized away.

```java
import java.util.stream.Stream;

Stream.Builder<Integer> builder = Stream.builder();

System.out.println("A: preparing source");
builder.add(2 + 3);             // the addition is evaluated here
builder.add(7);

Stream<Integer> pipeline = builder.build()
        .map(n -> {
            System.out.println("map: " + n);
            return n * 10;
        });

System.out.println("B: pipeline not run yet");
System.out.println(pipeline.toList());
```

Output:

```text
A: preparing source
B: pipeline not run yet
map: 5
map: 7
[50, 70]
```

Do not use Builder to simulate an infinite source or a source that generates values one by one on demand. When you want to emit elements as they are traversed, consider `Stream.generate(...)`, `Stream.iterate(...)`, or an appropriately designed `Spliterator`.

## 6. Element Ordering and Parallel Processing

A Stream created by a Builder is an **ordered Stream**: it has an *encounter order* matching the `add`/`accept` order. For example:

```java
List<Integer> result = Stream.<Integer>builder()
        .add(30)
        .add(10)
        .add(20)
        .build()
        .sorted()
        .toList();

// result = [10, 20, 30]
```

Before `sorted()`, the encounter order is `[30, 10, 20]`; afterward, the order is determined by sorting. Builder **does not automatically sort** or deduplicate elements.

`build()` produces a sequential Stream. You can call `parallel()` on the Stream if suitable for the problem, but distinguish between:

- **Phase of adding elements to the Builder:** performed sequentially by your program; do not assume Builder supports multiple threads calling `add()` concurrently.
- **Phase of processing the Stream:** `parallel()` requests parallel execution, but does not guarantee better performance; operations that must preserve order can incur coordination overhead.
- `forEach` on a parallel Stream does not guarantee print order. If order matters, use a terminal operation that preserves encounter order such as `forEachOrdered` or collect into `toList()` while the source remains ordered.

```java
Stream.<String>builder()
        .add("A")
        .add("B")
        .add("C")
        .build()
        .parallel()
        .forEachOrdered(System.out::println);

// A
// B
// C
```

Calling `parallel()` happens **after** `build()`; it does not turn the Builder itself into a parallel data input tool.

## 7. Empty Builder, `null` Values, and Primitive Types

### Adding No Elements

You can create an empty Stream:

```java
Stream<String> empty = Stream.<String>builder().build();
System.out.println(empty.count()); // 0
```

If you know from the start that there are no elements, `Stream.empty()` is usually shorter and states the intent more clearly.

### `null` Values

`Stream.Builder` can accept `null` as an element of a reference Stream. This is **different** from skipping the element:

```java
List<String> values = Stream.<String>builder()
        .add("ok")
        .add(null)
        .add("done")
        .build()
        .toList();

// values = [ok, null, done]
```

Some downstream operations can fail if `null` is not handled; for example, `map(String::length)` will throw `NullPointerException` when encountering `null`. If you want to drop `null`, you can use `filter(java.util.Objects::nonNull)`. For **a single** nullable value, `Stream.ofNullable(value)` (Java 9+) creates an empty Stream when that value is `null`.

### Builders for Primitive Streams

Besides `Stream.Builder<T>`, Java also provides `IntStream.Builder`, `LongStream.Builder`, and `DoubleStream.Builder`. These are suitable when storing primitive integers or floating-point numbers, avoiding unnecessary boxing into `Integer`, `Long`, or `Double`:

```java
import java.util.stream.IntStream;

IntStream.Builder builder = IntStream.builder();
builder.add(10).add(20).accept(30);

int sum = builder.build().sum();
System.out.println(sum); // 60
```

They follow the same lifecycle: add elements first, call `build()` once, then consume the resulting Stream.

## 8. When to Use Builder vs. Other Ways of Creating a Stream?

| Scenario | Suitable approach | Reason |
| --- | --- | --- |
| Already have a `List`, `Set`, or collection | `collection.stream()` | Uses the existing source directly. |
| Already have an array | `Arrays.stream(array)` | No need to copy elements into a Builder. |
| Know a few fixed values upfront | `Stream.of(a, b, c)` | Concise and readable. |
| Have exactly one possibly `null` value | `Stream.ofNullable(value)` | Returns 0 or 1 element. |
| Assemble elements produced across multiple conditional branches | `Stream.Builder<T>` | Adds elements flexibly while maintaining order. |
| Need to join two existing Streams | `Stream.concat(first, second)` | Joins two already existing Stream sources. |
| Need to generate elements on demand, possibly infinite | `Stream.generate(...)` / `Stream.iterate(...)` | Produces values during traversal instead of storing everything upfront. |
| Need a custom source for files, iterators, or parallel splitting | `Spliterator` and `StreamSupport.stream(...)` | Controls traversal mechanism and source characteristics. |

For example, when data is **already in a List**:

```java
List<String> input = List.of("Java", "Stream", "API");
List<String> upper = input.stream()
        .map(String::toUpperCase)
        .toList();
```

There is no need to create a new Builder and iterate over `input` to `add` each element: that approach allocates an extra container without benefit in this simple case.

Conversely, Builder is a clear choice when elements come from **different expressions or conditions**:

```java
Stream.Builder<String> messages = Stream.builder();
messages.add("Start processing");
if (hasWarnings) {
    messages.add("Warnings need checking");
}
if (isComplete) {
    messages.add("Completed");
}

List<String> response = messages.build().toList();
```

If you need to keep a mutable, repeatedly accessible, or long-lived dataset, use an appropriate collection instead of Builder because Builder **does not support adding elements after `build()`**.

## 9. Resource Limits and Common Pitfalls

### 9.1. Using Builder for Very Large Data Volumes

Every value is placed into the Builder before the Stream is created. Thus, Builder does not provide streaming in the sense of **reading and processing incrementally from a large source**. If millions of records already reside in a collection, calling `collection.stream()` is usually more natural; if data is read chunk by chunk from an external source, a lazy traversal mechanism and proper resource management are needed.

### 9.2. Mistaking `build()` for `collect()`

`build()` only finalizes the source and returns a Stream. To get a `List`, `Set`, grouped map, or aggregated value, a terminal operation is still required:

```java
List<String> result = Stream.<String>builder()
        .add("blue")
        .add("green")
        .build()
        .filter(color -> color.length() > 4)
        .toList();

// [green]
```

### 9.3. Reusing a Builder or Stream After Use

This is a lifecycle error, not a concurrency or compile-time error. Create a new Builder for a new assembly pass, and call `build()` exactly once.

### 9.4. Using Builder as an Accumulator in `parallelStream()`

Do not pass a shared Builder into `forEach` of a parallel pipeline:

```java
Stream.Builder<String> shared = Stream.builder();

// Do not do this: multiple threads may call add on the Builder concurrently.
// names.parallelStream().forEach(shared::add);
```

Builder is not designed as a shared accumulator across multiple threads. If the goal is to collect results, use the `collect` terminal operation with an appropriate Collector, such as `Collectors.toList()` or `groupingBy(...)`. If the goal is to create a Stream source from a custom algorithm, design an appropriate source or `Spliterator`.

### 9.5. Leaving Resources Open After Creating the Source

Builder itself does not read or close files, sockets, or database connections. If you obtain elements from a source that has closable resources **during assembly**, manage them where the data is read (e.g. `try-with-resources`). Do not assume `build()` or a terminal operation will automatically release external resources.

## 10. Self-Check Exercises

**Exercise 1 — Predict the output.** What does the following code produce?

```java
List<Integer> result = Stream.<Integer>builder()
        .add(3)
        .add(1)
        .add(3)
        .add(2)
        .build()
        .distinct()
        .sorted()
        .toList();
```

**Answer:** `[1, 2, 3]`. The Builder keeps elements `[3, 1, 3, 2]` in insertion order; `distinct` removes duplicates, and `sorted` sorts ascending.

**Exercise 2 — Lifecycle.** After `Stream<String> s = builder.build();`, can you call `builder.add("x")` to add to `s`?

**Answer:** No. The Builder has entered the built state; the operation will throw `IllegalStateException`. All elements must be added before calling `build()`.

**Exercise 3 — Laziness.** Given `builder.add(expensiveCalculation())`, is the calculation deferred until `toList()` is called?

**Answer:** No. The argument expression is evaluated when `add()` is called. Only the intermediate operations created on the Stream after `build()` typically execute lazily.

**Exercise 4 — Choosing the right tool.** If you want to convert all elements of a `List<String>` to uppercase, do you need Builder?

**Answer:** No. Just use `list.stream().map(String::toUpperCase).toList()`. Builder is more useful when you have to flexibly add multiple independent elements before having a Stream source.

## Key Takeaways

- `Stream.Builder<T>` is used to **assemble a finite Stream source**, in element insertion order, using `add` or `accept`.
- `add` returns the Builder for chaining; `accept` returns `void`; `build` returns a **sequential ordered Stream**.
- **A Builder can only `build()` once; a Stream can also only be consumed once**. Calling further operations on a completed Builder throws `IllegalStateException`.
- Values passed to `add` are evaluated **at the time of adding**; the pipeline on the resulting Stream can still execute **lazily**.
- For existing sources, prefer `collection.stream()` or `Arrays.stream(...)`; for lazily generated or large-scale sources, choose `generate`, `iterate`, or `Spliterator` as appropriate. Do not use a shared Builder to collect results from multiple parallel threads.
