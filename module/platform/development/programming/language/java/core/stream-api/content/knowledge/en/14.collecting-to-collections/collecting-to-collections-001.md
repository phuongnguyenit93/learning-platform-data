# Collecting into a List with Collectors.toList

In the Java Stream API, intermediate operations such as `filter`, `map`, `sorted`, and `distinct` describe how data is processed. When you need to **collect all output elements of a pipeline into a `List`**, you use the terminal operation `collect(Collectors.toList())`.

This lesson belongs to the **Collecting into Collections** chapter of the **JAVA_STREAM_API** module. It is the transition step from a lazy pipeline to a usable result: after filtering, transforming, or sorting data, we need to collect the elements. Beyond syntax, it is essential to understand the exact contract regarding **order, duplicate values, List type, mutability, parallel execution, and memory cost**. This understanding also serves as the foundation for learning grouping, custom collectors, and other reduction operations.

## 1. Syntax and When Collection Happens

`Collectors.toList()` is a static method of `java.util.stream.Collectors`. It creates a `Collector` used with the terminal operation `Stream.collect(...)`:

```java
List<R> result = source.stream()
    .filter(/* condition */)
    .map(/* transform to R */)
    .collect(Collectors.toList());
```

The letter `R` denotes the element type after the transformations; the result has type `List<R>`. For example, a `Stream<String>` source can be mapped to `Stream<Integer>` and then collected into a `List<Integer>`.

### Complete Java 8 Example

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Collectors;

public class CollectToListDemo {
    public static void main(String[] args) {
        List<String> rawNames = Arrays.asList(
            "  an  ", null, "Binh", "An", "Binh", " Chi "
        );

        List<String> names = rawNames.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .map(name -> name.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(names);    // [BINH, BINH, CHI]
        System.out.println(rawNames); // The source still contains the original values.
    }
}
```

Step-by-step explanation:

1. `rawNames.stream()` creates an ordered Stream based on the source `List`.
2. `filter(Objects::nonNull)` removes `null` values so that `String::trim` does not cause a `NullPointerException`.
3. `map(String::trim)` strips leading/trailing whitespace; `filter` keeps only names with at least three characters.
4. `map(...toUpperCase...)` produces uppercase strings, using `Locale.ROOT` to avoid depending on the default locale.
5. `collect(Collectors.toList())` triggers the pipeline execution and collects the remaining elements into a `List<String>`.

**`collect` is a terminal operation.** Before it is called, `filter` and `map` normally have not traversed the entire source: intermediate steps are evaluated lazily. Once complete, `names` is a List containing the collected results, which can be passed to other methods or read multiple times as a Collection.

The example above does not need to create temporary Lists between `filter` and `map` steps. The Stream processes elements through the pipeline on demand as requested by the terminal operation.

## 2. Which Elements Does the Result Keep?

`Collectors.toList()` collects **every element passed to it by the pipeline**. The collector itself does not filter, deduplicate, or sort. Those responsibilities belong to the intermediate operations.

```java
List<String> input = Arrays.asList("B", "A", "B", "C", "A");

List<String> keepAll = input.stream()
    .collect(Collectors.toList());
// [B, A, B, C, A]

List<String> unique = input.stream()
    .distinct()
    .collect(Collectors.toList());
// [B, A, C]

List<String> sorted = input.stream()
    .sorted()
    .collect(Collectors.toList());
// [A, A, B, B, C]

List<String> firstTwoUniqueSorted = input.stream()
    .distinct()
    .sorted()
    .limit(2)
    .collect(Collectors.toList());
// [A, B]
```

For a `Stream` with an encounter order, `distinct()` keeps the first occurrence of each value. `sorted()` produces a sorted order, and `limit(2)` caps the number of elements forwarded to the collector.

If you only need to check **whether any element matches**, `anyMatch(predicate)` is usually more appropriate and can short-circuit earlier than collecting an entire List. If you only need the **count**, use `count()` to avoid creating an unnecessary List.

### A List Can Contain Duplicate and null Elements

`List` allows duplicate values. `Collectors.toList()` also has no step that automatically removes `null`:

```java
List<String> withNull = Stream.of("A", null, "B")
    .collect(Collectors.toList());

System.out.println(withNull); // [A, null, B]
```

However, an intermediate operation such as `map(String::length)` will throw an exception when encountering `null`. Therefore, define a null-handling policy before transformations that may not accept null.

`distinct()` uses element equality semantics (typically `equals`); for custom object types, the `equals`/`hashCode` implementation can affect deduplication results.

## 3. Encounter Order and Element Order in the List

An important property of `toList` is that it **preserves encounter order if the Stream is ordered**. Encounter order is the order of elements defined by the source or an operation in the pipeline.

| Source or pipeline | Has encounter order? | Consequence when using `Collectors.toList()` |
| --- | --- | --- |
| `ArrayList.stream()` | Yes, by List order | Resulting List preserves order after pipeline steps |
| `LinkedHashSet.stream()` | Yes, by insertion order | Preserves insertion order of remaining elements |
| `TreeSet.stream()` | Yes, by sorted order | Preserves the Set's order |
| `HashSet.stream()` | Not guaranteed | Must not assume a fixed order for the resulting List |
| `stream.sorted()` | Has defined sorted order | Resulting List reflects the sorted order |
| `stream.unordered()` | Drops encounter order constraint | Must not rely on a specific element order |

Example collecting from a `HashSet`:

```java
Set<Integer> values = new HashSet<>(
    Arrays.asList(30, 10, 20)
);

List<Integer> withoutOrderGuarantee = values.stream()
    .collect(Collectors.toList());
// Do not assume the list is [10, 20, 30].

List<Integer> stableOrder = values.stream()
    .sorted()
    .collect(Collectors.toList());
// [10, 20, 30]
```

**A collector does not invent business ordering.** If you want to display a list of users by registration date, you must sort by registration date, and if dates can tie, add a tie-breaker key such as ID. Collecting into a List only preserves the order provided by the pipeline.

## 4. The Contract Does Not Guarantee a Specific or Mutable List

A common mistake is assuming that `Collectors.toList()` **always returns an `ArrayList` that supports `add`/`remove`**. That is not the API contract.

Under the `Collectors.toList()` contract, there is **no guarantee** regarding:

- The concrete List implementation class, such as `ArrayList` or another class.
- Mutability after collection.
- Serializability.
- Thread safety of the returned List.

On common JDKs, the actual result may be a mutable `ArrayList`, but application code **should not depend** on this implementation detail:

```java
List<String> result = Stream.of("A", "B")
    .collect(Collectors.toList());

// Do not write logic that requires the following operation to be supported:
// result.add("C");
```

If you want to **guarantee receiving a mutable `ArrayList`**, explicitly specify the Collection type to create using `Collectors.toCollection`:

```java
ArrayList<String> mutable = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C");
System.out.println(mutable); // [A, B, C]
```

Specifying `ArrayList::new` makes the code's intent clear and adheres to the concrete List class contract. Conversely, if you only need to read the list, you can keep the variable type as `List<T>` and not assume the result is mutable.

## 5. Distinguishing Three Common Ways to Collect a List

Across different Java versions, multiple APIs return a `List` but have different contracts.

| Syntax | Available since | Can the list be modified? | `null` values |
| --- | --- | --- | --- |
| `stream.collect(Collectors.toList())` | Java 8 | **Not guaranteed** | Can collect `null` elements |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Java 8 | Yes, because it returns `ArrayList` | `ArrayList` accepts `null` |
| `stream.collect(Collectors.toUnmodifiableList())` | Java 10 | No | Does not accept `null`; may throw `NullPointerException` |
| `stream.toList()` | Java 16 | No | Can contain `null` |

Each option fits specific situations:

```java
List<String> names = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toList()); // Java 8+

ArrayList<String> editable = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toCollection(ArrayList::new)); // Java 8+

List<String> immutableView = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toUnmodifiableList()); // Java 10+

List<String> unmodifiable = Stream.of("An", "Binh", "Chi")
    .toList(); // Java 16+
```

In this example, `immutableView` and `unmodifiable` both disallow `add`, `remove`, or `set`, but they are **result Lists**, not a way to deeply freeze the contents of each element object.

### Specifically: Collectors.toList and Stream.toList Are Not Equivalent

`Collectors.toList()` is a **Collector** passed into `collect(...)`. `Stream.toList()` is a **terminal operation directly on Stream**, added in Java 16. Although both return a `List`, the difference in mutability is part of the contract:

```java
// Java 16+:
List<String> result = Stream.of("A", "B").toList();

// Always throws UnsupportedOperationException:
// result.add("C");
```

Do not automatically replace `collect(Collectors.toList())` with `toList()` in legacy code if that code still modifies the resulting list; also, Java 8 code cannot compile calls to `Stream.toList()`.

`Collectors.toUnmodifiableList()` and `Stream.toList()` also differ in `null` handling. For example, `Stream.of("A", null).toList()` can contain `null`, whereas `collect(Collectors.toUnmodifiableList())` rejects `null`.

## 6. The Resulting List Is a Collection of References, Not a Deep Copy

When a Stream contains mutable objects, `Collectors.toList()` creates a List containing **references to the elements emitted by the pipeline**. Without using `map` to create new objects, no deep copying of individual elements occurs.

```java
List<StringBuilder> source = Arrays.asList(
    new StringBuilder("A"),
    new StringBuilder("B")
);

List<StringBuilder> result = source.stream()
    .collect(Collectors.toList());

source.get(0).append("!");
System.out.println(result.get(0)); // A!
```

The resulting List and the source List are two structures holding elements, but both reference the exact same first `StringBuilder` object. To obtain independent copies of elements, proactively map to new objects:

```java
List<StringBuilder> copies = source.stream()
    .map(item -> new StringBuilder(item.toString()))
    .collect(Collectors.toList());
```

If the goal is only to collect immutable `String`s, sharing references normally causes no issue with content mutation.

Another point: a `Stream` **does not take a snapshot of a Collection when `stream()` is called**. For a Collection that does not support concurrent modification, mutating the source structure while the pipeline is consuming it can cause `ConcurrentModificationException` or undefined behavior. Do not update the source inside `filter` or `forEach` and expect `collect` to handle it safely.

## 7. Collecting in a Parallel Stream

`collect(Collectors.toList())` uses a **mutable reduction** mechanism. Conceptually, a Collector has components: `supplier` creates a container, `accumulator` adds an element, `combiner` merges partial containers, and `finisher` produces the final result.

When running in parallel, the Stream can split data into branches, accumulate into **partial containers**, and merge them. You do not have to maintain a shared `ArrayList` for multiple threads to call `add` on concurrently.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> squares = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(squares); // [4, 16, 36]
```

Because `numbers` has an encounter order and collection respects that order, the resulting List is still `[4, 16, 36]`. That **does not mean** the `filter`/`map` calls executed sequentially in the order `1, 2, 3, 4, 5, 6`.

Contrast this with the dangerous style:

```java
List<Integer> unsafe = new ArrayList<>();

// Do not use: multiple threads mutating the same ArrayList concurrently.
// numbers.parallelStream().forEach(n -> unsafe.add(n * n));

List<Integer> safe = numbers.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

In the wrong example, `ArrayList` may experience concurrent writes leading to missing/corrupted results or exceptions. In the correct example, the collection framework merges results according to the Collector contract.

**Distinction:** the `collect` process from a parallel stream can be safe thanks to how containers are managed, but **the returned List is not thread-safe by default for concurrent modification**. If you truly need synchronization when using the result, design an appropriate protection layer for your application.

`Collectors.toList()` is not a concurrent collector. For ordered sources, preserving encounter order also incurs combining and positional-preservation costs. Therefore, `parallelStream()` does not promise faster List collection: measure on realistic workloads and transformations.

## 8. Laziness, Memory, and Infinite Sources

`Collectors.toList()` must be able to collect **all output elements of the pipeline** before returning the List. With an infinite source that has no stopping condition, this terminal operation cannot complete under normal evaluation:

```java
// DO NOT run: unbounded source.
// List<Integer> infinite = Stream.iterate(1, n -> n + 1)
//     .collect(Collectors.toList());
```

Limit the source with appropriate intermediate operations:

```java
List<Integer> firstFiveEven = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .collect(Collectors.toList());

System.out.println(firstFiveEven); // [2, 4, 6, 8, 10]
```

`limit(5)` caps the **number of elements that have passed the filter**. If the filter never lets any element through, a downstream `limit` will not help it terminate either. Since Java 9, `takeWhile` can set a stopping condition based on a contiguous prefix of a source with encounter order.

In terms of memory, the List must retain the collected elements: memory usage grows with the number of output elements, not counting the element objects themselves and temporary pipeline data. For large datasets, consider:

- Do you really need to hold **all** elements in RAM? If you only need the count, use `count`; if you need the sum, use `sum`/`reduce`.
- Can you filter, limit, or select only needed fields with `map` **before** collecting?
- If the data source comes from a database or service, should you paginate or load in batches at the source?
- When writing to an external destination, can you process in batches with explicit resource and error handling instead of gathering everything into one large List?

A Stream backed by an external resource such as `Files.lines(path)` needs to be closed with `try-with-resources`. Completing `collect` **does not automatically close** all resource-backed streams:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> nonBlank = lines
        .filter(s -> !s.trim().isEmpty())
        .collect(Collectors.toList());
    // Use nonBlank when needed.
}
```

This example uses `path` of type `Path` along with appropriate `Files`, `Stream`, `List`, and `Collectors` imports. `Files.lines` can throw `IOException`, so calling code must handle or declare the exception.

## 9. Combining with Other Collectors When Requirements Change

`Collectors.toList()` fits the requirement "give me a list of elements after the pipeline". When output requirements change, choosing another Collector can be more accurate and efficient.

| Output requirement | Suggestion |
| --- | --- |
| List of elements | `collect(Collectors.toList())` |
| List with a specific implementation class | `collect(Collectors.toCollection(ArrayList::new))` |
| Set of unique values | `collect(Collectors.toSet())`; do not assume order |
| List per key group | `collect(Collectors.groupingBy(keyFn))` |
| Join strings with a delimiter | `collect(Collectors.joining(", "))` |
| Count elements | `count()` or `Collectors.counting()` when nesting Collectors |

Example getting **Lists grouped by initial letter**:

```java
List<String> words = Arrays.asList("apple", "ant", "banana", "boat");

Map<Character, List<String>> byInitial = words.stream()
    .collect(Collectors.groupingBy(word -> word.charAt(0)));

// Key 'a' maps to [apple, ant]; key 'b' maps to [banana, boat].
// Do not rely on the iteration order of the resulting Map's keys.
```

`groupingBy` collects elements within each group into a List by default. When you want to explicitly specify the downstream collector:

```java
Map<Character, List<String>> explicit = words.stream()
    .collect(Collectors.groupingBy(
        word -> word.charAt(0),
        Collectors.toList()
    ));
```

This example shows that `Collectors.toList()` can also be used **inside a composite Collector**. From the basic goal of collecting a List, learners can progress to grouping, partitioning, and custom collectors.

## 10. Common Mistakes

| Mistake or misconception | Consequence | How to fix |
| --- | --- | --- |
| Using `Collectors.toList()` and assuming the result is `ArrayList` | Depends on implementation details | When `ArrayList` is needed, use `toCollection(ArrayList::new)` |
| Treating `Collectors.toList()` and `Stream.toList()` as identical | Different List mutability contracts and Java version requirements | Check Java version and the required List type |
| Collecting a List then calling `size()` just to count | Creates an unnecessary List | Use terminal `count()` |
| Collecting a List from `HashSet` and relying on order | No encounter order guarantee | Sort first or use an ordered source |
| Wanting deduplication but only calling `toList()` | Duplicate values are still kept | Add `distinct()` before the terminal operation |
| Source contains null and `String::trim` is called | Can throw `NullPointerException` | `filter(Objects::nonNull)` before transformation |
| Using `forEach(list::add)` on an external List in `parallelStream()` | Shared state can suffer race conditions | Use `collect(Collectors.toList())` |
| Assuming the resulting List deep-copies objects | Mutable element changes are visible across references | Create element copies with `map` when needed |
| Collecting all elements from an infinite Stream | Does not terminate or exhausts resources | Set a reachable limit, e.g., `limit(n)` |
| Reusing a Stream after `collect` | The Stream has already been consumed | Create a new Stream from the source for the next query |

## 11. Exercises with Answers

### Exercise 1 — Filter and Collect in Order

Given a list of scores `[5, 9, 7, 9, 3]`, get all scores of `7` or higher, preserving original order and duplicate values.

```java
List<Integer> points = Arrays.asList(5, 9, 7, 9, 3);

List<Integer> selected = points.stream()
    .filter(score -> score >= 7)
    .collect(Collectors.toList());
// [9, 7, 9]
```

**Answer:** `[9, 7, 9]`. `Collectors.toList()` does not automatically remove duplicates and preserves the List's encounter order.

### Exercise 2 — Transform Element Type Before Collecting

Given `["An", "Binh", "Chi"]`, create a `List<Integer>` containing the length of each name.

```java
List<Integer> lengths = Arrays.asList("An", "Binh", "Chi")
    .stream()
    .map(String::length)
    .collect(Collectors.toList());
// [2, 4, 3]
```

**Answer:** `map` converts `Stream<String>` to `Stream<Integer>`, so the result of `collect(Collectors.toList())` is `List<Integer>`.

### Exercise 3 — Needing a List That Supports add

Is the following code guaranteed to work on every Java API-compliant implementation?

```java
List<String> names = Stream.of("A", "B")
    .collect(Collectors.toList());
// names.add("C"); // Not guaranteed by the API.
```

**Answer:** No. If you need to add elements after collecting, explicitly specify `ArrayList`:

```java
ArrayList<String> names = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));
names.add("C");
```

### Exercise 4 — Does Parallel Execution Change Result Order?

```java
List<Integer> input = Arrays.asList(1, 2, 3, 4, 5);

List<Integer> values = input.parallelStream()
    .filter(n -> n % 2 != 0)
    .map(n -> n * 10)
    .collect(Collectors.toList());
```

**Answer:** `[10, 30, 50]`. With an ordered List source, the collector preserves the encounter order of output elements; the lambda **execution** order may still differ.

### Exercise 5 — Choosing a Terminal Operation by Requirement

Given a large `List<String> words`, you only need to know whether any name is empty after `trim`. Should you call `collect(Collectors.toList())`?

```java
boolean hasBlank = words.stream()
    .anyMatch(word -> word.trim().isEmpty());
```

**Answer:** Use `anyMatch` because the required result is a `boolean`; this terminal operation can short-circuit as soon as it finds the first blank string. If the data can contain `null`, define a separate null-handling rule, such as `word == null || word.trim().isEmpty()`.

### Exercise 6 — Empty List

```java
List<Integer> empty = Stream.of(1, 3, 5)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());
```

**Answer:** `empty` is an empty List, not `null`. `collect(Collectors.toList())` collects into a List even when no elements pass through the pipeline.

## Key Takeaways

In **JAVA_STREAM_API**, `collect(Collectors.toList())` is the standard way since Java 8 to turn remaining Stream elements into a `List`. It is a **terminal operation**, preserves duplicate values, and respects the encounter order of ordered sources, but **does not guarantee** the implementation class or mutability of the returned List. If you need a modifiable `ArrayList`, use `Collectors.toCollection(ArrayList::new)`; if you need an unmodifiable List, consider `Stream.toList()` (Java 16+) or `Collectors.toUnmodifiableList()` (Java 10+) with the appropriate null policy. When collecting in parallel, let the Collector manage partial results; when data is large or infinite, account for memory usage and pipeline termination.
