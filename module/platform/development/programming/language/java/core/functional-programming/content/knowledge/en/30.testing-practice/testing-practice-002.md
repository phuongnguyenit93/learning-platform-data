# Testing Empty Sources, Single Elements, Nulls, and Duplicates in Java Streams

## 1. Why test edge cases?

A Stream pipeline may produce the right result on multi-element sample data and still fail when:

- **Empty source:** there are no elements for `map`, `filter`, `reduce`, or `collect` to process.
- **Single-element source:** search, grouping, splitting, or taking the first/last element must not rely on an assumption that there are at least two elements.
- **`null` values:** this can be either **the source reference itself being null**, or just **an element inside the source being null**; the two situations must be handled differently.
- **Duplicate data:** `distinct`, `groupingBy`, `toMap`, and counting/aggregation business logic have different meanings when multiple records share a key.

In Java, a Stream is **a data-processing pipeline**, not a guarantee that data is always valid or never missing. Good tests need to establish the **intended contract** of each situation before writing transformations.

For example:

```java
List<String> names = List.of();
List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
System.out.println(result); // []
```

The pipeline is valid and returns an empty list. However, the following line can fail:

```java
String first = names.stream()
        .findFirst()
        .orElseThrow(); // NoSuchElementException.
```

The difference lies in the **terminal operation and absence-handling policy**, not that empty data itself is always an error.

**Lesson goal:** build a repeatable test suite for these four categories of scenarios, understand the semantics of the Java 17 Stream API, and know how to choose the right handling strategy instead of hiding abnormal data.

## 2. Minimum test matrix

First, write down the inputs and expected outputs clearly:

| Test case | Source | Pipeline | Expected result |
| --- | --- | --- | --- |
| Empty | `[]` | `filter(...).toList()` | `[]` |
| Empty | `[]` | `count()` | `0` |
| Empty | `[]` | `findFirst()` | `Optional.empty()` |
| Single element | `["solo"]` | `map(toUpperCase).toList()` | `["SOLO"]` |
| Single element | `["solo"]` | `count()` | `1` |
| Contains null | `["A", null, "B"]` | `toList()` | Retains the null element |
| Contains null | `["A", null, "B"]` | `filter(nonNull).toList()` | `["A","B"]` |
| Contains null | `["A", null, "B"]` | `map(String::trim)` | `NullPointerException` upon encountering null |
| Duplicates | `["a","b","a"]` | `distinct().toList()` | `["a","b"]` on an ordered stream |
| Duplicate keys | `["x","x"]` | `toMap` without merge | `IllegalStateException` |
| Duplicate keys | `["x","x"]` | `toMap` with counting merge | `{x=2}` |
| Null classifier | `[null]` | `groupingBy(identity)` | `NullPointerException` |
| Custom source | Empty or duplicate `Iterable` | `StreamSupport.stream` | Empty list or deduplicated result accordingly |

This is a **baseline case set**, not a fixed list to apply mechanically. Depending on the problem, you must add invalid data, multiple sizes, very large data, different orderings, integer overflow, I/O errors, thread contention, and time boundaries.

**Principle:** tests assert **results or error types per the contract**, not implementation details such as the internal class name of `Stream.toList()` or the arbitrary processing order of a parallel stream.

## 3. Empty source: many operations are completely valid

With `Stream.empty()` or `List.of().stream()`:

```java
List<Integer> empty = List.of();

System.out.println(empty.stream().toList()); // []
System.out.println(empty.stream().count());  // 0
System.out.println(empty.stream().filter(n -> n > 0).toList()); // []
```

`filter`, `map`, and `flatMap` have no elements to process, so the collected result remains empty. This differs from the case of a **non-existent source** (a null `List` variable), analyzed later.

### `findFirst`, `min`, `max`, and `average` return Optional

```java
boolean none = Stream.<String>empty()
        .findFirst()
        .isEmpty();

boolean noMax = java.util.stream.IntStream.empty()
        .max()
        .isEmpty();

boolean noAverage = java.util.stream.IntStream.empty()
        .average()
        .isEmpty();

System.out.println(none);      // true
System.out.println(noMax);     // true
System.out.println(noAverage); // true
```

`findFirst` returns `Optional<T>`, `IntStream.max` returns `OptionalInt`, and `IntStream.average` returns `OptionalDouble`. For an empty source, there is no first element, maximum, or average.

Do not call `get()`/`getAsInt()`/`getAsDouble()` unconditionally on an empty Optional. You can use `orElse` or `orElseThrow` depending on business rules:

```java
String display = Stream.<String>empty()
        .findFirst()
        .orElse("NO_DATA");

System.out.println(display); // NO_DATA
```

If "no data" is a normal state, use an explicit fallback; if it is a business error, throw an application-defined exception.

### Matching operations on an empty Stream

`anyMatch`, `allMatch`, and `noneMatch` have logic worth testing:

```java
boolean any = Stream.<Integer>empty()
        .anyMatch(n -> n > 0);  // false

boolean all = Stream.<Integer>empty()
        .allMatch(n -> n > 0);  // true

boolean none = Stream.<Integer>empty()
        .noneMatch(n -> n > 0); // true
```

`allMatch` returns `true` on an empty set by the rule of **vacuous truth**: no element violates the condition. `noneMatch` is also true because no element matches; `anyMatch` is false because no matching element is found.

If the system defines "all orders meet the standard" as meaningful only when there is at least one order, add a non-empty check at the business level rather than changing the contract interpretation of `allMatch`.

### `reduce`: with identity vs without identity

```java
int zero = Stream.<Integer>empty()
        .reduce(0, Integer::sum); // 0

boolean absent = Stream.<Integer>empty()
        .reduce(Integer::sum)
        .isEmpty(); // true
```

The overload `reduce(identity, accumulator)` returns **identity** for an empty source, whereas `reduce(accumulator)` without identity returns `Optional.empty()`. Use the right identity for the operation: 0 for addition, 1 for multiplication, but there is no "universal right default" for every domain problem.

### Do not rely on side effects in an empty pipeline

If a mapper, predicate, or `peek` is not invoked because there are no elements, that is natural behavior. However, **do not turn the invocation count of a mapper/peek into an audit mechanism**: some terminal operations like `count` can be optimized using the source size, and are not required to run every intermediate operation just to count.

## 4. Single element: transformations and boundary verification

A source with exactly one element is a test that catches code assuming there is a second element:

```java
List<String> single = List.of("solo");

System.out.println(single.stream().count()); // 1
System.out.println(single.stream()
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .toList()); // [SOLO]
System.out.println(single.stream()
        .findFirst().orElseThrow()); // solo
```

`findFirst` here has a value so `orElseThrow` returns `solo`; this differs from the empty source in section 3.

Scenarios worth adding tests for:

- `limit(0)` on one element must produce an empty stream; `limit(1)` keeps one element.
- `skip(1)` on one element produces an empty stream.
- `distinct` on one element keeps one element.
- `sorted` on one element needs no reordering.
- `min`/`max` on one element returns that same value.
- `collect(groupingBy(...))` creates one group if the classifier produces a valid key.

`Stream` does not have `get(index)`. If you want to access an element at a position, consider using a List, `skip`/`findFirst`, or an appropriate data model; do not write logic that implicitly expects random access on a stream.

### Do not confuse "one element" with "one null element"

`Stream.of((String) null)` creates a stream **with one element, and that element is null**. It differs from `Stream.empty()`, and differs from `Stream.ofNullable((String) null)`, which returns an empty stream:

```java
System.out.println(Stream.of((String) null).count()); // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
```

Casting `(String) null` makes the example unambiguous with the varargs overload of `Stream.of`. However, calling `findFirst()` on a stream whose first element is null can throw `NullPointerException` because `Optional` cannot hold a present null value. Check the source's contract before using a terminal that returns Optional.

## 5. Three different concepts of null

Some testing mistakes stem from using the same word "null" for three situations:

| Situation | Example | Behavior |
| --- | --- | --- |
| **Source is null** | `List<String> list = null; list.stream()` | Throws `NullPointerException` when invoked on a null reference |
| **Valid source contains null element** | `Arrays.asList("A", null, "B")` | Source still has three elements; mapper may fail when encountering null |
| **An optional value is null** | `Stream.ofNullable(null)` | Creates an empty stream |
| **Optional reference is null** | `Optional<String> opt = null; opt.stream()` | Throws `NullPointerException`; API used violating its contract |

Handling must match business policy:

- If the source is **required to exist**, use `Objects.requireNonNull(source)` to fail early at a clear location.
- If the source is **allowed to be absent**, convert it to an empty collection or use an Optional handling strategy, but state this explicitly in the contract.
- If **null elements are valid**, decide whether to retain, remove, replace with a sentinel, or report an error.
- If null indicates **corrupted data**, do not silently skip it just because the pipeline can filter it out.

Do not assume every null means the same thing or that every null should be turned into the string `"UNKNOWN"`.

### `List.of` does not allow null elements

```java
// Intentional example causing NullPointerException:
List<String> invalid = List.of((String) null);
```

`List.of` (Java 9+) rejects null when creating a list. In a running program, catch the exception or test with `assertThrows`; do not place this line before other tests and let the program abort unexpectedly.

A collection that can contain null for testing:

```java
List<String> nullable = java.util.Arrays.asList("A", null, "B");
```

`Arrays.asList` is a fixed-size list and can contain null in this example. It is **not** a fully size-mutable `ArrayList`, and replacing elements with `set` has a different contract from `Stream.toList`.

## 6. Handling null in a pipeline

Suppose:

```java
List<String> values = java.util.Arrays.asList(" A ", null, "B");
```

### Approach 1 — Keep null as data

```java
List<String> retained = values.stream().toList();
System.out.println(retained); // [ A , null, B]
```

`Stream.toList()` (Java 16+) creates an unmodifiable list that **allows null**. This does not mean every collector and every JDK List method also allows null.

### Approach 2 — Drop null if permitted

```java
List<String> nonNull = values.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::trim)
        .toList();

System.out.println(nonNull); // [A, B]
```

`filter(Objects::nonNull)` comes **before** `map(String::trim)` so it avoids calling an instance method on null. Reversing the order can throw `NullPointerException` before reaching the filter step.

### Approach 3 — Replace null with a defined domain value

```java
List<String> shown = values.stream()
        .map(value -> value == null ? "MISSING" : value.trim())
        .toList();

System.out.println(shown); // [A, MISSING, B]
```

This option is only right when `"MISSING"` is a valid representation and cannot be confused with a real value. When you need to distinguish multiple error causes, use an explicit status model instead of a special string.

### Approach 4 — `Stream.ofNullable` and `flatMap`

`Stream.ofNullable(T)` returns a one-element stream if T is non-null, otherwise an empty stream. Available since Java 9:

```java
List<String> clean = values.stream()
        .flatMap(Stream::ofNullable)
        .map(String::trim)
        .toList();

System.out.println(clean); // [A, B]
```

For this simple result, it is equivalent to filtering with `Objects::nonNull`. Choose whichever expression is clearer and consistent with the codebase. `Stream.ofNullable` is also useful when a transformation can return null and you want to turn each result into **0 or 1 element**.

### Approach 5 — Put null last when sorting

`sorted()` defaults to natural order; a source with null can throw `NullPointerException` if the comparator or comparison must handle null. If business rules **allow null** and want it sorted after real values:

```java
List<String> sorted = values.stream()
        .sorted(java.util.Comparator.nullsLast(
                java.util.Comparator.naturalOrder()))
        .toList();

System.out.println(sorted); // [ A , B, null]
```

Here `" A "` has leading/trailing spaces, so natural order is computed on the original value; it does not trim automatically. If you want to sort normalized data, normalize first and then sort.

## 7. Null in `groupingBy` and `toMap`

Not every collector accepts null keys.

`Collectors.groupingBy(classifier)` requires the classifier to return a **non-null** key. If the classifier returns null, collecting throws `NullPointerException`:

```java
// Intentional error: classifier returns null for a null element.
Map<String, List<String>> groups = Stream.of((String) null)
        .collect(java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity()));
```

This example must be used in an expected-exception test, not a happy-path test.

If "no value" is a meaningful group, produce a **non-null** sentinel key:

```java
Map<String, List<String>> groups = values.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                s -> s == null ? "MISSING" : s.trim()));
```

This example **does not decide** that the inner list must drop null: a `"MISSING"` group can still contain the original null element itself. If downstream code or a serializer forbids null, map or guard accordingly.

With `Collectors.toMap`, two elements with the same key cause the collector **without a merge function** to throw `IllegalStateException`. This is an error due to **duplicate keys**, not necessarily null. The fix is to define a keep-first/keep-last/accumulate contract:

```java
Map<String, Integer> counts = Stream.of("x", "x", "y")
        .collect(java.util.stream.Collectors.toMap(
                java.util.function.Function.identity(),
                value -> 1,
                Integer::sum));

System.out.println(counts.get("x")); // 2
```

Do not pick a merge function just to silence the exception if business rules actually forbid two records with the same code. When duplication signals bad data, fail fast with a clear message or validate duplicates before writing to the system.

## 8. Testing duplicates: `distinct` uses `equals`

`distinct()` is an intermediate operation that removes duplicate elements according to `Object.equals`:

```java
List<String> unique = Stream.of("a", "b", "a", "c", "b")
        .distinct()
        .toList();

System.out.println(unique); // [a, b, c]
```

For a stream with encounter order, `distinct` retains the **first element** of each group of values equal under `equals`. In an **ordered** parallel stream, stability with respect to encounter order is still part of the contract, though at a higher coordination cost.

### Character-level duplicates vs semantic duplicates

`"Java"` and `"java"` are two strings that are **not equal under `String.equals`**. If business rules treat them as the same, normalize first:

```java
List<String> words = List.of(" Java ", "java", "JAVA", "Stream");

List<String> unique = words.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .toList();

System.out.println(unique); // [java, stream]
```

Placing `distinct` before normalization will fail to remove semantic duplicates. The step order **normalize → distinct** is a concrete data decision and should have a test asserting it.

### Records and business keys are not necessarily the same

`record Order(String id, int amount)` has `equals` based on **all components**. Thus:

```java
record Order(String id, int amount) {}

List<Order> orders = List.of(
        new Order("A", 10),
        new Order("A", 10),
        new Order("A", 20)
);

System.out.println(orders.stream().distinct().count()); // 2
System.out.println(orders.stream()
        .map(Order::id).distinct().count());             // 1
```

This is an **illustrative** snippet that must be placed inside a valid Java class/method. Two records `("A",10)` are completely identical under record equality, while `("A",20)` has a different amount and is **not an object-value duplicate**. Yet when checking **duplicate IDs**, all three share ID A. Do not assume `distinct` on an object automatically knows which field is the business key.

When you need to detect duplicate IDs with differing content, `groupingBy(Order::id)` or `toMap` with an appropriate merge/validation policy is usually clearer.

## 9. Counting frequency instead of discarding duplicates

`distinct` discards information about **how many duplicates existed**. If the goal is to report occurrence counts, use `groupingBy(..., counting())`:

```java
List<String> raw = List.of(
        " Alpha ", "alpha", "BETA", "beta", "alpha");

Map<String, Long> counts = raw.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .collect(java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity(),
                java.util.TreeMap::new,
                java.util.stream.Collectors.counting()));

System.out.println(counts); // {alpha=3, beta=2}
```

Using `TreeMap::new` makes the **printed key order deterministic** according to natural order. Default `groupingBy` does not promise a specific map type or iteration order; if you write expected stdout using `map.toString()`, actively choose an ordered map or compare entries individually.

### Getting duplicate keys with occurrence count greater than 1

```java
List<String> duplicates = counts.entrySet().stream()
        .filter(entry -> entry.getValue() > 1L)
        .map(Map.Entry::getKey)
        .toList();

System.out.println(duplicates); // [alpha, beta]
```

In this snippet `counts` is a `TreeMap`, so streaming `entrySet` has encounter order by key; output is deterministic. If using `HashMap`, do not constrain iteration order over keys without `sorted`.

## 10. Complete Java 17 program: self-test without JUnit

This example creates a **small assertion helper** to test empty data, singleton, null, duplicates, collector errors, result ordering, and a custom `Iterable` source. The program **throws `AssertionError` immediately when a contract fails**, so the final line `All checks passed` only appears when every check succeeds.

Create the file **`StreamEdgeCasesDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class StreamEdgeCasesDemo {
    record Order(String id, int amount) {}

    static void expectEqual(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    static void expectThrows(Class<? extends Throwable> type,
                             Runnable action,
                             String label) {
        boolean matched = false;
        try {
            action.run();
        } catch (Throwable ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError(label
                        + " unexpected exception: " + ex, ex);
            }
            matched = true;
        }
        if (!matched) {
            throw new AssertionError(label
                    + " expected " + type.getSimpleName());
        }
    }

    public static void main(String[] args) {
        // 1. Empty source.
        List<String> empty = List.of();
        List<String> emptyResult = empty.stream()
                .map(String::toUpperCase)
                .toList();
        expectEqual(List.of(), emptyResult, "empty toList");
        expectEqual(0L, empty.stream().count(), "empty count");
        expectEqual(true, empty.stream().findFirst().isEmpty(),
                "empty findFirst");
        expectEqual(false, Stream.<Integer>empty()
                .anyMatch(n -> n > 0), "empty anyMatch");
        expectEqual(true, Stream.<Integer>empty()
                .allMatch(n -> n > 0), "empty allMatch");
        expectEqual(true, Stream.<Integer>empty()
                .noneMatch(n -> n > 0), "empty noneMatch");
        System.out.println("Empty: " + emptyResult);
        System.out.println("Empty count: " + empty.stream().count());
        System.out.println("Empty first present: "
                + empty.stream().findFirst().isPresent());
        System.out.println("Empty any/all/none: false/true/true");

        // 2. Single-element source.
        List<String> singleton = List.of("solo");
        List<String> singleUpper = singleton.stream()
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();
        expectEqual(List.of("SOLO"), singleUpper, "singleton map");
        expectEqual("solo", singleton.stream()
                .findFirst().orElseThrow(), "singleton first");
        expectEqual(1L, singleton.stream().count(), "singleton count");
        System.out.println("Singleton: " + singleUpper);

        // 3. Valid source containing null elements.
        List<String> nullable = Arrays.asList("A", null, "B");
        List<String> keptNull = nullable.stream().toList();
        List<String> removedNull = nullable.stream()
                .filter(Objects::nonNull)
                .toList();
        List<String> substituted = nullable.stream()
                .map(s -> s == null ? "MISSING" : s)
                .toList();
        List<String> usingNullable = nullable.stream()
                .flatMap(Stream::ofNullable)
                .toList();
        List<String> sortedNullLast = nullable.stream()
                .sorted(Comparator.nullsLast(
                        Comparator.naturalOrder()))
                .toList();

        expectEqual(Arrays.asList("A", null, "B"),
                keptNull, "toList keeps null");
        expectEqual(List.of("A", "B"), removedNull,
                "filter nonNull");
        expectEqual(List.of("A", "MISSING", "B"),
                substituted, "substitute null");
        expectEqual(List.of("A", "B"), usingNullable,
                "flatMap ofNullable");
        expectEqual(Arrays.asList("A", "B", null),
                sortedNullLast, "nullsLast");
        expectEqual(0L, Stream.ofNullable((String) null).count(),
                "ofNullable null is empty");

        System.out.println("Nullable retained: " + keptNull);
        System.out.println("Nullable filtered: " + removedNull);
        System.out.println("Nullable substituted: " + substituted);
        System.out.println("Nullable flatMap: " + usingNullable);
        System.out.println("Nullable sorted: " + sortedNullLast);

        // 4. Errors that must be asserted rather than ignored.
        expectThrows(NullPointerException.class,
                () -> List.of((String) null),
                "List.of(null)");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null)
                        .map(String::trim).toList(),
                "method call on null");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null).findFirst(),
                "findFirst of null");
        expectThrows(NullPointerException.class,
                () -> nullable.stream()
                        .collect(Collectors.toUnmodifiableList()),
                "toUnmodifiableList of null");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null)
                        .collect(Collectors.groupingBy(
                                Function.identity())),
                "groupingBy null key");
        expectThrows(UnsupportedOperationException.class,
                () -> keptNull.add("C"),
                "Stream.toList is unmodifiable");
        System.out.println("Null error cases: checked");

        // 5. Normalization and deduplication.
        List<String> raw = List.of(
                " Alpha ", "alpha", "BETA", "beta", "alpha");
        List<String> normalized = raw.stream()
                .map(String::trim)
                .map(s -> s.toLowerCase(Locale.ROOT))
                .toList();
        List<String> distinctTokens = normalized.stream()
                .distinct()
                .toList();
        Map<String, Long> frequency = normalized.stream()
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        TreeMap::new,
                        Collectors.counting()));

        expectEqual(List.of("alpha", "beta"),
                distinctTokens, "distinct tokens");
        expectEqual(Map.of("alpha", 3L, "beta", 2L),
                frequency, "frequency");
        System.out.println("Distinct tokens: " + distinctTokens);
        System.out.println("Frequency: " + frequency);

        // 6. Using record equality differs from business key.
        List<Order> orders = List.of(
                new Order("A", 10),
                new Order("A", 10),
                new Order("A", 20),
                new Order("B", 10));
        List<Order> distinctRecords = orders.stream()
                .distinct()
                .toList();
        List<String> distinctIds = orders.stream()
                .map(Order::id)
                .distinct()
                .toList();

        expectEqual(3, distinctRecords.size(), "record equality");
        expectEqual(List.of("A", "B"),
                distinctIds, "business key");
        System.out.println("Unique records: " + distinctRecords.size());
        System.out.println("Distinct IDs: " + distinctIds);

        // 7. toMap requires a policy for duplicate keys.
        expectThrows(IllegalStateException.class,
                () -> Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                Function.identity(),
                                String::length)),
                "duplicate key without merge");

        Map<String, Integer> merged = Stream.of("x", "x", "y")
                .collect(Collectors.toMap(
                        Function.identity(),
                        value -> 1,
                        Integer::sum,
                        TreeMap::new));
        expectEqual(Map.of("x", 2, "y", 1),
                merged, "duplicate count merge");
        System.out.println("Duplicate key merged: " + merged);

        // 8. distinct on an ordered stream keeps the first occurrence.
        List<String> parallelDistinct =
                List.of("a", "b", "a", "c")
                        .parallelStream()
                        .distinct()
                        .toList();
        expectEqual(List.of("a", "b", "c"),
                parallelDistinct, "ordered parallel distinct");
        System.out.println("Parallel distinct: " + parallelDistinct);

        // 9. Custom Iterable source (no Collection.stream needed).
        Iterable<String> custom =
                () -> Arrays.asList("old", "old", null).iterator();
        List<String> customUnique = StreamSupport
                .stream(custom.spliterator(), false)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        expectEqual(List.of("old"), customUnique, "custom Iterable");
        System.out.println("Custom source: " + customUnique);

        System.out.println("All checks passed");
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 StreamEdgeCasesDemo.java
java StreamEdgeCasesDemo
```

**Deterministic expected stdout:**

```text
Empty: []
Empty count: 0
Empty first present: false
Empty any/all/none: false/true/true
Singleton: [SOLO]
Nullable retained: [A, null, B]
Nullable filtered: [A, B]
Nullable substituted: [A, MISSING, B]
Nullable flatMap: [A, B]
Nullable sorted: [A, B, null]
Null error cases: checked
Distinct tokens: [alpha, beta]
Frequency: {alpha=3, beta=2}
Unique records: 3
Distinct IDs: [A, B]
Duplicate key merged: {x=2, y=1}
Parallel distinct: [a, b, c]
Custom source: [old]
All checks passed
```

### Why is this stdout stable?

1. `empty` and `singleton` are `List` instances with a clear encounter order. All collection operations produce results corresponding to the number of input elements.
2. `Arrays.asList("A", null, "B")` has null in the middle. `toList` keeps null, `filter` and `flatMap(Stream::ofNullable)` intentionally remove null, and `Comparator.nullsLast` moves null to the end.
3. Exception-throwing cases are **caught in `expectThrows`**. Execution continues to `Null error cases: checked` only when the exception has the right type.
4. Normalizing with `trim` and `toLowerCase(Locale.ROOT)` yields alpha, alpha, beta, beta, alpha in order. `distinct` keeps the first occurrences alpha/beta; `TreeMap` prints keys in alpha then beta order.
5. For record `Order`, two A/10 records are equal; A/20 differs; B/10 differs. Hence `distinctRecords.size()` is 3. Yet after extracting only `id`, the distinct values are A and B.
6. `toMap` with merge function `Integer::sum` turns two occurrences of x into count=2, and y into 1. `TreeMap` guarantees key display order.
7. `parallelStream().distinct().toList()` on an ordered `List` source preserves the stability of `distinct`; the result is a,b,c regardless of thread scheduling. No side effects depend on thread order in this example.
8. `custom` yields three elements: old, old, null. After filtering null and deduplicating, only old remains. There is no need to rely on ordering of an unordered source because only one value remains after processing.
9. The line `All checks passed` only appears after all expected values and expected exceptions have been verified. If any assertion fails, the program stops with `AssertionError`.

**Do not confuse "unchanged stdout" with "every parallel scenario has been tested".** The sample suite focuses on data results per contract. For stateful sources or custom Spliterators, you still need to test races, resources, and split accuracy.

## 11. Testing exceptions: must catch the exact error type

A valuable test must specify **what is allowed to happen**. Common error types:

| Situation | Expected exception type |
| --- | --- |
| `List.of((String)null)` | `NullPointerException` |
| Calling `String::trim` on a null element | `NullPointerException` |
| `Optional.empty().get()` | `NoSuchElementException` |
| `findFirst` selects a null element | `NullPointerException` |
| `Collectors.groupingBy` receives a null classifier key | `NullPointerException` |
| `Collectors.toMap` encounters a duplicate key without merge | `IllegalStateException` |
| `Stream.toList().add(...)` | `UnsupportedOperationException` |
| Reusing a Stream after a terminal operation | Usually throws `IllegalStateException` per Stream contract |
| `Integer.parseInt("abc")` inside a mapper | `NumberFormatException` |

**Do not test by catching `Exception` and passing by default**, because a different exception could indicate a bug. In the complete program, `expectThrows` checks `type.isInstance(ex)` and reports failure if the type does not match.

When you need to check the **message**, be careful: many messages from the JDK/collectors can change between versions or implementations. Focus on asserting the exception type and content controlled by **the application itself** rather than locking down an internal JDK message.

### Checked exceptions in a pipeline

A mapper calling an API declared with `throws IOException` cannot directly let a checked exception escape `Function.apply`. In an I/O-related test, distinguish compile-time errors from functional interface contracts from runtime I/O errors. You can catch/wrap `UncheckedIOException` or separate I/O from the pipeline; however, that is a separate issue from "empty/null/duplicate sources".

## 12. JUnit 5: from self-test to structured unit tests

Once a project is configured with JUnit Jupiter, test cases can be moved into separate test methods. The following example is **not a standalone JDK-only program**; it requires appropriate JUnit 5 dependencies in Maven/Gradle and must be run with a test runner:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class StreamEdgeCasesTest {
    @Test
    void emptyAndSingleton() {
        assertEquals(List.of(),
                Stream.<String>empty().toList());
        assertEquals(List.of("SOLO"),
                Stream.of("solo")
                        .map(String::toUpperCase)
                        .toList());
    }

    @Test
    void handlesNullByExplicitPolicy() {
        List<String> input = Arrays.asList("A", null, "B");
        assertEquals(List.of("A", "B"),
                input.stream()
                        .filter(Objects::nonNull)
                        .toList());
        assertThrows(NullPointerException.class,
                () -> input.stream()
                        .map(String::trim)
                        .toList());
    }

    @Test
    void rejectsDuplicateMapKeyUnlessMerged() {
        assertThrows(IllegalStateException.class,
                () -> Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                x -> x, String::length)));
        assertEquals(2,
                Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                x -> x, x -> 1, Integer::sum))
                        .get("x"));
    }
}
```

A test method that verifies **one behavior or a group of related behaviors** makes failures easier to diagnose than a giant test with only print statements. Unit tests should use assertions rather than visual comparison via stdout.

### Parameterized testing

If JUnit Jupiter Parameters is available, write different input/output cases as a dataset:

```java
// Component example for a JUnit 5 test class:
@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.MethodSource("cases")
void normalizedTokens(List<String> input, List<String> expected) {
    List<String> actual = input.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .map(s -> s.toLowerCase(java.util.Locale.ROOT))
            .distinct()
            .toList();
    org.junit.jupiter.api.Assertions.assertEquals(expected, actual);
}

static Stream<org.junit.jupiter.params.provider.Arguments> cases() {
    return Stream.of(
        org.junit.jupiter.params.provider.Arguments.of(
                List.of(), List.of()),
        org.junit.jupiter.params.provider.Arguments.of(
                List.of("A"), List.of("a")),
        org.junit.jupiter.params.provider.Arguments.of(
                Arrays.asList("A", null, "a"), List.of("a")),
        org.junit.jupiter.params.provider.Arguments.of(
                List.of("A", "B", "A"), List.of("a", "b"))
    );
}
```

This is a **supplementary snippet** to place inside a test class and requires imports for `List`, `Arrays`, `Objects`, and `Stream`. It requires both JUnit Jupiter API and Parameters on the classpath. Do not assume the project already has JUnit just because it uses JDK 17.

## 13. Property-based thinking: checking invariants instead of a single input

Beyond four fixed examples, you can define **invariants** that must hold across many datasets:

1. **Null filtering:** every element of the result of `filter(Objects::nonNull)` is non-null.
2. **Distinct:** the result has no two elements at different positions equal under `equals`.
3. **Order preservation:** for an ordered source, `distinct` keeps the first occurrence of each value.
4. **Group counts:** the sum of element counts across groups equals the number of input elements, if every input is classified into exactly one group and none are filtered.
5. **Frequency:** the sum of counts from `groupingBy(..., counting())` equals the number of input elements.
6. **No data loss:** if only normalizing without filtering, the output size equals the input size (unless an error or short-circuiting occurs per contract).
7. **Idempotent normalization:** normalizing already-normalized data a second time gives an equivalent result to the first time, if the normalize function is designed to be idempotent.

Invariants can be checked with a property-based testing library or a loop test with controlled generated inputs. However, **do not use unseeded randomness that relies on irreproducible results**: when a failure occurs, save the input/seed for diagnosis.

Example invariant idea for `distinct`:

```java
List<String> result = input.stream().distinct().toList();

long distinctCount = result.stream().distinct().count();
if (distinctCount != result.size()) {
    throw new AssertionError("duplicate remained");
}
```

This is an illustrative snippet and requires an `input` variable. This test only checks that **no duplicates remain**; to be sure no value groups were dropped, compare the value set or the list of first occurrences against an expected reference implementation.

## 14. Custom sources: testing empty, single-element, and duplicates

A custom `Iterable` or `Spliterator` can have bugs in **data generation**, independent of Stream operations. For example:

```java
Iterable<String> source = () ->
        java.util.Arrays.asList("a", "a", null).iterator();

List<String> result = StreamSupport
        .stream(source.spliterator(), false)
        .filter(java.util.Objects::nonNull)
        .distinct()
        .toList();

System.out.println(result); // [a]
```

This source uses `Iterable.spliterator()` wrapped via `StreamSupport`; `filter`/`distinct` behave just as with regular collections.

If you implement `Spliterator.tryAdvance`/`trySplit` yourself, also test:

- **Empty source:** `tryAdvance` returns false immediately, `count()` is 0.
- **Single element:** `tryAdvance` returns true once then false, emitting no duplicates.
- **Null:** if advertising `NONNULL`, the source must not emit null.
- **Duplicates:** if advertising `DISTINCT`, it must not emit two values equal under `equals`.
- **Ordered:** if advertising `ORDERED`, the result order must match the contract.
- **Sized:** if advertising `SIZED`, the size must be accurate under the promised conditions.
- **Splitting:** `trySplit` must not lose or duplicate elements, including with 0/1/2 elements.

**Do not advertise `DISTINCT` hoping downstream will deduplicate.** If the actual source has duplicates while the Spliterator falsely advertises `DISTINCT`, the Stream framework can optimize away `distinct()`. That is a source metadata bug, not a bug in `distinct`.

### Testing across multiple splits

For a splittable Spliterator:

```text
Source: [A, B, C, D]
       |
       +-- trySplit() --> left branch
       |
       +----------------> right branch
```

Collect the elements of both branches and verify **total element count**, **values**, **no unexpected duplicates**, and if `ORDERED`, **valid order**. Empty and singleton sources often expose `trySplit` bugs that return an empty branch while reporting a wrong size or failing to update the cursor.

## 15. When is duplicate data an error, and when is it normal business behavior?

Not all duplicate data should be removed with `distinct()`.

| Situation | Potentially appropriate handling |
| --- | --- |
| A user is imported twice with the same ID | Validate, warn, or merge per rules |
| The same product appears on two invoice lines | Possibly keep both lines to sum quantities |
| The same word appears multiple times in text | `groupingBy(..., counting())` to count frequency |
| A tag list repeats the same label | `distinct()` to display each tag once |
| Two different objects share the same business code | Group by key; do not just call `distinct()` on objects |
| Duplicate keys in `toMap` | Define a merge or report an error; do not pick randomly |
| Duplicate records from I/O retries | Idempotency, unique constraints, and auditing at the storage layer |
| Duplicate nulls in a list | One null element may remain after `distinct`, if keeping null is valid |

For business domains requiring data integrity, "deleting duplicates" is not always the right fix. For example, if two payment orders share the same ID but have different totals, merely calling `distinct` by ID and keeping one record can hide a serious bug. Tests must specify the **conflict-resolution principle**.

## 16. Testing null source vs null elements must be kept separate

For example, a legacy API may return `null` instead of a list:

```java
List<String> legacy = null;
```

Calling `legacy.stream()` throws `NullPointerException` right at the source. If the legacy API's contract allows absence, an explicit adapter is:

```java
List<String> safeSource =
        legacy == null ? List.of() : legacy;

List<String> result = safeSource.stream()
        .filter(java.util.Objects::nonNull)
        .toList();
```

This is an illustrative snippet. **Do not automatically treat every null source as empty** when null actually indicates a connection error, unloaded data, or a contract violation. In those cases, report a specific error/Result.

An approach using `Optional`:

```java
List<String> result =
        java.util.Optional.ofNullable(legacy)
                .orElseGet(List::of)
                .stream()
                .filter(java.util.Objects::nonNull)
                .toList();
```

Both approaches produce the same result when `legacy == null` and the policy states "null source = no elements". The difference from `Stream.ofNullable` is that the checked object here is the **source list**, not each element of a Stream.

## 17. Avoid tests that depend on arbitrary ordering

With `HashSet` or `HashMap`, do not write tests expecting an arbitrary order if the API does not guarantee encounter order. For example:

```java
java.util.Set<String> set =
        new java.util.HashSet<>(List.of("B", "A", "C"));

List<String> sorted = set.stream()
        .sorted()
        .toList();

System.out.println(sorted); // [A, B, C]
```

Calling `sorted()` makes the result order deterministic. Without it, the order from `HashSet` should not be a test requirement.

For a parallel stream on an ordered source, `distinct` and `toList` still preserve encounter order per contract. However, **the execution order of mappers or `forEach` is not guaranteed**. Test the result via collections/invariants, not by asserting log order or thread names.

### Tests should not assume default `groupingBy` order

`Collectors.groupingBy(...)` returns a map with no guaranteed iteration order. In a test:

```java
Map<String, Long> grouped = words.stream()
        .collect(Collectors.groupingBy(
                Function.identity(), Collectors.counting()));

assertEquals(2L, grouped.get("a"));
assertEquals(1L, grouped.get("b"));
```

This is an illustrative JUnit snippet; `words` must be defined and assertions imported. If key order is required, choose a `TreeMap`/`LinkedHashMap` per actual requirements, or `sorted` when iterating results.

## 18. Tests must not only check "right output" but also why it is right

A good test suite should cover:

**Expected normal result:** valid data returns the right List/Map/number.

**Expected exception:** invalid null or duplicate must fail with the right type, not be swallowed.

**Boundary:** empty, singleton, adjacent/non-adjacent duplicates, null at start/middle/end.

**Invariant:** no elements lost beyond defined filter/deduplication steps; counts, order, and groups are right.

**Resource and lifecycle:** Streams are not reused; single-use iterators; I/O sources closed when needed.

**Concurrency:** if the pipeline is parallel or the source is concurrent, verify no races and no thread-order dependency.

**Domain policy:** distinguish "not found" from "load failed", "valid duplicate record" from "ID conflict", "allowed null" from "schema-violating null".

It is usually helpful to organize tests into clear groups: `emptySource`, `singletonSource`, `nullSource`, `nullElements`, `duplicateValues`, `duplicateBusinessKeys`, `parallelOrderedResult`, and `customSpliterator`. Good naming helps maintainers immediately understand why a test case failed.

## 19. Common mistakes and fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Testing only multi-element lists | Misses empty/singleton | Test matrix by size 0, 1, n |
| `findFirst().get()` on empty source | Empty Optional | `orElse`/`orElseThrow` per policy |
| Thinking `allMatch` on empty is false | Stream quantifier logic | Assert `true` and validate non-empty separately |
| Confusing null List with List containing null | Different timing/failure | Test both inputs separately |
| Using `List.of(null)` to build fixtures | Factory forbids null | Use `Arrays.asList`/`ArrayList` if nullable fixture is needed |
| Treating `Stream.of((String)null)` as empty | Actually has one null element | Use `Stream.ofNullable` if empty is wanted |
| `map(String::trim)` before null filtering | NPE on encountering null | Filter/validate first |
| Thinking `Stream.toList` forbids null | API allows null | Contrast with `toUnmodifiableList` |
| `groupingBy(Function.identity())` with null | Null classifier key is invalid | Normalize key or fail fast |
| `distinct` before normalize | Semantic duplicates not removed | Normalize first |
| `distinct` on record to deduplicate IDs | Record equality includes all components | `map(Order::id)` or group by ID |
| `toMap` without merge on duplicate keys | `IllegalStateException` | Check/handle conflicts or merge explicitly |
| Using `Collectors.toSet` then asserting order | Set result does not guarantee order | `distinct().toList()` on an ordered stream |
| Using `HashMap.toString()` as exact expected | Key order is not guaranteed | Assert per entry or use an ordered map |
| Tests only print to console | Do not fail automatically on error | Use assertions and fail clearly |
| Catching any exception and passing | Other bugs are also treated as right | Assert exact exception type |
| Falsely advertising `DISTINCT`/`NONNULL` on Spliterator | Can cause wrong optimizations | Metadata must reflect actual source |
| Reusing stream after terminal | Stream already consumed | Create a fresh stream source |
| Dropping duplicates with `distinct` on auditable data | Hides errors or loses counts | Keep raw input, count and validate per domain |
| Asserting parallel thread order | Non-deterministic scheduling | Assert output/properties, not logs |

## 20. Practice exercises

1. Write a result table for `Stream.<Integer>empty().count()`, `findFirst()`, `anyMatch`, `allMatch`, and `noneMatch`. Explain why `allMatch` is true on empty.
2. With `List.of("A")`, test `limit(0)`, `limit(1)`, `skip(1)`, `distinct`, and `findFirst`. Note the return type of each terminal.
3. Create source `Arrays.asList("A", null, "B")`. Try `map(String::trim)` before and after `filter(Objects::nonNull)`; which case throws NPE?
4. Compare `Stream.of((String)null).count()` with `Stream.ofNullable((String)null).count()`. Why is one 1 and the other 0?
5. Try `Stream.of((String)null).findFirst()` and test the exception type; why can Optional not represent a "present" null value?
6. Use `Collectors.groupingBy(Function.identity())` on a source containing null; fix it with key `"MISSING"` when business rules allow.
7. Create `List.of("Java"," java ","JAVA")`, try `distinct` before normalization and after normalization. Write expected results.
8. Create `record Order(String id,int amount)` with two records sharing the same ID but different amounts. Why does `distinct()` on the record differ from `map(Order::id).distinct()`?
9. Use `groupingBy(Function.identity(), counting())` to count `[a,b,a,c,a]`. Verify counts a=3, b=1, c=1.
10. Use `toMap` with two `"x"` keys. Test `IllegalStateException` then define a merge function that sums frequencies.
11. Write a unit test with `assertThrows` for `List.of((String)null)` and another test for `Collectors.toUnmodifiableList` containing null.
12. Create a custom `Iterable` returning three elements `["x","x",null]`. Use `StreamSupport` and a null-filtering/`distinct` pipeline; expected is `["x"]`.
13. Create a custom Spliterator accurately advertising `ORDERED`/`SIZED`, testing empty/singleton/multi-element, `tryAdvance`, and `trySplit`.
14. Compare `List.of("b","a","b").parallelStream().distinct().toList()` with `HashSet.stream().toList()`. When should result order be asserted?
15. Use `TreeMap::new` with `groupingBy` and write expected output with ordered keys. Why should you not rely on `HashMap` order?
16. Write a policy for imported data: exact duplicate records are skipped, same ID with different content reports a conflict, missing ID fails. Choose an appropriate pipeline/collector and test cases.
17. Write a test on controlled generated data to check the invariant that total count after `groupingBy` equals input size (when no filtering occurs).
18. Create a mutable `List<String>` source that is null, then a valid list containing a null element. Write two separate tests and explain the policy when the source does not exist.
19. If a run fails because a file source cannot be opened, should it return `Stream.empty()` as if it were truly empty data? State the business difference and how to report the error.
20. Convert `StreamEdgeCasesDemo` into separate JUnit tests for each data category; keep expected-exception cases and do not depend on parallel execution order.

## 21. Stream test acceptance checklist

- Are there tests for **0 elements, 1 element, and multiple elements**?
- Are **null source** and **null elements in the source** clearly separated?
- Is the policy for `null` to keep, filter, replace, or report an error? Do the tests reflect that?
- Is `Stream.of(null)` distinguished from `Stream.ofNullable(null)`?
- Are both exact value duplicates and **duplicate business keys** tested?
- Does `distinct` use equality for the right purpose? Is normalization applied first if needed?
- Can `groupingBy`/`toMap` encounter null keys or duplicates? Is the handling rule specified?
- Are terminals returning Optional on empty explicitly handled?
- Are `anyMatch`/`allMatch`/`noneMatch` tested on empty?
- Are count preservation, no unintended data loss, and ordering on ordered sources tested?
- Are assertions used instead of only printing results to stdout?
- Are expected exceptions pinned per contract, avoiding catching all errors and passing by default?
- Are custom sources, `tryAdvance`/`trySplit`/characteristics tested if using StreamSupport?
- Are assertions on `HashMap`/`HashSet` order and parallel mapper execution schedules avoided?
- Are I/O error handling, lifecycle, and retries tested at the appropriate layer if data comes from external sources?
- Is the seed/input recorded when using randomly generated data to reproduce failing cases?

**Conclusion:** To test Java Stream pipelines reliably, actively test **empty sources**, **single elements**, **null sources or elements**, and **duplicate values/keys**. Every scenario must have a clear expected result or expected exception. Use `Objects::nonNull`/`Stream.ofNullable` when policy allows dropping null, `distinct` after normalization when semantic deduplication is needed, and `groupingBy`/`toMap` with appropriate duplicate-key rules. Automated assertions and invariant checks matter far more than glancing at stdout once and seeing something that "looks right".
