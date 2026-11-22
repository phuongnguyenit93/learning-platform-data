# Collecting into a `Set` and Understanding Deduplication Semantics

In the Java Stream API, `collect` is a terminal operation that turns a declarative pipeline into a concrete result. When a problem requires **unique values**, `Set` is the commonly chosen data structure. However, "unique" must be understood according to the exact equality contract of each `Set` type; element ordering, mutability, and `null` handling also depend on how collection is performed.

This lesson belongs to the **Collecting into Collections** chapter of the **JAVA_STREAM_API** module. It focuses on `Collectors.toSet()`, `Collectors.toCollection(...)`, `Collectors.toUnmodifiableSet()`, `equals`/`hashCode` rules, choosing between `HashSet`, `LinkedHashSet`, and `TreeSet`, as well as the difference between `distinct()` and collecting into a `Set`. The examples combine `filter`, `map`, `collect`, `groupingBy`, and parallel streams, while highlighting constraints around state, resources, and performance.

## 1. Collecting into a `Set` with `Collectors.toSet()`

Suppose an input list contains duplicate skill codes:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> skills = List.of("Java", "SQL", "Java", "Git", "SQL");

Set<String> unique = skills.stream()
        .collect(Collectors.toSet());

System.out.println(unique.size());                  // 3
System.out.println(unique.contains("Java"));        // true
System.out.println(unique.contains("SQL"));         // true
System.out.println(unique.contains("Git"));         // true
```

The input has five elements, but the resulting `Set` only has three distinct values. **Do not assume any specific order when printing `unique`**: `Collectors.toSet()` guarantees neither the concrete implementation type nor the iteration order.

The pipeline has three parts:

1. `skills.stream()` creates a source from the list, with an encounter order based on element position.
2. Optional intermediate operations such as `filter` or `map` describe filtering and transformations.
3. `collect(Collectors.toSet())` consumes the stream, accumulates elements into a `Set`, and eliminates duplicates according to the rules of the created `Set`.

If you need to combine other operations:

```java
Set<String> normalized = List.of(" Java ", "SQL", "Java", " Git ").stream()
        .map(String::trim)
        .map(String::toLowerCase)
        .collect(Collectors.toSet());

System.out.println(normalized.equals(Set.of("java", "sql", "git"))); // true
```

This is how you deduplicate **after normalization**. If two values differ only by whitespace or letter case and the application wants to treat them as the same code, normalize them before collecting.

### 1.1. What Does `toSet()` Guarantee, and What Does It Not Guarantee?

| Property | Contract of `Collectors.toSet()` |
|---|---|
| Element count | Each equivalent value per the `Set`'s rules appears at most once |
| Return type | `Set<T>` |
| Concrete implementation class | **Not guaranteed**; do not assume it is always `HashSet` |
| Element iteration order | **Not guaranteed**, even when the source is an ordered `List` |
| Mutability of result | **Not guaranteed** by the collector contract |
| Serializability or thread safety | **Not guaranteed** |
| Collector characteristics | `UNORDERED`; no promise to preserve encounter order |

If the application requires a specific `Set` type or a specific ordering policy, choose `Collectors.toCollection(supplier)` instead of relying on an implementation detail of `toSet()`.

## 2. What Does "Duplicate" Mean? `equals` and `hashCode`

For hash-based `Set` implementations such as `HashSet` and `LinkedHashSet`, uniqueness relies on the elements' `equals` and `hashCode`. Two objects with visually similar data are not necessarily considered equal.

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> names = List.of("Java", "Java", "java").stream()
        .collect(Collectors.toSet());

System.out.println(names.size()); // 2
```

`String.equals` is case-sensitive: `"Java"` equals `"Java"`, but does not equal `"java"`. Collecting into a `Set` **does not automatically normalize** data.

### 2.1. `equals` and `hashCode` Must Be Consistent

For elements used in a hash-based `Set`, the key contract is:

- `equals` must be reflexive, symmetric, transitive, and consistent when the compared state does not change.
- If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must hold.
- Two objects with the same `hashCode` are **not necessarily** equal; hash collisions are allowed.
- If you override `equals`, you must override `hashCode` accordingly; otherwise, `HashSet` may fail to detect duplicates properly.

A `record` by default has `equals` and `hashCode` considering **all components**:

```java
record Employee(long id, String name) {}

Set<Employee> employees = List.of(
        new Employee(1, "An"),
        new Employee(1, "An"),
        new Employee(1, "An Nguyen")
).stream().collect(Collectors.toSet());

System.out.println(employees.size()); // 2
```

In this example, the first and second records are equal because all components match. The third record has a different `name`, so it remains a separate element despite sharing the same `id`.

**Deduplication rules are domain rules**, not just a matter of calling `toSet()`. If you want to define "two employees with the same id are the same person", you must express or implement that criterion explicitly.

### 2.2. Customizing Semantics with an Identity-Keyed Object

Consider a data type whose identity is determined solely by `id`:

```java
import java.util.Objects;

final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }

    long id() { return id; }
    String name() { return name; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Customer customer)) return false;
        return id == customer.id;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(id);
    }

    @Override
    public String toString() {
        return "Customer[" + id + ", " + name + "]";
    }
}
```

With this type, `new Customer(1, "An")` and `new Customer(1, "An updated")` are considered equal by `id`. Collecting with `toSet()` will not keep both. **Do not assume that either the old or new record is always the one retained** by an unordered collector, especially in a parallel stream.

In practice, only override `equals`/`hashCode` by `id` if that matches the class's identity semantics everywhere. If the problem only requires counting unique `id`s, a clearer approach is:

```java
Set<Long> ids = List.of(
        new Employee(1, "An"),
        new Employee(1, "An updated"),
        new Employee(2, "Binh")
).stream()
 .map(Employee::id)
 .collect(Collectors.toSet());

System.out.println(ids.equals(Set.of(1L, 2L))); // true
```

### 2.3. Do Not Mutate Hash Keys While an Element Is in a `Set`

If `equals` and `hashCode` depend on a mutable property, modifying that property after inserting the element into a `HashSet` can cause `contains` or `remove` to behave unpredictably, because the element was placed into a bucket based on its old hash. Prefer immutable keys: `record`, `final` fields, or data that is not mutated while the element belongs to the set.

## 3. Choosing `HashSet`, `LinkedHashSet`, or `TreeSet`

`Set` is an interface. The construction and rules of the concrete structure determine ordering and duplicate detection strategy:

| `Set` type | Uniqueness rule | Iteration order | Typical use case |
|---|---|---|---|
| `HashSet` | `equals`/`hashCode` | Not guaranteed | Value lookup, membership testing |
| `LinkedHashSet` | `equals`/`hashCode` | Insertion order | Deduplicating while preserving first-seen order |
| `TreeSet` | Comparison via `compareTo` or `Comparator`; `compare(...) == 0` means duplicate | Sorted order | Unique values ordered ascending or by custom rule |

`Collectors.toCollection` lets you **specify the collection supplier**:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.TreeSet;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> source = List.of(4, 2, 4, 1, 3, 2);

HashSet<Integer> hash = source.stream()
        .collect(Collectors.toCollection(HashSet::new));

LinkedHashSet<Integer> insertion = source.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

TreeSet<Integer> sorted = source.stream()
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(insertion); // [4, 2, 1, 3]
System.out.println(sorted);    // [1, 2, 3, 4]
System.out.println(hash.size()); // 4; do not rely on print order
```

With an ordered `List` stream source, `LinkedHashSet` records the **first-time** insertion order. `TreeSet` places elements in the natural order of `Integer`. `HashSet` has no ordering contract, even if printing it on one JDK happens to look consistent.

### 3.1. Why Is `Collectors.toCollection(LinkedHashSet::new)` Different from `Collectors.toSet()`?

```java
List<String> events = List.of("open", "save", "open", "close", "save");

Set<String> firstSeenOrder = events.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(firstSeenOrder); // [open, save, close]
```

This is the right choice when business logic needs "unique events in order of first appearance". `Collectors.toSet()` only guarantees uniqueness per `Set`; it is an `UNORDERED` collector and makes no promise about appearance order.

For a stream whose encounter order was dropped with `unordered()` or an inherently unordered source like `HashSet`, `LinkedHashSet` still has an insertion order, but it does not **restore** an encounter order the source never provided. If you want a total order determined by values, sort or use `TreeSet` with an appropriate comparator.

### 3.2. `TreeSet` Has a Different Notion of "Duplicate"

`TreeSet` uses comparison results to decide element equivalence. For example, with a case-insensitive comparator:

```java
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<String> tokens = Stream.of("Java", "JAVA", "sql", "SQL")
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
        ));

System.out.println(tokens.size()); // 2
```

The two strings `"Java"` and `"JAVA"` differ under `String.equals`, but the comparator returns `0`, so `TreeSet` treats them as an equivalence group. Which representative element is retained depends on which was added first; do not interpret the result as "picking the most canonical casing". If you need a canonical form, use `map(String::toLowerCase)` or an explicit normalization rule before collecting.

For a sorted set, the comparator or natural ordering **should be consistent with `equals`** if you want to fully honor the general `Set` contract. Using an inconsistent comparator may be valid for a specific sorting need, but can cause surprises when comparing, exchanging, or processing different `Set` types.

A classic example:

```java
import java.math.BigDecimal;
import java.util.TreeSet;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0

Set<BigDecimal> hashBased = Stream.of(a, b)
        .collect(Collectors.toCollection(HashSet::new));
Set<BigDecimal> treeBased = Stream.of(a, b)
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(hashBased.size()); // 2
System.out.println(treeBased.size()); // 1
```

This is why you must determine the exact **duplication criterion** before choosing a `Set` type.

## 4. Are `distinct()` and `collect(toSet())` the Same?

Both relate to deduplication, but at **two different stages**:

| Characteristic | `distinct()` | `collect(Collectors.toSet())` |
|---|---|---|
| Operation type | Intermediate, stateful | Terminal |
| Data type after operation | Remains `Stream<T>` | Becomes `Set<T>` |
| Can continue with `map`, `filter`? | Yes | No, the stream is consumed |
| Duplication criterion | `Object.equals` | Determined by the `Set` used by the collector; for hash-based sets, `equals`/`hashCode` |
| Order with encounter-ordered source | Keeps the **first** appearing element | Order not guaranteed |
| Usage context | Deduplicate mid-pipeline before subsequent steps | Obtain a unique result set at the end of a pipeline |

Example:

```java
List<String> labels = List.of("A", "B", "A", "C", "B");

List<String> orderedUnique = labels.stream()
        .distinct()
        .toList();
System.out.println(orderedUnique); // [A, B, C]

Set<String> uniqueSet = labels.stream()
        .collect(Collectors.toSet());
System.out.println(uniqueSet.size()); // 3; order is not guaranteed
```

When a stream **has an encounter order**, `distinct()` retains the first element appearing in each equal group. If you need the final result in a `Set` while preserving first-seen order:

```java
LinkedHashSet<String> orderedSet = labels.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
System.out.println(orderedSet); // [A, B, C]
```

Adding `distinct()` before `toCollection(LinkedHashSet::new)` is not required: `LinkedHashSet` already deduplicates on its own. However, `distinct()` is useful if you must deduplicate **before a subsequent intermediate operation** or if you need an ordered result list.

### 4.1. `sorted()` Before `toSet()` Does Not Guarantee the `Set`'s Order

```java
Set<Integer> result = List.of(4, 1, 3, 2).stream()
        .sorted()
        .collect(Collectors.toSet());

System.out.println(result.size()); // 4
// Do not assert that iteration order is [1, 2, 3, 4].
```

If you need a `Set` in ascending order, use:

```java
TreeSet<Integer> sortedUnique = List.of(4, 1, 3, 2).stream()
        .collect(Collectors.toCollection(TreeSet::new));
System.out.println(sortedUnique); // [1, 2, 3, 4]
```

If you need a list in ascending order without duplicates, use `stream().distinct().sorted().toList()`. Choose the result structure based on how the caller will use the data.

## 5. Which Record Is Kept on Key Collisions?

A practical question is: "If two objects are equal by `equals` but contain different data, which one is kept?" With `Collectors.toSet()`, neither order nor the representative element is guaranteed. Which record is retained can depend on the collector, data splitting, or processing order.

For a source with an encounter order where you require the **first-appearing record under `equals`**, you can use `distinct()` and then collect into a `List`:

```java
List<Customer> customers = List.of(
        new Customer(1, "An old"),
        new Customer(1, "An new"),
        new Customer(2, "Binh")
);

List<Customer> firstByEquality = customers.stream()
        .distinct()
        .toList();

System.out.println(firstByEquality);
// [Customer[1, An old], Customer[2, Binh]]
```

In this example, `Customer` from section 2.2 has `equals` based on `id`; with an ordered `List.stream()`, `distinct()` keeps the first representative. **Do not replace this with `unordered().distinct()`** if the "first" criterion matters.

If the duplication criterion is a single field while the class's `equals` considers all fields, `distinct()` cannot infer "duplicate by id" on its own. You can use `toMap` with an explicit merge function:

```java
import java.util.LinkedHashMap;
import java.util.Map;

List<Employee> source = List.of(
        new Employee(1, "An old"),
        new Employee(1, "An new"),
        new Employee(2, "Binh")
);

Map<Long, Employee> firstById = source.stream()
        .collect(Collectors.toMap(
                Employee::id,
                employee -> employee,
                (first, ignored) -> first,
                LinkedHashMap::new
        ));

System.out.println(firstById.get(1L)); // Employee[id=1, name=An old]
```

This example uses an ordered source; the merge function `(first, ignored) -> first` specifies the selection policy based on element encounter order. `LinkedHashMap` preserves key insertion order in the result. If business logic requires the **latest record by timestamp**, define an explicit timestamp field and comparison rule; do not infer it from an object "coming later" in an unordered source.

## 6. Can the Result Be Modified or Not?

Some APIs produce immutable or unmodifiable `Set`s; this requirement is independent of deduplication.

| Creation approach | Key contract | Java version |
|---|---|---|
| `Collectors.toSet()` | Does not guarantee mutability or concrete type | Java 8+ |
| `Collectors.toCollection(HashSet::new)` | Result is a mutable `HashSet` | Java 8+ |
| `Collectors.toCollection(LinkedHashSet::new)` | Result is a mutable `LinkedHashSet` | Java 8+ |
| `Collectors.toUnmodifiableSet()` | Result cannot be modified; rejects `null` | Java 10+ |
| `Set.copyOf(collection)` | Unmodifiable copy; rejects `null` | Java 10+ |
| `Set.of(elements...)` | Unmodifiable; `null` and duplicates throw errors | Java 9+ |

### 6.1. `Collectors.toUnmodifiableSet()`

```java
Set<String> permissions = Stream.of("READ", "WRITE", "READ")
        .collect(Collectors.toUnmodifiableSet());

System.out.println(permissions.size()); // 2

// permissions.add("DELETE"); // Throws UnsupportedOperationException at runtime.
```

Do not confuse `toUnmodifiableSet()` with `toSet()`: the first API **guarantees unmodifiability**, while the second does not. `toUnmodifiableSet()` is also an unordered collector, and when equal elements are supplied, it makes no promise as to which representative object among equal elements is retained.

```java
// May throw NullPointerException because the result does not allow null:
// Set<String> invalid = Stream.of("A", null)
//         .collect(Collectors.toUnmodifiableSet());
```

If `null` needs to be removed, make that explicit in the pipeline:

```java
import java.util.Objects;

Set<String> safe = Stream.of("A", null, "B", "A")
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(safe.equals(Set.of("A", "B"))); // true
```

### 6.2. `Set.of` vs. `Set.copyOf`

```java
Set<String> fixed = Set.of("A", "B");
Set<String> copy = Set.copyOf(List.of("A", "B", "A"));

System.out.println(fixed.size()); // 2
System.out.println(copy.size());  // 2

// Set.of("A", "A"); // IllegalArgumentException: duplicate element.
```

`Set.of` **rejects duplicate elements**, whereas `Set.copyOf` **deduplicates** from the input collection. For distinct objects where `equals` returns `true`, `Set.copyOf` makes no guarantee about which specific representative is kept. Both set types forbid modification and reject `null`.

### 6.3. Preserving Insertion Order While Disallowing Modification

If you need a resulting `Set` that iterates in first-seen order and cannot be modified by callers, you can build a new `LinkedHashSet` and return an unmodifiable wrapper:

```java
import java.util.Collections;
import java.util.LinkedHashSet;

Set<String> orderedReadOnly = List.of("B", "A", "B", "C").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(LinkedHashSet::new),
                Collections::unmodifiableSet
        ));

System.out.println(orderedReadOnly); // [B, A, C]
// orderedReadOnly.add("D"); // UnsupportedOperationException.
```

Here the collector creates a fresh `LinkedHashSet` to which no external reference is held, then returns an unmodifiable wrapper. **This is not deep immutability**: if elements are mutable objects, their internal state can still change; therefore, collect immutable data where appropriate.

## 7. Handling `null` Before Collecting

`null` is not a valid business value in many systems. Do not rely on `Collectors.toSet()` currently creating a `HashSet` that accepts `null`: the API makes no guarantee about the result type. `Collectors.toUnmodifiableSet()` rejects `null`; a `TreeSet` with natural ordering cannot compare `null` in the normal way either.

```java
Set<String> labels = Stream.of("Java", null, "SQL", "Java")
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

System.out.println(labels.equals(Set.of("Java", "SQL"))); // true
```

If `null` has a distinct meaning (such as "unclassified"), map it to an explicit domain label or value:

```java
Set<String> categories = Stream.of("A", null, "B")
        .map(value -> value == null ? "UNCLASSIFIED" : value)
        .collect(Collectors.toSet());

System.out.println(categories.contains("UNCLASSIFIED")); // true
```

This decision belongs to business requirements: **dropping `null`** and **replacing `null` with a meaningful value** are two different behaviors.

## 8. Collecting into a `Set` in a Parallel Stream

```java
Set<Integer> unique = List.of(1, 2, 2, 3, 1, 4)
        .parallelStream()
        .collect(Collectors.toSet());

System.out.println(unique.equals(Set.of(1, 2, 3, 4))); // true
```

`Collectors.toSet()` can be used with `parallelStream()`. The Stream framework handles creating thread-local accumulation containers and combining partial results according to the collector contract. That **does not mean the returned `Set` is thread-safe**, nor does it mean you should share an external `HashSet` across multiple threads.

### 8.1. Mistake: Using `forEach` to Add Manually to a Shared `HashSet`

```java
import java.util.HashSet;

Set<Integer> target = new HashSet<>();

// Not safe:
// List.of(1, 2, 3, 4).parallelStream().forEach(target::add);
```

`HashSet` does not guarantee thread-safety for concurrent additions from multiple threads. Data can suffer race conditions, lost elements, or corrupted internal state. Use `collect(Collectors.toSet())` so the framework manages accumulation.

### 8.2. `UNORDERED` Does Not Mean `CONCURRENT`

These are two distinct concepts:

- **`UNORDERED`**: the collector does not promise any element ordering in the result.
- **`CONCURRENT`**: the collector allows multiple threads to accumulate concurrently into the same result container under conditions specified by the collector contract.

`Collectors.toSet()` is an `UNORDERED` collector; it does not claim to be a `CONCURRENT` collector. The fact that `parallelStream().collect(toSet())` executes validly does not authorize calling `add` on a shared `HashSet` from multiple threads.

If a concurrent data structure updated independently by multiple external threads is truly required, design an explicit synchronization mechanism or use an appropriate thread-safe structure. For a straightforward result-collecting pipeline, a collector is typically simpler and less error-prone.

### 8.3. Preserving Order in Parallel Can Increase Cost

With `LinkedHashSet` or `distinct()` on an ordered stream, maintaining first-seen order can incur coordination overhead when running in parallel. If business logic does not require ordering, `toSet()` gives the framework more execution freedom. **Do not assume an unordered collector is always faster**: measurements depend on data, hash collisions, set size, thread count, and container creation/merging overhead.

## 9. Combining `groupingBy` with `toSet()`

A common use case is grouping data and then collecting unique values within each group. For example, each study group has multiple course registrations, which may contain duplicates:

```java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

record Enrollment(String group, String course) {}

List<Enrollment> registrations = List.of(
        new Enrollment("A", "Java"),
        new Enrollment("A", "SQL"),
        new Enrollment("A", "Java"),
        new Enrollment("B", "Git"),
        new Enrollment("B", "SQL")
);

Map<String, Set<String>> coursesByGroup = registrations.stream()
        .collect(Collectors.groupingBy(
                Enrollment::group,
                Collectors.mapping(
                        Enrollment::course,
                        Collectors.toSet()
                )
        ));

System.out.println(coursesByGroup.get("A").equals(Set.of("Java", "SQL")));
// true
System.out.println(coursesByGroup.get("B").equals(Set.of("Git", "SQL")));
// true
```

`groupingBy` determines the group key, `mapping` extracts the `course` field, and `toSet()` deduplicates **within each group**. The `Map` created by the default `groupingBy` overload also does not guarantee key iteration order.

If you must preserve the first registration order of each course within a group, you can replace the downstream collector with:

```java
Map<String, LinkedHashSet<String>> orderedCoursesByGroup =
        registrations.stream().collect(Collectors.groupingBy(
                Enrollment::group,
                Collectors.mapping(
                        Enrollment::course,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));

System.out.println(orderedCoursesByGroup.get("A")); // [Java, SQL]
```

The `registrations` source is a `List` with encounter order. If the order of group keys is also required, specify a `mapFactory` to `groupingBy`, such as `LinkedHashMap::new`; choosing a `LinkedHashSet` downstream applies only to **the values within each group**.

## 10. Performance, Memory, and Lifecycle Limits

Collecting into a `Set` must store the unique values in memory. For a finite source with `n` elements and `u` unique elements:

- With a hash-based `Set`, average total insertion time is typically near `O(n)` when hash distribution is good; in the worst case, hash collisions and `equals` costs can slow it down significantly.
- `TreeSet` typically takes around `O(n log u)` to insert `n` elements, in exchange for comparison-based ordering.
- Memory for the result depends on roughly `u` elements and the data structure overhead, not just `n`. In parallel processing, additional intermediate containers and buffers may also exist.
- `toSet()` does not automatically close source resources and is not a short-circuiting terminal operation: it must traverse a finite source to completion.

With an infinite stream, do not call `collect(toSet())` directly because the terminal operation may never terminate, even if the generated element repeats endlessly:

```java
// Do not run:
// Set<Integer> forever = Stream.generate(() -> 1)
//         .collect(Collectors.toSet());

Set<Integer> sample = Stream.generate(() -> 1)
        .limit(100)
        .collect(Collectors.toSet());

System.out.println(sample.equals(Set.of(1))); // true
```

For resource-backed sources such as `Files.lines(path)`, use `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static Set<String> readUniqueLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toSet());
    }
}
```

After a `collect` terminal operation, do not consume the same `Stream` object again; to collect in a different way, create a new stream from a re-readable source. Do not use `peek` or stateful accumulators with side effects to replace collection: accumulating into a `Set` via a collector has clearer semantics and avoids mutating external state inside a pipeline.

## 11. Runnable Comprehensive Program (Java 17+)

The standalone example below demonstrates `toSet`, `toCollection`, `toUnmodifiableSet`, distinguishing `Set` types, and key-based deduplication:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectToSetDemo {
    record Employee(long id, String name) {}
    record Enrollment(String group, String course) {}

    public static void main(String[] args) {
        List<String> input = List.of("Java", "SQL", "Java", "Git", "SQL");

        Set<String> anyOrder = input.stream().collect(Collectors.toSet());
        System.out.println(anyOrder.equals(Set.of("Java", "SQL", "Git"))); // true

        LinkedHashSet<String> insertion = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println(insertion); // [Java, SQL, Git]

        TreeSet<String> sorted = input.stream()
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println(sorted); // [Git, Java, SQL]

        Set<String> readOnly = Stream.of("A", null, "A", "B")
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableSet());
        System.out.println(readOnly.equals(Set.of("A", "B"))); // true

        List<Employee> employees = List.of(
                new Employee(1, "An"),
                new Employee(1, "An updated"),
                new Employee(2, "Binh")
        );
        Set<Long> ids = employees.stream()
                .map(Employee::id)
                .collect(Collectors.toSet());
        System.out.println(ids.equals(Set.of(1L, 2L))); // true

        List<Enrollment> registrations = List.of(
                new Enrollment("A", "Java"),
                new Enrollment("A", "Java"),
                new Enrollment("A", "SQL"),
                new Enrollment("B", "Git")
        );
        Map<String, Set<String>> groups = registrations.stream()
                .collect(Collectors.groupingBy(
                        Enrollment::group,
                        Collectors.mapping(
                                Enrollment::course,
                                Collectors.toSet()
                        )
                ));
        System.out.println(groups.get("A").equals(Set.of("Java", "SQL")));
        // true

        Set<Integer> parallel = List.of(3, 1, 2, 3, 1).parallelStream()
                .collect(Collectors.toSet());
        System.out.println(parallel.equals(Set.of(1, 2, 3))); // true

        // Do not infer iteration order from toSet(), even when the source is a List.
    }
}
```

The program does not depend on the print order of `HashSet` or `toSet()` results; those checks use `Set.equals`, because set equality accurately reflects the element contents the application cares about.

## 12. Common Mistakes

| Misconception or snippet | Why is it problematic? | Appropriate approach |
|---|---|---|
| Calling `toSet()` and expecting `List` order to be preserved | The collector is `UNORDERED` | Use `toCollection(LinkedHashSet::new)` |
| Calling `sorted().collect(toSet())` and expecting a sorted set | Resulting `Set` does not promise iteration order | Use `toCollection(TreeSet::new)` or `distinct().sorted().toList()` |
| Assuming two objects with the same `id` are automatically deduplicated | `equals` may inspect other fields | Define identity by id or `map` to id |
| Overriding `equals` but forgetting `hashCode` | Violates the hash-based collection contract | Implement both consistently or use an appropriate `record` |
| Assuming `TreeSet` always deduplicates by `equals` | `TreeSet` relies on comparator or `compareTo` | Evaluate `compare(...) == 0` and consistency with `equals` |
| Expecting `Collectors.toSet()` to always return a mutable `HashSet` | API does not promise concrete type or mutability | Use `toCollection(HashSet::new)` when specifically needed |
| Using `toUnmodifiableSet()` with `null` | Collector rejects `null` | `filter(Objects::nonNull)` or define a replacement policy |
| Thinking `Set.of("A", "A")` will deduplicate | This factory throws `IllegalArgumentException` | Use `Set.copyOf` or a collector if deduplication is desired |
| `parallelStream().forEach(sharedSet::add)` | A shared `HashSet` is not thread-safe | Use `parallelStream().collect(toSet())` |
| Assuming `UNORDERED` means `CONCURRENT` | These are two different collector characteristics | Read `Collector.Characteristics` carefully |
| Collecting an infinite stream directly into a set | `collect` waits for the source to finish | Set a finite limit before `collect` |
| Using `distinct()` before `toSet()` in every pipeline | Can create an unnecessary deduplication step | Only use when mid-pipeline deduplication or ordered representative selection is needed |

## 13. Self-Check

1. **What does `List.of("a", "b", "a").stream().collect(Collectors.toSet()).size()` return?** Returns `2`.
2. **Does `Collectors.toSet()` guarantee creating a mutable `HashSet`?** No, neither implementation type nor mutability is guaranteed.
3. **How do you deduplicate while preserving first-appearance order from a `List` source?** `collect(Collectors.toCollection(LinkedHashSet::new))` or `distinct().toList()` if a `List` is needed.
4. **How do you create a set of ascending numbers?** `collect(Collectors.toCollection(TreeSet::new))` when elements have an appropriate natural order.
5. **Are two records `Employee(1, "An")` and `Employee(1, "An new")` deduplicated by default?** No, because `record.equals` compares all components.
6. **Why can `BigDecimal("1.0")` and `BigDecimal("1.00")` be treated as duplicates by `TreeSet` yet distinct by `HashSet`?** `compareTo` returns `0`, whereas `equals` distinguishes scale.
7. **How does `Collectors.toUnmodifiableSet()` differ from `Collectors.toSet()`?** The first guarantees unmodifiability and rejects `null`; the second guarantees neither mutability nor concrete type.
8. **Does `Set.of("A", "A")` return a single-element set?** No. It throws `IllegalArgumentException`.
9. **Does `parallelStream().collect(Collectors.toSet())` require `HashSet` to be thread-safe?** No. The framework manages containers and merging; the returned set does not automatically become thread-safe.
10. **To get unique courses within each group, which collectors do you use?** `groupingBy` with `mapping` and `toSet`.
11. **Does `Stream.generate(() -> 1).collect(Collectors.toSet())` terminate because there is only one unique value?** No. The collector still waits for the source to finish; a limit or finite source is required.
12. **If you need the first record by `equals` from an ordered source, what should you use?** `distinct().toList()` or `distinct()` followed by collecting into a structure that preserves encounter order.

**Key takeaway:** Collecting into a `Set` means choosing the **uniqueness rule**, **result structure**, and **ordering contract**. `Collectors.toSet()` fits when you only need a set of distinct elements; `toCollection(LinkedHashSet::new)` when first-seen order must be kept; `toCollection(TreeSet::new)` when iterating in comparison order; and `toUnmodifiableSet()` when an unmodifiable result is required. Before deduplicating objects, always verify what `equals`/`hashCode` or the comparator defines as "the same element".
