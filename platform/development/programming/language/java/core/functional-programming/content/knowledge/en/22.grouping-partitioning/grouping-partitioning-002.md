# Multi-level Grouping and Nested `Map` Structures in Java Stream

When data must be classified by **multiple criteria**, Java Stream allows nesting `Collectors.groupingBy()` to create a multi-level `Map`. For example, given a list of support requests, we want to group by **region**, then **priority**, and then compute the count or total duration for each smallest group.

What matters is not just the syntax: the order of grouping levels determines the data structure, the downstream collector determines the value type at the leaves, and the `Map` implementation affects presentation order. The examples use Java 17+.

## 1. From Single-Level to Two-Level Grouping

Suppose the source element is described by a record:

```java
record Ticket(String region, String priority, int minutes) {}
```

This is an illustrative type declaration, placed inside a class or at an appropriate Java file level. `record` has been available since Java 17.

With a single grouping level:

```java
Map<String, List<Ticket>> byRegion = tickets.stream()
        .collect(Collectors.groupingBy(Ticket::region));
```

The key is the region name and the value is the list of tickets belonging to that region.

When you need to group further by priority:

```java
Map<String, Map<String, List<Ticket>>> grouped =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(Ticket::priority)
        ));
```

The two snippets above are inside a method that has `tickets` of type `List<Ticket>`, requiring `java.util.List`, `java.util.Map`, and `java.util.stream.Collectors`.

The result type is read from the outside in:

```text
Map<region, Map<priority, List<Ticket>>>

North
  High -> [ticket A, ticket B]
  Low  -> [ticket C]
South
  High -> [ticket D]
  Low  -> [ticket E, ticket F]
```

`groupingBy(Ticket::region, groupingBy(Ticket::priority))` and `groupingBy(Ticket::priority, groupingBy(Ticket::region))` **do not have the same shape**: the first looks up by region first, while the second looks up by priority first. Choose the order based on the lookup operation or UI you need to build.

## 2. The Downstream Collector Determines the Group's Data

The general form is `Collectors.groupingBy(classifier, downstream)`:

- `classifier` transforms an element `T` into a group key `K`, for example `Ticket::region`.
- `downstream` receives the elements with the same key and aggregates them into a value `D`.
- The result has the form `Map<K,D>`. If `downstream` is another `groupingBy`, `D` is itself another `Map`.

The downstream at the final level determines the leaf value:

| Final Downstream | Leaf Data Type | Use When |
| --- | --- | --- |
| `toList()` | `List<Ticket>` | You need to keep each individual record |
| `counting()` | `Long` | You need to count elements |
| `summingInt(Ticket::minutes)` | `Integer` | You need the total minutes |
| `averagingInt(Ticket::minutes)` | `Double` | You need the average |
| `mapping(Ticket::minutes, toList())` | `List<Integer>` | You only need one attribute |
| `summarizingInt(Ticket::minutes)` | `IntSummaryStatistics` | You need count, sum, min, max, and average at the same time |

For example, instead of storing lists of tickets, we can count them:

```java
Map<String, Map<String, Long>> counts =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.counting()
                )
        ));
```

This snippet requires the `Ticket` type, `tickets`, and imports from above. Notably, `counting()` returns `Long`, **not `Integer`**.

## 3. Complete Runnable Java 17+ Program

So that the printed output has a deterministic order, the example uses `TreeMap` at **both levels**. Save it as `NestedGroupingDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NestedGroupingDemo {
    record Ticket(String region, String priority, int minutes) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("North", "High", 30),
                new Ticket("South", "Low", 10),
                new Ticket("North", "Low", 20),
                new Ticket("North", "High", 50),
                new Ticket("South", "High", 40),
                new Ticket("South", "Low", 15)
        );

        Map<String, Map<String, List<Ticket>>> grouped =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.toList()
                        )
                ));

        grouped.forEach((region, byPriority) ->
                byPriority.forEach((priority, members) ->
                        System.out.println(
                                region + "/" + priority + " = "
                                + members.stream()
                                        .map(Ticket::minutes)
                                        .toList()
                        )
                )
        );

        Map<String, Map<String, Integer>> totals =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.summingInt(Ticket::minutes)
                        )
                ));

        Map<String, Map<String, Long>> counts =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.counting()
                        )
                ));

        System.out.println("totals = " + totals);
        System.out.println("counts = " + counts);
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 NestedGroupingDemo.java
java NestedGroupingDemo
```

Stdout:

```text
North/High = [30, 50]
North/Low = [20]
South/High = [40]
South/Low = [10, 15]
totals = {North={High=80, Low=20}, South={High=40, Low=25}}
counts = {North={High=2, Low=1}, South={High=1, Low=2}}
```

**Why is the printed order above deterministic?** `TreeMap<String,...>` iterates keys in natural order: `North` before `South`, `High` before `Low`. In the leaf lists, the `tickets` source has an encounter order and a sequential pipeline preserves the appearance order of records, so `North/High` is `[30, 50]`.

All three `collect` calls create a new stream from the list. A `Stream` must not be reused after a terminal operation.

## 4. Controlling the `Map` Type at Each Level

You should not rely on the iteration order of the `Map` returned by the `groupingBy(classifier, downstream)` overload. The API makes no guarantees about the specific `Map` type or key order.

The three-argument overload lets you specify a map factory:

```java
Collectors.groupingBy(classifier, mapFactory, downstream)
```

In the program above, `TreeMap::new` appears twice because we want to sort keys at both levels.

If you want to iterate groups in **first-appearance** order, you can choose `LinkedHashMap` with an ordered sequential stream:

```java
Map<String, Map<String, List<Ticket>>> insertionOrdered =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                java.util.LinkedHashMap::new,
                Collectors.groupingBy(
                        Ticket::priority,
                        java.util.LinkedHashMap::new,
                        Collectors.toList()
                )
        ));
```

This snippet runs inside `main` of `NestedGroupingDemo`. `LinkedHashMap` preserves the key insertion order of the map itself. If you need a specific business order (for example Critical → High → Low), the natural order of `String` does not suffice: use an enum, a comparator for `TreeMap`, or sort at the presentation step.

## 5. Extracting Leaf Metrics with `mapping` and `summarizingInt`

If you only want the list of `minutes` in each group:

```java
Map<String, Map<String, List<Integer>>> minutesByGroup =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.mapping(
                                Ticket::minutes,
                                Collectors.toList()
                        )
                )
        ));
```

`mapping` transforms **each group's values** before passing them to the leaf collector. Calling `tickets.stream().map(Ticket::minutes)` before `groupingBy(Ticket::region)` would lose the `Ticket` object, leaving no `region` attribute to classify by.

When you need multiple statistics at once:

```java
Map<String, Map<String, java.util.IntSummaryStatistics>> stats =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.summarizingInt(Ticket::minutes)
                )
        ));

long northHighTotal = stats.get("North").get("High").getSum();
// 80L
```

Both snippets belong inside a class with `Ticket` and `tickets`. `getSum()` on `IntSummaryStatistics` returns **`long`**, so declare `long northHighTotal`, not `int`. If a group might not exist, perform a checked lookup first; see Section 8.

## 6. Three-Level Nesting and Complexity Limits

When there are three criteria, you can continue nesting downstream collectors:

```java
Map<String, Map<String, Map<String, Long>>> threeLevels =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.groupingBy(
                                t -> t.minutes() >= 30 ? "Long" : "Short",
                                Collectors.counting()
                        )
                )
        ));
```

This is `Map<region, Map<priority, Map<durationClass, count>>>`. For example, `threeLevels.get("North").get("High").get("Long")` is `2L`.

Multi-level nesting can suit tree-like UIs, but generic types and access chains grow long. For two- or three-dimensional reports aimed at **looking up key combinations** rather than traversing a tree, you can use a record as the key:

```java
record GroupKey(String region, String priority) {}

Map<GroupKey, Long> countByPair = tickets.stream()
        .collect(Collectors.groupingBy(
                t -> new GroupKey(t.region(), t.priority()),
                Collectors.counting()
        ));
```

Declare the `GroupKey` record in the class, and place the `collect` snippet in a method with `tickets`; requires `java.util.Map` and `java.util.stream.Collectors`. A record provides `equals`/`hashCode` based on its components, making it suitable as a key. The resulting `Map<GroupKey, Long>` avoids `get(region).get(priority)` and instead looks up directly with `new GroupKey(region, priority)`.

## 7. Combining `groupingBy` with `partitioningBy`

`groupingBy` classifies by keys produced by a classifier. `partitioningBy(predicate)` splits elements into two Boolean branches.

Group by region first, then partition long requests (`minutes >= 30`):

```java
Map<String, Map<Boolean, List<Ticket>>> byRegionAndDuration =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.partitioningBy(t -> t.minutes() >= 30)
        ));
```

In the `North` group, the `true` branch contains the two 30- and 50-minute tickets, and the `false` branch contains the 20-minute ticket. `partitioningBy` creates both `true` and `false` keys, even when one branch has no elements.

Reversed order:

```java
Map<Boolean, Map<String, Long>> countsByDuration =
        tickets.stream().collect(Collectors.partitioningBy(
                t -> t.minutes() >= 30,
                Collectors.groupingBy(
                        Ticket::region,
                        Collectors.counting()
                )
        ));
```

With this approach, the outer key is `Boolean`, while the inner key is `String region`. The two structures differ in their **access path**, so choose according to your application's needs.

## 8. Accessing Potentially Absent Groups

Writing directly:

```java
List<Ticket> critical = grouped.get("West").get("Critical");
```

can throw `NullPointerException` if `"West"` is not in the outer map. Even if `"West"` is present, `get("Critical")` can still return `null`.

Safer lookup:

```java
List<Ticket> critical = grouped
        .getOrDefault("West", Map.of())
        .getOrDefault("Critical", List.of());

int total = totals
        .getOrDefault("West", Map.of())
        .getOrDefault("Critical", 0);
```

These snippets run inside `main` of `NestedGroupingDemo`. `Map.of()` and `List.of()` create immutable fallbacks, suitable for **read-only** use.

However, using `0` as a fallback hides the difference between "group does not exist" and "group has an actual sum of 0". If this distinction has business significance, check `containsKey` or return an optional result representation.

`computeIfAbsent` can create a new group in a mutable map, so it is not a pure read operation. Do not use it just to read statistics unless you intend to mutate the result data.

## 9. Handling `null` Keys and Key Normalization

`groupingBy` does not allow the classifier to return a `null` key under the standard collector behavior: a `NullPointerException` may occur when grouping data. For real-world sources, define a policy for handling missing values.

For example, specifying that a missing region goes into the `"UNKNOWN"` group:

```java
Map<String, Long> byRegion = tickets.stream()
        .collect(Collectors.groupingBy(
                t -> t.region() == null ? "UNKNOWN" : t.region(),
                Collectors.counting()
        ));
```

If missing data should cause an error, validate upfront and report clearly. Do not silently drop records just to make grouping succeed.

Besides `null`, the strings `"North"`, `"north"`, and `" North "` are **three distinct keys**. Only normalize with `trim()`, `toUpperCase(Locale.ROOT)`, or an enum if business rules genuinely treat them as the same group. This also affects cardinality (number of group keys) and report quality.

## 10. Notes on Parallel Streams and Memory

`groupingBy` can be used with a parallel stream, but intermediate results must be merged, which can sometimes increase overhead. `groupingByConcurrent` provides a concurrent collector when semantics and processing needs fit, but it has limitations:

- It does not preserve element encounter order or key iteration order in the result by default.
- A `ConcurrentMap` does not mean every value object inside the map is automatically thread-safe if external code modifies them concurrently.
- If you need lists in input order or a deterministic report, you must choose an explicit collection/sorting strategy.

Regarding memory, `Map<String, Map<String, List<Ticket>>>` holds references to every source element in the leaf lists. If you only need counts or sums, use `counting()`/`summingInt()` instead of `toList()` to avoid retaining record lists. For very large datasets in a database, consider `GROUP BY` at the source rather than loading every row into Java before grouping.

Choose the easy-to-understand sequential approach first, and benchmark on real data if considering switching to parallel.

## 11. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Swapping `groupingBy(region, groupingBy(priority))` | The map has outer/inner keys with different meaning than intended | Determine the lookup dimension first, then choose the grouping order |
| Writing only `groupingBy(region)` when intending to also group by priority | Leaves remain `List<Ticket>` | Nest `groupingBy(priority)` as the downstream |
| Using `Map<String, Map<String, Integer>>` with `counting()` downstream | Type error because `counting()` returns `Long` | Use `Map<String, Map<String, Long>>` |
| Calling `get(a).get(b)` when key `a` might be missing | Risk of `NullPointerException` | Check keys or use `getOrDefault` |
| Expecting `HashMap` to print in a fixed order | The collector does not guarantee key order | Use `TreeMap`, `LinkedHashMap`, or sort before display |
| `toMap(keyFn, valueFn)` with duplicate keys and no merge function | May throw `IllegalStateException` | Use `groupingBy` or specify a merge rule |
| Classifier returning `null` | `groupingBy` may throw `NullPointerException` | Validate or normalize missing keys per contract |
| Nesting too many levels | Complex generics; many sub-maps, hard to traverse | Consider a composite record key or DTO |
| Using `toList()` at leaves when only counts are needed | Retains unnecessary data | Use `counting`, `summarizingInt` downstream |
| Assuming parallel `groupingByConcurrent` preserves source order | Order may be non-deterministic | Choose collector and display order intentionally |

## 12. Self-Check Questions

**Question 1.** What data type does `groupingBy(Ticket::region, groupingBy(Ticket::priority))` produce?

**Answer:** `Map<String, Map<String, List<Ticket>>>`, assuming both region and priority are `String`.

**Question 2.** To count tickets by each region and priority, which final downstream should you use?

**Answer:** `Collectors.counting()`; the leaf type is `Long`.

**Question 3.** To sort keys at both levels in natural order, what should you do?

**Answer:** Use the `groupingBy(classifier, TreeMap::new, downstream)` overload at **both levels**.

**Question 4.** Why can `grouped.get("West").get("High")` fail?

**Answer:** If the key `"West"` does not exist, `get("West")` returns `null`, so calling `.get("High")` will throw `NullPointerException`.

**Question 5.** If you only need two-dimensional statistics, what alternative is there to a nested Map structure?

**Answer:** Use `record GroupKey(region, priority)` as the key for `Map<GroupKey, Long>` and `counting()` as the downstream.

**Question 6.** What is the main difference between `partitioningBy` and `groupingBy`?

**Answer:** `partitioningBy` splits by a predicate into two Boolean keys `true`/`false`, even if one branch is empty; `groupingBy` creates keys based on the classifier and source data.

## Key Takeaways

- Nesting `groupingBy` as a downstream creates a `Map<K1, Map<K2, D>>` structure.
- **Classifier placement determines grouping level order** and access paths.
- **The final downstream determines the leaf type:** list, count, sum, average, or statistics.
- For explicit key ordering, use the `groupingBy(classifier, mapFactory, downstream)` overload at the required levels.
- Look up potentially absent groups safely; validate/normalize input keys.
- When dealing with many dimensions or large datasets, consider composite record keys or grouping at the data source.
