# Choosing the Map Type with mapFactory

In the Java Stream API, `Collectors.toMap` and `Collectors.groupingBy` can transform data through a `filter`, `map`, `collect` pipeline into a `Map<K, V>`. Getting the right **keys and values** is not always enough: some problems need to preserve encounter order, some need sorted keys, some use an enum as the key, and some need a `ConcurrentMap` for concurrent accumulation. In such cases, **`mapFactory`** lets you specify the concrete Map type to create.

This lesson belongs to the **Collecting to Maps** chapter of the **JAVA_STREAM_API** module. We will examine how to use `mapFactory` in the overloads of `toMap`, `groupingBy`, and concurrent collectors; practice with `HashMap`, `LinkedHashMap`, `TreeMap`, `EnumMap`, `ConcurrentHashMap`, and `ConcurrentSkipListMap`. At the same time, the lesson clarifies contracts regarding duplicate keys, `null` values, comparators, ordering, accumulation state, laziness, and parallel execution costs.

## 1. Why Do We Need to Choose the Map Type?

Suppose an application needs to convert a list of order records into reports:

- Look up orders by ID, without caring about key iteration order.
- Display order IDs in **first-appearance order**.
- Export a revenue report with region codes **sorted by key**.
- Count orders by an `enum Status`, following the enum's declaration order.
- Collect data from a parallel Stream into a concurrent structure.

All of these have a `Map` result shape, but their **Map type** requirements differ:

| Map Type | Key Characteristic | When to consider |
| --- | --- | --- |
| `HashMap` | No iteration order guaranteed; standard hash lookup | Key lookup without ordering requirements |
| `LinkedHashMap` | Iterates in insertion order by default | Display results that must remember key encounter order |
| `TreeMap` | Keys ordered by comparator or natural ordering | Reports requiring sorted keys |
| `EnumMap<E, V>` | Accepts keys of a single enum only; iterates in enum declaration order | Statistics over a fixed set of statuses |
| `ConcurrentHashMap` | Supports concurrent update operations; no order guaranteed | Concurrent collection with hashed keys |
| `ConcurrentSkipListMap` | `ConcurrentNavigableMap` with ordered keys | Need both concurrency and comparator ordering |

**Choosing a Map does not automatically solve data-grouping logic.** To collect properly, you still need to decide where keys come from, where values come from, how duplicate keys are handled, and whether `null` is permitted.

## 2. What Is `mapFactory`?

In collectors, `mapFactory` is a **`Supplier<M>`**, i.e. a function that creates a **new** Map whenever the collector needs an accumulation container.

Example:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.TreeMap;
import java.util.function.Supplier;

Supplier<HashMap<String, Integer>> hashFactory = HashMap::new;
Supplier<LinkedHashMap<String, Integer>> linkedFactory = LinkedHashMap::new;
Supplier<TreeMap<String, Integer>> treeFactory = TreeMap::new;
```

Do not pass an already-populated Map and reuse the exact same object across all collections:

```java
// Design flaw: every call to the supplier returns the same container.
HashMap<String, Integer> shared = new HashMap<>();
Supplier<HashMap<String, Integer>> unsafeFactory = () -> shared;
```

A collector may create multiple Maps during parallel processing or across independent `collect` calls. A supplier returning the same shared Map easily mixes data and causes concurrency bugs.

Conceptual flow:

```text
List<Order>
    |
    | stream().filter(...): lazy intermediate operation
    v
Stream<Order>
    |
    | collect(toMap(..., mapFactory)): terminal operation
    v
mapFactory.get() ---> new Map ---> add/merge entries ---> result Map
```

## 3. `Collectors.toMap` with `mapFactory`

The primary overload here has the signature:

```java
public static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
)
```

The four parameters serve distinct roles:

| Parameter | Role | Example |
| --- | --- | --- |
| `keyMapper` | Produces key `K` from element `T` | `Order::id` |
| `valueMapper` | Produces value `U` | `Function.identity()` |
| `mergeFunction` | Handles when two elements have duplicate keys under the target Map | `(oldValue, newValue) -> newValue` |
| `mapFactory` | Determines the container type `M` | `LinkedHashMap::new` |

`mergeFunction` is a **required parameter in this overload**, even if the current dataset has unique keys. If you want to use the two-argument overload `toMap(keyMapper, valueMapper)`, you must accept an unspecified Map implementation type and an exception on duplicate keys.

### 3.1. Using `HashMap` for general lookup

```java
import java.util.HashMap;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(String sku, String name) {}

List<Product> products = List.of(
    new Product("P-01", "Desk"),
    new Product("P-02", "Chair")
);

HashMap<String, Product> bySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Function.identity(),
        (first, second) -> second,
        HashMap::new
    ));

System.out.println(bySku.get("P-01").name()); // Desk
```

`HashMap` is appropriate when you only need `get(key)` lookups and **do not rely on iteration order as a contract**. Seeing entries appear sorted in a single run does not mean `HashMap` guarantees order.

### 3.2. Using `LinkedHashMap` to preserve insertion order

Suppose data arrives in the order `P-03`, `P-01`, `P-02` and the UI needs to iterate SKUs in that exact appearance order:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

List<Product> products = List.of(
    new Product("P-03", "Lamp"),
    new Product("P-01", "Desk"),
    new Product("P-02", "Chair")
);

LinkedHashMap<String, String> namesBySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (existing, incoming) -> incoming,
        LinkedHashMap::new
    ));

System.out.println(namesBySku.keySet()); // [P-03, P-01, P-02]
```

`LinkedHashMap` iterates in **key insertion order** by default, rather than sorting by value or key. In a **sequential** pipeline over an ordered `List` like this example, that order reflects the first encounter of each SKU.

On duplicate keys, replacing a value via `Map.merge` does not move the old key to the end in a default `LinkedHashMap`. If the business requires **most-recently-accessed** order, that is a separate `LinkedHashMap` mode (access order) and must be designed explicitly; do not assume `LinkedHashMap::new` provides access order.

### 3.3. Using `TreeMap` to sort by key

```java
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

List<Product> products = List.of(
    new Product("P-03", "Lamp"),
    new Product("P-01", "Desk"),
    new Product("P-02", "Chair")
);

TreeMap<String, String> sorted = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (first, second) -> second,
        TreeMap::new
    ));

System.out.println(sorted.keySet()); // [P-01, P-02, P-03]
```

`TreeMap::new` here uses the natural ordering of `String`. This natural ordering **is not a Vietnamese alphabetical collation rule**. If the domain requires locale-specific comparison or a type without natural ordering, select an appropriate comparator.

Example sorting keys in reverse order:

```java
import java.util.Comparator;

TreeMap<String, String> descending = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (oldValue, newValue) -> newValue,
        () -> new TreeMap<>(Comparator.reverseOrder())
    ));

System.out.println(descending.keySet()); // [P-03, P-02, P-01]
```

With `TreeMap`, the comparator **does not affect only ordering**; it also determines which two keys are considered equivalent via `compare(k1, k2) == 0`. This is a crucial point when handling duplicate keys.

## 4. A `TreeMap` Comparator Can Introduce Duplicate Keys

Consider the two strings `"API"` and `"api"`. `String.equals` treats them as different, but `String.CASE_INSENSITIVE_ORDER` compares them as 0.

```java
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

List<String> tags = List.of("API", "api", "Java");

TreeMap<String, Integer> counts = tags.stream()
    .collect(Collectors.toMap(
        tag -> tag,
        tag -> 1,
        Integer::sum,
        () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(counts.size());       // 2
System.out.println(counts.get("API"));   // 2
System.out.println(counts.get("api"));   // 2
System.out.println(counts.get("Java"));  // 1
```

Even though `"API"` and `"api"` differ under `equals`, this Map treats them as one logical key. `Integer::sum` merges the two values into 2.

This may be intentional (merging keys case-insensitively), or it may be a bug if identifiers must be case-sensitive. A comparator inconsistent with `equals` can also make full adherence to the general `Map` contract subtle when interoperating with other Map types; choose key semantics deliberately and test them.

Do not use a comparator purely for "display formatting" if it could merge keys that must stay separate. If you only want to display entries in a custom order, it is often better to keep the original Map and **sort the entry set when rendering the report**.

## 5. How Does `mergeFunction` Resolve Key Collisions?

Any collector placing multiple elements into a Map needs a strategy when keys repeat.

```java
record Price(String sku, long amountVnd) {}

List<Price> prices = List.of(
    new Price("P-01", 100_000L),
    new Price("P-02", 200_000L),
    new Price("P-01",  50_000L)
);
```

Options:

| Policy | Merge function | Result for `P-01` |
| --- | --- | --- |
| Keep old value in sequential pipeline | `(oldValue, incoming) -> oldValue` | `100000` |
| Keep new value in sequential pipeline | `(oldValue, incoming) -> incoming` | `50000` |
| Sum values | `Long::sum` | `150000` |
| Take maximum | `Long::max` | `100000` |
| Fail if duplicate key | Throw `IllegalStateException` | Collection fails |

Example summing values while preserving first-appearance order of each key:

```java
import java.util.LinkedHashMap;
import java.util.stream.Collectors;

LinkedHashMap<String, Long> totals = prices.stream()
    .collect(Collectors.toMap(
        Price::sku,
        Price::amountVnd,
        Long::sum,
        LinkedHashMap::new
    ));

System.out.println(totals); // {P-01=150000, P-02=200000}
```

If keys must be **unique**, do not silently pick the first or last record. Declare an error-detection policy:

```java
HashMap<String, Price> unique = prices.stream()
    .collect(Collectors.toMap(
        Price::sku,
        java.util.function.Function.identity(),
        (left, right) -> {
            throw new IllegalStateException(
                "Duplicate SKU: " + left.sku()
            );
        },
        HashMap::new
    ));
// Example intentionally throws an exception because P-01 appears twice.
```

**Parallel note:** Merges like `Long::sum` and `Long::max` are associative for the chosen operation and easy to reason about when partitions are combined. A "keep latest by time" policy should compare **actual timestamps or revisions** in the data rather than vaguely relying on when a parallel branch finishes. If records with the same revision must be arbitrated, define an explicit tie-breaker.

A merge function returning `null` can cause the entry to be removed per the `Map.merge` contract; this is usually **not** the desired way to handle duplicate keys and should be avoided unless the business has an explicit deletion rule.

## 6. Choosing a Map for `Collectors.groupingBy`

`groupingBy` typically takes a **classifier** (key-extracting function) and a downstream collector. The overload that lets you select the Map is:

```java
public static <T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

A memorable difference: `groupingBy` **does not take a mergeFunction directly**. It feeds elements with the same key into that group's **downstream collector**. `mapFactory` sits in the **second parameter**, before downstream.

### 6.1. `LinkedHashMap`: grouping in first-seen order

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, String sku, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("South",   "P-01", 100_000L),
    new Sale("North",   "P-02",  50_000L),
    new Sale("South",   "P-03", 150_000L),
    new Sale("Central", "P-04",  70_000L)
);

LinkedHashMap<String, Long> revenueByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(revenueByRegion);
// {South=250000, North=50000, Central=70000}
```

With a `List` source and a sequential pipeline, keys are added in first-encounter order: `South`, `North`, `Central`. Inside each group, `summingLong` sums all revenue. Note that a `long` sum can still overflow if data exceeds the 64-bit integer limit.

### 6.2. `TreeMap`: statistics by sorted keys

```java
import java.util.TreeMap;

TreeMap<String, Long> sortedRevenue = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(sortedRevenue.keySet());
// [Central, North, South] in natural ordering of String.
```

`TreeMap` keeps keys in comparator or natural order, not data-encounter order. When exporting a report with a stable key ordering is required, this is an expressive choice.

### 6.3. `EnumMap`: grouping by enum

When keys belong to a fixed enum, `EnumMap` is a fitting choice and is generally more compact than a general hash-based Map.

```java
import java.util.EnumMap;
import java.util.List;
import java.util.stream.Collectors;

enum Status { CREATED, PAID, CANCELLED }
record Order(String id, Status status) {}

List<Order> orders = List.of(
    new Order("O-01", Status.PAID),
    new Order("O-02", Status.CREATED),
    new Order("O-03", Status.PAID)
);

EnumMap<Status, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::status,
        () -> new EnumMap<>(Status.class),
        Collectors.counting()
    ));

System.out.println(counts);
// {CREATED=1, PAID=2}
```

`EnumMap` iterates in **enum declaration order**, not record encounter order. The `CANCELLED` group has no elements, so it **does not automatically get an entry** in the result.

If a report requires all statuses including zero counts, you can add them explicitly after collecting:

```java
for (Status status : Status.values()) {
    counts.putIfAbsent(status, 0L);
}

System.out.println(counts);
// {CREATED=1, PAID=2, CANCELLED=0}
```

Then every valid enum key is present. If you only care about statuses with data, no extra step is needed.

## 7. `MapFactory` and Concurrent Collectors

When collecting across multiple threads and you genuinely want concurrent accumulation, Java provides separate collectors:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction, mapFactory)
Collectors.groupingByConcurrent(classifier, mapFactory, downstream)
```

Key differences:

- `toMap` and `groupingBy` can be used with a **parallel Stream** by creating intermediate Maps and combining them. Using `HashMap` or `LinkedHashMap` does not mean a single Map is updated concurrently by multiple threads.
- `toConcurrentMap` and `groupingByConcurrent` provide **concurrent, unordered** collectors. When semantically permitted, accumulation can happen concurrently in the same container.
- The `mapFactory` of concurrent collectors must supply a type `M extends ConcurrentMap<K, V>`, not `HashMap` or `LinkedHashMap`.

### 7.1. Using `ConcurrentHashMap`

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

record Payment(String region, long amountVnd) {}

List<Payment> payments = List.of(
    new Payment("South", 100_000L),
    new Payment("North",  50_000L),
    new Payment("South", 200_000L)
);

ConcurrentHashMap<String, Long> totals = payments.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Payment::region,
        Payment::amountVnd,
        Long::sum,
        ConcurrentHashMap::new
    ));

System.out.println(totals.get("South")); // 300000
System.out.println(totals.get("North")); // 50000
```

`ConcurrentHashMap` does not guarantee key iteration order. Addition `Long::sum` is an appropriate merge policy for group totals when the `long` range suffices.

**Do not** use `ConcurrentHashMap` merely to be able to call `parallelStream()`. If the dataset is small or ordering is required, a sequential approach with an appropriate Map can be simpler and faster.

### 7.2. Using `ConcurrentSkipListMap` when both concurrency and sorted keys are needed

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> sortedTotals =
    payments.parallelStream()
        .collect(Collectors.toConcurrentMap(
            Payment::region,
            Payment::amountVnd,
            Long::sum,
            ConcurrentSkipListMap::new
        ));

System.out.println(sortedTotals.keySet()); // [North, South]
```

`ConcurrentSkipListMap` is a `ConcurrentNavigableMap`, so key traversal follows its comparator/natural ordering. However, the collector still has the `UNORDERED` characteristic: **source element encounter order** is not guaranteed like a list. The order of `keySet()` in the example is **sorted key order**, which is a different concept.

### 7.3. `groupingByConcurrent` with mapFactory

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> countsByRegion =
    payments.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            Payment::region,
            ConcurrentSkipListMap::new,
            Collectors.counting()
        ));
```

The resulting `countsByRegion` sorts keys in natural order. `Collectors.counting()` is the downstream collector for the element count per group. Do not infer from the word "Concurrent" that every downstream collector or every accumulation step per value is **lock-free**; implementations may still coordinate to maintain correctness.

## 8. A Complete Java 17 Example with Four Map Choices

The example below compiles and runs standalone; other sections in this lesson are snippets using the types declared in their respective sections.

```java
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapFactoryDemo {

    enum Status { NEW, PAID, REFUNDED }

    record Order(String id, String region, Status status, long amountVnd) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-02", "South",   Status.PAID,     120_000L),
            new Order("O-01", "North",   Status.NEW,       80_000L),
            new Order("O-02", "South",   Status.REFUNDED, 120_000L),
            new Order("O-03", "Central", Status.PAID,     200_000L)
        );

        // 1. Order IDs in first-appearance order; a later record overwrites
        // the old value on duplicate ID in a sequential stream.
        LinkedHashMap<String, Order> byId = orders.stream()
            .collect(Collectors.toMap(
                Order::id,
                Function.identity(),
                (existing, incoming) -> incoming,
                LinkedHashMap::new
            ));

        // 2. Group revenue of PAID orders; region keys are sorted.
        TreeMap<String, Long> paidByRegion = orders.stream()
            .filter(order -> order.status() == Status.PAID)
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                Collectors.summingLong(Order::amountVnd)
            ));

        // 3. Group by enum, iterating in enum declaration order.
        EnumMap<Status, Long> countByStatus = orders.stream()
            .collect(Collectors.groupingBy(
                Order::status,
                () -> new EnumMap<>(Status.class),
                Collectors.counting()
            ));

        // 4. Parallel aggregation into a ConcurrentMap with sorted keys.
        ConcurrentSkipListMap<String, Long> paidParallel =
            orders.parallelStream()
                .filter(order -> order.status() == Status.PAID)
                .collect(Collectors.toConcurrentMap(
                    Order::region,
                    Order::amountVnd,
                    Long::sum,
                    ConcurrentSkipListMap::new
                ));

        System.out.println(byId.keySet());
        System.out.println(byId.get("O-02").status());
        System.out.println(paidByRegion);
        System.out.println(countByStatus);
        System.out.println(paidParallel);
    }
}
```

Expected output:

```text
[O-02, O-01, O-03]
REFUNDED
{Central=200000, South=120000}
{NEW=1, PAID=2, REFUNDED=1}
{Central=200000, South=120000}
```

The four Maps serve different purposes: `LinkedHashMap` preserves key insertion order, `TreeMap` sorts region keys, `EnumMap` orders keys by enum declaration, and `ConcurrentSkipListMap` allows concurrent accumulation with sorted keys. Not every problem needs four collectors; the example simply helps compare the effect of `mapFactory` choices.

## 9. `null`, Duplicate Keys, and Each Map's Contract

### 9.1. `null` is not handled the same way across all collectors

`HashMap` permits one `null` key in the regular Map API; `ConcurrentHashMap` and `ConcurrentSkipListMap` forbid `null` keys and values. `TreeMap` with natural ordering forbids `null` keys. `EnumMap` forbids `null` keys.

Moreover, **collectors have their own contracts**:

- `Collectors.groupingBy` does not accept a classifier returning `null`, even if `mapFactory` returns a `HashMap`. Group labels must be normalized, filtered, or replaced with a meaningful key.
- `Collectors.toMap` should not be used with a `valueMapper` that can return `null`. Overloads with a merge function use `Map.merge`, which rejects a `null` incoming value. To represent "missing value", consider `Optional` or preprocess the data.
- For `Collectors.toConcurrentMap`, `null` keys and values are invalid under the corresponding `ConcurrentMap` contract.

Example normalizing a null group key into a meaningful label:

```java
import java.util.HashMap;
import java.util.stream.Collectors;

record User(String city) {}

List<User> users = List.of(
    new User("Hanoi"), new User(null), new User("Hanoi")
);

HashMap<String, Long> counts = users.stream()
    .collect(Collectors.groupingBy(
        user -> user.city() == null ? "UNKNOWN" : user.city(),
        HashMap::new,
        Collectors.counting()
    ));

System.out.println(counts.get("UNKNOWN")); // 1
```

When using a placeholder value for `null`, choose a key that cannot collide with valid business values. In larger systems, you can use a dedicated key type rather than a fixed sentinel string.

### 9.2. Treat the Comparator as part of the key rule

In `TreeMap`, two keys collide if the comparator returns 0, even when `equals` differs. Therefore you must test **key comparison**, **`mergeFunction`**, and **Map type** together as a single cohesive unit.

### 9.3. Why not use `IdentityHashMap` casually?

`IdentityHashMap` compares keys by **reference (`==`)** rather than `equals`. That contract differs from almost all business key-lookup rules. `mapFactory` is not the place to accidentally change key equality semantics; only use such a structure when the problem truly requires object identity comparison.

## 10. When You Want an Unmodifiable Map

`mapFactory` determines the Map structure **created**, but it does not automatically create an unmodifiable Map.

There are two separate goals:

1. Choose how keys are stored (`LinkedHashMap`, `TreeMap`, `EnumMap`, ...).
2. Specify whether callers receiving the result are allowed to call `put`/`remove`.

To produce an unmodifiable result, you can use `collectingAndThen` with a finishing step:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> stableNames = products.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            Product::sku,
            Product::name,
            (first, second) -> second,
            LinkedHashMap::new
        ),
        collected -> Collections.unmodifiableMap(
            new LinkedHashMap<>(collected)
        )
    ));

// stableNames.put("P-99", "New"); // UnsupportedOperationException
```

The `new LinkedHashMap<>(collected)` copy preserves traversal order and isolates the result from the internal accumulation Map; `Collections.unmodifiableMap` provides an **unmodifiable view** over that copy. If the *values* are mutable objects, wrapping the Map does not make value objects deeply immutable.

`Map.copyOf(map)` creates an unmodifiable result but **does not guarantee the same iteration order as `LinkedHashMap`**. Do not use it if ordering is a required part of the output contract.

`Collectors.toUnmodifiableMap` also produces an unmodifiable Map and has an overload for duplicate keys, but **it has no `mapFactory` parameter**. If you need both comparator-sorted keys and frozen mutability, design an appropriate finishing step.

## 11. Sequential Streams, Parallel Streams, and Ordering Conditions

Distinguish three concepts:

- **Encounter order**: the element order of the Stream source, such as the element order of a `List`.
- **Insertion order**: the order in which a Map records first insertions of **new keys**, as in `LinkedHashMap`.
- **Key order**: key order defined by a comparator or natural ordering, as in `TreeMap`.

These three orders are not equivalent. For codes appearing as `P-03, P-01, P-02`:

```text
List source (encounter)      : P-03 → P-01 → P-02
LinkedHashMap (insertion)    : P-03 → P-01 → P-02
TreeMap (key order)          : P-01 → P-02 → P-03
ConcurrentHashMap            : no guaranteed iteration order
```

A collector whose `mapFactory` returns `LinkedHashMap` does not automatically give every parallel source a meaningful order. If source order is inherently undefined (e.g., data from a `HashSet`), meaningful order cannot be restored merely by changing the Map.

With concurrent collectors that have the `UNORDERED` characteristic, do not use accumulation order to interpret "first element", "last element", or "latest version". If such a condition is needed, define the comparison criterion directly on the values or sort before outputting.

### Why doesn't `parallel()` automatically improve performance?

For non-concurrent `toMap`, merging many intermediate Maps can be expensive when the number of keys is very large. For `toConcurrentMap`, many threads contending on the same keys can also degrade performance. Outcomes depend on key distribution, element count, mapping cost, Map type, and how `Spliterator` splits data.

If speed matters, benchmark with representative data and an appropriate tool such as JMH after verifying correctness. Avoid enabling `parallelStream()` just because a collector has "Concurrent" in its name.

## 12. Choosing `toMap` or `groupingBy`?

| Problem | Usually appropriate collector | Example Map factory |
| --- | --- | --- |
| Each key has one value and keys are unique | `toMap(keyMapper, valueMapper, mergeFunction, factory)` | `HashMap::new` |
| Keys may collide, want to pick/merge **one value** | `toMap(..., mergeFunction, factory)` | `LinkedHashMap::new` |
| Want a `List<T>` per key | `groupingBy(classifier, factory, toList())` | `LinkedHashMap::new` |
| Want count/sum/aggregated value per key | `groupingBy(classifier, factory, counting()/summingLong(...))` | `TreeMap::new` |
| Keys are an enum | `groupingBy(classifier, EnumMap supplier, downstream)` | `() -> new EnumMap<>(Status.class)` |
| Want concurrent updates without encounter order dependency | `toConcurrentMap(...)` or `groupingByConcurrent(...)` | `ConcurrentHashMap::new` |
| Need sorted keys with concurrent support | Concurrent collector with `ConcurrentSkipListMap` | `ConcurrentSkipListMap::new` |

`groupingBy` does not have to produce a list. The downstream collector can be `counting`, `summingLong`, `mapping`, `reducing`, or a custom collector. Selecting `mapFactory` configures the **outer container**, while downstream defines how to compute the **value for each key**.

If there is only one value per key and no need to group multiple elements, `toMap` is usually more direct.

## 13. Notes on Laziness, Resources, and Data

`filter` and `map` are intermediate operations; `collect` is the **terminal operation** that triggers the pipeline.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> data = List.of("a", "bb", "ccc");

var pipeline = data.stream()
    .filter(text -> !text.isBlank()); // Not processed until the terminal operation.

Map<Integer, String> byLength = pipeline.collect(Collectors.toMap(
    String::length,
    text -> text,
    (first, second) -> first,
    HashMap::new
));

// pipeline.count(); // Cannot consume the Stream a second time.
```

A Map usually keeps at least one entry per distinct key, so memory can scale with the **number of unique keys**; with `groupingBy(..., toList())`, memory must also retain the elements of each group.

When the source is tied to I/O, such as `Files.lines(path)`, use `try-with-resources` to close the Stream even when the terminal operation is `collect`. Providing a `mapFactory` does not automatically close the file-reading resource.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Place inside a method declaring throws IOException or handle the exception.
try (Stream<String> lines = Files.lines(Path.of("codes.txt"))) {
    Map<String, Long> frequency = lines
        .filter(line -> !line.isBlank())
        .collect(Collectors.groupingBy(
            line -> line,
            TreeMap::new,
            Collectors.counting()
        ));
    System.out.println(frequency);
}
```

If the data source can mutate while the pipeline runs, establish a consistent read policy; `mapFactory` does not handle concurrent modification of the source. Do not modify the source `List` inside `keyMapper` or `valueMapper`.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Expecting `Collectors.toMap(key, value)` to always return a `HashMap` with a fixed order | No guarantee on type or order | Use the overload with `mapFactory` if a concrete Map type is required |
| Passing `LinkedHashMap::new` as the third argument to `toMap` | Wrong overload: the third argument is the merge function | Pass all four arguments `toMap(key, value, merge, factory)` |
| Passing `mergeFunction` as the second argument to `groupingBy` | Wrong API | Use `groupingBy(classifier, mapFactory, downstream)` |
| Ignoring duplicate keys in `toMap` | May throw `IllegalStateException` or lose data under the wrong policy | Explicitly define `mergeFunction` and test duplicates |
| Choosing a `TreeMap` comparator that treats distinct keys as equal | Two keys merge unexpectedly | Verify comparison rules and key semantics |
| Using `HashMap` and relying on `entrySet()` iteration order | Display order is not guaranteed | Use `LinkedHashMap` or `TreeMap` as intended |
| Using `groupingBy` with a classifier returning `null` | Exception thrown | Normalize or filter keys beforehand |
| Using `toMap` with a `valueMapper` returning `null` | May throw `NullPointerException` | Handle missing data explicitly |
| Using `HashMap::new` as the factory for `toConcurrentMap` | Does not satisfy the `ConcurrentMap` bound | Use `ConcurrentHashMap::new` or `ConcurrentSkipListMap::new` |
| Trying to achieve `CONCURRENT` by sharing a single `HashMap` manually | Race condition, wrong results | Use a properly contracted concurrent collector |
| Using "last value" merge to pick the newest record in an unordered stream | Nondeterministic with respect to business time | Compare timestamps/revisions explicitly |
| Treating `mapFactory` as a way to create an unmodifiable Map | The Map remains mutable | Use a finisher or an unmodifiable copy |
| Assuming `Map.copyOf(LinkedHashMap)` preserves iteration order | Copied Map order is not guaranteed | Use a `LinkedHashMap` copy and an appropriate wrapper |
| Assuming parallel is always faster with `ConcurrentHashMap` | Key contention and overhead may increase | Benchmark on representative data |

## 15. Practice Exercises

### Exercise 1: Product lookup by SKU

Create a list of products with `sku` and `name`; use `toMap` with `HashMap::new` for lookup. Test duplicate SKUs and build a policy that throws an exception. Explain why you should not silently pick one value if SKU must be unique.

### Exercise 2: Preserving display order

Given SKUs `P-04`, `P-02`, `P-01` in a `List`, use `LinkedHashMap::new` and then `TreeMap::new` on the same data. Print `keySet()` and explain the difference between insertion order and key order.

### Exercise 3: Summing amounts by region

Create a `List<Sale>` with multiple orders sharing regions. Compare `toMap(Sale::region, Sale::amountVnd, Long::sum, TreeMap::new)` with `groupingBy(Sale::region, TreeMap::new, summingLong(Sale::amountVnd))`. How do the two approaches differ?

### Exercise 4: Enum keys

Create an enum `Level { LOW, MEDIUM, HIGH }` and a list of alerts. Use `EnumMap` with `groupingBy` to count alerts per level. Why does a level with no alerts not appear automatically in the Map, and how can you add it with value 0?

### Exercise 5: Comparator and duplicate keys

Merge `["API", "api", "Java"]` into a `TreeMap` using `String.CASE_INSENSITIVE_ORDER`. Try `Integer::sum` and a throwing merge function. Explain why `"API"` and `"api"` are duplicate keys under this Map.

### Exercise 6: Concurrent collection

With one million payment records belonging to only a few regions, compare `toMap(..., HashMap::new)`, `toConcurrentMap(..., ConcurrentHashMap::new)`, and `toConcurrentMap(..., ConcurrentSkipListMap::new)`. Predict the impact of many records hitting the same key; measure before concluding.

### Exercise 7: Unmodifiable yet ordered report

From a `List<Product>`, collect into a `LinkedHashMap` and use `collectingAndThen` to produce an ordered copy wrapped in an unmodifiable view. Try `put` and verify `keySet()` order after collecting.

## 16. Self-Check Knowledge Questions

- What functional interface does `mapFactory` accept, and what does it create?
- Why does `toMap` require **four arguments** when specifying `mapFactory`?
- Where is `mapFactory` positioned in the `groupingBy` overload?
- How do `LinkedHashMap` and `TreeMap` differ in iteration order?
- How does a `TreeMap`'s Comparator relate to determining whether two keys are duplicates?
- When is `EnumMap` better suited than a general-purpose Map?
- What Map type must the factory used in `toConcurrentMap` return?
- Do concurrent collectors guarantee preserving source encounter order?
- Why is `Map.copyOf` a poor choice if insertion order must be preserved?
- When should you use `groupingBy` instead of `toMap`?
- Why does merely changing `mapFactory` not fix `null`, duplicate-key, or numeric overflow errors?
- Which costs should be measured when comparing sequential and parallel processing?

**Takeaway:** `mapFactory` is how you specify the **Map created by a collector**. Choose `HashMap` for simple lookup, `LinkedHashMap` for insertion order, `TreeMap` for sorted keys, `EnumMap` for enum keys, and `ConcurrentMap` for concurrent-accumulation collectors. Always design policies for **duplicate keys, comparators, `null`, ordering, and parallel correctness** together before optimizing performance.
