# Multi-Level Grouping with Nested Keys

In business reporting, a single level of grouping is often not enough to answer the question. For instance, aggregating revenue **by region** only tells you the totals for the North, Central, and South; a manager also wants to know **within each region, how much each product category contributes**. In that case, you need **multi-level grouping** (*multi-level grouping*).

In the **Java Stream API**, the familiar tool for this problem is `Collectors.groupingBy` combined with another **downstream collector**. When you nest `groupingBy` inside `groupingBy`, the result typically takes the form **`Map<K1, Map<K2, ...>>`**. Each map level corresponds to one dimension of data analysis.

This lesson belongs to the **Grouping and Partitioning** chapter of the **JAVA_STREAM_API** module. It focuses on how to build nested group maps, compute counts and totals within each group, apply `mapping`/`filtering`, design keys, access data safely, and control ordering, resources, and state when using parallel streams. It also lays the groundwork for exploring custom collectors, `Spliterator`, and Stream Gatherers.

## 1. From Single-Level to Multi-Level Grouping

Suppose each sales transaction has a **region**, **category**, **amount**, and **payment status**.

If you only group by region:

~~~java
Map<String, List<Sale>> byRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));
~~~

The result can be visualized as:

~~~text
"Bắc"   -> [transactions in the North]
"Trung" -> [transactions in the Central region]
"Nam"   -> [transactions in the South]
~~~

However, if you want to see both **region → category**, you pass a `groupingBy` collector as the **downstream** collector of the outer collector:

~~~java
Map<String, Map<String, List<Sale>>> byRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(Sale::category)
    ));
~~~

Resulting structure:

~~~text
"Bắc" ->
    "Sách" -> [Sách transactions in Bắc]
    "Bút"  -> [Bút transactions in Bắc]

"Nam" ->
    "Sách" -> [Sách transactions in Nam]
    "Bút"  -> [Bút transactions in Nam]
~~~

At the first level, `Sale::region` is the **outer classifier function**. Within each region group, `Sale::category` **further** classifies the elements of that group. The leaf level defaults to a `List<Sale>`.

**Key point:** nested collectors do not perform multiple full passes over the data like "for each region, filter the Stream from scratch". They describe a single collection process in which elements are routed to the appropriate containers according to the keys at each level.

## 2. Complete Example: Grouping Transactions by Region and Category

The following example runs on **JDK 17 or later** because it uses `record` and `List.of`. The `Stream` and `Collectors.groupingBy` APIs have been available since Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NestedGroupingDemo {
    record Sale(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S01", "Bắc",   "Sách", 100_000L, true),
            new Sale("S02", "Nam",   "Bút",   40_000L, true),
            new Sale("S03", "Bắc",   "Sách", 150_000L, false),
            new Sale("S04", "Bắc",   "Bút",   30_000L, true),
            new Sale("S05", "Nam",   "Sách", 200_000L, true),
            new Sale("S06", "Nam",   "Bút",   70_000L, false),
            new Sale("S07", "Trung", "Sách",  90_000L, true),
            new Sale("S08", "Trung", "Bút",   20_000L, false)
        );

        Map<String, Map<String, List<Sale>>> grouped =
            sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(Sale::category)
            ));

        List<Sale> northBooks = grouped.get("Bắc").get("Sách");

        System.out.println(northBooks.stream()
            .map(Sale::id)
            .collect(Collectors.toList()));
        // [S01, S03]

        System.out.println(grouped.get("Nam").get("Bút").size());
        // 2: S02 and S06
    }
}
~~~

This program produces a structure with two `Map` layers:

- **Outer Map:** `String` keys representing the region.
- **Inner Map:** `String` keys representing the category within that region.
- **Leaf value:** `List<Sale>` containing the transactions for that key pair.

The type `Map<String, Map<String, List<Sale>>>` can be verbose, but it describes the exact shape of the data. Read it from **outside in**: "a map of regions, where each region has a map of categories, and each category contains a list of transactions."

~~~mermaid
flowchart TD
    A["Stream<Sale>"] --> B["groupingBy(region)"]
    B --> C["Bắc"]
    B --> D["Nam"]
    B --> E["Trung"]
    C --> F["groupingBy(category)"]
    D --> G["groupingBy(category)"]
    E --> H["groupingBy(category)"]
    F --> I["Sách → [S01, S03]"]
    F --> J["Bút → [S04]"]
    G --> K["Bút → [S02, S06]"]
    G --> L["Sách → [S05]"]
    H --> M["Sách → [S07]"]
    H --> N["Bút → [S08]"]
~~~

The diagram only illustrates the keys present; it **does not represent the iteration order of `HashMap`**. If the output requires a deterministic key order, you must choose a `mapFactory` or sort when displaying.

## 3. Understanding the groupingBy Overload with a Downstream Collector

The two common overloads are:

~~~java
Collectors.groupingBy(classifier)

Collectors.groupingBy(classifier, downstream)
~~~

In terms of type signatures:

~~~java
<T, K> Collector<T, ?, Map<K, List<T>>>
groupingBy(Function<? super T, ? extends K> classifier)

<T, K, A, D> Collector<T, ?, Map<K, D>>
groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
~~~

These are **simplified signatures for learning**, not the full source code of `Collectors`.

`classifier` receives an input element `T` and returns the **group key** `K`. `downstream` specifies how to process **the elements within each group** to produce the final value `D`.

For two grouping levels:

~~~java
Collectors.groupingBy(
    Sale::region,                    // level 1: K1
    Collectors.groupingBy(           // level 2
        Sale::category               // K2; default downstream is toList()
    )
)
~~~

We deduce:

~~~text
T = Sale
K1 = String (region)
K2 = String (category)
D2 = List<Sale>
D1 = Map<String, List<Sale>>
Result = Map<String, Map<String, List<Sale>>>
~~~

**Rule of thumb:** when you replace the innermost downstream collector with `counting()` or `summingLong(...)`, only the **leaf value type** changes; the nested keys still follow the same grouping logic.

## 4. Two-Level Grouping with Per-Group Counting

If the goal is only to count, there is no need to store transaction lists at every leaf. Use `Collectors.counting()`:

~~~java
Map<String, Map<String, Long>> countByRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.counting()
        )
    ));
~~~

The `sales` variable and `Sale` type here come from the complete example in Section 2.

Results on the sample dataset:

| Region | Category | Transaction count |
|---|---|---:|
| Bắc | Sách | 2 |
| Bắc | Bút | 1 |
| Nam | Bút | 2 |
| Nam | Sách | 1 |
| Trung | Sách | 1 |
| Trung | Bút | 1 |

`counting()` returns a `Long` value, not `Integer`, because the element count can exceed the `int` range.

Access example:

~~~java
long northBookCount =
    countByRegionAndCategory.get("Bắc").get("Sách");

System.out.println(northBookCount); // 2
~~~

Here the keys are guaranteed to exist because we know the sample data. With arbitrary input data, `get("Bắc")` or `get("Sách")` can return `null`; Section 10 presents how to retrieve results safely.

### 4.1. Why does counting save more memory than toList?

`groupingBy(region, groupingBy(category))` retains **every `Sale` object** inside lists. `groupingBy(region, groupingBy(category, counting()))` stores only a count at each key pair.

With large datasets where only statistics are needed, the second approach has a memory footprint **closer to the number of groups** rather than the number of transactions. Do not store millions of records in Lists if the report only needs `count`.

## 5. Two-Level Grouping with Summing via summingLong

A more common business requirement is **total revenue by region and category**. Here we count only transactions with `paid = true`:

~~~java
Map<String, Map<String, Long>> revenueByRegionAndCategory =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
~~~

Revenue map from the sample dataset:

| Region | Category | Total paid amount |
|---|---|---:|
| Bắc | Sách | 100.000 |
| Bắc | Bút | 30.000 |
| Nam | Bút | 40.000 |
| Nam | Sách | 200.000 |
| Trung | Sách | 90.000 |

The pair **(Trung, Bút)** does not appear because transaction `S08` is unpaid and was removed by `filter` before grouping.

Components of the pipeline:

1. `filter(Sale::paid)` keeps paid transactions.
2. `groupingBy(Sale::region, ...)` selects the region.
3. `groupingBy(Sale::category, ...)` selects the category within that region.
4. `summingLong(Sale::amountVnd)` extracts a `long` from each transaction and accumulates the sum within each group.

`summingLong` is a **downstream collector**, not a `mapToLong(...).sum()` call after building the Map. It performs the aggregation **directly during group collection**.

**Overflow note:** `Long` can represent larger totals than `int`, but `long` is still finite. If total amounts can exceed `Long.MAX_VALUE`, the application must use an appropriate representation and addition operation (such as `BigDecimal` or checked business bounds).

### 5.1. Same data, different two-level aggregations

| Final downstream | Leaf type | When to use |
|---|---|---|
| Default `toList()` | `List<Sale>` | Inspect individual records |
| `counting()` | `Long` | Count transactions |
| `summingLong(Sale::amountVnd)` | `Long` | Sum amounts |
| `averagingLong(Sale::amountVnd)` | `Double` | Average value |
| `summarizingLong(Sale::amountVnd)` | `LongSummaryStatistics` | Count, sum, min, max, average |
| `maxBy(Comparator.comparingLong(...))` | `Optional<Sale>` | Find the transaction with the largest value |

**Type properties:** `Map<String, Map<String, Long>>` is a **structural result**. Which concrete `Map` is created, whether it is mutable, and how keys are ordered depend on the collector contract and map factory parameter; do not rely on a particular Map implementation when none was requested.

## 6. Three-Level Grouping: Adding Payment Status

You can nest another `groupingBy` if the report requires a third dimension:

~~~java
Map<String, Map<String, Map<Boolean, List<Sale>>>> tripleGroups =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.groupingBy(Sale::paid)
        )
    ));
~~~

Example:

~~~text
"Bắc" ->
  "Sách" ->
      true  -> [S01]
      false -> [S03]
  "Bút" ->
      true  -> [S04]

"Nam" ->
  "Bút" ->
      true  -> [S02]
      false -> [S06]
  "Sách" ->
      true  -> [S05]
~~~

Key distinction: `groupingBy(Sale::paid)` only creates a Boolean key **if there is at least one transaction with that value in the group**. Thus `tripleGroups.get("Bắc").get("Bút").get(false)` can be `null` instead of an empty list.

Do not write code assuming every branch has both Boolean values. For requirements that **always need both `true`/`false` branches**, a better-suited collector exists: `partitioningBy`.

### 6.1. partitioningBy for a two-state final level

~~~java
Map<String, Map<String, Map<Boolean, List<Sale>>>> partitioned =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.partitioningBy(Sale::paid)
        )
    ));

System.out.println(
    partitioned.get("Bắc").get("Bút").get(false).isEmpty()
); // true
~~~

For a group that **already exists** (here Bắc → Bút), `partitioningBy` creates a Map with both `true` and `false` keys, even if one side has no elements. However, region/category pairs that **never appeared in the source** are still not created by `groupingBy`.

| Mechanism at Boolean level | Guarantees both true and false keys for each existing group? | Use case |
|---|---|---|
| `groupingBy(Sale::paid)` | No | Only interested in statuses that have transactions |
| `partitioningBy(Sale::paid)` | Yes | Want two fixed branches, including empty ones |

`partitioningBy` also supports its own downstream collector, such as `partitioningBy(Sale::paid, counting())` to count both statuses within each group.

## 7. mapping: Transforming Elements Before Storing Them in Each Group

Sometimes you only need transaction IDs rather than full `Sale` objects. If you call `map(Sale::id)` **before** `groupingBy`, you lose the region and category fields needed for grouping unless you create another intermediate data type.

The proper approach is to keep `Sale` until group keys are determined, and then use **`Collectors.mapping` as the downstream collector**:

~~~java
Map<String, Map<String, List<String>>> idsByRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.mapping(
                Sale::id,
                Collectors.toList()
            )
        )
    ));
~~~

Result for Bắc → Sách:

~~~java
System.out.println(
    idsByRegionAndCategory.get("Bắc").get("Sách")
); // [S01, S03]
~~~

`mapping(mapper, downstream)` means: **within each group**, map the element to a new type and pass it to the downstream collector. The `mapping` method is a **collector**, unlike `Stream.map` which is an **intermediate operation**.

This is a common pattern in multidimensional reports: group by the source object, but emit only the needed fields at the end.

### 7.1. Choosing Set instead of List at the leaf

If transaction IDs may repeat and you need a set of unique IDs:

~~~java
Map<String, Map<String, Set<String>>> uniqueIds =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.mapping(
                Sale::id,
                Collectors.toSet()
            )
        )
    ));
~~~

This example requires `import java.util.Set;` in addition to the corresponding imports. `Collectors.toSet()` does not guarantee iteration order or a specific `Set` class. If you need a `TreeSet` in ascending order, use `Collectors.toCollection(TreeSet::new)` and ensure elements have a natural order or an appropriate comparator.

## 8. Downstream filtering vs. filter Before groupingBy

This is a very important **semantic** difference for reports with zero counts.

**Approach A — filter the entire Stream before grouping:**

~~~java
Map<String, Map<String, Long>> paidOnly =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.counting()
            )
        ));
~~~

Because transaction `S08` in **Trung → Bút** is unpaid and there are no other records in that key pair, the Map **has no Trung → Bút branch**.

**Approach B — keep all groups, filter only at the leaf with `Collectors.filtering` (Java 9+):**

~~~java
Map<String, Map<String, Long>> paidCountIncludingZero =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.filtering(
                Sale::paid,
                Collectors.counting()
            )
        )
    ));

System.out.println(
    paidCountIncludingZero.get("Trung").get("Bút")
); // 0
~~~

Because `groupingBy` has already established the **Trung → Bút** group before downstream filtering runs, the group is still created, and the count of qualifying transactions in that group is `0L`.

Similarly, you can use:

~~~java
Collectors.filtering(Sale::paid, Collectors.toList())
~~~

to keep an **empty list** in a group that has input data but no elements matching the predicate.

| Requirement | Recommended choice |
|---|---|
| Report shows only groups **with matching transactions** | `stream.filter(...).collect(groupingBy(...))` |
| Report must keep groups that appeared, even with a child result of 0 | `groupingBy(..., filtering(..., counting()))` |
| Report requires **every possible key combination**, even those that never appeared | Beyond grouping, **initialize/fill missing keys** from the business catalog |

`Collectors.filtering` does not automatically create region/category pairs that do not exist in the source data. It only preserves groups that the outer collector has already encountered.

## 9. Multiple Statistics at Each Leaf with summarizingLong

Sometimes you need `count`, `sum`, `min`, `max`, and `average` all at once. Instead of creating five separate Maps (equivalent to five collection passes), use `Collectors.summarizingLong`:

~~~java
import java.util.LongSummaryStatistics;

Map<String, Map<String, LongSummaryStatistics>> statistics =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summarizingLong(Sale::amountVnd)
            )
        ));

LongSummaryStatistics northBooks =
    statistics.get("Bắc").get("Sách");

System.out.println(northBooks.getCount());   // 1
System.out.println(northBooks.getSum());     // 100000
System.out.println(northBooks.getMin());     // 100000
System.out.println(northBooks.getMax());     // 100000
System.out.println(northBooks.getAverage()); // 100000.0
~~~

`LongSummaryStatistics` is a stateful statistics container. Values like count and sum are computed during collection without storing a `List<Sale>` for each group.

**Empty group case:** a fresh `LongSummaryStatistics` has count 0 and sum 0, but the min/max values of an object with no data hold sentinel values (`Long.MAX_VALUE`/`Long.MIN_VALUE`). Do not report those sentinels as actual amounts; check `getCount()` before interpreting min/max.

If transaction counts or values can be huge, watch out for `long` overflow in the sum. Also, average returns `double`, which has floating-point precision limits.

## 10. Accessing Nested Maps Safely

The sample dataset contains `Bắc → Sách`, so calling `grouped.get("Bắc").get("Sách")` directly works. With unknown inputs, however, a key might be absent and `Map.get` will return `null`.

Avoid writing:

~~~java
// Can throw NullPointerException if region "Tây" does not exist.
// long count = countByRegionAndCategory.get("Tây").get("Sách");
~~~

You can retrieve the value explicitly using a default Map:

~~~java
Map<String, Long> categories =
    countByRegionAndCategory.getOrDefault(
        "Tây",
        java.util.Collections.emptyMap()
    );

long count = categories.getOrDefault("Sách", 0L);

System.out.println(count); // 0
~~~

Distinguish between **absent** and **exact value 0**:

- If business rules state that an absent group should display `0`, using `getOrDefault` is reasonable.
- If you need to distinguish a group that never appeared from a group that appeared with zero matching transactions, use `containsKey` or `Optional`/an appropriate domain result type.

Example checking whether a key pair exists:

~~~java
Map<String, Long> categoriesOrNull =
    countByRegionAndCategory.get("Trung");

boolean hasPenGroup = categoriesOrNull != null
    && categoriesOrNull.containsKey("Bút");

System.out.println(hasPenGroup); // true on the original data
~~~

When multiple places query the nested Map, encapsulate the lookup into a small, clearly named helper method instead of repeating error-prone `get` chains.

## 11. Controlling Key Order with mapFactory

The `groupingBy(classifier, downstream)` overload **does not guarantee** the Map type or key iteration order. If a report must be displayed in a deterministic order, use the three-parameter overload:

~~~java
Collectors.groupingBy(classifier, mapFactory, downstream)
~~~

The `mapFactory` parameter is a `Supplier<M>` that creates the Map for **that grouping level**.

### 11.1. Sorting both levels with TreeMap

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, List<String>>> sortedGroups =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.groupingBy(
            Sale::category,
            TreeMap::new,
            Collectors.mapping(Sale::id, Collectors.toList())
        )
    ));
~~~

- The first `TreeMap::new` applies to **region** keys.
- The second `TreeMap::new` applies to **category** keys within each region.
- `mapping(Sale::id, toList())` builds the list of IDs at the leaf.

For `String` keys, a `TreeMap` without a comparator sorts by **`String.compareTo`**. This is not automatically Vietnamese alphabetical order for end users. If a business display order is needed, provide an appropriate comparator or define a custom ordering map.

### 11.2. Preserving key appearance order with LinkedHashMap

If the source is a sequential `List` and you want keys displayed in first-appearance order:

~~~java
import java.util.LinkedHashMap;

Map<String, Map<String, List<Sale>>> insertionOrdered =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::category,
            LinkedHashMap::new,
            Collectors.toList()
        )
    ));
~~~

In **sequential processing from a List with encounter order**, `LinkedHashMap` iterates keys in insertion order. With parallel Streams, combining containers introduces complexity; do not rely on thread completion order or assume every collector preserves first-encounter order when ordering characteristics are not guaranteed.

**Note:** `TreeMap` only changes key ordering, not the source names or values. If keys can be `null`, normalize them beforehand; Section 12 explains why.

## 12. Key Design and Null Handling

### 12.1. groupingBy requires the classifier to return a valid key

In standard Java `Collectors.groupingBy` implementations, a classifier returning `null` causes a `NullPointerException` (typically with a message that an element cannot be mapped to a null key). Do not assume the default Map will accept a null key.

Dangerous example:

~~~java
record Sale(String id, String region, String category, long amountVnd) {}

List<Sale> raw = List.of(
    new Sale("S01", null, "Sách", 100L)
);

// Fails because the region group key is null.
// raw.stream().collect(Collectors.groupingBy(Sale::region));
~~~

The `Sale` record above is a **standalone** type to illustrate null behavior; do not declare it with the same name in the same scope as the `Sale` record from Section 2.

Two common ways to handle this:

**Approach A: drop records missing a key before grouping.**

~~~java
Map<String, List<Sale>> validRegions = raw.stream()
    .filter(s -> s.region() != null)
    .collect(Collectors.groupingBy(Sale::region));
~~~

**Approach B: use a valid placeholder key per business policy.**

~~~java
Map<String, List<Sale>> withUnknown = raw.stream()
    .collect(Collectors.groupingBy(
        s -> s.region() == null ? "Chưa xác định" : s.region()
    ));
~~~

If you choose a sentinel string like `"Chưa xác định"`, make sure it **does not collide** with a real region value, or intentionally accept merging them.

With multiple levels, you must handle `null` at **every classifier level**, not just the outer key.

### 12.2. Normalizing keys before grouping

Data coming from multiple sources may contain `"Bắc"`, `" Bắc "`, and different letter casings. `groupingBy` does not treat them as the same key automatically.

A clean pipeline:

~~~java
record RegionItem(String region, String category, long amount) {}

List<RegionItem> input = List.of(
    new RegionItem(" Bắc ", "Sách", 100L),
    new RegionItem("Bắc",   "Sách", 200L)
);

Map<String, Map<String, Long>> totals = input.stream()
    .collect(Collectors.groupingBy(
        item -> item.region().trim(),
        Collectors.groupingBy(
            item -> item.category().trim(),
            Collectors.summingLong(RegionItem::amount)
        )
    ));

System.out.println(totals.get("Bắc").get("Sách")); // 300
~~~

This approach normalizes directly inside the classifier. For complex rules or when normalized keys are used in multiple places, you can create a normalized intermediate object via `map` before grouping, as long as no attributes needed for grouping are lost.

When processing proper names, Vietnamese labels, or Unicode text, do not call `toLowerCase` or compare strings under an arbitrary locale without defining the data domain rules.

### 12.3. equals and hashCode of keys

`String` keys already implement `equals` and `hashCode` consistently. For custom object keys, define equality to match the intended grouping semantics.

A key with mutable fields that are modified after being inserted into a `HashMap` can cause group lookups to fail. Prefer immutable keys; with Java 16+, `record` is very convenient for composite keys, as shown in the next section.

## 13. Nested Map or Composite Key?

There are two different models for the same grouping dimensions.

**Model A: nested Map** — result shaped as `Map<Region, Map<Category, Value>>`.

~~~java
Map<String, Map<String, Long>> nested =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.summingLong(Sale::amountVnd)
        )
    ));
~~~

**Model B: composite key** — combine multiple dimensions into a record key:

~~~java
record GroupKey(String region, String category) {}

Map<GroupKey, Long> flat =
    sales.stream().collect(Collectors.groupingBy(
        sale -> new GroupKey(sale.region(), sale.category()),
        Collectors.summingLong(Sale::amountVnd)
    ));
~~~

In the two examples above, `Sale` is the type from Section 2 and totals are computed across **all transactions**, not only paid ones. Both representations can hold the same information, but access differs:

~~~java
long byNested = nested.get("Bắc").get("Sách");
long byFlat = flat.get(new GroupKey("Bắc", "Sách"));

System.out.println(byNested); // 250000 (S01 + S03)
System.out.println(byFlat);   // 250000
~~~

### When to choose which?

| Criterion | Nested Map | Composite key |
|---|---|---|
| Traversing the report level by level | Convenient: iterate regions, then categories | Must regroup or filter by key fields to traverse level by level |
| Direct lookup of a single combination | Multiple `get` calls | One `get(new GroupKey(...))` call |
| Type verbosity | `Map<K1, Map<K2, V>>`, can grow long with deep nesting | `Map<GroupKey, V>`, usually shorter type |
| Expressing hierarchical reports | Natural | Requires transformation when exporting as a tree |
| Key structure | One key per level | One immutable key holding multiple dimensions |
| Empty combinations | Only groups present in source | Only keys present in source |

`record GroupKey` automatically generates `equals` and `hashCode` from its components. This is a convenient way to represent multiple dimensions without rewriting equality methods.

**Neither is always better.** If the UI needs to display "each region → its categories", a nested Map is very natural. If an algorithm repeatedly looks up key pairs, a composite key can be more convenient.

## 14. Too Many Nesting Levels: A Sign to Redesign

Three, four, or five levels of `groupingBy` can all be expressed in Java, but type and code verbosity grows rapidly:

~~~java
Map<String, Map<String, Map<Boolean, Long>>> counts =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.groupingBy(
                Sale::paid,
                Collectors.counting()
            )
        )
    ));
~~~

This snippet counts by **region → category → payment status**. Syntactically it is valid; design-wise, consider:

- Does the UI truly need a three-level hierarchical structure, or just a list of summary rows?
- Do absent groups need to be created with a value of 0?
- Do keys need to be sorted at each level?
- Should `partitioningBy` be used for the Boolean status?
- Should a composite key or a report object with clearly named fields be used?

When using deeply nested `Map` structures, callers easily write long chains of `get` calls and hit `NullPointerException` when a branch does not exist. In larger projects, encapsulate grouped data in a dedicated report type instead of letting complex Map structures spread throughout the application.

## 15. Performance, Resources, and Parallel Streams

### 15.1. Cost depends on the leaf value type

Suppose there are `n` transactions and `g` distinct group combinations:

- If the leaf is `List<Sale>`, the result holds references to nearly `n` elements, plus Map/List overhead.
- If the leaf is `Long` from `counting` or `summingLong`, result size mainly depends on the `g` groups.
- If the classifier allocates new key strings, performs complex normalization, or has an expensive `hashCode`, total runtime can increase.
- With hash-based Maps, average-case classification cost is usually favorable, but constant-time complexity should not be assumed as guaranteed in every case.

The more dimensions you add, the larger the number of group combinations **can** grow. If every transaction creates its own combination, grouping barely reduces data volume, even though the code uses a collector.

### 15.2. Parallel execution must still satisfy the contract

You can write:

~~~java
Map<String, Map<String, Long>> parallelTotals =
    sales.parallelStream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
~~~

`Collectors.groupingBy` is a regular non-concurrent collector; in parallel execution, the framework may create multiple intermediate Maps and then combine them. You **do not need to** and **should not** share a mutable `HashMap` from an outer variable and call `parallelStream().forEach(...)` to accumulate manually.

However, `parallel()` does not automatically guarantee faster execution. Splitting data, creating containers, and merging nested Maps can add significant overhead, especially when there are many groups or small datasets.

### 15.3. groupingByConcurrent is not an always-equivalent replacement

Java also provides `Collectors.groupingByConcurrent` to collect into a `ConcurrentMap` and support a concurrent accumulation strategy. However, this collector has the **UNORDERED** characteristic and organizes concurrency differently from regular grouping.

If a report needs to preserve element encounter order or specific key ordering, do not automatically replace `groupingBy` with `groupingByConcurrent`. With a downstream collector that is not itself concurrent, the implementation still has to coordinate accumulation safely; do not assume every leaf container like `ArrayList` can be arbitrarily updated by multiple threads.

When choosing between the two, determine your requirements for **ordering, result type, concurrency, and group count**, and then benchmark performance.

### 15.4. Grouping very large datasets may not fit in JVM memory

`collect` is a terminal operation: to produce grouped results, Map containers are built in memory. For very large datasets, streaming the input does not mean **small result memory**.

If you only need a summary report with very few groups, `counting`/`summingLong` may fit well. If you need to store every transaction in each group, consider heap limits, paginated loading, or pushing aggregation down to a database or data-processing engine suited to your system.

With **unbounded infinite Stream sources**, `collect(groupingBy(...))` generally cannot finish. You must design limits, processing windows, or stopping conditions; stateful real-time streaming models require their own architecture.

## 16. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong or risky | Fix |
|---|---|---|
| Using `groupingBy(region)` and assuming it already groups by category | Performs only **single-level** grouping | Pass `groupingBy(category)` as the downstream collector |
| Calling `map(Sale::id)` before grouping by region/category | Loses classifier data | Use downstream `mapping` after the grouping levels |
| Calling `map.get(region).get(category)` when keys may be absent | `Map.get` can return `null` | Use `getOrDefault`/`containsKey`, or a helper |
| Assuming every region/category pair is present | `groupingBy` only creates encountered groups | Initialize missing groups from the business catalog |
| Using `filter` before grouping when expecting count 0 groups | Groups with no qualifying elements disappear | Use downstream `Collectors.filtering` (Java 9+) |
| Using `groupingBy(boolean)` and assuming both true/false exist | A branch with no elements is absent | Use `partitioningBy` at the Boolean level |
| Classifier returns null | Usually throws `NullPointerException` | Filter/normalize or map to a sentinel |
| Believing `groupingBy` always returns `LinkedHashMap` | No guarantee on the default Map | Specify a `mapFactory` |
| Using `counting()` while declaring value type `Integer` | `counting` produces `Long` | Use `Map<..., Long>` |
| Using `toList()` when only sums/counts are needed | Retains unnecessary element references | Use `summingLong`/`counting` |
| Summing amounts in a shared Map via `parallelStream().forEach` | Race conditions and external state mutation | Use a contract-compliant collector |
| Using a collector on an unbounded infinite source | Cannot complete | Bound the stream or design processing windows |
| Forgetting overflow in `long` sums | Report totals can become incorrect | Choose appropriate numeric types/bounds and arithmetic policy |

## 17. Practice Exercise: Multi-Level Order Report

**Context:** a store has sales transactions, each with an ID, region, category, amount, and payment status. You need a report of **paid revenue by region → category**, and **paid transaction count for each region → category pair, including groups that only have unpaid transactions**.

**Requirements:**

1. Create `Map<String, Map<String, Long>>` for paid revenue.
2. Create another two-level Map for **paid transaction counts**, while keeping groups that appeared in the source with count 0.
3. Safely access the key pair `("Miền Tây", "Sách")` which does not exist in the data.
4. Explain the difference in key sets between the two reports.

### Reference Solution (Java 17+)

~~~java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class MultiLevelGroupingPractice {
    record Sale(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("A1", "Bắc", "Sách", 100L, true),
            new Sale("A2", "Bắc", "Sách", 200L, false),
            new Sale("A3", "Nam", "Bút",   50L, true),
            new Sale("A4", "Nam", "Sách",  70L, false)
        );

        // Report 1: exclude unpaid transactions before grouping.
        Map<String, Map<String, Long>> paidRevenue =
            sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                    Sale::region,
                    Collectors.groupingBy(
                        Sale::category,
                        Collectors.summingLong(Sale::amountVnd)
                    )
                ));

        // Report 2: form groups first, then filter inside each group.
        Map<String, Map<String, Long>> paidCountWithZero =
            sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(
                    Sale::category,
                    Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                    )
                )
            ));

        Map<String, Long> missingRegion =
            paidRevenue.getOrDefault(
                "Miền Tây",
                Collections.emptyMap()
            );
        long missingValue =
            missingRegion.getOrDefault("Sách", 0L);

        System.out.println(paidRevenue.get("Bắc").get("Sách")); // 100
        System.out.println(paidRevenue.get("Nam").get("Bút"));  // 50

        System.out.println(paidCountWithZero.get("Bắc").get("Sách")); // 1
        System.out.println(paidCountWithZero.get("Nam").get("Sách")); // 0

        System.out.println(missingValue); // 0 per display policy
        System.out.println(
            paidRevenue.get("Nam").containsKey("Sách")
        ); // false
    }
}
~~~

**Explanation:** the **Nam → Sách** group only has unpaid transaction `A4`. Therefore, the revenue report using `filter` before grouping **does not create** the `Sách` key under `Nam`; the count report using downstream `filtering` **still keeps** that key, with value `0L`. The pair `Miền Tây → Sách` does not exist in the source at all, so neither collector creates a group for it; `getOrDefault` only controls how it is **presented** on lookup.

### Self-Check Questions

1. What leaf type does `groupingBy(region, groupingBy(category))` return? — **`List<Sale>`**.
2. If you replace the final downstream with `counting()`, what is the leaf value type? — **`Long`**.
3. If you want to keep only transaction IDs at the leaf, which collector should you use? — **`mapping(Sale::id, toList())`**.
4. How do `filter` at the start of a pipeline and downstream `Collectors.filtering` differ? — **A group with no matching elements may be dropped completely or retained with an empty/0 value**.
5. Does `groupingBy(Sale::paid)` always create both `true` and `false` keys? — **No**; `partitioningBy` fits two fixed branches.
6. Does `groupingBy` guarantee key order in the resulting Map? — **No**, unless a map factory is configured.
7. Does a composite key using a record necessarily create a nested Map? — **No**, it creates `Map<GroupKey, V>`.
8. Can you assume a `null` key is accepted in `groupingBy`? — **No**; you must normalize or remove records with missing keys.
9. Is using `parallelStream()` with multi-level grouping faster by default? — **No**, you must measure and consider the cost of merging intermediate Maps.

## 18. Takeaways Before Building Multidimensional Reports

**Multi-level grouping** in the Java Stream API has the form **`groupingBy(khóaNgoài, groupingBy(khóaTrong, downstream))`**. Each `groupingBy` adds an analysis dimension, and the final downstream collector determines the leaf data: detailed list, count, sum, statistics, or group representative.

When building a pipeline, explicitly define the **hierarchy of grouping keys**, **leaf value type**, **empty-group policy**, **missing/null keys**, **display ordering**, and **source termination conditions**. For large datasets or parallel execution, prefer contract-compliant collectors and measure memory/coordination costs; do not manually update a shared `Map` using stateful callbacks.

A nested map expresses hierarchical reports well; when you need direct lookup of key combinations or want to reduce type depth, consider a **composite key**. Mastering these options helps you implement `groupingBy`, `partitioningBy`, custom collectors, and complex data-analysis tasks cleanly, testably, and safely.
