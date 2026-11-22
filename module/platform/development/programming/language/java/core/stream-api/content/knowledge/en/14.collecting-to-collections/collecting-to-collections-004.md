# Choosing the Container Type with `Collectors.toCollection`

In the **Java Stream API**, intermediate operations such as `filter`, `map`, `distinct`, or `sorted` describe a data processing pipeline declaratively and are typically executed *lazily*. When you need to store the processed elements into a collection, you use the terminal operation `collect`.

Familiar options are `Collectors.toList()` or `Collectors.toSet()`. However, if you require returning a specific **`ArrayList`**, preserving appearance order with **`LinkedHashSet`**, sorting with a comparator via **`TreeSet`**, or building an **`ArrayDeque`**, use `Collectors.toCollection(collectionFactory)`.

This lesson belongs to the **Collecting into Collections** chapter, focusing on how to choose the right container and understand the contracts regarding data types, duplicate elements, ordering, mutability, and parallel processing.

## 1. `toCollection` Takes a Factory and Returns a Collector

General signature of the method (Java 8+):

```java
public static <T, C extends Collection<T>> Collector<T, ?, C>
toCollection(Supplier<C> collectionFactory);
```

This is a static method of `java.util.stream.Collectors`. It accepts a `Supplier<C>`: a **zero-argument** function that, when called, must provide a collection to accumulate elements into. The created collection has type `C`, and its elements have type `T`.

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> words = Stream.of("Java", "Stream", "API")
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(words);            // [Java, Stream, API]
System.out.println(words.getClass());  // class java.util.ArrayList
words.add("Collector");                // Allowed because ArrayList is mutable
```

`ArrayList::new` is a *constructor reference* matching `Supplier<ArrayList<String>>`. `toCollection` creates a collector and `stream.collect(...)` uses that collector to terminate the pipeline. The constructed collection is a result you can access after the stream has been consumed.

### Why Pass `ArrayList::new` Instead of `new ArrayList<>()`?

```java
// CORRECT: pass a factory that creates a container when collect needs one.
Collectors.toCollection(ArrayList::new);

// WRONG TYPE: toCollection requires a Supplier, not an instance.
// Collectors.toCollection(new ArrayList<String>());
```

For a parallel pipeline, the collector may invoke the supplier **multiple times** to create independent accumulation containers, and then merge the results. Therefore, the factory must create a fresh container on each invocation. Do not use:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// WRONG EXAMPLE: every call to the supplier returns the exact same list.
List<String> broken = Stream.of("A", "B", "C").parallel()
    .collect(Collectors.toCollection(() -> shared));
```

That incorrect approach can cause parallel accumulators to mutate the same object and produce duplicated merges. Even when running sequentially, the result would depend on any pre-existing contents of `shared`. Always let the factory return a **new empty collection**, such as `ArrayList::new`.

## 2. Collection Selection Table by Requirement

No single collection type fits every problem. Choose according to the business properties that must be guaranteed.

| Factory passed to `toCollection` | Result type | Duplicates | Iteration order of result | Use case |
| --- | --- | --- | --- | --- |
| `ArrayList::new` | `ArrayList<T>` | Retained | Insertion order | List with indexed access that needs modification after collection. |
| `LinkedList::new` | `LinkedList<T>` | Retained | Insertion order | Need `LinkedList` API, such as `Deque`; weigh memory cost. |
| `HashSet::new` | `HashSet<T>` | Deduplicated via `equals/hashCode` | Not guaranteed | Set of unique elements where order is not needed. |
| `LinkedHashSet::new` | `LinkedHashSet<T>` | Deduplicated via `equals/hashCode` | Insertion order | Deduplicate while still iterating in order of appearance. |
| `TreeSet::new` | `TreeSet<T>` | Removes equivalent elements per comparison | Sorted order | Need a set with natural or comparator-based order. |
| `ArrayDeque::new` | `ArrayDeque<T>` | Retained | Front-to-back deque order | Double-ended queue; does not allow `null`. |
| `() -> EnumSet.noneOf(MyEnum.class)` | `EnumSet<MyEnum>` | Deduplicated | Enum declaration order | Efficient set for a specific enum type. |

Two points to distinguish:

1. **Encounter order** is the logical order of input elements, such as the element order of a `List`. Under the `toCollection` contract, elements are accumulated in encounter order if the stream is ordered.
2. **Iteration order** is the order observed when iterating over the collection **after collection**. `TreeSet` iterates by comparator, `HashSet` guarantees no order, and `EnumSet` iterates by enum declaration order. Thus `toCollection` does not mean every resulting collection will be iterated in source order.

## 3. `ArrayList`: An Ordered Mutable List

If you need to keep all elements, including duplicates, and want to add or remove items after collecting, `ArrayList` is a straightforward choice:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("  Java  ", "Stream", "Java", "API");

ArrayList<String> names = raw.stream()
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(names); // [Java, Stream, Java, API]

names.remove("Java");      // Removes the first occurrence of Java
names.add("Collector");
System.out.println(names); // [Stream, Java, API, Collector]
```

`map` and `filter` are lazy intermediate operations; `collect` triggers execution. Because the source is an ordered `List`, the resulting `ArrayList` preserves the order of elements passing the filter. `ArrayList` does not automatically remove duplicates.

**Note on shallow collections:** `toCollection` stores **references to the emitted elements**. If elements are mutable objects and you do not create copies in `map`, mutating an object afterward can be observed through both the source and the collected collection. Creating a new collection does not mean deep-copying each element.

## 4. `LinkedHashSet`: Deduplicate While Preserving Appearance Order

When processing tags or codes from input data, you may need to remove duplicates while keeping first-appearance order:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

List<String> rawTags = Arrays.asList(
    "  Java ", "Stream", "JAVA", "API", "Stream", "API"
);

LinkedHashSet<String> tags = rawTags.stream()
    .map(String::trim)
    .map(String::toLowerCase)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tags); // [java, stream, api]
```

`LinkedHashSet` uses `equals` and `hashCode` to identify duplicate elements and preserves insertion order. By normalizing to lowercase **before** collecting, `"Java"` and `"JAVA"` become the same value.

With a `HashSet`, the result would still contain three tags, but **iteration order is not guaranteed**. If using `Collectors.toSet()`, you also must not rely on order, concrete implementation class, or mutability of the resulting set.

### Is `distinct()` Needed Before Collecting into a Set?

```java
LinkedHashSet<String> a = rawTags.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = rawTags.stream()
    .map(String::trim)
    .distinct()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

In this example, both results have the same elements under `equals`. Because `LinkedHashSet` deduplicates on its own, `distinct()` is usually unnecessary if the **sole goal** is deduplication before inserting into a Set. `distinct` is a stateful intermediate operation and can add extra work; only include it if required for semantics or subsequent pipeline steps.

However, if a `map` **after** `distinct` transforms multiple distinct values into the same label, the final Set still determines uniqueness of the result.

## 5. `TreeSet`: Sorted Order and Comparator-Based Duplicate Rules

When you need a unique collection iterated in ascending order, use `TreeSet`:

```java
import java.util.Arrays;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<Integer> numbers = Arrays.asList(8, 3, 8, 1, 5).stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(numbers);        // [1, 3, 5, 8]
System.out.println(numbers.first()); // 1
System.out.println(numbers.last());  // 8
```

`TreeSet` uses **natural ordering** if no comparator is provided. Elements must be suitably comparable; otherwise, adding elements can throw `ClassCastException`. With comparators that do not support `null`, passing a `null` element can cause `NullPointerException`.

### Passing a Comparator via a Lambda Factory

```java
import java.util.Comparator;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Comparator<String> byLengthThenText = Comparator
    .comparingInt(String::length)
    .thenComparing(Comparator.naturalOrder());

TreeSet<String> names = Stream.of("Bob", "Ana", "Al", "Ana", "Zoe")
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(byLengthThenText)
    ));

System.out.println(names); // [Al, Ana, Bob, Zoe]
```

Because `TreeSet` has no zero-argument constructor for a **specific comparator**, the appropriate factory is `() -> new TreeSet<>(byLengthThenText)`. Each factory invocation must create a separate `TreeSet` while using the same comparison rule.

**Important note:** In a `TreeSet`, two elements are considered duplicates if the comparator returns **0**, even if their `equals` returns `false`. For example:

```java
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

TreeSet<String> words = Stream.of("Java", "JAVA", "API")
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(words.size()); // 2: Java and JAVA are equivalent per the comparator
```

When using `TreeSet` as a `Set`, the comparator **should be consistent with `equals`** if you want to adhere fully to the general Set contract. If the business requirement truly is case-insensitive merging, understand the equivalence rule in use and which representative value remains.

## 6. Specialized Collections: `ArrayDeque` and `EnumSet`

### Collecting into a Deque for Queue Processing

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Deque<String> jobs = Stream.of("parse", "validate", "save")
    .collect(Collectors.toCollection(ArrayDeque::new));

System.out.println(jobs.peekFirst()); // parse
System.out.println(jobs.pollFirst()); // parse, and removes it from the deque
System.out.println(jobs.peekFirst()); // validate
```

`ArrayDeque` fits head/tail queue operations. It retains duplicates, iterates from front to back, **does not accept `null`**, and is not designed for multiple threads concurrently modifying the same instance. When genuine concurrent workflows are needed, choose an appropriate data structure and coordination mechanism rather than simply adding `parallel()` to a collection pipeline.

### Collecting Enum Values

```java
import java.util.EnumSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PermissionExample {
    enum Permission { READ, WRITE, EXECUTE }

    public static void main(String[] args) {
        EnumSet<Permission> permissions =
            Stream.of(Permission.WRITE, Permission.READ, Permission.WRITE)
                .collect(Collectors.toCollection(
                    () -> EnumSet.noneOf(Permission.class)
                ));

        System.out.println(permissions); // [READ, WRITE]
    }
}
```

`EnumSet.noneOf(Permission.class)` creates a specialized empty set for the `Permission` type; `Permission.class` is a required parameter, so `EnumSet::noneOf` cannot be used directly as a zero-argument `Supplier`. `EnumSet` iterates in **enum declaration order**, not the order elements are fed by the stream. It also does not support `null` elements.

## 7. How Does `toCollection` Differ from `toList`, `toSet`, and `Stream.toList`?

Methods that look similar have different contracts:

| API | Promised result type | Can the resulting collection be modified? | Order and duplicate elements |
| --- | --- | --- | --- |
| `collect(Collectors.toCollection(ArrayList::new))` | Exact `ArrayList<T>` | Yes, per the `ArrayList` contract | Retains duplicates, iterates in encounter order of an ordered source. |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | Exact `LinkedHashSet<T>` | Yes | Deduplicates, iterates in insertion order. |
| `collect(Collectors.toList())` | `List<T>`, implementation class not promised | **Not guaranteed** mutable or immutable | Retains duplicates and source order when encounter order exists. |
| `collect(Collectors.toSet())` | `Set<T>`, implementation class not promised | **Not guaranteed** mutable or immutable | Deduplicates; collector imposes no ordering constraint. |
| `stream.toList()` (Java 16+) | Unmodifiable `List<T>` | No; `add`, `set`, `remove` throw `UnsupportedOperationException` | Retains duplicates, preserves encounter order if present. |
| `collect(Collectors.toUnmodifiableList())` (Java 10+) | Unmodifiable `List<T>` | No | Retains duplicates, preserves encounter order; rejects `null` elements. |

Example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<Integer> editable = Stream.of(1, 2, 3)
    .collect(Collectors.toCollection(ArrayList::new));
editable.add(4); // Valid

List<Integer> unspecified = Stream.of(1, 2, 3)
    .collect(Collectors.toList());
// Do not write code assuming unspecified is an ArrayList.

// Java 16+
List<Integer> readOnly = Stream.of(1, 2, 3).toList();
// readOnly.add(4); // UnsupportedOperationException
```

Choosing `toCollection` should stem from the **required output contract**, not assumptions about a current JDK's implementation class. If you only need a `List<T>` for reading, `toList()` or `Collectors.toList()` is usually sufficient; if you specifically need an `ArrayList`, `ArrayDeque`, or `TreeSet`, pass an explicit factory.

## 8. Encounter Order, Parallelism, and Mutable Containers

`toCollection` creates a collector that accumulates into a mutable collection. That does **not** mean parallel tasks should all write to one shared collection.

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

ArrayList<Integer> values = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(values.size());        // 10000
System.out.println(values.get(0));        // 0
System.out.println(values.get(9_999));    // 9999
```

`IntStream.range` has a defined encounter order. The `toCollection` collector accumulates in encounter order, so the final list still carries the order `0, 1, ..., 9999` when the pipeline preserves order. During parallel execution, intermediate containers may be created and combined in various ways; **do not rely on lambda invocation order**, how many times the supplier is called, or thread scheduling.

Principles to follow:

- A factory such as `ArrayList::new` or `LinkedHashSet::new` must create an **independent container**; never return a shared list from an outer variable.
- `map`/`filter` steps should **not interfere with the source** and **not depend on shared mutable state**, especially when parallel.
- `toCollection` is not a `CONCURRENT` collector: safe accumulation comes from how the framework organizes separate containers and merges them, not from every collection being thread-safe.
- Choosing `TreeSet` or `LinkedHashSet` has different memory and computation costs than `ArrayList`. Using `parallel()` does not guarantee faster execution; when performance matters, measure on real data.
- If `unordered()` is called or the source inherently lacks an encounter order, do not expect the resulting `ArrayList` or `LinkedHashSet` to have a stable order across runs.

A dangerous example is introducing side effects into a mapper:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// WRONG EXAMPLE: appending to an external collection from multiple threads.
List<String> result = Stream.of("A", "B", "C").parallel()
    .map(value -> {
        shared.add(value);
        return value;
    })
    .collect(Collectors.toCollection(ArrayList::new));
```

`shared.add` can run concurrently and is not a reliable way to collect all elements. The result you need is the collection returned by `collect`; no external container outside the pipeline is needed.

## 9. Easily Overlooked Limitations

### A Stream Can Only Be Consumed Once

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Stream<String> stream = Stream.of("A", "B", "A");
ArrayList<String> list =
    stream.collect(Collectors.toCollection(ArrayList::new));

// Invalid: the same Stream has already been consumed.
// LinkedHashSet<String> set =
//     stream.collect(Collectors.toCollection(LinkedHashSet::new));
```

If you need two collection types from the same existing `List`, create **two new streams from the List**. If the source can only be traversed once, such as `Files.lines`, consider whether you truly need to buffer the data or if results can be aggregated with an appropriate collector.

### Infinite Sources Require a Limit

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> five = Stream.generate(() -> "sample")
    .limit(5)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(five.size()); // 5
```

`collect(toCollection(...))` typically must traverse the entire input. If a source is infinite with no stopping condition or finite limit, collection **cannot complete**. Even a finite source can cause high memory pressure because all elements must be retained.

### A Collection May Be Mutable Yet Unable to Hold `null` Elements

`ArrayList` supports `null`, whereas `ArrayDeque` and `EnumSet` do not allow it; `TreeSet` with natural ordering also rejects `null`. Place `filter(Objects::nonNull)` before `collect` when that matches your data policy:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

ArrayDeque<String> queue = Arrays.asList("A", null, "B").stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toCollection(ArrayDeque::new));

System.out.println(queue); // [A, B]
```

Do not silently drop `null` if missing values must raise an error or be saved for separate handling.

## 10. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Passing an already-created collection to `toCollection` | Signature mismatch; API requires a `Supplier`. | Use `ArrayList::new` or `() -> new TreeSet<>(comparator)`. |
| Factory returns a shared mutable collection | Violates accumulation contract; prone to races or duplicate merges. | Return an independent instance on every supplier call. |
| Using `toList()` and assuming you can call `add` | `Stream.toList()` (Java 16+) returns an unmodifiable list. | Use `toCollection(ArrayList::new)`. |
| Using `toSet()` and assuming source iteration order | `toSet()` promises neither order nor concrete class. | Use `toCollection(LinkedHashSet::new)` on an ordered source. |
| Using `TreeSet` whose comparator only checks one non-unique field | Distinct elements may be treated as duplicates. | Define equivalence rules or add a tie-breaker to the comparator. |
| Collecting `null` elements into `ArrayDeque` | Throws `NullPointerException`. | Handle missing data before collecting. |
| Using `collect` to gather an entire infinite stream | Does not terminate or exhausts resources. | Limit input or choose a finite aggregation. |
| Adding elements to an external collection inside `parallel().map(...)` | Side effects suffer contention and are unreliable. | Let `collect` manage accumulation and return the result. |

## 11. Practice Exercises

**Exercise 1 — Modifiable List.** Create `Stream.of("a", "b", "a")`, collect with `toCollection(ArrayList::new)`, then call `add("c")`. Predict the result `[a, b, a, c]` and explain why you should not assume `Stream.toList()` also allows modification.

**Exercise 2 — Ordered Deduplication.** Given `["Java", "Stream", "Java", "API", "Stream"]`. Collect into `LinkedHashSet` and `TreeSet`, comparing iteration order as well as deduplication rules. Explain why `HashSet` is unsuitable when first-appearance order must be preserved.

**Exercise 3 — Comparator.** Collect `Stream.of("apple", "pear", "kiwi", "fig")` into a `TreeSet` using a comparator that only checks string length. Predict why `"pear"` and `"kiwi"` cannot both coexist in that set. Fix the comparator to use alphabetical order as a tie-breaker.

**Exercise 4 — EnumSet.** Define `enum Status { NEW, RUNNING, DONE }`. From the stream `DONE, NEW, DONE`, create an `EnumSet<Status>` via `toCollection(() -> EnumSet.noneOf(Status.class))`; verify the resulting set and its iteration order.

**Exercise 5 — Parallel.** Collect `IntStream.range(0, 10000).parallel().boxed()` into an `ArrayList` using a factory. Verify the count and the first/last elements. Try using `unordered()` and explain why you should not test the list against a fixed expected order.

**Key takeaway:** `Collectors.toCollection` lets you **specify the exact collection to create** using a `Supplier`. Choose the container type based on requirements for ordering, duplicates, mutability, null handling, comparator semantics, and cost. When collecting in parallel, use a factory that creates fresh containers and let the collector manage merging; when the source is infinite, limit the number of elements before storing everything in memory.
