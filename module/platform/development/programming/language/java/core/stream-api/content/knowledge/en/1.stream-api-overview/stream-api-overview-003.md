# The Data Source, Intermediate Operation, and Terminal Operation Model

> **Chapter:** Stream API Overview  
> **Module:** JAVA_STREAM_API  
> **Focus:** Understand how a Stream pipeline is created, transformed, executed, and terminated.

The Java Stream API allows expressing the processing of a sequence of elements in a declarative style: describing **what to filter, how to transform, and how to aggregate the result**, rather than manually controlling every loop. In the **JAVA_STREAM_API** module, this pipeline model is the foundation for learning `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers. Before using advanced techniques, it is essential to clearly distinguish three components: **data source**, **intermediate operations**, and **terminal operation**.

## 1. The big picture: a pipeline has three parts

A Stream pipeline typically has this structure:

```text
Data source
    │
    ▼
Stream<T> ──► intermediate 1 ──► intermediate 2 ──► ... ──► terminal
                  filter              map                    toList
                                                               │
                                                               ▼
                                                       Result / side effect
```

- **Data source:** supplies elements to the pipeline, such as a `List`, an array, a number range, lines in a file, or a source that generates elements on demand.
- **Intermediate operation:** accepts a Stream and returns another Stream, typically used to filter, transform, sort, or limit elements. There can be **0, 1, or many** intermediate operations.
- **Terminal operation:** triggers evaluation of the pipeline as needed, then produces a result or performs a side effect such as counting, searching, aggregating, or iterating over elements.

Example:

```java
List<Integer> prices = List.of(80, 250, 120, 400, 250);

List<Integer> result = prices.stream()     // Source: List<Integer>
    .filter(price -> price >= 200)          // Intermediate: keep price >= 200
    .map(price -> price / 10)                // Intermediate: change unit
    .distinct()                              // Intermediate: remove duplicates
    .toList();                               // Terminal: create List<Integer>

// result = [25, 40]
```

`prices` remains the original list. The pipeline produces a different result; a Stream itself is **not** a data storage container. Elements are drawn from the source and pass through the declared operations when the pipeline is executed.

An important pattern to remember:

1. Create a Stream from a source.
2. Declare the intermediate steps.
3. Call a terminal operation to obtain a result.
4. Do not reuse the same Stream object once it has terminated.

This is the **common usage pattern**, which does not mean every terminal operation must read the entire source. Some operations can stop early or optimize without traversing every element.

## 2. Data source: where do elements come from?

The source determines the element type, whether it is finite or infinite, the encounter order (if any), and sometimes whether resources need to be closed.

| Source | How to create the Stream | Meaning |
| --- | --- | --- |
| `Collection` | `list.stream()` | Reads elements of the collection using its traversal mechanism. |
| Array | `Arrays.stream(array)` | Creates a Stream from an array. Has overloads for primitive arrays. |
| Direct values | `Stream.of("A", "B")` | Creates a Stream from the given values. |
| Integer range | `IntStream.range(1, 5)` | Generates `1, 2, 3, 4`; the upper bound is exclusive. |
| Text lines in a file | `Files.lines(path)` | Reads lines on demand, tied to an I/O resource that must be closed. |
| Infinite generation | `Stream.generate(supplier)` | Calls the element supplier as the pipeline requests elements. |
| Iterative sequence | `Stream.iterate(seed, next)` | Generates a continuing sequence from an initial seed value. |

Example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

class SourceExamples {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");
        long fromList = names.stream().count();               // 3

        int[] scores = {7, 9, 6};
        int fromArray = Arrays.stream(scores).sum();          // 22

        List<Integer> fromRange = IntStream.range(1, 5)
            .boxed()
            .toList();                                        // [1, 2, 3, 4]

        List<String> fromValues = Stream.of("x", "y").toList(); // [x, y]

        List<Integer> firstThree = Stream.iterate(1, n -> n * 2)
            .limit(3)
            .toList();                                        // [1, 2, 4]

        System.out.println(fromList + fromArray);
        System.out.println(fromRange);
        System.out.println(fromValues);
        System.out.println(firstThree);
    }
}
```

The examples use `List.of` (Java 9+) and `Stream.toList` (Java 16+). In Java 8, you can replace the terminal `.toList()` with `.collect(Collectors.toList())`; these two approaches **do not share the same guarantee regarding the mutability** of the resulting list.

### 2.1. Object Streams and primitive Streams

- `Stream<T>` represents reference-type elements, such as `Stream<String>` or `Stream<Order>`.
- `IntStream`, `LongStream`, and `DoubleStream` support primitive values, avoiding unnecessary boxing and providing terminal operations such as `sum()`, `average()`, and `summaryStatistics()`.
- `mapToInt`, `mapToLong`, and `mapToDouble` convert from `Stream<T>` to a primitive Stream; `boxed()` converts back to a Stream of wrapper objects.

Example:

```java
double average = List.of(10, 20, 30).stream()
    .mapToInt(Integer::intValue)
    .average()
    .orElse(0.0); // 20.0
```

`average()` returns `OptionalDouble` because the source might contain no elements. `orElse(0.0)` is a default policy chosen by the programmer, not a default average value built into the API.

### 2.2. Sources do not necessarily hold all data upfront

A Stream from a `List` has an already existing collection. Conversely, `Files.lines(...)` can read on demand and `Stream.iterate(...)` can produce a sequence with no natural end. Therefore, **creating a Stream does not mean copying the entire source into memory**.

With potentially infinite sources, you must choose a terminal operation that can stop early or set an appropriate limit:

```java
List<Integer> tenSoChan = Stream.iterate(0, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(10)
    .toList(); // [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
```

If you omit `limit(10)` and call `toList()`, the pipeline above has no terminating condition. In addition, placing an operation that needs to see all elements, such as `sorted()`, before `limit()` on an infinite source can prevent the pipeline from ever producing a result.

### 2.3. I/O sources require resource management

`Files.lines` returns a `Stream<String>` backed by a file resource. The Stream must be closed when finished, even if an error occurs:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class FileLinesExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Stream<String> lines = Files.lines(path)) {
            long nonEmptyLines = lines
                .filter(line -> !line.isBlank())
                .count();

            System.out.println(nonEmptyLines);
        }
    }
}
```

The example assumes `data.txt` exists. `try-with-resources` guarantees `close()` is called. **A terminal operation does not automatically close a Stream**; with sources such as collections, there is usually no external resource to release.

## 3. Intermediate operations: describing how to process

Intermediate operations return a Stream so multiple steps can be chained with dots. These operations are **typically lazy (lazily evaluated)**: calling `filter`, `map`, or `sorted` does not immediately scan the entire source. They set up the processing chain, while fetching elements happens when a terminal operation needs data.

| Operation | Primary effect | Common characteristics |
| --- | --- | --- |
| `filter(predicate)` | Keeps elements matching the condition. | Does not change the element type. |
| `map(function)` | Transforms each element into another value. | Can change types, e.g., `Stream<Order>` to `Stream<Long>`. |
| `flatMap(function)` | Maps each element to a Stream and flattens the sub-streams. | Useful for nested lists. |
| `distinct()` | Removes duplicate elements according to `equals`. | Must track elements already seen; stateful. |
| `sorted()` / `sorted(comparator)` | Sorts elements. | Typically must collect data before emitting results. |
| `limit(n)` | Keeps at most `n` elements. | Can allow the pipeline to short-circuit. |
| `skip(n)` | Skips up to the first `n` elements. | Counting/skipping relates to ordering and state. |
| `peek(action)` | Attaches an observation action as elements pass through. | Primarily for diagnostics; unsuitable for mandatory business logic. |

Example of `filter` and `map`:

```java
List<String> users = List.of("  An  ", " Bình ", "  Chi ");

List<String> normalized = users.stream()
    .map(String::trim)
    .filter(name -> name.length() >= 3)
    .toList();

// normalized = [Bình, Chi]
```

Step order can change the result. If you filter by length **before** calling `trim`, leading/trailing spaces can let a short name pass the condition. Order the steps to match the actual business rules.

### 3.1. How does `map` differ from `flatMap`?

Suppose each group has a list of skills:

```java
List<List<String>> groups = List.of(
    List.of("Java", "SQL"),
    List.of("Docker", "Git")
);

List<Integer> sizes = groups.stream()
    .map(List::size)
    .toList(); // [2, 2]

List<String> allSkills = groups.stream()
    .flatMap(List::stream)
    .toList(); // [Java, SQL, Docker, Git]
```

`map(List::size)` produces **one result per input list**. `flatMap(List::stream)` creates a Stream of skills for each group and then concatenates them into a flat stream of elements. The number of output elements from `flatMap` can be 0, 1, or many per input element.

### 3.2. Stateless and stateful operations

`filter` and `map` are typically **stateless** operations: processing one element does not require remembering previous elements. By contrast:

- `distinct()` needs to know which values have already been seen in order to remove duplicates.
- `sorted()` needs enough data to determine the sort order; with infinite sources, this is typically an obstacle that cannot complete.
- `limit()` and `skip()` depend on how many elements have passed through, making them stateful intermediate operations.

This distinction affects memory usage, short-circuiting capability, and parallel execution cost. In particular, stateful operations combined with ordering requirements can reduce parallel efficiency.

## 4. Terminal operations: triggering and receiving results

A terminal operation causes the pipeline to be evaluated **to the extent necessary to produce a result**. The result may be a collection, a single value, an `Optional`, or a side effect without returning a value.

| Operation | Return value | When to use |
| --- | --- | --- |
| `toList()` | `List<T>` | Want to obtain a result list. |
| `collect(collector)` | Depends on the collector | Grouping, joining strings, building maps, computing statistics. |
| `count()` | `long` | Count the number of elements. |
| `reduce(...)` | Value or `Optional` | Combine elements using an associative operation. |
| `sum()` on primitive Streams | Number | Compute the sum of numbers. |
| `min(...)` / `max(...)` | `Optional<T>` | Find the minimum/maximum element. |
| `findFirst()` / `findAny()` | `Optional<T>` | Find one element; can short-circuit. |
| `anyMatch` / `allMatch` / `noneMatch` | `boolean` | Check a condition across elements. |
| `forEach(action)` | `void` | Perform an action on each element. |

Example using the same source, where **each terminal operation requires a new Stream**:

```java
List<Integer> amounts = List.of(50, 120, 250, 80);

long expensiveCount = amounts.stream()
    .filter(amount -> amount >= 100)
    .count(); // 2

boolean hasVeryExpensive = amounts.stream()
    .anyMatch(amount -> amount > 200); // true

int total = amounts.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 500
```

### 4.1. `reduce` and `collect` handle two different kinds of aggregation

`reduce` is suited for combining elements into a single value using an associative operation, such as a sum or product:

```java
int sum = List.of(5, 10, 15).stream()
    .reduce(0, Integer::sum); // 30
```

Here `0` is the identity value of addition; `Integer::sum` combines two values. When running in parallel, the reduction operator must satisfy associativity and follow the `reduce` contract. Do not use a shared mutable accumulator across elements as a `reduce` operator.

`collect` is suited for building a mutable result container during accumulation, such as grouping orders by category:

```java
Map<String, List<String>> byFirstLetter = List.of("An", "Anh", "Bình")
    .stream()
    .collect(Collectors.groupingBy(name -> name.substring(0, 1)));

// byFirstLetter contains groups "A" -> [An, Anh] and "B" -> [Bình]
```

`Collectors.groupingBy` is a collector that builds a map of groups. Topics such as downstream collectors and custom collectors build directly on this terminal mechanism.

**Note on lists:** `Stream.toList()` (Java 16+) returns a list that cannot have elements added, removed, or replaced. `Collectors.toList()` makes no specific guarantees about the implementation type or mutability. If you need a mutable `ArrayList`, specify it explicitly: `collect(Collectors.toCollection(ArrayList::new))`.

### 4.2. Short-circuiting terminal operations

You do not always need to read the entire source:

```java
boolean exists = Stream.of(3, 7, 12, 18)
    .anyMatch(n -> n % 2 == 0); // true, can stop upon encountering 12

Optional<Integer> first = Stream.of(3, 7, 12, 18)
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[12]
```

`findFirst` respects encounter order if the source is ordered. `findAny` allows selecting any matching element, which is especially useful in parallel execution. `allMatch` on an empty source returns `true`; `anyMatch` on an empty source returns `false` by definition of these matching operations.

## 5. Lazy evaluation and how data actually flows through a pipeline

Consider the following program:

```java
import java.util.Optional;
import java.util.stream.Stream;

class LazyExample {
    public static void main(String[] args) {
        Stream<Integer> pipeline = Stream.of(1, 2, 3, 4, 5)
            .filter(n -> {
                System.out.println("filter " + n);
                return n % 2 == 0;
            })
            .map(n -> {
                System.out.println("map " + n);
                return n * 10;
            });

        System.out.println("Pipeline declared");
        Optional<Integer> first = pipeline.findFirst();
        System.out.println(first);
    }
}
```

When run sequentially, the output order is:

```text
Pipeline declared
filter 1
filter 2
map 2
Optional[20]
```

From this we observe three things:

1. Creating `pipeline` does not invoke `filter` or `map` immediately.
2. When `findFirst()` requests data, elements pass through the applicable steps; for example, element `2` is filtered and then mapped before element `3` is examined.
3. `findFirst()` stops immediately once it finds the first valid element. Elements `3`, `4`, and `5` do not need to be processed.

This is often called **fused per-element processing (pipeline fusion)**. However, do not conclude that every pipeline operates independently element by element: `sorted` may need to buffer many elements before emitting the first one.

### 5.1. A terminal operation can also skip traversal via optimization

The following snippet must not be relied upon to expect `peek` to always print all three lines:

```java
long count = List.of("A", "B", "C").stream()
    .peek(System.out::println)
    .count(); // 3
```

With a source of known size and steps that do not change the element count, the Stream implementation can compute `count()` **without traversing the elements**, so the `peek` action may not execute. Similarly, optimizations and short-circuiting can prevent side effects inside lambdas from running as intuition might expect.

**Rule:** lambdas used in `filter`, `map`, and `peek` should not carry essential side effects. Use output data or an appropriate terminal operation to express business requirements.

## 6. Complete example: processing orders

Problem: given a list of orders with customer, category, and amount. Keep only orders with a positive amount, then compute **revenue by category**. The example uses Java 17+ (`record` and `List.of`); save it in `OrderPipelineDemo.java` to run.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderPipelineDemo {
    record Order(String customer, String category, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("An",   "Books",       120_000),
            new Order("Bình", "Books",        80_000),
            new Order("An",   "Accessories", 200_000),
            new Order("Chi",  "Books",       -10_000),
            new Order("Dung", "Accessories", 150_000)
        );

        Map<String, Long> revenueByCategory = orders.stream()
            .filter(order -> order.amount() > 0)
            .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                Collectors.summingLong(Order::amount)
            ));

        System.out.println(revenueByCategory);
        // {Accessories=350000, Books=200000}
    }
}
```

Step-by-step breakdown:

| Component | Code | Role |
| --- | --- | --- |
| Source | `orders.stream()` | Supplies `Order` objects. |
| Intermediate | `filter(order -> order.amount() > 0)` | Drops invalid orders per the example rule. |
| Terminal | `collect(...)` | Traverses required data and accumulates into a `Map`. |
| Collector | `groupingBy(Order::category, ...)` | Splits groups by category name. |
| Downstream collector | `summingLong(Order::amount)` | Sums the amounts of orders in each group. |
| Result container | `TreeMap::new` | Creates a map with natural key ordering for readable output. |

If you need a list of high-value customers, create **an independent pipeline** over the same collection:

```java
List<String> highValueCustomers = orders.stream()
    .filter(order -> order.amount() >= 150_000)
    .map(Order::customer)
    .distinct()
    .toList(); // [An, Dung]
```

The same `orders` source can open multiple new Streams. What is forbidden is reusing **the same `Stream` object after a terminal operation has been executed on it**.

## 7. Lifecycle and the single-use rule

A Stream object is designed to be consumed **once**. The following example is invalid:

```java
Stream<String> names = Stream.of("An", "Bình", "Chi");
long count = names.count();
List<String> result = names.toList(); // IllegalStateException
```

After `count()`, `names` has already been consumed. Some attempts to reuse an intermediate pipeline can also be caught earlier; therefore, do not hold onto branches and try to reuse an intermediate Stream repeatedly.

The right approach is to create a new Stream from a re-traversable source:

```java
List<String> names = List.of("An", "Bình", "Chi");

long count = names.stream().count();
List<String> result = names.stream()
    .filter(name -> name.length() > 2)
    .toList();
```

If you want to describe a reusable pipeline factory, you can write a function that creates a new Stream:

```java
Supplier<Stream<String>> nonBlankNames = () -> names.stream()
    .filter(name -> !name.isBlank());

long n = nonBlankNames.get().count();
List<String> clean = nonBlankNames.get().toList();
```

The last snippet requires `import java.util.function.Supplier;` and `import java.util.stream.Stream;`. Each call to `get()` creates a new Stream object over the collection. This approach **does not automatically make a single-read source (such as an open I/O stream) re-readable**.

## 8. Limitations and common design mistakes

### 8.1. Do not modify the source being traversed

`Stream` generally requires **non-interference**: do not interfere with the data source while the pipeline is running, except for sources designed for concurrent access. The following example risks causing `ConcurrentModificationException` or unpredictable results:

```java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

names.stream().forEach(name -> {
    if (name.equals("An")) {
        names.add("Chi"); // Wrong: modifying the source list during traversal
    }
});
```

Instead of directly mutating the collection being traversed, create a result collection or use an appropriate collection operation, such as `removeIf` when the goal is to conditionally remove elements without needing a Stream.

### 8.2. Avoid shared mutable state across lambdas

Do not use an external list as an accumulator variable inside a pipeline:

```java
List<String> output = new ArrayList<>();
names.parallelStream()
    .filter(name -> !name.isBlank())
    .forEach(output::add); // Not safe with ArrayList in a parallel stream
```

Use a terminal operation designed for accumulation:

```java
List<String> output = names.parallelStream()
    .filter(name -> !name.isBlank())
    .toList();
```

Side effects such as logging, modifying counters, or updating external objects can be affected by optimizations, ordering, and multiple threads. `forEach` is intended to perform an action, yet **does not guarantee encounter order when running in parallel**; if order during traversal is required, consider `forEachOrdered` along with its associated synchronization cost.

### 8.3. Mind the encounter order

`List` typically provides an ordered Stream; `HashSet` does not commit to a stable traversal order under its API contract. `findFirst()` means "first" in **encounter order** if the Stream is ordered. `findAny()` makes no guarantee to pick the first element.

`sorted()` establishes a sorted order for the result, at a cost; if the problem only requires checking whether a matching element exists, `anyMatch` usually expresses the intent more clearly and can short-circuit.

### 8.4. Do not assume parallel is faster by default

`parallelStream()` or `stream().parallel()` can distribute work across multiple threads, but splitting/merging, ordering, synchronization, and data size all affect performance. Small datasets, lightweight operations, many stateful operations, or blocking I/O rarely benefit noticeably.

Example:

```java
long count = orders.parallelStream()
    .filter(order -> order.amount() > 0)
    .count();
```

The pipeline structure looks identical to the sequential version, but lambdas must be suitable for parallel execution: **do not rely on shared state variables, and do not assume a processing order**. Choosing parallelism should be based on measuring under realistic workloads.

### 8.5. Stream is not always more optimal than a loop

Stream helps communicate data transformations and compose multiple processing steps. However, when an algorithm needs complex control flow, updates multiple interdependent state variables, or has very specific performance requirements, a traditional loop is sometimes easier to understand and optimize. Avoid creating unnecessary intermediate lists; a single pipeline usually expresses the work better than chaining conversions through temporary collections.

## 9. Choosing the right operation for the goal

| Goal | Suitable expression |
| --- | --- |
| Keep valid orders | `filter(order -> order.amount() > 0)` |
| Extract customer names from orders | `map(Order::customer)` |
| Flatten skill lists | `flatMap(List::stream)` |
| Take at most 10 items | `limit(10)` |
| Check whether any order exceeds a threshold | `anyMatch(order -> order.amount() > threshold)` |
| Count orders matching a condition | `filter(...).count()` |
| Calculate total amount | `mapToLong(Order::amount).sum()` |
| Group orders by category | `collect(Collectors.groupingBy(Order::category))` |
| Collect result list | `toList()` or `collect(...)` |
| Read file lines | `try (Stream<String> lines = Files.lines(path)) { ... }` |

A maintainable pipeline typically answers the following questions:

1. **Where is the source?** Is the data finite or infinite, ordered or unordered, and are there resources to close?
2. **What does each intermediate step do?** Does it change element types or element counts? Is there state or sorting cost?
3. **What is the final result needed?** A list, a map, a number, a single element, or just a condition check?
4. **Can it short-circuit?** If you only need to know whether an item exists, do not collect the entire list.
5. **Are there side effects or concurrency risks?** Lambdas should be independent and must not modify the source.
6. **Have you used the Stream strictly once and closed resources if needed?**

## 10. Core takeaways

- **The source** generates or supplies elements; a Stream represents the traversal and processing pipeline, not a place to store elements.
- **Intermediate operations** build the processing chain and are usually lazy; some steps like `sorted` and `distinct` must maintain state.
- **Terminal operations** evaluate the pipeline as needed, and may traverse everything, short-circuit, or apply optimizations that skip reading every element.
- **A Stream object can be consumed only once**; to compute multiple independent results, create a new Stream from an appropriate source.
- **Pipeline correctness** depends on processing order, the non-interference rule, avoiding side effects, and managing resources.
- **`filter` / `map` / `reduce` / `collect`** form the core backbone; grouping, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers all build on understanding this model.
