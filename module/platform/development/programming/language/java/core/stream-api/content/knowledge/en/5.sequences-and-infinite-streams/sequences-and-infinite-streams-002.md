# Creating Sources with `Stream.generate` and `Supplier`

When processing data with the Java Stream API, elements are not always already sitting in a `List`, array, or file. Sometimes a program needs to **generate values when the pipeline requests them**: generating sample data, obtaining a random number, issuing identifiers, or creating simulated events. `Stream.generate` combined with `Supplier` lets you describe this type of source with a lazy pipeline.

This lesson belongs to the **Sequences and Infinite Streams** chapter of the **JAVA_STREAM_API** module. The goal is to understand how `Supplier` provides elements, why `Stream.generate` is an unbounded source, how to limit the number of elements before using `filter`, `map`, `reduce`, or `collect`, and the risks regarding ordering, state, resources, and performance. The main examples use Java 17 or later; the foundational `Stream.generate` and `Supplier` concepts have been available since Java 8.

## 1. What Is `Supplier<T>`?

`Supplier<T>` is a functional interface in `java.util.function`. Its core contract has **one abstract method**:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

`get()` **takes no parameters** and **returns a value** of type `T`. The value can be a constant, the result of a computation, an API call result, or a new object. Whether a new value is created on each call depends entirely on how `Supplier` is implemented.

```java
import java.util.UUID;
import java.util.function.Supplier;

Supplier<String> fixed = () -> "Java";
Supplier<UUID> newId = UUID::randomUUID;

System.out.println(fixed.get()); // Java
System.out.println(newId.get()); // A UUID generated when get() runs
```

Two common ways to write it are a lambda `() -> expression` and a method reference `SomeClass::staticMethod` or `object::instanceMethod`.

Notes:

- `Supplier` has no argument to receive the **previous element**. If you need to describe a sequence following the rule "the next element depends on the previous element", `Stream.iterate` is usually more suitable.
- There is no requirement that `get()` always returns a different result. `() -> 5` can return `5` forever.
- `Supplier` can hold internal state or reference external state; such usage requires special caution when the stream runs in parallel.
- `Supplier.get()` can return `null`; by itself, that is **not** a signal to terminate the stream.

## 2. Syntax and Contract of `Stream.generate`

In `java.util.stream.Stream`, the method has the signature:

```java
public static <T> Stream<T> generate(Supplier<? extends T> s)
```

`Stream.generate(supplier)` creates a stream that is **sequential, has no defined encounter order, and is unbounded in the number of elements**. Each time an element is needed, the source calls `supplier.get()` to produce a value.

```java
import java.util.List;
import java.util.stream.Stream;

List<String> words = Stream.generate(() -> "Java")
        .limit(4)
        .toList();

System.out.println(words); // [Java, Java, Java, Java]
```

In this example:

1. `Stream.generate(() -> "Java")` builds a source capable of continuously generating elements.
2. `limit(4)` caps the pipeline at a maximum of four elements.
3. `toList()` is the terminal operation that requests data and produces the resulting list.

`Stream.generate` **does not pre-build an infinite list** in memory. It supplies elements on demand as requested by the pipeline. However, laziness does not automatically protect the program: if a terminal operation demands consuming all elements from an unbounded source, the program may run forever or exhaust resources.

### 2.1. Demonstrating Laziness

```java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.generate(() -> {
    System.out.println("Supplier.get()");
    return 7;
});

System.out.println("Stream created");
// Up to here, there is no "Supplier.get()" line yet.

numbers.limit(2).forEach(System.out::println);
// When the terminal operation runs:
// Supplier.get()
// 7
// Supplier.get()
// 7
```

The lambda creating the `Supplier` is passed into `generate`, but **the lambda body is only invoked when an element is needed**. The print order in the example illustrates a **sequential** pipeline. When using `parallel()` or operations that can be optimized, do not treat the invocation count or order of the lambda as a business contract.

### 2.2. Characteristics to Distinguish

| Characteristic | `Stream.generate(supplier)` |
|---|---|
| Element type | `T`, provided by `Supplier<? extends T>` |
| Source size | Unbounded; does not terminate on its own |
| Initial mode | Sequential (`sequential`) |
| Encounter order | **No guaranteed order** (`unordered`) |
| When values are produced | When the pipeline requests them, via `supplier.get()` |
| Generating sequences based on previous element | No mechanism to pass the previous element into `get()` |
| Resource release | Does not automatically close resources that the supplier itself opens or uses |

A source created sequentially **does not mean** a source with an encounter order. Even if the current run observes values in a familiar sequence, order-dependent operations should not rely on that when using `generate`.

## 3. Combining with `limit` to Turn an Infinite Source into a Finite Task

In most situations where a finite result set is needed, the safest and clearest usage is to place a limit early in the pipeline.

```java
import java.util.UUID;
import java.util.stream.Stream;

List<String> ids = Stream.generate(UUID::randomUUID)
        .limit(5)
        .map(UUID::toString)
        .toList();

System.out.println(ids); // List of 5 UUIDs as strings
```

`UUID::randomUUID` is the value supplier; `limit(5)` determines the number of elements passed to subsequent operations. UUIDs have an extremely small collision probability in practice, but this is not a mathematical guarantee that every generation is unique.

### 3.1. Generating Random Numbers in a Range

```java
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.Stream;

List<Integer> rolls = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(1, 7)
).limit(8).toList();

System.out.println(rolls); // 8 integers, each from 1 to 6
```

`nextInt(1, 7)` has an **inclusive** lower bound of `1` and an **exclusive** upper bound of `7`. `ThreadLocalRandom.current()` is suitable when generating random numbers in tasks that may run across multiple threads, though the results are not designed to be identically reproducible across runs.

When reproducible test data is needed, use a generator with an explicit seed and control sequential execution mode, or prepare a fixed test dataset beforehand.

### 3.2. Applying `map`, `filter`, `reduce`, and `collect`

```java
int total = Stream.generate(() -> 3)
        .limit(4)
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 24
```

Similarly, you can group or collect finite results:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, Long> frequency = Stream.generate(() -> 2)
        .limit(5)
        .collect(Collectors.groupingBy(
                n -> n,
                Collectors.counting()
        ));

System.out.println(frequency); // {2=5}
```

Crucial condition: you must know **whether the terminal operation can complete**. A pipeline starting from an unbounded source can still terminate if an appropriate `limit` is placed before operations that require the entire input.

### 3.3. The Placement of `limit` Changes the Result

```java
List<Integer> a = Stream.generate(() -> 5)
        .limit(3)
        .map(n -> n * 10)
        .toList();
// [50, 50, 50]
```

With `filter`, the order of `limit` and `filter` matters:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger aCounter = new AtomicInteger();
List<Integer> firstFiveThenEven = Stream.generate(aCounter::getAndIncrement)
        .limit(5)
        .filter(n -> n % 2 == 0)
        .toList();
// Sequential pipeline: [0, 2, 4]

AtomicInteger bCounter = new AtomicInteger();
List<Integer> firstThreeEven = Stream.generate(bCounter::getAndIncrement)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// Sequential pipeline: [0, 2, 4]
```

These two examples are intentionally written to illustrate how different data-processing steps work, **not** to recommend using a counter as an ordered source: `generate` remains an `unordered` source. In the first case, only the first five generated values are examined and then filtered; in the second case, the pipeline keeps requesting values until it receives three even elements. With a different predicate or a different limit, the count and content of the results can differ significantly.

If `filter` never lets an element through, `filter(...).limit(3)` will not terminate. Placing `limit` **before** `filter` caps the number of source elements examined, at the trade-off that the filtered result may have fewer than three elements.

## 4. Non-Terminating Pipelines and How to Fix Them

Because `generate` has no natural termination point, some short-looking code snippets can run infinitely.

### 4.1. Terminal Operations Requiring the Entire Source

```java
// Does not terminate: can never finish counting an infinite source.
// long count = Stream.generate(() -> 1).count();

// Has an explicit limit, so it completes.
long count = Stream.generate(() -> 1)
        .limit(100)
        .count();
System.out.println(count); // 100
```

Similarly, `collect(Collectors.toList())`, `toList()`, `reduce`, or `sum` on an entire unbounded source cannot complete under normal conditions. With `toList()`, the program can also continuously increase memory usage.

### 4.2. `sorted` and `distinct` Before `limit`

```java
// Does not terminate: sorted() needs to know the entire input to sort.
// Stream.generate(() -> 5).sorted().limit(10).toList();

// Completes: only sorts 10 elements.
List<Integer> sortedSample = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(100)
).limit(10).sorted().toList();
```

`distinct()` before `limit` can also fail to terminate if the source never produces enough distinct values:

```java
// Does not terminate: the source only has one distinct value.
// Stream.generate(() -> "A").distinct().limit(2).toList();

// Completes: only processes ten values from the source.
List<String> distinct = Stream.generate(() -> "A")
        .limit(10)
        .distinct()
        .toList();
System.out.println(distinct); // [A]
```

Keep two distinct goals in mind:

- **Select enough N elements matching a condition**: may read for a very long time or infinitely if the condition is rare or impossible.
- **Examine at most N source elements**: place `limit(N)` before the filtering/deduplication step; the resulting element count may be less than N.

### 4.3. `takeWhile` Is Not an Arbitrary Substitute for a Stopping Mechanism in `generate`

`takeWhile` was added in Java 9. For **ordered streams**, it takes the contiguous prefix satisfying the predicate. However, `Stream.generate` creates an **unordered** stream, so `takeWhile` does not have a contract to "stop cleanly at the first non-matching element" like an ordered sequence.

Therefore, avoid relying on `Stream.generate(supplier).takeWhile(...)` to decode a protocol that must stop at the first sentinel, especially when using `parallel()`. When you need an ordered sequence with a specific continuation condition, consider `Stream.iterate(seed, hasNext, next)` (Java 9+) or building an appropriate `Spliterator`. When reading data from files, use dedicated source APIs like `BufferedReader.lines()` or `Files.lines()` and manage resource closing.

## 5. Stateful `Supplier`: Examples and Limitations

A `Supplier` can remember how many times it has been called, which helps illustrate the element-supplying mechanism:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

AtomicInteger counter = new AtomicInteger();
Supplier<Integer> next = counter::getAndIncrement;

List<Integer> numbers = Stream.generate(next)
        .limit(5)
        .toList();

System.out.println(numbers); // For a sequential example: [0, 1, 2, 3, 4]
```

Although `AtomicInteger` guarantees that each increment operation is atomic, **it does not give `Stream.generate` an encounter order**. When switching to `parallel()`, threads may call `get()` and complete out of order; you must not assume the result will always be `[0, 1, 2, 3, 4]`.

```java
// Do not use if a deterministic ordered sequence is needed:
// Stream.generate(counter::getAndIncrement)
//       .parallel().limit(5).toList();

// Ordered consecutive sequence: describe using iterate or range.
List<Integer> ordered = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();
System.out.println(ordered); // [0, 1, 2, 3, 4]
```

`AtomicInteger` prevents lost increments, but does not solve all ordering or semantic requirements of an element-generating source. With large `int` values, a continuously increasing sequence can also overflow; an explicit bound and an appropriate data type are required.

### 5.1. Avoid Arbitrary Shared Mutable State in `parallel()`

```java
int[] holder = {0};

// Unsafe when running in parallel: updating holder[0] has a data race.
// Stream.generate(() -> holder[0]++).parallel().limit(100).toList();
```

Even when using thread-safe structures, code can still be difficult to control regarding ordering and generation count when a pipeline branches or short-circuits. To leverage parallel processing, prefer a `Supplier` that does not depend on shared state, for example:

```java
List<Integer> randomValues = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(1, 101)
).parallel().limit(20).toList();

System.out.println(randomValues.size()); // 20
```

Do not assume `parallel()` is faster: task allocation, synchronization, result collection, and data size can make the code slower. If order and reproducibility are business requirements, choose a source with an encounter order, avoid shared state, and benchmark performance with representative data.

## 6. Comparison with Other Sequence Sources

Not every "function-based data generation" case should use `Stream.generate`.

| Source | Size | Has encounter order? | Where does the next value come from? | When to use |
|---|---|---|---|---|
| `Stream.generate(supplier)` | Unbounded | No | Calls `supplier.get()` | Generating samples, UUIDs, random values |
| `Stream.iterate(seed, next)` | Unbounded unless limited | Yes | Applies `next` to previous value | Recurrence sequences, powers, step-by-step progression |
| `Stream.iterate(seed, hasNext, next)` | Can be finite | Yes | Stops when `hasNext` is false | Sequential series with a stopping condition |
| `IntStream.range(start, end)` | Finite | Yes | Consecutive increasing integers | Indices, integer ranges |
| `Stream.of(values...)` | Finite | Yes | Pre-existing values | Small set of constants or objects |

Examples illustrating the differences:

```java
// Issue a new ID each time requested (no logical order guaranteed).
List<UUID> ids = Stream.generate(UUID::randomUUID)
        .limit(3)
        .toList();

// Sequence depending on previous value: 1, 2, 4, 8, 16.
List<Integer> powersOfTwo = Stream.iterate(1, n -> n * 2)
        .limit(5)
        .toList();
System.out.println(powersOfTwo); // [1, 2, 4, 8, 16]

// Finite range, preserving order: 0, 1, 2, 3, 4.
int[] indexes = java.util.stream.IntStream.range(0, 5).toArray();
```

The two `Stream.iterate` overloads are not the same: `iterate(seed, next)` (Java 8) is an unbounded source; `iterate(seed, hasNext, next)` (Java 9+) has a condition to terminate. When a specific numeric sequence is needed, `IntStream.range` and `IntStream.iterate` also avoid boxing to `Integer`.

## 7. Combining with Short-Circuiting Terminal Operations

An infinite source **can** be consumed by a short-circuiting terminal operation, but you must check whether the condition will actually find a match.

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> sample = Stream.generate(() -> 42).findAny();
System.out.println(sample.orElseThrow()); // 42

boolean found = Stream.generate(() -> 42)
        .anyMatch(n -> n > 40);
System.out.println(found); // true
```

`findAny()` can complete as soon as it finds an element and has no requirement to pick the "first" one. Conversely:

```java
// Does not terminate: no element satisfies the condition.
// boolean found = Stream.generate(() -> 42).anyMatch(n -> n < 0);
```

With an infinite source, `allMatch`, `noneMatch`, `anyMatch`, `findAny`, or `findFirst` only have a chance to complete when the short-circuit contract allows stopping on actual data. `findFirst()` on a `generate` source does not mean "the first value of an ordered sequence", since the source has no encounter order.

## 8. `null` Values, Errors, and Resources

### 8.1. `null` Is Still an Element

```java
List<String> values = Stream.generate(() -> (String) null)
        .limit(2)
        .toList();

System.out.println(values); // [null, null]
```

`Supplier.get()` returning `null` does not make the source terminate. If the pipeline does not accept `null`, handle it explicitly with `filter(Objects::nonNull)` or design the source to produce non-null values. Be careful: `filter(Objects::nonNull).limit(3)` will not terminate if the supplier always returns null.

Some terminal operations like `findFirst()` or `findAny()` may throw `NullPointerException` if the selected element is `null`. Do not confuse `Stream.generate(() -> null)` with `Stream.empty()` or `Stream.ofNullable(null)`.

### 8.2. Exceptions in the Supplier

If `get()` throws an unchecked exception, the error occurs when the terminal operation demands the corresponding element:

```java
Stream<Integer> source = Stream.generate(() -> {
    throw new IllegalStateException("Cannot supply value");
});

// IllegalStateException only occurs at the consumption step:
// source.limit(1).toList();
```

`Supplier.get()` does not declare checked exceptions in its signature. When I/O operations or a source with a terminal state are needed, use dedicated stream/spliterator APIs instead of stuffing all reading and error handling into a lambda.

### 8.3. Stream Lifecycle and Resource Closing

```java
Stream<String> stream = Stream.generate(() -> "x");
System.out.println(stream.limit(3).count()); // 3

// Cannot reuse the same stream object after a terminal operation:
// stream.findAny(); // IllegalStateException
```

`Stream.generate` itself does not open files or connections. However, if a supplier accesses external resources, `Stream.close()` **does not automatically close those resources** unless you design proper closing behavior (for example, registering `onClose` and calling `close`, usually via `try-with-resources`). For files, prefer library-provided sources and resource-closing APIs.

## 9. Complete Runnable Example (Java 17+)

The following program combines three scenarios: a lazy source with `Supplier`, finite random sampling, and generating an ordered sequence with `iterate`.

```java
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class GenerateAndSupplierDemo {
    public static void main(String[] args) {
        // 1. Supplier is only called when the pipeline needs an element.
        AtomicInteger calls = new AtomicInteger();
        Supplier<Integer> nextNumber = calls::incrementAndGet;

        Stream<Integer> lazySource = Stream.generate(nextNumber);
        System.out.println(calls.get()); // 0

        List<Integer> samples = lazySource.limit(3).toList();
        System.out.println(samples);     // Sequential run: [1, 2, 3]
        System.out.println(calls.get()); // 3 in this sequential pipeline

        // 2. A data-generating source can be bounded with limit.
        List<Integer> dice = Stream.generate(
                () -> ThreadLocalRandom.current().nextInt(1, 7)
        ).limit(5).toList();
        System.out.println(dice);        // 5 numbers, each in [1, 6]

        // 3. Generate UUIDs, represented as strings.
        List<String> tokens = Stream.generate(UUID::randomUUID)
                .limit(3)
                .map(UUID::toString)
                .toList();
        System.out.println(tokens);      // List of 3 UUID strings

        // 4. Sequence needing deterministic order: use iterate.
        List<Integer> ordered = Stream.iterate(0, n -> n + 1)
                .limit(5)
                .toList();
        System.out.println(ordered);     // [0, 1, 2, 3, 4]
    }
}
```

In production code, if you only need N consecutive numbers, use `IntStream.range(0, N)` instead of a supplier with a counter. If you need N values generated on demand without ordering constraints, `Stream.generate(...).limit(N)` is a readable choice.

## 10. Common Errors and How to Fix Them

| Error or misconception | What can happen? | How to handle |
|---|---|---|
| `Stream.generate(...).toList()` without a limit | Runs forever, increases memory usage | Place a finite `limit` before the terminal operation |
| `sorted().limit(N)` on an infinite source | `sorted` cannot finish waiting for all input | Place `limit(N)` before `sorted` |
| `distinct().limit(N)` with a supplier repeating very few values | Not enough N distinct values to stop | Limit input samples or design a finite stopping condition |
| `filter(...).limit(N)` when predicate is always false | Pipeline does not terminate | `limit` before `filter`, or change the sample count requirement |
| Using a counting supplier and relying on parallel result order | `generate` is an unordered source | Use `iterate`, `IntStream.range`, or another ORDERED source |
| Sharing an `int` counter in a parallel lambda | Data race, lost updates | Avoid shared mutable state; control synchronization when truly needed |
| Assuming a supplier returning `null` stops the stream | `null` continues as an element | Design a separate stopping mechanism or use a source supporting termination |
| Reusing a stream object after `count()` | `IllegalStateException` | Create a new stream for another pipeline |
| Using `parallel()` on a very small set assuming it is faster | Coordination overhead may outweigh benefits | Only use parallelism after benchmarking performance |

## 11. Self-Check Questions

1. **What does `Stream.generate(() -> "A").limit(4).count()` return?** Returns `4`, because `limit` restricts the source to four elements.
2. **Does `Stream.generate(() -> 5)` terminate automatically after one element?** No. It can generate infinitely many elements with the same value `5`.
3. **Does `Stream.generate(() -> 2).distinct().limit(3).toList()` complete?** Not under normal circumstances, because the source only produces one distinct value.
4. **Does `generate` have an encounter order because it starts sequentially?** No. It is an `unordered` source; sequential execution mode does not automatically create an order guarantee.
5. **Does `Stream.generate(() -> 1).limit(5).sorted().toList()` complete?** Yes; `sorted` only receives five elements. Changing it to `sorted().limit(5)` cannot finish sorting an infinite source.
6. **To get the ordered sequence `1, 2, 4, 8`, what should be used?** `Stream.iterate(1, n -> n * 2).limit(4)`.
7. **Does a Supplier returning `null` automatically terminate the stream?** No. If you want to discard null, you can filter, but you must ensure the pipeline can terminate.
8. **Why should you avoid using a regular counter variable in a Supplier when calling `parallel()`?** Because threads can update the same state causing a data race, and a `generate` source does not guarantee encounter order.

**Key takeaway:** `Supplier<T>` returns a value when `get()` is called; `Stream.generate(supplier)` uses it as a lazy, initially sequential, unordered source with no natural termination point. To process a finite quantity, choose the limit and `limit` placement deliberately. When you need an ordered sequence or a deterministic recurrence rule, choose a source like `Stream.iterate` or `IntStream.range` that fits the problem.
