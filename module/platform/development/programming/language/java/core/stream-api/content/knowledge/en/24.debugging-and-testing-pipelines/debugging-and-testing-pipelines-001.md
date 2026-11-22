# Reading Pipelines by Data Type and Data Shape Step by Step

A Java Stream pipeline can be very short yet still hard to debug:

```java
var result = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .sorted()
    .toList();
```

When reading this snippet, knowing only that `result` is "a list" is not enough. We need to answer **two different questions at each step**:

1. **What is the Java type?** For example, `Stream<Order>`, `Stream<List<String>>`, `Stream<String>`, or `List<String>`.
2. **What is the *data shape*?** How many elements are there, is each element a record or a list, are there nested groups, what order is guaranteed, and can it be empty or contain duplicates?

This is a foundational skill for reading, explaining, debugging, and testing pipelines using `filter`, `map`, `flatMap`, `reduce`, `collect`, multi-level collectors, `Spliterator`, and Stream Gatherers. This lesson belongs to the **Debugging and Testing Pipelines** chapter of the **JAVA_STREAM_API** module: learning declarative data processing without losing the ability to reason about correctness, state, resources, and performance.

The core examples use **Java 17+**; the `Stream.gather` section is separated for **Java 24+** because Stream Gatherers became official only in JDK 24.

## 1. Data Type and Data Shape Are Not the Same Thing

Let's distinguish them:

| Concept | Question to ask | Example |
| --- | --- | --- |
| **Element type** | What Java type does each element have? | `Order`, `String`, `List<String>` |
| **Stream type** | In what form does the pipeline currently emit elements? | `Stream<Order>`, `LongStream` |
| **Cardinality** | How many elements remain after the stage? | From 4 orders down to 3 paid orders |
| **Nesting level** | Is each element a single value or a sub-collection? | `Stream<List<String>>` instead of `Stream<String>` |
| **Encounter order** | Do the elements have a guaranteed order? | `List.stream()` is ordered; `HashSet.stream()` is not |
| **Duplicates** | Can elements with the same value appear multiple times? | `["java", "java", "api"]` |
| **Empty/missing values** | Can the source or groups be empty? Can `null` exist? | `List.of()`, `Optional.empty()` |
| **Final result shape** | What object does the terminal operation return? | `List<String>`, `Map<String,Long>`, `Optional<Order>` |

A `Stream<List<String>>` with three elements is **not** the same as a `Stream<String>` with three elements. In the first case, each element is itself a list, and the length of each list can differ.

### Visualizing along two axes

```text
Static type                  Observable shape

Stream<Order>              [O1, O2, O3, O4]
      |                              |
      | filter(paid)                 | drop O2
      v                              v
Stream<Order>              [O1, O3, O4]
      |                              |
      | map(tags)                    | each O -> a List
      v                              v
Stream<List<String>>       [[java, backend], [java, streams], []]
      |                              |
      | flatMap(List::stream)        | concatenate sub-lists
      v                              v
Stream<String>             [java, backend, java, streams]
      |                              |
      | distinct()                   | remove duplicates
      v                              v
Stream<String>             [java, backend, streams]
      |                              |
      | sorted()                     | sort
      v                              v
Stream<String>             [backend, java, streams]
      |                              |
      | toList()                     | materialize
      v                              v
List<String>               [backend, java, streams]
```

**Rule:** Don't just say "`map` changed the list." State **how it changed the element type** and **how it changed the observable shape**. These two pieces of information are the key to catching `map`/`flatMap` bugs, collector bugs, and wrong cardinality expectations.

## 2. Sample Dataset Used Throughout

So that examples can be verified by hand, we use a small dataset containing both normal and edge cases.

```java
import java.util.List;

record Order(
    String id,
    String region,
    List<String> tags,
    long amountCents,
    boolean paid
) {}

List<Order> orders = List.of(
    new Order("O-1", "Bac",   List.of("java", "backend"), 120_000L, true),
    new Order("O-2", "Nam",   List.of("frontend"),       90_000L, false),
    new Order("O-3", "Bac",   List.of("java", "streams"),  80_000L, true),
    new Order("O-4", "Trung", List.of(),                  50_000L, true)
);
```

The source data consists of four records in the order `O-1, O-2, O-3, O-4`.

| Order | Paid? | Tags | Tag count | Amount (cents) |
| --- | --- | --- | ---: | ---: |
| O-1 | Yes | java, backend | 2 | 120,000 |
| O-2 | No | frontend | 1 | 90,000 |
| O-3 | Yes | java, streams | 2 | 80,000 |
| O-4 | Yes | (empty) | 0 | 50,000 |

When taking only paid orders, `O-1, O-3, O-4` remain: three orders, with a total of **four tag occurrences**, but only **three distinct tags**.

In the code snippets below, when only the `orders` variable is used, assume they run **in the same scope** as the record and list declarations above. A complete Java program is provided at the end of the lesson.

## 3. Source Initialization Step: `Collection` to `Stream<T>`

`orders` has type `List<Order>`. When calling `stream()`:

```java
java.util.stream.Stream<Order> source = orders.stream();
```

the type is `Stream<Order>`, **not `List<Order>`**. No new result list has been built yet and no processing pipeline has executed yet. The data remains in the source collection, while the Stream describes a single traversal and processing pass.

Logical shape:

```text
List<Order>      : [O-1, O-2, O-3, O-4]
                       |
                       | stream()
                       v
Stream<Order>    : Order elements in the List's encounter order
```

Things to keep in mind:

- A Stream is **consumed once**; after a terminal operation, you cannot run another terminal operation on that same Stream.
- Intermediate operations create new stages, rather than necessarily copying the source into a new collection.
- `Stream<T>` is not `T[]`, `List<T>`, or `Optional<T>`.
- Do not assume a Stream already knows its exact count if a custom source does not report its size.

## 4. Shape Contract Table of Intermediate Operations

This table is a quick-reference "dictionary." The cardinality notation indicates the **logical** number of elements that can reach the output if the pipeline is traversed appropriately, not a guarantee on how many times a lambda is invoked.

| Operation | Input type → output type | Typical shape and cardinality |
| --- | --- | --- |
| `filter(Predicate<T>)` | `Stream<T> → Stream<T>` | Keeps 0 or 1 element per input; total 0..N |
| `map(Function<T,R>)` | `Stream<T> → Stream<R>` | Logically 1:1 transformation; may change element type |
| `flatMap(Function<T,Stream<R>>)` | `Stream<T> → Stream<R>` | Each input becomes 0..n elements; removes one Stream layer |
| `mapMulti(...)` | `Stream<T> → Stream<R>` | Can emit 0..n results per input without forcing sub-Stream creation |
| `distinct()` | `Stream<T> → Stream<T>` | Removes equal elements; 0..N |
| `sorted(...)` | `Stream<T> → Stream<T>` | Same elements, sorted by comparator; can be stateful |
| `limit(k)` | `Stream<T> → Stream<T>` | Keeps at most k elements; on an ordered Stream keeps the first k |
| `skip(k)` | `Stream<T> → Stream<T>` | Skips the first k elements on an ordered Stream |
| `takeWhile(p)` | `Stream<T> → Stream<T>` | On an ordered Stream keeps the longest prefix matching p |
| `dropWhile(p)` | `Stream<T> → Stream<T>` | On an ordered Stream drops that prefix, keeps the entire suffix |
| `peek(Consumer<T>)` | `Stream<T> → Stream<T>` | Does not change type or logical result set; conditional observation only |
| `mapToInt(...)` | `Stream<T> → IntStream` | Transforms each element into an `int` when evaluated |
| `mapToLong(...)` | `Stream<T> → LongStream` | Transforms into a primitive `long` Stream |
| `boxed()` | `IntStream → Stream<Integer>` | Boxes numbers, does not merge elements |
| `gather(Gatherer)` | `Stream<T> → Stream<R>` | Flexible output count; can hold state, window elements; JDK 24+ |

For `map`, the phrase "one in, one out" describes the **logical relationship among processed elements**, not a guarantee that Java will run the `map` callback exactly N times under every terminal operation. When results are not needed, some stages may be optimized away.

## 5. Reading `filter`: Removing Elements Without Changing Type

`filter` selects paid orders:

```java
java.util.stream.Stream<Order> paidOrders = orders.stream()
    .filter(Order::paid);
```

The type remains `Stream<Order>`. The shape changes from four records to three:

```text
Stream<Order> : [O-1, O-2, O-3, O-4]
filter(paid)  : [O-1,      O-3, O-4]
Stream<Order> : [O-1, O-3, O-4]
```

`filter` does not produce `Stream<Boolean>`. The `Order::paid` method returns a boolean, but that boolean is only used to **decide whether to keep or drop the Order element**.

Distinguish between these two:

```java
// Keep Orders matching the condition.
List<Order> paid = orders.stream()
    .filter(Order::paid)
    .toList();

// Transform each Order into a Boolean, including unpaid orders.
List<Boolean> flags = orders.stream()
    .map(Order::paid)
    .toList();

System.out.println(paid.size()); // 3
System.out.println(flags);       // [true, false, true, true]
```

When reading a pipeline, ask: **does the predicate only decide which elements to keep, or does the boolean value itself become part of the result data?** The answer distinguishes `filter` from `map`.

## 6. Reading `map`: Changing Element Type Without Flattening

Transforming each order into its list of tags:

```java
java.util.stream.Stream<List<String>> groupedTags = orders.stream()
    .filter(Order::paid)
    .map(Order::tags);
```

The type after `map` is **`Stream<List<String>>`**:

```text
[O-1, O-3, O-4]
       |
       | map(Order::tags)
       v
[[java, backend], [java, streams], []]
```

There are **three elements at the outer Stream level**, corresponding to three orders. But each element is a `List<String>` of lengths 2, 2, and 0.

### 6.1. Common mistake: expecting `List<String>` when you have `List<List<String>>`

```java
List<List<String>> nested = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .toList();

System.out.println(nested);
// [[java, backend], [java, streams], []]
```

The following declaration will **fail to compile**, because the two types differ:

```java
// WRONG TYPE:
// List<String> tags = orders.stream()
//     .filter(Order::paid)
//     .map(Order::tags)
//     .toList();
```

`map` itself **does not know** whether you want to keep the sub-lists or merge them into one flat list. If the goal is tags grouped **per order**, `List<List<String>>` may be completely right; if the goal is all tags at the same level, you need `flatMap` or `mapMulti`.

## 7. Reading `flatMap`: Removing One Level of Nesting

`flatMap` takes each input element to create a sub-Stream, then concatenates the sub-Streams into a single flat Stream.

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .toList();

System.out.println(tags);
// [java, backend, java, streams]
```

Step table:

| Step | Type | Shape |
| --- | --- | --- |
| `orders.stream()` | `Stream<Order>` | 4 `Order`s |
| `filter(Order::paid)` | `Stream<Order>` | 3 `Order`s |
| `map(Order::tags)` | `Stream<List<String>>` | 3 lists: lengths 2, 2, 0 |
| `flatMap(List::stream)` | `Stream<String>` | 4 strings: java, backend, java, streams |
| `toList()` | `List<String>` | 4 strings materialized |

Equivalent shorthand:

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .toList();
```

**Key cardinality point:** the number of paid orders is 3, while the number of tags after `flatMap` is 4. Do not compare `count()` before and after `flatMap` as if they were counting the same kind of entity.

### 7.1. Distinguishing `map(List::stream)` from `flatMap(List::stream)`

```java
// Each element of the outer Stream is a sub-Stream.
List<java.util.stream.Stream<String>> nestedStreams = orders.stream()
    .filter(Order::paid)
    .map(order -> order.tags().stream())
    .toList();

// Concatenate all tags into one Stream<String>.
List<String> flatTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .toList();
```

The type of `map(order -> order.tags().stream())` is `Stream<Stream<String>>`. Only `flatMap` **flattens** the sub-Streams. Do not treat a list of sub-Streams as a normal long-lived result: each sub-Stream has a single-use lifecycle and may hold resources depending on its source.

### 7.2. `flatMap` with `Optional` and `Stream.ofNullable`

When data may be missing, you can turn `Optional<T>` into 0 or 1 element using `Optional.stream()` (Java 9+):

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> values = List.of(
    Optional.of("A"),
    Optional.empty(),
    Optional.of("B")
);

List<String> present = values.stream()
    .flatMap(Optional::stream)
    .toList();

System.out.println(present); // [A, B]
```

The shape transformation is `Stream<Optional<String>> → Stream<String>`. Each `Optional.empty()` contributes **0** elements. Similarly, `Stream.ofNullable(value)` creates a Stream with 0 or 1 element depending on whether `value` is null.

## 8. `mapMulti`: Same 0..n Output Goal, Different Implementation

Since Java 16, `Stream.mapMulti` provides a callback receiving an input element and a `Consumer` to emit multiple elements without forcing the callback to return a sub-Stream.

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .<String>mapMulti((order, output) -> {
        for (String tag : order.tags()) {
            output.accept(tag);
        }
    })
    .toList();

System.out.println(tags);
// [java, backend, java, streams]
```

Comparison:

| Approach | Before → after type | Output for one `Order` |
| --- | --- | --- |
| `map(Order::tags)` | `Stream<Order> → Stream<List<String>>` | One `List<String>` |
| `flatMap(o -> o.tags().stream())` | `Stream<Order> → Stream<String>` | 0..n `String`s |
| `mapMulti((o,out) -> ...)` | `Stream<Order> → Stream<String>` | 0..n `String`s |

The `<String>` before `mapMulti` helps the compiler infer the emitted type `R` in complex type-inference expressions. It is a **type witness** and does not mean `mapMulti` builds a `List<String>` at an intermediate step.

`mapMulti` can be useful when each element produces few results and you want to avoid creating many small sub-Streams; however, do not assume it is always faster than `flatMap`. Verify equivalent semantics and benchmark on representative data.

## 9. `distinct`, `sorted`, `limit`: Type May Stay the Same, Shape Still Changes

After flattening tags:

```text
[java, backend, java, streams]
```

`distinct()` reduces cardinality from 4 down to 3:

```java
List<String> uniqueTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .toList();

System.out.println(uniqueTags); // [java, backend, streams]
```

`sorted()` keeps the same three values but changes their order:

```java
List<String> sortedTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .sorted()
    .toList();

System.out.println(sortedTags); // [backend, java, streams]
```

`limit(2)` takes at most the first two values of the pipeline at that point:

```java
List<String> firstTwo = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .sorted()
    .limit(2)
    .toList();

System.out.println(firstTwo); // [backend, java]
```

| Stage | Type | Shape |
| --- | --- | --- |
| `flatMap(...)` | `Stream<String>` | 4 tags, with `java` duplicated |
| `distinct()` | `Stream<String>` | 3 distinct tags, in first-seen order for ordered sources |
| `sorted()` | `Stream<String>` | 3 tags in alphabetical order |
| `limit(2)` | `Stream<String>` | First 2 tags |
| `toList()` | `List<String>` | `[backend, java]` |

**Misconception to avoid:** "The type didn't change" **does not mean** "the data didn't change." `distinct` changes cardinality; `sorted` changes encounter order; `limit` changes the bound; `skip` changes the starting point.

### 9.1. Stage order determines meaning

```java
List<String> a = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .limit(2)
    .toList();

List<String> b = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .limit(2)
    .distinct()
    .toList();

System.out.println(a); // [java, backend]
System.out.println(b); // [java, backend]
```

The two results happen to match here **because of the sample data**, which does not prove the two operations always commute. With the sequence `[A, A, B]`:

```java
List<String> values = List.of("A", "A", "B");

System.out.println(values.stream().distinct().limit(2).toList());
// [A, B]

System.out.println(values.stream().limit(2).distinct().toList());
// [A]
```

This is how you debug shape bugs **caused by operation ordering**, not by Java types.

## 10. `takeWhile`/`dropWhile`: Prefix and Suffix Shapes

On an **ordered** Stream, `takeWhile(predicate)` returns the **longest prefix** matching the condition; `dropWhile(predicate)` drops that prefix and keeps everything after it.

```java
List<Integer> readings = List.of(2, 4, 9, 3, 6);

System.out.println(readings.stream()
    .filter(n -> n < 5)
    .toList()); // [2, 4, 3]

System.out.println(readings.stream()
    .takeWhile(n -> n < 5)
    .toList()); // [2, 4]

System.out.println(readings.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [9, 3, 6]
```

All three pipelines return `List<Integer>`, yet they express **three different shapes**. If a user reports "missing the number 3," check whether that is a bug or the exact semantics of `takeWhile`.

On an **unordered Stream**, prefix taking/dropping semantics are no longer tied to a fixed domain order. Do not call `unordered()` and then expect results identical to slicing from the start of the original list.

## 11. Primitive Streams: Changing Both Interface and Aggregation Capabilities

A `mapToLong` step doesn't just "convert each value to long." It changes the **Stream type**:

```java
java.util.stream.LongStream amounts = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents);
```

Shape:

```text
Stream<Order>  : [O-1, O-3, O-4]
       |
       | mapToLong(Order::amountCents)
       v
LongStream    : [120000, 80000, 50000]
       |
       | sum()
       v
long          : 250000
```

Code:

```java
long totalPaidCents = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents)
    .sum();

System.out.println(totalPaidCents); // 250000
```

### 11.1. Common terminal operations on primitive Streams

| Expression | Result type |
| --- | --- |
| `IntStream.sum()` | `int` |
| `LongStream.sum()` | `long` |
| `DoubleStream.sum()` | `double` |
| `IntStream.average()` | `OptionalDouble` |
| `LongStream.max()` | `OptionalLong` |
| `IntStream.summaryStatistics()` | `IntSummaryStatistics` |
| `IntStream.boxed()` | `Stream<Integer>` |

Example:

```java
java.util.OptionalDouble average = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents)
    .average();

System.out.println(average.orElse(0.0)); // 83333.33333333333
```

Key takeaways:

- `average()` returns `OptionalDouble` because the Stream might be empty.
- `sum()` returns a numeric primitive even when the source is empty (for a sum, the result is 0).
- Convert `IntStream` to `Stream<Integer>` with `boxed()` when you genuinely need object Stream methods.
- `IntStream.sum()` can overflow `int`; `LongStream.sum()` can still overflow `long`. **Changing shape does not automatically prevent numeric overflow**.

### 11.2. Difference between `map` and `mapToLong`

```java
// Type: Stream<Long>, with boxing.
var boxedAmounts = orders.stream()
    .map(Order::amountCents);

// Type: LongStream, without boxing each value as Long.
var primitiveAmounts = orders.stream()
    .mapToLong(Order::amountCents);
```

After the first expression, there is no `sum()` method directly on `Stream<Long>`. After the second expression, `sum()` is a terminal operation of `LongStream`.

Do not try to fix the error by casting `(LongStream) boxedAmounts`: those are two different Stream types. Choose `mapToLong` or an appropriate collector instead.

## 12. Terminal Operations: Reading the Final Output Type

Intermediate operations typically preserve the `Stream<...>` or primitive Stream form; a terminal operation **ends** the pipeline and produces a different result type.

| Terminal operation | Common type | When it makes sense |
| --- | --- | --- |
| `toList()` | `List<T>` | Need to store all output elements |
| `count()` | `long` | Need the number of elements after transformations |
| `findFirst()` | `Optional<T>` | A first element might not exist |
| `findAny()` | `Optional<T>` | Order of the chosen element is not strictly required |
| `anyMatch(p)` | `boolean` | Need to know if any element matches |
| `min(comparator)` | `Optional<T>` | A minimum value might not exist |
| `reduce(identity, op)` | `T` | Have an identity and associative operation |
| `reduce(op)` | `Optional<T>` | No identity; source may be empty |
| `collect(collector)` | `R` decided by Collector | `Map`, `List`, multi-level reports |
| `forEach(action)` | `void` | Perform an action, return no collection |

Example:

```java
long paidCount = orders.stream()
    .filter(Order::paid)
    .count(); // 3

java.util.Optional<Order> firstPaid = orders.stream()
    .filter(Order::paid)
    .findFirst(); // Optional[O-1] in List order

boolean hasLargePaidOrder = orders.stream()
    .filter(Order::paid)
    .anyMatch(order -> order.amountCents() >= 100_000L);
// true
```

### 12.1. `Optional<T>` is an optional-value container, not a Stream

```java
java.util.Optional<Order> found = orders.stream()
    .filter(o -> o.id().equals("MISSING"))
    .findFirst();

System.out.println(found.isPresent()); // false
```

Do not call `found.toList()` as if `found` were still a Stream. If you need to keep processing the optional value:

```java
String idOrFallback = found
    .map(Order::id)
    .orElse("NOT_FOUND");

System.out.println(idOrFallback); // NOT_FOUND
```

`Optional.map` is a method on `Optional`, differing from `Stream.map` in **result type**: `Optional<Order> → Optional<String>`.

When a Stream contains `null` elements, `findFirst()` is not a safe way to construct an `Optional` "holding null": the API can throw `NullPointerException` if the selected element is null. Establish a null policy before searching for elements.

## 13. `reduce`: Shape of the Accumulator and Result

Not every `reduce` requires the accumulator type to match the input element type.

### 13.1. `reduce(identity, BinaryOperator<T>)`

```java
int sum = List.of(1, 2, 3)
    .stream()
    .reduce(0, Integer::sum);

System.out.println(sum); // 6
```

Input type is `Stream<Integer>`; identity and result are both `Integer` (unboxed to `int` on assignment).

### 13.2. `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)`

For example, summing amounts from `Stream<Order>` while accumulating into `Long`:

```java
long total = orders.stream()
    .filter(Order::paid)
    .reduce(
        0L,
        (acc, order) -> acc + order.amountCents(),
        Long::sum
    );

System.out.println(total); // 250000
```

Here:

- `T = Order`: source element type.
- `U = Long`: accumulator and result type.
- Accumulator takes `(Long, Order)` and returns `Long`.
- Combiner takes `(Long, Long)` and returns `Long`, used to merge partial results when needed.

**Do not write a combiner that takes `Order`** in this overload; it combines **two `U` accumulators**, not another `T` source element.

Reductions used in parallel pipelines must have a proper identity and associativity. Do not pass a mutable `ArrayList` as the identity and call `add` in `reduce`'s accumulator to gather elements; `collect` is the proper tool for mutable accumulation.

## 14. `collect`: Turning Element Sequences into Report Structures

`collect` can build a `List`, `Set`, `Map`, or a domain aggregate object. When reading a collector, you must read **the downstream collectors as well**, not just glance at `groupingBy`.

### 14.1. Grouping by region: `Map<String, List<Order>>`

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;

Map<String, List<Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
```

Shape:

```text
Stream<Order>
  [O-1(Bac), O-2(Nam), O-3(Bac), O-4(Trung)]
                |
                | groupingBy(region)
                v
Map<String, List<Order>>
  Bac   -> [O-1, O-3]
  Nam   -> [O-2]
  Trung -> [O-4]
```

The `Map` has only **three keys**, yet still contains all four orders inside its value lists. Saying "`groupingBy` lost an order" is wrong: it changes the **data organization level**, without necessarily dropping elements.

### 14.2. Counting by region only: `Map<String, Long>`

```java
Map<String, Long> counts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(counts.get("Bac"));   // 2
System.out.println(counts.get("Trung")); // 1
System.out.println(counts.containsKey("Nam")); // false
```

The type `Map<String,Long>` is completely different from `Map<String,List<Order>>`. Looking only at `groupingBy` makes it easy to mistake the Map values for lists instead of counts.

The `Nam` region has no paid orders, so it has **no key** in the Map. This differs from a Map having key `Nam` with value 0. If the report must display regions with zero results as well, add a canonical key set or a report completion step.

### 14.3. `mapping` changes the data type at the group level

```java
Map<String, List<String>> idsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::id,
            Collectors.toList()
        )
    ));
```

`groupingBy` partitions the source into groups by `String region`; `mapping` converts each `Order` in each group into `String id`; `toList` creates the ID lists.

Do not confuse with:

```java
List<String> allIds = orders.stream()
    .map(Order::id)
    .toList();
```

Both transform `Order → String`, but one produces a `Map<String,List<String>>` by region while the other produces a flat `List<String>`.

### 14.4. `partitioningBy` and `toMap`

`partitioningBy(Order::paid)` produces a Map of type `Map<Boolean,List<Order>>`, splitting the source into true/false sides. It differs from `groupingBy` in key type and partitioning rule.

`toMap` turns elements into key/value pairs. If multiple records share a key without a merge function, `Collectors.toMap` can throw `IllegalStateException`:

```java
// Orders O-1 and O-3 share region "Bac": duplicate key.
// orders.stream().collect(Collectors.toMap(
//     Order::region, Order::amountCents
// )); // Can throw IllegalStateException on duplicate keys.
```

Valid way when summing by region:

```java
Map<String, Long> totals = orders.stream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountCents,
        Long::sum
    ));

System.out.println(totals.get("Bac")); // 200000
```

Or use `groupingBy(..., summingLong(...))` for clearer aggregation intent.

**Order warning:** `Collectors.groupingBy` and `Collectors.toMap` do not promise Map key iteration order by default. If a report requires display ordering, specify an appropriate `mapFactory` or sort when building the output.

## 15. Splitting a Pipeline into Typed Variables to Debug

When a pipeline is long, you can split stages into variables to **read their types** before reaching for a debugger:

```java
import java.util.List;
import java.util.stream.Stream;

Stream<Order> source = orders.stream();

Stream<Order> paid = source.filter(Order::paid);

Stream<List<String>> tagLists = paid.map(Order::tags);

Stream<String> flattened = tagLists.flatMap(List::stream);

Stream<String> unique = flattened.distinct();

Stream<String> sorted = unique.sorted();

List<String> result = sorted.toList();
```

Output:

```text
[backend, java, streams]
```

Each variable above has **one explicit static type**. If changed by mistake:

```java
// WRONG variable type:
// Stream<String> tagLists = paid.map(Order::tags);
```

the compiler will point out that `map(Order::tags)` produces `Stream<List<String>>`, not `Stream<String>`.

### 15.1. Do not reuse a consumed Stream

Wrong debugging approach:

```java
Stream<Order> paid = orders.stream().filter(Order::paid);

long count = paid.count();

// paid.toList(); // Invalid: the same Stream has already been consumed.
```

Right approach if you want to measure multiple questions on the same collection:

```java
long count = orders.stream()
    .filter(Order::paid)
    .count();

List<Order> paidList = orders.stream()
    .filter(Order::paid)
    .toList();
```

The two queries use **two separate Streams**. With file or connection sources, re-reading arbitrarily is not always possible; in that case decide whether to materialize the data for debugging, or design the statistics pass in **one traversal**.

### 15.2. Intermediate snapshots help reveal the shape

For small datasets, you can temporarily materialize a stage:

```java
List<Order> paidSnapshot = orders.stream()
    .filter(Order::paid)
    .toList();

List<List<String>> tagsSnapshot = paidSnapshot.stream()
    .map(Order::tags)
    .toList();

System.out.println(tagsSnapshot);
// [[java, backend], [java, streams], []]
```

This lets you see both **the outer element count (3)** and **the size of each inner list (2, 2, 0)**. However, snapshotting changes laziness, allocates extra memory, and can be unsuitable for large/infinite sources. Use it only as a controlled debugging technique.

## 16. `peek`: Limited Observation, Not Mandatory Logging

`peek` can be helpful for observing values passing through a stage:

```java
List<String> result = orders.stream()
    .filter(Order::paid)
    .peek(order -> System.out.println("paid: " + order.id()))
    .flatMap(order -> order.tags().stream())
    .peek(tag -> System.out.println("tag: " + tag))
    .distinct()
    .toList();
```

The two `peek` calls see **two different element types**: the first sees `Order`, the second sees `String`. Without paying attention to the type at each stage, log messages are easy to misread.

However:

- `peek` is an **intermediate operation**; without a terminal operation, nothing forces the pipeline to run.
- A terminal operation may be optimized without invoking some intermediate stages if the final result remains valid.
- With `parallel()`, log order and threads can differ from encounter order.
- Side effects inside `peek` must not be used to perform required business recording.

Important example:

```java
long n = List.of("A", "B", "C").stream()
    .peek(System.out::println)
    .count();

System.out.println(n); // 3
// Do not assert for certain that A, B, and C were all printed.
```

Because the source has a known size and `peek` does not alter element count, `count()` can be implemented without traversing every element. Use `peek` for **conditional observational debugging**, never using callback invocation count as a pass/fail indicator.

## 17. Use a Manual Trace Table Before Changing Code

A trace table is a quick way to locate where a bug occurs. For the full pipeline:

```java
List<String> result = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .sorted()
    .toList();
```

Build the table:

| Step | Static type | Outer count | Observed content/shape |
| --- | --- | ---: | --- |
| `orders` | `List<Order>` | 4 | O-1, O-2, O-3, O-4 |
| `stream` | `Stream<Order>` | 4 | 4 source records |
| `filter(paid)` | `Stream<Order>` | 3 | O-1, O-3, O-4 |
| `map(tags)` | `Stream<List<String>>` | 3 | Lists of length 2, 2, 0 |
| `flatMap` | `Stream<String>` | 4 | java, backend, java, streams |
| `distinct` | `Stream<String>` | 3 | java, backend, streams |
| `sorted` | `Stream<String>` | 3 | backend, java, streams |
| `toList` | `List<String>` | 3 | result list |

When comparing expectations with reality, pinpoint **the first step where expectations diverge**. For example:

- Expected 4 orders, but only 3 remain after `filter`: is the paid filter really what you intended?
- Expected 4 tags, but only 3 elements appear after `map`: those are 3 **lists**; `flatMap` is needed.
- Expected 4 tags, but only 3 remain after `distinct`: the duplicate `java` tag was removed.
- Expected input order, but it changed after `sorted`: that matches the sorting contract.

A trace table separates a **code bug** from **correct behavior that differs from a business assumption**.

## 18. Useful *Invariants* When Testing Shape

To test pipelines systematically, state the properties that must hold.

### 18.1. Cardinality invariants

For finite sources:

- `filter` cannot **increase** the result element count.
- `map` preserves the **logical** element count when evaluating each input element.
- `flatMap` and `mapMulti` can increase, decrease, or keep element count unchanged.
- `distinct` does not increase element count.
- `sorted` does not alter the multiset of elements, only their ordering.
- `limit(k)` yields at most k elements, for non-negative k.

Do not turn an invariant on the **result** into an invariant on **how many times a callback executes**. Execution counts can vary due to short-circuiting and optimizations.

### 18.2. Content invariants

For the problem "distinct tags of paid orders":

- Every output tag must come from at least one paid order.
- No duplicate tags under `String.equals`.
- If `sorted()` was called, the list must follow the corresponding comparison order.
- An order with an empty tag list must not introduce an `""` or `null` tag unless the data actually contains it.

### 18.3. Structural invariants

- After `groupingBy(Order::region)`, Map values are lists of `Order`s belonging to that region.
- After `groupingBy(..., counting())`, Map values are `Long`, no longer lists.
- After `flatMap(Optional::stream)`, no `Optional` wrapper remains around elements.
- After `findFirst()`, the result is `Optional<T>` and the empty branch must be handled.

These invariants can be translated into executable assertions.

## 19. Testing with JUnit 5: Checking Both Values and Shape

This lesson does not require installing a test library to read; below is a **JUnit 5 example** if your project already includes the JUnit Jupiter dependency.

Suppose we have these records and methods:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(
    String id, String region, List<String> tags,
    long amountCents, boolean paid
) {}

class OrderQueries {
    static List<String> uniquePaidTags(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .flatMap(o -> o.tags().stream())
            .distinct()
            .sorted()
            .toList();
    }

    static Map<String, Long> paidCountByRegion(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }
}
```

The test suite (in a standard project test file):

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderQueriesTest {
    private static List<Order> sample() {
        return List.of(
            new Order("O-1", "Bac", List.of("java", "backend"), 120_000L, true),
            new Order("O-2", "Nam", List.of("frontend"), 90_000L, false),
            new Order("O-3", "Bac", List.of("java", "streams"), 80_000L, true),
            new Order("O-4", "Trung", List.of(), 50_000L, true)
        );
    }

    @Test
    void uniquePaidTagsHaveCorrectShapeAndOrder() {
        List<String> result = OrderQueries.uniquePaidTags(sample());

        assertEquals(List.of("backend", "java", "streams"), result);
        assertEquals(3, result.size());
        assertEquals(3, result.stream().distinct().count());
    }

    @Test
    void emptySourceProducesEmptyListAndMap() {
        assertEquals(List.of(), OrderQueries.uniquePaidTags(List.of()));
        assertEquals(Map.of(), OrderQueries.paidCountByRegion(List.of()));
    }

    @Test
    void groupsContainCountsRatherThanLists() {
        Map<String, Long> counts =
            OrderQueries.paidCountByRegion(sample());

        assertEquals(Long.valueOf(2L), counts.get("Bac"));
        assertEquals(Long.valueOf(1L), counts.get("Trung"));
        assertFalse(counts.containsKey("Nam"));
    }
}
```

The takeaway is not the number of assertions, but **checking at multiple levels**:

1. **Values:** which tags appear?
2. **Shape:** is the result a `List<String>` or `Map<String,Long>`?
3. **Cardinality:** are there exactly 3 distinct tags?
4. **Order:** was `sorted` actually applied?
5. **Empty case:** does an empty source produce an empty list/Map?
6. **Missing group:** is key `Nam` absent rather than arbitrarily assigned 0?

For Maps, compare by key/value pairs or `Map.equals` instead of relying on a printed string having some specific order.

## 20. Complete Java 17 Program for Self-Verification

The following example can be saved as `PipelineShapeWalkthrough.java` and compiled with Java 17 or newer.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PipelineShapeWalkthrough {

    record Order(
        String id, String region, List<String> tags,
        long amountCents, boolean paid
    ) {}

    static List<Order> data() {
        return List.of(
            new Order("O-1", "Bac", List.of("java", "backend"), 120_000L, true),
            new Order("O-2", "Nam", List.of("frontend"), 90_000L, false),
            new Order("O-3", "Bac", List.of("java", "streams"), 80_000L, true),
            new Order("O-4", "Trung", List.of(), 50_000L, true)
        );
    }

    static List<String> uniquePaidTags(List<Order> orders) {
        Stream<Order> paid = orders.stream().filter(Order::paid);

        Stream<List<String>> nested = paid.map(Order::tags);

        Stream<String> flat = nested.flatMap(List::stream);

        return flat.distinct().sorted().toList();
    }

    static Map<String, Long> countPaidByRegion(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = data();

        List<String> tags = uniquePaidTags(orders);
        Map<String, Long> counts = countPaidByRegion(orders);
        long totalPaid = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountCents)
            .sum();

        System.out.println("tags = " + tags);
        System.out.println("Bac = " + counts.get("Bac"));
        System.out.println("Trung = " + counts.get("Trung"));
        System.out.println("paid total = " + totalPaid);

        if (!tags.equals(List.of("backend", "java", "streams"))) {
            throw new AssertionError("Unexpected tags");
        }

        if (!Long.valueOf(2L).equals(counts.get("Bac"))) {
            throw new AssertionError("Unexpected Bac count");
        }

        if (totalPaid != 250_000L) {
            throw new AssertionError("Unexpected paid total");
        }
    }
}
```

Expected output:

```text
tags = [backend, java, streams]
Bac = 2
Trung = 1
paid total = 250000
```

The program needs neither `peek` nor side effects inside pipelines. Intermediate variables are explicitly typed, exposing element type changes right at compile time.

## 21. Commonly Overlooked Causes of Shape Bugs

### 21.1. Nulls, empty lists, and missing data

`List.of(...)` and `List.copyOf(...)` reject nulls. Yet a `Stream` can draw data from another source containing null elements. Calling `Order::tags` on a null `Order` can throw `NullPointerException`. If `Order.tags()` returns null, `flatMap(order -> order.tags().stream())` throws as well.

How to handle this depends on the **data contract**, for instance filtering out null elements if nulls are permitted at the source:

```java
import java.util.Objects;

List<String> safeNames = someNames.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .toList();
```

The snippet above assumes `someNames` is a collection of strings that may contain nulls. Do not blindly filter out nulls if null represents a business state that must be counted.

### 21.2. `Map` has no guaranteed key order by default

Given `Map<String,List<Order>>`, the order within each group's `List<Order>` and the iteration order of the `String` keys are **two separate things**. `groupingBy` does not guarantee Map key order by default; if business logic requires ordering, choose how to build the Map and test it explicitly.

### 21.3. `toList()` is not identical to every form of `Collectors.toList()`

`Stream.toList()` (Java 16+) returns an **unmodifiable** list by contract. `Collectors.toList()` makes no guarantees about a specific implementation, mutability, or serializability. When mutating the collected list afterward is an explicit requirement, construct an `ArrayList` or use a collector designed for that purpose.

### 21.4. Type inference with `var` can hide shape issues

`var result = ...` is often convenient, but when debugging it can obscure the difference between `Stream<List<String>>` and `Stream<String>` for newcomers.

Temporarily using explicitly typed variables makes it clear:

```java
Stream<List<String>> beforeFlatten = orders.stream()
    .map(Order::tags);

Stream<String> afterFlatten = orders.stream()
    .flatMap(o -> o.tags().stream());
```

You don't have to abandon `var` in production code; the goal is to have a way to **test type hypotheses** when code is hard to read.

## 22. `parallel()` and `unordered()`: Same Shape, Different Order

With an ordered `List`, side-effect-free pipelines using appropriate terminal operations normally produce the same logical result sequentially and in parallel:

```java
List<String> sequential = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .sorted()
    .toList();

List<String> parallel = orders.parallelStream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .sorted()
    .toList();

System.out.println(sequential.equals(parallel)); // true
```

However:

- `forEach` on a parallel Stream **does not guarantee** the action runs in encounter order.
- `findAny` does not promise to return the first element.
- `unordered()` drops ordering constraints; order-sensitive operations like `limit` or `takeWhile` can have different semantics once the source is no longer ordered.
- `groupingByConcurrent` returns a Map with concurrent/unordered characteristics; do not infer element order within each group from input order.
- Lambdas reading/writing **shared mutable state** can cause data races and make the resulting shape non-deterministic.

**Debugging parallel pipelines:** first run the pipeline **sequentially** on a small input, verifying type and result invariants; then run in parallel and compare only the properties the contract actually guarantees. Do not compare `peek` logs as if logging reflected guaranteed data order.

## 23. `Spliterator` and Custom Sources Affect How Shape Is Read

With standard sources like `ArrayList`, `Stream.of`, or `IntStream.range`, encounter order and size are well understood. However, a custom `Spliterator` may not know its element count upfront, may split the source differently, or may not guarantee order.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> spliterator =
    List.of("A", "B", "C").spliterator();

System.out.println(spliterator.estimateSize()); // 3
System.out.println(
    spliterator.hasCharacteristics(Spliterator.ORDERED)
); // true
```

Flags such as `ORDERED`, `SIZED`, and `SUBSIZED` are the **source contract** the framework uses to decide how to process data. If a custom Spliterator declares `SIZED` while `estimateSize()` is wrong or `trySplit()` drops/duplicates elements, pipeline results can be wrong even when `map` and `filter` are completely correct.

When debugging shape from a custom source, inspect **the input and source characteristics first**, instead of looking only at downstream code. `StreamSupport` uses a Spliterator as a Stream source, but cannot fix contract violations declared by the Spliterator itself.

## 24. Stream Gatherers (Java 24+): A Stage That Changes the Data Level

`Stream.gather(...)` allows flexible, often stateful intermediate operations. In particular, `Gatherers.windowFixed(k)` and `Gatherers.windowSliding(k)` turn `Stream<T>` into **`Stream<List<T>>`**.

Java 24+ example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(fixed);   // [[1, 2, 3], [4, 5]]
System.out.println(sliding); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Read the shape at two levels:

| Stage | Type | Observed result |
| --- | --- | --- |
| `Stream.of(1,...,5)` | `Stream<Integer>` | 5 numbers |
| `gather(windowFixed(3))` | `Stream<List<Integer>>` | 2 lists: 3 and 2 numbers |
| `gather(windowSliding(3))` | `Stream<List<Integer>>` | 3 lists: 3 numbers each |
| `map(window -> window.size())` | `Stream<Integer>` | Element count in each window |
| `toList()` | `List<Integer>` | List of window sizes |

If the source has 1 or 2 elements and `windowSliding(3)` is used, the API emits **one short window** containing the entire source; an empty source emits no windows. Therefore, do not assume every `List<Integer>` has length exactly 3.

### 24.1. Computing metrics right after windowing

```java
List<Long> windowTotals = Stream.of(10L, 20L, 30L, 40L)
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream().mapToLong(Long::longValue).sum())
    .toList();

System.out.println(windowTotals); // [60, 90]
```

Types in sequence:

```text
Stream<Long>
    -> Stream<List<Long>>
    -> Stream<Long>
    -> List<Long>
```

This is a **multi-level shape transformation**, even though the code is only a few lines long. From the initial `Stream<Long>`, elements are grouped, each group is aggregated, and then the result returns to a flat `Stream<Long>`.

### 24.2. `gather` cannot be used directly on `IntStream`

In Java 24, `gather` is provided on `Stream<T>`; `IntStream` has no corresponding `gather` method. When a Gatherer is needed for an `int` source, you can call `boxed()` first:

```java
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

Key debugging point: **`IntStream → Stream<Integer> → Stream<List<Integer>> → List<List<Integer>>`**. Boxing can incur overhead on very large datasets; avoid using a Gatherer if you only need a sum on a primitive Stream.

## 25. I/O Sources: Right Shape with Wrong Lifecycle Is Still a Bug

`Files.lines(path)` returns a `Stream<String>` containing lines from a file, backed by a file-reading resource that must be closed. Downstream stages may produce the exact right type and content, yet forgetting to close it leaves a resource-management bug.

Example counting lines containing `ERROR`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> line.contains("ERROR"))
            .count();
    }
}
```

Shape:

```text
Path
  |
  | Files.lines(path)
  v
Stream<String> : lines, source backed by an I/O resource
  |
  | filter(contains ERROR)
  v
Stream<String> : error lines
  |
  | count()
  v
long           : number of error lines
```

`try-with-resources` closes the source even if an exception occurs or the pipeline short-circuits. The terminal operation `count` **does not automatically replace `close()`**.

If an API returns an open Stream to a caller, document clearly **which side owns and closes** the resource. When debugging a lazy file-reading pipeline, never return a Stream from inside `try-with-resources` and then try to consume it after the source has closed.

## 26. Checklist for Debugging a Long Pipeline

When facing a pipeline that "compiles and runs, but gives the wrong result," check in this order:

1. **Source:** What is the input data? `List`, `Map`, `Set`, a file, or a custom `Spliterator`? Is it ordered?
2. **Initial type:** What element type does `Stream<T>` hold?
3. **Type changes:** Which stage converts `T → R`, or `Stream<T> → IntStream`?
4. **Nesting levels:** Is there a `Stream<List<R>>` or `Stream<Optional<R>>` that needs flattening?
5. **Cardinality:** Which stage filters, multiplies, merges, deduplicates, or limits elements?
6. **Order:** Is there `sorted`, `unordered`, `parallel`, or a collector that does not guarantee order?
7. **Missing values:** Are there `null`s, empty groups, or `Optional.empty()`?
8. **Terminal result:** `List`, `Map`, `Optional`, primitive, or `void`?
9. **State:** Does any lambda or collector depend on mutable variables outside the pipeline?
10. **Resources:** Is there an I/O source that must be closed, or a pipeline that stops early?
11. **Numeric types:** Do `int`, `long`, `double`, and `BigDecimal` have the right range and precision?
12. **Tests:** Have you tested an empty source, duplicate elements, empty sub-lists, and reordered data?

### 26.1. Symptoms you can spot right away

| Symptom | Suspect | How to verify |
| --- | --- | --- |
| Unexpected `List<List<T>>` | Used `map` where `flatMap` was wanted | Print/infer types at each stage |
| Fewer elements after `distinct` | Values considered equal by `equals` | Check if duplicate data is expected |
| `Map` has fewer keys than records | `groupingBy` grouped by key | Count elements inside each group too |
| Missing group key after `filter` | No element matched in that group | Decide between absent key vs. value 0 |
| `findFirst` returns empty | No element in search scope | Check filters and order |
| `toMap` throws an exception | Duplicate key without a merge function | Choose the domain-appropriate merge |
| `count()` is right but `peek` prints less | Observation stage may be optimized away | Never use `peek` for required logic |
| `parallel` gives non-deterministic output | Side effects or broken source/collector contract | Remove shared state |
| Stream already closed/operated upon | Earlier terminal operation or close | Create a new Stream or fix lifecycle |
| Running on Java 17 reports no `gather` | API requires Java 24+ | Upgrade JDK or use an alternative |

## 27. Practice Exercises

### Exercise 1: Annotate types at every stage

Given:

```java
orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .toList();
```

Write the Java type **before and after every method call**. Using the sample dataset, record the outer element count after each stage and list the final result.

### Exercise 2: Replacing `map` with `flatMap`

Input `List.of(List.of(1,2), List.of(), List.of(3))`. Compare the results of `map(List::stream).toList()`, `map(list -> list).toList()`, and `flatMap(List::stream).toList()`. How do these cases differ in type, nesting level, and element count?

### Exercise 3: `filter` vs. boolean `map`

Create a `List<Order>` containing both paid and unpaid orders. Compare `filter(Order::paid).count()` with `map(Order::paid).count()`. Why does the second expression not count paid orders, even if the number of `map` callback invocations could be optimized?

### Exercise 4: Cardinality across `distinct` and `limit`

With `["A","A","B","C"]`, compare `distinct().limit(2)` and `limit(2).distinct()`. State in domain terms what each pipeline is doing.

### Exercise 5: Primitive Streams and optional results

From `orders`, compute the total paid amount as a `long` and the average as an `OptionalDouble`. Test with an empty source. Why does `average()` require an Optional type while `sum()` usually does not?

### Exercise 6: Reading a multi-level collector

Infer the type of:

```java
orders.stream().collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.mapping(Order::id, Collectors.toList())
    )
);
```

For orders in region `Bac`, is the value `List<Order>`, `List<String>`, or `Long`? Write a test proving it.

### Exercise 7: Handling absent keys

Compute the number of paid orders by region. Why does `Nam` have no key in the Map? If a dashboard must always display `Bac`, `Nam`, and `Trung`, propose a step to populate missing keys with count 0.

### Exercise 8: Finding why debugging with `peek` fails

A pipeline calls `peek(System.out::println).count()` on a `List` and prints no logs. Explain why this can be valid. Write a way to test the actual element count with an assertion instead of relying on log line count.

### Exercise 9: Testing a Map without relying on print order

Create a Map using `groupingBy` and write a test comparing counts per key. Why shouldn't you compare a Map's printed string representation as if it had a guaranteed default order?

### Exercise 10: Tracing a Gatherer on Java 24

For `Stream.of(1,2,3,4,5).gather(Gatherers.windowSliding(3)).map(List::size).toList()`, write the type at each step and the final result. Try a source with only two elements and explain the short-window behavior.

### Exercise 11: Tracing an I/O source

For `Files.lines(path).filter(...).limit(10).toList()`, identify the type at each stage, the early-termination condition, and where `try-with-resources` must be placed. Why doesn't `toList()` automatically ensure the file is closed?

### Exercise 12: Turn a pipeline into a trace table

Take a pipeline you previously wrote and create a table with columns: stage, Java type, logical element count, shape/nesting, and order. Identify which stage changes only the **type**, which changes **element count**, which changes **result structure**, and which changes **ordering**.

## 28. Self-Check Questions

- What is the difference between a Stream's static type and its runtime data shape?
- Why does `filter(Order::paid)` still return `Stream<Order>` instead of `Stream<Boolean>`?
- When does `map(Order::tags)` return `Stream<List<String>>`?
- How does `flatMap(List::stream)` change type and cardinality?
- How many results can `mapMulti` emit for a single input element?
- Do `distinct`, `sorted`, and `limit` change the element type? Do they change the shape?
- When does `findFirst` return `Optional.empty()`?
- Why does `IntStream.average` return `OptionalDouble`?
- What Map type does `Collectors.groupingBy` with a downstream `counting` collector return?
- Why is a missing group key different from a key with value 0?
- How does the three-argument `reduce` differ from the two-argument `reduce` in accumulator type?
- Why can't a Stream be reused after `count()`?
- Is `peek` an appropriate place for business counting?
- What ordering guarantees does `unordered()` change?
- Why does `Stream.gather(windowFixed(...))` introduce a new `List<T>` layer around elements?
- Why must debugging a pipeline reading `Files.lines` pay attention to `close()`?
- When testing a pipeline, why should you test an empty source, duplicate elements, and empty sub-lists?

## 29. References

Official documentation for checking return types and operation contracts:

1. [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `filter`, `map`, `flatMap`, `mapMulti`, `toList`, `reduce`, `collect`, and terminal operations.
2. [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `mapping`, `counting`, `toMap`, and downstream collectors.
3. [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): primitive conversions, `sum`, `average`, and `summaryStatistics`.
4. [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): handling potentially absent values.
5. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): `ORDERED`, `SIZED`, `SUBSIZED`, and source characteristics.
6. [Java SE 24 — Stream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html): the `gather` method.
7. [Java SE 24 — Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): windowing and stateful intermediate transformations.

**Remember:** When reading a pipeline, always track **two parallel streams of information**: the **Java type** (for example `Stream<Order> → Stream<List<String>> → Stream<String> → List<String>`) and the **data shape** (4 orders → 3 orders → 3 lists → 4 tags → 3 distinct tags). Types catch mistakes at compile time, while shape and invariants catch business-logic bugs at runtime. Use trace tables, explicitly typed variables, and small-input tests; observe sparingly with `peek`, and always check ordering, parallel state, numeric types, and I/O source lifecycles.
