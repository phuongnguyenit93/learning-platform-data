# `Collectors.groupingBy()` by a Single Attribute in Java

## 1. Problem and Learning Objectives

Suppose an application has a list of products, where each product contains a name, a category, and a price. We need to gather products of the **same category** together—for example, books in the `Books` group, food items in `Food`, and devices in `Gadgets`.

With Streams, the direct solution is `Collectors.groupingBy(classifier)`:

```java
Map<String, List<Product>> byCategory = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

Reading from left to right:

1. `products.stream()` creates a stream of `Product` elements.
2. `Product::category` is the **classifier**, i.e., the function that determines the group key for each element.
3. `Collectors.groupingBy(...)` creates a collector responsible for grouping elements with the same key.
4. `collect(...)` is the **terminal operation**, executing the pipeline and producing the resulting `Map`.
5. Each key in the `Map` is a category; the corresponding value defaults to a `List<Product>` containing the products assigned to that group.

Unlike `filter`, which keeps only a subset, `groupingBy` **classifies all** elements into groups (as long as the classifier returns a valid key). Each element is placed under a key determined by the classifier; elements whose keys are equal according to `equals` belong to the same group.

After this lesson, you will know how to choose a grouping attribute, read the `Map<K,List<T>>` type accurately, use the overloads and downstream collectors, handle empty data or null keys, guarantee ordering when needed, and test results instead of relying on the arbitrary print order of a `HashMap`.

## 2. Mechanism: The Classifier Determines Each Group's Key

Consider the following data:

| Name | Category | Price |
| --- | --- | ---: |
| Java | Books | 120 |
| Mouse | Gadgets | 80 |
| Tea | Food | 40 |
| Algorithms | Books | 200 |
| Keyboard | Gadgets | 150 |
| Coffee | Food | 60 |
| Spring | Books | 180 |

When the classifier is `Product::category`, the logical result is:

```text
Stream<Product>
  Java       → Books  ┐
  Mouse      → Gadgets├→ Map<Category, List<Product>>
  Tea        → Food   │
  Algorithms → Books  │
  Keyboard   → Gadgets│
  Coffee     → Food   │
  Spring     → Books  ┘

Books   → [Java, Algorithms, Spring]
Food    → [Tea, Coffee]
Gadgets → [Mouse, Keyboard]
```

This is a logical representation by group; it does not guarantee that the `Map` keys will be iterated and printed in the order `Books`, `Food`, `Gadgets` if you only use the default `groupingBy(classifier)` overload. If you want a **deterministic key order**, you can pass `TreeMap::new` as the map factory, as shown in a later section.

### Classifier Types

Suppose we declare:

```java
record Product(String name, String category, int price) {}
```

`Product::category` can be used as a `Function<Product, String>`:

```java
Function<Product, String> classifier = Product::category;
```

- `T = Product`: the type of the Stream elements.
- `K = String`: the key type returned by the classifier.
- The default value for each key is a `List<Product>`.

For `Stream<Employee>`, the classifier can be `Employee::department`, `Employee::city`, or a lambda that computes a key based on business rules. The core requirement is: **all elements in the same group must produce equal keys according to the `Map`'s comparison logic**. For `String`, `"Books"` and `"books"` are two distinct keys. If you want case-insensitive grouping, normalize the key before grouping.

## 3. Important Overloads of `groupingBy`

In `java.util.stream.Collectors`, there are three commonly used overloads:

```java
// 1. Group by classifier; values are List<T>.
groupingBy(classifier)

// 2. Group by classifier, then aggregate each group separately.
groupingBy(classifier, downstream)

// 3. Group and choose a specific Map, with a downstream collector.
groupingBy(classifier, mapFactory, downstream)
```

General type meaning:

| Call | Typical return type | Purpose |
| --- | --- | --- |
| `groupingBy(Product::category)` | `Map<String, List<Product>>` | Group full records by category |
| `groupingBy(Product::category, counting())` | `Map<String, Long>` | Count the number of records in each group |
| `groupingBy(Product::category, mapping(Product::name, toList()))` | `Map<String, List<String>>` | Keep only names in each group |
| `groupingBy(Product::category, summingInt(Product::price))` | `Map<String, Integer>` | Sum a numeric attribute in each group |
| `groupingBy(Product::category, TreeMap::new, toList())` | `TreeMap<String, List<Product>>` or `Map<String,List<Product>>` depending on variable declaration | Use a map with sorted keys |

`downstream` is a `Collector` applied **within each group**, not a `map` operation applied to the entire Stream before grouping. Compare:

```java
// Keep the original Product in each group:
products.stream()
        .collect(Collectors.groupingBy(Product::category));

// Keep only the name in each group:
products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(Product::name, Collectors.toList())));
```

In the second example, the classifier is still called on the **original Product**, and only then does the downstream collector transform each Product in the group into its name.

## 4. Complete Java 17+ Example

Create the file `GroupingByAttributeDemo.java`. The program uses fixed data, avoiding dependencies on system time, `HashMap` iteration order, or external libraries outside the JDK. It demonstrates grouping into a `List`, transforming values per group, counting, summing, averaging, and handling empty categories.

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class GroupingByAttributeDemo {
    record Product(String name, String category, int price) {}

    static List<Product> sample() {
        return List.of(
                new Product("Java", "Books", 120),
                new Product("Mouse", "Gadgets", 80),
                new Product("Tea", "Food", 40),
                new Product("Algorithms", "Books", 200),
                new Product("Keyboard", "Gadgets", 150),
                new Product("Coffee", "Food", 60),
                new Product("Spring", "Books", 180));
    }

    static Map<String, List<Product>> groupProducts(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.toList()));
    }

    static Map<String, List<String>> groupNames(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.mapping(
                                Product::name, Collectors.toList())));
    }

    static Map<String, Long> countByCategory(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.counting()));
    }

    static Map<String, Integer> totalPrices(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.summingInt(Product::price)));
    }

    static Map<String, Double> averagePrices(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.averagingInt(Product::price)));
    }

    static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Product> products = sample();
        Map<String, List<String>> names = groupNames(products);

        check(List.of("Java", "Algorithms", "Spring"),
                names.get("Books"), "book names");
        check(List.of("Tea", "Coffee"),
                names.get("Food"), "food names");
        check(List.of("Mouse", "Keyboard"),
                names.get("Gadgets"), "gadget names");

        check(Map.of("Books", 3L, "Food", 2L, "Gadgets", 2L),
                countByCategory(products), "category counts");
        check(Map.of("Books", 500, "Food", 100, "Gadgets", 230),
                totalPrices(products), "category price totals");

        check(true, Math.abs(
                averagePrices(products).get("Books") - 500.0 / 3)
                < 1e-9, "books average");

        check(7, products.size(), "source list unchanged");
        check(Map.of(), groupProducts(List.of()), "empty input");

        // Map a null key to an explicit label.
        List<Product> unknown = List.of(
                new Product("Mystery", null, 10));
        Map<String, Long> normalized = unknown.stream()
                .collect(Collectors.groupingBy(
                        p -> p.category() == null
                                ? "UNKNOWN" : p.category(),
                        Collectors.counting()));
        check(Map.of("UNKNOWN", 1L),
                normalized, "unknown category");

        // A classifier returning null directly is rejected by groupingBy.
        boolean nullKeyRejected = false;
        try {
            unknown.stream()
                    .collect(Collectors.groupingBy(
                            Product::category));
        } catch (NullPointerException expected) {
            nullKeyRejected = true;
        }
        check(true, nullKeyRejected, "null classifier key");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<Product> products = sample();
        Map<String, List<String>> names = groupNames(products);

        for (Map.Entry<String, List<String>> entry
                : names.entrySet()) {
            System.out.println(entry.getKey()
                    + "=" + entry.getValue());
        }

        System.out.println("counts=" + countByCategory(products));
        System.out.println("totals=" + totalPrices(products));
        System.out.println("booksAverage="
                + String.format(Locale.ROOT, "%.1f",
                        averagePrices(products).get("Books")));

        List<Product> unknown = List.of(
                new Product("Mystery", null, 10));
        long unknownCount = unknown.stream()
                .collect(Collectors.groupingBy(
                        p -> p.category() == null
                                ? "UNKNOWN" : p.category(),
                        Collectors.counting()))
                .get("UNKNOWN");
        System.out.println("unknown=" + unknownCount);

        boolean nullKeyRejected = false;
        try {
            Stream.of(new Product("Mystery", null, 10))
                    .collect(Collectors.groupingBy(
                            Product::category));
        } catch (NullPointerException expected) {
            nullKeyRejected = true;
        }
        System.out.println("nullKeyRejected=" + nullKeyRejected);
    }
}
```

Run with JDK 17 or newer:

```bash
javac GroupingByAttributeDemo.java
java GroupingByAttributeDemo
```

Expected stdout, in exact order:

```text
tests=PASS
Books=[Java, Algorithms, Spring]
Food=[Tea, Coffee]
Gadgets=[Mouse, Keyboard]
counts={Books=3, Food=2, Gadgets=2}
totals={Books=500, Food=100, Gadgets=230}
booksAverage=166.7
unknown=1
nullKeyRejected=true
```

### Why Is the Output Order Deterministic?

In the example, we pass `TreeMap::new` to the three-parameter overload. `TreeMap<String,...>` uses the natural ordering of `String`, so the keys appear in the order `Books`, `Food`, `Gadgets` when iterating `entrySet()` and printing the map. Within each group, `Collectors.toList()` preserves the encounter order of the ordered Stream in the sequential pipeline above, so the names appear in input order within each category.

However, the default `Collectors.groupingBy` **does not guarantee a specific `Map` type**, nor does it guarantee any key order. Do not use a `HashMap` printout that happens to look "right" as a test. If your problem requires order **by first appearance**, you can choose `LinkedHashMap::new`; if you want keys sorted, use `TreeMap::new`.

### What Is Being Verified?

`runTests()` verifies the number of products per group, the order of names in each group, price totals, the average of the Books group, that the input source is unchanged, an empty Stream, and the `null` key handling policy. The `check` method throws `AssertionError` on any mismatch; `-ea` does not need to be enabled.

The average for the Books group is `(120 + 200 + 180) / 3 = 500 / 3`, which is approximately `166.666...`. `String.format(Locale.ROOT, "%.1f", ...)` rounds it to `166.7` and keeps the decimal point consistent regardless of locale. `Collectors.averagingInt` returns `Double`, not `Integer`.

## 5. `mapping`: Collecting Only the Needed Attribute of Each Group

From `Map<String, List<Product>>`, sometimes the presentation layer only needs the names, not the prices or full records. `Collectors.mapping` is the right downstream collector:

```java
Map<String, List<String>> namesByCategory =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.mapping(
                                Product::name,
                                Collectors.toList())));
```

Meaning:

- `Product::category` determines the **group**.
- `Product::name` determines the **value placed into the group**.
- `Collectors.toList()` collects the names in the same group into a list.

Compared to calling `products.stream().map(Product::name)` first and then grouping, using a downstream collector keeps the `Product` object intact at the moment the classifier determines the category. If you convert to `String` too early, you can lose the `category` field and no longer have the data needed to group.

If you want a **set of unique names**, replace `toList()` with `toSet()`:

```java
Map<String, java.util.Set<String>> uniqueNames =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.mapping(
                                Product::name,
                                Collectors.toSet())));
```

`toSet()` does not guarantee element iteration order; any requirement for ordering or a comparator must be expressed through an appropriate collector, such as `toCollection(TreeSet::new)` if the type has a natural order or a suitable comparator.

## 6. `counting`, `summingInt`, `averagingInt`, and Other Downstream Collectors

Grouping by an attribute does not mean the result has to be a `List<T>`. `groupingBy` can use many downstream collectors to produce different kinds of aggregations.

### Counting Elements in Each Group

```java
Map<String, Long> counts = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.counting()));
```

The values have type `Long`, not `Integer`, because `Collectors.counting()` produces a `Long` result.

### Summing a Numeric Attribute

```java
Map<String, Integer> priceTotals = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::price)));
```

In the example, the sum of the `price` attribute per group is Books=500, Food=100, Gadgets=230. Note that using `summingInt` can overflow an integer if the data is large enough; choose `summingLong` or an appropriate arithmetic policy when needed.

### Averaging a Numeric Attribute

```java
Map<String, Double> averages = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.averagingInt(Product::price)));
```

Each group has a `Double` as its average value. Using floating-point averages may require a dedicated precision/rounding policy in monetary domains. Do not use `double` as an exact representation of money when strict financial accuracy is required.

### Computing Multiple Statistics per Group

When you need both count and sum in **a single grouping pass**, you can use `Collectors.summarizingInt(...)`:

```java
Map<String, java.util.IntSummaryStatistics> statistics =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.summarizingInt(Product::price)));
```

Each `IntSummaryStatistics` provides `getCount()`, `getSum()`, `getMin()`, `getMax()`, and `getAverage()`. The result of `getSum()` is `long`, though you still need to consider type limits and the meaning of addition in real-world processing.

**The choice depends on the business output**: if you need a list of products, use `toList`; if you need an aggregate report, collect statistics directly and avoid holding a large list just to count it afterward.

## 7. Choosing the Right `Map` and Understanding Ordering

The simple overload:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

does not guarantee that the result is a `HashMap`, `TreeMap`, `LinkedHashMap`, or any specific implementation. The API does not specify key order. If the application needs to rely on ordering, make it **explicit**:

### Lexicographically Ordered Keys

```java
Map<String, List<Product>> alphabetical = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                java.util.TreeMap::new,
                Collectors.toList()));
```

`TreeMap` requires keys to be comparable or a comparator to be provided; `String` has a natural order.

### Preserving First-Seen Key Order

```java
Map<String, List<Product>> firstSeen = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                java.util.LinkedHashMap::new,
                Collectors.toList()));
```

With a sequential Stream that has an encounter order and a consistent classifier, `LinkedHashMap` reflects the order in which keys are added to the map. If parallelism is enabled or an unordered source is used, you should not assume that key insertion order matches the original order in all cases. If ordering is a strict contract, test the actual source and collector configuration or sort explicitly in a final step.

### Mutability of the Map and Lists

The `groupingBy` collector does not guarantee a specific `Map` type, mutability, serializability, or thread-safety of the resulting `Map`/`List` across all overloads. If you want an unmodifiable result, you can choose data structures and create copies according to your contract policy, for example:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));

Map<String, List<Product>> snapshot = grouped.entrySet().stream()
        .collect(Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())));
```

This snippet is illustrative and requires `Product`, `products`, `Map`, `List`, and `Collectors` to be declared/imported accordingly. `Map` and `List` instances created by `copyOf`/`toUnmodifiableMap` reject `null` elements/keys by contract. If you also need to preserve key order, `toUnmodifiableMap` does not promise iteration order; you must choose a different design with the appropriate ordering and immutability policy.

## 8. Handling `null` Keys, Case Differences, and Multi-Form Keys

### `groupingBy` Rejects Classifiers That Return `null`

A common mistake:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

If there is a `Product` with `category() == null`, `Collectors.groupingBy` throws a `NullPointerException` when the classifier returns a `null` key. This is true even if another `Map` implementation might allow null keys: **this collector requires non-null grouping keys**.

Handling options depending on the contract:

- If category is required, validate early and throw an error with clear context.
- If category may be missing and must be grouped together, use a fallback label such as `"UNKNOWN"`.
- If you need to distinguish a category literally named `"UNKNOWN"` from an unspecified category, use a **dedicated key type** (a record or enum representing the state) instead of arbitrarily conflating both cases into one string.

Example using a fallback label:

```java
Map<String, Long> counts = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.category() == null
                        ? "UNKNOWN" : p.category(),
                Collectors.counting()));
```

This is an intentional **data policy** choice; do not use `filter(Objects::nonNull)` to silently drop entire products if the real problem requires reporting errors or products without a category.

### Normalizing Keys Before Grouping

If the data contains `"Books"`, `"books"`, and `" BOOKS "`, the default classifier treats them as distinct keys. You can normalize them:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.category().strip()
                        .toLowerCase(java.util.Locale.ROOT)));
```

The snippet above assumes `category()` is non-null; when data may be null, handle it according to your contract before calling `strip()`. `Locale.ROOT` avoids depending on the machine's default locale. Normalization can be useful for category codes, though it is not always appropriate for display strings, proper nouns, or different languages.

### Distinguishing Keys from Group Values

A classifier is a function `T -> K`. If you want to group by a computed attribute such as a price bracket, you can also use a classifier that produces labels:

```java
Map<String, List<Product>> byPriceLevel = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.price() >= 150 ? "HIGH" : "STANDARD"));
```

This is still grouping **by a derived attribute**. Do not confuse this with `partitioningBy(Predicate)`, which always produces two `Boolean` keys `true` and `false` (even when one side has no elements, the corresponding downstream value is provided). `groupingBy` only creates keys that actually appear in the input data; on an empty Stream, the result is an empty Map.

## 9. `groupingBy` vs. `toMap`, `partitioningBy`, and `groupingByConcurrent`

| Tool | Best suited when | Difference |
| --- | --- | --- |
| `groupingBy(classifier)` | Multiple elements share a key and need to be grouped | Creates groups; does not treat duplicate keys as an error |
| `toMap(keyMapper, valueMapper)` | Each key expects a single value, or there is an explicit merge strategy | Duplicate keys throw `IllegalStateException` without a merge function |
| `partitioningBy(predicate)` | Exactly two true/false groups | `Boolean`-keyed Map; both groups are always present |
| `groupingByConcurrent(classifier)` | Concurrent grouping for specific needs | Produces a concurrent map; ordering and downstream characteristics differ from sequential grouping |

Using `groupingByConcurrent` does not automatically make every computation faster; you must evaluate the data, source, classifier/downstream cost, key contention, and ordering requirements. It is a **concurrent** and **unordered** collector; it is not suitable if the application requires preserving the exact encounter order of the list within each group.

Grouping operations typically hold intermediate data/state per key. With millions of elements or one very large category, `groupingBy(..., toList())` can consume significant memory. If you only need counts or sums, use `counting`/`summingInt` downstream and avoid retaining every element in each group.

## 10. Testing for Correct Behavior

Some important invariants and test cases:

| Scenario | What to verify |
| --- | --- |
| Empty list | `groupingBy` returns an empty `Map`, with no phantom keys |
| Single category | Exactly one key, and its list contains all elements |
| Interleaved categories | Correct grouping with no lost elements |
| Equal keys | Elements with the same category end up in the same group |
| Case differences | Normalized or distinguished according to the documented rule |
| `null` keys | Validated or mapped to a fallback label/key type; no silent failure |
| Key order | When needed, choose `TreeMap`/`LinkedHashMap` with a clear reason |
| Element order per group | Test encounter order when guaranteed by the source and collector |
| Aggregate downstream | Verify both result types (`Long`, `Integer`, `Double`) and values |
| Input data | No unintended mutation |

For the example in section 4, you can check this invariant:

```java
long totalGrouped = groupProducts(sample()).values().stream()
        .mapToLong(List::size)
        .sum();

// totalGrouped == sample().size() == 7
```

This check is appropriate when no invalid element/key causes grouping to fail and every element is assigned to exactly one group. Checking only the total count is not enough: two products placed in the wrong groups still sum to 7; you must also verify the keys and group members as in `runTests()`.

### Extension: Type-Safe Grouping with Invariant Tests

To avoid ambiguity from user-entered category strings, you can replace `String category` with an `enum Category` and define behavior for unrecognized labels at the parsing layer. `groupingBy(Product::category)` then returns `Map<Category, List<Product>>` with the exact same mechanism. When categories truly form a closed set of values, `EnumMap` can be an appropriate map factory; declare the supplier with the proper type and ensure there are no null keys.

## 11. Common Mistakes

**Mistake 1 — thinking `groupingBy` returns a single `List`.** The default result is `Map<K, List<T>>`. Access a group via `grouped.get(key)`; when a key does not exist, `Map.get()` typically returns `null`, not an empty list. You can use `getOrDefault(key, List.of())` to avoid null when reading.

**Mistake 2 — assuming key order on the default Map.** Output that happens to look fine in one environment does not establish an ordering contract. Choose a map factory or sort when order matters.

**Mistake 3 — classifier returning null.** `groupingBy` does not accept null keys. Validation/normalization must happen before grouping; `TreeMap` also disallows null keys under natural ordering.

**Mistake 4 — treating keys as distinct solely due to casing/whitespace.** `"Books"` and `"books"` are different; normalize intentionally, and test Unicode/locale behavior if data is multilingual.

**Mistake 5 — placing `mapping` in the wrong position.** If you call `map(Product::name)` before determining the category, you no longer have the category on the source element. Downstream `mapping` lets you group on `Product` first, and then keep only the name.

**Mistake 6 — guessing downstream result types.** `counting()` returns `Long`; `averagingInt()` returns `Double`. Do not mistakenly assign `Map<String,Integer>` for `counting()` or perform unsafe casts.

**Mistake 7 — using `toMap` for non-unique keys.** `toMap(Product::category, Product::name)` fails by default when two products share a category. `groupingBy` is designed for repeated keys; if you need a single value per key, you must design a merge rule.

**Mistake 8 — using `parallelStream` and mutating shared external state.** Avoid side effects on a shared `HashMap`/`ArrayList` inside a lambda. Collectors already have an accumulation/combination mechanism; use the standard collector API and verify ordering/concurrency requirements.

**Mistake 9 — forgetting memory cost.** `groupingBy(..., toList())` retains elements in per-group lists. For large datasets where only statistics are needed, choose an appropriate downstream aggregation or a batched processing architecture.

**Mistake 10 — confusing the result Map with the source data.** `collect` creates a new result structure; it does not remove or modify products in the source `List`. If `Product` is a mutable object and you mutate it later, the grouped lists still reference the same object; use immutable records or snapshots if data isolation is required.

## 12. Practice Exercises

1. Using the sample `List<Product>`, call `groupingBy(Product::category)` and verify all three keys are present and the total number of grouped elements is 7. Avoid comparing Map print order.
2. Use `groupingBy(Product::category, counting())` to find the number of products per group. Why is the value type `Long`?
3. Use the downstream collector `mapping(Product::name, toSet())` to get unique names. Explain the effect on element ordering.
4. Use `groupingBy(Product::category, summingInt(Product::price))` to compute price totals, verifying Books=500, Food=100, Gadgets=230.
5. Modify the data to include `"Books"`, `"books"`, and `" Books "`. Design a classifier that normalizes them to a single key and write a test.
6. Add a `Product` with `category=null`. Write a test verifying the failure of `groupingBy(Product::category)`, then update the classifier to place it in `"UNKNOWN"` or an explicit key type.
7. Given an empty Stream, compare the results of `groupingBy` and `partitioningBy` by number of keys.
8. Try `TreeMap::new` and `LinkedHashMap::new` in the three-parameter overload, and explain the difference between key-name order and first-seen key order.
9. Group products into a Map by price label `HIGH`/`STANDARD`. Compare this with `partitioningBy(p -> p.price() >= 150)`.
10. Choose the downstream collector `summarizingInt(Product::price)` and retrieve the count, sum, min/max price, and average in each group; verify the logic against the sample data table.

## 13. Summary

`Collectors.groupingBy()` classifies `Stream<T>` elements according to a **classifier `T → K`**:

- The simple overload produces `Map<K,List<T>>`, where each key represents a group.
- The overload with a downstream collector produces `Map<K,D>`, such as counts, sums, averages, or lists of transformed attributes.
- The overload with a map factory lets you choose `TreeMap`, `LinkedHashMap`, or another suitable `Map` implementation when a specific ordering policy is needed.
- The classifier must return **non-null** keys. To handle missing categories or formatting differences, design explicit validation and normalization.
- Do not rely on default Map ordering or use `toMap` when keys can repeat. Test grouping, membership, result types, and count invariants.

By choosing the right classifier, downstream collector, and Map type, you can turn a stream of records into groups that are easy to look up, aggregate, and display without writing manual loops to manage lists per key.
