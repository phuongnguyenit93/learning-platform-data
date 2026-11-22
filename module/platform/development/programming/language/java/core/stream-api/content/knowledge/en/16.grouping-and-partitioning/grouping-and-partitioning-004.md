# Grouping by Composite Keys Using Value Objects

## 1. Problem Statement: A Single Attribute Is Not Enough to Define a Group

In the **Java Stream API**, `filter` and `map` select and transform elements; `collect` is the terminal operation used to gather data into a result. An important collector is `Collectors.groupingBy`: it classifies each element by a **group key** and accumulates elements sharing the same key.

Sometimes the group key consists of just one attribute, such as `department` or `year`. However, real-world reports often need to combine multiple criteria: revenue **by region and category**, order counts **by customer and month**, or academic results **by class and semester**.

If you only group by region, two product categories in the same region are merged together. If you only group by category, data from multiple regions gets mixed together. We need a **composite key** (*composite key*) containing both attributes.

```text
Orders
  ├─ (Miền Bắc, Sách, 100)
  ├─ (Miền Bắc, Bút,   30)
  ├─ (Miền Nam,  Sách,  80)
  └─ (Miền Bắc, Sách,  50)
          │
          ▼ classifier: Order -> GroupKey(region, category)
          │
          ▼ groupingBy
  ┌───────────────────────┬─────────────────┐
  │ Composite key         │ Order group     │
  ├───────────────────────┼─────────────────┤
  │ (Miền Bắc, Sách)      │ 100, 50         │
  │ (Miền Bắc, Bút)       │ 30              │
  │ (Miền Nam,  Sách)     │ 80              │
  └───────────────────────┴─────────────────┘
```

A safe and expressive way to represent a group key is to use a **value object** (*value object*): an object compared based on its component values rather than reference identity. In modern Java, `record` is ideally suited for this role.

After this lesson, you will be able to:

1. Create composite keys using `record` or an immutable class with `equals`/`hashCode`.
2. Use `groupingBy` to produce `Map<CompositeKey, List<T>>`.
3. Combine downstream collectors such as `counting`, `summingLong`, `mapping`, and `collectingAndThen` to compute per-key results.
4. Normalize key data; handle `null`; and define policies for ordering, parallelism, and memory cost.
5. Avoid mistakes such as concatenating strings as keys, using arrays as keys, or mutating keys after inserting them into a Map.

Complete examples use **Java 17+**, since `record` became a standard feature in Java 16. `Collectors.groupingBy` and Map key principles have existed since Java 8.

## 2. The groupingBy Mechanism and the Role of Keys

The basic overload of `groupingBy` is:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier)
```

`classifier` receives each input element `T` and returns a key `K`. Elements whose keys are **equal according to the resulting Map's mechanism** are gathered into the same group.

Example grouping by a single field:

```java
record Order(String id, String region, String category, long amount) {}

List<Order> orders = List.of(
        new Order("O01", "Bắc", "Sách", 100),
        new Order("O02", "Bắc", "Bút", 30),
        new Order("O03", "Nam", "Sách", 80),
        new Order("O04", "Bắc", "Sách", 50)
);

Map<String, List<Order>> byRegion = orders.stream()
        .collect(Collectors.groupingBy(Order::region));

System.out.println(byRegion.get("Bắc").size()); // 3
```

In `byRegion`, both book orders and pen orders in the Bắc region belong to the same group. To split further by category, the classifier must return **both attributes** in an appropriate key type.

`groupingBy` is a **Collector** passed to the `collect` terminal operation. Each element is classified by the classifier during collection; you do not need to manually build and iterate twice over an intermediate list. However, the internal organization and the number of partial result combines depend on whether the pipeline is sequential or parallel.

## 3. Designing a Composite Key with record

Define a small `record` holding the exact components that define group identity:

```java
record GroupKey(String region, String category) {}
```

Java automatically generates the constructor, `region()`/`category()` accessors, as well as `equals`, `hashCode`, and `toString` for the `record`. Two `GroupKey` objects are considered equal if **their corresponding components are equal**.

```java
GroupKey first = new GroupKey("Bắc", "Sách");
GroupKey second = new GroupKey("Bắc", "Sách");
GroupKey third = new GroupKey("Nam", "Sách");

System.out.println(first == second);      // false: two different references
System.out.println(first.equals(second)); // true: component values are equal
System.out.println(first.equals(third));  // false
System.out.println(first.hashCode() == second.hashCode()); // true
```

Because a Map typically uses `equals` and `hashCode` to manage keys, `record` semantics fit creating a new key from each order:

```java
Map<GroupKey, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));

GroupKey northBooks = new GroupKey("Bắc", "Sách");

System.out.println(groups.get(northBooks).size()); // 2
System.out.println(groups.size());                 // 3
```

Even though the classifier expression creates a new `GroupKey` object on every element, keys with equal values are grouped properly. Correctness **does not depend on reusing the same instance**.

### Why use a value object?

| Criterion | Key with `record GroupKey` | Key with manual string concatenation |
| --- | --- | --- |
| Structure | Dedicated field names and types | Must invent a delimiter convention |
| Equality check | Component-wise `equals`/`hashCode` | Compares the entire concatenated string |
| Extracting data | `key.region()`, `key.category()` | Must split the string to recover fields |
| Correctness | Reduces duplicate-key bugs from ambiguous encoding | Can collide if data contains the delimiter |
| Maintainability | Adding or changing field rules is explicit | Easy to produce string keys with inconsistent conventions |

Example of collision when concatenating strings without escaping rules:

```java
String a = "A:B" + ":" + "C"; // A:B:C
String b = "A" + ":" + "B:C"; // A:B:C

// Two different attribute pairs produce the same String key.
```

You should not solve this by adding ever more delimiter characters when the domain needs a multi-field key. A `record` or immutable value-key class expresses the intent much more clearly.

## 4. equals and hashCode Are the Core Contract

Two `GroupKey` instances with the same content must be recognized by the Map as the same key. For a standard `HashMap` structure:

- `hashCode` helps locate the bucket for the key; equal keys **must have the same hash code**.
- `equals` distinguishes keys that are genuinely equal, even when hash codes collide.
- Once placed in a Map, a key's components participating in `equals`/`hashCode` must remain **stable**.

`record` provides these methods automatically for its declared fields, though safety still depends on the component data types. `String`, `Integer`, `LocalDate`, and `enum` are common, stable choices.

### Do not use an array as a key if you want content-based comparison

`record` does not turn array comparison into element-by-element comparison:

```java
record BadKey(String[] fields) {}

BadKey a = new BadKey(new String[] {"Bắc", "Sách"});
BadKey b = new BadKey(new String[] {"Bắc", "Sách"});

System.out.println(a.equals(b)); // false
```

Two arrays are allocated separately; array `equals` does not compare contents like `Arrays.equals`. Furthermore, arrays can be mutated, making keys unstable. For a fixed number of known fields, declare two `String` components in `GroupKey`. For a dynamic number of fields, consider an immutable key object with an explicit equality definition.

### Do not use a mutable key object

```java
class MutableKey {
    String region;
    String category;

    MutableKey(String region, String category) {
        this.region = region;
        this.category = category;
    }

    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof MutableKey key)) return false;
        return java.util.Objects.equals(region, key.region)
                && java.util.Objects.equals(category, key.category);
    }

    @Override public int hashCode() {
        return java.util.Objects.hash(region, category);
    }
}

MutableKey key = new MutableKey("Bắc", "Sách");
Map<MutableKey, Integer> map = new java.util.HashMap<>();
map.put(key, 2);
key.region = "Nam"; // DESIGN ERROR: mutating a hash-contributing field after using it as a key
```

After the mutation, looking up `map.get(key)` can fail because the Map placed the entry under the old hash code. Do not use this pattern as a foundation for reports or caches. With a `record` containing only immutable components, this issue is avoided. **Records are only shallowly immutable:** if a component holds an array, list, or other mutable object, defensive copies and immutability rules are still required for that component.

## 5. Without record: Value Object Class on Java 8

In a codebase that must support Java 8, define a `final` class with `private final` fields, a constructor, getters, `equals`, and `hashCode`:

```java
import java.util.Objects;

public final class GroupKey {
    private final String region;
    private final String category;

    public GroupKey(String region, String category) {
        this.region = Objects.requireNonNull(region);
        this.category = Objects.requireNonNull(category);
    }

    public String getRegion() { return region; }
    public String getCategory() { return category; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof GroupKey)) return false;
        GroupKey that = (GroupKey) other;
        return region.equals(that.region)
                && category.equals(that.category);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, category);
    }
}
```

This sample class goes in `GroupKey.java` when used in a standard Java program. `region` and `category` are immutable strings, so the key's content is stable. In modern Java, `record GroupKey(String region, String category)` is usually shorter and less error-prone.

Do not rely on an object's `toString` as a Map key: a display string representation can change with class formatting, whereas `equals`/`hashCode` must accurately express the group's domain identity.

## 6. Grouping into Map<GroupKey, List<Order>>

The sample source has four orders, two of which share the same region and category pair:

```java
Map<GroupKey, List<Order>> byRegionAndCategory = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));

List<Order> northBooks = byRegionAndCategory.get(
        new GroupKey("Bắc", "Sách")
);

System.out.println(northBooks.stream().map(Order::id).toList());
// [O01, O04]
```

Key checkpoints:

1. The source element type is `Order`.
2. The classifier has the logical type `Function<Order, GroupKey>`.
3. The result is `Map<GroupKey, List<Order>>`.
4. Each key represents **one combination** of attributes; each value is the list of elements in that group.

`groupingBy(classifier)` does not guarantee a concrete implementation class or key iteration order for the resulting Map. To read a group, use `get(new GroupKey(...))`. To print a report in a stable order, define an explicit ordering rather than trusting `Map.toString()`.

If you need to check whether a group exists, use `containsKey` or `getOrDefault`; avoid calling methods directly on the result of `get` without considering the missing-key case:

```java
List<Order> westBooks = byRegionAndCategory.getOrDefault(
        new GroupKey("Tây", "Sách"),
        List.of()
);

System.out.println(westBooks.size()); // 0
```

When there are no orders for a combination, `groupingBy` **does not automatically create a key entry with an empty group**. If the report requires all `region × category` combinations, build the list of valid combinations or populate missing groups after collection.

## 7. Downstream Collectors: Counting and Summing by Composite Key

Sometimes you do not need to retain the full order objects. You only want **an aggregated number per key combination**. In that case, use the `groupingBy(classifier, downstream)` overload:

```java
Map<GroupKey, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.counting()
        ));

System.out.println(counts.get(new GroupKey("Bắc", "Sách"))); // 2
```

`Collectors.counting()` produces a `Long` count for each group; it does not allocate intermediate `List<Order>` objects like the default `groupingBy`.

Summing amounts by composite key:

```java
Map<GroupKey, Long> amountTotals = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.summingLong(Order::amount)
        ));

System.out.println(amountTotals.get(new GroupKey("Bắc", "Sách")));
// 150
```

In this case, `summingLong` receives each `Order` in the group and extracts `amount()`. If amounts represent real currency in the smallest unit, you can use `long` with overflow checks; if exact decimal arithmetic is needed, use `BigDecimal` with an appropriate accumulation operation.

### Collecting multiple metrics per group

`summarizingLong` computes count, sum, min, max, and average in a single collector:

```java
Map<GroupKey, LongSummaryStatistics> summaries = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.summarizingLong(Order::amount)
        ));

LongSummaryStatistics northBookStats =
        summaries.get(new GroupKey("Bắc", "Sách"));

System.out.println(northBookStats.getCount()); // 2
System.out.println(northBookStats.getSum());   // 150
System.out.println(northBookStats.getMin());   // 50
System.out.println(northBookStats.getMax());   // 100
```

`LongSummaryStatistics` is a **mutable accumulator object**. If the result is published to other code and you want to prevent mutation after collection, convert each statistics object into a dedicated immutable result value object in a finishing step:

```java
record Summary(long count, long totalAmount) {}

Map<GroupKey, Summary> immutableSummaries = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.collectingAndThen(
                        Collectors.summarizingLong(Order::amount),
                        stats -> new Summary(stats.getCount(), stats.getSum())
                )
        ));

System.out.println(immutableSummaries.get(
        new GroupKey("Bắc", "Sách")
)); // Summary[count=2, totalAmount=150]
```

`Summary` is a record with primitive fields, so the summary values themselves cannot be modified. The **outer Map can still be structurally modified** under the collector's default contract: if you need to publish an unmodifiable Map, create a copy with `Map.copyOf(immutableSummaries)` where appropriate.

## 8. Extracting Only Needed Fields per Group with mapping

If the report needs a list of **order IDs for each combination** rather than storing entire `Order` objects, use the `Collectors.mapping` downstream collector:

```java
Map<GroupKey, List<String>> idsByGroup = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.mapping(
                        Order::id,
                        Collectors.toList()
                )
        ));

System.out.println(idsByGroup.get(new GroupKey("Bắc", "Sách")));
// [O01, O04]
```

`groupingBy` determines the **group**, while `mapping` determines **which value is placed into each group**. You can also combine downstream `filtering` (Java 9+) or filter before `groupingBy`, depending on whether you want to drop the group entirely or keep a group with an empty downstream result.

For example, keeping only orders with `amount() >= 80` before grouping:

```java
Map<GroupKey, List<Order>> highValueGroups = orders.stream()
        .filter(order -> order.amount() >= 80)
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));
```

Combinations with no remaining elements after `filter` **will not appear** in the Map. If you use `Collectors.filtering` as the downstream of `groupingBy`, a key already encountered by the classifier can still exist with an empty Collection when none of the elements in that group pass the filter. This is a meaningful distinction when generating reports that must retain original groups.

## 9. Composite Key or Nested groupingBy?

The same problem can be solved using **nested `groupingBy`**:

```java
Map<String, Map<String, List<Order>>> nested = orders.stream()
        .collect(Collectors.groupingBy(
                Order::region,
                Collectors.groupingBy(Order::category)
        ));

System.out.println(nested.get("Bắc").get("Sách").size()); // 2
```

Comparing the two approaches:

| Aspect | Composite key `Map<GroupKey, List<Order>>` | Nested Map `Map<Region, Map<Category, ...>>` |
| --- | --- | --- |
| One key represents | A complete attribute combination | One level in the group hierarchy |
| Group lookup | `get(new GroupKey(r, c))` | `get(r).get(c)` after null checks |
| Iterating all combinations | Iterate entries of a single Map | Iterate each nested Map |
| Adding a third grouping field | Add a component to the value object | Typically requires adding another Map level |
| Querying by region alone | Must filter composite keys or maintain a separate index | Direct `nested.get(region)` lookup |
| Model readability | Suitable when the combination is a single group identity | Suitable for a region → category hierarchy |

Neither is always better. Choose a **composite key** when the attribute combination acts as a unified business key (report by month + branch, product group + region). Choose a **nested Map** when users typically navigate, aggregate, or display data level by level.

`groupingBy` and `partitioningBy` also differ. `partitioningBy(predicate)` creates two `Boolean` branches for true/false and always keeps both keys; it fits a binary condition and does not replace a composite key made of multiple independent attributes.

## 10. Normalizing Keys to Avoid Unintended Group Splitting

In real data, `"north"`, `" NORTH "`, and `"North"` might refer to the same region. A `record` only compares **actual field values** and does not automatically know business normalization rules.

```java
record RegionCategory(String region, String category) {}

List<Order> noisy = List.of(
        new Order("O10", "north", "Books", 20),
        new Order("O11", " NORTH ", "books", 30)
);

Map<RegionCategory, Long> before = noisy.stream()
        .collect(Collectors.groupingBy(
                o -> new RegionCategory(o.region(), o.category()),
                Collectors.counting()
        ));
System.out.println(before.size()); // 2: two distinct String keys
```

If the business treats those spellings as equivalent, normalize **before creating the key**:

```java
static String normalize(String value) {
    return value.strip().toUpperCase(java.util.Locale.ROOT);
}

// Placed in the same class that defines normalize:
Map<RegionCategory, Long> after = noisy.stream()
        .collect(Collectors.groupingBy(
                o -> new RegionCategory(
                        normalize(o.region()),
                        normalize(o.category())
                ),
                Collectors.counting()
        ));

System.out.println(after.size()); // 1
```

The normalization function should express a **data policy**, not a technical trick. For example, is uppercasing appropriate for case-sensitive codes? If components are `enum`s or IDs already normalized at the ingestion layer, calling `toUpperCase` may be unnecessary.

When original casing must be preserved for display, you can still keep the full `Order` in each group while `GroupKey` holds the normalized value. Avoid mutating the source object itself inside the classifier to achieve normalization.

## 11. Null in the Classifier and in Key Components

`Collectors.groupingBy` requires that **the value returned by the classifier must not be `null`**. If it returns `null`, the terminal operation throws `NullPointerException` (typically with a message about a null key).

```java
// WRONG: the classifier can return null.
Map<String, List<Order>> invalid = orders.stream()
        .collect(Collectors.groupingBy(o ->
                o.region().equals("Bắc") ? o.category() : null
        ));
```

However, distinguish **the entire key being null** from **a record key having a null component**. `new GroupKey(null, "Sách")` is still a non-null `GroupKey` object. A record allows null components by default; the record's `equals`/`hashCode` can handle them. Still, for clear data semantics, validate inputs or establish a convention for missing values:

```java
record StrictKey(String region, String category) {
    StrictKey {
        java.util.Objects.requireNonNull(region, "region");
        java.util.Objects.requireNonNull(category, "category");
    }
}
```

The compact constructor above rejects missing fields as soon as the key is created. If business rules allow an unknown region, map `null` to an `enum UNKNOWN` or a clearly defined placeholder value. Do not silently lump all kinds of invalid data into the same group if users need to tell the causes apart.

Note also: `Map.copyOf` and `toUnmodifiableMap` collectors reject null keys or values, whereas some mutable `Map` implementations may permit nulls. The output Map's null policy is separate from `groupingBy`'s classifier requirement.

## 12. Group Order, Element Order, and Choosing the Map

By default, `groupingBy(classifier)` does not guarantee the Map class or key iteration order. If you need **first-appearance order of groups** from an ordered sequential Stream, use the three-parameter overload with `LinkedHashMap::new`:

```java
Map<GroupKey, List<Order>> insertionOrderGroups = orders.stream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                LinkedHashMap::new,
                Collectors.toList()
        ));

insertionOrderGroups.keySet().forEach(System.out::println);
// GroupKey[region=Bắc, category=Sách]
// GroupKey[region=Bắc, category=Bút]
// GroupKey[region=Nam, category=Sách]
```

`Collectors.toList()` gathers elements within each group; with an ordered source Stream and a standard collector, each group's list preserves the corresponding encounter order. However, `Collectors.toList()` **does not guarantee** mutability or a concrete list implementation class.

If you need **sorted key order** instead of appearance order, provide a `TreeMap` with a comparator:

```java
Comparator<GroupKey> byKey = Comparator
        .comparing(GroupKey::region)
        .thenComparing(GroupKey::category);

Map<GroupKey, Long> sortedGroupCounts = orders.stream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                () -> new TreeMap<>(byKey),
                Collectors.counting()
        ));
```

In a sorted Map like `TreeMap`, the comparator determines whether two keys are considered the same key when comparison returns 0. Ensure the comparator is **consistent with the key's equality definition** so you do not accidentally merge or split groups differently from `equals`.

For example, a comparator that only compares `region` is **wrong** for the composite key `(region, category)`: two different categories in the same region would be treated as one key in `TreeMap`.

## 13. Parallel Streams and groupingByConcurrent

Writing:

```java
Map<GroupKey, Long> countsParallel = orders.parallelStream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                Collectors.counting()
        ));
```

`groupingBy` is not a **concurrent collector**. With a parallel Stream, the framework may create multiple partial result Maps and then **combine** their contents. The result can be contractually correct, but a large number of groups or large data volumes can make Map merging a significant cost.

If ordering does not matter and the problem fits, consider `groupingByConcurrent`:

```java
ConcurrentMap<GroupKey, Long> concurrentCounts =
        orders.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        o -> new GroupKey(o.region(), o.category()),
                        Collectors.counting()
                ));
```

`groupingByConcurrent` returns a `ConcurrentMap` and is a **concurrent, unordered** collector. It can support parallel accumulation in a way different from merging multiple Maps. However:

- Do not expect fixed key iteration order or element order within groups.
- The downstream collector and data characteristics determine actual effectiveness; using concurrent is not automatically faster.
- Do not use classifiers that modify the source, rely on shared counters, or create mutable keys.
- If you need group Lists with a stable order, prefer an approach that preserves encounter order and verify correctness before optimizing.

`ConcurrentMap` and `Collectors.counting` in the example only express the aggregated result; when an application has **another thread mutating the source itself** while the Stream traverses it, you must separately examine the source's thread-safety contract. `parallelStream()` does not turn an `ArrayList` into a structure safe for concurrent modification.

## 14. Complexity and Design Choices

Grouping by a composite key carries practical costs:

| Factor | Impact | How to evaluate |
| --- | --- | --- |
| Creating new keys | Typically allocates a key object for each classified element | Measure on large datasets; prefer keys with simple fields and clear semantics |
| Number of distinct groups | The Map must store an entry for each distinct combination | Combination count can grow rapidly as more key fields are added |
| Retaining all elements | Default `groupingBy` builds a `List<T>` per group | Use `counting`/`summingLong` if only metrics are needed |
| String normalization | `strip`, `toUpperCase` may allocate and process repeatedly | Normalize at the ingestion layer or before grouping when possible |
| Parallel Stream | Incurs work-splitting and Map-merging overhead | Benchmark with realistic data and configuration |
| Result ordering | Default Map usually makes no order guarantee; Sets may also be unordered | Choose `LinkedHashMap` or `TreeMap` when genuinely required |
| Precision and overflow | `long` sums can overflow; `double` has precision error | Choose appropriate numeric types, rounding rules, and overflow checks |

With `n` elements and `g` group combinations, classifying and inserting into a hash-based Map **typically** has expected cost close to `O(n)` when hashes distribute well; retaining all elements per group requires memory scaling with `n`, whereas only counting groups requires memory scaling with `g`. This is not a runtime guarantee in every scenario: hashing cost, comparisons, the data source, and parallel execution also contribute.

Stream pipelines are lazy until the terminal operation `collect` runs. Once `collect` finishes, the Stream cannot be consumed again. If you need two different reports from the same source, create two fresh Streams or consider a composite collector to gather both in one pass.

## 15. Complete Example: Order Report by Month and Region

Suppose each order contains an ID, region, reporting month, quantity, and completion status. We need to aggregate **order count and total quantity** by **(region, month)**. Use a composite key so each combination forms an independent group.

Standalone runnable Java 17+ example:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class CompositeGroupingDemo {
    record Order(
            String id,
            String region,
            int month,
            int quantity,
            boolean completed
    ) {}

    record GroupKey(String region, int month) {}
    record Summary(long orderCount, long totalQuantity) {}

    static String normalizeRegion(String region) {
        return region.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O01", " Bắc ", 1, 3, true),
                new Order("O02", "Nam", 1, 7, true),
                new Order("O03", "BẮC", 1, 2, true),
                new Order("O04", "Nam", 2, 5, true),
                new Order("O05", "Bắc", 1, 99, false),
                new Order("O06", "Bắc", 2, 4, true)
        );

        Map<GroupKey, Summary> report = orders.stream()
                .filter(Order::completed)
                .collect(Collectors.groupingBy(
                        order -> new GroupKey(
                                normalizeRegion(order.region()),
                                order.month()
                        ),
                        LinkedHashMap::new,
                        Collectors.collectingAndThen(
                                Collectors.summarizingLong(Order::quantity),
                                stats -> new Summary(
                                        stats.getCount(),
                                        stats.getSum()
                                )
                        )
                ));

        report.forEach((key, summary) ->
                System.out.printf(
                        "%s | month %d | orders=%d | quantity=%d%n",
                        key.region(),
                        key.month(),
                        summary.orderCount(),
                        summary.totalQuantity()
                )
        );

        // BẮC | month 1 | orders=2 | quantity=5
        // NAM | month 1 | orders=1 | quantity=7
        // NAM | month 2 | orders=1 | quantity=5
        // BẮC | month 2 | orders=1 | quantity=4

        System.out.println(report.get(new GroupKey("BẮC", 1)));
        // Summary[orderCount=2, totalQuantity=5]
    }
}
```

Analysis:

1. `filter(Order::completed)` excludes incomplete orders before grouping.
2. `normalizeRegion` ensures `" Bắc "` and `"BẮC"` produce the same key field `"BẮC"`.
3. `GroupKey` uses a `record`, so equality and hash code are computed from both region **and** month.
4. `groupingBy` classifies and routes elements with the same key into the same accumulator.
5. `summarizingLong` computes order count and total quantity; `collectingAndThen` finalizes the result into an immutable `Summary`.
6. `LinkedHashMap::new` preserves first-appearance order of keys in a sequential Stream.
7. `report.get(new GroupKey("BẮC", 1))` finds the right group even though the newly constructed key object is a different instance from the stored key.

The example assumes `region` is not `null` and `month` is valid from 1 to 12. If input does not guarantee those conditions, validate or define an explicit convention before creating GroupKey. For financial reports, choose data types and addition semantics suited to the currency unit, precision, and business rules.

## 16. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Groups merged unexpectedly | Classifier uses only one of the two fields | Create a `GroupKey` containing all group identity components |
| Same content ends up in separate groups | Key does not override `equals`/`hashCode` | Use a `record` or an immutable value class following the contract |
| String concatenation conflates combinations | Component strings contain the delimiter or conventions vary | Use a strongly typed composite key |
| Using an array as key breaks lookup | Arrays compare by reference, not contents | Use a record with immutable fields, not raw arrays |
| `map.get(key)` unexpectedly returns `null` after editing key | Mutable key field was modified | Never mutate values participating in `equals`/`hashCode` of a stored key |
| `NullPointerException` in `groupingBy` | Classifier returns a `null` key object or normalizes null | Normalize/validate beforehand and produce non-null keys |
| Groups split due to casing or whitespace | Data not normalized according to business rules | Build an explicit normalization function |
| Resulting Map prints in an unexpected order | `groupingBy` does not guarantee Map order | Use `LinkedHashMap` or `TreeMap` with an appropriate comparator |
| `TreeMap` merges two groups with different categories | Comparator only compares region, returning 0 for distinct keys | Compare all fields that define identity |
| Result holds many large Lists causing memory pressure | Default `groupingBy` retains all elements | Use downstream `counting`, `summingLong`, `summarizingLong` |
| `parallelStream` is slower than sequential | Map creation/merging overhead and high group count | Benchmark realistically and use concurrent collectors only when appropriate |

## 17. Practice Exercise and Reference Solution

Given time-tracking data:

```java
record Worklog(String team, int year, int hours, boolean approved) {}

List<Worklog> logs = List.of(
        new Worklog("Backend", 2025, 4, true),
        new Worklog("Backend", 2025, 6, true),
        new Worklog("Frontend", 2025, 5, true),
        new Worklog("Backend", 2026, 3, true),
        new Worklog("Backend", 2025, 10, false)
);
```

**Requirements:**

1. Create `record WorklogKey(String team, int year)` as the composite key.
2. Exclude unapproved worklogs and group by `(team, year)`.
3. For each group, calculate the number of approved worklogs and total hours.
4. Look up the total hours of the `("Backend", 2025)` group using a new key instance.
5. Replace the grouped structure with `Map<String, Map<Integer, ...>>` and compare the two representations.
6. If `team` can appear as `" backend "` or `"BACKEND"`, add a normalization policy so they belong to the same group when appropriate for the business domain.

**Reference Solution:**

```java
record WorklogKey(String team, int year) {}
record WorklogSummary(long count, long totalHours) {}

Map<WorklogKey, WorklogSummary> report = logs.stream()
        .filter(Worklog::approved)
        .collect(Collectors.groupingBy(
                log -> new WorklogKey(log.team(), log.year()),
                Collectors.collectingAndThen(
                        Collectors.summarizingLong(Worklog::hours),
                        stats -> new WorklogSummary(
                                stats.getCount(),
                                stats.getSum()
                        )
                )
        ));

System.out.println(report.get(
        new WorklogKey("Backend", 2025)
));
// WorklogSummary[count=2, totalHours=10]

Map<String, Map<Integer, Long>> nestedHours = logs.stream()
        .filter(Worklog::approved)
        .collect(Collectors.groupingBy(
                Worklog::team,
                Collectors.groupingBy(
                        Worklog::year,
                        Collectors.summingLong(Worklog::hours)
                )
        ));

System.out.println(nestedHours.get("Backend").get(2025)); // 10
```

For requirement 6, you can apply `log.team().strip().toUpperCase(Locale.ROOT)` directly in the classifier and must use **the same normalized value during lookup**. In larger applications, it is better to normalize/validate at the input boundary or in a key-builder function used consistently everywhere.

**Extended experiment:** If you switch the source to `parallelStream()`, immutable value records and contract-compliant downstream collectors still produce valid metrics. However, do not assert a fixed key iteration order. Compare Map contents key by key and measure performance instead of comparing the `toString` output of the entire Map.

## Takeaways

When grouping by multiple attributes, create a **composite key with value semantics** instead of concatenating strings or using mutable objects. `record GroupKey(a, b)` carries the identifying fields and provides `equals` and `hashCode` automatically, enabling `Collectors.groupingBy` to gather elements sharing the same key combination properly.

Use downstream collectors such as `counting`, `summingLong`, `mapping`, or `summarizingLong` when the report only needs metrics rather than the full lists. Normalize and check for `null` before grouping; choose `LinkedHashMap`/`TreeMap` when explicit ordering is required. With parallel Streams, keep classifiers stateless and non-interfering with the source, evaluate Map combination costs, and use `groupingByConcurrent` only when unordered semantics are acceptable.
