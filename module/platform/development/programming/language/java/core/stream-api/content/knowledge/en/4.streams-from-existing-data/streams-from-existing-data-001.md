# Creating a Stream from a Collection with stream() and parallelStream()

When data is already in a `Collection`, the Java Stream API provides two direct ways to build a pipeline: `collection.stream()` and `collection.parallelStream()`. Both allow processing data in a declarative style with `filter`, `map`, `reduce`, `collect`, and many other operations. The main difference is **sequential or potentially parallel execution mode** when the pipeline is consumed.

This lesson belongs to the **Streams from Existing Data** chapter of the **JAVA_STREAM_API** module. Understanding how to create a Stream from a Collection is foundational before approaching grouping, custom collectors, `Spliterator`, parallel processing, and advanced operations such as Stream Gatherers. In particular, it is necessary to distinguish **data source**, **execution time**, **result ordering**, **safety in parallel processing**, and **performance overhead**.

## 1. Two Built-in Methods on Collection

Since Java 8, the `java.util.Collection<E>` interface provides the methods:

```java
Stream<E> stream();
Stream<E> parallelStream();
```

By API contract, `stream()` returns a **sequential Stream**, while `parallelStream()` returns a **potentially parallel Stream**. The actual manner and degree of parallelism depend on the source, operations, execution environment, and data splitting capability.

`Collection` implementation classes such as `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, and `TreeSet` normally have access to both methods via the `Collection` interface:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi");
Stream<String> sequential = names.stream();
Stream<String> parallel = names.parallelStream();
```

Here, `Stream<String>` is a **stream describing the processing of elements**, not a new list. The two calls create **two separate Streams** from the same Collection; they do not convert or delete data from `names`.

| Existing source | How to create Stream | Notes |
| --- | --- | --- |
| `List<String>`, `ArrayList<String>` | `list.stream()` or `list.parallelStream()` | Regular Lists have a defined element order. |
| `Set<String>`, `HashSet<String>` | `set.stream()` or `set.parallelStream()` | HashSet does not guarantee traversal order. |
| `LinkedHashSet<String>` | `set.stream()` | Preserves insertion order when traversing elements. |
| `TreeSet<String>` | `set.stream()` | Traverses in the Set's sorted order. |
| `Map<K, V>` | `map.entrySet().stream()`, `map.keySet().stream()`, `map.values().stream()` | `Map` is **not** a `Collection`; create a Stream from the appropriate collection view. |
| Array `String[]` | `Arrays.stream(array)` | An array is not a Collection, so you cannot call `array.stream()` directly. |

Each Stream has the **element type** of its corresponding source. From `Map.entrySet()`, the element is `Map.Entry<K, V>`; from `Map.values()`, the element is `V`. This type determines what transformations can be written in subsequent steps.

## 2. Runnable Example: From List to Result

The following complete example is compatible with Java 8 and later:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class CollectionStreamDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList(
            "An", "Binh", " Chi ", "Dung", "Minh", "  "
        );

        List<String> normalized = names.stream()
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .map(name -> name.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(normalized);
        // [BINH, CHI, DUNG, MINH]

        long count = names.parallelStream()
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .count();

        System.out.println(count);
        // 4
    }
}
```

The pipeline is read from left to right:

1. `names.stream()` takes `List<String>` as the source and creates a sequential Stream.
2. `map(String::trim)` describes removing leading and trailing whitespace from each name.
3. `filter(...)` keeps names that have at least three characters after normalization.
4. `map(...toUpperCase...)` describes the transformation to uppercase.
5. `collect(Collectors.toList())` consumes the remaining elements and creates the result as a `List`.

The second pipeline creates its source using `parallelStream()`; the `count` value is still `4` because both pipelines apply the same filtering rule. With small data like this example, parallel processing usually has no advantage and may incur coordination overhead.

> The two calls `stream()` and `parallelStream()` do not require copying the Collection. `collect(...)` is the step that creates the resulting data structure. This "view of a computation" nature helps avoid temporary lists after each intermediate step.

## 3. Streams Are Lazy: Creating a Pipeline Does Not Traverse Data Yet

`filter` and `map` are *intermediate operations*. They usually only append rules to the pipeline; a *terminal operation* such as `count`, `collect`, or `findFirst` is what triggers data processing.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
    .filter(n -> {
        System.out.println("Filtering: " + n);
        return n % 2 == 0;
    });

System.out.println("Pipeline created");
long result = pipeline.count();
System.out.println("Even elements count: " + result);
```

In this sequential pipeline, `Pipeline created` appears before the filtering executions occur. `count()` needs to determine the number of elements after `filter`, so the pipeline evaluates the filter for the numbers in the list.

**A Stream can only be consumed once.** After `pipeline.count()`, you must not call `pipeline.collect(...)` on the same `pipeline` object. To process the Collection again, create a new Stream:

```java
long evenCount = numbers.stream().filter(n -> n % 2 == 0).count();
int evenSum = numbers.stream()
    .filter(n -> n % 2 == 0)
    .mapToInt(Integer::intValue)
    .sum();
// evenCount = 2; evenSum = 6
```

Do not treat side effects in `peek`, `map`, or intermediate steps as operations guaranteed to run exactly once per element. Some terminal operations can short-circuit or skip unnecessary operations during optimization, such as `count()` on a source with a known size.

## 4. What Differs Between stream() and parallelStream()?

| Aspect | `collection.stream()` | `collection.parallelStream()` |
| --- | --- | --- |
| Initial mode | Sequential | Potentially parallel |
| Typical execution | Elements are processed along a sequential path | Work can be split into multiple parts and executed concurrently |
| **Lambda execution** order | Easier to observe with ordered sources and stateless steps | Not guaranteed to follow source order |
| **Result** order | Follows source and terminal contracts | Can still preserve encounter order via appropriate terminal operations |
| Overhead | Low coordination, usually suitable for small sets | Has overhead for splitting work, merging results, and synchronization if needed |
| Risk when lambda mutates shared state | Can cause logic bugs | Adds risk of race conditions, missing or unstable results |

Java uses source information via `Spliterator` to traverse and, when appropriate, split elements into parts that can be processed independently. `parallelStream()` **does not mean** every element will be processed on a separate thread, nor does it promise a fixed number of threads.

You can check and switch the mode of an **unconsumed** pipeline:

```java
Stream<Integer> a = numbers.stream();
System.out.println(a.isParallel()); // false

Stream<Integer> b = numbers.parallelStream();
System.out.println(b.isParallel()); // true for common Collections

long total = numbers.stream()
    .parallel()
    .mapToLong(Integer::longValue)
    .sum();

long sequentialTotal = numbers.parallelStream()
    .sequential()
    .mapToLong(Integer::longValue)
    .sum();
```

`parallel()` and `sequential()` are mode configuration operations for the pipeline; they **do not start processing on their own**. On common Collections such as `ArrayList`, `parallelStream()` returns a Stream marked as parallel; the `Collection` API only commits to a Stream that *can* be parallel, so avoid treating this as a guarantee of CPU utilization.

## 5. Data Order and Execution Order Are Two Separate Concepts

**Encounter order** is the order in which elements are supplied to the Stream by the source, if the source has an order. For example, `List` usually provides index order, `LinkedHashSet` insertion order, `TreeSet` sort order; `HashSet` does not guarantee order.

From an ordered `List`, a parallel transformation can still produce an **ordered result**:

```java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> squared = source.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(squared); // [1, 4, 9, 16, 25, 36]
```

This **does not prove** that the lambda `n -> n * n` ran in the order `1, 2, 3, 4, 5, 6`. An appropriate collector combines results according to the source's encounter order.

Compare these two terminal operations:

```java
source.parallelStream().forEach(System.out::println);
// Print order may vary between runs.

source.parallelStream().forEachOrdered(System.out::println);
// For an ordered List: prints 1, 2, 3, 4, 5, 6.
```

`forEachOrdered` preserves the observable order but may make processing more expensive. `findFirst()` prioritizes the first element in encounter order; `findAny()` can pick any element, especially when running in parallel. Do not impose the notion of "first" by insertion order onto a `HashSet`.

For sources without an encounter order, a terminal operation cannot create a source ordering guarantee that does not exist. If you require results sorted by custom criteria, use `sorted(...)` and be aware of the sorting cost.

## 6. Do Not Use Shared State to Accumulate Parallel Results

A typical mistake is using `forEach` to add elements directly into an external `ArrayList`:

```java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> unsafe = new ArrayList<>();
source.parallelStream().forEach(n -> unsafe.add(n * n)); // Wrong!
```

`ArrayList` is not safe for multiple threads adding elements concurrently. Results may be missing, incorrect, or throw errors; sometimes running correctly is just coincidence. Replace it with a collection operation that has a clear contract:

```java
List<Integer> safe = source.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

The collector is coordinated by the library with work splitting and result combining mechanisms when running in parallel. **No** shared target variable is needed inside the lambda. This approach also works with sequential Streams.

Similarly, to compute a total count or sum, use an appropriate reduction operation:

```java
long sum = source.parallelStream()
    .mapToLong(Integer::longValue)
    .sum(); // 21
```

If you manually use `reduce(identity, accumulator, combiner)` on a parallel Stream, the combining operations must satisfy **associativity**, a neutral identity, and the compatibility requirements of the `reduce` contract. For order-dependent operations such as subtraction, you cannot arbitrarily group partial totals and subtract them expecting the same result as a sequential loop.

A grouping example, a common task in this module:

```java
Map<Integer, Long> countByLength = Arrays.asList("An", "Binh", "Chi", "Dung")
    .parallelStream()
    .collect(Collectors.groupingBy(String::length, Collectors.counting()));

// There is 1 name of length 2, 1 name of length 3, and 2 names of length 4.
// Do not rely on the iteration order of keys in the resulting Map.
```

`groupingBy` can still be used in a parallel pipeline thanks to the Collector's accumulation and combining mechanism; not using `ConcurrentHashMap` in this example does not mean the collection suffers from a race condition. For concurrent grouping without ordering requirements, `groupingByConcurrent` has its own contract to consider.

## 7. Collection, Spliterator, and Splitting Overhead

`Collection.stream()` and `Collection.parallelStream()` use the Collection's `Spliterator` to support data traversal. `Spliterator` can report source characteristics, such as:

- `ORDERED`: the source has an encounter order.
- `SIZED`: the size of the data portion being represented is known.
- `DISTINCT`: elements are distinct according to the source's contract.
- `SORTED`: elements follow a defined sort order.

The characteristics provided vary depending on the Collection and how the source is constructed. They help the Stream choose or optimize processing operations; for example, `count()` can obtain the size directly when it is certain no step changes the element count.

The effectiveness of `parallelStream()` depends significantly on data splitting capability: `ArrayList` is usually easy to partition by index, whereas linked structures such as `LinkedList` have different splitting and access characteristics. This is why the same pipeline can have very different performance on different Collections.

However, **a large element count does not necessarily mean parallel processing is faster**. You should consider:

| Factor | When is parallel processing worth considering? |
| --- | --- |
| Number of elements | Large enough to offset the cost of splitting and merging work. |
| Work per element | CPU-intensive, independent computations, minimal synchronization. |
| Source | Easy to split into relatively balanced parts. |
| Operations | Mostly stateless; does not have to maintain many ordering constraints. |
| Shared resources | Does not cause I/O bottlenecks, lock contention, or CPU competition with other tasks. |

You should not convert every `stream()` to `parallelStream()` by default. For small sets, very lightweight computations, or environments already running many concurrent tasks, sequential is usually clearer and can be faster. If performance is the reason for switching modes, benchmark under realistic conditions, with warm-up, and measure data creation, processing, and result collection separately.

## 8. Source Data Safety and Lifecycle

Creating a Stream from a Collection **does not create an immutable copy** of the data. With common Collections that do not support concurrent updates, modifying the Collection's structure while the pipeline is traversing it can lead to `ConcurrentModificationException` or unspecified behavior. Do not rely on that exception as a mechanism to detect all conflicts.

```java
List<String> names = new ArrayList<>(Arrays.asList("An", "Binh", "Chi"));

// Do not update the list while a stream is reading it:
// names.stream().forEach(name -> names.remove(name)); // Wrong

List<String> snapshot = new ArrayList<>(names);
List<String> upper = snapshot.stream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

`snapshot` is a copy of the List's contents at the time of copying (for mutable element objects, this is only a **shallow** copy). If multiple threads modify `names` concurrently, creating the snapshot also requires proper synchronization. There are concurrent Collections with different contracts, but you should not generalize that switching to `parallelStream()` automatically makes a source thread-safe.

Some practical guidelines:

1. Keep functions passed to `map`, `filter`, and `reduce` **non-modifying to the source**, and independent of state that could be changed by other threads.
2. Create a new Stream each time another terminal operation is needed; do not reuse a Stream after it has been consumed.
3. In-memory Collections normally do not need `close()` after `stream()`; sources from files or external resources have their own closing rules, for example `Files.lines(...)` requires `try-with-resources`.
4. Do not rely on the collected result being a mutable `ArrayList`: `Collectors.toList()` makes no guarantees on the specific List type or mutability. When you specifically need an `ArrayList`, use `collect(Collectors.toCollection(ArrayList::new))`.
5. Convert numeric data from `Collection<Integer>` to a primitive Stream using `mapToInt(Integer::intValue)` or `mapToLong(Integer::longValue)` when appropriate, reducing boxing/unboxing in subsequent computation steps.

## 9. Practice Exercises with Answers

### Exercise 1: Order List

Given order amounts `List<Integer> amounts = Arrays.asList(120, 50, 300, 80, 150);`. Compute the sum of orders of `100` or more using sequential and parallel Streams.

```java
List<Integer> amounts = Arrays.asList(120, 50, 300, 80, 150);

long sequential = amounts.stream()
    .filter(amount -> amount >= 100)
    .mapToLong(Integer::longValue)
    .sum();

long parallel = amounts.parallelStream()
    .filter(amount -> amount >= 100)
    .mapToLong(Integer::longValue)
    .sum();

// sequential = parallel = 570
```

**Explanation:** Both approaches filter the three values `120`, `300`, `150` and sum them with an appropriate aggregation operation. This problem does not need parallel execution for good performance.

### Exercise 2: Is Output Order Guaranteed?

```java
List<String> words = Arrays.asList("cat", "apple", "dog", "banana");
List<String> out = words.parallelStream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

**Answer:** `out` is `[APPLE, BANANA]` following the List's encounter order. The *execution* order of the `filter` and `map` calls may differ, but `collect(Collectors.toList())` preserves the element order of an ordered source.

### Exercise 3: Identify the Bug

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4);
List<Integer> shared = new ArrayList<>();
values.parallelStream().filter(n -> n % 2 == 0)
    .forEach(shared::add);
```

**Answer:** `shared` is an `ArrayList` being written to concurrently by multiple threads, which is unsafe. Rewrite as:

```java
List<Integer> evens = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList()); // [2, 4]
```

### Exercise 4: Stream from a Map

Given `Map<String, Integer> inventory` storing product names and stock quantities. Why is `inventory.stream()` invalid, and how do you get the names of products in stock?

```java
Map<String, Integer> inventory = new HashMap<>();
inventory.put("book", 12);
inventory.put("pen", 0);
inventory.put("notebook", 3);

List<String> available = inventory.entrySet().stream()
    .filter(entry -> entry.getValue() > 0)
    .map(Map.Entry::getKey)
    .collect(Collectors.toList());
// Includes "book" and "notebook"; order is not guaranteed by HashMap.
```

**Explanation:** `Map` does not implement `Collection`. `entrySet()` returns a `Set<Map.Entry<String, Integer>>`, so you can create a Stream from this Set, then filter and extract the key.

## Key Takeaways

`Collection.stream()` is the default choice for building a sequential pipeline that is predictable and usually fast enough. `Collection.parallelStream()` is suitable when data can be split efficiently, each element is processed independently, and computation cost is sufficiently high. Both **describe a lazy, single-use pipeline** and share rules regarding encounter order, lambda statelessness, and collection correctness. Choose the mode based on the problem's contract and actual measurements, rather than assuming "parallel" is automatically faster or safer.
