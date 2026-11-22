# Testing Empty, Single-Element, Duplicate, and Null Sources

In the **Java Stream API**, a pipeline using `filter`, `map`, `flatMap`, `distinct`, `reduce`, or `collect` can work cleanly on sample datasets of hundreds of records, yet fail when given **0 elements, 1 element, duplicate elements, or `null` values**. These boundary cases expose hidden assumptions: "there is always a first element," "every field is non-null," "keys are always unique," or "an average always exists."

This lesson belongs to the **Debugging and Testing Pipelines** chapter of the `JAVA_STREAM_API` module. Its goal is to design a reproducible test suite, distinguish behavior **guaranteed by the API** from behavior observed only by chance, and assert on pipeline outputs instead of relying on how many times a lambda was called.

In particular, you will learn how to define the **business policy** for duplicate or missing data. The fact that `filter(Objects::nonNull)` runs without throwing does not prove that silently dropping records is the right choice for a real system.

## 1. Build a Test Matrix Before Writing Assertions

Suppose we need to normalize product codes, filter valid codes, and compute per-code statistics. Test at least these scenarios:

| Input category | Example | What to verify |
| --- | --- | --- |
| **Empty source** | `[]` | No access to non-existent elements; identity and `Optional` behavior are right. |
| **Single valid element** | `[" SKU-01 "]` | Element is normalized and retained exactly once. |
| **Single filtered-out element** | `["   "]` | Pipeline returns empty; no blind `get(0)` calls. |
| **Exact duplicates** | `["A", "A"]` | Either keep all, `distinct`, count, or fail per requirements. |
| **Duplicates after normalization** | `[" a ", "A"]` | Distinguish two raw strings from one normalized `"A"` key. |
| **`null` element** | `["A", null]` | Drop, replace, reject, or deliberately retain `null`. |
| **`null` field inside object** | `Item(null, 2)` | Handle missing fields explicitly, not just `filter` non-null objects. |
| **All elements filtered out** | `[null, " ", ""]` | Post-filter output is empty even though the source was not. |

A pipeline can receive a non-empty input and **become empty after `filter`**. Therefore, testing both an empty source and **an empty intermediate result** is necessary.

General rule: specify **the expected value, expected exception, or business error indicator** for each case. Never test merely "no exception thrown" when the business requires exact data.

## 2. Constructing Test Sources Properly

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

Stream<String> empty = Stream.empty();
Stream<String> singleton = Stream.of("A");
Stream<String> duplicates = Stream.of("A", "A", "B");

// Arrays.asList can contain null elements.
List<String> withNull = Arrays.asList("A", null, "B");
Stream<String> nullableElements = withNull.stream();

// Collections.emptyList also creates an empty source.
List<String> emptyList = Collections.emptyList();
```

**Never use `List.of("A", null)` to create a source containing null**: `List.of` (Java 9+) rejects `null` at list construction time. If your goal is testing a pipeline that receives null elements, pick a source that actually **permits nulls** such as `Arrays.asList` or `Stream.of((String) null)`.

```java
import java.util.stream.Stream;

Stream<String> oneNull = Stream.of((String) null);
System.out.println(oneNull.count()); // 1
```

Casting `(String) null` makes clear this is **a single null element**. Avoid bare `Stream.of(null)` because of varargs overloads, which cause warnings or misinterpretation.

### Distinguishing `Stream.empty()` and `Stream.ofNullable`

`Stream.ofNullable(value)` (Java 9+) returns **0 elements if value is null**, whereas `Stream.of((String) null)` creates **1 null element**:

```java
import java.util.stream.Stream;

String absent = null;

System.out.println(Stream.ofNullable(absent).count());   // 0
System.out.println(Stream.of((String) absent).count());  // 1
System.out.println(Stream.ofNullable("A").count());      // 1
```

These are two different contracts; do not swap them without checking requirements. When business logic distinguishes "one empty row" from "zero rows," the difference between `0` and `1` matters greatly.

## 3. Empty Sources: `Optional`, Identities, and Short-Circuiting Operations

Terminal operations behave differently when no elements are present:

| Terminal operation | On an empty source | Notes |
| --- | --- | --- |
| `count()` | `0L` | Needs no elements to count. |
| `IntStream.sum()` | `0` | Empty sum equals the additive identity. |
| `IntStream.average()` | `OptionalDouble.empty()` | No observable average exists. |
| `IntStream.min()` / `max()` | `OptionalInt.empty()` | No min/max exists. |
| `Stream.findFirst()` / `findAny()` | `Optional.empty()` | Never call `get()` when absent. |
| `reduce(identity, op)` | Returns `identity` | Identity must match the associative operation. |
| `reduce(op)` | `Optional.empty()` | No identity was provided. |
| `anyMatch(p)` | `false` | No element matches `p`. |
| `allMatch(p)` | `true` | *Vacuously* true (no counterexample exists). |
| `noneMatch(p)` | `true` | No element matches `p`. |

Java 8+ examples:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

System.out.println(IntStream.empty().sum());      // 0
System.out.println(IntStream.empty().count());    // 0

OptionalInt minimum = IntStream.empty().min();
System.out.println(minimum.isPresent());           // false

System.out.println(Stream.<Integer>empty()
    .anyMatch(n -> n > 0));                        // false
System.out.println(Stream.<Integer>empty()
    .allMatch(n -> n > 0));                        // true
System.out.println(Stream.<Integer>empty()
    .noneMatch(n -> n > 0));                       // true
```

`allMatch == true` on an empty source does not mean the system verified **at least one** valid record. If business logic requires *data exists and all records pass*, check **non-emptiness as well**:

```java
import java.util.List;

List<Integer> scores = List.of();

boolean atLeastOneAndAllPassed =
    !scores.isEmpty() && scores.stream().allMatch(n -> n >= 60);

System.out.println(atLeastOneAndAllPassed); // false
```

For single-use sources (such as I/O), you cannot call two terminal operations on **the same stream** to check `count()` and `allMatch()`. Design an appropriate collector instead, or inspect data once collected into a re-traversable structure.

### Do not confuse an identity with a measured value

`sum() == 0` on an empty source is an algebraic rule; it does **not** mean a value of 0 was observed. Likewise, `LongSummaryStatistics.getAverage()` on an empty summary returns `0.0` by contract, so reporting code should check `getCount() == 0` before treating the average as an actual measurement.

## 4. Empty Sources When Collecting: `groupingBy` vs. `partitioningBy`

`groupingBy` creates groups only for elements actually classified, whereas `partitioningBy` **always** has both Boolean keys even when the source is empty:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, List<String>> groups = Stream.<String>empty()
    .collect(Collectors.groupingBy(s -> s));

Map<Boolean, List<String>> partitions = Stream.<String>empty()
    .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(groups.isEmpty());             // true
System.out.println(partitions.size());             // 2
System.out.println(partitions.get(true).isEmpty());  // true
System.out.println(partitions.get(false).isEmpty()); // true
```

This test catches bugs where code calls `groups.get("SKU-01").size()`: when a group doesn't exist, `get` returns `null`. With `partitioningBy`, both Boolean keys always exist, though **the downstream value in each branch** still depends on the supplied downstream collector.

## 5. Single Element: Testing Start, End, and Boundary Thresholds

A single-element source is the simplest way to catch assumptions like "a pair of elements," "at least two records," and boundary conditions.

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" sku-01 ")
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .toList();

System.out.println(normalized);          // [SKU-01]
System.out.println(normalized.size());   // 1
System.out.println(normalized.get(0));   // SKU-01
```

In this Java 16+ example, `Stream.toList()` returns an **unmodifiable** list. If a mutable list is required, use an appropriate collector/supplier; never assume `toList()` behaves like `new ArrayList<>()`.

Also test exact boundary thresholds:

```java
import java.util.stream.Stream;

System.out.println(Stream.of(60).filter(n -> n >= 60).count()); // 1
System.out.println(Stream.of(60).filter(n -> n > 60).count());  // 0
```

This catches common **off-by-one** bugs. For pipelines using windowing, pairwise grouping, or differences between adjacent elements, a single element may yield **zero results** or a special result; read the operation's contract carefully rather than guessing.

### Avoid unsafe access to the first element

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<String> first = Stream.<String>empty().findFirst();

System.out.println(first.orElse("KHÔNG CÓ DỮ LIỆU"));
// KHÔNG CÓ DỮ LIỆU

// Avoid calling first.get() when the Optional may be empty.
```

`Optional` expresses **presence or absence of an element**. If the first element itself can be `null`, `findFirst()` can throw `NullPointerException`, as analyzed in the null section.

## 6. Duplicate Data: Choose One Explicit Policy

There are at least four distinct problems involving duplicate elements:

| Requirement | Appropriate API | Result for `["A","A","B"]` |
| --- | --- | --- |
| Keep every record | No deduplication | `[A, A, B]` |
| Unique values | `distinct()` | `[A, B]` |
| Frequency counts | `groupingBy(identity(), counting())` | `A -> 2, B -> 1` |
| Fail on duplicate keys when building a map | `toMap(key, value)` without merger | Throws `IllegalStateException` on duplicate keys. |

Example:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> unique = Stream.of("A", "A", "B", "A")
    .distinct()
    .toList();

Map<String, Long> frequencies = Stream.of("A", "A", "B", "A")
    .collect(Collectors.groupingBy(
        Function.identity(),
        Collectors.counting()
    ));

System.out.println(unique);               // [A, B]
System.out.println(frequencies.get("A")); // 3
System.out.println(frequencies.get("B")); // 1
```

`distinct()` determines equality via `Object.equals`. For a stream with an encounter order, `distinct` is stable: it keeps **the first occurrence** among equal elements. Do not assume the same ordering for unordered sources; parallel execution may require extra state and cost to maintain stability.

### Duplicates after normalization are often trickier than raw duplicates

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

List<String> uniqueCodes = Stream.of(" sku-01 ", "SKU-01", "sku-02")
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .distinct()
    .toList();

System.out.println(uniqueCodes); // [SKU-01, SKU-02]
```

If `distinct()` is placed **before** normalization, `" sku-01 "` and `"SKU-01"` remain different and both pass through. Thus the order of `normalize` and `distinct` is part of the business contract.

If an order has a duplicate ID, silently calling `distinct` can **drop a transaction needed for reconciliation**. Many systems must raise an error, preserve both records and their source positions, or apply an explicit merge rule. Tests must verify that exact policy, not merely "expect the count to shrink."

## 7. `equals` and `hashCode` Define What `distinct` Means

Two objects with different references are not necessarily different by value:

```java
import java.util.List;
import java.util.stream.Stream;

record Product(String sku, int quantity) {}

List<Product> unique = Stream.of(
        new Product("A", 1),
        new Product("A", 1),
        new Product("A", 2)
    )
    .distinct()
    .toList();

System.out.println(unique.size()); // 2
```

A `record` derives `equals`/`hashCode` from **all its value components**; two `Product("A", 1)` instances are equal, while `Product("A", 2)` is distinct. If business logic treats **only `sku`** as the unique key, `distinct()` over the whole `Product` **does not meet the requirement**.

When uniqueness by a specific key is required, group by that key, use `toMap` with a defined merge function, or build a dedicated duplicate-detection structure. Never write `filter(x -> seen.add(x.sku()))` with a shared `HashSet` and run `parallel()`: that introduces side effects, race hazards, and schedule-dependent output.

If you define mutable classes and mutate fields used in `equals`/`hashCode` while a pipeline runs, `distinct` or hash-based collectors can produce wrong results. Keep keys immutable and avoid source interference.

## 8. `Collectors.toMap`: Do Not Silently Discard Duplicate Keys

`toMap(keyMapper, valueMapper)` **throws `IllegalStateException`** if multiple elements produce the same key. This behavior is worth testing when keys must be unique:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A");

// Error: key "A" appears twice.
// Map<String, String> result = codes.stream()
//     .collect(Collectors.toMap(Function.identity(), Function.identity()));
```

When duplicate keys are permitted, provide an explicit merge function:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A");

Map<String, Long> counts = codes.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        ignored -> 1L,
        Long::sum,
        LinkedHashMap::new
    ));

System.out.println(counts.get("A")); // 2
System.out.println(counts.get("B")); // 1
```

A `Long::sum` merger makes sense when **counting records per key**. To keep the latest record, base the rule on a timestamp or version; do not write `(oldValue, newValue) -> newValue` merely to silence the exception without defining what "latest" means.

In parallel streams, the merge function must also match how partial results combine. Relying on an external mutable counter or a non-associative merger can make outputs depend on execution scheduling.

## 9. `null`: Null Elements, Null Fields, and Null Sources Are Three Separate Problems

Distinguish all three:

1. **The source collection itself is null:** calling `source.stream()` throws `NullPointerException`.
2. **A non-null list containing a null element:** `stream()` succeeds, yet a mapper may dereference null.
3. **A non-null object with a null field inside:** `filter(Objects::nonNull)` does not catch missing inner fields.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList(" A ", null, " B ");

List<String> cleaned = raw.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .toList();

System.out.println(cleaned); // [A, B]
```

**Operation order matters**: placing `map(String::strip)` before `filter(Objects::nonNull)` invokes a method on null and throws `NullPointerException`.

### When input positions must be preserved

`filter(Objects::nonNull)` is not always right. If the second row of a data table is missing yet you must preserve row/column alignment:

```java
import java.util.Arrays;
import java.util.List;

List<String> raw = Arrays.asList(" A ", null, " B ");

List<String> withPlaceholders = raw.stream()
    .map(s -> s == null ? "(MISSING)" : s.strip())
    .toList();

System.out.println(withPlaceholders);
// [A, (MISSING), B]
```

When the application needs to report errors with line numbers, a better design is **preserving source indices** and returning a success/failure result type. Dropping rows with `filter` shifts the indices of remaining elements away from original line numbers.

### Use `Objects.requireNonNull` to catch contract violations

If the application specifies **the source must never be null**, a clear exception is better than silently treating null as an empty source:

```java
import java.util.List;
import java.util.Objects;

static long countPresent(List<String> source) {
    Objects.requireNonNull(source, "source");
    return source.stream()
        .filter(Objects::nonNull)
        .count();
}
```

In this design, a null **collection** is a programming bug caught immediately; a null **element** is data skipped according to a chosen policy. Do not conflate the two conditions.

## 10. How `null` Affects `findFirst`, `sorted`, `groupingBy`, and Collectors

Several operations behave unexpectedly when encountering `null`:

| Operation | With null | What to test |
| --- | --- | --- |
| `map(String::strip)` | Throws `NullPointerException` when mapper receives null. | Filter or handle null beforehand. |
| `findFirst()` / `findAny()` | Throws `NullPointerException` if selected element is null. | Never assume `Optional` can wrap null. |
| `sorted()` with natural order | Null cannot be compared via natural ordering. | Filter null or pass a null-safe comparator. |
| `groupingBy(classifier)` | Classifier cannot return a null key. | Normalize/assign a sentinel key or reject the record. |
| `toMap(keyMapper, valueMapper)` | Rejects null mapped values per collector contract. | Validate values before collecting into the map. |
| `List.of` / `List.copyOf` | Rejects null elements. | Never use them to construct test data containing nulls. |
| `Collectors.toUnmodifiableList()` | Rejects null elements. | Filter, replace, or reject with reason. |
| `mapToInt` unboxing `Integer` | Unboxing null throws `NullPointerException`. | Define policy for missing numbers. |

Example catching the error when `findFirst` encounters a null element:

```java
import java.util.stream.Stream;

// Throws NullPointerException because the selected element is null:
// Stream.of((String) null).findFirst();

System.out.println(Stream.ofNullable((String) null)
    .findFirst().isEmpty()); // true; isEmpty() since Java 11
```

Example sorting with nulls:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

List<String> ordered = Stream.of("B", null, "A")
    .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
    .toList();

System.out.println(ordered); // [A, B, null]
```

Do not treat `null` as a "default group" in `groupingBy`. If business logic wants missing data grouped under its own key, state it explicitly:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> counts = Arrays.asList("API", null, "UI", null)
    .stream()
    .collect(Collectors.groupingBy(
        s -> s == null ? "(UNKNOWN)" : s,
        Collectors.counting()
    ));

System.out.println(counts.get("(UNKNOWN)")); // 2
```

Choose `"(UNKNOWN)"` only when that string **cannot collide with a valid data key**. In systems requiring strict distinction, an enum or dedicated missing-state type is safer than a magic string.

## 11. A Realistic Pipeline for Testing All Four Input Categories

Let's build a small pipeline taking raw item rows. Each row has a SKU code and quantity; goals:

- Drop null rows or rows with null required fields.
- Normalize SKU using `strip()` and `toUpperCase(Locale.ROOT)`.
- Drop blank SKUs or non-positive quantities.
- **Retain rows with duplicate SKUs**, since the cleaned list still represents individual transactions.
- To count duplicate occurrences, call a separate aggregation method.

Complete example (Java 17+ for `record` and `Stream.toList()`):

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class ItemPipeline {
    private ItemPipeline() {}

    public record RawItem(String sku, Integer quantity) {}
    public record Item(String sku, int quantity) {}

    public static List<Item> clean(List<RawItem> rows) {
        Objects.requireNonNull(rows, "rows");

        return rows.stream()
            .filter(Objects::nonNull)
            .filter(row -> row.sku() != null
                && row.quantity() != null)
            .map(row -> new Item(
                row.sku().strip().toUpperCase(Locale.ROOT),
                row.quantity()
            ))
            .filter(item -> !item.sku().isEmpty()
                && item.quantity() > 0)
            .toList();
    }

    public static Map<String, Long> countBySku(List<Item> items) {
        Objects.requireNonNull(items, "items");

        return items.stream()
            .collect(Collectors.groupingBy(
                Item::sku,
                Collectors.counting()
            ));
    }
}
```

This example's contract is intentionally **simple** to focus on boundary-case testing, not a full production ingestion standard. It merely drops invalid rows without keeping `Reject(rowNumber, reason)`; financial or reconciliation applications must record rejected rows with reasons rather than dropping them silently.

`clean` is a pure transformation over an input not mutated during execution. `countBySku` aggregates normalized keys. Using `Map<String, Long>` lets tests compare **map contents**, independent of `HashMap` iteration order.

## 12. JUnit 5 Tests: Empty, Single-Element, Duplicate, and Null Cases

The example below uses **JUnit Jupiter 5**; the parameterized test requires the `junit-jupiter-params` module. Place the test file in a JUnit-configured project in the same package as `ItemPipeline` (or add the appropriate package/imports). Build commands aren't needed in the lesson to explain the semantics.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class ItemPipelineTest {

    @Test
    void emptyInputProducesEmptyResults() {
        List<ItemPipeline.Item> result =
            ItemPipeline.clean(List.of());

        assertTrue(result.isEmpty());
        assertTrue(ItemPipeline.countBySku(result).isEmpty());
    }

    @Test
    void singletonValidItemIsNormalizedOnce() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(new ItemPipeline.RawItem(" sku-9 ", 1))
        );

        assertEquals(
            List.of(new ItemPipeline.Item("SKU-9", 1)),
            result
        );
        assertEquals(Map.of("SKU-9", 1L),
            ItemPipeline.countBySku(result));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "\t"})
    void blankOrNullSkuIsRejected(String rawSku) {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(new ItemPipeline.RawItem(rawSku, 2))
        );

        assertTrue(result.isEmpty());
    }

    @Test
    void duplicateSkusRemainTwoTransactions() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(
                new ItemPipeline.RawItem(" a ", 2),
                new ItemPipeline.RawItem("A", 3)
            )
        );

        assertEquals(2, result.size());
        assertEquals(
            Map.of("A", 2L),
            ItemPipeline.countBySku(result)
        );
    }

    @Test
    void collectingDuplicateSkusIntoUniqueMapFails() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(
                new ItemPipeline.RawItem("A", 1),
                new ItemPipeline.RawItem("a", 2)
            )
        );

        assertThrows(IllegalStateException.class,
            () -> result.stream().collect(Collectors.toMap(
                ItemPipeline.Item::sku,
                Function.identity()
            )));
    }

    @Test
    void nullRowsAndFieldsFollowTheDeclaredPolicy() {
        List<ItemPipeline.RawItem> input = Arrays.asList(
            null,
            new ItemPipeline.RawItem(null, 2),
            new ItemPipeline.RawItem("A", null),
            new ItemPipeline.RawItem("A", 1),
            new ItemPipeline.RawItem("B", 0)
        );

        assertEquals(
            List.of(new ItemPipeline.Item("A", 1)),
            ItemPipeline.clean(input)
        );
    }

    @Test
    void nullSourceIsAProgrammingError() {
        assertThrows(NullPointerException.class,
            () -> ItemPipeline.clean(null));
    }
}
```

Reviewing what each test proves:

| Test name | What it proves |
| --- | --- |
| `emptyInputProducesEmptyResults` | Empty source causes no invalid element access; summary map is empty. |
| `singletonValidItemIsNormalizedOnce` | One valid row becomes one `Item` with normalized SKU and count = 1. |
| `blankOrNullSkuIsRejected` | Null/empty/whitespace SKUs are dropped per the example's policy. |
| `duplicateSkusRemainTwoTransactions` | Two transactions with the same SKU **are not deduplicated**; summary count = 2. |
| `collectingDuplicateSkusIntoUniqueMapFails` | When a unique-key map is required, duplicates fail explicitly. |
| `nullRowsAndFieldsFollowTheDeclaredPolicy` | Distinguishes null rows, null fields, and non-positive quantities. |
| `nullSourceIsAProgrammingError` | Contract does not silently treat a null collection as an empty list. |

In real test suites, also add Unicode inputs, over-length codes, very large quantities, rejected records with reasons, and multi-field duplicate policies. Those cases depend on **business rules**, not arbitrary error assumptions.

## 13. Testing Exceptions: Verify Failure at the Right Spot

A common mistake is catching overly broad `Exception` and passing the test regardless of what failed. Assert **the exact exception type**, and where appropriate, application-defined error messages or error codes:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class NullOperationTest {
    @Test
    void findFirstCannotWrapSelectedNull() {
        assertThrows(NullPointerException.class,
            () -> Stream.of((String) null).findFirst());
    }
}
```

For `Collectors.toMap`, tests can assert `IllegalStateException` on duplicate keys, while **avoiding brittle checks against exact JDK message text** if the API does not guarantee message stability across releases.

With `List.of(null)`, the exception occurs **when creating the source**, not inside `filter` or `collect`. Pinpoint the exact failing step so you don't misdiagnose the pipeline.

If business logic requires **preserving invalid records**, use a `Valid/Invalid` result (or an error-carrying record) rather than `assertThrows` for every bad input. Exceptions fit contract violations and unexpected failures; malformed input data may be an expected outcome.

## 14. Do Not Use `peek` or Side Effects as Primary Assertions

Stream pipelines are **lazy**: callbacks run only when a terminal operation demands results. Optimizations can even **omit callback execution** when it does not affect the terminal result.

```java
import java.util.List;

long count = List.of("A", "B", "C")
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// No guarantee peek will print A, B, or C.
```

Because `List` has a known size, a Stream implementation can compute `count()` **without traversing elements**. Tests must never assert "`peek` ran exactly three times" or "`map` always runs once per element" when that behavior is not part of the contract.

With short-circuiting operations like `findFirst`, `anyMatch`, and `limit`, the pipeline may stop early. On parallel streams, the framework may also process additional elements before producing the final result. **Assert guaranteed results and constraints**, not callback counts or incidental log order.

During debugging, `peek` can help temporarily for observation, while primary tests should rely on pure transformations and deterministic outputs.

## 15. Recreate the Stream for Each Check; Never Reuse a Closed Stream

A `Stream` instance can be operated upon **only once** after a terminal operation. Wrong example:

```java
import java.util.stream.Stream;

Stream<Integer> source = Stream.of(1, 2, 3);
long count = source.count();

// Cannot reuse the same Stream after a terminal operation:
// int sum = source.mapToInt(Integer::intValue).sum();
```

When testing the same data with multiple operations, create a fresh stream from a re-traversable source:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3);
long count = source.stream().count();
int sum = source.stream().mapToInt(Integer::intValue).sum();

System.out.println(count); // 3
System.out.println(sum);   // 6
```

Or use `Supplier<Stream<T>>` in tests:

```java
import java.util.function.Supplier;
import java.util.stream.Stream;

Supplier<Stream<String>> createStream =
    () -> Stream.of("A", "B", "C");

System.out.println(createStream.get().count());       // 3
System.out.println(createStream.get().findFirst());   // Optional[A]
```

The `Supplier` must return **a new stream**, never the same consumed stream. If the source is `Files.lines`, creating a new stream re-opens the file; wrap each read in `try-with-resources` and keep in mind the file contents could change between reads.

## 16. Testing Parallel Sources: Right Output, No Schedule Dependence

In a parallel pipeline, lambdas can run across multiple workers out of encounter order. Therefore:

- Never assert that `forEach` runs actions in a fixed order.
- Never use an external shared `ArrayList` inside `parallel().forEach(list::add)` to gather results.
- Never use a predicate depending on an external counter to assign records to groups.
- For `distinct` on ordered sources, test **value and order contracts** if needed; on unordered sources, assert only what is genuinely guaranteed.
- For `groupingByConcurrent`, do not assume value lists preserve encounter order.
- For floating-point numbers, parallel reduction sums can differ slightly due to addition order; apply an appropriate tolerance rather than brittle bit-for-bit equality when unnecessary.

Example testing grouping correctness:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Long> counts = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 4,
        Collectors.counting()
    ));

System.out.println(counts);
// Each key 0,1,2,3 has exactly 2500 elements.
```

Never compare `Map.toString()` as if it had a fixed order. Compare using `Map.equals`, `counts.get(key)`, or per-group counts.

For this lesson's goals, first verify **all boundary cases pass sequentially**. Then run in parallel when the algorithm and source fit, checking semantic equivalence rather than assuming deterministic execution scheduling.

## 17. Property-Based Checks Instead of Just a Few Hand-Picked Examples

**Invariants** often catch bugs better than a single "happy" input list. For example:

| Invariant | Applicability | How to check |
| --- | --- | --- |
| `filter` never increases count | Pipeline only filters and adds nothing | `result.size() <= input.size()`. |
| `distinct` never increases count | Elements have stable `equals` | `unique.size() <= input.size()`. |
| `distinct` is idempotent | No element mutation between calls | `distinct(distinct(xs)).equals(distinct(xs))` when ordered. |
| Normalization is idempotent | Normalization function is designed so | `normalize(normalize(x)).equals(normalize(x))`. |
| Group sizes sum to source size | Every element belongs to one group | Sum of group `counting()` equals initial element count. |
| `partitioningBy` preserves count | Every element goes to one side | `trueCount + falseCount == input.size()`. |
| Scheduling independence | Pure functions and non-interfering source | Sequential and parallel match per contract. |

Example of a small invariant check for `distinct`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> input = Arrays.asList("A", "B", "A", null, null);

List<String> first = input.stream().distinct().toList();
List<String> second = first.stream().distinct().toList();

if (!first.equals(second)) {
    throw new AssertionError("distinct không idempotent");
}
if (first.size() > input.size()) {
    throw new AssertionError("distinct tăng số phần tử");
}
System.out.println(first); // [A, B, null]
```

`distinct` can retain a `null` element in a reference stream; yet another terminal operation like `findFirst` rejects selecting `null`. That is why `null` cannot be tested with a single blanket assertion across all Stream operations.

For business domains, also test inputs with unstable `equals`/keys, consecutive duplicates, non-consecutive duplicates, post-normalization duplicates, all-null inputs, and nulls only at the start/end.

## 18. Workflow for Debugging a Failing Test

When a boundary-case test fails, follow this sequence:

1. **Reproduce with the minimal input**: usually `[]`, `[x]`, `[x,x]`, or `[null]` is enough.
2. **Locate the failing stage**: source creation, `map`, `filter`, terminal operation, or collector finisher.
3. **Check element types after each stage**: `map` might introduce null; `flatMap` might expand or shrink count.
4. **Read the terminal operation's contract**: some return `Optional`, some return an identity, some throw on null.
5. **Audit keys and equality**: `distinct` inspects whole elements; `groupingBy`/`toMap` inspect mapper-produced keys.
6. **Decide whether dropped rows must be reported**: if so, replace silent `filter` with a reason-carrying result model.
7. **Optimize only after correctness**: `parallel`, concurrent collectors, or caches can make bugs harder to reproduce.

Never "quick-fix" every crash by sprinkling `filter(Objects::nonNull)` everywhere. If `null` signals an important issue (such as a missing transaction ID), dropping it silently can corrupt aggregate totals without warning.

## 19. Practice Exercises

**Exercise 1 — Empty truth.** Predict the results of `anyMatch`, `allMatch`, and `noneMatch` on `Stream.empty()`. Explain why `allMatch` returning `true` does not prove any record was checked. Write a condition requiring **at least one element** and all matching.

**Exercise 2 — Single element and threshold.** With `Stream.of(60)`, compare `filter(n -> n >= 60)` and `filter(n -> n > 60)`. Add tests for `59`, `60`, and `61`.

**Exercise 3 — Duplicates before/after normalization.** With `[" SKU-01 ", "sku-01", "SKU-02"]`, inspect the result when `distinct` sits before vs. after `strip().toUpperCase(Locale.ROOT)`. Which fits if SKUs are case-insensitive?

**Exercise 4 — Duplicate keys in `toMap`.** Create two `Item`s with the same SKU and different quantities. Verify the two-mapper overload throws `IllegalStateException`, then build a summed quantity map using `Integer::sum`. Explain why a merge policy is required.

**Exercise 5 — Nulls across three layers.** Distinguish `source == null`, `source = Arrays.asList("A", null)`, and `RawItem(null, 2)`. Pick an explicit policy for each: contract error, skip element, or record rejection.

**Exercise 6 — `findFirst` with null.** Try `Stream.of((String) null).findFirst()` and `Stream.ofNullable((String) null).findFirst()`. Which creates a single null element, and which creates an empty stream? Why do the results differ?

**Exercise 7 — Parameterized JUnit test.** Add a `@ParameterizedTest` for SKUs `null`, `""`, `" "`, `"a"`, and `" A "`. Note which cases produce an `Item` and which are dropped.

**Exercise 8 — Parallel test.** Run `IntStream.range(0, 10_000).parallel().boxed().collect(groupingBy(n -> n % 4, counting()))` and verify four groups of 2,500 elements each. Do not compare printed map strings or lambda call schedules.

**Exercise 9 — Preserving invalid rows.** Extend `ItemPipeline.clean` to return `ImportResult(accepted, rejected)` preserving `rowNumber`/`reason` for each rejected row. Test the invariant `accepted.size() + rejected.size() == source.size()`.

## 20. Pre-Production Pipeline Testing Checklist

- [ ] Tested empty sources **and** empty results after filtering.
- [ ] Tested single-element sources, single filtered-out elements, and boundary values.
- [ ] Tested literal duplicates, non-adjacent duplicates, and post-normalization duplicates.
- [ ] Verified which `equals/hashCode` or business key defines duplication.
- [ ] `toMap` has an explicit duplicate-key policy; exceptions are never swallowed arbitrarily.
- [ ] Distinguished null collections, null elements, and null fields.
- [ ] Explicitly chose between dropping nulls, replacing nulls, and recording errors with reasons.
- [ ] Never assumed `findFirst` or `min` always has a value; properly checks `Optional`.
- [ ] Tested `allMatch` on empty sources and checked "at least one" when needed.
- [ ] Never used `List.of` to construct test data containing nulls.
- [ ] Did not rely on `peek`/`map` callback counts or log order in lazy pipelines.
- [ ] Never reused the same `Stream` after a terminal operation.
- [ ] Never used shared mutable state inside parallel lambdas.
- [ ] Assertions target values/exceptions/contracts, not unguaranteed map iteration order.
- [ ] Considered real rejected rows requiring audit trails and data-quality metrics.

**Remember:** Good Stream API testing goes beyond running one clean list through `collect`—it must exercise **empty sources, single elements, duplicates, and nulls**. Distinguish empty results from errors, algebraic identities from measured values, `equals`-based duplicates from key-based duplicates, and nulls at each data layer. Write assertions against well-defined contracts, preserve rejection reasons when reconciliation requires them, and evaluate performance or parallelization only after sequential correctness is proven.

**References:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [Collectors — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Collectors.html), [Objects — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/Objects.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
