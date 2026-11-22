# Distinguishing groupingBy, partitioningBy, and toMap

> **Chapter:** Grouping and Partitioning  
> **Module:** JAVA_STREAM_API  
> **Goal:** Choose correctly among `Collectors.groupingBy`, `Collectors.partitioningBy`, and `Collectors.toMap` based on the output data structure, number of values per key, duplicate-key handling requirements, and aggregation strategy.

When writing a **Java Stream API** pipeline, operations like `filter`, `map`, and `sorted` describe how data flows through the stream, while `collect` is commonly used to gather results into a structure such as `List`, `Set`, or `Map`. Among the collectors that return a Map, the three most frequently confused APIs are **`groupingBy`**, **`partitioningBy`**, and **`toMap`**.

All three can produce a `Map`, yet their **meanings are completely different**:

- `groupingBy` splits elements by a **classification key**, defaulting to holding a **list of multiple elements** per key.
- `partitioningBy` splits elements by a **boolean condition**, always containing **two keys: `true` and `false`**.
- `toMap` maps each element into **one key–value pair**; when keys collide, you must decide whether to **reject, pick one value, or merge the values**.

This lesson walks from reading the API signatures to business examples, downstream collectors, empty data, ordering, `null`, parallel execution, and performance. It also builds the foundation for learning multi-level grouping, custom collectors, `Spliterator`, and Stream Gatherers in the **JAVA_STREAM_API** module.

Examples use Java 17+ to support `record`, `List.of`, and `Stream.toList()`. All three main collectors have been available since Java 8; `Collectors.filtering` was added in Java 9.

## 1. Quick Overview: Same Map Return Type, Different Contracts

Suppose we have a set of sales transactions with ID, region, amount, and payment status. We have three requirements:

1. **By region:** which transactions belong to region "Bắc"?
2. **By status:** which transactions are paid and which are unpaid?
3. **By transaction ID:** how do we quickly look up the transaction with ID "S03"?

These three requirements lead to three collection approaches:

```java
// Map<String, List<Sale>>: one region can contain multiple transactions.
Map<String, List<Sale>> byRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));

// Map<Boolean, List<Sale>>: only true and false groups exist.
Map<Boolean, List<Sale>> byPaid = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

// Map<String, Sale>: one transaction ID maps to one Sale.
Map<String, Sale> byId = sales.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));
```

The variables and `Sale` type are fully declared in the example in Section 2. Imports needed are `java.util.List`, `java.util.Map`, `java.util.function.Function`, and `java.util.stream.Collectors`.

| Criterion | `groupingBy` | `partitioningBy` | `toMap` |
| --- | --- | --- | --- |
| Primary question | "Which group does the element belong to?" | "Is the condition true or false?" | "Which key and value does the element produce?" |
| Input function | `Function<T,K>` | `Predicate<T>` | `keyMapper` and `valueMapper` |
| Typical key type | Any non-`null` `K` | `Boolean` | Any `K` supported by the created Map |
| Default result type | `Map<K,List<T>>` | `Map<Boolean,List<T>>` | `Map<K,U>` |
| Multiple elements with the same key | Gathered into one group | Gathered into one of the two branches | Fails in the overload without a merge function |
| Has downstream collector? | Yes | Yes | Not via downstream syntax; has a merge function |
| Empty source | Empty Map | Still has `true` and `false` | Empty Map |
| Number of keys | 0 up to the number of generated keys | Always exactly 2 boolean keys | 0 up to the number of mapped keys |

**Quick identification rule:** if you want to keep a **collection of elements per key**, use `groupingBy`; if there are only **two branches from a condition**, use `partitioningBy`; if you need **one value per key**, consider `toMap` and define the duplicate-key policy.

## 2. Consistent Sample Data for the Entire Lesson

We use the `Sale` record:

```java
record Sale(String id, String region, long amount, boolean paid) {}
```

Input list:

```java
List<Sale> sales = List.of(
    new Sale("S01", "Bắc", 120_000L, true),
    new Sale("S02", "Nam",  60_000L, false),
    new Sale("S03", "Bắc",  80_000L, true),
    new Sale("S04", "Nam", 140_000L, true),
    new Sale("S05", "Bắc",  50_000L, false),
    new Sale("S06", "Tây", 200_000L, true)
);
```

Data table:

| ID | Region | Amount | Paid |
| --- | --- | ---: | --- |
| S01 | Bắc | 120.000 | true |
| S02 | Nam | 60.000 | false |
| S03 | Bắc | 80.000 | true |
| S04 | Nam | 140.000 | true |
| S05 | Bắc | 50.000 | false |
| S06 | Tây | 200.000 | true |

From this table, the expected results are:

- By region: **Bắc has 3**, **Nam has 2**, **Tây has 1** transaction.
- By payment status: **true has 4**, **false has 2** transactions.
- Gross revenue by region **without filtering status**: Bắc **250.000**, Nam **200.000**, Tây **200.000**.
- Revenue **for paid transactions only** by region: Bắc **200.000**, Nam **140.000**, Tây **200.000**.

Distinguishing "total amount of all transactions" from "paid revenue" is part of the business requirement, not an automatic decision made by the collector.

## 3. groupingBy: Grouping Multiple Elements by a Key

Simplest overload:

```java
Map<String, List<Sale>> salesByRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));
```

`Sale::region` is the *classifier* — a function taking a `Sale` and returning a `String` key. For each key, the collector builds a group of elements sharing the same classification value:

```text
Stream<Sale>
      │
      ▼
groupingBy(Sale::region)
      │
      ├── "Bắc" ──► [S01, S03, S05]
      ├── "Nam" ──► [S02, S04]
      └── "Tây" ──► [S06]
```

Accessing a group:

```java
List<Sale> northern = salesByRegion.get("Bắc");

System.out.println(northern.size()); // 3
```

### 3.1. groupingBy does not limit the number of groups

The classifier function can return strings, numbers, enums, records, or other domain keys, as long as they satisfy the collector and Map requirements. The number of groups depends on **the keys that actually appear in the source**, not the number of theoretically possible values of the key type.

Example grouping by year:

```java
record Invoice(String id, int year, long amount) {}

List<Invoice> invoices = List.of(
    new Invoice("I01", 2025, 100),
    new Invoice("I02", 2026, 200),
    new Invoice("I03", 2025, 300)
);

Map<Integer, List<Invoice>> byYear = invoices.stream()
    .collect(Collectors.groupingBy(Invoice::year));

// byYear has 2 keys: 2025 and 2026.
```

If there are no invoices for year 2024, the Map does not automatically create a 2024 group with an empty list.

### 3.2. groupingBy does not have to return a list

By default, `groupingBy(classifier)` can be understood as collecting with downstream `toList()`. However, the overload taking a **downstream collector** lets each group's result be a count, total amount, set of IDs, or custom summary:

```java
Map<String, Long> counts = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));

// Bắc -> 3; Nam -> 2; Tây -> 1.
```

`Collectors.counting()` processes elements in each group and produces a `Long`. Thus the result becomes `Map<String, Long>`, not `Map<String, List<Sale>>`.

### 3.3. groupingBy and null classification keys

`Collectors.groupingBy` does not accept `null` as a classifier result. If `region` is `null`, the call:

```java
// Can cause NullPointerException when a Sale has region == null.
// sales.stream().collect(Collectors.groupingBy(Sale::region));
```

will fail. Do not assume that because `HashMap` can hold a `null` key, `groupingBy` also accepts it automatically.

Determine the business meaning of records missing a region. If you want an "Unknown" ("Chưa xác định") group:

```java
Map<String, List<Sale>> safeGroups = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.region() == null
            ? "Chưa xác định"
            : sale.region()
    ));
```

If the string "Chưa xác định" could also be a valid real value, use a key type that cleanly separates the two cases, such as a dedicated record or `Optional<String>`:

```java
Map<Optional<String>, List<Sale>> byOptionalRegion = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> Optional.ofNullable(sale.region())
    ));
```

This example requires importing `java.util.Optional`. The key `Optional.empty()` represents a missing region, while `Optional.of("Bắc")` represents a present region.

## 4. partitioningBy: One Condition, Two Boolean Groups

`Collectors.partitioningBy` does not take an arbitrary classifier; it takes a **`Predicate<T>`**, i.e., a condition returning `boolean`:

```java
Map<Boolean, List<Sale>> paidPartition = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));
```

Result:

```text
Stream<Sale>
     │
     ▼
partitioningBy(Sale::paid)
     │
     ├── true  ──► [S01, S03, S04, S06]
     └── false ──► [S02, S05]
```

Retrieving both branches:

```java
List<Sale> paid = paidPartition.get(true);
List<Sale> unpaid = paidPartition.get(false);

System.out.println(paid.size());   // 4
System.out.println(unpaid.size()); // 2
```

### 4.1. partitioningBy always has two keys, even when one group is empty

This is the most important difference from `groupingBy`:

```java
Map<Boolean, List<Integer>> emptyPartition =
    Stream.<Integer>empty()
        .collect(Collectors.partitioningBy(n -> n > 0));

System.out.println(emptyPartition.containsKey(true));  // true
System.out.println(emptyPartition.containsKey(false)); // true
System.out.println(emptyPartition.get(true));           // []
System.out.println(emptyPartition.get(false));          // []
```

`partitioningBy` guarantees one result for `true` and one result for `false`. With a downstream collector, **both branches still receive a downstream result**, even when there are no elements in that branch.

Compare with `groupingBy` on an empty source:

```java
Map<String, List<String>> emptyGroup =
    Stream.<String>empty()
        .collect(Collectors.groupingBy(Function.identity()));

System.out.println(emptyGroup.isEmpty()); // true
```

`groupingBy` does not fabricate keys for groups that never appeared; `partitioningBy` pre-creates both boolean branches.

### 4.2. When to use partitioningBy instead of groupingBy?

You could write:

```java
Map<Boolean, List<Sale>> groupedBoolean = sales.stream()
    .collect(Collectors.groupingBy(Sale::paid));
```

On the current `sales` dataset which has both `true` and `false`, the grouped element lists look the same. However, if all transactions happened to be paid, `groupingBy(Sale::paid)` would contain only the `true` key, whereas `partitioningBy(Sale::paid)` still includes the `false` key with an empty list.

Therefore, **when the result domain must always include both states**, use `partitioningBy` to express that contract directly in the API.

### 4.3. The two branches do not have to represent business right/wrong

The predicate can test any condition:

```java
Map<Boolean, List<Sale>> largeOrders = sales.stream()
    .collect(Collectors.partitioningBy(
        sale -> sale.amount() >= 100_000
    ));
```

`true` means "orders meeting the threshold"; `false` means "orders below the threshold". When passing the Map to other components, choose descriptive variable names or convert to a result type with named fields so readers do not have to guess what the boolean keys mean.

## 5. toMap: Mapping One Key to One Value

`Collectors.toMap` takes **two essential functions**:

```java
Collectors.toMap(
    keyMapper,
    valueMapper
);
```

In the sales example, each transaction has a unique `id`:

```java
Map<String, Sale> byId = sales.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));

Sale found = byId.get("S03");
System.out.println(found.amount()); // 80000
```

With `toMap`, each key maps to **a single value**. That value can be the full object, a numeric attribute, a string, or a summary record.

### 5.1. What happens on duplicate keys?

If we replace `Sale::id` with `Sale::region`, multiple transactions share the "Bắc" key:

```java
// Throws IllegalStateException because region is not unique:
// Map<String, Sale> byRegion = sales.stream()
//     .collect(Collectors.toMap(
//         Sale::region,
//         Function.identity()
//     ));
```

The two-parameter overload of `toMap` **does not default to keeping the first, keeping the last, or collecting into a list**. It fails when two elements produce the same key.

This is the right behavior when keys are expected to be unique, because duplicate keys may indicate a data error that should be caught rather than silently overwritten.

### 5.2. Allowing duplicate keys with mergeFunction

The three-parameter overload adds **`BinaryOperator<U> mergeFunction`**:

```java
Map<String, Long> amountByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Sale::amount,
        Long::sum
    ));

// Bắc -> 250000, Nam -> 200000, Tây -> 200000.
```

At each key collision, `Long::sum` merges the amounts. The result is **one `Long` per region**, not a list of `Sale` objects.

Two other policies:

```java
// Keep the first encountered element when encounter order is guaranteed.
Map<String, Sale> firstByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Function.identity(),
        (first, next) -> first
    ));

// Keep the last encountered element when encounter order is guaranteed.
Map<String, Sale> lastByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Function.identity(),
        (first, next) -> next
    ));
```

Because `sales` is an ordered `List`, region Bắc keeps `S01` under the first-wins policy and `S05` under the last-wins policy. However, **encountered later does not automatically mean newest in business time**; if you need to select by timestamp, compare timestamps explicitly.

### 5.3. When to use toMap instead of groupingBy?

The key question is **how much information each key needs to retain**:

| Requirement | Recommended direction |
| --- | --- |
| Keep all transactions of a region | `groupingBy(Sale::region)` |
| Compute total amount of a region | `groupingBy(Sale::region, summingLong(...))` **or** `toMap(..., Long::sum)` |
| Look up transaction by unique ID | `toMap(Sale::id, identity())` |
| Keep one representative per region by an explicit rule | `toMap(..., mergeFunction)` |
| Need multiple structured statistics per region | `groupingBy` with a downstream collector is usually easier to extend |

Do not write `groupingBy` only to call `list.get(0)` afterward when the real requirement is picking one representative by a clear rule; conversely, do not use `toMap` and discard history if business rules require all elements.

## 6. API Signatures and How to Read Return Types

Written in general form, omitting wildcards to focus on meaning:

```java
// One key -> list of elements:
groupingBy(Function<T, K> classifier)
    // Collector<T, ?, Map<K, List<T>>>

// One key -> result from downstream:
groupingBy(Function<T, K> classifier,
           Collector<T, A, D> downstream)
    // Collector<T, ?, Map<K, D>>

// Two boolean branches -> lists:
partitioningBy(Predicate<T> predicate)
    // Collector<T, ?, Map<Boolean, List<T>>>

// Two boolean branches -> result from downstream:
partitioningBy(Predicate<T> predicate,
               Collector<T, A, D> downstream)
    // Collector<T, ?, Map<Boolean, D>>

// One key -> one value U; duplicate keys are rejected:
toMap(Function<T, K> keyMapper,
      Function<T, U> valueMapper)
    // Collector<T, ?, Map<K, U>>

// With a merge rule for U on duplicate keys:
toMap(Function<T, K> keyMapper,
      Function<T, U> valueMapper,
      BinaryOperator<U> mergeFunction)
    // Collector<T, ?, Map<K, U>>
```

The lines above are **signature diagrams**, not standalone compilable Java code. In real Java, generics include wildcards such as `? super T` and `? extends K` to support compatible types.

Note the differences:

- The **classifier** of `groupingBy` generates the group key; each element then flows into the downstream collector.
- The **predicate** of `partitioningBy` decides between the single `true` or `false` branch.
- The **key mapper + value mapper** of `toMap` produce `K,V` pairs directly; on key collisions, `mergeFunction` determines the combined `V` value.

`collect` itself is the Stream's terminal operation; the three collectors differ only in **how accumulation is structured**.

## 7. Downstream Collectors: The Strength of groupingBy and partitioningBy

Downstream collectors allow you to immediately compute a per-group result after grouping or partitioning rather than having to retain entire lists.

### 7.1. Counting elements by region

```java
Map<String, Long> countByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Result: Bắc = 3, Nam = 2, Tây = 1.

### 7.2. Total amount by region

```java
Map<String, Long> totalByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amount)
    ));

// Bắc=250000, Nam=200000, Tây=200000.
```

This produces the same values as `toMap(Sale::region, Sale::amount, Long::sum)` on the current dataset.

When multidimensional statistics are needed, `groupingBy` is usually easier to extend with other downstream collectors such as `summarizingLong`, `mapping`, `maxBy`, `filtering`, `collectingAndThen`, or a custom collector.

### 7.3. Counting transactions across both branches

```java
Map<Boolean, Long> countByPayment = sales.stream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));

System.out.println(countByPayment.get(true));  // 4
System.out.println(countByPayment.get(false)); // 2
```

On an empty source, the result still has `true -> 0L` and `false -> 0L`. The 0 value comes from the behavior of downstream `counting()` on an empty branch.

### 7.4. Collecting a list of IDs instead of objects

`Collectors.mapping` transforms each element before the downstream collects it:

```java
Map<String, List<String>> idsByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.mapping(
            Sale::id,
            Collectors.toList()
        )
    ));

// "Bắc" -> ["S01", "S03", "S05"]
```

With partitioning:

```java
Map<Boolean, List<String>> idsByPaid = sales.stream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.mapping(
            Sale::id,
            Collectors.toList()
        )
    ));

// true -> [S01, S03, S04, S06]
// false -> [S02, S05]
```

Compared to mapping the entire Stream to `Sale::id` before grouping, placing `mapping` in the downstream preserves the ability to group by attributes of the original object.

### 7.5. Picking the largest element in each group

```java
Map<String, Optional<Sale>> largestByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.maxBy(
            Comparator.comparingLong(Sale::amount)
        )
    ));
```

`Collectors.maxBy` returns `Optional<Sale>` in each group by collector contract. In standard `groupingBy`, keys arise from input elements so each group has at least one element, yet the `Optional` type is retained because the `maxBy` collector can handle empty inputs.

Retrieving the value for a region:

```java
Optional<Sale> largestNorthern =
    largestByRegion.getOrDefault("Bắc", Optional.empty());

System.out.println(
    largestNorthern.map(Sale::id).orElse("None")
); // S01
```

This example requires importing `java.util.Comparator` and `java.util.Optional`.

## 8. Combining Multi-Level Grouping and Partitioning

There is no rule restricting a report to a single collector. `groupingBy` and `partitioningBy` can act as each other's downstream collector.

### 8.1. By region, then split into paid/unpaid

```java
Map<String, Map<Boolean, List<Sale>>> byRegionAndPaid =
    sales.stream()
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.partitioningBy(Sale::paid)
        ));
```

Structure:

```text
"Bắc" ──► true  : [S01, S03]
           false : [S05]

"Nam" ──► true  : [S04]
           false : [S02]

"Tây" ──► true  : [S06]
           false : []
```

**Important property:** region "Tây" appeared, so it gets a `groupingBy` group. Inside that group, `partitioningBy` still creates **both branches**; the unpaid branch is an empty list.

However, a region that never appeared, such as "Đông", will **not** be automatically created in the outer Map.

### 8.2. By status, then group revenue by region

```java
Map<Boolean, Map<String, Long>> amountByPaymentAndRegion =
    sales.stream()
        .collect(Collectors.partitioningBy(
            Sale::paid,
            Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::amount)
            )
        ));
```

Result:

| Status | Bắc | Nam | Tây |
| --- | ---: | ---: | ---: |
| true (paid) | 200.000 | 140.000 | 200.000 |
| false (unpaid) | 50.000 | 60.000 | No Tây key |

Inside the `false` branch there is no Tây region because there are no unpaid transactions in that region. Both **boolean branches** always exist, whereas **region keys in the downstream `groupingBy`** appear only when corresponding data exists.

### 8.3. Grouping by a composite key using a record

If you simply want each *(region, status)* pair as its own group, you can use a record as the key:

```java
record GroupKey(String region, boolean paid) {}

Map<GroupKey, Long> counts = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> new GroupKey(sale.region(), sale.paid()),
        Collectors.counting()
    ));
```

`record` provides `equals` and `hashCode` based on its components, which is convenient when keys span multiple fields.

Unlike nesting `partitioningBy`, the `GroupKey` approach creates only pairs that actually appear: there is no `GroupKey("Tây", false)` entry unless a matching element exists.

## 9. Filtering Before Grouping vs. Filtering Inside the Downstream

This distinction is easily overlooked when building reports that must display all groups.

### 9.1. Pre-filtering: groups with no qualifying elements vanish

```java
Map<String, Long> paidCount = sales.stream()
    .filter(Sale::paid)
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

In the current dataset, all three regions have paid transactions so the Map still contains all three regions. However, if a region had only unpaid transactions, that region **would not appear**.

### 9.2. Downstream filtering: keeps already-created groups

`Collectors.filtering` (Java 9+) applies the condition **after the grouping key has been determined**:

```java
Map<String, Long> paidCountIncludingZero = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.filtering(
            Sale::paid,
            Collectors.counting()
        )
    ));
```

Suppose we add `new Sale("S07", "Đông", 30_000L, false)`:

- With `filter(Sale::paid)` **before** `groupingBy`, the "Đông" key does not appear.
- With `filtering(Sale::paid, counting())` **in the downstream**, the "Đông" key still appears with a value of **0L**.

This is useful when a report must preserve groups present in the input data even when no elements satisfy the secondary condition.

`Collectors.filtering` is not a full replacement for `Stream.filter`; they express **where filtering occurs in the grouping process** and can therefore produce different result structures.

### 9.3. partitioningBy still guarantees both groups

Similarly, on a dataset containing only `paid=true` transactions:

```java
Map<Boolean, Long> counts = Stream.of(
        new Sale("S08", "Bắc", 10_000L, true)
    )
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 1
System.out.println(counts.get(false)); // 0
```

You do not need to manually add the `false` key. That is the advantage of `partitioningBy` when the problem is strictly a boolean dichotomy.

## 10. Map Factories and Result Iteration Order

Element order in a Stream and iteration order over **Map keys** are two different concepts.

### 10.1. groupingBy has an overload specifying the Map type

```java
Map<String, List<Sale>> sortedRegionKeys = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.toList()
    ));
```

`TreeMap::new` causes region keys to be iterated in the natural order of `String`.

You can use `LinkedHashMap` when you want to preserve key insertion order in a pipeline with clear encounter order:

```java
Map<String, List<Sale>> encounterRegionKeys = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

In this sequential example over a `List`, keys are inserted in the order regions are first encountered. Do not assume that every Map created by default `groupingBy` is a `LinkedHashMap`; the default Map class and its iteration order are not guaranteed by the API.

### 10.2. toMap also has a mapFactory

```java
Map<String, Long> sortedAmountByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Sale::amount,
        Long::sum,
        TreeMap::new
    ));
```

The four-parameter overload selects the `Long::sum` merge policy and the `TreeMap` Map type. **`mapFactory` does not replace `mergeFunction`**: if duplicate keys occur, a merge rule is still required.

### 10.3. partitioningBy does not need a mapFactory

`Collectors.partitioningBy` provides no `mapFactory` overload because the key domain is fixed to the two boolean values. Do not rely on the internal iteration order of the returned Map.

If you need to present them in a specific order:

```java
Map<Boolean, List<Sale>> partitions = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

List<Sale> paidFirst = partitions.get(true);
List<Sale> unpaidSecond = partitions.get(false);
```

Key-based access is explicit and avoids guessing `entrySet()` order.

### 10.4. TreeMap and key equality rules

With `HashMap`, keys are equivalent according to `equals`/`hashCode`. With `TreeMap`, ordering and key-duplicate detection rely on a Comparator or the keys' natural ordering.

If a Comparator treats two distinct keys as equal (`compare(a,b) == 0`), `TreeMap` treats them as the same key. When case-insensitive codes are needed, normalize keys explicitly rather than inadvertently losing distinction:

```java
Map<String, Long> normalized = sales.stream()
    .collect(Collectors.toMap(
        sale -> sale.region().trim()
            .toLowerCase(Locale.ROOT),
        Sale::amount,
        Long::sum
    ));
```

This example requires importing `java.util.Locale`. String normalization must follow data rules; for some codes, uppercase and lowercase letters can carry different meanings.

## 11. Edge Cases: Empty Sources, Nulls, and Duplicate Keys

### 11.1. Comparing all three collectors on an empty source

```java
List<Sale> empty = List.of();

Map<String, List<Sale>> groups = empty.stream()
    .collect(Collectors.groupingBy(Sale::region));

Map<Boolean, List<Sale>> partitions = empty.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

Map<String, Sale> map = empty.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));

System.out.println(groups.isEmpty());          // true
System.out.println(partitions.size());         // 2
System.out.println(partitions.get(true));      // []
System.out.println(partitions.get(false));     // []
System.out.println(map.isEmpty());             // true
```

This is a quick check that highlights the contracts of the three APIs.

### 11.2. null in keys and values

For `groupingBy`, a classifier returning `null` causes `NullPointerException`. For `toMap`, avoid relying on whether a specific Map implementation allows `null` keys; define a valid data policy instead.

Values produced by `toMap`'s `valueMapper` should be non-`null`. On common JDK implementations, a `null` value causes `NullPointerException`:

```java
record User(String id, String email) {}

List<User> users = List.of(
    new User("U1", "an@example.com"),
    new User("U2", null)
);

// Do not collect directly with toMap(User::id, User::email)
// when email can be null and there is no handling policy.
```

If business rules allow skipping records missing an email:

```java
Map<String, String> emailsById = users.stream()
    .filter(user -> user.email() != null)
    .collect(Collectors.toMap(
        User::id,
        User::email
    ));
```

If a missing email is a state that must be preserved, use a non-`null` value type to represent it, such as a record or `Optional<String>`, and check the requirements of APIs consuming the Map downstream.

### 11.3. null from mergeFunction can remove an entry

`Map.merge` has a rule: if the merge function returns `null`, an existing mapping can be removed. Because `toMap` uses Map merging mechanics, **do not return null to mean "keep the existing value"**.

```java
Map<String, Long> map = new HashMap<>();

map.merge("Bắc", 100L, Long::sum);
map.merge("Bắc", 20L, (oldValue, newValue) -> null);

System.out.println(map.containsKey("Bắc")); // false
```

This example requires importing `java.util.HashMap`. When business rules call for keeping the first value, return `oldValue` explicitly.

### 11.4. Distinguishing null from empty groups

- **Key absent from a `groupingBy` Map:** no element classified to that key.
- **`true`/`false` key of `partitioningBy` with an empty list:** the branch is guaranteed to exist, yet has no elements.
- **A `toMap` Map lacking a key:** no element produced that key, or a special merge rule removed the mapping.

Do not conflate these meanings when designing APIs that return reports to users.

## 12. Ordering, Associativity, and Parallel Mode

### 12.1. Collectors can accumulate across multiple branches

A `parallelStream()` pipeline can split the source into parts, accumulate each part, and combine intermediate results.

```text
Source [S01, S02, S03, S04, S05, S06]
                   │
               trySplit(...)
             ┌─────┴──────┐
             ▼            ▼
         part A         part B
             │            │
       temp Map A     temp Map B
             └────┬───────┘
                  ▼
              merge Map
                  │
                  ▼
             final result
```

How the source is split and how many times internal functions are invoked depend on the framework and must not be relied upon as business rules. For `collect` to work correctly in parallel, accumulation and combination must satisfy the collector contract, including **identity, associativity, result equivalence**, and avoiding unsafe shared mutable state.

### 12.2. groupingBy can be used on parallelStream

```java
Map<String, Long> parallelCounts = sales.parallelStream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Count results must still be business-equivalent to sequential execution. However, standard `groupingBy` **is not a concurrent collector**. The framework may need to merge branch Maps; when there are many keys, merging incurs overhead.

`Collectors.groupingByConcurrent` is another option when appropriate, but its result does not guarantee element encounter order like an ordered collector. If lists inside each group must follow source order, do not blindly switch to `groupingByConcurrent` just for speed.

### 12.3. partitioningBy does not contend over many keys

`partitioningBy` has only two branches; that does not mean it is safe for multiple threads to write directly into the same `ArrayList`. Standard collectors are responsible for organizing accumulation containers and combining them according to contract in parallel execution.

```java
Map<Boolean, Long> parallelPaidCounts = sales.parallelStream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));
```

Do not create a shared `long[]` variable and increment it inside `forEach`; doing so can introduce race conditions.

### 12.4. toMap and mergeFunction must be associative

`Long::sum`, `Long::max`, and `Long::min` are merge rules that generally fit integer aggregation problems, keeping overflow in mind. Subtraction is not associative:

```text
(100 - 40) - 10 = 50
100 - (40 - 10) = 70
```

Therefore:

```java
// Do not use subtraction as a general merge function when
// the result must not depend on split/merge order:
// (left, right) -> left - right
```

If `mergeFunction` has side effects—such as logging to a shared `ArrayList`—the invocation count and call order can change in parallel execution. A proper collector expresses its result through **accumulated data**, not mandatory business side effects placed inside the merge function.

### 12.5. "Keep first" and "keep last" depend on source order

With a `List` that has encounter order, `(first,next)->first` and `(first,next)->next` can express picking the first/last element per key in that order when using standard `toMap`.

However, on a source without encounter order, first/last is not guaranteed. If the requirement is the **newest order by time**, merge using `BinaryOperator.maxBy(Comparator.comparing(...))` with a stable tie-breaker rather than assuming the last-processed element is the newest.

`toConcurrentMap` is a concurrent, unordered collector. Using it with a first/last policy based on source order can pick values depending on execution scheduling; it is not suitable when ordering is a business requirement.

## 13. Performance and Intermediate Data Structures

No single collector is always fastest. Efficiency depends on the goal, number of distinct keys, source size, and how much data must be retained.

### 13.1. Memory differences

Given `n` elements and `k` distinct keys:

| Collection method | Memory profile |
| --- | --- |
| Default `groupingBy(key)` | Holds lists of elements; total references can scale with `n`, plus group overhead. |
| `groupingBy(key, counting())` | Primarily holds count state for `k` groups. |
| Default `partitioningBy(predicate)` | Holds elements in two lists; total references scale with `n`. |
| `partitioningBy(predicate, counting())` | Requires only two result counters and appropriate accumulation state. |
| `toMap(key, value, merge)` | One final value per key, typically scaling with `k`. |

If you only need counts by region, there is no need to collect all transactions into lists just to call `size()`. If you only need revenue by region, `summingLong` or `Long::sum` avoids retaining all transactions.

### 13.2. Time and merge overhead

Collecting into a standard hash-based Map usually has average cost close to linear in the number of elements, though it depends on hash quality, key distribution, key extraction, the merge function, and collisions.

`TreeMap` typically has `O(log k)` operation cost in the number of keys `k` and provides comparator-based key iteration order. `LinkedHashMap` needs extra structure to track insertion order. In parallel execution, Map split/merge overhead can outweigh computation gains if the dataset is not large enough or the accumulation work is too light.

### 13.3. Infinite data and I/O resources

Full-source `collect` aggregations generally require a **finite, bounded** source. On an unbounded `Stream.generate(...)`, the pipeline may never terminate, and a collector keeping lists can grow memory without bound.

If the data comes from a file:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class PaidStateFromFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("statuses.txt");

        try (Stream<String> lines = Files.lines(path)) {
            Map<Boolean, Long> counts = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.partitioningBy(
                    line -> line.equalsIgnoreCase("PAID"),
                    Collectors.counting()
                ));

            System.out.println(counts.get(true));
            System.out.println(counts.get(false));
        }
    }
}
```

The sample assumes each line is a status, and any status other than `PAID` goes into `false`. For production data, define a policy for invalid statuses. `Files.lines` must be closed with `try-with-resources`: **`collect` does not automatically close file resources**.

## 14. Complete Java Example: All Three Collectors on One Source

The program below demonstrates grouping, partitioning, toMap, and multi-level downstream collectors in a single run. Save as `GroupingPartitioningMapDemo.java` and run with Java 17+.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class GroupingPartitioningMapDemo {
    record Sale(String id, String region, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S01", "Bắc", 120_000L, true),
            new Sale("S02", "Nam",  60_000L, false),
            new Sale("S03", "Bắc",  80_000L, true),
            new Sale("S04", "Nam", 140_000L, true),
            new Sale("S05", "Bắc",  50_000L, false),
            new Sale("S06", "Tây", 200_000L, true)
        );

        // 1. Multiple elements per region key.
        Map<String, List<Sale>> byRegion = sales.stream()
            .collect(Collectors.groupingBy(Sale::region));

        // 2. Always has both true and false branches.
        Map<Boolean, List<Sale>> byPayment = sales.stream()
            .collect(Collectors.partitioningBy(Sale::paid));

        // 3. One Sale per unique ID.
        Map<String, Sale> byId = sales.stream()
            .collect(Collectors.toMap(
                Sale::id,
                Function.identity()
            ));

        // 4. One long total per region, keys sorted.
        Map<String, Long> totalAmountByRegion = sales.stream()
            .collect(Collectors.toMap(
                Sale::region,
                Sale::amount,
                Long::sum,
                TreeMap::new
            ));

        // 5. Two boolean branches, each grouped by region.
        Map<Boolean, Map<String, Long>> amountByPaymentAndRegion =
            sales.stream()
                .collect(Collectors.partitioningBy(
                    Sale::paid,
                    Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingLong(Sale::amount)
                    )
                ));

        System.out.println(byRegion.get("Bắc").size());       // 3
        System.out.println(byPayment.get(true).size());       // 4
        System.out.println(byPayment.get(false).size());      // 2
        System.out.println(byId.get("S03").amount());         // 80000
        System.out.println(totalAmountByRegion.get("Bắc"));  // 250000

        System.out.println(
            amountByPaymentAndRegion.get(true).get("Bắc")
        ); // 200000

        System.out.println(
            amountByPaymentAndRegion.get(false).get("Nam")
        ); // 60000

        System.out.println(
            amountByPaymentAndRegion.get(false).containsKey("Tây")
        ); // false: there are no unpaid transactions in Tây.
    }
}
```

### 14.1. Meaning of each result

| Variable | Map type | Meaning |
| --- | --- | --- |
| `byRegion` | `Map<String, List<Sale>>` | Each region holds multiple `Sale`s. |
| `byPayment` | `Map<Boolean, List<Sale>>` | Two sets: paid and unpaid. |
| `byId` | `Map<String, Sale>` | Lookup by unique ID. |
| `totalAmountByRegion` | `Map<String, Long>` | Total amount by region, including unpaid transactions. |
| `amountByPaymentAndRegion` | `Map<Boolean, Map<String, Long>>` | Total amount by status, then by region. |

None of the collection operations above modify the contents of `sales`.

### 14.2. Why must a new Stream be created for each collect?

A `Stream` can be consumed only once. Because `sales` is a re-traversable `List`, each `sales.stream()` call creates a new Stream:

```java
var stream = sales.stream();
long count = stream.count();

// Do not reuse:
// Map<String, List<Sale>> wrong = stream.collect(
//     Collectors.groupingBy(Sale::region)
// );
```

If the original source is a single-use iterator or a file-reading Stream, design the pipeline to compute all needed results in one pass—for example, with a custom composite collector or `Collectors.teeing` when appropriate.

### 14.3. What if you only need three different results?

Collecting multiple times from a small List can be simple enough. However, if the source is very large or traversal is expensive, consider a combined summary that computes multiple counts and sums in a single pass. That belongs to custom collector design or `teeing`, rather than misusing a `Map<String, List<Sale>>` holding all records when only statistics are needed.

## 15. Collector Decision Table

| Practical requirement | Collector to consider | Reason |
| --- | --- | --- |
| List of transactions by region | `groupingBy(Sale::region)` | Each key holds multiple elements. |
| Count transactions by region | `groupingBy(Sale::region, counting())` | No need to retain individual elements. |
| Total amount by region | `groupingBy(..., summingLong(...))` or `toMap(..., Long::sum)` | Each key needs only a sum. |
| Split paid/unpaid orders | `partitioningBy(Sale::paid)` | Two boolean branches, including empty ones. |
| Count orders above/below threshold | `partitioningBy(predicate, counting())` | Two counts covering both statuses. |
| Look up transaction by unique ID | `toMap(Sale::id, identity())` | One object per key. |
| Pick best record per key | `toMap(key, identity(), BinaryOperator.maxBy(comparator))` | Explicit rule for picking one representative. |
| Keep all records per region/status combination | `groupingBy(compositeKey)` or nested `partitioningBy` | Depends on whether both branches must always exist. |
| By region, counting only qualifying orders | `groupingBy(region, filtering(predicate, downstream))` | Keeps regions whose elements all fail the predicate. |
| Keys need lexicographical sorting | `groupingBy(key, TreeMap::new, downstream)` or `toMap(..., TreeMap::new)` | Controls Map iteration order. |
| Parallel processing with many groups | `groupingByConcurrent` if unordered result is acceptable | Must evaluate correctness and measure performance. |

If you cannot decide within a few seconds, write down the **desired result data type** first. For example, `Map<String, List<Sale>>` usually points to `groupingBy`; `Map<Boolean, Long>` points to `partitioningBy(predicate, counting())`; `Map<String, Sale>` points to `toMap` with a duplicate-key policy.

## 16. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `toMap(region, identity())` when a region has multiple records | `IllegalStateException` due to duplicate keys. | Use `groupingBy(region)` or provide a merge function. |
| Using `groupingBy(Sale::paid)` and assuming both `true`/`false` exist | An unseen branch may be missing its key. | Use `partitioningBy(Sale::paid)`. |
| Treating `partitioningBy` as arbitrary multi-group grouping | Splits only by boolean. | Use `groupingBy(classifier)` for multiple labels. |
| Needing total amount yet keeping full `List<Sale>` in the Map | Consumes unnecessary memory. | Use `summingLong`, `counting`, or `toMap` with merge. |
| Confusing `filter` before grouping with downstream `Collectors.filtering` | Groups with no qualifying records may vanish. | Place filtering according to the report contract. |
| Expecting default `groupingBy` or `toMap` Map to keep Stream order | No guarantee on Map type or iteration order. | Use an appropriate `mapFactory` if needed. |
| Expecting `partitioningBy` to have a `mapFactory` overload | No such overload exists. | Access `true` and `false` keys explicitly. |
| Assuming `groupingBy` accepts `null` keys because `HashMap` does | `NullPointerException` when classifier returns null. | Normalize or use a key representing missing data. |
| Returning `null` values in `toMap` | Can throw `NullPointerException`. | Filter/validate or use a non-null value type. |
| Using `(a,b)->a-b` to merge revenue | Not associative across split/merge. | Use `Long::sum` or a suitable associative sum. |
| Using `parallelStream()` and mutating a shared `ArrayList` inside a lambda | Race condition. | Use a contract-compliant collector. |
| Using first/last on an unordered source | No guarantee which element wins. | Choose with a Comparator over domain fields. |
| Forgetting `long` overflow in amount totals | Wrong results when exceeding numeric bounds. | Use `Math.addExact` or a wider numeric type per policy. |
| Calling `collect` on an unbounded infinite Stream | Never terminates or exhausts memory. | Bound the source appropriately. |
| Calling `collect` on a file-backed Stream without closing it | I/O resource leak. | Use `try-with-resources`. |

## 17. Practice Exercises

**Exercise 1 — Three Map shapes.** Using the `Sale` list from Section 2, create `Map<String,List<Sale>>` by region, `Map<Boolean,List<Sale>>` by payment status, and `Map<String,Sale>` by ID. Explain when each Map is a better fit than the other two.

**Exercise 2 — Empty source.** Given `List<Sale> empty = List.of()`, collect three Maps using `groupingBy`, `partitioningBy`, and `toMap`. Check the key count and the values of both boolean branches.

**Exercise 3 — Per-key totals.** Compute amounts by region in two ways: `groupingBy(..., summingLong(...))` and `toMap(..., Long::sum)`. Compare the values for each key.

**Exercise 4 — Empty group after filtering.** Add a "Đông" region that has only unpaid transactions. Compare the result of filtering before `groupingBy` vs. `Collectors.filtering` in the downstream.

**Exercise 5 — Multi-level.** Create `Map<String, Map<Boolean, Long>>` with total amounts by region and then by status. Verify that the `false` branch for region Tây still exists and has total `0L`.

**Exercise 6 — Choosing a representative record.** For transactions sharing the same region key, pick the transaction with the highest `amount` using `toMap` and `BinaryOperator.maxBy`. Add a tie-breaker by `id` if multiple transactions have the same amount.

**Exercise 7 — Null key check.** Add a transaction with `region = null`. Observe how `groupingBy` behaves; propose a rule that preserves missing-region information without colliding with real region names.

**Exercise 8 — Parallel.** Count transactions by region using `stream()` and `parallelStream()`. Compare both Maps by value, independent of Map iteration order. Explain why a collector can run in parallel yet still have to merge intermediate Maps.

**Exercise 9 — Precision choices.** If total amounts can exceed `long` limits, propose an accumulation type or error-detection policy instead of blindly trusting `Long::sum`.

**Exercise 10 — Report design.** A system needs the total transaction count, paid transaction count, and paid total amount by region simultaneously. Propose a result type and how to build an appropriate downstream collector, pointing out where a custom collector might be needed.

Hint for Exercise 5:

```java
Map<String, Map<Boolean, Long>> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.partitioningBy(
            Sale::paid,
            Collectors.summingLong(Sale::amount)
        )
    ));

System.out.println(totals.get("Tây").get(false)); // 0
```

Because `groupingBy` already created the "Tây" group, the downstream `partitioningBy` for that group still contains both `true` and `false`, even though one branch's list is empty.

## 18. Core Takeaways

- **`groupingBy`** groups by a key `K` and defaults to returning `Map<K,List<T>>`. With a downstream collector, each group can become a count, total amount, set of IDs, or custom summary.
- **`partitioningBy`** groups by a `Predicate<T>` and always provides **exactly two keys, `true` and `false`**, even when the source or one branch is empty.
- **`toMap`** produces **one value per key**. The overload without a merge function rejects duplicate keys; the overload with a merge function allows keeping first, keeping last, summing, picking the max, or applying business rules.
- **The downstream collector determines the output structure** of `groupingBy`/`partitioningBy`. You can nest two collectors for multi-level reports and must pay attention to the difference between an absent group and an empty branch.
- **Filtering before `groupingBy` can drop a group key**, whereas `Collectors.filtering` in the downstream preserves already-created groups and returns the downstream result for groups with no matching elements.
- **Map iteration order is not the same as Stream encounter order.** Use `TreeMap` or `LinkedHashMap` according to your goal; access both boolean keys explicitly when partitioning.
- **Collectors must obey accumulation and combination contracts**, especially in parallel execution. Do not rely on side effects, execution order, or non-associative merge operations.
- **Correctness depends on data and source characteristics:** avoid `null` classifiers, consider duplicate keys, numeric overflow, the cost of retaining many lists, infinite Streams, and I/O resources.
- Clearly distinguishing these three Map collectors is the foundation for designing deeper grouping, custom collectors, `Spliterator` optimizations, and advanced declarative pipelines in **JAVA_STREAM_API**.
