# Sorting in Natural Order with `sorted`

The Java Stream API lets you describe data processing pipelines using declarative operations such as `filter`, `map`, `sorted`, and `collect`. When you need to arrange data in **natural order** without modifying the original dataset, use the zero-argument intermediate operation `sorted()`.

This lesson belongs to the **Ordering, Deduplication, and Slicing** chapter of the **JAVA_STREAM_API** module. It focuses on the contract of `Stream.sorted()`, how Java determines natural order from `Comparable`, the impact of encounter order, behavior with parallel streams, and constraints related to memory and infinite sources. The final sections illustrate combining sorting with `filter`, `map`, `distinct`, `limit`, `reduce`, and `collect`.

## 1. Getting Started with `sorted()`

```java
import java.util.List;

List<Integer> scores = List.of(8, 3, 10, 1, 3);

List<Integer> ascending = scores.stream()
        .sorted()
        .toList();

System.out.println(ascending); // [1, 3, 3, 8, 10]
System.out.println(scores);    // [8, 3, 10, 1, 3]
```

`sorted()` produces a **new stream ordered in ascending sequence** according to the elements' natural order. The original `scores` list is not sorted in place. `toList()` is a terminal operation that pulls the sorted elements to construct the resulting list.

In `Stream<T>`, the operation's signature is:

```java
Stream<T> sorted();
```

Key points to remember:

- `sorted()` is an **intermediate operation**: sorting is performed when a terminal operation actually requests data; calling `sorted()` alone does not immediately create a sorted result list.
- It is a **stateful** operation: to emit the smallest element in general, it must inspect the input elements, and sorting typically has to buffer them.
- Ordering is determined by each element's **natural ordering** via `Comparable`.
- `sorted()` does not remove duplicate elements. To deduplicate, add `distinct()`, though deduplication criteria use `equals`, not `compareTo`.
- `sorted()` sorts **in ascending order** according to natural order; for descending order or custom criteria, use `sorted(Comparator)`, which is outside the primary scope of this lesson.

## 2. Natural Order Comes from `Comparable`

Elements of `Stream<T>` must be comparable with one another via `Comparable`. The `java.lang.Comparable<T>` interface specifies:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

The result of `a.compareTo(b)` is interpreted by the **sign** of the returned integer:

| Result | Meaning |
|---|---|
| Negative | `a` comes before `b` |
| Equal to `0` | `a` and `b` are equal **in sort order** |
| Positive | `a` comes after `b` |

`compareTo` does not have to return only `-1`, `0`, or `1`; any negative or positive integer is valid as long as the comparison contract is satisfied. Do not interpret the absolute value of the result as the distance between two values.

Common types that already have natural ordering:

| Type | Natural order |
|---|---|
| `Integer`, `Long`, `Double` | By numeric value, following the comparison rules defined by each type |
| `String` | By lexicographical comparison of UTF-16 code units, case-sensitive |
| `LocalDate`, `LocalDateTime` | Chronologically by the date/time represented within the type's range |
| `BigDecimal` | By numeric value, not necessarily consistent with `equals` |
| `Enum` | By declaration order of the enum constants |

### 2.1. Integers: Clear Results

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = Stream.of(12, -3, 7, 0, 12)
        .sorted()
        .toList();

System.out.println(numbers); // [-3, 0, 7, 12, 12]
```

The value `12` appears twice, so both are retained. `sorted()` does not change the element count, alter values, or merge equal elements.

### 2.2. Strings: Natural Order Is Not Language-Aware Dictionary Order

```java
List<String> words = Stream.of("banana", "Apple", "apple", "Banana")
        .sorted()
        .toList();

System.out.println(words);
// [Apple, Banana, apple, banana]
```

`String.compareTo` is case-sensitive; the result is not necessarily the dictionary order users expect in Vietnamese or another language. When sorting according to locale rules, accents, and casing, choose a locale-aware comparator such as `Collator` and use the `sorted(Comparator)` overload.

Another pitfall is numeric data stored as `String`:

```java
System.out.println(Stream.of("2", "10", "3").sorted().toList());
// [10, 2, 3] — string comparison, not numeric value

System.out.println(Stream.of("2", "10", "3")
        .map(Integer::parseInt)
        .sorted()
        .toList());
// [2, 3, 10] — integer comparison
```

To sort numerically, convert to a numeric type before calling `sorted()`; invalid strings must be validated or handled when `parseInt` throws `NumberFormatException`.

### 2.3. Natural Order with Dates

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Stream;

List<LocalDate> dates = Stream.of(
        LocalDate.of(2026, 12, 1),
        LocalDate.of(2026, 1, 15),
        LocalDate.of(2025, 12, 31)
).sorted().toList();

System.out.println(dates);
// [2025-12-31, 2026-01-15, 2026-12-01]
```

With `LocalDate`, natural order is chronologically meaningful. Do not use arbitrary formatted strings such as `"31/12/2025"` for chronological sorting, because character order can differ from time order.

## 3. Defining Natural Order for Custom Types

If a class has a single, clear, stable ordering rule, it can implement `Comparable<T>`. For example, a system ranking tasks by ascending priority, then by code to break ties:

```java
import java.util.List;

record Task(int priority, String code) implements Comparable<Task> {
    @Override
    public int compareTo(Task other) {
        int byPriority = Integer.compare(this.priority, other.priority);
        if (byPriority != 0) {
            return byPriority;
        }
        return this.code.compareTo(other.code);
    }
}

List<Task> tasks = List.of(
        new Task(3, "C"),
        new Task(1, "B"),
        new Task(1, "A")
);

List<Task> ordered = tasks.stream().sorted().toList();
System.out.println(ordered);
// [Task[priority=1, code=A], Task[priority=1, code=B], Task[priority=3, code=C]]
```

`Integer.compare(a, b)` is more reliable than `a - b` when comparing integers, because subtraction can overflow:

```java
// Avoid this: subtraction can overflow.
// return this.priority - other.priority;

// Prefer:
return Integer.compare(this.priority, other.priority);
```

> The second `return` line above is an illustrative expression meant for the body of `compareTo`, not a standalone Java program.

### 3.1. The Contract of `compareTo`

A valid natural order must preserve a consistent comparison relation: if `a < b` and `b < c`, then `a < c`; sign symmetry must hold; and two values considered equal under comparison must relate consistently in order to any third value.

Normally, you should strive to make `compareTo(a, b) == 0` consistent with `a.equals(b)`. Java allows certain types to have a natural order inconsistent with `equals` (such as `BigDecimal` with different scales), but this can cause surprises when combining `sorted`, `distinct`, `TreeSet`, or `TreeMap`.

Example:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b)); // 0: equal in numeric value
System.out.println(a.equals(b));    // false: different scales
```

When no single natural order fits all contexts, instead of forcing the class to implement `Comparable`, pass a `Comparator` at the sorting site.

## 4. `sorted()` Is Stateful Yet Part of a Lazy Pipeline

Like other intermediate operations, `sorted()` constructs a pipeline stage; actual work happens when a terminal operation requests results.

```java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(9, 4, 7)
        .sorted();

// No terminal operation yet, so no sorted list has been requested.
System.out.println("Pipeline declared");

System.out.println(pipeline.toList()); // [4, 7, 9]
```

**Stateful** means `sorted()` must generally read the entire finite source and buffer the elements needed to determine the order; in general, it cannot emit elements one by one as soon as they arrive like `map` or `filter`.

Illustrating that sorting must observe values before emitting them:

```java
List<Integer> result = Stream.of(4, 1, 3)
        .peek(n -> System.out.println("Received: " + n))
        .sorted()
        .peek(n -> System.out.println("Emitted: " + n))
        .toList();

System.out.println(result); // [1, 3, 4]
```

In this sequential pipeline, you will typically observe all three `Received` lines before the `Emitted` lines, but **do not use `peek` as business logic**: the Stream API is allowed to optimize away stages when they do not affect the outcome. For example, `count()` on a sized source may skip executing `sorted()` and its surrounding `peek` callbacks.

Once a terminal operation consumes a stream, the same stream instance cannot be reused:

```java
Stream<Integer> values = Stream.of(3, 1, 2).sorted();
System.out.println(values.toList()); // [1, 2, 3]

// values.count(); // Invalid: stream has already been consumed.
```

To obtain another sorted view, create a new stream from the data source.

## 5. Encounter Order, Stability, and Parallel Results

**Encounter order** is the logical order in which elements are encountered in an ordered stream; it does not mean the source is already ascending. For `List.of(3, 1, 2)`, the initial encounter order is `3 → 1 → 2`. After `sorted()`, the stream has an encounter order matching the natural sort order.

```java
List<Integer> ordered = List.of(3, 1, 2)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(ordered); // [1, 2, 3]
```

In this example, elements may be processed on multiple threads, yet `toList()` still returns the list in sorted order.

### 5.1. When Is `sorted()` Stable?

For a **source with an encounter order**, `sorted()` is a **stable** sort: if two elements compare as `0`, they preserve their original relative order.

```java
import java.util.List;

record Player(int rank, String name) implements Comparable<Player> {
    @Override
    public int compareTo(Player other) {
        return Integer.compare(this.rank, other.rank);
    }
}

List<Player> players = List.of(
        new Player(2, "Lan"),
        new Player(1, "Minh"),
        new Player(2, "An")
);

System.out.println(players.stream().sorted().toList());
// [Player[rank=1, name=Minh], Player[rank=2, name=Lan], Player[rank=2, name=An]]
```

The two players with `rank = 2` are considered equal by `compareTo`, so `Lan` stays before `An`. This example intentionally orders by rank and **does not break ties** between names when ranks match; thus `Player`'s natural order is not strictly consistent with `equals`. If business logic requires a total order, add a secondary criterion such as `name`.

For an **unordered source** such as `HashSet.stream()`, `sorted()` still arranges values in natural order, but there is no stability guarantee for elements comparing equal (`0`). If you need reproducible results even when sort keys tie, define an explicit tie-breaker rather than relying on arrival position.

### 5.2. `parallel()` Does Not Break the Sorted Result

```java
List<Integer> result = List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(result); // [1, 2, 3, 4, 5]
```

`parallel()` changes execution mode, not the sorting requirement. However, the terminal operation `forEach` **does not guarantee action execution order** in a parallel pipeline:

```java
List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .forEach(n -> System.out.print(n + " "));
// Do not assume a fixed print order.

System.out.println();

List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

If the goal is to obtain a sorted list, `toList()` or `collect(Collectors.toList())` expresses the intent much more clearly than mutating an external list inside `forEach`. Adding elements to an `ArrayList` from multiple threads risks race conditions.

## 6. Where `sorted()` Sits in the Pipeline Determines Meaning

`filter`, `map`, `sorted`, `distinct`, and `limit` can all be combined, but reordering steps can change the result or the cost.

### 6.1. `filter` Before `sorted`

```java
List<Integer> even = Stream.of(9, 2, 6, 3, 4)
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();

System.out.println(even); // [2, 4, 6]
```

If filtering is independent of order, filtering before sorting is usually beneficial because it reduces the number of elements to sort. For instance, `sorted().filter(...)` also yields `[2, 4, 6]` here, but may have to sort more elements.

### 6.2. `map` Before or After `sorted`?

```java
List<Integer> byOriginal = Stream.of(-5, 2, -1)
        .sorted()
        .map(Math::abs)
        .toList();
System.out.println(byOriginal); // [5, 1, 2]

List<Integer> byAbsolute = Stream.of(-5, 2, -1)
        .map(Math::abs)
        .sorted()
        .toList();
System.out.println(byAbsolute); // [1, 2, 5]
```

Sorting **before** `map` sorts by original values; sorting **after** `map` sorts by transformed values. The two pipelines are equivalent only when the transformation preserves the comparison order.

### 6.3. `sorted().limit(n)` vs `limit(n).sorted()`

```java
List<Integer> firstThreeSmallest = Stream.of(8, 3, 7, 2, 9, 1)
        .sorted()
        .limit(3)
        .toList();
System.out.println(firstThreeSmallest); // [1, 2, 3]

List<Integer> sortFirstThreeSeen = Stream.of(8, 3, 7, 2, 9, 1)
        .limit(3)
        .sorted()
        .toList();
System.out.println(sortFirstThreeSeen); // [3, 7, 8]
```

The first pipeline returns the three smallest values across the **entire source**. The second takes only the **first three elements in encounter order** and then sorts those three. Step order carries different business meaning.

For **infinite** sources like `Stream.generate(...)`, placing `sorted()` before `limit()` normally prevents the program from finishing because `sorted()` requires the entire input. Conversely:

```java
import java.util.concurrent.ThreadLocalRandom;

List<Integer> sample = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(100)
).limit(10).sorted().toList();

System.out.println(sample); // 10 random numbers sorted in ascending order
```

Here `limit(10)` turns the stream into a finite source for `sorted()`. If you must find the smallest N elements from a very large finite source, `sorted().limit(N)` can consume substantial memory; consider a dedicated top-N algorithm.

### 6.4. Sorting and Deduplicating

```java
List<Integer> unique = Stream.of(4, 2, 4, 1, 2)
        .distinct()
        .sorted()
        .toList();

System.out.println(unique); // [1, 2, 4]
```

`distinct()` checks duplicates using `Object.equals`; `sorted()` determines natural order using `Comparable.compareTo`. The two rules are **not identical**:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> values = List.of(
        new BigDecimal("1.0"),
        new BigDecimal("1.00")
);

System.out.println(values.stream().sorted().distinct().count()); // 2
```

Both `BigDecimal` values are numerically equal according to `compareTo`, but `equals` differs due to scale; hence `distinct()` keeps both. Sorting does not change deduplication rules.

### 6.5. Choosing `min`/`max` When Only One Extremum Is Needed

```java
List<Integer> temperatures = List.of(30, 25, 28, 24);

int minimum = temperatures.stream()
        .min(Integer::compareTo)
        .orElseThrow();
System.out.println(minimum); // 24
```

If you only need the smallest element, `min` directly expresses the intent and can avoid sorting the entire stream:

```java
// Correct, but usually unnecessary if taking only one value:
int alsoMinimum = temperatures.stream()
        .sorted()
        .findFirst()
        .orElseThrow();
```

`min` and `max` return `Optional<T>` because the stream may be empty. For primitive numbers, `IntStream.min()`/`max()` and `OptionalInt` are available.

## 7. `sorted()` with Primitive Streams

`IntStream`, `LongStream`, and `DoubleStream` also provide a zero-argument `sorted()`, so you can sort directly without boxing to `Integer`, `Long`, or `Double`.

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] sortedNumbers = IntStream.of(6, 1, 4, 2)
        .sorted()
        .toArray();

System.out.println(Arrays.toString(sortedNumbers)); // [1, 2, 4, 6]
```

```java
double[] measurements = {2.5, -1.0, 3.0};

System.out.println(Arrays.toString(
        Arrays.stream(measurements).sorted().toArray()
)); // [-1.0, 2.5, 3.0]
```

With `DoubleStream`, sorting rules involving `NaN`, `-0.0`, and `+0.0` follow `Double.compare`; do not blindly apply everyday floating-point intuition to these special values.

## 8. Failure Cases: Non-Comparable Elements, `null`, and Unstable Ordering

### 8.1. Elements Not Implementing `Comparable`

```java
record Note(String text) {}

// No natural ordering; when actually comparing Note instances, this can throw
// ClassCastException while the terminal operation consumes the pipeline.
// Stream.of(new Note("B"), new Note("A")).sorted().toList();
```

The `sorted()` overload has no generic constraint in its signature requiring `T` to implement `Comparable`, so errors may surface only **at runtime** when comparison actually occurs. For types without a natural ordering, use `sorted(Comparator)` or design an appropriate `Comparable`.

If elements have mutually incomparable types, such as a mixed `Integer` and `String` set in `Stream<Object>`, you can also encounter a `ClassCastException`.

### 8.2. `null` in the Source

```java
import java.util.Objects;

List<String> safe = Stream.of("b", null, "a")
        .filter(Objects::nonNull)
        .sorted()
        .toList();

System.out.println(safe); // [a, b]
```

Natural ordering of types like `String` does not define whether `null` comes first or last. If `null` must be compared with a real value, `sorted()` can throw `NullPointerException` during comparison. Filter out `null` before sorting, or use `Comparator.nullsFirst(...)`/`Comparator.nullsLast(...)` on the comparator overload to specify an explicit policy.

### 8.3. Elements Whose Sort Key Mutates During Execution

Results can become unpredictable if objects mutate fields used in `compareTo` while the pipeline is sorting. Therefore, avoid mutating source data inside lambdas, avoid modifying sort keys from another thread, and consider mapping to immutable data before sorting.

## 9. Memory Cost, Complexity, and Infinite Sources

`sorted()` is a stateful operation; in general, sorting N elements typically costs around **O(N log N)** time and requires corresponding buffer memory to manage the data. Actual cost depends on implementation, source type, data characteristics, and sequential vs. parallel mode.

Practical guidelines:

1. **Large finite sources:** shrink the input with `filter` before `sorted` when semantics are unchanged; avoid sorting everything just to pick a single extremum.
2. **Unbounded sources:** `Stream.generate(...).sorted().limit(5)` cannot finish sorting an infinite source; use `limit(5).sorted()` if the goal is to sort a finite sample.
3. **Parallel execution:** `parallelStream().sorted()` can sort in parallel, but requires coordination and buffering of elements; overhead may make small datasets slower than sequential execution. Measure performance rather than assuming a win.
4. **Side effects:** do not use `peek`, `map`, or `compareTo` to write to shared state during sorting, as invocation order and counts must not become business requirements.
5. **Resources:** `sorted()` does not open files by itself; however, if the source comes from `Files.lines(path)`, the source stream holds resources and requires `try-with-resources`. Sorting excessively large file data may require an external-memory sort.

When data is already in a `List` and needs to be sorted **in place**, `List.sort` may be more suitable because it avoids allocating a new result list. But when you want to keep the source data intact, `list.stream().sorted().toList()` expresses that intent clearly.

## 10. Complete Runnable Example (Java 17+)

The following standalone program demonstrates that natural sorting does not mutate the source, combines with `filter` and `distinct`, and still produces ordered output on a parallel stream.

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public class NaturalSortedDemo {
    record Job(int priority, String id) implements Comparable<Job> {
        @Override
        public int compareTo(Job other) {
            int result = Integer.compare(priority, other.priority);
            return result != 0 ? result : id.compareTo(other.id);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(7, 3, 1, 7, 5);

        List<Integer> result = source.stream()
                .filter(n -> n >= 3)
                .distinct()
                .sorted()
                .toList();

        System.out.println(result); // [3, 5, 7]
        System.out.println(source); // [7, 3, 1, 7, 5]

        List<Job> jobs = List.of(
                new Job(2, "task-C"),
                new Job(1, "task-B"),
                new Job(1, "task-A")
        );

        System.out.println(jobs.parallelStream().sorted().toList());
        // [Job[priority=1, id=task-A], Job[priority=1, id=task-B],
        //  Job[priority=2, id=task-C]]

        System.out.println(Stream.of("Z", null, "A")
                .filter(Objects::nonNull)
                .sorted()
                .toList()); // [A, Z]

        System.out.println(Stream.of(9, 4, 1, 7)
                .sorted()
                .limit(2)
                .toList()); // [1, 4]
    }
}
```

From Java 16 onward you can use `Stream.toList()`; on Java 8–15, replace `.toList()` with `.collect(Collectors.toList())` and avoid `record` if your Java version does not support it. `Stream.toList()` returns an unmodifiable list, whereas `Collectors.toList()` makes no guarantees about the returned list's exact type or mutability.

## 11. Common Mistakes

| Assumption / snippet | Issue | Appropriate approach |
|---|---|---|
| `list.stream().sorted()` mutates `list` | Streams build pipelines, not in-place list sorting | Call a terminal operation for a result; to mutate in place use `list.sort` |
| `sorted()` removes duplicates automatically | Sorting does not deduplicate | Use `distinct()` when needed, noting `equals` criteria |
| `sorted()` always sorts every `String` in Vietnamese alphabetical order | `String.compareTo` does not follow locale rules | Use `Collator` / an appropriate comparator |
| `sorted().limit(3)` equals `limit(3).sorted()` | One inspects all elements, the other inspects only the first three | Choose based on business meaning |
| `sorted()` works on any object | Elements might not be `Comparable` | Define a natural order or pass a comparator |
| Sorting `null` values without a policy | Comparison may throw `NullPointerException` | Filter nulls or use a null-handling comparator |
| `parallelStream().sorted().forEach(...)` always prints ascending | `forEach` does not guarantee action order | Use `forEachOrdered` or `toList` |
| `sorted().limit(5)` always finishes on an infinite stream | `sorted` requires the entire source | Bound the source before sorting |
| Sorting everything just to get the minimum | Wastes time and memory | Use `min(Comparator)` or `IntStream.min()` |

## 12. Self-Check

1. **What does `Stream.of(4, 1, 4, 2).sorted().toList()` return?** `[1, 2, 4, 4]` because it sorts ascending and does not deduplicate.
2. **What does `Stream.of("2", "10", "3").sorted().toList()` return?** `[10, 2, 3]` because `String.compareTo` does not compare numeric values.
3. **What is the difference between `sorted().limit(2)` and `limit(2).sorted()` on `[9, 3, 1]`?** Results are `[1, 3]` and `[3, 9]`, respectively.
4. **Does `sorted()` modify the source `List`?** No. It creates a stage in the stream; source elements are not sorted in place.
5. **Why can calling `sorted()` on non-`Comparable` objects fail at runtime?** Because `Stream<T>.sorted()` has no compile-time generic bound; natural comparison is attempted at runtime.
6. **Can an unordered `HashSet` source use `sorted()`?** Yes, with comparable elements; natural ordering is established, though stability between elements with `compareTo == 0` is not guaranteed.
7. **Does `parallelStream().sorted().toList()` guarantee ascending output?** Yes, provided elements have a valid natural ordering and the pipeline completes normally.
8. **To find the smallest number, should you use `sorted().findFirst()` or `min()`?** Typically `min()`, as it communicates the goal directly without sorting the entire sequence.

**Rule of thumb:** use `sorted()` when elements have a **well-defined natural order** and the goal is ascending order; use `sorted(Comparator)` when a different rule is needed. Carefully review where `sorted` sits relative to `filter`, `map`, `distinct`, and `limit`, as placement determines both **result semantics** and **processing cost**.
