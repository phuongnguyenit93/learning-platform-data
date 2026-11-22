# Preserving Key Order with `LinkedHashMap` and Sorting with `TreeMap`

## 1. Why Must Collecting into a `Map` Care About Order?

In the Java Stream API, a pipeline typically filters and transforms records with `filter` and `map`, then uses `collect` to produce a result. When the output is a `Map<K,V>`, not only does **which key maps to which value** matter, sometimes **the iteration order of keys** is also part of the business requirement.

For example, a stream of orders arrives in region order:

```text
O-1: HN, 120_000
O-2: HCM, 80_000
O-3: HN, 30_000
O-4: DN, 50_000
```

After summing amounts by region, we need one of two results:

- **Preserve first-appearance region order:** `HN → HCM → DN`. Useful for reports that must preserve source order.
- **Iterate keys in sorted order:** `DN → HCM → HN`. Useful for lookup tables and displays ordered by region code.

These two needs use two different map types:

| Requirement | Typical choice |
| --- | --- |
| **Insertion order** of keys | `LinkedHashMap` |
| **Sorted key order** by comparison | `TreeMap` |
| Only key → value mapping needed, no ordering requirement | Ordinary `Map`, possibly chosen by the collector |

**Lesson goal:** read and properly use `Collectors.toMap` and `Collectors.groupingBy` overloads with a `mapFactory` parameter; choose between `LinkedHashMap` and `TreeMap`; handle duplicate keys; design comparators; test ordering; and recognize limits regarding `null`, parallel streams, resources, and performance.

Note: *stream element encounter order* and *map key iteration order* are two separate concepts. A `List` having an encounter order does not make a `HashMap` automatically iterate in that order.

## 2. Three `Map` Types and Their Ordering Promises

### 2.1. `HashMap`: no guarantee on iteration order

`HashMap` provides efficient key lookup in many cases, but **does not guarantee** the iteration order over `keySet()`, `values()`, or `entrySet()`. Seeing a run produce "insertion-like" or "sorted-like" order is purely coincidental.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> map = new HashMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);

System.out.println(map.keySet());
// Cannot predict the exact order solely from put order.
```

Therefore, if software must export CSV, JSON, or display tables in a defined order, **do not rely on `HashMap` iteration order**.

### 2.2. `LinkedHashMap`: preserves insertion order

In its default mode, `LinkedHashMap` maintains the order in which keys were first inserted into the map:

```java
import java.util.LinkedHashMap;
import java.util.List;

LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);
map.put("HN", 99); // Updates value of an existing key.

System.out.println(List.copyOf(map.keySet()));
// [HN, HCM, DN]
System.out.println(map.get("HN")); // 99
```

Re-inserting an existing key with `put` does not change that key's position in an **insertion-order `LinkedHashMap`**. This is especially useful when a collector encounters multiple records sharing the same key yet must keep the first-appearance position.

**Exception to distinguish:** `LinkedHashMap` has a constructor accepting an `accessOrder` parameter. When created with `accessOrder = true`, access operations such as `get` can move an entry to the end. This lesson uses the **default insertion mode** (`new LinkedHashMap<>()`), not access-order mode, for reporting input order.

### 2.3. `TreeMap`: keys are traversed according to a comparator

`TreeMap` is a `NavigableMap` that maintains keys in **natural order** or according to a supplied `Comparator`:

```java
import java.util.List;
import java.util.TreeMap;

TreeMap<String, Integer> map = new TreeMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);

System.out.println(List.copyOf(map.keySet()));
// [DN, HCM, HN]
```

It does not matter that `HN` was added before `DN`: `TreeMap` uses key comparison, not insertion time. Thus, "using `TreeMap`" **does not mean** "preserving element encounter order".

### 2.4. Quick comparison table

| Property | `HashMap` | Default `LinkedHashMap` | `TreeMap` |
| --- | --- | --- | --- |
| Key iteration order | No guarantee | First-insertion order | By key/comparator order |
| Typical `put/get` operation | Average near `O(1)` | Average near `O(1)` | `O(log n)` |
| `firstKey()/lastKey()` | Not available | Not a `SortedMap` API | Available |
| Relies on hash/equals | Yes | Yes | Relies on comparator/`compareTo` |
| Automatically sorts by **value**? | No | No | No, sorts by **key** |
| Best suited for | Order-agnostic lookups | Reports in appearance order | Key-ordered lookups/range queries |

These complexities describe typical map operations; actual performance depends on entry count, key distribution, `hashCode`/comparator cost, allocation, and memory access patterns.

## 3. The `Collectors.toMap` Overload with `mapFactory`

To select the result map type at collection time, use the four-argument overload:

```java
<T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
)
```

Breaking down each parameter:

| Parameter | Purpose |
| --- | --- |
| `keyMapper` | Extracts key `K` from element `T` |
| `valueMapper` | Extracts value `U` from element `T` |
| `mergeFunction` | Merges two `U` values on **duplicate keys** |
| `mapFactory` | Creates the result map of concrete type `M` |

Why is `mergeFunction` required? Because multiple elements may share the same key. Without specifying how to merge, the two-argument `toMap` overload throws `IllegalStateException` on duplicate keys.

With `mapFactory`, we can explicitly request `LinkedHashMap` or `TreeMap` instead of relying on whatever concrete type the default collector returns.

## 4. Complete Example: Total Revenue with Two Key Orders

Example runnable directly on **JDK 17 or later**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderedRevenueDemo {

    public record Order(String id, String region, long amountVnd) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0L) {
                throw new IllegalArgumentException("Invalid Order");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 120_000L),
            new Order("O-2", "HCM", 80_000L),
            new Order("O-3", "HN", 30_000L),
            new Order("O-4", "DN", 50_000L)
        );
    }

    public static LinkedHashMap<String, Long> totalsInSourceOrder(
        List<Order> orders
    ) {
        return orders.stream().collect(Collectors.toMap(
            Order::region,
            Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));
    }

    public static TreeMap<String, Long> totalsBySortedKey(
        List<Order> orders
    ) {
        return orders.stream().collect(Collectors.toMap(
            Order::region,
            Order::amountVnd,
            Long::sum,
            TreeMap::new
        ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        Map<String, Long> byEncounter = totalsInSourceOrder(orders);
        Map<String, Long> byKey = totalsBySortedKey(orders);

        System.out.println(List.copyOf(byEncounter.keySet()));
        // [HN, HCM, DN]
        System.out.println(List.copyOf(byKey.keySet()));
        // [DN, HCM, HN]

        System.out.println(byEncounter.get("HN")); // 150000
        System.out.println(byKey.get("HN"));       // 150000
        System.out.println(byEncounter.equals(byKey)); // true
    }
}
```

**Reading the pipeline step by step:**

1. `orders.stream()` is a `Stream<Order>` with encounter order from `List`.
2. `Order::region` produces `String` keys.
3. `Order::amountVnd` produces `Long` values via `long` autoboxing.
4. `Long::sum` merges amounts when two orders share the same region.
5. `LinkedHashMap::new` or `TreeMap::new` determines **key iteration order**.
6. `collect(...)` is the terminal operation; the result is a map, no longer a stream.

Two maps can be `equals` because `Map.equals` compares the set of key–value mappings and **does not consider iteration order part of equality**. If ordering must be tested, compare `List.copyOf(map.keySet())` or an ordered list of entries.

**Monetary note:** the example uses `long` units and `Long::sum` to focus on key ordering. `Long::sum` does not automatically detect overflow; if values can exceed `long`, choose an appropriate numeric type or arithmetic policy. Using `LinkedHashMap`/`TreeMap` does not alter that arithmetic risk.

## 5. Preserving Key Order with `groupingBy`

`Collectors.groupingBy` typically returns `Map<K,List<T>>` or `Map<K,D>` with a downstream collector. The three-argument overload accepts `mapFactory`:

```java
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Mental model: **classify** elements into keys, **create the map** via the factory, then **collect each key's values** using the downstream collector.

### 5.1. `LinkedHashMap` + `toList`: grouping in appearance order

Using `Order` and `sample()` from `OrderedRevenueDemo` in Section 4:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

LinkedHashMap<String, List<OrderedRevenueDemo.Order>> grouped =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderedRevenueDemo.Order::region,
            LinkedHashMap::new,
            Collectors.toList()
        ));

System.out.println(List.copyOf(grouped.keySet()));
// [HN, HCM, DN]
System.out.println(
    grouped.get("HN").stream().map(
        OrderedRevenueDemo.Order::id
    ).toList()
); // [O-1, O-3]
```

For a **sequential stream with encounter order**, a key seen for the first time is inserted into `LinkedHashMap` first. Subsequent elements with the same key are fed into the downstream collector and update its value; the key is not re-inserted when the group already exists.

### 5.2. `TreeMap` + `counting`: grouping and sorting by key

```java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> orderCountByRegion =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderedRevenueDemo.Order::region,
            TreeMap::new,
            Collectors.counting()
        ));

System.out.println(List.copyOf(orderCountByRegion.keySet()));
// [DN, HCM, HN]
System.out.println(orderCountByRegion.get("HN")); // 2
```

The downstream type changes from `List<Order>` to `Long`, while `TreeMap` still governs the order of **group keys**.

### 5.3. Comparing `toMap` and `groupingBy`

| Requirement | How to express it |
| --- | --- |
| Each element has a key and value, keys may collide | `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` |
| Want to retain **all records** per group | `groupingBy(classifier, mapFactory, toList())` |
| Want to count, sum, or compute stats per group | `groupingBy(classifier, mapFactory, downstream)` |
| Want keys in first-seen order | `LinkedHashMap::new` |
| Want keys ordered by comparator | `TreeMap::new` or a supplier creating a TreeMap with a comparator |

Do not confuse **map key order** with **element order inside downstream `List`s**: those are two separate contracts that must be evaluated by encounter order as well as collector characteristics.

## 6. Duplicate Keys: Key Position and Value Merging Are Separate Decisions

Suppose the source has three records in order:

```text
("HN", 10), ("HCM", 20), ("HN", 30)
```

With default `LinkedHashMap`, the key order is `[HN, HCM]`. However, the value for `HN` depends on `mergeFunction`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String key, int value) {}

List<Entry> rows = List.of(
    new Entry("HN", 10),
    new Entry("HCM", 20),
    new Entry("HN", 30)
);

Map<String, Integer> keepFirst = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        (oldValue, newValue) -> oldValue,
        LinkedHashMap::new
    ));

Map<String, Integer> keepLast = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        (oldValue, newValue) -> newValue,
        LinkedHashMap::new
    ));

Map<String, Integer> sumValues = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        Integer::sum,
        LinkedHashMap::new
    ));

System.out.println(keepFirst.get("HN"));  // 10
System.out.println(keepLast.get("HN"));   // 30
System.out.println(sumValues.get("HN"));  // 40
System.out.println(List.copyOf(keepLast.keySet())); // [HN, HCM]
```

**Important note:** "keep the later value" (`keepLast`) **does not mean** "move the key to the end of the map" (default `LinkedHashMap` still keeps the initial insertion position). If business logic requires ordering by last update, define a different algorithm; do not infer that from `(old, newer) -> newer`.

### 6.1. When should duplicate keys throw an error?

If keys are unique identifiers, any duplication may be a data error. Do not silently pick one to merge:

```java
Map<String, Entry> unique = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        java.util.function.Function.identity(),
        (first, second) -> {
            throw new IllegalArgumentException(
                "Duplicate key: " + first.key()
            );
        },
        LinkedHashMap::new
    ));
// With the current rows, the terminal operation will throw an exception.
```

For data with truly unique keys, the two-argument overload `toMap(keyMapper,valueMapper)` also fits, but **does not let you specify a `mapFactory`**; if ordering is also required, use the four-argument overload as shown above.

### 6.2. Merging needs a contract for parallel execution

For a collector used on a parallel stream, the result must match the sequential result per the collector contract. Choose a merge operation that is **associative** and matches business rules. `Long::sum` and `Integer::sum` are associative under modular integer addition; if overflow must be detected via `Math.addExact`, define the policy when totals exceed the representable range. For `double`, merge order can alter rounding errors.

Operations like subtraction `(a,b) -> a-b` are not associative, making them prone to wrong results when pipeline chunks are split and merged.

## 7. Sorting `TreeMap` by Natural Order or Comparator

`TreeMap` uses the key's `Comparable` implementation or a comparator. There is no need to sort the stream beforehand:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> ascending =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            TreeMap::new
        ));

System.out.println(List.copyOf(ascending.keySet()));
// [DN, HCM, HN]
```

### 7.1. Reversing key order

Pass the comparator in the supplier:

```java
import java.util.Comparator;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> descending =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            () -> new TreeMap<String, Long>(Comparator.reverseOrder())
        ));

System.out.println(List.copyOf(descending.keySet()));
// [HN, HCM, DN]
```

Here the comparator changes **how TreeMap iterates and identifies equivalent keys**, not merely creating a different display view.

### 7.2. Multi-field keys

Suppose a key has two parts: region code and year. A record used as a key gets generated `equals`/`hashCode`, but **does not automatically implement `Comparable`**; to store it in a `TreeMap`, provide a comparator:

```java
import java.util.Comparator;
import java.util.TreeMap;

record RegionYear(String region, int year) {}

Comparator<RegionYear> byRegionThenYear =
    Comparator.comparing(RegionYear::region)
        .thenComparingInt(RegionYear::year);

TreeMap<RegionYear, Long> revenue = new TreeMap<>(byRegionThenYear);
revenue.put(new RegionYear("HN", 2026), 100L);
revenue.put(new RegionYear("DN", 2025), 200L);
revenue.put(new RegionYear("HN", 2025), 300L);

System.out.println(List.copyOf(revenue.keySet()));
// [RegionYear[region=DN, year=2025],
//  RegionYear[region=HN, year=2025],
//  RegionYear[region=HN, year=2026]]
```

Multi-level comparators must accurately reflect business meaning; for example, you can change `thenComparingInt(RegionYear::year)` to a reversed year comparator if the report needs newer years first.

### 7.3. Comparator determines **duplicate** keys

`TreeMap` treats two keys as equivalent when the comparator returns `0`. This can differ from `equals`:

```java
import java.util.TreeMap;

TreeMap<String, Integer> insensitive =
    new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

insensitive.put("hn", 10);
insensitive.put("HN", 20);

System.out.println(insensitive.size());    // 1
System.out.println(insensitive.get("hn")); // 20
```

This is not just a display-order change: the two strings `"hn"` and `"HN"` have become **the same key** inside `TreeMap`. With `Collectors.toMap`, they trigger `mergeFunction`; with `groupingBy`, they belong to the same group according to the comparator.

**Rule:** a sorted map's comparator should be **consistent with `equals`** if full adherence to the `Map` contract is desired. If data must merge codes case-insensitively, it is usually safer to **normalize keys upfront** (e.g., `strip().toUpperCase(Locale.ROOT)`), then use a comparator suited for normalized keys. Do not use a comparator that compares only string length if two distinct codes of the same length must remain separate.

## 8. What If You Want to Sort by **Value**?

`TreeMap` sorts only by **key**, not automatically by revenue or quantity. If the requirement is "region with highest revenue first", one approach is to sort the **entry** stream by value and collect into a `LinkedHashMap`:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> source = OrderedRevenueDemo.totalsBySortedKey(
    OrderedRevenueDemo.sample()
);

LinkedHashMap<String, Long> byRevenueDescending = source.entrySet()
    .stream()
    .sorted(
        Map.Entry.<String, Long>comparingByValue(
            Comparator.reverseOrder()
        ).thenComparing(Map.Entry.comparingByKey())
    )
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue,
        (left, right) -> left,
        LinkedHashMap::new
    ));

System.out.println(List.copyOf(byRevenueDescending.keySet()));
// [HN, HCM, DN] (150000, 80000, 50000)
```

Here `sorted` orders by **value descending**, then **key ascending** to break ties deterministically. `LinkedHashMap` preserves the exact entry order supplied by `sorted`. Using `TreeMap` in the final step would defeat the goal of "sorting by value", because `TreeMap` sorts by key again.

If you only need to output a ranked list, you do not have to collect back into a map:

```java
List<Map.Entry<String, Long>> ranking = source.entrySet()
    .stream()
    .sorted(
        Map.Entry.<String, Long>comparingByValue().reversed()
            .thenComparing(Map.Entry.comparingByKey())
    )
    .toList();
```

**Remember:** `Map.equals` can still report two maps as equal despite different orders; test sorting via lists of keys or entries.

## 9. Operation Order: `filter`, `map`, `sorted`, and `collect`

A correct pipeline depends on step ordering. Consider the initial `Order` data from Section 4.

### 9.1. Filter first, then preserve key appearance order

```java
LinkedHashMap<String, Long> onlyLargeOrders =
    OrderedRevenueDemo.sample().stream()
        .filter(order -> order.amountVnd() >= 50_000L)
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));

System.out.println(List.copyOf(onlyLargeOrders.keySet()));
// [HN, HCM, DN]
```

With other data, if a region's first record is removed by `filter`, the **first appearance after filtering** determines that key's position in `LinkedHashMap`. That order follows the **collector's input stream**, not necessarily the raw collection.

### 9.2. Sort elements first, then keep post-sort key order

```java
LinkedHashMap<String, Long> byRegionOfSortedRows =
    OrderedRevenueDemo.sample().stream()
        .sorted(java.util.Comparator.comparing(
            OrderedRevenueDemo.Order::region
        ))
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));

System.out.println(List.copyOf(byRegionOfSortedRows.keySet()));
// [DN, HCM, HN]
```

In this case `LinkedHashMap` still does not "sort itself"; `sorted` established a new encounter order. If the goal is merely sorting **result keys**, using `TreeMap` in the collector is usually more direct and avoids sorting all source elements.

### 9.3. Sources without encounter order

If the source is a `HashSet` or the pipeline called `unordered()`, "first-seen key" is no longer a stable concept. `LinkedHashMap` still preserves the collector's **actual insertion order**, but that order is not necessarily guaranteed to satisfy business requirements. To achieve deterministic order, define an explicit sort or start from a source with an encounter order.

## 10. Empty Sources, `null` Keys, and `null` Values

### 10.1. Empty sources

With `LinkedHashMap::new` or `TreeMap::new`, collecting an empty source returns an empty map of the requested type:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

LinkedHashMap<String, Integer> emptyInsertion =
    List.<String>of().stream()
        .collect(Collectors.toMap(
            s -> s,
            String::length,
            Integer::sum,
            LinkedHashMap::new
        ));

TreeMap<String, Integer> emptySorted =
    List.<String>of().stream()
        .collect(Collectors.toMap(
            s -> s,
            String::length,
            Integer::sum,
            TreeMap::new
        ));

System.out.println(emptyInsertion.isEmpty()); // true
System.out.println(emptySorted.isEmpty());    // true
```

There is no need to wrap the result in `Optional<Map<...>>` just because the map might be empty; an empty `Map` already expresses "no elements to collect". If you need to distinguish "no records" from "query source failed", model the error state separately.

### 10.2. `null` keys

`TreeMap` using `String` natural ordering rejects `null` keys. `Collectors.groupingBy` also rejects classifiers returning `null` keys in standard JDK implementations rather than creating a `null` group. Do not extrapolate from `HashMap` allowing one null key to assume every collector overload shares that contract.

An explicit policy:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record SourceRow(String region, long amount) {}

List<SourceRow> rows = List.of(
    new SourceRow(null, 10L),
    new SourceRow(" hn ", 20L)
);

Map<String, Long> totals = rows.stream()
    .collect(Collectors.toMap(
        row -> row.region() == null
            ? "UNKNOWN"
            : row.region().strip().toUpperCase(Locale.ROOT),
        SourceRow::amount,
        Long::sum,
        TreeMap::new
    ));

System.out.println(List.copyOf(totals.keySet()));
// [HN, UNKNOWN]
```

If `"UNKNOWN"` could be a real region code, consider a dedicated key type or rejecting records missing a region rather than silently conflating the two cases. Normalization is only valid when permitted by the domain.

### 10.3. `null` values

With standard `Collectors.toMap`, do not pass a `valueMapper` that can return `null`; common JDK implementations throw `NullPointerException` instead of storing it in the map. Decide explicitly whether to **drop the record**, **substitute** a valid default value, or **throw an error**.

```java
// Example: reject missing amount by validating beforehand:
record Payment(String id, Long amount) {}

List<Payment> payments = List.of(
    new Payment("P1", 10L),
    new Payment("P2", null)
);

// payments.stream().collect(Collectors.toMap(
//     Payment::id, Payment::amount, Long::sum, LinkedHashMap::new
// )); // NullPointerException on standard JDKs.
```

If every record must have an amount, fail when constructing `Payment` or validate at the source boundary. If missing data may be skipped, `filter(payment -> payment.amount() != null)` is an explicit choice before `collect`.

## 11. Mutability, Copying, and Preserving Order After Returning Results

`LinkedHashMap` and `TreeMap` obtained as shown are **mutable**. Callers can invoke `put`/`remove`, which may be undesirable if this is a finalized report result.

### 11.1. Creating an unmodifiable snapshot that preserves order

`Collections.unmodifiableMap` creates an **unmodifiable view** of a map. To ensure nobody else retains a reference to the mutable map and alters the underlying order or contents, copy first:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

LinkedHashMap<String, Long> mutable =
    OrderedRevenueDemo.totalsInSourceOrder(OrderedRevenueDemo.sample());

Map<String, Long> immutableSnapshot = Collections.unmodifiableMap(
    new LinkedHashMap<>(mutable)
);

System.out.println(List.copyOf(immutableSnapshot.keySet()));
// [HN, HCM, DN]
// immutableSnapshot.put("HP", 10L); // UnsupportedOperationException
```

If you call `Collections.unmodifiableMap(mutable)` **without copying**, code elsewhere still holding `mutable` can mutate the underlying map. The wrapper does not make the original map immutable.

### 11.2. `Map.copyOf` and `Collectors.toUnmodifiableMap`

`Map.copyOf(source)` and `Collectors.toUnmodifiableMap` return unmodifiable maps, but **do not guarantee preserving the key iteration order of a source `LinkedHashMap`**. If ordering is part of the display contract, do not use them and claim `keySet()` will iterate in the prior order.

For `TreeMap`, if you need a snapshot that is **unmodifiable while keeping key order**, you can use:

```java
import java.util.Collections;
import java.util.SortedMap;
import java.util.TreeMap;

TreeMap<String, Long> sorted =
    OrderedRevenueDemo.totalsBySortedKey(OrderedRevenueDemo.sample());

SortedMap<String, Long> sortedSnapshot =
    Collections.unmodifiableSortedMap(new TreeMap<>(sorted));

System.out.println(List.copyOf(sortedSnapshot.keySet()));
// [DN, HCM, HN]
```

Unmodifiable views also do not imply that **value** objects inside the map are immutable. If a value is an `ArrayList` or mutable DTO, consider deep copying or designing immutable value types.

## 12. Parallel Streams and Ordering Guarantees

Ordinary `LinkedHashMap` and `TreeMap` are **not safe for concurrent updates by multiple threads**. However, `Collectors.toMap(..., mapFactory)` and `groupingBy(..., mapFactory, downstream)` are not concurrent collectors by default: when running in parallel, the framework may create separate accumulation maps and merge them via the combiner.

```java
Map<String, Long> totals = OrderedRevenueDemo.sample()
    .parallelStream()
    .collect(Collectors.toMap(
        OrderedRevenueDemo.Order::region,
        OrderedRevenueDemo.Order::amountVnd,
        Long::sum,
        LinkedHashMap::new
    ));
```

With `Long::sum` and non-overflowing values, total revenue per key is an aggregation independent of merge order. However, for a report that **guarantees key order by first source appearance**, the clearest approach is an **ordered sequential stream** with `LinkedHashMap`, or sorting the result by deterministic criteria. Do not generalize the ordering behavior of a sequential snippet into a contract for unverified parallel collectors/pipelines.

### 12.1. Do not swap `groupingBy` to `groupingByConcurrent`

`Collectors.groupingByConcurrent` is designed for concurrent accumulation and has `CONCURRENT`/`UNORDERED` characteristics; concurrent maps/accumulators target parallel scalability and **do not directly replace** the need for insertion-order preservation via `LinkedHashMap`. Likewise, `toConcurrentMap` does not provide key iteration order based on source appearance.

When key ordering is a business requirement, parallel optimization must be measured and verified separately. Often, moderate datasets, simple merges, and strict ordering requirements are easier to maintain when collected sequentially.

### 12.2. Do not use shared state outside the collector

Avoid:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Long> shared = new LinkedHashMap<>();
// Counterexample:
// orders.parallelStream().forEach(order ->
//     shared.merge(order.region(), order.amountVnd(), Long::sum)
// );
```

`LinkedHashMap` is not safe for concurrent writes from multiple threads. Using `collect` with a properly contracted supplier and combiner keeps mutable state **inside the collector** instead of letting `forEach` mutate a shared map.

## 13. Performance and Memory Costs

### 13.1. `LinkedHashMap`

Key insertion or lookup is typically near `O(1)` on average; insertion order is tracked via links between entries. Compared to an unordered map, it generally requires extra memory for link pointers. Iterating entries in insertion order is convenient for reports, but it is not **sorting** data.

### 13.2. `TreeMap`

`TreeMap` uses a balanced tree structure, with search/insert/delete typically `O(log n)`. It provides key-range operations such as `subMap`, `headMap`, `tailMap`, `firstKey`, and `lastKey`. If key-ordered lookup and traversal are needed frequently, maintaining order inside the map can be more convenient than repeatedly converting a map to a list and sorting it.

### 13.3. `sorted` before `LinkedHashMap`

A `stream.sorted(...).collect(toMap(..., LinkedHashMap::new))` pipeline may have to buffer and sort all source elements before collecting; the cost is typically around `O(n log n)` for sorting, with intermediate memory depending on the implementation. If only the **result keys** need sorting and the number of keys is much smaller than the element count, `TreeMap` in the collector is usually more direct.

### 13.4. Grouping many elements

`groupingBy(..., toList())` retains all elements of every group and can consume significant memory. If only `count` or `sum` is needed, use downstream `counting()` or `summingLong()` to hold smaller state. If the source is an I/O stream from `Files.lines`, close the source with `try-with-resources` even when the terminal operation is `collect`; the memory cost of the result is a separate concern.

**Optimize based on measurements.** When concurrency, many elements, expensive comparators, or high key-collision rates are involved, benchmark with representative data instead of assuming `LinkedHashMap` is always faster than `TreeMap`. The primary goal is a correct output contract.

## 14. Testing Key Order, Duplicate Keys, and Edge Cases

With JUnit 5, test both **values** and **key order**. Example using `OrderedRevenueDemo` from Section 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;

class OrderedRevenueDemoTest {

    @Test
    void linkedHashMapKeepsFirstKeyEncounterOrder() {
        LinkedHashMap<String, Long> actual =
            OrderedRevenueDemo.totalsInSourceOrder(
                OrderedRevenueDemo.sample()
            );

        assertEquals(List.of("HN", "HCM", "DN"),
            List.copyOf(actual.keySet()));
        assertEquals(150_000L, actual.get("HN"));
        assertEquals(3, actual.size());
    }

    @Test
    void treeMapSortsByKeyNotBySourceOrder() {
        TreeMap<String, Long> actual =
            OrderedRevenueDemo.totalsBySortedKey(
                OrderedRevenueDemo.sample()
            );

        assertEquals(List.of("DN", "HCM", "HN"),
            List.copyOf(actual.keySet()));
        assertEquals(50_000L, actual.get("DN"));
    }

    @Test
    void mapEqualityDoesNotTestIterationOrder() {
        var sample = OrderedRevenueDemo.sample();
        var insertion = OrderedRevenueDemo.totalsInSourceOrder(sample);
        var sorted = OrderedRevenueDemo.totalsBySortedKey(sample);

        assertEquals(insertion, sorted);
        // Yet keySet() has different orders:
        assertTrue(!List.copyOf(insertion.keySet())
            .equals(List.copyOf(sorted.keySet())));
    }

    @Test
    void emptySourceReturnsRequestedMapType() {
        var empty = List.<OrderedRevenueDemo.Order>of();

        assertTrue(OrderedRevenueDemo.totalsInSourceOrder(empty).isEmpty());
        assertTrue(OrderedRevenueDemo.totalsBySortedKey(empty).isEmpty());
    }

    @Test
    void duplicateKeyChangesValueNotFirstPosition() {
        var source = OrderedRevenueDemo.sample();
        var map = OrderedRevenueDemo.totalsInSourceOrder(source);

        assertEquals(List.of("HN", "HCM", "DN"),
            List.copyOf(map.keySet()));
        assertEquals(120_000L + 30_000L, map.get("HN"));
    }
}
```

**Cases to add:** lowercase/uppercase keys with a case-insensitive comparator, sources with `null` elements, value mappers returning `null`, empty data after `filter`, key order after `sorted`, keep-first/keep-last merge functions, comparators inconsistent with equals, mutability of the returned map, and overflow policies.

**Do not rely solely on `assertEquals(map1,map2)` to verify traversal order**, because two maps can compare equal even when one preserves insertion order and the other uses sorted order. Do not test combiner invocation counts or scheduling to infer parallel ordering.

## 15. Practice Exercises

### Exercise 1 — Preserve region appearance order

Given:

```java
record Sale(String region, long amount) {}
List<Sale> sales = List.of(
    new Sale("HCM", 10),
    new Sale("HN", 20),
    new Sale("HCM", 30),
    new Sale("DN", 40)
);
```

Write a four-argument `Collectors.toMap` using `LinkedHashMap::new` and `Long::sum` to produce `[HCM, HN, DN]` when iterating keys, with total `HCM = 40`. Try adding an `HN` transaction at the end of the source and demonstrate that the key position of `HN` does not change.

### Exercise 2 — Group and sort by key

From `sales` in Exercise 1, use `Collectors.groupingBy(Sale::region, TreeMap::new, Collectors.counting())`. Verify the order `[DN, HCM, HN]` and the result `HCM = 2`.

### Exercise 3 — Choose a merge policy

Suppose configuration data has three records `("timeout",10)`, `("retries",2)`, `("timeout",30)`. Collect into a `LinkedHashMap` under three policies: first value wins, last value wins, and error on duplicate keys. Explain why last value wins does not change the position of `timeout`.

### Exercise 4 — Unusual comparator

Create a `TreeMap<String,Integer>` with `String.CASE_INSENSITIVE_ORDER`; call `put("hn",1)` then `put("HN",2)`. Predict the map size and explain why the comparator affects identifying **equal keys**. Propose a region-code normalization design to avoid ambiguity.

### Exercise 5 — Sort by value

From a regional revenue map, sort descending by revenue, break ties by region code ascending, and collect into a `LinkedHashMap`. Explain why replacing the target map with `TreeMap` breaks value-based ordering.

### Exercise 6 — Empty map and missing data

Given an empty source, inspect the map type created by the factory. Add a row with `region == null`, choose a policy to throw an error or map to `UNKNOWN`, and explain why you should not assume every collector supports null keys.

### Exercise 7 — Parallel

Compare total amounts between `stream()` and `parallelStream()` with `Long::sum` merging. Clearly analyze that **value per key** and **key iteration order** are two independent requirements; if order is mandatory, propose a sequential solution or an explicit result-sorting step and measure actual cost.

## 16. Decision Table

| What do you need? | Typically appropriate choice |
| --- | --- |
| Map from elements, **unique** keys | `toMap(keyMapper, valueMapper)` if no concrete map type is required |
| Map that may have duplicate keys, need accumulation | `toMap(key, value, merge, mapFactory)` |
| Keys ordered by **first appearance** | `LinkedHashMap::new` on a sequential stream with encounter order |
| Keys **ascending by comparator** | `TreeMap::new` or a supplier creating a TreeMap with a comparator |
| Keys descending | `() -> new TreeMap<>(Comparator.reverseOrder())` |
| Grouped map keeping elements per key | `groupingBy(classifier, LinkedHashMap::new, toList())` |
| Grouped map sorting keys and counting | `groupingBy(classifier, TreeMap::new, counting())` |
| Sort **values** descending | Sort `entrySet().stream()` by value then collect into `LinkedHashMap` |
| Disallow duplicate keys | Merge function throws an error |
| Missing values or null keys | Validate, filter, or normalize under an explicit policy |
| Result must be unmodifiable yet ordered | Copy of `LinkedHashMap`/`TreeMap` + corresponding unmodifiable wrapper |
| Want to use a concurrent collector | Carefully read `CONCURRENT`/`UNORDERED` and drop insertion-order assumptions unless guaranteed |

`LinkedHashMap` and `TreeMap` solve **two different kinds of ordering** when collecting data with the Java Stream API: one preserves key insertion order, the other maintains key comparison order. When combining `mapFactory` with `toMap` or `groupingBy`, specify the duplicate-key policy, key/value validity, actual source order, and mutability requirements as well. Clarifying those contracts makes reports, groupings, and custom collectors semantically sound, easy to test, and well-grounded for performance tuning.
