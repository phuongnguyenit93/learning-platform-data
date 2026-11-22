# Creating a Stream from Map Keys, Values, and Entries

## 1. Why Can't We Call `map.stream()` Directly?

In the **Java Stream API**, a pipeline consists of a data source, intermediate operations such as `filter`, `map`, `sorted`, and a terminal operation such as `toList`, `count`, `reduce`, or `collect`. Most intermediate operations run **lazily**: the pipeline only actually traverses the data when the terminal operation is called.

A `Map<K, V>` stores **key → value** mappings, not a single sequence of elements. Therefore, the `Map` interface **does not have** a direct `stream()` method. We must decide which part of the Map we want to traverse:

```text
                         Map<K, V>
                        /    |     \
              keySet()    values()   entrySet()
                  |          |          |
              Set<K>    Collection<V> Set<Map.Entry<K,V>>
                  |          |          |
               stream()   stream()    stream()
                  |          |          |
              Stream<K>  Stream<V> Stream<Map.Entry<K,V>>
```

All three sources are **views backed by the original Map**; they do not automatically create a copy of the data. Which source you choose determines what information each element in the pipeline carries.

After this lesson, you will know how to:

- Create a Stream from `keySet()`, `values()`, and `entrySet()`; choose the right one for your business requirement.
- Filter, transform, sort, sum, and group data retrieved from a Map.
- Convert Stream results into a `List` or a new Map and handle duplicate keys in `Collectors.toMap`.
- Identify issues with traversal order, mutable views, concurrent sources, and performance limits.

The examples use Java 17 or later for `record`, `Map.of`, and `Stream.toList()`. The source operations `keySet()`/`values()`/`entrySet()` together with `stream()` have been available since Java 8.

## 2. Introductory Example: One Map with Three Perspectives

Consider an inventory where keys are product codes and values are stock quantities:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("SACH", 3);
stock.put("BUT", 8);
stock.put("VO", 2);
```

`LinkedHashMap` is used to preserve insertion order in the examples, making the illustrated results have an easy-to-verify order.

| Source | Stream element type | Retrieved elements | Best when |
| --- | --- | --- | --- |
| `stock.keySet().stream()` | `String` | `"SACH"`, `"BUT"`, `"VO"` | Only product codes/keys are needed. |
| `stock.values().stream()` | `Integer` | `3`, `8`, `2` | Only quantities/values are needed. |
| `stock.entrySet().stream()` | `Map.Entry<String, Integer>` | `("SACH", 3)`, … | Both key **and** value are needed. |

In a `Map`, every key is unique. Values, however, **can be duplicated**, so `values()` returns a `Collection<V>` rather than a `Set<V>`. If two products both have a stock of 3 items, `values().stream()` still contains two elements with value 3.

## 3. Stream from `keySet()`: Processing the List of Keys

`keySet()` provides the set of all keys. Each step in the pipeline receives only the key, so this is a clean choice when filtering conditions do not depend on values.

```java
List<String> codes = stock.keySet().stream()
        .filter(code -> code.startsWith("S"))
        .map(String::toLowerCase)
        .toList();

System.out.println(codes); // [sach]
```

A few other cases:

```java
long numberOfShortCodes = stock.keySet().stream()
        .filter(code -> code.length() <= 3)
        .count(); // 2: BUT, VO

List<String> sortedCodes = stock.keySet().stream()
        .sorted()
        .toList(); // [BUT, SACH, VO]
```

**Do you need to access the value?** You can call `stock.get(code)` from a key Stream, but when the processing condition needs both key and value, `entrySet().stream()` usually expresses the intent more clearly and avoids repeated Map lookups:

```java
// Works, but has to look up the value again for each key.
List<String> lowStockCodes = stock.keySet().stream()
        .filter(code -> stock.get(code) < 5)
        .toList();

// Better suited when both key and value are needed.
List<String> lowStockCodesFromEntries = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .map(Map.Entry::getKey)
        .toList();

System.out.println(lowStockCodesFromEntries); // [SACH, VO]
```

Do not assume every Map has the same `get` cost as `HashMap`. Moreover, if another thread is updating the Map, an independent `get` call does not constitute an atomic read tied to the key currently being traversed.

## 4. Stream from `values()`: Analyzing Only Values

`values()` returns the values in the Map. If you do not need to know which key a value belongs to, this source is more direct and readable than `entrySet()`.

```java
int totalStock = stock.values().stream()
        .mapToInt(Integer::intValue)
        .sum();

double averageStock = stock.values().stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0);

long nearlyEmptyProducts = stock.values().stream()
        .filter(quantity -> quantity < 5)
        .count();

System.out.println(totalStock);           // 13
System.out.println(averageStock);         // 4.333333333333333
System.out.println(nearlyEmptyProducts);  // 2
```

`mapToInt` creates an `IntStream` to use `sum`, `average`, `min`, `max`, or `summaryStatistics` without writing an accumulation loop manually. On an empty Map, `average()` returns `OptionalDouble.empty()`; in the example above, `orElse(0.0)` defines the default result.

You can compute value frequency statistics, including duplicate values:

```java
Map<Integer, Long> frequency = stock.values().stream()
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

// With current stock: {2=1, 3=1, 8=1}, display order is not guaranteed.
```

For Maps that allow `null` values, code using `Integer::intValue` will cause a `NullPointerException` upon encountering `null`. `Collectors.groupingBy` also does not accept a `null` grouping key in the usage above. If business logic requires skipping missing values, filter explicitly:

```java
int safeTotal = stock.values().stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
```

The short snippets above use `List`, `Collectors`, `Function`, and `Objects` from the `java.util` and `java.util.stream` packages; a complete example with `import` statements is in section 10.

## 5. Stream from `entrySet()`: Needing Both Key and Value

`entrySet()` returns a set of `Map.Entry<K, V>`. Each entry lets you retrieve `getKey()` and `getValue()` from the same pair.

```java
List<String> warnings = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .map(entry -> entry.getKey() + " has only " + entry.getValue())
        .toList();

System.out.println(warnings);
// [SACH has only 3, VO has only 2]
```

You can combine `filter` and `map` with selecting an object that has the maximum value:

```java
Optional<Map.Entry<String, Integer>> mostStocked = stock.entrySet().stream()
        .max(Map.Entry.comparingByValue());

mostStocked.ifPresent(entry ->
        System.out.println(entry.getKey() + ": " + entry.getValue())
); // BUT: 8
```

`max` returns an `Optional` because the Map might be empty. For equal values, the example above does not specify a key tie-breaking rule; if a deterministic result is needed, add a secondary rule.

### Sorting by Value

The default order of `TreeMap` is based on the **key**. To sort by **value**, use a Stream on `entrySet`:

```java
List<Map.Entry<String, Integer>> smallestFirst = stock.entrySet().stream()
        .sorted(Map.Entry.comparingByValue())
        .toList();

smallestFirst.forEach(entry ->
        System.out.println(entry.getKey() + " -> " + entry.getValue())
);
// VO -> 2
// SACH -> 3
// BUT -> 8
```

To obtain a consistent order even when stock quantities tie, add a secondary comparison by key:

```java
List<Map.Entry<String, Integer>> sorted = stock.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue()
                .thenComparing(Map.Entry.comparingByKey()))
        .toList();
```

Note that `sorted` establishes an **order on the resulting Stream**; it does not re-sort the original Map. Natural comparison requires values to be comparable and non-`null`, or you must supply a comparator with a `null`-handling rule.

## 6. Collecting an Entry Stream into a New Map

A pipeline often ends with `collect` to create another Map: filtering elements, changing values, changing key types, or preserving a sorted order.

Example of creating a Map containing low-stock products:

```java
Map<String, Integer> lowStock = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
        ));

// The key/value pairs are SACH=3 and VO=2.
// The resulting Map from simple toMap does not guarantee order or Map type.
```

If you need to preserve the **order after `sorted`** in the resulting Map, request a `LinkedHashMap` via the four-argument overload of `toMap`:

```java
Map<String, Integer> sortedByQuantity = stock.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue()
                .thenComparing(Map.Entry.comparingByKey()))
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue,
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(sortedByQuantity);
// {VO=2, SACH=3, BUT=8}
```

This overload takes `keyMapper`, `valueMapper`, a merge function for **duplicate keys**, and a Map factory in order. Because entries from the source Map have unique keys and the example does not alter keys, the merge function will not be called, yet it is still required when specifying the Map type.

### Duplicate Keys After Transformation Is an Easy Bug to Miss

The initial Map has distinct keys, but a `map` operation can turn them into the same key:

```java
Map<String, Integer> original = Map.of(
        "VIP", 10,
        "vip", 20
);

// WRONG: two distinct keys both become "vip", toMap throws IllegalStateException.
Map<String, Integer> broken = original.entrySet().stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey().toLowerCase(Locale.ROOT),
                Map.Entry::getValue
        ));
```

If you want to merge numbers instead of rejecting duplicate keys, pass a merge rule:

```java
Map<String, Integer> merged = original.entrySet().stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey().toLowerCase(Locale.ROOT),
                Map.Entry::getValue,
                Integer::sum
        ));

System.out.println(merged); // {vip=30}
```

Do not rely on `(oldValue, newValue) -> oldValue` or overwriting with `newValue` when source order is not guaranteed: which element arrives first may be indeterminate. For real business logic, define an appropriate merge rule (sum numbers, pick the maximum value, or explicitly report duplicates).

`Collectors.toMap` does not accept a `null` resulting value in standard Java implementations. If the source Map has `null` values, filter, replace, or choose a collection method that supports such data as required by the problem.

## 7. Grouping Map Entries by a Value's Property

When each value is an object, `entrySet()` lets you group by an attribute of the object while still keeping the key code.

Suppose the Map holds `Product`:

```java
record Product(String category, int stock) {}

Map<String, Product> products = new LinkedHashMap<>();
products.put("P-01", new Product("Stationery", 3));
products.put("P-02", new Product("Books", 8));
products.put("P-03", new Product("Stationery", 2));
```

Aggregating total stock by category:

```java
Map<String, Integer> stockByCategory = products.values().stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::stock)
        ));

System.out.println(stockByCategory);
// {Stationery=5, Books=8}, group order not guaranteed.
```

Here **only values are needed**, so `values()` suffices. However, if you want to get **product codes by category**, you must use `entrySet()`:

```java
Map<String, List<String>> codesByCategory = products.entrySet().stream()
        .collect(Collectors.groupingBy(
                entry -> entry.getValue().category(),
                Collectors.mapping(
                        Map.Entry::getKey,
                        Collectors.toList()
                )
        ));

// Stationery -> [P-01, P-03]
// Books -> [P-02]
```

This is a way to choose the Stream source based on the information that needs to be retained: once `values().stream()` is used, the pipeline no longer directly knows the key code of each value.

## 8. Map Views Are Backed by the Source: Avoid Modifying the Map While a Stream Runs

`keySet()`, `values()`, and `entrySet()` of ordinary Maps are **backed views**: when the Map changes, the view contents change too. Removing through a view can mutate the original Map. Those collection views must not be treated as snapshots.

Wrong example:

```java
Map<String, Integer> items = new HashMap<>();
items.put("A", 1);
items.put("B", 0);

items.entrySet().stream()
        .filter(entry -> entry.getValue() == 0)
        .forEach(entry -> items.remove(entry.getKey())); // WRONG
```

The pipeline is traversing `items.entrySet()` while removing elements from `items`. With `HashMap`, this behavior can lead to `ConcurrentModificationException`; the exception should not be regarded as the sole error detection mechanism.

Even calling `entry.setValue(...)` can modify the **value in the source Map**, even though it does not change the number of elements:

```java
items.entrySet().stream()
        .forEach(entry -> entry.setValue(entry.getValue() + 1)); // Avoid: modifying source while traversing
```

Not every entry permits `setValue`: an entry from an immutable Map can throw `UnsupportedOperationException`. And for mutable entries, not throwing an exception still does not make that usage a safe Stream pattern.

To filter and remove data, separate into two phases:

```java
List<String> outOfStock = items.entrySet().stream()
        .filter(entry -> entry.getValue() == 0)
        .map(Map.Entry::getKey)
        .toList();

// Terminal operation has finished; now modify the Map.
outOfStock.forEach(items::remove);
```

If you **only** want to remove conditionally, no Stream is needed:

```java
items.entrySet().removeIf(entry -> entry.getValue() == 0);
```

`removeIf` performs an intentional Map update. This approach suits modifiable Maps when no other thread is concurrently accessing them in a way that violates safety. Immutable Maps like `Map.of(...)` do not allow removal operations.

### Laziness and Lifecycle

Like other Stream sources, calling `items.entrySet().stream().filter(...)` only builds the pipeline; the terminal operation triggers traversal. Streams created from Maps with **late-binding** spliterators may reflect changes made before the terminal operation begins. However, not all Maps have the same read-timing guarantees; do not rely on this property if you need a stable snapshot.

To process over a fixed set of key/value pairs, create a copy **before** running the Stream, while the source is stable:

```java
Map<String, Integer> snapshot = new HashMap<>(items);
List<String> names = snapshot.entrySet().stream()
        .filter(entry -> entry.getValue() > 0)
        .map(Map.Entry::getKey)
        .toList();
```

This is a **shallow** copy: value objects may still be shared. Furthermore, creating a copy from a Map currently being modified does not provide an atomic snapshot; if concurrent access exists, synchronize or use an appropriate snapshot mechanism before copying.

## 9. Traversal Order, Concurrent Maps, and Parallel Processing

Do not look at the current order of a Map and assume a Stream always uses that order.

| Map type | Traversal order | Notes when creating a Stream |
| --- | --- | --- |
| `HashMap` | Order not guaranteed | If consistent results are needed, `sorted` by explicit criteria. |
| `LinkedHashMap` | Usually insertion order | Has *access-order* mode; calling `get` can change traversal order. |
| `TreeMap` | By key comparator | To order by value, you still must call `sorted` on entries. |
| `Map.of(...)` | Order not guaranteed | Immutable Map, does not allow add/remove or `null` keys/values. |
| `ConcurrentHashMap` | No fixed order guaranteed | *Weakly consistent* iterator supports concurrent updates, but does not create a snapshot. |

### With `parallelStream()`

You can create a parallel pipeline from a view:

```java
long available = stock.entrySet().parallelStream()
        .filter(entry -> entry.getValue() > 0)
        .count();
```

However, `parallelStream()` **does not turn `HashMap` or `LinkedHashMap` into a collection safe for concurrent modification**. For ordinary mutable Maps, keep the source stable during traversal; lambdas should be *stateless*, not modify the source, and avoid unsynchronized external accumulators.

`ConcurrentHashMap` has traversal supporting concurrent modifications, yet the result when another thread is updating depends on observation timing:

```java
ConcurrentHashMap<String, Integer> live = new ConcurrentHashMap<>();
live.put("A", 1);
live.put("B", 2);

List<String> seen = live.entrySet().parallelStream()
        .filter(entry -> entry.getValue() > 0)
        .map(Map.Entry::getKey)
        .toList();
```

If another thread modifies `live`, the `seen` list does not necessarily reflect the entire Map at a single point in time. Concurrent sources allow traversal to tolerate concurrent updates according to their contract; business consistency requirements must be designed separately.

Regarding performance, `entrySet()` is usually sensible when both key and value are needed because it avoids calling `get` for each key. For small Maps or cheap processing, the thread partitioning, splitting, and combining overhead of `parallelStream()` can outweigh the benefits; measure on real data and requirements. Operations like `sorted`, `distinct`, or grouping can allocate extra intermediate memory.

## 10. Complete Example: Reporting and Processing Inventory

The following program demonstrates all three Stream sources on the same `Map`, then updates the source **after** all Stream computations finish.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class MapStreamsDemo {
    record Product(String category, int quantity, boolean active) {}

    public static void main(String[] args) {
        Map<String, Product> catalog = new LinkedHashMap<>();
        catalog.put("P-01", new Product("Books", 5, true));
        catalog.put("P-02", new Product("Pens", 0, false));
        catalog.put("P-03", new Product("Books", 7, true));
        catalog.put("P-04", new Product("Notebooks", 2, true));

        // keySet: only product codes are used.
        List<String> codes = catalog.keySet().stream()
                .filter(code -> code.startsWith("P-0"))
                .toList();

        // values: sum quantities by Product property.
        int totalQuantity = catalog.values().stream()
                .filter(Product::active)
                .mapToInt(Product::quantity)
                .sum();

        // entrySet: need product code paired with its own quantity.
        List<String> depletedCodes = catalog.entrySet().stream()
                .filter(entry -> entry.getValue().quantity() == 0)
                .map(Map.Entry::getKey)
                .toList();

        Map<String, Integer> quantityByCategory = catalog.values().stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        LinkedHashMap::new,
                        Collectors.summingInt(Product::quantity)
                ));

        System.out.println(codes);              // [P-01, P-02, P-03, P-04]
        System.out.println(totalQuantity);      // 14
        System.out.println(depletedCodes);      // [P-02]
        System.out.println(quantityByCategory); // {Books=12, Pens=0, Notebooks=2}

        // Terminal operations have completed: now modify the source Map.
        depletedCodes.forEach(catalog::remove);
        System.out.println(catalog.keySet());   // [P-01, P-03, P-04]
    }
}
```

Here:

1. `keySet()` is appropriate because filtering is only by product code.
2. `values()` is appropriate because total stock and grouping depend only on `Product` properties.
3. `entrySet()` is appropriate for finding the **codes** of products with zero stock.
4. `Collectors.groupingBy` accumulates into a separate result Map. `LinkedHashMap::new` preserves the group encounter order of this sequential pipeline.
5. Removing out-of-stock codes occurs after the terminal operation, so it does not interfere with the source being processed.

## 11. Common Mistakes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Calling `map.stream()` does not compile | `Map` does not implement `Collection` and has no `stream()` | Choose `keySet()`, `values()`, or `entrySet()`. |
| Used `values()` but then need the key | Stream only has elements of type `V` | Use `entrySet()` from the start. |
| `Collectors.toMap` throws `IllegalStateException` | Transformation produces duplicate keys | Provide a merge function or redefine the key. |
| Resulting Map does not keep order after `sorted` | Default `toMap` does not guarantee Map type | Choose `LinkedHashMap::new` in the four-argument overload. |
| `ConcurrentModificationException` during `forEach` | Pipeline mutates source Map while traversing | Collect results first; update Map afterward, or use a direct mutation API. |
| Results vary between runs | Relying on `HashMap`/`Map.of` order or a source being updated concurrently | Sort explicitly; take a consistent snapshot when needed. |
| `NullPointerException` when summing/sorting | `null` values are not handled | Filter out `null` or provide an explicit rule. |

## 12. Practice Exercise

Given a list of scores by student ID:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("SV01", 8);
scores.put("SV02", 5);
scores.put("SV03", 9);
scores.put("SV04", 5);
```

**Requirements:**

1. Get the list of student IDs starting with `SV0`.
2. Compute the average score using a Stream over **values**.
3. Get the list of IDs with score 8 or higher, sorted by score descending, then by ID ascending on ties.
4. Create a Map `passOrFail` with student IDs and the string `"PASS"` if score is 5 or higher, `"FAIL"` if lower. Do not modify `scores`.

**Suggested solution:**

```java
List<String> studentCodes = scores.keySet().stream()
        .filter(code -> code.startsWith("SV0"))
        .toList();

double average = scores.values().stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0); // 6.75

List<String> highScorers = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 8)
        .sorted(Map.Entry.<String, Integer>comparingByValue(
                Comparator.reverseOrder()
        ).thenComparing(Map.Entry.comparingByKey()))
        .map(Map.Entry::getKey)
        .toList(); // [SV03, SV01]

Map<String, String> passOrFail = scores.entrySet().stream()
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> entry.getValue() >= 5 ? "PASS" : "FAIL",
                (first, second) -> first,
                LinkedHashMap::new
        ));

// {SV01=PASS, SV02=PASS, SV03=PASS, SV04=PASS}
```

The solution additionally uses `Comparator` from `java.util`. When solving similar exercises, ask yourself two questions before writing code: **what information does each Stream element need to carry?** and **should the result be a List, an aggregated number, or a new Map?**

## Key Takeaways

- Use `keySet().stream()` when only keys are needed; use `values().stream()` when only values are needed; use `entrySet().stream()` when **both key and value** are needed.
- The three collection views of an ordinary Map are backed by the original Map. Do not modify the source while a Stream is traversing it.
- `sorted` only orders the Stream elements; if the resulting Map must preserve order, pick an appropriate implementation such as `LinkedHashMap`.
- `Collectors.toMap` needs an explicit policy when **transformed** keys can collide. `groupingBy` and `summingInt` fit summary reports.
- Do not assume `HashMap` ordering, `ConcurrentHashMap` snapshot consistency, or `parallelStream()` performance gains. Base choices on source contracts and business needs.
