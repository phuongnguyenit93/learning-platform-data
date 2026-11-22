# Designing Maps with Duplicate Keys and Deterministic Output Order

## 1. Problem Statement: Correct Results Require Both Duplicate-Key Handling and Clear Ordering

When processing data declaratively with the **Java Stream API**, we often collect a `Stream<T>` into a `Map<K, V>` for fast lookup by product code, customer ID, or business group. This collection step commonly runs into two issues:

1. **Duplicate keys:** multiple source elements produce the same key `K`. The program must decide whether to keep one record, sum values, or fail with an error.
2. **Output ordering:** iterating over the Map's entries may need to follow original appearance order or sorted key order, rather than depending on the incidental behavior of `HashMap`.

For example, a product update table has multiple rows sharing the SKU `"P01"`:

```text
Source rows (ordered):
  P02 | Headphones     | version 1
  P01 | Old Notebook   | version 1
  P01 | New Notebook   | version 2
  P03 | Pen            | version 1
  P02 | Headphones Pro | version 3

Requirements:
  - Each SKU appears only once in the Map.
  - Duplicate keys: keep the record with the highest version.
  - When printing the report: iterate in ascending SKU order.

Expected result:
  P01 -> New Notebook   (v2)
  P02 -> Headphones Pro (v3)
  P03 -> Pen            (v1)
```

This lesson belongs to the **Beginner and Intermediate Exercises** chapter of the `JAVA_STREAM_API` module. We will solve the problem using `Collectors.toMap`, `Map.merge`, `LinkedHashMap`, `TreeMap`, and Stream operations such as `sorted`, `groupingBy`, and `collect`.

**Learning objectives:**

- Understand why the two-argument `Collectors.toMap` throws on duplicate keys.
- Write meaningful merge functions: keep old, replace with new, accumulate, or select the best record.
- Choose `LinkedHashMap` for insertion order and `TreeMap` for key-sorted order.
- Distinguish **source order**, **parallel processing order**, and **Map iteration order**.
- Write a Java 17+ program with test data, expected output, and deterministic assertions.

The core collectors and Map types used here have existed since Java 8. The complete example uses `record` and `Stream.toList()`, so it targets **Java 17+**.

## 2. Review: What Is a Map and Why Do Duplicate Keys Happen?

A `Map<K, V>` stores `key → value` pairs. Each key can map to **only one direct value** in the same Map; when another value arrives for the same key, there must be a replacement or combination rule.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> points = new HashMap<>();
points.put("A", 3);
points.put("B", 5);
points.put("A", 7); // Overwrites the previous value for A.

System.out.println(points.get("A")); // 7
System.out.println(points.size());   // 2
```

When collecting from a Stream, keys are produced by a **key mapper**, and values by a **value mapper**. Two distinct source elements can still yield the same key:

```java
record Sale(String id, String sku, int quantity) {}

List<Sale> sales = List.of(
        new Sale("S01", "P01", 2),
        new Sale("S02", "P02", 3),
        new Sale("S03", "P01", 4)
);

// Both sales S01 and S03 share the key P01.
```

Importantly: **duplicate keys are not necessarily a data error**. In a total-quantity-by-SKU report, duplicates are expected and must be **summed**. In a "one unique record per SKU" table, duplicates might be an error, or require retaining the latest version.

Before writing code, answer three questions:

1. **What is the key?** `sku`, `customerId`, or a composite key?
2. **What happens on collision?** Throw an error, sum, pick the first, pick the last, or pick the highest-ranked?
3. **What output order is required?** Unspecified, first-appearance order, or sorted by key?

Without answering these three questions, even a concise `toMap` pipeline can violate business rules.

## 3. Two-Argument `Collectors.toMap`: Duplicate Keys Throw an Exception

Start with the shortest form:

```java
Map<String, Sale> bySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity()
        ));
```

This snippet **throws `IllegalStateException`** because both `S01` and `S03` map to key `"P01"`. The two-argument overload does not default to keeping either the first or the last row.

General signature:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper
)
```

In the example:

| Component | Expression | Type and Role |
| --- | --- | --- |
| Input element | `Sale` | Each transaction is an object. |
| `keyMapper` | `Sale::sku` | Produces `String` as the key. |
| `valueMapper` | `Function.identity()` | Keeps the `Sale` object itself as the value. |
| Result type on success | `Map<String, Sale>` | One `Sale` per SKU. |
| On key collision | No merge function provided | Throws `IllegalStateException`. |

**When should you use the two-argument overload?** When inputs **must have unique keys** and a collision indicates a business error—for instance, a validated config list guaranteed to have unique IDs.

Note: the default `toMap` overload **does not guarantee the Map implementation class or entry iteration order**. Even without duplicates, never write tests relying on `map.toString()` having a fixed order.

## 4. Three-Argument `Collectors.toMap`: Defining a Collision Policy

When duplicate keys are valid, use the overload with a `mergeFunction`:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction
)
```

`mergeFunction` receives the **existing value** and the **incoming value for the same key**, returning the combined value. It must not mutate the source being traversed. Three common policies are:

### 4.1. Keep the Existing Value

```java
Map<String, Sale> keepExisting = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity(),
                (existing, incoming) -> existing
        ));

System.out.println(keepExisting.get("P01").id()); // S01
```

In this **sequential pipeline with encounter order**, the rule keeps the first record encountered for SKU `P01`.

### 4.2. Use the Incoming Value

```java
Map<String, Sale> useIncoming = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity(),
                (existing, incoming) -> incoming
        ));

System.out.println(useIncoming.get("P01").id()); // S03
```

With a `List` traversed sequentially, this keeps the last record encountered. **Do not confuse "last in List" with "latest by date"**: selecting by version or timestamp requires a comparator.

### 4.3. Accumulate Values

```java
Map<String, Integer> quantityBySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum
        ));

System.out.println(quantityBySku.get("P01")); // 6 = 2 + 4
System.out.println(quantityBySku.get("P02")); // 3
```

When summing very large quantities, `int` can overflow. Choose `long` or a numeric type appropriate for the business domain; `Long::sum` can still overflow `long`.

### Merge Function Selection Table

| Duplicate Key Requirement | Sample Merge Function | What to Control |
| --- | --- | --- |
| Keep old value | `(oldValue, newValue) -> oldValue` | "Old" means pipeline encounter order, not necessarily chronologically oldest. |
| Replace with new value | `(oldValue, newValue) -> newValue` | Encounter order must be well-defined. |
| Sum values | `Integer::sum` / `Long::sum` | Numeric bounds and associative merging. |
| Pick maximum | `Integer::max` / `BinaryOperator.maxBy(comparator)` | Comparator must reflect business priority. |
| Concatenate strings | `(left, right) -> left + "," + right` | Order, delimiter, and string-allocation cost. |

If the requirement prohibits duplicate data, **do not add an arbitrary merge function just to silence the exception**. Silently dropping records can corrupt reports without warning.

## 5. Selecting the Highest-Priority Record with a Comparator

Suppose multiple product updates share the same SKU. Instead of "first arrived" or "last arrived", business rules require **keeping the highest version**:

```java
record Product(String sku, String name, int version, long priceCents) {}

List<Product> updates = List.of(
        new Product("P02", "Headphones", 1, 200_000L),
        new Product("P01", "Old Notebook", 1, 30_000L),
        new Product("P01", "New Notebook", 2, 35_000L),
        new Product("P03", "Pen", 1, 8_000L),
        new Product("P02", "Headphones Pro", 3, 250_000L)
);

Comparator<Product> byVersion =
        Comparator.comparingInt(Product::version);

Map<String, Product> latestBySku = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion)
        ));

System.out.println(latestBySku.get("P01").name()); // New Notebook
System.out.println(latestBySku.get("P02").version()); // 3
```

`maxBy` uses the comparator to choose between two values on key collision. However, if **two records have the same version**, the comparator returns 0. In that case, which record wins may be underspecified, especially under parallel execution or unordered input.

Add tie-breakers (*tie-break*) when the result must be **deterministic**:

```java
Comparator<Product> policy = Comparator
        .comparingInt(Product::version)
        .thenComparing(Product::name)
        .thenComparingLong(Product::priceCents);

Map<String, Product> selected = updates.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(policy)
        ));
```

Here, higher version wins; ties break by name, then by price. **This is only an illustrative rule**, not a universal business default. Real systems usually compare `updatedAt`, a revision number, or a stable record ID. If two distinct objects still compare equal while differing in other fields, "which record to keep" is not yet fully defined.

**Crucial for parallel reduction:** the merge function must be associative and independent of shared mutable state. Taking the maximum under a consistent comparator with full tie-breaking is far safer than "whichever thread reaches the Map first".

## 6. Map Order Is Not Stream Order

This is the second half of the problem: **the same Map entries can be iterated in different orders**.

```java
Map<String, Integer> unorderedByContract = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::version,
                Integer::max
        ));

System.out.println(unorderedByContract);
// Contains entries P01=2, P02=3, P03=1;
// entry iteration order is not guaranteed.
```

Default `Collectors.toMap` **does not promise** `HashMap`, `LinkedHashMap`, `TreeMap`, or any specific iteration order. Therefore, never rely on your current machine consistently printing `P01` before `P02`.

Distinguish three kinds of order:

| Kind of Order | Example | Is It Guaranteed? |
| --- | --- | --- |
| Source order | Element index in a `List` | Yes, for ordered sources like `List.stream()`. |
| Execution order | Which thread runs `map`/`filter` first | Not fixed for `parallelStream()`. |
| Result Map iteration order | `entrySet()`, `keySet()`, `forEach` | Depends on the concrete Map implementation's contract. |

If the report requires "SKUs from smallest to largest", you must **choose a Map implementation that maintains key order** or **sort entries when formatting the report**. Having an ordered source Stream does not automatically produce a key-ordered Map.

## 7. `LinkedHashMap`: Preserving Key Insertion Order

`LinkedHashMap` iterates in **insertion order** under its default configuration. When an existing key's value is updated, that update **does not change the key's position** in insertion-order mode.

To choose the Map class in `Collectors.toMap`, use the **four-argument** overload:

```java
static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction,
        Supplier<M> mapFactory
)
```

Example:

```java
Map<String, Product> insertionOrder = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                LinkedHashMap::new
        ));

System.out.println(new ArrayList<>(insertionOrder.keySet()));
// [P02, P01, P03]
```

Because this is a **sequential Stream with source order**, keys first appear in the order `P02`, `P01`, `P03`. When `P01` or `P02` appears again, the merge function updates the value without changing the key's insertion position.

**When to choose it?** When the report must preserve **first-appearance order of keys** in a stable source—for example, grouping visits by first recorded session ID.

### What If Source Order Is Unspecified?

`LinkedHashMap` only records the insertion order **supplied to it**. If the input is an unordered `HashSet`, passing `LinkedHashMap::new` does not create a stable business order.

For deterministic output, **establish input order first** (e.g., sort by SKU, timestamp, and ID) or use a Map with a comparator. Do not treat `LinkedHashMap` as a substitute for sorting rules.

## 8. `TreeMap`: Output Sorted by Key

`TreeMap` maintains keys in **natural order** or according to a supplied `Comparator`. When a report must iterate in ascending SKU order, `TreeMap` is the direct choice:

```java
Map<String, Product> sortedBySku = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                TreeMap::new
        ));

System.out.println(new ArrayList<>(sortedBySku.keySet()));
// [P01, P02, P03]
```

Unlike `LinkedHashMap`, `TreeMap` never depends on insertion order to determine key iteration order. For `String` keys, natural order uses `String.compareTo`, which is **not necessarily the user's linguistic collation order**.

### Descending Order

```java
Map<String, Product> descending = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                () -> new TreeMap<String, Product>(
                        Comparator.reverseOrder()
                )
        ));

System.out.println(new ArrayList<>(descending.keySet()));
// [P03, P02, P01]
```

**Caution:** `TreeMap`'s comparator not only controls ordering—it also defines whether the Map treats two keys as equal. If `compare(a, b) == 0` for two keys that business rules treat as distinct, `TreeMap` can merge them into one entry.

Example:

```java
TreeMap<String, Integer> caseInsensitive =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

caseInsensitive.put("abc", 1);
caseInsensitive.put("ABC", 2);

System.out.println(caseInsensitive.size()); // 1
```

If SKUs are case-sensitive, that comparator is **inappropriate**. Conversely, if SKUs are case-insensitive, normalize them consistently according to business rules upon ingestion.

## 9. `sorted` Before `collect`: When Is It Useful?

You can also produce a key-ordered Map by preserving insertion order after sorting the source:

```java
Map<String, Product> sortedThenInserted = updates.stream()
        .sorted(Comparator.comparing(Product::sku))
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                LinkedHashMap::new
        ));

System.out.println(new ArrayList<>(sortedThenInserted.keySet()));
// [P01, P02, P03]
```

Here, `sorted` groups records by SKU order, and `LinkedHashMap` preserves the order in which each key is first inserted. The result is ordered by SKU in this **ordered sequential Stream** example.

Comparing strategies:

| Strategy | Semantics | When to Choose |
| --- | --- | --- |
| `toMap(..., TreeMap::new)` | Map always iterates keys by comparator | When the Map itself must maintain key ordering. |
| `sorted(...).collect(toMap(..., LinkedHashMap::new))` | Sorts source then preserves key insertion order | When source ordering matters or controls key emission order. |
| Collect Map then sort `entrySet` on export | Storage Map is unordered; output is sorted | When only one reporting channel needs a specific order. |

If you only need keys sorted, sorting the entire source beforehand is not always worthwhile: `TreeMap` can be simpler. If you need ordering by **a record value** or custom policy, `sorted` before collecting can be a sensible design choice, while still requiring a merge rule for duplicate keys.

## 10. Exporting a Map in Deterministic Order Without Changing Storage Structure

Sometimes a service needs a Map for fast lookups, and only needs key sorting when generating a report.

There is no need to rebuild the Map; you can sort its entries directly:

```java
Map<String, Integer> rawTotals = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum
        ));

List<String> reportLines = rawTotals.entrySet().stream()
        .sorted(Map.Entry.comparingByKey())
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(reportLines);
// [P01=6, P02=3]
```

`Map.Entry.comparingByKey()` uses natural `String` ordering, so **report line order is deterministic** regardless of the underlying Map implementation.

If the report must sort by **value descending**, add a key tie-breaker so rows with equal values still have a deterministic order:

```java
List<String> linesByQuantity = rawTotals.entrySet().stream()
        .sorted(
                Map.Entry.<String, Integer>comparingByValue(
                        Comparator.reverseOrder()
                ).thenComparing(Map.Entry.comparingByKey())
        )
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(linesByQuantity);
// [P01=6, P02=3]
```

**Important for testing:** `Map.equals` compares key/value contents, **not iteration order**. When ordered output lines are required, assert directly on `reportLines` or an ordered list of keys rather than checking Map equality alone.

External serializers may impose their own ordering policies. When producing deterministic JSON or CSV, enforce ordering at the serialization/output layer and test the serialized output itself, rather than assuming every serializer iterates Maps identically.

## 11. Ordering with `parallelStream`: Separate Two Concerns

With a `List` source, `parallelStream()` **does not erase encounter order**, though it does not fix lambda execution timing.

```java
List<String> orderedCodes = updates.parallelStream()
        .map(Product::sku)
        .toList();

System.out.println(orderedCodes);
// [P02, P01, P01, P03, P02]
```

However, when **selecting values for duplicate keys**, rely on a criteria-based merge operation rather than "whichever thread writes to the Map first":

```java
Map<String, Product> deterministicValues = updates.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(policy),
                TreeMap::new
        ));

System.out.println(new ArrayList<>(deterministicValues.keySet()));
// [P01, P02, P03]
```

Here, `TreeMap` orders the keys, and `maxBy(policy)` selects the winning record by value, **not by thread completion timing**. To remain completely deterministic when two different records compare equal, add a tie-breaker or define duplicate-rank error handling.

**Do not do this:**

```java
Map<String, Product> shared = new HashMap<>();

// WRONG: mutating a shared HashMap from multiple threads.
updates.parallelStream()
        .forEach(product -> shared.put(product.sku(), product));
```

`HashMap` does not support concurrent writes, and "keep later" depends on thread scheduling. Even switching to `ConcurrentHashMap` leaves **which record must win** undefined when calling `put` without business criteria.

### Tip for Selecting the "First Row" by Source Position in Parallel

Do not encode "first" via thread execution order. When you must select by **source index**, attach the index before collecting:

```java
record IndexedProduct(int index, Product product) {}

Map<String, IndexedProduct> firstByIndex =
        java.util.stream.IntStream.range(0, updates.size())
                .parallel()
                .mapToObj(i -> new IndexedProduct(i, updates.get(i)))
                .collect(Collectors.toMap(
                        entry -> entry.product().sku(),
                        java.util.function.Function.identity(),
                        java.util.function.BinaryOperator.minBy(
                                Comparator.comparingInt(IndexedProduct::index)
                        ),
                        TreeMap::new
                ));

System.out.println(firstByIndex.get("P01").product().name()); // Old Notebook
System.out.println(firstByIndex.get("P01").index());          // 1
```

Every List position has a unique index, so `minBy(index)` establishes an unambiguous selection rule. This is useful when a pipeline requires **first position** while running in parallel.

## 12. `null`, Invalid Keys, and Equality Rules

Before collecting into a Map, define policies for missing data:

- **`null` source element:** method references like `Product::sku` throw `NullPointerException`.
- **`null` returned by value mapper:** standard `toMap` collectors reject null values; do not use `null` as a placeholder value.
- **`null` keys:** Map implementations differ; `TreeMap` with natural ordering, `ConcurrentHashMap`, and `toUnmodifiableMap` reject null keys. Never depend on one Map implementation's quirks.
- **Equal keys:** hash-based Maps rely on `equals`/`hashCode`; `TreeMap` relies on its comparator, which must align with key identity rules.

Example filtering out null elements and missing keys before collecting:

```java
List<Product> input = new ArrayList<>(updates);
input.add(null);
input.add(new Product(null, "Missing SKU", 1, 0L));

Map<String, Product> valid = input.stream()
        .filter(java.util.Objects::nonNull)
        .filter(product -> product.sku() != null
                && !product.sku().isBlank())
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                TreeMap::new
        ));
```

If codes are case-sensitive, `"p01"` and `"P01"` are distinct keys. If business rules treat them as identical, normalize first:

```java
Map<String, Long> normalizedCount = updates.stream()
        .collect(Collectors.toMap(
                product -> product.sku().strip()
                        .toUpperCase(java.util.Locale.ROOT),
                product -> 1L,
                Long::sum,
                TreeMap::new
        ));
```

In the sample data, `P01` and `P02` each appear twice. Normalization requires **consistent rules between writing and querying**. Never normalize silently if the system treats case differences as meaningful.

## 13. Unmodifiable Maps Are Not Ordered Maps

Modern Java provides methods for creating unmodifiable Maps, such as `Map.copyOf` and `Collectors.toUnmodifiableMap`. They prevent **adding or removing entries**, but **do not guarantee iteration order from the source or by key**:

```java
Map<String, Integer> fixed = Map.copyOf(quantityBySku);
// fixed.put("P99", 1); // UnsupportedOperationException
```

`Map.copyOf` rejects `null` keys and values. It is not a mechanism for guaranteeing iteration order. Likewise, `Collectors.toUnmodifiableMap` still requires a merge function for duplicate keys and does not define output ordering.

If you must **preserve the order of a sorted Map**, make a private copy and wrap it in an unmodifiable view:

```java
Map<String, Product> orderedReadOnly =
        java.util.Collections.unmodifiableMap(
                new TreeMap<>(sortedBySku)
        );

System.out.println(new ArrayList<>(orderedReadOnly.keySet()));
// [P01, P02, P03]
```

`Collections.unmodifiableMap` creates a read-only view through that reference. Here, a new `TreeMap` is allocated internally and no mutable reference is exposed, protecting the **entry structure** from callers. Note this is still a **shallow copy**: if values are mutable objects, their internal state could still be mutated elsewhere.

If other code retains a reference to the backing Map of an unmodifiable view, mutations to the backing Map remain visible through the view. Creating a **defensive copy** is therefore essential.

## 14. Comparison with `groupingBy`: When to Keep All Duplicate Records?

`toMap` enforces **one value per key**, even if that value is a List. When business rules require **keeping every record** sharing a key, `groupingBy` is the direct tool:

```java
Map<String, List<Sale>> allSalesBySku = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::sku,
                TreeMap::new,
                Collectors.toList()
        ));

System.out.println(allSalesBySku.get("P01").size()); // 2
System.out.println(new ArrayList<>(allSalesBySku.keySet()));
// [P01, P02]
```

Comparison:

| Need | Suitable Collector |
| --- | --- |
| Keys must be unique; collision is an error | `toMap(keyMapper, valueMapper)` |
| Keep one chosen record per key | `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` |
| Keep a sum or count per key | `toMap(..., Long::sum, ...)` or `groupingBy(..., summingLong/counting)` |
| Keep the **full list of records** per key | `groupingBy(keyMapper, mapFactory, toList())` |
| Multi-level grouping | `groupingBy(..., groupingBy(...))` or composite key |

Default `groupingBy` does not guarantee Map ordering; its `mapFactory` overload lets you request `TreeMap` or `LinkedHashMap` when needed.

With downstream collectors like `mapping`, `counting`, or `summarizingLong`, you can aggregate within each group without writing a manual merge function. Choose the collector whose business intent is clearest.

## 15. Complete Java 17+ Example: Multi-Update Product Catalog

Problem: a system receives product updates by SKU. A SKU may appear multiple times, and we must produce the **representative record with the highest revision**. If revisions tie, compare update timestamps; if still tied, use the record ID for determinism. Finally, the report must iterate SKUs in **ascending order**.

The code below is a standalone runnable program (Java 17+):

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class DeterministicMapDemo {
    record CatalogRow(
            String rowId,
            String sku,
            String label,
            int revision,
            long updatedAt,
            long priceCents
    ) {}

    private static final Comparator<CatalogRow> PREFERENCE =
            Comparator.comparingInt(CatalogRow::revision)
                    .thenComparingLong(CatalogRow::updatedAt)
                    .thenComparing(CatalogRow::rowId)
                    .thenComparing(CatalogRow::label)
                    .thenComparingLong(CatalogRow::priceCents);

    static Map<String, CatalogRow> createCatalog(
            List<CatalogRow> updates, boolean parallel) {
        var stream = parallel
                ? updates.parallelStream()
                : updates.stream();

        return stream.collect(Collectors.toMap(
                CatalogRow::sku,
                Function.identity(),
                BinaryOperator.maxBy(PREFERENCE),
                TreeMap::new
        ));
    }

    public static void main(String[] args) {
        List<CatalogRow> updates = List.of(
                new CatalogRow("R01", "P02", "Headphones", 1, 100L, 200_000L),
                new CatalogRow("R02", "P01", "Old Notebook", 1, 110L, 30_000L),
                new CatalogRow("R03", "P01", "New Notebook", 2, 120L, 35_000L),
                new CatalogRow("R04", "P03", "Pen", 1, 130L, 8_000L),
                new CatalogRow("R05", "P02", "Headphones Pro", 3, 140L, 250_000L),
                new CatalogRow("R06", "P02", "Headphones Max", 3, 150L, 260_000L)
        );

        Map<String, CatalogRow> sequential = createCatalog(updates, false);
        Map<String, CatalogRow> parallel = createCatalog(updates, true);

        // Map.equals compares contents, not iteration order.
        if (!sequential.equals(parallel)) {
            throw new AssertionError("Sequential/parallel differ in content");
        }

        List<String> sortedKeys = new ArrayList<>(sequential.keySet());
        if (!sortedKeys.equals(List.of("P01", "P02", "P03"))) {
            throw new AssertionError("Incorrect key order");
        }

        if (!sequential.get("P01").rowId().equals("R03")) {
            throw new AssertionError("P01 did not select highest revision");
        }
        if (!sequential.get("P02").rowId().equals("R06")) {
            throw new AssertionError("P02 did not select latest updatedAt");
        }

        sequential.forEach((sku, row) ->
                System.out.printf(
                        "%s | %s | revision=%d | price=%d%n",
                        sku, row.label(), row.revision(), row.priceCents()
                )
        );

        // P01 | New Notebook   | revision=2 | price=35000
        // P02 | Headphones Max | revision=3 | price=260000
        // P03 | Pen            | revision=1 | price=8000
        System.out.println("PASS");
    }
}
```

**Why does this program satisfy the requirements?**

1. `CatalogRow::sku` provides the grouping key; each SKU gets one final value.
2. `BinaryOperator.maxBy(PREFERENCE)` chooses higher revisions, breaks revision ties by timestamp, and continues with deterministic tie-breakers. For the same SKU, if all comparison criteria match, the two records are identical across all remaining fields.
3. `TreeMap::new` orders keys by natural `String` ordering, independent of parallel branch execution order.
4. `CatalogRow` fields are immutable record components; the merge function mutates neither the source nor shared state.
5. The program asserts both **Map contents** and **key ordering** with separate checks, never relying on `HashMap.toString()` ordering.
6. Each call to `createCatalog` opens a fresh Stream over the same stable source list.

**Business note:** in real systems, timestamps can collide, prices can change independently of versions, and IDs may not be the right priority rule. Thus `PREFERENCE` is an **explicit rule stated for this exercise**, not a universal conflict-resolution default.

## 16. Exercises from Beginner to Intermediate

### Exercise 1 — Detecting Duplicate Keys

Given:

```java
record Student(String code, String name) {}
List<Student> students = List.of(
        new Student("S01", "An"),
        new Student("S02", "Bình"),
        new Student("S01", "Chi")
);
```

**Requirement:** try collecting with `toMap(Student::code, Function.identity())`; predict the exception. Then fix it to keep the first record encountered when traversing **sequentially in List order**.

**Solution:**

```java
Map<String, Student> firstStudent = students.stream()
        .collect(Collectors.toMap(
                Student::code,
                java.util.function.Function.identity(),
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(firstStudent.get("S01").name()); // An
System.out.println(new ArrayList<>(firstStudent.keySet()));
// [S01, S02]
```

### Exercise 2 — Summing Quantities and Printing Sorted by Key

Given:

```java
record Item(String sku, long quantity) {}
List<Item> items = List.of(
        new Item("B", 3),
        new Item("A", 4),
        new Item("B", 5),
        new Item("C", 2)
);
```

**Requirement:** build a `Map<String, Long>`, sum quantities on duplicate SKUs, and print in ascending SKU order.

**Solution:**

```java
Map<String, Long> totals = items.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Long::sum,
                TreeMap::new
        ));

totals.forEach((sku, quantity) ->
        System.out.println(sku + "=" + quantity));

// A=4
// B=8
// C=2
```

### Exercise 3 — Picking the Latest Update with a Tie-Breaker

Given:

```java
record Update(String key, long timestamp, String updateId) {}
List<Update> changes = List.of(
        new Update("X", 100L, "U02"),
        new Update("Y", 150L, "U01"),
        new Update("X", 100L, "U03"),
        new Update("X", 200L, "U04")
);
```

**Requirement:** keep the `Update` with the highest timestamp per key. If timestamps tie, use `updateId` ascending to pick the winner. Output in ascending key order.

**Solution:**

```java
Comparator<Update> updatePolicy = Comparator
        .comparingLong(Update::timestamp)
        .thenComparing(Update::updateId);

Map<String, Update> chosen = changes.parallelStream()
        .collect(Collectors.toMap(
                Update::key,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(updatePolicy),
                TreeMap::new
        ));

System.out.println(chosen.get("X").updateId()); // U04
System.out.println(new ArrayList<>(chosen.keySet())); // [X, Y]
```

Try removing line `U04`: then `U03` beats `U02` because both have timestamp 100 and `U03` has a larger ID. That is an explicit tie-breaker independent of thread scheduling.

### Exercise 4 — Keeping All Elements per Group

**Requirement:** using `items` from Exercise 2, build a `Map<String, List<Item>>` sorted by SKU **without discarding duplicate records**.

**Solution:**

```java
Map<String, List<Item>> groupedItems = items.stream()
        .collect(Collectors.groupingBy(
                Item::sku,
                TreeMap::new,
                Collectors.toList()
        ));

System.out.println(groupedItems.get("B").size()); // 2
```

Notice that `groupingBy` solves **keeping all records**, whereas `toMap` with `Long::sum` solves **summing totals**. Choose based on the required output shape, not shortest syntax.

### Exercise 5 — Distinguishing Map Order from Report Line Order

**Requirement:** collect total quantities using default `toMap` (without specifying a `mapFactory`), then build a `List<String>` of `"SKU=quantity"` lines sorted by **quantity descending**, breaking ties by SKU ascending.

**Solution:**

```java
Map<String, Long> totalsWithoutOrder = items.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Long::sum
        ));

List<String> lines = totalsWithoutOrder.entrySet().stream()
        .sorted(
                Map.Entry.<String, Long>comparingByValue(
                        Comparator.reverseOrder()
                ).thenComparing(Map.Entry.comparingByKey())
        )
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(lines); // [B=8, A=4, C=2]
```

The result is determined by the comparator on **entries**, not by the initial Map implementation.

## 17. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `IllegalStateException` in `toMap` | Two elements produce the same key without a merge function | Define a collision policy and use the merge overload, or treat duplicates as a valid error. |
| Values overwritten unexpectedly | Using `(old, next) -> next` without checking version/timestamp | Use a comparator or reducer reflecting business criteria. |
| Key order changes across runs | Relying on default `toMap` or `HashMap` | Choose `LinkedHashMap`, `TreeMap`, or sort entries on export. |
| `LinkedHashMap` still yields unwanted order | Input lacks encounter order or was not pre-sorted as needed | Establish source order or sort before collecting. |
| `TreeMap` drops certain keys | Comparator returns 0 for business-distinct keys | Use a comparator aligned with key identity rules. |
| `Map.equals` PASSES while report order is wrong | Map equality ignores iteration order | Assert `new ArrayList<>(map.keySet())` or exported line list. |
| `NullPointerException` in collector | Mapper returns null value, key invalid for Map type, or null in source | Validate/filter/normalize before collecting. |
| `ConcurrentModificationException` or lost data | `parallelStream().forEach(sharedMap::put)` mutates shared HashMap | Use `Collectors.toMap`/`groupingBy`, never mutate a shared Map. |
| Chosen "latest" record varies across runs | Merge depends on processing order or incomplete tie-breaking | Use a stable comparator with deterministic tie-breakers. |
| `Map.copyOf` alters iteration order | Unmodifiable Map does not mean ordered Map | Snapshot into `TreeMap`/`LinkedHashMap` with an unmodifiable view if needed. |
| Report requires multiple rows but only one remains | Using `toMap` by key instead of grouping into a list | Use `groupingBy` with downstream `toList`. |
| Large totals overflow | `Integer::sum`/`Long::sum` exceeds numeric bounds | Choose appropriate numeric types and guard against overflow. |

## 18. Submission Checklist

1. **Key:** does the key mapper produce keys matching the business definition?
2. **Duplicates:** is the policy to throw, accumulate, or pick a winner stated explicitly?
3. **Merge:** is it associative, free of shared-state mutation, and independent of thread scheduling?
4. **Tie-break:** if two records tie on primary priority, is the selection rule fully deterministic?
5. **Source:** is it an ordered `List` or an unordered `Set`? Does it require sorting for stability?
6. **Map:** do you need insertion order via `LinkedHashMap` or key-sorted order via `TreeMap`?
7. **Output:** must the Map itself be ordered, or only the exported report lines?
8. **Testing:** did you assert both key/value contents and ordering when order is required?
9. **Null:** are there clear policies for null elements, null keys, and null values?
10. **Parallel:** does the code avoid mutating a shared `HashMap` inside `forEach`?
11. **Empty source:** is an empty Map handled properly?
12. **Complexity:** have you accounted for sort, Map, merge, and memory costs at larger scale?

## Key Takeaways

When designing a `Map` from a Stream, **defining duplicate-key resolution** and **defining output order** are two separate decisions. `Collectors.toMap(keyMapper, valueMapper)` throws if multiple elements share a key. Use a merge function to sum, retain one record, or pick a winner via comparator; never pick based on incidental thread execution order.

`LinkedHashMap` preserves **insertion order**, fitting when source order is meaningful and stable. `TreeMap` maintains **sorted key order**, fitting when reports must iterate keys deterministically. If only the presentation layer needs sorting, sort `entrySet().stream().sorted(...)` without changing the lookup Map. For parallel execution, keep lambdas stateless and non-interfering, define complete tie-breakers, and verify results **against the business contract**, not by how a Map happens to print.
