# Counting, Summing, and Finding Representative Elements by Group with Java Stream

A very common requirement when processing data is to **split records into groups by a key**, and then compute a result for each group: how many records there are, what the total value is, and which record represents the group. The Java Stream API solves this using `Collectors.groupingBy(...)` combined with **downstream collectors** such as `counting()`, `summingInt()`, `summingLong()`, `maxBy()`, `minBy()`, and `teeing()`.

Example order data with ID, department, quantity, and amount:

~~~java
record Order(String id, String department, int quantity, long cents, boolean paid) {}
~~~

We can count the number of orders by department with:

~~~java
Map<String, Long> countByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.counting()));
~~~

This is an **illustrative snippet**; it requires `List<Order> orders`, `Map`, and `Collectors` in the appropriate context. Without a Map factory provided, **you must not rely on the iteration order of keys** in the resulting Map. In the full runnable example below, we use `TreeMap::new` to print groups in key order so that the output can be verified accurately.

## 1. Two-tier thinking: classifier and downstream collector

Read the expression:

~~~java
orders.stream().collect(
    Collectors.groupingBy(
        Order::department,
        Collectors.counting()
    )
);
~~~

as two decisions:

1. **Classifier `Order::department`**: which element belongs to which group? From `Order`, it returns a `String` key.
2. **Downstream `Collectors.counting()`**: what value will each group be collected into? Here it is a `Long` holding the number of elements.

Model:

~~~text
Stream<Order>
   |
   | classifier: Order::department
   v
books: [order A, order C, order E] ---> counting() ---> 3L
games: [order B, order D, order G] ---> counting() ---> 3L
toys : [order F]                 ---> counting() ---> 1L
   |
   v
Map<String, Long>
~~~

`groupingBy(classifier, downstream)` is a **collector**. The `stream.collect(...)` call itself is the terminal operation that consumes the Stream. The resulting Map contains keys as groups and values as downstream results. Distinguish this from:

~~~java
Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::department));
~~~

When omitting the downstream, `groupingBy(classifier)` has the same effect as using the `toList()` downstream: the result is a list of records per group. If you only need a count or sum, do not automatically collect the entire list and compute afterwards; a dedicated downstream usually expresses the requirement more clearly and avoids holding a list of every element.

## 2. `Collectors.counting()`: counting records in each group

Syntax:

~~~java
Map<String, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.counting()));
~~~

`counting()` has result type `Long`; do not declare `Map<String, Integer>`. It counts the **number of records** passed to the downstream, not the number of groups, and does not automatically deduplicate elements.

If the same department has three orders, the Map contains that department key with value `3L`. The total number of groups is `counts.size()`, which differs from the total number of orders `counts.values().stream().mapToLong(Long::longValue).sum()`.

Comparison:

| Purpose | Operation | Meaning |
| --- | --- | --- |
| Count all records in the entire Stream | `orders.stream().count()` | A single `long` value |
| Count records per group | `groupingBy(key, counting())` | `Map<K, Long>` |
| Count groups with at least one element | `counts.size()` | Number of keys in the Map |
| Count records matching a condition within a group | `groupingBy(key, filtering(p, counting()))` | Original groups are kept, count can be 0 |
| Count distinct elements by a sub-key | `groupingBy(key, mapping(subKey, toSet()))` then check size | Must specify equality rules for the sub-key |

### `counting()` and empty input

With `Stream.empty()`, `groupingBy(..., counting())` produces an empty Map: **there are no groups to receive a value of 0**. Once a group exists from the classifier, the counting downstream counts the elements of that group.

If business logic requires every expected group to appear even when there are no records, you must add the expected keys using separate logic or use a data structure that manages a fixed set of groups. `groupingBy` does not automatically create groups with no elements.

## 3. `summingInt()`, `summingLong()`, `summingDouble()`: summing by group

If records have numeric properties, use the appropriate downstream collector:

~~~java
Map<String, Integer> quantityByDept = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.summingInt(Order::quantity)));

Map<String, Long> centsByDept = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.summingLong(Order::cents)));
~~~

In the first case, `Order::quantity` returns `int`; `summingInt` extracts an integer quantity for each record, adds them, and returns `Integer`. In the second case, `Order::cents` returns `long`, so `summingLong` adds them and returns `Long`.

Both avoid intermediate operations like `Stream<Integer>` or `Stream<Long>` just to compute a sum. There is no need to write:

~~~java
// Heavier data structure if only a sum is needed:
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(Order::department));
// Then iterate over each List to compute the sum.
~~~

Use the `summing...` downstream if the final goal is a sum per group. Still, choosing the numeric type must be accurate for the business domain.

| Collector | Extractor function | Map value | Things to note |
| --- | --- | --- | --- |
| `summingInt` | `ToIntFunction<T>` | `Integer` | Sum may overflow `int` |
| `summingLong` | `ToLongFunction<T>` | `Long` | Sum may still overflow `long` |
| `summingDouble` | `ToDoubleFunction<T>` | `Double` | Floating-point precision errors, `NaN`, infinity |

### Avoiding overflow by widening before adding

Suppose `quantity` is `int` but the accumulated quantity may exceed `Integer.MAX_VALUE`:

~~~java
Map<String, Long> longQuantities = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.summingLong(o -> (long) o.quantity())));
~~~

Casting to `long` **before** addition keeps the sum within the `long` range. Do not sum with `summingInt` and then convert `Integer` to `Long`, because overflow has already occurred during addition.

For currency, the example chooses `long cents` to avoid binary floating-point errors of `double`. If the value range exceeds `long` or requires complex rounding rules, `BigDecimal` with a valid reduction may be more appropriate; do not convert money to `double` just because `summingDouble` exists.

## 4. `maxBy()` and `minBy()`: finding a representative element for each group

"Representative element" must be clearly defined: **largest by revenue? smallest by quantity? latest by time?** `maxBy` and `minBy` accept a `Comparator` to select the extreme element.

~~~java
Comparator<Order> byCents = Comparator.comparingLong(Order::cents);

Map<String, Optional<Order>> maxByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.maxBy(byCents)));

Map<String, Optional<Order>> minByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.minBy(byCents)));
~~~

The result of `maxBy` and `minBy` is **`Optional<Order>`**, because extreme-value collectors have a contract to handle empty input. Therefore the Map has type `Map<String, Optional<Order>>`, not `Map<String, Order>`.

With standard `groupingBy`, a key can only be created from at least one element actually passing through the classifier, so the corresponding group is normally non-empty. However, **keeping Optional is the public contract of the downstream collector**; do not bypass it with casts.

### When there are tied elements

If the comparator only compares amounts, two orders with equal amounts are considered tied. Which order becomes the representative should not be an unstated business assumption, especially when running in parallel.

Add an explicit secondary criterion:

~~~java
Comparator<Order> byCentsThenId = Comparator
        .comparingLong(Order::cents)
        .thenComparing(Order::id);
~~~

`maxBy(byCentsThenId)` selects the order with the largest `cents`; if tied, it selects the largest `id` in natural string order. `minBy` using the same comparator selects the smallest amount, and if tied, selects the smallest `id`.

Only use `thenComparing` if the secondary criterion is truly business-accurate; do not use an ascending ID by default as a stand-in for "latest order" if the ID does not represent time.

### Finding the record or just the maximum number?

- Need the **maximum value**: you can use `maxBy(Comparator.comparingLong(...))` and read the field, or `mapping(Order::cents, maxBy(Long::compare))`.
- Need the **record containing multiple properties**: the `maxBy(comparator)` downstream directly retains the `Order`, which is more suitable.
- Need **all tied records**: `maxBy` only returns one element; you must design a different rule (find the extreme value then filter records with the same level, or a collector that accumulates a list of tied items).

Do not confuse `maxBy` with `Stream.max`: `stream.max(comparator)` is a **terminal operation on the entire stream**, whereas `Collectors.maxBy(comparator)` is a **downstream collector** used inside `groupingBy`.

## 5. `Collectors.filtering()`: conditional counting while keeping groups

There are two approaches that are very easy to confuse:

~~~java
// Group only paid orders:
Map<String, Long> onlyPaidGroups = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::department, Collectors.counting()));

// Group all first, then count only paid orders:
Map<String, Long> paidCountPerExistingGroup = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.filtering(Order::paid, Collectors.counting())));
~~~

**Core difference:** the first approach removes records before the classifier groups them. A department with no paid orders will **not appear**. The second approach still creates keys for every department encountered from the source, and then the downstream filter only forwards matching orders to counting; a group with no paid orders can still receive a **value of `0L`**.

Example where the source has group `toys` with one unpaid order:

~~~text
Filtering before groupingBy:
{books=2, games=3}         // toys disappears

groupingBy + filtering:
{books=2, games=3, toys=0} // toys is still present
~~~

To print results in a fixed order in practice, use the overload with `TreeMap::new` as in the full program in section 9. If using the default Map, do not infer order when calling `toString()`.

This also illustrates why a downstream operation can produce an empty/0 value even when the group has source elements. `filtering` (Java 9+) is suitable for collecting conditional statistics **on the set of keys already formed**.

## 6. `mapping()` and nested collectors when you need different keys/values

`Collectors.mapping(mapper, downstream)` transforms **each element in a group**, then passes the transformed value to the downstream. It is useful when aggregated data is based on a sub-key.

For example, to get the distinct order IDs in each department:

~~~java
Map<String, Set<String>> ids = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.mapping(Order::id, Collectors.toSet())));
~~~

`mapping` does not change the outer classifier: groups are still by `department`, but the downstream content is `id`. When you only need the total record count, use `counting` instead of collecting a `Set` and calling `size`. When you need to count **distinct IDs**, a Set makes sense; note that `toSet()` makes no guarantees about ordering or implementation type.

To compute total quantity by department and payment status, you can use multi-level grouping:

~~~java
Map<String, Map<Boolean, Long>> nested = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.groupingBy(
                        Order::paid,
                        Collectors.summingLong(o -> (long) o.quantity()))));
~~~

With nested grouping, a `Boolean` key only appears when there is a corresponding record. If you want both `true` and `false` to always be present in every department, you need a separate policy/default; you can consider `partitioningBy(Order::paid, downstream)` after grouping by department.

## 7. `teeing()`: computing count and sum in a single collection pass

Since **Java 12**, `Collectors.teeing(downstream1, downstream2, merger)` distributes each element to two downstream collectors and finally merges the two results. Combined with groupingBy, each group can have both **record count** and **total amount**:

~~~java
record Summary(long count, long cents) {}

Map<String, Summary> reports = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Order::cents),
                        Summary::new)));
~~~

This is an illustrative snippet with `record Summary` placed inside a class; `orders` is a list of `Order` and requires importing `Map` and `Collectors`.

`teeing` is suitable when you need two independent statistics but want a combined result in a single collector. Some points to remember:

1. Each element of the group is processed by both the first and second downstream, which does not mean the `Stream` has to be reused twice.
2. `Summary::new` receives the two downstream values in the exact order `(count, cents)`; parameter order is crucial when both are `long`.
3. Both downstreams must be contract-safe when combining parallel results; do not pass custom accumulators with shared side effects.
4. If more than two metrics are needed, consider a specialized statistics collector or an accumulator with a clear contract, avoiding nesting multiple `teeing` calls that make code hard to read.

Another option for integers is `summarizingInt(Order::quantity)`, which returns an `IntSummaryStatistics` containing count, sum, min, max, and average in one result. When the data also requires the extreme **record** (not just a numeric value), `maxBy(OrderComparator)` still needs to be expressed separately.

## 8. Map type, key order, and null

### `groupingBy(classifier, downstream)` does not guarantee a specific Map

With the two-argument overload, Java does not guarantee `HashMap`, key ordering, thread safety, or serializability of the resulting Map. Do not write tests assuming groups will print in alphabetical order if no Map factory is specified.

To get a Map with `String` keys in natural order:

~~~java
Map<String, Long> countSortedByKey = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                TreeMap::new,
                Collectors.counting()));
~~~

The three-argument overload consists of **classifier, mapFactory, downstream**. Here `TreeMap::new` establishes the key-ordering contract; if keys do not support natural ordering or require a different rule, use `TreeMap` with an appropriate comparator.

### Null classifiers are not accepted

`groupingBy` enforces a contract that **does not accept a classifier returning null**: doing so causes a `NullPointerException` when such an element is processed. Do not rely on `HashMap`'s ability to hold null to assume `groupingBy` also accepts null keys.

If department can be missing, you must decide on a policy:

~~~java
Map<String, Long> withUnknown = orders.stream()
        .collect(Collectors.groupingBy(
                o -> o.department() == null ? "UNKNOWN" : o.department(),
                Collectors.counting()));
~~~

This is an **illustrative snippet**: there is a risk of key collision if `"UNKNOWN"` is also a valid department; in real applications, choose a clearer sentinel or key type. Another option is to filter out records missing a group beforehand, but only if business rules allow dropping them.

### The entire source may be empty

An empty `orders.stream()` produces an empty Map. `groupingBy` does not automatically create departments that exist in a catalog. If a report must display groups with no orders with a count/sum of 0, you must merge with the original catalog key set after collecting or design a report with a fixed set of groups.

## 9. Complete Java 17+ example with verifiable stdout

Save as **`GroupMetricsDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupMetricsDemo {
    record Order(String id, String department, int quantity, long cents, boolean paid) {}
    record Summary(long count, long cents) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", "books", 2, 1200, true),
                new Order("B", "games", 1, 2500, true),
                new Order("C", "books", 3, 1600, false),
                new Order("D", "games", 4, 900, true),
                new Order("E", "books", 1, 2600, true),
                new Order("F", "toys", 5, 700, false),
                new Order("G", "games", 2, 2600, true)
        );

        Map<String, Long> counts = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.counting()));
        Map<String, Integer> units = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.summingInt(Order::quantity)));
        Map<String, Long> cents = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.summingLong(Order::cents)));

        Comparator<Order> byCentsThenId = Comparator
                .comparingLong(Order::cents).thenComparing(Order::id);
        Map<String, Optional<Order>> mostExpensive = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.maxBy(byCentsThenId)));

        Map<String, Long> paidCounts = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.filtering(Order::paid, Collectors.counting())));

        Map<String, Summary> summaries = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingLong(Order::cents),
                                Summary::new)));

        System.out.println("counts=" + counts);
        System.out.println("units=" + units);
        System.out.println("cents=" + cents);
        System.out.println("paidCounts=" + paidCounts);
        System.out.println("summaries=" + summaries);
        mostExpensive.forEach((key, value) ->
                System.out.println("top " + key + "=" + value.orElseThrow().id()));
        System.out.println("noMissingKey=" + counts.containsKey("missing"));
    }
}
~~~

Compile and run with **JDK 17** or later:

~~~bash
javac GroupMetricsDemo.java
java GroupMetricsDemo
~~~

Exact output:

~~~text
counts={books=3, games=3, toys=1}
units={books=6, games=7, toys=5}
cents={books=5400, games=6000, toys=700}
paidCounts={books=2, games=3, toys=0}
summaries={books=Summary[count=3, cents=5400], games=Summary[count=3, cents=6000], toys=Summary[count=1, cents=700]}
top books=E
top games=G
top toys=F
noMissingKey=false
~~~

This is not accidental Map ordering: all six Maps use `TreeMap::new`, so they iterate keys `books`, `games`, `toys` in the natural order of `String`. `mostExpensive.forEach` also iterates in that order.

Detailed explanation:

- **`counts`**: books has three orders A, C, E; games has B, D, G; toys only has F.
- **`units`**: quantity for books = 2+3+1=6; games = 1+4+2=7; toys = 5.
- **`cents`**: total amount for books = 1200+1600+2600=5400; games = 2500+900+2600=6000; toys = 700.
- **`paidCounts`**: toys appears with `0` due to downstream filtering, even though it has no paid orders; this differs from filtering on the Stream before grouping.
- **`summaries`**: `teeing` collects both `count` and `summingLong` and merges them into `Summary`.
- **`mostExpensive`**: books picks E (2600), games picks G (2600), toys picks F (700). The comparator uses `id` as a secondary criterion to break ties in amount.
- **`noMissingKey=false`**: the Map does not contain groups that never appeared in the data.

Each call to `orders.stream()` creates a new Stream; a Stream that has already executed the terminal `collect` cannot be reused for another terminal operation.

## 10. Choosing a representative element and tie-breaking policies

The concept of "representative" depends on business requirements. Within a group, you may need:

| Purpose | Expression |
| --- | --- |
| Highest-value order | `maxBy(Comparator.comparingLong(Order::cents))` |
| Lowest-value order | `minBy(Comparator.comparingLong(Order::cents))` |
| Order with most items | `maxBy(Comparator.comparingInt(Order::quantity))` |
| Latest order | `maxBy(Comparator.comparing(Order::createdAt))` if `createdAt` actually exists in the model |
| Highest order, tie-broken by largest ID | `maxBy(comparingLong(...).thenComparing(...))` |
| All orders sharing the highest value | Requires a collector/algorithm keeping multiple elements; a single `maxBy` is not enough |

The `createdAt` entry in the table is an **idea to apply in a model with a timestamp field**, not a runnable call on the `record Order` in the current example.

Important: a `Comparator` can treat two objects as equal in ordering **without** making them equal according to `equals`. `maxBy` only uses the comparator to pick an extreme element; it does not perform `distinct()` deduplication. When the comparator lacks a secondary criterion, the representative chosen from tied elements may not match expectations, especially when traversal or parallelism changes. If selection must be deterministic, add a secondary criterion with a total order appropriate to the data.

### If you want to unwrap Optional in the result

One way to convert `Optional<Order>` to `Order` is using `collectingAndThen`:

~~~java
Map<String, Order> topByDept = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.collectingAndThen(
                        Collectors.maxBy(byCentsThenId),
                        Optional::orElseThrow)));
~~~

This is an **illustrative snippet** using the `orders` and `byCentsThenId` variables already defined. Because `groupingBy` invokes the downstream on groups that have at least one element from the source, the extreme-value `Optional` is normally present. However, if you build a custom collector or use a variant whose downstream filters out all elements, the Optional can be empty; in that case `orElseThrow()` throws `NoSuchElementException`. Choose a fallback or keep Optional when emptiness carries business meaning.

## 11. Grouping, partitioning, and multi-level grouping

`groupingBy` uses a classifier returning **any key K**, such as `String department`. `partitioningBy` splits by a `Predicate` into **two sides, `Boolean.TRUE` and `Boolean.FALSE`**:

~~~java
Map<Boolean, Long> paidUnpaid = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()));
~~~

The illustrative snippet above creates a Map with both true/false keys, even when one side has no elements (count 0), per the partitioning contract. This is the right choice if the main question is simply "paid or not", without needing a multi-valued classifier.

If you need to split by both department and status:

~~~java
Map<String, Map<Boolean, Long>> byDeptAndPaid = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.partitioningBy(
                        Order::paid,
                        Collectors.counting())));
~~~

Each department result will have two true/false branches per `partitioningBy`. This is one way to preserve a 0 value in a branch, unlike `groupingBy(Order::paid)` which may omit an absent branch.

Use multi-level grouping when the grouping dimensions truly add value; if only a simple report is needed, avoid nesting three or four levels of Maps that make downstream processing hard to follow.

## 12. Common mistakes

### Confusing record count with group count

`groupingBy(key, counting())` produces `Map<K, Long>`. `map.size()` is the number of groups; `map.get(key)` is the number of records in a group. If you want to count all elements, `stream.count()` needs no grouping.

### Using `summingInt` when the sum exceeds `int`

`summingInt` returns `Integer` and performs addition in the `int` range. If the sum is large, use `summingLong(o -> (long) o.quantity())` before adding. For money, choose the numeric type according to business limits and precision.

### Treating `maxBy` as a record instead of `Optional<Order>`

`Collectors.maxBy` returns `Optional<T>`. Therefore you cannot declare `Map<K, T>` unless you add a valid transformation step, such as `collectingAndThen` with explicit handling for empty.

### Missing tie-breaking rules

`maxBy(Comparator.comparingLong(Order::cents))` does not specify how to choose between two orders with the same amount. If it matters, add a deterministic criterion; if you want all tied orders, `maxBy` is not an expressive enough collector.

### Filtering beforehand and wondering why groups disappear

`stream.filter(p).collect(groupingBy(...))` drops records before keys are created. If you need **all groups present in the source** while counting only matching elements per group, use `groupingBy(key, filtering(p, counting()))`.

### Relying on the default Map's ordering

Default `groupingBy` does not promise key order or Map type. If ordering matters for report output, provide `TreeMap::new` or an appropriate Map type, or sort when presenting.

### Passing null from a classifier

`groupingBy` rejects null keys. Design a rule for "unknown" before grouping, or report a data error according to the contract.

### Collecting a List for every group just to sum numbers

`groupingBy(key)` returns `Map<K, List<T>>`, which can hold many extra references. If you only need count/sum/max, a dedicated downstream makes the intent clearer and usually saves work.

### Using a shared-state accumulator in a parallel stream

~~~java
// Do not use this approach:
// Map<String, Long> counts = new HashMap<>();
// orders.parallelStream().forEach(o ->
//         counts.merge(o.department(), 1L, Long::sum));
~~~

This example is wrong because it mutates an unsynchronized `HashMap` from multiple threads. Let `Collectors.groupingBy` manage collection and combining, or use `groupingByConcurrent` when appropriate for ordering, data, and thread-safety requirements. `groupingByConcurrent` is a concurrent/unordered collector; do not apply it mechanically when you need to preserve encounter order or determine a representative by encounter order.

### Assuming grouping creates groups with no data

Groups not present in the source will not automatically have keys. If a report needs every department in a catalog, add missing groups from the catalog after collecting or build a report structure with a fixed key set.

## 13. Performance, memory, and testing

- **Direct counting/summing:** `counting`/`summing...` downstreams keep a small accumulated state per group, without having to retain the full list of `Order`s like default `groupingBy(key)`.
- **Extrema:** `maxBy`/`minBy` only need to maintain the current candidate per group (in typical implementations) and the corresponding comparator.
- **Number of groups:** if the source has very many distinct keys, the Map and group states can still consume significant memory. Grouping does not make data "free".
- **Numeric computation:** `summingDouble` suffers from floating-point error; for exact monetary sums choose an integer type or `BigDecimal` as required.
- **Parallelism:** the collector manages the accumulator and combiner, but there is overhead in merging Maps/groups. Do not assume a parallel stream is always faster than sequential.
- **Testing:** test empty data, single-element groups, groups with count 0 after downstream filtering, extreme numeric values, comparators with ties, null keys, and expected Map ordering.

Do not put logging, email sending, or shared-data mutation inside classifiers/downstream mappers just to "piggyback" on the pipeline. They may be invoked differently depending on implementation or parallelism; it is best to use pure functions or ones that do not affect external state.

## 14. Tool selection table

| Requirement | Suitable downstream | Typical Map type |
| --- | --- | --- |
| Count records per group | `counting()` | `Map<K, Long>` |
| Total `int` quantity per group | `summingInt(getQuantity)` | `Map<K, Integer>` |
| Total quantity without `int` overflow | `summingLong(x -> (long) getQuantity(x))` | `Map<K, Long>` |
| Total `long` amount per group | `summingLong(getCents)` | `Map<K, Long>` |
| Average `double` per group | `averagingDouble(getScore)` | `Map<K, Double>` |
| Largest record by criterion | `maxBy(comparator)` | `Map<K, Optional<T>>` |
| Smallest record by criterion | `minBy(comparator)` | `Map<K, Optional<T>>` |
| Count by predicate while keeping groups | `filtering(predicate, counting())` | `Map<K, Long>` |
| Count and sum at the same time | `teeing(counting(), summingLong(...), Summary::new)` | `Map<K, Summary>` |
| Group by another sub-key | `mapping(mapper, downstream)` | `Map<K, R>` |
| Group and return ordered keys | `groupingBy(key, TreeMap::new, downstream)` | `TreeMap<K, R>` |

**In summary:** `groupingBy` determines the **group key**, while the downstream collector determines the **aggregation within each group**. Choose `counting` to count, `summingInt/Long` to sum, `maxBy/minBy` to pick a record by comparator, and `teeing` when combining two metrics. For accurate and stable reports, you must also define policies for **missing-data groups, null keys, numeric overflow, tied representatives, and output ordering**.