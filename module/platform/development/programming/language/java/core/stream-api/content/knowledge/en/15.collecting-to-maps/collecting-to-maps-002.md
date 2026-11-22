# Handling Duplicate Keys with a Merge Function

When converting a `Stream<T>` into a `Map<K,V>`, each element does not always produce a unique key. A transaction list may contain multiple transactions for the same customer, log lines may share the same error code, or input data from multiple sources may contain the same product code. In such cases, the important question is not only **what key to use**, but also **how two values with the same key must be combined**.

This lesson belongs to the **Collecting to Maps** chapter of the `JAVA_STREAM_API` module. You will learn how to use `Collectors.toMap` with a `mergeFunction`, choosing between keeping the first value, keeping the later value, accumulating totals, selecting a record by criteria, or throwing an error; while also examining contracts for state, associativity under parallel processing, `null`, key ordering, and performance costs. This topic continues the lazy pipeline mindset of `filter`, `map`, `collect`, and scenarios where `groupingBy` or `toConcurrentMap` must be chosen.

> The `Collectors.toMap` and `Collectors.toConcurrentMap` variants presented here have existed since **Java 8**. The examples mainly use `Arrays.asList` and `Collectors` so they can be applied directly to Java 8 projects.

## 1. Why Are Duplicate Keys a Problem?

Suppose we have quantity lines by product code:

```text
("P01", 3)
("P02", 5)
("P01", 7)
```

If each line becomes an entry in a Map, we encounter two values for the same key `"P01"`. However, a Map stores only **one value per key at a time**.

Depending on the business domain, the correct result could be:

- `P01 → 3`: keep the first record;
- `P01 → 7`: keep the later record;
- `P01 → 10`: sum the quantities;
- `P01 → [3, 7]`: keep all values, in which case `groupingBy` is usually more suitable;
- Throw an error: the key `P01` appeared repeatedly unexpectedly.

There is no single default strategy that is right for every problem. **The duplicate-key handling rule is part of the business requirement** and should be explicitly expressed in code rather than relying on an accidental Map outcome.

## 2. Two-Argument toMap: Suitable Only When Keys Do Not Collide

The common method:

```java
Collectors.toMap(keyMapper, valueMapper)
```

Here `keyMapper` extracts the key from an element, and `valueMapper` extracts the value. For example, each product name string is unique:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Integer> lengths = Arrays.asList(
        "Java", "Stream", "API"
).stream().collect(
        Collectors.toMap(
                Function.identity(),
                String::length
        )
);

System.out.println(lengths.get("Stream")); // 6
```

However, when `keyMapper` produces duplicate keys, the two-argument overload **throws `IllegalStateException`**, rather than automatically picking the first or last value:

```java
// Running this throws IllegalStateException because "java" appears twice.
Map<String, Integer> invalid = Arrays.asList(
        "java", "JAVA"
).stream().collect(
        Collectors.toMap(
                word -> word.toLowerCase(java.util.Locale.ROOT),
                String::length
        )
);
```

The typical collision condition in `HashMap` relies on `equals` and `hashCode` of the key, but **how two keys are determined to be equivalent also depends on the Map implementation used**. For instance, `TreeMap` considers two keys equivalent if its comparator returns 0. Therefore, the key normalization rule and the Map supplier are two factors to consider together.

If duplicate keys represent a data error, the two-argument overload is a useful choice: it helps detect violations instead of silently losing data.

## 3. Three-Argument toMap: Specifying a mergeFunction

Syntax for resolving duplicate keys:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction
)
```

At the type level, `mergeFunction` is a `BinaryOperator<U>`: it takes **two values of the same type U** for the same key and returns **one value U** after merging.

```text
                Element T
                    |
           +--------+--------+
           |                 |
     keyMapper(T)      valueMapper(T)
           |                 |
         key K            value U
           |                 |
           +--------+--------+
                    |
                Map<K,U>
                    |
         if K already has a value
                    |
        mergeFunction(oldU, newU)
                    |
               merged U
```

Example counting occurrences of each word without placing words into an intermediate list:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Long> counts = Arrays.asList(
        "java", "stream", "java", "api", "stream", "java"
).stream().collect(
        Collectors.toMap(
                Function.identity(), // key: the current word
                word -> 1L,          // each occurrence has value 1
                Long::sum            // sum on duplicate keys
        )
);

System.out.println(counts.get("java"));   // 3
System.out.println(counts.get("stream")); // 2
System.out.println(counts.get("api"));    // 1
```

Each time `"java"` is encountered, the Map must hold one aggregated value; `Long::sum` combines the existing value with the new one. When running in parallel, the two values passed to merge can be **two aggregated results from two branches**, not necessarily one side being the direct value of a single source element.

This is a crucial detail: the merge function must be able to combine **partial results**, rather than being valid only when one input is the "latest data row".

## 4. Three Common Collision-Handling Policies

Let's use data with uppercase/lowercase differences:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> users = Arrays.asList(
        "Alice@EXAMPLE.COM",
        "bob@example.com",
        "alice@example.com"
);
```

### 4.1. Keeping the first value

```java
Map<String, String> firstByEmail = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> existing
        ));

System.out.println(firstByEmail.get("alice@example.com"));
// Alice@EXAMPLE.COM
```

`(existing, incoming) -> existing` retains the existing value when processing sequentially. In this example, the **sequential** pipeline reads a `List` with an encounter order, so the first record for the normalized key is kept.

### 4.2. Keeping the later value

```java
Map<String, String> lastByEmail = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> incoming
        ));

System.out.println(lastByEmail.get("alice@example.com"));
// alice@example.com
```

`(existing, incoming) -> incoming` replaces the old value with the new one. This can be a valid rule if the list is already **sorted in ascending chronological order** and a later record must overwrite an earlier one.

**Do not assume "existing is the earliest record" or "incoming is the latest record" when the source is unordered or uses a concurrent collector**. If record timestamps truly matter, compare the timestamp field explicitly; doing so makes the logic less dependent on traversal order.

### 4.3. Throwing an error with a business message

```java
Map<String, String> strict = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> {
                    throw new IllegalArgumentException(
                            "Duplicate email: " + existing + " / " + incoming
                    );
                }
        ));
```

The code above **intentionally throws an exception** because the list contains duplicate keys. Use this approach when a key appearing multiple times indicates an input error that must halt processing.

If only the default error is needed, `toMap(keyMapper, valueMapper)` is enough. A custom exception-throwing function is useful when you need an error message with context about the two conflicting values.

## 5. Accumulating Values with mergeFunction

A common business example is summing quantities or revenue by key. Create a simple immutable class compatible with Java 8:

```java
import java.math.BigDecimal;

final class Payment {
    private final String customerId;
    private final BigDecimal amount;

    Payment(String customerId, String amount) {
        this.customerId = customerId;
        this.amount = new BigDecimal(amount);
    }

    String customerId() {
        return customerId;
    }

    BigDecimal amount() {
        return amount;
    }
}
```

Collect revenue by customer:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Payment> payments = Arrays.asList(
        new Payment("C01", "12.50"),
        new Payment("C02", "8.00"),
        new Payment("C01", "7.25")
);

Map<String, BigDecimal> revenue = payments.stream()
        .collect(Collectors.toMap(
                Payment::customerId,
                Payment::amount,
                BigDecimal::add
        ));

System.out.println(revenue.get("C01")); // 19.75
System.out.println(revenue.get("C02")); // 8.00
```

Here, `BigDecimal::add` creates a **new BigDecimal value** without mutating the old object. Additive merging satisfies the business requirement and works with both single values and partial sums.

A variant that counts quantities by code with `Integer::sum` is also possible, but watch out for **numeric overflow**. With large datasets, `long` values have a wider range than `int`; when the sum may exceed `long`, another policy such as `BigInteger` or overflow detection is required.

### Why not use (a, b) -> a - b?

```java
// Do not use this approach to aggregate per-key results that may run in parallel:
(existing, incoming) -> existing - incoming
```

Subtraction is **not associative**: `(10 - 3) - 2` differs from `10 - (3 - 2)`. With a parallel stream, branches can be merged in different groupings, making the result depend on the execution plan. Also avoid a `mergeFunction` with side effects on external variables unless there is a clear synchronization model and business intent; normally, design a pure function that does not depend on external state.

## 6. Selecting the Preferred Record by Rule, Not Position

If duplicate keys are a valid scenario yet we need to keep the record based on **update time**, put that criterion into `mergeFunction`. Below is a simple event class:

```java
import java.time.Instant;

final class ProductUpdate {
    private final String productId;
    private final Instant updatedAt;
    private final String revisionId;

    ProductUpdate(String productId, String time, String revisionId) {
        this.productId = productId;
        this.updatedAt = Instant.parse(time);
        this.revisionId = revisionId;
    }

    String productId() { return productId; }
    Instant updatedAt() { return updatedAt; }
    String revisionId() { return revisionId; }
}
```

Select the latest record, using `revisionId` as a secondary key to break ties when timestamps match:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

Comparator<ProductUpdate> priority = Comparator
        .comparing(ProductUpdate::updatedAt)
        .thenComparing(ProductUpdate::revisionId);

BinaryOperator<ProductUpdate> chooseLatest =
        BinaryOperator.maxBy(priority);

Map<String, ProductUpdate> latest = Arrays.asList(
        new ProductUpdate("P01", "2026-01-01T00:00:00Z", "a"),
        new ProductUpdate("P01", "2026-01-02T00:00:00Z", "b"),
        new ProductUpdate("P02", "2026-01-01T00:00:00Z", "c")
).stream().collect(
        Collectors.toMap(
                ProductUpdate::productId,
                Function.identity(),
                chooseLatest
        )
);

System.out.println(latest.get("P01").revisionId()); // b
```

`maxBy` always picks the higher-priority result, regardless of whether that event came earlier or later in the source. If the comparator does not establish a **unique** priority order across distinct records, tie-breaking can still depend on merge order. When the result must be completely deterministic, add a stable, unique secondary key or define an explicit tie-breaking policy.

**Difference from keeping the last record:** a source may not be sorted chronologically, especially when combining multiple files or parallel queries. A rule based on data attributes is usually much more reliable than assuming arrival order.

## 7. Four-Argument toMap: Choosing the Map Implementation

In addition to `keyMapper`, `valueMapper`, and `mergeFunction`, you can pass a `mapFactory`:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction,
        mapFactory
)
```

This supplier determines **which Map type is created for accumulation**. For example, needing a Map with key insertion order to print a report in first-seen order within a sequential pipeline:

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Integer> quantities = Arrays.asList(
        "P02:2", "P01:3", "P02:5", "P03:1"
).stream().collect(
        Collectors.toMap(
                row -> row.substring(0, row.indexOf(':')),
                row -> Integer.parseInt(
                        row.substring(row.indexOf(':') + 1)
                ),
                Integer::sum,
                LinkedHashMap::new
        )
);

System.out.println(quantities); // {P02=7, P01=3, P03=1}
```

`LinkedHashMap` preserves key insertion order by default. In an ordered sequential source, key `P02` appears first, followed by `P01` and `P03`; updating `P02` does not move this key to the end in default insertion-order mode.

Some other options:

| Factory | Characteristic to watch | When to use |
| --- | --- | --- |
| `HashMap::new` | No iteration order guarantee | Only key–value mapping is needed |
| `LinkedHashMap::new` | Key insertion order | Need output in encounter order of a sequential pipeline |
| `TreeMap::new` | Sorted by natural order of keys | Need to iterate keys in sorted order |
| `() -> new TreeMap<>(comparator)` | Comparator defines both order and key equivalence | Need custom key comparison/normalization rules |

With `TreeMap`, **two keys for which the comparator returns 0 are treated as the same key** even if their `equals` methods disagree. The merge policy must account for this behavior, such as when using `String.CASE_INSENSITIVE_ORDER`.

Do not assume by default that `Collectors.toMap(...)` returns a `HashMap` or has a fixed iteration order: the API makes no guarantees about the Map class, mutability, serializability, or thread-safety of the result when no factory is specified.

## 8. Parallel Execution: mergeFunction Must Be Associative

With `parallelStream()`, elements can be split into multiple chunks. Each chunk builds an intermediate Map, and then the framework combines the Maps. Therefore `mergeFunction` may receive:

- Two values originating from two different elements within the same branch;
- Or **two already-aggregated values** from two intermediate Maps.

For the result to remain semantically stable regardless of how elements are grouped, the merge operation should be **associative**:

```text
merge(merge(a, b), c) = merge(a, merge(b, c))
```

Rules like `Long::sum`, `BigDecimal::add`, or picking the maximum via a stable comparator are good examples. For `double`, floating-point addition has rounding errors so results across different groupings may differ slightly; consider precision requirements.

`(first, second) -> first` and `(first, second) -> second` are mathematically associative selection operations, but **not commutative**. They pick based on relative position during combination, so they are unsuitable if the business logic requires "chronologically first" when the Stream has lost encounter order.

```java
Map<String, Long> parallelCounts = Arrays.asList(
        "A", "B", "A", "A", "B"
).parallelStream().collect(
        Collectors.toMap(
                Function.identity(),
                key -> 1L,
                Long::sum
        )
);

System.out.println(parallelCounts.get("A")); // 3
System.out.println(parallelCounts.get("B")); // 2
```

This snippet is order-independent because counting total occurrences is an appropriate merge operation. However, **parallel is not automatically faster**: combining Maps incurs overhead for creating containers, iterating keys to merge, hashing, and scheduling work. When the source is small or there are too many distinct keys, coordination cost can outweigh the benefit.

Another note: standard `toMap` **is not a concurrent collector**. That does not mean it cannot run on a parallel stream. Java can still accumulate into separate Maps and combine them via the combiner; do not mutate a shared `HashMap` from `forEach` as a substitute.

## 9. How Does toConcurrentMap Differ?

When the business logic does not need encounter order and key collection can benefit from concurrent updates, `Collectors.toConcurrentMap` provides similar overloads:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction)
```

Example:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "warn", "info", "warn", "error"
).parallelStream().collect(
        Collectors.toConcurrentMap(
                Function.identity(),
                code -> 1L,
                Long::sum
        )
);

System.out.println(counts.get("warn")); // 2
```

`toConcurrentMap` is a **concurrent, unordered collector**: it allows accumulation using a concurrent strategy and does not guarantee preserving element encounter order in the result. This suits counting/summing, but does not suit keeping the "first-seen record" via `(a,b) -> a` if that order carries business meaning.

For more advanced needs, there is an overload taking an additional `mapFactory` for a suitable `ConcurrentMap`, while still requiring adherence to the `mergeFunction` contract and not assuming it is always faster than `toMap`. `ConcurrentMap` protects the Map operations defined as concurrent; it does not automatically make mutable objects stored inside the Map safe to modify across multiple threads.

## 10. Null Values and Merge Returning Null: Two Different Cases

`null` often causes subtle bugs when collecting into Maps. Distinguish between:

1. **`valueMapper` returning `null`:** many standard collection mechanisms, including `toMap`, do not accept `null` values and can throw `NullPointerException`. Do not rely on a specific implementation permitting null values.
2. **`mergeFunction` returning `null`:** under `Map.merge` semantics, `null` means **removing the mapping for the colliding key**, not "storing a null value in the Map". This is a deletion policy, not a value-selection policy.
3. **`keyMapper` returning `null`:** acceptance depends on the Map type and Collector; notably, `ConcurrentHashMap` rejects null keys. For portability across implementations, normalize or filter out keyless records before collecting.

Example illustrating when a merge function returns null:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, String> cancelled = Arrays.asList(
        "A", "B", "A"
).stream().collect(
        Collectors.toMap(
                Function.identity(),
                Function.identity(),
                (previous, incoming) -> null
        )
);

System.out.println(cancelled.containsKey("A")); // false
System.out.println(cancelled.get("B"));          // B
```

When two `"A"` records collide on the key, the merge function returns null, so the mapping for `A` is removed from the accumulating Map. If another `"A"` appears later, the key can be **re-added**; hence this behavior is **not** a reliable way to "remove all keys occurring more than once", especially under parallel splitting.

**Recommendation:** avoid returning `null` in `mergeFunction` as a data-cleaning trick. If you need to detect duplicate keys or exclude all keys occurring more than once, count frequencies first and filter by count, or use a collector whose intermediate state represents enough information.

Example clearly excluding keys that appear more than once:

```java
Map<String, Long> frequencies = Arrays.asList(
        "A", "B", "A", "C"
).stream().collect(
        Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        )
);

Map<String, Long> onlyUnique = frequencies.entrySet().stream()
        .filter(entry -> entry.getValue() == 1L)
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
        ));

System.out.println(onlyUnique.containsKey("A")); // false
System.out.println(onlyUnique.get("B"));          // 1
```

## 11. When to Use groupingBy Instead of toMap?

If **each key needs to retain multiple elements**, `groupingBy` is usually much more natural than `toMap` with a `mergeFunction` manually managing mutable lists.

| Requirement | Appropriate API | Reason |
| --- | --- | --- |
| One value per key; keys must be unique | `toMap(keyMapper, valueMapper)` | Duplicate keys fail loudly |
| Keep first or last value per key by clear rule | `toMap(..., (a,b) -> a/b)` | Explicit conflict resolution |
| Sum quantity/amount per key | `toMap(..., Long::sum)` or `groupingBy(..., summingLong(...))` | No need to keep a list |
| Keep all records per key | `groupingBy(classifier)` | Produces `Map<K,List<T>>` |
| Need count, average, min/max per key | `groupingBy(..., downstreamCollector)` | Built-in statistical collectors available |
| Need concurrent collection without ordering | `toConcurrentMap` / `groupingByConcurrent` | Supports concurrent accumulation by contract |

Example grouping all orders by customer ID:

```java
Map<String, List<Payment>> byCustomer = payments.stream()
        .collect(Collectors.groupingBy(Payment::customerId));

System.out.println(byCustomer.get("C01").size()); // 2
```

Using `toMap` just to create a new `List` per element and then concatenate lists makes code complex and prone to mutable-state mistakes, especially in parallel. `groupingBy` performs this exact task directly.

If only **total amount** per customer is needed, `groupingBy` can also use downstream `Collectors.reducing`:

```java
Map<String, BigDecimal> totals = payments.stream()
        .collect(Collectors.groupingBy(
                Payment::customerId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Payment::amount,
                        BigDecimal::add
                )
        ));

System.out.println(totals.get("C01")); // 19.75
```

Compared to `toMap(Payment::customerId, Payment::amount, BigDecimal::add)`, this looks slightly more verbose for a simple addition, but the downstream structure shines when statistical summaries or composite collectors are needed.

## 12. Rules for Choosing a Reliable mergeFunction

Before writing a merge function, determine:

1. **How are keys normalized?** Are whitespace trimmed, case folded, or composite keys used? Improper normalization can erroneously merge distinct records.
2. **Are duplicate keys an error or permitted?** If an error, use the two-argument overload or throw an explicit exception.
3. **What should the result for a key represent?** One prioritized record, a sum, or a list? The answer decides `toMap` vs. `groupingBy`.
4. **Is the merge operation associative and side-effect-free?** Especially critical if the pipeline runs in parallel.
5. **Does the rule depend on input order?** If so, verify encounter order and consider selecting by an attribute such as a timestamp.
6. **Can `null` occur?** Define the handling policy before `collect`; do not use null implicitly as a default value.
7. **Is Map iteration order required?** If so, choose an appropriate factory and source; do not infer order from a default `Map`.
8. **What are the data size and key-collision ratio?** A Map may hold many keys in memory; parallel/concurrent execution has different overhead profiles.

### Common Mistakes Table

| Anti-pattern or assumption | Risk | Fix |
| --- | --- | --- |
| `toMap(key, value)` on data with duplicate keys | `IllegalStateException` | Add an appropriate `mergeFunction` |
| `(a,b) -> b` when the chronologically latest value is needed | "Later" in merging may not mean latest timestamp | Compare `updatedAt` directly |
| `(a,b) -> a-b` when running in parallel | Not associative | Use a merge operation with a valid contract |
| `valueMapper` returns null | May throw `NullPointerException` | Filter, normalize, or represent absent values |
| Returning null from merge to permanently delete duplicates | Key can reappear later | Count frequencies then filter by count |
| Assuming default Map type or order | Not guaranteed by JDK | Pass `mapFactory` when actually needed |
| Mutating an external `HashMap` via `parallelStream().forEach` | State contention / race condition | Use `collect` with an appropriate Collector |
| `toConcurrentMap` to keep the "first occurrence" | Unordered collector | Pick a policy based on a priority key |
| Merging mutable `List`s with a custom `mergeFunction` | Error-prone / hard to manage state in parallel | Use `groupingBy` |
| Assuming enabling parallel is always faster | Creating/merging Maps and thread coordination have overhead | Benchmark on real data |

## 13. Combined Example: Revenue by Product Code and Filtering Invalid Records

Suppose sales transactions have a product code and quantity. Requirement: sum quantity per code, but exclude rows with non-positive quantity. We can collect directly into a Map:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

final class Sale {
    private final String productId;
    private final long quantity;

    Sale(String productId, long quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }

    String productId() { return productId; }
    long quantity() { return quantity; }
}

List<Sale> sales = Arrays.asList(
        new Sale("P01", 3),
        new Sale("P02", 2),
        new Sale("P01", 4),
        new Sale("P03", -1),
        new Sale("P02", 5)
);

Map<String, Long> sold = sales.stream()
        .filter(sale -> sale.quantity() > 0)
        .collect(Collectors.toMap(
                Sale::productId,
                Sale::quantity,
                Long::sum
        ));

System.out.println(sold.get("P01"));             // 7
System.out.println(sold.get("P02"));             // 7
System.out.println(sold.containsKey("P03"));     // false
```

Here:

- `filter` makes explicit the policy of **excluding non-positive quantities** before aggregation;
- `keyMapper` groups by product code;
- `valueMapper` extracts the quantity of each transaction;
- `Long::sum` correctly merges both individual values and branch partial sums;
- `collect` is the terminal operation, triggering the pipeline and returning the Map.

If the business needs to **record how many transactions were rejected** for auditing, simply using `filter` as above loses that information; add an error-handling path or a reporting Collector. If `long` might overflow, consider `Math.addExact` to detect overflow, or use `BigInteger` according to arithmetic requirements.

## 14. Self-Check Questions

1. What happens when `toMap(keyMapper, valueMapper)` encounters two elements with the same key? **`IllegalStateException`**, because no conflict-resolution strategy was specified.
2. What does the third parameter of `toMap` take? **Two values of type U** with the same key and returns **one U** after merging.
3. What does `(existing, incoming) -> existing` mean when sequentially traversing an ordered `List`? **Keep the previously stored value** for that key.
4. Why should `(a,b) -> b` not be used to pick the latest event if the data has no chronological order? **Because** merge position does not reflect the timestamp.
5. For counting quantities per key in parallel, why is `Long::sum` better than subtraction? **Because** addition is associative within the appropriate integer domain.
6. Does two-argument `toMap` return a `LinkedHashMap` by default? **No**, the Map type is not guaranteed.
7. How do you create a Map preserving key insertion order for a sequential pipeline? **Use the four-argument overload with `LinkedHashMap::new`**.
8. If `mergeFunction` returns `null` under `Map.merge`, what happens? **The mapping for the colliding key is removed**.
9. If each key must retain multiple records, should you choose `groupingBy` or manually merge `List`s in `toMap`? **Usually choose `groupingBy`**.
10. Does `toConcurrentMap` guarantee preserving first-seen source order? **No**, it is a concurrent, unordered collector.
11. By what criterion does `TreeMap` consider two keys duplicates? **The comparator returns 0** (or natural ordering when there is no comparator).
12. To pick one record by priority independent of encounter order, what should you do? **Use a comparator with a stable secondary key and a `mergeFunction` that selects the higher-priority record**.

**Guiding principle:** When collecting into a Map, decide **what duplicate keys mean before writing `collect`**. Use `toMap` without a `mergeFunction` to catch invalid collisions; use a pure, associative `mergeFunction` to accumulate or select values by an explicit rule; use `groupingBy` when multiple elements must be kept per group. Do not confuse merge order with business time, and only use concurrent or parallel collection after verifying correctness and performance.
