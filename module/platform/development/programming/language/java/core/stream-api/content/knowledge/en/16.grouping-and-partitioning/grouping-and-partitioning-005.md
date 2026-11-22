# Partitioning by Condition with `partitioningBy`

In the **Java Stream API**, we typically write a declarative pipeline consisting of a data source, *lazy* intermediate operations such as `filter` and `map`, and a terminal `collect` operation to build a result. When you want to split **all elements** into two groups based on a true/false condition, `Collectors.partitioningBy` is the collector designed for that purpose.

For example, a list of transactions needs to be split into **valid** and **invalid**, a list of tasks into **completed** and **incomplete**, or scores into **passing** and **failing**. Instead of filtering the same source twice, we partition the data with a predicate and obtain a `Map<Boolean, ...>`.

In the **Grouping and Partitioning** chapter, syntax alone is not enough. You need to understand the two `true`/`false` keys, the differences from `filter` and `groupingBy`, how to use downstream collectors, empty-input behavior, ordering, resources, and limitations in parallel execution.

## 1. Partitioning Means Splitting into Two Complementary Parts

Suppose the dataset is:

```text
Scores:     45  90  60  32  75
Condition:  score >= 60
               |
               +-- true  -> [90, 60, 75]
               +-- false -> [45, 32]
```

For each element `x`, the predicate `p(x)` returns exactly **one boolean value**. If `p(x) == true`, the element goes to the `true` branch; otherwise it goes to the `false` branch. The two branches are **disjoint** per evaluation and together cover the entire input.

This differs from calling `filter(p)`: `filter` **discards** elements that do not satisfy the condition, whereas `partitioningBy(p)` **keeps both sides** so you can inspect, report, or process them separately.

Minimal example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, List<Integer>> byPassing = scores.stream()
    .collect(Collectors.partitioningBy(score -> score >= 60));

System.out.println(byPassing.get(true));  // [90, 60, 75]
System.out.println(byPassing.get(false)); // [45, 32]
```

Do not misinterpret the key's meaning: `true` means **the predicate returned true**, not inherently "good", "successful", or "valid". If you write `score -> score < 60`, then `true` becomes the **failing** group.

## 2. Two Overloads of `Collectors.partitioningBy`

`partitioningBy` has been in `java.util.stream.Collectors` since Java 8, with two general overloads:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
partitioningBy(Predicate<? super T> predicate);

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
partitioningBy(
    Predicate<? super T> predicate,
    Collector<? super T, A, D> downstream
);
```

In the signatures above:

- `T`: element type of the stream.
- `predicate`: behavioral function `Predicate<? super T>` accepting an element and returning `boolean`.
- **One-parameter overload**: map values are `List<T>` containing the elements belonging to each branch.
- **Two-parameter overload**: `downstream` determines **the result type `D` of each branch**. It can be a count, sum, mapped list, statistics, or a nested grouping map.

Note: `partitioningBy` **creates a collector**, while `stream.collect(collector)` is the **terminal operation** that triggers stream traversal. The collector does not accept a pre-existing collection as an identity; the collection mechanism manages the accumulation containers and how they are combined.

## 3. Distinguishing `filter`, `partitioningBy`, and `groupingBy`

These three APIs are often placed side by side, yet they solve different problems:

| Tool | Typical result | Characteristics | Use when |
| --- | --- | --- | --- |
| `filter(predicate)` | `Stream<T>` with only matching elements | Lazy intermediate operation; non-matching elements are discarded | You only need **one side** of the condition. |
| `partitioningBy(predicate)` | `Map<Boolean, List<T>>` | Splits all elements into **two true/false branches** | You need both passing and failing groups. |
| `groupingBy(classifier)` | `Map<K, List<T>>` | Groups by a general key `K` | You need **multiple groups**, such as department codes or statuses. |

If you use `groupingBy(score -> score >= 60)`, the keys are also `Boolean`, but there is an important difference: `groupingBy` **is not required to create a key for a group that does not appear**. By contrast, `partitioningBy` **always contains both `true` and `false` keys**, even when one group receives no elements.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 90, 100);

Map<Boolean, List<Integer>> partitioned = scores.stream()
    .collect(Collectors.partitioningBy(score -> score >= 60));

Map<Boolean, List<Integer>> grouped = scores.stream()
    .collect(Collectors.groupingBy(score -> score >= 60));

System.out.println(partitioned.containsKey(false)); // true
System.out.println(partitioned.get(false));         // []
System.out.println(grouped.containsKey(false));     // false
```

For this reason, `partitioningBy` is very convenient when rendering a report table with **two fixed categories**, even if one of the two categories currently has no data.

You should not call `filter(p)` and `filter(p.negate())` on **the same Stream object**: after the first terminal operation, the stream has already been consumed. You can create a new stream from the `List` for each filter pass, but doing so processes the source multiple times and may observe different snapshots if the source mutates.

## 4. Both Keys Still Exist When One Branch or the Entire Source Is Empty

This is part of the `partitioningBy` **contract**, not incidental behavior of a particular JDK implementation:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<String>> empty =
    Collections.<String>emptyList().stream()
        .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(empty.size());        // 2
System.out.println(empty.get(true));     // []
System.out.println(empty.get(false));    // []
System.out.println(empty.containsKey(true));  // true
System.out.println(empty.containsKey(false)); // true
```

For the overload with a downstream collector, the result of an empty branch is produced **according to the downstream contract**:

| Downstream | Result for a branch with no elements |
| --- | --- |
| `Collectors.toList()` | An empty list. |
| `Collectors.counting()` | `0L`. |
| `Collectors.summingInt(...)` | `0`. |
| `Collectors.averagingInt(...)` | `0.0` by collector convention, which does not mean an observed average of 0. |
| `Collectors.maxBy(comparator)` | `Optional.empty()`. |
| `Collectors.summarizingInt(...)` | `IntSummaryStatistics` with `getCount() == 0`; min/max hold special initial sentinel values. |

Before interpreting `0.0` or the min/max of an empty group as real data, check the element count.

## 5. Only Need Counts: `partitioningBy` Combined with `counting`

If the goal is to count elements in each branch, do not build lists containing all data just to call `.size()`. Use `Collectors.counting()` as the downstream collector:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, Long> counts = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 3
System.out.println(counts.get(false)); // 2
```

The map value is now **`Long`**, not `List<Integer>`. There is no need to retain every score just to compute counts. Both keys always exist, so `counts.get(false)` returns `0L` if no one failed.

If you only need the passing count **without needing the failing count**, `scores.stream().filter(s -> s >= 60).count()` remains the most direct expression. Choose `partitioningBy` when you need both sides or need to coordinate statistics from both sides.

## 6. Computing Sums, Averages, and Multiple Statistics per Branch

Downstream collectors let you turn partitioning into a data aggregation rather than merely collecting elements:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, Integer> totals = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.summingInt(Integer::intValue)
    ));

Map<Boolean, Double> averages = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.averagingInt(Integer::intValue)
    ));

System.out.println(totals.get(true));   // 225
System.out.println(totals.get(false));  // 77
System.out.println(averages.get(true)); // 75.0
System.out.println(averages.get(false)); // 38.5
```

These are **two separate pipelines** over the same `List`. When you need count, sum, min, max, and average simultaneously **in a single logical collection pass**, use `Collectors.summarizingInt`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, IntSummaryStatistics> stats =
    Arrays.asList(45, 90, 60, 32, 75).stream()
        .collect(Collectors.partitioningBy(
            score -> score >= 60,
            Collectors.summarizingInt(Integer::intValue)
        ));

IntSummaryStatistics passed = stats.get(true);
System.out.println(passed.getCount());   // 3
System.out.println(passed.getSum());     // 225
System.out.println(passed.getMin());     // 60
System.out.println(passed.getMax());     // 90
System.out.println(passed.getAverage()); // 75.0
```

`IntSummaryStatistics.getSum()` returns `long`, helping avoid `int` overflow in many cases; the sum can still exceed the `long` range on extremely large datasets. `double` statistics can suffer from floating-point precision error. For empty inputs, check `getCount()` before interpreting min/max/average.

## 7. Storing Only the Needed Field with `mapping`

The two-parameter overload is especially useful when you want to **partition objects while keeping only one field**. Suppose a task has a name and a completion status:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class PartitionTaskNames {
    static final class Task {
        final String name;
        final boolean done;

        Task(String name, boolean done) {
            this.name = name;
            this.done = done;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("Design", true),
            new Task("Review", false),
            new Task("Test", true)
        );

        Map<Boolean, List<String>> namesByDone = tasks.stream()
            .collect(Collectors.partitioningBy(
                task -> task.done,
                Collectors.mapping(
                    task -> task.name,
                    Collectors.toList()
                )
            ));

        System.out.println(namesByDone.get(true));  // [Design, Test]
        System.out.println(namesByDone.get(false)); // [Review]
    }
}
```

`partitioningBy` evaluates `task.done` on the **original Task object**. The `mapping` downstream collector converts only the objects belonging to each branch into their names. This differs from calling `map(task -> task.name)` *before* `partitioningBy`: once the `done` field is lost, the predicate may no longer have enough data to classify elements.

If you only want to keep unique names, the downstream can be `Collectors.mapping(TaskNameMapper, Collectors.toSet())`. However, `toSet()` does not promise iteration order; when you need to preserve element encounter order, use `Collectors.toCollection(LinkedHashSet::new)` as the downstream after mapping.

## 8. Picking a Representative Element per Branch with `maxBy`

Each branch may need **a single** largest element rather than a list:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

Map<Boolean, Optional<Integer>> largest =
    Arrays.asList(45, 90, 60, 32, 75).stream()
        .collect(Collectors.partitioningBy(
            score -> score >= 60,
            Collectors.maxBy(Comparator.naturalOrder())
        ));

System.out.println(largest.get(true).orElse(-1));  // 90
System.out.println(largest.get(false).orElse(-1)); // 45
```

`Collectors.maxBy` returns an `Optional<T>` for each branch. When there are no elements, `Optional.empty()` expresses absence more clearly than a sentinel value like `-1`. In business logic, handle absence intentionally with `ifPresent`, `orElse`, or `orElseThrow`.

If you do not need partitioning and only want the maximum element of the entire stream, `stream.max(comparator)` is more direct.

## 9. Combining `groupingBy` and `partitioningBy`

One condition produces only **two groups**. When you need multi-dimensional classification, you can **nest collectors**. For example, within each department, you need the counts of completed and incomplete tasks:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TeamProgress {
    static final class Task {
        final String team;
        final boolean done;

        Task(String team, boolean done) {
            this.team = team;
            this.done = done;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("API", true),
            new Task("API", false),
            new Task("UI", true)
        );

        Map<String, Map<Boolean, Long>> counts = tasks.stream()
            .collect(Collectors.groupingBy(
                task -> task.team,
                Collectors.partitioningBy(
                    task -> task.done,
                    Collectors.counting()
                )
            ));

        System.out.println(counts.get("API").get(true));  // 1
        System.out.println(counts.get("API").get(false)); // 1
        System.out.println(counts.get("UI").get(true));   // 1
        System.out.println(counts.get("UI").get(false));  // 0
    }
}
```

At the outer level, `groupingBy` creates keys only for **departments that actually appear**. At the inner level, every department that appeared receives **both boolean keys**, even if one branch has no tasks. Calling `counts.get("UNKNOWN")` may return `null` because that department is absent from the outer map.

You can reverse the nesting order to get `Map<Boolean, Map<String, List<Task>>>` if the application needs to inspect the two statuses first and then the teams. Choose the map shape that gives the most common queries a clear access path.

## 10. Multiple Conditions: The Boundary of `partitioningBy`

A predicate always returns `boolean`, so each use of `partitioningBy` can split into only **two sides**. If there are three score levels—`FAIL`, `PASS`, `EXCELLENT`—`groupingBy` with a classifier returning an enum is usually a better fit:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ScoreLevels {
    enum Level { FAIL, PASS, EXCELLENT }

    static Level classify(int score) {
        if (score < 60) return Level.FAIL;
        if (score < 90) return Level.PASS;
        return Level.EXCELLENT;
    }

    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);
        Map<Level, List<Integer>> byLevel = scores.stream()
            .collect(Collectors.groupingBy(ScoreLevels::classify));

        System.out.println(byLevel.get(Level.FAIL));      // [45, 32]
        System.out.println(byLevel.get(Level.PASS));      // [60, 75]
        System.out.println(byLevel.get(Level.EXCELLENT)); // [90]
    }
}
```

If **two independent conditions** must be tracked, do not force them into a long, hard-to-read predicate. Instead, group by a pair of statuses or use a two-level classification structure. Note that nesting `partitioningBy` twice creates **four boolean combinations**, which differs from a mutually exclusive three-level classification.

## 11. Element Order, Mutability, and Collector Guarantees

When the source has encounter order, such as `List.stream()`, elements inside each resulting list of `partitioningBy(predicate)` preserve the **relative order** in which they appeared in the source:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> values =
    Arrays.asList(5, 4, 3, 2, 1).stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

System.out.println(values.get(true));  // [4, 2]
System.out.println(values.get(false)); // [5, 3, 1]
```

However, do not infer that iterating `entrySet()` or `keySet()` of the map yields `false` before `true` (or vice versa). If you need a fixed report layout, access `result.get(true)` and `result.get(false)` directly in the desired order.

The API does not guarantee the concrete implementation class, mutability, serializability, or thread-safety of the returned maps/lists. Do not write logic that depends on the map being a `HashMap` or the list being an `ArrayList`, or assume the result always allows `put`/`add`.

If you need an **unmodifiable** result for both the outer map and each branch's list, you can apply an explicit finishing step on Java 10+:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> snapshot = Arrays.asList(1, 2, 3, 4)
    .stream()
    .collect(Collectors.collectingAndThen(
        Collectors.partitioningBy(
            n -> n % 2 == 0,
            Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
            )
        ),
        Map::copyOf
    ));

System.out.println(snapshot.get(true)); // [2, 4]
// snapshot.put(true, Arrays.asList(8)); // UnsupportedOperationException
// snapshot.get(true).add(8);           // UnsupportedOperationException
```

`List.copyOf` and `Map.copyOf` reject `null` elements/values in contexts where nulls are disallowed, and produce an unmodifiable result without **deep-copying** mutable element objects. There is no need to wrap the map this way unless the application has a specific immutability requirement.

## 12. Parallel Execution: Predicate and Downstream Must Obey the Contract

`partitioningBy` works with both sequential and parallel streams:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Boolean, Long> counts = IntStream.range(0, 1_000_000)
    .parallel()
    .boxed()
    .collect(Collectors.partitioningBy(
        n -> n % 2 == 0,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 500000
System.out.println(counts.get(false)); // 500000
```

Parallel branches can process different parts of the source and then combine the statistical results. However, **`parallel()` does not guarantee a speedup**: boxing `int` to `Integer`, split/merge overhead, and source size all affect performance.

Important rules:

1. **The predicate must be non-interfering** (*non-interfering*) with the source and, whenever possible, **stateless** (*stateless*, not depending on mutable external state). For example, `n -> n % 2 == 0` is appropriate; `n -> counter++ % 2 == 0` is not.
2. Do not mutate the source collection while the pipeline is traversing it.
3. Do not append elements to a shared `ArrayList` outside a lambda on a parallel stream. Let the collector handle accumulation and combination.
4. Downstreams such as `counting`, `summingInt`, and `toList` must conform to the collector contract. A custom collector with shared mutable state can corrupt results.
5. Do not assume the predicate executes in the original list order or on the same thread. If deterministic ordering is needed in the result, preserve encounter order and choose appropriate collectors.

Example to avoid:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

AtomicInteger calls = new AtomicInteger();

// SEMANTICALLY WRONG: grouping depends on predicate invocation schedule.
Map<Boolean, List<Integer>> unstable = IntStream.range(0, 100)
    .parallel()
    .boxed()
    .collect(Collectors.partitioningBy(n ->
        calls.getAndIncrement() % 2 == 0
    ));
```

Crucially, **do not use** this style of classification. `AtomicInteger` ensures the increment itself is atomic, but does not determine when a particular element is evaluated. Which branch elements land in depends on the parallel execution schedule rather than a stable property of the data.

## 13. Business Example: Eligible Orders Report

Suppose each order has an ID, an integer total amount in the smallest currency unit, and a payment status. An order is considered **eligible for processing** when it is paid and its total amount is greater than 0. We need both the count and the total amount for both sides:

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class OrderReport {
    static final class Order {
        final String id;
        final boolean paid;
        final long amount;

        Order(String id, boolean paid, long amount) {
            this.id = id;
            this.paid = paid;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("A", true, 1200L),
            new Order("B", false, 500L),
            new Order("C", true, 800L),
            new Order("D", true, 0L)
        );

        Predicate<Order> eligible =
            order -> order.paid && order.amount > 0;

        Map<Boolean, LongSummaryStatistics> report = orders.stream()
            .collect(Collectors.partitioningBy(
                eligible,
                Collectors.summarizingLong(order -> order.amount)
            ));

        System.out.println(report.get(true).getCount()); // 2
        System.out.println(report.get(true).getSum());   // 2000
        System.out.println(report.get(false).getCount()); // 2
        System.out.println(report.get(false).getSum());   // 500
    }
}
```

Here, partitioning only decides **which side an order belongs to**. The `summarizingLong` downstream sums all orders in each side, including ineligible orders routed to the `false` branch. If you want to know the **reason** for ineligibility (unpaid, invalid amount, etc.), a Boolean alone is insufficient; group by a specific status type or collect additional explanatory details.

## 14. Common Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Using `filter` when both sides are needed | Non-matching data is discarded. | Use `partitioningBy` and read `get(true)`/`get(false)`. |
| Using `groupingBy(predicate)` and assuming both keys exist | A group with no elements may be absent. | Use `partitioningBy` when both keys are required. |
| Assuming key `true` always means passing/valid | Depends on the predicate itself. | Give the predicate a clear name and document the condition's meaning. |
| Collecting a list then calling `.size()` just to count | Wastes memory holding unused elements. | `partitioningBy(p, counting())`. |
| Treating an empty branch's `0.0` average as a measured result | No samples exist, yet it is displayed as valid data. | Check sample count with `counting` or `SummaryStatistics.getCount()`. |
| Assuming the resulting map is always mutable or has a specific iteration order | Not guaranteed by the collector. | Access via the two Boolean keys; create a snapshot/result type as needed. |
| Predicate has side effects or uses a shared counter | Unstable parallel results, hard to test. | Use a pure predicate based on the element's data. |
| Collecting an entire infinite stream | `collect` never finishes unless data is bounded. | Use `limit`, a finite source, or a real termination condition. |
| Using `partitioningBy` for three mutually exclusive states | Result has only two boolean branches. | Use `groupingBy` with an enum/classifier. |

### Lifecycle and Resource Notes

`collect(partitioningBy(...))` is a terminal operation; **the same `Stream` object cannot be reused** afterward. For `Files.lines` or other I/O sources, use `try-with-resources` to close the stream; `collect` does not automatically close all source resources. Collection operations generally traverse the entire finite source, so infinite streams must be bounded before partitioning.

## 15. Practice Exercises

**Exercise 1 — Split even/odd.** From `IntStream.rangeClosed(1, 10).boxed()`, use `partitioningBy(n -> n % 2 == 0)` to obtain two lists. Predict `get(true) = [2, 4, 6, 8, 10]` and `get(false) = [1, 3, 5, 7, 9]`.

**Exercise 2 — Empty branch case.** From `Stream.of(70, 80)`, partition by `score >= 60`; check both `containsKey(true)` and `containsKey(false)`. Then compare with `groupingBy(score -> score >= 60)` and explain why the second map may lack the `false` key.

**Exercise 3 — Statistics.** From scores `[45, 90, 60, 32, 75]`, use `partitioningBy` with `counting`, then with `summarizingInt`. Verify that the passing branch has 3 elements, sum 225, and average 75.0. State how to handle the case when no score passes.

**Exercise 4 — Nested grouping.** Create a list of tasks with `team` and `done`. Use `groupingBy(team, partitioningBy(done, counting()))`. Verify that every team that appears has both `true` and `false` keys, even for a branch with 0 tasks.

**Exercise 5 — Reasoning about parallelism.** Use `IntStream.range(0, 1000).parallel().boxed()` to count even and odd groups. Explain why `n -> n % 2 == 0` is more reliable than a predicate based on an `AtomicInteger` counter, even though incrementing the counter is thread-safe.

**Key takeaway:** `Collectors.partitioningBy(predicate)` splits data into **two complementary branches** with both Boolean keys always present. When a result other than `List<T>` is needed, pass a downstream collector to count, sum, extract a representative value, or group further. Choose `filter` when only one side is needed, `groupingBy` when there are multiple categories, and keep predicates free of shared mutable state so pipelines remain clear, testable, and safe under parallel execution.
